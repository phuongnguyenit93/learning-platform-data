# Phân biệt kiểm tra bắt buộc với kết quả chỉ mang tính tham khảo

Pipeline CI/CD có thể tạo ra nhiều kết quả: build thành công hay thất bại, unit test, coverage, phân tích mã nguồn, quét lỗ hổng, kiểm tra license, kiểm tra chất lượng API và báo cáo hiệu năng. Nếu mọi kết quả đều được coi là điều kiện chặn merge, nhóm có thể bị kẹt vì một cảnh báo nhỏ hoặc một báo cáo không liên quan trực tiếp đến thay đổi. Ngược lại, nếu mọi kiểm tra đều chỉ mang tính tham khảo, lỗi nghiêm trọng có thể đi qua cổng tích hợp và đến môi trường phát hành.

Một **cổng chất lượng** (quality gate) là tập hợp điều kiện được dùng để quyết định một thay đổi có được chuyển sang bước tiếp theo hay không. Trong cổng đó, cần phân biệt rõ:

- **Kiểm tra bắt buộc (required check):** phải đạt theo chính sách trước khi được merge, phát hành hoặc triển khai.
- **Kết quả tham khảo (advisory result):** cung cấp thông tin để nhóm đánh giá và cải thiện, nhưng bản thân kết quả đó không chặn luồng.

Phân loại này cần được công bố trước, gắn với mục đích kiểm soát và có chủ sở hữu. Một kết quả màu đỏ không tự động có nghĩa là bắt buộc chặn; một kết quả màu xanh cũng không chứng minh mọi rủi ro đã được loại bỏ.

## 1. Cổng chất lượng nằm ở đâu trong luồng CI/CD?

Một thay đổi thường đi qua nhiều điểm quyết định:

1. **Trước merge:** xác minh thay đổi có thể build, test và đáp ứng các chính sách cần thiết để nhập vào nhánh chung.
2. **Sau merge:** xác minh trạng thái nhánh chính, tạo artifact và kiểm tra các điều kiện của bản build tích hợp.
3. **Trước phát hành:** kiểm tra phiên bản, dependency, bảo mật, license, chữ ký và bằng chứng nguồn gốc artifact.
4. **Trước triển khai production:** xác minh phê duyệt, môi trường đích, kế hoạch triển khai và các điều kiện vận hành.
5. **Sau triển khai:** kiểm tra health, smoke test, telemetry và điều kiện tiếp tục hoặc quay lui.

Một kiểm tra có thể bắt buộc ở một điểm nhưng chỉ tham khảo ở điểm khác. Ví dụ, báo cáo coverage toàn repository có thể được dùng để theo dõi xu hướng trên mỗi pull request; nhưng chính sách coverage của mã mới có thể là điều kiện bắt buộc trước merge. Tương tự, kết quả scan bảo mật ở nhánh phát triển có thể chỉ cảnh báo đối với một lỗ hổng mức thấp đã được chấp nhận có thời hạn, trong khi phát hiện secret bị lộ hoặc lỗ hổng nghiêm trọng có thể chặn phát hành.

### Phân biệt check, gate và quyết định

- **Check:** một lần kiểm tra cụ thể, chẳng hạn unit-tests, dependency-scan hoặc license-audit.
- **Gate:** tập hợp các check và quy tắc đánh giá chúng.
- **Decision:** kết luận cho phép hoặc không cho phép chuyển bước, ví dụ merge được, cần sửa hoặc cần phê duyệt ngoại lệ.

Một gate có thể gồm nhiều check. Có check bắt buộc, check chỉ tham khảo và check chỉ áp dụng khi điều kiện nhất định được thỏa mãn. Không nên đồng nhất tên job trong CI với toàn bộ chính sách chất lượng.

## 2. Kiểm tra bắt buộc là gì?

Một check là bắt buộc khi kết quả của nó là điều kiện để hệ thống cho phép một hành động quan trọng. Nếu check thất bại, chưa hoàn tất hoặc không có bằng chứng hợp lệ, hành động đó phải bị giữ lại theo chính sách.

