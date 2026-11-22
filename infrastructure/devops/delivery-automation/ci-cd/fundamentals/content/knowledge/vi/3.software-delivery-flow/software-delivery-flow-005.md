# Phân biệt kiểm tra trước khi tích hợp với kiểm tra sau khi tích hợp

Trong một luồng CI/CD, mã nguồn thường đi qua hai thời điểm kiểm tra quan trọng: trước khi thay đổi được hợp nhất vào nhánh dùng chung và sau khi thay đổi đã trở thành một phần của trạng thái tích hợp. Hai thời điểm này trả lời hai câu hỏi khác nhau. Kiểm tra trước tích hợp giúp quyết định một thay đổi có đủ điều kiện gia nhập nhánh chung hay không. Kiểm tra sau tích hợp xác minh rằng trạng thái mã nguồn thực tế sau khi hợp nhất vẫn hoạt động đúng khi kết hợp với các thay đổi khác và các thành phần liên quan.

Phân biệt đúng hai nhóm kiểm tra giúp nhóm phát triển phản hồi nhanh mà vẫn kiểm soát rủi ro phát hành. Nếu chỉ kiểm tra trước khi hợp nhất, nhóm có thể bỏ sót lỗi chỉ xuất hiện khi nhiều thay đổi cùng tồn tại. Nếu chỉ kiểm tra sau khi hợp nhất, lỗi có thể đã đi vào nhánh chính, ảnh hưởng người khác và làm gián đoạn luồng giao phần mềm. Vì vậy, pipeline cần phối hợp cả hai lớp với mục tiêu, phạm vi, thời gian phản hồi và điều kiện chặn khác nhau.

## 1. Xác định điểm tích hợp trong luồng giao phần mềm

Trong bài học này, **tích hợp** chủ yếu nói đến việc đưa một thay đổi mã nguồn vào nhánh dùng chung mà nhóm sử dụng để phát triển hoặc phát hành, thường thông qua pull request hoặc merge request. Tùy nền tảng và quy trình, nhánh dùng chung có thể là **main**, **master**, **develop** hoặc một nhánh tích hợp chuyên biệt.

Một thay đổi thường đi qua các trạng thái:

1. Nhà phát triển tạo commit trên nhánh làm việc.
2. Pull request được mở để yêu cầu hợp nhất thay đổi.
3. Pipeline chạy các kiểm tra trước tích hợp trên commit hoặc kết quả hợp nhất dự kiến.
4. Khi các điều kiện bắt buộc đạt, thay đổi được hợp nhất vào nhánh dùng chung.
5. Pipeline sau tích hợp chạy trên commit đã hợp nhất.
6. Nếu đạt các điều kiện tiếp theo, hệ thống tạo hoặc promote artifact, triển khai lên môi trường và xác minh kết quả.

Sơ đồ dưới đây thể hiện hai lớp kiểm tra và mối liên hệ với phát hành:

~~~mermaid
flowchart TD
    A["Commit trên nhánh làm việc"] --> B["Mở hoặc cập nhật pull request"]
    B --> C["Kiểm tra trước tích hợp"]
    C --> D{"Các cổng bắt buộc đạt?"}
    D -- "Không" --> E["Trả phản hồi, sửa thay đổi"]
    E --> B
    D -- "Có" --> F["Review và hợp nhất"]
    F --> G["Commit tích hợp trên nhánh dùng chung"]
    G --> H["Kiểm tra sau tích hợp"]
    H --> I{"Trạng thái tích hợp đạt?"}
    I -- "Không" --> J["Điều tra, sửa lỗi hoặc khôi phục"]
    I -- "Có" --> K["Đóng gói và lưu artifact"]
    K --> L["Triển khai môi trường"]
    L --> M["Smoke test và xác minh"]
    M --> N["Sẵn sàng phát hành / tiếp tục rollout"]
~~~

Điểm cần nhớ là kiểm tra trước tích hợp và sau tích hợp không chỉ khác nhau ở thời điểm chạy. Chúng có **đầu vào**, **mục tiêu**, **mức độ cô lập**, **phạm vi kiểm tra** và **quyết định mà kết quả hỗ trợ** khác nhau.

Ngoài việc hợp nhất mã nguồn, một hệ thống còn có thể tích hợp dịch vụ, cơ sở dữ liệu, message broker hoặc API của bên thứ ba. Các kiểm tra ở hai thời điểm vẫn cần xác định rõ đang kiểm tra thay đổi trong repository, tương tác giữa các thành phần hay trạng thái của toàn hệ thống.

