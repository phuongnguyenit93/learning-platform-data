# Lộ trình học từ thay đổi mã nguồn đến kiểm chứng trên môi trường đích

Một thay đổi trong Git chỉ trở thành một bản phát hành đáng tin cậy khi ta có thể trả lời được các câu hỏi: thay đổi nào đã kích hoạt quy trình, mã nguồn đã được build và kiểm thử ra sao, artifact nào được tạo ra, artifact đó đã đi qua những môi trường nào, ai hoặc điều kiện nào cho phép triển khai, và hệ thống hoạt động thế nào sau khi triển khai?

Bài học này xây dựng một lộ trình CI/CD xuyên suốt từ sự kiện Git đến kiểm chứng trên môi trường đích. Trọng tâm là xem pipeline như một quy trình có thể đọc, kiểm soát và truy vết bằng mã. Lộ trình bao gồm tự động hóa build và kiểm thử, quản lý artifact, phân tách cấu hình môi trường, cổng chất lượng, bảo vệ bí mật, xác minh sau triển khai và phương án quay lui. Đây là nền tảng để thiết kế luồng phát hành có thể lặp lại và có bằng chứng ở từng bước.

## 1. Nhìn toàn cảnh một luồng CI/CD

CI (Continuous Integration – tích hợp liên tục) đưa các thay đổi mã nguồn vào một quy trình tích hợp thường xuyên. Mỗi thay đổi được kiểm tra tự động để phát hiện lỗi sớm, giảm rủi ro khi hợp nhất. CD thường được dùng với hai nghĩa:

- **Continuous Delivery – phân phối liên tục:** mọi thay đổi vượt qua các bước kiểm tra đều sẵn sàng phát hành; việc đưa lên production có thể cần một quyết định hoặc phê duyệt.
- **Continuous Deployment – triển khai liên tục:** thay đổi vượt qua toàn bộ cổng tự động sẽ được triển khai lên production mà không cần thao tác phê duyệt thủ công cho từng lần.

Một luồng cơ bản có thể mô tả như sau:

~~~mermaid
flowchart TD
    A["Thay đổi mã nguồn"] --> B["Sự kiện Git"]
    B --> C["Pipeline được kích hoạt"]
    C --> D["Build và kiểm thử"]
    D --> E{"Cổng chất lượng"}
    E -- "Không đạt" --> F["Báo lỗi, giữ lại bằng chứng"]
    E -- "Đạt" --> G["Đóng gói artifact"]
    G --> H["Lưu artifact bất biến"]
    H --> I["Triển khai môi trường kiểm thử"]
    I --> J["Smoke test và kiểm chứng"]
    J --> K{"Đủ điều kiện phát hành?"}
    K -- "Không" --> L["Dừng, điều tra hoặc sửa lỗi"]
    K -- "Có" --> M["Phê duyệt / tự động phát hành"]
    M --> N["Triển khai môi trường đích"]
    N --> O["Theo dõi sức khỏe và xác minh"]
    O --> P{"Hệ thống ổn định?"}
    P -- "Không" --> Q["Quay lui hoặc khắc phục"]
    P -- "Có" --> R["Ghi nhận bản phát hành"]
~~~

Pipeline không chỉ là danh sách lệnh chạy nối tiếp. Nó là hợp đồng vận hành: xác định điều kiện bắt đầu, đầu vào, các bước xử lý, tiêu chí đạt, quyền được sử dụng, đầu ra và cách xử lý khi thất bại. Một pipeline tốt làm cho cùng một thay đổi có thể được kiểm tra theo cùng một quy tắc và để lại đủ thông tin nhằm giải thích kết quả.

## 2. Bắt đầu từ sự kiện Git

Git cung cấp các sự kiện tự nhiên để kích hoạt tự động hóa. Việc chọn đúng sự kiện giúp quy trình chạy đúng thời điểm và đúng mức rủi ro.

