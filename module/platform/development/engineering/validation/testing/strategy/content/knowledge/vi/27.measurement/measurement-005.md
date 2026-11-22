# Đánh giá lỗi được phát hiện sớm và lỗi lọt ra production

Trong chiến lược kiểm thử xác thực (VALIDATION_TESTING_STRATEGY), số lượng test đã chạy hoặc tỷ lệ pass không cho biết đầy đủ khả năng phát hiện lỗi của quy trình. Một hệ thống có thể đạt tỷ lệ pass cao nhưng vẫn để nhiều lỗi quan trọng đến tay người dùng. Ngược lại, số lỗi được tìm thấy trong giai đoạn phát triển có thể tăng vì nhóm kiểm thử tốt hơn, phạm vi rộng hơn hoặc sản phẩm thay đổi nhiều hơn.

Để đánh giá chất lượng phát hiện lỗi, cần xem xét **lỗi được tìm thấy ở giai đoạn nào, lỗi nào chỉ được phát hiện sau khi triển khai, mức độ ảnh hưởng của chúng và thời gian cần để phát hiện, xử lý**. Việc đo lường phải liên kết lỗi với release hoặc thay đổi gây ra, phân biệt lỗi mới với lỗi đã biết, loại bỏ bản ghi trùng và chuẩn hóa theo quy mô hoặc mức độ sử dụng khi so sánh.

Bài học này trình bày cách xác định lỗi phát hiện sớm và lỗi lọt ra production, thiết kế chỉ số theo vòng đời, thu thập và phân loại dữ liệu, đọc kết quả theo ngữ cảnh, xây dựng ví dụ tính toán và chuyển số liệu thành hành động cải tiến.

## 1. Hiểu lỗi được phát hiện sớm và lỗi lọt ra production

### 1.1. Lỗi được phát hiện sớm là gì?

Lỗi được phát hiện sớm là lỗi được xác nhận trước khi phiên bản hoặc thay đổi liên quan đến người dùng production. Tùy quy trình, lỗi có thể được tìm thấy ở:

- Phân tích yêu cầu hoặc review thiết kế.
- Review mã nguồn.
- Unit test hoặc component test.
- Contract test và integration test.
- System test hoặc E2E test.
- Kiểm thử chấp nhận người dùng (UAT).
- Staging hoặc môi trường tiền production.

Phát hiện sớm giúp giảm chi phí sửa lỗi và hạn chế tác động đến người dùng, nhưng chỉ có ý nghĩa khi lỗi được ghi nhận, phân loại và xử lý đúng. Một cảnh báo scanner chưa được xác minh không nên được tính như một defect đã xác nhận. Một test thất bại do môi trường cũng không tự động là lỗi sản phẩm.

### 1.2. Lỗi lọt ra production là gì?

Lỗi lọt ra production (production escape hoặc escaped defect) là lỗi của sản phẩm được phát hiện lần đầu sau khi phiên bản liên quan đã được triển khai vào môi trường production. Lỗi có thể được phát hiện bởi:

- Người dùng hoặc khách hàng.
- Hệ thống giám sát và cảnh báo.
- Bộ phận hỗ trợ hoặc vận hành.
- Đối soát dữ liệu hoặc giao dịch.
- Kiểm tra production có kiểm soát.
- Điều tra sự cố hoặc phân tích sau triển khai.

Không phải mọi sự cố production đều là defect của phiên bản vừa phát hành. Sự cố có thể do hạ tầng, cấu hình, thao tác vận hành, nhà cung cấp hoặc một lỗi đã tồn tại từ trước. Cần điều tra và xác định quan hệ với release trước khi đưa vào chỉ số lỗi lọt.

### 1.3. Phân biệt giai đoạn phát sinh và giai đoạn phát hiện

Hai mốc này thường khác nhau:

- **Giai đoạn phát sinh (introduction phase):** khi thay đổi tạo ra lỗi, chẳng hạn lúc viết mã, sửa schema hoặc thay đổi cấu hình.
- **Giai đoạn phát hiện (detection phase):** khi có bằng chứng đủ để xác nhận lỗi.

Ví dụ, một lỗi phân quyền được đưa vào ở commit đầu tiên, không bị phát hiện trong unit và integration test, rồi được khách hàng báo cáo sau hai tuần production. Giai đoạn phát sinh là phát triển; giai đoạn phát hiện là production.

Không nên kết luận rằng lỗi phát sinh ở production chỉ vì được phát hiện ở đó. Việc phân biệt hai mốc giúp xác định cơ hội kiểm soát nào đã bỏ lỡ và nhóm nào có thể cải thiện quy trình.

### 1.4. Phân biệt lỗi mới phát hiện với lỗi đã biết nhưng được phát hành

Một defect được phát hiện ở staging nhưng chưa sửa trước release là lỗi đã biết được chấp nhận hoặc hoãn xử lý. Nó không phải lỗi “không được phát hiện” ở production, dù người dùng có thể gặp tác động sau triển khai.

Nên theo dõi riêng:

