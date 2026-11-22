# Xác định người sử dụng và mục tiêu của phần mã đang xét

Khi đánh giá chất lượng mã, câu hỏi đầu tiên thường không phải “Đoạn mã này có dùng mẫu thiết kế tốt không?” mà là **“Ai cần phần mã này hoạt động, họ dùng nó để làm gì và điều gì được xem là thành công?”**. Cùng một cách triển khai có thể hợp lý trong công cụ nội bộ chạy mỗi tháng một lần nhưng gây nhiều khó khăn nếu được đặt vào đường xử lý hàng nghìn yêu cầu mỗi giây.

Trong **CODE_QUALITY_FUNDAMENTALS**, chúng ta tìm hiểu những thuộc tính khiến mã nguồn đáng tin cậy, dễ hiểu và dễ thay đổi. Để đánh giá các thuộc tính ấy, trước hết phải xác định **bối cảnh sử dụng**: người nhận giá trị từ phần mềm, hệ thống gọi tới mã, người vận hành và người phải sửa đổi mã về sau. Bài học này tập trung vào việc tìm đúng những đối tượng đó và chuyển mục tiêu của họ thành tiêu chí có thể kiểm chứng.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Xác định ranh giới một phần mã và các nhóm người hoặc hệ thống phụ thuộc vào nó.
2. Phân biệt người dùng cuối, bên gọi API, người vận hành và người bảo trì; nhận ra nhu cầu của từng nhóm.
3. Làm rõ mục tiêu sử dụng, điều kiện vận hành, hậu quả khi lỗi và giới hạn bắt buộc.
4. Biến những phát biểu chung như “nhanh”, “dễ dùng”, “dễ bảo trì” thành tiêu chí chấp nhận phù hợp bối cảnh.
5. Giải thích vì sao bối cảnh khác nhau dẫn tới các lựa chọn thiết kế và đánh đổi chất lượng khác nhau.

## 1. “Người sử dụng mã” không chỉ là người nhấn nút trên giao diện

Một người mua hàng không đọc mã Java, nhưng kết quả mua hàng của họ phụ thuộc vào mã. Một dịch vụ khác có thể gọi trực tiếp một API mà không hề có giao diện. Một lập trình viên sẽ phải đọc và thay đổi mã sau sáu tháng. Khi phần mềm lỗi lúc nửa đêm, người trực vận hành cần biết nguyên nhân và cách phục hồi.

Vì vậy, hãy xét nhiều nhóm “người sử dụng” theo quan hệ của họ với **phần mã đang được đánh giá**:

| Nhóm | Họ tương tác với phần mã như thế nào? | Điều thường quan trọng với họ |
| --- | --- | --- |
| **Người dùng cuối** | Sử dụng chức năng qua ứng dụng, trang web hoặc thiết bị. | Kết quả đúng, thao tác dễ hiểu, phản hồi phù hợp, thông báo lỗi hữu ích. |
| **Người dùng nghiệp vụ** | Thực hiện công việc như nhập liệu, đối soát, phê duyệt hoặc xem báo cáo. | Dữ liệu đáng tin, phát hiện sai sót, giải quyết được khối lượng công việc thực tế. |
| **Thành phần gọi mã** (*caller/consumer*) | Gọi phương thức, thư viện, API hoặc nhận sự kiện. | Hợp đồng đầu vào/đầu ra ổn định, lỗi có thể xử lý, tương thích khi nâng cấp. |
| **Lập trình viên bảo trì** | Đọc, kiểm thử, sửa lỗi, thêm tính năng và tái cấu trúc. | Tên gọi rõ nghĩa, trách nhiệm tách bạch, kiểm thử tin cậy, phụ thuộc dễ kiểm soát. |
| **Người vận hành / hỗ trợ** | Theo dõi, chẩn đoán và khắc phục sự cố. | Log, chỉ số, truy vết, khả năng phục hồi và quy trình xử lý lỗi. |
| **Người phụ trách an toàn dữ liệu** | Đánh giá quyền truy cập và việc xử lý thông tin. | Quyền tối thiểu, không lộ dữ liệu nhạy cảm, có khả năng kiểm tra khi cần. |

