# Xác định phạm vi hành vi cần được bảo vệ

Một nhóm phát triển muốn chia nhỏ phương thức tính phí giao hàng vì mã khó đọc. Sau khi tái cấu trúc, mọi unit test cũ vẫn xanh, nhưng khách hàng ở đúng ngưỡng miễn phí lại bị tính thêm tiền. Ở một tình huống khác, giá trị trả về không đổi nhưng hệ thống gửi hai thông báo thay vì một. Cả hai cho thấy: **tái cấu trúc an toàn đòi hỏi biết chính xác hành vi nào phải được giữ nguyên trước khi bắt đầu sửa mã**.

Trong module **CODE_QUALITY_FUNDAMENTALS**, chúng ta nghiên cứu những thuộc tính làm mã nguồn **đáng tin cậy, dễ hiểu và dễ thay đổi**. Ở chương **Tái cấu trúc**, mục tiêu không phải chỉ là làm mã ngắn hoặc đẹp hơn. Mục tiêu là **cải thiện cấu trúc nội bộ trong khi bảo toàn hành vi quan sát được theo hợp đồng đã xác định**, trừ khi có một thay đổi hành vi được phê duyệt và tách bạch.

Bài học tập trung vào việc chọn **phạm vi hành vi cần bảo vệ**: đầu vào, đầu ra, lỗi, trạng thái, tác dụng phụ, tương tác với phụ thuộc, bảo mật và những đặc tính vận hành thực sự là một phần của yêu cầu.

## 1. Tái cấu trúc bảo vệ điều gì?

**Refactoring (tái cấu trúc)** là thay đổi cấu trúc bên trong của mã nhằm tăng khả năng hiểu, sửa hoặc tổ chức mà **không cố ý đổi hành vi bên ngoài theo hợp đồng**.

Ví dụ:

- Tách một phương thức dài thành các phương thức có tên rõ nghĩa.
- Loại bỏ quy tắc bị sao chép khi các bản sao thực sự cùng một hợp đồng.
- Đưa chi tiết gọi SDK ra khỏi lớp nghiệp vụ.
- Đơn giản hóa cấu trúc điều kiện nhưng giữ nguyên mọi nhánh có ý nghĩa.
- Tách trách nhiệm của một class khi các phần thay đổi vì những lý do khác nhau.

Tái cấu trúc **khác với sửa bug**. Nếu trước đây hàm tính sai ở một ngưỡng và sau đó tính đúng, đây là **thay đổi hành vi có chủ đích**, dù bản sửa chỉ thay một ký tự. Tái cấu trúc cũng khác với việc bổ sung tính năng, đổi mã lỗi, thay hợp đồng dữ liệu hay nâng giới hạn nghiệp vụ.

Một cách diễn đạt hữu ích:

> **Tái cấu trúc thay đổi cách hệ thống thực hiện nhiệm vụ, không thay đổi nhiệm vụ mà hệ thống cam kết thực hiện.**

Tuy nhiên, cụm từ “hành vi không đổi” cần được làm rõ. Nó không chỉ là cùng một giá trị trả về với một input đẹp; đôi khi còn bao gồm **ngoại lệ, dữ liệu đã ghi, số lần gửi thông báo, thứ tự tác dụng phụ và quyền truy cập**.

## 2. Phạm vi hành vi không đồng nghĩa phạm vi dòng mã

Khi refactor một phương thức, phạm vi code sửa có thể chỉ một file nhưng **phạm vi hành vi bị ảnh hưởng** có thể lớn hơn nhiều.

Ví dụ đường đi:

~~~mermaid
flowchart LR
    A["Checkout HTTP API"] --> B["OrderApplicationService"]
    B --> C["ShippingQuoteService"]
    B --> D["OrderRepository"]
    B --> E["NotificationSender"]
    C --> F["Shipping fee policy"]
~~~

Nếu tách ShippingQuoteService, cần xác định:

- Checkout nhận phí nào với các loại đơn?
- Thao tác có đổi exception hoặc HTTP response không?
- Mã có còn coi giao nhanh và vùng xa là hai phụ phí độc lập không?
- Có luồng nào khác gọi ShippingQuoteService không?
- Việc tính phí có đang vô tình gọi hoặc phụ thuộc trạng thái bên ngoài không?

**Phạm vi cần bảo vệ đi theo hợp đồng của những bên sử dụng**, không chỉ theo kích thước diff.

Một phương thức private có thể được thay hoàn toàn mà không cần kiểm thử trực tiếp từng bước nội bộ, miễn các **kết quả và bất biến quan trọng ở ranh giới thích hợp** vẫn được kiểm chứng.

## 3. Phân biệt hành vi hợp đồng, chi tiết triển khai và lỗi đã tồn tại

Không phải mọi đặc điểm của phiên bản cũ đều cần được đóng băng.

| Nhóm | Ví dụ | Khi refactor nên làm gì? |
| --- | --- | --- |
| **Hành vi được yêu cầu** | Đơn từ 500.000 VND miễn phí giao tiêu chuẩn. | Giữ nguyên và có assertion rõ. |
| **Tiền điều kiện** | Tổng tiền không được âm. | Giữ cách từ chối theo hợp đồng. |
| **Kết quả lỗi** | Đơn đã hủy không được thanh toán lại. | Giữ trạng thái từ chối và không tạo tác dụng phụ trái phép. |
| **Bất biến bảo mật** | Người dùng không có quyền không được xem tài liệu. | Bảo vệ ở đúng ranh giới và test đường từ chối. |
| **Chi tiết triển khai** | Dùng if/else hay toán tử điều kiện; tên biến local. | Có thể thay khi hành vi bên ngoài giữ nguyên. |
| **Tối ưu hóa nội bộ** | Một helper được gọi hai lần hay cache kết quả thuần. | Có thể đổi nếu không phá ràng buộc hiệu năng/tương tác có ý nghĩa. |
| **Lỗi đã biết** | Ở ngưỡng 500.000 VND bị thu sai phí dù chính sách yêu cầu miễn. | Không tự xem lỗi là hợp đồng; quyết định sửa riêng với test. |
| **Hành vi chưa rõ** | Một API trả null hay danh sách rỗng tùy nguồn dữ liệu. | Điều tra bên sử dụng và đặc tả trước khi quyết định giữ hay sửa. |

Mục tiêu là **bảo toàn điều cần được bảo toàn**, không phải sao chép mọi hành vi tình cờ của hệ thống cũ.

Có trường hợp client đã phụ thuộc vào một hành vi chưa được tài liệu hóa. Khi đó không thể giả định an toàn để thay ngay. Cần xác minh **tính tương thích**, mức sử dụng và phương án chuyển đổi. “Không được công bố” không tự động có nghĩa “không ai phụ thuộc”.