## 2. Kiểm tra trước tích hợp là gì?

**Kiểm tra trước tích hợp (pre-integration checks)** là các kiểm tra được thực hiện trước khi thay đổi được chấp nhận vào nhánh dùng chung. Trong quy trình pull request, chúng thường được kích hoạt khi pull request được tạo hoặc cập nhật.

Mục tiêu chính là phát hiện sớm lỗi thuộc về thay đổi đang đề xuất và cung cấp bằng chứng để người review quyết định có nên hợp nhất hay không. Nhà phát triển nhận phản hồi khi thay đổi vẫn còn ở phạm vi họ đang kiểm soát, vì vậy việc sửa lỗi thường ít gây ảnh hưởng dây chuyền hơn.

Các nhóm kiểm tra thường gặp gồm:

- **Kiểm tra định dạng và quy ước:** phát hiện mã không tuân theo quy tắc của dự án.
- **Phân tích tĩnh:** tìm lỗi có thể nhận biết mà không cần chạy toàn bộ ứng dụng.
- **Kiểm thử đơn vị:** xác minh logic của hàm, lớp hoặc thành phần nhỏ.
- **Kiểm thử component:** kiểm tra một thành phần trong phạm vi cô lập, có thể thay thế phụ thuộc bên ngoài bằng mock hoặc fake.
- **Kiểm tra biên dịch và build:** xác nhận thay đổi có thể được biên dịch hoặc đóng gói với cấu hình dự án.
- **Kiểm thử hợp đồng có mục tiêu:** xác minh thay đổi vẫn tuân thủ hợp đồng API hoặc message đã công bố.
- **Kiểm tra bảo mật và phụ thuộc:** phát hiện secret bị commit, dependency có vấn đề hoặc cấu hình không phù hợp với chính sách.
- **Một số kiểm thử tích hợp trong môi trường tạm:** khi cần xác minh thay đổi với dịch vụ phụ thuộc trước khi hợp nhất.

Không có quy tắc rằng mọi kiểm tra trước tích hợp đều phải là kiểm thử đơn vị. Một kiểm thử tích hợp có thể chạy trước khi merge nếu nó kiểm tra thay đổi trong một môi trường cô lập và có chi phí hợp lý. Tên gọi của lớp kiểm tra được xác định bởi thời điểm và mục đích trong luồng, còn loại kiểm thử được xác định bởi phạm vi tương tác mà nó bao phủ.

### 2.1. Đầu vào của kiểm tra trước tích hợp

Pipeline cần xác định chính xác mã nào đang được kiểm tra. Có một số cách phổ biến:

- **Commit của nhánh pull request:** kiểm tra đúng commit mới nhất do tác giả tạo.
- **Merge candidate:** kiểm tra kết quả giả lập khi ghép nhánh pull request với nhánh đích hiện tại.
- **Merge queue hoặc merge train:** nền tảng tạo một ứng viên tích hợp theo thứ tự, kiểm tra kết quả kết hợp với các thay đổi đang chờ hợp nhất.

Chỉ kiểm tra commit của nhánh pull request có thể chưa phát hiện xung đột hành vi với thay đổi mới nhất trên nhánh đích. Ví dụ, nhánh đích vừa đổi chữ ký một hàm, trong khi nhánh tính năng vẫn gọi chữ ký cũ. Kiểm thử trên nhánh tính năng có thể đạt nếu nó đang dùng mã nguồn cũ; kết quả merge candidate mới cho thấy lỗi biên dịch hoặc kiểm thử.

Vì vậy, với repository có nhiều pull request đồng thời, kiểm tra kết quả hợp nhất dự kiến hoặc dùng merge queue có thể tăng độ tin cậy. Điều kiện quan trọng là trạng thái được kiểm tra phải tương ứng với trạng thái thực sự được hợp nhất. Nếu nhánh đích thay đổi sau khi kiểm tra, pipeline cần chạy lại hoặc kiểm tra lại merge candidate mới.

### 2.2. Tiêu chí của một bộ kiểm tra trước tích hợp

Bộ kiểm tra trước tích hợp nên ưu tiên:

- Phản hồi đủ nhanh để không làm chậm vòng lặp phát triển.
- Kết quả ổn định và có thể lặp lại.
- Chỉ ra rõ commit, job và bước kiểm tra bị lỗi.
- Có khả năng chạy lại trên cùng đầu vào để tái hiện vấn đề.
- Chặn hợp nhất khi một kiểm tra bắt buộc thất bại.
- Không cấp quyền hoặc bí mật vượt quá nhu cầu của thay đổi chưa được tin cậy.

