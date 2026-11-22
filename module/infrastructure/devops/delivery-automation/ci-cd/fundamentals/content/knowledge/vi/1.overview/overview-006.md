# Mối liên hệ giữa DevOps, CI/CD và phản hồi từ vận hành

## 1. Vì sao cần nhìn DevOps, CI/CD và vận hành như một hệ thống?

Một thay đổi phần mềm chỉ tạo ra giá trị khi nó được đưa đến người dùng an toàn, hoạt động đúng trong môi trường thực tế và có thể được cải thiện dựa trên kết quả sử dụng. Việc viết mã và hoàn thành kiểm thử mới chỉ là một phần của quá trình đó. Sau khi triển khai, hệ thống vẫn có thể gặp lỗi do dữ liệu thực, tải tăng đột biến, cấu hình môi trường, dịch vụ phụ thuộc hoặc cách người dùng tương tác.

DevOps, CI/CD và phản hồi từ vận hành giải quyết các phần liên kết của cùng một bài toán:

- **DevOps** định hình cách các nhóm phát triển, kiểm thử, bảo mật và vận hành cùng chịu trách nhiệm về vòng đời dịch vụ.
- **CI/CD** cung cấp luồng tự động, có thể lặp lại để kiểm tra, đóng gói và đưa thay đổi qua các môi trường.
- **Phản hồi từ vận hành** cho biết thay đổi có thực sự cải thiện dịch vụ hay tạo ra rủi ro, từ đó dẫn dắt công việc tiếp theo.

Trong phạm vi **DEVOPS_CI_CD_FUNDAMENTALS**, mục tiêu là xây dựng tư duy CI/CD từ sự kiện Git, pipeline dưới dạng mã, build và kiểm thử tự động đến quản lý artifact, môi trường và cổng chất lượng; đồng thời thiết kế phát hành có truy vết, bảo vệ bí mật, xác minh sau triển khai và khả năng quay lui. Những kỹ thuật này phát huy đầy đủ tác dụng khi được đặt trong vòng phản hồi DevOps.

Có thể hình dung vòng đời như sau:

1. Nhóm xác định nhu cầu hoặc vấn đề từ người dùng và hệ thống đang chạy.
2. Nhóm thay đổi mã nguồn, kiểm thử và đưa thay đổi lên Git.
3. Pipeline tự động xác minh thay đổi, tạo artifact và triển khai theo chính sách.
4. Hệ thống được xác minh sau triển khai và tiếp tục được theo dõi.
5. Dữ liệu vận hành quay trở lại backlog, thiết kế, kiểm thử và cách phát hành.

Vòng lặp này giúp rút ngắn thời gian từ khi phát hiện một nhu cầu đến khi cung cấp được thay đổi có ích, đồng thời giảm rủi ro của mỗi lần phát hành.

## 2. Vai trò của từng khái niệm

| Khái niệm | Trọng tâm | Câu hỏi cần trả lời |
|---|---|---|
| DevOps | Con người, quy trình, trách nhiệm chung và khả năng cải tiến toàn vòng đời | Làm thế nào để xây dựng, phát hành và vận hành dịch vụ như một nhóm thống nhất? |
| Continuous Integration (CI) | Tích hợp thay đổi thường xuyên và xác minh tự động | Thay đổi này có tích hợp được với mã hiện tại và có vượt qua các kiểm tra cần thiết không? |
| Continuous Delivery | Giữ phần mềm ở trạng thái sẵn sàng phát hành | Chúng ta có thể phát hành phiên bản đã kiểm tra khi có quyết định phù hợp không? |
| Continuous Deployment | Tự động đưa thay đổi đủ điều kiện vào môi trường sản xuất | Thay đổi đã vượt qua chính sách có thể được triển khai sản xuất tự động không? |
| Phản hồi từ vận hành | Quan sát tác động thực tế và đưa thông tin trở lại quá trình phát triển | Sau khi phát hành, dịch vụ và người dùng đang chịu tác động gì? |

### 2.1. DevOps là cách tổ chức công việc xuyên suốt vòng đời

DevOps không đơn thuần là một chức danh, một nhóm riêng hay tên của một công cụ. Đây là tập hợp nguyên tắc và thực hành giúp các vai trò cùng chịu trách nhiệm về kết quả của dịch vụ.

Một số biểu hiện cụ thể:

- Nhóm phát triển hiểu cách dịch vụ được triển khai, giám sát và khôi phục.
- Nhóm vận hành tham gia sớm vào thiết kế khả năng quan sát, năng lực mở rộng, bảo mật và khả năng phục hồi.
- Nhóm bảo mật đưa kiểm tra và chính sách vào luồng làm việc thay vì chỉ xem xét ở cuối dự án.
- Nhóm cùng dùng dữ liệu về chất lượng, độ tin cậy và trải nghiệm người dùng để quyết định ưu tiên.
- Quy trình phát hành được chuẩn hóa và tự động hóa để giảm thao tác thủ công dễ sai.

DevOps hướng đến việc giảm khoảng cách giữa các công đoạn. Nếu nhóm phát triển chỉ được đánh giá bằng số tính năng hoàn thành còn nhóm vận hành chỉ được đánh giá bằng việc hạn chế thay đổi, hai mục tiêu có thể xung đột. Trách nhiệm chung về độ tin cậy và giá trị dịch vụ giúp các nhóm cân bằng tốc độ với an toàn.

