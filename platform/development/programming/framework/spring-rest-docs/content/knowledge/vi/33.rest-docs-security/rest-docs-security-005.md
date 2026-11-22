# Kiểm soát thư mục output và artifact tài liệu

## 1. Mục tiêu và bối cảnh

Spring REST Docs sinh snippets từ HTTP tests vào thư mục output. Build tool tiếp tục ghép snippets thành Asciidoctor/Markdown, render HTML và có thể đóng gói các file này thành CI artifacts hoặc publish lên website. Trong suốt vòng đời đó, tài liệu có thể chứa dữ liệu nhạy cảm nếu test fixture, request/response hoặc bước redaction chưa được cấu hình đúng.

Bảo mật không dừng ở việc che token trong snippet. Cần kiểm soát **nơi output được ghi, ai có thể đọc, artifact được lưu bao lâu, cách chia sẻ và cách xóa**. Một file không được commit vào Git vẫn có thể được upload vào CI artifact, cache, log hoặc website nội bộ có quyền truy cập rộng.

Bài học thuộc chương **Bảo mật** của module **SPRING_REST_DOCS**. Module tạo tài liệu REST API có thể kiểm chứng từ HTTP tests dùng MockMvc, WebTestClient hoặc REST Assured; sinh snippet cho request, response, payload, tham số và header; biên soạn Asciidoctor/Markdown và tích hợp build/CI.

Sau bài học, bạn có thể:

- Chọn thư mục output riêng cho generated snippets và rendered docs.
- Phân biệt source docs, generated output, cache, log và CI artifacts.
- Cấu hình Git ignore và quy tắc commit có chủ đích.
- Giới hạn quyền truy cập, retention và chia sẻ artifacts.
- Phân tách tài liệu nội bộ với tài liệu công khai.
- Dọn output/cache/artifact an toàn và xử lý khi phát hiện dữ liệu nhạy cảm.
- Thiết kế CI chỉ publish sau khi tests, redaction, scanning và review hoàn tất.

## 2. Nhận diện các loại output

Một pipeline REST Docs có thể tạo nhiều loại file ở nhiều vị trí:

| Loại | Ví dụ | Nội dung |
| --- | --- | --- |
| Source documentation | src/docs/asciidoc/index.adoc | Nội dung do nhóm biên soạn. |
| Generated snippets | build/generated-snippets/ | HTTP request/response, body, fields, links. |
| Assembled documentation | build/docs-source/ hoặc build/api-markdown/ | Trang đã ghép snippets. |
| Rendered site | build/docs/asciidoc/html5/ hoặc site/ | HTML, CSS, JS, images. |
| Test reports | build/reports/tests/ | Test result, failure details, có thể kèm dữ liệu request. |
| Logs | build/logs/ hoặc CI console | Diagnostics, đôi khi có headers/body. |
| Build cache | Gradle/Maven/CI cache | Intermediate outputs và task state. |
| CI artifacts | Artifact store của pipeline | File được upload để review/download. |

Tên thư mục chỉ là ví dụ. Hãy kiểm tra cấu hình Gradle/Maven, plugin docs và CI workflow của dự án để biết output thật sự nằm ở đâu.

Một dữ liệu nhạy cảm có thể đi qua nhiều vị trí. Chỉ scan thư mục generated-snippets là chưa đủ nếu assembled HTML hoặc test reports vẫn chứa giá trị ban đầu.

## 3. Tổ chức output trong build directory

Đặt generated outputs dưới build directory của project để phân biệt source với sản phẩm sinh tự động.

Ví dụ:

~~~text
project/
├── src/
│   ├── test/
│   └── docs/
│       └── asciidoc/
│           └── index.adoc
└── build/
    ├── generated-snippets/
    ├── docs-source/
    ├── docs/
    ├── reports/
    └── tmp/
~~~

Lợi ích:

- Output có thể tái tạo từ tests và source.
- Clean task có thể xóa output theo lifecycle của build.
- Không làm lẫn file sinh tự động với source được review.
- CI có thể upload đúng thư mục đã chọn.
- Có thể áp dụng quyền và retention khác nhau cho output nội bộ/public.

