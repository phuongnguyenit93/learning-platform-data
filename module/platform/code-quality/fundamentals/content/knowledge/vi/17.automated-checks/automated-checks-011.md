# Khác biệt giữa độ nghiêm trọng và độ tin cậy của cảnh báo

Một công cụ phân tích tự động trả về hai cảnh báo trong cùng bản thay đổi Java. Cảnh báo thứ nhất mang nhãn **High severity, Low confidence**: có thể xảy ra truy vấn SQL không an toàn, nhưng công cụ chưa xác định được một giá trị đầu vào thực sự có tới đường truy vấn đó hay không. Cảnh báo thứ hai là **Low severity, High confidence**: một import không được sử dụng, và công cụ có bằng chứng trực tiếp từ cú pháp.

Nhóm nên xử lý cảnh báo nào trước? Có thể kết luận cảnh báo thứ nhất là sai vì độ tin cậy thấp không? Cảnh báo thứ hai chắc chắn đúng thì có phải là rủi ro quan trọng hơn không?

Trong module **CODE_QUALITY_FUNDAMENTALS**, chúng ta tìm hiểu những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi** hay không. Ở chương **Kiểm tra tự động**, bài này làm rõ ba khái niệm dễ bị trộn lẫn: **độ nghiêm trọng (severity)**, **độ tin cậy của cảnh báo (confidence)** và **mức ưu tiên xử lý (priority)**. Phân biệt chúng giúp nhóm tận dụng công cụ hiệu quả mà không nhầm một con số hay nhãn màu với bằng chứng về chất lượng thực tế.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích **severity** mô tả mức tác động có thể có khi vấn đề là thật, còn **confidence** mô tả mức chắc chắn của nhận định mà công cụ đưa ra.
- Phân biệt hai thuộc tính trên với **khả năng khai thác**, **mức phơi lộ**, **trạng thái đã xác minh** và **priority**.
- Phân tích cảnh báo có độ nghiêm trọng cao nhưng độ tin cậy thấp mà không bỏ qua rủi ro hoặc vội kết luận đã có lỗ hổng.
- Dùng mã Java, bài kiểm thử và ngữ cảnh dữ liệu để xác minh một số loại cảnh báo SAST, nullability, luồng dữ liệu và chất lượng mã.
- Áp dụng quy trình triage có bằng chứng, quản lý false positive/suppression và thiết lập quality gate phù hợp với rủi ro thực tế.

## 1. Công cụ cảnh báo điều gì?

Các công cụ kiểm tra tự động có thể phân tích cú pháp, kiểu, luồng điều khiển, luồng dữ liệu, cấu hình, dependency hoặc hành vi của một chương trình. Kết quả thường là một **finding** — một nhận định rằng ở vị trí nào đó có dấu hiệu vi phạm quy tắc hoặc rủi ro.

Ví dụ, một finding có thể chứa:

~~~text
Rule: JDBC_SQL_CONCATENATION
Location: ReportRepository.java:42
Severity: HIGH
Confidence: MEDIUM
Summary: Giá trị bên ngoài có thể được ghép vào truy vấn SQL
Evidence: Dữ liệu reportId đi đến Statement.executeQuery(...)
~~~

Đây là **mẫu minh họa**, không phải output chuẩn của một công cụ cụ thể. Mỗi công cụ có tên rule, thang đánh giá và thuật toán riêng; một số công cụ thậm chí không công bố trường `confidence`.

Một finding không tự động chứng minh có lỗi sản phẩm. Nó là **đầu mối để điều tra**, với các bằng chứng và giả định mà bộ phân tích cung cấp. Ngược lại, không có finding cũng không chứng minh mã an toàn hay không có lỗi.

## 2. Độ nghiêm trọng (severity): nếu vấn đề là thật thì hậu quả gì?

**Severity** thể hiện mức nghiêm trọng của ảnh hưởng mà một loại vấn đề **có thể gây ra khi nhận định được xác nhận trong bối cảnh đang xét**.

Ví dụ:

- Làm lộ dữ liệu nhạy cảm qua endpoint công khai có thể có tác động rất cao.
- Tạo tổng tiền sai trong một chức năng thanh toán có thể ảnh hưởng trực tiếp tới tài chính và tính đúng đắn.
- Một cảnh báo đặt tên không nhất quán có thể gây khó bảo trì nhưng thường không có cùng hậu quả với mất quyền kiểm soát dữ liệu.
- Một import không dùng thường chỉ tạo nhiễu hoặc vi phạm style, nên tác động trực tiếp thấp.

Severity trả lời câu hỏi:

> **Nếu cảnh báo này mô tả một lỗi thật trong hệ thống đang được xét, mức thiệt hại hoặc suy giảm chất lượng có thể lớn tới đâu?**

Nó **không** trực tiếp trả lời:

- Lỗi này đã được chứng minh tồn tại chưa?
- Có ai từ bên ngoài chạm được đường mã liên quan không?
- Vấn đề chắc chắn bị khai thác không?
- Phải sửa trong ngày hôm nay hay có thể lên kế hoạch?

