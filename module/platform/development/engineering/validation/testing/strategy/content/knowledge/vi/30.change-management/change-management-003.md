# Cập nhật rủi ro và phân bổ kiểm thử theo bằng chứng mới

## 1. Vì sao chiến lược kiểm thử phải thay đổi theo bằng chứng?

Chiến lược kiểm thử thường được lập từ yêu cầu, kiến trúc, phân tích rủi ro và hiểu biết tại một thời điểm. Nhưng sản phẩm, phụ thuộc, môi trường và cách người dùng sử dụng luôn thay đổi. Sau khi có thêm bằng chứng, một giả định ban đầu có thể không còn đúng: lỗi mới xuất hiện ở một luồng ít được chú ý, một dependency đổi phiên bản, telemetry cho thấy một khu vực thường xuyên suy giảm, khách hàng báo một tình huống chưa có trong test suite hoặc một thay đổi kiến trúc làm tăng phạm vi ảnh hưởng.

Nếu nhóm tiếp tục chạy cùng một bộ test theo lịch cũ mà không cập nhật đánh giá rủi ro, nguồn lực có thể bị dành quá nhiều cho vùng đã ổn định trong khi rủi ro mới chưa được kiểm tra. Ngược lại, phản ứng với từng tín hiệu nhỏ bằng cách thay đổi toàn bộ suite có thể làm pipeline chậm, tăng chi phí và khiến phạm vi kiểm thử thiếu ổn định.

**Cập nhật rủi ro và phân bổ kiểm thử theo bằng chứng mới** là quy trình có kiểm soát để:

- Thu thập và đánh giá bằng chứng mới từ phát triển, kiểm thử và vận hành.
- Xác định bằng chứng làm thay đổi giả định, khả năng xảy ra, tác động hoặc mức độ bất định của rủi ro nào.
- Cập nhật risk register, impact map và liên kết requirement–risk–test.
- Điều chỉnh phạm vi, thứ tự, tần suất, môi trường và mức đầu tư kiểm thử.
- Giữ các kiểm thử bắt buộc và ghi nhận rõ mọi khoảng trống hoặc ngoại lệ.
- Theo dõi kết quả sau điều chỉnh để biết quyết định có cải thiện khả năng phát hiện rủi ro hay không.

Trong phạm vi **VALIDATION_TESTING_STRATEGY**, chiến lược kiểm thử cần vừa ổn định để có thể vận hành và so sánh, vừa thích ứng khi bằng chứng đủ mạnh cho thấy ưu tiên đã thay đổi. Điều chỉnh phải có lý do, người chịu trách nhiệm, thời điểm áp dụng và cách đánh giá hiệu quả.

## 2. Mối quan hệ giữa thay đổi, bằng chứng, rủi ro và kiểm thử

Các yếu tố tạo thành một vòng phản hồi:

~~~text
Thay đổi sản phẩm / tín hiệu mới / kết quả kiểm thử
                     |
                     v
            Thu thập và xác minh evidence
                     |
                     v
           Xác định giả định bị tác động
                     |
                     v
       Cập nhật risk register và impact map
                     |
                     v
      Chọn hành động kiểm thử theo mức rủi ro
                     |
                     v
      Điều chỉnh suite, thứ tự, môi trường, tần suất
                     |
                     v
        Chạy test và đánh giá bằng chứng mới
                     |
                     v
         Review hiệu quả và cập nhật tiếp
~~~

Không phải mọi thay đổi đều cần viết thêm test. Một số thay đổi yêu cầu chạy lại test hiện có, mở rộng dữ liệu, tăng tần suất giám sát, bổ sung kiểm tra ở tầng khác hoặc giảm phạm vi rollout. Một số bằng chứng có thể làm giảm rủi ro, nhưng chỉ khi chúng đủ liên quan và đáng tin cậy.

Ví dụ, nếu production incident cho thấy đơn hàng bị tạo trùng khi consumer nhận event nhiều lần, nhóm có thể:

- Tăng đánh giá rủi ro về idempotency và xử lý message trùng.
- Bổ sung test cho delivery at-least-once, retry và xử lý song song.
- Thêm kiểm tra contract hoặc integration giữa provider và consumer.
- Kiểm tra dữ liệu trùng và khả năng đối soát.
- Tăng monitoring cho duplicate-order signal.
- Đánh giá lại thứ tự chạy các test liên quan trước release.

Chỉ thêm một test cho trường hợp tái hiện incident mà không cập nhật rủi ro, phụ thuộc và các consumer liên quan có thể để lại khoảng trống tương tự ở nơi khác.

## 3. Nguồn bằng chứng mới cần theo dõi

### 3.1. Kết quả kiểm thử

Các tín hiệu từ test suite gồm:

- Test fail mới hoặc lỗi hồi quy được phát hiện.
- Flaky test tăng hoặc test chỉ fail trên một môi trường.
- Test bị blocked, not run hoặc inconclusive kéo dài.
- Mutation testing cho thấy assertion không phát hiện thay đổi đáng lẽ phải bị bắt.
- Contract test phát hiện provider/consumer không tương thích.
- Test hiệu năng cho thấy latency hoặc throughput suy giảm.
- Kiểm thử bảo mật phát hiện lỗ hổng hoặc đường truy cập vượt quyền.
- Test thủ công/exploratory tìm thấy hành vi chưa có trong kịch bản.

