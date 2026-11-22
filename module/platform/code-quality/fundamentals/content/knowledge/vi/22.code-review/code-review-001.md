# Mục tiêu của rà soát mã và giới hạn của việc đọc thủ công

Một pull request thêm chức năng giữ chỗ cho sự kiện. Người rà soát đọc phương thức Java: nếu số ghế còn lại đủ thì trừ đi số ghế khách yêu cầu. Tên biến rõ, điều kiện dễ hiểu, formatter không báo lỗi và unit test cho một người đặt chỗ đều xanh. Tuy nhiên, hai khách có thể đặt cùng **ghế cuối cùng** vào gần như cùng một lúc. Cả hai lời gọi đọc được số ghế còn lại là 1 trước khi bất kỳ lời gọi nào cập nhật trạng thái, rồi cùng báo thành công.

Đọc một thay đổi bằng mắt có thể giúp phát hiện **giả định về truy cập đồng thời**; nhưng việc một người đã đọc và nhấn “Approve” không chứng minh mọi thứ tự chạy, cấu hình cơ sở dữ liệu hoặc tình huống lỗi thực tế đều an toàn.

Trong module **CODE_QUALITY_FUNDAMENTALS**, chúng ta tìm hiểu những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi** hay không. Ở chương **Rà soát mã**, bài này bàn về **mục tiêu của code review**, **những giới hạn của việc đọc thủ công** và cách phối hợp review với kiểm thử, phân tích tự động, thiết kế hệ thống và bằng chứng vận hành để đưa ra quyết định có trách nhiệm.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Trình bày mục tiêu của code review: **bảo vệ hợp đồng hành vi, giảm rủi ro thiết kế, cải thiện khả năng hiểu và chia sẻ hiểu biết**, không chỉ tìm lỗi cú pháp.
- Phân biệt điều reviewer có thể đánh giá trực tiếp từ mã với điều cần **thực thi, đo lường hoặc xác minh ở môi trường phù hợp**.
- Nhận diện giới hạn của review chỉ nhìn diff, thiếu yêu cầu, thiếu bối cảnh, quá tải nhận thức và thiên kiến khi đã có test xanh.
- Đưa ra nhận xét review **có vị trí, cơ chế rủi ro, tác động và hướng kiểm chứng** thay vì chỉ nói “mã chưa tốt”.
- Sử dụng ví dụ Java 17/JUnit 5 để thấy vì sao review về concurrent state phải đi cùng kiểm thử và bảo đảm tại tầng lưu trữ.
- Chọn đúng công việc cho con người, formatter/linter, static analysis, test và hoạt động sau triển khai.

## 1. Code review là gì và không phải là gì?

**Code review** là hoạt động một hoặc nhiều người xem xét thay đổi mã nguồn, cách sử dụng các hợp đồng liên quan và bằng chứng đi kèm trước khi chấp nhận hoặc triển khai thay đổi. Nó có thể diễn ra qua pull request, pair programming, cuộc họp rà soát thiết kế hoặc kiểm tra thay đổi khẩn cấp theo quy trình riêng.

Một review tốt hỏi:

1. **Tại sao cần thay đổi này?** Yêu cầu và trường hợp sử dụng nào đang được giải quyết?
2. **Mã làm điều được yêu cầu không?** Có thiếu đường lỗi, giá trị biên hoặc bất biến quan trọng?
3. **Thành phần chịu trách nhiệm đúng không?** Có làm lộ trạng thái, thêm phụ thuộc vòng, tạo tác dụng phụ bất ngờ?
4. **Thay đổi có an toàn trong bối cảnh hệ thống không?** Quyền truy cập, đồng thời, giao dịch, hiệu năng, tương thích và khả năng phục hồi?
5. **Người khác có tiếp tục thay đổi mã được không?** Tên gọi, cấu trúc, tài liệu và test có đủ rõ?
6. **Bằng chứng đi kèm có đúng phạm vi không?** Test, kết quả phân tích và dữ liệu vận hành hỗ trợ kết luận nào, còn điều gì chưa được kiểm tra?

Review **không phải** việc đếm lỗi nhỏ để chứng minh người review giỏi hơn tác giả. Nó cũng không phải hành động “đọc rồi phê duyệt” chỉ vì người viết đã chạy test. Mục tiêu là **giảm rủi ro của thay đổi và cải thiện chất lượng quyết định kỹ thuật**.

### Mã được duyệt chưa chắc mã đã đúng

Một bản thay đổi có thể được approve dù vẫn có lỗi. Đó là lý do cần phân biệt:

| Khái niệm | Ý nghĩa | Không nên suy diễn |
| --- | --- | --- |
| **Review completed** | Những reviewer được chỉ định đã thực hiện hoạt động rà soát theo quy trình | Mọi yêu cầu và mọi đường chạy đã được xác minh |
| **Review approved** | Trong phạm vi hiểu biết và bằng chứng hiện có, reviewer chấp nhận thay đổi hoặc rủi ro theo quyền của mình | Không còn lỗi tiềm ẩn hoặc không cần kiểm thử |
| **Tests passed** | Những test đã chạy không phát hiện sai khác so với expected của chúng | Expected chắc chắn đúng, hoặc mọi tình huống đều được bao phủ |
| **Static checks passed** | Những quy tắc/cấu hình được bật không báo vấn đề chặn | Không còn bug logic hoặc lỗ hổng |
| **Production healthy** | Các chỉ báo vận hành đang được quan sát trong một khoảng thời gian | Hành vi chưa sử dụng hoặc chưa đo đều an toàn |

