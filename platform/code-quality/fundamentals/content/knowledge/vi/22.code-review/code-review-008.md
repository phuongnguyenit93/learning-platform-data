# Viết nhận xét có vị trí, lý do và tác động cụ thể

Một bình luận code review như “Đoạn này chưa ổn”, “Nên làm cho sạch hơn” hoặc “Có bug” có thể khiến tác giả phải đoán người review muốn nói đến đâu, vì sao lại có vấn đề và cần sửa thế nào. Thậm chí hai người có thể đồng ý rằng mã cần cải thiện nhưng vẫn mất nhiều vòng trao đổi chỉ vì nhận xét không chỉ ra **hành vi bị ảnh hưởng**.

Nhận xét hữu ích không nhất thiết dài. Nó nên giúp tác giả trả lời nhanh: **Vấn đề nằm ở đâu? Nhận định dựa trên căn cứ nào? Hậu quả đối với hệ thống là gì? Cần thay đổi hoặc kiểm chứng điều gì?** Khi reviewer chưa chắc chắn, nhận xét cũng phải cho thấy đâu là quan sát, đâu là giả thiết và điều gì cần xác minh.

Bài học thuộc chương **Rà soát mã** của **CODE_QUALITY_FUNDAMENTALS**. Theo mục tiêu module — hiểu những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi** hay không — chúng ta sẽ luyện cách viết nhận xét có vị trí, lý do và tác động cụ thể, ưu tiên theo rủi ro, diễn đạt với thái độ hợp tác, và biến phát hiện trong review thành hành động có thể kiểm tra.

## 1. Nhận xét code review là một đơn vị thông tin kỹ thuật

Một nhận xét tốt không chỉ thể hiện sở thích của người đọc. Nó chuyển một quan sát thành **bằng chứng phục vụ quyết định thay đổi mã**.

Ví dụ:

> “Ở điều kiện miễn phí vận chuyển trong `ShippingPolicy.feeVnd`, toán tử `>` loại đơn hàng đúng 500.000 VND khỏi nhánh miễn phí, trong khi quy tắc là *từ 500.000 VND trở lên*. Khách ở đúng ngưỡng sẽ bị thu thêm 30.000 VND. Đề xuất dùng `>=` và thêm test cho đúng ngưỡng để ngăn hồi quy. **Blocking — lỗi tính phí**.”

Nhận xét này có bốn phần kiểm tra được:

1. **Vị trí:** điều kiện trong phương thức đang được review.
2. **Lý do:** `>` không bao gồm giá trị bằng ngưỡng, trái đặc tả.
3. **Tác động:** tính sai phí đối với một nhóm đơn hàng xác định.
4. **Hành động:** đổi toán tử, bổ sung regression test và xác minh kết quả.

Nó cũng nói rõ **mức ưu tiên**. Người viết mã có thể xử lý mà không phải hỏi lại “vấn đề cụ thể là gì?”.

### 1.1. Một công thức thực dụng

~~~text
[Tại vị trí nào / khi điều kiện nào]
[Tôi quan sát thấy gì, dựa trên hợp đồng hoặc bằng chứng nào]
[Điều đó gây tác động gì]
[Đề nghị thay đổi hoặc cách kiểm chứng]
[Mức ưu tiên, khi cần]
~~~

Đây là khung suy nghĩ, **không phải khuôn bắt buộc mọi comment phải đủ năm dòng**. Với một lỗi rõ ràng, hai câu có thể đủ; với vấn đề xuyên nhiều module, một nhận xét ở cấp PR và liên kết tới bằng chứng có thể cần thiết hơn.

### 1.2. “Cụ thể” khác “dài”

| Nhận xét | Khả năng hành động |
| --- | --- |
| “Sai rồi.” | Không rõ sai gì và ở đâu |
| “Cần thêm test.” | Không rõ điều kiện nào chưa được bảo vệ |
| “Nên tách hàm.” | Chưa biết trách nhiệm nào đang bị trộn |
| “Ở nhánh `if` kiểm tra tổng tiền, chưa có ca đúng ngưỡng 500.000 VND; nếu dùng `>` thì đơn đúng ngưỡng bị tính phí. Thêm test cho trường hợp này giúp bắt lỗi so sánh.” | Rõ tình huống, hậu quả và phép kiểm chứng |
| “Hàm đang mở transaction trước khi gọi HTTP; nếu API timeout, kết nối DB có thể bị giữ lâu. Có thể chuyển cuộc gọi ra ngoài transaction hoặc giải thích vì sao cần tính nguyên tử ở đây?” | Rõ đường rủi ro nhưng có ngôn ngữ thận trọng khi chưa biết hợp đồng |

Mục tiêu không phải số từ, mà là **giảm sự mơ hồ và công trao đổi lại**.

## 2. Chọn đúng vị trí: dòng, đoạn, phương thức hay toàn PR?

Một nhận xét nên gắn vào **đơn vị nhỏ nhất đủ chứa nguyên nhân**, đồng thời cho người viết thấy bối cảnh cần thiết.

| Vị trí | Khi nên dùng | Ví dụ |
| --- | --- | --- |
| **Một dòng trong diff** | Lỗi gắn trực tiếp với điều kiện, lời gọi hoặc hằng số | Toán tử `>` sai ở ngưỡng |
| **Một đoạn nhiều dòng** | Tương tác giữa vài câu lệnh mới gây vấn đề | Ghi trạng thái trước khi xác thực quyền |
| **Phương thức/class** | Trách nhiệm hoặc hợp đồng của thành phần chưa rõ | Method xử lý vừa tính giá vừa gửi email |
| **File/module** | Phụ thuộc, tổ chức lớp hoặc cấu hình ảnh hưởng nhiều chỗ | Domain import trực tiếp lớp JDBC |
| **Nhận xét cấp PR** | Vấn đề xuyên nhiều file hoặc cần nói về phương án thiết kế chung | Migration xóa field trước khi consumer cũ dừng dùng |
| **Issue/ADR riêng** | Vấn đề lớn ngoài phạm vi thay đổi hiện tại | Kế hoạch tách toàn bộ một module theo quý |

### 2.1. Vị trí trong diff không nhất thiết là “số dòng cố định”

Trong công cụ review, gắn comment trực tiếp vào dòng hoặc đoạn thay đổi thường tốt hơn ghi “ở đâu đó trong class”. Nhưng **số dòng có thể dịch chuyển** sau khi tác giả push commit mới.

Với ví dụ minh họa, có thể ghi:

~~~text
File: src/main/java/example/checkout/ShippingPolicy.java
Vị trí: điều kiện kiểm tra ngưỡng trong feeVnd(...)
Điều kiện: subtotalVnd > FREE_THRESHOLD_VND
~~~

Đường dẫn trên chỉ minh họa, không phải vị trí đã được xác minh trong repository của người học. Khi review thật, hãy dùng **đường dẫn và vị trí thực** từ diff; nếu comment đã lỗi thời vì mã thay đổi, hãy xem phiên bản mới trước khi giữ yêu cầu.

### 2.2. Không buộc một lỗi xuyên nhiều file vào một dòng ngẫu nhiên

Ví dụ, việc **producer phát event phiên bản mới trước khi consumer được nâng cấp** không thể được giải thích hoàn chỉnh bằng một dòng thay đổi serializer. Nên tạo nhận xét cấp PR nói rõ luồng triển khai, hợp đồng dữ liệu và điều kiện tương thích, rồi có thể đặt comment cục bộ vào nơi tạo event để dẫn chiếu.

### 2.3. Không biến một nguyên nhân thành mười bình luận trùng nhau

