# Vai trò của năng lực kỹ thuật đối với khả năng thích ứng

## 1. Tại sao Agile không chỉ là lập kế hoạch linh hoạt?

Một nhóm phát triển nền tảng học trực tuyến nhận được phản hồi: người học thường bấm đăng ký khóa miễn phí nhiều lần vì không thấy thông báo xác nhận rõ ràng. Product Owner muốn cải thiện luồng đăng ký trong Sprint sắp tới. Nhóm nhanh chóng làm rõ user story, sắp thứ tự Product Backlog và thống nhất mục tiêu. Tuy nhiên, khi bắt đầu thay đổi, họ gặp ba khó khăn:

- Phần giao diện và API không có kiểm thử tích hợp; một thay đổi nhỏ về mã trạng thái làm thông báo thành công biến mất.
- Mã xử lý đăng ký trùng nằm rải rác nhiều nơi; sửa một nhánh điều kiện lại làm hỏng việc hủy đăng ký.
- Việc triển khai cần thao tác thủ công, thiếu giám sát và khó xác định lỗi sau phát hành.

Nhóm có thể tổ chức Daily Scrum đúng giờ, viết user story tốt và tiếp nhận phản hồi khách hàng liên tục, nhưng **vẫn không thể thích ứng nhanh** nếu mỗi lần đổi phần mềm đều gây lỗi khó dự đoán. Đó là lý do năng lực kỹ thuật (*engineering capability*) phải đồng hành với cách tổ chức Agile.

Tuyên ngôn Agile có nguyên tắc: **liên tục quan tâm đến sự xuất sắc kỹ thuật và thiết kế tốt sẽ nâng cao tính linh hoạt**. Ý nghĩa thực hành không phải chạy theo công nghệ mới hay xây kiến trúc cầu kỳ, mà là tạo đủ năng lực để:

1. **Hiểu nhanh** tác động của nhu cầu mới.
2. **Thay đổi với phạm vi nhỏ** mà không kéo theo quá nhiều phần không liên quan.
3. **Phát hiện lỗi sớm**, trước khi lỗi trở thành vấn đề của người dùng.
4. **Tích hợp và giao Increment có chất lượng** theo nhịp bền vững.
5. **Quan sát kết quả thật** và điều chỉnh tiếp dựa trên phản hồi.

Chủ đề thuộc chương **Thực hành kỹ thuật** trong module **AGILE_DEVELOPMENT**, với phạm vi từ các giá trị/nguyên tắc Agile đến user story, backlog, Scrum, Kanban, XP và đo lường dòng công việc. Trọng tâm bài là giải thích **vì sao chất lượng kỹ thuật quyết định khả năng thích ứng**, cách phát triển năng lực đó và cách đánh giá hiệu quả thay vì chỉ đếm số công cụ đã cài.

**Thông điệp nền tảng:** *Agile giúp nhóm chọn điều cần thay đổi; năng lực kỹ thuật giúp nhóm thực hiện thay đổi ấy nhanh, an toàn và đủ thường xuyên để tiếp tục học hỏi.*

## 2. “Năng lực kỹ thuật” bao gồm những gì?

Năng lực kỹ thuật không đồng nhất với tay nghề của một lập trình viên xuất sắc hoặc với số lượng công cụ DevOps. Đó là **khả năng của cả hệ thống phát triển** trong việc thiết kế, xây dựng, kiểm chứng, tích hợp, phát hành, vận hành và cải tiến phần mềm.

| Năng lực | Câu hỏi thực tế | Đóng góp vào thích ứng |
| --- | --- | --- |
| **Thiết kế có thể thay đổi** | Khi sửa một quy tắc, phải thay bao nhiêu nơi? | Giảm phạm vi tác động và chi phí đổi hướng |
| **Kiểm thử đáng tin cậy** | Thay đổi có phá hành vi cũ hoặc ranh giới tích hợp không? | Phản hồi sớm về tính đúng đắn |
| **Tích hợp liên tục (CI)** | Mã của nhiều người có được ghép và kiểm tra thường xuyên không? | Phát hiện xung đột gần thời điểm tạo ra |
| **Tự động hóa giao hàng** | Có thể tạo artifact và triển khai lặp lại nhất quán không? | Giảm thao tác thủ công và rủi ro phát hành |
| **Quan sát vận hành** | Sau khi giao, hệ thống có hoạt động đúng cho người dùng không? | Phát hiện sai lệch và học từ thực tế |
| **An toàn, bảo mật, quyền dữ liệu** | Thay đổi có vi phạm những ranh giới bắt buộc không? | Thích ứng mà không đánh đổi an toàn |
| **Hợp tác kỹ thuật** | Kiến thức và quyết định có bị khóa ở một người không? | Giảm chờ đợi, tăng khả năng hỗ trợ nhau |
| **Quản lý nợ kỹ thuật** | Rủi ro và chi phí thay đổi có tích tụ không? | Giữ khả năng giao giá trị về lâu dài |
| **Phản hồi từ sản phẩm** | Lát cắt được giao có giải quyết vấn đề người dùng không? | Hướng công sức kỹ thuật tới giá trị thật |

Các năng lực này liên kết. Ví dụ, kiểm thử tự động tốt hỗ trợ refactoring; refactoring làm mã dễ thay đổi; thay đổi nhỏ giúp CI phát hiện xung đột sớm; CI đáng tin giúp phát hành ít rủi ro; quan sát sau phát hành giúp nhóm biết thay đổi có tạo ra outcome mong muốn không.

### 2.1. Phân biệt kỹ năng cá nhân với năng lực tổ chức

Một Developer có thể viết kiểm thử rất giỏi nhưng nếu repository không cho chạy kiểm thử trong pipeline, môi trường tích hợp thường xuyên lỗi hoặc review luôn chờ nhiều ngày thì hệ thống vẫn khó thích ứng.

Ngược lại, mua công cụ CI hiện đại không tạo năng lực kỹ thuật nếu nhóm:

- Không thống nhất thế nào là kiểm thử có giá trị.
- Để nhánh mã riêng kéo dài hàng tuần.
- Không sửa khi build chung thất bại.
- Không dành thời gian loại bỏ nút nghẽn.
- Xem chất lượng chỉ là trách nhiệm của một người kiểm thử.

**Năng lực thực tế là hành vi và kết quả có thể quan sát**, không phải danh mục công cụ hoặc chức danh.

### 2.2. Chất lượng không phải một bước đặt ở cuối

Trong phát triển thích ứng, chất lượng được tạo xuyên suốt việc làm rõ nhu cầu, thiết kế, kiểm thử, triển khai, tích hợp và vận hành. Đợi cuối Sprint mới phát hiện một quy tắc nghiệp vụ sai có thể khiến cả giao diện, API và dữ liệu phải sửa lại.

Một nhịp giao hàng khỏe mạnh không nhất thiết có nhiều dòng mã hơn; nó có **ít việc làm lại không cần thiết, ít chờ đợi hơn và nhiều phần giá trị thật sự hoàn tất hơn**.

## 3. Cơ chế: kỹ thuật tốt làm giảm chi phí thay đổi thế nào?

Khi yêu cầu thay đổi, tổng chi phí không chỉ là số giờ viết thêm mã. Nhóm còn phải hiểu hệ thống, tìm vị trí sửa, đánh giá tác động, chạy kiểm thử, tích hợp, triển khai và theo dõi kết quả.

\[
\text{Chi phí thay đổi}
\approx
\text{Hiểu vấn đề}
+\text{Sửa giải pháp}
+\text{Kiểm chứng}
+\text{Tích hợp}
+\text{Triển khai/khôi phục}
+\text{Chi phí làm lại}
\]

Đây là **mô hình tư duy**, không phải công thức dự báo chính xác có thể cộng đơn giản trong mọi hệ thống. Các hoạt động có thể song song và có hàng chờ, phụ thuộc hoặc rủi ro tác động khác nhau.

Khi mã có ranh giới rõ, kiểm thử đáng tin và môi trường tích hợp ổn định, nhóm thường giảm được **thời gian tìm tác động, thời gian chờ phản hồi và phạm vi làm lại**.

~~~mermaid
flowchart TD
    A["Phản hồi hoặc nhu cầu sản phẩm thay đổi"] --> B["Làm rõ hành vi và rủi ro"]
    B --> C["Thay đổi nhỏ trong thiết kế có thể bảo trì"]
    C --> D["Kiểm thử và tích hợp nhận phản hồi sớm"]
    D --> E{"Đạt tiêu chuẩn chất lượng?"}
    E -->|"Chưa"| F["Sửa khi phạm vi thay đổi còn nhỏ"]
    F --> C
    E -->|"Có"| G["Tạo Increment có thể sử dụng"]
    G --> H["Phát hành phù hợp, quan sát và học hỏi"]
    H --> A
~~~

### 3.1. Tốc độ sửa nhanh khác tốc độ hoàn tất nhanh

Một lập trình viên có thể sửa mã trong 30 phút nhưng pull request chờ review ba ngày và kiểm thử tích hợp chờ môi trường thêm hai ngày. Người dùng không nhận được giá trị sau 30 phút.

Vì vậy, nên nhìn **dòng thời gian từ bắt đầu đến Done** và các hàng chờ, thay vì chỉ đo thời gian gõ mã. Những thực hành như CI, review ngắn, tự động hóa môi trường và giới hạn WIP thường giúp giảm độ trễ toàn hệ thống.

### 3.2. Chất lượng bên trong tạo linh hoạt bên ngoài

Người dùng không nhìn thấy tất cả cấu trúc mã, nhưng có thể cảm nhận hậu quả: thay đổi nhanh hay chậm, lỗi lặp lại hay không, tính năng có ổn định khi mở rộng không. Khả năng chỉnh sửa cấu trúc an toàn là điều kiện để nhóm **phản hồi yêu cầu mới mà không phải viết lại toàn bộ sản phẩm**.

Điều này không có nghĩa mọi cải thiện thiết kế đều lập tức tạo giá trị người dùng. Nhóm cần chọn cải tiến kỹ thuật giải quyết một **khó khăn, rủi ro hoặc chi phí thay đổi có thật**, không làm phức tạp sản phẩm vì muốn đạt một hình mẫu kiến trúc lý tưởng.

