# Secret retrieval trong pipeline

## 1. Mục tiêu và phạm vi

Trong CI/CD, secret retrieval là quá trình một job đang chạy lấy credential cần thiết từ hệ thống quản lý secret hoặc PAM, đúng thời điểm cần sử dụng. Credential có thể là mật khẩu triển khai, token truy cập kho artifact, tài khoản cơ sở dữ liệu tạm thời hoặc chứng thư khách hàng.

Mục tiêu không chỉ là chuyển mật khẩu ra khỏi repository. Một thiết kế tốt còn phải trả lời được: job nào đang yêu cầu, job được lấy secret nào, secret có hiệu lực đến khi nào, tiến trình nào được sử dụng, và làm thế nào biết quyền truy cập đã kết thúc.

Trong phạm vi PAM, pipeline là một chủ thể máy có thể nắm quyền đặc biệt. Một job triển khai production có thể sửa cấu hình, phát hành ứng dụng hoặc thực thi migration; vì vậy cần kiểm soát quyền của nó như kiểm soát một phiên quản trị tự động.

Sau bài này, người học có thể:

- Phân biệt lấy secret, đưa secret vào tiến trình và sử dụng secret tại hệ thống đích.
- Thiết kế luồng xác thực job bằng danh tính workload thay cho credential khởi tạo dài hạn.
- Giới hạn quyền theo repository, workflow, môi trường, tác vụ và thời gian.
- Xử lý vòng đời credential, lỗi retrieval, hủy job, retry và dọn dẹp.
- Xác định bằng chứng cần ghi nhận mà không ghi giá trị nhạy cảm vào log.

Các cấu hình và mã giả bên dưới dùng để giải thích thiết kế, không phải cú pháp của một sản phẩm cụ thể.

## 2. Retrieval chỉ là một phần của chuỗi truy cập

Một chuỗi truy cập đầy đủ thường gồm ba hoạt động khác nhau.

| Hoạt động | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| Retrieval | Job có được nhận credential này không? | PAM cấp credential triển khai cho job đã được phê duyệt |
| Injection | Credential được chuyển cho tiến trình tiêu thụ bằng cách nào? | Wrapper tạo file cấu hình tạm chỉ tiến trình triển khai đọc được |
| Use | Credential cho phép thao tác gì ở hệ thống đích? | Chỉ phát hành một dịch vụ trong một namespace |
| Termination | Quyền và dấu vết nhạy cảm được kết thúc thế nào? | Thu hồi lease, xóa file tạm và hủy runner |

Có thể retrieval đúng nhưng injection sai. Ví dụ, broker chỉ cấp đúng secret cho job hợp lệ, nhưng job lại ghi secret vào file được đóng gói làm artifact. Cũng có thể cả hai bước đầu đúng nhưng quyền tại hệ thống đích quá rộng, chẳng hạn một credential triển khai lại có quyền quản trị toàn bộ cụm.

Vì vậy, không đồng nhất “đã dùng vault” với “đã kiểm soát privileged access”.

Một mô hình hữu ích là:

~~~text
Nguồn danh tính CI → Job identity → PAM/broker → Credential giới hạn
                                                    ↓
                                        Tiến trình triển khai
                                                    ↓
                                          Hệ thống đích

Nhật ký CI + quyết định cấp quyền + lease + nhật ký đích
                    → chuỗi bằng chứng tương quan
~~~

Thành phần môi giới có thể là một chức năng của PAM hoặc một dịch vụ tích hợp. Không phải hệ thống nào cũng dùng đúng tên “broker”, nhưng các trách nhiệm xác thực, cấp quyền và kiểm toán vẫn cần được thể hiện rõ.

## 3. Bài toán bootstrap: ai được phép mở kho secret?

Nếu pipeline cần một token dài hạn để lấy mọi secret khác, ta mới chỉ chuyển rủi ro sang token bootstrap. Khi token này bị đánh cắp, kẻ tấn công có thể gọi dịch vụ cấp secret ngoài job hợp lệ, tùy các ràng buộc còn lại.

Một lựa chọn thường phù hợp hơn là liên kết danh tính workload:

1. Nền tảng CI phát hành một assertion có chữ ký cho đúng ngữ cảnh job.
2. Job gửi assertion tới broker có trust đã cấu hình trước.
3. Broker xác minh assertion và đối chiếu chính sách.
4. Broker cấp quyền retrieval hoặc trả credential ngắn hạn cho yêu cầu hợp lệ.

Assertion có thể là token OIDC hoặc loại bằng chứng workload khác. Nó chứng minh ngữ cảnh của job theo issuer mà broker tin cậy; nó không tự chứng minh mọi đoạn mã trong job đều an toàn.

