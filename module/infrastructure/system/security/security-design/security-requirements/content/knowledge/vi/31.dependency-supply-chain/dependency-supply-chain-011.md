# Container image security — Đặc tả yêu cầu bảo mật cho image container

## 1. Mục tiêu và phạm vi

Container image đóng gói mã ứng dụng, thư viện, môi trường chạy và metadata cần thiết để tạo container. Khi triển khai image, hệ thống tiếp nhận cả phần mềm do nhóm phát triển tạo ra lẫn các thành phần từ base image, package repository và quy trình build.

Một image có thể khởi động đúng chức năng nhưng vẫn chứa credential, dependency không được chấp thuận, công cụ không cần thiết hoặc mã khác với mã đã qua kiểm tra. Quyền kiểm soát image vì thế có thể trở thành quyền đưa mã vào môi trường production.

Trong chương **Dependency và supply chain**, bài học này chuyển các rủi ro đó thành yêu cầu bảo mật cụ thể, đo được và có thể kiểm chứng. Trọng tâm là liên kết yêu cầu với mô hình đe dọa, kiến trúc build, registry, xác thực nguồn, phân quyền phát hành, dữ liệu nhạy cảm, logging, kiểm thử và phục hồi.

Sau bài học, người học có thể:

- Xác định image cùng digest và nền tảng cụ thể cần được bảo vệ.
- Đặc tả yêu cầu cho base image, build, scanning, chữ ký và bằng chứng nguồn gốc.
- Thiết kế kiểm soát registry, promotion và quyết định cho phép triển khai.
- Phân biệt thuộc tính của image với chính sách thực thi tại runtime.
- Truy vết image có rủi ro tới các workload đang sử dụng và xác định bằng chứng phục hồi.

Tên hệ thống, policy và ngưỡng trong bài là ví dụ học tập. Dự án cần điều chỉnh theo dữ liệu, mức rủi ro và khả năng của công cụ thực tế.

## 2. Xác định đúng đối tượng cần kiểm chứng

### 2.1. Image không chỉ là một tên và tag

Một image thường liên quan tới manifest, cấu hình và các layer. Với image nhiều nền tảng, một index hoặc manifest list tham chiếu các manifest con cho những nền tảng khác nhau.

Các dạng định danh cần được phân biệt:

| Định danh hoặc thành phần | Ý nghĩa | Giới hạn cần lưu ý |
| --- | --- | --- |
| Repository và tag | Tên dễ dùng để tìm hoặc phát hành image | Tag có thể trỏ sang nội dung khác nếu không bị kiểm soát |
| Digest manifest | Nhận diện nội dung manifest theo thuật toán tương ứng | Không tự xác thực ai tạo image hoặc image có an toàn không |
| Digest index nhiều nền tảng | Ràng buộc nội dung index và các tham chiếu manifest con | Không chứng minh mọi nền tảng đã được quét hoặc được kiểm thử |
| Cấu hình image | Metadata như user mặc định, lệnh chạy và môi trường | Nhiều thuộc tính có thể bị ghi đè lúc triển khai |
| Các layer | Các thay đổi filesystem được đóng gói | File đã xóa ở layer sau vẫn có thể nằm trong layer trước |

Yêu cầu phải nói rõ digest thuộc loại đối tượng nào. Không so sánh một digest cấu hình với digest manifest rồi kết luận image đã bị thay chỉ vì chuỗi khác nhau.

### 2.2. Tag cố định và nội dung cố định khác nhau

Tag như `payment:release-42` có thể hữu ích cho con người, nhưng tên đó chưa đủ làm bằng chứng nội dung. Nếu tag bị ghi đè giữa lúc quét và lúc pull, image thực tế có thể khác image đã được chấp thuận.

> **IMG-ID-01:** Quyết định phát hành và triển khai phải ràng buộc với định danh nội dung của image. Workload phải sử dụng đúng nội dung đã được đánh giá, không chỉ cùng một tag.

Nếu cho phép tag tại một bước nhập liệu, hệ thống cần phân giải sang digest theo quy trình kiểm soát và bảo đảm chính digest đó được đưa tới điểm thực thi. Chỉ kiểm tra tag tại thời điểm phê duyệt chưa loại được khoảng hở thay đổi sau đó.

### 2.3. Image đa nền tảng cần bằng chứng bao phủ đúng

Một index đã được ký có thể ràng buộc các digest con, nhưng bằng chứng quét cho một manifest con không tự bao phủ manifest khác. Hai nền tảng có thể chứa các package hoặc phiên bản khác nhau.

Yêu cầu cần xác định:

- Những nền tảng nào được phép.
- Manifest con tương ứng với từng nền tảng.
- Bằng chứng quét và kiểm thử áp dụng cho đối tượng nào.
- Cách ngăn node chọn biến thể chưa được chấp thuận.
- Cách liên kết quan sát runtime với manifest đã được quyết định.

