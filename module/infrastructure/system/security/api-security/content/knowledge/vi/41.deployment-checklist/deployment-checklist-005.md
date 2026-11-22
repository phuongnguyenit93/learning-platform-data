# Checklist rate limit, quota, SSRF và dependency

Trước khi triển khai API, đội phát triển cần xác minh bốn nhóm kiểm soát thường bị bỏ sót: giới hạn tốc độ request (rate limit), quota sử dụng tài nguyên, chống Server-Side Request Forgery (SSRF) và an toàn dependency. Các nhóm này liên quan trực tiếp tới khả năng bị lạm dụng, chi phí vận hành, quyền truy cập mạng từ server và rủi ro chuỗi cung ứng phần mềm.

Checklist này dùng cho review trước release, go-live và kiểm tra định kỳ. Mỗi mục nên có trạng thái, bằng chứng, owner và kết quả xử lý. Không đánh dấu hoàn thành chỉ vì đã thêm một thư viện hoặc cấu hình; cần chứng minh policy được áp dụng trên mọi replica, mọi đường gọi và môi trường triển khai thực tế.

## 1. Xác định phạm vi và threat model trước release

Trước khi chọn ngưỡng hoặc bật scanner, hãy lập inventory những gì API có thể làm:

- Endpoint public, partner, internal và administrative.
- Endpoint không cần đăng nhập, endpoint cần user token và endpoint chỉ dành cho service identity.
- Operation có chi phí cao: search, report, export, upload, import, image/PDF processing, webhook delivery và batch mutation.
- Luồng server chủ động truy cập URL do user hoặc tenant cung cấp.
- Outbound dependency: payment, email, storage, identity provider, webhook destination, internal service và package registry.
- Dependency trực tiếp/gián tiếp, base image, build plugin, action và tool trong CI.
- Tenant, user, API client, provider account và tài nguyên có quota riêng.

Với mỗi luồng, xác định actor, dữ liệu, tài nguyên bị tiêu thụ, trust boundary, hậu quả nếu bị lạm dụng và cách phát hiện. Endpoint nội bộ vẫn cần kiểm soát vì request có thể đến từ workload bị xâm nhập hoặc service khác có bug.

## 2. Inventory endpoint và mức độ tốn tài nguyên

| Nhóm endpoint | Rủi ro chính | Kiểm soát cần có |
|---|---|---|
| Login, token, password reset | Brute force, credential stuffing, OTP abuse | Per-account/IP/device limits, anti-automation, lockout policy có kiểm soát |
| Read/list/search | Enumeration, query tốn CPU/DB | Principal/tenant limits, page-size cap, query timeout, object authorization |
| Create/update/delete | Spam, mass mutation, state abuse | User/tenant quota, idempotency, authorization và audit |
| Export/report | CPU, memory, storage và data exfiltration | Job quota, concurrency cap, cost budget, download authorization |
| Upload/import | File lớn, archive bomb, parser abuse | Byte/file count limits, content validation, scan, processing isolation |
| Webhook/callback | SSRF, retry storm, destination abuse | Destination policy, egress controls, signing, retry budget |
| URL preview/fetch | SSRF, redirect/DNS rebinding | URL validation, IP policy, redirect revalidation, egress proxy |
| Admin/bulk operation | Blast radius lớn | Strong authorization, step-up/approval, strict quota và audit |

Không dùng một rate limit chung cho mọi route. Một request đọc metadata và một request tạo báo cáo lớn có chi phí khác nhau. Hãy phân loại theo operation, cost và mức độ nhạy cảm.

## 3. Identity và quota key

- [ ] Rate limit được gắn với identity đã xác thực khi endpoint yêu cầu authentication.
- [ ] Tenant key lấy từ tenant context đã được server xác minh, không tin header/body do client tự khai.
- [ ] API key được chuyển thành client/key reference; không dùng raw secret làm Redis key hoặc log.
- [ ] Endpoint public có giới hạn theo IP/network/device signal phù hợp và có biện pháp chống distributed abuse.
- [ ] Có giới hạn riêng cho account, user, tenant, API client, route và global service khi cần.
- [ ] Service-to-service request được phân biệt theo workload/client identity.
- [ ] Proxy/CDN forwarding header chỉ được tin khi request đến từ proxy nằm trong trust configuration.
- [ ] Không dùng IP đơn lẻ làm identity duy nhất cho user đã xác thực; nhiều user có thể dùng chung NAT.