Nếu năm dòng đều dùng cùng một validation helper sai, bình luận tại **định nghĩa helper** và nhắc một hoặc hai đường tác động đại diện thường hiệu quả hơn gắn cùng thông điệp lên cả năm nơi gọi.

Nếu các nơi gọi có **hậu quả khác nhau**, có thể ghi riêng phần tác động quan trọng. Reviewer nên giúp tác giả thấy **nguyên nhân chung**, không chỉ liệt kê triệu chứng.

## 3. Tách quan sát, giả thiết và kết luận

Độ tin cậy của nhận xét tăng khi người review phân biệt những gì đã thấy trong mã với những gì mới suy đoán.

| Thành phần | Cách viết | Ví dụ |
| --- | --- | --- |
| **Quan sát** | “Ở dòng này...” hoặc “Trong diff, ...” | `ownerId` đang lấy từ request body |
| **Hợp đồng / căn cứ** | “Theo yêu cầu...” hoặc “Trong test...” | Người dùng chỉ được xem đơn của chính mình |
| **Suy luận** | “Vì vậy...” hoặc “Nếu...” | Caller có thể thay `ownerId` để tìm đơn của người khác |
| **Mức chắc chắn** | “Đã xác nhận” hay “Cần kiểm chứng” | Chưa thấy bước xác thực `ownerId` ở server |
| **Yêu cầu** | “Có thể sửa bằng...” hoặc “Nhờ bổ sung test...” | Lấy ID từ authentication context và test hai tài khoản |

Câu khẳng định tuyệt đối cần bằng chứng tương xứng. Nếu reviewer chưa biết có middleware kiểm tra quyền, hãy hỏi:

> “Mình thấy `ownerId` được lấy từ body ở đây. Có kiểm soát nào phía trước ràng buộc nó với người dùng đã xác thực không? Nếu không, caller có thể chọn ID khác để truy cập đơn ngoài quyền. Nhờ bổ sung kiểm tra tại server hoặc chỉ rõ test/hợp đồng đang bảo vệ trường hợp này.”

Cách viết này **không giả vờ chắc chắn** rằng lỗi phân quyền đã tồn tại. Nhưng nó vẫn chỉ ra đường rủi ro và cách đóng câu hỏi.

### 3.1. Tránh “có thể” quá mơ hồ

Câu “Có thể có vấn đề bảo mật” không hữu ích vì không cho biết điều kiện và tài sản. Thay bằng:

> “Nếu `accountId` lấy trực tiếp từ query parameter và repository không lọc theo danh tính đăng nhập, tài khoản A có thể yêu cầu bản ghi của B. Nhờ xác nhận nơi kiểm tra quyền và thêm ca thử bị từ chối.”

Sự thận trọng tốt là **xác định điều kiện làm kết luận đúng**, không phải loại bỏ mọi thông tin cụ thể.

## 4. Lý do và tác động không phải là một

Người review đôi khi viết “không nên dùng `HashMap` vì không an toàn”, nhưng không cho biết “không an toàn” theo nghĩa nào: dữ liệu sai, race condition, truy cập không được phép hay không giữ thứ tự?

- **Lý do (why):** cơ chế kỹ thuật hoặc hợp đồng bị vi phạm.
- **Tác động (impact):** hậu quả có thể quan sát trong hệ thống, sản phẩm hoặc quá trình bảo trì.

Ví dụ:

**Lý do:** “Biến `currentRequestId` là field của singleton và bị nhiều request ghi lại.”

**Tác động:** “Request A có thể ghi log hoặc gắn kết quả theo ID của request B, gây nhầm truy vết và rò ngữ cảnh.”

**Hành động:** “Giữ ID trong biến cục bộ hoặc đối tượng context riêng cho mỗi request; bổ sung test đồng thời nếu handler thực sự được chia sẻ.”

Một bình luận chỉ nói “vi phạm single responsibility” cũng chưa đủ. Cần nối quy tắc thiết kế với chi phí thực:

> “Phương thức đang tính chiết khấu và ghi tệp. Khi đổi chính sách giá, unit test phải dựng hệ thống tệp, khiến ca kiểm tra ngưỡng khó chạy độc lập. Tách tính toán thành hàm nhận `Order` và trả `PriceQuote` sẽ cho phép test chính sách mà không cần I/O.”

Điểm quan trọng là người đọc hiểu **vì sao thay đổi được đề xuất**, không phải chỉ nhận tên một nguyên tắc.

## 5. Viết tác động cụ thể: ai bị ảnh hưởng và trong điều kiện nào?

Một nhận xét có thể nêu một trong các loại tác động sau:

| Loại | Câu hỏi cần giải thích | Ví dụ |
| --- | --- | --- |
| **Tính đúng đắn** | Đầu vào nào trả kết quả sai? | Đơn đúng ngưỡng bị tính thêm 30.000 VND |
| **Dữ liệu** | Bản ghi nào bị mất, trùng hoặc sai? | Retry sau timeout có thể tạo hai đơn cùng request ID |
| **Bảo mật** | Quyền hoặc tài sản nào bị ảnh hưởng? | Khách A xem hóa đơn của khách B |
| **Độ tin cậy** | Hệ thống thất bại thế nào? | File ghi dở để lại báo cáo không đầy đủ |
| **Hiệu năng** | Workload nào gây chậm, tài nguyên nào tăng? | Một query riêng mỗi sản phẩm khiến số lượt gọi DB tăng theo `n` |
| **Khả năng kiểm thử** | Vì sao không kiểm tra độc lập được? | Tính phí phụ thuộc HTTP client ở mỗi lần gọi |
| **Khả năng thay đổi** | Một yêu cầu nhỏ phải sửa những nơi nào? | Đổi quy tắc giảm giá cần cập nhật ba controller |
| **Tương thích** | Người tiêu thụ nào không còn hiểu hợp đồng? | Consumer cũ không biết trường event mới bắt buộc |

Đừng biến tác động **giả định** thành một sự cố đã xảy ra. “Có thể đọc dữ liệu của người khác nếu...” khác với “Đã có rò rỉ dữ liệu”. Khi thiếu số liệu, dùng mô tả **đường gây hậu quả**, không tự tạo tỷ lệ lỗi hoặc số người dùng bị ảnh hưởng.

## 6. Mức ưu tiên: cần sửa trước merge hay chỉ là đề xuất?

Một PR có thể có lỗi làm sai tiền, vấn đề đặt tên và cơ hội refactor tương lai. Nếu tất cả comment đều viết “please fix”, tác giả khó biết cái gì thật sự chặn merge.

Có thể thống nhất nhãn trong nhóm, ví dụ:

| Nhãn minh họa | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Blocking / Must fix** | Vi phạm hợp đồng, rủi ro nghiêm trọng hoặc không đủ bằng chứng cho thay đổi hiện tại | Thiếu kiểm tra quyền, sai phép tính, nguy cơ mất dữ liệu |
| **Should fix** | Vấn đề đáng giải quyết trong PR, có tác động rõ nhưng không nhất thiết khẩn cấp nhất | Lỗi xử lý một nhánh thất bại hoặc test biên thiếu |
| **Suggestion / Non-blocking** | Phương án cải thiện hợp lý, có thể thảo luận và trì hoãn | Tách một helper để giảm trùng lặp |
| **Nit** | Chi tiết nhỏ, ưu tiên thấp và không ảnh hưởng hợp đồng đáng kể | Cách đặt tên phụ không đúng quy ước đã được formatter bao phủ |
| **Question** | Cần làm rõ giả thiết để đánh giá đúng | Middleware đã kiểm tra quyền ở đâu? |

Đây là **thang nhãn minh họa**, không phải tiêu chuẩn bắt buộc của mọi tổ chức. Một số công cụ dùng P0/P1/P2, `blocking`, `non-blocking` hoặc định nghĩa khác. Nên bám vào chính sách review đang có và **nói rõ kỳ vọng hành động**.

