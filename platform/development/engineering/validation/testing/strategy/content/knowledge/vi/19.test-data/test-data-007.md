# Kiểm soát thời gian, locale và yếu tố ngẫu nhiên

Trong module **VALIDATION_TESTING_STRATEGY**, thời gian, locale và yếu tố ngẫu nhiên là những nguồn biến thiên thường khiến kiểm thử cho kết quả khác nhau giữa máy phát triển, CI, môi trường tích hợp và sản xuất. Một kiểm thử có thể chạy đạt hôm nay nhưng thất bại vào ngày mai vì dữ liệu vừa hết hạn; cùng một ngày giờ có thể được hiểu khác nhau theo múi giờ; một số tiền có thể được định dạng bằng dấu phẩy hoặc dấu chấm tùy locale; một bộ dữ liệu sinh ngẫu nhiên có thể không tái tạo được khi lỗi xảy ra.

Để kiểm thử đáng tin cậy, cần kiểm soát các yếu tố này một cách có chủ đích. **Kiểm soát thời gian** giúp xác định chính xác thời điểm, múi giờ, thời hạn và tiến trình xử lý. **Kiểm soát locale** giúp xác minh cách hệ thống diễn giải và trình bày ngôn ngữ, ngày giờ, số, tiền tệ và thứ tự sắp xếp. **Kiểm soát yếu tố ngẫu nhiên** giúp tạo dữ liệu đa dạng nhưng vẫn có thể tái hiện khi phát hiện lỗi.

Bài học này trình bày cách nhận diện các nguồn biến thiên, thiết kế kiểm thử với đồng hồ và múi giờ rõ ràng, chọn locale phù hợp, quản lý seed và dữ liệu ngẫu nhiên, kiểm tra các trường hợp biên, cũng như ghi lại thông tin để tái tạo kết quả. Mục tiêu là bảo đảm mỗi lần chạy có điều kiện xác định, kết quả có thể giải thích và lỗi có thể được điều tra.

## 1. Vì sao cần kiểm soát các yếu tố biến thiên?

### 1.1. Thời gian có thể làm thay đổi kết quả

Nhiều quy tắc nghiệp vụ phụ thuộc vào thời điểm:

- Token hoặc phiên đăng nhập còn hiệu lực hay đã hết hạn.
- Mã giảm giá đã bắt đầu hoặc kết thúc.
- Người dùng có thể hủy lịch trước một ngưỡng thời gian.
- Giao dịch đã quá hạn thanh toán.
- Báo cáo tổng hợp dữ liệu theo ngày, tuần hoặc tháng.
- Tác vụ nền chạy theo lịch.
- Dữ liệu được giữ trong một khoảng thời gian rồi lưu trữ hoặc xóa.
- Hệ thống giới hạn số lần thao tác trong một cửa sổ thời gian.

Nếu kiểm thử dùng đồng hồ thực của máy, kết quả có thể thay đổi theo ngày chạy, múi giờ, thời gian thực thi hoặc độ trễ của CI. Một test kiểm tra token còn hạn trong 5 phút có thể thất bại nếu pipeline chạy chậm hoặc đồng hồ giữa các máy lệch nhau.

### 1.2. Locale có thể làm thay đổi cách hiểu dữ liệu

Locale ảnh hưởng đến cách hiển thị và đôi khi cách phân tích dữ liệu:

- Ngày có thể được viết theo thứ tự ngày/tháng/năm hoặc tháng/ngày/năm.
- Dấu phân cách phần thập phân và hàng nghìn khác nhau.
- Ký hiệu tiền tệ và vị trí ký hiệu thay đổi.
- Tên tháng, thứ trong tuần và lịch có thể khác.
- Quy tắc sắp xếp chữ có thể khác giữa ngôn ngữ.
- Chữ có dấu, ký tự kết hợp, chữ viết từ phải sang trái và quy tắc viết hoa có thể khác.

Ví dụ, chuỗi `03/04/2026` có thể được hiểu là ngày 3 tháng 4 hoặc ngày 4 tháng 3 tùy quy ước. Nếu kiểm thử phụ thuộc locale mặc định của máy, cùng một dữ liệu có thể được diễn giải khác giữa các môi trường.

### 1.3. Ngẫu nhiên có thể làm kiểm thử khó tái hiện

Dữ liệu ngẫu nhiên hữu ích để mở rộng phạm vi và tìm trường hợp chưa nghĩ đến. Tuy nhiên, nếu không lưu seed hoặc thông tin đầu vào, lỗi có thể chỉ xuất hiện một lần rồi biến mất.

Ví dụ:

- Một bộ sinh dữ liệu tạo số lượng, giá hoặc chuỗi ngẫu nhiên.
- Property-based testing sinh hàng trăm đầu vào.
- Fuzz testing tạo chuỗi hoặc payload bất thường.
- ID hoặc thứ tự xử lý được tạo ngẫu nhiên.
- Một test chọn ngẫu nhiên bản ghi từ tập dữ liệu lớn.

Nếu không ghi seed, phiên bản bộ sinh và cấu hình, nhóm có thể không tái tạo được dữ liệu gây lỗi.