Một test fail không tự động chứng minh sản phẩm có defect. Cần xác minh build, môi trường, dữ liệu, test logic và khả năng tái hiện. Tuy nhiên, ngay cả khi nguyên nhân là môi trường hoặc test, sự kiện đó vẫn có thể cung cấp bằng chứng về độ tin cậy của pipeline hoặc khả năng quan sát.

### 3.2. Defect và incident

Defect, escaped defect, incident và post-incident review có thể làm thay đổi đánh giá rủi ro:

- Lỗi đã xuất hiện ở production dù regression suite trước đó đạt.
- Một defect lặp lại sau khi đã sửa.
- Một lỗi có mức severity cao hơn dự kiến.
- Workaround không hoạt động trong điều kiện thực tế.
- Thời gian phát hiện hoặc khôi phục dài hơn mục tiêu.
- Nguyên nhân gốc liên quan đến dependency, dữ liệu, concurrency hoặc cấu hình chưa được kiểm thử.

Không chỉ lấy số lượng defect làm bằng chứng. Cần xem loại lỗi, tác động, tần suất, điều kiện xảy ra, mức độ phơi nhiễm và các kiểm soát đã thất bại.

### 3.3. Telemetry và vận hành

Metric, log, trace, RUM, synthetic monitoring và business event cung cấp tín hiệu về hành vi hệ thống:

- Error rate hoặc latency tăng sau một thay đổi.
- Queue lag, retry hoặc dead-letter message tăng.
- Một vùng, tenant, trình duyệt hoặc phiên bản có tỷ lệ lỗi cao hơn.
- Dữ liệu nghiệp vụ không nhất quán dù API trả mã thành công.
- Saturation hoặc resource usage tăng theo tải.
- SLO hoặc error budget bị tiêu thụ nhanh.
- Alert hoặc incident xuất hiện ở một dependency cụ thể.

Một bất thường trong telemetry có thể do lưu lượng, mùa vụ, dữ liệu hoặc thay đổi đo lường. Trước khi đổi test strategy, cần kiểm tra nguồn, thời gian, phân đoạn và mối liên hệ với phiên bản.

### 3.4. Thay đổi sản phẩm và kiến trúc

Các thay đổi có thể làm phát sinh hoặc thay đổi rủi ro:

- API, event, schema hoặc contract thay đổi.
- Thêm/bỏ service hoặc chuyển quyền sở hữu.
- Thay đổi luồng dữ liệu, queue, cache hoặc storage.
- Nâng cấp runtime, framework, thư viện hoặc base image.
- Thay đổi authentication, authorization hoặc secret handling.
- Chuyển cloud/region, mạng, gateway hoặc database.
- Thay đổi feature flag, rollout strategy hoặc tenant model.
- Thêm tính năng AI, thuật toán hoặc logic quyết định mới.

Impact analysis cần xem cả tác động trực tiếp và đường phụ thuộc gián tiếp. Một thay đổi trong thư viện xác thực dùng chung có thể ảnh hưởng nhiều service dù chỉ một repository được sửa.

### 3.5. Người dùng, khách hàng và nghiệp vụ

Phản hồi từ support, khách hàng, product owner và domain expert có thể cho thấy:

- Một luồng ít dùng nhưng hậu quả lớn.
- Một tổ hợp dữ liệu hoặc thao tác thực tế chưa được mô phỏng.
- Quy tắc nghiệp vụ thay đổi nhưng test chưa cập nhật.
- Một nhóm người dùng gặp vấn đề mà số liệu tổng thể che khuất.
- Workaround hoặc hướng dẫn hiện tại không đáp ứng nhu cầu.

Phản hồi cần được chuyển thành mô tả điều kiện, hành vi mong đợi và mức tác động có thể kiểm chứng. Không nên tự động biến mọi yêu cầu cá nhân thành test bắt buộc; cần xác nhận tính đại diện và rủi ro.

### 3.6. Bảo mật, tuân thủ và thay đổi bên ngoài

Threat intelligence, security advisory, audit finding, thay đổi luật/chính sách, yêu cầu hợp đồng hoặc sự cố từ nhà cung cấp có thể làm thay đổi mức rủi ro. Những bằng chứng này có thể yêu cầu kiểm thử chuyên môn, rà soát quyền, kiểm tra dependency hoặc xác nhận lưu trữ dữ liệu.

Với nghĩa vụ bắt buộc, cần tham vấn người có thẩm quyền chuyên môn. Không hạ mức kiểm thử chỉ vì rủi ro chưa từng xảy ra trong nội bộ.

## 4. Đánh giá chất lượng và mức liên quan của bằng chứng

Không phải mọi tín hiệu đều có trọng lượng như nhau. Trước khi thay đổi risk rating hoặc test allocation, đánh giá bằng chứng theo các chiều:

| Chiều đánh giá | Câu hỏi |
|---|---|
| Relevance | Bằng chứng có liên quan trực tiếp đến service, hành vi hoặc rủi ro đang xét không? |
| Reliability | Nguồn có đáng tin, phương pháp có phù hợp và dữ liệu có bị lỗi không? |
| Recency | Bằng chứng có còn đại diện cho phiên bản và điều kiện hiện tại không? |
| Reproducibility | Có thể tái hiện hoặc kiểm chứng độc lập không? |
| Coverage | Bằng chứng phản ánh một trường hợp riêng lẻ hay một tập điều kiện rộng hơn? |
| Severity | Hậu quả quan sát được hoặc có thể suy ra nghiêm trọng đến đâu? |
| Exposure | Có bao nhiêu người dùng, tenant, service hoặc giao dịch bị phơi nhiễm? |
| Uncertainty | Điều gì vẫn chưa biết và cần kiểm tra thêm? |

### 4.1. Xác minh nguồn và ngữ cảnh

Với test report, xác nhận build ID, commit, suite version, environment ID, test data và run ID. Với incident, xác nhận mốc thời gian, phạm vi ảnh hưởng, phiên bản và kết luận điều tra. Với telemetry, kiểm tra độ trễ, sampling, metric definition và thay đổi dashboard.

Không so sánh trực tiếp hai kết quả nếu môi trường, workload, mẫu số hoặc định nghĩa khác nhau mà chưa điều chỉnh.

### 4.2. Phân biệt sự kiện, giả thuyết và kết luận

Ví dụ:

- **Sự kiện:** p95 latency tăng từ baseline trong 20 phút sau rollout ở một region.
- **Giả thuyết:** truy vấn mới làm tăng lock wait.
- **Bằng chứng bổ sung:** trace và database metric cho thấy thời gian chờ khóa tăng trên endpoint đã thay đổi.
- **Kết luận tạm thời:** thay đổi truy vấn có liên quan đến suy giảm ở region đó.

Ghi riêng các mức này giúp tránh cập nhật risk register bằng một giả thuyết chưa được xác minh như thể đó là nguyên nhân đã kết luận.

### 4.3. Đánh giá bằng chứng trái chiều

Nếu test staging đạt nhưng production telemetry xấu, không chọn một nguồn để bỏ qua nguồn còn lại. Xem khác biệt dữ liệu, tải, cấu hình, dependency và phân đoạn. Nếu hai test độc lập cho kết quả khác nhau, xác định điều kiện khiến kết quả phân kỳ.

Bằng chứng trái chiều thường làm tăng mức bất định và có thể cần test bổ sung. Chỉ giảm rủi ro khi có giải thích hợp lý và được kiểm chứng.

## 5. Cập nhật risk register

### 5.1. Những trường thông tin cần xem lại

Với mỗi rủi ro bị tác động, xem xét:

- Risk ID và mô tả sự kiện không mong muốn.
- Tài sản, hành vi, service và người dùng liên quan.
- Nguyên nhân hoặc điều kiện kích hoạt.
- Khả năng xảy ra và cơ sở đánh giá.
- Tác động nếu xảy ra.
- Phạm vi phơi nhiễm.
- Khả năng phát hiện trước/sau khi ảnh hưởng người dùng.
- Khả năng khôi phục hoặc đảo ngược.
- Kiểm soát hiện tại và bằng chứng hiệu lực.
- Rủi ro còn lại sau kiểm soát.
- Owner, hành động và ngày review tiếp.

Không cập nhật một điểm số tổng hợp mà bỏ mất mô tả và giả định. Hai rủi ro có cùng điểm số có thể cần cách kiểm thử rất khác nhau.

### 5.2. Phân biệt rủi ro vốn có và rủi ro còn lại

Rủi ro vốn có là mức rủi ro trước khi tính các kiểm soát. Rủi ro còn lại là phần rủi ro sau khi đã xem xét kiểm soát và bằng chứng hiện có.

Ví dụ, rủi ro xử lý giao dịch trùng có thể được giảm bởi idempotency, unique constraint, reconciliation và test retry. Nếu incident mới cho thấy consumer có thể xử lý lại event sau timeout, hiệu lực của các kiểm soát cần được xem lại. Không tiếp tục dùng risk rating cũ chỉ vì các test trước đây đã đạt.

### 5.3. Cập nhật khả năng, tác động và bất định

Một bằng chứng mới có thể:

- Tăng khả năng xảy ra vì lỗi đã được tái hiện.
- Tăng tác động vì phạm vi ảnh hưởng lớn hơn dự kiến.
- Tăng phơi nhiễm vì một feature flag được bật cho nhiều tenant.
- Giảm khả năng phát hiện vì monitoring không có tín hiệu phù hợp.
- Giảm khả năng khôi phục vì migration không đảo ngược được.
- Tăng bất định vì kết quả staging và production mâu thuẫn.

Không phải lúc nào cũng cần tăng hoặc giảm một điểm số. Có thể giữ mức risk rating nhưng cập nhật giả định, phạm vi hoặc hành động cần thiết.

### 5.4. Tránh độ chính xác giả