### 6.1. Ưu tiên dựa trên tác động, không dựa trên giọng văn

Một nhận xét viết rất lịch sự vẫn có thể là **blocking** nếu phát hiện nguy cơ lộ dữ liệu. Ngược lại, một góp ý về tên biến không nên được làm thành mệnh lệnh tuyệt đối chỉ vì reviewer có sở thích mạnh.

Một comment có thể viết:

> “[Blocking — phân quyền] Có thể giúp mình xác nhận `tenantId` được lấy từ ngữ cảnh xác thực? Hiện repository nhận `tenantId` từ request body, nên nếu không có kiểm tra ở tầng trước, người dùng có thể đổi ID để truy cập tenant khác. Nếu đã có middleware, nhờ dẫn đường kiểm chứng; nếu chưa, cần bổ sung kiểm tra và test từ chối.”

Thân thiện và kiên quyết **không mâu thuẫn**.

### 6.2. Không yêu cầu sửa mọi nợ kỹ thuật trong PR

Nếu reviewer tìm một kiến trúc còn rối nhưng PR chỉ sửa một bug nhỏ, có thể tách vấn đề kiến trúc thành issue được mô tả, trừ khi **phần đang thay đổi làm rủi ro lớn hơn hoặc không thể kiểm chứng an toàn**.

Việc thêm yêu cầu ngoài phạm vi liên tục có thể khiến PR dài, khó review và khó rollback. Nhận xét tốt còn biết **giới hạn phạm vi đề nghị**.

## 7. Ví dụ Java: biến “có bug” thành nhận xét có thể kiểm chứng

Giả sử đặc tả là: **đơn từ 500.000 VND trở lên được miễn phí vận chuyển; dưới mức đó phí 30.000 VND**. Đầu vào không âm; ví dụ dùng số nguyên VND.

### 7.1. Đoạn mã cần review

~~~java
final class ShippingPolicy {
    private static final long FREE_THRESHOLD_VND = 500_000L;
    private static final long STANDARD_FEE_VND = 30_000L;

    static long feeVnd(long subtotalVnd) {
        if (subtotalVnd < 0L) {
            throw new IllegalArgumentException(
                    "subtotalVnd must be non-negative");
        }

        if (subtotalVnd > FREE_THRESHOLD_VND) {
            return 0L;
        }
        return STANDARD_FEE_VND;
    }
}
~~~

Phương thức có xử lý đầu vào âm, hai nhánh tính phí và tên trường có đơn vị rõ. Tuy nhiên dấu `>` không bao gồm đúng ngưỡng.

### 7.2. Nhận xét yếu

~~~text
Bug ở đây. Sửa lại điều kiện.
~~~

Tác giả biết có người phản đối nhưng chưa biết vì sao. Nếu người viết hiểu yêu cầu là “trên 500.000” thay vì “từ 500.000”, tranh luận tiếp là điều dễ xảy ra.

### 7.3. Nhận xét tốt hơn

~~~text
[Blocking — tính phí]
Vị trí: ShippingPolicy.feeVnd, điều kiện subtotalVnd > FREE_THRESHOLD_VND.

Theo quy tắc "từ 500.000 VND trở lên miễn phí", dấu > bỏ qua
trường hợp subtotalVnd = 500_000. Khi đó hàm trả 30.000 VND,
nên đơn đúng ngưỡng bị thu phí sai.

Đề xuất dùng >= và bổ sung regression test với 499_999,
500_000 và 500_001 VND để bảo vệ cả ba phía của ngưỡng.
~~~

Vị trí và dữ liệu đủ cụ thể để tác giả tái hiện. Reviewer không cần nói “code này rất tệ” hoặc viện dẫn một quy tắc mơ hồ.

### 7.4. Test hồi quy theo hợp đồng

Ví dụ JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class ShippingPolicyTest {
    @Test
    void chargesFeeImmediatelyBelowThreshold() {
        assertEquals(
                30_000L,
                ShippingPolicy.feeVnd(499_999L));
    }

    @Test
    void waivesFeeAtExactThreshold() {
        assertEquals(
                0L,
                ShippingPolicy.feeVnd(500_000L));
    }

    @Test
    void waivesFeeImmediatelyAboveThreshold() {
        assertEquals(
                0L,
                ShippingPolicy.feeVnd(500_001L));
    }

    @Test
    void rejectsNegativeSubtotal() {
        assertThrows(
                IllegalArgumentException.class,
                () -> ShippingPolicy.feeVnd(-1L));
    }
}
~~~

Test `waivesFeeAtExactThreshold` **sẽ thất bại** với mã có lỗi. Thay `>` thành `>=` làm test này qua, trong khi các ca còn lại giúp bảo vệ hai phía ngưỡng và đầu vào âm.

Không cần thêm công cụ mock hoặc database để kiểm tra phép tính thuần. Đây là ví dụ về comment yêu cầu **đúng cấp kiểm thử**, thay vì nói chung “tăng coverage”. Việc kiểm thử hành vi tại ngưỡng có giá trị hơn chỉ chạy qua cả hai nhánh.

### 7.5. Cần ghi rõ điều gì đã được xác minh

Nếu reviewer chỉ đọc diff mà chưa chạy test, không nên viết “tôi đã xác nhận build lỗi”. Có thể nói:

> “Theo điều kiện hiện tại, với đầu vào 500.000 VND hàm sẽ trả 30.000 VND; test ở ngưỡng trong ví dụ trên sẽ thất bại. Mình chưa chạy suite trên nhánh này.”

Nhận xét vẫn có lập luận từ mã mà không mạo nhận bằng chứng chạy thực tế. Sau khi test được thực thi, có thể bổ sung log hoặc kết quả nếu quy trình cần.

## 8. Ví dụ về nhận xét bảo mật: phân biệt truy vấn an toàn và quyền truy cập

Một reviewer thấy đoạn Java sử dụng `PreparedStatement`:

~~~java
String sql =
        "SELECT id, owner_id, total_vnd FROM orders WHERE id = ?";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, orderId);
    // Thực thi truy vấn, ánh xạ kết quả và trả về caller.
}
~~~

**Parameter binding** là một biện pháp phù hợp để tránh chèn dữ liệu thành cú pháp SQL ở vị trí giá trị. Nhưng không thể suy ra rằng truy vấn đã đảm bảo **quyền xem đơn hàng**.

### 8.1. Nhận xét thiếu thông tin

~~~text
Thiếu bảo mật ở query này.
~~~

### 8.2. Nhận xét có đường tác động và câu hỏi rõ

~~~text
[Blocking nếu endpoint cho phép khách tự truy cập theo orderId]
Vị trí: truy vấn lấy order theo id trong OrderReader.

Truy vấn hiện lọc theo id, chưa ràng buộc người có quyền xem đơn.
Nếu orderId đến từ URL của người dùng và không có bước kiểm tra
quyền khác, người dùng A có thể thay id để xem đơn của B.

Nhờ chỉ ra nơi xác thực owner/tenant ở server. Nếu chưa có,
cần kiểm tra quyền theo đối tượng (ví dụ lọc thêm owner_id
từ authentication context đáng tin) và test bằng hai tài khoản:
A được xem đơn của A nhưng không xem được đơn của B.
~~~

Nhận xét không kết luận chắc chắn có lỗ hổng khi chưa kiểm tra các lớp khác. Nó mô tả **đường dẫn giả định đến rủi ro**, yêu cầu bằng chứng và một trường hợp test cụ thể.

### 8.3. Không biến một cách sửa minh họa thành quy tắc chung