Rate limit theo IP hữu ích với pre-auth endpoint nhưng có thể ảnh hưởng người dùng chung mạng. Với authenticated API, principal và tenant thường là key quan trọng hơn. Kết hợp nhiều dimension giúp tránh một caller đổi IP để né quota hoặc một user dùng nhiều token để cộng dồn budget.

## 4. Rate limit và thuật toán

- [ ] Chọn thuật toán phù hợp: token bucket, sliding window, fixed window hoặc leaky bucket.
- [ ] Định nghĩa rõ burst capacity, refill rate và cửa sổ thời gian.
- [ ] Dùng shared/distributed state hoặc gateway global limiter cho quota cần áp dụng toàn hệ thống.
- [ ] Consume counter bằng thao tác atomic; không dùng read-modify-write rời rạc giữa nhiều replica.
- [ ] Local limiter chỉ là lớp bảo vệ process, không được coi là global quota.
- [ ] Quota không tăng khi autoscaling tạo thêm pod/instance.
- [ ] TTL của counter phù hợp cửa sổ và không làm reset budget sớm.
- [ ] Đồng hồ giữa node không tạo thêm token hoặc reset quota ngoài ý muốn.
- [ ] Key space có giới hạn; không cho client tạo vô hạn key bằng input tùy ý.
- [ ] Có giới hạn riêng cho route đắt tiền, authentication, upload và batch.

Ví dụ policy minh họa:

~~~yaml
rateLimits:
  - scope: user
    operation: profile-read
    capacity: 60
    refillPerSecond: 1
  - scope: tenant
    operation: report-create
    capacity: 10
    refillPerSecond: 0.1
  - scope: global
    operation: payment-provider
    capacity: 100
    refillPerSecond: 20
~~~

Các giá trị chỉ minh họa. Cần hiệu chỉnh bằng load test, SLA, provider contract và plan khách hàng. Policy phải được version hóa, review và rollout có kiểm soát.

## 5. Quota, concurrency và cost budget

Rate limit đếm tốc độ request; quota có thể đếm tổng usage theo kỳ; concurrency limit giới hạn số việc đang chạy. Một endpoint có thể cần cả ba.

- [ ] Có quota theo tenant/plan cho report, export, storage, message hoặc API credits.
- [ ] Có global cap bảo vệ database, provider account và service capacity.
- [ ] Có concurrency cap cho export, PDF/image processing, payment và background job.
- [ ] Có giới hạn kích thước payload, số phần tử batch, page size và số bản ghi export.
- [ ] Request/job tốn tài nguyên có cost weight hoặc estimate; client không tự khai cost.
- [ ] Reservation/settlement có idempotency để không double-charge khi retry.
- [ ] Job thất bại/hủy giải phóng reservation theo trạng thái rõ ràng.
- [ ] Queue có backlog cap, fairness theo tenant và admission control.
- [ ] Retry có exponential backoff, jitter, max attempts và retry budget.
- [ ] Provider 429/Retry-After được tôn trọng; không retry đồng loạt ngay lập tức.
- [ ] Database pool/concurrency được tính theo max replica và các workload khác.

Không dựa vào CPU autoscaling để kiểm soát quota nghiệp vụ. Autoscaling tăng capacity của ứng dụng nhưng không làm tăng giới hạn của tenant, database hay dịch vụ bên ngoài.

## 6. Response và hành vi khi vượt rate limit

- [ ] Trả HTTP 429 cho rate limit bị vượt theo API contract.
- [ ] Cung cấp Retry-After khi có thể xác định thời điểm thử lại.
- [ ] Error body ổn định, không tiết lộ tenant khác, raw key hoặc quota nội bộ.
- [ ] Phân biệt RATE_LIMIT_EXCEEDED, USAGE_QUOTA_EXCEEDED và CONCURRENCY_LIMIT_EXCEEDED nếu client cần hành động khác nhau.
- [ ] Không để response khác nhau vô tình tiết lộ sự tồn tại của account/object nhạy cảm.
- [ ] Client SDK không retry 429 ngay lập tức hoặc bỏ qua Retry-After.
- [ ] Có policy fail-open/fail-closed khi quota store không khả dụng.
- [ ] Fallback local có trần được thiết kế để không nhân tổng quota theo số pod.
- [ ] Endpoint thanh toán, tạo job đắt tiền hoặc provider egress có hành vi fail-closed/hạn chế phù hợp.

Fail-open có thể duy trì availability nhưng tạo đường vượt quota; fail-closed bảo vệ tài nguyên nhưng có thể từ chối request hợp lệ. Quyết định phải theo loại operation và tác động nghiệp vụ, không để thư viện limiter tự quyết định ngầm.

