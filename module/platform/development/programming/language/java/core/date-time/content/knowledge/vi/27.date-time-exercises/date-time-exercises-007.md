# Thiết kế dịch vụ hết hạn có Clock và kiểm thử lặp lại được

## 1. Bài toán thực hành

Một hệ thống tạo phiếu giữ chỗ có thời hạn hiệu lực. Khi tạo phiếu, hệ thống cần ghi:

- Mã phiếu.
- Thời điểm phát hành.
- Thời điểm hết hạn.

Sau đó, người gọi cần biết tại lúc kiểm tra phiếu đã hết hạn chưa và còn bao nhiêu thời gian.

Bài toán nhỏ nhưng có những lỗi phổ biến: kiểm thử phải chờ thật, kết quả đổi theo thời điểm chạy, đúng mốc hết hạn bị xử lý sai hoặc một lần trả kết quả dùng nhiều giá trị “bây giờ” không nhất quán.

Ta sẽ thiết kế dịch vụ có nguồn thời gian được truyền vào qua `Clock`, rồi kiểm chứng các ranh giới bằng thời gian cố định.

Trong bài, “phiếu giữ chỗ” chỉ là một đối tượng dữ liệu minh họa. Dịch vụ xác định trạng thái thời gian; không tạo hệ thống đặt chỗ, cơ sở dữ liệu hay tác vụ gửi thông báo.

## 2. Chốt hợp đồng hết hạn

Chính sách mẫu:

1. Thời lượng hiệu lực `lifetime` phải dương.
2. `issuedAt` lấy từ đồng hồ của dịch vụ khi tạo phiếu.
3. `expiresAt = issuedAt + lifetime`.
4. Tại `checkedAt < expiresAt`, phiếu chưa hết hạn.
5. Tại `checkedAt >= expiresAt`, phiếu đã hết hạn.
6. Thời gian còn lại được chặn dưới ở `Duration.ZERO`.
7. Đầu vào sai hoặc phép cộng vượt miền phải báo lỗi, không tự sửa.

Mốc hết hạn là đầu cuối loại trừ. Nếu phiếu hết hạn lúc 10:00:30 thì đúng 10:00:30 đã hết hiệu lực theo thời gian; không đợi qua thêm một nano giây.

| Thời điểm kiểm tra | `expired` | `remaining` |
| --- | --- | --- |
| 10:00:00, vừa phát hành | `false` | 30 giây |
| 10:00:29.999999999 | `false` | 1 nano giây |
| 10:00:30 | `true` | 0 |
| Sau 10:00:30 | `true` | 0 |

Bài chỉ xét điều kiện hết hạn. Những trạng thái như đã hủy, đã sử dụng hoặc chưa được phép kích hoạt là các điều kiện nghiệp vụ khác; không tự gộp chúng vào một phép so sánh thời gian.

## 3. Chọn Instant, Duration và Clock

### 3.1. Instant cho các mốc

[Instant](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Instant.html) biểu diễn một điểm trên dòng thời gian. Nó phù hợp cho `issuedAt`, `expiresAt` và `checkedAt` khi hết hạn dựa trên thời gian đã trôi qua.

Không cần `LocalDateTime` rồi ngầm coi đó là UTC. Việc thiếu offset/vùng ở một giá trị địa phương sẽ làm mốc hết hạn khó diễn giải giữa các môi trường.

Múi giờ có thể dùng để hiển thị hạn cho người dùng, nhưng không thay đổi thời điểm hạn đó đại diện.

### 3.2. Duration cho thời lượng hiệu lực

[Duration](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Duration.html) biểu diễn lượng thời gian theo giây và nano giây. Ví dụ `Duration.ofSeconds(30)` thể hiện đơn vị rõ hơn một số `30` không có tên.

`Duration` có thể bằng không hoặc âm, nên phải xác thực theo chính sách. Bài chọn từ chối cả hai. Một hệ thống khác có thể cho phép hiệu lực bằng không để hết hạn ngay, nhưng cần hợp đồng khác và kiểm chứng riêng.

Đây là hạn sau một thời lượng. Quy tắc “hết ngày làm việc thứ ba” hoặc “cuối tháng tại vùng của khách hàng” cần phép tính lịch và chính sách khác, không thể thay thế trực tiếp bằng một `Duration` cố định.

