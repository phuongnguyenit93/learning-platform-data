# `InstantSource` khi chỉ cần nguồn cung cấp thời điểm

## Khi một lớp không cần biết múi giờ

Một lớp kiểm tra bài nộp có quá hạn hay không chỉ cần biết:

```text
thời điểm hiện tại có đạt hoặc vượt thời điểm hết hạn không?
```

Nếu cả hai giá trị đều là `Instant`, lớp không cần tự chọn ngày theo Việt Nam, UTC hay một vùng nào khác. Truyền cả một `Clock` vẫn làm được, nhưng phạm vi phụ thuộc rộng hơn nhu cầu: Clock còn có vùng để suy ra ngày giờ địa phương.

Từ Java 17, `InstantSource` cung cấp một giao diện tập trung vào **nguồn thời điểm**. Lớp nghiệp vụ có thể nhận nguồn này từ bên ngoài, dùng thời gian hệ thống khi chạy thật và dùng mốc cố định khi kiểm thử.

## 1. `InstantSource` cung cấp điều gì?

Lời gọi cốt lõi:

```java
Instant now = source.instant();
```

`source` là một `InstantSource`. Nó có thể trả về thời gian hệ thống, một thời điểm cố định hoặc một nguồn khác theo cấu hình.

Các khả năng chính:

| API | Ý nghĩa |
| --- | --- |
| `instant()` | Đọc một `Instant` từ nguồn |
| `millis()` | Đọc giá trị thời điểm ở độ chi tiết mili giây |
| `system()` | Tạo nguồn dựa trên đồng hồ hệ thống |
| `fixed(instant)` | Tạo nguồn luôn trả cùng mốc |
| `offset(base, duration)` | Tạo nguồn trả mốc của nguồn gốc cộng độ dời |
| `tick(base, duration)` | Tạo nguồn có mốc bị cắt theo nhịp cấu hình |
| `withZone(zone)` | Tạo `Clock` mang vùng khi cần dùng ngày giờ địa phương |

Giao diện không có `getZone()`. Nó mô tả việc lấy thời điểm, không tự định nghĩa “hôm nay ở đâu”. Nguồn cũng không bắt buộc phải trả thời gian thực đang trôi; một nguồn cố định là cách dùng hợp lệ để kiểm thử. [Tài liệu `InstantSource`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/InstantSource.html)

Có thể hình dung:

```text
InstantSource
     │
     └── instant() → Instant
                         │
                         └── chỉ khi cần ngày/giờ:
                             chọn ZoneId hoặc tạo Clock bằng withZone
```

## 2. Chọn `InstantSource`, `Clock` hay `Instant`?

Ba kiểu này phục vụ ba nhu cầu:

| Nhu cầu của nơi nhận | Đầu vào thường phù hợp |
| --- | --- |
| Chỉ xử lý một mốc đã được quan sát | `Instant` |
| Tự quyết định lúc nào cần đọc “bây giờ”, chỉ cần mốc | `InstantSource` |
| Cần cả nguồn “bây giờ” và vùng để suy ra ngày/giờ | `Clock` |

Ví dụ:

- Một hàm thuần nhận `now` và `expiresAt` để so sánh có thể chỉ cần hai `Instant`.
- Một dịch vụ phải ghi thời điểm tạo bản ghi mỗi lần gọi có thể nhận `InstantSource`.
- Một dịch vụ xác định ngày đăng ký theo vùng nghiệp vụ có thể nhận `Clock`, hoặc nhận riêng nguồn thời điểm và vùng nếu đó là thiết kế rõ ràng hơn.

Không cần thay mọi `Clock` trong hệ thống chỉ để dùng kiểu mới. Chọn kiểu theo thông tin mà lớp thực sự cần.

`Clock` triển khai `InstantSource`, nên một Clock có sẵn có thể được truyền vào nơi nhận `InstantSource` mà không cần bộ chuyển đổi. [Tài liệu `Clock`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html)

```java
InstantSource source = Clock.systemUTC();
```

Đây là đoạn minh họa, cần import `InstantSource` và `Clock`.

Mặc dù đối tượng thực tế có thể là Clock, mã nhận kiểu `InstantSource` nên dùng đúng hợp đồng thời điểm thay vì ép kiểu về Clock để lấy vùng.

## 3. Chương trình hoàn chỉnh: tạo và kiểm tra hạn theo mốc thời gian