| Nhóm | Ý nghĩa | Ví dụ |
|---|---|---|
| Phát hiện và sửa trước release | Lỗi được tìm thấy trước production và bản sửa được xác minh. | Unit test phát hiện lỗi làm tròn; developer sửa và regression test đạt. |
| Phát hiện trước nhưng phát hành khi còn mở | Lỗi đã biết, có thể có waiver hoặc quyết định chấp nhận rủi ro. | Lỗi hiển thị trên một browser được chấp nhận tạm thời. |
| Phát hiện lần đầu sau release | Lỗi chưa được xác nhận trước production và được phát hiện sau triển khai. | Người dùng báo cáo không thể hoàn tất thanh toán. |
| Sự cố không phải defect sản phẩm | Vấn đề do hạ tầng, cấu hình hoặc yếu tố bên ngoài, không được quy cho lỗi sản phẩm nếu điều tra xác nhận. | Nhà cung cấp production ngừng hoạt động ngoài phạm vi kiểm soát của ứng dụng. |

Phân nhóm này tránh việc số liệu lỗi lọt bị phóng đại hoặc che giấu do cách phân loại không nhất quán.

## 2. Xây dựng mô hình phân loại lỗi theo vòng đời

### 2.1. Xác định các giai đoạn phát hiện thống nhất

Tổ chức cần một danh mục giai đoạn đủ ổn định để so sánh theo thời gian. Ví dụ:

| Mã giai đoạn | Giai đoạn | Ví dụ bằng chứng |
|---|---|---|
| REQ | Phân tích yêu cầu | Review phát hiện quy tắc nghiệp vụ mâu thuẫn. |
| DESIGN | Thiết kế/kiến trúc | Review phát hiện thiếu kiểm soát quyền ở ranh giới service. |
| REVIEW | Review mã nguồn | Reviewer phát hiện điều kiện so sánh sai. |
| UNIT | Unit/component test | Test logic hoặc giá trị biên thất bại. |
| INTEGRATION | Contract/integration test | Service không xử lý đúng schema hoặc transaction. |
| SYSTEM | System/E2E test | Luồng người dùng xuyên hệ thống không hoàn tất. |
| UAT | Kiểm thử chấp nhận | Đại diện nghiệp vụ phát hiện hành vi không đáp ứng nhu cầu. |
| STAGING | Tiền production | Kiểm tra ứng viên release phát hiện lỗi. |
| PROD | Production | Người dùng, monitoring hoặc vận hành phát hiện lỗi. |

Danh mục có thể gộp hoặc tách theo quy trình thực tế, nhưng không nên đổi định nghĩa giữa các kỳ báo cáo mà không có ánh xạ chuyển đổi.

### 2.2. Ghi nhận giai đoạn phát sinh riêng

Khi điều tra lỗi, có thể ghi giai đoạn phát sinh ở mức mà bằng chứng hỗ trợ:

- Yêu cầu hoặc quy tắc nghiệp vụ.
- Thiết kế hoặc kiến trúc.
- Code hoặc cấu hình.
- Tích hợp hoặc migration.
- Triển khai hoặc vận hành.
- Chưa xác định.

Không nên ép người điều tra chọn một nguyên nhân nếu chưa đủ dữ liệu. Trạng thái UNKNOWN hoặc UNDER_INVESTIGATION hữu ích hơn một nhãn đoán mò.

### 2.3. Phân loại theo mức độ nghiêm trọng

Số lượng lỗi không phản ánh đầy đủ mức độ tác động. Nên ghi severity theo chính sách chung, dựa trên:

- Mức ảnh hưởng đến người dùng.
- Mất mát hoặc sai lệch dữ liệu.
- Tác động tài chính.
- Rủi ro bảo mật và quyền riêng tư.
- Mức gián đoạn dịch vụ.
- Phạm vi người dùng, tenant hoặc giao dịch.
- Khả năng khôi phục và phát hiện.

Ví dụ phân loại:

| Mức | Mô tả định hướng |
|---|---|
| Critical | Mất dữ liệu nghiêm trọng, truy cập trái phép diện rộng, giao dịch sai nghiêm trọng hoặc dịch vụ cốt lõi ngừng hoạt động. |
| High | Chức năng quan trọng bị ảnh hưởng lớn, dữ liệu hoặc giao dịch có thể sai, cần workaround đáng kể. |
| Medium | Một phần chức năng bị ảnh hưởng, có cách thay thế hoặc phạm vi giới hạn. |
| Low | Tác động nhỏ, chủ yếu về hiển thị hoặc tiện ích, không làm sai dữ liệu cốt lõi. |

Severity cần được đánh giá theo tác động thực tế, không theo độ khó sửa hoặc số dòng mã thay đổi.

### 2.4. Xác định defect duy nhất và liên kết sự cố

Một lỗi có thể tạo ra nhiều ticket từ người dùng hoặc nhiều alert. Nếu tính mỗi ticket như một defect, số liệu sẽ bị đếm trùng. Cần quy định cách gộp theo nguyên nhân gốc hoặc hành vi lỗi.

Mỗi defect nên có:

- Defect ID duy nhất.
- Release hoặc cohort liên quan.
- Thành phần và chức năng bị ảnh hưởng.
- Giai đoạn phát sinh và phát hiện.
- Severity và mức ưu tiên.
- Thời điểm phát hiện, xác nhận, sửa và triển khai bản sửa.
- Incident, customer ticket hoặc alert liên quan.
- Root cause nếu đã xác định.
- Trạng thái và bằng chứng.

