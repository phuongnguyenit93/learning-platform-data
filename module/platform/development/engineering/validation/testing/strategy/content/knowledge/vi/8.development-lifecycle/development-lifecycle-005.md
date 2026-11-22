# Phối hợp kiểm thử trong nhóm Agile và chu trình DevOps

## 1. Chất lượng là trách nhiệm chung trong suốt vòng đời phát triển

Trong cách làm truyền thống, kiểm thử đôi khi được thực hiện chủ yếu sau khi nhóm phát triển hoàn tất chức năng. Cách tổ chức này tạo ra một điểm bàn giao lớn: yêu cầu được chuyển cho phát triển, sản phẩm được chuyển cho kiểm thử, rồi kết quả mới quay lại nhóm phát triển. Lỗi thường được phát hiện muộn, khi việc sửa đổi đã ảnh hưởng đến nhiều thành phần hoặc lịch phát hành.

Agile và DevOps khuyến khích nhóm nhận phản hồi sớm, phối hợp liên tục và đưa chất lượng vào công việc hằng ngày. Điều đó không có nghĩa là bỏ vai trò chuyên môn của kiểm thử. Nhóm vẫn cần người có kỹ năng phân tích rủi ro, thiết kế kiểm thử, kiểm thử khám phá, tự động hóa, bảo mật, hiệu năng và đánh giá trải nghiệm. Điểm thay đổi là các kỹ năng này được phối hợp với sản phẩm, phát triển và vận hành ngay từ đầu thay vì chỉ xuất hiện ở cuối quy trình.

Trong phạm vi **VALIDATION_TESTING_STRATEGY**, phối hợp kiểm thử trong nhóm Agile và chu trình DevOps giúp liên kết mục tiêu chất lượng với kế hoạch phát triển, pipeline tích hợp và triển khai liên tục, cũng như dữ liệu vận hành sau phát hành. Mục tiêu là tạo phản hồi đủ nhanh và đáng tin cậy để nhóm có thể quyết định dựa trên rủi ro ở từng giai đoạn.

Một nhóm có thể tự động hóa nhiều kiểm thử nhưng vẫn phối hợp kém nếu yêu cầu không rõ, môi trường không ổn định, lỗi không có người xử lý hoặc vận hành không được tham gia thiết kế. Ngược lại, một nhóm phối hợp tốt có thể kết hợp kiểm thử tự động, kiểm thử thủ công có mục tiêu và giám sát để duy trì chất lượng mà không biến mọi thay đổi thành một chuỗi bàn giao kéo dài.

## 2. Hiểu đúng Agile, DevOps và vai trò của kiểm thử

### 2.1. Agile là cách tổ chức công việc theo vòng lặp phản hồi

Agile là tập hợp các giá trị và nguyên tắc hướng đến việc cung cấp giá trị sớm, hợp tác với khách hàng, thích ứng với thay đổi và thường xuyên cải tiến. Scrum, Kanban và các phương pháp khác là những cách tổ chức công việc có thể hỗ trợ các nguyên tắc đó.

Trong một nhóm Agile, kiểm thử cần xuất hiện trong quá trình làm rõ nhu cầu, lập kế hoạch, thực hiện và đánh giá kết quả. Nhóm không nên chờ đến cuối sprint mới bắt đầu xác nhận các câu chuyện đã hoàn thành. Việc kiểm thử sớm giúp phát hiện hiểu nhầm về tiêu chí chấp nhận, dữ liệu, ngoại lệ và rủi ro trước khi chúng trở thành chi phí sửa lỗi lớn.

Agile không quy định mọi nhóm phải phát hành sản phẩm vào cuối mỗi sprint. Nhóm có thể hoàn thành phần việc trong sprint nhưng triển khai theo lịch hoặc theo điều kiện phát hành. Dù nhịp phát hành thế nào, trạng thái chất lượng của phần việc phải minh bạch và có bằng chứng phù hợp.

### 2.2. DevOps kết nối phát triển, triển khai và vận hành

DevOps là cách làm nhấn mạnh sự hợp tác giữa phát triển và vận hành, tự động hóa dòng chảy thay đổi, quan sát hệ thống và học từ môi trường thật. CI (Continuous Integration) khuyến khích tích hợp thay đổi thường xuyên vào nhánh chung với kiểm tra tự động. Continuous Delivery duy trì khả năng đưa phần mềm qua các bước kiểm chứng để sẵn sàng phát hành; Continuous Deployment có thể tự động đưa thay đổi đạt điều kiện vào sản xuất.

Không phải tổ chức nào cũng triển khai Continuous Deployment. Các yêu cầu phê duyệt, nghĩa vụ tuân thủ, mức rủi ro và lịch vận hành có thể cần các cổng quyết định bổ sung. Dù mức tự động hóa khác nhau, nguyên tắc quan trọng là kết quả kiểm thử, thông tin phiên bản và trạng thái triển khai phải được truy vết rõ.

DevOps cũng không đồng nghĩa với việc chỉ mua công cụ CI/CD. Nếu nhóm vẫn tối ưu riêng lẻ, đẩy lỗi qua nhóm khác hoặc không phản hồi từ sự cố, công cụ không tự tạo ra văn hóa phối hợp. Kiểm thử giúp DevOps bằng cách cung cấp bằng chứng nhanh, phát hiện rủi ro và xác nhận khả năng vận hành của thay đổi.

