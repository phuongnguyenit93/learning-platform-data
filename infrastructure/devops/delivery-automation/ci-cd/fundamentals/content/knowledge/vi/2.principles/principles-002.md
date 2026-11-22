# Giữ nhánh chính ở trạng thái có thể phát hành

Trong CI/CD, nhánh chính (thường có tên main, đôi khi vẫn là master) là điểm tích hợp đáng tin cậy của sản phẩm. Nguyên lý **giữ nhánh chính ở trạng thái có thể phát hành** yêu cầu mọi thay đổi được đưa vào nhánh này phải đi qua một quy trình kiểm tra có thể lặp lại, có bằng chứng và đủ nhanh để nhóm phát hiện vấn đề trước khi chúng tích tụ.

Một nhánh chính có thể phát hành không có nghĩa là phần mềm không còn lỗi, mọi tính năng đều đã bật hoặc mỗi commit đều phải được đưa ngay lên production. Điều đó có nghĩa là nhóm có thể lấy một phiên bản đã được tạo từ nhánh chính, triển khai nó theo quy trình đã định, xác minh hành vi và phát hành có kiểm soát. Những tính năng chưa sẵn sàng có thể được giữ sau feature flag; những thay đổi chưa đạt tiêu chuẩn phải ở ngoài nhánh chính.

Đây là nguyên lý nền tảng của **DEVOPS_CI_CD_FUNDAMENTALS**: kết nối sự kiện Git với pipeline dưới dạng mã, build và kiểm thử tự động, quản lý artifact và môi trường, áp dụng cổng chất lượng, bảo vệ bí mật, duy trì truy vết, xác minh sau triển khai và chuẩn bị khả năng quay lui.

## 1. Vì sao phải giữ nhánh chính luôn có thể phát hành?

Nhánh chính là nơi các thay đổi của nhiều người cùng hội tụ. Nếu mỗi nhánh tính năng tồn tại quá lâu, phần khác biệt giữa chúng ngày càng lớn. Khi hợp nhất, nhóm phải giải quyết xung đột mã nguồn, khác biệt hợp đồng API, thay đổi schema dữ liệu và những giả định đã lệch nhau. Các lỗi tích hợp thường chỉ xuất hiện khi nhiều thay đổi được ghép lại, khiến việc tìm nguyên nhân khó hơn.

Giữ nhánh chính có thể phát hành giúp giảm rủi ro theo bốn cách:

- **Phát hiện sớm:** kiểm tra chạy ngay khi mở hoặc cập nhật pull request (PR), khi phạm vi thay đổi còn nhỏ và tác giả vẫn nhớ rõ ý định.
- **Giảm kích thước lô thay đổi:** nhánh ngắn hạn và PR nhỏ giúp tích hợp thường xuyên, giảm xung đột và rút ngắn thời gian phản hồi.
- **Giới hạn phạm vi sự cố:** mỗi lần hợp nhất đưa vào một lượng thay đổi vừa đủ để truy nguyên. Khi pipeline đỏ, nhóm có thể tập trung vào commit hoặc PR gần nhất.
- **Giữ quyền lựa chọn phát hành:** nhóm có thể triển khai bản đã kiểm chứng vào thời điểm phù hợp, bật tính năng theo nhóm người dùng hoặc quay lại artifact tốt gần nhất.

Nguyên lý này chuyển trọng tâm từ câu hỏi “đã hoàn thành tính năng chưa?” sang “thay đổi này đã tích hợp an toàn và có thể đưa vào phát hành chưa?”. Một tính năng có thể đang phát triển nhưng nhánh chính vẫn phải hoạt động.

## 2. Phân biệt tích hợp, triển khai và phát hành

Ba khái niệm thường bị dùng lẫn lộn:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Tích hợp (integration) | Đưa thay đổi vào dòng mã nguồn chung sau khi vượt qua các kiểm tra bắt buộc | Hợp nhất PR vào main |
| Triển khai (deployment) | Cài đặt một artifact vào một môi trường để nó có thể chạy | Đưa image có digest xác định lên staging |
| Phát hành (release) | Làm cho một phiên bản hoặc tính năng sẵn sàng cho người dùng theo chính sách sản phẩm | Bật feature flag cho 10% người dùng rồi mở rộng |

