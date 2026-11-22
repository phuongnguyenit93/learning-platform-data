# Vòng lặp compare-and-set và việc tính lại khi tranh chấp

## 1. Từ một phép cập nhật đến một đề xuất có điều kiện

Giả sử hai luồng cùng tăng một bộ đếm đang có giá trị `0`. Cả hai có thể cùng đọc được `0` và cùng tính ra `1`. Nếu dùng riêng `get()` rồi `set(1)`, mỗi lời gọi là nguyên tử nhưng chuỗi đọc–tính–ghi không phải một thao tác nguyên tử: kết quả có thể chỉ tăng một lần.

So sánh và đặt (compare-and-set, CAS) giải quyết vấn đề bằng một đề xuất có điều kiện:

```java
boolean committed = counter.compareAndSet(expected, next);
```

Với `AtomicInteger`, thao tác chỉ ghi `next` khi giá trị hiện tại bằng `expected`. Việc kiểm tra điều kiện và ghi diễn ra như một thao tác nguyên tử. Kết quả `true` nghĩa là đề xuất đã được chấp nhận; `false` nghĩa là lần này không ghi gì.

Điều cần ghi nhớ là: **giá trị đã tính chỉ là một đề xuất dựa trên lần đọc trước; nó chưa phải kết quả đã được ghi nhận**. Khi một luồng khác cập nhật trước, đề xuất có thể mất hiệu lực. Vòng lặp CAS cho phép luồng đọc lại trạng thái, tính lại đề xuất và thử tiếp.

Các lớp nguyên tử được giới thiệu từ Java 5 và vẫn được dùng trong Java hiện đại. Những ví dụ dưới đây chạy trên Java 17 trở lên; bài không cần API nội bộ hay phương thức đã bị đánh dấu ngừng khuyến nghị.

## 2. Cấu trúc đúng của vòng lặp

Đây là phương thức minh họa, đặt trong một lớp có sẵn:

```java
import java.util.concurrent.atomic.AtomicInteger;

static int incrementWithCas(AtomicInteger counter) {
    for (;;) {
        int observed = counter.get();
        int next = Math.addExact(observed, 1);
        if (counter.compareAndSet(observed, next)) {
            return next;
        }
    }
}
```

Mỗi lượt gồm bốn việc:

1. Đọc một giá trị quan sát được bằng `get()`.
2. Tính đề xuất mới từ chính giá trị vừa đọc.
3. Thử ghi bằng `compareAndSet(observed, next)`.
4. Nếu thất bại, bắt đầu lượt mới bằng một lần đọc mới.

`Math.addExact` được dùng để bài không âm thầm quay từ `Integer.MAX_VALUE` sang số âm. Nếu xảy ra tràn số, phương thức ném `ArithmeticException` trước CAS; không ghi đề xuất của lượt đó. Đây là lựa chọn quy tắc số học, không phải yêu cầu bắt buộc của CAS.

Có thể viết cùng ý tưởng với biến nằm ngoài vòng lặp:

```java
int observed = counter.get();
for (;;) {
    int next = Math.addExact(observed, 1);
    if (counter.compareAndSet(observed, next)) {
        return next;
    }
    observed = counter.get();
}
```

Hai cách đều đúng vì sau thất bại, lần thử tiếp theo không tiếp tục dựa vào ảnh chụp cũ.

Để tăng một bộ đếm thông thường, nên dùng `incrementAndGet()` hoặc `getAndIncrement()` cho rõ ý định. Vòng lặp tự viết có ích khi cần hiểu cơ chế hoặc thực hiện phép chuyển trạng thái có điều kiện riêng.

## 3. Vì sao phải tính lại, không chỉ thử ghi lại?

Xét lịch thực thi sau, với trạng thái ban đầu `10`:

| Thời điểm | Luồng A | Luồng B | Giá trị chung |
| --- | --- | --- | --- |
| 1 | Đọc `10`, tính `11` | | 10 |
| 2 | | Đọc `10`, tính `11` | 10 |
| 3 | | CAS `10 → 11` thành công | 11 |
| 4 | CAS `10 → 11` thất bại | | 11 |
| 5 | Đọc lại `11`, tính `12` | | 11 |
| 6 | CAS `11 → 12` thành công | | 12 |

