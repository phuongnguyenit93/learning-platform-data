# Dependency update

Dependency update là quy trình cập nhật thư viện, framework, công cụ build và thành phần bên thứ ba mà ứng dụng web đang sử dụng. Với ứng dụng chạy trong trình duyệt, một dependency có thể được đóng gói trực tiếp vào JavaScript/CSS, tải từ CDN, chạy trong worker hoặc tham gia quá trình build và kiểm thử. Mỗi thay đổi phiên bản đều có thể ảnh hưởng tới bảo mật, khả năng tương thích trình duyệt, hiệu năng và hành vi của ứng dụng.

Trong module bảo mật ứng dụng web, dependency update cần được xem là một hoạt động vận hành có kiểm soát. Thư viện mới có thể sửa lỗ hổng XSS hoặc lỗi phân tích URL, nhưng cũng có thể thay đổi cách xử lý HTML, cookie, request, CSP, Trusted Types hoặc source map. Cập nhật an toàn cần biết thành phần nào đang được dùng, vì sao cần cập nhật, phiên bản nào được chọn, cách kiểm chứng và cách khôi phục khi phát hành gặp sự cố.

Bài học này tập trung vào dependency của ứng dụng web và công cụ phát triển frontend. Các lệnh minh họa dùng npm; nếu dự án dùng pnpm, Yarn hoặc hệ thống quản lý package khác, hãy áp dụng lệnh tương ứng và giữ nguyên nguyên tắc kiểm soát lockfile.

## Mục tiêu

Sau bài học, bạn có thể:

- Lập danh mục dependency trực tiếp, gián tiếp và dependency được tải lúc chạy.
- Đánh giá bản cập nhật theo mức độ rủi ro, khả năng khai thác và tác động tới ứng dụng.
- Cập nhật package cùng lockfile một cách có thể tái lập và kiểm tra được.
- Phát hiện rủi ro chuỗi cung ứng như package giả mạo, dependency bị chiếm quyền hoặc install script bất thường.
- Kiểm tra tương thích với CSP, Trusted Types, service worker và các browser engine.
- Phát hành theo từng giai đoạn, theo dõi lỗi và khôi phục phiên bản khi cần.

## Dependency trong ứng dụng web

Dependency là thành phần mà mã nguồn hoặc quy trình phát triển dựa vào. Không phải dependency nào cũng được đưa vào trình duyệt, nhưng một package ở giai đoạn build vẫn có thể ảnh hưởng tới mã được phát hành.

| Nhóm | Ví dụ | Rủi ro cần quan tâm |
|---|---|---|
| Runtime dependency | Framework giao diện, router, thư viện xử lý ngày giờ | Lỗ hổng trong mã được chạy trên trình duyệt, thay đổi hành vi và API |
| Transitive dependency | Package mà một package khác phụ thuộc | Lỗ hổng gián tiếp, khó nhận biết từ `package.json` |
| Development dependency | Bundler, compiler, test runner, lint tool | Mã build bị can thiệp, artifact đầu ra không đáng tin cậy |
| Build plugin | Plugin minify, CSS processor, loader | Thay đổi bundle, source map, CSS hoặc xử lý asset |
| Third-party script | Analytics, chat widget, SDK thanh toán tải từ CDN | Mã bên thứ ba chạy trong trang và có thể truy cập quyền của origin |
| Browser/runtime dependency | API trình duyệt, polyfill, worker script | Khác biệt giữa browser engine, phiên bản và môi trường triển khai |

Dependency trực tiếp thường được khai báo trong manifest như `package.json`. Dependency gián tiếp được giải quyết từ các package khác. Lockfile ghi lại cây phiên bản cụ thể và thông tin integrity để các lần cài đặt có thể tái lập.

Một thư viện chỉ dùng trong build vẫn quan trọng. Nếu bundler hoặc plugin bị xâm phạm, nó có thể chèn mã vào bundle cuối cùng dù package đó không xuất hiện trong `dependencies`. Vì vậy, danh mục cần bao gồm cả `dependencies`, `devDependencies`, optional dependencies, package được tải động và script bên ngoài.

## Lập danh mục và xác định phạm vi ảnh hưởng