## 4. Lập bản đồ hành vi quan sát được

Trước khi refactor, viết một **bản đồ hành vi** theo các chiều có liên quan. Không nhất thiết mọi phương thức đều có đủ tất cả các chiều, nhưng cần chủ động kiểm tra thay vì bỏ qua.

| Chiều hành vi | Câu hỏi bảo vệ | Ví dụ |
| --- | --- | --- |
| **Giá trị trả về** | Input nào tạo output nào? | Phí giao hàng 0, 20.000 hay 50.000 VND. |
| **Tiền điều kiện** | Dữ liệu nào được phép hoặc bị từ chối? | subtotal âm bị từ chối trước khi tính. |
| **Ngoại lệ/mã lỗi** | Loại lỗi, điều kiện phát sinh và mã công khai có đổi không? | IllegalArgumentException cho đầu vào âm. |
| **Trạng thái** | Sau lời gọi, dữ liệu nào được tạo, sửa hoặc xóa? | Đơn chuyển sang CONFIRMED. |
| **Tác dụng phụ** | Có gửi sự kiện, email, thanh toán hoặc ghi log/audit không? | Chỉ phát một thông báo khi xác nhận thành công. |
| **Thứ tự thao tác** | Có bước nào phải xảy ra trước bước khác không? | Xác thực quyền trước khi đọc dữ liệu riêng tư. |
| **Tính đồng thời** | Khi hai lời gọi chạy song song, bất biến có còn đúng? | Không giữ tồn kho âm hoặc tạo hoàn tiền trùng. |
| **Idempotency** | Gửi lại cùng yêu cầu có tạo tác dụng phụ lặp không? | Cùng khóa yêu cầu không tạo hai giao dịch. |
| **Hợp đồng bên ngoài** | API, schema, mã lỗi, message hoặc định dạng đã cam kết có giữ nguyên không? | JSON field và HTTP status client dựa vào. |
| **Tài nguyên/độ trễ có ràng buộc** | Có timeout, giới hạn queue, tải bộ nhớ hoặc SLO nào cần giữ không? | Không giữ toàn bộ file lớn trong RAM. |

**Không phải mọi chi tiết kỹ thuật đều cần assertion.** Hãy bảo vệ các phần người dùng, caller, hệ thống phụ thuộc hoặc vận hành **được phép dựa vào**.

## 5. Bước đầu: mô tả thay đổi cấu trúc dự định làm

Giả sử yêu cầu refactor là:

> “Phương thức tính báo giá giao hàng đang chứa ba nhánh phí và khó cập nhật. Hãy tách các bước có tên rõ ràng, nhưng giữ nguyên công thức và hợp đồng công khai.”

Trước khi viết code, hãy chốt phạm vi:

**Trong phạm vi refactor:**

- Tên và cách tổ chức helper private.
- Cách chia trách nhiệm tính phí cơ bản và các phụ phí.
- Loại bỏ biểu thức khó đọc, miễn không đổi quy tắc.

**Ngoài phạm vi refactor:**

- Đổi ngưỡng miễn phí từ 500.000 VND sang một giá trị khác.
- Thêm khuyến mãi hoặc quy tắc khu vực mới.
- Đổi đơn vị từ VND nguyên sang số thực.
- Đổi kiểu trả về công khai hoặc loại lỗi được client dựa vào.
- Thêm lưu dữ liệu hay gửi thông báo mới.
- Thay đổi quy tắc tính thuế hoặc thanh toán không liên quan.

Việc ghi rõ **phần không được đổi** giúp reviewer tách bug fix và feature khỏi refactor, đồng thời giúp xác định những test bảo vệ phù hợp.

## 6. Ví dụ xuyên suốt: đặc tả phí giao hàng trước khi refactor

Trong bài học này, chính sách giả định là:

1. **subtotalVnd** phải là số nguyên không âm.
2. Nếu subtotalVnd **nhỏ hơn 500.000**, phí giao tiêu chuẩn là **30.000 VND**.
3. Từ **500.000 trở lên**, phí tiêu chuẩn bằng **0 VND**.
4. Nếu **express = true**, cộng **20.000 VND**.
5. Nếu **remoteArea = true**, cộng thêm **15.000 VND**.
6. Hai phụ phí **cộng độc lập** và vẫn áp dụng khi phí tiêu chuẩn bằng 0.
7. Kết quả trả về tách từng khoản và tổng phí; hàm **không có tác dụng phụ**.
8. subtotalVnd âm làm phát sinh **IllegalArgumentException**.

Ngưỡng và mức phí chỉ là **giả định phục vụ bài học**, không phải chính sách chung của sản phẩm.

### Ma trận hợp đồng cần bảo vệ

| Ca | subtotalVnd | express | remoteArea | Phí tiêu chuẩn | Giao nhanh | Vùng xa | Tổng |
| --- | ---: | :---: | :---: | ---: | ---: | ---: | ---: |
| Q01 | 0 | false | false | 30.000 | 0 | 0 | **30.000** |
| Q02 | 499.999 | false | false | 30.000 | 0 | 0 | **30.000** |
| Q03 | 500.000 | false | false | 0 | 0 | 0 | **0** |
| Q04 | 500.001 | false | false | 0 | 0 | 0 | **0** |
| Q05 | 500.000 | true | false | 0 | 20.000 | 0 | **20.000** |
| Q06 | 500.000 | false | true | 0 | 0 | 15.000 | **15.000** |
| Q07 | 499.999 | true | true | 30.000 | 20.000 | 15.000 | **65.000** |
| Q08 | 500.000 | true | true | 0 | 20.000 | 15.000 | **35.000** |
| Q09 | -1 | false | false | — | — | — | **IllegalArgumentException** |

Bảng không được tạo bằng cách gọi chính phương thức cần refactor rồi sao chép output. **Kết quả kỳ vọng phải được suy độc lập từ đặc tả đã chốt**.

Bảng này có chủ đích bao gồm **ngay dưới, bằng và ngay trên ngưỡng**; nếu chỉ kiểm tra đơn 100.000 và 1.000.000 VND, lỗi dùng **>** thay **>=** có thể không bị phát hiện.

## 7. Phiên bản trước: mã gộp nhiều điều kiện

Một implementation Java 17 có thể viết:

~~~java
public final class ShippingQuoteService {
    public record Quote(
            long standardFeeVnd,
            long expressSurchargeVnd,
            long remoteSurchargeVnd,
            long totalFeeVnd) {
    }

