# Xác định kỹ năng chuyên sâu và khả năng đáp ứng của nhóm

## Mục tiêu bài học

Một chiến lược kiểm thử chỉ có thể thực hiện được khi nhóm có đủ kỹ năng, thời gian và quyền tiếp cận cần thiết. Một kế hoạch có thể yêu cầu kiểm thử hiệu năng, bảo mật, dữ liệu, tích hợp, tự động hóa và vận hành CI/CD, nhưng nhóm hiện tại có thể chỉ có kinh nghiệm kiểm thử chức năng. Ngược lại, nhóm có nhiều chuyên gia nhưng thiếu thời gian, môi trường hoặc sự phối hợp với chủ sở hữu hệ thống thì vẫn không đáp ứng được kế hoạch.

Trong VALIDATION_TESTING_STRATEGY, cần đánh giá đồng thời **năng lực chuyên môn** (capability) và **khả năng đáp ứng công việc** (capacity). Năng lực cho biết nhóm có kiến thức, kỹ năng và kinh nghiệm để thực hiện một loại kiểm thử hay không. Khả năng đáp ứng cho biết nhóm có đủ thời gian, nhân lực, công cụ, môi trường và quyền hạn để hoàn thành công việc trong thời hạn yêu cầu hay không. Hai yếu tố này liên quan nhưng không thay thế nhau.

Sau bài học, người học có thể:

- Phân biệt năng lực, mức thành thạo, công suất làm việc và khả năng đáp ứng.
- Xác định các kỹ năng chuyên sâu cần thiết theo rủi ro và phạm vi kiểm thử.
- Xây dựng ma trận kỹ năng với tiêu chí thành thạo có thể quan sát.
- Đánh giá năng lực bằng bằng chứng thực tế thay vì chỉ dựa trên tự nhận xét.
- Dự báo nhu cầu nguồn lực theo khối lượng, thời hạn và mức độ ưu tiên.
- Nhận diện khoảng trống kỹ năng, điểm phụ thuộc vào một cá nhân và rủi ro quá tải.
- Lập kế hoạch đào tạo, chia sẻ kiến thức, điều phối, tuyển dụng hoặc thuê chuyên gia.
- Theo dõi khả năng đáp ứng và điều chỉnh chiến lược kiểm thử khi nguồn lực thay đổi.

## 1. Năng lực và khả năng đáp ứng là hai câu hỏi khác nhau

Khi lập kế hoạch kiểm thử, nhóm cần trả lời hai câu hỏi:

1. **Chúng ta có thể làm công việc này không?** Đây là câu hỏi về năng lực: kiến thức, kỹ năng, kinh nghiệm và khả năng sử dụng công cụ.
2. **Chúng ta có thể hoàn thành công việc này trong điều kiện hiện tại không?** Đây là câu hỏi về khả năng đáp ứng: thời gian, số người, lịch làm việc, môi trường, ngân sách và các cam kết khác.

Ví dụ, một nhóm có chuyên gia kiểm thử hiệu năng đủ khả năng thiết kế kịch bản tải phức tạp. Tuy nhiên, nếu chuyên gia đó chỉ có thể dành một ngày trong khi kế hoạch cần hai tuần chuẩn bị, chạy thử và phân tích, nhóm vẫn không có khả năng đáp ứng đúng hạn.

Ngược lại, nhóm có nhiều người rảnh nhưng chưa ai có kinh nghiệm đánh giá lỗ hổng bảo mật có thể có công suất làm việc nhưng thiếu năng lực để tự thực hiện đánh giá chuyên sâu. Trong trường hợp đó, cần đào tạo, phối hợp với chuyên gia hoặc thay đổi phạm vi kiểm tra theo quyết định có thẩm quyền.

### 1.1. Các khái niệm cần phân biệt

| Khái niệm | Ý nghĩa | Câu hỏi cần trả lời |
|---|---|---|
| Năng lực (capability) | Khả năng thực hiện một loại công việc với chất lượng cần thiết. | Nhóm có kiến thức và kỹ năng cần thiết không? |
| Mức thành thạo (proficiency) | Mức độ độc lập, chiều sâu và độ tin cậy khi thực hiện kỹ năng. | Người thực hiện cần hướng dẫn ở mức nào? |
| Công suất (capacity) | Thời gian làm việc có thể phân bổ sau khi trừ các cam kết và hoạt động không dành cho dự án. | Nhóm có bao nhiêu thời gian thực sự? |
| Nhu cầu nguồn lực (demand) | Khối lượng công việc và kỹ năng cần thiết trong một khoảng thời gian. | Công việc cần bao nhiêu người, giờ và chuyên môn? |
| Khả năng đáp ứng (readiness) | Mức độ sẵn sàng tổng hợp về người, kỹ năng, công suất, công cụ, dữ liệu và môi trường. | Nhóm có thể thực hiện an toàn và đúng hạn không? |
| Độ bao phủ kỹ năng | Mức độ các kỹ năng quan trọng được nhiều người có thể thực hiện. | Nhóm có phụ thuộc vào một cá nhân không? |

### 1.2. Năng lực không chỉ nằm ở chức danh

Chức danh như QA Engineer, Automation Engineer, SDET hoặc Performance Engineer không mô tả đầy đủ những gì một người có thể làm. Hai người cùng chức danh có thể có kinh nghiệm khác nhau về phân tích rủi ro, thiết kế dữ liệu, kiểm thử API, concurrency hoặc điều tra production issue.

Đánh giá nên dựa trên công việc đã thực hiện, mức độ độc lập, chất lượng kết quả và khả năng hỗ trợ người khác. Không nên mặc định một người có thể đảm nhiệm mọi kỹ năng chỉ vì họ thuộc nhóm kiểm thử.

## 2. Xác định kỹ năng cần thiết từ mục tiêu và rủi ro kiểm thử

Không nên xây dựng danh sách kỹ năng chỉ dựa trên công nghệ đang thịnh hành hoặc sở thích của nhóm. Hãy bắt đầu từ sản phẩm, rủi ro và bằng chứng cần thu thập.

### 2.1. Đi từ rủi ro đến kỹ năng

Ví dụ:

| Rủi ro hoặc mục tiêu | Kỹ năng có thể cần |
|---|---|
| Sai quy tắc nghiệp vụ và luồng người dùng | Phân tích yêu cầu, khám phá nghiệp vụ, thiết kế test, UAT. |
| Lỗi giao tiếp giữa dịch vụ | API testing, contract testing, message/event testing, integration debugging. |
| Lỗi phân quyền hoặc rò rỉ dữ liệu | Security testing, identity/access control, tenant isolation, data privacy. |
| Suy giảm hiệu năng khi tải cao | Performance engineering, workload modeling, profiling, capacity analysis. |
| Dữ liệu không nhất quán hoặc migration lỗi | Database testing, data validation, migration testing, reconciliation. |
| Pipeline không đáng tin cậy | CI/CD, test automation, flaky test analysis, observability. |
| Hệ thống không phục hồi sau sự cố | Resilience testing, backup/restore, failover, incident operations. |
| Khác biệt thiết bị hoặc khả năng tiếp cận | Cross-browser/device testing, accessibility testing, usability evaluation. |
| Lỗi khó tái hiện trong môi trường thật | Log/trace analysis, debugging, production observability, exploratory testing. |

Một dự án không nhất thiết cần tất cả kỹ năng ở mức chuyên gia. Cần xác định kỹ năng nào phải có nội bộ, kỹ năng nào có thể phối hợp hoặc thuê ngoài, và kỹ năng nào chỉ cần hiểu biết cơ bản để nhận diện rủi ro.

### 2.2. Phân nhóm kỹ năng

Có thể phân loại theo các nhóm sau:

**Kỹ năng nền tảng về kiểm thử**

- Phân tích yêu cầu và tiêu chí chấp nhận.
- Thiết kế test case, phân vùng tương đương và giá trị biên.
- Phân tích rủi ro và thiết kế độ bao phủ.
- Kiểm thử thủ công và khám phá.
- Ghi nhận lỗi, tái hiện và điều tra nguyên nhân.
- Kiểm thử hồi quy và đánh giá tác động thay đổi.

**Kỹ năng kỹ thuật**

- Lập trình và đọc mã nguồn.
- Kiểm thử API, contract và tích hợp.
- Tự động hóa giao diện, dịch vụ và dữ liệu.
- Cơ sở dữ liệu, SQL, migration và transaction.
- Message broker, event-driven system và xử lý bất đồng bộ.
- Container, cloud, network và cấu hình môi trường.
- CI/CD, quản lý artifact và pipeline debugging.

**Kỹ năng chuyên sâu**

- Kiểm thử hiệu năng, tải, stress và endurance.
- Kiểm thử bảo mật và phân tích quyền truy cập.
- Kiểm thử khả năng phục hồi, failover và disaster recovery.
- Kiểm thử dữ liệu, chất lượng dữ liệu và đối soát.
- Accessibility và đánh giá khả năng sử dụng.
- Compatibility, localization và kiểm thử đa nền tảng.
- Kiểm thử AI/ML nếu sản phẩm có mô hình hoặc hành vi xác suất.

**Kỹ năng phối hợp và vận hành**

- Hiểu miền nghiệp vụ.
- Quản lý test strategy và test governance.
- Phân tích bằng chứng và truyền đạt rủi ro.
- Điều phối UAT và làm việc với stakeholder.
- Quản lý incident, release gate và escalation.
- Hướng dẫn, mentoring và chia sẻ kiến thức.

### 2.3. Chọn chiều sâu cần thiết

Với mỗi kỹ năng, hãy xác định mức độ cần thiết theo rủi ro:

- **Nhận biết:** hiểu thuật ngữ, giới hạn và dấu hiệu cần chuyên gia.
- **Thực hiện theo hướng dẫn:** có thể chạy quy trình hoặc công cụ đã được chuẩn bị.
- **Thực hiện độc lập:** có thể thiết kế, thực thi và phân tích công việc thông thường.
- **Chuyên sâu:** có thể giải quyết tình huống phức tạp, thiết kế phương pháp và hướng dẫn người khác.
- **Dẫn dắt/kiến trúc:** có thể định hướng chiến lược, đặt tiêu chuẩn, đánh giá trade-off và chịu trách nhiệm chuyên môn.

Không phải mọi kỹ năng đều cần một chuyên gia toàn thời gian. Ví dụ, nhóm có thể cần nhiều người biết chạy performance smoke test, nhưng chỉ cần một chuyên gia thiết kế workload và phân tích điểm nghẽn trong giai đoạn nhất định.

## 3. Xây dựng ma trận kỹ năng của nhóm

Ma trận kỹ năng (skills matrix) cho biết nhóm có những kỹ năng nào, mức thành thạo ra sao và có thể phân bổ vào công việc nào. Ma trận nên đủ chi tiết để hỗ trợ quyết định, nhưng không quá phức tạp khiến việc cập nhật trở thành gánh nặng.

### 3.1. Ví dụ ma trận kỹ năng

Thang mức minh họa:

- 0 — Chưa có kinh nghiệm thực tế.
- 1 — Nhận biết khái niệm, cần hướng dẫn sát.
- 2 — Thực hiện công việc cơ bản theo quy trình.
- 3 — Thực hiện độc lập và xử lý tình huống thông thường.
- 4 — Chuyên sâu, có thể thiết kế phương pháp và hướng dẫn người khác.

| Kỹ năng | An | Bình | Chi | Dũng | Mức cần cho dự án |
|---|---:|---:|---:|---:|---:|
| Phân tích yêu cầu và thiết kế test | 4 | 3 | 3 | 2 | 3 |
| API/contract testing | 3 | 4 | 2 | 2 | 3 |
| UI automation | 2 | 3 | 4 | 1 | 3 |
| Database/data testing | 3 | 2 | 2 | 3 | 3 |
| Performance testing | 1 | 3 | 1 | 2 | 3 |
| Security testing | 1 | 2 | 1 | 1 | 3 |
| CI/CD và pipeline debugging | 2 | 3 | 3 | 4 | 3 |
| Domain/UAT facilitation | 3 | 2 | 4 | 2 | 3 |