Một commit trên main có thể đã được tích hợp nhưng chưa được triển khai production. Một artifact có thể đã triển khai lên staging nhưng chưa được phát hành cho người dùng. Việc tách các khái niệm này giúp nhóm tích hợp liên tục mà không buộc phải công bố mọi tính năng ngay lập tức.

**Có thể phát hành** là trạng thái kỹ thuật và vận hành: artifact được tạo từ mã nguồn đã xác định, các cổng chất lượng cần thiết đã đạt, cấu hình môi trường được quản lý, quy trình triển khai có thể thực hiện và có cách xác minh hoặc quay lui. Đây là tiêu chuẩn thực tế hơn lời khẳng định rằng “build thành công”.

## 3. Quy tắc làm việc với Git để giảm rủi ro tích hợp

### 3.1. Giữ nhánh làm việc ngắn hạn và thay đổi nhỏ

Nhánh tính năng nên được tạo từ phiên bản mới nhất của nhánh chính và tồn tại trong thời gian ngắn. Chia công việc thành các PR nhỏ, mỗi PR giải quyết một mục đích có thể mô tả và xem xét độc lập. PR nhỏ giúp reviewer hiểu ý định, đánh giá ảnh hưởng và xác định lỗi nhanh hơn.

Ví dụ, thay vì giữ một nhánh trong nhiều tuần để hoàn thiện toàn bộ luồng thanh toán, nhóm có thể hợp nhất từng phần tương thích: thêm kiểu dữ liệu, bổ sung endpoint chưa bật, thêm xử lý nền, rồi bật tính năng bằng feature flag sau khi xác minh. Ở mỗi bước, phiên bản trên main vẫn phải biên dịch, kiểm thử và chạy được.

Trước khi mở PR, cập nhật nhánh làm việc từ nhánh chính theo quy ước của nhóm. Có thể dùng rebase hoặc merge để đồng bộ; điều quan trọng là giải quyết xung đột trên nhánh làm việc và chạy lại kiểm tra sau khi nội dung thay đổi. Không được xem kết quả CI của commit cũ là bằng chứng cho commit mới.

### 3.2. Dùng PR làm điểm kiểm soát thay đổi

PR cần cung cấp đủ thông tin để người khác đánh giá:

- Mục tiêu và hành vi trước/sau thay đổi.
- Phạm vi ảnh hưởng: API, dữ liệu, cấu hình, quyền truy cập, hạ tầng và các dịch vụ phụ thuộc.
- Cách kiểm thử, kết quả kiểm thử và các tình huống chưa được kiểm tra.
- Cách bật/tắt tính năng, triển khai, theo dõi và quay lui khi thay đổi có ảnh hưởng vận hành.

Reviewer kiểm tra tính đúng đắn, khả năng bảo trì, tương thích ngược, rủi ro bảo mật và mức độ phù hợp với kiến trúc. Với khu vực nhạy cảm, quy tắc CODEOWNERS hoặc cơ chế tương đương có thể yêu cầu người chịu trách nhiệm chuyên môn phê duyệt.

Không nên hợp nhất chỉ vì đã có một lượt phê duyệt. Các kiểm tra phải áp dụng cho đúng commit dự kiến được hợp nhất. Nếu tác giả cập nhật mã sau khi được duyệt, nhóm cần yêu cầu duyệt lại theo chính sách và chạy lại các kiểm tra bị ảnh hưởng.

### 3.3. Bảo vệ nhánh chính bằng chính sách có thể thực thi

Quy ước trong tài liệu chỉ có tác dụng khi nền tảng Git thực thi được. Cấu hình bảo vệ nhánh nên cân nhắc:

- Chỉ cho phép thay đổi qua PR hoặc merge queue.
- Yêu cầu số lượng phê duyệt phù hợp và phê duyệt của chủ sở hữu mã cho khu vực quan trọng.
- Yêu cầu các status check bắt buộc phải thành công trên commit mới nhất.
- Hủy hiệu lực phê duyệt cũ khi có thay đổi mới, nếu chính sách yêu cầu.
- Chặn force push và xóa nhánh chính.
- Giới hạn quyền bypass; mọi ngoại lệ cần có người chịu trách nhiệm và dấu vết kiểm toán.
- Dùng merge queue khi nhiều PR thường xuyên cạnh tranh để hợp nhất, nhằm kiểm tra tổ hợp commit gần với trạng thái sẽ được đưa vào nhánh chính.

