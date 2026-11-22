# Cân bằng khả năng kiểm thử với đóng gói

Một lập trình viên muốn kiểm tra số lượt còn lại trong một thẻ sử dụng dịch vụ. Thay vì gọi hành vi sử dụng thẻ, người đó đổi trường `remainingUses` từ `private` sang `public` để test có thể đọc và ghi trực tiếp. Bài kiểm thử trở nên dễ viết hơn, nhưng bất kỳ thành phần nào trong hệ thống cũng có thể tự ý sửa số lượt và bỏ qua quy tắc nghiệp vụ. **Mã dễ kiểm thử hơn theo cách này lại kém an toàn và khó bảo trì hơn.**

Trong module **CODE_QUALITY_FUNDAMENTALS**, chúng ta tìm hiểu những thuộc tính giúp mã nguồn **đáng tin cậy, dễ hiểu và dễ thay đổi**. Ở chương **Khả năng kiểm thử**, bài này tập trung vào một đánh đổi quan trọng: **làm sao tạo đủ điểm quan sát và kiểm soát để kiểm thử đáng tin cậy mà không làm lộ chi tiết triển khai hoặc phá vỡ tính đóng gói?**

Ý tưởng cốt lõi là: **kiểm thử điều mà thành phần cam kết thực hiện, đồng thời điều khiển những phụ thuộc cần thiết ở ranh giới của nó**. Không nên mặc định rằng test phải đọc được mọi trường riêng tư hoặc gọi được mọi phương thức `private`.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **khả năng kiểm thử (testability)**, **khả năng quan sát (observability)** và **tính đóng gói (encapsulation)** trong mã Java.
- Nhận biết khi nào một getter, setter hoặc phương thức công khai chỉ được thêm để chiều theo test và làm yếu hợp đồng của đối tượng.
- Kiểm thử qua **hành vi công khai**, dùng đầu vào, đầu ra, lỗi và tác dụng phụ có ý nghĩa nghiệp vụ.
- Kiểm soát các phụ thuộc ngoài phạm vi hàm, như đồng hồ, kho dữ liệu và cổng gửi thông điệp, bằng cách truyền phụ thuộc thích hợp.
- Quyết định khi nào nên trích xuất quy tắc thành một thành phần riêng, khi nào cần unit test hay integration test, và khi nào kiểm tra chi tiết triển khai chỉ tạo ra test dễ vỡ.

## 1. Vì sao kiểm thử và đóng gói có vẻ mâu thuẫn?

**Đóng gói** là việc một thành phần quản lý trạng thái và quy tắc của mình thông qua một giao diện có kiểm soát. Người dùng thành phần được biết **có thể yêu cầu hành vi gì**, không nhất thiết phải biết **bên trong dùng trường, collection hoặc thuật toán nào**.

**Khả năng kiểm thử** là mức độ dễ thiết lập điều kiện, thực thi hành vi, quan sát kết quả và xác định kết quả có đúng hay không một cách đáng tin cậy.

Tưởng như hai mục tiêu kéo theo hai hướng:

| Mong muốn | Cách làm vội vàng | Vấn đề |
| --- | --- | --- |
| Quan sát trạng thái sau khi gọi hàm | Cho test đọc trực tiếp mọi trường `private` | Chi tiết triển khai trở thành thứ test phụ thuộc |
| Thiết lập dữ liệu cho từng tình huống | Thêm `setRemainingUses(int)` công khai | Người dùng thật cũng có thể tạo trạng thái không hợp lệ |
| Kiểm tra một phép tính phụ | Đổi phương thức `private` thành `public` | Tăng API công khai chỉ để test nội bộ |
| Giả lập thời gian hoặc dữ liệu bên ngoài | Sửa biến `static` toàn cục trong từng test | Test ảnh hưởng lẫn nhau, khó chạy song song |
| Biết thuật toán có chạy không | Verify mọi lời gọi helper hoặc mock toàn bộ lớp | Test khóa chặt vào cách cài đặt, dễ vỡ khi refactor |

Điểm cần phân biệt là **test cần quan sát điều gì**. Nếu người dùng sản phẩm chỉ quan tâm một thẻ còn bao nhiêu lượt, có dùng được không và khi sử dụng thì số lượt thay đổi ra sao, những điều này phải được quan sát qua hợp đồng nghiệp vụ. Test không cần biết trường đó được lưu dưới dạng `int`, một đối tượng trạng thái hay một hàng trong cơ sở dữ liệu.

