# Kiểm tra đúng phiên bản sẽ được hợp nhất hoặc triển khai

Một pipeline CI xanh chưa chắc chứng minh rằng phiên bản đang chuẩn bị hợp nhất hoặc triển khai đã được kiểm tra. Kết quả kiểm tra chỉ có ý nghĩa khi nó gắn với đúng mã nguồn, đúng kết quả tích hợp và đúng artifact sẽ được đưa tới môi trường đích. Nếu pipeline kiểm tra một commit nhưng thao tác merge tạo ra commit khác, hoặc hệ thống triển khai lấy phiên bản mới nhất của một nhánh thay vì artifact đã được xác minh, nhóm có thể phát hành một phiên bản chưa từng vượt qua các cổng chất lượng đã đặt ra.

Vì vậy, mỗi quyết định merge hoặc deploy cần trả lời được ba câu hỏi: **đang kiểm tra chính xác đối tượng nào, kết quả kiểm tra thuộc về đối tượng nào, và đối tượng được đưa vào môi trường có trùng với đối tượng đã được phê duyệt hay không?** Bài học này trình bày cách xác định phiên bản nguồn, xác minh kết quả merge, liên kết commit với artifact, kiểm soát phát hành và lưu bằng chứng để có thể truy vết hoặc quay lui.

## 1. Vì sao phải xác minh đúng phiên bản?

Trong Git, tên nhánh như main hoặc release/2.x là một tham chiếu có thể di chuyển. Hôm nay main trỏ tới commit A, sau khi một PR được merge nó có thể trỏ tới commit B. Nếu một job chỉ ghi lại tên nhánh mà không ghi commit cụ thể, vài ngày sau nhóm có thể không xác định được chính xác mã nguồn đã được kiểm tra.

Tương tự, một lần chạy CI thành công không tự động chứng minh mọi phiên bản liên quan đều đạt:

- Một commit trên nhánh tính năng có thể chạy tốt riêng lẻ nhưng xung đột với thay đổi mới trên nhánh đích.
- PR có thể được cập nhật sau khi pipeline hoàn tất, khiến kết quả cũ không còn áp dụng cho nội dung hiện tại.
- Nền tảng Git có thể tạo merge commit, squash commit hoặc rebase commit khác với commit đầu PR đã được kiểm tra.
- Một tag có thể bị di chuyển để trỏ sang commit khác.
- Pipeline có thể build artifact từ một commit, nhưng bước deploy lại checkout nhánh main mới nhất và build lại.
- Artifact có thể bị thay thế hoặc ghi đè trong kho lưu trữ sau khi đã được kiểm tra.
- Cấu hình môi trường hoặc dependency ngoài mã nguồn có thể thay đổi giữa lúc kiểm tra và triển khai.

Những tình huống này tạo ra khoảng cách giữa **phiên bản được xác minh** và **phiên bản thực sự được sử dụng**. Mục tiêu của quy trình là thu hẹp khoảng cách đó bằng định danh bất biến, kiểm tra tại đúng điểm tích hợp và truy vết artifact xuyên suốt các môi trường.

## 2. Phân biệt các định danh phiên bản

Không phải mọi chuỗi trông giống số phiên bản đều có cùng ý nghĩa. Cần phân biệt tham chiếu Git, commit, tag, số phiên bản phát hành và định danh artifact.

| Định danh | Ví dụ | Đặc điểm | Cách sử dụng |
|---|---|---|---|
| Tên nhánh | main, release/2.x | Tham chiếu có thể di chuyển khi có commit mới | Chọn dòng phát triển hoặc dòng bảo trì |
| Commit SHA | 4f8c... | Định danh một commit cụ thể trong repository | Gắn kết quả CI, review và provenance với mã nguồn |
| Tag Git | v2.4.1 | Tên tham chiếu tới một đối tượng Git; có thể bị xóa hoặc tạo lại nếu chính sách cho phép | Đánh dấu mốc phát hành, nên bảo vệ và ký khi phù hợp |
| Version ứng dụng | 2.4.1 | Nhãn phiên bản do dự án quản lý | Hiển thị cho người dùng, tương thích và ghi chú phát hành |
| Artifact digest | sha256:... | Hash nội dung của gói hoặc image | Xác định chính xác artifact được lưu và triển khai |
| Pipeline run ID | 982731 | Định danh một lần thực thi pipeline | Tra cứu log, người kích hoạt và kết quả kiểm tra |