Không dùng báo cáo của một nền tảng làm kết luận cho toàn bộ image đa nền tảng khi chưa có bằng chứng tương ứng.

## 3. Mô hình đe dọa xuyên suốt vòng đời

Giả sử dịch vụ thanh toán Java được build trong CI, lấy base image từ nguồn được phê duyệt, đẩy image vào registry nội bộ và triển khai qua hệ thống điều phối.

Các tài sản quan trọng gồm mã được chạy, credential build và registry, dữ liệu khách hàng, tính toàn vẹn của release cùng khả năng xác định instance nào đang dùng image nào.

| Giai đoạn | Đe dọa | Tác động |
| --- | --- | --- |
| Chọn đầu vào | Base image hoặc package bị thay | Mã không được chấp thuận đi vào sản phẩm |
| Build | Pipeline bị sửa hoặc mã không đáng tin đọc secret | Lộ credential, tạo image bị cài mã |
| Đóng gói | Secret, file nội bộ hoặc công cụ dư bị đưa vào layer | Rò rỉ và tăng khả năng khai thác |
| Lưu trữ | Tài khoản registry bị lấy hoặc tag bị ghi đè | Người triển khai lấy nội dung khác |
| Kiểm tra | Báo cáo quét gắn với tag cũ hoặc sai nền tảng | Chấp thuận nhầm image |
| Promotion | Image được build lại hoặc thay nội dung sau phê duyệt | Mất liên kết giữa bằng chứng và sản phẩm |
| Triển khai | Có đường bỏ qua policy hoặc dùng image chưa duyệt | Mã không đủ điều kiện chạy trong production |
| Runtime | Image được chạy với quyền lớn hoặc mount nhạy cảm | Tăng tác động khi ứng dụng bị xâm nhập |
| Phục hồi | Rollback sang image cũ đã bị thu hồi | Tái đưa rủi ro vào hệ thống |

Mô hình không chỉ xét tấn công bên ngoài. Sai Dockerfile, cấu hình pipeline hoặc thao tác ghi đè nhầm cũng có thể phá vỡ các giả định bảo mật.

### 3.1. Phân biệt bốn mức đảm bảo

- **Toàn vẹn:** nội dung khớp đối tượng mong đợi.
- **Nguồn gốc:** bằng chứng về ai tạo hoặc phát hành và trong bối cảnh nào.
- **Được chấp thuận:** nội dung thỏa policy hiện hành cho môi trường dự định.
- **Được chạy an toàn:** workload thực thi với quyền, mạng và dữ liệu đúng giới hạn.

Digest, chữ ký, scanning và runtime policy hỗ trợ các phần khác nhau. Không có một tín hiệu đơn lẻ thay thế toàn bộ bốn mức.

## 4. Yêu cầu cho base image và quy trình build

### 4.1. Chọn và quản lý base image

> **IMG-BASE-01:** Base image phải thuộc nguồn được phê duyệt, được nhận diện bằng nội dung và có chủ sở hữu theo dõi vòng đời. Thay đổi base image phải tạo bằng chứng đánh giá cho image ứng dụng mới.

Cần ghi nhận:

- Nguồn, digest và nền tảng.
- Những thành phần môi trường chạy cần thiết.
- Chính sách cập nhật và điều kiện không còn được hỗ trợ theo đánh giá của dự án.
- Chủ sở hữu và đường xử lý khi có thông báo rủi ro.
- Những image ứng dụng kế thừa base image đó.

Pin digest giúp cố định đầu vào nhưng cũng có thể giữ lại một base image cũ nếu không có quy trình cập nhật. Yêu cầu cần cả tính bất biến cho một lần build và vòng đời cập nhật có kiểm soát.

Image nhỏ hơn thường giúp giảm thành phần không cần thiết, nhưng kích thước nhỏ không tự chứng minh an toàn. Image không có shell vẫn có thể chứa ứng dụng lỗi hoặc dependency bị thay.

### 4.2. Bảo vệ môi trường build và danh tính pipeline

> **IMG-BUILD-01:** Chỉ pipeline và danh tính build được phê duyệt mới được phát hành image vào phạm vi production. Mã không đáng tin không được dùng credential ký, push hoặc truy cập dữ liệu production.

Cần phân biệt các ngữ cảnh như pull request chưa tin cậy, build nhánh đã được duyệt và phát hành chính thức. Một danh tính pipeline hợp lệ không có nghĩa mọi mã mà pipeline chạy đều đã được chấp thuận.

Yêu cầu nên bao gồm:

- Quyền tối thiểu cho builder và credential có vòng đời phù hợp.
- Giới hạn đích mạng cần thiết cho build.
- Kiểm soát thay đổi định nghĩa pipeline và cấu hình ký.
- Cô lập job hoặc miền tin cậy khi dùng cache và worker dùng chung.
- Xác minh dependency, plugin và công cụ build trước khi thực thi theo chính sách.
- Ghi nhận nguồn mã, đầu vào và phiên bản công cụ cần truy vết.