### 1.4. Tính xác định và khả năng tái lập

Một kiểm thử có tính xác định (deterministic) khi cùng điều kiện đầu vào và cấu hình tạo ra kết quả có thể dự đoán. Khả năng tái lập (reproducibility) là khả năng chạy lại một trường hợp với cùng điều kiện để xác minh lỗi hoặc kết quả.

Không phải mọi kiểm thử đều cần dữ liệu cố định. Có thể dùng dữ liệu ngẫu nhiên để khám phá, miễn là lưu đủ thông tin để tái hiện trường hợp thất bại. Nguyên tắc là **đa dạng trong lúc tìm kiếm, xác định khi điều tra và xác nhận**.

## 2. Kiểm soát thời gian trong kiểm thử

### 2.1. Phân biệt các khái niệm thời gian

Cần chọn đúng kiểu thời gian cho mục đích sử dụng:

| Khái niệm | Ý nghĩa | Trường hợp thường dùng |
|---|---|---|
| Instant | Một thời điểm tuyệt đối trên dòng thời gian, thường biểu diễn theo UTC | Thời điểm tạo giao dịch, sự kiện hoặc log |
| LocalDate | Ngày lịch không kèm giờ hoặc múi giờ | Ngày sinh, ngày nghỉ, ngày hiệu lực |
| LocalTime | Giờ trong ngày không kèm ngày hoặc múi giờ | Giờ mở cửa, giờ hẹn lặp hằng ngày |
| LocalDateTime | Ngày và giờ địa phương nhưng chưa xác định múi giờ | Thời gian người dùng nhập trước khi gắn múi giờ |
| ZonedDateTime | Ngày giờ gắn với múi giờ cụ thể | Lịch hẹn theo địa điểm hoặc quy tắc vùng |
| Duration | Khoảng thời gian theo độ dài thời gian | Timeout, thời hạn 15 phút, thời gian chạy |
| Period | Khoảng thời gian theo đơn vị lịch như năm, tháng, ngày | Một tháng sau ngày đăng ký, một năm gia hạn |

Không nên dùng một kiểu duy nhất cho mọi trường hợp. “Hết hạn sau 24 giờ” thường là khoảng thời gian tuyệt đối; “hết hạn vào cuối ngày địa phương” là quy tắc theo lịch và múi giờ. Hai khái niệm này có thể cho kết quả khác nhau khi chuyển giờ mùa hè hoặc qua ranh giới ngày.

### 2.2. Phân biệt thời gian thực và thời gian đơn điệu

Có hai cách đo thời gian thường gặp:

- **Wall-clock time:** thời gian lịch mà người dùng nhìn thấy, có thể thay đổi do đồng bộ đồng hồ hoặc điều chỉnh hệ thống. Dùng cho ngày giờ nghiệp vụ và timestamp.
- **Monotonic time:** bộ đếm tăng liên tục trong tiến trình, phù hợp đo khoảng thời gian và timeout vì không bị lùi khi đồng hồ lịch được điều chỉnh.

Ví dụ trong Java:

```java
Instant startedAt = Instant.now();

// Đo thời lượng thực thi:
long startNanos = System.nanoTime();
performOperation();
long elapsedNanos = System.nanoTime() - startNanos;
```

Dùng `Instant` để ghi thời điểm và `System.nanoTime()` để đo thời lượng. Không nên tính timeout bằng cách so sánh timestamp lịch nếu hệ thống có thể điều chỉnh đồng hồ trong lúc chạy.

### 2.3. Đưa đồng hồ thành phụ thuộc có thể kiểm soát

Nếu logic gọi trực tiếp đồng hồ hệ thống ở nhiều nơi, kiểm thử khó kiểm soát thời điểm. Nên đưa nguồn thời gian vào thành phần cần dùng, chẳng hạn thông qua abstraction hoặc dependency injection.

Ví dụ Java với `Clock`:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.Duration;

public final class TokenService {
    private final Clock clock;

    public TokenService(Clock clock) {
        this.clock = clock;
    }

    public boolean isExpired(Instant expiresAt) {
        return !clock.instant().isBefore(expiresAt);
    }

    public Instant expiresAfter(Duration lifetime) {
        return clock.instant().plus(lifetime);
    }
}
```

Trong môi trường thực, có thể truyền `Clock.systemUTC()`. Trong kiểm thử, dùng đồng hồ cố định:

```java
Clock testClock = Clock.fixed(
    Instant.parse("2026-06-01T10:00:00Z"),
    ZoneOffset.UTC
);

