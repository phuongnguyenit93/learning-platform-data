# Phân biệt mục tiêu giao phần mềm với số lượng công cụ được sử dụng

## Mục tiêu học tập

Sau bài này, người học có thể:

- Giải thích được mục tiêu cuối cùng của CI/CD và phân biệt mục tiêu đó với hoạt động cấu hình pipeline hoặc cài đặt công cụ.
- Đánh giá một luồng giao phần mềm theo tốc độ phản hồi, độ tin cậy, khả năng truy vết, an toàn và khả năng phục hồi.
- Nhận diện chi phí do quá nhiều công cụ, tích hợp rời rạc hoặc chức năng chồng lấn gây ra.
- Chọn, kết hợp hoặc loại bỏ công cụ dựa trên vấn đề thực tế và kết quả đo được.
- Thiết kế luồng từ sự kiện Git đến triển khai và xác minh sau triển khai, trong đó artifact, bí mật, môi trường và cổng chất lượng được quản lý nhất quán.

## 1. Mục tiêu của CI/CD là giao phần mềm có giá trị

CI/CD thường được giới thiệu thông qua các sản phẩm kỹ thuật dễ nhìn thấy: máy chủ chạy pipeline, tệp cấu hình pipeline, hệ thống quản lý mã nguồn, bộ kiểm thử, kho artifact, công cụ quét bảo mật, nền tảng triển khai và dashboard. Những thành phần này quan trọng, nhưng chúng chỉ là phương tiện.

Mục tiêu của CI/CD là giúp thay đổi phần mềm đi từ ý tưởng hoặc yêu cầu đến người dùng một cách **nhanh, an toàn, lặp lại được và có thể kiểm chứng**. Khi một thay đổi được đưa vào Git, đội ngũ cần biết sớm thay đổi đó có hoạt động hay không; cần tạo ra một gói phần mềm xác định được nguồn gốc; cần đưa đúng gói đó qua các môi trường; và cần phát hiện, xử lý sự cố sau khi phát hành.

Vì vậy, một pipeline chạy thành công chưa đủ để chứng minh việc giao phần mềm đã tốt. Pipeline có thể xanh nhưng artifact không thể truy ngược về commit, bản triển khai thực tế khác bản đã kiểm thử, bước phát hành vẫn phụ thuộc vào thao tác thủ công dễ sai, hoặc hệ thống không có cách xác minh và quay lui. Ngược lại, một hệ thống dùng ít công cụ vẫn có thể giao phần mềm tốt nếu nó đáp ứng đầy đủ nhu cầu của sản phẩm và đội ngũ.

Có thể diễn đạt mục tiêu bằng một câu hỏi thực tế:

> Với mỗi thay đổi được chấp nhận, đội ngũ có thể đưa một phiên bản đúng, đã được kiểm chứng và có thể truy vết đến người dùng với mức rủi ro chấp nhận được hay không?

Số lượng công cụ không trả lời được câu hỏi này. Kết quả của toàn bộ luồng giao phần mềm mới trả lời được.

## 2. Phân biệt hoạt động, đầu ra và kết quả

Khi đánh giá CI/CD, cần tách ba cấp độ thường bị nhầm lẫn:

| Cấp độ | Câu hỏi | Ví dụ |
|---|---|---|
| Hoạt động | Đội ngũ đã làm gì? | Tạo pipeline, thêm job, cấu hình runner, tích hợp công cụ quét mã |
| Đầu ra trực tiếp | Hệ thống tạo ra thứ gì? | Kết quả kiểm thử, báo cáo quét, artifact, bản triển khai |
| Kết quả giao phần mềm | Người dùng và đội ngũ nhận được lợi ích gì? | Thay đổi được phát hành đúng, thời gian chờ giảm, lỗi được phát hiện sớm, có thể khôi phục nhanh |

Một nhóm có thể hoàn thành nhiều hoạt động và tạo ra nhiều đầu ra nhưng kết quả vẫn kém. Chẳng hạn, pipeline có hàng chục job và tích hợp nhiều hệ thống nhưng phải chờ một bước phê duyệt không rõ trách nhiệm. Thời gian từ lúc hợp nhất mã đến lúc người dùng nhận được thay đổi vẫn dài.