### 2.3. Continuous Testing là kiểm chứng xuyên suốt dòng chảy

Continuous Testing là việc tổ chức hoạt động kiểm chứng liên tục tại những điểm phù hợp trong vòng đời phát triển và phát hành. Các kiểm thử được chọn theo rủi ro và mục tiêu, có thể chạy khi tạo pull request, sau khi tích hợp, trước khi triển khai, trong quá trình triển khai và sau khi phát hành.

Không cần chạy mọi kiểm thử trong mọi bước. Kiểm thử nhanh và ổn định nên cung cấp phản hồi sớm; kiểm thử tốn thời gian hoặc cần môi trường chuyên biệt có thể chạy theo lịch, trước cổng phát hành hoặc sau khi triển khai lên môi trường phù hợp. Điều quan trọng là nhóm biết kiểm thử nào chạy ở đâu, rủi ro nào được bao phủ và bằng chứng nào còn thiếu.

## 3. Trách nhiệm và cách phối hợp trong nhóm liên chức năng

Chất lượng là trách nhiệm của cả nhóm, nhưng trách nhiệm chung không có nghĩa là trách nhiệm cá nhân trở nên mơ hồ. Cần thống nhất ai cung cấp thông tin, ai thực hiện kiểm tra, ai duy trì công cụ và ai có thẩm quyền quyết định.

| Vai trò | Đóng góp vào chất lượng và kiểm thử |
|---|---|
| Product Owner hoặc người phụ trách sản phẩm | Làm rõ giá trị, ưu tiên backlog, xác định tiêu chí chấp nhận và quyết định phạm vi nghiệp vụ |
| Nhà phân tích nghiệp vụ/đại diện người dùng | Cung cấp quy tắc, ví dụ, luồng ngoại lệ và xác nhận kết quả theo nhu cầu thực tế |
| Developer | Thiết kế có khả năng kiểm thử, viết kiểm thử đơn vị/thành phần, rà soát mã, sửa lỗi và hỗ trợ chẩn đoán |
| Tester/QA engineer | Phân tích rủi ro, thiết kế chiến lược và kịch bản kiểm thử, kiểm thử khám phá, đánh giá bằng chứng và cải thiện khả năng kiểm thử |
| Automation engineer/SDET | Xây dựng và duy trì hạ tầng, thư viện, dữ liệu và kiểm thử tự động phù hợp với kiến trúc |
| Architect/technical lead | Định hướng kiến trúc, ranh giới thành phần, thuộc tính chất lượng và các quyết định kỹ thuật có ảnh hưởng lớn |
| Security/privacy specialist | Tư vấn mối đe dọa, yêu cầu bảo vệ dữ liệu, rà soát thiết kế và kiểm chứng kiểm soát bảo mật |
| Operations/SRE | Định nghĩa khả năng vận hành, giám sát, cảnh báo, độ tin cậy, triển khai và phục hồi |

Một người có thể đảm nhiệm nhiều vai trò trong nhóm nhỏ. Điều cần giữ là năng lực và trách nhiệm phải được bao phủ, kể cả khi không có chức danh chuyên biệt.

### 3.1. Cùng làm rõ yêu cầu trước khi phát triển

Trong refinement hoặc hoạt động phân tích backlog, sản phẩm, phát triển và kiểm thử cùng trao đổi về:

- Mục tiêu người dùng và kết quả nghiệp vụ cần đạt.
- Luồng chính, luồng thay thế, trường hợp biên và quy tắc dữ liệu.
- Quyền truy cập, trạng thái lỗi, timeout, retry và hành vi khi phụ thuộc không sẵn sàng.
- Yêu cầu phi chức năng như hiệu năng, bảo mật, khả dụng, khả năng tiếp cận và khả năng phục hồi.
- Dữ liệu, môi trường, tích hợp và điều kiện cần để xác nhận.
- Tiêu chí chấp nhận và bằng chứng cần có để hoàn tất.

Tester có thể dùng câu hỏi và ví dụ cụ thể để phát hiện yêu cầu mơ hồ. Developer có thể chỉ ra giới hạn kiến trúc hoặc các nhánh triển khai. Product Owner xác nhận điều gì có giá trị với người dùng và mức rủi ro nào cần ưu tiên. Việc này làm giảm tình trạng mỗi vai trò hiểu cùng một yêu cầu theo cách khác nhau.

### 3.2. Phân chia công việc mà vẫn giữ trách nhiệm chung

Nhóm có thể giao một người làm chủ từng hoạt động, nhưng nên phối hợp theo cặp hoặc nhóm nhỏ khi công việc có rủi ro cao. Ví dụ, developer và tester cùng thiết kế dữ liệu cho kiểm thử chuyển đổi; security specialist cùng developer rà soát luồng phân quyền; SRE cùng tester xác định chỉ số và kịch bản phục hồi.

Khi phát hiện lỗi, người phát hiện cần cung cấp bước tái hiện, môi trường, dữ liệu và bằng chứng. Nhóm cùng xác định mức độ nghiêm trọng, phạm vi ảnh hưởng, nguyên nhân và kiểm thử hồi quy cần bổ sung. Không nên biến việc phân loại lỗi thành tranh luận về lỗi thuộc “team dev” hay “team QA”.