### 3.1. Những gì cần xác minh

Broker cần xác minh ít nhất chữ ký, issuer, audience, thời hạn và các claim dùng cho chính sách. Chỉ đọc payload của token rồi tin nội dung là không đủ.

Các claim hoặc thuộc tính liên quan có thể gồm:

- Định danh tổ chức, repository hoặc dự án.
- Định danh workflow và nguồn định nghĩa workflow được tin cậy.
- Ref hoặc commit liên quan đến lần chạy.
- Loại sự kiện kích hoạt và nguồn thay đổi.
- Môi trường triển khai và ngữ cảnh phê duyệt.
- Định danh lần chạy, lần thử lại và job.

Tên claim, mức độ sẵn có và ý nghĩa cụ thể phụ thuộc nền tảng CI. Chỉ dùng các thuộc tính mà nguồn danh tính thực sự chứng thực. Không mặc định mọi nền tảng đều đưa kết quả phê duyệt hoặc mọi thuộc tính trên vào token.

Nếu một quyết định cần dữ liệu ngoài token, broker phải lấy dữ liệu đó từ nguồn có xác thực và ràng buộc nó với đúng lần chạy. Một biến môi trường do script tự đặt không phải bằng chứng phê duyệt.

### 3.2. Chữ ký hợp lệ chưa có nghĩa là được cấp secret

Một token có chữ ký hợp lệ nhưng sai audience vẫn phải bị từ chối. Một token thuộc đúng repository nhưng xuất phát từ ngữ cảnh pull request không tin cậy cũng có thể phải bị từ chối.

Ví dụ, chỉ kiểm tra “repository = payment-service” là chưa đủ nếu repository đó cho phép chạy code do bên ngoài đóng góp. Chính sách production còn cần giới hạn ngữ cảnh chạy, workflow được tin cậy và điều kiện phát hành.

Token ngắn hạn cũng có thể bị replay trong cửa sổ còn hiệu lực. Cần hạn chế nơi nhận token, không ghi token vào log, không chuyển token cho bước không cần dùng, và sử dụng cơ chế ràng buộc hoặc chống replay phù hợp nếu hệ thống hỗ trợ. Không suy ra rằng token tự động chỉ dùng được một lần.

## 4. Thiết kế quyền retrieval theo đúng tác vụ

Pipeline không nên có một quyền chung kiểu “đọc mọi secret của dự án”. Hãy bắt đầu từ tác vụ cụ thể.

Ví dụ với một ứng dụng thanh toán:

| Tác vụ | Quyền retrieval | Quyền tại hệ thống đích |
| --- | --- | --- |
| Build | Credential đọc dependency riêng, nếu thật sự cần | Chỉ đọc đúng kho dependency |
| Publish artifact | Credential ghi một repository artifact | Ghi artifact vào đúng namespace |
| Deploy staging | Credential triển khai staging | Sửa đúng dịch vụ trong staging |
| Deploy production | Credential triển khai production | Sửa đúng dịch vụ trong production |
| Database migration | Credential migration riêng | Thực thi nhóm thay đổi cơ sở dữ liệu được cho phép |

Credential đọc dependency không cần tồn tại ở bước deploy. Credential deploy cũng không mặc nhiên được thực thi migration. Tách quyền giúp thu hồi, điều tra và áp dụng chính sách theo đúng mức rủi ro.

### 4.1. Chọn role từ chính sách được quản lý

Một thiết kế yếu cho phép script truyền một đường dẫn secret bất kỳ tới broker. Khi script bị sửa, người sửa có thể yêu cầu secret của môi trường khác.

Một thiết kế chặt hơn ánh xạ danh tính job và tác vụ vào role phía broker:

~~~text
Danh tính job đã xác minh
+ tác vụ yêu cầu
+ môi trường được phép
        ↓
Role do broker lựa chọn
        ↓
Tập secret và thao tác được cho phép
~~~

Client có thể gửi một tên role hoặc resource theo hợp đồng API, nhưng broker phải tự kiểm tra tên đó có thuộc tập quyền của job hay không. Giá trị client gửi chỉ là yêu cầu, không phải quyền đã được cấp.

### 4.2. Chính sách minh họa

~~~yaml
# Mô hình khái niệm, không dùng trực tiếp cho sản phẩm cụ thể.
policy:
  action: retrieve-deployment-credential
  trusted_identity:
    issuer: ci-issuer-da-duoc-dang-ky
    audience: pam-deployment-broker
    repository_id: payment-service-id
    workflow_identity: trusted-release-workflow
    deployment_environment: production
  authorization:
    require_trusted_release_context: true
    require_verified_approval_for_this_run: true
    allowed_role: payment-production-deployer
    allowed_target: payment-production
    maximum_credential_ttl: 10m
  audit:
    correlate_by:
      - run_id
      - job_id
      - attempt_id
      - commit_digest
