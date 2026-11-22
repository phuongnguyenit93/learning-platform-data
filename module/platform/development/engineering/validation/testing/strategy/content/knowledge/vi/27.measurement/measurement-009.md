# Đo lường: Đọc xu hướng theo phiên bản và ghi rõ điều kiện so sánh

## 1. Vì sao phải ghi điều kiện khi so sánh phiên bản?

Đo lường chất lượng qua nhiều phiên bản giúp nhóm nhận biết sản phẩm đang cải thiện, suy giảm hay giữ ổn định. Tuy nhiên, hai con số chỉ có ý nghĩa so sánh khi chúng được tạo ra trong những điều kiện đủ tương đồng hoặc khi khác biệt đã được ghi nhận và xử lý trong phân tích.

Ví dụ, tỷ lệ test pass tăng từ 94% lên 98% có thể trông như một cải thiện rõ rệt. Nhưng nếu phiên bản mới chạy ít test hơn, bỏ qua nhóm test chậm hoặc dùng môi trường ổn định hơn, mức tăng đó chưa chứng minh chất lượng sản phẩm tốt lên. Tương tự, p95 latency giảm từ 700 ms xuống 500 ms có thể do workload nhẹ hơn, cache đã warm-up hoặc cấu hình tài nguyên được tăng.

Trong **VALIDATION_TESTING_STRATEGY**, đọc xu hướng theo phiên bản cần kết hợp ba việc:

- Xác định metric và cách tính nhất quán giữa các lần đo.
- Ghi rõ điều kiện thực hiện để biết kết quả nào có thể so sánh trực tiếp.
- Diễn giải xu hướng cùng cỡ mẫu, độ biến động, thay đổi phạm vi và giới hạn bằng chứng.

Mục tiêu là tạo ra kết luận có thể kiểm chứng: phiên bản nào được so sánh, trong điều kiện nào, chỉ số thay đổi bao nhiêu, thay đổi đó có ý nghĩa gì và còn yếu tố nào có thể giải thích kết quả.

## 2. Xác định đối tượng và đơn vị so sánh

### 2.1. Phiên bản cần được nhận diện chính xác

Không nên chỉ ghi tên nhánh hoặc nhãn như *latest*, staging hay release candidate. Một kết quả đo nên liên kết với:

- Version hoặc release identifier.
- Build number và commit SHA.
- Artifact/image/package digest nếu có.
- Thời điểm build và triển khai.
- Phiên bản schema hoặc database migration.
- Feature flag và cấu hình quan trọng.
- Tập phiên bản của các dịch vụ phụ thuộc.

Trong hệ thống triển khai từng phần, một release có thể gồm nhiều phiên bản service cùng tồn tại. Cần ghi lại tổ hợp phiên bản thực sự xử lý traffic trong cửa sổ đo.

### 2.2. Chọn đơn vị so sánh phù hợp

Tùy mục tiêu, đơn vị so sánh có thể là:

- Một build với build trước đó.
- Một release candidate với release đã phát hành.
- Các bản phát hành theo tuần hoặc tháng.
- Các cohort người dùng được chuyển sang phiên bản khác nhau.
- Các lần chạy cùng một bộ test trên nhiều commit.
- Các khoảng thời gian trước và sau một thay đổi cấu hình.

Không trộn các đơn vị này trong cùng biểu đồ nếu ý nghĩa khác nhau. Ví dụ, so sánh số liệu theo tuần phản ánh cả thay đổi phiên bản và thay đổi lượng người dùng; so sánh hai build trên cùng workload có kiểm soát tập trung hơn vào khác biệt giữa build.

### 2.3. Ghi rõ phạm vi sản phẩm

Một metric toàn hệ thống có thể che giấu thay đổi ở từng thành phần. Khi cần, tách theo:

- Service, module hoặc component.
- API, endpoint hoặc workflow.
- Nhóm tính năng.
- Nền tảng, browser hoặc thiết bị.
- Tenant, khu vực hoặc nhóm người dùng.
- Suite, loại test hoặc mức độ rủi ro.

Phạm vi cần được giữ ổn định qua các phiên bản hoặc ghi rõ khi thay đổi. Nếu một module được thêm vào phiên bản mới, tổng số defect hoặc test có thể tăng đơn giản vì phạm vi rộng hơn.