| Sự kiện | Mục đích thường gặp | Hành vi phù hợp |
|---|---|---|
| Push lên nhánh tính năng | Kiểm tra thay đổi sớm | Build, lint và kiểm thử nhanh |
| Tạo hoặc cập nhật pull request | Đánh giá trước khi hợp nhất | Chạy bộ kiểm tra bắt buộc, báo kết quả cho người review |
| Merge vào nhánh chính | Xác nhận trạng thái tích hợp | Chạy đầy đủ kiểm thử, đóng gói artifact |
| Tạo tag hoặc release | Đánh dấu phiên bản phát hành | Tạo hoặc xác nhận artifact gắn với phiên bản |
| Kích hoạt thủ công | Xử lý phát hành có kiểm soát hoặc tác vụ vận hành | Kiểm tra quyền, tham số và môi trường đích |
| Lịch định kỳ | Quét lỗ hổng, kiểm tra phụ thuộc hoặc tác vụ bảo trì | Chạy độc lập với thay đổi mã nguồn khi cần |

Không phải sự kiện nào cũng nên có quyền triển khai production. Ví dụ, một pull request từ nhánh chưa được tin cậy có thể chạy kiểm thử nhưng không nên nhận thông tin xác thực production. Việc triển khai production thường chỉ được phép từ nhánh hoặc tag đã được bảo vệ, sau khi các kiểm tra bắt buộc thành công.

Khi thiết kế trigger, hãy xác định rõ:

1. Sự kiện nào được phép khởi chạy pipeline?
2. Nhánh, tag hoặc nguồn thay đổi nào được chấp nhận?
3. Pipeline nào chỉ kiểm tra, pipeline nào có thể triển khai?
4. Một lần chạy có thể bị kích hoạt trùng hay chạy đồng thời không?
5. Khi một commit mới xuất hiện, có nên hủy lần chạy cũ không?

Cần tránh việc cấu hình trigger quá rộng khiến mọi thay đổi nhỏ đều triển khai lên môi trường nhạy cảm. Ngược lại, trigger quá hẹp có thể khiến thay đổi quan trọng không được kiểm tra. Quy tắc kích hoạt phải phản ánh chiến lược nhánh và quy trình phát hành thực tế của nhóm.

## 3. Đưa pipeline vào quản lý bằng mã

Pipeline as Code là cách mô tả quy trình CI/CD trong các tệp cấu hình được lưu cùng repository hoặc trong một kho mã được quản lý phiên bản. Nhờ vậy, thay đổi pipeline có thể được review, kiểm thử, truy vết và khôi phục như thay đổi phần mềm.

Một cấu hình pipeline dễ bảo trì thường có các đặc điểm:

- **Có phiên bản:** lịch sử thay đổi cho biết ai đã thay đổi bước nào và vì sao.
- **Có thể review:** thay đổi về quyền, trigger, môi trường hoặc cổng chất lượng được xem xét trước khi áp dụng.
- **Có cấu trúc rõ:** tách các bước build, test, package, deploy và verify; tái sử dụng phần việc chung khi phù hợp.
- **Có điều kiện rõ ràng:** mỗi bước khai báo đầu vào, đầu ra và điều kiện chạy.
- **Có quyền tối thiểu:** job chỉ nhận quyền cần thiết cho đúng công việc.
- **Có thể lặp lại:** cùng đầu vào và cùng phiên bản công cụ phải tạo ra kết quả tương đương.
- **Có thời gian chờ và xử lý lỗi:** tránh job treo vô hạn hoặc tiếp tục triển khai sau khi bước bắt buộc thất bại.

Ví dụ sau là mô hình khái niệm để hình dung thứ tự và điều kiện của các công đoạn. Đây không phải cú pháp thực thi của một nền tảng CI/CD cụ thể:

~~~yaml
pipeline:
  trigger:
    - pull_request
    - push_to_main

  jobs:
    validate:
      steps:
        - checkout_source
        - install_locked_dependencies
        - lint
        - unit_tests

    package:
      needs: [validate]
      steps:
        - build
        - integration_tests
        - create_artifact
        - calculate_artifact_digest
        - publish_artifact

    deploy_test:
      needs: [package]
      environment: test
      steps:
        - deploy_published_artifact
        - smoke_tests

    deploy_production:
      needs: [deploy_test]
      environment: production
      approval: required
      steps:
        - deploy_same_artifact
        - verify_release
~~~