~~~

Các điều kiện “trusted release” và “verified approval” cần được triển khai bằng bằng chứng thật của nền tảng, không phải chuỗi tự khai báo. TTL mười phút chỉ là ví dụ; thời hạn thực tế phải dựa vào tác vụ và khả năng thu hồi của hệ thống đích.

Cần bảo vệ cả nơi định nghĩa workflow, chính sách broker và mã triển khai. Nếu một người có thể tùy ý sửa workflow production rồi tự kích hoạt, việc thêm broker không loại bỏ quyền phát hành quá rộng đó.

## 5. Luồng retrieval xuyên suốt một job

Một luồng triển khai có thể tổ chức như sau:

1. Xác minh artifact và điều kiện phát hành trước khi xin credential đặc quyền.
2. Khởi chạy job trên runner phù hợp với mức tin cậy của môi trường.
3. Lấy assertion dành riêng cho audience của broker.
4. Gửi yêu cầu retrieval qua kết nối xác thực máy chủ, kèm danh tính và thông tin tương quan cần thiết.
5. Broker kiểm tra danh tính, chính sách và quyền truy cập của role.
6. Broker lấy một secret đã lưu hoặc tạo credential động tại hệ thống đích.
7. Job nhận credential cùng thông tin quản lý vòng đời như thời điểm hết hạn và mã lease nếu có.
8. Wrapper chuyển credential cho đúng tiến trình tiêu thụ.
9. Tiến trình thực hiện tác vụ giới hạn.
10. Job yêu cầu thu hồi, xóa dữ liệu tạm và kết thúc.
11. Cơ chế phía máy chủ xử lý lease còn sót nếu job bị ngắt trước bước dọn dẹp.

Mỗi bước có trách nhiệm riêng. Nếu broker chỉ trả mật khẩu tĩnh đã lưu thì không được mô tả đó là tài khoản động. Nếu broker chỉ theo dõi một phiên checkout, đóng checkout chưa chắc đã làm mật khẩu hết hiệu lực tại hệ thống đích.

### 5.1. Lấy đúng lúc cần dùng

Không nên lấy credential production từ đầu một pipeline còn phải build và kiểm thử hàng chục phút. Khoảng thời gian credential nằm trong runner sẽ dài hơn, trong khi nhiều bước không cần quyền đó.

Hãy đặt retrieval gần bước sử dụng. Nếu pipeline có nhiều job độc lập, mỗi job nên xác thực và xin quyền của chính nó. Không truyền secret từ job này sang job khác bằng output, artifact hoặc file dùng chung.

### 5.2. Chỉ một số dữ liệu được đi tiếp

Trong chuỗi bằng chứng, có thể cần giữ run ID, artifact digest, quyết định cấp quyền, thời điểm cấp và kết quả thu hồi. Giá trị credential và assertion không nên trở thành output của job.

Mã lease cũng cần được phân loại. Nếu nó có thể dùng để thao tác quản lý lease, không công bố nó như một mã tương quan vô hại. Có thể dùng một audit reference riêng để liên kết sự kiện.

## 6. Phân biệt secret tĩnh, credential động và quyền ngắn hạn

| Loại | Đặc điểm | Điều phải kiểm tra |
| --- | --- | --- |
| Secret tĩnh được quản lý | Broker trả một giá trị đã tồn tại | Rotation, chia sẻ, phiên checkout và tác động khi lộ |
| Credential động | Dịch vụ cấp phát tạo credential cho yêu cầu hoặc lease | Quyền tại đích, TTL, renewal và thu hồi thực tế |
| Token hoặc chứng thư ngắn hạn | Quyền thường bị giới hạn bằng thời hạn hoặc điều kiện | Audience, scope, cách xác minh, khả năng thu hồi trước hạn |
| Quyền truy cập qua proxy | Job dùng một phiên được môi giới | Giới hạn phiên, ghi nhận hoạt động, hành vi khi proxy mất kết nối |

Credential động thuận lợi cho việc cô lập từng lần chạy, nhưng không tự bảo đảm quyền tối thiểu. Một tài khoản tạm có quyền quản trị toàn bộ cơ sở dữ liệu vẫn là một quyền quá rộng.

Tương tự, không phải mọi token ngắn hạn đều hỗ trợ thu hồi tức thì. Một token được hệ thống đích tự xác minh có thể tiếp tục được chấp nhận đến khi hết hạn, tùy cơ chế của đích. Chứng thư có thời hạn ngắn cũng không tự đóng mọi kết nối đã thiết lập.

