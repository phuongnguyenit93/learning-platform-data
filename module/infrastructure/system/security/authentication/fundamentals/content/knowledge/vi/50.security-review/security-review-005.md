# Dependency review: rà soát phụ thuộc trong hệ thống xác thực

Dependency review là hoạt động kiểm kê, đánh giá và quản lý rủi ro của các thành phần phần mềm mà một hệ thống phụ thuộc vào. Những thành phần này có thể là thư viện trực tiếp, thư viện bắc cầu, framework, plugin build, SDK của nhà cung cấp danh tính, gói JavaScript ở giao diện đăng nhập, image container hoặc thành phần hệ điều hành.

Trong hệ thống xác thực, một dependency nhỏ cũng có thể nằm trên đường đi của credential hoặc quyết định một token có được chấp nhận hay không. Lỗ hổng trong thư viện phân tích JWT, thư viện mật mã, HTTP client, parser chứng chỉ, SDK OIDC hoặc middleware session có thể làm suy yếu toàn bộ ranh giới tin cậy. Một gói độc hại trong quá trình build cũng có thể đọc secret của CI, chèn mã vào artifact hoặc đánh cắp credential khi ứng dụng khởi động.

Vì vậy, rà soát dependency phải trả lời được bốn câu hỏi:

1. Hệ thống thực sự sử dụng những thành phần nào, ở đâu và theo phiên bản nào?
2. Thành phần nào có rủi ro bảo mật, nguồn gốc hoặc khả năng bảo trì đáng lo ngại?
3. Rủi ro đó có thể tác động đến luồng xác thực, dữ liệu, token hoặc quyền nào?
4. Cần cập nhật, thay thế, cô lập hay chấp nhận rủi ro có thời hạn bằng bằng chứng gì?

Bài học đặt dependency review trong bối cảnh module SECURITY_AUTHENTICATION_FUNDAMENTALS: đánh giá các thành phần tham gia xử lý credential, mật khẩu, MFA, passkey, chứng chỉ, token, phiên và liên kết danh tính. Đây là một hoạt động của security review và quản lý chuỗi cung ứng phần mềm; nó bổ sung cho kiểm thử bảo mật và rà soát cấu hình, không thay thế các hoạt động đó.

## Mục tiêu học tập

Sau bài học, người học có thể:

- Phân biệt dependency trực tiếp, bắc cầu, runtime, build-time và thành phần được đóng gói cùng ứng dụng.
- Lập danh mục dependency và xác định dependency nào nằm trên đường đi của xác thực.
- Đọc dependency tree, lock file, SBOM và kết quả Software Composition Analysis (SCA).
- Đánh giá cảnh báo CVE theo phiên bản bị ảnh hưởng, khả năng tiếp cận mã lỗi, điều kiện khai thác và tác động đến hệ thống.
- Nhận diện rủi ro chuỗi cung ứng như typosquatting, dependency confusion, maintainer compromise và artifact bị thay thế.
- Lập kế hoạch cập nhật hoặc thay thế dependency có kiểm soát, sau đó xác minh bằng build, test và bằng chứng triển khai.
- Viết kết luận review có phạm vi, mức độ, bằng chứng, hành động và thời hạn xử lý rõ ràng.

## 1. Dependency là gì trong một hệ thống xác thực?

Dependency là thành phần mà phần mềm cần đến để biên dịch, đóng gói, khởi chạy hoặc thực hiện chức năng. Một dependency có thể cung cấp chức năng nghiệp vụ, nhưng cũng có thể xử lý dữ liệu nhạy cảm hoặc quyết định một kiểm tra an ninh quan trọng.

### 1.1. Các loại dependency cần kiểm kê

| Loại | Ví dụ trong hệ thống xác thực | Vì sao cần rà soát |
|---|---|---|
| Dependency trực tiếp | Thư viện JWT, OIDC client, WebAuthn, password hashing hoặc SDK identity provider được khai báo trong ứng dụng | Nhóm phát triển chủ động lựa chọn và thường có thể cập nhật trực tiếp |
| Dependency bắc cầu | Parser JSON, thư viện ASN.1, HTTP client hoặc crypto provider được thư viện khác kéo vào | Có thể tồn tại lỗ hổng dù nhóm phát triển không khai báo trực tiếp |
| Runtime dependency | Thư viện được tải khi ứng dụng chạy | Có thể tác động trực tiếp đến request, token, session hoặc credential |
| Build-time dependency | Compiler plugin, annotation processor, code generator, Gradle/Maven plugin | Có thể thực thi mã trong pipeline và tiếp cận source, artifact hoặc secret CI |
| Test dependency | Mock server, test framework, fixture parser, integration-test container | Thường không chạy production nhưng vẫn có thể ảnh hưởng môi trường CI hoặc bị đóng gói nhầm |
| Frontend dependency | Package quản lý form đăng nhập, WebAuthn browser helper, OAuth redirect hoặc UI MFA | Có thể tác động đến origin đăng nhập, dữ liệu người dùng và luồng trình duyệt |
| Container / OS component | Base image, OpenSSL, CA bundle, shell utility, package hệ điều hành | Ứng dụng có thể dùng thành phần này dù không xuất hiện trong dependency manifest |
| SDK / agent bên ngoài | SDK identity provider, telemetry agent, APM agent, service mesh sidecar | Có thể nhận token, claim, header hoặc thông tin định danh trong quá trình hoạt động |

Không nên chỉ kiểm tra file khai báo dependency trực tiếp. Dependency tree thực tế sau khi giải quyết phiên bản, artifact được đóng gói và image triển khai mới phản ánh gần đúng những gì hệ thống chạy.

### 1.2. Phân biệt dependency với dịch vụ bên ngoài

Một identity provider hoặc dịch vụ MFA được gọi qua mạng có thể không phải thư viện được đóng gói vào ứng dụng, nhưng vẫn là thành phần phụ thuộc về mặt vận hành và tin cậy. Review nên ghi nhận:

- Tổ chức nào vận hành dịch vụ và ai chịu trách nhiệm bảo mật?
- Ứng dụng gửi những dữ liệu nào: định danh, email, IP, token, assertion hay metadata thiết bị?
- Dịch vụ xác minh callback, chữ ký, issuer, audience và trạng thái giao dịch như thế nào?
- Khi dịch vụ ngừng hoạt động hoặc bị xâm phạm, hệ thống có fail open, fail closed hay có fallback?
- Có cơ chế xoay secret, chứng thư, signing key và thu hồi grant không?

