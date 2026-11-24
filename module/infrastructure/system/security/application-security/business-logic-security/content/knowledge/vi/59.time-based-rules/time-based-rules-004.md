# Effective date boundary — Ranh giới ngày hiệu lực

## 1. Một mili giây có thể thay đổi quyền lợi nghiệp vụ

Một chương trình giảm giá kết thúc lúc 00:00 ngày 01/01. Người dùng bấm thanh toán trước mốc này, nhưng yêu cầu phải chờ khóa dữ liệu và chỉ được xử lý sau đó. Hệ thống nên áp dụng giá nào? Nếu người dùng gửi lại cùng yêu cầu sau khi chương trình hết hạn thì có tạo thêm đơn giảm giá không? Nếu chính sách giá mới bắt đầu đúng lúc chính sách cũ kết thúc, phiên bản nào được chọn?

Đây là các câu hỏi về **effective date boundary**: ranh giới bắt đầu và kết thúc hiệu lực của một quy tắc nghiệp vụ. Những quy tắc này xuất hiện trong giá bán, ưu đãi, hợp đồng, quyền truy cập tạm thời, hạn nộp hồ sơ, thời hạn phê duyệt và lịch mở bán.

Lỗi ở ranh giới hiệu lực có thể cho phép áp dụng ưu đãi hết hạn, dùng quyền chưa có hiệu lực, chọn phiên bản giá có lợi bằng cách đổi múi giờ, hoặc giữ một kết quả kiểm tra cũ để thực hiện thao tác sau thời hạn. Đây là lỗi logic ngay cả khi đầu vào không chứa mã độc và người gọi đã đăng nhập hợp lệ.

Trong bài học này, ví dụ chính là một chương trình giá ưu đãi của tenant, có phiên bản chính sách và thời gian hiệu lực rõ ràng. Mục tiêu là gắn kiểm tra thời gian với quyền theo đối tượng, trạng thái phê duyệt, giao dịch, idempotency và kiểm thử các lịch sự kiện đối kháng.

## 2. Phân biệt ngày nghiệp vụ, thời điểm và thời hạn

### 2.1. Ngày không phải là một thời điểm duy nhất

`2026-12-01` là một ngày lịch. Nó chưa cho biết một thời điểm toàn cầu nếu thiếu múi giờ và quy tắc chuyển đổi. Ngược lại, `2026-11-30T17:00:00Z` là một thời điểm xác định; nó tương ứng với 00:00 ngày 01/12/2026 ở múi giờ `Asia/Ho_Chi_Minh`.

| Khái niệm | Ví dụ | Vai trò |
| --- | --- | --- |
| Ngày lịch nghiệp vụ | `2026-12-01` | Hợp đồng hoặc giao diện cấu hình theo ngày |
| Múi giờ nghiệp vụ | `Asia/Ho_Chi_Minh` | Diễn giải ngày và giờ theo địa phương |
| Thời điểm tuyệt đối | `2026-11-30T17:00:00Z` | So sánh và lưu mốc thực thi |
| Khoảng thời gian | Từ đầu tháng đến đầu tháng kế tiếp | Xác định tập thời điểm được áp dụng |
| Thời lượng | 15 phút kể từ khi cấp báo giá | Giới hạn độ dài của một quyền lợi tạm thời |

Không dùng múi giờ mặc định của máy chạy ứng dụng để diễn giải chính sách. Cùng một bản ghi không được có hiệu lực khác nhau chỉ vì request đi vào instance ở khu vực khác.

### 2.2. Phân biệt hai kiểu yêu cầu

“Có hiệu lực trong ngày 31/12 theo múi giờ cửa hàng” là một quy tắc lịch. “Báo giá có hiệu lực trong 15 phút kể từ khi cấp” là một quy tắc thời lượng. Hai quy tắc có thể dùng chung cách so sánh các mốc `Instant`, nhưng cách tạo mốc kết thúc khác nhau.

Với ngày lịch, phải xây mốc bắt đầu ngày theo múi giờ nghiệp vụ. Với thời lượng, phải xác định thời điểm cấp và cộng thời lượng theo hợp đồng. Không thay ngày lịch bằng phép cộng cố định 24 giờ trong mọi múi giờ, vì có nơi ngày chuyển giờ mùa hè không dài đúng 24 giờ.

## 3. Quy ước khoảng nửa mở: bắt đầu được tính, kết thúc không được tính

Một quy ước dễ kết hợp giữa các phiên bản là khoảng **nửa mở**:

```text
[validFrom, validUntil)

Được áp dụng khi:
    validFrom <= decisionAt
    và decisionAt < validUntil
```

`validFrom` được tính vào khoảng; `validUntil` là thời điểm đầu tiên không còn hiệu lực. Quy ước phải được ghi thành hợp đồng chung cho backend, API quản trị, giao diện và tác vụ nền.

Ví dụ chương trình có hiệu lực trong tháng 12/2026 theo giờ Việt Nam:

```text
Mốc theo múi giờ nghiệp vụ:
    validFrom  = 2026-12-01T00:00:00+07:00
    validUntil = 2027-01-01T00:00:00+07:00

Mốc tuyệt đối tương ứng:
    validFrom  = 2026-11-30T17:00:00Z
    validUntil = 2026-12-31T17:00:00Z
```

| Thời điểm quyết định theo giờ nghiệp vụ | Kết quả |
| --- | --- |
| Ngay trước `2026-12-01T00:00:00+07:00` | Chưa có hiệu lực |
| Đúng `2026-12-01T00:00:00+07:00` | Có hiệu lực |
| Ngay trước `2027-01-01T00:00:00+07:00` | Còn hiệu lực |
| Đúng `2027-01-01T00:00:00+07:00` | Hết hiệu lực |

“Ngay trước” phải được hiểu theo độ chính xác mà hệ thống hỗ trợ. Không mặc định database lưu được mọi nano giây chỉ vì kiểu dữ liệu trong Java biểu diễn được nano giây.

### 3.1. Vì sao không đặt kết thúc ở 23:59:59.999?