Bảng này chỉ minh họa cách tổ chức thông tin, không phải đánh giá nhân sự thực tế. Mức cần cho dự án cần được suy ra từ phạm vi và rủi ro đã thống nhất.

### 3.2. Ghi rõ bằng chứng và phạm vi

Một con số đơn lẻ có thể gây hiểu nhầm. Mức thành thạo nên đi kèm bằng chứng như:

- Đã thiết kế và triển khai loại kiểm thử nào.
- Có thể tự xử lý đến mức nào.
- Có sản phẩm hoặc kết quả đã được review.
- Đã xử lý tình huống phức tạp nào.
- Có thể hướng dẫn hoặc review công việc của người khác không.
- Kỹ năng còn mới hay đã được sử dụng gần đây.
- Có giới hạn công nghệ hoặc miền nghiệp vụ nào.

Ví dụ, một người có mức 3 về API testing với REST và JSON không nhất thiết có mức tương tự với gRPC, GraphQL hoặc message-based integration. Ma trận nên ghi rõ phạm vi công nghệ khi sự khác biệt quan trọng.

### 3.3. Đánh giá theo bằng chứng, không chỉ tự chấm điểm

Có thể kết hợp nhiều cách:

- Tự đánh giá để ghi nhận mức tự tin và nhu cầu phát triển.
- Review công việc thực tế hoặc portfolio nội bộ.
- Quan sát thực hiện một nhiệm vụ đại diện.
- Pairing hoặc mentoring để xem khả năng giải quyết vấn đề.
- Review test plan, code, báo cáo hoặc phân tích sự cố.
- Phản hồi từ người phối hợp và chủ sở hữu kỹ thuật.

Không nên dùng ma trận kỹ năng như bảng xếp hạng cá nhân hoặc căn cứ duy nhất cho đánh giá hiệu suất. Mục đích chính là tìm cách bố trí công việc, giảm điểm phụ thuộc và lập kế hoạch phát triển năng lực.

### 3.4. Cập nhật ma trận theo thời gian

Kỹ năng có thể tăng, giảm hoặc thay đổi phạm vi. Một người có thể chưa dùng công cụ trong thời gian dài; một công nghệ mới có thể khiến kỹ năng cũ không còn đủ. Nên rà soát khi:

- Phạm vi sản phẩm hoặc kiến trúc thay đổi.
- Có kỹ năng mới trở thành yêu cầu trọng yếu.
- Thành viên gia nhập hoặc rời nhóm.
- Một người được đào tạo hoặc hoàn thành dự án chuyên sâu.
- Phát sinh sự cố cho thấy năng lực hiện tại chưa đủ.
- Bắt đầu chu kỳ lập kế hoạch hoặc phát hành lớn.

Ghi ngày đánh giá và người xác nhận để tránh dùng một ma trận cũ như dữ liệu hiện tại.

## 4. Đánh giá mức độ thành thạo bằng hành vi quan sát được

Mức thành thạo cần mô tả người thực hiện có thể làm gì trong điều kiện thực tế. Tránh định nghĩa mơ hồ như “biết tốt”, “khá giỏi” hoặc “expert” mà không có tiêu chí.

### 4.1. Thang năng lực gợi ý

| Mức | Mô tả hành vi | Phạm vi trách nhiệm |
|---|---|---|
| 0 — Chưa có | Chưa có kinh nghiệm hoặc chưa thể giải thích các khái niệm cơ bản. | Chưa giao nhiệm vụ độc lập. |
| 1 — Nhận biết | Hiểu mục đích, thuật ngữ và có thể nhận diện khi nào cần hỗ trợ. | Tham gia quan sát hoặc thực hiện bước đơn giản có hướng dẫn. |
| 2 — Cơ bản | Thực hiện quy trình đã định nghĩa, dùng công cụ và báo cáo kết quả thông thường. | Làm việc với review thường xuyên. |
| 3 — Độc lập | Lựa chọn phương pháp, thiết kế và thực thi kiểm tra, phân tích kết quả và xử lý tình huống phổ biến. | Sở hữu một phạm vi công việc. |
| 4 — Chuyên sâu | Giải quyết vấn đề phức tạp, thiết kế phương pháp, đánh giá rủi ro và mentoring. | Là đầu mối chuyên môn cho một lĩnh vực. |
| 5 — Dẫn dắt | Định hướng tiêu chuẩn, kiến trúc, chiến lược và phát triển năng lực của nhiều nhóm. | Chịu trách nhiệm định hướng chuyên môn ở cấp rộng hơn. |

Thang điểm chỉ có ý nghĩa khi được gắn với ví dụ công việc. Không nên kỳ vọng mọi kỹ năng đều cần mức 5 trong cùng một nhóm.

### 4.2. Ví dụ tiêu chí cho performance testing

- **Mức 1:** hiểu throughput, latency, concurrency và biết đọc một báo cáo tải cơ bản.
- **Mức 2:** chạy được kịch bản đã có, kiểm tra dữ liệu đầu vào và ghi nhận kết quả.
- **Mức 3:** xây dựng workload đại diện, thiết lập baseline, chạy thử và phân tích bottleneck thông thường.
- **Mức 4:** thiết kế kiểm thử tải phức tạp, phân tích hệ thống phân tán, phối hợp profiling và đề xuất cải thiện.
- **Mức 5:** định hướng performance strategy, capacity model, tiêu chuẩn đo lường và quy trình kiểm soát hiệu năng liên nhóm.

### 4.3. Ví dụ tiêu chí cho security testing

- **Mức 1:** hiểu các nhóm rủi ro cơ bản và biết báo cáo dấu hiệu bất thường.
- **Mức 2:** thực hiện checklist hoặc scan đã được cấu hình và phân loại kết quả ban đầu.
- **Mức 3:** kiểm tra luồng xác thực, phân quyền và các tình huống truy cập trái phép theo phạm vi đã định.
- **Mức 4:** thiết kế kiểm tra bảo mật chuyên sâu, phân tích exploitability và phối hợp xử lý phát hiện.
- **Mức 5:** xây dựng chương trình kiểm thử bảo mật, mô hình đe dọa và tiêu chuẩn kiểm soát cho nhiều hệ thống.