Ví dụ điều kiện `WHERE id = ? AND owner_id = ?` có thể phù hợp khi **quy tắc là chỉ chủ đơn được xem**. Nhưng ứng dụng thật có thể cho phép nhân viên hỗ trợ, người được ủy quyền hoặc quyền theo tenant. Reviewer nên hỏi về **chính sách đúng**, không ép mọi sản phẩm dùng đúng một truy vấn mẫu.

Đặc biệt, `ownerId` không được lấy từ tham số tự khai của client rồi dùng như bằng chứng quyền. Nó phải dựa trên danh tính và hợp đồng xác thực đáng tin.

## 9. Ví dụ về xử lý lỗi: nhận xét khi ngoại lệ bị nuốt

Xét đoạn mã:

~~~java
try {
    invoiceWriter.write(invoice);
} catch (Exception ignored) {
    return true;
}
~~~

Nếu hợp đồng yêu cầu chỉ trả thành công sau khi hóa đơn đã được lưu, việc bắt mọi ngoại lệ rồi trả `true` có thể tạo kết quả sai.

**Nhận xét chưa đủ:** “Không catch Exception.”

**Nhận xét có lý do và tác động:**

> “[Blocking — trạng thái kết quả] Trong nhánh catch của `saveInvoice`, lỗi ghi bị bỏ qua nhưng hàm trả thành công. Nếu database hoặc disk từ chối ghi, caller sẽ nghĩ hóa đơn đã lưu và có thể tiếp tục thanh toán, trong khi dữ liệu chưa tồn tại. Nhờ giữ thông tin lỗi và trả trạng thái thất bại theo hợp đồng hiện tại; thêm test cho `invoiceWriter.write` ném `IOException` (nếu đây là loại lỗi adapter trả ra).”

Điều cần bảo vệ là **tính trung thực của kết quả và trạng thái sau lỗi**, không chỉ quy tắc cú pháp “không catch rộng”. Có trường hợp boundary bắt rộng để chuyển thành HTTP 500 hoặc ghi log rồi ném lại có căn cứ; đánh giá phải dựa trên hợp đồng.

### 9.1. Mức chắc chắn của comment

Nếu `write` có retry nội bộ hoặc việc lưu theo mô hình bất đồng bộ, reviewer cần xác minh hợp đồng “thành công” có nghĩa gì. Không được tự suy rằng mọi thành công phải đồng nghĩa dữ liệu đã ghi bền vững, nhưng nên **đặt câu hỏi tại ranh giới nơi caller dựa vào kết quả**.

## 10. Ví dụ về trạng thái dùng chung: chỉ rõ điều kiện đồng thời

Một handler được tạo theo scope singleton có field mutable:

~~~java
final class RequestHandler {
    private String currentRequestId;

    String handle(String requestId) {
        currentRequestId = requestId;
        return "processed:" + currentRequestId;
    }
}
~~~

Trong chạy tuần tự, kết quả có thể đúng. Nhưng nếu hai thread gọi cùng instance, request A có thể gán ID rồi bị request B ghi đè trước khi A đọc lại.

**Nhận xét nên viết:**

> “[Blocking nếu handler được chia sẻ giữa request] Trong `RequestHandler.handle`, `currentRequestId` là field mutable được ghi rồi đọc lại. Nếu bean có scope singleton và hai request chạy đồng thời, ID của B có thể xuất hiện trong kết quả của A. Chúng ta có thể giữ ID bằng biến cục bộ `requestId` thay vì field không? Nhờ xác nhận lifecycle của handler; nếu được chia sẻ, cần test hoặc review tính an toàn đồng thời.”

Ở đây **điều kiện “singleton và nhiều thread”** là thiết yếu. Nếu mỗi request có một instance, đường rủi ro có thể khác. Reviewer không nên mạo nhận đã chứng minh race từ một snippet khi chưa biết vòng đời đối tượng.

### 10.1. Khi sửa, kiểm tra tác động quan sát được

Một bản sửa đơn giản:

~~~java
final class RequestHandler {
    String handle(String requestId) {
        return "processed:" + requestId;
    }
}
~~~

Mục tiêu là loại bỏ trạng thái chung không cần thiết. Không nên “sửa” bằng cách đưa `volatile` vào field: `volatile` không tạo quyền sở hữu riêng cho từng request và không bảo đảm hai lời gọi không ghi đè nhau.

## 11. Nhận xét hiệu năng cần workload và dữ liệu, không chỉ trực giác

Nhận xét kiểu “Đoạn này O(n²), phải tối ưu ngay” có thể đúng về tiệm cận nhưng thiếu bằng chứng rằng độ phức tạp đó đang ảnh hưởng đến yêu cầu thực tế.

Giả sử mã:

~~~java
for (String requestedSku : requestedSkus) {
    if (allowedSkus.contains(requestedSku)) {
        accepted.add(requestedSku);
    }
}
~~~

Nếu `allowedSkus` là `List`, mỗi lần `contains` thường phải quét tuần tự trong trường hợp xấu. Với `n` phần tử được phép và `m` yêu cầu, chi phí so sánh có thể tới **O(n × m)**.

Một bình luận có ích:

> “[Suggestion — kiểm tra hiệu năng batch] Vòng lặp đang gọi `List.contains` cho từng SKU. Nếu danh mục có hàng chục nghìn phần tử và mỗi batch tra cứu nhiều lần, tổng số phép so sánh có thể tăng theo `n × m`. Chúng ta có số liệu kích thước danh mục và số lần tra cứu thực tế không? Nếu workload đủ lớn, có thể xây `HashSet` một lần cho batch và benchmark cả chi phí tạo index lẫn bộ nhớ.”

Câu này không tự khẳng định phương án mới luôn nhanh hơn. Với danh sách rất ngắn hoặc chỉ một lần tra cứu, xây `HashSet` có thể thêm chi phí không đáng.

### 11.1. Nếu đã có bằng chứng đo

Một nhận xét có thể mạnh hơn khi có kết quả thực:

> “Trong benchmark đính kèm dùng workload đại diện, đoạn tra cứu này chiếm phần đáng kể thời gian của batch và vượt ngưỡng mục tiêu đã thống nhất. Đề xuất index snapshot một lần; cần xác nhận kết quả trùng khớp với cách quét, và theo dõi heap/GC.”

**Không bịa p95, thời gian hoặc kích thước dữ liệu** nếu chưa đo. Việc phát hiện nguy cơ hiệu năng có thể bắt đầu bằng câu hỏi; việc chặn merge cần căn cứ theo rủi ro, ngân sách hoặc yêu cầu đã có.

## 12. Nhận xét về cấu trúc và khả năng bảo trì

Đối với nhận xét mang tính thiết kế, cần nói **chi phí thay đổi** thay vì chỉ gọi tên “code smell”.

### 12.1. Phương thức nhiều trách nhiệm

**Yếu:** “Hàm dài quá. Refactor.”

**Cụ thể:**

> “[Should fix — testability] `generateQuote` vừa tính chiết khấu, vừa mở kết nối DB và ghi file. Hiện test trường hợp đúng ngưỡng phải dựng cả DB và filesystem; nếu lỗi định dạng tệp, test giá cũng thất bại. Có thể tách phần tính `PriceQuote` khỏi adapter đọc/ghi, rồi test chính sách với dữ liệu thuần không?”

Nhận xét thể hiện **vấn đề đang có** và phương án đủ hẹp. Không bắt buộc người viết tạo sáu lớp chỉ để dùng một mô hình kiến trúc.

### 12.2. Trừu tượng hóa chưa có nhu cầu

**Yếu:** “Đừng overengineer.”

**Cụ thể:**