Cấu hình thực tế của GitHub Actions, GitLab CI, Jenkins hoặc nền tảng khác sẽ có cú pháp và cơ chế phân quyền riêng. Khi áp dụng, cần dùng đúng cú pháp của nền tảng, kiểm tra tài liệu phiên bản đang chạy và không sao chép nguyên mô hình khái niệm thành tệp cấu hình thực thi.

Nên coi pipeline là mã sản phẩm: có người sở hữu, có quy tắc review, có cách thử nghiệm thay đổi và có phương án khôi phục khi cấu hình mới làm gián đoạn phát hành.

## 4. Tự động hóa build và kiểm thử

Build chuyển mã nguồn cùng các phụ thuộc thành đầu ra có thể chạy hoặc triển khai. Kiểm thử cung cấp bằng chứng rằng đầu ra đáp ứng những hành vi mong đợi. Hai hoạt động này thường được tự động hóa ngay sau khi pipeline nhận mã nguồn.

Một thứ tự kiểm tra thực dụng là:

1. **Kiểm tra tĩnh và định dạng:** phát hiện lỗi quy ước, lỗi cú pháp hoặc vấn đề dễ nhận biết mà chưa cần chạy ứng dụng.
2. **Kiểm thử đơn vị:** xác minh các thành phần nhỏ trong phạm vi cô lập.
3. **Build:** biên dịch hoặc đóng gói bằng phiên bản công cụ và tập phụ thuộc đã khóa.
4. **Kiểm thử tích hợp:** kiểm tra tương tác giữa các thành phần, dịch vụ hoặc cơ sở dữ liệu.
5. **Kiểm thử hệ thống hoặc đầu cuối:** xác minh các luồng nghiệp vụ quan trọng qua nhiều thành phần.
6. **Kiểm tra bảo mật và phụ thuộc:** tìm lỗ hổng đã biết, cấu hình nguy hiểm hoặc thành phần không được phép sử dụng.
7. **Đóng gói:** chỉ tạo artifact phát hành sau khi các điều kiện bắt buộc đạt.

Không phải dự án nào cũng cần chạy mọi loại kiểm thử ở mọi sự kiện. Pipeline cho pull request có thể ưu tiên phản hồi nhanh; pipeline sau khi hợp nhất có thể chạy thêm kiểm thử tích hợp và kiểm tra sâu. Tuy nhiên, các kiểm tra quyết định khả năng phát hành phải được thực hiện trước khi cho phép triển khai.

Một số nguyên tắc giúp kết quả build và test đáng tin cậy:

- Khóa phiên bản dependency và công cụ build; tránh phụ thuộc vào phiên bản mới nhất không kiểm soát.
- Dùng môi trường chạy sạch hoặc được tạo lại theo cách xác định.
- Không để kiểm thử phụ thuộc vào dữ liệu dùng chung có thể bị thay đổi bởi job khác.
- Phân biệt lỗi sản phẩm với lỗi hạ tầng kiểm thử; ghi log và bằng chứng đủ để điều tra.
- Theo dõi flaky test (kiểm thử lúc đạt lúc không). Không bỏ qua lỗi lặp lại bằng cách tự động chạy lại vô hạn.
- Lưu báo cáo kiểm thử, log build và mã thoát để người phát triển biết chính xác bước nào thất bại.

Tốc độ cũng quan trọng. Các kiểm tra rẻ và nhanh nên chạy sớm để phản hồi nhanh. Các kiểm tra tốn thời gian có thể chạy sau, nhưng không được bỏ qua nếu chúng là điều kiện bắt buộc để phát hành.

## 5. Quản lý artifact như một đầu ra có danh tính

Artifact là đầu ra đã được build và đóng gói để kiểm thử hoặc triển khai, chẳng hạn gói ứng dụng, container image, thư viện hoặc tệp triển khai. Artifact cần có danh tính ổn định để nhóm biết chính xác thứ gì đang chạy ở từng môi trường.

Các nguyên tắc cốt lõi:

- **Build một lần, triển khai nhiều môi trường:** tạo artifact từ một commit đã xác định, sau đó đưa chính artifact đó qua test, staging và production. Không build lại riêng cho production nếu mục tiêu là xác minh cùng một đầu ra.
- **Bất biến:** sau khi phát hành, không thay nội dung artifact dưới cùng một phiên bản hoặc tag. Nếu nội dung thay đổi, phải tạo danh tính mới.
- **Có mã băm:** lưu digest hoặc checksum để xác nhận artifact khi tải xuống và triển khai.
- **Có metadata:** ghi commit SHA, lần chạy pipeline, phiên bản ứng dụng, phiên bản công cụ build và thời điểm tạo.
- **Có nơi lưu trữ phù hợp:** dùng artifact repository hoặc container registry có quyền truy cập, chính sách lưu giữ và cơ chế dọn dẹp rõ ràng.
- **Có thể truy xuất:** từ một deployment phải tìm ngược được artifact, pipeline run và commit nguồn.

Tag dễ đọc như 2.4.1 hữu ích cho con người, nhưng tag có thể bị di chuyển nếu registry cho phép. Digest đại diện cho nội dung cụ thể và phù hợp hơn khi cần bảo đảm môi trường đang chạy đúng artifact đã được kiểm tra. Trong quy trình nghiêm ngặt, có thể bổ sung SBOM (danh mục thành phần phần mềm), chữ ký artifact và provenance (bằng chứng nguồn gốc, quy trình tạo artifact).

## 6. Tách artifact khỏi cấu hình môi trường

Môi trường là nơi artifact được chạy và kiểm chứng. Một lộ trình thường gặp gồm development, test, staging và production. Tên gọi có thể khác nhau giữa các tổ chức, nhưng mỗi môi trường cần có mục đích và mức kiểm soát rõ ràng.

| Môi trường | Mục tiêu | Kiểm soát thường gặp |
|---|---|---|
| Development | Phản hồi nhanh cho nhóm phát triển | Dữ liệu thử nghiệm, triển khai thường xuyên |
| Test / QA | Kiểm tra chức năng và tích hợp | Bộ dữ liệu kiểm thử, cấu hình gần với thực tế |
| Staging | Diễn tập phát hành trong điều kiện tương tự production | Kiểm thử hồi quy, smoke test, xác minh cấu hình |
| Production | Phục vụ người dùng thật | Phân quyền chặt, quan sát đầy đủ, kế hoạch khôi phục |

Cùng một artifact có thể chạy ở nhiều môi trường, nhưng cấu hình môi trường sẽ khác nhau: địa chỉ dịch vụ, giới hạn tài nguyên, tên miền, thông số kết nối và thông tin xác thực. Cấu hình nên được cấp tại thời điểm triển khai hoặc khi ứng dụng khởi động, thay vì đóng cứng bí mật và thông số riêng của production vào artifact.

Cần đặc biệt chú ý đến thay đổi cơ sở dữ liệu. Một bản phát hành có thể triển khai mã ứng dụng và migration schema. Nếu migration phá vỡ khả năng tương thích với phiên bản cũ, quay lui ứng dụng có thể không đủ để khôi phục hệ thống. Một cách giảm rủi ro là thay đổi schema theo nhiều bước: mở rộng tương thích trước, triển khai mã mới, chuyển đổi dữ liệu khi cần, rồi mới loại bỏ cấu trúc cũ sau khi xác nhận an toàn.

Việc promote giữa các môi trường nên ghi nhận rõ artifact digest, người hoặc quy tắc cho phép, thời điểm và kết quả kiểm chứng. Điều này giúp tránh trường hợp staging đã kiểm tra một bản build nhưng production lại chạy một bản build khác.

## 7. Thiết kế cổng chất lượng

Quality gate là tập hợp điều kiện phải đạt trước khi pipeline được đi tiếp. Cổng chất lượng biến kỳ vọng của nhóm thành quy tắc có thể kiểm tra nhất quán.

Một cổng có thể bao gồm:

- Tất cả kiểm thử bắt buộc đều đạt.
- Không còn lỗi nghiêm trọng vượt ngưỡng đã thống nhất.
- Mức độ bao phủ kiểm thử đáp ứng chính sách của dự án, nếu dự án dùng coverage làm tiêu chí.
- Dependency hoặc container image không chứa lỗ hổng bị cấm theo chính sách.
- Artifact đã được tạo và lưu thành công, digest được ghi nhận.
- Smoke test sau triển khai đạt.
- Có phê duyệt của người có thẩm quyền đối với môi trường cần kiểm soát.