Việc một người có thể chạy scanner không đồng nghĩa họ đủ chuyên môn để kết luận một lỗ hổng không có rủi ro. Những đánh giá chuyên sâu cần người có năng lực tương ứng và quy trình phê duyệt phù hợp.

## 5. Tính toán công suất và khả năng đáp ứng

Sau khi biết nhóm có kỹ năng gì, cần tính thời gian thực tế có thể dành cho công việc. Tổng số giờ theo hợp đồng không phải toàn bộ công suất dự án.

### 5.1. Từ thời gian danh nghĩa đến công suất khả dụng

Có thể dùng công thức đơn giản:

\[
C_{\text{khả dụng}} =
C_{\text{danh nghĩa}}
- C_{\text{nghỉ}}
- C_{\text{họp}}
- C_{\text{hỗ trợ}}
- C_{\text{vận hành}}
- C_{\text{cam kết khác}}
\]

Ví dụ, một người có 40 giờ làm việc trong tuần. Sau khi trừ 4 giờ họp, 3 giờ hỗ trợ vận hành, 2 giờ đào tạo và 4 giờ dành cho công việc đã cam kết, công suất còn lại cho dự án là 27 giờ. Con số này vẫn cần điều chỉnh theo mức gián đoạn và đặc điểm công việc.

### 5.2. Tính công suất theo nhóm

Giả sử nhóm có bốn người, mỗi người có công suất dự án khả dụng khác nhau:

| Thành viên | Công suất khả dụng/tuần |
|---|---:|
| An | 27 giờ |
| Bình | 24 giờ |
| Chi | 30 giờ |
| Dũng | 20 giờ |
| **Tổng** | **101 giờ** |

Tổng 101 giờ không có nghĩa nhóm có thể xử lý mọi loại công việc. Nếu chỉ Bình có thể thiết kế performance test, công suất chung không thể thay thế công suất chuyên sâu của Bình. Cần tính theo kỹ năng và vai trò, không chỉ cộng tổng giờ.

### 5.3. Dự báo nhu cầu theo công việc

Với mỗi hoạt động, ước lượng:

- Kết quả cần bàn giao.
- Kỹ năng cần thiết.
- Người hoặc vai trò cần tham gia.
- Số giờ thực hiện và review.
- Thời điểm bắt đầu và thời hạn.
- Phụ thuộc vào môi trường, dữ liệu hoặc đội khác.
- Mức độ bất định và dự phòng.

Ví dụ:

| Công việc | Kỹ năng chính | Nhu cầu ước tính | Thời điểm |
|---|---|---:|---|
| Thiết kế API contract test | API/contract | 24 giờ | Tuần 1 |
| Tự động hóa luồng chính | UI/API automation | 48 giờ | Tuần 1–2 |
| Kiểm thử hiệu năng | Performance | 32 giờ | Tuần 2 |
| Rà soát quyền truy cập | Security/access control | 24 giờ | Tuần 2 |
| Tích hợp CI và báo cáo | CI/CD, observability | 20 giờ | Tuần 2–3 |

Các ước lượng cần có độ bất định. Không nên xem chúng như cam kết chính xác khi chưa rõ môi trường hoặc phụ thuộc.

### 5.4. Công suất không bằng mức sử dụng 100%

Nếu lập kế hoạch sử dụng toàn bộ giờ khả dụng, nhóm sẽ không có không gian cho sự cố, review, hỗ trợ và thay đổi ưu tiên. Cần giữ phần dự phòng phù hợp với độ biến động của công việc.

Một cách lập kế hoạch là dùng hệ số tập trung (focus factor), chẳng hạn chỉ phân bổ một tỷ lệ công suất khả dụng cho công việc đã lên kế hoạch. Tỷ lệ này cần dựa trên dữ liệu thực tế của nhóm, không dùng một con số cố định cho mọi tổ chức.

## 6. Đánh giá khả năng đáp ứng theo kỹ năng

Một nhóm có đủ tổng giờ nhưng thiếu một kỹ năng trọng yếu vẫn có thể không hoàn thành. Vì vậy, cần so sánh nhu cầu và công suất theo từng kỹ năng.

### 6.1. Bảng cung-cầu kỹ năng

| Kỹ năng | Nhu cầu trong giai đoạn | Người có thể thực hiện độc lập | Rủi ro |
|---|---:|---:|---|
| API/contract testing | 40 giờ | 2 | Có thể đáp ứng nếu phân bổ hợp lý. |
| UI automation | 48 giờ | 1 | Phụ thuộc một người; cần review và hỗ trợ. |
| Performance testing | 32 giờ | 1 | Nút thắt chuyên môn. |
| Security testing | 24 giờ | 0 | Chưa đủ năng lực nội bộ để tự thực hiện. |
| CI/CD | 20 giờ | 2 | Có dự phòng cơ bản. |

Bảng cho thấy không thể kết luận nhóm đáp ứng chỉ bằng tổng công suất. Security testing cần chuyên gia bên ngoài hoặc nguồn lực từ nhóm bảo mật; performance cần bảo vệ thời gian của người có kỹ năng.

### 6.2. Kiểm tra mức phủ tối thiểu

Với mỗi kỹ năng quan trọng, hãy xác định:

- Có ít nhất một người đủ khả năng thực hiện độc lập không?
- Có người thứ hai có thể review hoặc thay thế khi cần không?
- Có người hiểu kiến trúc và bối cảnh của kỹ năng đó không?
- Có công cụ, dữ liệu và môi trường để thực hiện không?
- Người có kỹ năng có thời gian trong đúng giai đoạn cần thiết không?
- Có phụ thuộc vào một người đang kiêm nhiệm nhiều dự án không?

Một kỹ năng có một chuyên gia nhưng người đó không có thời gian vẫn là khoảng trống về khả năng đáp ứng. Một người dự phòng có mức thành thạo cơ bản có thể giảm rủi ro vận hành nhưng chưa chắc đủ để thay thế chuyên gia trong tình huống phức tạp.

### 6.3. Phân biệt thiếu kỹ năng và thiếu công suất