Mốc “cuối ngày” dạng này phụ thuộc vào độ chính xác. Nếu có dữ liệu micro giây, các thời điểm sau `.999000` vẫn có thể thuộc ngày đó nhưng lại bị loại. Nếu một lớp làm tròn thay vì cắt phần lẻ, ranh giới còn có thể bị dịch sang ngày kế tiếp.

Nếu giao diện ghi “áp dụng đến hết ngày 31/12”, hãy chuyển thành mốc loại trừ là đầu ngày 01/01 theo múi giờ nghiệp vụ. Không tạo ranh giới bằng cách đoán giá trị phần giây lớn nhất.

### 3.2. Các phiên bản liền nhau

```text
V1: [t0, t1)
V2: [t1, t2)

Tại t1: chỉ V2 có hiệu lực.
```

Với hai khoảng hữu hạn hợp lệ A và B, chúng chồng lấn khi:

```text
A.from < B.until && B.from < A.until
```

Hai khoảng chạm nhau tại một đầu mút không chồng lấn. Nếu hỗ trợ không có ngày kết thúc, cần mô hình hóa rõ đầu mút mở về tương lai và điều chỉnh phép so sánh; không dùng một ngày tùy ý như năm 9999 rồi mặc định mọi thành phần đều xử lý giống nhau.

## 4. Chọn thời điểm nào để đưa ra quyết định?

Một thao tác có thể có nhiều timestamp hợp lệ nhưng mang ý nghĩa khác nhau.

| Mốc | Ai tạo hoặc quan sát? | Có thể dùng làm căn cứ gì? |
| --- | --- | --- |
| `clientSentAt` | Thiết bị người dùng | Chẩn đoán; không tự chứng minh quyền hưởng ưu đãi |
| `gatewayReceivedAt` | Cổng vào do hệ thống kiểm soát | Căn cứ nhận hồ sơ nếu hợp đồng và cơ chế ghi nhận quy định như vậy |
| `decisionAt` | Thành phần có thẩm quyền chốt quyết định | Chọn phiên bản và xác nhận điều kiện nghiệp vụ |
| `committedAt` | Hệ thống lưu trữ theo cơ chế ghi nhận cụ thể | Điều tra hoặc hợp đồng yêu cầu mốc hoàn tất ghi nhận |
| `providerEventAt` | Nhà cung cấp ngoài | Căn cứ sự kiện nếu nguồn, loại sự kiện và quy tắc chấp nhận đã được xác định |
| `processedAt` | Consumer hoặc worker | Theo dõi lúc xử lý, có thể muộn hơn lúc sự kiện xảy ra |

Đừng gọi mọi cột là `createdAt` rồi dùng thay thế lẫn nhau. Tên trường và hợp đồng phải cho biết mốc đó đo điều gì.

### 4.1. Hợp đồng minh họa: chốt khi giữ được quyền xử lý

Trong ví dụ giá ưu đãi, quy định:

> Hệ thống chọn chính sách tại `decisionAt`, sau khi đã giành được các khóa cần thiết để chốt đơn. Phiên bản và giá được lưu cùng quyết định. Commit có thể xảy ra sau đó; việc commit không đổi lại thời điểm lựa chọn giá.

Lịch sự kiện:

```text
23:59:59.800  Request đến API.
23:59:59.850  Request bắt đầu chờ khóa.
00:00:00.020  Giành được khóa.
00:00:00.021  Lấy decisionAt từ nguồn thời gian có thẩm quyền.
00:00:00.025  Chọn chính sách theo decisionAt.
```

Ưu đãi cũ đã hết hạn theo hợp đồng này. Dùng thời điểm trước khi chờ khóa sẽ làm thao tác nhận ưu đãi dựa trên một kiểm tra không còn phù hợp với thời điểm được chọn để chốt.

Nếu `decisionAt` nằm trước ranh giới và commit xảy ra sau ranh giới, quyết định vẫn có thể hợp lệ theo đúng hợp đồng vừa nêu. Không được tự chuyển yêu cầu thành “phải commit trước hạn” mà vẫn kiểm tra bằng timestamp lấy trước commit.

### 4.2. Có thể chọn thời điểm nhận yêu cầu, nhưng phải thực thi đúng

Một cổng tiếp nhận hồ sơ có thể quy định hồ sơ hợp lệ khi được hệ thống nhận trước hạn, dù được xử lý sau đó. Khi ấy phải ghi nhận mốc tiếp nhận bằng thành phần tin cậy, gắn với đúng hồ sơ và bảo đảm hồ sơ thực sự đã được tiếp nhận bền vững theo hợp đồng.

Không chấp nhận timestamp do client gửi như một giấy chứng nhận đã nộp trước hạn. Không cho phép tạo một “vỏ hồ sơ” trước hạn rồi thay toàn bộ nội dung quan trọng sau hạn, trừ khi chính sách cho phép và kiểm soát rõ việc bổ sung.

### 4.3. Báo giá và thanh toán là hai cửa sổ khác nhau

Một báo giá có thể được cấp khi chiến dịch còn hiệu lực và được giữ trong một khoảng riêng. Cần quyết định báo giá được giữ đến `quoteExpiresAt` độc lập hay bị chặn bởi thời điểm chiến dịch kết thúc:

```text
Nếu không cho phép giữ giá qua cuối chiến dịch:
    quoteExpiresAt = min(issuedAt + holdDuration, campaign.validUntil)

Nếu cho phép giữ giá qua cuối chiến dịch:
    quoteExpiresAt được tạo theo chính sách giữ giá riêng,
    gắn với policyVersionId và snapshot báo giá đã được cấp hợp lệ.
```

Khi thanh toán, phải kiểm tra quyền sở hữu báo giá, trạng thái chưa sử dụng, hạn báo giá và các điều kiện bắt buộc còn lại. Một token hoặc URL báo giá không được biến thành quyền sửa số tiền hay dùng lại nhiều lần. Chữ ký chỉ giúp phát hiện sửa nội dung; phía server vẫn phải thực thi trạng thái và quy tắc chống dùng lại.

## 5. Viết các bất biến trước khi viết điều kiện thời gian

