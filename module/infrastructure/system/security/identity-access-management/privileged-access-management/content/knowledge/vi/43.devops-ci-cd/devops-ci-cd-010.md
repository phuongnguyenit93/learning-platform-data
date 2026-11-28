# Không lưu admin key trong CI variable

## 1. Mục tiêu của bài học

Một pipeline có thể tự động xây dựng, kiểm thử và triển khai ứng dụng mà không phải giữ khóa quản trị thường trực. Thiết kế đúng bắt đầu từ câu hỏi: **job này cần được làm thao tác gì, trên tài nguyên nào, trong bao lâu và dựa vào bằng chứng danh tính nào?**

Trong phạm vi quản lý truy cập đặc quyền (PAM), CI/CD phải được xem là một workload có thể nắm quyền nhạy cảm. Runner thực thi mã, tải dependency, gọi API hạ tầng và đôi khi truy cập production. Khi pipeline giữ khóa admin dài hạn, bất kỳ thành phần nào chiếm được ngữ cảnh thực thi của job đều có thể trở thành một đường đi tới quyền quản trị.

Sau bài học, người học có thể:

- Nhận diện khóa và token đặc quyền đang được cất trong kho biến của CI/CD.
- Phân biệt việc che giá trị bí mật với việc kiểm soát quyền sử dụng bí mật.
- Thiết kế đường cấp quyền ngắn hạn dựa trên danh tính workload.
- Tách build, phát hành artifact và deploy thành các miền quyền khác nhau.
- Chuyển đổi khỏi khóa tĩnh theo từng bước, có kiểm tra, bằng chứng và phương án dừng an toàn.
- Xử lý trường hợp hệ thống đích chưa hỗ trợ danh tính liên kết.

Bài học tập trung vào nguyên tắc và thiết kế độc lập với nhà cung cấp. Các tên role, policy và trường cấu hình minh họa cần được ánh xạ sang cơ chế thực tế của hệ thống triển khai.

## 2. “Admin key trong CI variable” là gì?

CI variable là giá trị được hệ thống CI cung cấp cho pipeline hoặc job. Tùy nền tảng, biến có thể được cấu hình tại cấp tổ chức, nhóm, dự án, môi trường hoặc riêng một lần chạy. Một số giá trị được đánh dấu là secret, masked hoặc protected.

Admin key là cách gọi chung cho credential có quyền quản trị hoặc có khả năng tạo ra quyền quản trị, chẳng hạn:

- Access key của tài khoản cloud có quyền gần như toàn bộ subscription, project hoặc account.
- Token API có thể tạo người dùng, thay đổi IAM, phát hành token hoặc cấp thêm role.
- SSH private key đăng nhập root hoặc tài khoản có quyền sudo rộng.
- Credential của cơ sở dữ liệu có thể quản trị user và đọc dữ liệu nhạy cảm trên diện rộng.
- Token quản trị cluster hoặc kubeconfig mang danh tính được gán quyền cao.
- Credential của vault có thể đọc hầu hết secret, thay đổi policy hoặc cấp credential mới.
- Token quản trị chính nền tảng CI/CD, có khả năng sửa biến và cấu hình bảo vệ môi trường.

Tên biến không quyết định mức độ rủi ro. Một biến tên là DEPLOY_TOKEN vẫn có thể chứa credential quản trị. Ngược lại, một biến tên là ADMIN_TOKEN có thể đã bị thu hẹp quyền. Phải kiểm tra **quyền hiệu lực và khả năng mở rộng quyền**, thay vì chỉ đọc nhãn.

Ví dụ cấu hình có vấn đề:

~~~yaml
# Minh họa một thiết kế cần thay thế, không phải cấu hình để sử dụng.
ci_variables:
  CLOUD_ADMIN_KEY: "<credential quản trị dùng lâu dài>"
  DATABASE_ADMIN_PASSWORD: "<mật khẩu quản trị production>"

deploy_job:
  receives:
    - CLOUD_ADMIN_KEY
    - DATABASE_ADMIN_PASSWORD
  actions:
    - build
    - run_tests
    - change_infrastructure
    - deploy_production
~~~

Thiết kế này gom quá nhiều quyền vào một nơi thực thi nhiều loại mã. Một dependency của bước build, một script kiểm thử hoặc một thay đổi pipeline có thể tiếp cận quyền vốn chỉ cần cho một phần nhỏ của bước deploy.

**Nguyên tắc cốt lõi:** không dùng kho CI variable làm nơi giữ credential quản trị thường trực để mọi lần chạy thuận tiện lấy ra.

## 3. Secret variable bảo vệ điều gì, và không bảo vệ điều gì?

Secret storage và log masking vẫn hữu ích. Chúng giảm khả năng lộ giá trị qua giao diện, cơ sở lưu trữ hoặc những đường log được nền tảng hỗ trợ. Tuy nhiên, chúng không biến mã đang chạy trong job thành mã đáng tin.

Cần phân biệt ba lớp kiểm soát:

| Lớp kiểm soát | Câu hỏi được giải quyết | Giới hạn cần nhớ |
|---|---|---|
| Lưu trữ secret | Ai có thể đọc hoặc sửa giá trị được cất giữ? | Credential vẫn phải được cung cấp cho một thành phần khi sử dụng |
| Che giá trị trong log | Đầu ra nào có thể làm lộ giá trị? | Không ngăn job dùng credential để gọi API trái phép |
| Phân quyền ở hệ thống đích | Credential cho phép làm gì, ở đâu, khi nào? | Chỉ hiệu quả khi policy, trust và vòng đời credential được thiết kế đúng |

Nếu một job được quyền nhận secret, mã thực thi trong job có thể dùng secret đó, kể cả khi giao diện không cho người dùng xem lại giá trị. Kẻ tấn công không nhất thiết phải lấy được bản sao credential; gọi API bằng chính runner cũng có thể gây hậu quả.

Các nhãn masked, protected và environment-scoped có ý nghĩa cụ thể khác nhau theo nền tảng. Không được suy ra rằng một nhãn tự động cung cấp cả xác thực nguồn chạy, phê duyệt production, chặn pull request không tin cậy và thu hồi phiên.

Mã hóa khi lưu trữ cũng không giải quyết được tình huống job hợp lệ bị chiếm quyền. Khi bí mật được giải mã để sử dụng, cơ chế lưu trữ đã hoàn thành nhiệm vụ của nó; vấn đề còn lại thuộc về quyền và độ tin cậy của ngữ cảnh thực thi.

## 4. Đường đi từ pipeline tới quyền quản trị

Một chuỗi rủi ro thường gặp có dạng:

~~~text
Mã hoặc cấu hình không đáng tin
            |
            v
Job chạy trên runner có thể nhận secret
            |
            v
Credential quản trị có hiệu lực
            |
            v
Thay đổi IAM / đọc secret / sửa hạ tầng / truy cập dữ liệu
            |
            v
Tạo đường truy cập khác tồn tại sau khi job kết thúc
~~~

Nguồn mã không đáng tin không chỉ là pull request từ bên ngoài. Nó có thể đến từ tài khoản lập trình viên bị chiếm, dependency, action hoặc plugin bên thứ ba, script tải ở thời điểm chạy, artifact bị thay thế hay runner dùng chung bị xâm nhập.

Một đường đi khác là sửa chính định nghĩa pipeline để xin quyền trong một job vốn được tin cậy. Vì vậy, bảo vệ nhánh ứng dụng nhưng để cấu hình workflow hoặc mẫu pipeline dùng chung thay đổi tự do vẫn có thể để hở đường cấp quyền.

Phạm vi ảnh hưởng không kết thúc ở tài nguyên được deploy. Nếu credential có thể sửa IAM, tạo key mới hoặc gán role cho danh tính khác, kẻ tấn công có thể tạo quyền tồn tại lâu hơn credential ban đầu. Đây là lý do PAM phải đánh giá cả **quyền trực tiếp** và **khả năng tạo quyền gián tiếp**.

## 5. Thiết kế đích: pipeline xin quyền cho từng công việc

Thiết kế đích tách danh tính của lần chạy khỏi credential dùng với tài nguyên đích:

~~~text
Job CI đủ điều kiện
    |
    | 1. Nhận bằng chứng danh tính ngắn hạn của workload
    v
Bên phát hành danh tính CI
    |
    | 2. Token có chữ ký và các claim về nguồn chạy
    v
Dịch vụ trao đổi danh tính / PAM broker / vault
    |
    | 3. Kiểm tra issuer, audience, nguồn chạy và policy
    | 4. Ánh xạ sang đúng role được phép
    v
Credential hoặc phiên truy cập ngắn hạn
    |
    | 5. Thực hiện thao tác trên phạm vi đã giới hạn
    v
API triển khai / tài nguyên đích
~~~

Bằng chứng danh tính có thể là token OIDC được nền tảng CI cấp cho job, hoặc một cơ chế danh tính workload tương đương. Dịch vụ đích có thể hỗ trợ federation trực tiếp; một số kiến trúc dùng broker hoặc vault làm trung gian.

Credential quản trị không được chuyển từ CI variable sang một vị trí khác rồi tiếp tục trả nguyên vẹn cho job. Mục tiêu là job nhận **quyền hẹp và ngắn hạn**, hoặc chỉ được yêu cầu một thao tác đã giới hạn mà không nhận credential quản trị phía sau.

Các thuộc tính mong muốn:

1. Không có admin key tĩnh trong ngữ cảnh job thông thường.
2. Danh tính có thể gắn với nguồn chạy và mục đích sử dụng.
3. Role được xác định bằng policy bên cấp quyền, không do job tự khai là admin.
4. Quyền hiệu lực chỉ đủ cho thao tác được phê duyệt.
5. Credential có thời hạn phù hợp với công việc.
6. Mỗi lần cấp quyền và sử dụng quyền để lại bằng chứng tương quan.
7. Có cách chặn cấp mới và xử lý phiên đã cấp khi phát hiện sự cố.