### 2.2. CI giúp phát hiện vấn đề ngay khi tích hợp

Continuous Integration là thực hành đưa các thay đổi nhỏ vào nhánh tích hợp chung thường xuyên, sau đó tự động build và chạy các kiểm tra phù hợp.

Một luồng CI thường bắt đầu khi có pull request hoặc khi mã được đẩy lên nhánh được bảo vệ. Pipeline có thể thực hiện:

- Kiểm tra định dạng, quy tắc mã và kiểu dữ liệu.
- Chạy unit test.
- Chạy kiểm tra thành phần hoặc integration test.
- Phân tích mã tĩnh và dependency để phát hiện rủi ro bảo mật.
- Build ứng dụng hoặc container image.
- Lưu lại kết quả, log và thông tin commit tạo ra lần chạy.

CI hiệu quả khi thay đổi được tích hợp đủ nhỏ và đủ thường xuyên để lỗi dễ khoanh vùng. Một pipeline chỉ chạy theo lịch thưa hoặc chỉ chạy trước ngày phát hành không tạo được vòng phản hồi nhanh như mục tiêu của CI.

CI cũng không có nghĩa là mọi thay đổi đều được triển khai sản xuất. CI trả lời câu hỏi về khả năng tích hợp và chất lượng của thay đổi ở thời điểm kiểm tra.

### 2.3. Continuous Delivery và Continuous Deployment

Hai cách dùng từ Continuous Delivery và Continuous Deployment thường được gọi chung là CD, nhưng có một khác biệt quan trọng:

- **Continuous Delivery** tự động hóa các bước cần thiết để tạo ra phiên bản có thể phát hành. Việc đưa phiên bản vào sản xuất vẫn có thể cần phê duyệt hoặc quyết định nghiệp vụ.
- **Continuous Deployment** tiếp tục tự động hóa đến bước triển khai sản xuất khi thay đổi đã vượt qua tất cả cổng chất lượng và chính sách.

Continuous Delivery phù hợp với tổ chức cần kiểm soát thời điểm phát hành, phối hợp truyền thông hoặc tuân thủ quy trình phê duyệt. Continuous Deployment phù hợp khi tổ chức có bộ kiểm tra tự động đáng tin cậy, khả năng quan sát tốt và cơ chế giảm thiểu tác động đủ trưởng thành.

Cả hai đều cần artifact có thể truy vết, môi trường nhất quán, kiểm tra sau triển khai và phương án xử lý khi có sự cố.

## 3. CI/CD là cơ chế thực thi, DevOps là hệ thống cải tiến

DevOps và CI/CD có quan hệ chặt chẽ nhưng không đồng nghĩa. DevOps xác định cách các nhóm phối hợp và chịu trách nhiệm về kết quả. CI/CD biến những thực hành đã thống nhất thành luồng tự động có thể kiểm tra, lặp lại và đo lường.

Ví dụ, một nhóm có thể dùng công cụ CI để build và chạy test, nhưng vẫn chưa có cách làm DevOps hiệu quả nếu:

- Nhóm phát triển không biết lỗi nào thường xuất hiện sau khi triển khai.
- Nhóm vận hành không thể truy ngược sự cố về commit và artifact tương ứng.
- Các nhóm chỉ bàn giao công việc qua ticket mà không cùng xem xét kết quả.
- Pipeline xanh được xem là bằng chứng duy nhất rằng dịch vụ đang khỏe mạnh.
- Sau sự cố, nhóm chỉ khôi phục dịch vụ mà không chuyển bài học thành kiểm thử hoặc thay đổi thiết kế.

Ngược lại, một nhóm có tinh thần phối hợp tốt nhưng vẫn triển khai thủ công, thiếu kiểm tra lặp lại và không có dấu vết phát hành sẽ khó duy trì tốc độ và độ tin cậy khi hệ thống phát triển.

Mối liên hệ có thể tóm tắt bằng ba lớp:

1. **DevOps định hướng hành vi và trách nhiệm:** cộng tác, tự động hóa, chia sẻ thông tin và cải tiến liên tục.
2. **CI/CD chuẩn hóa đường đi của thay đổi:** kiểm tra, build, quản lý artifact, triển khai và xác minh.
3. **Vận hành cung cấp bằng chứng thực tế:** tình trạng dịch vụ, tác động người dùng, lỗi, tải và độ tin cậy.

Ba lớp này tạo thành vòng lặp thay vì ba hoạt động độc lập.

## 4. Từ sự kiện Git đến luồng phát hành

Git cung cấp các sự kiện có thể dùng làm điểm kích hoạt pipeline. Việc lựa chọn sự kiện cần phản ánh mục đích của từng bước trong vòng đời.

| Sự kiện Git | Mục đích thường gặp | Kiểm tra hoặc hành động phù hợp |
|---|---|---|
| Mở hoặc cập nhật pull request | Đánh giá thay đổi trước khi hợp nhất | Lint, unit test, kiểm tra bảo mật, kiểm tra hợp đồng API |
| Push lên nhánh tích hợp | Xác minh trạng thái mới nhất của mã | Build, integration test, tạo báo cáo chất lượng |
| Merge vào nhánh chính | Tạo phiên bản tích hợp được chấp nhận | Build artifact, lưu metadata, triển khai môi trường kiểm thử |
| Tạo tag phiên bản | Đánh dấu một mốc phát hành | Tạo release record hoặc khởi chạy luồng phát hành theo chính sách |
| Yêu cầu phát hành có kiểm soát | Thực hiện bước cần quyền hoặc quyết định riêng | Phê duyệt môi trường, triển khai production, xác minh sau phát hành |