Không phải bài toán nào cũng có đủ tất cả các vai trò. Ta chỉ cần nhận diện những vai trò **thực sự có nhu cầu hoặc chịu tác động**. Đồng thời, một người có thể mang nhiều vai trò: lập trình viên vừa là người gọi một thư viện, vừa là người bảo trì nó.

### Người dùng trực tiếp và người chịu tác động gián tiếp

Xét phương thức `calculateShippingFee()` trong một hệ thống thương mại điện tử:

- **Đối tượng gọi trực tiếp:** dịch vụ tạo đơn hàng.
- **Người hưởng kết quả:** khách hàng cần thấy phí vận chuyển chính xác trước khi xác nhận.
- **Người chịu tác động nghiệp vụ:** bộ phận tài chính cần đối soát đúng số phí.
- **Người phụ thuộc về lâu dài:** lập trình viên phải bổ sung quy tắc phí cho vùng mới.

Nếu chỉ nhìn vào chữ ký của phương thức, ta dễ bỏ sót các yêu cầu như giải thích phí cho khách hàng hoặc lưu vết quy tắc đã áp dụng để đối soát. Nhưng cũng không nên tự động biến mọi mong muốn của mọi nhóm thành chức năng: các mục tiêu cần được xác nhận và ưu tiên với người chịu trách nhiệm sản phẩm hoặc hệ thống.

## 2. Xác định chính xác **phần mã đang xét**

“Ai sử dụng?” chỉ có ý nghĩa khi biết mình đang đánh giá **ranh giới nào**. Ranh giới có thể là một hàm, một lớp, một thư viện, một API hoặc cả luồng nghiệp vụ.

Ví dụ, với việc nhập số lượng sản phẩm:

~~~text
Người dùng thao tác biểu mẫu       Nhân viên nhập dữ liệu hàng loạt
              │                                  │
              ▼                                  ▼
    API nhận biểu mẫu                    Chức năng nhập tệp
              │                                  │
              └─────────────┬────────────────────┘
                            ▼
                Quy tắc kiểm tra số lượng
                            │
                            ▼
                Dịch vụ xử lý nghiệp vụ
~~~

Nếu đang đánh giá **hàm kiểm tra số lượng**, đối tượng gọi là hai luồng phía trên; mục tiêu chung là quyết định số lượng có hợp lệ hay không. Nếu đang đánh giá **toàn bộ quy trình nhập tệp**, người dùng chính là nhân viên nghiệp vụ và mục tiêu quan trọng hơn có thể là phát hiện *tất cả* các dòng lỗi trong một lần kiểm tra.

Một cách làm thực tế:

1. Ghi tên phần mã và phạm vi của nó: hàm, API, lớp hay tác vụ nền.
2. Tìm các điểm gọi và luồng dữ liệu đi vào/đi ra; phân biệt bên gọi trực tiếp với người dùng cuối.
3. Xác định ai sở hữu quyết định nghiệp vụ và ai chịu hậu quả nếu kết quả sai.
4. Kiểm tra nơi dữ liệu được lưu, hiển thị hoặc chuyển tiếp để thấy tác động ngoài phạm vi hàm.

**Không nên suy ra toàn bộ mục tiêu chỉ từ tên hàm.** Một phương thức tên `process()` hoặc `validate()` không cho biết rõ ai sử dụng, mức độ nghiêm trọng của lỗi hay cách phản hồi mong muốn.

## 3. Từ đối tượng sử dụng đến **công việc cần hoàn thành**

Biết rằng “người dùng là nhân viên kho” vẫn chưa đủ. Cần biết nhân viên kho đang làm nhiệm vụ nào, ở hoàn cảnh nào và điều gì khiến họ hoàn thành công việc.

Một mô tả hữu ích có cấu trúc:

> **Khi** [bối cảnh hoặc tình huống], **[vai trò]** cần **[thao tác và kết quả]** để **[đạt mục đích nghiệp vụ]**.

Ví dụ:

> Khi tải lên bảng kiểm kê gồm nhiều dòng, nhân viên kho cần biết **những dòng nào có số lượng không hợp lệ** để sửa chúng trong một lượt, thay vì phải tải lại tệp nhiều lần mới phát hiện hết lỗi.

Từ đó, ta có thể đặt những câu hỏi cụ thể:

| Cần tìm hiểu | Câu hỏi hữu ích | Vì sao ảnh hưởng đến chất lượng |
| --- | --- | --- |
| **Nhiệm vụ** | Người dùng đang cố hoàn thành bước nào trong quy trình? | Giúp chọn hành vi thực sự cần thiết, tránh xây tính năng không phục vụ kết quả. |
| **Tần suất và quy mô** | Bao nhiêu lần mỗi ngày? Một lần có bao nhiêu bản ghi? | Quyết định ưu tiên về hiệu năng, chi phí tài nguyên và trải nghiệm. |
| **Bối cảnh thao tác** | Có tương tác trực tiếp, chạy nền hay xử lý theo lô? | Ảnh hưởng đến phản hồi, cách báo lỗi và thời gian chấp nhận được. |
| **Hậu quả khi sai** | Sai một bản ghi làm chậm việc, mất tiền hay lộ dữ liệu? | Xác định mức độ kiểm soát, xác nhận và bằng chứng cần có. |
| **Tính thay đổi** | Quy tắc có thường đổi? Ai thay đổi? | Ảnh hưởng đến tổ chức mã, khả năng mở rộng và kiểm thử hồi quy. |
| **Phụ thuộc** | API/bản ghi có được hệ thống khác sử dụng không? | Ảnh hưởng đến khả năng tương thích và thay đổi hợp đồng. |
| **Điều kiện vận hành** | Nếu mạng chậm, hệ thống khác lỗi hoặc thao tác bị lặp thì sao? | Làm rõ nhu cầu xử lý lỗi, retry, idempotency và quan sát. |

### Đừng nhầm giải pháp được đề xuất với mục tiêu

Yêu cầu “hãy dùng cache”, “thêm 5 lớp”, “chạy đa luồng” là **đề xuất cách làm**. Mục tiêu có thể là “giảm thời gian mở trang”, “dễ thay đổi quy tắc” hoặc “xử lý tệp nhập liệu đúng hạn”. Cần nắm mục tiêu trước rồi mới cân nhắc kỹ thuật.

Ví dụ, nếu vấn đề là API chậm do truy vấn dữ liệu không cần thiết, thêm cache có thể làm tăng độ phức tạp, dữ liệu cũ và chi phí vô hiệu hóa cache. Xác định công việc và tiêu chí thành công giúp chọn giải pháp giải quyết đúng vấn đề.

## 4. Biến mục tiêu thành tiêu chí có thể kiểm chứng

Các phát biểu “hệ thống cần nhanh”, “code cần dễ hiểu”, “nhập liệu cần thuận tiện” có thể là định hướng ban đầu, nhưng chưa đủ để kiểm tra kết quả.

Một tiêu chí hữu ích cần nêu rõ **đối tượng + tình huống + hành vi hoặc kết quả + điều kiện kiểm chứng**.

| Phát biểu chung | Ví dụ tiêu chí rõ hơn |
| --- | --- |
| “Khách hàng nhập số lượng dễ dàng.” | Khi nhập `0` hoặc ký tự không phải số, biểu mẫu hiển thị lỗi tại trường số lượng và không tạo đơn hàng. |
| “Tải tệp nhập liệu thuận tiện.” | Khi tệp có nhiều dòng không hợp lệ, kết quả kiểm tra liệt kê vị trí và lý do của từng dòng lỗi để người dùng sửa một lượt. |
| “Hệ thống nhanh.” | Trong điều kiện tải đã thống nhất, 95% yêu cầu tra cứu hoàn tất trong ngưỡng thời gian **do nhóm xác nhận**. |
| “API dễ tích hợp.” | Bên gọi có tài liệu rõ về dữ liệu hợp lệ, mã lỗi, định dạng phản hồi và quy tắc tương thích phiên bản. |
| “Dễ sửa đổi.” | Quy tắc kiểm tra số lượng được tập trung tại một vị trí; thay đổi quy tắc có bộ kiểm thử hồi quy phát hiện tác động. |
| “Dễ vận hành.” | Khi tác vụ nhập liệu thất bại, người trực có thể xác định tệp/tác vụ bị lỗi qua mã tương quan mà không cần ghi dữ liệu nhạy cảm vào log. |