Trước khi cập nhật, xác định package nào thực sự có mặt trong ứng dụng, package nào chỉ phục vụ phát triển và package nào đến từ bên thứ ba lúc chạy.

Với npm, có thể bắt đầu bằng các lệnh:

```bash
npm ls --depth=0
npm ls --all
npm outdated
npm explain <package-name>
```

- `npm ls --depth=0` liệt kê dependency trực tiếp đã cài.
- `npm ls --all` hiển thị cây dependency sâu hơn.
- `npm outdated` cho biết package có phiên bản mới hơn trong phạm vi registry và cấu hình hiện tại.
- `npm explain` giúp tìm lý do một package xuất hiện trong cây dependency.

Lệnh có thể trả trạng thái khác 0 khi cây dependency có vấn đề hoặc package thiếu; đọc phần output để phân biệt cảnh báo với lỗi cài đặt. Không coi danh sách package trực tiếp là toàn bộ bề mặt phụ thuộc.

Với ứng dụng lớn, tạo Software Bill of Materials (SBOM) bằng định dạng được tổ chức hỗ trợ, chẳng hạn CycloneDX hoặc SPDX. SBOM cần được tạo từ artifact hoặc lockfile của đúng bản build đang phát hành. Lưu lại phiên bản công cụ và thời điểm tạo để có thể đối chiếu khi có advisory mới.

Danh mục nên ghi nhận tối thiểu:

- Tên package, phiên bản đang dùng và nguồn registry/CDN.
- Dependency trực tiếp hay gián tiếp; package cha nào kéo nó vào.
- Mục đích sử dụng và thành phần sản phẩm bị ảnh hưởng.
- Có chạy trong trình duyệt, server, build, test hay CI hay không.
- Người hoặc nhóm chịu trách nhiệm cập nhật.
- License, trạng thái bảo trì và nguồn thông báo bảo mật nếu có.

Với script tải trực tiếp từ CDN, ghi cả URL đầy đủ, phiên bản, nhà cung cấp, cách xác minh integrity, CSP allowlist và chức năng mà script được cấp quyền thực hiện. Một URL dạng `latest` hoặc không ghim phiên bản khiến nội dung có thể thay đổi mà không có thay đổi trong repository.

## Theo dõi bản cập nhật và advisory bảo mật

Nguồn thông tin cập nhật thường gồm:

- Security advisory của nhà phát hành package và registry.
- Cơ sở dữ liệu lỗ hổng như GitHub Advisory Database hoặc OSV.
- Release notes, changelog và hướng dẫn migration chính thức.
- Cảnh báo từ công cụ quét dependency trong CI hoặc nền tảng quản lý mã nguồn.
- Thông báo từ nhà cung cấp CDN, SDK và dịch vụ bên thứ ba.

Không đánh giá chỉ bằng số phiên bản hoặc một điểm CVSS. Cần xác định phiên bản bị ảnh hưởng, điều kiện khai thác, package có thực sự được sử dụng ở đường chạy liên quan hay không, có cấu hình làm lộ bề mặt tấn công không và có bản vá hoặc biện pháp giảm thiểu nào.

### Phân loại mức độ ưu tiên

| Mức ưu tiên | Dấu hiệu | Hành động vận hành |
|---|---|---|
| Khẩn cấp | Lỗ hổng đang bị khai thác, ảnh hưởng trực tiếp tới mã production hoặc dữ liệu nhạy cảm | Đánh giá ngay, cô lập nếu cần và triển khai bản vá theo quy trình ứng phó sự cố |
| Cao | Lỗ hổng nghiêm trọng, package nằm trên đường xử lý dữ liệu không tin cậy hoặc quyền nhạy cảm | Lập bản cập nhật ưu tiên, kiểm thử tập trung và phát hành sớm |
| Trung bình | Có điều kiện khai thác hạn chế hoặc ảnh hưởng tới môi trường ít nhạy cảm | Đưa vào chu kỳ cập nhật gần nhất, ghi nhận lý do và biện pháp giảm thiểu |
| Thấp | Cập nhật bảo trì, sửa lỗi nhỏ hoặc cải thiện tương thích | Gom theo đợt cập nhật định kỳ và kiểm tra hồi quy phù hợp |

