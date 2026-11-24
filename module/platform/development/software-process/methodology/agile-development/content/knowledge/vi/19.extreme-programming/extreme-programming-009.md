# Lập trình cặp và chia sẻ hiểu biết khi phát triển

Một đội phần mềm có thể có nhiều lập trình viên giàu kinh nghiệm nhưng vẫn phụ thuộc vào một người duy nhất: chỉ người đó hiểu vì sao API phải trả một trạng thái đặc biệt, cách xử lý dữ liệu cũ hay vì sao một kiểm thử tưởng dư thừa lại rất quan trọng. Khi người ấy vắng mặt, các hạng mục khác bị chặn. Trong khi đó, sai lệch giữa giao diện, nghiệp vụ và backend có thể chỉ được phát hiện sau nhiều ngày làm việc độc lập.

**Lập trình cặp (pair programming)** là thực hành nổi bật của **Extreme Programming (XP)**: hai người cùng tập trung phát triển **một hạng mục tại một thời điểm**, thảo luận liên tục về yêu cầu, thiết kế, mã nguồn và kiểm chứng. Một người thường trực tiếp thao tác — **driver**; người còn lại quan sát và định hướng ở mức rộng hơn — **navigator**. Hai người có thể đổi vai thường xuyên, cùng tham gia suy nghĩ và chịu trách nhiệm về chất lượng.

Lập trình cặp **không phải hai người được giao hai task rồi ngồi cạnh nhau**, cũng không phải một người viết mã còn người kia im lặng kiểm tra lỗi. Đó là một phương thức phản hồi kỹ thuật sớm và **chia sẻ hiểu biết ngay trong quá trình làm việc**.

Bài thuộc chương **Extreme Programming** của mô-đun **AGILE_DEVELOPMENT**, kết nối giá trị Agile — phản hồi sớm, giao phần mềm tăng dần, cải tiến liên tục — với user story, Product Backlog, Scrum, Kanban, XP và đo lường dòng công việc.

Sau bài học, người học có thể:

- Giải thích cơ chế, mục tiêu và giới hạn của pair programming.
- Phân biệt vai trò driver/navigator, đổi vai và luân chuyển cặp giữa thành viên.
- Kết hợp lập trình cặp với **TDD, Continuous Integration, refactoring và collective code ownership**.
- Tổ chức một phiên ghép cặp có mục tiêu, tiêu chí chấp nhận và cách ghi lại điều học được.
- Giảm phụ thuộc kiến thức vào cá nhân mà không tạo thêm những nghi thức không cần thiết.
- Quyết định khi nào nên pair, khi nào cần review độc lập hoặc cách phối hợp khác.
- Đánh giá hiệu quả bằng chất lượng, dòng công việc và khả năng tiếp nối, không dùng số giờ ghép cặp làm KPI.

## 1. Vì sao chia sẻ hiểu biết là một vấn đề kỹ thuật và tổ chức?

Xét một nền tảng học trực tuyến có chức năng **lưu và khôi phục tiến độ học**. Người hiểu API lưu dữ liệu, người làm giao diện và người thiết kế kiểm thử là ba người khác nhau. Một lỗi xảy ra:

> Học viên nhận thông báo “Đã lưu tiến độ”, nhưng khi mở lại trang lại phải học từ vị trí cũ.

Nếu ba người làm việc hoàn toàn tách biệt, công việc có thể đi qua nhiều lần bàn giao: frontend đợi backend trả lời, backend đợi quyết định quy tắc nghiệp vụ, kiểm thử đợi cả hai sửa xong. Tất cả đều bận nhưng **giá trị chưa đến tay người dùng**.

| Dấu hiệu | Nguyên nhân có thể | Tác động |
| --- | --- | --- |
| Chỉ một người dám sửa module quan trọng | Kiến thức tập trung, thiếu kiểm thử/tài liệu | Công việc bị chặn khi người đó vắng mặt |
| Hai thành phần hiểu khác cùng một trạng thái | Trao đổi và kiểm chứng ranh giới tích hợp muộn | Lỗi chỉ lộ ra khi chạy end-to-end |
| Pull request lớn chờ review nhiều ngày | Phản hồi kỹ thuật xuất hiện sau khi viết nhiều mã | Tăng làm lại và khó tìm nguyên nhân |
| Người mới chỉ đọc tài liệu, chưa thực hiện được thay đổi | Thiếu trải nghiệm thực và phản hồi trong ngữ cảnh | Onboarding kéo dài |
| Một quyết định thiết kế chưa có phản biện | Giả định thiếu kiểm chứng | Rủi ro lỗi hoặc kiến trúc không cần thiết |
| Luồng công việc phụ thuộc người chuyên trách | Cách tổ chức kỹ năng và quyền hạn | Hàng đợi kéo dài qua nhiều bước |

Pair programming giải quyết **một phần** các vấn đề ấy: người tham gia cùng thấy bối cảnh, chất vấn giả định và hiểu quyết định ngay khi nó được tạo ra. Tuy nhiên, **pair không thay thế tài liệu rõ ràng, kiểm thử tự động, trao đổi với Product Owner hoặc chính sách bảo mật**.

## 2. Pair programming trong hệ thực hành XP

XP thường gắn lập trình cặp với các thực hành kỹ thuật khác, bởi nhiều lợi ích chỉ xuất hiện khi chúng hỗ trợ lẫn nhau.

| Thực hành | Mục đích | Sự bổ trợ của lập trình cặp |
| --- | --- | --- |
| **Test-Driven Development (TDD)** | Phát triển bằng vòng kiểm thử thất bại, làm đạt, rồi cải thiện mã | Một người viết/thực hiện bước nhỏ, người kia chất vấn hành vi và trường hợp biên |
| **Continuous Integration (CI)** | Tích hợp những thay đổi nhỏ thường xuyên và phát hiện lỗi sớm | Cặp giữ thay đổi có mục tiêu, kiểm tra trước khi tích hợp |
| **Refactoring** | Cải thiện cấu trúc mà không cố ý đổi hành vi | Navigator nhận ra trùng lặp hoặc tên thiếu rõ ràng |
| **Simple Design** | Tránh thiết kế phức tạp hơn nhu cầu hiện tại | Cặp thảo luận giả định và chọn phương án đủ đơn giản |
| **Collective Code Ownership** | Nhóm cùng có khả năng cải thiện mã theo quy ước | Luân chuyển cặp giúp kiến thức không thuộc riêng một người |
| **Coding Standards** | Làm mã nhất quán và dễ hiểu | Chuẩn được giải thích và áp dụng trong lúc phát triển |
| **Small Releases** | Giao giá trị sớm, học từ phần mềm thật | Cặp tập trung hoàn tất lát cắt có kiểm chứng, không chỉ mở nhiều việc |

Các giá trị thường được nhắc tới trong XP là **communication, simplicity, feedback, courage và respect** — giao tiếp, đơn giản, phản hồi, dũng cảm và tôn trọng. Pair programming không có nghĩa bắt buộc mọi tranh luận phải đạt đồng thuận tuyệt đối, mà đòi hỏi **nêu được lý do, xem được bằng chứng và giữ môi trường tôn trọng**.