## 7. Chống abuse và enumeration

- [ ] Giới hạn số ID và object khác nhau được thử trong một cửa sổ thời gian.
- [ ] Giám sát burst 403/404, object reference tuần tự và request đến nhiều tenant.
- [ ] Kiểm tra object authorization độc lập với rate limit.
- [ ] List/search/count/export chỉ trả dữ liệu trong authorization scope.
- [ ] Batch endpoint authorize từng object và có giới hạn số phần tử.
- [ ] Có idempotency key cho thao tác tạo tài nguyên có thể bị retry.
- [ ] Có giới hạn OTP, password reset, invitation, webhook registration và API key creation.
- [ ] Phát hiện một tenant/user tiêu thụ cost cao dù request rate thấp.
- [ ] Không tự động khóa toàn bộ tenant chỉ từ một tín hiệu chưa được xác minh.

Rate limit làm chậm abuse nhưng không sửa BOLA, broken function authorization hay business-flow abuse. Quyền trên object, action và trạng thái nghiệp vụ vẫn phải được kiểm tra ở server.

## 8. Inventory luồng có nguy cơ SSRF

SSRF xảy ra khi server truy cập địa chỉ do caller kiểm soát và có thể bị dụ kết nối tới tài nguyên không được phép. Không chỉ endpoint có tên fetch-url mới có rủi ro. Hãy tìm mọi tính năng nhận URL/hostname hoặc kích hoạt network fetch:

- Webhook destination và callback URL.
- Import dữ liệu từ URL, remote file hoặc feed.
- Avatar/image/document preview và thumbnail generator.
- PDF renderer, HTML-to-PDF, screenshot service và headless browser.
- Link unfurling, metadata preview và URL scanner.
- XML/SVG/document parser có external entity hoặc external resource loading.
- OAuth/OIDC discovery, JWKS/custom issuer URL nếu cho phép cấu hình.
- Package/dependency mirror, plugin loader và integration endpoint.
- Backend proxy hoặc API nhận URL rồi tải nội dung.

Với mỗi luồng, ghi rõ scheme, host, port, redirect, DNS resolver, HTTP client, proxy, network egress và dữ liệu trả về. Nếu không cần server fetch URL do user cung cấp, loại bỏ khả năng đó khỏi thiết kế.

## 9. Validate URL đầu vào

- [ ] Chỉ cho phép scheme cần thiết, thường là HTTPS; HTTP chỉ khi có lý do nghiệp vụ rõ ràng.
- [ ] Từ chối scheme như file, ftp, gopher, data, jar và scheme không được hỗ trợ.
- [ ] Từ chối URL chứa username/password trong authority.
- [ ] Parse bằng một URL parser chuẩn; không dùng regex đơn giản làm bộ xác thực chính.
- [ ] Chuẩn hóa hostname/IDNA, dấu chấm cuối và biểu diễn IP trước khi so policy.
- [ ] Kiểm tra port theo allowlist; không mặc định cho mọi port.
- [ ] Không cho phép URL dạng IP literal nếu nghiệp vụ không cần; nếu cho phép, áp dụng IP policy đầy đủ.
- [ ] Nếu dùng hostname allowlist, so khớp ranh giới domain chính xác; không dùng endsWith tùy tiện.
- [ ] Không cho client điều khiển proxy, Host header hoặc TLS verification.
- [ ] Giới hạn độ dài URL và reject ký tự/control syntax không hợp lệ.

Ví dụ allowlist cho subdomain phải kiểm tra hostname bằng đúng domain hoặc kết thúc bằng dấu chấm + domain. So sánh chuỗi đơn giản có thể chấp nhận nhầm evil-example.com hoặc example.com.attacker.invalid. Sau canonicalization, vẫn phải kiểm tra DNS/IP và egress.

## 10. DNS resolution và IP address policy

- [ ] Resolve cả A và AAAA record bằng resolver được kiểm soát.
- [ ] Từ chối loopback, private, link-local, multicast, unspecified, reserved và các special-purpose range không được phép.
- [ ] Chặn IPv4-mapped IPv6 và các biểu diễn IP không chuẩn sau khi canonicalize.
- [ ] Từ chối hostname có bất kỳ kết quả DNS nào thuộc range bị cấm, trừ khi policy cho phép rõ ràng.
- [ ] Kiểm tra IP thực tế tại thời điểm kết nối, không chỉ kiểm tra DNS trước đó.
- [ ] Chống DNS rebinding và TOCTOU bằng cách pin/validate địa chỉ đã resolve ở tầng kết nối hoặc dùng egress proxy có policy.
- [ ] Không để HTTP client tự resolve lại hostname sang địa chỉ khác sau bước validation.
- [ ] Không cho phép IPv6 zone identifier hoặc cú pháp địa chỉ đặc biệt ngoài policy.
- [ ] Có test cho DNS trả nhiều A/AAAA record, record thay đổi và mixed public/private result.