Đây là cách phân loại vận hành; tổ chức cần áp dụng chính sách SLA và tiêu chí rủi ro của mình. Một lỗ hổng trong thư viện parse HTML, URL hoặc xử lý Markdown có thể có mức ưu tiên cao nếu dữ liệu đầu vào đến từ người dùng. Một package chỉ dùng trong test có thể có mức ảnh hưởng production khác, nhưng vẫn cần xem xét nguy cơ xâm phạm pipeline build.

### Xác định dependency có thực sự bị ảnh hưởng

Khi nhận advisory, kiểm tra:

1. Dải phiên bản bị ảnh hưởng và phiên bản đã được sửa.
2. Package xuất hiện trực tiếp hay qua dependency nào.
3. Mã dễ bị ảnh hưởng có nằm trong bundle hoặc đường chạy đang dùng không.
4. Cấu hình, API hoặc input nào kích hoạt lỗi.
5. Có bản vá tương thích hay cần nâng cấp major.
6. Có biện pháp giảm thiểu tạm thời được nhà phát hành khuyến nghị không.

Không tự kết luận “không bị ảnh hưởng” chỉ vì package nằm trong `devDependencies`. Package build có thể thực thi trong CI với quyền truy cập repository, registry hoặc artifact. Cũng không bỏ qua package gián tiếp: một dependency lồng sâu vẫn có thể được bundle vào JavaScript production.

## Chọn chiến lược cập nhật

### Patch, minor và major

Theo Semantic Versioning, phiên bản thường có dạng `MAJOR.MINOR.PATCH`:

- Patch thường sửa lỗi tương thích trong cùng minor line.
- Minor thường bổ sung tính năng tương thích ngược theo cam kết của package.
- Major có thể chứa breaking changes và yêu cầu migration.

SemVer là cam kết của nhà phát hành, không phải bằng chứng rằng thay đổi không gây rủi ro. Một patch có thể thay đổi hành vi bảo mật, một minor có thể thay đổi bundle hoặc API trình duyệt, và một major có thể loại bỏ cơ chế cũ vốn không an toàn.

Ưu tiên bản vá bảo mật được nhà phát hành hỗ trợ. Nếu phải nâng major, đọc migration guide, xác định API đã bị loại bỏ, kiểm tra cấu hình mới và chia thay đổi thành các bước có thể review. Tránh nâng đồng loạt nhiều framework lớn trong một lần nếu không thể xác định nguyên nhân khi hồi quy.

### Cập nhật một package có chủ đích

Ví dụ với npm:

```bash
npm outdated
npm install <package-name>@<target-version>
npm ls <package-name>
npm audit
```

Lệnh `npm install` cập nhật manifest và lockfile theo cách npm giải quyết dependency. Nếu dự án yêu cầu phiên bản chính xác, dùng quy ước pin phiên bản của dự án, chẳng hạn `--save-exact`. Không tự thay đổi chính sách version range trong một PR nếu không có lý do rõ ràng.

`npm update` thường cập nhật trong phạm vi version range hiện có. Tùy chọn `--latest` hoặc thay đổi version range có thể đưa package sang phiên bản major mới; cần kiểm tra tài liệu của package manager và diff trước khi chấp nhận.

### Không dùng cập nhật tự động như quyết định cuối cùng

`npm audit fix` có thể sửa một số advisory bằng cách thay đổi cây dependency và lockfile; nó không thay thế việc đọc advisory hoặc review diff. Với thay đổi có breaking change, công cụ có thể không tự giải quyết hoặc có thể yêu cầu nâng cấp ngoài phạm vi hiện tại. Không chạy lệnh nâng cấp cưỡng bức trên toàn bộ cây dependency trong production branch mà không kiểm tra kết quả.

Một PR cập nhật nên giới hạn phạm vi, nêu package bị thay đổi, lý do, advisory liên quan, phiên bản đích và kết quả kiểm thử. Nếu một bản cập nhật kéo theo nhiều dependency khác, xem xét từng thay đổi trong lockfile để xác định có hợp lý không.

## Lockfile và cài đặt có thể tái lập

Lockfile là một phần của nguồn kiểm soát phiên bản. Với npm, file thường là `package-lock.json`; pnpm dùng `pnpm-lock.yaml`; Yarn dùng `yarn.lock`. Lockfile ghi phiên bản đã giải quyết và metadata cần để tái tạo cây dependency.