### Một số hiểu nhầm cần loại bỏ

- **“Chỉ hai người mở cùng IDE là XP.”** Chưa đủ; họ cần một mục tiêu chung và trao đổi chủ động.
- **“Hai người cùng làm một việc chắc chắn nhanh gấp đôi.”** Không đúng; chi phí phối hợp là thật và kết quả phụ thuộc ngữ cảnh.
- **“Pair thay thế mọi code review.”** Không luôn đúng, nhất là khi có yêu cầu review hoặc phê duyệt độc lập.
- **“Cứ ghép người mới với senior là kiến thức tự lan truyền.”** Chưa chắc nếu người mới không được thực hành và giải thích lại.
- **“Pairing tạo ra nhiều story point hơn.”** Story point không phải chỉ số năng suất và không đo giá trị người dùng.

## 3. Hai vai trò driver và navigator

Trong một phiên pair programming điển hình:

- **Driver:** Người trực tiếp gõ mã, viết kiểm thử, điều khiển IDE và chạy lệnh. Driver quan tâm bước triển khai ngay trước mắt, đồng thời giải thích những gì đang làm.
- **Navigator:** Người quan sát mã và hướng suy nghĩ ở mức rộng hơn: mục tiêu người dùng, các trường hợp biên, tính đúng, thiết kế, phụ thuộc và bước kiểm chứng tiếp theo.

Cả hai **chủ động tham gia**; navigator không phải người chỉ đọc cú pháp hoặc theo dõi để đánh giá driver.

| Thời điểm | Driver | Navigator |
| --- | --- | --- |
| Chọn hành vi | “Tôi sẽ viết kiểm thử cho trạng thái lưu đang chờ.” | “Khi nào hệ thống được phép nói đã lưu thành công?” |
| Viết mã | Tạo nhánh xử lý kết quả API | Nhận diện phản hồi đến muộn có thể làm trạng thái sai |
| Chạy kiểm thử | Quan sát lỗi, tái hiện và thay đổi mã | Phân biệt lỗi kiểm thử với hiểu sai nghiệp vụ |
| Refactor | Đổi tên/tách hàm và chạy lại test | Kiểm tra rằng cấu trúc mới không phức tạp hơn cần thiết |
| Kết thúc | Tích hợp và ghi trạng thái thực tế | Đối chiếu acceptance criteria và rủi ro còn lại |

### Vì sao cần đổi vai?

Nếu chỉ một người thao tác nhiều giờ, người kia có thể mất tập trung hoặc không hình thành năng lực thực hành. **Đổi vai** tạo điều kiện để cả hai thử ý tưởng, trải nghiệm công cụ, giải thích quyết định và phát hiện điều mình chưa hiểu.

Không có quy tắc bắt buộc phải đổi sau đúng một số phút. Cặp có thể đổi sau một kiểm thử, sau một vòng refactor, một đoạn thay đổi nhỏ hoặc khi muốn người đang quan sát thử thực hiện. Điều quan trọng là **thực sự chia sẻ quyền tham gia**, không máy móc đổi bàn phím giữa câu lệnh gây mất nhịp.

### Driver không phải người nhận chỉ thị

Navigator có thể gợi ý, nhưng driver được quyền hỏi lại, phản biện và đưa phương án khác. Hai người cần cùng sở hữu quyết định. Nếu navigator liên tục ra lệnh từng ký tự, hoạt động sẽ giống điều khiển từ xa hơn là cộng tác kỹ thuật.

## 4. Một phiên lập trình cặp từ mục tiêu đến kết quả

Pair programming không đòi hỏi nghi thức dài. Một quy trình nhẹ giúp cặp giữ mục tiêu và tạo kết quả có thể tiếp nối:

~~~mermaid
flowchart TD
    A["Chọn lát cắt nhỏ và mục tiêu có giá trị"] --> B["Làm rõ tiêu chí chấp nhận, rủi ro và phạm vi"]
    B --> C["Thống nhất driver/navigator, cách đổi vai"]
    C --> D["Chọn kiểm thử hoặc bước kiểm chứng tiếp theo"]
    D --> E["Thực hiện thay đổi nhỏ, trao đổi và chạy test"]
    E --> F{"Hành vi đúng, cấu trúc đủ rõ?"}
    F -->|Chưa| G["Làm rõ giả định, sửa hoặc thử phương án khác"]
    G --> D
    F -->|Rồi| H["Refactor, tích hợp và kiểm tra tiêu chí Done"]
    H --> I["Ghi quyết định, phần chưa xong và bước tiếp theo"]
~~~

### Bước 1 — Chọn hành vi nhỏ

Ví dụ:

> Khi dịch vụ lưu tiến độ chưa xác nhận thành công, giao diện không tuyên bố rằng tiến độ đã được lưu.

Đây là mục tiêu có thể kiểm chứng, tốt hơn mục tiêu mơ hồ “hai người cùng xử lý backend hôm nay”.

### Bước 2 — Kiểm tra điều chưa rõ

Nhóm hỏi:

1. “Đã lưu” có nghĩa dữ liệu bền vững hay chỉ yêu cầu đã được gửi?
2. Khi timeout, giao diện cần thể hiện trạng thái gì?
3. Nếu người dùng tải lại trang ngay, trạng thái nên được đọc từ đâu?
4. Nếu phản hồi cũ về muộn hơn phản hồi mới, quy tắc cập nhật là gì?
5. Cần bảo vệ quyền truy cập và dữ liệu học viên thế nào?

Những câu hỏi thuộc thẩm quyền nghiệp vụ phải được làm rõ với **Product Owner/người có thẩm quyền phù hợp**, không nên để hai người tự suy đoán thành chính sách sản phẩm.

### Bước 3 — Thống nhất cách làm việc

Cặp có thể thỏa thuận:

- Ai làm driver vòng đầu và lúc nào đổi vai.
- Người nào có thể yêu cầu dừng để làm rõ trường hợp lỗi hoặc vấn đề an toàn.
- Cách giải quyết bất đồng bằng kiểm thử và tiêu chí, thay vì tranh luận cá nhân.
- Thời điểm nghỉ và cách xử lý mất tập trung.
- Cách lưu một quyết định quan trọng để người khác không phải hỏi lại.

### Bước 4 — Đi từng vòng phản hồi nhỏ

Chọn một kiểm thử, quan sát kết quả, sửa mã vừa đủ và chạy lại. Nếu thấy rủi ro lớn ngoài story, ghi lại và thống nhất bước giải quyết thay vì tự mở rộng phạm vi vô hạn.

### Bước 5 — Để lại kết quả người khác có thể tiếp nối

Một phiên có thể kết thúc với một commit nhỏ đã kiểm tra, PR rõ ngữ cảnh, kiểm thử mới, quyết định kiến trúc ngắn hoặc câu hỏi còn mở. **Không cần ép mỗi phiên phải phát hành tính năng**, nhưng cần trung thực về trạng thái và khả năng tiếp nối.