> “[Suggestion] `DiscountStrategyFactory` hiện chỉ có một implementation và mọi `channel` đều trả cùng chiến lược. Khi đổi mức giảm giá, người đọc phải đi qua factory và registry dù chưa có lựa chọn thực. Nếu chưa có biến thể được phê duyệt, có thể gọi trực tiếp policy và ghi điều kiện xem lại khi chính sách theo kênh xuất hiện.”

Tuy nhiên, **một interface chỉ có một implementation không tự là mùi mã** nếu nó là ranh giới I/O hay public extension point. Reviewer phải kiểm tra trước khi yêu cầu xóa.

### 12.3. Tên và đơn vị chưa rõ

**Yếu:** “Tên xấu.”

**Cụ thể:**

> “[Non-blocking — clarity] Biến `amount` là giá trị VND trước hay sau giảm? Phương thức bên dưới cũng có `total`. Đặt thành `subtotalVnd` sẽ làm rõ đơn vị và tránh nhầm với `amountDueVnd` khi bổ sung phí vận chuyển.”

Đây là nhận xét nhỏ nhưng có lý do. Nếu formatter hoặc quy ước đặt tên đã xử lý được, có thể dẫn liên kết hoặc tự động sửa thay vì kéo dài trao đổi.

## 13. Mối quan hệ giữa comment và test

Review không phải chỉ “đọc cho có” trước merge. Một nhận xét phát hiện nguy cơ nên giúp nhóm tạo **bằng chứng phân biệt mã đúng và sai**.

| Vấn đề được nêu | Test hoặc bằng chứng phù hợp |
| --- | --- |
| Sai ở đúng ngưỡng | Unit test tại ngưỡng và hai phía |
| Trả thành công sau khi ghi thất bại | Test lỗi adapter và trạng thái kết quả |
| Có thể lộ dữ liệu giữa tenant | Test hai danh tính/two tenants, quyền được phép và bị từ chối |
| Cache trả dữ liệu cũ | Test cập nhật, invalidation và hợp đồng độ tươi |
| Retry tạo bản ghi trùng | Test idempotency với cùng request ID và lỗi trung gian |
| Handler rò state giữa request | Kiểm tra scope, test đồng thời và quan sát state riêng |
| SQL query sai mapping | Integration test với database/schema đại diện |
| PR phá tương thích event | Contract test với consumer cũ và lộ trình migration |
| Quy tắc quá khó hiểu | Review hành vi và cấu trúc; test chỉ xác nhận những phần có hợp đồng |

**Không nên yêu cầu “thêm unit test” cho mọi vấn đề**. Có những lỗi chỉ lộ khi framework wiring, transaction, cấu hình mạng hoặc client cũ tham gia. Cấp kiểm thử cần tương xứng với đường gây hậu quả.

### 13.1. Coverage không thay thế test oracle

Nếu bộ test chạy cả nhánh `true` và `false` của `subtotal > 500_000`, nó vẫn có thể bỏ sót đúng giá trị 500.000. Một comment tốt nói **ca nào chưa được kiểm tra và expected gì**, không chỉ ghi “coverage thấp/cao”.

### 13.2. Không bắt tác giả viết test vô nghĩa để thỏa comment

Một assertion như `assertNotNull(quote)` không bảo vệ việc giảm 10% chính xác. Reviewer có thể làm rõ:

> “Để bắt lỗi điều kiện ngưỡng, test cần khẳng định `discountVnd == 50_000` và `amountDueVnd == 450_000` với đầu vào 500.000 VND, không chỉ assert object được tạo.”

Như vậy, tác giả hiểu mục tiêu của test chứ không chỉ thêm số dòng kiểm thử.

## 14. Cách đặt câu hỏi mà vẫn truyền đạt rủi ro

Dùng câu hỏi là phù hợp khi reviewer thiếu dữ kiện, nhưng câu hỏi phải **giúp làm rõ điều quyết định**, không chỉ tạo một yêu cầu giải thích chung chung.

| Câu hỏi yếu | Câu hỏi tốt hơn |
| --- | --- |
| “Sao làm thế này?” | “`retry` có thể chạy lại sau timeout không? Nếu có, đâu là khóa idempotency ngăn lưu trùng?” |
| “Đã nghĩ đến security chưa?” | “Nguồn `tenantId` ở đây có được ràng buộc với người dùng đã xác thực không?” |
| “Có thể nhanh hơn không?” | “Batch thực tế có bao nhiêu SKU? Nếu lớn, có benchmark giữa quét `List` và xây `Set` không?” |
| “Sao không dùng interface?” | “Có ranh giới I/O hoặc biến thể đang tồn tại nào mà interface cần cô lập không?” |
| “Có cần test không?” | “Có test nào bảo vệ trường hợp đúng ngưỡng và thất bại khi dịch vụ ngoài timeout không?” |

Một câu hỏi tốt có **điều kiện**, **lý do hỏi** và **dữ liệu cần nhận**. Tác giả có thể trả lời bằng liên kết đến test, tài liệu, mã hoặc quyết định đã được xác nhận.

## 15. Giọng điệu cộng tác: tranh luận về mã, không đánh giá con người

Cùng một vấn đề có thể được nói theo cách gây phòng thủ hoặc tạo hợp tác.

| Nên tránh | Cách diễn đạt phù hợp hơn |
| --- | --- |
| “Sao bạn lại viết như vậy?” | “Mình đang hiểu đoạn này theo hướng X; hợp đồng có yêu cầu Y không?” |
| “Rõ ràng là sai.” | “Với đầu vào Z, điều kiện hiện tại trả A trong khi đặc tả yêu cầu B.” |
| “Bạn không biết SOLID à?” | “Logic giá đang phụ thuộc trực tiếp vào JDBC, nên test biên cần kết nối DB; tách ranh giới sẽ giảm chi phí test.” |
| “Làm lại hết đi.” | “Mình đề xuất tách bước ghi ra khỏi phép tính trước; các phần còn lại có thể giữ nguyên trong PR này.” |
| “Tôi thích cách này hơn.” | “Theo quy ước hiện hành về tên có đơn vị, `subtotalVnd` sẽ làm rõ ý nghĩa hơn `total`.” |
| “Cứ sửa theo tôi.” | “Có phương án nào giữ đúng hợp đồng và loại được rủi ro này không? Cách A là một lựa chọn.” |

Mục tiêu là **rõ ràng, lịch sự và có trách nhiệm**. Không cần làm yếu lời cảnh báo bảo mật chỉ để tỏ ra nhẹ nhàng; cũng không nên biến sở thích cá nhân thành mệnh lệnh chặn merge.

### 15.1. Phân biệt yêu cầu và đề xuất

- **Yêu cầu:** “Nhờ bảo đảm đơn đúng ngưỡng không bị tính phí; cần test biên trước merge.”
- **Đề xuất:** “Có thể dùng `PriceQuote` thay nhiều biến song song để làm rõ hợp đồng.”
- **Câu hỏi:** “Có consumer nào còn đọc event schema cũ không?”
- **Thông tin:** “Formatter hiện có thể tự xử lý khoảng trắng này; không cần sửa tay.”

Không nên viết một comment dưới dạng câu hỏi nhưng kỳ vọng tác giả **bắt buộc sửa** mà không nói rõ. Nếu thật sự chặn merge, hãy nói tại sao và điều kiện để giải quyết.

### 15.2. Tránh quá nhiều lời mở đầu làm mờ vấn đề

“Chỉ là ý kiến nhỏ thôi nhưng có thể có chút vấn đề...” có thể khiến lỗi tính tiền quan trọng trở nên khó nhận thấy. Một bình luận tốt có thể đồng thời **tôn trọng người viết** và **nêu mức độ nghiêm trọng chính xác**.

## 16. Khi nào nên đưa phương án sửa, khi nào nên để tác giả chọn?

