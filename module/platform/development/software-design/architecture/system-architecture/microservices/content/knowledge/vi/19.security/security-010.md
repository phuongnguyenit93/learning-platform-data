# Quản lý lỗ hổng, phụ thuộc và nguồn gốc gói triển khai

Trong một hệ thống microservices, mã nguồn do nhóm phát triển viết chỉ là một phần của phần mềm được đưa vào vận hành. Một bản triển khai còn bao gồm thư viện trực tiếp, thư viện bắc cầu, runtime, thư viện hệ điều hành trong container, công cụ build, plugin, cấu hình và nhiều bước xử lý trong CI/CD. Lỗ hổng hoặc sự thay đổi ngoài dự kiến ở bất kỳ mắt xích nào có thể tác động đến nhiều dịch vụ dù mã nghiệp vụ của từng dịch vụ không đổi.

**Quản lý lỗ hổng, phụ thuộc và nguồn gốc gói triển khai** là một năng lực vận hành bảo mật liên tục: biết chính xác mình đã xây dựng và triển khai thành phần nào, phát hiện rủi ro liên quan, quyết định cách xử lý dựa trên tác động thực tế, và có thể chứng minh gói đang chạy xuất phát từ nguồn cũng như quy trình build được tin cậy.

Ba câu hỏi xuyên suốt bài học:

1. **Có gì bên trong?** Liệt kê được dependency, phiên bản, nguồn và thành phần của artifact đã triển khai.
2. **Có rủi ro gì và xử lý ra sao?** Đối chiếu lỗ hổng với môi trường, đường gọi và mức độ khai thác; khắc phục có kiểm chứng.
3. **Có thể tin artifact này không?** Ràng buộc mã nguồn, build, artifact và deployment bằng định danh, chữ ký, bằng chứng nguồn gốc và chính sách kiểm tra.

Đây là vấn đề của cả vòng đời phần mềm, không thể giải quyết chỉ bằng một lần chạy công cụ quét trước khi phát hành.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

- Phân biệt dependency trực tiếp, dependency bắc cầu, thành phần build và thành phần có mặt trong runtime.
- Giải thích sự khác biệt giữa danh mục thành phần (**SBOM**), kết quả quét lỗ hổng, chữ ký artifact và **provenance/attestation**.
- Thiết kế quy trình phát hiện, phân loại, ưu tiên, sửa và xác minh lỗ hổng cho nhiều microservices.
- Xây dựng chính sách chặn triển khai dựa trên mức rủi ro và bằng chứng, đồng thời quản lý ngoại lệ có thời hạn.
- Liên kết commit, cấu hình build, dependency, bản phát hành, image digest và phiên bản đang chạy.
- Mô tả cách ngăn dependency confusion, package tampering và việc thay artifact sau khi đã kiểm tra.
- Đưa ra cách ứng phó khi phát hiện một dependency có lỗ hổng hoặc một artifact có nguồn gốc không được xác minh.

## 2. Bề mặt tấn công của chuỗi cung ứng phần mềm

Xem luồng phát hành giả định cho một dịch vụ Java:

~~~text
Source repository (commit)
          |
          v
    CI build job  -----> Gradle plugins / build tools
          |
          v
 Resolve dependencies ---> Package repositories
          |
          v
   Compile + test
          |
          v
  Application JAR ------> SBOM + scan result
          |
          v
  Container build ------> Base image + OS libraries
          |
          v
 Image registry (digest)
          |
          v
   Deployment cluster --> Pod / workload running image digest
~~~

Nếu một thư viện nhận phiên bản mới, một build plugin bị thay thế, một base image đổi nội dung hoặc artifact được sửa sau bước scan, mã chạy thực tế có thể khác kỳ vọng. Vì vậy kiểm tra mã nguồn đơn thuần không đủ để chứng minh tính toàn vẹn của deployment.

Ví dụ cùng một thư viện dễ bị tổn thương có thể xuất hiện qua nhiều đường:

- Order Service khai báo trực tiếp thư viện A.
- Inventory Service không khai báo A, nhưng framework B kéo A vào runtime.
- Payment Service dùng một bản A khác trong image cũ.
- Một công cụ sinh mã trong CI dùng A, nhưng A không xuất hiện trong application runtime.

Rủi ro, khả năng khai thác và hướng khắc phục của bốn tình huống có thể khác nhau. Quy trình phải biết **đúng thành phần, đúng phiên bản, đúng nơi xuất hiện và đúng artifact đang chạy**.

## 3. Phân biệt thành phần, lỗ hổng và bằng chứng

| Khái niệm | Trả lời câu hỏi nào? | Giới hạn cần hiểu |
|---|---|---|
| Dependency inventory | Hệ thống đang phụ thuộc những gì? | Một danh sách khai báo chưa chắc phản ánh phiên bản đã resolve hoặc runtime thực tế. |
| Dependency graph | Thành phần nào kéo thành phần nào vào ứng dụng? | Nhìn đúng configuration/scope; compile và runtime có thể khác. |
| SBOM (Software Bill of Materials) | Artifact hoặc ứng dụng bao gồm những thành phần nào? | SBOM là danh mục, không tự chứng minh thành phần an toàn hay artifact đáng tin. |
| SCA (Software Composition Analysis) | Dependency đã biết lỗ hổng hay vấn đề license nào? | Kết quả phụ thuộc dữ liệu tra cứu và khả năng nhận diện package. |
| CVE / advisory | Lỗ hổng nào đã được công bố và ảnh hưởng phiên bản nào? | Thông báo có thể thiếu chi tiết, bị cập nhật hoặc không áp dụng cho mọi kiểu sử dụng. |
| CVSS | Mức độ nghiêm trọng về kỹ thuật của lỗ hổng ra sao? | Không thể dùng riêng CVSS để suy ra mức ưu tiên xử lý của một dịch vụ. |
| EPSS / danh sách bị khai thác | Có thêm tín hiệu gì về khả năng bị khai thác trong thực tế? | Tín hiệu ưu tiên, không thay thế việc đánh giá mức phơi bày và tác động riêng. |
| Artifact signature | Ai hoặc khóa/định danh nào đã ký lên các bytes của artifact? | Chữ ký không bảo đảm code không có bug hay người ký luôn đáng tin. |
| Provenance / attestation | Artifact nào được tạo từ nguồn, công cụ và quy trình build nào? | Cần xác minh nhà phát hành bằng chứng và nội dung predicate; không mặc định tin lời tự khai. |
| Deployment inventory | Cluster đang chạy chính xác digest nào ở đâu? | Tag có thể đổi; cần ghi nhận digest hoặc định danh nội dung bất biến. |

