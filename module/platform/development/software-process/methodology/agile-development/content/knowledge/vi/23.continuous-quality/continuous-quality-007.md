# Ngăn tích tụ lỗi và công việc kiểm chứng ở cuối chu kỳ

Một Scrum Team có Sprint dài hai tuần. Trong tám ngày đầu, bảng công việc đầy các thẻ “đã code xong”; đến ngày thứ chín, người kiểm thử mới nhận một lô lớn để xác minh. Lỗi nghiệp vụ, lỗi phân quyền và lỗi tích hợp bắt đầu xuất hiện. Developers vừa sửa lỗi cũ, vừa hỗ trợ kiểm thử, vừa chuẩn bị Sprint Review. Một số thẻ bị đánh dấu Done vì “chỉ còn kiểm thử”, nhưng thực tế chưa có Increment đủ chất lượng để giao cho người dùng.

Đó là một dạng **tích tụ lỗi và công việc kiểm chứng ở cuối chu kỳ** (*end-of-cycle quality pileup*). Nhóm có vẻ làm nhanh ở đầu chu kỳ nhưng phải trả chi phí chờ đợi, chuyển ngữ cảnh, điều tra và làm lại ở cuối. Khi phát hiện vấn đề muộn, thông tin ban đầu đã phai, mã thay đổi nhiều lần và một lỗi có thể ảnh hưởng nhiều hạng mục.

**Chất lượng liên tục** (*continuous quality*) không có nghĩa không còn lỗi, kiểm thử tất cả mọi thứ ngay lập tức hoặc bắt buộc mọi thành viên thành chuyên gia của mọi công cụ. Đó là cách **xây dựng chất lượng vào từng lát cắt công việc**, đưa phản hồi tới gần lúc tạo ra thay đổi, làm minh bạch phần chưa được kiểm chứng và cải tiến hệ thống để lỗi không tích lũy thành một hàng đợi khó kiểm soát.

Bài thuộc chương **Chất lượng liên tục** của module **AGILE_DEVELOPMENT**. Tinh thần Agile — phản hồi sớm, giao Increment tăng dần, cải tiến liên tục — được kết nối với **user story, Product Backlog, Scrum, Kanban, XP, kiểm thử theo rủi ro và đo lường dòng công việc**. Trọng tâm là hành động cụ thể để **không biến cuối Sprint, cuối timebox hoặc trước release thành “mùa sửa lỗi”**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Nhận diện các dấu hiệu **lỗi, kiểm thử và tích hợp bị đẩy về cuối chu kỳ**.
2. Phân biệt **code complete**, **đã kiểm chứng** và **Done** theo tiêu chuẩn hoàn tất.
3. Thiết kế lát cắt user story có tiêu chí chấp nhận, kiểm thử và tích hợp ngay từ đầu.
4. Chọn các vòng phản hồi sớm: làm rõ nghiệp vụ, review, kiểm thử tự động, CI và kiểm tra chuyên môn.
5. Sử dụng WIP, work item age, cycle time, thời gian chờ và lượng lỗi tồn để phát hiện rủi ro tích tụ.
6. Tổ chức việc sửa lỗi, kiểm thử và làm lại trong năng lực thực tế, không đẩy tất cả cho một vai trò QA.
7. Áp dụng chính sách triage, Definition of Done, chất lượng phát hành và xử lý sự cố có thẩm quyền.
8. Thiết kế thử nghiệm cải tiến trong một đến hai Sprint và đánh giá kết quả bằng dữ liệu, không chỉ cảm nhận.

## 2. Tích tụ chất lượng cuối chu kỳ là gì?

Một quy trình phổ biến nhưng nhiều rủi ro:

~~~mermaid
flowchart LR
    A["Phân tích nhiều yêu cầu"] --> B["Code một lô lớn"]
    B --> C["Đẩy sang QA cuối Sprint"]
    C --> D["Phát hiện nhiều lỗi"]
    D --> E["Sửa gấp + kiểm thử lại"]
    E --> F["Chờ tích hợp/phát hành"]
    D -.->|"Lỗi quay lại"| B
~~~

Trong luồng này, **công việc kiểm chứng không biến mất**; nó chỉ bị đẩy sang một thời điểm và nhóm năng lực khác. Khi đến đó, hệ thống có thể nhận nhiều việc hơn tốc độ xử lý, tạo hàng đợi.

### 2.1. Bốn dạng tích tụ dễ gặp

| Dạng tích tụ | Dấu hiệu | Hậu quả |
| --- | --- | --- |
| **Yêu cầu chưa được làm rõ** | Story vào Sprint nhưng tiêu chí chấp nhận quan trọng còn mơ hồ | Developers phải đoán; phát hiện hiểu sai khi nghiệm thu |
| **Kiểm thử và review bị trì hoãn** | Nhiều thẻ “Dev Done”, ít thẻ Done theo tiêu chuẩn | Hàng đợi kiểm chứng tăng, cycle time dài |
| **Lỗi và làm lại dồn cuối kỳ** | Số bug mới tăng mạnh sát mốc giao; bug cũ chưa được xử lý | Phải chuyển ngữ cảnh, hạ độ tin cậy của dự báo |
| **Tích hợp và vận hành bị bỏ sau** | Chỉ cuối Sprint mới chạy cùng database, API, môi trường phát hành | Lộ phụ thuộc, lỗi cấu hình, dữ liệu hoặc quyền truy cập muộn |

**Không phải có lỗi là quy trình thất bại.** Phát hiện lỗi sớm khi thử một giả thuyết mới có thể là dấu hiệu tích cực. Vấn đề là **lỗi bị che, chờ xử lý quá lâu hoặc phát hiện muộn tới mức nhóm không còn đủ thời gian và thông tin để phản ứng an toàn**.

### 2.2. Chất lượng bị dồn khác với có bước kiểm soát cuối cùng

Một sản phẩm có thể cần kiểm tra pháp lý, bảo mật hoặc chấp thuận phát hành trước production. Những bước ấy có thể là điều kiện kiểm soát hợp lý.

**Sai lầm** là dùng bước cuối làm **lần đầu tiên** nhóm kiểm tra hành vi cốt lõi, quyền truy cập hoặc tính nhất quán dữ liệu. Chất lượng liên tục muốn **phần lớn rủi ro có thể kiểm chứng sớm được kiểm chứng sớm**, đồng thời giữ những kiểm soát chuyên sâu phù hợp ở thời điểm cần thiết.

## 3. Vì sao lỗi và kiểm chứng thường dồn về cuối?

### 3.1. Tối ưu công đoạn thay vì tối ưu dòng giá trị

Một nhóm có thể đo “Developers viết xong bao nhiêu story” và xem việc chuyển thẻ sang QA là hoàn tất. Nếu QA nhận công việc nhanh hơn khả năng kiểm chứng, **thời gian người dùng chờ không giảm**, dù số lượng thẻ Dev Done rất cao.

Ví dụ:

- Development đưa trung bình **8 story/tuần** tới trạng thái chờ kiểm thử.
- Năng lực kiểm chứng và sửa sai thực tế chỉ giúp **5 story/tuần** đạt điều kiện Done.
- Nếu nhu cầu và điều kiện tương tự duy trì, hàng đợi trước Done có xu hướng tăng khoảng **3 story mỗi tuần**.

Con số chỉ là mô hình minh họa: kích thước item, lỗi làm lại và năng lực có thể thay đổi. Nhưng nó cho thấy **đẩy thêm việc tới bước bị nghẽn không tự làm tăng throughput của cả hệ thống**.

### 3.2. Story quá lớn và không có lát cắt dọc

Một story “Xây toàn bộ quản lý workshop” chứa giao diện, API, database, email, hủy chỗ và báo cáo khiến kiểm thử đầu cuối chỉ khả thi sau nhiều ngày. Đến khi có thể thử, hàng loạt giả định đã được mã hóa.

Tách theo các tầng **“làm API”, “làm UI”, “làm database”** có thể giúp phân việc, nhưng chưa chắc tạo phần mềm hoàn chỉnh để kiểm chứng với người dùng.

### 3.3. Chất lượng bị xem là trách nhiệm riêng của QA

Developers viết xong rồi “giao cho QA chịu trách nhiệm chất lượng”; QA chỉ tham gia sau khi tính năng đã xây. Điều này tạo hai vấn đề:

1. Những câu hỏi nghiệp vụ quan trọng đến quá muộn.
2. Các điều kiện kiểm thử và môi trường trở thành **phụ thuộc nối tiếp**.

**Người kiểm thử chuyên trách có giá trị lớn**, nhưng không nên là nơi duy nhất “sở hữu chất lượng”. Phát triển phần mềm chất lượng cần **cùng lập kế hoạch, xây, xem xét, kiểm thử và sửa lỗi**.

### 3.4. Khuyến khích bắt đầu hơn hoàn tất

Nếu thành tích được đo bằng số task bắt đầu, số dòng code hoặc số story “Dev Done”, nhóm có xu hướng mở thêm việc thay vì giúp item cũ tới Done. **WIP tăng** làm việc bị chờ lâu hơn và nhiều phần ngữ cảnh bị quên.

### 3.5. Công cụ phản hồi chậm hoặc thiếu tin cậy

CI chạy một lần mỗi ngày, test flaky bị bỏ qua, môi trường staging thường xuyên hỏng hoặc dữ liệu test không tái lập được khiến Developers trì hoãn kiểm chứng. Lỗi chỉ được phát hiện khi có một đợt kiểm tra lớn.