Không coi môi trường build là an toàn chỉ vì diễn ra trước production. Builder có thể nắm quyền đưa mã vào production và tiếp cận credential có giá trị.

### 4.3. Không đưa secret vào image hoặc lịch sử build

Các cách dễ gây lộ dữ liệu gồm copy toàn bộ repository, dùng secret qua tham số build không phù hợp hoặc ghi token trong lệnh có thể xuất hiện ở log và metadata.

Ví dụ thiết kế sai:

```dockerfile
COPY . /workspace
RUN rm -f /workspace/.env
```

Nếu file secret đã được đưa vào layer trước, xóa ở layer sau không bảo đảm nội dung biến mất khỏi image được phân phối.

> **IMG-SECRET-01:** Credential, khóa riêng và dữ liệu production không được tồn tại trong layer, cấu hình, history, label, artifact build hoặc log thuộc phạm vi phát hành. Cơ chế cấp secret cho build phải hạn chế việc lưu giữ và rò rỉ qua lệnh thực thi.

Cần kiểm soát build context bằng danh sách loại trừ phù hợp và tốt hơn là chỉ đưa những đầu vào cần thiết. Tuy vậy, một file ignore không thay thế kiểm tra sản phẩm cuối.

Cơ chế secret tạm thời của công cụ build có thể giảm nguy cơ lưu vào layer. Nó không ngăn một script không đáng tin in secret hoặc gửi ra mạng; quyền, mã chạy và mạng vẫn cần kiểm soát.

Multi-stage build giúp tách công cụ build khỏi runtime, nhưng secret còn có thể nằm trong cache, artifact trung gian hoặc log của builder. Chính sách cần bao phủ những nơi đó.

### 4.4. Giảm thành phần và quyền mặc định

Image runtime chỉ nên chứa thành phần phục vụ mục đích đã được phê duyệt. Các công cụ debug, package manager hoặc file mã nguồn không cần thiết cần được xem xét theo rủi ro và nhu cầu vận hành.

Yêu cầu có thể quy định:

- User mặc định không có đặc quyền không cần thiết.
- File thực thi và cấu hình quan trọng không cho người chạy ứng dụng sửa trái phép.
- Thư mục cần ghi được xác định rõ.
- Entrypoint và lệnh chạy không mở thêm dịch vụ ngoài dự kiến.
- Metadata không chứa dữ liệu nhạy cảm hoặc giá trị mặc định yếu.

Chạy non-root là một lớp giảm quyền; nó không tự giải quyết capability, namespace, mount hoặc quyền truy cập dịch vụ bên ngoài. Container root và host root cũng không thể được đánh đồng mà bỏ qua cấu hình runtime.

Nếu nền tảng dùng UID được cấp động, cần thiết kế quyền filesystem tương thích thay vì yêu cầu một UID cố định không phù hợp. Điều cần chứng minh là quyền thực tế đủ dùng và không vượt nhu cầu.

## 5. Kiểm kê và đánh giá image

### 5.1. Kiểm tra sản phẩm cuối cùng

> **IMG-SCAN-01:** Image phát hành phải có kết quả đánh giá gắn với đúng digest và nền tảng thuộc phạm vi. Kết quả phải đáp ứng chính sách về độ mới, mức rủi ro và ngoại lệ trước khi được phép triển khai.

Phạm vi đánh giá có thể gồm:

- Package hệ điều hành.
- Thư viện ứng dụng và thành phần đóng gói bên trong.
- Thành phần môi trường chạy.
- Dấu hiệu secret hoặc file ngoài danh mục.
- Cấu hình image và quyền mặc định.
- Bằng chứng mã hoặc nội dung không được chấp thuận theo khả năng công cụ.

Quét một thư mục mã nguồn không thay thế kiểm tra image đã đóng gói. Image cuối có thể thêm package, bỏ thành phần hoặc chứa artifact khác với dự kiến.

Với ứng dụng Java, cần xác định công cụ có nhận diện thư viện đóng gói, dependency lồng nhau và môi trường chạy trong phạm vi thực tế hay không. Không suy rộng khả năng quét từ một loại package sang mọi kiểu đóng gói.

### 5.2. Kết quả quét phải có ngữ cảnh

Một chính sách chỉ ghi “không có lỗi nghiêm trọng” còn thiếu nhiều thông tin:

- Công cụ và phiên bản dữ liệu dùng để đánh giá.
- Thời điểm quét và tuổi tối đa được chấp nhận.
- Phạm vi thành phần có thể nhận diện.
- Mức độ, khả năng ảnh hưởng và điều kiện áp dụng.
- Bản sửa có sẵn hay cần biện pháp thay thế.
- Ngoại lệ có chủ sở hữu và hạn kết thúc.