Các mục này bổ trợ nhau. Một image có chữ ký hợp lệ vẫn có thể chứa dependency dễ bị khai thác. Một SBOM đầy đủ vẫn có thể đi kèm quy trình build bị chiếm quyền. Một kết quả scan sạch hôm nay có thể trở nên lỗi thời khi thông tin về lỗ hổng mới xuất hiện ngày mai.

## 4. Quản lý phụ thuộc đúng theo những gì sẽ chạy

### 4.1 Phụ thuộc trực tiếp và bắc cầu

Trong Java/Gradle, dependency trực tiếp được khai báo bởi module; dependency bắc cầu do những dependency khác kéo vào. Ví dụ:

~~~text
checkout-service
  +-- web-framework:version-X
  |     +-- http-server:version-Y
  |     +-- json-library:version-Z
  +-- resilience-library:version-P
  +-- database-driver:version-Q
~~~

Giả sử advisory ảnh hưởng json-library:version-Z, nhóm Checkout phải biết nó vào qua web-framework nào và phiên bản nào thực sự được chọn khi giải quyết xung đột.

Để khảo sát ở dự án Gradle tương ứng, có thể dùng:

~~~powershell
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency json-library --configuration runtimeClasspath
~~~

Ở Windows, dùng gradlew.bat nếu môi trường shell không chạy wrapper theo cú pháp Unix. Với dự án nhiều module, chỉ rõ project path khi cần. Các lệnh trên là ví dụ tra cứu dependency của một dự án Gradle thông thường, không giả định đường dẫn module cụ thể.

Một dependency xuất hiện trong dependency tree không đồng nghĩa lỗ hổng của nó có thể được kích hoạt. Cần tìm hiểu cách thư viện được sử dụng, bản build thực tế và khả năng kẻ tấn công tiếp cận đường code liên quan. Tuy nhiên, **không phát hiện được đường gọi** cũng chưa đủ để khẳng định hoàn toàn không thể bị khai thác.

### 4.2 Phân loại phạm vi dependency

Không gom mọi thành phần vào một danh sách không có ngữ cảnh:

- **Runtime dependencies:** được nạp hoặc đóng gói khi ứng dụng vận hành.
- **Build dependencies:** Gradle, plugin, trình sinh mã, compiler và các tool được CI thực thi.
- **Test dependencies:** có thể không nằm trong artifact phát hành, nhưng vẫn chạy trong CI và có quyền truy cập dữ liệu/secret của job.
- **Container / OS dependencies:** các gói nền tảng, runtime JDK, thư viện hệ điều hành, công cụ dòng lệnh trong image.
- **Deployment dependencies:** sidecar, agent giám sát, admission controller hoặc thành phần triển khai có quyền tác động workload.

Công cụ phân tích cần gắn mỗi phát hiện với lớp tương ứng; không nên coi một lỗ hổng chỉ tồn tại trong test utility là rủi ro runtime giống một thư viện nhận request từ Internet. Ngược lại, lỗi trong build plugin có thể rất nghiêm trọng nếu plugin chạy với quyền phát hành artifact.

### 4.3 Khóa phiên bản và tránh thay đổi ngoài dự kiến

Một phát hành đáng tin cần có thể giải thích dependency nào được chọn. Các biện pháp điển hình:

1. Khai báo phiên bản có chủ đích; hạn chế wildcard, phiên bản động và việc dùng snapshot không kiểm soát trong release.
2. Dùng cơ chế dependency locking phù hợp với build tool và lưu lockfile trong repository khi dự án chọn chiến lược này.
3. Dùng dependency verification hoặc checksum/signature để phát hiện package bytes khác với giá trị đã tin cậy.
4. Kiểm soát repository resolution: nguồn nội bộ/ngoài, thứ tự ưu tiên, namespace được phép và quyền publish.
5. Thường xuyên cập nhật theo nhóm thay đổi nhỏ, có kiểm thử, thay vì để nhiều năm rồi nâng cấp đồng loạt.
6. Ghi lại Java/toolchain, build configuration và phiên bản plugin để hỗ trợ truy nguyên.

**Dependency locking** trả lời “phiên bản nào được giải quyết”; **dependency verification** hỗ trợ trả lời “bytes nhận về có khớp với thông tin đã phê duyệt không”. Hai cơ chế giải quyết những vấn đề khác nhau. Lockfile cũng không thay thế việc xem xét lỗ hổng đã biết.

## 5. SBOM: biết artifact thực sự chứa những gì

SBOM là một danh mục máy đọc được về các thành phần phần mềm và quan hệ giữa chúng. Các chuẩn phổ biến bao gồm **CycloneDX** và **SPDX**. Một SBOM hữu ích cho microservice phải gắn với một bản build hoặc artifact cụ thể, không phải danh sách package chung cho cả repository.

Các trường nên lưu khi công cụ hỗ trợ:

| Trường | Vì sao cần |
|---|---|
| Tên package, ecosystem, version | Xác định chính xác thành phần để tra cứu advisory. |
| Package URL (purl) / định danh tương đương | Giảm nhầm lẫn giữa package cùng tên ở ecosystem khác nhau. |
| Hash hoặc định danh nội dung | Hỗ trợ đối chiếu thành phần với bytes đã được tạo/nhận. |
| Supplier / nguồn package khi có | Hỗ trợ điều tra chuỗi cung ứng và đánh giá nguồn tin cậy. |
| Quan hệ dependency | Biết package bị ảnh hưởng đi vào ứng dụng thông qua đường nào. |
| Artifact/image digest | Gắn danh mục với đúng bản phát hành bất biến. |
| Công cụ sinh SBOM, phiên bản, thời điểm | Biết nguồn gốc của chính danh mục và đánh giá độ mới của nó. |