Các bất biến cho chính sách giá có thể gồm:

```text
validFrom < validUntil đối với khoảng hữu hạn.

Một quyết định mới chỉ dùng phiên bản có trạng thái được phép áp dụng.
Phiên bản đó phải thuộc đúng tenant và đối tượng nghiệp vụ.
validFrom <= decisionAt < validUntil.

Với cùng tenant và businessKey, không có hai phiên bản được chọn
cho cùng decisionAt, trừ khi đã định nghĩa quy tắc kết hợp rõ ràng.

Giá, policyVersionId, decisionAt và operation phải được lưu nhất quán.
Retry cùng ý định không tạo thêm tác dụng và không tự chọn lại giá.

Client không tự đặt decisionAt, lùi ngày hiệu lực hoặc chọn phiên bản hết hạn.
```

Nếu nghiệp vụ yêu cầu chính sách liên tục không có khoảng trống, đó là một bất biến bổ sung. Không chồng lấn chưa đồng nghĩa không có khoảng trống. Khi không tìm thấy phiên bản phù hợp, phải có kết quả rõ ràng: từ chối, dùng giá nền đã định nghĩa hoặc xử lý theo quy tắc dự phòng được phê duyệt.

Thời gian hợp lệ cũng không thay thế quyền và trạng thái. Một chương trình đã bị thu hồi không được áp dụng chỉ vì `decisionAt` vẫn nằm giữa hai mốc. Một người dùng của tenant B không được dùng chính sách của tenant A chỉ vì biết `policyVersionId`.

## 6. Múi giờ, giờ mùa hè và độ chính xác

### 6.1. Tách dữ liệu nhập lịch khỏi mốc dùng để so sánh

Với giao diện nhập theo ngày, nên giữ được ý định cấu hình ban đầu:

```text
startDate:       2026-12-01
endDateExclusive: 2027-01-01
businessZone:    Asia/Ho_Chi_Minh

validFrom:       2026-11-30T17:00:00Z
validUntil:      2026-12-31T17:00:00Z
```

Ngày và múi giờ giúp giải thích quy tắc; các mốc tuyệt đối giúp thực thi nhất quán. Múi giờ phải lấy từ cấu hình được phép của tenant hoặc đối tượng, không tùy thuộc múi giờ trình duyệt đang gọi API.

Một offset như `+07:00` mô tả độ lệch tại một thời điểm. Tên vùng như `Asia/Ho_Chi_Minh` thể hiện quy tắc múi giờ dùng để diễn giải lịch. Khi chính sách được định nghĩa theo lịch địa phương, không tùy tiện thay tên vùng bằng một offset cố định cho mọi thời điểm tương lai.

### 6.2. DST tạo giờ không tồn tại hoặc xuất hiện hai lần

Ở vùng có chuyển đổi giờ mùa hè, một ngày có thể dài 23 hoặc 25 giờ. Một giờ địa phương có thể không tồn tại khi đồng hồ nhảy tới, hoặc có hai offset hợp lệ khi đồng hồ lùi lại.

Với đầu vào chỉ có ngày, có thể quy định mốc là thời điểm bắt đầu hợp lệ đầu tiên của ngày trong múi giờ đó. Với đầu vào đủ ngày và giờ, phải quy định cách xử lý giờ không tồn tại và giờ nhập nhằng: từ chối để người cấu hình chọn lại, hoặc yêu cầu lựa chọn offset hợp lệ cụ thể.

Không để hành vi mặc định khác nhau giữa thư viện frontend và backend âm thầm quyết định ngày hiệu lực. Nếu một ngày lịch bị bỏ qua do thay đổi múi giờ, cần kiểm tra kết quả chuyển đổi và các bất biến, thay vì mặc định mọi ngày nhập đều tạo thành một khoảng có độ dài dương.

### 6.3. Chuẩn hóa độ chính xác có chủ đích

Java `Instant` có phần nano giây, còn nơi lưu trữ hoặc giao thức có thể chỉ giữ mili giây hay micro giây. Phải xác định độ chính xác được hỗ trợ và quy tắc chấp nhận đầu vào.

- Chuẩn hóa hoặc từ chối độ chính xác vượt hợp đồng ngay khi cấu hình chính sách.
- Đọc lại các mốc đã lưu và kiểm tra vẫn còn `validFrom < validUntil`.
- Kiểm tra các mốc đúng ranh giới theo độ chính xác thực sự đi qua API, driver và database.
- Nếu làm tròn làm đổi ý nghĩa ranh giới, phải báo lỗi hoặc yêu cầu cấu hình lại, không âm thầm nới hạn.

Khi dùng epoch, đơn vị phải rõ ràng. Epoch giây bị đọc thành mili giây hoặc ngược lại có thể làm hạn hiệu lực lệch rất xa. Kiểm tra kiểu dữ liệu, đơn vị, khoảng giá trị và lỗi tràn; không chỉ kiểm tra trường có phải một số hay không.

### 6.4. Quy tắc múi giờ có thể thay đổi

Với lịch tương lai, cần chọn một trong các ý nghĩa: giữ cố định `Instant` đã phê duyệt, hoặc giữ ý định giờ địa phương và cho phép tính lại khi quy tắc múi giờ thay đổi. Lựa chọn phải được ghi rõ trong chính sách quản trị.

Nếu tính lại làm thay đổi thời điểm hiệu lực, nên tạo phiên bản điều chỉnh và ghi audit thay vì âm thầm thay lịch đã công bố. Với quyết định đã thực hiện, cần lưu mốc tuyệt đối và phiên bản đã dùng để không diễn giải lại lịch sử bằng quy tắc mới.

## 7. Biểu diễn cửa sổ hiệu lực trong Java

### 7.1. Một kiểu dữ liệu có bất biến rõ ràng

Ví dụ dùng Java record và `java.time`; record yêu cầu phiên bản Java hỗ trợ cú pháp này. Kiểu dữ liệu dưới đây chỉ mô hình hóa khoảng hữu hạn, chưa bao gồm quyền, trạng thái hay giao dịch.