Các check thường có thể được đặt thành bắt buộc:

| Nhóm kiểm tra | Ví dụ | Lý do có thể bắt buộc |
|---|---|---|
| Build | Biên dịch và đóng gói thành công | Tránh nhập mã không thể tạo phiên bản chạy được |
| Test cốt lõi | Unit test và integration test trọng yếu | Phát hiện lỗi hành vi trên luồng chính |
| Kiểu và cấu trúc | Type check, schema validation, API contract | Giữ hợp đồng giữa các thành phần |
| Bảo mật nghiêm trọng | Secret scan, lỗ hổng vượt ngưỡng chính sách | Ngăn credential bị lộ hoặc rủi ro không được chấp nhận |
| Dependency và license | Dependency bị cấm hoặc license không được phép | Tuân thủ chính sách chuỗi cung ứng và pháp lý |
| Artifact | Digest, chữ ký hoặc provenance hợp lệ | Bảo đảm artifact có thể truy vết và được tin cậy |
| Phê duyệt | Review của chủ sở hữu hoặc approval cho production | Đảm bảo thay đổi có người chịu trách nhiệm |

Danh sách này không phải mặc định cho mọi dự án. Nhóm phải chọn check theo rủi ro, kiến trúc, yêu cầu pháp lý và khả năng kiểm soát. Một test chậm có thể được chuyển sang giai đoạn sau nếu nó không cần thiết để quyết định merge, nhưng không được bỏ qua nếu nó là biện pháp duy nhất bảo vệ một rủi ro quan trọng.

### Tiêu chí của một required check tốt

Một check bắt buộc nên:

- Có mục tiêu và phạm vi rõ ràng.
- Có kết quả xác định: đạt, không đạt hoặc chưa thể kết luận.
- Có log và bằng chứng để điều tra.
- Có chủ sở hữu xử lý khi thất bại.
- Có thời gian phản hồi phù hợp với điểm chặn.
- Có cách xử lý lỗi hạ tầng hoặc dịch vụ phụ thuộc.
- Chạy trên đúng commit, merge result hoặc artifact cần xác minh.

Nếu một check thường xuyên thất bại do flaky test, cấu hình thiếu ổn định hoặc dịch vụ ngoài không đáng tin cậy, nó có thể làm tắc toàn bộ luồng. Nhóm cần sửa nguyên nhân và đặt quy trình xử lý rõ ràng; không nên biến check thành advisory chỉ để làm cho pipeline xanh.

## 3. Kết quả tham khảo là gì?

Kết quả tham khảo giúp nhóm hiểu xu hướng, phát hiện rủi ro sớm hoặc cung cấp dữ liệu cho quyết định của con người. Kết quả đó không tự động chặn merge hay phát hành.

Ví dụ:

| Kết quả | Cách dùng tham khảo |
|---|---|
| Coverage tổng thể | Theo dõi xu hướng chất lượng test qua nhiều phiên bản |
| Maintainability hoặc code smell mức thấp | Tạo backlog cải thiện, đánh giá theo module |
| Lỗ hổng mức thấp có kế hoạch xử lý | Ghi nhận, phân công chủ sở hữu và hạn xử lý |
| Benchmark hiệu năng chưa có ngưỡng ổn định | Theo dõi xu hướng trước khi đặt ngưỡng chặn |
| Báo cáo kích thước artifact | Quan sát dung lượng và xu hướng tăng |
| Test thử nghiệm hoặc kiểm tra chưa ổn định | Thu thập dữ liệu để đánh giá độ tin cậy |
| Phân tích kiến trúc bổ sung | Hỗ trợ review, không thay thế check hợp đồng bắt buộc |

Advisory không có nghĩa là có thể bỏ qua mãi mãi. Mỗi kết quả tham khảo quan trọng nên có chủ sở hữu, mức độ ưu tiên và cách chuyển thành chính sách bắt buộc khi công cụ đủ tin cậy. Nếu cảnh báo không ai đọc, không ai xử lý và không được theo dõi, nó chỉ tạo thêm nhiễu cho pipeline.