**Hai thời điểm tạo SBOM cần phân biệt:**

- **Source/build SBOM:** tạo từ manifest và dependency graph đã resolve trong quá trình build. Có lợi để hiểu quan hệ ở ecosystem ngôn ngữ, nhưng có thể bỏ sót gói OS hoặc thành phần được đưa vào image về sau.
- **Artifact/image SBOM:** phân tích package thực sự có mặt trong JAR hoặc container image đã build. Có lợi để kiểm kê đầu ra, nhưng một số thư viện được đóng gói lại hoặc tối giản có thể thiếu metadata nhận diện.

Có thể kết hợp hai góc nhìn để phát hiện chênh lệch. Không nên tuyên bố SBOM “đầy đủ 100%” chỉ vì công cụ tạo file thành công.

Ví dụ mô tả bản ghi theo dạng dễ đọc (không phải schema CycloneDX/SPDX chính thức):

~~~yaml
artifact:
  name: checkout-service
  image: registry.example/checkout@sha256:<image-digest>
  source_commit: <git-commit>
sbom:
  format: CycloneDX
  generated_from: built-container-image
  components:
    - name: json-library
      ecosystem: maven
      version: version-Z
      direct: false
    - name: runtime-jdk
      ecosystem: container
      version: release-R
~~~

Khi lưu SBOM, bảo đảm người đọc có thể truy tìm từ deployment đến image digest và từ image digest đến SBOM tương ứng. Nếu image thay đổi sau khi sinh SBOM, phải tạo lại hoặc chứng minh SBOM gắn đúng artifact mới.

## 6. Phát hiện lỗ hổng không dừng ở một công cụ scan

Một chương trình quản lý lỗ hổng thường lấy dữ liệu từ nhiều nguồn: advisory của nhà phát triển package, dữ liệu CVE, cơ sở dữ liệu hệ sinh thái như OSV, dữ liệu của nền tảng hosting package, thông báo của nhà cung cấp runtime và danh sách các lỗ hổng đã được khai thác trong thực tế. Mỗi nguồn có độ phủ và tốc độ cập nhật khác nhau.

Quy trình gợi ý:

~~~text
Resolved dependency + SBOM + deployed artifact
                    |
                    v
          Advisory / vulnerability feeds
                    |
                    v
      Match: package + version + ecosystem
                    |
                    v
   Normalize / deduplicate / collect evidence
                    |
                    v
  Determine exposure + reachability + business impact
                    |
                    v
      Prioritize -> Fix / Mitigate / Exception
                    |
                    v
     Rebuild -> Rescan -> Redeploy -> Monitor
~~~

Kết quả scan nên có tối thiểu: định danh finding; component và version; advisory/CVE; phiên bản chịu ảnh hưởng và bản khắc phục; nơi hiện diện (source, build, JAR, image); dịch vụ/artifact liên quan; thời điểm phát hiện; đường dẫn bằng chứng; người xử lý; trạng thái và hạn hoàn thành.

**Vấn đề dữ liệu phổ biến:**

- Công cụ nhận nhầm package có cùng tên nhưng khác ecosystem.
- Package vendor đã backport bản vá nhưng chuỗi phiên bản không phản ánh đúng patch level.
- Một CVE có nhiều advisory hoặc thông báo được sửa sau thời điểm scan.
- Dependency graph của nguồn khác artifact đã triển khai.
- Một lớp package bị thiếu vì SBOM chỉ khảo sát Java libraries mà bỏ qua OS packages.
- Một CVE được đánh dấu “fixed” chỉ vì version string mới hơn, nhưng image chạy vẫn là digest cũ.

Khi có nghi ngờ, dùng advisory gốc, metadata package và bằng chứng về artifact thực tế để xác định phạm vi. Không xóa finding chỉ vì một nguồn dữ liệu khác chưa liệt kê nó.

## 7. Ưu tiên theo rủi ro có thể khai thác

Một chỉ số “Critical” không tự động quyết định thứ tự xử lý khi một công ty vận hành hàng trăm dịch vụ. Ngược lại, finding “Medium” trong một thành phần Internet-facing có exploitation đang diễn ra có thể cần hành động tức thời.

Đánh giá từng finding theo ít nhất năm yếu tố:

1. **Mức độ nghiêm trọng kỹ thuật:** tác động lên tính bảo mật, toàn vẹn và tính sẵn sàng; CVSS là một tín hiệu.
2. **Bằng chứng khai thác thực tế:** có exploit công khai đáng tin cậy, đang bị khai thác, hoặc xuất hiện trong danh sách khai thác được cơ quan đáng tin công bố hay không.
3. **Độ phơi bày:** endpoint Internet-facing, API nội bộ, job batch, công cụ CI hay thư viện không được kích hoạt; có quyền truy cập cần thiết không.
4. **Tác động nghiệp vụ:** dữ liệu nhạy cảm, thanh toán, danh tính, khả năng lan truyền qua nhiều service, môi trường và khách hàng.
5. **Khả năng khắc phục và biện pháp bù trừ:** đã có bản vá hay chưa, thay đổi có gây rủi ro vận hành không, có thể chặn tính năng/traffic hoặc cách ly đường tấn công ngay không.

Một bảng ưu tiên minh họa:

| Finding | Độ nghiêm trọng công bố | Bối cảnh thực tế | Quyết định ví dụ |
|---|---|---|---|
| Lỗ hổng có bằng chứng khai thác trên thư viện xử lý request public | Cao | Đường gọi nhận input không đáng tin, hệ thống Internet-facing | Xử lý khẩn cấp; cân nhắc chặn đường tấn công trong lúc cập nhật. |
| CVE trong plugin build chạy với quyền publish | Trung bình | Plugin nhận dữ liệu ngoài và job có quyền phát hành | Ưu tiên cao do rủi ro chiếm chuỗi cung ứng. |
| CVE trong optional dependency không có trong artifact chạy | Cao | Chỉ được khai báo ở test scope | Xác minh phạm vi CI/test; không gán bừa là lỗ hổng runtime. |
| Package OS có advisory, nhưng vendor đã backport | Cao | Image dùng build hệ điều hành đã vá | Lưu bằng chứng vendor/distro; yêu cầu scanner hỗ trợ nhận diện bản vá. |
| Lỗ hổng không có fix upstream | Cao | Chức năng đang sử dụng và phơi bày | Áp dụng giảm thiểu, theo dõi liên tục và đặt hạn đánh giá lại. |

Đặt deadline dựa trên chính sách nội bộ và mức rủi ro. Ví dụ có thể quy định phát hiện đang bị khai thác trên tài sản Internet-facing phải được triage trong ngày, còn các finding đã được chứng minh không nằm trong runtime được xử lý theo chu kỳ thông thường. Đây là **ví dụ cách đặt chính sách**, không phải thời hạn phổ quát hoặc cam kết tuân thủ bất kỳ tiêu chuẩn nào.

### 7.1 Reachability có ý nghĩa gì?

Reachability hỏi liệu mã dễ bị tổn thương có thể được gọi trong điều kiện cần để khai thác. Công cụ tĩnh có thể cung cấp tín hiệu về method call và entry point; nhưng reflection, dynamic loading, serialization, config và luồng dữ liệu bất đồng bộ khiến kết luận không luôn chắc chắn.

Chỉ giảm ưu tiên khi có bằng chứng phù hợp. Không dùng “không tìm thấy call path” làm bằng chứng duy nhất cho việc miễn trừ mãi mãi.

### 7.2 Quản lý ngoại lệ có thời hạn

Một ngoại lệ hợp lệ nên chứa:

~~~yaml
finding: ADVISORY-EXAMPLE
component: package:version
affected_artifacts:
  - checkout@sha256:<digest>
reason: "Chưa có bản vá tương thích; endpoint đã được chặn tại gateway."
compensating_controls:
  - "Giới hạn truy cập endpoint /legacy-import từ mạng nội bộ."
owner: "Checkout team"
approved_by: "Security owner"
review_after: "YYYY-MM-DD"
expiration: "YYYY-MM-DD"
evidence:
  - "Link đến advisory và kết quả xác minh điều kiện khai thác."
~~~

Các trường là ví dụ cấu trúc quản trị, không phải định dạng bắt buộc. Ngoại lệ không xóa lỗ hổng khỏi thực tế; nó ghi nhận quyết định chấp nhận rủi ro trong một thời hạn có kiểm soát. Khi có bản vá, điều kiện phơi bày thay đổi hoặc ngoại lệ hết hạn, finding phải được đánh giá lại.

## 8. Khắc phục phụ thuộc mà không phá vỡ dịch vụ

Hướng xử lý ưu tiên là loại bỏ nguyên nhân hoặc đưa về phiên bản đã vá, sau đó kiểm thử và phát hành artifact mới. Các lựa chọn:

- **Nâng cấp trực tiếp:** nâng version library bị ảnh hưởng, chạy test hợp đồng API và kiểm thử tích hợp.
- **Nâng cấp dependency mẹ:** khi lỗ hổng nằm ở transitive dependency, update framework/SDK kéo package đó vào hoặc quản lý version override có chủ đích.
- **Thay thế thư viện:** khi upstream không duy trì, không có fix hoặc quyền truy cập không còn phù hợp.
- **Loại bỏ thành phần không sử dụng:** giảm bề mặt tấn công thay vì cố vá package không cần thiết.
- **Cập nhật base image:** xây lại container khi gói OS hoặc runtime JDK có bản vá; đảm bảo image mới thật sự được deploy.
- **Giảm thiểu tạm thời:** vô hiệu tính năng, giới hạn quyền, chặn input/đường mạng, thêm rule kiểm soát; kèm deadline và bằng chứng hiệu lực.

Đừng cố khắc phục bằng cách sửa file SBOM hoặc ẩn finding khỏi scanner. Kết quả scan chỉ là tín hiệu; artifact phải thực sự thay đổi hoặc điều kiện khai thác phải được giảm thiểu có kiểm chứng.

Khi cập nhật một dependency quan trọng, cần xem xét:

1. Chức năng ứng dụng và test hồi quy.
2. API/ABI compatibility giữa phiên bản cũ và mới.
3. Thay đổi hành vi serialization, timeout, retry, database driver hoặc security defaults.
4. Tác động hiệu năng, memory và thread pool.
5. Vấn đề license hoặc các dependency mới được kéo vào.
6. Tính tương thích của các service giao tiếp qua API/event contract.
7. Khả năng rollback an toàn nếu deployment mới xảy ra lỗi.

**Rollback không phải luôn luôn giải quyết sự cố bảo mật.** Quay lại image cũ có thể đưa lỗ hổng đã vá trở lại. Kế hoạch phản ứng phải phân biệt rollback do lỗi vận hành và rollback làm tăng lại rủi ro bảo mật.

## 9. Nguồn gốc gói triển khai: từ commit đến image digest

Một pipeline đáng tin phải nối được chuỗi:

~~~text
Commit SHA + reviewed source
          |
          v
Trusted build identity + declared inputs
          |
          v
Build execution
          |
          +--> test evidence
          +--> resolved dependencies
          +--> artifact/image SBOM
          +--> scan report
          +--> build provenance
          |
          v
Immutable artifact digest
          |
          +--> signature / attestation
          |
          v
Registry
          |
          v
Deployment policy verification
          |
          v
Running workload references same digest
~~~

Để điều tra một image đang chạy, cần lần ngược được: image digest → bản phát hành → build run → source commit/tag đã kiểm tra → dependency/build inputs → SBOM và kết quả scan → người hoặc hệ thống có quyền phê duyệt/phát hành.

### 9.1 Tag và digest không tương đương

