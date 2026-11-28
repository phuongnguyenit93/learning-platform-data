# PAM cho runner

## 1. Runner là điểm thực thi có thể chạm tới đặc quyền

Runner là máy, máy ảo, container hoặc môi trường thực thi nhận job từ hệ thống CI/CD. Nó checkout mã nguồn, chạy kiểm thử, đóng gói artifact và đôi khi triển khai lên môi trường vận hành. Khi một job có thể lấy credential triển khai, gọi API quản trị hay chạy lệnh trên hạ tầng nhạy cảm, runner trở thành một phần của đường truy cập đặc quyền.

Trong PAM, câu hỏi cần trả lời không chỉ là “secret nằm ở đâu”. Cần xác định **job nào được làm hành động gì, trên tài nguyên nào, trong khoảng thời gian nào, dựa vào bằng chứng nào và ai chịu trách nhiệm**. Runner phải thực thi các giới hạn đó ngay cả khi một script trong repository bị sửa hoặc một dependency thực thi mã ngoài dự kiến.

Ví dụ, runner biên dịch ứng dụng thanh toán chỉ cần đọc mã nguồn và ghi artifact vào một vùng staging. Runner triển khai production có thể được phép cập nhật đúng một dịch vụ bằng artifact đã duyệt. Không có lý do để hai công việc này cùng dùng một tài khoản quản trị có quyền trên toàn bộ cluster.

Sau bài này, người học có thể:

- Phân biệt danh tính của người kích hoạt, runner, job và tài khoản đích.
- Thiết kế quyền JIT theo job và phạm vi thao tác theo nguyên tắc least privilege.
- Chọn mức cô lập phù hợp với mức độ tin cậy của mã nguồn.
- Quản lý vòng đời credential, phiên truy cập và bằng chứng thực thi.
- Xây dựng phương án xử lý khi runner bị nghi xâm nhập hoặc job bị hủy giữa chừng.

Các chính sách và cấu hình trong bài là ví dụ thiết kế độc lập với nhà cung cấp. Khi triển khai, cần ánh xạ chúng sang khả năng thực tế của nền tảng CI, hệ thống PAM và hệ thống đích.

## 2. Tách bốn loại danh tính trước khi cấp quyền

Một job thường liên quan đến nhiều chủ thể. Gộp tất cả thành một tài khoản như “ci-admin” làm mất khả năng giới hạn quyền và truy vết.

| Danh tính | Đại diện cho điều gì? | Quyền nên có | Điều không nên suy ra |
| --- | --- | --- | --- |
| Người kích hoạt hoặc phê duyệt | Cá nhân tạo thay đổi, bấm chạy hoặc duyệt triển khai | Kích hoạt workflow, duyệt môi trường theo vai trò | Người được bấm chạy không mặc nhiên được cấp shell production |
| Runner manager hoặc autoscaler | Thành phần tạo runner, đăng ký và điều phối năng lực thực thi | Tạo/hủy runner trong phạm vi được giao | Không nên truyền credential quản lý runner xuống job |
| Runner host | Máy hoặc môi trường thực thi một hay nhiều job | Quyền vận hành tối thiểu của host | Host thuộc mạng nội bộ không đủ để tin mọi mã chạy trên đó |
| Job/workload | Một lần thực thi cụ thể của workflow | Quyền ngắn hạn gắn với repository, workflow và môi trường | Tên job hoặc nhãn runner do người dùng chọn không phải bằng chứng danh tính |
| Principal trên hệ thống đích | Tài khoản, role hoặc phiên mà PAM cấp để thực hiện thao tác | Chỉ thao tác cần thiết lên đúng tài nguyên | Một credential ngắn hạn vẫn có thể nguy hiểm nếu role quá rộng |

Một bản ghi truy cập cần nối được chuỗi:

**Người yêu cầu → thay đổi mã nguồn → workflow/job → runner instance → quyết định PAM → principal đích → thao tác thực tế.**

Không phải workflow nào cũng có người bấm chạy trực tiếp. Với lịch chạy hoặc sự kiện máy, cần lưu loại trigger, danh tính dịch vụ điều phối và chủ sở hữu nghiệp vụ. Không gán tùy tiện mọi hành động tự động cho người viết commit cuối cùng.

### 2.1. Đăng ký runner và lấy quyền triển khai là hai việc riêng

Credential dùng để đăng ký runner với hệ thống CI chỉ phục vụ vòng đời runner. Nó không được trở thành credential triển khai production. Ngược lại, job có quyền triển khai cũng không nên được sửa cấu hình pool, đăng ký runner mới hoặc lấy token quản lý toàn tổ chức.

Nếu job chiếm được quyền quản lý runner, kẻ tấn công có thể tạo điểm thực thi giả, nhận các job khác hoặc duy trì quyền ngoài vòng đời của job ban đầu. Vì vậy, quyền của runner manager là một tài sản đặc quyền riêng, cần được kiểm kê và kiểm soát.

### 2.2. Danh tính máy không thay thế danh tính job

Một runner có workload identity của host không có nghĩa mọi job trên host được dùng toàn bộ quyền ấy. Nếu bất kỳ script nào cũng gọi được metadata endpoint hoặc lấy token của host, ranh giới quyền giữa các job gần như bị bỏ qua.