## 3. Định nghĩa metric trước khi đọc xu hướng

### 3.1. Một metric cần có hợp đồng đo lường

Với mỗi chỉ số, ghi:

- Tên và mục đích.
- Định nghĩa chính xác.
- Công thức và đơn vị.
- Tử số, mẫu số hoặc cách tổng hợp.
- Nguồn dữ liệu.
- Bộ lọc và quy tắc loại trừ.
- Cửa sổ thời gian.
- Phạm vi thành phần và phiên bản.
- Tần suất thu thập.
- Chủ sở hữu và giới hạn diễn giải.

Ví dụ, “tỷ lệ pass” có thể được tính trên tổng test đã thực thi, trên tổng test được lên kế hoạch hoặc trên tổng test không bị skip. Các cách tính này cho kết quả khác nhau. Báo cáo cần chọn một định nghĩa và duy trì nhất quán.

### 3.2. Không trộn các metric có ý nghĩa khác nhau

| Nhóm | Metric ví dụ | Câu hỏi trả lời |
| --- | --- | --- |
| Kết quả kiểm thử | Pass rate, fail rate, skipped rate | Bộ kiểm thử có đạt kết quả mong đợi không? |
| Độ ổn định test | Flaky rate, rerun rate | Tín hiệu test có đáng tin cậy không? |
| Bao phủ | Requirement coverage, risk coverage, code coverage | Những yêu cầu/rủi ro/phần mã nào đã được kiểm tra? |
| Defect | Defect density, escaped defects, reopen rate | Lỗi được phát hiện ở đâu và có tái diễn không? |
| Hiệu năng | p50/p95/p99 latency, throughput, error rate | Hệ thống đáp ứng tải như thế nào? |
| Độ tin cậy | Availability, recovery time, failure frequency | Hệ thống duy trì và phục hồi dịch vụ ra sao? |
| Hiệu quả quy trình | Test duration, feedback time, time to triage | Nhóm nhận và xử lý tín hiệu nhanh đến đâu? |

Không nên tạo một điểm chất lượng duy nhất bằng cách cộng các metric khác đơn vị nếu chưa có mô hình trọng số và mục đích rõ ràng. Một điểm tổng hợp có thể che giấu một tiêu chí bắt buộc đang suy giảm.

### 3.3. Giữ định nghĩa ổn định qua thời gian

Nếu thay đổi cách đếm hoặc nguồn dữ liệu, hãy:

1. Ghi phiên bản định nghĩa metric.
2. Xác định thời điểm thay đổi.
3. Tính lại dữ liệu lịch sử nếu có thể và hợp lệ.
4. Nếu không thể tính lại, đánh dấu điểm đứt gãy trong chuỗi thời gian.
5. Tránh nối hai chuỗi như thể chúng có cùng cách đo.

Ví dụ, nếu phiên bản mới bổ sung test vào suite nhưng dashboard vẫn dùng tổng test cũ làm mẫu số, pass rate sẽ không phản ánh phạm vi mới.

## 4. Thiết lập baseline và điểm tham chiếu

### 4.1. Baseline là gì?

Baseline là tập kết quả hoặc điều kiện tham chiếu dùng để so sánh. Baseline có thể là:

- Phiên bản đã được chấp nhận gần nhất.
- Một build ổn định trước khi thay đổi.
- Giá trị trung vị của một số lần chạy có điều kiện tương đương.
- Mục tiêu chất lượng đã được phê duyệt.
- Cohort hoặc môi trường đối chứng.

Baseline cần được gắn với phiên bản, cấu hình, dữ liệu và phương pháp đo. Không chọn một lần chạy bất thường làm baseline chỉ vì nó tạo ra kết quả thuận lợi.

### 4.2. Chọn baseline phù hợp với câu hỏi

