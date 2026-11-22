# Thiết kế pipeline tối thiểu trước khi mở rộng

## Mục tiêu học tập

Sau bài này, người học có thể:

- Xác định phạm vi tối thiểu của một pipeline dựa trên loại sản phẩm, rủi ro và cách đội ngũ phát hành phần mềm.
- Thiết kế luồng từ sự kiện Git đến kiểm thử, đóng gói, triển khai và xác minh sau triển khai.
- Phân biệt bước bắt buộc để bảo đảm tính đúng đắn với bước tối ưu hoặc nâng cao có thể bổ sung sau.
- Tổ chức pipeline dưới dạng mã, dùng artifact bất biến, quản lý bí mật và quyền truy cập có kiểm soát.
- Xác định tiêu chí thành công, cách xử lý thất bại và bằng chứng cần có trước khi mở rộng pipeline.
- Nhận diện dấu hiệu pipeline đang quá phức tạp hoặc còn thiếu năng lực quan trọng.

## 1. Vì sao nên bắt đầu bằng pipeline tối thiểu?

Khi xây dựng CI/CD, đội ngũ thường dễ bị cuốn vào danh sách tính năng của nền tảng: ma trận build, nhiều loại kiểm thử, quét bảo mật, ký artifact, nhiều môi trường, canary, blue-green, phê duyệt nhiều cấp, dashboard và hàng loạt tích hợp. Mỗi năng lực có thể hữu ích, nhưng đưa tất cả vào ngay từ đầu làm tăng số lượng cấu hình, điểm lỗi, quyền truy cập và chi phí vận hành.

Một pipeline đầu tiên nên trả lời được câu hỏi cốt lõi: **một thay đổi mã nguồn có thể được kiểm tra, đóng gói và đưa đến môi trường đích theo một quy trình lặp lại, có bằng chứng và có cách xử lý khi thất bại hay không?**

Pipeline tối thiểu không phải pipeline có ít dòng YAML nhất hoặc ít job nhất. Đó là luồng nhỏ nhất vẫn tạo ra kết quả đáng tin cậy cho loại phần mềm đang giao. Một thư viện dùng nội bộ, một API phục vụ khách hàng và một dịch vụ thanh toán có thể cần các mức kiểm soát khác nhau. Không nên áp dụng một bộ bước giống hệt nhau cho mọi sản phẩm.

Có thể xem thiết kế pipeline như việc tạo một lát cắt đầu cuối có thể hoạt động:

1. Nhận một thay đổi từ Git.
2. Kiểm tra thay đổi bằng những phép kiểm tra có giá trị cao.
3. Tạo một artifact có thể nhận diện và truy vết.
4. Đưa artifact đến môi trường cần thiết.
5. Xác minh kết quả và lưu lại bằng chứng.
6. Dừng, sửa lỗi hoặc khôi phục khi điều kiện không đạt.

Khi lát cắt này hoạt động ổn định, đội ngũ mới có cơ sở để quyết định cần bổ sung kiểm thử, môi trường, chính sách hoặc chiến lược phát hành nào.

## 2. Xác định phạm vi trước khi viết pipeline

Trước khi chọn nền tảng hoặc viết cấu hình, cần thống nhất một số thông tin về sản phẩm và quy trình phát hành.

| Câu hỏi | Điều cần xác định | Ví dụ |
|---|---|---|
| Sản phẩm là gì? | Loại đầu ra cần tạo | Thư viện, ứng dụng web, API, image container |
| Sự kiện nào kích hoạt? | Thời điểm cần kiểm tra | Pull request, push vào nhánh chính, tạo tag |
| Đâu là nguồn sự thật? | Commit và nhánh được phép phát hành | Nhánh main đã được bảo vệ |
| Kiểm tra nào là bắt buộc? | Bằng chứng tối thiểu về tính đúng đắn và an toàn | Lint, unit test, kiểm tra dependency |
| Artifact là gì? | Gói nào sẽ được lưu và triển khai | JAR, package, image theo digest |
| Môi trường đích là gì? | Nơi xác minh và phát hành | Môi trường kiểm thử, staging, production |
| Điều kiện phát hành là gì? | Ai hoặc chính sách nào cho phép phát hành | Kiểm tra staging đạt, phê duyệt theo rủi ro |
| Nếu thất bại thì sao? | Cách thông báo, dừng và khôi phục | Chặn merge, giữ artifact cũ, rollback |

