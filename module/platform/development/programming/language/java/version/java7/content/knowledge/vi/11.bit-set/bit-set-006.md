# Tìm bit theo chiều ngược bằng `BitSet.previousSetBit` và `previousClearBit` trong Java

## 1. Bài toán và kết quả cần đạt

`java.util.BitSet` biểu diễn một tập hợp các bit có chỉ số **không âm**: mỗi bit ở trạng thái `true` (*set*, bằng 1) hoặc `false` (*clear*, bằng 0). Các vị trí bit thường đại diện cho slot đã sử dụng, quyền được bật, trạng thái hoàn tất hoặc một tập chỉ số rời rạc. Khi muốn tìm trạng thái gần nhất **ở bên trái** một mốc, duyệt từng chỉ số bằng `get(i)` không phải lúc nào cũng là cách rõ ràng nhất.

Hai phương thức được thiết kế cho tìm kiếm ngược là:

~~~java
int setIndex = bits.previousSetBit(fromIndex);
int clearIndex = bits.previousClearBit(fromIndex);
~~~

Đây là đoạn minh họa cú pháp, giả sử `bits` là một `BitSet` đã khởi tạo và `fromIndex` là chỉ số tìm kiếm.

- `previousSetBit(fromIndex)`: tìm chỉ số **lớn nhất, không vượt quá `fromIndex`**, có bit bằng `true`; không tìm thấy thì trả `-1`.
- `previousClearBit(fromIndex)`: tìm chỉ số **lớn nhất, không vượt quá `fromIndex`**, có bit bằng `false`; không tìm thấy trong tiền tố cần xét thì trả `-1`.

Cả hai tìm **ngược theo chỉ số giảm dần** và **bao gồm chính `fromIndex`**; chúng chỉ truy vấn, **không thay đổi bit**.

**Mục tiêu học tập:** xác định chính xác các giá trị trả về, phân biệt bit set/clear và phạm vi logic của ứng dụng, viết vòng lặp duyệt ngược an toàn, xử lý `-1`/đầu vào âm, và sử dụng hàm tìm vị trí trống trong một miền hữu hạn.

**Phiên bản:** `previousSetBit` và `previousClearBit` xuất hiện từ Java 7 và vẫn là API chuẩn của `BitSet` trên JDK hiện đại. Ví dụ được **biên dịch và chạy bằng Java 21**, không yêu cầu JDK cũ hay kỹ thuật đã legacy.

## 2. Ngữ nghĩa chính xác và cách đọc tên phương thức

| Phương thức | Bit cần tìm | Chiều tìm | Mốc đầu vào có được xét? | Khi không tìm thấy |
| --- | --- | --- | --- | --- |
| `previousSetBit(k)` | `true` / 1 | Từ `k` về 0 | **Có** | `-1` |
| `previousClearBit(k)` | `false` / 0 | Từ `k` về 0 | **Có** | `-1` |
| `nextSetBit(k)` (đối chiếu) | `true` / 1 | Từ `k` tới chỉ số tăng dần | **Có** | `-1` |
| `nextClearBit(k)` (đối chiếu) | `false` / 0 | Từ `k` tới chỉ số tăng dần | **Có** | Với mốc hợp lệ, có thể tìm ở vị trí cao hơn vì các bit chưa set mặc định bằng false |

Trong bài này, hai hàm **`previous...`** là trọng tâm; hai hàm `next...` chỉ dùng để phân biệt hướng tìm kiếm. Đối số là **vị trí bắt đầu**, không phải số phần tử, độ dài hay một khoảng bắt đầu-kết thúc.

Với `k >= 0`, có thể hình dung:

~~~text
previousSetBit(k)   = chỉ số lớn nhất i trong [0, k] mà bits.get(i) == true
previousClearBit(k) = chỉ số lớn nhất i trong [0, k] mà bits.get(i) == false
~~~

Đây là **mô tả toán học**, không phải lệnh Java có thể chạy. Hai phép tìm trả về **chỉ số**, không trả về boolean. Nếu muốn biết bit tại một vị trí, dùng `bits.get(index)`.

### 2.1. Ví dụ trực quan

Giả sử chỉ các chỉ số `0, 3, 7, 10` đang được set:

~~~text
Chỉ số:    0  1  2  3  4  5  6  7  8  9 10 11
Trạng thái: 1  0  0  1  0  0  0  1  0  0  1  0
                                      ^    ^
                         previous... từ 10
~~~