Không phải sự kiện nào cũng nên chạy toàn bộ pipeline. Kiểm tra nhanh trên pull request giúp phản hồi sớm. Build và kiểm tra tích hợp sau khi hợp nhất xác nhận trạng thái của nhánh chính. Luồng phát hành có thể dùng tag hoặc một thao tác được kiểm soát để xác định phiên bản dự kiến đưa đến môi trường tiếp theo.

Pipeline cần xác định rõ commit nào đang được kiểm tra. Nếu một pull request thay đổi trong lúc pipeline cũ còn chạy, kết quả cũ không được dùng để chứng minh cho nội dung mới. Cổng hợp nhất nên yêu cầu các kiểm tra bắt buộc hoàn tất trên đúng phiên bản thay đổi.

Một luồng khái quát:

~~~mermaid
flowchart TD
    A["Nhu cầu hoặc phản hồi vận hành"] --> B["Thay đổi mã nguồn"]
    B --> C["Push / Pull Request"]
    C --> D["CI: lint, test, scan"]
    D --> E{"Các kiểm tra đạt?"}
    E -- "Không" --> F["Sửa lỗi và chạy lại"]
    F --> B
    E -- "Có" --> G["Merge vào nhánh chính"]
    G --> H["Build artifact bất biến"]
    H --> I["Triển khai môi trường kiểm thử"]
    I --> J["Kiểm tra và cổng chất lượng"]
    J --> K{"Đủ điều kiện phát hành?"}
    K -- "Không" --> F
    K -- "Có" --> L["Phê duyệt hoặc tự động promote"]
    L --> M["Triển khai production"]
    M --> N["Xác minh và quan sát vận hành"]
    N --> O["Phản hồi vào backlog và kiểm thử"]
    O --> A
~~~

Sơ đồ thể hiện luồng tổng quát. Trong thực tế, một hệ thống có thể có nhiều dịch vụ, nhiều nhánh phát hành, bước phê duyệt khác nhau hoặc các đường triển khai độc lập.

## 5. Pipeline dưới dạng mã tạo ra tính nhất quán

Pipeline as Code nghĩa là định nghĩa các bước CI/CD bằng tệp cấu hình được lưu trong hệ thống quản lý phiên bản cùng với mã nguồn hoặc cấu hình hạ tầng liên quan.

Cách làm này mang lại một số lợi ích:

- **Có lịch sử thay đổi:** có thể biết ai thay đổi quy tắc build hoặc phát hành, thay đổi nào được duyệt và vì sao.
- **Có thể review:** thay đổi pipeline đi qua quy trình pull request như thay đổi ứng dụng.
- **Có thể tái tạo:** các môi trường hoặc nhánh có thể dùng chung định nghĩa đã được chuẩn hóa.
- **Có thể kiểm tra:** nhóm có thể phát hiện cấu hình sai, quyền quá rộng hoặc bước kiểm tra bị bỏ qua.
- **Giảm phụ thuộc vào thao tác cá nhân:** kiến thức về cách build và phát hành nằm trong quy trình có thể đọc được.

Một pipeline tốt thường có các đặc điểm sau:

1. Mỗi bước có mục đích rõ ràng và đầu vào, đầu ra xác định.
2. Các bước độc lập có thể chạy song song; bước phụ thuộc phải khai báo thứ tự.
3. Lỗi được báo rõ và lưu log đủ để điều tra.
4. Phiên bản công cụ và dependency quan trọng được kiểm soát.
5. Quyền truy cập được giới hạn theo công việc và môi trường.
6. Pipeline có thể chạy lại an toàn hoặc nhận biết bước nào đã hoàn thành.
7. Các quy tắc quan trọng được bảo vệ bằng quyền ở phía hệ thống Git và nền tảng triển khai, không chỉ dựa vào một dòng cấu hình.

Ví dụ sau là **mã giả mô tả cấu trúc**, không phải cú pháp có thể dán trực tiếp vào một nền tảng CI cụ thể:

~~~yaml
triggers:
  - pull_request
  - push_to_main
  - release_tag

stages:
  validate:
    steps:
      - lint
      - unit_tests
      - static_security_checks

  build:
    depends_on: validate
    steps:
      - build_application
      - build_container_image
      - integration_tests

  publish:
    depends_on: build
    steps:
      - publish_immutable_artifact
      - record_commit_and_artifact_digest

  deploy_staging:
    depends_on: publish
    steps:
      - deploy_the_published_digest
      - run_smoke_and_contract_tests

  promote_production:
    depends_on: deploy_staging
    condition: quality_gates_passed_and_release_authorized
    steps:
      - deploy_the_same_digest

  verify_production:
    depends_on: promote_production
    steps:
      - check_health_and_service_indicators
      - rollback_if_release_policy_requires_it
~~~

Mã giả nhấn mạnh một nguyên tắc: pipeline cần mô tả được mối quan hệ giữa các bước, điều kiện đi tiếp và bằng chứng tạo ra. Khi triển khai trên GitHub Actions, GitLab CI, Jenkins hay một nền tảng khác, cú pháp và cơ chế phân quyền sẽ khác nhau nhưng tư duy thiết kế vẫn tương tự.