Quy trình an toàn cần:

- Commit manifest và lockfile cùng nhau khi dependency thay đổi.
- Không xóa lockfile chỉ để “sửa” lỗi cài đặt hoặc làm diff biến mất.
- Không chỉnh tay hàng loạt phiên bản trong lockfile nếu package manager có thể tạo lại đúng cách.
- Cài đặt từ lockfile trong CI, ví dụ `npm ci` với npm.
- Review các thay đổi về phiên bản, URL registry, integrity hash và dependency mới.
- Dùng phiên bản Node.js và package manager được dự án hỗ trợ, có thể ghim qua công cụ quản lý runtime hoặc cấu hình CI.

`npm ci` yêu cầu lockfile đồng bộ với manifest và cài cây dependency theo lockfile; nó xóa thư mục `node_modules` hiện có trước khi cài. Nếu lệnh thất bại vì manifest và lockfile không đồng bộ, hãy cập nhật lockfile bằng package manager trong nhánh làm việc rồi review diff.

Không chấp nhận thay đổi integrity hash hoặc registry URL bất thường mà không xác minh nguồn package. Hash integrity giúp phát hiện nội dung tarball không khớp metadata đã khóa, nhưng không chứng minh package ban đầu là lành tính. Nếu package độc hại được phát hành hợp lệ, hash của nó vẫn có thể đúng.

## Bảo vệ chuỗi cung ứng phần mềm

Dependency update cũng là cơ hội rà soát nguy cơ chuỗi cung ứng. Package có thể bị chiếm tài khoản maintainer, bị publish nhầm, bị thay thế bằng package tên gần giống hoặc chứa install script thực thi lệnh trong lúc cài.

### Xác minh danh tính và nguồn package

Trước khi thêm package mới:

- Xác minh tên package chính xác từ tài liệu chính thức của dự án.
- Kiểm tra publisher, repository, lịch sử phát hành, maintainer và kênh thông báo bảo mật.
- Cẩn trọng với package có tên gần giống thư viện phổ biến hoặc package mới tạo nhưng được kéo vào bởi một hướng dẫn không đáng tin.
- Dùng registry được tổ chức phê duyệt và cấu hình scope rõ ràng.
- Kiểm tra package có script `preinstall`, `install`, `postinstall` hoặc script lifecycle khác không.
- Xác minh provenance/attestation hoặc chữ ký nếu registry và nhà phát hành hỗ trợ.

Không coi số lượt tải, nhãn verified hoặc một repository công khai là bằng chứng độc lập về an toàn. Cần xem nguồn phát hành, quyền mà package cần và khả năng tái tạo build.

### Kiểm tra install scripts

Install script có thể chạy mã trong môi trường cài đặt, thường với quyền của tiến trình CI hoặc máy phát triển. Khi dependency mới có lifecycle script, xác định script làm gì, tải thêm binary hay kết nối ra ngoài không và có thực sự cần thiết không.

Không vô hiệu hóa tất cả install scripts một cách mù quáng vì một số package cần biên dịch native module hoặc chuẩn bị binary. Thay vào đó, giới hạn quyền của CI, dùng secret tối thiểu, tách job build không cần quyền phát hành và review các script mới hoặc thay đổi bất thường.

### Kiểm soát registry và cấu hình

File cấu hình như `.npmrc` có thể chỉ định registry, proxy, scope và hành vi cài đặt. Không commit token registry hoặc credential vào repository. Dùng secret manager của CI và token có quyền đọc tối thiểu. Kiểm tra cấu hình registry để tránh package nội bộ bị resolve từ registry công khai ngoài ý muốn.

Đối với package CDN, ghim phiên bản cụ thể và dùng Subresource Integrity (SRI) khi tài nguyên phù hợp với cơ chế này:

```html
<script
  src="https://cdn.example.test/library/4.2.1/library.min.js"
  integrity="sha384-BASE64_HASH_FROM_TRUSTED_RELEASE"
  crossorigin="anonymous"></script>
```

Giá trị integrity trong ví dụ là placeholder, không thể dùng trực tiếp. Lấy hash từ quy trình phát hành đáng tin cậy hoặc tự tính từ đúng artifact đã xác minh. Khi nội dung thay đổi, hash phải được cập nhật tương ứng. SRI kiểm tra nội dung tải về có khớp hash đã khai báo; nó không xác minh logic của thư viện hoặc độ an toàn của nhà cung cấp.