Phạm vi bài học tập trung vào dependency phần mềm, nhưng kết luận phải nêu rõ nếu rủi ro còn phụ thuộc vào dịch vụ hoặc cấu hình bên ngoài.

### 1.3. Vì sao dependency xác thực có tác động lớn?

Một dependency có thể nằm ở một trong các vị trí sau:

- Nhận mật khẩu và chuyển mật khẩu đến password verifier.
- Tạo, lưu hoặc xác minh mã MFA.
- Tạo challenge, kiểm tra origin hoặc xác minh chữ ký WebAuthn.
- Parse và xác minh JWT, SAML assertion hoặc OAuth response.
- Xây dựng chuỗi tin cậy chứng chỉ và kiểm tra trạng thái thu hồi.
- Tạo session, cookie, CSRF token hoặc xử lý logout.
- Tra cứu liên kết danh tính và xử lý callback từ identity provider.
- Gửi request đến token endpoint hoặc user-info endpoint.
- Ghi log, trace, metric hoặc báo cáo lỗi có chứa thông tin nhạy cảm.

Lỗi trong dependency ở các vị trí này có thể khiến kẻ tấn công giả mạo danh tính, chiếm phiên, vượt MFA, đánh cắp token hoặc làm lộ thông tin. Tuy nhiên, mức tác động phụ thuộc vào cách ứng dụng sử dụng thư viện, cấu hình, quyền của tiến trình và các lớp kiểm soát còn lại.

## 2. Lập danh mục dependency và xác định phạm vi

Một review tốt bắt đầu bằng danh mục có thể tái lập. Danh mục phải gắn với một ứng dụng, phiên bản, commit, build hoặc artifact cụ thể.

### 2.1. Những nguồn dữ liệu nên thu thập

- Manifest: pom.xml, build.gradle, build.gradle.kts, package.json, requirements hoặc manifest tương ứng.
- Lock file: Gradle dependency lock, npm lock file hoặc lock file của hệ sinh thái đang dùng.
- Dependency tree sau khi resolve.
- SBOM (Software Bill of Materials) của artifact hoặc image được phát hành.
- Danh sách plugin build, compiler plugin, annotation processor và CI action.
- Container image digest và danh sách package hệ điều hành.
- Kết quả SCA, vulnerability scanner, secret scanner và license scanner.
- Artifact repository, package registry, nguồn tải và thông tin provenance nếu có.
- Phiên bản runtime thực tế và cấu hình bật/tắt dependency theo profile.

Ghi lại thời điểm tạo danh mục. Dependency tree có thể thay đổi theo repository, profile, platform, version catalog, variant hoặc cấu hình build. Một báo cáo cũ không tự động đại diện cho artifact mới.

### 2.2. Từ manifest đến dependency tree

Manifest cho biết ý định khai báo. Dependency tree cho biết quan hệ phụ thuộc được resolver chọn tại thời điểm build. Hai thứ có thể khác nhau do:

- Version range hoặc dynamic version.
- BOM và dependency management.
- Conflict resolution giữa nhiều phiên bản.
- Optional dependency hoặc profile theo môi trường.
- Plugin và platform-specific variant.
- Dependency được kéo vào bởi framework hoặc SDK.

Với dự án Java dùng Maven, có thể bắt đầu bằng:

~~~bash
mvn dependency:tree
mvn dependency:tree -Dscope=runtime
~~~

Với dự án Gradle:

~~~bash
./gradlew dependencies
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
~~~

Tên configuration và module cần điều chỉnh theo dự án. Một lệnh xem dependency tree không chứng minh rằng artifact production đã được triển khai đúng với cây đó; hãy liên kết kết quả với commit, build và artifact digest.

### 2.3. Lock file và khả năng tái lập

Lock file ghi nhận phiên bản đã được resolver chọn để các lần build sau có kết quả nhất quán hơn. Dependency locking giúp giảm việc một build hôm nay và ngày mai tự động lấy hai phiên bản khác nhau do khai báo dynamic.

Ví dụ cấu hình Gradle để bật dependency locking:

~~~kotlin
dependencyLocking {
    lockAllConfigurations()
}
~~~

Sau khi cấu hình, nhóm phát triển tạo và quản lý lock state theo quy trình của dự án. Lock file phải được review cùng thay đổi dependency; không cập nhật hàng loạt một cách mù quáng.

Locking giải quyết tính ổn định của phiên bản, nhưng không chứng minh phiên bản đã khóa là an toàn. Một phiên bản độc hại hoặc đã có lỗ hổng vẫn có thể được khóa ổn định.

### 2.4. SBOM giúp trả lời điều gì?

SBOM mô tả các thành phần có trong một sản phẩm phần mềm. Định dạng phổ biến gồm CycloneDX và SPDX. Tùy công cụ, SBOM có thể ghi:

- Tên package, phiên bản, supplier và định danh package.
- Quan hệ giữa các thành phần.
- License.
- Hash hoặc thông tin nhận dạng artifact.
- Dependency trực tiếp và bắc cầu.
- Metadata về build hoặc nguồn tạo SBOM.

SBOM hỗ trợ đối chiếu nhanh khi một lỗ hổng mới được công bố. Tuy vậy, SBOM có thể thiếu package của hệ điều hành, thành phần được tải động, plugin hoặc thông tin nguồn gốc. Cần biết công cụ đã quét loại artifact nào và giới hạn của kết quả.

## 3. Xác định dependency nào nằm trên đường đi xác thực

Không phải mọi dependency có cùng mức rủi ro. Hãy vẽ luồng xác thực và đánh dấu thành phần thực sự xử lý dữ liệu hoặc quyết định bảo mật.