Các kiểm tra nhanh như lint, phân tích tĩnh và unit test thường được chạy sớm. Kiểm thử tích hợp nặng hoặc kiểm thử đầu cuối có thể được chọn theo mức rủi ro, chạy song song hoặc chuyển sang giai đoạn sau nếu thời gian phản hồi của pull request trở nên quá dài. Dù vậy, những kiểm tra được xem là điều kiện bắt buộc để bảo vệ nhánh chung phải có quy tắc rõ ràng và không bị bỏ qua tùy tiện.

## 3. Kiểm tra sau tích hợp là gì?

**Kiểm tra sau tích hợp (post-integration checks)** là các kiểm tra chạy sau khi thay đổi đã được hợp nhất vào nhánh dùng chung. Pipeline thường được kích hoạt bởi sự kiện push hoặc merge trên nhánh đó.

Mục tiêu là xác minh trạng thái mã nguồn mới nhất trong bối cảnh tích hợp thực tế. Ở thời điểm này, hệ thống có thể chứa nhiều thay đổi đã được chấp nhận, nên nhóm cần biết liệu các thay đổi đó có tương thích với nhau và còn đáp ứng yêu cầu của sản phẩm hay không.

Các nhóm kiểm tra thường gặp:

- **Build từ nhánh dùng chung:** xác nhận commit tích hợp có thể tạo ra đầu ra hợp lệ.
- **Kiểm thử tích hợp:** xác minh tương tác giữa các module, dịch vụ, cơ sở dữ liệu hoặc message broker.
- **Kiểm thử hợp đồng ở phạm vi hệ thống:** kiểm tra tương thích giữa producer và consumer đang được kết hợp.
- **Kiểm thử hồi quy:** xác minh các luồng đã hoạt động trước đây vẫn đúng sau khi tích hợp.
- **Kiểm thử hệ thống hoặc đầu cuối:** thực hiện luồng nghiệp vụ qua nhiều thành phần.
- **Kiểm tra migration và tương thích dữ liệu:** xác minh thay đổi schema hoặc dữ liệu có thể phối hợp với phiên bản ứng dụng liên quan.
- **Kiểm tra bảo mật ở phạm vi rộng:** quét artifact, container image hoặc tập dependency cuối cùng.
- **Kiểm tra chất lượng artifact:** xác nhận đầu ra có metadata, digest và có thể lưu vào registry.
- **Kiểm tra triển khai và smoke test:** xác minh ứng dụng hoạt động sau khi được đưa lên môi trường tích hợp, test hoặc staging.

Không phải tất cả dự án đều chạy toàn bộ các kiểm tra này ngay sau mỗi lần merge. Phạm vi phụ thuộc vào thời gian, kiến trúc và rủi ro. Một số kiểm thử hệ thống có thể chạy theo lịch, trước release hoặc sau khi triển khai lên staging. Tuy nhiên, các kiểm tra được dùng để quyết định có tiếp tục phát hành hay không cần được đặt ở vị trí thích hợp trong pipeline và có kết quả truy vết được.

### 3.1. Vì sao cần kiểm tra lại sau khi hợp nhất?

Ngay cả khi từng pull request đều đạt, trạng thái sau khi hợp nhất vẫn có thể thất bại:

- Hai thay đổi riêng lẻ cùng sửa một giả định chung theo hai cách không tương thích.
- Một thay đổi cập nhật producer nhưng consumer khác chưa được cập nhật.
- Migration cơ sở dữ liệu không tương thích với phiên bản ứng dụng còn đang chạy.
- Cấu hình build trên nhánh chính khác với cấu hình cục bộ của pull request.
- Một thay đổi làm hỏng luồng nghiệp vụ cũ mà bộ kiểm thử riêng của pull request không bao phủ.
- Nhiều thay đổi đồng thời làm tăng thời gian khởi động, mức sử dụng bộ nhớ hoặc số lần gọi dịch vụ.
- Artifact được tạo từ trạng thái tích hợp có thành phần hoặc dependency khác với môi trường kiểm tra trước merge.

Kiểm tra sau tích hợp cung cấp một lớp xác nhận độc lập trên trạng thái đã trở thành nguồn chung. Nó giúp phát hiện lỗi tích hợp trước khi trạng thái đó được dùng để tạo bản phát hành hoặc triển khai lên môi trường nhạy cảm.

## 4. So sánh hai lớp kiểm tra

