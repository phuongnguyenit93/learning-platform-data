# Tiền điều kiện, hậu điều kiện và bất biến

Một phương thức Java có thể biên dịch thành công, vượt qua vài ca kiểm thử và vẫn sai: nó chấp nhận dữ liệu đầu vào không hợp lệ, trả kết quả trái quy tắc hoặc làm hỏng trạng thái dùng chung. Muốn đánh giá **tính đúng đắn (correctness)**, ta cần diễn đạt chính xác điều gì phải đúng **trước**, **sau** và **trong suốt** quá trình xử lý.

Trong module **CODE_QUALITY_FUNDAMENTALS**, ba khái niệm **tiền điều kiện (precondition)**, **hậu điều kiện (postcondition)** và **bất biến (invariant)** giúp chuyển yêu cầu từ câu mô tả chung thành những ràng buộc có thể lý giải, kiểm thử và duy trì. Chúng cũng hỗ trợ mục tiêu rộng hơn của chất lượng mã nguồn: phần mềm đáng tin cậy, dễ hiểu và dễ thay đổi khi nghiệp vụ phát triển.

## 1. Hợp đồng hành vi của một đoạn mã

Hãy xem phương thức `reserve(3)` của đối tượng quản lý tồn kho. Để kết quả đúng, ta có thể yêu cầu:

- **Trước khi gọi:** số lượng đặt giữ lớn hơn 0 và không vượt quá số hàng còn sẵn.
- **Sau khi gọi thành công:** số hàng sẵn giảm đúng 3, số hàng đã giữ tăng đúng 3.
- **Luôn đúng ở trạng thái hợp lệ:** tổng số hàng sẵn và hàng đã giữ bằng tổng tồn kho được quản lý; các số lượng không âm.

Đó là một **hợp đồng hành vi** (*contract*): những điều kiện mà mã và bên gọi có thể dựa vào để phối hợp đúng. Thay vì chỉ nhận xét “phương thức này chạy ổn”, ta hỏi được những câu kiểm chứng cụ thể.

| Khái niệm | Ý nghĩa | Ví dụ với tồn kho | Khi nào kiểm tra? |
| --- | --- | --- | --- |
| **Tiền điều kiện** `P` | Điều phải đúng để thao tác được phép thực hiện | `quantity > 0` và `quantity <= available` | Tại ranh giới đầu vào, trước khi sửa trạng thái |
| **Hậu điều kiện** `Q` | Điều phải đúng khi thao tác hoàn tất thành công | `available = old(available) - quantity` | Sau khi thao tác thành công |
| **Bất biến** `I` | Tính chất phải được duy trì tại các trạng thái được quy định | `available >= 0`, `reserved >= 0`, `available + reserved = total` | Sau khởi tạo và tại ranh giới các thao tác công khai; hoặc ở mỗi bước lặp tùy loại bất biến |

Ký hiệu `old(x)` trong bảng là giá trị của `x` **ngay trước thao tác**, không phải một hàm có sẵn trong Java. Nhờ giá trị cũ, hậu điều kiện diễn đạt được chính xác sự thay đổi thay vì chỉ kiểm tra kết quả cuối cùng có vẻ hợp lệ.

### 1.1. Cách đọc công thức Hoare

Trong lý luận chương trình, một cách diễn đạt hợp đồng là **bộ ba Hoare**:

```text
{ P }  C  { Q }
```

Ở đây `P` là tiền điều kiện; `C` là câu lệnh hoặc đoạn chương trình; `Q` là hậu điều kiện. Cách đọc: **nếu `P` đúng trước khi thực hiện `C`, thì khi `C` kết thúc bình thường, `Q` phải đúng**. Đây là cách diễn đạt về *tính đúng đắn từng phần* (*partial correctness*). Muốn khẳng định *tính đúng đắn toàn phần* (*total correctness*), cần chứng minh thêm chương trình sẽ kết thúc.

Ví dụ nhỏ:

```text
P: amount > 0 và balance >= amount
C: balance = balance - amount
Q: balance = old(balance) - amount và balance >= 0
```