### 3.3. Clock là nguồn thời gian có thể thay thế

[Clock](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Clock.html) cho phép cung cấp cách lấy thời điểm hiện tại thay vì gọi trực tiếp thời gian hệ thống ở mọi nơi.

Chữ ký constructor:

```java
ExpirationService(Clock clock);
```

giúp dịch vụ nói rõ nó phụ thuộc một nguồn thời gian. Khi dùng thật, nơi ghép ứng dụng có thể cấp `Clock.systemUTC()`. Khi kiểm chứng, cấp `Clock.fixed(...)` hoặc `Clock.offset(...)`.

Dịch vụ không cần biết đồng hồ đến từ hệ thống, từ một giá trị cố định hay một nguồn đã được kiểm soát khác. Nó chỉ gọi `clock.instant()`.

## 4. Vì sao không gọi Instant.now() trực tiếp bên trong?

Một phương thức lấy thời gian hệ thống ngầm sẽ có đầu vào ẩn:

```java
// Minh hoa phu thuoc an vao thoi gian he thong:
Instant issuedAt = Instant.now();
```

Cùng dữ liệu gọi nhưng chạy vào hai lúc khác nhau sẽ tạo hai mốc khác nhau. Đó là điều cần ở môi trường thật, nhưng làm kiểm chứng ranh giới khó kiểm soát.

Một phép kiểm chứng kiểu “tạo phiếu 100 mili giây rồi chờ 150 mili giây” phụ thuộc tốc độ máy, tải hệ thống và lịch chạy của luồng. Nó còn tốn thời gian thật dù logic chỉ là một phép so sánh.

Với `Clock` được truyền vào, kiểm chứng có thể đặt ngay thời gian ở trước, đúng hoặc sau mốc hết hạn. Không cần chờ, thay múi giờ toàn cục hoặc can thiệp phương thức tĩnh.

Việc truyền phụ thuộc qua constructor đủ cho ví dụ Java thuần; không cần một framework để có lợi ích này.

## 5. Thiết kế các đối tượng

Ta sử dụng ba thành phần:

| Thành phần | Trách nhiệm |
| --- | --- |
| `Lease` | Giữ mã phiếu và các mốc; kiểm tra dữ liệu lưu hợp lệ |
| `ExpirationService` | Phát hành phiếu và tính trạng thái bằng `Clock` |
| `ExpiryView` | Trả ảnh chụp kết quả gồm mốc kiểm tra, trạng thái và thời lượng còn lại |

`Lease` và `ExpiryView` là record. Các trường thời gian dùng kiểu bất biến, giúp kết quả không bị sửa ngầm sau khi trả về.

### 5.1. Chỉ lấy một mốc now cho mỗi thao tác

Khi phát hành, lấy `issuedAt` một lần rồi tính `expiresAt` từ chính mốc đó.

Khi kiểm tra, lấy `checkedAt` một lần, dùng nó cho cả `expired` lẫn `remaining`. Nếu gọi đồng hồ riêng cho từng trường, thao tác có thể vượt ranh giới ở giữa hai lời gọi:

- Lần đọc đầu cho biết chưa hết hạn.
- Lần đọc sau đã qua mốc và cho thời gian âm hoặc bằng không.

Một `ExpiryView` từ cùng `checkedAt` tránh ảnh chụp tự mâu thuẫn. Việc trả cả `checkedAt` cũng giúp nơi gọi hiểu kết quả là trạng thái được quan sát lúc nào.

Nó không làm thời gian dừng lại sau khi phương thức trả về. Kết quả là ảnh chụp, không phải lời bảo đảm trạng thái sẽ giữ nguyên khi một thao tác khác diễn ra sau đó.

## 6. Chương trình Java 17+ đầy đủ

Lưu thành `ClockExpiryPractice.java`:

```java
import java.time.Clock;
import java.time.DateTimeException;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.Objects;

public class ClockExpiryPractice {
    record Lease(String id, Instant issuedAt, Instant expiresAt) {
        Lease {
            Objects.requireNonNull(id);
            Objects.requireNonNull(issuedAt);
            Objects.requireNonNull(expiresAt);
            if (id.isBlank()) {
                throw new IllegalArgumentException("Blank lease ID");
            }
            if (!expiresAt.isAfter(issuedAt)) {
                throw new IllegalArgumentException(
                        "Expiry must be after issue time");
            }
        }
    }

    record ExpiryView(
            Instant checkedAt, boolean expired, Duration remaining) {}

    static final class ExpirationService {
        private final Clock clock;

        ExpirationService(Clock clock) {
            this.clock = Objects.requireNonNull(clock);
        }

        Lease issue(String id, Duration lifetime) {
            Objects.requireNonNull(lifetime);
            if (lifetime.isZero() || lifetime.isNegative()) {
                throw new IllegalArgumentException("Lifetime must be positive");
            }
            Instant issuedAt = clock.instant();
            Instant expiresAt = issuedAt.plus(lifetime);
            return new Lease(id, issuedAt, expiresAt);
        }

        ExpiryView inspect(Lease lease) {
            Objects.requireNonNull(lease);
            Instant checkedAt = clock.instant();
            boolean expired = !checkedAt.isBefore(lease.expiresAt());
            Duration remaining = expired
                    ? Duration.ZERO
                    : Duration.between(checkedAt, lease.expiresAt());
            return new ExpiryView(checkedAt, expired, remaining);
        }
    }

    static int checks;

    static void check(String label, boolean condition) {
        if (!condition) {
            throw new AssertionError(label);
        }
        checks++;
        System.out.println("PASS " + label);
    }

    static void expectThrows(
            String label,
            Class<? extends RuntimeException> expectedType,
            Runnable operation) {
        try {
            operation.run();
        } catch (RuntimeException ex) {
            check(label, expectedType.isInstance(ex));
            return;
        }
        throw new AssertionError(label + ": no exception");
    }

    public static void main(String[] args) {
        Instant origin = Instant.parse("2024-06-01T10:00:00Z");
        Clock fixed = Clock.fixed(origin, ZoneOffset.UTC);
        ExpirationService issuer = new ExpirationService(fixed);
        Lease lease = issuer.issue("hold-A", Duration.ofSeconds(30));

        check("issue time is controlled", lease.issuedAt().equals(origin));
        check("expiry uses lifetime",
                lease.expiresAt().equals(origin.plusSeconds(30)));

        ExpiryView atStart = issuer.inspect(lease);
        check("not expired at issue", !atStart.expired());
        check("initial remaining time",
                atStart.remaining().equals(Duration.ofSeconds(30)));
        check("fixed clock gives repeatable view",
                atStart.equals(issuer.inspect(lease)));

        Clock justBefore = Clock.fixed(
                lease.expiresAt().minusNanos(1), ZoneOffset.UTC);
        ExpiryView before = new ExpirationService(justBefore).inspect(lease);
        check("valid one nanosecond before", !before.expired());
        check("one nanosecond remains",
                before.remaining().equals(Duration.ofNanos(1)));

        Clock exactDeadline = Clock.offset(fixed, Duration.ofSeconds(30));
        ExpiryView exact =
                new ExpirationService(exactDeadline).inspect(lease);
        check("expired exactly at deadline", exact.expired());
        check("zero remains at deadline",
                exact.remaining().equals(Duration.ZERO));

        Clock justAfter = Clock.fixed(
                lease.expiresAt().plusNanos(1), ZoneOffset.UTC);
        ExpiryView after = new ExpirationService(justAfter).inspect(lease);
        check("expired after deadline", after.expired());
        check("remaining is not negative",
                after.remaining().equals(Duration.ZERO));

        Clock sameInstantDifferentZone =
                fixed.withZone(ZoneId.of("Asia/Ho_Chi_Minh"));
        ExpirationService otherZone =
                new ExpirationService(sameInstantDifferentZone);
        check("zone does not change absolute expiry",
                atStart.equals(otherZone.inspect(lease)));

        expectThrows("zero lifetime rejected",
                IllegalArgumentException.class,
                () -> issuer.issue("hold-B", Duration.ZERO));
        expectThrows("negative lifetime rejected",
                IllegalArgumentException.class,
                () -> issuer.issue("hold-C", Duration.ofSeconds(-1)));
        expectThrows("reversed stored times rejected",
                IllegalArgumentException.class,
                () -> new Lease("hold-D", origin, origin.minusSeconds(1)));

        ExpirationService atLimit = new ExpirationService(
                Clock.fixed(Instant.MAX, ZoneOffset.UTC));
        expectThrows("instant range overflow reported",
                DateTimeException.class,
                () -> atLimit.issue("hold-E", Duration.ofSeconds(1)));

        System.out.println("checks = " + checks);
        System.out.println("expiresAt = " + lease.expiresAt());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 ClockExpiryPractice.java
java ClockExpiryPractice
```