| Luồng | Nhóm dependency liên quan | Câu hỏi review |
|---|---|---|
| Password authentication | Framework security, password encoder, KDF provider, database driver | Mật khẩu có được băm bằng thuật toán phù hợp? Có bị log hoặc đưa vào exception không? |
| MFA / OTP | TOTP library, QR encoder, SMS/email SDK, push provider | Secret MFA có bị lộ? Có kiểm tra time window, replay và rate limit không? |
| Passkey / WebAuthn | WebAuthn server library, CBOR/COSE parser, browser helper | Có xác minh challenge, origin, RP ID, chữ ký và credential state đúng không? |
| Certificate authentication | TLS provider, X.509 parser, PKIX validator, OCSP/CRL client | Có xác minh chain, SAN, EKU, thời hạn và revocation theo policy không? |
| OAuth / OIDC / federation | OAuth client, OIDC library, JWT/JWS parser, SAML parser, HTTP client | Có kiểm tra issuer, audience, state, nonce, PKCE và redirect URI không? |
| Session management | Web framework, cookie/session middleware, CSRF library, distributed cache client | Session ID có được bảo vệ, rotate, expire và revoke đúng không? |
| Identity linking / recovery | Email/SMS SDK, account-linking module, workflow engine | Có ngăn liên kết nhầm tài khoản hoặc dùng recovery token nhiều lần không? |
| Logging / observability | Logging facade, encoder, tracing agent, APM exporter | Có redaction token, cookie, password, recovery code và assertion không? |

Tạo bản đồ dependency với các thuộc tính: module sử dụng, endpoint hoặc luồng liên quan, dữ liệu đầu vào, quyền của tiến trình, phiên bản và người sở hữu. Bản đồ này giúp phân biệt một parser chỉ dùng trong test với parser được gọi trên request không tin cậy trong production.

### 3.1. Đánh giá vị trí dữ liệu và quyền

Với từng dependency quan trọng, hỏi:

- Nó nhận dữ liệu từ người dùng, trình duyệt, IdP hay chỉ từ cấu hình nội bộ?
- Dữ liệu có được xác thực trước khi đưa vào thư viện không?
- Thư viện có chạy với quyền truy cập filesystem, network, environment variable hoặc secret store không?
- Nó có thể gọi callback hoặc plugin do bên ngoài cung cấp không?
- Lỗi có làm hệ thống từ chối truy cập, chấp nhận sai danh tính hay rò rỉ dữ liệu?
- Có thể tắt chức năng hoặc thay thư viện mà không phá vỡ luồng đăng nhập không?

Một parser xử lý token từ Internet có bề mặt tấn công khác một tiện ích chỉ xử lý dữ liệu test. Một build plugin có thể không chạy trong production nhưng vẫn có quyền đọc signing key và repository credential trong CI; vì vậy build-time dependency cũng cần review.

## 4. Các nhóm rủi ro dependency

### 4.1. Lỗ hổng đã công bố

Lỗ hổng có thể được công bố dưới CVE hoặc advisory của hệ sinh thái. Cần xác định:

- Package và phiên bản có đúng với thành phần trong artifact không?
- Advisory áp dụng cho module, classifier hoặc platform nào?
- Phiên bản đang dùng nằm trong dải bị ảnh hưởng hay đã được vá?
- Lỗ hổng cần cấu hình hoặc điều kiện kích hoạt nào?
- Mã dễ bị lỗi có thể được gọi từ luồng thực tế không?
- Có exploit công khai, khai thác thực tế hoặc dấu hiệu bị lạm dụng không?
- Có bản vá, phiên bản thay thế hoặc workaround được nhà cung cấp khuyến nghị không?

Không kết luận “không ảnh hưởng” chỉ vì scanner không tìm thấy CVE. Scanner có thể chưa nhận diện đúng package, thiếu advisory hoặc chưa hỗ trợ phiên bản mới. Cũng không kết luận “bị khai thác được” chỉ vì một CVE có điểm nghiêm trọng cao.

### 4.2. Dependency bị bỏ bảo trì

Dấu hiệu cần chú ý:

- Không có bản phát hành hoặc sửa lỗi trong thời gian dài.
- Maintainer không còn phản hồi issue bảo mật.
- Phiên bản hiện tại không còn được hỗ trợ.
- Không có quy trình công bố advisory hoặc phát hành bản vá.
- Dependency giữ nhiều API cũ, dùng thuật toán đã lỗi thời hoặc yêu cầu runtime không còn được hỗ trợ.

Không có commit gần đây không tự động chứng minh dự án không an toàn; thư viện ổn định có thể ít thay đổi. Hãy đánh giá khả năng nhận bản vá, mức độ phụ thuộc và phương án thay thế.

### 4.3. Rủi ro nguồn gốc và chuỗi cung ứng

| Rủi ro | Cách xảy ra | Tín hiệu cần xem xét |
|---|---|---|
| Typosquatting | Package có tên gần giống package phổ biến | Tên, namespace, maintainer, lịch sử phát hành và mức độ phổ biến bất thường |
| Dependency confusion | Resolver lấy package cùng tên từ registry không tin cậy | Cấu hình repository, namespace nội bộ, thứ tự ưu tiên và policy registry |
| Maintainer compromise | Tài khoản maintainer hoặc quyền publish bị chiếm | Thay đổi maintainer, release bất thường, artifact khác biệt hoặc cảnh báo từ registry |
| Malicious release | Phiên bản mới chứa mã độc hoặc hành vi không liên quan | Script cài đặt, code obfuscation, truy cập network/file/secret bất thường |
| Repository takeover | Tên package cũ được đăng ký lại sau khi package bị bỏ | Thay đổi chủ sở hữu, namespace hoặc lịch sử phát hành |
| Build plugin compromise | Plugin thực thi mã trong pipeline | Plugin có quyền quá rộng, tải mã động, thay đổi artifact hoặc truy cập secret CI |
| Artifact substitution | Artifact tải về khác artifact đã review | Hash/signature không khớp, nguồn tải không được xác thực |
| Compromised CI action | Action hoặc runner bị thay đổi | Reference theo nhánh có thể đổi, quyền token CI rộng và log/build bất thường |

Không tải hoặc chạy một package đáng ngờ trên máy phát triển hoặc pipeline production chỉ để “xem thử”. Dùng môi trường phân tích cô lập, không có credential thật và có kiểm soát network nếu cần phân tích hành vi.

### 4.4. Rủi ro mật mã và giao thức

Với dependency xử lý mật mã hoặc giao thức xác thực, review cần xem cả hỗ trợ thuật toán lẫn cách ứng dụng gọi thư viện:

- Có còn hỗ trợ thuật toán hoặc protocol đã lỗi thời không?
- Có sử dụng API mặc định an toàn hay ứng dụng tự bật chế độ yếu?
- Có kiểm tra chữ ký, MAC và chứng thư đúng cách không?
- Có dùng nguồn ngẫu nhiên an toàn và xử lý lỗi đúng không?
- Có xác minh hostname, certificate chain và thời hạn TLS không?
- Có parser dễ bị DoS do input quá lớn, lồng sâu hoặc cấu trúc bất thường không?
- Có phân biệt token cho các issuer, audience hoặc purpose khác nhau không?

