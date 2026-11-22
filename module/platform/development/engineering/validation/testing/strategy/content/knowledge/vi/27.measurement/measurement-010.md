# Nhận diện chỉ số dễ bị tối ưu sai hoặc thiếu ngữ cảnh

## 1. Vì sao cần thận trọng khi dùng chỉ số chất lượng?

Chỉ số giúp nhóm quan sát xu hướng, so sánh kết quả, phát hiện vấn đề và quyết định nơi cần đầu tư. Trong kiểm thử và xác nhận chất lượng, các con số như tỷ lệ test pass, code coverage, số defect, thời gian pipeline, defect escape rate hoặc thời gian khôi phục thường được dùng để đánh giá tình trạng sản phẩm và hiệu quả quy trình.

Tuy nhiên, một chỉ số không phải là toàn bộ sự thật về chất lượng. Nó chỉ phản ánh một khía cạnh được đo theo một định nghĩa, phạm vi, nguồn dữ liệu và khoảng thời gian nhất định. Nếu thiếu ngữ cảnh, một con số có thể tạo ra kết luận sai. Nếu gắn phần thưởng hoặc áp lực trực tiếp vào chỉ số, nhóm có thể tối ưu con số thay vì cải thiện kết quả mà chỉ số được dùng để đại diện.

Ví dụ:

- Tỷ lệ test pass tăng vì nhóm xóa hoặc quarantine những test hay thất bại, trong khi rủi ro chưa được kiểm tra vẫn tăng.
- Code coverage tăng nhờ thêm assertion hời hợt, nhưng các nhánh nghiệp vụ quan trọng vẫn chưa được xác nhận.
- Số defect giảm vì nhóm ít ghi nhận lỗi hơn, chứ không phải sản phẩm ít lỗi hơn.
- Thời gian sửa defect giảm vì các lỗi khó được phân loại lại hoặc để ở trạng thái chờ thông tin.
- Pipeline nhanh hơn vì các test dài bị bỏ khỏi gate, trong khi thời gian phát hiện lỗi sau tích hợp tăng.
- MTTR giảm vì incident được đóng sớm trên hệ thống theo dõi, dù tác động đến người dùng chưa kết thúc.

Hiện tượng một chỉ số trở thành mục tiêu rồi làm méo hành vi được thường liên hệ với **Goodhart's law**: khi một thước đo trở thành mục tiêu, nó có thể không còn là thước đo tốt. Đây không phải lý do để bỏ đo lường. Nó là lời nhắc phải thiết kế chỉ số cẩn thận, theo dõi tác dụng phụ và kết hợp bằng chứng định lượng với hiểu biết về hệ thống.

Trong phạm vi **VALIDATION_TESTING_STRATEGY**, cần nhận diện chỉ số dễ bị tối ưu sai hoặc thiếu ngữ cảnh để tránh kết luận rằng một quy trình kiểm thử tốt chỉ vì dashboard có nhiều màu xanh. Mục tiêu là đo đúng điều cần cải thiện, hiểu giới hạn của con số và không tạo động lực che giấu rủi ro.

## 2. Phân biệt chỉ số, mục tiêu, ngưỡng và bằng chứng

Các khái niệm này thường bị trộn lẫn:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Metric (chỉ số) | Đại lượng được quan sát hoặc tính toán | Tỷ lệ test pass của regression suite |
| Measurement (phép đo) | Quy trình thu thập và tính giá trị metric | Tổng số test pass chia cho tổng số test có kết quả hợp lệ |
| Target (mục tiêu) | Mức muốn đạt trong một khoảng thời gian hoặc phạm vi | Giảm thời gian phản hồi CI xuống một mức đã thống nhất |
| Threshold (ngưỡng) | Ranh giới dùng để cảnh báo hoặc ra quyết định | Không cho release khi còn finding Critical chưa xử lý |
| KPI | Chỉ số trọng yếu được dùng để theo dõi kết quả quản trị | Tỷ lệ rủi ro cao có bằng chứng xác nhận trước release |
| SLI | Chỉ số đo một khía cạnh của dịch vụ | Tỷ lệ request thành công hoặc độ trễ |
| SLO | Mục tiêu cho SLI trong một cửa sổ thời gian | Tỷ lệ request thành công tối thiểu theo kỳ |
| Evidence (bằng chứng) | Dữ liệu, artifact và ngữ cảnh hỗ trợ một kết luận | Test report gắn với build, environment và test ID |

Một metric có thể hữu ích để quan sát nhưng chưa phù hợp làm mục tiêu thưởng/phạt. Một target có thể giúp định hướng nhưng không tự động trở thành ngưỡng release. Một threshold có thể chặn hành động nhưng cần được kiểm chứng rằng nó phản ánh đúng rủi ro.

Ví dụ, code coverage 80% là một con số. Nó chỉ có ý nghĩa khi biết loại coverage, mẫu số, mã nào nằm trong phạm vi, test nào được tính, công cụ nào tạo báo cáo và phần mã nào quan trọng. Nếu đặt mục tiêu “mọi nhóm phải đạt 80%” mà không xét loại sản phẩm và rủi ro, nhóm có thể tập trung tăng số dòng được thực thi thay vì kiểm tra hành vi.

## 3. Cơ chế khiến chỉ số bị tối ưu sai

### 3.1. Goodhart's law và Campbell's law

Khi một chỉ số được dùng làm mục tiêu cứng, mọi người có xu hướng điều chỉnh hoạt động để đạt chỉ số đó. Nếu chỉ số chỉ đại diện một phần của mục tiêu thực, hành vi có thể lệch khỏi kết quả mong muốn.

Campbell's law cũng cảnh báo rằng càng dùng một chỉ số định lượng cho quyết định có hệ quả lớn, áp lực làm sai lệch chỉ số và quy trình đo lường càng tăng.

