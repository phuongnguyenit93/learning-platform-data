# Extreme Programming: Nhịp làm việc bền vững và khả năng duy trì chất lượng

Một nhóm phát triển ứng dụng đăng ký workshop được khen vì liên tục “cứu” thời hạn phát hành: lập trình muộn, bỏ bớt kiểm thử, xử lý lỗi vào cuối tuần. Tháng đầu họ có vẻ giao rất nhanh. Tháng sau, mỗi thay đổi lại làm hỏng một chức năng cũ, người có nhiều kinh nghiệm phải trực hỗ trợ liên tục, story bị chặn ở review và lịch bàn giao ngày càng khó dự đoán. Có thể nhóm đang **tăng tốc ngắn hạn bằng cách vay mượn chất lượng và năng lực của những vòng làm việc sau**.

**Extreme Programming (XP)** quan tâm đến tốc độ thay đổi **có thể duy trì được**. Nhịp làm việc bền vững (*sustainable pace*, thường gắn với cách gọi *energized work*) khuyến khích nhóm tổ chức công việc để tiếp tục phát triển phần mềm chất lượng cao qua nhiều vòng, thay vì phụ thuộc vào làm thêm giờ lặp lại và “người hùng” giải cứu dự án. Các thực hành XP như **test-driven development (TDD), pair programming, continuous integration, refactoring, simple design, collective code ownership, small releases** hỗ trợ mục tiêu đó bằng cách giảm rủi ro và chi phí thay đổi.

Bài học thuộc mô-đun **AGILE_DEVELOPMENT**: hiểu giá trị, nguyên tắc Agile, giao sản phẩm tăng dần, nhận phản hồi sớm, thực hành user story, backlog, Scrum, Kanban, XP và đo lường dòng công việc. Trọng tâm không phải tính một “số giờ chuẩn” cho mọi người mà là **thiết kế một hệ thống làm việc giúp nhóm giữ sức, bảo vệ chất lượng và giao giá trị ổn định**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích nhịp làm việc bền vững trong XP và liên hệ với nguyên tắc Agile về khả năng duy trì tốc độ phát triển lâu dài.
2. Phân biệt **tăng tốc nhất thời** với **khả năng giao sản phẩm ổn định qua nhiều vòng**.
3. Nhận diện vòng xoáy làm thêm giờ – mệt mỏi – lỗi – làm lại – chậm tiến độ.
4. Trình bày cách TDD, pairing, CI, refactoring, thiết kế đơn giản và phát hành nhỏ giúp duy trì chất lượng.
5. Tạo chính sách lập kế hoạch theo năng lực thực tế, quản lý WIP, xử lý gián đoạn và bảo vệ Definition of Done.
6. Chọn tín hiệu về dòng công việc, lỗi, giá trị người dùng và tính bền vững mà không biến thành đánh giá cá nhân.
7. Đề xuất phương án khi Sprint hoặc mốc phát hành bị đe dọa mà không mặc định bắt nhóm làm quá sức.
8. Thực hành một tình huống từ user story đến kiểm thử, quyết định phạm vi, kế hoạch cải tiến và đánh giá kết quả.

## 2. Nhịp bền vững trong XP thực sự có nghĩa gì?

### 2.1. Không phải “làm chậm”, mà là tránh tiêu hao tương lai

Một nhóm có nhịp bền vững:
- Có thể **hoàn thành công việc đáp ứng tiêu chuẩn chất lượng** lặp lại qua nhiều chu kỳ.
- Không cần duy trì trạng thái khẩn cấp, làm đêm hoặc cuối tuần như một điều kiện bình thường để đạt kế hoạch.
- Đủ thời gian để kiểm tra, tích hợp, sửa thiết kế khi cần và chia sẻ kiến thức.
- Có khả năng xử lý nhu cầu mới mà không làm mọi việc đang làm dở.
- Chủ động nhận diện giới hạn năng lực, phụ thuộc và rủi ro.
- Học từ phản hồi người dùng và cải thiện cách làm việc thay vì tích lũy lỗi phải sửa về sau.

**Nhịp bền vững không có nghĩa mọi tuần đều giống nhau.** Có thể xảy ra sự cố production khiến nhóm cần ứng phó khẩn; điều quan trọng là có cơ chế hỗ trợ, phục hồi, bù đắp và phòng ngừa, không coi trạng thái bất thường ấy thành cách vận hành mặc định.

### 2.2. Từ “40-hour week” đến energized work

Trong lịch sử XP, thực hành **“40-hour week”** được dùng để phản đối việc xem làm thêm giờ kéo dài như phương án tăng sản lượng. Trong nhiều cách trình bày XP hiện đại, trọng tâm được diễn đạt là **“energized work”**: con người cần đủ năng lượng và điều kiện để suy nghĩ, cộng tác và giữ chất lượng.

Không nên rút ra rằng **40 giờ mỗi tuần là tiêu chuẩn bắt buộc toàn cầu** cho mọi nhóm, mọi người hoặc mọi pháp luật lao động. Lịch làm việc thực tế phải tôn trọng quy định, hợp đồng, múi giờ, điều kiện cá nhân và nhu cầu vận hành. Tinh thần của thực hành là **không xây kế hoạch dựa trên việc phải thường xuyên làm quá sức**.

### 2.3. Liên hệ với nguyên tắc Agile

Một nguyên tắc trong Agile Manifesto nhấn mạnh rằng **Agile processes promote sustainable development**: những bên tài trợ, Developers và người dùng cần có khả năng **duy trì nhịp phát triển không giới hạn về mặt nguyên tắc**, thay vì chỉ tối ưu một đợt.

Ở đây, “không giới hạn” không phải lời hứa sản phẩm tồn tại mãi mãi. Nó là yêu cầu thiết kế một phương thức làm việc **không tự phá hủy khả năng tiếp tục phát triển** sau vài vòng.

### 2.4. Nhịp bền vững không đồng nghĩa luôn thư thả

Một nhóm làm việc bền vững vẫn có thể rất tập trung, giải quyết bài toán khó, phát hành thường xuyên và phản ứng nhanh khi cần. Sự khác biệt nằm ở **tính có thể lặp lại**: nhóm không cần trả giá bằng lỗi nghiêm trọng, sức khỏe, sự phụ thuộc vào một người hoặc nợ kỹ thuật ngoài tầm kiểm soát.

| Cách làm | Nhìn trong một tuần | Hệ quả có thể xảy ra sau nhiều vòng |
| --- | --- | --- |
| Dồn việc, bỏ test, làm đêm | Nhiều tính năng báo “xong” | Lỗi và làm lại tăng, khó dự báo |
| Làm ít đầu việc, hoàn tất đạt DoD | Số thẻ đóng có thể thấp hơn | Tích hợp đều, phản hồi sớm, giảm việc tồn |
| Pairing để xử lý vùng mã khó | Hai người tập trung cùng một việc | Phát hiện lỗi sớm, chia sẻ kiến thức |
| Chỉ một chuyên gia giải quyết mọi việc | Ban đầu có thể rất nhanh | Hàng chờ và rủi ro phụ thuộc cá nhân |
| Refactoring được thực hiện cùng test | Có công việc không hiện thành tính năng mới | Dễ thay đổi hơn, ít lỗi lặp lại nếu làm đúng |

Các hệ quả trong bảng là **khả năng cần kiểm chứng**, không phải quan hệ nhân quả luôn đúng trong mọi tổ chức.

## 3. Chất lượng và tốc độ dài hạn liên quan thế nào?

### 3.1. Chi phí sửa lỗi tăng khi phát hiện muộn

Một lỗi quy tắc đăng ký có thể dễ sửa khi Developers đang viết test. Nếu chỉ phát hiện sau khi đã gửi xác nhận chỗ sai cho người dùng, nhóm còn phải điều tra dữ liệu, giải thích với khách hàng, khôi phục dịch vụ và tránh tái diễn.

Vì vậy XP đề cao **vòng phản hồi kỹ thuật ngắn**:
- Kiểm tra giả định trước hoặc ngay khi thực hiện thay đổi.
- Tích hợp thường xuyên để thấy xung đột sớm.
- Chỉnh cấu trúc mã ở quy mô nhỏ, có kiểm thử bảo vệ.
- Bàn giao những lát cắt có ích để nhận phản hồi về sản phẩm.

Không thể bảo đảm mọi lỗi đều được tìm thấy sớm, nhưng nhóm có thể giảm **thời gian và phạm vi ảnh hưởng** của nhiều loại lỗi.

### 3.2. Vòng xoáy phản hồi tiêu cực

~~~mermaid
flowchart TD
    A[Cam kết vượt năng lực thực tế] --> B[Áp lực thời gian và làm thêm giờ lặp lại]
    B --> C[Mệt mỏi, chuyển ngữ cảnh, bỏ bớt kiểm tra]
    C --> D[Lỗi, tích hợp khó, khó bảo trì]
    D --> E[Tăng việc sửa lại, hỗ trợ, điều tra sự cố]
    E --> F[Ít năng lực hơn cho công việc mới]
    F --> A
~~~

Cách thoát không phải chỉ yêu cầu “mọi người cố gắng cẩn thận hơn”. Nhóm cần **thay đổi hệ thống lựa chọn và dòng công việc**: ưu tiên theo giá trị, giảm WIP, bảo vệ chất lượng, dự báo từ năng lực thực tế, làm rõ phụ thuộc và xử lý nguyên nhân lỗi.