Thiết kế cần trả lời: script chạy trong job có thể lấy những danh tính nào ngoài credential được cấp riêng cho job? Phải xem cả danh tính cloud, service account gắn vào pod, credential agent, socket và tệp cấu hình có sẵn trên host.

## 3. Mô hình đe dọa cho runner

Runner thực thi mã có khả năng thay đổi thường xuyên. Các nguồn mã gồm repository chính, pull request, script build, plugin, action, dependency và image build. Việc một job được hệ thống CI điều phối không làm cho toàn bộ những nguồn mã này đáng tin cậy.

| Điểm xâm nhập | Hậu quả có thể xảy ra | Kiểm soát chính |
| --- | --- | --- |
| Pull request từ nguồn chưa tin cậy | Đọc secret được đưa vào job hoặc gọi API lấy token | Chạy ở pool không đặc quyền; không cấp production identity |
| Workflow hoặc script triển khai bị sửa | Dùng quyền hợp lệ để thực hiện thao tác ngoài ý định | Bảo vệ thay đổi workflow; ràng buộc đúng phiên bản, approval và phạm vi đích |
| Dependency hay công cụ build độc hại | Chạy mã trong tiến trình có credential | Giảm quyền job build; tách bước cấp quyền triển khai; kiểm soát nguồn dependency |
| Runner dùng lại giữa các job | Đọc credential, tiến trình hoặc workspace còn sót | Cô lập theo job; hủy môi trường; kiểm tra cleanup và tiến trình nền |
| Quyền quản trị host hoặc container quá rộng | Thoát khỏi phạm vi job, truy cập host hoặc job khác | Hạn chế quyền host, mount, socket và môi trường dùng chung |
| Artifact hoặc cache bị đầu độc | Job production thực thi mã đã bị thay thế | Bảo vệ nguồn gốc artifact, digest, cache và đường thăng cấp |
| Credential bị ghi ra log | Người đọc log hoặc artifact sử dụng được quyền | Không log bí mật; giảm thời hạn; giới hạn quyền; kiểm soát quyền đọc bằng chứng |
| Runner manager bị chiếm | Tạo runner giả hoặc điều phối job sai nơi | Tách quản trị, giới hạn đăng ký, giám sát thay đổi pool và template |

### 3.1. Ranh giới tin cậy đi theo mã được thực thi

Một workflow “tin cậy” nhưng checkout rồi chạy script từ một nhánh chưa tin cậy vẫn thực thi mã chưa tin cậy. Chỉ bảo vệ tệp workflow mà bỏ qua script gọi từ tệp đó sẽ để lại đường lấy quyền.

Tương tự, không được để job đặc quyền tải artifact tùy ý do một job không tin cậy tạo ra rồi thực thi artifact ấy như công cụ triển khai. Kiểm tra digest chỉ chứng minh các byte không đổi so với digest tham chiếu; còn phải chứng minh digest tham chiếu thuộc đúng nguồn và quy trình được phép.

### 3.2. Ephemeral giảm tồn lưu, không ngăn lạm dụng trong lúc chạy

Runner ephemeral được tạo cho một job rồi hủy có thể giảm nguy cơ lây nhiễm sang job kế tiếp. Tuy nhiên, mã độc vẫn có thể sử dụng hoặc đánh cắp credential ngay trong thời gian job đang chạy.

Do đó, ephemeral cần đi cùng quyền tối thiểu, phân tách mạng, kiểm soát nguồn workflow và giới hạn credential. Không coi việc “hủy máy sau job” là bằng chứng rằng quyền production đã được thu hồi.

## 4. Thiết kế runner pool theo mức độ tin cậy

Một pool dùng chung cho kiểm thử pull request, build release và triển khai production thường khiến quyền phải mở rộng đến mức công việc nhạy cảm nhất. Nên thiết kế các miền thực thi theo ranh giới tin cậy và loại thao tác.

| Pool | Nguồn công việc | Quyền đích | Đặc điểm vận hành |
| --- | --- | --- | --- |
| Kiểm thử mã chưa tin cậy | Pull request, nhánh thử nghiệm | Không có quyền vào hệ thống nhạy cảm | Không nhận production secret; hạn chế đường vào mạng nội bộ |
| Build tin cậy | Mã đã qua điều kiện kiểm soát | Ghi đúng repository artifact hoặc vùng staging | Không có quyền triển khai production |
| Triển khai staging | Artifact từ luồng build hợp lệ | Cập nhật đúng dịch vụ staging | Danh tính, secret và mạng tách production |
| Triển khai production | Workflow được bảo vệ, artifact được duyệt | Thao tác triển khai hẹp trên dịch vụ production | Approval theo chính sách, credential theo job, bằng chứng đầy đủ |
| Bảo trì đặc biệt | Nhiệm vụ quản trị có kế hoạch hoặc khẩn cấp | Quyền bổ sung được phê duyệt riêng | Job riêng, thời hạn riêng, giám sát và review sau thực thi |

Nhãn như “production-runner” chỉ có ý nghĩa định tuyến khi nền tảng CI thực sự giới hạn ai được dùng pool đó. Nếu mọi repository đều tự gắn nhãn để chạy vào pool production, nhãn không tạo được ranh giới bảo mật.