| Câu hỏi | Baseline phù hợp |
| --- | --- |
| Thay đổi code có làm tăng lỗi test không? | Build ngay trước thay đổi, chạy cùng suite và môi trường |
| Release mới có cải thiện hiệu năng không? | Phiên bản ổn định trước đó, cùng workload và cấu hình đo |
| Chất lượng có đáp ứng mục tiêu không? | Ngưỡng hoặc SLO đã được phê duyệt |
| Tỷ lệ defect có giảm qua các quý không? | Chuỗi dữ liệu lịch sử với định nghĩa và phạm vi nhất quán |
| Tính năng mới ảnh hưởng nhóm người dùng nào? | Cohort tương đương hoặc nhóm đối chứng thích hợp |

### 4.3. Baseline không phải lúc nào cũng là một con số

Với metric biến động, baseline có thể là phân phối hoặc dải tham chiếu:

- Trung vị và percentile của nhiều lần chạy.
- Khoảng biến thiên thông thường.
- Control limits từ dữ liệu quá trình ổn định.
- Phân phối theo nhóm người dùng hoặc workload.

Một giá trị đơn lẻ không thể hiện độ biến động. Ví dụ, p95 500 ms trong một lần chạy không cho biết hệ thống thường ổn định quanh mức đó hay dao động từ 300 đến 900 ms.

## 5. Ghi điều kiện so sánh

### 5.1. Các yếu tố cần ghi nhận

Một bản ghi đo lường theo phiên bản nên có tối thiểu:

| Nhóm điều kiện | Thông tin cần ghi |
| --- | --- |
| Build | Version, commit, artifact digest, build ID |
| Triển khai | Thời điểm, rollout percentage, instance/region và tập phiên bản service |
| Môi trường | Test/staging/performance, hạ tầng, OS, runtime, database và network |
| Cấu hình | Feature flags, timeout, retry, cache, pool, limits và resource allocation |
| Dữ liệu | Dataset ID/version, quy mô, phân phối và trạng thái ban đầu |
| Workload | Request rate, concurrency, mix endpoint, thời lượng và warm-up |
| Bộ test | Suite/version, số test dự kiến, test thêm/bỏ, tag và filter |
| Công cụ | Runner, browser/device, agent version, collector và cách tính |
| Thời gian | Cửa sổ đo, timezone, lịch chạy và sự kiện bảo trì |
| Phụ thuộc | Provider, sandbox, broker, service ngoài và trạng thái |

Không phải metric nào cũng cần tất cả trường. Hãy xác định các yếu tố có thể ảnh hưởng đến kết quả và ghi chúng một cách nhất quán.

### 5.2. Điều kiện tương đương và điều kiện khác biệt

Phân loại mỗi yếu tố:

- **Tương đương:** giữ cùng giá trị hoặc cùng quy trình giữa các phiên bản.
- **Khác biệt có chủ đích:** thay đổi để kiểm tra tác động của một yếu tố.
- **Khác biệt ngoài ý muốn:** drift môi trường, tải nền hoặc cấu hình không được kiểm soát.
- **Không biết:** thiếu dữ liệu để xác nhận.

Nếu khác biệt là một phần của thử nghiệm, ghi nó như biến độc lập. Nếu khác biệt ngoài ý muốn có thể ảnh hưởng kết quả, cần chạy lại, phân tích riêng hoặc giảm mức độ chắc chắn của kết luận.

### 5.3. Ma trận điều kiện so sánh

~~~text
Phiên bản A:
  Build / commit:
  Environment:
  Configuration:
  Dataset:
  Workload / test suite:
  Tools / runner:
  Measurement window:

Phiên bản B:
  Build / commit:
  Environment:
  Configuration:
  Dataset:
  Workload / test suite:
  Tools / runner:
  Measurement window:

Điều kiện tương đương:
Khác biệt có chủ đích:
Khác biệt ngoài ý muốn:
Thông tin chưa có:
Ảnh hưởng dự kiến tới kết quả:
~~~

## 6. Chuẩn hóa để so sánh công bằng

### 6.1. Dùng tỷ lệ thay cho số đếm khi quy mô khác nhau

Số defect tăng từ 20 lên 30 không nhất thiết có nghĩa chất lượng giảm nếu số lượng giao dịch hoặc phạm vi kiểm thử tăng gấp đôi. Khi phù hợp, chuẩn hóa theo mẫu số:

- Defect trên 1.000 user journey.
- Lỗi request trên tổng request hợp lệ.
- Test fail trên tổng test thực thi.
- Defect theo module hoặc theo đơn vị thay đổi.
- Incident trên một khoảng thời gian vận hành.

