# Kiểm tra bất biến và các thuộc tính thay vì chỉ ví dụ cố định

Một hàm có thể vượt qua toàn bộ các ca kiểm thử quen thuộc mà vẫn sai ở dữ liệu biên, tổ hợp hiếm hoặc chuỗi thao tác dài. Ví dụ, chức năng giữ hàng vượt qua các ca “kho có 10, giữ 2” và “kho có 10, giữ 5”, nhưng lại từ chối giữ đúng 10 sản phẩm vì dùng toán tử `>=` thay cho `>`. Bộ test có ví dụ cụ thể đã chứng minh một số trường hợp đúng; nó chưa cho biết **quy luật mà chức năng phải tuân thủ** có được giữ với những trường hợp khác hay không.

Trong chương **Bằng chứng kiểm thử** của **CODE_QUALITY_FUNDAMENTALS**, bài học này trình bày cách kiểm tra **bất biến** (*invariants*) và **thuộc tính** (*properties*) để bổ sung cho kiểm thử bằng ví dụ cố định. Cách tiếp cận này phục vụ mục tiêu của học phần: hiểu những thuộc tính khiến mã nguồn **đáng tin cậy, dễ hiểu và dễ thay đổi**. Một yêu cầu được phát biểu thành quy luật có thể kiểm tra sẽ giúp phát hiện lỗi ngoài những đầu vào lập trình viên dự đoán sẵn và giữ ý nghĩa nghiệp vụ ổn định khi thay đổi cách cài đặt.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **kiểm thử theo ví dụ** với **kiểm thử dựa trên thuộc tính** (*property-based testing*).
2. Chuyển hợp đồng nghiệp vụ thành bất biến, hậu điều kiện và quan hệ giữa các thao tác.
3. Chọn miền dữ liệu sinh, trường hợp biên và giả định đầu vào để test không kiểm tra nhầm những tình huống ngoài hợp đồng.
4. Viết ví dụ Java/JUnit 5 và minh họa sử dụng thư viện jqwik để kiểm tra nhiều bộ dữ liệu.
5. Hiểu vai trò của seed, khả năng tái hiện lỗi (*reproducibility*) và thu nhỏ ca lỗi (*shrinking*).
6. Nhận ra giới hạn của test: mẫu sinh ngẫu nhiên không phải chứng minh hình thức, và unit test đối tượng không thay thế kiểm thử đồng thời hay tích hợp.

## 1. Kiểm thử bằng ví dụ trả lời câu hỏi nào?

**Kiểm thử theo ví dụ** (*example-based testing*) chọn một bộ đầu vào cụ thể và kỳ vọng kết quả cụ thể:

```text
Given tồn kho tổng cộng 10 sản phẩm, đã giữ 3
When  giữ thêm 2 sản phẩm
Then  đã giữ 5, còn có thể giữ 5
```

Đây là một ca có ích: dễ đọc, bám yêu cầu cụ thể và chỉ rõ kết quả sai nếu bị lỗi. Trong Java, test có thể viết:

```java
@Test
void reservesTwoItems() {
    InventoryState before = new InventoryState(10, 3);

    InventoryState after = before.reserve(2);

    assertEquals(5, after.reserved());
    assertEquals(5, after.available());
}
```

Nhưng riêng test này không kiểm tra các tình huống như:

- Kho không còn sản phẩm khả dụng.
- Giữ đúng số sản phẩm còn lại.
- Giữ số lượng không dương.
- Giữ rồi hoàn lại số lượng vừa giữ.
- Gọi nhiều thao tác liên tiếp và giữ bất biến sau mỗi bước.
- Tổ hợp giá trị sát giới hạn của kiểu dữ liệu.

Thêm nhiều ví dụ là cần thiết, nhưng việc liệt kê tất cả tổ hợp có thể là bất khả thi. **Kiểm thử dựa trên thuộc tính** bổ sung một câu hỏi khác: *Có điều gì luôn phải đúng với mọi đầu vào thuộc miền hợp lệ và mọi kết quả của thao tác hay không?*

### Hai cách kiểm tra bổ sung cho nhau

| Tiêu chí | Ví dụ cố định | Kiểm thử thuộc tính |
| --- | --- | --- |
| Đầu vào | Một số bộ dữ liệu đã chọn. | Nhiều bộ dữ liệu được sinh theo miền quy định. |
| Kỳ vọng | Một kết quả chính xác cho từng ví dụ. | Một quy luật phải đúng cho mỗi trường hợp sinh ra. |
| Thế mạnh | Diễn đạt yêu cầu cụ thể, regression, trường hợp từng gây lỗi. | Tìm ca bất thường, tổ hợp hiếm và quan hệ tổng quát bị vi phạm. |
| Điểm yếu | Dễ bỏ sót trường hợp chưa nghĩ tới. | Phụ thuộc vào chất lượng thuộc tính và bộ sinh; test chạy hữu hạn. |
| Khi thất bại | Đã biết ngay ví dụ đầu vào. | Cần ghi lại seed và dữ liệu; công cụ có thể thu nhỏ ca lỗi. |

Không có yêu cầu phải chọn **một trong hai**. Một bộ test tốt thường giữ ví dụ có ý nghĩa nghiệp vụ, bổ sung test biên có chủ đích và sử dụng thuộc tính để khám phá nhiều trường hợp khác.

## 2. Bất biến, hậu điều kiện và thuộc tính khác nhau ra sao?