### 4.1. Chọn đơn vị cô lập

Có thể cô lập bằng máy ảo theo job, container theo job hoặc cơ chế sandbox khác. Mức phù hợp phụ thuộc vào mã được thực thi, đặc quyền cần thiết và rủi ro chia sẻ kernel/host.

- Máy ảo theo job tạo một ranh giới khác với các container cùng host, nhưng template và quyền quản lý máy ảo vẫn phải được bảo vệ.
- Container thông thường không đồng nghĩa với một máy độc lập. Mount socket quản lý container, thư mục host hoặc thiết bị nhạy cảm có thể trao quyền ngoài container.
- Chạy không phải root giúp giảm một số quyền, nhưng không khắc phục credential có sẵn, API quản trị mở rộng hay socket cho phép điều khiển host.
- Nếu buộc phải build theo cách cần đặc quyền cao, cần pool build chuyên biệt và đánh giá cơ chế build cách ly. Không mang toàn bộ quyền đó sang job triển khai.

Với runner lâu sống vì lý do hiệu năng, cần nêu rõ giới hạn của cleanup. Xóa workspace không đảm bảo đã loại bỏ tiến trình nền, thay đổi hệ điều hành hay credential lưu ngoài workspace. Sau nghi ngờ xâm nhập, tái tạo host từ nguồn tin cậy đáng tin hơn việc chỉ chạy script dọn tệp.

### 4.2. Tách đường quản lý và đường thực thi

Runner manager cần giao tiếp với CI và nền tảng hạ tầng để tạo/hủy runner. Job cần giao tiếp với những dịch vụ phục vụ công việc. Hai luồng không nên tự động dùng chung credential hoặc quyền quản trị.

Quyền sửa runner image, startup script, network policy và mapping pool cũng là quyền có thể ảnh hưởng đến nhiều lần cấp quyền sau này. Người sửa template không nên tự động được bỏ qua quy trình kiểm soát thay đổi của template đó.

## 5. Cấp quyền JIT bằng danh tính workload

JIT, tức cấp quyền đúng lúc, giúp runner chỉ nhận quyền khi bước công việc thực sự cần. Nếu nền tảng hỗ trợ danh tính workload và hệ thống đích chấp nhận liên kết danh tính, có thể tránh lưu một mật khẩu triển khai dùng lâu dài trên runner.

Một luồng điển hình:

1. Nền tảng CI xác thực job và cung cấp assertion hoặc token danh tính thời hạn ngắn cho job đủ điều kiện.
2. Job gửi bằng chứng danh tính đến broker/PAM.
3. Broker xác minh bằng chứng và đánh giá chính sách cấp quyền.
4. Broker tạo một credential động, phiên truy cập hoặc quyền tạm thời được giới hạn.
5. Job thực hiện thao tác và các hệ thống ghi lại audit.
6. Khi job kết thúc, bị hủy hoặc vượt thời hạn, cơ chế bên ngoài runner thực hiện thu hồi và xác minh kết quả.

Token danh tính của CI, token truy cập PAM và credential đích có thể là ba đối tượng khác nhau, với audience, quyền, thời hạn và cơ chế thu hồi khác nhau. Thu hồi một đối tượng không tự động chứng minh hai đối tượng còn lại đã mất hiệu lực.

### 5.1. Xác minh bằng chứng trước khi đọc các claim để quyết định

Broker cần xác minh chữ ký bằng khóa của issuer được tin cậy, issuer, audience, thời hạn và các điều kiện hợp lệ của token. Việc giải mã payload để thấy tên repository không tương đương với xác thực token.

Sau đó mới dùng các claim có ngữ nghĩa đã biết để kiểm tra:

- Tổ chức hoặc tenant và định danh repository chính xác.
- Workflow nào được phép xin quyền và phiên bản hoặc nguồn workflow được tin cậy.
- Loại trigger: release, lịch chạy, push hay pull request.
- Nhánh, tag hoặc môi trường có thỏa chính sách bảo vệ hay không.
- Run, job và lần chạy lại nào đang xin quyền.
- Trạng thái phê duyệt nếu thao tác yêu cầu approval.
- Pool hoặc môi trường thực thi có thuộc miền tin cậy cần thiết hay không.

Không phải nền tảng nào cũng phát hành đủ những claim này trong token. Điều kiện nào không có bằng chứng đáng tin thì cần kiểm tra qua API CI đã xác thực hoặc nguồn chính sách bên ngoài. Không thay điều kiện thiếu bằng một biến môi trường do script tự khai báo.

Định danh bất biến của repository hoặc workflow, nếu được hỗ trợ, giúp tránh một số nhầm lẫn do đổi tên. Cần hiểu chính xác ngữ nghĩa claim của nền tảng đang dùng; không tự giả định tên hiển thị là bất biến.

### 5.2. Ràng buộc approval với đúng thay đổi

Một approval triển khai nên gắn với đúng môi trường, artifact hoặc digest, workflow/run và phiên bản mã có ý nghĩa trong quy trình. Nếu artifact đổi sau approval, hệ thống cần đánh giá lại điều kiện thay vì dùng lại approval cũ.