Stdout:

```text
PASS issue time is controlled
PASS expiry uses lifetime
PASS not expired at issue
PASS initial remaining time
PASS fixed clock gives repeatable view
PASS valid one nanosecond before
PASS one nanosecond remains
PASS expired exactly at deadline
PASS zero remains at deadline
PASS expired after deadline
PASS remaining is not negative
PASS zone does not change absolute expiry
PASS zero lifetime rejected
PASS negative lifetime rejected
PASS reversed stored times rejected
PASS instant range overflow reported
checks = 16
expiresAt = 2024-06-01T10:00:30Z
```

Nếu một điều kiện kiểm chứng sai, phương thức `check` ném `AssertionError` và chương trình thất bại. Nó không chỉ in một giá trị rồi mặc định coi đó là đúng.

`expectThrows` xác nhận những đầu vào hoặc phép tính không hợp lệ thật sự phát sinh loại ngoại lệ mong đợi. Một lời gọi không ném lỗi khi phải bị từ chối sẽ làm kiểm chứng thất bại.

Ví dụ dùng thư viện chuẩn để chạy trực tiếp bằng `javac`/`java`. Trong một dự án có JUnit, có thể chuyển từng tình huống sang phép kiểm thử tương ứng mà giữ nguyên đầu vào `Clock` và kết quả mong đợi.

## 7. Đọc các kiểm tra theo mục tiêu

### 7.1. Phát hành tại thời điểm biết trước

`Clock.fixed(origin, ZoneOffset.UTC)` luôn trả cùng `origin`. Dịch vụ phát hành phiếu với `issuedAt` chính xác bằng giá trị đó, và `expiresAt` bằng `origin.plusSeconds(30)`.

Phép kiểm chứng không so “gần với thời gian thật hiện tại”. Nó so với một mốc xác định nên chạy lại vào năm nào vẫn cho cùng kết quả.

### 7.2. Trước mốc một nano giây

Đặt đồng hồ tại `expiresAt.minusNanos(1)`:

- `expired` phải là `false`.
- `remaining` phải bằng `Duration.ofNanos(1)`.

Trường hợp này kiểm tra đúng toán tử so sánh tại ranh giới. Nếu hiện thực làm tròn về giây hoặc chỉ nhìn ngày, nó có thể cho kết quả sai.

Đây là kiểm chứng trên các giá trị Java trong bộ nhớ. Nếu hạn đi qua cơ sở dữ liệu chỉ giữ micro hoặc mili giây, kiểm chứng tích hợp cần xét độ chính xác thực tế của cột và driver, không tự giả định dữ liệu đã lưu còn giữ được mọi nano của đầu vào.

### 7.3. Đúng mốc

`Clock.offset(fixed, Duration.ofSeconds(30))` cho thời điểm đúng bằng `expiresAt` vì nguồn `fixed` không đổi.

Điều kiện:

```java
boolean expired = !checkedAt.isBefore(expiresAt);
```

bao gồm cả bằng nhau. Nếu viết `checkedAt.isAfter(expiresAt)` thì đúng mốc vẫn bị coi là chưa hết hạn, trái hợp đồng của bài.

### 7.4. Sau mốc

Sau mốc một nano giây, `expired` vẫn là `true` nhưng `remaining` là `ZERO`, không phải thời lượng âm.

Việc chặn dưới không được dùng để che sai logic trạng thái. Cả hai trường đều được tính từ cùng `checkedAt` theo hợp đồng.

### 7.5. Cùng thời điểm, khác vùng của đồng hồ