JIT áp dụng ở thời điểm cấp quyền: job chỉ nhận quyền khi đến bước cần dùng. JEA áp dụng ở phạm vi thực thi: ngay cả khi đã nhận quyền, job chỉ được thực hiện tập thao tác cần thiết.

## 6. Phân tách quyền giữa build, phát hành và deploy

Không nên dùng một danh tính chung cho toàn bộ pipeline. Các giai đoạn có mức độ tin cậy và nhu cầu quyền khác nhau.

| Giai đoạn | Nhu cầu hợp lý | Quyền thường không cần |
|---|---|---|
| Build và kiểm thử | Đọc mã, tải dependency qua nguồn được phép, ghi kết quả kiểm thử | Quản trị production, sửa IAM, đọc secret production |
| Phát hành artifact | Ghi vào đúng repository hoặc namespace artifact | Sửa tài nguyên production, quản trị registry toàn tổ chức |
| Deploy staging | Cập nhật ứng dụng staging thuộc phạm vi được cấp | Truy cập production, cấp role cho chính mình |
| Deploy production | Triển khai artifact đã chốt vào đúng ứng dụng production | Tạo admin mới, sửa trust policy, đọc mọi secret |
| Migration dữ liệu | Thực hiện tập thay đổi được duyệt trên đúng database | Quản trị user hoặc database khác nếu không có nhu cầu |
| Bootstrap quyền | Tạo hoặc thay đổi cấu hình cấp quyền theo quy trình riêng | Trở thành quyền mặc định của mọi lần deploy |

Một pipeline deploy ứng dụng không mặc nhiên cần quyền quản trị toàn bộ nền tảng. Nếu thao tác triển khai hiện tại đòi admin, cần xác định cụ thể API nào gây yêu cầu đó. Có thể phải tách phần bootstrap hoặc thay đổi IAM ra khỏi deploy thông thường.

Quyền “tạo mọi resource” cũng có thể nguy hiểm nếu cho phép tạo workload mang danh tính đặc quyền, gắn role cho tài nguyên mới hoặc truy cập dữ liệu của môi trường khác. Thu hẹp tên tài nguyên chưa đủ nếu job có thể gắn một execution role có quyền quá rộng.

### Ví dụ với một dịch vụ Java

Một dịch vụ thanh toán được đóng gói thành container. Pipeline có thể tách thành:

- Job build chạy kiểm thử và tạo image, không có danh tính production.
- Job publish chỉ được đẩy image vào kho artifact của dịch vụ thanh toán.
- Job deploy staging chỉ cập nhật workload staging của dịch vụ đó.
- Job deploy production chỉ cập nhật workload production từ digest image đã được duyệt.
- Job migration, nếu cần, dùng danh tính riêng với quyền trên đúng schema và chạy trong khoảng thời gian đã định.

Không có lý do để job kiểm thử Java giữ mật khẩu quản trị database production chỉ vì cùng nằm trong một pipeline.

## 7. Ràng buộc trust: xác thực đúng job, không chỉ đúng nhà cung cấp

Loại bỏ khóa tĩnh nhưng chấp nhận mọi token đến từ nền tảng CI có thể biến một rủi ro thành rủi ro khác. Bên nhận token phải xác thực token và quyết định rõ workload nào được phép đổi lấy quyền.

Các nội dung cần kiểm tra gồm:

- **Issuer:** bên phát hành danh tính nằm trong tập được tin cậy.
- **Chữ ký và thuật toán:** xác minh bằng khóa và thuật toán đã cấu hình tin cậy; không lấy chính thông tin do token không tin cậy cung cấp làm căn cứ duy nhất.
- **Audience:** token được phát hành cho đúng bên sử dụng hoặc dịch vụ trao đổi dự kiến.
- **Thời hạn:** token còn hiệu lực; xử lý thời gian theo cơ chế của bên xác thực.
- **Danh tính nguồn chạy:** tổ chức, dự án hoặc repository đúng phạm vi.
- **Ngữ cảnh thực thi:** workflow, loại sự kiện, ref, môi trường hoặc thuộc tính tương đương mà nền tảng thực sự chứng thực.
- **Role đích:** chỉ ánh xạ tới role được policy cho phép.

Tên claim và cách biểu diễn các điều kiện khác nhau giữa nền tảng. Có hệ thống ghép thông tin vào subject, có hệ thống cung cấp claim riêng. Không sao chép một mẫu subject từ môi trường khác mà chưa kiểm tra token thực tế và tài liệu cơ chế xác thực.

Quan trọng hơn, một chuỗi do script tự đặt như environment=production không phải là bằng chứng production. Quyết định phải dựa trên thông tin được nguồn đáng tin chứng thực và các kiểm soát được thực thi ngoài quyền tùy ý của job.

### Mẫu policy tư duy