Đối với thao tác rủi ro cao, có thể yêu cầu người duyệt độc lập theo vai trò. Người yêu cầu quyền không được sửa chính sách để tự miễn điều kiện duyệt.

Chạy lại job cũng là một lần thực thi cần theo dõi. Chính sách phải quy định approval có còn hợp lệ hay cần duyệt lại; credential mới không nên âm thầm kế thừa mọi điều kiện của lần chạy cũ.

### 5.3. Ví dụ chính sách độc lập với sản phẩm

Đây là mô hình mô tả quyết định, không phải cú pháp cấu hình của một hệ thống PAM cụ thể:

~~~yaml
policy_id: payments-prod-deploy
trusted_identity:
  issuer: "<CI_ISSUER_DA_XAC_MINH>"
  audience: pam-deployment-broker
request_conditions:
  repository_id: repo-payments-017
  workflow_identity: payments-release-approved
  event_type: approved-release
  execution_pool: trusted-production-deploy
  environment: production
  approval:
    bound_to: [run_id, artifact_digest, environment]
    required: true
grant:
  target_role: payments-deployer
  resource_scope: production/payments-api
  allowed_operation: deploy-approved-artifact
  maximum_duration_seconds: 600
  renewable: false
audit:
  required_context:
    - run_id
    - job_id
    - attempt_id
    - runner_instance_id
    - artifact_digest
    - approval_id
    - policy_version
~~~

Các tên trường trên thể hiện yêu cầu thiết kế. Broker phải lấy dữ liệu từ claim đã xác minh hoặc nguồn đáng tin; không tin trực tiếp một yêu cầu YAML do runner gửi.

Role “payments-deployer” trên hệ thống đích cũng phải được giới hạn tương ứng. Chính sách broker ghi “chỉ payments-api” nhưng credential thực tế là cluster administrator thì giới hạn chỉ tồn tại trên giấy.

## 6. Giới hạn quyền trên đích: JIT cần đi cùng JEA

JIT trả lời khi nào runner có quyền. JEA, trong nghĩa chỉ cho phép các thao tác cần thiết, trả lời runner làm được gì sau khi đã được cấp quyền. Có thể thực hiện ý tưởng này bằng role IAM, API triển khai chuyên dụng, cơ chế chạy lệnh giới hạn hoặc endpoint quản trị được thiết kế hẹp; không nhất thiết dùng một công nghệ cụ thể.

Một job triển khai có thể chỉ cần:

- Đọc trạng thái của một dịch vụ.
- Cập nhật dịch vụ đó sang artifact đã được phê duyệt.
- Theo dõi rollout.
- Khôi phục về một phiên bản được cho phép nếu điều kiện rollback thỏa mãn.

Nó thường không cần tạo tài khoản quản trị, sửa chính sách IAM, đọc tất cả secret, mở shell tùy ý hay xóa namespace dùng chung.

### 6.1. Cẩn thận với thao tác có quyền gián tiếp

Một role chỉ được “cập nhật workload” vẫn có thể rất mạnh. Nếu người giữ role được thay image, command, volume, service account hoặc security context tùy ý, họ có thể tạo workload để đọc secret hoặc tiếp cận tài nguyên khác.

Vì vậy, ngoài việc giới hạn tên dịch vụ, cần kiểm soát những thuộc tính được thay đổi. Một dịch vụ triển khai trung gian có thể chỉ chấp nhận digest đã duyệt và một số tham số an toàn, thay vì nhận toàn bộ manifest do runner tự gửi.

Tương tự, danh sách cho phép một lệnh shell chưa chắc giới hạn được hành vi nếu đối số cho phép nạp script, đọc tệp tùy ý hoặc gọi chương trình khác. Với đặc quyền nhạy cảm, giao diện thao tác có cấu trúc thường dễ giới hạn và kiểm toán hơn shell tổng quát.

### 6.2. Không dùng tài khoản chung khi có thể cấp principal riêng

Principal hoặc phiên gắn với từng job giúp giới hạn thời gian, thu hồi và truy vết. Nếu hệ thống legacy buộc dùng tài khoản chung, cần giữ mapping phiên checkout credential với run/job, có cơ chế phối hợp truy cập, rotation và kiểm tra credential cũ.

Việc có một tài khoản riêng cho CI vẫn tốt hơn việc dùng tài khoản cá nhân của quản trị viên, nhưng chưa đủ nếu tài khoản đó tiếp tục có quyền toàn hệ thống và được hàng trăm job dùng chung.

## 7. Quản lý credential trong suốt vòng đời job

### 7.1. Chỉ lấy credential ở bước cần dùng

Job build không nên giữ credential production từ đầu pipeline để “chuẩn bị sẵn”. Chỉ lấy quyền sau khi đã xác minh artifact, điều kiện môi trường và approval. Khoảng thời gian credential tồn tại càng dài thì càng nhiều công đoạn có cơ hội sử dụng nó.

Tách một pipeline thành nhiều step không tự tạo ra cô lập. Nếu các step chạy trên cùng host và chia sẻ workspace hoặc tiến trình, mã độc ở step trước vẫn có thể chờ credential xuất hiện ở step sau. Việc tách job hoặc tách runner phải đi cùng ranh giới thực thi phù hợp.

### 7.2. Giảm chỗ lưu và số tiến trình nhìn thấy credential