```java
import java.time.Instant;
import java.util.Objects;

public record EffectiveWindow(Instant from, Instant until) {
    public EffectiveWindow {
        Objects.requireNonNull(from, "from");
        Objects.requireNonNull(until, "until");
        if (!from.isBefore(until)) {
            throw new IllegalArgumentException("from must be before until");
        }
    }

    public boolean contains(Instant decisionAt) {
        Objects.requireNonNull(decisionAt, "decisionAt");
        return !decisionAt.isBefore(from) && decisionAt.isBefore(until);
    }
}
```

Không dùng `decisionAt <= until` cho một nhánh và `< until` cho nhánh khác. Việc gom phép kiểm tra vào một kiểu dữ liệu giúp giảm sai lệch, nhưng truy vấn SQL, consumer và công cụ quản trị cũng phải dùng cùng quy ước.

### 7.2. Chuyển ngày lịch sang mốc tuyệt đối

```java
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.Objects;

public final class EffectiveWindows {
    private EffectiveWindows() {}

    public static EffectiveWindow forDates(
            LocalDate startDate,
            LocalDate endDateExclusive,
            ZoneId businessZone) {

        Objects.requireNonNull(startDate, "startDate");
        Objects.requireNonNull(endDateExclusive, "endDateExclusive");
        Objects.requireNonNull(businessZone, "businessZone");
        if (!startDate.isBefore(endDateExclusive)) {
            throw new IllegalArgumentException("invalid date range");
        }

        return new EffectiveWindow(
                startDate.atStartOfDay(businessZone).toInstant(),
                endDateExclusive.atStartOfDay(businessZone).toInstant());
    }
}
```

`atStartOfDay(zone)` chọn thời điểm bắt đầu hợp lệ của ngày theo quy tắc vùng; không phải lời khẳng định rằng luôn có đúng 00:00 tại mọi ngày và mọi vùng. Constructor của `EffectiveWindow` tiếp tục chặn kết quả không tạo thành khoảng tăng nghiêm ngặt. Nếu hợp đồng bắt buộc từ chối mọi ngày bị điều chỉnh so với giờ nhập, cần kiểm tra bổ sung thay vì chỉ dựa vào phương thức này.

Nếu người dùng nhập ngày kết thúc bao gồm cả ngày đó, chuyển sang `endDateExclusive = inclusiveEndDate.plusDays(1)` sau khi kiểm tra miền dữ liệu được hỗ trợ. Không cộng 24 giờ vào một `Instant` để thay cho “ngày lịch kế tiếp” tại mọi múi giờ.

### 7.3. Lấy thời gian một lần cho một quyết định

```java
import java.time.Clock;
import java.time.Instant;

public final class WindowDecision {
    private final Clock clock;

    public WindowDecision(Clock clock) {
        this.clock = clock;
    }

    public boolean isEffective(EffectiveWindow window) {
        Instant decisionAt = clock.instant();
        return window.contains(decisionAt);
    }
}
```

Tiêm `Clock` giúp kiểm thử đúng mốc mà không phải đợi thời gian thật. Trong dịch vụ đầy đủ, phải gọi nó ở đúng thời điểm mà hợp đồng đã chọn. Nếu database là nguồn thời gian có thẩm quyền cho giao dịch, dùng mốc do database trả về thay cho việc lấy thêm thời gian độc lập từ JVM.

Không viết kiểm tra bằng hai lần đọc đồng hồ:

```java
// Hai phép kiểm tra có thể quan sát hai thời điểm khác nhau.
boolean effective = !clock.instant().isBefore(window.from())
        && clock.instant().isBefore(window.until());
```

Dù khoảng chỉ dài vài mili giây, mỗi quyết định vẫn cần một `decisionAt` duy nhất để so sánh, lưu kết quả và giải thích về sau.

## 8. Gắn kiểm tra thời gian với giao dịch và phiên bản

### 8.1. Kiểm tra trước rồi dùng sau là một khoảng hở

```text
T1: Kiểm tra ưu đãi còn hạn.
T2: Chờ khóa, gọi dịch vụ ngoài hoặc đứng trong hàng đợi.
T3: Tạo đơn bằng giá ưu đãi đã kiểm tra ở T1.
```

Nếu hợp đồng yêu cầu chốt tại T3, phép kiểm tra T1 không đủ. Ngoài việc đi qua ranh giới thời gian, chính sách có thể bị thu hồi hoặc thay phiên bản trong khoảng chờ.

Cần đặt điểm quyết định trong giao dịch ghi kết quả, phối hợp với những thay đổi chính sách liên quan. Một cách làm là khóa một bản ghi phạm vi chính sách tồn tại sẵn cho `(tenantId, businessKey)`. Cả thao tác xuất bản, thu hồi và chọn phiên bản để áp dụng đều tuân thủ cùng quy tắc phối hợp.

Chỉ khóa phiên bản đang có chưa chắc ngăn được một phiên bản chồng lấn mới được chèn. Khóa một truy vấn trả về không dòng cũng không tự tạo “khóa cho sự vắng mặt” trong mọi cơ chế database. Cần khóa phạm vi cha, ràng buộc chống chồng lấn hoặc mức cô lập với quy tắc retry phù hợp.

### 8.2. Phác thảo một giao dịch có điểm quyết định rõ ràng

SQL dưới đây minh họa cú pháp PostgreSQL và thứ tự thao tác. Các biến có dấu `:` là tham số do backend kiểm soát; đây chưa phải triển khai đầy đủ.

```sql
BEGIN;

-- Mọi đường thay đổi lịch của businessKey cùng phối hợp qua bản ghi này.
SELECT business_key
FROM policy_scope
WHERE tenant_id = :trusted_tenant_id
  AND business_key = :business_key
FOR UPDATE;

-- Lấy đúng một mốc sau khi đã giành các khóa quyết định cần thiết.
SELECT clock_timestamp() AS decision_at;

-- Backend dùng chính giá trị vừa nhận làm :decision_at.
SELECT policy_version_id, price, currency
FROM price_policy_version
WHERE tenant_id = :trusted_tenant_id
  AND business_key = :business_key
  AND publication_state = 'PUBLISHED'
  AND valid_from <= :decision_at
  AND :decision_at < valid_until;

-- Xác nhận chỉ có đúng một phiên bản, hoặc xử lý không có phiên bản
-- theo chính sách. Nếu có nhiều phiên bản ngoài dự kiến: không chọn tùy ý.
-- Ghi operation, decision_at, policy_version_id, snapshot giá và outbox
-- trong cùng giao dịch, sau khi kiểm tra các điều kiện nghiệp vụ khác.

COMMIT;
```

