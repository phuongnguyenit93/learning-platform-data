# Tái cấu trúc an toàn nhờ bằng chứng kiểm thử

## 1. Vì sao thiết kế tiến hóa cần khả năng refactor an toàn?

Một Scrum Team phát triển nền tảng học trực tuyến đã bàn giao chức năng “Tiếp tục học”. Trong phiên bản đầu tiên, quy tắc xác định bài tiếp theo nằm trong một service nhỏ. Vài Sprint sau, nền tảng có khóa tuyến tính, khóa cho phép học tự chọn, học viên chuyển thiết bị và các điều kiện quyền truy cập phức tạp hơn. Cùng một quy tắc bị sao chép sang API, trang khóa và tác vụ gửi nhắc học.

Khi Product Owner đề xuất thay đổi “học viên đã hoàn thành bài cuối cần thấy trạng thái hoàn thành”, Developers thấy một việc đáng lo: sửa một đoạn mã có thể làm sai đường dẫn học, báo cáo tiến độ hoặc quyền truy cập. Nhóm có hai lựa chọn không tốt: **ngại thay đổi vì sợ làm hỏng hệ thống**, hoặc **chỉnh mã thật nhanh nhưng để lỗi xuất hiện muộn trong production**.

**Thiết kế tiến hóa (evolutionary design)** nhìn thiết kế phần mềm như thứ được hoàn thiện liên tục khi nhóm hiểu rõ hơn về nhu cầu, dữ liệu, quy tắc và giới hạn kỹ thuật. Thay vì dự đoán toàn bộ kiến trúc ngay từ đầu, nhóm xây đủ cấu trúc cho vấn đề hiện tại, kiểm tra giả định, rồi cải thiện cấu trúc khi có bằng chứng mới.

**Refactoring (tái cấu trúc mã)** là việc thay đổi **cấu trúc nội bộ** của phần mềm trong khi **giữ nguyên hành vi có thể quan sát** theo hợp đồng hiện tại. Nó giúp mã dễ hiểu, giảm trùng lặp và giảm chi phí cho thay đổi tiếp theo. **Kiểm thử** là một nguồn bằng chứng quan trọng rằng thay đổi cấu trúc không vô tình phá hỏng hành vi đang được sử dụng.

Ví dụ:

- Đổi hai đoạn kiểm tra tiến độ trùng nhau thành một hàm dùng chung, giữ nguyên kết quả đầu ra: **refactoring**.
- Thay quy tắc “bài tiếp theo theo thứ tự” thành “bài được hệ thống gợi ý”: **thay đổi hành vi nghiệp vụ**.
- Đổi endpoint đang được ứng dụng di động sử dụng mà không hỗ trợ tương thích: **thay đổi hợp đồng bên ngoài**, không thể tự gọi là refactoring an toàn.
- Bổ sung kiểm thử quanh chức năng cũ trước khi sửa cấu trúc: **tạo hàng rào phản hồi**, giúp refactor có căn cứ.

Trong phạm vi **AGILE_DEVELOPMENT**, kỹ thuật này hỗ trợ việc giao Increment tăng dần, nhận phản hồi sớm và thay đổi linh hoạt qua Scrum, Kanban, XP. TDD, kiểm thử hồi quy, tích hợp liên tục và Definition of Done giúp nhóm thay đổi thiết kế **mà không phải đánh đổi chất lượng mỗi khi có user story mới**.

> **Nguyên tắc cốt lõi:** Refactor không phải “viết lại cho đẹp”. Hãy xác định hợp đồng cần giữ, bảo vệ nó bằng kiểm thử có ý nghĩa, thay đổi cấu trúc từng bước nhỏ và kiểm tra liên tục.

## 2. Refactoring, sửa lỗi, thêm tính năng và viết lại hệ thống khác nhau thế nào?

Trong một cuộc thảo luận kỹ thuật, câu “Chúng ta cần refactor” có thể che giấu nhiều mục đích khác nhau. Cần phân loại để biết **bằng chứng, rủi ro và cách lập kế hoạch** phù hợp.

| Hoạt động | Mục đích chính | Hành vi quan sát được | Ví dụ |
| --- | --- | --- | --- |
| **Refactoring** | Cải thiện cấu trúc, tính dễ hiểu và khả năng sửa đổi | **Giữ nguyên theo hợp đồng đang được bảo vệ** | Trích xuất hàm kiểm tra tiến độ trùng lặp |
| **Sửa lỗi (bug fix)** | Sửa hành vi sai so với quy tắc đúng | **Thay đổi từ sai sang đúng** | Ngăn người không có quyền mở bài qua liên kết trực tiếp |
| **Phát triển tính năng** | Đáp ứng nhu cầu hoặc hành vi mới | **Thêm/đổi khả năng** | Cho phép học viên chọn lộ trình học cá nhân |
| **Thay đổi kiến trúc** | Điều chỉnh cấu trúc hệ thống, ranh giới trách nhiệm hoặc triển khai | Có thể giữ hoặc thay hành vi; thường nhiều rủi ro hơn | Tách dịch vụ tiến độ khỏi ứng dụng đơn khối |
| **Viết lại (rewrite)** | Thay phần lớn hiện thực bằng cách mới | Rất dễ bỏ sót hoặc đổi hợp đồng nếu thiếu bằng chứng | Xây lại toàn bộ module ghi danh trên nền tảng khác |

Một hạng mục thực tế có thể bao gồm nhiều loại công việc. Ví dụ, sửa lỗi mất tiến độ có thể cần **viết test tái hiện lỗi → sửa hành vi → refactor phần xử lý trạng thái → chạy kiểm thử tích hợp**. Điều quan trọng là không trộn mọi thay đổi thành một commit rất lớn rồi gọi chung là refactor: khi test đỏ, nhóm sẽ khó biết phần nào làm thay đổi kết quả.

### Refactoring không đồng nghĩa “tối ưu hiệu năng”

Thay một thuật toán bằng cách nhanh hơn nhưng cho kết quả và hợp đồng quan sát tương đương có thể là cải thiện bên trong. Tuy nhiên, hiệu năng cũng có thể là **yêu cầu có thể quan sát**: độ trễ, mức sử dụng tài nguyên, thứ tự trả kết quả hoặc giới hạn truy vấn đều có thể ảnh hưởng người dùng. Nếu thay đổi hiệu năng làm đổi kết quả hoặc điều kiện vận hành đã cam kết, cần xem nó là thay đổi hành vi/hợp đồng và kiểm chứng tương ứng.

### Đừng refactor một hành vi sai rồi mặc định đó là hành vi cần giữ

Một hệ thống cũ có thể đang cấp quyền sai hoặc cho phép ghi danh trùng. Kiểm thử đặc tả hiện trạng có thể ghi nhận hành vi ấy để tránh vô tình thay đổi trong lúc tách mã, nhưng **không được biến hành vi sai thành tiêu chuẩn chấp nhận lâu dài**. Cần tách:

1. **Hành vi thực tế đang tồn tại** – điều mã hiện làm.
2. **Hành vi đúng theo nghiệp vụ** – điều người có thẩm quyền xác nhận.
3. **Thay đổi cấu trúc** – bước cải thiện mã không cố ý thay đổi hợp đồng.
4. **Thay đổi hành vi có chủ đích** – bước sửa lỗi hoặc bổ sung khả năng đã được thỏa thuận.

## 3. “Giữ nguyên hành vi” nghĩa là giữ điều gì?

Hành vi quan sát được không chỉ là giá trị trả về của một phương thức. Tùy bối cảnh, nó có thể bao gồm:

- Kết quả nghiệp vụ: bài nào được mở, trạng thái đăng ký nào được tạo.
- Kết quả lỗi: điều kiện nào bị từ chối, ngoại lệ hoặc mã lỗi nào theo hợp đồng.
- Quyền truy cập: ai được thấy nội dung, ai bị chặn kể cả qua API trực tiếp.
- Dữ liệu: thay đổi nào được ghi, bất biến và tính toàn vẹn được giữ ra sao.
- Giao tiếp bên ngoài: endpoint, schema, contract event, trạng thái API.
- Tương tác với hệ thống ngoài: có gửi email, thu tiền, tạo thông báo lặp không.
- Khả năng vận hành đã cam kết: giới hạn độ trễ, thứ tự xử lý, tính sẵn sàng hoặc nhật ký cần thiết.

