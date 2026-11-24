# Phân biệt mục tiêu và phạm vi của TDD, BDD và ATDD

> **Trọng tâm:** TDD (Test-Driven Development), BDD (Behavior-Driven Development) và ATDD (Acceptance Test-Driven Development) đều giúp phát triển phần mềm dựa trên phản hồi sớm, nhưng không đặt trọng tâm vào cùng một quyết định. **TDD** hỏi: “Thiết kế và hiện thực hành vi code này đúng thế nào?”. **ATDD** hỏi: “Những ví dụ nào chứng minh tính năng đáp ứng điều kiện chấp nhận đã thống nhất?”. **BDD** hỏi: “Các bên có hiểu cùng một hành vi nghiệp vụ, kể cả các trường hợp biên và ngôn ngữ mô tả không?”. Ba cách tiếp cận có thể phối hợp, không phải các lựa chọn loại trừ nhau.

## 1. Mục tiêu học tập

Sau bài học này, bạn có thể:

1. Phân biệt rõ **mục đích, phạm vi, đầu vào, đầu ra và người tham gia** của TDD, BDD, ATDD.
2. Giải thích vòng **Red–Green–Refactor** của TDD và vòng **Discovery–Formulation–Automation** thường dùng khi trình bày BDD.
3. Thống nhất **acceptance examples** trước khi viết code theo ATDD mà không mặc định mọi bài kiểm thử phải chạy qua trình duyệt.
4. Viết user story, acceptance criteria và kịch bản Given–When–Then cho một luồng có thành công, thất bại, và trạng thái bất định.
5. Mô tả một vòng TDD bằng Java/JUnit 5 và nêu ranh giới của unit test, component test, contract/integration test và end-to-end test.
6. Nhận diện **chỗ giao nhau giữa BDD và ATDD**, và cách TDD có thể hỗ trợ acceptance tests.
7. Phân biệt **acceptance criteria, Definition of Done, Increment và outcome**.
8. Lựa chọn cách kết hợp TDD, BDD, ATDD với Scrum, Kanban và XP dựa trên mức rủi ro và nhu cầu phản hồi.

## 2. Tình huống mở đầu: cùng một yêu cầu, ba câu hỏi

Một Scrum Team xây nền tảng học trực tuyến muốn giúp người học **lưu tiến độ** để quay lại tiếp tục bài học.

Product Owner nói:

> “Khi người học bấm lưu, ứng dụng phải cho biết tiến độ đã được lưu thành công hay chưa.”

Developer hỏi: “Dịch vụ lưu trả về trạng thái nào? Nếu thất bại thì logic phản hồi ra sao?”. Tester hỏi: “Nếu kết nối mất trước khi có xác nhận thì ứng dụng được phép thông báo điều gì?”. Người phụ trách sản phẩm bổ sung: “Người học không được nhận thông báo đã lưu nếu việc ghi chưa được xác nhận.”

Đây là ba lớp vấn đề:

| Câu hỏi | Cách tiếp cận nổi bật | Đích đến |
|---|---|---|
| “Hàm xử lý có trả về thành công sai khi kho dữ liệu từ chối không?” | **TDD** | Code đáp ứng hành vi nhỏ, dễ sửa và ít hồi quy |
| “Tính năng phải qua những tình huống nào để người dùng/nghiệp vụ chấp nhận?” | **ATDD** | Ví dụ chấp nhận rõ trước khi hiện thực |
| “Từ ‘đã lưu’ có nghĩa gì khi chưa nhận phản hồi hoặc khi lưu lặp?” | **BDD** | Cách hiểu chung, quy tắc và ngôn ngữ nghiệp vụ rõ ràng |

Nếu chỉ làm TDD, logic dịch vụ có thể đúng nhưng nhóm vẫn xây sai ý nghĩa của “đã lưu”. Nếu chỉ viết một browser acceptance test, phần code bên trong có thể khó bảo trì. Nếu chỉ viết Given–When–Then mà không cùng nhau làm rõ quy tắc thì vẫn chưa có sự cộng tác thật sự.

**Điểm chung** là hạn chế việc phát hiện sai lệch muộn; **điểm khác nhau** là tầng quyết định mà mỗi cách giúp nhóm đưa ra tốt hơn.

## 3. So sánh tổng quan

| Tiêu chí | TDD | ATDD | BDD |
|---|---|---|---|
| Tên đầy đủ | Test-Driven Development | Acceptance Test-Driven Development | Behavior-Driven Development |
| Trọng tâm | Thiết kế và hiện thực code qua bài test viết trước | Xác định, kiểm chứng các điều kiện chấp nhận trước khi xây | Cộng tác khám phá và mô tả hành vi bằng ngôn ngữ chung |
| Câu hỏi chính | “Phần code này phải làm gì?” | “Khi nào tính năng được chấp nhận?” | “Chúng ta đang hiểu cùng một quy tắc hành vi không?” |
| Người tham gia điển hình | Developers, người viết test, đôi khi pairing | Product Owner/nghiệp vụ, Developers, Tester, chuyên gia liên quan | Đại diện nghiệp vụ, Developers, Tester, người dùng hoặc stakeholder |
| Thời điểm nổi bật | Vừa trước khi hiện thực một hành vi nhỏ; nhiều vòng | Thống nhất ví dụ chấp nhận trước implementation | Trước/trong khi làm rõ và tiếp tục khi nhận phản hồi |
| Vòng thường dùng | **Red → Green → Refactor** | **Ví dụ chấp nhận → kiểm chứng chưa đạt → xây → đạt → đánh giá lại** | **Discovery → Formulation → Automation** |
| Phạm vi điển hình | Quy tắc hoặc thành phần nhỏ, phản hồi nhanh | Khả năng/feature/PBI theo góc nhìn chấp nhận | Quy tắc nghiệp vụ, hành vi có ý nghĩa ở nhiều tầng |
| Tài liệu/test thường thấy | Unit/component tests, code được refactor | Acceptance criteria, ví dụ và acceptance tests | Ví dụ nghiệp vụ, quy tắc, ngôn ngữ chung, scenarios |
| Công cụ có thể dùng | JUnit, pytest, xUnit, test doubles | API tests, contract tests, UI tests, kiểm chứng thủ công | Example Mapping, Gherkin/Cucumber, bảng quyết định |
| Điều không đồng nghĩa | **TDD không phải chỉ là unit testing** | **ATDD không phải chỉ là UI end-to-end testing** | **BDD không phải chỉ là Given–When–Then** |

Tên gọi đôi khi được các tổ chức dùng chồng lấn. Đặc biệt, nhiều nhóm thực hành BDD cũng làm ATDD. Vì vậy, hãy phân loại theo **câu hỏi và vòng phản hồi**, không theo phần mở rộng tệp hay tên framework.

## 4. TDD: kiểm thử dẫn dắt thiết kế code

### 4.1. TDD giải quyết vấn đề gì?

**TDD** là cách phát triển mà Developer viết một bài kiểm thử tự động cho **một hành vi nhỏ trước khi hiện thực hành vi ấy**; xác nhận nó thất bại đúng lý do; viết code vừa đủ để nó đạt; rồi cải thiện cấu trúc mà vẫn giữ các bài test xanh.

Lợi ích:

- Làm rõ hành vi mong muốn ở mức có thể hiện thực và kiểm chứng.
- Giảm thời gian phát hiện hồi quy do thay đổi nhỏ.
- Khuyến khích thiết kế tách trách nhiệm và dễ kiểm thử.
- Hỗ trợ refactoring vì có bài test bảo vệ hành vi cần giữ.
- Tránh phải đoán sau nhiều tuần tại sao một nhánh xử lý từng được viết.

TDD **không trực tiếp chứng minh sản phẩm có giá trị với người dùng**. Một đội có thể làm TDD rất giỏi để xây tính năng mà người dùng không cần.

### 4.2. Red–Green–Refactor

~~~mermaid
flowchart LR
    A["RED: test thất bại đúng lý do"] --> B["GREEN: code tối thiểu làm test qua"]
    B --> C["REFACTOR: cải thiện thiết kế, giữ test xanh"]
    C --> A
~~~