## 4. Đưa kiểm thử vào các hoạt động Agile

### 4.1. Product backlog và refinement

Mỗi backlog item nên mô tả giá trị, phạm vi và điều kiện chấp nhận đủ rõ để nhóm có thể phát triển và xác nhận. Trong refinement, nhóm cùng:

1. Làm rõ người dùng, mục tiêu và luồng nghiệp vụ.
2. Bổ sung ví dụ đầu vào/đầu ra, dữ liệu biên và trường hợp lỗi.
3. Xác định rủi ro và thuộc tính chất lượng có liên quan.
4. Kiểm tra phụ thuộc, môi trường, dữ liệu và khả năng kiểm thử.
5. Chia nhỏ công việc nếu phần việc quá lớn hoặc chứa nhiều giả định chưa được kiểm chứng.

Ví dụ, câu chuyện “người dùng có thể đổi mật khẩu” cần làm rõ xác thực người dùng, chính sách mật khẩu, thời hạn liên kết, hành vi khi liên kết hết hạn, thông báo, giới hạn thử lại và thu hồi phiên cũ. Những chi tiết này ảnh hưởng trực tiếp đến kiểm thử chức năng và bảo mật.

### 4.2. Sprint planning và dự báo năng lực

Khi lập kế hoạch sprint, nhóm cần tính đến công việc kiểm thử ngay trong ước lượng và năng lực thực hiện. Một backlog item không nên được coi là hoàn thành chỉ vì mã nguồn đã được viết. Nhóm cần dự trù thời gian cho kiểm thử, sửa lỗi, kiểm thử lại, cập nhật dữ liệu và xử lý các phụ thuộc.

Với hạng mục rủi ro cao, có thể lập nhiệm vụ riêng cho kiểm thử bảo mật, hiệu năng, di trú dữ liệu hoặc xác nhận vận hành. Nếu kiểm thử cần môi trường hay chuyên gia ngoài nhóm, phụ thuộc đó cần được phát hiện sớm và đưa vào kế hoạch.

### 4.3. Daily Scrum hoặc họp đồng bộ hằng ngày

Cuộc họp đồng bộ ngắn giúp nhóm phát hiện sớm trở ngại đối với mục tiêu sprint. Ngoài tiến độ phát triển, cần nêu các vấn đề ảnh hưởng đến dòng kiểm thử như môi trường hỏng, dữ liệu không sẵn sàng, kiểm thử chập chờn, lỗi đang chặn nhiều người hoặc kết quả kiểm thử chưa có người xử lý.

Không nên biến daily thành buổi báo cáo chi tiết từng ca kiểm thử. Những vấn đề cần phân tích sâu có thể được các thành viên liên quan xử lý ngay sau cuộc họp.

### 4.4. Sprint review

Trong review, nhóm trình bày phần sản phẩm đã hoàn thành và lấy phản hồi từ các bên liên quan. Kết quả kiểm thử giúp giải thích hành vi đã được xác nhận, giới hạn còn lại và các rủi ro cần cân nhắc. Nếu một chức năng chưa đạt tiêu chí hoặc chưa có bằng chứng cần thiết, cần phản ánh đúng trạng thái thay vì trình bày như một phần đã hoàn tất.

### 4.5. Retrospective

Retrospective là cơ hội cải thiện cách phối hợp và dòng phản hồi. Nhóm có thể xem xét:

- Lỗi nào được phát hiện muộn và vì sao?
- Yêu cầu nào thường phải làm rõ sau khi phát triển?
- Kiểm thử nào chậm, không ổn định hoặc ít tạo giá trị?
- Môi trường và dữ liệu có gây chờ đợi không?
- Việc bàn giao giữa phát triển, kiểm thử và vận hành có tạo điểm nghẽn không?
- Một thay đổi nhỏ nào có thể cải thiện chất lượng trong sprint tiếp theo?

Chọn ít hành động cải tiến nhưng có người phụ trách và thời hạn. Theo dõi kết quả ở các sprint sau để biết hành động có thực sự cải thiện tình hình không.

## 5. Thỏa thuận chất lượng: Definition of Ready và Definition of Done

Definition of Ready (DoR) và Definition of Done (DoD) là các thỏa thuận giúp nhóm thống nhất điều kiện để bắt đầu và hoàn tất công việc. Chúng không thay thế tiêu chí chấp nhận của từng backlog item.

### 5.1. Definition of Ready

Một backlog item có thể được coi là sẵn sàng khi nhóm hiểu đủ để bắt đầu công việc. Ví dụ:

- Mục tiêu và người dùng được xác định.
- Phạm vi và tiêu chí chấp nhận có thể hiểu và kiểm chứng.
- Quy tắc nghiệp vụ, dữ liệu và các trường hợp quan trọng đã được làm rõ.
- Phụ thuộc và rủi ro chính được nhận diện.
- Có cách tiếp cận kiểm thử sơ bộ và điều kiện môi trường cần thiết.
- Kích thước công việc phù hợp với khả năng hoàn thành trong một vòng lặp.

