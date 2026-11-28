# Deploy permission

## 1. Quyền triển khai trong quản lý truy cập đặc quyền

Deploy permission là quyền đưa một phiên bản phần mềm hoặc cấu hình vào môi trường thực thi. Đối tượng được triển khai có thể là ứng dụng, container image, gói thư viện nội bộ, cấu hình dịch vụ, migration cơ sở dữ liệu hoặc khai báo hạ tầng phục vụ ứng dụng.

Trong PAM, quyền triển khai là một dạng đặc quyền vì nó có thể làm thay đổi mã và cấu hình mà hệ thống tin cậy để vận hành. Người có quyền đưa mã vào production có thể ảnh hưởng đến dữ liệu, tính sẵn sàng, credential và các ranh giới phân quyền, ngay cả khi họ không giữ vai trò application admin trên giao diện.

Ví dụ, một nhân viên không được phép xuất dữ liệu khách hàng qua API nghiệp vụ nhưng lại được tự đưa bất kỳ mã nào vào dịch vụ xử lý khách hàng. Nếu dịch vụ có quyền đọc dữ liệu đó, đường triển khai có thể trở thành đường truy cập gián tiếp. Phân tích quyền chỉ dựa vào tài khoản tương tác của nhân viên sẽ bỏ sót khả năng này.

Quản lý deploy permission cần trả lời đồng thời:

- Ai được yêu cầu, phê duyệt và thực hiện triển khai?
- Được triển khai ứng dụng nào, vào môi trường và phạm vi tài nguyên nào?
- Được chọn artifact nào và sửa những tham số nào?
- Danh tính triển khai và danh tính ứng dụng đang chạy có quyền gì?
- Quyền có hiệu lực trong bao lâu, thu hồi bằng cách nào?
- Bằng chứng nào liên kết thay đổi đã duyệt với phiên bản thực sự đang chạy?

Sau bài học, bạn có thể phân tích đường đặc quyền của một quy trình triển khai, thiết kế quyền tối thiểu cho người và workload, và kiểm chứng cả giới hạn truy cập lẫn kết quả thu hồi.

## 2. Tách quyền phát triển, phát hành, triển khai và vận hành

Một chuỗi phân phối phần mềm thường có nhiều điểm kiểm soát. Chúng liên quan nhưng không phải cùng một quyền.

| Loại quyền | Năng lực điển hình | Rủi ro cần nhận diện |
|---|---|---|
| Sửa mã nguồn | Đề xuất hoặc hợp nhất thay đổi | Đưa logic làm thay đổi quyền hoặc xử lý dữ liệu |
| Sửa định nghĩa pipeline | Thay bước build, nguồn artifact, danh tính thực thi | Biến pipeline thành công cụ thực hiện tác vụ ngoài ý định |
| Build | Chuyển đầu vào thành artifact | Chèn hoặc thay phụ thuộc, tạo artifact không khớp đầu vào |
| Phát hành | Chấp thuận một artifact làm ứng viên sử dụng | Gắn tính hợp lệ cho một phiên bản chưa được kiểm tra |
| Triển khai | Đưa artifact và cấu hình vào đích | Thực thi mã dưới quyền của môi trường đích |
| Vận hành runtime | Can thiệp tiến trình, máy, pod hoặc dịch vụ | Chạy lệnh, đọc secret, sửa trạng thái ngoài luồng triển khai |
| Phê duyệt | Chấp thuận thay đổi trong một phạm vi cụ thể | Tự hợp thức hóa thay đổi nếu thiếu sự độc lập |
| Sửa chính sách bảo vệ | Đổi điều kiện để các quyền trên có hiệu lực | Vô hiệu hóa chính các điểm kiểm soát |

Một người có thể cần nhiều loại quyền, nhưng phải nhận diện từng loại. Cụm từ “được dùng CI/CD” quá rộng để làm mô tả quyền.

Chẳng hạn, được khởi chạy một workflow đã khóa để triển khai artifact đã duyệt vào staging khác hẳn với được sửa workflow rồi chạy nó bằng credential production. Trong trường hợp thứ hai, giới hạn của quyền không nằm ở tên nút “Deploy” mà nằm ở toàn bộ khả năng sửa lệnh, đầu vào và danh tính thực thi.

## 3. Phân tích quyền hiệu lực qua chuỗi triển khai

### 3.1. Ba danh tính cần phân biệt

Một triển khai có thể có ít nhất ba chủ thể:

1. Người yêu cầu hoặc kích hoạt triển khai.
2. Danh tính workload của bộ điều phối hoặc job triển khai.
3. Danh tính runtime mà ứng dụng sử dụng sau khi khởi động.

Ví dụ, Lan kích hoạt job production. Job dùng danh tính deploy-orders-prod. Ứng dụng chạy dưới danh tính runtime-orders-prod.

Nếu danh tính triển khai chỉ được cập nhật dịch vụ Orders nhưng có thể gán cho dịch vụ một danh tính runtime mạnh bất kỳ, phạm vi tác động của nó vẫn có thể rất lớn. Tương tự, không cần quyền đọc trực tiếp secret nếu người triển khai có thể thay mã ứng dụng đang được cấp secret đó.

