# Mã nguồn, kiểm thử và tài liệu phục vụ các nhu cầu khác nhau

Giả sử một lập trình viên mới tiếp nhận chức năng hủy lịch. Người đó đọc mã Java và thấy điều kiện “còn ít nhất 24 giờ trước lúc bắt đầu”. Bộ kiểm thử có trường hợp đúng 24 giờ và trước 24 giờ một giây. Nhưng tài liệu sản phẩm lại viết “được hủy miễn phí trước ngày diễn ra sự kiện”. Ba nguồn thông tin có vẻ liên quan đến cùng một chức năng, song **không trả lời cùng một câu hỏi**; thậm chí chúng đang mô tả những quy tắc khác nhau.

Trong module **CODE_QUALITY_FUNDAMENTALS**, mục tiêu là hiểu các thuộc tính giúp mã nguồn **đáng tin cậy, dễ hiểu và dễ thay đổi**. Thuộc chương **Tài liệu**, bài này làm rõ vai trò bổ sung của **mã nguồn**, **kiểm thử** và **tài liệu**. Nếu hiểu đúng nhiệm vụ của từng loại, nhóm phát triển có thể giải thích hệ thống rõ ràng hơn, phát hiện bất đồng giữa ý định và triển khai sớm hơn, đồng thời thay đổi phần mềm mà không khiến người sử dụng hoặc đồng nghiệp phải đoán.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt câu hỏi mà mã nguồn, kiểm thử và các loại tài liệu thường trả lời tốt nhất.
- Giải thích vì sao **mã đang chạy**, **test đang xanh** và **tài liệu được công bố** có thể chưa đồng nghĩa hệ thống đáp ứng đúng yêu cầu.
- Trình bày cùng một quy tắc nghiệp vụ bằng **Java**, **JUnit 5** và **tài liệu hợp đồng** mà không sao chép vô ích mọi chi tiết.
- Nhận diện loại thông tin nên nằm trong bình luận, API reference, README, tài liệu kiến trúc, ADR hoặc runbook.
- Xây dựng cách cập nhật mã, kiểm thử và tài liệu **cùng nhau** khi hành vi hoặc hợp đồng thay đổi.

## 1. Ba nguồn thông tin, ba mục đích chính

Khi tìm hiểu một hệ thống, người đọc thường hỏi ít nhất ba loại câu hỏi:

1. **Hệ thống thực hiện bằng cách nào?** Cần xem mã nguồn và cấu hình đang được triển khai.
2. **Bằng chứng nào cho thấy các hành vi quan trọng hoạt động như mong đợi?** Cần xem kiểm thử, dữ liệu kiểm thử, các assertion và kết quả chạy trong môi trường phù hợp.
3. **Hệ thống được thiết kế để phục vụ điều gì, sử dụng ra sao và tại sao chọn cách này?** Cần xem yêu cầu đã xác nhận, tài liệu hợp đồng, hướng dẫn sử dụng, quyết định thiết kế và tài liệu vận hành.

| Góc nhìn | Mã nguồn | Kiểm thử | Tài liệu |
| --- | --- | --- | --- |
| Câu hỏi mạnh nhất | *Chương trình thực thi như thế nào?* | *Trong tình huống đã kiểm tra, điều gì phải xảy ra?* | *Mục đích, hợp đồng, bối cảnh và cách sử dụng là gì?* |
| Nội dung điển hình | Kiểu, luồng xử lý, thuật toán, cấu hình, tích hợp | Input, expected output, lỗi, bất biến, tương tác | Quy tắc nghiệp vụ, API, giới hạn, hướng dẫn, quyết định, sơ đồ |
| Ai thường cần? | Lập trình viên, người review và người điều tra lỗi | Lập trình viên, QA, CI, người review | Người dùng API, vận hành, người mới, sản phẩm và người bảo trì |
| Điểm mạnh | Thể hiện hành vi được cài đặt | Tạo bằng chứng có thể chạy lại cho các trường hợp cụ thể | Truyền đạt ý định, lý do và ngữ cảnh ngoài mã |
| Giới hạn | Không tự chứng minh yêu cầu là đúng; “vì sao” có thể bị ẩn | Không bao phủ hết mọi trạng thái hay môi trường | Có thể lỗi thời hoặc không khớp với hệ thống thật |

**Ba loại không thay thế nhau.** Mã dễ đọc không giải thích hết lịch sử quyết định. Test xanh không chứng minh mọi trường hợp được hỗ trợ. Tài liệu rõ ràng không khiến phần triển khai tự động tuân thủ đúng những gì đã viết.

