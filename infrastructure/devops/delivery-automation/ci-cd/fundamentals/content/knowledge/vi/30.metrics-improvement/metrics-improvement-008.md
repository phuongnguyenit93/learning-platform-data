# Chọn một cải tiến nhỏ và kiểm tra ảnh hưởng sau khi áp dụng

Cải tiến CI/CD không nhất thiết phải bắt đầu bằng một dự án tái cấu trúc pipeline lớn. Nhiều kết quả có giá trị đến từ một thay đổi nhỏ, có phạm vi rõ và có thể đo được: giảm thời gian chờ của một job, loại bỏ một bước cài dependency lặp lại, làm rõ thông báo lỗi, giảm test flaky hoặc rút ngắn thời gian từ lúc push tới khi developer nhận được phản hồi.

Điều quan trọng là phải kiểm tra xem thay đổi có tạo ra kết quả mong muốn hay không. Một pipeline chạy nhanh hơn nhưng bỏ qua test, tăng tỷ lệ lỗi hoặc tạo thêm công việc điều tra không phải là cải tiến tốt. Nhóm cần bắt đầu từ dữ liệu hiện có, chọn đúng vấn đề, nêu giả thuyết có thể kiểm chứng, thay đổi một yếu tố trong phạm vi nhỏ và đo cả kết quả mong muốn lẫn tác dụng phụ.

Bài này trình bày một vòng lặp cải tiến thực tế cho CI/CD: đo hiện trạng, chọn cơ hội nhỏ, thử nghiệm có kiểm soát, so sánh trước/sau, quyết định giữ hoặc hoàn tác và ghi lại bài học để lần cải tiến tiếp theo có cơ sở.

## 1. Cải tiến là một giả thuyết cần được kiểm chứng

Một ý tưởng nghe hợp lý chưa chắc tạo ra hiệu quả trong hệ thống thật.

Ví dụ:

- "Bật cache sẽ làm pipeline nhanh hơn."
- "Chạy nhiều job song song sẽ rút ngắn thời gian phản hồi."
- "Thêm retry sẽ giảm số lần pipeline đỏ."
- "Chuyển test chậm sang nightly sẽ giúp PR nhanh hơn."
- "Tăng runner size sẽ giảm thời gian build."

Mỗi câu trên mới là giả thuyết. Cache có thể tăng tốc nhưng cũng có thể gây stale output; tăng parallelism có thể làm queue hoặc contention nặng hơn; retry có thể che giấu flaky test; chuyển test sang nightly có thể làm lỗi quan trọng được phát hiện muộn.

Một giả thuyết tốt mô tả:

1. Vấn đề quan sát được.
2. Nguyên nhân có khả năng gây ra vấn đề.
3. Thay đổi cụ thể sẽ thử.
4. Kết quả mong đợi và cách đo.
5. Điều kiện bảo vệ chất lượng.
6. Khoảng thời gian hoặc số lần chạy cần quan sát.
7. Điều kiện dừng hoặc hoàn tác.

Ví dụ: "Các job kiểm thử Gradle tải lại dependency ở nhiều lần chạy. Nếu bật cache dependency cho job Linux trên pull request, median execution time của job sẽ giảm ít nhất 15% sau giai đoạn warm-up, trong khi tỷ lệ test failure, cache restore error và kết quả test không thay đổi đáng kể."

Giả thuyết này có thể bị bác bỏ bằng dữ liệu. Đó là đặc điểm cần có của một thử nghiệm cải tiến tốt.

## 2. Bắt đầu bằng câu hỏi vận hành, không bắt đầu bằng công cụ

Trước khi thay workflow, cần xác định điều gì đang gây khó khăn cho nhóm.

Một số câu hỏi hữu ích:

- Developer phải chờ bao lâu để biết một pull request có lỗi?
- Phần thời gian nào nằm ở queue, phần nào là setup, build, test hoặc deploy?
- Job nào thường xuyên thất bại hoặc phải chạy lại?
- Lỗi được phát hiện ở bước nào và mất bao lâu để tìm nguyên nhân?
- Pipeline có làm lại công việc không cần thiết không?
- Một thay đổi nhỏ có kích hoạt quá nhiều project hoặc test không?
- Có bước thủ công nào thường gây chậm hoặc sai?
- Nhóm đang phải duy trì những workaround nào?