### 3.6. Không có chính sách với lỗi đang mở

Bug có thể tồn tại trong backlog nhiều tuần mà không có mức nghiêm trọng, người chịu trách nhiệm hoặc thời điểm xem lại. Khi sát mốc, mọi bug đều đột nhiên được gọi là “khẩn” và chen ngang kế hoạch.

## 4. Chuyển từ “kiểm tra chất lượng cuối kỳ” sang “xây chất lượng vào công việc”

Một luồng tốt hơn:

~~~mermaid
flowchart TD
    A["Chọn lát cắt giá trị nhỏ"] --> B["Làm rõ ví dụ và rủi ro với cả nhóm"]
    B --> C["Viết test/check phù hợp, chuẩn bị dữ liệu/môi trường"]
    C --> D["Phát triển + review + tích hợp sớm"]
    D --> E["Kiểm chứng theo lát cắt"]
    E --> F{"Đạt tiêu chuẩn Done?"}
    F -->|"Chưa"| G["Sửa ngay khi ngữ cảnh còn mới"]
    G --> D
    F -->|"Có"| H["Increment hoàn chỉnh"]
    H --> I["Phản hồi từ người dùng/vận hành"]
    I --> A
~~~

**Chất lượng liên tục không nhất thiết là mọi bước diễn ra theo thứ tự cứng**; trong thực tế làm rõ, lập trình, kiểm thử và review có thể lặp hoặc chồng lấn. Điều cần giữ là **lát cắt được kiểm chứng trước khi nhóm tuyên bố hoàn tất**.

### 4.1. Đổi câu hỏi quản lý

| Câu hỏi gây dồn cuối kỳ | Câu hỏi hướng tới dòng giá trị |
| --- | --- |
| Hôm nay có bao nhiêu story đã code xong? | Có bao nhiêu story **đạt Done** và sẵn sàng tạo giá trị? |
| QA còn bao nhiêu việc, khi nào QA làm nhanh hơn? | Điểm chờ kiểm chứng xuất hiện ở đâu và nhóm hỗ trợ thế nào? |
| Làm sao bắt đầu thêm ba story? | Có item nào gần Done mà cả nhóm có thể cùng hoàn tất? |
| Có thể bỏ vài test để giữ lịch không? | Có thể **giảm phạm vi tùy chọn** nhưng giữ tiêu chuẩn chất lượng không? |
| Bao nhiêu lỗi đã được đóng? | Những rủi ro trọng yếu đã được xử lý, kiểm chứng và không tái diễn chưa? |
| Sprint Review có thể demo tính năng này không? | Increment này đã đáp ứng DoD và có thể trình bày trung thực tới đâu? |

## 5. Definition of Done bảo vệ tính trung thực của kết quả

Trong **Scrum**, **Definition of Done (DoD)** là cam kết gắn với Increment và mô tả trạng thái chất lượng phải đạt. PBI **không được tính là một phần của Increment** nếu chưa đáp ứng DoD. DoD phải tuân thủ tiêu chuẩn tổ chức nếu có; nếu không, Scrum Team tạo DoD phù hợp với sản phẩm.

**“Code complete” không phải tên gọi khác của Done.** Một tính năng đã merge nhưng chưa kiểm tra phân quyền cần thiết hoặc chưa qua tích hợp bắt buộc có thể vẫn là công việc chưa hoàn tất.

### 5.1. Một DoD minh họa cho luồng đăng ký workshop

| Điều kiện | Bằng chứng mong muốn |
| --- | --- |
| Quy tắc nghiệp vụ đã làm rõ | Ví dụ chấp nhận về đủ điều kiện, chỗ trống, đăng ký trùng, lỗi |
| Mã đã tích hợp | Build và các check bắt buộc đạt trên đúng thay đổi |
| Hành vi cốt lõi đã kiểm chứng | Unit, service hoặc integration test theo rủi ro |
| Dữ liệu không bị mâu thuẫn | Kiểm tra đồng thời và tính toàn vẹn trên cơ chế phù hợp |
| Quyền truy cập đúng | Không xem/sửa đăng ký của người khác trái phép |
| Phản hồi cho người dùng rõ | Kết quả thành công/thất bại có trạng thái đáng tin |
| Không còn vấn đề ngăn đạt tiêu chuẩn | Lỗi/rủi ro liên quan đã được sửa hoặc xử lý đúng chính sách |
| Có khả năng vận hành tối thiểu | Log, cảnh báo, xử lý thất bại và tài liệu cần thiết phù hợp |

Đây chỉ là ví dụ, không phải DoD bắt buộc cho mọi tổ chức. **Đừng kéo toàn bộ tiêu chí chi tiết của từng PBI vào DoD một cách máy móc**: DoD là tiêu chuẩn chung cho Increment; còn tiêu chí chấp nhận làm rõ hành vi cụ thể của từng PBI. Hai nhóm điều kiện bổ sung nhau.

### 5.2. Không viết lại DoD để “cứu” ngày giao

Giả sử hạng mục đăng ký chỗ cuối chưa qua kiểm thử đồng thời. Không nên đổi quy tắc Done thành “đã code + unit test” ngay trước Sprint Review để tăng số hạng mục hoàn tất.

Nhóm có thể **thương lượng dời một chức năng tùy chọn**, thay cách thiết kế hoặc cập nhật dự báo, nhưng **không che phần chưa đạt chất lượng**. Nếu tiêu chuẩn thực sự cần được cải tiến, việc đó phải dựa trên rủi ro và sự thống nhất phù hợp, không phải một mẹo tăng số liệu.

## 6. Làm rõ yêu cầu và kiểm chứng trước khi bắt đầu code

Nhiều lỗi được phát hiện ở cuối Sprint thực chất là **hiểu lầm yêu cầu từ đầu**. Cách ngăn tốt không chỉ là viết thêm test sau khi code, mà là **đưa người hiểu nghiệp vụ, người phát triển và người kiểm thử vào cuộc trao đổi sớm**.

### 6.1. Ví dụ theo cách “ba góc nhìn”

**User story:** Là học viên, tôi muốn đăng ký workshop còn chỗ để giữ được một vị trí phù hợp.

| Góc nhìn | Câu hỏi sớm cần làm rõ |
| --- | --- |
| **Nghiệp vụ/Product Owner** | Ai được đăng ký? Có hạn chót? Khi nào một đăng ký được coi là xác nhận? |
| **Developers** | Cơ sở dữ liệu xử lý tranh chỗ cuối thế nào? API có idempotency? Các phụ thuộc nào? |
| **Kiểm thử/chất lượng** | Hai yêu cầu đồng thời, đăng ký trùng, lỗi mạng, xem dữ liệu người khác, hủy ở hạn chót ra sao? |

Một cuộc trao đổi ngắn có thể tạo ra nhiều giá trị hơn hàng chục trường hợp kiểm thử được viết **sau khi** giải pháp đã được đóng khung sai.

### 6.2. Ví dụ tiêu chí chấp nhận có thể kiểm chứng

~~~gherkin
Feature: Dang ky workshop

  Scenario: Dang ky khi con cho
    Given hoc vien A du dieu kien tham gia W
    And W con mot cho
    When A dang ky W
    Then A duoc thong bao trang thai xac nhan chinh xac
    And so cho xac nhan khong vuot suc chua

  Scenario: Hai hoc vien tranh cho cuoi
    Given W chi con mot cho
    When A va B gui yeu cau dang ky gan nhu dong thoi
    Then khong qua mot dang ky moi duoc xac nhan
    And moi yeu cau co ket qua ro rang

  Scenario: Bao ve du lieu ca nhan
    Given A da dang ky W
    When B khong co quyen xem dang ky cua A
    Then he thong tu choi truy cap
~~~

Gherkin ở đây là **mô tả hành vi**, không tự trở thành một bộ test chạy được nếu thiếu step definitions, dữ liệu thử và cấu hình công cụ.

### 6.3. Không cố làm rõ mọi thứ của tương lai

Làm rõ sớm không có nghĩa đặc tả toàn bộ Product Backlog. Hãy ưu tiên **những PBI gần được chọn**, phụ thuộc lớn và rủi ro quan trọng. Những yêu cầu có thể thay đổi xa trong tương lai được cập nhật khi có thêm bằng chứng.

## 7. Chia nhỏ PBI để kiểm chứng được trong chu kỳ

Một PBI lớn chứa nhiều hành vi khiến kiểm thử chỉ có ý nghĩa khi cả chuỗi hoàn tất. **Chia thành lát cắt dọc có giá trị** giúp review và test diễn ra sớm hơn.

### 7.1. Ví dụ chia lát cắt workshop

| PBI quá lớn | Các lát cắt hữu ích hơn |
| --- | --- |
| “Hoàn thiện hệ thống workshop” | Xem workshop còn chỗ; đăng ký một chỗ hợp lệ; xem đăng ký của mình; hủy theo chính sách; nhận nhắc lịch |
| “Xây module tài khoản” | Đăng nhập an toàn cho một vai trò; xem dữ liệu chính mình; cập nhật thông tin được phép |
| “Tích hợp dịch vụ bên ngoài” | Kiểm chứng hợp đồng API; thực hiện một hành vi thành công; xử lý lỗi quan trọng và retry an toàn |