Một thư viện mật mã được bảo trì tốt không thể sửa lỗi khi ứng dụng tự bỏ qua kiểm tra chữ ký, chấp nhận mọi audience hoặc tắt xác minh hostname.

### 4.5. Rủi ro license và điều khoản sử dụng

License không phải lỗ hổng kỹ thuật, nhưng có thể là rủi ro phát hành và vận hành. Cần ghi nhận license, nghĩa vụ phân phối source hoặc notice, hạn chế sử dụng và quy trình phê duyệt của tổ chức. Không gộp license risk với vulnerability severity; báo cáo nên tách hai loại kết luận.

## 5. Đọc và xác minh cảnh báo SCA

SCA (Software Composition Analysis) so khớp danh mục dependency với cơ sở dữ liệu lỗ hổng, license và đôi khi cả dữ liệu nguồn gốc. Công cụ hỗ trợ phát hiện, nhưng người review vẫn phải xác minh ngữ cảnh.

### 5.1. Các trường cần đọc trong một finding

| Trường | Ý nghĩa | Cách kiểm tra |
|---|---|---|
| Package identity | Tên, namespace, ecosystem và phiên bản | Đối chiếu manifest, lock file và SBOM |
| Advisory / CVE | Định danh cảnh báo | Đọc mô tả và nguồn advisory gốc |
| Affected range | Dải phiên bản bị ảnh hưởng | So sánh đúng quy tắc version của ecosystem |
| Fixed version | Phiên bản được cho là đã sửa | Xác minh changelog, release note và advisory |
| Severity / CVSS | Mức nghiêm trọng kỹ thuật | Xem vector và giả định của điểm số |
| EPSS / exploitation signal | Ước lượng hoặc tín hiệu khai thác | Dùng như một yếu tố ưu tiên, không coi là bằng chứng hệ thống đã bị xâm nhập |
| Reachability | Mã lỗi có thể được gọi từ ứng dụng không | Kiểm tra call path, feature, endpoint và cấu hình |
| Runtime exposure | Dependency có trong artifact hoặc môi trường chạy không | Đối chiếu image, package và deployment |
| License | Điều kiện sử dụng/phân phối | Xác minh license của đúng artifact và policy tổ chức |
| Evidence / confidence | Chất lượng dữ liệu và độ chắc chắn | Ghi rõ nguồn, thời điểm và giới hạn scanner |

### 5.2. Không chỉ dựa vào điểm CVSS

CVSS mô tả đặc tính và mức độ nghiêm trọng của lỗ hổng trong điều kiện giả định. Độ ưu tiên xử lý trong một hệ thống còn phụ thuộc:

- Dependency có thực sự được triển khai không?
- Luồng bị ảnh hưởng có bật trong production không?
- Kẻ tấn công có thể kiểm soát input đi vào mã dễ bị lỗi không?
- Có cần quyền, tương tác người dùng hoặc điều kiện mạng đặc biệt không?
- Thành phần có xử lý credential, token, signing key hay dữ liệu nhạy cảm không?
- Có biện pháp giảm thiểu đã được kiểm chứng không?
- Hệ thống có public exposure, tenant đa người dùng hoặc quyền quản trị cao không?
- Lỗ hổng có được khai thác thực tế hoặc có exploit khả dụng không?

Một CVE có CVSS cao nhưng chỉ ảnh hưởng công cụ test không có mặt trong production có thể được ưu tiên thấp hơn lỗ hổng mức vừa trong JWT verifier đang nhận request Internet. Tuy nhiên, build tool vẫn có thể là rủi ro cao nếu pipeline giữ production secret.

### 5.3. Reachability cần bằng chứng

Reachability là đánh giá liệu ứng dụng có thể gọi đến đoạn mã dễ bị lỗi trong điều kiện thực tế. Có thể xem xét:

1. Dependency xuất hiện trong dependency tree nào?
2. Module bị ảnh hưởng có được đóng gói và tải không?
3. API hoặc class dễ bị lỗi có được gọi không?
4. Dữ liệu đầu vào có thể đến từ nguồn không tin cậy không?
5. Cấu hình cần thiết để kích hoạt lỗ hổng có đang bật không?
6. Có kiểm thử hoặc trace nào chứng minh đường đi không?

Nếu chưa thể chứng minh reachability, ghi “chưa xác định” và đề xuất xác minh. Không biến việc scanner không thấy call path thành kết luận chắc chắn rằng lỗ hổng không thể khai thác.

## 6. Rà soát dependency theo từng luồng xác thực

### 6.1. Password và password hashing

Đối với thư viện password hashing hoặc crypto provider:

- Xác minh thuật toán được hỗ trợ và cấu hình sử dụng thực tế.
- Ưu tiên password hashing chuyên dụng như Argon2id, bcrypt hoặc scrypt theo chính sách và năng lực nền tảng; không dùng hash nhanh thông thường để lưu mật khẩu.
- Kiểm tra salt được tạo riêng cho mỗi mật khẩu và tham số cost có thể điều chỉnh.
- Kiểm tra thư viện có xử lý migration hash khi nâng tham số không.
- Xác minh API không log mật khẩu, hash, salt hoặc request body nhạy cảm.
- Kiểm tra giới hạn tài nguyên để tránh input gây tiêu thụ CPU/RAM quá mức.

Review dependency không thể chỉ nhìn tên thư viện. Cần kiểm tra cấu hình thực tế và xác minh hash được tạo ra bằng thuật toán, tham số và format dự kiến.

### 6.2. MFA và OTP

Với thư viện TOTP/HOTP hoặc SDK gửi mã:

- Xác minh kiểm tra counter/time-step, cửa sổ thời gian và replay.
- Kiểm tra mã có bị chấp nhận nhiều lần trong cùng giao dịch không.
- Đánh giá rate limit, lockout và chống enumeration ở lớp ứng dụng.
- Bảo vệ secret seed, QR enrollment và recovery code.
- Kiểm tra SDK SMS/email có log nội dung OTP hoặc ghi payload vào analytics không.
- Xác minh callback từ push provider có chữ ký hoặc cơ chế xác thực phù hợp.