**Bất biến** là điều kiện phải được giữ ở những trạng thái được xem là hợp lệ. **Hậu điều kiện** là điều phải đúng sau một thao tác thành công, nếu tiền điều kiện của thao tác đã được đáp ứng. **Thuộc tính kiểm thử** là một mệnh đề tổng quát có thể kiểm tra trên những đầu vào hoặc chuỗi thao tác được sinh ra.

Giả sử một hệ thống chỉ quản lý tổng số hàng có sẵn trong kho và số hàng đã được giữ chỗ:

```text
onHand   = tổng số sản phẩm kho đang quản lý
reserved = số đã giữ cho các yêu cầu
available = onHand - reserved
```

Theo **hợp đồng minh họa** của bài, một yêu cầu giữ hàng phải dương và không vượt số lượng có thể giữ. Thao tác hoàn trả hàng đã giữ cũng phải dương và không vượt số lượng đang giữ. Ví dụ này chưa mô hình hóa nhập kho, xuất kho, hàng hỏng, TTL của giữ hàng hay nhiều kho.

Những mệnh đề quan trọng có thể viết:

| Ký hiệu | Mệnh đề | Nhóm |
| --- | --- | --- |
| I1 | `onHand >= 0`. | Bất biến trạng thái. |
| I2 | `0 <= reserved <= onHand`. | Bất biến liên trường. |
| I3 | `available + reserved = onHand`. | Quan hệ bảo toàn theo mô hình. |
| P1 | Nếu `0 < q <= available`, `reserve(q)` thành công và trạng thái mới vẫn thỏa I1–I3. | Tiền/hậu điều kiện. |
| P2 | Giữ `q` rồi hoàn trả đúng `q` đưa trạng thái về giá trị ban đầu. | Thuộc tính quan hệ thao tác. |
| P3 | Nếu hai lượng giữ `a`, `b` đều hợp lệ và `a+b <= available`, thứ tự hai lần giữ không làm đổi trạng thái cuối. | Thuộc tính hoán đổi trong mô hình này. |
| P4 | Nếu `q <= 0` hoặc `q > available`, thao tác giữ bị từ chối. | Thuộc tính đầu vào sai. |

I1–I3 là **quy tắc trạng thái**. P1–P4 biến những quy tắc và hành vi thao tác thành **điều có thể thử với nhiều giá trị**.

> Những thuộc tính này chỉ đúng trong phạm vi mô hình được nêu. Trong hệ thống thật, giữ hàng có thể tạo mã giữ chỗ, timestamp, sự kiện hoặc thứ tự ưu tiên. Khi đó không thể tự suy rằng hai lần giữ hàng đảo thứ tự cho kết quả giống nhau ở mọi mặt. Hãy phát biểu chính xác **điều mà hợp đồng cần tương đương**.

## 3. Mô hình Java làm đối tượng cần kiểm thử

Ta chọn một kiểu giá trị bất biến trong Java 17. Constructor kiểm tra I1–I2; `available()` được tính từ các trường gốc để tránh lưu hai giá trị có thể mâu thuẫn; mỗi thao tác tạo trạng thái mới.

**`InventoryState.java`:**

```java
public record InventoryState(int onHand, int reserved) {

    public InventoryState {
        if (onHand < 0 || reserved < 0 || reserved > onHand) {
            throw new IllegalArgumentException("Invalid inventory state");
        }
    }

    public int available() {
        return onHand - reserved;
    }

    public InventoryState reserve(int quantity) {
        if (quantity <= 0 || quantity > available()) {
            throw new IllegalArgumentException("Invalid reserve quantity");
        }
        return new InventoryState(onHand, reserved + quantity);
    }

    public InventoryState release(int quantity) {
        if (quantity <= 0 || quantity > reserved) {
            throw new IllegalArgumentException("Invalid release quantity");
        }
        return new InventoryState(onHand, reserved - quantity);
    }
}
```

Với tiền điều kiện trên, `reserved + quantity <= onHand <= Integer.MAX_VALUE` nên phép cộng không tràn `int`; phép trừ trong `available()` và `release()` cũng không tràn. Nếu sau này thêm nhập/xuất kho hoặc chọn kiểu khác, phải xem lại giới hạn và các phép toán tương ứng.

Ví dụ sử dụng:

```java
InventoryState initial = new InventoryState(10, 3);
InventoryState afterReserve = initial.reserve(2);
InventoryState restored = afterReserve.release(2);

System.out.println(afterReserve.available()); // 5
System.out.println(initial.equals(restored));  // true
```

Đối tượng `initial` không bị thay đổi sau lời gọi `reserve`. Đây là một thuộc tính quan trọng của cách thiết kế bất biến: khi lời gọi ném ngoại lệ, trạng thái ban đầu cũng không bị sửa dở dang.

### Lỗi điển hình bị ví dụ cố định bỏ sót

Một phiên bản sai có thể chứa:

```java
if (quantity <= 0 || quantity >= available()) {
    throw new IllegalArgumentException("Invalid reserve quantity");
}
```

Lệnh này từ chối cả trường hợp `quantity == available()`, trong khi hợp đồng cho phép giữ hết phần còn lại. Một test chỉ thử giữ `2` khi còn `7` sẽ không phát hiện lỗi. Test ranh giới “giữ đúng toàn bộ số khả dụng” phải là một ví dụ bắt buộc, và bộ sinh thuộc tính cũng cần **chủ động** tạo giá trị ở ranh giới đó.

