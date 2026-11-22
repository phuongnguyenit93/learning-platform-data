# Review tài liệu trước khi công bố

## 1. Mục tiêu và bối cảnh

Tài liệu REST API được sinh từ HTTP tests có thể phản ánh chính xác request/response mà test đã thực thi. Tuy vậy, **test pass và tài liệu render thành công chưa đủ điều kiện để công bố**. Trước khi phát hành, nhóm cần xác minh nội dung đúng với API contract, không tiết lộ dữ liệu nhạy cảm, đúng đối tượng người đọc và được owner có thẩm quyền phê duyệt.

Với Spring REST Docs, review cần xem cả source viết tay, generated snippets, trang đã assemble và rendered output. Một header đã bị che trong trang chính vẫn có thể xuất hiện trong curl snippet, HTML hoặc artifact CI. Một operation nội bộ có thể vô tình được đưa vào bundle public. Một link tương đối có thể trỏ tới trang nội bộ hoặc tài nguyên không được phép chia sẻ.

Bài học thuộc chương **Bảo mật** của module **SPRING_REST_DOCS**. Module tạo tài liệu REST API có thể kiểm chứng từ HTTP tests dùng MockMvc, WebTestClient hoặc REST Assured; sinh snippet cho request, response, payload, tham số và header; biên soạn Asciidoctor/Markdown và tích hợp build/CI.

Sau bài học, bạn có thể xây dựng quy trình review trước khi publish; phân biệt kiểm tra kỹ thuật, bảo mật, quyền riêng tư và phê duyệt nội dung; xác minh snippets; phân loại public/internal/partner-only docs; kiểm tra secrets, PII, hostnames, links và artifacts; giao rõ trách nhiệm reviewer và release owner.

## 2. Vì sao cần review trước khi publish?

REST Docs tăng độ tin cậy bằng cách sinh snippets từ HTTP tests, nhưng test chỉ chứng minh hành vi đã được kiểm tra trong fixture và môi trường test. Nó không tự xác nhận:

- Operation có được phép công khai hay chỉ dùng nội bộ.
- Ví dụ có chứa token, cookie, email hoặc dữ liệu cá nhân không.
- Hostname, IP, path hoặc header có tiết lộ kiến trúc nội bộ không.
- Mô tả viết tay có đúng semantics và giới hạn nghiệp vụ không.
- Link, image và artifact có thể truy cập đúng audience không.
- Tài liệu có công bố feature chưa release hoặc endpoint deprecated không.

Review là cổng kiểm soát nội dung trước khi tài liệu rời khỏi workspace/build environment.

## 3. Xác định audience và classification

Trước khi review chi tiết, xác định ai sẽ đọc tài liệu và nơi phát hành:

| Classification | Audience | Ví dụ |
| --- | --- | --- |
| Public | Bất kỳ người dùng internet nào | Public API, sandbox contract, hướng dẫn tích hợp. |
| Partner-only | Đối tác được cấp quyền | Partner API, callback contract, onboarding. |
| Internal | Nhân viên và service nội bộ | Service-to-service APIs, operational endpoints. |
| Restricted | Nhóm có quyền cụ thể | Admin APIs, security flows, dữ liệu vận hành nhạy cảm. |

Classification cần được xác nhận bởi API owner hoặc policy tổ chức. Không suy luận rằng endpoint có path /internal thì chắc chắn private, hoặc endpoint đơn giản thì có thể public.

### 3.1. Public bundle phải được allowlist

Với tài liệu công khai, xác định rõ pages/operations được phép publish. Build public bundle từ allowlist đã review thay vì copy toàn bộ generated docs.

Kiểm tra operation có owner; method/path đúng release; không chứa admin/internal/test-only routes; không dẫn tới internal docs; không lộ private hostname, IP, environment name hoặc service topology; không bao gồm feature chưa release.

Nếu classification chưa rõ, giữ nội dung ngoài public bundle cho tới khi owner xác nhận.

## 4. Các lớp review