Phạm vi này cần đủ rõ để người khác có thể trả lời: thay đổi nào chạy pipeline nào, artifact nào được tạo, điều kiện nào cho phép triển khai và ai chịu trách nhiệm khi có lỗi.

Không nên bắt đầu bằng câu hỏi “nền tảng có bao nhiêu tính năng?”. Hãy bắt đầu bằng yêu cầu vận hành và bằng chứng cần thu được. Sau đó mới chọn cơ chế mà nền tảng hỗ trợ.

## 3. Cấu trúc nhỏ nhất có thể dùng được

Với một dịch vụ thông thường, pipeline đầu tiên có thể chia thành bốn phần logic:

- **Validate:** kiểm tra mã nguồn và các điều kiện cần thiết trước khi chấp nhận thay đổi.
- **Package:** build và tạo artifact bất biến, gắn với commit và lần chạy pipeline.
- **Deploy:** triển khai chính artifact đó đến môi trường phù hợp.
- **Verify:** kiểm tra dịch vụ sau triển khai, ghi nhận kết quả và quyết định tiếp tục hay dừng.

Các phần logic này không bắt buộc phải tương ứng với bốn công cụ hoặc bốn workflow riêng. Có thể có nhiều job trong một stage, hoặc một nền tảng thực hiện toàn bộ. Điều quan trọng là ranh giới đầu vào, đầu ra và điều kiện chuyển bước phải rõ ràng.

~~~mermaid
flowchart TD
    A["Pull request / commit"] --> B["Validate"]
    B --> C{"Kiểm tra đạt?"}
    C -- "Không" --> X["Báo lỗi và chặn thay đổi"]
    C -- "Có" --> D["Build và đóng gói"]
    D --> E["Artifact bất biến + metadata"]
    E --> F["Deploy môi trường kiểm thử"]
    F --> G["Smoke / integration checks"]
    G --> H{"Xác minh đạt?"}
    H -- "Không" --> Y["Dừng phát hành và điều tra"]
    H -- "Có" --> I["Release policy"]
    I --> J["Deploy production"]
    J --> K["Post-deploy verification"]
    K --> L{"Dịch vụ ổn định?"}
    L -- "Không" --> M["Rollback hoặc khắc phục"]
    L -- "Có" --> N["Ghi nhận release"]
~~~

Ở giai đoạn đầu, không cần tạo một hệ thống điều phối phức tạp để biểu diễn sơ đồ này. Hãy dùng những cơ chế sẵn có của nền tảng và giữ cho luồng dễ đọc, dễ chạy lại, dễ điều tra.

## 4. Thiết kế từng phần của pipeline

### 4.1. Validate: phản hồi sớm trên thay đổi

Validate thường chạy khi có pull request hoặc khi commit được đẩy lên nhánh chính. Mục tiêu là phát hiện vấn đề trước khi thay đổi trở thành một phần của bản phát hành.

Một bộ kiểm tra ban đầu thường gồm:

- Kiểm tra định dạng hoặc lint để giữ quy ước mã nguồn.
- Phân tích tĩnh cơ bản để phát hiện lỗi phổ biến.
- Kiểm thử đơn vị hoặc kiểm thử nhanh tương ứng với dự án.
- Kiểm tra bí mật bị lộ trong thay đổi.
- Kiểm tra lỗ hổng dependency ở mức phù hợp với chính sách của dự án.

Nên ưu tiên các kiểm tra nhanh, ổn định và có khả năng chỉ ra hành động sửa lỗi cụ thể. Kiểm thử tích hợp lớn, kiểm thử hiệu năng hoặc kiểm thử trên nhiều phiên bản runtime có thể được thêm sau khi có nhu cầu rõ ràng.

Không nên biến mọi cảnh báo thành lỗi chặn merge ngay lập tức. Phân biệt rõ:

- **Required check:** phải đạt để thay đổi được chấp nhận.
- **Advisory check:** cung cấp thông tin, chưa chặn thay đổi trong giai đoạn thử nghiệm.
- **Waiver có kiểm soát:** ngoại lệ có người phê duyệt, lý do, phạm vi và thời hạn.

Với kiểm tra quan trọng về tính toàn vẹn hoặc bí mật, cần có chính sách chặn rõ ràng. Với cảnh báo chất lượng chưa được hiệu chỉnh, có thể bắt đầu ở chế độ thông tin, đo tỷ lệ cảnh báo sai rồi điều chỉnh. Tránh để trạng thái “warning” kéo dài vô thời hạn mà không có người chịu trách nhiệm.

### 4.2. Package: build và tạo artifact có danh tính

Sau khi các kiểm tra bắt buộc đạt, pipeline tạo gói phần mềm. Artifact có thể là JAR, binary, package, gói frontend hoặc image container.

Ngay từ pipeline đầu tiên, cần ghi nhận tối thiểu:

- Mã commit hoặc revision nguồn.
- Mã lần chạy pipeline và thời điểm build.
- Phiên bản ứng dụng hoặc tag phát hành nếu có.
- Loại artifact và mã định danh bất biến, chẳng hạn digest.
- Kết quả các kiểm tra bắt buộc liên quan đến artifact.

Artifact cần được lưu trong kho phù hợp với chính sách truy cập và thời gian lưu giữ. Không nên chỉ dựa vào file còn nằm trong workspace của runner vì workspace có thể bị xóa hoặc thay đổi sau lần chạy.

Một nguyên tắc cần thiết là **build một lần, dùng cùng artifact cho các môi trường tiếp theo**. Nếu staging và production tự build lại, đội ngũ không còn chắc chắn rằng gói đã kiểm thử chính là gói được phát hành. Thay đổi cấu hình theo môi trường nên được quản lý tách biệt và không làm thay đổi nội dung artifact đã được tạo.

### 4.3. Deploy: triển khai theo môi trường và chính sách

Pipeline tối thiểu nên có ít nhất một môi trường mà đội ngũ có thể triển khai tự động và kiểm tra an toàn. Với nhiều dự án, đây là môi trường kiểm thử hoặc staging.

Triển khai cần xác định rõ:

- Artifact nào được triển khai, tốt nhất bằng digest hoặc định danh bất biến.
- Môi trường và cấu hình đích.
- Danh tính thực hiện triển khai và quyền được cấp.
- Cách truyền cấu hình và bí mật.
- Cách ghi nhận phiên bản đang chạy.
- Điều kiện dừng nếu bước triển khai thất bại.

Không nên đưa mật khẩu, token hoặc khóa riêng vào file pipeline, tham số dòng lệnh được ghi log hay artifact. Dùng secret store hoặc cơ chế định danh workload của nền tảng, cấp quyền tối thiểu theo môi trường và giới hạn thời gian sử dụng nếu có thể. Job triển khai production không nên tự động có quyền truy cập rộng hơn mức cần thiết.

Với production, có thể cần phê duyệt hoặc chính sách phát hành. Phê duyệt nên gắn với một phiên bản hoặc artifact cụ thể và lưu lại ai đã phê duyệt, thời điểm nào, dựa trên bằng chứng nào. Không nên yêu cầu phê duyệt thủ công ở mọi nơi nếu rủi ro thấp và chính sách cho phép tự động hóa.

### 4.4. Verify: xác minh sau khi triển khai

Lệnh deploy trả về thành công chỉ chứng minh thao tác triển khai đã hoàn tất theo góc nhìn của công cụ. Nó chưa chứng minh ứng dụng hoạt động đúng.

Bộ xác minh tối thiểu có thể gồm:

- Smoke test kiểm tra endpoint hoặc chức năng quan trọng nhất.
- Kiểm tra readiness/health của ứng dụng.
- Xác nhận phiên bản hoặc digest đang chạy đúng với artifact dự kiến.
- Kiểm tra một số tín hiệu vận hành cơ bản như tỷ lệ lỗi hoặc độ trễ.

