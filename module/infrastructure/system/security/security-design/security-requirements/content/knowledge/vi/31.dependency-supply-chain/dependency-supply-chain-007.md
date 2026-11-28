# Artifact signature

## 1. Từ mục tiêu chống thay thế artifact đến yêu cầu kiểm chứng

Trong chương **Dependency và supply chain**, artifact signature là chữ ký số dùng để hỗ trợ xác minh tính toàn vẹn và nguồn ký của một đơn vị phần mềm được phân phối: JAR, archive, executable, package, container image hoặc metadata gắn với chúng.

Một bản build có thể đi qua nhiều ranh giới trước khi chạy: pipeline, kho artifact, mirror, hệ thống promote, cache, máy triển khai và runtime. Nếu chỉ kiểm tra tên file hoặc tag, bên nhận có thể dùng nội dung khác với nội dung đã được chấp nhận.

Code signing hỗ trợ xác thực nguồn ký và phát hiện sửa đổi đối với nội dung được bảo vệ. Giá trị đó phụ thuộc vào việc bên nhận xác minh đúng chữ ký, đúng nội dung và đúng mô hình tin cậy. [NIST: Security Considerations for Code Signing](https://nvlpubs.nist.gov/nistpubs/CSWP/NIST.CSWP.01262018.pdf)

Trong đặc tả yêu cầu bảo mật, câu “artifact phải được ký” cần được phát triển thành:

**Artifact nào → ký nội dung gì → ai có quyền ký → tin cậy được thiết lập từ đâu → xác minh tại đâu → hành vi khi lỗi → bằng chứng nào được lưu.**

Sau bài học, người học có thể:

- Phân biệt kiểm tra mật mã, xác minh danh tính và quyết định cho phép sử dụng.
- Đặc tả subject, digest, phạm vi chữ ký và nguồn policy.
- Chọn mô hình quản lý khóa hoặc ký theo danh tính cùng ranh giới tin cậy.
- Viết yêu cầu cho ký, phân phối, promote, deploy, thu hồi và rollback.
- Chuyển các tình huống thay thế, phát lại, sai danh tính và lỗi phụ trợ thành tiêu chí kiểm thử.

Các định danh, policy, thời hạn và digest trong bài là ví dụ thiết kế. Chúng cần được xác nhận theo mô hình đe dọa và kiến trúc của dự án.

## 2. Chữ ký chứng minh điều gì và còn thiếu điều gì?

### 2.1. Các khái niệm cần tách biệt

| Khái niệm | Vai trò | Điều không được tự suy ra |
|---|---|---|
| Digest | Dấu vân tay nội dung theo thuật toán xác định | Digest lấy từ cùng nguồn bị chiếm không tự chứng minh nhà phát hành |
| Chữ ký số | Ràng buộc nội dung được ký với khóa xác minh tương ứng | Khóa đó có được phép phát hành sản phẩm này hay không |
| Certificate hoặc danh tính khóa đã đăng ký | Hỗ trợ gắn khóa với một danh tính theo mô hình tin cậy | Danh tính đã được cấp quyền ký mọi namespace và môi trường |
| Trust policy | Quy định nguồn ký, loại bằng chứng, thuật toán và điều kiện được chấp nhận | Artifact không có lỗi hoặc mã độc |
| Provenance | Mô tả nguồn và quá trình tạo artifact theo phạm vi bằng chứng | Mọi khai báo đều đúng nếu chưa kiểm tra người tạo và tính toàn vẹn |
| SBOM | Mô tả thành phần của subject theo phạm vi công bố | Có SBOM là đã xác minh chữ ký của artifact |
| Phê duyệt phát hành | Quyết định cho phép dùng artifact trong một phạm vi | Nội dung thực tế vẫn đúng nếu đường triển khai tải lại bằng tag khác |
| TLS | Bảo vệ một kết nối và xác thực đối tác theo cấu hình | Mọi artifact tại máy chủ đó đều đã được nhà phát hành được cấp ký |

Không mô tả chữ ký số như “mã hóa bằng private key”. Cần dùng cơ chế chữ ký, thư viện và định dạng đã được lựa chọn theo crypto profile của dự án, với đúng quy tắc xác minh.

### 2.2. Ba câu hỏi khác nhau trong một quyết định chấp nhận

Một verifier phải trả lời riêng:

1. **Nội dung có khớp không?** Những byte hoặc cấu trúc được bảo vệ có đúng subject được yêu cầu không?
2. **Nguồn ký có được xác minh không?** Chữ ký, khóa, certificate chain và bằng chứng liên quan có hợp lệ theo profile không?
3. **Nguồn ký có được cấp quyền ở đây không?** Danh tính đó có được ký loại artifact, sản phẩm và mục đích sử dụng này theo policy hiện hành không?

Một người bất kỳ có certificate hợp lệ vẫn không được tự động ký bản production cho dịch vụ tài liệu. Tương tự, chữ ký hợp lệ của một sản phẩm khác không trở thành bằng chứng phát hành chỉ vì artifact nằm trong cùng registry.

“Chữ ký hợp lệ” cũng không đồng nghĩa “được phép deploy hôm nay”. Artifact cũ có thể đã bị chặn; quyền signer có thể đã thay đổi; bằng chứng phát hành có thể không áp dụng cho môi trường đang yêu cầu.

### 2.3. Phạm vi bảo vệ phụ thuộc định dạng

Đặc tả phải xác định đang dùng:

- Chữ ký tách rời trên blob hoặc digest được ràng buộc theo định dạng đã chọn.
- Chữ ký trên manifest của image hoặc một cấu trúc mô tả artifact.
- Chữ ký nội tại của package, chẳng hạn cơ chế ký JAR.
- Chữ ký trên một statement chứa subject digest cùng provenance hoặc phê duyệt.

Không coi chữ ký trên SBOM là chữ ký trực tiếp của file JAR. Một statement đã xác minh có thể ràng buộc tới JAR thông qua subject digest, nhưng phải kiểm tra liên kết ấy.

Với JAR ký nội tại, cần kiểm tra phạm vi entry, certificate, thuật toán và cảnh báo theo công cụ tương ứng. Tài liệu jarsigner nêu trường hợp entry chưa ký và các cảnh báo nghiêm trọng; việc công cụ trả thành công ở chế độ mặc định không thay thế policy chấp nhận. [Oracle: The jarsigner Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jarsigner.html)

Trong tình huống chính của bài, ứng dụng dùng chữ ký tách rời gắn với digest của **file JAR cuối cùng**, sau mọi bước làm thay đổi byte. Đây là lựa chọn của ví dụ, không phải quy tắc cho mọi định dạng ký.

## 3. Mô hình đe dọa và phạm vi áp dụng

Xét dịch vụ tài liệu có pipeline build được quản lý, kho artifact, hệ thống promote và các môi trường production. Artifact sau đóng gói được xác định bằng digest bất biến.

Tài sản cần bảo vệ gồm code được thực thi, quyền ký, policy tin cậy, bằng chứng xác minh và dữ liệu mà workload có thể truy cập.

| Mã rủi ro | Tình huống | Điều kiện cần đặc tả |
|---|---|---|
| R-SIG-01 | Artifact bị thay trong kho, cache hoặc đường phân phối | Kiểm tra nội dung đối với subject được ký |
| R-SIG-02 | Chữ ký hợp lệ nhưng của signer không được cấp quyền | Ánh xạ danh tính tới sản phẩm, namespace và mục đích |
| R-SIG-03 | Lấy chữ ký/bằng chứng của artifact A để dùng cho B | Ràng buộc subject và kiểm tra digest thực tế |
| R-SIG-04 | Tag đổi sau xác minh hoặc file bị sửa trước thực thi | Giữ định danh bất biến và kiểm soát khoảng cách giữa kiểm tra với sử dụng |
| R-SIG-05 | Khóa, danh tính CI hoặc dịch vụ ký bị chiếm | Phạm vi quyền ký, cô lập và ứng phó thu hồi |
| R-SIG-06 | Artifact cũ còn chữ ký hợp lệ được phát lại | Policy chống dùng bản đã bị chặn và kiểm tra phê duyệt hiện hành |
| R-SIG-07 | Lỗi verifier hoặc mất dịch vụ phụ trợ làm bỏ kiểm tra | Hành vi không cấp quyền mới khi chưa đủ bằng chứng |
| R-SIG-08 | Policy hoặc trust root bị đổi trái phép | Nguồn có thẩm quyền, phiên bản, audit và chống khôi phục policy lỗi thời |
| R-SIG-09 | Chỉ lưu kết quả “PASS”, mất bằng chứng | Dữ liệu phục vụ điều tra và tái xác minh |
| R-SIG-10 | Thời gian hoặc trạng thái cache bị dùng sai | Nguồn thời gian, hiệu lực và độ mới của quyết định quyền |

Tác nhân không chỉ là người sửa registry. Một build step không tin cậy có thể xin ký nội dung tùy ý; một người vận hành có thể chọn nhầm signer; pipeline bị chiếm có thể tạo artifact độc hại rồi ký đúng quy trình.

Do đó cần nêu giới hạn: chữ ký giúp ràng buộc nội dung với nguồn ký theo policy, nhưng không tự đánh giá tính an toàn của code. Kiểm soát source, build, dependency và kiểm thử vẫn có trách nhiệm riêng.

## 4. Chọn mô hình ký và ranh giới tin cậy

### 4.1. Khóa do tổ chức quản lý

Một mô hình sử dụng khóa ký dài hạn được quản lý trong KMS, HSM hoặc hệ thống bảo vệ khóa phù hợp. Bên xác minh nhận public key hoặc chain theo một kênh quản lý tin cậy.

Yêu cầu cần chỉ rõ:

- Khóa nào có quyền ký namespace nào; định danh phiên bản khóa không bị mất khi rotation.
- Workload nào được yêu cầu thao tác ký và bằng chứng xác thực của workload.
- Nội dung nào dịch vụ ký được phép chấp nhận, dựa trên kết quả build đã được xác nhận.
- Quyền dùng khóa khác với quyền sửa policy tin cậy hoặc cấp quyền cho signer.
- Private key không đi vào repository, log, image hoặc môi trường build không được cấp.
- Cách lưu, xoay vòng, ngừng dùng và ứng phó khi nghi khóa bị lộ.

Giữ khóa trong HSM không tự ngăn kẻ có quyền gọi dịch vụ ký ký một artifact độc hại. Dịch vụ phải kiểm soát yêu cầu ký, không chỉ bảo vệ vật liệu khóa.

Public key tải cạnh artifact từ một nguồn không có cơ chế xác thực độc lập không tự tạo trust root. Bên thay artifact có thể thay luôn public key nếu cả hai cùng được tin chỉ vì cùng URL.

### 4.2. Ký theo danh tính với khóa ngắn hạn

Trong mô hình keyless của Sigstore, khóa tạm được gắn với danh tính thông qua certificate ngắn hạn; hệ thống còn có các thành phần cung cấp bằng chứng và cơ chế phân phối trust root. “Keyless” vẫn sử dụng khóa mật mã, đồng thời chuyển trọng tâm quản lý sang danh tính và hạ tầng tin cậy. [Sigstore: Signing overview](https://docs.sigstore.dev/cosign/signing/overview/)

Đặc tả bên nhận cần định nghĩa:

- Certificate authority và trust root được chấp nhận.
- Issuer của danh tính cùng giá trị identity cần khớp.
- Claim nào đã được xác thực, claim nào chỉ là metadata do người gửi tự cung cấp.
- Phạm vi quyền ký của identity đối với sản phẩm và loại phát hành.
- Bằng chứng thời gian và transparency được yêu cầu theo profile.
- Cách xử lý khi danh tính CI, issuer hoặc thành phần trust bị nghi xâm nhập.

Không chỉ kiểm tra certificate có chain hợp lệ. Ví dụ, verifier Sigstore có các điều kiện riêng cho certificate identity và OIDC issuer; dự án phải cấu hình giá trị mong đợi phù hợp, không chấp nhận mọi identity thuộc một issuer rộng. [Sigstore: Verifying signatures](https://docs.sigstore.dev/cosign/verifying/verify/)

Nếu identity đại diện cho workflow, cần hiểu chính xác các thuộc tính đã được nhà cung cấp danh tính xác thực. Không tin tên repository, branch hoặc workflow chỉ vì chúng xuất hiện trong một JSON chưa được ký hay chưa được đối chiếu.

### 4.3. Chọn policy có thẩm quyền, không lấy kỳ vọng từ artifact

Bên gửi có thể cung cấp signature và certificate để verifier kiểm tra, nhưng không được tự quyết định “hãy tin certificate này” hoặc “hãy bỏ qua identity”.

Một policy có thể do đội nền tảng và chủ sở hữu sản phẩm quản lý, phân phối bằng kênh được bảo vệ, có revision và thời hạn. Danh tính được cấp cho release thử nghiệm không được tự nâng thành signer production bằng một annotation do pipeline tự ghi.

Nếu yêu cầu hai vai trò xác nhận độc lập, cần định nghĩa hai role và danh tính được tính cho từng role. Hai bản chữ ký từ cùng một nguồn không tự trở thành hai bên độc lập.

## 5. Viết bộ yêu cầu bảo mật đo được

### 5.1. Một yêu cầu đầy đủ

**SIG-01 — Xác minh trước khi promote hoặc deploy**

- **Rủi ro:** R-SIG-01, R-SIG-02, R-SIG-03 và R-SIG-04.
- **Phạm vi:** mọi JAR ứng dụng đi vào production qua các đường triển khai được quản lý.
- **Điều kiện:** sau khi lấy artifact ứng viên, trước khi promote hoặc cho phiên bản workload mới sử dụng.
- **Yêu cầu:** kiểm tra nội dung, bằng chứng chữ ký, nguồn ký được cấp và policy còn hiệu lực đối với chính digest của artifact đó.
- **Khi lỗi:** không promote hoặc khởi chạy phiên bản ứng viên; ghi mã lý do ổn định, không coi thiếu bằng chứng là cảnh báo có thể bỏ qua.
- **Kết quả:** quyết định gắn với subject digest, signer đã xác minh, policy revision và phạm vi sử dụng.
- **Tiêu chí chấp nhận:** thay một byte của JAR, dùng signature của file khác hoặc signer ngoài phạm vi đều bị từ chối.
- **Giới hạn:** chữ ký hợp lệ vẫn phải đi cùng các cổng phát hành khác được dự án quy định.

Một lệnh verify chạy thành công trên máy lập trình viên không chứng minh SIG-01 được thực thi tại đường deploy thực tế.

### 5.2. Yêu cầu bổ sung và bằng chứng

| ID | Hành vi bắt buộc trong baseline minh họa | Bằng chứng chấp nhận chính |
|---|---|---|
| SIG-02 | Mọi yêu cầu ký có danh tính được xác thực và được cấp đúng phạm vi artifact; không ký digest tùy ý từ caller vượt quyền. | Build thử ngoài scope không lấy được chữ ký production; có audit quyết định |
| SIG-03 | Subject và định dạng nội dung được ký được xác định rõ; dữ liệu bảo mật cần ra quyết định nằm trong phần được bảo vệ hoặc bằng chứng có thẩm quyền liên kết tới subject. | Không tráo tên sản phẩm, digest, statement hoặc metadata để đổi nghĩa quyết định |
| SIG-04 | Verifier chỉ chấp nhận thuật toán, kiểu bằng chứng và trust root thuộc crypto/trust profile được quản lý. | Thuật toán bị cấm, định dạng không hỗ trợ hoặc root tự cấp bị từ chối |
| SIG-05 | Identity đã xác minh phải khớp policy cho namespace, mục đích và môi trường; issuer hợp lệ một mình chưa đủ. | Cùng issuer nhưng sai identity hoặc signer chỉ được ký thử nghiệm không qua production |
| SIG-06 | Nội dung đã xác minh và nội dung được sử dụng phải là cùng subject bất biến. | Tag đổi hoặc artifact bị thay sau verify không làm workload chạy byte chưa được chấp nhận |
| SIG-07 | Bằng chứng thời gian, certificate và transparency được kiểm tra theo profile, không theo timestamp tự khai của người gửi. | Sửa timestamp, sai chain hoặc proof không hợp lệ làm kiểm tra thất bại |
| SIG-08 | Quyết định chấp nhận xét policy hiện hành, trạng thái chặn artifact/signer và phạm vi phê duyệt phát hành. | Artifact cũ có chữ ký hợp lệ nhưng bị chặn vẫn không được deploy lại |
| SIG-09 | Cache không cho phép bỏ kiểm tra quyền hiện hành; dữ liệu quá hạn không tạo quyền triển khai mới. | Cache crypto còn nhưng lease quyền hết hạn thì không cấp triển khai |
| SIG-10 | Mất verifier hoặc thiếu bằng chứng bắt buộc không chuyển sang cho phép; workload đang chạy có chính sách vận hành riêng. | Mất dịch vụ phụ trợ chặn ứng viên mới, không tự tắt hay thay mọi workload hiện hữu |
| SIG-11 | Thay đổi trust root, quyền signer và policy có phân quyền, audit, version và cơ chế chống rollback trái phép. | Sửa trái quyền hoặc nạp policy cũ đã bị thu hồi không thay trạng thái chấp nhận |
| SIG-12 | Rotation, nghi lộ khóa và thu hồi có quy trình thực thi cùng thời hạn đã thống nhất. | Dừng ký mới bằng nguồn bị chặn, tìm được artifact liên quan và kiểm tra lại các điểm sử dụng |
| SIG-13 | Kết quả ký/xác minh và bằng chứng được giữ để điều tra, khôi phục và tái đánh giá. | Từ deployment truy được digest, signer, policy revision, thời điểm và evidence ID |

Các mã SIG là định danh của bài học, không phải điều khoản của một tiêu chuẩn. Mỗi yêu cầu trong dự án cần chủ sở hữu, phiên bản, thành phần thực thi và liên kết tới ca kiểm thử.

## 6. Hợp đồng policy và quy trình xác minh

### 6.1. Policy mẫu cho JAR production

Ví dụ dưới đây là schema tự định nghĩa cho hệ thống minh họa, không phải file cấu hình có thể đưa trực tiếp cho Cosign hay một admission controller.

```yaml
schemaVersion: 1
revision: "artifact-trust-042"
targetEnvironment: production

artifact:
  namespace: documents-service
  subjectMode: final-blob-digest
  digestAlgorithm: SHA-256

verification:
  evidenceProfile: approved-keyless-bundle
  cryptoProfileRef: production-code-signing-v3
  trustRootSetRef: managed-signing-roots-07
  requireDigestMatch: true
  requireAuthorizedRelease: true
  requireProvenancePolicyMatch: true
  allowUnverifiedFallback: false

authorizedSigners:
  - issuer: "https://issuer.example.invalid"
    identity: "https://ci.example.invalid/org/documents/release"
    role: application-release
    artifactNamespace: documents-service

freshness:
  cryptoResultCacheMaxSeconds: 300
  authorizationLeaseMaxSeconds: 30
  withdrawalDeadlineSeconds: 60

audit:
  durableDecisionRequiredBeforeNewDeployment: true
```

Ý nghĩa của hợp đồng:

- `final-blob-digest` quy định subject là JAR đã hoàn tất đóng gói, sau mọi thao tác làm thay đổi byte.
- `cryptoProfileRef` trỏ tới tập thuật toán, định dạng và quy tắc xác minh được quản lý. Không để artifact tự chọn profile yếu hơn.
- `trustRootSetRef` là tham chiếu tới nguồn trust đã được kiểm soát; bản thân một tên tham chiếu không thay việc xác minh dữ liệu trust.
- `issuer` và `identity` là cặp giá trị minh họa cần khớp trên danh tính đã được xác thực.
- `requireAuthorizedRelease` yêu cầu phê duyệt phát hành còn hiệu lực gắn đúng digest; chữ ký artifact một mình không tạo phê duyệt.
- `requireProvenancePolicyMatch` là điều kiện riêng của ví dụ: provenance phải gắn đúng subject, được xác minh và khớp kỳ vọng build đã duyệt.
- Cận cache crypto không phải thời hạn quyền sử dụng. Quyền hiện hành còn được kiểm tra qua lease riêng có thời gian ngắn hơn.
- Việc deployment thực sự là production phải được đối chiếu từ ngữ cảnh triển khai có thẩm quyền; không chỉ tin field trong file ứng viên.

Việc xác minh provenance cần kiểm tra bằng chứng và các kỳ vọng như builder, nguồn và tham số build có ý nghĩa với sản phẩm. SLSA mô tả các bước này riêng với việc kiểm tra chữ ký envelope. [SLSA: Verifying artifacts](https://slsa.dev/spec/v1.2/verifying-artifacts)

Schema phải quy định field bắt buộc, miền giá trị, cách xử lý khóa trùng, sai kiểu và field không biết. Thiếu cấu hình trust không được chuyển thành “tin mọi signer”.

### 6.2. Thứ tự trách nhiệm của verifier

Một quy trình khái niệm:

```text
evaluateCandidate(request):
    context = authenticateAndAuthorizeDeploymentRequest(request)
    policy = loadCurrentTrustedPolicy(context)

    subject = resolveImmutableSubject(request.artifactReference)
    artifact = fetchAndCheckContentDigest(subject)

    evidence = loadRequiredEvidence(subject, policy)
    profile = selectApprovedEvidenceProfile(policy, evidence)
    cryptoResult = verifyCryptographicEvidence(artifact, evidence, profile)

    signer = extractVerifiedSignerIdentity(cryptoResult)
    requireSignerAuthorized(signer, subject, context, policy)
    requireSubjectBindingsMatch(cryptoResult, subject)
    requireTimeAndTransparencyRules(cryptoResult, policy)
    requireReleaseAndProvenanceRules(subject, evidence, context, policy)
    requireCurrentPermissionAndNoApplicableBlock(subject, signer, policy)

    persistDurableDecision(subject, signer, policy.revision, context)
    return permitBoundTo(subject, context, policy)
```

Đây là mã giả mô tả trách nhiệm, không hướng dẫn tự cài thuật toán mật mã. Công cụ/thư viện được lựa chọn phải xử lý đúng định dạng chữ ký và nội dung envelope.

Không parse một statement rồi tùy ý serialize lại để thay thế những byte mà cơ chế ký yêu cầu kiểm tra. Quy tắc encoding, canonicalization hoặc envelope phụ thuộc định dạng đã chọn và phải được thực thi nhất quán.

Nếu có nhiều signature, phải đánh giá tập bằng chứng theo policy, bao gồm role và danh tính độc lập nếu được yêu cầu. Không chọn tùy tiện chữ ký đầu tiên hoặc coi số lượng bản ghi là số bên xác nhận.

### 6.3. Kết quả cần có ý nghĩa rõ

Có thể phân loại kết quả như:

| Kết quả | Ví dụ nguyên nhân | Hành vi cho ứng viên mới |
|---|---|---|
| ACCEPT | Đủ bằng chứng và đáp ứng policy hiện hành | Chỉ cấp quyền cho đúng subject và phạm vi đã xét |
| REJECT | Digest sai, signer sai, artifact bị chặn | Không promote/deploy; có audit mã lý do |
| INDETERMINATE | Không lấy được bằng chứng, trust chưa đủ mới, verifier lỗi | Chưa cấp quyền mới; thử lại hoặc xử lý theo quy trình đã thiết kế |

Không đổi INDETERMINATE thành ACCEPT để tránh gián đoạn pipeline. Đồng thời cần phân biệt nguyên nhân để đội vận hành biết đang xử lý vi phạm policy hay lỗi hạ tầng.

## 7. Đặt điểm kiểm soát từ ký đến thực thi

### 7.1. Ký sau khi chốt nội dung cần bảo vệ

Quy trình của ví dụ:

```text
Build và kiểm tra theo policy
    -> Đóng gói JAR cuối
    -> Chốt digest và bằng chứng build
    -> Dịch vụ ký kiểm tra danh tính, phạm vi và subject
    -> Tạo signature/bundle theo profile
    -> Đưa artifact và bằng chứng vào trạng thái sẵn sàng phân phối
    -> Verifier xét policy trước promote/deploy
    -> Triển khai cùng digest đã được chấp nhận
```

Nếu cần thay nội dung JAR sau bước ký, đó là một subject mới cần được xử lý lại theo quy trình. Không giữ signature cũ rồi đổi nhãn để coi như cùng artifact.

Với định dạng nhúng chữ ký vào package, thứ tự và định nghĩa subject phải tuân theo cơ chế của định dạng. Không áp dụng máy móc quy trình ký blob lên một file tự thay đổi khi nhúng chữ ký.

### 7.2. Công bố artifact và bằng chứng như một đơn vị phát hành

Kho có thể lưu artifact, signature, certificate, bundle và provenance ở các object khác nhau. Hợp đồng phát hành phải xác định khi nào bộ dữ liệu được coi là sẵn sàng.

Trong baseline, một release chưa có đủ bằng chứng bắt buộc không được promote dù byte artifact đã upload thành công. Consumer không được dùng “signature chưa xuất hiện” làm lý do bỏ xác minh.

Signature bị mất có thể gây gián đoạn phân phối, nhưng không được làm lộ private key để tái tạo nhanh. Cần bảo vệ và sao lưu bằng chứng công khai phù hợp với mục tiêu phục hồi.

### 7.3. Giữ nguyên subject từ lúc kiểm tra tới lúc sử dụng

Giả sử `documents:release` trỏ tới digest A khi verify, sau đó tag đổi sang B trước khi deploy. Lệnh kiểm tra có thể đã đúng nhưng workload vẫn nhận B nếu hệ thống tải lại bằng tag.

Đặc tả phải yêu cầu truyền tiếp định danh bất biến A, hoặc kiểm tra lại chính nội dung thực tế sẽ được dùng bằng cơ chế tương đương. Audit deployment phải ghi digest thực tế, không chỉ tag.

Với file JAR, cần tránh việc một chủ thể không được cấp sửa file giữa kiểm tra và khởi chạy. Các lựa chọn kiến trúc có thể gồm object theo nội dung, quyền ghi bị giới hạn hoặc chuyển giao file được bảo vệ; lựa chọn nào cũng phải có bằng chứng kiểm thử.

Chữ ký của image manifest hoặc index không tự xác minh mọi chữ ký độc lập của component con. Nếu policy chấp nhận quan hệ ràng buộc qua digest trong manifest, phải kiểm tra chuỗi liên kết nội dung đó và giới hạn platform tương ứng.

Bảo vệ sau khởi chạy cũng có phạm vi riêng. Nếu process có thể tự tải code tùy ý hoặc thư mục ứng dụng cho phép sửa, chữ ký gói ban đầu không đủ chứng minh toàn bộ code đang thực thi vẫn thuộc baseline.

## 8. Thời gian, certificate, transparency và cache

### 8.1. Đừng dùng đồng hồ tự khai làm bằng chứng ký

Field `signedAt` do người gửi ghi có thể chỉ là một lời khai. Để quyết định chữ ký có được tạo trong khoảng hiệu lực certificate hay không, cần cơ chế thời gian được profile tin cậy và kiểm tra liên kết với chữ ký/bằng chứng.

Sigstore mô tả xác minh certificate ngắn hạn dựa trên bằng chứng thời gian phù hợp, gồm timestamp từ nguồn được chấp nhận. Certificate hết hạn ở hiện tại không tự khiến mọi chữ ký cũ thất bại; verifier phải áp dụng đúng quy tắc thời gian của mô hình ký. [Sigstore: Timestamps](https://docs.sigstore.dev/cosign/verifying/timestamps/)

Ngược lại, một timestamp được xác minh không tự tạo quyền deploy hiện tại. Nó hỗ trợ kết luận theo thời điểm ký; trạng thái chặn, quyền signer và phê duyệt sử dụng vẫn phải được xét riêng.

Không mặc định việc thu hồi certificate được mọi công cụ xử lý giống nhau. Policy phải xác định nguồn trạng thái, quy tắc hiệu lực theo thời gian và hành vi khi không xác minh được thông tin cần thiết.

### 8.2. Transparency không phải phê duyệt phát hành

Transparency giúp cung cấp bằng chứng và khả năng kiểm toán các sự kiện theo mô hình triển khai. Nó không chứng minh artifact lành tính, đã được đội sản phẩm chấp thuận hoặc signer không bị xâm nhập.

Nếu profile yêu cầu log inclusion, checkpoint hoặc timestamp, cần xác minh loại bằng chứng tương ứng với khóa/root được tin cậy. Không chỉ kiểm tra tồn tại một log URL hoặc entry ID.

Một lời hứa đưa vào log và bằng chứng bao hàm đã được kiểm tra là hai loại bằng chứng khác nhau; không tự dùng chúng thay nhau nếu policy chưa cho phép. Cần chọn rõ profile được công cụ hỗ trợ và mức bảo đảm mong muốn.

Metadata công bố trong log có thể tiết lộ danh tính signer hoặc thông tin artifact. Đội thiết kế cần xác định dữ liệu nào được phép công khai, thay vì gửi secret hoặc thông tin nội bộ không cần thiết vào bằng chứng.

### 8.3. Offline verification vẫn cần trust và policy

Bundle có thể hỗ trợ giữ chữ ký, certificate và bằng chứng để xác minh mà không cần gọi lại mọi dịch vụ tại mỗi lần sử dụng. Tuy nhiên, khả năng offline của một định dạng không tự quyết định policy chấp nhận của dự án.

Cần có trust root được cấp qua kênh tin cậy, đúng phiên bản công cụ/profile và đủ bằng chứng. Không lấy root do artifact tự đính kèm làm root được tin chỉ vì bundle parse thành công.

Xác minh crypto offline thành công có thể vẫn chưa đủ để deploy mới nếu chưa biết trạng thái thu hồi hoặc lease quyền đã hết. Đây là khác biệt giữa “có thể kiểm tra chữ ký từ dữ liệu cục bộ” và “đủ điều kiện cấp quyền sử dụng hiện tại”.

### 8.4. Cache chỉ được tái sử dụng đúng kết luận

Trong ví dụ, cache 300 giây chỉ dành cho phần kết quả crypto có đầu vào bất biến và được khóa theo ít nhất:

- Subject digest.
- Định danh/digest của bộ bằng chứng.
- Profile và phiên bản verifier có ảnh hưởng.
- Bộ trust và phiên bản quy tắc xác minh liên quan.

Một kết quả crypto không phải vé deploy dùng lại vô điều kiện. Quyết định quyền hiện hành cần lease tối đa 30 giây và bị giới hạn theo subject, signer, môi trường cùng policy revision.

Cam kết thu hồi 60 giây đòi hỏi cận tổng cho lease, sai số thời gian, độ trễ thực thi và các điểm còn phục vụ policy cũ. Chỉ đặt polling 60 giây không đủ chứng minh đáp ứng.

Restart không được đặt lại thời hạn của lease. Khi mất nguồn xác nhận và lease hết, không cấp deployment mới. Những giá trị thời gian trên là lựa chọn minh họa cần chứng minh bằng kiến trúc và kiểm thử.

## 9. Rotation, thu hồi và phục hồi sau xâm nhập

### 9.1. Phân biệt rotation bình thường với sự cố

Rotation bình thường thay khóa hoặc trust material theo kế hoạch. Sự cố yêu cầu đánh giá xem khóa hoặc danh tính đã bị lạm dụng trong khoảng nào.

| Tình huống | Quyết định cần có |
|---|---|
| Đổi khóa định kỳ | Khoảng chuyển tiếp, người được cấp khóa mới và cách giữ bằng chứng cũ |
| Private key nghi bị lộ | Dừng quyền ký, cô lập nguồn, rà các signature và artifact liên quan |
| Danh tính CI bị chiếm | Thu hồi quyền phát hành, xử lý phiên/token và điều tra workflow sử dụng |
| Artifact cụ thể bị xác định độc hại | Chặn subject đó, tìm deployment liên quan và kích hoạt phương án xử lý |
| Trust root không còn được chấp nhận | Phân phối policy mới có thẩm quyền, giới hạn sử dụng và kiểm chứng hội tụ |
| Mất khóa nhưng chưa có bằng chứng bị lộ | Khôi phục năng lực ký bằng quy trình được cấp; không thay artifact hoặc bằng chứng cũ âm thầm |

Giữ public key hoặc thông tin xác minh lịch sử có thể cần thiết để điều tra chữ ký cũ. Việc giữ chúng không đồng nghĩa tiếp tục cấp quyền deploy cho mọi chữ ký từ nguồn đó.

Không mặc định “mọi chữ ký trước thời điểm phát hiện đều an toàn”. Cần dựa vào khoảng thời gian xâm nhập có thể xảy ra và bằng chứng điều tra. Một timestamp chỉ có ích trong giới hạn nguồn thời gian và mô hình tin cậy của nó.

### 9.2. Thu hồi phải đi tới điểm ra quyết định

Một danh sách signer bị chặn trong tài liệu không tự có hiệu lực tại verifier. Phải phân phối tới mọi nơi promote, deploy hoặc cài đặt được hỗ trợ.

Với thời hạn 60 giây của ví dụ, mốc bắt đầu là khi dịch vụ quản lý policy chấp nhận lệnh thu hồi. Mọi yêu cầu triển khai mới sau mốc cộng 60 giây phải dùng policy còn hiệu lực hoặc bị chặn.

Điểm bị cô lập không thể tự biết một lệnh thu hồi mới. Cơ chế lease, cô lập hoặc từ chối cấp quyền khi thiếu độ mới phải bảo đảm cận đã cam kết.

Đối với workload đã chạy, cần quyết định ứng phó riêng: tiếp tục có giám sát, hạn chế kết nối, cô lập hoặc thay thế. Không tự đồng nhất lỗi dịch vụ xác minh với bằng chứng code hiện hữu bị xâm nhập.

### 9.3. Rollback cũng là một lần cấp quyền sử dụng

Artifact cũ từng có signature hợp lệ vẫn phải được đánh giá bằng policy hiện hành khi triển khai lại. Rollback không được khôi phục artifact hoặc signer đã bị chặn chỉ vì đó là “bản trước”.

Nếu cần đường phát hành khẩn cấp, thiết kế trước danh tính, quyền, phạm vi, thời hạn và audit cho đường đó. Không có ngoại lệ tự cho phép bỏ kiểm tra digest hay coi chữ ký sai là đúng.

Sau khi xử lý sự cố, cần thử lại toàn bộ chuỗi: quyền ký mới, phân phối trust, xác minh, promote, deploy và truy vấn bằng chứng. Chỉ tạo khóa mới chưa chứng minh hệ thống đã ngừng tin nguồn bị chiếm.

## 10. Audit và liên kết tới kiến trúc

### 10.1. Sự kiện nào cần được ghi?

Các sự kiện có thể gồm yêu cầu ký, kết quả ký, công bố bằng chứng, xác minh, từ chối, promote, deploy, thay đổi policy, rotation và thu hồi.

Một bản ghi quyết định triển khai nên có:

| Field khái niệm | Mục đích |
|---|---|
| Subject digest và loại artifact | Xác định nội dung được xét |
| Sản phẩm, môi trường và caller | Xác định phạm vi yêu cầu |
| Signer đã xác minh | Đối chiếu danh tính được policy chấp nhận |
| Evidence ID/digest | Tìm đúng bằng chứng đã dùng |
| Policy/trust revision | Tái dựng quy tắc và nguồn tin cậy tại thời điểm quyết định |
| Thời gian và mã kết quả | Phân biệt lỗi nội dung, quyền, thời gian hay hạ tầng |
| Deployment/build ID | Liên kết quyết định với lần sử dụng thực tế |

Không log private key, identity token, credential KMS hoặc secret triển khai. Dữ liệu lấy từ artifact như tên, path và annotation cần được kiểm tra độ dài/định dạng trước khi đưa vào log.

Baseline yêu cầu ghi quyết định bền vững trước khi cho deployment mới dùng artifact. Nếu sink tập trung lỗi, có thể dùng cơ chế bền vững được thiết kế trước; không bỏ audit âm thầm.

Kết quả “đã cho phép” không tự chứng minh workload đã khởi chạy. Cần liên kết thêm sự kiện triển khai thực tế và digest được quan sát.

### 10.2. Thành phần nào thực thi yêu cầu?

| Thành phần kiến trúc | Trách nhiệm |
|---|---|
| Nền tảng build | Chốt output và bằng chứng theo phạm vi; kiểm soát nguồn được yêu cầu ký |
| Dịch vụ ký | Xác thực caller, kiểm tra scope và bảo vệ năng lực ký |
| Kho artifact | Phân phối nội dung và bằng chứng, giữ định danh bất biến đã công bố |
| Dịch vụ policy/trust | Cấp và thu hồi quyền signer, quản lý trust material có phiên bản |
| Verifier/cổng triển khai | Kiểm tra bằng chứng và policy trước cấp quyền sử dụng |
| Cơ chế deploy/runtime | Dùng đúng subject, ngăn sửa hoặc thay thế ngoài hợp đồng |
| Kho audit và inventory | Liên kết signer → artifact → release → deployment để điều tra |

Nếu đường triển khai thủ công hoặc tải plugin bỏ qua verifier, cần chặn đường đó hoặc đưa nó vào cùng hợp đồng. Kiểm tra trên đường chính không bao phủ tự động các đường phụ.

## 11. Kế hoạch kiểm thử theo tình huống đe dọa

Không cần mọi ca là kiểm thử đầu cuối. Các trường hợp signature hỏng phù hợp với kiểm thử verifier; thay tag, quyền ký, thu hồi và deploy phải có kiểm thử tích hợp hoặc môi trường đại diện.

| Ca | Đầu vào hoặc tác động | Kết quả chấp nhận |
|---|---|---|
| T01 | Artifact và bộ bằng chứng hợp lệ, signer đúng scope, quyền hiện hành còn hiệu lực | Được chấp nhận cho đúng digest/môi trường; audit liên kết tới deployment |
| T02 | Sửa một byte JAR cuối | Bị từ chối, không promote hoặc khởi chạy ứng viên |
| T03 | Dùng signature hoặc statement của artifact A cho B | Thất bại kiểm tra nội dung/subject binding |
| T04 | Chữ ký đúng mật mã nhưng signer không được cấp | Bị từ chối theo policy, không chỉ báo crypto thành công |
| T05 | Cùng issuer nhưng sai identity, sai namespace hoặc chỉ có quyền thử nghiệm | Không qua production |
| T06 | Root/public key do người gửi tự đưa vào nhưng chưa được cấp | Không được dùng làm nguồn trust có thẩm quyền |
| T07 | Thuật toán hoặc evidence profile không được hỗ trợ/cấp | Bị từ chối; không hạ xuống kiểu kiểm tra yếu hơn |
| T08 | Sửa timestamp hoặc cung cấp proof không hợp lệ theo profile | Không đáp ứng bằng chứng thời gian/transparency bắt buộc |
| T09 | Certificate đã hết hạn hiện tại nhưng có bằng chứng thời gian hợp lệ trong khoảng ký | Đánh giá theo đúng profile; vẫn cần quyền sử dụng hiện hành và các điều kiện khác |
| T10 | Tag đổi A thành B giữa verify và deploy | Chỉ A đã được chấp nhận được dùng, hoặc B phải qua kiểm tra mới |
| T11 | File đã verify bị sửa trước lúc khởi chạy | Không chạy byte thay thế chưa được chấp nhận |
| T12 | Caller ngoài scope xin dịch vụ ký một digest tùy ý | Không tạo signature production; có audit từ chối |
| T13 | Mất dịch vụ lấy bằng chứng/trust hoặc verifier timeout | Không cấp quyền ứng viên mới khi chưa đủ dữ liệu; không fallback bỏ kiểm tra |
| T14 | Cache crypto còn nhưng lease quyền hết hoặc subject/signer bị chặn | Không dùng cache để cấp deployment |
| T15 | Thu hồi rồi cô lập một điểm verifier, thử restart với cache cũ | Không cấp yêu cầu mới quá thời hạn cam kết; restart không đặt lại lease |
| T16 | Rollback về artifact đã bị chặn nhưng còn signature hợp lệ | Bị từ chối theo policy hiện hành |
| T17 | Thay đổi policy trái quyền hoặc phát lại revision đã bị thu hồi | Không đổi tập quyết định được chấp nhận |
| T18 | Mất artifact evidence hoặc kho audit trước promote/deploy | Không báo đủ điều kiện; khôi phục theo hợp đồng mà không lộ vật liệu ký |
| T19 | Policy yêu cầu hai role độc lập nhưng có hai bản ký từ cùng nguồn | Không đáp ứng điều kiện độc lập |
| T20 | Với profile JAR ký nội tại, thêm entry chưa ký hoặc phát sinh cảnh báo bị policy cấm | Không chỉ dựa dòng thông báo thành công hoặc exit code mặc định để chấp nhận |

T09 không đặt quy tắc rằng mọi signature quá khứ đều được chấp nhận. Nó kiểm tra hệ thống hiểu đúng chứng cứ thời gian, còn kết quả deploy phụ thuộc policy hiện hành.

T15 cần đo từ thời điểm lệnh thu hồi được chấp nhận và bao phủ mọi đường có thể cấp quyền. Chỉ kiểm tra một verifier khỏe không chứng minh cả hệ thống đáp ứng.

### 11.1. Ví dụ Given–When–Then

```gherkin
Given production chỉ chấp nhận artifact của namespace documents-service
And identity release được cấp đã ký artifact A
And chữ ký và digest của A đều hợp lệ
And subject digest A đã bị chặn trong policy hiện hành
When người vận hành đề nghị rollback production về A
Then cổng triển khai từ chối yêu cầu
And không dùng kết quả verify crypto cũ để cấp quyền
And không khởi chạy workload ứng viên từ A
And audit ghi digest, policy revision, caller và mã ARTIFACT_BLOCKED
```

Ca dương tương ứng cần chứng minh một artifact chưa bị chặn, có đầy đủ bằng chứng và quyền phù hợp thực sự đi qua cổng. Một hệ thống từ chối tất cả không đáp ứng nhu cầu phát hành an toàn.

## 12. Bài tập: sửa yêu cầu “có chữ ký là được deploy”

Một nhóm mô tả quy trình:

> CI ký file sau build. Máy triển khai tải public key từ cạnh file, chạy verify, rồi deploy image theo tag release. Nếu verifier không kết nối được thì bỏ kiểm tra để khôi phục dịch vụ.

Hãy xác định các điểm thiếu và viết lại thành yêu cầu có thể kiểm chứng:

1. Ai có quyền ký và nguồn nào thiết lập trust?
2. Chữ ký bảo vệ chính xác JAR, image, manifest hay statement nào?
3. Bằng chứng xác minh có áp dụng đúng subject thực tế sẽ chạy không?
4. Policy xét signer, namespace, môi trường và phê duyệt ra sao?
5. Thời gian, certificate và proof được đánh giá theo profile nào?
6. Mất dịch vụ phụ trợ, cache cũ, thu hồi và rollback được xử lý thế nào?
7. Dữ liệu nào đủ để tìm mọi deployment dùng artifact từ nguồn ký bị xâm nhập?

Một hướng đặc tả là cấp quyền ký theo workload được xác thực; phân phối trust qua kênh được quản lý; kiểm tra bằng chứng cho subject bất biến; chỉ deploy đúng digest đã được chấp nhận; giữ kiểm tra quyền hiện hành riêng với cache crypto; không cấp ứng viên mới khi thiếu điều kiện bắt buộc.

Chuỗi truy vết mẫu:

| Mắt xích | Nội dung |
|---|---|
| Rủi ro | R-SIG-04: nội dung được dùng khác nội dung đã xác minh |
| Yêu cầu | SIG-01, SIG-03 và SIG-06 |
| Kiến trúc | Bộ phân giải subject, verifier và cơ chế deploy bằng định danh bất biến |
| Kiểm thử | T02, T03, T10 và T11 |
| Bằng chứng vận hành | Digest trong quyết định chấp nhận khớp digest của deployment thực tế |

Sản phẩm cần đạt là hợp đồng về quyền ký và quyền sử dụng: kiểm tra nội dung nào, tin nguồn nào, cho phép trong phạm vi nào và làm sao chứng minh quyết định còn đúng khi xảy ra thay thế, mất kết nối hoặc thu hồi.