### Cảnh báo và lỗi là hai loại thông tin khác nhau

Một công cụ có thể trả về trạng thái cảnh báo dù tiến trình thoát mã 0, hoặc trả lỗi vì không thể kết nối dịch vụ phân tích. Cần phân biệt:

- Phát hiện vi phạm chính sách.
- Phát hiện rủi ro cần xem xét.
- Công cụ không chạy được hoặc không tạo đủ bằng chứng.
- Check bị bỏ qua vì điều kiện không áp dụng.

Không nên gộp tất cả thành một màu xanh hoặc một dòng success mà không giữ chi tiết. Trạng thái tổng hợp phải đi kèm báo cáo đủ để người đọc biết điều gì thực sự đã được kiểm tra.

## 4. Ma trận bắt buộc và tham khảo

Trước khi cấu hình CI, lập ma trận cho từng giai đoạn:

| Check | Trước merge | Trước release | Sau deploy | Phân loại gợi ý |
|---|---|---|---|---|
| Compile/build | Bắt buộc | Bắt buộc nếu tạo lại artifact | Không áp dụng | Required |
| Unit test cốt lõi | Bắt buộc | Có thể chạy lại trên artifact hoặc build tương ứng | Không áp dụng | Required |
| Integration/contract test | Bắt buộc với hợp đồng bị ảnh hưởng | Bắt buộc nếu rủi ro yêu cầu | Có thể smoke test | Required theo phạm vi |
| Coverage report | Báo cáo; có thể áp ngưỡng cho mã mới | Theo dõi xu hướng | Không áp dụng | Advisory hoặc required theo ngưỡng |
| Secret scan | Bắt buộc | Bắt buộc với artifact/nguồn phát hành | Không áp dụng | Required |
| Vulnerability scan | Chặn theo ngưỡng chính sách | Bắt buộc theo chính sách phát hành | Theo dõi khi cần | Kết hợp required/advisory |
| License report | Chặn license bị cấm | Bắt buộc trước phân phối | Không áp dụng | Required theo chính sách |
| Artifact signature/provenance | Có thể chưa cần | Bắt buộc | Xác minh artifact được triển khai | Required |
| Benchmark | Báo cáo xu hướng | Bắt buộc nếu có SLO hiệu năng cụ thể | Theo dõi telemetry | Thường advisory, có ngưỡng thì required |
| Smoke test/health | Không áp dụng | Có thể chạy trên staging | Bắt buộc trước khi kết thúc rollout | Required |

Ma trận cần chỉ rõ điều kiện áp dụng. Ví dụ, kiểm tra schema API chỉ cần chạy khi thay đổi ảnh hưởng đến schema; kiểm tra license cần áp dụng cho dependency mới hoặc thay đổi dependency graph; benchmark có thể chỉ chạy trên nhánh chính hoặc trước release.

Một chính sách tốt nói rõ cả điều kiện chạy và điều kiện bỏ qua. Nếu check không áp dụng, hệ thống phải ghi nhận trạng thái skipped hoặc not applicable cùng lý do. Không nên diễn giải việc không chạy là đã đạt.

## 5. Hiểu đúng trạng thái của một check

Các nền tảng CI có tên trạng thái khác nhau, nhưng có thể quy về những nhóm ý nghĩa sau:

| Trạng thái | Ý nghĩa | Xử lý với check bắt buộc |
|---|---|---|
| Success / Passed | Đã chạy và đạt tiêu chí | Có thể cho qua gate |
| Failure / Failed | Đã chạy và vi phạm tiêu chí | Chặn bước tiếp theo |
| Pending / In progress | Chưa có kết luận cuối | Chờ kết quả; không xem là đạt |
| Error / Infrastructure failure | Công cụ hoặc hạ tầng không thể xác minh | Giữ gate cho đến khi retry hoặc có quyết định theo chính sách |
| Skipped / Not applicable | Không chạy vì điều kiện không áp dụng | Chỉ chấp nhận nếu quy tắc gate cho phép và có lý do hợp lệ |
| Cancelled | Bị hủy trước khi có kết quả cuối | Không xem là pass; cần chạy lại hoặc xử lý theo chính sách |
| Neutral / Informational | Kết quả không đưa ra kết luận đạt/không đạt theo cách thông thường | Phải xác định rõ check đó có thể thỏa required condition hay không |