Trong PostgreSQL, `CURRENT_TIMESTAMP` và `now()` biểu diễn mốc đầu giao dịch; một giao dịch chờ lâu không tự làm các giá trị đó tiến tới thời điểm vừa giành được khóa. `statement_timestamp()` gắn với mốc bắt đầu statement. `clock_timestamp()` đọc thời gian đồng hồ tại lúc gọi. Khi cần thời gian sau chờ khóa, phải chọn đúng hàm và vị trí gọi, rồi giữ lại một kết quả duy nhất.

Không gọi `clock_timestamp()` độc lập ở từng vế điều kiện hoặc từng dòng để rồi lưu một timestamp khác làm bằng chứng quyết định. Mã giả trên lấy mốc qua một lệnh riêng sau thao tác khóa. Những khóa bổ sung bắt buộc cho điểm quyết định cũng phải được giành trước mốc đó theo thứ tự nhất quán.

Giao dịch vẫn cần xử lý idempotency, quyền đối tượng, kiểm tra số lượng dòng và rollback khi thất bại. Nếu bản ghi `policy_scope` không tồn tại, phải xử lý rõ ràng; không được tiếp tục như thể đã khóa được phạm vi.

### 8.3. Không gọi dịch vụ ngoài dưới giả định transaction bao trùm mọi thứ

Một database transaction không tự rollback được khoản tiền đã thu ở nhà cung cấp khác. Có thể ghi đơn, snapshot và sự kiện outbox trước, rồi thực hiện thanh toán theo state machine có điều kiện của báo giá hoặc đơn.

Nếu thanh toán cần một cửa sổ hiệu lực riêng, phải kiểm tra cửa sổ đó tại chuyển trạng thái tương ứng. Không lấy việc transaction tạo đơn đã thành công để suy ra rằng mọi hành động tương lai đều được miễn kiểm tra hạn.

## 9. Phiên bản lịch, chồng lấn và lùi ngày hiệu lực

### 9.1. Một phiên bản được phê duyệt không nên bị sửa âm thầm

Thay đổi giá, ngày hiệu lực hoặc phạm vi áp dụng của phiên bản đã xuất bản có thể làm lịch sử không còn giải thích được. Nên tạo phiên bản thay thế với người sửa, lý do, phạm vi, thời điểm ghi nhận và quy trình phê duyệt tương ứng.

```text
DRAFT -> APPROVED -> PUBLISHED
                       |
                       +-> REVOKED

Trạng thái thời gian tại decisionAt được suy ra riêng:
    SCHEDULED: decisionAt < validFrom
    EFFECTIVE: validFrom <= decisionAt < validUntil
    ENDED:     validUntil <= decisionAt
```

`PUBLISHED` thể hiện đã được phép đưa vào lịch, không có nghĩa luôn đang hiệu lực. Tương tự, việc nằm trong khoảng thời gian không tự chuyển bản nháp thành chính sách đã phê duyệt.

### 9.2. Chống chồng lấn phải bao phủ cập nhật đồng thời

Hai quản trị viên có thể cùng đọc thấy “không có khoảng chồng lấn”, rồi mỗi người chèn một phiên bản mới. Kiểm tra bằng truy vấn trước khi ghi mà không có cơ chế chống cạnh tranh không bảo vệ được bất biến.

Đường xuất bản cần phối hợp theo đúng `(tenantId, businessKey)` và kiểm tra tất cả khoảng liên quan trong cùng cơ chế bảo vệ. Nếu database hỗ trợ ràng buộc chống giao nhau phù hợp mô hình dữ liệu, có thể dùng thêm ràng buộc đó làm lớp bảo vệ. Nếu chính sách cho phép nhiều lớp ưu đãi cùng hiệu lực, phải định nghĩa thứ tự hoặc phép kết hợp rõ ràng thay vì dùng “bản ghi đọc được đầu tiên”.

### 9.3. Lùi ngày hiệu lực là quyền nghiệp vụ riêng

Cho phép sửa `validFrom` về quá khứ có thể làm phát sinh hoàn tiền, tính lại phí hoặc thay đổi kết quả duyệt trước đây. Không nên trao quyền này chỉ vì người dùng có quyền chỉnh tên chương trình.

Cần tách **thời gian có hiệu lực trong nghiệp vụ** khỏi **thời gian hệ thống ghi nhận thay đổi**:

```text
validFrom / validUntil: thay đổi được quy định áp dụng cho giai đoạn nào
recordedAt:             hệ thống biết và ghi nhận thay đổi lúc nào
decisionAt:             thao tác cụ thể đã chọn chính sách lúc nào
```

Ví dụ một quyết định điều chỉnh được ghi nhận ngày 10 nhưng có hiệu lực từ ngày 01. Điều đó không có nghĩa hệ thống đã biết chính sách này ở ngày 05. Khi cần điều chỉnh giao dịch cũ, thực hiện quy trình điều chỉnh có tham chiếu, không ghi đè snapshot để làm như giá mới đã luôn được áp dụng.

Quyền lùi ngày cần phạm vi, lý do, phê duyệt và audit phù hợp. Không nhận trường `effectiveAt` tùy ý trong API mua hàng thông thường rồi dùng nó thay cho thời điểm quyết định của server.

## 10. Retry, hàng đợi và sự kiện đến muộn

### 10.1. Retry không phải một quyết định mới nếu kết quả đã được chốt

