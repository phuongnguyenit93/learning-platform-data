# Bảo vệ nhánh chính, cấu hình pipeline và thành phần tái sử dụng

Pipeline CI/CD thường có quyền đọc mã nguồn, lấy dependency, tạo artifact, truy cập secret và triển khai ứng dụng. Nếu một thay đổi không được kiểm soát có thể sửa workflow, bỏ qua kiểm tra hoặc sử dụng token với quyền quá rộng, kẻ tấn công có thể biến pipeline thành đường đi để thay đổi mã phát hành hoặc truy cập hệ thống nội bộ. Vì vậy, bảo mật pipeline phải bắt đầu từ nơi thay đổi được chấp nhận, tiếp tục qua cách định nghĩa workflow và mở rộng đến mọi thành phần được tái sử dụng.

Ba vùng cần bảo vệ chặt chẽ là:

- **Nhánh chính:** nơi lưu trạng thái mã nguồn đã được review và thường là nguồn tạo bản phát hành.
- **Cấu hình pipeline:** workflow, script build, policy, manifest và cấu hình runner quyết định mã nào được thực thi với quyền gì.
- **Thành phần tái sử dụng:** reusable workflow, action, plugin, template, image build và script dùng chung có thể được nhiều repository tin cậy.

Một thay đổi ở bất kỳ vùng nào cũng có thể ảnh hưởng đến nhiều nhóm hoặc nhiều bản phát hành. Bài học này trình bày cách thiết lập bảo vệ nhánh, kiểm soát thay đổi pipeline-as-code, quản lý thành phần tái sử dụng, giới hạn quyền, cô lập mã chưa tin cậy và duy trì khả năng truy vết khi có sự cố.

## 1. Mô hình rủi ro của pipeline

Pipeline không chỉ là công cụ tự động chạy test. Nó là một hệ thống có quyền thực thi mã và truy cập tài nguyên. Những tài nguyên đó có thể gồm repository, package registry, artifact store, cloud account, môi trường triển khai, secret manager và hệ thống nội bộ.

Một đường tấn công thường bắt đầu từ một thay đổi tưởng như nhỏ:

1. Kẻ tấn công gửi pull request hoặc chiếm quyền một tài khoản phát triển.
2. Thay đổi được đưa vào workflow, script build, dependency hoặc thành phần dùng chung.
3. Pipeline chạy mã thay đổi trên runner có quyền đọc secret hoặc truy cập mạng.
4. Mã độc lấy token, sửa artifact, thay đổi package hoặc gọi API triển khai.
5. Artifact hoặc thay đổi đã bị tác động được đưa vào nhánh chính hay môi trường phát hành.

Mục tiêu của bảo mật pipeline là làm gián đoạn chuỗi này bằng nhiều lớp kiểm soát: bảo vệ nhánh, review độc lập, giới hạn quyền, xác minh thành phần, cô lập runner và phê duyệt triển khai.

~~~mermaid
flowchart TD
    A["Thay đổi mã nguồn hoặc workflow"] --> B["Pull request"]
    B --> C["Branch protection và review"]
    C --> D{"Các điều kiện bắt buộc đạt?"}
    D -- "Không" --> E["Giữ thay đổi ngoài nhánh chính"]
    D -- "Có" --> F["Merge vào nhánh chính"]
    F --> G["Pipeline được bảo vệ"]
    G --> H["Thành phần tái sử dụng đã xác minh"]
    H --> I["Job chạy với quyền tối thiểu"]
    I --> J["Artifact và bằng chứng có truy vết"]
    J --> K["Environment approval / deploy gate"]
    K --> L["Phát hành"]
~~~

Các lớp kiểm soát cần bổ trợ cho nhau. Branch protection không giúp ích nếu người review không biết workflow đã thay đổi quyền gì. Workflow an toàn cũng chưa đủ nếu nó gọi một action bên ngoài không được kiểm soát. Thành phần dùng chung được pin phiên bản vẫn cần quyền tối thiểu và review khi cập nhật.

## 2. Bảo vệ nhánh chính

Nhánh chính thường là nguồn tích hợp và phát hành. Nếu bất kỳ ai có thể push trực tiếp, force push hoặc xóa nhánh, các kiểm tra và review có thể bị bỏ qua. Branch protection hoặc ruleset giúp định nghĩa điều kiện để thay đổi được đưa vào nhánh này.

### 2.1. Yêu cầu pull request thay cho push trực tiếp