## 4. Vòng phản hồi ngắn là đòn bẩy kỹ thuật

Agile coi phản hồi sớm là nguồn học hỏi. Trong kỹ thuật phần mềm, phản hồi có nhiều cấp độ với độ nhanh và phạm vi khác nhau.

| Vòng phản hồi | Điều có thể học | Thực hành hỗ trợ | Giới hạn |
| --- | --- | --- | --- |
| **Trong vài phút phát triển** | Logic nhỏ có hoạt động như mong muốn? | Unit test, kiểm tra kiểu, linter, thử ví dụ nhỏ | Không xác minh toàn hệ thống |
| **Khi ghép thay đổi** | Các thành phần có còn tương thích? | CI, contract test, integration test, review | Chỉ phát hiện những gì đã kiểm chứng |
| **Khi hoàn tất lát cắt** | Hành vi nghiệp vụ có đáp ứng acceptance criteria và DoD? | Kiểm thử chấp nhận, exploratory test, kiểm tra bảo mật phù hợp | Có thể chưa có dữ liệu dùng thật |
| **Khi phát hành an toàn** | Sản phẩm có hoạt động trong môi trường thực? | Triển khai theo giai đoạn, log, metrics, tracing | Hoạt động đúng chưa chắc tạo giá trị |
| **Khi người dùng sử dụng** | Giải pháp có cải thiện nhu cầu thật? | Usability test, phân tích hành vi, phỏng vấn, đo outcome | Cần tránh kết luận nhân quả vội vàng |

### 4.1. Vì sao phản hồi muộn làm tăng công làm lại?

Giả sử nhóm hiểu sai điều kiện “chỉ được đăng ký một lần” thành “không bao giờ được đăng ký lại”, trong khi nghiệp vụ thực tế cho phép đăng ký lại sau khi hủy. Nếu làm rõ ngay trong refinement với một ví dụ, việc sửa chỉ là thay điều kiện dự kiến. Nếu phát hiện sau khi xây API, giao diện, migration và các luồng kiểm thử dựa trên giả định cũ, nhiều phần phải sửa.

**Tác động của phản hồi phụ thuộc thời điểm và khả năng hành động**, không phải cứ tăng số lượng kiểm thử là tự động cải thiện. Nhóm phải lựa chọn đúng ví dụ có nguy cơ và trao đổi với người có thẩm quyền nghiệp vụ.

### 4.2. Phản hồi âm tính có giá trị khi đáng tin

Một kiểm thử báo đỏ giúp phát hiện sai khác, nhưng nếu kiểm thử thường xuyên thất bại ngẫu nhiên (*flaky*) thì cả nhóm có thể mất lòng tin và bỏ qua cảnh báo. Năng lực kỹ thuật bao gồm **duy trì độ tin cậy của tín hiệu**, không chỉ tạo nhiều cảnh báo.

## 5. Kiểm thử tự động: lưới an toàn để thay đổi thường xuyên

Kiểm thử tự động giúp bảo vệ những hành vi quan trọng khi nhóm liên tục bổ sung hoặc thay đổi mã. Nó là **phương tiện phản hồi**, không phải một con số chứng minh phần mềm không còn lỗi.

### 5.1. Chọn loại kiểm thử theo ranh giới rủi ro

| Loại kiểm thử | Ranh giới kiểm tra | Ví dụ | Điều chưa bảo đảm |
| --- | --- | --- | --- |
| **Unit test** | Logic nhỏ, ít phụ thuộc ngoài | Quy tắc từ chối đăng ký trùng | UI và dữ liệu thật phối hợp đúng |
| **Component test** | Một thành phần có phụ thuộc được kiểm soát | Dịch vụ đăng ký với dữ liệu test | Hợp đồng giữa mọi dịch vụ vẫn đúng |
| **Contract test** | Thỏa thuận giao tiếp consumer–provider | Trường trạng thái API và kiểu lỗi | Mọi luồng xuyên hệ thống đều đúng |
| **Integration test** | Nhiều thành phần kết hợp | API lưu thành công và dữ liệu có thể đọc lại | Toàn bộ trải nghiệm người dùng dễ hiểu |
| **End-to-end test** | Luồng quan trọng qua nhiều lớp | Đăng nhập, đăng ký và thấy khóa đã đăng ký | Không có lỗi ở mọi tình huống hoặc tải cao |
| **Security/performance test** | Rủi ro đặc thù | Quyền dữ liệu; đáp ứng giới hạn độ trễ | Không có bất kỳ lỗ hổng hay nút nghẽn nào |
| **Exploratory test có chủ đích** | Trường hợp chưa mô tả đủ bằng script | Thao tác lặp, mất mạng, đầu vào bất thường | Không thay thế bộ kiểm thử lặp lại có giá trị |

Kiểm thử phù hợp phụ thuộc sản phẩm và rủi ro. Không có tỷ lệ unit/integration/end-to-end cố định do Agile hay Scrum bắt buộc cho mọi hệ thống. Những luồng thanh toán, phân quyền và dữ liệu cá nhân có thể cần kiểm tra sâu ở những ranh giới khác nhau.

### 5.2. Kiểm thử đúng hành vi thay vì quá phụ thuộc cách cài đặt

Một kiểm thử mong đợi đúng tên một hàm private hoặc số lần gọi nội bộ có thể thất bại khi Developer chỉ refactor mà không đổi hành vi người dùng. Những kiểm thử như vậy đôi khi cần cho một thiết kế cụ thể, nhưng nếu dùng khắp nơi, chúng khiến nhóm sợ thay đổi cấu trúc.

Khi có thể, ưu tiên mô tả **hành vi và bất biến có ý nghĩa**:

- Người học không tạo hai đăng ký đang có hiệu lực cho cùng khóa.
- Trạng thái thất bại không được hiển thị như đã đăng ký thành công.
- Một tài khoản không đọc được danh sách khóa riêng của tài khoản khác.
- Khi đăng ký hợp lệ, kết quả có thể được truy xuất nhất quán.

Những điều này bền hơn việc kiểm tra từng bước cài đặt nội bộ.

### 5.3. Kiểm thử tạo sự tự tin vừa đủ, không phải bảo đảm tuyệt đối

**Code coverage 100% không đồng nghĩa không có lỗi.** Nếu kiểm thử chỉ đi qua dòng lệnh mà không xác nhận hành vi có ý nghĩa, coverage cao vẫn có thể bỏ sót quy tắc nghiệp vụ sai. Mặt khác, coverage thấp ở các luồng rủi ro cao là tín hiệu nên xem xét.

Không nên dùng coverage hoặc số test như KPI cá nhân. Đặt câu hỏi: **Thay đổi quan trọng nào nhóm còn sợ thực hiện vì không biết cách xác minh?**

## 6. Ví dụ mã: từ quy tắc nghiệp vụ tới kiểm thử có ích

Giả sử cần quy tắc đăng ký khóa miễn phí:

- Tài khoản phải đăng nhập.
- Khóa phải đang cho phép đăng ký.
- Một người không thể tạo thêm đăng ký đang có hiệu lực trùng nhau.

Ta bắt đầu bằng một lớp chính sách nhỏ, tách logic ra khỏi HTTP, cơ sở dữ liệu và giao diện. **Ví dụ Java dưới đây giả định Java 17+** (dùng record) và chỉ minh họa quy tắc; nó không phải toàn bộ hệ thống đăng ký.

~~~java
public final class EnrollmentPolicy {
    private EnrollmentPolicy() {
    }

    public record Decision(boolean allowed, String reason) {
    }

    public static Decision evaluate(
            boolean loggedIn,
            boolean courseOpen,
            boolean alreadyEnrolled
    ) {
        if (!loggedIn) {
            return new Decision(false, "LOGIN_REQUIRED");
        }
        if (!courseOpen) {
            return new Decision(false, "COURSE_CLOSED");
        }
        if (alreadyEnrolled) {
            return new Decision(false, "ALREADY_ENROLLED");
        }
        return new Decision(true, "ALLOWED");
    }
}
~~~

Các kiểm thử minh họa dùng **JUnit Jupiter**; muốn thực thi cần dependency và cấu hình dự án tương ứng:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class EnrollmentPolicyTest {
    @Test
    void allowsEligibleEnrollment() {
        var result = EnrollmentPolicy.evaluate(true, true, false);

        assertTrue(result.allowed());
        assertEquals("ALLOWED", result.reason());
    }

    @Test
    void refusesDuplicateEnrollment() {
        var result = EnrollmentPolicy.evaluate(true, true, true);

        assertFalse(result.allowed());
        assertEquals("ALREADY_ENROLLED", result.reason());
    }

    @Test
    void requiresAuthentication() {
        var result = EnrollmentPolicy.evaluate(false, true, false);

        assertFalse(result.allowed());
        assertEquals("LOGIN_REQUIRED", result.reason());
    }

    @Test
    void refusesClosedCourse() {
        var result = EnrollmentPolicy.evaluate(true, false, false);

        assertFalse(result.allowed());
        assertEquals("COURSE_CLOSED", result.reason());
    }
}
~~~

Những kiểm thử này giúp nhóm nhanh chóng biết việc sửa **quy tắc thuần** có phá những hành vi đã thống nhất hay không. Khi Product Owner làm rõ rằng “đăng ký lại sau khi hủy được phép”, nhóm có thể điều chỉnh input từ cờ **alreadyEnrolled** sang trạng thái đăng ký phù hợp, viết thêm ví dụ rồi refactor mà vẫn nhìn rõ tác động.

### 6.1. Giới hạn của ví dụ unit test

Nếu hai yêu cầu đăng ký tới **đồng thời**, cả hai có thể thấy **alreadyEnrolled = false** trước khi lưu, rồi cùng tạo bản ghi. Unit test ở trên **không bảo đảm tính nhất quán dữ liệu khi có cạnh tranh**.

Hệ thống thật có thể cần:

- Ràng buộc duy nhất hoặc cơ chế nhất quán thích hợp ở tầng dữ liệu.
- Xử lý giao dịch và lỗi trùng theo quy tắc nghiệp vụ.
- Xử lý yêu cầu lặp (*idempotency*) ở điểm vào phù hợp.
- Kiểm thử tích hợp cho hai yêu cầu song song nếu đây là rủi ro quan trọng.

