# Phát triển có kiểm thử dẫn dắt và phản hồi tự động

## 1. Vì sao viết phần mềm thích ứng cần vòng phản hồi kỹ thuật ngắn?

Một Scrum Team phát triển nền tảng học trực tuyến muốn giúp học viên quay lại bài đang học. Nhóm thêm nút “Tiếp tục học”, sửa API trả về tiến độ và triển khai lên môi trường thử nghiệm. Giao diện chạy trong lần trình diễn đầu tiên, nhưng khi học viên đã hoàn thành bài cuối, API lại trả về một bài không tồn tại. Khi người khác dùng đường dẫn trực tiếp, hệ thống đôi lúc còn bỏ qua bước kiểm tra quyền.

Nếu các sai lệch này chỉ được phát hiện sau nhiều ngày hoặc sau khi phát hành, nhóm phải tìm lại ngữ cảnh, sửa nhiều phần, kiểm thử lại và có thể xử lý dữ liệu bị ảnh hưởng. **Chi phí của phản hồi đến muộn** không chỉ là thêm thời gian sửa lỗi: nó còn làm giảm khả năng thay đổi theo nhu cầu mới.

**Test-Driven Development (TDD, phát triển có kiểm thử dẫn dắt)** là một thực hành kỹ thuật gắn liền với Extreme Programming (XP). Với TDD, lập trình viên bắt đầu bằng một kiểm thử nhỏ mô tả hành vi mong muốn, quan sát nó thất bại đúng lý do, viết lượng mã vừa đủ để kiểm thử đạt, rồi cải thiện thiết kế trong khi giữ các kiểm thử xanh.

**Phản hồi tự động** mở rộng ý tưởng này ra khỏi máy cá nhân: bộ kiểm thử, kiểm tra chất lượng, tích hợp liên tục và quan sát sản phẩm cung cấp tín hiệu sớm khi một thay đổi vi phạm điều đã được xác nhận. Hai phần bổ trợ nhau:

- **TDD** hỗ trợ suy nghĩ về hành vi và thiết kế từng bước rất nhỏ.
- **Kiểm thử/tích hợp tự động** giúp phát hiện sai lệch lặp lại, kể cả khi nhiều người hoặc nhiều thành phần cùng thay đổi.
- **Phản hồi người dùng** tiếp tục giúp xác nhận rằng hành vi đúng về kỹ thuật có thật sự tạo giá trị sản phẩm hay không.

XP không chỉ là viết test trước; các thực hành cộng tác, tích hợp liên tục, refactoring và phát hành nhỏ tạo điều kiện để đội phát triển phần mềm **đáp ứng thay đổi mà vẫn giữ chất lượng**. Trong Agile, kỹ thuật này hỗ trợ user story, backlog, Scrum, Kanban và đo lường dòng công việc, chứ không thay thế quyết định sản phẩm.

> **Tư tưởng trọng tâm:** Kiểm thử dẫn dắt không phải cố đạt thật nhiều test case. Đó là cách tạo các vòng phản hồi đủ nhỏ để hiểu hành vi cần xây, nhận biết lỗi sớm và thay đổi thiết kế một cách tự tin.

## 2. TDD là gì, và điều gì không thuộc phạm vi của nó?

TDD thường theo vòng **Red – Green – Refactor**:

1. **Red:** viết một kiểm thử mới cho hành vi chưa được đáp ứng; chạy và thấy thất bại vì lý do mong đợi.
2. **Green:** viết thay đổi sản xuất nhỏ nhất hợp lý để kiểm thử mới cùng các kiểm thử liên quan đạt.
3. **Refactor:** cải thiện cấu trúc mã, loại bỏ trùng lặp, đặt tên rõ hơn, giữ nguyên hành vi đã được kiểm chứng.
4. **Repeat:** chọn trường hợp có ý nghĩa tiếp theo, lặp lại vòng nhỏ.

~~~mermaid
flowchart LR
    A["Một hành vi nhỏ cần xây"] --> B["RED: Viết test thất bại đúng lý do"]
    B --> C["GREEN: Viết mã đủ để test đạt"]
    C --> D["REFACTOR: Cải thiện thiết kế"]
    D --> E["Chạy lại bộ test phù hợp"]
    E --> F{"Còn trường hợp quan trọng?"}
    F -->|"Có"| A
    F -->|"Chưa"| G["Tích hợp, kiểm tra rộng hơn và nhận phản hồi"]
~~~

### Phân biệt ba trạng thái

| Giai đoạn | Việc cần thấy | Dấu hiệu sai |
| --- | --- | --- |
| **Red** | Test thất bại vì hành vi chưa đúng, chứng tỏ test có thể phát hiện sai lệch cần tìm | Test đỏ vì thiếu dependency, sai cấu hình hoặc lỗi môi trường không liên quan |
| **Green** | Hành vi mới đạt và không phá các hành vi đã kiểm tra trước đó | Chỉ sửa assertion cho xanh, bỏ qua trường hợp thất bại, hoặc vô hiệu hóa test |
| **Refactor** | Thiết kế rõ hơn mà hành vi quan sát được không đổi, test vẫn đạt | Thay đổi quy tắc nghiệp vụ mà không có test mới hoặc làm test phụ thuộc chi tiết triển khai |

Một vòng TDD có thể diễn ra trong vài phút, nhưng không có thời lượng chuẩn bắt buộc. TDD không yêu cầu viết toàn bộ bộ kiểm thử trước khi có mã; đó là **các bước nhỏ nối tiếp nhau**.

### TDD khác “viết test sau để tăng coverage”

Viết kiểm thử sau khi hoàn thành mã vẫn có giá trị, nhất là khi bổ sung hồi quy cho hệ thống cũ. Nhưng khi test được viết sau mọi quyết định thiết kế, nhóm dễ chỉ kiểm tra cách mã hiện đã hoạt động mà bỏ lỡ việc đặt câu hỏi “hành vi thật sự cần là gì?”.

Trong TDD, kiểm thử đầu tiên là một **phát biểu thực thi được về hành vi mong muốn**. Nó kéo theo cách thiết kế một giao diện dễ sử dụng và dễ kiểm tra, thay vì chỉ xác minh hiện trạng.

### TDD không tự bảo đảm phần mềm không có lỗi

Một bộ unit test xanh không chứng minh:

- API của hai dịch vụ đang tương thích trên môi trường tích hợp.
- Quyền truy cập đã được thực thi tại máy chủ trong mọi tình huống.
- Dữ liệu cũ và migration an toàn.
- Hệ thống chịu được tải thực tế.
- Người dùng thật hiểu giao diện và đạt outcome mong muốn.

