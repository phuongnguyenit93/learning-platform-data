# Khai thác cấu trúc khóa để vượt khỏi mô hình chỉ so sánh

> **Chủ đề:** Computer Science Algorithms → Sắp xếp phân phối.  
> **Mục tiêu:** Hiểu tại sao sắp xếp chỉ dựa trên so sánh có cận dưới `Ω(n log n)`, nhận diện thông tin bổ sung về **miền giá trị, chữ số, thứ tự từ điển và phân phối khóa**, rồi chọn và chứng minh counting sort, radix sort hoặc bucket sort đúng. Biết phân tích cả **thời gian, bộ nhớ, tính ổn định, ràng buộc đầu vào** và cài đặt bằng Java 17+.

## 1. “Vượt khỏi mô hình chỉ so sánh” có nghĩa gì?

Trong **mô hình sắp xếp so sánh** (*comparison sorting*), thuật toán tìm thứ tự của các phần tử chỉ bằng hỏi những câu như `a < b`, `a == b` hoặc `a > b`. Merge sort, heapsort và quicksort thông dụng thuộc nhóm này.

Với `n` khóa **phân biệt**, có `n!` hoán vị đầu vào có thể tương ứng với `n!` trật tự cần phân biệt. Một **cây quyết định so sánh nhị phân** phải có ít nhất `n!` lá để xác định mọi khả năng. Nếu chiều cao là `h`, cây có tối đa `2^h` lá, nên:

`2^h >= n!`, do đó `h >= log2(n!) = Ω(n log n)`.

Vì thế, trong trường hợp xấu nhất, **mọi thuật toán sắp xếp chỉ dùng so sánh** cần `Ω(n log n)` phép so sánh cho các khóa phân biệt. Đây là cận dưới của **mô hình thao tác** đã nêu, **không phải** quy định rằng mọi cách sắp xếp trên máy tính đều phải mất `Ω(n log n)` thời gian.

Nếu khóa là **số nguyên trong miền hữu hạn**, dãy **chữ số với độ dài xác định**, hay điểm số nằm trong các khoảng biết trước, thuật toán có thể đọc trực tiếp cấu trúc khóa:

- Dùng giá trị khóa làm chỉ số trong **mảng đếm**.
- Tách khóa thành các **chữ số/byte** rồi phân phối qua nhiều lượt.
- Ánh xạ khóa vào **các xô (*bucket*)** và chỉ sắp xếp bên trong từng xô.

Những thuật toán đó dựa thêm vào phép truy cập mảng, đếm, tách byte, phép toán số học và cấp phát bộ nhớ, chứ không chỉ so sánh hai phần tử tùy ý. Do đó chúng **không mâu thuẫn** với chứng minh cận dưới ở trên.

**Điểm cốt lõi:** lợi thế về thời gian không đến miễn phí. Cần một giả định về miền khóa, số chữ số, chi phí thao tác từ máy hoặc phân phối dữ liệu; phải tính đầy đủ chi phí của các giả định đó.

## 2. Nhìn vào khóa trước khi chọn thuật toán

Xét bốn dạng dữ liệu khác nhau:

| Dữ liệu | Cấu trúc khóa khai thác được | Hướng tiếp cận |
|---|---|---|
| Điểm kiểm tra nguyên từ `0` tới `100` | Miền khóa có `101` giá trị | Counting sort hoặc đếm rồi xuất |
| Mã nguyên có dấu 32 bit | Chính xác `4` byte mỗi khóa | Radix sort 4 lượt với cơ số `256` |
| Chuỗi chỉ gồm chữ in hoa ASCII, cùng độ dài `d` | `d` ký tự, mỗi ký tự có 26 khả năng | LSD radix theo vị trí ký tự |
| Số thực trong `[0,1)` gần phân phối đều | Biết miền và đặc điểm phân phối | Bucket sort, kèm thuật toán trong xô |

Ngược lại, nếu khóa là đối tượng tùy ý chỉ có `Comparator`, không có cách gán vào **số lượng xô hợp lý**, hoặc tính chữ số tốn kém, không nên gượng ép sắp xếp phân phối.

Ba câu hỏi phải trả lời trước khi dùng nhóm thuật toán này:

1. **Có biểu diễn khóa hữu hạn và có thể truy cập không?** Phải xác định miền `min..max`, độ dài chữ số `d` hoặc hàm ánh xạ xô.
2. **Cần bảo toàn những gì?** Kết quả phải đúng thứ tự, đủ phần tử và đúng số lần xuất hiện. Với bản ghi có khóa trùng, có cần **ổn định** (*stable*) không?
3. **Giá phải trả là bao nhiêu?** Mảng đếm dài `K`, bộ đệm đầu ra dài `n`, số lượt `d`, số xô `b` và độ lệch phân phối đều là chi phí thực.

Các phép sắp xếp phân phối thường tận dụng **miền khóa nhỏ hoặc chiều dài khóa bị chặn**. Khi các đại lượng đó phát triển theo đầu vào, cách viết đơn giản “`O(n)`” có thể không còn chính xác.

## 3. Counting sort: phân phối theo giá trị nguyên

### 3.1. Bài toán và ý tưởng

Cho `n` phần tử có **khóa nguyên** trong miền bao gồm hai đầu mút `[minKey, maxKey]`. Đặt:

`K = maxKey - minKey + 1`.

Tạo mảng `count[0..K-1]`, trong đó phần tử có khóa `x` tương ứng chỉ số `x - minKey`.

Ví dụ các khóa:

```text
Input: [2, -1, 2, 0, -1]
Miền:  [-1, 2]  →  K = 4

Khóa:       -1   0   1   2
Số lần:      2   1   0   2
Output:     -1  -1   0   2   2
```

Nếu chỉ cần sắp xếp **giá trị số** và không cần giữ bản ghi gốc, ta có thể đếm tần suất rồi xuất mỗi giá trị đúng số lần tương ứng. Nhưng nếu mỗi phần tử là một bản ghi `(key,id)`, muốn **ổn định** phải phân phối nguyên bản ghi đến vị trí thích hợp.

### 3.2. Counting sort ổn định bằng tổng tích lũy

Gọi `count[t]` là số lần xuất hiện khóa có chỉ số `t`.