## 5. Kết hợp TDD: Red–Green–Refactor khi làm cặp

**Test-Driven Development** thường được diễn giải qua ba bước:

1. **Red:** Viết kiểm thử thể hiện hành vi mong đợi, thấy kiểm thử thất bại đúng lý do.
2. **Green:** Viết mã tối thiểu đủ để kiểm thử đạt.
3. **Refactor:** Cải thiện cấu trúc trong khi giữ những kiểm thử hành vi đạt.

Trong cặp, navigator có thể hỏi “Hành vi nào cần chứng minh tiếp theo?”, driver tạo kiểm thử và mã, rồi hai người đổi vai.

### Ví dụ Java: hiển thị thông điệp lưu tiến độ

Một hàm đơn giản chuyển trạng thái từ API sang thông điệp hiển thị:

~~~java
enum SaveResult {
    CONFIRMED,
    PENDING,
    FAILED
}

final class SaveMessage {
    static String forResult(SaveResult result) {
        return switch (result) {
            case CONFIRMED -> "Đã lưu tiến độ";
            case PENDING   -> "Đang đồng bộ, chưa xác nhận lưu";
            case FAILED    -> "Chưa thể lưu tiến độ";
        };
    }
}
~~~

Đây là **ví dụ về một hàm thuần**, sử dụng cú pháp switch expression của Java hiện đại. Nó **không tự triển khai lưu trữ bền vững, retry, đồng bộ đa thiết bị, quyền truy cập hay giải quyết xung đột**; hệ thống thật cần xử lý riêng các vấn đề đó.

### Red — Viết kiểm thử trước khi hiện thực

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class SaveMessageTest {
    @Test
    void pendingMustNotClaimSaved() {
        assertEquals(
            "Đang đồng bộ, chưa xác nhận lưu",
            SaveMessage.forResult(SaveResult.PENDING)
        );
    }

    @Test
    void confirmedAndFailedMustDiffer() {
        assertEquals("Đã lưu tiến độ",
            SaveMessage.forResult(SaveResult.CONFIRMED));
        assertEquals("Chưa thể lưu tiến độ",
            SaveMessage.forResult(SaveResult.FAILED));
    }
}
~~~

Trong một chu trình TDD thực, cặp viết kiểm thử **trước khi có hiện thực**, quan sát lỗi biên dịch hoặc thất bại phù hợp, rồi mới bổ sung mã. Không nên viết kiểm thử sau và gọi lại là một vòng Red–Green.

### Green — Đạt kiểm thử bằng mã vừa đủ

Driver hiện thực cách chuyển đổi trạng thái. Navigator hỏi: “Ai tạo ra trạng thái CONFIRMED? Nó đã đại diện cho dữ liệu được lưu thật hay chưa?” Đây là câu hỏi quan trọng: **hàm hiển thị đúng không tự bảo đảm nguồn dữ liệu đúng**.

### Refactor — Nâng độ dễ hiểu, giữ hành vi

Cặp có thể xem lại tên biến, cấu trúc thông điệp và cách hỗ trợ đa ngôn ngữ. Nếu thay đổi cấu trúc, chạy lại kiểm thử. Không tạo thêm nhiều lớp trừu tượng chỉ vì “có thể dùng trong tương lai” khi chưa có nhu cầu.

### Kiểm thử đơn vị không thay kiểm thử tích hợp

Ví dụ trên chưa chứng minh API đã xác nhận ghi dữ liệu bền vững, không xử lý phản hồi cũ đến muộn và không chứng minh người dùng có thể khôi phục đúng tiến độ khi tải lại. Cặp cần kết hợp **acceptance criteria, kiểm thử tích hợp và điều kiện Done** với phạm vi thực tế của story.

## 6. Hai cơ chế chia sẻ kiến thức: đổi vai và luân chuyển cặp

**Đổi vai trong một cặp** giúp cả hai tham gia thực hiện. **Luân chuyển cặp giữa các thành viên** giúp hiểu biết lan ra nhiều người hơn.

| Cách làm | Ví dụ | Lợi ích | Rủi ro |
| --- | --- | --- | --- |
| **Đổi driver/navigator** | Sau một kiểm thử, người quan sát cầm bàn phím | Hai người trải nghiệm cả thiết kế và thao tác | Đổi quá dày làm đứt mạch tư duy |
| **Luân chuyển giữa các cặp** | A–B làm lưu tiến độ, sau đó B–C làm kiểm thử tích hợp | Nhiều người hiểu ranh giới hệ thống | Thiếu chuyển giao tạo chi phí làm quen |
| **Ghép khác chuyên môn** | Backend làm cùng frontend | Phát hiện giả định API/UI không khớp | Một người chiếm cuộc trao đổi bằng thuật ngữ |
| **Ghép senior/junior** | Người mới làm driver với hướng dẫn từ người nhiều kinh nghiệm | Học theo việc thật, nhận phản hồi nhanh | Trở thành hướng dẫn một chiều |
| **Ghép ngang kinh nghiệm** | Hai người cùng tìm cách sửa một lỗi khó | Kết hợp góc nhìn và phản biện thiết kế | Bất đồng kéo dài thiếu tiêu chí quyết định |

### Luân chuyển theo mục tiêu học tập

Ví dụ A biết API lưu dữ liệu, B hiểu giao diện, C giỏi kiểm thử và D mới vào đội:

1. **A–B:** Tìm cách thống nhất trạng thái lưu giữa backend và UI.
2. **B–C:** Xây kiểm thử tích hợp cho trường hợp mạng chập chờn.
3. **C–D:** D thực hiện một thay đổi nhỏ an toàn và giải thích được kiểm thử.

Không cần buộc mọi người ghép với tất cả đồng nghiệp trong cùng tuần. Nên chọn điểm đổi cặp khi phần việc đủ rõ để chuyển giao và tránh mất ngữ cảnh.

### Làm sao biết hiểu biết đã lan truyền?

Thay vì đếm số phiên pair, hãy xem:

- Người thứ hai có **giải thích được lý do** của một điều kiện và rủi ro liên quan không?
- Họ có thể sửa một lỗi tương tự bằng kiểm thử và quyền phù hợp không?
- Người ngoài cặp có hiểu quyết định từ kiểm thử, mã và ghi chú ngắn không?
- Khi một người vắng mặt, hạng mục còn có thể tiếp tục an toàn không?

**Biết tên file không đồng nghĩa hiểu hành vi.** Chia sẻ kiến thức phải thể hiện qua năng lực thực hành và giải thích lại.

## 7. Các kiểu ghép cặp và hình thức phối hợp gần gũi

### Driver–Navigator truyền thống

Hai người tập trung liên tục vào một thay đổi, một người thao tác, một người quan sát rộng hơn. Phù hợp khi cần phản hồi sớm về quyết định thiết kế và kiểm thử.

### Ping-pong TDD

Một cách luân phiên:

1. A viết một kiểm thử thất bại.
2. B bổ sung mã để kiểm thử đạt.
3. B viết kiểm thử tiếp theo.
4. A hiện thực; cả hai refactor khi phù hợp.