~~~yaml
# Mã giả mô tả yêu cầu bảo mật; không phải schema của sản phẩm.
identity_exchange_policy:
  issuer: "<issuer CI được cấu hình tin cậy>"
  audience: "<audience của bên trao đổi dự kiến>"
  source:
    project_id: "<định danh dự án được phép>"
    workflow_identity: "<workflow triển khai đã kiểm soát>"
    event_class: "<loại sự kiện triển khai được phép>"
    ref: "<ref được bảo vệ và xác minh>"
    environment: "<môi trường có cơ chế bảo vệ độc lập>"
  target_role: "<role deploy ứng dụng thanh toán production>"
  privilege:
    resource_scope: "<đúng ứng dụng và môi trường>"
    allowed_operations:
      - "<cập nhật phiên bản ứng dụng>"
      - "<đọc trạng thái triển khai>"
    iam_mutation: false
    secret_administration: false
  lifetime:
    maximum_session: "<thời gian đủ cho job>"
  audit:
    require_run_correlation: true
~~~

Policy này phải được chuyển thành các điều kiện mà sản phẩm thật sự hỗ trợ và thực thi. Các dòng iam_mutation: false hay environment không tự tạo ra sự bảo vệ khi chỉ tồn tại trong tài liệu.

Nếu một điều kiện cần thiết không thể được xác minh bằng cơ chế đang dùng, không được coi nó là đã đạt. Cần bổ sung lớp kiểm soát khác hoặc thu hẹp thiết kế cấp quyền.

## 8. Pull request, nhánh bảo vệ và môi trường production

Một pipeline thường cần xử lý cả mã chưa được tin cậy và mã đã được chấp thuận. Hai nhóm này không được chia sẻ cùng đường cấp quyền production.

Mô hình cơ bản:

~~~text
Pull request chưa được chấp thuận
        |
        v
Build / kiểm thử trong môi trường hạn chế
        |
        v
Review và hợp nhất theo kiểm soát nguồn
        |
        v
Build hoặc xác minh artifact từ nguồn được phép
        |
        v
Phê duyệt môi trường và artifact cụ thể
        |
        v
Cấp quyền deploy production ngắn hạn
~~~

Không tự động chạy script từ pull request trong một job có secret hoặc có quyền xin token deploy production. Đặc biệt phải đánh giá tình huống workflow có ngữ cảnh tin cậy nhưng lại checkout hoặc thực thi mã do bên không tin cậy cung cấp.

Các kiểm soát hỗ trợ gồm:

- Bảo vệ thay đổi cấu hình workflow, template và script triển khai.
- Đặt phê duyệt production ở lớp không thể bị bỏ qua bằng cách sửa một dòng script trong job.
- Giới hạn người có thể thay đổi trust policy và quyền của deploy role.
- Ràng buộc artifact được duyệt bằng digest hoặc định danh bất biến tương đương.
- Bảo đảm artifact được triển khai có quan hệ xác minh được với nguồn chạy được phép.
- Tách runner hoặc miền thực thi khi mức độ tin cậy khác nhau.

Branch protection chỉ là một thành phần. Nếu người có thể sửa workflow cũng có thể tự nới điều kiện bảo vệ môi trường và tự duyệt production, sự phân tách nhiệm vụ có thể chưa đạt mục tiêu.

## 9. Quyền ngắn hạn không thay thế least privilege

Credential có thời hạn ngắn làm giảm thời gian một credential bị đánh cắp có thể tiếp tục được sử dụng. Nó không ngăn hành động nguy hiểm trong thời gian credential còn hiệu lực.

Ví dụ, một phiên admin tồn tại tám phút vẫn có thể đủ để tạo user quản trị mới, đọc secret hoặc thay đổi trust. Quyền phát sinh từ những thao tác đó có thể tồn tại lâu hơn tám phút.

Do đó cần kết hợp:

- TTL đủ ngắn và phù hợp thời lượng công việc.
- Giới hạn thao tác và tài nguyên.
- Chặn hoặc kiểm soát đường tự mở rộng quyền.
- Giới hạn việc cấp lại, gia hạn và chuyển sang role khác.
- Theo dõi việc sử dụng ngoài mục đích dự kiến.
- Cơ chế chặn cấp mới và xử lý phiên đang có hiệu lực.

Không nên làm TTL dài hơn nhiều chỉ để một job bị treo vẫn tiếp tục hoạt động. Có thể chia công việc thành giai đoạn hoặc yêu cầu cấp lại quyền có điều kiện. Nếu cho phép cấp lại, phải bảo đảm job vẫn đáp ứng trust và không thể tự gia hạn vô hạn.

Thời hạn của token danh tính CI, thời hạn của credential đích và thời hạn phiên ứng dụng có thể khác nhau. Khi thiết kế thu hồi, cần xét riêng từng loại.

## 10. Luồng deploy minh họa không chứa admin key

Đoạn dưới là mã giả mô tả trình tự. Nó không gọi API thật và không định nghĩa một cú pháp pipeline có thể chạy trực tiếp.

