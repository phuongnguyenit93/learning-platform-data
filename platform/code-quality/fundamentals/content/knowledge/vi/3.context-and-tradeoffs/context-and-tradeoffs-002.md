# Mức độ quan trọng và hậu quả khi mã sai

Một đoạn mã được xem là có chất lượng khi nó đáp ứng đúng yêu cầu **trong bối cảnh sử dụng thực tế** và có thể được thay đổi an toàn. Vì vậy, khi đánh giá một lỗi, câu hỏi không chỉ là “mã có sai không?” mà còn là **“nếu mã sai, ai bị ảnh hưởng và thiệt hại đến đâu?”**

Cùng một lỗi làm tròn số có thể khiến một biểu đồ nội bộ hiển thị chưa đẹp, nhưng cũng có thể khiến hệ thống tính sai số tiền hoàn trả cho hàng nghìn khách hàng. Mức độ quan trọng của mã phụ thuộc vào hậu quả khi nó hoạt động sai.

Bài học này giúp bạn xác định độ nghiêm trọng của một lỗi, nhận diện những vùng mã cần bảo vệ kỹ hơn và phân bổ công sức kiểm thử, review, giám sát phù hợp.

## 1. Phân biệt mức độ quan trọng, hậu quả và rủi ro

Ba khái niệm liên quan nhưng không giống nhau:

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| **Mức độ quan trọng của chức năng (criticality)** | Chức năng này quan trọng thế nào đối với hoạt động của hệ thống? | Xác thực người dùng quyết định ai được sử dụng hệ thống. |
| **Mức độ nghiêm trọng của lỗi (severity/impact)** | Nếu lỗi xảy ra, hậu quả lớn đến đâu? | Đọc được dữ liệu tài khoản của người khác là hậu quả nghiêm trọng. |
| **Rủi ro (risk)** | Khả năng sự cố xảy ra và hậu quả của nó kết hợp như thế nào? | Một quy tắc phân quyền phức tạp, thường xuyên thay đổi và không có kiểm thử mang rủi ro đáng chú ý. |

Có thể dùng mô hình tư duy đơn giản:

> **Rủi ro ≈ khả năng xảy ra sự cố × mức độ hậu quả khi sự cố xảy ra.**

Đây là cách **định hướng quyết định**, không phải công thức đo chính xác mọi loại thiệt hại. Rò rỉ dữ liệu cá nhân, ảnh hưởng an toàn con người hay vi phạm nghĩa vụ pháp lý không thể luôn quy đổi thành một điểm số hoặc chi phí tiền tệ. Một sự cố rất hiếm nhưng không thể khắc phục vẫn có thể cần kiểm soát nghiêm ngặt.

**Lưu ý:** Lỗi khó sửa chưa chắc nghiêm trọng; lỗi chỉ có một dòng cũng có thể gây hậu quả rất lớn. Mức độ ưu tiên xử lý còn phụ thuộc vào phạm vi bị ảnh hưởng, khả năng phát hiện, cách khôi phục và các cam kết của sản phẩm.

## 2. Hậu quả khi mã sai xuất hiện dưới những hình thức nào?

Khi đánh giá mã, hãy nghĩ đến ít nhất sáu chiều hậu quả:

| Chiều hậu quả | Ví dụ lỗi | Điều cần xem xét |
| --- | --- | --- |
| **Đúng đắn nghiệp vụ** | Đơn hàng được áp sai mức giảm giá; tính thiếu thuế. | Kết quả có làm thay đổi tiền, quyền lợi hoặc quyết định của người dùng không? |
| **Dữ liệu và tính toàn vẹn** | Cập nhật sai trạng thái đơn hàng; ghi đè dữ liệu. | Có thể khôi phục chính xác trạng thái trước lỗi không? |
| **Bảo mật và riêng tư** | Trả dữ liệu của người dùng A cho người dùng B. | Ai xem hoặc sửa được thông tin trái phép? Có thể thu hồi dữ liệu đã lộ không? |
| **Tính sẵn sàng và độ tin cậy** | Một lỗi khiến luồng thanh toán ngừng hoạt động. | Bao nhiêu người dùng bị gián đoạn, trong bao lâu? |
| **An toàn và tuân thủ** | Bỏ qua giới hạn an toàn hoặc lưu dữ liệu vượt phạm vi cho phép. | Có gây nguy hiểm, vi phạm quy định hoặc nghĩa vụ hợp đồng không? |
| **Uy tín và chi phí vận hành** | Lặp giao dịch, gửi thông báo sai, phải đối soát thủ công. | Cần bao nhiêu công sức để phát hiện, sửa và giải thích sự cố? |