Những câu hỏi trên cần thêm **ngữ cảnh, bằng chứng và quyết định ưu tiên**.

### Không có một thang severity dùng chung cho mọi công cụ

Một số công cụ dùng `BLOCKER / CRITICAL / MAJOR / MINOR`, công cụ khác dùng `CRITICAL / HIGH / MEDIUM / LOW / INFO`. Một số thang gộp khả năng xảy ra vào điểm risk; một số chỉ đánh giá mức tác động của rule; một số phân biệt **security severity** với **maintainability impact**.

Vì vậy khi so sánh cảnh báo từ nhiều nguồn, cần biết rõ **định nghĩa của từng thang đo**, không tự coi hai nhãn `HIGH` ở hai công cụ là tương đương về rủi ro. Nhãn severity ban đầu của rule cũng có thể cần được điều chỉnh theo phạm vi tài sản và tác động thực tế đã xác minh.

## 3. Độ tin cậy (confidence): có bao nhiêu bằng chứng cho nhận định?

**Confidence** phản ánh mức chắc chắn mà bộ phân tích gán cho việc **cảnh báo tương ứng với một vấn đề có thật**, theo dữ liệu và mô hình phân tích công cụ đang có.

Ví dụ:

- Một import không được tham chiếu trong tệp Java là hiện tượng có thể được trình biên dịch/công cụ cú pháp quan sát trực tiếp; confidence thường cao.
- Một đường đi được phân tích rõ từ đầu vào HTTP tới cách ghép SQL không tham số hóa có thể tạo confidence cao hơn một suy luận dựa trên tên phương thức.
- Nếu dữ liệu đi qua thư viện hoặc hàm tùy biến mà công cụ không hiểu, nhận định về tính an toàn của đường đi có thể có confidence thấp hơn.
- Với xử lý phản chiếu (reflection), callback, native code hoặc cấu hình được tạo động, phân tích có thể thiếu thông tin để kết luận chính xác.

Confidence trả lời:

> **Dựa trên những gì công cụ quan sát và giả định, chúng ta chắc tới mức nào rằng vấn đề được mô tả thực sự có mặt?**

**Điều rất quan trọng:** `HIGH confidence` không có nghĩa vấn đề nghiêm trọng; `LOW confidence` không có nghĩa vấn đề nhẹ. Confidence thường **không phải xác suất thống kê được hiệu chuẩn**. Một nhãn `80%` trong công cụ cũng không nên được hiểu mặc định là “cứ 100 cảnh báo thì đúng 80” nếu công cụ không công bố và kiểm chứng cách hiệu chuẩn đó.

Ngoài ra, **confidence của công cụ** khác với **trạng thái xác minh của nhóm**:

| Thuộc tính | Ai cung cấp? | Ví dụ |
| --- | --- | --- |
| Confidence ban đầu | Công cụ hoặc quy tắc phân tích | `LOW` do thiếu mô hình về một hàm sanitizer |
| Bằng chứng điều tra | Người review, test, trace, dữ liệu chạy | Input thực đi vào SQL trực tiếp |
| Trạng thái xác minh | Quy trình triage của nhóm | `CONFIRMED`, `FALSE_POSITIVE`, `NEEDS_MORE_EVIDENCE` |
| Severity sau đánh giá | Chính sách công cụ kết hợp ngữ cảnh dự án | Tác động thực tế tới dữ liệu khách hàng |
| Priority | Nhóm chịu trách nhiệm lên kế hoạch xử lý | Sửa trước phát hành, trong sprint, hoặc chấp nhận có thời hạn |

Một cảnh báo `LOW confidence` có thể trở thành **lỗi đã xác nhận** sau khi điều tra. Khi đó không cần giả vờ rằng máy đã dự đoán đúng với confidence cao từ đầu; chỉ cần ghi rõ bằng chứng bổ sung và trạng thái mới.

## 4. Ma trận hai chiều: đừng gộp severity với confidence

Xét một bảng đơn giản với hai mức cao/thấp. Đây là ví dụ **định hướng điều tra**, không phải thuật toán tự động tính ưu tiên.

| | **Confidence cao** | **Confidence thấp** |
| --- | --- | --- |
| **Severity cao** | Khả năng lớn là có vấn đề tác động nặng. Cần xác minh ngữ cảnh và xử lý ưu tiên nếu đúng. | Hậu quả tiềm tàng lớn, nhưng bằng chứng chưa đủ. **Điều tra sớm**, không mặc định bỏ qua hoặc tuyên bố đã có lỗi. |
| **Severity thấp** | Vấn đề có nhiều bằng chứng nhưng tác động nhỏ. Thường phù hợp sửa tự động hoặc theo đợt. | Tác động thấp, nhận định chưa chắc. Có thể xếp thấp hơn, lấy mẫu hoặc phân loại nếu cần. |

Ví dụ gần với công việc Java:

| Finding minh họa | Severity | Confidence | Cách suy nghĩ phù hợp |
| --- | --- | --- | --- |
| Giá trị từ HTTP có thể chảy vào câu SQL ghép chuỗi | Cao | Thấp/trung bình | Xem nguồn dữ liệu, đường đi và cách bind tham số; không kết luận từ nhãn đơn lẻ |
| Giá trị không tin cậy được chứng minh đi thẳng vào câu SQL ghép chuỗi | Cao | Cao | Ưu tiên xác nhận phạm vi và sửa cách xây truy vấn |
| Import không dùng được bộ phân tích cú pháp chỉ ra | Thấp | Cao | Có thể sửa bằng IDE/formatter, không coi đây là rủi ro khẩn cấp |
| Mã được cho là dư thừa sau một nhánh rất phức tạp | Thấp | Thấp | Xem lại luồng thực tế trước khi xóa mã |

**Ví dụ quan trọng:** Một finding `HIGH severity / LOW confidence` **không thấp rủi ro hơn** finding `LOW severity / HIGH confidence` chỉ vì ít chắc chắn hơn. Cái cần quyết định trước là **điều tra có đáng ưu tiên không**, không phải “công cụ đã chắc nên phải sửa trước”.

## 5. Priority là quyết định xử lý, không phải phép đổi nhãn đơn giản

**Priority** trả lời: *Vấn đề này cần được điều tra hoặc khắc phục khi nào, bởi ai và trước hành động nào?*

Để quyết định, nhóm thường phải xét nhiều chiều:

| Yếu tố | Câu hỏi giúp đánh giá |
| --- | --- |
| Severity / tác động | Nếu lỗi là thật, hậu quả cho người dùng, dữ liệu và vận hành là gì? |
| Confidence / bằng chứng | Đã xác nhận lỗi chưa? Đường tái hiện rõ đến đâu? |
| Phạm vi phơi lộ | Mã chạy ở endpoint công khai, tác vụ nội bộ hay mã thử nghiệm không triển khai? |
| Khả năng đến được đường lỗi | Với đầu vào nào, quyền nào và trạng thái nào đường thực thi xảy ra? |
| Tài sản bị ảnh hưởng | Chỉ dữ liệu giả lập hay thông tin nhạy cảm / giao dịch thật? |
| Biện pháp đang có | Có kiểm tra quyền, giới hạn đầu vào, cô lập tầng lưu trữ hoặc kiểm soát khác? |
| Thời điểm thay đổi | Đây là mã mới sắp phát hành hay vấn đề lâu năm? Có bản phát hành gần không? |
| Chi phí và rủi ro sửa | Có giải pháp rõ và an toàn không? Sửa gấp có thể gây hồi quy gì? |
| Chính sách nhóm | Có ngưỡng bắt buộc, SLA hoặc yêu cầu pháp lý/hợp đồng cần tuân thủ? |

Không nên quy đổi một cách máy móc:

~~~text
priority = severity * confidence
~~~

Phép nhân này dễ gây hiểu lầm: hai nhãn định tính không nhất thiết có đơn vị số học; hơn nữa, confidence thấp **không loại trừ hậu quả rất lớn** của một khả năng cần điều tra. Một cảnh báo nguy cơ rò rỉ dữ liệu quan trọng nhưng chưa đủ chứng cứ có thể phải được điều tra ngay, chứ không chờ tới khi công cụ tự tăng confidence.

Một quy trình tốt thường có **hai quyết định tách biệt**: *mức ưu tiên xác minh finding* và *mức ưu tiên khắc phục lỗi sau khi đã xác nhận*. Điều này tránh xếp một vấn đề chưa kiểm chứng vào danh sách sửa như thể đã là bug, đồng thời không bỏ quên rủi ro cao.

## 6. Ví dụ Java: từ cảnh báo SAST đến phân tích đường dữ liệu

Giả sử một hệ thống cho phép người dùng đã đăng nhập xem tiêu đề báo cáo theo mã `reportId`. Tầng HTTP truyền mã đó cho repository JDBC.

Đoạn mã sau có một mẫu thiết kế nguy hiểm:

~~~java
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.Optional;
import javax.sql.DataSource;

public final class UnsafeReportRepository {
    private final DataSource dataSource;

    public UnsafeReportRepository(DataSource dataSource) {
        this.dataSource = java.util.Objects.requireNonNull(dataSource);
    }

    public Optional<String> findTitle(String reportId)
            throws SQLException {
        String sql = "SELECT title FROM reports WHERE report_id = '"
            + reportId + "'";

        try (Connection connection = dataSource.getConnection();
             Statement statement = connection.createStatement();
             ResultSet rs = statement.executeQuery(sql)) {
            return rs.next()
                ? Optional.ofNullable(rs.getString("title"))
                : Optional.empty();
        }
    }
}
~~~

Một công cụ SAST có thể cảnh báo về **SQL injection** do ghép `reportId` vào câu truy vấn. Nếu `reportId` có nguồn từ dữ liệu mà người gọi kiểm soát và không được ràng buộc an toàn trước khi tới SQL, vấn đề có thể ảnh hưởng bí mật/toàn vẹn dữ liệu. Tùy vai trò tài khoản DB và ngữ cảnh hệ thống, tác động thực tế khác nhau.