Cũng cần phân biệt **triển khai** với **phát hành giá trị**. Triển khai là đưa phiên bản phần mềm vào một môi trường. Phát hành là làm cho chức năng hoặc thay đổi sẵn sàng đến người dùng theo chính sách của sản phẩm. Một dịch vụ có thể được triển khai trước nhưng chỉ bật tính năng sau bằng feature flag; một bản triển khai có thể bị dừng lại nếu kiểm tra sức khỏe không đạt. CI/CD cần hỗ trợ cả hai khái niệm này thay vì xem thao tác deploy là đích đến duy nhất.

## 3. Những kết quả cần hướng tới trong một hệ thống CI/CD

Một hệ thống CI/CD phù hợp thường phục vụ nhiều kết quả cùng lúc. Mức ưu tiên cụ thể phụ thuộc vào loại sản phẩm, mức độ quan trọng của dịch vụ, yêu cầu tuân thủ và khả năng vận hành của đội ngũ.

### 3.1. Phản hồi sớm và giảm thời gian chờ

Khi lập trình viên tạo pull request hoặc đẩy commit, hệ thống nên nhanh chóng cung cấp bằng chứng về chất lượng thay đổi. Lỗi cú pháp, lỗi định dạng, kiểm thử đơn vị thất bại hoặc vi phạm quy tắc bảo mật cơ bản nên được phát hiện trước khi thay đổi đi sâu vào quy trình phát hành.

Phản hồi sớm giúp giảm chi phí sửa lỗi vì người tạo thay đổi vẫn còn nhớ rõ ý định và phạm vi chỉnh sửa. Nếu pipeline mất quá lâu, đội ngũ có thể tìm cách bỏ qua kiểm tra, gom nhiều thay đổi vào một lần hoặc chờ kết quả đến mức làm gián đoạn công việc.

Tuy nhiên, tốc độ không đồng nghĩa với việc bỏ bớt kiểm tra quan trọng. Cách tốt hơn là phân tầng kiểm tra: chạy những kiểm tra nhanh và có giá trị cao trước; chạy các kiểm tra tốn thời gian hơn ở giai đoạn phù hợp; đồng thời tránh chạy lại cùng một tác vụ không cần thiết.

### 3.2. Tính lặp lại và khả năng tái tạo

Cùng một nguồn mã, cấu hình và bộ phụ thuộc cần tạo ra kết quả có thể giải thích và tái tạo. Nếu hai lần build từ cùng một commit tạo ra các gói khác nhau mà không có nguyên nhân được kiểm soát, đội ngũ khó xác định chính xác thứ đã được kiểm thử và phát hành.

Tính lặp lại được hỗ trợ bởi việc khóa phiên bản phụ thuộc, kiểm soát cấu hình build, chuẩn hóa môi trường thực thi, ghi nhận phiên bản công cụ cần thiết và lưu thông tin nguồn gốc của artifact. Cache có thể giúp tăng tốc, nhưng không được làm kết quả build phụ thuộc vào trạng thái cũ không thể kiểm soát.

### 3.3. Chất lượng và an toàn có bằng chứng

Cổng chất lượng cần phản ánh rủi ro thực tế. Tùy hệ thống, bằng chứng có thể gồm kiểm thử đơn vị, kiểm thử tích hợp, kiểm thử hợp đồng API, phân tích tĩnh, quét lỗ hổng phụ thuộc, kiểm tra image container hoặc kiểm thử hiệu năng.

Một cổng chất lượng hữu ích phải có tiêu chí rõ ràng, kết quả có thể xem lại và cách xử lý khi thất bại. Nếu một bước kiểm tra thường xuyên báo lỗi giả hoặc không liên quan đến rủi ro của sản phẩm, người dùng sẽ mất niềm tin và tìm cách né tránh nó. Ngược lại, một kiểm tra quan trọng bị bỏ qua chỉ vì pipeline cần chạy nhanh có thể làm tăng rủi ro phát hành.

### 3.4. Artifact có danh tính và nguồn gốc rõ ràng

Artifact là gói đầu ra được đưa qua các bước kiểm thử và triển khai, chẳng hạn tệp thực thi, package, image container hoặc gói frontend. Mỗi artifact cần gắn được với commit, phiên bản build, cấu hình liên quan và các bằng chứng kiểm tra.

