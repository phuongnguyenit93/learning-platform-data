# Mã thử nghiệm, công cụ nội bộ và mã được duy trì lâu dài

Chất lượng mã nguồn không được quyết định chỉ bằng việc mã trông gọn hay có nhiều kiểm thử. Cùng một giải pháp kỹ thuật có thể hợp lý trong bản thử nghiệm kéo dài hai ngày nhưng không đủ tin cậy cho một dịch vụ phục vụ khách hàng nhiều năm. Ngược lại, áp dụng mọi quy trình và tầng trừu tượng của hệ thống lớn cho một thử nghiệm nhỏ có thể tốn công mà không tạo thêm giá trị tương xứng.

Bài học thuộc chương **Bối cảnh và đánh đổi** của **CODE_QUALITY_FUNDAMENTALS**: hiểu những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi** hay không. Trọng tâm là cách xác định mức đầu tư chất lượng theo mục đích sử dụng, hậu quả khi sai và vòng đời dự kiến của mã.

## 1. Ba bối cảnh thường gặp

### 1.1. Mã thử nghiệm: ưu tiên học nhanh và giảm bất định

Mã thử nghiệm có thể là **proof of concept (PoC)**, nguyên mẫu (prototype) hoặc **spike** để khảo sát một câu hỏi kỹ thuật. Ví dụ:

- Thư viện A có xử lý được định dạng dữ liệu mới không?
- Thuật toán phân nhóm có đủ chính xác trên tập dữ liệu mẫu không?
- Cách tích hợp một API có đáp ứng yêu cầu thời gian phản hồi không?

Giá trị chính của mã thử nghiệm là **bằng chứng giúp ra quyết định**. Thành công có thể là kết luận “phương án này không phù hợp”, miễn là thử nghiệm trả lời được câu hỏi đặt ra.

Với mã chỉ chạy cục bộ, dùng dữ liệu giả lập và dự kiến bỏ đi, nhóm có thể chấp nhận một tệp ngắn, ít trừu tượng, kiểm thử thủ công có ghi nhận kết quả và tài liệu tập trung vào cách chạy cùng phát hiện thu được. Không nhất thiết phải tạo nhiều lớp, hệ thống cấu hình phức tạp hoặc pipeline triển khai hoàn chỉnh.

Tuy nhiên, từ “thử nghiệm” không tự động cho phép bỏ qua an toàn. Nếu thử nghiệm gọi API thật, dùng dữ liệu nhạy cảm, tiêu tốn tài nguyên đắt tiền hoặc có thể thay đổi dữ liệu sản xuất, cần kiểm soát tương ứng: quyền truy cập tối thiểu, giới hạn tác động, bảo vệ bí mật và khả năng dừng hoặc khôi phục.

**Dấu hiệu hoàn tất:** câu hỏi giả thuyết đã được trả lời, điều kiện chạy và giới hạn của kết quả được ghi lại, quyết định tiếp tục/chuyển hướng/dừng được làm rõ.

### 1.2. Công cụ nội bộ: ưu tiên đúng việc, an toàn và dễ vận hành

Công cụ nội bộ là chương trình phục vụ nhân viên, vận hành, nhóm phát triển hoặc các quy trình hậu trường: tạo báo cáo, đối soát dữ liệu, chuyển đổi định dạng, hỗ trợ xử lý sự cố, di chuyển dữ liệu hay tự động hóa việc lặp lại.

Một công cụ nội bộ có thể ít người sử dụng nhưng **quyền rất lớn**. Ví dụ, script di chuyển dữ liệu chỉ do hai kỹ sư vận hành nhưng có thể sửa hàng triệu bản ghi. Khi đó, yêu cầu an toàn và tính đúng đắn có thể **cao hơn** một trang web công khai chỉ hiển thị nội dung tĩnh.

Các câu hỏi đặc thù:

- Người dùng có hiểu đầu vào, tham số, lỗi và kết quả chạy không?
- Chạy lại có làm nhân đôi tác động hay phá hủy dữ liệu không?
- Có chế độ xem trước (**dry-run**), giới hạn phạm vi, xác nhận cho thao tác nguy hiểm hoặc sao lưu phù hợp không?
- Có thông báo đủ rõ để người vận hành biết bản ghi nào thành công, thất bại và cần xử lý tiếp?
- Ai duy trì khi tác giả ban đầu không còn trực tiếp sử dụng?