Tên và tùy chọn cấu hình khác nhau giữa GitHub, GitLab, Bitbucket và máy chủ Git tự quản. Hãy chọn cơ chế tương đương của nền tảng, sau đó xác minh bằng một PR thử nghiệm rằng nhánh thực sự từ chối hợp nhất khi một kiểm tra bắt buộc thất bại.

Không phải mọi nhóm đều cần cùng một quy tắc. Ví dụ, yêu cầu hai người phê duyệt cho mọi thay đổi tài liệu có thể làm chậm nhóm mà không giảm rủi ro tương ứng. Hãy phân loại khu vực theo mức độ ảnh hưởng và đặt chính sách tương xứng, nhưng không bỏ qua kiểm tra kỹ thuật bắt buộc.

## 4. Thiết kế pipeline bảo đảm chất lượng cho nhánh chính

Pipeline cần phản hồi sớm ở PR và kiểm tra lại trạng thái tích hợp trên nhánh chính. Pipeline được lưu dưới dạng mã, quản lý phiên bản cùng sản phẩm để có thể xem ai đã thay đổi quy trình, thay đổi khi nào và thay đổi đó ảnh hưởng đến lần build nào.

### 4.1. Chạy kiểm tra trên đúng commit

Sự kiện Git thường khởi chạy pipeline:

| Sự kiện | Mục tiêu kiểm tra |
| --- | --- |
| Mở PR hoặc cập nhật PR | Kiểm tra nội dung dự kiến hợp nhất, trả phản hồi nhanh cho tác giả |
| Push lên nhánh chính | Xác nhận trạng thái sau tích hợp và tạo artifact có thể truy vết |
| Tạo tag hoặc yêu cầu phát hành | Xác định phiên bản phát hành và áp dụng các cổng phát hành tương ứng |

Pipeline phải checkout đúng commit SHA được kiểm tra. Không nên dùng một tham chiếu di động như latest để xác định mã nguồn của lần build. Kết quả CI gắn với commit cụ thể; khi commit thay đổi, bằng chứng cũ không còn đủ để cho phép hợp nhất.

### 4.2. Sắp xếp kiểm tra theo tốc độ và mức độ rủi ro

Một chuỗi kiểm tra thực tế có thể gồm:

1. **Kiểm tra cấu trúc và phong cách:** định dạng, lint, quy tắc đặt tên, kiểm tra cấu hình.
2. **Biên dịch và kiểm tra kiểu:** phát hiện lỗi cú pháp, kiểu dữ liệu và phụ thuộc không hợp lệ.
3. **Unit test:** xác minh các hàm và thành phần nhỏ với dữ liệu kiểm soát được.
4. **Integration test và contract test:** kiểm tra tương tác giữa thành phần, dịch vụ, cơ sở dữ liệu và hợp đồng API.
5. **Kiểm tra hệ thống hoặc luồng quan trọng:** xác minh hành vi xuyên suốt ở môi trường gần với thực tế.
6. **Kiểm tra bảo mật và phụ thuộc:** phát hiện secret bị lộ, lỗ hổng trong dependency, mã nguồn hoặc image; áp dụng chính sách giấy phép khi cần.
7. **Kiểm tra artifact và cấu hình triển khai:** xác nhận gói đầu ra, manifest, migration và cấu hình đáp ứng yêu cầu môi trường.

Không nhất thiết chạy mọi kiểm tra nặng trên mỗi lần lưu mã. Có thể chạy nhóm kiểm tra nhanh trước để phản hồi sớm, rồi chạy kiểm tra tích hợp, bảo mật hoặc hiệu năng sâu hơn theo thay đổi và mức rủi ro. Tuy vậy, các kiểm tra bắt buộc để bảo vệ nhánh chính phải được thực thi trước khi hợp nhất hoặc trước khi cho phép phát hành theo chính sách.

Kiểm thử chỉ có giá trị khi đáng tin cậy. Môi trường kiểm thử cần có dữ liệu và phụ thuộc được kiểm soát; test nên độc lập, có kết quả xác định và dọn dẹp tài nguyên sau khi chạy. Test chập chờn (flaky test) làm giảm niềm tin vào pipeline. Khi phát hiện, hãy ghi nhận chủ sở hữu, nguyên nhân và thời hạn xử lý; nếu phải tạm cách ly, cần có biện pháp thay thế để phần rủi ro đó vẫn được kiểm soát. Không biến việc chạy lại cho đến khi xanh thành cách bỏ qua lỗi.