Reviewer cần nêu **kết quả cần đạt**. Phương án cụ thể hữu ích khi nó ngắn, phù hợp hợp đồng và dễ kiểm chứng. Nhưng reviewer có thể chưa biết đầy đủ trade-off triển khai.

### 16.1. Nên đề nghị thay đổi cụ thể khi

- Lỗi và cách sửa trực tiếp đã rõ, chẳng hạn `>` thành `>=`.
- Có quy ước đã thống nhất, như đặt tên với đơn vị.
- Cách xử lý an toàn có căn cứ mạnh, chẳng hạn dùng parameter binding cho giá trị SQL.
- Test cần thêm đúng một trường hợp rõ ràng.

### 16.2. Nên nêu mục tiêu và thảo luận phương án khi

- Thay đổi vượt nhiều service hoặc schema.
- Có nhiều lựa chọn với trade-off khác nhau.
- Chưa biết đầy đủ vòng đời đối tượng, tải, dữ liệu hoặc consumer.
- Một phép tối ưu phải đo trước khi chọn cấu trúc.
- Cần phối hợp với đội sở hữu hệ thống khác.

Ví dụ:

> “Mục tiêu là bảo đảm timeout không tạo thanh toán trùng. Mình nghĩ có thể dùng khóa idempotency gắn request và đối soát trạng thái trước retry, nhưng muốn xác nhận hợp đồng của cổng thanh toán và ranh giới transaction trước khi chọn cách triển khai.”

Comment như vậy vừa có **định hướng**, vừa tránh áp đặt giải pháp có thể không phù hợp.

## 17. Tác giả nên phản hồi nhận xét như thế nào?

Review là hoạt động hai chiều. Khi nhận comment có vị trí, lý do và tác động, tác giả có thể trả lời bằng bằng chứng thay vì chỉ “done”.

Một chu trình hợp tác:

1. **Xác nhận cách hiểu:** vấn đề là trường hợp nào, hợp đồng nào?
2. **Kiểm tra căn cứ:** tái hiện test, truy vết caller hoặc xem cấu hình.
3. **Sửa hoặc giải thích:** đưa commit, test hoặc lý do không thay theo đề xuất.
4. **Nêu tác động:** hành vi nào đổi hoặc được giữ; có rủi ro chuyển chỗ không?
5. **Mời kiểm chứng:** cung cấp đường dẫn diff, test và kết quả review lại.

### 17.1. Ví dụ phản hồi khi đã sửa

~~~text
Đã đổi điều kiện thành >= ở ShippingPolicy.feeVnd.
Bổ sung test cho 499_999, 500_000 và 500_001 VND,
trong đó trường hợp đúng ngưỡng thất bại trên phiên bản cũ.
Đã chạy bộ test liên quan trên nhánh cập nhật và cả ba ca đều qua.
Nhờ xem lại phần thay đổi ở commit tương ứng.
~~~

Đây là **mẫu phản hồi**, không phải tuyên bố đã chạy test ở một repository thật.

### 17.2. Ví dụ phản hồi khi có kiểm soát ở tầng khác

~~~text
Cảm ơn đã chỉ ra rủi ro. tenantId ở đoạn này không lấy trực tiếp
từ body; middleware đã ánh xạ từ authentication context và từ chối
khác tenant. Mình đã bổ sung liên kết đến phần kiểm tra và một
integration test cho tài khoản A truy cập dữ liệu của B. Nếu còn
đường gọi nào bỏ qua middleware, mình sẽ rà soát thêm.
~~~

Nếu reviewer đã sai giả thiết, người viết vẫn nên trả lời **vào lý do kỹ thuật** thay vì chỉ nói “không có bug”. Reviewer cũng cần sẵn sàng cập nhật kết luận sau khi có bằng chứng mới.

### 17.3. Khi hai bên chưa thống nhất

Có thể tổng hợp thành câu hỏi quyết định:

> “Hợp đồng của API này có yêu cầu phản hồi đồng bộ sau khi dữ liệu đã ghi bền vững hay chỉ xác nhận đã nhận việc? Hai cách hiểu dẫn đến hai hướng xử lý lỗi khác nhau. Nhờ người sở hữu nghiệp vụ xác nhận trước khi chọn thiết kế.”

Không phải mọi bất đồng đều phải giải bằng tranh luận cú pháp ở một comment. Nếu cần quyết định rộng, có thể hẹn trao đổi hoặc tạo ADR/issue, nhưng **kết luận nên được ghi lại ở vị trí nhóm có thể tra cứu**.

## 18. Dùng công cụ tự động để giảm comment lặp lại

Formatter, linter, static analysis, CI và test có thể xử lý những quy tắc khách quan lặp lại. Reviewer nên tập trung vào **ngữ nghĩa, rủi ro và lý do thiết kế** mà công cụ không thể tự kết luận đầy đủ.

| Vấn đề | Công cụ có thể hỗ trợ | Reviewer vẫn cần làm gì? |
| --- | --- | --- |
| Thụt lề, sắp xếp import | Formatter / linter theo cấu hình | Không tranh luận thủ công nếu đã có chuẩn |
| Vi phạm cấu trúc đơn giản | Static analysis, architecture checks | Xem quy tắc có áp dụng đúng phạm vi không |
| Không đóng tài nguyên | Rule tĩnh và test lỗi | Kiểm tra ownership, lifecycle và đường thất bại |
| Sai biên nghiệp vụ | Unit test với dữ liệu đúng | Xác nhận đặc tả và chất lượng oracle |
| Thiếu phân quyền đối tượng | Test quyền và review luồng dữ liệu | Xác minh chính sách ownership/tenant thật |
| Suy giảm hiệu năng | Profiling và benchmark | Xác nhận workload, mục tiêu và trade-off |
| Phá hợp đồng API | Contract test, schema compatibility | Xác nhận consumer và lộ trình migration |

**Đừng trích một cảnh báo analyzer như thể đó là kết luận chắc chắn.** Có thể có dương tính giả và âm tính giả; reviewer cần xem source/sink, cấu hình và giả thiết công cụ. Tương tự, báo cáo CI xanh không chứng minh mọi trường hợp nghiệp vụ đã được kiểm tra.

### 18.1. Nhận xét về công cụ cũng cần cụ thể

Thay vì:

> “Sonar báo rồi, sửa.”

Nên ghi:

> “Rule X chỉ ra nhánh này có thể không đóng `ResultSet` nếu `executeQuery` ném ngoại lệ. Trong đường lỗi, tài nguyên có thể bị giữ đến khi connection đóng, gây áp lực lên pool khi có nhiều request thất bại. Nhờ xem có thể dùng `try-with-resources` và bổ sung test lỗi phù hợp không. Mình chưa xác nhận toàn bộ lifecycle ở adapter này.”

Nếu review xác nhận cảnh báo là FP, ghi lý do và xử lý theo quy trình thay vì giữ comment vô hạn.

## 19. Một quy trình viết nhận xét trong PR

### Bước 1 — Hiểu mục đích thay đổi

Trước khi bình luận, đọc mô tả PR, yêu cầu, hợp đồng và những test liên quan. Một dòng trông kỳ lạ có thể là giải pháp tương thích đã được quyết định; ngược lại, một thay đổi nhỏ có thể ảnh hưởng dữ liệu quan trọng.

### Bước 2 — Đọc luồng thay vì chỉ diff riêng lẻ

Đặt đoạn mã vào bối cảnh: ai gọi, dữ liệu từ đâu đến, đầu ra đi đâu, có state/transaction/quyền nào liên quan. Với thay đổi nhiều file, xem phụ thuộc và tác động trước khi nêu nhận xét cấu trúc.

### Bước 3 — Phân loại phát hiện