Cần biết rõ ba thời điểm:

- Khi broker không còn cho lấy credential mới.
- Khi credential hiện tại không còn được đích chấp nhận.
- Khi các phiên hoặc kết nối đã mở thực sự bị kết thúc.

Ba thời điểm này có thể khác nhau. Thiết kế ứng phó sự cố cần dựa trên hành vi thực tế, không chỉ trên một giá trị TTL.

## 7. Injection: đưa secret đến đúng tiến trình

Sau retrieval, secret phải tồn tại ở đâu đó để client sử dụng. Không có phương thức injection nào tự bảo vệ được trước mọi mã độc đang chạy cùng mức đặc quyền trên runner.

| Phương thức | Điểm cần cân nhắc | Kiểm soát quan trọng |
| --- | --- | --- |
| SDK hoặc handle trong bộ nhớ | Tránh tạo file, nhưng ứng dụng và debugger vẫn có thể đọc | Thu hẹp tiến trình và thời gian giữ giá trị |
| File tạm | Phù hợp client cần file cấu hình, có nguy cơ bị thu gom hoặc còn sót | Quyền truy cập, thư mục riêng, loại khỏi artifact và cleanup |
| Biến môi trường | Dễ tích hợp nhưng dễ bị kế thừa hoặc xuất trong chẩn đoán | Chỉ truyền cho tiến trình con cần dùng, không dump môi trường |
| Standard input | Tránh tham số dòng lệnh nếu client hỗ trợ | Không ghi luồng input, không chuyển qua công cụ trung gian không tin cậy |
| Proxy hoặc agent | Có thể giảm việc phát credential thô cho job | Kiểm soát phiên, runner identity và quyền gọi agent |

### 7.1. Tránh những kênh rò rỉ phổ biến

Không đưa secret vào:

- Tham số dòng lệnh khi công cụ có phương thức nhận an toàn hơn.
- URL, query string hoặc tên file.
- Step output, job output hoặc thông báo lỗi.
- Artifact, cache, ảnh container hoặc thư mục workspace sẽ được đóng gói.
- Báo cáo kiểm thử, trace HTTP, core dump hoặc gói chẩn đoán.
- Lệnh được in ra bởi shell tracing.

Masking là một lớp giảm rò rỉ trong log, không phải ranh giới bảo mật. Giá trị bị biến đổi, chia nhỏ hoặc mã hóa có thể không được che như mong đợi. Mã độc trong job cũng có thể gửi secret ra ngoài mà không qua log.

Với file tạm, quyền file chỉ hữu ích khi người dùng và tiến trình khác không có quyền tương đương hoặc cao hơn. Xóa file sau sử dụng không thể đảo ngược việc secret đã bị sao chép hoặc truyền ra ngoài.

### 7.2. Wrapper cần giới hạn môi trường tiến trình con

Thay vì đặt secret vào môi trường chung của toàn job, wrapper có thể dựng một môi trường tối thiểu chỉ cho tiến trình triển khai. Các bước build, test và báo cáo không được kế thừa credential một cách tự động.

Nếu công cụ triển khai tự gọi plugin, hook hoặc script bổ sung, các thành phần đó cũng nằm trong phạm vi có thể tiếp cận secret. Cần tính cả chuỗi tiến trình con, không chỉ chương trình đầu tiên được gọi.

## 8. Mã giả quản lý vòng đời

Ví dụ sau mô tả trách nhiệm của một wrapper. Các tên hàm là khái niệm, không phải API sẵn có.

~~~text
function deployApprovedArtifact(context):
    assertTrustedArtifact(context.artifactDigest)

    credential = NONE
    temporaryInput = NONE
    deploymentResult = FAILURE

    try:
        assertion = requestWorkloadAssertion(
            audience = "pam-deployment-broker"
        )

        credential = broker.retrieve(
            identity = assertion,
            requestedAction = "deploy-payment-production",
            correlation = {
                run: context.runId,
                job: context.jobId,
                attempt: context.attemptId,
                artifact: context.artifactDigest
            },
            deadline = context.retrievalDeadline
        )

        discardAssertionReference()

        requireCredentialLifetimeForStart(
            credential.expiresAt,
            context.minimumStartWindow
        )

        temporaryInput = createPrivateConsumerInput(
            secret = credential.value,
            locationOutsideWorkspace = true
        )

        deploymentResult = runDeployment(
            artifactDigest = context.artifactDigest,
            credentialInput = temporaryInput,
            boundedRuntime = context.deploymentDeadline,
            sanitizedEnvironment = true
        )

    finally:
        try:
            if credential exists:
                requestRevocationWithBoundedRetry(
                    credential.managementReference
                )
        finally:
            removeTemporaryInputIfPresent(temporaryInput)
            discardCredentialReferences()
            reportLifecycleOutcomeWithoutSensitiveValues()

    return deploymentResult