Vì vậy, TDD cần được kết hợp với các cấp kiểm thử thích hợp, Definition of Done và phản hồi sản phẩm. **Một hành vi được kiểm thử đúng vẫn có thể là tính năng không ai cần.**

## 3. Chọn hành vi nhỏ từ user story trước khi bắt đầu code

Ví dụ user story của nền tảng học:

> Là học viên có quyền truy cập khóa học tuyến tính, tôi muốn mở bài tiếp theo sau phần đã hoàn tất để tiếp tục học mà không cần tìm trong danh sách.

Trước khi lập trình, nhóm cần làm rõ:

- **Khóa tuyến tính** có bắt buộc học theo thứ tự không?
- Một bài được tính là **đã hoàn tất** theo quy tắc nào?
- Nếu chưa hoàn thành bài nào, bài tiếp theo là bài mấy?
- Nếu đã hoàn tất bài cuối, hệ thống hiển thị điều gì?
- Người dùng không có quyền có thể truy cập đường dẫn trực tiếp không?
- Nguồn tiến độ có thể thiếu hoặc cập nhật từ nhiều thiết bị không?

Đối với ví dụ TDD dưới đây, ta **giả định** khóa học tuyến tính có ít nhất một bài, bài được đánh số từ 1 đến N, và tham số completedLessons là số bài đầu liên tiếp đã hoàn thành. Mục tiêu của hàm đơn thuần là xác định **số thứ tự bài tiếp theo**, chưa kiểm tra quyền học, truy vấn dữ liệu hay đồng bộ thiết bị.

Ranh giới này có chủ đích: một quy tắc thuần dễ được minh họa bằng unit test; những hành vi bên ngoài cần kiểm tra ở cấp cao hơn.

| Trường hợp | Dữ liệu đầu vào | Kết quả kỳ vọng |
| --- | --- | --- |
| Chưa học bài nào | completedLessons = 0, totalLessons = 3 | Bài 1 |
| Đã hoàn tất bài đầu | completedLessons = 1, totalLessons = 3 | Bài 2 |
| Đã hoàn tất bài cuối | completedLessons = 3, totalLessons = 3 | Không còn bài tiếp theo |
| Tiến độ vượt số bài | completedLessons = 4, totalLessons = 3 | Từ chối dữ liệu không hợp lệ |
| Khóa không có bài | completedLessons = 0, totalLessons = 0 | Từ chối đầu vào không hợp lệ theo hợp đồng ví dụ |

Những quy tắc này được chọn **để học TDD**, không phải chính sách bắt buộc cho mọi nền tảng học. Với khóa tự chọn, bài được khóa theo điều kiện hoặc dữ liệu tiến độ không tuần tự, nhóm phải thay đổi mô hình và kiểm thử.

## 4. Ví dụ Java/JUnit: đi từ Red sang Green rồi Refactor

### 4.1. Red – viết test cho hành vi dễ hiểu nhất

Giả sử dự án dùng Java và JUnit Jupiter (JUnit 5). Kiểm thử đầu tiên:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import java.util.OptionalInt;
import org.junit.jupiter.api.Test;

class LessonNavigatorTest {
    @Test
    void returnsNextLessonAfterFirstCompletedLesson() {
        LessonNavigator navigator = new LessonNavigator();

        OptionalInt actual = navigator.nextLesson(1, 3);

        assertEquals(OptionalInt.of(2), actual);
    }
}
~~~

Để quan sát test đỏ vì hành vi sai, ta có thể tạo một hiện thực tạm thời **chưa đáp ứng quy tắc**:

~~~java
import java.util.OptionalInt;

public final class LessonNavigator {
    public OptionalInt nextLesson(int completedLessons, int totalLessons) {
        return OptionalInt.empty();
    }
}
~~~

Khi chạy, test kỳ vọng bài 2 nhưng nhận “không còn bài”. Đó là **Red có ý nghĩa**. Nếu test thất bại chỉ vì chưa cài JUnit hoặc sai tên package, cần sửa môi trường trước khi dùng kết quả để suy luận về hành vi.

### 4.2. Green – mã nhỏ nhất đáp ứng trường hợp hiện tại

Ta có thể thay hiện thực bằng:

~~~java
import java.util.OptionalInt;

public final class LessonNavigator {
    public OptionalInt nextLesson(int completedLessons, int totalLessons) {
        return OptionalInt.of(completedLessons + 1);
    }
}
~~~

Test đầu tiên đã có thể xanh. Nhưng mã này **chưa đúng với bài cuối hoặc dữ liệu không hợp lệ**. TDD khuyến khích chọn tiếp trường hợp cụ thể thay vì suy rằng một kiểm thử xanh đã đủ.

### 4.3. Thêm test để dẫn dắt quy tắc biên

Mở rộng lớp test để kiểm tra nhiều trường hợp quan trọng:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import java.util.OptionalInt;
import org.junit.jupiter.api.Test;

class LessonNavigatorTest {
    private final LessonNavigator navigator = new LessonNavigator();

    @Test
    void startsAtFirstLessonWhenNoneCompleted() {
        assertEquals(OptionalInt.of(1), navigator.nextLesson(0, 3));
    }

    @Test
    void returnsNextLessonAfterFirstCompletedLesson() {
        assertEquals(OptionalInt.of(2), navigator.nextLesson(1, 3));
    }

    @Test
    void returnsNoNextLessonWhenCourseCompleted() {
        assertEquals(OptionalInt.empty(), navigator.nextLesson(3, 3));
    }

    @Test
    void rejectsProgressOutsideCourseBounds() {
        assertThrows(IllegalArgumentException.class,
                () -> navigator.nextLesson(4, 3));
        assertThrows(IllegalArgumentException.class,
                () -> navigator.nextLesson(-1, 3));
        assertThrows(IllegalArgumentException.class,
                () -> navigator.nextLesson(0, 0));
    }
}
~~~

Các kiểm thử được thêm **từng trường hợp trong các vòng TDD kế tiếp**; đoạn mã tổng hợp giúp người học nhìn toàn bộ hợp đồng sau khi khám phá các trường hợp biên.

### 4.4. Green và Refactor – hiện thực tổng quát, dễ đọc

~~~java
import java.util.OptionalInt;

public final class LessonNavigator {
    public OptionalInt nextLesson(int completedLessons, int totalLessons) {
        if (totalLessons < 1
                || completedLessons < 0
                || completedLessons > totalLessons) {
            throw new IllegalArgumentException("Invalid course progress");
        }

        if (completedLessons == totalLessons) {
            return OptionalInt.empty();
        }

        return OptionalInt.of(completedLessons + 1);
    }
}
~~~