    public Quote quote(
            long subtotalVnd, boolean express, boolean remoteArea) {
        if (subtotalVnd < 0L) {
            throw new IllegalArgumentException("negative subtotal");
        }

        long standard = subtotalVnd >= 500_000L ? 0L : 30_000L;
        long expressFee = express ? 20_000L : 0L;
        long remoteFee = remoteArea ? 15_000L : 0L;

        return new Quote(
                standard, expressFee, remoteFee,
                standard + expressFee + remoteFee);
    }
}
~~~

Đoạn code này khá ngắn và hoàn toàn có thể chấp nhận được nếu không có nhu cầu tổ chức lại. Giả sử trong hệ thống thật phương thức chứa thêm nhiều nhánh phụ phí và quy tắc độc lập, nhóm quyết định **đặt tên cho các bước** để giảm rủi ro khi thay đổi.

Điều cần nhớ: phương thức hiện tại là **mốc hành vi cần so sánh**, nhưng **hợp đồng chính thức** vẫn là đặc tả ở phần 6. Nếu phát hiện phương thức trước vốn có bug, phải phân loại thay vì đưa bug đó vào đặc tả.

## 8. Phiên bản sau: đổi cấu trúc, giữ cùng hợp đồng

Dưới đây là **phiên bản thay thế** của cùng lớp. Không đặt hai bản định nghĩa ShippingQuoteService cạnh nhau trong cùng package khi biên dịch; hãy xem đây là trạng thái trước/sau của một file.

~~~java
public final class ShippingQuoteService {
    private static final long FREE_STANDARD_THRESHOLD = 500_000L;
    private static final long STANDARD_FEE = 30_000L;
    private static final long EXPRESS_SURCHARGE = 20_000L;
    private static final long REMOTE_SURCHARGE = 15_000L;

    public record Quote(
            long standardFeeVnd,
            long expressSurchargeVnd,
            long remoteSurchargeVnd,
            long totalFeeVnd) {
    }

    public Quote quote(
            long subtotalVnd, boolean express, boolean remoteArea) {
        validateSubtotal(subtotalVnd);

        long standardFee = calculateStandardFee(subtotalVnd);
        long expressFee = express ? EXPRESS_SURCHARGE : 0L;
        long remoteFee = remoteArea ? REMOTE_SURCHARGE : 0L;

        long totalFee = standardFee + expressFee + remoteFee;
        return new Quote(standardFee, expressFee, remoteFee, totalFee);
    }

    private static void validateSubtotal(long subtotalVnd) {
        if (subtotalVnd < 0L) {
            throw new IllegalArgumentException("negative subtotal");
        }
    }

    private static long calculateStandardFee(long subtotalVnd) {
        return subtotalVnd >= FREE_STANDARD_THRESHOLD
                ? 0L
                : STANDARD_FEE;
    }
}
~~~

Những điểm **đã đổi**:

- Đặt tên hằng số thay cho giá trị rải trong biểu thức.
- Tách điều kiện hợp lệ của subtotal thành một helper.
- Tách phép tính phí tiêu chuẩn thành một helper có ý nghĩa.
- Đặt tên **totalFee** để kết quả dễ đọc hơn.

Những điểm **được yêu cầu giữ nguyên**:

- Chữ ký phương thức công khai **quote(long, boolean, boolean)**.
- Kiểu trả về và ý nghĩa các thành phần trong **Quote**.
- Điều kiện subtotal âm bị từ chối bằng **IllegalArgumentException**.
- Ngưỡng miễn phí, mức phí và phép cộng của các phụ phí.
- Không có ghi dữ liệu, gọi mạng hay sự kiện mới.

Không cần tạo một interface và ba lớp chỉ để chia nhỏ từng phép cộng. **Tách helper là phương tiện tăng khả năng hiểu, không phải mục tiêu số lượng lớp.**

## 9. Kiểm thử JUnit 5 dựa trên hợp đồng

Dùng bộ dữ liệu ở phần 6 để bảo vệ **giá trị đầu ra cụ thể**, thay vì chỉ đối chiếu “trước và sau ra cùng kết quả” trên vài trường hợp tùy ý.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class ShippingQuoteServiceTest {
    private final ShippingQuoteService service = new ShippingQuoteService();

    @ParameterizedTest
    @CsvSource({
            "0, false, false, 30000, 0, 0, 30000",
            "499999, false, false, 30000, 0, 0, 30000",
            "500000, false, false, 0, 0, 0, 0",
            "500001, false, false, 0, 0, 0, 0",
            "500000, true, false, 0, 20000, 0, 20000",
            "500000, false, true, 0, 0, 15000, 15000",
            "499999, true, true, 30000, 20000, 15000, 65000",
            "500000, true, true, 0, 20000, 15000, 35000"
    })
    void quotesMatchApprovedPolicy(
            long subtotal, boolean express, boolean remoteArea,
            long standard, long expressFee, long remoteFee, long total) {
        var expected = new ShippingQuoteService.Quote(
                standard, expressFee, remoteFee, total);

        assertEquals(expected, service.quote(subtotal, express, remoteArea));
    }

    @Test
    void invalidSubtotalIsRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> service.quote(-1L, false, false));
    }
}
~~~

Đoạn này dùng **JUnit Jupiter Params** cho kiểm thử tham số hóa. Nếu dự án chưa có dependency tương ứng, cần bổ sung vào cấu hình kiểm thử theo quy trình riêng; bài này không chạy build.

Các assertion trên bảo vệ:

- Biên **499.999 / 500.000 / 500.001**.
- Ba thành phần phí **và** tổng phí.
- Việc cộng hai phụ phí độc lập.
- Hành vi từ chối subtotal âm.

Một assertion chỉ kiểm tra **totalFeeVnd** không nhất thiết phát hiện trường hợp một thành phần phí sai nhưng bị thành phần khác bù lại. Khi client hiển thị từng khoản, **cấu trúc Quote cũng thuộc hợp đồng**.

## 10. Không chỉ kiểm thử đường thành công

Một refactor có thể giữ nguyên kết quả cho input thông thường nhưng đổi đường lỗi:

- Trước kia đầu vào âm bị từ chối trước khi truy vấn phụ thuộc; sau refactor lại truy vấn rồi mới từ chối.
- Trước kia một API trả lỗi **NOT_FOUND**; sau refactor lại trả null, dẫn tới lỗi khác ở caller.
- Trước kia khi thiếu quyền không đọc tài liệu; sau refactor đọc trước rồi mới ném exception.
- Trước kia đơn đã hủy không tạo sự kiện mới; sau refactor phát thêm sự kiện khi gọi lặp.

Vì vậy, ma trận hành vi cần bảo vệ phải có cả **đường được phép** và **đường phải dừng**.