Blocklist IP cần dựa trên thư viện parser và danh sách special-purpose range được duy trì. Không chỉ kiểm tra ba dải RFC1918; loopback, link-local, CGNAT, IPv6 ULA, IPv6 link-local, multicast và metadata endpoint cũng cần được xử lý. Danh sách phải được cập nhật cùng thay đổi hạ tầng.

## 11. Redirect và HTTP client

- [ ] Tắt automatic redirect cho luồng fetch URL không tin cậy, hoặc tự xử lý redirect có giới hạn.
- [ ] Mỗi redirect được parse, canonicalize, resolve DNS và kiểm tra IP/hostname lại từ đầu.
- [ ] Giới hạn số hop redirect và phát hiện loop.
- [ ] Không forward Authorization, Cookie, proxy credential hoặc header nội bộ sang host redirect.
- [ ] Không tự động dùng credential của server khi truy cập URL do caller cung cấp.
- [ ] TLS certificate và hostname verification luôn bật.
- [ ] Timeout connect/read/overall được cấu hình.
- [ ] Giới hạn response bytes, decompressed bytes, header size và thời gian xử lý.
- [ ] Giới hạn content type và chỉ parse định dạng cần thiết.
- [ ] Không cho response redirect hoặc body kích hoạt request tiếp theo ngoài policy.

Một URL public ban đầu có thể redirect tới localhost hoặc metadata IP. Vì vậy, kiểm tra URL đầu vào một lần rồi bật redirect tự động là chưa đủ. HTTP client cần được cấu hình riêng cho outbound fetch không tin cậy; không dùng chung client có cookie store, internal auth interceptor hoặc proxy credential.

## 12. Egress network và metadata protection

Application validation có thể có bug hoặc bị bypass. Network layer cần giới hạn đích mà workload được kết nối:

- [ ] Workload fetch URL chỉ được egress tới DNS/HTTP proxy hoặc destination cần thiết.
- [ ] Network policy/firewall chặn private subnet, loopback, link-local và management network không cần thiết.
- [ ] Chặn cloud metadata endpoint theo IPv4 và IPv6; dùng metadata service protection như hop limit/identity controls phù hợp nền tảng.
- [ ] Không cho API workload truy cập control plane, node management, database admin hoặc secret service nếu không cần.
- [ ] Egress proxy kiểm tra hostname, resolved IP, port và redirect theo cùng policy.
- [ ] DNS resolver không cho caller truy vấn tùy ý tới internal zone qua luồng fetch.
- [ ] Tách network zone của URL fetcher, document renderer và workload chứa credential.
- [ ] Không dựa riêng vào CORS hoặc browser same-origin policy để chống SSRF server-side.

Network egress là defense in depth. Nếu workload cần truy cập một internal service cụ thể, allowlist đúng service/port và xác thực workload identity; không mở toàn bộ private network.

## 13. Giới hạn tác động của URL fetch và parser

- [ ] Có timeout tổng và timeout cho từng giai đoạn DNS/connect/TLS/read.
- [ ] Có giới hạn byte tải về và byte sau giải nén.
- [ ] Giới hạn số redirect, số tài nguyên con và độ sâu parse.
- [ ] Chặn archive bomb, XML external entity và external resource loading không cần thiết.
- [ ] Chạy browser/PDF/image parser trong sandbox/container có quyền tối thiểu.
- [ ] Không mount secret, Docker socket hoặc host filesystem vào worker xử lý URL.
- [ ] Giới hạn CPU, memory, process, file descriptor và concurrency.
- [ ] Xóa temporary file an toàn và không đưa URL/token nhạy cảm vào log.
- [ ] Có quota theo tenant cho fetch, import, preview và render job.

SSRF có thể kết hợp với resource exhaustion. Một URL trỏ tới response vô hạn, file nén cực lớn hoặc trang có hàng nghìn subresource có thể tiêu thụ CPU, memory và bandwidth ngay cả khi destination là public.

## 14. Webhook và callback URL