Tag như checkout:release-42 là tên tham chiếu có thể bị gán lại trong một số registry. Digest có dạng sha256:<hash> định danh nội dung image theo cách bất biến đối với cùng bytes và metadata được băm. Vì vậy deployment và việc đối chiếu bằng chứng nên ưu tiên **image digest**, không dựa riêng vào tag hoặc thời điểm push.

Ví dụ:

~~~text
Khó kiểm chứng:
  registry.example/checkout:latest

Rõ hơn:
  registry.example/checkout@sha256:<digest>
~~~

Dòng dùng <digest> trong ví dụ là placeholder, không phải digest thật; phải thay bằng giá trị tạo ra từ registry/build. Nếu dịch vụ được rebuild từ cùng source vì base image mới, digest có thể đổi. Điều này là bình thường; cần ghi lại cả commit và digest để truy vết.

### 9.2 Build provenance và attestation

**Provenance** mô tả quá trình tạo artifact: builder là ai hoặc hệ thống nào; source commit nào; loại workflow; inputs và parameters liên quan; artifact subject/digest nào. **Attestation** là bản phát biểu có cấu trúc về một subject, có thể mang provenance, kết quả test, policy hay thông tin khác.

Có thể biểu diễn ý tưởng:

~~~yaml
subject:
  image: registry.example/checkout
  digest: sha256:<image-digest>
predicate:
  source_repository: <repository-identity>
  source_revision: <commit-sha>
  builder: <trusted-ci-workflow-identity>
  build_definition: <workflow-and-parameters>
  build_completed_at: <timestamp>
~~~

Đây là **minh họa khái niệm**, không phải schema attestation chuẩn. Khi triển khai thực tế, chọn định dạng có thể kiểm tra bằng công cụ và chính sách xác minh, chẳng hạn provenance theo hệ sinh thái SLSA/in-toto.

Provenance tốt giúp trả lời “gói này được sinh ra như thế nào”; nó **không** tự chứng minh mọi dependency đều an toàn hoặc builder không thể bị xâm nhập. Mức độ tin cậy phụ thuộc vào cách tạo chứng cứ, cô lập build, quyền của runner và việc bên triển khai tự xác minh.

### 9.3 Chữ ký, identity và trust policy

Ký artifact/image giúp bên nhận phát hiện bytes bị thay đổi và xác minh chữ ký gắn với identity/key được tin cậy. Hệ sinh thái ký hiện đại có thể dùng cách quản lý khóa truyền thống hoặc keyless signing dựa trên identity của CI và cơ chế chứng thực ngắn hạn.

Bên triển khai phải xác định rõ:

- Chấp nhận artifact từ registry/namespace nào.
- Chấp nhận identity của tổ chức, repository, workflow hoặc builder nào.
- Chữ ký phải ràng buộc chính xác image digest nào.
- Có cần provenance hay attestation đi kèm không; cần predicate hoặc source revision nào.
- Khi kiểm tra chữ ký hoặc policy thất bại thì dừng triển khai ra sao.
- Cách thu hồi, thay đổi identity và kiểm soát quyền ký/publish.

**Chữ ký hợp lệ nhưng identity sai vẫn phải bị từ chối.** Ví dụ một cá nhân có thể ký image bằng khóa riêng của họ, nhưng điều đó không chứng minh image được tạo bởi CI phát hành chính thức của Checkout.

### 9.4 SLSA ở vị trí nào?

SLSA là một khung hướng dẫn tăng mức đảm bảo cho chuỗi cung ứng phần mềm, đặc biệt ở quy trình build và bằng chứng nguồn gốc. Có thể dùng khung này để đặt mục tiêu nâng cấp như: provenance được tạo tự động, builder được kiểm soát, quy trình có tính cô lập và bằng chứng được xác minh trước deploy. Không nên chỉ ghi “đạt SLSA” trong tài liệu mà bỏ qua phạm vi, yêu cầu cụ thể và bằng chứng triển khai.

## 10. Bảo vệ điểm yếu của CI/CD và package registry

Quy trình build thường có quyền lớn hơn ứng dụng đang chạy: đọc source, tạo release, ký image, publish package hoặc deploy cluster. Một công cụ độc hại trong build chain có thể lấy cắp credential hoặc thay artifact trước khi phát hành.

Các kiểm soát đáng cân nhắc:

| Điểm rủi ro | Biện pháp điển hình |
|---|---|
| Dependency confusion | Tách namespace nội bộ, xác định repository được phép, kiểm soát resolution và quyền publish. |
| Typosquatting | Kiểm tra tên package và maintainer; dùng review/allowlist cho dependency mới hoặc có rủi ro cao. |
| Tài khoản maintainer/package bị chiếm | Theo dõi thay đổi bất thường, xác minh digest/chữ ký khi có, review bản nâng cấp. |
| Build runner bị xâm nhập | Runner cô lập, ephemeral khi phù hợp, cập nhật image builder, tối thiểu hóa secret và quyền mạng. |
| Workflow lạ có quyền phát hành | Bảo vệ branch/tag, review workflow, hạn chế trigger, kiểm tra source và identity của run. |
| Credential tồn tại lâu | Ưu tiên token ngắn hạn, cấp đúng audience/scope, không để token trong log/artifact. |
| Artifact bị thay sau scan | Scan và ký theo đúng digest cuối cùng; policy khi deploy xác minh cùng digest. |
| Mutable tags | Tạo deployment theo digest, giới hạn quyền ghi/xóa registry và lưu manifest phát hành. |
| SBOM hoặc attestation bị thay | Gắn bằng chứng với digest và chữ ký/identity đáng tin; kiểm tra tại điểm sử dụng. |

Nhiều pipeline có bước scan nhưng thiếu **thực thi chính sách**: kết quả được lưu vào dashboard mà vẫn cho deploy khi vi phạm quy tắc quan trọng. Phải định nghĩa rõ khi nào pipeline chỉ cảnh báo, khi nào fail build và khi nào deployment bị từ chối; giữ ngoại lệ có thời hạn và người phê duyệt.

## 11. Thiết kế luồng phát hành có kiểm soát

Một pipeline tham chiếu cho microservice Java đóng gói container:

~~~text
Pull request:
  1. Review source + dependency changes
  2. Dependency update check + SCA
  3. Unit tests, integration tests, contract tests
  4. Policy check cho dependency mới / lỗ hổng nghiêm trọng

Merge vào nhánh phát hành:
  5. Build trên runner đã được kiểm soát
  6. Resolve dependencies và lưu thông tin đầu vào
  7. Build JAR và container image cuối cùng
  8. Sinh SBOM gắn với image digest
  9. Quét application packages + OS packages của image
 10. Đánh giá risk policy + ngoại lệ còn hiệu lực
 11. Sinh provenance/attestation cho đúng artifact digest
 12. Ký artifact hoặc chứng thực bằng identity của trusted CI
 13. Publish image và metadata ra registry

Trước và trong deploy:
 14. Xác minh digest, chữ ký, identity, provenance, policy
 15. Deploy đúng digest đã được kiểm tra
 16. Ghi nhận digest đang chạy, rollout ID và thời điểm
 17. Tiếp tục giám sát advisory mới + runtime exposure
~~~

Các bước có thể khác nhau theo công cụ; điều cốt lõi là **không có khoảng hở để bytes của artifact đổi sau khi kiểm tra** mà bản thay đổi vẫn được triển khai dựa trên kết quả cũ.

Ví dụ biểu diễn quy tắc policy mức cao:

~~~yaml
deployment_policy:
  require:
    - artifact_digest_is_immutable
    - signature_identity_matches_release_ci
    - provenance_subject_matches_image_digest
    - source_revision_is_approved
    - sbom_subject_matches_image_digest
    - vulnerability_scan_is_recent_enough
    - no_unapproved_high_risk_findings
  on_verification_failure: deny
~~~

Đây là **pseudocode diễn đạt chính sách**, không phải cấu hình chạy trực tiếp trong GitHub Actions, Kubernetes hoặc admission controller. Khi triển khai cần chuyển từng điều kiện thành luật do công cụ hỗ trợ và xác định rõ khái niệm “recent enough”, “high risk” theo chính sách của tổ chức.

### 11.1 Ai tạo bằng chứng và ai xác minh?

Không nên đặt toàn bộ niềm tin vào chính job đang có khả năng bị xâm nhập: nếu job vừa tự ghi “scan passed” vừa tự cấp quyền triển khai, kẻ tấn công kiểm soát job có thể giả mạo kết quả.

Một thiết kế tốt tách vai trò khi điều kiện cho phép:

- Build pipeline tạo artifact và sinh chứng cứ.
- Dịch vụ quản lý khóa/identity cấp quyền ký theo các điều kiện hạn chế.
- Registry lưu artifact và metadata theo digest.
- Deployment controller/admission policy xác minh độc lập identity, digest và attestation trước khi chấp nhận.
- Nền tảng quan sát lưu record digest cuối cùng thực sự chạy để đối chiếu với release.

Tách nhiệm vụ giúp giảm khả năng một thành phần bị chiếm quyền có thể thay đổi mọi bằng chứng mà không bị phát hiện.

## 12. Microservices: kiểm kê nhiều artifact và trách nhiệm sở hữu

Một hệ thống nhiều service thường chạy nhiều phiên bản khác nhau ở các cluster/region. Một finding liên quan đến package X cần ánh xạ:

~~~text
CVE / advisory
      |
      v
Package + affected version range
      |
      v
SBOM / artifact digest
      |
      v
Service + release + environment
      |
      v
Cluster / namespace / workload
      |
      v
Owner + exposed business function
~~~

Không chỉ mở ticket “hãy cập nhật package X” mà không cho biết nơi đang chạy. Với cùng image, staging có thể đã cập nhật trong khi production còn dùng bản cũ. Một release đã build nhưng chưa deploy cũng không giải quyết exposure của pod đang chạy.

Gợi ý một inventory tối thiểu:

| Trường | Ví dụ giá trị |
|---|---|
| Service | checkout |
| Owner | đội phụ trách checkout |
| Environment | production |
| Region / cluster / namespace | cluster-a / namespace-checkout |
| Source revision | commit SHA |
| Image reference | registry.example/checkout@sha256:<digest> |
| Build run | CI run ID |
| SBOM / provenance | URI hoặc artifact reference gắn digest |
| Scan timestamp | thời điểm đánh giá |
| Finding status | open / mitigating / fixed / exception |
| Next action | build lại, deploy bản sửa, đánh giá reachability |

**Quyền sở hữu:** nhóm service chịu trách nhiệm đánh giá ảnh hưởng và sửa dependency; nền tảng phụ trách base image, CI, registry, policy và kiểm soát chung; nhóm bảo mật hỗ trợ chuẩn ưu tiên, threat intelligence và theo dõi ngoại lệ. Trách nhiệm có thể phân công khác nhau giữa tổ chức, nhưng phải có người nhận việc rõ ràng.

## 13. Duy trì an toàn sau khi đã phát hành

Một image được quét và ký lúc phát hành có thể tồn tại trong registry và production nhiều tháng. Trong khoảng thời gian đó có thể xuất hiện advisory mới, thay đổi điểm CVSS, bằng chứng khai thác hoặc phát hiện về package giả mạo.

Cần một vòng lặp vận hành:

1. Thu thập liên tục danh sách artifact/digest thực sự đang chạy.
2. Lưu SBOM theo digest đủ lâu để đối chiếu advisory mới.
3. Tái đánh giá lỗ hổng khi feed cập nhật, kể cả khi source code không đổi.
4. Đánh dấu môi trường và người sở hữu của các release bị ảnh hưởng.
5. Tạo remediation task, theo dõi deadline và ngoại lệ.
6. Build phiên bản mới từ nguồn/baseline được kiểm soát; quét và ký artifact mới.
7. Theo dõi rollout đến khi mọi workload mục tiêu chạy digest đã sửa.
8. Xác nhận finding không còn trong phạm vi triển khai hoặc có bằng chứng giảm thiểu phù hợp.