Hậu quả còn phụ thuộc vào **phạm vi ảnh hưởng (blast radius)**. Một lỗi chỉ ảnh hưởng bản nháp cá nhân khác đáng kể với lỗi trong thư viện dùng chung của hàng trăm dịch vụ. **Thời gian tồn tại** cũng quan trọng: sai lệch được phát hiện sau vài giây dễ kiểm soát hơn sai lệch âm thầm tích lũy nhiều tháng.

## 3. Cùng một lỗi, hậu quả khác nhau theo bối cảnh

Giả sử một hàm làm tròn số tiền bị sai một đơn vị ở một số trường hợp biên.

- **Bối cảnh A — bản xem trước nội bộ:** Con số minh họa trên giao diện thử nghiệm lệch một đơn vị, không được dùng để ra quyết định. Hậu quả trực tiếp có thể nhỏ.
- **Bối cảnh B — hóa đơn chính thức:** Cùng kết quả đó được dùng để lập hóa đơn hoặc tính hoàn tiền cho nhiều đơn hàng. Sai lệch có thể nhân lên, gây khiếu nại và buộc đối soát.
- **Bối cảnh C — giới hạn giao dịch:** Kết quả được dùng để kiểm tra giao dịch có vượt hạn mức hay không. Lỗi tại ranh giới có thể cho phép một giao dịch vốn phải bị từ chối.

Điểm khác biệt không nằm ở số dòng mã hoặc vẻ phức tạp của hàm. Nó nằm ở **ai sử dụng kết quả, kết quả quyết định điều gì, số lần lặp lại và khả năng sửa hậu quả**.

Ngay cả lỗi “chỉ ở giao diện” cũng không mặc nhiên nhẹ: nếu giao diện công khai đưa ra giá sai hoặc thông tin gây hiểu nhầm khiến khách hàng quyết định mua hàng, tác động có thể lớn. Luôn xác định luồng dữ liệu và quyết định thực tế trước khi xếp mức độ nghiêm trọng.

## 4. Ví dụ Java: lỗi phân quyền có hậu quả lớn dù mã rất ngắn

Xét một dịch vụ xem sao kê. Một cách viết sai là chỉ kiểm tra tài liệu có tồn tại rồi trả nội dung, bỏ qua người đang yêu cầu:

~~~java
// SAI: biết mã tài liệu là có thể đọc nội dung.
String readStatement(Statement statement) {
    return statement.content();
}
~~~

Vấn đề không phải ở cú pháp Java; vấn đề ở **điều kiện nghiệp vụ bắt buộc**: chỉ người có quyền mới được xem sao kê. Nếu mã định danh tài liệu bị đoán hoặc lộ qua nơi khác, dữ liệu có thể bị truy cập trái phép.

Một phiên bản minh họa kiểm tra quyền sở hữu trước khi trả dữ liệu:

~~~java
public final class StatementService {
    public record Statement(String ownerId, String content) {}

    public String readStatement(String authenticatedUserId, Statement statement) {
        if (authenticatedUserId == null
                || authenticatedUserId.isBlank()
                || statement == null
                || statement.ownerId() == null
                || !statement.ownerId().equals(authenticatedUserId)) {
            throw new SecurityException("Access denied");
        }
        return statement.content();
    }
}
~~~

Trong ví dụ này:

1. Mã người dùng phải đến từ **ngữ cảnh xác thực đáng tin cậy ở phía máy chủ**, không lấy trực tiếp từ tham số mà khách hàng có thể tự đổi.
2. Thiếu thông tin hoặc kiểm tra thất bại thì **từ chối truy cập**; không tự động cho phép.
3. Điều kiện bảo vệ dữ liệu phải được thực thi tại phía máy chủ, kể cả khi giao diện đã ẩn nút hoặc đường dẫn.

Các trường hợp kiểm thử tối thiểu bằng JUnit 5 có thể viết như sau (đặt trong phương thức test):

~~~java
var service = new StatementService();
var statement = new StatementService.Statement("user-A", "Sensitive data");

assertEquals("Sensitive data",
        service.readStatement("user-A", statement));

assertThrows(SecurityException.class,
        () -> service.readStatement("user-B", statement));

assertThrows(SecurityException.class,
        () -> service.readStatement(null, statement));
~~~

Ví dụ chủ ý đơn giản để làm rõ **bất biến bảo mật**: người không có quyền không được đọc tài liệu. Hệ thống thật có thể cần thêm quyền được ủy quyền, phạm vi tổ chức (tenant), truy xuất tài liệu từ kho dữ liệu, audit log, xử lý mã HTTP và các kiểm thử bảo mật khác.