Ma trận xác suất/tác động có thể giúp ưu tiên, nhưng không nên diễn giải một con số như xác suất chính xác nếu không có dữ liệu phù hợp. Với sự kiện hiếm nhưng hậu quả rất lớn, cần dùng ngưỡng chính sách và đánh giá chuyên môn. Ghi rõ mức tin cậy, khoảng bất định và lý do phân loại.

## 6. Từ rủi ro mới đến quyết định phân bổ kiểm thử

Khi rủi ro thay đổi, nhóm cần quyết định kiểm thử nào cần tăng, giữ, chuyển, bổ sung hoặc giảm. Một quyết định phân bổ tốt trả lời:

- Rủi ro nào cần bằng chứng mới?
- Hành vi hoặc điều kiện nào chưa được kiểm tra?
- Test nào hiện có có thể tái sử dụng?
- Cần thêm test ở tầng nào?
- Test chạy ở môi trường, dữ liệu và cấu hình nào?
- Khi nào chạy và kết quả sẽ ảnh hưởng đến quyết định nào?
- Ai sở hữu test, bằng chứng và hành động?

### 6.1. Tăng kiểm thử ở vùng rủi ro tăng

Có thể:

- Bổ sung scenario hoặc boundary case.
- Mở rộng test data theo phân bố thực tế.
- Thêm negative, concurrency, retry hoặc failure-path test.
- Tăng số lần chạy hoặc chạy trên nhiều cấu hình.
- Thêm contract/integration test cho dependency liên quan.
- Chạy performance, security hoặc data integrity test chuyên sâu.
- Tăng tần suất kiểm thử trong giai đoạn rollout.

Tăng số lượng test không phải mục tiêu tự thân. Chọn test có khả năng cung cấp bằng chứng cho rủi ro cụ thể.

### 6.2. Giữ kiểm thử bắt buộc

Các kiểm thử bắt buộc theo policy, hợp đồng, bảo mật, an toàn hoặc yêu cầu release vẫn phải được thực hiện. Phân bổ lại nguồn lực không có nghĩa bỏ các kiểm soát bắt buộc để dành thời gian cho một rủi ro mới.

Nếu không thể chạy một kiểm thử bắt buộc, cần dùng quy trình blocked/waiver phù hợp với thẩm quyền và chính sách. Không tự đổi phân loại test từ hard gate sang advisory.

### 6.3. Chạy lại test hiện có khi bằng chứng thay đổi điều kiện

Không nhất thiết phải viết test mới nếu test hiện có đã bao phủ hành vi nhưng chưa chạy trên phiên bản, dữ liệu hoặc môi trường mới. Khi đó, có thể chạy lại trên đúng điều kiện, xác minh tính hiệu lực của kết quả cũ và ghi rõ phạm vi.

### 6.4. Bổ sung tầng kiểm thử phù hợp

Một incident production có thể cho thấy unit test không đủ vì lỗi nằm ở serialization hoặc retry giữa hai service. Giải pháp có thể là component test, contract test hoặc integration test, không chỉ thêm một unit test mô phỏng chi tiết triển khai.

Chọn tầng kiểm thử sao cho bằng chứng đủ gần với điều kiện gây lỗi nhưng vẫn ổn định, nhanh và có thể bảo trì.

### 6.5. Điều chỉnh thứ tự và thời điểm chạy

Rủi ro cao và test phản hồi nhanh có thể được đưa lên sớm trong pipeline. Test dài hoặc phụ thuộc môi trường đặc biệt có thể chạy ở stage phù hợp, miễn hoàn tất trước gate cần bằng chứng. Khi rủi ro mới xuất hiện trong production, có thể tăng test sau deploy hoặc bổ sung canary check.

### 6.6. Giảm hoặc nghỉ test có căn cứ

Có thể giảm tần suất hoặc retire một test khi:

- Hành vi không còn tồn tại hoặc yêu cầu đã bị loại bỏ.
- Test trùng lặp và có bằng chứng thay thế tốt hơn.
- Rủi ro đã thay đổi do kiến trúc hoặc kiểm soát khác.
- Chi phí bảo trì lớn hơn giá trị bằng chứng trong phạm vi đã đánh giá.

Việc giảm phải có impact analysis, consumer review, owner và quyết định lưu/retire. Không xóa test chỉ vì test fail hoặc làm pipeline chậm.

## 7. Ưu tiên phân bổ khi nguồn lực có hạn

Không phải mọi rủi ro đều có thể được kiểm tra đồng thời. Có thể dùng mô hình ưu tiên định tính:

| Mức ưu tiên | Điều kiện gợi ý | Hành động kiểm thử |
|---|---|---|
| P0 – Khẩn cấp | Rủi ro nghiêm trọng, đang ảnh hưởng người dùng hoặc có thể vi phạm yêu cầu bắt buộc | Điều tra và kiểm tra ngay; cân nhắc dừng rollout/incident response |
| P1 – Cao | Tác động lớn, thay đổi mới, bằng chứng gần đây làm tăng rủi ro | Ưu tiên trong pipeline/release gate; bổ sung test trực tiếp |
| P2 – Trung bình | Có rủi ro đáng kể nhưng phạm vi hoặc khả năng xảy ra giới hạn | Lên kế hoạch test theo sprint hoặc trước mốc release |
| P3 – Thấp | Tác động nhỏ, có kiểm soát khác và chưa có tín hiệu mới | Duy trì kiểm tra định kỳ, theo dõi xu hướng |

