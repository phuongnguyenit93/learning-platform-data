# Kết hợp kiểm thử tự động với kiểm thử khám phá

Một nhóm phát triển nền tảng học trực tuyến có bộ kiểm thử tự động chạy xanh sau mỗi lần tích hợp mã. API lưu tiến độ trả đúng dữ liệu mẫu, giao diện có nút “Học tiếp”, và bài kiểm thử end-to-end bấm nút thành công. Nhưng khi một học viên thật mở hai tab, đổi khóa học, bị mất kết nối trong lúc lưu rồi quay lại bằng điện thoại, hệ thống có lúc mở sai bài hoặc báo đã lưu dù dữ liệu chưa được ghi. **Tất cả bài kiểm thử đã biết đều qua, nhưng sản phẩm vẫn có vấn đề**.

Trường hợp này cho thấy **kiểm thử tự động và kiểm thử khám phá giải quyết hai nhu cầu bổ sung nhau**. Kiểm thử tự động giúp nhóm kiểm tra lại nhanh và nhất quán những điều đã được xác định. Kiểm thử khám phá giúp con người chủ động tìm hiểu sản phẩm, nhận ra những giả định chưa được thử thách, thiết kế phép thử ngay khi có phát hiện mới và tìm các rủi ro mà bộ kiểm thử hiện tại có thể chưa nhận biết.

Mục tiêu của bài không phải so tài “máy tốt hơn người” hay “kiểm thử thủ công tốt hơn tự động”, mà là xây **vòng phản hồi chất lượng liên tục**: hiểu rủi ro → kiểm tra điều đã biết → khám phá điều chưa biết → sửa và bổ sung bằng chứng → tự động hóa những phát hiện thích hợp → quan sát sản phẩm thật → cải tiến cách làm.

Bài thuộc chương **Chất lượng liên tục** của module **AGILE_DEVELOPMENT**. Cách phối hợp này gắn với các giá trị Agile: giao phần mềm tăng dần, nhận phản hồi sớm, cộng tác quanh user story và backlog, kết hợp các thực hành Scrum, Kanban, Extreme Programming (XP) và số đo dòng công việc để bảo vệ chất lượng khi thường xuyên thay đổi.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

1. Phân biệt **kiểm tra tự động (automated checks)**, **kiểm thử theo kịch bản** và **kiểm thử khám phá (exploratory testing)** mà không đánh đồng khám phá với thử ngẫu nhiên.
2. Nêu điểm mạnh, giới hạn và loại rủi ro phù hợp của từng cách tiếp cận.
3. Tạo **test charter** có mục tiêu, phạm vi, giả thuyết, dữ liệu, timebox và cách ghi nhận bằng chứng.
4. Dùng các heuristic về luồng người dùng, trạng thái, dữ liệu, ranh giới, thời gian và quyền truy cập để thiết kế phép thử khám phá.
5. Lựa chọn bài kiểm tra nên tự động hóa ở cấp **unit, component/API, integration, contract, end-to-end** theo hiệu quả phản hồi và chi phí bảo trì.
6. Biến một phát hiện từ phiên khám phá thành **ví dụ nghiệp vụ, kiểm thử hồi quy phù hợp và quyết định sản phẩm**.
7. Tổ chức vòng phản hồi cùng Developers, người kiểm thử, Product Owner và các bên hiểu nghiệp vụ trong Scrum, Kanban và XP.
8. Đọc các tín hiệu như lỗi lọt production, flaky tests, thời gian phản hồi, độ bao phủ rủi ro mà không dùng số lượng test như bằng chứng tuyệt đối về chất lượng.
9. Xây kế hoạch kết hợp hai hình thức kiểm thử cho một user story thực tế, có Definition of Done và cơ chế thu phản hồi sau phát hành.

## 2. Hai cách kiểm thử: bổ sung thay vì thay thế

Một phép kiểm tra tự động thường có **đầu vào, thao tác và kết quả mong đợi được xác định trước**. Chương trình thực hiện các bước và so sánh kết quả thực với điều kiện đã được mã hóa.

Trong kiểm thử khám phá, người thực hiện **đồng thời học về sản phẩm, thiết kế phép thử, thực hiện, quan sát và điều chỉnh hướng kiểm tra** dựa trên thông tin vừa xuất hiện. Người thực hiện có thể dùng script, công cụ tự động, query dữ liệu và log để hỗ trợ; “khám phá” không đồng nghĩa mọi thao tác phải bằng tay.

| Tiêu chí | Kiểm thử tự động | Kiểm thử khám phá |
| --- | --- | --- |
| **Câu hỏi chính** | Hành vi đã định nghĩa còn đúng không? | Chúng ta đang bỏ sót rủi ro, giả định hoặc hành vi nào? |
| **Cách xác định phép thử** | Thiết kế trước; kết quả mong đợi thường được mã hóa | Thiết kế và điều chỉnh ngay trong phiên học hỏi |
| **Ưu thế** | Lặp lại nhanh, nhất quán, mở rộng trên nhiều thay đổi, phát hiện hồi quy sớm | Linh hoạt trước thông tin mới, tìm hành vi bất ngờ, đánh giá tính hợp lý và khả dụng |
| **Hạn chế** | Không tự phát hiện kỳ vọng sai hoặc những tình huống chưa được mô tả; có chi phí bảo trì | Tốn tư duy và thời gian người có chuyên môn; khó lặp y nguyên mọi quan sát |
| **Bằng chứng tạo ra** | Kết quả pass/fail, dữ liệu chạy, log, ảnh chụp/trace khi phù hợp | Ghi chú, giả thuyết, tình huống tái hiện, lỗi, câu hỏi và gợi ý thiết kế |
| **Khi thay đổi** | Chạy lại bộ kiểm tra liên quan để phát hiện điều đã biết bị hỏng | Mở rộng điều cần hỏi và khám phá những vùng tác động chưa hiểu |
| **Nguy cơ lạm dụng** | Tăng số lượng bài test mà vẫn bỏ trống rủi ro chính | Thử tùy hứng không mục tiêu, không ghi bằng chứng, lặp thao tác cũ |

**Không phải mọi kiểm thử thủ công đều là kiểm thử khám phá.** Nếu một người làm theo checklist từng bước có kết quả mong đợi cố định và không chủ động thay đổi hướng tìm hiểu, đó chủ yếu là kiểm thử theo kịch bản thủ công. Nó vẫn có thể hữu ích, nhưng không đồng nghĩa với exploratory testing có tính khám phá mạnh.

**Không phải mọi phát hiện chỉ đến từ con người.** Property-based testing, fuzzing, model-based testing hoặc các công cụ quan sát có thể tự sinh tình huống và làm lộ hành vi chưa dự kiến. Tuy nhiên, vẫn cần con người đánh giá ý nghĩa, rủi ro và điều kiện đúng theo miền nghiệp vụ.

## 3. Vì sao kiểm thử tự động chạy xanh vẫn chưa đủ?

Một bộ kiểm tra tự động chỉ xác nhận **những điều đã được chọn để kiểm tra** trong những điều kiện đã được dựng. Có ít nhất sáu khoảng trống thường gặp.

| Khoảng trống | Ví dụ | Cách tiếp cận bổ trợ |
| --- | --- | --- |
| **Kỳ vọng sai** | Test khẳng định “luôn mở bài đầu” nhưng học viên cần bài đang dở | Trao đổi với người dùng, khám phá hành trình thật, cập nhật tiêu chí chấp nhận |
| **Đường đi chưa được mô tả** | Người học đổi khóa học, quay lại từ thông báo, dùng nút Back | Khám phá luồng thay thế và trạng thái chuyển tiếp |
| **Trạng thái dữ liệu khó lường** | Checkpoint cũ, bài bị xóa, quyền đã hết, đồng bộ chậm | Khám phá bằng dữ liệu biên và trạng thái thực tế an toàn |
| **Tương tác thời gian/đồng thời** | Hai tab ghi tiến độ gần cùng lúc | Khám phá race condition rồi tự động hóa phép kiểm chứng thích hợp |
| **Khả dụng và hiểu biết người dùng** | Nút hiện ra nhưng tên và vị trí gây nhầm | Quan sát thao tác, đánh giá khả dụng và accessibility |
| **Điều kiện môi trường** | Mạng chập chờn, cache lỗi, session hết hạn, giờ hệ thống lệch | Thử ngắt kết nối, refresh, retry và quan sát phản ứng |

Ví dụ, automation có thể xác nhận:

~~~text
Given: Học viên A có checkpoint hợp lệ ở bài B
When:  A nhấn "Học tiếp"
Then:  Hệ thống mở đúng bài B tại vị trí đã lưu
~~~

Nhưng câu hỏi khám phá có thể là: **“Điều gì xảy ra nếu người học đang ở bài B, mở bài C ở tab khác, rồi mạng mất ngay trước khi request lưu của B trả về?”** Nếu nhóm chưa bao giờ nghĩ tới tình huống đó, một nghìn lần chạy happy-path test cũng khó tìm ra lỗi.

### Sản phẩm đúng kỹ thuật chưa chắc đúng nhu cầu

Một tính năng có thể tuân thủ API contract nhưng thiếu khả dụng thực tế. Ví dụ API trả chính xác checkpoint, nhưng giao diện đặt “Học tiếp” ở vị trí khó nhận thấy với người dùng màn hình nhỏ. Cần kiểm tra cả **đúng chức năng, đáng tin và có ích với người sử dụng**, chứ không chỉ một loại bằng chứng.

## 4. Kiểm thử khám phá không phải “bấm thử lung tung”

Exploratory testing có tính kỷ luật: xác định **điều cần học**, dùng heuristic để tìm tình huống, thu thập bằng chứng, thay đổi hướng điều tra và diễn giải kết quả.

~~~mermaid
flowchart TD
    A["Mục tiêu và rủi ro cần tìm hiểu"] --> B["Lập charter<br/>phạm vi, dữ liệu, thời gian"]
    B --> C["Thực hiện phép thử và quan sát"]
    C --> D{"Có thông tin mới?"}
    D -->|Có| E["Đặt giả thuyết mới<br/>thay đổi phép thử"]
    E --> C
    D -->|Chưa| F["Đánh giá vùng chưa kiểm tra"]
    F --> C
    C --> G["Ghi nhận lỗi, câu hỏi<br/>và bằng chứng"]
    G --> H["Debrief và quyết định<br/>sửa, làm rõ, tự động hóa"]
~~~

Mô hình diễn tả **tư duy trong phiên**, không đòi người thực hiện phải dừng hẳn ở một bước trước khi sang bước khác. Ghi chú và trao đổi có thể diễn ra ngay trong quá trình khám phá.

Một phiên tốt thường có:

- **Mục tiêu có ý nghĩa:** rủi ro hoặc giả thuyết nào cần kiểm chứng?
- **Phạm vi rõ:** tính năng, phiên bản, môi trường, đối tượng và điều kiện dữ liệu.
- **Timebox phù hợp:** tránh khám phá không hồi kết; có thể gia hạn có chủ đích.
- **Heuristic và quan sát:** thay đổi dữ liệu, trạng thái, môi trường và luồng theo cách có lý do.
- **Bằng chứng:** request/response phù hợp, log đã khử dữ liệu nhạy cảm, ảnh chụp, kịch bản tái hiện, timestamp.
- **Kết luận trung thực:** điều đã thấy, điều chưa kiểm chứng, mức độ tin cậy, rủi ro còn lại và bước tiếp theo.

### Sự khác nhau giữa lỗi và câu hỏi

Không phải phát hiện nào cũng là bug. Có thể xuất hiện:

1. **Defect:** kết quả trái với quy tắc đã thống nhất.
2. **Ambiguity:** hai bên chưa thống nhất quy tắc.
3. **Usability concern:** người dùng gặp khó dù chương trình làm đúng theo mô tả.
4. **Risk:** chưa thấy lỗi nhưng điều kiện có thể gây hậu quả nghiêm trọng.
5. **Opportunity:** một phương án đơn giản hơn có thể giúp người dùng tốt hơn.

Gắn nhãn đúng giúp Product Owner và Developers quyết định phù hợp, thay vì chuyển mọi câu hỏi thành một “bug blocker” hoặc bỏ qua vì “chưa tái hiện được”.

## 5. Bắt đầu từ rủi ro và giá trị sản phẩm

Không thể kiểm thử mọi tổ hợp đầu vào, trạng thái, môi trường và hành vi người dùng. Vì vậy, trước khi chia thời gian giữa automation và exploration, hãy xác định **rủi ro nào có hậu quả cao, dễ xảy ra hoặc khó phát hiện**.

Một khung đánh giá:

| Chiều đánh giá | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Tác động** | Sai thì ai bị ảnh hưởng và nghiêm trọng ra sao? | Lộ dữ liệu tiến độ học viên là tác động cao |
| **Khả năng xuất hiện** | Điều kiện này phổ biến tới mức nào hoặc có bằng chứng gì? | Nhiều học viên dùng điện thoại và mạng kém |
| **Khả năng phát hiện trước khi gây hại** | Monitoring, test và phản hồi có thấy nhanh không? | Ghi checkpoint sai có thể không tạo lỗi HTTP |
| **Độ bất định** | Chúng ta hiểu quy tắc và môi trường đến đâu? | Retry và đồng bộ hai thiết bị chưa rõ |
| **Độ mới / phạm vi thay đổi** | Thay đổi chạm những thành phần nào? | Migration cấu trúc tiến độ ảnh hưởng cả web/mobile |
| **Khả năng phục hồi** | Nếu sai, có đảo tác động được không? | Mất tiến độ thật khó sửa chỉ bằng rollback code |

### Bản đồ rủi ro minh họa

| Rủi ro | Tác động | Cách kiểm tra tự động | Hướng khám phá |
| --- | --- | --- | --- |
| Người A đọc tiến độ người B | Rất cao | API authorization tests, test ID khác tài khoản, kiểm soát backend | Đổi session/tài khoản/đường dẫn, tìm lộ dữ liệu qua cache và thông báo lỗi |
| Retry làm ghi đè checkpoint mới | Cao | Integration/concurrency tests, kiểm tra idempotency theo thiết kế | Thử mạng chậm, gửi lại request, hai tab, chuyển thiết bị |
| Học viên không thấy nút “Học tiếp” | Trung bình về chức năng, có thể cao về outcome | Kiểm tra UI hiển thị, nhãn accessible và interaction cơ bản | Quan sát tác vụ trên màn hình nhỏ, dùng bàn phím/đọc màn hình |
| Nút mở sai bài khi bài đã hoàn tất | Trung bình–cao | Rule-based unit/API tests cho trạng thái bài | Kết hợp trạng thái khóa học, chuyển bài, Back/Forward |
| Giao diện lỗi ở mạng chập chờn | Tùy mức ảnh hưởng | E2E smoke cho timeout/error state đã biết | Thử offline/online, chậm, refresh và phản ứng của người dùng |

**Không cần giả vờ có con số xác suất chính xác khi chưa có dữ liệu.** Mục đích của đánh giá là quyết định **nên tập trung tìm hiểu và phòng ngừa rủi ro nào trước**, chứ không tạo một ma trận điểm số trông khoa học nhưng vô căn cứ.

### Kết hợp test dựa trên rủi ro với user story

Với user story “Học viên tiếp tục bài đang dở”, acceptance criteria cần mô tả những hành vi bắt buộc. Ngoài ra, danh sách rủi ro giúp nhóm thiết kế **kiểm thử bảo vệ** mà tiêu chí chấp nhận ngắn có thể chưa mô tả hết, ví dụ điều kiện cạnh tranh, dữ liệu riêng tư hoặc migration.

## 6. Một chiến lược kiểm thử cân bằng theo nhiều lớp

Không phải phép kiểm tra nào cũng cần thực hiện qua giao diện trình duyệt. Những quy tắc ổn định có thể được xác nhận nhanh ở unit/API; một số hành trình quan trọng vẫn cần end-to-end. Kiểm thử khám phá đi **xuyên các lớp** để tìm những rủi ro khó nhìn từ một test đã định nghĩa.

| Cấp / loại kiểm tra | Giá trị điển hình | Điểm cần thận trọng |
| --- | --- | --- |
| **Unit tests** | Nhanh, kiểm tra quy tắc và điều kiện biên của đơn vị nhỏ | Không chứng minh nhiều hệ thống tương tác đúng |
| **Component/service tests** | Kiểm tra hành vi một dịch vụ với phụ thuộc được kiểm soát | Mock quá nhiều có thể che lỗi tích hợp thật |
| **API/contract tests** | Phân quyền, schema, business rules và tương thích giữa consumer/provider | Contract đúng chưa chứng minh luồng người dùng dễ sử dụng |
| **Integration tests** | Kiểm tra ứng dụng, database, message broker và các phụ thuộc thật có phối hợp | Cần quản lý dữ liệu, môi trường và thời gian chạy |
| **End-to-end tests** | Kiểm tra đường đi giá trị xuyên các thành phần chính | Chậm, dễ flaky nếu quá nhiều, khó định vị nguyên nhân |
| **Kiểm thử khám phá** | Tìm những câu hỏi/hành vi chưa được mã hóa; đánh giá trải nghiệm và rủi ro | Cần mục tiêu, kỹ năng, dữ liệu, ghi chú và debrief |
| **Kiểm thử sau phát hành/quan sát** | Phát hiện tình huống thực về tải, thiết bị, dữ liệu và sử dụng | Không thay thế kiểm tra phòng ngừa hay cho phép thử nghiệm nguy hiểm trên người dùng |

### Test pyramid là heuristic, không phải luật về phần trăm

Nhiều nhóm sử dụng **test pyramid**: nhiều bài kiểm tra nhanh ở cấp thấp, ít bài E2E hơn vì tốc độ và chi phí duy trì. Nhưng không có tỷ lệ “70% unit, 20% integration, 10% UI” bắt buộc cho mọi sản phẩm.

Một dịch vụ xử lý quy tắc thuần có thể phù hợp với nhiều unit tests; một hệ thống có nhiều giao tiếp và rủi ro cấu hình cần integration/contract tests mạnh. **Chọn cấp kiểm tra dựa trên loại lỗi cần phát hiện, tốc độ phản hồi và độ tin cậy của bằng chứng**, không theo tỷ lệ mặc định.

### Đừng “dịch” mọi ca kiểm thử khám phá thành E2E

Khi phát hiện lỗi do quy tắc chọn checkpoint, test hồi quy tốt nhất có thể là **unit test** ở domain service. Nếu lỗi do transaction hoặc tương tác dữ liệu, cần **integration test**. Chỉ giữ E2E khi muốn bảo vệ hành trình xuyên hệ thống. Tự động hóa ở cấp thấp nhất vẫn **kiểm chứng đúng rủi ro**, không tự động hóa ở UI chỉ vì lỗi được tìm thấy qua UI.

## 7. Viết test charter để việc khám phá có mục tiêu

**Test charter** là định hướng ngắn cho một phiên khám phá, không phải một danh sách bước cứng. Nó giúp người thực hiện tự do thiết kế phép thử mà vẫn biết **đang tìm điều gì**.

### Mẫu charter có thể sử dụng ngay

~~~text
CHARTER ID / PHIÊN BẢN:
  Tên tính năng, build/digest, môi trường thử.

MISSION:
  Điều gì cần khám phá và vì sao?

SCOPE:
  Luồng, đối tượng người dùng, hệ thống và trạng thái cần xem.

RISKS / HYPOTHESES:
  Những sai lệch hoặc điều chưa biết có hậu quả đáng kể.

TEST DATA & ACCESS:
  Dữ liệu mô phỏng, tài khoản thử, quyền hợp lệ,
  cách dọn dẹp và bảo vệ thông tin.

HEURISTICS / EXPERIMENTS:
  Các biến thể dữ liệu, trạng thái, thời gian, thiết bị, môi trường.

TIMEBOX & PARTICIPANTS:
  Ví dụ 40 phút; người thực hiện và người có thể trao đổi.

ORACLES & EVIDENCE:
  Dựa vào quy tắc nào biết đúng/sai?
  Ghi log/timestamp/video nếu được phép và cần thiết.

DEBRIEF & NEXT ACTIONS:
  Lỗi, câu hỏi, giả định mới, rủi ro chưa phủ,
  test hồi quy đề xuất, ai quyết định tiếp.
~~~

**Oracle** trong kiểm thử là nguồn hoặc nguyên tắc giúp đánh giá kết quả, ví dụ acceptance criteria, quy tắc nghiệp vụ, mô hình trạng thái, tài liệu bảo mật hoặc so sánh với hành vi đã được công nhận. Nếu không có oracle rõ, phát hiện vẫn có thể là vấn đề đáng tìm hiểu, nhưng cần trao đổi để tránh báo lỗi dựa trên suy đoán.

### Charter ví dụ: học tiếp khi phiên và kết nối thay đổi

> **Mission:** Tìm rủi ro mở sai bài hoặc mất checkpoint khi học viên chuyển tab, mất kết nối rồi đăng nhập lại.  
> **Scope:** Tài khoản học viên thử, khóa học K, bài B/C, web trên trình duyệt hỗ trợ; không dùng dữ liệu thật.  
> **Giả thuyết:** Request lưu chậm có thể ghi đè tiến độ mới; UI có thể báo “đã lưu” dù request thất bại.  
> **Timebox:** 45 phút, có Developer hỗ trợ kiểm tra log/trace nếu phát hiện bất thường.  
> **Oracle:** Quy tắc chọn checkpoint, không truy cập sai tài khoản, không báo lưu thành công giả.  
> **Bằng chứng:** Chuỗi thao tác, thời gian và trạng thái mạng, request IDs đã khử thông tin nhạy cảm, kết quả backend.  
> **Debrief:** Lỗi có thể tái hiện, câu hỏi về chính sách xung đột và ứng viên kiểm thử hồi quy.

Charter này **không bắt buộc** người thực hiện phải thử đúng một chuỗi thao tác. Nếu xuất hiện dấu hiệu session expiry, người thực hiện có thể dành một phần phiên để điều tra theo rủi ro mới.

## 8. Một phiên kiểm thử khám phá: chuẩn bị, thực hiện, debrief

Các nhóm có thể sử dụng kỹ thuật **session-based test management (SBTM)** để timebox phiên khám phá và lưu kết quả. Đây là một cách hỗ trợ quản lý, **không phải nghi thức bắt buộc** cho mọi nhóm.

### Trước phiên

1. Chọn charter có **rủi ro ưu tiên**, không chỉ “test màn hình mới”.
2. Xác nhận phiên bản phần mềm, môi trường, feature flags và cấu hình.
3. Chuẩn bị dữ liệu và tài khoản thử với các trạng thái cụ thể.
4. Biết cách ghi bằng chứng **không làm lộ dữ liệu cá nhân**.
5. Có người biết nghiệp vụ hoặc kỹ thuật để trao đổi khi gặp kết quả mơ hồ.

### Trong phiên

- Bắt đầu từ một luồng hợp lệ để hiểu trạng thái bình thường.
- Thay từng biến quan trọng: quyền, dữ liệu, thời điểm, thiết bị, trạng thái bài, mạng.
- Quan sát **cả giao diện và hệ thống phía sau**, không chỉ văn bản hiển thị.
- Nếu kết quả lạ xuất hiện, **dừng ghi lại bối cảnh và dữ liệu tái hiện**, sau đó thử thay đổi một điều kiện để thu hẹp nguyên nhân.
- Phân biệt **lỗi**, **giả định chưa rõ** và **ý tưởng cải tiến**.
- Khi phát hiện nghiêm trọng như rò rỉ dữ liệu hoặc mất tiến độ, thông báo ngay theo chính sách; không đợi hết timebox.

### Sau phiên: debrief

Một cuộc debrief ngắn có thể hỏi:

| Câu hỏi | Kết quả cần ghi |
| --- | --- |
| Chúng ta đã học được gì? | Hành vi mới thấy, những giả định được xác nhận/bác bỏ |
| Có lỗi nào tái hiện được? | Bước, dữ liệu, kỳ vọng, kết quả thực, mức ảnh hưởng |
| Điều gì còn chưa biết? | Vùng chưa thử, rủi ro chưa có oracle, phụ thuộc |
| Cần làm rõ với ai? | Product Owner, domain expert, Developers, bảo mật, vận hành |
| Điều gì nên tự động hóa? | Quy tắc ổn định, lỗi hồi quy có thể tái hiện, cấp test phù hợp |
| Có cần sửa backlog/Definition of Done? | Chính sách chất lượng và ưu tiên thực tế thay đổi gì |

### Báo cáo một phiên ≠ đánh giá năng suất cá nhân

Số bug mỗi giờ hoặc số charter hoàn tất không phản ánh đầy đủ chất lượng của tư duy kiểm thử. Một phiên có thể **bác bỏ một rủi ro lớn bằng bằng chứng tốt** mà không tạo bug nào. Một phiên khác tìm lỗi nghiêm trọng trong vài phút. Đánh giá theo **thông tin hữu ích và quyết định tốt hơn**, không chỉ số thẻ bug.

## 9. Heuristic khám phá: thay đổi có phương pháp

Heuristic là **gợi ý tìm tình huống đáng thử**, không phải danh sách tất cả lỗi có thể xảy ra. Người thử lựa chọn dựa trên đặc điểm sản phẩm.

### 9.1. Hành trình và thứ tự thao tác