Không ghi generated snippets vào source folder chỉ để tiện include. Nếu cần chia sẻ snippets để review, tạo artifact có chủ đích và kiểm tra nội dung trước khi chia sẻ.

### 3.1. Phân tách output theo mục đích

Có thể tách:

- generated-snippets: dữ liệu REST Docs vừa sinh.
- docs-source: source đã assemble.
- docs-public: site đã được kiểm tra và cho phép công khai.
- docs-internal: tài liệu nội bộ có giới hạn truy cập.
- reports: kết quả test, lint, link check và security scan.

Không phải dự án nào cũng cần tất cả folder. Quan trọng là mỗi loại output có chủ sở hữu, mục đích và chính sách truy cập rõ ràng.

## 4. Quản lý Git: ignore output và commit có chủ đích

Generated snippets thường được tạo lại bằng test, vì vậy build outputs không nên tự động trở thành source of truth. Quy tắc ignore có thể gồm:

~~~gitignore
# Build outputs
/build/
/target/

# Generated REST Docs snippets
/generated-snippets/

# Local documentation preview
/site-preview/
~~~

Các pattern trên là ví dụ; kiểm tra repo hiện có trước khi thêm để không ignore nhầm output được project chủ động version-control.

Không thêm một quy tắc ignore rộng nếu repository đang commit một thư mục docs output có chủ đích. Nếu cần lưu snapshot public docs trong Git, hãy lưu đúng thư mục được review, không commit raw snippets hoặc test reports ngoài ý muốn.

### 4.1. Khi nào commit generated snippets?

Thông thường không cần commit snippets nếu:

- Tests tạo lại ổn định.
- Build/CI có thể tạo docs từ source.
- Reviewer có thể xem rendered artifact của pull request.

Có thể commit khi tổ chức yêu cầu snapshot generated output hoặc tài liệu được phát hành độc lập với source/build. Khi đó:

- Chỉ commit file đã được redaction và review.
- Có quy trình cập nhật snapshot từ build sạch.
- Không commit test report, cache, temporary files.
- Scan secret trước khi stage/commit.
- Review diff generated như một phần contract API.

Không dùng generated file đã commit làm bằng chứng rằng test hiện tại đã chạy thành công. CI vẫn phải tái tạo snippets.

## 5. Quyền truy cập filesystem

Output tài liệu có thể chứa endpoint nội bộ, dữ liệu mẫu, thông tin lỗi hoặc identifiers. Giới hạn quyền truy cập theo nguyên tắc least privilege:

- Developer chỉ cần quyền đọc/ghi output trong workspace của họ.
- CI job chỉ ghi vào workspace và artifact locations cần thiết.
- Job publish chỉ đọc artifact đã qua kiểm tra.
- Người dùng không liên quan không cần quyền truy cập artifact nội bộ.
- Service account không nên dùng chung credentials với tài khoản cá nhân.
- Temporary directories không nên có quyền truy cập rộng hơn cần thiết.

Không đặt generated docs chứa dữ liệu nội bộ vào thư mục đồng bộ cloud/public share mặc định nếu chưa được phê duyệt theo policy của tổ chức.

### 5.1. Quyền đọc và quyền publish là hai quyền khác nhau

Một developer có thể được phép xem artifact nội bộ nhưng không được phép publish tài liệu ra website công khai. Tách quyền:

| Hành động | Quyền cần thiết |
| --- | --- |
| Sinh snippets local | Workspace write. |
| Xem CI artifact nội bộ | Artifact read. |
| Xóa artifact | Artifact administration hoặc quyền tương ứng. |
| Publish docs nội bộ | Quyền deploy vào internal site. |
| Publish public docs | Quyền release/publication riêng. |

Không dùng một credential có quyền admin để chạy mọi bước build/test/publish nếu có thể tách service accounts.

## 6. Bảo vệ CI artifacts