Không nên chọn ngưỡng chỉ vì công cụ có thể đo được. Mỗi điều kiện phải gắn với rủi ro mà nhóm muốn giảm. Ví dụ, coverage cao không tự chứng minh kiểm thử có chất lượng; một bài kiểm thử có thể chạy qua nhiều dòng lệnh mà không xác minh kết quả quan trọng. Tương tự, việc quét bảo mật không phát hiện lỗi không đồng nghĩa ứng dụng hoàn toàn an toàn.

Cổng cần có kết quả dễ hiểu: đạt, không đạt hoặc cần quyết định có kiểm soát. Nếu cho phép ngoại lệ, hãy ghi lý do, phạm vi, người chấp thuận và thời hạn xem xét lại. Không nên biến việc bỏ qua cổng thành hành vi mặc định vì khi đó cổng không còn tác dụng bảo vệ.

## 8. Bảo vệ bí mật và quyền truy cập

Pipeline thường cần truy cập registry, cloud, máy chủ triển khai, cơ sở dữ liệu hoặc dịch vụ bên ngoài. Vì vậy, pipeline cũng là một nơi có rủi ro lộ thông tin xác thực.

Thực hành nên áp dụng:

- Lưu bí mật trong secret manager hoặc kho bí mật được nền tảng CI/CD hỗ trợ; không commit token, mật khẩu, private key hay tệp .env chứa bí mật vào Git.
- Cấp quyền tối thiểu theo từng job và từng môi trường. Job chỉ chạy unit test không cần quyền deploy production.
- Ưu tiên thông tin xác thực ngắn hạn hoặc cơ chế liên kết danh tính như OIDC khi nền tảng hỗ trợ, thay cho khóa dài hạn khó luân chuyển.
- Tách bí mật theo môi trường; giới hạn job nào có thể đọc bí mật production.
- Không in bí mật ra log, dòng lệnh hoặc thông báo lỗi. Cơ chế che giá trị trong log chỉ là lớp hỗ trợ, không thay thế việc tránh đưa bí mật vào đầu ra.
- Kiểm tra quyền của pull request từ fork hoặc nguồn không tin cậy trước khi cho phép job tiếp cận secret.
- Có quy trình thu hồi và luân chuyển thông tin xác thực khi nghi ngờ bị lộ.

Một nguyên tắc dễ nhớ: mã nguồn và artifact có thể được chia sẻ theo chính sách repository, còn bí mật phải được cấp đúng lúc, đúng job, đúng môi trường và đúng quyền.

## 9. Triển khai có kiểm soát

Chiến lược triển khai quyết định cách phiên bản mới thay thế phiên bản đang chạy. Việc lựa chọn phụ thuộc vào kiến trúc, khả năng chịu gián đoạn, chi phí hạ tầng và mức độ rủi ro.

| Chiến lược | Cách hoạt động | Khi phù hợp |
|---|---|---|
| Rolling update | Thay thế từng nhóm instance hoặc pod theo từng đợt | Hệ thống có nhiều bản sao và hỗ trợ chạy song song phiên bản |
| Blue-green | Duy trì hai môi trường; kiểm chứng môi trường mới rồi chuyển lưu lượng | Cần chuyển đổi nhanh và có khả năng giữ môi trường cũ để quay lại |
| Canary | Chuyển một tỷ lệ nhỏ lưu lượng sang phiên bản mới rồi tăng dần | Muốn quan sát tác động trên một phần người dùng trước khi mở rộng |

Triển khai an toàn cần xác định trước tiêu chí bắt đầu, phạm vi lưu lượng, điều kiện dừng và cách khôi phục. Với canary, ví dụ, có thể bắt đầu ở tỷ lệ nhỏ, theo dõi lỗi và độ trễ, rồi chỉ tăng lưu lượng khi chỉ số nằm trong ngưỡng. Với blue-green, cần xác minh môi trường mới trước khi đổi hướng lưu lượng.

Cũng cần kiểm tra khả năng tương thích giữa các phiên bản khi nhiều instance chạy đồng thời. API, schema cơ sở dữ liệu, message format và cache key có thể được sử dụng bởi cả phiên bản cũ lẫn mới trong thời gian chuyển tiếp.

## 10. Kiểm chứng sau triển khai trên môi trường đích