~~~

Mã giả này cần được bổ sung khi triển khai thật:

- Không đưa assertion hoặc secret vào exception, telemetry hay object được serialize.
- Áp dụng timeout cho retrieval, thao tác đích và cleanup.
- Giữ kết quả triển khai tách với kết quả thu hồi; cleanup thất bại không được biến mất trong log thành công.
- Bảo đảm cleanup vẫn được thử nếu tạo file tạm hoặc chạy client thất bại.
- Có cơ chế TTL hoặc reaper phía máy chủ cho trường hợp runner mất nguồn, bị kill hoặc không chạy được khối finally.
- Hạn chế thời gian lưu giá trị trong bộ nhớ, nhưng không tuyên bố có thể xóa sạch mọi bản sao trong runtime có garbage collector.

Không có khối finally nào bảo đảm chạy được khi máy chủ runner bị mất. Đây là lý do cần cơ chế kết thúc quyền độc lập với job.

## 9. TTL, renewal, retry và tính lặp lại

### 9.1. Chọn TTL theo tác vụ, không theo sự tiện lợi

TTL cần đủ cho tác vụ dự kiến và một khoảng đệm có kiểm soát, nhưng không nên kéo dài chỉ vì pipeline có nhiều bước không cần đặc quyền.

Ví dụ, nếu triển khai thường mất bốn phút, cần đánh giá thời gian khởi tạo client, độ lệch đồng hồ và tình huống chậm hợp lý trước khi chọn TTL. Nếu job có thể chạy hàng giờ, hãy chia nhỏ tác vụ hoặc thiết kế renewal có giới hạn thay vì cấp một credential rất dài từ đầu.

Client nên dừng trước khi bắt đầu một thao tác nếu thời hạn còn lại không đáp ứng cửa sổ tối thiểu đã định. Không tự chuyển sang credential dài hạn khi credential ngắn hạn không đủ.

### 9.2. Renewal là một quyết định cấp quyền tiếp theo

Renewal không nên là một vòng lặp vô hạn chỉ vì job còn giữ mã lease. Cần xác định:

- Lease có hỗ trợ renewal hay không.
- Tổng thời gian tối đa được phép.
- Điều kiện nào làm mất quyền tiếp tục.
- Danh tính hoặc bằng chứng nào cần cho yêu cầu renewal.
- Hành vi khi renewal bị từ chối giữa tác vụ.

Với tác vụ không thể ngắt tùy tiện, phải thiết kế giới hạn và cơ chế phục hồi của chính tác vụ. Không để nhu cầu kéo dài credential thay thế việc quản lý giao dịch hoặc tính nhất quán ở hệ thống đích.

### 9.3. Retry retrieval khác retry deployment

Một yêu cầu cấp credential bị timeout có thể đã được broker xử lý. Retry thiếu kiểm soát có thể tạo nhiều credential hoặc lease.

Nếu dịch vụ hỗ trợ khóa idempotency, cần ràng buộc khóa với danh tính, loại yêu cầu và lần thử tương ứng. Dịch vụ cũng phải xử lý xung đột nội dung cho cùng khóa. Nếu không hỗ trợ, cần cơ chế quản lý credential mồ côi và giới hạn retry; không giả định mỗi lần timeout đồng nghĩa chưa cấp gì.

Tương tự, deployment bị timeout không đồng nghĩa deployment chưa xảy ra. Trước khi chạy lại migration hoặc phát hành, phải kiểm tra trạng thái tại đích và tính lặp lại của thao tác.

Đối với lỗi từ chối quyền, không thử lần lượt các role rộng hơn. Retry phù hợp với lỗi tạm thời; thay đổi chính sách cần một quyết định khác có bằng chứng.

## 10. Runner, nguồn code và ranh giới tin cậy

Một runner bị kiểm soát có thể đọc credential mà nó nhận hợp lệ. Vì vậy, thiết kế retrieval phải đi cùng thiết kế môi trường thực thi.

### 10.1. Tách job không tin cậy khỏi job đặc quyền

Job chạy code từ pull request bên ngoài không nên nhận secret production. Cũng không nên cho job đó đặt sẵn script hoặc executable mà job production sẽ dùng sau này trong một workspace chung.