Mục tiêu không phải coi mọi quyền triển khai đều tương đương quản trị toàn hệ thống. Cần xác định chính xác chuỗi quyền thực tế và các giới hạn đã được hệ thống thực thi.

### 3.2. Đồ thị tin cậy minh họa

~~~mermaid
flowchart LR
    A[Người yêu cầu] --> B[Workflow triển khai]
    C[Người sửa workflow] --> B
    D[Artifact đã duyệt] --> B
    E[Phê duyệt gắn với artifact và đích] --> B
    B --> F[Danh tính triển khai]
    F --> G[Ứng dụng production]
    G --> H[Danh tính runtime]
    H --> I[Dữ liệu và dịch vụ phụ thuộc]
~~~

Các mũi tên biểu diễn quan hệ ảnh hưởng, không có nghĩa mọi chủ thể đều được truy cập trực tiếp đối tượng tiếp theo.

Khi đánh giá quyền, hãy hỏi ai có thể sửa từng nút và từng điều kiện nối giữa chúng. Một tài khoản không có quyền production trực tiếp vẫn có thể điều khiển bước build hoặc chính sách phát hành để tác động vào production.

### 3.3. Kiểm tra các đường nâng quyền gián tiếp

Một số câu hỏi quan trọng:

- Người khởi chạy có được nhập lệnh tùy ý không?
- Có thể chọn runner, môi trường hoặc credential khác không?
- Có thể đổi role mà pipeline yêu cầu khi nhận credential không?
- Có thể sửa nơi lấy artifact, tag hoặc digest không?
- Có thể sửa danh tính runtime, quyền truy cập secret hoặc volume gắn vào ứng dụng không?
- Có thể thay sidecar, init task, hook triển khai hoặc migration không?
- Có thể làm pipeline dùng mã hoặc cấu hình từ nguồn chưa được phê duyệt không?
- Có thể vô hiệu hóa audit, chính sách xác minh hoặc bước phê duyệt không?

Không phải hệ thống nào cũng có mọi năng lực trong danh sách. Đây là các đường cần kiểm chứng, không phải kết luận về một sản phẩm cụ thể.

## 4. Định nghĩa phạm vi quyền triển khai

Một phép cấp quyền nên mô tả được chủ thể, hành động, tài nguyên, điều kiện và thời gian.

| Chiều phạm vi | Ví dụ | Điều cần tránh |
|---|---|---|
| Ứng dụng | Chỉ dịch vụ Orders | Quyền triển khai toàn bộ danh mục ứng dụng vì cùng một đội |
| Môi trường | Staging hoặc production cụ thể | Mọi môi trường dùng chung một credential |
| Đơn vị sở hữu | Dự án, account, tenant, cluster hoặc namespace được duyệt | Dùng tên namespace như bằng chứng cô lập đầy đủ |
| Loại thao tác | Cập nhật phiên bản đã tồn tại | Mặc nhiên cho tạo role, cấp quyền và sửa chính sách |
| Artifact | Digest cụ thể từ nguồn được tin cậy | Cho nhập URL hoặc tag bất kỳ |
| Cấu hình | Tập khóa và miền giá trị được phép | Cho truyền mọi biến môi trường hoặc mọi manifest |
| Danh tính runtime | Danh tính đã duyệt cho ứng dụng | Tự chọn danh tính có đặc quyền cao hơn |
| Thời gian | Cửa sổ kích hoạt gắn với tác vụ | Quyền thường trực cho người chỉ triển khai định kỳ |

Một ranh giới tổ chức không tự là ranh giới bảo mật. Ví dụ, nếu người triển khai được tạo workload có quyền truy cập tài nguyên cấp host hoặc các danh tính không thuộc ứng dụng, việc chỉ giới hạn vào một namespace có thể chưa đáp ứng ý định kiểm soát.

Phải kiểm tra cả quyền cập nhật tài nguyên và quyền quyết định nội dung được cập nhật.

### Ví dụ về mô tả quyền

Mô tả chưa đủ:

> Nhóm Release có quyền deploy production.

Mô tả rõ hơn:

> Nhóm Release được yêu cầu triển khai artifact đã được phê duyệt của Orders vào production của đơn vị A. Bộ điều phối chỉ nhận digest đã đăng ký, dùng danh tính triển khai riêng và giữ nguyên danh tính runtime được duyệt. Thay đổi quyền, secret và chính sách bảo vệ đi theo quy trình riêng.

Mô tả này mới là ý định. Cần ánh xạ từng giới hạn vào khả năng thực thi và ca kiểm thử tương ứng.

## 5. Thiết kế vai trò theo tác vụ và phân tách trách nhiệm

Đội nhỏ không nhất thiết phải tạo nhiều chức danh. Tuy nhiên, quy trình cần thể hiện ai có thể đề xuất, chấp thuận và thực hiện thay đổi có tác động cao.

Ma trận dưới đây là thiết kế minh họa:

| Hành động | Người phát triển | Người duyệt phát hành | Bộ điều phối triển khai | Quản trị nền tảng | Người kiểm toán |
|---|---|---|---|---|---|
| Đề xuất thay đổi mã | Có | Theo nhiệm vụ | Không | Theo nhiệm vụ | Không |
| Tạo bản build | Qua pipeline đã duyệt | Không mặc định | Không mặc định | Không mặc định | Không |
| Chấp thuận artifact cho production | Không tự duyệt thay đổi của mình | Có trong phạm vi | Không | Không mặc định | Không |
| Yêu cầu triển khai production | Theo chính sách | Theo chính sách | Nhận yêu cầu hợp lệ | Không mặc định | Không |
| Ghi thay đổi vào đích production | Không trực tiếp theo luồng chuẩn | Không trực tiếp | Có trong phạm vi | Qua quyền quản trị riêng | Không |
| Sửa chính sách cấp credential | Không | Không | Không | Qua thay đổi được kiểm soát | Không |
| Đọc bằng chứng triển khai | Theo nhu cầu | Có trong phạm vi | Ghi bằng chứng | Theo nhu cầu | Có trong phạm vi |

Cần kiểm soát cả tổ hợp quyền. Một người có thể không tự duyệt release nhưng lại sửa được danh sách người duyệt, tắt bảo vệ môi trường hoặc thay workflow để bỏ qua phê duyệt. Khi đó, phân tách trên biểu mẫu chưa tạo ra sự độc lập thực tế.

Hai tài khoản do cùng một cá nhân điều khiển cũng không tự tạo thành hai bên độc lập.

### Quản trị pipeline là đặc quyền riêng

Ai được sửa pipeline có thể quyết định:

- Lệnh nào chạy trên runner.
- Đầu vào nào được tin cậy.
- Credential nào được yêu cầu.
- Điều kiện nào dẫn đến production.
- Bằng chứng nào được tạo hoặc bị bỏ qua.

Vì vậy, thay đổi pipeline, cấu hình bảo vệ môi trường và chính sách danh tính của pipeline cần được quản lý như thay đổi đặc quyền. Không nên chỉ kiểm soát người bấm triển khai ở cuối chuỗi.

## 6. Danh tính workload và quản lý credential

### 6.1. Dùng danh tính riêng cho từng ranh giới

Build không mặc nhiên cần credential production. Job kiểm thử cũng không nên kế thừa quyền triển khai chỉ vì dùng cùng hệ thống CI.

Có thể phân tách theo các ranh giới phù hợp:

- Build và triển khai.
- Staging và production.
- Ứng dụng hoặc nhóm tài nguyên.
- Quy trình bình thường và quy trình khẩn cấp.
- Job tin cậy và job xử lý đầu vào chưa tin cậy.

Số lượng danh tính cần đủ để giới hạn phạm vi mà vẫn quản lý được. Không nên tạo quá nhiều tài khoản rồi bỏ quên chủ sở hữu, chính sách và vòng đời.

Mỗi danh tính phải có chủ sở hữu, mục đích, phạm vi, nguồn gọi hợp lệ và cơ chế thu hồi.

### 6.2. Credential ngắn hạn cần ràng buộc đúng ngữ cảnh

Nếu nền tảng hỗ trợ cấp credential ngắn hạn từ danh tính workload, chính sách tin cậy cần xác minh các thuộc tính phù hợp như nguồn phát hành, đối tượng nhận token, danh tính workflow, nguồn mã và môi trường đã được hệ thống bảo vệ.

Tên môi trường do người dùng nhập không đủ để chứng minh một job đã đi qua cổng production. Thuộc tính dùng để cấp quyền phải có ý nghĩa bảo mật rõ ràng và không bị người khởi chạy tự giả mạo.

Mô hình khái niệm:

~~~text
Yêu cầu credential
    -> Xác minh bằng chứng danh tính workload
    -> Kiểm tra nguồn workflow và điều kiện được bảo vệ
    -> Chọn role và scope được phép từ phía cấp quyền
    -> Cấp credential ngắn hạn
    -> Ghi sự kiện có mã job và thời hạn
~~~

Không để job yêu cầu tùy ý một role mạnh hơn bằng cách sửa tham số đầu vào.

Credential ngắn hạn làm giảm thời gian sử dụng một credential bị lộ. Nó không làm hẹp quyền của credential và cũng không ngăn việc liên tục nhận credential mới nếu quyền nhận vẫn còn.

### 6.3. Khi phải dùng credential lưu trong vault

Với hệ thống chưa hỗ trợ danh tính workload phù hợp, có thể cần credential được quản lý trong vault. Khi đó cần giới hạn:

- Job nào được lấy credential.
- Phiên bản hoặc nguồn workflow nào được dùng.
- Thời gian và mục đích được lấy.
- Quyền tại hệ thống đích.
- Cách rotate, vô hiệu hóa và xử lý sự cố.

Không ghi credential vào log, artifact build, cache hoặc đầu ra debug. Che chuỗi trên giao diện log là một lớp hỗ trợ; nó không bảo đảm bí mật không bị truyền sang nơi khác.

Runner xử lý job chưa tin cậy không nên có sẵn đường tiếp cận credential production. Nếu runner được tái sử dụng, cần kiểm soát trạng thái còn lại từ job trước, bao gồm file, tiến trình, cache và công cụ đã bị thay đổi.