### 4.3. Định nghĩa cổng chất lượng rõ ràng

Cổng chất lượng (quality gate) là tập điều kiện mà thay đổi hoặc artifact phải đạt trước khi đi tiếp. Ví dụ:

- Build và các bộ test bắt buộc thành công.
- Không có secret được phát hiện trong phần thay đổi.
- Không có lỗ hổng ở mức nghiêm trọng bị chính sách chặn.
- Migration có thể chạy theo trình tự triển khai đã thiết kế.
- Các kiểm tra hợp đồng và tương thích API đạt yêu cầu.
- Artifact được tạo, lưu và xác định bằng digest.

Mỗi cổng cần có chủ sở hữu, phạm vi áp dụng, nguồn dữ liệu, tiêu chí pass/fail và cách xử lý ngoại lệ. Tiêu chí phải có thể kiểm tra tự động ở mức phù hợp. Nếu chỉ ghi “mã phải tốt” hoặc “không có lỗi nghiêm trọng” mà không định nghĩa nguồn phát hiện và ngưỡng, cổng sẽ khó thực thi nhất quán.

Không nên đặt một ngưỡng độ phủ kiểm thử duy nhất làm đại diện cho chất lượng. Độ phủ cao vẫn có thể bỏ sót hành vi quan trọng; độ phủ thấp ở một vùng rủi ro cao có thể là dấu hiệu cần bổ sung test. Hãy kết hợp độ phủ với test cho luồng nghiệp vụ, kiểm tra hợp đồng, phân tích bảo mật và đánh giá thay đổi.

### 4.4. Ví dụ luồng pipeline dưới dạng mã

Đoạn dưới đây là mô tả trung lập với nền tảng. Tên khóa và cú pháp cần điều chỉnh theo hệ thống CI đang dùng:

~~~yaml
pipeline:
  on:
    - pull_request
    - push_to_main

  jobs:
    validate:
      steps:
        - checkout: exact_commit_sha
        - install: locked_dependencies
        - run: format_check
        - run: lint
        - run: compile
        - run: unit_tests
        - run: integration_and_contract_tests
        - run: secret_and_dependency_scans

    build:
      needs: [validate]
      only: push_to_main
      steps:
        - build: application
        - package: immutable_artifact
        - calculate: artifact_digest
        - publish: artifact_and_provenance

    verify_staging:
      needs: [build]
      steps:
        - deploy: artifact_by_digest
        - run: smoke_tests
        - verify: health_and_critical_flows

    release:
      needs: [verify_staging]
      when: release_policy_allows
      steps:
        - promote: same_artifact_digest
        - verify: production_health
        - rollback: last_known_good_artifact_if_needed
~~~

Ví dụ thể hiện ba điểm quan trọng: kiểm tra PR trên commit cụ thể; chỉ tạo artifact sau khi các kiểm tra cần thiết đạt; và triển khai cùng một artifact đã xác minh qua các môi trường. Pipeline thực tế có thể tách job, thêm phê duyệt thủ công hoặc triển khai theo tỷ lệ tùy yêu cầu dịch vụ.

## 5. Build một lần, quản lý artifact bất biến

Một lỗi thiết kế phổ biến là build lại mã nguồn ở từng môi trường. Nếu staging và production được build độc lập, chúng có thể nhận artifact khác nhau do dependency thay đổi, thời điểm build, biến môi trường bị trộn vào gói hoặc công cụ build không đồng nhất. Khi đó, việc staging chạy tốt không chứng minh artifact production sẽ chạy tốt.

Quy tắc nên áp dụng là **build một lần và promote cùng một artifact**:

1. Pipeline lấy mã nguồn tại commit SHA xác định.
2. Dependency được khóa phiên bản và build trong môi trường có thể tái lập.
3. Pipeline tạo artifact, chẳng hạn JAR, package hoặc container image.
4. Artifact được lưu trong registry hoặc kho artifact có kiểm soát quyền truy cập.
5. Hệ thống ghi digest, commit SHA, build ID và thông tin provenance.
6. Staging và production nhận cùng artifact theo digest; cấu hình môi trường được cung cấp riêng.

Artifact bất biến nghĩa là nội dung đã phát hành không bị ghi đè dưới cùng một định danh. Tag dễ đọc như 1.8.0 hữu ích cho con người, nhưng digest nội dung mới là định danh chắc chắn cho image hoặc package. Nếu một lần build mới tạo nội dung khác, nó phải có định danh mới.