CI artifact tiện cho review nhưng thường được lưu ở hệ thống riêng với Git repository. Cần kiểm soát:

- Artifact nào được upload.
- Ai có quyền download.
- Artifact có được chia sẻ qua link công khai không.
- Thời hạn lưu.
- Có chứa source maps, logs, test reports hoặc raw snippets không.
- Artifact có được đưa vào cache dùng chung giữa branches/projects không.

Một artifact preview có thể chứa tài liệu nội bộ dù website production là private. Kiểm tra visibility của artifact store và quyền download, không suy luận từ quyền truy cập repository.

### 6.1. Chọn artifact cần upload

Thông thường chỉ upload:

- Rendered docs đã được redaction và scan.
- Preview artifact phục vụ review.
- Báo cáo validation không chứa raw secret.

Cân nhắc không upload:

- Raw HTTP traces.
- Full test logs có headers/body.
- Unfiltered generated snippets.
- Environment dumps.
- Build cache không cần cho review.

Nếu cần upload raw snippets để debug, giới hạn quyền, retention ngắn và không dùng dữ liệu production.

### 6.2. Retention

Đặt retention theo mục đích:

| Artifact | Retention gợi ý theo policy |
| --- | --- |
| PR preview | Ngắn, chỉ đủ thời gian review. |
| Test reports | Theo thời hạn điều tra lỗi của tổ chức. |
| Release docs artifact | Theo chính sách release/audit. |
| Debug artifact có dữ liệu nội bộ | Ngắn nhất có thể, giới hạn người đọc. |
| Public documentation | Theo vòng đời nội dung đã publish. |

Đây là nhóm tham khảo, không phải thời hạn cố định. Áp dụng retention policy của tổ chức và yêu cầu pháp lý/hợp đồng liên quan.

## 7. Phân tách tài liệu nội bộ và tài liệu công khai

Không phải mọi endpoint đều dành cho người dùng bên ngoài. Tài liệu có thể có:

- Public API contract.
- Internal service-to-service endpoints.
- Admin/operations endpoints.
- Sandbox/test-only endpoints.
- Partner-only API.
- Deprecated hoặc unreleased operations.

Tách output hoặc publication targets để tránh một bước publish vô tình đưa toàn bộ docs nội bộ ra public site.

Ví dụ cấu trúc:

~~~text
build/
├── docs-internal/
│   └── index.html
└── docs-public/
    └── index.html
~~~

Phân loại phải dựa trên policy và metadata được project quản lý, không dựa vào việc endpoint “trông có vẻ nội bộ”. Khi không rõ một operation có thể công khai hay không, không đưa nó vào public bundle cho tới khi owner xác nhận.

### 7.1. Allowlist public documentation

Một cách an toàn là định nghĩa danh sách pages/operations được phép publish public. Build tạo public bundle từ allowlist thay vì copy toàn bộ generated output.

Kiểm tra:

- Mọi operation public có owner.
- Không có admin/internal endpoints.
- Không có internal hostnames, private IPs hoặc environment names.
- Không có test-only routes hoặc credentials.
- Links không dẫn tới internal docs.
- Chỉ artifact public đã qua scan mới được deploy.

## 8. Làm sạch output và cache

Clean build giúp tránh snippet cũ bị include nhầm. Tuy nhiên, xóa output local không đồng nghĩa xóa artifact đã upload hoặc lịch sử Git.

Quy trình làm sạch nên:

1. Dừng task/process đang ghi output.
2. Xác định đúng generated directories do project sở hữu.
3. Dùng clean task hoặc cơ chế cleanup đã được build tool quản lý.
4. Không xóa source docs, test fixtures hoặc file người dùng tạo.
5. Chạy build lại để tái tạo snippets.
6. Kiểm tra artifact directory sau build.

Ví dụ Gradle:

~~~bash
./gradlew clean test asciidoctor
~~~

Ví dụ Maven:

~~~bash
./mvnw clean verify
~~~