**Rescan khác rebuild:** chỉ chạy scanner lần nữa không sửa image cũ. Nếu base image có bản vá nhưng application image chưa được build lại, pod có thể vẫn mang lớp OS cũ. Ngược lại, rebuild source không đổi có thể tạo digest mới nếu base image hoặc dependency thay đổi; phải cập nhật SBOM/provenance theo artifact mới.

**Không đánh giá từ tag lúc scan rồi triển khai tag lúc khác**: thời điểm kiểm tra và thời điểm sử dụng có thể trỏ tới các bytes khác nhau (time-of-check/time-of-use). Luôn ràng buộc kết quả với digest.

## 14. Kịch bản thực hành 1 — CVE nằm trong dependency bắc cầu

Giả sử Checkout dùng web-framework phiên bản F, framework kéo json-library phiên bản J. Một advisory mới cho biết J bị ảnh hưởng khi ứng dụng parse payload không đáng tin ở một cấu hình cụ thể.

**Phân tích:**

- Tìm J trong dependency graph của runtimeClasspath và trong SBOM của image Checkout đang chạy.
- Xác minh version/build variant tương ứng advisory; đọc điều kiện khai thác.
- Kiểm tra API nào nhận payload bên ngoài và cấu hình deserialize có kích hoạt đường nguy hiểm không.
- Đối chiếu image digest ở production, số replica, phạm vi traffic và loại dữ liệu có thể tác động.
- Xác định phiên bản web-framework hoặc phiên bản J đã sửa, sự tương thích và các breaking changes.
- Nếu patch chưa thể deploy ngay, đặt biện pháp giảm thiểu có kiểm chứng như chặn đường input hoặc tính năng rủi ro, cùng thời hạn khắc phục.

**Sửa và xác nhận:** nâng dependency theo đường ổn định, chạy test deserialize/input validation, integration test và contract test; build image mới; sinh SBOM, scan, ký; deploy đúng digest và xác minh mọi pod đã thay thế. Đóng finding khi evidence cho thấy phiên bản đang chạy không còn bị ảnh hưởng hoặc cơ chế giảm thiểu được chấp nhận theo chính sách.

**Điểm cần nhớ:** không được chỉ nâng trực tiếp một package trong build file rồi đánh dấu fixed nếu Gradle thực tế vẫn resolve phiên bản dễ bị ảnh hưởng hoặc production vẫn đang dùng image cũ.

## 15. Kịch bản thực hành 2 — Artifact không có provenance hợp lệ

Giả sử registry chứa image checkout:release-42. Pipeline triển khai phát hiện digest tương ứng không có provenance từ workflow phát hành được phê duyệt, dù image đó vẫn có SBOM và kết quả scan “no critical vulnerabilities”.

**Phân tích:**

1. Tạm dừng rollout image chưa được xác minh.
2. Ghi nhận digest và nơi đang chạy (nếu có), nhưng không dựa vào tag như danh tính cuối cùng.
3. Kiểm tra audit trail của registry: ai push, thời điểm nào và có thay tag không.
4. Kiểm tra CI run chính thức cho commit mong đợi và digest output của run.
5. So sánh chữ ký, identity phát hành, provenance subject và source revision; tìm ra chỗ đứt chuỗi.
6. Nếu nghi ngờ artifact bị thay đổi hoặc CI bị chiếm quyền, xử lý như sự cố chuỗi cung ứng theo quy trình ứng cứu.

**Cách xử lý:** build lại từ commit được phê duyệt trên workflow tin cậy, tạo SBOM và provenance mới, ký digest mới, kiểm tra chính sách rồi mới deploy. Một image có thể “không có CVE đã biết” mà vẫn bị từ chối vì **không chứng minh được nguồn gốc**.

## 16. Ứng phó khi có dấu hiệu đã bị khai thác hoặc bị cấy mã

Một finding mới công bố khác với một dấu hiệu hệ thống đã bị khai thác. Khi có chỉ báo xâm nhập, cần phối hợp ứng cứu sự cố thay vì chỉ mở ticket nâng version.

Các bước nguyên tắc:

- **Xác định phạm vi:** package, artifact digest, build run, service, cluster và credential có thể bị ảnh hưởng.
- **Ngăn lan truyền:** giới hạn quyền, cô lập workload hoặc dừng triển khai khi phù hợp; bảo toàn bằng chứng trước các thao tác có thể xóa log cần điều tra.
- **Điều tra nguồn:** package registry, hoạt động CI, quyền publish, thay đổi workflow và thời điểm xuất hiện artifact.
- **Xử lý credential:** thu hồi hoặc xoay vòng token/secret có khả năng đã lộ; không giả định rebuild image sẽ tự xử lý một token bị đánh cắp.
- **Khôi phục từ nguồn sạch:** source revision đã kiểm tra, build environment đáng tin, dependencies và base image được xác minh; sinh artifact/provenance mới.
- **Theo dõi và rút kinh nghiệm:** tìm dấu hiệu lặp lại, bổ sung detection, siết quyền CI và cập nhật policy.

Đừng xóa image nghi ngờ khỏi registry ngay nếu tổ chức cần giữ bằng chứng điều tra; cô lập quyền sử dụng và tuân theo quy trình lưu giữ bằng chứng. Đồng thời không tiếp tục rollout chỉ để có thêm tín hiệu trong lúc nguy cơ lây lan còn cao.

## 17. Các lỗi triển khai phổ biến