Metadata nên liên kết artifact với:

- Commit SHA và nhánh nguồn.
- Build ID, phiên bản công cụ và dependency quan trọng.
- Kết quả test và các cổng chất lượng đã đạt.
- Digest, SBOM (danh mục thành phần phần mềm) và provenance nếu quy trình yêu cầu.
- Người hoặc quy trình phê duyệt phát hành.
- Môi trường, thời điểm triển khai và kết quả xác minh.

Nhờ vậy, khi có sự cố, nhóm có thể trả lời: production đang chạy artifact nào, artifact được build từ commit nào, những kiểm tra nào đã chạy và artifact trước đó có thể khôi phục là gì.

## 6. Giữ tính năng chưa hoàn tất ngoài trải nghiệm người dùng

Một nhóm có thể cần hợp nhất mã sớm để giảm nhánh dài hạn, dù tính năng chưa sẵn sàng cho người dùng. Feature flag cho phép tách **triển khai mã** khỏi **bật tính năng**:

- Mã mới được tích hợp nhưng cờ mặc định ở trạng thái tắt.
- Chỉ người dùng nội bộ hoặc nhóm thử nghiệm được phép bật.
- Khi có đủ bằng chứng, mở rộng dần phạm vi sử dụng.
- Nếu có lỗi, tắt cờ để giảm ảnh hưởng trong khi nhóm điều tra.

Feature flag cần có chủ sở hữu, mô tả, giá trị mặc định, quy tắc phân phối và thời hạn xem xét hoặc xóa. Cờ tồn tại lâu có thể tạo ra nhiều nhánh hành vi và làm tăng chi phí kiểm thử. Không dùng feature flag để che giấu một thay đổi phá vỡ tính tương thích hoặc để bỏ qua kiểm tra bảo mật.

Với API và dữ liệu, cần thiết kế tương thích trong giai đoạn chuyển tiếp. Ví dụ, khi đổi tên một trường API, có thể triển khai theo trình tự: thêm trường mới nhưng vẫn đọc trường cũ; cập nhật client; quan sát mức sử dụng trường cũ; sau đó mới loại bỏ trường cũ trong một lần thay đổi riêng. Cách này giúp phiên bản cũ và mới cùng tồn tại trong thời gian triển khai.

Đối với cơ sở dữ liệu, chiến lược **expand–migrate–contract** thường giảm rủi ro:

1. **Expand:** thêm bảng hoặc cột mới theo cách không làm hỏng ứng dụng hiện tại.
2. **Migrate:** chuyển dữ liệu theo lô, có thể chạy lặp an toàn và theo dõi tiến độ.
3. **Switch:** triển khai ứng dụng đọc/ghi theo cấu trúc mới, có bước xác minh.
4. **Contract:** chỉ xóa cấu trúc cũ sau khi xác nhận không còn phiên bản ứng dụng nào phụ thuộc.

Migration phá hủy dữ liệu hoặc không thể đảo ngược cần được xem xét riêng. Quay lui ứng dụng không tự động khôi phục dữ liệu đã biến đổi; vì vậy phải có kế hoạch tương thích, backup và phục hồi được kiểm chứng.

## 7. Quản lý môi trường, bí mật và quyền triển khai

Khả năng phát hành phụ thuộc vào môi trường vận hành. Các môi trường development, test, staging và production nên có mục đích, quyền truy cập và cấu hình được quản lý rõ ràng. Staging cần đủ tương đồng với production để phát hiện vấn đề về kết nối, quyền, migration và cấu hình, nhưng không được sao chép dữ liệu nhạy cảm một cách tùy tiện.

Giữ cấu hình tách khỏi artifact. Cùng một artifact có thể nhận endpoint, giới hạn tài nguyên hoặc feature flag khác nhau theo môi trường thông qua cơ chế cấu hình được kiểm soát. Không đóng gói mật khẩu, token hoặc khóa riêng vào mã nguồn, image hay log.

Pipeline nên tuân thủ nguyên tắc quyền tối thiểu:

- Chỉ cấp quyền đọc hoặc ghi registry, môi trường và repository khi job thực sự cần.
- Ưu tiên thông tin xác thực ngắn hạn hoặc cơ chế OIDC giữa CI và nhà cung cấp đích thay cho khóa dài hạn.
- Không đưa secret production vào job chạy mã từ fork hoặc PR không đáng tin cậy.
- Che dữ liệu nhạy cảm trong log và tránh in toàn bộ môi trường tiến trình.
- Ghi nhận ai hoặc quy trình nào đã phê duyệt và thực hiện triển khai.