~~~text
deploy_production(run):
    require run.source_is_allowed
    require run.workflow_is_allowed
    require production_approval_matches(run.artifact_digest)

    identity = CI.obtain_workload_identity(
        audience = EXPECTED_EXCHANGE_AUDIENCE
    )

    session = BROKER.exchange(
        identity = identity,
        requested_role = PAYMENT_PRODUCTION_DEPLOY_ROLE,
        correlation_id = run.id
    )
    # Broker tự xác thực token và quyết định role.
    # Không tin các thuộc tính tự khai do job gửi lên.

    try:
        TARGET.deploy(
            resource = PAYMENT_PRODUCTION_APPLICATION,
            artifact_digest = run.artifact_digest,
            session = session
        )
        TARGET.wait_for_result_with_timeout()
    finally:
        discard_local_session_material()
        release_or_revoke_lease_if_supported()

    AUDIT.record_non_secret_result(
        run_id = run.id,
        artifact_digest = run.artifact_digest,
        target = PAYMENT_PRODUCTION_APPLICATION,
        outcome = deployment_result
    )
~~~

Trong triển khai thật, token và session material không được in ra log, đưa vào artifact, ghi vào cache hoặc lưu lại thành CI variable cho lần chạy sau. Nếu công cụ bắt buộc dùng file credential, file phải có quyền truy cập hạn chế, tồn tại trong vùng tạm phù hợp và được dọn khi hoàn tất.

Việc xóa file cục bộ không tự thu hồi credential đã bị sao chép. Tương tự, đóng job hoặc runner không bảo đảm mọi phiên ở hệ thống đích đã hết hiệu lực. Thu hồi phía dịch vụ và xử lý lease phải theo cơ chế thực tế của hệ thống đó.

## 11. Bảo vệ runner và đường vận chuyển credential

Danh tính workload xác thực nguồn chạy; nó không chứng minh mọi mã trong runner đều lành tính. Runner bị chiếm quyền có thể dùng token hợp lệ ngay trong thời gian job chạy.

Các điểm cần thiết kế:

### 11.1. Cô lập môi trường thực thi

Tránh để job có độ tin cậy thấp dùng chung môi trường với job production theo cách cho phép đọc file, cache, process hoặc socket của nhau. Với runner tự quản lý, cần đánh giá credential nền của máy, tài khoản dịch vụ, quyền hệ điều hành và các mount được cung cấp.

Runner không được mang sẵn một quyền máy chủ rộng hơn quyền mà pipeline đang cố kiểm soát. Nếu role production đã được thu hẹp nhưng runner vẫn truy cập được danh tính cloud quản trị qua môi trường máy chủ, job vẫn có thể đi vòng qua broker.

### 11.2. Kiểm soát dependency và thành phần mở rộng

Một action, plugin hoặc script tải từ bên ngoài có thể thực thi trong cùng ngữ cảnh nhận quyền. Cần hạn chế thành phần này ở giai đoạn đặc quyền, kiểm soát nguồn và phiên bản, đồng thời đánh giá khi thay đổi.

Việc ghim phiên bản hoặc digest giúp giảm thay đổi ngoài dự kiến, nhưng không phải bằng chứng tuyệt đối rằng nội dung đó an toàn.

### 11.3. Kiểm soát đầu ra và lưu trữ phụ

Không đưa credential vào:

- Log debug, shell tracing hoặc thông báo lỗi.
- File cấu hình được upload cùng artifact.
- Cache build hoặc dependency cache.
- Container image, layer build hoặc package được phát hành.
- Biến output để job khác nhận lại ngoài đường cấp quyền đã thiết kế.
- Báo cáo kiểm thử hoặc bản ghi chẩn đoán có thể tải xuống.

Nếu cần ghi bằng chứng, ghi định danh phiên, role, run ID và kết quả. Không ghi token hoàn chỉnh hoặc giá trị secret.

### 11.4. Giới hạn đường mạng

Nếu khả thi, job đặc quyền chỉ nên truy cập các dịch vụ cần thiết. Kiểm soát mạng giảm một số đường rò rỉ và truy cập ngoài mục đích, nhưng không thay thế authorization: job vẫn có thể lạm dụng API hợp lệ mà nó được quyền gọi.

## 12. Khi hệ thống đích chưa hỗ trợ federation

Không phải dịch vụ nào cũng nhận danh tính workload hoặc cấp credential động. Có thể sử dụng phương án chuyển tiếp, nhưng phải làm rõ rủi ro còn lại.

| Phương án | Cách triển khai quyền | Điểm cần kiểm soát |
|---|---|---|
| Credential động qua vault | Job xác thực bằng danh tính workload rồi nhận credential ngắn hạn | Policy vault, quyền trên hệ thống đích, lease và thu hồi |
| Broker thực hiện thao tác | Job yêu cầu thao tác; broker giữ credential phía sau | API phải giới hạn tham số và thao tác, không thành proxy quản trị tùy ý |
| Credential dịch vụ tĩnh nhưng hẹp | Cất trong vault, chỉ cấp cho job đủ điều kiện và đúng thời điểm | Rotation, phạm vi quyền, dấu vết sử dụng và thời hạn ngoại lệ |
| Phiên quản trị khẩn cấp | Phê duyệt và cấp quyền qua đường break-glass riêng | Người chịu trách nhiệm, thời gian hiệu lực, ghi bằng chứng và rà soát sau dùng |