Một lệnh deploy thành công chỉ chứng minh nền tảng triển khai đã thực hiện được thao tác. Nó chưa chứng minh người dùng có thể sử dụng hệ thống bình thường. Vì vậy, sau triển khai phải có bước xác minh độc lập.

Có thể tổ chức xác minh theo nhiều lớp:

1. **Trạng thái triển khai:** nền tảng báo đúng phiên bản, instance hoặc pod đã sẵn sàng.
2. **Health check:** tiến trình và các phụ thuộc thiết yếu đáp ứng điều kiện sẵn sàng.
3. **Smoke test:** các luồng cốt lõi như đăng nhập, đọc dữ liệu hoặc tạo giao dịch thử nghiệm hoạt động.
4. **Integration hoặc synthetic test:** kiểm tra tương tác với dịch vụ bên ngoài bằng yêu cầu có kiểm soát.
5. **Quan sát vận hành:** theo dõi tỷ lệ lỗi, độ trễ, lưu lượng, tài nguyên và log trong khoảng thời gian phù hợp.
6. **Xác nhận danh tính phiên bản:** đối chiếu commit hoặc artifact digest đang chạy với bản phát hành dự kiến.

Health check nên phân biệt giữa trạng thái tiến trình còn sống và trạng thái sẵn sàng phục vụ. Một ứng dụng có thể vẫn chạy nhưng chưa kết nối được cơ sở dữ liệu hoặc chưa nạp xong cấu hình. Nếu chỉ kiểm tra tiến trình, pipeline có thể kết luận thành công quá sớm.

Tiêu chí xác minh cần gắn với hành vi và rủi ro của hệ thống. Với dịch vụ giao dịch, tỷ lệ lỗi và khả năng ghi nhận giao dịch quan trọng hơn việc chỉ nhận được mã HTTP thành công. Với hệ thống xử lý nền, cần theo dõi hàng đợi, độ trễ xử lý và tỷ lệ tác vụ thất bại.

Kết quả xác minh phải được lưu cùng bản phát hành. Nếu kiểm tra thất bại, pipeline cần dừng mở rộng rollout, phát tín hiệu cho người chịu trách nhiệm và kích hoạt phương án khôi phục đã định trước.

## 11. Chuẩn bị quay lui và khắc phục

Rollback là đưa hệ thống về trạng thái phiên bản trước đã biết là ổn định. Khả năng quay lui cần được thiết kế trước khi phát hành, bởi trong sự cố người vận hành thường không có đủ thời gian để tạo một quy trình mới.

Một phương án quay lui cần trả lời:

- Phiên bản ổn định gần nhất là artifact nào? Có thể truy xuất bằng digest không?
- Ai hoặc điều kiện nào được phép kích hoạt rollback?
- Có thể chuyển lại lưu lượng hoặc triển khai lại artifact cũ trong bao lâu?
- Cấu hình và schema dữ liệu có còn tương thích với phiên bản cũ không?
- Làm sao xác minh hệ thống đã phục hồi?
- Những dữ liệu đã ghi bởi phiên bản mới có cần xử lý riêng không?

Không phải lỗi nào cũng nên rollback. Nếu lỗi có thể sửa nhanh bằng một bản vá an toàn và việc quay lui làm mất dữ liệu hoặc tạo thêm gián đoạn, forward fix có thể phù hợp hơn. Với thay đổi dữ liệu không thể đảo ngược, cần có kế hoạch phục hồi dữ liệu riêng. Feature flag cũng có thể giúp tắt nhanh một chức năng mới mà không cần triển khai lại toàn bộ ứng dụng.

Sau khi khôi phục, cần lưu thời điểm phát hiện, phạm vi ảnh hưởng, artifact liên quan, quyết định xử lý và kết quả xác minh. Những thông tin này hỗ trợ phân tích nguyên nhân và cải thiện cổng chất lượng cho các lần phát hành sau.

## 12. Giữ khả năng truy vết từ commit đến môi trường chạy

Một luồng CI/CD đáng tin cậy phải nối được các dấu mốc:

**Commit SHA → sự kiện Git → pipeline run → kết quả build/test → artifact digest → lần triển khai → môi trường → kết quả xác minh.**