DoR nên là công cụ giúp trao đổi, không phải một cổng hành chính cứng khiến nhóm từ chối mọi công việc còn một câu hỏi nhỏ. Nếu một giả định chưa thể giải quyết, hãy ghi rõ và xác định cách kiểm chứng nó trong quá trình thực hiện.

### 5.2. Definition of Done

DoD mô tả điều kiện chung để một phần công việc được xem là hoàn tất. Một ví dụ có thể gồm:

- Mã nguồn được rà soát và tích hợp theo quy trình của nhóm.
- Kiểm thử đơn vị/thành phần phù hợp đã chạy và đạt.
- Kiểm thử tích hợp hoặc hợp đồng liên quan đã có kết quả.
- Tiêu chí chấp nhận được xác nhận bằng bằng chứng.
- Lỗi nghiêm trọng đã được xử lý hoặc có quyết định ngoại lệ đúng thẩm quyền.
- Tài liệu, cấu hình, nhật ký thay đổi và hướng dẫn vận hành cần thiết được cập nhật.
- Yêu cầu bảo mật, dữ liệu và khả năng tiếp cận liên quan được xem xét.
- Có khả năng triển khai và quan sát theo mức yêu cầu của sản phẩm.

DoD cần phù hợp với loại công việc. Một thay đổi giao diện nhỏ và một thay đổi cơ chế thanh toán có thể cần độ sâu kiểm chứng khác nhau. Các yêu cầu bắt buộc của tổ chức vẫn phải được tuân thủ dù nhóm dùng DoD linh hoạt.

## 6. Phối hợp kiểm thử trong pipeline CI/CD

Pipeline CI/CD tạo ra các điểm kiểm tra có thể lặp lại khi mã nguồn và cấu hình thay đổi. Cách sắp xếp thường bắt đầu bằng kiểm tra nhanh, sau đó mở rộng đến kiểm thử cần môi trường hoặc thời gian lớn hơn.

```text
Thay đổi mã nguồn / Pull Request
              |
              v
Kiểm tra định dạng, phân tích tĩnh, rà soát phụ thuộc
              |
              v
Kiểm thử đơn vị và thành phần
              |
              v
Build artifact và kiểm tra cấu hình
              |
              v
Kiểm thử API / hợp đồng / tích hợp
              |
              v
Triển khai môi trường kiểm thử
              |
              v
Kiểm thử đầu cuối và phi chức năng theo rủi ro
              |
              v
Đánh giá bằng chứng và cổng phát hành
              |
              v
Triển khai theo chiến lược đã chọn
              |
              v
Smoke test, giám sát và phản hồi sau triển khai
```

Đây là luồng tham khảo. Không phải pipeline nào cũng cần mọi bước chạy tuần tự; một số kiểm tra có thể chạy song song, theo lịch hoặc tại một cổng riêng. Nhóm nên chọn vị trí kiểm tra sao cho lỗi được phát hiện gần thời điểm tạo ra mà không làm mất các xác nhận cần thiết trước phát hành.

### 6.1. Kiểm tra sớm khi tạo thay đổi

Khi mở pull request, pipeline có thể chạy định dạng, lint, phân tích tĩnh, kiểm tra bí mật trong mã nguồn, rà soát thành phần phụ thuộc và kiểm thử đơn vị. Kết quả cần được gắn với đúng commit để người tạo thay đổi biết điều kiện nào chưa đạt.

Developer chịu trách nhiệm xem kết quả và sửa lỗi thuộc thay đổi của mình. Tester giúp xác định các kịch bản rủi ro cần bổ sung và đánh giá liệu kiểm thử hiện có đủ bao phủ. Người rà soát mã cần xem cả khả năng kiểm thử, xử lý lỗi và quan sát của thay đổi.

### 6.2. Kiểm thử sau tích hợp

Sau khi các thay đổi được tích hợp, nhóm có thể chạy kiểm thử hợp đồng, tích hợp, API và một tập hồi quy phù hợp. Các kiểm thử này xác nhận thành phần phối hợp với nhau và phát hiện lỗi do khác biệt schema, cấu hình, thứ tự sự kiện hoặc phụ thuộc.

Nếu kiểm thử cần môi trường chung, nhóm phải quản lý xung đột dữ liệu, cấu hình và phiên bản dịch vụ. Môi trường dùng chung cần có chủ sở hữu, quy tắc đặt lịch hoặc cơ chế tạo môi trường tạm thời để giảm thời gian chờ.

### 6.3. Cổng chất lượng và ngoại lệ

Cổng chất lượng (quality gate) là tập điều kiện được thống nhất để quyết định có thể chuyển thay đổi sang bước tiếp theo hay không. Ví dụ, không có kiểm thử bắt buộc thất bại, không có lỗ hổng nghiêm trọng chưa được xử lý và các mục tiêu hiệu năng trọng yếu đạt ngưỡng.

Một cổng tốt cần nêu rõ:

- Kiểm tra nào là bắt buộc và kiểm tra nào chỉ cung cấp thông tin.
- Kết quả nào làm pipeline dừng hoặc yêu cầu người có thẩm quyền xem xét.
- Ai được quyền phê duyệt ngoại lệ và ngoại lệ có hiệu lực đến khi nào.
- Bằng chứng, lý do và rủi ro còn lại được lưu ở đâu.
- Điều kiện nào khiến ngoại lệ phải được đánh giá lại.