| Lớp | Câu hỏi chính | Người phù hợp |
| --- | --- | --- |
| Technical accuracy | Snippet và mô tả có đúng API behavior? | API developer/test owner. |
| Security | Có secret, auth detail hoặc internal information bị lộ? | Security reviewer/service owner. |
| Privacy/data | Có PII hoặc dữ liệu khách hàng thật? | Data/privacy owner theo policy. |
| Audience/classification | Nội dung có đúng public/partner/internal? | API/product owner. |
| Editorial/usability | Người đọc có hiểu và dùng được? | Documentation reviewer/API consumer. |
| Release approval | Artifact đúng version và destination? | Release owner/publisher. |

Một người có thể đảm nhiệm nhiều vai trò nếu policy cho phép. Tuy nhiên, người tạo nội dung không nên tự phê duyệt nội dung restricted khi tổ chức yêu cầu independent approval.

## 5. Review kỹ thuật: snippets và contract

Xác minh generated snippets được tạo từ test hiện tại:

- HTTP tests pass trên clean build.
- Operation identifier đúng và duy nhất.
- Request method, path và query parameters đúng.
- Request/response headers đúng contract.
- Status code và response body khớp assertions.
- Field descriptors không thiếu hoặc mô tả sai.
- Error scenarios quan trọng được ghi nhận.
- Snippets thuộc đúng operation/scenario, không bị ghi đè.
- Trang cuối include đúng file và extension.

Không chỉ nhìn rendered page. Khi cần điều tra, so sánh test, generated snippet và nội dung assembled để tìm nơi phát sinh sai khác.

### 5.1. Test coverage và API coverage

Một trang có snippet không chứng minh toàn bộ API đã được tài liệu hóa. Tạo operation inventory từ scope release và so sánh với docs:

- Mọi operation được công bố có test/documentation tương ứng.
- Operation bị loại khỏi release bundle có lý do.
- Status/error scenarios quan trọng được mô tả.
- Deprecated operations có nhãn phù hợp.
- Versioned endpoints nằm đúng section/version.

Không cần công bố mọi test nội bộ. Mục tiêu là docs đủ cho audience dự kiến và không tạo ấn tượng sai về API coverage.

## 6. Review bảo mật và secret scanning

Kiểm tra mọi tầng output, không chỉ source Markdown:

1. Generated snippets directory.
2. Assembled Markdown/Asciidoctor source.
3. Rendered HTML/PDF.
4. Test reports và logs được upload.
5. CI artifacts và preview deployments.
6. Public site sau publish.

Tìm các giá trị như Authorization bearer/basic credentials, Cookie/Set-Cookie, session ID, CSRF tokens, API keys, client secrets, access/refresh tokens, password, private keys, signed URLs, reset codes, internal hostnames, private IPs, file paths, environment names và stack traces có connection strings.

Dùng sentinel trong test fixture để chứng minh preprocessors đã che đúng. Secret scanner bổ sung cho redaction; không thay thế synthetic data ngay từ test.

### 6.1. False positives

Một chuỗi ví dụ có thể vô tình giống credential hợp lệ. Không dùng token thật rồi chỉ dựa vào việc “đã mask trên trang chính”. Scan toàn bộ output và artifacts trước upload.

Nếu scanner báo false positive, reviewer xác minh nguồn và ghi nhận ngoại lệ có scope hẹp. Không thêm allowlist tổng quát chỉ để CI xanh.

## 7. Review quyền riêng tư và dữ liệu mẫu

Kiểm tra email, số điện thoại, địa chỉ, tên người thật, customer/account/order IDs có thể truy ngược, ngày sinh, thông tin tài chính, free-text fields và URL/error message chứa identifiers.

Ưu tiên synthetic fixtures có quy ước dễ nhận biết, ví dụ domain example.test và identifiers dành riêng cho test. Nếu cần giữ hình dạng dữ liệu để minh họa validation, giữ format nhưng thay value bằng dữ liệu tổng hợp.

Không đưa PII vào tài liệu chỉ vì endpoint test hiện dùng fixture lấy từ production snapshot.

## 8. Review internal information và môi trường

