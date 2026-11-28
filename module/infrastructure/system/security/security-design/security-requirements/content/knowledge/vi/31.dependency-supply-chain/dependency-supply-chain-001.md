# Dependency inventory

## 1. Inventory là nền tảng để biết hệ thống phụ thuộc vào những gì

Trong chương **Dependency và supply chain**, dependency inventory là tập thông tin có quản lý về các thành phần phần mềm mà một sản phẩm sử dụng để được xây dựng, đóng gói hoặc vận hành. Một inventory hữu ích phải trả lời được thành phần nào, phiên bản hoặc revision nào, xuất hiện ở đâu, đi vào bằng đường nào và bằng chứng nào hỗ trợ kết luận đó.

Khi có thông tin một thư viện bị xâm nhập, câu hỏi đầu tiên thường không phải “công cụ có phát hiện lỗ hổng không?” mà là:

- Sản phẩm nào chứa hoặc sử dụng đúng thành phần đó?
- Bản phát hành và deployment nào liên quan?
- Nó là dependency trực tiếp, bắc cầu, công cụ build hay plugin được nạp thêm?
- Ai có trách nhiệm xác nhận và xử lý?
- Phần nào của câu trả lời còn chưa được kiểm chứng?

Một file khai báo dependency trong repository chưa trả lời đủ những câu hỏi này. Nội dung được resolve trong một lần build, nội dung thực sự đóng gói và thành phần được nạp tại runtime có thể khác nhau.

Trong module yêu cầu bảo mật, cần chuyển mục tiêu “quản lý đầy đủ dependency” thành chuỗi có thể kiểm chứng:

**Rủi ro thiếu nhận diện → phạm vi inventory → định danh và quan hệ → nguồn bằng chứng → điều kiện chấp nhận → truy vấn phục vụ ứng phó.**

Sau bài học, người học có thể:

- Phân biệt inventory, manifest, dependency graph, SBOM và provenance.
- Đặc tả phạm vi cho dependency trực tiếp, bắc cầu, build, runtime và thành phần nhúng.
- Thiết kế định danh, liên kết artifact/deployment và biểu diễn mức độ chưa biết.
- Viết yêu cầu về tạo mới, cập nhật, truy vấn, bảo vệ và phục hồi inventory.
- Xây dựng tiêu chí kiểm thử có dữ liệu đối chứng, không chỉ kiểm tra công cụ chạy thành công.

Các tên package, digest, ngưỡng thời gian và quy mô bên dưới là ví dụ học tập, không phải dữ liệu của một sản phẩm thật hoặc chuẩn bắt buộc cho mọi dự án.

## 2. Phân biệt các loại thông tin thường bị gộp chung

| Khái niệm | Câu hỏi chính | Giới hạn cần nhận biết |
|---|---|---|
| Manifest khai báo | Dự án yêu cầu những dependency và ràng buộc nào? | Có thể chứa khoảng phiên bản, profile, điều kiện và khai báo không được đóng gói |
| Kết quả resolve | Lần build cụ thể đã chọn những phiên bản và artifact nào? | Không tự chứng minh tất cả thành phần ấy đi vào gói phát hành |
| Dependency graph | Thành phần nào phụ thuộc vào thành phần nào? | Một graph thiếu node hoặc cạnh vẫn có thể hợp lệ về cú pháp |
| SBOM | Tài liệu trao đổi mô tả thành phần và quan hệ trong phạm vi được công bố | Phải gắn với subject, thời điểm, phạm vi và cách tạo; có file không đồng nghĩa đã đầy đủ |
| Dependency inventory | Hệ thống quản lý và truy vấn những bản ghi liên quan đến sản phẩm, artifact và vận hành | Cần giữ lịch sử và bằng chứng, tránh biến thành danh sách tên toàn tổ chức |
| Provenance | Artifact được tạo ra từ đâu, khi nào và bằng quy trình nào? | Không tự thay thế mô tả thành phần của artifact |
| Kết quả đánh giá rủi ro | Thành phần có cảnh báo gì và tác động trong bối cảnh nào? | Thông tin này thay đổi độc lập với danh sách thành phần của artifact bất biến |