- Đi đúng luồng chính, rồi bỏ qua hoặc quay lại một bước.
- Dùng Back/Forward, refresh, mở deep link, mở cùng tính năng từ thông báo.
- Bấm hai lần, nhấn liên tiếp, đóng tab giữa thao tác.
- Đổi khóa học hoặc đổi bài ngay trước/ sau khi lưu checkpoint.
- Thực hiện hành động ở thứ tự không thường thấy.

### 9.2. Trạng thái và vòng đời dữ liệu

- Chưa có checkpoint, đang học, đã hoàn thành, đã xóa bài.
- Quyền học sắp hết, vừa hết hoặc được cấp lại.
- Dữ liệu cũ sau migration, dữ liệu bị trùng hoặc thiếu trường tùy chọn.
- Cùng tài khoản đăng nhập nhiều thiết bị hoặc hai tab.
- Cache chứa trạng thái không còn hợp lệ.

### 9.3. Ranh giới và đầu vào

- Vị trí học bằng 0, đúng độ dài video, âm, vượt thời lượng.
- Khóa học có 1 bài, rất nhiều bài hoặc không có bài hợp lệ.
- Tên bài dài, Unicode, ký tự đặc biệt; định dạng ngày/giờ theo múi giờ.
- Thay đổi giá trị ở ranh giới của quyền truy cập hoặc quy tắc hoàn thành.
- Phân biệt dữ liệu thiếu với dữ liệu rỗng và dữ liệu không hợp lệ.

### 9.4. Thời gian, kết nối và đồng thời

- Mạng chậm, ngắt đúng lúc gửi request, kết nối lại.
- Retry, duplicate request, response tới không theo thứ tự.
- Token hết hạn trong khi trình phát đang chạy.
- Đồng hồ client lệch, thay đổi múi giờ hoặc thời điểm qua nửa đêm.
- Nhiều thao tác cùng cập nhật một bản ghi theo những phiên bản khác nhau.

### 9.5. Người dùng và quyền truy cập

- Học viên chưa đăng nhập, đăng nhập lại hoặc đổi tài khoản.
- Có quyền khóa học A nhưng không có quyền khóa học B.
- Vai trò học viên, giảng viên, quản trị; truy cập theo API trực tiếp.
- Thử ID tài nguyên khác, cookie/session cũ hoặc URL chia sẻ.
- Kiểm tra **authorization tại server**, không dựa trên nút đã bị ẩn ở UI.

### 9.6. Khả dụng và accessibility

- Màn hình nhỏ, phóng to chữ, tương phản màu, chuyển chế độ sáng/tối.
- Chỉ dùng bàn phím, vị trí focus, thứ tự tab, nhãn cho trình đọc màn hình.
- Trạng thái loading, lỗi, retry và các thông báo có dễ hiểu không?
- Người dùng không biết thuật ngữ kỹ thuật như checkpoint có hiểu được hành vi không?
- Giao diện hoạt động với tốc độ mạng và thiết bị trong phạm vi hỗ trợ không?

**Không thử bằng thông tin cá nhân thật hoặc truy cập trái phép.** Các phép thử bảo mật và phân quyền phải nằm trong **môi trường được cấp quyền, dữ liệu giả lập và phạm vi thử nghiệm được phê duyệt**.

## 10. Lựa chọn điều nên tự động hóa

Không phải trường hợp nào con người vừa khám phá cũng đáng đưa thành test tự động. Một quyết định tốt phải xét **khả năng lặp lại, rủi ro, giá trị phản hồi, chi phí viết/chạy/bảo trì, oracle và cấp kiểm thử phù hợp**.

### Ứng viên tốt cho kiểm thử tự động

- Quy tắc nghiệp vụ **rõ và quan trọng**, chẳng hạn không mở bài khi không có quyền.
- Lỗi đã tái hiện và có khả năng **tái xuất** qua thay đổi tương lai.
- Các điều kiện ranh giới có thể sinh nhiều dữ liệu đầu vào.
- Hợp đồng API hoặc schema được nhiều consumer sử dụng.
- Luồng cốt lõi phải hoạt động sau mỗi lần triển khai.
- Những kiểm tra thủ công lặp đi lặp lại, tốn công nhưng có oracle rõ.
- Những kiểm tra an toàn cần chạy đều đặn trên nhiều phiên bản.

### Trường hợp thường cần giữ khám phá của con người

- Khả dụng, mức dễ hiểu, hành vi bất ngờ trong hành trình người dùng.
- Kỳ vọng nghiệp vụ chưa thống nhất.
- Rủi ro mới chưa biết phải mã hóa thành điều kiện kiểm tra nào.
- Tình huống nhiều yếu tố cần người thực hiện điều chỉnh giả thuyết liên tục.
- Đánh giá trải nghiệm và chất lượng mang nhiều yếu tố ngữ cảnh.

**Không nên dùng “khó tự động hóa” làm lý do bỏ qua rủi ro.** Có thể kết hợp: dùng automation thiết lập trạng thái/dữ liệu, rồi dành thời gian con người cho phần quan sát và học hỏi; sau phiên, chỉ tự động hóa những điều đã rõ và có giá trị hồi quy.

### Ma trận quyết định

| Tình huống | Ưu tiên cách kiểm tra | Lý do |
| --- | --- | --- |
| Quy tắc chọn bài chưa học khi checkpoint đã hoàn thành | **Unit/domain tests** + vài ví dụ nghiệp vụ | Quy tắc ổn định, cần kiểm tra nhiều biến thể nhanh |
| Truy cập tiến độ tài khoản khác bằng API | **API/integration security tests** + khám phá theo vai trò | Phân quyền có oracle bắt buộc và nhiều đường tấn công |
| Hai tab ghi tiến độ gần đồng thời | **Concurrency/integration tests** + phiên khám phá mạng và UI | Cần kiểm chứng kỹ thuật cùng hành vi người dùng |
| Nút “Học tiếp” có dễ tìm không? | **Khám phá khả dụng/nghiên cứu người dùng** + một ít accessibility checks tự động | Sự hiện diện DOM không chứng minh người dùng hiểu |
| UI chính không mở được sau deploy | **E2E smoke tự động** | Hành trình quan trọng, cần tín hiệu nhanh |
| Lỗi hiếm trong dữ liệu migration | **Integration/migration tests** + exploratory sampling có mục tiêu | Có rủi ro dữ liệu và không thể chỉ dùng vài happy-path examples |
| Hệ thống hoạt động khi mạng chuyển offline/online | **Fault-injection tests có kiểm soát** + khám phá trạng thái và thông báo | Vừa có điều kiện kỹ thuật vừa có trải nghiệm khó đo bằng assertion đơn giản |

## 11. Chuyển user story thành ví dụ có thể kiểm chứng

**User story:**

> “Là học viên đang học một khóa, tôi muốn nhấn ‘Học tiếp’ để mở lại đúng bài đang dở mà không phải tìm thủ công.”

Đây là **lời mời trao đổi** về hành vi, không phải đặc tả đầy đủ. Product Owner, Developers và người kiểm thử cần làm rõ các quy tắc:

- Người dùng phải đăng nhập và còn quyền học.
- Nếu có checkpoint hợp lệ, mở đúng bài và vị trí được phép.
- Nếu chưa có checkpoint, hiển thị hành động bắt đầu hợp lệ.
- Nếu checkpoint đã cũ hoặc bài bị xóa, không tự động mở nội dung không còn hợp lệ.
- Nếu yêu cầu lưu thất bại, không thông báo “đã lưu” sai.
- Không đọc hoặc sửa tiến độ của tài khoản khác.

### Ví dụ BDD/Gherkin

~~~gherkin
Feature: Tiếp tục bài đang học

  Scenario: Mở lại vị trí hợp lệ
    Given học viên A đã đăng nhập và có quyền vào khóa học K
      And A có checkpoint hợp lệ tại bài B ở vị trí 120 giây
    When A chọn "Học tiếp" từ trang khóa học K
    Then hệ thống mở bài B tại vị trí 120 giây
      And chỉ sử dụng dữ liệu tiến độ thuộc A

  Scenario: Không còn quyền học
    Given học viên A không còn quyền truy cập khóa học K
      And A từng có checkpoint trong khóa học K
    When A yêu cầu mở lại bài B
    Then hệ thống không trả nội dung được bảo vệ của bài B
      And hiển thị kết quả từ chối truy cập phù hợp

  Scenario: Chưa có tiến độ
    Given học viên A có quyền vào khóa học K
      And chưa có checkpoint cho khóa học K
    When A mở trang khóa học K
    Then hệ thống gợi ý hành động bắt đầu tại bài hợp lệ theo quy tắc
~~~

Các kịch bản này là **ví dụ đã biết** phù hợp để tự động hóa ở cấp thích hợp. Kiểm thử khám phá tiếp tục hỏi:

> “Điều gì xảy ra nếu A có checkpoint từ khóa học bị thu hồi, nhưng cache của trình duyệt vẫn hiển thị nút? Nếu A chuyển tài khoản ngay khi request đang chạy? Nếu vị trí đã lưu vượt thời lượng hiện tại do bài học bị chỉnh sửa?”

Một câu hỏi có thể được chuyển thành acceptance criteria mới hoặc bug hồi quy **sau khi quy tắc được làm rõ**. Không nên viết assertion dựa trên một quyết định nghiệp vụ tự suy đoán.

## 12. Ví dụ Java: tự động kiểm tra một quy tắc ở cấp unit

Giả sử miền nghiệp vụ quy định: **vị trí học phải nằm trong khoảng từ 0 đến thời lượng bài, tính bằng giây**. Một kiểm tra cấp unit cho giá trị ranh giới có thể đơn giản và nhanh.

~~~java
// Ví dụ minh họa JUnit 5 cho logic nghiệp vụ tự chứa
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

final class CheckpointValidator {
    boolean isValid(long positionSeconds, long durationSeconds) {
        return durationSeconds > 0
                && positionSeconds >= 0
                && positionSeconds <= durationSeconds;
    }
}

class CheckpointValidatorTest {
    private final CheckpointValidator validator = new CheckpointValidator();

    @Test
    void acceptsBeginningAndEndBoundary() {
        assertTrue(validator.isValid(0, 300));
        assertTrue(validator.isValid(300, 300));
    }

    @Test
    void rejectsNegativeAndOutOfRangePositions() {
        assertFalse(validator.isValid(-1, 300));
        assertFalse(validator.isValid(301, 300));
    }

    @Test
    void rejectsInvalidLessonDuration() {
        assertFalse(validator.isValid(0, 0));
        assertFalse(validator.isValid(10, -2));
    }
}
~~~

Đoạn mã minh họa **một quy tắc giả định**. Trong sản phẩm thực, cần hỏi domain expert liệu vị trí đúng cuối video có được lưu là “300 giây” hay phải chuyển trạng thái sang “hoàn thành”; phép kiểm tra không nên tự quyết định quy tắc thay nghiệp vụ.

Đơn vị kiểm thử này **không chứng minh** API bảo mật đúng, dữ liệu được commit xuống storage, nhiều request đồng thời an toàn hoặc UI hiển thị hữu ích. Nó bảo vệ một quy tắc rõ ràng để Developers có thể refactor mà ít sợ lỗi hồi quy.

### Từ phiên khám phá sang unit test

Nếu một phiên khám phá phát hiện giá trị vị trí âm trong bản ghi cũ làm trình phát lỗi, Developers cần:

1. Xác minh trường hợp và quy tắc mong muốn: từ chối, sửa dữ liệu hay khôi phục về điểm an toàn.
2. Viết kiểm tra ở cấp nhỏ nhất phản ánh quyết định đã chốt.
3. Sửa logic và kiểm tra lại đường đi end-to-end nếu cần.
4. Cập nhật phạm vi khám phá cho các trường dữ liệu tương tự.

**Không chỉ chép lại các bước bấm UI** nếu nguyên nhân và điều kiện đúng nằm ở logic miền.

## 13. API, integration và end-to-end: đặt kiểm tra ở đâu?

Một lỗi được phát hiện trên trình duyệt có thể nằm ở nhiều lớp. Chọn cấp kiểm tra thích hợp giúp **phản hồi nhanh và dễ chẩn đoán**.

| Lỗi/rủi ro | Cấp kiểm tra ưu tiên | Vì sao? |
| --- | --- | --- |
| Thuật toán chọn checkpoint sai với bài đã hoàn tất | Unit/domain | Có thể kiểm tra nhiều biến thể, độc lập hạ tầng |
| API trả tiến độ của tài khoản khác | API/integration security | Phải kiểm tra authorization server-side với dữ liệu và danh tính thật của môi trường thử |
| Hai request ghi checkpoint bị đảo thứ tự | Integration/concurrency | Cần database/transaction hoặc cơ chế versioning thật để kiểm chứng |
| Consumer mới không đọc được response API | Contract + integration | Xác minh tương thích schema và hành vi giao tiếp |
| Giao diện hiển thị “đã lưu” trước khi server xác nhận | Component/UI + E2E trọng yếu | Cần kiểm tra trạng thái bất đồng bộ và luồng người dùng |
| Từ trang khóa học không thể mở bài dù API hoạt động | E2E smoke | Bảo vệ kết nối những thành phần chính trong hành trình |