Không phải mọi chi tiết nội bộ đều là hợp đồng. Việc đổi tên biến cục bộ hay tách một hàm private thường không cần tác động người dùng. Nhưng một phương thức public đang được nhiều thành phần gọi có thể là **hợp đồng**, dù lập trình viên cho rằng nó “chỉ là chi tiết kỹ thuật”.

### Ma trận hợp đồng ví dụ cho “Tiếp tục học”

| Điều kiện | Hành vi cần giữ khi refactor | Cách kiểm chứng phù hợp |
| --- | --- | --- |
| Học viên có quyền, đã xong bài 1/3 | Mở được bài 2 | Unit/service test và một kiểm thử luồng |
| Học viên có quyền, chưa xong bài nào | Bắt đầu bài 1 theo quy tắc khóa | Unit test quy tắc, service test |
| Học viên hoàn thành bài cuối | Không tạo đường dẫn bài 4 không tồn tại | Unit test trạng thái biên, API/UI test chọn lọc |
| Người dùng không có quyền | Không thể truy cập nội dung bị hạn chế | Security/API integration test |
| Tiến độ âm hoặc vượt tổng bài | Không âm thầm đưa người học tới bài sai | Unit test và cách xử lý lỗi ở API |
| Dữ liệu tiến độ cũ | Giữ ý nghĩa sau thay đổi schema hoặc adapter | Integration/contract test với fixture phù hợp |

**Thứ tự và cách trả lỗi cũng có thể quan trọng.** Ví dụ, hệ thống có chủ ý kiểm tra quyền trước khi cung cấp chi tiết dữ liệu tiến độ; đảo thứ tự có thể làm lộ thông tin qua thông báo lỗi. Nếu muốn thay đổi hợp đồng, nhóm phải coi đó là thay đổi có chủ đích, không đơn thuần là “dọn mã”.

### Khi nào cần hỏi người nghiệp vụ?

Nếu không chắc “đã hoàn thành bài cuối” nghĩa là đã xem video hết, đã làm quiz hay đã được giảng viên chấm, đó là **câu hỏi nghiệp vụ**. Developers không nên tự chọn một quy tắc rồi viết test để hợp thức hóa lựa chọn. Hãy dùng refinement, Three Amigos/ATDD hoặc đối thoại trực tiếp với Product Owner và người hiểu nghiệp vụ để xác nhận.

## 4. Kiểm thử cung cấp bằng chứng gì – và không cung cấp gì?

Một bộ kiểm thử là **tập bằng chứng có giới hạn**: nó xác minh những tình huống và các thuộc tính đã được thiết kế để kiểm tra. Test xanh tăng niềm tin, nhưng không phải chứng minh toán học rằng toàn bộ hệ thống không có lỗi.

| Nguồn bằng chứng | Có thể bảo vệ | Không tự bảo đảm |
| --- | --- | --- |
| **Unit test** | Quy tắc thuần, giá trị biên, phép chuyển trạng thái | Transaction thật, API giữa các dịch vụ, quyền trên môi trường tích hợp |
| **Component/service test** | Hành vi qua giao diện service, phối hợp với phụ thuộc được kiểm soát | Toàn bộ hệ thống thật nếu phụ thuộc bị mock |
| **API/contract test** | Hợp đồng giữa bên cung cấp và tiêu thụ, cấu trúc/trạng thái phản hồi | Quy trình nghiệp vụ end-to-end |
| **Integration test** | Database, queue, transaction và sự tương thích của thành phần | Tất cả tình huống người dùng hoặc hệ thống ngoài |
| **End-to-end test** | Một hành trình thực tế qua các thành phần quan trọng | Mọi biến thể; kiểm thử UI thường chậm và dễ nhạy môi trường |
| **Security/performance checks** | Rủi ro phân quyền, lộ dữ liệu, hiệu năng/độ tin cậy theo tiêu chí | Giá trị sản phẩm hay mọi lỗ hổng chưa biết |
| **Observability và canary** | Dấu hiệu bất thường trên môi trường thực, tác động sau triển khai | Không thay thế kiểm thử trước phát hành |
| **Review và hiểu biết chuyên môn** | Phát hiện rủi ro thiết kế/test thiếu, sai giả định | Không thay thế bằng chứng thực thi |

### Refactor “dễ” và refactor “rủi ro cao”

Đổi tên một biến private có phạm vi nhỏ và được IDE hỗ trợ thường cần ít kiểm chứng hơn việc tách một service chứa giao dịch tiền hoặc thay đổi hợp đồng API đang có nhiều client. **Mức bằng chứng phải tỷ lệ với mức tác động**.

Nếu refactor chạm đến quyền truy cập, dữ liệu tồn tại lâu, concurrency hoặc giao tiếp hệ thống ngoài, phải bổ sung kiểm thử ở ranh giới phù hợp. Unit test của một lớp mới không thể chứng minh bất biến dữ liệu hoặc tính tương thích khi cả hai phiên bản dịch vụ cùng tồn tại.

### “Coverage cao” vẫn có thể bỏ sót hành vi quan trọng

100% line coverage không chắc phát hiện trường hợp hai yêu cầu ghi danh đến đồng thời, một account xem dữ liệu account khác hoặc migration mất dữ liệu cũ. Coverage giúp thấy **mã nào được chạy**, còn test assertions và mô hình rủi ro quyết định **điều gì thực sự được xác minh**. Mutation testing có thể hỗ trợ kiểm tra sức mạnh của một số assertions, nhưng cũng không thay thế kiểm thử tích hợp hay phân tích bảo mật.

## 5. Vòng refactor an toàn: chuẩn bị – thay đổi nhỏ – kiểm chứng

Một quy trình thực hành có thể gồm:

1. **Xác định mục tiêu thiết kế cụ thể.** Ví dụ: giảm trùng lặp quy tắc tiến độ làm việc thêm trường hợp biên dễ sai.
2. **Khoanh vùng hành vi phải giữ.** Xem hợp đồng ở mức có người sử dụng, những trường hợp rủi ro và các bất biến dữ liệu.
3. **Tạo hoặc củng cố bằng chứng kiểm thử.** Dùng test hiện có, thêm trường hợp bị thiếu, cân nhắc characterization test cho hệ thống cũ.
4. **Xác nhận đường cơ sở xanh.** Test phản ánh đúng hành vi, pipeline và môi trường đủ tin cậy; nếu có test đỏ sẵn, phải hiểu vì sao.
5. **Thực hiện một thay đổi cấu trúc nhỏ.** Ví dụ extract method, rename, move method, loại lặp có kiểm soát.
6. **Chạy kiểm thử thích hợp.** Bắt đầu nhanh ở cấp unit, sau đó chạy kiểm tra rộng theo rủi ro trước khi tích hợp.
7. **Review khác biệt hành vi và diff.** Khi test đỏ, phân biệt lỗi cấu trúc, dữ liệu test, môi trường hoặc giả định sai.
8. **Tích hợp sớm vào bản chung.** Dùng CI, contract/integration tests và tránh nhánh quá dài.
9. **Lặp lại từng bước**, chỉ mở rộng refactor khi bằng chứng tiếp tục đáng tin.
10. **Đánh giá kết quả.** Mã có dễ thay đổi hơn, ít lặp hơn hoặc giảm rủi ro thực tế không? Có tạo điểm nghẽn mới không?

~~~mermaid
flowchart TD
    A["Mục đích refactor + ranh giới hợp đồng"] --> B["Chọn test hồi quy và rủi ro cần bảo vệ"]
    B --> C["Đường cơ sở kiểm thử đáng tin"]
    C --> D["Một bước thay đổi cấu trúc nhỏ"]
    D --> E["Chạy test phù hợp + kiểm tra diff"]
    E --> F{"Hành vi theo hợp đồng được giữ?"}
    F -->|"Không/chưa rõ"| G["Điều tra, hoàn nguyên hoặc sửa bước nhỏ"]
    G --> C
    F -->|"Có"| H["CI, contract/integration tests khi cần"]
    H --> I{"Còn cải tiến có giá trị?"}
    I -->|"Có"| D
    I -->|"Không"| J["Tích hợp, ghi kết quả và tiếp tục delivery"]
~~~

**Không cần chạy toàn bộ kiểm thử đầu-cuối sau mỗi lần đổi tên biến.** Tối ưu vòng phản hồi bằng cách chọn test nhanh phù hợp trong lúc sửa, rồi áp dụng bộ kiểm tra rộng hơn theo rủi ro khi tích hợp và trước khi tuyên bố Increment đáp ứng Definition of Done.