Một nguyên tắc quan trọng là **build một lần, promote cùng một artifact qua các môi trường**. Nếu môi trường staging và production tự build lại từ cùng nhánh mã, hai gói đầu ra có thể khác nhau do phụ thuộc, thời điểm hoặc cấu hình build. Khi đó, kết quả kiểm thử staging không còn chứng minh trực tiếp cho gói đang chạy ở production.

Việc lưu digest hoặc mã định danh bất biến của artifact giúp xác nhận gói nào đã được kiểm thử, phê duyệt và triển khai. Khi có sự cố, đội ngũ có thể xác định phiên bản đang chạy và đối chiếu nó với nguồn mã.

### 3.5. Triển khai có kiểm soát và phù hợp với môi trường

Pipeline cần quản lý sự khác biệt giữa môi trường phát triển, kiểm thử, staging và production. Cấu hình môi trường có thể khác nhau, nhưng sự khác biệt phải được khai báo và kiểm soát. Bí mật như token, mật khẩu và khóa ký phải được cấp qua cơ chế quản lý bí mật phù hợp, giới hạn quyền truy cập và tránh xuất hiện trong log hoặc artifact.

Một luồng triển khai tốt cũng xác định ai hoặc điều kiện nào được phép đưa phiên bản đến production. Với dịch vụ có rủi ro cao, có thể cần phê duyệt, triển khai theo từng nhóm người dùng, canary hoặc blue-green. Với dịch vụ nhỏ và rủi ro thấp, tự động hóa hoàn toàn có thể phù hợp hơn. Mức kiểm soát nên tương xứng với tác động của lỗi.

### 3.6. Xác minh sau triển khai và khả năng phục hồi

Pipeline không nên kết thúc ngay khi lệnh deploy trả về thành công. Hệ thống cần xác minh phiên bản mới thực sự hoạt động thông qua smoke test, kiểm tra endpoint, chỉ số sức khỏe, log hoặc tín hiệu nghiệp vụ phù hợp.

Nếu phiên bản mới làm hệ thống suy giảm, đội ngũ cần biết điều kiện nào kích hoạt dừng phát hành, quay lui hoặc chuyển lưu lượng về phiên bản trước. Quay lui chỉ khả thi khi artifact cũ còn được lưu, cấu hình và dữ liệu tương thích, quy trình được diễn tập và quyền thực hiện được xác định.

Khả năng phục hồi là một phần của chất lượng giao phần mềm. Một hệ thống phát hành nhanh nhưng không thể phát hiện hoặc khắc phục sự cố có thể gây thiệt hại lớn hơn hệ thống phát hành chậm hơn một chút nhưng kiểm soát rủi ro tốt.

## 4. Vì sao số lượng công cụ là thước đo sai

Đếm công cụ là cách đo dễ thực hiện nhưng không phản ánh chất lượng của luồng giao phần mềm. Có ít nhất năm lý do.

**Thứ nhất, công cụ không cho biết vấn đề đã được giải quyết hay chưa.** Một công cụ kiểm thử có thể được cài đặt nhưng chỉ chạy trên một phần mã nguồn. Một công cụ quét bảo mật có thể tạo báo cáo nhưng không có người xử lý phát hiện. Sự hiện diện của công cụ không chứng minh năng lực đã được vận hành.

**Thứ hai, số lượng không thể hiện mức độ tích hợp.** Nhiều công cụ có thể hoạt động như một hệ thống thống nhất nếu chúng trao đổi dữ liệu và tự động chuyển giao artifact, trạng thái, danh tính người dùng và bằng chứng. Ngược lại, chỉ vài công cụ cũng có thể tạo ra nhiều điểm bàn giao thủ công và lỗi đồng bộ.

**Thứ ba, số lượng không thể hiện nút thắt.** Pipeline có thể hoàn thành build và test rất nhanh nhưng chờ môi trường, người phê duyệt hoặc quy trình thay đổi cơ sở dữ liệu. Thêm một công cụ build khác không giải quyết được nút thắt đó.