### Tại sao cùng mẫu có thể tạo confidence khác nhau?

Với đoạn mã trên, một số công cụ có thể nhận biết trực tiếp `reportId` đi vào `Statement.executeQuery`. Nhưng trong ứng dụng thật, dữ liệu có thể đi qua nhiều lớp:

~~~text
HTTP request (reportId)
          |
          v
   ReportController
          |
          v
  ReportIdNormalizer
          |
          v
 UnsafeReportRepository
          |
          v
  Statement.executeQuery
~~~

Công cụ không hiểu `ReportIdNormalizer` có thể đánh dấu “chưa chắc giá trị còn nguy hiểm”, hoặc ngược lại suy luận “có thể nguy hiểm” dù normalizer đã bảo đảm một tập định danh cố định. Người review phải **đọc quy tắc và đường chạy thật**, thay vì coi tên `Normalizer` hay `Sanitizer` tự động chứng minh an toàn.

Ngược lại, nếu `reportId` do người dùng nhập và được ghép trực tiếp như ví dụ, bằng chứng về đường dữ liệu là rõ hơn. Severity vẫn cần xét **quyền của DB, dữ liệu liên quan, phạm vi endpoint và các lớp bảo vệ khác**; mức tác động không thể được suy chỉ từ một dòng mã.

### Sửa theo nguyên nhân, không theo nhãn confidence

Đối với giá trị trong truy vấn SQL, nên dùng **tham số ràng buộc** thay vì ghép trực tiếp vào cú pháp SQL:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Optional;
import javax.sql.DataSource;

public final class ReportRepository {
    private final DataSource dataSource;

    public ReportRepository(DataSource dataSource) {
        this.dataSource = java.util.Objects.requireNonNull(dataSource);
    }

    public Optional<String> findTitle(String reportId)
            throws SQLException {
        if (reportId == null || reportId.isBlank()) {
            throw new IllegalArgumentException("reportId is required");
        }

        String sql = "SELECT title FROM reports WHERE report_id = ?";
        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setString(1, reportId);
            try (ResultSet rs = statement.executeQuery()) {
                return rs.next()
                    ? Optional.ofNullable(rs.getString("title"))
                    : Optional.empty();
            }
        }
    }
}
~~~

`PreparedStatement` với `?` và `setString` giúp tách **giá trị đầu vào** khỏi **cú pháp câu truy vấn**, ngăn chuỗi đầu vào trở thành phần cấu trúc SQL ở vị trí giá trị đã được tham số hóa. Đây là cách sửa phù hợp hơn việc tự thêm ký tự escape cho một số trường hợp.

**Giới hạn cần nhớ:** dấu `?` không thay thế trực tiếp tên bảng/cột hoặc mọi đoạn cú pháp động. Nếu ứng dụng cần lựa chọn một tên cột để sắp xếp, hãy dùng **danh sách lựa chọn cho phép** và ánh xạ sang tên cột cố định, thay vì ghép tùy ý input vào SQL. Đồng thời, việc tham số hóa truy vấn **không tự giải quyết phân quyền từng báo cáo**; repository hoặc tầng nghiệp vụ vẫn phải kiểm tra người gọi có quyền với tài nguyên.

### Bằng chứng kiểm tra cần có

- **Code review:** xác minh mọi đường dữ liệu liên quan sử dụng bind parameter hoặc một cơ chế an toàn tương đương.
- **SAST:** chạy lại quy tắc; xác định finding cũ còn xuất hiện không và có đường tương tự ở nơi khác không.
- **Integration test:** với database test thích hợp, kiểm tra `reportId` chứa dấu nháy hoặc ký tự đặc biệt được xử lý như **giá trị**, không làm thay đổi cấu trúc truy vấn.
- **Authorization test:** người dùng A không được xem báo cáo B nếu chính sách có quy định quyền sở hữu.
- **Kiểm thử hồi quy:** truy vấn vẫn trả đúng báo cáo tồn tại và kết quả vắng mặt cho mã không tồn tại.

Một unit test chỉ assert câu SQL có dấu `?` là **bằng chứng yếu**: nó không chứng minh adapter thật bind đúng giá trị, câu truy vấn chạy đúng hay quyền truy cập được bảo vệ. Cần chọn mức test tương ứng với điều cảnh báo mô tả.

## 7. Ví dụ khác: cảnh báo chắc chắn nhưng tác động nhỏ

Xét mã Java:

~~~java
import java.util.ArrayList;
import java.util.List;

public final class LabelFormatter {
    public String firstLabel(List<String> labels) {
        return labels.isEmpty() ? "" : labels.get(0);
    }
}
~~~