HTTP snippets có thể tiết lộ hostname nội bộ/service discovery, private IP/port, namespace/cluster/cloud resource identifiers, debug headers, trace IDs, gateway/proxy details, file path, username hoặc version/build metadata chưa công bố.

Dùng URI preprocessors để chuẩn hóa scheme/host/port khi thích hợp, nhưng xác minh phạm vi API. Nếu path/query chứa thông tin nhạy cảm, xử lý riêng; đổi host không che query hoặc path.

Public documentation nên dùng hostname dành cho tài liệu/sandbox, không dùng địa chỉ nội bộ lấy từ CI.

## 9. Review links, assets và navigation

Kiểm tra links trong source và rendered site:

- Internal links có trỏ đúng page/anchor?
- Public page có link sang internal site?
- External links có đúng domain chính thức?
- Image, diagram và download files có được phép công bố?
- Link có signed query values hoặc access token?
- Base URL và relative path có đúng khi deploy?
- Navigation có làm lộ tên section restricted?

Chạy link checker trên output cuối. Link resolve thành công vẫn có thể dẫn tới nội dung sai audience; reviewer phải kiểm tra classification của destination.

## 10. Review nội dung và trải nghiệm người đọc

Kiểm tra API method/path và mục đích; authentication/authorization requirements; required/optional fields và constraints; status codes/error semantics; example values có chạy trong sandbox; placeholder được giải thích; version/deprecation/compatibility; tính nhất quán giữa overview, operation và schema; tiếng Việt, headings, tables và code blocks.

Không sửa generated snippets để làm ví dụ đẹp nếu sửa khiến snippet không còn phản ánh test. Nếu cần trình bày thân thiện hơn, chỉnh template hoặc phần diễn giải xung quanh.

## 11. Quy trình review theo pull request

~~~mermaid
flowchart TD
    A["Author updates tests/docs"] --> B["CI generates snippets"]
    B --> C["Redaction and secret scan"]
    C --> D["Assemble and render"]
    D --> E["Technical review"]
    E --> F["Security/privacy review"]
    F --> G["Audience and editorial review"]
    G --> H{"Required approvals complete?"}
    H -->|No| X["Do not publish"]
    H -->|Yes| I["Release approval"]
    I --> J["Publish approved artifact"]
~~~

PR nên hiển thị source/test changes, diff generated snippets, rendered preview artifact, secret scan/link check results, audience/classification và reviewer/owner approval status.

Reviewer cần xem output cuối, không chỉ source Markdown. Khi snippet đổi do API contract, xác minh đó là thay đổi có chủ đích.

## 12. Checklist trước khi công bố

### Nội dung và kỹ thuật

- [ ] Clean build chạy HTTP tests và sinh snippets mới.
- [ ] Operation identifiers không collision.
- [ ] Request/response/status/fields đúng contract.
- [ ] Operations public nằm trong inventory/allowlist.
- [ ] Deprecated/unreleased operations được xử lý đúng.
- [ ] Trang cuối include đúng snippets và render thành công.

### Bảo mật và quyền riêng tư

- [ ] Authorization, Cookie, Set-Cookie và CSRF values đã được xử lý.
- [ ] Body không còn password, token, API key hoặc private key.
- [ ] Query strings và signed URLs không còn secret.
- [ ] Không có PII hoặc dữ liệu production.
- [ ] Không có internal hostnames, IPs, file paths hoặc debug details.
- [ ] Secret scan chạy trên snippets, assembled docs và rendered output.
- [ ] CI logs/artifacts tuân thủ policy.

### Audience và release

- [ ] Classification public/partner/internal/restricted được xác nhận.
- [ ] Public bundle chỉ chứa allowlisted operations.
- [ ] Links/assets trỏ đúng audience và destination.
- [ ] Owner và reviewer có thẩm quyền đã approve.
- [ ] Artifact version/commit/destination được ghi nhận.
- [ ] Retention/access của preview artifact đúng policy.
- [ ] Publish job chỉ dùng artifact đã qua mọi gate.

## 13. Bằng chứng review và traceability