Mỗi lát cắt cần **đầy đủ hành vi, tích hợp và kiểm chứng tương xứng rủi ro**. Không nên gọi “xong giao diện” là Increment nếu người dùng chưa thể thực hiện hành vi có ích và sản phẩm chưa đạt DoD.

### 7.2. Phân biệt chia nhỏ thật với chia giả

**Chia nhỏ thật:** “Học viên xem được đăng ký của chính mình” có hành vi đầu cuối độc lập, đạt kiểm thử và chất lượng.

**Chia giả:** “Viết controller”, “tạo entity”, “viết repository” là các task kỹ thuật cần phối hợp nhưng chưa riêng lẻ mang lại kết quả sử dụng.

Task kỹ thuật vẫn có thể xuất hiện trong Sprint Backlog, nhưng khi đo **story Done** hoặc throughput giá trị, phải biết chính sách đếm là gì.

### 7.3. Ưu tiên “hoàn tất trước khi bắt đầu thêm”

Nếu một PBI đã qua phần code nhưng chờ kiểm chứng, nhóm nên xem có thể **cùng hoàn thành nó** trước khi mở thêm PBI mới. Giảm kích thước lô có thể giảm thời gian chờ review, phát hiện lỗi sớm và giữ ngữ cảnh.

## 8. Phối hợp kiểm thử xuyên suốt một PBI

Thay vì tuần tự “BA viết → Dev code → QA test”, các hoạt động có thể chồng lấn hợp lý:

1. **Trước triển khai:** Làm rõ hành vi, giả định, rủi ro, dữ liệu và tiêu chí kiểm chứng.
2. **Khi bắt đầu:** Xây test phù hợp hoặc chuẩn bị cách kiểm chứng; kiểm tra phụ thuộc sớm.
3. **Trong triển khai:** Unit test, review, pairing, tích hợp liên tục, thử ở tầng phù hợp.
4. **Khi có lát cắt:** Kiểm tra hành vi từ đầu tới cuối; sửa vấn đề khi người viết còn nhớ ngữ cảnh.
5. **Trước Done:** Đánh giá DoD, vấn đề mở, độ tin cậy của check và sự sẵn sàng vận hành.
6. **Sau giao:** Thu phản hồi thật, quan sát lỗi lọt và đưa bài học trở lại backlog.

### 8.1. “Shift left” và “shift right” bổ trợ nhau

**Shift left** là đưa việc học và phát hiện vấn đề tới sớm hơn: làm rõ yêu cầu, threat modeling, test và review ngay gần lúc tạo ra mã.

**Shift right** là tiếp tục kiểm chứng khi phần mềm được dùng trong điều kiện thực: giám sát, thử nghiệm có kiểm soát, phản hồi người dùng, cảnh báo và phân tích sự cố.

**Không nên hiểu shift right là cho phép bỏ test trước phát hành**. Những rủi ro quan trọng đã biết phải được kiểm soát trước khi đưa người dùng vào tình huống có thể gây hại. Quan sát sau giao nhằm **bổ sung bằng chứng và phát hiện điều chưa lường trước**, không thay thế những kiểm tra bắt buộc.

## 9. Chiến lược kiểm thử nhiều tầng và theo rủi ro

Không có một tỷ lệ unit/integration/E2E bắt buộc cho tất cả nhóm. Nên chọn tầng kiểm thử theo **loại lỗi, tốc độ phản hồi, độ tin cậy và chi phí bảo trì**.

| Tầng hoặc phương pháp | Kiểm chứng điều gì? | Ví dụ workshop | Giới hạn |
| --- | --- | --- | --- |
| **Unit test** | Logic nhỏ có đầu vào/kết quả rõ | Học viên có đủ điều kiện đăng ký? | Mock không chứng minh database thật đúng |
| **Service/component test** | Một thành phần phối hợp đúng | Service trả trạng thái phù hợp | Có thể bỏ sót ranh giới ngoài |
| **Integration test** | Dữ liệu, transaction, API thật | Hai yêu cầu tranh chỗ cuối không tạo hai xác nhận | Môi trường phức tạp hơn |
| **Contract test** | Hai dịch vụ thống nhất giao diện | API gửi thông báo có payload đúng | Không thay kiểm thử toàn luồng |
| **End-to-end test** | Hành trình người dùng | Đăng nhập → xem workshop → đăng ký → xem trạng thái | Chậm, dễ phụ thuộc môi trường |
| **Security test** | Quyền, dữ liệu và cấu hình ở các ranh giới | B không đọc được đăng ký A | Không có bộ test bao phủ mọi lỗ hổng |
| **Performance/load test** | Hệ thống chịu được tải dự kiến? | Đợt đăng ký đông người | Cần workload đại diện |
| **Exploratory testing** | Điều bất ngờ qua khám phá có mục tiêu | Lỗi giao diện, tương tác ít gặp | Cần ghi phát hiện và học hỏi, khó tự động hóa toàn phần |
| **Accessibility/usability** | Người dùng có thể thao tác đúng? | Thông báo lỗi rõ, hỗ trợ bàn phím | Thường cần phối hợp tự động và con người |

### 9.1. Phòng lỗi ở đúng tầng

Nếu lỗi là **quy tắc tính điều kiện**, unit test có thể phát hiện rất sớm. Nếu lỗi là **giao dịch đồng thời**, cần test hoặc phân tích ở ranh giới database thật. Nếu lỗi là **đối tác hiểu khác schema**, contract test và một lần tích hợp thật có ích.

**Thêm nhiều test cùng loại không giúp nếu loại đó không thấy được rủi ro đang gây lỗi.**

### 9.2. Đừng biến E2E thành toàn bộ chiến lược kiểm thử

Một bộ E2E lớn chạy một lần mỗi tối có thể phát hiện lỗi muộn, khó chẩn đoán và dễ chờ môi trường. Hãy giữ một số luồng E2E trọng yếu, đồng thời **đưa những kiểm chứng có thể nhanh và ổn định hơn xuống tầng thích hợp**.

## 10. Thực hành XP giảm lỗi và làm lại

Những thực hành kỹ thuật từ **Extreme Programming** bổ trợ trực tiếp cho chất lượng liên tục.

### 10.1. TDD: phản hồi khi thay đổi còn nhỏ

Chu trình **Red – Green – Refactor**:

1. **Red:** Viết một test nhỏ cho hành vi cần có, thấy nó thất bại đúng lý do.
2. **Green:** Viết mã vừa đủ để test đạt.
3. **Refactor:** Cải thiện cấu trúc khi test vẫn bảo vệ hành vi.

TDD giúp phát hiện sai lệch sớm và giảm nỗi sợ refactor, nhưng **unit TDD không thay thế kiểm thử tích hợp hoặc thẩm định bảo mật theo rủi ro**.

### 10.2. Pair programming và review sớm

Hai người cùng giải quyết phần rủi ro cao như quyền xem đăng ký hoặc giữ chỗ cuối có thể:

- Làm rõ giả định ngay khi xuất hiện.
- Phát hiện rủi ro thiết kế trước khi có PR rất lớn.
- Chia sẻ kiến thức để giảm lệ thuộc vào một reviewer.
- Viết kiểm thử có ý nghĩa và nhận phản hồi tức thì.

Pairing không bắt buộc mọi lúc; dùng theo **mục tiêu, độ phức tạp, năng lực và sự đồng thuận**.

### 10.3. Continuous Integration

**CI** hướng nhóm tích hợp các thay đổi nhỏ, thường xuyên và **phản ứng với kết quả build/test**. Một pipeline chỉ chạy tối thứ Sáu không tự giúp phòng lỗi tích hợp từ thứ Hai.

Những điều cần có:

- Build và test trên **đúng commit** đang xét.
- Các bước kiểm chứng bắt buộc hiển thị rõ pass/fail.
- Thay đổi nhỏ để khi fail dễ xác định nguyên nhân.
- Nhánh chung đang đỏ được xử lý kịp thời.
- Báo cáo đủ để tái hiện, không lộ secret.
- Suite kiểm thử rộng hơn chạy ở thời điểm phù hợp, không bị quên.

### 10.4. Refactoring thường xuyên

**Refactoring** cải thiện cấu trúc bên trong mà không cố ý thay đổi hành vi quan sát được. Làm từng bước nhỏ có kiểm thử giúp tránh tích tụ thiết kế khó đổi; nhưng không nên lấy “refactor” làm lý do sửa toàn bộ hệ thống trong một lần thiếu bằng chứng.

## 11. Chất lượng kiểm thử: test flaky làm lỗi bị che

**Flaky test** là test có thể pass hoặc fail không ổn định trong những điều kiện mà nhóm mong đợi tương đương. Nó khiến Developers mất lòng tin vào tín hiệu và dễ chọn **retry tới khi xanh**, ngay cả khi có lỗi sản phẩm thật.

| Nguyên nhân khả dĩ | Cách kiểm tra/cải tiến |
| --- | --- |
| Thời gian bất đồng bộ | Chờ theo điều kiện với timeout hợp lý thay cho sleep cố định |
| Dữ liệu dùng chung | Fixture độc lập, cleanup hoặc transaction đúng |
| Thứ tự test phụ thuộc nhau | Làm test tự thiết lập tiền điều kiện |
| Network/service ngoài thất thường | Tách test contract/mock phù hợp và kiểm tra tích hợp thật có lịch |
| Race condition trong sản phẩm | Tái hiện có kiểm soát, kiểm tra giao dịch/dữ liệu và log |
| CI runner quá tải | Đo thời gian chờ, năng lực và giới hạn tài nguyên |
| Giờ thực, timezone, random | Kiểm soát clock, cấu hình và dữ liệu sinh theo cách phù hợp |