Với dịch vụ quan trọng, cần quan sát trong một khoảng thời gian sau triển khai hoặc theo dõi canary trước khi tăng toàn bộ lưu lượng. Điều kiện dừng hoặc rollback nên được xác định trước, tránh quyết định tùy hứng khi sự cố đang xảy ra.

Cũng cần nghĩ đến khả năng tương thích dữ liệu. Nếu bản mới thay đổi schema cơ sở dữ liệu, quay lui mã nguồn chưa chắc khôi phục được hệ thống. Ưu tiên migration tương thích ngược theo từng bước, chẳng hạn mở rộng schema trước, chuyển ứng dụng, rồi mới loại bỏ cấu trúc cũ khi không còn phiên bản nào phụ thuộc.

## 5. Tách pipeline kiểm tra thay đổi và pipeline phát hành

Không phải mọi sự kiện Git đều cần chạy toàn bộ quy trình. Có thể tách hai mục đích:

**Pipeline kiểm tra thay đổi** chạy trên pull request hoặc commit. Nó cung cấp phản hồi sớm và quyết định thay đổi có đủ điều kiện đi vào nhánh chính hay không.

**Pipeline phát hành** chạy khi có commit được chấp nhận, tag hoặc yêu cầu phát hành. Nó tạo hoặc lấy artifact đã xác định, triển khai theo chính sách và xác minh môi trường đích.

Cách tách này giúp tránh triển khai production mỗi khi có một commit chưa được phê duyệt. Nó cũng giúp đội ngũ phân biệt lỗi kiểm thử của thay đổi với lỗi triển khai hoặc lỗi môi trường.

Một luồng đơn giản có thể là:

~~~mermaid
flowchart LR
    A["Pull request"] --> B["Lint + tests + security checks"]
    B --> C{"Required checks pass?"}
    C -- "No" --> D["Fix change"]
    D --> A
    C -- "Yes" --> E["Merge to main"]
    E --> F["Build + publish artifact"]
    F --> G["Deploy and verify"]
    G --> H["Release under policy"]
~~~

Nếu nền tảng hỗ trợ tái sử dụng kết quả build, cần bảo đảm artifact được tạo từ đúng commit đã được chấp nhận. Nếu phải build sau khi merge, pipeline phát hành phải ghi rõ commit và digest để giữ liên kết với kết quả kiểm tra trước đó.

## 6. Pipeline dưới dạng mã: giữ cấu hình có thể xem lại

Pipeline as code nghĩa là cấu hình CI/CD được lưu trong hệ thống quản lý phiên bản cùng với mã nguồn hoặc trong kho cấu hình được quản trị. Cách làm này giúp thay đổi pipeline có lịch sử, có review, có thể khôi phục và được kiểm tra như thay đổi phần mềm.

Một pipeline ban đầu nên ưu tiên:

- Tên stage và job phản ánh đúng mục đích.
- Các điều kiện kích hoạt được khai báo rõ.
- Phiên bản action, plugin hoặc image được cố định ở mức phù hợp.
- Có timeout cho job có thể bị treo.
- Log cho biết bước nào chạy, kết quả gì và liên kết đến artifact.
- Không lặp lại cấu hình nếu có thể dùng một template đơn giản.
- Không đưa bí mật hoặc dữ liệu nhạy cảm vào repository.

Ví dụ dưới đây là YAML giả lập để mô tả ý tưởng, không phải cấu hình chạy trực tiếp trên GitHub Actions, GitLab CI hay Jenkins:

~~~yaml
pipeline:
  triggers:
    - pull_request
    - push_to_main

  validate:
    required: true
    steps:
      - checkout_source
      - lint
      - unit_tests
      - dependency_check
      - secret_scan

  package:
    requires: validate_passed
    steps:
      - build_once
      - create_immutable_artifact
      - attach_commit_and_run_metadata
      - publish_artifact

  test_environment:
    requires: artifact_published
    steps:
      - deploy_artifact_by_digest
      - run_smoke_tests
      - record_deployed_version

  production:
    requires:
      - test_environment_passed
      - release_policy_satisfied
    steps:
      - deploy_same_artifact
      - verify_health
      - stop_or_rollback_on_failure
      - record_release
~~~