| Tình huống | Hành vi cần bảo vệ | Assertion phù hợp |
| --- | --- | --- |
| Input hợp lệ | Kết quả đúng theo yêu cầu. | So sánh giá trị cụ thể và các trường có ý nghĩa. |
| Input sai kiểu/miền | Từ chối trước tác dụng phụ. | Loại lỗi, không ghi dữ liệu. |
| Không đủ quyền | Không truy cập dữ liệu ngoài phạm vi. | Phản hồi phù hợp và không gọi điểm đọc/ghi bảo vệ. |
| Phụ thuộc timeout | Không biến lỗi kỹ thuật thành kết quả nghiệp vụ giả. | Loại lỗi, trạng thái không bị sửa trái hợp đồng. |
| Gửi trùng yêu cầu | Không tạo tác dụng phụ lặp ngoài chính sách. | Dữ liệu/trạng thái và số lần thực thi có ý nghĩa. |
| Cập nhật đồng thời | Giữ bất biến trạng thái. | Kiểm thử tích hợp/transaction phù hợp. |

Điều quan trọng không phải **test càng nhiều loại ngoại lệ càng tốt**, mà là **test những thất bại có khả năng làm sai hợp đồng hoặc tạo rủi ro**.

## 11. Hành vi quan sát được bao gồm cả tác dụng phụ

Xem một ca sử dụng gửi thông báo sau khi xác nhận đơn:

- Nếu người dùng đã chọn nhận thông báo, gửi **một thông báo**.
- Nếu người dùng không chọn nhận, **không gửi**.
- Nếu orderId không hợp lệ, **không gửi** và báo lỗi đầu vào.

Đoạn Java 17 minh họa ranh giới có tác dụng phụ:

~~~java
import java.util.Objects;

public final class ShipmentNotification {
    @FunctionalInterface
    public interface Sender {
        void send(String orderId);
    }

    private final Sender sender;

    public ShipmentNotification(Sender sender) {
        this.sender = Objects.requireNonNull(sender);
    }

    public void notifyIfEnabled(String orderId, boolean optedIn) {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("invalid orderId");
        }

        if (optedIn) {
            sender.send(orderId);
        }
    }
}
~~~

Một refactor có thể chuyển điều kiện từ service sang adapter hoặc trích xuất helper. Nhưng nếu refactor khiến **sender.send** chạy cả khi optedIn = false, hành vi đã đổi dù phương thức vẫn trả **void** như cũ.

### Kiểm thử ghi nhận tác dụng phụ có ý nghĩa

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class ShipmentNotificationTest {
    @Test
    void optedInCustomerReceivesExactlyOneNotification() {
        List<String> sent = new ArrayList<>();
        var service = new ShipmentNotification(sent::add);

        service.notifyIfEnabled("order-42", true);

        assertEquals(List.of("order-42"), sent);
    }

    @Test
    void optedOutCustomerReceivesNothing() {
        List<String> sent = new ArrayList<>();
        var service = new ShipmentNotification(sent::add);

        service.notifyIfEnabled("order-42", false);

        assertEquals(List.of(), sent);
    }

    @Test
    void invalidInputNeverCallsSender() {
        List<String> sent = new ArrayList<>();
        var service = new ShipmentNotification(sent::add);

        assertThrows(IllegalArgumentException.class,
                () -> service.notifyIfEnabled("", true));
        assertEquals(List.of(), sent);
    }
}
~~~

Ở đây, kiểm tra số lần gửi **không phải phụ thuộc tùy tiện vào triển khai nội bộ**: số thông báo được phát đi chính là một phần kết quả mà hệ thống bên ngoài có thể quan sát.

Tuy nhiên, với hệ thống thật, **gọi Sender một lần không chứng minh nhà cung cấp giao tin đúng một lần**. Cần phân biệt lời gọi từ ứng dụng với kết quả giao thực tế, cơ chế retry và idempotency theo hợp đồng.

## 12. Thứ tự thao tác: lúc nào cần bảo vệ?

Có những thứ tự là chi tiết triển khai, có những thứ tự là yêu cầu an toàn.

**Thứ tự có ý nghĩa:**

~~~text
1. Xác thực danh tính
2. Kiểm tra quyền với tài nguyên
3. Đọc dữ liệu nhạy cảm
4. Trả nội dung đã được phép
~~~

Nếu refactor chuyển bước đọc lên trước kiểm tra quyền, **đường đi bảo mật đã thay đổi**. Một unit test chỉ assert HTTP 403 có thể không phát hiện việc đọc trái phép nếu dữ liệu đã vào bộ nhớ, log hoặc thành phần khác.

Trong các ca ghi dữ liệu, thứ tự hoặc tính nguyên tử có thể liên quan đến:

- Transaction commit/rollback.
- Ghi outbox và phát sự kiện.
- Thu tiền, hoàn tiền và đối soát.
- Ghi audit theo chính sách.
- Khóa tài nguyên và kiểm soát đồng thời.

**Thứ tự không có ý nghĩa theo hợp đồng** có thể được thay đổi: ví dụ hai phép tính thuần độc lập không gây tác dụng phụ được đảo thứ tự mà không làm đổi kết quả hay giới hạn tài nguyên.

Đừng viết test bắt buộc gọi một helper private trước helper khác nếu đó chỉ là cách thực hiện hiện tại. Test như vậy khiến refactor khó hơn mà không bảo vệ người dùng.

## 13. Xác định ranh giới: cái gì là hợp đồng, cái gì là nội bộ?

Phạm vi test nên gắn với **lớp ranh giới đủ ổn định**.

| Ranh giới | Điều thường cần kiểm chứng | Điều thường không nên khóa cứng |
| --- | --- | --- |
| **Hàm nghiệp vụ thuần** | Giá trị, miền đầu vào, ngoại lệ có ý nghĩa. | Số helper, tên biến local, từng nhánh private. |
| **Application service** | Trạng thái và tác dụng phụ nghiệp vụ. | Thứ tự mọi lời gọi mock không quan trọng. |
| **HTTP API** | Status, schema, mã lỗi, trường dữ liệu và tương thích. | Class/controller nội bộ nào thực hiện mapping. |
| **Persistence** | Dữ liệu được commit đúng, bất biến đồng thời, rollback. | Cú pháp SQL cụ thể nếu không phải hợp đồng hiệu năng hoặc schema. |
| **Message consumer** | Quy tắc xác nhận message, idempotency, xử lý lỗi và retry. | Cách đặt tên biến đếm hoặc cấu trúc helper. |
| **Thư viện công khai** | Chữ ký, kiểu dữ liệu, ngoại lệ/đặc tính đã cam kết. | Cách tổ chức nội bộ mà caller không quan sát. |