- [ ] Chỉ role/service phù hợp được tạo hoặc thay đổi destination.
- [ ] Destination được validate và áp dụng cùng DNS/IP/redirect/egress policy.
- [ ] Không cho webhook gọi arbitrary internal host/port.
- [ ] Signing secret được lưu trong secret manager, không trả lại raw secret sau khi tạo.
- [ ] Signature bao phủ raw body và timestamp/nonce theo protocol.
- [ ] Consumer xác minh signature constant-time và chống replay theo timestamp/idempotency.
- [ ] Delivery có timeout, concurrency/rate quota, retry budget và dead-letter policy.
- [ ] Không retry 4xx không phù hợp; xử lý 429/Retry-After có backoff.
- [ ] Secret/header không bị forward sang redirect host khác.
- [ ] Có test DNS rebinding, redirect tới private IP và destination thay đổi sau khi đăng ký.

Nếu business yêu cầu webhook tới customer domain tùy ý, dùng outbound gateway chuyên biệt để enforce policy và audit. Không để mỗi service tự viết một HTTP client với bộ lọc khác nhau.

## 15. Dependency inventory và lockfile

- [ ] Có manifest cho dependency trực tiếp và dependency bắc cầu.
- [ ] Lockfile được commit và build dùng chế độ reproducible/locked khi hệ sinh thái hỗ trợ.
- [ ] Version dependency được pin theo policy; tránh wildcard hoặc version range không kiểm soát trong release.
- [ ] Maven/Gradle/npm/pip/nuget và build plugin được đưa vào inventory.
- [ ] Base image, OS package, compiler, build action và CI tool cũng được quản lý.
- [ ] Xác định package source/registry được phép; hạn chế dependency lấy từ URL hoặc repository tùy ý.
- [ ] Kiểm tra typo-squatting, dependency confusion và namespace ownership.
- [ ] Không để untrusted build step thay đổi dependency source hoặc lockfile mà không review.
- [ ] Xác định owner cho dependency quan trọng và dependency đã bỏ bảo trì.

Chỉ kiểm tra pom.xml/build.gradle hoặc package.json là chưa đủ nếu không xét dependency bắc cầu, plugin, base image và tool được dùng trong pipeline. Lockfile giúp cố định resolution nhưng không chứng minh package an toàn.

## 16. Vulnerability scanning và remediation

- [ ] Quét SCA cho dependency trực tiếp và transitive.
- [ ] Quét container base image và OS packages.
- [ ] Quét IaC, build plugin, CI action và runtime image khi công cụ hỗ trợ.
- [ ] Scan tại pull request, build/release và định kỳ theo lịch.
- [ ] Báo cáo có package/version, ecosystem, advisory/CVE, severity và fixed version.
- [ ] Đánh giá reachability/exploitability và exposure của thành phần bị ảnh hưởng.
- [ ] Ưu tiên lỗ hổng critical/high có exploit đang được sử dụng hoặc component public-facing.
- [ ] Có deadline remediation theo severity và SLA.
- [ ] Exception có owner, lý do, compensating control, expiry và review.
- [ ] Re-scan sau khi nâng version hoặc cập nhật base image.

Không chỉ dựa vào CVSS. Một dependency có CVE nghiêm trọng nhưng không reachable có thể được ưu tiên khác với một lỗ hổng có exploit nằm trên đường request public. Ngược lại, không bỏ qua lỗ hổng chỉ vì scanner đánh giá reachability thấp nếu runtime configuration làm code path có thể truy cập.

## 17. Provenance, integrity và registry

- [ ] Dùng registry/repository tin cậy và TLS verification.
- [ ] Pin artifact theo version/digest khi cần bảo đảm tính bất biến.
- [ ] Verify checksum/signature của artifact theo trust policy.
- [ ] Build trong môi trường cô lập, quyền tối thiểu và không dùng secret production cho untrusted pull request.
- [ ] Tạo SBOM cho release artifact/container image.
- [ ] Lưu build provenance: source revision, builder identity, build parameters và artifact digest.
- [ ] Ký artifact/image và verify chữ ký trước deploy nếu release process yêu cầu.
- [ ] Chỉ cho phép deploy artifact đã qua scan và có provenance hợp lệ.
- [ ] Theo dõi image digest thực tế đang chạy, không chỉ tag mutable.
- [ ] Có quy trình quarantine/revoke artifact khi package hoặc builder bị compromise.

SBOM là inventory có thể dùng để truy vấn ảnh hưởng khi có advisory mới; nó không phải chứng nhận rằng artifact không có lỗ hổng. Provenance và signature giúp xác minh nguồn gốc/toàn vẹn, nhưng không chứng minh source hoặc builder hoàn toàn an toàn.