### Refactor nên có điểm dừng rõ

Một mục tiêu hợp lý có thể là “gom quy tắc kiểm tra tiến độ về một nơi, loại hai đoạn sao chép, thêm test cho bài cuối và dữ liệu sai”. Mục tiêu “làm kiến trúc thật sạch” có thể kéo dài không giới hạn, khó chứng minh giá trị và dễ biến thành một đợt rewrite.

## 6. Ví dụ Java: trước khi refactor có hai quy tắc trùng nhau

Giả sử một module đã có hai phương thức: một tạo đường dẫn tới bài tiếp theo và một tạo nhãn hiển thị. Cả hai cùng kiểm tra quyền và số bài đã hoàn thành.

**Hợp đồng minh họa**:

- Nếu không có quyền học: trả chuỗi `NO_ACCESS`.
- Nếu có quyền nhưng tổng số bài không hợp lệ hoặc số bài hoàn thành ngoài khoảng: ném `IllegalArgumentException`.
- Nếu đã hoàn thành toàn bộ: trả `FINISHED`.
- Nếu còn bài: `linkFor` trả `/lessons/N`, `labelFor` trả `Bài N`, với N bằng số bài đã hoàn thành liên tiếp cộng một.

Quy tắc này chỉ phục vụ **khóa học tuyến tính**, chưa phải quy tắc cho khóa tự chọn hoặc trường hợp dữ liệu đồng bộ đa thiết bị. Quyền học được truyền vào để minh họa sự khác biệt giữa hợp đồng và cấu trúc; trong hệ thống thật, **kiểm tra quyền ở phía máy chủ** còn cần xác minh qua kiểm thử API/integration.

### 6.1. Mã trước refactor

~~~java
public final class LessonNavigation {
    public String linkFor(int completed, int total, boolean hasAccess) {
        if (!hasAccess) {
            return "NO_ACCESS";
        }
        if (total < 1 || completed < 0 || completed > total) {
            throw new IllegalArgumentException("Invalid progress");
        }
        if (completed == total) {
            return "FINISHED";
        }
        return "/lessons/" + (completed + 1);
    }

    public String labelFor(int completed, int total, boolean hasAccess) {
        if (!hasAccess) {
            return "NO_ACCESS";
        }
        if (total < 1 || completed < 0 || completed > total) {
            throw new IllegalArgumentException("Invalid progress");
        }
        if (completed == total) {
            return "FINISHED";
        }
        return "Bài " + (completed + 1);
    }
}
~~~

Mã không sai về hành vi trong phạm vi giả định, nhưng **quy tắc kiểm tra và kết thúc khóa bị lặp**. Một người có thể sửa trường hợp `completed == total` ở `linkFor` mà quên `labelFor`. Đây là cơ hội refactor có mục đích.

### 6.2. Viết kiểm thử mô tả hành vi trước khi sửa cấu trúc

Ví dụ với JUnit Jupiter (JUnit 5):

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class LessonNavigationTest {
    private final LessonNavigation navigation = new LessonNavigation();

    @Test
    void keepsLinkAndLabelForNextLesson() {
        assertEquals("/lessons/2", navigation.linkFor(1, 3, true));
        assertEquals("Bài 2", navigation.labelFor(1, 3, true));
    }

    @Test
    void startsAtFirstLessonWhenNoneCompleted() {
        assertEquals("/lessons/1", navigation.linkFor(0, 3, true));
        assertEquals("Bài 1", navigation.labelFor(0, 3, true));
    }

    @Test
    void returnsFinishedAtLastLesson() {
        assertEquals("FINISHED", navigation.linkFor(3, 3, true));
        assertEquals("FINISHED", navigation.labelFor(3, 3, true));
    }

    @Test
    void deniesAccessBeforeExposingProgressValidation() {
        assertEquals("NO_ACCESS", navigation.linkFor(-1, 0, false));
        assertEquals("NO_ACCESS", navigation.labelFor(-1, 0, false));
    }

    @Test
    void rejectsInvalidProgressForAuthorizedLearner() {
        assertThrows(IllegalArgumentException.class,
                () -> navigation.linkFor(4, 3, true));
        assertThrows(IllegalArgumentException.class,
                () -> navigation.labelFor(-1, 3, true));
        assertThrows(IllegalArgumentException.class,
                () -> navigation.linkFor(0, 0, true));
    }
}
~~~

Chúng ta bảo vệ **kết quả và thứ tự kiểm tra mang ý nghĩa quan sát được**, thay vì assert rằng mã phải có hai câu lệnh `if` hoặc một phương thức private cụ thể. Sau khi test xanh trên mã cũ, nhóm có cơ sở để thử thay đổi cấu trúc.

### 6.3. Refactor: gom quy tắc về một phương thức private

~~~java
import java.util.OptionalInt;

public final class LessonNavigation {
    public String linkFor(int completed, int total, boolean hasAccess) {
        if (!hasAccess) {
            return "NO_ACCESS";
        }
        OptionalInt next = nextLessonNumber(completed, total);
        return next.isPresent()
                ? "/lessons/" + next.getAsInt()
                : "FINISHED";
    }

    public String labelFor(int completed, int total, boolean hasAccess) {
        if (!hasAccess) {
            return "NO_ACCESS";
        }
        OptionalInt next = nextLessonNumber(completed, total);
        return next.isPresent()
                ? "Bài " + next.getAsInt()
                : "FINISHED";
    }

    private OptionalInt nextLessonNumber(int completed, int total) {
        if (total < 1 || completed < 0 || completed > total) {
            throw new IllegalArgumentException("Invalid progress");
        }
        return completed == total
                ? OptionalInt.empty()
                : OptionalInt.of(completed + 1);
    }
}
~~~

Điều được thay đổi là **cấu trúc**: một quy tắc chung thay cho hai bản sao. Điều được giữ theo hợp đồng:

- Cùng phương thức public và tham số.
- Cùng kết quả đường dẫn, nhãn, hoàn tất và từ chối truy cập.
- Cùng điều kiện dữ liệu không hợp lệ và kiểu ngoại lệ.
- Cùng thứ tự ưu tiên kiểm tra quyền trước khi để lộ lỗi về tiến độ.

Sau bước này, chạy lại unit tests để kiểm tra **không có khác biệt quan sát được trong những trường hợp đã bảo vệ**. Tình huống mới có thể cần bổ sung test; không có bảo đảm tuyệt đối khi bộ test chưa bao phủ mọi hợp đồng.

### 6.4. Vì sao phương thức private không cần được test trực tiếp?

`nextLessonNumber` là chi tiết triển khai. Kiểm thử hai phương thức public giúp phép **Extract Method** không làm test bị phụ thuộc vào việc nhóm đặt tên hoặc chuyển phương thức private. Nếu test chỉ đạt sau khi thay đổi assertion theo mã mới, cần kiểm tra lại liệu đây có còn là refactor hay đã lén đổi hành vi.

### 6.5. Khi nào mã này cần cải tiến tiếp?

Nếu sau đó có nhiều loại khóa học, nhóm có thể cần mô hình hóa chính sách chọn bài thay vì kiểm tra một số nguyên `completed`. Đây có thể là **thiết kế tiến hóa dựa trên nhu cầu mới**. Không nên tự thêm một hệ thống plugin phức tạp, tầng interface và hierarchy chỉ vì tưởng tượng tương lai sẽ có hàng chục loại khóa.

## 7. Những bước refactor thường gặp và mức kiểm chứng cần thiết

| Kỹ thuật | Mục tiêu | Rủi ro/cách kiểm chứng |
| --- | --- | --- |
| **Rename variable/method nội bộ** | Ngữ nghĩa rõ hơn | IDE, compiler và test liên quan; xem phạm vi API public |
| **Extract Method** | Chia hàm dài, đặt tên cho quy tắc | Test bảo vệ nhánh và thứ tự kiểm tra; tránh đổi hiệu ứng phụ |
| **Inline Method** | Loại tầng trừu tượng không giúp hiểu mã | Test hành vi và kiểm tra nơi gọi |
| **Move Method/Field** | Đưa trách nhiệm về nơi phù hợp | Test tại ranh giới đối tượng, kiểm tra tác động dependency |
| **Extract Class** | Tách hai nhóm trách nhiệm thường đổi vì lý do khác nhau | Test qua API công khai, quan sát kết nối dữ liệu và lifecycle |
| **Remove Duplication** | Một nguồn cho quy tắc thay vì nhiều bản sao | Test các biến thể để không gộp nhầm khác biệt nghiệp vụ |
| **Introduce Parameter Object** | Gom tham số liên quan, rõ ràng hợp đồng | Kiểm tra tương thích chữ ký đang được client dùng |
| **Replace Conditional with Polymorphism/Strategy** | Tách biến thể hành vi phức tạp | Bảo vệ mọi nhánh hiện hữu và lỗi/giá trị biên |
| **Encapsulate Collection/State** | Tránh các bên thay dữ liệu không hợp lệ | Kiểm tra bất biến và tương tác có thể quan sát |