## 2. Một ví dụ dễ kiểm thử nhưng đóng gói yếu

Giả sử yêu cầu nghiệp vụ **đã được xác nhận** cho thẻ sử dụng:

- Thẻ có số lượt ban đầu **lớn hơn 0**.
- Mỗi lần sử dụng thành công tiêu tốn **một lượt**.
- Không thể sử dụng nếu đã hết lượt.
- Thẻ chỉ còn hiệu lực **trước** thời điểm hết hạn; tại đúng thời điểm hết hạn, thẻ đã hết hiệu lực.
- Sử dụng thất bại không làm giảm số lượt.

Đây là đặc tả giả định dành cho bài học; hệ thống thật có thể có thêm quy tắc khác.

Một thiết kế yếu:

~~~java
import java.time.Instant;

public class UnsafeAccessPass {
    public int remainingUses;
    public Instant expiresAt;

    public UnsafeAccessPass(int remainingUses, Instant expiresAt) {
        this.remainingUses = remainingUses;
        this.expiresAt = expiresAt;
    }

    public void use() {
        if (remainingUses > 0 && Instant.now().isBefore(expiresAt)) {
            remainingUses--;
        }
    }
}
~~~

Test có thể viết `pass.remainingUses = -10` để tạo một ca kiểm tra. Nhưng người gọi trong ứng dụng cũng có thể làm như vậy. Kết quả là:

1. **Không bảo vệ bất biến:** số lượt có thể âm hoặc tăng không đúng quy tắc.
2. **Không rõ thất bại:** `use()` im lặng khi thẻ hết lượt hoặc hết hạn, khiến người gọi khó xác định có sử dụng thành công không.
3. **Phụ thuộc ẩn vào đồng hồ:** test gần mốc hết hạn có thể thành công hoặc thất bại tùy thời điểm chạy.
4. **Test bị buộc vào cách lưu:** nếu đổi trường `remainingUses` thành đối tượng khác, test đọc trường trực tiếp phải viết lại dù hành vi hợp lệ không thay đổi.

Đổi trường sang `private` nhưng tạo setter công khai để test viết lại nó **không khắc phục gốc vấn đề**. Quyền sửa trạng thái vẫn bị mở ra ngoài hợp đồng nghiệp vụ.

## 3. Thiết kế một đối tượng vừa đóng gói vừa kiểm thử được

Thay vì cho bên ngoài trực tiếp chỉnh số lượt, đối tượng nên có các **thao tác mang ý nghĩa nghiệp vụ**. Thời gian là phụ thuộc có thể được kiểm soát tại điểm tạo đối tượng.

Ví dụ sau dùng Java 17 trở lên:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

public final class AccessPass {
    private final Instant expiresAt;
    private final Clock clock;
    private int remainingUses;

    public AccessPass(int initialUses, Instant expiresAt, Clock clock) {
        if (initialUses <= 0) {
            throw new IllegalArgumentException(
                "initialUses must be positive"
            );
        }

        this.expiresAt = Objects.requireNonNull(expiresAt, "expiresAt");
        this.clock = Objects.requireNonNull(clock, "clock");
        this.remainingUses = initialUses;
    }

    public boolean canUse() {
        return remainingUses > 0 && clock.instant().isBefore(expiresAt);
    }

    public void use() {
        if (!canUse()) {
            throw new IllegalStateException("Pass cannot be used");
        }
        remainingUses--;
    }

    public int remainingUses() {
        return remainingUses;
    }
}
~~~

Người dùng đối tượng chỉ cần biết:

- `canUse()`: ở **thời điểm kiểm tra hiện tại**, thẻ có đáp ứng điều kiện sử dụng không?
- `use()`: yêu cầu tiêu tốn một lượt; nếu không hợp lệ thì báo lỗi.
- `remainingUses()`: có bao nhiêu lượt còn lại?

Trường `remainingUses` vẫn `private`; không có `setRemainingUses`. Người dùng không thể tùy ý nâng lượt hoặc làm âm số lượt bằng API công khai. `Instant` là kiểu giá trị bất biến, còn `Clock` được truyền qua constructor, nên test có thể chọn thời gian **mà không can thiệp vào đồng hồ của cả máy**.

### Vì sao `remainingUses()` không phá vỡ đóng gói?