Thang này chỉ là ví dụ. Chính sách nội bộ có thể dùng tên và tiêu chí khác. Rủi ro về an toàn, bảo mật, quyền riêng tư hoặc nghĩa vụ bắt buộc cần áp dụng quy trình chuyên môn, không bị hạ ưu tiên chỉ vì ít xảy ra.

### 7.1. Cân nhắc giá trị thông tin của test

Khi chọn giữa nhiều test, xem test nào có khả năng thay đổi quyết định:

- Test có thể phát hiện hậu quả nghiêm trọng mà kiểm soát hiện tại bỏ sót không?
- Test có kiểm tra giả định đang bị nghi ngờ không?
- Kết quả có thể thu được trong thời gian phù hợp không?
- Có thể tái sử dụng test ở nhiều release hoặc service không?
- Test có đủ ổn định để làm gate không?
- Có test khác cung cấp bằng chứng tương đương với chi phí thấp hơn không?

Một test có giá trị thông tin cao có thể được ưu tiên dù số lượng scenario ít. Một test tốn kém nhưng kiểm tra rủi ro hiếm và nghiêm trọng có thể cần chạy trước release thay vì trong mọi commit.

### 7.2. Không để ưu tiên làm mất tính đại diện

Chỉ chạy test trên vùng dễ nhất có thể tạo ra kết quả nhanh nhưng không đại diện. Nếu rủi ro phụ thuộc dữ liệu lớn, concurrency, tenant hoặc khu vực địa lý, phải bảo đảm test được phân bổ tới điều kiện đó ở một giai đoạn phù hợp.

## 8. Liên kết thay đổi với impact analysis và traceability

### 8.1. Lập bản đồ thay đổi

Với mỗi change, ghi:

- Change ID, commit/build và thời điểm.
- Thành phần, API, schema, config hoặc dependency bị thay đổi.
- Service provider và consumer liên quan.
- Hành trình nghiệp vụ hoặc dữ liệu bị ảnh hưởng.
- Requirement và risk ID liên quan.
- Test suite hiện có và bằng chứng gần nhất.

### 8.2. Từ impact map đến test selection

Có thể biểu diễn mối liên hệ:

~~~text
Change
  |
  +--> Component / API / Data / Config
             |
             +--> Consumer / User Journey
                        |
                        +--> Requirement
                        |       |
                        |       +--> Risk
                        |                |
                        |                +--> Test suite / Test ID
                        |                |
                        |                +--> Evidence / Result
                        |
                        +--> Monitoring / Operational control
~~~

Traceability giúp xác định test nào bị ảnh hưởng và rủi ro nào chưa có bằng chứng. Nó cũng giúp tránh chạy lại toàn bộ suite khi chỉ một vùng nhỏ thay đổi, nếu impact analysis đủ tin cậy.

### 8.3. Cập nhật liên kết sau khi thêm hoặc bỏ test

Khi thêm test, liên kết test với risk/requirement và ghi điều kiện chạy. Khi bỏ test, đánh giá xem rủi ro còn được kiểm soát bởi test khác, monitoring hay biện pháp nào. Khi test bị quarantine, traceability phải thể hiện khoảng trống đang tồn tại.

## 9. Quy trình cập nhật rủi ro và phân bổ kiểm thử

### Bước 1: Tiếp nhận tín hiệu

Ghi nhận defect, incident, test result, telemetry anomaly, change request, phản hồi khách hàng hoặc security advisory. Mỗi tín hiệu cần nguồn, thời điểm, phạm vi và người gửi.

### Bước 2: Xác minh bằng chứng

Kiểm tra phiên bản, điều kiện, dữ liệu, độ tin cậy và khả năng tái hiện. Phân biệt sự kiện, giả thuyết và kết luận. Nếu chưa đủ, tạo hành động bổ sung bằng chứng.

### Bước 3: Xác định rủi ro bị tác động

Liên kết tín hiệu với requirement, service, user journey, dependency và risk ID. Nếu chưa có risk record phù hợp, tạo hoặc đề xuất một rủi ro mới theo quy trình quản lý.

### Bước 4: Đánh giá thay đổi mức rủi ro

Xem lại khả năng, tác động, phơi nhiễm, khả năng phát hiện, khôi phục và bất định. Ghi giả định thay đổi, mức độ tin cậy và lý do cập nhật.

### Bước 5: Chọn hành động kiểm thử

Quyết định chạy lại, mở rộng, bổ sung, chuyển tầng, tăng tần suất, đổi môi trường hoặc giảm test. Xác định kiểm thử bắt buộc và những giới hạn không thể miễn trừ.

### Bước 6: Cập nhật suite và kế hoạch

Tạo hoặc sửa test, cập nhật data/fixture, trigger, thứ tự pipeline, môi trường, owner và expected result. Cập nhật impact map và liên kết traceability.