1. **Đếm:** tăng `count[key-minKey]` với mỗi bản ghi.
2. **Cộng dồn:** biến `count[t]` thành tổng số phần tử có khóa **không lớn hơn** khóa `t`. Đây là **vị trí kết thúc độc quyền** (*exclusive end*) của nhóm đó trong mảng đầu ra.
3. **Quét đầu vào từ phải sang trái:** với bản ghi có chỉ số khóa `t`, giảm `count[t]`, rồi đặt bản ghi tại `out[count[t]]`.
4. Sao chép/trả mảng kết quả.

Ví dụ hai bản ghi có cùng khóa `2` là `(2,A)` rồi `(2,C)`. Khi quét ngược, `(2,C)` được đặt vào **ô cuối** dành cho khóa `2`; `(2,A)` được đặt vào ô ngay trước. Do đó kết quả vẫn có thứ tự **A trước C**.

**Bất biến ổn định:** các ô dành cho mỗi khóa tạo thành một đoạn liên tiếp; khi quét ngược, bản ghi đứng về sau trong dữ liệu gốc được đặt vào vị trí trống cuối cùng của đoạn khóa đó. Mọi bản ghi cùng khóa có thứ tự sau cùng như ban đầu.

### 3.3. Java 17: counting sort ổn định, có khóa âm

Lưu tệp **StableCountingSortDemo.java**:

```java
import java.util.Arrays;
import java.util.Objects;

public class StableCountingSortDemo {
    record Entry(int key, String id) {
        @Override
        public String toString() {
            return key + ":" + id;
        }
    }

    static Entry[] sort(Entry[] input, int minKey, int maxKey) {
        Objects.requireNonNull(input, "input");
        if (minKey > maxKey) {
            throw new IllegalArgumentException("Invalid key domain");
        }

        // Tính bằng long để tránh tràn số khi trừ hai int.
        long span = (long) maxKey - minKey + 1L;
        if (span > Integer.MAX_VALUE) {
            throw new IllegalArgumentException("Key range too large");
        }
        int[] count = new int[(int) span];

        for (Entry entry : input) {
            Objects.requireNonNull(entry, "entry");
            if (entry.key() < minKey || entry.key() > maxKey) {
                throw new IllegalArgumentException("Key outside domain");
            }
            int slot = (int) ((long) entry.key() - minKey);
            count[slot]++;
        }

        // count[t] là số phần tử có khóa <= khóa tại t.
        for (int t = 1; t < count.length; t++) {
            count[t] += count[t - 1];
        }

        Entry[] output = new Entry[input.length];
        for (int i = input.length - 1; i >= 0; i--) {
            Entry entry = input[i];
            int slot = (int) ((long) entry.key() - minKey);
            output[--count[slot]] = entry;
        }
        return output;
    }

    public static void main(String[] args) {
        Entry[] items = {
            new Entry(2, "A"),
            new Entry(-1, "B"),
            new Entry(2, "C"),
            new Entry(0, "D"),
            new Entry(-1, "E")
        };

        System.out.println("Input:  " + Arrays.toString(items));
        System.out.println("Sorted: " + Arrays.toString(sort(items, -1, 2)));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 StableCountingSortDemo.java
java StableCountingSortDemo
```

Stdout:

```text
Input:  [2:A, -1:B, 2:C, 0:D, -1:E]
Sorted: [-1:B, -1:E, 0:D, 2:A, 2:C]
```

Ở khóa `-1`, B đứng trước E; ở khóa `2`, A đứng trước C. Mảng đầu vào không bị thay đổi. Ví dụ này có thể áp dụng cho bản ghi vì **chỉ khóa** được dùng để tính vị trí, còn toàn bộ đối tượng được chuyển nguyên vẹn.

**Lưu ý phạm vi:** ví dụ yêu cầu miền `[minKey,maxKey]` hợp lệ ngay cả khi `input` rỗng. Nếu `K` rất lớn dù `n` nhỏ, việc tạo `int[K]` có thể không khả thi trong bộ nhớ thực tế. Việc `span <= Integer.MAX_VALUE` chỉ là điều kiện về khả năng đánh chỉ số Java; **không bảo đảm** RAM đủ để cấp phát.

### 3.4. Chứng minh tính đúng

Đặt `F(t)` là số phần tử có chỉ số khóa bằng `t`, `P(t)` là tổng `F(0)+...+F(t)`, và `P(-1)=0`.

- Sau bước đếm, `count[t]=F(t)` vì mỗi phần tử đóng góp chính xác một lần vào vị trí ứng với khóa của nó.
- Sau bước cộng dồn, `count[t]=P(t)`. Vùng dành riêng cho khóa `t` là `[P(t-1),P(t))` và có chính xác `F(t)` ô.
- Khi quét ngược, mỗi lần gặp khóa `t`, `--count[t]` cấp một ô **chưa sử dụng** trong vùng đó; không có hai bản ghi nhận cùng ô.
- Có đúng `F(t)` bản ghi khóa `t`, nên mọi ô của vùng `[P(t-1),P(t))` được lấp đầy, không bỏ hoặc thêm bản ghi.
- Các vùng của khóa nhỏ hơn nằm hoàn toàn trước vùng của khóa lớn hơn, vì các `P(t)` không giảm. Do đó đầu ra được sắp xếp.
- Quét từ phải sang trái cộng với điền từ cuối vùng về đầu giữ đúng thứ tự tương đối trong mỗi nhóm khóa; thuật toán ổn định.

**Chi phí:** đếm `O(n)`, cộng dồn `O(K)`, phân phối `O(n)` → **`O(n+K)` thời gian**, **`O(n+K)` bộ nhớ phụ** cho mảng output và count. Nếu chỉ cần xuất các giá trị nguyên (không phải bản ghi), có thể không cần bộ đệm output phụ khi đầu ra ghi đè hợp lệ, nhưng vẫn cần mảng đếm `O(K)`.

**Cảnh báo khi dùng khóa âm:** chỉ số phải được dịch bằng `key - minKey` và phép trừ/tính `K` phải tránh tràn `int`. Nếu `minKey = Integer.MIN_VALUE`, `maxKey = Integer.MAX_VALUE`, miền có `2^32` giá trị, không thể cấp mảng đếm theo cách trên. Khi miền cực rộng nhưng chỉ có vài khóa xuất hiện, cân nhắc cấu trúc thưa hoặc thuật toán khác.

## 4. Radix sort: phân phối lần lượt theo chữ số

