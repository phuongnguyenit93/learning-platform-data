# Bổ sung thực hành XP để củng cố chất lượng cùng khả năng thay đổi

Một nhóm phát triển nền tảng học Java sử dụng Scrum. Sprint Planning diễn ra đúng lịch, Product Backlog được sắp thứ tự, Daily Scrum được tổ chức đều đặn và Sprint Review có sự tham gia của giảng viên. Tuy nhiên, vào cuối mỗi Sprint, Developers vẫn phải dành nhiều ngày ghép các nhánh mã, sửa lỗi kiểm thử hồi quy và giải quyết những thay đổi “nhỏ” nhưng gây ảnh hưởng dây chuyền. Sprint mới bắt đầu trong khi những lỗi từ Sprint trước chưa được xử lý. Product Owner muốn thử một cách tính kết quả bài kiểm tra mới nhưng nhóm ước lượng phải mất hàng tuần vì sợ làm hỏng cách tính cũ.

Có phải nhóm cần thêm một sự kiện Scrum hoặc lập kế hoạch kỹ hơn? Có thể không. Những trở ngại này nằm nhiều ở **cách xây dựng và duy trì phần mềm**. Nhóm có thể bổ sung những thực hành của **Extreme Programming (XP)** như kiểm thử trước hành vi, refactoring liên tục, tích hợp thường xuyên, lập trình cặp và thiết kế đơn giản. Mục tiêu không phải “đạt chứng nhận XP” hay tăng số ticket đóng, mà là **giảm rủi ro khi thay đổi và giữ phần mềm luôn ở trạng thái có thể phát triển, kiểm chứng và bàn giao**.

Bài **“Bổ sung thực hành XP để củng cố chất lượng cùng khả năng thay đổi”** thuộc chương **Lựa chọn cách tiếp cận** của module **AGILE_DEVELOPMENT**. Định hướng module là hiểu giá trị và nguyên tắc Agile qua phản hồi sớm, giao sản phẩm tăng dần và cải tiến liên tục; thực hành user story, backlog, Scrum, Kanban, XP và đo lường dòng công việc để chọn cách phối hợp phù hợp. Ở đây, chúng ta tập trung vào câu hỏi thực tiễn: **khi nào, vì sao và bằng cách nào nên bổ sung các thực hành XP vào phương pháp nhóm đang sử dụng**.

Các ví dụ với Java và JUnit 5 nhằm minh họa kỹ thuật; chúng không giả định mọi dự án dùng cùng framework, repository hoặc pipeline. Đoạn mã học tập chưa thay thế kiểm thử tích hợp, bảo mật, hiệu năng và chính sách phát hành của hệ thống thật.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao một nhóm có **Scrum events hoặc Kanban board rõ** vẫn có thể gặp vấn đề chất lượng và khả năng thay đổi.
2. Nhận diện các giá trị XP và ý nghĩa của **feedback, communication, simplicity, courage, respect**.
3. Chọn thực hành XP theo **vấn đề, bằng chứng, rủi ro và khả năng thay đổi** của nhóm, không áp dụng máy móc.
4. Thực hành chu kỳ **Test-Driven Development (TDD): Red → Green → Refactor** với quy tắc Java có thể kiểm tra.
5. Phân biệt kiểm thử đơn vị, tích hợp, hợp đồng, chấp nhận và bảo mật; hiểu giới hạn của coverage.
6. Thực hành **refactoring an toàn và simple design** để giảm chi phí thay đổi.
7. Thiết kế **Continuous Integration (CI), nhánh ngắn, kiểm thử nhanh và phản hồi build rõ**.
8. Chọn tình huống cần **pair programming, ensemble programming, review và collective code ownership**.
9. Liên kết XP với **Definition of Done, user stories, Sprint Goal, Kanban WIP và small releases**.
10. Xây kế hoạch áp dụng dần cho **code legacy, nhóm mới và hệ thống có ràng buộc nghiêm ngặt**.
11. Đo cải tiến bằng **flow, escaped defects, độ tin cậy CI, thời gian đến phản hồi và outcome**.
12. Tự thực hành qua bài tập, hướng giải và checklist.

## 1. Điều phối Agile rõ ràng chưa bảo đảm code dễ thay đổi

Scrum cho nhóm khuôn khổ kiểm tra và thích ứng quanh Product Goal, Sprint Goal, Increment và events. Kanban giúp trực quan hóa luồng, kiểm soát WIP và theo dõi flow metrics. Nhưng nếu code khó kiểm thử, ranh giới module mơ hồ, mỗi thay đổi làm hỏng nhiều tính năng, thì **nhìn thấy vấn đề không đồng nghĩa tự giải quyết được vấn đề kỹ thuật**.

Ví dụ một nhóm có thể:

- Dùng Sprint hai tuần nhưng chỉ tích hợp code vào ngày cuối.
- Chọn PBI nhỏ nhưng mọi PBI đều cần sửa chung một class 3.000 dòng.
- Báo unit tests thành công nhưng không kiểm hợp đồng giữa API chấm điểm và giao diện.
- Có DoD nhưng thiếu tự động hóa khiến kiểm chứng mỗi lần tốn nhiều ngày.
- Nói “cần chất lượng hơn” trong Retrospective nhưng không thử kỹ thuật cụ thể.
- Bàn giao Increment rồi ba ngày sau production lỗi, nhóm phải quay lại sửa.

Những dấu hiệu đó gợi ý cần **kỹ thuật phản hồi sớm, thay đổi an toàn và phối hợp trong code**, không chỉ lập kế hoạch kỹ hơn.

### 1.1. Chất lượng liên quan khả năng thay đổi

Chất lượng không chỉ là ít lỗi ở thời điểm hiện tại. Nó còn là khả năng **hiểu, kiểm tra, sửa và mở rộng hành vi mà không gây hồi quy ngoài dự tính**.

Khi cấu trúc rõ, kiểm thử đáng tin và tích hợp liên tục:

1. Developers thử thay đổi nhỏ nhanh hơn.
2. Tác động sai lộ trong phút/giờ thay vì cuối Sprint.
3. Chi phí sửa, khôi phục và đổi hướng có thể thấp hơn.
4. PO dễ thay thứ tự Product Backlog theo phản hồi hơn.
5. Nhóm có cơ hội giao Increment nhỏ, học sớm và cải tiến liên tục.

Đó là **cơ chế hỗ trợ thích ứng**, không phải bảo đảm tự động rằng thêm một công cụ tạo ra giá trị.

## 2. XP là gì và đứng ở đâu khi chọn cách tiếp cận?

**Extreme Programming (XP)** là một phương pháp Agile nhấn mạnh chất lượng kỹ thuật, phản hồi nhanh, cộng tác và khả năng đáp ứng yêu cầu thay đổi. XP có các giá trị và nhóm thực hành phát triển phần mềm liên kết với nhau. Nhiều thực hành của XP có thể áp dụng ngay cả khi nhóm không tự nhận làm XP.

| Giá trị XP | Ý nghĩa | Hành vi minh họa |
| --- | --- | --- |
| **Communication — giao tiếp** | Chia sẻ hiểu biết, phát hiện giả định khác nhau. | Pairing và làm rõ acceptance criteria với người hiểu nghiệp vụ. |
| **Simplicity — đơn giản** | Xây giải pháp đủ tốt cho điều đã biết, có thể tiến hóa. | Không tạo plugin framework phức tạp khi mới có một quy tắc. |
| **Feedback — phản hồi** | Nhận tín hiệu sớm từ code, tích hợp và người dùng. | TDD, CI, demo Increment, quan sát học viên. |
| **Courage — can đảm** | Dám sửa thiết kế, nêu rủi ro và thay cách làm. | Refactor vùng khó hiểu có safety net. |
| **Respect — tôn trọng** | Tôn trọng đồng đội, người dùng, chất lượng và nhịp làm bền vững. | Review không đổ lỗi, giữ DoD, không ép làm thêm giờ vô hạn. |

Các nguồn/phiên bản XP có thể nhóm và gọi tên thực hành khác nhau. Không nên coi **một số lượng thực hành cố định** là điều kiện bắt buộc cho mọi nhóm.

### 2.1. Các thực hành XP thường hữu ích

- **Test-Driven Development (TDD)** và kiểm thử tự động.
- **Refactoring** liên tục.
- **Continuous Integration (CI)** và tích hợp thường xuyên.
- **Simple design**, thiết kế tiến hóa.
- **Pair programming** và chia sẻ tri thức ngay trong công việc.
- **Collective code ownership** đi cùng tiêu chuẩn chất lượng chung.
- **Coding standards** và code dễ đọc.
- **Small releases** và phản hồi người dùng.
- **Customer collaboration/whole team** để làm rõ quy tắc.
- **Sustainable pace** để giữ năng lực lâu dài.
- **Acceptance tests** theo ví dụ nghiệp vụ.
- **Spikes** giới hạn thời gian để làm rõ bất định kỹ thuật.

Không phải tất cả chỉ thuộc XP, và **không cần đổi framework quản trị** mới được bổ sung chúng.

## 3. XP bổ trợ Scrum, Kanban thế nào?

| Khía cạnh | Scrum | Kanban | XP |
| --- | --- | --- | --- |
| **Trọng tâm** | Kiểm tra và thích ứng theo Sprint, tạo Increment. | Quản lý flow bằng WIP và chính sách rõ. | Cách xây code chất lượng và đổi an toàn. |
| **Đơn vị phối hợp** | Product Backlog, Sprint Backlog, Increment. | Work items qua Definition of Workflow. | Thay đổi nhỏ, tests, CI, pairing, feedback. |
| **Phản hồi** | Events/Increment; có thể release trước Sprint Review. | Liên tục qua dòng công việc. | Liên tục ở tầng code, tích hợp, người dùng. |
| **Số đo** | Mục tiêu, Increment, chất lượng; velocity tùy chọn. | Throughput, cycle time, WIP, work item age. | CI health, hồi quy, change safety, cộng với flow/outcome. |
| **Điểm không quy định** | Không bắt buộc TDD/pairing/CI. | Không quy định cách test/refactor. | Không thay trách nhiệm mục tiêu/ưu tiên sản phẩm của nhóm. |

### 3.1. Trong Scrum

- Giữ **Product Goal, Sprint Goal, Definition of Done** và các events theo Scrum Guide.
- PO trao đổi giá trị và thứ tự Product Backlog; Developers quyết định cách tạo Increment.
- Dùng TDD với logic phù hợp, pairing khi rủi ro cao, CI khi tích hợp, refactoring trong quá trình phát triển.
- Chỉ công nhận Done khi đáp ứng DoD; Sprint Review không thay kiểm thử chất lượng.
- Retrospective đánh giá xem thực hành kỹ thuật có thực sự giảm trở ngại không.

### 3.2. Trong Kanban

- Xác định Started, Done, WIP và blocked policies.
- Chia work item đủ nhỏ để tích hợp và kiểm chứng thường xuyên.
- Dùng TDD/CI/refactoring để giảm thời gian tới Done.
- Khi review là hàng chờ, thử pairing hoặc review liên tục thay vì mở thêm ticket.
- Theo dõi flow và chất lượng, không chỉ số mục Done.

### 3.3. Tránh “cộng mọi nghi thức”

Thêm họp XP, một checklist Scrum mới và nhiều cột Kanban không hữu ích nếu không đổi cách làm. Hãy **chọn thực hành giảm trở ngại quan sát được**, tránh đo lặp và giữ accountabilities rõ.

## 4. Bắt đầu từ triệu chứng thay vì danh sách thực hành yêu thích