Các tiêu chí trong bảng là **ví dụ minh họa**, không phải cam kết cố định cho mọi sản phẩm. Ngưỡng thời gian, số dòng, cách xử lý bản ghi hợp lệ khi tệp có lỗi và mức độ chi tiết của log phải được xác nhận theo bối cảnh cụ thể.

### Mục tiêu, tiêu chí và ràng buộc khác nhau ra sao?

- **Mục tiêu:** điều muốn đạt, chẳng hạn giúp nhân viên kho sửa dữ liệu nhanh hơn.
- **Tiêu chí chấp nhận:** dấu hiệu quan sát được để biết mục tiêu đã đạt, chẳng hạn báo đủ vị trí dòng lỗi.
- **Ràng buộc:** giới hạn cần tuân thủ, chẳng hạn người dùng chỉ xem được dữ liệu thuộc phạm vi được cấp quyền.
- **Đánh đổi:** lựa chọn ưu tiên giữa các cách đáp ứng mục tiêu trong giới hạn đó, chẳng hạn thu thập mọi lỗi trước khi phản hồi sẽ tốn thêm thời gian xử lý.

Một hệ thống không được bỏ qua tính đúng đắn, bảo mật hoặc các ràng buộc bắt buộc chỉ để cải thiện con số hiệu năng.

## 5. Ví dụ Java: cùng quy tắc, hai người dùng, hai mục tiêu

Giả sử hệ thống bán hàng có quy tắc: **số lượng đặt hàng phải là số nguyên dương**. Hai luồng cần dùng quy tắc này:

**Luồng A – khách hàng điền biểu mẫu:** người dùng cần biết ngay trường số lượng sai ở đâu để sửa, không bị chuyển sang bước tiếp theo với dữ liệu lỗi.

**Luồng B – nhân viên nhập tệp hàng loạt:** người dùng cần kiểm tra nhiều dòng, lấy danh sách dòng sai và lý do, sau đó sửa tệp một lượt.

Quy tắc lõi giống nhau; **cách trình bày và tổng hợp lỗi** khác nhau. Nếu cố ép cả hai vào một hàm trả về thông điệp giao diện, mã kiểm tra sẽ phụ thuộc vào chi tiết nhập liệu. Nếu viết hai bộ quy tắc riêng biệt, chúng có thể dần cho kết quả không nhất quán.

### 5.1. Tách quy tắc nghiệp vụ dùng chung

~~~java
public final class QuantityRules {
    private QuantityRules() {
    }

    /**
     * Trả về số lượng hợp lệ; ném ngoại lệ nếu dữ liệu sai.
     * Hợp đồng: giá trị đầu vào phải là chuỗi số nguyên dương.
     */
    public static int parsePositiveQuantity(String raw) {
        if (raw == null || raw.trim().isEmpty()) {
            throw new IllegalArgumentException("Quantity is required");
        }

        final int quantity;
        try {
            quantity = Integer.parseInt(raw.trim());
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException(
                    "Quantity must be an integer", ex);
        }

        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "Quantity must be positive");
        }
        return quantity;
    }
}
~~~

Phương thức này chỉ có **một trách nhiệm**: chuyển giá trị đầu vào thành số lượng hợp lệ theo hợp đồng. Nó không biết dữ liệu đến từ biểu mẫu hay tệp CSV, không tự tạo đơn hàng và không tự ghi log. Điều đó giúp quy tắc dễ kiểm thử và tái sử dụng.

Với biểu mẫu, phía gọi có thể kiểm tra từng giá trị và trả lỗi ngay ở trường tương ứng:

~~~java
try {
    int quantity = QuantityRules.parsePositiveQuantity(formValue);
    // Chỉ đi tiếp đến bước tạo đơn hàng khi đầu vào hợp lệ.
} catch (IllegalArgumentException ex) {
    // Chuyển loại lỗi thành thông báo phù hợp với giao diện.
    // Không đưa đơn hàng có số lượng sai sang bước tiếp theo.
}
~~~

Với dữ liệu hàng loạt, phía gọi có thể tích lũy lỗi thay vì dừng ở dòng sai đầu tiên:

~~~java
import java.util.ArrayList;
import java.util.List;

public final class ImportQuantityCheck {
    private ImportQuantityCheck() {
    }

    public static List<String> findErrors(List<String> quantityCells) {
        List<String> errors = new ArrayList<>();
        for (int index = 0; index < quantityCells.size(); index++) {
            try {
                QuantityRules.parsePositiveQuantity(quantityCells.get(index));
            } catch (IllegalArgumentException ex) {
                errors.add("Row " + (index + 1) + ": " + ex.getMessage());
            }
        }
        return errors;
    }
}
~~~

Đoạn mã nhập liệu trên chỉ minh họa bước **kiểm tra cột số lượng**, chưa phải bộ phân tích CSV đầy đủ hoặc thao tác ghi dữ liệu. Hành vi lưu tệp khi một phần dòng bị lỗi — từ chối toàn bộ hay chấp nhận những dòng hợp lệ — cần được xác định thành hợp đồng riêng trước khi triển khai. Trong sản phẩm thực, mã lỗi có cấu trúc sẽ thuận tiện hơn cho dịch ngôn ngữ và hiển thị từng dòng.

### 5.2. Vì sao bối cảnh thay đổi quyết định thiết kế?

| Tiêu chí | Biểu mẫu tương tác | Kiểm tra tệp hàng loạt |
| --- | --- | --- |
| **Người sử dụng chính** | Khách hàng / nhân viên tạo đơn. | Nhân viên vận hành dữ liệu. |
| **Mục tiêu trước mắt** | Sửa lỗi nhập ngay để tiếp tục thao tác. | Xác định nhiều lỗi cùng lúc để sửa tệp. |
| **Chiến lược báo lỗi** | Hiện tại trường bị lỗi; có thể dừng luồng gửi. | Ghi nhận vị trí của từng dòng có lỗi; tiếp tục kiểm tra. |
| **Đơn vị công việc** | Một trường hoặc một đơn hàng. | Một danh sách bản ghi. |
| **Thước đo quan sát** | Thông báo rõ và không gửi dữ liệu không hợp lệ. | Báo cáo lỗi đầy đủ và có thể đối chiếu với nguồn. |
| **Quy tắc lõi** | Số lượng là số nguyên dương. | Cũng là số nguyên dương. |

Nhận diện người dùng và mục tiêu giúp **giữ một hợp đồng nghiệp vụ chung** nhưng tổ chức phần xử lý quanh nó phù hợp cho từng luồng. Đây là một quyết định thiết kế có căn cứ, thay vì lựa chọn cấu trúc theo thói quen.

### 5.3. Kiểm thử bám vào mục tiêu sử dụng

Một số kiểm thử JUnit 5 phù hợp với hợp đồng minh họa:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.Arrays;
import java.util.List;
import org.junit.jupiter.api.Test;

class QuantityRulesTest {
    @Test
    void acceptsValidQuantity() {
        assertEquals(3, QuantityRules.parsePositiveQuantity("3"));
    }

    @Test
    void rejectsZeroAndNonNumericText() {
        assertThrows(IllegalArgumentException.class,
                () -> QuantityRules.parsePositiveQuantity("0"));
        assertThrows(IllegalArgumentException.class,
                () -> QuantityRules.parsePositiveQuantity("abc"));
    }

    @Test
    void batchValidationReportsEachInvalidRow() {
        List<String> errors = ImportQuantityCheck.findErrors(
                Arrays.asList("2", "0", "xyz", "5"));

        assertEquals(2, errors.size());
        assertTrue(errors.get(0).startsWith("Row 2:"));
        assertTrue(errors.get(1).startsWith("Row 3:"));
    }
}
~~~