## 4. Từ yêu cầu thành thuộc tính kiểm thử

Để viết property tốt, trước hết phải phân biệt **giả định về dữ liệu trước thao tác** và **điều cần đúng sau thao tác**.

Ví dụ, mệnh đề:

```text
Với mọi trạng thái S hợp lệ và mọi q thỏa 1 <= q <= S.available:
    T = S.reserve(q)
    T.onHand == S.onHand
    T.reserved >= 0
    T.available >= 0
    T.reserved + T.available == T.onHand
    T.release(q) == S
```

Mệnh đề nói rõ phạm vi; nếu bộ sinh đưa `q = 0` vào mà test đòi `reserve(q)` thành công, **test đang sai hợp đồng**, không phải implementation. Tương tự, thuộc tính “giữ hàng làm giảm available” cần điều kiện `q > 0`; nếu không, sẽ mâu thuẫn với chính quy tắc đầu vào.

### Nên kiểm tra điều gì?

Có nhiều kiểu thuộc tính bổ sung cho nhau:

| Kiểu thuộc tính | Câu hỏi | Minh họa |
| --- | --- | --- |
| **Bất biến** | Trạng thái hợp lệ còn hợp lệ sau thao tác không? | `0 <= reserved <= onHand`. |
| **Bảo toàn** | Đại lượng nào phải được giữ nguyên? | `reserved + available == onHand`. |
| **Quan hệ nghịch đảo** | Có thao tác nào phục hồi lại trạng thái trước không? | `reserve(q)` rồi `release(q)` trả về trạng thái ban đầu. |
| **Đơn điệu** | Giá trị nào chỉ có thể tăng/giảm theo thao tác? | `reserve(q)` không làm tăng `available`. |
| **Hoán đổi** | Thứ tự một số thao tác có làm đổi kết quả không? | Hai lần `reserve` hợp lệ, khi chỉ xét trạng thái tổng hợp, cho kết quả cuối giống nhau. |
| **Đầu vào sai** | Hệ thống có từ chối và giữ nguyên trạng thái không? | `reserve(0)`, `reserve(-1)`, `reserve(available+1)`. |
| **Tất định** | Cùng dữ liệu đầu vào có cho cùng kết quả không? | Với kiểu giá trị thuần, hai lời gọi từ cùng một trạng thái tạo giá trị bằng nhau. |

Không nên lấy chính implementation làm “oracle” cho test. Ví dụ, kiểm tra `after.reserved() == before.reserved() + q` là một hậu điều kiện hữu ích, nhưng nếu chỉ sao chép nguyên biểu thức từ phương thức đang kiểm tra, một sai lầm chung trong đặc tả có thể làm cả code và test cùng xanh. Phối hợp nhiều loại thuộc tính độc lập như **bất biến, quan hệ nghịch đảo, trường hợp biên và yêu cầu nghiệp vụ được xác nhận** sẽ cho bằng chứng mạnh hơn.

### Thuộc tính nhìn có vẻ hợp lý nhưng sai

Không thể áp đặt `reserve(q)` là idempotent:

```text
S.reserve(q).reserve(q) == S.reserve(q)  // Sai nói chung.
```

Giữ hàng là thao tác tích lũy: gọi hai lần từ trạng thái đủ hàng thì tăng số lượng đã giữ hai lần. Nếu API nghiệp vụ hỗ trợ *idempotency key* để một **ý định giữ hàng** không bị áp dụng hai lần khi retry, thuộc tính đó thuộc **hợp đồng API/dịch vụ có định danh yêu cầu**, không tự xuất hiện trong phương thức `InventoryState.reserve(q)`. Nhầm lẫn phạm vi thuộc tính sẽ tạo test sai hoặc dẫn đến thiết kế sai.

## 5. Kiểm thử thuộc tính với JUnit 5 và dữ liệu sinh có seed

Không bắt buộc có thư viện property-based testing để bắt đầu. Một vòng sinh dữ liệu dùng `java.util.Random` với **seed cố định** có thể kiểm tra nhiều trạng thái:

**`InventoryStateTest.java` (JUnit 5):**

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Random;
import org.junit.jupiter.api.Test;

class InventoryStateTest {
    private static final long SEED = 20261116L;

    @Test
    void reservePreservesInvariantsAndReleaseRestoresState() {
        Random random = new Random(SEED);

        for (int iteration = 0; iteration < 10_000; iteration++) {
            int onHand = random.nextInt(10_001);
            int reserved = random.nextInt(onHand + 1);
            InventoryState before = new InventoryState(onHand, reserved);

            assertEquals(onHand,
                    before.reserved() + before.available());

            if (before.available() == 0) {
                continue;
            }

            int quantity = 1 + random.nextInt(before.available());
            InventoryState after = before.reserve(quantity);

            assertEquals(before.onHand(), after.onHand());
            assertTrue(after.reserved() >= 0);
            assertTrue(after.reserved() <= after.onHand());
            assertTrue(after.available() >= 0);
            assertEquals(after.onHand(),
                    after.reserved() + after.available());
            assertTrue(after.available() < before.available());
            assertEquals(before, after.release(quantity));
        }
    }