Dữ liệu có thể đến từ CI provider, build scan, test report, deployment history, issue tracker hoặc quan sát của developer. Ý kiến của nhóm giúp tìm nơi cần xem xét; dữ liệu giúp xác định mức độ và kiểm tra kết quả.

Không nên chọn một công cụ mới chỉ vì nó phổ biến. Nếu bottleneck nằm ở thời gian queue do thiếu runner, đổi build tool có thể không giải quyết vấn đề. Nếu thời gian test chiếm phần lớn, tối ưu checkout có thể chỉ tạo khác biệt rất nhỏ.

## 3. Xác định đúng metric và cách tính

Một metric cần có định nghĩa đủ rõ để hai người đo cùng một sự kiện sẽ thu được kết quả tương đương.

Với CI/CD, có thể xem xét các nhóm metric sau:

| Nhóm | Metric | Câu hỏi |
|---|---|---|
| Feedback time | Thời gian từ push tới kết quả đầu tiên | Developer nhận tín hiệu sớm đến đâu? |
| Queue | Thời gian chờ runner | Hệ thống có đủ năng lực thực thi không? |
| Execution | Thời gian build/test/deploy | Bước nào thực sự tốn thời gian? |
| Reliability | Tỷ lệ job thất bại do sản phẩm hoặc hạ tầng | Pipeline có ổn định không? |
| Flakiness | Tỷ lệ test cho kết quả không nhất quán | Kết quả đỏ có đáng tin không? |
| Rework | Số lần rerun hoặc thời gian điều tra | Nhóm mất bao nhiêu công sức xử lý phản hồi? |
| Delivery | Thời gian từ thay đổi được chấp nhận tới production | Thay đổi đi qua hệ thống nhanh đến đâu? |
| Recovery | Thời gian khôi phục sau deploy lỗi | Nhóm phục hồi hiệu quả thế nào? |

Cần phân biệt thời gian queue và execution time. Nếu job bắt đầu sau 12 phút chờ runner nhưng chỉ chạy 4 phút, tối ưu script có thể không thay đổi trải nghiệm chờ tổng thể. Tương tự, thời gian từ push tới kết quả đầu tiên khác với thời gian hoàn tất toàn bộ workflow.

Định nghĩa metric nên nêu rõ điểm bắt đầu, điểm kết thúc, đơn vị, phạm vi job và cách xử lý lần chạy bị hủy hoặc retry.

## 4. Chọn một chỉ số chính và các guardrail

Một thử nghiệm nên có một metric chính để đánh giá giả thuyết. Ngoài ra cần có guardrail metrics để phát hiện tác dụng phụ.

Ví dụ khi tối ưu thời gian CI:

- **Metric chính:** median execution time của job mục tiêu.
- **Guardrail 1:** tỷ lệ test failure không tăng vượt mức cho phép.
- **Guardrail 2:** không bỏ qua hoặc giảm phạm vi test bắt buộc.
- **Guardrail 3:** cache restore/save error không làm job mất ổn định.
- **Guardrail 4:** chi phí runner và storage không tăng ngoài dự kiến.
- **Guardrail 5:** artifact và kết quả test vẫn có thể truy vết.

Nếu chỉ nhìn vào thời gian trung bình, một vài lần chạy cực nhanh có thể che giấu phần lớn job không thay đổi. Median thường bền vững hơn với outlier; percentile cao như p90 giúp nhìn thấy trải nghiệm của những lần chạy chậm.

Không chọn quá nhiều metric chính. Nếu mọi metric đều là mục tiêu, nhóm khó xác định thử nghiệm thành công theo tiêu chí nào. Hãy giữ một mục tiêu chính và một tập guardrail vừa đủ để bảo vệ chất lượng.

## 5. Ghi baseline trước khi thay đổi

Baseline là dữ liệu hiện trạng dùng làm mốc so sánh. Nếu không có baseline, nhóm dễ nhầm một thay đổi khác trong hệ thống với kết quả của cải tiến.

Trước khi sửa pipeline:

1. Chọn workflow/job cần cải tiến.
2. Xác định các loại run được đưa vào so sánh.
3. Thu thập dữ liệu trong một khoảng thời gian đủ đại diện.
4. Ghi median, p90, số lần chạy và tỷ lệ lỗi.
5. Ghi lại runner, OS, branch, matrix và loại trigger.
6. Ghi các thay đổi khác đang diễn ra có thể ảnh hưởng kết quả.