## 2. Mã nguồn cho biết hành vi được cài đặt

Mã nguồn có nhiệm vụ chính là **thực hiện hành vi**. Một lớp Java có tên, kiểu dữ liệu và cấu trúc hợp lý có thể cho người đọc biết điều gì được tính toán, dữ liệu đi qua đâu, nhánh nào từ chối yêu cầu và thành phần nào chịu trách nhiệm.

Ví dụ, nhóm sản phẩm xác nhận **chính sách giả định** sau cho việc hủy lịch:

- Người đặt lịch được hủy **miễn phí** nếu gửi yêu cầu **trước hoặc đúng 24 giờ** so với thời điểm bắt đầu.
- “24 giờ” nghĩa là **24 giờ thực trôi qua**, không phải “trước ngày hôm trước” theo lịch địa phương.
- Nếu yêu cầu đến muộn hơn ranh giới đó, chức năng trả về **không đủ điều kiện miễn phí**.
- Hàm này chỉ quyết định **đủ điều kiện hủy miễn phí hay không**; nó không trực tiếp hủy lịch, hoàn tiền hoặc ghi cơ sở dữ liệu.

Một cách cài đặt Java 17 dễ đọc:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;

public final class FreeCancellationPolicy {
    private static final Duration REQUIRED_NOTICE = Duration.ofHours(24);

    private FreeCancellationPolicy() {
    }

    public static boolean isEligible(
            Instant startsAt,
            Instant cancellationRequestedAt) {
        Objects.requireNonNull(startsAt, "startsAt");
        Objects.requireNonNull(
            cancellationRequestedAt, "cancellationRequestedAt"
        );

        Duration notice = Duration.between(
            cancellationRequestedAt,
            startsAt
        );
        return notice.compareTo(REQUIRED_NOTICE) >= 0;
    }
}
~~~

Nhìn vào mã, người đọc biết rằng:

- Đầu vào dùng `Instant`, tức là hai mốc thời gian tuyệt đối.
- Quy tắc so sánh một khoảng `Duration` với 24 giờ.
- Điều kiện `>= 0` sau phép so sánh cho phép trường hợp **đúng 24 giờ**.
- Hàm không truy cập đồng hồ hệ thống, repository hay tài nguyên ngoài; với cùng đầu vào hợp lệ, nó cho cùng kết quả.
- `null` bị từ chối thay vì được hiểu ngầm là “bây giờ” hoặc “không có hạn”.

Tuy nhiên, **mã chưa trả lời vì sao chọn 24 giờ** chứ không phải 12 hoặc 48 giờ; ai quyết định chính sách; chính sách áp dụng cho loại lịch nào; trường hợp khách hàng đặc biệt có ngoại lệ không. Những thông tin ấy thuộc về **hợp đồng và quyết định nghiệp vụ**.

### Tên rõ nghĩa tốt hơn bình luận lặp lại câu lệnh

Một bình luận như:

~~~java
// So sánh notice với REQUIRED_NOTICE.
return notice.compareTo(REQUIRED_NOTICE) >= 0;
~~~

ít giúp ích vì chỉ diễn đạt lại Java bằng tiếng Việt. Nếu có điểm không hiển nhiên cần ghi lại, bình luận có thể giải thích **lý do**:

~~~java
// Chính sách yêu cầu 24 giờ thực trôi qua, không lấy ngày
// địa phương làm ranh giới; do đó dùng Instant và Duration.
~~~

Những lý do có giá trị dài hạn vẫn nên được ghi trong tài liệu chính sách hoặc bản ghi quyết định phù hợp, vì chúng có thể liên quan đến nhiều đoạn mã và nhiều người đọc ngoài lập trình viên.

## 3. Kiểm thử minh họa và kiểm chứng hợp đồng

Kiểm thử hữu ích không chỉ chạy phương thức; nó cần so sánh **kết quả thực tế** với **kết quả mong đợi độc lập từ quy tắc**.

Với thời điểm bắt đầu cố định `2026-12-01T15:00:00Z`, các tình huống quan trọng gồm:

| Thời điểm yêu cầu hủy (UTC) | Khoảng trước lúc bắt đầu | Đủ điều kiện miễn phí? |
| --- | --- | --- |
| 2026-11-30 14:59:59 | 24 giờ 1 giây | Có |
| 2026-11-30 15:00:00 | Đúng 24 giờ | Có |
| 2026-11-30 15:00:01 | 23 giờ 59 phút 59 giây | Không |
| 2026-12-01 15:00:00 | Đúng giờ bắt đầu | Không |