### 3.3. Vòng phản hồi tích cực

~~~mermaid
flowchart TD
    A[Chọn lát cắt nhỏ theo giá trị] --> B[Test và thiết kế rõ, tích hợp thường xuyên]
    B --> C[Increment đáp ứng chất lượng]
    C --> D[Phản hồi sớm từ người dùng và vận hành]
    D --> E[Điều chỉnh backlog và hiểu rủi ro tốt hơn]
    E --> F[Ít làm lại, tăng khả năng dự báo]
    F --> A
~~~

Hai vòng trên là **mô hình tư duy**, không phải số liệu định lượng. Nhóm cần xem liệu dữ liệu thực tế có cho thấy những mối liên hệ đó không.

### 3.4. Phân biệt nợ kỹ thuật và công việc chất lượng cần thiết

Nợ kỹ thuật có thể là lựa chọn có ý thức chấp nhận một chi phí tương lai để lấy lợi ích hiện tại, hoặc hậu quả của việc thường xuyên thiếu tiêu chuẩn. Không nên gọi **mọi mã chưa hoàn hảo** là nợ kỹ thuật; cũng không nên dùng “chúng tôi đang bận” để bỏ qua kiểm tra an toàn bắt buộc.

Một khoản cần xử lý nên được diễn đạt cụ thể:
- Rủi ro hoặc chi phí thay đổi đang phát sinh ở đâu?
- Người dùng hoặc khả năng giao giá trị nào bị ảnh hưởng?
- Cần sửa đến mức nào để giảm rủi ro?
- Chỉ số hoặc tình huống nào cho thấy cải thiện?

Ví dụ: “Bổ sung kiểm thử cho trường hợp hai đăng ký đồng thời ở suất cuối để tránh xác nhận vượt sức chứa” rõ và có thể kiểm chứng hơn “làm sạch code”.

## 4. Những yếu tố làm nhịp làm việc mất bền vững

### 4.1. Cam kết vượt năng lực và thiếu vùng đệm

Nếu nhóm đã lên kế hoạch hết mọi giờ có sẵn cho story mới, một yêu cầu hỗ trợ nhỏ hay lỗi production đều buộc người khác làm thêm hoặc bỏ kiểm thử. Năng lực thực tế luôn chịu ảnh hưởng của trao đổi, học hỏi, nghỉ phép, phụ thuộc, bảo trì và sự cố.

**Lập kế hoạch không phải phép cộng toàn bộ giờ có thể ngồi trước máy.** Cần tính thời gian khả dụng thực sự cho công việc hoàn tất đạt chất lượng và xem lịch sử gián đoạn.

### 4.2. WIP cao và công việc dở dang

Work in Progress cao khiến nhiều item chờ review, chờ môi trường, chờ nghiệp vụ hoặc chờ một người có chuyên môn. Mọi người trông có vẻ bận, nhưng throughput có thể không tăng và work item age có thể dài hơn.

Một chính sách pull hoặc giới hạn WIP phù hợp khuyến khích **hoàn tất trước khi bắt đầu thêm**. Không nên coi WIP limit là chuẩn Kanban bắt buộc có một con số áp dụng cho mọi nhóm.

### 4.3. Phụ thuộc vào một người

Nếu chỉ một Developers hiểu triển khai, phân quyền hoặc bộ test, người đó dễ trở thành “điểm khẩn cấp” mỗi khi có vấn đề. Làm thêm giờ của một chuyên gia không giải quyết gốc của rủi ro phụ thuộc.

**Pairing, rotation, tài liệu ngắn và collective ownership** có thể phân tán hiểu biết. Việc luân chuyển cần có thời gian học, không chỉ chuyển trách nhiệm trên bảng.

### 4.4. Hàng chờ chất lượng bị che khuất

Một số hệ thống chỉ hiển thị cột “Đang phát triển” và “Done”, nhưng code có thể nằm nhiều ngày chờ review hoặc test. Nếu nhóm đánh dấu “Done” ngay sau khi viết mã, dữ liệu tiến độ đẹp nhưng Increment chưa sẵn sàng.

Cần **Definition of Done (DoD)** hoặc chính sách hoàn tất rõ, hiển thị hàng chờ và đo thời gian từ bắt đầu đến hoàn tất phù hợp dịch vụ.

### 4.5. Văn hóa khuyến khích cứu hỏa

Nếu người được công nhận luôn là người thức đêm “giải cứu”, còn người chủ động ngăn lỗi bằng test và cải tiến hệ thống không được ghi nhận, nhóm có thể vô tình thưởng cho nguyên nhân tạo ra các sự cố lặp lại.

Thay vì khen số giờ làm đêm, hãy công nhận **khả năng ngăn lỗi, chia sẻ kiến thức, cải thiện dòng công việc và giao kết quả an toàn**.

## 5. Các thực hành XP hỗ trợ nhịp bền vững

Không có một thực hành đơn lẻ bảo đảm thành công. Chúng **bổ trợ lẫn nhau**: TDD khó duy trì nếu CI luôn hỏng; pairing giảm phụ thuộc nhưng sẽ kém hiệu quả nếu không có thời gian học; refactoring cần test để đổi thiết kế tự tin.

| Thực hành XP | Cơ chế hỗ trợ chất lượng | Đóng góp vào nhịp bền vững | Điểm cần tránh |
| --- | --- | --- | --- |
| **Test-driven development (TDD)** | Vòng red–green–refactor, buộc làm rõ hành vi và phản hồi sớm | Giảm lỗi phát hiện muộn, hỗ trợ thiết kế dễ thay đổi | Chỉ viết test hình thức hoặc coi unit test thay thế mọi kiểm thử |
| **Pair programming** | Hai người cùng xử lý, trao đổi hiểu biết và kiểm tra liên tục | Giảm phụ thuộc cá nhân, phát hiện hiểu nhầm sớm | Ép cặp liên tục không phù hợp hoặc xem pairing là hai người làm một việc “mất năng suất” |
| **Continuous integration (CI)** | Tích hợp thay đổi thường xuyên, chạy kiểm tra tự động | Phát hiện xung đột sớm, giảm công việc tích hợp cuối kỳ | Cố tình bỏ qua pipeline đỏ |
| **Refactoring** | Cải thiện cấu trúc mã nhưng giữ hành vi quan sát được | Giảm chi phí thay đổi về sau | Sửa toàn bộ hệ thống không gắn nhu cầu, không có test bảo vệ |
| **Simple design** | Chọn cấu trúc đủ giải quyết yêu cầu hiện tại | Giảm chi phí xây và bảo trì tính năng chưa cần | Hiểu nhầm “đơn giản” là bỏ kiểm tra quan trọng |
| **Small releases** | Giao lát cắt nhỏ có giá trị, thu phản hồi thường xuyên | Hạn chế khối lượng làm lại khi giả định sai | Phát hành chức năng chưa đạt tiêu chuẩn chỉ để “nhỏ và nhanh” |
| **Collective code ownership** | Nhóm có thể cải thiện mã chung với nguyên tắc và chất lượng thống nhất | Ít nút thắt một người, cải thiện khả năng ứng phó | Sửa tùy tiện không review, không hiểu rủi ro |
| **Coding standards** | Quy ước chung giúp đọc và sửa mã nhất quán | Giảm tranh luận lặt vặt, hỗ trợ review/pairing | Tập trung quá mức vào hình thức mà bỏ qua hành vi |
| **Whole team / customer collaboration** | Thông tin nghiệp vụ sớm, ít hiểu sai yêu cầu | Giảm thời gian chờ làm rõ, bớt làm lại | Bỏ qua việc xác minh với người dùng thật |
| **Energized work / sustainable pace** | Có nhịp, sức và điều kiện để suy nghĩ, học hỏi và làm việc chất lượng | Tránh phụ thuộc vào làm thêm giờ kéo dài | Đồng nhất với một số giờ tuyệt đối cho mọi người |

### 5.1. Không chọn kỹ thuật theo khẩu hiệu

Nếu nhóm thiếu test hồi quy cho khu vực thay đổi nhiều, ưu tiên TDD và kiểm thử có thể tạo giá trị. Nếu chất lượng tốt nhưng công việc thường chờ một reviewer độc nhất, pairing/rotation và chính sách review có thể có tác động lớn hơn. Nếu mỗi đợt release cần gộp hàng chục thay đổi lớn, cải thiện CI và nhỏ hóa phạm vi bàn giao có thể quan trọng.

**Chọn thực hành dựa trên nút thắt và rủi ro hiện tại, thử rồi quan sát**, không đo “mức XP” bằng số kỹ thuật đã được liệt kê trong quy trình.

## 6. TDD: rút ngắn vòng phản hồi trước khi lỗi thành nợ

### 6.1. Vòng red – green – refactor

TDD thường được mô tả bằng ba bước lặp lại với thay đổi nhỏ:

1. **Red:** viết một bài kiểm thử mô tả hành vi mong muốn và xác nhận nó thất bại vì hành vi chưa được triển khai.
2. **Green:** viết lượng mã vừa đủ để bài kiểm thử mới cùng các kiểm thử liên quan chạy đạt.
3. **Refactor:** cải thiện cấu trúc thiết kế, giữ hành vi được bảo vệ bởi kiểm thử.