Ví dụ baseline có thể lấy trong 10 ngày làm việc hoặc tối thiểu một số lượng run đủ để nhìn thấy biến động. Con số cần thiết phụ thuộc tần suất chạy và độ ổn định của hệ thống; dự án ít PR có thể cần thời gian dài hơn.

Không chỉ lấy một lần chạy trước khi thay đổi. Build có thể nhanh bất thường vì cache đã nóng, hoặc chậm vì runner dùng chung đang quá tải.

## 6. So sánh những điều kiện tương đương

So sánh trước/sau chỉ có ý nghĩa nếu hai nhóm dữ liệu tương đối tương đồng.

Cần xem xét:

- Cùng workflow và job scope.
- Cùng OS/runner class và architecture.
- Cùng test suite và matrix.
- Cùng loại trigger, ví dụ PR với PR.
- Cùng chính sách concurrency.
- Cùng cách tính thời gian.
- Cùng cách xử lý retry và cancelled run.
- Khối lượng thay đổi hoặc kích thước test tương đối tương đương.

Nếu trước thay đổi có 20 job test và sau thay đổi chỉ còn 12 job, thời gian giảm có thể do giảm phạm vi kiểm tra. Đây không phải bằng chứng rằng pipeline hiệu quả hơn nếu chất lượng coverage đã giảm.

Nếu runner image hoặc dependency thay đổi đồng thời, phải ghi lại vì đó là yếu tố gây nhiễu. Khi có thể, chỉ thay một yếu tố trong mỗi thử nghiệm để dễ diễn giải.

## 7. Chọn cải tiến nhỏ có phạm vi kiểm soát

Một cải tiến nhỏ thường có các đặc điểm:

- Chỉ ảnh hưởng một workflow, job hoặc service.
- Có thể bật/tắt bằng cấu hình hoặc thay đổi nhỏ.
- Có thể triển khai cho một nhóm run trước.
- Có metric để đo.
- Có thể hoàn tác nhanh.
- Không làm giảm gate chất lượng hoặc bảo mật.

Ví dụ phù hợp:

- Bật dependency cache cho một job.
- Loại bỏ một bước cài tool đã có trong runner image.
- Chia test report để xác định suite chậm.
- Chạy lint trước integration test để phản hồi lỗi đơn giản sớm hơn.
- Giảm một lần checkout hoặc artifact download dư thừa.
- Sửa một test flaky đã xác định nguyên nhân.
- Tạo thông báo lỗi rõ hơn khi secret reference thiếu.

Ví dụ có phạm vi quá lớn cho một thử nghiệm đầu tiên:

- Thay toàn bộ CI provider.
- Chuyển toàn bộ build sang hệ thống mới.
- Viết lại tất cả pipeline cùng lúc.
- Bỏ nhiều test để giảm thời gian.
- Thay runner, build tool, dependency và test strategy trong một lần.

Phạm vi nhỏ giúp xác định nguyên nhân kết quả và giới hạn ảnh hưởng nếu thay đổi không như kỳ vọng.

## 8. Viết kế hoạch thử nghiệm trước khi triển khai

Một kế hoạch ngắn giúp nhóm thống nhất mục tiêu trước khi nhìn thấy kết quả.

| Thành phần | Ví dụ |
|---|---|
| Vấn đề | Job integration thường tải dependency nhiều lần |
| Baseline | Median 12 phút, p90 17 phút trong 2 tuần |
| Giả thuyết | Dependency cache giảm thời gian thực thi |
| Thay đổi | Bật dependency cache và build cache cho job Linux PR |
| Metric chính | Median execution time |
| Guardrails | Test failure, cache error, storage và coverage |
| Phạm vi | Một workflow, một nhóm runner |
| Cửa sổ đo | 2 tuần sau warm-up |
| Điều kiện giữ | Median giảm ít nhất 15%, guardrails đạt |
| Điều kiện dừng | Test sai lệch, cache lỗi hoặc chi phí vượt ngưỡng |
| Owner | Người phụ trách workflow |
| Hoàn tác | Tắt cache configuration và chạy lại kiểm tra |

Ngưỡng trong bảng là ví dụ minh họa. Nhóm cần chọn ngưỡng theo chi phí thay đổi, mức biến động baseline và giá trị kinh doanh. Không đặt mục tiêu quá thấp đến mức mọi thay đổi đều được gọi là thành công, hoặc quá cao khiến thử nghiệm không có khả năng đạt.

## 9. Thực hiện thay đổi theo từng bước