Bài kiểm thử của hàm lõi chứng minh quy tắc hợp lệ. Bài kiểm thử của bộ kiểm tra tệp chứng minh **mục tiêu riêng của người dùng nhập liệu**: nhận đủ lỗi và vị trí tương ứng. Một bộ kiểm thử chỉ xác nhận `parsePositiveQuantity("3")` trả về `3` sẽ không chứng minh được trải nghiệm nhập liệu đã đạt yêu cầu.

## 6. Từ mục tiêu đến ưu tiên và đánh đổi chất lượng

Các chiều chất lượng mã nguồn thường liên quan và đôi lúc tạo ra lựa chọn khó: tính đúng đắn, mức độ dễ hiểu, khả năng thay đổi, hiệu năng, tính tin cậy, khả năng quan sát và chi phí thực hiện. **Ưu tiên hợp lý phụ thuộc vào ai sử dụng, trong hoàn cảnh nào, và hậu quả của việc không đáp ứng yêu cầu.**

| Bối cảnh | Điều cần ưu tiên hoặc làm rõ | Đánh đổi cần cân nhắc |
| --- | --- | --- |
| Công cụ nội bộ chạy hiếm khi, dữ liệu nhỏ | Tính đúng đắn, dễ hiểu, chi phí bảo trì thấp. | Xây kiến trúc phân tán hoặc cache phức tạp có thể không đem lại lợi ích tương xứng. |
| API công khai có nhiều bên tích hợp | Hợp đồng rõ, tương thích, phân loại lỗi và quản lý phiên bản. | Thay đổi cấu trúc dữ liệu thuận tiện cho nhóm phát triển có thể phá vỡ ứng dụng phía gọi. |
| Tác vụ đối soát tiền | Tính chính xác, truy vết, khôi phục và phát hiện sai lệch. | Ghi dấu vết, xác nhận và kiểm tra bổ sung có thể tăng thời gian xử lý. |
| Màn hình tương tác thường xuyên | Trải nghiệm phản hồi, tính nhất quán với dữ liệu, xử lý lỗi rõ ràng. | Dùng cache giúp nhanh hơn nhưng phải quyết định mức độ dữ liệu cũ chấp nhận được. |
| Bộ quy tắc thay đổi thường xuyên | Tính dễ sửa đổi, phân tách trách nhiệm và kiểm thử hồi quy. | Tạo điểm mở rộng phù hợp có chi phí ban đầu; trừu tượng hóa quá sớm có thể làm mã khó đọc. |

Đánh đổi không có nghĩa muốn bỏ qua điều kiện bắt buộc. Chẳng hạn, nếu pháp lý và chính sách yêu cầu kiểm soát truy cập dữ liệu khách hàng, ta không thể chọn lược bỏ bước phân quyền chỉ vì muốn giảm độ trễ. Bài toán là tìm thiết kế đáp ứng các **ràng buộc** trong khi tối ưu mục tiêu có thể thương lượng.

### Một khung ra quyết định ngắn

Khi cân nhắc hai cách triển khai, hãy ghi rõ:

1. **Đối tượng và công việc:** ai được lợi hoặc bị ảnh hưởng?
2. **Điều không được vi phạm:** tính đúng đắn, an toàn dữ liệu, quy tắc nghiệp vụ, hợp đồng API.
3. **Điều đang tối ưu:** thời gian phản hồi, thông lượng, công sức sửa đổi, khả năng chẩn đoán hay chi phí.
4. **Bằng chứng:** đo đạc, dữ liệu lỗi, thử nghiệm, ví dụ chấp nhận hoặc kinh nghiệm vận hành có liên quan.
5. **Giá phải trả:** độ phức tạp, tài nguyên, rủi ro dữ liệu cũ, phụ thuộc mới và công sức bảo trì.

Ví dụ, nếu đề xuất cache cho trang tra cứu, cần hỏi người dùng có chấp nhận thấy số liệu chậm cập nhật không và chậm bao lâu; từ đó mới định nghĩa cơ chế làm mới và kiểm thử đúng đắn của dữ liệu. Không có thông tin này, tranh luận “cache có tốt không” thiếu căn cứ.