Không tải script từ URL `latest`, branch mutable hoặc endpoint không ghim phiên bản nếu cần kiểm soát chính xác nội dung production. Giữ CSP allowlist đủ hẹp và review mọi host mới được thêm vào `script-src`, `connect-src`, `worker-src` hoặc directive liên quan.

## Kiểm tra tác động tới bảo mật trình duyệt

Một dependency frontend có thể thay đổi cách ứng dụng tương tác với DOM, URL, cookie, storage và chính sách trình duyệt. Sau khi cập nhật, chạy các kiểm thử tập trung theo chức năng package.

### XSS, DOM sink và Trusted Types

Nếu cập nhật framework, template engine, Markdown renderer hoặc thư viện sanitize HTML, kiểm tra lại:

- Mọi dữ liệu không tin cậy vẫn được escape theo đúng ngữ cảnh.
- Các API chèn HTML thô không được thêm mới ngoài thiết kế.
- Sanitizer vẫn dùng allowlist phù hợp và không làm mất bảo vệ với URL scheme nguy hiểm.
- Trusted Types policy vẫn hoạt động và không xuất hiện policy mặc định quá rộng.
- CSP không phải nới lỏng bằng `unsafe-inline` hoặc `unsafe-eval` chỉ để tương thích với package mới mà chưa đánh giá.
- Bundle không đưa thêm script từ host bên ngoài ngoài dự kiến.

Đối với thay đổi ở sanitizer, kiểm thử payload đại diện cho HTML, SVG, URL và thuộc tính sự kiện trong môi trường an toàn. Xác nhận output được render theo mong đợi và không thực thi script. Một bộ test unit của package không thay thế kiểm thử tích hợp trên DOM thật.

### Cookie, request và CORS

Nếu package thay đổi HTTP client, router, authentication SDK hoặc thư viện form, kiểm tra:

- `credentials`/cookie có được gửi đúng origin và endpoint không.
- Redirect không chuyển token hoặc header nhạy cảm sang host khác.
- CORS preflight và custom header vẫn theo allowlist.
- CSRF token vẫn được gửi và xác minh trên các thao tác thay đổi trạng thái.
- Retry không lặp thao tác có tác dụng phụ ngoài dự kiến.
- URL được parse và chuẩn hóa an toàn; không phát sinh open redirect hoặc lỗi kiểm tra origin.

Không giả định nâng cấp HTTP client chỉ ảnh hưởng cú pháp API. Thay đổi mặc định về redirect, cookie, timeout hoặc retry có thể làm thay đổi ranh giới bảo mật.

### CSP và security headers

Thay đổi bundler hoặc framework có thể đổi tên file, cách tạo inline script/style, dynamic import, worker hoặc preload. Kiểm tra CSP report và response header trên các route quan trọng. Nếu build mới tạo inline script, hãy đánh giá nonce/hash theo kiến trúc hiện tại; không tự động thêm `'unsafe-inline'` để làm hết lỗi Console.