## 7. Artifact, cấu hình và phê duyệt phải gắn với nhau

### 7.1. Định danh nội dung thay vì chỉ định danh nhãn

Nhãn như “release-candidate” hoặc “latest” có thể trỏ sang nội dung khác nếu hệ thống cho phép cập nhật nhãn. Nếu duyệt nhãn rồi triển khai nhãn ở thời điểm khác, chưa chắc hai bước dùng cùng artifact.

Một hồ sơ triển khai nên liên kết với định danh nội dung bất biến, chẳng hạn digest, cùng nguồn phát hành và bằng chứng build liên quan.

Digest giúp phát hiện nội dung có khác hay không. Nó không tự chứng minh mã an toàn, artifact đến từ nguồn được phép hoặc build đã qua kiểm thử.

Tương tự, chữ ký chỉ có ý nghĩa khi chính sách xác minh kiểm tra đúng người hoặc workload ký, mục đích, phạm vi và quan hệ với nguồn build được tin cậy. “Có chữ ký” không đồng nghĩa “được phép triển khai production”.

### 7.2. Phê duyệt cả những đầu vào làm thay đổi hành vi

Cùng một artifact có thể hoạt động khác đáng kể nếu thay:

- Cấu hình kết nối cơ sở dữ liệu.
- Đích webhook hoặc nơi xuất dữ liệu.
- Feature flag.
- Danh tính runtime.
- Secret reference.
- Migration hoặc hook chạy kèm.
- Chính sách mạng và tài nguyên gắn vào workload.

Vì vậy, yêu cầu phê duyệt cần liên kết những đầu vào có ý nghĩa đối với tác vụ, không chỉ tên phiên bản phần mềm.

Ví dụ một thay đổi đã được duyệt cho artifact A, cấu hình C và đích T. Nếu người thực thi đổi thành artifact B hoặc chọn danh tính runtime khác, hệ thống phải đánh giá lại theo chính sách. Một dấu “approved” chung không nên được tái sử dụng cho một tập đầu vào khác.

### 7.3. Chống thay đổi giữa lúc duyệt và lúc thực thi

Cần kiểm tra lại các tham chiếu và điều kiện quan trọng tại thời điểm triển khai. Nếu có thể, dùng tham chiếu nội dung bất biến, bản chụp cấu hình hoặc revision cụ thể.

Với rollout dài, cũng phải xác định điều gì xảy ra nếu phê duyệt hoặc quyền bị thu hồi trong khi tác vụ đang chạy. Chính sách cần phân biệt việc ngừng nhận thao tác mới, dừng các bước chưa chạy và xử lý phần thay đổi đã áp dụng.

Không nên giả định thu hồi quyền sẽ tự hoàn tác các replica đã cập nhật.

## 8. JIT và JEA cho hoạt động triển khai

### 8.1. JIT: quyền có hiệu lực khi có nhu cầu

Trong luồng JIT, người dùng hoặc workload chỉ có quyền triển khai trong một cửa sổ được phép, gắn với yêu cầu cụ thể.

Luồng minh họa:

1. Người dùng tạo yêu cầu với ứng dụng, đích, artifact và cấu hình.
2. Hệ thống kiểm tra điều kiện và phê duyệt cần thiết.
3. Quyền hoặc phiên triển khai được kích hoạt trong thời hạn phù hợp.
4. Pipeline nhận credential có phạm vi đúng với yêu cầu.
5. Triển khai, thu bằng chứng và kết thúc quyền.
6. Kiểm tra lại quyền cấp mới, phiên đang tồn tại và phần thay đổi còn lại.

Khoảng thời gian quyền của con người, thời hạn credential của job và thời gian rollout có thể khác nhau. Cần xác định quan hệ giữa chúng thay vì coi một trường thời gian hết hạn là đã giải quyết toàn bộ vòng đời.

### 8.2. JEA: chỉ làm được tác vụ đã định nghĩa

Một giao diện “triển khai Orders bằng digest đã duyệt” có thể hẹp hơn đáng kể so với quyền chạy shell trên máy production.

JEA trong bối cảnh này có thể giới hạn:

- Tập ứng dụng và môi trường.
- Hành động được phép thực hiện.
- Nguồn và định danh artifact.
- Các khóa cấu hình được thay đổi.
- Danh tính runtime được sử dụng.
- Hook, plugin và lệnh bổ sung.
- Phương án rollback được phép.

Nếu job nhận một chuỗi lệnh tự do hoặc manifest không bị ràng buộc, việc đặt tên nó là “JEA deployment” không làm phạm vi thực thi trở nên hẹp.

### 8.3. Quyền tạm thời vẫn có thể tạo hậu quả lâu dài

Trong vài phút triển khai, một chủ thể có thể đưa mã mới vào chạy nhiều tháng, tạo tài khoản phụ, sửa chính sách hoặc thiết lập tác vụ định kỳ nếu quyền cho phép.

Hết hạn quyền không tự xóa các thay đổi này. Phân tích JIT phải xem cả những hiện vật và đường truy cập mà job có thể tạo.

Với triển khai hợp lệ, việc phiên bản mới tiếp tục chạy là kết quả mong muốn. Vấn đề cần kiểm soát là liệu người triển khai có thể để lại đường truy cập ngoài yêu cầu đã duyệt hay không.