~~~mermaid
flowchart LR
    A[Red: test mới thất bại đúng lý do] --> B[Green: triển khai tối thiểu để test đạt]
    B --> C[Refactor: cải thiện cấu trúc, giữ hành vi]
    C --> D[Chạy toàn bộ kiểm tra liên quan]
    D --> A
~~~

Mục đích không phải tạo thật nhiều test để tăng chỉ số. TDD giúp Developers **diễn đạt hành vi có thể kiểm tra**, tách trách nhiệm và phát hiện một số lỗi sớm hơn.

### 6.2. Ví dụ quy tắc nghiệp vụ đăng ký

Nhóm cần bảo đảm **không xác nhận thêm học viên nếu buổi đã đủ chỗ**.

Một phép thử đơn vị ở mức mô tả:

~~~java
// Ví dụ đơn giản minh họa cách nghĩ theo TDD.
// Mã test và lớp nghiệp vụ cần hoàn thiện theo framework thực tế.
@Test
void khongChoXacNhanNeuBuoiDaDay() {
    RegistrationPolicy policy = new RegistrationPolicy();
    assertFalse(policy.canConfirm(10, 10));
}

@Test
void coTheXacNhanNeuConCho() {
    RegistrationPolicy policy = new RegistrationPolicy();
    assertTrue(policy.canConfirm(9, 10));
}
~~~

Sau khi thấy test thất bại ở vòng Red, Developers triển khai logic nhỏ:

~~~java
public final class RegistrationPolicy {
    public boolean canConfirm(int confirmedCount, int capacity) {
        if (confirmedCount < 0 || capacity < 0) {
            throw new IllegalArgumentException("Số lượng không hợp lệ");
        }
        return confirmedCount < capacity;
    }
}
~~~

Ví dụ này **chỉ bảo vệ phép kiểm tra trên các giá trị đầu vào được cung cấp**. Nó **không giải quyết hoàn chỉnh tình huống hai yêu cầu đồng thời**: cả hai luồng có thể đọc cùng giá trị 9 rồi cùng xác nhận, vượt sức chứa 10. Sản phẩm thật phải có **cơ chế cập nhật nguyên tử hoặc kiểm soát cạnh tranh phù hợp** và kiểm thử tích hợp/đồng thời tại ranh giới dữ liệu, thay vì suy rằng hai unit test trên đủ để an toàn.

### 6.3. TDD không thay thế các cấp kiểm thử khác

| Loại kiểm tra | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| **Unit test** | Quy tắc nhỏ có xử lý đúng các đầu vào? | Số đã xác nhận bằng sức chứa phải từ chối |
| **Integration test** | Thành phần và dữ liệu phối hợp đúng? | Hai request đồng thời không làm vượt sức chứa |
| **Contract/API test** | Giao diện giữa các thành phần giữ cam kết? | API trạng thái trả đúng trạng thái hợp lệ |
| **End-to-end / acceptance** | Người dùng thực hiện được luồng có ích? | Học viên đăng ký, thấy trạng thái, không đọc dữ liệu của người khác |
| **Security / resilience checks** | Quyền, dữ liệu và lỗi hệ thống được xử lý an toàn? | Không lộ thông tin, retry không tạo xác nhận trùng |

Không phải mọi story đều cần số lượng test cố định ở mỗi tầng. Nhóm chọn **loại kiểm tra theo rủi ro và yêu cầu thực**, tránh dựa một chỉ số coverage để tuyên bố phần mềm không còn lỗi.

### 6.4. Khi TDD mới áp dụng khiến nhóm có vẻ chậm hơn

Ban đầu, viết test trước, thiết kế theo lát cắt và làm quen công cụ có thể cần thêm thời gian. Nếu chỉ nhìn số story hoàn tất của một Sprint, có thể hiểu nhầm “TDD làm chậm đội”. Cần quan sát qua vài vòng:
- Lỗi phát hiện sau phát hành có giảm không?
- Thời gian sửa một thay đổi mới có giảm không?
- Pipeline có ổn định hơn không?
- Code có dễ thay đổi mà không làm hỏng hành vi cũ không?
- Nhóm có thể giao lát cắt nhỏ đáng tin hơn không?

TDD là **đầu tư nhằm giảm chi phí thay đổi**, cần được kiểm chứng theo bối cảnh chứ không được coi là điều kỳ diệu tự động tăng năng suất.

## 7. Pair programming và collective ownership: giảm phụ thuộc, tăng khả năng học

### 7.1. Pairing là cộng tác có chủ đích

Trong **pair programming**, hai Developers cùng làm trên một vấn đề, liên tục trao đổi ý định, giả định, thiết kế và kết quả kiểm tra. Có thể luân phiên vai trò **driver** (thao tác) và **navigator** (giữ bức tranh, kiểm tra giả định, đề xuất hướng đi).

Một phiên có ích cần có:
- Mục tiêu cụ thể, chẳng hạn test quy tắc chống xác nhận trùng.
- Cả hai thực sự tham gia suy nghĩ, không phải một người làm và người kia ngồi xem.
- Luân chuyển quyền thao tác phù hợp.
- Dừng lại khi cần giải thích kiến thức nền, không dùng pairing để gây áp lực.
- Kết thúc với mã/test hoặc điều học được có thể chia sẻ.

### 7.2. Pairing không đồng nghĩa hai người phải ở cạnh nhau cả ngày

Nhịp làm việc phù hợp có thể bao gồm **pairing theo vùng mã khó, theo rủi ro hoặc để học kiến thức**, xen kẽ thời gian tập trung cá nhân. Một số hoàn cảnh hoặc nhu cầu tiếp cận khác nhau cần điều chỉnh cách phối hợp.

Các biến thể:
- **Driver–navigator:** hai người xem một bài toán, đổi vai định kỳ.
- **Ping-pong TDD:** một người viết test đỏ, người còn lại triển khai test xanh, sau đó đổi.
- **Mob/ensemble programming:** cả nhóm nhỏ giải một vấn đề chung khi chi phí chia nhỏ/đồng bộ cao; không phải lựa chọn mặc định cho mọi task.
- **Remote pairing:** chia sẻ không gian làm việc và giao tiếp rõ, có nghỉ ngắn, tránh làm việc liên tục qua giờ khác múi giờ.

### 7.3. Collective ownership giảm bus factor khi có nền tảng phù hợp

**Collective code ownership** nghĩa là mã không bị “khóa” vĩnh viễn cho một cá nhân. Người khác có thể sửa trong phạm vi hiểu biết và chính sách chung, nhờ:
- Test hồi quy chạy tin cậy.
- Quy ước code và review.
- Pairing và chuyển giao bối cảnh.
- Tài liệu/decision log ngắn ở các rủi ro quan trọng.
- Quyền truy cập theo nguyên tắc an toàn và trách nhiệm phù hợp.

Không nên diễn giải collective ownership thành “ai cũng có quyền sửa production không cần kiểm tra”. Chất lượng và quản lý truy cập vẫn là những ràng buộc bắt buộc.

### 7.4. Ví dụ giảm rủi ro một người trực hỗ trợ

Giả sử chỉ một người hiểu cơ chế gửi email sau đăng ký. Khi hệ thống gặp lỗi, người đó thường xuyên phải xử lý vào buổi tối.

Nhóm có thể:
1. Dành một phiên pairing để người khác hiểu luồng và viết test cho tình huống email gửi thất bại.
2. Ghi các bước quan sát, retry, kiểm tra trạng thái và phục hồi trong runbook.
3. Luân chuyển reviewer của thay đổi liên quan.
4. Diễn tập tình huống trên môi trường an toàn.
5. Kiểm tra sau vài vòng xem còn phụ thuộc độc nhất vào một cá nhân không.

Việc này **không bảo đảm có thể bỏ trực vận hành**, nhưng làm giảm nguy cơ một người phải giải quyết mọi vấn đề một mình.

## 8. CI, refactoring và thiết kế đơn giản: bảo vệ khả năng thay đổi

### 8.1. Continuous integration giúp lỗi không tích lũy âm thầm

CI trong tinh thần XP là **tích hợp thay đổi thường xuyên**, nhận phản hồi nhanh về build, test và sự tương thích của các thay đổi. Pipeline tự động hóa là phương tiện; **CI không chỉ là cài đặt một công cụ chạy lệnh**.

Một thói quen phù hợp:
- Giữ thay đổi nhỏ để dễ review và kiểm tra.
- Tích hợp thường xuyên vào nhánh chung theo chính sách của nhóm.
- Tự động chạy những kiểm tra có giá trị.
- Khi pipeline hỏng, ưu tiên đưa nó về trạng thái đáng tin trước khi chồng thêm thay đổi.
- Theo dõi test không ổn định (*flaky*) để tránh việc nhóm học cách bỏ qua cảnh báo đỏ.

Không nên tắt test thất bại mà không có đánh giá và kế hoạch sửa chỉ vì muốn biểu đồ tích hợp xanh.

### 8.2. Refactoring là thay cấu trúc, không phải thay hành vi

**Refactoring** cải thiện cấu trúc mã trong khi giữ nguyên hành vi bên ngoài theo phạm vi kiểm chứng. Ví dụ: tách logic xác định trạng thái đăng ký ra khỏi lớp gửi email để thay kênh thông báo dễ hơn.