Dependency cung cấp TOTP không tự bảo đảm rằng hệ thống chống brute force. Chính sách giới hạn lần thử và trạng thái sử dụng mã thường nằm ở lớp ứng dụng hoặc kho dữ liệu.

### 6.3. Passkey và WebAuthn

Dependency WebAuthn có thể xử lý CBOR, COSE, authenticator data và client data. Review cần kiểm tra:

- Phiên bản thư viện còn được hỗ trợ và có bản vá parser không?
- Có xác minh challenge được tạo cho đúng giao dịch và chỉ dùng một lần không?
- Có kiểm tra origin và RP ID theo cấu hình chính xác không?
- Có xác minh chữ ký, credential public key và loại thuật toán được cho phép không?
- Có kiểm tra user presence / user verification theo policy không?
- Có kiểm soát counter hoặc tín hiệu clone theo cách phù hợp với authenticator hiện đại không?
- Có xử lý an toàn credential ID, attestation và metadata nhạy cảm không?
- Có cập nhật chính sách khi thư viện thay đổi cách parse hoặc kiểm tra extension không?

Không coi việc thư viện trả về “verification successful” là đủ nếu ứng dụng truyền sai expected origin, RP ID, challenge hoặc user context.

### 6.4. Certificate và PKI

Đối với X.509, TLS và PKIX dependency:

- Kiểm tra xây dựng và xác minh certificate chain.
- Kiểm tra SAN, EKU, key usage, issuer, subject và thời hạn.
- Kiểm tra hostname verification và trust store.
- Xác định chính sách CRL/OCSP, cache và hành vi khi dịch vụ kiểm tra trạng thái không sẵn sàng.
- Kiểm tra parser xử lý certificate bất thường hoặc chuỗi lớn như thế nào.
- Đảm bảo private key không bị ghi log hoặc export ngoài policy.

Đặc biệt tránh tự viết logic xác minh chứng chỉ bằng cách so sánh chuỗi subject hoặc chỉ kiểm tra ngày hết hạn. Hãy dùng thư viện PKI được hỗ trợ và cấu hình trust anchor rõ ràng.

### 6.5. OAuth, OIDC, JWT và federation

Với thư viện protocol:

- Kiểm tra issuer, audience, signature, algorithm allowlist và thời hạn.
- Kiểm tra state, nonce và PKCE theo flow.
- Ràng buộc redirect URI chính xác.
- Phân biệt ID token, access token và authorization code.
- Xác minh token endpoint, JWKS endpoint và TLS hostname.
- Xử lý key rotation và cache JWKS an toàn.
- Kiểm tra SAML signature wrapping, XML parser hardening và các tùy chọn external entity nếu có SAML/XML.
- Xác minh clock skew và cách xử lý claim thiếu hoặc sai kiểu.

Thư viện JWT có thể parse token mà không xác minh chữ ký. API parse không đồng nghĩa API verify. Review phải xác định ứng dụng gọi đúng API và từ chối token nếu bất kỳ kiểm tra bắt buộc nào thất bại.

### 6.6. Session, cookie và HTTP client

Đánh giá framework và middleware xử lý:

- Session ID có được rotate sau đăng nhập hoặc nâng quyền không?
- Cookie có Secure, HttpOnly và SameSite phù hợp không?
- Có giới hạn idle timeout và absolute lifetime không?
- Logout có hủy trạng thái server-side và token liên quan không?
- HTTP client có xác minh TLS và hostname không?
- Redirect có thể làm lộ Authorization header hoặc token đến host khác không?
- Retry có thể gửi lại authorization code, OTP hoặc thao tác nhạy cảm không?
- Error message có chứa header, cookie hoặc token không?

Một HTTP client có redirect behavior không an toàn có thể chuyển credential đến một origin khác. Review cần kiểm tra cả default behavior lẫn wrapper của ứng dụng.

## 7. Quy trình dependency review có thể lặp lại

### Bước 1 — Chốt phạm vi và phiên bản

Ghi nhận repository, module, commit, build profile, artifact, môi trường và ngày review. Xác định mục tiêu là source tree, container image, production artifact hay tất cả. Không trộn kết quả của các phiên bản khác nhau.

### Bước 2 — Thu thập danh mục

Tạo dependency tree, lock file và SBOM. Thu thập cả build plugin, CI action, container base image và package hệ điều hành có liên quan. Ghi rõ thành phần nào không thể nhận diện hoặc chưa có dữ liệu.

### Bước 3 — Quét và đối chiếu nguồn

Chạy SCA/vulnerability scanner và license scanner trong pipeline hoặc môi trường review. Đối chiếu advisory với nguồn của maintainer, ecosystem hoặc cơ sở dữ liệu đáng tin cậy. Kiểm tra package identity để tránh nhầm tên hoặc nhầm phiên bản.

### Bước 4 — Xác minh ảnh hưởng xác thực

Với từng finding, liên kết dependency với luồng xác thực, endpoint, dữ liệu, quyền và cấu hình. Đánh giá reachability, runtime exposure, điều kiện khai thác và biện pháp giảm thiểu.

### Bước 5 — Xếp hạng và quyết định

Chấm mức độ theo tác động, khả năng khai thác, exposure, độ nhạy dữ liệu và chất lượng bằng chứng. Xác định một trong các quyết định:

- Update: nâng lên phiên bản đã vá.
- Replace: thay dependency bằng thành phần được hỗ trợ.
- Remove: loại bỏ dependency không cần thiết.
- Mitigate: giảm exposure hoặc tắt chức năng dễ bị lỗi trong thời gian chờ bản vá.
- Accept temporarily: chấp nhận có thời hạn, có chủ sở hữu, lý do và biện pháp giảm thiểu.
- Investigate: cần thêm bằng chứng trước khi quyết định.

### Bước 6 — Thay đổi và kiểm thử

Thay đổi dependency trong nhánh có review. Kiểm tra release note, breaking change, migration note và thay đổi API. Chạy build, unit test, integration test và security regression test liên quan đến luồng xác thực.

Kiểm thử tối thiểu nên bao gồm:

- Đăng nhập hợp lệ và từ chối credential không hợp lệ.
- Token sai chữ ký, issuer, audience, thời hạn hoặc nonce.
- Authorization code dùng lại hoặc PKCE không khớp.
- MFA code hết hạn hoặc đã dùng lại.
- WebAuthn challenge/origin/RP ID sai.
- Certificate hết hạn, sai SAN hoặc chain không tin cậy.
- Session cũ sau logout hoặc sau khi đổi quyền.
- Lỗi dependency không làm hệ thống chuyển sang trạng thái fail-open.

Không chỉ chạy test happy path. Cập nhật parser, crypto provider hoặc authentication framework có thể làm thay đổi cách xử lý dữ liệu sai định dạng và lỗi xác minh.

### Bước 7 — Xác minh artifact và triển khai

Tạo lại SBOM cho artifact mới, xác minh package version và hash, sau đó đối chiếu với artifact được triển khai. Kiểm tra container image digest, dependency lock state và provenance theo quy trình release.

Với hệ thống xác thực quan trọng, có thể triển khai theo canary hoặc rollout có giám sát. Theo dõi tỷ lệ đăng nhập thất bại, lỗi token validation, lỗi TLS, lỗi callback, MFA enrollment và các cảnh báo bất thường sau cập nhật.

### Bước 8 — Ghi nhận và theo dõi

Mỗi finding cần có owner, mức độ, bằng chứng, quyết định, hạn xử lý, trạng thái và điều kiện đóng. Nếu chấp nhận tạm thời, phải có ngày hết hạn và sự kiện kích hoạt review lại, chẳng hạn bản vá được phát hành hoặc dependency bị khai thác thực tế.

## 8. Ví dụ thực hành với Maven và Gradle

### 8.1. Maven: kiểm tra dependency tree

~~~bash
mvn dependency:tree
mvn dependency:tree -Dscope=runtime
~~~

Đọc kết quả để xác định dependency nào kéo một thư viện vào và phiên bản nào được chọn. Nếu thư viện JWT xuất hiện qua một SDK identity provider, ghi lại cả đường phụ thuộc để xác định nơi cần nâng phiên bản.

Có thể dùng dependencyManagement hoặc BOM để quản lý phiên bản nhất quán:

~~~xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>com.example.security</groupId>
      <artifactId>security-bom</artifactId>
      <version>1.2.3</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>
~~~

Đây là ví dụ cấu trúc minh họa; tọa độ và phiên bản phải lấy từ BOM thật của dự án. Không sao chép một version minh họa vào production.

### 8.2. Gradle: xem dependency và nguồn phiên bản

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jose --configuration runtimeClasspath
~~~

Tên dependency và configuration cần điều chỉnh theo project. Dependency insight giúp tìm lý do một phiên bản được chọn, ví dụ do constraint, platform hoặc một dependency khác yêu cầu.

Có thể khai báo version catalog để tập trung quản lý:

~~~toml
[versions]
security-lib = "1.2.3"

[libraries]
security-core = { module = "com.example.security:security-core", version.ref = "security-lib" }
~~~

Version catalog cải thiện khả năng quản lý và review; nó không tự xác minh package an toàn.

### 8.3. Dependency verification

Gradle hỗ trợ verification metadata để kiểm tra artifact theo checksum hoặc chữ ký đã được cấu hình. Khi sử dụng, cần:

- Lấy checksum hoặc chữ ký từ nguồn tin cậy độc lập.
- Review thay đổi verification metadata như thay đổi mã nguồn nhạy cảm.
- Không tự động chấp nhận mọi checksum mới chỉ vì build báo mismatch.
- Bảo vệ khóa ký và quy trình phát hành artifact.
- Kiểm tra cả plugin và dependency theo phạm vi công cụ hỗ trợ.

Checksum chứng minh artifact khớp với giá trị tham chiếu. Nếu giá trị tham chiếu được lấy từ cùng nguồn đã bị xâm phạm, nó không chứng minh artifact đáng tin cậy.

### 8.4. SCA và SBOM trong pipeline

Một pipeline có thể tổ chức như sau:

~~~text
Checkout source
    |
    v
Resolve dependencies with locked versions
    |
    v
Build and run tests
    |
    v
Generate SBOM for the produced artifact
    |
    v
Run SCA and license policy checks
    |
    v
Review high-risk findings and exceptions
    |
    v
Verify artifact provenance and digest
    |
    v
Publish only approved artifact
~~~

Công cụ có thể gồm scanner theo ecosystem, SCA scanner, SBOM generator và image scanner. Chọn công cụ dựa trên ecosystem, khả năng nhận diện package, độ cập nhật advisory, hỗ trợ CI và cách xuất bằng chứng. Không có một scanner duy nhất bao phủ mọi dependency hoặc mọi dạng rủi ro chuỗi cung ứng.

## 9. Tình huống minh họa: thư viện JWT bắc cầu có lỗ hổng

Một dịch vụ đăng nhập sử dụng SDK của identity provider. SDK kéo vào thư viện JWT parser ở dạng dependency bắc cầu. SCA cảnh báo phiên bản parser có một lỗ hổng liên quan đến xử lý header token.

Nhóm review không nên dừng ở việc nhìn điểm CVSS. Hãy làm theo trình tự:

1. Xác minh package identity và phiên bản trong runtime dependency tree.
2. Kiểm tra thư viện parser có nằm trong artifact production không.
3. Đọc advisory để xác định điều kiện khai thác và module/API bị ảnh hưởng.
4. Xác định dịch vụ có parse JWT từ request không tin cậy bằng API bị ảnh hưởng không.
5. Kiểm tra token có được xác minh chữ ký, issuer, audience và algorithm allowlist trước khi dùng claim không.
6. Kiểm tra phiên bản đã vá và khả năng tương thích của SDK.
7. Nâng dependency hoặc SDK theo đường được nhà cung cấp hỗ trợ; tránh ép một phiên bản bắc cầu nếu SDK yêu cầu API không tương thích.
8. Chạy regression test với token hợp lệ, token sai chữ ký, token sai audience, header bất thường và token quá lớn.
9. Tạo SBOM mới, xác minh artifact mới và theo dõi lỗi xác thực sau triển khai.

**Kết luận review mẫu:** Finding ảnh hưởng đến parser được đóng gói trong runtime artifact và có đường gọi từ endpoint xác minh token. Nhóm đã cập nhật SDK lên phiên bản đã vá, kiểm thử các trường hợp token hợp lệ/không hợp lệ và xác minh SBOM của artifact mới. Nếu chưa chứng minh được call path, ghi rõ reachability chưa xác định và đặt hạn xác minh; không tự đóng finding bằng giả định.