Phương thức đọc này công khai **thông tin nghiệp vụ hữu ích**: số lượt còn lại, vốn có thể cần để hiển thị cho người sử dụng. Nó không cho phép người gọi sửa trạng thái, và không bắt họ biết trường được lưu trữ ra sao.

Ngược lại, một phương thức như `getInternalCounterArray()` trả ra mảng nội bộ có thể sửa sẽ làm lộ cách biểu diễn và trao quyền thay đổi dữ liệu. Tên bắt đầu bằng `get` không làm một phương thức tự động an toàn.

**Một truy vấn công khai nên được biện minh bởi hợp đồng của thành phần, không phải chỉ bởi việc test cần đọc một biến.** Nếu số lượt còn lại không phải thông tin nghiệp vụ được phép công bố, có thể kiểm thử kết quả qua những thao tác khác thay vì thêm getter.

## 4. Kiểm thử hành vi công khai bằng JUnit 5

`Clock.fixed(...)` cho phép tạo các tình huống trước, đúng và sau thời điểm hết hạn mà không cần `Thread.sleep()` hoặc thay đồng hồ hệ thống.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

class AccessPassTest {
    private static final Instant EXPIRES_AT =
        Instant.parse("2026-11-16T12:00:00Z");

    private AccessPass passAt(String now, int initialUses) {
        Clock clock = Clock.fixed(
            Instant.parse(now),
            ZoneOffset.UTC
        );
        return new AccessPass(initialUses, EXPIRES_AT, clock);
    }

    @Test
    void usingPassConsumesOneUse() {
        AccessPass pass = passAt("2026-11-16T11:59:59Z", 2);

        assertTrue(pass.canUse());
        pass.use();

        assertEquals(1, pass.remainingUses());
        assertTrue(pass.canUse());
    }

    @Test
    void noUseIsAllowedAfterLastUse() {
        AccessPass pass = passAt("2026-11-16T11:59:59Z", 1);
        pass.use();

        assertFalse(pass.canUse());
        assertThrows(IllegalStateException.class, pass::use);
        assertEquals(0, pass.remainingUses());
    }

    @Test
    void exactExpiryRejectsUseWithoutChangingState() {
        AccessPass pass = passAt("2026-11-16T12:00:00Z", 2);

        assertFalse(pass.canUse());
        assertThrows(IllegalStateException.class, pass::use);
        assertEquals(2, pass.remainingUses());
    }

    @Test
    void invalidInitialUsesAreRejected() {
        Clock clock = Clock.fixed(
            Instant.parse("2026-11-16T11:59:59Z"),
            ZoneOffset.UTC
        );

        assertThrows(
            IllegalArgumentException.class,
            () -> new AccessPass(0, EXPIRES_AT, clock)
        );
    }
}
~~~

Những bài kiểm thử trên:

- Không đọc hoặc sửa trường `private`.
- Không gọi phương thức hỗ trợ nội bộ.
- Kiểm tra **kết quả được cam kết**: thành công làm giảm một lượt, hết lượt bị từ chối, đúng giờ hết hạn bị từ chối và thất bại không làm đổi số lượt.
- Có thể được chạy lại ở thời điểm khác mà không phụ thuộc vào đồng hồ thực.

Nếu sau này mã nguồn đổi từ `int remainingUses` sang một mô hình lưu trữ khác nhưng vẫn giữ hợp đồng công khai, các test này **có cơ hội giữ nguyên**. Đó là lợi ích quan trọng của việc kiểm thử dựa trên hành vi.

**Giới hạn của ví dụ:** `AccessPass` là mô hình bộ nhớ đơn giản, chưa giải quyết việc nhiều luồng gọi `use()` đồng thời hay lưu số lượt vào cơ sở dữ liệu. Nếu sản phẩm có yêu cầu đồng thời hoặc lưu bền vững, cần cơ chế kiểm soát tương ứng và kiểm thử tích hợp. `canUse()` chỉ cung cấp thông tin tại thời điểm gọi, không bảo đảm rằng một lời gọi `use()` trong tương lai chắc chắn thành công.

## 5. Test nên quan sát hành vi nào?

Hãy hình dung có hai nhóm bài kiểm thử.

**Nhóm A — Kiểm thử hợp đồng:**

~~~java
pass.use();
assertEquals(1, pass.remainingUses());
~~~

Test này kiểm tra kết quả có ý nghĩa: một lần dùng thành công giảm đúng một lượt.