## 18. Cập nhật dependency và base image

- [ ] Theo dõi security advisory của ecosystem, vendor và base image.
- [ ] Có lịch cập nhật dependency định kỳ và quy trình emergency patch.
- [ ] Ưu tiên version đã được vendor hỗ trợ và còn nhận security fix.
- [ ] Kiểm tra breaking change, migration và compatibility trước rollout.
- [ ] Rebuild image từ base image đã vá; không chỉ sửa tag trong manifest.
- [ ] Không giữ cache layer chứa package cũ khi cần bảo đảm rebuild sạch.
- [ ] Kiểm tra runtime artifact thực tế sau build, không chỉ source manifest.
- [ ] Ghi nhận dependency exception và ngày hết hạn.
- [ ] Có khả năng rollback sang artifact đã biết tốt nhưng vẫn không chứa lỗ hổng đang bị khai thác.

Không tự động nâng mọi dependency production mà không kiểm thử. Nhưng cũng không để quy trình review kéo dài vô hạn khi có exploit đang hoạt động. Cần emergency path có owner, test tối thiểu, rollout theo giai đoạn và xác minh sau deploy.

## 19. Secret dùng bởi dependency và CI/CD

- [ ] Không hardcode token registry, package repository hoặc signing key trong source/build file.
- [ ] Dùng secret manager hoặc workload identity/federation cho CI khi có thể.
- [ ] Credential chỉ có quyền đọc dependency cần thiết; publish/sign permission tách riêng.
- [ ] Token có scope hẹp, lifetime ngắn và rotation/revocation được kiểm thử.
- [ ] Không expose secret cho pipeline chạy code từ fork/untrusted contributor.
- [ ] Không in environment, command line hoặc package manager config có credential vào log.
- [ ] Không lưu credential trong Docker ARG/ENV hoặc image layer.
- [ ] Quét source, build log, artifact và image để phát hiện secret.
- [ ] Dependency update bot không tự động được cấp quyền deploy production.

Package lifecycle script hoặc build plugin có thể thực thi code trong lúc build. Vì vậy, token trong build environment cần được giới hạn tối thiểu và chỉ cấp cho step thực sự cần.

## 20. CI/CD gate trước khi publish

| Gate | Điều kiện tối thiểu | Bằng chứng |
|---|---|---|
| Rate-limit policy | Route nhạy cảm có limit và shared enforcement | Policy version, integration test |
| Quota/cost | Tenant, global, concurrency và job limits đã định nghĩa | Quota config, load test |
| SSRF | URL fetch path có validation, redirect/DNS/IP và egress controls | SSRF test matrix, network policy |
| Dependency SCA | Không còn finding vượt release threshold | Scan report/SBOM |
| Integrity | Lockfile, digest, signature/provenance hợp lệ theo policy | Build attestation |
| Secret scan | Không có secret finding chặn | Redacted scan report |
| Runtime config | Timeout, pool, egress, resource limits và secret injection đúng | Deployment manifest/config review |
| Observability | Metric/log/alert cho deny, 429, SSRF block, CVE và dependency outage | Dashboard/alert test |

Pipeline phải phân biệt passed, failed, partial và not_scanned. Scanner timeout hoặc không đọc được archive/image không được coi là pass. Exception cần approval, scope, compensating control và expiry.

## 21. Quan sát và cảnh báo sau triển khai

**Rate limit và quota**

- [ ] Theo dõi request allow/deny theo route, principal class và reason code.
- [ ] Theo dõi usage/reserved/limit theo tenant và meter.
- [ ] Alert khi một tenant có burst, cost hoặc job backlog bất thường.
- [ ] Theo dõi quota-store latency/error và fallback mode.
- [ ] Theo dõi provider 429, retry count, concurrency và circuit breaker.

**SSRF và outbound**

- [ ] Ghi nhận destination đã canonicalize, policy decision và reason code; tránh log credential/query nhạy cảm.
- [ ] Alert khi request bị chặn vì private/link-local/metadata IP hoặc redirect bất thường.
- [ ] Theo dõi DNS resolution failure, redirect hop và response-size limit.
- [ ] Theo dõi egress tới destination/port ngoài allowlist.
- [ ] Tương quan request ID, tenant, worker/job và outbound connection.

**Dependency và supply chain**