Với nhánh chính, nên yêu cầu thay đổi đi qua pull request hoặc merge request. Cách này tạo điểm kiểm soát để review nội dung, thảo luận rủi ro và xem trạng thái kiểm tra trước khi merge.

Chính sách thường bao gồm:

- Chặn push trực tiếp từ tài khoản thông thường.
- Chỉ cho phép merge qua quy trình đã định nghĩa.
- Yêu cầu một hoặc nhiều phê duyệt độc lập.
- Yêu cầu tất cả status check bắt buộc đạt.
- Yêu cầu conversation hoặc review thread cần thiết được giải quyết.
- Hạn chế force push và xóa nhánh.
- Giới hạn ai được phép bypass quy tắc.

Không nên xem việc có pull request là đủ. Nếu tác giả có thể tự phê duyệt thay đổi nhạy cảm hoặc tự bỏ qua check, quy trình vẫn có điểm yếu.

### 2.2. Số lượng và tính độc lập của review

Số lượng reviewer cần thiết phụ thuộc mức độ ảnh hưởng của repository và thay đổi. Một thư viện dùng chung, workflow phát hành hoặc script có quyền triển khai có thể cần người review thuộc nhóm sở hữu tương ứng.

Review cần độc lập với người tạo thay đổi. Với thay đổi nhạy cảm, nên yêu cầu ít nhất một người có chuyên môn hoặc ownership phù hợp. Không nên để cùng một người tạo thay đổi và tự phê duyệt ngoại lệ cho chính thay đổi đó nếu chính sách yêu cầu kiểm soát hai người.

Có thể sử dụng CODEOWNERS hoặc cơ chế ownership tương đương để yêu cầu nhóm chịu trách nhiệm review những đường dẫn cụ thể, chẳng hạn:

- Workflow CI/CD.
- Script build và deploy.
- File định nghĩa dependency hoặc plugin.
- Manifest hạ tầng và policy.
- Thành phần tái sử dụng.
- Cấu hình secret hoặc environment protection.

CODEOWNERS chỉ có giá trị khi được bảo vệ và review đúng. Nếu người gửi PR có thể sửa file ownership để loại bỏ reviewer cần thiết trong cùng thay đổi, cơ chế này có thể bị vô hiệu hóa. Hãy bảo vệ chính file định nghĩa owner và xác minh quy tắc ownership thực tế của nền tảng.

### 2.3. Bắt buộc các status check quan trọng

Required status checks là điều kiện để merge. Chúng nên bao gồm các kiểm tra có vai trò bảo vệ nhánh chung, ví dụ:

- Lint, static analysis và unit test.
- Build hoặc kiểm tra biên dịch.
- Kiểm tra bảo mật bắt buộc.
- Validation của workflow và cấu hình.
- Kiểm tra ownership hoặc policy nếu hệ thống hỗ trợ.

Tên check cần ổn định, có chủ sở hữu và được tạo bởi workflow đáng tin cậy. Cẩn thận với check name trùng nhau: nếu nhiều workflow hoặc ứng dụng có thể phát ra cùng tên check, người review có thể nhầm kết quả của một job không đúng với điều kiện bảo vệ.

Không nên biến tất cả cảnh báo thành required check. Chỉ chọn những kiểm tra có mục tiêu rõ và đủ ổn định để làm điều kiện merge. Các kiểm tra mở rộng có thể chạy sau merge hoặc trước release, nhưng không được âm thầm thay thế một kiểm tra bắt buộc đã bị lỗi.

### 2.4. Kiểm tra trên trạng thái hợp nhất mới nhất

Một pull request có thể đạt kiểm tra trên commit của nhánh nguồn nhưng thất bại khi ghép với nhánh chính đã thay đổi. Có thể yêu cầu nhánh nguồn cập nhật với nhánh đích trước khi merge, kiểm tra merge candidate hoặc dùng merge queue/merge train.

Khi nhánh đích thay đổi, kết quả kiểm tra cũ có thể không còn đại diện cho trạng thái sắp được hợp nhất. Cần chạy lại hoặc xác nhận kết quả cho đúng merge candidate. Với merge queue, pipeline cần kiểm tra chính tổ hợp thay đổi mà hệ thống dự định đưa vào nhánh chính.

### 2.5. Bảo vệ lịch sử và danh tính commit

Ngoài review và status check, có thể áp dụng:

- Chặn force push trên nhánh chính.
- Chặn xóa nhánh chính.
- Yêu cầu commit được ký hoặc xác minh danh tính theo chính sách của tổ chức.
- Hạn chế quyền quản trị có thể bypass branch protection.
- Ghi audit cho thay đổi rule, bypass và thao tác merge.

Commit signing giúp xác minh commit được ký bởi một khóa hoặc danh tính được chấp nhận. Nó không chứng minh nội dung commit an toàn, vì vậy vẫn cần review và kiểm tra tự động. Tương tự, bảo vệ lịch sử không thay thế việc kiểm tra artifact và quy trình phát hành.

## 3. Bảo vệ các file định nghĩa pipeline

Pipeline-as-code đặt workflow và cấu hình tự động hóa trong repository. Điều này giúp review và version hóa thay đổi, nhưng cũng có nghĩa một pull request có thể thay đổi chính quy tắc kiểm tra và quyền thực thi.

Các file cần được xem là thành phần nhạy cảm:

- Workflow YAML hoặc Jenkinsfile.
- Pipeline template và reusable workflow.
- Script build, test, package và deploy.
- Dockerfile, build container và runner image.
- File cấu hình action, plugin hoặc extension.
- IaC, deployment manifest và network policy.
- File khai báo permission, environment và secret reference.

### 3.1. Review thay đổi workflow như thay đổi mã có quyền

Một thay đổi workflow có thể làm cho job nhận thêm quyền, chạy trên runner khác, truy cập secret hoặc thực hiện deploy. Người review cần xem xét:

- Event nào kích hoạt workflow?
- Nhánh, tag hoặc nguồn PR nào được phép kích hoạt?
- Job nào có quyền đọc hoặc ghi repository?
- Secret nào có thể được truy cập?
- Runner có thể truy cập mạng hoặc tài nguyên nào?
- Action hoặc plugin nào được gọi?
- Artifact được tạo và publish ở đâu?
- Có thể bỏ qua gate hoặc approval không?

Không nên chỉ review phần cú pháp YAML. Hãy xem tác động thực tế của workflow và quyền mà nó tạo ra.

### 3.2. Ownership và thay đổi nhạy cảm

Có thể gắn ownership cho thư mục workflow và script triển khai. Thay đổi tại những vùng này nên yêu cầu reviewer có trách nhiệm với nền tảng CI/CD hoặc bảo mật.

Với repository lớn, có thể tách workflow dùng chung khỏi ứng dụng, nhưng cần kiểm soát quyền cập nhật và quy trình phát hành của repository chứa workflow. Nếu nhiều dự án cùng gọi một workflow, thay đổi ở workflow đó có thể ảnh hưởng diện rộng.

### 3.3. Validation trước khi merge

Nên kiểm tra cấu trúc và hành vi của workflow trước khi cho phép merge:

- Parse YAML và kiểm tra schema.
- Kiểm tra action/plugin tham chiếu có tồn tại.
- Kiểm tra permission và event trigger.
- Kiểm tra tham số đầu vào và output.
- Kiểm tra không có secret literal trong file.
- Phát hiện lệnh shell nguy hiểm hoặc quyền vượt nhu cầu.
- Chạy test cho script build và deploy.
- Review khác biệt của runner, network và environment.

Validation tự động không thay thế review con người. Nó giúp phát hiện lỗi cấu trúc và chính sách phổ biến, còn reviewer đánh giá ý nghĩa và tác động của thay đổi.

## 4. Giới hạn quyền của workflow và token

Workflow thường nhận token hoặc danh tính để đọc repository, ghi trạng thái, tải package, publish artifact hoặc gọi API. Quyền mặc định rộng làm tăng tác động khi một job bị xâm nhập.

### 4.1. Quyền tối thiểu theo job

Cấp quyền ở phạm vi nhỏ nhất có thể:

- Job chỉ checkout và test nên chủ yếu cần quyền đọc source.
- Job cập nhật check status chỉ cần quyền ghi trạng thái tương ứng.
- Job publish package cần quyền ghi đúng package namespace.
- Job deploy chỉ cần quyền triển khai vào môi trường được phép.
- Job tạo release cần quyền release riêng và có điều kiện bảo vệ.

Nếu nền tảng hỗ trợ khai báo permission ở mức workflow và job, hãy đặt mặc định tối thiểu rồi mở rộng riêng cho job thực sự cần. Không dùng một token quản trị toàn repository cho mọi bước.

### 4.2. Không truyền token qua các job không cần