**Nhóm B — Kiểm thử chi tiết triển khai (mã minh họa giả định):**

~~~java
// Không phải API của AccessPass ở ví dụ trên.
// verify(pass).validateExpiry();
// verify(pass).decrementInternalCounter();
~~~

Nhóm B muốn xác nhận helper nào được gọi và gọi bao nhiêu lần, thay vì xác nhận số lượt thực tế. Nếu refactor gộp hai helper, test có thể thất bại dù hành vi nghiệp vụ vẫn đúng.

| Câu hỏi | Nên ưu tiên kiểm thử qua đâu? |
| --- | --- |
| Một thao tác thành công tạo ra kết quả gì? | Giá trị trả về, trạng thái công khai theo hợp đồng |
| Một thao tác bị từ chối thì sao? | Loại lỗi/kết quả từ chối, trạng thái không đổi |
| Có phát sinh tác dụng phụ nghiệp vụ không? | Thông điệp, dữ liệu ghi hoặc sự kiện đã cam kết |
| Một thuật toán nội bộ có mấy bước? | Thường không cần khóa chặt bằng unit test |
| Một phụ thuộc bên ngoài được gọi theo hợp đồng nào? | Test ranh giới tích hợp hoặc fake/spy khi tương tác là hành vi cần bảo đảm |

Không phải mọi kiểm tra số lần gọi đều xấu. Ví dụ, nếu hợp đồng quy định “không gửi hai lần cùng một yêu cầu thanh toán”, số lần phát lệnh ở ranh giới thanh toán là **một hành vi quan trọng**, cần xác minh. Vấn đề là phân biệt **tương tác có ý nghĩa nghiệp vụ** với **chi tiết phụ trợ chỉ phục vụ cách triển khai hiện tại**.

## 6. Không cần mở `private` chỉ để thử một helper

Giả sử `AccessPass` có phương thức nội bộ:

~~~java
private boolean isBeforeExpiry() {
    return clock.instant().isBefore(expiresAt);
}
~~~

Có ba lựa chọn khi muốn kiểm thử quy tắc này:

1. **Giữ `private` và kiểm thử qua `canUse()`/`use()`.** Với logic đơn giản và hợp đồng rõ, cách này thường tốt nhất. Kiểm tra đúng thời điểm hết hạn qua hành vi công khai đã bắt được lỗi `<=` thay vì `<`.
2. **Trích xuất một thành phần nghiệp vụ thực sự độc lập** nếu quy tắc phức tạp, có nhiều tình huống và được sử dụng ở nhiều nơi. Chẳng hạn, nếu quy tắc hiệu lực phụ thuộc lịch nghỉ, thời gian gia hạn và vùng giờ, một `ValidityPolicy` với hợp đồng rõ có thể có lý do tồn tại ngoài mục đích test.
3. **Dùng phạm vi truy cập package-private có cân nhắc** nếu cấu trúc module cho phép và quy tắc là một cộng tác viên nội bộ quan trọng. Test cùng package có thể truy cập, nhưng phải chấp nhận rằng các lớp khác trong package cũng có thể gọi. Đây không phải một “quyền truy cập dành riêng cho test”.

Không nên mặc định chọn `public` hoặc reflection chỉ vì test muốn chạm vào phương thức nhỏ. Trong Java, gọi phương thức riêng bằng reflection thường làm test phụ thuộc vào **tên, chữ ký và cấu trúc nội bộ**, có thể bị ảnh hưởng bởi cơ chế module, quyền truy cập và thay đổi mã. Nếu phải dùng reflection để kiểm tra hành vi cơ bản, đó là tín hiệu nên xem lại cách đặt ranh giới và thiết kế test.

### Khi nào trích xuất lớp là hợp lý?

Một lớp `ValidityPolicy` có ích nếu nó là một **khái niệm có trách nhiệm rõ**, chẳng hạn có nhiều khách hàng hoặc nhiều đối tượng cần dùng cùng chính sách. Nhưng nếu chỉ có một phép so sánh `Instant`, tạo interface, factory và nhiều lớp chỉ để gọi một dòng code sẽ tăng chi phí hiểu và bảo trì.

**Không phải mọi phép tính có thể tách đều nên trở thành một abstraction mới.** Giá trị của việc trích xuất là giảm trách nhiệm lẫn lộn hoặc làm rõ mô hình, không chỉ làm tăng số test “trực tiếp”.