Tùy công cụ, credential có thể được chuyển qua API client, agent, biến môi trường hoặc tệp tạm. Không có cách nào tự động an toàn trong mọi hoàn cảnh:

| Cách truyền | Rủi ro cần hiểu | Biện pháp thực tế |
| --- | --- | --- |
| Biến môi trường | Tiến trình con kế thừa; diagnostic hoặc crash dump có thể làm lộ | Giới hạn môi trường của tiến trình, tránh dump, hủy sau bước dùng |
| Tệp tạm | Bị đưa vào cache/artifact hoặc còn lại sau job | Quyền truy cập hẹp, vị trí tách workspace, không upload, có cleanup |
| Tham số dòng lệnh | Có thể lộ trong log lệnh hoặc thông tin tiến trình tùy hệ thống | Tránh đặt secret trực tiếp trong đối số nếu công cụ hỗ trợ cách khác |
| Agent/proxy | Có thể bị lợi dụng để thực hiện thao tác dù không lộ raw secret | Giới hạn kết nối, phiên, đích và khả năng gọi từ job |
| Bộ nhớ tiến trình | Mã chạy cùng quyền hoặc dump có thể tiếp cận | Giảm phạm vi tiến trình, cô lập và hạn chế khả năng debug |

Masking trên log là một lớp hỗ trợ. Nó không ngăn được mọi dạng biến đổi, chia nhỏ, mã hóa hoặc gửi bí mật qua mạng. Không tạo bản ghi credential để rồi dựa hoàn toàn vào masking để che.

Nếu công cụ hỗ trợ proxy truy cập đích mà không trả raw secret cho job, có thể giảm số nơi giữ secret. Tuy nhiên, job vẫn đang nắm khả năng sử dụng proxy trong phiên được cấp; khả năng ấy cũng phải được giới hạn và có audit.

### 7.3. Kiểm soát thời hạn và gia hạn

Thời hạn phải phù hợp với thao tác và giới hạn rủi ro, không đặt theo toàn bộ tuổi thọ runner. Ví dụ minh họa: một rollout thường mất vài phút có thể nhận phiên tối đa mười phút, với timeout job và cơ chế dừng độc lập.

Nếu công việc dài hơn thời hạn, cần chọn rõ một trong hai hướng:

- Chia thao tác thành những phần có điểm kiểm tra, xin quyền riêng khi cần.
- Cho phép gia hạn có điều kiện, kiểm tra job còn sống, approval còn hợp lệ và chưa vượt tổng thời gian tối đa.

Không gia hạn vô hạn chỉ vì một tiến trình còn gửi heartbeat. Job bị chiếm cũng có thể tiếp tục gửi heartbeat hợp lệ.

### 7.4. Xử lý hệ thống legacy chỉ chấp nhận secret tĩnh

Có thể lấy credential từ vault ngay trước khi dùng, kiểm soát checkout và rotate theo khả năng của đích. Cần xác minh quyền thực tế của tài khoản, số consumer dùng chung và việc credential có bị cache ở công cụ triển khai không.

Rotate sau mỗi job có thể gây gián đoạn nếu nhiều job cùng dùng một tài khoản. Cần thiết kế phối hợp hoặc tách principal, không để job cuối cùng vô hiệu hóa credential mà job khác đang sử dụng hợp lệ.

Nếu hệ thống đích không hỗ trợ quyền ngắn hạn hoặc thu hồi phiên tức thì, phải ghi nhận rõ giới hạn đó. Có thể giảm rủi ro bằng proxy, giới hạn mạng, khóa tài khoản hoặc rotate credential khi phù hợp, nhưng không gọi một secret tĩnh vừa lấy từ vault là credential động.

## 8. Cô lập mạng, cache và artifact

### 8.1. Giới hạn đường đi của runner

Runner production chỉ nên tiếp cận các endpoint cần thiết như CI, broker/PAM, kho artifact được tin cậy, dịch vụ triển khai và hệ thống log. Không nên có đường tới mọi cổng quản trị trong mạng nội bộ.

Cần xét cả kết nối ra ngoài và kết nối vào runner. Nếu job không cần nhận kết nối quản trị từ mạng chung, không nên mở sẵn SSH/RDP để tiện xử lý sự cố. Truy cập bảo trì host phải qua đường quản trị có kiểm soát riêng.

Với metadata endpoint, workload identity hoặc socket nội bộ, cần kiểm tra khả năng truy cập từ đúng môi trường job. Chặn Internet nhưng để job lấy được credential quản trị host vẫn không đạt mục tiêu PAM.

Giới hạn mạng giúp giảm đường tiếp cận và đường đưa dữ liệu ra ngoài; nó không thay thế phân quyền. Một endpoint được phép có thể vẫn cho phép hành động nguy hiểm nếu principal quá mạnh.

### 8.2. Cache không phải kho bí mật

Không đưa vào cache hay artifact các tệp như cấu hình CLI có token, khóa SSH, credential cloud, bản sao vault response hoặc thư mục home chứa thông tin đăng nhập.

Cache cần được phân vùng theo mức tin cậy. Job kiểm thử nguồn chưa tin cậy không nên được ghi vào cache mà job triển khai production tải về và thực thi. Với nội dung nhạy cảm, sử dụng nguồn artifact bất biến và metadata nguồn gốc được bảo vệ.