| Tình huống | Chẩn đoán | Hành động phù hợp |
|---|---|---|
| Có người đủ kỹ năng nhưng không có thời gian | Thiếu công suất. | Điều chỉnh ưu tiên, lịch, phạm vi hoặc bổ sung người. |
| Có thời gian nhưng chưa ai biết thực hiện | Thiếu năng lực. | Đào tạo, mentoring, thuê chuyên gia hoặc phối hợp nhóm khác. |
| Có kỹ năng và thời gian nhưng thiếu môi trường | Thiếu điều kiện thực hiện. | Chuẩn bị môi trường, sandbox, dữ liệu hoặc công cụ. |
| Có chuyên gia nhưng chỉ một người hiểu hệ thống | Rủi ro phụ thuộc cá nhân. | Pairing, tài liệu hóa và phát triển người thay thế. |
| Nhu cầu thay đổi liên tục | Bất định kế hoạch. | Lập kế hoạch theo giai đoạn, dự phòng và rà soát thường xuyên. |

## 7. Nhận diện khoảng trống và rủi ro phụ thuộc cá nhân

Khoảng trống kỹ năng là sự chênh lệch giữa năng lực hiện có và năng lực cần thiết. Khoảng trống có thể xuất hiện ở mức chuyên môn, số người, công suất, công cụ hoặc khả năng phối hợp.

### 7.1. Phân tích khoảng trống

Với mỗi kỹ năng, ghi:

- Mức cần thiết theo rủi ro.
- Mức hiện tại của nhóm.
- Số người có thể thực hiện độc lập.
- Số người có thể review hoặc thay thế.
- Công suất thực tế trong giai đoạn.
- Mức độ phụ thuộc vào bên ngoài.
- Thời gian cần để phát triển năng lực.

Có thể dùng ma trận khoảng trống:

| Kỹ năng | Mức cần | Mức hiện tại | Số người độc lập | Khoảng trống | Ưu tiên |
|---|---:|---:|---:|---|---|
| API/contract | 3 | 3 | 2 | Nhỏ | Trung bình |
| Performance | 3 | 2 | 1 | Thiếu chiều sâu | Cao |
| Security | 4 | 1 | 0 | Thiếu chuyên gia | Rất cao |
| Data testing | 3 | 2 | 1 | Thiếu dự phòng | Cao |

### 7.2. Bus factor và điểm phụ thuộc

Bus factor là cách gọi phổ biến cho số người tối thiểu có thể rời nhóm trước khi nhóm mất khả năng duy trì một phần công việc quan trọng. Không cần dùng thuật ngữ này để đánh giá cá nhân; hãy dùng nó để nhận diện rủi ro kiến thức tập trung.

Ví dụ, nếu chỉ một người có thể vận hành performance test và người đó nghỉ phép, hoạt động có thể dừng. Nếu chỉ một người hiểu cách khôi phục dữ liệu test, một sự cố môi trường có thể kéo dài.

Các biện pháp giảm phụ thuộc:

- Pairing và shadowing.
- Tài liệu hóa quy trình và quyết định.
- Tạo người dự phòng có thể thực hiện độc lập.
- Review chéo test plan, script và báo cáo.
- Chia sẻ quyền truy cập và hướng dẫn vận hành theo nguyên tắc an toàn.
- Tạo bài tập thực hành hoặc diễn tập chuyển giao.
- Luân phiên nhiệm vụ khi phù hợp.

Không nên đặt mục tiêu mọi người đều phải biết mọi thứ. Mục tiêu là bảo đảm các kỹ năng trọng yếu có độ phủ phù hợp và không phụ thuộc vào một điểm duy nhất mà không có phương án.

## 8. Lựa chọn cách lấp khoảng trống kỹ năng

Khi phát hiện thiếu năng lực hoặc công suất, có nhiều lựa chọn. Cần chọn theo mức độ khẩn cấp, độ sâu cần thiết, thời gian phát triển và tính chất lâu dài của nhu cầu.

| Phương án | Khi phù hợp | Ưu điểm | Giới hạn |
|---|---|---|---|
| Đào tạo nội bộ | Kỹ năng có thể phát triển trong thời gian dự án cho phép. | Tăng năng lực bền vững và hiểu biết sản phẩm. | Cần thời gian học và cơ hội thực hành. |
| Mentoring/pairing | Có chuyên gia nội bộ và người học có nền tảng phù hợp. | Truyền kiến thức gắn với công việc thực tế. | Có thể làm giảm công suất ngắn hạn của chuyên gia. |
| Luân chuyển nhiệm vụ | Cần tạo dự phòng và mở rộng trải nghiệm. | Giảm phụ thuộc cá nhân. | Cần giám sát để không ảnh hưởng chất lượng. |
| Phối hợp nhóm chuyên môn | Kỹ năng nằm ở nhóm bảo mật, dữ liệu, SRE hoặc nền tảng. | Dùng được chuyên môn sẵn có. | Cần lịch, quyền ưu tiên và trách nhiệm rõ. |
| Thuê chuyên gia hoặc nhà cung cấp | Cần chuyên môn sâu, hiếm hoặc khẩn cấp. | Có thể lấp khoảng trống nhanh. | Cần quản lý phạm vi, chi phí, dữ liệu và chuyển giao. |
| Tuyển dụng | Nhu cầu lâu dài, liên tục và đủ lớn. | Tăng năng lực nội bộ bền vững. | Thời gian tuyển và hòa nhập dài. |
| Giảm hoặc chia giai đoạn phạm vi | Không thể bổ sung nguồn lực kịp thời. | Tập trung vào rủi ro ưu tiên cao. | Cần người có thẩm quyền chấp nhận phần rủi ro chưa kiểm tra. |

### 8.1. Chọn theo thời gian và mức rủi ro

- Nếu rủi ro cao và thời hạn gần, cần chuyên gia đủ năng lực ngay; đào tạo người mới có thể không kịp.
- Nếu nhu cầu lặp lại lâu dài, đầu tư đào tạo hoặc tuyển dụng có thể hợp lý hơn thuê ngoài từng lần.
- Nếu công việc chỉ xuất hiện một lần, phối hợp chuyên gia hoặc thuê dịch vụ có thể phù hợp.
- Nếu không thể đáp ứng, cần điều chỉnh phạm vi, thời hạn hoặc kế hoạch phát hành qua quyết định có thẩm quyền.