Một vòng refactoring an toàn:
1. Xác định hành vi cần giữ và kiểm tra hiện có.
2. Bổ sung test nếu thiếu bảo vệ ở vùng thay đổi quan trọng.
3. Sửa cấu trúc bằng các bước nhỏ.
4. Chạy test và kiểm tra hồi quy sau từng bước phù hợp.
5. Tích hợp thường xuyên và quan sát kết quả.

**Không nên gộp một cuộc viết lại toàn bộ kiến trúc vào một story nhỏ** rồi gọi đó là refactoring nếu hành vi, phạm vi và rủi ro đã đổi đáng kể.

### 8.3. Thiết kế đơn giản nhưng có khả năng mở rộng bằng học hỏi

XP khuyến khích thiết kế **đủ cho những yêu cầu đã biết**, tránh xây trước kiến trúc phức tạp cho các kịch bản chưa có bằng chứng. Đơn giản không có nghĩa bỏ qua các quy tắc dữ liệu, bảo mật hay tính đúng đắn.

Ví dụ: sản phẩm chưa xác minh nhu cầu SMS. Nhóm có thể giữ logic “trạng thái đăng ký” độc lập với việc gửi thông báo; không cần xây ngay nền tảng tích hợp mười kênh. Khi phản hồi người dùng xác nhận nhu cầu, nhóm đưa ra quyết định dựa trên bằng chứng mới.

### 8.4. Small releases không có nghĩa release liều lĩnh

Lát cắt nhỏ giúp:
- Giảm phạm vi phải kiểm tra mỗi lần.
- Phản hồi người dùng nhanh hơn.
- Phát hiện giả định sai trước khi xây nhiều chức năng.
- Giảm chi phí điều tra khi thay đổi gây lỗi.
- Tạo cơ hội rollback hoặc giảm phạm vi ảnh hưởng.

Nhưng chỉ phát hành khi đáp ứng điều kiện chất lượng và vận hành phù hợp: DoD, bảo mật, dữ liệu, monitoring, phương án xử lý lỗi nếu cần. **Phát hành thường xuyên không đồng nghĩa bỏ bước bảo vệ quan trọng**.

## 9. Definition of Done: chất lượng không biến mất khi Sprint sắp kết thúc

### 9.1. DoD là ranh giới giữa “đã làm việc” và “hoàn tất”

Trong Scrum, **Definition of Done** mô tả trạng thái của Increment khi đáp ứng các tiêu chuẩn chất lượng cần có. XP có thể cung cấp các thực hành kỹ thuật giúp thực hiện những tiêu chuẩn đó. Các nhóm không dùng Scrum vẫn cần chính sách hoàn tất và bàn giao rõ.

Một DoD minh họa cho nhóm workshop có thể yêu cầu:
- Hành vi phù hợp acceptance criteria đã thống nhất.
- Mã được tích hợp và review theo chính sách nhóm.
- Kiểm thử tự động và thủ công cần thiết theo rủi ro đã đạt.
- Không có lỗi nghiêm trọng đã biết làm sai dữ liệu đăng ký hoặc vi phạm quyền truy cập.
- Các tình huống lỗi, quyền, cạnh tranh dữ liệu được kiểm tra khi liên quan.
- Tài liệu/runbook và cách quan sát vận hành được cập nhật khi thay đổi yêu cầu.
- Increment có thể sử dụng theo chuẩn chất lượng nhóm đã thống nhất.

Đây là **DoD minh họa**, không thay thế tiêu chuẩn của sản phẩm hoặc tổ chức. Đối với dữ liệu nhạy cảm và hệ thống quan trọng, có thể cần nhiều điều kiện chuyên môn hơn.

### 9.2. Không đánh dấu Done bằng tỷ lệ hoàn thành

Một story đã viết xong mã nhưng chưa qua kiểm thử tích hợp là **chưa Done** nếu DoD yêu cầu bước đó. Nhóm không nên cộng “80% story” vào velocity như một Increment đã hoàn tất.

Giữ chuẩn Done có thể khiến số story hoàn thành của một Sprint thấp hơn, nhưng làm **thông tin đáng tin cậy hơn**. Sprint tiếp theo sẽ không phải trả giá bằng việc phát hiện các hạng mục “Done trên giấy”.

### 9.3. Acceptance criteria và DoD khác nhau

| Khái niệm | Phạm vi | Ví dụ |
| --- | --- | --- |
| **Acceptance criteria** | Hành vi mong muốn của một story cụ thể | Khi buổi đầy, học viên không nhận thông báo đã xác nhận chỗ |
| **Definition of Done** | Chuẩn chất lượng chung để công việc tạo Increment được xem là hoàn tất | Build/test tích hợp đạt, quyền dữ liệu đúng, review theo quy ước |
| **Release readiness** | Điều kiện đưa thay đổi đến môi trường hoặc đối tượng nhận | Cấu hình, giám sát, kế hoạch triển khai/rollback, xác minh dữ liệu khi cần |

Một story đạt acceptance criteria trong môi trường thử nhưng chưa đáp ứng DoD **không phải Increment hoàn tất**. Một Increment đạt DoD có thể sẵn sàng nhưng chưa được phát hành vì quyết định sản phẩm hoặc vận hành. Cần nói rõ ranh giới, không gộp ba khái niệm.

### 9.4. Chất lượng phải được tích hợp vào công việc, không đặt ở cuối

Nếu QA, review và bảo mật chỉ xuất hiện ở hai ngày cuối Sprint, nguy cơ tồn đọng sẽ lớn. Nhóm có thể:
- Viết ví dụ nghiệp vụ trước khi bắt đầu story.
- Ghép cặp ở chỗ có rủi ro.
- Tích hợp test và code từng lát cắt.
- Kiểm tra điều kiện DoD liên tục.
- Chọn ít hạng mục hơn nhưng đưa được qua toàn bộ dòng đến Done.

Đó là cách **giao chất lượng trong nhịp**, không phải cố “chạy kiểm thử thật nhanh” ở phút cuối.

## 10. Lập kế hoạch theo năng lực thực tế, không theo ảo tưởng 100% sử dụng

### 10.1. Phân biệt thời gian hiện diện với năng lực hoàn tất

Số ngày công theo lịch không đồng nghĩa toàn bộ thời gian phát triển tập trung. Một nhóm còn có nghỉ phép, trao đổi nghiệp vụ, review, hỗ trợ, học công nghệ, triển khai và ứng phó sự cố.

**Capacity** là thông tin để lựa chọn phạm vi khả thi; không phải mệnh lệnh phải lấp kín tất cả giờ. **Velocity** của nhóm dùng story points chỉ giúp tham khảo lịch sử hoàn tất theo chính quy ước của nhóm, không trực tiếp đo số giờ công, năng suất con người hoặc giá trị.

### 10.2. Ví dụ tính capacity minh họa

Một nhóm có **4 Developers**, Sprint **10 ngày làm việc**. Sau khi tính các hoạt động lặp lại và nghỉ giải lao theo cách ước lượng nội bộ, nhóm giả định mỗi người có trung bình **6 giờ/ngày** cho công việc làm ra Increment (bao gồm thiết kế, coding, test, review).

~~~text
Năng lực lý thuyết cho dòng phát triển:
4 người × 10 ngày × 6 giờ/ngày = 240 giờ

Dự kiến công việc hỗ trợ/sự cố phải xử lý trong cùng quỹ giờ:
30 giờ

Dự kiến phụ thuộc và phối hợp ngoài kế hoạch thông thường:
18 giờ

Năng lực tham khảo còn lại:
240 − 30 − 18 = 192 giờ
~~~

**Các số hoàn toàn giả định**; 6 giờ không phải chuẩn XP và 192 giờ không phải lời hứa. Nếu 30 giờ hỗ trợ đã được tính trong con số 6 giờ/ngày thì không được **trừ hai lần**. Nhóm cần thống nhất cách phân loại công việc, xem dữ liệu thực và tránh lập kế hoạch dựa trên giả định quá chính xác.

Nếu backlog dự kiến cần **220 giờ theo cùng quy ước thô**, chênh lệch so với mức 192 giờ là **28 giờ**. Phản ứng có trách nhiệm là **giảm hoặc chia phạm vi, ưu tiên lát cắt giá trị, xử lý phụ thuộc và trao đổi sớm**, không mặc định yêu cầu mọi người làm thêm 28 giờ.

### 10.3. Capacity theo giờ không biến story points thành giờ

Đối với nhóm dùng story points, không nên tuyên bố “1 point = 3 giờ” như một định nghĩa bắt buộc. Story points, nếu dùng, là ước lượng tương đối của hạng mục trong bối cảnh nhóm. Capacity theo thời gian giúp kiểm tra các sự kiện đã biết như nghỉ phép và hỗ trợ, còn **dữ liệu hoàn tất lịch sử** giúp dự báo với bất định.

Nếu muốn dự báo bằng throughput của Kanban, đơn vị là số item finished theo kỳ trong một tập công việc nhất quán; không tự đồng nhất một item với một point.

### 10.4. Không tối ưu mức bận của từng cá nhân

Một người trống một giờ không nhất thiết phải bắt đầu story mới. Họ có thể:
- Giúp review item sắp hoàn tất.
- Pairing để giải quyết blocker.
- Cải thiện kiểm thử lặp lại.
- Làm rõ một trường hợp nghiệp vụ đang chặn người khác.
- Hoàn thiện tài liệu vận hành quan trọng.