### Ví dụ API test dạng giả mã

~~~text
SETUP:
  Tạo tài khoản A và B hợp lệ trong môi trường thử.
  Chỉ A có checkpoint P ở khóa học K.

ACT:
  Đăng nhập bằng token của B.
  Gọi GET /courses/K/continue với tham số chỉ đến P.

ASSERT:
  Server từ chối truy cập trái quyền theo contract.
  Response không tiết lộ checkpoint hoặc nội dung riêng của A.
  Không có thay đổi dữ liệu của A/B do request bị từ chối.

CLEANUP:
  Thu hồi token thử, dọn dữ liệu theo chính sách.
~~~

**Đây là kiểm tra an toàn có kiểm soát**. Không dùng tài khoản hoặc dữ liệu cá nhân của người dùng thật nếu chưa có quyền và quy trình bảo vệ phù hợp.

### Khi nào cần UI E2E?

Một số hành trình người dùng quan trọng đáng có **một ít kiểm tra end-to-end ổn định**, ví dụ học viên mở trang khóa học và thực sự tiếp tục bài. Nhưng nếu mỗi quy tắc dữ liệu đều được kiểm tra qua E2E, suite dễ chậm và khó bảo trì. Hãy phân tách: **quy tắc ở unit/API, tích hợp ở integration/contract, hành trình cốt lõi ở E2E**.

## 14. Kịch bản kiểm thử khám phá chi tiết cho tính năng “Học tiếp”

Giả sử nhóm có bộ kiểm thử tự động xanh cho kịch bản đăng nhập, lưu checkpoint, mở đúng bài. Mục tiêu phiên khám phá là **tìm nguy cơ mất tiến độ và thông báo sai về trạng thái lưu**.

### Chuẩn bị

- Tài khoản thử learnerA, learnerB với quyền khác nhau; không dùng dữ liệu thật.
- Một khóa học K có bài B và C, checkpoint hợp lệ và một số bản ghi biên đã được tạo an toàn.
- Hai tab trình duyệt và công cụ mô phỏng mạng chậm/ngắt kết nối.
- Khả năng xem trạng thái lưu ở backend và request IDs không chứa bí mật.
- Quy tắc: người học không được mất checkpoint mới hơn do request cũ; khi lưu chưa thành công UI không được báo đã lưu.

### Phiên khám phá minh họa

| Bước | Thao tác / thay đổi biến | Điều quan sát | Câu hỏi mới |
| --- | --- | --- | --- |
| **1** | A mở bài B và lưu vị trí 60 giây | UI và backend nhất quán | Điều gì xảy ra khi hai lần lưu gần nhau? |
| **2** | A mở tab thứ hai, chuyển tới 180 giây | Backend nhận checkpoint mới | Request cũ của tab đầu có thể đến muộn? |
| **3** | Giảm tốc mạng ở tab đầu, gửi checkpoint 90 giây | Một response đến sau response 180 giây | Server dùng chính sách thứ tự hay ghi đè cuối cùng? |
| **4** | Ngắt mạng ngay sau khi UI bắt đầu lưu | UI vẫn có thể hiện trạng thái cũ | Người học có bị báo thành công giả không? |
| **5** | Kết nối lại, refresh trang khóa học | Có thể xuất hiện vị trí khác kỳ vọng | Tài khoản được ưu tiên theo sự kiện hay timestamp nào? |
| **6** | Đổi sang tài khoản B trên cùng trình duyệt | Cache có thể hiển thị dữ liệu cũ | UI/API đã xóa và phân quyền mọi dữ liệu cục bộ chưa? |

Đây là **chuỗi tình huống để học**, không phải khẳng định sản phẩm thật có lỗi. Mỗi bước cần có oracle và dữ liệu quan sát. Khi có hiện tượng lạ, người thử ghi thời điểm, trình duyệt, điều kiện mạng và trạng thái backend để Developers có thể tái hiện.

### Ví dụ một phát hiện có chất lượng

> **Quan sát:** Request lưu vị trí 90 giây từ tab 1 đến server sau request 180 giây từ tab 2; bản ghi cuối cùng quay về 90 giây.  
> **Bằng chứng:** Hai request IDs, thời điểm gửi/nhận và version của checkpoint, chạy trên dữ liệu thử.  
> **Rủi ro:** Học viên có thể mất vị trí mới nhất trong phạm vi hỗ trợ hai tab.  
> **Chưa rõ:** Chính sách đúng là ưu tiên timestamp server, version, hay một mô hình tiến độ khác?  
> **Tiếp theo:** Thống nhất quy tắc với người hiểu nghiệp vụ; bổ sung integration/concurrency regression test, rồi sửa cơ chế ghi có kiểm soát.

Nếu sản phẩm cố ý chỉ hỗ trợ một phiên hoặc có chính sách chọn checkpoint khác, điều cần làm trước là **làm rõ kỳ vọng**. Không ghi lỗi “sai” dựa trên thuật toán mà người thử tự tưởng tượng.

## 15. Từ phát hiện khám phá đến vòng hồi quy tự động

Giá trị của khám phá không dừng ở một bug ticket. Khi có kết quả mới, hãy biến hiểu biết đó thành **quy tắc, test, theo dõi hoặc thay đổi ưu tiên phù hợp**.

~~~mermaid
flowchart TD
    A["Phiên khám phá có mục tiêu"] --> B{"Phát hiện thuộc loại nào?"}
    B -->|Bug với hành vi rõ| C["Tái hiện, xác định oracle<br/>và mức ảnh hưởng"]
    B -->|Quy tắc chưa rõ| D["Trao đổi Product Owner<br/>hoặc domain expert"]
    B -->|Nhu cầu/khả dụng mới| E["Cập nhật Product Backlog<br/>và giả thuyết giá trị"]
    C --> F["Chọn cấp regression test<br/>nhỏ nhất phù hợp"]
    D --> F
    F --> G["Viết kiểm tra tự động<br/>và sửa sản phẩm"]
    G --> H["CI chạy lại thường xuyên"]
    H --> I["Khám phá những vùng<br/>rủi ro chưa biết tiếp theo"]
    E --> I
~~~

### Quy trình quyết định sau một phát hiện

1. **Tái hiện và khoanh phạm vi:** lỗi có xảy ra nhiều lần không; môi trường/phiên bản nào?
2. **Kiểm tra oracle:** đã có quy tắc xác định đúng/sai chưa; cần người nghiệp vụ quyết định gì?
3. **Đánh giá ảnh hưởng:** dữ liệu, quyền riêng tư, tài chính, khả dụng hay chỉ thẩm mỹ?
4. **Xem có đáng tự động hóa không:** khả năng tái xuất, độ ổn định, chi phí và tốc độ kiểm tra.
5. **Đặt đúng lớp kiểm thử:** unit, API, integration, contract, E2E hoặc một công cụ fault-injection.
6. **Sửa và chứng minh:** chạy test lỗi trước/sau sửa khi có thể, xác nhận hệ thống và các kiểm tra liên quan.
7. **Phòng ngừa:** cập nhật acceptance criteria, Definition of Done, charter hoặc chính sách dữ liệu khi cần.
8. **Tiếp tục khám phá:** tìm các trường hợp cùng nguyên nhân, không dừng ở việc sửa đúng một biểu hiện.

### Khi nào không nên tự động hóa?

Một nhận xét như “nút này có vẻ khó hiểu với người lần đầu dùng” cần được **quan sát và kiểm chứng bằng người dùng**. Có thể tự động hóa kiểm tra nhãn accessible, vùng bấm hoặc trạng thái focus, nhưng không thể kết luận sự hiểu biết của người dùng chỉ bằng một assertion rằng nút tồn tại.

Mục tiêu là tạo **hệ thống học hỏi lũy tiến**: kiểm tra đã biết chạy nhanh hơn, giải phóng thời gian con người để tìm câu hỏi chưa biết.

## 16. Automation có thể hỗ trợ khám phá, không chỉ chạy regression

Một cách kết hợp rất hiệu quả là **tự động hóa những phần việc lặp lại để con người dành thời gian cho việc quan sát và đặt câu hỏi**. Không cần chọn một trong hai thái cực “mọi thứ đều tự động” hoặc “khám phá là làm thủ công hoàn toàn”.

### Các việc có thể tự động hỗ trợ

| Công cụ / kỹ thuật | Giảm chi phí nào? | Phần con người vẫn cần quyết định |
| --- | --- | --- |
| **Data fixtures / seed scripts** | Tạo tài khoản, khóa học, checkpoint với trạng thái xác định | Kết hợp trạng thái nào có rủi ro đáng điều tra? |
| **API clients / scripts** | Gửi request, thay header, so sánh response nhanh | Dấu hiệu nào là lỗi thực, quy tắc nào cần làm rõ? |
| **Network shaping / fault injection** | Mô phỏng chậm, timeout, ngắt kết nối, retry | Người dùng bị ảnh hưởng thế nào, cần thử tiếp gì? |
| **Property-based tests** | Sinh nhiều đầu vào để kiểm tra bất biến đã biết | Bất biến nào thực sự đúng với nghiệp vụ? |
| **Fuzzing có kiểm soát** | Thăm dò xử lý đầu vào lạ trong phạm vi được phép | Phân tích crash, lỗi và mức ảnh hưởng thực tế |
| **Screenshots / tracing / logs** | Lưu trạng thái và chuỗi sự kiện để so sánh | Điều gì đáng nghi, bằng chứng đã đủ chưa? |
| **Accessibility scanners** | Tìm nhanh một số vi phạm kỹ thuật phổ biến | Trải nghiệm bàn phím, đọc màn hình và khả năng hiểu có thực sự tốt? |
| **Browser/device matrices** | Lặp các ca đã biết trên nhiều môi trường | Những kết hợp môi trường nào cần khám phá sâu? |

### Ví dụ: tự động khởi tạo dữ liệu rồi khám phá bằng người

~~~text
Script chuẩn bị:
  Tạo học viên A và B, khóa học K có bài B/C.
  A có checkpoint tại B:60, B không có quyền vào K.
  Tạo thêm một checkpoint cũ đã được đánh dấu.
  Bật ghi log thử nghiệm đã loại bỏ thông tin nhạy cảm.

Người thực hiện:
  Thử hai tab, thay đổi tốc độ mạng, đăng xuất rồi đăng nhập.
  Quan sát UI, API và dữ liệu sau từng chuỗi hành động.
  Thay hướng khám phá nếu phát hiện điều bất thường.

Script dọn dẹp:
  Xóa dữ liệu thử đúng phạm vi và thu hồi quyền thử.
~~~

Automation ở đây **không thay phần tư duy khám phá**; nó giảm thời gian chuẩn bị và tăng khả năng tái hiện. Khi thấy lỗi, script còn giúp dựng lại trạng thái khởi đầu để kiểm chứng nguyên nhân.

## 17. Đưa kiểm tra tự động và khám phá vào vòng CI/CD

**CI** có thể tự động chạy kiểm tra mỗi khi thay đổi được tích hợp; **Continuous Delivery** giúp phần mềm được kiểm chứng và sẵn sàng đưa tới môi trường đích khi cần. Kiểm thử khám phá nên được bố trí theo **rủi ro và thời điểm có thông tin hữu ích**, không phải thành một “cổng người” mặc định kiểm tra lại toàn bộ sau mọi commit.

### Một chiến lược phân tầng

~~~mermaid
flowchart TD
    A["Story + ví dụ nghiệp vụ<br/>và rủi ro"] --> B["Developers xây lát cắt nhỏ"]
    B --> C["CI: unit/component<br/>static/security checks"]
    C --> D{"Checks đạt?"}
    D -->|Không| E["Sửa và chạy lại"]
    E --> B
    D -->|Có| F["Integration/contract<br/>và E2E thiết yếu"]
    F --> G["Build có thể dùng để thử"]
    G --> H["Khám phá theo charter<br/>và rủi ro chưa biết"]
    H --> I{"Học được gì?"}
    I -->|Defect hoặc rule mới| J["Trao đổi, sửa và thêm<br/>regression check phù hợp"]
    J --> B
    I -->|Đủ bằng chứng cho phạm vi| K["Đánh giá Definition of Done<br/>và điều kiện release"]
    K --> L["Triển khai/phát hành an toàn<br/>với monitoring"]
    L --> M["Phản hồi production<br/>và Product Backlog"]
    M -.-> A
~~~