Với công cụ chạy định kỳ và được nhiều người phụ thuộc, yêu cầu về kiểm thử, xử lý lỗi, tài liệu và phát hành tăng lên theo thời gian. Nhãn “nội bộ” **không đồng nghĩa** với “chỉ cần chạy được”.

### 1.3. Mã duy trì lâu dài: ưu tiên thay đổi an toàn qua nhiều vòng đời

Mã được duy trì lâu dài có thể là dịch vụ sản xuất, thư viện dùng chung, ứng dụng nhiều phiên bản hoặc hệ thống nghiệp vụ cốt lõi. Nó thường được thay đổi nhiều lần bởi nhiều người, chịu các phụ thuộc và có người sử dụng trông đợi tính ổn định.

Giá trị chất lượng cần xét cả **hôm nay** lẫn **những lần sửa sau**:

- Hành vi đúng với trường hợp thường, biên và lỗi; có kiểm thử hồi quy.
- Ranh giới trách nhiệm và quy tắc nghiệp vụ đủ rõ để người mới đọc hiểu.
- Thiết kế và giao diện đủ ổn định để thay đổi có phạm vi kiểm soát.
- Giám sát, log, chỉ số hoặc truy vết phù hợp giúp chẩn đoán vấn đề.
- Quy trình phát hành, tương thích, di chuyển dữ liệu và quay lui khi thay đổi có rủi ro.

“Duy trì lâu dài” không có nghĩa thiết kế tất cả chức năng tương lai ngay từ đầu. Trừu tượng hóa quá sớm cũng tạo gánh nặng; nên đầu tư vào **điểm chắc chắn cần thay đổi** và duy trì cấu trúc đủ đơn giản cho nhu cầu đã biết.

## 2. So sánh mức đầu tư chất lượng theo bối cảnh

Bảng sau mô tả **điểm xuất phát**, không phải tiêu chuẩn cứng. Khi hậu quả sai nghiêm trọng, mức bảo đảm cần tăng bất kể loại mã.

| Khía cạnh | Mã thử nghiệm có phạm vi cô lập | Công cụ nội bộ | Mã được duy trì lâu dài |
| --- | --- | --- | --- |
| Mục tiêu chính | Kiểm chứng giả thuyết, học nhanh | Hoàn thành tác vụ tin cậy, giảm thao tác tay | Cung cấp chức năng ổn định và liên tục phát triển |
| Thời gian dự kiến | Ngắn, có điểm dừng | Một lần, theo đợt hoặc định kỳ | Nhiều phiên bản, nhiều năm hoặc chưa xác định |
| Yêu cầu chức năng | Đúng đối với phép thử và dữ liệu mẫu đã nêu | Đúng với dữ liệu, thao tác và lỗi thực tế của người vận hành | Đúng theo hợp đồng nghiệp vụ và tương thích cần thiết |
| Kiểm thử | Kiểm tra các giả thuyết, ca then chốt, ghi nhận kết quả | Ca dữ liệu điển hình, lỗi nhập, chạy lại, tác động phụ | Kiểm thử đơn vị, tích hợp, hồi quy và mức khác theo rủi ro |
| Cấu trúc mã | Đủ rõ để thử và kiểm chứng | Tách thao tác nguy hiểm khỏi logic xử lý; thông báo lỗi rõ | Ranh giới trách nhiệm, tính kết dính, khả năng mở rộng hợp lý |
| Tài liệu | Mục đích, cách chạy, giới hạn kết quả | Hướng dẫn sử dụng, quyền, tham số, xử lý lỗi, người phụ trách | Hợp đồng, quyết định thiết kế quan trọng, vận hành, thay đổi |
| Khả năng quan sát | Ghi nhận phép thử, thời gian, kết quả | Báo cáo số bản ghi xử lý, lỗi và trạng thái chạy | Log/metrics/tracing và cảnh báo phù hợp với tác động |
| Khả năng khôi phục | Có thể bỏ kết quả thử | Cân nhắc dry-run, sao lưu, checkpoint, idempotency | Có chiến lược triển khai, rollback hoặc khắc phục sự cố |
| Chi phí đáng ưu tiên | Thời gian có câu trả lời | Rủi ro tác động dữ liệu và công sức vận hành | Tổng chi phí sở hữu và rủi ro trong nhiều lần thay đổi |