TokenService service = new TokenService(testClock);
```

Khi đó, kết quả không phụ thuộc thời gian thực của máy. Với trường hợp cần tiến thời gian, có thể dùng một clock giả lập có khả năng thay đổi hoặc một abstraction riêng do nhóm kiểm soát.

### 2.4. Kiểm tra ranh giới thời hạn

Với một quy tắc hết hạn tại thời điểm (T), cần làm rõ điều kiện có bao gồm đúng thời điểm (T) hay không.

Ví dụ token hết hạn tại 10:00:00 UTC:

| Thời điểm kiểm thử | Câu hỏi | Kết quả theo quy tắc hết hạn tại hoặc sau T |
|---|---|---|
| 09:59:59.999 | Còn trước hạn không? | Còn hiệu lực |
| 10:00:00.000 | Đúng thời điểm hết hạn? | Hết hiệu lực |
| 10:00:00.001 | Đã qua hạn? | Hết hiệu lực |

Dùng đồng hồ cố định giúp kiểm tra chính xác các trường hợp này. Cần chú ý độ chính xác của timestamp trong hệ thống: giây, mili giây hay nano giây. Nếu database lưu đến mili giây nhưng test so sánh nano giây, kết quả có thể khác do làm tròn hoặc cắt độ chính xác.

### 2.5. Không dùng sleep để điều khiển thời gian nghiệp vụ

Một cách kiểm thử dễ gặp là gọi `Thread.sleep()` để chờ token hết hạn hoặc tác vụ nền chạy. Cách này thường làm test chậm và không ổn định:

- CI có thể chạy chậm hoặc bị tạm dừng.
- Thời gian ngủ không bảo đảm tác vụ đã hoàn tất.
- Test mất nhiều phút khi cần kiểm tra nhiều mốc thời gian.
- Lỗi có thể phụ thuộc tải máy.

Ưu tiên:

- Clock có thể cố định hoặc tiến thời gian.
- Scheduler giả lập hoặc bộ điều khiển tác vụ nền.
- API kiểm thử để kích hoạt job trong môi trường chuyên biệt.
- Chờ theo điều kiện có thể quan sát với thời hạn tối đa rõ ràng khi kiểm tra tích hợp bất đồng bộ.

Ví dụ, thay vì ngủ 60 giây để chờ mã giảm giá hết hạn, đặt clock kiểm thử tiến qua thời điểm hết hạn rồi gọi lại logic xác minh.

## 3. Kiểm soát múi giờ và quy tắc lịch

### 3.1. Múi giờ là một phần của ý nghĩa thời gian

Một timestamp tuyệt đối có thể được hiển thị ở nhiều múi giờ. Ngược lại, một giờ địa phương như 09:00 không xác định được thời điểm tuyệt đối nếu chưa biết ngày và múi giờ.

Ví dụ:

- Người dùng ở Việt Nam đặt lịch lúc 09:00 theo giờ địa phương.
- Hệ thống lưu thời điểm tuyệt đối để các dịch vụ xử lý thống nhất.
- Giao diện hiển thị lại theo múi giờ của người dùng hoặc địa điểm cung cấp dịch vụ.

Cần xác định múi giờ thuộc về người dùng, địa điểm, tổ chức hay cấu hình hệ thống. Không nên ngầm lấy múi giờ của máy chạy test.

### 3.2. Lưu và chuyển đổi thời gian

Một chiến lược phổ biến:

- Lưu sự kiện đã xảy ra dưới dạng thời điểm tuyệt đối, thường UTC.
- Lưu múi giờ IANA khi quy tắc nghiệp vụ phụ thuộc địa điểm.
- Chuyển đổi sang giờ địa phương ở biên giao tiếp hoặc hiển thị.
- Giữ ngày lịch như ngày sinh hoặc ngày nghỉ dưới dạng ngày, không tự biến thành timestamp nếu không cần.

Ví dụ Java:

```java
Instant eventTime = Instant.parse("2026-06-01T03:00:00Z");
ZoneId vietnamZone = ZoneId.of("Asia/Ho_Chi_Minh");