Không cần áp tất cả kỹ thuật vào một story. Nếu đổi cấu trúc khiến mã phức tạp hơn, thêm nhiều tầng gián tiếp và tăng thời gian hiểu quy tắc, đó không hẳn là cải tiến.

### Một thay đổi nhỏ có thể đảo ngược tốt hơn một “đại phẫu”

Ví dụ với hàm dài: trước tiên bổ sung test cho nhánh nghiệp vụ quan trọng; trích xuất một phép tính thuần; chạy test; đổi tên rõ ràng; chạy test; tách phụ thuộc database; kiểm tra tích hợp. Mỗi bước **đều có thể được hiểu và hoàn nguyên** nếu phát hiện điều bất ngờ.

Ngược lại, vừa đổi schema, tách service, chuyển framework HTTP và sửa quy tắc cấp quyền trong cùng lần thay đổi sẽ khiến bộ test đỏ rất khó chẩn đoán. Nếu phải làm thay đổi lớn, hãy tìm cách chia **các bước chuyển tiếp có tương thích**.

## 8. Legacy code: tạo characterization tests khi chưa có “hàng rào” kiểm thử

Trong một hệ thống cũ, có thể có logic 1.000 dòng không có test, kết nối trực tiếp database, đọc đồng hồ hệ thống và phát email. Không thể yêu cầu “cứ refactor an toàn” khi nhóm **không biết hành vi hiện tại và chưa có cách nhận ra khác biệt**.

**Characterization tests** ghi nhận một phần **hành vi thực tế hiện hữu** để phát hiện thay đổi ngoài ý muốn. Chúng đặc biệt hữu ích khi chưa có đặc tả đáng tin. Nhưng chúng không chứng minh hành vi cũ là đúng về nghiệp vụ.

### 8.1. Quy trình thực hành với hệ thống cũ

1. **Xác định ranh giới quan sát:** một API public, một xử lý batch hoặc một hàm có đầu vào/đầu ra rõ.
2. **Chọn dữ liệu đại diện và các trường hợp rủi ro:** luồng chính, biên, lỗi và dữ liệu cũ.
3. **Chạy phiên bản hiện tại trong môi trường an toàn:** ghi kết quả và điều kiện có thể tái lập.
4. **Tạo test mô tả hiện trạng:** nêu rõ test bảo vệ tương thích, chưa chắc quy tắc đúng.
5. **Cố định nguồn bất định khi thích hợp:** đồng hồ, random, dịch vụ ngoài, dữ liệu test.
6. **Tách một “seam” nhỏ:** đưa tác động ngoài vào một adapter hoặc ranh giới có thể kiểm soát.
7. **Refactor một bước rồi kiểm tra:** nếu kết quả khác, phân tích trước khi chấp nhận.
8. **Đối chiếu quy tắc nghiệp vụ:** nếu hiện trạng sai, lập thay đổi hành vi có chủ đích với tiêu chí mới.

### 8.2. Golden master/snapshot có thể giúp gì?

Với một bộ dữ liệu đầu vào được chọn, nhóm có thể ghi kết quả đầu ra của phiên bản cũ làm **baseline**, rồi chạy phiên bản mới để so sánh. Cách này có thể giúp phát hiện khác biệt trong những hệ thống khó tách unit test.

Nhưng nếu baseline chứa **lỗi cũ, dữ liệu nhạy cảm, timestamp ngẫu nhiên hoặc thứ tự không ổn định**, việc so sánh nguyên văn có thể vô nghĩa hoặc làm lộ thông tin. Cần:

- Dùng dữ liệu test không nhạy cảm, có thể tái tạo.
- Chỉ chuẩn hóa trường **không thuộc hợp đồng**, không che hành vi quan trọng.
- Ghi rõ các trường hợp baseline đang sai và cần sửa riêng.
- Dùng kiểm thử xác nhận nghiệp vụ bổ sung, không coi snapshot là nguồn chân lý duy nhất.

### 8.3. Tạo “seam” để kiểm tra phụ thuộc

Một service xử lý tiến độ vừa gọi database, lấy giờ hệ thống, kiểm tra quyền và gửi thông báo có thể rất khó kiểm tra. Nhóm có thể tách phần **quy tắc thuần** khỏi những adapter hạ tầng, rồi dùng test double có chủ đích để tạo tình huống.

Tuy nhiên, fake database không mô phỏng hết transaction, lock hoặc concurrency. Sau khi test unit xanh, những bất biến dữ liệu và tương tác giữa hệ thống vẫn phải được bảo vệ bằng **integration/contract tests theo rủi ro**.

## 9. Refactor mã đồng thời giữ hợp đồng API và dữ liệu

Một số thay đổi nhìn như “đổi cấu trúc” nhưng ảnh hưởng trực tiếp các thành phần đang sử dụng. Ví dụ, đổi tên trường JSON, thay trạng thái `PENDING` thành `WAITING`, chuyển API đồng bộ sang bất đồng bộ hoặc đổi schema dữ liệu mà không hỗ trợ phiên bản cũ.

### 9.1. Expand – Migrate – Contract cho thay đổi không thể làm đồng thời

Một chiến lược thường dùng khi cần đổi hợp đồng với rủi ro thấp:

1. **Expand:** bổ sung trường/hợp đồng mới mà vẫn hỗ trợ cách cũ.
2. **Migrate:** chuyển bên sử dụng và dữ liệu theo từng bước; kiểm tra bản cũ và mới hoạt động trong giai đoạn chuyển tiếp.
3. **Contract:** chỉ bỏ phần tương thích cũ khi đã có bằng chứng không còn bên phụ thuộc và dữ liệu đã được chuyển hợp lệ.

Ví dụ, API trước trả `lastCompletedLesson`; mô hình mới cần lưu `completedLessonIds` cho khóa tự chọn. Không nên xóa ngay trường cũ khi ứng dụng di động vẫn sử dụng. Nhóm có thể cung cấp dữ liệu chuyển tiếp tương thích, chuyển từng client, theo dõi lỗi và dọn hợp đồng cũ sau khi xác nhận đủ điều kiện.

~~~mermaid
flowchart LR
    A["Hợp đồng/dữ liệu hiện tại"] --> B["EXPAND: hỗ trợ cấu trúc cũ + mới"]
    B --> C["MIGRATE: chuyển client/dữ liệu theo đợt"]
    C --> D{"Bằng chứng tương thích và chất lượng đạt?"}
    D -->|"Chưa"| E["Khắc phục, theo dõi và kiểm tra lại"]
    E --> C
    D -->|"Có"| F["CONTRACT: bỏ cấu trúc cũ đúng thời điểm"]
~~~

Đây là **chiến lược chuyển đổi hợp đồng** để hỗ trợ thiết kế tiến hóa, không phải một thao tác refactoring thuần ở cấp phương thức. Nó có thay đổi bên ngoài được quản lý nên cần kế hoạch, quyền quyết định và bằng chứng riêng.

### 9.2. Các kiểm thử quan trọng trong chuyển đổi

| Khu vực | Bằng chứng cần xem |
| --- | --- |
| **API/contract** | Consumer cũ và mới đọc được trạng thái đúng, mã lỗi và dữ liệu quan trọng không đổi sai |
| **Migration dữ liệu** | Dữ liệu cũ được chuyển đủ, không mất/nhân đôi, có cách kiểm tra và phục hồi phù hợp |
| **Transaction/concurrency** | Yêu cầu lặp hoặc đồng thời không phá bất biến |
| **Quyền truy cập** | Không cấp quyền sai trong cả trạng thái cũ và mới |
| **Vận hành** | Triển khai nhiều phiên bản, quay lui và theo dõi lỗi được đánh giá theo đặc tính dữ liệu |
| **Hành trình người dùng** | Những luồng trọng yếu tiếp tục hoạt động khi từng phần chuyển phiên bản |