    @Test
    void coversExactBoundaryAndInvalidQuantities() {
        InventoryState before = new InventoryState(10, 3);

        InventoryState fullyReserved = before.reserve(7);
        assertEquals(0, fullyReserved.available());
        assertEquals(before, fullyReserved.release(7));

        assertThrows(IllegalArgumentException.class,
                () -> before.reserve(0));
        assertThrows(IllegalArgumentException.class,
                () -> before.reserve(-1));
        assertThrows(IllegalArgumentException.class,
                () -> before.reserve(8));
        assertEquals(new InventoryState(10, 3), before);
    }

    @Test
    void invalidStateCannotBeCreated() {
        assertThrows(IllegalArgumentException.class,
                () -> new InventoryState(-1, 0));
        assertThrows(IllegalArgumentException.class,
                () -> new InventoryState(10, -1));
        assertThrows(IllegalArgumentException.class,
                () -> new InventoryState(10, 11));
    }
}
```

Test thứ nhất chọn nhiều cặp `(onHand, reserved)` hợp lệ, chỉ chọn số lượng `quantity` trong miền cho phép, rồi kiểm tra hàng loạt thuộc tính. Test thứ hai **cố định các ranh giới bắt buộc**; đây là phần mà sinh ngẫu nhiên thuần túy có thể bỏ lỡ.

### Seed giúp ích gì?

- Với cùng `SEED` và cùng thuật toán sinh, vòng test chọn lại cùng chuỗi dữ liệu, giúp tái hiện lỗi.
- Khi dùng random seed thay đổi giữa các lần chạy, hãy **ghi seed thất bại** và bộ dữ liệu tối thiểu vào báo cáo để điều tra được.
- Nếu thay thuật toán sinh hoặc phiên bản thư viện, cùng seed không nhất thiết tạo cùng chuỗi dữ liệu; **đầu vào gây lỗi thực tế** vẫn nên được lưu thành ca regression.

JUnit test phía trên không có **shrinking tự động**. Nếu một ca lớn thất bại, người viết phải tự thu gọn hoặc ghi từng giá trị rồi rút ra trường hợp đơn giản nhất. Các framework chuyên dụng hỗ trợ tốt hơn công việc này.

## 6. Sử dụng jqwik để sinh và thu nhỏ trường hợp kiểm thử

**jqwik** là một thư viện property-based testing cho JVM có thể dùng với hệ sinh thái JUnit Platform. Các annotation `@Property`, `@ForAll` và `@Provide` cho phép định nghĩa nhiều đầu vào từ bộ sinh `Arbitrary`. Cần khai báo jqwik như một dependency kiểm thử trong dự án muốn chạy ví dụ này; chỉ có JUnit Jupiter thì chưa đủ.

Ví dụ sau sử dụng **cùng lớp `InventoryState`** nhưng sinh cả trạng thái hợp lệ và lượng cần giữ trong miền:

```java
import static org.junit.jupiter.api.Assertions.*;

import net.jqwik.api.Arbitraries;
import net.jqwik.api.Arbitrary;
import net.jqwik.api.ForAll;
import net.jqwik.api.Property;
import net.jqwik.api.Provide;

class InventoryProperties {
    record ReservationCase(InventoryState before, int quantity) {}

    @Provide
    Arbitrary<ReservationCase> reservationCases() {
        return Arbitraries.integers().between(1, 1000)
                .flatMap(onHand ->
                    Arbitraries.integers().between(0, onHand - 1)
                        .flatMap(reserved ->
                            Arbitraries.integers()
                                .between(1, onHand - reserved)
                                .map(quantity -> new ReservationCase(
                                    new InventoryState(onHand, reserved),
                                    quantity))));
    }