| Trường | Ví dụ |
| --- | --- |
| Documentation version | v2.4 |
| Source commit | Git commit SHA |
| Build ID | CI run identifier |
| API owner | Team/service owner |
| Classification | Public hoặc Internal |
| Test status | Passed |
| Secret scan | Passed, scanner/version |
| Link/render validation | Passed |
| Approvals | Reviewer identities theo policy |
| Destination | Site/project được phê duyệt |
| Published at | Release timestamp |

Manifest không chứa token, environment variables hoặc raw request/response. Chỉ lưu trạng thái và tham chiếu cần thiết.

## 14. Sau khi công bố: monitoring và rollback

Sau release:

- Kiểm tra URL public/internal thực tế.
- Xác minh access control và navigation.
- Kiểm tra artifact không bị expose qua directory listing hoặc link chia sẻ rộng.
- Theo dõi broken links và feedback API consumers.
- Cập nhật docs cùng release khi contract thay đổi.
- Khi phát hiện secret/PII, gỡ hoặc hạn chế truy cập theo incident policy.
- Rotate/revoke credential thật nếu có khả năng bị lộ.
- Xử lý CI artifacts, caches, Git history và mirrors theo từng hệ thống.
- Publish bản sửa sau khi scan/review lại.

Không coi sửa source và publish lại là đủ nếu bản cũ còn trong CDN, artifact store hoặc cache.

## 15. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| CI xanh nhưng public docs lộ endpoint nội bộ | Chỉ test/render, không classification | Public allowlist và owner approval. |
| Token không có trong trang chính nhưng còn trong artifact | Chỉ scan một output location | Scan snippets, reports, HTML và artifacts. |
| Reviewer chỉ xem source Markdown | Không có rendered preview | Đính kèm preview artifact trong PR. |
| Tài liệu mô tả sai status code | Không đối chiếu snippet/test | Review contract và assertions. |
| Public link trỏ tới internal page | Không kiểm tra audience destination | Link review và classification. |
| Ví dụ chứa dữ liệu production | Fixture lấy từ snapshot thật | Thay bằng synthetic data. |
| Scanner có false positives | Pattern/allowlist quá rộng | Sentinel và ngoại lệ scope hẹp. |
| Release không truy vết được | Không lưu commit/build/approval | Manifest không chứa secrets. |
| Bản cũ còn lộ sau khi sửa | CDN/artifact/cache chưa expire | Removal/retention theo provider. |
| Không ai chịu trách nhiệm phê duyệt | Role/owner không rõ | Gán API owner, security reviewer, publisher. |

## 16. Bài thực hành

Chuẩn bị release docs cho API có public endpoints, partner callbacks và internal admin operations.

1. Tạo inventory các operations dự kiến công bố.
2. Phân loại từng operation public/partner/internal/restricted.
3. Chạy clean REST Docs tests và tạo generated snippets.
4. Kiểm tra contract, identifiers, error scenarios và generated diff.
5. Scan snippets, assembled docs, HTML, reports và CI artifacts.
6. Kiểm tra PII, secret, hostname/IP và query strings.
7. Render preview, chạy link checker và kiểm tra navigation.
8. Tạo public bundle từ allowlist; xác minh không chứa partner/internal pages.
9. Gán API owner, security/privacy reviewer và release approver.
10. Tạo manifest gồm commit, build, classification, scan status và approvals.
11. Chỉ publish sau khi tất cả gate pass.
12. Mô phỏng secret leak sau publish và thực hành rollback, rotate/revoke, artifact cleanup.

**Tiêu chí hoàn thành:** có inventory/classification rõ; generated docs đúng contract; secret/privacy scan pass; rendered preview đã review; public bundle chỉ có nội dung được phép; approval/manifest truy vết được; có phương án xử lý sau publish.

## Tài liệu tham khảo

- [Spring REST Docs — Documenting Your API](https://docs.spring.io/spring-restdocs/reference/documenting-your-api.html)
- [Spring REST Docs — Preprocessing](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/preprocessors.html)
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [OWASP — Privacy by Design](https://owasp.org/www-project-top-10-privacy-risks/)
- [OWASP — CI/CD Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/CI_CD_Security_Cheat_Sheet.html)