**Thứ tư, số lượng không thể hiện chi phí vận hành.** Mỗi công cụ có thể cần giấy phép, tài khoản, quyền truy cập, nâng cấp, giám sát, sao lưu, đào tạo và xử lý sự cố. Các chi phí này tăng lên khi công cụ có chức năng chồng lấn hoặc không có người chịu trách nhiệm.

**Thứ năm, số lượng không phản ánh rủi ro.** Mỗi tích hợp mới có thể tạo thêm thông tin xác thực, quyền truy cập, webhook, dữ liệu được sao chép và điểm cần bảo vệ. Một hệ thống có nhiều công cụ nhưng không quản lý tốt danh tính và bí mật có thể mở rộng bề mặt tấn công.

Điều này không có nghĩa là càng ít công cụ càng tốt. Một nền tảng duy nhất có thể không đáp ứng tốt mọi nhu cầu về build, bảo mật, quản lý artifact, triển khai và quan sát. Dùng nhiều công cụ chuyên biệt có thể hợp lý nếu mỗi công cụ giải quyết một nhu cầu rõ ràng và được tích hợp có kiểm soát.

Mục tiêu là **tối ưu kết quả và tổng chi phí của toàn bộ hệ thống**, không tối thiểu hóa một con số riêng lẻ.

## 5. Nhìn CI/CD như một luồng giao giá trị đầu cuối

Thay vì bắt đầu bằng câu hỏi “nên dùng công cụ nào?”, hãy mô tả luồng thay đổi từ Git đến người dùng. Một luồng tham chiếu có thể như sau:

~~~mermaid
flowchart TD
    A["Sự kiện Git: commit / pull request"] --> B["Kiểm tra nhanh: lint, phân tích tĩnh"]
    B --> C["Kiểm thử tự động"]
    C --> D["Build và đóng gói"]
    D --> E["Artifact bất biến + thông tin nguồn gốc"]
    E --> F["Triển khai staging"]
    F --> G["Kiểm thử và xác minh"]
    G --> H{"Đạt cổng chất lượng?"}
    H -- "Không" --> I["Thông báo, điều tra và sửa lỗi"]
    I --> A
    H -- "Có" --> J["Phê duyệt hoặc chính sách phát hành"]
    J --> K["Triển khai production"]
    K --> L["Xác minh sức khỏe và tín hiệu người dùng"]
    L --> M{"Hoạt động ổn định?"}
    M -- "Không" --> N["Dừng phát hành / quay lui / khắc phục"]
    M -- "Có" --> O["Ghi nhận phiên bản và hoàn tất phát hành"]
~~~

Sơ đồ thể hiện các năng lực cần có, không quy định mỗi ô phải là một công cụ riêng. Một nền tảng có thể thực hiện nhiều bước; một bước cũng có thể cần nhiều thành phần phối hợp. Điều cần quan tâm là dữ liệu và trách nhiệm có được chuyển tiếp đầy đủ hay không.

Ở mỗi điểm bàn giao, hãy đặt các câu hỏi:

- Đầu vào của bước này là gì và đến từ đâu?
- Kết quả có được lưu lại và gắn với commit hoặc artifact không?
- Nếu bước thất bại, ai nhận được thông tin và có thể hành động như thế nào?
- Bước này có thực sự giảm rủi ro hoặc thời gian chờ không?
- Có công đoạn nào phải nhập lại dữ liệu, tải lên thủ công hoặc chạy lại cùng một việc không?
- Bí mật và quyền truy cập được cấp theo nguyên tắc tối thiểu cần thiết chưa?

Các câu hỏi này giúp phát hiện vấn đề của luồng thay vì chỉ kiểm kê danh sách sản phẩm.

## 6. Ví dụ: hai đội có số lượng công cụ khác nhau

Giả sử hai đội cùng phát triển một dịch vụ API. Các con số dưới đây chỉ là tình huống minh họa.