Công thức giúp nêu rõ nghĩa của thao tác, nhưng **không tự chứng minh** mã đúng. Cần xét phép toán có tràn số hay không, trạng thái có bị tác nhân khác thay đổi đồng thời hay không và liệu triển khai có thực sự giữ các điều kiện đã nêu.

## 2. Tiền điều kiện: khi nào lời gọi hợp lệ?

Tiền điều kiện xác định **miền đầu vào và trạng thái cho phép** của thao tác. Tùy hợp đồng API, nó có thể gồm:

1. **Kiểu và sự hiện diện của dữ liệu:** tham chiếu không được `null`, chuỗi không được rỗng, đối tượng phải có cấu trúc hợp lệ.
2. **Miền giá trị:** số lượng phải dương; chỉ số nằm trong giới hạn; ngày bắt đầu không sau ngày kết thúc.
3. **Trạng thái hiện tại:** một đơn hàng chỉ được thanh toán khi ở trạng thái cho phép; không thể hủy lượng hàng vượt quá số đang đặt giữ.
4. **Điều kiện môi trường:** thao tác ghi cần quyền thích hợp hoặc giao dịch còn hoạt động.

Với cùng một phép tính, những ràng buộc này có thể dẫn đến hành vi khác nhau. Ví dụ:

```java
static int percentOf(int part, int whole) {
    if (whole <= 0) {
        throw new IllegalArgumentException("whole must be positive");
    }
    if (part < 0 || part > whole) {
        throw new IllegalArgumentException("part must be in [0, whole]");
    }
    return (int) ((100L * part) / whole);
}
```

**Hợp đồng minh họa:** `whole > 0` và `0 <= part <= whole`; nếu gọi hợp lệ, kết quả là phần trăm nguyên làm tròn xuống trong khoảng 0–100. Ép phép nhân sang `long` trước khi nhân giúp tránh tràn số nguyên `int` cho phép nhân này. Nếu quy tắc nghiệp vụ đòi làm tròn khác hoặc số thập phân, hậu điều kiện cũng phải thay đổi tương ứng.

### 2.1. Làm gì khi tiền điều kiện không thỏa?

Một hợp đồng tốt cần chỉ rõ hành vi khi đầu vào không hợp lệ, nhất là tại API công khai hoặc ranh giới tin cậy:

- **Từ chối và báo lỗi:** ví dụ ném `IllegalArgumentException` khi số lượng không dương.
- **Trả kết quả miền nghiệp vụ:** ví dụ kết quả “không đủ hàng” nếu đây là tình huống dự kiến mà bên gọi cần xử lý.
- **Bảo đảm không thay đổi trạng thái khi thất bại:** đặc biệt cần thiết với các thao tác cập nhật dữ liệu.

Không nên âm thầm sửa dữ liệu không hợp lệ (chẳng hạn đổi số âm thành 0) trừ khi hợp đồng đã quy định rõ cách chuẩn hóa đó. Việc kiểm tra tiền điều kiện càng gần điểm bắt đầu sửa trạng thái càng giúp xác định ranh giới trách nhiệm.

**Phân biệt quan trọng:** kiểm tra điều kiện đầu vào bằng `if` và ném ngoại lệ là một cách *thực thi hợp đồng lúc chạy*. Tiền điều kiện là quy tắc logic; nó vẫn tồn tại ngay cả khi không có câu lệnh kiểm tra tương ứng trong mã.

## 3. Hậu điều kiện: điều gì được bảo đảm khi thành công?

Hậu điều kiện mô tả kết quả mà bên gọi có thể dựa vào **sau khi thao tác thành công**. Nó có thể nói đến giá trị trả về, thay đổi trạng thái và những thứ phải giữ nguyên.

Ví dụ, với thao tác chuyển `quantity` hàng từ “sẵn có” sang “đặt giữ”, giả sử các tiền điều kiện đã đúng:

```text
available_after = available_before - quantity
reserved_after  = reserved_before  + quantity
total_after     = total_before
```