## 7. Kiểm soát phụ thuộc thay vì làm lộ trạng thái

Đôi khi test khó viết không phải vì các trường `private`, mà vì mã đang tự lấy những thứ **khó kiểm soát**:

~~~java
public boolean canUse() {
    return remainingUses > 0
        && Instant.now().isBefore(expiresAt);
}
~~~

Nếu test phải thay thời gian hệ thống hoặc chờ đến lúc thẻ hết hạn, bài kiểm thử rất dễ không ổn định. Thay vì mở trường `expiresAt` để test tùy ý chỉnh, hãy đưa **nguồn thời gian** thành phụ thuộc rõ ràng.

Trong ví dụ `AccessPass`, phụ thuộc là `Clock` ở constructor. Ở chương trình thực tế, điểm khởi tạo có thể truyền `Clock.systemUTC()`; trong test, truyền `Clock.fixed(...)`. Cùng một hợp đồng được dùng ở hai môi trường mà không yêu cầu test sửa trạng thái ẩn của ứng dụng.

Các phụ thuộc thường đáng kiểm soát:

| Phụ thuộc khó dự đoán | Cách đưa vào ranh giới | Điều test có thể kiểm soát |
| --- | --- | --- |
| Thời điểm hiện tại | `Clock` | Trước, đúng, sau hạn |
| Mã ngẫu nhiên/ID | `IdGenerator` có hợp đồng | ID ổn định trong test |
| Kho dữ liệu | `Repository` | Dữ liệu có/không, lỗi lưu trữ |
| HTTP/đối tác | Gateway/client interface | Thành công, timeout, mã lỗi |
| Cấu hình chính sách | Đối tượng cấu hình bất biến | Các mức ngưỡng và lựa chọn |
| Lịch chạy tác vụ | Scheduler/queue adapter | Tác vụ nào được lên lịch, thời điểm theo hợp đồng |

Không phải loại phụ thuộc nào cũng cần interface. `Clock` của thư viện Java đã phù hợp. Một hàm thuần chỉ xử lý các tham số đầu vào có thể không cần dependency injection. Hãy kiểm soát những yếu tố thật sự khiến test không thể tái hiện hoặc làm logic phải gắn với hạ tầng.

## 8. Fake, stub và spy nên được đặt ở ranh giới

Khi một dịch vụ phải lưu dữ liệu hoặc gửi thông báo, kiểm thử đơn vị có thể thay hệ thống bên ngoài bằng một **test double** có hành vi xác định trước.

- **Stub** cung cấp giá trị hoặc kết quả được kiểm soát, chẳng hạn repository trả “không tìm thấy”.
- **Fake** có cài đặt đơn giản nhưng hoạt động được trong test, chẳng hạn một repository lưu trong bộ nhớ.
- **Spy** ghi nhận tương tác để test xác minh, chẳng hạn thông báo nào được yêu cầu gửi.

Ví dụ, một dịch vụ gửi xác nhận khi thẻ được sử dụng có thể phụ thuộc vào một hợp đồng:

~~~java
public interface UseEventPublisher {
    void publishUsed(String passId);
}
~~~

Trong một bài kiểm thử, có thể dùng fake/spy:

~~~java
import java.util.ArrayList;
import java.util.List;

final class RecordingPublisher implements UseEventPublisher {
    private final List<String> publishedPassIds = new ArrayList<>();

    @Override
    public void publishUsed(String passId) {
        publishedPassIds.add(passId);
    }

    public List<String> publishedPassIds() {
        return List.copyOf(publishedPassIds);
    }
}
~~~

Nếu hợp đồng nghiệp vụ cam kết mỗi lần sử dụng thành công phát **một** thông báo với mã thẻ tương ứng, test của **dịch vụ tích hợp Publisher** có thể xác minh danh sách `publishedPassIds`. Cần lưu ý `RecordingPublisher` là thành phần thử nghiệm minh họa; lớp `AccessPass` ở phần 3 không sử dụng publisher và **không nên thêm publisher vào nó chỉ để minh họa test**.

Khi tích hợp thật, cần kiểm tra thêm các tình huống gửi thất bại, retry, thứ tự và idempotency nếu đó là hợp đồng. Spy chỉ cho biết **một lời gọi đã được thực hiện trong môi trường test**, không chứng minh một dịch vụ ngoài đã nhận thành công hoặc dữ liệu đã được commit.