Chuyển admin key từ CI variable sang vault rồi cho mọi job đọc key đó chỉ cải thiện một phần việc lưu trữ. Nó chưa giải quyết quyền thường trực hoặc phạm vi ảnh hưởng của credential.

Nếu bắt buộc sử dụng credential tĩnh tạm thời:

1. Dùng tài khoản dịch vụ riêng theo ứng dụng và môi trường.
2. Loại bỏ quyền quản trị không cần thiết.
3. Giới hạn job và danh tính được phép truy xuất credential.
4. Cấp vào giai đoạn cần dùng, tránh đưa vào toàn bộ pipeline.
5. Xác định lịch rotation và quy trình thay thế không gián đoạn.
6. Theo dõi hoạt động sử dụng và thiết lập người sở hữu ngoại lệ.
7. Đặt thời điểm đánh giá lại phương án chuyển sang danh tính ngắn hạn.

Credential bootstrap có quyền cao, nếu vẫn cần, phải được quản lý như một tài sản đặc quyền riêng. Không biến nó thành biến mặc định của pipeline ứng dụng.

## 13. Lộ trình loại bỏ admin key đang có

### Bước 1 — Kiểm kê theo quyền hiệu lực

Lập danh sách credential được pipeline sử dụng và xác định:

- Nơi khai báo, cấp kế thừa và các môi trường có thể nhận.
- Job nào thực sự sử dụng.
- Tài khoản, role và quyền hiệu lực tương ứng.
- Tài nguyên và dữ liệu có thể truy cập.
- Khả năng tạo credential mới hoặc sửa cấu hình cấp quyền.
- Người sở hữu, thời hạn và lần rotation gần nhất.
- Những job còn có đường lấy credential qua runner hoặc file cấu hình.

Không sao chép giá trị secret vào bảng kiểm kê. Dùng định danh credential hoặc tham chiếu được kiểm soát.

### Bước 2 — Tách nhiệm vụ và xác định role tối thiểu

Tách deploy ứng dụng khỏi bootstrap IAM, quản trị vault, quản trị cluster và các công việc không cần chạy ở mọi lần release. Ghi rõ API cần dùng và tài nguyên đích của từng nhiệm vụ.

Có thể dùng log sử dụng để hỗ trợ xác định nhu cầu, nhưng không sao chép toàn bộ quyền từng được dùng thành policy mới. Hoạt động lịch sử có thể bao gồm thao tác quá quyền hoặc tác vụ quản trị một lần.

### Bước 3 — Thiết lập đường danh tính và trust

Cấu hình bên phát hành danh tính được tin cậy, audience và điều kiện nguồn chạy. Tạo role theo môi trường. Bảo vệ người có thể thay đổi trust, policy, workflow và phê duyệt môi trường.

Chọn thời hạn phiên dựa trên thời gian thực thi quan sát được và khả năng dừng công việc. Không chọn thời hạn dài chỉ để tránh xử lý lỗi cấp quyền.

### Bước 4 — Thử nghiệm trong phạm vi hạn chế

Kiểm tra trên môi trường thử nghiệm hoặc một phạm vi có thể phục hồi. Xác nhận job hợp lệ được cấp quyền và các nguồn chạy không hợp lệ bị từ chối.

Ở giai đoạn thử nghiệm, tránh để job âm thầm quay về dùng admin key khi đường mới lỗi. Một fallback như vậy có thể làm kết quả kiểm tra trông thành công dù federation chưa hoạt động.

### Bước 5 — Cắt chuyển production có kiểm soát

Triển khai trên một dịch vụ hoặc nhóm tài nguyên giới hạn trước. Kiểm tra role thực sự được sử dụng từ bằng chứng hệ thống đích, không chỉ dựa vào log “deploy thành công”.

Theo dõi cả tình huống thất bại giữa chừng, cleanup, rollback và migration. Đây là các bước thường phát sinh nhu cầu quyền khác với đường deploy thành công.

### Bước 6 — Vô hiệu hóa credential cũ tại nơi phát hành

Xóa CI variable không làm credential mất hiệu lực ở hệ thống đích. Sau khi xác nhận các bên sử dụng đã chuyển đổi, phải vô hiệu hóa hoặc thu hồi credential cũ bằng cơ chế của bên phát hành.

Đánh giá riêng các phiên đã cấp, credential con hoặc quyền phát sinh. Không coi việc xóa key ban đầu là bằng chứng mọi đường truy cập liên quan đã bị đóng.

### Bước 7 — Dọn bản sao và hoàn tất bằng chứng

Loại bỏ tham chiếu cũ trong pipeline, tài liệu vận hành và cấu hình liên quan. Kiểm tra khả năng credential từng xuất hiện trong log, cache, artifact hoặc lịch sử mã.

Không cần giữ admin key còn hoạt động để làm phương án rollback. Phương án phục hồi nên dùng một đường truy cập có kiểm soát và được phê duyệt riêng. Nếu vẫn phải giữ ngoại lệ, phải có phạm vi, người sở hữu và thời điểm kết thúc cụ thể.

## 14. Kiểm chứng bằng các ca cho phép và từ chối