## 9. Mô hình chính sách minh họa

Mẫu dưới đây mô tả ý định quản trị, không phải cú pháp cấu hình của một sản phẩm cụ thể:

~~~yaml
deployment_grant:
  request_id: CHANGE-EX-042
  application: orders
  environment: production
  target_scope: orders-production-A
  requester_reference: "<danh tính người yêu cầu>"
  executor_identity: deploy-orders-prod
  allowed_action: update-approved-release

  release:
    artifact_reference: "<nguồn artifact được duyệt>"
    artifact_digest: "<digest đầy đủ của nội dung>"
    configuration_revision: "<revision cấu hình đã duyệt>"
    runtime_identity: runtime-orders-prod
    migration_revision: "<revision migration hoặc none>"

  approval:
    record_reference: APPROVAL-EX-042
    independent_review_required: true
    bind_to_release_and_target: true

  activation:
    start: "<thời điểm có múi giờ>"
    end: "<thời điểm có múi giờ>"
    request_new_credentials_after_expiry: deny

  boundaries:
    arbitrary_command_execution: deny
    change_runtime_identity: deny
    manage_access_policy: deny
    read_secret_values: deny
    change_audit_configuration: deny

  evidence:
    correlation_id: DEPLOY-EX-042
    accountable_owner: team-orders
~~~

Các giá trị “deny” trong mẫu là yêu cầu thiết kế. Chúng chỉ có tác dụng khi được ánh xạ vào các lớp thực thi phù hợp.

Ví dụ, cấm API đọc secret trực tiếp vẫn chưa loại trừ đường đọc secret qua mã ứng dụng. Nếu quyền triển khai cho phép thay mã tùy ý dưới danh tính runtime có secret, phải đánh giá và kiểm soát đường đó ở chuỗi review, build, phát hành và triển khai.

## 10. Điểm kiểm soát trong bộ điều phối

Một bộ điều phối không nên tin rằng mọi yêu cầu đến từ giao diện được bảo vệ đều hợp lệ.

Giả mã sau minh họa các nhóm kiểm tra:

~~~text
xu_ly_trien_khai(yeu_cau):
    nguoi_yeu_cau = xac_minh_danh_tinh_va_phien(yeu_cau)
    dich = xac_lap_dich_trong_pham_vi_duoc_phep(nguoi_yeu_cau, yeu_cau)
    ban_phat_hanh = nap_ban_phat_hanh_bat_bien(yeu_cau.release_id)

    kiem_tra_quyen_dang_hieu_luc(nguoi_yeu_cau, dich)
    kiem_tra_phe_duyet_gan_voi(
        ban_phat_hanh,
        dich,
        cau_hinh,
        danh_tinh_runtime,
        migration
    )
    kiem_tra_nguon_artifact_va_bang_chung_duoc_yeu_cau()
    kiem_tra_gioi_han_cau_hinh_va_chinh_sach_dich()

    danh_tinh_job = xac_lap_danh_tinh_workload_tin_cay()
    credential = cap_credential_gioi_han(danh_tinh_job, dich, thoi_han)

    ghi_su_kien_bat_dau_khong_chua_bi_mat()
    ap_dung_thay_doi_theo_ke_hoach()
    doi_soat_phien_ban_va_cau_hinh_thuc_te()
    ghi_ket_qua_va_cac_buoc_chua_hoan_tat()
    ket_thuc_kha_nang_nhan_credential_theo_chinh_sach()
~~~

Đây không phải triển khai hoàn chỉnh. Một hệ thống thực tế còn cần xử lý lỗi từng phần, tính lặp an toàn, yêu cầu trùng, cạnh tranh giữa nhiều rollout và độ sẵn sàng của các điểm kiểm soát.

Cổng production cũng phải được áp dụng cho API, scheduler và các đường tự động khác. Chỉ yêu cầu duyệt khi bấm nút trên giao diện sẽ không đủ nếu gọi API trực tiếp có thể bỏ qua cùng điều kiện.

## 11. Triển khai theo cơ chế pull và GitOps

Trong cơ chế pull, một agent hoặc bộ điều khiển bên trong môi trường lấy trạng thái mong muốn từ nguồn đã cấu hình rồi áp dụng thay đổi.

Mô hình này có thể giảm nhu cầu đưa credential trực tiếp của môi trường đích cho người dùng hoặc pipeline bên ngoài. Tuy nhiên, đặc quyền chuyển sang các điểm khác:

- Ai được sửa nguồn trạng thái mong muốn?
- Ai được đổi repository, branch hoặc đường dẫn mà controller theo dõi?
- Ai được sửa quyền và danh tính của controller?
- Nguồn artifact và cấu hình có được ràng buộc đúng không?
- Ai được tạm dừng đồng bộ hoặc áp dụng thay đổi trực tiếp?
- Ai được sửa chính sách xác minh và bảo vệ đích?

Quyền ghi vào nguồn mà controller tin cậy có thể là quyền triển khai gián tiếp. Một pull request thay manifest vẫn là yêu cầu đặc quyền nếu sau khi hợp nhất nó làm production thay đổi.