Nó tạo cơ hội cùng thiết kế kiểm thử, nhưng nếu chưa hiểu nghiệp vụ thì có thể chỉ khiến cặp viết nhanh nhiều kiểm thử cho một giả định sai.

### Strong-style pairing

Một người có ý tưởng diễn giải để người kia thực hiện, thay vì chiếm bàn phím. Cách này khuyến khích làm rõ tư duy và hữu ích khi truyền kiến thức. Cần đồng thuận, không dùng nó để làm khó người mới hoặc tạo áp lực.

### Ensemble / mob programming

Nhiều hơn hai người cùng tập trung một vấn đề có thể hữu ích khi cần kết hợp kiến thức về nghiệp vụ, thiết kế, kiểm thử và vận hành. Nhưng chi phí phối hợp lớn; không nhất thiết huy động cả nhóm cho mọi sửa đổi nhỏ.

### Code review không đồng bộ

Review một pull request thường xảy ra **sau khi mã đã được viết**, còn pair programming đem lại phản hồi **ngay khi quyết định được tạo ra**. Hai cách có thể bổ trợ nhau. Nếu tổ chức có kiểm soát độc lập, bảo mật hoặc nghĩa vụ phê duyệt, **pairing không tự động thay thế những kiểm soát đó**.

## 8. Collective Code Ownership và giảm phụ thuộc cá nhân

**Sở hữu mã nguồn tập thể (collective code ownership)** là tư duy XP rằng mã là trách nhiệm chung của nhóm: người có chuyên môn và quyền phù hợp có thể cải thiện những phần cần thiết, tuân thủ tiêu chuẩn mã và kiểm thử chung.

Điều đó **không** có nghĩa ai cũng được sửa bất kỳ đoạn mã nào mà không cần hiểu rủi ro, kiểm thử hoặc quyền truy cập. Nó còn không có nghĩa mọi thành viên phải trở thành chuyên gia của mọi module ngay lập tức.

### Ví dụ rủi ro phụ thuộc

Module tiến độ học chỉ một Developer hiểu xử lý trạng thái cũ. Các hạng mục và sự cố liên quan liên tục chờ người đó. Một số đội dùng khái niệm **bus factor** để mô tả mức phụ thuộc vào vài người có kiến thức quan trọng. Không nên dùng khái niệm này để **xếp hạng hay tạo áp lực cá nhân**; vấn đề cần cải thiện là hệ thống chia sẻ năng lực.

| Cơ chế | Cách giảm rủi ro |
| --- | --- |
| Luân chuyển cặp có mục tiêu | Nhiều người được trực tiếp xử lý hành vi quan trọng |
| Kiểm thử rõ ràng | Ghi lại các quy tắc cần được bảo vệ |
| Nhật ký quyết định ngắn | Lưu lý do chọn giải pháp và giới hạn |
| Tiêu chuẩn mã và cấu trúc dễ đọc | Người khác có thể hiểu nhanh hơn |
| Refactoring thường xuyên | Giảm mã khó hiểu và phụ thuộc tri thức ngầm |
| Onboarding bằng một thay đổi thật | Người mới học luồng công việc và tiêu chuẩn |
| Quan sát khả năng tiếp nối | Xem liệu công việc có tiếp tục khi một người vắng mặt |

### Pair không thay việc chia sẻ ngữ cảnh

Nếu A và B cùng pair nhưng những thay đổi quan trọng không có kiểm thử, không ghi lý do và chỉ A–B hiểu phần mã, đội vẫn còn phụ thuộc vào một **cặp cố định**. Nên kết hợp **luân chuyển có chủ đích, tài liệu ngắn và mã kiểm chứng được**.

## 9. Giao tiếp và giải quyết bất đồng trong cặp

Pair programming tạo nhiều cơ hội phản hồi, nhưng có thể thất bại nếu người tham gia không tôn trọng nhau.

| Cách nói gây khó cộng tác | Cách phản hồi dựa trên bằng chứng |
| --- | --- |
| “Cách này sai, tôi biết tốt hơn.” | “Ta thử kiểm tra trường hợp nào khiến cách này không đáp ứng yêu cầu.” |
| “Đừng hỏi chuyện cơ bản.” | “Phần này có ngữ cảnh API; tôi giải thích, sau đó bạn thử triển khai.” |
| “Tôi làm cho nhanh, bạn nhìn.” | “Sau bước này mình đổi vai để cả hai hiểu rõ phần thay đổi.” |
| “Viết test mất thời gian.” | “Kiểm thử nhỏ nhất nào giúp phát hiện sai trước khi tích hợp?” |
| “Trước giờ luôn làm thế.” | “Quy tắc cũ bảo vệ điều gì, và bối cảnh hiện tại có khác không?” |
| “Đây là code của tôi.” | “Chúng ta thống nhất trách nhiệm chung và tiêu chuẩn thay đổi thế nào?” |

### Một quy trình xử lý bất đồng kỹ thuật

1. Nêu **mục tiêu và tiêu chí**: tính đúng, an toàn, đơn giản, hiệu năng hay khả năng bảo trì.
2. Mô tả **hai giả định khác nhau**, không gắn nhãn ai đúng ai sai.
3. Viết một ví dụ hoặc kiểm thử phân biệt hai phương án.
4. Nếu bất định lớn, làm **spike ngắn có giới hạn** hoặc hỏi chuyên gia thích hợp.
5. Ghi quyết định đủ để người khác hiểu và xem lại nếu có bằng chứng mới.

Không phải mọi khác biệt đều cần tranh luận lâu. Nếu hai phương án an toàn tương đương và dễ thay đổi, có thể thử một phương án rồi đo, thay vì mất cả ngày cố “thắng”.

## 10. Pairing giữa người mới và người có kinh nghiệm

Ghép senior/junior có thể hữu ích cho onboarding nếu người mới **được tự thao tác và giải thích**.

### Cách tổ chức tốt

- Bắt đầu bằng một user story hoặc sửa lỗi nhỏ, có kiểm thử và ranh giới rõ.
- Cho người mới làm **driver** trong phần phù hợp, không chỉ ngồi quan sát.
- Người nhiều kinh nghiệm giải thích **vì sao** cần một điều kiện, không chỉ đưa phím tắt.
- Dừng để làm rõ thuật ngữ, kiến trúc và bối cảnh nghiệp vụ.
- Để người mới tự trình bày lại logic và đề xuất kiểm thử.
- Kiểm tra kết quả bằng tiêu chí chất lượng chung, không chỉ sự đồng ý của mentor.

### Chênh lệch quyền lực

Nếu navigator đồng thời là người quản lý hiệu suất, người mới có thể ngại nêu ý tưởng hoặc nhận lỗi. Cần công khai mục tiêu phiên ghép cặp là **học hỏi và tạo phần mềm**, không phải kỳ thi bí mật. Khi có đánh giá chính thức, tiêu chí và quyền tham gia phải minh bạch.