Đây là minh họa vì sao **thiết kế dễ kiểm thử và kiểm thử nhiều lớp bổ sung nhau**. Một lớp chính sách thuần dễ thay đổi giúp phản hồi nhanh; kiểm thử tích hợp bảo vệ các đặc tính mà unit test không mô phỏng đủ.

### 6.2. TDD giúp phát triển khả năng đổi hướng như thế nào?

Test-Driven Development (TDD) thường được mô tả bằng chu trình **Red → Green → Refactor**:

1. Viết một ví dụ hành vi cần có và thấy kiểm thử thất bại vì chưa đáp ứng.
2. Thực hiện lượng mã vừa đủ để kiểm thử đạt.
3. Cải thiện cấu trúc mã khi có lưới kiểm thử bảo vệ.
4. Lặp lại với một ví dụ nhỏ mới.

~~~mermaid
flowchart LR
    A["Red: ví dụ hành vi chưa đạt"] --> B["Green: thực hiện tối thiểu"]
    B --> C["Refactor: cải thiện thiết kế an toàn"]
    C --> D["Chọn ví dụ tiếp theo"]
    D --> A
~~~

TDD không bảo đảm thiết kế tốt hoặc đủ mọi kiểm thử, và không bắt buộc cho mọi thay đổi. Giá trị lớn nhất là **vòng phản hồi ngắn và áp lực làm rõ hành vi trước khi xây quá nhiều mã**.

## 7. Tích hợp liên tục giúp tránh chi phí ghép mã muộn

**Continuous Integration (CI)** là thực hành thường xuyên tích hợp những thay đổi nhỏ vào dòng mã chung và kiểm chứng trạng thái tích hợp bằng các kiểm tra tự động có ý nghĩa.

Trong nhóm không có CI đáng tin, những thay đổi có thể chạy riêng trên máy từng Developer nhưng lỗi khi ghép:

- Giao diện đang chờ trạng thái **success**, dịch vụ đổi thành **enrolled**.
- Cơ sở dữ liệu thay cột nhưng một dịch vụ cũ vẫn dùng schema trước đó.
- Hai thay đổi cùng sửa hành vi xử lý đơn hàng theo giả định khác nhau.
- Thư viện hoặc cấu hình khác nhau khiến pipeline hoặc môi trường thật thất bại.

**Không phải xung đột nào cũng là Git merge conflict.** Có xung đột về hành vi, hợp đồng API, dữ liệu và môi trường mà công cụ merge không thể thấy.

### 7.1. Dòng tích hợp gợi ý

~~~mermaid
flowchart TD
    A["Chọn lát cắt nhỏ"] --> B["Viết mã và kiểm thử liên quan"]
    B --> C["Đồng bộ với mã chung"]
    C --> D["Chạy kiểm tra nhanh"]
    D --> E["Tạo thay đổi / PR theo chính sách"]
    E --> F["CI: build, unit, contract, integration cần thiết"]
    F --> G{"Đủ điều kiện hợp nhất?"}
    G -->|"Chưa"| H["Điều tra và sửa sớm"]
    H --> B
    G -->|"Có"| I["Hợp nhất, kiểm tra trạng thái chung"]
    I --> J{"Mã chung vẫn đáng tin?"}
    J -->|"Không"| K["Ưu tiên khôi phục hoặc revert phù hợp"]
    K --> I
    J -->|"Có"| L["Tiếp tục lát cắt, nhận phản hồi"]
    L --> A
~~~

Một pull request tồn tại hai tuần, dù luôn chạy unit test, **vẫn tạo rủi ro tích hợp muộn**. Nhánh ngắn, review thường xuyên và kiểm chứng sau khi hợp nhất giúp giảm khoảng cách giữa các giả định kỹ thuật.

### 7.2. Xanh trước merge không chắc xanh sau merge

Hai pull request có thể đều pass trên cùng revision gốc nhưng khi hợp nhất lần lượt, chúng tương tác gây lỗi. Nhóm nên có chính sách kiểm tra **trạng thái tích hợp thực tế** hoặc dùng khả năng kiểm tra tổ hợp thay đổi trước merge nếu công cụ hỗ trợ.

Khi build chung đỏ, không nên tiếp tục hợp nhất nhiều thay đổi không liên quan. Tùy mức rủi ro, nhóm sửa, hoàn nguyên và chạy lại các kiểm tra cần thiết. Mục tiêu là khôi phục **tín hiệu kiểm chứng đáng tin**.

### 7.3. CI, Continuous Delivery và Continuous Deployment

| Thuật ngữ | Mục tiêu | Điểm khác biệt |
| --- | --- | --- |
| **CI** | Hợp nhất thường xuyên, phát hiện lỗi tích hợp nhanh | Không tự động phát hành tới người dùng |
| **Continuous Delivery** | Có thể phát hành phiên bản được kiểm chứng bằng quy trình đáng tin khi quyết định | Quyết định phát hành có thể thủ công |
| **Continuous Deployment** | Phiên bản qua các điều kiện chính sách tự động được triển khai tới môi trường đích | Cần kiểm soát và theo dõi rủi ro triển khai |

Một nhóm có CI tốt vẫn có thể phát hành theo lịch vì nghĩa vụ vận hành hoặc pháp lý. Không nên đánh đồng “đã merge” với “người dùng đã nhận giá trị”.

## 8. Refactoring giữ thiết kế dễ thay đổi

**Refactoring** là cải thiện cấu trúc bên trong của mã **mà không chủ định thay đổi hành vi bên ngoài đã được xác định**. Nó giúp nhóm tiếp tục sửa phần mềm khi nhu cầu mới xuất hiện, thay vì phải làm việc quanh những cấu trúc ngày càng khó hiểu.

### 8.1. Khi nào nên refactor?

- Khi một quy tắc bị sao chép ở nhiều nơi và dễ sửa không đồng nhất.
- Khi một hàm quá lớn khiến không thể hiểu tác động của thay đổi.
- Khi phụ thuộc vòng làm kiểm thử hoặc triển khai khó khăn.
- Khi đổi một hành vi nhỏ liên tục đòi chỉnh nhiều thành phần không liên quan.
- Khi code review cho thấy tên gọi, ranh giới trách nhiệm hoặc cấu trúc che giấu mục đích.

**Refactoring có kiểm soát** thường làm từng bước nhỏ, giữ kiểm thử chạy được và tích hợp sớm. Điều đó khác với một dự án viết lại toàn bộ vì sở thích kiến trúc mà chưa xác định giá trị hoặc rủi ro.

### 8.2. Phân biệt ba loại thay đổi

| Loại | Ví dụ | Cách kiểm chứng |
| --- | --- | --- |
| **Thay đổi hành vi** | Cho phép đăng ký lại sau khi hủy | Làm rõ acceptance criteria, cập nhật kiểm thử hành vi |
| **Refactoring** | Tách kiểm tra điều kiện đăng ký thành một lớp chính sách | Chứng minh hành vi cũ vẫn giữ nguyên |
| **Thay đổi hạ tầng/kiến trúc** | Chuyển dữ liệu từ một dịch vụ sang dịch vụ khác | Kiểm tra tương thích, migration và rủi ro vận hành |

Trong thực tế, thay đổi có thể chứa nhiều loại. Việc tách thành các bước reviewable giúp nhóm phân biệt lỗi do **đổi quy tắc** hay do **đổi cấu trúc**, từ đó sửa nhanh hơn.

### 8.3. Mã cũ thiếu kiểm thử thì làm sao?

Không nên tự tin refactor vùng mã nhiều rủi ro khi chưa hiểu hành vi hiện tại. Có thể:

1. Khảo sát luồng sử dụng và các phụ thuộc quan trọng.
2. Viết **characterization tests** ghi nhận hành vi hiện có ở những ranh giới cần bảo vệ.
3. Làm rõ với Product Owner đâu là hành vi mong muốn, đâu là lỗi cần sửa.
4. Tách thay đổi nhỏ và kiểm tra sau mỗi bước.
5. Theo dõi kết quả khi tích hợp và phát hành phù hợp.

Lưu ý: characterization test có thể ghi lại **cả hành vi sai cũ**; nó hỗ trợ phát hiện thay đổi, nhưng không tự khẳng định mọi hành vi đó cần được giữ mãi.

## 9. Thiết kế và kiến trúc hỗ trợ thay đổi có trách nhiệm

Một sản phẩm Agile thường phải thay đổi hướng khi nhận phản hồi. Thiết kế tốt làm giảm việc **một thay đổi nhỏ lan sang quá nhiều nơi**.

### 9.1. Những đặc điểm hỗ trợ khả năng thích ứng

| Đặc điểm | Ví dụ | Lợi ích |
| --- | --- | --- |
| **Cohesion — trách nhiệm tập trung** | Quy tắc đăng ký nằm ở một mô-đun dễ tìm | Khi nghiệp vụ đổi, biết nơi cần sửa |
| **Coupling có kiểm soát** | Giao diện dùng API/hợp đồng rõ thay vì phụ thuộc chi tiết DB | Dễ thay đổi thành phần mà ít tác động lan truyền |
| **Ranh giới dữ liệu rõ** | Quyền tài khoản được kiểm tra ở dịch vụ | Tránh lỗi khi UI thay đổi |
| **Hợp đồng có thể kiểm chứng** | Contract test cho trạng thái đăng ký | Phát hiện sai khác consumer/provider |
| **Khả năng quan sát** | Log sự kiện đăng ký lỗi kèm correlation ID phù hợp | Chẩn đoán lỗi sau phát hành nhanh hơn |
| **Đơn giản hóa có chủ đích** | Không tạo nhiều tầng trừu tượng chưa có nhu cầu | Giảm chi phí nhận thức và bảo trì |
| **Đổi hướng có kiểm soát** | Feature flag hoặc cấu trúc thay thế dịch vụ khi có rủi ro thật | Giảm chi phí thử và khôi phục |

### 9.2. “Simple design” không phải “thiết kế sơ sài”

Thiết kế đơn giản nghĩa là chọn **cấu trúc ít phức tạp nhất vẫn đáp ứng nhu cầu và các ràng buộc đã biết**. Nó có thể bao gồm kiểm tra phân quyền, ràng buộc dữ liệu, mã dễ kiểm thử và quan sát lỗi — dù những việc đó làm thay đổi đầu tiên tốn công hơn.