Giả sử lần đầu tạo đơn thành công lúc 23:59:59 nhưng response bị mất. Người dùng retry cùng idempotency key lúc 00:00:01. Nếu hệ thống kiểm tra ưu đãi hiện tại trước khi tra kết quả cũ, nó có thể trả “hết hạn” dù đơn ưu đãi đã được tạo, khiến người dùng tiếp tục gửi yêu cầu mới hoặc bị thu tiền lần nữa.

Luồng xử lý nên phân biệt phát lại kết quả đã có với thực hiện tác dụng mới:

```text
1. Xác thực người gọi và quyền đối với operation liên quan.
2. Tra idempotency theo tenant, loại thao tác và key.
3. Đối chiếu hash của các tham số nghiệp vụ đã chuẩn hóa.
4. Nếu có kết quả cuối đã lưu: trả lại theo hợp đồng API, không tạo đơn mới.
5. Nếu chưa có quyết định cuối: phối hợp xử lý và kiểm tra hiệu lực
   tại điểm quyết định được quy định cho lần thực thi này.
6. Lưu kết quả, snapshot chính sách và tác dụng nghiệp vụ nguyên tử.
```

Cùng key nhưng khác nội dung phải bị xử lý như xung đột, không được lấy snapshot giá cũ để mua một sản phẩm hay số lượng khác. Phát lại kết quả cũng không cấp quyền xem dữ liệu của operation cho một chủ thể đã mất quyền truy cập; cần kiểm tra quyền trả kết quả theo hợp đồng bảo mật hiện hành.

Tạo một bản ghi `IN_PROGRESS` trước hạn không tự giữ ưu đãi. Nếu nghiệp vụ muốn giữ quyền tại lúc tiếp nhận, phải tạo một reservation hoặc báo giá được cấp hợp lệ, với snapshot, thời hạn và giới hạn sử dụng riêng.

Thời gian lưu chống trùng phải bao phủ cửa sổ retry và delivery liên quan. Nếu xóa idempotency record trong khi một sự kiện cũ vẫn có thể được phát lại, cần ràng buộc nghiệp vụ hoặc dấu vết operation đủ để không tạo thêm tác dụng. “Key hết hạn” không có nghĩa một lần mua đã hoàn tất được phép thực hiện lại ngoài ý muốn.

### 10.2. Vào hàng đợi trước hạn chưa chắc được thực hiện sau hạn

Nếu hợp đồng dùng `decisionAt` tại consumer, thời điểm enqueue không quyết định quyền lợi. Consumer phải kiểm tra tại điểm chốt, không tin một trường `eligible=true` từ bước API chạy trước đó.

Nếu hợp đồng dùng thời điểm tiếp nhận bền vững, consumer có thể xử lý sau hạn dựa trên receipt tin cậy. Receipt phải gắn với nội dung đã được chốt và không cho client tùy ý sửa mốc hoặc thay payload sau đó.

Hai mô hình đều có thể hợp lệ. Lỗi xuất hiện khi API dùng một mô hình còn consumer dùng mô hình khác, hoặc khi retry vô tình thay đổi mốc căn cứ.

### 10.3. Event time và processing time

Webhook thanh toán có thể đến sau ranh giới, trong khi nhà cung cấp ghi nhận một sự kiện trước ranh giới. Cần định nghĩa chính xác sự kiện nào có ý nghĩa: khởi tạo thanh toán, ủy quyền, thu tiền thành công hay một trạng thái khác. Không thể thay thế chúng chỉ vì tất cả đều có timestamp.

Nếu cho phép dùng thời gian từ nhà cung cấp, cần:

- Xác minh nguồn và tính toàn vẹn thông báo theo giao thức của nhà cung cấp.
- Đối chiếu tenant, đơn, số tiền, loại tiền và mã sự kiện.
- Ghi riêng `providerEventAt`, `receivedAt` và `processedAt`.
- Quy định cửa sổ chấp nhận sự kiện đến muộn và cách xử lý sự kiện không hợp lệ.
- Chống trùng và chống chuyển trạng thái lùi khi sự kiện đến sai thứ tự.

Thông báo có chữ ký hợp lệ không tự chứng minh rằng mọi loại timestamp trong đó đều phù hợp làm mốc nghiệp vụ. Phải biết ngữ nghĩa của trường được chọn. Một timestamp do người dùng chèn vào metadata không trở thành thời gian có thẩm quyền chỉ vì nó được gửi lại trong webhook.

Nếu thêm thời gian gia hạn, hãy biểu diễn nó thành cửa sổ nghiệp vụ được phê duyệt. Ví dụ thời hạn nhận thông báo có thể khác thời hạn sự kiện được phép xảy ra. Không rải các phép cộng “thêm 30 giây cho chắc” ở nhiều nơi, vì chúng âm thầm thay đổi ranh giới hiệu lực.

## 11. Các đường lạm dụng thường gặp

| Hành vi | Lỗ hổng bị khai thác | Cách bảo vệ |
| --- | --- | --- |
| Đổi đồng hồ điện thoại | Backend tin `clientSentAt` | Lấy thời gian từ nguồn có thẩm quyền; timestamp client chỉ hỗ trợ chẩn đoán |
| Đổi offset hoặc múi giờ request | Cùng ngày được diễn giải khác nhau | Múi giờ nghiệp vụ do server kiểm soát, định dạng API rõ ràng |
| Gửi request trước hạn rồi cố tình giữ xử lý lâu | Kiểm tra ở đầu request, dùng kết quả sau chờ | Chốt rõ điểm quyết định hoặc tạo reservation có hạn |
| Gọi trực tiếp API sau khi nút đã bị khóa | Chỉ frontend kiểm tra countdown | Backend thực thi điều kiện tại thao tác gây tác dụng |
| Chọn thủ công phiên bản giá cũ | Server tin `policyVersionId` từ client | Server chọn phiên bản; kiểm tra tenant, trạng thái và cửa sổ hiệu lực |
| Retry qua ranh giới để tạo nhiều kết quả | Chống trùng không gắn với tác dụng nghiệp vụ | Idempotency, định danh operation và ràng buộc duy nhất |
| Xuất bản hai khoảng chồng lấn đồng thời | Kiểm tra giao nhau không có cơ chế đồng bộ | Phối hợp cấp phạm vi, transaction và ràng buộc phù hợp |
| Sửa lùi ngày chương trình | Quyền sửa cấu hình quá rộng | Tách quyền lùi ngày, phê duyệt và audit |
| Dùng cache ưu đãi đã thu hồi | Quyết định dựa trên cache không còn hợp lệ | Kiểm tra trạng thái hoặc phiên bản tại nguồn có thẩm quyền |
| Dùng lại báo giá đã thanh toán | Token đúng chữ ký nhưng không có trạng thái sử dụng | Kiểm tra ownership, hạn và chuyển trạng thái nguyên tử |