Ví dụ:

\[
\text{Error rate} = \frac{\text{Số request lỗi}}{\text{Tổng request hợp lệ}} \times 100\%
\]

Nếu phiên bản A có 200 lỗi trên 100.000 request, error rate là 0,2%. Phiên bản B có 300 lỗi trên 300.000 request, error rate là 0,1%. Số lỗi tuyệt đối tăng nhưng tỷ lệ giảm. Cần vẫn xem xét loại lỗi và mức độ nghiêm trọng, vì tỷ lệ tổng có thể che một nhóm lỗi nghiêm trọng.

### 6.2. Giữ cùng mẫu số và quy tắc loại trừ

Mẫu số cần có cùng ý nghĩa. Ví dụ:

- Không tính skipped test như pass.
- Không loại timeout hoặc request lỗi khỏi mẫu số latency nếu chúng thuộc workload cần đánh giá.
- Không trộn request health check với request nghiệp vụ nếu mục tiêu là đo user journey.
- Không thay đổi định nghĩa defect hoặc cách gộp duplicate mà không ghi nhận.

Nếu mẫu số thay đổi, công bố cả số tuyệt đối và tỷ lệ cùng cách tính.

### 6.3. Chuẩn hóa theo quy mô và cơ cấu

Khi workload hoặc nhóm người dùng khác nhau, có thể cần phân tầng hoặc chuẩn hóa theo cơ cấu:

- Tỷ lệ theo endpoint hoặc loại giao dịch.
- Latency theo payload size hoặc request class.
- Defect theo module hoặc mức độ thay đổi.
- Pass rate theo suite và mức rủi ro.
- Lỗi theo region, device hoặc browser.

Một tỷ lệ tổng hợp có thể thay đổi chỉ vì cơ cấu nhóm thay đổi. Vì vậy, cần xem cả số tổng và số theo từng nhóm.

## 7. Phân tầng dữ liệu và tránh kết luận sai

### 7.1. So sánh theo cohort

Cohort là nhóm đối tượng có đặc điểm hoặc điều kiện chung. Có thể phân nhóm theo:

- Phiên bản ứng dụng.
- Nhóm người dùng hoặc tenant.
- Region hoặc môi trường.
- Loại thiết bị/browser.
- Endpoint hoặc workflow.
- Mức độ tải.
- Nhóm test hoặc risk category.

So sánh trong cùng cohort giúp hạn chế việc kết quả tổng bị chi phối bởi thay đổi cơ cấu.

### 7.2. Ví dụ về thay đổi cơ cấu

Giả sử phiên bản B có tỷ lệ lỗi tổng cao hơn A. Khi tách theo loại request:

| Loại request | A: tổng số | A: lỗi | A: tỷ lệ lỗi | B: tổng số | B: lỗi | B: tỷ lệ lỗi |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Đọc dữ liệu (ít lỗi) | 9.000 | 90 | 1,0% | 2.000 | 30 | 1,5% |
| Giao dịch (nhiều lỗi hơn) | 1.000 | 50 | 5,0% | 8.000 | 440 | 5,5% |
| **Tổng** | **10.000** | **140** | **1,4%** | **10.000** | **470** | **4,7%** |

Trong ví dụ này, tỷ lệ lỗi tăng ở cả hai nhóm và cơ cấu workload cũng thay đổi đáng kể. Phân tầng cho thấy cả hai yếu tố đều cần điều tra. Nếu chỉ nhìn tổng, nhóm có thể không biết thay đổi đến từ workload hay từ lỗi trong từng nhóm.

Trong những trường hợp khác, tỷ lệ tổng có thể đi ngược xu hướng của từng nhóm do thay đổi trọng số cohort. Đây là một dạng nghịch lý Simpson. Cách phòng tránh là công bố cơ cấu nhóm, phân tích từng cohort và chỉ tổng hợp theo trọng số được xác định rõ.

### 7.3. Không gộp các nhóm có hành vi khác nhau

Ví dụ, latency desktop và mobile có thể khác do network và thiết bị. Nếu tỷ lệ mobile tăng ở phiên bản B, p95 tổng có thể tăng dù latency của từng nhóm không đổi. Hãy báo cáo theo nhóm hoặc chuẩn hóa theo cơ cấu thiết bị khi mục tiêu là so sánh bản thân ứng dụng.