**Điểm chung tối thiểu:** mục đích rõ, điều kiện thành công kiểm chứng được, không để lộ bí mật, không tự ý ảnh hưởng dữ liệu hoặc hệ thống ngoài phạm vi được phép. Cách thực thi các yêu cầu này có thể khác nhau tùy ngữ cảnh.

## 3. Đánh giá bối cảnh bằng rủi ro thực tế

Thay vì hỏi “đây là prototype hay production?”, hãy hỏi **điều gì xảy ra nếu mã sai và ai sẽ phải xử lý hậu quả**.

### 3.1. Những yếu tố quyết định mức đầu tư

1. **Mức độ ảnh hưởng:** sai sót chỉ làm hỏng dữ liệu thử, hay có thể làm mất tiền, mất dữ liệu thật, ảnh hưởng khách hàng hoặc quyền truy cập?
2. **Phạm vi tác động:** chạy trên một máy với dữ liệu giả hay tác động nhiều dịch vụ, tài khoản và bản ghi?
3. **Tần suất sử dụng:** chạy một lần hay hàng ngày? Có phụ thuộc nghiệp vụ khác không?
4. **Số người và khả năng thay người duy trì:** một tác giả còn nhớ mọi giả định, hay nhóm nhiều người sẽ tiếp quản?
5. **Tần suất thay đổi yêu cầu:** kết quả thử nghiệm cố định hay quy tắc thay đổi theo từng đợt kinh doanh?
6. **Khả năng phát hiện và phục hồi:** có thể biết sai ngay, chạy lại, đảo ngược hoặc khôi phục không?
7. **Tuổi thọ thực tế:** dự kiến bỏ sau một tuần, nhưng có dấu hiệu sẽ tiếp tục được gọi trong nhiều tháng không?
8. **Bảo mật và yêu cầu tổ chức:** có dùng dữ liệu thật, thông tin cá nhân, tài khoản đặc quyền hoặc thuộc quy trình bắt buộc nào không?

Đánh giá theo **mức ảnh hưởng và xác suất**, sau đó cân nhắc chi phí phòng ngừa, khả năng phát hiện và khắc phục. Ví dụ, xác suất thấp nhưng ảnh hưởng đến toàn bộ dữ liệu thanh toán vẫn cần kiểm soát nghiêm ngặt.

### 3.2. Ví dụ phân loại: cùng gọi là “script” nhưng khác trách nhiệm

| Tình huống | Bối cảnh cần ưu tiên | Lựa chọn phù hợp |
| --- | --- | --- |
| Chạy thuật toán trên 100 bản ghi giả để so sánh hai thư viện | Thử nghiệm cô lập | Mã nhỏ, dễ đổi; lưu giả thuyết, dữ liệu mẫu, kết quả |
| Tạo báo cáo trạng thái đơn hàng hàng tuần cho đội vận hành | Công cụ nội bộ dùng lặp lại | Kiểm tra đầu vào, xử lý lỗi, báo cáo nhất quán, người phụ trách |
| Chạy một lần để cập nhật giá của toàn bộ đơn hàng thật | Công cụ có rủi ro cao | Phê duyệt phạm vi, dry-run, backup/rollback khả thi, kiểm tra số bản ghi, nhật ký thao tác |
| API tính phí dùng bởi nhiều sản phẩm qua nhiều năm | Mã duy trì lâu dài | Hợp đồng rõ, kiểm thử hồi quy, tương thích, quan sát vận hành |

Số lượng dòng mã hoặc số người dùng **không đủ** để xác định mức rủi ro. Một công cụ 50 dòng sửa dữ liệu thật có thể cần kiểm soát chặt hơn một thư viện thử nghiệm 2.000 dòng.