### 4.1. Khóa có nhiều chữ số

Thay vì tạo một mảng đếm đủ cho toàn bộ miền khóa, **radix sort** tách mỗi khóa thành các chữ số thuộc cơ số `b` (ví dụ `10`, `16`, `256`). Mỗi chữ số nhận giá trị `0..b-1`, vì vậy ở mỗi lượt chỉ cần đếm **`b` nhóm**.

Hai hướng chính:

- **LSD (*least significant digit*)**: xử lý chữ số **ít quan trọng nhất** trước, rồi đến chữ số quan trọng hơn; **mọi lượt phải ổn định** để bảo toàn thứ tự do các chữ số đã xử lý tạo ra.
- **MSD (*most significant digit*)**: phân phối theo chữ số quan trọng nhất trước, rồi xử lý **đệ quy bên trong từng nhóm** theo chữ số kế tiếp; phải xử lý ký hiệu kết thúc chuỗi và trường hợp dừng đúng.

Radix sort không phải một phép so sánh trực tiếp của toàn bộ các khóa. Nó dựa trên việc đọc chữ số độc lập với kích thước khóa, thường kết hợp **counting sort ổn định** cho mỗi lượt.

### 4.2. Ví dụ LSD bằng hai chữ số thập phân

Cho `[31,12,21,13]`, các khóa có hai chữ số:

```text
Ban đầu:                     [31, 12, 21, 13]
Lượt chữ số hàng đơn vị:      [31, 21, 12, 13]
                               ^1  ^1  ^2  ^3
Lượt chữ số hàng chục:       [12, 13, 21, 31]
                               ^1  ^1  ^2  ^3
```

Ở lượt đơn vị, `31` đứng trước `21` vì cùng đơn vị `1` và lượt phân phối ổn định. Ở lượt chục, `12` vẫn đứng trước `13` vì cùng chữ số hàng chục `1`; quy tắc ổn định giữ lại thứ tự theo đơn vị từ lượt trước. Đây là lý do **mỗi lượt LSD cần ổn định**.

### 4.3. Bất biến của LSD radix sort

Giả sử mỗi khóa có `d` chữ số theo cùng quy ước số 0 ở đầu khi cần. Sau khi xử lý `r` chữ số thấp nhất bằng các lượt phân phối ổn định, dãy được sắp xếp đúng theo **`r` chữ số thấp nhất** của khóa.

- **Cơ sở:** sau lượt chữ số thấp nhất, dãy có thứ tự theo chữ số đó.
- **Bước:** lượt chữ số kế tiếp sắp theo chữ số mới; trong nhóm có chữ số mới bằng nhau, tính ổn định giữ thứ tự theo các chữ số thấp hơn từ trước. Vì vậy dãy đúng theo `r+1` chữ số thấp nhất.
- **Kết luận:** sau `d` lượt, mọi chữ số đã tham gia nên dãy có thứ tự theo toàn bộ khóa.

Nếu các khóa có cùng tiền tố hoặc hậu tố tương ứng, thứ tự ổn định giúp tránh đảo các bản ghi có khóa hoàn toàn bằng nhau.

**Chi phí tổng quát:** với `n` phần tử, `d` lượt, `b` nhóm, một lượt counting sort ổn định tốn `O(n+b)`. Tổng là **`O(d(n+b))` thời gian**, bộ nhớ phụ thường **`O(n+b)`** (tái sử dụng mảng). Chỉ khi `d` và `b` bị chặn bởi hằng số trong mô hình chi phí phù hợp mới có thể gọi nó là **tuyến tính theo n**.

### 4.4. Số nguyên âm và bit dấu trong Java

Java `int` là số nguyên **có dấu 32 bit**; việc chỉ đọc bốn byte từ thấp lên cao như số không dấu sẽ đặt các số âm sau số dương nếu không sửa cách diễn giải bit dấu.

Có thể biến đổi khóa bằng:

`mapped = value ^ Integer.MIN_VALUE`.

Phép XOR này **đảo bit dấu**:

- Các số âm được ánh xạ vào nửa thấp của không gian **không dấu**.
- Các số không âm được ánh xạ vào nửa cao.
- Bên trong từng nửa, thứ tự theo số nguyên có dấu được giữ nguyên khi so theo các bit không dấu.

Vì vậy, sắp xếp bốn byte của `mapped` theo thứ tự số **không dấu** cho đúng thứ tự tăng của các `int` gốc. Ta chỉ dùng `mapped` để đọc chữ số, còn mảng kết quả giữ nguyên giá trị `int` ban đầu. Không dùng `Math.abs(value)` để xử lý dấu: `Math.abs(Integer.MIN_VALUE)` vẫn âm do không biểu diễn được giá trị dương tương ứng bằng `int`.

### 4.5. Java 17: LSD radix sort cho toàn bộ miền `int`

Lưu tệp **RadixSignedIntDemo.java**:

```java
import java.util.Arrays;
import java.util.Objects;

public class RadixSignedIntDemo {
    static void sort(int[] a) {
        Objects.requireNonNull(a, "a");

        int[] buffer = new int[a.length];
        final int RADIX = 256;

        // int có 32 bit: 4 lượt, mỗi lượt xử lý 8 bit.
        for (int shift = 0; shift < 32; shift += 8) {
            int[] count = new int[RADIX];

            for (int value : a) {
                int mapped = value ^ Integer.MIN_VALUE;
                int digit = (mapped >>> shift) & 0xFF;
                count[digit]++;
            }

            // next[d] là ô bắt đầu ghi cho nhóm digit d.
            int[] next = new int[RADIX];
            for (int d = 1; d < RADIX; d++) {
                next[d] = next[d - 1] + count[d - 1];
            }

            // Quét trái sang phải + next[d]++ => phân phối ổn định.
            for (int value : a) {
                int mapped = value ^ Integer.MIN_VALUE;
                int digit = (mapped >>> shift) & 0xFF;
                buffer[next[digit]++] = value;
            }

            System.arraycopy(buffer, 0, a, 0, a.length);
        }
    }

    public static void main(String[] args) {
        int[] a = {
            12, -1, Integer.MIN_VALUE, 3,
            0, Integer.MAX_VALUE, -9, 0
        };
        sort(a);
        System.out.println("Sorted: " + Arrays.toString(a));

        int[] empty = {};
        sort(empty);
        System.out.println("Empty: " + Arrays.toString(empty));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 RadixSignedIntDemo.java
java RadixSignedIntDemo
```