| Triệu chứng | Giả thuyết cần kiểm chứng | Thực hành ứng viên | Tín hiệu theo dõi |
| --- | --- | --- | --- |
| Lỗi quy tắc chấm điểm tái diễn. | Thiếu ví dụ và kiểm thử hồi quy đáng tin. | TDD + acceptance tests + pairing. | Escaped defects, lỗi tái phát. |
| Merge conflict cuối Sprint. | Nhánh lâu ngày, tích hợp thưa. | CI, thay đổi nhỏ, nhánh ngắn. | Thời gian tích hợp, conflicts. |
| Sửa A làm hỏng B. | Coupling cao, safety net yếu. | Characterization tests + refactoring. | Lỗi hồi quy, phạm vi ảnh hưởng. |
| Review chờ nhiều ngày. | WIP cao, review tách khỏi dòng công việc. | Pairing, review thường xuyên, WIP policy. | Blocked time, review wait. |
| Chỉ một người sửa được module. | Ownership cứng, thiếu chia sẻ. | Pair rotation, collective ownership có safeguards. | Bus factor, onboarding time. |
| Code xong nhưng không dùng được. | Chia ngang, tích hợp cuối. | Vertical slicing, acceptance tests, CI. | Done theo DoD, time-to-Increment. |
| Làm thêm giờ nhưng rework tăng. | WIP và mệt mỏi cao. | Sustainable pace, simple design, WIP control. | Cycle time, lỗi, phản hồi nhóm. |
| Stakeholder bảo “đó không phải điều tôi muốn”. | Yêu cầu thiếu ví dụ và phản hồi muộn. | Example mapping, customer collaboration, small releases. | Rework do hiểu sai, time-to-feedback. |

### 4.1. Chọn bằng bằng chứng

CI không giải quyết việc **không ai biết quy tắc đúng**. TDD không tự giải quyết môi trường đối tác bên ngoài thiếu ổn định. Pairing không hữu ích nếu hai người chỉ mở một cuộc gọi rồi làm hai việc riêng.

Cần hỏi: **“Thực hành nào có cơ chế rõ để giảm vấn đề này, và chúng ta sẽ kiểm tra kết quả ra sao?”**

### 4.2. Áp dụng từng bước

Đổi toàn bộ công cụ, branch strategy, coding standard, pipeline và DoD trong một tuần khiến rất khó biết điều nào giúp và điều nào tạo tắc. Tốt hơn là **một hoặc hai thực hành tương hỗ**, có baseline và checkpoint.

## 5. Các tầng phản hồi kỹ thuật và sản phẩm

~~~mermaid
flowchart TD
    A["Ý định người dùng + acceptance examples"] --> B["Lát công việc nhỏ"]
    B --> C["TDD: Red → Green → Refactor"]
    C --> D["Pair / Review / Standards"]
    D --> E["CI: unit, integration, contract, security checks"]
    E --> F{"Đạt Definition of Done?"}
    F -->|"Chưa"| C
    F -->|"Rồi"| G["Increment có thể sử dụng"]
    G --> H["Release phù hợp + quan sát"]
    H --> I["Feedback giá trị, chất lượng, vận hành"]
    I --> J["Điều chỉnh Backlog / luồng / thiết kế"]
    J --> B
~~~

| Tầng | Cung cấp bằng chứng về | Không thể tự chứng minh |
| --- | --- | --- |
| **Unit tests** | Quy tắc nhỏ và hồi quy tại vùng code. | API thực, quyền end-to-end, nhu cầu người dùng. |
| **Pair/review** | Giả định và thiết kế chưa rõ. | Không thay tất cả kiểm thử thực thi. |
| **CI** | Code tích hợp qua bộ kiểm tra đã thiết kế. | Build xanh không nghĩa không còn lỗi. |
| **Acceptance/integration** | Hành vi qua nhiều lớp và hợp đồng. | Không tự chứng minh kết quả có giá trị. |
| **Release/telemetry** | Vận hành và hành vi người dùng thật. | Không mặc định chứng minh nhân quả. |
| **Review với người dùng** | Cần ưu tiên/đổi hướng gì. | Không thay DoD hoặc bảo mật. |

**Feedback ngắn khi vẫn đáng tin** giúp nhóm sửa ngay một lát nhỏ thay vì viết lại khối lớn vào cuối Sprint.

## 6. Test-Driven Development: Red → Green → Refactor

**TDD** là chu kỳ phát triển trong đó Developers diễn đạt một hành vi bằng test nhỏ, thấy test thất bại vì hành vi chưa có (**Red**), viết mã tối thiểu để test đạt (**Green**), rồi cải thiện cấu trúc mà vẫn giữ hành vi (**Refactor**).

~~~mermaid
flowchart LR
    R["RED: test thất bại đúng lý do"] --> G["GREEN: mã nhỏ nhất làm test đạt"]
    G --> F["REFACTOR: cải thiện cấu trúc, giữ tests xanh"]
    F --> R
~~~

### 6.1. Red cần thất bại đúng lý do

Test không compile do thiếu import, phụ thuộc mạng lỗi hoặc fixture sai không phải bằng chứng logic sản phẩm thiếu. Developers nên sửa điều kiện chạy rồi xác nhận **test thể hiện yêu cầu chưa được đáp ứng**.

### 6.2. Green không phải lách test

Viết mã vừa đủ để đáp ứng yêu cầu đang kiểm, **không hard-code kết quả chỉ để qua một ví dụ**. Refactor giữ thiết kế rõ sau những lần thay đổi nhỏ.

### 6.3. Refactor không đổi hành vi

Nếu thay quy tắc điểm hoặc hành vi trả lỗi API, đó là **thay đổi nghiệp vụ**, phải làm rõ acceptance criteria/test. Không nên gọi nó là refactoring để tránh trao đổi với PO.

### 6.4. TDD không chọn hộ sản phẩm đúng

Test có thể xanh mà rule sai với người học. Cần **hiểu nghiệp vụ, kiểm thử tích hợp, quyền, dữ liệu, hiệu năng và phản hồi người dùng**, không đồng nhất TDD với chất lượng hoàn chỉnh.

## 7. Ví dụ Java: TDD quy tắc chấm bài trắc nghiệm

Một PBI:

> Là học viên, tôi muốn được chấm bài trắc nghiệm theo số câu đúng, để hiểu kết quả và học tiếp.

Để thực hành, nhóm tách **logic thuần** khỏi API và database:

- Mỗi câu đúng được 1 điểm.
- Câu sai hoặc bỏ trống được 0.
- Bài không có câu hỏi là dữ liệu không hợp lệ.
- Mỗi ID câu hỏi xuất hiện tối đa một lần trong Map.
- Những ràng buộc về quyền, lần nộp, idempotency và lưu kết quả sẽ kiểm ở tầng phù hợp, không giả định bộ code dưới xử lý chúng.

### 7.1. RED — viết test trước

Ví dụ dùng JUnit 5, với dự án đã cấu hình dependency phù hợp:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;
import java.util.Map;

class QuizScorerTest {
    @Test
    void countsOnlyCorrectAnswers() {
        var correct = Map.of(
            "Q1", "A",
            "Q2", "C",
            "Q3", "B"
        );
        var submitted = Map.of(
            "Q1", "A",
            "Q2", "B",
            "Q3", "B"
        );

        var scorer = new QuizScorer();
        assertEquals(2, scorer.score(correct, submitted));
    }
}
~~~

Đầu tiên test chưa đạt vì logic chấm chưa có; tạo vỏ lớp/phương thức rồi kiểm tra test thất bại vì **chưa xử lý yêu cầu**. Đây là ví dụ của vòng Red, không phải một yêu cầu làm toàn bộ dự án luôn đỏ.

### 7.2. GREEN — cài đặt logic tối thiểu

~~~java
import java.util.Map;
import java.util.Objects;

public final class QuizScorer {
    public int score(
        Map<String, String> correct,
        Map<String, String> submitted
    ) {
        Objects.requireNonNull(correct, "correct");
        Objects.requireNonNull(submitted, "submitted");

        if (correct.isEmpty()) {
            throw new IllegalArgumentException(
                "Quiz must have at least one question"
            );
        }

        int points = 0;
        for (var question : correct.entrySet()) {
            String id = question.getKey();
            String expected = question.getValue();

            if (expected != null
                    && submitted.containsKey(id)
                    && expected.equals(submitted.get(id))) {
                points++;
            }
        }
        return points;
    }
}
~~~

Đoạn mã chỉ tính điểm theo dữ liệu đầu vào đã tin cậy. **Không cho client tự cung cấp bộ đáp án đúng trong API thật**. Map bảo đảm mỗi key là duy nhất trong cấu trúc này nhưng **không chứng minh chống gửi request trùng hoặc lưu kết quả hai lần**.

### 7.3. Thêm test biên theo vòng Red–Green–Refactor

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import java.util.Map;

class QuizScorerEdgeCasesTest {
    private final QuizScorer scorer = new QuizScorer();

    @Test
    void unansweredQuestionScoresZero() {
        assertEquals(1, scorer.score(
            Map.of("Q1", "A", "Q2", "B"),
            Map.of("Q1", "A")
        ));
    }

    @Test
    void unknownQuestionDoesNotIncreaseScore() {
        assertEquals(0, scorer.score(
            Map.of("Q1", "A"),
            Map.of("Q999", "A")
        ));
    }

    @Test
    void emptyQuizIsInvalid() {
        assertThrows(IllegalArgumentException.class,
            () -> scorer.score(Map.of(), Map.of()));
    }

    @Test
    void emptySubmissionHasZeroCorrectAnswers() {
        assertEquals(0, scorer.score(
            Map.of("Q1", "A"),
            Map.of()
        ));
    }
}
~~~

Trong TDD thực tế, nhóm **thêm từng hành vi theo những vòng nhỏ**, không nhất thiết viết tất cả tests cùng lúc như cách trình bày cô đọng ở đây.

### 7.4. REFACTOR — làm rõ cấu trúc

Khi tests xanh, có thể:

- Đặt tên rõ cho class, method và đối tượng nghiệp vụ.
- Tách chính sách điểm nếu sản phẩm thật xuất hiện nhiều biến thể.
- Loại lặp logic, làm rõ null/invalid input.
- Giữ giao diện công khai nhỏ và ổn định.
- Chạy lại toàn bộ tests phù hợp sau mỗi thay đổi.

Không cần xây mười interface ngay từ đầu để “chuẩn bị cho tương lai” chưa có bằng chứng.

### 7.5. Những rủi ro ngoài ví dụ

- Bộ đáp án phải được lấy từ nguồn tin cậy.
- Học viên phải có quyền làm và đọc kết quả.
- Mỗi lần nộp phải có quy tắc và identity rõ.
- Retry/duplicate cần kiểm soát tại tầng lưu/API.
- Lỗi giao dịch không được báo thành công giả.
- Dữ liệu cá nhân và log phải được bảo vệ.
- Câu hỏi nhiều đáp án, điểm một phần hoặc trừ điểm cần rule riêng.

Do đó **unit TDD chỉ bảo vệ một phần hành vi**, không tự đủ để đánh dấu cả Increment Done.

## 8. Acceptance tests kết nối code với kết quả người dùng

Product Owner và giảng viên không chỉ cần lớp QuizScorer đúng, mà cần **người học được nộp và xem kết quả đúng trong luồng thật**.

~~~gherkin
Feature: Nộp bài trắc nghiệm Java đáng tin

Scenario: Học viên nộp bài hợp lệ
  Given học viên có quyền làm bài "Java căn bản"
  And bài có ba câu với đáp án đúng đã được xác nhận
  When học viên gửi câu trả lời có hai câu đúng
  Then hệ thống lưu một kết quả hợp lệ
  And hiển thị hai trên ba câu đúng theo quy tắc

Scenario: Gửi lại request đã xử lý
  Given request "attempt-42" đã được xử lý thành công
  When hệ thống nhận lại cùng request đó
  Then không tạo kết quả trùng trái quy tắc nghiệp vụ
  And trạng thái phản hồi phù hợp với lần xử lý ban đầu

Scenario: Không có quyền
  Given tài khoản không có quyền đọc kết quả của người khác
  When tài khoản đó yêu cầu đọc kết quả theo ID người khác
  Then hệ thống từ chối theo chính sách
  And không tiết lộ điểm hoặc đáp án riêng tư

Scenario: Không thể xác nhận ghi dữ liệu
  Given học viên được phép nộp bài
  And dịch vụ ghi kết quả đang không sẵn sàng
  When học viên gửi bài
  Then giao diện không xác nhận sai rằng đã lưu thành công
  And đưa trạng thái và hướng xử lý phù hợp
~~~

**Acceptance criteria** mô tả hành vi riêng của PBI; **Definition of Done** là tiêu chuẩn chất lượng chung cho Increment (tích hợp, kiểm thử, quyền, vận hành theo phạm vi). Test đơn vị xanh nhưng API lộ điểm người khác thì **không đạt DoD**.

### 8.1. Example mapping trước khi code

Người hiểu nghiệp vụ và Developers có thể xác định:

- **Rule:** mỗi câu đúng được một điểm.
- **Example:** hai trong ba câu đúng cho điểm 2.
- **Question:** bỏ trắng có bị trừ điểm? được nộp lại không?
- **Risk:** retry tạo hai attempt? lấy đáp án đúng từ client?
- **Decision:** người sở hữu quy tắc làm rõ và ghi lại acceptance criteria.

TDD hữu ích nhất khi **kiểm đúng rule cần có**, không khóa cứng một giả định chưa được xác nhận.

## 9. TDD, test-first và test-after: áp dụng linh hoạt

| Cách làm | Lợi ích | Giới hạn cần kiểm soát |
| --- | --- | --- |
| **TDD Red–Green–Refactor** | Khuyến khích thiết kế kiểm thử được, feedback nhỏ và hồi quy sớm. | Chỉ test điều dễ vẫn bỏ contract/rights. |
| **Acceptance test-first** | Làm rõ hành vi đầu cuối và giao tiếp nghiệp vụ. | Dùng E2E cho mọi trường hợp nhỏ có thể chậm và giòn. |
| **Code rồi thêm tests trong cùng thay đổi** | Có thể phù hợp khi di chuyển dần từ legacy hoặc sau spike. | Dễ bỏ biên/rủi ro khi áp lực tăng. |
| **Characterization tests** | Ghi lại hành vi hiện hữu trước refactor legacy. | Có thể ghi cả bug; cần tách hành vi hiện tại với mong muốn. |
| **Exploratory testing** | Tìm lỗi ngoài giả định đã được mã hóa. | Khó làm safety net nếu không tự động hóa phần tái diễn. |

### Khi TDD phù hợp

Rất hữu ích cho rule tính điểm, xử lý trạng thái, chuyển đổi dữ liệu, policy và thành phần có contract rõ.

### Khi không nên ép như nghi thức

- Spike ngắn để hiểu công nghệ chưa biết.
- Prototype UX cần người dùng đánh giá trước khi chốt contract.
- Hệ thống legacy chưa có seam, cần tạo characterization tests trước.
- Tương tác phần cứng/phụ thuộc khó thiết lập, cần thiết kế test doubles hoặc môi trường phù hợp.

Điều này **không miễn yêu cầu DoD** khi đưa giải pháp vào sản phẩm thật.

## 10. Refactoring: sửa cấu trúc mà giữ nguyên hành vi

**Refactoring** là biến đổi cấu trúc nội bộ có chủ đích để code dễ hiểu, ít trùng lặp và ít coupling hơn, **không đổi hành vi quan sát được**.

Một QuizService lớn có thể vừa kiểm quyền, vừa chấm, lưu điểm, tạo chứng nhận, gửi email và log. Mỗi yêu cầu mới phải đụng cả hệ thống.

### Các bước refactor nhỏ

1. Xác định contract và đường lỗi phải giữ.
2. Viết/củng cố tests cho hành vi hiện tại.
3. Chọn **một thay đổi cấu trúc nhỏ**, ví dụ tách QuizScorer.
4. Chạy tests, CI và review.
5. Xem cấu trúc có thực sự rõ hơn, ít phụ thuộc hơn không.
6. Tiếp tục nếu giảm chi phí cho thay đổi kế tiếp.

### Phân biệt refactor với đổi behavior

Nếu thay công thức chấm điểm, đó là **thay đổi chức năng**. Nếu chỉ chuyển logic tính điểm sang lớp thuần nhưng mọi đầu vào/đầu ra giữ nguyên, đó là refactor.

Không nên đưa đổi schema, đổi rule, đổi quyền và di chuyển nhiều package vào một PR khổng lồ nếu có thể tách thành bước kiểm chứng được.

### Test không phải “lá chắn tuyệt đối”

Nếu thiếu negative tests quyền, retry hay concurrency, bộ unit xanh có thể che sai sót lớn. **Safety net phải phù hợp rủi ro**, không dựa duy nhất vào số lượng test.

## 11. Simple design và kiến trúc tiến hóa

**Simple design** nghĩa là xây cấu trúc **vừa đủ cho nhu cầu đã biết, dễ đọc, dễ kiểm thử và có thể sửa khi học được điều mới**.

Hai cực đoan:

- **Over-engineering:** dựng plugin framework, event bus và 12 lớp abstraction cho một rule điểm.
- **Under-engineering:** controller xử lý quyền, chấm điểm, giao dịch, email và chứng nhận trong một method, không có test.

Một cấu trúc minh họa:

~~~text
QuizSubmissionController
   -> AuthorizationPolicy
   -> QuizSubmissionService
       -> QuizScorer
       -> AttemptRepository
       -> OutcomeEventPublisher (chỉ khi thật sự cần)

Điều kiện:
   - Chính sách quyền tại ranh giới rõ
   - Scorer thuần, dễ TDD
   - Lưu kết quả nhất quán, có idempotency phù hợp
   - Contract/integration tests với các phụ thuộc
   - Thiết kế có thể đổi theo bằng chứng mới
~~~

Đây không phải sơ đồ kiến trúc bắt buộc. Nên trì hoãn các abstraction chưa cần thiết nhưng **không trì hoãn quyết định khó đảo ngược về dữ liệu, quyền hoặc tính tương thích**.

### Câu hỏi để kiểm tra thiết kế

- Thêm rule điểm mới có phải sửa nhiều class không liên quan?
- Unit tests cho rule chạy nhanh và dễ hiểu?
- Thay API có giữ tương thích với consumer?
- Người mới có xác định được vị trí sửa và lý do thiết kế?
- Có thể refactor vùng code mà không sợ làm hỏng đường quan trọng?

## 12. Continuous Integration: phát hiện lỗi ghép mã khi còn nhỏ

**CI** là thực hành tích hợp thay đổi vào codebase chung thường xuyên, dùng build và tests để phát hiện vấn đề sớm.

~~~mermaid
flowchart LR
    A["Thay đổi nhỏ + test cục bộ"] --> B["Commit / PR ngắn"]
    B --> C["Build + static checks"]
    C --> D["Unit tests"]
    D --> E["Integration / contract / security checks"]
    E --> F{"CI đạt và review đủ?"}
    F -->|"Không"| G["Sửa nhanh, không tích hợp mã lỗi"]
    G --> B
    F -->|"Có"| H["Tích hợp mainline"]
    H --> I["Kiểm chứng Increment / DoD"]
~~~

### Để CI thực sự có tác dụng

- Tích hợp **thường xuyên**, không giữ nhánh tách nhiều tuần.
- Có người phản ứng với build đỏ, không bỏ mặc.
- Checks phản ánh rủi ro thật, không chỉ formatter.
- Test đủ nhanh và ổn định để Developers tin.
- Lỗi có log rõ nhưng không tiết lộ secret/dữ liệu riêng.
- Review và pipeline không thành hàng chờ dài.
- Không bỏ checks bắt buộc để merge cho kịp báo cáo.

### CI, Continuous Delivery và Continuous Deployment khác nhau

- **CI:** thường xuyên tích hợp và kiểm tra thay đổi.
- **Continuous Delivery:** giữ phần mềm ở trạng thái sẵn sàng phát hành đáng tin, có thể cần quyết định release.
- **Continuous Deployment:** tự động triển khai thay đổi đạt điều kiện theo chính sách.

Một pipeline xanh không tự chứng minh người dùng đã nhận giá trị. Deployment không tự bằng release; release có thể còn phụ thuộc feature flag, cohort, vận hành và thẩm quyền.

### Nhánh ngắn và trunk-based

Nhánh ngắn và thay đổi nhỏ thường giảm merge conflict. **Trunk-based development** có thể hỗ trợ CI nhưng không phải tiêu chí duy nhất để gọi là XP. Nếu tổ chức yêu cầu PR review, có thể dùng nhánh ngắn và CI trước merge; không nên dùng “CI” làm lý do bỏ review bắt buộc.

## 13. Tầng kiểm thử: feedback nhanh phải đủ đáng tin

| Tầng | Cần kiểm tra | Rủi ro nếu dùng sai |
| --- | --- | --- |
| **Unit/component** | Rule điểm, state transitions, pure policies. | Mock quá mức, test chỉ kiểm method được gọi. |
| **Integration** | API–database, transaction, kết nối phụ thuộc thật phù hợp. | Dùng full stack cho mọi rule khiến suite chậm. |
| **Contract** | Producer/consumer thống nhất schema, status và semantics. | Contract sai nhu cầu vẫn có thể xanh. |
| **Acceptance** | Hành vi end-to-end theo ví dụ người dùng. | Chỉ happy path bỏ lỗi quyền/mạng. |
| **Security/privacy** | Quyền, secret, dữ liệu và ranh giới tin cậy. | Scanner không thay negative tests/review. |
| **Performance/resilience** | Tải, timeout, retry, recovery. | Một test không chứng minh toàn bộ production. |
| **Exploratory/usability** | Điều ngoài giả định đã mã hóa. | Thiếu ghi nhận khiến lỗi lặp. |

### Test pyramid là gợi ý

Thường nên có nhiều tests nhanh ở tầng thấp và ít tests E2E tập trung vào đường rủi ro cao. Nhưng không có tỷ lệ cố định cho mọi hệ thống. Mục tiêu là **phát hiện đúng loại lỗi, nhanh và đáng tin**.

### Coverage không phải điểm chất lượng duy nhất

Một suite 100% line coverage có thể không kiểm retry, phân quyền hoặc lỗi dữ liệu. Ngược lại, coverage thấp ở logic trọng yếu là tín hiệu cần xem. Kết hợp **quality of assertions, negative cases, escaped defects và mức độ tin vào CI**, không dùng coverage làm KPI cá nhân.

### Test flaky làm giảm niềm tin

Nếu tests lúc xanh lúc đỏ do clock, shared state, race condition hay môi trường mạng, cần phân loại và xử lý. Không nên bỏ test quan trọng rồi không có kiểm soát thay thế chỉ để pipeline luôn xanh.

## 14. Pair programming: khám phá giả định khi đang code

**Pair programming** là hai Developers cùng giải quyết **một vấn đề** trong thời gian thực. Có thể luân phiên:

- **Driver:** thao tác code/test.
- **Navigator:** xem rủi ro, thiết kế, trường hợp biên và hướng tiếp theo.

Cần đổi vai, không mặc định người có thâm niên làm mọi thao tác còn người mới chỉ nhìn.

### Khi nào pairing có thể có giá trị cao?

- Quy tắc chấm điểm nhạy cảm hoặc nhiều trường hợp biên.
- Đường phân quyền hoặc xử lý dữ liệu quan trọng.
- Refactor legacy có rủi ro.
- Review đang trở thành hàng chờ.
- Module chỉ một người biết.
- Test fail khó chẩn đoán.
- Onboarding kiến thức bằng công việc thật.

### Khi nào cần cân nhắc cách khác?

- Việc nhỏ, rõ, ít phụ thuộc, không có lợi ích chia sẻ lớn.
- Hai người cần nghiên cứu độc lập trước khi hội ý.
- Thiếu điều kiện kết nối hoặc thời gian trùng nhau phù hợp.
- Pairing bị ép cả ngày gây mệt và giảm tập trung.

**Pairing không phải mở cuộc gọi rồi làm hai việc khác nhau.**

### Ví dụ

A viết test “gửi lại request đã xử lý không tạo kết quả trùng”. B hỏi: “Thế nào là cùng request: requestId, attemptId hay hash payload?”. Nhóm phát hiện **hợp đồng nghiệp vụ còn thiếu**, làm rõ với người có thẩm quyền rồi mới code. Giá trị lớn nhất đến từ phát hiện sai giả định **trước khi nó thành kiến trúc production**.

## 15. Ensemble programming, review và collective ownership

**Ensemble/mob programming** là một nhóm nhỏ cùng giải quyết một vấn đề với quy tắc tương tác rõ, thường luân phiên người thao tác. Có thể hữu ích cho kiến trúc hoặc rủi ro liên nhóm, nhưng cần cân nhắc chi phí cơ hội; không phải mọi PBI đều cần cả nhóm cùng ngồi.

**Code review** bổ sung cho pairing. Ở hệ thống có chính sách bắt buộc, pairing không tự thay phê duyệt độc lập. Review nên tập trung vào:

- Hành vi/acceptance criteria.
- Quyền, dữ liệu, concurrency và đường lỗi.
- Test, readability, simplicity.
- Tương thích hợp đồng và rollout.
- Cần quyết định/ADR nào chưa rõ.