| Khía cạnh | Đội A: nhiều công cụ, tích hợp yếu | Đội B: ít công cụ hơn, tích hợp rõ |
|---|---|---|
| Kiểm thử | Kết quả nằm ở nhiều hệ thống, phải mở từng nơi để xem | Pipeline tổng hợp trạng thái và liên kết đến bằng chứng |
| Artifact | Build riêng cho staging và production | Build một lần, promote cùng artifact |
| Bí mật | Nhiều token cấu hình thủ công ở từng job | Dùng cơ chế quản lý bí mật và quyền theo môi trường |
| Phát hành | Chuyển file và xác nhận qua nhiều bước thủ công | Triển khai tự động theo chính sách đã khai báo |
| Xác minh | Chỉ kiểm tra lệnh deploy có trả về thành công | Chạy smoke test và theo dõi sức khỏe sau triển khai |
| Sự cố | Khó biết phiên bản nào đang chạy và gói nào cần khôi phục | Tra được phiên bản, artifact và quy trình quay lui |

Đội A có thể sử dụng nhiều sản phẩm chuyên biệt, nhưng việc bàn giao rời rạc khiến kỹ sư phải tự kết nối dữ liệu. Đội B có thể dùng một nền tảng CI/CD cùng kho artifact và dịch vụ quan sát, miễn là các năng lực cần thiết đều được đáp ứng.

Không thể kết luận đội B tốt hơn chỉ vì dùng ít công cụ. Nếu sản phẩm của đội B cần kiểm thử bảo mật chuyên sâu mà nền tảng hiện tại không hỗ trợ, bổ sung một công cụ chuyên biệt là quyết định hợp lý. Tương tự, nếu đội A có yêu cầu tuân thủ khiến từng hệ thống phải được tách riêng, nhiều công cụ có thể là lựa chọn cần thiết. Phép so sánh phải dựa trên bằng chứng về kết quả, rủi ro và chi phí.

## 7. Cách quyết định có nên thêm hoặc thay một công cụ

Một quyết định tốt bắt đầu từ vấn đề đang tồn tại. Quy trình sau giúp tránh mua hoặc tích hợp công cụ chỉ vì xu hướng.

### Bước 1: Xác định kết quả cần cải thiện

Mô tả vấn đề bằng tình huống quan sát được. Ví dụ:

- Pull request phải chờ quá lâu mới có kết quả kiểm thử.
- Không xác định được artifact production được tạo từ commit nào.
- Mỗi môi trường tự build nên không chứng minh được gói đã kiểm thử chính là gói phát hành.
- Bí mật được sao chép vào nhiều cấu hình pipeline.
- Sau triển khai không có tín hiệu đủ tin cậy để quyết định tiếp tục hay quay lui.

Tránh mô tả vấn đề bằng tên sản phẩm, chẳng hạn “đội cần cài thêm nền tảng X”. Tên công cụ là một phương án, chưa phải bằng chứng về nhu cầu.

### Bước 2: Tìm nút thắt trong luồng hiện tại

Vẽ các bước từ commit đến production, ghi thời gian chờ, thời gian xử lý, lần thất bại, điểm bàn giao và thao tác thủ công. Xác định nơi làm chậm toàn bộ luồng hoặc tạo ra rủi ro lớn nhất.

Nếu thời gian chờ chủ yếu nằm ở việc cấp môi trường, thay công cụ build sẽ không giải quyết nguyên nhân. Nếu vấn đề là thiếu bằng chứng nguồn gốc artifact, thêm dashboard tổng quát cũng không thay thế được metadata và cơ chế truy vết.

### Bước 3: Xác định năng lực cần có

Viết yêu cầu theo năng lực, không theo tên nhà cung cấp. Ví dụ: “Mỗi artifact phải có mã định danh bất biến, liên kết tới commit và kết quả kiểm tra; cùng artifact đó phải được promote qua staging và production.”

Một yêu cầu như vậy giúp so sánh được nhiều phương án: cấu hình lại nền tảng hiện tại, bổ sung một dịch vụ chuyên biệt hoặc thay đổi cách tổ chức pipeline.

### Bước 4: So sánh lợi ích với tổng chi phí

Đánh giá ít nhất các khía cạnh sau:

| Tiêu chí | Câu hỏi đánh giá |
|---|---|
| Kết quả | Công cụ cải thiện chỉ số hoặc giảm rủi ro cụ thể nào? |
| Tích hợp | Có trao đổi được trạng thái, artifact và danh tính với hệ thống hiện có không? |
| Vận hành | Ai cập nhật, giám sát, xử lý sự cố và hỗ trợ người dùng? |
| Bảo mật | Quyền truy cập, dữ liệu và bí mật được quản lý thế nào? |
| Độ tin cậy | Khi công cụ hoặc dịch vụ phụ thuộc bị lỗi, luồng giao phần mềm bị ảnh hưởng ra sao? |
| Chi phí | Có chi phí giấy phép, hạ tầng, đào tạo và bảo trì nào? |
| Khả năng thay thế | Có thể xuất dữ liệu, chuyển cấu hình hoặc rời công cụ khi cần không? |

Đừng chỉ so sánh giá giấy phép. Một công cụ miễn phí nhưng cần nhiều giờ bảo trì mỗi tuần có thể tốn kém hơn dịch vụ trả phí được quản lý tốt. Ngược lại, một nền tảng đắt tiền có thể không đáng đầu tư nếu phần lớn năng lực của nó không được sử dụng.

### Bước 5: Thử nghiệm trong phạm vi nhỏ và đo lại

Chọn một dịch vụ hoặc luồng đại diện. Ghi nhận đường cơ sở trước khi thay đổi, triển khai thử, quan sát kết quả và hỏi người trực tiếp sử dụng. Nếu công cụ mới không cải thiện kết quả hoặc tạo thêm gánh nặng lớn hơn lợi ích, hãy điều chỉnh hoặc dừng thử nghiệm.

Sau khi công cụ được chấp nhận, cần xác định chủ sở hữu, quy tắc vận hành, quyền truy cập, cách xử lý khi dịch vụ ngừng hoạt động và cách loại bỏ chức năng cũ. Công cụ không có người chịu trách nhiệm sẽ nhanh chóng trở thành một phần nợ vận hành.

## 8. Đo kết quả thay vì đếm công cụ

Các chỉ số cần phản ánh cả tốc độ và độ ổn định. Có thể sử dụng bốn nhóm chỉ số thường được gọi là DORA metrics:

- **Deployment frequency – Tần suất triển khai:** hệ thống đưa thay đổi vào môi trường production thường xuyên đến mức nào.
- **Lead time for changes – Thời gian từ thay đổi đến triển khai:** một thay đổi cần bao lâu để đi từ lúc được đưa vào luồng chính đến khi được triển khai.
- **Change failure rate – Tỷ lệ triển khai gây lỗi:** tỷ lệ triển khai dẫn đến suy giảm dịch vụ, rollback, hotfix hoặc biện pháp khắc phục khẩn cấp theo định nghĩa của đội ngũ.
- **Time to restore service – Thời gian khôi phục dịch vụ:** cần bao lâu để khôi phục dịch vụ sau một sự cố liên quan đến thay đổi.

Các chỉ số này nên được xem theo xu hướng và theo bối cảnh của từng dịch vụ. Không nên đặt mục tiêu tăng tần suất triển khai bằng mọi giá nếu điều đó làm tỷ lệ lỗi tăng mạnh. Cũng không nên giảm tỷ lệ lỗi bằng cách trì hoãn mọi thay đổi đến mức người dùng phải chờ lâu.

Có thể bổ sung các chỉ số vận hành trực tiếp cho pipeline:

| Nhóm | Chỉ số gợi ý | Ý nghĩa |
|---|---|---|
| Phản hồi | Thời gian từ commit đến kết quả kiểm tra đầu tiên | Người phát triển biết vấn đề sớm đến đâu |
| Hiệu suất | Thời gian chờ runner, thời gian build và thời gian kiểm thử | Xác định nút thắt cụ thể |
| Chất lượng | Tỷ lệ job thất bại do lỗi thực, tỷ lệ cảnh báo sai | Đánh giá độ hữu ích của cổng chất lượng |
| Truy vết | Tỷ lệ artifact liên kết được với commit và lần triển khai | Xác nhận nguồn gốc của phần mềm |
| Phát hành | Tỷ lệ triển khai cần thao tác thủ công ngoài chính sách | Đánh giá mức tự động hóa thực tế |
| Phục hồi | Thời gian phát hiện và khôi phục sau triển khai lỗi | Đánh giá khả năng kiểm soát sự cố |
| Bảo mật | Số lần phát hiện bí mật bị lộ hoặc quyền vượt mức cần thiết | Theo dõi rủi ro của chuỗi giao phần mềm |