Stdout:

```text
Sorted: [-2147483648, -9, -1, 0, 0, 3, 12, 2147483647]
Empty: []
```

Đoạn mã dùng phép `>>>` để **dịch phải không giữ dấu**. `& 0xFF` giữ đúng một byte từ `0` tới `255`. Mỗi lượt có `256` nhóm; vị trí đầu nhóm được tính bằng tổng số phần tử của các nhóm **nhỏ hơn**, và quét trái sang phải duy trì ổn định.

**Độ phức tạp:** đúng bốn lượt nên `O(4(n+256))`, thường viết `O(n)` khi coi kích thước khóa `int` 32 bit và cơ số `256` là hằng số; thêm mảng `buffer[n]` và hai mảng 256 phần tử mỗi lượt, tức **`O(n+256)`** bộ nhớ phụ. Điều này không có nghĩa mọi kiểu số dài tùy ý cũng được sắp xếp với bốn lượt.

**Trường hợp `Integer.MIN_VALUE` và `Integer.MAX_VALUE`:** đã được ví dụ bao quát, không có phép trừ để tính chữ số nên tránh tràn. Với số `long` 64 bit có thể dùng **tám lượt byte**, đảo bit dấu bằng `Long.MIN_VALUE`, dùng dịch `>>>` trên `long`.

**Lưu ý về ổn định:** với dữ liệu `int[]`, các khóa bằng nhau không có nhãn nên khó quan sát. Cùng cách phân phối ổn định có thể áp dụng cho bản ghi bằng cách lưu **bản ghi** trong buffer và trích khóa để lấy byte; nếu mọi lượt đều ổn định, các bản ghi cùng khóa sẽ giữ thứ tự gốc.

## 5. Radix sort trên chuỗi: khai thác vị trí ký tự

Khi dữ liệu là chuỗi, “chữ số” có thể là **ký tự tại một vị trí**. Nhưng điều kiện không đơn giản như với số nguyên.

**Ví dụ đặc biệt dễ:** tất cả chuỗi có cùng độ dài `d`, chỉ gồm chữ in hoa ASCII `'A'..'Z'`, và thứ tự mong muốn là **thứ tự từ điển theo các ký tự ASCII đó**. Mỗi vị trí chỉ có 26 giá trị, có thể dùng LSD radix từ ký tự cuối đến ký tự đầu.

Nếu chuỗi có độ dài **khác nhau**, ta phải xử lý rõ **ký hiệu kết thúc** (*end-of-string sentinel*) sao cho `"AB"` đứng trước `"ABA"` trong thứ tự từ điển; không thể tự đệm dấu cách hoặc ký tự `'Z'` tùy ý mà không xét ảnh hưởng đến thứ tự. Với tiếng Việt, Unicode, chữ hoa/thường, chuẩn hóa và so sánh theo ngôn ngữ, thứ tự ký tự có thể khác thứ tự mã Unicode; phải định nghĩa comparator/chuẩn hóa cụ thể trước khi thiết kế radix.

### 5.1. Java 17: các chuỗi ASCII cùng độ dài

Lưu tệp **FixedWidthStringRadixDemo.java**:

```java
import java.util.Arrays;
import java.util.Objects;

public class FixedWidthStringRadixDemo {
    static void sort(String[] words, int width) {
        Objects.requireNonNull(words, "words");
        if (width < 0) {
            throw new IllegalArgumentException("Negative width");
        }
        for (String s : words) {
            if (s == null || s.length() != width) {
                throw new IllegalArgumentException("Different word lengths");
            }
            for (int p = 0; p < width; p++) {
                if (s.charAt(p) < 'A' || s.charAt(p) > 'Z') {
                    throw new IllegalArgumentException("Only ASCII A..Z");
                }
            }
        }

        String[] buffer = new String[words.length];
        // Từ ký tự cuối về ký tự đầu.
        for (int p = width - 1; p >= 0; p--) {
            int[] count = new int[26];

            for (String s : words) {
                count[s.charAt(p) - 'A']++;
            }
            // count[d] là vị trí kết thúc độc quyền của nhóm d.
            for (int d = 1; d < 26; d++) {
                count[d] += count[d - 1];
            }

            // Quét ngược để phân phối ổn định.
            for (int i = words.length - 1; i >= 0; i--) {
                String s = words[i];
                int d = s.charAt(p) - 'A';
                buffer[--count[d]] = s;
            }
            System.arraycopy(buffer, 0, words, 0, words.length);
        }
    }

    public static void main(String[] args) {
        String[] words = {"CAB", "ABC", "BAA", "ABA", "AAA", "CAB"};
        sort(words, 3);
        System.out.println(Arrays.toString(words));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 FixedWidthStringRadixDemo.java
java FixedWidthStringRadixDemo
```

Stdout:

```text
[AAA, ABA, ABC, BAA, CAB, CAB]
```

**Chi phí:** nếu `n` chuỗi đều có chiều dài `d` và bảng ký tự `R=26`, kiểm tra đầu vào `O(nd)`, mỗi lượt phân phối `O(n+R)`, tổng **`O(d(n+R))` thời gian**. Bộ nhớ phụ là `O(n+R)` tham chiếu/biến đếm, ngoài vùng lưu nội dung các chuỗi. Nếu `d` tăng theo kích thước đầu vào, **không** được gộp nó thành hằng số và tuyên bố `O(n)` một cách vô điều kiện.

**Tính ổn định:** các bản sao `"CAB"` vẫn giữ thứ tự tương đối vì mỗi lượt phân phối dùng phép đếm cộng dồn và quét ngược. Nếu chuỗi là bản ghi có cùng `key`, ta có thể phân phối bản ghi thay vì `String`, tương tự counting sort.

## 6. Bucket sort: khai thác miền và phân phối

**Bucket sort** chia miền khóa thành `b` khoảng (*bucket*), đưa mỗi phần tử vào một khoảng, sắp xếp các phần tử **bên trong từng bucket**, rồi nối các bucket theo thứ tự.

Với số thực hữu hạn trong **`[0,1)`**, một ánh xạ phổ biến là:

`bucketIndex(x) = floor(b * x)` với `b` bucket và `0 <= x < 1`.