Một refactor có thể giữ đầu ra Java như cũ nhưng đổi **JSON field, HTTP status hoặc source/binary compatibility** của thư viện. Vì thế, với phần mềm có nhiều người dùng, cần cả **unit tests** và **contract/integration tests** theo ranh giới.

Không có yêu cầu rằng mọi chi tiết công khai đều phải bất biến vĩnh viễn. Khi cần đổi hợp đồng, phải **gắn nhãn đó là thay đổi hành vi/hợp đồng riêng**, đánh giá tương thích và có kế hoạch chuyển đổi.

## 14. Đặc tả, hệ thống hiện tại và hành vi thực sự được dùng

Đối với mã cũ, không phải lúc nào cũng có tài liệu hợp đồng tốt. Khi ấy, có ba nguồn thông tin cần đối chiếu:

1. **Đặc tả mong muốn:** quy tắc nghiệp vụ, tài liệu API, quyết định đã được phê duyệt.
2. **Hành vi hiện tại:** điều mã thực sự làm với dữ liệu đầu vào và trạng thái đang có.
3. **Hành vi mà bên sử dụng đang phụ thuộc:** các mẫu dùng thật của client, công việc vận hành và tích hợp liên quan.

Ba nguồn có thể không trùng nhau. Ví dụ API vốn cam kết sort tăng dần, nhưng bản triển khai hiện trả thứ tự ngẫu nhiên; một client đang tự sort lại. Refactor không nên bất cẩn làm thay đổi hợp đồng mà các bên đang sử dụng, nhưng cũng **không nên chuẩn hóa lỗi** chỉ vì nó đang tồn tại.

Cần phân loại từng bất đồng:

- **Hợp đồng rõ, implementation sai:** ghi bug, test theo hợp đồng và sửa có chủ đích.
- **Hợp đồng thiếu, hành vi ổn định và có client phụ thuộc:** điều tra, làm rõ hợp đồng, cân nhắc compatibility.
- **Hành vi vô tình, không có yêu cầu giữ:** có thể thay khi đã đánh giá tác động; tránh cam kết bừa “giữ nguyên mọi byte”.
- **Không thể xác minh:** ghi rủi ro và giới hạn bằng chứng, không tự suy đoán là an toàn.

**Bảo vệ hành vi không có nghĩa khóa cứng mọi bug của phiên bản cũ.**

## 15. Characterization tests khi mã cũ chưa có đặc tả đầy đủ

**Characterization test** (kiểm thử ghi nhận hành vi hiện tại) giúp khám phá cách một thành phần cũ thực sự phản hồi ở những trường hợp quan trọng trước khi thay cấu trúc.

Quy trình:

1. Chọn input và trạng thái **đại diện cho cách dùng thật**.
2. Ghi lại output, ngoại lệ và tác dụng phụ của phiên bản hiện tại.
3. So sánh quan sát với các yêu cầu và quy tắc đã biết.
4. Phân loại quan sát là **hợp đồng cần giữ**, **bug cần sửa riêng** hay **hành vi chưa rõ**.
5. Chỉ biến các hành vi cần bảo vệ thành assertion dài hạn.
6. Sau refactor, chạy lại để phát hiện sai lệch bất ngờ.

Ví dụ, nếu hệ thống cũ với subtotal = 500.000 trả 30.000 dù yêu cầu nói miễn phí, một characterization test có thể ghi nhận thực tế ấy **để hiểu tình trạng ban đầu**, nhưng không nên trở thành test chuẩn bắt buộc giữ phí 30.000 mãi mãi.

### Golden master và snapshot: dùng có chọn lọc

Một kỹ thuật khác là lưu kết quả của phiên bản cũ thành **golden file** hoặc snapshot rồi so sánh sau refactor. Nó có ích khi output lớn và khó liệt kê thủ công, nhưng có rủi ro:

- Snapshot có thể chứa **bug hiện tại**.
- Timestamp, ID ngẫu nhiên, thứ tự không được cam kết hoặc dữ liệu môi trường làm test nhiễu.
- Người review có thể chấp nhận snapshot mới mà chưa hiểu khác biệt.
- Snapshot có thể chứa thông tin nhạy cảm nếu sao chép dữ liệu thật.

Do đó, chỉ snapshot **những phần đầu ra có ý nghĩa**, chuẩn hóa dữ liệu biến động theo hợp đồng, kiểm tra quyền riêng tư và review từng khác biệt. Snapshot là bằng chứng bổ sung, không phải nguồn chân lý tuyệt đối.

## 16. Khi số ca kiểm thử là hữu hạn: chọn phạm vi theo rủi ro

Không thể kiểm thử mọi đầu vào và mọi lịch chạy. Cần ưu tiên vùng **dễ sai, hậu quả cao hoặc đang chịu ảnh hưởng bởi refactor**.

Một ma trận lựa chọn:

| Nhóm ưu tiên | Dữ liệu/tình huống nên có | Vì sao |
| --- | --- | --- |
| **Rất cao** | Quyền truy cập, tiền, dữ liệu, transaction, idempotency và ngưỡng nghiệp vụ. | Sai có thể gây hậu quả lớn hoặc khó hoàn tác. |
| **Cao** | Điều kiện boolean, null, danh sách rỗng, biên số, ngoại lệ và phụ thuộc lỗi. | Dễ sai khi chuyển nhánh, trích xuất method hoặc đổi thứ tự. |
| **Trung bình** | Ca sử dụng phổ biến, biến thể cấu hình và dữ liệu đại diện. | Bảo vệ hành vi thường xuyên được dùng. |
| **Theo bối cảnh** | Unicode, timezone, phân phối tải, timeout, thứ tự và tương thích phiên bản. | Quan trọng khi chúng là một phần hợp đồng của thành phần. |
| **Thấp hơn** | Tên biến local, số helper hoặc cách format code. | Không phải hành vi cần được bảo vệ bằng assertion. |

Đây là **gợi ý lập kế hoạch**, không phải công thức điểm số. Nếu refactor một thuật toán mã hóa, vùng ưu tiên có thể khác hoàn toàn so với một hàm tính phí đơn giản.

Một bộ kiểm thử nhỏ nhưng có ca đúng **499.999/500.000/500.001** có thể mạnh hơn hàng trăm ca đều nằm xa ngưỡng.

## 17. Chọn mức kiểm thử phù hợp

Hệ thống thực thường cần **nhiều mức bằng chứng**, nhưng không nhất thiết mỗi yêu cầu phải có mọi mức.