**Bài học về đánh đổi:** Với một lỗi căn chỉnh giao diện ít ảnh hưởng, có thể ưu tiên sửa theo lịch thông thường. Với lỗi có thể làm lộ sao kê, cần ưu tiên chặn đường truy cập trái phép, kiểm tra mức độ ảnh hưởng, sửa và bổ sung bằng chứng kiểm thử ngay theo quy trình xử lý sự cố của hệ thống.

## 5. Đánh giá độ nghiêm trọng một cách có hệ thống

Không có thang phân loại áp dụng giống nhau cho mọi tổ chức. Bảng dưới đây là **khung tham khảo**, cần điều chỉnh theo nghiệp vụ, thỏa thuận dịch vụ và yêu cầu pháp lý.

| Mức hậu quả | Dấu hiệu tham khảo | Hướng xử lý thường phù hợp |
| --- | --- | --- |
| **Rất cao / nghiêm trọng** | Gây nguy hiểm; truy cập dữ liệu trái phép trên diện rộng; giao dịch tiền không kiểm soát; mất dữ liệu quan trọng không phục hồi được. | Cô lập hoặc giảm tác động ngay, xử lý theo quy trình sự cố, xác minh nguyên nhân và phòng tái diễn. |
| **Cao** | Chức năng cốt lõi bị gián đoạn; sai dữ liệu của nhiều khách hàng; thiệt hại đáng kể nhưng có khả năng khắc phục. | Ưu tiên sửa nhanh, kiểm chứng kỹ và theo dõi sau sửa. |
| **Trung bình** | Một luồng phụ bị lỗi; kết quả sai trong phạm vi hạn chế, có cách xử lý thay thế. | Lập kế hoạch sửa với kiểm thử phù hợp phạm vi ảnh hưởng. |
| **Thấp** | Lỗi trình bày nhỏ, ít ảnh hưởng đến quyết định và thao tác, dễ sửa hoặc đảo ngược. | Sửa theo mức ưu tiên sản phẩm và tránh tạo rủi ro hồi quy không cần thiết. |

Trước khi phân loại, nên hỏi:

- **Ai bị ảnh hưởng?** Một người thử nghiệm, một nhóm khách hàng hay toàn hệ thống?
- **Điều gì sai?** Chỉ hiển thị, hay dữ liệu được lưu, quyền truy cập và giao dịch cũng bị thay đổi?
- **Sai bao lâu và lan rộng thế nào?** Lỗi xảy ra ở một yêu cầu hay lặp lại trong tác vụ nền, hàng đợi và nhiều dịch vụ?
- **Có phát hiện sớm không?** Có log, chỉ số, cảnh báo, đối soát hoặc kiểm thử chỉ ra sai lệch?
- **Có khôi phục được không?** Hoàn tác có chính xác và an toàn không? Dữ liệu đã bị tiết lộ có thể thu hồi không?
- **Có cam kết đặc biệt không?** An toàn, pháp lý, hợp đồng, SLA, hoặc nhu cầu của nhóm người dùng dễ bị tổn thương?

Cần tách **độ nghiêm trọng của hậu quả** khỏi **độ ưu tiên thực hiện công việc**. Độ ưu tiên còn tính đến khả năng sự cố tái diễn, mức phơi nhiễm, biện pháp tạm thời, nguồn lực và rủi ro do chính bản sửa gây ra. Dù vậy, một nguy cơ không thể đảo ngược vẫn cần được đánh giá nghiêm túc ngay cả khi ít xảy ra.

## 6. Phân bổ công sức kiểm soát theo rủi ro

Chất lượng không có nghĩa mọi dòng mã đều nhận cùng lượng kiểm thử và review. Hãy chọn biện pháp dựa trên hậu quả có thể xảy ra:

| Vùng mã | Bằng chứng chất lượng nên ưu tiên |
| --- | --- |
| **Tiền, quyền truy cập, dữ liệu quan trọng** | Kiểm thử bất biến nghiệp vụ; ca lỗi và biên; review độc lập; kiểm tra quyền ở máy chủ; tính nguyên tử và khả năng chống thực hiện lặp khi có giao dịch. |
| **Luồng cốt lõi có tải lớn** | Kiểm thử tích hợp, xử lý timeout/retry, khả năng phục hồi, giám sát và cảnh báo, phương án triển khai hoặc quay lui. |
| **Báo cáo và dữ liệu hỗ trợ quyết định** | Đối chiếu với nguồn đáng tin cậy, xác minh quy tắc tính toán, truy vết nguồn dữ liệu, kiểm thử dữ liệu bất thường. |
| **Trình bày ít rủi ro** | Kiểm tra hành vi chính, kiểm thử mức hợp lý, review gọn và phản hồi từ người dùng. |