Thiết kế này tránh trả về số bài không tồn tại và định nghĩa rõ trường hợp không còn bài bằng OptionalInt.empty(). Sau khi bộ kiểm thử xanh, có thể refactor tên biến, phân tách phần kiểm tra dữ liệu hoặc đổi cấu trúc hợp lý **mà không thay đổi hành vi**.

Chỉ refactor khi có lý do: nếu lớp đã rõ ràng, không cần tạo thêm nhiều tầng trừu tượng chỉ để chứng minh có bước Refactor.

### 4.5. Mỗi test nên chứng minh điều gì?

- **Trường hợp chính:** từ 1/3 tiến đến bài 2.
- **Trường hợp bắt đầu:** từ 0/3 mở bài 1.
- **Biên hoàn thành:** từ 3/3 không được tạo bài 4.
- **Dữ liệu bất hợp lệ:** tiến độ âm, vượt tổng số bài hoặc tổng bài không dương bị từ chối theo hợp đồng đã chọn.

Đây mới là **unit test của quy tắc thuần**. Nó chưa chứng minh học viên được cấp đúng quyền, lưu tiến độ chính xác hoặc giao diện xử lý OptionalInt.empty() phù hợp. Những phần còn lại cần một thiết kế kiểm thử khác.

## 5. Các đặc tính của kiểm thử hữu ích với TDD

Không phải mọi kiểm thử tự động đều là một phản hồi tốt. Một test dễ sai, chậm, thiếu rõ ràng hoặc phụ thuộc quá nhiều vào chi tiết triển khai sẽ làm nhóm mất niềm tin.

| Đặc tính | Ý nghĩa trong thực hành | Ví dụ |
| --- | --- | --- |
| **Có hành vi cụ thể** | Test giải thích rõ điều gì phải đúng | “Đã xong bài cuối thì không còn bài tiếp theo” |
| **Kết quả ổn định** | Cùng điều kiện đầu vào cho cùng kết quả | Không dựa vào thời gian hệ thống ngẫu nhiên |
| **Độc lập phù hợp** | Có thể chạy lại, không phụ thuộc thứ tự test khác | Mỗi test tự chuẩn bị dữ liệu cần thiết |
| **Nhanh ở cấp unit** | Vòng Red–Green–Refactor không bị gián đoạn lâu | Không cần khởi động toàn bộ ứng dụng để thử hàm thuần |
| **Thất bại dễ chẩn đoán** | Tên, assertion và thông báo chỉ ra hành vi bị vi phạm | Phân biệt “không có quyền” với “không có bài” |
| **Không gắn cứng vào nội bộ** | Refactor được mà test hành vi vẫn giữ giá trị | Không ép một phương thức private phải được gọi đúng số lần |
| **Có khả năng phát hiện lỗi thật** | Nếu hành vi sai có chủ đích, test phải đỏ | Thử thay đổi kết quả kỳ vọng để kiểm tra tín hiệu |
| **Dễ bảo trì** | Mẫu tạo dữ liệu và helper đủ rõ, không giấu nghiệp vụ | Tên dữ liệu diễn đạt trạng thái học viên |

### Mẫu Arrange – Act – Assert

Một cấu trúc dễ đọc là:

1. **Arrange:** chuẩn bị dữ liệu và đối tượng.
2. **Act:** thực hiện hành vi cần kiểm thử.
3. **Assert:** xác nhận kết quả có ý nghĩa.

Không có luật cứng mỗi test phải đúng một assertion. Nếu nhiều assertion cùng xác minh một hành vi thống nhất, chúng có thể hợp lý. Mặt khác, một test quá dài kiểm tra mọi trường hợp có thể khiến lỗi khó chẩn đoán.

### Kiểm thử dữ liệu biên thay vì chỉ “happy path”

Hãy nghĩ về **phân hoạch tương đương** và **giá trị biên**: không có bài, một bài, bài cuối, dữ liệu rỗng, trạng thái quyền thay đổi, request gửi lặp, dữ liệu đồng thời. Nhưng đừng tạo hàng nghìn test vô mục đích. Chọn trường hợp quan trọng theo **rủi ro sản phẩm** và những lỗi đã từng xuất hiện.

## 6. Test double: dùng fake, stub, mock đúng mức

Khi phần mềm gọi database, hệ thống gửi email hoặc dịch vụ thanh toán, unit test cần tạo điều kiện kiểm tra nhanh và có thể kiểm soát. **Test double** là tên chung cho những đối tượng thay thế hoặc mô phỏng một phụ thuộc trong quá trình kiểm thử.

| Loại thường gặp | Vai trò | Khi nên dùng |
| --- | --- | --- |
| **Stub** | Trả dữ liệu đã định để đưa hệ thống vào một tình huống | Giả lập trạng thái khóa đã đóng |
| **Fake** | Có hiện thực đơn giản nhưng dùng được, như repository trong bộ nhớ | Thử logic nghiệp vụ độc lập database thật |
| **Mock** | Dùng để xác nhận tương tác với cộng tác viên theo hợp đồng | Kiểm tra sự kiện thông báo được yêu cầu gửi |
| **Spy** | Ghi lại lời gọi/thông tin để kiểm tra sau | Xác minh một thao tác ngoài đã được yêu cầu theo quy tắc |

Các từ này có thể khác đôi chút giữa các thư viện. Quan trọng là **phân biệt điều đang kiểm tra**: kết quả nghiệp vụ hay cách các đối tượng trao đổi.

### Vấn đề của over-mocking

Giả sử test của chức năng ghi danh yêu cầu method validateUser() được gọi đúng một lần, rồi repository.save() đúng một lần, rồi notifier.send() đúng một lần. Khi nhóm refactor mà vẫn giữ hành vi bên ngoài, test có thể đỏ chỉ vì thứ tự hoặc cách gọi bên trong thay đổi.

Nếu điều người dùng quan tâm là **không tạo đăng ký trùng và chỉ cấp quyền sau khi thỏa điều kiện**, nên ưu tiên kiểm tra **trạng thái và kết quả quan sát được**. Chỉ kiểm tra tương tác khi bản thân tương tác đó có ý nghĩa theo hợp đồng, ví dụ phải phát một yêu cầu gửi email sau một sự kiện.

### Fake có thể che khác biệt với database thật

Repository trong bộ nhớ không mô phỏng hoàn toàn transaction, uniqueness constraint, lock, concurrent request hoặc lỗi kết nối. Một unit test xanh với fake không chứng minh hai yêu cầu ghi danh đồng thời sẽ không tạo hai bản ghi trùng. Với quy tắc quan trọng, cần **kiểm thử tích hợp với công nghệ lưu trữ thực tế hoặc môi trường đủ tương đương**.

## 7. TDD, ATDD và BDD: ba góc nhìn bổ trợ nhau