### Feature flag không giải quyết mọi rủi ro

Một feature flag có thể giúp ẩn hoặc bật một khả năng trong giai đoạn rollout. Nó **không thể tự phục hồi dữ liệu đã ghi sai hoặc hoàn tác migration phá hủy**. Với thay đổi dữ liệu, cần kế hoạch sao lưu/phục hồi, khả năng tương thích và kiểm tra được thống nhất theo yêu cầu vận hành.

## 10. Kiểm thử tại nhiều lớp khi refactor xuyên thành phần

Khi một module tiến độ được tách khỏi ứng dụng đơn khối, rủi ro không chỉ ở thuật toán mà còn ở **giao tiếp giữa dịch vụ**. Nhóm cần kết hợp bằng chứng:

| Cấp kiểm tra | Ví dụ kiểm tra khi tách module tiến độ |
| --- | --- |
| **Unit** | Quy tắc chọn bài theo khóa tuyến tính không đổi |
| **Service/component** | Service trả trạng thái `FINISHED` cho học viên đã xong khóa |
| **Contract** | Client trang khóa đọc đúng trường phản hồi cũ/mới trong giai đoạn chuyển tiếp |
| **Database integration** | Ghi tiến độ, retry và migration giữ tính toàn vẹn dữ liệu |
| **Security/API** | Không thể lấy tiến độ của học viên khác bằng cách đổi ID |
| **End-to-end** | Học viên có quyền mở bài tiếp theo từ trang khóa |
| **Observability** | Có tín hiệu phù hợp để phát hiện tăng lỗi và bất thường sau rollout |

### Gherkin thể hiện hợp đồng người dùng

~~~gherkin
Feature: Tiếp tục học sau khi cải thiện thiết kế module tiến độ

  Scenario: Học viên có quyền mở bài tiếp theo
    Given học viên đã đăng nhập và có quyền học khóa tuyến tính
    And học viên đã hoàn thành bài đầu của khóa ba bài
    When học viên mở trang khóa và chọn "Tiếp tục học"
    Then hệ thống mở bài thứ hai
    And tiến độ đã lưu không bị thay đổi sai

  Scenario: Hoàn thành bài cuối
    Given học viên có quyền học và đã hoàn thành ba bài
    When học viên mở trang khóa
    Then hệ thống hiển thị trạng thái hoàn thành
    And không tạo liên kết đến bài thứ tư

  Scenario: Truy cập trái quyền
    Given người dùng không có quyền truy cập khóa
    When người dùng yêu cầu API mở bài bị hạn chế
    Then hệ thống từ chối cấp nội dung bị hạn chế
    And không tiết lộ dữ liệu tiến độ riêng của học viên khác
~~~

Những ví dụ này là **hành vi cần duy trì**, nhưng không đủ bảo vệ tất cả tình huống đồng bộ đa thiết bị, dữ liệu cũ và trường hợp tải cao. Phần chưa được bảo vệ cần được nhận diện rõ thay vì tuyên bố “refactor an toàn tuyệt đối”.

## 11. Kết hợp TDD, ATDD và characterization tests

| Công cụ tư duy/kỹ thuật | Dùng khi nào? | Đóng góp vào refactoring |
| --- | --- | --- |
| **TDD – Red/Green/Refactor** | Khi phát triển hoặc sửa một quy tắc nhỏ | Dẫn dắt thiết kế và tạo test nhanh bảo vệ hành vi |
| **ATDD** | Khi story/tiêu chí nghiệp vụ chưa được hiểu giống nhau | Thống nhất các ví dụ chấp nhận trước khi xây thay đổi |
| **BDD/Gherkin** | Khi cần ngôn ngữ chung cho hành vi giữa nghiệp vụ và kỹ thuật | Tạo ví dụ dễ đọc, kiểm chứng được qua tầng test phù hợp |
| **Characterization tests** | Khi làm việc với legacy code thiếu đặc tả/bằng chứng | Ghi nhận hành vi hiện tại để phát hiện khác biệt ngoài ý muốn |
| **Contract/integration tests** | Khi refactor chạm database, API, message hoặc nhiều module | Phát hiện lỗi ghép nối mà unit test không thấy |
| **Exploratory testing** | Khi có hành vi phức tạp, rủi ro mới hoặc lỗ hổng trong hiểu biết | Khám phá những điều bộ test dự đoán trước chưa bao phủ |

### TDD và refactoring có cùng một điểm quan trọng

Vòng **Red – Green – Refactor** cho phép tạo hành vi mới bằng test rồi cải thiện thiết kế khi test xanh. Trong một **refactor thuần**, nhóm thường bắt đầu từ **hành vi đã được bảo vệ bằng test xanh**, đổi cấu trúc từng bước và giữ test xanh sau mỗi bước. Nếu cố tình thêm test đỏ cho một hành vi chưa có, phần tiếp theo sẽ là **phát triển tính năng/sửa lỗi**, không còn chỉ là refactor.

### ATDD giữ refactoring gắn với nhu cầu

Giả sử Developers muốn gom nhiều trạng thái đăng ký thành một enum chung. Nếu người nghiệp vụ coi `PENDING` và `ACTIVE` là khác nhau về quyền học, việc hợp nhất không được làm mất ý nghĩa. Một buổi Three Amigos ngắn và bảng ví dụ có thể giúp xác nhận ranh giới trước khi sửa cấu trúc.

## 12. Tổ chức phản hồi tự động và CI để phát hiện sai lệch sớm

Một refactor kiểm tra hoàn toàn bằng tay dễ gặp vấn đề: người sửa nhớ chạy test này nhưng quên test khác; bản tích hợp của đồng nghiệp có API mới; thay đổi được merge khi nhánh chính đã khác nhiều.

**Continuous Integration (CI)** giúp chạy lại những kiểm tra phù hợp khi mã được tích hợp thường xuyên. Một pipeline minh họa:

~~~mermaid
flowchart TD
    A["Refactor nhỏ + unit tests cục bộ"] --> B["Tích hợp thay đổi"]
    B --> C["Build/static checks"]
    C --> D["Unit + service tests"]
    D --> E["Contract/integration tests"]
    E --> F["Smoke/E2E và kiểm tra rủi ro trọng yếu"]
    F --> G["Increment được đánh giá theo DoD"]
    G --> H["Rollout phù hợp và quan sát phản hồi"]
    C -. "Đỏ" .-> X["Xác định nguyên nhân và khắc phục"]
    D -. "Đỏ" .-> X
    E -. "Đỏ" .-> X
    F -. "Đỏ" .-> X
    X --> B
~~~

### Một quy ước thực hành khi CI đỏ

1. Xác minh thất bại có liên quan thay đổi mới hay do pipeline/test flaky.
2. Không sửa expected result để “hợp mã mới” khi chưa có quyết định thay đổi hành vi.
3. Nếu hợp đồng bị phá ngoài ý muốn, khôi phục hoặc sửa refactor trước khi tích tụ thêm thay đổi.
4. Nếu test mới phát hiện **lỗi cũ**, tách vấn đề nghiệp vụ khỏi mục tiêu refactor và báo rủi ro.
5. Không tắt lâu dài các kiểm thử bắt buộc chỉ vì làm chậm tiến độ.

Một pipeline chậm và thường thất bại ngẫu nhiên cũng là vấn đề cần cải thiện. Nhưng **bỏ tất cả kiểm tra nặng** không phải lời giải nếu những kiểm tra đó đang bảo vệ dữ liệu, quyền và sự tương thích quan trọng.

### Không cần chạy mọi test ở mọi bước

Trong lúc Extract Method của một lớp thuần, chạy unit test nhanh cung cấp phản hồi tốt. Trước khi merge hoặc release một refactor chạm hợp đồng API, cần các kiểm tra rộng hơn. Chiến lược chạy test nên cân bằng **độ trễ phản hồi, mức rủi ro, độ tin cậy và chi phí hạ tầng**.

### Không chạy code chưa phải bằng chứng runtime

Các ví dụ Java/JUnit trong bài nhằm minh họa cách lập test và refactor; trong dự án thật, nhóm phải **chạy chúng trên môi trường phù hợp** cùng các kiểm thử tích hợp cần thiết. Đọc mã hoặc xem test trên tài liệu không đủ xác nhận rằng hệ thống đang hoạt động đúng.

## 13. Dùng rollout có kiểm soát và quan sát production