Kiểm tra các header liên quan như `Content-Security-Policy`, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`, `Cross-Origin-Opener-Policy`, `Cross-Origin-Embedder-Policy` và `Cross-Origin-Resource-Policy` khi chúng thuộc cấu hình ứng dụng. Đảm bảo pipeline deploy không vô tình bỏ header hoặc chỉ áp dụng header cho một số route.

### Service worker và cache

Dependency update có thể thay đổi tên bundle, manifest hoặc chiến lược cache. Service worker cũ có thể tiếp tục phục vụ HTML/JavaScript cũ trong khi server đã triển khai asset mới, dẫn tới lỗi phiên bản hoặc chạy mã không còn phù hợp.

Kiểm tra:

- Cache key và version của precache manifest được cập nhật đúng.
- Service worker mới được cài và kích hoạt theo vòng đời mong muốn.
- Asset cũ không bị xóa trước khi client đang mở còn cần chúng.
- Luồng update/reload không làm mất dữ liệu biểu mẫu hoặc trạng thái nghiệp vụ.
- Rollback có thể phục hồi cả bundle và asset tương ứng, không chỉ manifest.

Không xóa cache người dùng hàng loạt như một cách khắc phục mặc định. Nếu cần buộc cập nhật service worker, thiết kế thông báo và thời điểm reload phù hợp để tránh gián đoạn thao tác đang diễn ra.

### Tương thích browser và accessibility

Kiểm tra các browser engine mà sản phẩm hỗ trợ, không chỉ một phiên bản Chrome trên máy phát triển. Cập nhật có thể thay đổi polyfill, event handling, focus behavior, clipboard, file upload, Web Worker hoặc API mới.

Chạy smoke test trên các trình duyệt mục tiêu, kích thước màn hình cần hỗ trợ và chế độ hỗ trợ tiếp cận phù hợp. Kiểm tra keyboard navigation, focus sau khi đóng dialog, thông báo lỗi cho screen reader và trạng thái loading. Một dependency cập nhật có thể không gây lỗi JavaScript nhưng vẫn làm trải nghiệm hoặc khả năng truy cập suy giảm.

## Quy trình cập nhật trong repository

Một quy trình thực tế có thể chia thành các bước sau:

1. **Tạo nhánh cập nhật:** ghi rõ package, phiên bản hiện tại, phiên bản đích và lý do.
2. **Đọc advisory/changelog:** xác định lỗ hổng được sửa, breaking change và migration cần thiết.
3. **Cập nhật có phạm vi:** thay đổi package cần thiết và lockfile bằng package manager của dự án.
4. **Review diff:** kiểm tra manifest, lockfile, registry, integrity, package mới và install script.
5. **Cài đặt sạch:** chạy lệnh cài đặt từ lockfile trong môi trường được kiểm soát.
6. **Kiểm thử:** lint, type check, unit, integration, browser security test và build production.
7. **Tạo artifact:** lưu SBOM hoặc metadata build nếu quy trình yêu cầu.
8. **Review và phát hành:** mô tả rủi ro còn lại, phê duyệt theo chính sách và triển khai theo giai đoạn.
9. **Theo dõi:** quan sát lỗi runtime, CSP report, crash, hiệu năng và cảnh báo bảo mật.
10. **Đóng cập nhật:** ghi phiên bản đã phát hành, bằng chứng kiểm thử và kế hoạch xử lý nếu có phát hiện mới.

Ví dụ chuỗi lệnh kiểm tra trong dự án npm:

```bash
# Xác nhận phiên bản runtime và package manager
node --version
npm --version

# Xem trạng thái dependency trước khi cập nhật
npm ls --depth=0
npm outdated
npm audit

# Cập nhật package đã chọn; thay placeholder bằng package và phiên bản đã review
npm install <package-name>@<target-version>

# Cài sạch theo lockfile và chạy kiểm tra của dự án
npm ci
npm run lint
npm test
npm run build

# Kiểm tra lại cây dependency sau cập nhật
npm ls --all
npm audit
```

Các script `lint`, `test` và `build` là ví dụ; dùng tên script thật của repository. Chạy `npm ci` sau khi đã tạo lockfile mới để kiểm tra khả năng cài đặt tái lập. Không chạy lệnh cập nhật trực tiếp trên môi trường production.

## Tích hợp kiểm tra dependency vào CI/CD

CI nên kiểm tra dependency trên mỗi pull request và theo lịch định kỳ. Một pipeline tối thiểu có thể gồm:

- Cài đặt từ lockfile bằng phiên bản runtime/package manager đã ghim.
- Quét advisory cho dependency trực tiếp và gián tiếp.
- Kiểm tra license hoặc policy package theo quy định tổ chức.
- Phát hiện manifest thay đổi nhưng lockfile chưa cập nhật.
- Chạy lint, unit, integration, browser test và build.
- Tạo SBOM hoặc artifact provenance nếu pipeline hỗ trợ.
- Lưu kết quả scan cùng commit/build identifier để truy vết.

Không nên để một cảnh báo không liên quan chặn vô thời hạn mọi bản vá khẩn cấp. Cần có quy trình ngoại lệ có thời hạn, người phê duyệt, lý do, biện pháp giảm thiểu và ngày xem xét lại. Ngoại lệ không được âm thầm trở thành trạng thái vĩnh viễn.

### Tự động hóa Dependabot

Với repository GitHub, Dependabot có thể mở pull request cập nhật dependency theo lịch. Ví dụ cấu hình tối thiểu:

```yaml
version: 2
updates:
  - package-ecosystem: "npm"
    directory: "/"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 5
    labels:
      - "dependencies"