**Collective code ownership** giảm phụ thuộc vào một người, để Developers có thể cải thiện nhiều vùng code theo tiêu chuẩn chung. Nó cần CI, tests, coding standards, review và chia sẻ tri thức. **Không có nghĩa ai cũng được truy cập mọi dữ liệu hoặc thay chính sách bảo mật ngoài quyền.**

## 16. Coding standards, whole team và sự hiểu biết chung

### Coding standards

Tiêu chuẩn chung giảm chi phí đọc/review:

- Tên class, method và package nhất quán.
- Định dạng tự động khi phù hợp.
- Cách xử lý lỗi, log và dữ liệu nhạy cảm.
- Viết test, fixture và test data dễ hiểu.
- Policy dependency/secret và contract versioning.
- Quy tắc review khi đổi quyền, dữ liệu hoặc API.

Không nên mở cuộc họp dài về dấu cách nếu formatter xử lý được. **Tiêu chuẩn là công cụ giảm ma sát**, không phải công cụ phân loại năng lực cá nhân.

### Whole team và cộng tác nghiệp vụ

Không có nghĩa PO phải ngồi cùng Developers tám giờ mỗi ngày. Điều cần có là **đường hỏi–đáp và phản hồi đủ nhanh**:

- Người hiểu rule có thể giúp làm rõ.
- Acceptance criteria có ví dụ cụ thể.
- Giả định còn mở được ghi rõ và có owner.
- User stories được chia lát có giá trị.
- Stakeholder thấy Increment sớm và phản hồi.
- Quyết định về scope không tự phát sinh chỉ vì Developers thấy dễ code.

Nhóm phân tán có thể dùng example mapping bất đồng bộ, cuộc gọi ngắn và decision log để duy trì bối cảnh.

## 17. Sustainable pace: khả năng thay đổi cần nhịp làm bền vững

Một nhóm không thể mãi giảm lỗi bằng cách làm thêm giờ liên tục. Mệt mỏi ảnh hưởng review, kiểm thử và trao đổi, có thể làm rework tăng.

Tín hiệu cần xem:

- Sprint nào cũng phải overtime để “đạt velocity”.
- Lỗi sau release tăng.
- WIP lớn, ít PBI đạt DoD.
- Review và xử lý sự cố mặc định ngoài giờ.
- Developers né refactor hoặc test vì chỉ được đánh giá qua số ticket.
- Một người giải quyết mọi vấn đề khó, không có cơ chế chia sẻ.

Cải thiện:

1. Giữ DoD và các guardrails.
2. Giới hạn WIP, hoàn tất việc trước khi mở thêm.
3. Chia lát nhỏ.
4. Giảm rework với examples, TDD và CI.
5. Pair/rotation để giảm bus factor.
6. Trao đổi PO về phạm vi khi capacity thay đổi.
7. Quản lý sự cố theo ca trực và thẩm quyền.
8. Thu phản hồi của nhóm để cải tiến cách làm.

Sustainable pace không có nghĩa từ chối mọi tình huống khẩn, mà là **không biến khẩn cấp thành mô hình vận hành mặc định**.

## 18. Code legacy: áp dụng XP bằng những lát thay đổi có kiểm soát

Một nhóm duy trì nền tảng học nhiều năm có thể gặp:

- Lớp chấm điểm quá lớn, vừa gọi database vừa tính điểm.
- Phụ thuộc tĩnh, đồng hồ hệ thống và HTTP client nằm trong cùng method.
- Unit tests ít, integration tests chạy lâu và không ổn định.
- Người viết code ban đầu đã chuyển nhóm.
- Dữ liệu cũ có những trường hợp “bất thường” mà không ai dám sửa.
- Một lần đổi tính năng phải chạy kiểm thử thủ công nhiều ngày.

Yêu cầu “từ ngày mai toàn bộ mã phải TDD 100%” có thể không thực tế. Một lựa chọn tốt hơn là **tạo điểm kiểm soát quanh phần sắp thay đổi**, rồi cải thiện cấu trúc từng bước.

### 18.1. Chiến lược từng bước

1. **Khoanh vùng thay đổi thật:** PBI nào cần chạm vào code legacy? Rủi ro lớn nằm ở đâu?
2. **Chốt hành vi hiện tại:** những ví dụ, test và dữ liệu nào mô tả điều hệ thống đang làm?
3. **Viết characterization tests:** ghi lại hành vi quan sát được để phát hiện thay đổi ngoài dự kiến.
4. **Làm rõ yêu cầu đúng:** nếu hành vi cũ là bug, phải phân biệt việc giữ nguyên tạm thời với thay đổi nghiệp vụ có chủ đích.
5. **Tạo seam:** tách một ranh giới cho thời gian, database, HTTP hoặc rule.
6. **Refactor rất nhỏ:** chạy tests và CI sau mỗi bước.
7. **Thêm TDD cho hành vi mới:** yêu cầu mới đi qua Red–Green–Refactor.
8. **Bổ sung integration/contract tests:** kiểm chứng seam vẫn hoạt động trong hệ thống thật.
9. **Dọn phần cũ khi không còn phụ thuộc:** tránh kéo dài hai nguồn logic.
10. **Ghi quyết định và rủi ro còn lại:** không tuyên bố “đã hiện đại hóa” chỉ vì di chuyển file.

### 18.2. Characterization tests không mặc nhiên xác nhận nghiệp vụ đúng

Giả sử hệ thống cũ có bug: câu bỏ trống cũng được một điểm trong một điều kiện hiếm. Characterization test có thể ghi lại điều đó để **tránh thay đổi ngầm**. Khi PO/người hiểu nghiệp vụ xác nhận phải sửa, nhóm sẽ viết **test cho hành vi đúng** và thay đổi có chủ đích. Không nên giữ bug mãi chỉ vì test cũ đang xanh.

### 18.3. Tách một vùng logic thuần

~~~text
TRƯỚC:
  LegacyQuizController
    - Đọc HTTP request
    - Kiểm tra quyền
    - Lấy câu hỏi từ DB
    - Tính điểm trong 200 dòng if/else
    - Ghi kết quả
    - Gửi email

BƯỚC AN TOÀN:
  LegacyQuizController
    - Giữ hành vi vào/ra và giao dịch hiện tại
    - Gọi QuizScorer cho rule đã được kiểm chứng
    - Có regression + integration tests cho luồng thật

SAU KHI CÓ BẰNG CHỨNG:
  QuizSubmissionService
    - Tách rule điểm, quyền, lưu và thông báo
    - Giữ contract với clients cũ khi còn sử dụng
~~~

Mục tiêu không phải biến một class thành mười microservices. Mục tiêu là **thay rule mà không phải mạo hiểm với tất cả phần còn lại**.

## 19. Branch by abstraction và thay đổi có tính tương thích

Khi một phần hệ thống cần được thay dần nhưng không thể ngừng phục vụ, nhóm có thể dùng **branch by abstraction**:

1. Xác định interface/ranh giới ổn định.
2. Đặt triển khai hiện tại sau ranh giới đó.
3. Xây triển khai mới theo các thay đổi nhỏ, chạy test contract chung.
4. Chọn cách chuyển đổi an toàn (cấu hình, routing, feature flag) theo chính sách.
5. Quan sát, đối soát kết quả và giới hạn phạm vi.
6. Gỡ triển khai cũ khi không còn consumers và bằng chứng phù hợp.

### Ví dụ thay cách tính điểm

Một cơ chế chấm điểm mới chỉ dùng cho một loại bài đánh giá thử. API vẫn trả kết quả với cùng contract. Có thể chạy **shadow calculation** trong môi trường được phép và so sánh điểm mới/cũ trước khi thực sự áp dụng, nhưng phải:

- Không làm thay đổi điểm chính thức vô tình.
- Không gây side effect như cấp chứng nhận hai lần.
- Không gửi dữ liệu cá nhân tới hệ thống không được phép.
- Xác định hành vi nào khác biệt **do thay rule có chủ đích**.
- Có người chịu trách nhiệm quyết định khi kết quả không khớp.

### 19.1. Mở rộng–chuyển đổi–thu hẹp dữ liệu

Với thay đổi schema khó rollback, một cách tiếp cận minh họa là:

1. **Expand:** hỗ trợ cột/cấu trúc mới và cũ.
2. **Migrate:** chuyển dần dữ liệu có đối soát.
3. **Switch:** chuyển consumers/luồng đọc ghi sau khi test.
4. **Contract:** bỏ cấu trúc cũ khi thực sự an toàn.

**Rollback mã không tự rollback dữ liệu**. Feature flag có thể chặn một luồng UI nhưng không hoàn tác dữ liệu đã ghi hoặc bản tin đã phát. XP giúp thay đổi nhỏ và có test, nhưng trách nhiệm migration, backup, monitoring và quyền phát hành vẫn cần được quản lý.

## 20. CI theo nhiều tốc độ phản hồi

Một pipeline tốt không cần mọi kiểm tra đều chạy ở đúng cùng một thời điểm. Có thể tách các lớp feedback để Developers nhận kết quả quan trọng nhanh mà vẫn có kiểm tra chuyên sâu khi cần.

| Tầng | Mục đích | Ví dụ |
| --- | --- | --- |
| **Local/fast checks** | Phát hiện lỗi thường gặp trong thời gian ngắn. | Formatter, compile, unit tests thuần, lint phù hợp. |
| **Pre-merge CI** | Ngăn lỗi tích hợp và contract nghiêm trọng. | Unit suite, integration chọn lọc, auth negative tests liên quan, review. |
| **Post-merge/mainline CI** | Bảo vệ codebase chung. | Build, integration/contract suites đáng tin, artifact checks. |
| **Scheduled/deeper tests** | Phát hiện rủi ro nặng hoặc hiếm. | Performance, resilience, security scans/phân tích chuyên sâu. |
| **Pre-release checks** | Chứng minh đủ điều kiện cho rollout cụ thể. | DoD, migration, observability, quyền release, rollback readiness. |
| **Post-release monitoring** | Nhận phản hồi vận hành và người dùng. | Error rate, latency, data integrity, task success, incident signals. |

**Không được chuyển một kiểm tra bắt buộc ra sau release nếu điều đó gây rủi ro không được chấp nhận.** Phân tầng nhằm giảm lãng phí và tăng tốc phản hồi trong phạm vi an toàn, không né guardrails.

### 20.1. Một pipeline kiểm chứng minh họa

~~~text
Khi mở Pull Request:
  1. Compile + formatter/lint
  2. Unit tests của code và domain rules
  3. Integration + contract tests quan trọng
  4. Negative authorization tests liên quan
  5. Dependency/secret checks theo chính sách
  6. Review với tiêu chí rõ

Khi merge:
  7. Mainline build + kiểm tra môi trường tích hợp
  8. Tạo artifact có version
  9. Xác nhận DoD, migration và rủi ro cần thiết

Khi release:
  10. Kiểm tra quyền, điều kiện vận hành và người có thẩm quyền
  11. Rollout có kiểm soát
  12. Quan sát lỗi và phản hồi
  13. Dừng/khôi phục nếu chạm stop condition
~~~

Thứ tự và nơi chạy checks thay đổi theo kiến trúc; đây là **mẫu tư duy** chứ không phải file cấu hình có thể dùng nguyên cho mọi CI server.

### 20.2. Khi build đỏ

Một working agreement nên nêu:

- Ai nhận thông báo?
- Có ngừng merge vào mainline hay không?
- Cần tái hiện lỗi ở môi trường nào?
- Ai chịu trách nhiệm sửa, revert hoặc chuyển cấp?
- Trường hợp false positive/flaky test xử lý thế nào?
- Có ghi nguyên nhân và hành động phòng ngừa khi lỗi lặp?

Nếu mọi người tiếp tục merge trong khi build đỏ kéo dài, CI trở thành **dashboard trang trí**, không còn là feedback đáng tin.

### 20.3. Kiểm tra độ ổn định của pipeline

Theo dõi không chỉ thời gian chạy trung bình, mà còn:

- Phân bố thời gian feedback, đặc biệt những lần chạy rất chậm.
- Tỷ lệ fail do lỗi sản phẩm so với fail do hạ tầng/test flake.
- Tỷ lệ rerun làm xanh mà không đổi code.
- Thời gian từ build đỏ tới phục hồi.
- Số thay đổi bị chặn do queue, môi trường hoặc approval.
- Độ phủ của các đường rủi ro cao, không chỉ line coverage.