**Red:** đặt một kỳ vọng mới và chạy test để thấy điều chưa có. Lỗi do không biên dịch vì cấu hình hỏng không phải phản hồi Red có ý nghĩa.

**Green:** hiện thực đủ đúng cho trường hợp đang xét; không xây trước nhiều lớp trừu tượng chưa được chứng minh là cần.

**Refactor:** đổi cấu trúc nội bộ, tên gọi, phân tách trách nhiệm hoặc giảm trùng lặp mà không cố ý đổi hành vi đã được xác nhận. Chạy lại test.

Mỗi vòng nên nhỏ để khi thất bại, nguyên nhân dễ xác định. “Viết một trăm unit tests sau khi hoàn thành tính năng” không phải trải nghiệm Red–Green–Refactor.

### 4.3. Ví dụ TDD bằng Java: trạng thái lưu tiến độ

Giả sử hợp đồng đơn giản được thống nhất: nơi lưu trả **thành công hoặc thất bại rõ ràng**. Mục tiêu nhỏ: dịch vụ không được trả xác nhận thành công nếu nơi lưu từ chối.

Viết trước bài kiểm thử JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class ProgressServiceTest {
    @Test
    void rejectsFalseSuccessWhenStorageFails() {
        ProgressRepository repository =
            (userId, lessonId, position) -> false;
        ProgressService service = new ProgressService(repository);

        SaveStatus status = service.saveProgress("learner-7", 42, 120);

        assertEquals(SaveStatus.FAILED, status);
    }

    @Test
    void confirmsAfterSuccessfulStorage() {
        ProgressRepository repository =
            (userId, lessonId, position) -> true;
        ProgressService service = new ProgressService(repository);

        SaveStatus status = service.saveProgress("learner-7", 42, 120);

        assertEquals(SaveStatus.CONFIRMED, status);
    }
}
~~~

Một implementation tối thiểu có thể là:

~~~java
enum SaveStatus {
    CONFIRMED, FAILED
}

@FunctionalInterface
interface ProgressRepository {
    boolean save(String userId, int lessonId, int position);
}

final class ProgressService {
    private final ProgressRepository repository;

    ProgressService(ProgressRepository repository) {
        this.repository = repository;
    }

    SaveStatus saveProgress(String userId, int lessonId, int position) {
        boolean stored = repository.save(userId, lessonId, position);
        return stored ? SaveStatus.CONFIRMED : SaveStatus.FAILED;
    }
}
~~~

Ví dụ tập trung vào **một quy tắc nhỏ**, không phải code production hoàn chỉnh. Một hệ thống thật còn cần xác minh phân quyền, dữ liệu, lỗi mạng, timeout, xử lý yêu cầu lặp, bất đồng bộ và đồng bộ giữa thiết bị. Đặc biệt, **timeout có thể khiến kết quả chưa xác định**, không thể luôn ép thành thành công hoặc thất bại. Khi có yêu cầu mới về trạng thái chưa xác định, nhóm phải làm rõ hợp đồng và viết thêm test trước khi sửa code.

### 4.4. TDD không đồng nghĩa với unit test

**Unit, component, contract, integration, end-to-end** mô tả **ranh giới kiểm thử**. **TDD** mô tả **cách dùng test để dẫn dắt phát triển**.

- Unit test viết trước theo Red–Green–Refactor là một ví dụ TDD quen thuộc.
- Unit test viết sau để đạt tỷ lệ coverage **không tự trở thành TDD**.
- Một component hoặc contract test viết trước cũng có thể định hướng code theo tinh thần TDD.
- Test cấp cao quá chậm thường không phù hợp cho *mọi* vòng TDD nhỏ; cần phân tầng kiểm tra để phản hồi nhanh.

TDD không thay thế integration tests, kiểm thử khả năng sử dụng, bảo mật hoặc phản hồi người dùng.

### 4.5. Khi TDD có thể kém hiệu quả?

| Dấu hiệu | Vấn đề bên dưới | Hướng điều chỉnh |
|---|---|---|
| Test assert từng lần gọi phương thức nội bộ | Bám chi tiết cài đặt, refactor khó | Ưu tiên hành vi quan sát được và hợp đồng cần giữ |
| Test quá chậm nên Developer tránh chạy | Vòng phản hồi kéo dài | Tách các lớp test nhanh/chuyên sâu phù hợp |
| Test xanh nhưng API tích hợp sai | Thiếu kiểm tra ranh giới | Bổ sung contract/integration tests |
| Test chỉ bao phủ happy path | Thiếu rủi ro/nghiệp vụ | Từ BDD/ATDD thêm ví dụ lỗi và trường hợp biên |
| Refactor làm vỡ test dù hành vi không đổi | Test giòn hoặc kiến trúc chưa tách rõ | Cải thiện cách viết test, không hủy bỏ ý nghĩa refactoring |

## 5. ATDD: thống nhất điều kiện chấp nhận trước khi xây

### 5.1. Câu hỏi đặc trưng của ATDD

**Acceptance Test-Driven Development** bắt đầu bằng việc Product Owner/đại diện nghiệp vụ, Developers, Tester và người có chuyên môn liên quan **thống nhất những ví dụ chứng minh một khả năng được chấp nhận trước khi hiện thực**.

Ví dụ: “Điều kiện nào chứng minh PBI lưu tiến độ đã giải quyết đúng nhu cầu, kể cả khi có lỗi?”

ATDD giúp:

- Làm rõ ranh giới của một PBI/feature và điều gì được xem là đủ.
- Phát hiện mâu thuẫn giữa điều nghiệp vụ cần, điều code có thể làm và điều Tester dự định kiểm tra.
- Tạo bài kiểm tra có thể lặp lại cho các ví dụ chấp nhận.
- Hạn chế việc code xong mới tranh cãi “đã đạt chưa?”.

### 5.2. Three Amigos: ba góc nhìn, không phải ba chức danh

Trong một buổi làm rõ, nhóm có thể lấy ba góc nhìn:

- **Sản phẩm/nghiệp vụ:** giá trị, ai sử dụng, trường hợp nào quan trọng?
- **Phát triển:** ranh giới kỹ thuật, dữ liệu, trạng thái, phụ thuộc và đánh đổi?
- **Kiểm thử:** ví dụ nào chứng minh đúng/sai, trường hợp biên nào dễ bị bỏ sót?

Đây thường được gọi là **Three Amigos**, một thực hành cộng tác có thể lựa chọn, **không phải một Scrum Event chính thức**. Người có góc nhìn kiểm thử hoặc nghiệp vụ có thể là thành viên Scrum Team, hoặc chuyên gia ngoài được mời khi cần.

### 5.3. Bảng ví dụ chấp nhận

| Mã | Bối cảnh | Hành động | Kết quả phải đạt | Điều chưa rõ |
|---|---|---|---|---|
| **AC-01** | Người học hợp lệ, dịch vụ lưu hoạt động | Lưu tiến độ | UI chỉ báo đã lưu khi có xác nhận; dữ liệu đọc lại được | Xác nhận bền vững ở bước nào? |
| **AC-02** | Dịch vụ báo lỗi rõ ràng | Gửi yêu cầu lưu | UI không báo thành công giả; có hướng xử lý phù hợp | Có giữ bản cục bộ tạm không? |
| **AC-03** | Mạng ngắt trước khi nhận kết quả | Người học đã gửi yêu cầu | Không khẳng định đã lưu; hiển thị trạng thái chưa xác định phù hợp | Đối soát sau khi nối lại thế nào? |
| **AC-04** | Tài khoản không có quyền | Yêu cầu đọc tiến độ người khác | Từ chối, không tiết lộ dữ liệu | Vai trò và quy tắc cấp quyền cụ thể |
| **AC-05** | Tiến độ đã được xác nhận | Mở lại từ thiết bị được hỗ trợ | Hiển thị theo chính sách đồng bộ đã thống nhất | Xung đột nhiều thiết bị xử lý ra sao? |

Khi cột “Điều chưa rõ” chứa câu hỏi ảnh hưởng kết quả, nhóm **phải xác nhận hoặc giới hạn phạm vi** trước khi gọi acceptance example là đã thống nhất. Không nên tự bịa chính sách đồng bộ để viết test nhanh.