Không nhận diện được package hoặc scanner lỗi không được tự coi là không có vấn đề. Kết quả không có phát hiện chỉ phản ánh phạm vi và thông tin mà công cụ có tại thời điểm đó.

Một ví dụ yêu cầu dự án có thể quy định báo cáo không quá 24 giờ trước quyết định phát hành cho nhóm dịch vụ nhạy cảm. Con số cần được lựa chọn theo rủi ro và khả năng cập nhật thông tin, không phải ngưỡng chung cho mọi image.

### 5.3. SBOM và provenance có vai trò khác nhau

SBOM giúp kiểm kê thành phần; provenance cung cấp tuyên bố về nguồn và quá trình tạo sản phẩm. Cả hai cần gắn với đúng đối tượng image được xét.

Không coi SBOM là bằng chứng mọi thành phần đã được xác minh hoặc mọi lỗ hổng đã được phát hiện. Cũng không mặc định provenance ghi đủ mọi đầu vào hoặc rằng builder có danh tính hợp lệ thì không thể bị xâm nhập.

Nếu policy cần những trường cụ thể như nguồn mã, builder hoặc base image, phải kiểm tra chúng theo hợp đồng. Bằng chứng có chữ ký nhưng nói về digest khác không đáp ứng yêu cầu.

## 6. Xác thực nguồn phát hành và bảo vệ registry

### 6.1. Chữ ký phải gắn với chính sách danh tính

> **IMG-SIGN-01:** Image thuộc phạm vi bắt buộc phải có bằng chứng xác thực nội dung từ danh tính được phép phát hành. Bộ xác minh phải kiểm tra digest, danh tính, phạm vi và trạng thái tin cậy theo policy hiện hành.

Yêu cầu cần nêu:

- Đối tượng được ký là manifest, index hay một tuyên bố có subject cụ thể.
- Khóa, issuer hoặc danh tính nào được tin cậy.
- Danh tính được phát hành cho repository, môi trường và ngữ cảnh nào.
- Chính sách thuật toán, thời gian và thu hồi.
- Cách xoay vòng trust root.
- Hành vi khi bằng chứng thiếu, sai, quá hạn hoặc không kiểm tra được.

“Có chữ ký hợp lệ” chưa đủ nếu signer không được phép phát hành dịch vụ đó. Tương tự, một label ghi “official” hoặc “scanned” chỉ là metadata tự khai nếu chưa có bằng chứng được xác minh.

Chữ ký không chứng minh image không có mã độc. Nếu tài khoản phát hành hoặc builder được tin cậy bị chiếm, image nguy hiểm vẫn có thể được ký đúng quy trình kỹ thuật.

### 6.2. Phân quyền repository và vòng đời credential

> **IMG-REG-01:** Registry phải giới hạn quyền theo chức năng và phạm vi. Danh tính pull của workload không được tự có quyền push, sửa policy hoặc xóa artifact.

Cần phân biệt quyền:

- Đọc hoặc pull.
- Push vào khu vực build.
- Promotion sang phạm vi production.
- Ghi hoặc sửa tag.
- Xóa image và bằng chứng.
- Quản trị repository, retention và quyền truy cập.

Credential cần được bảo vệ, xoay vòng và thu hồi theo mô hình danh tính phù hợp. Không nhúng credential registry vào image, source code hoặc manifest có thể bị đọc ngoài phạm vi.

Kết nối registry cần xác thực peer và bảo vệ đường truyền theo chính sách. Không bỏ xác minh TLS khi gặp lỗi chứng thư để tiếp tục pull.

Registry nội bộ không tự tạo ra sự tin cậy cho mọi nội dung trong đó. Quyền publish, kiểm chứng nội dung và chính sách sử dụng vẫn phải tồn tại.

### 6.3. Promotion giữ liên kết nội dung và bằng chứng

> **IMG-PROMOTE-01:** Image được kiểm tra, được chấp thuận và được promotion phải liên kết bằng nội dung xác định. Thay đổi nội dung hoặc cấu trúc manifest trong quá trình chuyển phải được phát hiện và đánh giá lại.

Không mặc định thao tác sao chép giữa hai registry luôn bảo toàn mọi digest hoặc mọi bằng chứng. Cần kiểm chứng hành vi của công cụ và registry thực tế.

Nếu build lại để phát hành, phải coi đó là sản phẩm mới cần bằng chứng phù hợp. Cùng commit không bảo đảm cùng image khi đầu vào, công cụ hoặc môi trường build đã khác.

Bằng chứng quét, SBOM, provenance và chữ ký cần được quản lý cùng vòng đời sản phẩm. Chính sách retention phải xét khả năng điều tra và rollback, không chỉ tiết kiệm dung lượng.