## 4. Ví dụ xuyên suốt: thống kê trạng thái đơn hàng

Giả sử nhóm cần thống kê số đơn theo trạng thái **NEW**, **PAID**, **CANCELLED**.

### Giai đoạn A — Kiểm tra giả thuyết bằng dữ liệu mẫu

Mục tiêu là xác định thuật toán đếm có phù hợp với dạng dữ liệu dự kiến hay không:

~~~java
import java.util.List;

class CountPrototype {
    public static void main(String[] args) {
        List<String> statuses =
                List.of("PAID", "NEW", "PAID", "CANCELLED");

        long paid = statuses.stream()
                .filter("PAID"::equals)
                .count();

        System.out.println("PAID = " + paid);
    }
}
~~~

Đoạn này đủ trả lời câu hỏi nhỏ: với bộ dữ liệu trên, số đơn **PAID** là **2**. Nó **chưa phải** công cụ báo cáo hoàn chỉnh: chỉ đếm một trạng thái, dữ liệu gắn trong mã, chưa có xử lý file lỗi hoặc đầu vào không hợp lệ. Đó không phải khiếm khuyết cần sửa ngay nếu phạm vi thử nghiệm chỉ có vậy.

Tuy nhiên, nếu kết quả dùng để quyết định quan trọng, cần bổ sung bộ dữ liệu đại diện, xác nhận quy tắc đếm và giới hạn của kết luận. Một lần chạy thành công trên bốn phần tử không chứng minh khả năng xử lý dữ liệu thật.

### Giai đoạn B — Chuyển thành logic cốt lõi của công cụ nội bộ

Khi báo cáo được dùng định kỳ, logic nên kiểm tra trạng thái hợp lệ và phản hồi rõ nếu dữ liệu nguồn không khớp kỳ vọng. Ví dụ Java 9+:

~~~java
import java.util.Collection;
import java.util.Collections;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeMap;

final class OrderStatusReport {
    private static final Set<String> ALLOWED_STATUSES =
            Set.of("NEW", "PAID", "CANCELLED");

    static Map<String, Long> countByStatus(
            Collection<String> statuses) {

        Objects.requireNonNull(statuses, "statuses");

        Map<String, Long> counts = new TreeMap<>();
        for (String status : statuses) {
            if (status == null || !ALLOWED_STATUSES.contains(status)) {
                throw new IllegalArgumentException(
                        "Unsupported status: " + status);
            }
            counts.merge(status, 1L, Long::sum);
        }

        return Collections.unmodifiableMap(counts);
    }
}
~~~

Đoạn mã này:

- Đếm **tất cả trạng thái hợp lệ** thay vì chỉ PAID.
- Báo lỗi khi thấy trạng thái không mong đợi, tránh âm thầm đưa ra thống kê sai.
- Trả về bản đồ không thể sửa qua giao diện trả về, tránh người gọi vô tình thay đổi kết quả.
- Tách phép tính khỏi việc đọc file, hiển thị kết quả hay gửi báo cáo; các tác vụ đó có thể được thay đổi độc lập.

**Giới hạn cần ghi rõ:** đây chỉ là **logic tính toán**. Công cụ dùng thật vẫn cần bộ đọc định dạng dữ liệu phù hợp (ví dụ thư viện CSV xử lý dấu ngoặc kép đúng chuẩn), quy định về dữ liệu thiếu, báo cáo lỗi dòng nào, cơ chế xác thực và cách vận hành. Với báo cáo chỉ đọc, **dry-run** có thể không cần thiết; với công cụ cập nhật dữ liệu, dry-run hoặc cơ chế kiểm soát tương đương có thể là yêu cầu thiết yếu.

Một kiểm thử nhỏ cho logic cốt lõi bằng JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

class OrderStatusReportTest {
    @Test
    void countsSupportedStatuses() {
        Map<String, Long> result = OrderStatusReport.countByStatus(
                List.of("PAID", "NEW", "PAID"));

        assertEquals(2L, result.get("PAID"));
        assertEquals(1L, result.get("NEW"));
    }