Khi thử nghiệm bắt đầu, giữ phạm vi đúng như kế hoạch:

1. Tạo thay đổi nhỏ và review.
2. Xác nhận test và security gate vẫn được giữ.
3. Triển khai vào nhánh hoặc workflow mục tiêu.
4. Ghi thời điểm bắt đầu áp dụng.
5. Theo dõi run đầu tiên và các lỗi mới.
6. Chờ giai đoạn warm-up nếu có cache hoặc cơ chế cần dữ liệu ban đầu.
7. Thu thập đủ số lần chạy theo kế hoạch.
8. Không thay đổi thêm yếu tố khác nếu chưa ghi nhận và đánh giá ảnh hưởng.

Không sửa ngưỡng thành công sau khi thấy kết quả không đạt. Nếu phát hiện một điều kiện ban đầu không hợp lý, hãy ghi rõ và thiết kế thử nghiệm tiếp theo.

## 10. Ví dụ thực tế: bật Gradle build cache cho một job CI

Giả sử job integration test của một dự án Java chạy Gradle thường xuyên tải dependency và thực hiện lại một số task có output có thể tái sử dụng.

Nhóm quan sát thấy job mất nhiều thời gian ở dependency resolution và một số task build lặp lại. Ý tưởng là bật Gradle build cache hoặc dependency cache theo đúng phạm vi, sau đó đo tác động.

Cần phân biệt hai loại cache:

- **Dependency cache:** lưu các artifact dependency đã tải để lần chạy sau không cần tải lại nếu dependency không đổi.
- **Build cache:** lưu output của task có thể tái sử dụng khi input tương ứng không thay đổi.

Build cache chỉ an toàn khi task được khai báo input/output đúng và có thể tái lập. Một task tùy biến khai báo thiếu input có thể trả về output cũ không còn hợp lệ. Vì vậy, không bật remote cache rộng cho mọi task mà chưa kiểm tra cache correctness.

### 10.1. Baseline giả định

Dữ liệu minh họa trong hai tuần:

| Metric | Trước thay đổi |
|---|---:|
| Số lần chạy | 80 |
| Median execution time | 12 phút 20 giây |
| p90 execution time | 17 phút |
| Median queue time | 2 phút |
| Test failure rate | 5,0% |
| Cache hit rate | Không đo hoặc chưa bật |

Đây là ví dụ để minh họa phương pháp. Trong dự án thật, cần lấy dữ liệu từ CI provider/build scan và ghi lại cách lọc run.

### 10.2. Giả thuyết và phạm vi

Giả thuyết: bật dependency cache và build cache cho job integration trên Linux sẽ giảm median execution time ít nhất 15% sau warm-up, không làm thay đổi test result và không tăng cache-related failure.

Phạm vi thử nghiệm:

- Chỉ áp dụng cho một job integration.
- Chỉ dùng runner Linux cùng loại với baseline.
- Giữ nguyên test suite và matrix.
- Không thay đổi đồng thời runner size hoặc Gradle version.
- Chỉ cache nội dung có thể tái tạo và có key phù hợp.

### 10.3. Ví dụ cấu hình

Có thể bật build cache trong Gradle command:

```bash
./gradlew --build-cache integrationTest
```

Nếu dùng GitHub Actions, có thể cấu hình Gradle dependency cache qua action setup phù hợp hoặc dùng cơ chế cache được tổ chức phê duyệt. Ví dụ workflow khái niệm:

```yaml
steps:
  - uses: actions/checkout@v4

  - uses: actions/setup-java@v4
    with:
      distribution: temurin
      java-version: '21'
      cache: gradle

  - name: Run integration tests with build cache
    run: ./gradlew --build-cache integrationTest
```

Đây là ví dụ minh họa. Cần kiểm tra phiên bản action và chính sách pin action của repository. Dependency cache và Gradle build cache là hai cơ chế khác nhau; bật cache dependency không tự động bật build cache.

Nếu dùng remote build cache, cần xác định quyền ghi/đọc, trust boundary giữa branch đáng tin cậy và pull request từ fork, retention, cache key và cách vô hiệu hóa cache. Không để một job không tin cậy ghi output vào cache được job phát hành tin cậy sử dụng.

### 10.4. Theo dõi cache correctness

Một cache hit không tự chứng minh output đúng. Cần kiểm tra:

- Task có khai báo đủ input và output không?
- Task có phụ thuộc thời gian, biến môi trường hoặc file ngoài mà không được khai báo không?
- Cache key có phân biệt toolchain hoặc cấu hình cần thiết không?
- Có task nào không deterministic không?
- Có thể chạy build không cache để đối chiếu khi nghi ngờ không?
- Artifact sau cache có vượt qua cùng test và verification không?

Trong giai đoạn đầu, có thể dùng cache ở phạm vi nhỏ, giữ khả năng chạy uncached để so sánh và quan sát cache hit/miss. Nếu phát hiện kết quả sai khác, tắt cache cho task nghi vấn, điều tra input/output declaration rồi mới bật lại.

### 10.5. Kết quả sau thử nghiệm giả định

Sau warm-up và hai tuần quan sát:

| Metric | Trước | Sau | Diễn giải |
|---|---:|---:|---|
| Số lần chạy | 80 | 82 | Khối lượng gần tương đương |
| Median execution time | 12:20 | 9:40 | Giảm khoảng 21,6% |
| p90 execution time | 17:00 | 13:00 | Nhóm run chậm cũng cải thiện |
| Median queue time | 2:00 | 2:05 | Gần như không đổi |
| Test failure rate | 5,0% | 5,1% | Chênh 0,1 điểm phần trăm; cần thêm mẫu để đánh giá biến động |
| Cache hit rate | Chưa đo | 72% | Có tái sử dụng cache |

Kết quả giả định cho thấy execution time giảm và queue time gần như không đổi. Chênh lệch failure rate 0,1 điểm phần trăm với khoảng 80 run mỗi nhóm chưa đủ để kết luận có hay không có tác động thực; cần theo dõi thêm và xem cả nguyên nhân của từng failure. Nếu dữ liệu thực tế đạt tiêu chí đã đặt, nhóm có thể mở rộng thử nghiệm sang các job tương tự.

Không kết luận rằng cache chắc chắn là nguyên nhân duy nhất nếu cùng thời điểm có thay đổi runner hoặc dependency. Hãy ghi các yếu tố đó và cân nhắc một đợt đo tiếp theo.

## 11. Tính mức cải thiện

Có thể tính mức cải thiện tương đối của một metric mà giá trị thấp hơn là tốt hơn:

\[
\text{Improvement (\%)} =
\frac{\text{Baseline} - \text{After}}{\text{Baseline}} \times 100
\]

Với median execution time trong ví dụ:

\[
\frac{12.33 - 9.67}{12.33} \times 100
\approx 21.6\%
\]

Cần giữ cùng đơn vị khi tính. Có thể tính bằng giây để tránh lỗi chuyển phút/giây.

Với metric mà giá trị cao hơn là tốt hơn, ví dụ cache hit rate hoặc deployment success rate, công thức chênh lệch tương đối cần đảo chiều phù hợp. Với tỷ lệ lỗi, nên báo cả chênh lệch điểm phần trăm và thay đổi tương đối để người đọc không nhầm.

Ví dụ, failure rate tăng từ 5,0% lên 5,1% là tăng 0,1 điểm phần trăm, tương đương tăng 2% tương đối. Hai cách diễn đạt trả lời hai câu hỏi khác nhau.

## 12. Đừng chỉ nhìn median

Median cho biết điểm giữa của phân phối, nhưng có thể che giấu các lần chạy rất chậm hoặc một nhóm runner gặp vấn đề.

Nên xem thêm:

- p50: trải nghiệm điển hình.
- p90 hoặc p95: nhóm run chậm.
- Min/max: hữu ích để tìm outlier nhưng không nên dùng làm kết luận chính.
- Phân phối theo runner/OS/branch.
- Queue time và execution time riêng.
- Số lần chạy và số lần bị loại khỏi tập dữ liệu.

Nếu median giảm nhưng p90 tăng mạnh, một nhóm developer có thể vẫn gặp phản hồi rất chậm. Cần điều tra phân phối và phân nhóm trước khi tuyên bố cải tiến thành công.

Không nên gộp các loại job khác nhau vào một median chung. Job unit test 3 phút và job integration 30 phút cần được phân tích riêng hoặc chuẩn hóa theo loại.

## 13. Cần đủ mẫu và thời gian quan sát

Một hoặc hai run không đủ để kết luận hiệu quả của một thay đổi trong CI/CD. Kết quả có thể bị ảnh hưởng bởi cache cold, runner contention, traffic, số lượng test hoặc thời điểm trong ngày.

Chọn cửa sổ đo dựa trên:

- Tần suất chạy thực tế.
- Độ biến động của metric.
- Số lượng branch/PR đại diện.
- Chu kỳ nightly hoặc release.
- Thời gian cần để cache warm-up hoặc workload ổn định.
- Mức rủi ro nếu tiếp tục thử nghiệm.

Nếu dự án có hàng trăm run mỗi ngày, có thể đạt số mẫu trong vài ngày. Nếu chỉ có vài release mỗi tháng, cần quan sát lâu hơn hoặc dùng một tập thử nghiệm có kiểm soát.

Ghi số mẫu cùng mọi con số tổng hợp. Không báo "median giảm 20%" mà không nói median được tính từ bao nhiêu run và khoảng thời gian nào.

## 14. Nhận diện yếu tố gây nhiễu

Một kết quả trước/sau có thể bị ảnh hưởng bởi thay đổi ngoài thử nghiệm.

Các yếu tố thường gặp:

- Runner image hoặc loại máy thay đổi.
- Số lượng test thay đổi do commit khác.
- Branch hoặc PR workload khác nhau.
- Dependency registry chậm hoặc nhanh bất thường.
- Cache đã warm ở một nhóm nhưng cold ở nhóm còn lại.
- Thời điểm chạy trùng giờ cao điểm.
- Concurrency hoặc quota runner thay đổi.
- Có thêm job khác dùng chung tài nguyên.
- Gradle/JDK hoặc plugin được nâng cấp.
- Retry policy thay đổi.
- Một test flaky được quarantine trong cùng đợt.

Cách giảm nhiễu:

1. Giữ runner class và workflow scope ổn định.
2. So sánh cùng loại trigger.
3. Ghi lại version toolchain và matrix.
4. Tách cold run khỏi warm run nếu cache là yếu tố thử nghiệm.
5. Tránh triển khai nhiều thay đổi cùng lúc.
6. Ghi chú những thay đổi không thể kiểm soát.
7. Nếu cần, dùng một nhóm đối chứng hoặc triển khai theo cohort.

Không phải lúc nào cũng có thể loại bỏ toàn bộ yếu tố gây nhiễu. Mục tiêu là làm cho giới hạn của kết luận rõ ràng và không khẳng định quá mức dữ liệu.

## 15. Dùng control group hoặc rollout theo cohort

Với thay đổi có thể bật theo nhóm, có thể giữ một nhóm tương tự làm đối chứng trong thời gian ngắn.

Ví dụ:

- Nhóm A tiếp tục chạy cấu hình CI hiện tại.
- Nhóm B bật cache mới.
- Hai nhóm sử dụng runner class và test scope tương đương.
- So sánh execution time, failure rate và cache errors.

Không phải dự án nào cũng có đủ workload để chia nhóm. Có thể dùng rollout theo repository, branch hoặc job. Cần tránh phân nhóm theo cách khiến một nhóm chỉ nhận task nhẹ còn nhóm kia nhận task nặng.

Nếu có control group, ghi rõ cách phân nhóm, số mẫu và điều kiện. Nếu không có, dùng before/after có kiểm soát và nêu rõ giới hạn suy luận.

## 16. Đặt guardrail và điều kiện dừng

Một cải tiến không được tiếp tục chỉ vì metric chính tốt lên. Cần có điều kiện dừng khi chất lượng hoặc bảo mật bị ảnh hưởng.

Ví dụ guardrail cho cache:

- Không có test bị bỏ qua hoặc giảm coverage.
- Không có khác biệt giữa build cached và uncached ở các kiểm tra cần thiết.
- Tỷ lệ cache restore/save error dưới ngưỡng.
- Không có artifact sai hoặc stale output.
- Không có cache poisoning giữa untrusted và trusted workflow.
- Chi phí storage và network nằm trong giới hạn.
- Tỷ lệ job thất bại không tăng quá mức cho phép.

Khi guardrail bị vi phạm:

1. Dừng mở rộng phạm vi.
2. Tắt hoặc giới hạn thay đổi nếu có nguy cơ ảnh hưởng kết quả.
3. Giữ log/report để điều tra.
4. Xác định nguyên nhân.
5. Sửa và chạy lại thử nghiệm mới với baseline/điều kiện rõ.
6. Ghi lại quyết định và tác động.

Không đợi hết cửa sổ đo nếu có dấu hiệu tạo artifact sai, bỏ qua kiểm tra bảo mật hoặc làm sai kết quả test.