### Những thứ không nên mock quá mức

Không nên mock mọi đối tượng giá trị hoặc helper đơn giản. Ví dụ `Instant`, `SeatCount` hay một hàm cộng điểm thuần túy thường có thể dùng trực tiếp trong test. Mock những đối tượng này sẽ khiến test khó hiểu mà không kiểm soát thêm rủi ro thực tế.

Tương tự, việc verify một danh sách dài các lời gọi nội bộ `validate()`, `normalize()`, `calculate()` có thể làm test vỡ khi đổi cách tổ chức, dù kết quả cuối không đổi. Chỉ khóa thứ tự hoặc số lần gọi nếu **thứ tự hoặc số lần đó là một phần của hợp đồng**.

## 9. Kiểm thử qua API công khai không có nghĩa bỏ qua cấu trúc nội bộ

Một số lập trình viên hiểu sai rằng “chỉ kiểm thử hành vi công khai” nghĩa là tất cả test phải đi qua controller HTTP hoặc màn hình người dùng. Điều đó không cần thiết.

Đối với một **đơn vị có hợp đồng rõ**, có thể kiểm thử trực tiếp API của đơn vị:

- Với `AccessPass`, đó là `use()`, `canUse()` và `remainingUses()`.
- Với một thành phần chính sách được tách độc lập, đó có thể là `evaluate(input)`.
- Với repository adapter, đó là phương thức truy vấn/lưu trữ theo hợp đồng.

Vấn đề không phải một test có gọi “public” theo từ khóa Java hay không, mà là **test đang chứng minh một hợp đồng có ý nghĩa hay đang khóa cách một lớp được cài đặt vào hôm nay**.

Đóng gói có nhiều mức:

| Ranh giới | Hợp đồng cần kiểm tra | Chi tiết không nên phụ thuộc tùy tiện |
| --- | --- | --- |
| Đối tượng nghiệp vụ | Chuyển trạng thái, bất biến, kết quả thao tác | Trường `private`, thuật toán phụ trợ |
| Service/use case | Kết quả nghiệp vụ, phối hợp tác dụng phụ | Tên và số helper nội bộ |
| Adapter dữ liệu | Lưu/đọc đúng, transaction theo cam kết | Cách viết SQL cụ thể nếu không thuộc hợp đồng |
| HTTP API | Status, payload, lỗi, quyền truy cập | Cấu trúc lớp controller và service bên trong |

Một test kiểm tra trực tiếp implementation vì lý do hiệu năng, thuật toán hoặc điều kiện lỗi khó tới được qua tầng ngoài vẫn có thể hữu ích. Điều cần tránh là **để các test đó xác định hợp đồng công khai thay vì yêu cầu nghiệp vụ** và làm mọi refactor phải giữ nguyên chi tiết không được cam kết.

## 10. Khi nào test khó là dấu hiệu thiết kế cần cải thiện?

Một số triệu chứng nên khiến nhóm xem lại trách nhiệm và ranh giới:

| Triệu chứng | Nguyên nhân có thể | Hướng xem xét |
| --- | --- | --- |
| Muốn test một quy tắc nhỏ phải khởi động database và HTTP server | Logic nghiệp vụ trộn chặt với I/O | Tách phép tính/điều kiện khỏi adapter |
| Test phải sửa biến `static` rồi khôi phục trong `finally` | Phụ thuộc ẩn hoặc trạng thái toàn cục | Truyền cấu hình, clock hoặc cộng tác viên tường minh |
| Test phải gọi reflection vào nhiều `private` | Test phụ thuộc vào cấu trúc nội bộ | Kiểm thử qua hợp đồng hoặc trích xuất trách nhiệm thực sự |
| Test có nhiều mock hơn dữ liệu nghiệp vụ | Thành phần đang ôm nhiều trách nhiệm hoặc test ở mức không phù hợp | Giảm phạm vi test, tách trách nhiệm, cân nhắc integration test |
| Mọi refactor đều làm hàng chục test thất bại | Verify quá chi tiết cách thực hiện | Chuyển trọng tâm sang kết quả/hành vi quan sát được |
| Không biết quan sát kết quả thành công hay thất bại | API không có kết quả hoặc điểm quan sát rõ | Làm rõ hợp đồng trả về, trạng thái và lỗi |
| Muốn đặt trạng thái bất hợp lệ bằng setter công khai | Đối tượng không có điểm tạo hợp lệ cho tình huống đó | Test qua thao tác được phép; cân nhắc factory/fixture trong test |