Mục tiêu là **tăng khả năng hoàn tất giá trị của hệ thống**, không phải khiến mỗi thành viên liên tục bắt đầu thêm việc để biểu đồ sử dụng đạt 100%.

## 11. Quản lý WIP, gián đoạn và chính sách khẩn cấp

### 11.1. WIP quá nhiều có thể làm nhịp làm việc thất thường

Ví dụ trên bảng:

~~~text
Ready           Doing (WIP 3)       Review (WIP 2)      Verify      Done
--------------------------------------------------------------------------------
Story A         Story B              Story C            Bug D       Story E
Story F         Story G              Story H
Story I         Story J
~~~

Khi Review đã có C và H, bắt đầu thêm một story không giải quyết hàng chờ. Nhóm có thể giúp review hoặc gỡ blocker, đưa item cũ đến Done trước khi kéo việc mới.

Các mức WIP 3 và 2 chỉ là **giới hạn minh họa do nhóm đặt ra**, không phải giới hạn mặc định của XP hay Kanban.

### 11.2. Công việc ngoài luồng phải được nhìn thấy

Yêu cầu đến qua tin nhắn riêng, cuộc họp bất ngờ và sự cố có thể chiếm năng lực nhưng không hiện trong Sprint Backlog hoặc bảng. Nếu chúng đủ lớn để làm thay đổi dự báo hoặc chất lượng, nhóm cần ghi nhận theo chính sách rõ, gồm:
- Vì sao công việc xuất hiện và ai quyết định mức khẩn.
- Người chịu trách nhiệm điều phối.
- Tác động lên công việc hiện tại và mục tiêu.
- Thời gian/kết quả xử lý ở mức có ích.
- Nguyên nhân lặp lại và cơ hội cải tiến.

Không nhất thiết tạo thẻ cho mọi trao đổi vài phút. Mục tiêu là **minh bạch chi phí thật**, không tăng thủ tục.

### 11.3. Phân biệt khẩn cấp thực và yêu cầu ưu tiên cao

| Loại | Ví dụ | Cách xử lý |
| --- | --- | --- |
| **Sự cố khẩn** | Lỗi production xác nhận vượt sức chứa, lộ dữ liệu | Kích hoạt quy trình ứng phó phù hợp ngay, bảo vệ người dùng |
| **Yêu cầu gấp nhưng có thể thương lượng** | Cần báo cáo cho buổi họp ngày mai | Xác minh tác động, cân nhắc đổi phạm vi với người có thẩm quyền |
| **Nhu cầu thông thường** | Đề nghị thêm lựa chọn giao diện | Đưa vào backlog, làm rõ giá trị và sắp thứ tự |
| **Cải tiến phòng ngừa** | Bổ sung test cho bug lặp lại | Đưa vào kế hoạch chất lượng theo rủi ro, không trì hoãn vô hạn |

Khi sự cố khẩn xảy ra, tính bền vững không có nghĩa “không bao giờ phải đáp ứng ngay”. Nó nghĩa là **sự cố được điều phối, phân ca, giảm tải, phục hồi và dùng làm dữ liệu ngăn lặp lại**; không để mọi tình huống đều trở thành lý do bắt nhóm làm thêm liên tục.

### 11.4. Sau sự cố, cần phục hồi năng lực và học

Ví dụ quy trình:
1. Phân công điều phối và giới hạn phạm vi xử lý.
2. Bảo vệ dữ liệu/người dùng, khắc phục hoặc giảm thiểu tác động.
3. Ghi lại quyết định và trạng thái thực tế.
4. Kiểm chứng sửa lỗi và theo dõi tác dụng phụ.
5. Chủ động điều chỉnh cam kết khác, lịch trực và kế hoạch sau sự cố.
6. Phân tích nguyên nhân hệ thống và chọn cải tiến có thể kiểm chứng.

Không nên để một sự cố kéo dài đến lúc mọi thành viên không còn nghỉ ngơi, rồi ngay sau đó yêu cầu đội bù toàn bộ story đã bị gián đoạn mà không đổi kế hoạch.

## 12. Nhịp làm việc bền vững trong Scrum và Kanban

### 12.1. XP không đồng nghĩa Scrum

**XP** đặc biệt nhấn mạnh các thực hành kỹ thuật và phát triển có phản hồi ngắn; **Scrum** cung cấp accountability, artifacts và events để kiểm tra–thích ứng; **Kanban** giúp nhìn thấy và cải thiện dòng công việc bằng chính sách tường minh và flow metrics. Chúng có thể bổ trợ nhau, nhưng không phải mọi quy định của Scrum đều là quy định XP.

### 12.2. Khi dùng Scrum

- **Product Goal:** định hướng giá trị dài hạn của sản phẩm.
- **Product Backlog:** Product Owner giữ thứ tự công việc theo giá trị, rủi ro và phản hồi.
- **Sprint Planning:** Developers chọn phạm vi khả thi để đạt Sprint Goal; dữ liệu năng lực và chất lượng có ý nghĩa.
- **Daily Scrum:** Developers kiểm tra tiến triển tới Sprint Goal và điều chỉnh Sprint Backlog, không phải báo cáo số giờ làm.
- **Sprint Review:** kiểm tra Increment và kết quả với stakeholder, điều chỉnh ưu tiên.
- **Sprint Retrospective:** chọn thay đổi cách làm việc có thể thử và kiểm chứng.

**Definition of Done không được hạ để cứu dự báo Sprint.** Nếu Sprint Goal vẫn có giá trị nhưng phạm vi quá lớn, Product Owner và Developers có thể làm rõ, thương lượng phạm vi mà không làm nguy hại mục tiêu.

### 12.3. Khi dùng Kanban

Nhóm có thể định nghĩa **Definition of Workflow** rõ started/finished, đặt giới hạn WIP, theo dõi **work item age, throughput, cycle time** và SLE dựa trên lịch sử.

Ví dụ, nếu work item age của một story vượt hẳn mức thường thấy, nhóm nên tìm blocker thay vì bắt đầu thêm việc mới. Nếu nhiều item đứng chờ review, cần thử cải thiện khả năng review, pairing hoặc chia nhỏ công việc.

Không nên dùng cycle time thấp như bằng chứng duy nhất về năng suất khi loại item, chất lượng hoặc điểm finished đã thay đổi.

### 12.4. Nhịp giao giá trị có thể liên tục

Scrum có Sprint cố định; một nhóm Kanban có thể giao liên tục mà không dùng Sprint. **Nhịp bền vững là nguyên tắc tổ chức**, không đòi mọi nhóm phải có cùng lịch họp hoặc cùng độ dài vòng làm việc.

Cả hai bối cảnh vẫn cần: công việc đủ rõ, tiêu chuẩn hoàn tất có trách nhiệm, phản hồi thực tế, cải tiến thường xuyên và không che dấu gián đoạn.

## 13. Đo chất lượng và độ bền của nhịp làm việc

**Không có một KPI “sustainable pace” duy nhất.** Chỉ nhìn số giờ làm thêm, velocity hoặc số bug có thể bỏ sót bối cảnh. Cần kết hợp nhiều loại tín hiệu, ưu tiên dữ liệu ở cấp nhóm và có mục đích cải tiến.

### 13.1. Bộ tín hiệu minh họa

| Nhóm tín hiệu | Cách quan sát | Câu hỏi cần trả lời |
| --- | --- | --- |
| **Flow** | WIP, throughput, cycle time, work item age, blocked time | Nhóm hoàn tất công việc ổn định hay mở quá nhiều việc? |
| **Chất lượng sản phẩm** | Lỗi lọt ra sau phát hành, sự cố, lỗi phải sửa lại, kiểm thử vùng quan trọng | Việc giao nhanh có đi kèm độ tin cậy không? |
| **Khả năng phát hành** | Tần suất triển khai phù hợp, thời gian dẫn tới thay đổi, tỷ lệ thay đổi gây sự cố, thời gian khôi phục | Có thể đưa thay đổi an toàn tới người dùng thường xuyên không? |
| **Chất lượng kỹ thuật** | Build/pipeline thất bại, test flaky, vùng mã thường phải sửa nhiều lần | Công cụ và mã có hỗ trợ thay đổi hay đang tạo cản trở? |
| **Bền vững công việc** | Số lần phải ứng phó ngoài giờ, gián đoạn kéo dài, nhận xét tự nguyện về tải công việc, phụ thuộc vào một người | Nhóm có thể tiếp tục làm việc có chất lượng trong các vòng sau không? |
| **Giá trị người dùng** | Tỷ lệ hoàn tất tác vụ, mức hiểu trạng thái, lỗi nghiệp vụ, phản hồi hỗ trợ | Phần mềm giao ra có giải quyết vấn đề thật? |

Không dùng dữ liệu về sức khỏe hoặc thời gian cá nhân để giám sát, xếp hạng hay suy diễn tình trạng riêng tư. Nếu thu phản hồi nhóm về tải công việc, cần tôn trọng quyền riêng tư, sự tự nguyện và mục đích cải tiến đã thống nhất.

### 13.2. Velocity khác giá trị và năng suất

Velocity là tổng story points của công việc đạt DoD trong một Sprint theo cách ước lượng của nhóm, nếu nhóm có dùng story points. Nó **không đo trực tiếp hiệu quả của từng người, chất lượng hay giá trị khách hàng**.