Mỗi chỉ số cần có định nghĩa, nguồn dữ liệu, phạm vi đo và người chịu trách nhiệm. Nếu hai đội định nghĩa “triển khai thất bại” khác nhau, so sánh số liệu giữa họ có thể dẫn đến kết luận sai.

Đặc biệt, tránh dùng số lượng pipeline, số job, số tích hợp hoặc số công cụ như chỉ tiêu thành tích. Chúng có thể hữu ích cho kiểm kê và quản trị, nhưng không phải bằng chứng trực tiếp về giá trị mà người dùng nhận được.

## 9. Những dấu hiệu cho thấy đội ngũ đang tối ưu công cụ thay vì tối ưu giao phần mềm

Một số dấu hiệu thường gặp:

- Đội ngũ thường xuyên thảo luận nên chuyển sang công cụ mới, nhưng không thống nhất được vấn đề nào trong luồng hiện tại cần giải quyết.
- Cùng một loại kiểm tra được chạy ở nhiều nơi mà không có lý do về độ tin cậy hoặc phân lớp rủi ro.
- Pipeline có nhiều job nhưng kết quả không được tổng hợp thành một trạng thái dễ hiểu và có thể hành động.
- Artifact được tạo lại ở từng môi trường, khiến không thể chứng minh gói đã kiểm thử là gói đang chạy.
- Việc phát hành phụ thuộc vào người nhớ chạy một lệnh hoặc sao chép một tệp.
- Dashboard có nhiều biểu đồ nhưng không chỉ ra ai cần làm gì khi một ngưỡng bị vượt.
- Token và quyền truy cập được tạo riêng lẻ cho từng tích hợp, không có quy tắc thu hồi và rà soát.
- Khi triển khai lỗi, đội ngũ không biết phiên bản trước ở đâu hoặc chưa từng diễn tập quay lui.

Khi gặp các dấu hiệu này, nên quay lại luồng đầu cuối, xác định điểm gây chậm hoặc rủi ro, rồi giải quyết đúng điểm đó. Đôi khi giải pháp là thêm công cụ; đôi khi là tích hợp lại, tự động hóa một bước, loại bỏ thao tác thừa hoặc làm rõ trách nhiệm.

## 10. Ví dụ về một pipeline được thiết kế theo kết quả

Dưới đây là mô hình logic minh họa cho một dịch vụ. Đây không phải cú pháp của một nền tảng CI/CD cụ thể:

~~~yaml
pipeline:
  trigger:
    - pull_request
    - push_to_main

  validate:
    steps:
      - checkout_source
      - lint_and_static_analysis
      - unit_tests
      - dependency_and_secret_checks

  package:
    requires: validate_passed
    steps:
      - build_once
      - create_immutable_artifact
      - attach_commit_and_build_metadata
      - publish_artifact

  staging:
    requires: artifact_published
    steps:
      - deploy_the_published_artifact
      - run_integration_and_smoke_tests
      - record_verification_results

  production:
    requires:
      - staging_passed
      - release_policy_satisfied
    steps:
      - deploy_the_same_artifact
      - verify_health_and_user_signals
      - stop_or_rollback_if_thresholds_fail
      - record_release_identity
~~~

Mỗi nhóm bước có một mục đích rõ ràng:

- Validate cung cấp phản hồi và bằng chứng chất lượng trước khi phát hành.
- Package tạo artifact có danh tính và thông tin nguồn gốc.
- Staging kiểm tra artifact trong môi trường gần với điều kiện vận hành.
- Production chỉ nhận artifact đã vượt qua các điều kiện cần thiết, sau đó tiếp tục được xác minh.

Có thể triển khai mô hình này bằng một nền tảng duy nhất hoặc bằng nhiều hệ thống. Dù chọn cách nào, luồng vẫn phải giữ được liên kết giữa commit, kết quả kiểm tra, artifact và lần triển khai. Nếu nền tảng không thể biểu diễn một yêu cầu quan trọng, đội ngũ có thể bổ sung thành phần chuyên biệt và xác định rõ cách trao đổi dữ liệu với phần còn lại.