| Tiêu chí | Trước tích hợp | Sau tích hợp |
|---|---|---|
| Thời điểm | Khi thay đổi đang được đề xuất, trước khi merge | Sau khi thay đổi đã vào nhánh dùng chung |
| Đầu vào | Commit pull request hoặc merge candidate | Commit đã tích hợp trên nhánh chung |
| Câu hỏi chính | Thay đổi này có đủ điều kiện được hợp nhất không? | Trạng thái tích hợp mới có hoạt động đúng không? |
| Phạm vi ưu tiên | Lỗi cục bộ, chất lượng thay đổi, tương thích dự kiến | Tương tác giữa thay đổi, hồi quy và hành vi toàn hệ thống |
| Môi trường | Thường cô lập, tạm thời hoặc dùng phụ thuộc giả lập | Có thể dùng môi trường tích hợp với các dịch vụ thật hoặc gần thật |
| Tốc độ mong muốn | Phản hồi nhanh để hỗ trợ review | Có thể lâu hơn nếu cần kiểm tra sâu |
| Quyết định | Cho phép hoặc chặn merge | Cho phép hoặc chặn đóng gói, promote hay phát hành |
| Phạm vi tác động khi lỗi | Chủ yếu ảnh hưởng pull request đang đề xuất | Có thể ảnh hưởng nhánh chung và các nhóm phụ thuộc |
| Bằng chứng | Check status, log, báo cáo kiểm thử của pull request | Kết quả pipeline của commit tích hợp, báo cáo và artifact liên quan |

Sự khác biệt này không có nghĩa một loại kiểm thử chỉ được chạy ở một phía. Unit test có thể chạy cả trước và sau tích hợp. Kiểm thử hợp đồng cũng có thể chạy ở cả hai thời điểm. Điều quan trọng là **mỗi lần chạy phải có lý do rõ ràng và xác nhận đúng rủi ro ở thời điểm đó**.

Ví dụ, unit test trên pull request giúp tác giả phát hiện lỗi trong thay đổi. Chạy lại unit test trên nhánh chính giúp xác nhận build tích hợp vẫn nhất quán với cấu hình và đầu vào của nhánh chung. Hai lần chạy có thể dùng cùng bộ test nhưng trả lời hai câu hỏi vận hành khác nhau.

## 5. Phân bổ loại kiểm thử theo rủi ro và thời gian phản hồi

Không nên thiết kế pipeline bằng cách đưa mọi test vào một nhóm duy nhất. Hãy phân loại theo thời gian chạy, độ tin cậy, phạm vi phụ thuộc và mức độ nghiêm trọng nếu lỗi bị bỏ sót.

| Nhóm kiểm tra | Trước tích hợp | Sau tích hợp | Lý do phân bổ |
|---|---|---|---|
| Format, lint, phân tích tĩnh | Thường bắt buộc | Có thể chạy lại hoặc dùng kết quả build chung | Phản hồi nhanh về chất lượng thay đổi |
| Unit test | Thường bắt buộc | Thường chạy trong bộ xác nhận nhánh chung | Xác minh logic và trạng thái build tích hợp |
| Component test | Theo thành phần thay đổi | Có thể chạy trong bộ hồi quy | Kiểm tra ranh giới thành phần |
| Integration test | Chọn lọc, dùng môi trường tạm | Thường mở rộng phạm vi | Xác minh tương tác thật giữa các thành phần |
| Contract test | Có thể kiểm tra hợp đồng bị ảnh hưởng | Xác minh producer/consumer đã tích hợp | Giảm lỗi không tương thích API hoặc message |
| End-to-end test | Chọn lọc cho luồng quan trọng | Chạy trên trạng thái tích hợp hoặc môi trường phù hợp | Kiểm tra luồng nghiệp vụ xuyên hệ thống |
| Security scan | Quét thay đổi, secret và dependency | Quét artifact hoặc image cuối cùng | Phát hiện rủi ro ở cả mã nguồn và đầu ra |
| Smoke test sau deploy | Không áp dụng nếu chưa triển khai | Chạy sau khi triển khai môi trường | Xác nhận ứng dụng thực sự sẵn sàng |

Một quy tắc thực dụng là đặt kiểm tra có chi phí thấp và khả năng phát hiện lỗi cao ở đầu pipeline. Kiểm tra tốn thời gian hơn được chạy sau khi các bước cơ bản đạt, hoặc trên môi trường phù hợp. Việc chạy song song có thể rút ngắn tổng thời gian, nhưng cần bảo đảm các job không tranh chấp tài nguyên hay dữ liệu dùng chung.