### 11.1. Chính sách xử lý flaky

1. Ghi lại test, dấu hiệu, tần suất và độ nghiêm trọng.
2. Phân biệt lỗi sản phẩm với lỗi test hoặc hạ tầng dựa trên bằng chứng.
3. Xác định người xử lý và mốc xem lại.
4. Nếu cần cách ly test tạm, minh bạch phần bằng chứng bị mất và cách kiểm chứng thay thế.
5. Sửa nguyên nhân, đưa test về luồng chính và theo dõi kết quả qua nhiều lần chạy.

**Không xóa test phân quyền hoặc giao dịch quan trọng chỉ vì nó làm pipeline đỏ.** Nếu không thể kiểm chứng rủi ro thiết yếu, hạng mục có thể chưa đáp ứng điều kiện Done.

## 12. Kanban giúp nhìn nơi kiểm chứng đang bị tắc

Kanban bổ sung khả năng **trực quan hóa dòng công việc, đặt giới hạn WIP, quản lý việc kéo và đo thời gian chờ**. Khi chất lượng bị dồn cuối Sprint, một bảng chỉ có To Do / In Progress / Done thường che mất hàng đợi.

### 12.1. Bảng minh họa

| Sẵn sàng | Đang phát triển | Chờ review | Đang review | Chờ kiểm thử | Đang kiểm thử | Done |
| --- | --- | --- | --- | --- | --- | --- |
| Nâng chất lượng tìm kiếm | Cập nhật quy tắc hủy | Xác nhận workshop | Kiểm tra quyền | Luồng giữ chỗ cuối | Test API hủy | Xem danh sách workshop |

Đây là trạng thái minh họa. Thực tế nhóm có thể gộp review với triển khai hoặc chia bước khác. **Nên mô tả các hàng đợi thực sự tồn tại**, không thêm cột chỉ để bảng phức tạp.

### 12.2. Quy tắc chuyển trạng thái

- **Chờ review:** Mã đã đủ điều kiện review nhưng chưa được reviewer bắt đầu.
- **Đang review:** Có người thực sự kiểm tra và phản hồi.
- **Chờ kiểm thử:** Hạng mục sẵn sàng kiểm chứng nhưng thiếu năng lực/môi trường.
- **Đang kiểm thử:** Có công việc kiểm chứng thực tế đang diễn ra.
- **Blocked:** Có rào cản ngăn bước tiếp theo; ghi lý do, tác động và hành động.
- **Done:** Đáp ứng chính sách hoàn thành, không chỉ chuyển cột vì gần hết Sprint.

Nếu mọi thẻ “Chờ review” được kéo sang “Đang review” chỉ để bảng bớt đỏ, **dữ liệu không còn phản ánh thực tế**.

### 12.3. Giới hạn WIP để tập trung hoàn tất

Giả sử nhóm thử chính sách:

| Vùng | Giới hạn thử nghiệm | Mục đích |
| --- | ---: | --- |
| Đang phát triển | 3 | Tránh bắt đầu vô hạn việc mới |
| Chờ + đang review | 2 | Khuyến khích review và xử lý phản hồi sớm |
| Chờ + đang kiểm thử | 2 | Ngăn tạo lô kiểm thử lớn cuối kỳ |

Các con số **chỉ là ví dụ**, không phải quy định Kanban. Khi một vùng chạm giới hạn, nhóm nên **giúp hoàn tất việc cũ, giải quyết trở ngại hoặc chia sẻ năng lực phù hợp** thay vì tự động mở việc mới. Không ép người chưa đủ kỹ năng phê duyệt thay đổi bảo mật quan trọng chỉ để giữ WIP.

## 13. Thước đo báo hiệu chất lượng đang tích tụ

Đếm số lỗi cuối Sprint chỉ cho biết một phần tình hình. Cần kết hợp **dòng công việc, mức rủi ro và kết quả thực tế**.

| Tín hiệu | Cách hiểu | Cần thận trọng |
| --- | --- | --- |
| **WIP ở vùng chờ review/test** | Bao nhiêu item đã bắt đầu nhưng chưa được kiểm chứng? | Có thể do một đợt đến ngắn hoặc item khác kích thước |
| **Work item age** | Item chưa Done đã tồn tại trong luồng bao lâu? | So với loại việc và chính sách bắt đầu tương ứng |
| **Cycle time** | Thời gian từ bắt đầu tới Done | Dùng cùng ranh giới đo và DoD |
| **Throughput** | Số item hoàn tất theo kỳ | Số lượng item không tự đồng nghĩa giá trị |
| **Queue/blocked time** | Phần chờ review, môi trường, phê duyệt, phụ thuộc | Nhãn blocked chưa chắc ghi hết mọi kiểu chờ |
| **Lỗi chưa xử lý theo mức nghiêm trọng** | Rủi ro còn mở và tuổi của lỗi | Đếm lỗi nhỏ như lỗi dữ liệu nghiêm trọng sẽ gây hiểu sai |
| **Lỗi lọt sau giao** | Những khiếm khuyết người dùng phát hiện sau phát hành | Phụ thuộc mức sử dụng, cách báo và kênh phát hiện |
| **Reopen/rework** | Công việc phải sửa hoặc test lại vì chưa đạt | Phải phân biệt phản hồi học hỏi bình thường với làm lại do lỗi |
| **Kết quả test và CI** | Tốc độ, độ tin cậy, nơi kiểm chứng thiếu | Test pass chỉ có ý nghĩa trong phạm vi đã chạy |
| **Giá trị người dùng** | Mức hoàn thành tác vụ, lỗi ảnh hưởng trải nghiệm, phản hồi | Outcome chịu ảnh hưởng nhiều yếu tố |

### 13.1. Hai chỉ số cần nhìn cùng nhau

**Throughput tăng, lỗi sau phát hành cũng tăng:** Nhóm có thể đang rút ngắn kiểm thử sai cách; cần kiểm tra chính sách Done và rủi ro.

**Lỗi được phát hiện trong Sprint tăng, lỗi lọt production giảm:** Có thể là dấu hiệu kiểm chứng sớm tốt hơn, không nhất thiết chất lượng xấu đi. Cần xem mức nghiêm trọng, phạm vi tính năng và dữ liệu nhiều chu kỳ.

Không nên thưởng/phạt cá nhân theo số bug “tạo ra” hay “tìm được”. Cơ chế đó khuyến khích che lỗi, giảm báo cáo và tranh cãi trách nhiệm thay vì cải tiến.

## 14. Phân biệt lỗi phát hiện sớm và nợ lỗi tích tụ

Một lỗi vừa được phát hiện qua test khi đang code và sửa ngay **khác bản chất** với lỗi đã biết nhưng nằm chờ ba tháng, không có chủ sở hữu hoặc kế hoạch xử lý.

| Tình huống | Điều cần quan tâm |
| --- | --- |
| Test mới phát hiện logic đăng ký trùng ngay trong PBI đang làm | Sửa và kiểm chứng trước Done; học thêm test phù hợp |
| Lỗi phân quyền của chức năng đang phát triển chưa được xử lý | Không coi chức năng là Done nếu chưa đạt chất lượng cần thiết |
| Lỗi giao diện nhỏ trên tính năng đã phát hành | Triage theo ảnh hưởng người dùng, rủi ro, giá trị và ưu tiên |
| Lỗi dữ liệu production có nguy cơ gây hại | Theo quy trình ứng phó sự cố, người có thẩm quyền và nghĩa vụ liên quan |
| Bug từ hệ thống cũ ít ảnh hưởng nhưng tồn rất lâu | Cần quyền sở hữu và xem lại chi phí/giá trị, tránh để mốc thời gian mất nghĩa |
| Lỗi được “đóng” chỉ vì không tái hiện trên một máy | Chưa chắc đã được xác minh; cần thu bằng chứng và ghi rõ điều kiện |

**Chất lượng liên tục không có nghĩa mọi bug đều phải được sửa ngay theo thứ tự xuất hiện**. Nó cần triage theo rủi ro và **không che các lỗi làm phần mềm không đáp ứng tiêu chuẩn đã cam kết**.

## 15. Triage lỗi: ra quyết định bằng tác động, không chỉ số lượng

Một chính sách triage hữu ích giúp nhóm biết **lỗi nào cần xử lý khẩn, lỗi nào ngăn Done, lỗi nào đưa vào Product Backlog để cân nhắc**.

### 15.1. Thông tin tối thiểu của một bug

~~~text
MA LOI / MUC DICH:
HANH VI MONG DOI:
HANH VI THUC TE:
DIEU KIEN TAI HIEN / MOI TRUONG:
DU LIEU MINH HOA KHONG NHAY CAM:
PHAM VI NGUOI DUNG BI ANH HUONG:
TAC DONG: AN TOAN / DU LIEU / NGHIEP VU / TRAI NGHIEM:
MUC DO KHAN VA LY DO:
HANG MUC / INCREMENT LIEN QUAN:
LOG / TEST / BANG CHUNG:
NGUOI CHIU TRACH NHIEM PHOI HOP:
QUYET DINH: SUA NGAY / GAN PBI / THEO DOI / KHONG SUA:
KHI NAO KIEM TRA LAI:
~~~