**TDD** hướng vào các bước nhỏ khi lập trình và thiết kế. **Acceptance Test-Driven Development (ATDD)** nhấn mạnh việc các bên cùng làm rõ tiêu chí chấp nhận trước khi triển khai. **Behavior-Driven Development (BDD)** nhấn mạnh mô tả hành vi thông qua ngôn ngữ chung và các ví dụ có thể kiểm tra. Có thể áp dụng chúng cùng nhau, nhưng không nên dùng ba tên gọi như đồng nghĩa hoàn toàn.

| Cách tiếp cận | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| **TDD** | Một thay đổi nhỏ của mã phải biểu hiện hành vi nào? | Quy tắc nextLesson(3,3) trả “không còn bài” |
| **ATDD** | Product Owner, Developers và người kiểm thử thống nhất story thành công thế nào? | Học viên có quyền mở được bài tiếp theo; người ngoài bị chặn |
| **BDD** | Có thể diễn đạt tình huống nghiệp vụ bằng ví dụ chung dễ hiểu không? | Given – When – Then cho luồng tiếp tục học |

### Ví dụ Gherkin của cùng user story

~~~gherkin
Feature: Tiếp tục học trên nền tảng khóa học

  Scenario: Học viên có quyền mở bài tiếp theo
    Given học viên đã đăng nhập và có quyền học khóa tuyến tính
    And học viên đã hoàn tất bài đầu trong tổng ba bài
    When học viên chọn "Tiếp tục học" trên trang khóa
    Then hệ thống mở bài thứ hai

  Scenario: Học viên đã hoàn tất bài cuối
    Given học viên có quyền học và đã hoàn tất cả ba bài
    When học viên mở trang khóa
    Then hệ thống hiển thị trạng thái hoàn thành
    And không điều hướng đến bài thứ tư

  Scenario: Người dùng không có quyền
    Given người dùng không có quyền học khóa
    When người dùng gửi yêu cầu mở liên kết trực tiếp đến một bài
    Then máy chủ từ chối truy cập nội dung bị hạn chế
~~~

Những ví dụ này là **acceptance criteria**, không bắt buộc tất cả đều phải được thực thi qua trình duyệt. Có thể xác minh phần nghiệp vụ ở API/service test và dành một số luồng đầu-cuối cho kiểm tra trải nghiệm. Cần tránh việc có nhiều bài test trùng nhau ở mọi tầng mà không tăng giá trị phát hiện lỗi.

### Từ acceptance criteria đến các vòng TDD

Một ví dụ “học viên đã hoàn tất ba bài” có thể được phân rã:

1. Unit test quy tắc xác định không còn bài tiếp theo.
2. Service test chuyển trạng thái nghiệp vụ sang kết quả thích hợp.
3. API integration test kiểm tra xác thực/quyền và phản hồi HTTP phù hợp.
4. UI test quan trọng kiểm tra thông báo hoàn thành và không hiển thị đường dẫn sai.

Đây là **cách chọn tầng test theo rủi ro**, không phải luật mỗi acceptance criterion phải tạo bốn bài kiểm thử.

## 8. Phản hồi tự động qua các lớp kiểm thử

Một hệ thống phản hồi tốt không chỉ chạy unit test. Nó đặt các phép kiểm tra vào những vị trí phù hợp để lỗi xuất hiện **gần thời điểm thay đổi** và dễ tìm nguyên nhân.

| Cấp/loại kiểm tra | Bảo vệ điều gì? | Đặc điểm và giới hạn |
| --- | --- | --- |
| **Unit test** | Logic nhỏ, biên, quy tắc và chuyển trạng thái | Nhanh, chính xác, nhưng thường không thấy lỗi tích hợp |
| **Component/service test** | Một dịch vụ theo hợp đồng công khai, có phụ thuộc được kiểm soát | Phát hiện nhiều lỗi hơn unit, nhưng có thể chưa giống môi trường đầy đủ |
| **Integration test** | Giao tiếp với database, queue, cache, hệ thống ngoài | Quan trọng với transaction/dữ liệu; cần môi trường đáng tin |
| **Contract test** | Thỏa thuận giữa bên cung cấp và sử dụng API/sự kiện | Giảm lỗi không tương thích khi nhiều nhóm thay đổi |
| **End-to-end test** | Hành trình người dùng qua nhiều thành phần | Có giá trị cho luồng cốt lõi nhưng thường chậm và dễ nhạy môi trường |
| **Security checks** | Rủi ro phân quyền, dữ liệu nhạy cảm, phụ thuộc và cấu hình | Chọn phương pháp theo threat model/ràng buộc |
| **Performance/reliability checks** | Độ trễ, khả năng chịu tải và phục hồi | Cần mô hình tải/tiêu chí phù hợp, không thay thế test chức năng |
| **Static analysis/build checks** | Lỗi biên dịch, quy ước chất lượng, một số vấn đề mã | Nhanh nhưng không chứng minh hành vi đúng |

### Kim tự tháp kiểm thử là gợi ý, không phải quota

Một chiến lược phổ biến là nhiều test nhanh ở tầng thấp, ít test đầu-cuối hơn và chọn các kiểm thử tích hợp ở những ranh giới có rủi ro. Điều quan trọng hơn hình dạng sơ đồ là **chi phí phản hồi, khả năng phát hiện lỗi và tính bảo trì**.

Đừng viết mọi bài kiểm thử qua UI chỉ vì nó “giống người dùng thật”: UI chậm và thay đổi thường xuyên có thể tạo nhiều test flaky. Nhưng cũng đừng bỏ kiểm tra đầu-cuối cho các hành trình sống còn như cấp quyền học sau thanh toán chỉ vì unit test đã xanh.

### Ví dụ cần test tích hợp chứ không chỉ test thuần

Quy tắc “mỗi học viên có tối đa một đăng ký hiệu lực cho một khóa” có thể bị vi phạm khi hai yêu cầu đồng thời đều kiểm tra “chưa có” rồi cùng ghi dữ liệu. Một lớp dịch vụ dùng phương thức **kiểm tra rồi thêm** đơn giản chưa chắc an toàn dưới cạnh tranh đồng thời.

Để bảo vệ quy tắc này, có thể cần ràng buộc dữ liệu duy nhất, transaction hoặc cơ chế idempotency thích hợp. Kiểm thử tích hợp phải xác minh trường hợp hai yêu cầu đồng thời và cách hệ thống trả kết quả. Đây là ví dụ cho thấy **logic ở unit test và sự thật ở hạ tầng cần hai vòng phản hồi khác nhau**.

## 9. Tích hợp liên tục (CI): đưa phản hồi từ máy cá nhân vào sản phẩm chung