- `previousSetBit(10) == 10`: bit tại mốc 10 đang set; trả về **chính 10**.
- `previousClearBit(10) == 9`: bit tại mốc 10 đang set; bit clear gần nhất bên trái ở 9.
- `previousSetBit(9) == 7`: bit set gần nhất không vượt quá 9 nằm ở 7.
- `previousClearBit(3) == 2`: mốc 3 đang set, nên tìm tiếp về 2.
- `previousSetBit(2) == 0`: bỏ qua các bit clear ở 2 và 1.
- `previousClearBit(1) == 1`: bit tại mốc 1 **đã clear**, trả ngay 1.
- `previousClearBit(0) == -1`: duy nhất bit 0 trong miền `[0,0]` đang set, nên không có bit clear nào trong miền đó.

Mô hình hữu ích nhất là: **bắt đầu ngay tại mốc, tìm lùi, dừng ở bit thỏa điều kiện đầu tiên**.

## 3. Một khác biệt đặc biệt: bit clear tồn tại ngoài phần đã set

`BitSet` không phải một mảng boolean có độ dài cố định do ứng dụng cấp sẵn. Theo hợp đồng `BitSet`, các chỉ số chưa được đặt thành `true` mặc định đều được coi là **`false`**. Vì vậy:

~~~java
BitSet bits = new BitSet();
bits.set(10);

// Bit 100 đang clear mặc dù vượt xa bit set cao nhất.
int result = bits.previousClearBit(100); // 100
~~~

Đây là đoạn Java minh họa (cần import `java.util.BitSet`). Mốc 100 hợp lệ, và bit tại 100 đang clear; `previousClearBit(100)` trả **100**, **không** tự động giới hạn kết quả trong `[0, bits.length())`.

Ngược lại, `previousSetBit(100)` với dữ liệu này trả **10**, vì bit set cao nhất là 10. Nếu `BitSet` chưa có bit set nào:

~~~java
BitSet empty = new BitSet();

int lastSet = empty.previousSetBit(6);     // -1
int lastClear = empty.previousClearBit(6); // 6
~~~

Không có bit set nên kết quả tìm set là `-1`. Còn bit 6 tự nó đang clear nên kết quả tìm clear là `6`.

**Hệ quả quan trọng:** `previousClearBit(k)` không trả về “vị trí trống lớn nhất trong danh sách công việc của tôi” trừ khi **bạn đã xác định rõ `k` là cận trên của danh sách đó**. Nếu miền slot hợp lệ là `0..9`, hãy tìm từ `9`; nếu tìm từ `100`, Java có thể trả 100 dù ứng dụng chỉ có 10 slot.

### 3.1. `length()` và `size()` không phải giới hạn nghiệp vụ

- `bits.length()` là **chỉ số bit set cao nhất cộng 1**; nếu không có bit set, trả 0. Nó không biểu diễn số slot mà ứng dụng đã đăng ký.
- `bits.cardinality()` là **số bit set**, không phải vị trí bit set cuối cùng. Với các bit set `{0,3,7,10}`, `cardinality() == 4` nhưng `length() == 11`.
- `bits.size()` thể hiện **dung lượng lưu trữ nội bộ tính theo bit** ở thời điểm gọi, không phải cận trên của dữ liệu nghiệp vụ; `BitSet` có thể tăng dung lượng theo nhu cầu.
- `BitSet` về mặt khái niệm có các bit clear ở mọi vị trí không âm chưa set. Đừng xem vùng chưa cấp phát từ bộ nhớ là “không tồn tại” chỉ vì `size()` nhỏ.

Muốn tìm slot trống trong miền `[0, count - 1]`, cần biết `count` từ nghiệp vụ, không đoán từ `length()`/`size()`.

## 4. Chương trình Java 21 hoàn chỉnh — biên dịch, chạy và quan sát

Tạo file `src/main/java/demo/ReverseBitSetExample.java`:

~~~java
package demo;

import java.util.ArrayList;
import java.util.BitSet;
import java.util.List;

public final class ReverseBitSetExample {
    private ReverseBitSetExample() {}

    static List<Integer> collectSetDescending(BitSet bits) {
        List<Integer> indexes = new ArrayList<>();
        for (int i = bits.previousSetBit(bits.length() - 1);
                i >= 0;
                i = bits.previousSetBit(i - 1)) {
            indexes.add(i);
        }
        return indexes;
    }

    static List<Integer> collectClearDescending(BitSet bits, int upperInclusive) {
        if (upperInclusive < 0) {
            throw new IllegalArgumentException("upperInclusive must be >= 0");
        }
        List<Integer> indexes = new ArrayList<>();
        for (int i = bits.previousClearBit(upperInclusive);
                i >= 0;
                i = bits.previousClearBit(i - 1)) {
            indexes.add(i);
        }
        return indexes;
    }