A thất bại vì điều kiện `current == 10` không còn đúng ở thời điểm CAS. Đây là tranh chấp bình thường, không phải mất bản cập nhật đã thành công.

Có hai lỗi thường gặp.

### Giữ nguyên giá trị kỳ vọng

```java
// SAI: observed không được cập nhật.
int observed = counter.get();
int next = observed + 1;
while (!counter.compareAndSet(observed, next)) {
    // Không đọc lại.
}
```

Nếu luồng khác đã đổi giá trị và nó không quay về `observed`, vòng lặp có thể chạy mãi. Thử nhiều lần không làm ảnh chụp cũ trở nên mới.

### Đọc lại kỳ vọng nhưng giữ đề xuất cũ

```java
// SAI: next vẫn được tính từ lần đọc đầu tiên.
int observed = counter.get();
int next = observed + 1;
while (!counter.compareAndSet(observed, next)) {
    observed = counter.get();
}
```

Ví dụ ban đầu `10`, luồng khác tăng lên `11`: lần sau có thể CAS `11 → 11` thành công. Phương thức tưởng đã tăng nhưng thực tế bỏ mất lần tăng của mình.

Quy tắc đúng là giữ một cặp nhất quán: **`next` phải được tính từ đúng `observed` dùng trong CAS của lượt đó**. Nếu công thức phụ thuộc vào trạng thái vừa đọc, thay `observed` đồng nghĩa phải xem xét và tính lại công thức.

## 4. Ví dụ chạy được: chắc chắn có một lần thất bại

Chỉ khởi chạy nhiều luồng không bảo đảm lần chạy nào cũng xuất hiện thất bại CAS. Chương trình sau dùng hai chốt chờ để cả hai luồng cùng giữ ảnh chụp `0` trước lần thử đầu. Vì vậy có đúng hai cập nhật thành công và đúng một lần thất bại.

Lưu thành `CasRetryDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class CasRetryDemo {
    private static void increment(
            AtomicInteger counter,
            CountDownLatch ready,
            CountDownLatch start,
            int[] calculations,
            int[] failures,
            int worker) {
        int observed = counter.get();
        ready.countDown();
        try {
            start.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted before CAS", e);
        }

        for (;;) {
            calculations[worker]++;
            int next = Math.addExact(observed, 1);
            if (counter.compareAndSet(observed, next)) {
                return;
            }
            failures[worker]++;
            observed = counter.get();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        AtomicInteger counter = new AtomicInteger(0);
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);
        int[] calculations = new int[2];
        int[] failures = new int[2];

        Thread first = new Thread(
                () -> increment(counter, ready, start,
                        calculations, failures, 0));
        Thread second = new Thread(
                () -> increment(counter, ready, start,
                        calculations, failures, 1));

        first.start();
        second.start();
        ready.await();
        start.countDown();
        first.join();
        second.join();

        System.out.println("value=" + counter.get());
        System.out.println("calculations="
                + (calculations[0] + calculations[1]));
        System.out.println("failedCas=" + (failures[0] + failures[1]));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 CasRetryDemo.java
java CasRetryDemo
```

Stdout khi chạy bình thường, không bị ngắt:

```text
value=2
calculations=3
failedCas=1
```

Giải thích:

- Mỗi luồng đọc `0` trước khi báo `ready`. Luồng chính chỉ mở `start` sau khi nhận đủ hai tín hiệu.
- Một trong hai CAS đầu tiên thắng. Luồng còn lại vẫn kỳ vọng `0`, nên thất bại.
- Luồng thua đọc lại `1`, tính `2` rồi thành công vì luồng thắng đã kết thúc phương thức.
- Thứ tự luồng thắng không cố định, nhưng ba dòng tổng hợp trên không phụ thuộc thứ tự đó.
- Mỗi luồng chỉ ghi phần tử riêng của hai mảng thống kê. Luồng chính đọc sau `join()`; không có hai luồng cùng tăng một phần tử mảng.

