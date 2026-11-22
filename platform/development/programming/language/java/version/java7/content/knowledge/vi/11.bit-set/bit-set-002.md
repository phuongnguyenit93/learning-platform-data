# Phân biệt độ dài logic và dung lượng lưu trữ trong Java BitSet

**Chủ đề:** Java 7 — `BitSet`  
**Bài học:** Phân biệt độ dài logic với dung lượng lưu trữ  
**Phiên bản thực hành:** Java 17+; sử dụng `java.util.BitSet` và các API hiện hành, tránh dựa vào chi tiết bộ nhớ của một bản JDK cụ thể.

## 1. Tại sao BitSet có cả length() và size()?

`BitSet` là tập hợp các bit Boolean được đánh chỉ số **từ 0**. Có thể tưởng tượng mỗi vị trí là một công tắc: `true` nếu bit được bật, `false` nếu chưa bật hoặc đã tắt. Không giống `boolean[]` có chiều dài cố định, `BitSet` **có thể mở rộng khi cần**.

Đây là điểm dễ nhầm khi mới học: **vùng lưu trữ được chuẩn bị bên trong** không phải **độ dài logic của các bit đang bật**, và cả hai đều không đồng nghĩa với **số bit có giá trị true**.

Ba method phải phân biệt:

- **`length()`:** độ dài logic, bằng **chỉ số bit được bật cao nhất cộng 1**. Nếu không có bit nào bật, trả `0`.
- **`size()`:** số **vị trí bit mà vùng lưu trữ hiện tại có không gian biểu diễn**. Nó phản ánh cách implementation dự trữ/lưu bit, **không** phải số phần tử thật, cũng không phải giới hạn cố định của dữ liệu nghiệp vụ.
- **`cardinality()`:** số lượng bit **đang bật (true)**. Đây mới là “đếm có bao nhiêu cờ được chọn”.

Ví dụ nếu bật bit `2` và bit `9`:

```text
chỉ số:     9 8 7 6 5 4 3 2 1 0
giá trị:    1 0 0 0 0 0 0 1 0 0

length()      = 10    (bit cao nhất là 9)
cardinality() = 2     (chỉ có hai bit bằng true)
size()        = dung lượng lưu trữ hiện có;
                không nhất thiết bằng 10 hoặc 2
```

`BitSet` **không tự nhớ** rằng nghiệp vụ muốn có “10 ô lựa chọn” chỉ vì đã từng có bit `9`. Nếu xóa bit `9`, `length()` giảm về `3` ngay khi bit `2` là bit cao nhất còn bật. Nếu xóa cả bit `2`, `length()` trở về `0`.

**Kết luận cốt lõi:** Nếu cần biểu diễn chính xác 10, 12 hay 365 vị trí, bạn phải lưu **độ rộng miền nghiệp vụ** riêng. Đừng lấy `BitSet.length()` hoặc `BitSet.size()` thay cho nó.

## 2. Bảng đối chiếu API

| Phương thức | Đo lường | Khi tập hợp rỗng | Khi bật bit cao | Khi xóa bit cao nhất |
| --- | --- | --- | --- | --- |
| `length()` | Chỉ số bit true cao nhất + 1 | `0` | Tăng đến `index + 1` nếu index mới cao nhất | Có thể giảm mạnh |
| `size()` | Số bit của không gian lưu trữ hiện tại | Phụ thuộc cách khởi tạo/implementation | Có thể tăng để chứa index mới | **Không phải phép đo độ dài logic**, không nên suy đoán cách thu hồi |
| `cardinality()` | Tổng số bit true | `0` | Tăng thêm 1 nếu bit trước đó false | Giảm 1 nếu bit trước đó true |
| `isEmpty()` | Có không có bit true | `true` | `false` nếu một bit được bật | `true` khi đã tắt hết |
| `get(index)` | Giá trị của một vị trí bit | `false` với index không âm | Không thay đổi trạng thái | Không thay đổi trạng thái |

Với mọi `BitSet` ở trạng thái bình thường:

```text
0 <= cardinality() <= length() <= size()
```

Đây là quan hệ hữu ích để **hiểu ý nghĩa**, không phải công thức chuyển đổi giữa các chỉ số. Hai `BitSet` có cùng `length()` có thể có số bit true khác nhau. Hai `BitSet` có cùng `cardinality()` cũng có thể bật các bit ở những vị trí hoàn toàn khác nhau.

### 2.1. Vì sao size() không phải một số ổn định để đưa vào giao thức?

JavaDoc mô tả `size()` là số bit của **không gian thực tế được dùng để biểu diễn các giá trị bit** và nói rõ nó **liên quan tới implementation**. Một số implementation phổ biến lưu các bit theo những word máy; việc mở rộng thường theo các nhóm word, nên con số `size()` có thể lớn hơn `length()` đáng kể.

**Không dựa vào các giả định sau:**

- `size()` luôn bằng `length()`.
- `size()` luôn là số bit người dùng cho phép chọn.
- `size()` luôn là một con số cố định giữa mọi bản JDK.
- `size() / 8` là chính xác số byte RAM mà object dùng (còn overhead object, metadata, array, alignment và cách cấp phát).
- `clear()` sẽ ngay lập tức trả toàn bộ phần bộ nhớ đã cấp phát cho hệ thống.

`size()` có ích khi **quan sát dung lượng tương đối** và nghiên cứu hiệu suất, không phải giá trị đáng tin để định nghĩa kích thước dữ liệu nghiệp vụ.

## 3. Constructor chỉ đưa ra dung lượng ban đầu, không đặt giới hạn logic

Hai cách tạo thường thấy:

```java
BitSet a = new BitSet();
BitSet b = new BitSet(128);
```

Đây là **đoạn minh họa trong method** với `import java.util.BitSet;`. Constructor có tham số `int nbits` yêu cầu khởi tạo không gian đủ để **biểu diễn được** các bit chỉ số `0..nbits-1`. Nó **không tự bật** bit nào và **không cấm** gọi `set` tại chỉ số lớn hơn `nbits - 1`.

Ngay sau `new BitSet(128)`:

- `length() == 0` vì không có bit nào true.
- `cardinality() == 0`.
- `isEmpty() == true`.
- `size() >= 128` theo nhu cầu lưu trữ ban đầu.
- `get(127) == false`, mặc dù vùng lưu trữ có không gian cho vị trí đó.

Để bật bit, phải gọi `set`; để có một **giới hạn tối đa**, code ứng dụng phải tự kiểm tra index.

### 3.1. Ví dụ runnable: ba con số khác nhau

Tạo file `BitSetDimensionsDemo.java`:

```java
import java.util.BitSet;

public class BitSetDimensionsDemo {
    public static void main(String[] args) {
        BitSet bits = new BitSet(128);

        System.out.println("new-length=" + bits.length());
        System.out.println("new-count=" + bits.cardinality());
        System.out.println(
                "reserved-space=" + (bits.size() >= 128));

        bits.set(3);
        bits.set(130);
        System.out.println(
                "after-set-length=" + bits.length());
        System.out.println(
                "after-set-count=" + bits.cardinality());
        System.out.println(
                "space-covers-length="
                + (bits.size() >= bits.length()));

        bits.clear(130);
        System.out.println(
                "after-clear-high-length=" + bits.length());
        System.out.println(
                "after-clear-high-count=" + bits.cardinality());

        bits.clear();
        System.out.println(
                "after-clear-all-length=" + bits.length());
        System.out.println(
                "after-clear-all-count=" + bits.cardinality());
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 -Xlint:all BitSetDimensionsDemo.java
java BitSetDimensionsDemo
```

**stdout chính xác:**

```text
new-length=0
new-count=0
reserved-space=true
after-set-length=131
after-set-count=2
space-covers-length=true
after-clear-high-length=4
after-clear-high-count=1
after-clear-all-length=0
after-clear-all-count=0
```

**Phân tích:**

1. Constructor yêu cầu không gian cho ít nhất 128 vị trí nhưng `length` và `cardinality` vẫn `0`. **Dung lượng có sẵn không tạo ra bit true**.
2. `bits.set(3)` bật bit `3`; `bits.set(130)` bật bit `130`. Do đó `length() == 131` và `cardinality() == 2`. Điều này cũng chứng minh `128` **không phải trần cho chỉ số**.
3. `bits.clear(130)` tắt bit cao nhất. Bit `3` còn true nên `length() == 4`, dù từng có bit ở vị trí 130.
4. `bits.clear()` tắt tất cả, đưa `length` và `cardinality` về `0`. Bài không khẳng định rằng Java phải thu hồi một lượng bộ nhớ cụ thể ngay lúc clear.

**Tại sao không in cố định `size()` trong stdout?** Con số cụ thể có thể bị ảnh hưởng bởi cách cấp phát và phiên bản JDK. Ví dụ chỉ kiểm tra các **bất biến có ý nghĩa ngữ nghĩa**; muốn quan sát máy bạn, hãy thử thêm `System.out.println(bits.size())` rồi ghi rõ đây là một kết quả đo **của môi trường đó**, không phải giá trị để code dựa vào.

## 4. Length là vị trí bit cao nhất, không phải số phần tử

Giả sử những bit true nằm tại `{2, 1000}`:

- `length() == 1001`.
- `cardinality() == 2`.
- `size()` cần đủ để biểu diễn index `1000`, có thể lớn hơn `1001`.

Một cấu trúc cực kỳ thưa có thể có `length` rất lớn dù `cardinality` chỉ là 1. Không nên coi `length()` là phép đếm những phần tử được sử dụng.

### 4.1. Xóa đúng bit cao nhất làm length() giảm

`BitSet` không lưu “độ dài cao nhất từng chạm tới” ở `length()`. Nó phản ánh **trạng thái bit hiện tại**.

Nếu tập hợp có `{7, 63}`, `length() == 64`. Sau khi `clear(63)`, bit true cao nhất còn lại là `7`, nên `length() == 8`. Nếu `flip(7)` để tắt bit cuối cùng thì `length() == 0`.

Ngược lại, xóa một bit nằm **dưới** bit true cao nhất chỉ giảm `cardinality`, chưa chắc giảm `length`.

### 4.2. Range dùng điểm cuối loại trừ

`set(fromIndex, toIndex)`, `clear(fromIndex, toIndex)` và `flip(fromIndex, toIndex)` dùng đoạn **[fromIndex, toIndex)**:

```java
bits.set(4, 8);    // Bật 4, 5, 6, 7; không bật 8.
bits.clear(6, 8);  // Tắt 6, 7.
bits.flip(0, 4);   // Đảo 0, 1, 2, 3.
```

Đây là **mã minh họa** trong method. Một range như `set(0, 10)` bật 10 bit và làm `length() == 10` nếu không có bit cao hơn đã bật. Nhưng nếu set cả range rồi xóa bit `9`, `length()` giảm về `9` (bit `8` là cao nhất), chứ không lưu độ rộng ban đầu là 10.

### 4.3. Ví dụ runnable về set, clear và flip

Tạo file `BitSetMutationsDemo.java`:

```java
import java.util.BitSet;

public class BitSetMutationsDemo {
    static void show(String event, BitSet bits) {
        System.out.println(
                event + "=" + bits
                + " length=" + bits.length()
                + " count=" + bits.cardinality());
    }

    public static void main(String[] args) {
        BitSet bits = new BitSet();
        bits.set(7);
        bits.set(63);
        show("initial", bits);

        bits.clear(63);
        show("clear-last", bits);

        bits.flip(7);
        show("flip-last", bits);

        bits.set(100, false);
        show("clear-false", bits);

        bits.flip(4, 8);
        show("flip-range", bits);

        bits.flip(4, 8);
        show("flip-again", bits);

        bits.set(0, 4);
        show("set-range", bits);

        bits.clear(1, 4);
        show("remove-range", bits);
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all BitSetMutationsDemo.java
java BitSetMutationsDemo
```

```text
initial={7, 63} length=64 count=2
clear-last={7} length=8 count=1
flip-last={} length=0 count=0
clear-false={} length=0 count=0
flip-range={4, 5, 6, 7} length=8 count=4
flip-again={} length=0 count=0
set-range={0, 1, 2, 3} length=4 count=4
remove-range={0} length=1 count=1
```

**Chú ý thêm:** `set(100, false)` tương đương việc xóa bit `100`. Nó không làm tăng độ dài logic thành `101`, vì không có bit true mới. `flip(4,8)` bật hoặc tắt từng bit trong range: sau lần đảo thứ hai, các bit lại false và `length()` về `0`.

`BitSet.toString()` in **danh sách chỉ số bit đang bật** như `{4, 5, 6, 7}`, không in chuỗi nhị phân `0000...` và không tiết lộ dung lượng lưu trữ.

## 5. Trường hợp quan trọng nhất: độ rộng nghiệp vụ cố định

Giả sử thiết kế bộ cờ cho **12 tháng**. Bit `0` đại diện tháng 1, bit `11` đại diện tháng 12. Trên thực tế, phần lớn tháng chưa bật thì `BitSet.length()` có thể là `0`, `1`, `7` hoặc `12`. Không con số nào, ngoài biến domain riêng, có thể bảo đảm **có đúng 12 vị trí thuộc mô hình nghiệp vụ**.

Cần lưu hai ý độc lập:

- `DOMAIN_WIDTH = 12`: mô hình có đúng 12 lựa chọn hợp lệ.
- `BitSet`: chỉ lưu tháng nào đang được chọn; `length()` chỉ là đặc trưng của bit cao nhất đang bật.

Đừng viết:

```java
// Sai nếu muốn lặp đủ 12 tháng:
// for (int i = 0; i < months.length(); i++) {
//     render(months.get(i));
// }
```

Nếu tháng 11 và 12 đang false, loop trên bỏ qua chúng, dù giao diện vẫn cần hiển thị.

Thay bằng loop tới `DOMAIN_WIDTH` và kiểm tra index trước khi `get`/`set`. Điều này đặc biệt quan trọng với bitsets biểu diễn quyền, lịch, trạng thái các slot cố định, ngày trong tháng, flags theo schema hay một protocol có chiều dài được thỏa thuận.

### 5.1. Ví dụ runnable: wrapper giữ độ rộng đúng nghĩa

Tạo file `FixedWidthBitSetDemo.java`:

```java
import java.util.BitSet;
import java.util.List;

public class FixedWidthBitSetDemo {
    static final class Months {
        static final int WIDTH = 12;
        private final BitSet enabled = new BitSet(WIDTH);

        void enable(int month, boolean value) {
            checkMonth(month);
            enabled.set(month - 1, value);
        }

        boolean contains(int month) {
            checkMonth(month);
            return enabled.get(month - 1);
        }

        List<Integer> selectedMonths() {
            return enabled.stream()
                    .map(index -> index + 1)
                    .boxed()
                    .toList();
        }

        String bits() {
            StringBuilder result = new StringBuilder(WIDTH);
            for (int index = WIDTH - 1; index >= 0; index--) {
                result.append(enabled.get(index) ? '1' : '0');
            }
            return result.toString();
        }

        int logicalLength() {
            return enabled.length();
        }

        int selectedCount() {
            return enabled.cardinality();
        }

        private static void checkMonth(int month) {
            if (month < 1 || month > WIDTH) {
                throw new IllegalArgumentException(
                        "month out of range: " + month);
            }
        }
    }

    static void print(String label, Months months) {
        System.out.println(
                label + " width=" + Months.WIDTH
                + " length=" + months.logicalLength()
                + " count=" + months.selectedCount()
                + " bits=" + months.bits()
                + " months=" + months.selectedMonths());
    }

    public static void main(String[] args) {
        Months months = new Months();
        print("initial", months);

        months.enable(1, true);
        months.enable(12, true);
        print("enabled", months);

        months.enable(12, false);
        print("disable-high", months);

        try {
            months.enable(13, true);
        } catch (IllegalArgumentException ex) {
            System.out.println("reject=" + ex.getMessage());
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all FixedWidthBitSetDemo.java
java FixedWidthBitSetDemo
```

```text
initial width=12 length=0 count=0 bits=000000000000 months=[]
enabled width=12 length=12 count=2 bits=100000000001 months=[1, 12]
disable-high width=12 length=1 count=1 bits=000000000001 months=[1]
reject=month out of range: 13
```

**Phân tích thiết kế:**