Việc tách thành hai job chỉ hữu ích khi ranh giới dữ liệu giữa chúng được kiểm soát. Artifact chuyển sang bước triển khai cần được xác minh nguồn, tính toàn vẹn và điều kiện phát hành phù hợp.

Một job triển khai tin cậy nên sử dụng artifact đã xác minh và quy trình triển khai được bảo vệ. Tránh việc lấy credential production rồi chạy thêm script tùy ý lấy từ nguồn thay đổi chưa được tin cậy.

### 10.2. Runner tạm thời và runner dùng lâu dài

Runner tạm thời theo job giúp giảm dữ liệu còn sót và giảm cơ hội một job cài persistence để chờ job sau. Tuy nhiên, nó không ngăn secret bị đánh cắp ngay trong job hiện tại.

Runner dùng lâu dài cần đặc biệt chú ý:

- Tài khoản thực thi và quyền quản trị máy.
- Workspace, thư mục tạm, cache và tiến trình nền còn sót.
- Container runtime, socket điều khiển và các volume gắn từ host.
- Kênh truy cập metadata hoặc danh tính nền của máy.
- Việc nhiều job có thể cùng dùng chung một ranh giới bảo mật.

Container không mặc nhiên tạo ra ranh giới đủ mạnh nếu job có quyền quản trị host hoặc truy cập socket điều khiển container. Secret không nên được bảo vệ chỉ bằng niềm tin rằng “mỗi bước nằm trong một container”.

### 10.3. Thành phần bên thứ ba

Action, plugin hoặc công cụ bên thứ ba trong bước có secret có thể đọc secret theo quyền của tiến trình. Cần quản lý nguồn, phiên bản hoặc digest tin cậy và giới hạn thành phần được chạy ở job đặc quyền.

Không cần cấp secret chỉ để một bước tạo báo cáo hoặc gửi thông báo. Đặt các bước đó ngoài phạm vi tiến trình có credential khi thiết kế cho phép.

## 11. Xử lý lỗi theo cách không mở rộng quyền

| Tình huống | Hành vi phù hợp | Bằng chứng nên giữ |
| --- | --- | --- |
| Không lấy được workload identity | Dừng bước đặc quyền | Run/job, loại lỗi, thời điểm |
| Assertion sai issuer, audience hoặc hết hạn | Từ chối retrieval | Lý do đã chuẩn hóa, không giữ token |
| Không đủ quyền theo policy | Dừng, không thử role rộng hơn | Role được yêu cầu, policy decision reference |
| Broker tạm thời không sẵn sàng | Retry có giới hạn rồi dừng | Số lần thử, timeout, mã lỗi |
| Credential không còn đủ thời hạn để bắt đầu | Xin lại hoặc dừng theo hợp đồng | Thời hạn và quyết định, không ghi giá trị |
| Job bị hủy | Thử cleanup, dựa thêm vào cơ chế phía máy chủ | Kết quả thu hồi hoặc trạng thái chưa xác định |
| Thu hồi thất bại | Ghi nhận lifecycle chưa hoàn tất, cảnh báo theo quy trình | Credential reference được bảo vệ, đích, thời hạn |
| Nghi lộ secret | Ngăn cấp mới và xử lý quyền còn hiệu lực tại đích | Phạm vi ảnh hưởng và chuỗi sự kiện |

Fail closed ở đây nghĩa là thiếu bằng chứng hoặc không được cấp quyền thì không chạy bước đặc quyền. Nó không đồng nghĩa bỏ qua việc ghi nhận và phục hồi một deployment đã thực hiện dở.

Đường break-glass nếu tồn tại phải là quy trình được quản lý riêng, có người chịu trách nhiệm và bằng chứng. Không cài một mật khẩu dự phòng vào pipeline để tự động bỏ qua lỗi của broker.

## 12. Logging và bằng chứng kiểm toán

Một bản ghi retrieval có ích cần nối được danh tính job với quyền đã cấp và hành vi tại hệ thống đích, nhưng không chứa giá trị có thể dùng để truy cập.

Ví dụ bản ghi đã làm sạch:

~~~json
{
  "event": "pam.credential.issue",
  "run_id": "run-8421",
  "job_id": "deploy-production",
  "attempt_id": "attempt-1",
  "artifact_digest": "sha256:example-artifact-digest",
  "requested_action": "deploy-payment-production",
  "authorized_role": "payment-production-deployer",
  "target": "payment-production",
  "decision": "allow",
  "audit_reference": "audit-5832",
  "expires_at": "2026-01-01T10:10:00Z"
}
~~~