### 5.4. Acceptance test không bắt buộc là browser E2E test

Điểm cốt lõi của ATDD là **định nghĩa điều kiện chấp nhận có thể kiểm chứng trước implementation**, không phải dùng Selenium, Playwright hoặc bất kỳ công cụ UI nào.

Một acceptance example có thể được kiểm chứng ở:

- **Component/API level:** khi behavior nhìn thấy rõ qua API hoặc thành phần.
- **Contract/integration level:** khi cần kiểm tra hệ thống giao tiếp đúng qua ranh giới.
- **UI/end-to-end level:** với số ít hành trình người dùng mà trải nghiệm giao diện quyết định kết quả.
- **Phiên kiểm chứng với người:** khi hành vi khó tự động hóa có ý nghĩa như khả năng hiểu, dùng được hoặc trường hợp đặc thù.

Nhóm nên chọn **cấp kiểm chứng thấp nhất vẫn cung cấp bằng chứng đáng tin về hành vi**, bổ sung E2E khi thực sự cần. Nếu mọi acceptance test đều khởi động trình duyệt và nhiều dịch vụ, test suite dễ chậm, flaky và khó chẩn đoán.

### 5.5. ATDD khác việc Tester viết test sau khi có code

~~~text
ATDD:
  Bàn ví dụ chấp nhận -> rõ quy tắc -> test chưa đạt
  -> hiện thực -> test đạt -> kiểm chứng chất lượng toàn Increment

Kiểm thử sau:
  Hiện thực -> Tester nhận bản giao -> tìm kỳ vọng và thử
  -> có thể phát hiện sai hiểu rất muộn
~~~

Kiểm thử sau vẫn có vai trò, đặc biệt khám phá lỗi hoặc đánh giá rủi ro. Nhưng **ATDD chuyển việc thống nhất kỳ vọng sang trước khi xây**.

### 5.6. Phân biệt acceptance criteria, acceptance test và DoD

| Khái niệm | Dùng để làm gì? | Ví dụ |
|---|---|---|
| **Acceptance criteria** | Nêu điều kiện hành vi/kết quả của một PBI | Không thông báo “Đã lưu” khi chưa có xác nhận |
| **Acceptance test** | Kiểm chứng một ví dụ chấp nhận cụ thể | Giả lập backend trả lỗi và xác nhận UI không báo thành công |
| **Definition of Done** | Chuẩn chất lượng chung để Increment được coi là hoàn thành | Đã tích hợp, test cần thiết đạt, kiểm soát bảo mật và vận hành đáp ứng |
| **Outcome** | Kết quả người dùng/sản phẩm sau khi họ sử dụng | Giảm trường hợp mất tiến độ và tỷ lệ học lại không mong muốn |

Acceptance test xanh **không tự làm PBI Done** nếu DoD chưa đạt. Increment đạt DoD **không tự chứng minh Product Goal đạt**, vì outcome còn cần quan sát.

## 6. BDD: khám phá hành vi bằng ngôn ngữ chung

### 6.1. BDD không chỉ là Given–When–Then

**Behavior-Driven Development** đặt trọng tâm vào việc **người hiểu sản phẩm, người xây và người kiểm thử cùng khám phá và thống nhất hành vi có giá trị**.

Một cách mô tả vòng BDD:

1. **Discovery:** cùng tìm quy tắc, ví dụ, phản ví dụ và câu hỏi chưa có đáp án.
2. **Formulation:** diễn đạt hành vi cụ thể, dễ đọc, trong **ngôn ngữ chung của miền nghiệp vụ**.
3. **Automation:** tự động hóa những ví dụ phù hợp để kiểm chứng qua thay đổi; cập nhật khi quy tắc đổi.

Không phải mọi ví dụ phải được tự động hóa. Viết nhiều file Gherkin mà không có Discovery có thể chỉ là **kiểm thử theo cú pháp BDD**, chưa đạt được lợi ích cộng tác mà BDD nhấn mạnh.

### 6.2. Discovery: phát hiện một từ gây hiểu nhầm

Product Owner nói: “Ứng dụng phải báo đã lưu ngay sau khi người học bấm Lưu.”

Developer hỏi: “Ngay sau bấm nút, hay sau khi backend xác nhận lưu?”.

Tester hỏi: “Nếu timeout khiến ta không biết backend đã ghi hay chưa thì sao?”.

Sau trao đổi, nhóm thống nhất:

- **Đã gửi yêu cầu**: có request, chưa có nghĩa dữ liệu đã lưu.
- **Đang lưu**: đang xử lý, chưa đủ bằng chứng.
- **Đã lưu**: có xác nhận hợp lệ theo hợp đồng đã thống nhất.
- **Lưu thất bại**: có kết quả thất bại rõ ràng.
- **Chưa xác định**: không đủ căn cứ khẳng định thành công hoặc thất bại.

Điều này ảnh hưởng giao diện, API, các test và tài liệu. **Phản hồi quan trọng nhất của BDD có thể là phát hiện thiếu quy tắc trước khi code.**

### 6.3. Gherkin diễn đạt hành vi có thể quan sát

Gherkin cho phép mô tả ví dụ với các từ khóa Feature, Scenario, Given, When, Then, And. Dưới đây dùng **từ khóa tiếng Anh chuẩn**, còn nội dung bước viết bằng tiếng Việt. Để chạy tự động cần triển khai step definitions, dữ liệu thử và môi trường phù hợp.

~~~gherkin
Feature: Phản hồi trạng thái lưu tiến độ học
  Người học cần biết liệu dữ liệu của mình đã được xác nhận lưu hay chưa.

  Scenario: Lưu tiến độ thành công
    Given người học có quyền học bài "Java cơ bản"
    And dịch vụ lưu đang hoạt động bình thường
    When người học yêu cầu lưu tại phút thứ 5
    And dịch vụ xác nhận tiến độ đã được lưu
    Then người học nhìn thấy trạng thái "Đã lưu"
    And tiến độ xác nhận có thể được đọc lại

  Scenario: Dịch vụ xác nhận lưu thất bại
    Given người học đang có tiến độ chưa được xác nhận
    When người học gửi yêu cầu lưu
    And dịch vụ trả kết quả thất bại
    Then giao diện không hiển thị trạng thái "Đã lưu"
    And người học được hướng dẫn xử lý phù hợp

  Scenario: Kết nối mất trước khi biết kết quả
    Given người học đã gửi yêu cầu lưu
    When kết nối ngắt trước khi có kết quả đáng tin
    Then giao diện không khẳng định "Đã lưu"
    And giao diện hiển thị trạng thái chưa xác định phù hợp
~~~

Các kịch bản **không tự quyết định chính sách đối soát sau timeout**; nếu điều đó chưa rõ, cần ghi câu hỏi và làm rõ với người có thẩm quyền. BDD không biến một giả định thiếu cơ sở thành yêu cầu chỉ vì nó được viết trong file Feature.

### 6.4. Scenario có thể chạy nhưng thiếu giá trị nghiệp vụ

~~~gherkin
Scenario: Bấm nút lưu
  Given tôi mở trang học
  When tôi bấm #save-button
  Then phần tử .toast-green xuất hiện
~~~

Scenario trên không trả lời **khi nào hệ thống được phép báo thành công**. Nó có thể kiểm tra một chi tiết UI, nhưng chưa đủ để giải thích và bảo vệ quy tắc nghiệp vụ.

Một scenario tốt ưu tiên **điều kiện, hành vi quan sát được và ý nghĩa**, thay vì khóa chặt người đọc vào tên class CSS, id phần tử hoặc trình tự gọi phương thức nội bộ.

### 6.5. Example Mapping: story, rule, example, question

Một kỹ thuật có thể dùng trong BDD Discovery là **Example Mapping**:

| Thành phần | Ví dụ |
|---|---|
| **Story** | Người học cần biết tiến độ đã lưu tin cậy chưa |
| **Rule** | Chỉ nói “Đã lưu” khi có xác nhận hợp lệ |
| **Example** | Backend báo thành công và dữ liệu đọc lại được |
| **Counterexample** | Backend báo lỗi; UI không được báo thành công |
| **Rule** | Không đoán kết quả khi request timeout |
| **Example** | Mất phản hồi; UI dùng trạng thái chưa xác định |
| **Question** | Nếu backend đã lưu nhưng response mất, đối soát sau khi nối lại ra sao? |