## 11. Nguyên tắc thực hành

Khi thiết kế hoặc cải tiến CI/CD, hãy giữ các nguyên tắc sau:

1. **Bắt đầu từ người dùng và dịch vụ.** Xác định thay đổi cần đến người dùng với mức độ tin cậy nào, thay vì bắt đầu từ danh sách công cụ muốn cài.
2. **Tối ưu toàn bộ luồng.** Một bước nhanh hơn không có nhiều ý nghĩa nếu nút thắt tiếp theo vẫn giữ nguyên.
3. **Giữ bằng chứng xuyên suốt.** Commit, kiểm thử, artifact, phê duyệt và triển khai phải liên kết được với nhau.
4. **Build một lần, promote cùng artifact.** Tránh tạo ra các gói khác nhau cho từng môi trường mà không có lý do được kiểm soát.
5. **Đặt cổng chất lượng theo rủi ro.** Mỗi cổng cần có tiêu chí rõ, chủ sở hữu và hành động khi thất bại.
6. **Bảo vệ bí mật và quyền truy cập.** Tự động hóa không được trở thành lý do để cấp quyền rộng hoặc lưu token ở nơi không an toàn.
7. **Xác minh sau triển khai.** Thành công của lệnh deploy chưa chứng minh dịch vụ đang phục vụ người dùng tốt.
8. **Chuẩn bị khả năng quay lui.** Biết artifact nào cần khôi phục, ai có quyền thực hiện và cách xác minh sau khi khôi phục.
9. **Tính cả chi phí vận hành.** Công cụ cần được nâng cấp, giám sát, bảo vệ và có người chịu trách nhiệm.
10. **Đo kết quả và cải tiến liên tục.** Dùng dữ liệu để tìm nút thắt, thử thay đổi nhỏ và xác nhận tác động.

## 12. Tình huống tự đánh giá

Một nhóm phát triển dịch vụ thanh toán đã tích hợp thêm ba công cụ vào pipeline trong quý vừa qua. Số lượng job tăng đáng kể, báo cáo kiểm tra cũng nhiều hơn. Tuy vậy, thời gian từ khi merge đến khi phát hành không giảm. Khi xảy ra lỗi production, nhóm mất nhiều thời gian để xác định artifact được triển khai và chưa có quy trình quay lui đã diễn tập.

Hãy phân tích tình huống bằng các câu hỏi:

1. Những hoạt động và đầu ra nào đã tăng? Kết quả giao phần mềm nào chưa cải thiện?
2. Nút thắt có thể nằm ở đâu trong luồng từ Git đến production?
3. Cần bổ sung bằng chứng nào để truy vết artifact từ commit đến lần triển khai?
4. Cần xác minh điều gì sau triển khai để phát hiện suy giảm dịch vụ?
5. Có thể dùng chỉ số nào để đánh giá thời gian phát hành, tỷ lệ triển khai gây lỗi và thời gian khôi phục?
6. Với mỗi công cụ mới, nhóm cần chứng minh năng lực cụ thể nào và chi phí vận hành nào?

Một câu trả lời tốt không mặc định rằng nhóm phải xóa công cụ hoặc mua thêm công cụ. Câu trả lời cần xác định nguyên nhân, kết quả mong muốn, bằng chứng cần thu thập và thay đổi nhỏ nhất có thể kiểm chứng.

## Kết luận

CI/CD là năng lực tổ chức việc giao phần mềm, từ sự kiện Git đến build, kiểm thử, quản lý artifact, triển khai, xác minh và phục hồi. Công cụ giúp hiện thực hóa năng lực đó, nhưng số lượng công cụ không nói lên việc người dùng nhận được phần mềm tốt hơn hay đội ngũ kiểm soát phát hành tốt hơn.

Một hệ thống CI/CD trưởng thành tạo ra phản hồi sớm, kết quả có thể lặp lại, artifact truy vết được, cổng chất lượng phù hợp, bí mật được bảo vệ và quy trình xác minh, quay lui có thể thực hiện. Hãy chọn công cụ sau khi đã hiểu mục tiêu, nút thắt và chi phí của luồng giao phần mềm; sau đó đánh giá quyết định bằng kết quả thực tế.