Ba dòng trên mạnh hơn câu “số lượng sau thao tác hợp lệ”: chúng quy định *mức thay đổi chính xác* và *tài sản nào không bị thay đổi*. Ràng buộc “không đổi” thường được gọi là **điều kiện khung** (*frame condition*), vì nó xác định giới hạn tác động của thao tác.

Khi viết hậu điều kiện, cần xét ít nhất:

| Câu hỏi | Ví dụ cần làm rõ |
| --- | --- |
| Kết quả nào là đúng? | Phí giao hàng trả về theo bảng giá nào, với quy tắc làm tròn nào? |
| Thành phần nào được phép thay đổi? | Chỉ `available` và `reserved`; `total` không thay đổi |
| Trường hợp biên có được định nghĩa không? | Đặt giữ **đúng bằng** số lượng đang có phải thành công hay thất bại? |
| Khi thất bại có tác dụng phụ không? | Không được trừ tồn kho trước rồi mới ném ngoại lệ |
| Có tác động ra bên ngoài không? | Ghi cơ sở dữ liệu hoặc phát sự kiện có nằm trong cùng giao dịch hay không? |

Hậu điều kiện thành công **không tự áp dụng** cho lời gọi ném ngoại lệ. Nếu hệ thống còn yêu cầu trạng thái không đổi khi lỗi, hãy ghi đó là một cam kết riêng cho đường thất bại và kiểm thử rõ ràng.

## 4. Bất biến: những điều không được phá vỡ

**Bất biến đối tượng/lớp** (*class invariant*) mô tả những tính chất phải đúng ở trạng thái quan sát được của một đối tượng hợp lệ. Ví dụ, với kho hàng:

```text
I1: available >= 0
I2: reserved >= 0
I3: available + reserved = total
I4: total >= 0 và total không đổi sau khi khởi tạo
```

Chỉ cần một phương thức quên tăng `reserved` trong khi giảm `available`, bất biến `I3` sẽ bị phá vỡ. Hệ thống có thể chưa báo lỗi ngay nhưng những phép tính sau đó đã dựa trên dữ liệu không nhất quán.

Để gìn giữ bất biến, đối tượng nên **kiểm soát đường thay đổi trạng thái**: ẩn trường dữ liệu, khởi tạo hợp lệ, cập nhật qua phương thức có kiểm tra và hạn chế cung cấp tham chiếu có thể sửa trực tiếp cấu trúc nội bộ.

Không phải mọi bất biến đều phải đúng **sau từng dòng lệnh**. Trong một thao tác nội bộ, có thể tồn tại trạng thái trung gian tạm thời, miễn là trạng thái đó không bị quan sát trái phép và bất biến được phục hồi khi thao tác kết thúc bình thường. Với dữ liệu dùng chung giữa nhiều luồng, yêu cầu này còn liên quan đến đồng bộ hóa, tính nguyên tử và ranh giới giao dịch.

**Bất biến vòng lặp** (*loop invariant*) là khái niệm có liên quan nhưng khác: nó phải đúng **trước mỗi lần kiểm tra điều kiện lặp**. Nó giúp suy luận vì sao các bước lặp tích lũy kết quả đúng; không nhất thiết là thuộc tính của cả đối tượng.

## 5. Ví dụ Java xuyên suốt: giữ và trả tồn kho

Xét lớp quản lý lượng hàng của **một mã sản phẩm trong bộ nhớ**, với ba thuộc tính:

- `total`: lượng hàng thuộc phạm vi đối tượng quản lý, cố định từ khi khởi tạo.
- `available`: lượng hàng còn có thể đặt giữ.
- `reserved`: lượng hàng đã đặt giữ nhưng chưa được hoàn trả.

Đây là mô hình dạy học có giới hạn: nó chưa biểu diễn nhập thêm hàng, bán hàng đã giữ, nhiều kho vật lý hoặc lưu trữ cơ sở dữ liệu. Các quy tắc dưới đây chỉ áp dụng trong phạm vi mô hình đó.

### 5.1. Định nghĩa hợp đồng trước khi viết mã