Nhóm có thể dùng giấy, bảng online hoặc đoạn ghi chú ngắn. **Không cần công cụ chuyên biệt** để đạt được hội thoại có ích.

### 6.6. BDD không bắt buộc mọi scenario là end-to-end

BDD có thể mô tả quy tắc miền, hành vi API, hoặc luồng người dùng. Chọn mức thực thi tương ứng:

- Quy tắc tính phí có thể kiểm chứng ở component/domain level.
- Quy tắc quyền truy cập cần integration/security tests phù hợp.
- Luồng “mở bài → lưu → mở lại” có thể cần một số E2E tests chọn lọc.

Tập trung vào **hành vi có nghĩa**, không phải tạo ra một kho scenario rất lớn rồi bỏ qua chúng vì thời gian chạy quá lâu.

## 7. BDD và ATDD giao nhau, nhưng không hoàn toàn giống nhau

### 7.1. Một ví dụ có thể phục vụ cả hai

Ví dụ: “Khi backend xác nhận lưu thất bại, UI không báo đã lưu thành công.”

- Nó là **kết quả BDD** nếu xuất phát từ cuộc thảo luận về ý nghĩa “đã lưu”, nơi các bên hiểu và đặt tên cùng một quy tắc.
- Nó có thể là **acceptance test của ATDD** nếu được các bên thống nhất trước khi code là điều kiện cần để chấp nhận PBI.

Không cần viết hai test trùng nhau chỉ để một cái mang tên BDD và một cái mang tên ATDD.

### 7.2. Sự khác biệt ở điểm nhấn

| Câu hỏi | BDD nổi bật | ATDD nổi bật |
|---|---|---|
| Vì sao hội thoại bắt đầu? | Khám phá hành vi, từ ngữ, giả định, điều chưa biết | Chốt tiêu chí đủ để một khả năng được chấp nhận |
| Kết quả ban đầu | Quy tắc, ví dụ, ngôn ngữ chung, câu hỏi mới | Ví dụ chấp nhận rõ và kiểm chứng được |
| Phạm vi | Từ quy tắc miền nhỏ tới hành trình người dùng | Chủ yếu theo PBI/feature/capability cần nghiệm thu |
| Có nhất thiết Gherkin? | Không | Không |
| Có nhất thiết UI test? | Không | Không |
| Mối liên hệ TDD | Ví dụ hành vi định hướng code cần tạo | Acceptance tests cấp cao có thể dẫn tới các vòng TDD nhỏ |

Một nhóm có thể dùng cách **outside-in**: bắt đầu bằng ví dụ chấp nhận cấp cao, sau đó dùng TDD ở các thành phần để làm hành vi cấp cao đạt. Nhưng đây không phải thứ tự cứng cho mọi công việc.

### 7.3. Sơ đồ kết hợp

~~~mermaid
flowchart TD
    P["Product Goal / vấn đề người dùng"] --> D["BDD Discovery: quy tắc, ví dụ, ngôn ngữ"]
    D --> A["ATDD: ví dụ chấp nhận trước implementation"]
    A --> F["Acceptance scenario chưa đạt"]
    F --> T["TDD: Red → Green → Refactor các hành vi nhỏ"]
    T --> I["CI, contract/integration tests"]
    I --> Q{"Acceptance tests và DoD đạt?"}
    Q -->|"Chưa"| T
    Q -->|"Có"| N["Increment tích hợp có thể sử dụng"]
    N --> O["Phản hồi người dùng và outcome"]
    O --> D
~~~

Vòng này là **một cách mô hình hóa việc kết hợp**, không phải quy trình bắt buộc. Nhóm có thể quay lại Discovery bất kỳ khi nào tìm thấy ví dụ chưa rõ, hoặc điều chỉnh acceptance test khi có quyết định nghiệp vụ mới.

## 8. Không nhầm phương pháp với tầng kiểm thử

### 8.1. Bốn trục độc lập

| Trục | Những lựa chọn thường gặp | Câu hỏi phân biệt |
|---|---|---|
| **Mục đích** | Thiết kế code, xác nhận chấp nhận, tìm lỗi, bảo vệ hồi quy | “Tại sao chúng ta kiểm tra việc này?” |
| **Thời điểm** | Trước khi code, trong lúc phát triển, sau triển khai | “Phản hồi có đến đủ sớm không?” |
| **Cấp kiểm tra** | Unit, component, contract, integration, E2E, exploratory | “Kiểm tra qua những ranh giới nào?” |
| **Biểu đạt/công cụ** | Java/JUnit, Gherkin, bảng quyết định, API test, thao tác thủ công | “Ai có thể đọc và tin kết quả?” |

**Ví dụ với cùng một quy tắc:**

- **BDD:** xác định “đã lưu” phải có xác nhận hợp lệ và trường hợp chưa biết không được báo thành công.
- **ATDD:** xác định trước ví dụ chấp nhận về UI–API khi backend lỗi.
- **TDD:** viết test nhỏ cho service chuyển trạng thái kết quả.
- **Contract test:** xác nhận API trả đúng ý nghĩa trạng thái để UI hiểu nhất quán.
- **Integration test:** xác minh chuỗi UI–API–storage khi nơi lưu từ chối.
- **Exploratory test:** thử ngắt mạng ở thời điểm bất thường, bấm lặp, đổi thiết bị.
- **Production observation:** xem tỉ lệ lỗi lưu và mất tiến độ thực tế.

Không hoạt động nào tự thay thế tất cả các hoạt động khác. **Test xanh không đồng nghĩa với Product Goal đã đạt**.

### 8.2. Tránh mọi acceptance test trở thành browser test

Nếu mọi quy tắc đều chạy qua trình duyệt, cơ sở dữ liệu, API và nhiều dịch vụ, bộ test thường:

- Chậm cho vòng Red–Green–Refactor.
- Dễ thất bại do môi trường hoặc dữ liệu không ổn định.
- Khó chỉ ra nguyên nhân đúng khi có lỗi.
- Tốn bảo trì khi giao diện thay đổi nhưng hành vi nghiệp vụ không đổi.

Cách thực dụng thường là **nhiều kiểm tra nhanh ở mức nhỏ**, **contract/integration tests** ở ranh giới quan trọng và **một số E2E tests** cho hành trình người dùng rủi ro cao. Tỉ lệ cụ thể tùy sản phẩm, không có công thức áp chung cho mọi đội.

### 8.3. Tự động hóa không thay toàn bộ kiểm tra của con người

Phần mềm cần thêm **exploratory testing**, thử nghiệm khả năng sử dụng và tiếp cận, review bảo mật, kiểm tra vận hành hoặc quan sát người dùng tùy mức rủi ro. Một acceptance test tự động chỉ chứng minh hành vi được mô tả trong điều kiện đã kiểm tra, không chứng minh mọi trường hợp thực tế.

## 9. Tình huống xuyên suốt: từ yêu cầu lưu tiến độ tới Increment có thể sử dụng

### 9.1. Product Goal và vấn đề người dùng

Một Scrum Team xây nền tảng học trực tuyến có **Product Goal**:

> “Người học có thể bắt đầu, tiếp tục và hoàn thành bài học mà không bị mất tiến độ trong các điều kiện được sản phẩm hỗ trợ.”

Người dùng báo rằng khi mạng yếu, giao diện đôi khi hiển thị “Đã lưu”, nhưng mở lại bài thì tiến độ chưa được cập nhật. Trong một vài trường hợp, thử lại nhiều lần còn khiến người học không biết tiến độ nào là mới nhất.

Product Owner đưa PBI:

> **User story:** “Là người học đang học dở, tôi muốn biết chắc tiến độ đã lưu thành công hay chưa, để có thể rời bài và quay lại mà không mất công sức.”

**Sprint Goal minh họa:** người học có thể mở bài đầu và nhận trạng thái lưu tiến độ đáng tin cậy trong những trường hợp đã xác định.