Ví dụ quy định một cửa sổ nộp bài mở tại `issuedAt` và hết hạn tại `expiresAt`. Khi thời điểm hiện tại **bằng** `expiresAt`, bài đã quá hạn. Khoảng hiệu lực được hiểu là `[issuedAt, expiresAt)`.

Lưu dưới tên `InstantSourceDemo.java`. Chương trình yêu cầu Java 17 trở lên:

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.InstantSource;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.Objects;

public class InstantSourceDemo {
    record SubmissionWindow(Instant issuedAt, Instant expiresAt) {}

    static final class SubmissionService {
        private final InstantSource source;

        SubmissionService(InstantSource source) {
            this.source = Objects.requireNonNull(source);
        }

        SubmissionWindow openWindow(Duration validity) {
            Objects.requireNonNull(validity);
            if (validity.isNegative() || validity.isZero()) {
                throw new IllegalArgumentException("Thoi han phai duong");
            }

            Instant issuedAt = source.instant();
            return new SubmissionWindow(
                    issuedAt, issuedAt.plus(validity));
        }

        boolean isExpired(SubmissionWindow window) {
            Instant now = source.instant();
            return !now.isBefore(window.expiresAt());
        }
    }

    public static void main(String[] args) {
        Instant observedAt = Instant.parse("2024-06-15T18:30:00Z");
        InstantSource fixed = InstantSource.fixed(observedAt);

        SubmissionService service = new SubmissionService(fixed);
        SubmissionWindow window =
                service.openWindow(Duration.ofMinutes(10));

        System.out.println("issuedAt=" + window.issuedAt());
        System.out.println("expiresAt=" + window.expiresAt());
        System.out.println("expiredAtIssue=" + service.isExpired(window));

        InstantSource justBefore = InstantSource.fixed(
                window.expiresAt().minusNanos(1));
        InstantSource atBoundary =
                InstantSource.fixed(window.expiresAt());
        InstantSource justAfter = InstantSource.fixed(
                window.expiresAt().plusNanos(1));

        System.out.println("expiredJustBefore="
                + new SubmissionService(justBefore).isExpired(window));
        System.out.println("expiredAtBoundary="
                + new SubmissionService(atBoundary).isExpired(window));
        System.out.println("expiredJustAfter="
                + new SubmissionService(justAfter).isExpired(window));

        InstantSource shifted =
                InstantSource.offset(fixed, Duration.ofMinutes(10));
        System.out.println("shiftedInstant=" + shifted.instant());
        System.out.println("originalUnchanged=" + fixed.instant());

        ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
        Clock clockView = fixed.withZone(vietnam);

        System.out.println("clockViewInstant=" + clockView.instant());
        System.out.println("clockViewZone=" + clockView.getZone().getId());
        System.out.println("localDateFromClock=" + LocalDate.now(clockView));

        InstantSource acceptedClock =
                Clock.fixed(observedAt, vietnam);
        SubmissionWindow fromClock =
                new SubmissionService(acceptedClock)
                        .openWindow(Duration.ofMinutes(10));
        System.out.println("clockAcceptedSameExpiry="
                + fromClock.expiresAt().equals(window.expiresAt()));

        InstantSource system = InstantSource.system();
        System.out.println("systemInstantRead=" + (system.instant() != null));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 InstantSourceDemo.java
java InstantSourceDemo
```

Stdout:

```text
issuedAt=2024-06-15T18:30:00Z
expiresAt=2024-06-15T18:40:00Z
expiredAtIssue=false
expiredJustBefore=false
expiredAtBoundary=true
expiredJustAfter=true
shiftedInstant=2024-06-15T18:40:00Z
originalUnchanged=2024-06-15T18:30:00Z
clockViewInstant=2024-06-15T18:30:00Z
clockViewZone=Asia/Ho_Chi_Minh
localDateFromClock=2024-06-16
clockAcceptedSameExpiry=true
systemInstantRead=true
```

Chương trình đọc nguồn hệ thống ở cuối nhưng không in giá trị “hiện tại” thay đổi theo mỗi lần chạy. Các kết quả nghiệp vụ dùng mốc cố định để tái lập được.

## 4. Vì sao nguồn được truyền vào thay vì tạo trong phương thức?

Khi chạy thật, phần lắp ghép ứng dụng có thể dùng:

```java
SubmissionService service =
        new SubmissionService(InstantSource.system());
```

Đây là đoạn trích, cần lớp dịch vụ như chương trình đầy đủ.

Khi kiểm thử, cùng lớp nhận `InstantSource.fixed`. Không cần đổi mã nghiệp vụ, không cần chờ thời gian trôi và không cần thay đồng hồ hệ thống.

Nếu phương thức tự gọi `Instant.now()` hoặc tự tạo `InstantSource.system()` bên trong, nguồn được truyền vào không còn kiểm soát toàn bộ hành vi. Một lớp có trường `source` nhưng vẫn đọc trực tiếp thời gian ở nơi khác chỉ mới được tách phụ thuộc một phần.

Trong Java 17, cách trực tiếp với biến kiểu `InstantSource` là `source.instant()`. Không giả định có overload `Instant.now(InstantSource)`; overload nhận nguồn của `Instant.now` trong phiên bản này nhận `Clock`. Không cần tạo một Clock có vùng tùy ý chỉ để gọi `now` nếu nhu cầu đã được đáp ứng bằng `instant()`.

Chọn nguồn ở ranh giới cấu hình, đọc nguồn ở đúng nơi cần quan sát “bây giờ”.

## 5. Đọc một mốc khi các giá trị phải liên hệ với cùng lần quan sát

Phương thức `openWindow` đọc nguồn một lần:

```java
Instant issuedAt = source.instant();
Instant expiresAt = issuedAt.plus(validity);
```

Nhờ vậy, thời hạn 10 phút được tính từ chính mốc phát hành.

Cách sau có ý nghĩa khác vì có hai lần đọc:

```java
Instant issuedAt = source.instant();
Instant expiresAt = source.instant().plus(validity);
```

Đây là đoạn minh họa điều cần tránh nếu yêu cầu là `expiresAt = issuedAt + validity`. Với nguồn thật, lần đọc thứ hai có thể muộn hơn. Với nguồn giả lập thay đổi qua từng lần đọc, sự khác biệt càng dễ nhìn thấy.

Không cần ép mọi phương thức chỉ đọc một lần cho mọi tình huống. Nếu đang xử lý một quy trình dài và thật sự cần quan sát lại thời gian, việc đọc thêm là đúng. Điều cần quyết định là các giá trị nào phải được tính từ cùng một mốc.

## 6. Kiểm thử ranh giới bằng nguồn cố định

Ba ca:

```text
expiresAt - 1 nano giây → chưa hết hạn
expiresAt              → đã hết hạn
expiresAt + 1 nano giây → đã hết hạn
```

kiểm chứng trực tiếp quy tắc tại điểm biên.

Nếu viết:

```java
return now.isAfter(expiresAt);
```

thì thời điểm bằng hạn chưa bị coi là hết hạn. Công thức trong bài dùng `!now.isBefore(expiresAt)` vì hợp đồng đã chọn cận cuối không bao gồm.

Quy tắc bằng hạn là quyết định nghiệp vụ; điều quan trọng là xác định rõ rồi kiểm tra cả ba phía. Đừng chờ 10 phút thật hoặc dùng `Thread.sleep` để kiểm chứng một phép so sánh có thể kiểm soát đầu vào.

Mốc nano trong phép thử không nói nguồn hệ thống có độ chính xác nano. Nó chỉ kiểm tra logic so sánh các `Instant` mà kiểu dữ liệu có thể biểu diễn.

## 7. `offset` dịch mốc, `withZone` thêm cách nhìn địa phương

Hai phương thức có tác động khác nhau:

| Thao tác | Có đổi `Instant` được cung cấp không? | Mục đích |
| --- | --- | --- |
| `InstantSource.offset(base, duration)` | Có, cộng độ dời vào mốc của nguồn gốc | Mô phỏng trước/sau một thời lượng |
| `source.withZone(zone)` | Không đổi mốc do nguồn gốc cung cấp | Tạo Clock để dùng vùng khi suy ra ngày/giờ |

Trong chương trình:

- `offset` đưa mốc từ 18:30 lên 18:40.
- `withZone(vietnam)` vẫn cung cấp mốc 18:30Z, nhưng ngày địa phương là 16/06.

Độ dời thời lượng không phải offset múi giờ. `Duration.ofHours(7)` làm mốc tiến bảy giờ; chọn vùng `Asia/Ho_Chi_Minh` làm cùng mốc được nhìn theo quy tắc vùng.

Nguồn được tạo bởi `offset` không làm biến `fixed` chuyển sang mốc mới. Chương trình in lại nguồn gốc để cho thấy nó vẫn là 18:30.

Với nguồn gốc hệ thống, bọc `offset` vẫn là một nguồn đang đọc thời gian trôi. Nó không tự trở thành nguồn cố định. [Tài liệu `offset` và `withZone`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/InstantSource.html)

## 8. Khi chỉ một thời điểm đã đủ

Không phải lớp nào cũng cần giữ một nguồn. Nếu nơi gọi đã chụp `now` cho cả thao tác, một hàm có thể nhận mốc trực tiếp:

```java
static boolean isExpiredAt(Instant now, Instant expiresAt) {
    return !now.isBefore(expiresAt);
}
```

Đây là hàm minh họa đặt trong một lớp, cần import `Instant`.

Hàm này không quyết định lúc đọc thời gian, nên kiểm thử bằng hai giá trị rất đơn giản. Nơi gọi có thể dùng `source.instant()` một lần rồi truyền mốc ấy cho nhiều kiểm tra cần nhất quán.

Dùng `InstantSource` khi nơi nhận cần **khả năng lấy thời điểm theo lúc thực hiện**. Dùng `Instant` khi nơi nhận chỉ cần **một giá trị thời điểm đã được xác định**. Hai lựa chọn có thể cùng tồn tại trong một thiết kế.

## 9. Giới hạn và lưu ý khi dùng nguồn tùy chỉnh

`InstantSource` là trừu tượng cho nguồn thời điểm, không bảo đảm mọi nguồn đều theo thời gian thực. Nguồn có thể cố định, dịch mốc hoặc có hành vi đã được tài liệu hóa khác.

Khi dùng hoặc tự triển khai nguồn, cần biết:

- Nguồn có an toàn khi được nhiều luồng gọi không.
- Nguồn có thể phát sinh lỗi khi đọc hay không.
- Độ chính xác và độ phân giải thực tế.
- Thời gian có thể bị hiệu chỉnh hoặc không tăng đều không.
- Việc tái lập hành vi trong kiểm thử được kiểm soát thế nào.

Không mặc định `InstantSource.system()` là nguồn đo thời lượng đơn điệu hoặc nguồn đồng bộ thời gian độc lập từ mạng. Nó dựa trên nguồn hệ thống có sẵn. Nếu mục tiêu là đo hiệu năng hay thời gian trôi cho thuật toán, cần chọn công cụ theo yêu cầu đó thay vì suy từ tên “source”.

`millis()` chỉ cho mức biểu diễn mili giây; nếu logic cần so sánh mốc có phần lẻ nhỏ hơn, giữ `Instant` và hiểu độ chính xác của dữ liệu nguồn. Đừng đổi sang số nguyên rồi làm mất phần lẻ ngoài ý muốn.

## 10. Kiểm chứng thiết kế và tự thực hành

Một bộ ca có ích cho lớp chỉ cần thời điểm:

- Nguồn cố định cho giá trị phát hành dự kiến.
- Thời điểm trước, đúng và sau hạn.
- Nguồn được truyền vào thật sự chi phối hành vi.
- Thời hạn âm hoặc bằng không được xử lý theo hợp đồng.
- Clock có vùng khác nhau nhưng cùng mốc vẫn cho cùng kết quả so sánh hạn.
- Nhiều giá trị cần nhất quán được suy ra từ cùng một lần đọc.

Câu hỏi tự kiểm tra:

1. Một dịch vụ chỉ so sánh hai `Instant` có nhất thiết cần biết múi giờ không?
2. `Clock` có thể được truyền vào tham số `InstantSource` không?
3. Nguồn cố định có tự tiến lên sau khi chờ bằng `sleep` không?
4. `offset` bảy giờ có tương đương đổi vùng sang Việt Nam không?
5. Khi nên truyền `Instant` thay cho một nguồn?

Gợi ý đáp án:

1. Không; nếu nghiệp vụ chỉ là so sánh mốc.
2. Có, vì Clock triển khai giao diện này.
3. Không; nó luôn trả mốc đã cấu hình.
4. Không; một thao tác đổi mốc, thao tác kia đổi cách nhìn địa phương.
5. Khi nơi nhận chỉ xử lý một mốc đã được quan sát và không cần tự đọc “bây giờ”.

Hãy dùng `InstantSource` để thể hiện đúng phụ thuộc vào nguồn thời điểm, chọn nguồn thật hoặc cố định tại nơi lắp ghép và kiểm chứng rõ các ranh giới mà nghiệp vụ yêu cầu.