SPDX cung cấp mô hình biểu diễn package, file và các quan hệ giữa chúng. CycloneDX có mô hình cho component, dependency, service và thông tin về mức độ đầy đủ của thành phần được mô tả. Khi chọn định dạng trao đổi, cần dùng đúng phiên bản schema và profile đã thống nhất. [SPDX: Composition of a document](https://spdx.github.io/spdx-spec/v2.3.1/composition-of-an-SPDX-document/), [CycloneDX: Specification overview](https://www.cyclonedx.org/specification/overview/)

Provenance mô tả nguồn gốc và quá trình tạo artifact; trong SLSA, thông tin này phục vụ truy vết về nguồn và quy trình sản xuất phần mềm. Inventory cần liên kết tới bằng chứng đó khi có, thay vì dùng một danh sách component để suy ra build đáng tin cậy. [SLSA: Provenance](https://slsa.dev/spec/v1.2/provenance)

Một inventory không có cảnh báo lỗ hổng vẫn có thể thiếu thành phần. Ngược lại, một component có mặt trong inventory chưa đủ kết luận một lỗ hổng cụ thể có thể bị khai thác. Reachability, cấu hình và khả năng khai thác thuộc đánh giá tiếp theo; không xóa component khỏi inventory chỉ vì đang cho rằng nó không bị ảnh hưởng.

## 3. Định nghĩa phạm vi trước khi yêu cầu “đầy đủ”

### 3.1. Các lớp cần xem xét

| Lớp | Thành phần minh họa | Lý do cần được nhận diện |
|---|---|---|
| Ứng dụng | Thư viện được tham chiếu trực tiếp | Liên quan tới chức năng và dữ liệu của ứng dụng |
| Dependency bắc cầu | Parser do một SDK kéo vào | Không có trong khai báo trực tiếp nhưng có thể đi vào gói phát hành |
| Build | Compiler extension, plugin, annotation processor, công cụ sinh mã | Có thể ảnh hưởng nội dung đầu ra hoặc môi trường build |
| Test | Thư viện và công cụ chỉ dùng khi kiểm thử | Có quyền trong pipeline dù không cần tồn tại trong gói production |
| Runtime nền | JRE, native library, package hệ điều hành trong image | Có thể tạo rủi ro ở ngoài graph thư viện ứng dụng |
| Đóng gói | Code vendored, thư viện nhúng, binary bên thứ ba | Có thể không xuất hiện trong package manager |
| Runtime động | Plugin, agent hoặc module tải sau triển khai | Có thể xuất hiện sau khi SBOM của gói gốc đã được tạo |
| Thành phần triển khai liên quan | Sidecar hoặc image phụ trợ | Có vòng đời artifact riêng nhưng cùng tham gia cung cấp dịch vụ |

Phạm vi không nhất thiết gộp mọi lớp thành một tài liệu. Có thể dùng inventory ứng dụng, inventory môi trường build và inventory runtime riêng, rồi liên kết bằng subject, build ID và deployment.

Dịch vụ SaaS hoặc API bên ngoài cũng là phụ thuộc kiến trúc, nhưng không mặc nhiên là package nằm trong artifact của mình. Nếu theo dõi chúng, cần record loại service và quan hệ tương ứng, không gán một phiên bản thư viện giả để làm đầy bảng.

### 3.2. Trực tiếp, bắc cầu và hiện diện là những chiều khác nhau

“Trực tiếp” mô tả quan hệ với một root được chọn. “Bắc cầu” mô tả đường đi qua thành phần khác. Một thư viện có thể là dependency trực tiếp của module A nhưng là bắc cầu của sản phẩm tổng hợp.

“Có trong artifact” là một kết luận khác, cần bằng chứng đóng gói. “Được nạp tại runtime” lại là một quan sát ở thời điểm khác.

Trong Java, scope, optional dependency, exclusion và cơ chế chọn phiên bản ảnh hưởng kết quả dependency. Không thể chỉ gom mọi phiên bản xuất hiện trong POM rồi coi đó là các thư viện được phát hành. [Maven: Dependency mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)

Ví dụ, một dependency được khai báo để compile có thể được môi trường cung cấp riêng; một thư viện test không được chủ đích đóng gói nhưng vẫn có thể bị gói nhầm. Inventory phải phản ánh bằng chứng của từng giai đoạn, không suy diễn hoàn toàn từ tên scope.

### 3.3. Chốt đơn vị được kiểm kê

Đặc tả cần chỉ rõ inventory đang mô tả:

- Một repository ở commit nào.
- Một lần build với cấu hình và nền tảng nào.
- Một JAR hoặc archive có digest nào.
- Một image cho nền tảng cụ thể nào.
- Một deployment với các instance và plugin nào ở thời điểm quan sát.

Image tag hoặc tên bản phát hành chỉ là nhãn có thể cần phân giải. Với image đa nền tảng, phải phân biệt chỉ mục tổng hợp với image thực tế được chọn cho từng nền tảng. Nếu nội dung khác nhau, không dùng một danh sách package duy nhất rồi bỏ qua khác biệt.

Kernel của host không nên bị ghi như package được đóng gói trong image nếu nó không nằm trong đó. Nó có thể được tham chiếu trong inventory môi trường vận hành theo phạm vi riêng.

## 4. Bắt đầu từ tình huống rủi ro và câu hỏi ứng phó

Xét dịch vụ tài liệu có một thư viện báo cáo, một SDK đồng bộ và image runtime riêng:

```text
documents-service
  -> report-sdk 2.4.0
       -> document-parser 1.7.0
  -> sync-sdk 3.1.0
       -> document-parser 1.7.0

build pipeline
  -> code-generation-plugin 4.3.0

deployment
  -> application image
  -> runtime agent được cấp riêng
```

Các tên và phiên bản đều giả định. Graph này cho thấy cùng một component có thể có nhiều đường đưa vào. Nếu gộp nó theo tên rồi chỉ giữ một parent, nhóm vận hành có thể sửa report-sdk nhưng vẫn còn parser qua sync-sdk.

| Mã rủi ro | Tình huống | Hệ quả |
|---|---|---|
| R-INV-01 | Chỉ ghi dependency trực tiếp | Bỏ sót thành phần bắc cầu cần rà soát |
| R-INV-02 | Gộp theo tên, thiếu ecosystem hoặc nội dung artifact | Nhầm package, phiên bản hoặc biến thể |
| R-INV-03 | SBOM không gắn đúng artifact | Dùng danh sách của lần build khác để quyết định phát hành |
| R-INV-04 | Bỏ qua thành phần nhúng hoặc tải động | Có code thực thi nhưng không truy vết được |
| R-INV-05 | Mất liên kết giữa artifact và deployment | Không biết bản đang chạy ở đâu khi cần ứng phó |
| R-INV-06 | Inventory bị sửa, giả mạo hoặc lộ quá rộng | Quyết định sai hoặc tiết lộ cấu trúc nội bộ |
| R-INV-07 | Không biểu diễn phần chưa xác định | Báo “không có” khi thực tế chưa đủ dữ liệu |
| R-INV-08 | Lịch sử bị ghi đè hoặc xóa sớm | Không điều tra được bản phát hành cũ và không kiểm chứng rollback |

Các câu hỏi chấp nhận nên xuất phát từ rủi ro. Ví dụ, “tìm mọi deployment chứa document-parser 1.7.0” đòi hỏi liên kết component → artifact → release → deployment, không chỉ một cột version trong bảng package.

Nếu câu hỏi là “artifact nào được tạo bằng plugin build bị xâm nhập”, cần thêm liên kết build dependency → build execution → output. Một SBOM chỉ mô tả nội dung đóng gói chưa chắc đủ cho câu hỏi đó.

## 5. Thiết kế định danh, quan hệ và bằng chứng

### 5.1. Định danh phải phù hợp mục đích truy vấn

Một bản ghi có thể cần nhiều lớp định danh:

| Lớp | Dữ liệu cần có trong ví dụ |
|---|---|
| Component logic | Ecosystem, namespace, name, version hoặc revision đã xác định |
| Artifact cụ thể | Thuật toán digest, digest đầy đủ, loại gói và biến thể cần thiết |
| Subject của inventory | Digest của JAR/image hoặc định danh immutable tương ứng |
| Occurrence | Vị trí xuất hiện trong subject, layer hoặc package chứa nó |
| Deployment | Môi trường, đơn vị triển khai, artifact thực tế và thời gian quan sát |
| Bằng chứng | Nguồn dữ liệu, công cụ/phương thức, phiên bản cấu hình và thời điểm thu thập |

Package URL giúp biểu diễn định danh package theo ecosystem với cấu trúc như type, namespace, name, version và qualifier. Ví dụ giả định `pkg:maven/com.example/document-parser@1.7.0` mô tả một package Maven. [Package-URL: Specification](https://github.com/package-url/purl-spec)

Một purl không tự chứng minh những byte nào đã được tải hoặc ai đã phát hành chúng. Cần digest và bằng chứng nguồn riêng theo hợp đồng.

Không dùng đường dẫn `lib/parser.jar` làm định danh duy nhất: hai file cùng tên có thể khác nội dung. Không tự gộp hai artifact chỉ vì cùng group, name và version khi digest khác nhau. Sự khác biệt có thể là biến thể hợp lệ hoặc bất thường cần làm rõ; phải giữ đủ ngữ cảnh để quyết định.

Ngược lại, cùng một digest có thể có nhiều nhãn hoặc nhiều occurrence. Việc giảm trùng dữ liệu phải giữ được quan hệ và vị trí xuất hiện.

### 5.2. Tách thông tin khai báo, đo được và suy luận

Những field dễ bị hiểu nhầm cần có nguồn và trạng thái:

- Version do metadata khai báo không hoàn toàn giống version được xác nhận từ artifact.
- Supplier được ghi trong tài liệu của nhà cung cấp không giống danh tính đã được xác minh.
- Repository tải xuống không mặc nhiên là chủ sở hữu hoặc nhà sản xuất package.
- Không quan sát thấy component được nạp không chứng minh nó không tồn tại trong gói.
- Không có dữ liệu dependency của một SDK đóng không đồng nghĩa SDK đó không có dependency.

Nếu thiếu version nhưng đo được digest, vẫn giữ bản ghi, nêu lý do chưa biết và phạm vi còn phải làm rõ. Không tự bịa version từ tên file.

Nếu chưa có supplier hoặc dữ liệu license đáng tin cậy, biểu diễn trạng thái chưa xác định với nguồn bằng chứng. Việc điền metadata không thay thế quyết định pháp lý hoặc đánh giá quyền sử dụng.

### 5.3. Graph cần giữ đúng ý nghĩa cạnh

Các quan hệ có thể khác nhau:

| Quan hệ khái niệm | Ý nghĩa |
|---|---|
| depends-on | Thành phần A phụ thuộc thành phần B trong ngữ cảnh được chỉ rõ |
| contains | Artifact A chứa thành phần B |
| built-with | Build dùng công cụ hoặc dependency B để tạo đầu ra |
| deployed-as | Bản phát hành hoặc artifact được triển khai vào đơn vị vận hành |
| derived-from | Thành phần đã được biến đổi từ một nguồn khác |
| observed-loaded | Một occurrence được quan sát nạp tại runtime trong khoảng thời gian xác định |

Đây là tên khái niệm nội bộ của bài học. Khi xuất SPDX hoặc CycloneDX, cần ánh xạ sang những quan hệ và cấu trúc thực sự được phiên bản định dạng lựa chọn hỗ trợ; không tự coi các tên trên là enum chuẩn.

Một graph không nhất thiết là cây. Nhiều parent hoặc nhiều đường tới cùng component là thông tin cần giữ. Reference phải trỏ tới node tồn tại hoặc một tài liệu ngoài được định danh rõ; không để cạnh treo mà vẫn báo dữ liệu hoàn chỉnh.

## 6. Hợp đồng dữ liệu cho inventory

### 6.1. Field nào phải có để phục vụ quyết định?

| Nhóm field | Yêu cầu trong baseline minh họa |
|---|---|
| Subject | Loại artifact, định danh bất biến và digest đầy đủ nếu có byte artifact để đo |
| Snapshot | Inventory ID, revision, thời điểm tạo, phạm vi, phương pháp và trạng thái hoàn tất |
| Component | ID nội bộ ổn định trong snapshot, ecosystem/name, version hoặc trạng thái chưa biết |
| Quan hệ | Root, parent/child hoặc liên kết tài liệu; ngữ cảnh build/packaged/runtime |
| Nguồn | Nguồn thu thập, thông tin công cụ, cấu hình liên quan, thời điểm và tham chiếu bằng chứng |
| Chất lượng | Phạm vi đã phân tích, khoảng trống, xung đột và lý do chưa xác định |
| Trách nhiệm | Đội chịu trách nhiệm sản phẩm, người xử lý khoảng trống và hạn xử lý được giao |
| Vận hành | Liên kết release/deployment, lần xác nhận gần nhất và trạng thái hiện tại/lịch sử |

Những field bắt buộc cần có quy tắc cho thiếu, rỗng, sai kiểu và không biết. “Không biết version” là một trạng thái có ý nghĩa, khác với bỏ trống do lỗi đồng bộ.

Đối với thành phần có digest đã đo, cần lưu cả thuật toán và giá trị đầy đủ. Không chấp nhận digest rút gọn làm bằng chứng đối chiếu ở cổng phát hành.

### 6.2. Đoạn trích minh họa

Đây là bản ghi theo schema tự định nghĩa, trích từ một inventory lớn hơn; không phải tài liệu SPDX hoặc CycloneDX hoàn chỉnh. Các digest toàn số lặp chỉ là placeholder học tập, không xác minh một artifact thật.

```json
{
  "inventoryId": "inv-documents-build-208",
  "revision": 1,
  "subject": {
    "release": "documents-service-1.8.0",
    "digest": {
      "algorithm": "SHA-256",
      "value": "2222222222222222222222222222222222222222222222222222222222222222"
    }
  },
  "component": {
    "ref": "cmp-document-parser",
    "purl": "pkg:maven/com.example/document-parser@1.7.0",
    "resolvedVersion": "1.7.0",
    "digest": {
      "algorithm": "SHA-256",
      "value": "1111111111111111111111111111111111111111111111111111111111111111"
    },
    "contexts": ["packaged-runtime"],
    "occurrences": [
      {
        "path": "lib/document-parser-1.7.0.jar",
        "evidenceRef": "ev-package-analysis-208"
      }
    ],
    "introducedThrough": ["cmp-report-sdk", "cmp-sync-sdk"],
    "supplierAssessment": {
      "status": "unknown",
      "reason": "publisher-identity-not-yet-verified"
    }
  },
  "evidence": {
    "ref": "ev-package-analysis-208",
    "method": "final-artifact-analysis",
    "observedAt": "2026-11-27T03:00:00Z"
  },
  "ownerTeam": "documents-platform"
}
```

Trong snapshot đầy đủ, các reference như `cmp-report-sdk` và `cmp-sync-sdk` phải được phân giải; hai quan hệ không được mất khi hợp nhất dữ liệu.

Đường dẫn occurrence phải chỉ rõ ngữ cảnh của artifact. Nếu thư viện bị shading hoặc code được nhúng vào file khác, không giữ nguyên một đường dẫn JAR không còn tồn tại. Cần bằng chứng nguồn/biến đổi, vị trí được nhận diện và mức tin cậy phù hợp.

## 7. Bộ yêu cầu bảo mật mẫu

### 7.1. Một yêu cầu đầy đủ

**INV-01 — Inventory phải gắn với đúng artifact được phát hành**

- **Rủi ro:** R-INV-03, R-INV-05 và R-INV-08.
- **Phạm vi:** mọi artifact ứng dụng được promote vào production trong pipeline được quản lý.
- **Điều kiện:** sau khi đóng gói hoàn tất, trước khi promote.
- **Yêu cầu:** tạo hoặc xác minh inventory cho chính digest của artifact ứng viên; không chỉ gắn với tên branch, tag hoặc version.
- **Bằng chứng:** subject digest, build execution ID, snapshot inventory, nguồn tạo và kết quả kiểm tra.
- **Khi thiếu hoặc sai liên kết:** không promote artifact đó; không tự dùng inventory của bản “gần giống”.
- **Tiêu chí chấp nhận:** thay một byte của artifact hoặc thay inventory bằng bản của build khác làm kiểm tra liên kết thất bại.
- **Giới hạn:** liên kết digest đúng không tự chứng minh nội dung inventory đầy đủ; điều đó cần các yêu cầu riêng.

Nếu SBOM nhúng nằm bên trong artifact, cần định nghĩa cách nhận diện subject để tránh vòng lặp “nhúng digest của chính file chứa digest”. Một cách là lưu bằng chứng ràng buộc cuối cùng ở ngoài artifact sau khi đóng gói; kiến trúc phải chốt rõ subject và thứ tự tạo.

### 7.2. Các yêu cầu bổ sung

| ID | Yêu cầu trong baseline minh họa | Tiêu chí chấp nhận chính |
|---|---|---|
| INV-02 | Inventory ứng dụng bao phủ dependency trực tiếp và bắc cầu trong phạm vi resolve/packaged đã công bố. | Bộ dữ liệu thử có dependency nhiều tầng và nhiều parent được nhận diện đúng; không chỉ đọc khai báo trực tiếp. |
| INV-03 | Build, test, packaged và runtime là các ngữ cảnh riêng có liên kết. | Plugin build không bị báo là JAR đang chạy; công cụ build vẫn truy vết được tới các output liên quan. |
| INV-04 | Code vendored, thư viện nhúng, native library và artifact không qua package manager phải được nhận diện hoặc ghi khoảng trống rõ. | Một JAR thêm thủ công hoặc code đã shading không bị bỏ qua rồi báo đầy đủ. |
| INV-05 | Định danh phải giữ ecosystem, namespace, phiên bản/revision, biến thể cần thiết và digest đo được. | Package trùng tên khác ecosystem hoặc cùng tọa độ khác digest không bị gộp mất. |
| INV-06 | Mỗi kết luận về hiện diện và version có nguồn bằng chứng, thời điểm và trạng thái xác nhận. | Dữ liệu supplier gửi và quan sát từ artifact được phân biệt; xung đột không bị ghi đè âm thầm. |
| INV-07 | Release liên kết tới artifact bất biến; deployment liên kết tới artifact thực tế và inventory tương ứng. | Truy vấn từ deployment trả đúng bản đang chạy, không chỉ bản mới nhất của repository. |
| INV-08 | Thành phần tải động trong phạm vi loader được quản lý phải được xác minh và đăng ký bền vững trước khi kích hoạt. | Plugin chưa có định danh/bằng chứng bắt buộc không được nạp; không chặn toàn dịch vụ nếu chỉ tính năng plugin tùy chọn bị từ chối. |
| INV-09 | Snapshot công bố phạm vi, trạng thái hoàn tất và khoảng trống; không suy ra “không có” từ “chưa biết”. | SDK không phân tích được có bản ghi và vấn đề cần xử lý; kết quả truy vấn nêu phần chưa đủ dữ liệu. |
| INV-10 | Chỉ nguồn có thẩm quyền được tạo, sửa hoặc xác nhận inventory; lịch sử và bằng chứng được bảo vệ. | Sửa snapshot đã phát hành phải tạo revision mới có audit; không thay nội dung cũ mà giữ nguyên danh tính. |
| INV-11 | Hệ thống hỗ trợ truy vấn component → artifact → deployment → owner và chiều ngược lại. | Kết quả gồm mọi đường đã biết trong dữ liệu đối chứng, không trả thiếu vì chỉ giữ một parent. |
| INV-12 | Có chính sách về độ mới, lưu giữ, thu hồi và khôi phục dữ liệu. | Dữ liệu quá hạn được đánh dấu; rollback và điều tra vẫn truy cập đúng lịch sử đã cam kết. |

Với khoảng trống nhận diện, dự án có thể cho phép ngoại lệ trong phạm vi rủi ro được chấp nhận, có chủ sở hữu, lý do và hạn xử lý. Ngoại lệ không biến inventory thành đầy đủ.

Trong baseline này, sai subject digest hoặc bằng chứng bị sửa không được bỏ qua bằng một ngoại lệ “thiếu metadata”. Phải sửa liên kết/bằng chứng trước khi promote.

## 8. Thu thập và đối soát trong vòng đời phát triển

### 8.1. Kết hợp các nguồn có điểm mạnh khác nhau

Một quy trình khái niệm:

```text
Manifest và cấu hình build
    -> Thu kết quả resolve của đúng lần build
    -> Thu dependency và công cụ build theo phạm vi
    -> Đóng gói artifact cuối
    -> Phân tích nội dung artifact/image
    -> Đối soát, ghi chênh lệch và khoảng trống
    -> Gắn snapshot với subject bất biến
    -> Kiểm tra điều kiện phát hành
    -> Liên kết deployment và bổ sung quan sát runtime
```

Không có nguồn nào trong chuỗi tự giải quyết mọi trường hợp. Kết quả resolve biết phiên bản được chọn; phân tích artifact giúp phát hiện nội dung được thêm hoặc loại khi đóng gói; quan sát runtime giúp thấy plugin hoặc agent xuất hiện sau đó.

Cần ghi cấu hình thu thập và biến thể build. Hai profile, hệ điều hành hoặc kiến trúc khác nhau có thể tạo đầu ra khác dù dùng cùng commit.

### 8.2. Đối soát chênh lệch thay vì cộng mọi danh sách

| Chênh lệch | Câu hỏi cần làm rõ | Hành vi của inventory |
|---|---|---|
| Có khai báo nhưng không resolve | Dependency có điều kiện, bị loại hay cấu hình chưa được kích hoạt? | Giữ ở view khai báo; không tự báo là được đóng gói |
| Có resolve nhưng không thấy trong gói | Nó chỉ dùng build/test, được môi trường cung cấp hay bị loại khi đóng gói? | Ghi ngữ cảnh và bằng chứng; không tự kết luận không liên quan |
| Có trong gói nhưng không có ở graph resolve | File thủ công, thư viện nhúng, vendor SDK hay lỗi thu thập? | Tạo bản ghi cùng khoảng trống; áp dụng cổng chấp nhận phù hợp |
| Có runtime observation nhưng không có ở snapshot artifact | Plugin, agent, sidecar hay drift? | Gắn đúng đơn vị vận hành và điều tra đường đưa vào |
| Cùng tọa độ nhưng khác digest | Khác classifier, build lại, nguồn khác hay artifact bị thay? | Giữ cả bằng chứng, không gộp trước khi giải thích |
| Supplier và phép đo mâu thuẫn | Metadata cũ, artifact khác hay phương pháp nhận diện sai? | Ghi xung đột và người xác nhận; không chọn nguồn chỉ vì mới hơn |

Nếu một máy quét báo không thấy thư viện trong artifact đã shading, không được dùng kết quả âm đó để xóa bằng chứng đáng tin từ quá trình đóng gói. Cần đánh giá giới hạn phương pháp và tạo kết luận có căn cứ.

### 8.3. Dynamic dependency cần điểm thực thi thích hợp

Với plugin tải sau triển khai, chỉ quét image lúc build sẽ không bao phủ trạng thái vận hành.

Trong baseline của ví dụ, loader được quản lý phải kiểm tra định danh, digest, nguồn được cấp và đăng ký occurrence trước khi cho plugin chạy. Yêu cầu này đòi hỏi kiến trúc loader thực thi được, không chỉ một tác vụ đồng bộ báo cáo.

Nếu hệ thống cũ chỉ có khả năng phát hiện sau khi nạp, phải ghi rõ khoảng trễ và giới hạn. Không mô tả nó như cơ chế ngăn thành phần không biết chạy.

Khi plugin bị gỡ, giữ lịch sử lúc bắt đầu/kết thúc và liên kết artifact. Nếu nguồn quan sát mất liên lạc, chuyển trạng thái sang chưa xác nhận thay vì tự kết luận plugin đã biến mất.

## 9. Đặc tả độ mới, chất lượng và truy vấn

### 9.1. Độ mới có nhiều đồng hồ khác nhau

| Thông tin | Mốc cần quản lý |
|---|---|
| Thành phần của artifact bất biến | Lần tạo/phân tích và revision sửa sai của snapshot |
| Liên kết deployment | Lần deployment được chấp nhận và lần xác nhận artifact thực tế |
| Thành phần tải động | Lần đăng ký, nạp, quan sát và gỡ |
| Metadata nhà cung cấp | Lần nhận và lần xác minh thông tin |
| Cảnh báo lỗ hổng liên kết | Thời điểm dữ liệu rủi ro được cập nhật, tách khỏi inventory nội dung |

Không cần tạo một danh sách thành phần khác chỉ vì có cảnh báo mới cho artifact không đổi. Cần cập nhật đánh giá rủi ro và giữ liên kết tới cùng subject.

Nếu phát hiện inventory cũ nhận diện sai component, tạo revision mới cho cùng subject, giữ lịch sử sửa, nguồn bằng chứng và thời điểm. Không thay đổi artifact để hợp thức hóa một bản ghi sai.

### 9.2. Ví dụ mục tiêu đo được

Một dự án có thể chọn các mục tiêu sau:

- Mọi artifact production thuộc phạm vi phải có snapshot vượt cổng kiểm tra trước promote.
- Liên kết deployment phải được đăng ký không quá 15 phút từ sự kiện nền tảng chấp nhận triển khai.
- Ít nhất một lần trong mỗi 24 giờ, đối soát các deployment đang được quản lý với artifact thực tế và đánh dấu quan sát quá hạn.
- Với bộ dữ liệu tối đa 10.000 deployment và tải truy vấn đồng thời đã xác định, 95% truy vấn component → deployment hoàn tất trong 5 giây.
- Lưu snapshot và liên kết đủ cho vòng đời hỗ trợ của release, cộng thời gian điều tra do dự án quy định.

Đây là mục tiêu minh họa cần đo trong môi trường đại diện. “Đối soát mỗi 24 giờ” không tự bảo đảm mọi drift được phát hiện trong 24 giờ nếu nguồn dữ liệu hoặc quá trình thu thập không có cận độ trễ tương ứng.

Liên kết deployment quá hạn phải xuất hiện như một khoảng trống, không bị loại khỏi mẫu số để làm tỷ lệ đẹp hơn. Nếu chưa biết tổng tài sản ngoài phạm vi quản lý, không công bố tỷ lệ như thể đã bao phủ toàn tổ chức.

### 9.3. Tránh số đo gây hiểu lầm

Các chỉ số có ích gồm:

- Số artifact ứng viên có subject binding hợp lệ trên tổng artifact ứng viên thuộc phạm vi.
- Số deployment có liên kết còn được xác nhận trên tổng deployment được nền tảng quản lý ghi nhận.
- Số khoảng trống chưa xử lý theo loại, độ tuổi và chủ sở hữu.
- Số xung đột định danh hoặc bằng chứng đang chờ xác nhận.
- Thời gian trả lời và độ đầy đủ kết quả trên bộ dữ liệu đối chứng.

Không thể tính “100% component thực tế đã được nhận diện” chỉ từ số component công cụ đã tìm được, vì chưa biết phần bị bỏ sót.

## 10. Bảo vệ inventory và khả năng khôi phục

Inventory có thể tiết lộ cấu trúc hệ thống, package nội bộ, phiên bản cũ, vị trí triển khai và tên đội. Cần phân quyền đọc, sửa, export và chia sẻ theo đối tượng.

Nên phân biệt:

- Người tạo hoặc gửi dữ liệu.
- Người xác nhận nguồn và chất lượng.
- Người quyết định phát hành hoặc chấp nhận khoảng trống.
- Người đọc kết quả phục vụ vận hành và ứng phó.

Không lưu credential của repository, token pipeline hoặc secret triển khai trong URL nguồn và log thu thập. Dữ liệu bên ngoài như tên package, path, supplier note cần được kiểm tra và hiển thị an toàn.

### 10.1. Ràng buộc tính toàn vẹn và thẩm quyền

Digest giúp đối chiếu nội dung nhưng không tự xác nhận danh tính người cung cấp. Chữ ký hoặc attestation chỉ có ý nghĩa khi kiểm tra đúng chủ thể ký, phạm vi được cấp, subject và chính sách tin cậy.

Một inventory được ký vẫn có thể thiếu thành phần nếu người tạo hoặc phương pháp thu thập không đầy đủ. Cần kiểm tra thẩm quyền và tính toàn vẹn riêng với chất lượng dữ liệu.

Cổng phát hành phải dùng snapshot đã kiểm tra theo digest và revision, tránh khoảng cách giữa “đã kiểm tra inventory A” và “thực tế lấy inventory B” khi promote.

### 10.2. Sự cố và phục hồi

Nếu kho inventory không khả dụng, baseline có thể ngăn promote mới khi không xác minh được bằng chứng bắt buộc. Không suy ra phải dừng mọi workload đang chạy chỉ vì giao diện inventory tạm thời lỗi.

Cần có bản sao lưu, kiểm thử khôi phục và cơ chế tái lập chỉ mục truy vấn từ dữ liệu bền vững. Snapshot, quan hệ, lịch sử sửa và liên kết deployment đều là đối tượng cần khôi phục; chỉ khôi phục bảng tên package là chưa đủ.

Khi rollback phần mềm, dùng inventory của đúng artifact được khôi phục và ghi một sự kiện triển khai mới. Không cập nhật nhãn “current” rồi làm mất dấu thời gian bản cũ từng hoạt động.

Việc xóa dữ liệu khi hết hạn lưu phải giữ đúng chính sách và các yêu cầu điều tra đang áp dụng. Chính sách lưu giữ cần được chốt bởi dự án; bài học không đặt một thời hạn pháp lý chung.

## 11. Kế hoạch kiểm thử và bằng chứng chấp nhận

Bộ dữ liệu đối chứng nên có ứng dụng thử với thành phần đã biết: trực tiếp, nhiều tầng, nhiều parent, build-only, file thêm thủ công, thành phần nhúng và plugin động. Bằng chứng đối chứng cần độc lập với chính thuật toán đang được kiểm tra.

| Ca | Thiết lập hoặc tác động | Kết quả chấp nhận |
|---|---|---|
| T01 | Một thư viện trực tiếp kéo thêm dependency hai tầng | Nhận diện đủ node và đường phụ thuộc trong phạm vi công bố |
| T02 | Hai SDK cùng đưa vào một parser | Giữ cả hai đường; hợp nhất component không làm mất parent hoặc occurrence |
| T03 | Hai ecosystem có package cùng tên | Không gộp nhầm; truy vấn trả đúng phạm vi ecosystem |
| T04 | Cùng tọa độ/version nhưng có hai digest | Giữ được khác biệt và bằng chứng; không ghi đè âm thầm |
| T05 | Có plugin build và thư viện chỉ dùng test | Ghi đúng context; không tự báo là được đóng gói runtime |
| T06 | Đóng gói thêm JAR ngoài package manager | Phát hiện hoặc công bố khoảng trống, có owner và cổng chấp nhận rõ |
| T07 | Shading, vendored code hoặc SDK đóng | Giữ thông tin nguồn/biến đổi có bằng chứng; phần không xác định không biến thành không có |
| T08 | Thay artifact sau khi tạo inventory | Kiểm tra subject binding thất bại; artifact không được promote |
| T09 | Dùng inventory của build khác nhưng cùng nhãn version | Không chấp nhận nếu subject không khớp |
| T10 | Runtime nạp plugin qua loader được quản lý | Chỉ nạp sau kiểm tra và đăng ký; thiếu bằng chứng bắt buộc bị từ chối |
| T11 | Nguồn quan sát deployment mất liên lạc | Ghi trạng thái chưa xác nhận/quá hạn; không xóa deployment khỏi kết quả |
| T12 | Truy vấn một component tồn tại trong nhiều artifact và deployment | Trả đủ liên kết trong dữ liệu đối chứng, owner và trạng thái bằng chứng |
| T13 | Sửa snapshot đã phát hành bằng tài khoản không có quyền | Bị từ chối; không thay lịch sử, có audit phù hợp |
| T14 | Sửa lỗi nhận diện của snapshot đã phát hành | Tạo revision mới, giữ bản trước và lý do sửa; subject vẫn đúng |
| T15 | Rollback về artifact cũ | Liên kết đúng inventory cũ và giữ cả lịch sử triển khai trước/sau |
| T16 | Xuất rồi nhập dữ liệu qua định dạng đã chọn | Không mất định danh, quan hệ, context hoặc khoảng trống bắt buộc của profile |
| T17 | Khôi phục kho và chỉ mục từ bản sao lưu | Truy vấn lại được snapshot, quan hệ và deployment theo mục tiêu phục hồi đã đặt |
| T18 | Inventory chưa hoàn tất hoặc schema không hợp lệ | Không bị báo như bản hoàn chỉnh; cổng chấp nhận xử lý theo policy |

T16 cần có kiểm tra ngữ nghĩa sau khi kiểm tra schema. Tài liệu JSON đúng cú pháp vẫn có thể chứa reference treo hoặc làm mất quan hệ quan trọng.

### 11.1. Ví dụ Given–When–Then

```gherkin
Given artifact A đã có inventory gắn với digest của A
And một artifact B có cùng nhãn release nhưng khác digest
When pipeline đề nghị promote B bằng inventory của A
Then yêu cầu promote bị từ chối
And không tạo liên kết deployment hợp lệ cho B bằng snapshot đó
And audit ghi subject được đề nghị, snapshot, kết quả và mã lý do
And không thay đổi lịch sử inventory của A
```

Ca dương tương ứng cần chứng minh artifact A với bằng chứng hợp lệ có thể đi qua cổng và được liên kết đúng deployment.

Không chỉ kiểm tra câu lệnh thu thập trả exit code thành công. Cần kiểm tra kết quả có đúng subject, đủ quan hệ đã biết, nêu khoảng trống và hỗ trợ câu hỏi ứng phó đã đặt ra.

## 12. Bài tập: chuyển danh sách thư viện thành yêu cầu inventory

Một nhóm đang duy trì bảng gồm hai cột tên thư viện và version. Bảng được cập nhật khi lập trình viên nhớ sửa; không có dependency bắc cầu, digest, build ID hoặc deployment.

Khi có thông tin một parser có thể bị xâm nhập, nhóm thấy parser không xuất hiện trong bảng và kết luận không bị ảnh hưởng. Sau đó phát hiện nó nằm trong SDK đã đóng gói và một agent tải thêm tại startup.

Hãy viết đặc tả để sửa quy trình:

1. Chốt phạm vi ứng dụng, build, image runtime và thành phần tải động.
2. Định nghĩa subject bất biến, component, occurrence và quan hệ.
3. Chỉ rõ nguồn bằng chứng cho resolved, packaged và observed-runtime.
4. Nêu hành vi khi thiếu version, supplier, quan hệ hoặc kết quả phân tích.
5. Đặt cổng phát hành và yêu cầu đăng ký plugin trước kích hoạt.
6. Thiết kế truy vấn component → artifact → deployment → owner.
7. Thêm tiêu chí về lịch sử sửa, mất liên lạc, rollback và phục hồi.

Một chuỗi truy vết mẫu:

| Mắt xích | Nội dung |
|---|---|
| Rủi ro | R-INV-01 và R-INV-04: parser đi vào gián tiếp hoặc được nạp ngoài gói gốc |
| Yêu cầu | INV-02, INV-04 và INV-08 |
| Kiến trúc | Thu kết quả resolve, phân tích artifact cuối, loader được quản lý |
| Dữ liệu | Định danh component, digest, parent, occurrence, subject và evidence |
| Kiểm thử | T01, T06, T07 và T10 |
| Bằng chứng vận hành | Inventory theo artifact, đăng ký runtime và liên kết deployment còn được xác nhận |

Sản phẩm cần đạt không chỉ là một bảng nhiều dòng hơn. Đó là hợp đồng có thể kiểm chứng về những gì đã biết, những gì còn thiếu và cách đi từ một thành phần tới đúng bản phát hành, hệ thống đang chạy và người chịu trách nhiệm.