Với XP, tích hợp liên tục giúp các thành viên ghép thay đổi nhỏ thường xuyên vào nhánh/bản tích hợp chung và phát hiện sai lệch sớm. CI hữu ích khi các tín hiệu quan trọng được kiểm tra tự động và kết quả thất bại được xử lý, không phải chỉ khi tổ chức có một trang dashboard đẹp.

Một chuỗi phản hồi minh họa:

~~~mermaid
flowchart TD
    A["Thay đổi nhỏ + unit tests cục bộ"] --> B["Commit / tích hợp theo chính sách nhóm"]
    B --> C["Build + static checks"]
    C --> D["Unit tests"]
    D --> E["Integration / contract tests"]
    E --> F["Smoke test luồng quan trọng"]
    F --> G["Artifact có thể triển khai"]
    G --> H["Triển khai/rollout khi đáp ứng điều kiện"]
    H --> I["Monitoring + phản hồi người dùng"]
    C -. "Thất bại" .-> X["Cung cấp tín hiệu, sửa và chạy lại"]
    D -. "Thất bại" .-> X
    E -. "Thất bại" .-> X
    F -. "Thất bại" .-> X
    X --> B
~~~

### Thứ tự kiểm tra có thể dựa trên tốc độ và rủi ro

Một cách tổ chức thường hợp lý là chạy kiểm tra **nhanh, ổn định, chi phí thấp** trước để phản hồi sớm; sau đó là các bài test cần database hoặc môi trường. Nhưng không phải dự án nào cũng nên dùng cùng một thứ tự. Một kiểm tra bảo mật cực nhanh có thể chạy sớm; một bài kiểm tra tải dài có thể thực hiện theo lịch hoặc trước các thay đổi liên quan.

### Ví dụ lệnh cho dự án Java dùng Gradle

~~~text
# Ví dụ minh họa, phụ thuộc cấu hình Gradle của dự án
./gradlew test
./gradlew check

# Trên Windows có thể dùng wrapper tương ứng:
gradlew.bat test
gradlew.bat check
~~~

Các lệnh trên chỉ thể hiện ý tưởng. **Không mặc định task check đã bao gồm mọi kiểm thử tích hợp, bảo mật hoặc end-to-end**: dự án phải cấu hình những task đó. Bài học không yêu cầu chạy các lệnh này để hiểu quy trình TDD.

### Hành động khi pipeline đỏ

- Phân biệt lỗi mã thật với lỗi môi trường hoặc test flaky.
- Ưu tiên sửa bản tích hợp bị lỗi trước khi tích tụ thêm nhiều thay đổi.
- Không bỏ qua test hoặc thay đổi assertion chỉ để có trạng thái xanh.
- Nếu pipeline quá chậm hoặc không ổn định, coi đó là vấn đề hệ thống cần cải tiến.
- Ghi nhận và điều tra các trường hợp bất thường lặp lại để tăng chất lượng tín hiệu.

**CI thành công không đồng nghĩa đã phát hành.** Delivery/deployment còn phụ thuộc kiểm soát vận hành, dữ liệu, an toàn, thời điểm kinh doanh và quyết định rollout. Definition of Done của Scrum xác định mức chất lượng để Increment được coi là hoàn tất; kế hoạch release là vấn đề liên quan nhưng không hoàn toàn đồng nhất.

## 10. Thiết kế vòng phản hồi đáng tin: nhanh chưa đủ

Một test suite trả kết quả trong ba phút nhưng thường đỏ ngẫu nhiên có thể làm nhóm bỏ qua cảnh báo. Ngược lại, suite rất ổn định nhưng chỉ chạy sau ba ngày sẽ làm lỗi bị phát hiện muộn. Cần xem đồng thời **độ trễ, độ tin cậy và khả năng hành động từ tín hiệu**.

### Ba đặc điểm cần quan sát

1. **Feedback latency – độ trễ:** từ lúc thay đổi đến khi nhóm biết nó có vấn đề. Đo theo các giai đoạn nếu cần.
2. **Signal quality – chất lượng tín hiệu:** khi test đỏ, có phản ánh sai lệch thật không? Test có thường sai ngẫu nhiên không?
3. **Actionability – khả năng xử lý:** thông báo có đủ rõ để người phụ trách xác định nguyên nhân và sửa không?

| Vấn đề | Nguyên nhân thường gặp | Hướng cải thiện |
| --- | --- | --- |
| Unit tests chậm | Nhiều test không cần thiết khởi động toàn bộ ứng dụng | Tách logic thuần, giảm phụ thuộc trong test phù hợp |
| Test thất bại ngẫu nhiên | Đồng hồ, mạng, dữ liệu chia sẻ, thứ tự chạy, đồng thời | Kiểm soát thời gian/dữ liệu, dùng giả lập hợp lý, cách ly trạng thái |
| CI đỏ khó hiểu | Log quá nhiều, tên test mơ hồ, thiếu bằng chứng lỗi | Đặt tên theo hành vi, ghi thông tin chẩn đoán an toàn |
| Test xanh nhưng production lỗi | Thiếu hợp đồng, dữ liệu thật hoặc tình huống cạnh tranh | Bổ sung integration/contract/risk-based tests và quan sát thực tế |
| Pipeline quá dài | Mọi thay đổi đều chạy toàn bộ bài kiểm tra nặng | Phân tầng kiểm tra, chạy theo rủi ro và vẫn bảo đảm cổng chất lượng bắt buộc |
| Nhóm bỏ qua test đỏ | Test flaky kéo dài, không có chính sách xử lý | Phân công giải quyết nguồn không tin cậy, giữ minh bạch về coverage |

### Dữ liệu test phải an toàn và tái lập

Không đưa mật khẩu, token hoặc hồ sơ học viên thật vào log hoặc test case. Với môi trường tích hợp, nên dùng dữ liệu giả lập hoặc đã được xử lý theo quy định. Test cần dọn trạng thái khi cần, tránh phụ thuộc vào kết quả test khác. Với luồng dữ liệu có tính thời gian, nên **kiểm soát nguồn thời gian** thay vì giả định test luôn chạy đúng một giây cụ thể.

### Test flaky cần được xử lý có trách nhiệm

Một test thỉnh thoảng thất bại không có nghĩa có thể tắt vô hạn. Nếu cần cách ly tạm thời để bảo vệ phản hồi, nhóm cần ghi rủi ro, người xử lý và kế hoạch khôi phục; đồng thời không được gắn Done cho Increment khi một điều kiện DoD bắt buộc vẫn chưa được đáp ứng.

## 11. Dùng TDD để thúc đẩy thiết kế tốt, không tạo cấu trúc phức tạp