    @Property(tries = 500)
    void reservationMaintainsInvariants(
            @ForAll("reservationCases") ReservationCase sample) {

        InventoryState before = sample.before();
        int quantity = sample.quantity();
        InventoryState after = before.reserve(quantity);

        assertEquals(before.onHand(), after.onHand());
        assertTrue(after.reserved() >= 0);
        assertTrue(after.reserved() <= after.onHand());
        assertEquals(after.onHand(),
                after.reserved() + after.available());
        assertEquals(before, after.release(quantity));
    }
}
```

Bộ sinh trên bảo đảm `onHand >= 1`, `0 <= reserved < onHand` và `1 <= quantity <= available`. Nó không cần phải “lọc bỏ” hàng nghìn bộ dữ liệu sai; mỗi trường hợp được tạo đã đáp ứng tiền điều kiện của `reserve`. Đổi lại, những trạng thái có `available == 0` hay trường hợp số lượng không hợp lệ cần property hoặc ca ví dụ riêng.

### Shrinking là gì?

Khi một property thất bại với trạng thái lớn, công cụ có thể thử **thu nhỏ** các giá trị để tìm phản ví dụ dễ đọc hơn. Chẳng hạn:

```text
Ca lỗi ban đầu: onHand=987, reserved=24, quantity=963
Có thể rút gọn: onHand=1, reserved=0, quantity=1
```

Nếu implementation sai ở trường hợp giữ đúng số còn lại, ca nhỏ `(1, 0, 1)` giúp người đọc nhìn ra điều kiện `>=` bị viết sai. Đây là ví dụ về **kiểu phản ví dụ mong muốn**, không phải cam kết rằng jqwik luôn rút đúng chuỗi số đó. Hiệu quả shrinking phụ thuộc cách bộ sinh được xây dựng; các chuỗi `flatMap` có ràng buộc chéo có thể khó thu nhỏ hơn kiểu cấu trúc được thiết kế riêng.

Hãy xem đầu vào nhỏ được công cụ báo và lưu nó thành **regression test có tên diễn đạt lỗi**. Property tiếp tục có giá trị để khám phá những trường hợp khác, còn ca regression giúp bất cứ người sửa code nào hiểu nhanh bug đã từng xảy ra.

## 7. Chọn miền và bộ sinh để phát hiện lỗi thật

Một property được lặp 100.000 lần trên các số trong khoảng `1..10` chưa chắc tốt hơn property chạy 500 lần nhưng tạo đúng các vùng dữ liệu rủi ro. Chất lượng kiểm thử phụ thuộc vào **cách chọn miền, phân bố và ranh giới**.

| Miền cần kiểm | Giá trị/nhóm nên sinh có chủ đích | Lỗi có thể phát hiện |
| --- | --- | --- |
| Số nguyên | 0, 1, -1, giới hạn kiểu, giá trị ngay sát ngưỡng. | Sai dấu so sánh, tràn số. |
| Quan hệ hai số | Bằng nhau, chênh 1, đảo thứ tự. | Bỏ sót điều kiện biên, bất biến liên trường. |
| Collection | Rỗng, một phần tử, nhiều phần tử, phần tử lặp, thứ tự khác nhau. | Giả định sai về kích thước/duy nhất/thứ tự. |
| Chuỗi | Rỗng, khoảng trắng, Unicode, ký tự đặc biệt, chuỗi dài. | Chuẩn hóa sai, giới hạn độ dài, xử lý encoding. |
| Thời gian | Mốc bằng nhau, trước/sau, ngày chuyển tháng/năm, offset khác nhau. | So sánh và múi giờ sai. |
| Tiền tệ | 0, số lẻ, số lớn, nhiều đơn vị tiền nếu được hỗ trợ. | Nhầm đơn vị, làm tròn, tràn. |
| Trạng thái nghiệp vụ | Mọi trạng thái hợp lệ và chuyển trạng thái không hợp lệ. | Đi đường tắt, bỏ qua điều kiện vòng đời. |
| Hệ thống phân tán | Gửi trùng, đảo thứ tự, timeout sau commit, chạy đồng thời. | Tác dụng phụ lặp, mất cập nhật, không nhất quán. |

Với `InventoryState`, cần **ép sinh** những lớp đặc biệt: `available = 0`, `quantity = available`, `quantity = 1`, `reserved = 0` và `reserved = onHand`. Bộ sinh hợp lệ và bộ sinh không hợp lệ nên tách rõ để expected outcome không mơ hồ.

### Đừng lạm dụng giả định làm test bỏ qua dữ liệu

Một cách viết property kém hiệu quả:

```text
sinh hai int bất kỳ a, b
nếu a < 0 hoặc b < 0 hoặc b > a: bỏ qua
kiểm tra thuộc tính trên phần còn lại
```

Hầu hết giá trị trong miền `int` có thể bị loại. Test trông như đã chạy nhiều lần nhưng rất ít trường hợp hợp lệ được kiểm tra. Nên sinh trực tiếp `onHand >= 0` rồi sinh `reserved` trong `[0, onHand]`. Nếu dùng bộ lọc/assumption, hãy theo dõi số trường hợp bị loại để biết test có thật sự thử được miền quan tâm.

## 8. Quan hệ biến đổi và kiểm thử metamorphic

Đôi khi không có cách dễ dàng để tính **đáp án chính xác** cho mọi đầu vào. *Metamorphic testing* kiểm tra quan hệ giữa **nhiều lần thực thi**, thay vì cần biết trước một giá trị kết quả riêng lẻ.

Ví dụ trong mô hình tồn kho:

```text
reserve(q) rồi release(q)  →  khôi phục trạng thái ban đầu

reserve(a) rồi reserve(b)  →  cùng trạng thái cuối với
reserve(b) rồi reserve(a), nếu cả hai trình tự đều hợp lệ
```

Thuộc tính thứ nhất là **nghịch đảo**. Thuộc tính thứ hai là **hoán đổi thao tác** trong mô hình chỉ giữ tổng số lượng, không lưu mã giữ hàng và thứ tự thực hiện.

Ví dụ JUnit 5 kiểm tra tính hoán đổi ở một ca cụ thể:

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class InventoryOrderTest {
    @Test
    void reservingTwoQuantitiesIsOrderIndependentInThisModel() {
        InventoryState initial = new InventoryState(10, 2);

        InventoryState left = initial.reserve(3).reserve(4);
        InventoryState right = initial.reserve(4).reserve(3);

        assertEquals(left, right);
        assertEquals(1, left.available());
    }
}
```

Khi sinh ngẫu nhiên `a` và `b`, cần bảo đảm tổng `a+b <= available` **mà không tràn số**, chẳng hạn giới hạn miền nhỏ hoặc tính tổng bằng `long`. Nếu muốn mở rộng sang đối tượng giữ hàng có định danh, thứ tự nghiệp vụ và thời điểm tạo, phải điều chỉnh thuộc tính thành “tổng số lượng cuối giống nhau” thay vì “toàn bộ đối tượng bằng nhau”.

Một số quan hệ metamorphic thường hữu ích:

- **Định dạng và phân tích cú pháp:** với các giá trị được hỗ trợ, `parse(format(x))` phải khôi phục giá trị tương đương `x`.
- **Sắp xếp:** sắp xếp danh sách đã sắp xếp lại không đổi kết quả; kết quả được sắp xếp và giữ nguyên số lần xuất hiện của mỗi phần tử.
- **Mã hóa và giải mã:** với dữ liệu thuộc miền được hỗ trợ, `decode(encode(x))` trả lại dữ liệu gốc.
- **Chia nhỏ rồi gộp:** một phép tính có tính kết hợp có thể cho kết quả tương đương khi chia nhóm; cần xem kỹ làm tròn và tràn số.

Các quan hệ này **không đúng cho mọi hàm**. Ví dụ phép cộng số thực dấu phẩy động không bảo đảm kết hợp chính xác theo từng bit; thứ tự làm tròn có thể thay đổi kết quả. Trước khi dùng một quan hệ làm oracle, hãy kiểm tra nó thực sự được hợp đồng cho phép.

## 9. Kiểm thử chuỗi thao tác và mô hình trạng thái

Một bất biến có thể đúng sau **một** thao tác nhưng bị phá sau **một chuỗi dài**: giữ hàng, hoàn một phần, giữ tiếp, hoàn hết, thử giữ quá số tồn. Khi đó có thể dùng *stateful property testing* hoặc *model-based testing*.

Quy trình chung:

1. Định nghĩa trạng thái ban đầu hợp lệ.
2. Định nghĩa những command được phép ở trạng thái hiện tại.
3. Sinh một chuỗi command với lượng dữ liệu hợp lệ hoặc có chủ đích không hợp lệ.
4. Thực thi từng command và kiểm tra bất biến sau **mỗi bước**.
5. Khi thất bại, thu ngắn chuỗi đến phần nhỏ nhất vẫn tái hiện lỗi.

Ví dụ Java/JUnit 5 chạy nhiều chuỗi giữ và hoàn trả:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Random;
import org.junit.jupiter.api.Test;

class InventorySequenceTest {
    @Test
    void invariantHoldsAfterEveryStep() {
        Random random = new Random(43102L);

        for (int scenario = 0; scenario < 200; scenario++) {
            int total = random.nextInt(101);
            InventoryState state = new InventoryState(total, 0);

            for (int step = 0; step < 200; step++) {
                boolean chooseReserve = random.nextBoolean();

                if (chooseReserve && state.available() > 0) {
                    int q = 1 + random.nextInt(state.available());
                    state = state.reserve(q);
                } else if (state.reserved() > 0) {
                    int q = 1 + random.nextInt(state.reserved());
                    state = state.release(q);
                }

                assertEquals(total, state.onHand());
                assertTrue(state.reserved() >= 0);
                assertTrue(state.available() >= 0);
                assertEquals(total,
                        state.reserved() + state.available());
            }
        }
    }
}
```

Test trên kiểm tra **40.000 bước chuyển trạng thái** trong những chuỗi sinh từ seed cố định. Số bước lớn không tự bảo đảm đã thử mọi trạng thái; bộ sinh có thể thiên lệch một số kiểu chuỗi. Có thể bổ sung command bất hợp lệ, thay đổi tồn kho tổng theo hợp đồng và test trình tự biên có chủ đích. Khi property thất bại, ghi lại seed, scenario, step và chuỗi command giúp tái hiện nhanh hơn.

### So sánh với một mô hình tham chiếu

Với thao tác phức tạp, có thể xây dựng **một mô hình tham chiếu đơn giản** và so kết quả trạng thái của hệ thống thật sau mỗi command. Chẳng hạn, mô hình dùng một tập `Set<String>` chứa mã giữ hàng đang hoạt động, còn hệ thống thật lưu ở DB. Từ cùng chuỗi lệnh, cả hai phải cho cùng số lượng đang giữ và cùng khả năng nhận/từ chối yêu cầu.

Mô hình tham chiếu phải **độc lập đủ mức** với cách cài đặt cần kiểm tra. Nếu sao chép cùng thuật toán hoặc cùng lỗi vào mô hình, phép so sánh không phát hiện được vấn đề.

## 10. Khi có đồng thời và tác dụng phụ, cần mở rộng phạm vi

Unit test của `InventoryState` kiểm tra giá trị thuần trong bộ nhớ. Nó chưa chứng minh **một dịch vụ tồn kho thực sự** không giữ vượt tổng khi hai request đồng thời. Hai request có thể cùng đọc còn 5, mỗi request giữ 4 và cùng được chấp nhận nếu lớp lưu trữ thiếu cập nhật nguyên tử.

Để kiểm chứng bất biến ở cấp hệ thống, cần xác định:

| Cấp kiểm chứng | Ví dụ thuộc tính | Cơ chế cần thử |
| --- | --- | --- |
| Value object | `0 <= reserved <= onHand` sau mỗi thao tác. | Unit/property test của Java object. |
| Repository/DB | Tổng số lượng giữ không vượt tồn kho sau các transaction. | Integration test với DB và cập nhật có điều kiện/khóa phù hợp. |
| API có retry | Một ý định giữ hàng với cùng idempotency key không bị áp dụng hai lần. | Kiểm thử duplicate request và timeout sau commit. |
| Event consumer | Cùng event được phát lại không tạo thêm tác dụng phụ nghiệp vụ. | Kiểm thử giao sự kiện lặp và transaction đánh dấu đã xử lý. |
| Quy trình nghiệp vụ | Sau hủy giữ hàng, hàng trở lại khả dụng theo hợp đồng. | Integration/E2E và kiểm thử bù trừ/lỗi trung gian. |

Với tính đúng đắn đồng thời, thuộc tính có thể là:

```text
Sau khi mọi thao tác hoàn tất:
    tổng lượng đã giữ thành công <= tồn kho được phép sử dụng
    mỗi request được chấp nhận có biên nhận tương ứng
    request bị từ chối không làm giảm tồn kho
