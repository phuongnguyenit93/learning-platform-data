# Vì sao tăng dung lượng theo cấp số nhân cho chi phí khấu hao hằng số

Mảng động (*dynamic array*) cho phép thêm phần tử vào cuối dù bộ đệm lưu trữ bên dưới có kích thước cố định. Khi bộ đệm đầy, cấu trúc phải cấp phát vùng lớn hơn và sao chép các phần tử đang có. Việc sao chép có thể tốn **O(n)** cho một lần thêm, nhưng nhiều thư viện vẫn mô tả thao tác thêm cuối là **O(1) khấu hao** (*amortized O(1)*).

Điều đó không mâu thuẫn. Bí quyết nằm ở **cách chọn dung lượng mới**: nếu mỗi lần đầy, mảng động tăng sức chứa theo **một hệ số cố định lớn hơn 1** (ví dụ gấp đôi), số lần mở rộng trở nên thưa dần. Tổng công sao chép trong một chuỗi dài lần thêm chỉ tăng tuyến tính theo số phần tử đã thêm.

Bài này chứng minh nhận định đó bằng ví dụ, công thức tổng chi phí và cách phân bổ chi phí cho từng thao tác; đồng thời phân tích vì sao tăng từng ô lại chậm và việc tăng theo cấp số nhân đánh đổi những gì về bộ nhớ.

## 1. Một lần thêm cuối có hai trường hợp

Một mảng động thường quản lý:

- `buffer`: vùng lưu trữ liên tiếp của các phần tử;
- `size`: số phần tử logic hiện đang chứa;
- `capacity`: số ô mà bộ đệm hiện có thể chứa trước khi mở rộng.

Luôn phải duy trì bất biến `0 <= size <= capacity`. Phần tử hợp lệ nằm trong đoạn chỉ số `[0, size)`; các ô từ `size` đến `capacity - 1` chỉ là chỗ dự trữ.

Khi thêm `value` ở cuối:

| Điều kiện | Cách thực hiện | Chi phí thường gặp |
| --- | --- | --- |
| `size < capacity` | Ghi `buffer[size] = value`, sau đó tăng `size` | O(1) |
| `size == capacity` | Tạo bộ đệm lớn hơn, sao chép `size` phần tử cũ, thêm `value` | O(n) cho riêng lần này, với `n = size` |

Ví dụ, với `size = capacity = 4`:

```text
Trước thêm 50:
buffer cũ (capacity = 4):  [10][20][30][40]

Cấp phát buffer mới gấp đôi:
buffer mới (capacity = 8): [10][20][30][40][ ?][ ?][ ?][ ?]
                           \_____ 4 phần tử được sao chép ____/

Ghi phần tử mới:
buffer mới (capacity = 8): [10][20][30][40][50][ ?][ ?][ ?]
size = 5, capacity = 8
```

Lần thêm này phải sao chép bốn phần tử, song những lần thêm tiếp theo (cho đến khi bộ đệm tám ô đầy) chỉ cần ghi vào ô trống.

## 2. Thử nhân đôi dung lượng qua một chuỗi thao tác

Giả sử `size = capacity = 0` lúc khởi tạo. Khi mảng đầy, chọn:

```text
newCapacity = 1                 nếu capacity == 0
newCapacity = 2 * capacity      nếu capacity > 0
```

Theo dõi lần lượt chín thao tác thêm cuối:

| Lần thêm thứ | `size` trước khi thêm | `capacity` trước | `capacity` sau | Số phần tử cũ phải sao chép |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 0 | 0 | 1 | 0 |
| 2 | 1 | 1 | 2 | 1 |
| 3 | 2 | 2 | 4 | 2 |
| 4 | 3 | 4 | 4 | 0 |
| 5 | 4 | 4 | 8 | 4 |
| 6 | 5 | 8 | 8 | 0 |
| 7 | 6 | 8 | 8 | 0 |
| 8 | 7 | 8 | 8 | 0 |
| 9 | 8 | 8 | 16 | 8 |