## 10. Tình huống chuỗi cung ứng: package đăng nhập bị thay đổi

Một package frontend dùng trong trang đăng nhập phát hành phiên bản mới. Sau khi nâng phiên bản, pipeline phát hiện package có script cài đặt mới và hành vi truy cập network không phù hợp với chức năng.

Quy trình ứng phó:

1. Dừng promotion của artifact chưa phát hành; xác định build nào đã dùng phiên bản đáng ngờ.
2. Lưu metadata package, lock file, hash, build log và thời điểm tải.
3. Kiểm tra package đến từ registry và namespace nào; so sánh release với phiên bản trước và thông tin maintainer.
4. Xác định package có chạy trong CI, lúc cài đặt hay trong trình duyệt người dùng.
5. Nếu pipeline có thể đã lộ secret, rà soát quyền CI và xoay credential có nguy cơ bị đọc.
6. Nếu artifact đã đến production, đánh giá hành vi có thể đã chạy trên trình duyệt và dữ liệu nào có thể bị truy cập.
7. Gỡ hoặc khóa phiên bản đáng ngờ, thay bằng phiên bản xác minh được hoặc package thay thế.
8. Tạo lại artifact trong môi trường sạch, kiểm tra lock file và provenance.
9. Tăng kiểm soát registry, dependency review và quyền token của pipeline.

Không phải mọi thay đổi script cài đặt đều là mã độc. Cần xác minh hành vi và nguồn phát hành, nhưng không đưa artifact chưa rõ nguồn gốc vào môi trường có secret thật để kiểm tra.

## 11. Ưu tiên xử lý và ngoại lệ

Có thể dùng ma trận tham khảo dưới đây để thống nhất cách ưu tiên:

| Mức | Điều kiện tham khảo | Kỳ vọng xử lý |
|---|---|---|
| P0 / khẩn cấp | Dependency có dấu hiệu độc hại hoặc lỗ hổng đang bị khai thác, nằm trên đường xác thực/credential đặc quyền hoặc có nguy cơ lộ secret diện rộng | Cô lập, thu hồi credential liên quan khi cần, xác minh phạm vi và triển khai biện pháp khẩn cấp |
| P1 / cao | Lỗ hổng nghiêm trọng, runtime exposed, input không tin cậy có thể đến mã dễ bị lỗi hoặc ảnh hưởng token/identity boundary | Ưu tiên bản vá hoặc workaround được kiểm chứng; đặt owner và hạn xử lý ngắn |
| P2 / trung bình | Có lỗ hổng nhưng điều kiện khai thác hạn chế, exposure thấp hoặc có kiểm soát giảm thiểu đáng tin cậy | Lên lịch nâng cấp, kiểm thử và theo dõi advisory |
| P3 / thấp | Rủi ro thấp, không có đường thực thi liên quan hoặc thành phần chỉ dùng trong môi trường giới hạn | Ghi nhận, xử lý theo chu kỳ bảo trì và đánh giá lại khi phạm vi thay đổi |

Đây là khung nội bộ tham khảo, không phải SLA phổ quát. Tổ chức cần quy định thời hạn theo mức độ, loại dữ liệu, nghĩa vụ pháp lý và khả năng vận hành.

### 11.1. Khi cần chấp nhận rủi ro tạm thời

Một ngoại lệ hợp lệ cần có:

- Dependency, phiên bản, artifact và môi trường chính xác.
- Advisory hoặc rủi ro được xem xét.
- Bằng chứng về reachability, exposure và điều kiện khai thác.
- Lý do chưa thể cập nhật hoặc thay thế.
- Biện pháp giảm thiểu có thể kiểm tra.
- Người chịu trách nhiệm chấp nhận rủi ro.
- Ngày hết hạn và điều kiện review lại.
- Kế hoạch chuyển sang phiên bản đã vá hoặc giải pháp thay thế.

Không chấp nhận ngoại lệ vô thời hạn chỉ vì “không có thời gian nâng cấp”. Nếu dependency nằm trong luồng xác thực, cần đánh giá rõ tác động tới danh tính, phiên và quyền truy cập.

## 12. Kiểm soát liên tục trong vòng đời phát triển

Dependency review hiệu quả khi được thực hiện nhiều thời điểm:

- Khi thêm hoặc nâng dependency trong pull request.
- Khi lock file thay đổi.
- Khi tạo release hoặc container image.
- Theo lịch định kỳ để tìm advisory mới.
- Khi có thông báo maintainer compromise hoặc package bị thu hồi.
- Khi thay đổi identity provider, framework, protocol hoặc runtime.
- Sau sự cố có liên quan đến credential, token hoặc build pipeline.

Các kiểm soát nên bao gồm:

1. Chỉ cho phép registry và namespace được phê duyệt.
2. Ưu tiên phiên bản cụ thể, lock file và dependency constraints.
3. Review thay đổi dependency như thay đổi mã nguồn có rủi ro.
4. Bảo vệ CI token bằng quyền tối thiểu, thời hạn ngắn và scope hẹp.
5. Dùng SBOM cho artifact phát hành và lưu gắn với build ID.
6. Xác minh hash/chữ ký/provenance theo trust root đã thiết lập.
7. Chặn hoặc yêu cầu phê duyệt khi finding vượt ngưỡng policy.
8. Có quy trình exception với owner và ngày hết hạn.
9. Theo dõi dependency hết hỗ trợ và kế hoạch nâng cấp.
10. Định kỳ kiểm tra artifact production có khớp với dependency đã review.

Không nên tự động nâng mọi dependency lên phiên bản mới nhất mà không kiểm thử. Cập nhật bảo mật cần đi cùng kiểm tra tương thích, regression test và khả năng rollback an toàn.

## 13. Mẫu ghi nhận một dependency finding

Có thể dùng cấu trúc sau trong báo cáo review:

~~~text
Finding ID:
Application / module:
Commit / build / artifact digest:
Dependency:
Direct or transitive:
Resolved version:
Affected version range:
Advisory / CVE:
Source and date checked:
Runtime or build-time:
Authentication flow affected:
Input and call path:
Reachability:
Exploit preconditions:
Impact on identity / credential / token / session:
Existing mitigations:
Severity and rationale:
Decision: update / replace / remove / mitigate / accept temporarily / investigate
Owner:
Target date:
Validation evidence:
Residual risk:
Exception expiry (if applicable):
Status:
~~~