Ngay cả khi unit, integration và contract tests đều đạt, một refactor lớn vẫn có thể tác động đến những đặc tính môi trường thật mà test chưa mô phỏng đủ: tải đồng thời, dữ liệu cũ, client ít gặp, sự cố mạng hay cấu hình cụ thể.

Với thay đổi rủi ro cao, nhóm có thể cân nhắc:

- **Canary rollout:** cung cấp cho một phần lưu lượng được kiểm soát, theo dõi tín hiệu trước khi mở rộng.
- **Feature flag:** bật/tắt nhánh hành vi nếu thiết kế và dữ liệu cho phép.
- **Shadow traffic/differential testing:** so sánh kết quả cũ và mới trên những request phù hợp, không tạo hiệu ứng phụ ngoài ý muốn.
- **Parallel run:** chạy hai con đường xử lý trong một khoảng hạn chế để kiểm tra sự phù hợp của kết quả.
- **Observability:** theo dõi lỗi, độ trễ, trạng thái bất thường và kết quả người dùng.

Những chiến lược này có chi phí và rủi ro riêng. Ví dụ, **không nên gửi cùng một yêu cầu thanh toán hoặc email thực hai lần** chỉ để so sánh kết quả của hai phiên bản. Shadow traffic cần xử lý an toàn dữ liệu cá nhân và hiệu ứng phụ.

### Chọn guardrail trước khi triển khai

| Guardrail | Ví dụ tín hiệu | Khi nào cần xử lý |
| --- | --- | --- |
| **Quyền truy cập** | Số yêu cầu truy cập trái quyền không bị chặn hoặc dấu hiệu lộ dữ liệu | Hành động theo quy trình sự cố; không chờ đến Sprint Review |
| **Tính toàn vẹn tiến độ** | Số bản ghi mất, trùng hoặc chuyển trạng thái sai | Điều tra, hạn chế tác động, khôi phục theo chính sách |
| **Độ tin cậy API** | Tỷ lệ lỗi, timeout, độ trễ theo mục tiêu | Xem ngưỡng chấp nhận và khả năng rollback |
| **Khả năng học** | Tỷ lệ học viên đủ điều kiện mở đúng bài tiếp theo | Kiểm chứng chức năng vẫn hữu ích sau thay đổi |

Không tự gán ngưỡng số phần trăm cho mọi sản phẩm. Ngưỡng, quy tắc cảnh báo và biện pháp ứng phó cần dựa trên **rủi ro và cam kết vận hành** thực tế.

### Rollback không luôn đủ

Quay lại phiên bản code cũ có thể khôi phục hành vi nếu không có thay đổi dữ liệu không tương thích. Nhưng nếu migration đã xóa dữ liệu hoặc viết sai trạng thái, cần phương án **khôi phục dữ liệu, forward fix và kiểm tra nhất quán**. Refactor có ảnh hưởng dữ liệu phải dự liệu kịch bản này ngay từ khi thiết kế thay đổi.

## 14. Refactor bao nhiêu là đủ? Gắn chất lượng mã với giá trị sản phẩm

Không phải mọi đoạn mã chưa đẹp đều cần được refactor lập tức. Kỹ thuật tốt giúp giảm chi phí thay đổi, nhưng đầu tư kỹ thuật cần được cân nhắc theo **mức tác động, tần suất sửa, rủi ro và mục tiêu sản phẩm**.

### Ưu tiên vùng mã có ma sát cao

| Dấu hiệu | Ý nghĩa cần xem xét | Phương án phù hợp |
| --- | --- | --- |
| Quy tắc bị sao chép, thường sửa lệch giữa hai chỗ | Chi phí thay đổi cao, dễ tạo bug | Test bảo vệ biến thể rồi gom logic chung |
| Mỗi thay đổi nhỏ đều làm hỏng nhiều test tích hợp | Thiết kế/phụ thuộc quá chặt hoặc test quá bám nội bộ | Kiểm tra test design và tách ranh giới hợp lý |
| Một lớp vừa xử lý HTTP, database, quyền và nghiệp vụ | Khó hiểu, khó cô lập lỗi | Tách quy tắc thuần hoặc adapter từng bước |
| Hàng đợi code review liên tục bị nghẽn vì PR rất lớn | Phản hồi chậm, rủi ro tích hợp cao | Chia refactor thành thay đổi nhỏ và có thể review |
| Một chức năng rất ổn định, ít đổi, rủi ro thấp | Có thể chưa đáng đầu tư lớn | Ghi nhận nợ kỹ thuật và theo dõi, không rewrite chỉ vì phong cách |
| Module lõi sắp có thay đổi nghiệp vụ lớn | Thiết kế hiện tại có thể cản trở delivery | Refactor có mục tiêu trước hoặc cùng một lát mới, giữ test xanh |

### Boy Scout Rule với giới hạn hợp lý

Quy tắc “để mã sạch hơn một chút so với khi bạn đến” có thể giúp cải tiến đều đặn: đặt tên tốt hơn, bỏ một đoạn trùng lặp nhỏ, bổ sung test còn thiếu. Nhưng nếu một PR sửa bug nhỏ kéo theo đổi cấu trúc hàng chục file không liên quan, phạm vi review và rủi ro tăng. Hãy phân biệt **cải thiện gọn trong phạm vi công việc** với **refactor lớn cần một kế hoạch và bằng chứng riêng**.

### Cách nói về giá trị của refactoring với Product Owner

Thay vì “chúng tôi muốn làm sạch module”, hãy làm rõ:

> “Quy tắc quyền học bị lặp ở ba nơi; hai lần sửa gần đây làm sai một nơi khác. Chúng tôi muốn viết kiểm thử hồi quy cho các trường hợp quyền và gom quy tắc về một điểm. Điều này giảm nguy cơ phát hành sai quyền khi thêm tính năng khóa cần duyệt và giúp nhóm giao những thay đổi tiếp theo an toàn hơn.”

Lập luận này gắn công việc kỹ thuật với **rủi ro sản phẩm, khả năng bàn giao và nhu cầu sắp tới**. Không cần biến mọi việc thành một chỉ số tiền tệ giả chính xác; có thể sử dụng bằng chứng lỗi lặp, thời gian sửa và độ bất định.

## 15. Scrum, Kanban, XP và Lean hỗ trợ refactor an toàn ra sao?

### XP: kiểm thử và refactoring là nhịp kỹ thuật liên tục

Trong XP, **TDD, refactoring, tích hợp liên tục, thiết kế đơn giản và làm việc cộng tác** giúp nhóm thay đổi mã ở các bước nhỏ. Khi kiểm thử bảo vệ hành vi, việc refactor không còn là một đợt “dọn dẹp lớn” sau khi phát triển xong, mà có thể diễn ra cùng vòng giao giá trị.

### Scrum: chất lượng gắn với Definition of Done

Scrum không bắt buộc kỹ thuật refactoring cụ thể, nhưng **Increment phải đạt Definition of Done**. Developers chịu trách nhiệm chất lượng, có thể lựa chọn refactor và bổ sung kiểm thử để đáp ứng DoD, giảm rủi ro khi phát triển các Product Backlog Items. Product Owner cung cấp bối cảnh giá trị và sắp xếp thứ tự Product Backlog hiệu quả.

**Sprint Review** là nơi Scrum Team và stakeholder kiểm tra kết quả Sprint và hướng sản phẩm, không phải cổng cuối để QA ký cho mã chưa đạt DoD. **Sprint Retrospective** có thể giúp nhóm nhận ra refactor bị trì hoãn vì PR quá lớn, CI yếu hoặc chưa phân bổ thời gian cải thiện.

### Kanban: giảm thời gian refactor mắc trong hàng đợi

Một refactor nhỏ có thể kéo dài hàng tuần nếu hạng mục chờ review, chờ test hoặc liên tục bị ngắt bởi nhiều việc mở. Dùng **WIP limits, work item age, cycle time và throughput** giúp nhóm nhìn điểm nghẽn và hoàn tất công việc trước khi bắt đầu thêm.

Không nên biến số pull request đã merge thành thước đo giá trị. Một refactor thành công phải **giữ đúng hành vi và giúp quá trình thay đổi đáng tin hơn**, không chỉ tạo nhiều commit.

### Lean: tối ưu toàn hệ thống

Nếu lập trình viên viết mã nhanh hơn nhưng lỗi phát hiện muộn trong QA, nhóm vẫn giao giá trị chậm. Lean giúp thấy thời gian chờ, làm lại, tích hợp và vận hành trong **toàn dòng giá trị**, từ nhu cầu đến Increment dùng được. Refactoring có mục tiêu giúp giảm **lãng phí do cấu trúc khó thay đổi** khi nó thực sự làm giảm lỗi và lead time.