| Mức kiểm thử | Phạm vi bảo vệ | Ví dụ |
| --- | --- | --- |
| **Unit test** | Quy tắc thuần, quyết định, tiền điều kiện và giá trị trả về. | ShippingQuoteService ở phần 9. |
| **Component/service test** | Điều phối, dữ liệu, ranh giới phụ thuộc và tác dụng phụ tại service. | ShipmentNotification với Sender giả. |
| **Integration test** | CSDL, framework, transaction, serializer và tương tác kỹ thuật thật. | Rollback khi ghi thất bại; mapping entity. |
| **Contract test** | Hợp đồng mà consumer/provider hoặc client dựa vào. | JSON schema, mã lỗi và đường API. |
| **End-to-end test** | Một luồng người dùng quan trọng qua nhiều thành phần. | Đặt hàng, thanh toán và nhận kết quả. |
| **Performance/load test** | Độ trễ, thông lượng và giới hạn tài nguyên đã cam kết. | p95 và queue wait tại tải đại diện. |

**Không nên chỉ đếm số test.** Hãy chọn mức test đủ để quan sát hành vi cần bảo vệ với chi phí chạy và bảo trì hợp lý.

Một luồng chạy thật có thể khác unit test vì annotation, proxy, cấu hình DI, serializer hoặc transaction. Đặc biệt khi refactor di chuyển phương thức qua lớp hoặc module, kiểm thử tích hợp thường cần thiết để xác minh hành vi framework.

## 18. Tránh test khóa cứng chi tiết triển khai

Một kiểm thử dễ vỡ có thể trông như sau về mặt ý tưởng:

~~~text
Khi gọi quote(...):
  - bắt buộc gọi private helper validateSubtotal đúng một lần
  - bắt buộc gọi private helper calculateStandardFee đúng một lần
  - bắt buộc tính phụ phí express trước phụ phí remote
~~~

Nếu các bước thuần này không phải một phần hợp đồng, test đang **khóa cấu trúc nội bộ**. Sau refactor, tên helper và thứ tự tính các phép cộng độc lập có thể thay mà kết quả vẫn đúng.

So sánh với assertion tốt hơn:

~~~text
Input:
  subtotalVnd = 500000
  express = true
  remoteArea = true

Expected:
  standardFeeVnd = 0
  expressSurchargeVnd = 20000
  remoteSurchargeVnd = 15000
  totalFeeVnd = 35000
~~~

Test thứ hai giữ **điều caller thực sự cần**, cho phép implementation tiếp tục được cải thiện.

Ngoại lệ hợp lý: nếu số lần gọi đến API thanh toán là một phần bảo đảm chống thu tiền trùng, thì **số lần gọi là hành vi quan sát được**, không phải chi tiết mock tùy tiện.

## 19. Quan sát thay đổi khi có trạng thái và concurrency

Một phương thức đọc và ghi dữ liệu khác hẳn hàm thuần. Khi refactor, có thể vô tình đổi:

- **Transaction boundary:** dữ liệu từng commit cùng nhau giờ bị tách.
- **Atomicity:** hai bước từng được cập nhật nguyên tử giờ có khoảng trống cạnh tranh.
- **Isolation:** quyết định dùng dữ liệu đã đọc có thể lỗi thời khi người khác cập nhật.
- **Locking:** thay thứ tự lấy lock có thể tạo deadlock.
- **Retry:** chuyển một lời gọi vào khối retry có thể khiến tác dụng phụ chạy lặp.
- **Idempotency:** xử lý lại cùng message có thể tạo thêm bản ghi.
- **Event ordering:** sự kiện phát ra trước khi dữ liệu được commit.
- **Failure recovery:** lỗi sau một thao tác thành công có thể để lại trạng thái dở dang.

Ví dụ một bất biến: **số lượng tồn kho không được âm**. Kiểm thử tuần tự với một request có thể xanh trong khi hai request đồng thời vẫn bán quá số lượng có sẵn.

Khi refactor chạm tới những vùng này, phạm vi bảo vệ cần được **mở rộng tới transaction, thao tác lưu trữ và kịch bản cạnh tranh**, không chỉ thêm vài unit test cho hàm tính toán.

### Không phải mọi concurrency đều cần test ngẫu nhiên

Kiểm thử bằng Thread.sleep và hy vọng hai luồng va nhau có thể rất kém ổn định. Ưu tiên cơ chế đồng bộ có thể kiểm soát (barrier/latch), test tích hợp phù hợp với CSDL và xác nhận **bất biến cuối cùng**.

Đừng khẳng định một refactor “không đổi hành vi” nếu đã di chuyển ranh giới transaction mà chưa kiểm chứng tác dụng của framework.

## 20. Ràng buộc hiệu năng và tài nguyên có thuộc hành vi cần giữ không?

Một refactor thuần cấu trúc có thể làm tăng số truy vấn CSDL từ 1 lên 100, hoặc thay cách đọc file theo luồng bằng cách tải toàn bộ vào bộ nhớ. Giá trị trả về vẫn đúng, nhưng chi phí vận hành có thể thay đổi đáng kể.

Nếu hệ thống có **SLO, giới hạn bộ nhớ, giới hạn số lời gọi phụ thuộc hoặc ngân sách thời gian**, những ràng buộc đó cần được xem là **điều kiện chấp nhận** của refactor.

Những tín hiệu thường cần theo dõi:

- Độ trễ trung bình và p95/p99 ở tải đại diện.
- Số lần truy vấn và số byte truyền qua mạng.
- Số tác vụ đồng thời, hàng đợi và tỷ lệ từ chối.
- Bộ nhớ peak, allocation, thời gian GC.
- Timeout, retry và lượng tác dụng phụ phát sinh.
- Khác biệt theo kích thước đầu vào.

**Không nhất thiết phải bảo toàn từng nanosecond hoặc cùng số câu lệnh máy.** Mục tiêu là không làm vi phạm **đặc tính vận hành đã cam kết** hoặc gây hồi quy đáng kể ở đường quan trọng. Muốn kết luận cải thiện/suy giảm hiệu năng, phải đo với môi trường và workload có thể so sánh.

## 21. Quy trình thực hành trước và trong refactor

Một quy trình an toàn có thể đi theo các bước:

~~~mermaid
flowchart TD
    A["Xác định cấu trúc cần cải thiện"] --> B["Tìm caller và hợp đồng liên quan"]
    B --> C["Liệt kê hành vi và bất biến cần giữ"]
    C --> D["Chọn test theo rủi ro và xác định expected độc lập"]
    D --> E["Ghi baseline: test và quan sát vận hành phù hợp"]
    E --> F["Refactor một bước nhỏ"]
    F --> G["Chạy lại kiểm chứng và xem diff"]
    G --> H{"Hành vi có ngoài phạm vi thay đổi?"}
    H -- "Có" --> I["Hoàn tác/sửa hoặc tách thành thay đổi riêng"]
    I --> F
    H -- "Không" --> J["Review cấu trúc, hợp đồng và tiếp tục bước nhỏ"]