Không nên đặt cổng dựa trên một con số không có ý nghĩa trực tiếp với rủi ro, chẳng hạn chỉ yêu cầu một tỷ lệ bao phủ mã nguồn chung mà không xác định luồng quan trọng. Cũng không nên cho phép bỏ qua kiểm thử bắt buộc mà không ghi nhận người chấp thuận và tác động.

### 6.4. Quản lý kiểm thử chậm và kiểm thử không ổn định

Kiểm thử chậm có thể chạy theo lịch, trên nhánh chính, trước phát hành hoặc trong môi trường chuyên biệt. Nhóm cần biết kết quả gần nhất còn phù hợp với phiên bản nào và rủi ro nào được bao phủ trong lúc chờ.

Kiểm thử chập chờn (flaky test) cho kết quả khác nhau khi mã nguồn và điều kiện không đổi. Chúng làm giảm niềm tin vào pipeline và khiến nhóm có xu hướng bỏ qua cảnh báo. Cần theo dõi tỷ lệ chập chờn, phân tích nguyên nhân như phụ thuộc thời gian, dữ liệu dùng chung, thứ tự chạy, mạng hoặc đồng bộ bất ổn. Nếu tạm thời cách ly kiểm thử, phải ghi rõ rủi ro bị giảm mức bao phủ và thời hạn khôi phục.

## 7. Kết hợp kiểm thử tự động và kiểm thử thủ công

Tự động hóa phù hợp với các kiểm tra có quy tắc rõ, lặp lại thường xuyên và cần phản hồi nhanh. Kiểm thử thủ công có giá trị khi cần phán đoán, quan sát trải nghiệm, khám phá hành vi mới hoặc đánh giá tình huống khó mô hình hóa. Hai cách này bổ sung cho nhau.

| Hoạt động | Khi phù hợp | Cách phối hợp |
|---|---|---|
| Kiểm thử đơn vị/thành phần tự động | Quy tắc cục bộ, xử lý dữ liệu, điều kiện biên | Developer duy trì cùng mã nguồn; tester hỗ trợ phân tích trường hợp rủi ro |
| Kiểm thử API/hợp đồng tự động | Giao diện giữa dịch vụ, schema và tương thích phiên bản | Nhóm cung cấp và tiêu thụ dịch vụ thống nhất hợp đồng và dữ liệu |
| Kiểm thử đầu cuối tự động | Một số hành trình người dùng quan trọng và tương đối ổn định | Tester chọn kịch bản có giá trị; developer/automation engineer duy trì độ ổn định |
| Kiểm thử khám phá | Tính năng mới, yêu cầu chưa rõ, rủi ro tương tác và hành vi bất ngờ | Tester và developer cùng xem xét phát hiện; ghi charter và kết quả để có thể lặp lại |
| Kiểm thử khả dụng/khả năng tiếp cận | Đánh giá mức dễ sử dụng và khả năng tiếp cận với người dùng thực | Kết hợp thử nghiệm người dùng, kiểm tra công cụ và rà soát chuyên môn |
| Kiểm thử bảo mật, hiệu năng, phục hồi | Rủi ro chuyên biệt hoặc tác động lớn | Chuyên gia và nhóm dịch vụ cùng xác định điều kiện, ngưỡng và cách xử lý kết quả |

Một mô hình thường dùng là kim tự tháp kiểm thử: nhiều kiểm thử đơn vị/thành phần nhanh ở đáy, số lượng vừa phải kiểm thử tích hợp/API ở giữa và ít kiểm thử đầu cuối ở đỉnh. Đây là định hướng về tốc độ và chi phí phản hồi, không phải tỷ lệ cứng cho mọi hệ thống. Kiến trúc, rủi ro và khả năng kiểm thử có thể khiến phân bố phù hợp khác nhau.

Không tự động hóa một kịch bản chỉ vì có thể viết script. Hãy cân nhắc tần suất chạy, độ ổn định, giá trị phát hiện lỗi, chi phí bảo trì và khả năng hiểu kết quả. Một kiểm thử tự động không đáng tin cậy có thể làm chậm nhóm hơn một bước kiểm tra thủ công có mục tiêu.

## 8. Shift-left và shift-right trong chu trình DevOps

### 8.1. Shift-left: đưa kiểm chứng sớm hơn

Shift-left là đưa hoạt động chất lượng về những giai đoạn sớm hơn của vòng đời, chẳng hạn làm rõ yêu cầu, rà soát thiết kế, phân tích mối đe dọa, kiểm thử đơn vị và kiểm tra phụ thuộc ngay trong pull request.

Ví dụ:

- Trong refinement, kiểm tra tiêu chí chấp nhận có thể đo được và có trường hợp lỗi.
- Khi thiết kế, rà soát luồng dữ liệu, phân quyền, điểm nghẽn và khả năng phục hồi.
- Khi viết mã, chạy kiểm thử đơn vị, phân tích tĩnh và kiểm tra bí mật.
- Khi tích hợp, kiểm thử hợp đồng và tương thích API.

Shift-left giảm thời gian giữa lúc tạo lỗi và lúc phát hiện. Tuy vậy, kiểm thử sớm không thể thay thế xác nhận tích hợp, hiệu năng hoặc vận hành trong môi trường gần thực tế.