Không nên sao chép nguyên ví dụ này vào dự án mà chưa ánh xạ các bước sang công cụ và điều kiện thực tế. Hãy coi nó như hợp đồng logic: đầu vào, điều kiện, đầu ra và cách xử lý lỗi của từng phần phải được định nghĩa.

## 7. Chính sách thất bại: pipeline phải nói rõ điều gì xảy ra tiếp theo

Pipeline đáng tin cậy cần có hành vi xác định khi một bước thất bại. Một job màu đỏ nhưng không rõ phải làm gì sẽ tạo ra nhiều thao tác thủ công và khiến người dùng dần bỏ qua cảnh báo.

| Tình huống | Hành vi tối thiểu nên có |
|---|---|
| Lint hoặc unit test thất bại | Chặn thay đổi theo chính sách; hiển thị log và thông tin test lỗi |
| Quét phát hiện bí mật | Chặn luồng phù hợp, thông báo cách xử lý và quy trình thu hồi bí mật đã lộ |
| Build thất bại | Không publish artifact chưa hoàn chỉnh; giữ log để điều tra |
| Publish artifact thất bại | Không chuyển sang deploy; cho phép chạy lại an toàn |
| Deploy thất bại | Dừng rollout, giữ trạng thái hiện tại có thể xác định và phát cảnh báo |
| Smoke test thất bại | Không đánh dấu release thành công; dừng tăng lưu lượng hoặc rollback theo chính sách |
| Dịch vụ suy giảm sau deploy | Kích hoạt ngưỡng cảnh báo và quy trình khôi phục đã định trước |

Phân biệt lỗi có thể thử lại với lỗi cần sửa. Lỗi mạng tạm thời khi tải dependency có thể được retry có giới hạn. Unit test thất bại do regression không nên tự chạy lại nhiều lần để biến kết quả đỏ thành xanh. Retry không có giới hạn có thể che giấu lỗi thật và làm pipeline kéo dài.

Mỗi job cần timeout hợp lý. Nếu một bước bị treo, pipeline phải kết thúc có kiểm soát và cung cấp thông tin đủ để điều tra. Các thao tác publish hoặc deploy cần được thiết kế để chạy lại an toàn hoặc có cơ chế phát hiện trạng thái đã hoàn tất.

## 8. Bảo vệ bí mật và quyền truy cập ngay từ phiên bản đầu

Bảo mật không phải phần trang trí để thêm vào khi pipeline đã lớn. Một pipeline tối thiểu vẫn phải có ranh giới tin cậy rõ ràng.

Một số quy tắc cơ bản:

1. Không lưu token, mật khẩu, private key hoặc credential trong repository.
2. Không cấp secret production cho pipeline chạy trên pull request từ nguồn không tin cậy.
3. Tách quyền đọc artifact, quyền triển khai staging và quyền triển khai production.
4. Dùng danh tính ngắn hạn hoặc cơ chế xác thực của nền tảng khi có thể.
5. Giới hạn quyền theo repository, môi trường và job.
6. Che dữ liệu nhạy cảm khỏi log và xóa credential khỏi runner sau khi dùng.
7. Ghi nhận ai hoặc workload nào đã triển khai phiên bản production.

Một pipeline có thể ít job nhưng vẫn có bề mặt rủi ro lớn nếu mọi job dùng chung một token quản trị. Nguyên tắc tối thiểu cần đạt là mỗi bước chỉ có quyền cần thiết để hoàn thành nhiệm vụ của nó.

## 9. Đo pipeline trước khi mở rộng

Không có đường cơ sở thì rất khó biết một thay đổi pipeline có cải thiện hay làm tình hình tệ hơn. Trước khi tối ưu, hãy đo một số chỉ số đơn giản:

| Chỉ số | Cách hiểu | Câu hỏi giúp trả lời |
|---|---|---|
| Thời gian phản hồi đầu tiên | Từ lúc mở PR đến kết quả kiểm tra đầu tiên | Người phát triển phải chờ bao lâu mới biết lỗi? |
| Tổng thời gian pipeline | Từ lúc bắt đầu đến lúc hoàn tất | Luồng có đang quá chậm không? |
| Thời gian chờ runner | Thời gian job chờ tài nguyên thực thi | Nút thắt nằm ở năng lực runner hay ở script? |
| Tỷ lệ pipeline thất bại | Số lần thất bại trên tổng số lần chạy, phân loại nguyên nhân | Job nào thường xuyên không ổn định? |
| Thời gian từ merge đến deploy | Khoảng thời gian thay đổi cần để đến môi trường đích | Quy trình phát hành đang chờ ở đâu? |
| Tỷ lệ triển khai gây lỗi | Tỷ lệ release dẫn đến sự cố hoặc khắc phục khẩn cấp | Tốc độ có đi kèm độ ổn định không? |
| Thời gian khôi phục | Từ lúc phát hiện sự cố đến khi dịch vụ phục hồi | Quy trình phục hồi có hiệu quả không? |

Không nên tối ưu tất cả chỉ số cùng lúc. Hãy chọn một vấn đề có tác động rõ, thay đổi một phần pipeline, rồi so sánh trước và sau. Ví dụ, nếu pipeline chậm vì cài dependency lặp lại, cache có thể giúp ích. Nếu thời gian chủ yếu nằm ở kiểm thử tích hợp phụ thuộc môi trường dùng chung, thêm runner sẽ không giải quyết nguyên nhân.

## 10. Khi nào cần mở rộng pipeline?

Chỉ thêm stage, job hoặc công cụ khi có nhu cầu cụ thể mà pipeline hiện tại chưa đáp ứng. Một số tín hiệu hợp lý:

| Tín hiệu quan sát được | Năng lực có thể cần bổ sung |
|---|---|
| Lỗi chỉ xuất hiện khi các service tích hợp với nhau | Integration test hoặc contract test |
| Nhiều runtime hoặc phiên bản nền tảng được hỗ trợ | Matrix test có phạm vi rõ |
| Dependency hoặc image có rủi ro bảo mật cao | Quét lỗ hổng sâu hơn và chính sách xử lý |
| Artifact phải chứng minh nguồn gốc hoặc tính toàn vẹn | SBOM, chữ ký và provenance |
| Deploy ảnh hưởng lớn đến người dùng | Canary, blue-green hoặc progressive delivery |
| Thay đổi schema gây rủi ro tương thích | Kiểm tra migration và quy trình expand-contract |
| Sản phẩm có yêu cầu tuân thủ | Audit trail, approval policy và lưu bằng chứng |
| Nhiều repository lặp lại cùng cấu hình | Pipeline template hoặc reusable workflow |
| Pipeline có nhiều thao tác thủ công dễ sai | Tự động hóa đúng điểm bàn giao |

Một năng lực mới nên đi kèm câu trả lời cho bốn câu hỏi:

- Rủi ro hoặc nút thắt nào đang được giải quyết?
- Bằng chứng nào cho thấy năng lực mới hoạt động?
- Ai sở hữu và vận hành nó?
- Chi phí, quyền truy cập và điểm lỗi mới là gì?

Nếu chưa trả lời được, hãy ghi nhận nhu cầu và thu thập dữ liệu trước khi thêm.

## 11. Lộ trình phát triển theo từng mức

Có thể phát triển pipeline qua các mức sau. Đây là lộ trình tham khảo, không phải quy định mọi dự án phải đi qua tất cả mức.

### Mức 1: Kiểm tra thay đổi

- Kích hoạt theo pull request hoặc commit.
- Chạy lint, unit test và kiểm tra cơ bản về dependency/bí mật.
- Chặn merge khi required checks thất bại.
- Hiển thị log và kết quả rõ ràng.

Mức này giúp đội ngũ có phản hồi tự động trước khi chấp nhận thay đổi.

### Mức 2: Tạo và lưu artifact

- Build từ commit đã xác định.
- Gắn metadata và mã định danh bất biến.
- Publish artifact vào kho có kiểm soát.
- Lưu liên kết giữa commit, pipeline run và artifact.

Mức này giúp đội ngũ biết chính xác gói nào được tạo ra và có thể sử dụng lại.

### Mức 3: Triển khai và xác minh tự động