Trong thực tế, metric gaming không nhất thiết là gian lận có chủ ý. Nó có thể xuất hiện do:

- Mục tiêu được đặt mà không giải thích mục đích.
- Nhóm bị đánh giá bằng một con số nằm ngoài khả năng kiểm soát.
- Chỉ số dễ đạt hơn kết quả thực cần cải thiện.
- Hệ thống ghi nhận trạng thái không phản ánh đầy đủ thực tế.
- Người quản lý chỉ xem dashboard mà không xem mẫu dữ liệu.
- Các tác dụng phụ không được đo hoặc không được quan tâm.

### 3.2. Tối ưu cục bộ

Một nhóm có thể cải thiện chỉ số của mình nhưng làm xấu kết quả tổng thể. Ví dụ, nhóm kiểm thử giảm thời gian pipeline bằng cách chuyển phần lớn test sang lịch chạy ban đêm. PR có phản hồi nhanh hơn, nhưng lỗi tích hợp chỉ được phát hiện muộn, làm tăng chi phí sửa và rủi ro release.

Tối ưu cục bộ thường xuất hiện khi metric không bao gồm luồng công việc đầu-cuối hoặc tác động đến nhóm tiêu thụ kết quả.

### 3.3. Thay đổi định nghĩa hoặc mẫu số

Chỉ số có thể tăng mà hành vi thực tế không thay đổi nếu nhóm:

- Loại test thất bại khỏi mẫu số.
- Đổi cách phân loại defect.
- Chỉ tính module dễ đạt coverage.
- Bỏ qua lần chạy bị hủy hoặc blocked.
- Thay đổi cửa sổ thời gian để loại sự kiện xấu.
- Đổi severity sau khi finding đã được ghi nhận.

Mọi thay đổi định nghĩa cần có phiên bản, lý do và khả năng so sánh trước/sau. Không nên nối hai chuỗi số liệu có định nghĩa khác nhau như thể chúng cùng một metric.

### 3.4. Chạy theo con số thay vì theo rủi ro

Khi số lượng test hoặc tỷ lệ pass trở thành mục tiêu, nhóm có thể ưu tiên test dễ viết, dễ chạy và ít thất bại. Các tình huống hiếm, luồng xuyên dịch vụ hoặc rủi ro bảo mật có thể bị bỏ qua vì khó tạo thành tích nhanh.

Một bộ test nhỏ nhưng bao phủ đúng rủi ro có thể hữu ích hơn một bộ test lớn có nhiều trường hợp trùng lặp. Ngược lại, số lượng test thấp không tự động chứng minh suite được thiết kế tốt. Cần đánh giá nội dung và bằng chứng.

## 4. Ngữ cảnh tối thiểu phải có khi đọc một chỉ số

Trước khi so sánh hoặc ra quyết định từ một con số, cần xác định:

1. **Định nghĩa:** metric đo chính xác điều gì và tính như thế nào?
2. **Phạm vi:** sản phẩm, service, suite, môi trường, nhóm người dùng hoặc release nào?
3. **Mẫu số:** những đối tượng nào được tính và những đối tượng nào bị loại?
4. **Thời gian:** cửa sổ đo, thời điểm chốt và độ trễ dữ liệu?
5. **Phân bố:** trung bình, median, percentile, min/max hay tỷ lệ theo nhóm?
6. **Nguồn dữ liệu:** pipeline, test management, incident system, log hay nhập thủ công?
7. **Chất lượng dữ liệu:** thiếu, trùng, sai nhãn hoặc thay đổi schema có thể ảnh hưởng không?
8. **Điều kiện so sánh:** build, cấu hình, workload, môi trường và quy trình có tương đương không?
9. **Yếu tố tác động:** có thay đổi sản phẩm, đội ngũ, công cụ hoặc cách đo trong kỳ không?
10. **Hành động:** nếu metric tăng/giảm thì nhóm sẽ làm gì và ai chịu trách nhiệm?

Nếu không trả lời được các câu hỏi này, con số nên được xem là tín hiệu sơ bộ thay vì kết luận chắc chắn.

## 5. Các chỉ số kiểm thử dễ bị tối ưu sai

### 5.1. Tỷ lệ test pass

**Cách hiểu thông thường:** số test passed chia cho số test đã thực thi có kết quả kết luận.

**Nguy cơ tối ưu sai:**

- Xóa test khó hoặc hay thất bại.
- Quarantine test nhưng không theo dõi thời hạn và khoảng trống.
- Retry đến khi pass rồi chỉ báo cáo lần cuối.
- Bỏ qua test blocked, inconclusive hoặc not run.
- Chạy test trên build cũ nhưng gắn kết quả cho build mới.

**Ngữ cảnh cần bổ sung:**

- Tổng số test trong phạm vi và số test theo từng trạng thái.
- Test bắt buộc so với test mở rộng.
- Số lần retry và lịch sử flaky.
- Build, môi trường, dữ liệu và thời điểm.
- Bao phủ theo yêu cầu, hành trình và rủi ro.
- Lý do loại test khỏi mẫu số.

Không nên chỉ công bố “pass rate 98%”. Cần cho biết còn bao nhiêu test failed, blocked, not run, skipped và quarantined, đồng thời rủi ro nào chưa có bằng chứng.

### 5.2. Code coverage

Các loại coverage thường gặp gồm line, statement, branch, function và condition coverage. Chúng đo mức thực thi mã theo những cách khác nhau, không trực tiếp đo mức độ kiểm tra đúng của assertion.

**Nguy cơ tối ưu sai:**

- Thêm test chỉ để chạy qua dòng mã.
- Assertion quá yếu hoặc không kiểm tra kết quả có ý nghĩa.
- Tập trung vào mã dễ đo, bỏ qua luồng quan trọng.
- Exclude mã khó kiểm tra khỏi phạm vi mà không ghi lý do.
- So sánh coverage giữa ngôn ngữ, framework hoặc module khác nhau.