Mỗi mắt xích nên có định danh và liên kết đến bằng chứng tương ứng. Ví dụ, khi một người báo lỗi trên production, nhóm có thể xác định phiên bản đang chạy, tìm artifact digest, mở pipeline đã tạo artifact đó, xem commit nguồn và đọc báo cáo kiểm thử.

Một bản ghi phát hành tối thiểu nên có:

| Thông tin | Ý nghĩa |
|---|---|
| Phiên bản và commit SHA | Xác định thay đổi mã nguồn |
| Pipeline run ID | Tìm log và kết quả tự động hóa |
| Artifact name và digest | Xác định chính xác đầu ra được triển khai |
| Môi trường và thời điểm | Biết artifact đã được đưa đến đâu, khi nào |
| Người hoặc chính sách phê duyệt | Truy lại quyết định phát hành |
| Kết quả kiểm thử và xác minh | Có bằng chứng về chất lượng và trạng thái sau triển khai |
| Trạng thái rollout hoặc rollback | Biết lần phát hành kết thúc như thế nào |

Truy vết không chỉ phục vụ kiểm toán. Nó giúp điều tra sự cố nhanh hơn, so sánh hai lần phát hành và xác định liệu lỗi xuất hiện từ thay đổi mã nguồn, artifact, cấu hình hay môi trường.

## 13. Đi qua một tình huống phát hành mẫu

Giả sử nhóm phát triển một dịch vụ web và chuẩn bị hợp nhất thay đổi vào nhánh chính.

1. Nhà phát triển mở pull request. Sự kiện này kích hoạt pipeline kiểm tra định dạng, lint, unit test và các chính sách bắt buộc. Job kiểm tra không nhận bí mật production.
2. Khi pull request đạt yêu cầu và được hợp nhất, pipeline của nhánh chính chạy lại các kiểm tra cần thiết, build ứng dụng và chạy kiểm thử tích hợp.
3. Pipeline tạo một artifact, tính digest và lưu artifact cùng metadata gồm commit SHA và pipeline run ID.
4. Chính artifact đó được triển khai lên môi trường test hoặc staging. Pipeline chạy health check, smoke test và các kiểm tra hồi quy cần thiết.
5. Nếu các cổng chất lượng đạt, quy trình phân phối liên tục có thể chờ phê duyệt production. Người phê duyệt xem commit, artifact, kết quả kiểm thử và môi trường đích.
6. Sau khi được phép, pipeline triển khai cùng artifact lên production theo chiến lược rolling, blue-green hoặc canary đã chọn.
7. Pipeline xác nhận phiên bản đang chạy, kiểm tra các luồng nghiệp vụ quan trọng và theo dõi chỉ số vận hành. Nếu chỉ số vượt ngưỡng, rollout dừng và phương án rollback hoặc khắc phục được kích hoạt.
8. Kết quả cuối cùng được ghi vào bản ghi phát hành, liên kết ngược đến commit, pipeline và artifact.

Điểm quan trọng của tình huống này là mọi môi trường đều nhận cùng một artifact đã được xác định danh tính. Mỗi bước chuyển tiếp có điều kiện rõ ràng và để lại bằng chứng. Khi có sự cố, nhóm không phải đoán bản build nào đang chạy hoặc tìm thủ công xem ai đã triển khai.

## 14. Các lỗi thường gặp và cách điều tra

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Pipeline không chạy | Trigger hoặc bộ lọc nhánh không khớp; sự kiện không được gửi | Kiểm tra sự kiện Git, điều kiện trigger và lịch sử lần chạy |
| Build lúc đạt lúc lỗi | Dependency không khóa, môi trường build thay đổi hoặc cache không nhất quán | So sánh phiên bản công cụ, dependency và log giữa các lần chạy |
| Kiểm thử thất bại trên CI nhưng đạt ở máy cá nhân | Khác biệt cấu hình, dữ liệu, timezone, dịch vụ phụ thuộc hoặc thứ tự chạy | Tái tạo môi trường CI và cô lập phụ thuộc ngoài |
| Deploy không tìm thấy artifact | Sai tên, phiên bản, quyền truy cập hoặc registry | Đối chiếu metadata, digest và quyền đọc artifact |
| Staging đạt nhưng production lỗi | Cấu hình, dữ liệu, quyền hoặc tải thực tế khác nhau | So sánh cấu hình được cấp, dependency và telemetry giữa môi trường |
| Job lộ thông tin nhạy cảm | In biến môi trường, bật debug hoặc cấp secret cho job không tin cậy | Xác định log và phạm vi truy cập, thu hồi/luân chuyển secret nếu cần |
| Deploy báo thành công nhưng dịch vụ không dùng được | Chỉ kiểm tra thao tác deploy, thiếu health check hoặc smoke test | Kiểm tra readiness, log ứng dụng, dependency và luồng nghiệp vụ |
| Rollback không khôi phục hoàn toàn | Schema hoặc dữ liệu đã thay đổi không tương thích | Kiểm tra migration, khả năng chạy song song phiên bản và kế hoạch dữ liệu |