Không phải test khó nào cũng có nghĩa production code sai thiết kế. Có những hệ thống tích hợp vốn phức tạp thật sự; với chúng, integration test hoặc end-to-end test là chi phí phù hợp. Đừng thêm một ranh giới trừu tượng chỉ để mọi test đều trở thành unit test.

## 11. Những đánh đổi khi thiết kế cho khả năng kiểm thử

| Lựa chọn | Lợi ích | Chi phí hoặc rủi ro |
| --- | --- | --- |
| Giữ trường và helper `private` | Bảo vệ bất biến, tự do refactor | Test phải dựa vào hành vi thay vì nhìn trực tiếp bên trong |
| Thêm truy vấn nghiệp vụ `remainingUses()` | Cho UI và test quan sát trạng thái hợp lệ | Mở rộng hợp đồng công khai; phải duy trì ý nghĩa truy vấn |
| Truyền `Clock` hoặc repository qua constructor | Test kiểm soát điều kiện, phụ thuộc rõ ràng | Thêm bước khởi tạo/wiring |
| Trích xuất policy độc lập | Logic có trách nhiệm riêng, dễ kiểm thử | Thêm lớp và ranh giới có thể không cần nếu quy tắc đơn giản |
| Dùng package-private cho một thành phần nội bộ | Có thể test trực tiếp khi thật sự cần | Không chỉ test mà cả package đều truy cập được |
| Dùng fake/spy ở cổng ngoài | Quan sát tương tác quan trọng, không gọi hệ thống thật | Có thể khác hành vi adapter thật; cần integration test bổ sung |
| Dùng getter/setter mọi nơi | Test dễ thao tác trạng thái | Phá bất biến, làm API rộng, tăng liên kết |

Không có mục tiêu “mỗi phương thức một unit test” hay “mọi trường đều phải có getter”. Mục tiêu là **phần hành vi quan trọng được kiểm tra đủ tin cậy mà mô hình vẫn giữ được trách nhiệm và quy tắc của mình**.

## 12. Quy trình thực tế khi gặp một lớp khó kiểm thử

Khi cần thêm kiểm thử cho một lớp đã tồn tại, có thể theo quy trình:

1. **Xác định hợp đồng:** những đầu vào nào được hỗ trợ, kết quả/ngoại lệ nào là đúng, trạng thái nào không được vi phạm và tác dụng phụ nào phải xảy ra?
2. **Tìm điểm quan sát hợp lệ:** giá trị trả về, truy vấn nghiệp vụ, dữ liệu ghi nhận, sự kiện được công bố. Tránh bắt đầu bằng việc liệt kê tất cả trường `private`.
3. **Tìm nguồn không xác định:** đồng hồ, số ngẫu nhiên, database, file, HTTP, biến toàn cục, scheduling hoặc thread. Chỉ đưa ra ranh giới những phụ thuộc thật sự cần điều khiển.
4. **Viết test mô tả hành vi:** trường hợp bình thường, giá trị biên, đầu vào sai và thất bại không được làm thay đổi trạng thái. Với mã cũ chưa có tài liệu, ghi nhận hành vi hiện tại rồi đối chiếu với yêu cầu.
5. **Thay cấu trúc nhỏ và kiểm tra lại:** dùng constructor injection, trích xuất policy hoặc đưa thao tác về đúng đối tượng nếu việc đó làm rõ trách nhiệm.
6. **Giữ mức truy cập nhỏ nhất phù hợp:** không công khai helper chỉ vì test. Nếu thêm phương thức đọc, bảo đảm có ý nghĩa trong hợp đồng.
7. **Bổ sung integration test cho adapter thật:** fake không chứng minh truy vấn database hoặc giao thức mạng đúng. Kiểm tra ranh giới quan trọng với môi trường tương ứng.
8. **Review độ bền của test:** một lần đổi tên helper hoặc thay cách tính nội bộ có khiến test vỡ không, dù hành vi đúng? Nếu có, xem lại mức phụ thuộc vào implementation.

Trong code review, một câu hỏi hữu ích là: **“Nếu thay toàn bộ thuật toán bên trong mà vẫn giữ kết quả và tác dụng phụ đã cam kết, những test nào nên tiếp tục đạt?”** Câu trả lời giúp phân biệt test bảo vệ hợp đồng với test chỉ bảo vệ cấu trúc hiện tại.

