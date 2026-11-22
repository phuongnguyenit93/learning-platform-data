# Vì sao gọi `now()` trực tiếp làm kiểm thử khó lặp lại

## 1. “Hiện tại” là một đầu vào đang bị giấu

Giả sử một mã sử dụng chỉ có hiệu lực trước thời điểm hết hạn. Hàm nhận `expiresAt` rồi gọi `Instant.now()` bên trong để quyết định còn dùng được hay không. Nhìn chữ ký, ta chỉ thấy một đầu vào; thực tế kết quả còn phụ thuộc vào thời điểm đồng hồ hệ thống trả về khi hàm chạy.

Nếu chạy cùng kiểm thử hôm nay và tuần sau, hoặc chạy lại sau một khoảng chờ, nhánh xử lý có thể khác dù dữ liệu truyền vào giống hệt. Đây là phụ thuộc ẩn vào môi trường thực thi.

`now()` không phải lời gọi có lỗi. Vấn đề kiểm thử nằm ở việc phần quyết định nghiệp vụ tự lấy thời gian thật mà nơi kiểm thử không kiểm soát được. [Java SE 21 — Instant.now()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Instant.html#now()) cũng nêu sự khác biệt giữa dùng đồng hồ hệ thống trực tiếp và dùng overload nhận một nguồn đồng hồ.

Một kiểm thử có thể lặp lại cần kiểm soát những đầu vào ảnh hưởng đến kết quả, trong đó có “hiện tại”. Không phải mọi kiểm thử đều phải đóng băng thời gian, nhưng khi cần kiểm tra chính xác ranh giới trước/đúng/sau một mốc, phải có cách chọn mốc quan sát.

## 2. Những dạng khó lặp lại thường gặp

### Kết quả đúng lúc viết bài rồi sai ở một ngày khác

Đoạn mã minh họa trong một phương thức:

```java
boolean expired = !Instant.now().isBefore(expiresAt);
```

Nếu `expiresAt` được viết cố định trong kiểm thử nhưng “hiện tại” là thời gian thật, kiểm thử không cố định cả hai phía của phép so sánh. Sau khi qua ngày hết hạn, kỳ vọng viết trước đó có thể không còn đúng. Sửa kỳ vọng theo từng năm chỉ che nguyên nhân phụ thuộc vào đồng hồ.

### Hai lần gọi không phải cùng một lần quan sát

Ví dụ một kiểm thử ghi nhận `before = Instant.now()`, gọi hàm tạo bản ghi, rồi so sánh `createdAt` phải bằng `before`. Trong khoảng giữa hai lần lấy giờ, thời gian đã có thể trôi qua; độ chính xác của đồng hồ và thời gian chạy không cho phép dựa vào việc bằng nhau.

Ngay trong một thao tác nghiệp vụ, gọi nhiều lần `LocalDate.now()` quanh thời điểm nửa đêm có thể lấy hai ngày khác nhau. Nếu yêu cầu thao tác dùng một mốc nhất quán, cần lấy mốc một lần rồi dùng lại. Việc lấy một lần giúp nhất quán trong thao tác; nó chưa tự làm kiểm thử kiểm soát được mốc đó.

### Cùng thời điểm, khác vùng thì khác ngày

`LocalDate.now()` dùng đồng hồ và vùng mặc định của hệ thống, theo [Java SE 21 — LocalDate.now()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html#now()). Một kiểm thử ngày đáo hạn có thể qua ở máy người viết nhưng sai ở môi trường dùng vùng khác, nhất là sát ranh giới ngày.

`LocalDate.now(zone)` làm rõ vùng nhưng vẫn lấy thời gian thật. Nó xử lý phụ thuộc vùng, chưa xử lý phụ thuộc thời điểm. `Instant.now()` không có bài toán chọn ngày địa phương để trả `Instant`, nhưng vẫn phụ thuộc đồng hồ hệ thống.

## 3. Đưa nguồn thời gian ra thành phụ thuộc rõ ràng

Có hai cách đơn giản theo cấu trúc ứng dụng:

| Nhu cầu | Cách đưa thời gian vào |
| --- | --- |
| Một phép tính chỉ cần một mốc để so sánh | Truyền `Instant now` hoặc ngày đã xác định vào hàm |
| Một đối tượng dịch vụ cần lấy giờ trong nhiều thao tác | Nhận `Clock` qua hàm khởi tạo hoặc tham số |

Ví dụ hàm tính thuần túy có thể nhận cả `expiresAt` và `observedNow`; nơi gọi có trách nhiệm quyết định mốc quan sát. Với đối tượng dịch vụ, `Clock` là nguồn giờ có thể thay thế. [Java SE 21 — Clock](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Clock.html) được thiết kế để ứng dụng có thể dùng đồng hồ hệ thống hoặc một đồng hồ được kiểm soát trong kiểm thử.

Khi chạy thật, có thể cung cấp `Clock.systemUTC()` nếu quy tắc dùng thời điểm UTC. Khi kiểm thử, `Clock.fixed(instant, zone)` luôn cung cấp cùng một thời điểm đã chọn. Những lời gọi như `Instant.now(clock)` hoặc `LocalDate.now(clock)` vẫn dùng tên `now`, nhưng “hiện tại” lúc này đến từ nguồn được truyền vào.

## 4. Chọn hợp đồng ranh giới trước khi kiểm thử

Trong bài, mã sử dụng hết hiệu lực khi `now >= expiresAt`. Nói cách khác, chỉ những thời điểm **trước** hạn mới còn hiệu lực. Vì vậy biểu thức là:

```java
return !observedNow.isBefore(expiresAt);
```

Nếu chỉ dùng `observedNow.isAfter(expiresAt)`, đúng bằng mốc hết hạn sẽ chưa bị coi là hết hạn. Đó là một hợp đồng khác, không phải khác biệt do đồng hồ. Kiểm thử phải xác nhận đúng quan hệ so sánh đã chọn.

Ba trường hợp dưới đây dùng `Instant` nên có thể chọn cách mốc một nano giây. Đây là kiểm tra logic so sánh của ứng dụng, không phải tuyên bố đồng hồ vật lý có độ chính xác một nano giây.

## 5. Chương trình kiểm chứng đầy đủ

Lưu mã vào `RepeatableNowDemo.java`. Chương trình dùng Java 17 trở lên, không cần thư viện kiểm thử bên ngoài. Mỗi điều kiện sai sẽ ném `AssertionError`, nên phép kiểm tra vẫn chạy dù không bật cờ `-ea`:

```java
import java.time.*;
import java.util.Objects;

public class RepeatableNowDemo {
    static final class ExpiryPolicy {
        private final Clock clock;

        ExpiryPolicy(Clock clock) {
            this.clock = Objects.requireNonNull(clock);
        }

        boolean isExpired(Instant expiresAt) {
            Instant observedNow = clock.instant();
            return !observedNow.isBefore(expiresAt);
        }
    }

    private static void check(String label, Instant now,
                              Instant deadline, boolean expected) {
        ExpiryPolicy policy = new ExpiryPolicy(Clock.fixed(now, ZoneOffset.UTC));
        boolean actual = policy.isExpired(deadline);
        if (actual != expected) {
            throw new AssertionError(label + ": expected " + expected
                    + ", got " + actual);
        }
        System.out.println(label + " = " + actual);
    }

    public static void main(String[] args) {
        Instant deadline = Instant.parse("2025-06-10T00:00:00Z");
        check("before deadline", deadline.minusNanos(1), deadline, false);
        check("at deadline", deadline, deadline, true);
        check("after deadline", deadline.plusNanos(1), deadline, true);

        Instant shared = Instant.parse("2025-06-09T18:00:00Z");
        Clock utc = Clock.fixed(shared, ZoneOffset.UTC);
        Clock hcm = utc.withZone(ZoneId.of("Asia/Ho_Chi_Minh"));
        System.out.println("UTC date = " + LocalDate.now(utc));
        System.out.println("HCM date = " + LocalDate.now(hcm));
        System.out.println("same instant = "
                + Instant.now(utc).equals(Instant.now(hcm)));
        System.out.println("fixed reads equal = "
                + Instant.now(utc).equals(Instant.now(utc)));

        System.out.println("all checks passed");
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 RepeatableNowDemo.java
java RepeatableNowDemo
```

Kết quả:

```text
before deadline = false
at deadline = true
after deadline = true
UTC date = 2025-06-09
HCM date = 2025-06-10
same instant = true
fixed reads equal = true
all checks passed
```

## 6. Vì sao chương trình lặp lại được?

### Cả mốc quan sát và hạn đều do kiểm thử quyết định

`check()` tạo `Clock.fixed(now, UTC)` cho từng tình huống. Hàm `isExpired()` dùng đồng hồ được cấp; không truy cập nguồn giờ hệ thống khác. Do đó, cùng `now` và `deadline` cho cùng kết quả trước/đúng/sau hạn mỗi lần chạy.

Không cần chờ đến năm 2025 hoặc thay đồng hồ máy. Ngày trong dữ liệu chỉ là mốc để chương trình tính, không yêu cầu thời gian thật phải đi tới mốc ấy.

### Quy tắc nghiệp vụ chỉ đọc đồng hồ một lần

Trong `isExpired()`, biến `observedNow` lưu một lần quan sát cho phép so sánh. Với logic nhiều nhánh dùng chung “hiện tại”, cách tổ chức tương tự tránh việc mỗi nhánh vô tình lấy một mốc khác.

Không suy ra rằng toàn bộ ứng dụng chỉ được phép đọc giờ đúng một lần. Một thao tác dài có thể cần quan sát nhiều mốc theo yêu cầu; điều cần làm rõ là khi nào cần một mốc nhất quán và khi nào muốn đo/quan sát một thời điểm mới.

### Vùng được kiểm tra độc lập với thời điểm

`utc` và `hcm` trong chương trình cùng trả `2025-06-09T18:00:00Z`. Tuy nhiên, ngày UTC là 9 tháng 6, còn ngày ở `Asia/Ho_Chi_Minh` đã sang 10 tháng 6. `same instant = true` cho thấy việc đổi ngày không phải đồng hồ chạy thêm giờ, mà là cách diễn giải theo vùng khác.

Vì `isExpired()` chỉ so sánh các `Instant`, vùng không thay đổi kết quả của quy tắc hết hạn đó. Với quy tắc theo ngày như “đến hết ngày kinh doanh”, cần chọn vùng kinh doanh và ngày tương ứng trước; không đổi sang UTC chỉ để làm kiểm thử dễ hơn nếu như vậy thay ý nghĩa nghiệp vụ.

## 7. Đưa cùng thiết kế vào mã chạy thật

Ở nơi khởi tạo dịch vụ, có thể cấp nguồn giờ hệ thống. Đoạn sau minh họa cách lắp đối tượng trong cùng phạm vi có thể truy cập `ExpiryPolicy`:

```java
ExpiryPolicy production = new ExpiryPolicy(Clock.systemUTC());
```

`systemUTC()` vẫn chạy theo thời gian hệ thống; nó chỉ cấu hình vùng UTC cho những cách đọc cần vùng. Khi dùng quy tắc theo ngày địa phương, có thể cung cấp `Clock.system(businessZone)` với `businessZone` đã được xác định. Không cần thay thuật toán chỉ để chuyển giữa đồng hồ thật và đồng hồ kiểm thử.

Một lựa chọn khác là giữ phần tính toán nhận `Instant observedNow`, còn lớp ở ranh giới đọc `clock.instant()` rồi truyền vào. Cách đó phù hợp khi muốn phần tính toán hoàn toàn không biết cách lấy “hiện tại”. Chọn mức tách phù hợp với phạm vi, không cần xây một hệ thống quản lý thời gian lớn chỉ cho một phép so sánh.

Cần bảo đảm những nhánh liên quan đều dùng nguồn đã truyền vào. Nếu một nhánh vẫn gọi `Instant.now()` hoặc tạo `Clock.systemUTC()` bên trong, đồng hồ cố định của kiểm thử không kiểm soát được nhánh đó.

## 8. Những cách khắc phục chưa giải quyết đúng vấn đề

**Chờ bằng `Thread.sleep()`.** Cách này làm kiểm thử chậm và phụ thuộc lập lịch của hệ điều hành; nó không giúp chọn đúng mốc bằng hạn. Với `Clock.fixed()`, chờ bao lâu cũng không làm đồng hồ ấy tự tiến. Muốn kiểm tra mốc khác, cấp đồng hồ cố định khác hoặc thiết kế nguồn giờ điều khiển được theo nhu cầu.

**Đổi vùng mặc định toàn JVM trong kiểm thử.** Việc này ảnh hưởng trạng thái dùng chung và có thể gây tương tác giữa các kiểm thử chạy song song. Truyền vùng/đồng hồ rõ ràng giúp thu hẹp phụ thuộc ngay tại nơi cần dùng.

**Chỉ làm tròn hoặc thêm khoảng dung sai cho mọi phép so sánh.** Một khoảng chấp nhận có thể phù hợp khi kiểm thử tích hợp thật sự quan sát dấu thời gian hệ thống. Nhưng nó không thay việc kiểm thử chính xác quy tắc bằng hạn hay qua ngày. Không dùng dung sai để che một hợp đồng ranh giới chưa rõ.

**Kiểm thử lại cùng biểu thức `now()` thay cho kiểm tra hành vi.** Nếu kỳ vọng cũng lấy giờ thật lần nữa, hai bên vẫn có thể nhìn hai mốc khác nhau. Hãy đặt mốc đã biết rồi kiểm tra nhánh kết quả hoặc giá trị đầu ra cần thiết.

## 9. Phạm vi bảo đảm và tự thực hành

Truyền `Clock` làm phụ thuộc thời gian của phần mã dùng nó có thể kiểm soát. Nó không tự điều khiển thời gian của cơ sở dữ liệu, tác vụ chạy theo lịch, bộ đếm thời gian của hệ điều hành hoặc một dịch vụ ngoài. Với kiểm thử đi qua nhiều thành phần, cần biết thành phần nào tạo dấu thời gian và nguồn nào đang được dùng.

Bài tập: thay hợp đồng hết hạn thành “chỉ hết hạn khi đã sau mốc, đúng bằng mốc vẫn hợp lệ”. Dự đoán ba kỳ vọng lần lượt là `false`, `false`, `true`, rồi đổi biểu thức so sánh tương ứng. Tiếp theo, giữ nguyên hợp đồng ban đầu và kiểm tra một ngày nghiệp vụ sát nửa đêm ở hai vùng. Hai phần giúp phân biệt lỗi quan hệ so sánh với lỗi lựa chọn thời điểm/vùng, thay vì gộp tất cả thành lỗi ngẫu nhiên của `now()`.