1. `WIDTH` là hằng domain được giữ **riêng** và không thay đổi khi bật/tắt bit. Hàm `bits()` luôn tạo một chuỗi đúng 12 chữ số nhị phân, kể cả khi `length() == 0`.
2. Mapping giữa tháng và bit luôn là `index = month - 1`. Nếu truyền tháng 13, `checkMonth` từ chối; nếu bỏ kiểm tra, `BitSet` sẽ **tự mở rộng**, vô tình nhận trạng thái ngoài mô hình.
3. `selectedMonths()` sử dụng `BitSet.stream()` để duyệt **chỉ các bit true**, không dùng `size()` hay một loop duyệt từng bit để đếm. `IntStream.map` và `Stream.toList()` ở ví dụ phù hợp Java 17+.
4. Sau khi tắt tháng 12, `logicalLength()` trở về `1` vì tháng 1 là bit `0`; nhưng **domain vẫn 12 tháng**.
5. Nếu class cần cho phép caller nhận bản sao `BitSet`, hãy dùng `(BitSet) enabled.clone()`; không trả thẳng reference mutable nội bộ nếu điều đó cho phép phá bất biến width.

**Nhắc lại:** `new BitSet(WIDTH)` chỉ là cấu hình không gian ban đầu để giảm số lần mở rộng ở một số implementation; việc **kiểm tra phạm vi** mới thực sự bảo đảm giá trị hợp lệ.

## 6. Khi nào cần length(), size() hoặc cardinality()?

Chọn theo câu hỏi:

| Câu hỏi | Cách đo đúng |
| --- | --- |
| Có bit true nào không? | `isEmpty()` hoặc `cardinality() == 0` |
| Có bao nhiêu bit true? | `cardinality()` |
| Bit true cao nhất ở đâu? | Nếu không rỗng, `length() - 1` |
| Cần biểu diễn mọi bit đến vị trí true cao nhất? | `length()` |
| Object đã có vùng lưu trữ đủ nhiều bit không? | `size()` như thông tin dung lượng implementation |
| Cấu hình này có bao nhiêu slot hợp lệ theo schema? | **Biến `width`/`domainSize` riêng** |
| Cần bao nhiêu byte để lưu những bit có ý nghĩa hiện tại? | `toByteArray().length`, dựa trên bit true cao nhất |
| Có bao nhiêu vị trí đang được bật khi có khoảng trống lớn? | `cardinality()`, không phải `length()` |
| Muốn lặp qua tất cả bit true? | `stream()` hoặc `nextSetBit()` |
| Muốn lặp đủ n vị trí cho một biểu mẫu? | Loop với `domainSize`, dùng `get(index)` |

**Cẩn thận với `length() - 1`:** khi không có bit true, `length() == 0` và phép trừ cho ra `-1`. `-1` không phải index hợp lệ để truyền cho `get`/`set`. Nên kiểm tra `isEmpty()` trước khi dùng bit cao nhất.

## 7. Duyệt BitSet: bit đang bật khác mọi vị trí có thể có

Có hai bài toán khác nhau:

**A. Duyệt bit đang bật** — ví dụ lấy ID các cờ đã chọn:

```java
for (int index = bits.nextSetBit(0);
        index >= 0;
        index = bits.nextSetBit(index + 1)) {
    process(index);
}
```

Đây là **đoạn minh họa**, `bits` và `process` nằm trong ứng dụng. `nextSetBit` tìm bit true tiếp theo và trả `-1` nếu không còn. Với code hiện đại, `bits.stream()` thường ngắn gọn hơn.

**B. Duyệt toàn bộ miền hợp lệ** — ví dụ dựng 12 ô checkbox:

```java
for (int index = 0; index < domainWidth; index++) {
    render(index, bits.get(index));
}
```

Đây là **đoạn minh họa**; `domainWidth` được xác định theo nghiệp vụ. Không thay `domainWidth` bằng `length()` vì những bit false ở cuối miền sẽ bị bỏ qua.

**Cảnh báo:** `nextClearBit(fromIndex)` tìm bit false tiếp theo, kể cả **vượt quá bit true cuối cùng**. Nó không tự dừng ở `length()` hoặc `size()`. Nếu ứng dụng duyệt bit chưa chọn trong một domain, phải ràng buộc index bằng domain width:

```java
for (int index = bits.nextClearBit(0);
        index < domainWidth;
        index = bits.nextClearBit(index + 1)) {
    renderMissing(index);
}
```

Đây là mã minh họa; biến index không âm, domainWidth là số vị trí hợp lệ. Trong code tổng quát với chỉ số rất lớn, cần thêm các kiểm tra giới hạn `int` trước khi tăng index để tránh overflow; đừng thiết kế vòng lặp vô hạn trên các index không giới hạn.

### 7.1. Ví dụ runnable: duyệt indices và quan sát clear bits

Tạo file `BitSetIterationDemo.java`:

```java
import java.util.ArrayList;
import java.util.BitSet;
import java.util.List;

public class BitSetIterationDemo {
    public static void main(String[] args) {
        BitSet bits = new BitSet();
        bits.set(1);
        bits.set(5);
        bits.set(20);

        System.out.println(
                "stream-indices="
                + bits.stream().boxed().toList());

        List<Integer> viaNext = new ArrayList<>();
        for (int index = bits.nextSetBit(0);
                index >= 0;
                index = bits.nextSetBit(index + 1)) {
            viaNext.add(index);
        }
        System.out.println("next-indices=" + viaNext);

        System.out.println(
                "next-clear-from-10=" + bits.nextClearBit(10));
        System.out.println("count=" + bits.cardinality());

        bits.clear();
        System.out.println(
                "empty-next-set=" + bits.nextSetBit(0));
        System.out.println(
                "empty-next-clear=" + bits.nextClearBit(0));
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all BitSetIterationDemo.java
java BitSetIterationDemo
```

```text
stream-indices=[1, 5, 20]
next-indices=[1, 5, 20]
next-clear-from-10=10
count=3
empty-next-set=-1
empty-next-clear=0
```