Kiểm thử JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class FreeCancellationPolicyTest {
    private static final Instant STARTS_AT =
        Instant.parse("2026-12-01T15:00:00Z");

    @ParameterizedTest
    @CsvSource({
        "2026-11-30T14:59:59Z, true",
        "2026-11-30T15:00:00Z, true",
        "2026-11-30T15:00:01Z, false",
        "2026-12-01T15:00:00Z, false"
    })
    void followsFreeCancellationBoundary(
            String requestedAtText,
            boolean expected) {
        boolean actual = FreeCancellationPolicy.isEligible(
            STARTS_AT,
            Instant.parse(requestedAtText)
        );
        assertEquals(expected, actual);
    }

    @Test
    void rejectsMissingTime() {
        assertThrows(
            NullPointerException.class,
            () -> FreeCancellationPolicy.isEligible(STARTS_AT, null)
        );
    }
}
~~~

Bộ kiểm thử này nói rõ **những tình huống nào đã được kiểm tra** và kết quả mong đợi cho từng tình huống. Nó rất hữu ích khi ai đó thay toán tử `>=` thành `>` hoặc hiểu sai ranh giới 24 giờ.

Tuy nhiên, kiểm thử cũng có giới hạn:

- Nếu cả mã và test đều dùng 24 giờ nhưng chính sách thật đã đổi thành 12 giờ, test có thể vẫn xanh trong khi hành vi không còn đáp ứng yêu cầu.
- Nếu ứng dụng truyền nhầm thời điểm từ múi giờ địa phương vào `Instant`, unit test của hàm thuần túy không tự phát hiện lỗi chuyển đổi ở tầng tích hợp.
- Nếu việc hủy thật cần kiểm tra quyền chủ sở hữu hoặc cập nhật database nguyên tử, bộ test này chưa kiểm chứng những hành vi đó.
- Tỷ lệ bao phủ dòng lệnh cao không chứng minh mọi tình huống nghiệp vụ, lỗi tích hợp hay rủi ro đều đã được kiểm tra.

**Kiểm thử là bằng chứng có phạm vi**, không phải bản sao có thể chạy của mọi thông tin về sản phẩm.

## 4. Tài liệu mô tả ý nghĩa và cách dùng hợp đồng

Người sử dụng API hoặc người phụ trách nghiệp vụ không nên phải đọc biểu thức `Duration.between(...)` để đoán chính sách. Một đoạn tài liệu hợp đồng có thể ghi:

> **Điều kiện hủy miễn phí:** Yêu cầu hủy phải được ghi nhận ít nhất **24 giờ thực trôi qua** trước thời điểm bắt đầu lịch. Yêu cầu đến đúng ranh giới 24 giờ vẫn đủ điều kiện; yêu cầu đến sau ranh giới không đủ điều kiện miễn phí. Quy tắc này chỉ xác định điều kiện miễn phí, không thực hiện thao tác hủy hay hoàn tiền. Cả hai thời điểm được biểu diễn bằng `Instant`.

Đoạn này giúp người gọi hiểu **ngữ nghĩa**, phạm vi và điều kiện biên mà không cần nhìn vào mã. Nó cũng tạo một tiêu chí rõ để reviewer so sánh với triển khai và test.

### Ba tầng tài liệu nên phân biệt

| Loại tài liệu | Câu hỏi cần trả lời | Nội dung thích hợp |
| --- | --- | --- |
| **Tài liệu hợp đồng / API reference** | Gọi thế nào, nhận gì, lỗi nào, cam kết gì? | Tham số, đơn vị, tiền điều kiện, kết quả, lỗi, ví dụ hợp lệ |
| **Tài liệu thiết kế / quyết định** | Vì sao chọn quy tắc và cấu trúc hiện tại? | Bối cảnh, phương án đã cân nhắc, đánh đổi, quyết định, hệ quả |
| **Tài liệu sử dụng / vận hành** | Cài đặt, cấu hình, triển khai và xử lý sự cố ra sao? | Điều kiện môi trường, lệnh chạy, sơ đồ luồng, giám sát, rollback |

Mỗi loại phục vụ người đọc và thời điểm khác nhau. Người tích hợp API có thể cần biết `null` bị từ chối; người review thiết kế cần biết vì sao dùng mốc thời gian tuyệt đối; người trực vận hành cần biết cách nhận diện lỗi chuyển đổi múi giờ từ dữ liệu đầu vào.