```

Đặt file cấu hình tại `.github/dependabot.yml` trong repository nếu tổ chức sử dụng GitHub Dependabot. Chọn lịch và giới hạn PR phù hợp với khả năng review. Cấu hình này chỉ tạo đề xuất cập nhật; vẫn cần kiểm tra diff, kiểm thử và phê duyệt trước khi merge.

Nếu dùng Renovate hoặc công cụ khác, áp dụng nguyên tắc tương tự: nhóm cập nhật theo mức độ rủi ro, tránh gom quá nhiều major change vào một PR và ưu tiên security update theo SLA.

## Phát hành, theo dõi và rollback

Dependency update có thể ảnh hưởng tới người dùng sau khi bundle mới được tải. Nếu có thể, phát hành theo canary hoặc một phần lưu lượng trước khi mở rộng. Theo dõi:

- Tỷ lệ lỗi JavaScript và lỗi tải chunk.
- Lỗi CSP, Trusted Types, CORS và service worker.
- Lỗi xác thực, request bị từ chối bất thường hoặc retry tăng cao.
- Core Web Vitals, thời gian tải và kích thước bundle.
- Crash hoặc lỗi riêng theo browser engine.
- Cảnh báo mới từ scanner hoặc nhà phát hành dependency.

Rollback cần khôi phục một tập artifact tương thích: bundle, manifest, asset, service worker và cấu hình liên quan. Nếu bản cập nhật có thay đổi schema dữ liệu hoặc định dạng cache, rollback code đơn thuần có thể không đủ. Lập kế hoạch tương thích ngược trước khi triển khai các thay đổi như vậy.

Khi rollback, ghi lại phiên bản bị lỗi, dấu hiệu kích hoạt, phạm vi người dùng bị ảnh hưởng và lý do. Không giữ lại một dependency đã biết có lỗ hổng nghiêm trọng chỉ vì rollback tiện hơn; nếu cần quay lại tạm thời, phải có biện pháp giảm thiểu, giới hạn thời gian và kế hoạch bản vá tiếp theo.

## Xử lý khi phát hiện dependency bị xâm phạm

Nếu phát hiện package đã phát hành bị chiếm quyền hoặc có mã độc:

1. Xác định phiên bản và khoảng thời gian package có mặt trong build hoặc CI.
2. Dừng sử dụng phiên bản bị ảnh hưởng và ngăn pipeline tiếp tục cài đặt nó.
3. Kiểm tra artifact, log cài đặt, build runner, registry token và secret có thể đã bị truy cập.
4. Xác định bundle production nào chứa mã bị ảnh hưởng và phạm vi người dùng đã tải bundle.
5. Thực hiện quy trình ứng phó sự cố của tổ chức; thu hồi hoặc xoay vòng credential nếu có bằng chứng hoặc nguy cơ lộ.
6. Thay bằng phiên bản sạch đã xác minh hoặc gỡ dependency nếu có thể.
7. Build lại trong môi trường sạch, kiểm thử và phát hành artifact mới.
8. Ghi nhận timeline, tác động, quyết định và hành động phòng ngừa.

Chỉ cập nhật version number chưa đủ nếu package registry, maintainer account hoặc pipeline build vẫn bị xâm phạm. Cần xác minh nguồn phát hành và môi trường build trước khi tin artifact mới.

## Lỗi thường gặp khi cập nhật dependency

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| CI cài package khác máy phát triển | Lockfile thiếu hoặc không đồng bộ; khác phiên bản package manager | Dùng lệnh cài sạch từ lockfile và ghim toolchain |
| Bundle phát sinh lỗi CSP | Package thêm inline script, worker hoặc host mới | Xác định directive bị vi phạm, đánh giá nonce/hash hoặc cấu hình resource; không nới lỏng CSP tùy tiện |
| Trusted Types báo lỗi | Dependency mới dùng DOM sink hoặc policy chưa được hỗ trợ | Xác định sink, cập nhật tích hợp an toàn và giữ policy hẹp |
| Một số người dùng vẫn chạy bundle cũ | Service worker hoặc cache CDN giữ asset cũ | Kiểm tra cache version, manifest, thời gian sống asset và quy trình cập nhật client |
| `npm audit` vẫn báo lỗ hổng | Advisory ở dependency gián tiếp hoặc chưa có bản vá | Dùng `npm explain`, kiểm tra dải ảnh hưởng và phương án giảm thiểu; ghi nhận ngoại lệ có thời hạn nếu cần |
| Cập nhật gây lỗi browser cũ | Package bỏ polyfill hoặc dùng API mới | Kiểm tra browser support, cấu hình transpile/polyfill và test trên engine mục tiêu |
| Diff lockfile thay đổi quá lớn | Runtime/package manager khác hoặc giải quyết lại toàn bộ cây | Dùng đúng toolchain, giới hạn phạm vi và review package tăng/giảm |
| Package tải từ nguồn lạ | Registry hoặc scope cấu hình sai | Kiểm tra `.npmrc`, registry, package identity và credential |

## Checklist cho một pull request dependency update

- [ ] Nêu package, phiên bản hiện tại, phiên bản đích và lý do cập nhật.
- [ ] Đọc advisory, changelog và migration guide liên quan.
- [ ] Xác định package trực tiếp/gián tiếp và thành phần sản phẩm bị ảnh hưởng.
- [ ] Manifest và lockfile được cập nhật cùng nhau bằng package manager phù hợp.
- [ ] Kiểm tra registry URL, integrity hash, package mới và lifecycle script.
- [ ] Cài đặt sạch từ lockfile thành công.
- [ ] Quét dependency và ghi nhận cảnh báo còn lại cùng lý do.
- [ ] Chạy lint, test, build và browser security regression test phù hợp.
- [ ] Kiểm tra CSP, Trusted Types, CORS, cookie, service worker và bundle khi liên quan.
- [ ] Có kế hoạch phát hành, theo dõi và rollback.
- [ ] Không có secret, token hoặc dữ liệu nhạy cảm trong diff và log CI.

## Thực hành

Trong một ứng dụng frontend thử nghiệm, chọn một dependency trực tiếp và một dependency gián tiếp. Dùng package manager của dự án để xác định package cha, phiên bản hiện tại và phiên bản có thể cập nhật.

Thực hiện các bước:

1. Lưu lại kết quả `npm ls --all`, `npm outdated` và `npm audit` trước cập nhật.
2. Đọc changelog/advisory của package được chọn và xác định lý do cần nâng cấp.
3. Tạo nhánh riêng, cập nhật một package cùng lockfile và review toàn bộ diff.
4. Cài sạch bằng `npm ci`, chạy kiểm tra và build production.
5. Kiểm tra bundle, CSP/Trusted Types và các luồng browser có sử dụng package đó.
6. Tạo bản build thử nghiệm, theo dõi lỗi và diễn tập rollback về artifact trước đó.
7. Ghi lại kết quả, cảnh báo còn lại và quyết định chấp nhận hoặc hoãn cập nhật.

Nếu không có advisory hoặc phiên bản mới trong package được chọn, hãy dùng một package thử nghiệm riêng và không tạo thay đổi giả trong dependency production. Không dùng token, dữ liệu người dùng hoặc package không rõ nguồn trong bài thực hành.

## Ghi nhớ

- Dependency gồm package runtime, package gián tiếp, công cụ build và script bên thứ ba tải lúc chạy.
- Lockfile, toolchain và registry được kiểm soát giúp tái lập bản build.
- Ưu tiên theo khả năng khai thác và tác động thực tế; không chỉ dựa vào số phiên bản hoặc điểm CVSS.
- Review package identity, integrity, provenance và install script để giảm rủi ro chuỗi cung ứng.
- Kiểm tra hồi quy XSS, CSP, Trusted Types, CORS, cookie, service worker và tương thích browser khi dependency có liên quan.
- Phát hành theo giai đoạn, theo dõi lỗi và chuẩn bị rollback cho cả bundle lẫn asset/cache.
- Ghi nhận ngoại lệ bảo mật có người chịu trách nhiệm, biện pháp giảm thiểu và thời hạn xem xét.