Bucket 0 chứa khóa gần 0; bucket cuối chứa khóa gần 1. Nếu mọi bucket tương ứng các khoảng không giao nhau và có thứ tự từ thấp tới cao, **mọi phần tử của bucket i nhỏ hơn mọi phần tử của bucket j khi i < j**. Do đó chỉ cần sắp xếp bên trong từng bucket, rồi nối.

Ví dụ với `b=5`:

```text
Input: [0.78, 0.17, 0.39, 0.26, 0.72, 0.94, 0.21, 0.17]

Bucket 0 [0.0, 0.2):  [0.17, 0.17]
Bucket 1 [0.2, 0.4):  [0.39, 0.26, 0.21]
Bucket 2 [0.4, 0.6):  []
Bucket 3 [0.6, 0.8):  [0.78, 0.72]
Bucket 4 [0.8, 1.0):  [0.94]

Sắp từng bucket, nối: [0.17, 0.17, 0.21, 0.26,
                        0.39, 0.72, 0.78, 0.94]
```

Nhận xét quan trọng: một bucket có thể chứa nhiều phần tử, nên **không thể** chỉ đếm số phần tử rồi đặt ra kết quả nếu các khóa trong bucket khác nhau. Mỗi bucket cần cách sắp thứ tự bên trong, ví dụ insertion sort, hoặc một phép phân phối sâu hơn.

### 6.1. Java 17: bucket sort trên `double` trong `[0,1)`

Ví dụ chọn `b=n` bucket để minh họa giả thiết phân phối đều và dùng insertion sort trong từng bucket.

Lưu tệp **BucketSort01Demo.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

public class BucketSort01Demo {
    static double[] sort(double[] values) {
        Objects.requireNonNull(values, "values");
        int n = values.length;
        List<List<Double>> buckets = new ArrayList<>(n);
        for (int i = 0; i < n; i++) {
            buckets.add(new ArrayList<>());
        }

        for (double v : values) {
            if (!Double.isFinite(v)
                    || Double.compare(v, 0.0) < 0
                    || v >= 1.0) {
                throw new IllegalArgumentException("Expected 0 <= x < 1");
            }
            // Chặn sai số làm tròn tại biên cao nhất.
            int index = Math.min(n - 1, (int) (v * n));
            buckets.get(index).add(v);
        }

        double[] result = new double[n];
        int write = 0;
        for (List<Double> bucket : buckets) {
            // Insertion sort ổn định bên trong từng bucket.
            for (int i = 1; i < bucket.size(); i++) {
                double key = bucket.get(i);
                int j = i - 1;
                while (j >= 0 && bucket.get(j) > key) {
                    bucket.set(j + 1, bucket.get(j));
                    j--;
                }
                bucket.set(j + 1, key);
            }
            for (double v : bucket) {
                result[write++] = v;
            }
        }
        return result;
    }