Một lần deploy thành công chỉ chứng minh có một đường hoạt động. Cần chứng minh các đường không được phép thực sự bị chặn.

| Ca kiểm tra | Kết quả mong đợi | Bằng chứng cần xem |
|---|---|---|
| Workflow hợp lệ deploy đúng ứng dụng production đã duyệt | Được cấp role deploy và cập nhật thành công | Run ID, phê duyệt, sự kiện cấp phiên, log API đích |
| Job build yêu cầu role production | Bị từ chối | Quyết định policy và danh tính nguồn chạy |
| Repository hoặc dự án khác yêu cầu cùng role | Bị từ chối | Điều kiện trust không khớp |
| Nguồn chạy không thuộc ref hoặc ngữ cảnh được phép | Bị từ chối theo policy | Claim đã xác thực và quyết định authorization |
| Token có audience sai hoặc hết hạn | Không được trao đổi | Log xác thực không chứa token |
| Role deploy thử sửa IAM hoặc cấp credential mới | Bị từ chối | Sự kiện từ chối tại hệ thống đích |
| Role staging thử tác động production | Bị từ chối | Scope tài nguyên và log từ chối |
| Job thử triển khai artifact khác artifact đã duyệt | Bị chặn trước hoặc tại lớp triển khai | Digest được duyệt và digest thực tế |
| Chặn cấp mới cho một danh tính đang nghi ngờ | Không cấp phiên mới | Sự kiện thay đổi policy và lần thử sau đó |
| Kiểm tra credential cũ sau cutover | Không thể dùng để xác thực hoặc cấp quyền mới | Trạng thái tại bên phát hành và phép thử được kiểm soát |

Các phép thử tác động IAM hoặc tài nguyên nhạy cảm phải thực hiện trong phạm vi thử nghiệm được phép, bằng thao tác kiểm tra phù hợp. Không thử phá hệ thống production để chứng minh policy.

Với phiên đã cấp trước khi thay đổi trust, kết quả phụ thuộc cơ chế thu hồi của dịch vụ. Ca kiểm tra phải xác định rõ đang thử **cấp phiên mới** hay **sử dụng phiên hiện có**; hai việc này không tương đương.

## 15. Bằng chứng phục vụ kiểm toán và ứng phó sự cố

Mỗi lần deploy đặc quyền cần tạo được một chuỗi tương quan:

~~~text
Thay đổi mã / cấu hình được duyệt
        ->
Run ID và workflow
        ->
Artifact bất biến
        ->
Phê duyệt môi trường
        ->
Danh tính được xác thực
        ->
Role và phiên được cấp
        ->
Thao tác trên tài nguyên đích
        ->
Kết quả và kết thúc phiên / lease
~~~

Một bản ghi có thể chứa:

~~~json
{
  "run_id": "run-example-1042",
  "project_id": "payment-service",
  "workflow": "production-deployment",
  "source_revision": "<commit đã xác minh>",
  "artifact_digest": "<digest artifact đã duyệt>",
  "environment": "production",
  "approval_reference": "<tham chiếu phê duyệt>",
  "role": "payment-production-deployer",
  "session_reference": "<định danh không bí mật>",
  "target_resource": "payment-production-application",
  "outcome": "succeeded"
}
~~~

Đây là dữ liệu minh họa. Hệ thống thực tế cần phân biệt thông tin do job tự báo với bằng chứng do nền tảng CI, broker và dịch vụ đích ghi nhận. Không cho job tự tuyên bố “đã được duyệt” rồi dùng trường đó làm quyết định duy nhất.

Log nên được bảo vệ khỏi việc chính deploy role sửa hoặc xóa để che dấu hoạt động. Thời gian giữa các hệ thống cần đủ nhất quán để điều tra, đồng thời thời hạn lưu bằng chứng phải theo chính sách của tổ chức.

Khi nghi credential hoặc job bị lạm dụng:

1. Chặn nguồn chạy hoặc đường cấp quyền đang bị nghi ngờ.
2. Thu hồi credential bị lộ và xử lý phiên, lease hoặc token liên quan theo khả năng của dịch vụ.
3. Cô lập runner và bảo toàn bằng chứng cần thiết.
4. Kiểm tra thay đổi IAM, credential mới, policy, secret và tài nguyên bị tác động.
5. Phục hồi từ nguồn và artifact đã được xác minh.
6. Chỉ mở lại quyền sau khi xử lý đường xâm nhập và kiểm chứng policy.

Việc key hết hạn không tự xóa quyền mà kẻ tấn công đã tạo hoặc phục hồi dữ liệu đã bị đọc.

## 16. Các sai lầm thiết kế thường gặp

### 16.1. “Biến đã masked nên admin key an toàn”

Masking là kiểm soát đầu ra trong phạm vi nền tảng hỗ trợ. Nó không giới hạn các API mà job có thể gọi. Cần thu hẹp quyền và thay đổi vòng đời cấp quyền.

### 16.2. “Đã dùng OIDC nên có thể cấp admin”

OIDC hỗ trợ xác thực danh tính nguồn chạy. Authorization vẫn phải xác định role, thao tác và tài nguyên. Phiên admin ngắn hạn vẫn là phiên admin.