| Thao tác | Tiền điều kiện khi thành công | Hậu điều kiện thành công | Khi điều kiện không thỏa |
| --- | --- | --- | --- |
| `new Stock(total)` | `total >= 0` | `available = total`; `reserved = 0` | Từ chối số âm |
| `reserve(q)` | `q > 0` và `q <= available` | `available' = available - q`; `reserved' = reserved + q` | Báo lỗi, trạng thái không đổi |
| `release(q)` | `q > 0` và `q <= reserved` | `available' = available + q`; `reserved' = reserved - q` | Báo lỗi, trạng thái không đổi |
| Các phương thức đọc | Đối tượng đã được khởi tạo hợp lệ | Trả về ảnh chụp giá trị hiện tại, không sửa trạng thái | Không có nhánh lỗi dự kiến trong mô hình |

Dấu phẩy trên `available'`, `reserved'` chỉ giá trị sau thao tác. Với mọi thao tác thành công, bất biến `I1–I4` ở phần trước phải tiếp tục đúng.

### 5.2. Triển khai có kiểm tra điều kiện

```java
public final class Stock {
    private final int total;
    private int available;
    private int reserved;

    public Stock(int total) {
        if (total < 0) {
            throw new IllegalArgumentException("total must not be negative");
        }
        this.total = total;
        this.available = total;
        this.reserved = 0;
    }

    public synchronized void reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        if (quantity > available) {
            throw new IllegalStateException("not enough available stock");
        }

        available -= quantity;
        reserved += quantity;
    }

    public synchronized void release(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        if (quantity > reserved) {
            throw new IllegalStateException("not enough reserved stock");
        }

        reserved -= quantity;
        available += quantity;
    }

    public synchronized int available() {
        return available;
    }

    public synchronized int reserved() {
        return reserved;
    }

    public int total() {
        return total;
    }
}
```

Những quyết định trong mã xuất phát trực tiếp từ hợp đồng:

1. **Khởi tạo:** `total >= 0` và `available = total`, `reserved = 0`, nên tổng được bảo toàn từ đầu.
2. **Kiểm tra trước khi sửa:** mọi trường hợp lỗi đều ném ngoại lệ trước khi cập nhật trường dữ liệu; vì vậy đường thất bại không làm thay đổi tồn kho.
3. **Đặt giữ:** nhờ `quantity <= available`, phép trừ không tạo số âm. Đồng thời `reserved + quantity <= total`, nên phép cộng không vượt giới hạn `int` khi đối tượng bắt đầu ở trạng thái hợp lệ.
4. **Hoàn trả:** nhờ `quantity <= reserved`, phép trừ không tạo số âm. Tương tự, `available + quantity <= total`.
5. **Đồng bộ:** `synchronized` giúp các thao tác trên **cùng một đối tượng `Stock`** thực thi lần lượt và các phương thức đọc có kết quả nhất quán với cập nhật đó.

Lớp này **không bảo đảm tính nguyên tử giữa nhiều tiến trình, nhiều đối tượng hay nhiều bản ghi cơ sở dữ liệu**. Nếu tồn kho là dữ liệu thật trong hệ thống nhiều máy chủ, cần thiết kế ranh giới giao dịch, khóa hoặc cập nhật có điều kiện tại kho dữ liệu. Việc giữ bất biến ở tầng Java chưa đủ để bảo đảm tính đúng đắn ở toàn hệ thống.

### 5.3. Chứng minh ngắn tính bảo toàn bất biến

Giả sử trước lời gọi `reserve(q)`, ta có:

```text
available >= 0, reserved >= 0
available + reserved = total
0 < q <= available
```

Sau cập nhật:

```text
available' = available - q >= 0
reserved'  = reserved + q  >= 0

available' + reserved'
  = (available - q) + (reserved + q)
  = available + reserved
  = total
```

Vậy các bất biến vẫn đúng. Lập luận cho `release(q)` tương tự khi `0 < q <= reserved`. Điểm mấu chốt là **cả tiền điều kiện lẫn thao tác cập nhật đều cần thiết**: bỏ kiểm tra `q <= available` hoặc quên cập nhật `reserved` có thể phá vỡ chứng minh này.