Digest và thời điểm trong ví dụ chỉ là dữ liệu minh họa. Bản ghi thực tế nên bổ sung định danh policy hoặc phiên bản policy, kết quả phê duyệt có nguồn xác minh, loại credential và thông tin tương quan phía đích nếu có.

Không ghi assertion, access token, refresh token, mật khẩu, private key hoặc toàn bộ phản hồi retrieval. Cũng không bật HTTP debug rồi cho rằng redaction ở log CI sẽ bảo vệ mọi hệ thống lưu trace.

Những sự kiện nên được nối thành chuỗi:

~~~text
Phê duyệt → xác thực job → quyết định cấp quyền → cấp credential
          → thao tác tại đích → thu hồi/hết hạn → kết thúc job
~~~

“Job thành công” chưa chứng minh credential đã bị thu hồi. “Đã gửi yêu cầu revoke” cũng chưa chứng minh đích đã vô hiệu hóa credential hoặc đóng phiên liên quan. Cần ghi rõ kết quả đã xác minh và phần còn chưa biết.

Log và audit reference cũng có thể chứa thông tin nhạy cảm về hạ tầng. Phân quyền đọc và thời gian lưu của chúng là một phần của thiết kế kiểm toán.

## 13. Tình huống thực tế: triển khai và migration

Một nhóm có một job dùng chung tài khoản “automation-admin” cho build, deploy và migration. Mật khẩu được lấy từ vault nhưng giữ trong biến môi trường của toàn job. Job tải thêm công cụ báo cáo sau khi triển khai.

Thiết kế này có ba vấn đề chính: quyền được gộp quá rộng, nhiều bước nhận secret không cần thiết, và thành phần tải thêm có cơ hội tiếp cận credential.

Có thể thay đổi thiết kế theo từng tác vụ:

1. Job build không có credential production, tạo artifact có digest.
2. Job deploy tin cậy xác minh artifact và điều kiện phê duyệt của lần chạy.
3. Broker cấp role triển khai chỉ cho đúng ứng dụng ở production.
4. Wrapper truyền credential cho tiến trình deploy, sau đó thu hồi.
5. Nếu cần migration, một bước hoặc job được cấp quyền migration riêng theo chính sách.
6. Báo cáo chỉ nhận trạng thái và audit reference đã làm sạch.

Tách role deploy và migration không buộc phải có hai lần phê duyệt trong mọi hệ thống. Điều quan trọng là các quyền, điều kiện và trách nhiệm được định nghĩa rõ, thay vì vô tình cho mọi bước cùng một quyền quản trị.

Nếu migration thất bại sau khi deployment hoàn tất, phải đánh giá trạng thái ứng dụng và cơ sở dữ liệu. Không xử lý bằng cách tự xin một credential rộng hơn để thử lại.

## 14. Tình huống hủy job và credential còn hiệu lực

Giả sử job đã nhận một credential động TTL mười phút. Sau hai phút, runner mất kết nối. Bước cleanup không chạy.

Có thể xảy ra các trạng thái sau:

- Broker biết lease vẫn tồn tại nhưng không biết tác vụ đã thực hiện đến đâu.
- Credential có thể còn được đích chấp nhận đến khi hết hạn hoặc được thu hồi.
- Một kết nối đã mở có thể có vòng đời khác với credential ban đầu.
- Lần chạy lại có thể tạo credential thứ hai và thực hiện trùng thao tác.

Thiết kế cần có cơ chế xử lý lease bị bỏ lại, nhận biết job hoặc runner đã mất, và xác minh hành vi thu hồi tại đích. Khi chạy lại, kiểm tra trạng thái deployment thay vì dựa vào sự vắng mặt của log thành công.

Nếu dùng secret tĩnh, TTL của checkout không tự giới hạn tuổi thọ của mật khẩu. Tùy chính sách và khả năng tích hợp, có thể cần rotation, chặn phiên hoặc biện pháp tại đích khác. Mọi thay đổi phải tính đến consumer hợp lệ đang dùng cùng credential.

## 15. Bài thực hành thiết kế

### 15.1. Đề bài

Một pipeline gồm build, integration test, publish artifact và deploy production. Pull request từ fork cũng được chạy test. Hệ thống hỗ trợ workload identity và broker cấp credential triển khai theo lease.

Hãy thiết kế luồng retrieval sao cho:

- Test từ fork không thể lấy credential production.
- Bước publish chỉ có quyền ghi đúng kho artifact.
- Deploy chỉ dùng artifact đã được xác minh.
- Hủy job không để credential tồn tại vô thời hạn.
- Log đủ để liên kết phê duyệt, lần chạy và hoạt động tại đích.

### 15.2. Một phương án đáp ứng