### Senior cũng được lợi

Người mới thường hỏi những câu tưởng hiển nhiên nhưng có thể phát hiện một giả định lỗi: “Nếu hệ thống chỉ biết đã gửi yêu cầu, vì sao UI báo đã lưu thành công?”. **Chia sẻ hiểu biết là hai chiều**, không chỉ truyền từ người nhiều kinh nghiệm sang người mới.

## 11. Pair programming từ xa: phối hợp mà không bỏ an toàn

Pairing có thể diễn ra qua chia sẻ màn hình, IDE cộng tác hoặc phiên điều khiển từ xa được phép. Hai người không nhất thiết ở cùng văn phòng.

### Chuẩn bị trước phiên

1. Chọn hạng mục nhỏ và tiêu chí kiểm chứng.
2. Thống nhất công cụ, quyền truy cập và cách chuyển driver.
3. Kiểm tra cả hai có thể nhìn, nghe và tham gia chủ động.
4. Thỏa thuận thời gian nghỉ và kênh hỏi người ngoài cặp.
5. Chọn dữ liệu mẫu thay vì dùng dữ liệu nhạy cảm của khách hàng.

| Rủi ro khi làm từ xa | Cách xử lý |
| --- | --- |
| Một người không có quyền thao tác | Cấp quyền phù hợp theo chính sách, không chia sẻ mật khẩu |
| Độ trễ âm thanh/hình ảnh | Dùng bước nhỏ và nói rõ lúc đổi vai |
| Vô tình hiển thị token hoặc dữ liệu cá nhân | Ẩn bí mật và sử dụng môi trường/dữ liệu an toàn |
| Hai người cùng thao tác gây xung đột | Thống nhất ai đang làm driver |
| Cuộc gọi dài khiến mọi người kiệt sức | Chia phiên, nghỉ và cho phép công việc tập trung độc lập |
| Khác múi giờ hoặc điều kiện tiếp cận | Tôn trọng lịch làm việc và công cụ hỗ trợ phù hợp |

Pair programming không phải lý do để vượt **nguyên tắc quyền tối thiểu, kiểm soát dữ liệu hoặc chính sách bảo mật**. Nếu một người không được phép truy cập dữ liệu thật, dùng môi trường kiểm thử với dữ liệu phù hợp và quyền được cấp.

## 12. Khi nào nên ghép cặp và khi nào không cần?

Pairing tiêu tốn sự tập trung của hai người trên một hạng mục, nên cần đánh đổi với lợi ích về chất lượng, tri thức và phản hồi.

| Bối cảnh | Lựa chọn gợi ý | Lý do |
| --- | --- | --- |
| Logic quan trọng với nhiều trường hợp lỗi | **Đáng cân nhắc pair** | Hai góc nhìn giúp phát hiện sai sớm |
| Lỗi khó tái hiện, liên quan nhiều thành phần | **Pair hoặc ensemble ngắn** | Kết nối ngữ cảnh và phân tích nguyên nhân |
| Module chỉ một người hiểu | **Pair và luân chuyển có chủ đích** | Giảm phụ thuộc kiến thức |
| Lát cắt mới đi qua UI, API và dữ liệu | **Pair liên chuyên môn** | Thống nhất hợp đồng tích hợp |
| Đổi tên một biến đã rõ, có test | **Có thể tự làm và review phù hợp** | Chi phí ghép cặp có thể cao hơn lợi ích |
| Đọc sâu tài liệu hoặc thử nhiều hướng riêng | **Có thể nghiên cứu độc lập rồi hợp cặp** | Một số phút tập trung cá nhân hữu ích hơn |
| Sự cố bảo mật nghiêm trọng | **Chỉ theo quy trình sự cố và quyền hạn** | Cần kiểm soát và phân vai rõ |
| Người tham gia mệt mỏi, giao tiếp không hiệu quả | **Tạm dừng hoặc điều chỉnh** | Ghép cặp ép buộc có thể giảm chất lượng |

### Đừng chỉ đếm “hai người làm việc của một người”

Một cặp có thể viết ít mã hơn trong một giờ so với hai người làm độc lập, nhưng giảm được nhiều giờ **review, sửa lỗi, chuyển giao hoặc chờ chuyên gia**. Ngược lại, pairing cũng có thể không hiệu quả trên công việc cơ học đơn giản. Cần đánh giá **dòng công việc end-to-end và chất lượng**, không tuyên bố luôn nhanh hơn hay luôn chậm hơn.

### Pair có chọn lọc, không tạo quy định 100% thời gian

Đội có thể dành phiên pairing cho các điểm bất định, thiết kế và xử lý lỗi, còn lại có thời gian đọc tài liệu, suy nghĩ riêng hoặc hoàn thành công việc đã rõ. **Không có tỷ lệ thời gian pairing bắt buộc cho mọi đội Agile**.

## 13. Phản hồi ngay khi viết mã so với review sau đó

Một luồng làm việc phổ biến:

~~~text
Developer viết một thay đổi lớn
       -> Tạo pull request
       -> Chờ reviewer
       -> Nhận ý kiến, sửa
       -> Chờ review lại
       -> Tích hợp, phát hiện lỗi khác
~~~

Pair programming có thể giúp nhận câu hỏi và phản biện **trong lúc thiết kế hoặc viết kiểm thử**, làm pull request nhỏ hơn và rõ ngữ cảnh hơn.

~~~mermaid
flowchart LR
    A["Lát cắt nhỏ, mục tiêu rõ"] --> B["Cặp tạo kiểm thử và mã"]
    B --> C["Đổi vai, kiểm tra các giả định"]
    C --> D["CI và kiểm thử tự động"]
    D --> E["Review độc lập nếu chính sách yêu cầu"]
    E --> F["Increment chất lượng"]
    F --> G["Phản hồi và cải tiến"]
~~~

**Ranh giới:** Hai người cùng xem mã **không mặc nhiên thay thế review độc lập** nếu chính sách tổ chức, kiểm soát an toàn hoặc tuân thủ yêu cầu người khác xác nhận. Pairing nên giúp mã **dễ kiểm chứng**, không dùng làm lý do bỏ bước kiểm soát cần thiết.

## 14. Kết hợp XP với Scrum và Product Backlog

Trong Scrum, **Product Owner** chịu trách nhiệm quản lý Product Backlog để tối đa hóa giá trị; **Developers** chịu trách nhiệm tạo Increment đáp ứng Definition of Done và lập kế hoạch trong Sprint; **Scrum Master** hỗ trợ việc áp dụng Scrum và hiệu quả Scrum Team.

### Ví dụ chuyển một user story thành công việc có thể pair

Product Owner ưu tiên:

> Là học viên đang học dở, tôi muốn quay lại đúng vị trí đã được lưu thành công, để không phải học lại phần trước.

Sau khi làm rõ tiêu chí chấp nhận và phạm vi, Developers chọn một lát cắt, quyết định ghép cặp để xử lý API và trạng thái UI. Họ viết kiểm thử, tích hợp và hoàn thiện theo Definition of Done.