### 5.4. Kiểm thử hợp đồng với JUnit 5

Các kiểm thử dưới đây sử dụng JUnit Jupiter (`org.junit.jupiter.api`) và giả định `Stock` ở cùng package với `StockTest`:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class StockTest {
    @Test
    void constructorEstablishesInvariant() {
        Stock stock = new Stock(10);
        assertEquals(10, stock.total());
        assertEquals(10, stock.available());
        assertEquals(0, stock.reserved());
    }

    @Test
    void canReserveExactlyAllAvailableItems() {
        Stock stock = new Stock(10);
        stock.reserve(10);
        assertEquals(0, stock.available());
        assertEquals(10, stock.reserved());
        assertEquals(stock.total(), stock.available() + stock.reserved());
    }

    @Test
    void releaseMovesItemsBackToAvailable() {
        Stock stock = new Stock(10);
        stock.reserve(6);
        stock.release(4);
        assertEquals(8, stock.available());
        assertEquals(2, stock.reserved());
        assertEquals(10, stock.available() + stock.reserved());
    }

    @Test
    void invalidReservationLeavesStateUnchanged() {
        Stock stock = new Stock(5);
        assertThrows(IllegalStateException.class, () -> stock.reserve(6));
        assertEquals(5, stock.available());
        assertEquals(0, stock.reserved());
        assertEquals(5, stock.total());
    }

    @Test
    void invalidReleaseLeavesStateUnchanged() {
        Stock stock = new Stock(5);
        stock.reserve(2);
        assertThrows(IllegalStateException.class, () -> stock.release(3));
        assertEquals(3, stock.available());
        assertEquals(2, stock.reserved());
    }

    @Test
    void rejectsNonPositiveQuantityAndNegativeTotal() {
        Stock stock = new Stock(5);
        assertThrows(IllegalArgumentException.class, () -> stock.reserve(0));
        assertThrows(IllegalArgumentException.class, () -> stock.release(-1));
        assertThrows(IllegalArgumentException.class, () -> new Stock(-1));
        assertEquals(5, stock.available());
        assertEquals(0, stock.reserved());
    }
}
```

Bộ kiểm thử chú trọng **ngưỡng đúng bằng lượng còn sẵn**, đường đi bình thường, điều kiện đầu vào sai và cam kết **không đổi trạng thái khi từ chối**. Những kiểm thử này hỗ trợ kiểm chứng; chúng chưa chứng minh tất cả chuỗi thao tác hoặc mọi tình huống đồng thời. Với mã sản xuất, có thể bổ sung kiểm thử thuộc tính (*property-based testing*) sinh nhiều chuỗi `reserve/release` hợp lệ và kiểm tra `available + reserved == total` sau mỗi bước.

## 6. Bất biến vòng lặp: suy luận từ từng bước đến kết quả cuối

Bất biến không chỉ áp dụng cho đối tượng có trạng thái. Xét phương thức tính tổng các số nguyên không âm:

```java
import java.util.Objects;