**Tài liệu hiệu quả không nhất thiết lặp lại từng câu lệnh Java.** Nó nên bổ sung những gì người đọc khó suy ra một cách đáng tin từ mã.

## 5. Ví dụ API reference đủ để sử dụng đúng

Nếu `FreeCancellationPolicy` được công bố như một thư viện Java, một mô tả ngắn cho người gọi có thể như sau:

| Thành phần | Hợp đồng |
| --- | --- |
| Phương thức | `FreeCancellationPolicy.isEligible(startsAt, cancellationRequestedAt)` |
| `startsAt` | Thời điểm lịch bắt đầu, kiểu `Instant`, bắt buộc |
| `cancellationRequestedAt` | Thời điểm hệ thống ghi nhận yêu cầu hủy, kiểu `Instant`, bắt buộc |
| Kết quả `true` | Khoảng cách tới lúc bắt đầu **ít nhất 24 giờ** |
| Kết quả `false` | Khoảng cách tới lúc bắt đầu **nhỏ hơn 24 giờ**, kể cả yêu cầu đến sau lúc bắt đầu |
| Đầu vào `null` | Bị từ chối bằng `NullPointerException` trong cài đặt minh họa |
| Tác dụng phụ | Không sửa dữ liệu, không hủy lịch, không gọi hệ thống ngoài |
| Giới hạn phạm vi | Không quyết định quyền hủy, phí thực thu, hoàn tiền hoặc chính sách ngoại lệ |

Để tránh hiểu nhầm, tài liệu nên phân biệt **đủ điều kiện hủy miễn phí** với **quyền được hủy**. Một người có thể không đủ điều kiện miễn phí nhưng vẫn được hủy với phí; người khác có thể đủ điều kiện theo thời gian nhưng không có quyền thao tác với lịch đó. Hai quyết định khác nhau không nên bị gộp thành một Boolean có ý nghĩa mơ hồ.

### Ví dụ Javadoc vừa đủ

~~~java
/**
 * Xác định điều kiện hủy miễn phí dựa trên thời gian thông báo.
 *
 * <p>Yêu cầu hủy phải đến trước hoặc đúng 24 giờ thực trôi qua
 * so với thời điểm bắt đầu. Phương thức không thực hiện việc hủy.
 *
 * @param startsAt thời điểm bắt đầu theo Instant
 * @param cancellationRequestedAt thời điểm ghi nhận yêu cầu hủy
 * @return true nếu khoảng thông báo ít nhất 24 giờ
 * @throws NullPointerException nếu một tham số là null
 */
public static boolean isEligible(
        Instant startsAt,
        Instant cancellationRequestedAt) {
    // Phần triển khai giống ví dụ trước.
}
~~~

Đây là **minh họa nội dung Javadoc**, không phải một phương thức thứ hai cần chép vào cùng lớp. Phần tài liệu tập trung vào **cam kết**, thay vì nhắc rằng hàm dùng toán tử `compareTo`. Trong một thư viện có public API, tài liệu ở nơi khai báo là điểm tra cứu quan trọng; nếu cần hướng dẫn dài hoặc quyết định kiến trúc, nên liên kết tới tài liệu khác.

## 6. Quyết định thiết kế lưu lại “vì sao”

Mã nguồn và test thường diễn đạt **cái gì**, nhưng không lưu trọn vẹn **tại sao**. Ví dụ, lựa chọn “24 giờ thực trôi qua” thay cho “trước ngày bắt đầu một ngày” có thể liên quan đến chính sách, công bằng giữa các múi giờ và tránh nhập nhằng khi chuyển giờ mùa hè.

Một **Architecture Decision Record (ADR)** hoặc bản ghi quyết định ngắn có thể có cấu trúc:

~~~text
Quyết định: Dùng 24 giờ thực trôi qua cho điều kiện hủy miễn phí
Trạng thái: Đã thống nhất (ví dụ minh họa)
Bối cảnh:
  Khách hàng đặt lịch ở nhiều múi giờ.
  "Ngày trước" dễ có nhiều cách hiểu khi đổi múi giờ/lịch.
Quyết định:
  So sánh Instant và Duration.ofHours(24).
  Trường hợp đúng 24 giờ vẫn đủ điều kiện.
Phương án đã cân nhắc:
  - So sánh theo ngày địa phương của địa điểm tổ chức
  - Dùng thời gian cố định 24 giờ thực trôi qua
