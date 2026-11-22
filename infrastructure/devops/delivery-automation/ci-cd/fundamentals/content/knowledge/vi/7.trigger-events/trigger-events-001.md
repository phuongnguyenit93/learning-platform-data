# Kích hoạt theo push, pull request, nhãn phiên bản và lịch định kỳ

Trigger là quy tắc xác định khi nào một pipeline CI/CD bắt đầu chạy. Chọn đúng sự kiện kích hoạt giúp nhóm kiểm tra thay đổi đúng thời điểm, sử dụng tài nguyên hợp lý và kiểm soát ai hoặc thay đổi nào có thể đưa quy trình đến bước phát hành.

Bốn nhóm sự kiện thường gặp là push, pull request, nhãn phiên bản và lịch định kỳ. Push phản ánh commit mới được gửi lên repository. Pull request mở ra một điểm kiểm soát trước khi thay đổi được hợp nhất. Nhãn phiên bản, thường là Git tag, đánh dấu một mốc mã nguồn có ý nghĩa phát hành. Lịch định kỳ kích hoạt các công việc không phụ thuộc trực tiếp vào một commit mới, chẳng hạn quét bảo mật, kiểm tra tương thích hoặc tổng hợp tình trạng pipeline.

Các sự kiện này có thể cùng tồn tại trong một hệ thống CI/CD, nhưng không nên tự động thực hiện cùng một công việc. Pipeline cần phân biệt mục tiêu, phạm vi mã nguồn, quyền truy cập, điều kiện chạy và tác động của từng trigger. Bài học này giải thích cách thiết kế các trigger trên, tránh chạy trùng hoặc bỏ sót sự kiện, bảo vệ bí mật và giữ khả năng truy vết từ sự kiện đến kết quả.

## 1. Trigger trong kiến trúc CI/CD

Một trigger là tín hiệu khởi đầu workflow hoặc pipeline. Nền tảng CI/CD nhận sự kiện từ Git, lịch chạy hoặc thao tác được cho phép, sau đó đánh giá bộ lọc và điều kiện để quyết định có tạo lần chạy hay không.

Cần phân biệt ba khái niệm:

- **Event (sự kiện):** điều gì đã xảy ra, ví dụ commit được push hoặc pull request được mở.
- **Filter (bộ lọc):** giới hạn sự kiện nào được quan tâm, ví dụ chỉ push lên nhánh chính hoặc chỉ thay đổi trong thư mục dịch vụ API.
- **Condition (điều kiện):** quyết định một job hoặc bước có được thực hiện trong lần chạy đó hay không, ví dụ chỉ publish artifact khi sự kiện là push lên nhánh phát hành.

Sơ đồ khái quát:

~~~mermaid
flowchart TD
    A["Git / lịch / thao tác người dùng"] --> B["Sự kiện được nền tảng nhận"]
    B --> C["Đánh giá event filter"]
    C --> D{"Có khớp bộ lọc?"}
    D -- "Không" --> E["Không tạo pipeline run"]
    D -- "Có" --> F["Tạo pipeline run"]
    F --> G["Đánh giá job conditions"]
    G --> H["Chạy các job phù hợp"]
    H --> I["Lưu kết quả, log và metadata"]
    I --> J["Cập nhật trạng thái / thông báo"]
~~~

Ví dụ, một lần push lên nhánh tính năng có thể kích hoạt lint và unit test. Cùng một commit khi được hợp nhất vào nhánh chính có thể kích hoạt thêm integration test và đóng gói artifact. Một tag phiên bản có thể kích hoạt quy trình kiểm tra release candidate và chuẩn bị phát hành. Một lịch chạy ban đêm có thể quét toàn bộ dependency hoặc chạy kiểm thử hồi quy.

Trigger xác định thời điểm bắt đầu; các stage bên trong pipeline xác định công việc thực hiện. Không nên đưa toàn bộ quyết định nghiệp vụ vào điều kiện trigger phức tạp đến mức khó review. Hãy giữ bộ lọc sự kiện dễ hiểu và dùng điều kiện job cho các quyết định phụ thuộc vào dữ liệu của lần chạy.

## 2. Kích hoạt theo push

Push event xảy ra khi một hoặc nhiều commit được gửi lên một ref của repository, thường là nhánh hoặc tag. Đây là trigger phổ biến để xác minh mã nguồn sau mỗi lần cập nhật.