Nếu một lỗi đã sửa nhưng tái xuất hiện do regression, hãy ghi nhận lần tái diễn như một sự kiện riêng và liên kết với defect gốc. Chính sách đếm cần nhất quán để vừa tránh trùng lặp vừa không che giấu việc lỗi tái diễn.

## 3. Xác định cohort để đo lường công bằng

### 3.1. Cohort là gì?

Cohort là nhóm thay đổi, tính năng hoặc release được theo dõi như một đơn vị. Để đánh giá lỗi phát hiện sớm và lỗi lọt ra production, cần xác định các defect nào thuộc cùng một cohort.

Có thể chọn:

- Một release hoặc phiên bản triển khai.
- Một nhóm thay đổi được phát hành cùng nhau.
- Một tính năng hoặc epic.
- Một service trong một khoảng thời gian.
- Một nhóm commit hoặc deployment có quan hệ rõ.

Ví dụ, tất cả defect liên quan đến release R-42 được theo dõi trong cửa sổ 30 ngày sau khi release triển khai. Cần ghi rõ cửa sổ và quy tắc attribution.

### 3.2. Gắn defect với release gây ra lỗi

Không nên quy mọi defect phát hiện trong tuần sau release cho release mới nhất. Lỗi có thể tồn tại từ phiên bản cũ hoặc phát sinh từ cấu hình và dữ liệu.

Cần dùng bằng chứng như:

- Commit hoặc change ID gây ra hành vi.
- Phiên bản đầu tiên có lỗi.
- Lịch sử deployment.
- Log, trace và dữ liệu tái hiện.
- Phân tích root cause.
- Xác nhận từ owner của thành phần.

Nếu chưa xác định được release, ghi trạng thái chưa rõ và không tự động phân bổ cho cohort gần nhất.

### 3.3. Chọn cửa sổ quan sát sau release

Defect có thể chỉ xuất hiện khi dữ liệu tích lũy, tải tăng hoặc một điều kiện hiếm xảy ra. Cửa sổ 24 giờ có thể phù hợp với một số luồng, nhưng quá ngắn cho lỗi chỉ xuất hiện cuối tháng hoặc sau một chu kỳ thanh toán.

Cần chọn cửa sổ theo đặc tính sản phẩm, ví dụ:

- 7 ngày cho lỗi thường xuất hiện ngay sau triển khai.
- 30 ngày cho một kỳ vận hành thông thường.
- 60 hoặc 90 ngày cho luồng có chu kỳ dài.
- Một chu kỳ nghiệp vụ đầy đủ cho đối soát, thanh toán hoặc báo cáo định kỳ.

Các con số trên chỉ là ví dụ. Cần dùng cùng cửa sổ khi so sánh cohort tương đương và ghi rõ cohort nào chưa đủ thời gian quan sát.

### 3.4. Xử lý defect phát hiện muộn

Nếu lỗi của release A chỉ được phát hiện trong thời gian release B đang hoạt động, cần quy về cohort A khi có bằng chứng. Nếu không thể xác định, ghi attribution unknown và báo cáo riêng.

Không nên đóng cohort quá sớm rồi bỏ qua lỗi phát hiện muộn. Báo cáo có thể hiển thị số liệu tạm thời và cập nhật khi có thêm defect được xác nhận.

## 4. Các chỉ số phát hiện lỗi sớm và lỗi lọt

### 4.1. Phân bố defect theo giai đoạn phát hiện

Đây là số lượng hoặc tỷ trọng defect được xác nhận lần đầu ở từng giai đoạn. Nó cho biết nơi quy trình đang phát hiện lỗi.

Có thể trình bày bằng bảng:

| Giai đoạn phát hiện | Số defect | Tỷ trọng |
|---|---:|---:|
| Yêu cầu/thiết kế/review | 12 | 15% |
| Unit/component | 28 | 35% |
| Integration/API | 20 | 25% |
| System/UAT/staging | 12 | 15% |
| Production | 8 | 10% |
| **Tổng** | **80** | **100%** |

Tỷ trọng cần được tính trên cùng một cohort và cùng quy tắc đếm. Nếu thay đổi số giai đoạn hoặc phạm vi, cần chú thích để người đọc hiểu.

### 4.2. Tỷ lệ phát hiện trước production

Có thể định nghĩa tỷ lệ phát hiện trước production:

\[
\text{Pre-production Detection Rate}
=
\frac{\text{Defect lần đầu phát hiện trước production}}
{\text{Tổng defect duy nhất của cohort}}
\times 100\%
\]

Chỉ số này phản ánh phần defect đã được phát hiện trước khi phiên bản đến production. Nó không tự chứng minh mọi lỗi đã được sửa hoặc release an toàn.

### 4.3. Tỷ lệ lỗi lọt ra production

Một định nghĩa thường dùng:

\[
\text{Production Escape Rate}
=
\frac{\text{Defect lần đầu phát hiện ở production}}
{\text{Tổng defect duy nhất của cohort}}
\times 100\%
\]

Khi các nhóm phát hiện trước production và production loại trừ lẫn nhau, có cùng cohort và cùng cửa sổ quan sát, hai tỷ lệ trên cộng lại bằng 100%.