Nếu `ArrayList` không được dùng, một rule kiểm tra import có thể kết luận với confidence rất cao rằng dòng `import java.util.ArrayList;` dư thừa. Xóa import này thường không làm thay đổi hành vi runtime. Đây là loại finding có thể được sửa bằng **organize imports** hoặc một quy ước formatter.

Tuy nhiên, công cụ phát hiện chính xác một vấn đề nhỏ **không biến vấn đề đó thành lỗi nghiêm trọng**. Nhóm có thể cấu hình cho formatter sửa tự động hoặc gom lại trong các đợt làm sạch, trong khi vẫn ưu tiên việc đánh giá đường truy vấn SQL có khả năng ảnh hưởng dữ liệu.

Mặt khác, một rule về tiền điều kiện hoặc truy cập collection đôi khi cảnh báo:

~~~java
import java.util.List;

public final class UnsafeLabelFormatter {
    public String firstRequiredLabel(List<String> labels) {
        return labels.get(0);
    }
}
~~~

Nếu `labels` có thể là danh sách rỗng, `get(0)` ném `IndexOutOfBoundsException`. Confidence của tool phụ thuộc khả năng chứng minh input rỗng có thể đến đây. Severity lại phụ thuộc ngữ cảnh: lỗi này chỉ gây thất bại một bước hiển thị, hay làm hỏng luồng xử lý thanh toán quan trọng?

**Hai câu hỏi phải được hỏi riêng:** *Có đường chạy thật đưa danh sách rỗng vào đây không?* và *Nếu có, hậu quả nghiệp vụ là gì?*

## 8. Kiểm thử có thể xác minh giả thuyết, không thay thế suy luận

Với phương thức `firstRequiredLabel`, nếu hợp đồng cho phép danh sách rỗng, ta có thể dùng JUnit 5 để tái hiện lỗi:

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import java.util.List;
import org.junit.jupiter.api.Test;

class LabelFormatterTest {
    @Test
    void emptyListExposesUncheckedPrecondition() {
        UnsafeLabelFormatter formatter = new UnsafeLabelFormatter();

        assertThrows(
            IndexOutOfBoundsException.class,
            () -> formatter.firstRequiredLabel(List.of())
        );
    }
}
~~~

Nhưng test này chỉ cho thấy **lời gọi với danh sách rỗng ném ngoại lệ**. Nó chưa nói hợp đồng đúng phải là gì. Có ít nhất ba lựa chọn sau khi xác nhận yêu cầu:

1. Nếu danh sách rỗng là **đầu vào không hợp lệ**, từ chối rõ ở ranh giới bằng lỗi có tên hoặc ngoại lệ phù hợp.
2. Nếu rỗng là **trường hợp bình thường**, trả một kết quả biểu thị vắng dữ liệu, chẳng hạn `Optional.empty()`.
3. Nếu rỗng được **loại trừ bởi một bất biến đã được bảo vệ**, cần bảo đảm invariant được thực thi tại mọi đường vào thay vì chỉ giả định.

Ví dụ cho lựa chọn thứ hai:

~~~java
import java.util.List;
import java.util.Objects;
import java.util.Optional;

public final class SafeLabelFormatter {
    public Optional<String> firstLabel(List<String> labels) {
        Objects.requireNonNull(labels, "labels");
        return labels.stream().findFirst();
    }
}
~~~

Với `List.of()`, kết quả là `Optional.empty()`; với `List.of("A")`, kết quả chứa `"A"`. Nếu danh sách có phần tử `null`, `Stream.findFirst()` có thể ném `NullPointerException`, nên hợp đồng cần nói rõ có cho phép `null` trong phần tử hay không.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.Test;

class SafeLabelFormatterTest {
    @Test
    void emptyListMeansNoLabel() {
        SafeLabelFormatter formatter = new SafeLabelFormatter();
        assertEquals(Optional.empty(), formatter.firstLabel(List.of()));
    }

    @Test
    void nonEmptyListReturnsFirstLabel() {
        SafeLabelFormatter formatter = new SafeLabelFormatter();
        assertEquals(
            Optional.of("A"),
            formatter.firstLabel(List.of("A", "B"))
        );
    }
}
~~~

Đây là cách biến một finding thành cơ hội **làm rõ hợp đồng**, không đơn thuần xóa cảnh báo để bảng điều khiển chuyển màu xanh.

## 9. False positive và false negative

Hai loại sai lệch quan trọng:

| Khái niệm | Nghĩa | Điều cần làm |
| --- | --- | --- |
| **False positive** | Công cụ cảnh báo một vấn đề không thực sự tồn tại theo mô hình/hợp đồng đã xác nhận | Ghi bằng chứng cụ thể, lý do và phạm vi; xem có cần cấu hình rule hoặc suppression |
| **False negative** | Một vấn đề có thật nhưng công cụ không phát hiện | Bổ sung review, test, rule hoặc kiểm soát khác; không coi công cụ im lặng là an toàn |

Một finding **đang có confidence thấp không đồng nghĩa với false positive**. Chỉ khi đã điều tra đủ để bác bỏ nhận định trong phạm vi cụ thể, ta mới có cơ sở đánh dấu false positive.