Không nên giao một nhiệm vụ bảo mật, hiệu năng hoặc phục hồi quan trọng cho người chưa đủ năng lực chỉ để lấp một ô trong ma trận.

### 8.2. Kế hoạch phát triển năng lực

Một kế hoạch đào tạo nên xác định:

- Kỹ năng mục tiêu và mức thành thạo cần đạt.
- Khoảng trống hiện tại.
- Người hướng dẫn hoặc nguồn học.
- Bài tập thực tế hoặc nhiệm vụ có giám sát.
- Thời gian và công suất dành cho học tập.
- Bằng chứng hoàn thành.
- Người review và thời điểm đánh giá lại.
- Phạm vi công việc có thể giao sau đào tạo.

Hoàn thành khóa học không tự động chứng minh năng lực thực tế. Cần có cơ hội thực hành và review kết quả.

## 9. Kết hợp kỹ năng trong nhóm và mô hình làm việc

Một chiến lược kiểm thử thường cần phối hợp nhiều chuyên môn. Có thể tổ chức theo các mô hình:

### 9.1. Nhóm đa kỹ năng (cross-functional)

Các thành viên có kỹ năng bổ trợ cùng làm việc trong một nhóm sản phẩm. Cách này giúp phản hồi nhanh và chia sẻ trách nhiệm chất lượng xuyên suốt.

Phù hợp khi kiểm thử cần phối hợp thường xuyên với phát triển, sản phẩm và vận hành. Cần tránh việc một người bị kỳ vọng làm mọi vai trò mà không có chiều sâu chuyên môn.

### 9.2. Nhóm chuyên môn tập trung (center of excellence hoặc enabling team)

Một nhóm nhỏ chuyên sâu về performance, security, automation hoặc test platform hỗ trợ nhiều nhóm sản phẩm. Họ có thể:

- Xây dựng tiêu chuẩn và công cụ dùng chung.
- Hướng dẫn và review phương pháp.
- Tham gia các đánh giá có rủi ro cao.
- Đào tạo người trong nhóm sản phẩm.
- Duy trì năng lực chuyên sâu khó phân bổ toàn thời gian.

Cần có cơ chế ưu tiên và thời gian hỗ trợ rõ ràng; nếu không, nhóm chuyên môn có thể trở thành nút thắt cho mọi yêu cầu.

### 9.3. Mô hình kết hợp

Một mô hình phổ biến là mỗi nhóm sản phẩm có năng lực kiểm thử nền tảng, còn chuyên gia chuyên sâu được chia sẻ theo nhu cầu. Ví dụ, nhóm sản phẩm tự sở hữu unit, API và regression test; chuyên gia security hỗ trợ threat-based testing; performance engineer tham gia trước các đợt tăng tải lớn.

Mô hình này cần xác định rõ ai chịu trách nhiệm cuối cùng cho kết quả và ai chỉ cung cấp tư vấn.

## 10. Lập kế hoạch nguồn lực theo giai đoạn

Nhu cầu kỹ năng thay đổi theo vòng đời sản phẩm. Không nên phân bổ cùng một nhóm người và công suất cho mọi giai đoạn.

| Giai đoạn | Nhu cầu kỹ năng thường gặp | Trọng tâm nguồn lực |
|---|---|---|
| Khám phá và thiết kế | Phân tích nghiệp vụ, risk assessment, test strategy, architecture review. | Người hiểu miền nghiệp vụ và kiến trúc. |
| Phát triển ban đầu | Unit/component test, API test, automation, data setup. | Developer, QA/SDET và test automation. |
| Tích hợp | Contract, integration, database, event và environment debugging. | Nhóm dịch vụ, integration tester, platform/data. |
| Trước phát hành | Regression, security, performance, UAT, release readiness. | Chuyên gia theo rủi ro và người có quyền chấp nhận. |
| Sau triển khai | Smoke, observability, incident response, production verification. | SRE/operations, component owner và QA. |
| Bảo trì | Flaky test, test data, regression optimization, capability development. | Test owner, platform và nhóm sản phẩm. |

### 10.1. Dự báo theo mốc và phụ thuộc

Lập kế hoạch cần xét thời điểm kỹ năng phải sẵn sàng. Một chuyên gia có thể có công suất trong tháng nhưng không có trong tuần cần kiểm thử. Một bài kiểm thử cần môi trường được cấp trước; nếu môi trường đến muộn, nhân lực có sẵn vẫn không thể làm việc.

Với mỗi mốc, ghi:

- Kỹ năng bắt buộc.
- Người hoặc nhóm cung cấp.
- Thời điểm cần bắt đầu và kết thúc.
- Phụ thuộc môi trường/dữ liệu/công cụ.
- Thời gian review và xử lý phát hiện.
- Dự phòng cho lỗi và thay đổi.
- Quyết định nếu nguồn lực không sẵn sàng.

### 10.2. Không phân bổ cùng một chuyên gia cho nhiều việc đồng thời

Một chuyên gia có thể được nhiều nhóm yêu cầu. Nếu lịch không được điều phối, các dự án đều giả định rằng người đó sẵn sàng, dẫn đến quá tải và trễ hạn.

Nên có một cơ chế ưu tiên dựa trên rủi ro, thời hạn và tác động. Ghi rõ phần trăm hoặc số giờ cam kết, các giai đoạn cần tham gia và người thay thế khi vắng mặt.

## 11. Đánh giá khả năng đáp ứng của nhóm qua kịch bản

Thay vì chỉ nhìn ma trận, có thể kiểm tra khả năng đáp ứng bằng các câu hỏi tình huống:

- Nếu chuyên gia security nghỉ hai tuần trước release, ai có thể tiếp nhận và phần nào cần hoãn?
- Nếu performance test phát hiện bottleneck, nhóm có người phân tích profiling và phối hợp với developer không?
- Nếu CI runner ngừng hoạt động, ai khôi phục và ai quyết định về các gate đang chờ?
- Nếu test data bị lỗi, ai hiểu quan hệ dữ liệu và có quyền reset môi trường?
- Nếu một người sở hữu test automation rời nhóm, ai có thể duy trì pipeline?
- Nếu hai dự án cùng cần một chuyên gia, ai ưu tiên và theo tiêu chí nào?
- Nếu yêu cầu thay đổi sát thời hạn, nhóm có thể đánh giá tác động và ước lượng lại không?