Không đưa token vào output, artifact, cache hoặc file workspace để job sau sử dụng. Nếu job khác cần quyền, hãy cấp danh tính riêng cho job đó. Điều này giảm phạm vi tác động nếu một job chạy mã không tin cậy hoặc bị lộ log.

Token nên có thời hạn ngắn và scope giới hạn. Khi nền tảng hỗ trợ OIDC hoặc workload identity, ưu tiên cấp credential tạm thời theo repository, ref, environment và workflow thay vì lưu khóa cloud dài hạn trong secret.

### 4.3. Phân biệt token của nền tảng và secret ứng dụng

Token do CI cấp thường dùng để tương tác với repository hoặc API nền tảng. Secret ứng dụng có thể là database password, signing key hoặc credential của dịch vụ bên ngoài. Hai nhóm có mục đích và chính sách khác nhau.

Không cấp secret production cho job pull request từ fork hoặc nguồn chưa được tin cậy. Việc che secret trong log không bảo vệ được nếu mã độc có thể đọc giá trị trong process hoặc gửi nó qua mạng.

## 5. Xử lý pull request từ nguồn chưa tin cậy

Pull request từ fork hoặc contributor bên ngoài có thể chứa script build, test hoặc workflow thay đổi. Khi pipeline thực thi mã này, nó phải được coi là mã chưa được tin cậy.

Các biện pháp cần có:

- Dùng runner tạm thời hoặc pool riêng cho PR không tin cậy.
- Không cấp secret production hoặc credential có quyền ghi.
- Giới hạn token ở quyền đọc cần thiết.
- Chặn truy cập vào mạng quản trị và dịch vụ nội bộ.
- Không cho phép job tự publish package hoặc deploy môi trường dùng chung.
- Hủy workspace và tài nguyên tạm sau khi job kết thúc.
- Chỉ cấp quyền bổ sung sau khi review hoặc theo một cơ chế phê duyệt rõ ràng.

Một số nền tảng có event hoặc chế độ workflow chạy với ngữ cảnh của repository đích dù nội dung PR đến từ fork. Ví dụ, cần đặc biệt thận trọng với các cơ chế tương tự pull_request_target: workflow có thể có quyền của repository đích trong khi xử lý metadata hoặc nội dung do bên ngoài kiểm soát. Không checkout rồi thực thi script từ PR chưa tin cậy trong job có secret hoặc quyền ghi.

Nếu cần thực hiện thao tác tin cậy sau khi PR được review, hãy tách thành workflow hoặc job khác với điều kiện, danh tính và quyền riêng. Không dựa vào việc người dùng đã mở PR hoặc nhãn được gắn để mặc định mã nguồn đã an toàn.

## 6. Bảo vệ thành phần tái sử dụng

Reusable workflow, action, plugin, pipeline template và script dùng chung giúp giảm lặp lại và chuẩn hóa cách build/test/deploy. Nhưng chúng cũng tạo ra một chuỗi tin cậy: repository gọi thành phần bên ngoài và trao cho thành phần đó quyền chạy trong pipeline.

Nếu một thành phần dùng chung bị thay đổi hoặc bị chiếm quyền, nhiều repository có thể bị ảnh hưởng cùng lúc.

### 6.1. Pin phiên bản theo danh tính bất biến

Không nên tham chiếu thành phần bên ngoài bằng nhánh mutable như main hoặc một tag có thể bị di chuyển nếu cần mức kiểm soát cao. Hãy pin vào phiên bản cụ thể hoặc commit SHA bất biến theo chính sách của nền tảng.

Ví dụ tham chiếu action theo commit:

~~~yaml
steps:
  - name: Checkout source
    uses: actions/checkout@<COMMIT_SHA_40_HEX>
~~~

Đây là ví dụ cho GitHub Actions; placeholder cần được thay bằng SHA commit đã xác minh. Việc pin SHA giúp tránh thành phần tự thay đổi nội dung khi nhánh hoặc tag được cập nhật. Nó không tự chứng minh commit an toàn, vì vậy vẫn cần xác minh nguồn, review thay đổi và theo dõi cập nhật bảo mật.

Với nền tảng khác, hãy dùng cơ chế pin phiên bản bất biến tương đương. Nếu nền tảng chỉ hỗ trợ version tag, cần có quy trình xác minh tag, nguồn phát hành và tính bất biến của registry.

### 6.2. Kiểm tra nguồn và quyền của thành phần

Trước khi dùng action, plugin hoặc workflow bên ngoài, cần xem:

- Chủ sở hữu repository và lịch sử bảo trì.
- Mã nguồn thực thi và dependency của thành phần.
- Quyền mà thành phần yêu cầu.
- Có tải script hoặc binary từ URL động hay không.
- Có gửi dữ liệu ra ngoài hoặc thay đổi cấu hình runner không.
- Có release signature, provenance hoặc quy trình phát hành đáng tin cậy không.
- Chính sách cập nhật khi phát hiện lỗ hổng.

Ưu tiên thành phần từ nguồn chính thức hoặc nguồn nội bộ đã được tổ chức phê duyệt. Với thành phần bên thứ ba, nên có allowlist hoặc quy trình kiểm duyệt trước khi đưa vào workflow quan trọng.

### 6.3. Bọc thành phần bên ngoài bằng workflow nội bộ

Một tổ chức có thể tạo reusable workflow nội bộ để chuẩn hóa build, test, scan hoặc deploy. Workflow nội bộ giúp:

- Đặt permission mặc định tối thiểu.
- Chuẩn hóa runner và environment.
- Kiểm soát phiên bản action bên trong.
- Định nghĩa input/output được phép.
- Ghi log và metadata thống nhất.
- Cập nhật bảo mật tại một điểm có review.

Tuy nhiên, reusable workflow nội bộ cũng là thành phần có ảnh hưởng rộng. Repository chứa nó cần branch protection, reviewer ownership, test và release version riêng. Không nên cho phép caller truyền tùy ý shell command, quyền token hoặc secret rộng vào workflow dùng chung.

### 6.4. Thiết kế input và secret rõ ràng

Reusable workflow nên khai báo input có kiểu, giá trị mặc định an toàn và validation. Tránh nhận một chuỗi lệnh shell tùy ý rồi thực thi trực tiếp.

Chỉ truyền secret mà workflow thực sự cần. Tránh dùng cơ chế tương tự secrets: inherit nếu workflow chỉ cần một hoặc hai secret cụ thể, vì nó có thể mở rộng phạm vi dữ liệu nhạy cảm được chia sẻ. Không ghi secret vào output hoặc artifact.

Output của thành phần tái sử dụng cũng cần được xem là dữ liệu đầu vào chưa tin cậy nếu nó có thể chứa nội dung do mã PR kiểm soát. Khi đưa output vào shell, cần xử lý đúng cách và không ghép chuỗi tùy tiện.

## 7. Kiểm soát phiên bản và cập nhật thành phần dùng chung

Pin một phiên bản giúp ổn định nhưng không có nghĩa nên giữ mãi phiên bản cũ. Thành phần dùng chung có thể nhận bản vá bảo mật, thay đổi API hoặc sửa lỗi tương thích.

Một quy trình cập nhật tốt gồm:

1. Theo dõi release và advisory của thành phần.
2. Xác minh nguồn và phiên bản mới.
3. Xem diff từ phiên bản đang dùng đến phiên bản mới.
4. Kiểm tra thay đổi permission, network, dependency và script.
5. Cập nhật pin trong pull request.
6. Chạy validation và test trên repository đại diện.
7. Review bởi owner của pipeline.
8. Phát hành phiên bản reusable workflow nội bộ mới nếu có.
9. Theo dõi adoption và gỡ phiên bản đã lỗi thời theo kế hoạch.

Có thể dùng dependency update bot để tạo PR cập nhật action hoặc plugin, nhưng không nên tự động merge mọi thay đổi. Việc cập nhật thành phần có quyền thực thi cần review theo rủi ro.

### 7.1. Quản lý phiên bản workflow nội bộ

Reusable workflow nội bộ có thể được phát hành theo tag version hoặc commit SHA. Caller nên pin phiên bản đã được kiểm thử. Khi cần cập nhật diện rộng, có thể tạo PR hàng loạt hoặc một đợt nâng cấp có kế hoạch.

Tránh thay đổi hành vi bảo mật của workflow đang được nhiều dự án dùng mà không thông báo. Nếu phải thu hồi phiên bản có lỗ hổng, cần có quy trình khẩn cấp để xác định caller bị ảnh hưởng và thay phiên bản.

### 7.2. Không dùng floating reference cho release-critical workflow

Tham chiếu theo nhánh mặc định tiện cho thử nghiệm nhưng khiến lần chạy sau có thể thực thi mã khác mà repository caller không thay đổi. Với build và deploy quan trọng, hãy dùng phiên bản bất biến và nâng cấp qua pull request có review.

## 8. Bảo vệ runner và môi trường triển khai