    public static void main(String[] args) {
        BitSet bits = new BitSet();
        bits.set(0);
        bits.set(3);
        bits.set(7);
        bits.set(10);

        System.out.println("bits=" + bits);
        System.out.println("previousSetBit(9)=" + bits.previousSetBit(9));
        System.out.println("previousSetBit(10)=" + bits.previousSetBit(10));
        System.out.println("previousSetBit(2)=" + bits.previousSetBit(2));
        System.out.println("previousSetBit(100)=" + bits.previousSetBit(100));
        System.out.println("previousSetBit(-1)=" + bits.previousSetBit(-1));

        System.out.println("previousClearBit(10)=" + bits.previousClearBit(10));
        System.out.println("previousClearBit(3)=" + bits.previousClearBit(3));
        System.out.println("previousClearBit(1)=" + bits.previousClearBit(1));
        System.out.println("previousClearBit(0)=" + bits.previousClearBit(0));
        System.out.println("previousClearBit(11)=" + bits.previousClearBit(11));
        System.out.println("previousClearBit(100)=" + bits.previousClearBit(100));
        System.out.println("previousClearBit(-1)=" + bits.previousClearBit(-1));

        System.out.println("setDescending=" + collectSetDescending(bits));
        System.out.println("clearDescending(10)="
                + collectClearDescending(bits, 10));

        BitSet fullPrefix = new BitSet();
        fullPrefix.set(0, 5);
        System.out.println("fullPrefix=" + fullPrefix);
        System.out.println("fullPreviousClear(4)="
                + fullPrefix.previousClearBit(4));
        System.out.println("fullPreviousClear(5)="
                + fullPrefix.previousClearBit(5));

        BitSet empty = new BitSet();
        System.out.println("emptySet(6)=" + empty.previousSetBit(6));
        System.out.println("emptyClear(6)=" + empty.previousClearBit(6));
        System.out.println("maxClear="
                + bits.previousClearBit(Integer.MAX_VALUE));

        try {
            bits.previousSetBit(-2);
        } catch (IndexOutOfBoundsException ex) {
            System.out.println("previousSetBit(-2)=IndexOutOfBoundsException");
        }
        try {
            bits.previousClearBit(-2);
        } catch (IndexOutOfBoundsException ex) {
            System.out.println("previousClearBit(-2)=IndexOutOfBoundsException");
        }
    }
}
~~~

Trong thư mục chứa `src/`, dùng JDK hỗ trợ biên dịch ở mức Java 21:

~~~sh
javac --release 21 -encoding UTF-8 -Xlint:all -d out src/main/java/demo/ReverseBitSetExample.java
java -cp out demo.ReverseBitSetExample
~~~

**Stdout chính xác** (đã kiểm thử):

~~~text
bits={0, 3, 7, 10}
previousSetBit(9)=7
previousSetBit(10)=10
previousSetBit(2)=0
previousSetBit(100)=10
previousSetBit(-1)=-1
previousClearBit(10)=9
previousClearBit(3)=2
previousClearBit(1)=1
previousClearBit(0)=-1
previousClearBit(11)=11
previousClearBit(100)=100
previousClearBit(-1)=-1
setDescending=[10, 7, 3, 0]
clearDescending(10)=[9, 8, 6, 5, 4, 2, 1]
fullPrefix={0, 1, 2, 3, 4}
fullPreviousClear(4)=-1
fullPreviousClear(5)=5
emptySet(6)=-1
emptyClear(6)=6
maxClear=2147483647
previousSetBit(-2)=IndexOutOfBoundsException
previousClearBit(-2)=IndexOutOfBoundsException
~~~

### Đọc kết quả theo nhóm

**Nhóm tìm bit set.** Với `{0,3,7,10}`, tìm từ 9 gặp 7; tìm từ 10 gặp 10; tìm từ 2 gặp 0. Tìm từ 100 vẫn gặp 10, vì không có bit set cao hơn. Tìm từ `-1` trả `-1` — đây là một trường hợp sentinel được Java hỗ trợ có chủ đích.

**Nhóm tìm bit clear.** `previousClearBit(10)` trả 9 vì mốc 10 set; `previousClearBit(1)` trả ngay 1; `previousClearBit(0)` trả `-1` vì bit 0 set và không có chỉ số thấp hơn 0 hợp lệ. Khi tìm từ 11 hoặc 100, kết quả chính là mốc vì các bit đó chưa set.