Tách lỗi tính đúng, bảo mật, độ tin cậy, tương thích, hiệu năng và khả năng bảo trì. Chọn mức ưu tiên; cân nhắc xem vấn đề có thực sự do PR tạo ra hoặc làm trầm trọng thêm không.

### Bước 4 — Đặt nhận xét đúng vị trí

Gắn vào dòng chứa nguyên nhân nếu có thể. Nếu vấn đề vượt một đoạn, tạo comment cấp PR với các vị trí liên quan. Tránh để tác giả phải tìm lại cả repository để hiểu ý.

### Bước 5 — Nêu điều kiện và bằng chứng

Mô tả dữ liệu hoặc trạng thái gây lỗi, cách mã vận hành và hợp đồng bị ảnh hưởng. Nếu chưa chắc chắn, đánh dấu giả thiết và hỏi đúng điều cần xác minh.

### Bước 6 — Nêu tác động và hành động

Trả lời “nếu không sửa thì sao?” và “làm sao biết vấn đề đã được giải quyết?”. Có thể đề xuất test, thay đổi code nhỏ, điều tra cấu hình hoặc quyết định thiết kế.

### Bước 7 — Rà lại mức độ và giọng điệu

Kiểm tra comment có vô tình thành công kích cá nhân, áp đặt sở thích hay làm vấn đề minor thành blocker không. Nếu nhiều comment cùng gốc, gom lại.

### Bước 8 — Theo dõi phiên bản mới

Sau khi tác giả sửa, đọc code mới và xác minh bằng bằng chứng phù hợp. Không đóng comment chỉ vì có câu “fixed”; cũng không giữ comment đã lỗi thời mà không đọc lại thay đổi.

## 20. Ma trận ví dụ: từ nhận xét mơ hồ đến nhận xét có thể hành động

| Tình huống | Nhận xét mơ hồ | Nhận xét có ích |
| --- | --- | --- |
| **Điều kiện biên** | “Sửa dấu so sánh.” | “Đơn đúng 500.000 VND chưa được miễn phí vì dùng `>`; cần `>=` và test ngưỡng.” |
| **Phân quyền** | “Bảo mật chưa tốt.” | “Nếu ID từ URL không được kiểm tra ownership, A có thể xem đơn B; xác nhận guard và test bị từ chối.” |
| **Trạng thái dùng chung** | “Thread unsafe.” | “Field chứa request ID bị hai request ghi trên singleton; chuyển sang state riêng từng lời gọi.” |
| **Lỗi bị nuốt** | “Không catch rộng.” | “Khi ghi thất bại, hàm vẫn trả `true` nên caller tưởng đã lưu; cần phản ánh thất bại theo hợp đồng.” |
| **Hiệu năng** | “N+1 query.” | “Mỗi item gọi DB một lần; batch 100 item tạo 100 round-trip. Có thể fetch theo batch và đo query count/latency?” |
| **Tên biến** | “Tên chưa đẹp.” | “`total` chưa rõ trước/sau giảm và đơn vị; dùng `subtotalVnd` hoặc `amountDueVnd` theo vai trò.” |
| **Tách trách nhiệm** | “SOLID!” | “Hàm tính tiền cũng ghi file, khiến unit test cần I/O; tách tính giá để test biên độc lập.” |
| **Thay đổi schema** | “Migration nguy hiểm.” | “Cột cũ bị xóa trước khi job đọc cũ được nâng cấp; cần kế hoạch compatibility/expand–contract.” |
| **Test yếu** | “Thêm test.” | “Test mới chỉ assert `notNull`; thêm expected cụ thể ở đúng ngưỡng vì lỗi `>` vẫn có thể qua.” |
| **Đề xuất nhỏ** | “Dùng tên khác.” | “Non-blocking: `requestedAt` cho thấy đây là thời điểm yêu cầu, thay vì `date` dễ bị hiểu là ngày giao hàng.” |

Bảng nhằm thể hiện **cách lập luận**, không quyết định sẵn mức ưu tiên cho mọi dự án. Một lỗi ghi không bền vững có thể blocking ở hệ thống tiền tệ, nhưng yêu cầu về format báo cáo thử nghiệm có thể nhẹ hơn.

## 21. Khi nào không nên viết comment?

Có lúc **không bình luận** giúp review hiệu quả hơn.

- Vấn đề đã được formatter xử lý tự động và CI sẽ sửa hoặc báo chính xác.
- Nhận xét chỉ là sở thích cá nhân, không có quy ước hoặc tác động rõ.
- Đoạn mã nằm ngoài phạm vi PR và không làm tăng rủi ro của thay đổi hiện tại; có thể ghi issue riêng nếu cần.
- Reviewer chưa đọc đủ bối cảnh để hiểu đường dữ liệu; nên đọc tiếp hoặc hỏi một câu cụ thể trước.
- Cùng một vấn đề đã được nêu ở comment khác và tác giả đang xử lý.
- Comment cũ đã được giải quyết ở commit mới, không còn phản ánh mã hiện tại.

Điều này **không có nghĩa bỏ qua lỗi nghiêm trọng ngoài diff**. Nếu phát hiện nguy cơ mất dữ liệu hoặc phân quyền, cần nêu với mức ưu tiên phù hợp và phối hợp phạm vi xử lý. Ý chính là không biến review thành một danh sách nhận xét trùng hoặc khó hành động.

## 22. Lỗi thường gặp khi viết nhận xét

**“Chỗ này không tốt.”** Thiếu vị trí chính xác, điều kiện và tác động; người nhận phải đoán.

**“Tất cả nên dùng pattern X.”** Mẫu thiết kế không tự bảo đảm chất lượng. Nên giải thích một ranh giới hoặc biến thể có thật cần pattern ấy.

**“Chắc chắn gây lỗi” khi chưa xem cấu hình.** Giả thiết chưa xác minh cần được ghi dưới dạng điều kiện và câu hỏi có thể trả lời.

**“Có thể có vấn đề hiệu năng” mà không nêu workload.** Nên phân biệt nguy cơ tiệm cận với nút thắt đã đo; không tự bịa số liệu.

**“Đề nghị thêm test” nhưng không nói ca nào.** Cần đầu vào, expected và lý do test sẽ bắt được sai lệch.

**“Blocker” cho mọi khác biệt thẩm mỹ.** Làm mất ý nghĩa mức ưu tiên, khiến tác giả không phân biệt rủi ro lớn và nhỏ.

**“Nên viết lại toàn bộ class” trong PR sửa lỗi hẹp.** Có thể làm tăng diff và rủi ro hồi quy. Ưu tiên thay đổi nhỏ giải quyết vấn đề đã xác định.

**“Tại sao bạn không biết cách này?”** Chuyển tranh luận khỏi mã sang con người, giảm khả năng hợp tác.

**“Đã sửa” nhưng không đưa bằng chứng.** Khi có nghi ngờ về hợp đồng, nên chỉ ra test hoặc đoạn mã mới cho thấy điều kiện đã được xử lý.

**“Tác động là code không sạch.”** Đây chỉ là đánh giá hình thức. Nên nói cụ thể khó đọc ở đâu, chi phí thay đổi hay khả năng kiểm thử bị ảnh hưởng thế nào.

**“Không có tác động vì test xanh.”** Test có thể thiếu trường hợp biên hoặc tích hợp. Kết luận phải dựa trên phạm vi test thực sự chạy và oracle của nó.

**“Người review luôn có quyền quyết định cuối cùng.”** Quy trình có thể trao quyền theo chủ sở hữu module, security hoặc team lead; dù thế nào, lập luận vẫn cần bằng chứng và hợp đồng, không chỉ chức danh.

## 23. Bài tập tự luyện