## 17. Quyết định giữ, điều chỉnh hay hoàn tác

Cuối thử nghiệm, không phải lúc nào cũng chỉ có hai kết quả pass/fail.

| Kết quả | Điều kiện | Hành động |
|---|---|---|
| Keep | Metric chính đạt, guardrails đạt | Giữ và mở rộng có kiểm soát |
| Extend | Kết quả có tín hiệu tốt nhưng chưa đủ mẫu | Tiếp tục đo trong phạm vi hiện tại |
| Adjust | Metric chưa đạt nhưng có nguyên nhân cụ thể và cách sửa nhỏ | Sửa kế hoạch và chạy thử nghiệm mới |
| Roll back | Guardrail vi phạm hoặc tác dụng phụ lớn | Hoàn tác và xác minh trạng thái cũ |
| Reject | Không tạo lợi ích đủ lớn so với chi phí | Không áp dụng rộng |
| Inconclusive | Thiếu dữ liệu hoặc có yếu tố gây nhiễu lớn | Không tuyên bố thành công; thiết kế lại phép đo |

Quyết định cần ghi người chịu trách nhiệm và dữ liệu được dùng. Nếu giữ thay đổi, cần xác định liệu có nên mở rộng sang các workflow khác hay chỉ giữ ở job hiện tại.

## 18. Đo tác động ngoài metric chính

Một thay đổi nhỏ có thể tác động tới các nhóm khác ngoài job được chỉnh sửa.

Ví dụ, tăng parallelism có thể làm một job nhanh hơn nhưng tăng queue time của repository khác. Cache có thể giảm download nhưng tăng chi phí storage. Chuyển test sang nightly có thể giảm PR duration nhưng kéo dài thời gian phát hiện regression.

Do đó, xem xét:

- Tác động tới developer feedback.
- Tác động tới quota và chi phí runner.
- Tác động tới storage/network.
- Tác động tới độ tin cậy của kết quả.
- Tác động tới thời gian phát hiện lỗi.
- Tác động tới các workflow hoặc project dùng chung.
- Tác động tới bảo mật và quyền truy cập.

Đây là lý do cần guardrail ở cấp hệ thống khi thay đổi ảnh hưởng tài nguyên dùng chung.

## 19. Ghi lại kết quả để nhóm có thể học lại

Một thử nghiệm nên có record ngắn, đủ để người khác hiểu điều gì đã được thử và vì sao quyết định được đưa ra.

Record có thể gồm:

- Tên và owner của thử nghiệm.
- Vấn đề và phạm vi.
- Hypothesis.
- Baseline window và sample count.
- Metric chính và guardrails.
- Thay đổi đã triển khai, commit hoặc PR.
- Thời điểm bắt đầu và kết thúc.
- Kết quả trước/sau.
- Các yếu tố gây nhiễu.
- Sự cố hoặc ngoại lệ.
- Quyết định keep/extend/adjust/rollback/reject.
- Bước tiếp theo và owner.

Không cần viết báo cáo dài cho mọi thay đổi nhỏ. Một bảng trong issue hoặc pull request có thể đủ. Nhưng kết quả phải được lưu ở nơi nhóm có thể tìm lại khi đánh giá cải tiến tiếp theo.

## 20. Tránh các cách cải tiến tạo số đẹp nhưng chất lượng giảm

Một số cách làm có thể khiến metric trông tốt hơn trong ngắn hạn nhưng làm hệ thống kém tin cậy:

- Xóa test chậm thay vì tối ưu test.
- Chuyển test quan trọng khỏi PR mà không có release gate thay thế.
- Thêm retry vô hạn để biến job đỏ thành xanh.
- Bỏ qua failure của một platform.
- Dùng cache không an toàn và không xác minh output.
- Giảm timeout đến mức job bị kill trước khi báo lỗi có ích.
- Đo thời gian chỉ ở job nhanh hơn mà bỏ qua thời gian queue.
- So sánh một run cold với một run warm.
- Thay đổi nhiều yếu tố rồi gán toàn bộ lợi ích cho một thay đổi.
- Không tính chi phí runner/storage hoặc công sức bảo trì.

Cải tiến có ý nghĩa phải nâng hiệu quả mà vẫn giữ độ tin cậy, khả năng truy vết và mức chất lượng đã cam kết.

## 21. Ví dụ khác: giảm flaky test bằng cách sửa nguyên nhân