**Ngữ cảnh cần bổ sung:**

- Loại coverage và công cụ.
- Mã nguồn nằm trong phạm vi.
- Coverage của phần mã thay đổi và baseline.
- Branch quan trọng chưa được kiểm tra.
- Liên kết với requirement/risk coverage.
- Chất lượng assertion và mutation testing nếu có.

Coverage thấp có thể chỉ ra khoảng trống, nhưng coverage cao không chứng minh chất lượng cao. Nên dùng coverage để đặt câu hỏi “phần nào chưa được thực thi?” chứ không dùng nó như đại diện duy nhất cho chất lượng test.

### 5.3. Số lượng test case

**Nguy cơ tối ưu sai:** tạo nhiều test tương tự nhau, chia một scenario thành nhiều test nhỏ hoặc đếm cả test vô hiệu hóa để tăng quy mô.

**Ngữ cảnh cần bổ sung:** số test độc lập, độ bao phủ theo rủi ro, mức trùng lặp, độ ổn định, thời gian chạy và tỷ lệ test có owner. Số lượng chỉ hữu ích khi biết suite bảo vệ những hành vi nào.

### 5.4. Defect count

**Nguy cơ tối ưu sai:**

- Nhóm giảm ghi nhận lỗi để đạt mục tiêu ít defect.
- Lỗi được phân loại thành change request hoặc support issue để không tính vào defect.
- Nhiều lỗi nhỏ được gộp vào một ticket, làm giảm số lượng.
- Lỗi nghiêm trọng bị hạ severity.
- Chỉ đếm lỗi đã đóng, bỏ qua lỗi mở hoặc lỗi chưa triage.

**Ngữ cảnh cần bổ sung:**

- Defect theo severity, priority, component và release.
- Tỷ lệ lỗi được phát hiện trước/sau phát hành.
- Mức độ ảnh hưởng và số người dùng/giao dịch liên quan.
- Defect aging, reopen và recurrence.
- Quy tắc phân loại và thay đổi taxonomy.

Số defect tăng có thể phản ánh việc kiểm thử tốt hơn hoặc báo cáo minh bạch hơn. Số defect giảm có thể phản ánh chất lượng tốt hơn, nhưng cũng có thể do phát hiện yếu hơn. Cần xem cùng escaped defect, mức độ nghiêm trọng và phạm vi kiểm thử.

### 5.5. Defect density

Defect density thường được tính theo số defect trên một đơn vị kích thước như KLOC, function point hoặc module size.

**Nguy cơ tối ưu sai:** thay đổi cách đếm dòng mã, chia/gộp module, ghi nhận defect không nhất quán hoặc so sánh các thành phần có độ phức tạp khác nhau.

**Ngữ cảnh cần bổ sung:** đơn vị kích thước, loại defect, thời điểm phát hiện, mức độ nghiêm trọng, độ phức tạp và cách tính phạm vi. Không nên so sánh trực tiếp defect density của một thư viện tiện ích với một hệ thống giao dịch phân tán.

### 5.6. Defect escape rate

Chỉ số này thường mô tả tỷ lệ lỗi được phát hiện ở giai đoạn sau hoặc sau phát hành so với tổng số lỗi thuộc phạm vi đo.

**Nguy cơ tối ưu sai:**

- Thay đổi thời điểm hoặc cách phân loại lỗi.
- Bỏ lỗi do người dùng báo cáo khỏi mẫu số.
- Chỉ tính lỗi có nguyên nhân đã xác nhận.
- Đếm lỗi theo ticket thay vì theo sự kiện hoặc tác động.
- Cửa sổ theo dõi sau release quá ngắn.

**Ngữ cảnh cần bổ sung:** release cohort, cửa sổ quan sát, nguồn báo lỗi, severity, số người dùng bị ảnh hưởng, cách xử lý lỗi trùng và độ trễ báo cáo.

Một release mới có thể có escape rate thấp trong tuần đầu nhưng tăng sau khi nhiều người dùng gặp tình huống hiếm. Vì vậy, phải nêu rõ ngày chốt và cập nhật khi có dữ liệu mới.

### 5.7. Thời gian phát hiện lỗi (time to detect)

**Nguy cơ tối ưu sai:** đo từ lúc ticket được tạo thay vì từ lúc lỗi xuất hiện; không tính lỗi không được phát hiện; đóng khoảng thời gian khi hệ thống chưa có quan sát.

**Ngữ cảnh cần bổ sung:** thời điểm thay đổi gây lỗi, thời điểm lỗi bắt đầu, thời điểm có tín hiệu đầu tiên, thời điểm xác nhận và nguồn timestamp. Có thể báo cáo median và percentile theo severity hoặc loại lỗi thay vì chỉ trung bình.

### 5.8. Thời gian sửa lỗi (time to fix)

**Nguy cơ tối ưu sai:**

- Đóng ticket trước khi xác minh.
- Chuyển ticket sang trạng thái chờ để dừng đồng hồ.
- Tách một lỗi thành nhiều ticket hoặc gộp lỗi.
- Không tính thời gian chờ review, deploy hoặc xác nhận.

**Ngữ cảnh cần bổ sung:** định nghĩa điểm bắt đầu/kết thúc, thời gian chờ theo trạng thái, severity, độ phức tạp, thời điểm fix được deploy và thời điểm xác minh hoàn tất.

Nên phân biệt thời gian từ lúc báo lỗi đến khi có owner, thời gian phân tích, thời gian sửa, thời gian chờ phát hành và thời gian xác minh. Một con số duy nhất có thể che phần nghẽn thực tế.

### 5.9. Flaky test rate

**Nguy cơ tối ưu sai:** loại test flaky khỏi mẫu số, chỉ tính lần chạy cuối hoặc không ghi số retry.