## 6. Artifact kết nối build với triển khai

Artifact là đầu ra có thể lưu trữ và triển khai của quá trình build, chẳng hạn gói ứng dụng, binary hoặc container image. Artifact là mắt xích quan trọng để truy vết một thay đổi từ Git đến môi trường đang chạy.

Một nguyên tắc hữu ích là **build một lần, promote cùng một artifact qua các môi trường**:

1. Pipeline build từ một commit đã xác định.
2. Pipeline chạy kiểm thử phù hợp trên artifact hoặc trên đầu ra tương ứng.
3. Artifact được lưu vào registry hoặc kho lưu trữ có kiểm soát.
4. Môi trường staging triển khai đúng artifact đó.
5. Sau khi vượt qua cổng chất lượng, production nhận chính artifact đã được xác minh.

Nếu mỗi môi trường tự build lại từ mã nguồn, đầu ra có thể khác nhau do phiên bản dependency, thời điểm build, biến môi trường hoặc công cụ. Khi đó, kết quả kiểm thử trên staging không còn là bằng chứng trực tiếp cho artifact chạy ở production.

Nhãn phiên bản như **1.4.2** giúp con người đọc dễ hơn nhưng có thể bị ghi đè tùy cấu hình registry. Với việc triển khai, nên lưu định danh bất biến như digest của container image hoặc checksum của gói. Digest giúp xác định chính xác nội dung được triển khai.

Metadata của artifact có thể bao gồm:

- Commit SHA và repository nguồn.
- Phiên bản hoặc số lần chạy pipeline.
- Thời điểm build và công cụ build.
- Danh sách dependency hoặc SBOM nếu quy trình yêu cầu.
- Kết quả kiểm thử và kiểm tra bảo mật.
- Người hoặc danh tính máy đã tạo và phát hành artifact.
- Chữ ký hoặc thông tin provenance khi hệ thống hỗ trợ.

Nhờ đó, khi một phiên bản gây sự cố, nhóm có thể xác định nó được tạo từ thay đổi nào, đã vượt qua kiểm tra nào và đang chạy ở môi trường nào.

## 7. Môi trường và cổng chất lượng liên kết với nhau

Mỗi môi trường có vai trò khác nhau trong việc giảm rủi ro:

| Môi trường | Mục đích chính | Ví dụ kiểm tra |
|---|---|---|
| Local hoặc ephemeral | Phản hồi nhanh cho người phát triển hoặc pull request | Unit test, kiểm tra thành phần, preview |
| Integration hoặc test | Kiểm tra tương tác giữa các thành phần | Integration test, contract test, kiểm tra dữ liệu |
| Staging hoặc pre-production | Mô phỏng gần production và xác nhận khả năng phát hành | Smoke test, migration test, kiểm tra cấu hình, kiểm thử hiệu năng phù hợp |
| Production | Phục vụ người dùng thật | Health check, synthetic test, metrics, logs, traces và SLO |

Môi trường càng gần production càng cần kiểm soát quyền và dữ liệu chặt chẽ. Không nên mặc định rằng staging giống production chỉ vì cùng chạy một artifact. Cấu hình, dịch vụ phụ thuộc, quyền truy cập, dữ liệu và tải có thể khác nhau.

Để giảm sai lệch:

- Giữ cấu hình môi trường trong hệ thống quản lý có kiểm soát.
- Tách cấu hình khỏi artifact; cùng một artifact có thể nhận cấu hình phù hợp với từng môi trường.
- Dùng dữ liệu kiểm thử an toàn, tránh sao chép dữ liệu nhạy cảm thật một cách tùy tiện.
- Tự động tạo và hủy môi trường tạm khi có ích.
- Quản lý hạ tầng bằng mã để thay đổi có thể review và tái tạo.
- Kiểm tra migration và khả năng tương thích khi nhiều phiên bản ứng dụng cùng hoạt động.

### 7.1. Cổng chất lượng là điều kiện để đi tiếp

Quality gate là tập hợp điều kiện cần đạt trước khi pipeline chuyển sang bước tiếp theo. Cổng chất lượng có thể gồm:

- Các kiểm thử bắt buộc thành công.
- Không còn lỗ hổng bảo mật ở mức bị chính sách chặn.
- Artifact có metadata và nguồn gốc hợp lệ.
- Migration đã được kiểm tra.
- Smoke test hoặc contract test thành công.
- Môi trường đích sẵn sàng.
- Có phê duyệt đối với thay đổi cần kiểm soát.
- Các chỉ số sau triển khai nằm trong giới hạn chính sách.

Không nên dùng một ngưỡng duy nhất cho mọi dịch vụ. Một thay đổi giao diện nhỏ và một thay đổi xử lý thanh toán có thể cần mức kiểm soát khác nhau. Cổng chất lượng nên dựa trên rủi ro, mức độ ảnh hưởng và yêu cầu của dịch vụ.

Cổng chất lượng cũng cần hữu ích trong thực tế. Nếu pipeline thường xuyên báo lỗi giả, quá chậm hoặc có quá nhiều ngoại lệ không được giải thích, nhóm sẽ tìm cách bỏ qua nó. Vì vậy, mỗi cổng cần có chủ sở hữu, lý do tồn tại, hướng dẫn xử lý khi thất bại và cách đánh giá lại khi hệ thống thay đổi.