- [ ] Theo dõi finding mới trong dependency/runtime image.
- [ ] Theo dõi artifact chưa có SBOM/provenance hoặc signature verify thất bại.
- [ ] Alert khi registry/builder/CI credential bị sử dụng bất thường.
- [ ] Theo dõi thời gian từ advisory tới patch/deploy.
- [ ] Giám sát scanner failure và coverage giảm.

Không đưa raw API key, token, full signed URL hoặc query string nhạy cảm vào metric label/log. Dùng reference đã pseudonymize và giới hạn quyền truy cập audit.

## 22. Kiểm thử rate limit, quota và autoscaling

- [ ] Test một user gửi burst vượt limit.
- [ ] Test nhiều user trong cùng tenant và nhiều tenant cùng lúc.
- [ ] Test request đi qua nhiều replica; tổng quota không nhân theo pod.
- [ ] Test concurrency và queue backlog khi autoscaling.
- [ ] Test quota backend chậm/mất kết nối và xác minh fail mode.
- [ ] Test retry, duplicate request, idempotency và reservation settlement.
- [ ] Test batch/page size/payload lớn và operation có cost cao.
- [ ] Test provider trả 429/Retry-After và 5xx.
- [ ] Test scale-in/restart không reset usage.
- [ ] Test fairness để một tenant không chiếm hết global capacity.

Load test cần theo dõi latency của limiter, DB pool, queue và provider. Một limiter chính xác nhưng trở thành bottleneck duy nhất có thể làm toàn hệ thống mất khả năng phục vụ.

## 23. Kiểm thử SSRF

Các test phải chạy trong môi trường kiểm soát, dùng endpoint giả lập; không thử truy cập metadata hoặc hệ thống nội bộ production.

| Kịch bản | Kết quả mong đợi |
|---|---|
| Scheme không cho phép như file/ftp/gopher | Từ chối trước khi tạo outbound request |
| URL có userinfo hoặc port ngoài allowlist | Từ chối |
| Hostname trỏ loopback/private/link-local | Từ chối |
| DNS trả đồng thời public và private IP | Từ chối theo policy |
| IPv4-mapped IPv6 hoặc IP encoding khác thường | Canonicalize rồi áp dụng cùng IP policy |
| DNS rebinding giữa validate và connect | Kết nối vẫn bị chặn tại tầng egress/connection |
| Public URL redirect tới private IP | Redirect bị chặn sau khi validate lại |
| Redirect loop hoặc quá nhiều hop | Dừng theo giới hạn |
| Response quá lớn hoặc decompression bomb | Dừng và giới hạn tài nguyên |
| Slow response/slow headers | Timeout giải phóng worker |
| URL fetcher nhận internal auth header | Header không bị forward sang destination không tin cậy |
| Proxy bypass/direct egress | Network policy chặn đường đi ngoài proxy |
| Webhook destination đổi sau khi đăng ký | Mỗi lần delivery vẫn được resolve/validate theo policy |

Kiểm tra cả HTTP client, DNS resolver và network policy thực tế. Unit test cho URL validator không đủ chứng minh kết nối cuối cùng không thể tới IP bị cấm.

## 24. Kiểm thử dependency và supply chain

- [ ] CI phát hiện dependency có CVE theo threshold đã định nghĩa.
- [ ] Transitive dependency, plugin, base image và OS package đều có coverage.
- [ ] Lockfile drift hoặc build không reproducible được phát hiện.
- [ ] Package từ registry không tin cậy/namespace confusion bị chặn theo policy.
- [ ] SBOM khớp artifact digest được phát hành.
- [ ] Signature/provenance verification thất bại thì deploy gate từ chối.
- [ ] Scanner không in raw secret hoặc credential registry ra log.
- [ ] Pipeline từ fork không đọc được secret publish/sign/deploy.
- [ ] Emergency dependency patch được build, scan, test và rollout theo playbook.
- [ ] Artifact đang chạy có thể truy ngược về source revision và builder.

Test scanner bằng fixture/canary an toàn, không đưa credential production hoặc package độc hại thật vào pipeline kiểm thử.

## 25. Rollout, rollback và xử lý sự cố

**Trước rollout**

- [ ] Policy và rule version đã review, có owner.
- [ ] Threshold được thử ở staging với traffic gần thực tế.
- [ ] Có baseline false positive và danh sách exception hết hạn rõ ràng.
- [ ] Có dashboard và alert trước khi bật enforcement rộng.
- [ ] Có phương án rollback cấu hình limiter/egress/dependency nếu gây lỗi ngoài dự kiến.

**Trong rollout**