**Ngữ cảnh cần bổ sung:** test nào được chạy bao nhiêu lần, điều kiện môi trường, số lần retry, mức độ ảnh hưởng, trạng thái quarantine và thời gian tồn tại của flaky test.

Flaky test làm giảm niềm tin vào pipeline. Tuy nhiên, giảm flaky rate bằng cách tắt test sẽ làm giảm khả năng phát hiện. Cần theo dõi cả flaky rate và tỷ lệ test bị cách ly, tuổi cách ly, cùng rủi ro bị mất.

### 5.10. Thời gian pipeline

**Nguy cơ tối ưu sai:** bỏ test dài, giảm số lần chạy, giảm mức song song hoặc không tính thời gian chờ môi trường.

**Ngữ cảnh cần bổ sung:** thời gian theo stage, percentile, queue time, provisioning time, retry, số test thực thi, tỷ lệ hủy và độ trễ phát hiện lỗi.

Pipeline nhanh hơn là tốt nếu vẫn giữ đủ bằng chứng cần thiết. Nếu thời gian giảm vì test trọng yếu bị dời khỏi điểm kiểm soát, cần đo thêm thời gian phát hiện lỗi và chi phí sửa muộn.

### 5.11. Test automation rate

**Nguy cơ tối ưu sai:** tự động hóa test không quan trọng chỉ để tăng tỷ lệ; đếm script thay vì hành vi được kiểm tra; bỏ qua chi phí bảo trì và flaky.

**Ngữ cảnh cần bổ sung:** tỷ lệ hành vi/rủi ro phù hợp đã được tự động hóa, độ ổn định, chi phí duy trì, thời gian tiết kiệm, khả năng phát hiện lỗi và phần kiểm thử thủ công còn cần thiết.

Tự động hóa là phương tiện. Một test thủ công có giá trị cao và khó tự động hóa có thể là lựa chọn hợp lý nếu có owner, cadence và bằng chứng rõ.

## 6. Các chỉ số vận hành và quản trị cũng cần ngữ cảnh

### 6.1. MTTR (Mean Time to Recovery/Restore/Repair)

MTTR có nhiều cách mở rộng và định nghĩa. Có nơi dùng mean time to recovery, nơi khác dùng repair hoặc restore. Trước khi so sánh, phải ghi rõ định nghĩa.

**Nguy cơ tối ưu sai:** đóng incident sớm, không tính thời gian tác động còn lại, gộp incident nhỏ và lớn hoặc bỏ qua thời gian khôi phục dữ liệu.

**Ngữ cảnh cần bổ sung:** định nghĩa start/end, mức độ incident, thời gian khôi phục dịch vụ, thời gian khôi phục dữ liệu, thời gian đến khi người dùng không còn bị ảnh hưởng và số lượng người dùng/giao dịch.

Nên kết hợp MTTR với recurrence, customer impact, time to detect và thời gian phục hồi hoàn toàn. MTTR giảm nhưng incident tái diễn thường xuyên không phải kết quả tốt.

### 6.2. Availability và uptime

**Nguy cơ tối ưu sai:** dùng khoảng thời gian đo dài để làm loãng một outage ngắn nhưng nghiêm trọng; bỏ maintenance hoặc lỗi một vùng; đo health endpoint thay vì hành trình người dùng.

**Ngữ cảnh cần bổ sung:** service boundary, user journey, cửa sổ thời gian, loại request, lỗi được tính, vùng địa lý, dependency và cách xử lý planned maintenance.

Một dịch vụ có uptime cao nhưng chức năng thanh toán thường xuyên thất bại vẫn không đáp ứng mục tiêu nghiệp vụ.

### 6.3. Số incident

**Nguy cơ tối ưu sai:** thay đổi ngưỡng tạo incident, không mở incident cho sự cố lặp lại hoặc phân loại thành support request.

**Ngữ cảnh cần bổ sung:** severity, thời gian tác động, số người dùng, recurrence, nguyên nhân, mức độ gián đoạn và cách phát hiện.

Số incident tăng trong giai đoạn đầu có thể do khả năng phát hiện tốt hơn. Cần xem xu hướng cùng tác động thực tế thay vì coi mọi lần tăng là suy giảm chất lượng.

### 6.4. SLA/SLO compliance

**Nguy cơ tối ưu sai:** chọn cửa sổ đo hoặc định nghĩa request thuận lợi, loại bỏ lỗi từ dependency mà người dùng vẫn cảm nhận, hoặc tối ưu một SLI làm giảm chất lượng khía cạnh khác.

**Ngữ cảnh cần bổ sung:** user journey, SLI definition, SLO window, error budget, dependency và các chỉ số bổ trợ như latency, correctness, data freshness.

### 6.5. Chi phí kiểm thử

**Nguy cơ tối ưu sai:** giảm chi phí hạ tầng bằng cách cắt môi trường, thiết bị hoặc test chuyên biệt; không tính chi phí điều tra lỗi lọt; chuyển chi phí sang nhóm khác.

**Ngữ cảnh cần bổ sung:** cost per useful evidence, chi phí bảo trì, chi phí chờ, chi phí lỗi sau phát hành, mức sử dụng tài nguyên và rủi ro bị bỏ sót.

Chi phí thấp không phải mục tiêu độc lập. Cần đánh giá giá trị bằng chứng và hậu quả của việc không kiểm tra.

## 7. Dùng bộ chỉ số cân bằng thay vì một con số đơn lẻ

Một chỉ số đơn thường tạo góc nhìn hẹp. Có thể kết hợp metric chính với guardrail và bằng chứng định tính.