Những thao tác này thường dùng đúng endpoint và kiểu dữ liệu hợp lệ. Kiểm thử chỉ tìm chuỗi SQL injection hoặc quyền truy cập route sẽ không phát hiện đầy đủ lỗi về thời gian và thứ tự nghiệp vụ.

## 12. Kiểm thử ranh giới bằng đồng hồ điều khiển được

### 12.1. Ma trận tối thiểu cho một khoảng hữu hạn

Với `from < until`, chọn `epsilon` phù hợp độ chính xác được hỗ trợ và nhỏ hơn độ dài khoảng:

| Mốc kiểm thử | Kết quả mong đợi |
| --- | --- |
| `from - epsilon` | Chưa hiệu lực |
| `from` | Có hiệu lực |
| `from + epsilon` | Có hiệu lực, nếu vẫn nhỏ hơn `until` |
| `until - epsilon` | Có hiệu lực |
| `until` | Hết hiệu lực |
| `until + epsilon` | Hết hiệu lực |
| `from == until` | Cấu hình không hợp lệ |
| `from > until` | Cấu hình không hợp lệ |

Nếu phần kiểm tra thuần Java dùng nano giây nhưng database chỉ lưu micro giây, cần có cả kiểm thử qua lưu trữ với `epsilon` tương ứng. Một bộ unit test đúng trong bộ nhớ không chứng minh phép round-trip qua database giữ nguyên ranh giới.

Ví dụ tạo đồng hồ cố định cho đúng mốc kết thúc:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Instant from = Instant.parse("2026-11-30T17:00:00Z");
Instant until = Instant.parse("2026-12-31T17:00:00Z");
EffectiveWindow window = new EffectiveWindow(from, until);

Clock atEnd = Clock.fixed(until, ZoneOffset.UTC);
WindowDecision decision = new WindowDecision(atEnd);

// Giá trị cần được xác nhận là false trong bộ kiểm thử.
boolean effectiveAtEnd = decision.isEffective(window);
```

Không dùng `sleep` để hy vọng kiểm thử chạy đúng vào nửa đêm. Đồng hồ điều khiển được giúp tái hiện mốc chính xác; kiểm thử giao dịch cần thêm cách điều khiển thứ tự khóa và sự kiện.

### 12.2. Kiểm thử lịch, parser và múi giờ

- Chuyển ngày theo múi giờ nghiệp vụ đã cấu hình; thay múi giờ mặc định JVM không làm đổi kết quả.
- Một chuỗi có `Z` và một chuỗi có offset khác nhưng biểu diễn cùng `Instant` phải cho cùng kết quả.
- Ngày đổi tháng, đổi năm và ngày nhuận được chuyển theo lịch, không bằng số giây cố định.
- Ngày chuyển DST được kiểm tra cả mốc bắt đầu và kết thúc; không mặc định độ dài 24 giờ.
- Giờ địa phương không tồn tại hoặc có hai offset được xử lý theo chính sách nhập liệu đã công bố.
- Input thiếu offset khi API yêu cầu timestamp tuyệt đối, sai đơn vị epoch hoặc vượt miền cho phép phải bị từ chối rõ ràng.
- Mốc sau lưu và đọc lại vẫn giữ đúng độ chính xác, thứ tự và kết quả bao gồm/loại trừ tại đầu mút.

### 12.3. Kiểm thử cạnh tranh và đi qua hạn

| Lịch sự kiện | Điều cần chứng minh |
| --- | --- |
| Request đến trước hạn, giành khóa sau hạn | Chọn mốc theo hợp đồng; không dùng nhầm thời gian trước chờ |
| Quyết định trước hạn, commit sau hạn | Kết quả tuân thủ chính sách decision-time đã định nghĩa |
| Hai admin xuất bản hai khoảng giao nhau | Không thể cùng commit thành một lịch trái bất biến |
| Thu hồi chính sách đua với tạo đơn | Hai thao tác có thứ tự nhất quán; kết quả gắn với phiên bản đã chốt |
| Retry sau hạn của một operation thành công trước hạn | Không tạo đơn hoặc khoản thu mới; trả kết quả cũ nếu còn quyền xem |
| Request trước hạn mới chỉ có `IN_PROGRESS` | Không tự được coi là đã giữ ưu đãi |
| Webhook đến sau hạn nhưng sự kiện đủ điều kiện trước hạn | Áp dụng đúng quy tắc event-time và cửa sổ nhận muộn |
| Webhook bị gửi lặp hoặc đảo thứ tự | Không ghi hai lần hoặc phục hồi một trạng thái đã kết thúc trái phép |
| Cache vẫn hiển thị chính sách cũ | Thao tác gây tác dụng vẫn dùng kiểm tra có thẩm quyền |
| Client gửi thời điểm quá khứ và policy ID cũ | Không được lùi điểm quyết định hoặc vượt quyền đối tượng |

Một kịch bản đối kháng hữu ích:

```text
Given:
    V1 có hiệu lực [t0, t1)
    V2 có hiệu lực [t1, t2)
    hợp đồng chọn decisionAt sau khi giành khóa

When:
    request X vào hệ thống trước t1
    X bị chặn ở khóa cho đến sau t1
    X được chốt, nhưng response bị mất
    client retry cùng key và cùng nội dung

Then:
    X chỉ tạo một operation
    snapshot của X dùng V2
    retry không chuyển X về V1 và không tạo thêm đơn
    audit giải thích được decisionAt và phiên bản đã chọn