Một Sprint có ít points hơn nhưng đã khắc phục lỗi mất dữ liệu hoặc giảm nợ kỹ thuật quan trọng có thể mang lợi ích lớn hơn Sprint nhiều points chỉ bổ sung giao diện ít dùng. Cần đánh giá theo **mục tiêu sản phẩm và kết quả người dùng**, không đặt chỉ tiêu tăng points vô hạn.

### 13.3. Chỉ số phải đi cùng định nghĩa và bối cảnh

Nếu thay đổi DoD từ “merge xong” sang “đã kiểm thử tích hợp và sẵn sàng triển khai”, số story Done có thể giảm hoặc cycle time tăng vì **ranh giới đo đã thay đổi**. Không được kết luận ngay nhóm chậm hơn.

Nếu tuần trước có sự cố production lớn, throughput thấp là dữ liệu cần giải thích; không đủ bằng chứng quy nguyên nhân cho một cá nhân.

Một thay đổi tích cực có căn cứ thường là:
- Công việc đạt DoD ổn định hơn.
- Lỗi sau phát hành giảm hoặc được phát hiện sớm hơn.
- Hàng chờ và blocked được xử lý.
- Ít tình huống ngoài giờ lặp lại vì nguyên nhân hệ thống được sửa.
- Kết quả người dùng không xấu đi khi nhịp giao hàng cải thiện.

### 13.4. Quan sát cả tín hiệu dẫn trước và kết quả theo sau

**Tín hiệu dẫn trước** có thể là CI đỏ nhiều lần, review tồn đọng, story vượt WIP, số test vùng rủi ro chưa có hoặc nhiều người phải thay nhau cứu một sự cố.

**Kết quả theo sau** có thể là lỗi production, chu kỳ hoàn tất dài, bỏ lỡ mốc sản phẩm, tỷ lệ người dùng không hoàn tất tác vụ.

Theo dõi cả hai giúp nhóm **can thiệp trước khi sự cố tích tụ**, nhưng không nên coi tín hiệu dẫn trước là sự bảo đảm tuyệt đối cho kết quả sau.

## 14. Tình huống xuyên suốt: nhóm workshop thoát vòng xoáy cứu deadline

### 14.1. Bối cảnh

Một Scrum Team đang xây phần mềm đăng ký workshop. Product Goal là học viên có thể tự đăng ký buổi còn chỗ và hiểu kết quả, trong khi điều phối viên giữ số chỗ chính xác.

Nhóm đã phát hành hai lát cắt đầu tiên nhưng thường gặp:
- Story được gắn Done sau khi viết xong code, chưa đủ kiểm thử.
- Chỉ một Developers biết luồng xác nhận suất cuối.
- Kiểm thử đồng thời không có trong pipeline.
- Review tồn nhiều thẻ; người khác vẫn bắt đầu story mới.
- Hai Sprint liên tiếp có tình huống phải làm tối vì deadline.

Người quản lý đề nghị “Sprint tới tăng velocity thêm 30%”.

### 14.2. Dữ liệu trước cải tiến

Dữ liệu sau đây **hoàn toàn giả định**, chỉ để luyện cách đánh giá:

| Quan sát trong Sprint hai tuần | Sprint A | Sprint B |
| --- | ---: | ---: |
| Points đạt DoD thực sự | 19 | 22 |
| Lỗi nghiêm trọng phát hiện sau bàn giao | 2 | 3 |
| Số story bị chặn ở review quá 2 ngày | 3 | 5 |
| Lần nhóm phải xử lý ngoài giờ | 2 | 4 |
| Lượt học viên thử hiểu đúng trạng thái | 9/15 | 10/15 |

Số points tăng từ 19 lên 22 (**khoảng 15,8%**) nhưng lỗi và gián đoạn cũng tăng. Không đủ căn cứ kết luận có quan hệ nhân quả; các story và bối cảnh có thể khác nhau. Tuy nhiên, dữ liệu **không ủng hộ suy luận rằng điểm tăng đồng nghĩa sản phẩm tốt hơn và nhịp đã bền vững**.

### 14.3. Quyết định ở Sprint tiếp theo

Product Owner và Developers thống nhất mục tiêu tạo một luồng đăng ký đáng tin, không chỉ tăng points. Họ chọn:

1. **Giữ DoD:** không tính Done cho story chưa kiểm thử tình huống quan trọng.
2. **TDD và test tích hợp:** viết test cho quy tắc chỗ và tình huống đồng thời ở mức phù hợp.
3. **Pairing:** hai người làm cùng vùng mã xác nhận để giảm phụ thuộc độc nhất.
4. **Giảm WIP:** khi Review đầy, ưu tiên hỗ trợ hoàn tất trước khi kéo việc mới.
5. **Small slice:** ưu tiên luồng gửi yêu cầu và trạng thái rõ; trì hoãn báo cáo nâng cao chưa chứng minh giá trị.
6. **Minh bạch năng lực:** đưa việc hỗ trợ/sự cố vào quyết định kế hoạch.
7. **Kiểm tra kết quả:** theo dõi lỗi, thời gian chờ, phản hồi học viên và nhịp công việc qua vài Sprint.

Không có bằng chứng rằng nhóm sẽ ngay lập tức tăng tốc. Trong Sprint đầu áp dụng TDD, lượng work hoàn tất có thể giảm vì nhóm đang trả chi phí sửa những lỗ hổng chất lượng.

### 14.4. Dữ liệu sau thay đổi để thảo luận

Giả sử trong Sprint C và D, nhóm quan sát:

| Quan sát | Sprint C | Sprint D |
| --- | ---: | ---: |
| Points đạt DoD | 16 | 18 |
| Lỗi nghiêm trọng phát hiện sau bàn giao | 1 | 0 |
| Story bị chặn review quá 2 ngày | 3 | 1 |
| Lần xử lý ngoài giờ | 1 | 0 |
| Lượt học viên thử hiểu đúng trạng thái | 11/15 | 13/15 |

Dữ liệu minh họa **gợi ý** nhóm cải thiện độ ổn định và kết quả người dùng trong khi velocity chưa quay lại 22. Nhưng các số nhỏ và dữ liệu giả định **chưa đủ chứng minh riêng TDD, pairing hoặc WIP limit là nguyên nhân**.

Một câu hỏi tốt trong Retrospective là: “Những thay đổi nào có khả năng góp phần cải thiện, yếu tố nào bên ngoài thay đổi và chúng ta cần quan sát thêm bao lâu?”

### 14.5. Bài học từ tình huống

- Không tối ưu velocity thay cho Product Goal.
- Đo **Done thật** thay vì dùng trạng thái ảo để làm đẹp báo cáo.
- Cải tiến chất lượng có thể cần đầu tư trước khi thấy lợi ích dòng công việc.
- Pairing và tập trung hoàn tất có thể giảm phụ thuộc và hàng chờ.
- Tình huống ứng phó ngoài giờ cần được ghi nhận ở cấp vận hành để phòng ngừa, không cổ vũ người hùng.
- Giá trị thực đến từ học viên hiểu trạng thái và đăng ký đúng, không chỉ từ số màn hình giao ra.

## 15. Những đánh đổi khó và cách ra quyết định

### 15.1. Khi deadline đến gần nhưng story chưa đạt DoD

Không nên chọn ngay phương án “bỏ test”. Có thể cân nhắc theo thứ tự:
1. **Giữ phần an toàn và có giá trị nhất** của Sprint Goal hoặc mục tiêu phát hành.
2. Chia story thành lát cắt dọc nhỏ hơn, từng phần đạt DoD.
3. Thương lượng bỏ hoặc dời chức năng ít giá trị hơn.
4. Bổ sung người hỗ trợ review, gỡ phụ thuộc khi thật sự hữu ích.
5. Công khai bất định và quyết định với Product Owner/stakeholder.
6. Nếu thay đổi không đủ an toàn, **không phát hành** phần chưa đáp ứng điều kiện thiết yếu.

Các lựa chọn không bảo đảm luôn giữ nguyên ngày ra mắt. Một ngày hẹn thiếu căn cứ không được ưu tiên hơn an toàn và tính đúng đắn dữ liệu.

### 15.2. Khi sản phẩm có sự cố khẩn

Sự cố đang gây hại cần ứng phó kịp thời. Nhưng cách tổ chức có thể giảm tác động lên sức khỏe và nhịp làm việc:
- Người điều phối và phạm vi ứng phó rõ.
- Phân công theo năng lực phù hợp, có thay ca và liên lạc cần thiết.
- Giảm phạm vi ảnh hưởng hoặc phục hồi dịch vụ trước khi làm mọi cải tiến dài hạn.
- Kiểm tra sau sửa và theo dõi rủi ro.
- Điều chỉnh kế hoạch thường ngày vì năng lực đã dùng cho sự cố.
- Chọn hành động phòng ngừa qua phân tích nguyên nhân không đổ lỗi.

Chính sách ứng phó cần phù hợp quy định và ràng buộc thực tế của tổ chức.

### 15.3. Khi có quá nhiều hoạt động chất lượng cạnh tranh thời gian