**Không đồng nhất skipped với passed.** Một check có thể được bỏ qua vì path filter, điều kiện job hoặc cấu hình sai. Nếu đó là check bắt buộc, cần bảo đảm việc bỏ qua là một trường hợp được chính sách cho phép, ví dụ thay đổi không liên quan đến thành phần đó và một check tổng hợp vẫn báo kết quả đúng.

Tương tự, lỗi hạ tầng không có nghĩa mã nguồn chắc chắn sai, nhưng cũng không phải bằng chứng mã nguồn an toàn. Với check bắt buộc, trạng thái không xác định thường phải giữ gate cho đến khi có lần chạy hợp lệ hoặc ngoại lệ được phê duyệt.

### Không để required check bị treo

Một số nền tảng giữ trạng thái check bắt buộc ở pending nếu workflow bị bỏ qua hoàn toàn bởi branch hoặc path filter. Điều này có thể chặn merge dù không có job nào thực sự thất bại. Khi cấu hình filter, hãy kiểm tra cách nền tảng tạo check và trạng thái cuối.

Một mẫu thường dùng là tạo check tổng hợp luôn chạy, nhận kết quả từ các job con và kết luận rõ:

- Đạt nếu tất cả check bắt buộc áp dụng đều đạt.
- Đạt theo chính sách nếu check được xác định không áp dụng.
- Thất bại nếu có check bắt buộc thất bại.
- Chưa kết luận nếu check bắt buộc chưa chạy hoặc không có bằng chứng hợp lệ.

Check tổng hợp phải xác minh rằng kết quả thuộc đúng commit hoặc merge group. Không nên chấp nhận một trạng thái cũ từ commit trước.

## 6. Cấu hình required checks trong GitHub Actions

Workflow định nghĩa job và check được tạo ra; chính sách branch protection hoặc repository ruleset quyết định check nào là bắt buộc trước merge. Chỉ đặt tên job trong YAML không tự biến nó thành required check.

Ví dụ workflow có một job kiểm tra bắt buộc và một job báo cáo tham khảo:

~~~yaml
name: Pull request quality

on:
  pull_request:
    branches:
      - main

jobs:
  required-validation:
    name: required-validation
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build and test
        run: ./gradlew clean check

  advisory-report:
    name: advisory-report
    runs-on: ubuntu-latest
    continue-on-error: true
    steps:
      - uses: actions/checkout@v4
      - name: Generate advisory report
        run: ./gradlew qualityReport
~~~

Trong repository, cấu hình branch protection hoặc ruleset để yêu cầu check required-validation. Check advisory-report cung cấp thông tin nhưng không nằm trong danh sách required. continue-on-error là ví dụ cách cho phép job không làm thất bại workflow; nó không thay thế việc phân loại check trong chính sách repository.

Tên check được yêu cầu cần ổn định. Khi đổi tên workflow hoặc job, phải cập nhật chính sách branch protection tương ứng và xác minh trạng thái mới. Nếu có nhiều workflow tạo check cùng tên, kết quả có thể trở nên khó phân biệt; nên đặt tên rõ theo mục đích và nguồn tạo.

### Lưu ý với required checks và path filters

Nếu workflow bị bỏ qua ở cấp workflow do branch/path filter, nền tảng có thể không tạo kết quả check cuối cùng và required check vẫn pending. Với check bắt buộc, cân nhắc:

- Luôn tạo workflow và dùng điều kiện ở cấp job.
- Có check tổng hợp luôn chạy để kết luận khi một nhóm kiểm tra không áp dụng.
- Đảm bảo mọi nhánh điều kiện đều tạo ra kết quả check có tên ổn định.
- Kiểm thử trên pull request chỉ thay đổi tài liệu, mã nguồn hoặc cấu hình build.