Đây là mẫu giúp giao tiếp, **không phải artifact bắt buộc của Scrum**. Không cần điền đầy đủ cho một lỗi hiển thị nhỏ nếu nhóm đã có cách trao đổi rõ.

### 15.2. Ma trận xử lý theo rủi ro

| Loại lỗi | Hành động thường phù hợp | Điều cần tránh |
| --- | --- | --- |
| **Mất dữ liệu/lộ thông tin/sự cố nghiêm trọng** | Bảo vệ người dùng, phản ứng sự cố và báo đúng thẩm quyền ngay | Chờ Sprint Planning tiếp theo mới xử lý |
| **Lỗi làm PBI không đạt DoD** | Sửa và kiểm chứng trước khi tính Done, hoặc minh bạch PBI chưa hoàn tất | “Đóng như Done rồi mở bug riêng” để tăng báo cáo |
| **Lỗi người dùng đáng kể của sản phẩm đang vận hành** | Product Owner và các bên liên quan xem giá trị/rủi ro; Developers đánh giá phương án | Chỉ nhìn độ lớn thay vì tác động |
| **Lỗi nhỏ, có phương án chấp nhận được** | Backlog với mô tả và ưu tiên; xem lại theo chính sách | Giấu hoặc để không ai sở hữu đến vô hạn |
| **Nghi ngờ lỗi nhưng chưa đủ bằng chứng** | Thu thông tin, thử tái hiện, giám sát có mục tiêu | Tuyên bố “không có lỗi” chỉ vì không thấy trong một lần chạy |

Các mức trong bảng là **ví dụ**, không phải phân loại mức nghiêm trọng chung cho mọi ngành. Phần mềm tài chính, y tế hoặc hệ thống có nghĩa vụ đặc thù có thể cần quy trình nghiêm ngặt hơn.

### 15.3. Lỗi tồn phải có chính sách tuổi và xem lại

Để tránh backlog lỗi tích tụ:

- Thống nhất ai xem xét các lỗi còn mở và tần suất hợp lý.
- Gắn mức ảnh hưởng, rủi ro, tính tái hiện và người chịu trách nhiệm.
- Làm rõ lỗi nào **ngăn Done**, lỗi nào là công việc sản phẩm độc lập.
- Theo dõi **tuổi của lỗi nghiêm trọng** thay vì chỉ tổng số bug.
- Định kỳ xem lỗi còn giá trị sửa không, có phương án thay thế hợp lệ không.
- Không tự xóa bug lịch sử hoặc hạ mức nghiêm trọng chỉ để báo cáo đẹp.

## 16. Kiểm chứng là công việc cần năng lực, không phải phần phụ không tính

Một nguyên nhân phổ biến của kiểm thử dồn cuối kỳ là **lập kế hoạch chỉ tính thời gian code**.

Một PBI có thể cần:

- Làm rõ ví dụ và tiêu chí chấp nhận.
- Thiết kế test/fixture và dữ liệu.
- Viết mã và unit tests.
- Review và cập nhật theo phản hồi.
- Tích hợp với database/dịch vụ ngoài.
- Kiểm thử các nhánh lỗi, quyền và concurrency.
- Sửa lỗi, regression và kiểm tra khả năng vận hành.

Nếu chỉ ước lượng “hai ngày code”, nhóm có thể bỏ sót phần lớn **năng lực thực sự cần để tạo Increment hoàn chỉnh**.

### 16.1. Kế hoạch dựa trên năng lực thật

Khi chọn PBI cho một Sprint, Developers cần xem **năng lực, kỹ năng, công việc hỗ trợ, sự cố, nghỉ phép, phụ thuộc và lịch sử hoàn tất**, không chỉ tổng số story point hoặc số giờ lập trình.

Trong Scrum, Developers chịu trách nhiệm tạo kế hoạch Sprint Backlog và Increment đạt DoD; Product Owner góp thông tin về giá trị và thứ tự Product Backlog; Scrum Master giúp nhóm cải thiện hiệu quả và xử lý trở ngại.

**Không nên biến QA thành một “trạm cuối” nhận lượng việc không giới hạn**. Kiểm thử, review và vận hành cần tham gia từ khi làm rõ lát cắt để nhóm có cơ hội phối hợp, chia sẻ năng lực và chuẩn bị môi trường.

### 16.2. Phần dự phòng và bất định

Không có tỷ lệ dự phòng cố định hợp lý cho mọi nhóm. Nếu item mới lạ, có rủi ro tích hợp hoặc lịch sử nhiều lỗi, cần làm rõ **độ bất định và phương án giảm rủi ro sớm** như spike giới hạn thời gian, contract test, thử database hoặc lát cắt kỹ thuật nhỏ.

## 17. Ví dụ định lượng: hàng đợi kiểm thử phình ra như thế nào?

Giả sử một nhóm làm việc theo luồng ổn định tương đối, tính theo **story có kích thước gần tương đồng** và chính sách Done không đổi. Đây là mô hình học tập giả định, không phải dự báo cho dự án thật.

### 17.1. Kịch bản đẩy việc nhiều hơn năng lực kiểm chứng

Trong bốn tuần:

- Development đưa **8 story/tuần** sang chờ kiểm chứng.
- Luồng kiểm chứng và sửa sai hoàn tất trung bình **5 story/tuần**.
- Đầu kỳ không có hàng đợi.

| Cuối tuần | Story đến chờ kiểm chứng trong tuần | Story được hoàn tất trong tuần | Story còn trong hàng đợi (minh họa) |
| --- | ---: | ---: | ---: |
| 1 | 8 | 5 | 3 |
| 2 | 8 | 5 | 6 |
| 3 | 8 | 5 | 9 |
| 4 | 8 | 5 | 12 |

Tổng **32 story chuyển sang kiểm chứng**, **20 story đạt Done**, còn **12 story đang chờ hoặc chưa hoàn tất** theo ranh giới đơn giản này.

\[
\text{Hàng đợi cuối tuần 4}=4\times(8-5)=12.
\]

Tình huống trên cho thấy **việc bắt đầu nhanh không bù được khả năng hoàn tất thấp hơn**. Những story chờ lâu có thể phải cập nhật theo thay đổi của nhánh chung, làm chi phí làm lại tăng thêm.

### 17.2. Kịch bản thử ưu tiên hoàn tất

Nhóm thử giảm số story mới đẩy vào vùng kiểm chứng xuống **5 mỗi tuần**, đồng thời cải thiện môi trường và tích hợp để **năng lực kiểm chứng hoàn tất 6 story/tuần** trong thời gian còn đủ việc tồn:

- Nếu đầu kỳ còn **12 story** và luồng thật sự duy trì đầu vào 5, đầu ra 6, hàng đợi có thể giảm **1 story mỗi tuần**.
- Sau bốn tuần trong mô hình đơn giản, hàng đợi còn **8 story**.

\[
12 + 4\times5 - 4\times6=8.
\]

**Cần thận trọng:** Giảm số story chuyển bước không phải là mục tiêu độc lập. Nhóm nên giảm **WIP và làm lại**, tăng khả năng hoàn tất **theo chính sách Done có chất lượng**, chứ không giữ mã dở ở trạng thái khác để bảng “Chờ QA” đẹp hơn.

### 17.3. Đếm số story có thể đánh lừa

Nếu tuần 1 có tám PBI nhỏ và tuần 2 có tám PBI lớn gấp nhiều lần, **số đếm không còn đại diện cho cùng lượng việc**. Dùng thêm cycle time, work item age, phân nhóm theo loại việc và thông tin rủi ro trước khi kết luận.

## 18. Vòng phản hồi tự động: giúp phát hiện lỗi khi ngữ cảnh còn mới

Để không dồn kiểm chứng cuối Sprint, CI và các công cụ kỹ thuật cần **chạy ở tần suất phù hợp với tốc độ thay đổi**.

### 18.1. Các lớp check có thể phối hợp

| Giai đoạn | Check phù hợp | Quyết định được hỗ trợ |
| --- | --- | --- |
| **Ngay khi phát triển** | Unit test, formatter, lint nhanh, review/pairing | Có nên tiếp tục hoặc sửa ngay? |
| **Pull request / trước merge** | Build, unit/component tests, static/security checks thích hợp | Thay đổi có đủ điều kiện tích hợp? |
| **Trên nhánh chung** | Integration/contract tests và kiểm chứng artifact | Tích hợp có còn hoạt động? |
| **Trước phát hành/theo rủi ro** | End-to-end nặng, performance, security review, dữ liệu migration | Sản phẩm có đủ điều kiện giao ở môi trường dự kiến? |
| **Sau triển khai** | Smoke test, logs/metrics, quan sát người dùng và sự cố | Điều gì cần sửa và học thêm? |

**Không cần chạy mọi test trên mọi commit** nếu chi phí gây phản hồi quá chậm, nhưng cần chỉ rõ những bài kiểm tra nặng **được chạy khi nào, ai chịu trách nhiệm, kết quả nào chặn quyết định nào**.

### 18.2. Khi CI đỏ

Một chính sách thực hành:

1. Ghi nhận commit, test/check lỗi và log liên quan.
2. Phân loại lỗi mã, test, dependency hoặc hạ tầng.
3. Người phù hợp ưu tiên sửa, rollback hoặc giảm tác động lên nhánh chung.
4. Chạy lại những check cần thiết sau thay đổi.
5. Không chồng thêm nhiều thay đổi thiếu kiểm chứng lên nhánh chung đỏ lâu.
6. Xem lại vì sao lỗi không được phát hiện sớm hơn.