Controller cần quyền đủ cho phạm vi quản lý, không mặc nhiên có quyền toàn hệ thống. Nếu có cơ chế tự khôi phục trạng thái, quy trình can thiệp khẩn cấp phải xét việc controller có thể áp dụng lại một cấu hình chưa an toàn sau khi người vận hành đã sửa trực tiếp.

## 12. Migration, rollback và thay đổi khẩn cấp

### 12.1. Migration là thay đổi có ranh giới quyền riêng

Migration có thể cần quyền sửa schema hoặc chuyển đổi dữ liệu mà runtime thông thường không cần.

Nếu dùng cùng một credential mạnh cho runtime và migration, ứng dụng có thể giữ quyền quản trị dữ liệu suốt thời gian hoạt động. Một thiết kế khác là tách danh tính migration, cấp quyền theo tác vụ và đối soát sau khi hoàn thành.

Quyền của migration vẫn phải phù hợp với nội dung đã duyệt. Không nên coi một script tùy ý là an toàn chỉ vì nó nằm trong gói triển khai.

### 12.2. Rollback cũng là một triển khai

Quyền quay lại phiên bản trước có thể gây tác động lớn:

- Khôi phục một phiên bản có lỗ hổng đã biết.
- Đưa cấu hình hoặc quyền cũ trở lại.
- Gây không tương thích với schema hiện tại.
- Làm mất hoặc thay đổi cách xử lý dữ liệu.

Vì vậy, rollback cần artifact được định danh, điều kiện sử dụng và người chịu trách nhiệm. Có thể chuẩn bị sẵn một tập phiên bản quay lui đã được đánh giá để phản ứng nhanh, thay vì cho chọn bất kỳ phiên bản lịch sử nào.

Rollback mã không đồng nghĩa rollback dữ liệu. Migration không đảo ngược được cần phương án xử lý riêng.

### 12.3. Quy trình khẩn cấp phải thực hiện được

Khi pipeline chuẩn gặp sự cố, một tổ chức có thể cần đường break-glass. Đường này cần có danh tính riêng hoặc cơ chế nhận diện rõ, phạm vi, thời hạn, người kích hoạt, bằng chứng và rà soát sau sự kiện.

Nếu cần bỏ qua một cổng kiểm soát, phải xác định cổng nào, do ai quyết định và kiểm soát nào còn áp dụng. Không nên tạo một credential quản trị dùng chung không có thời hạn chỉ để dự phòng.

Sau khi dùng, cần đối soát thay đổi thực tế, credential đã cấp, cấu hình được can thiệp và những đường truy cập có thể còn tồn tại.

## 13. Nhật ký và bằng chứng kiểm toán

Một sự kiện “pipeline thành công” chưa chứng minh phiên bản được duyệt đã chạy đúng đích.

Chuỗi bằng chứng nên liên kết được:

~~~text
Yêu cầu thay đổi
  -> Phê duyệt và tập đầu vào được duyệt
  -> Nguồn mã, build và artifact được định danh
  -> Job cùng danh tính thực thi
  -> Credential và phạm vi được cấp
  -> Thao tác tại hệ thống đích
  -> Phiên bản và cấu hình thực tế sau triển khai
  -> Kết thúc quyền và xử lý ngoại lệ
~~~

Các trường phù hợp có thể gồm:

| Nhóm bằng chứng | Dữ liệu cần liên kết |
|---|---|
| Yêu cầu | Mã thay đổi, ứng dụng, môi trường, lý do, chủ sở hữu |
| Phê duyệt | Người duyệt, thời điểm, revision của tập đầu vào |
| Artifact | Digest, nguồn, build reference, kết quả xác minh cần thiết |
| Thực thi | Mã job, nguồn workflow, danh tính người và workload |
| Quyền | Role, scope, thời hạn, sự kiện cấp hoặc từ chối credential |
| Kết quả | Đối tượng đã đổi, revision thực tế, rollout thành công hay một phần |
| Thu hồi | Khả năng nhận credential mới, phiên cũ, ngoại lệ và biện pháp xử lý |

Không ghi giá trị secret, token hoặc khóa riêng vào bằng chứng. Khi lưu cấu hình trước và sau, cần loại bỏ hoặc che dữ liệu bí mật theo thiết kế.

Nếu người triển khai có thể sửa log trong môi trường đích, cần đưa bằng chứng quan trọng tới nơi mà quyền triển khai đó không tự chỉnh sửa được.

### Tín hiệu đáng điều tra

Một số thay đổi cần được đối chiếu với yêu cầu đã duyệt:

- Workflow production được sửa rồi lập tức dùng để nhận credential.
- Có yêu cầu credential từ nguồn hoặc môi trường không mong đợi.
- Artifact thực tế khác digest đã phê duyệt.
- Runtime identity, secret reference hoặc đích dữ liệu bị thay ngoài phạm vi.
- Có thay đổi trực tiếp ở production không liên kết được job hợp lệ.
- Quyền triển khai được dùng sau thời hạn hoặc ngoài ứng dụng được phép.
- Cấu hình audit, bảo vệ môi trường hoặc chính sách tin cậy bị giảm mức kiểm soát.