Nhóm thống nhất không cố giải quyết toàn bộ bài toán đồng bộ nhiều thiết bị và offline dài ngày trong một Sprint khi những chính sách đó còn chưa rõ.

### 9.2. BDD Discovery làm lộ giả định quan trọng

Ba góc nhìn cùng thảo luận:

| Góc nhìn | Ví dụ câu hỏi | Điều làm rõ |
|---|---|---|
| Product Owner | Khi nào người học có thể an tâm rời bài? | Chỉ khi tiến độ đã được xác nhận lưu theo hợp đồng |
| Developer | Một request được gửi có phải bằng chứng đã lưu? | Không; cần phân biệt gửi yêu cầu và ghi dữ liệu |
| Tester | Nếu kết nối ngắt trước phản hồi, ta biết kết quả không? | Có thể không; cần trạng thái chưa xác định |
| Vận hành | Làm sao chẩn đoán lỗi mà không ghi dữ liệu cá nhân không cần thiết? | Cần kiểm tra log/tracing và chính sách truy cập |

Nhóm thống nhất ngôn ngữ chính:

- **Đang lưu:** thao tác đang được xử lý.
- **Đã lưu:** có xác nhận lưu hợp lệ.
- **Lưu thất bại:** có xác nhận thất bại.
- **Chưa xác định:** không đủ bằng chứng kết luận thành công hoặc thất bại.

Những điều còn cần làm rõ, như đối soát khi mất phản hồi, được ghi lại. Không tự suy luận rằng timeout luôn có nghĩa là không ghi được dữ liệu.

### 9.3. ATDD chốt những ví dụ có thể chấp nhận

Với lát cắt đầu, các bên thống nhất ba điều kiện:

1. **Thành công:** sau khi API xác nhận lưu, UI có thể hiển thị “Đã lưu”; dữ liệu đã xác nhận phải đọc lại phù hợp.
2. **Thất bại:** khi backend trả lỗi rõ ràng, UI không thông báo thành công giả và đưa hướng xử lý.
3. **Chưa xác định:** khi kết nối gián đoạn khiến chưa có kết quả tin cậy, UI không khẳng định đã lưu; thể hiện trạng thái theo quy tắc đã thống nhất.

Một số kiểm tra có thể chạy ở service/integration level; một luồng UI được chọn để xác minh người học thực sự nhìn thấy trạng thái đúng.

Những acceptance examples này được thống nhất **trước implementation**. Nếu vẫn chưa có quy tắc xử lý dữ liệu nhiều thiết bị, nhóm giới hạn phạm vi thử thay vì viết test khẳng định một chính sách chưa được quyết định.

### 9.4. TDD hiện thực từng quy tắc nhỏ

Developers bắt đầu bằng bài test thất bại cho trường hợp nơi lưu từ chối; sau đó viết code để test xanh. Tiếp theo là test cho kết quả thành công. Sau khi có quyết định cho trạng thái chưa xác định, họ bổ sung test và thiết kế kiểu kết quả phù hợp hơn một boolean.

Một hướng phát triển theo vòng ngắn:

~~~text
RED 1:
  Khi repository trả thất bại, service không được trả CONFIRMED.
GREEN 1:
  Chuyển kết quả thất bại thành FAILED.
REFACTOR 1:
  Làm rõ tên trạng thái và tách dependency cho dễ kiểm thử.

RED 2:
  Khi repository xác nhận thành công, service trả CONFIRMED.
GREEN 2:
  Hiện thực nhánh xác nhận.
REFACTOR 2:
  Gỡ trùng lặp và giữ code dễ hiểu.

RED 3 (sau khi đã thống nhất hợp đồng):
  Khi kết quả không xác định, không được trả CONFIRMED.
GREEN 3:
  Biểu diễn trạng thái UNKNOWN hoặc cách tương đương phù hợp.
REFACTOR 3:
  Tách việc đối soát/hiển thị trạng thái khỏi quy tắc nghiệp vụ.
~~~

**TDD giúp quản lý thiết kế code**, còn acceptance tests đảm bảo việc ghép các thành phần giữ đúng nghĩa nghiệp vụ. Không nên dùng một unit test với fake repository làm bằng chứng rằng UI hoặc dữ liệu production đã hoạt động đúng.

### 9.5. Tích hợp, kiểm chứng và Definition of Done

| Cấp kiểm chứng | Điều cần nhìn thấy |
|---|---|
| Unit/component | Quy tắc chuyển trạng thái lưu đúng theo kết quả và dữ liệu đầu vào |
| Contract/API | UI và API dùng thống nhất ý nghĩa CONFIRMED, FAILED, UNKNOWN |
| Integration | Lưu thật trong môi trường thử, mô phỏng lỗi dịch vụ và phản hồi mất kết nối |
| End-to-end chọn lọc | Người học mở bài, yêu cầu lưu, nhìn thấy trạng thái đúng và mở lại được tiến độ đã xác nhận |
| Bảo mật/vận hành | Quyền dữ liệu được bảo vệ; log và cách ứng cứu theo tiêu chuẩn áp dụng |
| DoD | Thay đổi đã tích hợp và đạt chuẩn chất lượng chung của Increment |

Nếu acceptance tests của đường thành công đã qua nhưng một kiểm tra quyền truy cập bắt buộc vẫn đỏ, **PBI chưa đạt Definition of Done**. Scrum Team phải minh bạch phần chưa hoàn thành, điều chỉnh kế hoạch hoặc phạm vi khi cần, thay vì báo “Done” vì gần hết Sprint.

### 9.6. Sprint Review và kết quả sử dụng

Trong Sprint Review, nhóm trình bày Increment **thực sự đạt DoD** và mời stakeholder kiểm tra những hành vi có ý nghĩa. Nếu thử với người học cho thấy thông báo đúng hơn nhưng nhiều người vẫn không quay lại hoàn thành bài, nhóm cần tìm hiểu thêm về nội dung hoặc trải nghiệm học.

Một bộ tín hiệu minh họa:

| Tín hiệu | Câu hỏi |
|---|---|
| Tỷ lệ thao tác lưu lỗi theo định nghĩa | Có ít thất bại hơn trong điều kiện tương đương không? |
| Số báo cáo mất tiến độ đã xác minh | Người học có bớt phải làm lại không? |
| Lỗi hồi quy liên quan sau phát hành | TDD/CI và các test chấp nhận có bảo vệ phần thay đổi không? |
| Thời gian phản hồi CI và test flaky | Vòng phản hồi có đủ nhanh và tin cậy không? |
| Tỷ lệ người học quay lại bài | Thay đổi có gắn với giá trị sản phẩm không? |
| Tỷ lệ hoàn thành bài đầu | Product Goal có dấu hiệu tiến triển không? |

Không suy ra quan hệ nhân quả chỉ từ một đợt quan sát. Nếu lượng người dùng, nhóm thiết bị hoặc nguồn truy cập khác nhau, cần xem các yếu tố đó trước khi kết luận.

### 9.7. Những lớp phản hồi đã kết nối như thế nào?

| Bước | Cách tiếp cận nổi bật | Đầu ra hữu ích |
|---|---|---|
| Làm rõ ý nghĩa “đã lưu” | BDD | Ngôn ngữ, quy tắc, ví dụ và câu hỏi cần quyết định |
| Chốt điều kiện cho PBI | ATDD | Các acceptance examples có thể kiểm chứng |
| Hiện thực quy tắc xử lý trạng thái | TDD | Unit/component tests, code và refactoring |
| Kiểm tra hệ thống hoạt động chung | Các lớp kiểm thử bổ trợ | CI, contract/integration/E2E tests và chất lượng theo DoD |
| Kiểm tra kết quả với người dùng | Phản hồi Agile | Bằng chứng outcome, Product Backlog được thích ứng |

**TDD giúp xây phần code dễ đổi; ATDD giúp xác định thế nào là tính năng đúng; BDD giúp bảo đảm nhóm đang nói về cùng một hành vi.**

## 10. Scrum, XP và Kanban dùng ba cách tiếp cận như thế nào?

### 10.1. Trong Scrum

Scrum định nghĩa **Product Goal, Sprint Goal và Definition of Done**, chứ không bắt buộc dùng TDD, BDD hay ATDD.

Các điểm áp dụng có ích:

- **Product Backlog refinement:** trao đổi BDD/ATDD để chia nhỏ và làm rõ những PBI gần thời điểm thực hiện; refinement không phải một Scrum Event bắt buộc.
- **Sprint Planning:** Sprint Goal định hướng lựa chọn PBI; Developers xem acceptance criteria, rủi ro và cách kiểm tra để lập kế hoạch.
- **Trong Sprint:** Developers dùng TDD, CI và acceptance tests để tạo Increment; điều chỉnh Sprint Backlog theo thông tin mới, thương lượng phạm vi với Product Owner khi cần.
- **Daily Scrum:** kiểm tra tiến độ hướng Sprint Goal, không chỉ báo số unit tests đã viết.
- **Sprint Review:** kiểm tra Increment và phản hồi cùng các bên liên quan; không biến demo thành thủ tục hợp thức hóa công việc chưa đạt DoD.
- **Sprint Retrospective:** xem test nào quá chậm, yêu cầu nào gây hiểu nhầm và cải thiện cách phối hợp.

Theo Scrum Guide, **chất lượng không được giảm trong Sprint**. Có thể điều chỉnh phạm vi phù hợp để bảo vệ Sprint Goal, nhưng không gọi PBI đã Done khi chưa đáp ứng DoD.

### 10.2. Trong XP

XP nhấn mạnh **TDD, refactoring, simple design, pair programming, collective code ownership, CI, small releases và cộng tác với khách hàng**.

- TDD giúp tạo lưới an toàn cho refactoring.
- Pair programming hỗ trợ làm rõ hành vi và chia sẻ kiến thức kiểm thử.
- CI cho biết sớm khi thay đổi nhỏ phá vỡ tích hợp.
- Small releases cho phản hồi sử dụng, giúp bổ sung câu hỏi BDD hoặc acceptance criteria ATDD mới.
- Nhịp làm việc bền vững giúp nhóm duy trì các vòng phản hồi thay vì cắt bỏ test khi có áp lực thời hạn.

Không phải mọi thay đổi đều cần pairing liên tục hoặc một file Gherkin. Chọn thực hành để giải quyết rủi ro cụ thể, không phải để tăng số mục đã “áp dụng XP”.

### 10.3. Trong Kanban

Kanban có thể làm rõ workflow từ **làm rõ nhu cầu → thực hiện → review → kiểm thử → hoàn thành**, các điểm tắc và sự biến động.

Nhóm quan sát:

- **WIP:** có bao nhiêu việc đã bắt đầu nhưng chưa hoàn thành?
- **Work item age:** PBI đang chờ làm rõ acceptance examples hoặc chờ môi trường thử bao lâu?
- **Cycle time:** từ khi bắt đầu tới lúc đạt Done mất bao lâu?
- **Throughput:** mỗi tuần có bao nhiêu hạng mục thực sự hoàn tất?

Khi nhiều PBI bị chặn ở bước kiểm thử tích hợp, giới hạn WIP có thể giúp nhóm **hoàn tất việc đang mở trước khi nhận thêm**. Nếu nguyên nhân là acceptance criteria mơ hồ, bổ sung test tự động đơn thuần chưa đủ; cần cải thiện hội thoại BDD/ATDD.

Các phép đo luồng không tự đo giá trị người dùng. Chúng hỗ trợ phát hiện thời gian chờ, không thay cho Product Goal.

## 11. Khi nào nên ưu tiên TDD, BDD, ATDD?

### 11.1. Ưu tiên TDD khi vấn đề nằm trong thiết kế code và hồi quy

Những tình huống thường phù hợp:

- Quy tắc tính phí, giảm giá, điểm thưởng hoặc chuyển trạng thái có ví dụ rõ.
- Code khó refactor vì thiếu bài test bảo vệ.
- Module có nhiều nhánh quyết định và muốn phản hồi nhanh sau mỗi thay đổi.
- Logic cần thiết kế độc lập với database/API để kiểm tra trong vài giây.

Ví dụ: quy tắc tính giá không cho tổng phải trả âm. Tuy nhiên, **quy tắc nghiệp vụ có đúng hay không vẫn phải được xác nhận**, nhất là khi có voucher hoàn tiền hoặc giá trị âm mang ý nghĩa riêng.

### 11.2. Ưu tiên ATDD khi điều kiện chấp nhận còn khác nhau

Những tình huống thường phù hợp:

- Có tranh luận “thế nào là xong?” giữa Product Owner, Developers và Tester.
- PBI có nhiều trường hợp lỗi hoặc rủi ro nghiệp vụ.
- Feature liên quan hợp đồng API hoặc nhiều nhóm cần cách kiểm chứng nhất quán.
- Cần làm rõ trường hợp phải đạt trước khi phân rã thành code.

Ví dụ: gửi lại email xác thực với giới hạn gửi lặp, thất bại dịch vụ và trạng thái người dùng đã xác thực.

### 11.3. Ưu tiên BDD khi ngôn ngữ và quy tắc chưa rõ

Những tình huống thường phù hợp:

- Một thuật ngữ nghiệp vụ mang nhiều nghĩa: “đã thanh toán”, “đã giao”, “đã lưu”.
- Nhiều stakeholder có yêu cầu hoặc cách hiểu mâu thuẫn.
- Các trường hợp biên lộ ra quy tắc chưa hề được thống nhất.
- Nhóm cần tài liệu ví dụ dễ đọc và được cập nhật khi sản phẩm đổi.

Ví dụ: hệ thống thanh toán nhận timeout nhưng giao dịch có thể đã được ghi. BDD giúp hỏi đúng các điều kiện trước khi có một acceptance test chính xác.

### 11.4. Khi nào kết hợp cả ba?

Một khả năng có UI, API, dữ liệu và ràng buộc an toàn quan trọng thường có lợi khi:

1. BDD làm rõ hành vi và thuật ngữ.
2. ATDD tạo các ví dụ chấp nhận đã được thống nhất trước code.
3. TDD hiện thực từng quy tắc nhỏ theo vòng ngắn.
4. CI và kiểm thử qua ranh giới phù hợp bảo vệ chất lượng.
5. Phản hồi sản phẩm xác nhận kết quả với người dùng.

**Không biến thành quy trình nặng nề cho mọi sửa nhỏ.** Mức chi tiết phải tương xứng độ rủi ro, khả năng đảo ngược và mức bất định của yêu cầu.

## 12. Sai lầm và ngộ nhận phổ biến

| Ngộ nhận | Vì sao nguy hiểm? | Cách hiểu phù hợp |
|---|---|---|
| “TDD là viết unit test sau khi code xong.” | Mất vòng phản hồi dẫn dắt thiết kế | TDD dùng Red–Green–Refactor |
| “TDD chỉ là unit testing.” | Nhầm cách làm với mức kiểm thử | TDD thường dùng test nhỏ, nhưng có thể hỗ trợ ngoài-vào-trong |
| “Coverage 100% nghĩa là code không lỗi.” | Test có thể bỏ sót hành vi và tích hợp | Xem test có ý nghĩa, chất lượng và rủi ro thực |
| “BDD chỉ cần file Gherkin hoặc Cucumber.” | Không có Discovery và ngôn ngữ chung | BDD coi hội thoại và ví dụ là trung tâm |
| “BDD chỉ dùng cho UI.” | Bỏ qua quy tắc nghiệp vụ và API | Mô tả hành vi ở cấp phù hợp |
| “ATDD là QA viết test cuối Sprint.” | Tiêu chí vẫn được làm rõ quá muộn | Các bên thống nhất ví dụ trước implementation |
| “ATDD luôn là browser E2E test.” | Test chậm, giòn và khó chẩn đoán | Kiểm chứng ở ranh giới có ý nghĩa |
| “BDD và ATDD phải có hai bộ test riêng.” | Trùng lặp, tốn bảo trì | Tái sử dụng ví dụ nếu phục vụ cả khám phá và chấp nhận |
| “BDD và ATDD hoàn toàn giống nhau.” | Quên điểm nhấn về khám phá ngôn ngữ hoặc chốt điều kiện | Phân biệt mục tiêu của hội thoại và kiểm chứng |
| “Acceptance tests đủ rồi, không cần unit tests.” | Phản hồi code chậm và refactoring khó | Kết hợp nhiều tầng theo rủi ro |
| “Unit tests xanh nên PBI đã Done.” | Bỏ qua DoD, tích hợp và bảo mật | Xác nhận Increment đạt chuẩn chất lượng |
| “Mọi scenario phải tự động hóa.” | Nhiều test giòn, chi phí không đáng | Chọn scenario giá trị cao và cách kiểm chứng phù hợp |
| “Test tự động thay Tester.” | Mất exploratory testing và hiểu biết nghiệp vụ | Kết hợp người và tự động hóa |
| “Nếu yêu cầu chưa rõ cứ tự viết test.” | Đóng băng giả định sai vào code | Ghi câu hỏi, tìm người có thẩm quyền xác nhận |
| “Đổi yêu cầu nghĩa là test cũ phải giữ nguyên.” | Tài liệu/test không còn đúng nghiệp vụ | Cập nhật ví dụ và test theo quyết định minh bạch |
| “Để kịp deadline có thể giảm DoD.” | Giao sản phẩm rủi ro và báo Done sai | Điều chỉnh phạm vi/ngày, bảo vệ chất lượng |