Ngược lại, dựng hệ thống microservice cho một sản phẩm nhỏ chưa có nhu cầu độc lập triển khai có thể tăng độ phức tạp. Kiến trúc nguyên khối được mô-đun hóa tốt vẫn có thể thích ứng nhanh hơn một tập dịch vụ bị phụ thuộc chặt.

**Không có kiến trúc “Agile chuẩn” duy nhất.** Quyết định phải dựa trên loại thay đổi dự kiến, rủi ro vận hành, năng lực nhóm và khả năng thu thập phản hồi.

### 9.3. Quyết định dễ đảo ngược và khó đảo ngược

Một màn hình thử nghiệm có thể thay nhanh; chọn mô hình dữ liệu cho lịch sử thanh toán hoặc chuyển dữ liệu cá nhân sang bên thứ ba thường khó đảo ngược hơn. Nhóm nên giữ các phương án ở những điểm rủi ro lớn, tạo spike hoặc thử nghiệm có giới hạn trước khi cam kết.

Tuy nhiên, trì hoãn quá lâu cũng tạo chi phí. **Chọn muộn nhất có trách nhiệm** nghĩa là có đủ bằng chứng hoặc đến ngưỡng phải chốt để không đánh mất khả năng giao hàng an toàn.

### 9.4. Migration dữ liệu cũng là vấn đề thích ứng

Nếu cần đổi cấu trúc dữ liệu mà các phiên bản ứng dụng có thể cùng tồn tại, nhóm có thể dùng chiến lược **expand–migrate–contract**:

1. Mở rộng schema theo cách tương thích khi cần.
2. Chuyển dữ liệu và cập nhật các thành phần theo từng bước.
3. Chỉ bỏ phần cũ khi các phụ thuộc đã hết và điều kiện an toàn được kiểm chứng.

Đây là kỹ thuật tham khảo, không phải mỗi migration đều phải có ba đợt phát hành. Quan trọng là **không làm thay đổi một nơi khiến những phiên bản khác mất khả năng hoạt động**.

## 10. Khả năng vận hành là một phần của năng lực thay đổi

Nếu nhóm giao một Increment nhưng không biết người dùng đang gặp lỗi gì, phản hồi thực tế bị chậm. Vì vậy năng lực thích ứng bao gồm cả việc **quan sát và hỗ trợ hệ thống sau khi triển khai**.

### 10.1. Ba nguồn quan sát thường dùng

- **Logs:** Ghi sự kiện cần thiết để điều tra, hạn chế dữ liệu nhạy cảm và tránh ghi thông tin nhận dạng không cần thiết.
- **Metrics:** Thể hiện xu hướng về tỷ lệ lỗi, độ trễ, lưu lượng, mức sử dụng tài nguyên và các chỉ số phù hợp với nhu cầu.
- **Traces:** Hỗ trợ theo dõi một yêu cầu qua các thành phần phân tán khi kiến trúc có nhu cầu.

Ví dụ, trong luồng đăng ký khóa học, nhóm có thể theo dõi tỷ lệ đăng ký thất bại, độ trễ API, lỗi không đồng bộ trạng thái và số yêu cầu trùng theo định nghĩa an toàn. Các quan sát giúp phát hiện khi phiên bản mới làm tăng lỗi dù pipeline CI xanh.

### 10.2. Quan sát kỹ thuật và quan sát kết quả sản phẩm

| Câu hỏi | Tín hiệu thích hợp |
| --- | --- |
| Hệ thống có xử lý yêu cầu đúng và ổn định không? | Lỗi, độ trễ, kiểm tra tính nhất quán |
| Người học có hiểu kết quả đăng ký không? | Usability test, phản hồi và quan sát hành trình |
| Người học có bắt đầu học sau đăng ký không? | Chỉ số outcome được định nghĩa và thu thập hợp lệ |
| Khi lỗi xuất hiện, nhóm mất bao lâu để phát hiện/khôi phục? | Thời gian phát hiện và khôi phục, theo cách đo rõ |

**Hệ thống hoạt động đúng không đồng nghĩa tính năng có giá trị.** Agile cần cả kỹ thuật đáng tin và phản hồi về nhu cầu.

### 10.3. Kế hoạch phát hành và khôi phục

Với thay đổi có rủi ro, nhóm có thể cân nhắc phát hành theo đợt, feature flag, smoke test, theo dõi và phương án rollback. Không phải rollback nào cũng chỉ là chạy lại phiên bản mã cũ: với thay đổi dữ liệu có tính không đảo ngược, cần kế hoạch phục hồi riêng và đánh giá ảnh hưởng.

Khi có sự cố, ưu tiên an toàn và quy trình ứng cứu được phê duyệt; không viện dẫn “thử nhanh” để bỏ qua quyền dữ liệu hoặc tiêu chuẩn vận hành bắt buộc.

## 11. Security và quyền riêng tư phải nằm trong dòng công việc

Một thay đổi có vẻ nhỏ như thêm gợi ý khóa học có thể đụng tới dữ liệu hành vi cá nhân. Nếu chỉ rà soát bảo mật vào cuối Sprint, nhóm có nguy cơ phải sửa lại kiến trúc hoặc thậm chí không được phép triển khai.

**Shift left** trong bối cảnh này là xem rủi ro phù hợp **sớm hơn**, không phải đưa mọi trách nhiệm bảo mật cho Developers mà không có hỗ trợ chuyên môn.

| Thời điểm | Câu hỏi an toàn cần cân nhắc |
| --- | --- |
| Làm rõ PBI | Dữ liệu nào được dùng, ai có quyền truy cập, có điều kiện pháp lý/hợp đồng nào? |
| Thiết kế | Quyền được thực thi ở đâu, có ranh giới tin cậy nào, dữ liệu được giữ bao lâu? |
| Phát triển | Có kiểm tra đầu vào, phân quyền và quản lý secret phù hợp không? |
| CI | Có kiểm tra phụ thuộc, lộ secret, thay đổi cấu hình rủi ro theo chính sách không? |
| Tích hợp | Hành vi từ nhiều thành phần có tạo đường truy cập ngoài ý muốn không? |
| Phát hành | Có quyền phê duyệt và phương án xử lý sự cố theo yêu cầu? |
| Vận hành | Có giám sát rủi ro và cơ chế khắc phục/làm sạch dữ liệu phù hợp không? |

**Kỷ luật bảo mật tăng khả năng thích ứng dài hạn** vì giảm nguy cơ một lỗi nghiêm trọng khiến nhóm phải dừng mọi công việc để ứng cứu. Tuy nhiên, không nên áp mọi loại kiểm tra nặng như nhau cho thay đổi ít rủi ro; cần phân loại và đáp ứng đầy đủ những chuẩn bắt buộc.

## 12. Cộng tác kỹ thuật giúp nhóm không phụ thuộc một cá nhân

Agile nhấn mạnh con người và tương tác; năng lực kỹ thuật cũng là năng lực cộng tác.

### 12.1. Review hướng tới hiểu biết, không chỉ dấu xác nhận

Code review có thể phát hiện lỗi, xác nhận quyết định thiết kế và chia sẻ kiến thức. Một review hữu ích nên hỏi:

1. Thay đổi này phục vụ nhu cầu hoặc lỗi nào?
2. Những điều kiện nghiệp vụ quan trọng đã được kiểm chứng?
3. Có rủi ro tương thích, dữ liệu hoặc quyền truy cập nào?
4. Cấu trúc mới có làm thay đổi tiếp theo dễ hơn hay khó hơn?
5. Phạm vi PR có đủ nhỏ để hiểu và nhận phản hồi kịp thời?

Review kéo dài nhiều ngày có thể trở thành nút nghẽn. Giảm kích thước PR, thời gian chờ và làm rõ tiêu chí review đôi khi quan trọng hơn thêm người phát triển tính năng.

### 12.2. Pair programming và mob/ensemble programming

Làm việc cặp hoặc nhóm có thể hữu ích khi:

- Xử lý phần mã phức tạp hoặc ít người biết.
- Thiết kế thử một ranh giới tích hợp.
- Điều tra lỗi khó tái hiện.
- Chuyển giao kiến thức cho người mới.
- Thực hiện một thay đổi bảo mật cần nhiều góc nhìn.

Những thực hành này không bắt buộc áp cho mọi tác vụ và không phải lúc nào cũng làm tăng throughput ngắn hạn. Giá trị có thể đến từ **ít lỗi hơn, phản hồi nhanh hơn, nhiều người có thể hỗ trợ và giảm phụ thuộc lâu dài**.

### 12.3. Trách nhiệm chất lượng thuộc về cả nhóm

Một Scrum Team có thể có nhiều chuyên môn, nhưng Developers cùng chịu trách nhiệm tạo Increment đạt DoD. Không nên coi “lập trình xong rồi chuyển cho QA” là ranh giới bàn giao làm mất trách nhiệm. Chuyên gia kiểm thử giúp nhóm nhìn rủi ro sâu hơn; chuyên gia vận hành giúp nhóm hiểu khả năng triển khai; những góc nhìn đó nên tham gia sớm khi cần.

Ngược lại, không phải mọi thành viên có quyền thao tác trên production hoặc phê duyệt thay đổi dữ liệu nhạy cảm. Tự quản cần **quyền hạn rõ và cộng tác đúng chuyên môn**.

## 13. Definition of Done kết nối giá trị với chất lượng kỹ thuật

Trong Scrum, **Definition of Done (DoD)** là commitment của **Increment**, mô tả trạng thái chất lượng mà một phần sản phẩm phải đạt để được coi là hoàn tất.

Các thành phần thường được nhắc cùng DoD nhưng có vai trò khác nhau:

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Sprint Goal** | Vì sao Sprint này có giá trị? | Người học đăng ký khóa miễn phí và thấy xác nhận đáng tin |
| **Acceptance criteria** | Hành vi riêng của PBI cần đúng thế nào? | Đăng ký lặp không tạo bản ghi trùng |
| **DoD** | Chuẩn chất lượng chung nào cần đạt để PBI thành phần của Increment? | Kiểm thử cần thiết đạt, tích hợp và bảo mật áp dụng được bảo đảm |
| **Technical task** | Hoạt động nào cần thực hiện để đạt kết quả? | Thêm integration test và migration tương thích |
| **CI check** | Bằng chứng tự động nào có thể kiểm chứng? | Build, unit/contract/integration test trên revision đã chọn |