Một tín hiệu không tự chứng minh hành vi sai. Cần đủ ngữ cảnh để xác định đó là thay đổi hợp lệ, sai cấu hình hay sử dụng trái phép.

## 14. Thu hồi quyền và xử lý sự cố

Thu hồi deploy permission cần bao phủ các điểm cấp quyền thực tế, không chỉ bỏ người dùng khỏi một nhóm.

Một trình tự có thể gồm:

1. Ngừng chấp nhận yêu cầu triển khai mới của chủ thể bị thu hồi.
2. Thu hồi phép gán trực tiếp, nhóm và quyền ủy quyền liên quan.
3. Ngăn nhận thêm credential từ nguồn workflow hoặc danh tính bị ảnh hưởng.
4. Xác định credential đã cấp còn sử dụng được đến khi nào và có cơ chế vô hiệu hóa nào.
5. Kiểm tra job đang chạy, hàng đợi và thao tác chưa thực hiện.
6. Đối soát thay đổi đã áp dụng và hiện vật có thể tạo truy cập tồn dư.
7. Kiểm chứng kết quả ở cả bộ điều phối và hệ thống đích.

Việc chặn cấp credential mới không tự làm credential đang tồn tại mất hiệu lực. Dừng job cũng không chắc chấm dứt mọi hành động đã gửi tới hệ thống đích.

Trong sự cố credential bị lộ, cần xác định phạm vi tài nguyên có thể bị tác động và đối soát thay đổi thực tế. Nếu nghi ngờ artifact hoặc nguồn build bị ảnh hưởng, chỉ rotate credential triển khai chưa giải quyết được toàn bộ sự cố.

Cũng cần phân biệt:

- Thu hồi quyền thực hiện thay đổi tiếp theo.
- Ngăn hoặc dừng rollout còn đang diễn ra.
- Khôi phục trạng thái mong muốn.
- Xử lý dữ liệu hoặc bí mật đã bị tác động.

Mỗi việc cần một cơ chế và bằng chứng riêng.

## 15. Tình huống thực tế: triển khai dịch vụ Orders

### Bối cảnh

Đội ứng dụng cần phát hành Orders vào production. Luồng hiện tại cho phép người phát triển sửa workflow, chọn image bằng tag và dùng credential production chung. Credential này còn được phép thay danh tính runtime.

Một thành viên chỉ cần cập nhật phiên bản dịch vụ nhưng thực tế có thể làm nhiều hơn:

- Sửa workflow để chạy lệnh ngoài mục đích triển khai.
- Chọn nội dung khác dưới cùng tag.
- Dùng credential cho tài nguyên khác.
- Đổi runtime identity để mở rộng khả năng truy cập.

### Thiết kế được đề xuất

Đội tách build khỏi triển khai production. Build tạo artifact có digest và lưu bằng chứng nguồn. Hồ sơ phát hành liên kết digest, revision cấu hình, runtime identity và đích Orders production.

Người duyệt chấp thuận tập đầu vào này. Bộ điều phối chỉ nhận release đã duyệt, không nhận lệnh tự do. Danh tính triển khai được cấp credential ngắn hạn cho tài nguyên Orders production. Chính sách đích giới hạn loại cập nhật và danh tính runtime được sử dụng.

Thay đổi workflow production và chính sách cấp credential cần được kiểm soát riêng. Người phát triển có thể yêu cầu triển khai nhưng không tự biến workflow chưa được duyệt thành nguồn tin cậy.

### Kiểm thử giới hạn

| Ca kiểm thử | Kết quả mong đợi |
|---|---|
| Triển khai release đã duyệt vào Orders production | Thành công và có bằng chứng liên kết |
| Đổi digest sau khi được duyệt | Bị từ chối hoặc bắt buộc đánh giá lại |
| Dùng cùng quyền để cập nhật Payments | Bị từ chối |
| Đổi runtime identity ngoài tập cho phép | Bị từ chối |
| Thêm lệnh shell tùy ý vào yêu cầu | Không được chấp nhận |
| Yêu cầu credential từ workflow chưa được tin cậy | Bị từ chối |
| Gọi API triển khai trực tiếp để bỏ qua duyệt | Vẫn chịu cùng điều kiện |
| Nhận credential mới sau khi quyền hết hạn | Bị từ chối |
| Dùng credential cũ sau thu hồi | Có kết quả đúng với cơ chế vô hiệu hóa đã thiết kế |
| Đối chiếu runtime với release | Khớp digest và revision hoặc báo sai lệch rõ ràng |

Giới hạn còn lại phải được ghi nhận. Ví dụ, nếu credential đã cấp không thể bị hủy ngay, chính sách cần quy định thời hạn và biện pháp chặn tại đích có thể áp dụng. Không báo thu hồi tức thì khi kiến trúc chưa thực hiện được.

## 16. Những lỗi thường gặp

### Chỉ xét người bấm nút triển khai

Người sửa pipeline, nguồn artifact hoặc chính sách tin cậy có thể có ảnh hưởng lớn hơn người bấm nút. Cần rà soát cả chuỗi điều khiển.

### Dùng một danh tính cho mọi môi trường