    @Test
    void rejectsUnknownStatus() {
        assertThrows(IllegalArgumentException.class,
                () -> OrderStatusReport.countByStatus(
                        List.of("PAID", "UNKNOWN")));
    }
}
~~~

### Giai đoạn C — Trở thành thành phần lâu dài trong hệ thống

Nếu sau đó báo cáo được nhiều dịch vụ sử dụng và tích hợp vào sản phẩm chính, phần lớn công việc **không chỉ nằm ở phép đếm**:

- Định nghĩa trạng thái thành một mô hình miền rõ ràng, thống nhất ý nghĩa và cách xử lý trạng thái mới.
- Xác định hợp đồng đầu vào/đầu ra: trường bắt buộc, tương thích phiên bản, múi giờ nếu thống kê theo ngày và cách xử lý sự kiện trùng.
- Xử lý dung lượng lớn: đọc theo luồng, phân trang hoặc tổng hợp tại nguồn dữ liệu khi thích hợp thay vì nạp tất cả bản ghi vào bộ nhớ.
- Đặt ranh giới giữa nghiệp vụ, đọc dữ liệu và xuất báo cáo; kiểm thử các ranh giới quan trọng.
- Quan sát số lượng bản ghi, lỗi dữ liệu, thời gian xử lý; thiết kế cách chạy lại mà không tạo kết quả sai.
- Có quy trình triển khai, di chuyển dữ liệu và phục hồi đáp ứng mức ảnh hưởng.

Một phép đếm đơn giản vẫn có thể nằm trong lõi; tính bền vững đến từ **hợp đồng, vận hành và khả năng thay đổi an toàn** xung quanh nó. Không cần tạo ngay các tầng kiến trúc nếu chưa có lý do thực tế.

## 5. Những đánh đổi phổ biến

### 5.1. Tốc độ làm ra kết quả và mức bảo đảm

Mã thử nghiệm thường tối ưu cho **thời gian có thông tin**. Mã đang vận hành với hậu quả lỗi cao phải ưu tiên **khả năng đưa ra kết quả đúng và kiểm chứng được**. Tăng kiểm thử và kiểm tra đầu vào có chi phí trước mắt, nhưng có thể giảm mạnh chi phí tìm, sửa và khắc phục sự cố.

Cách quyết định: thử nghiệm cần bao nhiêu bằng chứng để kết luận? Công cụ vận hành cần bao nhiêu bằng chứng để được phép tác động dữ liệu? Hai ngưỡng này có thể rất khác nhau.

### 5.2. Mã ngắn và mã dễ bảo trì

Một tệp ngắn có thể dễ hiểu khi chỉ một người dùng, nhưng trở nên khó bảo trì khi trộn lẫn quy tắc nghiệp vụ, truy cập cơ sở dữ liệu và gửi thông báo. Tách lớp quá sớm cũng làm người đọc phải nhảy qua nhiều file.

**Tiêu chí:** mỗi phần có lý do thay đổi rõ hay chưa, và việc sửa một quy tắc kéo theo bao nhiêu phần không liên quan? Tránh dùng số lượng lớp hoặc số dòng làm chỉ số chất lượng độc lập.

### 5.3. Tái sử dụng và tính độc lập

Gom mọi đoạn mã trông giống nhau vào một hàm chung có thể gây phụ thuộc không cần thiết. Trước khi chia sẻ một thành phần, cần xác định **chúng có cùng ý nghĩa nghiệp vụ và thường thay đổi cùng nhau không**. Trong bản thử nghiệm, sao chép ít dòng có thể chấp nhận được; trong hệ thống lâu dài, sao chép cùng chính sách trên nhiều nơi thường làm tăng nguy cơ sửa thiếu.

### 5.4. Khả năng mở rộng và độ phức tạp vận hành

Khả năng xử lý hàng triệu bản ghi có giá trị khi khối lượng thật sự đòi hỏi. Dùng hàng đợi, cache phân tán và nhiều dịch vụ nhỏ cho tác vụ 100 dòng dữ liệu có thể gây quá nhiều chi phí triển khai, giám sát và sửa lỗi.

