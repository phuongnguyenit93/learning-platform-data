# Kiểm thử trước, đúng và sau thời điểm hết hạn

## 1. Trường hợp đúng thời điểm là quyết định của hợp đồng

Một chức năng có thể hoạt động đúng ở thời điểm trước hạn nhiều giờ và sau hạn nhiều ngày nhưng vẫn sai đúng tại ranh giới. Nguyên nhân thường là nhầm giữa “sau thời điểm hết hạn” và “từ thời điểm hết hạn trở đi”.

Trước khi viết kiểm thử, chọn quy tắc rõ ràng. Trong bài này:

> Giá trị còn hiệu lực khi `now < expiresAt`; đã hết hạn khi `now >= expiresAt`.

Vì vậy đúng tại `expiresAt` đã là hết hạn. Không có một quy tắc mặc định của `Clock` tự quyết định điều này; đó là lựa chọn của chức năng.

| Vị trí của now | Còn hiệu lực? | Hết hạn? |
|---|---|---|
| Trước `expiresAt` | Có | Không |
| Bằng `expiresAt` | Không | Có |
| Sau `expiresAt` | Không | Có |

Ba hàng là bộ kiểm thử tối thiểu có ý nghĩa cho điều kiện ranh giới này. Trường hợp bằng nhau giúp phát hiện sai khác chỉ một dấu so sánh mà hai trường hợp còn lại không phân biệt được.

## 2. Biểu diễn điều kiện bằng Instant

Khi hạn là một thời điểm toàn cục, dùng `Instant` cho cả `now` và `expiresAt` để so sánh trên cùng trục thời gian:

```java
Instant now = clock.instant();
boolean expired = !now.isBefore(expiresAt);
```

`isBefore` chỉ đúng khi ở trước. Phủ định của nó bao gồm cả bằng và sau.

Một cách diễn đạt tương đương là `now.compareTo(expiresAt) >= 0`. Chọn cách dễ đọc theo hợp đồng; không cần đồng thời dùng nhiều biểu thức tương đương trong mã thật.

Lỗi phổ biến:

```java
boolean expired = now.isAfter(expiresAt);
```

Theo hợp đồng của bài, biểu thức trên thiếu trường hợp bằng nhau. Nó chỉ thích hợp nếu quy tắc của chức năng thật sự cho phép còn hiệu lực đúng tại thời điểm hạn.

Đừng kiểm thử bằng việc so sánh chuỗi ngày giờ, chỉ lấy phần ngày, hay so sánh `getEpochSecond()` nếu phần nano giây có ý nghĩa. Các cách ấy có thể bỏ mất thông tin ngay ở ranh giới cần kiểm tra.

## 3. Điều khiển now bằng Clock.fixed

Thay vì gọi giờ thật rồi cố chạy kiểm thử ngay trước hạn, tạo ba nguồn cố định:

```java
Clock before = Clock.fixed(expiresAt.minusNanos(1), ZoneOffset.UTC);
Clock exactly = Clock.fixed(expiresAt, ZoneOffset.UTC);
Clock after = Clock.fixed(expiresAt.plusNanos(1), ZoneOffset.UTC);
```

Đây là ba đồng hồ độc lập với cùng cách xác định múi giờ. Chúng không tự chuyển từ trước sang bằng rồi sang sau khi được đọc. Mỗi trường hợp cần truyền đúng đồng hồ vào chức năng đang kiểm tra.

Không cần `Thread.sleep`, không cần đổi đồng hồ hệ điều hành và không cần chờ đến một ngày tương lai. Nếu kiểm thử thất bại, có thể chạy lại với đúng dữ liệu thời gian như cũ.

Mốc hạn phải được giữ nguyên giữa ba trường hợp. Nếu mỗi lần kiểm tra lại tính `expiresAt = clock.instant().plus(...)`, bạn đang dời cả hạn theo nguồn kiểm thử, có thể khiến trạng thái luôn “chưa hết hạn” và mất ý nghĩa của phép thử.

Với chức năng tạo hạn từ một thời lượng, kiểm tra hai trách nhiệm riêng: lúc tạo hạn có tính đúng từ mốc phát hành hay không, và lúc xác nhận có so sánh đúng với hạn đã tạo hay không.