### Commit SHA và tên nhánh

Commit SHA xác định một đối tượng commit cụ thể, trong khi tên nhánh biểu thị vị trí hiện tại của dòng phát triển. Khi cần chứng minh một phiên bản đã qua CI, hãy ghi SHA đầy đủ hoặc một định danh đủ để hệ thống tra cứu chính xác. Không nên chỉ ghi "CI của main đã thành công", vì main có thể đã trỏ tới commit khác.

Một commit chứa thông tin về cây nội dung và lịch sử cha của nó. Cùng một nội dung file nhưng khác metadata commit hoặc lịch sử cha có thể tạo ra SHA khác. Do đó, việc so sánh SHA cần được hiểu theo định danh commit trong repository, không chỉ so sánh tên nhánh hoặc thông điệp commit.

### Tag và version ứng dụng

Tag như v2.4.1 thuận tiện cho con người, nhưng tag vẫn là một tham chiếu Git. Nếu quyền ghi tag không được bảo vệ, một tag có thể bị di chuyển để trỏ tới commit khác. Quy trình phát hành nên hạn chế quyền tạo, sửa hoặc xóa tag; có thể yêu cầu tag được ký và kiểm tra chữ ký theo chính sách dự án.

Version ứng dụng cũng không thay thế commit SHA. Một phiên bản 2.4.1 cần có bản ghi rõ nó được tạo từ commit nào và tạo ra artifact nào. Nếu có nhiều bản build cùng mang nhãn 2.4.1, nhãn đó không đủ để xác định duy nhất gói cần triển khai.

### Artifact digest

Artifact digest, thường là SHA-256, định danh nội dung chính xác của một gói, file hoặc container image. Với container registry, nên tham chiếu image bằng digest thay vì chỉ dùng tag như latest hoặc stable. Tag tiện tra cứu, còn digest giúp xác định chính xác nội dung được kéo về.

Commit SHA và artifact digest bổ sung cho nhau: commit cho biết mã nguồn đầu vào; digest cho biết đầu ra đã được tạo ra và sẽ được sử dụng. Một quy trình phát hành đáng tin cậy cần lưu mối liên hệ giữa hai định danh này.

## 3. Kiểm tra commit đầu PR và kết quả merge

Một PR thường có ít nhất hai góc nhìn cần xác minh:

- **Commit đầu PR (head commit):** phiên bản do người tạo PR đề xuất. Nó phù hợp cho việc review nội dung và chạy các kiểm tra trên thay đổi của nhánh nguồn.
- **Kết quả tích hợp dự kiến (merge candidate):** kết quả khi thay đổi được kết hợp với trạng thái hiện tại của nhánh đích. Nó cho biết các thay đổi có hoạt động cùng nhau trong trạng thái sắp được hợp nhất hay không.

Chỉ kiểm tra head commit có thể bỏ sót lỗi tương tác với nhánh đích. Ví dụ, nhánh tính năng thay đổi chữ ký của một hàm, trong khi main vừa có một commit bổ sung lời gọi hàm đó. Nhánh tính năng có thể build thành công riêng, nhưng kết quả sau merge có thể không biên dịch được.

### Kiểm tra theo chiến lược merge

Cách tạo commit sau merge ảnh hưởng đến đối tượng cần xác minh:

| Chiến lược | Kết quả | Điều cần kiểm tra |
|---|---|---|
| Merge commit | Tạo commit mới có các nhánh cha thể hiện việc hợp nhất | Kiểm tra merge candidate chứa cả thay đổi PR và trạng thái nhánh đích |
| Squash merge | Gộp các commit PR thành một commit mới trên nhánh đích | Xác minh nội dung tích hợp và kiểm tra commit kết quả sau khi tạo |
| Rebase merge | Đặt lại các commit PR lên đầu nhánh đích, tạo commit mới | Kiểm tra chuỗi commit sau rebase và kết quả tích hợp cuối cùng |
| Fast-forward | Di chuyển nhánh đích tới commit đã có trên nhánh nguồn | Đảm bảo commit được kiểm tra vẫn chính là commit được đưa lên nhánh đích |

Các nền tảng Git có thể tạo một commit tổng hợp để kiểm tra PR. Định danh và hành vi cụ thể phụ thuộc nền tảng, chiến lược merge và cấu hình pipeline. Nhóm cần hiểu pipeline đang checkout head commit hay merge candidate, sau đó dùng đúng đối tượng làm điều kiện bắt buộc trước khi merge.

### Vì sao cần kiểm tra lại khi nhánh đích thay đổi?

Giả sử PR được kiểm tra khi main ở commit A. Trong lúc người review đang xem xét, một PR khác được merge và main chuyển sang commit B. Kết quả tích hợp dự kiến giữa PR hiện tại với A không chứng minh rằng PR sẽ hoạt động với B.

Có ba cách xử lý thường dùng:

1. Yêu cầu PR cập nhật với nhánh đích rồi chạy lại kiểm tra.
2. Dùng merge queue hoặc merge train để kiểm tra thay đổi trong thứ tự tích hợp dự kiến.
3. Chạy pipeline xác minh trên commit thực tế ngay sau khi merge, đồng thời có quy trình xử lý nếu nhánh chính bị lỗi.

Merge queue đặc biệt hữu ích khi nhiều PR cùng chờ vào một nhánh. Hệ thống tạo ứng viên tích hợp theo thứ tự, chạy kiểm tra trên trạng thái dự kiến và chỉ tiến hành merge khi ứng viên đó đạt. Nếu trạng thái nhánh đích thay đổi, ứng viên cần được tạo hoặc kiểm tra lại theo cơ chế của nền tảng.

## 4. Gắn status check với đúng commit

Kết quả CI phải gắn với commit hoặc merge candidate cụ thể. Status check chỉ có giá trị khi có thể xác định:

- Commit SHA được checkout và kiểm tra.
- PR hoặc nhánh đích liên quan.
- Loại đối tượng đã kiểm tra: head commit, merge candidate hay commit sau merge.
- Pipeline definition và phiên bản công cụ được sử dụng.
- Các job bắt buộc, kết quả từng job và thời điểm hoàn tất.
- Trạng thái có còn hợp lệ với phiên bản PR hiện tại hay không.

Chính sách bảo vệ nhánh nên yêu cầu các status check bắt buộc thành công trên đúng đối tượng mà nền tảng sử dụng để merge. Nếu tên job thay đổi, cấu hình branch protection cũng cần được cập nhật và xác minh. Một tên check cũ bị bỏ quên hoặc check trùng tên có thể khiến quy tắc bảo vệ nhánh không phản ánh ý định ban đầu.

### Tránh dùng kết quả cũ cho nội dung mới

Mỗi lần PR có commit mới, hệ thống cần tạo kết quả kiểm tra mới cho commit đó. Không nên coi trạng thái xanh của commit trước là bằng chứng cho commit sau, dù phần thay đổi mới có vẻ nhỏ.

Các điều kiện cần chú ý:

- Commit mới được push sau khi CI đã hoàn tất.
- PR được cập nhật hoặc rebase lên nhánh đích.
- Nhánh đích thay đổi và tạo ra merge candidate mới.
- Cấu hình pipeline hoặc quality gate thay đổi.
- Dependency lock file, toolchain hoặc file cấu hình build thay đổi.
- Một status check bị bỏ qua, bị hủy hoặc chưa hoàn tất.

Một kết quả "pending", "skipped" hoặc "cancelled" không tương đương với "success". Chính sách merge cần xác định rõ các trạng thái nào được chấp nhận, đặc biệt khi pipeline có job điều kiện hoặc job chạy theo phạm vi file thay đổi.

## 5. Ví dụ kiểm tra merge candidate với GitHub Actions

Ví dụ dưới đây minh họa workflow chạy khi PR được tạo/cập nhật và khi PR đi vào merge queue. Workflow checkout đúng SHA của sự kiện rồi chạy kiểm tra Gradle. Trên GitHub Actions, sự kiện merge_group cho phép workflow tham gia vào quy trình merge queue; nhóm cần bật merge queue và cấu hình required status check tương ứng trong repository.

    name: validate-merge-candidate

    on:
      pull_request:
      merge_group:

    permissions:
      contents: read

    jobs:
      verify:
        name: verify-merge-candidate
        runs-on: ubuntu-latest
        timeout-minutes: 25

        steps:
          - name: Checkout event commit
            uses: actions/checkout@v4
            with:
              ref: ${{ github.sha }}

          - name: Set up JDK
            uses: actions/setup-java@v4
            with:
              distribution: temurin
              java-version: "21"
              cache: gradle

          - name: Verify
            run: ./gradlew --no-daemon check

Một số lưu ý khi dùng ví dụ:

- SHA của sự kiện là định danh cần được kiểm tra; không thay bằng việc checkout tên nhánh main ở giữa workflow.
- Phiên bản JDK phải phù hợp với toolchain và yêu cầu build của dự án.
- Task check cần thực sự bao gồm các kiểm tra bắt buộc mà nhóm muốn dùng làm cổng merge.
- Nếu dự án dùng action trong môi trường yêu cầu kiểm soát chuỗi cung ứng nghiêm ngặt, hãy pin action theo commit SHA đầy đủ và cập nhật theo quy trình đã review.
- Với merge queue, required status check phải khớp chính xác với tên check mà workflow công bố.
- Workflow này chỉ xác minh mã nguồn. Nó chưa tự động chứng minh artifact được deploy sau đó được tạo từ chính commit đã kiểm tra.

Nếu dùng GitLab, có thể cấu hình merged results pipelines hoặc merge trains để kiểm tra kết quả tích hợp dự kiến. Dù dùng nền tảng nào, nguyên tắc vẫn là ghi rõ đối tượng checkout và bảo đảm kết quả được gắn với đúng ứng viên merge.

## 6. Xác định đúng phiên bản khi triển khai

Sau khi merge, quy trình triển khai cần chọn một đầu vào có định danh ổn định. Có hai cách phổ biến:

- Build từ commit đã được hợp nhất, sau đó tạo artifact và lưu digest.
- Lấy artifact đã được build và xác minh trong pipeline trước đó, rồi promote artifact đó qua các môi trường.

Cách thứ hai thường dễ bảo đảm tính nhất quán hơn nếu artifact được lưu bất biến và có provenance đầy đủ. Dù chọn cách nào, bước deploy phải biết chính xác artifact nào sẽ được triển khai.

### Không deploy bằng tên nhánh di động

Một lệnh deploy kiểu "lấy phiên bản mới nhất của main rồi build" có thể chọn commit khác với commit đã được review. Tình huống này thường xảy ra khi deploy được kích hoạt thủ công sau một khoảng thời gian, hoặc pipeline build và deploy chạy tách rời.

Thay vào đó, deployment request nên mang theo các định danh cụ thể:

- Commit SHA nguồn.
- Version ứng dụng hoặc release ID.
- Artifact URI trong kho lưu trữ.
- Artifact digest.
- Môi trường đích.
- Pipeline run đã tạo artifact.
- Kết quả quality gate và thông tin phê duyệt liên quan.

Nếu một release được phát hành thành nhiều thành phần, manifest cần liệt kê từng artifact và digest của chúng. Chỉ lưu một version tổng quát có thể không đủ để xác định chính xác những service hoặc image nào đang chạy.

### Build once, promote many

Một nguyên tắc quan trọng trong quản lý artifact là build một lần rồi promote cùng artifact qua các môi trường. Ví dụ:

1. Commit C được merge vào main.
2. Pipeline build và test commit C.
3. Pipeline tạo container image, tính digest D và lưu image vào registry.
4. Image digest D được triển khai lên môi trường kiểm thử.
5. Sau khi xác minh và được phê duyệt, chính digest D được triển khai lên staging rồi production.

Không nên build lại từ nhãn version giống nhau ở mỗi môi trường, vì đầu ra có thể khác nhau do dependency, toolchain, thời điểm tải thư viện hoặc biến môi trường build. Nếu bắt buộc phải build lại, cần coi đó là artifact mới và chạy lại các kiểm tra áp dụng cho artifact mới.

Cấu hình môi trường như URL dịch vụ, số replica và feature flag có thể khác nhau giữa các môi trường. Những cấu hình này cần được quản lý và truy vết riêng. Build once, promote many không có nghĩa mọi môi trường dùng cùng một cấu hình runtime.

## 7. Kiểm tra nguồn gốc và tính toàn vẹn của artifact

Một artifact đáng tin cậy cần có thể trả lời được nó đến từ đâu và đã trải qua những kiểm tra nào. Thông tin provenance nên liên kết đầu ra với mã nguồn, pipeline và công cụ tạo ra nó.

Một manifest phát hành có thể chứa các trường sau:

    release:
      version: "2.4.1"
      source:
        repository: "org/service"
        commit: "4f8c1d2..."
        ref: "refs/heads/main"
      build:
        pipeline: "ci"
        run_id: "982731"
        toolchain: "JDK 21"
        dependency_lock_hash: "sha256:..."
      artifact:
        uri: "registry.example.com/service"
        digest: "sha256:..."
        media_type: "application/vnd.oci.image.manifest.v1+json"
      verification:
        unit_tests: "passed"
        integration_tests: "passed"
        security_scan: "passed"
        quality_gate: "passed"

Đây là ví dụ minh họa cấu trúc; tên trường và giá trị cần điều chỉnh theo nền tảng của dự án. Không đưa secret hoặc dữ liệu nhạy cảm vào manifest.

### Digest và kiểm tra tính toàn vẹn

Khi tải artifact để triển khai, hệ thống nên xác minh digest nhận được khớp với digest đã ghi nhận sau build. Nếu digest không khớp, phải dừng triển khai và điều tra nguyên nhân. Có thể dùng checksum cho file package hoặc digest của image trong container registry.

Digest chỉ chứng minh nội dung nhận được khớp với nội dung được băm. Nó không tự chứng minh artifact được tạo bởi pipeline đáng tin cậy. Để chứng minh nguồn gốc, có thể bổ sung chữ ký, build attestation hoặc chữ ký provenance từ hệ thống build. Khóa ký cần được bảo vệ và quy trình xác minh chữ ký phải được thực hiện trước khi triển khai.

### Bảo vệ artifact bất biến

Kho artifact cần có chính sách hạn chế ghi đè hoặc xóa phiên bản đã phát hành. Các biện pháp thường dùng gồm:

- Dùng version hoặc đường dẫn lưu trữ duy nhất cho mỗi lần phát hành.
- Bật immutable tag hoặc retention policy nếu registry hỗ trợ.
- Hạn chế quyền publish và quyền xóa artifact.
- Lưu checksum, chữ ký và provenance cùng metadata release.
- Ghi nhận ai hoặc pipeline nào đã xuất bản artifact.
- Có cơ chế lưu giữ artifact đủ lâu cho nhu cầu rollback và kiểm toán.