**Duyệt ngược.** `collectSetDescending` chỉ ghé các bit set nên thu được `[10, 7, 3, 0]`. `collectClearDescending(bits, 10)` quét các bit clear trong miền 0..10 và trả `[9, 8, 6, 5, 4, 2, 1]`. Hai phương thức không thay đổi dữ liệu đầu vào.

**Tiền tố được set đầy đủ.** `fullPrefix.set(0, 5)` đặt các bit **0,1,2,3,4** thành true vì tham số kết thúc của `set(fromIndex, toIndex)` là **exclusive**. Tìm clear từ 4 trả `-1`, nhưng tìm clear từ 5 trả 5: bit 5 nằm ngoài tiền tố set và mặc định clear.

**BitSet rỗng và chỉ số cực đại.** Không có set bit, nhưng vẫn có clear bit tại 6. `previousClearBit(Integer.MAX_VALUE)` trả chính `2147483647` vì vị trí đó đang clear. Ví dụ chỉ **truy vấn một lần**, không cố liệt kê mọi vị trí clear xuống 0.

**Tham số âm.** `-1` là sentinel hợp lệ với hai phương thức. `-2` thì gây `IndexOutOfBoundsException`. Điều này không giống với `BitSet.get(-1)`, `set(-1)` hoặc `clear(-1)`, vốn không nhận `-1` làm giá trị sentinel.

## 5. Duyệt bit set theo chiều ngược an toàn

Một mẫu duyệt thường gặp:

~~~java
for (int i = bits.previousSetBit(bits.length() - 1);
        i >= 0;
        i = bits.previousSetBit(i - 1)) {
    System.out.println(i);
}
~~~

Đây là **đoạn minh họa trong ngữ cảnh có biến `BitSet bits`**.

**Vì sao mẫu này an toàn?**

1. `bits.length() - 1` là bit set cao nhất, nếu BitSet không rỗng.
2. Nếu BitSet rỗng, `bits.length() == 0`, nên tìm từ `-1` và nhận kết quả `-1`; vòng lặp không vào thân.
3. Điều kiện `i >= 0` ngăn xử lý sentinel như chỉ số hợp lệ.
4. Mỗi vòng dùng `i - 1` để **không lấy lại chính bit vừa tìm**. Nếu dùng `previousSetBit(i)`, vì tìm kiếm bao gồm mốc, vòng lặp có thể không tiến lên và bị lặp vô hạn.
5. Khi `i == 0`, `i - 1 == -1`. `previousSetBit(-1)` trả `-1`, kết thúc vòng lặp sạch mà không cần một nhánh đặc biệt.

**Lưu ý:** mẫu vòng lặp này giả định `bits` **không bị sửa trong khi duyệt**. `BitSet` là mutable và không tự đồng bộ cho các thao tác cạnh tranh. Khi xử lý dữ liệu có nhiều luồng, dùng snapshot/cơ chế đồng bộ phù hợp; đừng dựa vào việc tập bit giữ nguyên nếu luồng khác có thể gọi `set`/`clear`.

### 5.1. Bắt đầu từ một cận trên cụ thể

Không phải lúc nào ta cũng muốn tìm từ bit set cao nhất. Nếu bài toán chỉ xem các bit `0..maxIndex`:

~~~java
for (int i = bits.previousSetBit(maxIndex);
        i >= 0;
        i = bits.previousSetBit(i - 1)) {
    consume(i);
}
~~~

Đoạn minh họa này cần định nghĩa `maxIndex >= 0`, `bits` và `consume`. Nó bỏ qua mọi set bit có chỉ số cao hơn `maxIndex` mà không cần xóa chúng.

Nếu chỉ muốn miền `[lowerInclusive, upperInclusive]`, thêm điều kiện dừng:

~~~java
for (int i = bits.previousSetBit(upperInclusive);
        i >= lowerInclusive;
        i = bits.previousSetBit(i - 1)) {
    consume(i);
}
~~~

Cần xác thực `0 <= lowerInclusive <= upperInclusive` trước khi duyệt. Vòng lặp dừng khi kết quả nhỏ hơn cận dưới hoặc là `-1`. Cận trên và cận dưới ở đây đều **inclusive** theo thiết kế bài toán.

## 6. Duyệt bit clear theo chiều ngược: phải chọn **phạm vi hữu hạn**

Vòng lặp tìm các vị trí trống có dạng:

~~~java
for (int i = bits.previousClearBit(upperInclusive);
        i >= 0;
        i = bits.previousClearBit(i - 1)) {
    System.out.println(i);
}
~~~