TDD thường mang lại áp lực thiết kế hữu ích: nếu một đối tượng quá khó test vì phụ thuộc database, HTTP, thời gian và cấu hình toàn cục, có thể cần tách **quy tắc nghiệp vụ** khỏi **hạ tầng**.

Ví dụ với chức năng “Tiếp tục học”:

- **Quy tắc thuần:** tìm bài tiếp theo từ thông tin tiến độ đã hợp lệ.
- **Quy tắc quyền:** xác định học viên có quyền xem khóa.
- **Phối hợp dịch vụ:** đọc tiến độ, kiểm tra quyền, gọi quy tắc, trả trạng thái.
- **HTTP/UI:** chuyển trạng thái thành thông báo và điều hướng thích hợp.
- **Hạ tầng:** database, cache, logs, tracing, sự kiện và vận hành.

Các phần này có thể được kiểm tra với độ rộng khác nhau. Phân tách như vậy chỉ có ích nếu nó **giảm sự phụ thuộc và giúp hành vi rõ hơn**. Không cần thêm interface, factory hoặc repository giả cho mọi lớp để có thể gọi tất cả mọi thứ là “dễ test”.

### Refactor và thay đổi hành vi là hai việc khác nhau

Nếu thay quy tắc “mở bài tiếp theo” thành “mở bài gần nhất chưa hoàn thành”, đó là **thay đổi nghiệp vụ**. Cần trao đổi lại acceptance criteria, tạo kiểm thử diễn đạt hành vi mới và cập nhật mã.

Nếu chỉ đổi tên biến completedLessons thành completedCount hoặc rút logic lặp vào hàm riêng mà kết quả quan sát không đổi, đó là **refactor**. Unit tests nên tiếp tục xanh; nếu đỏ chỉ vì tên phương thức private thay đổi, có thể test đã bám quá sát nội bộ.

### Legacy code chưa có test thì bắt đầu từ đâu?

Trong hệ thống cũ, không phải lúc nào cũng dễ viết test trước một thay đổi. Một cách thực dụng:

1. Chọn một hành vi nhỏ, có rủi ro và phạm vi rõ.
2. Ghi nhận hành vi hiện tại bằng **characterization test** khi cần, phân biệt rõ hành vi hiện hữu với hành vi đúng mong muốn.
3. Tạo điểm tách phụ thuộc để thử hành vi mà không kéo theo toàn hệ thống.
4. Thêm test cho quy tắc mới, sửa mã ít nhất có thể và giữ hồi quy.
5. Cải tiến thiết kế từng bước, không refactor toàn bộ hệ thống trong một lần.

**Characterization test không có nghĩa hành vi cũ luôn đúng**; nó giúp biết khi nào ta vô tình thay đổi điều đang tồn tại. Product Owner và người hiểu nghiệp vụ vẫn cần quyết định điều gì nên được giữ hoặc sửa.

## 12. Phối hợp TDD và phản hồi tự động với Scrum, Kanban, XP

### XP là nơi TDD phát huy trong một hệ thống thực hành

TDD góp phần tạo vòng phản hồi ở cấp lập trình. XP còn khuyến khích tích hợp thường xuyên, phát triển theo bước nhỏ, refactoring, cộng tác và chất lượng kỹ thuật cao. Khi kết hợp, những kiểm thử xanh làm cho thay đổi tiếp theo **ít rủi ro hơn**, giúp nhóm đáp ứng phản hồi mà không kéo theo chi phí sửa lỗi quá lớn.

### Trong Scrum: test góp phần đáp ứng Definition of Done

Scrum không quy định phải dùng TDD hay một công cụ cụ thể, nhưng yêu cầu Increment đáp ứng **Definition of Done**. Developers chịu trách nhiệm chất lượng và có thể chọn TDD, kiểm thử tích hợp tự động, review hoặc các kỹ thuật khác để đáp ứng DoD.

Tại Sprint Planning/refinement, story cần đủ rõ về giá trị và trường hợp chấp nhận. Trong Sprint, Developers có thể dùng Red–Green–Refactor để xây từng lát. Sprint Review kiểm tra Increment và phản hồi sản phẩm; Retrospective là cơ hội điều chỉnh cách kiểm thử và CI nếu chất lượng hoặc tốc độ phản hồi có vấn đề.

Nếu unit tests xanh nhưng phân quyền chưa được kiểm tra theo DoD, PBI **chưa Done**. Product Owner không thể thay thế tiêu chuẩn chất lượng bằng một cái gật đầu tại Review.

### Trong Kanban: giảm thời gian chờ kiểm tra và làm lại

Một bảng Kanban có thể cho thấy công việc chờ review, kiểm thử hoặc triển khai. TDD/CI giúp giảm thời gian chờ phát hiện lỗi và tránh dồn nhiều thay đổi vào một lô lớn. Nhóm có thể theo dõi **WIP, cycle time, work item age và throughput** để kiểm tra liệu phản hồi tự động có giúp hạng mục hoàn thành nhanh và ổn định hơn.

Điểm quan trọng là **giảm thời gian từ bắt đầu đến Done**, không chỉ làm máy chạy nhiều bài kiểm thử hơn. Một pipeline quá nặng mà không phân tầng hợp lý có thể tự trở thành điểm nghẽn.

### Giữ vòng phản hồi người dùng

TDD trả lời “mã có tuân theo hành vi đã giả định không?”, còn Sprint Review, quan sát sản phẩm và discovery hỏi “hành vi đó có đáng xây, có thực sự hữu ích không?”. Hai loại phản hồi không thay thế nhau. Sản phẩm Agile cần cả **đúng về kỹ thuật** và **đúng về nhu cầu**.

## 13. Đo hiệu quả thực hành mà không biến test thành KPI hình thức

Các chỉ số có thể giúp phát hiện điểm nghẽn hoặc rủi ro, nhưng không nên dùng để xếp hạng cá nhân hoặc tạo động cơ tối ưu sai.

| Chỉ báo | Câu hỏi hữu ích | Diễn giải sai cần tránh |
| --- | --- | --- |
| **Thời gian phản hồi CI** | Bao lâu sau thay đổi có tín hiệu đủ hành động? | Pipeline nhanh là tốt dù bỏ kiểm tra quan trọng |
| **Tỷ lệ test flaky** | Có bao nhiêu thất bại khó tái lập, thiếu tin cậy? | Test xanh nhiều thì không có lỗi |
| **Lỗi thoát ra sau phát hành** | Rủi ro nào bộ kiểm thử chưa phát hiện? | Chỉ đếm số lỗi mà không xét mức độ ảnh hưởng |
| **Thời gian sửa bản tích hợp đỏ** | Nhóm có khôi phục feedback loop nhanh không? | Áp chỉ tiêu làm đỏ ít bằng cách không chạy test |
| **Cycle time và work item age** | Việc kiểm tra/tích hợp có tạo hàng đợi lâu? | Đổ lỗi cho người có story tồn tại lâu mà không xem phụ thuộc |
| **Coverage** | Phần nào của mã được chạy khi kiểm thử? | Coverage cao chứng minh hành vi hoặc yêu cầu đều đúng |
| **Mutation testing (nếu phù hợp)** | Test có phát hiện được một số biến đổi hành vi nhỏ không? | Điểm mutation cao thay thế kiểm thử tích hợp/người dùng |
| **Outcome người dùng** | Increment đang cải thiện khả năng học tập không? | Nhầm nhiều test xanh với giá trị tăng |