## 21. Small releases và feedback sớm: ghép XP với chiến lược sản phẩm

**Small releases** nhằm đưa một phần giá trị đủ chất lượng tới người dùng sớm hơn, từ đó hiểu nhu cầu và giảm chi phí đổi hướng. Chúng cần nối với cách PO quản lý Product Backlog và những ràng buộc phát hành.

### Ví dụ chia lát tính năng bài kiểm tra

| Lát | Hành vi có giá trị | Kỹ thuật XP hỗ trợ | Bằng chứng cần thu |
| --- | --- | --- | --- |
| **I1** | Học viên có quyền nộp một bài ngắn và xem số câu đúng. | TDD cho QuizScorer, acceptance tests, CI. | Rule đúng, quyền an toàn, người học hiểu trạng thái. |
| **I2** | Học viên xem lại một kết quả đã lưu qua phiên. | Integration/contract tests, refactoring dữ liệu. | Không lẫn kết quả người khác, đúng khi retry. |
| **I3** | Học viên nhận phản hồi vì sao một đáp án sai. | Pairing với giảng viên/PO, example mapping. | Học viên hiểu lời giải và có thể tiếp tục. |
| **I4** | Người học đủ điều kiện nhận chứng nhận hợp lệ. | TDD business rules + tests idempotency. | Không cấp trùng, đúng điều kiện. |
| **I5** | Mở rộng nhiều loại bài và chế độ học. | Simple design, refactoring khi xuất hiện biến thể thật. | Có nhu cầu và giữ chất lượng. |

Một lát mới có thể dùng trước Sprint Review nếu đã đạt DoD và điều kiện release phù hợp. **Sprint Review không phải cổng release bắt buộc** theo Scrum.

### 21.1. Feature flag và đợt mở nhỏ

Feature flag có thể hỗ trợ tách deploy khỏi release và thử một cohort. Tuy nhiên:

- Không thay kiểm thử quyền/dữ liệu.
- Không được dùng để hợp thức hóa code chưa đạt DoD.
- Phải có owner và kế hoạch xóa flag khi không còn dùng.
- Cần hiểu rollback ảnh hưởng dữ liệu hoặc side effects thế nào.
- Phải có stop conditions và telemetry thích hợp.

### 21.2. Đừng đồng nhất release nhiều với tạo nhiều giá trị

Nếu nhóm phát hành 20 lần trong tuần nhưng không ai dùng hoặc lỗi tăng, số release lớn không chứng minh thành công. Hãy xem **thời gian đến phản hồi hữu ích, chất lượng và outcome người học**, không tối ưu số lần deploy đơn thuần.

## 22. XP và rủi ro bảo mật, dữ liệu, tuân thủ

Các thực hành XP tăng feedback nhưng **không cấp quyền bỏ kiểm soát bắt buộc**. Ví dụ một PBI chấm điểm Java có thể liên quan:

- Thẩm quyền đọc/ghi kết quả.
- PII của học viên và việc lưu log.
- Idempotency cho submit/retake.
- Thay contract của hệ thống khóa học.
- Quy tắc không cấp chứng nhận khi chưa đủ điều kiện.
- Giới hạn lưu dữ liệu và yêu cầu audit.
- Tính tương thích khi schema tiến hóa.

### 22.1. Bảo mật đưa vào acceptance/DoD

Ví dụ acceptance criteria:

~~~gherkin
Feature: Chỉ chủ sở hữu hoặc người được phép mới xem kết quả

Scenario: Học viên đọc kết quả của chính mình
  Given học viên đã đăng nhập và có quyền với bài đánh giá
  When yêu cầu kết quả của mình
  Then hệ thống trả dữ liệu được phép theo chính sách

Scenario: Học viên cố đọc kết quả người khác
  Given tài khoản không có quyền với kết quả "attempt-other"
  When yêu cầu kết quả "attempt-other"
  Then hệ thống từ chối theo chính sách
  And không tiết lộ điểm hoặc thông tin riêng tư

Scenario: Yêu cầu ghi kết quả bị gửi lại
  Given request "req-42" đã được xử lý hợp lệ
  When cùng request được gửi lại
  Then hệ thống không tạo kết quả trùng trái quy tắc
~~~

Với một thay đổi lớn về quyền, cần cả **review chuyên môn và tests theo rủi ro**, không coi 100% coverage là chấp nhận được.

### 22.2. Thẩm quyền và phê duyệt

- PO chịu trách nhiệm giá trị và thứ tự Product Backlog trong Scrum.
- Developers chịu trách nhiệm tạo Increment đạt DoD.
- Scrum Master giúp nhóm và tổ chức làm Scrum hiệu quả.
- Quyền phê duyệt **bảo mật, pháp lý, release hoặc chấp nhận rủi ro còn lại** do chính sách thực tế xác định.

Pairing, CI hay “đã đồng thuận trong Retrospective” không tự thay sự phê duyệt được yêu cầu bởi nghĩa vụ bắt buộc.

## 23. Phân tán, nhiều múi giờ và áp dụng XP

Một nhóm làm việc từ xa vẫn có thể pairing, CI và chia sẻ code ownership. Điều kiện thành công khác khi mọi người không có giờ làm trùng.

### Pairing từ xa có chủ đích

- Chọn vấn đề đủ rõ và đáng cùng giải.
- Gửi acceptance criteria, test thất bại và nhánh code trước.
- Thỏa thuận thời lượng ngắn và mục tiêu mỗi phiên.
- Dùng công cụ chia sẻ được phép, bảo vệ secret/dữ liệu.
- Đổi Driver/Navigator.
- Ghi quyết định và link PR/tests để người ở múi giờ khác tiếp tục.
- Không biến pairing thành cuộc gọi 8 giờ gây kiệt sức.

### Phản hồi bất đồng bộ

Khi không cùng giờ:

- CI và logs tạo **bằng chứng có thể kiểm tra**.
- PR nhỏ, mô tả hành vi, test và rủi ro.
- Contract/ADR đủ ngữ cảnh để người đến sau hiểu.
- Review có owner/khung phản hồi tương ứng múi giờ.
- Handoff ghi trạng thái được xác minh và next action.

### Khi không nên cố áp pairing đồng bộ

Một nhóm không có giờ trùng an toàn có thể ưu tiên **review async thường xuyên, ensemble theo phiên ngắn luân phiên, test-first và cập nhật tài liệu**, thay vì ép ai đó làm việc ban đêm. XP phục vụ chất lượng và tôn trọng, không phải lý do phá nhịp làm bền vững.

## 24. Đo chất lượng và khả năng thay đổi: nhìn hệ thống, không xếp hạng cá nhân

Một thí nghiệm áp dụng XP cần **baseline** và tín hiệu để biết có cải thiện không. Không có một con số đơn lẻ đo được toàn bộ chất lượng.

| Góc nhìn | Số đo minh họa | Giới hạn |
| --- | --- | --- |
| **Flow** | Cycle time, throughput, WIP, work item age, blocked time. | Thay cách chia ticket có thể làm số thay đổi. |
| **Change safety** | Escaped defects theo mức nghiêm trọng, incidents sau release. | Không phản ánh những lỗi chưa được phát hiện; cần ngữ cảnh. |
| **CI feedback** | Thời gian CI, test flakiness, thời gian sửa build đỏ. | Pipeline nhanh nhưng thiếu checks không đủ chất lượng. |
| **Release capability** | Thời gian từ Done tới Released, lead time cho thay đổi. | Nhiều deploy chưa chắc tạo giá trị. |
| **Reliability** | Failed changes, thời gian phục hồi, lỗi/tải khi sử dụng. | Phải định nghĩa sự cố/failed deployment nhất quán. |
| **Design changeability** | Thời gian thay rule có test, phạm vi code ảnh hưởng, mức rework. | Khó quy thành một điểm số duy nhất. |
| **Knowledge sharing** | Số người có thể sửa vùng code với hỗ trợ phù hợp, onboarding friction. | Không dùng để đánh giá một người qua số PR. |
| **Outcome** | Tỷ lệ học viên nộp bài hợp lệ, hiểu kết quả, tiếp tục bài học. | Nhiều yếu tố khác có thể gây thay đổi outcome. |

Các chỉ số DORA về tốc độ và ổn định delivery có thể hữu ích ở cấp hệ thống nếu định nghĩa rõ và dùng đúng bối cảnh. Không nên coi metric trung bình của một tổ chức là chuẩn bắt buộc cho mọi nhóm khác nhau.

### 24.1. Ví dụ dữ liệu trước–sau mang tính minh họa

Giả sử trước khi nhóm cải thiện, cycle time của năm PBI gần như tương tự (đơn vị ngày làm việc) là:

| Giai đoạn | Dữ liệu PBI | Trung vị |
| --- | --- | ---: |
| **Trước** | 8, 11, 10, 14, 9 | 10 |
| **Sau** | 7, 6, 8, 7, 6 | 7 |

Dữ liệu cho thấy **trung vị quan sát** giảm từ 10 xuống 7 ngày, tương đương 3 ngày trong hai mẫu nhỏ.

Nhưng **chưa thể quy toàn bộ mức giảm cho XP** nếu đồng thời:

- PBI sau nhỏ hơn hoặc dễ hơn.
- Nhóm đổi thành viên.
- Một phụ thuộc bên ngoài được giải quyết.
- Definition of Done bị hạ.
- Cách ghi Started/Done thay đổi.
- Có ít lỗi production nhưng chưa đủ thời gian theo dõi.

Cần giữ **DoD, chất lượng, loại PBI và cách đo** rõ, xem thêm nhiều quan sát và phản hồi định tính.

### 24.2. Khi coverage tăng nhưng quality không tăng

Nếu coverage từ 50% lên 85%, đó là một tín hiệu kỹ thuật. Tuy nhiên, nếu tests chủ yếu kiểm method được gọi và không bắt lỗi chấm điểm, nó chưa chứng minh sản phẩm an toàn. Cần kết hợp **sức mạnh assertion, rủi ro được kiểm, lỗi thoát ra production và khả năng refactor tự tin**.

### 24.3. Không dùng XP để tạo KPI points

Một cặp Developers có thể giải quyết bug khó trong một ngày, một người khác sửa nhiều ticket nhỏ. Không thể lấy số ticket/points của từng người để kết luận năng suất. Pairing và collective ownership đặc biệt dễ bị méo nếu tổ chức chỉ ghi công người commit.

## 25. Ma trận quyết định: nên bổ sung thực hành nào trước?

| Điều kiện nhóm | Lựa chọn khởi đầu khả thi | Điều cần cẩn trọng |
| --- | --- | --- |
| **Code mới, quy tắc rõ, ít phụ thuộc** | TDD ở logic, CI nhanh, coding standards. | Không xây abstraction cho tương lai giả định. |
| **Legacy ít tests** | Characterization tests, refactor lát nhỏ, CI cho vùng chạm tới. | Không viết lại toàn bộ trước khi giao giá trị. |
| **Phụ thuộc API liên nhóm nhiều** | Contract tests, pairing/review liên nhóm, tích hợp thường xuyên. | Chủ sở hữu hợp đồng và quyền thay cần rõ. |
| **Review bị nghẽn** | PR nhỏ, pairing, review policy, giới hạn WIP. | Đừng ép mọi PBI phải có cả nhóm tham gia. |
| **Nhiều lỗi sau release** | Negative/acceptance/integration tests, CI, DoD, small rollout. | Đừng chỉ tăng số unit tests mà bỏ incident analysis. |
| **Remote nhiều múi giờ** | CI, small PR, decision log, pairing theo khung trùng giờ tự nguyện. | Không ép ngoài giờ hoặc phụ thuộc cuộc gọi không ghi kết quả. |
| **Thành viên mới chưa quen domain** | Pair rotation, example mapping, tests dễ đọc. | Không biến pairing thành kèm cặp một chiều mãi mãi. |
| **Áp lực deadline thật** | Chia lát dọc, giữ DoD, CI, forecast theo phạm vi. | Không hạ kiểm thử hay “đóng points” để kịp số. |
| **Yêu cầu bảo mật/tuân thủ cao** | Test-first ở logic nhạy cảm, kiểm tra quyền, CI evidence, review thẩm quyền. | XP không thay phê duyệt hoặc chuẩn bắt buộc. |
| **Flow ổn nhưng outcome thấp** | Customer collaboration, acceptance examples, small releases, discovery. | Tăng TDD không sửa được việc xây sai sản phẩm. |