## 7. Quyết định cho phép triển khai

### 7.1. Policy phải được thực thi ở mọi đường tạo workload

> **IMG-ADMIT-01:** Trước khi cho phép workload trong môi trường được bảo vệ chạy image, hệ thống phải kiểm tra nguồn, định danh nội dung và bằng chứng bắt buộc theo policy. Thiếu hoặc không xác minh được điều kiện bắt buộc phải được xử lý theo chính sách chặn đã định.

Phạm vi phải xét:

- Container ứng dụng.
- Init container và sidecar.
- Job, tác vụ định kỳ và công cụ vận hành.
- Container chẩn đoán hoặc đường cập nhật workload nếu nền tảng hỗ trợ.
- Pipeline triển khai khác hoặc thao tác trực tiếp có thể bỏ qua đường chuẩn.

Một bước kiểm tra trong CI chưa chứng minh mọi workload production đều đi qua nó. Người có quyền tạo workload trực tiếp có thể cần bị ràng buộc bằng kiểm soát tại nền tảng.

Cũng cần nêu giới hạn: chủ thể có quyền sửa hoặc vô hiệu hóa chính sách nền tảng nằm trong một ranh giới tin cậy khác. Không tuyên bố policy ngăn được mọi quản trị viên nếu họ có thể thay chính cơ chế thực thi.

### 7.2. Policy là hợp đồng, không phải nhãn trạng thái

Schema học tập:

```yaml
policyId: PROD-PAYMENT-IMAGE-01
scope:
  environment: production
  workloadGroup: payment
identity:
  requireContentDigest: true
  allowedRegistries:
    - registry.example.internal
evidence:
  publisherPolicy: approved-payment-release-identity
  requireProvenance: true
  requireComponentInventory: true
  maximumAssessmentAgeHours: 24
platforms:
  requireAssessmentForSelectedManifest: true
failure:
  missingRequiredEvidence: DENY
  unsupportedEvidenceFormat: DENY
exceptions:
  requireOwnerAndExpiry: true
```

Đây là schema minh họa, không phải cấu hình dùng trực tiếp cho một sản phẩm. Các giới hạn mức rủi ro, thuật toán và chi tiết xác minh phải được điền vào policy triển khai.

Một báo cáo có trường “passed” không tự được tin. Cần xác minh ai tạo báo cáo, nó nói về digest nào, policy nào và bằng chứng còn hợp lệ không.

### 7.3. Mã giả cho bước đánh giá

```text
evaluateWorkloadImage(request, trustedEnvironmentContext):
    policy = loadApplicableTrustedPolicy(trustedEnvironmentContext)
    reference = requireContentBoundReference(request.image)

    requireRegistryAllowed(reference.registry, policy)
    subjects = resolveManifestAndPlatformSubjects(reference, request.platform)

    for subject in subjects.requiredByPolicy:
        verifyPublisherAuthorization(subject, policy)
        verifyRequiredProvenance(subject, policy)
        verifyAssessmentSubjectAndFreshness(subject, policy)
        evaluateFindingsAndApplicableExceptions(subject, policy)

    requireReferenceUsedByWorkloadMatchesApprovedSubjects(reference, subjects)
    recordFilteredDecision(reference, subjects, policy.revision)
    return ALLOW
```

Khi chưa biết node hoặc nền tảng lúc đánh giá, policy phải quy định cách xử lý: chỉ cho phép một tập nền tảng đã đủ bằng chứng, hoặc có bước xác minh tiếp theo trước khi chạy. Không bỏ kiểm tra manifest con chỉ vì chưa biết sẽ chọn biến thể nào.

### 7.4. Tránh khoảng hở giữa kiểm tra và sử dụng

Nếu kiểm tra một tag rồi workload vẫn pull bằng tag đó, nội dung có thể đổi. Quyết định nên gắn với đối tượng bất biến hoặc có cơ chế tương đương bảo đảm nội dung.

Ngoài image, cần liên kết đúng môi trường và workload. Một ngoại lệ cho môi trường thử nghiệm không được dùng để vượt policy production.

Khi quan sát runtime, cần hiểu hệ thống đang báo manifest digest, config digest hay dạng định danh khác. Đối chiếu bằng ánh xạ đã được xác minh thay vì so chuỗi không cùng loại.

## 8. Yêu cầu runtime liên quan nhưng không thuộc riêng image

Image có user mặc định phù hợp vẫn có thể bị chạy với quyền khác. Vì vậy, cần tách yêu cầu xây dựng image và yêu cầu cấu hình workload.