### 8.2. Shift-right: học từ hành vi sau triển khai

Shift-right là tiếp tục xác nhận và học từ hệ thống trong môi trường triển khai, bao gồm kiểm thử smoke, giám sát, phân tích log/trace/metric, thử nghiệm có kiểm soát và diễn tập vận hành.

Các kỹ thuật có thể dùng:

- **Canary release:** đưa thay đổi đến một tỷ lệ hoặc nhóm nhỏ người dùng trước khi mở rộng.
- **Blue-green deployment:** duy trì hai môi trường triển khai để chuyển lưu lượng có kiểm soát và hỗ trợ quay lại.
- **Feature flag:** bật/tắt tính năng theo cấu hình hoặc nhóm người dùng để giới hạn phạm vi ảnh hưởng.
- **Synthetic monitoring:** tạo yêu cầu kiểm tra định kỳ để xác nhận hành trình hoặc khả năng sẵn sàng.
- **Observability:** dùng metric, log và trace để hiểu trạng thái hệ thống và nguyên nhân bất thường.
- **Chaos/failure testing:** mô phỏng một số lỗi phụ thuộc hoặc hạ tầng trong phạm vi an toàn, có kiểm soát.
- **A/B testing:** so sánh kết quả trải nghiệm hoặc hành vi giữa các biến thể khi có giả thuyết và thiết kế thử nghiệm phù hợp.

Các hoạt động trên cần có giới hạn an toàn, tiêu chí dừng và kế hoạch ứng phó. Không thử nghiệm lỗi trên người dùng hoặc dữ liệu thật nếu chưa có đánh giá tác động, phê duyệt và cơ chế bảo vệ phù hợp.

### 8.3. Liên kết tín hiệu sản xuất với backlog

Khi giám sát phát hiện độ trễ tăng, lỗi giao dịch, tỷ lệ thoát cao hoặc cảnh báo bảo mật, nhóm cần chuyển thông tin thành hành động có chủ sở hữu. Có thể tạo lỗi, cập nhật hồ sơ rủi ro, bổ sung kiểm thử hồi quy, sửa telemetry hoặc thay đổi mục tiêu chất lượng.

Phản hồi sản xuất chỉ có giá trị khi quay lại quy trình phát triển. Nếu dashboard có nhiều cảnh báo nhưng không ai phân tích, nhóm không học được từ dữ liệu vận hành.

## 9. Phối hợp với vận hành và bảo đảm khả năng phát hành

Kiểm thử trong DevOps không kết thúc khi pipeline chuyển sang màu xanh. Nhóm cần xác nhận sản phẩm có thể triển khai, quan sát, hỗ trợ và khôi phục.

Trước phát hành, nhóm có thể kiểm tra:

- Artifact được tạo từ commit đã xác nhận và có thể truy vết.
- Cấu hình, secret, migration và phụ thuộc được quản lý đúng cách.
- Health check, metric, log, trace và cảnh báo cần thiết đã sẵn sàng.
- Có hướng dẫn triển khai, rollback hoặc tắt tính năng.
- Các kịch bản smoke và kiểm tra sau triển khai đã được xác định.
- Rủi ro còn lại và ngoại lệ được ghi nhận, có người chấp thuận đúng thẩm quyền.

Sau triển khai, nhóm theo dõi chỉ báo quan trọng theo cửa sổ thời gian phù hợp. Nếu canary có lỗi vượt ngưỡng, hệ thống cần dừng mở rộng hoặc quay lại theo chính sách. Nếu thay đổi gây sự cố, cần xử lý sự cố trước, sau đó cập nhật kiểm thử, rủi ro và quyết định phát hành.

Rollback không phải lúc nào cũng khôi phục được trạng thái dữ liệu hoặc đảo ngược tác động bên ngoài. Với thay đổi schema, giao dịch tài chính hoặc gửi thông báo, cần thiết kế khả năng tương thích và quy trình khắc phục dữ liệu trước khi triển khai.

## 10. Quản lý môi trường và dữ liệu kiểm thử trong nhóm liên chức năng

Môi trường và dữ liệu thường là nguồn gây chậm trễ, kết quả không ổn định và khoảng trống kiểm thử. Nhóm Agile/DevOps cần coi chúng là tài sản được quản lý, có chủ sở hữu và quy trình sử dụng rõ ràng.

### 10.1. Môi trường

Môi trường kiểm thử nên có cấu hình và phiên bản phụ thuộc được kiểm soát. Với hệ thống có thể tạo môi trường tạm thời, nhóm có thể dùng infrastructure as code hoặc container để tái tạo cấu hình nhất quán. Cần ghi rõ những khác biệt với sản xuất như quy mô dữ liệu, cấu hình mạng, dịch vụ giả lập và giới hạn tài nguyên.

Không phải mọi kiểm thử đều cần bản sao hoàn chỉnh của sản xuất. Nhưng với kiểm thử hiệu năng, bảo mật, tương thích và phục hồi, khác biệt môi trường có thể làm giảm giá trị bằng chứng. Nhóm cần xác định khác biệt nào có ảnh hưởng và bổ sung kiểm tra phù hợp.

### 10.2. Dữ liệu kiểm thử