Tách job test không tin cậy khỏi các job có quyền ghi hoặc triển khai. Không dùng runner hoặc workspace chung theo cách cho phép test để lại mã sẽ chạy trong bước đặc quyền.

Broker cấp role publish và role deploy khác nhau. Quyết định role dựa trên danh tính đã xác minh và điều kiện chính sách. Role deploy chỉ hợp lệ trong ngữ cảnh phát hành production được bảo vệ, với bằng chứng phê duyệt ràng buộc đúng lần chạy.

Deploy xác minh artifact trước retrieval. Credential được cấp gần thời điểm dùng, truyền vào tiến trình triển khai và không xuất thành output hoặc artifact. Job thử revoke khi kết thúc; TTL và cơ chế xử lý lease phía máy chủ giới hạn credential còn sót khi job bị mất.

Hệ thống ghi run ID, job ID, attempt ID, artifact digest, policy decision, audit reference, đích và kết quả vòng đời. Nhật ký hệ thống đích được liên kết bằng định danh hoặc phiên đã cấp nếu tích hợp cho phép.

### 15.3. Các phép kiểm tra trong môi trường thử nghiệm

| Phép kiểm tra | Kết quả mong đợi |
| --- | --- |
| Yêu cầu production từ ngữ cảnh fork | Broker từ chối; không cấp credential |
| Gửi assertion có audience sai | Xác thực thất bại |
| Dùng role publish để xin quyền deploy | Chính sách từ chối |
| Hủy job sau khi cấp credential | Cleanup được thử hoặc lease được xử lý bởi cơ chế phía máy chủ |
| Broker không sẵn sàng | Job retry hữu hạn rồi dừng bước đặc quyền |
| Timeout khi cấp credential | Không tạo lease vô hạn qua retry không kiểm soát |
| Client in lỗi | Không có secret hoặc assertion trong log, output và artifact |
| Thu hồi khi client đang kết nối | Ghi nhận đúng hành vi của đích đối với credential và phiên đang mở |

Đây là kế hoạch kiểm tra để triển khai bài thực hành, không phải kết quả kiểm thử đã chạy. Với secret thật, chỉ kiểm tra trong phạm vi được phép và tránh đưa giá trị nhạy cảm vào bằng chứng.

## 16. Câu hỏi tự kiểm tra

**1. Vì sao chuyển mật khẩu vào vault chưa giải quyết toàn bộ rủi ro của pipeline?**

Vì job vẫn có thể xin quyền quá rộng, truyền secret qua kênh rò rỉ hoặc chạy code không tin cậy sau khi nhận secret. Cần kiểm soát cả danh tính job, quyền tại đích, injection và kết thúc quyền.

**2. Assertion đúng chữ ký có đủ để lấy credential production không?**

Không. Còn cần issuer và audience đúng, thời hạn hợp lệ, cùng các điều kiện ủy quyền ràng buộc với ngữ cảnh job được tin cậy.

**3. Vì sao không nên dùng job output để chuyển credential sang job deploy?**

Output tạo thêm nơi lưu và truyền secret, kéo dài phạm vi tiếp cận và làm mờ danh tính consumer. Job deploy nên tự xác thực và nhận đúng quyền của nó.

**4. Xóa file credential có tương đương revoke không?**

Không. Xóa file chỉ xử lý một bản sao cục bộ. Revoke hoặc hết hạn cần làm quyền truy cập không còn được đích chấp nhận; các phiên đã mở có thể cần xử lý riêng.

**5. Tại sao cleanup trong job phải đi kèm cơ chế phía máy chủ?**

Vì runner có thể bị kill, mất nguồn hoặc mất kết nối trước khi cleanup chạy. TTL, lease reaper và cơ chế thu hồi phía máy chủ tạo giới hạn không phụ thuộc hoàn toàn vào sự hợp tác của job.

**6. Masking trong log có ngăn mã độc lấy secret không?**

Không. Mã độc có thể biến đổi giá trị hoặc gửi ra ngoài. Masking giảm một loại rò rỉ quan sát được; ranh giới tin cậy của code và runner mới quyết định ai có thể đọc secret.

## 17. Điểm cần ghi nhớ

Secret retrieval an toàn bắt đầu từ danh tính job được xác minh và một tác vụ được ủy quyền cụ thể. Credential cần có quyền đủ hẹp, tồn tại đủ ngắn và chỉ đến đúng tiến trình tiêu thụ.

Vòng đời không kết thúc ở lúc API trả secret. Cần quản lý injection, retry, hủy job, thu hồi và những phiên đã mở tại hệ thống đích. Bằng chứng tốt liên kết được toàn bộ chuỗi đó mà không trở thành một kho chứa credential thứ hai.