    public static void main(String[] args) {
        double[] a = {
            0.78, 0.17, 0.39, 0.26,
            0.72, 0.94, 0.21, 0.17
        };
        System.out.println(Arrays.toString(sort(a)));
        System.out.println(Arrays.toString(sort(new double[0])));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 BucketSort01Demo.java
java BucketSort01Demo
```

Stdout:

```text
[0.17, 0.17, 0.21, 0.26, 0.39, 0.72, 0.78, 0.94]
[]
```

Hàm từ chối `NaN`, vô cực, giá trị âm (bao gồm `-0.0` theo thứ tự `Double.compare`) và giá trị từ `1.0` trở lên. Với đầu vào rỗng, không có bucket và kết quả là mảng rỗng. Điều kiện miền này là **hợp đồng của ví dụ**, không phải giới hạn bắt buộc của mọi thuật toán bucket sort.

**Độ phức tạp:**

- Tạo `b` bucket `O(b)`, phân phối `O(n)`, nối `O(n)`.
- Nếu bucket `i` chứa `n_i` phần tử và sắp bằng insertion sort, chi phí tổng là `O(b+n+Σ n_i²)`.
- **Xấu nhất:** mọi phần tử rơi vào cùng một bucket, khi đó có thể là **`O(n²+b)`**.
- **Kỳ vọng:** nếu các khóa là những mẫu **độc lập, phân phối đều** trên `[0,1)` và dùng `b=Θ(n)`, số phần tử trong các bucket khá cân đối về kỳ vọng; tổng `Σ n_i²` có kỳ vọng `O(n)`, nên thời gian kỳ vọng **`O(n)`**.
- **Bộ nhớ:** `O(n+b)` để lưu các bucket, tham chiếu/giá trị và kết quả, chưa kể chi phí đối tượng `ArrayList`/boxing `Double` của Java.

**Không tuyên bố bucket sort luôn `O(n)`**: lệch phân phối, nhiều phần tử trùng hoặc ánh xạ xô kém có thể làm một bucket rất lớn. Nếu bên trong dùng thuật toán có chặn `O(t log t)` thay insertion sort, chặn thời gian xấu của toàn bộ thuật toán sẽ khác.

### 6.2. Tính đúng và tính ổn định của bucket sort

1. Mỗi phần tử hợp lệ được đưa vào **đúng một** bucket theo hàm ánh xạ; vì thế không mất hay nhân đôi phần tử.
2. Các miền bucket phải có thứ tự: nếu `i<j`, mọi khóa trong bucket `i` không lớn hơn mọi khóa trong bucket `j`.
3. Sau khi mỗi bucket được sắp xếp đúng, nối các bucket từ nhỏ đến lớn tạo toàn bộ dãy có thứ tự và bảo toàn đa tập.
4. Nếu cần ổn định, thuật toán bên trong bucket phải ổn định, và các phần tử có cùng khóa phải rơi vào cùng bucket; khi đó thứ tự tương đối các bản ghi bằng khóa được bảo toàn. Mã dùng phép `>` khi chèn nên không đảo các khóa bằng nhau.

Phân tích tính đúng **không cần** giả định phân phối đều; giả định đó chỉ dùng khi **ước lượng thời gian kỳ vọng**. Phân biệt hai mục tiêu này là một kỹ năng quan trọng khi đánh giá thuật toán.

## 7. Khai thác cấu trúc khóa không phải lúc nào cũng nhanh hơn

### 7.1. Counting sort với miền quá rộng

`n=1_000` bản ghi nhưng khóa rải từ `-1_000_000_000` đến `1_000_000_000` ⇒ `K≈2×10^9`; việc tạo mảng đếm cực lớn không hợp lý. `O(n+K)` lớn hơn nhiều `O(n log n)` trên `n` phần tử.

Nếu chỉ có vài giá trị khóa khác nhau, dùng **map đếm** có thể tiết kiệm bộ nhớ, nhưng vẫn phải **sắp xếp các khóa phân biệt** để xuất thứ tự; bước này có chi phí phụ. Không thể tuyên bố một `HashMap` tự động tạo ra kết quả đã sắp xếp vì hash table không cung cấp thứ tự tăng của khóa.

### 7.2. “Nén tọa độ” không xóa cận dưới so sánh

Giả sử khóa ban đầu là các số nguyên rất lớn. Ta muốn thay mỗi giá trị bằng **rank** `0..u-1` theo thứ tự tăng rồi counting sort.

Nếu tạo rank bằng cách **sắp xếp các giá trị phân biệt theo comparator**, việc nén tọa độ đã trả chi phí sắp xếp, thường `O(n log n)` khi không khai thác cấu trúc khóa khác. Không được tính riêng bước counting rồi khẳng định toàn bộ lời giải chạy `O(n)`.

Nén tọa độ vẫn rất hữu ích khi rank đã có sẵn, được dùng lại qua nhiều phép toán, hoặc có cách xây rank phù hợp hơn.

### 7.3. Radix sort và số chữ số

Với số nguyên 32 bit, bốn lượt byte là hằng số. Nhưng với khóa dài `d` ký tự, độ phức tạp là `O(d(n+b))`, và việc **đọc/ghi toàn bộ ký tự** đã tốn thời gian theo tổng chiều dài.

Nếu các chuỗi cực dài, dữ liệu Unicode phải chuẩn hóa, hoặc phép truy cập chữ số không có chi phí hằng, chi phí thực tế khác rõ rệt. Trên Java, `String.length()` là số **đơn vị UTF-16**, không luôn bằng số ký tự Unicode mà người dùng nhìn thấy; không nên áp dụng trực tiếp radix ASCII cho từ tiếng Việt khi yêu cầu sắp theo ngôn ngữ.

### 7.4. Bucket sort và phân phối thực tế

Với dữ liệu tập trung gần một giá trị, dùng các bucket độ rộng bằng nhau có thể khiến hầu hết phần tử dồn một xô. Có thể:

- Điều chỉnh hàm chia xô theo phân phối đã biết.
- Dùng thuật toán sắp xếp tốt hơn trong bucket lớn.
- Chọn thuật toán khác nếu không có giả định đủ mạnh về phân phối.

Nếu cần bảo đảm thời gian **xấu nhất**, không nên dùng riêng kết luận kỳ vọng tuyến tính làm cam kết.

### 7.5. Không bỏ qua truy cập bộ nhớ và cấp phát

Trong thực tế, counting/radix/bucket thường cấp phát bộ đệm và quét nhiều lượt. Với mảng nhỏ, một thuật toán so sánh tại chỗ có thể nhanh hơn do chi phí cố định, cache và GC. “Ít phép so sánh hơn” không đồng nghĩa luôn “ít thời gian thực thi hơn”. Bên cạnh Big-O, cần thử benchmark **trên đúng loại dữ liệu và giới hạn bộ nhớ**.

## 8. Bảng chọn thuật toán và độ phức tạp

Ký hiệu: `n` là số phần tử, `K` là số giá trị nguyên trong miền, `d` số chữ số, `b` số nhóm/chữ số, và `n_i` số phần tử thuộc bucket `i`.

| Thuật toán | Điều kiện/khóa khai thác | Thời gian | Bộ nhớ phụ | Ổn định? |
|---|---|---|---|---|
| **Counting sort ổn định** | Khóa nguyên trong miền `K` đủ nhỏ | `O(n+K)` | `O(n+K)` | Có, khi phân phối đúng cách |
| **LSD radix + counting** | Khóa có `d` chữ số cơ số `b` | `O(d(n+b))` | `O(n+b)` | Có nếu mỗi lượt ổn định |
| **MSD radix** | Có thể xét chữ số quan trọng trước và chia tiếp nhóm | Tùy phân phối/chiều dài khóa | Tùy cách cài đặt | Phải xét rõ từng nhánh |
| **Bucket + insertion** | Có thể ánh xạ khóa vào các khoảng có thứ tự | `O(b+n+Σ n_i²)`; kỳ vọng `O(n)` khi giả thiết phù hợp | `O(n+b)` | Có nếu bucket con ổn định |
| **Merge sort** | Chỉ cần comparator | `O(n log n)` | Thường `O(n)` cho mảng | Có nếu merge ổn định |
| **Heapsort** | Chỉ cần comparator | `O(n log n)` | `O(1)` tại chỗ | Thường không |
| **Quicksort thông dụng** | Chỉ cần comparator | Kỳ vọng/trung bình `O(n log n)`, xấu nhất `O(n²)` | Tùy đệ quy | Thường không |

Bảng giả sử thao tác truy cập chữ số/khóa có chi phí thích hợp theo mô hình đã nói. Các trường hợp biên (`n=0`, `K=0` không hợp lệ khi có khóa, `b=0`, khóa không có chữ số) phải được xác định riêng trong cài đặt.

**Về ổn định:** counting/radix không tự động ổn định chỉ vì “không dùng so sánh”. Cần cách phân phối bảo toàn thứ tự trong từng nhóm. Bucket sort cũng phụ thuộc thuật toán dùng bên trong và cách xử lý phần tử bằng nhau.

## 9. Những lỗi thường gặp trong thiết kế và Java

### 9.1. Dùng giá trị âm làm chỉ số mảng

Sai:

```java
count[key]++; // key = -3 => ArrayIndexOutOfBoundsException.
```

Đúng với miền khai báo `[minKey,maxKey]`: dùng chỉ số `key-minKey`, kiểm tra miền và tính chênh lệch bằng `long` nếu hai đầu có thể ở biên `int`.

### 9.2. Đếm rồi phân phối nhưng mất ổn định

Khi `count[t]` giữ **vị trí kết thúc độc quyền**, phải **quét đầu vào từ phải sang trái** và gán `out[--count[t]] = item`, hoặc dùng một mảng vị trí **bắt đầu** và quét xuôi. Quét xuôi kết hợp giảm từ vị trí kết thúc có thể đảo các bản ghi cùng khóa.

### 9.3. Lạm dụng bộ nhớ vì `K` quá lớn

Cần tính `K` bằng `long` trước khi cấp phát. `K` lớn hơn số phần tử thực nhiều bậc có thể khiến counting sort chậm hoặc hết bộ nhớ. Không giả định rằng `K` vừa trong `int` là sẽ vừa trong RAM.

### 9.4. Cho rằng radix sort không cần ổn định

Trong LSD radix, ở lượt chữ số cao hơn, các phần tử có chữ số cao bằng nhau phải giữ trật tự đã hình thành từ chữ số thấp hơn. Nếu một lượt phân phối đảo thứ tự hòa, kết quả cuối có thể sai.

### 9.5. Xử lý `int` âm bằng `Math.abs`

`Math.abs(Integer.MIN_VALUE)` không trả số dương mong đợi vì không thể biểu diễn `2147483648` bằng `int`. Bản Java dùng `x ^ Integer.MIN_VALUE` để ánh xạ thứ tự có dấu vào thứ tự bit không dấu, áp dụng thống nhất trên cả bốn byte.

### 9.6. Nhầm `>>` và `>>>`

Dịch phải có dấu `>>` điền bit dấu, còn `>>>` điền 0. Khi rút byte từ một số có thể âm, dùng `>>>` cùng mặt nạ `& 0xFF` để lấy đúng một chữ số từ `0..255`.

### 9.7. Bỏ qua đầu mút của khoảng

Bucket sort ví dụ yêu cầu **`0 <= x < 1`**, không nhận `x=1`. Nếu dùng `floor(b*x)` với `x=1`, chỉ số thành `b`, nằm ngoài `0..b-1`. Cũng phải xét `NaN`, vô cực và sai số làm tròn số thực. Với số thực gần đầu mút, code có thể chặn chỉ số sau khi xác thực miền.

### 9.8. Cho rằng các xô đã có thứ tự nội bộ

Bucket chỉ bảo đảm **thứ tự giữa các miền** nếu ánh xạ đúng. Các phần tử trong cùng xô vẫn có thể lộn xộn; cần sắp nội bộ trước khi nối.

### 9.9. Không thống nhất ngữ nghĩa chuỗi

Thứ tự ASCII của ký tự không thay thế thứ tự ngôn ngữ tự nhiên; `'A'..'Z'` cùng độ dài là tiền điều kiện cụ thể của ví dụ. Với Unicode, chuỗi có độ dài khác nhau hoặc ký tự có dấu, cần xác định chuẩn hóa, cách so sánh và ký hiệu kết thúc nếu dùng radix.

### 9.10. Đếm nhầm chi phí khi lập luận vượt `n log n`

Chỉ nói “mỗi phần tử được duyệt một lần” là thiếu: counting sort duyệt mảng đếm `K`, radix thực hiện `d` lượt, bucket sort còn có chi phí sắp nội bộ. Phải tính đủ **`n`, `K`, `d`, `b` và phân phối**.

### 9.11. Đánh đồng ổn định với bảo toàn đa tập

Một thuật toán có thể trả đầy đủ phần tử và đúng thứ tự khóa nhưng **đảo ID của bản ghi cùng khóa**. Muốn kiểm thử ổn định phải lưu nhãn/ID, không chỉ so sánh mảng các khóa số.

### 9.12. Bỏ qua chi phí chuyển đổi khóa

Nếu phải chuyển chuỗi phức tạp thành số, parse JSON, chuẩn hóa Unicode hay tính hash, chi phí chuyển đổi có thể chiếm ưu thế. Hash **không bảo toàn thứ tự** theo mặc định, vì thế không thể thay khóa so sánh bằng hash rồi counting sort để có thứ tự gốc.

## 10. Kiểm thử đúng theo hợp đồng

### Counting sort

| Input | Miền | Output kỳ vọng | Điểm cần kiểm tra |
|---|---|---|---|
| `[]` | `[0,2]` | `[]` | Mảng rỗng |
| `[0]` | `[0,0]` | `[0]` | Một khóa duy nhất |
| `[-2,0,-2,3]` | `[-2,3]` | `[-2,-2,0,3]` | Chỉ số bù, giá trị âm |
| `[4,4,4]` | `[4,4]` | `[4,4,4]` | Khóa trùng |
| `[(1,A),(0,B),(1,C)]` | `[0,1]` | `[(0,B),(1,A),(1,C)]` | Ổn định |

Mảng đầu vào có khóa nằm **ngoài miền** là lỗi tiền điều kiện; cài đặt minh họa ném ngoại lệ, không âm thầm bỏ phần tử.

### Radix sort cho `int`

Dùng các bộ dữ liệu: rỗng, toàn số 0, âm/dương trộn nhau, trùng giá trị, `Integer.MIN_VALUE`, `Integer.MAX_VALUE`, các giá trị chỉ khác byte cao. Với mỗi bộ, so sánh kết quả với `Arrays.sort` trên **bản sao** để bắt lỗi chuyển bit dấu và phân phối từng lượt.

### Bucket sort

Thử giá trị gần `0`, gần `1` nhưng vẫn nhỏ hơn `1`, các phần tử bằng nhau, mọi phần tử dồn cùng xô, mảng rỗng và dữ liệu sai miền (`NaN`, `1.0`, số âm). Ca **mọi phần tử cùng xô** rất hữu ích để xác nhận bộ đếm thời gian thực tế có thể đạt trường hợp xấu.

**Các bất biến cần kiểm tra:**

1. **Thứ tự:** với mọi vị trí kề nhau, khóa trước không lớn hơn khóa sau.
2. **Bảo toàn đa tập:** mọi phần tử/bản ghi xuất hiện đúng số lần ban đầu.
3. **Ổn định nếu cần:** nhãn của các bản ghi cùng khóa giữ thứ tự xuất hiện.
4. **An toàn miền:** không có chỉ số âm, ngoài mảng đếm, ngoài số bucket.
5. **Chi phí:** đo cả kích thước miền và số lượt/phân phối, không chỉ số phần tử.

Kiểm thử giúp phát hiện lỗi cài đặt; **chứng minh** cần dựa vào bất biến phân phối, cấu trúc khóa và các giả thiết đầu vào rõ ràng.

## 11. Bài tập có lời giải

### Bài 1 — Khi nào counting sort có lợi?

Dữ liệu gồm `n=200_000` điểm nguyên từ `0` đến `100`. Có cần một thuật toán so sánh `O(n log n)` không?

**Gợi ý đáp án:** không bắt buộc. Miền chỉ có `K=101` khóa, counting sort chạy `O(n+101)` và dùng mảng đếm rất nhỏ. Nếu các bản ghi khác nhau có cùng điểm và cần ổn định, dùng bản phân phối ổn định với bộ đệm `O(n)` như phần 3.

### Bài 2 — Counting sort với khóa âm

Cho `[-3, 1, -3, 0]` và miền `[-3,1]`. Hãy viết chỉ số mỗi giá trị vào count.

**Đáp án:** dùng `index=value-(-3)=value+3`: `-3→0`, `0→3`, `1→4`. Mảng đếm cuối có `K=5` ô và số lần tương ứng `[2,0,0,1,1]`.

### Bài 3 — Tại sao LSD cần ổn định?

Cho các số có hai chữ số `[31,12,21,13]`. Sau lượt hàng đơn vị ổn định có kết quả nào? Nếu lượt hàng chục không ổn định thì có nguy cơ gì?

**Đáp án:** `[31,21,12,13]`. Nếu lượt hàng chục đảo thứ tự nhóm chữ số chục bằng nhau, `12` và `13` có thể bị đảo, hoặc `31` và `21` bị đảo. Kết quả sai thứ tự toàn số dù mỗi lượt dường như đã phân nhóm.

### Bài 4 — Radix sort 32 bit có chấp nhận số âm không?

Một bạn cho rằng chỉ sắp lần lượt bốn byte của biểu diễn `int` nguyên gốc, coi mỗi byte là không dấu, đủ để thu thứ tự tăng của mọi `int`.

**Đáp án:** chưa đúng với số âm. Bit cao nhất của số âm là 1 nên nhóm byte cao sẽ bị đặt sau nhóm dương nếu diễn giải không dấu. Có thể đảo bit dấu bằng `x ^ Integer.MIN_VALUE` để trích các byte sắp theo thứ tự phù hợp.

### Bài 5 — Bucket sort có luôn tuyến tính?

Có `n` số thực đều bằng `0.51`, dùng `n` bucket và insertion sort bên trong. Có thể khẳng định `O(n)` xấu nhất không?

**Đáp án:** không. Tất cả rơi một bucket; insertion sort có chặn xấu `O(n²)` trên dữ liệu tổng quát (dù trường hợp **mọi khóa thật sự bằng nhau** thì insertion sort ổn định với điều kiện `>` chạy nhanh trên bộ này). Muốn tạo ví dụ thực sự đạt thời gian xấu, dùng **n khóa phân biệt nhưng cùng thuộc một bucket và xếp giảm dần**; khi đó insertion sort nội bộ làm `Θ(n²)` bước.

### Bài 6 — Chi phí của nén tọa độ

Có `n` số nguyên lớn, trước hết sắp các giá trị phân biệt để gán rank, sau đó counting sort theo rank. Có được tuyên bố tổng thời gian `O(n)` không?

**Đáp án:** không nếu bước tạo rank dựa trên sắp xếp so sánh `O(n log n)`. Counting sort sau đó có thể tuyến tính nhưng **toàn pipeline** không tuyến tính.

### Bài 7 — Chọn phương pháp cho chuỗi

Có một triệu mã ba ký tự, mỗi ký tự chỉ thuộc `'A'..'Z'`, cần thứ tự ASCII từ điển. Những thông tin nào có thể tận dụng?

**Gợi ý đáp án:** độ dài cố định `d=3`, bảng chữ số `R=26`, có thể LSD radix 3 lượt phân phối ổn định; thời gian `O(3(n+26))`, bộ nhớ phụ `O(n+26)`. Nếu mã dài biến thiên hoặc yêu cầu collation tiếng Việt, thiết kế phải đổi tương ứng.

## 12. Checklist lựa chọn trước khi triển khai

1. **Khóa là gì?** Số nguyên, chữ số cố định, chuỗi, số thực theo miền hay đối tượng tùy ý?
2. **Thông tin nào được phép dùng ngoài so sánh?** Miền `K`, cơ số `b`, độ dài `d`, ánh xạ bucket có được xác định và rẻ không?
3. **Miền rộng hơn số phần tử bao nhiêu?** Counting sort tốt khi `K` hợp lý; miền cực rộng thì không.
4. **Độ dài khóa có bị chặn không?** Radix sort trên `int` 32 bit có bốn lượt byte; chuỗi dài `d` phải tính theo `d`.
5. **Đầu vào có phân phối phù hợp không?** Bucket sort kỳ vọng nhanh khi phân phối không dồn lệch, không phải bảo đảm mọi trường hợp.
6. **Có phần tử âm, dấu, đầu mút hoặc Unicode không?** Cần xử lý đúng chỉ số bù, bit dấu, miền `[0,1)`, ký tự kết thúc.
7. **Có cần ổn định không?** Chọn cách tính vùng đích và chiều quét phù hợp; kiểm thử với bản ghi có ID.
8. **Bộ nhớ có đủ không?** Tính cả count, bucket, bộ đệm, boxing, số lượt và overhead thực tế.
9. **Số liệu độ phức tạp có đủ tham số không?** Viết `O(n+K)`, `O(d(n+b))` hoặc `O(b+n+Σ n_i²)` trước khi rút gọn trong điều kiện cụ thể.
10. **Có thể chứng minh đúng không?** Mọi phần tử được phân phối đúng một lần; thứ tự các nhóm đúng; nội bộ nhóm đúng; mối quan hệ ổn định/tiền điều kiện được giữ.

**Kết luận:** cận dưới `Ω(n log n)` ràng buộc **thuật toán chỉ nhận thông tin từ so sánh khóa tùy ý**. Nếu khai thác được **cấu trúc đã biết của khóa**, counting/radix/bucket sort có thể cải thiện đáng kể thời gian cho những miền dữ liệu phù hợp. Đổi lại, phải chứng minh đúng cả ánh xạ khóa, phân phối, tính ổn định và tính đủ phần tử; đồng thời tính chính xác **`K`, `d`, `b`, phân phối và bộ nhớ**. Không tồn tại một “sắp xếp tuyến tính cho mọi khóa tùy ý” chỉ bằng đổi tên thuật toán.