Sơ đồ chỉ là một **vòng phản hồi điển hình**, không bắt buộc mọi phiên khám phá phải chờ hết pipeline hay mọi thay đổi đều phải tổ chức họp thủ công. Có thể khám phá **trước khi code** bằng prototype và ví dụ nghiệp vụ, **trong khi code** trên lát cắt đang hoạt động và **sau khi code** trên bản tích hợp.

### Những việc nên xảy ra sớm

- Khi refinement: Product Owner, Developers và người kiểm thử nêu các giả định và rủi ro chất lượng.
- Khi thiết kế: review ví dụ nghiệp vụ và test charters cho hành vi chưa rõ.
- Khi lập trình: unit/API tests cho quy tắc đã biết, pairing và test-first khi phù hợp.
- Khi tích hợp: contract/integration tests và khám phá hành vi bất ngờ ở luồng đầu-cuối.
- Trước phát hành: đánh giá rủi ro còn lại, những kiểm tra bắt buộc, độ tin cậy của dữ liệu, khả năng quan sát và phương án xử lý.
- Sau phát hành: quan sát lỗi thực, tiếp xúc người dùng và cập nhật backlog.

**Không mặc định rằng một “test phase” cuối Sprint phải gánh toàn bộ chất lượng.** Tính liên tục có nghĩa học và sửa sớm, không dồn lỗi tới một người hoặc một tuần cuối.

### Một ví dụ pipeline giả lập

~~~yaml
# MÔ HÌNH MINH HỌA, KHÔNG PHẢI CẤU HÌNH CI CÓ THỂ CHẠY NGAY
on_change:
  - build
  - static_checks
  - unit_tests
  - security_and_dependency_checks
  - component_and_contract_tests

before_release_candidate:
  - deploy_to_controlled_test_environment
  - integration_tests
  - critical_end_to_end_smoke_tests
  - collect_test_evidence
  - evaluate_mandatory_quality_and_risk_policies

after_safe_deployment:
  - production_health_and_business_guardrails
  - monitor_for_regression
  - feed_findings_into_product_and_quality_backlogs
~~~

Kiểm thử khám phá **có thể diễn ra song song** với pipeline và được kích hoạt theo rủi ro; nó không biến thành bước tự động chỉ vì được nêu trong một định nghĩa quy trình.

## 18. Dữ liệu và môi trường thử: điều kiện để có bằng chứng đáng tin

Kiểm thử tốt không thể chỉ dựa vào **một tài khoản mẫu sạch và một database trống**. Sản phẩm thật có dữ liệu cũ, quyền thay đổi, cache, bản ghi trùng, lịch sử nhiều năm và thao tác đồng thời. Nhưng đưa dữ liệu thật thiếu kiểm soát vào môi trường thử lại có nguy cơ riêng tư.

### Chính sách dữ liệu thử có trách nhiệm

| Nhu cầu | Cách làm phù hợp |
| --- | --- |
| **Trạng thái rõ ràng** | Tạo fixtures mô tả học viên, bài học, checkpoint và quyền có thể tái tạo |
| **Độc lập giữa tests** | Dữ liệu được cách ly, reset/dọn dẹp để tests không vô tình ảnh hưởng lẫn nhau |
| **Dữ liệu biên** | Có bản ghi cũ, thiếu trường, trùng, giới hạn và trạng thái kết hợp theo rủi ro |
| **Tương tự production** | Tái hiện những đặc trưng cấu trúc/khối lượng cần thiết bằng dữ liệu tổng hợp hoặc đã được xử lý an toàn |
| **Quyền truy cập** | Test role khác nhau bằng tài khoản được cấp phép, không tái sử dụng token production |
| **Bảo vệ bí mật** | Không hardcode credential, không ghi dữ liệu nhạy cảm vào test log hoặc ảnh chụp |
| **Tính tái hiện** | Ghi phiên bản ứng dụng, schema, feature flags, locale, thời gian và cấu hình quan trọng |

### Dữ liệu giống production không có nghĩa sao chép production

Khi test một lỗi migration, nhóm cần kiểm chứng **hình dạng dữ liệu và các ngoại lệ**; có thể dùng dữ liệu tổng hợp mô phỏng đặc tính quan trọng. Nếu thật sự có nhu cầu sử dụng dữ liệu nhạy cảm, phải có phê duyệt, chính sách an toàn và biện pháp bảo vệ phù hợp, không mặc định tải database thật về máy cá nhân.

### Môi trường “giống production” có giới hạn

Staging có thể không tái tạo đầy đủ tải, độ trễ, tổ hợp trình duyệt hoặc sự bất thường của dữ liệu thật. Do đó:

1. Kiểm tra trước production theo rủi ro với môi trường hợp lý.
2. Với rủi ro chưa thể mô phỏng hết, thiết kế **canary/rollout hạn chế, quan sát và khả năng dừng**.
3. Không sử dụng người dùng làm đối tượng thử nghiệm nguy hiểm khi có thể phòng ngừa bằng test phù hợp.

Kết quả “đã qua staging” là **một bằng chứng**, không phải bảo đảm tuyệt đối.

## 19. Chất lượng của chính bộ kiểm thử tự động

Một test suite kém tin cậy khiến nhóm **không dám đổi mã** hoặc dần phớt lờ tín hiệu lỗi. Cần quản lý chất lượng của tests như quản lý mã production.

### Flaky test

**Flaky test** là bài test có thể pass hoặc fail khi code không thay đổi theo nguyên nhân mà bài test định kiểm chứng. Nguồn gốc có thể là:

- Chờ bằng số giây cứng thay vì điều kiện thực.
- Dùng chung dữ liệu hoặc phụ thuộc thứ tự chạy.
- Race condition, request bất đồng bộ chưa được đồng bộ đúng.
- Môi trường, network hoặc dịch vụ ngoài không ổn định.
- Timestamp, múi giờ hoặc ID ngẫu nhiên không được kiểm soát.
- Assertion quá phụ thuộc vào nội dung giao diện không liên quan đến hành vi cần bảo vệ.

**Không nên chỉ retry đến khi pass rồi bỏ qua.** Retry có thể tạm cho thông tin chẩn đoán, nhưng nếu mọi lỗi thất thường đều bị che bằng chạy lại, pipeline mất ý nghĩa. Cần thu thập bằng chứng, phân loại nguyên nhân, sửa đồng bộ dữ liệu hoặc thiết kế test. Nếu phải cách ly tạm một test, nhóm cần theo dõi rủi ro còn lại và kế hoạch khôi phục, không mặc định bỏ kiểm tra bắt buộc.

### Test coverage có nói lên điều gì?

**Line/branch coverage** cho biết phần mã nào được thực thi khi chạy tests theo cách đo đã chọn; nó **không chứng minh assertion đúng**, yêu cầu nghiệp vụ đã được kiểm tra hay dữ liệu an toàn. Một test chỉ gọi hàm mà không xác nhận kết quả vẫn có thể tăng coverage.

**Mutation testing** có thể đánh giá một phần năng lực phát hiện lỗi của tests bằng cách tạo thay đổi nhỏ có kiểm soát trong mã và xem tests có bắt được không. Đây là công cụ bổ trợ, không phải công thức bảo đảm chất lượng: hiệu quả phụ thuộc loại mutation, phạm vi, chi phí chạy và đặc điểm mã.

### Các tiêu chí đánh giá test có ích

| Tiêu chí | Câu hỏi |
| --- | --- |
| **Ý nghĩa của assertion** | Test có bảo vệ một quy tắc/rủi ro đáng quan tâm không? |
| **Độ tin cậy** | Kết quả có ổn định khi điều kiện không đổi không? |
| **Thời gian phản hồi** | Người sửa mã có nhận tín hiệu đủ nhanh để hành động không? |
| **Khả năng chẩn đoán** | Khi fail, log chỉ ra điều sai hay chỉ báo “timeout”? |
| **Chi phí bảo trì** | Test có phụ thuộc quá chặt vào chi tiết giao diện không cần thiết không? |
| **Độ bao phủ rủi ro** | Test có chạm các trường hợp nghiêm trọng, không chỉ happy path không? |
| **Khả năng tái hiện** | Dữ liệu và phiên bản có được kiểm soát đủ không? |

Chạy 10.000 tests yếu không tự tốt hơn 1.000 tests nhắm đúng rủi ro. **Tối ưu chất lượng phản hồi, không tối ưu số lượng bài test.**

## 20. Khám phá khả dụng, accessibility và trải nghiệm người dùng

Một giao diện có thể **đúng chức năng** nhưng không **dễ dùng**. Automation có thể kiểm tra một số quy tắc khả dụng kỹ thuật, còn người dùng và người thử nghiệm có thể phát hiện sự khó hiểu không được diễn đạt bằng assertion đơn giản.

### Ví dụ khám phá nút “Học tiếp”

| Khía cạnh | Kiểm tra tự động có thể làm | Khám phá/quan sát cần bổ sung |
| --- | --- | --- |
| **Nút tồn tại** | Test DOM/component xác nhận hiển thị với người có quyền | Người dùng có nhìn thấy nút khi tìm bài không? |
| **Nhãn accessible** | Kiểm tra tên truy cập và role của phần tử | Người dùng trình đọc màn hình hiểu nút mở tới đâu không? |
| **Bàn phím** | Một số E2E có thể xác nhận tab/focus và kích hoạt | Thứ tự focus có thực tế và dễ theo dõi không? |
| **Thông báo lỗi** | Xác nhận có error state khi API fail | Nội dung thông báo có giúp người học biết phải làm gì? |
| **Mobile layout** | Kiểm tra responsive, lỗi overflow điển hình | Nút có nằm ở vị trí thuận tiện trong hành trình thực không? |
| **Tiến độ đang lưu** | UI tests xác minh các state loading/saved/error | Người học có hiểu sự khác nhau, có lo mất dữ liệu không? |

### Khám phá accessibility có mục tiêu

Một charter có thể yêu cầu:

> “Khám phá hành trình quay lại bài đang học bằng **chỉ bàn phím và trình đọc màn hình trong phạm vi hỗ trợ**. Tìm vị trí focus bị mất, nhãn không mô tả hành động, thông báo trạng thái lưu không được công bố và khả năng kẹt trong dialog.”

Các công cụ kiểm tra accessibility tự động có thể phát hiện **một phần lỗi theo quy tắc**, nhưng không thay toàn bộ tương tác bằng thiết bị trợ năng và sự hiểu của người dùng. Khi cần đánh giá phù hợp một tiêu chuẩn như WCAG, nhóm phải xem **tiêu chí áp dụng và phương pháp kiểm tra phù hợp**, không dựa duy nhất vào số lỗi scanner.

### Phản hồi người dùng không giống kiểm thử kỹ thuật

Nếu ba học viên thử không tìm thấy nút, đó là **tín hiệu định tính cần điều tra**, không tự chứng minh tỷ lệ người dùng toàn sản phẩm là bao nhiêu. Nhóm có thể sửa thiết kế theo bằng chứng phù hợp, rồi tiếp tục theo dõi hành vi trên nhóm người dùng rộng hơn khi an toàn.

## 21. Bảo mật, hiệu năng và khả năng phục hồi cần cả kiểm tra lẫn khám phá

Không nên thu hẹp “chất lượng liên tục” thành logic chức năng. Những đặc tính phi chức năng có thể gây hậu quả lớn ngay cả khi mọi user story đều có nút hoạt động.

| Thuộc tính | Kiểm tra tự động | Hướng khám phá bổ sung |
| --- | --- | --- |
| **Security/authorization** | Test kiểm soát quyền, dependency scan, static checks, API contracts | Thử chuỗi trạng thái xác thực/phiên, cache, URL trực tiếp trong phạm vi được phép |
| **Performance** | Load/latency checks với dữ liệu và tải mô phỏng phù hợp | Quan sát luồng trên thiết bị yếu, mạng chậm, dữ liệu lớn và thao tác người dùng |
| **Reliability** | Chaos/fault injection có kiểm soát, retry/idempotency tests, health checks | Khám phá sự cố xảy ra đúng thời điểm chuyển trạng thái hoặc nhiều hành động gần nhau |
| **Data integrity** | Migration/concurrency/integration tests | So sánh dữ liệu trước/sau lỗi, thử bản ghi cũ và trạng thái mâu thuẫn |
| **Accessibility** | Scanner, component checks và E2E bàn phím đã biết | Đánh giá với thiết bị trợ năng, người dùng phù hợp, khả năng hiểu |
| **Observability** | Kiểm tra log/metric/tracing có tín hiệu quan trọng | Điều tra xem nhóm có đủ thông tin để hiểu lỗi bất ngờ không |

### Không thử nghiệm nguy hiểm ngoài phạm vi được cho phép

Exploratory testing có thể chạm vào security hoặc khả năng phục hồi, nhưng **phạm vi quyền hạn, môi trường và dữ liệu** phải rõ ràng. Không chạy stress test hoặc fault injection lên production khi chưa có quy trình kiểm soát thích hợp; không khai thác dữ liệu khách hàng thật để chứng minh thiếu phân quyền.