Trong **Daily Scrum**, Developers xem tiến độ hướng tới Sprint Goal và điều chỉnh kế hoạch; không cần báo “đã pair sáu giờ” như KPI. Trong **Sprint Review**, người dùng thử Increment và phản hồi trải nghiệm. Trong **Sprint Retrospective**, đội đánh giá pairing có giảm phụ thuộc và lỗi tích hợp không rồi cải tiến cách làm.

**Pair programming là kỹ thuật do Developers lựa chọn phù hợp với mục tiêu**, không phải Scrum event hay phương thức Scrum Master dùng để giao việc cho từng cá nhân.

## 15. Kanban, Lean và những nút thắt mà pairing có thể giúp giảm

Một bảng công việc giả định:

| Trạng thái | Số hạng mục |
| --- | ---: |
| Đang phát triển | 4 |
| Chờ review | 6 |
| Đang review | 1 |
| Chờ kiểm thử | 3 |
| Đang kiểm thử | 1 |

Nếu nhiều hạng mục **chờ review**, pairing với thay đổi rủi ro và gửi PR nhỏ có thể giúp giảm vòng sửa–review. Cũng có thể nhóm cần **giảm WIP và hỗ trợ hoàn tất những việc đang chờ** thay vì bắt đầu thêm story.

Nếu toàn bộ hạng mục chờ **môi trường kiểm thử hoặc quyết định nghiệp vụ**, tăng số cặp viết mã thường không giải quyết được. Phải xử lý đúng nguyên nhân.

### Các chỉ số cần xem cùng nhau

| Tín hiệu | Giúp trả lời điều gì? | Giới hạn |
| --- | --- | --- |
| **Cycle time** | Hạng mục đi từ bắt đầu đến Done có nhanh hơn? | Công việc khác độ khó cần được đặt trong bối cảnh |
| **Thời gian chờ review** | Phản hồi kỹ thuật có đến sớm và dễ xử lý hơn? | Không bỏ các kiểm soát độc lập bắt buộc |
| **WIP / Work Item Age** | Có bớt việc dở dang hoặc bị kẹt lâu? | Không ẩn blocked để làm đẹp dữ liệu |
| **Lỗi trước/sau bàn giao** | Chất lượng có thay đổi? | Số lỗi phụ thuộc cách phát hiện và báo cáo |
| **Khả năng tiếp nối** | Có nhiều người hiểu và sửa an toàn module? | Không đánh giá bằng tên người dự phiên pair |
| **Outcome người dùng** | Thay đổi có đem lại giá trị? | Không quy mọi kết quả cho pairing |

**Lean và Kanban quan tâm hiệu quả toàn hệ thống**, không phải tỷ lệ bận của từng Developer. Hai người giúp một hạng mục đạt Done sớm có thể đem lại nhiều giá trị hơn hai người mở hai việc rồi cùng bị chặn.

## 16. Case study: module tiến độ học phụ thuộc một chuyên gia

**Bối cảnh giả định:** Đội xây nền tảng học có bốn Developers: An hiểu API tiến độ, Bình chuyên giao diện, Chi làm kiểm thử tích hợp và Dũng mới tham gia. Lỗi lưu tiến độ thường phải chờ An giải quyết. Nhóm muốn giảm phụ thuộc và phát hiện sai lệch giữa UI/API sớm hơn.

### Vấn đề gốc

| Quan sát | Rủi ro |
| --- | --- |
| Chỉ An biết quy tắc dữ liệu cũ không ghi đè dữ liệu mới | Khi An vắng mặt, sự cố khó xử lý |
| Backend và UI hiểu khác điều kiện “đã lưu” | Người dùng nhận thông báo sai |
| Pull request lớn chỉ được review cuối Sprint | Khó nhận phản hồi sớm |
| Chi chưa có đủ môi trường kiểm thử | Lỗi tích hợp đến muộn |
| Dũng chỉ đọc tài liệu mà ít sửa mã | Chậm tạo năng lực tiếp nối |

Không nên đổ lỗi cho An. Kiến thức tập trung thường là kết quả của cách phân việc và ưu tiên từ trước; cần **thay đổi hệ thống cộng tác**.

### Vòng 1 — An và Bình: thống nhất API và UI

Cặp lấy mục tiêu nhỏ: **chỉ hiển thị “Đã lưu” sau khi dịch vụ xác nhận thành công**. An làm driver vòng đầu, Bình làm navigator và hỏi về thông điệp giao diện. Họ bổ sung kiểm thử cho trạng thái confirmed/pending/failed. Sau khi đổi vai, Bình viết phần UI còn An theo dõi hợp đồng dữ liệu.

**Hiểu biết mới:** Gửi yêu cầu lưu không đồng nghĩa dữ liệu được xác nhận đã lưu. Ranh giới tích hợp cần điều kiện rõ, không chỉ đặt tên response đẹp.

### Vòng 2 — Bình và Chi: làm rõ kiểm thử

Bình giải thích luồng UI; Chi làm driver để viết kiểm thử tích hợp:

1. Đã xác nhận lưu → tải lại đọc đúng tiến độ.
2. Mất mạng trước xác nhận → không báo thành công sai.
3. Phản hồi cũ đến muộn → không tự ghi đè trạng thái mới trái quy tắc.

Nếu quy tắc xử lý phản hồi cũ chưa được nghiệp vụ xác nhận, cặp ghi câu hỏi để đúng người quyết định thay vì tự kết luận.

### Vòng 3 — Chi và Dũng: học bằng việc thực

Dũng làm driver để thêm một kiểm thử hồi quy và sửa một phần xử lý nhỏ, an toàn. Chi giải thích cách tái hiện, đọc log thử nghiệm và kiểm chứng không dùng dữ liệu nhạy cảm. Cuối phiên, Dũng trình bày lại vì sao thông báo lưu có thể sai và những kiểm thử nào bảo vệ hành vi.

**Bằng chứng chia sẻ kiến thức:** Dũng có thể giải thích và thực hiện một thay đổi nhỏ, không chỉ nhớ rằng “Chi đã hướng dẫn”.

### Bàn giao và xem lại

Khi lát cắt đạt Definition of Done, nhóm bàn giao phù hợp và quan sát phản hồi người học. Trong Sprint Review, một học viên đề nghị làm rõ “Đang đồng bộ”. Product Owner cân nhắc cập nhật Product Backlog. Trong Retrospective, Developers xem:

- Có bao nhiêu việc vẫn bị chặn vì chờ An?
- PR có rõ và dễ review hơn?
- Lỗi tích hợp có được phát hiện trước khi phát hành?
- Dũng có thể tiếp nối luồng làm việc không?
- Cặp có tạo mệt mỏi hay gián đoạn quá lớn không?

Không nên kết luận chắc chắn pairing gây ra mọi thay đổi chỉ từ một Sprint; cần quan sát qua nhiều vòng với bối cảnh rõ.

## 17. Đánh giá hiệu quả: học hỏi, dòng công việc và chất lượng