### 25.1. Quy tắc chọn theo rủi ro

Nếu nhiều lựa chọn đều hấp dẫn, ưu tiên thực hành:

1. Xử lý **nút thắt/rủi ro lớn nhất** tới mục tiêu.
2. Có thể thử trong phạm vi **nhỏ nhưng đủ quan sát**.
3. Không phá DoD và các ràng buộc hiện có.
4. Có người dẫn dắt/cùng học, không chỉ ra lệnh.
5. Có cách đánh giá dựa trên dữ liệu và phản hồi.
6. Có thể dừng hoặc đổi khi bằng chứng không hỗ trợ.

## 26. Lộ trình áp dụng trong sáu tuần: không đổi mọi thứ cùng lúc

Đây là **một phương án minh họa**, không phải công thức bắt buộc cho mọi nhóm.

| Giai đoạn | Thử nghiệm | Bằng chứng mong muốn |
| --- | --- | --- |
| **Tuần 1: hiểu baseline** | Chọn vùng code có thay đổi thật; đo cycle time, lỗi, CI, review wait. | Biết vấn đề và mục tiêu thử nghiệm. |
| **Tuần 2: feedback nhỏ** | TDD ở một rule thuần và CI chạy unit tests khi PR. | Test Red–Green–Refactor được thực hành, lỗi lộ sớm. |
| **Tuần 3: legacy safety net** | Characterization tests và refactor một seam. | Giữ hành vi hiện có; thay rule mới dễ hơn. |
| **Tuần 4: tích hợp và cộng tác** | Contract tests, PR nhỏ, pairing ở vùng có rủi ro. | Giảm chờ review/tích hợp, bớt hiểu sai. |
| **Tuần 5: Increment & release** | Giao một lát dọc qua DoD, quan sát người dùng phù hợp. | Bằng chứng quality + outcome. |
| **Tuần 6: đánh giá và thích ứng** | Retrospective dựa trên số liệu và trải nghiệm nhóm. | Giữ/sửa/bỏ thực hành, chọn nút thắt tiếp. |

Nếu CI đang hỏng nặng hoặc đã có lỗi bảo mật nghiêm trọng, **không cần đợi đúng tuần trong bảng**; ưu tiên xử lý rủi ro và kiểm soát tương ứng.

### 26.1. Một thử nghiệm tốt phải có “điều kiện thành công”

Ví dụ:

> “Trong hai Sprint tới, với các PBI thay đổi logic chấm điểm, Developers sẽ dùng TDD cho các rule thuần và chạy unit/integration checks trong CI trước merge. Chúng tôi kỳ vọng ít lỗi chấm điểm thoát sang test end-to-end và thời gian chẩn đoán giảm, đồng thời cycle time/DoD không xấu đi rõ rệt. Nếu suite quá flaky hoặc việc viết test không phù hợp thiết kế hiện tại, nhóm sẽ cải thiện seam/fixture thay vì bỏ kiểm thử quan trọng.”

Đó là giả thuyết **có thể kiểm tra và điều chỉnh**, không phải chỉ tiêu “mọi người phải có 100% TDD”.

## 27. Áp dụng XP trong Sprint Planning và Definition of Done

### 27.1. Trước Sprint

- PO làm rõ mục tiêu người dùng và thứ tự PBI.
- Developers xem PBI có đủ ví dụ, chia lát và phụ thuộc chưa.
- Xác định rủi ro test/integration/quyền quan trọng.
- Ước lượng/forecast theo quy ước riêng nếu cần, tính **toàn bộ việc đạt DoD**, không chỉ code.
- Không tách “viết test” thành công việc hứa làm Sprint sau để giữ points đẹp.

### 27.2. Trong Sprint

- Chọn một PBI nhỏ và xây **end-to-end**.
- Dùng TDD ở logic phù hợp, tests ở các ranh giới cần thiết.
- CI chạy thường xuyên, xử lý build đỏ.
- Pair/review vùng có rủi ro.
- Refactor sau mỗi vòng khi tests bảo vệ.
- Theo dõi blocked/WIP; tập trung đưa PBI tới Done.
- Khi phát hiện bất định mới, Developers trao đổi PO về phạm vi trong giới hạn Sprint Goal và DoD.

### 27.3. Definition of Done minh họa

~~~text
INCREMENT DEFINITION OF DONE — ví dụ, không phải chuẩn chung

- PBI có hành vi đầu cuối đáp ứng acceptance criteria.
- Code tích hợp với sản phẩm hiện tại và review theo chính sách.
- Unit/integration/contract tests phù hợp đều đạt.
- Negative authorization tests ở đường dữ liệu nhạy cảm đạt.
- Không có lỗi biết trước vi phạm tiêu chuẩn an toàn bắt buộc.
- Dữ liệu, migration, retry và khả năng phục hồi được xử lý theo rủi ro.
- CI/mainline không hỏng vì thay đổi này.
- Hướng dẫn/telemetry vận hành cần thiết đã cập nhật.
- Không phá Increment trước trong phạm vi được hỗ trợ.
~~~

Scrum Guide quy định **Definition of Done là commitment của Increment**; tổ chức có thể có chuẩn tối thiểu bắt buộc. XP làm cách đạt DoD đáng tin hơn, không thay DoD bằng những khẩu hiệu như “chúng tôi luôn viết TDD”.

## 28. Khi không nên áp dụng một thực hành XP theo đúng hình thức

Một quyết định trưởng thành có thể là **không chọn** kỹ thuật nào đó ở một số công việc, nếu đã hiểu đánh đổi.

### 28.1. Không ép mọi thay đổi phải có hai người pairing

Sửa một nhãn text đơn giản với CI và review phù hợp có thể không cần pairing. Hãy ưu tiên pairing ở vùng **rủi ro, bất định hoặc lợi ích chia sẻ tri thức** cao.

### 28.2. Không viết toàn bộ end-to-end tests trước khi hiểu rule

Ở bài toán chưa rõ, có thể dùng **example mapping, prototype hoặc spike** trước; khi behavior đã đủ hiểu, mới thiết kế tests ở tầng thích hợp. Không dùng code tests để khóa một giả định nghiệp vụ chưa được xác nhận.

### 28.3. Không refactor toàn bộ legacy vì sợ nợ kỹ thuật

Refactor vùng đang thay đổi, có safety net và mục đích cụ thể. Một cuộc viết lại toàn bộ thường tăng rủi ro, hoãn giao giá trị và có thể tái tạo lỗi cũ trong kiến trúc mới.

### 28.4. Không tích hợp nhanh bằng cách bỏ test cần thiết

Muốn CI nhanh hơn có thể chia suite, sửa flaky tests, cache build hoặc parallelize an toàn; **không lặng lẽ bỏ negative tests phân quyền hoặc contract checks bắt buộc**.

### 28.5. Không dùng feature flag thay release readiness

Một flag tắt không chứng minh mã đã an toàn, không tự rollback dữ liệu sai. Muốn release phải giữ guardrails, quyền và kế hoạch vận hành.

### 28.6. Không gọi XP là thay thế Scrum hoặc Kanban trong mọi tổ chức

Một nhóm có thể có Scrum/Kanban hiệu quả và chọn vài thực hành XP; nhóm khác dùng một cách tiếp cận khác khi phụ thuộc, rủi ro, regulatory constraints hoặc dòng việc đòi hỏi. **Đánh giá dựa trên kết quả và phù hợp bối cảnh**, không dựa nhãn phương pháp.

## 29. Tình huống xuyên suốt: chọn XP cho nhóm làm nền tảng thi Java

Một Scrum Team tám thành viên phát triển tính năng bài kiểm tra Java cho các khóa học. Nhóm có Sprint hai tuần. Product Owner muốn học viên làm bài, xem kết quả và nhận phản hồi trong bốn tuần tiếp theo.

### Trạng thái ban đầu

- Product Backlog có thứ tự, Sprint Goal rõ, nhưng code thường chưa tích hợp xong cuối Sprint.
- Một module legacy vừa tính điểm, vừa lưu kết quả, vừa gửi sự kiện cấp chứng nhận.
- Developers giữ nhánh riêng nhiều ngày; merge conflict xảy ra cuối Sprint.
- Unit tests chủ yếu kiểm trường hợp đơn giản, integration suite chạy thủ công.
- Mỗi Sprint mất hai đến ba ngày xử lý lỗi tích hợp.
- Request nộp bài bị gửi lại có thể ghi hai kết quả.
- PO/giảng viên chưa thống nhất câu bỏ trắng có trừ điểm không.
- Nhóm định triển khai toàn bộ chức năng trong một đợt lớn.

Nếu chỉ yêu cầu “mọi người viết TDD” thì rủi ro **idempotency, quyền và yêu cầu nghiệp vụ** vẫn tồn tại. Cần chọn những thực hành bổ trợ nhau.

### 29.1. Phân tích và quyết định

| Vấn đề | Can thiệp được ưu tiên | Cơ chế lợi ích |
| --- | --- | --- |
| Rule điểm thiếu thống nhất. | Example mapping và acceptance criteria với PO/giảng viên. | Tests kiểm đúng rule, không khóa giả định. |
| Legacy scorer khó đổi. | Characterization tests, tách scorer, TDD rule mới. | Tạo safety net và giảm coupling. |
| Nhánh dài, tích hợp muộn. | CI + thay đổi/PR nhỏ + merge thường xuyên. | Phát hiện xung đột sớm. |
| Submit trùng khi retry. | Pairing tại ranh giới idempotency + integration tests. | Làm rõ request identity, giao dịch và cạnh tranh. |
| Rủi ro quyền. | Negative authorization tests + review chuyên môn. | Bảo vệ dữ liệu và DoD. |
| Feedback người học quá muộn. | Vertical slices + release có kiểm soát. | Kiểm chứng giá trị trước khi mở rộng. |
| Một người biết module legacy. | Pair rotation + standards + collective ownership. | Giảm phụ thuộc cá nhân. |

### 29.2. Sprint Goal và lát dọc

**Sprint Goal ứng viên:**

> “Học viên có quyền có thể nộp một bài Java cơ bản, nhận kết quả chính xác và hiểu rõ trạng thái nộp bài ngay cả khi mạng có lỗi.”

Lát đầu gồm một loại câu hỏi được hỗ trợ, rule điểm xác nhận, phân quyền, xử lý retry và giao diện không báo thành công giả. Các điều kiện này **phải đạt DoD**, không được xem là những lát tùy chọn làm sau.

Lát sau có thể là xem lại kết quả qua phiên, giải thích một loại câu sai, rồi chứng nhận khi có giá trị/rủi ro rõ. Không cần lập tức bảng xếp hạng, AI gợi ý hay tích hợp email.

### 29.3. Một chuỗi thực hành XP trong Sprint

1. **Example mapping:** người hiểu nghiệp vụ và Developers xác định điểm, bỏ trắng, retry và retake.
2. **Pairing:** hai Developers hỏi khi nào hai request được coi là cùng một lần nộp.
3. **TDD:** viết test cho rule chấm, thấy fail, viết logic, refactor.
4. **Characterization tests:** bảo vệ hành vi legacy chưa thay.
5. **CI:** tích hợp từng thay đổi nhỏ, chạy unit/integration/contract checks theo rủi ro.
6. **Review:** xác nhận quyền, lưu dữ liệu, concurrency, error handling.
7. **DoD:** chỉ đánh dấu Done khi Increment có thể sử dụng và đáp ứng tiêu chuẩn.
8. **Small release:** khi đủ điều kiện, mở cho nhóm học viên được phép và quan sát.
9. **Inspect/adapt:** dùng phản hồi sửa Product Backlog và cải tiến cách làm.

### 29.4. Rủi ro request đồng thời

Unit TDD của QuizScorer **không phát hiện lỗi ghi trùng**. Hai request có thể cùng đọc “chưa có kết quả” rồi cùng insert. Cần thiết kế và test theo hợp đồng thật:

- Định danh requestId, learnerId, attemptId và quyền tương ứng.
- Ràng buộc idempotency ở đúng phạm vi.
- Unique constraint hoặc cơ chế dữ liệu tương đương.
- Transaction và xử lý race condition.
- Phản hồi nhất quán cho retry hợp lệ.
- Audit/telemetry không làm lộ PII/đáp án.
- Negative tests và concurrency integration tests.