### Bước 7: Thực thi và thu thập kết quả

Chạy test trên đúng build và điều kiện. Lưu report, log, trace, dữ liệu seed và các trạng thái failed/blocked/not run. Không coi test chưa chạy là đạt.

### Bước 8: Review quyết định và residual risk

Đánh giá bằng chứng mới có giảm bất định hoặc rủi ro không. Nếu rủi ro vẫn cao, đề xuất biện pháp khác như giảm rollout, thêm monitoring, hoãn release hoặc escalation.

### Bước 9: Ghi nhận và theo dõi

Cập nhật risk register, decision log, test ownership và hạn review. Theo dõi hiệu quả của điều chỉnh trong release hoặc chu kỳ tiếp theo.

## 10. Quản lý thay đổi trong test strategy

### 10.1. Ghi lý do cho mọi điều chỉnh có ý nghĩa

Một change record nên nêu:

- Bằng chứng kích hoạt thay đổi.
- Rủi ro và giả định bị tác động.
- Phạm vi test được thêm, sửa, chuyển hoặc bỏ.
- Tác động lên thời gian pipeline, chi phí và môi trường.
- Test bắt buộc vẫn được giữ như thế nào.
- Owner, reviewer và ngày hiệu lực.
- Cách đánh giá hiệu quả sau thay đổi.

### 10.2. Phiên bản hóa test strategy và risk register

Lưu lịch sử thay đổi cho risk rating, suite, test selection rule, gate và ngưỡng. Khi điều tra incident, nhóm cần biết chiến lược và bằng chứng nào đã có tại thời điểm release, không chỉ trạng thái hiện tại.

### 10.3. Phê duyệt thay đổi có ảnh hưởng lớn

Thay đổi làm bỏ test bắt buộc, hạ mức rủi ro, đổi ngưỡng gate hoặc thay đổi bằng chứng tuân thủ cần review bởi vai trò có thẩm quyền. Điều chỉnh nhỏ như bổ sung một test vào suite có thể theo quy trình review kỹ thuật thông thường.

### 10.4. Giữ tính ổn định của pipeline

Không liên tục thay đổi thứ tự và phạm vi test chỉ dựa trên một tín hiệu nhiễu. Có thể dùng ngưỡng xác minh, cửa sổ quan sát hoặc review của test lead trước khi thay đổi chính thức. Với rủi ro khẩn cấp, áp dụng kiểm soát tạm thời ngay nhưng ghi rõ thời hạn và điều kiện review.

## 11. Đánh giá hiệu quả sau khi phân bổ lại kiểm thử

Không đánh giá thành công chỉ bằng số test được thêm. Cần xem thay đổi có cải thiện khả năng phát hiện và quyết định hay không:

| Chỉ số/quan sát | Câu hỏi |
|---|---|
| Risk coverage | Rủi ro mới có test hoặc kiểm soát cung cấp bằng chứng chưa? |
| Detection effectiveness | Test mới có phát hiện lỗi hoặc sai lệch mà trước đây bị bỏ sót không? |
| Escaped defects | Lỗi cùng loại có tiếp tục lọt sau release không? |
| Test stability | Test mới có ổn định và ít false positive không? |
| Feedback time | Thời gian phát hiện rủi ro có phù hợp với mốc quyết định không? |
| Pipeline cost | Thời gian và tài nguyên tăng bao nhiêu, có hợp lý không? |
| Residual risk | Rủi ro còn lại và bất định có giảm không? |
| Operational signals | Monitoring có phát hiện được tình huống mà test không bao phủ không? |
| Maintenance burden | Owner có thể duy trì test và dữ liệu lâu dài không? |

Nếu test mới không cung cấp bằng chứng hữu ích, cần xem lại thiết kế, assertion, dữ liệu hoặc tầng kiểm thử. Nếu suite tăng mạnh nhưng pipeline chậm và flaky, có thể cần tối ưu hoặc chuyển test sang stage khác, miễn không làm mất kiểm soát bắt buộc.

## 12. Ví dụ thực tế

### Ví dụ A: Incident tạo đơn trùng làm thay đổi ưu tiên hồi quy

Một incident cho thấy khi message được gửi lại sau timeout, order consumer tạo hai đơn cho cùng một yêu cầu. Trước đó, suite chỉ kiểm tra một lần publish và một lần consume.

Nhóm xác minh incident bằng correlation ID và dữ liệu đã làm sạch. Risk register được cập nhật để tăng mức rủi ro về idempotency, retry và xử lý đồng thời. Test allocation được điều chỉnh:

- Thêm integration test gửi cùng event nhiều lần.
- Thêm concurrency test cho hai consumer xử lý đồng thời.
- Kiểm tra unique constraint và idempotency key.
- Bổ sung reconciliation test cho dữ liệu trùng.
- Thêm business metric theo dõi duplicate order.

Những test này được đặt trước release gate vì rủi ro liên quan trực tiếp đến giao dịch.

### Ví dụ B: Dependency nâng phiên bản làm tăng rủi ro tương thích