ZonedDateTime localTime = eventTime.atZone(vietnamZone);
System.out.println(localTime);
```

Không nên lưu chuỗi giờ địa phương không có múi giờ rồi giả định mọi hệ thống sẽ diễn giải giống nhau. Với lịch hẹn theo địa điểm, lưu cả quy tắc múi giờ liên quan để diễn giải đúng khi quy định vùng thay đổi.

### 3.3. Kiểm tra giờ mùa hè (DST)

Ở một số khu vực, đồng hồ được điều chỉnh theo giờ mùa hè (Daylight Saving Time, DST). Điều này tạo ra hai tình huống đặc biệt:

- **Giờ không tồn tại:** đồng hồ nhảy qua một khoảng, ví dụ từ 01:59 lên 03:00 nên 02:30 không xảy ra trong ngày đó.
- **Giờ bị lặp:** đồng hồ lùi lại, một khoảng giờ địa phương xuất hiện hai lần và cần phân biệt hai thời điểm tuyệt đối.

Kiểm thử lịch theo múi giờ có DST cần bao gồm ngày chuyển đổi. Xác định hệ thống sẽ từ chối giờ không tồn tại, tự điều chỉnh hay yêu cầu người dùng chọn giờ khác. Với giờ bị lặp, xác định cách chọn offset hoặc lần xuất hiện.

Không nên chỉ kiểm thử ở một múi giờ không có DST rồi kết luận quy tắc lịch hoạt động đúng trên toàn cầu.

### 3.4. Kiểm tra năm nhuận, cuối tháng và chuyển năm

Các tình huống lịch thường tạo lỗi:

- Ngày 29 tháng 2 trong năm nhuận và năm thường.
- Cộng một tháng từ ngày 29, 30 hoặc 31.
- Chuyển từ tháng 12 sang tháng 1.
- Ngày cuối tháng và ngày đầu tháng.
- Tuần bắt đầu vào thứ Hai hay Chủ nhật.
- Tuần hoặc năm tài chính khác năm dương lịch.
- Ngày nghỉ hoặc ngày làm việc theo khu vực.

Ví dụ, “gia hạn một tháng” từ ngày 31 tháng 1 có thể được diễn giải thành ngày cuối tháng 2, ngày 3 tháng 3 hoặc một quy tắc khác tùy chính sách. Không tự giả định cách cộng tháng; cần có ví dụ nghiệp vụ và kết quả được xác nhận.

### 3.5. Kiểm thử ranh giới ngày và báo cáo

Với báo cáo theo ngày, cần xác định:

- Ngày được tính theo UTC hay múi giờ nghiệp vụ.
- Khoảng thời gian là đóng hay nửa mở.
- Giao dịch đúng lúc nửa đêm thuộc ngày nào.
- Dữ liệu đến muộn được đưa vào kỳ nào.
- Ngày bắt đầu và kết thúc của tuần, tháng hoặc quý.
- Thời điểm chuyển ngày khi có DST.

Một cách biểu diễn khoảng thời gian thường dễ kiểm soát là khoảng nửa mở ([start, end)): bao gồm thời điểm bắt đầu và không bao gồm thời điểm kết thúc. Khi đó hai khoảng liền nhau không chồng lấn. Tuy nhiên, phải dùng đúng quy tắc của báo cáo hoặc nghiệp vụ.

## 4. Kiểm soát locale và ngôn ngữ

### 4.1. Locale khác với múi giờ

Locale mô tả quy tắc ngôn ngữ và định dạng theo vùng; múi giờ mô tả quan hệ giữa giờ địa phương và thời điểm tuyệt đối.

Một người có thể dùng giao diện tiếng Việt nhưng làm việc tại múi giờ khác. Một người ở Việt Nam có thể chọn giao diện tiếng Anh. Không nên suy ra múi giờ chỉ từ ngôn ngữ hoặc locale.

Nên quản lý riêng:

- Ngôn ngữ giao diện.
- Locale định dạng số, ngày và tiền tệ.
- Múi giờ hiển thị hoặc quy tắc nghiệp vụ.
- Lịch sử dụng nếu sản phẩm hỗ trợ lịch khác dương lịch.
- Quy tắc sắp xếp và tìm kiếm theo ngôn ngữ.

### 4.2. Dùng locale tường minh trong kiểm thử

Không nên phụ thuộc locale mặc định của máy. Hãy truyền locale rõ ràng khi định dạng hoặc phân tích dữ liệu.

Ví dụ Java:

```java
Locale vietnamese = Locale.forLanguageTag("vi-VN");
Locale germany = Locale.GERMANY;

NumberFormat vietnamFormat =
    NumberFormat.getNumberInstance(vietnamese);

NumberFormat germanyFormat =
    NumberFormat.getNumberInstance(germany);