Không dùng path filter để vô tình bỏ qua check bảo mật hoặc dependency có phạm vi rộng hơn thư mục mã nguồn.

## 7. Cấu hình allow_failure trong GitLab CI

GitLab CI cho phép phân biệt job chặn pipeline và job có thể thất bại mà pipeline vẫn tiếp tục thông qua allow_failure.

~~~yaml
stages:
  - validate
  - report

required-tests:
  stage: validate
  script:
    - ./gradlew clean check
  allow_failure: false

advisory-quality-report:
  stage: report
  script:
    - ./gradlew qualityReport
  allow_failure: true
~~~

Trong ví dụ, required-tests chặn pipeline khi thất bại. advisory-quality-report có thể thất bại mà pipeline vẫn được xem là thành công, nhưng kết quả job vẫn cần được hiển thị và theo dõi. Cần kiểm tra thêm cấu hình merge request approval, protected branch và các chính sách khác để bảo đảm việc cho phép merge đúng với yêu cầu của dự án.

allow_failure không nên được dùng để làm mềm mọi job khó ổn định. Nếu một kiểm tra quan trọng thường xuyên thất bại, hãy xử lý độ tin cậy hoặc xây dựng cơ chế retry/ngoại lệ có kiểm soát.

## 8. Đặt ngưỡng cho quality gate

Một số công cụ trả về điểm số hoặc số lượng phát hiện. Để biến chúng thành gate, cần định nghĩa ngưỡng rõ:

- Coverage không thấp hơn mức tối thiểu cho phần mã mới.
- Không có lỗ hổng critical hoặc high thuộc phạm vi chính sách.
- Không có secret bị phát hiện.
- Không có dependency sử dụng license bị cấm.
- Không có lỗi contract hoặc schema compatibility.
- Artifact phải có chữ ký và provenance hợp lệ trước phát hành.

Không nên chọn ngưỡng chỉ vì công cụ hỗ trợ. Ngưỡng cần phản ánh rủi ro và có khả năng đo lường đáng tin cậy.

### Coverage

Coverage tổng thể có thể bị chi phối bởi mã cũ và không phản ánh chất lượng của thay đổi hiện tại. Một cách tiếp cận là theo dõi coverage của mã mới hoặc phần mã bị thay đổi, đồng thời theo dõi xu hướng tổng thể. Nếu đặt required threshold, cần xác định:

- Công cụ và cách tính coverage.
- Phạm vi mã được tính và loại trừ.
- Ngưỡng tối thiểu.
- Cách xử lý generated code, test fixture và mã không thể kiểm thử hợp lý.
- Quy tắc khi báo cáo coverage không được tạo ra.

Không xem việc thiếu báo cáo như coverage 100% hoặc tự động cho qua gate.

### Security findings

Ngưỡng bảo mật nên xem xét mức độ nghiêm trọng, khả năng khai thác, mức độ phơi nhiễm, khả năng truy cập từ ứng dụng và chính sách tổ chức. Không phải mọi lỗ hổng ở một dependency đều có cùng mức rủi ro thực tế; nhưng việc đánh giá phải dựa trên bằng chứng và được lưu lại.

Một chính sách có thể chặn secret leak và lỗ hổng vượt ngưỡng, trong khi các phát hiện thấp hơn được ghi thành advisory có chủ sở hữu và hạn xử lý. Không nên dùng một con số CVSS đơn lẻ làm đại diện cho toàn bộ quyết định nếu tổ chức có thêm dữ liệu về exploitability hoặc reachability.

### Hiệu năng và kích thước artifact

Benchmark thường có nhiễu do runner, tải hệ thống và dữ liệu đầu vào. Trước khi đặt gate, cần có baseline ổn định, số lần lặp đủ và ngưỡng có ý nghĩa. Một cảnh báo tăng 1% ở benchmark chưa ổn định có thể chỉ là nhiễu; một vi phạm SLO đã được đo tin cậy có thể cần chặn phát hành.