~~~

### Bước 1 — Tìm ranh giới và người tiêu thụ

Xác định lớp, method, endpoint hoặc consumer nào sử dụng phần đang sửa. Đừng chỉ tìm tên method trong một file nếu còn cấu hình framework, reflection, serializer hoặc API công khai.

### Bước 2 — Viết hợp đồng hiện hành

Mô tả input, output, nhánh lỗi, trạng thái và tác dụng phụ. Ghi cả bất biến và các đường không được phép.

### Bước 3 — Phân loại điểm chưa rõ

Điều nào được đặc tả, điều nào được suy từ code cũ, điều nào do client thật phụ thuộc? Với bug đã biết, quyết định sửa riêng để không lẫn với thay đổi cấu trúc.

### Bước 4 — Chọn test và dữ liệu có sức phát hiện sai lệch

Chọn biên, trường hợp lỗi, tương tác có ý nghĩa và mức test phù hợp. Đảm bảo expected được xác định độc lập.

### Bước 5 — Ghi baseline đáng tin

Trước khi sửa, ghi nhận test nào xanh/đỏ, hành vi nào chưa có bằng chứng và các giới hạn môi trường. Nếu baseline đã lỗi, không được quy mọi thất bại sau refactor cho thay đổi mới.

### Bước 6 — Thay từng bước nhỏ

Trích xuất helper, đổi tên nội bộ hoặc di chuyển trách nhiệm từng phần. Giữ phạm vi diff có thể review, tránh tiện tay đổi chính sách hoặc format cả module.

### Bước 7 — Kiểm chứng sau mỗi bước

Chạy những test phù hợp; xem raw diff; nếu refactor ảnh hưởng framework, transaction hoặc hợp đồng ngoài, bổ sung integration/contract test.

### Bước 8 — Đánh giá lợi ích thật

Mã có dễ đọc hơn không? Trách nhiệm và phụ thuộc rõ hơn không? Có tạo thêm lớp gián tiếp vô nghĩa không? Test có tiếp tục bảo vệ hợp đồng mà không khóa chi tiết nội bộ không?

Nếu câu trả lời chỉ là “LOC giảm”, chưa đủ để xác nhận refactor có ích.

## 22. Cách viết phạm vi bảo vệ trong pull request

Một mô tả PR tốt giúp reviewer biết **cần tìm điều gì có thể sai**:

~~~markdown
## Mục tiêu refactor
Tách bước tính phí tiêu chuẩn khỏi ShippingQuoteService.quote
để làm rõ trách nhiệm và giảm độ phức tạp điều kiện.

## Hành vi phải giữ
- Chữ ký quote(long, boolean, boolean) và kiểu Quote.
- Ngưỡng miễn phí tiêu chuẩn 500.000 VND.
- Phí tiêu chuẩn 30.000 VND dưới ngưỡng.
- Phụ phí giao nhanh 20.000 VND và vùng xa 15.000 VND.
- Tổng phí bằng tổng các thành phần.
- subtotal âm gây IllegalArgumentException.
- Không thêm tác dụng phụ.

## Ngoài phạm vi
- Không thay chính sách giá, hợp đồng API hoặc dữ liệu lưu trữ.
- Không thay cấu hình môi trường hoặc formatter toàn module.

## Bằng chứng cần đính kèm
- Ca biên 499.999 / 500.000 / 500.001.
- Các tổ hợp express và remoteArea.
- Ca đầu vào âm.
- Kết quả kiểm thử và phần diff liên quan.
~~~

Đây là **mẫu mô tả**. Khi áp dụng thực tế, cần ghi **kết quả test đã chạy**, không dùng một checklist chưa thực hiện làm bằng chứng hoàn tất.

## 23. Những lỗi thường gặp khi xác định phạm vi bảo vệ

| Sai lầm | Hệ quả | Cách cải thiện |
| --- | --- | --- |
| **Chỉ test happy path** | Bỏ sót lỗi biên, quyền, exception hoặc dữ liệu không hợp lệ. | Lập ma trận nhánh theo rủi ro. |
| **Expected lấy từ code cũ** | Bug hiện tại có thể bị đóng băng thành chuẩn. | Đối chiếu đặc tả và người sở hữu nghiệp vụ. |
| **Bảo vệ mọi lời gọi nội bộ** | Test vỡ khi chỉ đổi cấu trúc, làm refactor khó khăn. | Assert hợp đồng và tác dụng phụ quan sát được. |
| **Chỉ kiểm tra giá trị trả về** | Bỏ qua ghi dữ liệu, gửi thông báo trùng hoặc mất transaction. | Test cả trạng thái và tác dụng phụ quan trọng. |
| **Không xem consumer ngoài module** | Đổi API hoặc schema khiến tích hợp hỏng. | Tìm caller, contract và phiên bản được dùng. |
| **Gom bug fix vào refactor** | Không biết thay đổi nào làm hành vi khác. | Tách mục tiêu và test hoặc ghi ranh giới rõ. |
| **Không kiểm tra dữ liệu dùng chung** | Test phụ thuộc thứ tự, khó tái lập. | Fixture cô lập, clock và seed được kiểm soát. |
| **Giữ nguyên cả giới hạn kỹ thuật không cần thiết** | Đóng băng cấu trúc xấu dù không phải hợp đồng. | Phân biệt SLO/bất biến với chi tiết thực hiện. |
| **Không kiểm chứng concurrency** | Có thể phát sinh bán quá tồn kho, xử lý lặp. | Test tích hợp/atomicity phù hợp vùng rủi ro. |
| **Chỉ dựa vào coverage** | Các nhánh có chạy nhưng expected không phát hiện sai. | Test oracle rõ và ca phân biệt lỗi. |

Bất kỳ công cụ tự động nào cũng chỉ hỗ trợ một phần. **Người review phải xác định phần nào là hợp đồng có ý nghĩa và phần nào có thể thay đổi an toàn**.

## 24. Bài tập tự luyện

### Bài 1 — Đúng kết quả nhưng gửi trùng

Một refactor OrderConfirmationService giữ nguyên trạng thái đơn và HTTP response. Tuy nhiên, NotificationSender bị gọi hai lần khi đơn được xác nhận.

**Câu hỏi:** Refactor có giữ hành vi không? Bộ test nào thiếu?