Cần ghi rõ mẫu số. Nếu chỉ tính defect đã xác nhận, không tính alert chưa xác minh; nếu một lỗi production chưa thể attribution, phải báo riêng thay vì lặng lẽ bỏ qua.

### 4.4. Defect Removal Efficiency (DRE)

DRE đo tỷ lệ defect được phát hiện trước production trong tổng số defect được xác nhận cho cohort:

\[
\text{DRE}
=
\frac{D_{\text{pre}}}
{D_{\text{pre}} + D_{\text{prod}}}
\times 100\%
\]

Trong đó:

- \(D_{\text{pre}}\): defect duy nhất được phát hiện lần đầu trước production.
- \(D_{\text{prod}}\): defect duy nhất được phát hiện lần đầu sau khi triển khai production trong cửa sổ quan sát.

Cách định nghĩa này đo hiệu quả phát hiện trước production. Nó không trực tiếp đo tỷ lệ defect đã được sửa và xác minh trước release. Nếu cần đánh giá việc xử lý, phải theo dõi thêm trạng thái đóng và xác minh bản sửa.

Một số tổ chức dùng thuật ngữ DRE hoặc defect leakage theo định nghĩa khác. Khi triển khai, cần công bố công thức chính thức và giữ nhất quán để tránh so sánh sai.

### 4.5. Tỷ lệ defect phát hiện sớm đã được xử lý trước release

Để biết lỗi tìm được sớm có thực sự được xử lý, có thể đo:

\[
\text{Pre-release Closure Rate}
=
\frac{\text{Defect phát hiện trước release đã sửa và retest đạt}}
{\text{Defect phát hiện trước release}}
\times 100\%
\]

Defect được waiver hoặc phát hành khi còn mở không được tính là đã đóng. Chỉ tính khi có bằng chứng sửa và kiểm tra lại.

### 4.6. Tỷ lệ lỗi đã biết được phát hành

Theo dõi riêng số defect đã được phát hiện trước release nhưng vẫn mở tại thời điểm triển khai:

\[
\text{Known-open Release Rate}
=
\frac{\text{Defect đã biết còn mở khi release}}
{\text{Defect phát hiện trước release}}
\times 100\%
\]

Chỉ số này giúp thấy quyết định phát hành với lỗi đã biết. Nên phân tách theo severity và ghi liên kết waiver nếu có.

### 4.7. Tỷ lệ lỗi lọt có trọng số severity

Hai release có cùng số defect production nhưng mức ảnh hưởng có thể khác nhau. Có thể dùng trọng số severity đã thống nhất:

\[
\text{Weighted Escape Score}
=
\sum_{i=1}^{n} w(s_i)
\]

Trong đó \(w(s_i)\) là trọng số được quy định cho severity của defect thứ \(i\). Ví dụ tổ chức có thể chọn Critical = 10, High = 5, Medium = 2, Low = 1.

Có thể tính tỷ lệ có trọng số:

\[
\text{Weighted Escape Rate}
=
\frac{\text{Tổng trọng số defect production}}
{\text{Tổng trọng số defect của cohort}}
\times 100\%
\]

Trọng số là quy ước quản trị, không phải thước đo khách quan tuyệt đối. Cần công bố cách gán, không thay đổi tùy tiện giữa các kỳ và luôn xem số defect Critical/High riêng.

### 4.8. Mật độ lỗi lọt theo mức độ sử dụng

Số defect production tuyệt đối có thể tăng khi số người dùng hoặc giao dịch tăng. Để so sánh sản phẩm có quy mô khác nhau, có thể chuẩn hóa theo một mẫu số phù hợp:

- Defect production trên 10.000 giao dịch.
- Defect production trên 1.000 người dùng hoạt động.
- Defect production trên một số lượng request.
- Defect production trên một đơn vị quy mô thay đổi đã thống nhất.

Ví dụ:

\[
\text{Escaped Defects per 10,000 Transactions}
=
\frac{\text{Defect production được xác nhận}}
{\text{Số giao dịch trong cùng cửa sổ}}
\times 10,000
\]

Mẫu số phải phản ánh cơ hội xuất hiện lỗi. Với lỗi chỉ ảnh hưởng chức năng xuất báo cáo, số giao dịch thanh toán có thể không phải mẫu số phù hợp. Hãy chọn exposure gắn với hành vi có nguy cơ.

### 4.9. Thời gian phát hiện và xử lý

Ngoài tỷ lệ, cần đo thời gian:

- **Time to Detect (TTD):** từ thời điểm thay đổi có lỗi được đưa vào môi trường liên quan đến khi lỗi được phát hiện.
- **Time to Confirm:** từ phát hiện ban đầu đến xác nhận defect.
- **Time to Fix:** từ xác nhận đến khi bản sửa sẵn sàng.
- **Time to Verify:** từ bản sửa đến khi kiểm tra lại đạt.
- **Time to Mitigate/Restore:** thời gian giảm tác động hoặc phục hồi dịch vụ trong production.

Với lỗi production, có thể đo thời gian từ lúc bắt đầu ảnh hưởng đến lúc monitoring hoặc người dùng phát hiện. Cần phân biệt thời điểm phát sinh, thời điểm bắt đầu ảnh hưởng và thời điểm được phát hiện; không phải lúc nào cũng biết chính xác cả ba.