### Kiểm tra độ an toàn của đường lỗi

Với “Học tiếp”, khi dịch vụ tiến độ không khả dụng, sản phẩm có thể cần:

1. Không báo “đã lưu” nếu chưa có xác nhận phù hợp.
2. Không trả checkpoint thuộc tài khoản khác.
3. Giải thích được trạng thái chưa lưu/chờ thử lại theo phạm vi hỗ trợ.
4. Tránh retry gây ghi đè sai.
5. Có log/metric cho sự cố mà không lưu dữ liệu nhạy cảm quá mức.

Đây là ví dụ về **kỳ vọng cần được làm rõ với người chịu trách nhiệm sản phẩm và kỹ thuật** trước khi viết mọi assertion. Người thử khám phá các điều kiện làm kỳ vọng ấy trở nên mong manh.

## 22. Vai trò của cả nhóm trong chất lượng liên tục

Chất lượng không nên bị chuyển thành trách nhiệm cuối cùng của một nhóm “QA” đứng riêng. Người có chuyên môn kiểm thử rất quan trọng, nhưng **khả năng tạo sản phẩm đúng và đáng tin là trách nhiệm hợp tác của cả nhóm phát triển sản phẩm**.

| Người/nhóm tham gia | Đóng góp nổi bật | Điều không nên làm |
| --- | --- | --- |
| **Product Owner / người phụ trách giá trị** | Làm rõ nhu cầu, ưu tiên rủi ro giá trị, lựa chọn outcome và các quy tắc nghiệp vụ | Chỉ giao danh sách chức năng rồi đợi cuối Sprint mới xác nhận điều cần có |
| **Developers** | Thiết kế, viết unit/integration tests, xử lý lỗi, quan sát sản phẩm và làm việc với kiểm thử khám phá | Chuyển tất cả kiểm thử sang một người khác sau khi code “xong” |
| **Test specialist / QA engineer** | Tư duy rủi ro, charters, kỹ thuật khám phá, automation strategy, hỗ trợ điều tra lỗi | Trở thành “cổng duyệt thủ công” duy nhất khiến mọi thay đổi phải chờ |
| **Thiết kế/UX** | Hiểu hành trình và khả dụng; tham gia khám phá vấn đề người dùng | Chỉ đánh giá giao diện qua ảnh tĩnh mà không xem hành vi thật |
| **Vận hành/SRE/bảo mật** | Hệ thống kiểm chứng, reliability, an toàn, log/metrics và xử lý sự cố | Chỉ xuất hiện sau khi production có lỗi |
| **Scrum Master (nếu dùng Scrum)** | Hỗ trợ nhóm cải tiến cách cộng tác và loại bỏ trở ngại hệ thống | Biến số bug từng cá nhân thành công cụ kiểm soát năng suất |

### Kỹ thuật “three amigos”

Một cuộc trao đổi ngắn giữa **người hiểu nghiệp vụ, Developers và người có chuyên môn kiểm thử** có thể:

1. Chọn một user story và giá trị mong muốn.
2. Nêu ví dụ đúng/sai và quy tắc quan trọng.
3. Xác định điều có thể kiểm tra tự động.
4. Nêu giả định cần charter khám phá.
5. Chốt cách xác nhận Done và phản hồi sản phẩm.

“Three amigos” là **mẫu cộng tác**, không phải quy định luôn phải có đúng ba cá nhân hoặc ba chức danh riêng. Trong nhóm nhỏ, một người có thể đóng góp nhiều năng lực nhưng vẫn cần **đa dạng góc nhìn**.

## 23. Kết hợp với Scrum, Kanban và XP

Các framework và thực hành có điểm nhấn riêng, có thể hỗ trợ cùng một mục tiêu chất lượng.

### Scrum: Definition of Done, Sprint Goal và kiểm tra liên tục

Trong Scrum, **Increment phải đáp ứng Definition of Done**. Một Product Backlog Item chưa đạt Definition of Done **không được coi là Increment hoàn tất** dù đã viết mã xong. Scrum không yêu cầu đợi Sprint Review mới được phát hành Increment đạt chuẩn.

Một Sprint hai tuần có thể thực hiện:

- Trong **refinement/Sprint Planning:** làm rõ rủi ro và các ví dụ chấp nhận của PBIs được chọn; dự báo đủ thời gian cho kiểm thử và khám phá quan trọng.
- Trong **Sprint:** Developers liên tục tích hợp, chạy kiểm tra, khám phá các lát cắt nhỏ; khi học thêm quy tắc, trao đổi với Product Owner và cập nhật Sprint Backlog đúng trách nhiệm.
- Ở **Daily Scrum:** xem trở ngại đối với Sprint Goal và Done, không chỉ hỏi “QA đã test xong chưa?”.
- Ở **Sprint Review:** xem Increment thật và phản hồi của bên liên quan, cập nhật Product Backlog.
- Ở **Sprint Retrospective:** học về test suite, việc chờ, phát hiện lỗi muộn và cải tiến cách hợp tác.

**Không giảm Definition of Done để tuyên bố một Sprint thành công.** Nếu rủi ro bắt buộc chưa được kiểm chứng, nhóm phải minh bạch và xem lại phạm vi/dự báo.

### Kanban: quản lý flow của việc kiểm chứng

Một bảng workflow có thể gồm:

~~~text
Ready → Developing → Review/Verify → Done
                   \                /
                    Blocked (đánh dấu trạng thái, không giấu WIP)
~~~

Nếu nhiều story dồn vào Review/Verify, giải pháp không phải chỉ tuyển thêm người kiểm thử hoặc mở thêm story. Nhóm cần xem **WIP, work item age, cycle time và throughput**, chuyển năng lực tới điểm nghẽn, tự động hóa những bước lặp hoặc thay đổi cách làm để kiểm tra xảy ra sớm hơn.

**Blocked vẫn cần được nhìn thấy** trong ranh giới WIP, trừ khi Definition of Workflow có quy tắc khác rõ ràng. Một thẻ gắn nhãn “đang chờ QA” không phải bằng chứng đã đạt Done.

### XP: kiểm thử chủ động và phản hồi kỹ thuật ngắn

XP đóng góp **test-first/TDD, continuous integration, refactoring, pair programming, simple design và small releases**. Các thực hành này tạo nền để tự động hóa kiểm tra hồi quy nhanh và đáng tin. Kiểm thử khám phá bổ sung những câu hỏi và hành vi chưa được mô tả trong tests.

Một vòng có ích:

~~~text
Trao đổi ví dụ nghiệp vụ
  → TDD/kiểm tra tự động cho quy tắc đã biết
  → Lát cắt nhỏ được tích hợp
  → Khám phá rủi ro ở hành vi đầu-cuối
  → Phát hiện/rà giả định
  → Thêm test hồi quy phù hợp và refactor
  → Increment đạt chuẩn, nhận phản hồi người dùng
~~~

**TDD không thay thế exploratory testing**: TDD giúp thiết kế và bảo vệ hành vi mà Developers đã hiểu; khám phá giúp đặt câu hỏi liệu hành vi và mô hình đang được hiểu có đủ hay chưa.

## 24. Chất lượng không phải bước “ký duyệt” sau cùng

Một hệ thống có thể yêu cầu quality gates, nhưng nếu mọi việc đều được đẩy sang cuối Sprint, nhóm sẽ phát hiện lỗi khi chi phí sửa đã cao. Chất lượng liên tục cần **phản hồi nhiều thời điểm**.

| Thời điểm | Điều cần học/kiểm tra | Quyết định có thể đưa ra |
| --- | --- | --- |
| **Trước code** | Nhu cầu, ví dụ, dữ liệu, quy tắc, rủi ro nghiệp vụ | Chia user story, làm rõ acceptance criteria, đổi ưu tiên |
| **Khi code** | Logic, interface, thành phần, kiểm thử tự động nhanh | Sửa/điều chỉnh thiết kế trước khi tích hợp lớn |
| **Khi tích hợp** | Quy tắc xuyên thành phần, dữ liệu, E2E thiết yếu, khám phá | Sửa sai, bổ sung test, điều chỉnh phạm vi |
| **Trước release** | Definition of Done, rủi ro còn lại, rollout/monitoring, chính sách | Go/no-go theo trách nhiệm và điều kiện an toàn |
| **Sau release** | Người dùng thật, lỗi production, dữ liệu outcome | Thử tiếp, cải thiện, rollback/roll-forward, cập nhật backlog |

### Rủi ro còn lại phải minh bạch

Không tồn tại bằng chứng rằng đã kiểm tra hết mọi trường hợp. Một quyết định release có trách nhiệm cần ghi:

- Những hành vi và loại rủi ro đã được kiểm tra bằng gì?
- Vùng nào **chưa đủ bằng chứng**, vì lý do gì?
- Có ràng buộc nào **không được vi phạm**?
- Phạm vi người dùng, khả năng dừng/khôi phục và monitoring có phù hợp rủi ro?
- Ai chịu trách nhiệm quyết định và theo dõi sau phát hành?

**Không dùng “đã khám phá 2 giờ” làm giấy phép phát hành khi một lỗi phân quyền nghiêm trọng vẫn tồn tại.** Thời lượng là dữ liệu về nỗ lực, không phải kết quả chất lượng.

### Tự động hóa cho tốc độ, khám phá cho bất định

Một cách diễn đạt đơn giản:

> “Những điều đã hiểu và cần đúng lặp lại được tự động kiểm tra đủ thường xuyên; những điều chưa hiểu hoặc có rủi ro mới được chủ động khám phá; cả hai tạo bằng chứng cho quyết định giao hàng.”

Đây là phương châm điều hành, **không phải tỷ lệ phân bổ thời gian cứng**.

## 25. Case study: một Sprint hai tuần với chức năng “Học tiếp”

Tình huống dưới đây là **ví dụ giả định để thực hành**, không phải số liệu của một đội phần mềm thực.

### 25.1. Bối cảnh và Sprint Goal

**Product Goal:** Giúp học viên quay lại lộ trình học thuận tiện, tin cậy.

**Sprint Goal:** “Học viên đã đăng nhập và còn quyền học có thể từ trang khóa học tiếp tục đúng bài đang dở trên cùng thiết bị, với dữ liệu tiến độ của mình được bảo vệ.”

Các PBIs đã chọn gồm hành vi đọc/lưu checkpoint hợp lệ, hiển thị hành động “Học tiếp” và những điều kiện đo/giám sát cần thiết. Phần đồng bộ nhiều thiết bị chưa phải khả năng được hứa cho người dùng, nhưng **các rủi ro dữ liệu vẫn phải được quản lý** trong phạm vi phiên hoặc tab mà ứng dụng thực sự hỗ trợ.

### 25.2. Ngày đầu: lập bản đồ kiểm thử

Product Owner, Developers và người kiểm thử cùng làm rõ:

| Quy tắc / rủi ro | Kiểm tra tự động được chọn | Hướng khám phá |
| --- | --- | --- |
| Checkpoint hợp lệ theo thời lượng | Unit tests cho vị trí 0, hợp lệ, vượt biên | Bài bị thay đổi thời lượng hoặc bị xóa |
| Quyền theo tài khoản và Enrollment | API/integration tests với 2 tài khoản | Đổi phiên, deep link, cache khi hết quyền |
| Luồng UI–API mở bài | Một E2E smoke ổn định | Trình duyệt Back/Forward, hai tab, mạng chậm |
| Hiển thị trạng thái lưu | Component tests cho success/error/loading | Ngắt mạng đúng thời điểm, retry, refresh |
| Người học hiểu “Học tiếp” | Accessibility checks cơ bản | Quan sát thao tác trên màn hình nhỏ, đọc màn hình |

Nhóm không bắt đầu bằng cách viết hàng trăm E2E tests trước khi hiểu sản phẩm.

### 25.3. Giữa Sprint: CI xanh, nhưng khám phá thấy rủi ro

Developers đã chạy unit/API tests xanh và một luồng E2E. Một phiên charter về **ngắt kết nối khi lưu** phát hiện UI thông báo “Đã lưu” trước khi server xác nhận.

**Hành động:**

1. Ghi điều kiện mạng, timestamp, response và bằng chứng UI.
2. Trao đổi với Product Owner về thông báo phù hợp và giới hạn hỗ trợ offline.
3. Developers sửa trạng thái bất đồng bộ, chỉ báo thành công sau bằng chứng lưu theo contract.
4. Thêm component/integration regression test cho request thất bại/chậm; giữ một ca E2E quan trọng nếu cần.
5. Kiểm thử khám phá lại tình huống retry, double-click và refresh để tìm tác động liên quan.

Việc sửa không phải “scope creep tùy ý”: **không báo lưu thành công giả** là điều kiện để luồng đang giao đáng tin. Nếu phát hiện ảnh hưởng dự báo, nhóm cần làm rõ phạm vi khác cùng Product Owner mà vẫn giữ chất lượng.