Đoạn minh họa này yêu cầu `upperInclusive >= 0`. Khác với duyệt bit set bằng `bits.length() - 1`, duyệt clear phải dựa vào **cận trên do nghiệp vụ cung cấp**, ví dụ `slotCount - 1`.

Nếu bạn viết `previousClearBit(Integer.MAX_VALUE)` để “tìm slot trống gần nhất” mà không có giới hạn, phương thức có thể trả một chỉ số **rất lớn và hoàn toàn ngoài phạm vi nghiệp vụ**. Vòng lặp tiếp tục giảm chỉ số trong một không gian bit rộng vô nghĩa, có thể tốn nhiều tài nguyên và thời gian.

### 6.1. Tìm một vị trí trống cuối cùng trong danh sách slot

Giả sử `occupied` đánh dấu slot đã dùng, và có `slotCount` slot hợp lệ đánh số 0..`slotCount - 1`. Ta muốn tìm slot trống **gần phía cuối nhất**:

~~~java
static int lastFreeSlot(BitSet occupied, int slotCount) {
    if (slotCount < 0) {
        throw new IllegalArgumentException("slotCount must be >= 0");
    }
    if (slotCount == 0) {
        return -1;
    }
    return occupied.previousClearBit(slotCount - 1);
}
~~~

Đây là **phương thức có thể biên dịch khi đặt trong lớp có import `java.util.BitSet`**. Kết quả:

- Nếu mọi slot `0..slotCount-1` đều occupied, trả `-1`.
- Nếu slot cuối cùng trống, trả `slotCount - 1`.
- Nếu slot cuối cùng đã dùng, tìm lùi tới slot trống gần nhất.
- Nếu `slotCount == 0`, trả `-1`, không gọi tìm từ một miền không tồn tại.
- Nếu `slotCount < 0`, báo lỗi đầu vào, không âm thầm coi là một miền rỗng.
- Các bit đang set có chỉ số **ngoài miền slot** không ảnh hưởng kết quả vì mốc tìm đã được giới hạn.

Đây là ví dụ ứng dụng hữu ích hơn việc gọi `previousClearBit(bits.length() - 1)`: độ dài logic của tập slot và vị trí bit set cao nhất là hai khái niệm có thể khác nhau.

### 6.2. Tìm trong một khoảng bất kỳ

Nếu chỉ được chọn vị trí từ `lowerInclusive` đến `upperInclusive`:

~~~java
static int lastClearInRange(
        BitSet bits, int lowerInclusive, int upperInclusive) {
    if (lowerInclusive < 0 || upperInclusive < lowerInclusive) {
        throw new IllegalArgumentException("invalid range");
    }
    int found = bits.previousClearBit(upperInclusive);
    return found >= lowerInclusive ? found : -1;
}
~~~

Đây là **phương thức minh họa**. Điều kiện trả `found >= lowerInclusive` ngăn kết quả nằm bên trái miền được phép. Với `previousSetBit`, chỉ cần thay lời gọi tương ứng để tìm bit đang set:

~~~java
int found = bits.previousSetBit(upperInclusive);
return found >= lowerInclusive ? found : -1;
~~~

Hai dòng cuối là một **đoạn minh họa bên trong helper tương ứng**, không phải toàn bộ phương thức thứ hai. Nếu dùng `-1` để biểu thị “không thấy”, hãy ghi rõ vì 0 là chỉ số hoàn toàn hợp lệ.

## 7. Phân biệt `-1` là kết quả tìm kiếm và đầu vào hợp lệ

Cả `previousSetBit` và `previousClearBit` đều có xử lý đặc biệt với tham số âm:

| Giá trị `fromIndex` | Hành vi |
| --- | --- |
| `>= 0` | Tìm từ chỉ số này, bao gồm chính chỉ số đó |
| `-1` | Trả ngay `-1` |
| `< -1` | Ném `IndexOutOfBoundsException` |

Đây là một khác biệt với nhiều phương thức chỉ số của `BitSet` như `get`, `set` và `clear`, vốn yêu cầu chỉ số không âm. Phân biệt quy tắc riêng của từng API thay vì cho rằng toàn bộ `BitSet` cho phép `-1`.

Vì sao `-1` có ích? Khi vòng lặp đang ở chỉ số 0, biểu thức `i - 1` trở thành `-1`. Phương thức trả lại sentinel và vòng lặp kết thúc tự nhiên.

Tuy nhiên, nếu chỉ số xuất phát được tính từ dữ liệu không tin cậy, **đừng chuyển mọi số âm thành “không tìm thấy”**. `-2`, `-3` và các giá trị nhỏ hơn có thể biểu thị lỗi logic; hãy kiểm tra giới hạn đầu vào nếu chúng được tính từ kích thước, phân đoạn hoặc vị trí của người dùng.