## 5. Thu thập dữ liệu đáng tin cậy

### 5.1. Nguồn dữ liệu

Có thể kết hợp:

- Issue tracker hoặc defect management.
- Test management và CI/CD result.
- Deployment record và release metadata.
- Incident management.
- Customer support ticket.
- Monitoring, alert, log và trace.
- Root cause analysis.
- Security finding và vulnerability management.
- Change/release approval record.

Không nên dùng một nguồn duy nhất nếu nguồn đó không ghi giai đoạn phát hiện hoặc release attribution.

### 5.2. Trường dữ liệu tối thiểu

Mỗi defect nên có các trường:

| Trường | Mục đích |
|---|---|
| Defect ID | Định danh duy nhất, tránh đếm trùng. |
| Summary và affected behavior | Mô tả hành vi sai. |
| Product/module/service | Xác định phạm vi. |
| Release/cohort | Liên kết với phiên bản gây ra lỗi. |
| Introduction phase | Giai đoạn phát sinh nếu biết. |
| Detection phase | Giai đoạn phát hiện lần đầu. |
| First detected at | Thời điểm phát hiện đầu tiên. |
| Confirmed at | Thời điểm xác nhận defect. |
| Severity/priority | Đánh giá tác động và mức ưu tiên. |
| Status at release | Đã đóng, còn mở, waived hoặc chưa rõ. |
| Fix version | Phiên bản chứa bản sửa. |
| Verified at | Thời điểm retest xác nhận. |
| Customer/transaction impact | Phạm vi ảnh hưởng thực tế nếu có. |
| Root cause | Nguyên nhân sau điều tra, có thể chưa xác định. |
| Evidence links | Test run, incident, log, trace hoặc ticket liên quan. |

### 5.3. Quy tắc ghi nhận giai đoạn phát hiện

Dùng giai đoạn đầu tiên có bằng chứng đủ để xác nhận defect. Nếu một cảnh báo được tạo ở unit test nhưng chỉ xác nhận là lỗi sản phẩm sau khi điều tra, cần quy định liệu detection phase là thời điểm cảnh báo hay thời điểm xác nhận.

Một quy tắc thực tế là lưu cả hai thời điểm:

- First observed: lần đầu có tín hiệu.
- Confirmed: lần đầu xác nhận lỗi sản phẩm.

Báo cáo chính có thể dùng thời điểm xác nhận để tránh tính false positive, trong khi chỉ số thời gian phát hiện có thể theo dõi từ first observed để đánh giá khả năng cảnh báo. Cần thống nhất và ghi rõ cách dùng.

### 5.4. Xử lý duplicate và false positive

Trước khi đưa vào số liệu:

1. Gộp các ticket cùng một nguyên nhân gốc theo quy tắc đã thống nhất.
2. Giữ liên kết đến mọi incident hoặc customer report.
3. Loại false positive đã được xác nhận, nhưng lưu số lượng riêng nếu cần đánh giá chất lượng công cụ.
4. Không xóa defect vì nó khó tái hiện; ghi trạng thái chưa xác định và bằng chứng.
5. Tách lỗi sản phẩm khỏi lỗi hạ tầng hoặc thao tác vận hành nếu điều tra đủ căn cứ.

Không gộp hai lỗi chỉ vì cùng thông báo nếu nguyên nhân hoặc hành vi bị ảnh hưởng khác nhau.

### 5.5. Kiểm soát chất lượng dữ liệu

Rà soát định kỳ:

- Defect có release/cohort hay chưa?
- Detection phase có hợp lệ?
- Severity có theo rubric chung?
- Các ticket trùng có được liên kết?
- Thời điểm có nhất quán timezone?
- Defect production có được attribution?
- Trạng thái đóng có bằng chứng retest?
- Waiver còn hiệu lực có được ghi nhận riêng?
- Cohort đã đủ cửa sổ quan sát chưa?

Nếu dữ liệu thiếu, hiển thị phần unknown hoặc coverage của dữ liệu. Không tự điền bằng suy đoán chỉ để hoàn thiện dashboard.

## 6. Cách đọc và diễn giải kết quả

### 6.1. DRE cao không tự động có nghĩa chất lượng cao

DRE cao cho biết phần lớn defect đã biết được phát hiện trước production. Nhưng chỉ số có thể tăng vì:

- Phạm vi kiểm thử trước release tốt hơn.
- Sản phẩm có ít thay đổi rủi ro hơn.
- Defect production chưa được báo cáo hoặc chưa được attribution.
- Cửa sổ quan sát quá ngắn.
- Nhóm ghi nhận defect trước release đầy đủ hơn production.
- Nhiều lỗi nhỏ được tìm thấy sớm nhưng lỗi nghiêm trọng vẫn lọt.

Do đó, cần đọc DRE cùng severity, tác động khách hàng, coverage, known-open defects và thời gian quan sát.

### 6.2. Số lỗi phát hiện trước release tăng có thể là tín hiệu tốt

Số defect trước production tăng không nhất thiết cho thấy chất lượng phát triển giảm. Nó có thể phản ánh:

- Kiểm thử được mở rộng.
- Review phát hiện nhiều vấn đề hơn.
- Tính năng phức tạp hơn.
- Nhóm ghi nhận lỗi nhất quán hơn.
- Có thêm công cụ quan sát hoặc scanning.