Không nên dựa vào tag latest để xác định đầu vào production. Nếu vẫn sử dụng tag thân thiện như stable, deployment cần resolve tag thành digest rồi ghi nhận digest đó trong bản ghi triển khai.

## 8. Kiểm tra điều kiện trước khi deploy

Trước khi triển khai, hệ thống cần đánh giá cả artifact và trạng thái môi trường. Một quality gate trước deploy có thể gồm:

| Điều kiện | Câu hỏi cần trả lời | Bằng chứng |
|---|---|---|
| Nguồn gốc | Artifact được tạo từ commit đã được hợp nhất hoặc phê duyệt? | Commit SHA và build provenance |
| Tính toàn vẹn | Artifact tải về có đúng nội dung đã được tạo? | Digest hoặc checksum |
| Chất lượng | Các kiểm tra bắt buộc có thành công? | CI status, test report và quality gate |
| Bảo mật | Artifact có vi phạm chính sách bảo mật? | Kết quả dependency scan, image scan, chữ ký hoặc attestation |
| Tương thích | Artifact có tương thích với runtime và môi trường đích? | Kiểm tra cấu hình, contract và migration |
| Phê duyệt | Có đủ phê duyệt cho môi trường cần kiểm soát? | Approval record và deployment policy |
| Khả năng khôi phục | Có phiên bản ổn định trước đó và cách quay lui? | Digest phiên bản trước, migration và runbook |

Các điều kiện cần được điều chỉnh theo mức độ rủi ro. Một service nội bộ có thể không cần cùng quy trình phê duyệt với hệ thống xử lý thanh toán hoặc dữ liệu quan trọng. Tuy nhiên, định danh artifact và khả năng truy vết vẫn cần được duy trì.

### Quản lý secret và quyền triển khai

Job build kiểm tra mã nguồn không nhất thiết phải có quyền deploy production. Nên tách quyền theo mục đích:

- Job kiểm tra PR chỉ cần quyền đọc repository và chạy test.
- Job publish chỉ được phép ghi vào registry hoặc artifact repository cần thiết.
- Job deploy chỉ được phép truy cập môi trường đích mà nó phụ trách.
- Quyền phê duyệt production được giới hạn cho nhóm hoặc vai trò phù hợp.

Secret triển khai nên được lưu trong secret store của nền tảng hoặc hệ thống quản lý bí mật chuyên dụng. Chỉ truyền secret vào job cần dùng, tránh ghi vào log và không cấp secret production cho workflow chạy mã nguồn không tin cậy từ fork.

## 9. Xác minh sau triển khai phiên bản nào đang chạy

Triển khai thành công ở cấp độ công cụ chỉ cho biết thao tác deploy đã hoàn tất theo báo cáo của nền tảng. Nó chưa chắc chứng minh mọi instance đã chạy đúng phiên bản hoặc ứng dụng hoạt động bình thường.

Sau deploy, nên xác minh:

1. Deployment record ghi đúng release ID, commit SHA và artifact digest.
2. Runtime hoặc endpoint thông tin phiên bản báo đúng build đang chạy.
3. Các instance, pod hoặc worker đã cập nhật tới phiên bản mục tiêu.
4. Readiness và health check đạt.
5. Smoke test hoặc kiểm tra luồng nghiệp vụ quan trọng thành công.
6. Metrics, log và trace không cho thấy dấu hiệu bất thường sau rollout.

Ứng dụng có thể cung cấp endpoint hoặc metadata build chỉ đọc, ví dụ thông tin version, commit và build ID. Không trả secret, biến môi trường nhạy cảm hoặc thông tin nội bộ không cần thiết qua endpoint này.

### Kiểm tra theo từng giai đoạn rollout