Runner là nơi mã thực sự được thực thi. Nếu nhiều trust level dùng chung runner persistent, một job có thể để lại file, process hoặc credential ảnh hưởng job sau.

Nên:

- Tách runner xử lý PR không tin cậy khỏi runner release/deploy.
- Ưu tiên ephemeral runner cho job có mức tin cậy thấp hoặc quyền cao.
- Không mount Docker socket hoặc filesystem nhạy cảm cho job không cần.
- Giới hạn outbound network theo endpoint cần thiết.
- Cập nhật runner image và agent.
- Xóa workspace, token, container và volume tạm sau job.
- Theo dõi process bất thường và kết nối mạng.
- Không để runner production có quyền truy cập rộng vào mọi môi trường.

Job deploy cần quyền và network path riêng. Một job build thông thường không nên có thể gọi API production chỉ vì runner nằm trong cùng network.

### 8.1. Environment protection

Môi trường staging và production có thể có protection rule như phê duyệt thủ công, giới hạn nhánh được deploy, người được phép triển khai hoặc thời gian chờ. Những quy tắc này cần được quản lý ngoài mã nguồn PR chưa tin cậy.

Approval phải gắn với đúng artifact, commit và môi trường. Nếu artifact hoặc cấu hình thay đổi sau phê duyệt, cần đánh giá lại điều kiện phê duyệt. Không dùng một approval chung cho nhiều bản build không có cùng digest.

## 9. Bảo vệ artifact và đầu ra của pipeline

Artifact được tạo bởi pipeline có thể trở thành đầu vào của hệ thống phát hành. Cần bảo đảm nó đến từ workflow và commit được phép.

Các kiểm soát quan trọng:

- Tạo artifact từ commit đã xác định và được chấp nhận.
- Gắn pipeline run ID, commit SHA và builder identity.
- Tính digest và xác minh sau khi tải.
- Hạn chế quyền ghi registry và ngăn ghi đè phiên bản phát hành.
- Tách artifact tạm của PR với artifact phát hành.
- Tạo SBOM hoặc provenance nếu quy trình yêu cầu.
- Chỉ promote artifact đã vượt qua gate.
- Không build lại một bản khác sau khi kiểm thử rồi coi đó là cùng artifact.

Một pipeline PR không tin cậy không nên có quyền publish package chính thức. Nếu cần tạo artifact preview, hãy lưu ở namespace tạm, quyền truy cập giới hạn và retention ngắn.

## 10. Kiểm soát thay đổi policy và quyền bypass

Branch protection, ruleset, permission mặc định, runner group và environment approval đều là cấu hình bảo mật. Nếu một người có thể thay đổi chúng mà không review hoặc audit, các kiểm soát còn lại có thể bị vô hiệu hóa.

Nên xác định:

- Ai được tạo, sửa hoặc xóa branch protection/ruleset?
- Ai được thay đổi required status checks?
- Ai được thêm hoặc xóa owner của workflow?
- Ai được đăng ký runner hoặc thay đổi runner group?
- Ai được cấp quyền secret và environment?
- Ai được bypass review hoặc required checks?
- Thao tác bypass có được ghi audit và thông báo không?

Quyền quản trị nên được giới hạn cho nhóm nhỏ và sử dụng tài khoản cá nhân có xác thực mạnh. Tài khoản quản trị khẩn cấp cần được quản lý riêng, có giám sát và chỉ sử dụng khi có lý do được ghi nhận.

Nếu tổ chức cho phép bypass trong tình huống khẩn cấp, cần có quy trình hậu kiểm: ghi người thực hiện, lý do, phạm vi, artifact/commit bị ảnh hưởng và các kiểm tra phải chạy bổ sung sau đó. Bypass không nên trở thành con đường thường xuyên để hợp nhất nhanh.

## 11. Ví dụ cấu hình bảo vệ pipeline ở mức khái niệm

Ví dụ sau mô tả chính sách tổng hợp. Đây không phải cấu hình thực thi đầy đủ của một nền tảng cụ thể:

~~~yaml
repository_security:
  main_branch:
    direct_push: denied
    force_push: denied
    deletion: denied
    pull_request_required: true
    approvals:
      minimum: 2
      dismiss_stale_reviews: true
      require_code_owner_review: true
    required_checks:
      - lint
      - unit_tests
      - build
      - workflow_validation
      - security_scan
    require_up_to_date_or_merge_queue: true
    bypass:
      allowed_teams:
        - release_administrators
      audit_required: true

  pipeline:
    default_token_permissions: read_only
    job_level_permissions: true
    untrusted_pull_request:
      secrets: denied
      write_token: denied
      runner_pool: ephemeral_untrusted
      internal_network: denied
    release:
      runner_pool: isolated_release
      artifact_digest_required: true
      environment_approval: true

  reusable_components:
    external_actions:
      pin_to_immutable_revision: true
      approved_sources_only: true
      update_requires_review: true
    internal_workflows:
      code_owner_review: true
      versioned_release: true
      input_validation: true
      explicit_secret_mapping: true
~~~

Khi triển khai thực tế, ánh xạ từng mục sang branch ruleset, permission, runner group, environment protection và cơ chế reusable workflow của nền tảng. Không giả định các trường trong ví dụ là tên cấu hình chuẩn.

## 12. Xử lý khi phát hiện pipeline hoặc thành phần bị xâm phạm

Nếu nghi ngờ workflow, runner hoặc action dùng chung đã bị thay đổi trái phép, cần coi đây là sự cố chuỗi cung ứng phần mềm.

Các bước phản ứng có thể gồm:

1. Xác định repository, workflow, runner và khoảng thời gian bị ảnh hưởng.
2. Tạm dừng workflow hoặc thu hồi quyền của thành phần nghi ngờ nếu cần.
3. Thu hồi token, secret hoặc credential có thể đã bị truy cập.
4. Kiểm tra audit log của branch ruleset, workflow, runner và environment.
5. Xác định commit, artifact, package và deployment được tạo trong khoảng thời gian đó.
6. Xác minh digest, provenance và nguồn phát hành của artifact.
7. Cô lập runner nghi ngờ; tái tạo runner từ image tin cậy.
8. Khôi phục workflow hoặc thành phần dùng chung về phiên bản đã xác minh.
9. Build lại artifact từ source tin cậy nếu cần.
10. Đánh giá môi trường đã triển khai và quyết định rollback hoặc phát hành bản sạch.
11. Ghi nhận nguyên nhân gốc và cập nhật chính sách để ngăn tái diễn.

Không nên chỉ revert một commit workflow rồi tiếp tục phát hành mà chưa kiểm tra token, artifact và runner có thể đã bị tác động. Một workflow độc hại có thể đã đọc secret hoặc thay đổi package trước khi bị phát hiện.

## 13. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách giảm rủi ro |
|---|---|---|
| Cho phép push trực tiếp vào main | Bỏ qua review và status check | Bắt buộc PR và branch protection |
| Cho phép force push hoặc xóa nhánh chính | Thay đổi lịch sử, làm mất mốc đã xác minh | Chặn force push và deletion |
| Không bảo vệ workflow file | PR có thể sửa quyền và lệnh pipeline | CODEOWNERS, required review và workflow validation |
| Token mặc định có quyền ghi rộng | Job bị xâm nhập có thể sửa repository hoặc release | Permission tối thiểu ở workflow/job |
| Chạy mã fork với secret | Lộ credential hoặc truy cập tài nguyên nội bộ | Runner cô lập, không cấp secret và quyền ghi |
| Dùng action theo nhánh mutable | Nội dung thực thi thay đổi ngoài PR | Pin SHA/version bất biến và review cập nhật |
| Reusable workflow nhận shell command tùy ý | Caller có thể điều khiển hành vi workflow có quyền | Input có kiểu, validation và giới hạn command |
| Dùng secrets inherit không cần thiết | Chia sẻ nhiều secret hơn nhu cầu | Ánh xạ rõ từng secret |
| Runner persistent dùng chung mọi trust level | Rò rỉ file, process hoặc credential giữa job | Tách pool và dùng ephemeral runner |
| Artifact PR được publish như release | Đầu ra chưa tin cậy đi vào registry chính thức | Tách namespace và quyền publish |
| Bypass không audit | Không thể giải thích quyết định merge/release | Hạn chế bypass và ghi nhận bắt buộc |
| Pin phiên bản nhưng không cập nhật | Tiếp tục dùng thành phần có lỗ hổng đã biết | Theo dõi advisory và quy trình nâng cấp |

## 14. Tình huống mẫu: cập nhật action dùng chung cho pipeline phát hành

Giả sử tổ chức có nhiều repository dùng một action bên ngoài để đăng nhập cloud và triển khai ứng dụng.