Một phê duyệt nên là **quyết định có phạm vi và trách nhiệm**, không phải lời bảo đảm tuyệt đối.

## 2. Những mục tiêu chính của rà soát mã

### 2.1. Kiểm tra hành vi so với yêu cầu

Người review có thể đối chiếu điều kiện trong mã với **hợp đồng nghiệp vụ đã xác nhận**:

- Đơn hàng từ **500.000 VND trở lên** được miễn phí, mã có dùng `>=` hay nhầm thành `>`?
- Dịch vụ yêu cầu quyền xem một báo cáo, mã có kiểm tra quyền **theo tài nguyên** hay chỉ biết người dùng đã đăng nhập?
- Một thao tác không thành công có để lại trạng thái bị sửa một phần không?
- Một lệnh thanh toán bị gửi lại sau timeout có tạo giao dịch trùng không?

Những câu hỏi này cần **bối cảnh yêu cầu**. Chỉ nhìn vào một phép so sánh `>`, không thể biết nó sai nếu không biết quy tắc “từ ... trở lên” hoặc “lớn hơn ...” đã được xác nhận.

### 2.2. Xem xét thiết kế và ranh giới trách nhiệm

Review là nơi con người có thể đánh giá:

- Lớp có đang ôm cả logic nghiệp vụ, HTTP, database và logging không?
- Dữ liệu mutable có bị trả trực tiếp ra ngoài làm phá vỡ bất biến?
- Có phụ thuộc ẩn vào đồng hồ, biến toàn cục hoặc trạng thái chia sẻ?
- Tên phương thức có che giấu tác dụng phụ, ví dụ `checkBalance()` nhưng lại ghi sổ?
- Thay đổi có thêm trừu tượng không cần thiết hay làm một quy tắc phải được sửa ở nhiều chỗ?
- Nếu yêu cầu thay đổi tháng sau, ranh giới nào sẽ chịu trách nhiệm?

Các câu hỏi này khó được quyết định chỉ bằng độ dài phương thức hay điểm complexity. Một bộ phân tích có thể chỉ ra **vùng cần xem xét**, nhưng người review phải hiểu **ý nghĩa và lý do thay đổi**.

### 2.3. Xem rủi ro bảo mật, tính nhất quán và vận hành

Con người có thể đặt câu hỏi về **giả định tin cậy và đường dữ liệu**: giá trị từ người dùng có thể đến SQL không, principal đã được xác thực chưa, có bỏ qua kiểm tra tenant khi tải bản ghi không, dữ liệu bí mật có rơi vào log không?

Với hệ thống nhiều yêu cầu đồng thời, review cần xét các thao tác **đọc rồi ghi**, thứ tự khóa, idempotency, retry và phạm vi transaction. Với xử lý tệp hoặc mạng, cần xem cách đóng tài nguyên, timeout, giới hạn và khôi phục.

Review không tự thay thế **threat modeling, kiểm thử race, integration test hoặc đánh giá tải**. Nó giúp **chỉ ra câu hỏi quan trọng** để lựa chọn loại bằng chứng phù hợp.

### 2.4. Tăng khả năng hiểu, bảo trì và chia sẻ tri thức

Code review còn giúp tác giả và reviewer đồng thuận về:

- Tên và kiểu dữ liệu diễn đạt mô hình bài toán.
- Quy ước ngoại lệ, null, tài nguyên và log.
- Vị trí hợp lý để đặt quy tắc, tài liệu hợp đồng và test.
- Lý do của một quyết định không hiển nhiên, đặc biệt khi liên quan tới hệ thống cũ.
- Những giới hạn và rủi ro mà người bảo trì sau này cần biết.

Một nhận xét có giải thích cơ chế giúp **chuyển giao hiểu biết**, khác với nhận xét “sửa theo ý tôi” mà không nêu tiêu chí.

## 3. Review cần những đầu vào nào?

Không nên bắt reviewer **đoán ý định** từ tên ticket hoặc vài dòng diff. Một pull request dễ rà soát thường cung cấp:

| Đầu vào | Vì sao hữu ích | Ví dụ |
| --- | --- | --- |
| **Mục tiêu thay đổi** | Biết hành vi nào cần có hoặc cần giữ | “Không cho đặt số chỗ lớn hơn sức chứa còn lại” |
| **Quy tắc và giá trị biên** | Đánh giá điều kiện có đúng nghĩa không | “Đặt đúng số chỗ còn lại là hợp lệ” |
| **Phạm vi ảnh hưởng** | Hiểu những luồng gọi và dữ liệu dùng chung | Checkout, API đặt chỗ, job xử lý lại |
| **Bằng chứng kiểm thử** | Thấy tình huống đã chạy, kết quả và giới hạn | JUnit 5, test database, test đồng thời |
| **Kết quả công cụ tự động** | Đỡ tốn thời gian cho lỗi máy kiểm tra tốt hơn | Format, compile, SAST, dependency checks |
| **Rủi ro và kế hoạch triển khai** | Đánh giá tác dụng phụ ở môi trường thực | Migration, cờ tính năng, rollback |
| **Điểm cần reviewer tập trung** | Tránh bỏ qua phần khó trong diff lớn | “Hãy xem tính nguyên tử của bước trừ ghế” |

Thông tin này không nhất thiết phải ở một biểu mẫu dài. Một mô tả PR ngắn, liên kết yêu cầu đã xác nhận và kết quả kiểm chứng có thể đủ với thay đổi nhỏ. Với sửa đổi liên quan giao dịch, quyền truy cập hoặc dữ liệu bền vững, cần thêm ngữ cảnh tương xứng với rủi ro.