**DoD không phải danh sách kiểm tra do một công cụ CI tự sinh.** Một pipeline xanh có thể là bằng chứng cho một số điều kiện, nhưng có những điều còn cần review chuyên môn, kiểm thử khám phá hoặc xác nhận yêu cầu ngoài hệ thống.

### 13.1. Một DoD minh họa cho nền tảng học trực tuyến

Nhóm có thể thống nhất những loại điều kiện phù hợp như:

- Hành vi theo acceptance criteria được kiểm chứng.
- Những kiểm thử tự động và kiểm tra thủ công cần thiết đã thực hiện.
- Thay đổi được review, tích hợp và không phá chức năng quan trọng.
- Quyền truy cập và bảo mật áp dụng được kiểm tra.
- Các yêu cầu vận hành, cấu hình hoặc tài liệu cần thiết đã được đáp ứng.
- Không còn vấn đề chất lượng ngăn phần sản phẩm được coi là có thể sử dụng.

Đây là **ví dụ tham khảo**, không phải DoD bắt buộc cho mọi dự án. Nếu tổ chức có chuẩn áp dụng, Scrum Team phải đáp ứng chuẩn đó; nếu chưa có, Scrum Team cần tạo DoD phù hợp cho sản phẩm.

**Không được hạ DoD chỉ để giữ báo cáo tiến độ**. Công việc chưa đạt DoD không trở thành phần Increment đã hoàn tất, dù mã đã merge và giao diện có thể demo.

### 13.2. Chất lượng được tính trong công việc, không để ngoài kế hoạch

Nếu PBI “đăng ký khóa miễn phí” được ước lượng chỉ bằng thời gian viết UI và API, rồi kiểm thử và tích hợp được coi là phát sinh, dự báo hoàn tất sẽ sai ngay từ đầu. Developers cần xem **công việc tới Done**, bao gồm review, kiểm thử, xử lý lỗi và yêu cầu chất lượng.

Một phần năng lực có thể được dành riêng cho cải thiện pipeline, bảo trì hoặc giảm rủi ro kỹ thuật đã biết. Cần tránh đếm trùng nếu các hoạt động đó đã nằm trong ước lượng PBI.

## 14. Công việc kỹ thuật được ưu tiên thế nào trong Product Backlog?

Không phải mọi cải thiện kỹ thuật đều mang giá trị như nhau tại cùng thời điểm. Một việc không trực tiếp tạo màn hình mới vẫn có thể có giá trị lớn nếu giảm rủi ro mất dữ liệu hoặc loại nút nghẽn khiến mọi Sprint bị chậm.

### 14.1. Mô tả “technical debt” bằng tác động thật

Thay vì chỉ ghi “refactor service đăng ký”, hãy làm rõ:

> “Mỗi lần đổi quy tắc đăng ký, Developers phải sửa ba nơi và mất nhiều ngày kiểm tra hồi quy. Chúng ta muốn hợp nhất quy tắc nghiệp vụ tại một ranh giới được kiểm thử để giảm nguy cơ sai khác và giúp thay đổi tiếp theo an toàn hơn.”

Thông tin hữu ích gồm:

- **Vấn đề hiện tại:** Lỗi, chờ đợi, làm lại hay khó phát triển gì?
- **Tác động:** Ai bị ảnh hưởng, mức rủi ro hoặc chi phí thay đổi?
- **Kết quả mong muốn:** Giảm xung đột, phát hiện lỗi sớm, nâng khả năng vận hành?
- **Bằng chứng hoàn tất:** Kiểm thử mới, thời gian chờ giảm, đường mã cũ được thay an toàn?
- **Chi phí cơ hội:** Công việc nào bị hoãn khi đầu tư cải tiến này?

### 14.2. Bốn cách xử lý nợ kỹ thuật

| Tình huống | Cách tiếp cận phù hợp |
| --- | --- |
| Rủi ro bảo mật hoặc dữ liệu nghiêm trọng, có nghĩa vụ bắt buộc | Xử lý theo mức khẩn và thẩm quyền |
| Nợ kỹ thuật nằm đúng chỗ đang thay đổi | Refactor đủ mức cùng PBI, thêm kiểm thử bảo vệ |
| Nút nghẽn CI gây ảnh hưởng nhiều hạng mục | Tạo công việc cải tiến rõ ràng, ưu tiên dựa trên tác động toàn luồng |
| Mã ít thay đổi, rủi ro thấp và chi phí sửa cao | Có thể theo dõi, chưa ưu tiên ngay |

Không nên dùng quy tắc “phải dành chính xác 20% năng lực cho nợ kỹ thuật” như luật Agile. Tỷ lệ cố định có thể là **thỏa thuận thử nghiệm** nếu nhóm có lý do, nhưng giá trị của từng công việc vẫn phải được xem xét.

### 14.3. Kết nối với Product Owner

Trong Scrum, Product Owner chịu trách nhiệm tối đa hóa giá trị và quản lý hiệu quả Product Backlog. Developers cung cấp bằng chứng về tác động kỹ thuật, chi phí và rủi ro. Hai bên nên cùng hiểu vì sao một đầu tư kỹ thuật có thể giúp phục vụ khách hàng nhanh hơn hoặc giảm nguy cơ nghiêm trọng.

Không nên chỉ nói “đây là việc kỹ thuật nên Product Owner không cần biết”, cũng không nên để Product Owner tự chỉ định cách refactor cụ thể thay Developers. **Giá trị và phương án thực hiện cần được trao đổi ở đúng trách nhiệm**.

## 15. Ví dụ xuyên suốt: thay đổi quy tắc đăng ký khóa học

### 15.1. Bối cảnh và mục tiêu

Sản phẩm hiện hỗ trợ đăng ký khóa miễn phí. Sau phản hồi người dùng, Product Owner yêu cầu:

> “Người học đã hủy đăng ký một khóa có thể đăng ký lại khi khóa còn mở, nhưng không được tạo hai đăng ký đang có hiệu lực cùng lúc.”

Nhóm nhận thấy hệ thống cũ có:

- Quy tắc trạng thái đăng ký sao chép ở giao diện và hai dịch vụ.
- Kiểm thử chủ yếu kiểm tra trường hợp thành công.
- Migration dữ liệu đăng ký chưa được thử với bản ghi cũ.
- Một PR thường tồn tại nhiều ngày vì khó review.
- Môi trường tích hợp không ổn định.

Nếu nhóm chỉ thêm một nhánh điều kiện ở giao diện, khả năng cao lỗi sẽ tái xuất ở API hoặc dữ liệu.

### 15.2. Phân rã công việc theo rủi ro và giá trị

| Bước | Lát cắt hoặc hoạt động | Mục tiêu học hỏi/chất lượng |
| --- | --- | --- |
| 1 | Làm rõ trạng thái Active, Cancelled và các ví dụ | Không hiểu sai nghiệp vụ đăng ký lại |
| 2 | Viết kiểm thử hành vi cho trạng thái và quyền truy cập | Có lưới an toàn khi đổi logic |
| 3 | Tách quy tắc đăng ký về ranh giới dễ kiểm chứng | Giảm sửa lặp giữa thành phần |
| 4 | Kiểm tra ràng buộc dữ liệu và migration | Không tạo bản ghi Active trùng hoặc làm mất dữ liệu hợp lệ |
| 5 | Tích hợp API với giao diện qua PR nhỏ | Phát hiện hợp đồng sai sớm |
| 6 | Kiểm thử luồng xuyên hệ thống, quan sát và hoàn tất DoD | Increment đúng và an toàn |
| 7 | Phát hành theo chính sách, theo dõi lỗi và phản hồi | Xác nhận kết quả thực tế |

Một số bước có thể chồng lắp, nhưng phải giữ **chuỗi phụ thuộc rủi ro** hợp lý. Ví dụ, nếu chưa rõ quy tắc hủy và đăng ký lại, xây migration dữ liệu vội có thể phải sửa lớn.

### 15.3. Ví dụ acceptance criteria

~~~gherkin
Tính năng: Đăng ký lại khóa học miễn phí

  Tình huống: Đăng ký lần đầu
    Cho trước người học đã đăng nhập
    Và khóa "Java nhập môn" còn mở
    Và người học chưa có đăng ký đang có hiệu lực cho khóa này
    Khi người học yêu cầu đăng ký
    Thì hệ thống tạo một đăng ký đang có hiệu lực
    Và hiển thị trạng thái đăng ký thành công

  Tình huống: Đăng ký lại sau khi hủy
    Cho trước người học đã hủy đăng ký "Java nhập môn"
    Và khóa vẫn cho phép đăng ký
    Khi người học yêu cầu đăng ký lại
    Thì hệ thống có đúng một đăng ký đang có hiệu lực cho người học và khóa đó
    Và kết quả được hiển thị đúng

  Tình huống: Gửi hai yêu cầu gần đồng thời
    Cho trước người học đã đăng nhập
    Và khóa còn mở
    Khi hai yêu cầu đăng ký cùng khóa được gửi gần đồng thời
    Thì hệ thống không tạo hai đăng ký đang có hiệu lực trùng nhau
    Và phản hồi của các yêu cầu tuân theo quy tắc nghiệp vụ đã thống nhất

  Tình huống: Dịch vụ ghi dữ liệu thất bại
    Cho trước dịch vụ không thể xác nhận đã ghi đăng ký
    Khi người học yêu cầu đăng ký
    Thì giao diện không báo chắc chắn đăng ký thành công
    Và hiển thị thông tin phù hợp để kiểm tra hoặc thử lại
~~~

Các tình huống này **chưa tự trở thành test thực thi**. Nhóm cần chọn cách tự động hóa và kiểm chứng tích hợp phù hợp, cộng với điều kiện DoD và bảo mật.

### 15.4. Một ví dụ thất bại trước và sau cải tiến

**Trước cải tiến:** Backend đổi trạng thái trả về thành **ACTIVE**, frontend vẫn chờ **ENROLLED**. Unit test riêng hai phần vẫn xanh vì frontend dùng mock cũ. Sai khác chỉ bị phát hiện khi thử toàn bộ luồng vào cuối Sprint.