Sau chín lần thêm, mảng chứa chín phần tử trong bộ đệm 16 ô. Toàn bộ số phần tử cũ được sao chép qua các lần mở rộng là:

\[
0+1+2+4+8=15.
\]

Ngoài 15 lần sao chép này, cấu trúc còn thực hiện chín lần ghi phần tử mới. Ta có thể hình dung tổng **24 thao tác ghi/sao chép ô** trong mô hình chi phí đơn giản, thay vì phải chép lại toàn bộ dữ liệu sau mọi lần thêm.

Quan sát dãy dung lượng:

```text
Số phần tử:  1   2   3   4   5   6   7   8   9
Capacity:   1   2   4   4   8   8   8   8  16
Copies:     0   1   2   0   4   0   0   0   8
```

Các lần sao chép lớn xuất hiện ít hơn theo thời gian: sau khi mở rộng từ tám lên 16 ô, còn chỗ cho bảy lần thêm tiếp theo mà không phải cấp phát lại.

## 3. Nếu chỉ tăng dung lượng thêm một ô thì sao?

Xét chiến lược khác: mỗi khi đầy chỉ đặt `newCapacity = capacity + 1`. Khi thêm lần lượt `n` phần tử vào mảng rỗng, lần thứ hai sao chép một phần tử, lần thứ ba sao chép hai phần tử, v.v.:

\[
T_{\text{sao chép}}(n)
=0+1+2+\dots+(n-1)
=\frac{n(n-1)}{2}.
\]

Suy ra tổng công sao chép là **O(n²)**. Nếu tính thêm một thao tác ghi mới cho mỗi phần tử, tổng chi phí vẫn là O(n²):

\[
T_{\text{thêm}}(n)=n+\frac{n(n-1)}{2}=O(n^2).
\]

Do đó thời gian khấu hao cho mỗi lần thêm trở thành **O(n)** tính trên một chuỗi `n` lần thêm. Đây là chi phí rất lớn khi xây dựng mảng từng phần tử một.

So sánh cùng chín lần thêm:

| Chính sách tăng trưởng | Dung lượng cuối | Tổng số phần tử cũ được sao chép |
| --- | ---: | ---: |
| Tăng từng ô: `c -> c + 1` | 9 | `0 + 1 + ... + 8 = 36` |
| Nhân đôi khi đầy | 16 | `0 + 1 + 2 + 4 + 8 = 15` |

Nhân đôi có thể giữ nhiều ô trống hơn, nhưng đổi lại giảm mạnh tổng chi phí sao chép khi số lần thêm tăng.

## 4. Chứng minh bằng tổng chi phí: nhân đôi cho O(1) khấu hao

Giả sử ta thực hiện `n` lần thêm cuối, bắt đầu từ bộ đệm rỗng, và dung lượng tăng theo chuỗi `1, 2, 4, 8, ...`. Tạm coi ghi hoặc sao chép một phần tử có chi phí hằng số.

**Bước 1: Đếm phần tử mới.** Mỗi lần thêm có đúng một phép ghi phần tử mới. Với `n` lần thêm, tổng công ghi là `n = O(n)`.

**Bước 2: Đếm các phần tử phải sao chép.** Sao chép chỉ xảy ra khi dung lượng cũ vừa đầy. Số phần tử cũ được sao chép ở từng lần mở rộng lần lượt là `1, 2, 4, 8, ...`. Nếu `p` là dung lượng lớn nhất đã được sao chép trước hoặc trong chuỗi, thì `p < n` (vì phải có ít nhất `p + 1` phần tử mới kích hoạt mở rộng bộ đệm sức chứa `p`). Tổng sao chép thỏa mãn:

\[
1+2+4+\cdots+p = 2p-1 < 2n
\]

với `p` là lũy thừa của hai; nếu chưa có lần sao chép nào, tổng bằng 0.

**Bước 3: Cộng hai thành phần.** Với đơn vị chi phí là một lần ghi hoặc sao chép ô:

\[
T(n) \le n + 2n = 3n = O(n).
\]

Vì có `n` thao tác thêm, **chi phí khấu hao** cho một lần thêm là:

\[
\frac{T(n)}{n}=O(1).
\]

Kết luận này nói về **tổng chi phí của cả chuỗi thao tác**. Nó không nói rằng thao tác kích hoạt mở rộng tự nhiên trở thành O(1): một lần thêm khi `size = capacity = n` vẫn phải xử lý O(n) phần tử cũ.

Trong thực tế, việc cấp phát và khởi tạo bộ đệm mới có thể tốn thời gian theo độ dài vùng cấp phát. Với chiến lược nhân đôi, tổng dung lượng của các lần cấp phát `1 + 2 + 4 + ...` cũng là cấp số nhân có tổng O(n), nên không làm thay đổi kết luận khấu hao theo mô hình chi phí thông dụng.

## 5. Chứng minh theo cách phân bổ chi phí (*accounting method*)

Có thể hiểu ý tưởng khấu hao như một cách **trả trước** cho những lần mở rộng tương lai. Giả sử:

- Ghi một phần tử mới tốn một đơn vị công.
- Sao chép một phần tử cũ tốn một đơn vị công.
- Mỗi lần `append` được tính trước **ba đơn vị**: một đơn vị trả chi phí ghi ngay, hai đơn vị để dành cho sao chép về sau.

Vì sao hai đơn vị để dành đủ dùng?

Sau khi tăng dung lượng từ `c/2` lên `c`, mảng cần thêm khoảng `c/2` phần tử cho đến khi đầy `c` ô. Trong khoảng này, mỗi lần thêm để dành hai đơn vị. Trước lần mở rộng tiếp theo từ `c` lên `2c`, số tín dụng tích lũy đủ để sao chép `c` phần tử:

\[
\underbrace{\frac{c}{2}}_{\text{số lần thêm từ đợt mở rộng trước}}
\times
\underbrace{2}_{\text{tín dụng mỗi lần}}
=c.
\]

Chẳng hạn sau khi bộ đệm tăng lên bốn ô, có hai lần thêm kể từ lúc bộ đệm được mở rộng từ hai lên bốn, tính cả lần thêm kích hoạt đợt mở rộng đó. Mỗi lần để dành hai đơn vị, tổng cộng bốn đơn vị đủ để sao chép bốn phần tử khi chuyển lên tám ô.

Với dung lượng khởi đầu một ô, lần thêm đầu tiên cũng có thể để dành tín dụng trả cho việc sao chép một phần tử ở lần mở rộng tiếp theo. Về sau lập luận lặp lại ở các dung lượng `2, 4, 8, ...`.

Như vậy, chi phí thực tế của một số lần thêm có thể rất lớn, nhưng khi thu phí cố định theo mỗi thao tác, tổng tín dụng luôn đủ trang trải sao chép. Đó là ý nghĩa của **O(1) khấu hao** theo phương pháp kế toán; tín dụng chỉ là công cụ phân tích, không phải vùng nhớ hay biến mà chương trình phải lưu.

### Phân tích khấu hao khác trung bình xác suất

Một nhận định trung bình có thể dựa vào giả định về xác suất xuất hiện của dữ liệu. Ngược lại, phân tích khấu hao ở đây dựa vào **cấu trúc của chuỗi thao tác và quy tắc mở rộng**, không cần giả định lần thêm nào là ngẫu nhiên.

| Độ phức tạp | Câu hỏi được trả lời |
| --- | --- |
| O(1) cho lần còn chỗ | Một lần thêm cụ thể làm bao nhiêu việc nếu bộ đệm chưa đầy? |
| O(n) cho lần phải mở rộng | Trường hợp xấu của một lần thêm khi đã có `n` phần tử là gì? |
| O(1) khấu hao | Trung bình phân bổ chi phí trên một chuỗi nhiều lần thêm liên tiếp là bao nhiêu? |

Không nên dùng chi phí khấu hao để hứa rằng mọi lần thêm đều đáp ứng giới hạn thời gian cứng như nhau. Hệ thống yêu cầu độ trễ ổn định vẫn phải tính đến những lần cấp phát lại lớn.