Nếu đội đặt KPI “mỗi người pair 30 giờ/tuần”, họ có thể đạt số giờ mà người dùng vẫn gặp lỗi, module vẫn phụ thuộc một người hoặc ai cũng kiệt sức. Hãy dùng ba lớp:

| Lớp | Câu hỏi | Bằng chứng hữu ích |
| --- | --- | --- |
| **Kiến thức** | Thêm người có thể sửa và giải thích phần mã quan trọng? | Bài kiểm thử, thay đổi thực, khả năng chuyển giao |
| **Dòng công việc** | Phản hồi và thời gian hoàn thành hạng mục có cải thiện? | Thời gian chờ review, WIP, cycle time, blocked |
| **Chất lượng và giá trị** | Phần mềm đáng tin hơn và phục vụ nhu cầu tốt hơn? | Lỗi, khả năng phục hồi, DoD và outcome |

### Một phép thử hai Sprint

~~~text
Vấn đề:
  Module lưu tiến độ phụ thuộc một người,
  PR liên quan thường chờ review lâu.

Giả thuyết:
  Pair và luân chuyển có mục tiêu giúp phát hiện sai sớm,
  giảm hàng chờ và tạo thêm người hiểu hành vi quan trọng.

Phạm vi:
  Ghép cặp cho các thay đổi rủi ro trong module tiến độ;
  không bắt buộc mọi task phải pair.

Tín hiệu:
  Người khác sửa được module an toàn,
  kiểm thử và review có rõ hơn không,
  cycle time, lỗi tích hợp và mức mệt mỏi.

Xem lại:
  Cuối mỗi Sprint và tổng kết sau hai Sprint;
  tiếp tục, điều chỉnh, đổi cặp hoặc dừng theo dữ liệu.
~~~

**Cẩn trọng với quan hệ nhân quả:** Nếu lỗi giảm, có thể đồng thời do CI tốt hơn, thay đổi nhỏ hơn, môi trường ổn định hơn hoặc phạm vi thí điểm ít rủi ro. Nên ghi bối cảnh, không tuyên bố tỷ lệ cải thiện chính xác khi thiếu bằng chứng.

## 18. Những phản mẫu cần tránh

| Phản mẫu | Hậu quả | Hướng điều chỉnh |
| --- | --- | --- |
| Một người thao tác, người kia xem thụ động | Không chia sẻ năng lực | Chủ động driver/navigator và đổi vai |
| Senior luôn giữ bàn phím | Người mới thiếu thực hành | Cho người mới làm driver trên hạng mục phù hợp |
| Pairing được dùng để giám sát nhân viên | Giảm cởi mở, tăng áp lực | Tách học hỏi khỏi đánh giá nhân sự |
| Bắt cặp toàn thời gian, mọi task | Quá tải, chi phí cao | Chọn theo giá trị và rủi ro |
| Hai người cùng cuộc gọi nhưng làm hai task riêng | Không có phản hồi liên tục về một hạng mục | Phân biệt cộng tác song song với pair |
| Tranh luận theo thâm niên | Mất phản biện và niềm tin | Dùng ví dụ, test và tiêu chí rõ |
| Không đổi cặp | Kiến thức chỉ lan trong cặp cố định | Luân chuyển tại điểm chuyển giao hợp lý |
| Đổi cặp quá nhanh không ghi ngữ cảnh | Tốn thời gian tiếp nhận, thiếu trách nhiệm | Ghi lý do và bước kế tiếp |
| Không có kiểm thử hoặc acceptance criteria | Hai người có thể cùng hiểu sai | TDD, ví dụ nghiệp vụ, kiểm thử tích hợp |
| Coi pair thay review độc lập | Bỏ kiểm soát bắt buộc | Giữ yêu cầu review/tuân thủ thích hợp |
| Remote pairing lộ token/dữ liệu | Rủi ro an toàn nghiêm trọng | Quyền cá nhân và dữ liệu thử an toàn |
| Cuộc gọi kéo dài không nghỉ | Mệt, kém tập trung | Chia phiên, có khoảng nghỉ |
| Không ghi quyết định quan trọng | Người ngoài cặp vẫn thiếu ngữ cảnh | Tài liệu ngắn, mã và test rõ |
| Chỉ đo số giờ pairing | Tối ưu hình thức thay vì giá trị | Đo kiến thức, dòng công việc, chất lượng |

## 19. Bài thực hành: làm cặp từ user story đến kiểm thử

**Bối cảnh:** Nền tảng học trực tuyến có lỗi khi mạng ngắt: giao diện đôi khi hiển thị “Đã lưu” dù dịch vụ chưa xác nhận. Hai Developers cần sửa một lát cắt nhỏ.

### Bài 1 — Thống nhất driver/navigator và mục tiêu

Mục tiêu:

> Khi lưu chưa được xác nhận thành công, giao diện không tuyên bố tiến độ đã lưu.

Hãy trả lời:

1. Ai làm driver vòng đầu, ai làm navigator?
2. Navigator sẽ kiểm tra những giả định và trường hợp biên nào?
3. Khi nào đổi vai?
4. Nếu quy tắc nghiệp vụ chưa rõ, cần hỏi ai?
5. Bằng chứng nào xác nhận hoàn thành phần việc?

### Bài 2 — Viết ví dụ chấp nhận

~~~gherkin
Tính năng: Hiển thị trạng thái lưu tiến độ

  Kịch bản: Đã có xác nhận lưu
    Cho dịch vụ đã xác nhận lưu tiến độ thành công
    Khi học viên xem trạng thái
    Thì giao diện hiển thị "Đã lưu tiến độ"

  Kịch bản: Chưa có xác nhận
    Cho yêu cầu lưu đang chờ kết quả
    Khi học viên xem trạng thái
    Thì giao diện không hiển thị thông báo đã lưu thành công
    Và thể hiện rõ trạng thái đang đồng bộ

  Kịch bản: Lưu thất bại
    Cho dịch vụ trả kết quả thất bại
    Khi học viên xem trạng thái
    Thì giao diện thông báo chưa thể lưu
    Và không tuyên bố tiến độ đã được bảo toàn
~~~

Đây là kịch bản minh họa, cần được điều chỉnh theo hợp đồng dịch vụ, dữ liệu thật và quy tắc của sản phẩm.

### Bài 3 — Thực hiện Red–Green–Refactor

Dựa trên ví dụ Java ở mục 5:

1. **Red:** Viết kiểm thử cho trạng thái PENDING, quan sát thất bại.
2. **Green:** Hiện thực ánh xạ trạng thái để kiểm thử đạt.
3. **Refactor:** Cải thiện tên hoặc cấu trúc, giữ kiểm thử đạt.
4. **Đổi vai:** Navigator làm driver vòng kiểm thử kế tiếp.
5. **Mở rộng suy nghĩ:** Xác định kiểm thử tích hợp cần thiết để chứng minh trạng thái CONFIRMED thực sự đáng tin.

**Câu hỏi:** Nếu phản hồi từ một lần lưu cũ đến muộn hơn lần lưu mới, kiểm thử hoặc quy tắc nghiệp vụ nào cần được bổ sung? Không tự áp một thuật toán xung đột khi chưa rõ yêu cầu.