Với kích thước artifact, xác định loại file, cách đo và ngưỡng. Cảnh báo khi JAR tăng dung lượng có thể là advisory; giới hạn image vượt quota triển khai hoặc chính sách phân phối có thể là required.

## 9. Ngoại lệ đối với kiểm tra bắt buộc

Trong thực tế, đôi khi cần merge hoặc phát hành dù một check chưa đạt, ví dụ:

- Sự cố production cần hotfix khẩn cấp.
- Dịch vụ scan bên ngoài bị gián đoạn.
- Một phát hiện false positive đã có bằng chứng.
- Test không ổn định đang được điều tra và thay đổi không ảnh hưởng phạm vi đó.
- Có yêu cầu kinh doanh đặc biệt với thời hạn rõ ràng.

Ngoại lệ không nên là cách đổi check bắt buộc thành advisory lâu dài. Một quy trình ngoại lệ nên có:

1. **Lý do cụ thể:** check nào chưa đạt và vì sao vẫn cần tiếp tục.
2. **Phạm vi:** repository, commit, artifact, môi trường và hành động được phép.
3. **Người phê duyệt:** chủ sở hữu rủi ro hoặc vai trò được ủy quyền.
4. **Thời hạn:** thời điểm hết hiệu lực hoặc điều kiện phải xem xét lại.
5. **Biện pháp giảm thiểu:** giới hạn rollout, feature flag, giám sát bổ sung hoặc kế hoạch quay lui.
6. **Dấu vết:** người yêu cầu, người duyệt, thời điểm, bằng chứng và kết quả.
7. **Theo dõi sau ngoại lệ:** xác minh rủi ro đã được xử lý và đóng ngoại lệ.

Không nên cho phép người tạo thay đổi tự phê duyệt ngoại lệ của chính mình nếu chính sách yêu cầu phân tách trách nhiệm. Với lỗ hổng hoặc secret nghiêm trọng, ngoại lệ có thể bị cấm hoàn toàn theo chính sách tổ chức.

### Tách lỗi công cụ khỏi lỗi chất lượng

Nếu scanner không khởi chạy vì dịch vụ ngoài mất kết nối, đó là lỗi khả năng xác minh chứ không phải kết quả scan sạch. Nếu công cụ chạy xong và phát hiện vi phạm, đó là lỗi chính sách. Hai trường hợp cần cách xử lý khác nhau:

- Lỗi công cụ: retry có giới hạn, chuyển sang nguồn dự phòng hoặc yêu cầu phê duyệt ngoại lệ theo chính sách.
- Lỗi chất lượng: sửa nguyên nhân, cập nhật dependency hoặc cung cấp bằng chứng false positive để review.

Không được đổi trạng thái công cụ thất bại thành passed chỉ để giải phóng pipeline.

## 10. Bảo đảm gate kiểm tra đúng đối tượng

Một kết quả chỉ có giá trị khi nó gắn với đúng đầu vào cần kiểm tra. Trước merge, đối tượng có thể là head commit hoặc merge result; trước release, đối tượng cần được kiểm tra có thể là artifact digest; trước deploy, đối tượng là phiên bản và môi trường cụ thể.

Một gate cần lưu:

- Repository và branch/ref.
- Commit SHA hoặc merge group ID.
- Workflow, job và check name.
- Phiên bản công cụ và cấu hình chính sách.
- Artifact digest nếu kiểm tra artifact.
- Môi trường đích nếu kiểm tra triển khai.
- Thời điểm chạy và kết quả cuối.
- Báo cáo hoặc liên kết bằng chứng.

Không nên dùng check xanh từ commit cũ để cho phép merge commit mới. Không dùng báo cáo scan của một artifact để chứng minh artifact khác an toàn. Nếu artifact được tạo một lần rồi chuyển qua staging và production, hãy xác minh digest để bảo đảm cùng một artifact được triển khai.

### Kiểm soát thứ tự và tính mới của kết quả