## 6. Tổng quát: tăng theo hệ số bất kỳ lớn hơn 1

Nhân đôi chỉ là một ví dụ. Chọn một **hằng số** `\alpha > 1` và mỗi lần đầy tăng dung lượng theo quy tắc:

\[
C_{k+1}=\lceil \alpha C_k \rceil,
\]

với dung lượng khởi đầu dương, chẳng hạn `C_0 = 1`. Ví dụ `\alpha = 1{,}5` sẽ cho dãy sức chứa tăng xấp xỉ `1, 2, 3, 5, 8, 12, ...`; một thư viện có thể sử dụng quy tắc làm tròn hoặc cấp phát khác.

Do `C_{k+1} \ge \alpha C_k`, các dung lượng trước một lần cấp phát lớn có thể được chặn trên bằng các số hạng của cấp số nhân theo hướng ngược lại. Giả sử `L` là dung lượng cũ lớn nhất từng phải sao chép trong chuỗi `n` lần thêm, khi đó:

\[
\begin{aligned}
T_{\text{sao chép}}(n)
&\le L + \frac{L}{\alpha}+\frac{L}{\alpha^2}+\cdots\\
&< \frac{\alpha}{\alpha-1}\,L\\
&< \frac{\alpha}{\alpha-1}\,n.
\end{aligned}
\]

Bất đẳng thức cuối đúng vì phải có nhiều hơn `L` phần tử mới để kích hoạt lần mở rộng sau khi bộ đệm `L` ô đầy. Nếu không hề mở rộng, tổng sao chép bằng 0.

Với `\alpha > 1` **cố định và không phụ thuộc vào `n`**, hệ số `\alpha/(\alpha-1)` là hằng số. Bởi thế:

\[
T_{\text{sao chép}}(n)=O(n),
\qquad
T_{\text{tất cả lần thêm}}(n)=O(n),
\]

và thêm cuối vẫn là **O(1) khấu hao**.

Điểm cần để ý: nếu chọn `\alpha` quá gần 1, ví dụ `1{,}1`, hằng số ẩn trong O(1) khấu hao có thể lớn hơn đáng kể. Nếu tỉ lệ tăng giảm dần theo kích thước đến mức mỗi lần chỉ cộng một ô, không thể áp dụng chứng minh với một `\alpha > 1` cố định; ta quay về trường hợp có tổng công O(n²).

## 7. Đổi công sao chép lấy bộ nhớ dự trữ

Lựa chọn hệ số tăng trưởng là một bài toán cân bằng:

| Chính sách | Số lần mở rộng | Dung lượng dự trữ | Nhận xét |
| --- | --- | --- | --- |
| Chỉ thêm một ô | Rất nhiều khi thêm liên tục | Ít ô trống | Chi phí sao chép tổng O(n²) |
| Nhân `1{,}5` | Ít hơn tăng từng ô | Vừa phải | O(1) khấu hao; hằng số sao chép lớn hơn khi hệ số tiến sát 1 |
| Nhân đôi | Ít hơn nữa | Có thể gần gấp đôi số phần tử ngay sau mở rộng | O(1) khấu hao, đơn giản để phân tích |
| Nhân hệ số rất lớn | Ít lần mở rộng | Có thể giữ nhiều ô dự trữ | Tăng tiêu thụ bộ nhớ |

Với chính sách nhân đôi, bắt đầu từ một ô và **chỉ thêm, không xóa hoặc chủ động `reserve`**, khi `size > 0`, `capacity` thường thỏa mãn `size <= capacity < 2 * size`. Sau khi mở rộng từ `c` lên `2c` và thêm một phần tử, mảng có `size = c + 1` và `capacity = 2c`. Đây là nguyên nhân việc thêm cuối đạt tốc độ tốt nhưng cần thêm bộ nhớ để giữ các ô chưa dùng.

Trong lúc cấp phát lại, có thể cả bộ đệm cũ lẫn mới cùng tồn tại cho đến khi sao chép xong, khiến bộ nhớ đỉnh lớn hơn lượng lưu trữ ổn định sau mở rộng. Khi dùng mảng chứa đối tượng, chi phí sao chép thực tế còn tùy kiểu phần tử và cách ngôn ngữ quản lý đối tượng.