Ví dụ: trong xử lý thanh toán, chỉ kiểm thử kết quả đúng của một lần gọi là chưa đủ. Cần xem xét **gọi lại cùng yêu cầu**, lỗi mạng giữa chừng, nhiều yêu cầu đồng thời, hoàn tiền vượt số đã thanh toán và khả năng đối soát. Các biện pháp như khóa giao dịch, ràng buộc dữ liệu và khóa idempotency phải được thiết kế ở đúng ranh giới hệ thống; một câu lệnh kiểm tra trong bộ nhớ không đủ bảo đảm khi có nhiều tiến trình.

Ngược lại, thêm hàng chục lớp trừu tượng hoặc quy trình duyệt nặng nề cho một nhãn hiển thị có thể làm mã khó thay đổi mà ít giảm rủi ro thực tế. **Mức bảo vệ phải tương xứng với hậu quả**, đồng thời vẫn giữ mức chất lượng cơ bản như mã dễ đọc và kiểm tra được.

## 7. Quy trình ngắn trước khi sửa hoặc phát hành mã

1. **Xác định chức năng và người sử dụng.** Nêu đầu vào, đầu ra, trạng thái bị thay đổi và các hệ thống phụ thuộc.
2. **Viết ra bất biến quan trọng.** Ví dụ: “mỗi giao dịch được ghi nhận đúng một lần”, “người dùng không đọc được dữ liệu của người khác”, “tổng hoàn tiền không vượt số tiền hợp lệ”.
3. **Đặt kịch bản thất bại.** Điều gì xảy ra nếu đầu vào trống, giá trị ở biên, kết nối đứt, yêu cầu lặp, có truy cập đồng thời hoặc một phụ thuộc trả sai?
4. **Ước lượng hậu quả và khả năng khôi phục.** Xem phạm vi, thời gian, dữ liệu, tiền, quyền truy cập, pháp lý và khả năng phát hiện.
5. **Chọn kiểm soát phù hợp.** Bổ sung validation, kiểm thử, review, phân quyền, ràng buộc lưu trữ, log/metrics/alert hoặc kế hoạch rollback tùy rủi ro.
6. **Xác minh sau thay đổi.** Kiểm tra cả trường hợp thành công lẫn thất bại; theo dõi tín hiệu thực tế sau khi đưa vào sử dụng.

Khi nhiều tiêu chí xung đột, chẳng hạn tốc độ giao hàng và độ an toàn của dữ liệu, hãy ghi rõ **giả định, hậu quả chấp nhận được, điều kiện phải từ chối xử lý và lý do chọn giải pháp**. Quyết định có cơ sở giúp đội ngũ đánh giá lại khi quy mô hoặc bối cảnh thay đổi.

## 8. Tình huống tự luyện

**Tình huống 1.** Một phép tính phần trăm sai khiến dashboard thử nghiệm hiện 21% thay vì 20%. Dashboard không dùng để quyết định hay xuất báo cáo. Bạn có lập tức dừng toàn bộ hệ thống không?

**Gợi ý:** Chưa có cơ sở để dừng hệ thống. Cần xác nhận phạm vi sử dụng thực tế, sửa lỗi và kiểm thử; mức ưu tiên có thể thấp nếu hậu quả thực sự nhỏ.

**Tình huống 2.** Cùng hàm tính phần trăm được tái sử dụng để quyết định mức phí trên hóa đơn của mọi khách hàng. Đánh giá có thay đổi không?

**Gợi ý:** Có. Cần kiểm tra phạm vi ảnh hưởng, đối soát hóa đơn, tính đúng đắn của dữ liệu đã ghi và cách khắc phục. Việc hàm chỉ gồm vài dòng không làm hậu quả nhỏ đi.

**Tình huống 3.** Một API trả kết quả chính xác khi người dùng có quyền, nhưng cũng trả đúng dữ liệu đó cho người dùng không có quyền. Bộ kiểm thử “đường đi thành công” đều vượt qua. Điều gì còn thiếu?

**Gợi ý:** Thiếu kiểm thử các trường hợp **phải từ chối**, đánh giá ranh giới tin cậy và bất biến phân quyền. Đúng kết quả cho người dùng hợp lệ chưa đủ để kết luận chức năng an toàn.

---

**Ghi nhớ:** Muốn đánh giá chất lượng mã và quyết định đánh đổi hợp lý, hãy nhìn từ **hậu quả khi mã sai**: mức độ ảnh hưởng, phạm vi lan truyền, khả năng phát hiện và phục hồi. Chính bối cảnh sử dụng quyết định vùng mã nào cần bằng chứng chất lượng chặt chẽ hơn.