~~~mermaid
sequenceDiagram
    actor Student as Học viên
    participant UI as Giao diện
    participant API as Submission API
    participant Auth as Authorization
    participant Store as Attempt Store
    Student->>UI: Nhấn Nộp
    UI->>API: Submit với requestId
    API->>Auth: Xác minh quyền và trạng thái lần thi
    Auth-->>API: Kết quả kiểm tra
    API->>Store: Ghi theo idempotency/transaction
    Store-->>API: Kết quả hoặc lỗi an toàn
    API-->>UI: Phản hồi trạng thái thật
    Note over UI,API: Retry cùng requestId theo contract nhất quán
~~~

Sơ đồ **không thay kiến trúc giao dịch thật**. Isolation, constraint, retry policy và lỗi cần được chọn/kiểm thử với database và hệ thống cụ thể.

### 29.5. Đánh giá sau hai Sprint

Không hỏi chỉ “bao nhiêu points được cộng?”. Cần xem:

- Lỗi điểm và submit trùng còn xuất hiện không?
- Thời gian review/tích hợp có giảm không?
- Khi đổi rule, Developers có tự tin chạy safety net không?
- CI có bớt flaky không?
- Increment có đạt DoD đúng hơn?
- Người học nộp và hiểu kết quả tốt hơn?
- Nhóm có bền vững, ít rework?

Nếu flow nhanh hơn nhưng lỗi phân quyền tăng, không thể coi cải tiến thành công.

## 30. Workshop lựa chọn thực hành XP có căn cứ

Một buổi workshop ngắn giúp nhóm chuyển từ tranh luận nhãn “Scrum hay XP?” thành một thử nghiệm có thể đánh giá.

### Bước 1 — Thu thập trở ngại thật

Mỗi người mang một ví dụ gần đây: PBI bị blocked, PR chờ review, incident, build đỏ, thay đổi gây hồi quy hoặc feedback nghiệp vụ đến muộn. Dẫn link từ công cụ có thẩm quyền.

### Bước 2 — Tìm nguyên nhân có thể kiểm tra

Ví dụ:

> Lỗi nộp bài lọt tới production → tests chỉ kiểm happy path → acceptance criteria không có retry → rule retake chưa được chốt → cần người nghiệp vụ và ví dụ trước khi thêm test.

Không tự động kết luận “Developer thiếu cẩn thận” nếu chưa có bằng chứng.

### Bước 3 — Chọn thực hành phù hợp

- **TDD** khi rule nhỏ thường gây lỗi.
- **CI/nhánh ngắn** khi merge và test muộn.
- **Refactoring/characterization** khi legacy khó đổi.
- **Pairing/ensemble** khi thiếu tri thức hoặc rủi ro cao.
- **Customer collaboration/example mapping** khi nghiệp vụ hiểu khác.
- **Small releases** khi thiếu phản hồi người dùng.
- **Sustainable pace/WIP control** khi bận rộn nhưng nhiều rework.

### Bước 4 — Chọn lát thử

Chỉ thử trên một tính năng “Quiz Submission” trong hai Sprint thay vì thay toàn bộ quy trình tổ chức. Phạm vi phải đủ đại diện để quan sát chất lượng.

### Bước 5 — Chọn baseline và guardrails

Baseline: cycle time, review wait, flaky tests, escaped defects, thời gian đến phản hồi người học. Guardrails: DoD, quyền, không ghi điểm sai, không ép làm thêm giờ kéo dài.

### Bước 6 — Owner, checkpoint và quyết định

Ghi ai hỗ trợ TDD/CI, ai làm rõ nghiệp vụ, ai xem kết quả, khi nào đánh giá, điều kiện giữ/sửa/dừng. Không kết thúc bằng khẩu hiệu “hãy viết code sạch hơn”.

## 31. Mẫu experiment card cho việc bổ sung XP

~~~text
EXPERIMENT: TDD + CI cho luồng Quiz Submission

VẤN ĐỀ:
  Lỗi chấm điểm và request trùng;
  rework phát hiện cuối Sprint.

GIẢ THUYẾT:
  Nếu làm rõ acceptance examples, TDD cho rule thuần,
  CI kiểm tra tích hợp trước merge, lỗi được phát hiện sớm hơn.

PHẠM VI:
  Một lát nộp bài trắc nghiệm Java, hai Sprint.
  Không ép toàn bộ legacy đổi ngay.

THỰC HÀNH:
  - Red–Green–Refactor cho scoring rules.
  - Characterization tests cho legacy bị tác động.
  - CI/contract tests/negative tests phù hợp.
  - Pairing ở ranh giới concurrency và quyền.
  - PR nhỏ và review liên tục.

BASELINE:
  Cycle time, review wait, escaped defects,
  flakiness và thời gian phục hồi build đỏ.

GUARDRAILS:
  Definition of Done và dữ liệu/quyền học viên.
  Không bỏ kiểm thử bắt buộc, không overtime liên tục.

OWNER:
  Developers vận hành CI/tests.
  PO làm rõ mục tiêu/acceptance criteria.
  Người có thẩm quyền quyết những ràng buộc áp dụng.

CHECKPOINT:
  Xem sau mỗi Sprint và đánh giá sau hai Sprint.

QUYẾT ĐỊNH:
  Giữ / sửa / mở rộng / dừng, có bằng chứng.
~~~

Đây là mẫu hỗ trợ thử nghiệm, **không phải hiện vật bắt buộc của Scrum hoặc XP**. Nếu dữ liệu đã nằm trong backlog/decision log chính, nên liên kết thay vì sao chép.

## 32. Những anti-patterns thường gặp

| Anti-pattern | Hệ quả | Cách thay |
| --- | --- | --- |
| **Bắt buộc TDD 100% mọi dòng code.** | Chạy theo tỷ lệ hơn chất lượng feedback. | Chọn behavior và rủi ro có thể kiểm tra, diễn tập vòng thật. |
| **Viết tests sau code và gọi là TDD.** | Mất vòng Red–Green–Refactor. | Thử trên một rule mới với test fail đúng lý do. |
| **Unit tests thay integration.** | Bỏ lỗi transaction, API, quyền và concurrency. | Phân tầng theo thuộc tính cần bảo vệ. |
| **Coverage là KPI cá nhân.** | Test assertion yếu hoặc cố lách coverage. | Xem escaped defects, negative tests và safety net. |
| **Pairing thành giám sát người mới.** | Một người chỉ xem, không chia sẻ tri thức. | Luân phiên vai trò, cùng giải quyết vấn đề. |
| **Pair mọi ticket.** | Lãng phí capacity hoặc gây mệt mỏi. | Chọn theo rủi ro và lợi ích. |
| **Collective ownership bỏ review.** | Ai cũng sửa nhưng thiếu ranh giới quyền/contract. | Standards, tests và review phù hợp. |
| **Refactor nghĩa là rewrite toàn hệ thống.** | Rủi ro/lãng phí lớn trước khi nhận feedback. | Refactor lát nhỏ có characterization tests. |
| **CI chỉ chạy formatter.** | Rule/API/permission vẫn lỗi. | Thêm checks theo rủi ro thực. |
| **Build đỏ vẫn merge.** | CI mất khả năng bảo vệ mainline. | Có owner và cách sửa/revert rõ. |
| **Bỏ flaky tests không có kế hoạch.** | Mất kiểm soát quan trọng. | Sửa root causes hoặc có kiểm soát thay thế tạm. |
| **Nhánh tồn tại cả Sprint.** | Xung đột lộ muộn. | Thay đổi nhỏ, tích hợp thường xuyên. |
| **PR/commit counts dùng xếp hạng.** | Khuyến khích chia nhỏ giả tạo. | Đo flow và quality/outcome ở cấp hệ thống. |
| **Simple design thành code không cấu trúc.** | Rối hơn khi đổi. | Tối giản có ranh giới và tests. |
| **Bỏ QA/security để release nhỏ.** | Mang lỗi và rủi ro tới người dùng. | Giữ DoD, giảm scope chứ không giảm an toàn. |
| **Deploy tự động nghĩa không cần quyền release.** | Nhầm năng lực kỹ thuật với thẩm quyền. | Phân biệt CI/CD, deploy và release. |
| **XP để ép velocity tăng đều.** | Points bị thổi, chất lượng xấu đi. | Forecast trung thực và đo giá trị/chất lượng. |
| **Pairing ép ngoài giờ.** | Phá sustainable pace. | Giờ giao nhau phù hợp và async review. |
| **Không hỏi PO vì đã có tests.** | Test rule sai vẫn xanh. | Example mapping và phản hồi nghiệp vụ. |
| **Không có baseline/checkpoint.** | Không biết cải tiến giúp hay hại. | Thử nhỏ, quan sát và thích ứng. |

## 33. Bài tập thực hành: kết hợp Scrum và XP khi lỗi tăng

Một nhóm sáu Developers, một Product Owner và một Scrum Master xây sản phẩm học Java, Sprint hai tuần, có DoD chung.

**Dữ liệu tình huống:**

1. Sprint Goal rõ nhưng PBI thường chưa đạt DoD vì tích hợp cuối Sprint.
2. Nhánh code tồn tại 8–12 ngày, merge cuối Sprint nhiều xung đột.
3. CI mất 45 phút; khoảng 20% lần chạy phải rerun do flaky tests.
4. Class legacy 1.800 dòng vừa chấm, ghi tiến độ và gửi sự kiện chứng nhận.
5. Học viên đôi khi nộp lại sau timeout; database xuất hiện hai kết quả.
6. Acceptance criteria “nộp thành công” không nói mạng lỗi/retry.
7. Unit coverage 82%, chưa có negative tests xem điểm người khác.
8. Một Developer duy nhất hiểu cơ chế cấp chứng nhận.
9. Code review chờ hai ngày do reviewers có quá nhiều WIP.
10. PO muốn thử giải thích đáp án sai cho một lớp học viên.
11. Quản lý yêu cầu tăng velocity từ 25 lên 40 points/Sprint như KPI.
12. Hai Developers ở múi giờ khác không thể pairing dài mỗi ngày.
13. Có deadline ra mắt luồng nộp cơ bản trước khai giảng; dashboard/email chưa rõ có bắt buộc không.
14. Một người đề xuất tắt checks quyền để giảm CI xuống 20 phút.
15. Nhóm có hai Sprint để thử cải tiến nhưng không thể ngừng delivery.
16. Build đã deploy production nhưng flag còn OFF; báo cáo nói “đã release”.

### Nhiệm vụ

1. Chọn **ba vấn đề ưu tiên**, giải thích tác động.
2. Chọn **2–4 thực hành XP** bổ trợ Scrum và cơ chế lợi ích.
3. Viết Sprint Goal theo **kết quả người học**.
4. Chia thành **2–3 lát dọc có thể sử dụng**.
5. Tách việc phù hợp **unit TDD, integration/contract và security tests**.
6. Mô tả vòng Red–Green–Refactor cho một rule điểm.
7. Đề xuất refactor legacy từng bước mà không dừng delivery.
8. Cải thiện CI và nhánh dài, không bỏ checks bắt buộc.
9. Thiết kế review/pairing phù hợp hai múi giờ.
10. Giải thích vì sao coverage 82% không đủ chứng minh chất lượng.
11. Nêu rủi ro idempotency khi request gửi lại và cách test.
12. Phân biệt Done, Deployed, Released.
13. Trả lời yêu cầu velocity 40 mà vẫn hỗ trợ forecast.
14. Chọn hai flow metrics, hai guardrails, một outcome và kênh phản hồi định tính.
15. Viết experiment card hai Sprint có checkpoint và điều kiện sửa.
16. Nếu cycle time tăng nhưng escaped defects giảm, nên diễn giải thế nào?

## 34. Hướng giải tham khảo

### 34.1. Ưu tiên và kỹ thuật

| Vấn đề | Thực hành chọn | Cơ chế |
| --- | --- | --- |
| **Submit trùng và thiếu kiểm tra quyền.** | Acceptance examples, negative tests, pairing ở concurrency/permission. | Phát hiện rủi ro dữ liệu quan trọng, giữ DoD. |
| **Legacy khó thay, rule thiếu test.** | Characterization tests, refactor một seam, TDD rule mới. | Tạo safety net trong khi vẫn giao Increment. |
| **Tích hợp muộn, CI flaky, review chờ.** | CI đáng tin, nhánh/PR ngắn, review liên tục/WIP. | Rút ngắn thời gian đến phản hồi. |