## 4. Chọn độ lệch kiểm thử theo độ chính xác thực tế

Trong mã thuần dùng `Instant`, trước/sau 1 nano giây là cách sát ranh giới để kiểm tra dấu so sánh. Nó không có nghĩa nguồn đồng hồ hoặc cơ sở dữ liệu ngoài thực tế luôn có độ chính xác nano giây.

| Tầng kiểm tra | Mốc trước/sau cần chú ý |
|---|---|
| Hàm thuần làm việc trực tiếp với Instant | Có thể dùng ±1 ns để xác nhận chính xác phép so sánh |
| Dữ liệu qua lưu trữ chỉ giữ mili giây | Thử ranh giới ở độ phân giải mili giây và việc đọc/ghi phần lẻ |
| Giao thức chỉ truyền giây | Xác định quy tắc bỏ/làm tròn phần lẻ, rồi kiểm tra theo hợp đồng đó |
| Nguồn bị cắt bằng Clock.tick | Kiểm tra tác động của việc nguồn có thể vẫn báo mốc cũ |

Không dùng dung sai tùy tiện như “lệch dưới một giây thì coi là bằng” để làm kiểm thử dễ qua khi quy tắc thật không có khoảng dung sai. Nếu sản phẩm có thời gian gia hạn, mô hình nó tường minh như một điều kiện riêng.

Cũng không chỉ thử trước/sau nhiều ngày. Các trường hợp xa ranh giới có thể hữu ích nhưng không thay thế trường hợp đúng hạn và sát hạn ở độ chính xác cần hỗ trợ.

## 5. Đọc thời gian một lần cho một quyết định

Nếu cần trả cả trạng thái và thời điểm kiểm tra, chụp `now` một lần rồi dùng cùng giá trị:

```java
Instant checkedAt = clock.instant();
boolean expired = !checkedAt.isBefore(expiresAt);
```

Không gọi nguồn thời gian riêng cho từng trường dữ liệu rồi giả định chúng xảy ra ở cùng mốc. Với nguồn thật, lần đọc đầu có thể ở trước hạn còn lần sau ở sau hạn. Một bản kết quả dùng hai mốc có thể tự mâu thuẫn.

Điều này không biến phép kiểm tra thành cơ chế khóa hay giao dịch cho thao tác tiếp theo. Nếu chức năng phải bảo đảm trạng thái vẫn hợp lệ tại lúc ghi dữ liệu, cần xác định đúng thời điểm quyết định và cơ chế phối hợp với thao tác đó. Phạm vi kiểm thử trong bài là phép phân loại theo một mốc được chụp.

## 6. Hạn theo ngày địa phương cần một bước xác định ranh giới

Yêu cầu “còn hiệu lực hết ngày 25/10/2026 tại Việt Nam” không trực tiếp là một `Instant`: nó gồm ngày và múi giờ của chức năng.

Một cách biểu diễn rõ là hạn cuối **không bao gồm** đầu ngày kế tiếp:

```java
Instant endExclusive = lastValidDate.plusDays(1)
        .atStartOfDay(businessZone)
        .toInstant();
```

Với `lastValidDate = 2026-10-25` và vùng `Asia/Ho_Chi_Minh`, ranh giới là `2026-10-25T17:00:00Z`, tương ứng 00:00 ngày 26/10 tại vùng đó. Ngay trước ranh giới vẫn còn hiệu lực; bằng ranh giới là hết hạn theo cùng điều kiện `now >= endExclusive`.

Cách này tránh tạo thủ công mốc “23:59:59.999...” với một độ chính xác có thể không khớp nơi lưu trữ. `atStartOfDay(zone)` còn tuân theo thời điểm đầu ngày hợp lệ theo quy tắc vùng; không mặc định mọi vùng và mọi ngày đều có đúng 00:00 hợp lệ hoặc một ngày dài đúng 24 giờ.

Cần chọn múi giờ nghiệp vụ tường minh. Không để múi giờ máy chạy tự quyết định ranh giới của một ngày mà chức năng đã định nghĩa theo vùng khác.

## 7. Chương trình kiểm thử chạy đầy đủ