Một thư viện serialization được nâng cấp. Unit test của service vẫn đạt, nhưng contract test của một consumer phát hiện trường optional field được serialize khác trước.

Nhóm cập nhật impact map cho tất cả provider/consumer sử dụng thư viện, không chỉ repository đã nâng cấp. Bổ sung contract compatibility test và test dữ liệu cũ/mới. Những service có consumer quan trọng được ưu tiên chạy trước. Risk rating chỉ giảm sau khi các phiên bản liên quan có bằng chứng tương thích.

### Ví dụ C: Telemetry phát hiện suy giảm theo vùng

Sau rollout, tỷ lệ lỗi tổng thể gần như không đổi nhưng một region có p95 latency tăng mạnh. Trace cho thấy request tới một database replica ở vùng đó chậm hơn.

Nhóm không kết luận toàn bộ dịch vụ suy giảm đồng đều. Họ phân đoạn risk record theo region, thêm test truy vấn trên cấu hình gần với region bị ảnh hưởng và điều chỉnh rollout để giữ vùng đó ở mức traffic giới hạn. Monitoring được bổ sung cho replication lag và latency theo region.

### Ví dụ D: Phản hồi khách hàng chỉ ra tình huống dữ liệu hiếm

Khách hàng báo cáo báo cáo số dư sai khi tài khoản có giao dịch đảo ngược và múi giờ khác nhau. Bộ test hiện tại chỉ dùng dữ liệu giao dịch thông thường.

Domain expert xác nhận quy tắc thời điểm ghi nhận và đảo ngược. Nhóm cập nhật risk register cho tính đúng đắn của báo cáo, bổ sung dataset có timezone, giao dịch bù trừ và thứ tự sự kiện khác nhau. Test được đặt ở service/component và integration level để kiểm tra cả tính toán lẫn đồng bộ dữ liệu.

### Ví dụ E: Security advisory làm thay đổi phạm vi kiểm thử

Một advisory mới liên quan đến thư viện xác thực đang được sử dụng. Dù chưa có incident, bằng chứng về lỗ hổng làm tăng rủi ro của các luồng xác thực.

Security owner xác định phiên bản bị ảnh hưởng và phạm vi sử dụng. Nhóm ưu tiên dependency scan, kiểm tra cấu hình, authentication/authorization regression và kiểm thử session/token. Release có thể bị chặn theo policy cho đến khi phiên bản an toàn được triển khai hoặc có quyết định chuyên môn hợp lệ.

### Ví dụ F: Giảm tần suất một suite đã ổn định

Một suite kiểm tra một cấu hình cũ đã được thay thế hoàn toàn. Telemetry, dependency inventory và change history xác nhận cấu hình không còn được triển khai; suite mới kiểm tra đường thay thế.

Nhóm review consumer, rủi ro được bảo vệ và bằng chứng thay thế trước khi giảm tần suất rồi retire suite cũ. Lịch sử report được giữ theo retention policy. Quyết định được ghi trong change log để tránh xóa test chỉ vì không còn thấy lỗi.

## 13. Mẫu ghi nhận cập nhật rủi ro và test allocation

~~~yaml
strategy_adjustment:
  change_id: TEST-STRATEGY-2026-014
  reviewed_at: "2026-11-16"
  trigger:
    type: production-incident
    reference: "INC-4821"
    summary: "Duplicate order after repeated event delivery"

evidence:
  source: "incident-timeline-and-sanitized-traces"
  build_id: "order-5.2.1"
  confidence: high
  limitations:
    - "Concurrency profile not yet reproduced at production scale"

affected_risks:
  - risk_id: ORDER-IDEMPOTENCY-03
    previous_level: medium
    updated_level: high
    rationale: "Observed duplicate transaction in production"
    owner: order-service-owner

test_allocation:
  add:
    - test_id: ORDER-REPLAY-01
      purpose: "Verify duplicate event handling"
      level: integration
      priority: P1
      owner: order-test-owner
    - test_id: ORDER-CONCURRENCY-02
      purpose: "Verify concurrent consumer idempotency"
      level: concurrency
      priority: P1
      owner: order-test-owner
  increase_frequency:
    - suite: "order-critical-regression"
      cadence: "pre-release"
  retain_mandatory:
    - "core-order-regression"
    - "security-required-checks"
  retire: []

approval:
  reviewed_by:
    - order-service-owner
    - test-lead
  effective_from: "order-5.2.2"

follow_up:
  success_criteria:
    - "replay and concurrency tests pass on target build"
    - "duplicate-order signal remains within approved threshold"
  review_date: "2026-11-23"
~~~

Đây là mẫu khái niệm. Risk level, priority, tên owner, ngưỡng và ngày phải phản ánh dữ liệu thực tế. Không dùng giá trị mẫu như đánh giá rủi ro mặc định.

## 14. Mẫu quyết định phân bổ kiểm thử