Giả sử một integration test thất bại ngẫu nhiên khoảng 4% số lần chạy do phụ thuộc vào thời gian khởi động của service test.

Thay đổi nhỏ có thể là chờ readiness condition rõ ràng thay vì sleep cố định.

Kế hoạch:

- Baseline: ghi số lần chạy, failure rate và thời gian chờ hiện tại.
- Hypothesis: readiness polling sẽ giảm false failure mà không làm tăng thời gian đáng kể.
- Change: thay sleep cố định bằng polling có timeout và thông báo lỗi.
- Guardrails: test vẫn thất bại nếu service không ready; không tăng timeout vô hạn.
- Measure: so sánh failure rate, p90 test duration và timeout count.
- Decision: giữ nếu false failure giảm mà lỗi thật vẫn được phát hiện.

Không nên chỉ tăng retry count để che flaky test. Retry có thể hữu ích cho lỗi hạ tầng tạm thời nếu được phân loại, giới hạn và ghi nhận; nó không thay thế việc sửa nguyên nhân khiến test không ổn định.

## 22. Cải tiến liên tục theo vòng lặp nhỏ

Sau khi một thử nghiệm kết thúc, nhóm có thể lặp lại:

1. Xem lại metric và phản hồi của developer.
2. Xác định bottleneck tiếp theo có tác động lớn.
3. Kiểm tra nguyên nhân thay vì đoán.
4. Viết hypothesis và guardrails.
5. Chọn một thay đổi nhỏ.
6. Đo baseline.
7. Thử nghiệm trong phạm vi kiểm soát.
8. So sánh và quyết định.
9. Cập nhật tài liệu, workflow và ownership.
10. Chuyển sang vấn đề tiếp theo.

Không nên mở nhiều thử nghiệm chồng lấn trên cùng một metric nếu không thể tách tác động. Nếu nhiều thay đổi cần diễn ra đồng thời, hãy xác định cách đo từng thay đổi hoặc chấp nhận rằng kết quả chỉ có thể đánh giá ở cấp nhóm thay đổi.

Cải tiến không phải một chiến dịch kết thúc khi đạt một con số. Pipeline, dependency, runner và nhu cầu sản phẩm thay đổi liên tục; nhóm cần duy trì thói quen xem dữ liệu và điều chỉnh theo bằng chứng.

## 23. Checklist trước khi áp dụng một cải tiến nhỏ

- [ ] Vấn đề có dữ liệu hoặc ví dụ cụ thể.
- [ ] Metric có định nghĩa và cách tính rõ.
- [ ] Baseline có khoảng thời gian và số mẫu.
- [ ] Đã tách queue time khỏi execution time nếu phù hợp.
- [ ] Có một metric chính để đánh giá.
- [ ] Có guardrails cho test, security, artifact và chi phí.
- [ ] Hypothesis có thể được xác nhận hoặc bác bỏ.
- [ ] Thay đổi có phạm vi nhỏ và owner.
- [ ] Có cách rollout và rollback.
- [ ] Điều kiện so sánh trước/sau tương đương.
- [ ] Yếu tố gây nhiễu được ghi lại.
- [ ] Cửa sổ đo và sample size phù hợp.
- [ ] Không giảm test coverage hoặc gate để làm đẹp số.
- [ ] Có tiêu chí dừng khi guardrail vi phạm.
- [ ] Có quyết định keep, extend, adjust, rollback hoặc reject.
- [ ] Kết quả được ghi lại và chia sẻ cho nhóm.

## Kết luận

Chọn một cải tiến nhỏ và kiểm tra ảnh hưởng sau khi áp dụng là cách biến cải tiến CI/CD thành một hoạt động có thể học hỏi và lặp lại. Nhóm cần bắt đầu từ vấn đề quan sát được, xác định metric và baseline, nêu hypothesis, thay đổi một yếu tố trong phạm vi nhỏ rồi đo cả kết quả mong muốn lẫn guardrails.

Một thay đổi chỉ nên được giữ khi dữ liệu cho thấy lợi ích đủ rõ và chất lượng, bảo mật, chi phí cùng khả năng truy vết vẫn được bảo vệ. Nếu kết quả chưa đủ mẫu hoặc có yếu tố gây nhiễu, hãy tiếp tục đo hoặc thiết kế lại thử nghiệm. Nếu guardrail bị vi phạm, dừng và hoàn tác. Cách làm này giúp nhóm cải thiện từng bước mà không đánh đổi độ tin cậy của quy trình phát hành.