### Coverage là tín hiệu chứ không phải mục tiêu tối hậu

100% line coverage vẫn có thể không kiểm tra điều quan trọng: hai request ghi danh đồng thời, đường dẫn truy cập trái quyền, dữ liệu cũ hoặc callback thanh toán lặp. Ngược lại, test có chất lượng về những rủi ro cao có thể mang lại giá trị lớn hơn việc tăng coverage ở mã ít quan trọng.

**Đo lường có ý nghĩa khi giúp điều chỉnh thiết kế và cách làm**, không phải để yêu cầu lập trình viên thêm assertion hình thức.

### Kết hợp phản hồi kỹ thuật và dữ liệu luồng

Giả sử trước khi cải tiến, lỗi tích hợp thường phát hiện sau ba ngày; sau khi thêm contract test vào CI, lỗi tương thích API xuất hiện ngay trong ngày. Đây là một tín hiệu tích cực nếu:

- Việc kiểm tra không tạo quá nhiều false alarms.
- Cycle time hoặc thời gian sửa lỗi thực sự giảm.
- Lỗi production không tăng.
- Nhóm tiếp tục giao Increment có ích theo DoD.

Đừng kết luận chỉ từ một vài tuần số liệu nếu loại hạng mục, thành viên hoặc kiến trúc đã thay đổi mạnh. Cần nhìn **xu hướng cùng bối cảnh** và tiếp tục thử nghiệm cải tiến.

## 14. Phản mẫu thường gặp khi áp dụng TDD và phản hồi tự động

| Phản mẫu | Vì sao gây hại | Cách cải thiện |
| --- | --- | --- |
| Viết nhiều test sau cùng rồi gọi là TDD | Không có vòng thiết kế từ kiểm thử | Bắt đầu từ một hành vi nhỏ, Red–Green–Refactor |
| Test đỏ vì môi trường nhưng vẫn coi là bước Red hợp lệ | Không kiểm chứng được hành vi | Sửa cấu hình; test phải thất bại đúng lý do |
| Sửa assertion cho xanh thay vì sửa sản phẩm | Che giấu sai lệch | Xem lại hợp đồng hành vi với người hiểu nghiệp vụ |
| Viết implementation quá lớn cho một test | Khó phát hiện lỗi và refactor | Đi từng lát nhỏ có thể kiểm chứng |
| Test bám chặt method private và số lần gọi nội bộ | Refactor gây test đỏ vô ích | Kiểm tra kết quả/hợp đồng quan sát được |
| Mock mọi database và API | Bỏ sót transaction, hợp đồng, đồng thời | Bổ sung test tích hợp đúng rủi ro |
| Dồn toàn bộ test qua UI | Chậm và flaky, khó xác định nguyên nhân | Phân tầng unit, integration, contract và E2E |
| Chỉ có unit test rồi tuyên bố đã bảo mật | Bỏ sót quyền ở API/môi trường thật | Threat-based security và integration tests |
| Không xử lý CI đỏ | Mất niềm tin vào tín hiệu; lỗi tích tụ | Khôi phục bản tích hợp, sửa flaky và nguyên nhân |
| Tắt test lâu dài để kịp phát hành | Mất kiểm soát hồi quy, có thể vi phạm DoD | Minh bạch rủi ro, khắc phục thay vì giấu |
| Chạy hàng nghìn test chậm sau mỗi thay đổi nhỏ | Phản hồi đến muộn, phát triển bị chặn | Phân tầng và ưu tiên kiểm tra nhanh trước |
| Chạy theo coverage 100% | Tăng test hình thức, chưa chắc giảm lỗi | Tập trung hành vi và rủi ro quan trọng |
| TDD nhưng không nói chuyện với người dùng | Có thể xây đúng tính năng không ai cần | Phối hợp ATDD/BDD, Sprint Review, discovery |
| Quá nhiều refactoring không có mục đích | Thêm thay đổi, tăng rủi ro và chi phí | Refactor nhỏ khi cải thiện thiết kế thực sự |

### “Test xanh” chưa phải hoàn thành một user story

Một story có thể cần UI, API, kiểm soát quyền, dữ liệu và vận hành. Nếu chỉ kiểm tra từng hàm riêng, mọi unit test xanh nhưng hành trình chưa tích hợp, nhóm vẫn chưa có Increment đạt DoD. DoD là cam kết chất lượng của Scrum; acceptance criteria mô tả hành vi story; CI và các cấp kiểm thử là những phương tiện để đáp ứng chúng.

## 15. Bài thực hành: làm TDD cho chức năng ghi danh khóa miễn phí

### 15.1. Bối cảnh

Nền tảng học trực tuyến có user story:

> Là học viên đã đăng nhập, tôi muốn ghi danh vào một khóa miễn phí đang mở để có thể bắt đầu học mà không cần liên hệ hỗ trợ.

Người phụ trách sản phẩm làm rõ các quy tắc **minh họa**:

1. Học viên có quyền và khóa đang mở có thể ghi danh thành công.
2. Một học viên chỉ có tối đa một đăng ký hiệu lực cho cùng khóa.
3. Khóa đã đóng ghi danh không cho tạo đăng ký mới.
4. Người không đủ quyền không thể dùng đường dẫn API để ghi danh thay tài khoản khác.
5. Nếu yêu cầu được gửi lặp do mạng chậm, kết quả vẫn nhất quán, không sinh hai đăng ký hiệu lực.

### 15.2. Nhiệm vụ cho người học