Mục đích là **giữ tín hiệu đáng tin và khả năng tích hợp**, không phải tìm cá nhân để phạt.

### 18.3. Quality gate phải gắn với rủi ro

Ví dụ gate cho luồng đăng ký yêu cầu build, test phân quyền, test giao dịch, kiểm tra secret và review phù hợp. Chỉ số coverage cao không chứng minh luồng chống vượt sức chứa đúng nếu **test concurrency còn thiếu**.

Một ngoại lệ khi check hỏng cần **bằng chứng, phạm vi, người phê duyệt và cách khôi phục kiểm chứng**. Không âm thầm bỏ gate để đủ số story Done.

## 19. Trách nhiệm phối hợp: chất lượng là việc của cả nhóm

| Vai trò/góc nhìn | Trách nhiệm đóng góp điển hình | Không nên biến thành |
| --- | --- | --- |
| **Product Owner/người hiểu nghiệp vụ** | Làm rõ giá trị, ưu tiên và hành vi chấp nhận; nêu điều kiện người dùng cần | Người ký duyệt mọi dòng mã |
| **Developers** | Xây Increment có chất lượng, test/review/tích hợp, tự quản kế hoạch và sửa lỗi phù hợp | “Chỉ viết code rồi chuyển trách nhiệm chất lượng cho QA” |
| **Người chuyên môn kiểm thử** | Thiết kế kiểm chứng, khám phá rủi ro, dữ liệu/môi trường, hỗ trợ test automation | Cổng cuối phải nhận vô hạn việc dồn từ mọi người |
| **Scrum Master** | Coaching tự quản, giúp Scrum hiệu quả, làm rõ trở ngại hệ thống | Người ra lệnh QA làm nhanh hoặc đổi DoD để giữ lịch |
| **Bảo mật/vận hành/nhóm phụ thuộc** | Phản hồi sớm về quyền, log, khôi phục, cấu hình và phụ thuộc | Chỉ được hỏi khi sắp deploy |
| **Stakeholder** | Cung cấp phản hồi sản phẩm, mục tiêu và ràng buộc thực | Người dùng chức vụ để ép tính Done phần chưa đạt chất lượng |

Trong Scrum, **Developers** là một nhóm trách nhiệm bao gồm những người tạo Increment, không chỉ lập trình viên viết mã. Những người có kỹ năng kiểm thử hoặc chuyên môn khác có thể cùng là Developers theo cấu trúc Scrum Team.

### 19.1. Không phải ai cũng phải làm mọi loại kiểm thử

Chia sẻ trách nhiệm chất lượng **không đồng nghĩa** ép một người chưa đủ kỹ năng phê duyệt kiểm tra bảo mật, dữ liệu hoặc tuân thủ phức tạp. Nhóm cần **phối hợp đúng chuyên môn, chia sẻ kiến thức và cải thiện khả năng kiểm chứng sớm**, thay vì tạo nút thắt chỉ có một người hoặc bỏ điều kiện cần thiết.

### 19.2. Ngôn ngữ trao đổi tạo khác biệt

Thay vì nói **“QA lại tìm quá nhiều bug nên trễ Sprint”**, hãy hỏi:

> “Những lỗi này có thể được phát hiện ở bước nào sớm hơn? Vì sao các trường hợp chấp nhận chưa rõ? Hàng đợi kiểm chứng tăng ở giai đoạn nào? Nhóm cần đổi cách chia lát cắt, test và phối hợp ra sao để những lỗi tương tự không lặp lại?”

Đó là **học hỏi nguyên nhân hệ thống**, không đổ lỗi cho người phát hiện sự thật.

## 20. Xử lý khi đến cuối Sprint vẫn có lỗi hoặc việc chưa kiểm chứng

Ngay cả khi nhóm làm tốt, một số PBI vẫn có thể chưa hoàn tất trong timebox. Scrum **không yêu cầu kéo dài Sprint để hoàn thành danh sách**, cũng không cho phép hạ DoD chỉ để kết quả đẹp.

### 20.1. Phân loại trạng thái trung thực

| Trạng thái thực tế | Cách xử lý |
| --- | --- |
| PBI đã đáp ứng DoD | Là phần của Increment; có thể được xem xét phát hành phù hợp |
| Code đã viết nhưng chưa qua kiểm thử tích hợp bắt buộc | **Chưa Done**, không tính là Increment |
| Lỗi nghiêm trọng làm tính năng không đáp ứng DoD | Sửa/kiểm chứng hoặc ghi rõ chưa hoàn tất |
| Một phần của PBI lớn đã thành lát cắt độc lập, đáp ứng DoD | Có thể làm rõ cách ghi nhận phần giá trị hoàn chỉnh một cách trung thực |
| Một tính năng chưa hoàn thành nhưng không còn giá trị | Đưa tình trạng cho Product Owner xem lại trong Product Backlog; có thể bỏ |
| Hệ thống production có sự cố khẩn | Xử lý theo mức độ và quy trình sự cố ngay; không trì hoãn vì sự kiện Scrum |

Trong Scrum, **công việc chưa đáp ứng DoD trở về Product Backlog để xem xét**, không tự động được tính là Done hoặc mặc định phải vào Sprint sau. Product Owner quản lý thứ tự Product Backlog; Developers đóng góp thông tin về công việc còn lại, rủi ro và khả thi.

### 20.2. Sprint Review và Retrospective không phải nơi hợp thức hóa lỗi

- **Sprint Review:** Kiểm tra Increment thực sự hoàn chỉnh, tiến độ tới Product Goal, phản hồi và bước tiếp theo. Không trình bày phần chưa đạt DoD như Increment Done.
- **Sprint Retrospective:** Xem cách làm, luồng chờ, lỗi lặp và điều kiện chất lượng; chọn cải tiến nhỏ có thể kiểm chứng.

Lỗi được nêu trong Sprint Review **không phải điều đáng xấu hổ**. Đáng lo là **che rủi ro, tuyên bố Done sai hoặc không tạo điều kiện sửa nguyên nhân**.

## 21. Tình huống thực tế: nhóm workshop dồn QA cuối Sprint

Một Scrum Team có Sprint hai tuần. Sprint Goal là:

> **Học viên đủ điều kiện đăng ký được workshop còn chỗ và nhìn thấy trạng thái đáng tin.**

Nhóm chọn bốn PBI:

| PBI | Giá trị dự kiến | Rủi ro cần kiểm chứng |
| --- | --- | --- |
| A. Xem workshop còn chỗ | Người học tìm được buổi phù hợp | Dữ liệu còn chỗ không bị sai |
| B. Đăng ký workshop | Người học tự đăng ký | Đăng ký trùng, tranh chỗ cuối, phân quyền |
| C. Xem trạng thái đăng ký | Biết kết quả thực tế | Không lộ dữ liệu người khác |
| D. Email xác nhận | Bớt phải kiểm tra thủ công | Không gửi sai trạng thái, xử lý thất bại |

### 21.1. Sprint trước: “dev xong hết” nhưng chưa Done

- **Ngày 1–3:** Developers bắt đầu cả bốn PBI, chưa thống nhất các ví dụ cạnh tranh.
- **Ngày 4–6:** Nhiều phần code hoàn tất trên nhánh riêng, review bị trì hoãn.
- **Ngày 7:** QA nhận một lô thay đổi lớn; môi trường test chưa sẵn sàng.
- **Ngày 8:** Phát hiện hai học viên có thể xác nhận chỗ cuối.
- **Ngày 9:** Phát hiện C lộ trạng thái đăng ký của người khác.
- **Ngày 10:** Nhóm cố sửa cả lỗi, test lại và demo; D chưa kiểm chứng lỗi gửi mail.

Nếu nhóm đánh dấu B, C, D Done chỉ để có kết quả Sprint, họ đang **che việc chưa đạt chất lượng**. Việc người dùng nhận một trạng thái sai có thể nguy hiểm hơn việc chưa có email xác nhận.

### 21.2. Thử thay đổi trong Sprint kế tiếp

Nhóm thống nhất:

1. **Làm rõ A, B, C bằng ví dụ chấp nhận trước khi bắt đầu**, đặc biệt tình huống đồng thời và phân quyền.
2. **Chia nhỏ lát cắt** để có thể review, tích hợp và kiểm thử ngay trong tuần đầu.
3. **Giới hạn WIP**, ưu tiên giúp item cũ tới DoD trước khi mở thêm.
4. **CI chạy unit/integration checks theo rủi ro** trên các thay đổi liên quan.
5. **Kiểm thử tham gia từ sớm** để xác nhận dữ liệu thử và môi trường.
6. **Daily Scrum nhìn Sprint Goal và các item đang chờ**, không chỉ báo cáo ai đã code xong.
7. **Product Owner làm rõ ưu tiên**, có thể dời D nếu không phải điều kiện bắt buộc của Sprint Goal hoặc nghĩa vụ khác.

### 21.3. Kế hoạch theo ngày minh họa