Cần xem tỷ lệ lỗi lọt, mức độ nghiêm trọng và xu hướng theo cohort. Nếu lỗi trước release tăng nhưng lỗi production nghiêm trọng giảm, đó có thể là dấu hiệu kiểm soát sớm hiệu quả hơn.

### 6.3. Ít lỗi production không đồng nghĩa ít rủi ro

Có thể không có defect được báo cáo vì:

- Người dùng chưa thực hiện hành vi bị ảnh hưởng.
- Monitoring không quan sát được lỗi.
- Người dùng không báo cáo.
- Tính năng ít được sử dụng.
- Cửa sổ quan sát chưa đủ dài.
- Defect chưa được xác định hoặc attribution.

Kết hợp dữ liệu support, monitoring, giao dịch, phản hồi người dùng và kiểm tra chủ động để hiểu mức độ quan sát.

### 6.4. So sánh theo xu hướng và cohort tương đương

So sánh các release cần xét:

- Quy mô và độ phức tạp thay đổi.
- Số người dùng và volume giao dịch.
- Số service hoặc thành phần thay đổi.
- Mức độ sử dụng tính năng.
- Phạm vi test và môi trường.
- Cửa sổ quan sát.
- Quy tắc severity và defect deduplication.
- Mức độ đầy đủ của dữ liệu.

Không nên xếp hạng nhóm phát triển chỉ bằng số lỗi production tuyệt đối. Sản phẩm có lưu lượng và phạm vi lớn hơn có nhiều cơ hội quan sát defect hơn.

### 6.5. Xem xét riêng lỗi nghiêm trọng

Một defect Critical có thể quan trọng hơn hàng chục defect Low. Báo cáo nên có:

- Số defect Critical/High phát hiện trước production.
- Số defect Critical/High lọt ra production.
- Tác động khách hàng hoặc dữ liệu.
- Thời gian phát hiện và khắc phục.
- Nguyên nhân và kiểm soát bị bỏ lỡ.
- Trạng thái hành động phòng ngừa.

Không để một tỷ lệ tổng hợp tốt che khuất một lỗi nghiêm trọng.

## 7. Ví dụ tính toán theo một release

Giả sử release R-42 có cửa sổ quan sát 30 ngày. Sau khi loại duplicate và xác nhận attribution, nhóm ghi nhận:

- 72 defect được phát hiện trước production.
- 8 defect được phát hiện lần đầu ở production.
- Trong 72 defect trước release, 66 đã sửa và retest đạt trước khi triển khai; 6 vẫn mở và được chấp nhận có điều kiện.
- Trong 8 defect production: 1 High, 3 Medium và 4 Low.
- Tổng giao dịch trong cửa sổ quan sát là 120.000.

### 7.1. Tính tỷ lệ phát hiện trước production

Tổng defect duy nhất trong cohort:

\[
D_{\text{total}} = 72 + 8 = 80
\]

Tỷ lệ phát hiện trước production:

\[
\frac{72}{80} \times 100\% = 90\%
\]

### 7.2. Tính tỷ lệ lỗi lọt ra production và DRE

\[
\text{Production Escape Rate}
=
\frac{8}{80} \times 100\% = 10\%
\]

Theo định nghĩa đã nêu:

\[
\text{DRE}
=
\frac{72}{72+8} \times 100\% = 90\%
\]

DRE và tỷ lệ lỗi lọt cộng lại bằng 100% trong ví dụ vì hai nhóm được định nghĩa loại trừ lẫn nhau và dữ liệu cohort đầy đủ.

### 7.3. Tính tỷ lệ đóng lỗi trước release

\[
\text{Pre-release Closure Rate}
=
\frac{66}{72} \times 100\% \approx 91.7\%
\]

Sáu defect còn mở cần được theo dõi riêng. Chúng không được tính là đã sửa chỉ vì có waiver.

### 7.4. Tính mật độ lỗi lọt

\[
\frac{8}{120,000} \times 10,000
\approx 0.67
\]

Có khoảng 0,67 defect production được xác nhận trên mỗi 10.000 giao dịch trong cửa sổ quan sát. Chỉ số này chỉ phù hợp để so sánh nếu các cohort có exposure và quy tắc attribution tương tự.

### 7.5. Đọc kết quả và hành động

Không nên kết luận release tốt chỉ vì DRE đạt 90%. Nhóm cần xem:

- Defect High production có ảnh hưởng giao dịch hoặc dữ liệu không?
- Sáu defect đã biết còn mở có được chấp nhận đúng thẩm quyền?
- Lỗi production tập trung ở một tầng, service hoặc loại dữ liệu nào?
- Monitoring phát hiện trước khách hàng hay sau báo cáo của khách hàng?
- Có regression test mới nào cần bổ sung?
- Cửa sổ 30 ngày đã đủ cho các chu kỳ nghiệp vụ chưa?

Nếu defect High xuất phát từ callback thanh toán không được kiểm tra với dữ liệu lặp, hành động có thể là bổ sung integration test idempotency, cải thiện contract test và cảnh báo trạng thái giao dịch bất thường.

## 8. Chuyển số liệu thành cải tiến quy trình