`fixed.withZone(Asia/Ho_Chi_Minh)` thay vùng dùng để diễn giải ngày giờ địa phương nhưng vẫn giữ cùng thời điểm của đồng hồ cố định.

Dịch vụ chỉ dùng `clock.instant()` nên trạng thái và thời lượng còn lại không đổi. Nếu đổi vùng mà hạn tuyệt đối thay đổi, cần xem lại có đoạn mã nào dùng `LocalDateTime.now(clock)` rồi diễn giải sai vùng hay không.

### 7.6. Thời lượng không hợp lệ và vượt miền

`Duration.ZERO` và thời lượng âm bị từ chối ngay theo chính sách mẫu. Các mốc được nạp vào `Lease` cũng phải có `expiresAt > issuedAt`.

Một phép cộng quá lớn có thể vượt miền `Instant`. Kiểm chứng gần `Instant.MAX` xác nhận lỗi được báo, không biến thành một hạn khác hoặc một giá trị mặc định.

Trong ứng dụng thực tế, thường nên có giới hạn thời lượng hợp lý theo miền nghiệp vụ trước khi chạm biên rất xa của kiểu Java.

## 8. Hiểu đúng fixed, offset và đồng hồ hệ thống

| Cách tạo | Hành vi |
| --- | --- |
| `Clock.systemUTC()` | Lấy thời gian hệ thống, vùng UTC |
| `Clock.fixed(instant, zone)` | Luôn trả một thời điểm cố định |
| `Clock.offset(base, duration)` | Thời điểm của nguồn cộng một độ dời |
| `clock.withZone(zone)` | Cùng nguồn thời gian với cách diễn giải vùng phù hợp |

`Clock.offset` không tự trở thành một đồng hồ có thể “vặn” qua API. Nếu nguồn cố định thì kết quả cũng cố định; nếu nguồn chạy theo hệ thống thì kết quả cũng tiến theo nguồn đó.

Không thay đồng hồ hệ thống toàn máy để kiểm chứng một dịch vụ. Cũng không thay một biến `Clock` toàn cục dùng chung cho các phép kiểm thử chạy song song nếu chúng cần các thời điểm khác nhau.

Bài tạo những service nhỏ với clock riêng cho từng tình huống. Chúng cùng kiểm tra một `Lease` bất biến, nên không phải sửa đối tượng đã phát hành để giả lập thời gian trôi qua.

## 9. Ghép vào môi trường thật mà không đổi logic

Tại nơi tạo dịch vụ có thể dùng:

```java
ExpirationService service =
        new ExpirationService(Clock.systemUTC());
```

Đây là ví dụ ghép phụ thuộc. Mã nghiệp vụ trong `issue` và `inspect` không đổi khi chuyển giữa clock hệ thống và clock kiểm chứng.

Nếu framework quản lý đối tượng, có thể cung cấp một `Clock` dùng chung qua cơ chế truyền phụ thuộc của framework. Điều cần giữ là dịch vụ không tạo `Clock.systemUTC()` hoặc gọi `Instant.now()` riêng bên trong rồi bỏ qua phụ thuộc đã được truyền.

Nên tránh một phương thức tiện ích ở sâu trong chuỗi lại tự gọi thời gian hệ thống. Đó vẫn là một nguồn thời gian ẩn và có thể làm kết quả kiểm chứng không lặp lại được dù service cấp trên đã nhận `Clock`.

Đối với việc định dạng hạn ra màn hình, dùng thêm vùng hiển thị của người dùng. Không sửa `expiresAt` chỉ để chuỗi hiển thị đúng giờ địa phương.

## 10. Lưu trữ và xử lý hết hạn

### 10.1. Lưu mốc đã quyết định

Nếu cần giữ phiếu qua lần khởi động lại, thường cần lưu `issuedAt` và `expiresAt` hoặc dữ liệu tương đương theo hợp đồng. Không chỉ lưu TTL rồi mỗi lần đọc lại tính `now + TTL`; cách đó gia hạn lại phiếu sau mỗi lần đọc.