| Mục tiêu | Metric chính | Guardrail/bối cảnh bổ sung |
|---|---|---|
| Cải thiện độ tin cậy của regression | Tỷ lệ test pass theo suite | Failed/blocked/not run, flaky, quarantine age, risk coverage |
| Cải thiện coverage | Branch/requirement coverage | Assertion quality, mutation score, rủi ro chưa có test |
| Giảm thời gian CI | p50/p95 pipeline duration | Test trọng yếu đã chạy, escaped defects, queue time |
| Giảm defect sau release | Escaped defect rate | Severity, customer impact, reporting window, detection capability |
| Tăng tự động hóa | Tỷ lệ kịch bản phù hợp được tự động hóa | Flaky rate, maintenance cost, manual exploratory findings |
| Rút ngắn khôi phục | MTTR theo severity | Recurrence, time to detect, data recovery, customer impact |
| Cải thiện hiệu năng | p95/p99 latency và throughput | Error rate, workload, data volume, resource saturation |
| Tăng readiness release | Tỷ lệ tiêu chí bắt buộc có bằng chứng | Waiver, untested risks, rollback readiness, monitoring |

### 7.1. Leading và lagging indicators

**Leading indicators** cung cấp tín hiệu sớm về khả năng xảy ra vấn đề, ví dụ tỷ lệ thay đổi có impact analysis, tỷ lệ suite có owner, tuổi của flaky test hoặc tỷ lệ migration được thử trên dữ liệu đại diện.

**Lagging indicators** phản ánh kết quả đã xảy ra, ví dụ escaped defects, incident, dữ liệu sai hoặc thời gian gián đoạn.

Chỉ dùng lagging indicators khiến nhóm biết vấn đề sau khi tác động đã xuất hiện. Chỉ dùng leading indicators có thể tạo cảm giác an toàn nếu các hoạt động được hoàn thành nhưng không cải thiện kết quả. Cần kết hợp cả hai và kiểm tra mối liên hệ theo thời gian.

### 7.2. Guardrail metrics

Guardrail là chỉ số bảo vệ để một mục tiêu không được cải thiện bằng cách làm xấu khía cạnh quan trọng khác.

Ví dụ, mục tiêu giảm pipeline duration có guardrail là test bắt buộc vẫn chạy trên đúng build, tỷ lệ lỗi lọt không tăng và thời gian phát hiện không xấu đi. Mục tiêu tăng automation có guardrail là flaky rate, maintenance effort và tỷ lệ kịch bản rủi ro cao được kiểm tra.

Guardrail cần có ngưỡng và hành động. Nếu chỉ theo dõi mà không phản ứng khi vượt ngưỡng, nó khó ngăn tối ưu sai.

## 8. Phân đoạn dữ liệu để tránh kết luận sai

Giá trị trung bình tổng thể có thể che khuất nhóm có kết quả rất khác. Khi phù hợp, hãy phân đoạn theo:

- Service, module hoặc domain.
- Severity và priority.
- Loại test: unit, API, contract, integration, E2E, performance.
- Môi trường và phiên bản.
- Nhóm người dùng, tenant hoặc khu vực.
- Loại thay đổi: code, dependency, schema, config, infrastructure.
- Release cohort và khoảng thời gian sau phát hành.
- Nhóm test bắt buộc, mở rộng, flaky hoặc quarantined.

Ví dụ, tỷ lệ pass tổng thể 97% có thể trông tốt, nhưng suite thanh toán chỉ đạt 70% trong khi suite giao diện đạt 99%. Nếu chỉ nhìn tổng thể, nhóm có thể bỏ qua rủi ro ở khu vực trọng yếu.

Phân đoạn quá sâu cũng có rủi ro: số mẫu nhỏ làm tỷ lệ dao động mạnh và có thể nhận diện cá nhân hoặc nhóm nhỏ. Cần cân bằng độ chi tiết với độ tin cậy thống kê và quyền riêng tư.

## 9. Baseline, xu hướng và so sánh công bằng

### 9.1. Thiết lập baseline

Baseline là mốc tham chiếu được xác định rõ, không nhất thiết là giá trị tốt nhất từng đạt. Khi thiết lập, ghi:

- Phiên bản sản phẩm và công cụ.
- Phạm vi đo và định nghĩa metric.
- Môi trường, cấu hình và workload.
- Cửa sổ thời gian và số mẫu.
- Các thay đổi lớn trong quy trình.
- Những giới hạn hoặc dữ liệu thiếu.

Nếu baseline được đo trên môi trường khác hoặc bộ test khác, cần nêu rõ giới hạn so sánh.

### 9.2. So sánh cùng điều kiện

So sánh hai kỳ cần xem các điều kiện có tương đương không. Ví dụ, pipeline duration có thể tăng vì bộ test được mở rộng; escaped defect rate có thể tăng vì số người dùng tăng; MTTR có thể giảm vì incident nhẹ hơn.

Khi điều kiện khác nhau, hãy phân tích nguyên nhân thay vì kết luận trực tiếp rằng chất lượng tăng hoặc giảm.

### 9.3. Dùng median và percentile khi phân bố lệch

Thời gian pipeline, thời gian triage và latency thường có phân bố lệch. Mean có thể bị kéo bởi một số lần chạy rất dài. Median mô tả điểm giữa; p90/p95/p99 giúp thấy phần đuôi. Cần chọn thống kê phù hợp với câu hỏi và công bố số mẫu.

### 9.4. Nhận biết cỡ mẫu nhỏ

Một tỷ lệ từ 5 lần chạy không có độ chắc chắn như tỷ lệ từ hàng nghìn lần chạy. Khi số mẫu nhỏ, nên hiển thị số đếm và cảnh báo bất định. Không nên xếp hạng nhóm theo phần trăm khi số lượng cơ hội khác nhau đáng kể.

## 10. Đọc tương quan mà không kết luận quan hệ nhân quả