- Deploy cùng artifact đến môi trường kiểm thử.
- Chạy smoke test hoặc integration test cần thiết.
- Ghi nhận phiên bản đang chạy.
- Chỉ đánh dấu thành công sau khi xác minh đạt.

Mức này tạo ra luồng giao phần mềm đầu cuối có thể lặp lại.

### Mức 4: Kiểm soát phát hành và phục hồi

- Áp dụng phê duyệt hoặc chính sách phát hành theo rủi ro.
- Quản lý quyền production tách biệt.
- Thêm rollout theo tỷ lệ hoặc nhóm người dùng khi cần.
- Đặt ngưỡng dừng và diễn tập rollback.

Mức này tăng khả năng kiểm soát tác động khi phát hành.

### Mức 5: Tối ưu và chuẩn hóa

- Dùng cache và parallelism dựa trên dữ liệu.
- Tạo template dùng chung cho nhiều repository.
- Bổ sung SBOM, chữ ký, provenance và kiểm tra chính sách khi có yêu cầu.
- Theo dõi chỉ số giao phần mềm và cải tiến định kỳ.

Chỉ nên chuẩn hóa rộng sau khi một pipeline đại diện đã chứng minh được tính ổn định. Template sao chép một thiết kế chưa tốt sẽ nhân rộng chi phí và lỗi cho nhiều repository.

## 12. Những lỗi thường gặp khi thiết kế pipeline đầu tiên

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Thêm quá nhiều job ngay từ đầu | Khó hiểu, khó bảo trì, phản hồi chậm | Bắt đầu với luồng đầu cuối ngắn và mở rộng theo bằng chứng |
| Chỉ kiểm tra build thành công | Không có bằng chứng về chất lượng chức năng | Thêm test và kiểm tra cần thiết theo rủi ro |
| Build lại ở mỗi môi trường | Không chắc artifact đã kiểm thử là artifact phát hành | Build một lần, promote cùng artifact |
| Dùng chung token quyền cao | Một job bị xâm nhập có thể ảnh hưởng toàn hệ thống | Tách danh tính và quyền theo job/môi trường |
| Không có timeout | Runner có thể bị chiếm dụng vô hạn | Đặt timeout và thông báo khi hết thời gian |
| Retry mọi lỗi | Che giấu regression hoặc test không ổn định | Phân loại lỗi và retry có giới hạn cho lỗi tạm thời |
| Không xác minh sau deploy | Deploy xanh nhưng dịch vụ có thể hỏng | Thêm health check và smoke test |
| Dùng template quá sớm | Nhân rộng cấu hình chưa phù hợp | Thử nghiệm trên một repository đại diện trước |
| Không có người sở hữu pipeline | Job lỗi kéo dài, cảnh báo không được xử lý | Chỉ định owner và cách tiếp nhận sự cố |

## 13. Ví dụ thực hành: pipeline tối thiểu cho một API

Giả sử đội ngũ có một API được lưu trong Git, đóng gói thành image container và triển khai lên môi trường staging trước production.

Có thể bắt đầu với phạm vi sau:

| Thời điểm | Bước | Điều kiện đầu ra |
|---|---|---|
| Pull request | Lint, unit test, secret scan, dependency check | Kết quả kiểm tra gắn với commit |
| Merge vào main | Build image một lần | Image được gắn commit và digest |
| Sau build | Publish image | Artifact có thể truy cập bằng digest |
| Staging | Deploy image theo digest | Phiên bản đang chạy được ghi nhận |
| Sau deploy staging | Smoke test API và kiểm tra health | Bằng chứng xác minh được lưu |
| Phát hành production | Kiểm tra release policy, phê duyệt nếu cần | Xác định người/quy tắc cho phép phát hành |
| Sau deploy production | Kiểm tra health và tỷ lệ lỗi | Hoàn tất hoặc kích hoạt dừng/rollback |

Trong tuần đầu, đội ngũ nên tập trung xác nhận các đường đi chính: PR hợp lệ, PR thất bại, build thất bại, deploy staging thất bại và smoke test thất bại. Không cần tạo hàng chục biến thể môi trường khi chưa có nhu cầu. Nhưng các đường lỗi quan trọng phải có hành vi rõ ràng.