| Thời điểm | Trọng tâm | Bằng chứng mong muốn |
| --- | --- | --- |
| Ngày 1 | Làm rõ hành vi và các rủi ro quan trọng | Ví dụ chấp nhận, tiêu chuẩn Done và dữ liệu thử |
| Ngày 2–3 | Lát cắt A từ đầu tới cuối | Tích hợp, test, review và Done cho A |
| Ngày 3–6 | Lát cắt B gồm quyền và xử lý đồng thời | Test unit + integration, phản hồi sớm khi lỗi |
| Ngày 5–8 | Lát cắt C và xem lại trạng thái B | Kiểm chứng phân quyền và dữ liệu liên quan |
| Ngày 8–9 | Cân nhắc D khi năng lực và ưu tiên cho phép | Không mở D nếu B/C còn bị chặn nghiêm trọng |
| Ngày 10 | Review Increment và cải tiến cách làm | Chỉ tính Done phần thật sự đạt tiêu chuẩn |

Đây **không phải lịch bắt buộc**, và các khoảng có thể chồng lấn. Nếu B bộc lộ vấn đề mới, kế hoạch phải điều chỉnh theo dữ liệu, không cố giữ mọi ngày bằng cách bỏ kiểm thử.

### 21.4. Kết quả cần xem sau thử nghiệm

Thay vì kết luận “đã cải tiến vì có nhiều test hơn”, nhóm hỏi:

- Có hạng mục nào đạt DoD ngay giữa Sprint không?
- Thời gian chờ review/kiểm thử có giảm?
- Work item age của những PBI đang mở có giảm hoặc ổn định hơn?
- Lỗi dữ liệu/phân quyền được phát hiện trước khi gần hết Sprint?
- QA và Developers có phối hợp sớm hơn mà không tạo quá tải?
- Người học thử lát cắt có nhận trạng thái đúng và hiểu cách sử dụng?
- Nếu còn PBI chưa hoàn tất, lý do được ghi nhận có ích để quyết định tiếp không?

## 22. Kế hoạch thử nghiệm cải tiến trong hai Sprint

Chọn một cải tiến có thể quan sát, không bắt đầu đồng thời quá nhiều sáng kiến.

### 22.1. Đường cơ sở

Trong một đến vài Sprint trước, nhóm thu dữ liệu đủ tin:

| Dữ liệu | Mục đích |
| --- | --- |
| Số PBI đạt DoD theo từng thời điểm trong Sprint | Thấy có thực sự hoàn tất tăng dần hay dồn cuối |
| WIP ở review/test và work item age | Thấy hàng đợi và item có nguy cơ kéo dài |
| Loại lỗi được phát hiện, thời điểm và mức độ | Biết lỗi thường lộ muộn ở đâu |
| Thời gian chờ môi trường, phụ thuộc và reviewer | Tìm rào cản không nằm ở người viết code |
| Lỗi lọt sau phát hành và phản hồi người dùng | Đảm bảo cải thiện không hy sinh chất lượng |

Không nên dựng lại dữ liệu lịch sử theo cách suy đoán. Nếu trước đây không đo queue time, **bắt đầu thu từ hiện tại**, đồng thời ghi hạn chế khi so sánh.

### 22.2. Giả thuyết thử nghiệm

> **Nếu** nhóm thống nhất ví dụ chấp nhận sớm, chia PBI nhỏ và đặt giới hạn WIP tại vùng chờ kiểm chứng, **thì** nhiều lát cắt có thể đạt DoD sớm hơn và hàng đợi lỗi cuối Sprint sẽ giảm, **với điều kiện** các kiểm tra chất lượng cốt lõi vẫn được giữ.

### 22.3. Trách nhiệm thực hiện

- Developers tự điều chỉnh cách chia và hoàn tất PBI, tích hợp sớm.
- Người có chuyên môn kiểm thử hỗ trợ thiết kế test và dữ liệu từ đầu.
- Product Owner làm rõ giá trị, ưu tiên và điều kiện chấp nhận.
- Scrum Master giúp nhóm xem trở ngại, phản hồi, tự quản và cải tiến.
- Những nhóm phụ thuộc cung cấp môi trường, bảo mật hoặc quyền phù hợp.

### 22.4. Tiêu chí kiểm chứng

Sau hai Sprint, nhóm so sánh:

1. Phần trăm PBI Done vào giữa Sprint **chỉ dùng để quan sát xu hướng**, không làm KPI ép đóng thẻ.
2. Work item age và thời gian chờ review/test.
3. Số lỗi nghiêm trọng phát hiện quá muộn.
4. Lỗi lọt production và lượng công việc làm lại.
5. Khả năng đạt Sprint Goal và chất lượng Increment.
6. Trải nghiệm hợp tác và mức quá tải thực tế của nhóm.

Nếu bảng QA trống hơn nhưng bug sản phẩm tăng, **cần xem lại cách đo và chính sách Done**. Nếu số lỗi phát hiện trước khi merge tăng nhưng lỗi lọt production giảm, đó có thể là tín hiệu tích cực của việc phản hồi sớm.

## 23. Những sai lầm thường gặp

| Hiểu lầm/sai lầm | Vì sao gây hại | Cách điều chỉnh |
| --- | --- | --- |
| “QA chịu trách nhiệm cuối cùng về mọi chất lượng” | Tạo hàng đợi và giao tiếp muộn | Chất lượng thuộc trách nhiệm cộng tác của nhóm tạo Increment |
| “Dev Done nghĩa là Done” | Báo tiến độ sai, che công việc chưa kiểm chứng | Chính sách Done phản ánh trạng thái thật |
| “Cứ đẩy nhiều story sang test là tiến độ tốt” | Tạo backlog kiểm chứng, WIP tăng | Theo dõi Done toàn luồng và thời gian chờ |
| “Bỏ test để giữ deadline” | Chuyển rủi ro sang người dùng và làm lại | Dời phạm vi tùy chọn, không hạ chất lượng |
| “Cuối Sprint mới tích hợp thì dễ quản lý” | Lỗi và xung đột xuất hiện khi đã quá muộn | Tích hợp và review thay đổi nhỏ thường xuyên |
| “Càng nhiều E2E test càng an toàn” | Suite chậm, flaky, chưa chắc phủ đúng rủi ro | Phân tầng test theo loại lỗi và tốc độ phản hồi |
| “100% coverage chứng minh chất lượng” | Có thể test không assert đúng hoặc thiếu tích hợp | Dùng coverage như tín hiệu, bổ sung kiểm chứng rủi ro |
| “Flaky thì cứ retry tới xanh” | Che test không tin cậy và lỗi thật | Điều tra, sửa nguyên nhân, theo dõi ngoại lệ |
| “Lỗi phát hiện sớm tăng là chất lượng đang tệ đi” | Trừng phạt việc tìm lỗi và giảm minh bạch | Xem thời điểm, mức độ và lỗi lọt sau giao |
| “Bug nào cũng ưu tiên ngang nhau” | Lỗi nghiêm trọng không được xử lý đúng mức | Triage theo tác động và rủi ro |
| “Số bug đóng là KPI cho từng Developer/QA” | Khuyến khích chia bug nhỏ, che lỗi và tranh trách nhiệm | Đo hệ thống, chất lượng và giá trị người dùng |
| “Chỉ cần tăng thêm QA cuối Sprint” | Chưa xử lý nguyên nhân item lớn và yêu cầu sai | Cùng tham gia sớm, giới hạn WIP, cải thiện cách làm |
| “Giới hạn WIP thì không được giúp nhau” | Mất mục đích pull và swarming | Ưu tiên giúp item tới Done trong ranh giới kỹ năng |
| “Dời lỗi chưa sửa sang bug nhỏ là PBI đã Done” | Hợp thức hóa phần không đạt DoD | Minh bạch PBI chưa hoàn tất |
| “Kiểm thử tự động thay thế mọi đánh giá con người” | Bỏ sót trải nghiệm, rủi ro không có test | Kết hợp tự động và thẩm định theo bối cảnh |
| “Chờ review không phải WIP vì code đã xong” | Che thời gian đi qua luồng và tạo áp lực sai | Thống nhất ranh giới WIP tới Done |
| “Thử một Sprint đã đủ kết luận cải tiến” | Bị ảnh hưởng ngẫu nhiên, loại việc thay đổi | Quan sát nhiều chu kỳ và nêu giới hạn |
| “Người làm càng bận thì hệ thống càng nhanh” | WIP cao, chuyển ngữ cảnh và hàng đợi dài | Tập trung hoàn tất và giảm thời gian chờ |

## 24. Checklist ngăn tồn đọng chất lượng

Mẫu sau chỉ dùng cho **học tập và cải tiến cách làm**, không phải artifact bắt buộc của Scrum.

~~~text
TRUOC KHI BAT DAU PBI
[ ] Gia tri va hanh vi nguoi dung duoc lam ro
[ ] Co vi du chap nhan va rui ro quan trong
[ ] Co du lieu/moi truong kiem chung can thiet
[ ] Item du nho de co the dat Done trong chu ky
[ ] Tieu chuan hoan tat va phu thuoc da duoc hieu

TRONG KHI THUC HIEN
[ ] Test/review duoc bat dau som, khong doi cuoi chu ky
[ ] Thay doi duoc tich hop va kiem chung thuong xuyen
[ ] Loi phat hien duoc sua khi ngu canh con moi
[ ] WIP va work item age duoc nhin thay
[ ] Item bi chan co ly do, nguoi phoi hop va moc xem lai
[ ] Khong bat dau them khi item cu co the duoc hoan tat truoc

TRUOC KHI DANH DAU DONE
[ ] Hanh vi va kiem thu theo rui ro da duoc xac minh
[ ] Khong con loi ngan dat chinh sach Done
[ ] Tich hop, phan quyen, du lieu va van hanh phu hop
[ ] Bang chung va ket qua kiem chung co the truy vet
[ ] Phan chua hoan thanh duoc hien thi trung thuc