Hai metric cùng thay đổi không chứng minh metric này gây ra metric kia. Ví dụ, sau khi tăng automation rate, số defect production giảm. Có thể automation đã góp phần, nhưng cũng có thể do thay đổi nhỏ hơn, lưu lượng thấp hơn, release ít hơn hoặc quy trình review được cải thiện.

Khi đánh giá một thay đổi:

1. Ghi giả thuyết trước khi triển khai.
2. Xác định kết quả chính và guardrail.
3. Ghi yếu tố có thể gây nhiễu.
4. So sánh theo cùng phạm vi hoặc cohort phù hợp.
5. Kiểm tra cả xu hướng trước và sau, không chỉ hai điểm đơn.
6. Tìm bằng chứng định tính từ incident, defect và người thực hiện.
7. Nêu mức độ chắc chắn thay vì khẳng định quá mức.

Nếu có thể, dùng pilot, nhóm đối chứng hoặc triển khai theo giai đoạn để hiểu tác động. Trong môi trường phức tạp, không phải lúc nào cũng có thể cô lập một biến; khi đó cần trình bày giới hạn của suy luận.

## 11. Chất lượng dữ liệu đo lường

Metric sai thường bắt nguồn từ dữ liệu đầu vào không đáng tin. Cần kiểm tra:

- **Completeness:** có thiếu event, report hoặc trạng thái không?
- **Accuracy:** nhãn, timestamp và kết quả có phản ánh sự thật không?
- **Consistency:** các công cụ có dùng cùng định nghĩa và ID không?
- **Timeliness:** dữ liệu có đến trễ hoặc cập nhật sau thời điểm chốt không?
- **Uniqueness:** event hoặc defect có bị đếm trùng không?
- **Lineage:** có biết nguồn, phép biến đổi và phiên bản dữ liệu không?

### 11.1. Chuẩn hóa trạng thái

Các hệ thống có thể dùng trạng thái khác nhau như skipped, disabled, ignored, quarantined hoặc not applicable. Cần có mapping rõ và không gộp trạng thái có ý nghĩa khác nhau.

### 11.2. Gắn định danh và phiên bản

Mỗi kết quả nên liên kết với test ID, suite version, commit/build, environment ID, run ID, dataset/seed và thời gian. Khi thiếu định danh, khó xác định report có thuộc release đang đánh giá không.

### 11.3. Quản lý thay đổi định nghĩa

Khi đổi công cụ, schema, cách tính hoặc taxonomy, cần ghi ngày hiệu lực và phiên bản. Nếu không thể tính lại dữ liệu lịch sử theo định nghĩa mới, hãy bắt đầu chuỗi mới hoặc ghi chú điểm gãy trong biểu đồ.

### 11.4. Phát hiện dữ liệu bất thường

Theo dõi đột biến như pass rate tăng mạnh trong khi số test chạy giảm, defect count giảm đột ngột sau khi đổi taxonomy, pipeline duration giảm cùng lúc nhiều stage bị bỏ hoặc incident count bằng 0 do mất tích hợp dữ liệu. Những thay đổi bất thường cần được xác minh trước khi dùng cho quyết định.

## 12. Cách thiết kế metric để giảm nguy cơ gaming

### 12.1. Bắt đầu bằng câu hỏi quyết định

Đừng bắt đầu từ dữ liệu sẵn có rồi tìm mục tiêu để gắn vào. Hãy hỏi:

- Quyết định nào cần hỗ trợ?
- Hành vi hoặc kết quả nào cần cải thiện?
- Metric có thể bị thao túng theo cách nào?
- Những tác dụng phụ nào có thể xảy ra?
- Ai kiểm soát dữ liệu và ai được đánh giá bằng metric?

### 12.2. Định nghĩa rõ tử số và mẫu số

Ví dụ, thay vì “tỷ lệ regression pass”, định nghĩa:

> Số test trong baseline bắt buộc có kết quả passed trên build được đánh giá, chia cho tổng số test áp dụng trong baseline đó. Failed, blocked, not run và inconclusive được báo riêng; test not applicable chỉ loại khỏi mẫu số khi có lý do được review.

Định nghĩa này không giải quyết mọi vấn đề, nhưng giảm khả năng loại test thất bại mà không để lại dấu vết.

### 12.3. Ghép metric chính với guardrail

Nếu mục tiêu là rút ngắn pipeline, guardrail có thể gồm số test bắt buộc, escaped defect và thời gian phát hiện. Nếu mục tiêu là tăng automation, guardrail có thể gồm flaky rate, maintenance cost và rủi ro chưa được kiểm tra.

### 12.4. Không gắn thưởng/phạt với một metric duy nhất

Không dùng pass rate, số defect hoặc coverage đơn lẻ để xếp hạng cá nhân hay nhóm. Nếu dùng metric trong đánh giá hiệu quả, cần kết hợp bối cảnh, chất lượng bằng chứng, mức độ phức tạp, kết quả nghiệp vụ và đánh giá chuyên môn.

### 12.5. Công bố giới hạn và cách diễn giải

Mỗi dashboard nên có định nghĩa, phạm vi, nguồn dữ liệu, thời điểm cập nhật và cảnh báo về mẫu số hoặc độ trễ. Người xem phải biết điều gì không thể kết luận từ metric đó.

### 12.6. Review định kỳ hành vi phát sinh

Hỏi nhóm liệu metric có khiến họ thay đổi cách ghi nhận, lựa chọn test, ưu tiên công việc hoặc báo cáo sự cố không. Nếu xuất hiện hành vi không mong muốn, sửa cách đo hoặc cách dùng metric thay vì đổ lỗi cho người thực hiện.

## 13. Ví dụ thực tế

### Ví dụ A: Pass rate tăng nhưng chất lượng hồi quy giảm

Một nhóm đặt mục tiêu pass rate trên 98%. Sau vài sprint, dashboard đạt 99,5%. Khi điều tra, nhóm phát hiện nhiều test hay thất bại đã bị quarantine và không có thời hạn khôi phục; một số test blocked cũng bị loại khỏi mẫu số.