### Bài 4 — Lập kế hoạch luân chuyển cặp

| Thành viên | Thế mạnh | Mục tiêu học |
| --- | --- | --- |
| A | API và lưu trữ | Hiểu hành vi giao diện khi mạng lỗi |
| B | Giao diện | Hiểu xác nhận lưu và tính bền vững dữ liệu |
| C | Kiểm thử tích hợp | Hiểu xử lý phản hồi cũ |
| D | Người mới | Có thể sửa và kiểm thử một luồng nhỏ an toàn |

Đề xuất hai hoặc ba phiên ghép cặp với **mục tiêu học, người làm driver, điểm đổi vai, bằng chứng tiếp nối và rủi ro chuyển giao**. Không cần buộc mọi người phải ghép với nhau theo vòng tròn máy móc.

### Bài 5 — Chọn thực hành phù hợp theo rủi ro

Đánh giá các hạng mục:

- Sửa một lỗi có nguy cơ làm mất tiến độ người học.
- Đổi tên biến không đổi hành vi, có kiểm thử đầy đủ.
- Tích hợp API mới mà chỉ một người đã sử dụng.
- Làm rõ một vấn đề khả dụng với người thiết kế trải nghiệm.
- Di chuyển dữ liệu nhạy cảm có yêu cầu kiểm soát độc lập.

Với mỗi hạng mục, chọn **pair, làm độc lập rồi review, spike, phối hợp liên chuyên môn hoặc review độc lập bắt buộc**. Giải thích bằng rủi ro và lợi ích, không bằng khẩu hiệu “mọi task đều phải pair”.

### Bài 6 — Thiết kế thử nghiệm trong hai Sprint

Đội thấy PR review chờ lâu, module tiến độ chỉ một người hiểu. Hãy mô tả:

- **Giả thuyết:** Pairing cho những thay đổi rủi ro sẽ giảm hiểu sai và tăng người hiểu module.
- **Phạm vi thử:** Hai hoặc ba user story đủ nhỏ, có kiểm thử và ranh giới rõ.
- **Chính sách đổi vai/đổi cặp:** Có mục tiêu học, không đổi giữa chừng thiếu ngữ cảnh.
- **Tín hiệu:** Thời gian chờ review, cycle time, lỗi tích hợp, khả năng người khác sửa module, mức mệt mỏi.
- **Điểm xem lại:** Cuối từng Sprint và sau hai Sprint.
- **Quyết định tiếp:** Tiếp tục, điều chỉnh cách ghép, mở rộng hoặc dừng theo bằng chứng.

## 20. Checklist pairing có trách nhiệm

- [ ] Có **mục tiêu hành vi hoặc giá trị** cụ thể cho phiên.
- [ ] Hai người hiểu phạm vi, tiêu chí chấp nhận và các điều kiện chất lượng.
- [ ] Driver/navigator **đều chủ động**, không biến một người thành khán giả.
- [ ] Có kế hoạch đổi vai phù hợp để **cả hai được thực hành**.
- [ ] Bất đồng được xử lý bằng **kiểm thử, ví dụ và tiêu chí**, không áp đặt bằng thâm niên.
- [ ] Câu hỏi nghiệp vụ chưa rõ được đưa đến **người có thẩm quyền**.
- [ ] Kiểm thử, refactoring và tích hợp tuân thủ tiêu chuẩn nhóm.
- [ ] Luân chuyển cặp **có mục tiêu chia sẻ kiến thức**, tránh thay đổi hình thức.
- [ ] Quyết định quan trọng được ghi đủ để người ngoài cặp hiểu và tiếp nối.
- [ ] Pairing **không thay thế review độc lập** khi chính sách yêu cầu.
- [ ] Remote pairing bảo vệ quyền truy cập, thông tin bí mật và dữ liệu cá nhân.
- [ ] Tôn trọng nhịp làm việc, nghỉ ngơi và nhu cầu tiếp cận của người tham gia.
- [ ] Không ép pairing 100% nếu bối cảnh không phù hợp.
- [ ] Hiệu quả được đánh giá bằng **kiến thức, dòng công việc, chất lượng và outcome**, không chỉ giờ pair.
- [ ] Phản hồi từ pairing giúp đội cải tiến qua những vòng Agile tiếp theo.

## 21. Câu hỏi ôn tập

1. Pair programming khác việc hai người được giao chung một ticket nhưng thực hiện độc lập thế nào?
2. Driver và navigator có vai trò gì? Vì sao cả hai cần tham gia chủ động?
3. Đổi vai trong cặp khác luân chuyển cặp giữa nhiều thành viên ra sao?
4. Những giá trị XP nào hỗ trợ phản biện kỹ thuật mang tính xây dựng?
5. Lập trình cặp hỗ trợ chu trình TDD Red–Green–Refactor bằng cách nào?
6. Vì sao unit test của hàm hiển thị chưa chứng minh API đã lưu dữ liệu thành công?
7. Làm sao xác nhận **kiến thức được chia sẻ thật**, thay vì chỉ đếm người tham gia?
8. Sở hữu mã nguồn tập thể có nghĩa mọi người được phép sửa mã không cần kiểm thử hay quyền truy cập không?
9. Pair có thể giảm chờ review thế nào, và tại sao không tự thay được review độc lập bắt buộc?
10. Nguy cơ nào xuất hiện nếu người mới luôn làm navigator mà không bao giờ cầm bàn phím?
11. Vì sao pairing mọi giờ, mọi task có thể làm giảm hiệu quả?
12. Pairing hỗ trợ Developers trong Scrum thế nào mà không làm thay đổi accountability của Product Owner và Scrum Master?
13. Khi phần lớn công việc bị chặn bởi môi trường kiểm thử, tăng số cặp viết mã có giải quyết được không?
14. Các điều kiện bảo mật và khả năng tiếp cận cần quan tâm khi remote pairing?
15. Case study cho thấy kiến thức có thể lan truyền qua các cặp nào và được kiểm chứng ra sao?
16. Nêu một thử nghiệm ngắn cho đội để đánh giá pairing dựa trên chất lượng, thời gian phản hồi và khả năng tiếp nối.

**Ghi nhớ:** **Lập trình cặp** trong XP không chỉ là hai người ngồi cùng máy; đó là **phản hồi kỹ thuật liên tục và chia sẻ hiểu biết qua việc thực**. Khi driver và navigator cùng tham gia, đổi vai, phát triển theo kiểm thử, tích hợp sớm và luân chuyển có mục tiêu, đội có thể giảm phụ thuộc kiến thức, phát hiện hiểu sai nhanh hơn và tạo phần mềm đáng tin cậy hơn. Hãy sử dụng pairing theo rủi ro và bối cảnh, tôn trọng an toàn, chất lượng và nhịp làm việc bền vững. **Giá trị của pairing nằm ở năng lực và kết quả của toàn đội**, không phải tổng số giờ hai người cùng nhìn màn hình.