`BitSet.stream()` trả **chỉ số các bit true**, không trả một stream các giá trị Boolean. `nextClearBit(10)` trả `10` bởi bit đó đang false; bit false vẫn tồn tại về mặt ý nghĩa ngay cả khi không có ô “được cấp phát riêng” cho index đó.

**Trong tình huống cực đoan:** mô thức tăng `index + 1` có thể tràn số nếu xử lý vị trí `Integer.MAX_VALUE`; ví dụ dạy học và hầu hết ứng dụng không thể cấp phát cấu trúc khổng lồ như vậy, nhưng API tổng quát vẫn nên dùng giới hạn rõ và chọn lối duyệt phù hợp.

## 8. Độ dài logic và biểu diễn byte[] / long[]

`BitSet` hỗ trợ `toByteArray()` và `toLongArray()`, nhưng dữ liệu xuất ra là **biểu diễn gọn tối thiểu của các bit có ý nghĩa**, không phải bản sao nguyên vùng lưu trữ của `size()`.

Theo hợp đồng API:

- `toByteArray()` trả `byte[]` có chiều dài `(length() + 7) / 8`, làm tròn lên theo byte.
- `toLongArray()` trả `long[]` có chiều dài `(length() + 63) / 64`, làm tròn lên theo word 64 bit.
- Nếu không có bit nào true, cả hai đều trả **array độ dài 0**.
- Những bit false ở cuối **không được giữ lại như một số lượng byte cố định**.
- `BitSet.valueOf(byte[])` và `BitSet.valueOf(long[])` cho phép tạo `BitSet` từ biểu diễn phù hợp. Với `byte[]`, cách đánh số bit dùng **little-endian bit numbering** trong mỗi byte (bit chỉ số `0` là bit thấp nhất của byte đầu).

Bởi thế, `new BitSet(256).toByteArray().length == 0` cho tập hợp chưa bật bit, dù constructor đã yêu cầu không gian lưu trữ cho ít nhất 256 vị trí.

### 8.1. Ví dụ runnable: compact payload khác domain width

Tạo file `BitSetWireFormatDemo.java`:

```java
import java.util.Arrays;
import java.util.BitSet;

public class BitSetWireFormatDemo {
    public static void main(String[] args) {
        BitSet flags = new BitSet(256);

        System.out.println(
                "reserved-length=" + flags.length()
                + " bytes=" + flags.toByteArray().length
                + " space-enough=" + (flags.size() >= 256));

        flags.set(0);
        flags.set(9);
        System.out.println(
                "value=" + Arrays.toString(flags.toByteArray()));
        System.out.println(
                "logical=" + flags.length()
                + " words=" + flags.toLongArray().length);

        flags.clear(9);
        byte[] compact = flags.toByteArray();
        System.out.println(
                "after-clear=" + Arrays.toString(compact)
                + " length=" + flags.length());

        byte[] fixed = Arrays.copyOf(compact, 4);
        System.out.println(
                "fixed=" + Arrays.toString(fixed));
        System.out.println(
                "roundtrip=" + BitSet.valueOf(fixed).equals(flags));

        flags.clear();
        System.out.println(
                "empty-bytes=" + flags.toByteArray().length
                + " logical=" + flags.length());
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all BitSetWireFormatDemo.java
java BitSetWireFormatDemo
```

```text
reserved-length=0 bytes=0 space-enough=true
value=[1, 2]
logical=10 words=1
after-clear=[1] length=1
fixed=[1, 0, 0, 0]
roundtrip=true
empty-bytes=0 logical=0
```

**Diễn giải từng trạng thái:**

1. `new BitSet(256)` chưa có bit true, nên **payload compact rỗng**. Con số `256` không được đưa vào mảng xuất dữ liệu.
2. Bật bit `0` và bit `9` tạo mảng hai byte `[1, 2]`: byte đầu mang bit `0`, byte thứ hai mang bit `9`. `length()==10`, đủ để cần hai byte.
3. `toLongArray().length == 1` vì các bit true hiện tại nằm trong một nhóm 64 bit đầu.
4. Sau khi xóa bit `9`, chỉ bit `0` còn bật: `length()==1` và payload compact chỉ còn `[1]`.
5. `Arrays.copyOf(compact, 4)` tạo **biểu diễn 4 byte cố định do ứng dụng chọn**. `BitSet.valueOf(fixed)` khôi phục đúng các bit true, nhưng không tự lưu “width=32” như một domain property. Nếu protocol thực sự cần width cố định, hãy định nghĩa rõ độ rộng, endian và cách padding.
6. Xóa tất cả khiến `toByteArray()` trả mảng rỗng. Sự tồn tại của vùng lưu trữ bên trong không bắt buộc phải được serialize.

**Quan trọng khi viết protocol:** JavaDoc của `valueOf(byte[])` quy định thứ tự bit cụ thể; bên nhận không phải Java có thể dùng cách đánh số khác. Không dùng `BitSet.toString()` như định dạng wire chính thức nếu cần dữ liệu nhị phân ổn định và có domain width.

### 8.2. Một round-trip có thể mất “ý định độ rộng”

Giả sử hai cấu hình `BitSet` cùng không bật bit nào: một ứng dụng coi nó là một mask 8 bit, ứng dụng khác coi là 1024 bit. Cả hai khi gọi `toByteArray()` đều cho `byte[0]`. Nếu bạn chỉ truyền mảng này, người nhận **không thể biết độ rộng ban đầu**.

Giải pháp:

- Gửi `domainWidth` như một trường metadata riêng trong message hoặc schema.
- Hoặc quy định sẵn chiều dài mask ở API/protocol.
- Hoặc tự encode thành số byte cố định bằng cách padding, nhưng **vẫn phải xác định thứ tự bit và ý nghĩa index**.

`length()` phù hợp để nén theo **bit true cao nhất**, không phù hợp để tái tạo độ rộng ban đầu chứa nhiều bit false ở cuối.

## 9. Equality của BitSet dựa trên bit đã bật, không dựa trên dung lượng

Hai `BitSet` có thể được khởi tạo với các giá trị `nbits` khác nhau nhưng bật **cùng một tập chỉ số**. Chúng biểu diễn cùng trạng thái Boolean và được `BitSet.equals` coi là bằng nhau; khác biệt `size()` không quyết định equality.

Tạo file `BitSetEqualityDemo.java`:

```java
import java.util.BitSet;

public class BitSetEqualityDemo {
    public static void main(String[] args) {
        BitSet small = new BitSet(8);
        BitSet large = new BitSet(4096);

        small.set(2);
        small.set(7);
        large.set(2);
        large.set(7);

        System.out.println(
                "same-bits=" + small.equals(large));
        System.out.println(
                "same-hash="
                + (small.hashCode() == large.hashCode()));
        System.out.println(
                "same-length="
                + (small.length() == large.length()));
        System.out.println(
                "counts=" + small.cardinality()
                + "," + large.cardinality());
        System.out.println(
                "large-space=" + (large.size() >= 4096));

        small.clear(7);
        System.out.println(
                "after-clear-length=" + small.length()
                + " equals=" + small.equals(large));
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all BitSetEqualityDemo.java
java BitSetEqualityDemo
```

```text
same-bits=true
same-hash=true
same-length=true
counts=2,2
large-space=true
after-clear-length=3 equals=false
```

Đoạn này chứng minh:

- `equals` không coi “được khởi tạo với 8 hay 4096 bit không gian” là sự khác biệt giá trị.
- Hai bitset bằng nhau cũng có `hashCode` bằng nhau theo hợp đồng.
- Khi `small.clear(7)`, tập bit true khác `large`; `small.length()` còn `3`, và hai bitset không còn bằng nhau.

**Hệ quả:** Nếu hai mask có cùng bit true nhưng thuộc hai domain khác nhau, `BitSet.equals` vẫn có thể trả true. **Domain width phải tham gia so sánh tại tầng dữ liệu bọc bên ngoài** nếu nghiệp vụ yêu cầu độ rộng là một phần của identity.

Ví dụ về ý nghĩa: mask `{1, 3}` dành cho 8 quyền và mask `{1, 3}` dành cho 64 quyền có giá trị `BitSet` giống nhau, nhưng không nhất thiết tương đương như cấu hình nghiệp vụ nếu vị trí khác nhau có nghĩa riêng.

## 10. Các phép toán bitwise ảnh hưởng length() như thế nào?

`BitSet` hỗ trợ các phép `and`, `or`, `xor`, `andNot`, `flip`. Chúng **thay đổi tập bit true**, nên `length()` và `cardinality()` cũng có thể thay đổi.

| Thao tác | Ý nghĩa | Ảnh hưởng thường gặp |
| --- | --- | --- |
| `a.or(b)` | Hợp những bit true | Có thể tăng `length` nếu `b` có bit cao hơn |
| `a.and(b)` | Chỉ giữ bit true chung | Có thể hạ `length` khi bit cao nhất bị xóa |
| `a.xor(b)` | Bit true ở đúng một bên | Có thể bật hoặc tắt bit cao nhất |
| `a.andNot(b)` | Xóa khỏi `a` những bit true có trong `b` | Có thể giảm `cardinality` và `length` |
| `a.flip(from,to)` | Đảo bit trong một miền hữu hạn | Có thể làm tăng hoặc giảm `length` |

Không có một phép “NOT tất cả bit trong vũ trụ” không giới hạn, vì `BitSet` về mặt logic có **vô hạn bit false** ở các chỉ số chưa bật; đảo vô hạn bit không phải một kết quả hữu hạn. Khi cần phần bù, phải **chọn một độ rộng hợp lệ** rồi `flip(0, domainWidth)`.

Ví dụ minh họa:

```java
BitSet selected = new BitSet();
selected.set(1);
selected.set(3);

BitSet complement = (BitSet) selected.clone();
complement.flip(0, 8);  // Phần bù trong domain [0, 8).
```

Đây là **snippet trong method**, có import `BitSet`. `complement` bật `{0, 2, 4, 5, 6, 7}`. **Không dùng `selected.length()` làm domainWidth** nếu muốn phần bù của cả 8 vị trí: vì `selected.length() == 4`, `flip(0,4)` sẽ bỏ sót bốn vị trí `4..7`.

### 10.1. Clone và mutate đúng đối tượng

Các phép như `and`/`or`/`xor`/`flip` thường **sửa trực tiếp receiver**. Nếu cần giữ input bất biến theo giao diện nghiệp vụ, tạo bản sao `BitSet` trước:

```java
BitSet result = (BitSet) original.clone();
result.and(filter);
```

Đây là **snippet**, `original` và `filter` là `BitSet`. `clone()` tạo bản sao độc lập về tập bit, nhưng không làm object ban đầu bất biến. Đừng dựa vào khác biệt dung lượng `size()` của bản clone để ra quyết định; điều cần duy trì là **các bit true**.

## 11. get() ngoài độ dài logic và kiểm tra index

Một hành vi quan trọng của `BitSet.get(int)`: với **index không âm** vượt quá bit đang bật cao nhất, kết quả bình thường là `false`. Điều đó không có nghĩa index ấy hợp lệ về nghiệp vụ.