Lưu mã sau vào `ExpirationBoundaryDemo.java`. Chương trình dùng Java 17 trở lên, không cần thư viện ngoài. Nó có các phép kiểm tra tự động: nếu kết quả khác mong đợi, `AssertionError` được ném ra và chương trình thất bại, không chỉ in thông tin cho người đọc tự đoán.

```java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.Objects;

public class ExpirationBoundaryDemo {
    record CheckResult(Instant checkedAt, boolean expired) {}

    static final class ExpirationService {
        private final Clock clock;

        ExpirationService(Clock clock) {
            this.clock = Objects.requireNonNull(clock);
        }

        CheckResult check(Instant expiresAt) {
            Objects.requireNonNull(expiresAt);
            Instant now = clock.instant();
            return new CheckResult(now, !now.isBefore(expiresAt));
        }
    }

    record BoundaryCase(String label, Instant now, boolean expectedExpired) {}

    public static void main(String[] args) {
        Instant expiresAt = Instant.parse("2026-10-25T10:00:00Z");
        for (BoundaryCase test : new BoundaryCase[]{
                new BoundaryCase("before", expiresAt.minusNanos(1), false),
                new BoundaryCase("exactly", expiresAt, true),
                new BoundaryCase("after", expiresAt.plusNanos(1), true)
        }) {
            verify(test, expiresAt, ZoneOffset.UTC);
        }

        Clock utc = Clock.fixed(expiresAt, ZoneOffset.UTC);
        Clock vietnam = utc.withZone(ZoneId.of("Asia/Ho_Chi_Minh"));
        boolean utcResult = new ExpirationService(utc).check(expiresAt).expired();
        boolean vnResult =
                new ExpirationService(vietnam).check(expiresAt).expired();
        if (utcResult != vnResult) {
            throw new AssertionError("instant comparison must be zone independent");
        }
        System.out.println("sameInstantDifferentZone=PASS");

        LocalDate lastValidDate = LocalDate.of(2026, 10, 25);
        ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
        Instant endExclusive = lastValidDate.plusDays(1)
                .atStartOfDay(businessZone).toInstant();
        System.out.println("endExclusive=" + endExclusive);

        verify(new BoundaryCase("dayBeforeEnd",
                endExclusive.minusNanos(1), false), endExclusive, businessZone);
        verify(new BoundaryCase("dayExactlyEnd",
                endExclusive, true), endExclusive, businessZone);
        verify(new BoundaryCase("dayAfterEnd",
                endExclusive.plusNanos(1), true), endExclusive, businessZone);
        System.out.println("allChecks=PASS");
    }

    private static void verify(BoundaryCase test,
                               Instant expiresAt,
                               ZoneId zone) {
        Clock fixed = Clock.fixed(test.now(), zone);
        CheckResult actual = new ExpirationService(fixed).check(expiresAt);
        if (actual.expired() != test.expectedExpired()
                || !actual.checkedAt().equals(test.now())) {
            throw new AssertionError("failed case: " + test.label());
        }
        System.out.println(test.label() + " expired=" + actual.expired());
    }
}
```

Biên dịch và chạy:

```shell
javac ExpirationBoundaryDemo.java
java ExpirationBoundaryDemo
```

Kết quả chuẩn:

```text
before expired=false
exactly expired=true
after expired=true
sameInstantDifferentZone=PASS
endExclusive=2026-10-25T17:00:00Z
dayBeforeEnd expired=false
dayExactlyEnd expired=true
dayAfterEnd expired=true
allChecks=PASS
```

Các phép kiểm tra dùng `if` và ném `AssertionError` trực tiếp, nên không cần bật tùy chọn `-ea` như khi dùng từ khóa `assert` của Java.

`verify` kiểm tra cả trạng thái và mốc `checkedAt`. Các mong đợi được liệt kê tường minh trong dữ liệu `BoundaryCase`, không được tính lại bằng cùng biểu thức mà lớp cần kiểm tra đang dùng.

Trường hợp đổi múi giờ giữ nguyên cùng `Instant` và cùng hạn. Kết quả hết hạn phải giữ nguyên vì phép so sánh chỉ dùng thời điểm; múi giờ ảnh hưởng bước tạo ranh giới theo ngày địa phương, không làm đổi quan hệ trước/bằng/sau giữa hai `Instant` đã xác định.