**Sau cải tiến:** Nhóm thống nhất hợp đồng rõ, bổ sung contract/integration test ở ranh giới UI–API và tích hợp PR nhỏ hơn. Khi backend định đổi status, kiểm thử phát hiện sớm; Developers cùng quyết định giữ tương thích hoặc cập nhật consumer có kiểm chứng.

**Lợi ích:** Không phải hợp đồng API không bao giờ được đổi, mà là **nhóm có thể đổi hợp đồng một cách có chủ đích với thông tin về tác động**, thay vì phát hiện lỗi ngẫu nhiên sau nhiều ngày.

## 16. Đo khả năng thích ứng bằng chỉ số hệ thống

Nhiều nhóm đánh giá kỹ thuật bằng số commit, story point hoặc phần trăm code coverage. Những chỉ số này có thể hỗ trợ một mục đích hẹp, nhưng **không trực tiếp đo khả năng giao giá trị an toàn**.

### 16.1. Kết hợp dòng công việc, chất lượng và kết quả sản phẩm

| Tín hiệu | Câu hỏi | Rủi ro khi diễn giải |
| --- | --- | --- |
| **Cycle time** | Từ lúc bắt đầu đến Done mất bao lâu? | Bị ảnh hưởng bởi cách chia item và ranh giới đo |
| **Throughput** | Có bao nhiêu item Done trong một đơn vị thời gian? | Số item không đo trực tiếp giá trị |
| **WIP / Work Item Age** | Công việc nào tồn lâu hoặc đang bị chặn? | Không được xem tuổi cao là lỗi cá nhân |
| **Thời gian chờ PR/CI** | Phản hồi kỹ thuật bị chậm ở đâu? | Chỉ tối ưu thời gian chạy mà bỏ chất lượng kiểm tra |
| **Lỗi sau phát hành** | Thay đổi có gây vấn đề cho người dùng? | Cần xem mức nghiêm trọng, khả năng phát hiện, lượng thay đổi |
| **Khả năng khôi phục** | Khi lỗi xảy ra, nhóm phát hiện và phục hồi ra sao? | Không thể đánh giá qua một sự cố đơn lẻ |
| **Sự ổn định kiểm thử** | Pipeline có đáng tin để ra quyết định? | Test xanh giả nếu bỏ kiểm tra quan trọng |
| **Outcome người dùng** | Tính năng có giải quyết nhu cầu? | Tương quan không tự chứng minh nguyên nhân |
| **Mức làm lại do lỗi kỹ thuật** | Có giảm việc sửa lặp lại hoặc thay đổi lan truyền? | Phải phân biệt làm lại do lỗi với thích ứng hợp lý theo phản hồi |

**Không có chỉ số duy nhất đủ để kết luận năng lực kỹ thuật mạnh.** Throughput tăng trong khi lỗi production tăng có thể là dấu hiệu nhóm đang đẩy rủi ro sang người dùng.

### 16.2. Nhóm chỉ số giao hàng thường được nhắc tới

Trong thực hành DevOps, các thước đo liên quan **tần suất triển khai, thời gian đưa thay đổi tới môi trường, tỷ lệ thay đổi gây thất bại và khả năng phục hồi sau sự cố** thường được sử dụng để hiểu hiệu quả giao hàng. Tùy mô hình đo và phiên bản hướng dẫn, định nghĩa có thể thay đổi; hãy công bố **cụ thể mốc đo và đối tượng đo**.

Điều quan trọng là **đọc tốc độ cùng độ ổn định**, không lấy một số để xếp hạng cá nhân hoặc đặt mục tiêu “deploy thật nhiều” mà không xét giá trị và chất lượng.

### 16.3. Ví dụ đo một cải tiến kỹ thuật

Giả sử nhóm đo **thời gian chờ từ khi PR sẵn sàng review đến khi bắt đầu review** trên những hạng mục tương đồng:

| Giai đoạn giả định | Trung vị thời gian chờ | Điều kiện bối cảnh |
| --- | --- | --- |
| Trước khi thử quy tắc PR nhỏ và review hằng ngày | 18 giờ làm việc | Nhiều PR lớn, một người review chính |
| Sau bốn tuần thử nghiệm | 7 giờ làm việc | PR nhỏ hơn, hai người có thể hỗ trợ review |

Mức giảm trung vị minh họa là:

\[
18-7=11\ \text{giờ làm việc}
\]

Nhưng muốn kết luận cải tiến **gây ra** kết quả, cần xem thêm kích thước mẫu, thay đổi loại công việc, mức WIP, lịch nghỉ và biến động bình thường. Quan trọng hơn, nhóm phải kiểm tra **cycle time tới Done, lỗi tích hợp và chất lượng review**: giảm thời gian chờ nhưng bỏ qua lỗi không phải cải tiến đúng mục tiêu.

## 17. Scrum, Kanban, XP và Lean đóng góp những gì?

### 17.1. Scrum: định hướng giá trị và tiêu chuẩn hoàn tất

Scrum đặt ra **Product Goal, Sprint Goal, Definition of Done**, các artifact, event và accountabilities. Developers tự quản cách tạo Increment, cùng chịu trách nhiệm chất lượng và điều chỉnh kế hoạch hướng tới Sprint Goal.

Năng lực kỹ thuật hỗ trợ:

- **Sprint Planning:** Developers dự báo công việc có thể đạt DoD, không chỉ code xong.
- **Daily Scrum:** Nhóm thấy build đỏ, review chờ, tích hợp nghẽn và thay đổi kế hoạch để bảo vệ Sprint Goal.
- **Sprint Review:** Có Increment dùng được để kiểm tra với stakeholder.
- **Sprint Retrospective:** Tìm nguyên nhân lặp lại của lỗi, chờ đợi và chọn cải tiến kỹ thuật có thể thử.

**Scrum không bắt buộc một công cụ CI, TDD, tỷ lệ coverage hay cấu trúc pipeline cụ thể.** Những kỹ thuật đó được chọn để giúp đạt chất lượng và khả năng giao giá trị.

### 17.2. Kanban: nhìn rõ sự chờ đợi trong luồng kỹ thuật

Kanban giúp trực quan hóa công việc và quản lý WIP. Nếu nhiều item dừng tại cột **Review/CI**, nhóm nên xử lý nút nghẽn này thay vì mở thêm nhiều PBI mới.

Những chỉ số **cycle time, throughput, work item age và WIP** giúp thấy trạng thái trước khi công việc hoàn tất. Một item đã chờ CI chín ngày không được xem là “90% Done” chỉ vì có nhiều mã; cần nhìn nguyên nhân chờ và điều kiện để đạt Done.

### 17.3. XP: những thực hành kỹ thuật hỗ trợ nhịp Agile

Extreme Programming (XP) nhấn mạnh phản hồi nhanh và kỷ luật kỹ thuật qua những thực hành như:

- TDD và kiểm thử tự động phù hợp.
- Continuous Integration.
- Refactoring và simple design.
- Pair programming, chia sẻ kiến thức.
- Small releases và cộng tác chặt với người hiểu nhu cầu.

Không phải mọi thực hành XP đều bắt buộc khi một nhóm tự nhận áp dụng Scrum, nhưng việc kết hợp hợp lý có thể giúp Scrum Team **đáp ứng DoD và thay đổi an toàn hơn**.

### 17.4. Lean: loại lãng phí và học hỏi sớm

Lean khuyến khích giảm chờ đợi, công việc dở dang, làm lại và các hoạt động không tạo giá trị. Kiểm thử sớm giúp tránh làm lại; thiết kế đơn giản giảm độ phức tạp; phát hành nhỏ giúp kiểm chứng giả định trước khi đầu tư lớn.

**Không nên hiểu Lean là cắt bỏ mọi kiểm thử hoặc tài liệu.** Một hoạt động giúp giảm rủi ro và duy trì khả năng thay đổi có thể rất có giá trị dù không tạo màn hình mới ngay.

| Cách tiếp cận | Câu hỏi cốt lõi | Năng lực kỹ thuật hỗ trợ |
| --- | --- | --- |
| **Scrum** | Sprint này tạo giá trị gì, đã đạt Done chưa? | Kiểm thử, tích hợp, DoD và Increment có thể dùng |
| **Kanban** | Việc chảy qua đâu, đang nghẽn ở bước nào? | CI, review, giảm WIP, xử lý việc già |
| **XP** | Làm sao đổi phần mềm thường xuyên mà vẫn giữ chất lượng? | TDD, CI, refactoring, design, cộng tác |
| **Lean** | Hoạt động nào tạo học hỏi/giá trị, lãng phí nằm ở đâu? | Lát cắt nhỏ, tự động hóa, giảm làm lại và chờ đợi |

## 18. Đánh đổi: bao nhiêu kỹ thuật là đủ?

Kỹ thuật tốt không đồng nghĩa **càng nhiều trừu tượng, càng nhiều test hay càng nhiều dịch vụ càng tốt**. Mọi năng lực đều có chi phí tạo và bảo trì.

### 18.1. Khi đầu tư quá ít

- Không có kiểm thử cho quy tắc có rủi ro lớn.
- Tích hợp vào cuối Sprint.
- Không biết cách triển khai/khôi phục nhất quán.
- Lỗi production lặp lại vì không có kiểm soát nguyên nhân.
- Mỗi thay đổi nhỏ phải sửa nhiều nơi và mất nhiều ngày.

Nhóm thường có vẻ nhanh lúc đầu nhưng tích lũy **chi phí thay đổi** và rủi ro, khiến phản hồi của người dùng ngày càng khó chuyển thành phần mềm đáng tin.

### 18.2. Khi đầu tư quá mức

- Xây nhiều tầng kiến trúc trước khi có nhu cầu thật.
- Duy trì quá nhiều test trùng lặp hoặc chập chờn.
- Áp quy trình phê duyệt giống nhau cho sửa câu chữ và migration dữ liệu rủi ro cao.
- Dành hàng tháng xây framework nội bộ thay vì học từ sản phẩm.
- Chạy mọi kiểm thử nặng trước từng thao tác nhỏ mà không xem thời gian phản hồi.