Hãy đo hoặc dự báo hợp lý **dung lượng, tốc độ, ngưỡng chấp nhận được và khả năng tăng trưởng**, rồi chọn kiến trúc tương ứng. Đừng dùng một kịch bản tăng trưởng chưa có cơ sở để biện minh cho mọi lớp phức tạp.

## 6. Khi mã thử nghiệm hoặc công cụ nội bộ bắt đầu sống lâu hơn dự kiến

Một nguồn nợ kỹ thuật phổ biến là **mã tạm thời được sử dụng lâu dài mà không được đánh giá lại**. Điểm chuyển đổi thường diễn ra âm thầm: kết quả thử nghiệm hữu ích, một người khác bắt đầu chạy hàng tuần, rồi công việc kinh doanh phụ thuộc vào nó.

Các tín hiệu cần đánh giá lại:

- Đã có người hoặc hệ thống khác phụ thuộc vào đầu ra.
- Bắt đầu dùng dữ liệu thật, quyền cao hơn hoặc quy trình có hậu quả khó đảo ngược.
- Nhiều người sửa mã; người tạo ban đầu không còn là người vận hành chính.
- Cần triển khai định kỳ, chạy trên nhiều môi trường hoặc hỗ trợ các phiên bản dữ liệu.
- Sự cố trước đây làm mất thời gian xử lý, khó tái hiện hoặc gây sai kết quả.
- Mỗi thay đổi nhỏ kéo theo sửa nhiều nơi và phát sinh lỗi hồi quy.

Có thể dùng quy trình nâng cấp theo từng bước:

1. **Định nghĩa lại mục tiêu và mức rủi ro:** xác nhận ai dùng, dữ liệu gì, hậu quả khi thất bại và tuổi thọ dự kiến.
2. **Chốt hành vi đang được phụ thuộc:** ghi nhận đầu vào/đầu ra, thêm kiểm thử cho trường hợp biên, trường hợp lỗi và chức năng quan trọng.
3. **Loại bỏ giả định nguy hiểm:** cấu hình và thông tin bí mật gắn trong mã, đường dẫn máy cá nhân, quyền quá rộng, xử lý lỗi im lặng.
4. **Tách phần cần ổn định:** phân biệt logic miền với hạ tầng, xác định giao diện, chuẩn bị hướng dẫn chạy và cách chẩn đoán lỗi.
5. **Tăng mức bảo đảm theo hậu quả:** kiểm thử tích hợp, quan sát, rollback, kiểm soát thay đổi, bảo trì thư viện phụ thuộc khi cần.
6. **Quyết định giữ, viết lại hay thay thế:** so sánh chi phí nâng cấp với rủi ro và lợi ích. Không mặc định phải viết lại mọi prototype.

Việc nâng cấp có thể thực hiện dần; không nên tái cấu trúc toàn bộ chỉ để đạt hình thức của “dự án lớn”. Với mã có rủi ro cao nhưng thiếu bằng chứng kiểm soát an toàn, **tạm dừng đưa vào sử dụng thật** cho đến khi đáp ứng yêu cầu quan trọng là quyết định phù hợp.

## 7. Cách ra quyết định và ghi nhận đánh đổi

Trước khi chọn mức đầu tư, nhóm có thể ghi ngắn gọn:

| Câu hỏi | Ví dụ câu trả lời cho công cụ báo cáo nội bộ |
| --- | --- |
| Mục tiêu và người dùng? | Đội vận hành tạo báo cáo hàng tuần |
| Dữ liệu và quyền truy cập? | Đọc dữ liệu đơn hàng thật; không sửa dữ liệu |
| Hậu quả khi sai? | Báo cáo kinh doanh thiếu hoặc sai số lượng |
| Tần suất, tuổi thọ? | Mỗi tuần, dự kiến tối thiểu một năm |
| Kiểm soát ưu tiên? | Kiểm tra đầu vào, test tổng hợp, thông báo lỗi rõ, quyền chỉ đọc |
| Chấp nhận hoãn điều gì? | Dashboard trực quan và tự động gửi email |
| Điều kiện đánh giá lại? | Nhiều nhóm dùng chung, khối lượng tăng, cần API |
| Ai sở hữu và xác nhận hoàn tất? | Người phụ trách công cụ cùng người dùng nghiệp vụ |