Nếu TTL cấu hình đổi sau khi phiếu đã phát hành, phải xác định phiếu cũ giữ mốc ban đầu hay được cập nhật theo một chính sách riêng. Đừng để phép đọc cấu hình mới âm thầm thay nghĩa dữ liệu đã lưu.

### 10.2. Dọn dữ liệu khác với hiệu lực logic

Một tác vụ dọn phiếu hết hạn có thể chạy định kỳ và chậm hơn mốc hết hạn. Việc bản ghi vẫn còn trong cơ sở dữ liệu không có nghĩa nó còn hiệu lực.

Khi xử lý yêu cầu sử dụng phiếu, phải kiểm tra điều kiện thời gian theo hợp đồng tại điểm quyết định. Tác vụ dọn dữ liệu chỉ phục vụ quản lý lưu trữ nếu thiết kế chọn như vậy.

Tương tự, một bộ hẹn giờ đã được đặt không thay thế kiểm tra hạn ở nơi sử dụng. Tác vụ có thể bị trễ, hệ thống có thể khởi động lại hoặc công việc có thể được thử lại.

### 10.3. Ảnh chụp không bảo đảm tính nguyên tử

`inspect` trả ảnh chụp ở `checkedAt`. Nếu ứng dụng kiểm tra rồi thực hiện một thao tác quan trọng sau một khoảng chờ, hạn có thể đã qua ở giữa.

Nếu yêu cầu cần việc kiểm tra và cập nhật trạng thái nhất quán trong môi trường đồng thời, phải thiết kế điều kiện cập nhật/giao dịch hoặc cơ chế thực thi tương ứng. `Clock` giúp kiểm soát nguồn thời gian, không tự tạo tính nguyên tử cho cơ sở dữ liệu.

Bài không hiện thực tầng lưu trữ đó; đây là ranh giới cần nhận diện khi đưa phần logic thời gian vào dịch vụ hoàn chỉnh.

## 11. Đồng hồ thực có thể được điều chỉnh

`Clock` không hứa rằng mọi lần đọc luôn lớn hơn lần trước. Đồng hồ hệ thống có thể được đồng bộ hoặc điều chỉnh.

Với hợp đồng “so thời điểm hiện tại với `expiresAt`”, nếu thời gian quay lùi, thời lượng còn lại có thể tăng và một lần kiểm tra sau có thể cho trạng thái khác lần trước. Đó là hệ quả của nguồn thời gian và chính sách so sánh, không phải do `Clock.fixed` hoạt động sai.

Nếu nghiệp vụ yêu cầu một khi đã đánh dấu hết hạn thì không bao giờ trở lại trạng thái trước đó, cần lưu chuyển trạng thái không đảo ngược theo hợp đồng. Không kỳ vọng một phép so sánh thời gian thuần tự nhớ lịch sử đã quan sát.

Đối với đo một khoảng chạy trong cùng tiến trình, có thể cần nguồn đo thời gian trôi qua thích hợp. Đối với hạn tuyệt đối cần lưu và chia sẻ giữa các tiến trình, `Instant` có vai trò khác. Đừng trộn hai loại mốc chỉ vì cả hai đều được gọi là “thời gian”.

Trong hệ thống có nhiều máy, việc truyền `Clock` cũng không tự đồng bộ đồng hồ giữa các nút. Nguồn thời gian và nơi có thẩm quyền quyết định hạn cần được xác định trong kiến trúc triển khai.

## 12. Mở rộng kiểm thử mà vẫn lặp lại được

Các tình huống nên bổ sung khi phát triển tiếp:

| Tình huống | Điều cần kiểm tra |
| --- | --- |
| ID rỗng hoặc chỉ khoảng trắng | Từ chối theo ràng buộc |
| `Clock` hoặc `Duration` bị thiếu | Lỗi đầu vào rõ ràng |
| TTL rất nhỏ | Không tự cắt về giây |
| TTL lớn nhưng hợp lệ theo miền | Tính đúng mốc |
| Clock trước thời điểm phát hành đã lưu | Nêu rõ hợp đồng, không suy thêm trạng thái kích hoạt |
| Hai lần đọc tại cùng fixed clock | Kết quả bằng nhau |
| Đọc sau khi ghi DB | Hạn đúng theo độ chính xác đã công bố |
| Gia hạn | Xác định tính từ hiện tại hay từ hạn cũ |