Hai bộ đếm mảng chỉ là thiết bị quan sát trong thí nghiệm. Việc tính lại đã xảy ra ba lần trong khi trạng thái chung chỉ được cập nhật thành công hai lần. Trong mã nghiệp vụ, chính sự khác nhau này quyết định điều gì được phép đặt trong phần có thể chạy lại.

## 5. Phần tính lại phải an toàn khi thực thi nhiều lần

Hãy coi phần tạo đề xuất là một phép tính có thể bị bỏ đi. Nó nên ngắn, chỉ phụ thuộc vào dữ liệu phù hợp và không tạo tác dụng phụ nghiệp vụ.

Ví dụ nguy hiểm:

```java
// Mã minh họa SAI; chargeCard là thao tác bên ngoài.
for (;;) {
    int observed = balance.get();
    chargeCard(amount);
    int next = observed + amount;
    if (balance.compareAndSet(observed, next)) {
        break;
    }
}
```

Nếu CAS thất bại hai lần rồi mới thành công, thao tác thu tiền có thể đã chạy ba lần. CAS chỉ bảo vệ việc cập nhật `balance`; nó không hoàn tác lời gọi thu tiền.

Những việc không nên nằm trong phép tính có thể thử lại gồm gửi email, ghi hóa đơn, gọi dịch vụ thanh toán và sửa một đối tượng dùng chung khác. Ngay cả ghi log trong vòng lặp cũng có thể tạo nhiều dòng cho một cập nhật; nếu dùng để chẩn đoán, phải hiểu đó là log của từng lần thử.

Đưa tác dụng phụ ra sau CAS thành công tránh việc lặp nó do chính các lần CAS thất bại. Tuy nhiên, **điều đó không tạo giao dịch nguyên tử giữa bộ nhớ và hệ thống bên ngoài**: tiến trình có thể dừng sau khi CAS thành công nhưng trước khi gửi, hoặc yêu cầu bên ngoài có thể bị gửi lại sau lỗi mạng. Khi có yêu cầu nhất quán như vậy, cần cơ chế phù hợp, chẳng hạn giao dịch cơ sở dữ liệu và hộp thư giao dịch (transactional outbox), cùng khóa chống xử lý lặp ở phía nhận.

Nếu đầu vào như `amount` thuộc về một yêu cầu, thường nên cố định nó trước vòng lặp và kiểm tra hợp lệ một lần. Trạng thái dùng chung thì đọc lại mỗi lượt. Nếu phép tính còn đọc nhiều biến dùng chung độc lập, CAS trên một biến không chứng minh rằng các biến kia tạo thành cùng một ảnh chụp nhất quán.

## 6. Áp dụng cho cập nhật có điều kiện

Một tình huống thực tế là lấy một suất còn lại mà không cho số lượng âm. Đoạn sau là phương thức độc lập để đặt vào lớp có sẵn:

```java
import java.util.concurrent.atomic.AtomicInteger;

static boolean tryAcquire(AtomicInteger remaining) {
    for (;;) {
        int observed = remaining.get();
        if (observed <= 0) {
            return false;
        }
        int next = observed - 1;
        if (remaining.compareAndSet(observed, next)) {
            return true;
        }
    }
}
```

Giả sử còn một suất và hai luồng cùng đọc `1`. Một luồng CAS `1 → 0` thành công. Luồng còn lại thất bại, đọc lại `0` rồi trả `false`. Nó không trừ tiếp từ một kỳ vọng đã lỗi thời.

Điều kiện `observed <= 0` phải được đánh giá lại cùng với giá trị mới. Không đưa lần kiểm tra này ra ngoài vòng lặp rồi cho rằng nó vẫn đúng sau tranh chấp.

Để lập luận về tính đúng, xác định điểm tuyến tính hóa (linearization point): thời điểm một lời gọi có thể được xem như xảy ra tức thời.