**Bẫy trừ chỉ số:** khi một helper nhận `slotCount` và gọi `previousClearBit(slotCount - 1)`, cần xử lý riêng `slotCount == 0`, vì không có slot hợp lệ. Với đếm số slot âm, phải từ chối thay vì dựa vào xử lý sentinel.

## 8. So sánh với vòng lặp `get(i)` và API duyệt khác

Có thể tự viết tìm kiếm ngược theo từng chỉ số:

~~~java
int found = -1;
for (int i = fromIndex; i >= 0; i--) {
    if (bits.get(i)) {
        found = i;
        break;
    }
}
~~~

Đây là đoạn minh họa tìm **bit set** với `fromIndex >= 0`. Nó kiểm tra từng chỉ số, có thể bao gồm nhiều vị trí clear liên tiếp.

Trong khi đó:

~~~java
int found = bits.previousSetBit(fromIndex);
~~~

diễn đạt trực tiếp mục tiêu tìm kiếm và để `BitSet` xử lý biểu diễn bit nội bộ. Với bit set thưa, duyệt bằng các phương thức tìm vị trí có thể tránh việc viết code ứng dụng kiểm tra từng chỉ số. **Không hứa hẹn một độ phức tạp cụ thể không được Javadoc cam kết**; benchmark nếu bạn cần tối ưu một workload đặc thù.

### 8.1. Khi nào dùng `nextSetBit`, `nextClearBit`?

- Duyệt **tăng dần**, muốn tìm về phía chỉ số lớn hơn: dùng `nextSetBit` hoặc `nextClearBit`.
- Duyệt **giảm dần**, muốn tìm về phía chỉ số nhỏ hơn: dùng `previousSetBit` hoặc `previousClearBit`.
- Cần tất cả chỉ số set có thể dùng `BitSet.stream()` trên Java hiện đại, nhưng `stream()` đưa các bit set theo **thứ tự tăng dần**, không thay thế trực tiếp vòng lặp tìm ngược khi cần dừng sớm từ cận trên.
- Muốn hỏi trạng thái của **một** chỉ số, dùng `get(i)`; không cần một tìm kiếm ngược.

Đừng dùng `previousClearBit` để “bật” hoặc “tắt” bit. Nó chỉ tìm kiếm. Khi cần sửa trạng thái, dùng `set`, `clear` hoặc `flip` ở vị trí phù hợp sau khi đã kiểm tra miền nghiệp vụ.

## 9. Những tình huống cần chú ý khi dữ liệu thay đổi

### 9.1. BitSet không tự mang giới hạn chỉ số của bài toán

Trong ứng dụng quản lý 16 slot, `BitSet` có thể có dung lượng lưu trữ lớn hơn 16 và có các bit clear ở vị trí rất xa. Cần giữ `slotCount` hoặc `upperInclusive` riêng nếu muốn tìm vị trí còn trống. Đừng dùng `size()` thay cho số slot, và đừng nghĩ `previousClearBit(999)` sẽ tự giới hạn trong 16 slot.

### 9.2. BitSet rỗng

Một `BitSet` rỗng có `length() == 0` và `previousSetBit(k) == -1` cho mọi `k >= 0`. Trong khi đó, `previousClearBit(k) == k` với `k >= 0`. Việc ứng dụng coi “không có slot nào tồn tại” hay “mọi slot chưa sử dụng” là quyết định **ngoài BitSet**.

### 9.3. Dữ liệu đầy trong một tiền tố

Nếu tất cả bit `0..4` đều set, `previousClearBit(4) == -1`; nhưng `previousClearBit(5) == 5`. Hàm không nói “không còn bit clear ở bất kỳ đâu”, mà nói **không còn bit clear trong miền từ chỉ số mốc trở xuống**.

### 9.4. Nhiều luồng và trạng thái nhất quán

`BitSet` là mutable; các phương thức tìm kiếm không tự biến thao tác “tìm rồi đánh dấu” thành một **giao dịch nguyên tử**. Ví dụ, hai luồng cùng làm:

~~~java
int free = occupied.previousClearBit(lastSlot);
if (free >= 0) {
    occupied.set(free);
}
~~~

Đây là **đoạn minh họa không đồng bộ**. Hai luồng có thể cùng thấy một slot trống trước khi một trong hai set bit. Nếu cần cấp phát slot duy nhất, bảo vệ thao tác tìm-và-đánh-dấu bằng khóa, cơ chế đồng bộ thích hợp hoặc một thiết kế concurrency-safe khác. Không dựa vào `BitSet` như một bộ cấp phát slot thread-safe mặc định.