Một số thư viện hỗ trợ **dành sẵn dung lượng** nếu biết trước quy mô, ví dụ `std::vector::reserve(k)` ở C++ hoặc `ArrayList.ensureCapacity(k)` ở Java. Dành sẵn chỗ có thể giảm các lần cấp phát lại trong giai đoạn thêm nhiều phần tử, nhưng `reserve`/`ensureCapacity` không tự tạo thêm phần tử logic. Bản thân lần dành sẵn chỗ cũng có chi phí nếu cần cấp phát và sao chép.

## 8. Thử nghiệm bằng Java: đếm số phần tử được sao chép

Đoạn mã sau mô phỏng chiến lược nhân đôi, đếm số phần tử cũ cần sao chép qua tất cả lần mở rộng và kiểm tra kết quả sau chín thao tác thêm.

```java
import java.util.Arrays;

public class GeometricGrowthDemo {
    static final class DynamicIntArray {
        private int[] buffer = new int[0];
        private int size = 0;
        private long copiedElements = 0;

        void append(int value) {
            if (size == buffer.length) {
                int oldCapacity = buffer.length;

                // Cài đặt học tập: tránh tràn int khi nhân đôi.
                if (oldCapacity > Integer.MAX_VALUE / 2) {
                    throw new IllegalStateException("Capacity qua lon de nhan doi");
                }
                int newCapacity = oldCapacity == 0 ? 1 : 2 * oldCapacity;

                int[] newBuffer = Arrays.copyOf(buffer, newCapacity);
                copiedElements += size;
                buffer = newBuffer;

                System.out.printf(
                    "Mo rong %d -> %d, sao chep %d phan tu%n",
                    oldCapacity, newCapacity, size
                );
            }

            buffer[size] = value;
            size++;
        }

        int size() {
            return size;
        }

        int capacity() {
            return buffer.length;
        }

        long copiedElements() {
            return copiedElements;
        }

        int get(int index) {
            if (index < 0 || index >= size) {
                throw new IndexOutOfBoundsException("index=" + index);
            }
            return buffer[index];
        }
    }

    public static void main(String[] args) {
        DynamicIntArray array = new DynamicIntArray();
        for (int value = 1; value <= 9; value++) {
            array.append(value * 10);
        }

        System.out.printf(
            "size=%d, capacity=%d, copied=%d, last=%d%n",
            array.size(), array.capacity(),
            array.copiedElements(), array.get(8)
        );
    }
}
```

Kết quả dự kiến:

```text
Mo rong 0 -> 1, sao chep 0 phan tu
Mo rong 1 -> 2, sao chep 1 phan tu
Mo rong 2 -> 4, sao chep 2 phan tu
Mo rong 4 -> 8, sao chep 4 phan tu
Mo rong 8 -> 16, sao chep 8 phan tu
size=9, capacity=16, copied=15, last=90
```

Mã dùng `Arrays.copyOf` để tạo bộ đệm lớn và sao chép nội dung cũ; `copiedElements` chỉ đếm các phần tử **đang dùng** (khi `size == oldCapacity`). Nó chưa phải là bộ đếm toàn bộ thời gian CPU, chi phí cấp phát hay bộ nhớ của máy ảo Java. Cài đặt thực tế còn phải xử lý giới hạn dung lượng của runtime và trường hợp không đủ bộ nhớ.

## 9. Các lỗi lập luận thường gặp