- [ ] Bật theo canary/tenant cohort/route khi phù hợp.
- [ ] Theo dõi 429, latency, error rate, queue depth và provider throttle.
- [ ] Kiểm tra SSRF block không làm hỏng luồng hợp lệ ngoài allowlist.
- [ ] Xác minh đúng image digest và dependency version đang chạy.
- [ ] Không tắt toàn bộ policy khi có một false positive; điều chỉnh scope hẹp.

**Khi có sự cố**

- [ ] Tăng hạn chế hoặc tắt endpoint/feature bị lạm dụng theo incident playbook.
- [ ] Revoke credential bị lộ hoặc credential registry/provider có dấu hiệu bị chiếm.
- [ ] Chặn egress destination bị khai thác và giữ lại audit evidence.
- [ ] Quarantine artifact/image có dependency compromise.
- [ ] Xác định tenant, user, job, destination và dữ liệu bị ảnh hưởng.
- [ ] Rebuild/redeploy artifact sạch và quét lại.
- [ ] Ghi timeline, root cause, phạm vi, quyết định và follow-up owner.

Rollback không được đưa lại dependency có lỗ hổng đang bị khai thác hoặc mở egress không giới hạn. Nếu cần khôi phục availability, dùng mitigation có scope và thời hạn, sau đó xác minh lại.

## 26. Evidence cần lưu cho mỗi release

Mỗi release nên có một bộ bằng chứng liên kết với commit và artifact digest:

- Endpoint inventory và rate-limit/quota policy version.
- Kết quả integration/load test cho nhiều replica.
- SSRF test matrix, URL policy version và egress/network policy.
- Dependency scan report, SBOM, base image digest và exception đã duyệt.
- Signature/provenance verification result.
- Secret scan status đã redact.
- Runtime config review: timeout, connection pool, resource limits, proxy và secret injection.
- Dashboard/alert links hoặc kết quả alert test.
- Release approver, thời điểm, rollback reference và owner xử lý finding còn mở.

Report phải tránh chứa raw token, password, signed URL hoặc payload nhạy cảm. Lưu bằng chứng ở nơi có access control và retention phù hợp.

## 27. Checklist tổng hợp go-live

**Rate limit và quota**

- [ ] Endpoint đã được phân loại theo cost và mức rủi ro.
- [ ] Rate limit theo principal/tenant/client/route được áp dụng phù hợp.
- [ ] Shared limiter atomic hoạt động trên mọi replica.
- [ ] Usage quota, concurrency, queue và provider cap đã định nghĩa.
- [ ] 429, Retry-After, retry budget và fail mode đã kiểm thử.
- [ ] Autoscaling không làm tăng tổng quota.

**SSRF và outbound**

- [ ] Mọi luồng nhận URL/host đã được inventory.
- [ ] Scheme, hostname, port và URL parser policy rõ ràng.
- [ ] DNS A/AAAA, private/special IP, DNS rebinding và redirect được kiểm soát.
- [ ] HTTP client timeout, response limit và TLS verification được bật.
- [ ] Egress firewall/proxy chặn metadata và internal network không cần thiết.
- [ ] Webhook/fetcher/parser có sandbox, quota và audit.

**Dependency và supply chain**

- [ ] Dependency trực tiếp/transitive, plugin, base image và CI tool có inventory.
- [ ] Lockfile/version pin và registry policy được áp dụng.
- [ ] SCA, image scan, secret scan và remediation gate đã chạy.
- [ ] SBOM, digest, signature và provenance được lưu/xác minh theo policy.
- [ ] Exception có owner, lý do, compensating control và expiry.

**Vận hành**

- [ ] Dashboard, alert và audit đã được xác minh.
- [ ] Test rate limit, SSRF, dependency và failure mode đã pass.
- [ ] Có rollout canary, rollback và incident playbook.
- [ ] Bằng chứng release gắn với commit và artifact digest.

## Kết luận

Rate limit và quota phải theo identity/tài nguyên đã xác minh, dùng enforcement dùng chung và giữ nguyên giới hạn khi autoscaling. SSRF cần kiểm soát cả URL parser, DNS, IP thực tế, redirect, HTTP client và network egress; chỉ kiểm tra hostname đầu vào là chưa đủ. Dependency security cần inventory cả transitive package, plugin, base image và CI tool, đồng thời kết hợp vulnerability scan, lockfile, SBOM, provenance và remediation có owner. Trước go-live, hãy yêu cầu bằng chứng test nhiều replica, SSRF negative cases, dependency gates, observability và rollback. Checklist chỉ được coi là hoàn tất khi policy thực sự hoạt động trong runtime và có thể kiểm chứng sau release.