## 13. Đo lường hiệu quả mà không biến test thành KPI

Một nhóm có thể viết nhiều test hơn nhưng vẫn giao chậm hoặc sai nhu cầu. Không nên chỉ dựa trên **số lượng test, coverage, scenario hoặc số giờ pairing**.

| Loại tín hiệu | Ví dụ | Câu hỏi |
|---|---|---|
| **Hiểu yêu cầu** | PBI phải mở lại vì hiểu sai quy tắc, thời gian chờ làm rõ | BDD/ATDD có giảm hiểu nhầm trước code không? |
| **Phản hồi kỹ thuật** | Thời gian CI, độ ổn định test, lỗi hồi quy | TDD/test giúp biết và sửa sai sớm hơn không? |
| **Bảo trì test** | Test flaky, số test vỡ khi refactor không đổi hành vi | Test có phản ánh behavior hay bám chi tiết cài đặt? |
| **Dòng công việc** | WIP, work item age, cycle time, throughput | Việc có tiến tới Done đều hơn không? |
| **Chất lượng sản phẩm** | Lỗi nghiêm trọng sau phát hành, thời gian khôi phục | Có giảm rủi ro lọt tới người dùng không? |
| **Kết quả người dùng** | Tỷ lệ học tiếp, hoàn thành bài, số báo mất tiến độ | Có tiến gần Product Goal không? |
| **Sức khỏe nhóm** | Quá tải review, áp lực làm thêm giờ, thời gian test | Cách làm có bền vững không? |

### 13.1. Ví dụ số liệu và cách đọc thận trọng

Giả sử một nhóm thử các hoạt động BDD/ATDD và TDD ở phần lưu tiến độ. Dữ liệu **hoàn toàn minh họa**:

| Chỉ báo | Trước | Sau | Lưu ý |
|---|---:|---:|---|
| PBI mở lại vì hiểu sai acceptance criteria | 6 | 2 | Cách tính và loại PBI có tương tự không? |
| Lỗi hồi quy lưu tiến độ sau phát hành | 8 | 3 | Số người dùng và thời gian quan sát có đổi không? |
| Thời gian phản hồi CI trung vị | 18 phút | 7 phút | Có vô hiệu hóa test quan trọng để chạy nhanh không? |
| Tỷ lệ người học quay lại hoàn thành bài | 27% | 30% | Có thay đổi nội dung hoặc nguồn người dùng đồng thời không? |

Các chỉ báo gợi ý hướng cải thiện nhưng **không chứng minh quan hệ nhân quả**. Cần xem mẫu, thời gian, định nghĩa sự kiện, thay đổi đồng thời và phản hồi định tính trước khi kết luận.

### 13.2. Thử nghiệm cải tiến có thể kiểm chứng

~~~text
Quan sát:
  PBI về lưu tiến độ hay phải mở lại vì mô tả trạng thái lỗi mơ hồ.
  Unit tests xanh nhưng lỗi tích hợp vẫn xuất hiện muộn.

Giả thuyết:
  BDD Discovery + ATDD acceptance examples trước code
  và TDD cho các quy tắc trạng thái nhỏ sẽ giảm hiểu nhầm.

Phạm vi:
  Một số PBI liên quan lưu dữ liệu trong các Sprint gần.

Hành động:
  - 15–30 phút trao đổi các ví dụ có rủi ro cao.
  - Chốt các trường hợp chấp nhận ở cấp kiểm tra phù hợp.
  - Dùng Red–Green–Refactor cho logic nhỏ.
  - Kiểm tra tích hợp trong CI và giữ DoD.

Tín hiệu:
  PBI mở lại, lỗi hồi quy, thời gian phản hồi CI, work item age.

Tín hiệu bảo vệ:
  Test flaky, tốc độ test, chất lượng sau phát hành, áp lực nhóm.

Xem lại:
  Trong Retrospective và sau khi có dữ liệu người dùng đủ tin cậy.

Quyết định:
  Giữ, sửa hoặc dừng cách làm theo bằng chứng.
~~~

## 14. Checklist thực hành

### Trước khi viết code

1. PBI đang giải quyết **vấn đề hoặc rủi ro sản phẩm** nào?
2. Có **thuật ngữ nghiệp vụ** nào đang được hiểu khác nhau?
3. Đã nêu **ví dụ thành công, thất bại và trường hợp biên quan trọng** chưa?
4. Có quy tắc chưa rõ cần Product Owner hoặc chuyên gia quyết định không?
5. Các **acceptance examples** đã đủ cụ thể để kiểm chứng trước khi xây chưa?
6. Có thể chia một **lát cắt nhỏ và có thể sử dụng** để nhận phản hồi sớm không?

### Khi hiện thực

7. Với logic phù hợp, có tạo vòng **Red–Green–Refactor** nhỏ không?
8. Các test có kiểm tra **hành vi** hay chỉ thứ tự gọi hàm và chi tiết nội bộ?
9. Có kiểm thử **contract/integration** ở ranh giới quan trọng không?
10. CI có phản hồi nhanh, ổn định và được xử lý khi đỏ không?
11. Nếu phát hiện quy tắc mới, nhóm có quay lại **BDD/ATDD** làm rõ thay vì tự suy đoán không?

### Khi gọi một PBI Done

12. Acceptance examples quan trọng trong phạm vi đã được xác minh chưa?
13. Phần mới có **được tích hợp và đạt Definition of Done** không?
14. Những trường hợp về bảo mật, dữ liệu và vận hành bắt buộc có được kiểm tra đúng không?
15. Công việc chưa đạt chuẩn có được **báo đúng trạng thái** không?
16. Có kế hoạch quan sát **outcome người dùng** sau khi giao Increment không?
17. Ví dụ và test có được cập nhật theo phản hồi, tránh thành tài liệu lỗi thời không?

Checklist phục vụ ra quyết định, không phải giấy phép biến mỗi PBI thành một chuỗi cuộc họp, phê duyệt và hàng trăm kịch bản không cần thiết.

## 15. Bài tập vận dụng

### Bài tập 1 — Phân loại theo mục tiêu

Hãy phân loại hoạt động sau là **TDD, BDD, ATDD** hay kiểm thử bổ trợ:

1. Developer viết unit test thất bại cho quy tắc giá không âm rồi hiện thực code.
2. Product Owner, Tester và Developer thảo luận “đã thanh toán” nghĩa là gì khi đối tác trả timeout.
3. Nhóm thống nhất trước code ba ví dụ chấp nhận của chức năng gửi lại email kích hoạt.
4. Tester viết browser test sau khi tính năng hoàn thành để kiểm tra nút đăng nhập.
5. Nhóm viết nhiều scenario Gherkin nhưng chưa từng hỏi nghiệp vụ về trường hợp lỗi.
6. Developer refactor cấu trúc class sau khi test xanh rồi chạy lại test.

**Gợi ý:** (1) TDD; (2) BDD Discovery; (3) ATDD; (4) kiểm thử bổ trợ nhưng không tự là ATDD; (5) có cú pháp BDD nhưng thiếu khám phá; (6) một phần vòng TDD.