Không nên phủ nhận giá trị test hoặc refactoring, nhưng cũng không biến “chất lượng” thành lý do xây lại toàn bộ phần mềm. Nhóm đánh giá:
- Rủi ro nào nghiêm trọng và xảy ra thường xuyên?
- Test nào cho phản hồi nhanh với giá trị lớn?
- Vùng mã nào thường xuyên thay đổi?
- Thay đổi cấu trúc nhỏ nào giúp story hiện tại an toàn hơn?
- Cần giữ guardrail nào dù phạm vi chức năng bị giảm?

**Chất lượng đủ để giao an toàn** và **cải tiến dài hạn có chủ đích** đều quan trọng. Tỷ lệ thời gian cho mỗi loại phụ thuộc vào tình trạng thực, không có công thức XP áp dụng cho mọi nhóm.

### 15.4. Quy tắc trao đổi minh bạch

Một thông điệp có thể là:

> “Nhóm có thể giao lát cắt đăng ký cơ bản đã đạt DoD trong mốc này. Báo cáo nâng cao và một kịch bản thông báo chưa đủ kiểm chứng sẽ được xem lại. Nếu muốn đưa thêm chúng vào cùng mốc, chúng ta phải nêu rõ phần nào khác cần lùi, những rủi ro phát sinh và năng lực thực tế. Chúng tôi không đề xuất bỏ kiểm thử trường hợp xác nhận trùng vì nó ảnh hưởng dữ liệu của học viên.”

Cách nói này bảo vệ **giá trị, chất lượng và sự minh bạch về đánh đổi**, không dùng cam kết mơ hồ để giảm bất đồng trong cuộc họp.

## 16. Sai lầm phổ biến và cách sửa

| Sai lầm | Hệ quả | Cách điều chỉnh |
| --- | --- | --- |
| Coi làm đêm thường xuyên là tinh thần XP | Mệt mỏi, lỗi, phụ thuộc và làm lại tăng | Lập kế hoạch theo năng lực thực, bảo đảm thời gian phục hồi |
| Áp một số giờ cứng cho tất cả mọi người | Bỏ qua pháp luật, bối cảnh và nhu cầu khác nhau | Tập trung nguyên tắc energized work, thống nhất điều kiện phù hợp |
| Khen người luôn cứu sự cố, quên phòng ngừa | Củng cố vòng xoáy cứu hỏa | Công nhận cải tiến test, CI, chia sẻ kiến thức, ngăn lỗi |
| Bỏ test để tăng số story Done | Increment thiếu tin cậy, lỗi xuất hiện muộn | Định nghĩa DoD và thực hiện kiểm tra trong luồng |
| Coi unit test coverage cao là đủ | Bỏ lọt lỗi tích hợp, quyền và đồng thời | Chọn tầng kiểm thử theo rủi ro thực |
| Pairing chỉ là hai người nhìn một màn hình | Không chia sẻ tư duy, tăng chi phí vô ích | Có mục tiêu, vai trò, luân chuyển và cơ hội giải thích |
| Ép pairing liên tục bất kể hoàn cảnh | Mệt mỏi, thiếu thời gian tập trung, khó tiếp cận | Chọn pairing có chủ đích, xen kẽ nghỉ và làm độc lập |
| CI đỏ nhưng vẫn gộp thêm thay đổi | Khó biết nguồn lỗi, phản hồi không đáng tin | Ưu tiên khôi phục pipeline và làm ổn định test |
| Refactoring không có test bảo vệ | Thay cấu trúc làm hỏng hành vi | Thay đổi nhỏ, chạy kiểm tra phù hợp, tích hợp thường xuyên |
| Thiết kế trước mọi khả năng tương lai | Xây dư, tăng chi phí bảo trì | Simple design và quyết định theo bằng chứng |
| Bắt đầu nhiều story để “mọi người đều bận” | Tăng WIP, review chờ lâu, khó giao | Hoàn tất việc cũ, giúp gỡ chặn, dùng pull |
| Xem velocity là năng suất cá nhân | Tạo cạnh tranh điểm, bỏ việc hỗ trợ | Dùng dữ liệu nhóm để dự báo; đo chất lượng và outcome |
| Chỉ nhìn lỗi phát hành, không nhìn làm lại | Không thấy chi phí chất lượng ẩn | Theo dõi rework, blocked và vòng sửa trong luồng |
| Chỉ cải tiến kỹ thuật, không hỏi người dùng | Giao nhanh tính năng không cần thiết | Bảo đảm vòng phản hồi sản phẩm và ưu tiên giá trị |
| Không cập nhật kế hoạch sau sự cố | Kỳ vọng phi thực tế, đẩy làm thêm giờ | Minh bạch năng lực đã dùng và thương lượng phạm vi |
| Retro liệt kê rất nhiều việc nhưng không thử gì | Không cải thiện được hệ thống | Chọn một thay đổi nhỏ, có owner và điều kiện kiểm chứng |

## 17. Bài thực hành: thiết kế nhịp chất lượng cho một XP team

### 17.1. Bối cảnh

Nhóm bốn Developers xây ứng dụng đặt lịch. Trong hai Sprint gần nhất:
- Một người thường phải sửa luồng xác nhận ngoài giờ.
- Có nhiều story được gắn Done trước khi kiểm thử tích hợp.
- Review bị dồn cuối Sprint.
- Product Owner muốn bổ sung báo cáo nâng cao.
- Người dùng thử vẫn hiểu nhầm trạng thái “đang chờ” với “đã có chỗ”.

Đây là **tình huống giả định** để luyện quyết định, không phải số liệu một nhóm thực tế.

### 17.2. Nhiệm vụ A – Chẩn đoán vòng xoáy (15 phút)

Vẽ sơ đồ nhân quả tối thiểu sáu mắt xích từ **cam kết quá nhiều việc** đến **làm thêm giờ, bỏ test, tăng lỗi và giảm năng lực**.

Sau đó xác định:
1. Mắt xích nào là quan sát đã có dữ liệu?
2. Mắt xích nào chỉ là giả thuyết cần kiểm chứng?
3. Hai hành động nào có thể cắt vòng xoáy trong Sprint tiếp theo?
4. Vì sao chỉ yêu cầu cá nhân “cẩn thận hơn” không đủ?

### 17.3. Nhiệm vụ B – TDD cho quy tắc đăng ký (20 phút)

Một workshop có sức chứa 10 chỗ. Hiện có 9 yêu cầu đã được xác nhận. Hai học viên cùng gửi yêu cầu ở thời điểm gần như đồng thời.

Hãy:
1. Viết ít nhất ba tình huống unit test cho quy tắc **còn chỗ / hết chỗ / đầu vào bất hợp lệ**.
2. Mô tả vì sao kiểm tra “9 nhỏ hơn 10” riêng lẻ **chưa ngăn hai request đồng thời**.
3. Đề xuất một bài integration test về cập nhật đồng thời và bất biến **không vượt 10 chỗ**.
4. Ghi quy tắc quyền riêng tư cần kiểm tra khi hiển thị trạng thái đăng ký.
5. Xác định điều kiện DoD liên quan trước khi có thể nói story đã hoàn tất.

Gợi ý dạng chấp nhận:

~~~gherkin
Tính năng: Xác nhận chỗ workshop

  Tình huống: Hai yêu cầu cùng cạnh tranh suất cuối
    Cho trước workshop còn đúng một chỗ
    Khi hai yêu cầu xác nhận hợp lệ được xử lý gần đồng thời
    Thì tổng số chỗ được xác nhận không vượt sức chứa
    Và mỗi người nhận trạng thái phản ánh kết quả thực tế
~~~

Tình huống là **tiêu chí kiểm chứng ý định**, không thay thế thiết kế nguyên tử hóa dữ liệu và kiểm thử phù hợp với cơ sở dữ liệu/cơ chế triển khai thật.

### 17.4. Nhiệm vụ C – Tính năng lực và chọn phạm vi (15 phút)

Nhóm có:
- 4 Developers.
- 10 ngày làm việc.
- Giả định mỗi người có 6 giờ/ngày dành cho công việc tạo Increment, đã tính phần hoạt động lặp lại.
- 30 giờ hỗ trợ và 18 giờ phối hợp phát sinh **chưa tính** trong 6 giờ/ngày.
- Công việc dự kiến theo cùng quy ước là 220 giờ.

Câu hỏi:
1. Năng lực ban đầu tính bằng giờ là bao nhiêu?
2. Năng lực tham khảo còn lại sau công việc phát sinh?
3. Phần chênh lệch của kế hoạch?
4. Nêu ba lựa chọn tốt hơn việc mặc định làm thêm.
5. Vì sao không được coi 192 giờ là cam kết chắc chắn hoặc quy đổi tự động ra story points?

**Đáp án tự kiểm tra:** 4 × 10 × 6 = **240 giờ**; 240 − 30 − 18 = **192 giờ**; kế hoạch 220 giờ vượt tham khảo **28 giờ**. Cần xác minh cách tính và bất định rồi giảm/chia phạm vi, cải thiện dòng hoặc thương lượng lại mốc.

### 17.5. Nhiệm vụ D – Đề xuất chính sách nhịp bền vững (20 phút)

Theo nhóm nhỏ, xây chính sách thử trong hai Sprint về:
- Cách chọn phạm vi theo Product Goal và năng lực thực.
- Giới hạn WIP cho Doing và Review.
- Khi nào pairing giúp giảm rủi ro, ai luân chuyển cùng ai.
- Điều kiện CI xanh và cách xử lý test flaky.
- Quy tắc refactoring cùng kiểm tra hồi quy.
- Điều kiện Done và khi nào được phát hành.
- Cách tiếp nhận sự cố khẩn và công việc ngoài luồng.
- Cách chia sẻ kiến thức để người trực không phụ thuộc một chuyên gia.
- Hai tín hiệu chất lượng, hai tín hiệu flow và một outcome người dùng để kiểm chứng.