Hệ quả:
  - Quy tắc biên rõ, kiểm thử được.
  - Cần chuyển đổi đúng thời điểm từ giao diện người dùng.
Nguồn xác nhận:
  Người phụ trách chính sách và phiên bản yêu cầu liên quan.
~~~

Bản ghi phải phản ánh **quyết định đã thực sự được phê duyệt**; đoạn trên chỉ là minh họa cách viết. Không nên tự biến một cách triển khai hiện tại thành “quyết định nghiệp vụ” nếu chưa có nguồn xác nhận.

ADR hữu ích khi có nhiều lựa chọn đều khả thi về kỹ thuật. Nếu sau này muốn đổi sang “trước 18:00 giờ địa phương ngày hôm trước”, người bảo trì sẽ hiểu vì sao có sự khác biệt và những chỗ cần đánh giá lại.

## 7. README và runbook phục vụ những người khác nhau

Một **README** của module thường nên trả lời: đây là thành phần gì, phạm vi trách nhiệm, điều kiện chạy, cách build/test, điểm vào chính và nơi tìm tài liệu chi tiết. Người mới có thể dùng nó như **bản đồ dẫn đường**, không phải bản sao của mọi class.

Ví dụ cấu trúc README:

~~~markdown
# Cancellation Policy

## Phạm vi
Tính điều kiện hủy miễn phí dựa trên mốc 24 giờ; không thực hiện hoàn tiền.

## Yêu cầu
JDK phù hợp với phiên bản đã được dự án xác nhận.

## Kiểm tra
Chạy bài test của chính sách theo lệnh chuẩn của dự án.

## Hợp đồng
Xem API reference và các tình huống biên.

## Quyết định
Xem bản ghi quyết định về cách hiểu "24 giờ".
~~~

Không nên tự điền một lệnh Gradle, Maven, biến môi trường hoặc đường dẫn triển khai **chưa được kiểm chứng**. Lệnh sai hoặc thông tin thiếu điều kiện có thể khiến README gây hại cho người mới hơn là giúp họ.

**Runbook** phục vụ người trực vận hành hoặc xử lý sự cố. Nếu có dịch vụ hủy lịch thực sự, runbook có thể ghi dấu hiệu sai múi giờ, cách phân biệt thời điểm yêu cầu do client gửi với thời điểm server ghi nhận, log/correlation ID cần xem, người phụ trách liên hệ và cách khôi phục an toàn. Đây là các thao tác phụ thuộc kiến trúc triển khai nên không thể suy ra đầy đủ từ phương thức `isEligible`.

Một thông tin rất quan trọng là **đối tượng đọc**. API reference phải hữu ích với người gọi thư viện; README giúp người bắt đầu; ADR giúp người thay đổi thiết kế; runbook giúp người xử lý hệ thống khi có sự cố. Cùng một thông tin có thể được liên kết giữa các tài liệu thay vì chép lặp toàn bộ.

## 8. Khi ba nguồn thông tin mâu thuẫn, tin vào đâu?

Không thể áp dụng máy móc quy tắc “mã luôn đúng”, “test luôn đúng” hoặc “tài liệu luôn đúng”.

Giả sử mã đang kiểm tra 24 giờ, test cũng kỳ vọng 24 giờ, nhưng tài liệu chính sách được phê duyệt gần đây quy định 12 giờ. Mã và test đang đồng nhất với nhau, song có thể **cùng sai so với yêu cầu mới**.

Ngược lại, nếu tài liệu chưa được cập nhật sau thay đổi chính sách được chấp thuận, người đọc tài liệu có thể đang dựa vào phiên bản cũ; không nên vội sửa mã theo tài liệu lỗi thời.

Quy trình giải quyết:

1. **Xác định phiên bản và thời điểm hiệu lực.** Mã chạy trong bản phát hành nào, test gắn với commit nào, tài liệu áp dụng từ ngày nào?
2. **Phân biệt hiện trạng và yêu cầu.** Mã cho biết hệ thống đang làm gì; tài liệu được phê duyệt cho biết điều được cam kết; test thể hiện những trường hợp đã được chọn để kiểm chứng.
3. **Tìm nguồn quyết định có thẩm quyền.** Đối chiếu với người phụ trách nghiệp vụ, hợp đồng API, quyết định thiết kế hoặc yêu cầu đã xác nhận.
4. **Phân loại sai khác.** Bug triển khai, test viết sai kỳ vọng, tài liệu lỗi thời, thay đổi chính sách có chủ đích hoặc yêu cầu chưa rõ.
5. **Đồng bộ có kiểm chứng.** Cập nhật phần cần sửa, bổ sung ca hồi quy và ghi lại phạm vi ảnh hưởng.