### 8.1. Phân tích mẫu lỗi theo giai đoạn

Nếu nhiều lỗi được phát hiện ở system test nhưng ít lỗi được phát hiện ở unit/integration, hãy xem:

- Quy tắc nghiệp vụ có nằm trong tầng kiểm thử phù hợp?
- Module có phụ thuộc quá chặt khiến test cục bộ khó viết?
- Contract giữa service có được kiểm tra?
- Test data có bao phủ trạng thái và giá trị biên?
- Review có tập trung vào logic rủi ro?
- Có đủ khả năng quan sát để chẩn đoán?

Mục tiêu không phải chuyển mọi lỗi xuống unit test. Một số lỗi chỉ xuất hiện khi các thành phần phối hợp và cần được phát hiện ở tầng tích hợp hoặc hệ thống.

### 8.2. Phân tích lỗi lọt theo loại rủi ro

Nhóm defect production theo:

- Quyền và bảo mật.
- Tính toàn vẹn dữ liệu.
- Tính toán hoặc giao dịch.
- Hiệu năng và tải.
- Tích hợp bên ngoài.
- Giao diện và khả năng sử dụng.
- Cấu hình và triển khai.
- Bất đồng bộ, retry và concurrency.

Nếu lỗi tập trung ở một loại, điều chỉnh chiến lược tương ứng. Ví dụ:

| Mẫu lỗi | Hành động cải tiến có thể phù hợp |
|---|---|
| Truy cập chéo tài khoản | Thêm test ma trận role/object ownership ở API và review policy. |
| Sai số tiền hoặc làm tròn | Bổ sung test biên, property-based test và đối soát tổng tiền. |
| Callback lặp hoặc sai thứ tự | Tăng integration test về idempotency, retry và trạng thái cuối. |
| Lỗi chỉ xuất hiện trên browser cụ thể | Mở rộng ma trận browser và kiểm tra UI có mục tiêu. |
| Timeout dưới tải | Bổ sung performance test, kiểm tra quota và alert latency. |
| Migration làm mất dữ liệu | Thêm test nâng cấp, rollback, backup và đối soát dữ liệu. |
| Cấu hình production khác staging | Cải thiện config validation, drift detection và post-deploy smoke. |

### 8.3. Cập nhật test strategy và test suite

Mỗi defect quan trọng nên được xem xét để xác định:

- Có regression test nào cần thêm?
- Test nên đặt ở unit, API, integration hay E2E?
- Có cần thêm dữ liệu hoặc trạng thái mới?
- Có cần thay đổi readiness hoặc môi trường?
- Có cần bổ sung monitoring hoặc alert?
- Có cần sửa tiêu chí hoàn tất hoặc risk register?

Không phải mọi defect đều cần thêm một E2E test. Chọn tầng kiểm tra có thể tái hiện nguyên nhân với chi phí và độ ổn định phù hợp.

### 8.4. Đo hiệu quả sau hành động

Sau khi thay đổi quy trình, theo dõi các cohort tiếp theo để xem:

- Loại lỗi mục tiêu có giảm không?
- Lỗi có được phát hiện ở giai đoạn sớm hơn không?
- Có tạo ra false positive hoặc flaky test mới không?
- Thời gian phản hồi có tăng quá mức không?
- Chi phí test có phù hợp với mức giảm rủi ro không?
- Tác động khách hàng có giảm không?

Không kết luận cải tiến thành công chỉ vì một release không có lỗi. Cần đủ dữ liệu qua nhiều chu kỳ hoặc có bằng chứng trực tiếp về kiểm soát mới.

## 9. Dashboard và báo cáo

### 9.1. Dashboard nên trả lời câu hỏi quản trị

Một dashboard hữu ích có thể hiển thị:

- Defect theo giai đoạn phát hiện.
- Production escape rate và DRE theo cohort.
- Defect production theo severity.
- Known-open defects tại thời điểm release.
- Defect density theo exposure phù hợp.
- Thời gian phát hiện và khắc phục.
- Nguồn phát hiện: test, monitoring, support hoặc người dùng.
- Phạm vi dữ liệu chưa đủ hoặc chưa attribution.
- Hành động cải tiến và trạng thái.

Không nên hiển thị một con số tổng duy nhất mà không có drill-down theo release, service, severity và detection phase.

### 9.2. Báo cáo cần nêu định nghĩa

Mỗi báo cáo nên công bố:

- Công thức và mẫu số.
- Cách xác định defect duy nhất.
- Cửa sổ quan sát.
- Quy tắc attribution release.
- Rubric severity.
- Nguồn dữ liệu.
- Số defect chưa phân loại hoặc chưa xác nhận.
- Phần bị loại trừ và lý do.
- Ngày cập nhật dữ liệu.

Nếu định nghĩa thay đổi, cần ghi ngày hiệu lực và không so sánh trực tiếp số liệu trước/sau khi chưa điều chỉnh.

### 9.3. Tránh dùng chỉ số để quy trách nhiệm cá nhân

Các chỉ số phản ánh hệ thống quy trình, độ phức tạp, môi trường, phạm vi và cơ hội phát hiện. Dùng số lỗi lọt để xếp hạng cá nhân có thể khiến mọi người ngại báo cáo, hạ severity hoặc tạo nhiều test ít giá trị.