Nhóm bổ sung báo cáo theo trạng thái, số test trong baseline, tuổi quarantine và risk coverage. Pass rate được tính trên phạm vi test áp dụng, còn blocked/not run được hiển thị riêng. Gate yêu cầu test trọng yếu có kết quả hoặc có waiver hợp lệ.

Kết quả ban đầu có thể trông kém hơn vì khoảng trống được công khai, nhưng quyết định release đáng tin hơn.

### Ví dụ B: Coverage cao nhưng lỗi nhánh nghiệp vụ vẫn lọt

Một module đạt 92% line coverage nhưng lỗi xuất hiện khi tài khoản bị khóa và giao dịch đang chờ. Test đã gọi qua phần lớn dòng mã nhưng assertion chỉ kiểm tra response không rỗng.

Nhóm xem lại branch coverage, requirement mapping và chất lượng assertion. Họ bổ sung test cho trạng thái tài khoản, chuyển trạng thái giao dịch và quyền truy cập; đồng thời dùng mutation testing trên một số logic quan trọng. Coverage vẫn được theo dõi nhưng không còn là tiêu chí chất lượng duy nhất.

### Ví dụ C: Pipeline nhanh hơn nhưng lỗi phát hiện muộn

Thời gian pipeline giảm từ 30 xuống 12 phút sau khi chuyển integration test sang nightly. PR được phản hồi nhanh hơn, nhưng lỗi contract chỉ được phát hiện vào sáng hôm sau và làm chậm release.

Nhóm phân loại test theo rủi ro, giữ contract test nhanh trong PR và chạy integration suite rộng hơn sau merge. Dashboard hiển thị cả PR feedback time, thời gian phát hiện lỗi, test coverage theo rủi ro và escaped defect. Tối ưu được đánh giá theo toàn bộ luồng thay vì chỉ thời gian CI.

### Ví dụ D: Số defect giảm do thay đổi cách ghi nhận

Sau khi thay đổi quy trình, số defect giảm 40%. Tuy nhiên, support ticket và incident liên quan tăng. Khi kiểm tra, nhiều lỗi giao diện và lỗi dữ liệu được chuyển sang loại “request” nên không còn tính vào defect report.

Nhóm thống nhất taxonomy, liên kết support ticket với defect khi phù hợp và giữ lịch sử chuyển loại. Báo cáo phân biệt defect count, incident, customer impact và nguồn phát hiện. Việc giảm defect chỉ được xem là cải thiện khi các chỉ số tác động và phát hiện cũng hỗ trợ kết luận.

### Ví dụ E: MTTR giảm nhưng sự cố tái diễn

Một nhóm giảm MTTR bằng cách đóng incident ngay khi service phục hồi. Các hành động sửa dữ liệu và loại bỏ nguyên nhân gốc vẫn đang mở. Sự cố tương tự tái diễn nhiều lần.

Nhóm định nghĩa rõ thời điểm service restored và thời điểm incident fully resolved, theo dõi recurrence và action completion. MTTR được báo cáo cùng customer impact, time to detect và số incident lặp. Việc phục hồi nhanh vẫn được ghi nhận nhưng không che giấu công việc còn lại.

### Ví dụ F: Automation rate cao nhưng chi phí bảo trì tăng

Một chương trình đặt mục tiêu tự động hóa 90% test case. Nhóm tự động hóa nhiều kịch bản giao diện dễ thay đổi, khiến test flaky và tốn thời gian sửa locator. Một số exploratory test có giá trị cao bị bỏ qua.

Nhóm thay đổi cách đo sang tỷ lệ hành vi/rủi ro phù hợp được tự động hóa, kết hợp flaky rate, maintenance effort, thời gian tiết kiệm và findings từ exploratory testing. Quyết định tự động hóa dựa trên lợi ích vòng đời chứ không phải số script.

## 14. Mẫu từ điển metric

Một metric nên có data contract hoặc từ điển để các nhóm hiểu cùng một cách:

~~~yaml
metric:
  id: REGRESSION_EXECUTION_COMPLETENESS
  name: "Regression execution completeness"
  purpose: "Cho biết bao nhiêu test áp dụng đã có kết quả thực thi hợp lệ"
  owner: "quality-engineering"

definition:
  numerator: "Số test áp dụng có kết quả thực thi hợp lệ"
  denominator: "Tổng số test áp dụng trong baseline đã chốt"
  unit: "percent"
  formula: "numerator / denominator * 100"

scope:
  suite: "mandatory-regression"
  release_candidate: "required"
  test_status_in_numerator:
    - passed
    - failed
  excluded_status:
    - not_applicable
  reported_separately:
    - blocked
    - not_run
    - deferred
    - inconclusive
    - quarantined

dimensions:
  - service
  - risk_level
  - test_level
  - release

data:
  source: "test-management-and-ci"
  refresh: "per-release-run"
  required_keys:
    - build_id
    - suite_version
    - test_id
    - run_id
    - environment_id

interpretation:
  limitations:
    - "Không đo chất lượng assertion"
    - "Không chứng minh rủi ro chưa được chọn đã được kiểm tra"
  guardrails:
    - "Báo riêng số test blocked và not_run"
    - "Theo dõi test quarantined và thời gian cách ly"
~~~

Đây là ví dụ định nghĩa một metric, không phải công thức chuẩn cho mọi tổ chức. Cần điều chỉnh tử số, mẫu số, trạng thái và phạm vi theo quy ước kiểm thử. Đặc biệt, nếu failed được tính là đã thực thi, completeness không đồng nghĩa với pass rate; hai metric cần tên và ý nghĩa riêng.

## 15. Mẫu review metric trước khi đưa vào dashboard hoặc KPI

Có thể dùng các câu hỏi sau để review một chỉ số:

| Nhóm câu hỏi | Nội dung kiểm tra |
|---|---|
| Purpose | Chỉ số hỗ trợ quyết định nào? |
| Definition | Tử số, mẫu số, đơn vị và phép tính đã rõ chưa? |
| Scope | Đối tượng nào được tính, loại trừ nào được phép? |
| Data quality | Nguồn có đầy đủ, đúng, nhất quán và kịp thời không? |
| Context | Có baseline, cửa sổ thời gian, cỡ mẫu và điều kiện so sánh không? |
| Segmentation | Tổng thể có che khuất service, severity hoặc cohort quan trọng không? |
| Gaming risk | Người bị đánh giá có thể làm con số đẹp lên mà không cải thiện kết quả không? |
| Guardrails | Metric nào phát hiện tác dụng phụ? |
| Ownership | Ai sở hữu định nghĩa, nguồn dữ liệu và hành động khi vượt ngưỡng? |
| Decision rule | Khi metric tăng/giảm thì hành động nào xảy ra? |
| Limitations | Điều gì không thể kết luận từ metric này? |
| Review | Khi nào định nghĩa hoặc ngưỡng cần được xem lại? |

## 16. Những sai lầm thường gặp khi sử dụng metric

- **Xem metric là sự thật đầy đủ:** quên rằng con số phụ thuộc định nghĩa và dữ liệu.
- **Dùng một metric làm đại diện toàn bộ chất lượng:** bỏ qua các chiều rủi ro khác.
- **Không công bố mẫu số:** tỷ lệ không thể diễn giải hoặc so sánh.
- **Thay đổi định nghĩa mà không lưu phiên bản:** xu hướng lịch sử mất ý nghĩa.
- **Chỉ xem trung bình:** che phần đuôi hoặc nhóm có kết quả xấu.
- **Không phân đoạn:** khu vực rủi ro cao bị che bởi số tổng thể.
- **Đặt target trước khi hiểu baseline:** tạo áp lực và hành vi đối phó.
- **Thưởng/phạt dựa trên một con số:** khuyến khích gaming và che giấu vấn đề.
- **Đếm hoạt động thay cho kết quả:** số test hoặc số script tăng nhưng rủi ro không giảm.
- **Bỏ qua trạng thái chưa chạy:** tạo cảm giác coverage đầy đủ.
- **Đánh đồng tương quan với nhân quả:** đưa ra kết luận sai về hiệu quả cải tiến.
- **Không kiểm tra chất lượng dữ liệu:** dashboard chính xác về mặt tính toán nhưng sai về thực tế.
- **Không có owner hành động:** metric chỉ được quan sát mà không dẫn đến cải thiện.
- **Không review tác dụng phụ:** tối ưu một mục tiêu làm xấu độ tin cậy hoặc chi phí tổng thể.

## 17. Checklist sử dụng chỉ số có trách nhiệm

### Trước khi chọn metric

- [ ] Câu hỏi hoặc quyết định cần hỗ trợ đã rõ.
- [ ] Metric liên quan trực tiếp đến mục tiêu hoặc rủi ro.
- [ ] Đã xác định metric chính và các guardrail cần thiết.
- [ ] Có baseline và điều kiện đo đủ rõ.
- [ ] Định nghĩa tử số, mẫu số, phạm vi và trạng thái loại trừ.

### Khi thu thập và trình bày

- [ ] Nguồn dữ liệu, thời điểm cập nhật và phiên bản định nghĩa được ghi.
- [ ] Build, environment, workload và cohort được xác định khi cần.
- [ ] Có số đếm, cỡ mẫu và phân bố phù hợp.
- [ ] Dữ liệu thiếu, trùng, sai nhãn hoặc đến trễ được kiểm tra.
- [ ] Kết quả được phân đoạn theo service, severity, test level hoặc release khi có ý nghĩa.
- [ ] Giới hạn diễn giải được hiển thị cùng metric.

### Khi dùng để quản trị hoặc ra quyết định

- [ ] Không dùng một metric duy nhất để đánh giá chất lượng tổng thể hoặc xếp hạng cá nhân.
- [ ] Không khuyến khích xóa test, hạ severity hoặc thay đổi taxonomy để đạt target.
- [ ] Có guardrail phát hiện tác dụng phụ.
- [ ] Có owner cho định nghĩa, dữ liệu và hành động.
- [ ] Có quy tắc xử lý khi ngưỡng bị vượt.
- [ ] Tương quan không bị diễn giải thành nhân quả nếu chưa có bằng chứng.

### Khi review và cải tiến

- [ ] Kiểm tra hành vi thực tế phát sinh từ metric.
- [ ] Rà soát định nghĩa khi sản phẩm, quy trình hoặc công cụ thay đổi.
- [ ] Đánh giá metric có còn hỗ trợ quyết định hay đã trở thành thủ tục.
- [ ] Loại bỏ hoặc thay thế metric không còn giá trị với lý do được ghi nhận.
- [ ] Kiểm tra metric cùng bằng chứng định tính và kết quả người dùng.

## Kết luận

Chỉ số giúp nhìn thấy một phần của chất lượng, nhưng có thể gây hiểu lầm khi bị tối ưu sai hoặc thiếu ngữ cảnh. Cần hiểu cơ chế Goodhart, kiểm tra định nghĩa và mẫu số, phân đoạn theo rủi ro, so sánh trên điều kiện tương đương, đánh giá chất lượng dữ liệu và kết hợp metric chính với guardrail. Tỷ lệ pass, coverage, defect count, pipeline duration, automation rate hay MTTR đều hữu ích khi biết chúng đo gì và không đo gì. Khi có owner, giới hạn diễn giải và hành động rõ ràng, đo lường hỗ trợ cải tiến chất lượng thay vì khuyến khích làm đẹp dashboard.