```

Kết quả định dạng có thể khác nhau về dấu phân cách. Test nên kiểm tra giá trị ngữ nghĩa và chuỗi hiển thị theo locale mục tiêu, không dùng một chuỗi cố định cho mọi locale.

### 4.3. Ngày tháng và lịch

Các định dạng ngày phổ biến có thể khác nhau:

| Locale minh họa | Cách hiển thị thường gặp | Lưu ý |
|---|---|---|
| vi-VN | 31/12/2026 | Ngày trước tháng |
| en-US | 12/31/2026 | Tháng trước ngày |
| en-GB | 31/12/2026 | Ngày trước tháng |
| ja-JP | Có thể dùng thứ tự năm/tháng/ngày | Có thể có quy tắc lịch và ký tự riêng |

Các định dạng cụ thể phụ thuộc thư viện và cấu hình. Không nên parse ngày bằng cách tách chuỗi theo dấu gạch chéo hoặc giả định vị trí ngày/tháng. Dùng parser theo locale hoặc định dạng máy đọc được đã được quy định.

Đối với API, nên thống nhất định dạng máy đọc được, chẳng hạn ISO 8601 cho timestamp, và quy định rõ timezone. Đối với giao diện, hiển thị theo locale người dùng hoặc chính sách sản phẩm.

### 4.4. Số, tiền tệ và quy tắc làm tròn

Locale có thể ảnh hưởng:

- Dấu phân cách thập phân.
- Dấu phân cách hàng nghìn.
- Vị trí ký hiệu tiền tệ.
- Khoảng trắng hoặc ký tự đặc biệt.
- Số chữ số thập phân được hiển thị.
- Quy tắc định dạng âm.

Ví dụ chuỗi `1.234,56` và `1,234.56` có thể biểu diễn cùng giá trị theo quy ước khác nhau. Kiểm thử cần phân biệt parsing, giá trị nội bộ và định dạng hiển thị.

Với tiền tệ, không nên dùng số thực nhị phân để kiểm tra phép tính tiền nếu hệ thống yêu cầu độ chính xác thập phân. Xác định currency, đơn vị nhỏ nhất, scale và quy tắc làm tròn. Locale định dạng không được làm thay đổi giá trị tiền nghiệp vụ.

### 4.5. Ngôn ngữ, Unicode và sắp xếp

Kiểm tra nội dung với:

- Ký tự có dấu và dấu kết hợp.
- Tên người hoặc địa chỉ dài.
- Ký tự ngoài bảng Latin.
- Chữ viết từ phải sang trái nếu hỗ trợ.
- Chuỗi hỗn hợp nhiều ngôn ngữ.
- Quy tắc viết hoa và chuyển chữ.
- Sắp xếp tên, tìm kiếm không dấu hoặc dấu phụ nếu sản phẩm hỗ trợ.
- Chuỗi có emoji hoặc ký tự đặc biệt.

Hai chuỗi trông giống nhau có thể có cách mã hóa Unicode khác nhau, ví dụ ký tự dựng sẵn và ký tự cơ sở cộng dấu kết hợp. Kiểm thử nên xác định hệ thống cần chuẩn hóa, so sánh hoặc lưu chuỗi ra sao.

### 4.6. Locale mặc định là nguồn lỗi tiềm ẩn

Nếu code gọi `Locale.getDefault()` hoặc formatter không chỉ định locale, kết quả phụ thuộc môi trường. Điều này có thể gây lỗi chỉ xuất hiện trên máy developer hoặc runner có cấu hình khác.

Trong test, đặt locale tường minh cho từng trường hợp. Nếu sản phẩm chủ đích hỗ trợ locale mặc định của người dùng, hãy kiểm tra cả cơ chế chọn locale và fallback khi không có bản dịch.

## 5. Kiểm soát yếu tố ngẫu nhiên

### 5.1. Vì sao dùng dữ liệu ngẫu nhiên?

Dữ liệu ngẫu nhiên có thể giúp:

- Khám phá đầu vào mà người viết test chưa nghĩ đến.
- Tạo nhiều giá trị và tổ hợp dữ liệu.
- Kiểm tra bất biến trên một tập đầu vào rộng.
- Tìm lỗi xử lý chuỗi, số, cấu trúc lồng nhau và dữ liệu biên.
- Tăng khả năng phát hiện lỗi trong property-based testing và fuzzing.

Tuy nhiên, random không tự động đồng nghĩa với bao phủ tốt. Bộ sinh cần có phân bố, giới hạn và mục tiêu. Nếu chỉ sinh số nguyên đều trong một khoảng rộng, các giá trị biên hoặc trạng thái hiếm có thể ít xuất hiện.

### 5.2. Seed và khả năng tái tạo

Pseudo-random number generator (PRNG) tạo chuỗi giá trị có vẻ ngẫu nhiên nhưng có thể tái tạo từ seed và thuật toán tương ứng.

Ví dụ Java:

```java
long seed = 20261116L;
Random random = new Random(seed);