Không nên dùng thời gian chạy làm tiêu chí duy nhất. Một kiểm thử đầu cuối có thể chậm nhưng bảo vệ luồng thanh toán quan trọng; một kiểm tra bảo mật có thể tốn thời gian nhưng cần thiết trước phát hành. Cần xác định mức độ rủi ro mà từng kiểm tra bao phủ, tần suất cần chạy và thời điểm kết quả phải sẵn sàng.

## 6. Thiết kế pipeline với hai cổng rõ ràng

Pipeline có thể chia thành hai nhóm stage chính: xác nhận thay đổi trước merge và xác nhận trạng thái sau merge. Tên job tùy nền tảng, nhưng quan hệ phụ thuộc nên thể hiện rõ.

~~~yaml
# Mô hình khái niệm, không phải cú pháp của một nền tảng CI/CD cụ thể.
pipeline:
  on_pull_request:
    jobs:
      fast_checks:
        steps:
          - checkout_pull_request
          - format_and_lint
          - static_analysis
          - unit_tests
          - build_candidate

      focused_integration:
        needs: [fast_checks]
        steps:
          - start_temporary_dependencies
          - run_affected_integration_tests
          - contract_checks

      merge_gate:
        needs: [fast_checks, focused_integration]
        condition: all_required_checks_pass

  on_push_to_shared_branch:
    jobs:
      integrated_validation:
        steps:
          - checkout_integrated_commit
          - build
          - unit_tests
          - integration_tests
          - regression_tests

      package:
        needs: [integrated_validation]
        steps:
          - create_artifact
          - calculate_digest
          - publish_artifact

      environment_validation:
        needs: [package]
        steps:
          - deploy_to_test_environment
          - smoke_tests
          - verify_running_version
~~~

Ví dụ trên chỉ mô tả ý tưởng tổ chức stage. Cấu hình thật cần dùng cú pháp và cơ chế của nền tảng CI/CD đang sử dụng.

### 6.1. Cổng trước tích hợp

Cổng trước tích hợp nên có danh sách kiểm tra bắt buộc, trạng thái hiển thị rõ trên pull request và chính sách nhánh yêu cầu các kiểm tra đó đạt trước khi merge.

Một số quyết định cần xác định:

- Có bắt buộc review của người khác không?
- Có yêu cầu pull request phải cập nhật với nhánh đích không?
- Khi nhánh đích thay đổi, có cần chạy lại kiểm tra merge candidate không?
- Kiểm thử nào là bắt buộc và kiểm thử nào chỉ mang tính thông tin?
- Ai có quyền cho phép ngoại lệ và ngoại lệ được ghi nhận ở đâu?

Không nên cho phép một job tùy chọn thất bại nhưng vẫn được hiểu nhầm là cổng bắt buộc đã đạt. Tên và trạng thái các check phải giúp người review hiểu được điều kiện thực sự.

### 6.2. Cổng sau tích hợp

Cổng sau tích hợp xác nhận trạng thái của nhánh dùng chung trước khi tiếp tục đóng gói, promote hoặc phát hành. Cần xác định:

- Build và bộ kiểm thử nào phải đạt trên commit đã merge?
- Có cần kiểm thử tích hợp với dịch vụ thật hoặc môi trường tạm không?
- Artifact có được tạo từ chính commit đã kiểm tra không?
- Nếu kiểm thử thất bại, nhánh chung được xử lý thế nào?
- Có dừng pipeline phát hành hoặc chặn promote artifact không?
- Ai chịu trách nhiệm điều tra và khôi phục trạng thái nhánh?

Nếu nhánh chính được bảo vệ, nhóm có thể yêu cầu quy trình sửa lỗi nhanh, revert hoặc hotfix khi kiểm tra sau tích hợp thất bại. Với hệ thống dùng merge queue, việc kiểm tra trước merge trên merge candidate giúp giảm khả năng đưa trạng thái lỗi vào nhánh chung, nhưng vẫn cần xác minh sau khi commit thực tế được tạo.

## 7. Quản lý đầu vào, artifact và tính nhất quán

Một trong những nguyên nhân khiến kết quả trước và sau tích hợp khó so sánh là hai pipeline không kiểm tra cùng một đầu vào hoặc không sử dụng cùng một quy trình build.

Cần ghi nhận tối thiểu:

- Commit SHA của nhánh pull request.
- Commit SHA của nhánh đích tại thời điểm kiểm tra.
- Merge candidate hoặc merge commit SHA nếu có.
- Pipeline run ID và phiên bản cấu hình pipeline.
- Phiên bản runtime, compiler, build tool và dependency.
- Môi trường kiểm thử và phiên bản dịch vụ phụ thuộc.
- Kết quả test, log và báo cáo.
- Artifact digest nếu pipeline tạo artifact.