Ví dụ:

- Rule nói “có thể ghép input không tin cậy vào SQL”, nhưng code đã bind tham số trong mọi đường thực thi liên quan. Sau khi kiểm tra cụ thể, finding có thể là false positive.
- Rule không báo gì về ID báo cáo, nhưng API cho phép người dùng tải tài liệu người khác vì thiếu kiểm tra quyền. Đây có thể là **false negative của phạm vi kiểm soát tự động** hoặc đơn giản là vấn đề nằm ngoài những rule đã bật.

Tỷ lệ false positive thấp không đồng nghĩa hệ thống đã an toàn nếu công cụ bỏ sót một lớp lỗi quan trọng. Tương tự, tìm được nhiều cảnh báo không có nghĩa công cụ kém nếu nó chủ động chọn **khám phá rộng hơn** rồi cần người xác minh.

### Không đo hiệu quả chỉ bằng số lượng finding

“Số cảnh báo giảm từ 200 xuống 10” có thể là tiến bộ, nhưng cũng có thể xảy ra vì:

- Tắt một rule quan trọng.
- Thay đổi phạm vi tệp được quét.
- Chuyển finding vào baseline không được xem lại.
- Bỏ qua warning hoặc đánh dấu hàng loạt là false positive.
- Đổi phiên bản/cấu hình công cụ làm nhãn hoặc fingerprint thay đổi.

Vì vậy cần nhìn cả **tình trạng xác minh, chất lượng bằng chứng, coverage của phạm vi quét và số lỗi mới/đã sửa**.

## 10. Quy trình triage theo bằng chứng

Khi nhận một finding, có thể thực hiện lần lượt:

1. **Nhận diện chính xác:** lưu rule ID, phiên bản công cụ, commit, vị trí, severity, confidence, đường dữ liệu/stack trace nếu có và cấu hình scan.
2. **Đọc hợp đồng và đường thực thi:** input đến từ đâu, loại dữ liệu gì, điều kiện nào khiến nhánh chạy, có tầng kiểm soát nào đã tồn tại?
3. **Đánh giá tác động nếu đúng:** dữ liệu, tiền, quyền hạn, tính đúng đắn, khả dụng hay khả năng bảo trì nào bị ảnh hưởng?
4. **Xác minh giả thuyết:** code review có định hướng; dùng unit/integration test hoặc môi trường thử nghiệm an toàn khi phù hợp. Không thử cách khai thác gây hại trên dữ liệu thật.
5. **Phân loại kết luận:** `CONFIRMED`, `FALSE_POSITIVE`, `NEEDS_MORE_EVIDENCE` hoặc `ACCEPTED_RISK` (sau quyết định có thẩm quyền), không gộp tất cả thành “resolved”.
6. **Chọn hành động:** sửa mã, bổ sung validation/transaction, sửa cấu hình, thay dependency, cập nhật rule, hoặc lưu ngoại lệ có lý do.
7. **Kiểm chứng sau thay đổi:** chạy lại rule và những test có liên quan; xác nhận không có hồi quy hành vi quan trọng.
8. **Ghi rủi ro còn lại và người chịu trách nhiệm:** đặc biệt khi finding severity cao, phát hiện đã tồn tại trong bản phát hành hoặc có hành vi chưa thể chứng minh.

Một mẫu ghi nhận ngắn:

~~~text
Finding: F-017
Rule: JDBC_SQL_CONCATENATION
Commit / scan config: <mã commit và cấu hình quét đã xác minh>
Severity (tool): HIGH
Confidence (tool): MEDIUM
Observed path: request.reportId -> repository.findTitle -> SQL
Verification: CONFIRMED
Impact context: endpoint dùng bởi người dùng đã xác thực,
                truy vấn dữ liệu báo cáo, tài khoản DB có quyền đọc
Decision: dùng PreparedStatement với bind parameter
Evidence after fix: review + integration tests + scan lại
Residual risk: kiểm tra quyền theo báo cáo được theo dõi riêng
Owner: nhóm sở hữu dịch vụ
~~~

Không nên ghi “đã sửa” chỉ vì dòng cảnh báo biến mất; phải xác minh **điều kiện nguy hiểm thật sự đã được kiểm soát**.

## 11. Suppression, baseline và quality gate: tránh hai cực đoan

Nếu công cụ tạo nhiều false positive, nhóm có thể có xu hướng tắt toàn bộ rule. Ngược lại, nếu bắt mọi cảnh báo mức thấp phải sửa ngay trước khi merge, nhóm có thể ngập trong công việc ít giá trị và tìm cách lách công cụ.

Một quy trình lành mạnh thường phân biệt:

| Cơ chế | Mục đích hợp lý | Rủi ro nếu lạm dụng |
| --- | --- | --- |
| **Suppression** | Bỏ qua một finding cụ thể đã được điều tra và có bằng chứng | Che lỗi mới nếu phạm vi suppress quá rộng |
| **Baseline** | Ghi nhận nợ hiện hữu để tập trung kiểm soát finding mới | Biến cảnh báo cũ thành thứ không ai còn sở hữu |
| **Quality gate** | Chặn thay đổi không đạt tiêu chí chất lượng đã thống nhất | Chặn bởi nhiễu, khuyến khích đổi nhãn/suppress hàng loạt |
| **Rule tuning** | Điều chỉnh nguồn dữ liệu, sanitizer, phạm vi hoặc ngưỡng theo kiến trúc thật | Làm giảm khả năng phát hiện khi tinh chỉnh không có test |
| **Manual review / exception** | Xử lý trường hợp đặc biệt cần ngữ cảnh con người | Quyết định khó kiểm tra nếu không lưu lý do và người duyệt |

Một suppression tốt cần có **mã finding/rule, phạm vi chính xác, lý do có thể kiểm chứng, người phụ trách và điều kiện xem lại**. Với rủi ro cao, nên yêu cầu đánh giá trước khi suppress. Khi mã thay đổi hoặc công cụ được nâng cấp, có thể phải xem lại kết luận false positive.

### Quy tắc quality gate minh họa

Không có một ngưỡng duy nhất hợp lý cho mọi sản phẩm. Chẳng hạn, một nhóm có thể:

- Chặn merge khi có **lỗi đã xác nhận** ảnh hưởng nghiêm trọng tới dữ liệu hoặc quyền truy cập trong phần mã mới.
- Yêu cầu review kịp thời những finding **severity cao nhưng chưa đủ bằng chứng**, thay vì xếp chúng thành “không cần quan tâm”.
- Cho phép formatter tự sửa warning kiểu import/style, để các trường hợp tác động thấp không phải qua phê duyệt thủ công tốn kém.
- Theo dõi nợ tồn tại bằng baseline có chủ sở hữu và kế hoạch giảm dần, không âm thầm đổi chúng thành “không còn vấn đề”.
- Định kỳ kiểm tra tỷ lệ true positive, độ phủ rule, lỗi thực tế thoát ra production và chi phí triage.

Các lựa chọn này là **chính sách minh họa**, phải điều chỉnh theo rủi ro, quy trình và quyền quyết định của dự án. Không nên lấy ví dụ thành SLA hoặc điều kiện phát hành của một hệ thống cụ thể.

## 12. Cách đọc báo cáo đa công cụ

Một dự án có thể chạy formatter/linter, static analyzer, security scanner, dependency scanner và kiểm thử trong CI. Mỗi nguồn phản ánh một khía cạnh khác nhau:

| Loại kiểm tra | Ví dụ finding | Vấn đề cần lưu ý khi so sánh |
| --- | --- | --- |
| **Formatter / linter cú pháp** | Import không dùng, format không chuẩn | Thường xác định được trực tiếp, nhưng tác động có thể nhỏ |
| **Static analysis luồng dữ liệu** | Có thể truyền `null`, dữ liệu không tin cậy tới sink | Phụ thuộc mô hình về đường gọi, sanitizer, framework |
| **SAST bảo mật** | Truy vấn không tham số hóa, đường dẫn file không an toàn | Cần xem nguồn/sink, quyền, phạm vi khai thác |
| **SCA / dependency scanning** | Thư viện có advisory ở một phiên bản | Severity của advisory không tự chứng minh đường lỗi có thể tới được trong ứng dụng |
| **Test runner** | Assertion thất bại, timeout | Là bằng chứng về một lần chạy với input/môi trường cụ thể, không tự có confidence label theo cùng nghĩa SAST |
| **Coverage** | Nhánh chưa được thực thi trong test | Không phải severity hay confidence của một bug; chỉ phản ánh phạm vi được chạy |

Đặc biệt, **điểm severity của một CVE/advisory**, **độ tin cậy một finding SAST**, **điểm maintainability** và **mức ưu tiên của ticket** không thể tự động gộp thành cùng một thang đo mà không định nghĩa cách chuyển đổi và giới hạn.

Nếu cần báo cáo cho người quản lý, hãy phân biệt rõ **số finding mới**, **số đã xác nhận**, **số đang điều tra**, **số false positive**, **tác động đã được đánh giá** và **tiến độ khắc phục**. Đây thường là thông tin hành động được hơn việc đưa ra một con số “điểm chất lượng tổng hợp” không có định nghĩa.

## 13. Checklist khi review một cảnh báo

Trước khi bấm “Fix”, “Ignore” hoặc “Accept”, tự hỏi:

1. **Rule nào đưa ra cảnh báo?** Phiên bản, cấu hình và phạm vi quét có rõ không?
2. **Severity ở đây được công cụ định nghĩa ra sao?** Tác động mặc định của rule hay tác động đã xét trong hệ thống?
3. **Confidence dựa vào bằng chứng gì?** Công cụ có trace nguồn → sink, đường thực thi, điều kiện kích hoạt hay chỉ thấy mẫu cú pháp?
4. **Tình huống có khả thi không?** Input và trạng thái nào đưa chương trình tới vị trí cảnh báo?
5. **Tài sản gì bị ảnh hưởng?** Dữ liệu cá nhân, tiền, quyền, tính toàn vẹn, khả dụng hay chỉ style?
6. **Kiểm soát nào đã có?** Validation, bind parameter, authorization, transaction, giới hạn quyền và phạm vi triển khai?
7. **Cần loại kiểm chứng nào?** Code review, unit test, integration test, thử tải, cấu hình hoặc quan sát runtime?
8. **Kết luận đã được phân loại chưa?** Chưa đủ chứng cứ khác với false positive; “accepted risk” khác với “fixed”.
9. **Nếu suppress, bằng chứng và người chịu trách nhiệm ở đâu?** Scope và điều kiện xem lại có đủ hẹp không?
10. **Sau khi sửa, hành vi nghiệp vụ có giữ nguyên đúng hợp đồng không?** Cảnh báo biến mất có thể chỉ vì đường kiểm tra không còn nhìn thấy mã.

Khi nhiều người cùng review, một bản mô tả finding ngắn với **giả thuyết → bằng chứng → kết luận → hành động** giúp trao đổi hiệu quả hơn các tranh luận chỉ dựa trên nhãn đỏ/vàng/xanh.

## 14. Bài tập tình huống

Bạn nhận một báo cáo tự động gồm bốn finding:

| ID | Mô tả | Severity của tool | Confidence của tool |
| --- | --- | --- | --- |
| A | Luồng dữ liệu có thể đưa tham số request vào câu SQL ghép chuỗi | High | Low |
| B | Một import trong lớp Java không được dùng | Low | High |
| C | Có thể gọi `Optional.get()` khi giá trị rỗng ở một tác vụ thanh toán | Medium | High |
| D | Một dependency có advisory nghiêm trọng, chưa rõ đường mã bị ảnh hưởng có chạy trong ứng dụng không | High | Medium |

**Câu hỏi A.** Có thể chỉ dựa vào confidence để ưu tiên B trước A không? Vì sao?

**Câu hỏi B.** Với finding C, cần xác minh những gì trước khi quyết định mức tác động thực tế và cách sửa?

**Câu hỏi C.** Với D, cần phân biệt thông tin gì giữa “dependency có cảnh báo” và “ứng dụng hiện tại chịu rủi ro khai thác”?

**Câu hỏi D.** Nếu sau review phát hiện A là false positive vì mọi giá trị đi vào SQL đều được bind an toàn theo một ranh giới mà công cụ chưa hiểu, có nên tắt luôn rule SQL injection cho toàn dự án không?

### Gợi ý đáp án

**A.** Không. B có bằng chứng rất chắc về một vấn đề nhẹ, trong khi A đặt ra giả thuyết có hậu quả nghiêm trọng. Cần **xác minh A sớm theo rủi ro**, đồng thời có thể giao B cho formatter. Không khẳng định A là bug thật trước khi điều tra.

**B.** Kiểm tra liệu `Optional` có thể rỗng trên đường đi thật; nếu có, khi ném `NoSuchElementException` thì tác vụ thanh toán đang ở trạng thái nào, có ghi tiền hoặc giao dịch dở dang không, retry có gây xử lý trùng không. Tùy hợp đồng, có thể từ chối đầu vào sớm, xử lý `Optional.empty()` rõ ràng hoặc bảo vệ invariant cần thiết. Test nên bao gồm cả trường hợp rỗng và các tác dụng phụ nghiệp vụ.

**C.** Cần đối chiếu phiên bản dependency đang dùng, advisory mô tả điều kiện ảnh hưởng, API/cấu hình có được sử dụng không, đường mã có thể tới được không, các lớp kiểm soát hiện có và phiên bản sửa lỗi. Việc dependency có advisory là **đầu mối điều tra quan trọng**, nhưng tác động tới ứng dụng cần được xác minh theo bối cảnh.

**D.** Không nên. Nên ghi rõ bằng chứng cho finding cụ thể và cân nhắc **suppression hẹp** hoặc cập nhật mô hình sanitizer/taint của công cụ. Tắt cả rule có thể gây false negative khi một đường SQL khác thực sự nguy hiểm xuất hiện.

## Ghi nhớ

**Severity** nói về **mức tác động nếu vấn đề là thật**; **confidence** nói về **mức chắc chắn của nhận định mà công cụ đưa ra**; còn **priority** là **quyết định điều tra và khắc phục trong bối cảnh dự án**. Ba khái niệm có liên quan nhưng không được đánh đồng.

Một finding nghiêm trọng nhưng confidence thấp vẫn cần được xem xét theo rủi ro; một finding chắc chắn nhưng nhẹ có thể xử lý theo đợt. Muốn biến cảnh báo tự động thành bằng chứng chất lượng, hãy **xem đường chạy và hợp đồng, xác minh bằng test/review phù hợp, ghi rõ trạng thái và lý do**, rồi sửa **nguyên nhân thật** thay vì chỉ tìm cách làm bộ quét hiện màu xanh.