### ATDD và user story vẫn quan trọng

Refactor kỹ thuật không bảo đảm nhóm hiểu đúng nhu cầu. Với chức năng mới, user story và ví dụ chấp nhận giúp xác định hành vi cần có; TDD/refactor hỗ trợ triển khai an toàn. Kiểm thử có thể chứng minh mã đúng theo tiêu chí, nhưng sản phẩm vẫn cần đo **outcome người dùng** và nhận phản hồi.

## 16. Đo hiệu quả refactor mà không chạy theo chỉ số hình thức

Một thay đổi cấu trúc nên được đánh giá theo mục tiêu đã nêu. Các tín hiệu:

| Chỉ số/bằng chứng | Câu hỏi | Cảnh báo |
| --- | --- | --- |
| **Lỗi hồi quy ở vùng mã liên quan** | Những lần sửa tiếp theo có ít lỗi ngoài ý muốn hơn không? | Không kết luận từ một Sprint hoặc một sự cố |
| **Thời gian thay đổi một quy tắc** | Thêm một biến thể nghiệp vụ cần sửa bao nhiêu nơi, mất bao lâu? | Tác vụ khác độ phức tạp có thể không so sánh trực tiếp |
| **Độ trễ phản hồi CI** | Phát hiện sai lệch sau thay đổi nhanh và đáng tin thế nào? | Pipeline rất nhanh nhưng thiếu test quan trọng không đủ |
| **Test flaky/khả năng tái lập** | Những lần đỏ có ý nghĩa và chẩn đoán được không? | Đừng bỏ test để làm trạng thái xanh |
| **Cycle time/work item age** | Các story trong vùng mã được hoàn tất ổn định hơn? | Cần đối chiếu loại việc, WIP và phụ thuộc |
| **Phạm vi mã phải sửa cho một thay đổi** | Còn phải sửa nhiều bản sao và cập nhật cùng logic ở nhiều nơi? | Đếm dòng code không trực tiếp đo mức tốt của thiết kế |
| **Contract/integration failures** | Hợp đồng giữa các thành phần có ít bị phá ngoài ý muốn? | Phân biệt thay đổi có chủ đích với lỗi tương thích |
| **Outcome và guardrail** | Người dùng còn được phục vụ an toàn và đạt mục tiêu? | Refactor sạch nhưng làm tăng lỗi dữ liệu là thất bại |

### Ví dụ cách diễn giải

Giả sử nhóm trước đây phải sửa ba lớp khi đổi một quy tắc tiến độ, sau refactor chỉ còn một điểm thay đổi và bộ kiểm thử hồi quy đủ nhanh. Đây là **bằng chứng thiết kế dễ thay đổi hơn ở tình huống đó**. Tuy nhiên, cần tiếp tục theo dõi một vài thay đổi thực tế để biết abstraction có thực sự hữu ích hoặc tạo coupling mới hay không.

Nếu số dòng mã giảm 20% nhưng thêm điều kiện khó hiểu và test khó bảo trì hơn, không thể kết luận refactor thành công chỉ từ số dòng giảm.

## 17. Những phản mẫu khiến refactor trở thành nguồn rủi ro

| Phản mẫu | Hậu quả | Cách điều chỉnh |
| --- | --- | --- |
| **Đổi hành vi và cấu trúc trong cùng bước quá lớn** | Test đỏ khó chẩn đoán, khó rollback | Tách refactor khỏi feature/bug fix khi thực tế cho phép |
| **Chỉ dựa vào unit tests** | Bỏ sót API, database, phân quyền và tương tranh | Thêm contract/integration/security tests theo rủi ro |
| **Tin coverage 100% là bảo đảm** | Vẫn có thể thiếu assertions hoặc trường hợp quan trọng | Kiểm tra hành vi biên, bất biến và lỗi thực tế |
| **Refactor legacy code mà chưa hiểu hiện trạng** | Vô tình phá hành vi đang được client sử dụng | Characterization tests, quan sát và làm rõ hợp đồng |
| **Golden master bị coi là nghiệp vụ đúng tuyệt đối** | Đóng băng lỗi cũ hoặc dữ liệu nhạy cảm | Phân biệt hiện trạng và hành vi mong muốn, đối chiếu với người có thẩm quyền |
| **Test bám quá sát phương thức private** | Đổi cấu trúc hợp lệ cũng làm test vỡ | Ưu tiên test hợp đồng quan sát được |
| **Mock mọi tích hợp** | Không phát hiện transaction, hợp đồng và race condition | Giữ kiểm thử tích hợp chọn lọc cho rủi ro cao |
| **Refactor trên nhánh dài không tích hợp** | Xung đột, khó ghép với code mới | Chia bước nhỏ và tích hợp thường xuyên |
| **Thay API/schema mà không giữ tương thích** | Phá client và dữ liệu khi nhiều phiên bản cùng tồn tại | Expand–Migrate–Contract và kiểm tra tương thích |
| **Tin feature flag sẽ tự phục hồi dữ liệu** | Rollback code không sửa được dữ liệu hỏng | Có kế hoạch dữ liệu và phục hồi phù hợp |
| **Bỏ test đỏ để merge cho kịp** | Mất bằng chứng, Increment có thể chưa đạt DoD | Điều tra nguyên nhân, không che rủi ro |
| **Tối ưu cấu trúc không gắn nhu cầu** | Đầu tư quá nhiều vào vùng ít đổi | Chọn nơi có ma sát, rủi ro và thay đổi sắp tới |
| **Refactor thành rewrite toàn hệ thống** | Chậm giao giá trị, nhiều điều chưa biết cùng lúc | Chọn lát, strangler/adapter hoặc bước chuyển tương thích |
| **Đồng nhất “test xanh” với “sản phẩm có giá trị”** | Xây đúng kỹ thuật nhưng chưa giúp người dùng | Tiếp tục đo outcome và kiểm tra Product Goal |
| **Dùng số ticket/refactor để xếp hạng người làm** | Khuyến khích chia việc hình thức và giấu lỗi | Dùng dữ liệu để cải thiện khả năng delivery của cả nhóm |

### Không phải mọi rủi ro đều cần thêm một bài test UI

Nếu kiểm tra quy tắc thuần có thể chạy trong mili giây, không nhất thiết phải khởi động trình duyệt cho mọi trường hợp. Nếu lỗi xảy ra do hợp đồng giữa hai service, thêm hàng chục unit tests cho một service có thể không giúp ích. Hãy tìm **tầng kiểm thử gần nhất với nơi rủi ro có thể xuất hiện**.

## 18. Bài thực hành: refactor module trạng thái ghi danh

### 18.1. Tình huống

Nền tảng học trực tuyến có hai đoạn mã gần giống nhau:

- API trả trạng thái của yêu cầu ghi danh để UI hiển thị.
- Service quyết định học viên có thể mở bài đầu hay không.

Cả hai đều kiểm tra `PENDING`, `ACTIVE` và `REJECTED`, nhưng code bị sao chép. Một lập trình viên dự định gom tất cả thành hàm `isEnrolled()` trả `true` cho cả `PENDING` và `ACTIVE`, vì “người học đã gửi yêu cầu”. Đây có nguy cơ cấp quyền trước khi duyệt.

**Quy tắc nghiệp vụ minh họa đã thống nhất:** chỉ đăng ký `ACTIVE` cấp quyền mở nội dung bị hạn chế; `PENDING` chỉ cho biết yêu cầu đang chờ; `REJECTED` không cấp quyền. Không có yêu cầu thay đổi nghiệp vụ trong bài tập này.

### 18.2. Nhiệm vụ cho người học

1. Xác định mục đích refactor và liệt kê **những hành vi quan sát được phải giữ**.
2. Viết ít nhất **năm kiểm thử hồi quy** cho ba trạng thái, người không có quyền và dữ liệu không hợp lệ.
3. Giải thích vì sao việc cho `PENDING` mở bài là **thay đổi hành vi**, không phải refactor.
4. Chọn một bước nhỏ để loại trùng lặp mà không làm nhập nhằng quy tắc.
5. Chỉ ra kiểm thử nào nên ở tầng **unit**, **API/integration** và **security**.
6. Lập trình tự thực hiện: test baseline, một thay đổi cấu trúc, chạy lại test, tích hợp, xem kết quả.
7. Nếu database cũ có trạng thái `WAITING` được ánh xạ sang `PENDING`, bạn sẽ kiểm chứng tương thích như thế nào?
8. Nêu một chỉ số về **khả năng thay đổi mã** và hai guardrail sau refactor.