| Thuộc tính | Điều image có thể hỗ trợ | Điều runtime phải thực thi |
| --- | --- | --- |
| User | Định nghĩa user và quyền filesystem phù hợp | Ngăn override sang quyền không được phép |
| Filesystem | Bố trí file và thư mục cần ghi | Root filesystem chỉ đọc nếu áp dụng; vùng ghi được cấp rõ ràng |
| Quyền hệ thống | Không yêu cầu đặc quyền không cần thiết | Giới hạn capability, đặc quyền và cơ chế tăng quyền |
| Tài nguyên host | Không phụ thuộc mount nhạy cảm ngoài thiết kế | Kiểm soát host path, namespace và socket quản trị |
| Mạng | Chỉ đóng gói chức năng mạng cần thiết | Chính sách kết nối, phân đoạn và danh tính dịch vụ |
| Secret | Không chứa secret trong image | Cấp secret theo workload, quyền và vòng đời |
| Công cụ chẩn đoán | Giảm thành phần không cần thiết | Quy trình debug có danh tính, phạm vi và audit |

> **IMG-RUN-01:** Workload phải tuân theo baseline quyền runtime được phê duyệt. Thuộc tính mặc định của image không được dùng làm bằng chứng thay thế cho cấu hình và quyền có hiệu lực của container.

Không mount socket quản trị container hoặc tài nguyên host nhạy cảm chỉ để tiện vận hành nếu chưa có nhu cầu và kiểm soát được phê duyệt.

Không có shell không làm ứng dụng miễn nhiễm với thực thi mã trái phép. Mã ứng dụng và runtime vẫn có khả năng đọc dữ liệu hoặc gọi mạng theo quyền được cấp.

Nếu cần debug, dùng quy trình được kiểm soát thay vì đưa công cụ quyền cao và credential vào mọi image production. Công cụ debug cũng thuộc phạm vi chính sách image và quyền runtime.

Các file được mount hoặc thành phần tải động sau khởi động có thể thay đổi nội dung thực thi ngoài image ban đầu. Nếu hệ thống cho phép, phải có yêu cầu kiểm soát riêng; digest của image không tự bao phủ chúng.

## 9. Logging, cảnh báo và ứng phó

### 9.1. Lưu bằng chứng theo đối tượng nội dung

Mỗi quyết định phát hành hoặc triển khai quan trọng nên ghi:

- Dịch vụ, môi trường, workload và danh tính thực hiện.
- Registry, digest, loại đối tượng và nền tảng liên quan.
- Revision policy và nguồn bằng chứng.
- Kết quả xác minh nguồn, đánh giá rủi ro và ngoại lệ.
- Lý do cho phép hoặc từ chối.
- Thời điểm và mã tương quan của build, promotion hoặc triển khai.

Không ghi registry token, khóa ký, credential build hoặc nguyên dữ liệu nhạy cảm phát hiện trong layer. Khi scanner phát hiện secret, log và ticket chỉ nên chứa thông tin đủ xử lý với quyền đọc phù hợp, không sao chép giá trị secret.

Audit cần được bảo vệ khỏi sửa hoặc xóa trái phép theo chính sách. Quyền push image không nên mặc nhiên kèm khả năng sửa policy và xóa mọi bằng chứng về image đó.

### 9.2. Đo độ bao phủ và trạng thái chưa xác định

Các chỉ số hữu ích:

- Số image và manifest thuộc phạm vi đã có bằng chứng hợp lệ.
- Số workload đang dùng image không xác định được trạng thái.
- Số quyết định bị từ chối theo nhóm nguyên nhân.
- Tuổi bằng chứng và thời gian từ phát hiện tới xử lý.
- Số ngoại lệ còn hiệu lực hoặc quá hạn.
- Tỷ lệ workload quan sát được khớp với quyết định chấp thuận.
- Thời gian truyền quyết định thu hồi tới các điểm thực thi.

Mẫu số cần rõ: thống kê chỉ các image đã quét có thể bỏ qua image được triển khai ngoài đường chuẩn. Cần đối soát danh mục registry, quyết định triển khai và trạng thái workload thực tế.

Scanner lỗi, không nhận diện được thành phần hoặc hệ thống bằng chứng ngừng cập nhật phải được báo là thiếu dữ liệu theo chính sách, không phải “không phát hiện rủi ro”.

### 9.3. Xử lý image không còn được phép

> **IMG-REVOKE-01:** Khi image hoặc danh tính phát hành không còn được tin cậy trong phạm vi xác định, hệ thống phải chặn triển khai mới theo thời hạn đã quy định và xác định các workload đang dùng nội dung liên quan để xử lý.

Các bước phản ứng có thể gồm:

1. Chặn promotion hoặc triển khai image bị ảnh hưởng.
2. Thu hồi credential registry, builder hoặc signer khi cần.
3. Xác định digest, nền tảng và khoảng thời gian liên quan.
4. Truy vết workload, phiên bản sản phẩm và dữ liệu có thể bị ảnh hưởng.
5. Đánh giá cách ly, thay image hoặc rollback theo tác động nghiệp vụ.
6. Kiểm chứng image thay thế và trạng thái runtime sau khôi phục.
7. Giữ bằng chứng điều tra trong kho được kiểm soát.