### Bài tập 2 — Ba lớp phản hồi cho một quy tắc thanh toán

Quy tắc: “Không báo thanh toán thành công khi cổng thanh toán chưa xác nhận kết quả hợp lệ.”

**Yêu cầu:**

1. Viết ba câu hỏi BDD Discovery làm rõ khi nào được nói “đã thanh toán”.
2. Viết ba acceptance examples theo ATDD: thành công, thất bại rõ và timeout.
3. Chọn hai test nhỏ cho TDD ở service.
4. Nêu một contract/integration test cần có.
5. Giải thích vì sao **không tự động thử lại** nếu chưa có quy tắc idempotency hoặc đối soát với đối tác.

### Bài tập 3 — Sửa scenario quá thiên về giao diện

~~~gherkin
Scenario: Thanh toán
  Given tôi đang ở /checkout
  When tôi bấm #pay
  Then .toast-green hiển thị
~~~

Hãy chỉ ra ít nhất ba điểm mơ hồ; viết lại thành scenario **có kết quả nghiệp vụ** và thêm phản ví dụ về thất bại khi bên thanh toán từ chối.

**Gợi ý:** trọng tâm là trạng thái thanh toán đã được xác nhận, không chỉ tên phần tử hoặc màu thông báo.

### Bài tập 4 — Phân biệt acceptance test và Definition of Done

PBI: “Người học được gửi lại email kích hoạt khi chưa nhận thư.”

1. Viết acceptance criteria cho gửi thành công, yêu cầu lặp và dịch vụ gửi lỗi.
2. Đề xuất hai acceptance tests ở API/component level, không cần browser.
3. Nêu bốn điều kiện DoD về tích hợp, hồi quy, bảo mật và vận hành.
4. Giải thích vì sao acceptance tests xanh nhưng kiểm tra quyền truy cập bắt buộc đỏ thì PBI vẫn chưa Done.

### Bài tập 5 — Thiết kế vòng TDD cho phép tính

Một ứng dụng bán vé có quy tắc minh họa: giá cuối không được âm, giá gốc và mức giảm tính bằng đơn vị tiền nhỏ nhất.

1. Viết ba ví dụ với giảm ít hơn, bằng và lớn hơn giá gốc.
2. Mô tả ba vòng Red–Green–Refactor.
3. Nêu điều cần làm rõ về đầu vào âm và kiểu dữ liệu tiền.
4. Cho biết vì sao unit tests đúng chưa chứng minh quy trình mua vé hoạt động end-to-end.

### Bài tập 6 — Test xanh nhưng người dùng vẫn mất tiến độ

Một nhóm có coverage 90%, CI xanh, nhưng khi mất mạng UI thường báo “Đã lưu” sai.

Hãy thiết kế một buổi BDD Discovery ngắn, hai acceptance examples ATDD, các unit tests TDD và một integration test cần có. Nêu một tín hiệu quan sát sau phát hành.

**Gợi ý:** coverage không phản ánh đầy đủ **chất lượng của các ví dụ được kiểm tra**.

### Bài tập 7 — Chia lát cắt ngoài-vào-trong

Epic: “Đồng bộ tiến độ giữa mọi thiết bị, offline hoàn toàn, quản lý xung đột và lịch sử.”

Chia thành ba lát cắt có giá trị. Với lát đầu, điền:

~~~text
Product Goal:
Người dùng và kết quả mong đợi:
Điều đã biết / chưa rõ:
Ví dụ BDD Discovery:
Acceptance examples ATDD:
Các test TDD nhỏ:
Contract/integration/E2E checks:
Definition of Done:
Điều cố ý chưa làm:
Phản hồi cần thu thập:
~~~

### Bài tập 8 — Lập thử nghiệm cải tiến cho đội

Một đội gặp nhiều PBI mở lại vì hiểu sai yêu cầu, test chậm và refactor khó. Hãy thiết kế thử nghiệm trong vài Sprint kết hợp **BDD Discovery có mục đích + ATDD chọn lọc + TDD cho quy tắc rủi ro**.

~~~text
Vấn đề và bằng chứng nền:
Loại PBI thử nghiệm:
Ai tham gia Discovery và vì sao:
Cách ghi rule / example / question:
Ví dụ chấp nhận và cấp kiểm tra:
Những quy tắc nhỏ cần TDD:
CI và cách xử lý test flaky:
Chỉ số hiểu sai, lỗi hồi quy, cycle time:
Tín hiệu bảo vệ chất lượng / tải công việc:
Điểm xem lại và điều kiện giữ / sửa / dừng:
~~~

**Tự đánh giá:** bạn có thể giải thích **vì sao cần từng cách tiếp cận và chúng hỗ trợ nhau ra sao**, thay vì chỉ liệt kê các công cụ đã dùng hay không?

## 16. Tổng kết

Trong phát triển phần mềm Agile, TDD, BDD và ATDD cùng thúc đẩy **làm rõ sớm, kiểm chứng sớm và thay đổi an toàn hơn**, nhưng khác nhau ở trọng tâm:

1. **TDD** dẫn dắt **thiết kế và hiện thực code** bằng vòng Red–Green–Refactor; thường dùng test nhỏ, phản hồi nhanh, không chỉ unit test.
2. **ATDD** thống nhất **điều kiện và ví dụ chấp nhận trước implementation**; không bắt buộc các ví dụ phải kiểm chứng qua browser.
3. **BDD** thúc đẩy **hội thoại khám phá quy tắc, ngôn ngữ và hành vi**; Given–When–Then chỉ là một cách diễn đạt.
4. **BDD và ATDD giao nhau:** ví dụ nghiệp vụ có thể đồng thời là điều kiện chấp nhận; không cần nhân đôi test chỉ vì khác tên phương pháp.
5. **TDD hỗ trợ ATDD:** những vòng code nhỏ giúp các acceptance scenarios cấp cao đạt mà vẫn dễ refactor.
6. **Cấp độ kiểm thử là trục khác:** unit, component, contract, integration, E2E và exploratory kiểm tra các ranh giới khác nhau; không gắn một cấp duy nhất với một phương pháp.
7. **Definition of Done bảo vệ chất lượng Increment:** không đánh đồng test xanh với Done hoặc outcome người dùng.
8. **Kết hợp theo bối cảnh:** Scrum giữ mục tiêu và chuẩn hoàn thành, Kanban giúp nhìn dòng công việc, XP tăng cường chất lượng kỹ thuật và phản hồi.

> **Câu hỏi ghi nhớ:** “Nhóm đang cần hiểu rõ **hành vi nghiệp vụ** (BDD), thống nhất **điều kiện chấp nhận** (ATDD), hay thiết kế **code đúng, dễ thay đổi** (TDD) — và bằng chứng nào nối ba lớp này tới giá trị người dùng?”

### Tài liệu tham khảo

- Kent Beck, *Test-Driven Development: By Example* — nền tảng Red–Green–Refactor, test nhỏ và thiết kế phát triển dần.
- [Martin Fowler — Test-Driven Development](https://martinfowler.com/bliki/TestDrivenDevelopment.html) — tư duy và vòng phản hồi TDD.
- [Dan North — Introducing BDD](https://dannorth.net/introducing-bdd/) — bối cảnh phát triển tư duy Behavior-Driven Development.
- [Cucumber — Behavior-Driven Development](https://cucumber.io/docs/bdd/) — khám phá và đặc tả hành vi bằng cộng tác.
- [Cucumber — Gherkin Reference](https://cucumber.io/docs/gherkin/reference/) — cấu trúc Feature, Scenario, Given, When, Then.
- [The Scrum Guide (2020)](https://scrumguides.org/scrum-guide.html) — Product Goal, Sprint Goal, Increment, Definition of Done và kiểm tra/thích ứng.
- [The Kanban Guide](https://kanbanguides.org/) — Definition of Workflow, WIP, work item age, throughput và cycle time.
- [Manifesto for Agile Software Development](https://agilemanifesto.org/) và [12 Principles](https://agilemanifesto.org/principles.html) — phát triển thích ứng, hợp tác và sự xuất sắc kỹ thuật.