## 7. Cách thu thập và xác nhận thông tin

Không nên suy luận toàn bộ bối cảnh từ code hiện tại, vì code hiện tại cũng có thể phản ánh những giả định sai hoặc yêu cầu cũ. Kết hợp nhiều nguồn sẽ giúp mô tả chính xác hơn:

- **Người sở hữu nghiệp vụ và người sử dụng thực tế:** phỏng vấn ngắn hoặc quan sát luồng làm việc để biết mục đích, khó khăn, ngoại lệ.
- **Yêu cầu, tiêu chí chấp nhận và hợp đồng API:** làm rõ kết quả được hứa hẹn, phạm vi hợp lệ và khả năng tương thích.
- **Caller và luồng dữ liệu:** xác định thành phần phụ thuộc và hậu quả khi thay đổi hành vi.
- **Báo cáo lỗi, log và số liệu vận hành:** tìm các tình huống thất bại, quy mô dữ liệu và hành vi thực tế.
- **Lịch sử sửa đổi và kiểm thử hiện có:** hiểu những quy tắc từng dễ bị phá vỡ, đồng thời kiểm tra xem chúng còn đúng với nghiệp vụ hiện tại không.

Khi nguồn thông tin mâu thuẫn, hãy **ghi nhận bất đồng và xác nhận người có quyền quyết định**, thay vì đoán rằng triển khai đang chạy là chuẩn cuối cùng. Nếu chưa đo được độ trễ thực tế, ghi rõ “chưa đo” và xây cách đo trước khi quyết định tối ưu hiệu năng.

## 8. Mẫu ghi bối cảnh ngắn cho một phần mã

Bạn có thể dùng mẫu sau trong mô tả thiết kế, issue hoặc pull request:

~~~text
Phần mã / ranh giới:
Người sử dụng chính:
Các bên gọi hoặc bị tác động:
Tình huống sử dụng thực tế:
Kết quả nghiệp vụ cần đạt:
Đầu vào, đầu ra và hành vi lỗi:
Điều kiện vận hành (tải, tần suất, dữ liệu, phụ thuộc):
Ràng buộc bắt buộc:
Tiêu chí chấp nhận / cách đo:
Quyết định thiết kế và đánh đổi:
Nguồn xác nhận / điều còn chưa rõ:
~~~

Ví dụ đã điền cho phần kiểm tra số lượng hàng loạt:

| Trường | Nội dung |
| --- | --- |
| Phần mã | `ImportQuantityCheck.findErrors()`. |
| Người sử dụng chính | Nhân viên nhập tệp dữ liệu. |
| Tình huống | Kiểm tra cột số lượng trên nhiều dòng trước khi nhập. |
| Mục tiêu | Sửa được các dòng sai trong một lượt. |
| Hành vi yêu cầu | Liệt kê mọi dòng có số lượng thiếu, không phải số nguyên hoặc không dương. |
| Tiêu chí chấp nhận | Với các dòng `2, 0, xyz, 5`, báo lỗi tại dòng 2 và 3. |
| Ràng buộc | Không ghi những dòng chưa được kiểm tra vào hệ thống. |
| Đánh đổi | Kiểm tra toàn bộ danh sách tốn thêm thời gian so với dừng ở lỗi đầu tiên. |
| Điều cần xác nhận | Giới hạn kích thước tệp và chính sách nhập toàn bộ hay từng phần. |

Mẫu này đủ ngắn để dùng trong review nhưng buộc người viết liên hệ **quyết định kỹ thuật với giá trị và ràng buộc thực tế**.

## 9. Những sai lầm thường gặp

**Chỉ hỏi ai gọi phương thức.** Caller rất quan trọng, nhưng một thay đổi có thể ảnh hưởng đến khách hàng, người vận hành và bên tích hợp. Cần nhìn xuyên qua lời gọi để thấy kết quả cuối cùng.