Với quy trình phát hành, nên tạo artifact từ commit tích hợp đã vượt qua các cổng sau merge, sau đó promote chính artifact đó qua test, staging và production. Nếu pipeline trước merge cũng tạo artifact tạm để kiểm thử, cần phân biệt rõ artifact ứng viên với artifact phát hành. Không nên vô tình triển khai artifact được build từ một commit pull request khác với commit đã hợp nhất.

Trong trường hợp merge queue tạo và kiểm tra một merge candidate, nền tảng có thể cho phép tái sử dụng kết quả nếu commit thực tế được hợp nhất chính là đầu vào đã kiểm tra và các điều kiện về môi trường, cấu hình, dependency vẫn còn hiệu lực. Nếu đầu vào thay đổi, kết quả cũ không còn là bằng chứng đầy đủ cho trạng thái mới.

## 8. Xử lý khi kiểm tra thất bại

Cách phản ứng với lỗi trước và sau tích hợp khác nhau vì phạm vi tác động khác nhau.

### 8.1. Lỗi trước tích hợp

Khi một kiểm tra trên pull request thất bại:

1. Giữ pull request ở trạng thái chưa đủ điều kiện merge.
2. Hiển thị job, bước và thông tin lỗi có thể hành động.
3. Xác định lỗi thuộc về thay đổi, môi trường kiểm thử hay hạ tầng CI.
4. Tác giả cập nhật commit hoặc người vận hành khắc phục hạ tầng.
5. Chạy lại các kiểm tra cần thiết trên đầu vào mới nhất.
6. Chỉ cho phép merge khi các cổng bắt buộc đã đạt.

Không nên cho phép merge chỉ vì một lần chạy trước đó từng đạt nếu pull request đã có commit mới. Trạng thái kiểm tra phải gắn với đúng commit hoặc merge candidate.

### 8.2. Lỗi sau tích hợp

Khi kiểm tra trên nhánh dùng chung thất bại:

1. Xác định commit tích hợp và lần chạy pipeline bị ảnh hưởng.
2. Dừng các bước đóng gói, promote hoặc phát hành phụ thuộc vào kết quả đó.
3. Thông báo cho người sở hữu thay đổi và nhóm phụ thuộc.
4. Phân loại lỗi: lỗi mã nguồn, xung đột tích hợp, cấu hình, dependency hay hạ tầng kiểm thử.
5. Chọn cách khôi phục phù hợp: sửa trực tiếp, revert commit, tạo hotfix hoặc khôi phục môi trường.
6. Chạy lại bộ kiểm tra sau khi trạng thái được sửa.
7. Lưu kết quả và nguyên nhân để cải thiện quy trình.

Nếu nhánh chung là nguồn tạo release, một trạng thái đỏ kéo dài có thể chặn nhiều nhóm khác. Vì vậy, nhóm cần có quy ước ưu tiên khôi phục nhánh chung, người chịu trách nhiệm và cơ chế báo hiệu rõ ràng.

Không phải mọi lỗi sau merge đều đòi hỏi revert ngay lập tức. Quyết định phụ thuộc vào mức độ ảnh hưởng, khả năng cô lập, thời gian sửa và nguy cơ phát hành nhầm. Tuy nhiên, pipeline phải ngăn một trạng thái chưa được xác minh tiếp tục đi qua các cổng phát hành đã quy định.

## 9. Những bẫy thường gặp

### Chỉ kiểm tra nhánh pull request, không kiểm tra kết quả hợp nhất

Một pull request có thể đạt trên nền mã nguồn cũ của nhánh đích nhưng thất bại khi ghép với thay đổi mới. Cách giảm rủi ro là kiểm tra merge candidate, yêu cầu cập nhật nhánh đích hoặc dùng merge queue.

### Coi kiểm tra sau merge là bản sao không cần thiết

Chạy lại cùng bộ test có vẻ tốn thời gian, nhưng kiểm tra sau merge xác nhận một commit và cấu hình cụ thể trên nhánh dùng chung. Có thể tối ưu bằng cache, chia test hoặc tái sử dụng kết quả có điều kiện, nhưng cần bảo đảm bằng chứng vẫn đúng với đầu vào thực tế.

### Đưa mọi kiểm thử nặng vào pull request