## 8. Đọc xu hướng theo loại metric

### 8.1. Pass rate và fail rate

Pass rate:

\[
\text{Pass rate} = \frac{\text{Số test pass}}{\text{Số test đã thực thi hợp lệ}} \times 100\%
\]

Khi so sánh phiên bản, cần ghi:

- Suite và phiên bản test code.
- Tổng test dự kiến, thực thi, pass, fail, skipped và blocked.
- Test mới, test bị xóa hoặc được quarantine.
- Thay đổi về môi trường và dữ liệu.
- Test flaky và số lần retry.

Pass rate tăng do bỏ test fail hoặc chuyển test sang skipped không phải cải thiện chất lượng. Báo cáo cần giữ riêng số lượng và trạng thái test.

### 8.2. Flaky rate

Flaky rate phản ánh tỷ lệ test có kết quả không ổn định trong điều kiện được lặp lại:

\[
\text{Flaky rate} = \frac{\text{Số test được xác định flaky}}{\text{Số test được đánh giá}} \times 100\%
\]

Phải định nghĩa rõ “flaky” được xác định qua bao nhiêu lần chạy, trong cửa sổ nào và cách xử lý retry. Một test fail rồi pass khi rerun không tự động là flaky; có thể là lỗi thật phụ thuộc trạng thái hoặc lỗi hạ tầng.

### 8.3. Defect và escaped defect

Khi so sánh defect:

- Ghi phạm vi tìm defect và giai đoạn phát hiện.
- Phân loại severity và module.
- Nêu cách gộp defect trùng.
- Chuẩn hóa theo quy mô release hoặc lượng sử dụng nếu phù hợp.
- Theo dõi defect reopen và defect tái xuất hiện riêng.

Defect được phát hiện nhiều hơn có thể phản ánh kiểm thử tốt hơn hoặc chất lượng sản phẩm thấp hơn. Cần xem cả phạm vi kiểm thử, mức độ bao phủ và defect lọt tới người dùng.

### 8.4. Coverage

Code coverage, requirement coverage và risk coverage trả lời các câu hỏi khác nhau. Khi thay đổi test suite hoặc công cụ đo, số coverage có thể tăng/giảm do cách tính thay đổi.

Ghi rõ:

- Loại coverage.
- Phạm vi và mẫu số.
- Công cụ và phiên bản.
- Generated code hoặc code bị loại trừ.
- Test mới/xóa và mapping yêu cầu/rủi ro.

Coverage cao không tự chứng minh test có oracle tốt hoặc phát hiện được lỗi.

### 8.5. Hiệu năng và độ tin cậy

Với latency, throughput, error rate và availability, ghi:

- Workload, request mix và concurrency.
- Warm-up và thời lượng đo.
- Tài nguyên, autoscaling và cache state.
- Percentile, số mẫu và khoảng biến động.
- Lỗi timeout và request bị loại.
- Tải nền và sự kiện hạ tầng.

Không so sánh p95 từ một lần chạy ngắn với p95 từ một cửa sổ dài mà không nêu khác biệt.

## 9. Cỡ mẫu, độ biến động và ý nghĩa của thay đổi

### 9.1. Một lần chạy không đại diện cho xu hướng

Nhiều metric có biến động ngẫu nhiên. Với test suite, biến động có thể đến từ concurrency, lịch chạy, network hoặc phụ thuộc. Với production, biến động đến từ traffic, người dùng và tải nền.

Khi có thể:

- Chạy lặp nhiều lần trong điều kiện tương đương.
- Báo số lần chạy và số quan sát.
- Dùng median/percentile hoặc khoảng biến động phù hợp.
- Giữ dữ liệu thô để điều tra.
- So sánh cùng thời điểm hoặc cùng loại workload nếu có tính mùa vụ.

### 9.2. Cỡ mẫu và khoảng bất định

Một tỷ lệ 0% lỗi trên 20 request có ý nghĩa khác 0% lỗi trên 2 triệu request. Khi số mẫu nhỏ, khoảng bất định rộng hơn. Với tỷ lệ, có thể dùng khoảng tin cậy nhị thức hoặc phương pháp phù hợp với cách lấy mẫu; không nên chỉ báo một phần trăm đơn lẻ.