Dữ liệu cần đại diện cho quy tắc và trường hợp biên, đồng thời tuân thủ yêu cầu bảo mật và riêng tư. Có thể dùng dữ liệu tổng hợp, dữ liệu đã ẩn danh hoặc dữ liệu giả lập có kiểm soát. Cần có quy tắc tạo, làm sạch, làm mới và phân quyền truy cập dữ liệu.

Không nên để các kiểm thử dùng chung dữ liệu có trạng thái thay đổi mà không có cơ chế cô lập. Điều này dễ gây phụ thuộc thứ tự chạy và lỗi chập chờn. Có thể tạo dữ liệu riêng theo test run, dùng namespace hoặc khôi phục trạng thái sau kiểm thử.

### 10.3. Phụ thuộc bên ngoài

Với dịch vụ của đối tác, nhóm có thể dùng sandbox, mock hoặc service virtualization để kiểm thử các tình huống lỗi và phản hồi không phổ biến. Tuy nhiên, mock không chứng minh tích hợp thật hoạt động hoàn toàn đúng. Cần duy trì một số kiểm tra tích hợp thật trong môi trường được kiểm soát và ghi rõ phần chưa được xác nhận.

## 11. Đo lường hiệu quả phối hợp và chất lượng

Chỉ số nên giúp nhóm phát hiện điểm nghẽn và cải thiện kết quả. Tránh dùng một chỉ số đơn lẻ để xếp hạng cá nhân hoặc kết luận chất lượng tổng thể.

| Nhóm đo lường | Ví dụ chỉ số | Cách sử dụng |
|---|---|---|
| Dòng chảy phát triển | Lead time for changes, tần suất triển khai, thời gian chờ review | Nhận diện thời gian chờ và điểm nghẽn giữa các bước |
| Độ tin cậy phát hành | Change failure rate, thời gian khôi phục dịch vụ | Đánh giá tác động của thay đổi và khả năng phục hồi |
| Hiệu quả kiểm thử | Thời gian phản hồi pipeline, tỷ lệ kiểm thử chập chờn, lỗi phát hiện theo giai đoạn | Cải thiện chất lượng tín hiệu và tốc độ phản hồi |
| Kết quả chất lượng | Lỗi nghiêm trọng lọt ra, lỗi lặp lại, sự cố theo luồng nghiệp vụ | Xác định khoảng trống kiểm thử và ưu tiên giảm rủi ro |
| Trải nghiệm người dùng | Tỷ lệ hoàn thành tác vụ, độ trễ cảm nhận, phản hồi hỗ trợ | Đối chiếu chất lượng kỹ thuật với kết quả người dùng |
| Khả năng vận hành | SLO, error budget, thời gian phát hiện và xử lý sự cố | Điều chỉnh mức thay đổi, kiểm soát và đầu tư độ tin cậy |

Các chỉ số DORA thường được dùng để hiểu hiệu quả dòng chảy phát triển và độ tin cậy phát hành, nhưng cần đọc theo bối cảnh hệ thống, loại dịch vụ và cách đo. Chúng không phải thước đo năng suất cá nhân và không thể thay thế dữ liệu chất lượng sản phẩm.

Ví dụ, tăng tần suất triển khai là tín hiệu tốt khi đi cùng thay đổi nhỏ, tỷ lệ lỗi thấp và khả năng khôi phục tốt. Nếu tần suất tăng nhưng lỗi lọt ra và thời gian khôi phục cũng tăng, nhóm cần xem xét chất lượng cổng kiểm thử, phạm vi thay đổi và năng lực vận hành.

Không nên đặt mục tiêu giảm thời gian pipeline bằng cách bỏ kiểm thử quan trọng. Tối ưu cần xét cả tốc độ, độ tin cậy và khả năng phát hiện rủi ro.

## 12. Ví dụ phối hợp xuyên suốt: phát triển tính năng thanh toán

Giả sử một nhóm Agile phát triển tính năng thanh toán mới cho ứng dụng thương mại điện tử. Mục tiêu là người mua có thể thanh toán đúng, nhận phản hồi rõ ràng và không bị thu tiền hai lần khi mạng hoặc nhà cung cấp gặp lỗi.

| Giai đoạn | Hoạt động phối hợp | Bằng chứng/kết quả |
|---|---|---|
| Refinement | Product Owner, developer và tester làm rõ luồng thành công, từ chối, timeout, retry, hoàn tiền và quyền truy cập | Tiêu chí chấp nhận, sơ đồ trạng thái và danh sách rủi ro |
| Thiết kế | Developer, architect, security và tester rà soát idempotency, webhook, dữ liệu nhạy cảm và xử lý lỗi | Quyết định thiết kế, phân tích mối đe dọa và kịch bản kiểm thử |
| Phát triển | Developer viết kiểm thử đơn vị cho quy tắc tính tiền; tester chuẩn bị dữ liệu biên và charter khám phá | Kiểm thử đơn vị, rà soát mã và dữ liệu kiểm thử |
| Pull request | CI chạy phân tích tĩnh, kiểm tra phụ thuộc, kiểm thử đơn vị và kiểm tra hợp đồng | Kết quả pipeline gắn với commit |
| Tích hợp | Nhóm chạy kiểm thử API, webhook lặp, timeout, retry và đối soát với sandbox | Báo cáo tích hợp và bằng chứng xử lý trạng thái |
| Trước phát hành | Tester và SRE xác nhận tải, cảnh báo, smoke test, feature flag và rollback | Báo cáo hiệu năng, dashboard và kế hoạch triển khai |
| Triển khai | Nhóm phát hành canary cho một nhóm nhỏ, theo dõi tỷ lệ lỗi và giao dịch chưa rõ | Chỉ số sản xuất và quyết định mở rộng hoặc dừng |
| Sau phát hành | Nhóm rà soát sự cố, phản hồi khách hàng và kiểm thử bị thiếu | Backlog cải tiến, kiểm thử hồi quy và cập nhật hồ sơ rủi ro |