### Ma trận ví dụ

| Mã | Test | Tài liệu | Cần làm gì? |
| --- | --- | --- | --- |
| 24 giờ | 24 giờ | 24 giờ | Vẫn cần xác nhận đây là chính sách còn hiệu lực |
| 24 giờ | 24 giờ | 12 giờ | Kiểm tra ngày hiệu lực và phê duyệt; có thể cả mã lẫn test cần đổi |
| 12 giờ | 24 giờ | 12 giờ | Test có thể lỗi thời; xác minh trước khi đổi expected |
| 24 giờ | 12 giờ | 12 giờ | Mã có thể chưa đáp ứng yêu cầu; sửa và kiểm thử hồi quy |
| 12 giờ | 12 giờ | 24 giờ | Tài liệu có thể chưa cập nhật; kiểm tra nguồn và bản phát hành |

**Sự nhất quán là cần thiết nhưng chưa đủ**: ba nguồn cùng mô tả một hành vi sai vẫn có thể tạo cảm giác an toàn giả tạo.

## 9. Tài liệu nào nên sống gần mã, tài liệu nào cần tách riêng?

Một nguyên tắc hữu ích là đặt thông tin ở nơi **người cần nó có khả năng tìm thấy và duy trì nó**.

| Nội dung | Vị trí thường phù hợp | Lý do |
| --- | --- | --- |
| Hợp đồng phương thức public | Javadoc, API reference hoặc sơ đồ hợp đồng được liên kết | Gần chữ ký và người dùng API |
| Giải thích tại sao có một điều kiện không hiển nhiên | Bình luận ngắn + liên kết quyết định nếu cần | Giúp người đang đọc đúng đoạn mã |
| Quy tắc nghiệp vụ bao trùm nhiều lớp | Tài liệu yêu cầu/chính sách với chủ sở hữu rõ | Tránh bị trộn vào một class hoặc một test |
| Những tình huống cụ thể đã kiểm chứng | Test với tên rõ nghĩa, test data, báo cáo CI | Có thể thực thi lại, giúp review thay đổi |
| Cách chạy dự án và tìm điểm vào | README / hướng dẫn phát triển | Dành cho người mới và người bảo trì |
| Lý do chọn kiến trúc hoặc giao thức | ADR / tài liệu thiết kế | Ghi bối cảnh và đánh đổi |
| Cách điều tra và phục hồi sự cố | Runbook / tài liệu vận hành | Phù hợp với hoạt động khi triển khai |
| Thay đổi ảnh hưởng người dùng hay tích hợp | Changelog / release notes / migration guide | Giúp người ngoài nhóm điều chỉnh cách sử dụng |

Không cần tạo tất cả loại tài liệu cho một thư viện nhỏ. Chọn tài liệu theo **độ phức tạp của hệ thống, rủi ro, đối tượng đọc và nhu cầu thay đổi**. Một README ngắn, một bộ test dễ hiểu và Javadoc chính xác có thể đủ với một API đơn giản; một dịch vụ thanh toán nhiều tích hợp có thể cần ADR và runbook riêng.

## 10. Tránh trùng lặp thông tin làm tài liệu nhanh lỗi thời

Sao chép nguyên quy tắc sang README, wiki, comment, tài liệu API, ghi chú triển khai và cả test dưới nhiều cách diễn đạt sẽ tạo chi phí đồng bộ. Khi chính sách đổi từ 24 giờ sang 12 giờ, mỗi bản sao trở thành một nơi có thể bị quên.

Giải pháp không phải xóa mọi mô tả trùng nhau. **Một số lặp lại có chủ đích** vẫn cần thiết:

- Test phải chứa expected rõ ràng và độc lập, dù cùng quy tắc nghiệp vụ được giải thích trong tài liệu.
- API reference cần đủ nội dung để người gọi hiểu hợp đồng mà không bị buộc phải đọc ADR.
- Bình luận gần đoạn mã có thể giúp giải thích một quyết định đặc biệt dù đã có tài liệu dài hơn.

Điều cần tránh là **nhiều nguồn cùng tự nhận là nơi duy nhất quy định chính sách** nhưng không có liên kết, phiên bản hoặc chủ sở hữu.

Một cách tổ chức thực tế:

~~~text
Yêu cầu/chính sách được xác nhận
          |
          +----> API reference: cam kết dành cho người gọi
          |
          +----> Mã nguồn: triển khai hành vi
          |
          +----> Test: các ví dụ và bất biến cần kiểm chứng
          |
          +----> ADR: lý do và đánh đổi của lựa chọn kỹ thuật
~~~

Các liên kết, ID yêu cầu, tên chính sách hoặc đường dẫn tài liệu phải đủ ổn định để người đọc **truy vết**. Tên file và cấu trúc có thể thay đổi, nên ưu tiên cơ chế quản lý tham chiếu phù hợp với dự án thay vì dựa vào một chuỗi đường dẫn không được bảo trì.

### Ví dụ tài liệu sinh tự động và tài liệu có thể chạy

Nếu dự án có khả năng sinh API reference từ chữ ký, annotation hoặc schema, nên tận dụng để tránh tự viết nhiều bản danh sách tham số. Nhưng bản sinh tự động chỉ chính xác trong **phần dữ liệu được mô tả ở nguồn sinh**; nó không tự suy ra lý do nghiệp vụ hoặc ngoại lệ chưa khai báo.

Ví dụ mã trong tài liệu có thể được đưa vào kiểm tra biên dịch hoặc smoke test, nếu hệ thống build hỗ trợ. Điều đó phát hiện các ví dụ dùng API đã bị đổi tên. Nhưng **ví dụ biên dịch thành công không chứng minh phần mô tả nghiệp vụ xung quanh còn đúng**.

## 11. Khi một quy tắc thay đổi: cập nhật những gì?

Giả sử nhóm nghiệp vụ quyết định đổi ngưỡng hủy miễn phí từ **24 giờ** thành **12 giờ**, có ngày hiệu lực được xác nhận. Đây không chỉ là thay một hằng số trong Java.

Một checklist thay đổi:

1. **Xác nhận chính sách mới:** 12 giờ thực trôi qua hay 12 giờ theo quy ước khác? Đúng ranh giới vẫn được miễn phí không? Áp dụng cho lịch cũ hay chỉ lịch tạo mới?
2. **Cập nhật mã:** đổi giá trị ngưỡng ở thành phần có trách nhiệm và bảo đảm không có nơi nào tự tính một ngưỡng khác.
3. **Cập nhật test:** tạo tình huống trước, đúng và sau 12 giờ; giữ ca chứng minh 24 giờ nay vẫn đủ điều kiện nhưng không còn là ranh giới. Tách các test của chính sách cũ nếu hệ thống vẫn phải hỗ trợ lịch đã tạo trước ngày hiệu lực.
4. **Cập nhật tài liệu hợp đồng:** mô tả ngưỡng mới, phạm vi, đơn vị, quy tắc biên và lỗi.
5. **Cập nhật quyết định và lịch sử:** ghi bối cảnh, người xác nhận và hệ quả của thay đổi; không âm thầm viết lại lịch sử ADR mà không để lại dấu vết.
6. **Cập nhật tài liệu người dùng/vận hành:** nếu API, giao diện, vận hành hoặc xử lý ngoại lệ bị ảnh hưởng, sửa các hướng dẫn liên quan.
7. **Đánh giá tương thích và triển khai:** lịch hiện có, ứng dụng khách cũ, cache, phiên bản song song và ngày hiệu lực có thể đòi hỏi kế hoạch chuyển đổi.
8. **Chạy kiểm tra ở cấp phù hợp:** unit test chính sách, integration test luồng hủy, và kiểm tra thông tin hiển thị nếu ứng dụng có UI.

Khi code review, nên kiểm tra một bản thay đổi dưới góc nhìn **hành vi, bằng chứng và khả năng giải thích**. PR sửa mã nhưng quên test hoặc tài liệu có thể chưa hoàn chỉnh; PR chỉ cập nhật tài liệu khi hệ thống thực tế chưa hỗ trợ hành vi được mô tả cũng gây hiểu lầm.

## 12. Kiểm tra chất lượng của từng loại thông tin

Một bộ câu hỏi ngắn giúp đánh giá:

| Nguồn | Câu hỏi kiểm tra | Dấu hiệu cần cải thiện |
| --- | --- | --- |
| **Mã nguồn** | Tên/kiểu có diễn đạt ý định không, phụ thuộc có rõ không, ranh giới hành vi ở đâu? | Nhiều “magic number”, logic lặp, ý nghĩa ẩn trong cờ |
| **Kiểm thử** | Expected xuất phát từ yêu cầu nào, có ca biên và thất bại không, có thể chạy lại ổn định không? | Test chỉ gọi hàm nhưng không assert, expected sao chép thuật toán |
| **Tài liệu hợp đồng** | Người gọi có thể dùng đúng mà không đoán đơn vị, lỗi hay phạm vi không? | Mơ hồ về thời gian, dữ liệu không hợp lệ và tác dụng phụ |
| **Tài liệu thiết kế** | Ghi rõ bối cảnh, lựa chọn, lý do và hệ quả không? | Chỉ mô tả cấu trúc hiện tại, không nói vì sao |
| **Tài liệu vận hành** | Có thể làm theo, kiểm chứng và khôi phục an toàn không? | Lệnh lỗi thời, thiếu điều kiện môi trường, không rõ người chịu trách nhiệm |

Một tài liệu dài nhưng không trả lời được câu hỏi quan trọng vẫn có thể kém giá trị hơn một bảng ngắn chính xác. Tương tự, test có nhiều assertion nhưng kiểm tra sai kỳ vọng nghiệp vụ không phải bằng chứng mạnh.

## 13. Bài tập tình huống

Bạn tiếp nhận hệ thống gửi thông báo nhắc thanh toán. Ba nguồn thông tin đang có:

- **Mã nguồn:** gửi nhắc khi còn đúng hoặc ít hơn 48 giờ trước hạn thanh toán.
- **Kiểm thử:** kiểm tra trường hợp còn 24 giờ và 1 giờ thì gửi; không có ca đúng 48 giờ.
- **Tài liệu:** viết “thông báo được gửi một ngày trước hạn”.

**Câu hỏi A.** Có thể kết luận mã sai chỉ vì tài liệu viết “một ngày trước” không? Tại sao?

**Câu hỏi B.** Những thông tin nào cần xác nhận trước khi sửa?

**Câu hỏi C.** Nếu chính sách cuối cùng được xác nhận là “chỉ gửi một lần khi bắt đầu bước vào khoảng 24 giờ trước hạn”, mã, test và tài liệu mỗi bên phải giải quyết phần nào?

### Gợi ý trả lời

**A.** Chưa thể kết luận. Tài liệu có thể lỗi thời hoặc mô tả quá mơ hồ; mã cũng có thể không khớp với chính sách thật. Cần đối chiếu **nguồn yêu cầu còn hiệu lực**, phạm vi áp dụng và phiên bản triển khai.

**B.** Cần làm rõ ý nghĩa “một ngày”: 24 giờ thực trôi qua hay ngày lịch; chỉ có một lần thông báo hay gửi lặp lại; tính theo thời điểm server hay timezone người dùng; biên đúng 24 giờ/48 giờ được xử lý ra sao; những thông báo đã lên lịch trước khi đổi chính sách có cần thay không.

**C.** **Mã nguồn** cần thực hiện đúng chính sách “một lần” và ngưỡng 24 giờ, gồm cơ chế lưu dấu hoặc idempotency phù hợp để không gửi trùng khi job chạy lại. **Kiểm thử** cần ca trước/trong/sau ngưỡng, xác nhận không gửi trùng khi chạy lại, và kiểm tra thời gian bằng nguồn kiểm soát được. **Tài liệu** phải mô tả chính xác mốc 24 giờ, cách hiểu thời gian, phạm vi và hành vi gửi một lần, đồng thời ghi quyết định hoặc thay đổi có hiệu lực nếu cần.

## Ghi nhớ

**Mã nguồn, kiểm thử và tài liệu là ba hình thức tri thức bổ trợ nhau**. Mã cho biết hành vi được triển khai; kiểm thử tạo bằng chứng cho những tình huống đã kiểm tra; tài liệu truyền đạt hợp đồng, mục đích, bối cảnh và cách sử dụng hoặc vận hành. Không nguồn nào có thể một mình chứng minh toàn bộ hệ thống đúng, đáng tin cậy và dễ bảo trì.

Khi thay đổi phần mềm, hãy truy vết từ **yêu cầu được xác nhận → hợp đồng được mô tả → triển khai → kiểm chứng**, rồi cập nhật những nguồn thông tin bị ảnh hưởng. Mục tiêu không phải tạo nhiều tài liệu nhất, mà là giúp mỗi người **tìm đúng thông tin, hiểu đúng ý nghĩa và có bằng chứng đủ tin cậy để tiếp tục phát triển hệ thống**.