**Gợi ý:** Không, nếu hợp đồng chỉ phát một thông báo. Cần kiểm tra tác dụng phụ ngoài giá trị trả về và xem đường retry/điều phối có làm lời gọi lặp.

### Bài 2 — Sửa bug trong lúc đổi cấu trúc

Phương thức cũ dùng điều kiện **subtotalVnd > 500_000** nhưng đặc tả yêu cầu **>= 500_000**. Người phát triển sửa toán tử trong cùng PR chia nhỏ phương thức.

**Câu hỏi:** Vì sao nên phân biệt hai mục tiêu?

**Gợi ý:** Đổi toán tử là sửa hành vi, còn chia nhỏ method là refactor. Cần có expected tại ngưỡng và làm rõ bản thay đổi nào bảo vệ hợp đồng, bản nào sửa kết quả sai.

### Bài 3 — Kiểm thử phụ thuộc helper

Sau refactor, một test thất bại vì phương thức private **computeFee** được đổi tên thành **calculateStandardFee**. Mọi phí trả về vẫn đúng và không có tác dụng phụ mới.

**Câu hỏi:** Test này bảo vệ điều gì?

**Gợi ý:** Có thể nó đang khóa chi tiết triển khai thay vì hợp đồng. Hãy kiểm tra kết quả công khai và các bất biến quan trọng.

### Bài 4 — Đổi transaction khi tách service

Một phương thức từng cập nhật đơn và lưu outbox trong cùng transaction. Sau refactor, hai thao tác được chuyển sang hai service khác nhau và commit riêng. Unit test tính trạng thái vẫn xanh.

**Câu hỏi:** Phạm vi bảo vệ nào còn thiếu?

**Gợi ý:** Tính nguyên tử khi ghi, khả năng phục hồi nếu lỗi giữa hai bước, retry và sự nhất quán với event. Cần test tích hợp cho ranh giới transaction.

### Bài 5 — API trả khác lỗi

Trước refactor, đầu vào thiếu productCode trả **400** với mã **INVALID_REQUEST**. Sau refactor, một NullPointerException bị catch chung và trả **500**. Không có lỗi với input hợp lệ.

**Câu hỏi:** Đây có phải refactor bảo toàn hợp đồng?

**Gợi ý:** Không. Đường lỗi và HTTP contract đã đổi. Cần test cho đầu vào không hợp lệ và mapping exception.

### Bài 6 — Thứ tự có hoặc không có ý nghĩa

Một hàm tính tổng hai khoản phí không có tác dụng phụ; sau refactor, hai phép tính độc lập bị đảo thứ tự. Một service khác đảo thứ tự từ **kiểm tra quyền → đọc dữ liệu** thành **đọc dữ liệu → kiểm tra quyền**.

**Câu hỏi:** Vì sao hai thay đổi thứ tự phải được đánh giá khác nhau?

**Gợi ý:** Thứ tự các phép tính thuần độc lập có thể không quan sát được, nhưng thứ tự bảo vệ truy cập ảnh hưởng đến quyền và khả năng lộ dữ liệu.

### Bài 7 — Code ít hơn, truy vấn nhiều hơn

Sau refactor, số dòng giảm 30%, nhưng mỗi dòng đơn hàng gây thêm một truy vấn CSDL; với đơn có nhiều mục, p95 tăng đáng kể.

**Câu hỏi:** Cần mở rộng phạm vi bảo vệ thế nào?

**Gợi ý:** Thêm bằng chứng về số truy vấn, hiệu năng ở tải đại diện và ngân sách latency. Giá trị đúng chưa bảo đảm thiết kế đạt yêu cầu vận hành.

### Bài 8 — Snapshot từ hệ thống cũ

Một golden file chứa cả timestamp, thứ tự ngẫu nhiên và một mã lỗi đã được xác định là bug. Nhóm định chấp nhận toàn bộ snapshot làm expected bắt buộc.

**Câu hỏi:** Rủi ro nào phát sinh?

**Gợi ý:** Có thể đóng băng bug và dữ liệu biến động không thuộc hợp đồng. Cần phân loại phần nào được bảo vệ, chuẩn hóa nguồn bất định, và chuyển sửa bug sang thay đổi có chủ đích.

## 25. Checklist trước khi bắt đầu một refactor

Hãy kiểm tra nhanh:

1. **Mục tiêu cấu trúc là gì?** Có một vấn đề dễ hiểu, dễ thay đổi hoặc phụ thuộc cần cải thiện không?
2. **Ai sử dụng phần đang đổi?** Đã tìm đúng caller và ranh giới công khai chưa?
3. **Đầu vào và kết quả nào thuộc hợp đồng?** Có giá trị biên và dữ liệu không hợp lệ không?
4. **Đường thất bại nào quan trọng?** Ngoại lệ, mã lỗi, không đủ quyền, phụ thuộc lỗi?
5. **Có trạng thái và tác dụng phụ không?** Test có xác minh điều phải xảy ra và điều phải không xảy ra?
6. **Có bất biến transaction, đồng thời hoặc idempotency không?**
7. **Hợp đồng vận hành nào cần giữ?** Tài nguyên, deadline, độ trễ hoặc số lời gọi phụ thuộc?
8. **Có bug đã biết trong code cũ không?** Đã phân loại và có kế hoạch sửa riêng chưa?
9. **Expected được xác định từ đâu?** Đặc tả độc lập hay copy output hiện tại?
10. **Mức test nào phù hợp?** Unit, component, integration, contract hoặc end-to-end?
11. **Test có khóa chi tiết nội bộ không?** Có thể đổi helper mà vẫn xanh nếu hợp đồng đúng không?
12. **Baseline và tiêu chí hoàn tất đã rõ chưa?** Có thể chứng minh refactor không đổi hành vi ngoài phạm vi không?

Không phải một refactor nhỏ đều cần hàng trăm test. Cần **bằng chứng tương xứng với rủi ro và những ranh giới thực sự bị chạm tới**.

---

**Ghi nhớ:** Trước khi tái cấu trúc, hãy xác định **hành vi quan sát được theo hợp đồng** cần giữ, thay vì chỉ nhìn vào những dòng code sẽ sửa. Bảo vệ **đầu ra, tiền điều kiện, đường lỗi, trạng thái, tác dụng phụ, quyền, đồng thời và các giới hạn vận hành có ý nghĩa**, nhưng đừng khóa cứng tên helper hoặc cách chia nội bộ. Khi có bug đã biết, hãy phân biệt rõ **sửa hành vi** với **refactor giữ hành vi**. Một refactor tốt không chỉ làm mã dễ hiểu hơn mà còn có **bằng chứng cụ thể rằng điều quan trọng với người dùng và các bên tích hợp vẫn đúng**.