Chính sách cần **ngắn, quan sát được và có thể điều chỉnh** sau khi dùng thử. Không biến mọi điểm thành chỉ tiêu đánh giá cá nhân.

### 17.6. Nhiệm vụ E – Phản hồi yêu cầu tăng velocity (10 phút)

Một quản lý yêu cầu: “Sprint tới phải tăng từ 20 lên 30 points vì dự án chậm.”

Viết đoạn trao đổi giải thích:
1. Vì sao velocity không đo trực tiếp năng suất hoặc giá trị.
2. Những dữ liệu nào cần xem để tìm nguyên nhân chậm.
3. Có thể giữ mục tiêu người dùng nào với phạm vi nhỏ hơn.
4. Điều kiện chất lượng nào không được bỏ qua.
5. Khi nào kiểm tra lại khả năng giao sản phẩm và sự bền vững.

Một câu trả lời tốt **không từ chối đo lường**; nó dùng số liệu để mở thảo luận về khả năng giao kết quả hữu ích, bền vững.

### 17.7. Nhiệm vụ F – Thiết kế thử nghiệm cải tiến (10 phút)

Nhóm chọn giả thuyết:

> “Nếu giới hạn số story đang làm và pairing ở vùng xác nhận chỗ, số việc chờ review lâu và lỗi tích hợp sẽ giảm mà không làm xấu trải nghiệm học viên.”

Hãy xác định:
- Baseline cần thu trước khi thử.
- Chính sách WIP và pairing cụ thể.
- Thời gian thử hợp lý.
- Các biến gây nhiễu như thay đổi loại story hoặc nghỉ phép.
- Tín hiệu tác dụng phụ: một người phải pairing liên tục, QA trở thành nút thắt mới, story bị chia vụn không tạo giá trị.
- Mốc xem lại và tiêu chí giữ/điều chỉnh/ngừng thử.

### 17.8. Thang tự đánh giá

| Tiêu chí | Chưa đạt | Đạt | Vững |
| --- | --- | --- | --- |
| **Hiểu sustainable pace** | Coi làm thêm giờ là cách tăng tốc mặc định | Giải thích nhịp dài hạn và giới hạn năng lực | Phân tích được vòng lỗi – làm lại – phụ thuộc – hồi phục |
| **Kỹ thuật XP** | Chỉ nêu tên TDD/pairing/CI | Trình bày cơ chế và cách áp dụng đúng | Chọn thực hành theo rủi ro, hiểu giới hạn của từng thực hành |
| **Bảo vệ chất lượng** | Gắn Done trước kiểm thử | Có DoD, acceptance criteria và test phù hợp | Có kiểm tra đồng thời/quyền, điều kiện phát hành, theo dõi lỗi |
| **Lập kế hoạch** | Cam kết vượt năng lực, mặc định overtime | Có capacity, WIP và trao đổi phạm vi | Dự báo theo dữ liệu, xử lý gián đoạn và học sau mỗi vòng |
| **Đo lường** | Chỉ theo velocity hoặc giờ làm | Kết hợp flow, quality và outcome | Diễn giải bất định, chống bóp méo chỉ số, không đánh giá cá nhân |
| **Cải tiến** | Retro chỉ nêu vấn đề chung | Có thử nghiệm nhỏ, người phối hợp và mốc xem lại | Đối chiếu dữ liệu, nhận diện tác dụng phụ và chỉnh chính sách |

## 18. Mẫu áp dụng và checklist

### 18.1. Mẫu lập kế hoạch nhịp bền vững

~~~text
Product Goal và Sprint Goal (nếu dùng Scrum):
Lát cắt có ích cần giao:
Năng lực khả dụng, nghỉ phép và phụ thuộc:
Công việc hỗ trợ/sự cố dự kiến:
Rủi ro về chất lượng và dữ liệu:
Definition of Done áp dụng:
Những việc cần test/pairing/review kỹ:
Giới hạn WIP và chính sách ưu tiên hoàn tất:
Phạm vi có thể giảm hoặc chia nhỏ:
Ai quyết định đổi ưu tiên / phạm vi:
Cách phản hồi stakeholder:
Ngày kiểm tra lại dự báo:
~~~

### 18.2. Mẫu lựa chọn một cải tiến kỹ thuật XP

~~~text
Vấn đề quan sát:
Bằng chứng hiện có:
Giả thuyết nguyên nhân:
Thực hành sẽ thử: TDD / pairing / CI / refactoring / ...
Phạm vi thử và điều kiện an toàn:
Người phối hợp và nguồn lực cần có:
Baseline chất lượng, flow và giá trị:
Tín hiệu đánh giá:
Tác dụng phụ cần theo dõi:
Mốc xem lại:
Quyết định: giữ / chỉnh / dừng thử:
~~~

### 18.3. Mẫu phân tích sự cố không đổ lỗi

~~~text
Điều đã xảy ra và người dùng bị ảnh hưởng:
Mốc thời gian và cách phát hiện:
Bước giảm thiểu và khôi phục dịch vụ:
Cách xác minh dữ liệu, quyền và tính đúng:
Những điều làm việc phát hiện hoặc xử lý bị chậm:
Phụ thuộc cá nhân hay công cụ:
Test hoặc ranh giới kỹ thuật còn thiếu:
Tác động lên WIP, backlog, năng lực và lịch trực:
Hành động phòng ngừa có thể kiểm chứng:
Người theo dõi và mốc xem lại:
~~~

### 18.4. Checklist cuối bài

**Nhịp bền vững:**

- [ ] Nhóm lập kế hoạch theo năng lực thực tế thay vì giả định mọi giờ đều làm tính năng mới.
- [ ] Không dựa vào làm thêm giờ lặp lại để bảo đảm cam kết thông thường.
- [ ] Sự cố khẩn có quy trình ứng phó và điều chỉnh kế hoạch sau khi dùng năng lực.
- [ ] Nhóm có cơ hội học, chia sẻ hiểu biết và phục hồi để tiếp tục làm việc lâu dài.
- [ ] Không duy trì một “người hùng” duy nhất cho hệ thống quan trọng.
- [ ] Giảm WIP và ưu tiên hoàn tất giá trị trước khi kéo thêm việc.

**Khả năng duy trì chất lượng:**

- [ ] Có Definition of Done/chính sách hoàn tất rõ và không hạ chuẩn vì áp lực deadline.
- [ ] TDD được dùng ở những rủi ro phù hợp, với vòng red–green–refactor có ý nghĩa.
- [ ] Kiểm thử đơn vị không bị coi là thay thế toàn bộ kiểm thử tích hợp, quyền và đồng thời.
- [ ] Pipeline CI cung cấp phản hồi đáng tin; test flaky và build đỏ được xử lý.
- [ ] Refactoring diễn ra bằng bước nhỏ, có kiểm tra bảo vệ hành vi.
- [ ] Pairing và collective ownership giúp chia sẻ kiến thức trong khu vực rủi ro.
- [ ] Thiết kế đơn giản đáp ứng nhu cầu hiện biết, không xây trước phức tạp không có căn cứ.
- [ ] Lát cắt nhỏ được bàn giao theo tiêu chuẩn chất lượng phù hợp, không chỉ “xong code”.
- [ ] Công việc sửa lỗi và nợ kỹ thuật được cân nhắc theo tác động lên sản phẩm và khả năng giao.

**Đo lường và cải tiến:**

- [ ] Velocity, throughput, cycle time và số điểm được diễn giải theo định nghĩa nhất quán.
- [ ] Không dùng điểm, số giờ làm hoặc bug cá nhân để xếp hạng con người.
- [ ] Có quan sát lỗi lọt sau phát hành, làm lại, WIP, blocker và độ ổn định của CI.
- [ ] Outcome người dùng được theo dõi cùng chất lượng, thay vì chỉ đếm output.
- [ ] Nhóm kiểm tra nguyên nhân trước khi kết luận năng suất tăng hoặc giảm.
- [ ] Retrospective hoặc nhịp cải tiến chọn được hành động cụ thể có người phối hợp và mốc đánh giá.
- [ ] Stakeholder hiểu những đánh đổi phạm vi, chất lượng, thời gian và năng lực.
- [ ] Khi thay đổi phương pháp hay chuẩn Done, nhóm ghi rõ để không so sánh dữ liệu sai lệch.

**Kết luận:** Trong Extreme Programming, **nhịp làm việc bền vững và khả năng duy trì chất lượng là hai mặt của cùng một năng lực**. Khi nhóm không cần dựa vào làm quá sức, dùng TDD, pairing, CI, refactoring và thiết kế đơn giản để bảo vệ thay đổi, rồi giao các lát cắt nhỏ có ích, họ có cơ hội nhận phản hồi sớm mà không liên tục vay mượn khả năng của tương lai. Thành công không được đo bằng số giờ làm thêm hay một Sprint có velocity cao, mà bằng **việc tiếp tục đưa phần mềm hữu ích, đáng tin đến người dùng qua nhiều vòng với cách làm việc có thể duy trì và cải tiến**.