**Nếu thiếu yêu cầu quan trọng, reviewer nên nêu sự thiếu hụt**, thay vì giả định mã hiện tại chính là đặc tả cần đạt.

## 4. Ví dụ Java: một đoạn mã rất dễ đọc nhưng có rủi ro

Giả sử một sự kiện có số ghế còn lại. Hợp đồng **giả định cho bài học**:

- Ban đầu số ghế không âm.
- Mỗi yêu cầu giữ số ghế **nguyên dương**.
- Nếu đủ ghế, yêu cầu thành công và giảm đúng số ghế được giữ.
- Nếu không đủ, trả thất bại và không làm thay đổi số ghế.
- Nhiều yêu cầu có thể xảy ra đồng thời; tổng số ghế giữ thành công **không được vượt số ghế còn lại**.

Một triển khai ban đầu:

~~~java
public final class UnsafeSeatInventory {
    private int remainingSeats;

    public UnsafeSeatInventory(int initialSeats) {
        this.remainingSeats = initialSeats;
    }

    public boolean reserve(int requestedSeats) {
        if (remainingSeats < requestedSeats) {
            return false;
        }
        remainingSeats -= requestedSeats;
        return true;
    }

    public int remainingSeats() {
        return remainingSeats;
    }
}
~~~

Một reviewer chỉ nhìn đường thành công có thể nghĩ:

> “Kiểm tra đủ ghế, trừ số ghế rồi trả true — hợp lý.”

Nhưng ngay cả khi mã ngắn và tên biến rõ, **ít nhất ba câu hỏi** phải được đặt ra.

### 4.1. Có chặn đầu vào không hợp lệ?

Với `requestedSeats = -1`, điều kiện `remainingSeats < requestedSeats` thường là sai khi còn ghế, sau đó câu lệnh `remainingSeats -= -1` **làm tăng số ghế**. Constructor cũng cho phép số ghế ban đầu âm. Đây là lỗi có thể phát hiện bằng **đọc điều kiện có đối chiếu hợp đồng** và kiểm thử giá trị biên.

### 4.2. Đọc rồi cập nhật có phải một thao tác nguyên tử?

Giả sử chỉ còn một ghế và hai luồng cùng gọi `reserve(1)`. Một thứ tự xen kẽ có thể xảy ra:

~~~text
Trạng thái ban đầu: remainingSeats = 1

Luồng A: đọc remainingSeats = 1 -> điều kiện đủ ghế
Luồng B: đọc remainingSeats = 1 -> điều kiện đủ ghế
Luồng A: tính 1 - 1, ghi 0; trả true
Luồng B: tính 1 - 1, ghi 0; trả true

Kết quả: hai yêu cầu đều được xác nhận thành công,
         dù ban đầu chỉ có một ghế.
~~~

Đây là ví dụ **mất cập nhật / read–modify–write không nguyên tử** và truy cập `int` không được đồng bộ. Trong Java, hai luồng cùng đọc/ghi trường mutable mà không có giao thức đồng bộ còn có vấn đề về tính nhìn thấy (*visibility*) theo Java Memory Model. Giá trị cuối **không phải bằng chứng** rằng cả hai đặt chỗ hợp lệ; lỗi quan trọng là **có thể trả thành công cho nhiều yêu cầu hơn sức chứa**.

Test tuần tự gọi một lượt có thể hoàn toàn xanh. Một lượt review bằng mắt **có thể suy ra tồn tại rủi ro**, nhưng không chứng minh được mọi lịch chạy hay mọi triển khai dùng cơ sở dữ liệu thật đều thỏa mãn bất biến.

### 4.3. Phạm vi của trạng thái là gì?

Nếu ứng dụng có nhiều instance server, mỗi instance giữ một `UnsafeSeatInventory` riêng sẽ tạo ra nhiều “số ghế còn lại” không được điều phối. Sửa thành `synchronized` hoặc `AtomicInteger` trong một JVM chỉ giải quyết trạng thái trong **một đối tượng/bộ nhớ của tiến trình**, không tự điều phối nhiều server.

Review cần hỏi: **ai là nguồn dữ liệu có thẩm quyền về số ghế?** Nếu là database, điều kiện “đủ ghế rồi trừ” phải được bảo đảm tại **ranh giới giao dịch/lưu trữ phù hợp**, không chỉ tại lớp HTTP.

## 5. Thiết kế minh họa có hợp đồng rõ hơn

Đối với **một đối tượng in-memory dùng chung giữa các luồng**, Java 17 cung cấp `AtomicInteger` để thực hiện cập nhật theo phép **compare-and-set (CAS)**.

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public final class SeatInventory {
    private final AtomicInteger remainingSeats;

    public SeatInventory(int initialSeats) {
        if (initialSeats < 0) {
            throw new IllegalArgumentException(
                "initialSeats must not be negative"
            );
        }
        this.remainingSeats = new AtomicInteger(initialSeats);
    }

    public boolean tryReserve(int requestedSeats) {
        if (requestedSeats <= 0) {
            throw new IllegalArgumentException(
                "requestedSeats must be positive"
            );
        }

        while (true) {
            int current = remainingSeats.get();
            if (current < requestedSeats) {
                return false;
            }

            int updated = current - requestedSeats;
            if (remainingSeats.compareAndSet(current, updated)) {
                return true;
            }
            // Có luồng khác sửa giá trị: đọc lại và thử tiếp.
        }
    }

    public int remainingSeats() {
        return remainingSeats.get();
    }
}
~~~