Một finding tốt cho phép người khác tái lập kết luận. Tránh ghi “thư viện không an toàn” mà không nêu package, phiên bản, artifact, nguồn advisory và tác động.

### 13.1. Ví dụ ghi nhận ngắn

~~~text
Finding ID: AUTH-DEP-014
Dependency: JWT parser library (transitive)
Resolved version: 4.x.y
Runtime or build-time: Runtime
Authentication flow affected: OIDC callback and API bearer-token validation
Reachability: Confirmed for untrusted token input at callback endpoint
Impact: Token parsing may fail unsafely under the advisory's stated preconditions
Decision: Update through the supported identity SDK release
Validation: Signature, issuer, audience, expiry and malformed-token regression tests passed
Residual risk: None known for the reviewed artifact; monitor upstream advisories
~~~

Các giá trị trên chỉ minh họa cấu trúc báo cáo, không mô tả một finding thực tế của dự án.

## 14. Checklist cho reviewer

### Phạm vi và inventory

- [ ] Đã xác định repository, module, commit, build profile và artifact.
- [ ] Đã thu thập manifest, lock file, dependency tree và SBOM phù hợp.
- [ ] Đã xem xét dependency bắc cầu, plugin build, CI action, container và package hệ điều hành.
- [ ] Đã phân biệt runtime, build-time và test-only dependency.
- [ ] Đã ghi nhận giới hạn của công cụ hoặc thành phần chưa nhận diện.

### Rủi ro và tác động xác thực

- [ ] Đã xác định dependency nào xử lý password, MFA, passkey, certificate, token, session hoặc recovery.
- [ ] Đã đối chiếu package/version với advisory đáng tin cậy.
- [ ] Đã kiểm tra affected range, fixed version và điều kiện khai thác.
- [ ] Đã đánh giá reachability và nguồn input không tin cậy.
- [ ] Đã xem xét quyền của dependency, CI và môi trường chạy.
- [ ] Đã kiểm tra provenance, maintainer, registry và dấu hiệu release bất thường.
- [ ] Đã xem xét license và tình trạng bảo trì riêng với vulnerability finding.

### Khắc phục và xác minh

- [ ] Đã chọn update, replace, remove, mitigate, accept temporarily hoặc investigate.
- [ ] Đã review lock file và thay đổi version.
- [ ] Đã chạy build và regression test liên quan đến luồng xác thực.
- [ ] Đã kiểm tra negative case như token sai chữ ký/audience, OTP replay và certificate không hợp lệ.
- [ ] Đã tạo lại SBOM và xác minh artifact sau cập nhật.
- [ ] Đã ghi owner, hạn xử lý, bằng chứng và residual risk.
- [ ] Ngoại lệ có ngày hết hạn và điều kiện review lại.

## 15. Tự kiểm tra kiến thức

**Câu 1.** Vì sao chỉ đọc manifest dependency trực tiếp chưa đủ để rà soát bảo mật?

**Gợi ý:** Thư viện trực tiếp có thể kéo theo dependency bắc cầu; build plugin, container và package hệ điều hành cũng có thể tham gia build hoặc runtime. Cần dependency tree và SBOM phù hợp với artifact.

**Câu 2.** Scanner báo một CVE nghiêm trọng trong dependency. Có thể lập tức kết luận production bị khai thác được không?

**Gợi ý:** Chưa. Cần xác minh package/version, affected range, artifact có chứa dependency không, mã dễ bị lỗi có reachable không và điều kiện khai thác có tồn tại không. Cũng phải xem xét exposure và biện pháp giảm thiểu.

**Câu 3.** Dependency locking có chứng minh dependency an toàn không?

**Gợi ý:** Không. Locking làm phiên bản được resolve ổn định và tái lập hơn; nó không xác nhận phiên bản đã khóa không có lỗ hổng hoặc nguồn phát hành đáng tin cậy.

**Câu 4.** Vì sao build-time dependency vẫn cần được review nếu không được đóng gói vào production?

**Gợi ý:** Plugin hoặc công cụ build có thể chạy trong CI, đọc source, signing key, registry credential và secret của pipeline. Nếu bị xâm phạm, nó có thể thay đổi artifact hoặc lấy secret.

**Câu 5.** Một thư viện JWT xác minh chữ ký đúng nhưng ứng dụng không kiểm tra audience. Finding thuộc trách nhiệm của ai?

**Gợi ý:** Cần xem cả API và cách ứng dụng tích hợp. Thư viện cung cấp chức năng xác minh chữ ký không tự bảo đảm toàn bộ policy token. Ứng dụng phải kiểm tra audience và các claim bắt buộc theo resource server.

**Câu 6.** Vì sao checksum tải cùng artifact từ một registry không đủ để chứng minh artifact đáng tin cậy?

**Gợi ý:** Nếu artifact và checksum cùng bị thay thế từ một nguồn đã bị xâm phạm, chúng vẫn khớp nhau. Cần trust root hoặc bằng chứng provenance/chữ ký độc lập theo policy.

## 16. Nguyên tắc cần ghi nhớ

1. Review dependency phải gắn với artifact và phiên bản thực tế được build hoặc triển khai.
2. Kiểm tra cả dependency trực tiếp, bắc cầu, build-time, frontend, container và hệ điều hành.
3. Đánh giá lỗ hổng bằng phiên bản, điều kiện khai thác, reachability, exposure và tác động xác thực.
4. Một thư viện bảo mật tốt không bù được cách tích hợp sai hoặc cấu hình bỏ qua kiểm tra.
5. Lock file, SBOM, checksum và provenance giải quyết các câu hỏi khác nhau; không công cụ nào thay thế tất cả.
6. Rủi ro chuỗi cung ứng có thể xuất hiện qua maintainer, registry, build plugin, CI action hoặc artifact.
7. Cập nhật phải đi cùng regression test, xác minh artifact và theo dõi sau triển khai.
8. Ngoại lệ cần owner, bằng chứng, biện pháp giảm thiểu và ngày hết hạn.

Dependency review hoàn tất khi nhóm có thể chỉ ra thành phần nào được sử dụng, rủi ro nào ảnh hưởng đến luồng xác thực, quyết định xử lý dựa trên bằng chứng nào và artifact sau xử lý đã được xác minh ra sao.