### 25.4. Gần cuối Sprint: phân biệt Done và gần Done

Giả sử các automated checks đều xanh, nhưng phiên khám phá mới cho thấy trình duyệt có thể giữ cache của tài khoản A sau khi đăng nhập bằng B. Nhóm xác định đây là rủi ro dữ liệu cá nhân đáng kể.

**Quyết định đúng:** không gọi Increment đã đạt Definition of Done nếu luồng còn vi phạm điều kiện bắt buộc. Developers làm rõ nguyên nhân, sửa và kiểm chứng. Nếu chưa đủ thời gian, nêu đúng trạng thái và xử lý phần chưa Done theo Product Backlog; không âm thầm tắt ca test để đóng ticket.

### 25.5. Sau khi giao phần đạt chuẩn

Khi Increment an toàn, nhóm có thể phát hành cho nhóm người dùng phù hợp, quan sát:

- Học viên có tìm và mở đúng bài không?
- Tỷ lệ lỗi đọc/lưu checkpoint có tăng không?
- Có sự cố phân quyền hoặc dữ liệu bất thường không?
- Người học có hiểu khi tiến độ chưa lưu thành công không?
- Những thiết bị/môi trường nào xuất hiện nhiều vấn đề cần khám phá thêm?

Phản hồi kỹ thuật tạo **kiểm tra mới hoặc sửa cơ chế vận hành**; phản hồi người dùng tạo **câu hỏi sản phẩm và điều chỉnh Product Backlog**. Không suy từ “tất cả test pass” rằng tỷ lệ tiếp tục học đã tăng.

### 25.6. Cái gì được cải tiến ở Retrospective?

Nhóm có thể nhận thấy lỗi bị phát hiện muộn vì chỉ chạy happy-path E2E, thiếu charter về trạng thái mạng. Một thử nghiệm cải tiến hợp lý:

> “Trong hai Sprint tới, khi story có lưu dữ liệu bất đồng bộ, chúng ta sẽ trao đổi các trạng thái success/pending/error ngay khi refinement, có component tests cho lỗi mạng và thực hiện một charter ngắn về retry/trạng thái biên trước khi gọi Done. Sau đó xem lại lỗi lọt, thời gian chờ test và độ ổn định CI.”

Đây là **giả thuyết cải tiến có thể kiểm chứng**, không phải áp một checklist mới quá nặng cho mọi story không liên quan.

## 26. Đo chất lượng liên tục mà không tạo chỉ tiêu sai

Muốn cải tiến, nhóm cần quan sát **chất lượng bằng chứng, tốc độ phản hồi, dòng công việc và tác động lỗi**. Không có một chỉ số đơn lẻ khẳng định sản phẩm “99% chất lượng”.

| Nhóm tín hiệu | Có thể theo dõi | Cách đọc có trách nhiệm |
| --- | --- | --- |
| **Tốc độ phản hồi** | Thời gian CI/test suite, thời gian từ phát hiện đến sửa | Nhanh là tốt khi tín hiệu đáng tin và không cắt bảo vệ quan trọng |
| **Độ tin cậy kiểm thử** | Tỷ lệ flaky, test bị cách ly, lỗi môi trường thử | Cần lý do và hành động, không dùng retry để che tất cả |
| **Lỗi phát hiện** | Defects theo mức ảnh hưởng, nguồn phát hiện, lỗi tái xuất | Số bug nhiều có thể phản ánh khám phá tốt hơn, không tự nói nhóm tệ hơn |
| **Lỗi lọt production** | Sự cố dữ liệu/quyền, lỗi nghiêm trọng, thời gian phát hiện và phục hồi | Xem hậu quả, bối cảnh thay đổi và mức độ quan sát |
| **Độ bao phủ rủi ro** | Danh mục rủi ro cao có bằng chứng kiểm tra, charter còn thiếu | Có giá trị hơn đếm tổng số test không phân loại |
| **Dòng công việc** | WIP, cycle time, work item age, thời gian chờ Review/Verify | Tìm nút thắt hệ thống, không đánh giá từng người theo số ticket |
| **Chất lượng giá trị** | Hoàn thành tác vụ, người dùng hiểu hành vi, phản hồi định tính | Không suy ra outcome chỉ từ pipeline xanh |

### Ví dụ đọc số liệu

Một Sprint trước nhóm có **40 bài E2E**, chạy mất 80 phút; Sprint sau chuyển một phần kiểm tra quy tắc xuống cấp unit/API, còn **12 bài E2E cốt lõi**, chạy 15 phút. Đồng thời, nhóm thêm charter về rủi ro dữ liệu.

Điều này **có thể là cải tiến** nếu bằng chứng bảo vệ rủi ro vẫn đầy đủ, suite ổn định hơn và lỗi lọt không tăng. Không thể kết luận chất lượng giảm chỉ vì số test UI ít đi, hay chất lượng tăng chỉ vì pipeline nhanh hơn.

### Tỷ lệ lỗi lọt không phải phép đo tuyệt đối

Nếu sau một đợt phát hành số lỗi được báo tăng, có thể do:

- Bản phát hành thực sự nhiều lỗi hơn.
- Nhóm mở rộng đối tượng người dùng hoặc thêm monitoring.
- Người dùng có cách báo lỗi dễ hơn.
- Khối lượng/loại công việc và dữ liệu đã thay đổi.

Cần xem **mức ảnh hưởng, xu hướng theo thời gian, độ quan sát và tính đại diện**, thay vì quy toàn bộ thay đổi của một con số cho một cá nhân.

### Một báo cáo chất lượng hữu ích

> “Đối với luồng Học tiếp, các quy tắc phân quyền và checkpoint đã có unit/API/integration checks ở CI. Đã thực hiện hai charter về mạng chậm và đổi tài khoản; tìm một lỗi báo lưu thành công giả, hiện đã sửa và có regression test. Còn chưa kiểm chứng đầy đủ hành vi trên một trình duyệt cũ ngoài phạm vi hỗ trợ chính; Product Owner và Developers đã ghi nhận ranh giới release, cùng phương án theo dõi sau phát hành.”

Báo cáo nêu **bằng chứng, rủi ro và quyết định**; không đơn thuần là “500/500 tests xanh, chất lượng 100%”.

## 27. Phản mẫu thường gặp

### 27.1. “Đã có automation nên không cần tester khám phá”

Automation bảo vệ những điều đã được mã hóa. Nó không tự thay việc đặt câu hỏi mới về giá trị, dữ liệu thật, luồng bất thường và khả dụng. **Cải tiến:** giữ thời gian học hỏi có mục tiêu cho những rủi ro chưa biết.

### 27.2. “Exploratory testing là bấm ngẫu nhiên không cần tài liệu”

Không có charter, ghi chú, bằng chứng và debrief khiến phát hiện khó tái hiện, thông tin bị mất. **Cải tiến:** charter ngắn, timebox và kết luận có hành động, nhưng không biến charter thành script cứng.

### 27.3. “Càng nhiều test case càng an toàn”

Hàng nghìn happy-path assertions có thể bỏ trống bảo mật, dữ liệu biên và concurrency. **Cải tiến:** đánh giá rủi ro được bảo vệ, oracle, tốc độ và độ tin cậy thay vì đếm test.

### 27.4. “Mọi lỗi tìm bằng UI phải tạo một E2E test”

Suite trở nên chậm và flaky, khó xác định nguyên nhân. **Cải tiến:** đưa regression check vào **cấp thấp nhất vẫn kiểm chứng đúng lỗi**, thêm E2E cho hành trình cần bảo vệ.

### 27.5. “Thêm test tới 100% coverage là đủ”

Coverage có thể cao trong khi thiếu assertion hoặc quy tắc an toàn quan trọng. **Cải tiến:** kết hợp review risk, mutation testing có chọn lọc, khám phá và dữ liệu người dùng.

### 27.6. “Chạy lại đến khi xanh”

Retry vô điều kiện che flaky tests và lỗi race condition. **Cải tiến:** thu bằng chứng, cách ly nguyên nhân và sửa độ tin cậy; ghi rõ rủi ro nếu có kiểm tra bị vô hiệu hóa tạm.

### 27.7. “Cuối Sprint mới bắt đầu kiểm thử”

Lỗi đến muộn, việc dồn ở Review/Verify và khó đạt Done. **Cải tiến:** cùng xây ví dụ trước code, kiểm tra sớm trên lát cắt nhỏ, khám phá trong lúc phát triển.

### 27.8. “QA là người duy nhất chịu trách nhiệm chất lượng”

Developers có thể coi “code complete” là kết thúc trách nhiệm, còn QA biến thành hàng đợi. **Cải tiến:** cả nhóm cùng sở hữu chất lượng; người kiểm thử đóng góp chuyên môn, không làm thay mọi trách nhiệm kỹ thuật và nghiệp vụ.

### 27.9. “Mỗi phát hiện khám phá đều là bug”

Nhiều phát hiện chỉ là câu hỏi, giả định chưa thống nhất hoặc ý tưởng UX. **Cải tiến:** phân loại rồi hỏi đúng người có thẩm quyền, không mặc định gắn trạng thái defect.

### 27.10. “Báo cáo bug là năng suất của một tester”

Khuyến khích tìm lỗi vặt, né khám phá rủi ro lớn nhưng khó tái hiện. **Cải tiến:** đánh giá giá trị thông tin, chất lượng tái hiện và khả năng phòng ngừa.

### 27.11. “Dùng dữ liệu production thật để có test thực tế hơn”

Nguy cơ rò rỉ dữ liệu và vi phạm quyền riêng tư. **Cải tiến:** dữ liệu tổng hợp hoặc xử lý an toàn, quyền và môi trường thử rõ ràng.

### 27.12. “Exploratory testing thay cho kiểm thử bảo mật bắt buộc”

Một người thử vài đường đi không đủ chứng minh quyền và dữ liệu được bảo vệ. **Cải tiến:** có tests tự động và kiểm tra chuyên sâu phù hợp rủi ro, khám phá chỉ bổ sung.

### 27.13. “Không thể tự động hóa kiểm thử UX nên bỏ qua”

Khả dụng cần quan sát và phản hồi từ người dùng, không chỉ assertions. **Cải tiến:** kết hợp scanner, checklist, thử bàn phím, thiết bị trợ năng và nghiên cứu phù hợp.

### 27.14. “Pass hết test nghĩa là giá trị sản phẩm đã được chứng minh”

Kiểm tra kỹ thuật không trực tiếp chứng minh outcome. **Cải tiến:** sau khi giao Increment đáng tin, đo hành vi và lắng nghe người dùng để điều chỉnh backlog.

### 27.15. “Không còn thời gian nên bỏ kiểm thử quan trọng”

Đánh đổi chất lượng bắt buộc để giữ deadline có thể gây hại. **Cải tiến:** thương lượng phạm vi, làm rõ dự báo, không tuyên bố Done khi chưa đạt điều kiện an toàn.

## 28. Workshop 60–75 phút: xây chiến lược kết hợp cho một user story

Đây là **bài tập mô phỏng**, không phải timebox bắt buộc của Scrum hoặc một tiêu chuẩn kiểm thử.

| Giai đoạn | Thời lượng gợi ý | Hoạt động | Đầu ra |
| --- | ---: | --- | --- |
| **1. Nhu cầu và quy tắc** | 10 phút | Người hiểu nghiệp vụ trình bày story, giá trị và trường hợp quan trọng | User story, acceptance criteria sơ bộ |
| **2. Bản đồ rủi ro** | 10 phút | Developers và tester nêu tác động, bất định, dữ liệu và quyền | 3–5 rủi ro cần ưu tiên |
| **3. Chọn automation** | 15 phút | Quyết định unit, API, integration, E2E cho từng quy tắc | Danh sách checks có mục tiêu và oracle |
| **4. Viết charter** | 10 phút | Chọn một vùng chưa biết, xác định heuristic và dữ liệu | Test charter khám phá có timebox |
| **5. Mô phỏng phiên** | 10–15 phút | Thử trên prototype hoặc thảo luận chuỗi tình huống | Phát hiện, câu hỏi và bằng chứng cần thu |
| **6. Debrief và cải tiến** | 5–15 phút | Chọn test hồi quy, sửa backlog, xác định Done/monitoring | Quyết định và hành động tiếp theo |

### Bài toán dùng cho workshop

> “Học viên đã đăng nhập có thể lưu vị trí đang học và quay lại bài học sau khi đóng trình duyệt.”

Đội phải xử lý ít nhất:

- Đọc và ghi checkpoint hợp lệ, bảo vệ đúng tài khoản.
- Không báo lưu thành công giả khi request thất bại.
- Trường hợp hai tab có thể ghi cùng bài.
- Quyền học hết hạn sau khi đã có checkpoint.
- Khả dụng trên màn hình nhỏ hoặc chỉ dùng bàn phím.