Khi pull request nhận commit mới, check của commit cũ có thể không còn phù hợp. Merge queue cũng có thể tạo merge result mới sau khi nhánh đích thay đổi. Hệ thống cần bảo đảm required check áp dụng cho đúng trạng thái sẽ được merge.

Nếu check bị hủy hoặc đang chạy, không được coi kết quả trước đó là kết quả của commit mới. Khi dùng concurrency để hủy phiên cũ, check tổng hợp phải chờ phiên mới hoàn tất hoặc báo trạng thái chưa kết luận.

## 11. Thiết kế báo cáo để người đọc hiểu mức độ quan trọng

Một giao diện kết quả tốt nên phân biệt rõ:

- **Blocking:** check bắt buộc thất bại; hành động tiếp theo bị chặn.
- **Passed:** check bắt buộc đã đạt.
- **Pending:** chưa có kết luận, cần chờ.
- **Advisory:** có cảnh báo hoặc dữ liệu cần xem xét, nhưng không chặn.
- **Not applicable:** check không áp dụng theo quy tắc đã định nghĩa.
- **Infrastructure error:** không thể hoàn tất kiểm tra do công cụ hoặc môi trường.

Đừng chỉ hiển thị tổng số lỗi. Người xem cần biết check nào là blocker, check nào chỉ cảnh báo, ai phụ trách và cần làm gì tiếp theo. Link đến log và báo cáo phải trỏ đến đúng run và commit.

Ví dụ báo cáo tổng hợp:

~~~text
Pull request: #248
Commit: 9f3a2c1

Required
  Build                 PASSED
  Unit tests            PASSED
  API contract          PASSED
  Secret scan           PASSED
  Dependency policy     FAILED

Advisory
  Coverage trend        78.4% (informational)
  Maintainability       3 low-priority findings
  Benchmark             +1.2% (below alert threshold)

Decision: BLOCKED
Reason: Dependency policy has an unresolved required finding.
Owner: Platform security
~~~

Ví dụ minh họa cách trình bày. Giá trị thực tế phải lấy từ run tương ứng; không dùng số liệu giả định để ra quyết định merge.

## 12. Quản trị chính sách quality gate

Quality gate thay đổi theo kiến trúc, mức rủi ro và công cụ. Cần quản lý chính sách như một phần của hệ thống phát hành:

### Có chủ sở hữu

Mỗi check bắt buộc cần một nhóm hoặc vai trò chịu trách nhiệm về:

- Tiêu chí đạt và ngưỡng.
- Cấu hình công cụ.
- Thời gian phản hồi và hỗ trợ khi lỗi.
- Xử lý false positive.
- Nâng cấp công cụ và duy trì tương thích.
- Quy trình ngoại lệ.

Không nên để một check bắt buộc không có người chịu trách nhiệm. Khi nó hỏng, toàn bộ nhóm sẽ không biết ai có quyền xử lý.

### Review thay đổi chính sách

Thay đổi từ required sang advisory làm giảm mức bảo vệ của luồng. Thay đổi ngược lại có thể làm tăng thời gian merge và ảnh hưởng năng suất. Vì vậy, thay đổi chính sách nên có:

- Lý do và rủi ro được giải quyết.
- Phạm vi repository và nhánh áp dụng.
- Tác động đến check hiện có.
- Cách thử nghiệm trước khi áp dụng rộng.
- Người review và phê duyệt.
- Kế hoạch truyền thông và theo dõi sau thay đổi.

### Theo dõi chất lượng của chính gate

Gate cũng cần được đo lường:

| Chỉ số | Câu hỏi |
|---|---|
| Required check failure rate | Check bắt buộc thường thất bại vì lỗi thực hay lỗi công cụ? |
| Time to green | Thay đổi mất bao lâu để đạt đủ các check bắt buộc? |
| Flaky rate | Check có cho kết quả khác nhau trên cùng đầu vào không? |
| Advisory finding age | Cảnh báo tham khảo tồn tại bao lâu chưa xử lý? |
| Exception frequency | Có thường xuyên phải bỏ qua gate không? |
| False positive rate | Công cụ có tạo quá nhiều phát hiện sai không? |
| Gate bypass count | Có bao nhiêu lần chính sách được vượt qua và vì sao? |
| Missing/pending checks | Có check bắt buộc nào không tạo được kết quả? |