### 16.3. “Chỉ cần tin issuer của nền tảng CI”

Một nền tảng có thể phát hành danh tính cho nhiều tổ chức, dự án và workflow. Trust phải ràng buộc tới đúng workload và ngữ cảnh, không chỉ tên bên phát hành.

### 16.4. “Chỉ deploy mới có secret, nên build luôn an toàn”

Nếu deploy chạy lại script, hook hoặc artifact thực thi do build không tin cậy tạo ra, mã đó có thể tiếp cận quyền deploy. Cần đánh giá dữ liệu nào sẽ trở thành mã và kiểm soát tính toàn vẹn của artifact.

### 16.5. “Xóa biến là đã thu hồi”

Credential có thể đã được sao chép hoặc đang có phiên còn hiệu lực. Phải xử lý tại nơi phát hành và xác định cách thu hồi phiên theo từng dịch vụ.

### 16.6. “Dùng chung một deploy role cho mọi môi trường giúp đơn giản”

Cách này làm khó việc chứng minh job staging không thể tác động production. Tách role và trust theo môi trường giúp giới hạn phạm vi ảnh hưởng và làm rõ bằng chứng.

### 16.7. “Nếu đường mới lỗi thì tự động dùng admin key cũ”

Fallback âm thầm duy trì đường đặc quyền ngoài thiết kế và che giấu lỗi trust. Một phương án khẩn cấp cần được kích hoạt có kiểm soát, có lý do và có dấu vết riêng.

## 17. Bài tập tình huống

Một nhóm đang vận hành pipeline của dịch vụ thanh toán:

- Build và deploy dùng chung runner tự quản lý.
- Một CI variable cấp nhóm chứa cloud key có quyền admin.
- Job staging và production đều được nhận biến này.
- Deploy production cần một người bấm nút xác nhận.
- Khi deploy lỗi, nhóm bật debug để xem toàn bộ lệnh.
- Artifact được chọn bằng tag có thể thay đổi.

### Yêu cầu

1. Chỉ ra ít nhất bốn đường đưa quyền quản trị tới nơi không cần thiết.
2. Thiết kế danh tính và role riêng cho build, publish, staging và production.
3. Xác định các thuộc tính nguồn chạy cần được bên cấp quyền xác minh.
4. Mô tả cách ràng buộc phê duyệt với artifact được deploy.
5. Đưa ra trình tự thu hồi key cũ mà không tạo fallback admin tự động.
6. Chọn các bằng chứng để chứng minh cutover đã hoàn thành.

### Hướng phân tích

Quyền admin được cấp nhóm có thể lan tới nhiều dự án và môi trường. Runner dùng chung cần được đánh giá khả năng đọc credential hoặc giữ lại trạng thái giữa các job. Nút xác nhận chưa đủ nếu người sửa workflow có thể thay đổi thao tác sau phê duyệt. Debug và tag thay đổi được làm tăng rủi ro lộ credential và triển khai nội dung không đúng với nội dung đã duyệt.

Thiết kế cải thiện cần tách miền thực thi theo độ tin cậy, dùng danh tính workload có trust chặt chẽ, cấp role hẹp theo môi trường và triển khai theo digest. Sau thử nghiệm cho phép và từ chối, nhóm thu hồi key tại bên phát hành, đánh giá phiên còn sống và xác nhận các pipeline không còn phụ thuộc key.

Các bằng chứng phù hợp là: thay đổi policy đã được duyệt, run thử nghiệm, kết quả từ chối sai nguồn chạy, danh tính của phiên deploy thực tế, artifact digest, trạng thái thu hồi key và log tương quan từ CI tới tài nguyên đích.

## 18. Tiêu chí hoàn thành trong vận hành

Có thể coi thiết kế đã đạt mục tiêu khi trả lời được các câu hỏi sau bằng bằng chứng:

- Pipeline thông thường có còn nhận credential quản trị thường trực không?
- Mỗi giai đoạn có danh tính và phạm vi quyền phù hợp không?
- Nguồn chạy không được tin cậy có bị chặn khỏi đường cấp quyền production không?
- Role deploy có bị ngăn tự mở rộng quyền hoặc truy cập môi trường khác không?
- Artifact được triển khai có đúng artifact đã xác minh và phê duyệt không?
- Thời hạn credential, cách cấp lại và cách thu hồi đã được kiểm chứng chưa?
- Runner có còn mang danh tính nền cho phép đi vòng qua policy không?
- Log, cache, artifact và debug có tránh lưu credential không?
- Key cũ đã được vô hiệu hóa tại nơi phát hành và xử lý các bên sử dụng liên quan chưa?
- Mọi ngoại lệ tĩnh còn lại có người sở hữu, phạm vi và thời hạn đánh giá lại không?

PAM cho CI/CD không dừng ở việc cất secret ở một nơi kín hơn. Kết quả cần đạt là mỗi workload chỉ nhận đúng quyền, đúng thời điểm, trên đúng tài nguyên, với đường thu hồi và bằng chứng có thể kiểm tra.