Có thể chọn pairing rotation/collective ownership để giảm bus factor, nhưng nên đánh giá năng lực và chi phí.

### 34.2. Sprint Goal và lát dọc

**Sprint Goal:**

> “Học viên có quyền có thể nộp bài Java cơ bản và xem kết quả chính xác, không ghi trùng khi retry và không được thông báo thành công sai.”

Lát ứng viên:

- **I1:** nộp một bài trắc nghiệm và xem kết quả đúng; quyền/retry/lỗi/DoD đầy đủ.
- **I2:** xem lại kết quả đã lưu qua phiên, bảo vệ dữ liệu.
- **I3:** giải thích một loại câu sai, sau khi PO/giảng viên làm rõ giá trị.

Không chia database, API, UI, QA thành bốn Increment giả vì chưa có hành vi đầu cuối.

### 34.3. Các loại kiểm thử

- **TDD unit:** điểm câu đúng/sai/bỏ trống, chuyển trạng thái thuần.
- **Integration:** request nộp, transaction, duplicate, unique constraint và concurrency.
- **Contract:** status/body của API khi thành công, timeout, gửi lại.
- **Security:** negative tests quyền theo learnerId/attemptId, hạn chế lộ điểm và log.
- **Usability:** quan sát người học hiểu trạng thái đã nộp hoặc chưa xác nhận.

**Red:** test ba câu có hai câu đúng phải trả 2, thấy fail đúng lý do. **Green:** viết scorer tối thiểu qua test. **Refactor:** cải thiện tên/ranh giới, tests vẫn xanh. Tiếp tục vòng mới cho câu bỏ trắng và những rule được xác nhận.

### 34.4. Legacy, CI và múi giờ

- Tạo characterization tests cho đường cũ trước refactor.
- Chuyển logic scoring sang thành phần dễ test với thay đổi nhỏ.
- Không rewrite class 1.800 dòng một lần.
- Sửa flaky tests có root-cause và policy, không âm thầm loại checks quyền.
- PR nhỏ, build/contract tests thường xuyên, xử lý mainline đỏ.
- Pair ở thời gian trùng giờ cho vùng rủi ro; review async với mô tả/CI/test rõ.
- Giữ sustainable pace, tránh bắt mọi người làm việc ngoài giờ.

### 34.5. Chỉ số, trạng thái và KPI

- **Done:** Increment đạt DoD.
- **Deployed:** bản build trên môi trường.
- **Released:** chức năng mở cho cohort có quyền; flag OFF nghĩa là chưa Released.

Velocity theo story points là thang nội bộ, không trực tiếp đo năng suất hoặc giá trị. Có thể dùng lịch sử của **chính nhóm** cho forecast có điều kiện, nhưng **không đặt tăng lên 40 points bắt buộc**. Nếu deadline thật, thương lượng scope và ưu tiên giá trị; không hạ DoD.

- **Flow:** cycle time Started → Done, review blocked time.
- **Guardrails:** không kết quả trùng trái quy tắc, không truy cập điểm trái quyền.
- **Outcome:** tỷ lệ học viên nộp và hiểu kết quả trong luồng thử có định nghĩa rõ.
- **Định tính:** quan sát học viên nộp khi mạng có vấn đề và hỏi cách họ hiểu thông báo.

**Experiment:** trong hai Sprint thử TDD scoring rule, CI ổn định và pairing ở idempotency, đo trước–sau và xem lại ở mỗi Sprint. Nếu cycle time tăng nhưng escaped defects giảm, cần đánh giá **mức nghiêm trọng lỗi, loại PBI, ảnh hưởng dài hạn, capacity và phản hồi người dùng**, không kết luận từ một chỉ số.

## 35. Tự kiểm tra kiến thức

**Câu 1.** Vì sao Scrum hoặc Kanban có thể cần XP bổ trợ?

**Đáp án:** Những cách điều phối giúp quản lý mục tiêu và luồng nhưng không bắt buộc kỹ thuật tests, refactoring, CI hay pairing; XP cung cấp những thực hành giúp tạo Increment chất lượng và đổi an toàn.

**Câu 2.** XP có yêu cầu nhóm triển khai mọi thực hành ngay không?

**Đáp án:** Không phải cách lựa chọn khôn ngoan. Có thể chọn thực hành có cơ chế giải quyết rủi ro/nút thắt, thử nhỏ, đo và điều chỉnh; hiểu các thực hành tương hỗ.

**Câu 3.** Red–Green–Refactor là gì?

**Đáp án:** Viết test hành vi mới thấy fail đúng lý do, viết mã tối thiểu để test đạt, sau đó cải thiện cấu trúc không đổi hành vi.

**Câu 4.** Unit test QuizScorer xanh chứng minh toàn luồng an toàn chưa?

**Đáp án:** Chưa. Còn quyền, contract, database, transaction, concurrency, retry và chất lượng theo DoD.

**Câu 5.** Characterization tests nghĩa mọi hành vi cũ đều đúng?

**Đáp án:** Không. Chúng ghi hành vi hiện tại làm safety net. Bug cũ vẫn cần sửa có chủ đích sau khi nghiệp vụ xác nhận.

**Câu 6.** Refactoring có được đổi điểm của người học không?

**Đáp án:** Không theo định nghĩa refactoring. Đổi rule là thay đổi behavior cần acceptance criteria/test riêng.

**Câu 7.** Simple design có nghĩa bỏ cấu trúc, tests hoặc quyền?

**Đáp án:** Không. Là thiết kế vừa đủ, dễ hiểu/dễ thay nhưng vẫn giữ ranh giới và tiêu chuẩn cần thiết.

**Câu 8.** Continuous Integration có phải tự động release mọi commit?

**Đáp án:** Không. CI là tích hợp/kiểm tra thường xuyên; Delivery/Deployment và release có điều kiện riêng.

**Câu 9.** Pair programming phải dùng cho tất cả PBI?

**Đáp án:** Không. Ưu tiên ở vùng rủi ro, bất định, review chờ hoặc cần chia sẻ kiến thức; cân nhắc capacity và múi giờ.

**Câu 10.** Collective code ownership có nghĩa bỏ phân quyền và review?

**Đáp án:** Không. Cần standards, tests, review và giới hạn quyền theo thực tế.

**Câu 11.** Coverage 100% bảo đảm không còn lỗi?

**Đáp án:** Không. Không phản ánh assertions, dữ liệu, quyền, concurrency hay nhu cầu người dùng nếu những điều đó không được kiểm.

**Câu 12.** Vì sao test flaky làm giảm giá trị CI?

**Đáp án:** Developers không tin tín hiệu, rerun nhiều và dễ bỏ lỗi thật. Cần sửa nguyên nhân hoặc kiểm soát thay thế minh bạch.

**Câu 13.** Small release có thể bỏ DoD vì cohort nhỏ?

**Đáp án:** Không. Giảm scope hoặc cohort trong ranh giới an toàn, không bỏ kiểm soát bắt buộc.

**Câu 14.** Velocity có là KPI phù hợp đo thành công XP không?

**Đáp án:** Không. Nó phụ thuộc thang points nội bộ, không trực tiếp đo chất lượng/giá trị. Nên nhìn flow, escaped defects, CI health và outcome.

**Câu 15.** Khi nào example mapping quan trọng hơn viết thêm test?

**Đáp án:** Khi quy tắc chưa rõ hoặc các bên hiểu khác; test sẽ khóa giả định sai nếu không làm rõ trước.

**Câu 16.** Vì sao kỹ thuật XP cần feedback từ người dùng?

**Đáp án:** Code ít lỗi vẫn có thể xây thứ không ai cần. Increment nhỏ và review với người dùng giúp quyết định nên phát triển gì tiếp.

## 36. Checklist bổ sung XP có trách nhiệm

### Trước khi chọn

- [ ] Biết vấn đề chất lượng/khả năng thay đổi thực tế.
- [ ] Có bằng chứng từ PBI, CI, incident, flow và phản hồi.
- [ ] Phân biệt nguyên nhân kỹ thuật, nghiệp vụ, phụ thuộc và phối hợp.
- [ ] Không chọn thực hành chỉ vì tên gọi thời thượng.
- [ ] Mục tiêu và ràng buộc chất lượng đã rõ.

### Trong phát triển

- [ ] TDD áp dụng cho hành vi có thể kiểm và rule đủ rõ.
- [ ] Acceptance/integration/contract/security tests bảo vệ ranh giới quan trọng.
- [ ] Refactoring có safety net và mục tiêu cấu trúc cụ thể.
- [ ] Simple design không thành over-engineering hoặc thiếu an toàn.
- [ ] CI chạy thường xuyên, đáng tin, có chính sách build đỏ.
- [ ] PR/nhánh đủ nhỏ để tránh tích hợp cuối Sprint.
- [ ] Pair/ensemble được chọn theo rủi ro và lợi ích.
- [ ] Collective ownership có coding standards, review và quyền phù hợp.
- [ ] Sustainable pace được tôn trọng.

### Khi giao Increment

- [ ] PBI là lát dọc có giá trị, không chỉ task theo tầng.
- [ ] Acceptance criteria có success/error/permission/retry phù hợp.
- [ ] DoD giữ nguyên, không coi “90% code” là Done.
- [ ] Phần mới tương thích với phần đã Done trước.
- [ ] Done, Deployed, Released không bị trộn.
- [ ] Release theo cohort/thẩm quyền và điều kiện an toàn.
- [ ] Feedback người dùng thực sự quay vào Product Backlog.

### Khi đánh giá

- [ ] Có baseline và checkpoint.
- [ ] Đo flow, quality và outcome cùng nhau.
- [ ] Coverage/test flakiness được đọc trong bối cảnh.
- [ ] Không dùng commits, PR, points, giờ online để xếp hạng cá nhân.
- [ ] Xem tác dụng phụ lên WIP, CI time, mệt mỏi và phụ thuộc.
- [ ] Có quyết định giữ, điều chỉnh, mở rộng hoặc dừng.
- [ ] Kết quả cải tiến giúp giao phần mềm an toàn và thay đổi nhanh hơn.

Checklist hỗ trợ **ra quyết định**, không phải một cổng hành chính cho mọi thay đổi nhỏ.

## 37. Tổng kết: XP giúp giảm chi phí của sự thay đổi

- **XP bổ sung kỹ thuật tạo phần mềm chất lượng** cho cách điều phối Scrum, Kanban và các mô hình Agile.
- **Chọn từ vấn đề thật:** lỗi hồi quy, code khó đổi, tích hợp muộn, review chờ, kiến thức tập trung hoặc phản hồi giá trị chậm.
- **TDD Red–Green–Refactor** giúp có feedback nhỏ, hiểu hành vi và cải thiện thiết kế liên tục.
- **Acceptance tests và example mapping** giúp test bám theo nghiệp vụ đúng.
- **Refactoring và simple design** giữ code dễ thay, không dựng quá nhiều kiến trúc theo dự đoán.
- **CI, PR nhỏ và tích hợp thường xuyên** làm lỗi xuất hiện sớm; pipeline cần đáng tin và có người xử lý lỗi.
- **Pairing, ensemble và collective ownership** hỗ trợ chất lượng và chia sẻ tri thức, đi cùng quyền và nhịp bền vững.
- **Legacy cần safety net từng bước**: characterization tests, seam, refactor nhỏ, TDD cho hành vi mới.
- **DoD, quyền, dữ liệu và tương thích là guardrails**, không hoãn để tăng velocity.
- **Small releases nối kỹ thuật với feedback người dùng**; Done, Deployed và Released không đồng nghĩa.
- **Không triển khai XP bằng mệnh lệnh hình thức**, mà bằng một thử nghiệm có baseline, checkpoint và quyết định rõ.
- **Đo flow, chất lượng và giá trị cùng nhau**, không lấy coverage, commit hoặc story points làm mục tiêu tự thân.

Khi cân nhắc XP, hãy hỏi: **“Thực hành nào giúp nhóm phát hiện sai sớm hơn, thay đổi mã an toàn hơn và đưa một phần giá trị thật tới người dùng mà vẫn giữ tiêu chuẩn chất lượng?”**. Trả lời bằng **một thử nghiệm nhỏ, có bằng chứng và điểm xem lại rõ** là cách kết hợp Agile với XP để phần mềm vừa đáng tin vừa thích ứng với phản hồi mới.