## 8. Bảo mật là một phần của đường phát hành

Pipeline có quyền đọc mã nguồn, tạo artifact và triển khai môi trường. Vì vậy, pipeline cũng là một phần của bề mặt tấn công.

Một số nguyên tắc cơ bản:

- **Không lưu bí mật trong repository:** không commit token, mật khẩu, khóa riêng hoặc tệp cấu hình chứa thông tin xác thực.
- **Dùng kho quản lý bí mật:** lấy thông tin xác thực từ secret manager hoặc cơ chế bảo mật tương đương.
- **Giới hạn quyền:** job chỉ nhận quyền cần thiết; job kiểm tra pull request không nên mặc nhiên có quyền triển khai production.
- **Ưu tiên thông tin xác thực ngắn hạn:** nếu nền tảng hỗ trợ, dùng cơ chế danh tính workload hoặc OIDC để lấy credential tạm thời thay cho khóa dài hạn.
- **Bảo vệ log:** không in bí mật ra log; che giá trị nhạy cảm và giới hạn quyền đọc log.
- **Kiểm soát nguồn pipeline:** bảo vệ nhánh chính, review thay đổi workflow và pin phiên bản action hoặc plugin quan trọng.
- **Tách quyền theo môi trường:** quyền triển khai production cần được cấp riêng và có thể yêu cầu phê duyệt.
- **Có quy trình thu hồi và xoay vòng:** khi bí mật bị lộ hoặc không còn cần thiết, phải có cách vô hiệu hóa và cấp lại.

Bảo mật không nên chỉ là một lần quét ở cuối pipeline. Kiểm tra dependency, mã nguồn, cấu hình container, hạ tầng và quyền triển khai cần được đặt ở những điểm phù hợp trong toàn luồng.

## 9. Phản hồi từ vận hành đóng vòng lặp DevOps

Pipeline cho biết một thay đổi đã vượt qua các bước tự động đã định nghĩa. Vận hành cho biết dịch vụ thực sự hoạt động ra sao sau khi thay đổi được triển khai.

Các nguồn phản hồi phổ biến gồm:

- **Metrics:** số lượng request, tỷ lệ lỗi, độ trễ, mức sử dụng CPU, bộ nhớ, kết nối và hàng đợi.
- **Logs:** sự kiện và thông tin chi tiết về hành vi ứng dụng, lỗi hoặc giao dịch.
- **Traces:** đường đi của một request qua nhiều dịch vụ, giúp tìm thành phần gây chậm hoặc lỗi.
- **Health checks và synthetic tests:** xác minh các chức năng quan trọng theo cách có thể lặp lại.
- **Sự cố và cảnh báo:** dấu hiệu dịch vụ vượt ngưỡng hoặc có nguy cơ ảnh hưởng người dùng.
- **Phản hồi người dùng và bộ phận hỗ trợ:** vấn đề trải nghiệm có thể không xuất hiện trong log hoặc kiểm thử tự động.

Một hệ thống có khả năng quan sát tốt cần giúp nhóm trả lời ít nhất bốn câu hỏi:

1. Dịch vụ có đang hoạt động không?
2. Người dùng đang chịu tác động gì?
3. Thành phần hoặc thay đổi nào có khả năng gây ra vấn đề?
4. Nhóm có thể xác minh việc khắc phục bằng tín hiệu nào?

Để trả lời được, dữ liệu cần có ngữ cảnh. Log hoặc trace nên mang theo các định danh phù hợp như service name, environment, version, commit hoặc release identifier. Không đưa thông tin nhạy cảm của người dùng vào log chỉ để tiện điều tra.

### 9.1. SLO giúp phản hồi gắn với trải nghiệm người dùng

Service Level Indicator (SLI) là phép đo một khía cạnh của chất lượng dịch vụ, chẳng hạn tỷ lệ request thành công hoặc độ trễ. Service Level Objective (SLO) là mục tiêu đặt ra cho SLI trong một khoảng thời gian.

Ví dụ, một dịch vụ có thể theo dõi tỷ lệ request hợp lệ hoàn tất thành công và đặt mục tiêu độ tin cậy theo tháng. Khi mức độ tin cậy giảm, nhóm cần xem xét tác động của thay đổi gần đây, tải, dependency và sự cố đang diễn ra.

Error budget là phần sai lệch cho phép so với mục tiêu SLO trong kỳ. Khi error budget bị tiêu hao nhanh, nhóm có thể giảm tốc độ phát hành tính năng và ưu tiên khắc phục độ tin cậy. Khi dịch vụ ổn định, nhóm có thêm dư địa để thử nghiệm thay đổi. Cách tiếp cận này giúp quyết định phát hành dựa trên sức khỏe dịch vụ thay vì chỉ dựa vào lịch.

SLO cần phản ánh điều người dùng quan tâm. CPU thấp không tự chứng minh một dịch vụ tốt; một API có thể dùng ít CPU nhưng vẫn trả lỗi hoặc phản hồi quá chậm.

### 9.2. Biến sự cố thành cải tiến có thể kiểm chứng

Khi có sự cố, mục tiêu đầu tiên là giảm tác động và khôi phục dịch vụ. Sau đó, nhóm cần tìm hiểu nguyên nhân ở cấp hệ thống, quy trình và điều kiện kích hoạt.