### 2.1. Khi nào dùng push trigger?

Push có thể phục vụ nhiều mục tiêu:

- Kiểm tra nhanh trên nhánh tính năng để phát hiện lỗi ngay sau khi commit được gửi.
- Xác minh nhánh dùng chung sau khi merge.
- Build và đóng gói artifact từ commit đã được chấp nhận.
- Cập nhật tài liệu, website preview hoặc môi trường tích hợp.
- Kích hoạt quy trình phát hành khi push một tag phiên bản, nếu nền tảng hỗ trợ sự kiện tag riêng hoặc push filter.

Một repository có thể giới hạn push trigger vào một số nhánh:

| Nhánh | Mục tiêu thường gặp | Công việc phù hợp |
|---|---|---|
| Nhánh tính năng | Phản hồi sớm cho tác giả | Lint, unit test, build bị ảnh hưởng |
| Nhánh tích hợp | Xác nhận trạng thái kết hợp | Integration test và regression chọn lọc |
| Nhánh chính | Xác nhận nguồn phát hành | Build, test sâu, tạo artifact |
| Nhánh bảo trì | Kiểm tra bản vá cho phiên bản đang hỗ trợ | Test tương thích và build phiên bản bảo trì |

Không phải mọi push đều cần quyền triển khai. Một push từ nhánh tính năng có thể chạy test trong môi trường tạm, trong khi deploy đến môi trường dùng chung chỉ được phép từ nhánh đã bảo vệ và sau khi các cổng bắt buộc đạt.

### 2.2. Bộ lọc nhánh và đường dẫn

Bộ lọc nhánh giới hạn pipeline vào những nhánh phù hợp. Bộ lọc đường dẫn giới hạn lần chạy khi có file trong một vùng nhất định thay đổi.

Ví dụ về chính sách ở mức khái niệm:

~~~yaml
push:
  branches:
    - main
    - release/*
  paths:
    - services/orders/**
    - shared/contracts/**
~~~

Ví dụ này có nghĩa là quan tâm đến push trên nhánh chính hoặc nhánh release, đồng thời giới hạn phạm vi thay đổi vào các đường dẫn được nêu. Cú pháp và cách kết hợp branch filter với path filter khác nhau theo nền tảng CI/CD; cần xác nhận chính xác logic AND/OR trong tài liệu nền tảng đang sử dụng.

Path filter hữu ích với monorepo, nhưng có thể bỏ sót ảnh hưởng gián tiếp. Một thay đổi trong thư viện dùng chung có thể ảnh hưởng nhiều dịch vụ; thay đổi build script, dependency lockfile hoặc pipeline có thể ảnh hưởng toàn repository. Vì vậy, cần có quy tắc fallback để chạy kiểm tra rộng khi thay đổi không thể phân loại an toàn.

### 2.3. Push nhiều commit và chạy trùng

Một push có thể chứa nhiều commit. Pipeline thường kiểm tra trạng thái cuối cùng của ref tại thời điểm sự kiện được xử lý, nhưng chi tiết phụ thuộc nền tảng. Nếu nhiều push liên tiếp xảy ra, có thể có nhiều lần chạy cùng cạnh tranh tài nguyên.

Các biện pháp kiểm soát:

- Dùng concurrency group theo repository, nhánh hoặc pull request khi phù hợp.
- Hủy lần chạy cũ khi commit mới thay thế đầu vào và kết quả cũ không còn giá trị.
- Giữ lại lần chạy phục vụ phát hành hoặc điều tra, không hủy chỉ vì có push mới.
- Đảm bảo job deploy không thể để một lần chạy cũ ghi đè phiên bản mới hơn.
- Gắn kết quả với commit SHA cụ thể thay vì chỉ ghi tên nhánh.

Hủy job cũ giúp tiết kiệm tài nguyên nhưng cần thiết kế cẩn thận. Một lần chạy đang triển khai hoặc đang thực hiện migration có thể không an toàn để dừng giữa chừng. Cần phân biệt job kiểm tra có thể hủy với thao tác thay đổi trạng thái môi trường cần cơ chế khóa và xử lý hoàn tất.

## 3. Kích hoạt theo pull request

Pull request (PR), hoặc merge request trên một số nền tảng, là đề xuất hợp nhất thay đổi từ nhánh nguồn vào nhánh đích. PR trigger giúp tự động hóa kiểm tra trước khi thay đổi đi vào nhánh dùng chung.

### 3.1. Các thời điểm thường kích hoạt

Một pipeline PR có thể chạy khi:

- PR được mở lần đầu.
- PR nhận commit mới hoặc được cập nhật.
- PR được mở lại sau khi đóng.
- Nhãn hoặc metadata của PR thay đổi.
- Có thao tác đồng bộ với nhánh đích.
- PR được đưa vào merge queue hoặc merge train.

Không phải nền tảng nào cũng coi mọi thay đổi metadata là một sự kiện PR giống nhau. Hãy chọn đúng loại sự kiện cần thiết để tránh chạy lại test khi chỉ có thay đổi không ảnh hưởng đến mã nguồn.

### 3.2. Mục tiêu của PR pipeline

PR pipeline thường thực hiện:

- Format, lint và static analysis.
- Unit test và build candidate.
- Component hoặc integration test có mục tiêu.
- Kiểm tra hợp đồng API, schema hoặc cấu hình.
- Kiểm tra secret, license và dependency theo chính sách.
- Tạo preview hoặc môi trường tạm nếu sản phẩm cần review trực quan.

Kết quả phải được gắn với đúng PR và commit. Người review cần biết check nào bắt buộc, check nào chỉ mang tính thông tin và lý do một job bị bỏ qua.

### 3.3. Kiểm tra commit hay kết quả hợp nhất dự kiến?

Có hai loại đầu vào thường gặp:

- **Head commit:** commit mới nhất trên nhánh nguồn của PR.
- **Merge candidate:** kết quả giả lập khi ghép nhánh nguồn với nhánh đích hiện tại.

Kiểm tra head commit xác nhận thay đổi của tác giả trong trạng thái riêng của nhánh nguồn. Tuy nhiên, nếu nhánh đích đã thay đổi, head commit có thể không phản ánh kết quả hợp nhất sắp tới. Merge candidate giúp phát hiện lỗi do kết hợp thay đổi trước khi merge.

Với repository có nhiều PR đồng thời, merge queue hoặc merge train có thể kiểm tra một tổ hợp thay đổi theo thứ tự dự kiến. Điều quan trọng là trạng thái đã kiểm tra phải tương ứng với commit thực sự được hợp nhất. Nếu nhánh đích hoặc PR thay đổi sau khi kiểm tra, kết quả cũ có thể không còn hợp lệ.

### 3.4. PR từ fork và mã nguồn chưa tin cậy

PR từ fork có thể chứa mã hoặc script do người ngoài repository kiểm soát. Một bước build/test có thể thực thi mã đó. Vì vậy:

- Không cấp secret production cho job xử lý PR từ fork hoặc nguồn chưa tin cậy.
- Giới hạn quyền ghi token của workflow.
- Không cho phép job PR tự ý publish package hoặc deploy môi trường dùng chung.
- Tách runner và dữ liệu kiểm thử khỏi môi trường nhạy cảm.
- Chỉ cấp quyền bổ sung sau khi có review hoặc một cơ chế tin cậy được tổ chức phê duyệt.
- Không giả định rằng che secret trong log sẽ bảo vệ được secret nếu mã độc có thể đọc biến môi trường.

PR pipeline nên được thiết kế theo nguyên tắc quyền tối thiểu. Nhu cầu chạy test không đồng nghĩa với quyền truy cập mọi tài nguyên mà pipeline phát hành đang có.

## 4. Kích hoạt theo nhãn phiên bản (Git tag)

Git tag đánh dấu một commit cụ thể. Nhãn phiên bản như v1.4.0 hoặc v2.0.0 thường được dùng để xác định mốc phát hành. Khi một tag được tạo và push lên remote, nền tảng CI/CD có thể kích hoạt release pipeline.

### 4.1. Tag khác branch như thế nào?

Branch là ref có thể di chuyển khi có commit mới. Tag thường được dùng để đánh dấu một commit cụ thể và được kỳ vọng giữ nguyên sau khi phát hành.

| Đặc điểm | Branch | Tag phiên bản |
|---|---|---|
| Ý nghĩa | Dòng phát triển tiếp tục thay đổi | Mốc mã nguồn có danh tính phiên bản |
| Vị trí trỏ đến | Thay đổi khi có commit mới | Thường cố định sau khi tạo |
| Trigger phổ biến | Push, pull request | Push tag hoặc release event |
| Mục tiêu | Tích hợp và phát triển | Build, xác minh và phát hành phiên bản |
| Quy tắc quản trị | Bảo vệ nhánh, review, merge | Giới hạn quyền tạo, sửa hoặc xóa tag |

Tag có thể là lightweight tag hoặc annotated tag. Annotated tag chứa metadata như người tạo, thời điểm và thông điệp, phù hợp hơn khi cần đánh dấu bản phát hành có chủ đích. Dù dùng loại nào, cần bảo vệ quy trình tạo tag để tránh tag phát hành bị di chuyển hoặc thay thế ngoài ý muốn.

### 4.2. Tag version kích hoạt release pipeline

Một tag phiên bản có thể kích hoạt các bước:

1. Xác định commit mà tag trỏ tới.
2. Kiểm tra tên tag theo quy tắc phiên bản của dự án.
3. Xác nhận commit nằm trên nhánh hoặc mốc phát hành được phép.
4. Chạy build và bộ kiểm thử cần thiết.
5. Tạo artifact và metadata phát hành.
6. Tính digest, ký artifact hoặc tạo provenance nếu quy trình yêu cầu.
7. Publish vào registry hoặc kho phát hành.
8. Chờ phê duyệt và triển khai theo chính sách môi trường.
9. Ghi nhận kết quả, phiên bản và liên kết đến pipeline run.

Ví dụ quy tắc tag theo Semantic Versioning có thể là vMAJOR.MINOR.PATCH, chẳng hạn v2.3.1. Số MAJOR biểu thị thay đổi không tương thích theo chính sách API của dự án; MINOR biểu thị tính năng tương thích ngược; PATCH biểu thị sửa lỗi tương thích ngược. Dự án có thể có quy ước riêng, nhưng cần kiểm tra định dạng nhất quán.

### 4.3. Không để tên tag quyết định mù quáng artifact

Tag là tên dễ đọc, còn commit SHA và artifact digest giúp xác định nội dung cụ thể. Release pipeline cần ghi lại cả ba:

- Tên tag, ví dụ v2.3.1.
- Commit SHA mà tag trỏ tới.
- Digest của artifact được tạo từ commit đó.

Nếu tag bị xóa và tạo lại trỏ đến commit khác, cùng một tên phiên bản có thể đại diện cho nội dung khác nhau. Với registry hỗ trợ immutable tag hoặc chính sách bảo vệ release, hãy bật cơ chế ngăn ghi đè. Nếu phát hiện tag bị di chuyển, phải xử lý như một vấn đề quản trị phát hành.

### 4.4. Tách tag phát hành và tag thử nghiệm

Một repository có thể dùng nhiều quy ước:

- Tag release ổn định: v2.3.1.
- Tag pre-release: v2.4.0-rc.1 hoặc v2.4.0-beta.2.
- Tag build thử nghiệm: theo quy tắc nội bộ riêng.

Pipeline phải phân biệt các loại này. Pre-release có thể được publish vào registry hoặc môi trường thử nghiệm riêng; nó không nên tự động được coi là bản production ổn định nếu chưa qua release gate.

## 5. Kích hoạt theo lịch định kỳ

Scheduled trigger chạy workflow theo lịch, thường dùng biểu thức cron hoặc cơ chế lập lịch của nền tảng. Nó phù hợp với công việc không cần chờ một sự kiện Git mới.

Ví dụ:

- Quét dependency và lỗ hổng đã biết mỗi đêm.
- Chạy full regression trên nhánh chính.
- Kiểm thử tương thích nhiều phiên bản runtime.
- Kiểm thử tải hoặc soak test theo tuần.
- Kiểm tra drift của cấu hình hoặc tài liệu.
- Tổng hợp thời gian build, flaky test và tình trạng pipeline.
- Dọn dẹp artifact hoặc môi trường tạm theo chính sách.

### 5.1. Lịch cron và múi giờ

Cron thường mô tả phút, giờ, ngày trong tháng, tháng và ngày trong tuần. Ví dụ:

~~~cron
0 2 * * 1-5
~~~

Biểu thức này biểu thị 02:00 từ thứ Hai đến thứ Sáu theo múi giờ mà nền tảng sử dụng. Nhiều nền tảng CI/CD diễn giải lịch theo UTC, trong khi một số nền tảng có cấu hình timezone riêng. Cần kiểm tra tài liệu của nền tảng để tránh chạy sai giờ, đặc biệt khi nhóm làm việc ở nhiều múi giờ hoặc có thay đổi giờ mùa hè.

Không nên giả định lịch cron luôn chạy chính xác đến từng giây hoặc không bao giờ bị trễ. Nền tảng có thể trì hoãn job khi quá tải hoặc giới hạn số lần chạy. Nếu công việc có deadline nghiêm ngặt, cần cơ chế giám sát lần chạy cuối và cảnh báo khi lịch bị bỏ lỡ.

### 5.2. Scheduled workflow cần xác định ref

Một scheduled workflow thường chạy trên một nhánh hoặc ref mặc định theo cấu hình nền tảng. Cần xác định rõ:

- Chạy trên nhánh chính hay nhánh bảo trì?
- Có cần chạy trên mọi nhánh đang được hỗ trợ không?
- Kết quả có gắn với commit SHA tại thời điểm bắt đầu không?
- Nếu nhánh thay đổi trong lúc job chạy, đầu vào có còn nhất quán không?
- Có nên hủy lần chạy trước nếu lịch mới đến khi lần cũ chưa kết thúc?

Ghi lại commit SHA khi bắt đầu giúp kết quả có thể truy vết. Nếu lịch chạy full test cho nhiều nhánh, nên đặt ma trận và giới hạn concurrency để tránh chiếm hết runner.

### 5.3. Idempotency và chồng lấn lịch

Scheduled job có thể chạy lại sau lỗi hoặc bị khởi động trùng bởi thao tác thủ công. Job nên có tính idempotent khi có thể: chạy nhiều lần với cùng đầu vào không tạo trạng thái sai hoặc tác dụng phụ ngoài dự kiến.

Ví dụ, một job tổng hợp báo cáo nên ghi nhận kỳ báo cáo và cập nhật cùng một bản ghi thay vì tạo vô hạn bản sao. Job dọn dẹp chỉ xóa tài nguyên đã hết hạn theo nhãn hoặc metadata rõ ràng. Job kiểm thử tải cần giới hạn một lần chạy trên một môi trường để không làm sai kết quả.

## 6. Kết hợp nhiều trigger mà không chạy lặp

Một workflow có thể lắng nghe cả push và pull request. Tuy nhiên, cùng một thay đổi có thể tạo ra nhiều lần chạy: PR được cập nhật, commit được push lên nhánh nguồn và sau đó merge vào nhánh đích.

Việc chạy lặp không phải lúc nào cũng sai. Một lần chạy kiểm tra PR và một lần chạy xác minh nhánh chính có mục tiêu khác nhau. Vấn đề xuất hiện khi các lần chạy trùng lặp thực hiện cùng một công việc tốn tài nguyên hoặc cùng triển khai vào một môi trường.

Một số cách tổ chức:

- Dùng workflow hoặc job riêng cho PR validation, branch integration và release.
- Dùng điều kiện job để chỉ chạy publish khi sự kiện đến từ nhánh hoặc tag được phép.
- Dùng concurrency group theo PR hoặc ref để hạn chế nhiều lần chạy cùng phạm vi.
- Hủy các lần chạy kiểm tra cũ khi có commit mới, nếu kết quả cũ không còn giá trị.
- Đảm bảo thao tác deploy có khóa môi trường hoặc cơ chế tuần tự hóa.
- Không tái sử dụng kết quả kiểm tra nếu commit, cấu hình, dependency hoặc môi trường đầu vào đã thay đổi.

Bảng định hướng:

| Trigger | Công việc chính | Quyền thường cần |
|---|---|---|
| Push nhánh tính năng | Kiểm tra nhanh, build candidate | Đọc repository, ghi kết quả check nếu cần |
| Pull request | Review checks, test thay đổi và merge candidate | Quyền tối thiểu, không có secret production |
| Push nhánh chính | Full validation, build và publish artifact theo chính sách | Quyền ghi registry có giới hạn |
| Push version tag | Xác minh và tạo release | Quyền release/publish được bảo vệ |
| Scheduled | Scan, regression, performance hoặc báo cáo | Quyền đọc và quyền môi trường chuyên biệt theo job |

## 7. Thiết kế bộ lọc và điều kiện an toàn

Một trigger rõ ràng nên khai báo:

1. Event nào được lắng nghe?
2. Ref hoặc nhánh nào được chấp nhận?
3. Có path filter hay tag pattern không?
4. Điều kiện nào cho phép từng job chạy?
5. Job nào được phép truy cập secret?
6. Job nào được phép publish hoặc deploy?
7. Cách xử lý khi có nhiều lần chạy đồng thời?

Không nên dùng một điều kiện chung cho cả workflow nếu từng job có quyền và mục đích khác nhau. Ví dụ, PR có thể chạy test nhưng job publish package chỉ chạy khi có push lên nhánh chính hoặc tag được bảo vệ.

Ví dụ logic khái niệm:

~~~yaml
workflow:
  triggers:
    - pull_request
    - push_to_main
    - version_tag
    - scheduled_scan

  jobs:
    validate:
      runs_on:
        - pull_request
        - push_to_main
        - version_tag

    publish:
      condition:
        event_is: version_tag
        tag_matches: "v*"
        release_checks_pass: true

    scheduled_security_scan:
      condition:
        event_is: scheduled_scan
~~~

Đây là mô hình minh họa, không phải cú pháp nền tảng cụ thể. Khi chuyển sang GitHub Actions, GitLab CI, Jenkins hoặc hệ thống khác, phải dùng đúng tên event, filter và expression của nền tảng đó.

### 7.1. Thận trọng với path filter

Path filter có thể tiết kiệm tài nguyên nhưng cũng có thể tạo ra khoảng trống kiểm tra. Một số tình huống cần chú ý:

- Thay đổi file dùng chung ảnh hưởng nhiều service.
- Thay đổi dependency lockfile ảnh hưởng build toàn dự án.
- Thay đổi pipeline hoặc script build làm thay đổi cách mọi job hoạt động.
- File bị xóa hoặc đổi tên khiến bộ lọc chỉ kiểm tra đường dẫn mới.
- Pull request có nhiều commit với thay đổi ở nhiều vùng.
- Nền tảng giới hạn số file hoặc số commit được dùng để đánh giá filter.

Khi không thể xác định phạm vi chính xác, hãy chạy bộ kiểm tra rộng theo chính sách. Trạng thái bỏ qua phải được giải thích, không được hiển thị như thể test đã chạy và đạt.

### 7.2. Thận trọng với tag filter

Tag pattern cần đủ chặt để không kích hoạt release pipeline cho tag thử nghiệm hoặc tên không hợp lệ. Ví dụ, mẫu v* có thể khớp cả tag v-next hoặc v2.0.0-rc.1. Nếu chỉ muốn phát hành ổn định, cần kiểm tra định dạng phiên bản và điều kiện pre-release trong job.

Ngoài pattern, cần xác minh tag được tạo từ commit hợp lệ, người tạo có quyền và tag không bị di chuyển theo chính sách repository.

## 8. Bảo vệ quyền và bí mật theo loại sự kiện

Mỗi trigger có mức độ tin cậy khác nhau. Một PR từ fork, một push từ nhánh được bảo vệ và một tag release không nên mặc định có cùng quyền.

Nguyên tắc cần áp dụng:

- **Quyền tối thiểu:** chỉ cấp quyền đọc, ghi, publish hoặc deploy mà job thực sự cần.
- **Phân tách secret:** test không cần secret production; release job chỉ nhận secret sau khi điều kiện bảo vệ đạt.
- **Runner phù hợp:** mã chưa tin cậy chạy trên runner cô lập, không dùng chung môi trường có credential nhạy cảm.
- **Thông tin xác thực ngắn hạn:** ưu tiên token hoặc danh tính tạm thời khi nền tảng hỗ trợ.
- **Bảo vệ nhánh và tag:** giới hạn ai được merge nhánh chính, tạo tag release hoặc phê duyệt deploy.
- **Kiểm soát log:** tránh in token, biến môi trường nhạy cảm hoặc thông tin xác thực ra log.
- **Phê duyệt môi trường:** dùng approval hoặc protection rule cho môi trường cần kiểm soát.

Một trigger được kích hoạt không đồng nghĩa job có quyền thực hiện mọi hành động. Quyền phải được cấp tại phạm vi job hoặc bước cụ thể. Điều này đặc biệt quan trọng khi cùng một workflow xử lý cả PR không tin cậy và release chính thức.

## 9. Đảm bảo lần chạy có thể truy vết

Mỗi pipeline run nên ghi lại metadata để người vận hành có thể giải thích vì sao nó chạy và nó đã kiểm tra điều gì.

Thông tin hữu ích gồm:

| Metadata | Mục đích |
|---|---|
| Event name | Biết trigger là push, PR, tag hay schedule |
| Event timestamp | Biết thời điểm nền tảng nhận sự kiện |
| Repository và ref | Xác định nguồn thay đổi |
| Commit SHA | Xác định mã nguồn chính xác |
| PR number và base/head SHA | Truy lại thay đổi và nhánh đích |
| Tag name và target SHA | Xác định mốc phát hành |
| Schedule identifier | Biết lần chạy định kỳ thuộc lịch nào |
| Workflow version | Biết cấu hình pipeline nào đã thực thi |
| Actor hoặc initiator | Truy lại tác nhân kích hoạt theo chính sách quyền riêng tư |
| Job result và artifact digest | Nối kết quả kiểm tra với đầu ra |

Với release, chuỗi truy vết nên nối được tag, commit SHA, pipeline run, test report, artifact digest, người hoặc chính sách phê duyệt và môi trường đích. Với scheduled scan, cần ghi lại commit hoặc phiên bản dependency được quét, thời điểm, phạm vi và kết quả.

Nếu một lần chạy bị bỏ qua do filter, cũng nên có cách giải thích lý do trong trạng thái hoặc log của hệ thống. Điều này giúp phân biệt không có thay đổi phù hợp với lỗi cấu hình trigger.

## 10. Tình huống mẫu: từ pull request đến tag phát hành

Giả sử nhóm phát triển một dịch vụ API và muốn phát hành phiên bản 2.3.1.

1. Nhà phát triển push commit lên nhánh tính năng. Push trigger chạy lint, unit test và build candidate.
2. Nhà phát triển mở pull request. PR trigger chạy lại các check bắt buộc trên commit hoặc merge candidate, đồng thời hiển thị kết quả cho người review.
3. PR được cập nhật. Lần chạy cũ có thể bị hủy nếu chỉ kiểm tra commit đã lỗi thời; lần chạy mới gắn với head SHA hiện tại.
4. PR đạt các điều kiện và được merge vào nhánh chính. Push trigger trên nhánh chính chạy integration test, regression chọn lọc và tạo artifact.
5. Artifact được lưu với commit SHA, pipeline run ID và digest. Nó có thể được triển khai lên môi trường test để xác minh.
6. Khi nhóm quyết định phát hành, người có quyền tạo và push tag v2.3.1 lên commit đã được xác minh.
7. Tag trigger chạy release pipeline: kiểm tra định dạng tag, xác nhận target commit, xác minh artifact hoặc tạo artifact theo chính sách, kiểm tra provenance và chờ phê duyệt nếu cần.
8. Artifact được publish hoặc promote đến môi trường đích. Pipeline xác nhận phiên bản đang chạy và lưu kết quả.
9. Scheduled workflow tiếp tục quét dependency, chạy regression và theo dõi tình trạng hệ thống sau phát hành.

Tình huống này minh họa rằng mỗi trigger có một vai trò riêng. Push hỗ trợ vòng lặp phát triển và xác nhận nhánh chung; PR kiểm soát việc hợp nhất; tag đánh dấu bản phát hành; lịch định kỳ duy trì kiểm tra liên tục sau khi thay đổi đã được tích hợp hoặc phát hành.

## 11. Các lỗi thường gặp khi thiết kế trigger

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Push không kích hoạt pipeline | Nhánh không khớp filter, workflow không được nhận diện hoặc quyền webhook sai | Kiểm tra ref, cấu hình workflow và lịch sử sự kiện |
| PR không có check | Sai loại PR event, filter đường dẫn loại bỏ lần chạy hoặc workflow không có quyền cập nhật check | Kiểm tra event, filter và quyền |
| Merge xong không có pipeline nhánh chính | Bộ lọc push không khớp nhánh đích hoặc cơ chế merge không tạo event như dự kiến | Kiểm tra sự kiện thực tế và cấu hình branch |
| Release chạy nhầm tag | Pattern quá rộng hoặc thiếu kiểm tra định dạng phiên bản | Xác thực tag và phân biệt pre-release |
| Cùng thay đổi chạy nhiều pipeline | Push và PR cùng kích hoạt hoặc nhiều event tương đương | Phân tách job, dùng concurrency và điều kiện |
| Lịch chạy sai giờ | Nhầm timezone hoặc cron không được nền tảng hỗ trợ như dự kiến | Kiểm tra timezone, cú pháp và lịch thực tế |
| Lịch chạy chồng lấn | Job lâu hơn chu kỳ hoặc không có concurrency limit | Đặt giới hạn đồng thời và xử lý idempotent |
| Pipeline PR đọc được secret nhạy cảm | Quyền workflow quá rộng hoặc runner dùng chung | Giảm quyền, tách runner và bảo vệ secret |
| Tag bị thay đổi sau phát hành | Không bảo vệ tag hoặc registry cho phép ghi đè | Dùng tag protection và immutable artifact |
| Job bị bỏ qua nhưng không ai biết | Filter hoặc condition không có trạng thái giải thích | Ghi rõ lý do skip và có fallback |

Khi điều tra, hãy bắt đầu từ sự kiện thực tế mà nền tảng nhận được, sau đó kiểm tra filter, điều kiện job và quyền truy cập. Không nên chỉ xem log của job vì job có thể chưa từng được tạo nếu trigger hoặc filter không khớp.

## 12. Lộ trình thực hành

Có thể thực hành trên repository mẫu theo các bước:

1. **Tạo push workflow:** kích hoạt trên nhánh tính năng và nhánh chính, chạy lint, unit test và build.
2. **Tạo PR workflow:** chạy các check bắt buộc khi PR được mở hoặc cập nhật; gắn trạng thái với commit và merge candidate nếu nền tảng hỗ trợ.
3. **Thử path filter:** thay đổi một module và xác nhận chỉ các test liên quan được chọn; sau đó thử thay đổi file dùng chung để kiểm tra fallback.
4. **Tạo tag phát hành thử:** tạo tag theo định dạng phiên bản, xác nhận pipeline kiểm tra target commit và metadata.
5. **Tạo scheduled workflow:** chạy một tác vụ scan hoặc regression theo cron; xác nhận timezone và ref đầu vào.
6. **Kiểm tra chạy trùng:** push liên tiếp nhiều commit và quan sát concurrency, cancellation và trạng thái deploy.
7. **Kiểm tra bảo mật:** dùng PR từ fork hoặc nguồn chưa tin cậy trong môi trường an toàn để xác nhận không có secret production và quyền ghi ngoài dự kiến.
8. **Kiểm tra truy vết:** từ một release, tìm được event, tag, commit SHA, pipeline run, artifact digest và kết quả xác minh.

### Tiêu chí hoàn thành

Người học có thể xem bài thực hành hoàn thành khi chứng minh được:

- Phân biệt được event, filter và condition.
- Thiết kế được push trigger cho nhánh phù hợp.
- Thiết kế được PR trigger và giải thích khác biệt giữa head commit với merge candidate.
- Kích hoạt release pipeline theo tag phiên bản và xác minh target commit.
- Tạo scheduled workflow với timezone và ref được xác định rõ.
- Kiểm soát path filter, tag filter và fallback khi phạm vi không rõ.
- Ngăn chạy trùng hoặc thao tác deploy đồng thời gây ghi đè.
- Giới hạn secret và quyền theo mức độ tin cậy của sự kiện.
- Truy vết được mỗi lần chạy về sự kiện và commit đầu vào.

## Kết luận

Push, pull request, tag phiên bản và lịch định kỳ là bốn nhóm trigger quan trọng trong một hệ thống CI/CD. Push hỗ trợ kiểm tra khi mã nguồn thay đổi; pull request tạo cổng đánh giá trước khi hợp nhất; tag đánh dấu mốc phát hành có chủ đích; scheduled trigger duy trì các kiểm tra không phụ thuộc vào một commit mới.

Thiết kế trigger đáng tin cậy cần kết hợp event, filter và condition rõ ràng, quản lý concurrency, xác định ref đầu vào, bảo vệ quyền theo nguồn sự kiện và lưu metadata đủ để truy vết. Khi mỗi trigger có mục tiêu và quyền hạn phù hợp, pipeline chạy đúng việc, đúng thời điểm và tạo được bằng chứng đáng tin cậy cho toàn bộ luồng phát hành.