Kịch bản giúp phát hiện khoảng trống về người thay thế, quyền truy cập, tài liệu và quyết định, không chỉ khoảng trống kiến thức.

### 11.1. Đánh giá readiness theo từng hoạt động

Một hoạt động có thể được coi là sẵn sàng khi:

- Có người đủ năng lực thực hiện và review.
- Có công suất trong thời gian cần thiết.
- Mục tiêu, phạm vi và tiêu chí đã rõ.
- Có công cụ, dữ liệu và môi trường.
- Có quyền truy cập và phê duyệt cần thiết.
- Có phương án khi người hoặc phụ thuộc chính không sẵn sàng.
- Có cách ghi nhận kết quả và xử lý phát hiện.

Nếu thiếu một điều kiện trọng yếu, cần ghi rõ và quyết định khắc phục trước khi bắt đầu hoặc điều chỉnh kế hoạch.

## 12. Quản lý kiến thức và khả năng thay thế

Kỹ năng cá nhân chỉ trở thành năng lực bền vững của nhóm khi kiến thức có thể được chia sẻ và tái sử dụng.

Các tài sản kiến thức có thể gồm:

- Hướng dẫn chạy kiểm thử chuyên sâu.
- Test strategy và risk model.
- Mẫu workload, test data builder và fixture.
- Runbook cho pipeline, môi trường và sự cố.
- Hướng dẫn phân tích log, trace và profiling.
- Quy tắc bảo mật và quy trình phê duyệt.
- Bài học từ incident và lỗi đã xảy ra.
- Ví dụ về test tốt, báo cáo tốt và cách diễn giải kết quả.

Tài liệu cần có owner, phiên bản và ngày rà soát. Tài liệu lỗi thời có thể nguy hiểm hơn không có tài liệu nếu người thực hiện tin rằng hướng dẫn vẫn đúng.

### 12.1. Kiểm tra khả năng chuyển giao

Có thể dùng shadowing và reverse shadowing:

1. Người có kinh nghiệm thực hiện nhiệm vụ và giải thích quyết định.
2. Người học quan sát và thực hành một phần.
3. Người học thực hiện nhiệm vụ dưới sự giám sát.
4. Người học tự thực hiện, người hướng dẫn chỉ review.
5. Người học xử lý một tình huống phát sinh và giải thích lựa chọn.
6. Nhóm cập nhật tài liệu và xác nhận người dự phòng đã sẵn sàng.

Việc hoàn thành các bước này cung cấp bằng chứng tốt hơn việc chỉ ghi tên một người vào ma trận.

## 13. Đo lường năng lực và khả năng đáp ứng

Chỉ số nên hỗ trợ quyết định về rủi ro và kế hoạch, không trở thành bảng xếp hạng cá nhân.

| Chỉ số | Ý nghĩa | Cách sử dụng |
|---|---|---|
| Skill coverage | Tỷ lệ kỹ năng trọng yếu có ít nhất một người đạt mức cần thiết. | Nhận diện lĩnh vực chưa có năng lực tối thiểu. |
| Backup coverage | Tỷ lệ kỹ năng trọng yếu có người thứ hai có thể thay thế. | Đánh giá rủi ro phụ thuộc cá nhân. |
| Capacity coverage | Công suất khả dụng so với nhu cầu theo giai đoạn. | Nhận diện quá tải hoặc thiếu thời gian. |
| Demand/capacity ratio | Nhu cầu giờ hoặc effort chia cho công suất khả dụng. | Hỗ trợ ưu tiên và điều chỉnh phạm vi. |
| Time to proficiency | Thời gian để người học đạt mức thực hiện độc lập. | Lập kế hoạch đào tạo và succession. |
| External dependency | Mức độ công việc phụ thuộc chuyên gia hoặc nhà cung cấp ngoài. | Đánh giá tính bền vững và chi phí. |
| Planned vs actual effort | Chênh lệch giữa ước lượng và thời gian thực tế. | Cải thiện dự báo và hiểu nguồn gây gián đoạn. |
| Work in progress | Số công việc đang mở trên mỗi người hoặc nhóm. | Nhận diện phân mảnh và quá tải. |
| Critical skill concentration | Mức tập trung kỹ năng vào một vài người. | Lập kế hoạch chia sẻ kiến thức và dự phòng. |

Không nên diễn giải demand/capacity ratio vượt 1 như một kết luận tự động rằng dự án chắc chắn thất bại; cần xem xét lịch, mức độ song song, khả năng điều chỉnh phạm vi và độ bất định. Tuy nhiên, tỷ lệ vượt công suất trong nhiều giai đoạn là tín hiệu cần quyết định sớm.

## 14. Ví dụ thực tế: nhóm kiểm thử cho một nền tảng dịch vụ

Một nhóm có năm người chuẩn bị cho đợt phát hành nền tảng dịch vụ gồm API, giao diện web, xử lý sự kiện và thanh toán. Các rủi ro ưu tiên là tính đúng của giao dịch, quyền truy cập, hiệu năng và độ tin cậy của pipeline.

### 14.1. Đánh giá ban đầu

- Hai người có thể thực hiện API và contract test độc lập.
- Một người có kinh nghiệm sâu về UI automation.
- Một người có thể vận hành CI/CD và điều tra runner.
- Một người có kinh nghiệm performance ở mức cơ bản.
- Không ai đủ năng lực đánh giá bảo mật chuyên sâu.
- Chỉ một người hiểu toàn bộ test data và fixture cho giao dịch.

Tổng công suất danh nghĩa của nhóm là 200 giờ/tuần, nhưng sau các cuộc họp, hỗ trợ vận hành và công việc đã cam kết, công suất dành cho dự án còn 132 giờ. Chuyên gia UI automation chỉ có 18 giờ trong tuần đầu vì đang hỗ trợ một dự án khác.

### 14.2. Nhận diện khoảng trống