Khi luồng cơ bản ổn định, có thể đo thời gian từng bước. Nếu kiểm thử đơn vị chiếm phần lớn thời gian, tối ưu test. Nếu runner thường xuyên xếp hàng, xem xét năng lực thực thi. Nếu deploy staging mất nhiều thao tác, chuẩn hóa cấu hình và quyền. Mỗi cải tiến cần gắn với nút thắt đã quan sát.

## 14. Checklist nghiệm thu pipeline tối thiểu

Trước khi xem pipeline đầu tiên là sẵn sàng sử dụng, hãy kiểm tra:

- [ ] Sự kiện Git và nhánh được phép chạy đã được xác định.
- [ ] Required checks có tiêu chí đạt/trượt rõ ràng.
- [ ] Kết quả kiểm tra gắn với commit và hiển thị cho người tạo thay đổi.
- [ ] Build tạo artifact có danh tính bất biến.
- [ ] Artifact được lưu ở vị trí có kiểm soát và truy cập được.
- [ ] Cùng một artifact được dùng xuyên suốt các môi trường.
- [ ] Secret không nằm trong repository, log hoặc artifact.
- [ ] Quyền triển khai được giới hạn theo môi trường và nhiệm vụ.
- [ ] Deploy thất bại sẽ dừng luồng và thông báo rõ.
- [ ] Có kiểm tra sau deploy và xác nhận phiên bản đang chạy.
- [ ] Có người chịu trách nhiệm cho pipeline và cách xử lý khi nó lỗi.
- [ ] Các chỉ số cơ bản được thu thập để làm đường cơ sở.

Nếu một mục chưa đáp ứng, cần xác định đó là rủi ro chấp nhận được trong phạm vi hiện tại hay điều kiện bắt buộc trước khi phát hành. Với bí mật, tính toàn vẹn artifact và xác minh production, không nên bỏ qua chỉ vì muốn pipeline ngắn hơn.

## 15. Bài tập tự đánh giá

Một nhóm có repository cho dịch vụ web. Hiện tại, lập trình viên merge vào nhánh chính, sau đó một người tải file build về máy, đăng nhập vào máy chủ staging và chép file thủ công. Khi kiểm thử xong, người đó lặp lại thao tác tương tự cho production. Nhóm muốn đưa CI/CD vào sử dụng nhưng chỉ có thời gian xây dựng một pipeline đầu tiên.

Hãy trả lời:

1. Những sự kiện Git nào nên kích hoạt pipeline kiểm tra thay đổi và pipeline phát hành?
2. Ba đến năm kiểm tra đầu tiên nào có giá trị cao nhất đối với repository này? Vì sao?
3. Artifact cần mang thông tin nào để truy vết đến commit và lần build?
4. Làm thế nào để staging và production dùng cùng artifact?
5. Bí mật và quyền triển khai nên được cấp cho job như thế nào?
6. Sau deploy, cần kiểm tra điều gì để biết ứng dụng hoạt động?
7. Nếu deploy thành công nhưng smoke test thất bại, pipeline nên làm gì?
8. Sau vài tuần vận hành, dữ liệu nào sẽ giúp quyết định có nên thêm integration test, canary hoặc template dùng chung?

Một thiết kế tốt cần thể hiện được luồng đầu cuối, điều kiện dừng, cách truy vết và người chịu trách nhiệm. Không cần chọn thật nhiều công cụ để chứng minh đã có CI/CD.

## Kết luận

Pipeline đầu tiên nên tạo được một đường đi ngắn nhưng đáng tin cậy từ thay đổi Git đến artifact, môi trường triển khai và bằng chứng xác minh. Các bước cốt lõi gồm kiểm tra thay đổi, build một lần, lưu artifact có danh tính, triển khai theo quyền được kiểm soát và xác minh sau triển khai.

Khi pipeline hoạt động ổn định, hãy dùng dữ liệu về thời gian, lỗi và rủi ro để chọn năng lực tiếp theo cần bổ sung. Cách phát triển theo từng lát cắt giúp đội ngũ duy trì khả năng hiểu, vận hành và cải tiến pipeline trong suốt vòng đời sản phẩm.