### 9.5. Đầu vào quá lớn

`previousSetBit(Integer.MAX_VALUE)` có thể tìm bit set gần nhất nếu có; `previousClearBit(Integer.MAX_VALUE)` có thể trả chính `Integer.MAX_VALUE` khi bit đó clear. Nhưng việc dùng chỉ số cực lớn để **khởi tạo hoặc set bit ở vị trí đó** có thể tạo nhu cầu bộ nhớ rất lớn. Truy vấn clear và cấp phát bit mới là hai thao tác khác nhau.

Không biến kết quả cao bất thường thành thao tác `set(...)` nếu không xác thực giới hạn nghiệp vụ và ngân sách tài nguyên.

## 10. Sai lầm phổ biến

| Sai lầm | Hệ quả | Cách làm đúng |
| --- | --- | --- |
| Nghĩ `previousSetBit(k)` luôn bắt đầu tại `k-1` | Bỏ sót bit đang set ngay tại mốc | Nhớ **bao gồm `k`** |
| Nghĩ `previousClearBit(k)` chỉ tìm trong `length()` | Có thể nhận chỉ số vượt vùng set cao nhất | Dùng cận trên **do ứng dụng xác định** |
| Tăng hoặc giữ nguyên mốc sau một lần tìm | Lặp lại chính bit vừa tìm | Dùng `i - 1` khi cần duyệt sang bên trái |
| Viết `while (i > 0)` | Bỏ sót bit ở vị trí 0 | Dùng `i >= 0` và sentinel `-1` |
| Dùng `size()` để xác định số slot | Lẫn dung lượng nội bộ với miền dữ liệu | Giữ `slotCount` riêng |
| Dùng `cardinality()` làm chỉ số bit cuối | Sai khi bit set rời rạc | Dùng `length()-1` cho set bit cuối, hoặc cận nghiệp vụ |
| Cho rằng `-1` luôn là lỗi đầu vào | Không hiểu vòng lặp duyệt ngược hợp lệ | `-1` trả `-1`; chỉ nhỏ hơn `-1` mới bị từ chối |
| Dùng `previousClearBit` mà không ràng buộc miền trống hợp lệ | Chọn chỉ số quá xa hoặc làm vòng lặp vô nghĩa | Xác thực `upperInclusive`/`slotCount` |
| Quên rằng tìm kiếm không tự set/clear bit | Slot trống có thể bị chọn lại | Nếu cần cấp phát, thực hiện `set` trong vùng đồng bộ đúng |
| Cho rằng kết quả là boolean | Dùng sai điều kiện tìm thấy | Kiểm tra `index >= 0` trước khi sử dụng |
| Dùng `BitSet` đồng thời từ nhiều luồng không có bảo vệ | Có thể không nhất quán hoặc cấp phát trùng | Dùng đồng bộ hóa hoặc cấu trúc khác phù hợp |

## 11. Bài tập tự kiểm tra

**Bài 1.** Một `BitSet` có bit set ở `{2, 5, 9}`. `previousSetBit(8)` trả gì? `previousSetBit(9)` trả gì?

**Đáp án:** Từ 8, bit set gần nhất là 5 nên trả `5`. Từ 9, bit 9 đang set nên trả `9`.

**Bài 2.** Cùng dữ liệu `{2, 5, 9}`, `previousClearBit(9)` và `previousClearBit(6)` trả gì?

**Đáp án:** Từ 9, bit 9 set, bit 8 clear nên trả `8`. Từ 6, bit 6 clear nên trả `6`.

**Bài 3.** Nếu mọi bit từ 0 đến 7 đều set, `previousClearBit(7)` có trả 8 vì 8 đang clear không?

**Đáp án:** **Không.** Phương thức tìm **ngược** và không vượt mốc 7; kết quả `-1`. Nếu tìm từ 8, kết quả mới là `8`.

**Bài 4.** `BitSet` trống, `previousClearBit(500)` trả gì? Điều đó có khẳng định ứng dụng có ít nhất 501 slot không?

**Đáp án:** Trả `500` vì bit đó mặc định clear. Nó **không** nói gì về số slot hợp lệ của ứng dụng; đó là giới hạn do ứng dụng tự quản lý.

**Bài 5.** Vì sao vòng lặp `for (i = bits.previousSetBit(k); i >= 0; i = bits.previousSetBit(i))` nguy hiểm?