Ví dụ:

```java
BitSet flags = new BitSet();
flags.set(3);

boolean inUse = flags.get(1000);  // false, không phải "domain có 1001 slot".
```

Đây là snippet. `get(1000)` trả false vì bit đó chưa được bật; nó không tự mở rộng độ dài logic chỉ bằng cách đọc.

Cần phân biệt các nhóm lỗi:

- `get(-1)`/`set(-1)`: chỉ số âm không hợp lệ, ném `IndexOutOfBoundsException`.
- `set(9999)`: **có thể hợp lệ về mặt BitSet** và yêu cầu mở rộng không gian, dù ứng dụng chỉ cho phép 12 slot.
- `get(9999)`: thường trả false vì bit chưa bật, không tự đánh dấu index có thuộc domain hay không.
- `clear(9999)`: không bảo đảm giảm/tăng domain width; nó chỉ yêu cầu tắt bit ở vị trí đó.
- `set(from,to)` với `from > to`: lỗi chỉ số range theo hợp đồng API; không dùng range âm hoặc đảo ngược.

Vì vậy wrapper như `Months` ở phần 5 **bắt buộc tự validate** index trước khi gọi BitSet, nếu cần một dải hợp lệ cứng.

## 12. Lỗi thường gặp khi nhầm length và size

| Sai lầm | Hậu quả | Thay bằng |
| --- | --- | --- |
| Dùng `bits.size()` làm số lựa chọn nghiệp vụ | Hiển thị nhiều slot “dư” do vùng lưu trữ làm tròn | Dùng `domainWidth` riêng |
| Dùng `bits.length()` để render tất cả checkbox của form cố định | Bỏ qua những slot false cuối form | Lặp đến `domainWidth` |
| Dùng `bits.length()` để đếm số lựa chọn bật | Đếm cả khoảng trống false giữa các bit | Dùng `cardinality()` |
| Cho rằng `new BitSet(100)` có 100 bit true | Thực tế các bit ban đầu đều false | Bật bằng `set` khi cần |
| Cho rằng `new BitSet(100)` cấm `set(100)` | BitSet tự mở rộng, có thể phá schema | Validate index trong wrapper |
| Cho rằng `clear()` làm `size()==0` | `size()` là thuộc tính không gian lưu trữ | Chỉ khẳng định `length()==0`, `cardinality()==0` |
| Serialize bằng `toByteArray()` rồi nghĩ vẫn giữ width | Những byte zero ở cuối bị loại bỏ | Lưu width bằng metadata/schema hoặc padding có quy tắc |
| Coi `size()/8` là RAM sử dụng | Bỏ qua overhead/implementation | Dùng profiler/measurement, không biến thành invariant |
| Tính phần bù bằng `flip(0, bits.length())` | Không đảo bit false ở cuối domain | `flip(0, domainWidth)` |
| Duyệt bit false bằng `nextClearBit` mà không chặn range | Có thể duyệt vượt domain | Kiểm tra `index < domainWidth` |
| Dùng `get(index) == false` để kết luận index hợp lệ | BitSet không biết ràng buộc schema | Validate bounds trước |
| Coi hai bitset khác capacity là khác giá trị | `BitSet.equals` chỉ xét các bit true | So sánh `BitSet` và metadata width riêng nếu cần |

## 13. Khi nào BitSet phù hợp, khi nào cần cấu trúc khác?

**Hợp lý với BitSet khi:**

- Mỗi chỉ số không âm tương ứng một flag Boolean.
- Nhiều thao tác bitwise hoặc membership trên một miền index tương đối gọn.
- Cần duyệt tập chỉ số đang bật bằng `nextSetBit()`/`stream()`.
- Có thể quản lý domain width/bounds bằng logic ứng dụng nếu cần fixed-size semantics.

**Cân nhắc lựa chọn khác khi:**

- Muốn **độ dài cố định** là bất biến của object: dùng `boolean[]` hoặc một wrapper lưu `width` và `BitSet`.
- Flags là một tập hằng có tên: `EnumSet<E>` thường dễ đọc, cho type safety và tránh off-by-one khi mapping index.
- Chỉ một vài chỉ số rất lớn được bật: `BitSet` vẫn cần biểu diễn không gian đến vùng chỉ số cao, nên `Set<Integer>` hoặc cấu trúc sparse chuyên dụng có thể phù hợp hơn.
- Cần serialized format có schema cứng: tự định nghĩa encoding, version, width và bit ordering; không coi layout nội bộ `BitSet` là wire protocol.

**Về hiệu suất:** không nên suy từ `cardinality()==1` rằng bộ nhớ dùng luôn rất ít. Nếu bit true duy nhất có index rất lớn, `BitSet` có thể cần vùng lưu trữ lớn để chứa nó. Ngược lại, `length()` lớn không tự nói có bao nhiêu bit true. Hãy đo với dữ liệu thật và chọn cấu trúc thích hợp.

**Về thread safety:** `BitSet` là mutable, không bảo đảm thread-safe nếu nhiều thread truy cập/chỉnh sửa đồng thời mà không có đồng bộ thích hợp. Một phép `size()` hoặc `length()` đơn lẻ cũng không tạo snapshot nguyên tử của toàn bộ trạng thái đang bị sửa. Khi cần chia sẻ giữa threads, dùng synchronization/ownership rõ hoặc copy dữ liệu trước khi phân tích.

## 14. Checklist khi review code dùng BitSet