Với latency, percentile ở mẫu nhỏ có thể rất không ổn định, đặc biệt p99. Cần số quan sát đủ lớn theo mục tiêu và ghi rõ cách tính percentile.

### 9.3. Ý nghĩa thống kê và ý nghĩa thực tiễn

Một khác biệt có thể có ý nghĩa thống kê nhưng quá nhỏ để ảnh hưởng người dùng. Ngược lại, một thay đổi có tác động lớn nhưng chưa đủ mẫu để đạt ý nghĩa thống kê vẫn cần được điều tra.

Hãy xem:

- Độ lớn thay đổi tuyệt đối và tương đối.
- Khoảng bất định.
- Ngưỡng chất lượng/SLO.
- Mức độ nghiêm trọng của nhóm lỗi.
- Chi phí hoặc ảnh hưởng thực tế.

Không dùng p-value hoặc một ngưỡng thống kê duy nhất làm quyết định chất lượng. Kết luận cần kết hợp dữ liệu, rủi ro và tiêu chí đã thống nhất.

### 9.4. Control chart cho quá trình ổn định

Với metric được thu thập đều đặn, control chart có thể giúp phân biệt biến động thông thường với tín hiệu bất thường. Cần:

- Chọn loại chart phù hợp với dữ liệu.
- Dùng baseline từ quá trình tương đối ổn định.
- Tính control limits theo phương pháp phù hợp.
- Đánh dấu thay đổi phiên bản, cấu hình hoặc môi trường.
- Không diễn giải control limit như ngưỡng chấp nhận nghiệp vụ.

Control limit mô tả biến động của quá trình; specification limit hoặc SLO mô tả mức chất lượng cần đạt. Hai khái niệm này không thay thế nhau.

## 10. Nhận diện yếu tố gây nhiễu

### 10.1. Những thay đổi có thể làm sai lệch so sánh

Các yếu tố thường gặp:

- Hạ tầng, số instance hoặc loại máy khác nhau.
- Dataset hoặc phân phối traffic thay đổi.
- Feature flag hoặc cấu hình khác.
- Browser, OS, runtime hoặc database version đổi.
- Test suite, test data hoặc test harness thay đổi.
- Cache warm/cold, connection pool hoặc autoscaling khác.
- Thời điểm đo trùng giờ cao điểm, bảo trì hoặc sự cố provider.
- Sampling, filter hoặc pipeline tính metric thay đổi.
- Nhiều thay đổi code cùng được triển khai.

### 10.2. Phân biệt tương quan và nguyên nhân

Nếu metric xấu đi ngay sau một release, điều đó tạo giả thuyết về tác động của release nhưng chưa chứng minh release là nguyên nhân. Cần kiểm tra:

- Có thay đổi cấu hình hoặc hạ tầng đồng thời không?
- Có thay đổi workload hoặc nhóm người dùng không?
- Có sự cố dependency bên ngoài không?
- Có đủ dữ liệu trước và sau không?
- Có thể chạy lại trên cùng điều kiện hoặc so sánh cohort đối chứng không?

Khi cần xác định quan hệ nhân quả, có thể dùng canary, A/B test, rollout theo cohort hoặc benchmark có kiểm soát. Phải nêu giới hạn thiết kế và rủi ro khi nhóm không được phân bổ ngẫu nhiên.

### 10.3. Thay đổi nhiều yếu tố cùng lúc

Nếu một release thay đổi code, database, cache và hạ tầng cùng lúc, xu hướng tổng không cho biết yếu tố nào tạo ra khác biệt. Khi điều tra, có thể:

- Tách từng thay đổi trong benchmark.
- Dùng rollout từng bước.
- So sánh component metric.
- Chạy ablation hoặc thử nghiệm có kiểm soát.
- Ghi lại các yếu tố không thể tách riêng.

Không nên tuyên bố một commit cụ thể gây ra thay đổi khi nhiều biến cùng thay đổi và không có bằng chứng phân biệt.

## 11. Đọc xu hướng theo thời gian và theo release