Một vòng phản hồi có ích thường diễn ra như sau:

1. Phát hiện vấn đề qua cảnh báo, synthetic test hoặc phản hồi người dùng.
2. Xác định phạm vi ảnh hưởng và phiên bản đang chạy.
3. Giảm tác động bằng rollback, tắt feature flag, chuyển lưu lượng hoặc biện pháp khẩn cấp phù hợp.
4. Thu thập log, metrics, traces và lịch sử triển khai.
5. Phân tích yếu tố góp phần gây sự cố mà không quy kết cá nhân.
6. Tạo hành động cải tiến có chủ sở hữu, mức ưu tiên và tiêu chí hoàn thành.
7. Bổ sung kiểm thử, cảnh báo, quy tắc pipeline hoặc thay đổi thiết kế để phát hiện sớm vấn đề tương tự.

Nếu một sự cố được xử lý xong nhưng không tạo ra thay đổi nào trong kiểm thử, giám sát hoặc thiết kế, tổ chức có thể tiếp tục gặp lại cùng một dạng lỗi.

## 10. Xác minh sau triển khai và khả năng quay lui

Triển khai thành công ở cấp công cụ chỉ chứng minh rằng thao tác triển khai đã hoàn tất. Nó không chứng minh ứng dụng phục vụ đúng yêu cầu. Vì vậy, sau mỗi lần triển khai cần có bước xác minh phù hợp.

Có thể chia xác minh thành ba lớp:

- **Xác minh kỹ thuật:** process hoạt động, container sẵn sàng, endpoint health trả kết quả hợp lệ.
- **Xác minh chức năng:** các luồng quan trọng như đăng nhập, tạo đơn hoặc truy vấn dữ liệu hoạt động.
- **Xác minh tác động:** tỷ lệ lỗi, độ trễ, lưu lượng, giao dịch thành công và SLO không xấu đi bất thường.

Các chiến lược triển khai giúp kiểm soát phạm vi ảnh hưởng:

| Chiến lược | Cách hoạt động | Khi nào hữu ích |
|---|---|---|
| Rolling deployment | Thay thế từng nhóm instance theo từng đợt | Dịch vụ có nhiều instance và hỗ trợ chạy đồng thời nhiều phiên bản |
| Blue-green | Chuẩn bị môi trường mới rồi chuyển lưu lượng sang môi trường đó | Cần chuyển đổi nhanh và có môi trường song song |
| Canary | Chuyển một phần lưu lượng đến phiên bản mới, quan sát rồi tăng dần | Muốn đánh giá hành vi trên lưu lượng thực với phạm vi ảnh hưởng ban đầu nhỏ |
| Feature flag | Triển khai mã nhưng bật tính năng theo điều kiện hoặc nhóm người dùng | Muốn tách thời điểm triển khai mã khỏi thời điểm mở tính năng |

### 10.1. Rollback cần được chuẩn bị trước

Rollback là đưa dịch vụ về phiên bản hoặc trạng thái đã biết là ổn định. Khả năng quay lui chỉ đáng tin cậy khi nhóm đã chuẩn bị artifact trước đó, biết cách triển khai lại và hiểu tác động của thay đổi dữ liệu.

Cần chú ý đặc biệt đến database migration. Nếu phiên bản mới thay đổi schema theo cách phiên bản cũ không đọc được, quay lui mã nguồn có thể khiến hệ thống tiếp tục lỗi. Một cách triển khai migration an toàn thường dùng các bước tương thích ngược:

1. **Expand:** thêm cột hoặc cấu trúc mới mà phiên bản hiện tại vẫn có thể hoạt động.
2. **Migrate:** chuyển đổi dữ liệu hoặc ghi song song theo kế hoạch.
3. **Switch:** triển khai ứng dụng sử dụng cấu trúc mới sau khi đã xác minh.
4. **Contract:** chỉ loại bỏ cấu trúc cũ khi không còn phiên bản hoặc tiến trình nào cần nó.

Không phải lỗi nào cũng nên rollback. Với một số thay đổi, sửa tiến về phía trước (roll-forward) an toàn hơn, nhất là khi dữ liệu đã được ghi theo định dạng mới. Quyết định cần dựa trên mức độ ảnh hưởng, khả năng tương thích, tính toàn vẹn dữ liệu và thời gian khôi phục.

Rollback cũng nên có điều kiện kích hoạt rõ ràng. Ví dụ: tỷ lệ lỗi vượt ngưỡng trong khoảng quan sát, health check thất bại liên tục hoặc một giao dịch quan trọng không hoàn tất. Tránh tự động rollback chỉ vì một chỉ số nhiễu trong vài giây; chính sách cần cân nhắc thời gian xác nhận và mức độ nghiêm trọng.

## 11. Ví dụ xuyên suốt: phát hành thay đổi cho luồng thanh toán

Giả sử một nhóm phát triển thay đổi cách tính phí vận chuyển trong dịch vụ checkout.

**Trước khi hợp nhất**

- Nhà phát triển tạo pull request và mô tả quy tắc tính phí mới.
- Pipeline chạy lint, unit test cho các trường hợp biên, contract test với dịch vụ đơn hàng và kiểm tra dependency.
- Người review xác nhận thay đổi mã, kiểm thử và ảnh hưởng đến dữ liệu.
- Nếu kiểm tra bắt buộc thất bại, pull request chưa được phép hợp nhất.