Nếu tỷ lệ ngoại lệ tăng liên tục, có thể ngưỡng quá chặt, công cụ không ổn định hoặc quy trình chưa phù hợp. Không nên chỉ hạ tiêu chuẩn để làm số liệu đẹp; hãy tìm nguyên nhân và điều chỉnh có bằng chứng.

## 13. Các sai lầm thường gặp

### Đặt mọi check thành bắt buộc

Pipeline sẽ chậm và dễ bị chặn bởi báo cáo ít quan trọng. Chọn check theo rủi ro và điểm quyết định; các chỉ số theo dõi xu hướng có thể ở dạng advisory.

### Để mọi check ở dạng tham khảo

Các lỗi build, test cốt lõi, secret leak hoặc vi phạm chính sách nghiêm trọng có thể đi qua merge và phát hành. Xác định những điều kiện tối thiểu phải đạt trước khi chuyển bước.

### Coi check không chạy là check thành công

Một job bị bỏ qua vì path filter hoặc điều kiện sai không chứng minh chất lượng đã được xác minh. Ghi rõ not applicable và có check tổng hợp xử lý trạng thái đó.

### Chỉ dựa vào màu xanh tổng hợp

Một pipeline xanh có thể chứa nhiều job advisory thất bại hoặc job bắt buộc chưa thực sự kiểm tra đúng commit. Hiển thị trạng thái và bằng chứng của từng check.

### Dùng ngoại lệ không thời hạn

Một cảnh báo được miễn trừ vĩnh viễn sẽ biến thành lỗ hổng chính sách. Ngoại lệ cần phạm vi, người duyệt, thời hạn và biện pháp giảm thiểu.

### Dùng kết quả cũ cho commit hoặc artifact mới

Check phải gắn với đúng SHA, merge group hoặc artifact digest. Kết quả cũ không được tự động áp dụng cho đầu vào đã thay đổi.

### Hạ mức kiểm soát khi công cụ không ổn định

Nếu scanner hoặc test flaky, việc đổi thành advisory có thể làm mất bảo vệ mà không giải quyết nguyên nhân. Cần tách lỗi hạ tầng khỏi lỗi chất lượng và cải thiện độ tin cậy.

## 14. Checklist thiết kế cổng chất lượng

- [ ] Mỗi check có mục đích và giai đoạn áp dụng rõ ràng.
- [ ] Required và advisory được phân loại công khai.
- [ ] Required check có tiêu chí đạt, chủ sở hữu và bằng chứng.
- [ ] Check được gắn với đúng commit, merge result hoặc artifact digest.
- [ ] Pending, failed, skipped, cancelled và infrastructure error được xử lý riêng.
- [ ] Check không áp dụng có lý do và không bị hiểu nhầm là đã chạy thành công.
- [ ] Path filter và điều kiện job không làm mất required check.
- [ ] Advisory result vẫn có người theo dõi và thời hạn xử lý khi cần.
- [ ] Ngoại lệ có người phê duyệt, phạm vi, thời hạn và dấu vết.
- [ ] Chính sách được review khi thay đổi và được theo dõi bằng metrics.
- [ ] Pipeline xanh không che giấu check bắt buộc bị bỏ qua hoặc chạy trên đầu vào cũ.

Phân biệt kiểm tra bắt buộc với kết quả tham khảo giúp CI/CD cân bằng giữa tốc độ và mức bảo đảm. Required check bảo vệ những điều kiện không được phép bỏ qua trước khi chuyển bước; advisory result cung cấp tín hiệu để nhóm cải thiện mà không làm tắc luồng vì mọi cảnh báo nhỏ. Khi chính sách rõ ràng, gắn với đúng đầu vào và có quy trình ngoại lệ minh bạch, nhóm có thể đưa ra quyết định merge và phát hành nhất quán, có truy vết.