Xóa tag không bảo đảm nội dung đã bị chặn: node có thể còn cache, workload có thể dùng digest và artifact có thể tồn tại ở registry khác.

Chặn triển khai mới cũng không tự dừng workload đang chạy. Phản ứng với workload hiện hữu cần chính sách riêng, xét mức rủi ro và khả năng gây gián đoạn.

### 9.4. Rebuild và rollback cần kiểm chứng lại

Một image từng được chấp thuận không tự là lựa chọn rollback an toàn. Nó có thể đã bị thu hồi, chứa thành phần không còn được phép hoặc không tương thích với dữ liệu hiện tại.

Nếu phát hiện secret trong image, xóa layer ở bản mới chưa thu hồi secret đã lộ. Cần đánh giá và xoay vòng credential tương ứng.

Rebuild từ base image đã sửa cũng chưa đủ nếu ứng dụng vẫn kéo dependency cũ hoặc pipeline bị xâm nhập. Sản phẩm mới cần đi qua đầy đủ yêu cầu có liên quan.

## 10. Ma trận truy vết yêu cầu và bằng chứng

| ID | Rủi ro chính | Điểm thực thi | Tiêu chí chấp nhận tiêu biểu |
| --- | --- | --- | --- |
| IMG-ID-01 | Dùng nội dung khác image đã duyệt | Tham chiếu phát hành và workload | Đổi tag sau kiểm tra không làm workload chạy nội dung khác |
| IMG-BASE-01 | Đầu vào không được quản lý | Danh mục base image và build | Nguồn hoặc digest ngoài chính sách bị từ chối |
| IMG-BUILD-01 | Build không tin cậy có quyền phát hành | CI, danh tính và registry | Job không tin cậy không lấy được credential ký hoặc push production |
| IMG-SECRET-01 | Secret tồn tại trong image hoặc log | Build context, layer và pipeline | Secret thử nghiệm bị phát hiện; xóa ở layer sau không làm kiểm tra bỏ sót |
| IMG-SCAN-01 | Bằng chứng cũ hoặc sai đối tượng | Đánh giá sản phẩm cuối | Báo cáo sai digest, sai nền tảng hoặc quá hạn không được dùng |
| IMG-SIGN-01 | Image giả hoặc signer không đúng quyền | Bộ xác minh và trust policy | Chữ ký hợp lệ bởi danh tính không được phép vẫn bị từ chối |
| IMG-REG-01 | Ghi đè hoặc xóa ngoài quyền | Registry và quản lý credential | Danh tính pull không push, sửa tag hoặc xóa được |
| IMG-PROMOTE-01 | Mất liên kết sau promotion | Quy trình phát hành | Image thay đổi nội dung phải bị phát hiện và đánh giá lại |
| IMG-ADMIT-01 | Bỏ qua policy khi tạo workload | Nền tảng triển khai | API trực tiếp, job, init container và đường chẩn đoán không vượt kiểm tra |
| IMG-RUN-01 | Image tốt nhưng chạy quá quyền | Runtime policy | Override user, mount hoặc đặc quyền trái baseline bị chặn |
| IMG-REVOKE-01 | Tiếp tục dùng image bị thu hồi | Phân phối policy và inventory | Chặn triển khai mới và tìm được workload liên quan trong thời hạn mục tiêu |

Mỗi yêu cầu cần bổ sung chủ sở hữu, phạm vi áp dụng, mức ưu tiên, thời hạn và nơi lưu bằng chứng. Không đánh dấu đạt chỉ vì có một sản phẩm ký image hoặc một scanner đã được cài đặt.

## 11. Kiểm chứng trong vòng đời phát triển

### 11.1. Trước khi xây dựng và phát hành

Từ mô hình đe dọa, chọn các điều kiện bắt buộc cho từng môi trường. Một môi trường thử nghiệm có thể có policy khác production nhưng vẫn cần ranh giới và dữ liệu phù hợp.

Thiết kế phải xác định nơi tạo bằng chứng, nơi kiểm tra và chủ thể có thể thay đổi chúng. Nếu cùng một tài khoản có thể build, tự phê duyệt policy và xóa audit, cần đánh giá rủi ro của sự tập trung quyền đó.

Khi thêm nền tảng hoặc đổi base image, mở rộng phạm vi kiểm thử tương ứng. Không suy luận kết quả của một kiến trúc áp dụng cho mọi kiến trúc còn lại.

### 11.2. Các tình huống kiểm thử cần ưu tiên