### 18.3. Hợp đồng và bảng ví dụ tham khảo

| Trạng thái ghi danh | Học viên xem được trạng thái của chính mình? | Có quyền mở nội dung hạn chế? | Bằng chứng chính |
| --- | --- | --- | --- |
| **PENDING** | Có, nếu đã xác thực và đúng chủ thể | **Không** | Service test, API authorization test |
| **ACTIVE** | Có, nếu đúng chủ thể | **Có**, nếu các điều kiện quyền khác vẫn hợp lệ | Unit/service + integration |
| **REJECTED** | Có, nếu chính sách cho phép xem kết quả của mình | **Không** | Service/API test |
| **Không có đăng ký** | Có thể thấy trạng thái chưa ghi danh theo chính sách | **Không** | API test |
| **Người khác truy cập dữ liệu** | **Không** | **Không** | Security/API test |

Nhóm cần tách **quy tắc hiển thị trạng thái** và **quy tắc cấp quyền** dù cả hai cùng dùng một enum. Có thể dùng một kiểu dữ liệu trạng thái chung nhưng giữ các phương thức có ý nghĩa riêng: `canViewEnrollmentStatus` và `canAccessLesson`. Đừng dùng một boolean `isEnrolled` mơ hồ cho hai mục đích.

### 18.4. Một số kiểm thử có thể viết bằng Gherkin

~~~gherkin
Feature: Giữ nguyên quy tắc quyền khi refactor trạng thái ghi danh

  Scenario: Yêu cầu đang chờ không cấp quyền học
    Given học viên có yêu cầu ghi danh ở trạng thái PENDING
    When học viên gửi yêu cầu mở bài bị hạn chế
    Then hệ thống từ chối cấp nội dung hạn chế

  Scenario: Đăng ký có hiệu lực cho phép học theo chính sách
    Given học viên có đăng ký ACTIVE và đủ điều kiện truy cập
    When học viên mở bài được phép
    Then hệ thống cho phép truy cập bài đó

  Scenario: Người ngoài không được xem trạng thái của học viên
    Given người dùng A không có quyền xem dữ liệu ghi danh của B
    When người dùng A yêu cầu trạng thái đăng ký của B
    Then hệ thống từ chối truy cập dữ liệu đó
~~~

### 18.5. Lời giải tham khảo về quy trình refactor

**Bước 1 – Baseline:** kiểm tra hiện trạng bằng test cho `PENDING`, `ACTIVE`, `REJECTED`, không có đăng ký, dữ liệu sai và truy cập trái quyền. Nếu mã cũ có hành vi không đúng quy tắc, ghi nhận đó là **bug cần giải quyết riêng**, không lấy bug làm hợp đồng chuẩn.

**Bước 2 – Extract rule:** trích xuất quy tắc ánh xạ trạng thái chung hoặc bỏ trùng lặp ở phần biến đổi dữ liệu, nhưng giữ **hai phép quyết định tách biệt**: trạng thái nào có thể hiển thị và trạng thái nào cấp quyền truy cập.

**Bước 3 – Test nhỏ:** chạy unit/service tests cho từng trạng thái, xác minh không đổi kết quả. Khi tiếp tục gom phần mã, kiểm tra lại một bước một.

**Bước 4 – Integration:** dùng API/security tests để xác nhận không thể truy cập trạng thái người khác hay mở bài khi PENDING. Nếu dùng adapter ánh xạ `WAITING` sang `PENDING`, tạo fixture dữ liệu cũ và kiểm tra cả hai cách đọc trong quá trình chuyển.

**Bước 5 – Delivery:** CI chạy các kiểm tra bắt buộc, nhóm xem diff và đánh giá Definition of Done. Nếu có rollout rủi ro cao, theo dõi lỗi quyền và trạng thái bất thường sau triển khai.

**Chỉ số thiết kế:** số nơi cần sửa khi thay một quy tắc trạng thái hoặc thời gian đưa một thay đổi tương đương qua review/test. **Guardrail:** không cấp quyền cho PENDING/REJECTED; không làm lộ trạng thái của người khác. Có thể theo dõi thêm lỗi dữ liệu và trải nghiệm người học.

### 18.6. Bài tập mở rộng: khi thay đổi nghiệp vụ thật sự xuất hiện

Sau refactor, Product Owner xác nhận rằng học viên ở trạng thái `PENDING` **được xem một bài giới thiệu công khai**, nhưng vẫn không được mở bài có nội dung hạn chế. Hãy nêu:

- Tiêu chí chấp nhận nào phải cập nhật?
- Quy tắc `canAccessLesson` có cần xét **loại bài** không?
- Kiểm thử nào chứng minh bài công khai được xem, bài hạn chế vẫn bị chặn?
- Đây là refactor thuần hay một **thay đổi hành vi có chủ đích**?

Đáp án định hướng: đây là **thay đổi hành vi mới**, cần ví dụ và kiểm thử mới. Không được diễn giải nó thành “mọi PENDING đều có quyền học”. Thiết kế đã refactor tốt sẽ giúp thêm quy tắc **mà ít sửa trùng lặp hơn**, nhưng không quyết định thay nghiệp vụ.

## 19. Checklist trước, trong và sau khi refactor

- [ ] Mục tiêu refactor nói rõ **ma sát hoặc rủi ro cần giảm**, không chỉ “mã cho đẹp”?
- [ ] Có phân biệt **refactoring, bug fix, tính năng và thay đổi hợp đồng**?
- [ ] Các hành vi quan sát được cần giữ đã được xác định, nhất là **quyền, dữ liệu, lỗi và API**?
- [ ] Người có thẩm quyền đã xác nhận quy tắc nghiệp vụ mơ hồ?
- [ ] Có **đường cơ sở kiểm thử đáng tin** trước khi sửa mã?
- [ ] Legacy code thiếu test đã được bảo vệ bằng characterization tests/fixture phù hợp?
- [ ] Nếu hiện trạng sai, nhóm không mặc định biến lỗi thành hành vi phải giữ?
- [ ] Từng bước refactor đủ nhỏ để **hiểu, kiểm tra và hoàn nguyên** khi cần?
- [ ] Unit tests tập trung vào **hành vi ở ranh giới hợp lý**, không chỉ gọi phương thức private?
- [ ] Các thay đổi liên quan database, API, sự kiện hoặc đồng thời có **integration/contract tests** phù hợp?
- [ ] Các rủi ro về bảo mật, cấp quyền và dữ liệu không bị bỏ qua vì coverage cao?
- [ ] CI phản hồi đủ nhanh, đáng tin và nhóm điều tra khi test đỏ?
- [ ] Có phương án chuyển tiếp cho client/dữ liệu cũ nếu cần tương thích?
- [ ] Feature flag/canary được dùng **có chủ đích**, không thay thế kế hoạch phục hồi dữ liệu?
- [ ] Increment vẫn phải **đáp ứng Definition of Done** trước khi được coi là hoàn tất?
- [ ] Những thay đổi cấu trúc không bị kéo dài thành một rewrite không có điểm dừng?
- [ ] Công việc refactor được đánh giá bằng **khả năng thay đổi, lỗi hồi quy và chất lượng**, không chỉ số dòng mã?
- [ ] Scrum, Kanban, XP và Lean được dùng để giảm rủi ro và cải thiện dòng giá trị?
- [ ] Sau refactor, nhóm tiếp tục nhận phản hồi người dùng và đo outcome?

**Ghi nhớ:** Thiết kế tiến hóa chỉ bền vững khi nhóm có thể **cải thiện cấu trúc mà không làm hỏng hành vi đã cam kết**. Kiểm thử hồi quy, characterization tests, các bằng chứng ở tầng API/tích hợp, TDD và CI tạo những vòng phản hồi giúp refactor từng bước nhỏ có kiểm soát. Khi thay đổi liên quan hợp đồng hoặc dữ liệu, phải bảo vệ cả tương thích và khả năng khôi phục, không chỉ một bộ unit test xanh. Kết hợp refactoring với **Definition of Done, user story, Scrum, Kanban, XP và đo lường luồng** giúp Agile thay đổi an toàn, bàn giao tăng dần và học hỏi liên tục từ giá trị thực tế.