**Những điều bản sửa này cải thiện trong phạm vi ví dụ:**

- Chặn số ghế ban đầu âm và số ghế yêu cầu không dương.
- Kiểm tra đủ ghế và giảm số ghế bằng vòng CAS: mỗi lần giữ thành công phải cập nhật dựa trên giá trị vẫn còn đúng tại điểm CAS.
- Các thao tác trên `AtomicInteger` cung cấp ngữ nghĩa đồng bộ phù hợp cho giá trị đếm này trong cùng đối tượng; không còn dùng một trường `int` mutable không đồng bộ.
- Phương thức tên `tryReserve` cho biết “không đủ” là một kết quả dự kiến thông qua `false`.

**Những điều bản sửa chưa giải quyết:**

- Không lưu ghế bền vững qua lần khởi động lại.
- Không bảo vệ sức chứa khi nhiều tiến trình/server có kho dữ liệu riêng.
- Không ghi bản ghi từng khách, chống đặt trùng hoặc xử lý hoàn tác khi bước sau thất bại.
- Không thực hiện authorization, idempotency hoặc bảo đảm transaction khi đặt chỗ có thanh toán.

Một reviewer có trách nhiệm không tuyên bố “đã an toàn đồng thời toàn hệ thống” chỉ từ việc thấy `AtomicInteger`. Cần định nghĩa **phạm vi và tầng sở hữu trạng thái**.

## 6. Kiểm thử bổ sung cho suy luận khi review

Trong ví dụ Java 17, JUnit 5 có thể xác minh **bất biến cục bộ** và thử nhiều lời gọi tranh chấp một ghế.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class SeatInventoryTest {

    @Test
    void rejectsInvalidCounts() {
        assertThrows(
            IllegalArgumentException.class,
            () -> new SeatInventory(-1)
        );

        SeatInventory inventory = new SeatInventory(2);
        assertThrows(
            IllegalArgumentException.class,
            () -> inventory.tryReserve(0)
        );
        assertThrows(
            IllegalArgumentException.class,
            () -> inventory.tryReserve(-1)
        );
        assertEquals(2, inventory.remainingSeats());
    }

    @Test
    void exactAvailabilityCanBeReserved() {
        SeatInventory inventory = new SeatInventory(2);

        assertTrue(inventory.tryReserve(2));
        assertEquals(0, inventory.remainingSeats());
        assertFalse(inventory.tryReserve(1));
        assertEquals(0, inventory.remainingSeats());
    }

    @Test
    void insufficientSeatsDoNotChangeState() {
        SeatInventory inventory = new SeatInventory(1);

        assertFalse(inventory.tryReserve(2));
        assertEquals(1, inventory.remainingSeats());
    }
}
~~~

Các test này kiểm tra **hợp đồng độc lập với cấu trúc**: giá trị âm bị từ chối, đúng sức chứa thì thành công, không đủ thì thất bại và không sửa trạng thái.

### Một thử nghiệm cạnh tranh có kiểm soát

Để hai tác vụ bắt đầu gần nhau mà không dùng `Thread.sleep()` tùy ý, có thể dùng `CountDownLatch`. Ví dụ sau giữ **một ghế** và cho **hai luồng** cùng yêu cầu một ghế:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

class SeatInventoryConcurrencyTest {

    @Test
    void onlyOneOfTwoConcurrentRequestsCanSucceed() throws Exception {
        SeatInventory inventory = new SeatInventory(1);
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);
        ExecutorService executor = Executors.newFixedThreadPool(2);

        Callable<Boolean> reserve = () -> {
            ready.countDown();
            start.await();
            return inventory.tryReserve(1);
        };

        try {
            Future<Boolean> first = executor.submit(reserve);
            Future<Boolean> second = executor.submit(reserve);

            assertTrue(ready.await(10, TimeUnit.SECONDS));
            start.countDown();

            int successCount = (first.get(10, TimeUnit.SECONDS) ? 1 : 0)
                + (second.get(10, TimeUnit.SECONDS) ? 1 : 0);

            assertEquals(1, successCount);
            assertEquals(0, inventory.remainingSeats());
        } finally {
            start.countDown();
            executor.shutdownNow();
        }
    }
}
~~~

Phép thử này giúp bắt một số sai sót và chứng minh kết quả trong **lịch chạy đã thực hiện**. Nhưng có ba giới hạn:

1. `CountDownLatch` giúp các luồng bắt đầu cùng đợt, **không buộc chúng xen kẽ tại từng câu lệnh**. Một test cạnh tranh đạt không chứng minh mọi interleaving đều đúng.
2. Timeout 10 giây là **giới hạn chống treo**, không phải cam kết mọi máy CI sẽ luôn lập lịch xong đúng thời gian. Nếu test chập chờn, cần điều tra tải và giao thức đồng bộ thay vì tăng timeout vô hạn.
3. Test dùng **cùng đối tượng trong một JVM**. Nó không kiểm tra nhiều instance, transaction database hoặc các bước đặt chỗ/thu tiền nằm ngoài `SeatInventory`.

**Đọc mã và test bổ sung cho nhau:** review có thể nhận ra lý do CAS cần thiết; test xác minh một số kết quả được dự đoán; kiểm chứng rộng hơn phải xem cơ chế lưu trữ và kiến trúc thật.

## 7. Với database, review phải kiểm tra ranh giới khác

Giả sử số ghế còn lại nằm trong database, hai server đều phục vụ đặt chỗ. Một giải pháp có thể là **cập nhật có điều kiện tại database**, ví dụ câu SQL minh họa:

~~~sql
UPDATE event_inventory
SET remaining_seats = remaining_seats - ?
WHERE event_id = ?
  AND remaining_seats >= ?;
~~~

Nếu database và giao dịch cung cấp tính nguyên tử phù hợp, code có thể kiểm tra **số hàng được cập nhật** để xác định có giữ được ghế hay không. Tuy nhiên, đây chưa phải thiết kế hoàn chỉnh:

- Phải truyền cùng `requestedSeats` hợp lệ ở tham số thứ nhất và thứ ba.
- Phải phân biệt yêu cầu **không đủ ghế** với sự kiện **không tồn tại** nếu hợp đồng yêu cầu.
- Cần xử lý transaction khi lưu đặt chỗ, cập nhật ghế và phát sự kiện nghiệp vụ.
- Phải quyết định điều gì xảy ra khi request được gửi lại sau timeout.
- Phải kiểm tra quyền đặt chỗ, giới hạn theo người dùng và dữ liệu nhiều tenant nếu có.
- Cần integration test trên **loại database, isolation level và mô hình triển khai** phù hợp.

Chỉ nhìn cú pháp SQL hoặc review service không đủ chứng minh tính nguyên tử trong toàn bộ hệ thống. Review tốt phải chỉ ra **các giả định cần kiểm tra với adapter thực tế**.

## 8. Giới hạn của việc đọc mã bằng mắt

### 8.1. Người review không có đủ mọi đường thực thi trong đầu

Các chương trình có nhánh, vòng lặp, trạng thái, callback, exceptions và nhiều tác vụ bất đồng bộ. Số tổ hợp có thể lớn nhanh. Ngay cả một reviewer rất giỏi cũng khó mô phỏng toàn bộ luồng thực thi chỉ bằng cách đọc diff.

Ví dụ, nếu có 8 điều kiện Boolean độc lập về mặt mô hình, có thể có **2⁸ = 256 tổ hợp đầu vào** trước khi xét thời gian, dữ liệu ngoài hoặc đồng thời. Con số này không có nghĩa mọi tổ hợp đều khả thi hay cần 256 test, nhưng cho thấy giới hạn của việc chỉ “đọc một lượt rồi thấy ổn”.

### 8.2. Diff-only review dễ mất ngữ cảnh

Một dòng thay đổi:

~~~java
return inventory.tryReserve(requestedSeats);
~~~

trông đơn giản. Nhưng reviewer cần biết `inventory` là đối tượng chia sẻ trong một JVM hay snapshot riêng cho mỗi request; số ghế có được cập nhật ở database khác không; ai tạo và giữ inventory; rollback khi lỗi xảy ra như thế nào.

Chỉ xem **những dòng thêm/xóa** có thể bỏ lỡ tác động tới caller, class sở hữu trạng thái, contract cũ, dữ liệu có phiên bản hoặc luồng nghiệp vụ không đi qua phương thức này.

### 8.3. Độ mệt mỏi và thiên kiến làm giảm chất lượng review

Review một PR quá lớn, nhiều refactor không liên quan hoặc chỉ toàn thay đổi định dạng khiến reviewer phải giữ quá nhiều thông tin trong đầu. Họ có thể:

- Bỏ qua đường lỗi vì tập trung vào đường thành công.
- Tin rằng mã đúng vì tác giả có kinh nghiệm hoặc CI xanh.
- Chỉ tìm những vấn đề quen thuộc và bỏ qua mô hình nghiệp vụ mới.
- Đưa ra nhận xét chủ quan về style thay vì xác minh tác động.
- Bị cuốn vào thảo luận nhỏ trong khi thiếu kiểm tra bất biến quan trọng.

Giảm kích thước và phạm vi PR, mô tả rủi ro, dùng công cụ tự động cho việc lặp và phân chia review theo chuyên môn giúp giảm các hạn chế này, **nhưng không thể loại bỏ hoàn toàn sai sót con người**.

### 8.4. Mã nguồn không chứa toàn bộ sự thật về hệ thống

Khi chỉ đọc Java, người review có thể không thấy:

- Cấu hình runtime và quyền database/object storage.
- Dữ liệu thực tế, phân bố kích thước và tần suất truy cập.
- Cách gateway, queue hoặc đối tác xử lý timeout và retry.
- Hiệu năng dưới tải, contention và hành vi GC.
- Người dùng hoặc tenant nào có quyền thực hiện thao tác.
- Phạm vi các bản phát hành cũ còn được hỗ trợ.

Vì vậy một khẳng định như “đã review toàn bộ file nên chắc không có rủi ro hiệu năng/bảo mật” là **quá mức so với bằng chứng**.

## 9. Phân chia việc cho người và công cụ

Để review có thời gian cho những quyết định cần ngữ cảnh, nên tự động hóa những kiểm tra mà máy làm ổn định hơn:

| Hoạt động | Điều thường làm tốt | Giới hạn không nên bỏ qua |
| --- | --- | --- |
| **Formatter / lint** | Format, import dư, quy ước cú pháp | Không xác nhận hợp đồng nghiệp vụ |
| **Compiler / type checker** | Lỗi kiểu và một số vấn đề cấu trúc | Không chứng minh logic đúng hay ranh giới quyền hợp lệ |
| **Static analysis / SAST** | Mẫu nguy hiểm, luồng dữ liệu, lỗi null tiềm tàng | False positive/negative, không hiểu mọi chính sách |
| **Dependency scan / SCA** | Thư viện, phiên bản và advisory đã biết | Phải đánh giá mức ảnh hưởng theo cấu hình và đường chạy |
| **Unit test** | Quy tắc và giá trị biên đã được đặc tả | Không kiểm tra mọi trạng thái hoặc adapter thật |
| **Integration / contract test** | Hợp đồng giữa thành phần, DB, HTTP, queue | Môi trường test có thể khác production |
| **Load / concurrency test** | Một số tình huống áp lực, cạnh tranh và hiệu năng | Không chứng minh mọi interleaving hay mức tải tương lai |
| **Code/design review** | Ý định, ranh giới, trách nhiệm, rủi ro theo bối cảnh | Phụ thuộc ngữ cảnh và năng lực người review; không thực thi mã |
| **Monitoring / audit** | Dấu hiệu sai lệch và tác động sau triển khai | Không thay thế phòng ngừa và test trước phát hành |

**Không có một công cụ nào thay thế tất cả các cột còn lại.** Mục tiêu là thu thập đủ loại bằng chứng cho **những rủi ro quan trọng của thay đổi**, không phải bật mọi công cụ ở mức tối đa trên mọi PR.

Ví dụ, với một thay đổi chỉ sửa tên biến trong hàm thuần, review và test có thể đủ. Với luồng chuyển tiền có retry và concurrency, cần kết hợp review hợp đồng, test trường hợp phản hồi mất, database/đối tác và chiến lược idempotency.

## 10. Một review comment tốt có cấu trúc gì?

Một nhận xét hữu ích thường chỉ rõ **vị trí → quan sát → cơ chế rủi ro → hệ quả → câu hỏi hoặc hành động/kiểm chứng**.

### Nhận xét thiếu bằng chứng

> “Code này không an toàn, sửa đi.”

### Nhận xét có thể hành động

> “Ở `reserve()`, điều kiện kiểm tra đủ ghế và bước trừ `remainingSeats` là hai thao tác tách rời trên trạng thái mutable. Nếu hai request cùng đọc còn một ghế, cả hai có thể trả thành công. Sức chứa có được quản lý qua nhiều server không? Nếu có, cần bảo đảm cập nhật có điều kiện ở tầng lưu trữ và bổ sung integration test cho hai yêu cầu tranh ghế cuối.”

Nhận xét thứ hai:

- Chỉ vào **đường mã và giả định cụ thể**.
- Giải thích **một kịch bản thất bại** có thể kiểm chứng.
- Không tự khẳng định “đã có lỗi production” khi chưa có bằng chứng.
- Tách giải pháp cho **in-memory** và **nhiều server**.
- Đề xuất bước tiếp theo có người thực hiện được.

Với lỗi nhỏ, một nhận xét ngắn là đủ:

> “`requestedSeats` cần lớn hơn 0 theo hợp đồng; hiện tại truyền `-1` làm tăng tồn ghế. Hãy từ chối giá trị không dương và thêm test biên.”

Không phải mọi góp ý đều phải dài. Điều quan trọng là **phân biệt điều đã quan sát, điều đang suy luận và điều cần xác minh**.

## 11. Phân loại mức quan trọng của góp ý

Một nhóm có thể thống nhất nhãn đơn giản:

| Loại | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Blocking / correctness** | Vi phạm hợp đồng hoặc rủi ro nghiêm trọng cần xử lý trước merge theo chính sách | Số ghế âm, bỏ kiểm tra quyền báo cáo, thay đổi giao thức không tương thích |
| **Question / needs context** | Chưa đủ thông tin để đánh giá đúng sai | “Đây là trạng thái trong một JVM hay đã có transaction DB?” |
| **Suggestion / maintainability** | Cải thiện rõ ràng nhưng có thể cân nhắc thời điểm | Đổi tên mơ hồ, giảm lặp chính sách |
| **Nit / style** | Chi tiết nhỏ không ảnh hưởng đáng kể tới hợp đồng | Định dạng mà formatter chưa hỗ trợ |
| **Praise / learning** | Ghi nhận quyết định có giá trị và giúp người khác hiểu | “Test đúng thời điểm hết hạn đã bảo vệ giá trị biên quan trọng” |

Nhãn và quyền chặn merge phải theo **quy trình nhóm**, không theo cảm tính mỗi người. Một comment về style không nên được giả định có cùng mức ưu tiên với lỗi mất dữ liệu. Ngược lại, các lỗi mang rủi ro cao cần có người chịu trách nhiệm và quyết định rõ ràng.

**Mức độ chắc chắn** cũng khác **mức tác động**: có thể nghi ngờ một race condition có tác động lớn nhưng chưa đủ thông tin về phạm vi triển khai. Khi đó nên yêu cầu thêm bằng chứng, không vội gắn nhãn đã xác nhận hoặc bỏ qua vì chưa tái hiện được.

## 12. Trình tự rà soát theo rủi ro

Một quy trình review có thể chia thành những bước nhỏ:

1. **Đọc mục tiêu và hợp đồng.** Xác định người dùng, hành vi thay đổi, tiền điều kiện, bất biến, giá trị biên và trường hợp không được phép xảy ra.
2. **Xác định phạm vi.** Nhìn qua cấu trúc thay đổi, những API bị ảnh hưởng, dữ liệu được lưu, caller, đường lỗi, migration và tương tác với hệ thống ngoài.
3. **Ưu tiên rủi ro cao.** Với thanh toán, quyền truy cập, tính nhất quán dữ liệu, đồng thời, tài nguyên và tương thích, đặt câu hỏi trước khi tranh luận format.
4. **Theo luồng dữ liệu và trạng thái.** Input đến từ đâu, quyền được xác thực ở đâu, trạng thái đổi lúc nào, có bước nào đọc–ghi tách rời, retry hoặc tác dụng phụ bị che?
5. **Đọc test như bằng chứng.** Expected được lấy từ yêu cầu hay chỉ sao chép thuật toán? Có ca biên, đường từ chối, lỗi I/O và trường hợp đồng thời liên quan?
6. **Xem công cụ tự động.** Kết quả compile, test, formatter, SAST/SCA và mức bao phủ được công bố; đánh giá cảnh báo theo ngữ cảnh, không chỉ nhìn số.
7. **Viết góp ý có mục đích.** Đưa kịch bản, tác động và hướng xác minh. Nêu rõ điều gì chặn merge, điều gì là câu hỏi, điều gì chỉ là đề xuất.
8. **Kiểm tra thay đổi sau phản hồi.** Reviewer cần xem giải pháp mới có giữ hợp đồng và giải quyết đúng rủi ro đã nêu không; không chỉ kiểm tra comment đã được đánh dấu “resolved”.
9. **Ghi giới hạn hoặc rủi ro còn lại.** Nếu chưa thể kiểm chứng một giả định vì thiếu môi trường hoặc thông tin, công bố rõ và quyết định theo mức rủi ro.

Đối với PR nhỏ, các bước này có thể diễn ra rất nhanh; không cần tạo một quy trình nặng nề. Đối với thay đổi có nguy cơ mất tiền/dữ liệu hoặc mở rộng quyền truy cập, cần thêm thời gian và bằng chứng phù hợp.

### Giảm tải cho reviewer bằng cách chuẩn bị PR

Tác giả có thể giúp review hiệu quả hơn bằng cách:

- Tách **refactor không đổi hành vi** và **thay đổi nghiệp vụ** thành các phần có thể nhận diện.
- Tránh trộn formatter toàn repository với thay đổi logic nhỏ.
- Cung cấp test cho giá trị biên và đường lỗi có tác động lớn.
- Nêu lý do chọn một ranh giới thay vì chỉ trình bày tên lớp mới.
- Đánh dấu những phần mã dễ bị hiểu sai hoặc cần chuyên gia về database/security.
- Không yêu cầu reviewer phê duyệt trong khi những kiểm tra bắt buộc còn chưa chạy hoặc dữ liệu kiểm chứng chưa có.

Đây không phải nghi thức để tăng số lượng checkbox; mục tiêu là **tăng thời gian reviewer dành cho suy luận quan trọng**.

## 13. Khi nào review chỉ bằng mắt là chưa đủ?

| Loại thay đổi | Câu hỏi review có thể nêu | Bằng chứng bổ sung thường cần |
| --- | --- | --- |
| Logic giá trị biên | `>=` hay `>` khớp chính sách? | Unit test đúng ranh giới và xung quanh |
| Trạng thái dùng chung | Có đọc–ghi không nguyên tử? | Thiết kế đồng bộ và concurrency/integration test |
| Truy vấn dữ liệu | Có kiểm tra quyền/tenant theo bản ghi? | Integration test trên dữ liệu nhiều chủ thể |
| Retry thanh toán | Phản hồi mất nhưng giao dịch đã thành công thì sao? | Mô phỏng timeout sau commit, idempotency test |
| Thay schema DB | Dữ liệu cũ và ứng dụng cũ có còn dùng được? | Migration test và kế hoạch rollback |
| Tối ưu hiệu năng | Có giảm thời gian xử lý dưới tải thật không? | Benchmark, profiling và đo trên tải đại diện |
| Thêm cache | Dữ liệu cũ/thu hồi quyền được xử lý thế nào? | Test invalidation, TTL và điều kiện đồng thời |
| Thay dependency | Phiên bản mới có làm đổi hợp đồng hoặc bảo mật? | SCA, compatibility test, đánh giá cấu hình |
| Đổi log | Có đủ ngữ cảnh mà không lộ dữ liệu nhạy cảm? | Review policy logging và test/quan sát log |

**Một kết quả kiểm thử đạt cũng có phạm vi**. Ví dụ test race đạt trong 100 lần chạy không chứng minh đã thử hết mọi lịch luồng; benchmark nhanh hơn trên máy cá nhân không tự bảo đảm nhanh hơn ở production; một test authorization với một tài khoản không chứng minh không có lỗi đa tenant.

## 14. Bài tập tình huống

Nhóm triển khai endpoint tải báo cáo:

~~~java
public byte[] downloadReport(String reportId, String requesterId) {
    // Người gọi đã đăng nhập nên có thể tải báo cáo.
    Report report = repository.findById(reportId)
        .orElseThrow(ReportNotFoundException::new);
    return storage.read(report.storageKey());
}
~~~

Trong tình huống giả định này, chính sách nghiệp vụ quy định người dùng chỉ được xem báo cáo **thuộc quyền của mình**. `requesterId` đến từ tham số của HTTP request do client cung cấp, còn lớp xác thực đã có khả năng tạo principal đáng tin cậy ở một vị trí khác.

Đoạn mã trên minh họa một **phương thức đặt trong class đã có repository và storage**, các kiểu phụ thuộc cần định nghĩa riêng trong hệ thống thật.

**Câu hỏi A.** Chỉ ra ít nhất ba vấn đề reviewer nên nêu, phân biệt lỗi đã thấy rõ và điều còn cần hỏi thêm.