### 8.3. Thăng cấp cùng một artifact

Một luồng tốt là build một lần, xác định digest, kiểm tra rồi triển khai chính artifact ấy. Nếu production job build lại từ một tag có thể thay đổi, kết quả triển khai có thể khác thứ đã được duyệt.

Bằng chứng nguồn gốc cần nối artifact với workflow tạo ra nó, mã nguồn và điều kiện kiểm soát tương ứng. Chữ ký artifact chỉ có ý nghĩa khi hệ thống xác minh đúng signer được tin cậy và đúng chính sách phát hành.

## 9. Kết thúc job phải kéo theo kết thúc đặc quyền

Script cleanup bên trong runner hữu ích nhưng có thể không chạy khi host bị tắt, job bị kill hoặc kết nối mạng hỏng. Thu hồi quyền cần có bộ điều khiển ở ngoài runner và một thời hạn cuối được hệ thống đích thực thi.

Một vòng đời có thể mô tả bằng các trạng thái:

~~~text
YEU_CAU
  -> XAC_MINH_DANH_TINH
  -> KIEM_TRA_DIEU_KIEN_VA_APPROVAL
  -> CAP_QUYEN
  -> THUC_THI
  -> THU_HOI
  -> XAC_MINH_KET_THUC_QUYEN
  -> DONG_JOB

Mọi trạng thái đã CAP_QUYEN:
  khi cancel / timeout / mat-runner / nghi-xam-nhap
  -> DUONG_THU_HOI_DOC_LAP
~~~

Đây là mô hình trạng thái mong muốn; cần ánh xạ từng chuyển trạng thái sang sự kiện, API và trách nhiệm vận hành cụ thể.

### 9.1. Phân biệt thu hồi lease, credential và phiên

Thu hồi lease tại vault/PAM không luôn kết thúc ngay phiên đang tồn tại trên đích. Ví dụ, một kết nối được xác thực trước đó có thể tiếp tục hoạt động tùy hành vi của hệ thống. Tương tự, một token tự chứa có thể tiếp tục được đích chấp nhận đến hết hạn nếu không có cơ chế kiểm tra thu hồi.

Cần xác minh riêng:

1. Broker đã ngừng phát hoặc gia hạn quyền cho job.
2. Credential hoặc role tạm đã hết hiệu lực theo cơ chế thực tế của đích.
3. Các phiên, kết nối hoặc tác vụ đã tạo còn tiếp tục được hay không.
4. Tài nguyên mà job đã tạo có chứa một quyền tồn lưu mới hay không.

Không kết luận “đã an toàn” chỉ vì runner bị xóa hoặc endpoint revoke trả thành công. Kiểm tra phải phản ánh hành vi từ chối trên đích và trạng thái phiên, trong phạm vi vận hành được phép.

### 9.2. Cleanup có thể chạy lặp lại

Bộ điều khiển có thể nhận sự kiện kết thúc nhiều lần hoặc retry sau lỗi mạng. Thao tác thu hồi nên được thiết kế chạy lặp lại an toàn, dùng định danh phiên/job rõ ràng và không ảnh hưởng các job khác.

Nếu thu hồi thất bại, ghi trạng thái cần xử lý, cảnh báo và retry có giới hạn theo chính sách. Không đánh dấu job đóng hoàn toàn chỉ vì phần triển khai đã thành công.

### 9.3. Khi PAM hoặc đường audit không sẵn sàng

Với cấp quyền nhạy cảm mới, nên từ chối cấp nếu không xác minh được điều kiện bắt buộc. Không tự chuyển sang một mật khẩu quản trị tĩnh chỉ vì broker đang lỗi.

Phiên đang tồn tại cần hành xử theo chính sách đã xác định: tiếp tục đến thời hạn ngắn đã cấp, dừng thao tác mới hoặc bị đóng qua bộ điều khiển độc lập. Cần biết trước hành vi này, nhất là với triển khai đang giữa chừng.

Nếu yêu cầu audit bắt buộc mà không thể ghi nhận, có thể từ chối cấp quyền mới hoặc dùng cơ chế đệm bền vững đã được phê duyệt. Không để runner tự quyết định bỏ audit rồi báo triển khai thành công.

## 10. Ví dụ: triển khai payments-api lên production

### 10.1. Bối cảnh và phân quyền

Nhóm Payments có ứng dụng payments-api. Pipeline nhận thay đổi đã qua review, build artifact, kiểm thử ở staging rồi yêu cầu triển khai production.

Thiết kế chia thành ba miền:

- Build runner đọc mã nguồn, chạy kiểm thử và ghi artifact vào đúng vùng build.
- Staging runner dùng principal staging để triển khai artifact đủ điều kiện.
- Production runner chỉ nhận quyền triển khai payments-api sau khi kiểm tra approval và nguồn gốc artifact.

Credential quản lý runner pool do thành phần điều phối giữ. Credential production không tồn tại trong image runner và không được dùng ở bước build.

### 10.2. Luồng thực thi minh họa

Đoạn dưới là mã giả mô tả trách nhiệm của các thành phần, không phải SDK hoặc workflow có thể chạy trực tiếp:

~~~text
on_production_deployment_request(request):
    verified_job = ci.verify_workload_identity(request.identity_assertion)
    context = ci.fetch_trusted_run_context(verified_job.run_id)

    require context.repository_id == "repo-payments-017"
    require context.workflow_is_trusted
    require context.execution_pool == "trusted-production-deploy"
    require context.environment == "production"
    require context.job_is_active

    artifact = registry.resolve_verified_artifact(request.artifact_digest)
    approval = approvals.find_valid_approval(
        run_id=context.run_id,
        artifact_digest=artifact.digest,
        environment="production"
    )
    require approval.satisfies_policy

    grant = pam.issue_job_scoped_grant(
        principal_scope="production/payments-api",
        operation="deploy-approved-artifact",
        maximum_duration_seconds=600,
        artifact_digest=artifact.digest,
        job_id=context.job_id,
        attempt_id=context.attempt_id
    )

    audit.record_grant(context, artifact.digest, approval.id, grant.id)
    deployment_service.deploy_with_grant(grant, artifact.digest)

external_job_lifecycle_controller.on_terminal_event(job_id, attempt_id):
    grants = pam.find_grants(job_id, attempt_id)
    for grant in grants:
        pam.revoke(grant.id)
        target.verify_grant_no_longer_authorizes(grant)
        target.check_remaining_sessions_and_operations(grant)
    audit.record_cleanup_result(job_id, attempt_id)
~~~

Dịch vụ triển khai phải thực thi giới hạn artifact và phạm vi tài nguyên; không chỉ kiểm tra ở runner. Broker cũng cần xử lý trường hợp hủy job trong lúc đang cấp quyền bằng việc kiểm tra trạng thái, phối hợp trạng thái grant và thu hồi độc lập.

Lệnh triển khai có thể đã được đích chấp nhận trước thời điểm thu hồi. Thu hồi không tự hoàn tác thay đổi đã xảy ra. Vì vậy, ngoài kiểm soát quyền còn cần chính sách rollout, rollback và kiểm tra trạng thái dịch vụ.

### 10.3. Những tình huống phải bị chặn

| Yêu cầu | Kết quả mong muốn | Lý do |
| --- | --- | --- |
| Pull request xin role production | Từ chối cấp | Nguồn thực thi không thuộc luồng production |
| Job staging đổi biến môi trường thành production | Từ chối cấp | Biến của job không thay được ngữ cảnh CI đã xác minh |
| Đúng repository nhưng sai workflow | Từ chối cấp | Repository identity chưa đủ để cho phép đặc quyền |
| Approval cho digest A nhưng triển khai digest B | Từ chối cấp hoặc yêu cầu duyệt lại | Approval không còn gắn với artifact thực thi |
| Credential payments-api được dùng để sửa dịch vụ khác | Đích từ chối | Scope phải được thực thi tại đích |
| Job đã bị hủy tiếp tục xin gia hạn | Từ chối và thu hồi quyền còn lại | Điều kiện job còn hoạt động không thỏa |
| Job hợp lệ xin đọc toàn bộ secret production | Đích và chính sách từ chối | Đây không phải thao tác cần cho triển khai |
| Runner tự gửi tên pool production giả | Từ chối hoặc không sử dụng giá trị tự khai | Pool phải được xác minh từ nguồn đáng tin |

## 11. Audit và ứng phó khi runner bị nghi xâm nhập

### 11.1. Bằng chứng đủ để dựng lại hành động

Log build cho biết một số lệnh đã chạy, nhưng không thay thế audit từ broker và hệ thống đích. Một bản ghi cấp quyền nên có:

- Repository/workflow định danh rõ ràng; commit hoặc revision liên quan.
- Run ID, job ID, lần chạy lại và runner instance ID.
- Artifact digest và môi trường đích.
- Người hoặc dịch vụ yêu cầu; người duyệt và approval ID nếu có.
- Policy ID, phiên bản chính sách và kết quả đánh giá.
- Grant/lease/session ID, principal đích, scope và thời hạn.
- Thời điểm cấp, sử dụng, gia hạn, thu hồi và xác minh kết thúc quyền.
- Kết quả thao tác trên đích và trạng thái cleanup.

Không đưa raw token, mật khẩu, private key hoặc payload nhạy cảm vào bằng chứng. Correlation ID giúp nối log mà không cần lưu bí mật.

Dùng thời gian thống nhất và kiểm soát đồng hồ giữa các hệ thống để có thể dựng lại thứ tự sự kiện. Nên chuyển audit ra khỏi runner sớm; khi host bị hủy hoặc bị chiếm, log chỉ nằm trên host có thể mất hoặc bị sửa.

### 11.2. Tín hiệu cần theo dõi

Các tín hiệu có giá trị gồm job không đủ điều kiện liên tục xin production role, yêu cầu gia hạn bất thường, truy cập đích ngoài scope, thay đổi runner template, credential sử dụng sau khi job kết thúc và cleanup thất bại.

Cần phân biệt cảnh báo sai cấu hình với dấu hiệu lạm dụng, nhưng không tự động mở rộng role chỉ để làm im các lỗi từ chối. Mỗi thay đổi quyền cần có nhu cầu nghiệp vụ và kiểm tra phạm vi rõ ràng.