Việc một pipeline có thể triển khai production không đồng nghĩa mọi job đều cần quyền production. Tách quyền build, kiểm thử và triển khai giúp giảm hậu quả khi một bước bị xâm nhập hoặc cấu hình sai.

## 8. Phát hành có kiểm soát và xác minh sau triển khai

Đạt quality gate là điều kiện cần; hệ thống vẫn có thể gặp lỗi chỉ xuất hiện trong môi trường thực. Trước khi phát hành, cần xác định tín hiệu xác minh và điều kiện dừng. Sau triển khai, kiểm tra tối thiểu nên bao gồm:

- Ứng dụng khởi động và readiness/liveness probe đạt.
- Endpoint quan trọng phản hồi đúng.
- Kết nối đến cơ sở dữ liệu, message broker và dịch vụ phụ thuộc hoạt động.
- Luồng nghiệp vụ cốt lõi có thể thực hiện.
- Tỷ lệ lỗi, độ trễ, mức sử dụng tài nguyên và hàng đợi không vượt ngưỡng cảnh báo.

Với dịch vụ có rủi ro cao, dùng canary hoặc blue-green deployment. Canary đưa artifact đến một tỷ lệ nhỏ lưu lượng trước, so sánh các chỉ số với baseline rồi mới mở rộng. Blue-green duy trì hai môi trường tương đương và chuyển lưu lượng khi môi trường mới đã được xác minh. Rolling deployment thay thế từng nhóm instance; cần bảo đảm các phiên bản cũ và mới có thể cùng hoạt động trong giai đoạn chuyển tiếp.

Điều kiện tiếp tục hoặc dừng phải được định nghĩa trước, chẳng hạn tỷ lệ lỗi tăng, p95 latency vượt ngưỡng, health check thất bại hoặc luồng thanh toán bị gián đoạn. Nếu điều kiện dừng xảy ra, pipeline hoặc người trực vận hành cần có quyền ngăn mở rộng rollout và chuyển về artifact tốt gần nhất theo runbook.

Quan sát sau triển khai cần gắn với phiên bản. Log, metric, trace và sự kiện deployment nên chứa version hoặc release ID để người vận hành so sánh trước/sau, khoanh vùng thay đổi liên quan và xác định phạm vi ảnh hưởng.

## 9. Khi nhánh chính bị lỗi: khôi phục trạng thái xanh

Một nhánh chính không thể luôn xanh tuyệt đối. Điều tạo nên kỷ luật là cách nhóm phản ứng khi một kiểm tra bắt buộc thất bại hoặc một lỗi được phát hiện sau hợp nhất.

Quy trình xử lý nên rõ ràng:

1. **Dừng đưa thêm thay đổi vào vùng đang lỗi.** Tạm dừng merge nếu lỗi làm mất khả năng build, test hoặc phát hành.
2. **Xác định điểm bắt đầu.** Tìm commit đầu tiên làm pipeline chuyển từ xanh sang đỏ; đối chiếu log và artifact để thu hẹp nguyên nhân.
3. **Chọn sửa hoặc revert.** Nếu có thể sửa nhanh và an toàn, tạo PR khắc phục nhỏ. Nếu thay đổi gây lỗi có thể đảo ngược, revert để khôi phục trạng thái đã biết là tốt.
4. **Chạy lại toàn bộ kiểm tra liên quan.** Không bỏ qua kiểm tra chỉ để làm trạng thái hiển thị chuyển xanh.
5. **Xác minh artifact và môi trường.** Nếu lỗi đã lên production, thực hiện rollback hoặc hotfix theo runbook, sau đó kiểm tra health và luồng nghiệp vụ.
6. **Ghi nhận nguyên nhân và biện pháp ngăn tái diễn.** Bổ sung test, cải thiện cổng chất lượng, sửa quy trình hoặc cập nhật hướng dẫn vận hành.

Ví dụ lệnh revert một commit thông thường:

~~~bash
git revert <commit-sha>
git push origin <recovery-branch>
~~~

Sau đó mở PR khôi phục theo chính sách của nhóm. Với merge commit, cần xác định đúng parent khi revert; không chạy lệnh một cách máy móc vì chọn sai parent có thể tạo ra kết quả không mong muốn.