**Câu hỏi B.** Một unit test dùng fake repository luôn trả `Optional.empty()` cho người không có quyền đã đủ chứng minh endpoint an toàn chưa?

**Câu hỏi C.** Nếu formatter, compiler và test đường thành công đều xanh, kết quả đó hỗ trợ kết luận nào và chưa hỗ trợ kết luận nào?

**Câu hỏi D.** Hãy viết một review comment ngắn có cơ chế rủi ro, tác động và hướng kiểm chứng.

**Câu hỏi E.** Nếu tác giả sửa bằng cách truyền `requesterId` vào `repository.findOwnedById(...)` nhưng vẫn lấy giá trị đó từ JSON/query, vấn đề đã được giải quyết chưa?

### Gợi ý đáp án

**A.** Phương thức không dùng `requesterId` để ràng buộc kết quả; truy vấn chỉ theo `reportId` nên có nguy cơ truy cập trái quyền. Bình luận “đã đăng nhập” nhầm **xác thực danh tính** với **quyền trên từng tài nguyên**. Thêm vào đó, `requesterId` là dữ liệu do client kiểm soát nên không được dùng như principal đáng tin cậy. Cần hỏi thêm các đường tải khác và quyền truy cập object storage để đánh giá phạm vi hệ thống.

**B.** Chưa. Fake có thể thực thi đúng một quy tắc mà adapter database thật lại bỏ sót. Cần integration test với nhiều chủ sở hữu/tenant trên repository thật, cùng HTTP test xác minh principal phải xuất phát từ quá trình xác thực và việc bị từ chối không đọc nội dung trái quyền.

**C.** Kết quả cho biết mã biên dịch được và những quy tắc/test đã bật không phát hiện lỗi trong phạm vi chúng kiểm tra. Chúng không chứng minh kiểm soát quyền theo đối tượng, vì đường thành công không kiểm tra người A cố tải báo cáo B.

**D.** Ví dụ: “`downloadReport` lấy báo cáo theo ID mà không ràng buộc với chủ sở hữu. Người dùng A có thể thay `reportId` để yêu cầu báo cáo của B. Cần dùng principal đã xác thực và kiểm tra quyền theo tài nguyên trước khi đọc storage; bổ sung test HTTP/repository cho hai người dùng khác nhau và xác minh không đọc nội dung khi bị từ chối.”

**E.** Chưa. Tham số do người dùng gửi có thể bị giả mạo. Phải truyền **principal đã được xác minh** từ lớp xác thực, và repository thực thi đúng điều kiện owner/tenant. Tên `findOwnedById` không tự bảo đảm implementation đúng; cần kiểm chứng tại ranh giới dữ liệu thật.

## 15. Checklist cuối khi thực hiện hoặc nhận code review

| Khía cạnh | Câu hỏi thực hành |
| --- | --- |
| **Yêu cầu** | Có biết điều phải giữ, điều phải đổi và nguồn xác nhận không? |
| **Đầu vào** | Có validation và hợp đồng `null`/giá trị biên rõ không? |
| **Hành vi** | Đường thành công, thất bại, ngoại lệ và tác dụng phụ có hợp lý không? |
| **Đồng thời** | Những trạng thái nào được chia sẻ, có bước đọc–ghi cần nguyên tử không? |
| **Bảo mật** | Danh tính, quyền, dữ liệu không tin cậy và bí mật trong log được bảo vệ tại đâu? |
| **Thiết kế** | Trách nhiệm, phụ thuộc và quyền sở hữu dữ liệu/tài nguyên có rõ không? |
| **Tương thích** | Client cũ, schema, cấu hình và dữ liệu lịch sử có bị ảnh hưởng không? |
| **Kiểm thử** | Expected độc lập với implementation? Có test biên, đường lỗi và mức tích hợp phù hợp? |
| **Công cụ** | Formatter, compiler, analyzer và dependency checks đã chạy trong phạm vi nào? |
| **Triển khai** | Có giám sát, kế hoạch rollback hoặc xử lý sự cố khi rủi ro yêu cầu không? |
| **Nhận xét** | Comment có cơ chế, tác động và hành động rõ, phân biệt bắt buộc với gợi ý không? |
| **Kết luận** | Những điều gì đã xác minh, còn giả định hoặc rủi ro nào chưa được kiểm chứng? |

## Ghi nhớ

**Rà soát mã nhằm nâng chất lượng quyết định thay đổi**, bằng cách kiểm tra hợp đồng, thiết kế, rủi ro, khả năng hiểu và chia sẻ tri thức. Giá trị lớn nhất của reviewer không phải làm việc thay formatter hay đếm số dòng, mà là **đặt đúng câu hỏi dựa trên ngữ cảnh** và chỉ ra điều cần chứng minh.

**Đọc thủ công có giới hạn**: diff có thể thiếu bối cảnh; con người không thể mô phỏng mọi đường đi, thứ tự luồng hay môi trường thực tế; reviewer có thể bị ảnh hưởng bởi độ lớn PR, mệt mỏi và thiên kiến. Vì vậy, một review có trách nhiệm phải kết hợp **yêu cầu đã xác nhận, kiểm thử có assertion, phân tích tự động, kiểm chứng tích hợp và quan sát vận hành** theo mức rủi ro.

Một lời phê duyệt tốt không có nghĩa “không còn lỗi”, mà là: **những hành vi và rủi ro quan trọng đã được xem xét trong phạm vi rõ ràng, các bằng chứng cần thiết đã được kiểm tra, và điều chưa chắc chắn được nêu ra để xử lý đúng trách nhiệm**.