| Tình huống | Bằng chứng cần quan sát |
| --- | --- |
| Tag bị chuyển sau khi quét | Workload vẫn dùng nội dung đã chấp thuận hoặc quyết định bị từ chối |
| Nội dung manifest hoặc layer bị thay | Sai lệch integrity được phát hiện ở điểm liên quan |
| Image có chữ ký đúng nhưng sai danh tính phát hành | Policy từ chối theo phạm vi signer |
| Báo cáo quét nói về digest khác | Không được dùng để cấp phép |
| Index có một nền tảng chưa đủ bằng chứng | Không được chọn biến thể đó ngoài chính sách |
| Secret được copy rồi xóa ở layer sau | Kiểm tra vẫn nhận diện rủi ro theo phạm vi thiết kế |
| Pull credential thử push hoặc xóa | Quyền bị từ chối và có audit phù hợp |
| Job không tin cậy thử lấy credential phát hành | Không nhận được credential hoặc quyền tương ứng |
| Tạo workload qua đường trực tiếp hoặc container phụ | Chính sách image vẫn được thực thi |
| Image mặc định non-root nhưng workload yêu cầu đặc quyền | Runtime policy xử lý theo baseline |
| Bằng chứng quá hạn hoặc dịch vụ xác minh lỗi | Áp dụng phản ứng đã đặc tả, không ngầm coi là đạt |
| Image đã thu hồi còn trong cache của node | Không được triển khai mới trái policy; workload hiện hữu được theo dõi riêng |
| Promotion làm thay định danh nội dung | Bằng chứng cũ không tự chấp thuận nội dung mới |
| Log scanner gặp secret thử nghiệm | Cảnh báo không làm lộ chính giá trị secret |

Các phép thử cần dùng image, credential và hạ tầng thử nghiệm được phép. Không đặt credential production vào image chỉ để chứng minh công cụ có thể tìm ra.

Quét image không đáng tin cũng cần môi trường xử lý an toàn: parser và thao tác giải nén có thể gặp nội dung độc hại hoặc tiêu tốn tài nguyên. Không chạy image nghi ngờ trên máy người vận hành để xem nó làm gì.

### 11.3. Phân biệt bằng chứng theo lớp

- Kiểm thử logic cho ánh xạ digest, signer, policy và ngoại lệ.
- Kiểm thử tích hợp cho build, registry, promotion và đánh giá triển khai.
- Kiểm tra môi trường cho quyền, mạng và các đường bỏ qua.
- Quan sát runtime để xác nhận workload thực sự dùng nội dung và quyền dự định.
- Diễn tập cho thu hồi, truy vết, rebuild và phục hồi.

Một lần triển khai thành công chỉ chứng minh đường cho phép đã chạy. Cần kiểm thử cả trường hợp phải bị chặn.

### 11.4. Duy trì sau phát hành

Thông tin rủi ro có thể thay đổi dù image không đổi. Cần đánh giá lại các image đang dùng theo chính sách, theo dõi thông báo từ nguồn liên quan và duy trì khả năng rebuild.

Thời hạn khắc phục cần dựa trên tác động, khả năng khai thác, dữ liệu và biện pháp giảm thiểu. Nếu chưa có bản sửa, phải có quyết định rủi ro và kế hoạch phù hợp thay vì chỉ ghi “chờ upstream”.

Khi ngừng dùng image, cập nhật registry, retention, quyền và inventory. Giữ bằng chứng cần thiết cho các sản phẩm còn hỗ trợ hoặc phục vụ điều tra theo thời hạn đã phê duyệt.

## 12. Bài tập áp dụng

Một nhóm Java đề xuất dùng tag `latest`, quét image trước phát hành, ký mọi image từ cùng một tài khoản CI và chạy container với quyền cao để tránh lỗi filesystem.

Hãy xây dựng đặc tả thay thế gồm:

1. Cách nhận diện image và biến thể nền tảng được phép.
2. Mô hình đe dọa cho base image, CI, registry, promotion và runtime.
3. Tám yêu cầu có ID, chủ sở hữu, điểm thực thi và tiêu chí chấp nhận.
4. Chính sách bằng chứng quét, chữ ký, SBOM và provenance.
5. Phân quyền pull, push, promotion, quản trị và xóa.
6. Bộ kiểm thử cho tag bị thay, signer sai phạm vi và biến thể chưa được kiểm tra.
7. Yêu cầu runtime để giới hạn quyền mà vẫn đáp ứng nhu cầu ghi dữ liệu.
8. Runbook khi phát hiện secret trong image và khi phải thu hồi một digest đã triển khai.

Đặc tả cần trả lời được image nào thực sự được chạy, vì sao bằng chứng áp dụng cho đúng nội dung đó và điều gì giới hạn tác động nếu mã trong image bị xâm nhập. Khi câu trả lời gắn với rủi ro, điểm thực thi và phép kiểm chứng cụ thể, container image security trở thành một tập yêu cầu có thể sử dụng xuyên suốt vòng đời phát triển và vận hành.