Tên task/goal phụ thuộc cấu hình dự án. Lệnh trên chỉ minh họa clean lifecycle và build docs; cần gọi đúng task/goal tạo snippets và render.

### 8.1. Cache và output cũ

Build cache có thể lưu output task để tái sử dụng. Nếu task input/output khai báo sai, build có thể tái sử dụng artifact cũ. Hãy khai báo đúng inputs/outputs cho task sinh snippets và assemble docs.

Không đưa secret vào cache key, command line hoặc task arguments. Nếu artifact có dữ liệu nhạy cảm đã được cache, xử lý cache theo khả năng và policy của hệ thống CI/build cache.

## 9. Quy trình publish an toàn

Một publication pipeline nên có các cổng kiểm tra tuần tự:

~~~mermaid
flowchart TD
    A["Run HTTP tests with synthetic data"] --> B["Generate REST Docs snippets"]
    B --> C["Apply redaction"]
    C --> D["Assemble and render docs"]
    D --> E["Secret scan and content classification"]
    E --> F{"Approved for target audience?"}
    F -->|No| X["Block publication"]
    F -->|Yes| G["Review artifact and links"]
    G --> H{"Checks pass?"}
    H -->|No| X
    H -->|Yes| I["Publish to approved target"]
~~~

Trình tự đề xuất:

1. Tests dùng synthetic data.
2. REST Docs sinh snippets.
3. Preprocessors che header/body/link nhạy cảm.
4. Assemble source pages và render.
5. Secret scan trên snippets, assembled docs và HTML.
6. Kiểm tra phân loại public/internal và allowlist.
7. Review artifact, links và nội dung.
8. Publish bằng service account có quyền tối thiểu.
9. Ghi nhận version, commit và destination để truy vết.

Không publish chỉ vì build task render thành công. Render pass không chứng minh nội dung được phép công khai.

## 10. Xử lý khi phát hiện dữ liệu nhạy cảm trong artifact

Nếu phát hiện token, password, session ID hoặc PII trong generated output:

1. Dừng publish hoặc gỡ artifact khỏi nơi chia sẻ nếu đã phát hành.
2. Xác định giá trị có phải credential còn hiệu lực không.
3. Nếu là credential thật, revoke/rotate theo quy trình incident của tổ chức.
4. Xác định phạm vi: snippets, assembled pages, HTML, logs, CI artifacts, caches và Git history.
5. Hạn chế quyền truy cập trong khi điều tra.
6. Xóa hoặc expire artifact theo cơ chế của từng hệ thống.
7. Nếu secret đã commit, xử lý Git history theo policy và phối hợp owner repository.
8. Sửa fixture/preprocessor/scanner để ngăn tái diễn.
9. Tạo lại docs từ build sạch và xác minh không còn sentinel.

Không chỉ xóa file local rồi coi sự cố đã được xử lý. Artifact có thể tồn tại trong cache, mirror, download hoặc bản sao của người dùng đã truy cập.

## 11. Kiểm tra output trước khi upload

Trước khi upload artifact, xác minh:

- Đúng thư mục output được phép.
- Không có raw logs hoặc test reports không cần thiết.
- Redaction đã chạy trên request/response.
- Không có secret sentinel trong generated snippets.
- Không có internal hostname/IP trong public bundle.
- Không có file tạm, environment dump hoặc credentials.
- Tất cả links/assets cần thiết đã được render.
- Artifact name/version gắn với commit/build rõ ràng.
- Visibility và retention đúng policy.

Một manifest đơn giản có thể ghi lại tên artifact, commit SHA, thời điểm build, audience (internal/public) và bước validation đã pass. Không ghi secret hoặc token vào manifest.

## 12. Ví dụ cấu hình CI ở mức khái niệm

Pipeline có thể tách job build/test, scan và publish:

~~~yaml
jobs:
  docs-test:
    steps:
      - run: ./gradlew clean test asciidoctor
      - run: ./scripts/scan-docs-output.sh build/generated-snippets build/docs

  docs-review:
    needs: docs-test
    steps:
      - upload-artifact:
          name: docs-preview
          path: build/docs
          retention-days: 3

  docs-publish:
    needs: docs-review
    environment: approved-docs
    steps:
      - run: ./scripts/verify-public-docs.sh build/docs-public
      - run: ./scripts/publish-docs.sh build/docs-public
~~~

Đây là pseudoconfiguration để thể hiện dependency và trust boundaries; cú pháp upload artifact, retention và environment protection phụ thuộc CI provider. Trong thực tế, không cho job publish dùng artifact chưa được scan/review hoặc path có cả internal và public docs.

### 12.1. Tách quyền theo job

- Test job tạo snippets, không cần quyền publish.
- Scan job đọc output, không cần quyền sửa source hoặc deploy.
- Review job cung cấp artifact nội bộ với retention ngắn.
- Publish job chỉ nhận bundle public đã qua kiểm tra và dùng credential deploy riêng.

Tách job giúp giảm tác động nếu một bước test hoặc dependency bị compromise.

## 13. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Snippets bị commit ngoài ý muốn | Thiếu ignore rule hoặc stage toàn bộ build | Ignore đúng output, review staged diff. |
| PR artifact chứa internal endpoint | Upload toàn bộ site thay vì public bundle | Tách internal/public output và allowlist. |
| Người ngoài tải được preview | Artifact store có visibility rộng | Giới hạn quyền download và retention. |
| Token còn trong HTML dù snippet đã sạch | Assemble/render dùng output cũ hoặc log khác | Clean build và scan final output. |
| Clean local nhưng artifact vẫn tồn tại | CI artifact/cache độc lập với workspace | Expire/delete qua artifact provider. |
| Build dùng snippet cũ | Task inputs/outputs hoặc dependency sai | Khai báo task graph và clean lifecycle. |
| Public docs có hostname nội bộ | Không phân loại content trước publish | Scan hostnames và review allowlist. |
| Artifact lưu quá lâu | Không đặt retention | Áp dụng policy theo loại artifact. |
| Publish job có quyền quá rộng | Dùng chung credential với build job | Tách service account và least privilege. |
| Xóa file nhưng secret còn trong Git | File đã commit trong history | Rotate secret và xử lý history theo policy. |

## 14. Bài thực hành

Thiết lập pipeline tài liệu cho một API có public endpoints và internal admin endpoints.

Thực hiện:

1. Cấu hình REST Docs output dưới build directory riêng.
2. Xác định source docs, generated snippets, assembled pages, rendered site, reports và logs.
3. Thêm Git ignore cho generated outputs phù hợp repository.
4. Tạo public bundle từ allowlist; giữ admin/internal docs ở output riêng.
5. Chạy tests với synthetic data và redaction preprocessors.
6. Scan snippets, assembled Markdown/Asciidoctor và rendered HTML.
7. Upload preview artifact nội bộ với quyền và retention phù hợp.
8. Tách job test/scan/review/publish và service account tương ứng.
9. Chạy clean build để bảo đảm không dùng output cũ.
10. Mô phỏng phát hiện secret trong artifact; thực hành block publish và xác định nơi cần expire/delete.
11. Ghi manifest gồm commit, audience, build ID và validation status, không chứa secrets.

**Tiêu chí hoàn thành:** output nằm trong thư mục có chủ đích; Git không vô tình commit generated files; CI artifact có access/retention rõ; public/internal bundles tách biệt; secret scan chạy trước publish; clean build tái tạo được docs; và có quy trình xử lý artifact khi phát hiện dữ liệu nhạy cảm.

## Tài liệu tham khảo

- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
- [Gradle — Directory and File Operations](https://docs.gradle.org/current/userguide/working_with_files.html)
- [Git — gitignore](https://git-scm.com/docs/gitignore)
- [GitHub Actions — Store and Share Data with Workflow Artifacts](https://docs.github.com/en/actions/using-workflows/storing-workflow-data-as-artifacts)
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [OWASP — CI/CD Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/CI_CD_Security_Cheat_Sheet.html)