### Tình huống A — Điều kiện ngưỡng

Trong `ShippingPolicy`, quy tắc là miễn phí từ 500.000 VND. Code dùng `subtotalVnd > 500_000`. Người review định viết: “Sai toán tử”.

**Yêu cầu:** viết lại một comment có vị trí, lý do, tác động và hành động.

**Gợi ý:** chỉ rõ nhánh `if`, đầu vào 500.000, kết quả 30.000 trái hợp đồng, dùng `>=` và thêm test đúng ngưỡng.

### Tình huống B — API trả dữ liệu theo ID

Endpoint `GET /orders/{id}` có câu SQL parameterized, nhưng người review chưa thấy bước xác minh quyền xem đơn.

**Yêu cầu:** đặt câu hỏi đủ cụ thể mà không khẳng định lỗ hổng khi chưa đủ dữ liệu.

**Gợi ý:** hỏi `ownerId`/tenant được kiểm tra ở đâu, xác định điều kiện nếu thiếu guard thì A có thể đọc đơn B, yêu cầu test với hai danh tính.

### Tình huống C — Viết log toàn bộ request

Một nhánh lỗi có `logger.error("failed {}", request)` và request có thể chứa token.

**Yêu cầu:** viết comment ưu tiên phù hợp với đường rủi ro.

**Gợi ý:** chỉ ra nguồn token, nơi log được ghi và người có thể xem log; đề nghị log trường có chọn lọc và test/policy che dữ liệu. Nếu chưa chắc `toString()` của request có chứa token, cần xác minh chứ không tuyên bố chắc chắn bị lộ.

### Tình huống D — Cảnh báo hiệu năng chưa đo

Một vòng lặp gọi `List.contains` cho từng phần tử, nhưng danh sách thường chỉ có 5–10 phần tử. Reviewer muốn chặn PR để dùng `HashSet`.

**Yêu cầu:** quyết định cần thêm bằng chứng gì trước khi blocking.

**Gợi ý:** xem số truy vấn/batch, chi phí tạo set, bộ nhớ và mục tiêu latency. Nếu workload nhỏ, đổi cấu trúc có thể không cần. Một comment “suggestion/question” có thể phù hợp hơn.

### Tình huống E — Tác giả trả lời “đã có test”

Một test mới gọi phương thức tính phí với 600.000 VND và chỉ kiểm tra kết quả khác null. Reviewer đang lo lỗi đúng ngưỡng 500.000 VND.

**Yêu cầu:** viết phản hồi sao cho không tranh luận chung chung về coverage.

**Gợi ý:** nêu cụ thể test hiện chưa kích hoạt đầu vào 500.000, và khẳng định phải là phí 0. Có thể dẫn chứng bằng ca JUnit ngắn.

### Tình huống F — Đổi schema qua nhiều service

PR thêm field bắt buộc vào event và xóa field cũ. Một consumer vẫn đang dùng schema cũ.

**Yêu cầu:** chọn vị trí comment và giải thích vì sao khó hoàn tác.

**Gợi ý:** comment cấp PR với nơi producer và consumer liên quan, mô tả phiên bản cũ không đọc được event mới, đề nghị kiểm tra compatibility và kế hoạch expand–migrate–contract.

### Tình huống G — Nhận xét chỉ dựa trên style cá nhân

Reviewer viết “Tôi thích stream hơn vòng lặp”. Vòng lặp đang ngắn, dễ đọc và không vi phạm convention.

**Yêu cầu:** có nên comment không? Nếu có, mức nào?

**Gợi ý:** không cần ép thay. Nếu stream cải thiện điều gì thực sự, giải thích rõ; nếu chỉ là sở thích, có thể bỏ qua hoặc đánh dấu non-blocking với lời đề xuất nhẹ.

### Tình huống H — Đồng thời và vòng đời object

Một field mutable bị cập nhật trong `handle`, nhưng reviewer chưa biết handler được tạo mỗi request hay dùng singleton.

**Yêu cầu:** biến nhận định “race condition” thành comment dựa trên điều kiện.

**Gợi ý:** chỉ ra field, hai lần gọi có thể ghi xen kẽ nếu cùng instance, hỏi lifecycle/scope và đề nghị dùng biến cục bộ nếu không cần giữ state.

## 24. Mẫu comment và checklist có thể dùng khi review

Một mẫu đầy đủ cho vấn đề quan trọng:

~~~text
[Mức ưu tiên — loại vấn đề]
Vị trí: <file / method / đoạn điều kiện có thật trong diff>

Quan sát:
<Đoạn mã hiện làm gì; dữ liệu hoặc trạng thái nào liên quan?>

Căn cứ:
<Đặc tả, hợp đồng, test, quy ước hoặc bằng chứng đo nào?>

Tác động:
<Với điều kiện nào, ai hoặc tài nguyên nào chịu hậu quả gì?>

Đề nghị:
<Thay đổi tối thiểu hoặc cách xác minh; test cần bảo vệ điều gì?>

Mức chắc chắn:
<Đã tái hiện / suy luận trực tiếp / còn phải xác minh điều kiện nào?>
~~~

Một mẫu ngắn cho góp ý nhỏ:

~~~text
[Non-blocking] Ở <vị trí>, tên <tên cũ> chưa cho biết <ý nghĩa>.
Có thể dùng <tên mới> để người đọc phân biệt <hai khái niệm>?
~~~

### Checklist cho người viết nhận xét

- **Vị trí:** tôi đã chọn đúng dòng, đoạn hoặc cấp PR?
- **Bối cảnh:** đã hiểu luồng gọi, dữ liệu và yêu cầu của thay đổi?
- **Quan sát:** có thể mô tả điều mã đang làm mà không phán đoán người viết?
- **Lý do:** có nêu hợp đồng hoặc cơ chế khiến đây là vấn đề?
- **Tác động:** biết đầu vào/trạng thái nào và hậu quả cụ thể?
- **Độ chắc chắn:** đã phân biệt bằng chứng xác nhận với giả thiết?
- **Mức ưu tiên:** rõ là blocker, should fix, suggestion, nit hay question?
- **Hành động:** tác giả biết cần thay đổi hoặc xác minh điều gì?
- **Kiểm thử:** có thể đề xuất một test có expected thật sự phân biệt đúng/sai?
- **Phạm vi:** nhận xét có nằm trong PR hay cần việc riêng?
- **Giọng điệu:** đang nhận xét code và hợp đồng thay vì đánh giá con người?
- **Theo dõi:** sau khi code đổi, có xem lại comment dựa trên phiên bản mới?

## 25. Kết luận

**Nhận xét code review có chất lượng là nhận xét giúp đưa ra quyết định kỹ thuật, chứ không chỉ bày tỏ cảm giác rằng một đoạn mã “đẹp” hay “xấu”.** Vị trí cụ thể giúp người viết tìm đúng nơi. Lý do và bằng chứng giúp hai bên kiểm tra cùng một giả thiết. Tác động giúp xếp ưu tiên theo rủi ro. Hành động hoặc test đề xuất giúp xác nhận vấn đề đã được giải quyết.

Một nhận xét tốt cũng biết nói **“tôi chưa chắc chắn ở điều kiện này”** khi cần, biết giữ **blocking** cho vấn đề quan trọng và biết dừng ở mức **suggestion** nếu chỉ có một lựa chọn thiết kế khác cũng hợp lệ. Trong **CODE_QUALITY_FUNDAMENTALS**, kỹ năng này giúp review trở thành phương tiện cải thiện mã **đáng tin cậy hơn nhờ phát hiện lỗi thật, dễ hiểu hơn nhờ lý do rõ ràng và dễ thay đổi hơn nhờ quyết định có thể tra cứu và kiểm chứng**.