**Đáp án:** `previousSetBit(i)` bao gồm chỉ số `i` đang set nên sẽ trả lại chính `i`, tạo vòng lặp vô hạn. Phải dùng `previousSetBit(i - 1)` sau khi xử lý vị trí hiện tại.

**Bài 6.** Khi `i == 0`, gọi `previousSetBit(i - 1)` có bị lỗi không? Còn `previousSetBit(-2)`?

**Đáp án:** `previousSetBit(-1)` trả `-1` hợp lệ để kết thúc. `previousSetBit(-2)` gây `IndexOutOfBoundsException`.

**Bài 7.** Một hệ thống có `slotCount=5`; `occupied` đã set `{0,1,3,4}`. `lastFreeSlot(occupied, 5)` trả gì?

**Đáp án:** Trả `2`, vì 4 và 3 set, còn 2 clear; không tìm các vị trí ngoài 0..4.

**Bài 8.** Nếu gọi `lastFreeSlot(occupied, 0)`, kết quả phù hợp là gì và vì sao không nên lấy `size()` thay cho 0?

**Đáp án:** Trả `-1` vì miền slot hợp lệ rỗng. `BitSet.size()` chỉ là dung lượng lưu trữ, không thể biến một hệ thống có 0 slot thành hệ thống có hàng chục slot.

**Bài 9.** Hai luồng đồng thời gọi `previousClearBit(lastSlot)` rồi `set(index)`. Có thể chọn cùng một slot không?

**Đáp án:** Có thể. Tìm và set là hai thao tác rời nhau, không tự atomic. Cần đồng bộ nếu có yêu cầu cấp phát slot duy nhất.

## 12. Checklist áp dụng

- [ ] Dùng `previousSetBit(k)` khi cần tìm bit **1** gần nhất từ `k` trở về 0.
- [ ] Dùng `previousClearBit(k)` khi cần tìm bit **0** gần nhất từ `k` trở về 0.
- [ ] Nhớ cả hai xét **chính `k`**, không tự bỏ qua bit tại mốc.
- [ ] Kiểm tra `>= 0` trước khi dùng kết quả tìm kiếm như chỉ số hợp lệ.
- [ ] Khi duyệt ngược nhiều phần tử, tiếp tục từ `i - 1` để không lặp lại phần tử vừa thấy.
- [ ] Hiểu `-1` là sentinel được hỗ trợ; giá trị đầu vào `< -1` gây lỗi.
- [ ] Với bit clear, luôn xác định cận trên nghiệp vụ; không suy diễn cận từ `length()` hoặc `size()`.
- [ ] Phân biệt `length()` (bit set cao nhất + 1), `cardinality()` (số bit set) và `size()` (dung lượng lưu trữ).
- [ ] Nếu cần miền `[low, high]`, kiểm tra `low >= 0`, `high >= low` và kết quả không nhỏ hơn `low`.
- [ ] Hiểu `previous...` chỉ truy vấn, không tự thay đổi BitSet hoặc đồng bộ thao tác cấp phát.
- [ ] Kiểm thử cả: BitSet rỗng, bit 0, miền đã set kín, mốc cao hơn bit cuối, `-1` và `-2`.
- [ ] Dùng API hiện đại, kiểm tra các giả định trên JDK đang hỗ trợ.

## 13. Tài liệu chính thức

- [Javadoc Java SE 21 — BitSet.previousSetBit(int)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/BitSet.html#previousSetBit(int)): định nghĩa tìm bit set ngược, giá trị `-1` và lỗi đầu vào quá âm.
- [Javadoc Java SE 21 — BitSet.previousClearBit(int)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/BitSet.html#previousClearBit(int)): định nghĩa tìm bit clear ngược và các ranh giới.
- [Javadoc Java SE 21 — BitSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/BitSet.html): tính chất bit mặc định clear, các phương thức `length()`, `cardinality()`, `size()`, `set` và `get`.
- [Javadoc Java SE 21 — BitSet.stream()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/BitSet.html#stream()): stream chỉ số các bit set, thích hợp khi cần duyệt tăng dần.

**Kết luận:** `previousSetBit` và `previousClearBit` là công cụ tìm vị trí bit theo chiều giảm dần, trả **chỉ số** và bao gồm điểm xuất phát. Khác biệt quan trọng nhất không nằm ở cú pháp mà ở **cách hiểu miền bit**: bit clear mặc định tồn tại cả ngoài phần đã set, nên tìm slot trống phải có cận trên rõ ràng. Kết hợp sentinel `-1` và bước lặp `i - 1` giúp viết vòng lặp duyệt ngược đúng, gọn và không cần API lỗi thời.