Không sửa trực tiếp `expiresAt` trong mỗi phép kiểm thử rồi bỏ qua đường phát hành. Cần kiểm chứng cả cách tính mốc và cách đánh giá mốc đã có.

Nếu cần mô phỏng nhiều bước thời gian trong cùng service, có thể cung cấp một clock kiểm chứng có thể điều khiển. Hiện thực đó phải có hợp đồng rõ và an toàn khi được dùng đồng thời. Với các ca độc lập trong bài, `fixed`/`offset` đã đủ, nên không cần xây thêm lớp phức tạp.

Không chia sẻ trạng thái đồng hồ kiểm chứng giữa các ca chạy song song nếu việc tiến thời gian ở một ca có thể ảnh hưởng ca khác.

## 13. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Gọi `Instant.now()` rải rác trong dịch vụ | Đầu vào thời gian ẩn | Truyền `Clock` và dùng nhất quán |
| Kiểm thử bằng chờ thật | Chậm và phụ thuộc lịch chạy hệ thống | Dùng mốc cố định |
| Dùng `isAfter` cho hợp đồng hết hạn tại mốc | Đúng mốc vẫn được chấp nhận | Dùng điều kiện bao gồm bằng nhau |
| Đọc đồng hồ riêng cho trạng thái và remaining | Ảnh chụp có thể mâu thuẫn | Lấy `checkedAt` một lần |
| Trả remaining âm | Nơi gọi phải tự suy trạng thái | Chặn dưới theo hợp đồng |
| Chỉ lưu TTL rồi tính lại từ now khi đọc | Hạn trượt liên tục | Giữ mốc hết hạn đã quyết định |
| Dùng ngày giờ địa phương không có vùng làm hạn tuyệt đối | Khó diễn giải giữa môi trường | Dùng `Instant` cho mốc tuyệt đối |
| Dùng tác vụ dọn dữ liệu làm kiểm tra hiệu lực duy nhất | Phiếu quá hạn vẫn có thể bị dùng | Kiểm tra tại điểm sử dụng |
| Tưởng Clock tạo tính nguyên tử hoặc đồng bộ nhiều máy | Bỏ sót vấn đề đồng thời | Thiết kế tầng quyết định/lưu riêng |
| Nới dung sai tùy tiện để kiểm thử qua | Che lỗi ranh giới | Kiểm chứng mốc chính xác theo hợp đồng |

## 14. Bài tập thực hành

1. Viết lại trường hợp đúng mốc bằng JUnit nếu dự án đã có JUnit. Kết quả phải giữ quy tắc `checkedAt == expiresAt` là hết hạn.
2. Thêm kiểm tra ID trắng và TTL một nano giây.
3. Thêm phương thức chỉ trả trạng thái hết hạn nhưng vẫn sử dụng phụ thuộc `Clock`, không tự gọi đồng hồ hệ thống.
4. Thiết kế gia hạn theo hai chính sách: tính từ lúc gia hạn và cộng vào hạn cũ. Cho ví dụ chúng khác nhau; không chọn ngầm một cách.
5. Lưu/đọc `Lease` qua kho dữ liệu thật và kiểm tra độ chính xác mốc. Phân biệt lỗi phần giây với lỗi múi giờ.
6. Thiết kế phép kiểm chứng khi clock quay lùi. Ghi rõ trạng thái hết hạn là kết quả thuần của thời điểm hiện tại hay là trạng thái đã được ghi nhận không đảo ngược.
7. Thêm trạng thái “đã hủy” và giải thích vì sao nó không nên bị coi là đồng nghĩa với hết hạn.
8. Nêu cách kiểm tra và cập nhật phiếu trong môi trường có hai yêu cầu cùng sử dụng, đồng thời giữ logic so thời gian có thể kiểm chứng.

Một dịch vụ hết hạn dễ kiểm thử cần biến thời gian thành phụ thuộc rõ ràng và định nghĩa chính xác ranh giới. `Clock` cho phép kiểm soát đầu vào đó; `Instant`, `Duration` và các kiểm chứng trước/đúng/sau mốc giúp biến hợp đồng thành hành vi có thể lặp lại.