Rollback production nên triển khai lại artifact đã lưu và đã biết là tốt, theo digest hoặc định danh bất biến. Không nên build lại mã cũ rồi giả định nội dung đầu ra giống hệt. Nếu thay đổi dữ liệu không tương thích, rollback ứng dụng có thể không đủ; cần thực hiện kế hoạch phục hồi dữ liệu hoặc hotfix tương thích.

Nhóm nên thống nhất một quy tắc vận hành: **sửa trạng thái nhánh chính trước khi tiếp tục công việc bình thường**. Việc để pipeline đỏ kéo dài làm suy yếu ý nghĩa của status check và khiến các thay đổi mới khó được đánh giá.

## 10. Ví dụ thực tế: thêm một endpoint mới

Giả sử nhóm cần thêm endpoint tra cứu trạng thái đơn hàng. Thiết kế theo nguyên lý nhánh chính có thể phát hành như sau:

1. Tác giả tạo nhánh ngắn hạn từ main, thêm endpoint ở trạng thái chưa công khai và viết unit test cho quy tắc nghiệp vụ.
2. PR mô tả hợp đồng request/response, quyền truy cập, cách xử lý lỗi và ảnh hưởng đến client. CI chạy lint, compile, unit test, contract test, kiểm tra dependency và secret.
3. Reviewer kiểm tra phân quyền, khả năng tương thích với client hiện có và cách ghi log. Status check bắt buộc đạt trước khi merge.
4. Sau khi hợp nhất, pipeline trên main build một image, gắn commit SHA và digest, lưu provenance cùng kết quả kiểm tra.
5. Pipeline triển khai đúng image đó lên staging, chạy smoke test và thử luồng tra cứu bằng tài khoản có quyền phù hợp.
6. Khi được phép phát hành, cùng digest được triển khai theo canary. Feature flag chỉ mở cho nhóm người dùng thử nghiệm.
7. Nhóm theo dõi tỷ lệ lỗi, độ trễ và log theo release ID. Nếu chỉ số vượt ngưỡng, dừng rollout và tắt flag hoặc quay về artifact tốt gần nhất.
8. Khi luồng hoạt động ổn định, mở rộng flag theo kế hoạch và lên lịch xóa mã cờ tạm thời sau khi không còn cần.

Trong toàn bộ quy trình, nhánh chính luôn có mã có thể build và kiểm thử; tính năng mới chỉ trở nên khả dụng khi đã qua bước xác minh và quyết định phát hành.

## 11. Các dấu hiệu cho thấy nguyên lý chưa được thực hiện tốt

| Dấu hiệu | Rủi ro | Hướng cải thiện |
| --- | --- | --- |
| Nhánh tính năng sống nhiều tuần | Tăng xung đột và chi phí tích hợp | Chia nhỏ thay đổi, hợp nhất thường xuyên |
| Có thể merge khi CI chưa chạy hoặc đang thất bại | Nhánh chính nhận mã chưa được xác minh | Bật required status checks trên commit mới nhất |
| Chỉ chạy test trên máy cá nhân | Thiếu bằng chứng nhất quán và khó tái lập | Đưa kiểm tra cần thiết vào pipeline |
| Build lại ở staging và production | Artifact có thể khác nhau giữa các môi trường | Build một lần, promote theo digest |
| Dùng tag latest để triển khai | Khó xác định chính xác nội dung đang chạy | Ghim phiên bản bất biến hoặc digest |
| Secret được lưu trong repository hoặc log | Có thể lộ quyền truy cập hệ thống | Secret manager, OIDC và quyền tối thiểu |
| Tính năng chưa hoàn tất làm hỏng luồng hiện tại | Tích hợp bị gắn chặt với thời điểm phát hành | Thiết kế tương thích và dùng feature flag đúng cách |
| Pipeline đỏ nhưng nhóm vẫn tiếp tục merge | Mất niềm tin vào quality gate | Dừng merge, khôi phục trạng thái xanh và xử lý nguyên nhân |
| Không biết production đang chạy commit nào | Khó điều tra và rollback | Gắn commit, build ID, digest và release ID vào deployment |
| Chỉ kiểm tra triển khai thành công, không kiểm tra hành vi | Lỗi runtime có thể bị bỏ sót | Smoke test, health check và theo dõi chỉ số sau triển khai |