## 8. Đưa cùng cấu trúc vào bộ kiểm thử của dự án

Khi dự án dùng JUnit, ba dòng dữ liệu trước/bằng/sau có thể trở thành một kiểm thử tham số hóa. Vẫn giữ các nguyên tắc của chương trình:

- Mỗi trường hợp có `Clock.fixed` và mốc hạn xác định rõ.
- Mong đợi được ghi theo quy tắc nghiệp vụ, không sao chép thuật toán vào phần tạo mong đợi.
- Trường hợp sai dấu so sánh phải làm kiểm thử thất bại.
- Không dùng thời gian thật hoặc chờ để đi qua ranh giới.
- Nguồn thời gian của đối tượng kiểm tra được truyền vào, không bị đường xử lý khác bỏ qua bằng `Instant.now()` không tham số.

Ví dụ này kiểm tra hàm quyết định thuần. Nếu hạn được lưu trong cơ sở dữ liệu, cần kiểm tra tích hợp riêng cho độ chính xác, cách chuyển kiểu và dữ liệu thực sự đọc lại. Nếu một tác vụ định kỳ xóa dữ liệu hết hạn, tính đúng của phép so sánh không tự chứng minh tác vụ được chạy đúng lịch.

Chỉ bổ sung các trường hợp đó khi chúng thuộc hợp đồng chức năng. Không kéo một kiểm thử ranh giới đơn giản thành kiểm thử toàn hệ thống chỉ để xác nhận một dấu so sánh.

## 9. Lỗi thường gặp khi kiểm thử hạn

| Lỗi | Vì sao dễ bỏ sót sai lệch? |
|---|---|
| Chỉ thử trước và sau, không thử bằng | Không phân biệt được `>` và `>=` |
| Dùng `Clock.systemUTC()` cho kiểm thử cần mốc cố định | Kết quả phụ thuộc lúc chạy |
| Tạo lại hạn từ now trong mọi trường hợp | Ranh giới di chuyển cùng dữ liệu thử |
| Dùng ±1 ms nhưng dữ liệu có nano giây, hoặc ngược lại | Có thể không thử đúng hợp đồng độ chính xác |
| Đổi ngày/giờ sang chuỗi để so sánh | Có thể mất phần lẻ hoặc phụ thuộc định dạng/múi giờ |
| Chỉ in kết quả mà không có kiểm tra mong đợi | Chương trình vẫn kết thúc thành công khi kết quả sai |
| Cho phép dung sai để bỏ qua trường hợp bằng | Làm mờ chính ranh giới cần xác định |

Không tự xử lý `null` hạn thành một ý nghĩa như “vĩnh viễn” nếu hợp đồng không cho phép. Trong chương trình, hạn bắt buộc có giá trị; thiết kế hạn không giới hạn phải được mô hình và kiểm tra riêng.

## 10. Tự thực hành

1. Cố ý đổi điều kiện trong `ExpirationService` thành `now.isAfter(expiresAt)`. Chạy lại và xác nhận trường hợp `exactly` thất bại. Đây là phép kiểm tra rằng bộ dữ liệu bắt được lỗi biên mong muốn.
2. Đổi hợp đồng thành “đúng thời điểm vẫn còn hiệu lực”. Cập nhật có chủ đích điều kiện và các mong đợi tại ranh giới; đừng chỉ sửa mã đến khi các dòng cũ đều qua.
3. Giả định nơi lưu trữ chỉ giữ mili giây. Thêm một vòng ghi/đọc giả lập theo chính sách độ chính xác đã chọn, rồi xác định lại mốc sát ranh giới có thể quan sát ở tầng đó.
4. Thay vùng của hạn theo ngày bằng một vùng khác, tính lại `endExclusive` và giữ các kiểm thử trước/bằng/sau quanh chính ranh giới mới.

Tham khảo: [Clock — fixed](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Clock.html#fixed(java.time.Instant,java.time.ZoneId)), [Instant — isBefore/isAfter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Instant.html) và [LocalDate — atStartOfDay](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html#atStartOfDay(java.time.ZoneId)) trong Java SE 21.