1. Nhóm phát hiện phiên bản action hiện tại có thay đổi đáng ngờ hoặc một advisory bảo mật.
2. Owner của workflow xác định repository và workflow đang tham chiếu phiên bản đó.
3. Nhóm tạm dừng các job deploy phụ thuộc nếu có rủi ro thực thi mã không tin cậy.
4. Kiểm tra nguồn action, commit được tham chiếu, quyền token, network access và log của các lần chạy gần đây.
5. Thu hồi credential có khả năng bị lộ và kiểm tra các artifact đã tạo.
6. Chọn phiên bản đã xác minh hoặc thay bằng workflow nội bộ được kiểm duyệt.
7. Tạo pull request cập nhật pin SHA; CODEOWNERS yêu cầu review từ nhóm pipeline và bảo mật.
8. Workflow validation kiểm tra permission, input, output và nguồn thành phần.
9. Chạy test trên repository đại diện với runner cô lập và credential không có quyền production.
10. Sau khi phê duyệt, triển khai phiên bản mới theo kế hoạch, theo dõi các caller và ghi nhận phiên bản đã áp dụng.

Tình huống này cho thấy reusable component cần được quản lý như dependency có quyền thực thi. Việc dùng chung giúp giảm lặp lại, nhưng cũng làm tăng phạm vi ảnh hưởng nếu thành phần bị xâm phạm.

## 15. Lộ trình thực hành

Có thể áp dụng trên một repository mẫu theo các bước:

1. **Kiểm kê nhánh và quyền:** xác định nhánh chính, ai có quyền push, merge, bypass và sửa ruleset.
2. **Bật branch protection:** yêu cầu pull request, review độc lập, owner review và required checks; chặn force push và deletion.
3. **Bảo vệ workflow:** xác định file CI/CD, script build/deploy và cấu hình runner; gán owner và yêu cầu review.
4. **Validation pipeline-as-code:** thêm kiểm tra YAML/schema, permission, trigger, secret reference và action source.
5. **Giảm quyền token:** đặt mặc định read-only, mở quyền ghi ở đúng job cần thiết.
6. **Thử nghiệm PR không tin cậy:** xác nhận không có secret production, không có quyền ghi và không truy cập được mạng nội bộ.
7. **Pin thành phần tái sử dụng:** thay tham chiếu mutable bằng revision bất biến đã xác minh; thiết lập quy trình cập nhật.
8. **Tách runner:** tạo pool riêng cho PR, build, release và deploy theo trust level.
9. **Bảo vệ artifact:** tách artifact preview và release, gắn digest và chỉ cho job tin cậy publish.
10. **Kiểm tra bypass:** thử quy trình khẩn cấp trong môi trường thử nghiệm và xác nhận audit được ghi.
11. **Diễn tập sự cố:** giả lập một reusable component bị thu hồi, truy vết caller, credential, artifact và runner liên quan.

### Tiêu chí hoàn thành

Người học có thể xem bài thực hành hoàn thành khi chứng minh được:

- Thiết lập được branch protection cho nhánh chính.
- Yêu cầu review độc lập và owner review cho file pipeline nhạy cảm.
- Cấu hình required status checks và kiểm tra merge candidate.
- Bảo vệ workflow, script build/deploy và policy khỏi thay đổi không được review.
- Giới hạn token và secret theo từng job.
- Cô lập pipeline xử lý mã từ fork hoặc nguồn chưa tin cậy.
- Pin và cập nhật reusable workflow/action theo phiên bản bất biến.
- Xác minh nguồn, quyền và input/output của thành phần dùng chung.
- Bảo vệ runner, artifact và environment approval.
- Truy vết được bypass, thay đổi workflow và artifact khi có sự cố.

## Kết luận

Bảo vệ nhánh chính, cấu hình pipeline và thành phần tái sử dụng là ba lớp gắn kết trong bảo mật CI/CD. Branch protection bảo đảm thay đổi được review và kiểm tra trước khi vào nhánh chung. Pipeline-as-code cần được quản lý như mã có quyền thực thi, với ownership, validation và permission tối thiểu. Reusable workflow và action cần có nguồn tin cậy, phiên bản bất biến, input rõ ràng và quy trình cập nhật được review.

Khi kết hợp các lớp này với runner cô lập, secret ngắn hạn, artifact có digest và audit cho thao tác bypass, nhóm giảm khả năng một thay đổi hoặc dependency bị xâm phạm có thể tác động đến bản phát hành. Quan trọng hơn, mọi quyết định từ pull request đến deploy đều có thể truy vết và giải thích bằng bằng chứng cụ thể.