public class QuantityMath {
    public static long sumNonNegative(int[] values) {
        Objects.requireNonNull(values, "values");
        long sum = 0;

        for (int i = 0; i < values.length; i++) {
            if (values[i] < 0) {
                throw new IllegalArgumentException("negative quantity");
            }
            sum += values[i];
        }
        return sum;
    }
}
```

**Hợp đồng thành công:** `values != null`, mọi phần tử đều không âm; kết quả trả về bằng tổng các phần tử. Nếu phần tử âm, phương thức ném ngoại lệ; nếu `values == null`, nó ném `NullPointerException`. Dùng `long` để tổng của các phần tử `int` không bị tràn ở phạm vi độ dài mảng Java có thể biểu diễn.

Ta chọn bất biến tại đầu mỗi vòng lặp:

```text
0 <= i <= values.length
sum = values[0] + values[1] + ... + values[i - 1]
```

Ba phần của lập luận:

1. **Khởi tạo:** khi `i = 0`, chưa có phần tử nào được cộng; `sum = 0` là tổng của đoạn rỗng.
2. **Duy trì:** nếu bất biến đúng ở đầu lượt `i`, việc cộng `values[i]` rồi tăng `i` làm `sum` bằng tổng của `i + 1` phần tử đầu tiên. Với đầu vào hợp lệ, không có ngoại lệ làm gián đoạn đường thành công.
3. **Kết thúc:** khi `i == values.length`, bất biến suy ra `sum` bằng tổng toàn bộ mảng, đúng hậu điều kiện.

Ngoài ra, đại lượng `values.length - i` là số nguyên không âm và giảm sau mỗi lượt, giúp giải thích vì sao vòng lặp sẽ kết thúc khi đầu vào là một mảng hữu hạn. Đó là bước suy luận bổ sung từ tính đúng đắn từng phần sang tính đúng đắn toàn phần.

## 7. Chuyển hợp đồng thành kiểm thử và review

Để tránh kiểm thử chỉ đi qua “đường vui”, có thể dùng ma trận sau khi nhận một yêu cầu:

| Loại điều kiện | Câu hỏi kiểm thử | Ví dụ |
| --- | --- | --- |
| Tiền điều kiện hợp lệ | Có chấp nhận các giá trị biên hợp lệ? | `reserve(available)` phải thành công |
| Tiền điều kiện không hợp lệ | Có từ chối rõ ràng mà không sửa trạng thái? | `reserve(available + 1)` bị từ chối |
| Hậu điều kiện | Kết quả và mức thay đổi có đúng chính xác? | Đặt giữ 3 làm `available` giảm 3, `reserved` tăng 3 |
| Điều kiện khung | Có thuộc tính nào ngoài phạm vi bị đổi? | `total` giữ nguyên |
| Bất biến | Các quan hệ giữa trường còn đúng qua chuỗi thao tác? | `available + reserved == total` sau nhiều lần giữ/trả |
| Tình huống lỗi | Lỗi xảy ra ở bước nào; có cập nhật dở dang? | Thao tác không đủ hàng không làm mất hàng |
| Đồng thời | Nhiều tác nhân có quan sát hoặc cập nhật trạng thái trái quy tắc? | Hai lời gọi giữ hàng cùng lúc không được vượt tổng tồn kho |

Trong review, hãy yêu cầu người sửa nêu ngắn gọn: **hợp đồng trước khi thay đổi**, **hợp đồng cần duy trì** và **bằng chứng kiểm tra**. Khi bổ sung nghiệp vụ mới, trước tiên cập nhật hợp đồng, rồi điều chỉnh mã và kiểm thử theo cùng định nghĩa.

### Các công cụ và giới hạn

- **`if` + ngoại lệ** hữu ích tại biên API để thực thi tiền điều kiện và mô tả lỗi rõ ràng.
- **JUnit** kiểm tra các trường hợp được chọn; kiểm thử tham số và kiểm thử thuộc tính giúp tăng phạm vi tình huống.
- **`assert` của Java** phù hợp để kiểm tra giả định nội bộ trong quá trình phát triển, nhưng thường bị tắt khi không bật cờ `-ea`. Không dùng `assert` làm cơ chế duy nhất để bảo vệ đầu vào hoặc quy tắc nghiệp vụ trong môi trường chạy thật.
- **Phân tích tĩnh, type system, thiết kế kiểu dữ liệu** có thể giúp loại trừ một phần trạng thái không hợp lệ; chúng không tự thay thế ràng buộc nghiệp vụ hoặc việc kiểm tra hành vi thực tế.
- **Kiểm thử đồng thời và giao dịch** cần thiết khi bất biến phụ thuộc vào nhiều tác nhân. Hợp đồng cục bộ của một đối tượng không tự bao trùm toàn bộ hệ thống.

## 8. Lỗi tư duy thường gặp

| Ngộ nhận | Hệ quả | Điều chỉnh |
| --- | --- | --- |
| “Không ném ngoại lệ tức là kết quả đúng.” | Đầu ra có thể sai nhưng vẫn nằm trong kiểu hợp lệ | Định nghĩa hậu điều kiện bằng giá trị và quan hệ chính xác |
| “Kiểm tra đầu vào xong là đủ.” | Phần cập nhật có thể phá vỡ bất biến | Kiểm tra cả hậu điều kiện và trạng thái sau thao tác |
| “Bất biến phải đúng ở mọi dòng lệnh.” | Nhầm lẫn trạng thái nội bộ tạm thời với trạng thái quan sát được | Xác định rõ ranh giới mà bất biến phải đúng, bảo đảm tính nguyên tử thích hợp |
| “Kiểm thử bao phủ 100% chứng minh hợp đồng.” | Có thể bỏ sót giá trị biên, chuỗi thao tác hoặc tương tác đồng thời | Xây dựng kiểm thử từ từng mệnh đề của hợp đồng |
| “`assert` sẽ luôn bảo vệ đầu vào.” | Trong nhiều cấu hình chạy, assertion không được thực thi | Dùng kiểm tra rõ ràng cho điều kiện cần bảo vệ khi chạy thật |
| “Dùng `int` luôn an toàn vì đúng kiểu.” | Phép toán trung gian có thể tràn số | Xét miền giá trị, thứ tự phép toán, kiểu rộng hơn hoặc phép toán có kiểm tra |

## 9. Bài tập áp dụng

Một hệ thống có đối tượng `Wallet` quản lý số dư bằng đơn vị nhỏ nhất của tiền tệ. Nó hỗ trợ `deposit(amount)` và `withdraw(amount)`. Yêu cầu: số dư không âm; không cho rút quá số dư; không được tạo số dư vượt miền giá trị của kiểu dữ liệu.

Hãy tự hoàn thành các bước:

1. Viết **tiền điều kiện** cho hai thao tác (lưu ý cả số dương, số dư hiện tại và nguy cơ tràn số khi nạp).
2. Viết **hậu điều kiện** thành công bằng ký hiệu `old(balance)`; nêu rõ trạng thái khi lời gọi bị từ chối.
3. Xác định **bất biến** phải đúng sau khi tạo ví và sau mỗi thao tác công khai.
4. Đề xuất các ca kiểm thử tại biên: `amount = 0`, `amount = balance`, `amount > balance`, số dư gần giới hạn kiểu và chuỗi nạp/rút liên tiếp.
5. Giải thích điều gì còn thiếu nếu ví được cập nhật đồng thời từ nhiều dịch vụ.

**Gợi ý đối chiếu:** Với `withdraw(amount)`, nếu trả về thành công thì `amount > 0`, `amount <= old(balance)`, `balance = old(balance) - amount` và `balance >= 0`. Với `deposit(amount)`, cần bảo đảm phép cộng không vượt giá trị lớn nhất trước khi ghi, chẳng hạn kiểm tra `amount <= Long.MAX_VALUE - balance` khi cả hai đều không âm và dùng `long`. Ở hệ thống phân tán, cần cơ chế giao dịch hoặc cập nhật có điều kiện tại nguồn dữ liệu lưu trữ để bảo vệ bất biến qua nhiều tác nhân.

## 10. Ghi nhớ

**Tiền điều kiện** trả lời “khi nào có thể gọi?”, **hậu điều kiện** trả lời “thành công thì chính xác điều gì đúng?”, còn **bất biến** trả lời “điều gì phải luôn được bảo toàn tại các ranh giới đã xác định?”.

Ba khái niệm tạo thành một cách làm việc thực dụng: diễn đạt quy tắc trước, chọn thiết kế ngăn trạng thái sai, kiểm tra biên và đường thất bại, rồi dùng kiểm thử và lập luận để xác nhận mã thực hiện đúng hợp đồng. Khi các ràng buộc được viết rõ, người bảo trì dễ thay đổi cách triển khai hơn vì biết điều gì được phép đổi và điều gì phải được giữ nguyên.