Credential staging bị lộ có thể kéo theo production nếu cùng danh tính và scope. Phải xác định ranh giới thực sự ở hệ thống cấp quyền và đích.

### Cho phép chọn artifact bất kỳ sau phê duyệt

Phê duyệt một release không bảo vệ được triển khai nếu người thực thi có thể đổi nội dung mà vẫn giữ cùng mã phê duyệt.

### Coi TTL ngắn là least privilege

Credential có thời hạn ngắn vẫn có thể sửa chính sách, tạo danh tính mới hoặc triển khai mã tồn tại lâu dài nếu quyền quá rộng.

### Chỉ chặn đọc secret trực tiếp

Mã triển khai có thể tiếp cận secret qua runtime. Cần đánh giá đường sử dụng gián tiếp và quyền thay mã.

### Đồng nhất pipeline thành công với kết quả đúng

Job có thể thành công trong khi rollout chưa hoàn tất, một số replica vẫn chạy phiên bản cũ hoặc cấu hình khác bản duyệt. Cần đối soát trạng thái thực tế.

### Coi rollback là thao tác vô hại

Một phiên bản cũ có thể không còn được phép hoặc không tương thích dữ liệu hiện tại. Rollback phải nằm trong phạm vi quyền và kế hoạch thay đổi.

### Đánh dấu thu hồi ngay khi bỏ nhóm

Phiên cũ, credential đã cấp, job đang chạy và quyền tạo qua đường khác có thể vẫn tồn tại. Phải kiểm tra quyền hiệu lực.

## 17. Bài thực hành

Thiết kế quyền triển khai cho hai dịch vụ Orders và Payments, mỗi dịch vụ có staging và production.

Yêu cầu nghiệp vụ:

- Lập trình viên được triển khai phiên bản thử nghiệm vào staging.
- Production chỉ nhận release đã được duyệt.
- Nhân sự phụ trách Orders không tự triển khai Payments.
- Job build không có credential production.
- Có phương án rollback và triển khai khẩn cấp.
- Có thể thu hồi quyền một người mà vẫn giữ hệ thống hoạt động.

Sản phẩm cần tạo:

1. Sơ đồ ba nhóm danh tính: con người, triển khai và runtime.
2. Ma trận thao tác theo ứng dụng, môi trường và vai trò.
3. Danh mục những ai sửa được workflow, artifact source và chính sách tin cậy.
4. Hồ sơ phê duyệt liên kết artifact, cấu hình, runtime identity và đích.
5. Kế hoạch cấp credential, thời hạn, rotation và thu hồi.
6. Bảng kiểm thử có ca vượt ứng dụng, đổi artifact, bỏ qua phê duyệt và sau thu hồi.
7. Mẫu bằng chứng triển khai không chứa bí mật.
8. Phương án xử lý rollout một phần và quyền bị thu hồi khi job đang chạy.

Một phương án đạt phải chỉ ra nơi thực thi từng giới hạn. Nếu nền tảng chưa hỗ trợ một giới hạn, cần ghi rõ khoảng trống và biện pháp bù, không chỉ đặt một trường cấu hình minh họa rồi xem như đã bảo vệ.

## 18. Câu hỏi tự kiểm tra

**Vì sao deploy permission được xem là đặc quyền dù người dùng không có tài khoản admin ứng dụng?**

Vì họ có thể thay mã hoặc cấu hình được ứng dụng thực thi, từ đó tác động tới dữ liệu và năng lực mà runtime đang nắm giữ.

**Người có quyền khởi chạy pipeline có luôn có quyền sửa pipeline không?**

Không. Đây là hai năng lực khác nhau và nên được đánh giá riêng. Nếu chúng được gộp, người dùng có thể thay đổi chính tác vụ mà pipeline được phép thực hiện.

**Digest có chứng minh artifact an toàn không?**

Không. Digest định danh nội dung. Còn cần đánh giá nguồn, bằng chứng build, các kiểm tra và quyết định phát hành theo chính sách.

**Credential ngắn hạn có làm quyền triển khai trở nên tối thiểu không?**

Không. Thời hạn và phạm vi là hai chiều khác nhau. Credential ngắn hạn vẫn có thể có quyền rất rộng.

**Tại sao phải kiểm soát runtime identity khi cấp quyền deploy?**

Vì mã được triển khai sẽ sử dụng năng lực của danh tính runtime. Cho phép chọn danh tính mạnh hơn có thể tạo một đường nâng quyền.

**Bỏ quyền người dùng có đủ để dừng job đang chạy không?**

Không thể mặc định. Job có thể đã nhận credential hoặc gửi thao tác tới đích. Cần cơ chế xử lý riêng và kiểm thử theo kiến trúc thực tế.

**Bằng chứng nào giúp xác nhận triển khai đúng?**

Bằng chứng cần liên kết yêu cầu và phê duyệt với artifact, cấu hình, đích, danh tính thực thi và trạng thái thực tế sau triển khai.

**Quyền rollback có cần được kiểm soát như deploy không?**

Có. Rollback cũng thay đổi mã hoặc cấu hình đang chạy và có thể ảnh hưởng quyền, dữ liệu cùng tính sẵn sàng.