### 11.3. Quy trình xử lý sự cố

Khi nghi runner bị xâm nhập:

1. Ngừng nhận job mới trên instance/pool bị ảnh hưởng và cô lập đường truy cập phù hợp.
2. Chặn cấp hoặc gia hạn grant liên quan, thu hồi quyền còn hiệu lực trên các hệ thống đích.
3. Kiểm tra phiên đang mở, thao tác đang chạy và tài nguyên có quyền tồn lưu được job tạo ra.
4. Bảo toàn bằng chứng cần thiết theo quy trình, đồng thời tránh để host tiếp tục gây hại.
5. Xác định credential nào đã được đưa vào job hoặc có thể bị lấy từ host, cache, log và artifact.
6. Rotate hoặc thay thế credential còn nguy cơ theo phạm vi ảnh hưởng đã xác định.
7. Tái tạo runner từ nguồn tin cậy; kiểm tra image, workflow, dependency và cấu hình điều phối.
8. Khôi phục pool có kiểm soát sau khi nguyên nhân và điều kiện cấp quyền đã được xử lý.

Không chỉ đổi mật khẩu một tài khoản rồi đưa lại host cũ vào pool nếu chưa hiểu đường xâm nhập. Với runner production, phạm vi điều tra có thể bao gồm thay đổi mà credential đã thực hiện trên đích, chứ không dừng ở bản thân runner.

Quyền khẩn cấp để xử lý sự cố cũng phải có danh tính riêng, phạm vi, thời hạn và bằng chứng. Không nên giữ sẵn một khóa quản trị không hết hạn trong mọi runner để phòng khi có sự cố.

## 12. Thực hành thiết kế và tiêu chí nghiệm thu

### 12.1. Bài tập

Giả sử một đội đang dùng một runner lâu sống để build, test và deploy. Runner lưu credential có quyền quản trị cluster trong thư mục home. Các pull request đều có thể chạy trên runner này; credential được che bởi tính năng mask log.

Hãy thiết kế lại luồng với yêu cầu:

- Pull request vẫn chạy kiểm thử được nhưng không có đường lấy đặc quyền production.
- Chỉ workflow phát hành được bảo vệ mới xin quyền triển khai.
- Quyền triển khai gắn với một artifact và một dịch vụ.
- Hủy job phải dẫn đến thu hồi quyền bằng cơ chế ngoài runner.
- Có bằng chứng nối người duyệt, artifact, job và thao tác trên đích.

Một hướng giải quyết là tạo pool kiểm thử riêng không có production identity; tách build khỏi deploy; dùng runner production được tạo theo job; đưa credential ra khỏi image/home; sử dụng danh tính workload để broker cấp quyền JIT; áp dụng role triển khai hẹp và ghi audit ngoài runner.

Thiết kế chỉ được coi là đáp ứng khi hệ thống đích thực sự thực thi scope và quy trình thu hồi có bằng chứng. Việc đổi tên tài khoản “admin” thành “ci-deployer” không làm thay đổi quyền của nó.

### 12.2. Các kiểm tra trong môi trường thử nghiệm

| Kiểm tra | Bằng chứng cần quan sát |
| --- | --- |
| Job chưa tin cậy gọi broker | Yêu cầu bị từ chối, có lý do và correlation ID |
| Token có audience hoặc issuer sai | Bị từ chối trước khi cấp quyền |
| Job hợp lệ triển khai đúng artifact | Được cấp đúng principal/scope và ghi nhận thao tác thành công |
| Job hợp lệ thử sửa tài nguyên ngoài scope | Bị đích từ chối |
| Artifact thay sau approval | Approval cũ không cho phép triển khai artifact mới |
| Job bị hủy hoặc runner mất kết nối | Bộ điều khiển ngoài runner xử lý; quyền kết thúc theo chính sách |
| Credential đã hết hạn được dùng lại | Đích từ chối; phiên cũ được kiểm tra theo cơ chế riêng |
| Cleanup được gửi lặp lại | Không ảnh hưởng grant của job khác |
| Thu hồi hoặc đích tạm thời lỗi | Có cảnh báo và trạng thái chưa đóng; không báo cleanup thành công |
| Kiểm tra workspace, cache và artifact sau job | Không chứa credential đã cấp cho job |

Các thử nghiệm dùng tài nguyên giả lập hoặc sandbox được phép. Không cần đưa secret production thật vào bài kiểm tra.

### 12.3. Các nguyên tắc cần giữ

Runner là nơi mã được thực thi, nên quyền của nó phải đi theo mức tin cậy của mã và nhu cầu của từng job. Tách runner manager, host identity và job identity giúp tránh một tài khoản trở thành đường vượt mọi giới hạn.

PAM cho runner cần kết hợp JIT với phạm vi thao tác hẹp, ranh giới thực thi, bảo vệ artifact và thu hồi ngoài runner. Ephemeral, vault và masking đều hữu ích trong đúng vai trò của chúng; không thành phần nào tự mình bảo đảm toàn bộ vòng đời truy cập đặc quyền.

Khi nhìn vào một lần triển khai, đội vận hành phải chứng minh được vì sao quyền đã được cấp, quyền thực tế là gì, nó đã được dùng ra sao và khi nào quyền ấy kết thúc.