1. **Chỉ scan source manifest.** Bỏ sót transitive dependency đã resolve, gói OS hoặc image đang thực sự chạy. Cần nhiều lớp inventory và đối chiếu artifact.
2. **Chặn mọi CVE theo điểm số duy nhất.** Dễ tạo nhiễu và trì hoãn rủi ro khai thác thật. Dùng chính sách rủi ro có ngữ cảnh và bằng chứng.
3. **Bỏ qua build dependencies.** Một plugin độc hại có thể thao túng artifact dù không tồn tại trong runtime.
4. **Không khóa hoặc xác minh đầu vào build.** Hai build từ cùng commit có thể nhận dependency khác nhau ngoài dự kiến.
5. **Tin tag là bất biến.** Tag có thể được gán lại; phải ghi và xác minh digest.
6. **Chỉ ký image mà không kiểm tra signer.** Chữ ký có giá trị khi identity/khóa được đối chiếu chính sách đáng tin.
7. **Sinh SBOM cho JAR nhưng gắn nhãn toàn bộ image.** Gây hiểu nhầm rằng OS package cũng đã được kiểm kê.
8. **Đánh dấu fixed sau khi merge PR.** Release hoặc pod cũ vẫn có thể đang chạy; cần xác minh deployment inventory.
9. **Không quản lý ngoại lệ.** Một finding bị “ignore” vô thời hạn khiến rủi ro bị bỏ quên.
10. **Để cùng job tự tuyên bố pass và tự deploy không xác minh.** Tăng nguy cơ giả mạo kết quả khi CI bị chiếm quyền.
11. **Không tái quét artifact cũ.** Lỗ hổng có thể được công bố sau ngày phát hành.
12. **Rebuild từ nguồn không còn đáng tin.** Việc có digest mới và chữ ký mới không tự loại bỏ mã độc nếu source hoặc builder vẫn bị kiểm soát.

## 18. Bài tập áp dụng

### Bài tập A — Lập bản đồ dependency cho một microservice

Cho một ứng dụng Java có framework HTTP, database driver và thư viện JSON. Hãy lập sơ đồ dependency trực tiếp/bắc cầu ở runtime, chỉ ra plugin build quan trọng, rồi đề xuất nơi sinh SBOM để bao phủ cả JAR và container. Mỗi thành phần cần gắn version, scope, nguồn và artifact digest liên quan. Nêu rõ phần nào inventory chưa thể khẳng định do thiếu thông tin.

### Bài tập B — Xếp ưu tiên remediation

Một tổ chức có ba finding giả định:

- F1: CVE nghiêm trọng trên thư viện input parser của public API, có dấu hiệu khai thác rộng rãi.
- F2: CVE nghiêm trọng trên thư viện chỉ dùng trong test, không được đóng gói runtime nhưng chạy trong CI.
- F3: CVE mức trung bình ở build plugin có quyền truy cập credential publish.

Hãy đặt thứ tự triage dựa trên exposure, khả năng khai thác, quyền, tác động và mức khẩn cấp; giải thích tại sao không thể chỉ sắp theo nhãn severity. Với mỗi finding, nêu bằng chứng cần có trước khi tuyên bố đã xử lý.

### Bài tập C — Thiết kế policy trước deploy

Một release checkout có image digest, SBOM và scan report nhưng thiếu provenance. Xây bộ quy tắc xác minh source commit, build identity, signature, artifact digest, SBOM subject và ngoại lệ. Chỉ rõ kết quả “allow”, “deny” và ai được quyền cấp ngoại lệ trong tình huống được phê duyệt. Nêu lý do không thể cho qua chỉ vì scanner hiện không tìm thấy CVE mức Critical.

### Bài tập D — Từ advisory mới đến các pod đang chạy

Một advisory phát hiện ảnh hưởng package J nằm trong nhiều dịch vụ. Hãy mô tả đường truy vết từ package/version → SBOM/image digest → release → cluster/namespace/pod → đội sở hữu. Sau khi update và triển khai, đề xuất cách chứng minh tất cả workload mục tiêu đã chuyển sang digest mới.

## 19. Checklist thực tế cho một bản phát hành

Trước khi tuyên bố một microservice đủ điều kiện phát hành, người phụ trách có thể đối chiếu:

- [ ] Source revision đã được kiểm tra và ghi nhận theo commit SHA cụ thể.
- [ ] Dependency trực tiếp/bắc cầu và build tools có cơ chế kiểm soát phiên bản/nguồn phù hợp.
- [ ] Artifact/image cuối cùng có digest rõ ràng; deployment sẽ sử dụng chính digest đó.
- [ ] SBOM được sinh từ đầu vào/bản build phù hợp và gắn với artifact digest.
- [ ] SCA/image scan đã xử lý các finding theo policy; ngoại lệ được phê duyệt và còn hạn.
- [ ] Test nghiệp vụ, tích hợp, contract và kiểm thử hồi quy cần thiết đã chạy.
- [ ] Provenance/attestation phản ánh đúng source, builder và subject digest.
- [ ] Artifact được ký hoặc chứng thực bằng identity được tổ chức tin cậy.
- [ ] Bên triển khai xác minh chữ ký, provenance, digest và chính sách độc lập.
- [ ] Registry, CI và deployment sử dụng quyền tối thiểu cần thiết; secret không đi vào log.
- [ ] Inventory có khả năng xác định image digest cuối cùng đang chạy theo môi trường.
- [ ] Có cơ chế tiếp nhận advisory mới và kế hoạch remediation sau khi phát hành.

Checklist là công cụ vận hành, không thay thế risk assessment hoặc quy định riêng của dự án. Điều kiện phát hành cần điều chỉnh theo mức nhạy cảm của dịch vụ và bối cảnh tuân thủ.

## 20. Tổng kết

Bảo mật chuỗi cung ứng của microservices được hình thành bằng **ba đường liên kết có thể kiểm chứng**:

- **Thành phần:** kiểm kê đúng dependency, phiên bản, quan hệ và các lớp phần mềm thực sự nằm trong artifact.
- **Rủi ro:** phát hiện advisory, đánh giá khả năng khai thác theo môi trường, khắc phục có bằng chứng và giám sát tiếp khi đã deploy.
- **Nguồn gốc:** ràng buộc code, build, SBOM, scan, chữ ký, provenance và deployment vào cùng artifact digest cùng identity được tin cậy.

Một bản phát hành không được xem là an toàn chỉ vì “scan xanh”, chỉ vì “có chữ ký” hoặc chỉ vì “được build từ nhánh chính”. Sự tin cậy có ý nghĩa khi nhóm vận hành có thể trả lời chính xác **gói nào đang chạy, được tạo từ đâu, chứa những gì, có rủi ro nào đang được xử lý và bằng chứng nào chứng minh các kết luận đó**.