```

Kiểm thử thêm trường hợp quyền trên đối tượng bị thu hồi trong lúc chờ. Một phép kiểm tra thời gian đúng không được che mất điều kiện authorization đã thay đổi.

## 13. Vận hành: đồng hồ, cache và tác vụ nền

### 13.1. Nguồn thời gian phải có ý nghĩa thống nhất

Lưu theo UTC giúp thống nhất cách biểu diễn; nó không tự đồng bộ đồng hồ giữa các máy. Nếu các instance lệch giờ, cùng một `Instant` kết thúc vẫn có thể cho kết quả khác nhau khi mỗi instance tự lấy “bây giờ”.

Chọn nguồn thời gian có thẩm quyền phù hợp với ranh giới giao dịch, theo dõi độ lệch và quy định cách xử lý khi độ tin cậy của đồng hồ không còn đáp ứng yêu cầu. Có thể tạm ngừng các thao tác nhạy cảm với ranh giới hoặc dùng nguồn đã được xác định, thay vì mặc định cộng dung sai để mọi request đều được qua.

Đồng hồ thời gian thực có thể bị điều chỉnh tiến hoặc lùi. Các chuyển trạng thái đã kết thúc không được tự mở lại chỉ vì một phép kiểm tra thời gian sau đó cho kết quả khác. Với đo thời lượng cục bộ như timeout của một lần chờ, có thể dùng đồng hồ đơn điệu thích hợp; giá trị đó không thay thế timestamp tuyệt đối dùng cho lịch nghiệp vụ và không được đem lưu rồi so sánh tùy ý giữa các tiến trình.

### 13.2. Cron không phải cơ chế xác thực hiệu lực

Một tác vụ chạy lúc nửa đêm có thể bị trễ, chạy lại hoặc dừng. Không nên dựa duy nhất vào cờ `active=true` mà cron chưa kịp đổi. Tại thời điểm gây tác dụng, vẫn phải kiểm tra khoảng hiệu lực và trạng thái được phép áp dụng.

Cron có thể phục vụ thông báo, làm mới cache hoặc dọn dữ liệu. Nếu chủ động vật chất hóa trạng thái hiệu lực để tối ưu, cần có cơ chế bảo vệ tại ranh giới tương đương với bất biến; không mặc định việc cron “thường chạy đúng giờ” là bằng chứng bảo mật.

Cache có TTL đến `validUntil` cũng chưa đủ xử lý thu hồi sớm hoặc thay đổi chính sách. Cần quy tắc vô hiệu hóa, phiên bản hóa và kiểm tra cuối phù hợp với yêu cầu nhất quán. Cache hiển thị và quyết định tính giá có thể có mức trễ chấp nhận khác nhau.

### 13.3. Audit phải tái dựng được quyết định

Một quyết định quan trọng nên lưu đủ thông tin:

```text
operationId, tenantId, businessObjectId
policyVersionId, policyRevision
validFrom, validUntil, businessZone
decisionAt, timeSource
snapshot giá hoặc điều kiện đã áp dụng
receiptAt / providerEventAt nếu thực sự là căn cứ liên quan
kết quả và mã lý do
```

Không ghi đè `decisionAt` bằng thời gian retry. Không dựng lại giá lịch sử chỉ bằng cách truy vấn phiên bản đang hiệu lực hôm nay. Snapshot và tham chiếu phiên bản phải được lưu cùng kết quả nghiệp vụ, có quy tắc lưu giữ phù hợp.

Các chỉ số hữu ích gồm số lần từ chối vì chưa tới hạn hoặc đã hết hạn, chênh lệch giữa tiếp nhận và quyết định, thời gian chờ khóa gần ranh giới, số khoảng chồng lấn bị chặn và độ trễ webhook. Khi cần điều tra, log phải cho biết quy tắc nào đã được dùng; tránh đưa dữ liệu nhạy cảm hoặc token thanh toán vào log.

## 14. Bài tập thiết kế

Thiết kế API áp dụng giá cho một chương trình có ngày bắt đầu và ngày kết thúc theo múi giờ tenant. Người dùng có thể tạo báo giá, trả tiền sau đó và retry khi mất response. Quản trị viên có thể thu hồi chương trình trước hạn.

Hãy đưa ra các quyết định sau:

1. Ngày kết thúc trên giao diện được chuyển thành mốc loại trừ như thế nào?
2. Tại tạo báo giá và tại thanh toán, mốc nào quyết định quyền lợi?
3. Báo giá có được giữ qua cuối chiến dịch không, và tối đa đến khi nào?
4. Thu hồi chương trình có vô hiệu hóa báo giá đã cấp không? Nếu có, phối hợp trạng thái ra sao?
5. Retry cùng key sau hạn trả kết quả gì khi lần đầu đã thành công, đang xử lý hoặc chưa được chốt?
6. Quyền sửa lịch tương lai và quyền lùi ngày có khác nhau không?
7. Giao dịch, ràng buộc dữ liệu và audit nào bảo vệ các bất biến?

Một thiết kế đạt yêu cầu phải trả lời được những câu hỏi này bằng quy tắc có thể kiểm thử. Chỉ nói “lưu UTC” hoặc “so sánh với ngày hiện tại” chưa đủ xác định hành vi khi có chờ khóa, thu hồi, retry hoặc sự kiện đến muộn.

## 15. Ghi nhớ

Ranh giới ngày hiệu lực là một phần của quyền thực hiện nghiệp vụ. Để bảo vệ nó, cần chọn rõ múi giờ và ý nghĩa ngày, thống nhất khoảng `[from, until)`, xác định nguồn thời gian và điểm quyết định có thẩm quyền.

Kiểm tra thời gian phải đi cùng phiên bản chính sách, trạng thái phê duyệt, quyền trên đối tượng và giao dịch ghi tác dụng. Idempotency giữ nguyên một kết quả đã chốt; reservation và báo giá tạo quyền có thời hạn riêng; audit lưu lại căn cứ thực tế. Khi những phần này được nối đúng, việc đi qua nửa đêm, chờ khóa hoặc gửi lại yêu cầu không còn trở thành cách thay đổi quyền lợi ngoài chính sách.
