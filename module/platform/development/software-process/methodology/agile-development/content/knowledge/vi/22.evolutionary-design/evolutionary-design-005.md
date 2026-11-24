# Giữ tính đơn giản và tránh xây sẵn khả năng chưa được chứng minh

Một đội phát triển nền tảng học trực tuyến được giao yêu cầu: **“Học viên muốn tiếp tục bài học từ vị trí đã lưu.”** Trước khi có phiên bản đầu tiên cho người dùng thử, nhóm đã dự định xây một hệ thống plugin hỗ trợ nhiều loại khóa học, cơ chế đồng bộ offline mọi thiết bị, chiến lược giải quyết xung đột tùy biến và giao diện cấu hình cho các đối tác chưa ký hợp đồng. Kế hoạch nghe có vẻ “sẵn sàng cho tương lai”, nhưng nhu cầu đơn giản của học viên vẫn chưa được giải quyết.

**Thiết kế tiến hóa (evolutionary design)** đặt một câu hỏi thực dụng:

> Với những nhu cầu và ràng buộc **đã có bằng chứng**, đâu là thiết kế **đơn giản nhất mà vẫn đúng, an toàn, dễ hiểu và có thể thay đổi**?

Thay vì dự đoán mọi thay đổi, nhóm xây **lát cắt có giá trị**, kiểm chứng hành vi, học từ phản hồi rồi cải thiện cấu trúc khi nhu cầu mới xuất hiện. Hai nguyên tắc liên quan thường được nhắc tới là **KISS (Keep It Simple)** và **YAGNI (You Aren't Gonna Need It — đừng xây trước điều chưa có nhu cầu được chứng minh)**. Tuy nhiên, chúng không cho phép bỏ kiểm thử, bỏ bảo mật, bỏ thiết kế hoặc hy sinh độ tin cậy để viết mã thật ngắn.

Bài thuộc chương **Thiết kế tiến hóa** trong mô-đun **AGILE_DEVELOPMENT**, kết nối Agile qua phản hồi sớm, bàn giao phần mềm tăng dần và cải tiến liên tục với user story, Product Backlog, Scrum, Kanban, XP và đo lường dòng công việc.

**Mục tiêu học tập:** Sau bài này, bạn có thể phân biệt đơn giản với sơ sài; phát hiện thiết kế dựa trên giả định tương lai; đánh giá khi nào nên và không nên trừu tượng hóa; dùng kiểm thử, refactoring, tích hợp liên tục để tiến hóa an toàn; xem xét những quyết định kiến trúc khó đảo ngược; và đánh giá thiết kế dựa trên kết quả sản phẩm, chất lượng cùng khả năng thích ứng.

## 1. “Đơn giản” không đồng nghĩa “ít dòng mã nhất”

Một chương trình có ít dòng mã nhưng khó hiểu, không có kiểm thử và có thể làm mất dữ liệu **không phải thiết kế đơn giản tốt**. Sự đơn giản cần được nhìn qua **chi phí hiểu, thay đổi, kiểm chứng, vận hành và bảo vệ hành vi** của cả hệ thống.

| Cách hiểu | Ví dụ | Đánh giá |
| --- | --- | --- |
| **Ít dòng mã** | Một hàm dài chứa mọi nhánh nghiệp vụ | Có thể ít file nhưng khó sửa và khó kiểm thử |
| **Ít thành phần không cần thiết** | Chưa dựng plugin framework khi chỉ có một kiểu lưu tiến độ | Giảm số mối quan hệ phải hiểu |
| **Ý định rõ ràng** | Tên hàm mô tả quy tắc không ghi đè tiến độ đã xác nhận | Giúp người khác sửa an toàn |
| **Ít giả định tương lai** | Hỗ trợ một thiết bị ở lát cắt đầu theo phạm vi đã thống nhất | Tránh đầu tư trước khi biết có cần |
| **Đủ chất lượng** | Có kiểm thử, xử lý lỗi và bảo vệ dữ liệu theo rủi ro | Không đánh đổi tính đúng để tiết kiệm ngắn hạn |
| **Dễ thay đổi có kiểm chứng** | Ranh giới rõ, test đáng tin và thay đổi nhỏ | Hỗ trợ thiết kế tiến hóa |

### Hai cách “đơn giản” khác nhau

**Cách A:** Hệ thống luôn hiển thị “Đã lưu” ngay khi người dùng nhấn nút. Đây là một câu lệnh rất ngắn nhưng **sai** nếu mạng bị ngắt hoặc API chưa xác nhận.

**Cách B:** Hệ thống phân biệt **đang lưu, đã xác nhận và không thể lưu**, kiểm thử từng trạng thái và thông báo đúng cho người dùng. Cách B dài hơn, nhưng **đơn giản về ý nghĩa nghiệp vụ và dễ bảo vệ bằng kiểm thử**.

**Nguyên tắc:** Tìm thiết kế **ít phức tạp nhất trong số những thiết kế đáp ứng hành vi và tiêu chuẩn chất lượng**, không tìm mã ít ký tự nhất.

## 2. KISS, YAGNI và Simple Design trong XP

### KISS — tránh phức tạp không tạo thêm giá trị

**KISS** khuyến khích chọn giải pháp dễ hiểu và có ít mối phụ thuộc hơn **nếu các lựa chọn đều giải quyết được cùng yêu cầu với chất lượng phù hợp**.

Ví dụ, để chuyển trạng thái lưu đã xác nhận thành thông điệp, một quy tắc ánh xạ rõ ràng có thể đơn giản hơn một engine sự kiện động cùng hệ thống plugin thông điệp. Tuy nhiên, dùng một thư viện ổn định đang giải quyết đúng một yêu cầu khó cũng có thể **đơn giản hơn tự viết lại cơ chế đó**.

### YAGNI — chưa có bằng chứng thì đừng tự xây tương lai

**YAGNI** thường gắn với XP, nhắc đội không triển khai khả năng chưa có nhu cầu hiện tại hoặc bằng chứng đủ mạnh chỉ để chuẩn bị cho **một kịch bản tương lai suy đoán**.

Ví dụ:

- **Đã cần:** Học viên lưu và khôi phục tiến độ đáng tin cậy trên cùng thiết bị.
- **Có thể cần:** Đồng bộ offline giữa nhiều thiết bị, giải quyết các kiểu xung đột.
- **Quyết định:** Hoàn thành lát cắt hiện tại, ghi điều chưa biết và làm rõ đa thiết bị khi được ưu tiên thật sự.

YAGNI không yêu cầu mọi quyết định phải có số liệu thị trường hoàn hảo. **Ràng buộc bảo mật đã biết, tính đúng dữ liệu, hợp đồng bắt buộc và rủi ro kiến trúc nghiêm trọng** có thể đòi hỏi đầu tư trước khi người dùng nhìn thấy trực tiếp.

### Simple Design — thiết kế đủ rõ, đủ tốt

Trong truyền thống XP, thiết kế đơn giản thường được giải thích bằng những định hướng:

1. **Những kiểm thử quan trọng cho hành vi hiện tại đều đạt**.
2. **Mã thể hiện ý định rõ**, giúp người khác hiểu tại sao nó tồn tại.
3. **Tránh trùng lặp không cần thiết của kiến thức hoặc quy tắc**.
4. **Không thêm phần tử, trạng thái hoặc cơ chế vượt nhu cầu**.

Đó là những tiêu chí gợi ý, không phải công thức máy móc. Loại bỏ trùng lặp bằng một hệ phân cấp phức tạp có thể đi ngược sự đơn giản nếu hai đoạn mã chỉ tình cờ giống cú pháp.

| Tư tưởng | Câu hỏi | Ví dụ quyết định |
| --- | --- | --- |
| **KISS** | Có cách đạt cùng mục tiêu với ít phức tạp hơn? | Dùng quy tắc trạng thái rõ thay vì engine cấu hình |
| **YAGNI** | Đây là nhu cầu đã xác nhận hay giả định tương lai? | Chưa xây adapter offline khi chưa có phạm vi offline |
| **Thiết kế tiến hóa** | Khi bằng chứng đổi, ta có sửa an toàn không? | Test, ranh giới rõ và refactoring có kiểm chứng |

## 3. Nhận diện một khả năng chưa được chứng minh

Những câu nói dễ dẫn tới **speculative generality — tổng quát hóa theo suy đoán**:

> “Sau này chắc chắn sẽ có mười nhà cung cấp lưu trữ.”
>
> “Cứ làm một framework workflow chung cho mọi sản phẩm trước.”
>
> “Chưa có khách hàng offline, nhưng nên xử lý tất cả chiến lược xung đột ngay.”
>
> “Làm cấu hình cho mọi quy tắc để khỏi sửa code về sau.”

Những đề xuất này không tự động sai. Câu hỏi là **bằng chứng, chi phí và thời điểm quyết định**.

| Tình trạng | Ví dụ | Cách phản ứng hợp lý |
| --- | --- | --- |
| **Bắt buộc ở lát cắt hiện tại** | Chỉ đúng tài khoản có quyền mới đọc tiến độ | Thiết kế và kiểm chứng ngay |
| **Nhu cầu đã được ưu tiên** | Sắp triển khai đồng bộ thiết bị thứ hai | Làm rõ quy tắc và lên kế hoạch |
| **Có tín hiệu nhưng chưa cần ngay** | Nghiên cứu chỉ ra nhu cầu offline | Ghi giả thuyết, điều kiện ưu tiên và chi phí đổi sau |
| **Chỉ là khả năng tưởng tượng** | Một ngày có plugin từ mười đối tác | Chưa xây toàn bộ; theo dõi bằng chứng |
| **Rủi ro khó đảo ngược** | Định danh dữ liệu ảnh hưởng migration lâu dài | Nghiên cứu có giới hạn và chọn ranh giới an toàn |

### Sáu câu hỏi quyết định

1. **Ai cần** khả năng ấy và khi nào cần?
2. **Bằng chứng** nào ủng hộ: người dùng, hợp đồng, quy định, kết quả đo hay trực giác?
3. Nếu **không xây bây giờ**, hệ thống hiện tại có sai hoặc thiếu an toàn không?
4. Nếu nhu cầu đến sau, **chi phí bổ sung khi đó** thực sự lớn tới đâu?
5. Quyết định này **khó đảo ngược** vì dữ liệu, API công khai hoặc vận hành không?
6. Có **bước chuẩn bị nhỏ, ít tốn kém** để giữ khả năng đổi hướng không?

Quyết định có thể là **xây ngay, hoãn, chia lát cắt hoặc thực hiện spike giới hạn**. YAGNI không có nghĩa lúc nào cũng trả lời “không”.

## 4. Tách nhu cầu, giả định, giải pháp và điều kiện chất lượng

Một nguyên nhân overengineering là yêu cầu ban đầu đã chứa sẵn công nghệ và phạm vi suy đoán.

| Loại thông tin | Ví dụ | Câu hỏi cần đặt |
| --- | --- | --- |
| **Vấn đề** | Học viên mất tiến độ khi quay lại | Điều gì xảy ra, ảnh hưởng tới ai? |
| **Outcome** | Học viên tiếp tục mà không phải học lại | Làm sao quan sát kết quả ấy? |
| **Giả định** | Ai cũng học trên nhiều thiết bị | Có số liệu hoặc phản hồi xác nhận? |
| **Đề xuất giải pháp** | Xây engine đồng bộ hai chiều có plugin | Có phương án nhỏ hơn đáp ứng nhu cầu? |
| **Ràng buộc bắt buộc** | Chỉ tài khoản có quyền mới đọc tiến độ | Cần kiểm chứng ở mọi lát cắt nào? |
| **Điều kiện chất lượng** | Không báo lưu thành công sai hoặc làm mất dữ liệu | Test/DoD cần bảo vệ điều gì? |

User story minh họa:

> Là học viên đang học dở, tôi muốn quay lại đúng tiến độ đã được lưu thành công, để không phải học lại những phần đã hoàn tất.

Story không bắt buộc event sourcing, message broker hoặc plugin framework. Các kỹ thuật ấy có thể cần ở bối cảnh khác, nhưng **phải có lý do cụ thể từ nhu cầu và rủi ro đang biết**.

### Hai cực đoan cần tránh

- **Overengineering:** Dựng hệ thống rộng, tốn vận hành để giải quyết yêu cầu nhỏ.
- **Underengineering:** Bỏ xử lý lỗi, kiểm thử, quyền truy cập hoặc tính đúng vì muốn nhanh.

Thiết kế tiến hóa tìm **mức đầu tư vừa đủ**: không giải quyết vấn đề chưa có, cũng không **vay nợ chất lượng không lý do**.

## 5. Xác định một lát cắt giá trị đủ nhỏ

**Bối cảnh giả định:** Product Goal là giúp học viên hoàn thành bài đầu và quay lại học đáng tin cậy. Nhóm chốt lát cắt:

- Một tài khoản đã xác thực, một thiết bị và có kết nối.
- Lưu **bước học hoàn thành gần nhất** theo quy tắc bài tuyến tính.
- Khôi phục tiến độ **đã được xác nhận**.
- Không thông báo thành công khi việc lưu còn chưa chắc chắn.
- Duy trì phân quyền và tiêu chuẩn chất lượng.

**Chưa bao gồm:** học offline nhiều ngày, đồng bộ xung đột đa thiết bị, giao diện cấu hình chính sách tiến độ cho đối tác và workflow engine tùy biến.

### Ví dụ nghiệp vụ quan trọng

~~~gherkin
Feature: Lưu và khôi phục tiến độ của học viên

  Scenario: Khôi phục dữ liệu đã được xác nhận lưu
    Given học viên đã được xác nhận hoàn thành bước 4
    When học viên mở lại bài học với cùng tài khoản
    Then hệ thống khôi phục tiến độ tương ứng bước 4

  Scenario: Không tuyên bố thành công khi chưa có xác nhận
    Given học viên vừa hoàn thành bước 5
    And dịch vụ chưa xác nhận tiến độ đã được lưu
    When học viên xem trạng thái
    Then giao diện không thông báo "Đã lưu tiến độ"
    And học viên biết việc lưu chưa được xác nhận

  Scenario: Từ chối sự kiện hoàn thành ngoài phạm vi
    Given bài học chỉ có 8 bước
    When hệ thống nhận yêu cầu hoàn thành bước 12
    Then hệ thống từ chối yêu cầu không hợp lệ
~~~

Nhóm vẫn phải làm rõ “khôi phục bước 4” nghĩa là bắt đầu bước 4 hay vị trí sau bước 4. **BDD giúp nhận diện điều chưa rõ, không biến giả định thành sự thật bằng cách viết kịch bản**.

### Thiết kế vừa đủ

Một hướng hiện thực gồm:

1. Quy tắc tiến độ đơn giản cho **bài tuyến tính**.
2. Đọc/ghi bằng hệ thống dữ liệu hiện có khi phù hợp.
3. Hợp đồng trạng thái lưu chính xác.
4. Unit test cho quy tắc, test tích hợp đọc/ghi và kiểm soát quyền.
5. Increment hoàn thành theo Definition of Done.

Điều cần bảo vệ là **hành vi đã có**, không phải kiến trúc đầu tiên bất biến.

## 6. Ví dụ Java: quy tắc hiện tại thay vì framework giả định

Giả sử trong **phạm vi đã xác nhận**, bài học là tuyến tính và tiến độ đã hoàn thành **không giảm**: sự kiện cũ không được xóa những bước đã hoàn thành. Quy tắc này không tự áp dụng cho bài học có nhánh, reset chủ động hoặc đồng bộ nhiều thiết bị.

Một hiện thực gọn:

~~~java
public final class ProgressPolicy {
    private ProgressPolicy() {
    }

    public static int recordCompletedStep(
            int currentCompleted,
            int newlyCompleted,
            int totalSteps) {

        if (totalSteps < 1
                || currentCompleted < 0
                || currentCompleted > totalSteps
                || newlyCompleted < 1
                || newlyCompleted > totalSteps) {
            throw new IllegalArgumentException("Bước học không hợp lệ");
        }

        // Cho phép hoàn tất bước kế tiếp hoặc ghi nhận lại bước cũ.
        if (newlyCompleted > currentCompleted + 1) {
            throw new IllegalArgumentException("Không được bỏ qua bước");
        }

        return Math.max(currentCompleted, newlyCompleted);
    }
}
~~~

Hàm chỉ biểu diễn **quy tắc tiến độ tuyến tính**. Nó không xử lý quyền, dữ liệu bền vững, điều kiện đồng thời, giao diện hay mạng. Khi đưa vào ứng dụng thật, các vấn đề ấy cần được thiết kế và kiểm chứng tại ranh giới phù hợp.

### Vì sao chưa cần một chuỗi factory và registry?

~~~text
ProgressPolicyPlugin
  -> ProgressPolicyRegistry
     -> ProgressStrategyFactory
        -> ReflectionLoader
           -> ProgressPolicyResolver
              -> CurrentProgressPolicy
~~~

Nếu chỉ có một chính sách hiện hành, hệ thống trên có thể tăng số thành phần và hướng phụ thuộc **mà chưa tạo thêm hành vi giá trị**. Khi xuất hiện loại bài học thứ hai được xác nhận, nhóm có bằng chứng để thiết kế abstraction theo **những khác biệt thật sự**.

### Bảo vệ quy tắc bằng kiểm thử

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import org.junit.jupiter.api.Test;

class ProgressPolicyTest {
    @Test
    void completesNextStep() {
        assertEquals(4,
            ProgressPolicy.recordCompletedStep(3, 4, 8));
    }

    @Test
    void oldEventDoesNotLowerProgress() {
        assertEquals(4,
            ProgressPolicy.recordCompletedStep(4, 3, 8));
    }

    @Test
    void cannotSkipAnUnfinishedStep() {
        assertThrows(IllegalArgumentException.class,
            () -> ProgressPolicy.recordCompletedStep(3, 6, 8));
    }

    @Test
    void cannotCompleteStepOutsideLesson() {
        assertThrows(IllegalArgumentException.class,
            () -> ProgressPolicy.recordCompletedStep(3, 12, 8));
    }
}
~~~

Ví dụ dùng Java và JUnit Jupiter. Muốn chạy thật cần dự án Java, dependency JUnit phù hợp và cấu hình kiểm thử; các đoạn mã chỉ nhằm minh họa. **Unit test xanh không chứng minh đã lưu dữ liệu bền vững, kiểm soát phân quyền hay xử lý xung đột đồng thời đúng**.

## 7. Khi xuất hiện nhu cầu thứ hai: tiến hóa theo bằng chứng

Giả sử sau một số Increment, Product Owner xác nhận và ưu tiên **hai loại bài học**:

- **Tuyến tính:** Hoàn thành bước 1, 2, 3 theo thứ tự.
- **Có nhánh:** Học viên chọn một nhánh, trạng thái gồm các node đã hoàn thành; một số bước có thể được bỏ qua theo quy tắc.

Lúc này mô hình chỉ dùng số bước tăng dần **không còn diễn tả đủ miền nghiệp vụ**. Đó là lý do thực để đánh giá thiết kế mới.

### Tiến hóa theo ba bước

**Bước A — Giữ hành vi cũ được bảo vệ.** Các kiểm thử cho bài tuyến tính tiếp tục chạy. Nhóm dùng ví dụ nghiệp vụ làm rõ điều gì khác ở bài có nhánh.

**Bước B — Tách những khái niệm thực sự khác.** Không cố nhét tiến độ theo nhánh vào một số nguyên hoặc thêm hàng chục cờ boolean.

**Bước C — Chỉ tạo abstraction chung khi có một hợp đồng có nghĩa.** Nếu hai loại tiến độ có hành vi chung thật, cân nhắc giao diện phù hợp; nếu khác nhau sâu sắc, giữ mô hình riêng có thể đơn giản hơn.

~~~text
LessonProgress
  |
  +-- LinearProgress
  |      completedStep, totalSteps
  |
  +-- BranchProgress
         completedNodeIds, selectedBranch

ProgressApplicationService
  -> áp dụng quy tắc theo loại bài học đã xác định
  -> bảo vệ quyền và lưu dữ liệu bền vững
~~~

Đây là **sơ đồ khái niệm**, không phải yêu cầu phải tạo cây kế thừa. Một vài kiểu dữ liệu tách biệt và các hàm rõ nghĩa có thể tốt hơn một interface quá chung.

### “Đợi trường hợp thứ hai” không phải định luật

Khi mới có một trường hợp, đội thường **đoán** phần nào sẽ thay đổi. Khi có hai trường hợp thật, họ biết điều gì chung hoặc khác. Nhưng không bắt buộc phải đợi đúng hai use case mới được tạo interface: ranh giới giữa hệ thống ngoài hoặc yêu cầu kiểm soát đã xác nhận có thể cần ngay. Ngược lại, ba use case cũng chưa chắc cần một framework.

## 8. Refactoring giữ thiết kế đơn giản theo thời gian

**Refactoring** là cải thiện cấu trúc bên trong **không có chủ đích thay đổi hành vi quan sát được**.

Ví dụ:

- Đặt lại tên biến để thể hiện ý nghĩa nghiệp vụ.
- Tách một hàm dài thành các phần trách nhiệm rõ.
- Gom quy tắc bị lặp tại những nơi có cùng lý do thay đổi.
- Tách kiểm soát quyền truy cập khỏi phép tính tiến độ.
- Loại bỏ lớp wrapper không còn được sử dụng.

~~~mermaid
flowchart TD
    A["Có hành vi và kiểm thử quan trọng"] --> B["Nhận diện mã khó hiểu / trùng lặp"]
    B --> C["Chọn một thay đổi cấu trúc nhỏ"]
    C --> D["Chạy kiểm thử và tích hợp cần thiết"]
    D --> E{"Hành vi ngoài ý muốn thay đổi?"}
    E -->|Có| F["Sửa hoặc hoàn nguyên bước vừa làm"]
    F --> C
    E -->|Không| G["Tích hợp thay đổi nhỏ"]
    G --> H["Tiếp tục lát cắt / refactor khi cần"]
~~~

| Refactoring | Rewriting |
| --- | --- |
| Thường là thay đổi cấu trúc nhỏ có test bảo vệ | Có thể thay phần lớn hiện thực |
| Phản hồi nhanh, dễ thu hẹp lỗi | Nhiều khác biệt hành vi cần kiểm chứng |
| Giữ khả năng tích hợp thường xuyên | Có thể cần kế hoạch di chuyển song song |
| Phù hợp cải thiện cấu trúc hiện hữu | Có thể cần khi nền tảng cũ không còn đáp ứng |

Không phải mọi hệ thống đều có thể thay đổi bằng refactor nhỏ; migration lớn đôi khi cần thiết. Nhưng **YAGNI không phải lý do trì hoãn refactoring** khi mã hiện tại thực sự khó hiểu hoặc dễ gây lỗi.

## 9. Kiểm thử và phản hồi kỹ thuật là điều kiện để thay đổi an toàn

Nếu mỗi lần sửa mã phải chạy thử thủ công toàn bộ hệ thống, chi phí refactor sẽ cao và đội dễ né thay đổi. Để thiết kế tiến hóa hoạt động, cần **mạng lưới phản hồi đủ nhanh và đáng tin**.

| Lớp kiểm chứng | Điều được bảo vệ | Giới hạn |
| --- | --- | --- |
| **Unit/domain** | Quy tắc bước học và dữ liệu đầu vào | Không chứng minh dữ liệu thực đã lưu |
| **Contract** | Hợp đồng trạng thái client–server | Không chứng minh hành trình người dùng |
| **Integration** | Đọc/ghi tiến độ đúng tài khoản | Cần môi trường/dữ liệu đáng tin |
| **End-to-end chọn lọc** | Học dở → lưu → tải lại → khôi phục | Chậm và dễ phụ thuộc UI nếu lạm dụng |
| **Kiểm thử phi chức năng** | Phân quyền, đồng thời, hiệu năng và phục hồi | Cần lựa chọn theo rủi ro |
| **Quan sát vận hành** | Sự cố và hành vi thật sau phát hành | Không thay kiểm thử trước khi giao |

**TDD (Red–Green–Refactor)** giúp làm một hành vi nhỏ, viết mã vừa đủ rồi cải thiện cấu trúc. **BDD** giúp các góc nhìn nghiệp vụ–phát triển–kiểm thử thống nhất **hành vi nên có** trước khi đầu tư quá nhiều. **Continuous Integration** giúp phát hiện lỗi tích hợp sớm hơn.

~~~text
User story / nhu cầu hiện tại
  -> Trao đổi ví dụ nghiệp vụ
  -> Kiểm thử quan trọng
  -> Hiện thực đơn giản đủ đúng
  -> Refactor có bảo vệ
  -> CI và kiểm thử tích hợp
  -> Increment đạt Definition of Done
  -> Phản hồi người dùng và vận hành
  -> Cập nhật hiểu biết / thiết kế
~~~

**Lưu ý:** Test xanh chứng minh điều đã được kiểm tra trong phạm vi test, không chứng minh mọi giả định sản phẩm đúng hoặc mọi rủi ro đã biến mất.

## 10. Chuẩn bị cho thay đổi khác với xây trước mọi thay đổi

Một số quyết định tạo **khả năng đổi hướng** mà không triển khai luôn tính năng suy đoán:

| Bước chuẩn bị nhỏ | Lợi ích hiện tại | Phần chưa cần xây |
| --- | --- | --- |
| Tên khái niệm miền nghiệp vụ rõ | Đỡ nhầm trạng thái và quy tắc | Framework cấu hình toàn bộ miền |
| Kiểm thử hồi quy | Bảo vệ hành vi đang có | Hàng trăm scenario chưa có use case |
| Tách phân quyền khỏi quy tắc tiến độ | Bảo vệ an toàn và trách nhiệm rõ | Hệ thống phân quyền tự xây cho mọi đối tác |
| Hợp đồng API đúng ngữ nghĩa | Giúp UI và backend làm việc hiện tại | Hàng chục phiên bản giả định |
| Migration dữ liệu có kiểm soát | Bảo vệ dữ liệu đang tồn tại | Nền tảng migration tổng quát chưa dùng |
| Đường khôi phục sự cố phù hợp | Giảm ảnh hưởng thay đổi hiện tại | Bộ orchestration tùy biến không có nhu cầu |
| Ghi quyết định kiến trúc ngắn | Người mới hiểu lý do hiện tại | Tài liệu dự báo mọi kiến trúc tương lai |

Không nên cộng hàng chục “bước chuẩn bị nhỏ” mà không xét tổng chi phí. **Mỗi bước vẫn cần một lý do và mức đầu tư tương xứng**.

## 11. Quyết định kiến trúc dễ đảo ngược và khó đảo ngược

Nếu YAGNI bị hiểu thành “không suy nghĩ về tương lai dưới bất kỳ hình thức nào”, đội có thể tạo ra **những lựa chọn dữ liệu hoặc API rất khó sửa**.

| Loại quyết định | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| **Dễ đảo ngược** | Tên helper nội bộ, tổ chức một module chưa công khai | Chọn đơn giản, đo rồi sửa |
| **Khó đảo ngược** | Định danh người dùng, schema lưu dữ liệu lớn, API công khai, mô hình quyền | Làm rõ yêu cầu, kiểm chứng rủi ro và đường tương thích |

### Ví dụ định danh dữ liệu

Nếu tiến độ được lưu chỉ theo mã bài học, hai học viên học cùng bài có thể ghi đè dữ liệu của nhau. Bỏ định danh học viên hoặc phân quyền **không phải KISS hoặc YAGNI**: đó là **vi phạm tính đúng và bảo vệ dữ liệu hiện tại**.

Ngược lại, thiết kế ngay một hệ thống cách ly cho hàng trăm đối tác chưa tồn tại có thể là phạm vi suy đoán.

### Ghi quyết định ngắn và điều kiện xem lại

~~~text
QUYẾT ĐỊNH:
  Lưu tiến độ theo tài khoản học viên và bài học.

LÝ DO:
  Khôi phục đúng dữ liệu người học, không để đọc chéo.

RÀNG BUỘC:
  Phân quyền, tính đúng, migration dữ liệu hiện có.

CHƯA BAO GỒM:
  Đồng bộ offline hoặc giải quyết xung đột đa thiết bị.

XEM LẠI KHI:
  Product Backlog có nhu cầu mới được xác nhận,
  hoặc phát hiện rủi ro kỹ thuật làm thay đổi quyết định.
~~~

Không cần viết một kiến trúc hàng trăm trang. Điều cần là **vì sao chọn hiện tại, giới hạn và dấu hiệu cần xem lại**.

## 12. YAGNI không phải lý do bỏ kiểm soát và chất lượng

Những điều sau có thể **bắt buộc ngay cả khi không tạo tính năng nhìn thấy được**:

- Xác thực, phân quyền và bảo vệ dữ liệu cá nhân.
- Kiểm tra đầu vào và quy tắc nghiệp vụ gây sai dữ liệu.
- Xử lý lỗi, xác nhận lưu và tính nhất quán theo yêu cầu.
- Kiểm thử tích hợp tại những ranh giới có rủi ro.
- Khả năng phát hiện và khôi phục sự cố phù hợp.
- Yêu cầu hiệu năng, độ sẵn sàng và tuân thủ đã xác nhận.
- Tiêu chuẩn Definition of Done cho phần sản phẩm hoàn thành.

**Phản ví dụ:** Nhóm bỏ kiểm tra quyền đọc tiến độ vì cho rằng “đa tenant là chuyện tương lai”. Quyền riêng tư giữa hai tài khoản hiện tại **không phải tính năng tương lai**.

Trong Scrum, **Definition of Done** là commitment của Increment. Một hạng mục chưa đáp ứng chất lượng cần thiết **không nên được tính là Increment hoàn thành** chỉ vì giao diện đã có thể demo.

**Đơn giản không có nghĩa tự viết một hệ thống bảo mật mới.** Tái sử dụng cơ chế được kiểm chứng và phù hợp bối cảnh có thể đơn giản, an toàn hơn sáng tạo thêm framework riêng.

## 13. Tiến hóa dữ liệu và API mà không phá hệ thống đang chạy

Khi đã có người dùng, thay đổi dữ liệu có thể khó đảo ngược hơn thay đổi một lớp Java. Ứng dụng phiên bản cũ và mới có thể hoạt động cùng lúc, dịch vụ ngoài đang gọi API hiện tại hoặc dữ liệu tiến độ cần được giữ chính xác qua quá trình chuyển đổi.

Một kỹ thuật hữu ích là **expand–migrate–contract**:

1. **Expand — mở rộng tương thích:** Thêm trường hoặc cấu trúc mới mà những thành phần cũ còn hoạt động được.
2. **Migrate — chuyển đổi từng phần:** Chuyển dữ liệu và các thành phần đọc/ghi theo quy trình kiểm soát, đo kết quả và kiểm tra lỗi.
3. **Contract — thu hẹp sau khi an toàn:** Xóa cấu trúc cũ chỉ khi đã xác nhận không còn phụ thuộc và có kế hoạch phục hồi phù hợp.

~~~mermaid
flowchart LR
    A["Schema và API đang hoạt động"] --> B["Expand: thêm phần tương thích"]
    B --> C["Migrate: chuyển đổi từng bước"]
    C --> D["Đối soát dữ liệu + quan sát vận hành"]
    D --> E{"Còn phụ thuộc phần cũ?"}
    E -->|Có| C
    E -->|Không| F["Contract: loại bỏ phần cũ an toàn"]
~~~

### Ví dụ cải tiến cách lưu tiến độ

Ban đầu mỗi tài khoản–bài học có một số bước đã hoàn thành. Khi có bài học theo nhánh được ưu tiên thật, nhóm cần cách biểu diễn các node đã hoàn thành.

**Không nên** đổi toàn bộ dữ liệu sang kiểu mới trong một bước mù mờ nếu nhiều thành phần còn dùng cách cũ. Một kế hoạch có kiểm soát có thể:

- Thêm cấu trúc lưu tiến độ theo nhánh mà không phá cách đọc hiện tại.
- Cập nhật ứng dụng để đọc đúng kiểu bài, đồng thời giữ tương thích trong thời gian chuyển đổi.
- Chuyển dữ liệu thuộc phạm vi phù hợp và đối soát kết quả.
- Quan sát lỗi, quyền truy cập, hiệu năng và phương án khôi phục.
- Chỉ xóa cách lưu cũ khi chứng minh không còn thành phần phụ thuộc.

Mẫu này **không bắt buộc** cho mọi migration. Nếu thay đổi có tính không thể đảo ngược, cần đánh giá sao lưu, tính nhất quán, quyền và quy định vận hành. Đó là **đầu tư bảo vệ hiện tại**, không phải overengineering.

## 14. Tránh abstraction quá sớm và sự phức tạp tình cờ

Abstraction có ích khi giúp che một **ranh giới thay đổi thực**. Nếu tạo sai thời điểm, nó khiến một yêu cầu nhỏ phải đi qua quá nhiều file, lớp và chính sách.

### Dấu hiệu của abstraction suy đoán

- Interface một hiện thực nhưng tồn tại chủ yếu vì “sau này chắc có nhiều”.
- Các lớp Factory, Manager, Resolver và Registry hầu như chỉ chuyển lời gọi.
- Cấu hình cho nhiều trường hợp chưa có người sử dụng hoặc hành vi rõ.
- Reflection, dynamic discovery hoặc event bus được dùng cho một quy tắc đơn giản, ổn định.
- Mỗi thay đổi nghiệp vụ nhỏ phải sửa nhiều tầng liên quan một tương lai chưa xuất hiện.
- Người mới không thể lần theo hành trình “học viên nhấn lưu → phản hồi” mà không hiểu toàn bộ framework.

Một interface một hiện thực **không tự động sai**. Nó có thể là ranh giới có chủ đích để cách ly dịch vụ ngoài, bảo vệ miền khỏi phụ thuộc kỹ thuật hoặc thực hiện một hợp đồng đã được nhiều đội sử dụng. Cần hỏi **nó đang giải quyết vấn đề nào hôm nay**.

| Bối cảnh | Hướng thiết kế nên cân nhắc |
| --- | --- |
| Một quy tắc, một hiện thực, ít phụ thuộc | Hàm/lớp cụ thể, tên rõ và kiểm thử |
| Hai biến thể thật có cùng hợp đồng ổn định | Cân nhắc interface hoặc strategy |
| Tương tác dịch vụ bên ngoài phức tạp | Adapter/ràng buộc rõ để tránh trộn miền với hạ tầng |
| Cùng một quy tắc nghiệp vụ bị sao chép nhiều nơi | Gom về một nguồn sự thật khi có ý nghĩa |
| Hai đoạn mã giống cú pháp nhưng thay đổi vì lý do khác | Có thể chưa nên gộp |
| Các biến thể có dữ liệu, quy tắc rất khác nhau | Giữ mô hình riêng, tránh interface chung quá mơ hồ |

### DRY không có nghĩa phải gom mọi đoạn mã giống nhau

**DRY (Don't Repeat Yourself)** thường hữu ích khi **cùng một kiến thức hoặc quy tắc** bị sao chép khiến các bản có thể lệch nhau. Nếu hai đoạn mã chỉ tình cờ giống nhau nhưng thay đổi vì lý do khác, ép chúng vào một abstraction có thể tạo **coupling ngẫu nhiên**: sửa trường hợp A làm hỏng trường hợp B.

### Cohesion và coupling trong thiết kế đơn giản

- **Cohesion (mức gắn kết nội tại):** Thành phần có một mục đích rõ, các phần trong nó liên quan cùng trách nhiệm.
- **Coupling (mức phụ thuộc):** Thành phần phải biết nhiều chi tiết của thành phần khác tới mức nào.

Một thiết kế có tên rõ, trách nhiệm tập trung và ít phụ thuộc không cần thiết thường **dễ thay đổi** hơn thiết kế có nhiều lớp chỉ để đáp ứng mô hình lý tưởng. Nhưng giảm phụ thuộc bằng hàng trăm adapter không có nhu cầu cũng không tự làm mã tốt hơn.

### Một câu hỏi tự kiểm tra

> Nếu bỏ abstraction này, một hành vi đang dùng hoặc một yêu cầu chất lượng hiện tại có mất đi không? Nếu giữ nó, nhóm đang giảm rủi ro thật nào?

Nếu không trả lời được, abstraction có thể là ứng viên để **chưa tạo hoặc refactor bỏ bớt**.

## 15. Giữ khả năng đổi hướng mà không xây trọn sản phẩm tương lai

Một số lựa chọn nhỏ có thể **giữ quyền lựa chọn (optionality)** mà không phải phát triển luôn chức năng chưa chắc cần.

| Rủi ro tương lai | Bước nhỏ có thể cân nhắc | Điều chưa cần xây |
| --- | --- | --- |
| Có thêm loại bài học | Đặt tên khái niệm tiến độ rõ, không gắn UI với schema tùy tiện | Toàn bộ plugin framework |
| Có nhiều phiên bản client | Giữ hợp đồng API tương thích với client đang dùng | Cơ chế thương lượng mọi phiên bản giả định |
| Có thể thay dịch vụ ngoài | Đặt ranh giới rõ tại lời gọi đã tồn tại | Registry cho mười nhà cung cấp chưa dùng |
| Dữ liệu tăng và phải migration | Định danh, phân quyền và đường chuyển đổi an toàn | Microservice hóa mọi module |
| Muốn phát hành nhỏ thường xuyên | Tự động hóa build/test phù hợp, ghi log thiết yếu | Tự xây nền tảng orchestration hoàn chỉnh |

### Phân biệt phương án có thể đảo ngược

Một lựa chọn có thể đổi bằng refactor nhỏ và kiểm thử thường không đáng đầu tư hàng tuần để “future-proof”. Nhưng nếu việc đổi sau này có thể **làm mất dữ liệu, phá hợp đồng công khai hoặc yêu cầu ngừng hệ thống dài**, cần điều tra sớm hơn.

Mục tiêu không phải luôn “hoãn quyết định càng lâu càng tốt”; là **quyết định tại thời điểm có đủ thông tin, trước khi chi phí chậm quyết định trở nên nguy hiểm**.

### Bảng cân nhắc định tính

| Tiêu chí | Nếu câu trả lời là “cao” | Cách ứng xử |
| --- | --- | --- |
| Giá trị hiện tại | Người dùng đang bị ảnh hưởng rõ | Ưu tiên lát cắt có thể bàn giao |
| Mức bất định | Chưa biết đúng nhu cầu hoặc giải pháp | Ví dụ nghiệp vụ, thí điểm hoặc spike |
| Chi phí đổi sau | Phải migration nhiều dữ liệu hoặc client | Thiết kế ranh giới và tương thích sớm |
| Chi phí xây trước | Cần nhiều tuần framework và vận hành | Tránh nếu thiếu bằng chứng đủ mạnh |
| Rủi ro chất lượng | Có nguy cơ mất dữ liệu hoặc vi phạm quyền | Đưa kiểm soát vào thiết kế ngay |
| Khả năng quan sát | Chưa đo được tác động sau phát hành | Đầu tư tín hiệu tối thiểu đáng tin |

Không cần chấm một con số tổng giả chính xác cho các tiêu chí. **Trao đổi về sự đánh đổi và điều chưa biết** quan trọng hơn một bảng điểm cứng.

## 16. Kiểm tra thiết kế bằng các “fitness function” vừa đủ

Khi hệ thống phát triển, nhóm cần biết thiết kế có còn **đáp ứng những tính chất quan trọng** hay không. Một cách tiếp cận của kiến trúc tiến hóa là sử dụng **architecture fitness functions** — những phép kiểm hoặc tín hiệu cho biết một thuộc tính kiến trúc có còn được bảo vệ.

Trong một ứng dụng nhỏ, fitness function không cần là bộ công cụ phức tạp. Nó có thể là **kiểm thử, quy tắc phân tích mã, chỉ số vận hành hoặc phép xác minh rõ ràng**.

| Thuộc tính muốn bảo vệ | Ví dụ kiểm chứng | Giới hạn |
| --- | --- | --- |
| **Tính đúng của tiến độ** | Kiểm thử không ghi đè sai và khôi phục đúng | Phải bao quát các ranh giới tích hợp quan trọng |
| **Phân quyền** | Kiểm thử tài khoản A không đọc dữ liệu của B | Cần đánh giá rủi ro bảo mật đầy đủ khi thích hợp |
| **Khả năng tích hợp** | Build và contract tests chạy trên CI | Test xanh chưa chứng minh hệ thống thật không lỗi |
| **Độ tin cậy vận hành** | Tỷ lệ lỗi lưu, độ trễ, tín hiệu sự cố | Phải có cách phân biệt biến động và lỗi thật |
| **Khả năng đổi cấu trúc** | Kiểm thử hồi quy khi refactor một quy tắc | Thời gian sửa còn phụ thuộc độ phức tạp yêu cầu |
| **Thời gian phản hồi** | Pipeline kiểm thử nhanh và có tín hiệu hữu ích | Không làm test quá nông để chỉ tăng tốc |

**Đừng xây hệ thống đo lường kiến trúc quá mức.** Chọn một số thuộc tính có rủi ro thật; chỉ tăng kiểm chứng khi có vấn đề hoặc yêu cầu mới.

### Khi nào fitness function trở thành gánh nặng?

Nếu mỗi thay đổi nhỏ phải qua hàng trăm bước ít liên quan, phản hồi tới Developers sẽ chậm. Hãy xem kiểm tra nào cần chạy **ngay trong vòng phát triển**, kiểm tra nào cần chạy trước phát hành và kiểm tra nào giám sát sau phát hành, luôn giữ những kiểm soát bắt buộc.

## 17. Thiết kế tiến hóa cần vòng phản hồi sản phẩm

Thiết kế đơn giản chỉ tạo lợi thế khi nhóm có cách biết **điều gì cần xây tiếp**.

~~~mermaid
flowchart TD
    A["Product Goal / vấn đề người dùng"] --> B["Giả thuyết và lát cắt nhỏ"]
    B --> C["Thiết kế đơn giản, đúng và an toàn"]
    C --> D["Kiểm thử + CI + Increment"]
    D --> E["Bàn giao / thí điểm / quan sát"]
    E --> F{"Có bằng chứng cần thay đổi?"}
    F -->|Có| G["Làm rõ và refactor/mở rộng có mục tiêu"]
    F -->|Chưa| H["Giữ thiết kế, không thêm khả năng suy đoán"]
    G --> B
    H --> A
~~~

### Phản hồi có thể thay đổi ưu tiên

Product Owner dự định phát triển đồng bộ offline sau khi có chức năng lưu tiến độ. Nhưng học viên thí điểm phản ánh rằng **thông báo trạng thái lưu gây hiểu nhầm**. Nhóm có thể ưu tiên sửa trải nghiệm và tính đáng tin cậy trước, thay vì xây offline chỉ vì tính năng ấy đã được ghi trong roadmap.

Đó là **phát triển thích ứng**: Product Backlog và cấu trúc phần mềm đều có thể thay đổi theo bằng chứng. Roadmap giúp định hướng nhưng không phải hợp đồng bất biến cho mọi chi tiết.

### Các nguồn phản hồi bổ sung nhau

- **BDD / ví dụ nghiệp vụ:** Nhận phản hồi về cách hiểu yêu cầu.
- **TDD và kiểm thử tự động:** Nhận phản hồi về hành vi mã.
- **Continuous Integration:** Nhận phản hồi về khả năng tích hợp.
- **Sprint Review / thử nghiệm với người dùng:** Nhận phản hồi về sản phẩm và giá trị.
- **Quan sát vận hành:** Nhận phản hồi về lỗi, hiệu năng và độ tin cậy.
- **Retrospective / phân tích dòng công việc:** Nhận phản hồi về cách phối hợp và chi phí thay đổi.

Không nguồn nào một mình chứng minh **sản phẩm đang tạo đủ giá trị**. Thiết kế tiến hóa cần liên tục kết nối phản hồi kỹ thuật với kết quả người dùng.

## 18. Scrum: thiết kế vừa đủ để hướng tới Sprint Goal và Product Goal

Theo Scrum, **Product Owner** chịu trách nhiệm tối đa hóa giá trị và quản lý Product Backlog; **Developers** chịu trách nhiệm xây Increment đáp ứng Definition of Done và lập kế hoạch thực hiện; **Scrum Master** hỗ trợ áp dụng Scrum cùng hiệu quả Scrum Team.

### Trong Product Backlog refinement

Các góc nhìn nghiệp vụ và phát triển làm rõ:

- Giá trị **bắt buộc hiện tại** là gì?
- Điều kiện chất lượng nào **không thể trì hoãn**?
- Phần nào là giả định chưa có bằng chứng?
- Có thể chia thành **lát cắt dọc** cho người dùng thử sớm không?
- Có quyết định khó đảo ngược nào cần một **spike có giới hạn**?

### Sprint Planning

Sprint Goal mô tả **kết quả có giá trị**, không phải “hoàn thành framework tiến độ v2”. Developers chọn PBI và lập kế hoạch dựa trên năng lực, rủi ro và Definition of Done. Một thiết kế lớn không tự trở thành Sprint Goal chỉ vì đã lên kế hoạch từ trước.

### Trong Sprint

Developers có thể triển khai vừa đủ, refactor và tích hợp liên tục. Không dùng YAGNI để bỏ kiểm thử hoặc chất lượng. Khi hiểu biết thay đổi, Developers và Product Owner có thể làm rõ và thương lượng phạm vi mà không gây nguy hại Sprint Goal.

### Sprint Review và Retrospective

**Sprint Review** giúp nhìn Increment, kết quả người dùng và bối cảnh để điều chỉnh Product Backlog. **Sprint Retrospective** giúp kiểm tra chi phí thay đổi, chất lượng và cách phối hợp, từ đó cải tiến thực hành thiết kế.

**Scrum không bắt buộc dùng một design pattern, bộ nguyên tắc YAGNI cụ thể hay tỷ lệ refactoring cố định.** Chúng là những lựa chọn thực hành kỹ thuật để tạo giá trị hiệu quả.

## 19. Kanban và Lean: thấy “tồn kho kiến trúc” làm chậm dòng giá trị

Theo Lean, công việc đã bắt đầu nhưng chưa bàn giao là **công việc dở dang**, có thể tạo hàng chờ và tăng thời gian tới giá trị. Một framework tương lai xây mãi chưa xong có thể chiếm năng lực trong khi người dùng vẫn chưa nhận phần cải tiến nhỏ họ cần.

~~~text
Product Backlog có thứ tự
          |
          v
Sẵn sàng -> Phát triển -> Chờ review -> Kiểm thử -> Done
                |
                +-- [BLOCKED: chờ quyết định offline chưa được ưu tiên]
~~~

Nếu story hiện tại chỉ là lưu tiến độ **cùng một thiết bị**, nhưng code bị chặn vì phải chốt mọi chiến lược offline, nhóm cần hỏi:

> Phụ thuộc này có thật sự cần cho lát cắt đang làm, hay ta đã đưa một khả năng chưa được xác nhận vào phạm vi quá sớm?

Nếu chưa cần, có thể tách câu hỏi offline ra khỏi story hiện tại và tiếp tục một lát cắt có giá trị.

| Tín hiệu | Câu hỏi | Lưu ý |
| --- | --- | --- |
| **WIP** | Có nhiều hạng mục mở chỉ vì kiến trúc rộng? | Không ẩn thẻ blocked để giảm số giả |
| **Cycle time** | Từ bắt đầu tới Done mất bao lâu? | Giữ ranh giới đo nhất quán |
| **Throughput** | Có bao nhiêu hạng mục có ý nghĩa hoàn tất? | Chia ticket nhỏ hơn có thể làm số tăng |
| **Thời gian chờ quyết định** | Kiến trúc đang chờ giả định chưa rõ bao lâu? | Có quyết định thật cần người có thẩm quyền |
| **Làm lại** | Có sửa lớn sau phản hồi vì hiểu sai? | Không xem mọi lần học hỏi là thất bại |
| **Lỗi hồi quy** | Việc refactor có an toàn không? | Không tăng tốc bằng cách bỏ kiểm thử |
| **Time to value/feedback** | Người dùng nhận và phản hồi sớm hơn? | Phân biệt deployment, release và outcome |

Không nên dùng số lớp, số interface hoặc số design pattern làm KPI kiến trúc. Những con số đó không trực tiếp biểu đạt tính đúng, giá trị hay chi phí thay đổi.

## 20. XP và tích hợp liên tục giúp thiết kế phát triển an toàn

XP cung cấp nhiều thực hành bổ trợ cho thiết kế tiến hóa:

| Thực hành | Vai trò |
| --- | --- |
| **TDD** | Bảo vệ hành vi hiện tại, hướng tới hiện thực vừa đủ |
| **Refactoring** | Loại bỏ phức tạp phát sinh, cải thiện cấu trúc |
| **Simple Design** | Tránh khả năng chưa được sử dụng |
| **Pair Programming** | Phản biện thiết kế, chia sẻ hiểu biết và rủi ro |
| **Collective Code Ownership** | Giảm phụ thuộc vào một chuyên gia khi sửa cấu trúc |
| **Continuous Integration** | Phát hiện lỗi tích hợp sớm, khuyến khích thay đổi nhỏ |
| **Small Releases** | Đưa giá trị và giả thuyết ra kiểm chứng sớm |

### Vì sao refactor nhỏ thường ít rủi ro hơn “đại tu” kéo dài?

Một thay đổi nhỏ, có kiểm thử và tích hợp sớm giúp đội **thu hẹp vùng tìm lỗi** nếu có sai. Một đợt viết lại lớn có nhiều giả định chưa kiểm chứng, khác biệt hành vi và nguy cơ tích hợp. Nhưng những migration lớn vẫn có thể cần thiết khi ràng buộc đã thay đổi. CI và test **giúp quản lý rủi ro**, không loại bỏ mọi rủi ro.

~~~text
Nhu cầu và quy tắc đã hiểu
  -> Kiểm thử quan trọng
  -> Hiện thực đủ đúng
  -> Refactor một bước
  -> Chạy kiểm thử + CI
  -> Tích hợp và hoàn tất theo DoD
  -> Quan sát phản hồi
  -> Chỉ mở rộng thiết kế khi có lý do
~~~

Nếu pipeline thử nghiệm/triển khai thủ công đang **làm chậm mọi thay đổi hiện tại**, cải thiện nó là một nhu cầu thực tế — không phải vi phạm YAGNI. Điều cần tránh là tự xây một nền tảng CI/CD tổng quát vượt nhu cầu và năng lực vận hành.

## 21. Spike: giảm bất định mà không xây cả tính năng tương lai

Khi một quyết định kỹ thuật có rủi ro cao nhưng chưa có bằng chứng, nhóm có thể làm **spike (nghiên cứu hoặc thử nghiệm có mục tiêu và giới hạn)** thay vì triển khai trọn một framework.

### Ví dụ spike cho đồng bộ tiến độ

~~~text
CÂU HỎI:
  Nếu phản hồi lưu đến muộn, có thể bảo vệ tiến độ
  mới hơn mà không ghi đè sai trong hệ thống hiện tại?

PHẠM VI:
  Mô phỏng một tài khoản, một bài học và một số sự kiện
  ghi/đọc đến theo các thứ tự khác nhau.

GIỚI HẠN:
  Không xây offline đầy đủ, plugin framework
  hoặc giao diện cấu hình.

BẰNG CHỨNG:
  Kết quả thử, rủi ro, phương án khả thi,
  câu hỏi nghiệp vụ cần được quyết định.

KẾT LUẬN:
  Bỏ giả định, chia lát cắt hoặc đầu tư tiếp
  nếu Product Backlog có lý do và ưu tiên rõ.
~~~

Đầu ra của spike là **kiến thức giúp quyết định**, không mặc nhiên là Increment có giá trị sử dụng. Nếu sau mỗi spike nhóm cứ mở thêm phạm vi không được ưu tiên, spike đã trở thành cách lách YAGNI.

### Khi nào không cần spike?

Nếu câu hỏi có thể trả lời bằng một kiểm thử đơn giản, tài liệu hiện có của hệ thống hoặc trao đổi ngắn với người có chuyên môn, một spike nhiều ngày có thể không đáng chi phí. Chọn cách **rẻ nhất đủ trả lời rủi ro quan trọng**.

## 22. Case study xuyên suốt: từ overengineering đến thiết kế tiến hóa

**Bối cảnh giả định:** Đội phát triển nền tảng học trực tuyến muốn giảm việc học viên phải học lại. Sản phẩm đã có cơ sở dữ liệu và một API tiến độ cơ bản. Chưa có bằng chứng đủ rõ cho yêu cầu offline đa thiết bị.

### Giai đoạn 1 — Đề xuất ban đầu quá rộng

Nhóm dự định làm:

- Plugin cho nhiều dịch vụ lưu trữ chưa có khách hàng.
- Workflow engine tùy biến mọi trạng thái bài học.
- Cơ chế xung đột đa thiết bị hỗ trợ mọi chiến lược.
- Event bus riêng cho từng bước tiến độ.
- Admin dashboard tự cấu hình quy tắc.
- Tính năng offline khi chưa có nghiên cứu ưu tiên.

**Hậu quả có thể xảy ra:** Nhiều module chưa hoàn tất, kiểm thử tích hợp khó, kiến thức tập trung ở người thiết kế framework, và người học vẫn chưa thử được lưu/khôi phục cơ bản.

### Giai đoạn 2 — Làm rõ vấn đề và rủi ro

Product Owner, Developers và người có góc nhìn kiểm thử/hiểu nghiệp vụ cùng hỏi:

1. Người học đang mất giá trị ở đâu?
2. Lát cắt nhỏ nào có thể giải quyết một phần vấn đề ngay?
3. Yêu cầu bảo vệ dữ liệu và độ tin cậy nào bắt buộc?
4. Khả năng tương lai nào còn thiếu bằng chứng?
5. Quyết định khó đảo ngược nào cần nghiên cứu trước?

Nhóm chọn lát cắt: **lưu tiến độ được xác nhận và khôi phục trên cùng tài khoản, với trạng thái lỗi trung thực**. Offline và plugin không thuộc phạm vi đầu.

### Giai đoạn 3 — Hiện thực, kiểm chứng và nhận phản hồi

Nhóm:

- Viết ví dụ chấp nhận cho lưu thành công, chưa xác nhận và dữ liệu không hợp lệ.
- Dùng quy tắc tiến độ rõ và hệ thống dữ liệu hiện có khi phù hợp.
- Kiểm chứng quyền truy cập, tính bền vững và xử lý lỗi theo yêu cầu.
- Có unit tests cho miền và integration tests cho đường đọc/ghi.
- Tích hợp thay đổi nhỏ, review phù hợp và giữ Definition of Done.
- Cho người dùng thử trong phạm vi an toàn và quan sát kết quả.

Phản hồi xuất hiện: “Tôi không biết trạng thái đang đồng bộ có an toàn để đóng trang không.” Đội có thể làm rõ thông điệp **ngay**, không cần đợi framework tiến độ hoàn thành.

### Giai đoạn 4 — Một nhu cầu mới có bằng chứng

Sau khi quan sát, nhóm xác nhận nhiều học viên chuyển qua lại giữa hai thiết bị. Product Owner ưu tiên đồng bộ. Các ví dụ nghiệp vụ mới gồm:

- Cập nhật trên A phải xuất hiện hợp lý trên B.
- Một phản hồi cũ không được âm thầm ghi đè dữ liệu mới.
- Quy tắc học lại có chủ đích phải được thống nhất.
- Không thông báo sai rằng đã đồng bộ khi mạng thất bại.

Giờ đây Developers có **bằng chứng về hành vi cần hỗ trợ**, có thể đánh giá lại mô hình tiến độ, hợp đồng API và cơ chế xung đột. Họ refactor theo bước, migration dữ liệu có kiểm soát khi cần, duy trì test của hành vi cũ.

### Kết quả quan sát

| Góc nhìn | Tín hiệu có ích | Giới hạn |
| --- | --- | --- |
| **Giá trị người học** | Số sự cố mất tiến độ, khả năng tiếp tục học, phản hồi về thông báo | Có nhiều yếu tố cùng tác động |
| **Dòng công việc** | Time to feedback, cycle time, blocked work | Cần so cùng loại công việc và ranh giới |
| **Chất lượng** | Lỗi hồi quy, sự cố dữ liệu, thời gian phục hồi | Không bỏ test để cải thiện tốc độ |
| **Khả năng đổi thiết kế** | Thời gian thêm quy tắc thật, số phụ thuộc cần sửa, hiểu biết của nhóm | Không chỉ đếm số file thay đổi |
| **Chi phí kiến trúc** | Cơ chế đang bảo trì nhưng chưa phục vụ nhu cầu | Không xóa kiểm soát bắt buộc chỉ để ít lớp |

**Kết luận:** Thiết kế tiến hóa không chọn một kiến trúc hoàn hảo từ đầu. Nó **đầu tư khi có bằng chứng, giữ kỷ luật chất lượng và bảo vệ khả năng thay đổi tiếp**.

## 23. Những phản mẫu thường gặp

| Phản mẫu | Hậu quả | Cách cải thiện |
| --- | --- | --- |
| **Xây framework trước use case thật** | Khởi tạo tốn công, abstraction có thể sai | Bắt đầu từ hành vi thật, xem điểm biến thiên |
| **Dùng YAGNI để bỏ bảo mật và kiểm thử** | Rủi ro dữ liệu, lỗi nghiêm trọng | Coi chất lượng/an toàn là ràng buộc hiện tại |
| **Coi đơn giản là ít dòng mã** | Mã khó hiểu và khó thay đổi | Ưu tiên ý định rõ và kiểm thử |
| **Tạo interface cho mọi lớp** | Nhiều lớp chuyển tiếp, chi phí hiểu cao | Chọn ranh giới có lý do cụ thể |
| **Gộp mã chỉ vì giống cú pháp** | Coupling giữa quy tắc không liên quan | Xem cùng kiến thức và lý do thay đổi |
| **Không refactor vì “chưa cần”** | Phức tạp tích tụ, sửa lỗi ngày càng khó | Refactor nhỏ khi có vấn đề hiện hữu |
| **Refactor lớn thiếu test** | Dễ sai hành vi, khó tìm nguyên nhân | Viết test bảo vệ, thay đổi từng bước |
| **Đóng băng thiết kế từ đầu** | Không thích ứng khi có bằng chứng mới | Ghi điều kiện xem lại quyết định |
| **Mỗi Sprint đổi cả kiến trúc** | Bất ổn và lặp chi phí tích hợp | Thay đổi theo nhu cầu và rủi ro thực |
| **Mở nhiều tính năng tương lai cùng lúc** | WIP lớn, ít Increment hoàn thành | Chia lát cắt, giới hạn WIP |
| **Chọn công nghệ vì đang phổ biến** | Vận hành thêm nhưng không giải quyết vấn đề | Đánh giá chi phí và yêu cầu thật |
| **Tối ưu module, bỏ qua dòng giá trị** | Hàng đợi review/kiểm thử vẫn cao | Đo end-to-end time to feedback |
| **Không ghi lý do quyết định khó đảo ngược** | Người sau đoán và tranh luận lại | Ghi decision note ngắn |
| **Dùng feature flag che tính năng chưa an toàn** | Rủi ro khi bật, chất lượng mơ hồ | Giữ kiểm thử, DoD và chính sách phát hành |
| **Xem mọi thay đổi yêu cầu là thất bại** | Cố giữ giải pháp cũ dù không còn giá trị | Phân biệt học hỏi hợp lý và lỗi chất lượng |

## 24. Bài thực hành: chọn thiết kế vừa đủ

### Bài 1 — Phân loại nhu cầu hiện tại và giả thuyết tương lai

Một đội đang chuẩn bị chức năng tiếp tục học:

1. Đăng nhập và đọc lại đúng tiến độ của tài khoản.
2. API xác nhận lưu trước khi UI tuyên bố đã lưu.
3. Plugin cho mười dịch vụ lưu trữ chưa có khách hàng.
4. Ngăn người dùng đọc tiến độ của tài khoản khác.
5. Chế độ offline đa thiết bị chưa có nghiên cứu.
6. Kiểm thử hồi quy cho mất mạng và phản hồi chậm.
7. Dashboard cấu hình mọi quy tắc cho đối tác chưa ký.

Hãy phân loại thành **cần ngay**, **cần bằng chứng** và **cần làm rõ rủi ro**; giải thích tại sao không thể lấy YAGNI làm lý do hoãn bảo vệ dữ liệu.

**Gợi ý:** Trong phạm vi đã xác nhận, (1), (2), (4), (6) có ý nghĩa trực tiếp; (3), (5), (7) có dấu hiệu suy đoán. Nếu có hợp đồng hoặc rủi ro đã biết, phân loại cần được cập nhật.

### Bài 2 — So sánh hai thiết kế

**Phương án A:** Một mô hình miền tuyến tính với hàm rõ nghĩa, kiểm thử bảo vệ và dịch vụ lưu hiện có.

**Phương án B:** Plugin framework cho mọi kiểu tiến độ, nhiều strategy và registry dù chỉ một strategy đang được dùng.

Hãy đánh giá:

- Khả năng đáp ứng hành vi hiện tại.
- Chi phí hiểu, kiểm thử, triển khai và duy trì.
- Phần nào có thể thay đổi nếu có kiểu bài học thứ hai.
- Kiểm soát an toàn nào bắt buộc ở cả hai.
- **Bằng chứng gì** có thể khiến phương án B hoặc một phương án trung gian hợp lý hơn.

### Bài 3 — Refactor dựa trên kiểm thử

Dùng hàm Java ở mục 6:

1. Giải thích ý nghĩa ba tham số.
2. Nêu trường hợp hoàn thành bước vượt tổng số bước phải bị từ chối.
3. Viết thêm kiểm thử sự kiện cũ không làm giảm tiến độ.
4. Tách logic validation thành một hàm rõ nghĩa hoặc đổi tên để tăng khả năng hiểu; chạy lại test.
5. Chỉ rõ hành vi **chưa được unit test chứng minh** như ghi bền vững, đồng thời và phân quyền.

**Tiêu chí đánh giá:** Refactor giữ hành vi hiện tại; không xây thêm framework vì một bài tập nhỏ.

### Bài 4 — Chọn lúc nào tạo abstraction

| Tình huống | Câu hỏi |
| --- | --- |
| Một nhà cung cấp lưu trữ đang dùng | Có ranh giới hiện tại nào thực sự cần adapter không? |
| Hai loại bài học có tiến độ khác nhau | Điểm chung và điểm khác đã được làm rõ chưa? |
| Hai hàm trùng cú pháp nhưng nghiệp vụ khác | Gộp có tạo coupling sai không? |
| API công khai có nhiều client | Điều gì khó đảo ngược và cần tương thích? |
| Một thao tác đơn giản phải đi qua mười wrapper | Mỗi lớp giải quyết rủi ro thực nào? |

Chọn **giữ mã cụ thể, tạo abstraction có mục đích, làm rõ nghiệp vụ hoặc thực hiện spike** và nêu lý do.

### Bài 5 — Thiết kế spike có giới hạn

Đội lo sau này cần đồng bộ hai thiết bị nhưng chưa biết quy tắc xử lý xung đột.

Viết:

- Một câu hỏi kỹ thuật/nghiệp vụ **có thể kiểm chứng**.
- Phạm vi mô phỏng nhỏ, không xây offline đầy đủ.
- Bằng chứng cần thu: những thứ tự sự kiện và dữ liệu kết quả.
- Giới hạn đầu tư và **điều kiện dừng**.
- Người có thẩm quyền xác nhận quy tắc.
- Điều kiện khiến Product Backlog ưu tiên phát triển tiếp.

Giải thích vì sao **spike cho ra hiểu biết**, chưa chắc là Increment có thể dùng.

### Bài 6 — Lập kế hoạch ba vòng phát triển

**Vòng 1:** Lưu/khôi phục có kết nối trên một thiết bị, đủ an toàn.

**Vòng 2:** Dùng phản hồi người học để sửa thông điệp hoặc độ tin cậy.

**Vòng 3:** Chỉ mở rộng đa thiết bị khi có bằng chứng và quy tắc đã làm rõ.

| Vòng | Giá trị cần kiểm chứng | Thiết kế vừa đủ | Kiểm thử bảo vệ | Tín hiệu quyết định tiếp |
| --- | --- | --- | --- | --- |
| 1 | ... | ... | ... | ... |
| 2 | ... | ... | ... | ... |
| 3 | ... | ... | ... | ... |

Nếu vòng 1 cho thấy nhiều học viên mất dữ liệu, hãy giải thích vì sao **ưu tiên sửa độ tin cậy** có thể quan trọng hơn mở rộng tính năng.

### Bài 7 — Thử cải tiến hai Sprint

Nhóm có nhiều story chờ một framework chung chưa hoàn thành:

~~~text
VẤN ĐỀ:
  Các lát cắt nhỏ phụ thuộc vào framework tương lai,
  tăng WIP và thời gian tới Increment có thể dùng.

GIẢ THUYẾT:
  Nếu bỏ phụ thuộc không bắt buộc và thiết kế vừa đủ
  với test bảo vệ, nhóm nhận phản hồi sớm hơn.

THỬ NGHIỆM:
  Hoàn tất một luồng lưu/khôi phục an toàn;
  chưa xây plugin cho use case chưa xác nhận.

QUAN SÁT:
  Cycle time, thời gian chờ, lỗi dữ liệu,
  khả năng sửa mã và phản hồi học viên.

CHỈ SỐ BẢO VỆ:
  Definition of Done, kiểm thử tích hợp,
  phân quyền và lỗi sau bàn giao.

XEM LẠI:
  Cuối mỗi Sprint; đánh giá sau hai Sprint.
~~~

**Hỏi thêm:** Vì sao cycle time giảm nhưng lỗi dữ liệu tăng **không** phải thành công của thiết kế tiến hóa?

## 25. Checklist thiết kế đơn giản nhưng đáng tin cậy

- [ ] Nhóm hiểu **người dùng, vấn đề và kết quả mong muốn**, không chỉ tên công nghệ.
- [ ] Phạm vi lát cắt và điều **chưa bao gồm** được ghi rõ.
- [ ] Mỗi khả năng xây thêm có **bằng chứng, ràng buộc hoặc rủi ro** cụ thể.
- [ ] Không xây plugin, framework hoặc cấu hình chỉ vì “sau này có thể cần”.
- [ ] Bảo mật, dữ liệu, tính đúng và tuân thủ **hiện tại** vẫn được bảo vệ.
- [ ] Mã dễ **đọc, kiểm chứng và sửa**, không chỉ ít dòng.
- [ ] Abstraction có mục đích thực và ranh giới rõ.
- [ ] Trùng lặp được xem theo **kiến thức nghiệp vụ**, không chỉ cú pháp.
- [ ] Quyết định kiến trúc khó đảo ngược được đánh giá và ghi lý do.
- [ ] Có kiểm thử thích hợp trước khi refactor hành vi quan trọng.
- [ ] Thay đổi được tích hợp và kiểm chứng thường xuyên.
- [ ] Câu hỏi chưa rõ có thể được xử lý bằng **spike giới hạn**, không âm thầm mở phạm vi.
- [ ] Product Backlog có thể thay đổi khi nhận **phản hồi thực tế**.
- [ ] Không tích tụ WIP lớn chỉ để xây hạ tầng chưa có use case.
- [ ] Chỉ số thời gian, chất lượng và outcome có **ranh giới cùng bối cảnh rõ**.
- [ ] Cải tiến kỹ thuật được đánh giá qua **Increment có giá trị**, không qua số pattern.

## 26. Câu hỏi ôn tập

1. “Thiết kế đơn giản” khác “viết ít dòng mã” như thế nào?
2. KISS, YAGNI và thiết kế tiến hóa bổ trợ nhau ra sao?
3. Những tín hiệu nào cho thấy nhóm đang tổng quát hóa cho tương lai suy đoán?
4. Bằng chứng nào khiến một khả năng tương lai thành nhu cầu thực sự?
5. Vì sao không được dùng YAGNI để bỏ kiểm thử hoặc bảo vệ dữ liệu?
6. Một chính sách tiến độ tuyến tính sẽ không còn đủ trong những trường hợp nào?
7. Khi nào nên tạo abstraction theo biến thể thật thay vì dự đoán?
8. Refactoring khác viết lại toàn bộ ở điểm nào?
9. TDD, BDD và CI giúp thay đổi thiết kế an toàn thế nào?
10. Vì sao unit test xanh chưa chứng minh lưu dữ liệu, phân quyền hoặc đồng thời đúng?
11. Một quyết định kiến trúc khó đảo ngược là gì? Nêu ví dụ liên quan API hoặc dữ liệu.
12. Expand–migrate–contract giúp giảm rủi ro thay đổi schema thế nào?
13. Có phải mọi đoạn mã giống cú pháp đều nên gộp lại theo DRY?
14. Những bước nhỏ nào giữ khả năng đổi hướng mà không xây tính năng tương lai?
15. Architecture fitness function có thể đơn giản tới mức nào?
16. Khi nào nên thực hiện spike thay vì xây trọn một framework?
17. Product Owner, Developers và Scrum Master liên quan đến phạm vi và quyết định kỹ thuật ra sao?
18. Kanban/Lean có thể làm lộ chi phí của overengineering ở dòng công việc như thế nào?
19. Vì sao cycle time giảm nhưng tỷ lệ lỗi dữ liệu tăng không phải cải tiến tốt?
20. Trong case study, phản hồi nào có thể khiến Product Owner ưu tiên sửa độ tin cậy trước khi xây offline?

**Ghi nhớ:** **Thiết kế tiến hóa không đồng nghĩa lười thiết kế hay bỏ mọi quyết định dài hạn.** Nó yêu cầu đầu tư **đủ cho nhu cầu và chất lượng đã có bằng chứng**, chọn giải pháp **đơn giản, rõ nghĩa và kiểm chứng được**, tránh tính năng suy đoán theo tinh thần **YAGNI**, rồi **refactor an toàn** khi hiểu biết mới xuất hiện. Hãy bảo vệ những quyết định khó đảo ngược, dữ liệu và tiêu chuẩn chất lượng; chia sản phẩm thành lát cắt có ích, tích hợp và kiểm thử sớm, đo thời gian cùng kết quả người dùng. Giá trị của thiết kế không nằm ở số tầng abstraction hay số design pattern, mà ở **khả năng liên tục tạo giá trị và thay đổi đúng hướng với chi phí, rủi ro chấp nhận được**.