- Khi trả `true`, đó là CAS thành công.
- Khi trả `false`, đó là lần đọc quan sát thấy không còn suất.

Một luồng khác có thể bổ sung suất ngay sau lần đọc dẫn đến `false`. Kết quả vẫn phù hợp với hợp đồng “thử lấy theo trạng thái quan sát được”, không phải cam kết rằng hệ thống sẽ tiếp tục hết suất khi phương thức trả về.

Giả định của ví dụ: trạng thái không âm ban đầu và mọi đường cập nhật đều giữ quy tắc đó. Một nơi khác gọi `remaining.set(-100)` thì phương thức này không thể bảo vệ toàn bộ hệ thống.

## 7. API cập nhật bằng hàm có cùng yêu cầu về việc thử lại

Trong Java hiện đại, có thể diễn đạt nhiều phép cập nhật ngắn gọn:

```java
int updated = counter.updateAndGet(
        current -> Math.addExact(current, 1));

int previous = counter.getAndUpdate(
        current -> Math.addExact(current, 1));
```

Đây là hai thao tác riêng, không phải hai cách lấy kết quả của cùng một lần cập nhật. `updateAndGet` trả giá trị sau cập nhật; `getAndUpdate` trả giá trị trước cập nhật.

Hàm cập nhật có thể được thực thi lại khi có tranh chấp. Vì vậy, không đặt tác dụng phụ trong lambda và không suy ra rằng số lần gọi lambda bằng số cập nhật thành công. Cũng không dựa vào số lần tính lại cụ thể bên trong một phiên bản JDK: hợp đồng API cho phép thử lại, còn chi tiết thực hiện có thể thay đổi.

Ví dụ không nên viết:

```java
// SAI: sendEmail có thể được gọi nhiều lần cho một lần cập nhật.
counter.updateAndGet(current -> {
    sendEmail();
    return current + 1;
});
```

`accumulateAndGet` và `getAndAccumulate` cũng đòi hỏi hàm tính toán an toàn khi bị thực thi lại. Với một phép cộng đơn giản không cần kiểm tra riêng, `addAndGet` hoặc `getAndAdd` thường thể hiện ý định trực tiếp hơn.

## 8. Phạm vi bảo đảm và giới hạn cần hiểu

### CAS thành công không khóa giá trị sau đó

Kết quả `true` chỉ xác nhận phép chuyển đã xảy ra tại thời điểm CAS. Một luồng khác có thể cập nhật tiếp trước khi phương thức của bạn trả về. Nếu cần trả kết quả do mình vừa ghi, trả biến `next`; gọi thêm `get()` có thể trả về giá trị của lần cập nhật sau.

`get()` của `AtomicInteger` có ngữ nghĩa đọc volatile; `compareAndSet` có ngữ nghĩa bộ nhớ theo hợp đồng của thao tác CAS tương ứng. Đó là cơ sở cho việc phối hợp giữa các luồng, nhưng không biến toàn bộ thân vòng lặp thành vùng độc quyền.

### Không bảo đảm một luồng cụ thể sẽ thắng nhanh

Vòng lặp có thể phải thử nhiều lần khi tranh chấp cao. Đối với vòng lặp đơn giản có phép tính hữu hạn, thất bại của CAS mạnh cho biết giá trị đã không còn bằng kỳ vọng tại thời điểm so sánh; thường một cập nhật khác đã chen vào. Điều đó không đặt ra số lần thử tối đa cho từng luồng và không bảo đảm công bằng.

Đừng đồng nhất “không dùng khóa trong đoạn mã” với “luôn nhanh hơn khóa”. Tính toán lại, tải trên bộ nhớ đệm và việc tranh giành cùng một vị trí có thể làm chi phí tăng. Nếu phép tính dài hoặc cạnh tranh cao, cần đo đạc và cân nhắc thiết kế như chia nhỏ trạng thái hay dùng khóa. Không thêm `Thread.sleep` tùy ý để sửa một vòng lặp sai.