Với rolling deployment, canary hoặc blue-green deployment, cần ghi nhận phiên bản của từng nhóm instance. Trong một khoảng thời gian rollout, nhiều phiên bản có thể cùng tồn tại. Hệ thống quan sát cần phân biệt chúng để phát hiện lỗi chỉ xuất hiện trên phiên bản mới.

Nếu một canary nhận lưu lượng nhỏ và có tỷ lệ lỗi tăng cao, hệ thống có thể dừng mở rộng rollout. Việc tự động dừng cần dựa trên ngưỡng đã định nghĩa, khoảng thời gian quan sát và dữ liệu đủ tin cậy. Không nên kết luận thành công chỉ vì tiến trình triển khai đã trả về exit code 0.

## 10. Quay lui đúng artifact đã biết

Rollback là việc đưa hệ thống trở về một trạng thái phát hành trước đó đã được xác định. Để rollback có thể thực hiện nhanh và chính xác, cần lưu artifact digest, release manifest, cấu hình triển khai và thông tin migration của phiên bản trước.

Một quy trình rollback có thể gồm:

1. Xác định release đang gây lỗi và phạm vi ảnh hưởng.
2. Chọn release ổn định gần nhất từ deployment record.
3. Xác minh artifact digest và chữ ký/provenance của release đó.
4. Kiểm tra khả năng tương thích của schema, cấu hình và dữ liệu.
5. Triển khai lại artifact đã biết tới môi trường đích.
6. Xác minh health check, smoke test và metrics sau rollback.
7. Ghi nhận thời điểm, người thực hiện, lý do và kết quả.

Không nên rollback bằng cách checkout một tag có thể đã bị di chuyển hoặc build lại một commit cũ với dependency hiện tại. Hãy dùng artifact bất biến đã được lưu từ lần phát hành trước.

Rollback ứng dụng cũng không tự động đảo ngược database migration. Nếu schema đã thay đổi theo hướng không tương thích, cần migration có khả năng tương thích ngược, chiến lược expand-and-contract hoặc kế hoạch khôi phục dữ liệu riêng. Thiết kế migration cần được xem xét trước khi deploy.

## 11. Tình huống thực tế: PR được kiểm tra nhưng deploy nhầm commit

Một nhóm phát triển service thanh toán có PR thay đổi cách tính phí. CI chạy thành công trên commit H1 của nhánh feature. Trong lúc review, main nhận thêm commit M2 sửa một API dùng chung. PR sau đó được merge bằng squash, tạo commit S3.

Nếu pipeline deploy chỉ ghi "deploy main" rồi checkout trạng thái mới nhất, một commit khác có thể được build trong lúc một PR tiếp theo đã được merge. Khi có sự cố, nhóm sẽ khó xác định artifact đang chạy có chứa thay đổi đã review hay không.

Quy trình được thiết kế lại như sau:

- PR ghi nhận head SHA H1 và chạy kiểm tra.
- Merge queue tạo merge candidate từ trạng thái main hiện tại và PR; pipeline kiểm tra candidate đó.
- Sau khi merge, pipeline trên main ghi nhận commit S3 thực tế.
- Build tạo artifact A với digest D, lưu provenance liên kết S3, pipeline run và kết quả test.
- Staging và production cùng triển khai digest D.
- Deployment record lưu D, S3, môi trường, thời điểm và kết quả xác minh.
- Nếu có lỗi, nhóm chọn digest của release ổn định trước đó để rollback.

Nhờ đó, nhóm có thể lần theo chuỗi từ PR, commit được hợp nhất, artifact được tạo, tới phiên bản đang chạy ở từng môi trường.

## 12. Các lỗi thiết kế thường gặp