Điều này có thể làm feedback chậm, tăng WIP và giảm giá trị giao. Nhóm nên ưu tiên **năng lực giải quyết rủi ro có thật**.

### 18.3. Nguyên tắc chọn đầu tư

1. **Tác động:** Lỗi hoặc chi phí thay đổi này ảnh hưởng người dùng/khả năng giao hàng ra sao?
2. **Tần suất:** Phần mã hoặc hoạt động này có được thay đổi thường xuyên?
3. **Độ khó phục hồi:** Nếu sai, sửa hoặc rollback có khó không?
4. **Giá trị của kiểm tra sớm:** Một vòng feedback ngắn có tránh làm lại đáng kể?
5. **Chi phí dài hạn:** Công cụ/test/kiến trúc mới cần bao nhiêu công bảo trì?
6. **Bằng chứng:** Có cách thử nhỏ để biết đầu tư có hiệu quả?

**Chất lượng vừa đủ** không phải **chất lượng thấp nhất**. Các điều kiện an toàn, quyền dữ liệu và DoD bắt buộc phải được đáp ứng trước khi tuyên bố Done.

## 19. Kế hoạch cải tiến năng lực kỹ thuật theo từng bước

Một nhóm không cần “cải tổ toàn bộ công nghệ” trước khi bắt đầu Agile. Họ có thể chọn một vấn đề có tác động rõ và cải thiện theo vòng ngắn.

### 19.1. Ví dụ lộ trình thử nghiệm bốn tuần

| Tuần | Vấn đề tập trung | Thử nghiệm cải tiến | Bằng chứng cần quan sát |
| --- | --- | --- | --- |
| **1** | Review chờ lâu | Chia PR nhỏ hơn và thống nhất thời điểm review | Tuổi PR, thời gian chờ, chất lượng review |
| **2** | Thay đổi API hay phá UI | Thêm contract/integration test cho luồng đăng ký | Lỗi hợp đồng được phát hiện trước khi merge |
| **3** | Build chung đỏ và khó tái hiện | Sửa test flaky, làm rõ cách khôi phục build | Tỷ lệ flaky, thời gian khôi phục, mức tin cậy CI |
| **4** | Nghiệp vụ đăng ký khó thay đổi | Refactor ranh giới chính sách có kiểm thử bảo vệ | Phạm vi thay đổi, lỗi hồi quy, khả năng xử lý yêu cầu mới |

Đây là **lộ trình minh họa**, không phải cam kết mỗi cải tiến phải xong chính xác trong một tuần. Nếu lỗi bảo mật khẩn cấp xuất hiện, ưu tiên có thể thay đổi theo rủi ro thực tế.

### 19.2. Chu trình cải tiến nhỏ

~~~mermaid
flowchart TD
    A["Quan sát một trở ngại kỹ thuật"] --> B["Nêu giả thuyết nguyên nhân và mục tiêu"]
    B --> C["Chọn thay đổi nhỏ, có giới hạn"]
    C --> D["Thực hiện cùng kiểm tra chất lượng"]
    D --> E["Đo tác động lên dòng việc và lỗi"]
    E --> F{"Kết quả có ích?"}
    F -->|"Có"| G["Giữ và phổ biến thực hành"]
    F -->|"Chưa"| H["Sửa giả thuyết hoặc đổi cách thử"]
    G --> A
    H --> B
~~~

Một cải tiến nên có **người thúc đẩy, cách đánh giá và thời điểm nhìn lại**. Nếu nhóm chỉ ghi “cần nâng chất lượng code” trong Retrospective mà không thay đổi hành động, khả năng thích ứng không tự tăng.

### 19.3. Lập kế hoạch cho năng lực thực tế

Khi dự báo Sprint hoặc luồng công việc, cần tính năng lực cho:

- Công việc tạo chức năng mới **tới Done**, gồm kiểm thử và tích hợp.
- Bảo trì đã biết hoặc giảm rủi ro cần được ưu tiên.
- Hỗ trợ vận hành thường kỳ.
- Một mức dự phòng hợp lý cho sự cố và công việc phát sinh.
- Phối hợp, review và các hoạt động cải tiến cần thiết.

Không có tỷ lệ dự phòng hay tỷ lệ “tech debt” cố định do Agile bắt buộc. Nhóm cần lấy dữ liệu tải công việc thực tế, tránh đếm trùng và điều chỉnh khi điều kiện thay đổi.

## 20. Những hiểu lầm thường gặp

**1. “Agile chỉ cần họp đúng và viết user story.”** Không có năng lực kiểm thử, tích hợp và thiết kế, nhóm khó biến phản hồi thành phần mềm dùng được.

**2. “Technical excellence là dùng công nghệ mới nhất.”** Năng lực thực nằm ở khả năng giao thay đổi đúng, an toàn, bền vững và có phản hồi.

**3. “Tăng tốc nghĩa là bỏ bớt kiểm thử.”** Giảm kiểm chứng cần thiết có thể chuyển lỗi sang production và tăng thời gian làm lại.

**4. “Coverage cao nghĩa là không có lỗi.”** Coverage chỉ nói kiểm thử đi qua mã, không chứng minh hành vi hay rủi ro đã được kiểm tra đầy đủ.

**5. “Pipeline xanh đồng nghĩa đã đạt Definition of Done.”** DoD có thể còn điều kiện nghiệp vụ, bảo mật, vận hành và kiểm tra khác.

**6. “CI là chạy test trên mỗi nhánh rồi tích hợp cuối Sprint.”** CI nhấn mạnh tích hợp thường xuyên vào trạng thái chung và xử lý phản hồi sớm.

**7. “Merge được thì không còn xung đột.”** Hợp đồng API, dữ liệu và hành vi vẫn có thể sai dù Git không báo conflict.

**8. “Refactoring luôn là viết lại toàn bộ cho sạch.”** Refactoring có kiểm soát là thay cấu trúc theo bước nhỏ, giữ hành vi được kiểm chứng.

**9. “Kỹ thuật tốt nghĩa là kiến trúc càng nhiều lớp càng tốt.”** Trừu tượng hóa không có nhu cầu thật có thể tạo chi phí thay đổi lớn hơn.

**10. “Một người giỏi có thể bù cho mọi quy trình yếu.”** Phụ thuộc vào một cá nhân tạo nút nghẽn và rủi ro khi người đó vắng.

**11. “Kiểm thử là việc riêng của QA ở cuối.”** Các chuyên môn cùng chịu trách nhiệm chất lượng; trao đổi kiểm chứng cần bắt đầu sớm.

**12. “Feature flag biến mã chưa hoàn tất thành Done.”** Flag giúp kiểm soát khả năng hiển thị, không miễn các điều kiện DoD và kiểm thử.

**13. “Deploy nhiều là sản phẩm chắc tốt hơn.”** Tần suất giao hàng phải đọc cùng lỗi, khôi phục, giá trị và sự phù hợp của nhu cầu.

**14. “Technical debt nào cũng cần sửa ngay.”** Ưu tiên dựa vào tác động, rủi ro, mức thay đổi và chi phí cơ hội.

**15. “Không có thời gian cải thiện CI vì đang quá bận giao tính năng.”** Nếu CI là nút nghẽn lặp lại, bỏ qua nó có thể khiến các tính năng tiếp tục chậm và lỗi.

**16. “Tăng WIP sẽ giúp nhiều người bận và giao nhanh hơn.”** Việc dở dang có thể làm hàng chờ review, kiểm thử và tích hợp tăng; cần nhìn throughput/cycle time thật.

**17. “Số commit hoặc story point đo năng suất cá nhân.”** Chúng dễ bị làm đẹp và không phản ánh trực tiếp giá trị, chất lượng hoặc cộng tác.

**18. “Phát hành nhanh đồng nghĩa được thử mọi rủi ro trên người dùng.”** An toàn, bảo mật, quyền riêng tư và ràng buộc tổ chức luôn cần được tôn trọng.

**19. “Một cải tiến kỹ thuật phải lập tức tăng tốc mọi tính năng.”** Lợi ích có thể là giảm lỗi hiếm nhưng nghiêm trọng, giảm phụ thuộc hoặc tạo khả năng đổi hướng trong tương lai.

**20. “Scrum bắt buộc TDD, CI hoặc một kiến trúc cố định.”** Scrum xác định những yếu tố và cam kết của framework; kỹ thuật cụ thể được chọn để hỗ trợ chất lượng và giá trị.

## 21. Bài tập tình huống: nhóm Agile không thể đổi nhanh

Một Scrum Team phát triển nền tảng học trực tuyến có Sprint dài hai tuần. **Sprint Goal** là:

> “Người học đã đăng nhập có thể đăng ký lại một khóa đã hủy và thấy trạng thái chính xác.”

Product Owner đã làm rõ nhu cầu. Developers lựa chọn các PBI liên quan và bắt đầu thực hiện. Đến ngày thứ sáu:

1. Mỗi Developer có một nhánh mã riêng tồn tại năm ngày.
2. API đổi giá trị status nhưng frontend mock vẫn dùng giá trị cũ; unit test cả hai nhánh đều xanh.
3. Cơ sở dữ liệu có dữ liệu đăng ký trùng từ phiên bản cũ; migration thêm ràng buộc duy nhất chưa được thử trên dữ liệu tương đồng.
4. Pull request chờ review trung bình ba ngày; chỉ một người có quyền phê duyệt.
5. Bộ kiểm thử tích hợp bị flaky nên mọi người thường rerun đến khi xanh.
6. Scrum Team báo “80% task hoàn tất”, nhưng luồng đăng ký lại chưa chạy được từ giao diện tới dữ liệu.

### Câu hỏi

1. Những vấn đề nào thuộc **chất lượng kỹ thuật**, vấn đề nào thuộc **dòng công việc và phối hợp**?
2. Vì sao kiểm thử đơn vị xanh riêng lẻ chưa đủ bảo đảm Sprint Goal?
3. Hãy chọn **ba hành động ưu tiên** trong hai ngày tới, giải thích vì sao.
4. Những kiểm thử và bằng chứng nào cần có để thấy chức năng đăng ký lại đủ an toàn?
5. Nên xử lý dữ liệu trùng trước migration thế nào cho đúng trách nhiệm?
6. Developers và Product Owner cần trao đổi điều gì nếu phạm vi phải điều chỉnh?
7. Chọn ít nhất **bốn tín hiệu** để đánh giá cải tiến ở những Sprint sau.
8. Điều gì không nên làm chỉ để “kịp Sprint”?