Các quyết định nhỏ có thể ghi trong README của **chính công cụ** hoặc trong issue; quyết định có ảnh hưởng lớn nên có bản ghi thiết kế rõ lý do, phương án đã cân nhắc và điểm cần xem lại. Mục tiêu là giúp người tiếp theo hiểu **vì sao đánh đổi được chấp nhận**, không phải làm tài liệu cho đủ thủ tục.

Có thể đánh giá tương đối tổng chi phí theo công thức khái niệm:

**Chi phí sở hữu = chi phí xây dựng ban đầu + chi phí thay đổi và vận hành + tổn thất kỳ vọng do lỗi + chi phí nâng cấp hoặc thay thế.**

Đây là khung suy nghĩ, không phải công thức có thể đo chính xác mọi biến số. Giải pháp nhanh nhất hôm nay chưa chắc là giải pháp rẻ nhất sau nhiều lần thay đổi; nhưng đôi khi việc xây quá kỹ một thử nghiệm sắp bỏ cũng là lãng phí.

## 8. Những nhận định dễ gây nhầm lẫn

**“Prototype không cần chất lượng.”** Prototype vẫn phải trả lời đúng câu hỏi, minh bạch về giả định và giới hạn. Nếu tác động dữ liệu thật thì vẫn phải an toàn tương xứng.

**“Công cụ nội bộ không cần bảo mật.”** Sai. Quyền vận hành và dữ liệu nội bộ có thể khiến công cụ gây ra hậu quả lớn nếu lộ thông tin, lỗi tham số hoặc bị dùng sai.

**“Mã production càng nhiều lớp càng tốt.”** Sai. Dễ thay đổi và dễ hiểu phụ thuộc vào ranh giới phù hợp, không phải số lượng tầng trừu tượng.

**“Một khi viết tạm thì chỉ cần đánh bóng rồi đưa lên production.”** Không hẳn. Cần xem lại giả định, dữ liệu, hợp đồng, kiểm thử, quyền truy cập và vận hành. Đôi khi nền tảng thử nghiệm không đáng giữ lại.

**“Mọi code smell phải được xử lý trước khi thử nghiệm.”** Không nhất thiết. Một số mùi mã không cản trở mục tiêu học nhanh; nhưng nếu chúng làm kết quả thử nghiệm khó kiểm chứng thì cần sửa.

**“Chạy được một lần nghĩa là đã tin cậy.”** Sai. Tính tin cậy thể hiện ở khả năng xử lý đầu vào khác nhau, lỗi, thay đổi môi trường, chạy lặp và hồi phục khi cần.

## 9. Tự kiểm tra quyết định trong một phút

Trước khi viết hoặc tái sử dụng một đoạn mã, tự hỏi:

- **Mục đích:** cần chứng minh điều gì hay phục vụ ai?
- **Tác động:** nếu sai, hậu quả gì và có đảo ngược được không?
- **Thời gian:** đoạn mã sẽ dùng bao lâu và bao nhiêu người cần hiểu nó?
- **Bằng chứng:** kiểm thử, kiểm tra thủ công hoặc quan sát nào đủ để tin kết quả?
- **Thay đổi:** quyết định nào giúp sửa an toàn khi yêu cầu khác đi?
- **Ranh giới:** khi nào phải nâng cấp mức kiểm soát hoặc ngừng sử dụng?

Chất lượng mã trong **CODE_QUALITY_FUNDAMENTALS** vì vậy luôn gắn với bối cảnh: **mã thử nghiệm** cần tạo kiến thức đáng tin, **công cụ nội bộ** cần hoàn thành tác vụ an toàn và rõ ràng, còn **mã duy trì lâu dài** cần giữ chức năng đúng qua nhiều lần thay đổi. Mức đầu tư có thể khác nhau, nhưng quyết định tốt luôn dựa trên hậu quả, bằng chứng và chi phí trong suốt vòng đời sử dụng.