| Cách làm | Rủi ro | Điều chỉnh |
|---|---|---|
| Chỉ kiểm tra head commit của PR | Bỏ sót lỗi khi kết hợp với nhánh đích | Kiểm tra merge candidate hoặc dùng merge queue |
| Giữ kết quả CI cũ sau khi PR đổi commit | Merge nội dung chưa được kiểm tra | Gắn status với SHA và yêu cầu chạy lại |
| Chỉ lưu tên nhánh trong log | Không xác định được commit đã chạy | Lưu commit SHA đầy đủ |
| Merge xong mới phát hiện kết quả tích hợp lỗi | Nhánh chính mất ổn định | Kiểm tra ứng viên merge và xác minh sau merge |
| Deploy bằng tag latest | Tag có thể trỏ tới nội dung mới | Resolve và triển khai bằng digest |
| Build lại ở mỗi môi trường | Artifact có thể khác nhau | Build once, promote many |
| Ghi version nhưng không lưu commit | Không truy vết được nguồn mã | Liên kết version với commit SHA |
| Artifact có thể bị ghi đè | Bằng chứng kiểm thử không còn khớp | Bật lưu trữ bất biến và phân quyền |
| Không kiểm tra sau deploy | Không biết runtime thực sự chạy phiên bản nào | Đọc build metadata, health check và smoke test |
| Rollback bằng cách build lại tag cũ | Đầu ra có thể khác lần phát hành ban đầu | Triển khai lại artifact digest đã lưu |
| Job CI có quyền production rộng | Mã nguồn không tin cậy có thể lạm dụng quyền | Tách job và giới hạn secret, permission |

## 13. Checklist trước merge và trước deploy

### Trước khi merge

- [ ] Đã xác định head commit SHA của PR.
- [ ] Pipeline đã kiểm tra đúng commit hoặc merge candidate theo chiến lược merge.
- [ ] Nếu nhánh đích thay đổi, ứng viên tích hợp đã được cập nhật và kiểm tra lại.
- [ ] Các status check bắt buộc đều thành công trên đúng SHA.
- [ ] Không chấp nhận trạng thái pending, skipped hoặc cancelled cho gate bắt buộc.
- [ ] Chính sách branch protection hoặc merge queue được cấu hình đúng.
- [ ] Có thể tra cứu log và test report của lần chạy tương ứng.

### Trước khi deploy

- [ ] Commit nguồn của artifact trùng với release đã được phê duyệt.
- [ ] Artifact digest khớp với metadata được lưu sau build.
- [ ] Provenance và chữ ký được xác minh theo chính sách.
- [ ] Các quality gate và security check bắt buộc đều đạt.
- [ ] Môi trường đích, cấu hình và migration đã được kiểm tra.
- [ ] Phê duyệt cần thiết đã được ghi nhận.
- [ ] Secret và quyền deploy được giới hạn đúng phạm vi.
- [ ] Có artifact ổn định trước đó và kế hoạch rollback.

### Sau khi deploy

- [ ] Deployment record lưu release, commit SHA và artifact digest.
- [ ] Runtime báo đúng phiên bản đang chạy.
- [ ] Các instance hoặc workload đã đạt trạng thái sẵn sàng.
- [ ] Smoke test và kiểm tra nghiệp vụ quan trọng thành công.
- [ ] Metrics, logs và traces được theo dõi trong thời gian xác minh.
- [ ] Nếu rollout bị dừng hoặc rollback, nguyên nhân và kết quả được ghi nhận.

## Kết luận

Xác minh đúng phiên bản là cầu nối giữa CI, tích hợp mã nguồn và phát hành phần mềm. Hãy gắn mỗi kết quả kiểm tra với một commit hoặc merge candidate cụ thể, gắn mỗi artifact với nguồn tạo ra nó bằng provenance và digest, rồi triển khai chính artifact đã được xác minh qua các môi trường. Khi có deployment record và cơ chế xác minh sau triển khai, nhóm có thể biết chính xác phiên bản nào đang chạy, vì sao nó được phép phát hành và cần khôi phục về đâu khi có sự cố.