### CAS so sánh giá trị hiện tại, không ghi lại toàn bộ lịch sử

Nếu trạng thái đổi `A → B → A` giữa lần đọc và CAS, CAS kỳ vọng `A` vẫn có thể thành công. Đây là vấn đề ABA khi thuật toán cần biết đã có thay đổi trung gian.

Với bộ đếm có quy tắc số học phù hợp, lịch sử trung gian có thể không ảnh hưởng phép tăng. Với cấu trúc dữ liệu dựa trên tham chiếu, danh tính nút và vòng đời có thể rất quan trọng. Khi thuật toán thật sự cần phát hiện lịch sử, phải thiết kế thêm phiên bản hoặc dấu thích hợp; không kết luận rằng chỉ có vòng lặp là loại bỏ ABA. Bài này không triển khai cấu trúc dữ liệu đó.

### Một CAS không bảo vệ nhiều biến độc lập

CAS trên số dư A rồi CAS trên số dư B không tạo thao tác chuyển tiền nguyên tử. CAS thứ hai có thể thất bại sau khi CAS thứ nhất đã thành công. Khi một quy tắc bao trùm nhiều trường, cần chọn cơ chế bao trùm toàn bộ quy tắc: khóa chung, giao dịch, hoặc một đối tượng trạng thái bất biến được công bố bằng một tham chiếu nguyên tử với thuật toán phù hợp.

Với `AtomicReference`, chỉ cập nhật tham chiếu nguyên tử cũng không tự bảo vệ những trường khả biến bên trong đối tượng được tham chiếu. Nếu dùng mô hình tạo trạng thái đề xuất mới, cần tránh sửa đối tượng cũ trong phần có thể thử lại.

### Chọn đúng biến thể CAS

Bài dùng `compareAndSet`, không phải biến thể CAS yếu. Các biến thể có tên `weakCompareAndSet...` có thể thất bại giả và có hợp đồng bộ nhớ riêng; không áp dụng máy móc lập luận “mỗi thất bại là do luồng khác đã đổi giá trị” cho chúng. Với người học mới, dùng CAS mạnh giúp tập trung vào quan hệ giữa ảnh chụp, đề xuất và thử lại.

## 9. Tự kiểm tra

1. Hai luồng cùng đọc `5`, cùng tính `6`. Sau khi một luồng CAS thành công, luồng còn lại cần làm gì?
2. Vì sao chỉ cập nhật `observed` nhưng không tính lại `next` có thể làm mất một lần tăng?
3. Một lambda trong `updateAndGet` được gọi ba lần nhưng chỉ một lần cập nhật thành công. Có gì sai không?
4. Nếu `tryAcquire` trả `false` rồi ngay sau đó có thêm suất, kết quả trước đó có nhất thiết sai không?
5. Sau CAS thành công, gọi `counter.get()` có luôn trả đúng giá trị do lời gọi của mình vừa ghi không?

Đáp án gợi ý:

1. Đọc lại trạng thái, tính đề xuất mới rồi CAS bằng cặp mới.
2. Đề xuất vẫn gắn với ảnh chụp cũ; nó có thể ghi đè hoặc không thực hiện phép tăng dự định.
3. Không. Điều này được phép khi thử lại; hàm phải an toàn khi chạy nhiều lần.
4. Không. Cần xét trạng thái ở điểm tuyến tính hóa của lần thử.
5. Không. Một cập nhật khác có thể xảy ra trước lần đọc bổ sung.

Khi đọc hoặc viết một vòng lặp CAS, hãy kiểm tra ba câu: đề xuất được tính từ ảnh chụp nào, phần nào có thể chạy lại, và thời điểm nào mới được coi là cập nhật thành công.

## Tài liệu đối chiếu

- [AtomicInteger — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): hợp đồng `compareAndSet`, các phương thức cập nhật và yêu cầu đối với hàm cập nhật.
- [Gói java.util.concurrent.atomic — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/atomic/package-summary.html): vai trò của biến nguyên tử và phạm vi hỗ trợ trên một biến.