KHI KET THUC CHU KY
[ ] Khong tinh PBI chua dat DoD la Increment
[ ] Loi ton dong duoc triage theo tac dong va tuoi
[ ] Product Backlog duoc xem lai theo gia tri/rui ro
[ ] Retrospective chon cai tien nho co bang chung
[ ] Khong dung cac chi so de phat nguoi phat hien loi

THU NGHIEM CAI TIEN
- Nut that dang nghi ngo:
- Bang chung va rui ro:
- Gia thuyet:
- Thay doi nho:
- Dieu kien chat luong khong duoc bo:
- Moc xem lai va tieu chi danh gia:
~~~

Không cần biến checklist thành một thủ tục dài cho mọi thay đổi. Nó giúp nhóm nhớ **điều gì cần kiểm chứng sớm và điều gì không thể bỏ**, nhất là khi có áp lực tiến độ.

## 25. Bài tập thực hành: tìm nguyên nhân chất lượng dồn cuối Sprint

**Bối cảnh:** Một nhóm phát triển nền tảng học tập làm Sprint hai tuần để giao luồng “Học viên xem, đăng ký và hủy workshop”. Các PBI có tiêu chuẩn Done đòi hỏi kiểm thử quyền, trạng thái dữ liệu đúng và khả năng tích hợp.

Cuối ngày thứ bảy, bảng có:

| Item | Trạng thái | Work item age | Rủi ro/chờ |
| --- | --- | ---: | --- |
| A. Xem workshop còn chỗ | Done | 3 ngày khi hoàn tất | Đã tích hợp và kiểm chứng |
| B. Đăng ký chỗ cuối | Chờ integration test | 6 ngày | Chưa có test yêu cầu đồng thời |
| C. Xem đăng ký của mình | Chờ review | 5 ngày | Một reviewer đang xử lý sự cố |
| D. Tự hủy workshop | Đang phát triển | 4 ngày | Chưa rõ giới hạn thời gian hủy |
| E. Email xác nhận | Chờ môi trường | 7 ngày | Dịch vụ thử của đối tác chưa sẵn |
| F. Lọc workshop nâng cao | Đang phát triển | 2 ngày | Tùy chọn, chưa cốt lõi |

Developers muốn bắt đầu thêm hai PBI nhỏ để “không lãng phí thời gian”, trong khi Product Owner muốn demo cả sáu tính năng vào ngày cuối. Một người đề xuất **đánh dấu B và C Done trước để số báo cáo đẹp, kiểm thử sau**.

### Câu hỏi

1. Có những dấu hiệu **hàng đợi và lỗi/kiểm chứng tích tụ** nào?
2. Trong sáu PBI, phần nào thực sự đã đạt Done theo dữ liệu đề bài?
3. Vì sao B chưa Done dù code đã xong? Test nào cần bổ sung và tại sao?
4. Với C, nhóm có thể hỗ trợ reviewer mà không giao quyền review cho người chưa đủ kỹ năng như thế nào?
5. Với D, câu hỏi nghiệp vụ nào nên được làm rõ ngay?
6. Với E, những phương án chia lát cắt hoặc kiểm chứng thay thế nào cần bàn với Product Owner và đối tác?
7. Việc bắt đầu thêm hai PBI khi B/C/E đang chờ có thể gây tác động gì tới WIP và cycle time?
8. Nếu F là tính năng tùy chọn, có thể thương lượng phạm vi ra sao để giữ chất lượng B/C/D?
9. Vì sao đánh dấu B/C Done rồi mở bug mới không phù hợp với DoD?
10. Nếu đã sát cuối Sprint, Scrum Team nên làm gì với PBI chưa đáp ứng DoD?
11. Bạn sẽ chọn **một thử nghiệm cải tiến nhỏ** cho Sprint sau và đo bằng dữ liệu nào?
12. Những loại lỗi nào cần xử lý ngay theo quy trình sự cố và không nên chờ Sprint Planning?

### Gợi ý giải

**B** có rủi ro tính nhất quán dữ liệu chưa được kiểm chứng; **C** bị chờ review; **D** mơ hồ nghiệp vụ; **E** phụ thuộc môi trường. Đây là các điểm khác nhau, không thể gộp thành “QA chậm”. **A** là PBI duy nhất được đề bài xác nhận Done; F đang thực hiện và không phải điều kiện của mục tiêu đăng ký tin cậy.

Nhóm có thể:

- Ưu tiên tạo và chạy integration test cho B với yêu cầu gần đồng thời, kiểm tra trạng thái cuối của database.
- Review sớm C với người đủ thẩm quyền, chia sẻ kiến thức để giảm lệ thuộc.
- Làm rõ với Product Owner quy tắc hủy cho D bằng ví dụ.
- Làm rõ mức bắt buộc của E; kiểm thử phần độc lập, dùng stub/contract test khi phù hợp nhưng **không tuyên bố đã xác minh tích hợp thật**.
- Hạn chế mở thêm việc, tập trung hoàn tất B/C/D trước F nếu phù hợp Sprint Goal và năng lực.
- Giữ DoD; không gọi phần chưa kiểm chứng là Increment.

**Khi hết timebox**, phần chưa đạt DoD quay về Product Backlog để xem xét trong Scrum; không kéo dài Sprint để làm đủ danh sách. Bên cạnh đó, nên xem lại policy WIP, dữ liệu chờ, cách chuẩn bị test và cách chia PBI trong Sprint Retrospective.

## 26. Ghi nhớ và tự kiểm tra

**Ngăn tích tụ lỗi và công việc kiểm chứng ở cuối chu kỳ** không bắt đầu bằng việc yêu cầu QA “test nhanh hơn”. Nó bắt đầu từ **cách nhóm làm rõ yêu cầu, chia lát cắt, tích hợp, review, kiểm thử, sửa lỗi và định nghĩa hoàn tất**. Khi việc kiểm chứng được đưa vào từng PBI, nhóm có thể nhận phản hồi sớm, giảm hàng đợi, bảo vệ chất lượng và giao Increment thực sự có giá trị.

Những nguyên tắc cần giữ:

1. **Không tách chất lượng khỏi công việc phát triển:** Review, test, tích hợp và xử lý lỗi là một phần của việc hoàn thành lát cắt.
2. **Không đánh dấu Done khi chưa đạt tiêu chuẩn:** “Code xong” và “Increment hoàn chỉnh” là hai trạng thái khác nhau.
3. **Nhìn luồng toàn hệ thống:** Giảm WIP và điểm chờ, ưu tiên hoàn tất thay vì mở thêm việc chỉ để mọi người bận.
4. **Phòng lỗi sớm theo rủi ro:** Ví dụ chấp nhận, TDD, CI, integration/security tests và chuyên môn phù hợp.
5. **Triage minh bạch:** Không phải mọi bug giống nhau; lỗi nguy hiểm cần phản ứng ngay, lỗi ít ảnh hưởng cần người sở hữu và xem lại.
6. **Đo để học, không để đổ lỗi:** Kết hợp thời gian chờ, tuổi công việc, lỗi lọt sau giao và phản hồi người dùng.
7. **Cải tiến từng bước:** Dùng thử nghiệm nhỏ, dữ liệu trước/sau và không hy sinh chất lượng để làm đẹp số liệu.

Tự kiểm tra:

1. Vì sao chuyển nhiều thẻ sang “Chờ QA” không đồng nghĩa giao giá trị nhanh?
2. Những nguyên nhân nào thường khiến lỗi và kiểm thử dồn cuối Sprint?
3. User story có tiêu chí chấp nhận rõ giúp phát hiện vấn đề sớm ra sao?
4. Phân biệt task theo tầng kỹ thuật và lát cắt dọc có giá trị.
5. DoD trong Scrum có vai trò gì đối với việc ngăn “Done giả”?
6. Khi nào unit test không đủ, cần integration hoặc security test?
7. TDD và CI giúp giảm làm lại, nhưng có giới hạn gì?
8. WIP và work item age giúp phát hiện kiểm chứng tồn đọng thế nào?
9. Tại sao một flaky test có thể là rủi ro chất lượng thật?
10. Khi lỗi phát hiện trong Sprint tăng nhưng lỗi lọt production giảm, nên diễn giải thế nào?
11. Vì sao việc đếm số bug đóng không phù hợp làm KPI cá nhân?
12. Làm gì khi một PBI chưa qua kiểm thử bắt buộc vào cuối Sprint?
13. Shift left và shift right bổ trợ nhau như thế nào?
14. Một thử nghiệm nhỏ nào giúp giảm hàng đợi review/test mà vẫn giữ chất lượng?
15. Ai cần tham gia để chất lượng là trách nhiệm hợp tác thay vì trạm QA cuối?

Trước khi bắt đầu thêm một PBI, hãy tự hỏi: **“Công việc nào đang chờ được kiểm chứng, điều gì ngăn nó đạt Done, và chúng ta có thể cùng hoàn tất một lát cắt có giá trị mà không đánh đổi chất lượng hay không?”** Trả lời câu hỏi ấy mỗi ngày giúp nhóm **giao phần mềm đáng tin cậy tăng dần, học từ phản hồi sớm và cải tiến liên tục**, thay vì chờ đến cuối chu kỳ mới phát hiện mình còn bao nhiêu việc chưa thực sự hoàn tất.