1. Chọn **một quy tắc nhỏ nhất** có thể viết unit test trước, ví dụ khóa đã đóng không thể ghi danh.
2. Viết tên test và các bước **Arrange – Act – Assert** diễn đạt quy tắc.
3. Mô tả **Red** cần thất bại theo hành vi nào, **Green** cần thay đổi tối thiểu gì và **Refactor** có thể cải thiện điều gì mà không đổi hành vi.
4. Chọn trường hợp biên tiếp theo cho vòng TDD.
5. Phân biệt **điều có thể kiểm tra bằng unit test** với **điều cần kiểm thử tích hợp**, nhất là quy tắc chống đăng ký trùng khi gửi đồng thời.
6. Viết ít nhất hai ví dụ Gherkin để người hiểu nghiệp vụ xác nhận.
7. Đề xuất một pipeline CI đơn giản và giải thích bước nào cung cấp phản hồi nhanh nhất.
8. Nêu **hai guardrail** và một chỉ số phản hồi giúp kiểm tra cách làm mới có bảo vệ giá trị không.

### 15.3. Gợi ý lời giải

**Unit test đầu tiên:** “Khi khóa đã đóng, một yêu cầu ghi danh hợp lệ về người dùng bị từ chối”. Chuẩn bị một đối tượng khóa có trạng thái CLOSED, gọi quy tắc đăng ký, khẳng định hệ thống trả kết quả bị từ chối và không phát ra quyết định cấp quyền.

**Red:** hiện thực chưa kiểm tra trạng thái khóa nên test trả thành công, trong khi kỳ vọng bị từ chối. **Green:** thêm nhánh kiểm tra trạng thái và trả kết quả thích hợp. **Refactor:** làm rõ cách biểu diễn trạng thái, trích quy tắc kiểm tra có tên dễ hiểu nếu thực sự giảm trùng lặp, giữ test xanh.

**Các vòng tiếp:** kiểm tra khóa mở; học viên đã ghi danh; học viên không đủ quyền; yêu cầu trùng. Với việc chống trùng, unit test có thể xác nhận logic khi repository báo “đã tồn tại”, nhưng **không chứng minh** an toàn khi hai transaction đồng thời cùng thấy “chưa tồn tại”. Cần tích hợp database và kiểm thử cạnh tranh theo thiết kế nhất quán.

**Acceptance criteria ví dụ:**

~~~gherkin
Feature: Ghi danh khóa miễn phí

  Scenario: Ghi danh hợp lệ
    Given học viên đã đăng nhập và đủ điều kiện
    And khóa miễn phí đang nhận ghi danh
    And học viên chưa có đăng ký hiệu lực cho khóa
    When học viên xác nhận ghi danh
    Then hệ thống có đúng một đăng ký hiệu lực
    And học viên được cấp quyền học theo chính sách

  Scenario: Gửi yêu cầu ghi danh lặp
    Given học viên đã có đăng ký hiệu lực cho khóa
    When học viên gửi lại yêu cầu ghi danh cùng khóa
    Then hệ thống không tạo thêm đăng ký hiệu lực trùng
    And phản hồi trạng thái phù hợp

  Scenario: Khóa đã đóng ghi danh
    Given khóa miễn phí không còn nhận ghi danh
    When học viên gửi yêu cầu ghi danh
    Then hệ thống từ chối tạo đăng ký mới
    And không cấp thêm quyền học
~~~

**Pipeline gợi ý:** biên dịch và kiểm tra tĩnh → unit tests → integration/contract tests có database phù hợp → một số kiểm thử luồng trọng yếu → đóng gói → triển khai khi đáp ứng các điều kiện. Phản hồi nên xuất hiện sớm nhất ở bộ test nhanh và đáng tin, nhưng không được loại bỏ các kiểm tra bắt buộc để rút ngắn pipeline.

**Guardrail:** không cấp quyền sai; không tạo hoặc làm hỏng dữ liệu đăng ký hiệu lực. **Chỉ số kỹ thuật:** thời gian từ khi thay đổi đến khi CI phát hiện sai lệch; có thể theo dõi thêm test flaky, lỗi production và cycle time. **Outcome:** tỷ lệ học viên đủ điều kiện ghi danh thành công rồi mở bài đầu, được định nghĩa và đo đúng mẫu số.

Không có một cấu trúc lớp hoặc công cụ mock duy nhất đúng cho bài tập này. Cần ưu tiên **hợp đồng hành vi, kiểm chứng rủi ro và phản hồi đáng tin**.

## 16. Checklist khi áp dụng TDD và phản hồi tự động

- [ ] Nhóm hiểu **người hưởng lợi, hành vi cần có và acceptance criteria** trước khi chấm số test?
- [ ] Vòng TDD bắt đầu bằng **một trường hợp nhỏ**, không phải viết toàn bộ implementation?
- [ ] Ở bước Red, test thất bại **đúng lý do**?
- [ ] Ở bước Green, test mới và các test liên quan **đều đạt**?
- [ ] Refactor giữ nguyên hành vi, kiểm thử vẫn xanh và thiết kế thực sự rõ hơn?
- [ ] Tên test và assertion diễn đạt **kết quả quan sát được**, tránh bám cứng nội bộ?
- [ ] Đã kiểm tra **biên, dữ liệu bất hợp lệ, quyền và tình huống rủi ro cao**?
- [ ] Test doubles được sử dụng có chủ đích, không che giấu lỗi transaction/API thật?
- [ ] Unit, integration, contract, E2E và kiểm tra an toàn được phân tầng theo **rủi ro và chi phí phản hồi**?
- [ ] Test tự động có thể chạy lại, độc lập phù hợp và không rò rỉ dữ liệu nhạy cảm?
- [ ] CI có tín hiệu nhanh, dễ chẩn đoán và được xử lý khi đỏ?
- [ ] Test flaky được theo dõi và cải thiện, không vô hiệu hóa vô thời hạn?
- [ ] Story/Increment chỉ được xem là Done khi **đạt DoD**, không chỉ vì unit tests xanh?
- [ ] Có phân biệt **phản hồi kỹ thuật** với **phản hồi giá trị từ người dùng**?
- [ ] Scrum, Kanban và XP được dùng bổ trợ cho **bàn giao tăng dần và cải tiến liên tục**?
- [ ] Chỉ số coverage, số test, velocity không bị dùng để **xếp hạng cá nhân hay làm đẹp báo cáo**?
- [ ] Nhóm có học từ lỗi thoát ra production và cải thiện kiểm thử ở cấp phù hợp?

**Ghi nhớ:** **TDD** dùng vòng **Red–Green–Refactor** để thiết kế và bảo vệ từng hành vi nhỏ; **phản hồi tự động** qua kiểm thử nhiều cấp và tích hợp liên tục giúp sai lệch được phát hiện sớm trên sản phẩm chung. Cả hai cần được kết hợp với **Definition of Done, phản hồi người dùng và quản lý luồng công việc**. Khi đó, thực hành kỹ thuật của XP giúp Agile không chỉ giao phần mềm thường xuyên mà còn **thay đổi an toàn, học hỏi nhanh và duy trì chất lượng có thể kiểm chứng**.