| Nhu cầu | Hiện trạng | Khoảng trống |
|---|---|---|
| API/contract | Hai người độc lập | Có thể đáp ứng. |
| UI automation | Một người, công suất hạn chế | Rủi ro thời hạn và điểm phụ thuộc. |
| Performance | Một người ở mức cơ bản | Thiếu chiều sâu cho workload và phân tích bottleneck. |
| Security | Chưa có chuyên gia | Cần phối hợp nhóm security hoặc thuê chuyên gia. |
| Test data | Một người hiểu fixture chính | Rủi ro bus factor và khả năng khôi phục. |
| CI/CD | Một người chuyên sâu, một người cơ bản | Cần phát triển người dự phòng. |

### 14.3. Kế hoạch đáp ứng

1. Ưu tiên thời gian của người UI automation cho luồng thanh toán cốt lõi; chuyển kiểm tra ít rủi ro sang API test phù hợp.
2. Đặt lịch chuyên gia performance tham gia thiết kế workload và review kết quả; người nội bộ thực hiện các bước chạy theo hướng dẫn.
3. Yêu cầu nhóm security thực hiện đánh giá chuyên sâu trước release, đồng thời nhóm kiểm thử chuẩn bị dữ liệu và luồng cần xác minh.
4. Pairing để một người thứ hai có thể tạo và khôi phục test data.
5. Tài liệu hóa runbook CI/CD và cho người dự phòng thực hành khôi phục runner trong môi trường thử nghiệm.
6. Chia công việc theo giai đoạn và giữ thời gian dự phòng cho phát hiện nghiêm trọng.

### 14.4. Quyết định readiness

Nhóm có thể tự thực hiện API, contract, UI và CI ở phạm vi đã định. Đánh giá bảo mật chuyên sâu phụ thuộc nhóm chuyên môn; performance cần review của chuyên gia. Nếu hai nguồn lực đó không sẵn sàng trước mốc phát hành, release owner cần điều chỉnh lịch hoặc chấp nhận rủi ro theo thẩm quyền. Không nên ghi toàn bộ chiến lược “đã sẵn sàng” chỉ vì nhóm có đủ tổng số giờ.

## 15. Những sai lầm thường gặp

- **Đánh đồng số người với năng lực:** đông người không có nghĩa đủ chuyên môn.
- **Đánh đồng giờ làm với công suất dự án:** bỏ qua họp, hỗ trợ, vận hành và cam kết khác.
- **Chỉ dùng tự đánh giá:** không có bằng chứng về khả năng thực hiện độc lập.
- **Dùng chức danh làm đại diện kỹ năng:** bỏ qua khác biệt về công nghệ và chiều sâu.
- **Yêu cầu mọi người biết mọi thứ:** tạo ma trận không thực tế và khó phát triển chuyên môn.
- **Chỉ có một chuyên gia cho kỹ năng trọng yếu:** tạo điểm phụ thuộc và rủi ro khi vắng mặt.
- **Không tính thời gian review và phối hợp:** ước lượng effort thấp hơn thực tế.
- **Không tính thời điểm cần kỹ năng:** chuyên gia có thể rảnh nhưng không đúng giai đoạn.
- **Giao việc chuyên sâu cho người chưa đủ năng lực:** tạo rủi ro chất lượng và trách nhiệm.
- **Đào tạo mà không có thực hành:** không chứng minh kỹ năng đã chuyển thành năng lực.
- **Thuê ngoài mà không chuyển giao:** kiến thức và khả năng vận hành vẫn phụ thuộc nhà cung cấp.
- **Không cập nhật ma trận:** quyết định dựa trên năng lực đã thay đổi.
- **Tối ưu mức sử dụng đến 100%:** không có chỗ cho phát hiện, sự cố và thay đổi ưu tiên.

## 16. Checklist xác định kỹ năng và khả năng đáp ứng

- [ ] Mục tiêu, rủi ro và phạm vi kiểm thử đã được xác định.
- [ ] Các kỹ năng nền tảng và chuyên sâu cần thiết đã được liệt kê.
- [ ] Mức thành thạo cần thiết được xác định theo rủi ro.
- [ ] Tiêu chí từng mức thành thạo mô tả hành vi có thể quan sát.
- [ ] Ma trận kỹ năng có bằng chứng và ngày rà soát.
- [ ] Có phân biệt năng lực, công suất và khả năng đáp ứng.
- [ ] Công suất đã trừ nghỉ phép, họp, hỗ trợ và cam kết khác.
- [ ] Nhu cầu được dự báo theo kỹ năng và thời điểm cần.
- [ ] Có kiểm tra mức phủ tối thiểu và người dự phòng cho kỹ năng trọng yếu.
- [ ] Khoảng trống được phân loại thành thiếu năng lực, công suất hoặc điều kiện.
- [ ] Có kế hoạch đào tạo, mentoring, phối hợp, thuê chuyên gia hoặc điều chỉnh phạm vi.
- [ ] Có lịch và quyền ưu tiên cho chuyên gia dùng chung.
- [ ] Kiến thức và runbook có owner, phiên bản và người thay thế.
- [ ] Readiness được đánh giá theo từng hoạt động, không chỉ tổng số giờ.
- [ ] Rủi ro chưa được đáp ứng được báo cáo cho người có thẩm quyền.
- [ ] Chỉ số được theo dõi và ma trận được cập nhật khi nhóm hoặc sản phẩm thay đổi.

## Kết luận

Xác định kỹ năng chuyên sâu và khả năng đáp ứng cần kết hợp đánh giá năng lực, mức thành thạo, công suất và điều kiện thực hiện. Hãy suy ra kỹ năng từ mục tiêu và rủi ro kiểm thử, mô tả mức thành thạo bằng hành vi có thể quan sát, đối chiếu cung-cầu theo từng kỹ năng và thời điểm. Khoảng trống có thể được xử lý bằng đào tạo, mentoring, phối hợp chuyên gia, tuyển dụng, thuê ngoài hoặc điều chỉnh phạm vi theo quyết định có thẩm quyền. Ma trận kỹ năng và kế hoạch nguồn lực chỉ hữu ích khi được cập nhật bằng bằng chứng, có người dự phòng cho lĩnh vực trọng yếu và phản ánh thời gian thực sự nhóm có thể dành cho công việc.