### Tiêu chí đánh giá sản phẩm workshop

1. **Có rủi ro nào bị bỏ sót vì mọi người chỉ nghĩ tới happy path không?**
2. **Mỗi kiểm tra tự động có oracle và cấp kiểm tra phù hợp không?**
3. **Charter có câu hỏi và không trói người thử vào script cứng không?**
4. **Đã làm rõ dữ liệu thử, quyền truy cập và cách lưu bằng chứng chưa?**
5. **Khi phát hiện sai, nhóm biết cần quyết định, sửa và bổ sung test ở đâu không?**
6. **Nhóm biết điều kiện nào bắt buộc trước khi gọi Done và phát hành không?**

Không đánh giá bằng số lượng sticky notes hoặc số bug giả định; đánh giá bằng **khả năng lý giải rủi ro, thu bằng chứng và tạo vòng học hỏi liên tục**.

## 29. Bài tập tự kiểm tra và gợi ý

### Bài tập A — Kiểm tra tự động hay khám phá?

Phân loại các tình huống và giải thích:

1. Một JUnit test xác nhận checkpoint âm bị từ chối.
2. Người thử có charter “đánh giá hành vi khi mạng chậm”, lần lượt thay tốc độ và theo dấu response, đổi phép thử sau khi thấy UI báo sai.
3. Một tester đọc kịch bản có sẵn và bấm đúng năm bước, không thay đổi cách thử.
4. Một fuzzing job tự sinh dữ liệu API bất thường và phát hiện crash.
5. Một người dùng thử không tìm được nút “Học tiếp”, dù E2E test bấm nút thành công.

**Gợi ý:** (1) kiểm tra tự động; (2) khám phá có mục tiêu; (3) kiểm thử theo kịch bản thủ công; (4) tự động hóa tìm kiếm lỗi, vẫn cần phân tích; (5) tín hiệu khả dụng cần điều tra.

### Bài tập B — Tạo charter

Hãy viết charter 40 phút cho trường hợp:

> “Người dùng có thể chuyển giữa hai thiết bị khi đang học và phải không bị mất tiến độ.”

Charter phải nêu **mission, phạm vi, giả thuyết, môi trường, dữ liệu, oracle, heuristic, bằng chứng và debrief**. Nếu sản phẩm chưa hứa hỗ trợ đồng bộ nhiều thiết bị, hãy giải thích cách chuyển charter sang **kiểm chứng rủi ro trước khi quyết định mở rộng phạm vi**, thay vì tự coi đó là lỗi phải sửa trong bản đầu.

### Bài tập C — Chọn cấp kiểm thử hồi quy

Một phiên khám phá tìm thấy:

| Phát hiện | Cấp kiểm thử nên cân nhắc |
| --- | --- |
| Vị trí lớn hơn thời lượng bài được lưu | Unit/domain + API nếu cần |
| Token tài khoản B đọc dữ liệu tài khoản A | API/integration security |
| Hai request cùng lưu làm mất checkpoint mới | Integration/concurrency |
| Nút bị mất focus khi đóng dialog | Component/E2E có accessibility checks |
| Người học không hiểu nhãn “Tiếp tục” | Khám phá/quan sát người dùng; tự động hóa các yêu cầu kỹ thuật đã rõ |

Giải thích vì sao **không nên tạo một UI E2E riêng cho mọi phát hiện**.

### Bài tập D — Khi pipeline xanh nhưng chưa được giao

Nhóm có CI xanh, nhưng kiểm thử khám phá phát hiện có thể đọc tiến độ tài khoản khác bằng một ID trực tiếp. Product Owner muốn phát hành trong ngày.

1. Rủi ro này thuộc loại nào?
2. Có nên gọi Increment đã Done khi lỗi còn tồn tại không?
3. Kiểm tra nào nên được thêm để phòng tái xuất?
4. Ai cần phối hợp làm rõ phạm vi và ảnh hưởng dự báo?
5. Nếu chưa thể sửa ngay, nên nói gì với bên liên quan?

**Gợi ý:** Đây là rủi ro bảo vệ dữ liệu nghiêm trọng; không được che lỗi bằng CI xanh hay đổi label. Nhóm cần xử lý hoặc giữ phần không an toàn chưa phát hành, minh bạch ảnh hưởng.

### Bài tập E — Nhận diện flaky test

Một E2E test dùng lệnh “chờ 2 giây” trước khi kiểm tra thông báo “đã lưu”. Test thường pass trên máy người viết nhưng fail ở CI khi hệ thống chậm.

Hãy đề xuất:

- Cách đồng bộ test theo **điều kiện thực** thay vì thời gian cố định.
- Dữ liệu và trạng thái nào cần reset.
- Assertion nào nên chuyển xuống component/API.
- Cách thu bằng chứng khi fail.
- Có nên xóa test ngay để pipeline xanh không?

**Gợi ý:** Tập trung vào nguyên nhân và đúng cấp kiểm tra; không che lỗi bằng retry liên tục hoặc bỏ qua kiểm tra bắt buộc.

### Bài tập F — Lập kế hoạch một Sprint

Một Scrum Team có Sprint Goal về luồng “Học tiếp”. Developers chọn ba PBIs, thời gian kiểm thử bị dồn vào ba ngày cuối, bảng Kanban có tám item đang Doing và hai item ở trạng thái chờ kiểm tra.

Hãy đề xuất:

1. Hai cải tiến giúp đưa kiểm tra đến **sớm hơn trong Sprint**.
2. Một charter khám phá cần ưu tiên vì rủi ro dữ liệu.
3. Hai checks tự động ở cấp phù hợp.
4. Một thay đổi WIP/flow để giúp nhóm hoàn tất việc.
5. Những tín hiệu nào sẽ chứng minh cải tiến có ích mà không giảm Definition of Done.

**Gợi ý:** Làm rõ ví dụ trước code, test-first, tích hợp lát cắt nhỏ, phối hợp Developers với tester, giảm WIP và quan sát cycle time/work item age.

### Bài tập G — Đọc chỉ số chất lượng

Tuần 1 có 300 tests xanh, tuần 2 có 400 tests xanh nhưng production phát sinh thêm lỗi checkpoint nghiêm trọng.

Hãy phân tích:

- Vì sao **số test tăng** không chứng minh rủi ro đã giảm?
- Những rủi ro nào chưa có kiểm tra hoặc monitoring?
- Charter nào giúp điều tra sâu hơn?
- Có nên dùng số bug/giờ để đánh giá năng suất tester?
- Nên báo cáo chất lượng ra sao để quyết định bước tiếp theo?

**Gợi ý:** Tập trung vào độ bao phủ rủi ro, độ tin cậy test, tác động người dùng và chất lượng bằng chứng hơn là số lượng.

## 30. Checklist triển khai kết hợp hai cách kiểm thử

- [ ] Nhóm có một định nghĩa chung về **kiểm tra tự động, kiểm thử theo kịch bản và khám phá**.
- [ ] User story có **giá trị, ví dụ nghiệp vụ và quy tắc quan trọng** đủ rõ.
- [ ] Rủi ro chất lượng được đánh giá **trước và trong khi phát triển**, không chỉ cuối Sprint.
- [ ] Có kiểm tra tự động cho các quy tắc cốt lõi, dữ liệu biên và bảo mật bắt buộc.
- [ ] Mỗi kiểm tra có oracle có căn cứ, không mã hóa kỳ vọng tự suy đoán.
- [ ] Unit/API/integration/E2E được dùng ở cấp phù hợp với loại lỗi cần bảo vệ.
- [ ] Không cố tự động hóa tất cả kiểm tra bằng UI khi cấp thấp hơn đủ bằng chứng.
- [ ] Có **charter khám phá** cho những vùng rủi ro/bất định quan trọng.
- [ ] Phiên khám phá có mục tiêu, timebox, heuristic, dữ liệu thử và ghi chú phù hợp.
- [ ] Người thực hiện có công cụ quan sát UI, API, backend và môi trường ở mức cần thiết.
- [ ] Dữ liệu và tài khoản thử được quản lý an toàn, không lộ thông tin người dùng.
- [ ] Phát hiện được phân loại: bug, câu hỏi nghiệp vụ, UX, rủi ro hay cơ hội.
- [ ] Những bug đã rõ được biến thành **regression tests phù hợp** khi có giá trị.
- [ ] Những vùng khó tự động hóa vẫn có kế hoạch quan sát/khám phá, không bị bỏ qua.
- [ ] CI có tín hiệu nhanh, đáng tin, không che flaky tests hoặc bỏ test để chạy xanh.
- [ ] Test suite có quản lý dữ liệu, thời gian chạy, khả năng chẩn đoán và chi phí bảo trì.
- [ ] Product Owner, Developers, người thử nghiệm và bên liên quan trao đổi theo đúng trách nhiệm.
- [ ] Nếu dùng Scrum, **Definition of Done** không bị hạ vì Sprint gần hết thời gian.
- [ ] Nếu dùng Kanban, công việc chờ review/verify được nhìn thấy và không làm WIP tăng không kiểm soát.
- [ ] Nếu dùng XP, TDD/CI/refactoring bổ trợ cho khám phá chứ không thay thế việc học về nhu cầu.
- [ ] Trước release, các rủi ro chưa kiểm chứng và điều kiện bắt buộc được minh bạch.
- [ ] Sau release, nhóm quan sát cả **lỗi kỹ thuật, dữ liệu và outcome người dùng**.
- [ ] Các số đo không được dùng để thưởng/phạt cá nhân dựa trên số bug hoặc số test.
- [ ] Nhóm có thể chỉ ra một **bài học từ khám phá** đã làm thay đổi test tự động, thiết kế hoặc Product Backlog.

## 31. Tài liệu đọc thêm và tổng kết

- [Agile Manifesto](https://agilemanifesto.org/): giá trị giao phần mềm hoạt động, hợp tác và thích ứng bằng phản hồi sớm.
- [The Scrum Guide](https://scrumguides.org/): Sprint Goal, Increment, Definition of Done và các sự kiện kiểm tra/thích ứng.
- [The Kanban Guide](https://kanbanguides.org/): Definition of Workflow, WIP, throughput, cycle time, work item age và cải tiến dòng công việc.
- Kent Beck và Cynthia Andres, *Extreme Programming Explained: Embrace Change*, ấn bản 2 (2004): test-first, continuous integration, refactoring và small releases.
- Lisa Crispin và Janet Gregory, *Agile Testing: A Practical Guide for Testers and Agile Teams* (2009): cộng tác giữa người làm sản phẩm, Developers và testers trong Agile.
- Lisa Crispin và Janet Gregory, *More Agile Testing: Learning Journeys for the Whole Team* (2014): các cách mở rộng năng lực kiểm thử của cả nhóm.
- James Bach và Michael Bolton, các bài viết về **exploratory testing, testing vs checking và session-based test management**: nguồn tìm hiểu tư duy khám phá, oracle và kiểm thử có mục tiêu.
- Elisabeth Hendrickson, *Explore It!: Reduce Risk and Increase Confidence with Exploratory Testing* (2013): charters, heuristic và cách dùng khám phá để giảm rủi ro.
- [Martin Fowler — Test Pyramid](https://martinfowler.com/articles/practical-test-pyramid.html): hướng dẫn lựa chọn cấp kiểm tra và cân đối chi phí phản hồi.
- [OWASP Web Security Testing Guide](https://owasp.org/www-project-web-security-testing-guide/): nguyên tắc kiểm tra bảo mật trong phạm vi được phép và quản lý rủi ro ứng dụng web.
- [W3C Web Accessibility Initiative](https://www.w3.org/WAI/): hướng dẫn về khả năng tiếp cận, bao gồm kiểm tra tự động và đánh giá có con người.

**Điểm cốt lõi:** **Kiểm thử tự động bảo vệ những điều đã biết cần đúng; kiểm thử khám phá giúp tìm điều chưa biết, điều chưa rõ và những rủi ro chưa được kiểm tra.** Chúng không cạnh tranh mà tạo thành một vòng học hỏi: **khám phá → làm rõ quy tắc và phát hiện rủi ro → tự động hóa hồi quy thích hợp → tích hợp và giao an toàn → nhận phản hồi mới → tiếp tục khám phá**.

Trong Agile, mục tiêu không phải nhiều tests nhất, nhiều bug nhất hay kiểm tra thật nhanh bất chấp hậu quả. Mục tiêu là **tạo Increment có chất lượng đáng tin, đưa giá trị đến người dùng sớm, minh bạch về rủi ro và liên tục cải tiến nhờ bằng chứng**. Khi cả Developers, Product Owner và người có chuyên môn kiểm thử cùng tham gia từ đầu, chất lượng trở thành **một phần của quá trình phát triển**, không còn là một chặng kiểm tra bị dồn xuống cuối.