| Trường | Nội dung cần ghi |
|---|---|
| Trigger | Bằng chứng hoặc thay đổi làm phát sinh review |
| Evidence reference | Link/ID report, incident, trace hoặc change |
| Affected risks | Risk ID và mô tả thay đổi |
| Assumptions changed | Giả định nào không còn đúng |
| Test action | Add, modify, rerun, move, increase cadence, reduce hoặc retire |
| Rationale | Vì sao hành động này cung cấp bằng chứng phù hợp |
| Scope and environment | Build, service, dữ liệu, môi trường và dependency |
| Owner/reviewer | Người thực hiện và người review |
| Mandatory constraints | Những test/gate bắt buộc không được bỏ |
| Effective date | Khi nào thay đổi có hiệu lực |
| Success criteria | Bằng chứng nào cho thấy điều chỉnh có hiệu quả |
| Review date | Khi nào đánh giá lại |

## 15. Những sai lầm thường gặp

- **Chỉ phản ứng với lỗi mới bằng cách thêm test:** bỏ qua nguyên nhân, dependency và rủi ro liên quan.
- **Coi mọi tín hiệu là bằng chứng chắc chắn:** không xác minh nguồn, phiên bản và điều kiện.
- **Chỉ dùng số lượng defect:** bỏ qua severity, exposure và khả năng phát hiện.
- **Cập nhật risk score mà không ghi lý do:** không thể giải thích vì sao ưu tiên thay đổi.
- **Không liên kết risk với test:** nhóm không biết test nào bảo vệ rủi ro mới.
- **Chạy lại toàn bộ suite cho mọi thay đổi:** lãng phí tài nguyên và làm chậm phản hồi.
- **Chỉ chạy test mới mà bỏ regression cũ:** tạo khoảng trống ở hành vi đã ổn định.
- **Hạ mức kiểm thử bắt buộc để dành tài nguyên:** vi phạm policy và che giấu rủi ro.
- **Tăng test mà không có owner:** suite nhanh chóng lỗi thời hoặc flaky.
- **Thay đổi liên tục theo telemetry nhiễu:** pipeline mất ổn định và khó so sánh.
- **Không phân biệt giả thuyết với nguyên nhân đã xác nhận:** quyết định sai phạm vi.
- **Retire test không review consumer:** làm mất bằng chứng mà nhóm khác đang sử dụng.
- **Không đánh giá tác động lên thời gian pipeline:** điều chỉnh làm chậm release mà không tăng giá trị.
- **Không theo dõi hiệu quả sau điều chỉnh:** không biết test mới có giảm rủi ro hay chỉ tăng hoạt động.

## 16. Checklist cập nhật rủi ro và phân bổ kiểm thử

### Khi tiếp nhận bằng chứng mới

- [ ] Nguồn, thời điểm, phiên bản và phạm vi bằng chứng được ghi.
- [ ] Độ tin cậy, tính liên quan và giới hạn được đánh giá.
- [ ] Sự kiện, giả thuyết và kết luận được phân biệt.
- [ ] Bằng chứng trái chiều được xem xét.
- [ ] Dữ liệu nhạy cảm được bảo vệ.

### Khi cập nhật rủi ro

- [ ] Risk ID, requirement, service và user journey liên quan được xác định.
- [ ] Khả năng, tác động, exposure, detection và recovery được xem lại.
- [ ] Giả định cũ và giả định mới được ghi.
- [ ] Rủi ro vốn có và rủi ro còn lại được phân biệt.
- [ ] Owner và ngày review tiếp được cập nhật.

### Khi phân bổ lại kiểm thử

- [ ] Test action gắn với rủi ro cụ thể.
- [ ] Đã xem xét tái sử dụng test hiện có trước khi viết mới.
- [ ] Tầng, dữ liệu, môi trường, tần suất và thứ tự chạy phù hợp.
- [ ] Test bắt buộc và hard gate được giữ.
- [ ] Test bị giảm hoặc retire có impact analysis và phê duyệt phù hợp.
- [ ] Có owner, reviewer và expected result.

### Sau khi điều chỉnh

- [ ] Test chạy trên đúng build và điều kiện.
- [ ] Report và artifact có thể truy xuất.
- [ ] Risk register và traceability được cập nhật.
- [ ] Có tiêu chí đánh giá hiệu quả và ngày review.
- [ ] Theo dõi tác động lên pipeline, độ ổn định và chi phí.
- [ ] Rủi ro còn lại hoặc khoảng trống chưa giải quyết được công khai.

## Kết luận

Cập nhật rủi ro và phân bổ kiểm thử theo bằng chứng mới là vòng phản hồi liên tục giữa thay đổi, kết quả kiểm thử, defect, incident, telemetry và quyết định chất lượng. Nhóm cần xác minh bằng chứng, phân biệt sự kiện với giả thuyết, cập nhật risk register và impact map, rồi chọn hành động kiểm thử có giá trị thông tin phù hợp. Việc thêm, sửa, chạy lại, chuyển tầng, tăng tần suất hoặc retire test phải có lý do, owner, ràng buộc và tiêu chí đánh giá. Khi test bắt buộc được bảo toàn, quyết định được phiên bản hóa và hiệu quả được review, chiến lược kiểm thử có thể thích ứng với rủi ro thực tế mà vẫn duy trì tính nhất quán và khả năng truy vết.