int quantity = random.nextInt(10) + 1;
```

Với cùng seed và cùng cách gọi generator trong cùng môi trường tương thích, chuỗi giá trị có thể được tái tạo. Khi test thất bại, ghi lại:

- Seed.
- Thuật toán hoặc thư viện generator.
- Phiên bản thư viện.
- Cấu hình và giới hạn sinh dữ liệu.
- Thứ tự hoặc số lần gọi generator nếu cần.
- Giá trị đầu vào thực tế đã gây lỗi.

Chỉ lưu seed đôi khi chưa đủ nếu phiên bản thư viện, thứ tự chạy hoặc số lần gọi đã thay đổi. Đối với lỗi quan trọng, lưu luôn bộ dữ liệu thất bại hoặc fixture đã thu nhỏ.

### 5.3. Phân biệt PRNG với nguồn ngẫu nhiên bảo mật

PRNG thông thường phù hợp tạo dữ liệu kiểm thử có thể tái lập. `SecureRandom` phục vụ mục tiêu sinh giá trị khó dự đoán cho bảo mật, chẳng hạn token hoặc nonce. Không nên dùng một seed cố định trong môi trường thực để làm yếu tính bảo mật.

Khi kiểm thử logic bảo mật, không nên thay nguồn ngẫu nhiên bảo mật bằng generator yếu trong production. Có thể thiết kế abstraction hoặc điểm tiêm phụ thuộc dành cho test để kiểm tra logic với giá trị xác định, đồng thời có kiểm tra riêng bảo đảm cấu hình thực dùng nguồn ngẫu nhiên phù hợp.

### 5.4. Quản lý generator riêng cho từng test

Một generator dùng chung cho nhiều test có thể làm kết quả phụ thuộc thứ tự chạy. Nếu một test gọi thêm một lần random, các test sau nhận chuỗi giá trị khác.

Để cô lập:

- Tạo generator riêng cho từng test hoặc từng test run.
- Dùng seed được ghi nhận.
- Truyền generator vào factory thay vì dùng trạng thái toàn cục.
- Không để test song song chia sẻ generator có trạng thái thay đổi.
- Ghi dữ liệu cuối cùng khi thất bại.
- Giữ seed ổn định cho test hồi quy đã tái hiện lỗi.

Ví dụ:

```java
Random randomForCase(long seed) {
    return new Random(seed);
}
```

Không nên tạo seed từ thời gian hiện tại mà không ghi lại. Cách đó tạo biến thiên mới mỗi lần và khiến lỗi khó tái hiện.

## 6. Property-based testing và fuzz testing

### 6.1. Property-based testing

Property-based testing kiểm tra các thuộc tính phải đúng với nhiều đầu vào được sinh tự động, thay vì chỉ kiểm tra một số ví dụ cố định.

Ví dụ thuộc tính cho phép tính tổng:

- Tổng của danh sách rỗng bằng 0 nếu quy tắc cho phép.
- Thêm một mặt hàng có giá không âm không làm tổng giảm.
- Hoán đổi thứ tự các dòng không làm thay đổi tổng.
- Tổng phải bằng tổng các dòng sau khi áp dụng quy tắc thuế và giảm giá.

Một framework có thể sinh nhiều đầu vào, kiểm tra thuộc tính và cố gắng thu nhỏ dữ liệu khi phát hiện lỗi. Khi thất bại, cần lưu seed và trường hợp đã thu nhỏ để tạo regression test ổn định.

### 6.2. Fuzz testing

Fuzz testing tạo đầu vào đa dạng hoặc bất thường để tìm lỗi về parser, validation, bộ nhớ, bảo mật và xử lý ngoại lệ.

Có thể fuzz:

- Chuỗi Unicode và ký tự đặc biệt.
- JSON lồng sâu hoặc thiếu trường.
- Số rất lớn, rất nhỏ hoặc giá trị biên.
- Ngày giờ sai định dạng.
- Header hoặc payload không hợp lệ.
- Tệp có kích thước và cấu trúc khác nhau.

Fuzzing cần giới hạn tài nguyên và chạy trong môi trường phù hợp. Không dùng dữ liệu fuzz tùy tiện lên hệ thống sản xuất hoặc endpoint bên ngoài khi chưa được phép.

### 6.3. Từ phát hiện ngẫu nhiên đến kiểm thử hồi quy

Khi random hoặc property-based test tìm được lỗi:

1. Lưu seed, phiên bản generator và cấu hình.
2. Lưu đầu vào thất bại.
3. Thu nhỏ đầu vào nếu công cụ hỗ trợ.
4. Xác định thuộc tính hoặc quy tắc bị vi phạm.
5. Tạo test hồi quy với đầu vào tối thiểu và rõ nghĩa.
6. Giữ test khám phá ngẫu nhiên trong suite phù hợp.
7. Ghi liên kết giữa lỗi, seed và test hồi quy.

Test hồi quy cố định giúp xác nhận lỗi đã được sửa trong các lần chạy sau. Test ngẫu nhiên tiếp tục tìm biến thể khác.

## 7. Kiểm soát kết hợp thời gian, locale và ngẫu nhiên

Các yếu tố này thường tương tác với nhau. Một test có thể sinh ngày ngẫu nhiên, định dạng theo locale và chuyển đổi qua múi giờ. Nếu không kiểm soát cả ba, lỗi có thể khó xác định nguyên nhân.

### 7.1. Thiết kế dữ liệu với thời gian và locale rõ ràng

Với mỗi trường hợp, ghi:

- Thời điểm tham chiếu.
- Múi giờ.
- Locale.
- Lịch nếu có.
- Seed hoặc dữ liệu sinh.
- Phiên bản generator và formatter.
- Kết quả kỳ vọng ở dạng giá trị máy và dạng hiển thị.

Ví dụ, kiểm thử hóa đơn cho khách tại Việt Nam có thể cố định một `Instant`, dùng `Asia/Ho_Chi_Minh` để xác định ngày nghiệp vụ, dùng `vi-VN` để định dạng và dùng dữ liệu sản phẩm được tạo từ seed đã ghi nhận.

### 7.2. Tránh phụ thuộc cấu hình mặc định

Không giả định:

- Múi giờ máy chạy là UTC.
- Locale mặc định là tiếng Anh.
- Ngày hiện tại giống nhau trên tất cả runner.
- Thứ tự dữ liệu sinh ngẫu nhiên không đổi.
- Đồng hồ giữa các dịch vụ luôn đồng bộ tuyệt đối.

Đặt cấu hình tường minh trong test và kiểm tra các biến môi trường có thể ảnh hưởng. Với hệ thống phân tán, cần hiểu đồng hồ của từng dịch vụ, độ lệch cho phép và nguồn timestamp được xem là có thẩm quyền.

### 7.3. Kiểm tra đồng hồ lệch và sự kiện đến muộn

Trong hệ thống phân tán, các máy có thể có độ lệch đồng hồ. Sự kiện có timestamp sớm hơn sự kiện khác không nhất thiết được xử lý trước. Cần phân biệt:

- Thời điểm sự kiện xảy ra.
- Thời điểm dịch vụ nhận sự kiện.
- Thời điểm sự kiện được xử lý.
- Thời điểm dữ liệu được ghi.
- Thứ tự được xác định bởi sequence hoặc version nếu có.

Kiểm thử nên xem xét sự kiện đến muộn, lặp hoặc sai thứ tự nếu hệ thống có yêu cầu xử lý chúng. Không dùng timestamp đơn lẻ làm bằng chứng duy nhất cho thứ tự nếu kiến trúc không bảo đảm điều đó.

### 7.4. Kiểm thử song song và nguồn biến thiên dùng chung

Khi nhiều test chạy đồng thời, các nguồn biến thiên dùng chung có thể gây xung đột:

- Hai test cùng tạo dữ liệu với ID ngẫu nhiên nhưng trùng do generator bị khởi tạo giống nhau.
- Hai test thay đổi locale mặc định toàn tiến trình.
- Một test thay đổi clock dùng chung trong khi test khác đang chạy.
- Test cùng sửa cấu hình timezone hoặc biến môi trường.
- Test dùng chung tài khoản và trạng thái.

Giải pháp là cô lập phụ thuộc theo test, tránh thay đổi cấu hình toàn cục và dùng namespace hoặc mã test run riêng.

## 8. Mẫu thiết kế kiểm thử cho từng yếu tố

### 8.1. Mẫu kiểm thử thời hạn

Mục tiêu: xác nhận token hết hạn đúng tại thời điểm quy định.

| Thuộc tính | Giá trị |
|---|---|
| Clock | Fixed clock |
| Instant tham chiếu | 2026-06-01T10:00:00Z |
| Token hết hạn | 2026-06-01T10:05:00Z |
| Trường hợp trước hạn | 10:04:59.999Z |
| Trường hợp đúng hạn | 10:05:00.000Z |
| Trường hợp sau hạn | 10:05:00.001Z |
| Kết quả cần xác minh | Còn hiệu lực trước hạn; hết hạn tại hoặc sau thời điểm hết hạn theo quy tắc |

### 8.2. Mẫu kiểm thử locale

Mục tiêu: hiển thị cùng một giá trị theo locale được chọn.

| Thuộc tính | Giá trị |
|---|---|
| Giá trị nội bộ | Số thập phân đã xác định |
| Locale A | vi-VN |
| Locale B | en-US |
| Locale C | de-DE |
| Điều cần kiểm tra | Dấu phân cách, ký hiệu, thứ tự và parsing |
| Bằng chứng | Giá trị nội bộ không đổi; chuỗi hiển thị phù hợp locale |

Không so sánh chuỗi định dạng của locale này với chuỗi của locale khác như thể chúng phải giống nhau. Xác minh cả giá trị ngữ nghĩa sau parse nếu chức năng có hỗ trợ nhập dữ liệu.

### 8.3. Mẫu kiểm thử dữ liệu ngẫu nhiên

Mục tiêu: tìm lỗi trong phép tính giỏ hàng.

| Thuộc tính | Cách kiểm soát |
|---|---|
| Generator | PRNG được chỉ định |
| Seed | Lưu cùng kết quả chạy |
| Miền dữ liệu | Số lượng, giá, giảm giá trong giới hạn nghiệp vụ |
| Bất biến | Tổng không âm và khớp tổng dòng theo quy tắc |
| Khi thất bại | Lưu seed, đầu vào và dữ liệu đã thu nhỏ |
| Hồi quy | Tạo test cố định cho trường hợp gây lỗi |

### 8.4. Mẫu thông tin cần lưu khi thất bại

Một báo cáo đủ để tái hiện nên gồm:

| Trường | Nội dung |
|---|---|
| Test ID | Mã kiểm thử |
| Build / commit | Phiên bản chạy |
| Thời điểm chạy | Timestamp và timezone |
| Clock mode | System, fixed, offset hoặc mutable |
| Reference time | Thời điểm kiểm thử sử dụng |
| Zone ID | Múi giờ áp dụng |
| Locale | Ngôn ngữ và vùng |
| Random seed | Seed và loại generator |
| Generator version | Phiên bản thư viện hoặc thuật toán |
| Input data | Dữ liệu thực tế gây lỗi |
| Environment | Runner, hệ điều hành và cấu hình liên quan |
| Expected / actual | Kết quả mong đợi và thực tế |
| Evidence | Log, trace, report hoặc fixture |

## 9. Quy trình thực hiện và duy trì

### 9.1. Trước khi chạy

1. Xác định mục tiêu và quy tắc có phụ thuộc thời gian, locale hoặc random không.
2. Chọn kiểu thời gian phù hợp và xác định clock tham chiếu.
3. Ghi múi giờ và locale rõ ràng.
4. Chọn generator, seed và miền dữ liệu.
5. Chuẩn bị dữ liệu biên và trạng thái cần thiết.
6. Kiểm tra cấu hình runner và biến môi trường.
7. Xác nhận các phụ thuộc được cô lập.

### 9.2. Trong khi chạy

- Không dùng đồng hồ hệ thống trực tiếp nếu logic cần thời gian có thể kiểm soát.
- Không dựa vào locale mặc định.
- Ghi seed và đầu vào thực tế khi dùng random.
- Tránh sleep tùy ý để chờ thời hạn hoặc job.
- Dùng thời hạn chờ và điều kiện quan sát rõ ràng cho xử lý bất đồng bộ.
- Thu thập bằng chứng tại thời điểm lỗi.

### 9.3. Sau khi chạy

- Lưu thông tin cấu hình đủ để tái hiện.
- Giữ lại fixture gây lỗi theo chính sách.
- Tạo test hồi quy cho lỗi đã xác nhận.
- Kiểm tra không còn dữ liệu hoặc cấu hình toàn cục bị thay đổi.
- Đánh giá lỗi có phải do logic, môi trường hay dữ liệu không ổn định.
- Cập nhật tài liệu nếu quy tắc thời gian, locale hoặc generator thay đổi.

## 10. Những sai lầm thường gặp

1. **Dùng đồng hồ hệ thống trong mọi test:** kết quả phụ thuộc ngày giờ thực và tốc độ CI.
2. **Dùng sleep để chờ hết hạn:** làm test chậm và không bảo đảm tác vụ đã hoàn tất.
3. **Không xác định múi giờ:** diễn giải timestamp khác nhau giữa máy.
4. **Nhầm locale với timezone:** cấu hình ngôn ngữ nhưng bỏ qua múi giờ nghiệp vụ.
5. **Parse ngày theo chuỗi cố định:** giả định thứ tự ngày/tháng không thay đổi.
6. **Bỏ qua DST và năm nhuận:** lỗi chỉ xuất hiện ở một số ngày hoặc khu vực.
7. **Dùng locale mặc định:** kết quả phụ thuộc cấu hình máy developer hoặc runner.
8. **So sánh chuỗi tiền tệ thay cho giá trị:** nhầm định dạng hiển thị với giá trị nghiệp vụ.
9. **Dùng random không lưu seed:** không thể tái tạo dữ liệu gây lỗi.
10. **Chia sẻ generator toàn cục:** test phụ thuộc thứ tự hoặc ảnh hưởng lẫn nhau.
11. **Dùng PRNG cho mục đích bảo mật:** làm suy yếu token hoặc giá trị cần khó dự đoán.
12. **Chỉ lưu seed mà không lưu đầu vào:** thay đổi phiên bản hoặc thứ tự gọi khiến lỗi khó tái hiện.
13. **Không kiểm tra cấu hình song song:** clock, locale hoặc dữ liệu dùng chung tạo flaky test.
14. **Không chuyển lỗi random thành regression test:** lỗi đã tìm được có thể xuất hiện lại mà không có kiểm tra cố định.

## 11. Checklist kiểm soát thời gian, locale và yếu tố ngẫu nhiên

- [ ] Đã xác định mục tiêu nào phụ thuộc vào thời gian, locale hoặc dữ liệu ngẫu nhiên.
- [ ] Đã chọn đúng kiểu thời gian: Instant, LocalDate, LocalDateTime, ZonedDateTime, Duration hoặc Period.
- [ ] Logic thời gian có thể nhận clock được kiểm soát trong test.
- [ ] Đã xác định timezone và quy tắc lưu, chuyển đổi, hiển thị.
- [ ] Đã kiểm tra thời hạn tại trước, đúng và sau ranh giới.
- [ ] Đã xem xét DST, năm nhuận, cuối tháng và ranh giới ngày.
- [ ] Dùng monotonic time cho đo thời lượng và timeout khi phù hợp.
- [ ] Không dùng sleep tùy ý thay cho clock hoặc điều kiện chờ.
- [ ] Locale được chỉ định tường minh trong các test liên quan.
- [ ] Đã kiểm tra định dạng ngày, số, tiền tệ, Unicode và sắp xếp theo phạm vi hỗ trợ.
- [ ] Đã phân biệt locale, ngôn ngữ giao diện và múi giờ.
- [ ] Generator ngẫu nhiên có seed và phạm vi dữ liệu được kiểm soát.
- [ ] Mỗi test có generator riêng hoặc cách cô lập trạng thái random.
- [ ] Đã phân biệt PRNG dùng cho test với nguồn ngẫu nhiên bảo mật.
- [ ] Khi random test thất bại, đã lưu seed, phiên bản generator và đầu vào thực tế.
- [ ] Đã chuyển trường hợp lỗi được xác nhận thành test hồi quy.
- [ ] Đã kiểm tra tác động của chạy song song và cấu hình toàn cục.
- [ ] Báo cáo có đủ thông tin để tái tạo kết quả và giải thích giới hạn.

Kiểm soát thời gian, locale và yếu tố ngẫu nhiên giúp kiểm thử phản ánh đúng quy tắc thay vì vô tình phụ thuộc vào máy chạy hoặc thời điểm chạy. Khi clock, múi giờ, locale, seed và dữ liệu được khai báo rõ ràng, nhóm có thể kiểm tra các trường hợp biên một cách nhanh chóng, tái hiện lỗi đáng tin cậy và duy trì bộ kiểm thử ổn định qua nhiều môi trường.