Trong ví dụ này, tester tham gia từ refinement nhưng không làm thay trách nhiệm của developer trong kiểm thử mã nguồn. Developer hỗ trợ kiểm thử khám phá và xử lý kết quả. SRE tham gia từ thiết kế để bảo đảm có thể giám sát và phục hồi. Product Owner quyết định ưu tiên nghiệp vụ và cùng người có thẩm quyền xem xét rủi ro còn lại.

## 13. Những sai lầm thường gặp

- **Để kiểm thử đến cuối sprint:** lỗi yêu cầu và thiết kế chỉ được phát hiện khi chi phí sửa đã cao.
- **Coi chất lượng là trách nhiệm riêng của QA:** developer, sản phẩm và vận hành không tham gia tạo bằng chứng và xử lý nguyên nhân.
- **Đồng nhất DevOps với công cụ CI/CD:** pipeline tự động không thay thế hợp tác, trách nhiệm và phản hồi từ vận hành.
- **Chạy mọi kiểm thử ở mọi commit:** pipeline quá chậm làm nhóm tìm cách bỏ qua hoặc trì hoãn kiểm tra.
- **Chỉ tự động hóa giao diện:** bỏ lỡ phản hồi nhanh từ kiểm thử đơn vị, thành phần, API và hợp đồng.
- **Tin tuyệt đối vào mock:** chưa xác nhận hành vi của hệ thống và nhà cung cấp thật.
- **Không quản lý dữ liệu và môi trường:** kết quả không lặp lại, kiểm thử chập chờn và nhóm mất thời gian chờ đợi.
- **Bỏ qua kiểm thử phi chức năng:** chức năng có thể đúng nhưng vẫn không đáp ứng hiệu năng, bảo mật hoặc khả năng phục hồi.
- **Xem pipeline xanh là bảo đảm phát hành:** cần xét phiên bản, phạm vi kiểm thử, rủi ro còn lại và trạng thái vận hành.
- **Không đưa phản hồi sản xuất về backlog:** nhóm tiếp tục lặp lại lỗi mà không cải thiện kiểm thử hoặc thiết kế.
- **Dùng chỉ số để gây áp lực cá nhân:** số lượng ca kiểm thử hoặc lỗi tìm được không phản ánh đầy đủ giá trị và chất lượng phối hợp.

## 14. Checklist thiết lập phối hợp kiểm thử Agile và DevOps

- [ ] Mục tiêu chất lượng và rủi ro được thảo luận trong refinement.
- [ ] Tiêu chí chấp nhận có thể kiểm chứng và bao gồm trường hợp lỗi quan trọng.
- [ ] Developer, tester, sản phẩm và vận hành hiểu trách nhiệm của mình.
- [ ] DoR và DoD phản ánh các điều kiện chất lượng cần thiết.
- [ ] Kiểm thử được đưa vào kế hoạch sprint và ước lượng công việc.
- [ ] Pipeline cung cấp phản hồi nhanh cho kiểm tra phù hợp và có cổng rõ ràng.
- [ ] Kiểm thử chậm, kiểm thử chập chờn và ngoại lệ được theo dõi có chủ sở hữu.
- [ ] Môi trường, dữ liệu và phụ thuộc kiểm thử có người quản lý.
- [ ] Kiểm thử bảo mật, hiệu năng, dữ liệu và khả năng phục hồi được chọn theo rủi ro.
- [ ] Có smoke test, giám sát và kế hoạch rollback/khắc phục sau triển khai.
- [ ] Chỉ báo sản xuất và sự cố được đưa trở lại backlog và hồ sơ rủi ro.
- [ ] Nhóm dùng retrospective để cải thiện dòng phản hồi và theo dõi hiệu quả hành động.

## Kết luận

Phối hợp kiểm thử trong Agile và DevOps đưa chất lượng vào toàn bộ dòng chảy phát triển: từ làm rõ nhu cầu, thiết kế, viết mã và tích hợp đến triển khai, vận hành và cải tiến. Nhóm liên chức năng cần chia sẻ mục tiêu nhưng giữ trách nhiệm rõ ràng, dùng kiểm thử tự động và thủ công theo đúng giá trị, tổ chức pipeline tạo phản hồi đáng tin cậy và đưa tín hiệu sản xuất trở lại quá trình phát triển. Khi quyết định kiểm thử gắn với rủi ro, bằng chứng và khả năng vận hành, nhóm có thể cung cấp thay đổi thường xuyên mà vẫn kiểm soát được chất lượng.