**Cho rằng mọi nhóm đều có chung một mục tiêu.** Người nhập biểu mẫu muốn được báo lỗi tức thì; nhân viên nhập tệp muốn tổng hợp lỗi. Ép hai luồng dùng cùng chiến lược báo lỗi dễ tạo trải nghiệm không phù hợp.

**Bắt đầu từ công nghệ rồi mới tìm vấn đề.** Chọn cache, đa luồng, generic framework hay microservice trước khi hiểu quy mô và hậu quả lỗi sẽ làm đánh đổi khó được chứng minh.

**Dùng tính từ không thể đo.** “Nhanh”, “an toàn” và “dễ bảo trì” cần chuyển thành các điều kiện cụ thể và cách kiểm chứng ở đúng ranh giới.

**Chỉ tối ưu cho người dùng hiện tại.** API có bên tích hợp hoặc phần mã được sửa thường xuyên còn có người dùng tương lai: lập trình viên sẽ bảo trì và người sẽ triển khai phiên bản tiếp theo.

**Bỏ qua trường hợp lỗi.** Mục tiêu sử dụng bao gồm cả khả năng người dùng hiểu, sửa hoặc phục hồi sau lỗi; thông báo thành công chưa nói lên chất lượng toàn bộ luồng.

**Coi mọi mong muốn là ràng buộc tuyệt đối.** Hãy tách điều bắt buộc khỏi điều có thể thương lượng để các đánh đổi trở nên minh bạch.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Một thư viện Java được dùng bởi nhiều dịch vụ nội bộ. Nhóm phát triển muốn đổi kiểu dữ liệu trả về để code ngắn hơn. Cần xác định ai và điều gì trước khi sửa?

*Gợi ý:* Liệt kê các dịch vụ gọi trực tiếp, cách chúng sử dụng kết quả, hợp đồng và yêu cầu tương thích, người bảo trì thư viện, kế hoạch chuyển đổi. Việc code ngắn hơn phải được cân nhắc với chi phí phá vỡ các bên dùng thư viện.

**Câu 2.** Với tệp nhập 10.000 dòng, bạn sẽ dừng ở lỗi đầu tiên hay kiểm tra toàn bộ?

*Gợi ý:* Chưa thể chọn chỉ dựa vào số dòng. Cần biết người dùng muốn sửa dữ liệu theo cách nào, giới hạn thời gian/tài nguyên, chính sách ghi dữ liệu, số lượng lỗi dự kiến và cách trình bày báo cáo. Mỗi lựa chọn phục vụ một mục tiêu khác nhau.

**Câu 3.** Một yêu cầu ghi “API phải rất nhanh”. Bạn sẽ làm rõ thành tiêu chí kiểm chứng bằng cách nào?

*Gợi ý:* Hỏi loại yêu cầu, người dùng, mức tải, kích thước dữ liệu, phân vị độ trễ cần đạt, điều kiện đo, tác động khi vượt ngưỡng và những ràng buộc dữ liệu không được vi phạm.

## Ghi nhớ

- **Bắt đầu từ ranh giới phần mã** để biết người sử dụng trực tiếp, gián tiếp và người chịu tác động khi thay đổi.
- **Vai trò chưa phải mục tiêu**: cần mô tả công việc, tình huống, kết quả mong muốn và hậu quả khi không đạt.
- **Tiêu chí có thể kiểm chứng** biến những kỳ vọng chung thành hợp đồng và phép đo rõ ràng.
- **Bối cảnh quyết định ưu tiên chất lượng và đánh đổi**, nhưng những ràng buộc bắt buộc vẫn phải được bảo đảm.
- **Đánh giá lại khi bối cảnh thay đổi**: số lượng người dùng, quy mô dữ liệu, yêu cầu mới hoặc bên gọi API mới có thể làm quyết định cũ không còn phù hợp.

Trước khi nhận xét một đoạn mã là “tốt” hay “kém”, hãy trả lời được: **Ai phụ thuộc vào đoạn mã này, họ đang cố hoàn thành việc gì, điều gì xảy ra nếu nó sai và bằng chứng nào cho thấy cách triển khai đang phục vụ đúng mục tiêu đó?**