Điều này làm phản hồi chậm, khuyến khích người phát triển tìm cách bỏ qua kiểm tra và làm giảm năng suất review. Hãy phân tầng theo rủi ro, chạy song song và đặt kiểm tra ở thời điểm phù hợp. Không chuyển một kiểm tra quan trọng sang sau merge chỉ để làm pull request nhanh hơn nếu điều đó khiến nhánh chung thường xuyên bị hỏng.

### Chỉ chạy kiểm thử đầu cuối

Kiểm thử đầu cuối bao phủ luồng lớn nhưng thường chậm, khó định vị nguyên nhân và dễ phụ thuộc môi trường. Cần kết hợp unit test, component test, integration test và end-to-end test theo phạm vi phù hợp.

### Không quản lý flaky test

Một kiểm thử lúc đạt lúc không làm mất niềm tin vào cổng chất lượng. Cần theo dõi tần suất thất bại không ổn định, lưu bằng chứng, xác định chủ sở hữu và sửa nguyên nhân. Tự động retry có thể hỗ trợ phân loại tạm thời nhưng không nên biến lỗi chập chờn thành trạng thái được chấp nhận lâu dài.

### Dùng secret production trong pipeline của pull request

Mã nguồn từ pull request, đặc biệt từ fork hoặc nguồn chưa tin cậy, có thể thực thi lệnh trong quá trình build/test. Không cấp bí mật triển khai production cho các job đó. Dùng quyền tối thiểu, secret theo môi trường và thông tin xác thực ngắn hạn khi nền tảng hỗ trợ.

### Không gắn kết quả kiểm tra với commit

Một dấu xanh không có ý nghĩa nếu không biết nó thuộc commit nào. Mọi kết quả phải gắn với commit SHA hoặc merge candidate cụ thể. Khi đầu vào thay đổi, trạng thái cũ cần được xem là không còn đại diện cho thay đổi mới.

## 10. Tình huống minh họa: hai pull request cùng thay đổi một hợp đồng

Giả sử một nhóm có dịch vụ đơn hàng và dịch vụ thanh toán. Hai pull request được phát triển song song:

- Pull request A thay đổi trường dữ liệu trong yêu cầu thanh toán.
- Pull request B cập nhật consumer để đọc trường mới.

Mỗi pull request có thể chạy unit test và build riêng. Nếu A kiểm tra trên phiên bản consumer cũ hoặc B kiểm tra trên phiên bản producer cũ, cả hai vẫn có thể đạt trong môi trường cô lập tùy cách mock phụ thuộc. Khi hai thay đổi được tích hợp không đúng thứ tự hoặc chỉ một thay đổi được hợp nhất, hệ thống có thể phát sinh lỗi tương thích.

Một quy trình kiểm tra phù hợp có thể là:

1. Trước tích hợp, pull request A chạy lint, unit test, contract test cho schema mới và kiểm tra tương thích với consumer hiện hành.
2. Trước tích hợp, pull request B chạy unit test, contract test và xác minh consumer xử lý được dữ liệu theo hợp đồng đã thống nhất.
3. Nếu hai pull request phụ thuộc lẫn nhau, nhóm dùng merge queue hoặc một nhánh tích hợp tạm để kiểm tra tổ hợp thay đổi.
4. Sau khi hợp nhất, pipeline chạy integration test giữa producer và consumer trên trạng thái chung.
5. Bộ kiểm thử hồi quy xác minh luồng tạo đơn hàng và thanh toán.
6. Nếu tất cả đạt, pipeline đóng gói artifact, triển khai môi trường test và chạy smoke test.

Tình huống này cho thấy kiểm tra riêng từng thay đổi không thay thế được kiểm tra tương tác sau tích hợp. Đồng thời, contract test trước merge giúp phát hiện sớm thay đổi không tương thích trước khi nó đi vào nhánh chung.

## 11. Đo lường hiệu quả của hai lớp kiểm tra

Để cải thiện pipeline, cần đo cả tốc độ phản hồi lẫn khả năng phát hiện lỗi. Một số chỉ số hữu ích:

| Chỉ số | Ý nghĩa | Cách sử dụng |
|---|---|---|
| Thời gian phản hồi pull request | Thời gian từ khi mở/cập nhật PR đến khi có kết quả bắt buộc | Tìm job làm chậm vòng lặp review |
| Tỷ lệ pull request phải sửa do kiểm tra thất bại | Mức độ lỗi được phát hiện trước merge | Phân loại lỗi phổ biến và cải thiện hướng dẫn |
| Tỷ lệ pipeline sau merge thất bại | Mức độ ổn định của trạng thái tích hợp | Tìm lỗi tương tác hoặc lỗ hổng của bộ kiểm tra trước merge |
| Thời gian khôi phục nhánh chung | Thời gian từ khi phát hiện lỗi đến khi trạng thái tích hợp ổn định | Đánh giá quy trình xử lý sự cố |
| Tỷ lệ flaky test | Mức độ ổn định của bộ kiểm thử | Ưu tiên sửa test làm giảm độ tin cậy |
| Defect escape | Lỗi chỉ được phát hiện ở môi trường sau hoặc bởi người dùng | Xác định khoảng trống kiểm tra |
| Thời gian từ merge đến artifact sẵn sàng | Độ trễ từ tích hợp đến đầu ra có thể phát hành | Tối ưu stage sau tích hợp |

Không nên tối ưu một chỉ số đơn lẻ. Ví dụ, giảm thời gian pull request bằng cách loại bỏ mọi kiểm tra có thể làm tỷ lệ lỗi sau merge tăng. Ngược lại, thêm nhiều kiểm tra mà không quan tâm thời gian và độ tin cậy có thể khiến nhóm bỏ qua pipeline. Mục tiêu là chọn được tập kiểm tra phát hiện rủi ro quan trọng với chi phí và thời gian phản hồi phù hợp.

## 12. Lộ trình thực hành

Có thể thực hành theo các bước sau trên một repository mẫu:

1. **Xác định điểm tích hợp:** chọn nhánh dùng chung, quy tắc pull request và sự kiện kích hoạt pipeline.
2. **Tạo bộ kiểm tra trước merge:** thêm format, lint, static analysis, unit test và build candidate.
3. **Gắn cổng vào pull request:** cấu hình các check bắt buộc và thử nghiệm một thay đổi cố ý gây lỗi để xác nhận merge bị chặn.
4. **Kiểm tra merge candidate:** tạo hai nhánh thay đổi độc lập, cập nhật nhánh đích rồi xác minh pipeline phát hiện xung đột hoặc lỗi do tổ hợp thay đổi.
5. **Tạo pipeline sau merge:** kích hoạt khi có commit trên nhánh chung, chạy build và bộ kiểm thử tích hợp.
6. **Thêm kiểm thử hệ thống:** chạy contract test, regression test hoặc end-to-end test trên môi trường phù hợp.
7. **Quản lý artifact:** tạo artifact từ commit tích hợp, lưu digest và metadata, rồi triển khai artifact đó lên môi trường test.
8. **Thử nghiệm đường lỗi:** tạo một lỗi chỉ xuất hiện khi hai thành phần tương tác, xác nhận pipeline sau merge chặn bước phát hành.
9. **Kiểm tra truy vết:** từ kết quả pipeline, xác định commit, test report, artifact và môi trường đã được xác minh.

### Tiêu chí hoàn thành

Người học có thể xem bài thực hành hoàn thành khi chứng minh được:

- Giải thích được mục tiêu và thời điểm của kiểm tra trước tích hợp và sau tích hợp.
- Phân biệt được commit pull request, merge candidate và commit đã tích hợp.
- Chọn được kiểm tra phù hợp với rủi ro và thời gian phản hồi của từng giai đoạn.
- Cấu hình được cổng bắt buộc trước merge.
- Chạy được kiểm tra trên trạng thái mã nguồn thực tế sau merge.
- Giải thích được vì sao một pull request đạt vẫn có thể khiến pipeline sau merge thất bại.
- Xử lý được lỗi trước merge và lỗi sau merge theo đúng phạm vi tác động.
- Gắn kết quả kiểm tra với commit, pipeline run và artifact có liên quan.

## Kết luận

Kiểm tra trước tích hợp bảo vệ nhánh dùng chung bằng cách đánh giá thay đổi khi nó còn đang được đề xuất. Kiểm tra sau tích hợp bảo vệ trạng thái chung bằng cách xác minh các thay đổi đã kết hợp với nhau. Hai lớp có thể dùng chung nhiều loại test, nhưng cần tách rõ đầu vào, mục tiêu, điều kiện đạt và quyết định mà kết quả hỗ trợ.

Một luồng giao phần mềm vững chắc đưa phản hồi nhanh đến pull request, kiểm tra trạng thái hợp nhất thực tế, lưu bằng chứng theo commit và chỉ tiếp tục đóng gói hoặc phát hành khi các cổng cần thiết đã đạt. Khi tổ chức được hai lớp kiểm tra như vậy, nhóm giảm lỗi lọt vào nhánh chung, rút ngắn thời gian điều tra và giữ được khả năng truy vết từ thay đổi mã nguồn đến artifact được triển khai.