1. **“Một lần thêm cuối luôn O(1).”** Sai trong trường hợp xấu nhất: lần thêm kích hoạt cấp phát lại có thể sao chép O(n) phần tử.
2. **“Có một lần O(n) nên toàn bộ n lần thêm là O(n²).”** Kết luận đó không theo sau nếu các lần mở rộng thưa dần. Phải cộng **số lần sao chép thực sự** trên cả chuỗi.
3. **“Mọi cách tăng capacity đều cho O(1) khấu hao.”** Sai. Tăng từng ô có tổng sao chép O(n²); chứng minh ở đây cần hệ số tăng cố định lớn hơn 1.
4. **“Dành chỗ dư làm size tăng theo.”** Sai. `capacity` thay đổi số ô có thể chứa, còn `size` chỉ tăng khi thêm phần tử thành công.
5. **“O(1) khấu hao nghĩa là độ trễ luôn ổn định.”** Sai. Một đợt sao chép nhiều phần tử vẫn có thể tạo ra lần thêm chậm bất thường.
6. **“Số bản sao chỉ tính cho lần thêm cuối cùng.”** Sai. Trong phân tích khấu hao phải tính cả những lần mở rộng trước đó, chẳng hạn `1 + 2 + 4 + 8` khi thêm chín phần tử.
7. **“Nhân đôi không ảnh hưởng gì đến bộ nhớ.”** Sai. Dung lượng dự trữ và bộ nhớ đỉnh khi thay bộ đệm là chi phí đánh đổi cho việc ít phải cấp phát lại.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Một mảng động có `size = 7`, `capacity = 8`. Thêm một phần tử cuối cần sao chép mấy phần tử cũ? Sau thao tác, `size` và `capacity` bằng bao nhiêu?

**Đáp án:** Không cần sao chép. Sau thao tác, `size = 8`, `capacity = 8`.

**Câu 2.** Sau đó thêm tiếp một phần tử nữa theo chính sách nhân đôi. Lần thêm này phải sao chép bao nhiêu phần tử cũ?

**Đáp án:** Sao chép tám phần tử sang bộ đệm 16 ô, ghi phần tử mới, nên `size = 9`, `capacity = 16`.

**Câu 3.** Tại sao dãy công sao chép `1, 2, 4, 8, ...` có tổng tuyến tính theo số phần tử đã thêm?

**Đáp án:** Đây là cấp số nhân; tổng các số hạng trước không lớn hơn một hằng số nhân với số hạng lớn nhất. Số hạng lớn nhất phải nhỏ hơn số phần tử đã thêm để kích hoạt đợt sao chép đó, nên tổng công sao chép là O(n).

**Câu 4.** Một người đề xuất tăng dung lượng từ `c` lên `c + 1` mỗi khi đầy để tiết kiệm bộ nhớ. Khi thêm `n` phần tử từ mảng rỗng, tổng công sao chép sẽ là bao nhiêu?

**Đáp án:** `0 + 1 + ... + (n-1) = n(n-1)/2 = O(n²)`. Đánh đổi là tổng thời gian thêm lớn hơn đáng kể khi `n` tăng.

**Câu 5.** Nếu đổi hệ số nhân đôi thành một hằng số `1{,}5`, có còn đảm bảo O(1) khấu hao hay không?

**Đáp án:** Có, với chính sách làm tròn bảo đảm dung lượng mới tăng ít nhất theo hệ số `\alpha = 1{,}5 > 1`. Tổng chi phí sao chép vẫn là O(n), dù hệ số ẩn trong thời gian và lượng bộ nhớ dự trữ khác với nhân đôi.

**Câu 6.** Phân tích O(1) khấu hao của thêm cuối có tự động chứng minh rằng mọi chuỗi thao tác gồm chèn giữa, xóa giữa và thêm cuối đều O(1) mỗi thao tác không?

**Đáp án:** Không. Chèn hoặc xóa ở giữa có thể phải dời nhiều phần tử trong mỗi lần thực hiện, nên bản thân chúng thường có chi phí O(n). Kết quả khấu hao trong bài dành cho **thêm ở cuối** theo chính sách mở rộng hình học.

**Điểm ghi nhớ:** Cấp phát lại là một thao tác đắt, nhưng khi dung lượng tăng theo cấp số nhân, ta chỉ cần trả chi phí đó ngày càng thưa. Tổng số phần tử được sao chép trong `n` lần thêm cuối là O(n), nên chi phí khấu hao trên mỗi lần thêm là O(1), trong khi một lần thêm đơn lẻ vẫn có thể mất O(n).