## 12. Chỉ số để đánh giá hiệu quả

Không nên đánh giá nguyên lý này chỉ bằng số lần pipeline xanh. Một pipeline có thể luôn xanh vì kiểm tra quá ít hoặc vì nhóm thường xuyên bỏ qua lỗi. Hãy kết hợp một số chỉ số:

- **Tỷ lệ pipeline thành công trên nhánh chính:** cho biết mức ổn định của tích hợp, cần phân tích thêm nguyên nhân thất bại.
- **Thời gian khôi phục nhánh chính:** thời gian từ lúc phát hiện trạng thái đỏ đến khi khôi phục được trạng thái có thể phát hành.
- **Thời gian tồn tại của PR và nhánh:** thời gian chờ review, số lần cập nhật và kích thước thay đổi giúp nhận diện nút thắt tích hợp.
- **Lead time for changes:** thời gian từ lúc thay đổi được commit đến khi chạy trong production.
- **Change failure rate:** tỷ lệ thay đổi phát hành gây sự cố cần khắc phục, rollback hoặc hotfix.
- **Tần suất triển khai:** cho thấy khả năng đưa thay đổi đã kiểm chứng đến môi trường đích.

Các chỉ số cần được đọc cùng nhau. Tăng tần suất triển khai mà change failure rate cũng tăng có thể cho thấy kiểm soát chất lượng chưa theo kịp. Giảm thời gian pipeline bằng cách bỏ các kiểm tra quan trọng có thể làm tăng chi phí sự cố về sau. Mục tiêu là phản hồi nhanh, chất lượng có bằng chứng và khả năng phục hồi tốt.

## 13. Checklist áp dụng

Trước khi hợp nhất PR:

- [ ] PR nhỏ, có mục tiêu và mô tả ảnh hưởng rõ ràng.
- [ ] Nhánh làm việc đã đồng bộ với nhánh chính theo quy ước.
- [ ] Review và phê duyệt cần thiết đã hoàn tất.
- [ ] Required checks chạy trên commit mới nhất và đều đạt.
- [ ] Không có secret bị lộ hoặc lỗ hổng bị chính sách chặn.
- [ ] Thay đổi API, dữ liệu và cấu hình tương thích với giai đoạn chuyển tiếp.
- [ ] Tính năng chưa sẵn sàng được kiểm soát bằng cơ chế phù hợp.

Trước khi phát hành:

- [ ] Artifact được build từ commit xác định và có digest bất biến.
- [ ] Kết quả test, provenance và thông tin phiên bản có thể truy vết.
- [ ] Artifact đã được xác minh ở môi trường phù hợp.
- [ ] Cấu hình và secret được cấp theo môi trường với quyền tối thiểu.
- [ ] Có điều kiện tiếp tục/dừng rollout, người chịu trách nhiệm và runbook.
- [ ] Có artifact tốt gần nhất và phương án xử lý migration nếu cần.

Sau khi phát hành:

- [ ] Health check và luồng nghiệp vụ quan trọng đạt.
- [ ] Metric, log và trace có thể liên kết với release ID.
- [ ] Tỷ lệ lỗi, độ trễ và tài nguyên nằm trong ngưỡng vận hành.
- [ ] Rollout được mở rộng hoặc dừng theo tín hiệu đã định nghĩa.
- [ ] Sự cố và ngoại lệ được ghi nhận thành hành động cải tiến cụ thể.

## Kết luận

Giữ nhánh chính ở trạng thái có thể phát hành là kỷ luật liên tục của cả nhóm phát triển và vận hành. Nhánh ngắn hạn, PR nhỏ, review có trách nhiệm, pipeline đáng tin cậy, cổng chất lượng rõ ràng và chính sách bảo vệ Git tạo nên một dòng tích hợp có kiểm soát. Build một lần, quản lý artifact bất biến, tách cấu hình và feature flag, triển khai có xác minh và chuẩn bị rollback giúp nhóm phát hành thường xuyên mà vẫn kiểm soát được rủi ro.

Khi nhánh chính bị lỗi, ưu tiên khôi phục trạng thái có thể phát hành và xử lý nguyên nhân trước khi tiếp tục hợp nhất. Khi mỗi thay đổi đều có commit, kiểm tra, artifact, môi trường và kết quả triển khai có thể truy vết, CI/CD trở thành một quy trình phát hành có bằng chứng thay vì chỉ là chuỗi lệnh tự động.