1. **Xác định domain:** có phải mọi index không âm đều hợp lệ, hay chỉ `0..width-1`?
2. **Xác định ý nghĩa câu hỏi:** cần bit cao nhất, số bit true hay kích thước nghiệp vụ?
3. **Kiểm tra chỗ gọi `length()`:** có nhầm thành fixed width hoặc số lượng bit bật không?
4. **Kiểm tra chỗ gọi `size()`:** có vô tình coi thuộc tính implementation thành hợp đồng API hoặc protocol không?
5. **Kiểm tra `cardinality()`:** nếu cần đếm bit true, đây thường là lựa chọn đúng.
6. **Kiểm tra index/range:** mapping zero-based, giới hạn index, range end-exclusive và trường hợp âm.
7. **Kiểm tra các đường clear/flip:** xóa bit cao nhất có thể làm `length` giảm bất ngờ; có test trường hợp bitset rỗng không?
8. **Kiểm tra serialize/deserialize:** có bảo toàn domain width, endian và trailing zero semantics không?
9. **Kiểm tra equality:** nếu domain là phần của value semantics, có so sánh metadata width ngoài `BitSet.equals` không?
10. **Kiểm tra duyệt các bit:** đang muốn lặp các bit true hay lặp mọi slot? Có chặn `nextClearBit` bằng width không?
11. **Kiểm tra bộ nhớ:** có nhận chỉ số từ input không đáng tin gây cấp phát cực lớn không?
12. **Kiểm tra concurrency:** có nhiều thread mutate cùng một BitSet mà không có khóa hoặc snapshot không?

## 15. Bài thực hành

**Bài 1 — Ba đại lượng:** chạy `BitSetDimensionsDemo`. Dự đoán `length`, `cardinality` và điều kiện `size() >= length()` tại từng bước. Thử `set(10000)` trên tập rỗng và giải thích tại sao count bằng 1 nhưng logical length lớn.

**Bài 2 — Thay đổi bit cao nhất:** chạy `BitSetMutationsDemo`, thay `clear(63)` bằng `clear(7)`. Vì sao `cardinality` giảm mà `length` vẫn bằng `64`? Thử xóa cả hai rồi bật bit thấp.

**Bài 3 — Fixed width:** chạy `FixedWidthBitSetDemo`. Thêm method `clearAll()` vẫn giữ `WIDTH=12`; thử format 12 ký tự dù tất cả bit false. Viết test kiểm tra tháng 0 và 13 đều bị từ chối.

**Bài 4 — Format byte:** chạy `BitSetWireFormatDemo`, thử `set(16)` rồi quan sát số byte. Giải thích vì sao clear bit 16 làm payload gọn lại và vì sao bên nhận không thể tự biết cần bao nhiêu trailing zero slots.

**Bài 5 — Equality:** chạy `BitSetEqualityDemo`. Thử tạo hai bitset có cùng bit true nhưng khởi tạo dung lượng khác nhau; kiểm tra `equals` và `hashCode`. Thiết kế record `Mask(int width, BitSet bits)` có defensive copy và chính sách equality bao gồm width.

**Bài 6 — Duyệt indices:** chạy `BitSetIterationDemo`; so sánh `stream()` với `nextSetBit()`. Với domain 12 slot, hãy viết method liệt kê mọi slot còn false mà không đi quá `11`.

**Bài 7 — Chọn cấu trúc:** một ứng dụng có 3 triệu ID nhưng chỉ 100 ID rất lớn được chọn. So sánh lượng không gian theo bit true cao nhất với số ID được chọn để quyết định nên dùng `BitSet` hay một cấu trúc sparse.

**Bài 8 — Review lỗi:** tìm và sửa đoạn code dùng `for (int i=0; i<flags.size(); i++)` để hiển thị 24 quyền. Thêm kiểm thử khi quyền cuối cùng không được bật và khi BitSet được khởi tạo với nhiều không gian hơn 24.

## 16. Ghi nhớ

- **`length()`** = vị trí bit true cao nhất + 1; không có bit true thì bằng 0.
- **`cardinality()`** = số bit true; đây là cách đếm các cờ đang được bật.
- **`size()`** = không gian lưu trữ mà implementation hiện có để biểu diễn bit; **không phải** độ dài logic, số phần tử hay dung lượng domain cố định.
- **`new BitSet(nbits)`** chuẩn bị không gian, **không bật bit** và không đặt trần chỉ số.
- **Xóa bit cao nhất** có thể hạ `length()`, nhưng không nói được điều gì chắc chắn về việc thu hồi toàn bộ không gian lưu trữ.
- **Nếu domain cố định**, giữ `width`/`domainSize` riêng, tự validate index và dùng width khi format, duyệt slot hay truyền dữ liệu.
- **`toByteArray()/toLongArray()`** cho biểu diễn gọn theo các bit có ý nghĩa; không tự giữ các trailing zero slots hoặc domain width.
- **`BitSet.equals`** so sánh tập bit true, không so dung lượng đã được yêu cầu ở constructor.
- **`nextSetBit()/stream()`** duyệt bit true; muốn duyệt bit false hoặc toàn bộ slot phải có miền hữu hạn rõ ràng.
- Mọi nguyên tắc trên **vẫn áp dụng trên Java 17+**; không dựa vào chi tiết bố trí word nội bộ, đoán trước RAM hoặc cơ chế cleanup không được API cam kết.

## Tài liệu chính thức

- [BitSet — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/BitSet.html): `length()`, `size()`, `cardinality()`, constructors, `set`/`clear`/`flip`, stream, mảng byte/long và equality.
- [Arrays — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Arrays.html): `copyOf` khi cần padding payload theo định dạng ứng dụng.
- [EnumSet — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/EnumSet.html): lựa chọn phù hợp cho tập cờ dựa trên enum có tên.