```

Thử một vài request song song không phải chứng minh đầy đủ mọi lịch thực thi (*interleaving*). Có thể dùng stress test, cơ chế chèn lỗi, công cụ kiểm tra đồng thời phù hợp và ràng buộc DB để tăng độ tin cậy. **Một thuộc tính có ý nghĩa phải được đo ở đúng phạm vi trạng thái mà nó mô tả.**

## 11. Đánh giá sức mạnh của bằng chứng kiểm thử

Không nên diễn giải “10.000 ca random đã xanh” thành “đã chứng minh không còn bug”. Test chỉ kiểm tra những trường hợp được tạo trong môi trường và thời điểm thực thi cụ thể. Bằng chứng mạnh hơn khi kết hợp nhiều mặt:

| Bằng chứng | Nó giúp thấy gì? | Giới hạn |
| --- | --- | --- |
| Ví dụ nghiệp vụ cụ thể | Kết quả mong đợi dễ hiểu, có thể truy vết về yêu cầu. | Dễ bỏ sót dữ liệu chưa được chọn. |
| Giá trị biên có chủ đích | Các nhầm lẫn `<` / `<=`, trạng thái rỗng và ngưỡng. | Chưa bao phủ mọi tổ hợp. |
| Property-based testing | Quy luật có còn đúng ở nhiều bộ dữ liệu sinh ra? | Phụ thuộc cách sinh và tính đúng của thuộc tính. |
| Stateful/model-based testing | Bất biến còn đúng sau chuỗi chuyển trạng thái? | Mô hình tham chiếu hoặc bộ sinh command có thể thiếu trường hợp. |
| Mutation testing | Test có phát hiện được những thay đổi lỗi có chủ đích trong code? | Mutant sống không tự chứng minh test sai; cần phân tích trường hợp tương đương. |
| Integration/concurrency testing | Ràng buộc có được duy trì qua DB, mạng và nhiều luồng? | Giới hạn bởi môi trường, lịch thực thi và tải. |
| Phân tích tĩnh/chứng minh hình thức | Một số loại vi phạm được chứng minh hoặc loại bỏ theo mô hình. | Cần giả định và mô hình chính xác; có chi phí triển khai. |

Ví dụ mutation testing thay `quantity > available()` thành `quantity >= available()`. Nếu không có test nào thất bại, bộ kiểm thử đang thiếu ca ranh giới hoặc oracle chưa đủ mạnh. Thêm test `reserve(available())` là cải thiện trực tiếp, không cần tăng số random vô hạn.

**Code coverage cao chỉ nói những dòng/nhánh nào đã chạy**, không chứng minh các assertion thể hiện đúng nghiệp vụ. Một property sai có thể chạy hàng triệu lần mà vẫn cho cảm giác an toàn giả tạo.

## 12. Những sai lầm thường gặp

**“Viết nhiều test cùng công thức với implementation là đủ.”** Nếu code và test cùng hiểu nhầm yêu cầu, cả hai đều có thể sai giống nhau. Hãy lấy thuộc tính từ hợp đồng, ví dụ nghiệp vụ và quan hệ độc lập.

**“Chạy nhiều trường hợp ngẫu nhiên tự động tìm được trường hợp biên.”** Một bộ sinh đều trên miền rộng có thể rất hiếm tạo đúng ngưỡng. Cần chỉ định ranh giới và các nhóm dữ liệu quan trọng.

**“Mọi dữ liệu bất kỳ đều phải được chấp nhận.”** Nhiều phương thức có tiền điều kiện. Property cho đường thành công phải sinh dữ liệu hợp lệ; property cho đầu vào sai phải kiểm tra quy tắc từ chối riêng.

**“Một ca test thất bại khi random chạy lại được là đủ.”** Phản ví dụ cần seed và đầu vào cụ thể để người khác tái hiện. Sau khi sửa, hãy giữ test regression cho lỗi đã tìm ra.

**“Một thuộc tính càng tổng quát càng mạnh.”** Thuộc tính vượt quá phạm vi nghiệp vụ, như bắt một lệnh giữ hàng phải idempotent, có thể sai và dẫn đến thiết kế sai.

**“Hàm thuần đúng thì service cũng đúng.”** DB, retry, concurrency và tác dụng phụ ngoài tiến trình cần test và biện pháp bảo vệ ở cấp tương ứng.

**“Shrinking luôn đưa ra lỗi nhỏ nhất.”** Công cụ thường cố gắng thu nhỏ phản ví dụ theo thuật toán của bộ sinh, nhưng không cam kết tìm tối ưu toàn cục. Dữ liệu có ràng buộc chéo có thể cần bộ sinh tốt hơn.

**“Property test thay thế mọi test ví dụ.”** Những kịch bản nghiệp vụ, lỗi đã từng xảy ra và hợp đồng API cụ thể vẫn nên được biểu diễn bằng ví dụ dễ đọc.

## 13. Quy trình thực hành khi kiểm tra một chức năng mới

1. **Xác định phạm vi và hợp đồng.** Đầu vào nào hợp lệ, bất biến nào phải giữ và trạng thái nào được quan sát?
2. **Viết ví dụ chấp nhận quan trọng.** Ghi các ca thông thường, đầu vào không hợp lệ và đúng ranh giới theo yêu cầu.
3. **Rút ra các thuộc tính.** Bảo toàn, đơn điệu, nghịch đảo, tương đương, thứ tự và kết quả khi thao tác bị từ chối.
4. **Kiểm tra tính đúng của từng mệnh đề.** Thử tìm phản ví dụ về mặt nghiệp vụ trước khi đưa vào test.
5. **Thiết kế bộ sinh có ý thức.** Sinh trực tiếp miền hợp lệ, bổ sung miền sai và các phân bố có chủ đích ở ngưỡng.
6. **Gắn khả năng tái hiện.** Lưu seed, input, chuỗi command và phiên bản môi trường khi thất bại.
7. **Thu nhỏ, sửa và lưu ca regression.** Biến một lần tìm được lỗi thành bảo vệ lâu dài.
8. **Kiểm tra đúng tầng trách nhiệm.** Bất biến của object kiểm bằng unit test; bất biến liên DB, API và concurrency cần kiểm chứng tích hợp phù hợp.
9. **Đánh giá sức mạnh test theo lỗi có thể bắt.** Kết hợp review thuộc tính, boundary test và mutation testing nếu có ích.
10. **Cập nhật test khi hợp đồng đổi.** Nếu nghiệp vụ cho phép giữ quá tồn kho theo hạn mức, không giữ property cũ như một “chân lý” bất biến.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Một test xác nhận `reserve(2)` thành công khi còn 7 sản phẩm. Test này có bắt được lỗi dùng `quantity >= available` để từ chối không?

*Gợi ý:* Không. Cần thử `reserve(7)` khi `available=7`, hoặc sinh lượng giữ đúng ranh giới. Thuộc tính phải cho phép giữ toàn bộ lượng có thể giữ.

**Câu 2.** Thuộc tính “`release(q)` là phép nghịch đảo của `reserve(q)`” cần giả định gì?

*Gợi ý:* `reserve(q)` phải hợp lệ, trạng thái không bị thao tác khác xen vào và `release(q)` có thể hoàn đúng lượng đã giữ. Với hệ thống có mã giữ chỗ, thu phí hoặc sự kiện, cần nói rõ những phần trạng thái được mong đợi phục hồi.

**Câu 3.** Khi sinh `onHand` và `reserved` độc lập từ toàn bộ miền `int`, rồi bỏ các cặp không hợp lệ, có vấn đề gì?

*Gợi ý:* Phần lớn dữ liệu có thể bị loại; test thực tế kiểm quá ít trạng thái hợp lệ. Nên sinh `reserved` dựa trên `onHand` để dữ liệu đáp ứng tiền điều kiện.

**Câu 4.** Một property chạy 100.000 lần và đều xanh. Có thể khẳng định chương trình đúng với mọi đầu vào không?

*Gợi ý:* Không. Kết quả là bằng chứng trên tập dữ liệu đã sinh, trong môi trường đã chạy; có thể còn miền chưa được sinh hoặc mệnh đề test đang thiếu/hiểu sai yêu cầu.

**Câu 5.** Vì sao unit property test của `InventoryState` chưa đủ để kết luận hai HTTP request giữ hàng đồng thời không thể vượt tồn kho?

*Gợi ý:* Đối tượng thuần không mô hình hóa giao dịch, dữ liệu chia sẻ và lịch thực thi đồng thời. Cần kiểm thử và cơ chế cập nhật nguyên tử ở cấp repository/dịch vụ.

**Câu 6.** Khi jqwik tìm một input gây lỗi rồi thu gọn nó, nên làm gì sau khi sửa implementation?

*Gợi ý:* Lưu ca tối giản thành regression test có tên rõ, giữ property test để tiếp tục khám phá, và ghi nguyên nhân cùng thay đổi hợp đồng nếu có.

## Ghi nhớ

- **Ví dụ cố định** cho biết một vài tình huống mong đợi; **thuộc tính** mô tả quy luật cần đúng trong toàn miền được đặc tả.
- Bất biến, hậu điều kiện, quan hệ bảo toàn, nghịch đảo và metamorphic relation là nguồn xây dựng oracle có giá trị.
- **Chất lượng bộ sinh quan trọng hơn số lần chạy đơn thuần**: hãy chủ động có ranh giới, trường hợp rỗng, giá trị lớn và trình tự nghiệp vụ đáng ngờ.
- Seed, shrinking và regression test giúp biến lỗi ngẫu nhiên thành ca tái hiện và bảo vệ lâu dài.
- Bằng chứng kiểm thử luôn có **phạm vi và giới hạn**. Hãy kết hợp property test với ví dụ nghiệp vụ, kiểm thử tích hợp, kiểm tra đồng thời và review hợp đồng khi cần.

**Câu hỏi thực hành:** “Ngoài vài đầu vào đã viết trong test, điều gì về kết quả hoặc trạng thái **bắt buộc luôn đúng** với mọi đầu vào hợp lệ?” Câu trả lời là nơi bắt đầu để thiết kế những thuộc tính kiểm thử đáng giá.