### Gợi ý lời giải

**Câu 1:** Nhánh tồn lâu, review nghẽn, CI flaky và cấu hình môi trường là vấn đề dòng công việc/kỹ thuật. Hợp đồng API sai, migration chưa thử với dữ liệu cũ và thiếu kiểm thử xuyên hệ thống là rủi ro chất lượng. Chúng liên hệ nhau; không thể phân loại thành vấn đề của riêng một cá nhân.

**Câu 2:** Frontend được kiểm thử với mock cũ, backend trả hợp đồng mới. Hai bộ test riêng đều có thể xanh nhưng hành vi phối hợp sai. Cần kiểm tra **contract** và luồng **end-to-end/integration** cho những ranh giới quan trọng.

**Câu 3:** Có thể ưu tiên:

- **Gỡ nút nghẽn tích hợp:** Thống nhất hợp đồng UI–API, ghép các thay đổi nhỏ tương thích và chạy kiểm tra trạng thái chung.
- **Bảo vệ dữ liệu:** Xác định ý nghĩa bản ghi trùng, chuẩn bị kế hoạch migration có kiểm chứng; không xóa tùy tiện.
- **Khôi phục tín hiệu CI/review:** Xử lý hoặc quản lý minh bạch test flaky quan trọng, chuyển người phù hợp sang review, giảm mở việc mới.

Thứ tự cụ thể cần đánh giá rủi ro thật, nhưng mục tiêu là **có một lát cắt đăng ký lại thực sự đủ Done**, không tăng số task đóng.

**Câu 4:** Ví dụ chấp nhận cho đăng ký lần đầu, đăng ký lại sau hủy, gửi yêu cầu lặp hoặc gần đồng thời, lỗi ghi dữ liệu, quyền tài khoản; unit test chính sách; contract test API; integration test dịch vụ và DB; kiểm thử migration trên dữ liệu đại diện; các điều kiện DoD và an toàn áp dụng. Không bắt buộc mọi test phải tự động theo cùng một cách, nhưng các rủi ro trọng yếu cần bằng chứng phù hợp.

**Câu 5:** Phân tích ý nghĩa dữ liệu, người có quyền quyết định, tác động người dùng và phương án di chuyển/khôi phục. Nếu bản ghi trùng có thông tin lịch sử hợp lệ, việc tự xóa để qua migration có thể gây mất dữ liệu.

**Câu 6:** Developers trình bày khả năng hoàn tất, phụ thuộc và tác động tới Sprint Goal; cùng Product Owner làm rõ giá trị và thương lượng phạm vi khi cần. **Không giảm chất lượng hoặc âm thầm đổi mục tiêu** để hợp thức hóa việc đang trễ.

**Câu 7:** Có thể dùng thời gian chờ PR, tuổi nhánh, thời gian tới phản hồi CI, tỷ lệ flaky, cycle time tới Done, lỗi hợp đồng chỉ phát hiện ở staging, tỷ lệ phát hành có lỗi và thời gian phục hồi. Đọc chỉ số **cùng loại công việc và chất lượng**, không xếp hạng cá nhân.

**Câu 8:** Không gọi phần chưa đạt DoD là Done; không bỏ kiểm thử tích hợp bắt buộc; không xóa dữ liệu thật tùy tiện; không lạm dụng feature flag để che lỗi; không bắt mọi người làm thêm giờ như giải pháp mặc định.

### Bài tập mở rộng: thiết kế một thử nghiệm cải tiến

Hãy đề xuất một thử nghiệm kéo dài hai Sprint với cấu trúc:

| Trường | Câu trả lời mẫu |
| --- | --- |
| **Vấn đề** | Review PR mất nhiều ngày, làm tăng tuổi công việc và tích hợp muộn |
| **Giả thuyết** | Nếu chia PR thành thay đổi nhỏ và có lịch review ngắn, thời gian chờ giảm |
| **Thay đổi thử** | Mô tả phạm vi PR rõ, ưu tiên review trước khi kéo thêm việc mới |
| **Số liệu trước/sau** | Trung vị thời gian chờ, work item age, cycle time và lỗi review bỏ sót |
| **Guardrail** | Không cắt bước kiểm thử quan trọng hoặc hạ DoD |
| **Quyết định sau thử** | Giữ, điều chỉnh hoặc bỏ chính sách theo bằng chứng thu được |

Không cần chứng minh một “công thức Agile tối ưu” cho mọi nhóm. Bài tập nhằm rèn khả năng **nhận diện rủi ro kỹ thuật, tạo cải tiến nhỏ và đánh giá tác động vào dòng giá trị**.

## 22. Checklist phát triển năng lực kỹ thuật để thích ứng

### Khi làm rõ và chọn công việc

1. **Mục tiêu giá trị:** Nhóm hiểu nhu cầu người dùng và kết quả cần kiểm chứng chưa?
2. **Rủi ro kỹ thuật:** Những điểm nào có thể gây sai dữ liệu, hợp đồng hoặc quyền truy cập?
3. **Lát cắt nhỏ:** Có thể giao/kiểm chứng một phần giá trị sớm thay vì xây riêng từng tầng đến cuối?
4. **Cách kiểm thử:** Có ví dụ hành vi và kế hoạch kiểm chứng ở các ranh giới quan trọng chưa?
5. **DoD:** Những yêu cầu chất lượng, bảo mật và tích hợp đã được tính trong năng lực thực hiện chưa?

### Khi phát triển và tích hợp

6. **Thiết kế:** Thay đổi mới có tạo phụ thuộc lan rộng hoặc trừu tượng hóa không cần thiết không?
7. **Kiểm thử:** Có phản hồi nhanh và đáng tin khi sửa quy tắc?
8. **Tích hợp:** Nhánh mã và PR có được hợp nhất thường xuyên, không tồn quá lâu?
9. **Trạng thái chung:** Nếu build đỏ, nhóm có ưu tiên khôi phục theo chính sách?
10. **Review:** Có chia sẻ hiểu biết và kiểm tra tác động, không chỉ nhận dấu xác nhận?
11. **Dữ liệu:** Migration và các phiên bản đang chạy có được kiểm tra tương thích khi cần?
12. **An toàn:** Secret, phân quyền và dữ liệu thử có được bảo vệ?
13. **Công việc đang dở:** Có giảm WIP và ưu tiên hoàn tất thay vì mở thêm nhiều việc?

### Khi giao và học hỏi

14. **Increment:** Công việc đã thật sự đạt DoD hay mới “code xong”?
15. **Phát hành:** Có quy trình triển khai, giám sát và khôi phục phù hợp rủi ro?
16. **Quan sát:** Người dùng gặp lỗi gì, hệ thống phản ứng ra sao, dữ liệu được thu thập hợp lệ chưa?
17. **Outcome:** Thay đổi có giúp người dùng đạt mục tiêu tốt hơn không?
18. **Phản hồi:** Bằng chứng mới có được đưa vào Product Backlog và kế hoạch tiếp theo?

### Khi cải tiến dài hạn

19. **Nút nghẽn:** Review, CI, kiểm thử, môi trường hoặc kiến trúc đang cản dòng công việc ở đâu?
20. **Nợ kỹ thuật:** Công việc cải tiến nào có tác động thực tế và cần ưu tiên?
21. **Số liệu:** Có đọc tốc độ cùng chất lượng, WIP, work item age và lỗi sau phát hành?
22. **Cộng tác:** Kiến thức có được chia sẻ để nhóm không phụ thuộc quá nhiều một người?
23. **Đánh đổi:** Công cụ hay kiến trúc mới có lợi ích rõ lớn hơn chi phí bảo trì?
24. **Bền vững:** Nhịp giao có bảo vệ thời gian học hỏi, chất lượng và năng lực ứng phó sự cố?

## 23. Tổng kết: năng lực kỹ thuật biến phản hồi thành thay đổi an toàn

Năng lực kỹ thuật tốt không thay thế việc hiểu nhu cầu người dùng, thứ tự ưu tiên sản phẩm hay cách cộng tác Agile. Nó giúp **những quyết định sản phẩm có thể trở thành phần mềm hoạt động** với chi phí thay đổi và rủi ro ở mức có thể kiểm soát.

| Khi năng lực kỹ thuật yếu | Khi năng lực kỹ thuật được phát triển có chủ đích |
| --- | --- |
| Mỗi thay đổi nhỏ có thể làm hỏng phần không liên quan | Thiết kế và kiểm thử giúp nhìn rõ tác động |
| Phản hồi lỗi đến khi gần hết Sprint | CI và kiểm chứng sớm giúp sửa trong phạm vi nhỏ |
| Ghép mã và kiểm thử bị dồn cuối kỳ | Tích hợp và tạo Increment diễn ra liên tục |
| “Code xong” được hiểu như giao xong | DoD và kiểm tra giá trị phản ánh kết quả thật |
| Lỗi production khó phát hiện và khó phục hồi | Quan sát và quy trình vận hành hỗ trợ phản hồi nhanh |
| Chỉ một người hiểu khu vực quan trọng | Cộng tác, review và chia sẻ kiến thức giảm phụ thuộc |
| Công việc bảo trì luôn bị trì hoãn | Rủi ro kỹ thuật được ưu tiên theo tác động |
| Số task đóng là thước đo thành công | Dòng giá trị, chất lượng và outcome định hướng cải tiến |

**Ghi nhớ:** Khả năng thích ứng không đến từ việc “chấp nhận thay đổi” bằng lời nói, mà từ năng lực **thay đổi phần mềm thường xuyên, phát hiện sai sớm, bảo vệ chất lượng và học từ người dùng**. Kiểm thử có ích, tích hợp liên tục, refactoring, thiết kế đơn giản, vận hành đáng tin, bảo mật và cộng tác kỹ thuật tạo nền tảng cho điều đó. Khi kết hợp cùng backlog ưu tiên theo giá trị, Scrum, Kanban và XP, nhóm có thể giao Increment nhỏ, nhận phản hồi sớm và cải tiến liên tục mà không biến tốc độ thành lý do đánh đổi an toàn hoặc chất lượng.