**Sau khi hợp nhất**

- Commit trên nhánh chính được build thành container image.
- Pipeline gắn commit SHA, phiên bản build và digest vào metadata.
- Artifact được lưu trong registry; staging triển khai đúng digest đó.
- Integration test và smoke test xác minh luồng tạo đơn, tính phí và phản hồi API.
- Cổng chất lượng kiểm tra kết quả test, bảo mật và các điều kiện phát hành.

**Khi phát hành production**

- Nhóm phê duyệt phiên bản hoặc hệ thống tự động tiếp tục theo chính sách Continuous Deployment.
- Phiên bản mới được đưa vào một phần lưu lượng bằng canary.
- Dashboard theo dõi tỷ lệ thanh toán thành công, lỗi API, độ trễ và các giao dịch có phí vận chuyển bất thường.
- Nếu chỉ số vượt ngưỡng, hệ thống dừng tăng lưu lượng và thực hiện hành động đã định trước; nhóm có thể chuyển về artifact trước đó nếu điều kiện tương thích cho phép.
- Nếu các chỉ số ổn định, lưu lượng được tăng dần đến toàn bộ hệ thống.

**Sau phát hành**

Giả sử nhóm hỗ trợ nhận được phản ánh rằng một số đơn hàng có địa chỉ đặc biệt bị tính phí sai, trong khi unit test hiện tại vẫn xanh. Nhóm đối chiếu thời điểm đơn hàng, phiên bản, log và dữ liệu đầu vào; xác định thiếu trường hợp kiểm thử cho một kiểu địa chỉ. Nhóm bổ sung test hồi quy, sửa quy tắc tính phí và cập nhật dashboard để theo dõi nhóm giao dịch tương ứng.

Ví dụ này cho thấy phản hồi vận hành có thể làm thay đổi cả mã nguồn, bộ kiểm thử, cổng chất lượng và cách quan sát. CI/CD cung cấp đường đi để thay đổi được xác minh và phát hành; DevOps giúp các nhóm cùng xử lý kết quả thực tế.

## 12. Những cách làm khiến vòng lặp bị đứt

| Biểu hiện | Hệ quả | Hướng cải thiện |
|---|---|---|
| Pipeline chỉ chạy trước ngày phát hành | Lỗi tích hợp được phát hiện muộn và khó khoanh vùng | Chạy kiểm tra phù hợp trên pull request và mỗi lần tích hợp |
| Mỗi môi trường tự build lại | Artifact giữa staging và production có thể khác nhau | Build một lần, promote cùng digest |
| Pipeline xanh được coi là đủ | Lỗi cấu hình, tải hoặc hành vi thực tế có thể bị bỏ sót | Thêm xác minh sau triển khai và theo dõi chỉ số dịch vụ |
| Triển khai thủ công không có dấu vết | Khó biết ai triển khai gì, khi nào và bằng artifact nào | Lưu release record, commit, digest và lịch sử triển khai |
| Bí mật được đặt trực tiếp trong tệp cấu hình | Dễ rò rỉ qua Git, log hoặc artifact | Dùng secret manager và quyền ngắn hạn, tối thiểu |
| Cổng chất lượng có quá nhiều ngoại lệ | Nhóm mất niềm tin và bỏ qua kiểm tra | Giảm cảnh báo giả, nêu rõ lý do chặn và chủ sở hữu |
| Rollback chỉ được nghĩ đến khi xảy ra sự cố | Thời gian khôi phục dài hoặc dữ liệu không tương thích | Chuẩn bị artifact cũ, runbook và kiểm tra migration |
| Sự cố chỉ được xử lý tại thời điểm phát sinh | Lỗi tương tự có thể lặp lại | Chuyển bài học thành test, cảnh báo hoặc thay đổi thiết kế |
| Chỉ tối ưu tốc độ triển khai | Số lần phát hành tăng nhưng chất lượng có thể giảm | Cân bằng tốc độ với tỷ lệ lỗi, thời gian khôi phục và trải nghiệm người dùng |

## 13. Đo lường để cải tiến, không chạy theo chỉ số

Một số chỉ số thường dùng để hiểu hiệu quả phát hành và vận hành:

- **Deployment frequency:** tần suất triển khai thành công.
- **Lead time for changes:** thời gian từ khi thay đổi được đưa vào quy trình đến khi chạy trong production.
- **Change failure rate:** tỷ lệ thay đổi dẫn đến suy giảm dịch vụ hoặc cần khắc phục ngoài kế hoạch.
- **Time to restore service:** thời gian khôi phục dịch vụ sau sự cố.

Các chỉ số này thường được dùng cùng nhau. Tăng tần suất triển khai nhưng đồng thời làm tăng lỗi và kéo dài thời gian khôi phục không phải là cải thiện bền vững. Tương tự, giảm số lần triển khai bằng cách gom nhiều thay đổi lớn có thể khiến mỗi lần phát hành khó kiểm tra và khó quay lui hơn.

Nên kết hợp chỉ số quy trình với chỉ số trải nghiệm dịch vụ:

- Tỷ lệ request thành công.
- Độ trễ ở các phân vị phù hợp.
- Tỷ lệ giao dịch hoặc luồng nghiệp vụ hoàn tất.
- Số sự cố ảnh hưởng người dùng.
- Mức tiêu hao error budget.
- Thời gian phát hiện và xử lý cảnh báo.

Mỗi chỉ số cần có định nghĩa, nguồn dữ liệu, phạm vi đo và người chịu trách nhiệm. Không dùng một chỉ số đơn lẻ để xếp hạng cá nhân hoặc tạo động lực che giấu sự cố. Mục tiêu là tìm điểm nghẽn của hệ thống và chọn cải tiến có tác động.

## 14. Phân chia trách nhiệm trong một luồng DevOps

Trách nhiệm có thể khác nhau theo quy mô tổ chức, nhưng các bên cần phối hợp quanh cùng một dịch vụ:

| Vai trò | Đóng góp trong vòng đời |
|---|---|
| Phát triển | Thiết kế, viết mã, unit test, xử lý lỗi và cung cấp thông tin thay đổi |
| Kiểm thử hoặc chất lượng | Thiết kế chiến lược kiểm thử, kiểm tra rủi ro và xác minh luồng nghiệp vụ |
| Nền tảng hoặc DevOps | Cung cấp pipeline, môi trường, công cụ phát hành, khả năng truy vết và tự động hóa |
| Vận hành hoặc SRE | Xác định yêu cầu độ tin cậy, giám sát, cảnh báo, xử lý sự cố và khả năng phục hồi |
| Bảo mật | Định nghĩa chính sách, kiểm tra rủi ro và hướng dẫn bảo vệ chuỗi cung ứng phần mềm |
| Chủ sở hữu sản phẩm | Xác định giá trị, mức độ ưu tiên, tác động người dùng và quyết định phát hành phù hợp |

Một nhóm nhỏ có thể để một người đảm nhiệm nhiều vai trò. Điều quan trọng là trách nhiệm không bị bỏ trống: phải có người chịu trách nhiệm cho chất lượng pipeline, quyền triển khai, cảnh báo, runbook và việc chuyển bài học vận hành thành cải tiến.

## 15. Checklist thiết kế vòng lặp CI/CD có phản hồi

Trước khi xem một luồng CI/CD là đủ trưởng thành cho một dịch vụ, nhóm có thể tự kiểm tra:

**Từ Git đến CI**

- [ ] Pipeline được kích hoạt bởi các sự kiện Git phù hợp.
- [ ] Pull request chạy các kiểm tra bắt buộc trên đúng commit.
- [ ] Nhánh chính có quy tắc bảo vệ và review phù hợp.
- [ ] Kết quả kiểm tra có log và lý do thất bại dễ hiểu.

**Build và artifact**

- [ ] Build có thể tái tạo trong điều kiện đã kiểm soát.
- [ ] Artifact có định danh bất biến và gắn với commit nguồn.
- [ ] Artifact được lưu trong kho có phân quyền.
- [ ] Metadata cần thiết cho kiểm toán và điều tra được lưu lại.

**Môi trường và phát hành**

- [ ] Cấu hình được quản lý riêng và có kiểm soát.
- [ ] Cùng một artifact được promote qua các môi trường.
- [ ] Cổng chất lượng phản ánh rủi ro của dịch vụ.
- [ ] Quyền triển khai production được giới hạn.
- [ ] Có cơ chế phê duyệt hoặc chính sách tự động rõ ràng.

**Bảo mật và truy vết**

- [ ] Bí mật được lấy từ nơi quản lý an toàn.
- [ ] Job có quyền tối thiểu cần thiết.
- [ ] Có thể truy từ release về artifact, pipeline run và commit.
- [ ] Log không làm lộ thông tin nhạy cảm.

**Vận hành và khôi phục**

- [ ] Có health check và kiểm tra chức năng sau triển khai.
- [ ] Có dashboard hoặc cảnh báo cho chỉ số ảnh hưởng người dùng.
- [ ] Có ngưỡng dừng rollout hoặc rollback phù hợp.
- [ ] Artifact trước đó và quy trình khôi phục đã sẵn sàng.
- [ ] Sự cố tạo ra hành động cải tiến có thể kiểm chứng.

Checklist này là điểm bắt đầu để thảo luận, không phải chứng nhận tự động. Mỗi dịch vụ cần chọn mức kiểm soát phù hợp với tác động, kiến trúc, dữ liệu và yêu cầu vận hành.

## 16. Kết luận

DevOps tạo nền tảng cộng tác và trách nhiệm chung trong toàn vòng đời dịch vụ. CI/CD biến cách làm đó thành luồng tự động từ sự kiện Git, kiểm tra, build, quản lý artifact, triển khai đến xác minh. Vận hành cung cấp bằng chứng về tác động thật của thay đổi và đưa bằng chứng ấy trở lại backlog, kiểm thử, thiết kế và chính sách phát hành.

Một vòng lặp chỉ thực sự khép kín khi nhóm có thể trả lời được: thay đổi nào đang chạy, nó được tạo ra như thế nào, đã vượt qua những cổng nào, dịch vụ đang hoạt động ra sao và nhóm sẽ làm gì nếu kết quả không đạt kỳ vọng. Khi những câu trả lời này có thể truy vết và được dùng để cải tiến liên tục, CI/CD trở thành một năng lực vận hành của DevOps thay vì chỉ là một chuỗi lệnh tự động.