## 13. Bài tập tình huống

Một lớp quản lý hạn mức chuyển điểm có đoạn mã sau:

~~~java
class TransferLimit {
    public int remaining;

    public TransferLimit(int remaining) {
        this.remaining = remaining;
    }

    public boolean transfer(int points) {
        if (points > remaining) {
            return false;
        }
        remaining -= points;
        return true;
    }
}
~~~

Giả sử chính sách đã được xác nhận: hạn mức khởi tạo không âm; số điểm chuyển phải **lớn hơn 0**; chuyển thành công giảm hạn mức đúng bằng số điểm chuyển; thất bại không làm thay đổi hạn mức.

**Câu hỏi A.** Chỉ ra ít nhất ba cách người gọi hoặc test có thể đưa lớp vào trạng thái sai hoặc nhận kết quả sai.

**Câu hỏi B.** Đề xuất một API công khai vừa bảo vệ bất biến vừa cho phép người dùng biết hạn mức còn lại. Có cần setter công khai cho test không?

**Câu hỏi C.** Viết ba tình huống test có ý nghĩa: chuyển thành công, chuyển quá hạn mức và chuyển số điểm không hợp lệ.

### Gợi ý đáp án

**A.** Có thể tạo `new TransferLimit(-5)`; đặt `remaining = -100` trực tiếp; gọi `transfer(-1)` khiến `remaining` tăng lên; gọi `transfer(0)` có thể trả thành công dù chính sách cấm. Những sai sót này cho thấy test đọc/ghi trường công khai không bảo vệ được tính đúng đắn.

**B.** Có thể dùng một constructor kiểm tra hạn mức ban đầu, trường `private int remaining`, truy vấn `remainingPoints()` và thao tác `transfer(int points)` kiểm tra `points > 0`. Không cần `setRemaining` công khai. Với chính sách “chuyển quá hạn mức” trả `false`, phương thức có thể giữ kết quả Boolean; với số điểm không hợp lệ, có thể ném `IllegalArgumentException` nếu hợp đồng quy định như vậy.

Ví dụ phác thảo:

~~~java
public final class TransferLimit {
    private int remaining;

    public TransferLimit(int initialPoints) {
        if (initialPoints < 0) {
            throw new IllegalArgumentException("Negative limit");
        }
        this.remaining = initialPoints;
    }

    public int remainingPoints() {
        return remaining;
    }

    public boolean transfer(int points) {
        if (points <= 0) {
            throw new IllegalArgumentException("Points must be positive");
        }
        if (points > remaining) {
            return false;
        }
        remaining -= points;
        return true;
    }
}
~~~

**C.** Có thể kiểm tra: từ hạn mức 10 chuyển 4 → trả `true`, còn 6; chuyển 11 → trả `false`, vẫn còn 10; chuyển 0 hoặc -1 → `IllegalArgumentException`, hạn mức không đổi. Test chỉ dùng constructor, `transfer()` và `remainingPoints()` — không cần truy cập trạng thái nội bộ.

Nếu nhiều luồng có thể chuyển đồng thời từ cùng một hạn mức, đoạn mã phác thảo trên **chưa đủ an toàn luồng**. Khi đó cần kiểm soát cập nhật nguyên tử hoặc transaction phù hợp. Khả năng test tốt không thay thế việc xác định đúng phạm vi đồng thời của hệ thống.

## Ghi nhớ

**Khả năng kiểm thử và đóng gói không đối lập nếu ta kiểm thử đúng ranh giới.** Một thành phần nên công bố **hành vi, kết quả và trạng thái nghiệp vụ cần thiết**, nhưng vẫn giữ quyền kiểm soát các bất biến và chi tiết triển khai. Thay vì mở trường `private` hoặc thêm setter cho test, hãy ưu tiên **kiểm thử qua hợp đồng công khai**, điều khiển **phụ thuộc không xác định** từ ranh giới, và chỉ trích xuất cấu trúc mới khi nó phản ánh trách nhiệm thực sự.

Mã nguồn đáng tin cậy không phải mã có số test nhiều nhất hay số lượng API công khai lớn nhất, mà là mã **có những quy tắc quan trọng được kiểm chứng**, **khó bị sử dụng sai** và **có thể đổi cách triển khai mà không làm vỡ các kiểm thử dựa trên hành vi hợp lệ**.