Nên dùng dữ liệu để tìm lỗ hổng trong kiểm soát, ưu tiên đầu tư và cải thiện phối hợp. Đánh giá trách nhiệm cá nhân cần bối cảnh và quy trình riêng, không suy ra từ một tỷ lệ đơn lẻ.

## 10. Những giới hạn và sai lầm thường gặp

- **Đếm ticket thay vì defect duy nhất:** nhiều báo cáo cho cùng lỗi làm số liệu bị phóng đại.
- **Quy mọi lỗi sau release cho release mới nhất:** attribution sai dẫn đến kết luận sai.
- **Không có cửa sổ quan sát:** cohort mới và cũ không thể so sánh công bằng.
- **Coi mọi lỗi production là defect sản phẩm:** bỏ qua hạ tầng, cấu hình và yếu tố bên ngoài.
- **Coi DRE cao là chất lượng tốt tuyệt đối:** chỉ số không phản ánh đầy đủ severity và mức độ sử dụng.
- **Chỉ xem số lượng, không xem tác động:** một lỗi Critical có thể quan trọng hơn nhiều lỗi Low.
- **Bỏ qua lỗi đã biết được phát hành:** waiver và known-open defects cần được báo cáo riêng.
- **Không đo mức độ sử dụng:** số lỗi tuyệt đối có thể tăng theo lượng giao dịch.
- **Không ghi dữ liệu chưa phân loại:** unknown bị ẩn làm dashboard có vẻ chính xác hơn thực tế.
- **Thay đổi công thức giữa các kỳ:** xu hướng mất ý nghĩa.
- **Dùng tỷ lệ để phạt nhóm:** tạo động cơ che giấu lỗi hoặc tránh ghi nhận.
- **Không chuyển số liệu thành hành động:** đo lường trở thành báo cáo mà không cải thiện kiểm soát.

## 11. Mẫu dữ liệu và quy trình đánh giá

### 11.1. Mẫu ghi nhận defect

~~~text
Defect ID:
Tiêu đề:
Product / module / service:
Release cohort:
Commit / change / build liên quan:

Introduction phase:
Detection phase:
First observed at:
Confirmed at:
Severity / priority:
Trạng thái tại release:
Fix version:
Verified at:

Hành vi sai:
Điều kiện tái hiện:
Người dùng / giao dịch bị ảnh hưởng:
Incident / customer ticket liên quan:
Root cause:
Test hoặc kiểm soát đã bỏ lỡ:
Bằng chứng:
Regression test cần bổ sung:
Owner và hành động tiếp theo:
~~~

### 11.2. Mẫu báo cáo cohort

~~~text
Release / cohort:
Ngày triển khai:
Cửa sổ quan sát:
Số giao dịch / người dùng / exposure:
Tổng defect duy nhất được xác nhận:

Defect phát hiện trước production:
- Theo giai đoạn:
- Theo severity:
- Đã sửa và retest đạt:
- Còn mở khi release:

Defect phát hiện lần đầu ở production:
- Theo severity:
- Theo nguồn phát hiện:
- Theo loại tác động:
- Đã attribution / chưa attribution:

Pre-production Detection Rate:
Production Escape Rate:
DRE:
Pre-release Closure Rate:
Known-open Release Rate:
Weighted Escape Rate (nếu dùng):
Escaped Defects per exposure:

Thời gian phát hiện / xác nhận / khắc phục:
Các giới hạn dữ liệu:
Root cause nổi bật:
Hành động cải tiến:
Owner / deadline:
Ngày cập nhật:
~~~

### 11.3. Checklist trước khi công bố số liệu

- [ ] Giai đoạn phát hiện và giai đoạn phát sinh được phân biệt.
- [ ] Defect được liên kết với release/cohort bằng bằng chứng.
- [ ] Duplicate và false positive được xử lý theo quy tắc.
- [ ] Defect đã biết nhưng còn mở được theo dõi riêng.
- [ ] Severity dùng rubric nhất quán.
- [ ] Cửa sổ quan sát và exposure được công bố.
- [ ] Công thức và mẫu số được ghi rõ.
- [ ] Defect chưa xác định được attribution không bị phân bổ đoán.
- [ ] Dữ liệu từ test, incident, support và monitoring được đối chiếu.
- [ ] Các cohort đủ thời gian quan sát được phân biệt với cohort tạm thời.
- [ ] Số liệu tổng hợp không che khuất lỗi Critical/High.
- [ ] Có hành động cải tiến, owner và thời hạn.

## Kết luận

Đánh giá khả năng phát hiện lỗi cần theo dõi cả giai đoạn phát hiện, giai đoạn phát sinh, mức độ nghiêm trọng và quan hệ giữa defect với release. DRE và production escape rate chỉ có ý nghĩa khi định nghĩa, cohort, cửa sổ quan sát và quy tắc đếm được thống nhất; đồng thời cần theo dõi riêng lỗi đã biết còn mở, mức độ đóng trước release, exposure và thời gian phát hiện. Khi dữ liệu đáng tin cậy được kết hợp với phân tích nguyên nhân và hành động cải tiến, nhóm có thể nhận ra cơ hội phát hiện sớm hơn, giảm tác động production và điều chỉnh chiến lược kiểm thử dựa trên bằng chứng.