### 11.1. Chuỗi thời gian cần có điểm đánh dấu

Biểu đồ xu hướng nên đánh dấu:

- Release/build được triển khai.
- Feature flag thay đổi.
- Migration hoặc thay đổi cấu hình.
- Incident hoặc thời gian bảo trì.
- Thay đổi cách đo hoặc nguồn dữ liệu.
- Thay đổi traffic/workload lớn.

Điểm đánh dấu giúp người đọc tránh diễn giải một bước nhảy trên biểu đồ như tác động của phiên bản khi thực tế có thể là một sự kiện khác.

### 11.2. So sánh trước/sau

Khi dùng phép so sánh trước/sau:

- Chọn cửa sổ đủ dài để phản ánh hoạt động bình thường.
- Tránh gộp thời gian rollout và thời gian ổn định nếu mục tiêu là đo steady state.
- So sánh cùng ngày trong tuần hoặc khung giờ nếu traffic có tính mùa vụ.
- Nêu thay đổi cấu hình, tải và dữ liệu.
- Xem cả metric tổng và theo cohort.

Nếu phiên bản được rollout dần, cửa sổ “sau release” có thể chứa nhiều version cùng lúc. Ghi tỷ lệ traffic theo version hoặc chờ rollout hoàn tất trước khi kết luận.

### 11.3. Theo dõi cohort phiên bản

Trong hệ thống có nhiều phiên bản chạy đồng thời, gắn metric với version thực tế xử lý request thay vì chỉ gắn với thời điểm triển khai. Điều này cho phép so sánh cohort đang chạy phiên bản A và B trong cùng một khoảng thời gian, nếu các cohort đủ tương đồng.

Nếu nhóm người dùng tự chọn phiên bản hoặc được rollout theo tiêu chí khác nhau, cohort có thể không tương đương. Cần xem cách phân bổ và các khác biệt ban đầu.

## 12. Ví dụ tổng hợp: so sánh hiệu năng giữa hai phiên bản

### 12.1. Mục tiêu

Đánh giá xem build B có cải thiện p95 latency của API tìm kiếm so với build A hay không.

### 12.2. Điều kiện được giữ tương đương

- Cùng loại máy và số instance.
- Cùng database engine, schema và cấu hình connection pool.
- Cùng dataset snapshot và index.
- Cùng request mix và concurrency.
- Cùng warm-up, thời lượng đo và công cụ.
- Cùng cách lọc request và tính percentile.

### 12.3. Kết quả minh họa

| Chỉ số | Build A | Build B |
| --- | ---: | ---: |
| Request hợp lệ | 50.000 | 50.000 |
| p50 latency | 180 ms | 160 ms |
| p95 latency | 620 ms | 510 ms |
| p99 latency | 1.100 ms | 980 ms |
| Error rate | 0,30% | 0,28% |
| CPU trung bình | 62% | 64% |

Trong điều kiện được giữ tương đương, các percentile latency và error rate đều cải thiện trong lần đo này. CPU trung bình tăng nhẹ, vì vậy cần kiểm tra thêm mức saturation và số lần chạy lặp trước khi kết luận cải thiện ổn định.

### 12.4. Cách diễn giải

Một kết luận có trách nhiệm có thể viết:

> Trong ba lần chạy với cùng dataset, request mix và cấu hình hạ tầng, build B có p95 thấp hơn build A ở cả ba lần. Kết quả quan sát được cho thấy cải thiện latency trong phạm vi benchmark này. Cần tiếp tục theo dõi CPU và xác nhận trên workload production-like trước khi suy rộng sang môi trường vận hành.

Không nên viết “build B nhanh hơn 18% trong production” nếu chỉ có một benchmark staging và chưa có dữ liệu production tương đương.

## 13. Mẫu báo cáo xu hướng theo phiên bản

~~~text
Mục tiêu so sánh:
Metric và định nghĩa:
Ngưỡng/SLO liên quan:

Phiên bản A:
- Version / build / commit:
- Artifact:
- Environment / configuration:
- Dataset / workload / test suite:
- Measurement window:

Phiên bản B:
- Version / build / commit:
- Artifact:
- Environment / configuration:
- Dataset / workload / test suite:
- Measurement window:

Điều kiện tương đương:
Khác biệt có chủ đích:
Khác biệt ngoài ý muốn / chưa biết:

Kết quả A:
- Giá trị / mẫu số / số quan sát:
- Phân phối hoặc khoảng biến động:

Kết quả B:
- Giá trị / mẫu số / số quan sát:
- Phân phối hoặc khoảng biến động:

Thay đổi tuyệt đối:
Thay đổi tương đối:
Phân tích theo cohort:
Yếu tố gây nhiễu:
Mức độ tin cậy:
Kết luận trong phạm vi:
Giới hạn không thể suy rộng:
Hành động tiếp theo / owner:
~~~

## 14. Các sai lầm thường gặp khi đọc xu hướng

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| So sánh version không rõ build | Không biết artifact nào tạo ra số liệu | Gắn build, commit và artifact digest |
| Chỉ nhìn phần trăm tổng | Che giấu thay đổi mẫu số hoặc cơ cấu | Báo cả số tuyệt đối, mẫu số và cohort |
| Thay đổi suite nhưng không ghi | Pass rate không còn cùng ý nghĩa | Version hóa suite và định nghĩa metric |
| So sánh workload khác nhau | Gán sai thay đổi cho phiên bản | Giữ workload hoặc phân tầng/chuẩn hóa |
| Chỉ dùng một lần chạy | Bị chi phối bởi biến động ngẫu nhiên | Chạy lặp và báo độ phân tán |
| Bỏ request lỗi khỏi latency | Làm kết quả có vẻ tốt hơn | Công bố quy tắc loại trừ và error rate |
| Không đánh dấu incident/deploy | Đọc sai điểm thay đổi trên chuỗi thời gian | Gắn sự kiện vào biểu đồ |
| Gọi tương quan là nguyên nhân | Kết luận quá mức | Dùng thử nghiệm có kiểm soát hoặc nêu giới hạn |
| Dùng control limit như SLO | Nhầm biến động quá trình với ngưỡng chất lượng | Báo riêng control limits và specification limits |
| Gộp mọi metric thành một score | Che giấu tiêu chí bắt buộc suy giảm | Giữ metric riêng và giải thích trọng số nếu tổng hợp |

## 15. Checklist đọc xu hướng theo phiên bản

- [ ] Phiên bản, build, commit và artifact được nhận diện chính xác.
- [ ] Phạm vi sản phẩm và đơn vị so sánh được xác định.
- [ ] Metric có định nghĩa, công thức, nguồn và mẫu số rõ ràng.
- [ ] Baseline phù hợp với câu hỏi và có nhiều quan sát khi cần.
- [ ] Điều kiện môi trường, cấu hình, dữ liệu, workload và công cụ được ghi lại.
- [ ] Khác biệt tương đương, có chủ đích, ngoài ý muốn và chưa biết được phân loại.
- [ ] Mẫu số và quy tắc loại trừ được giữ nhất quán hoặc công bố rõ.
- [ ] Kết quả được phân tầng theo cohort khi cơ cấu có thể ảnh hưởng.
- [ ] Cỡ mẫu, độ biến động và khoảng bất định được xem xét.
- [ ] Thay đổi metric hoặc pipeline được đánh dấu trong chuỗi thời gian.
- [ ] Incident, rollout, migration và thay đổi cấu hình được chú thích.
- [ ] Tương quan không bị diễn giải thành nguyên nhân nếu thiếu thiết kế phù hợp.
- [ ] Kết luận nêu rõ phạm vi, mức tin cậy và giới hạn suy rộng.
- [ ] Hành động tiếp theo có owner và cách xác nhận.

Đọc xu hướng theo phiên bản có ý nghĩa khi nhóm biết rõ mỗi con số được tạo ra trong điều kiện nào. Giữ định nghĩa metric, baseline, mẫu số và điều kiện đo nhất quán; phân tầng khi cơ cấu thay đổi; đồng thời công bố cỡ mẫu và giới hạn giúp nhóm phân biệt cải thiện thực sự với khác biệt do môi trường hoặc cách đo. Một báo cáo tốt không chỉ cho biết chỉ số tăng hay giảm mà còn giải thích mức độ tin cậy và phạm vi mà kết luận có thể áp dụng.