Khi điều tra, nên lần theo chuỗi bằng chứng từ điểm thất bại đầu tiên. Không nên chỉ chạy lại pipeline nhiều lần mà không xác định nguyên nhân; việc chạy lại có thể che khuất lỗi phụ thuộc thời điểm hoặc tạo thêm thay đổi trên môi trường.

## 15. Lộ trình thực hành và tiêu chí hoàn thành

Có thể học theo các bài tập tăng dần sau:

1. **Vẽ luồng từ Git:** chọn các sự kiện push, pull request, merge và tag; ghi rõ mỗi sự kiện được phép thực hiện những công việc nào.
2. **Tạo pipeline kiểm tra:** tự động checkout mã nguồn, cài dependency đã khóa, lint, build và chạy unit test. Quan sát cách pipeline báo lỗi khi một bước thất bại.
3. **Đóng gói artifact:** tạo artifact từ commit xác định, tính digest và lưu metadata. Kiểm tra rằng có thể tải lại đúng artifact.
4. **Promote qua môi trường:** triển khai artifact đã tạo lên test hoặc staging; cấp cấu hình theo môi trường và chạy smoke test.
5. **Thêm cổng chất lượng và quyền:** yêu cầu kiểm thử đạt, giới hạn quyền của job và thêm phê duyệt cho môi trường cần kiểm soát.
6. **Kiểm chứng production có kiểm soát:** chọn chiến lược rollout, theo dõi chỉ số sau triển khai và diễn tập dừng rollout hoặc quay lui trong môi trường an toàn.
7. **Kiểm tra truy vết:** từ một deployment, tìm được commit, pipeline run, artifact digest, người hoặc chính sách phê duyệt và kết quả xác minh.

Có thể xem bài thực hành hoàn thành khi người học chứng minh được các điều sau:

- Giải thích được sự kiện Git nào kích hoạt từng pipeline và vì sao.
- Đọc được pipeline dưới dạng mã, nhận diện điều kiện chạy và quyền của từng job.
- Tự động build và chạy kiểm thử với đầu vào có thể lặp lại.
- Tạo, lưu và xác định artifact bằng phiên bản cùng digest.
- Đưa cùng artifact qua các môi trường với cấu hình được quản lý riêng.
- Thiết lập quality gate và bảo vệ secret theo nguyên tắc quyền tối thiểu.
- Xác minh được phiên bản và sức khỏe hệ thống sau triển khai.
- Truy vết được một bản phát hành và mô tả cách rollback hoặc khắc phục.

## Kết luận

CI/CD là một chuỗi kiểm soát liên tục nối thay đổi mã nguồn với hệ thống đang phục vụ người dùng. Sự kiện Git xác định khi nào quy trình bắt đầu; pipeline-as-code mô tả cách quy trình vận hành; build và test tạo bằng chứng về chất lượng; artifact bất biến bảo đảm đầu ra có danh tính; quản lý môi trường và quality gate kiểm soát việc phát hành; quản lý secret bảo vệ quyền truy cập; còn xác minh sau triển khai và rollback giúp hệ thống phục hồi khi kết quả thực tế không như mong đợi.

Khi từng bước đều có điều kiện, quyền hạn, đầu ra và bằng chứng rõ ràng, nhóm có thể phát hành thường xuyên hơn mà vẫn kiểm soát được rủi ro và giải thích được chính xác điều gì đã chạy trên môi trường đích.

