# Hệ số tăng trưởng và đánh đổi giữa sao chép với bộ nhớ dư

Một mảng động (*dynamic array*) có thể thêm phần tử vào cuối ngay cả khi bộ đệm bên dưới đã đầy. Khi đó, cấu trúc cấp phát một bộ đệm lớn hơn, sao chép các phần tử hiện có và tiếp tục thêm. Vấn đề thiết kế quan trọng là **nên tăng dung lượng bao nhiêu mỗi lần đầy?**

Nếu chỉ tăng thêm một ô, ta tiết kiệm chỗ trống nhưng phải cấp phát và sao chép quá thường xuyên. Nếu tăng lên gấp nhiều lần, ta giảm số lần sao chép nhưng giữ nhiều bộ nhớ chưa dùng và có thể gặp đỉnh bộ nhớ cao trong lúc thay bộ đệm. **Hệ số tăng trưởng** quyết định sự cân bằng này.

Bài học tập trung vào cách lựa chọn hệ số tăng trưởng, đo lường số lần sao chép, số ô dư, bộ nhớ đỉnh và liên hệ đến độ phức tạp khấu hao của mảng động. Đây là một ví dụ điển hình về việc lựa chọn cấu trúc dữ liệu và chiến lược quản lý bộ nhớ theo đặc điểm bài toán.

## 1. Mô hình bộ đệm và hệ số tăng trưởng

Mảng động được mô tả bằng ba thành phần:

- `buffer`: bộ đệm có các ô lưu trữ liên tiếp;
- `size`: số phần tử hợp lệ đang được dùng;
- `capacity`: số ô có thể chứa trong bộ đệm hiện tại.

Mọi thao tác phải duy trì bất biến:

\[
0 \leq \text{size} \leq \text{capacity}.
\]

Khi thêm cuối mà `size < capacity`, mảng chỉ cần ghi vào `buffer[size]` rồi tăng `size` lên một. Khi `size == capacity`, mảng phải mở rộng trước khi ghi.

Gọi `g` là **hệ số tăng trưởng** (*growth factor*). Một chính sách điển hình là:

\[
C_{\text{mới}}=\left\lceil g C_{\text{cũ}}\right\rceil,\qquad g>1,
\]

trong đó `C` là `capacity`. Nếu dung lượng hiện tại bằng không, cần một giá trị khởi tạo dương, chẳng hạn một ô; nếu không, nhân `0` với bất kỳ hệ số nào cũng vẫn bằng `0`.

Ví dụ:

| Hệ số | Khi bộ đệm 8 ô đầy, dung lượng mới | Số ô trống ngay sau khi thêm phần tử thứ 9 |
| --- | ---: | ---: |
| `g = 1,5` | `ceil(1,5 × 8) = 12` | 3 |
| `g = 2` | 16 | 7 |
| `g = 3` | 24 | 15 |

Ở cả ba trường hợp, `size` sau thao tác đều là `9`. Dung lượng tăng thêm chỉ tạo các ô **dự trữ**, không tạo phần tử logic mới. Hệ số tăng trưởng là một lựa chọn của cài đặt; không có quy tắc chung buộc mọi thư viện phải dùng đúng `1,5`, `2` hoặc `3`.

## 2. Tại sao tăng càng ít thì sao chép càng nhiều?

Mỗi lần mảng đầy tại `size = capacity = C`, thao tác mở rộng thường phải sao chép `C` phần tử đang sử dụng. Nếu chỉ cộng thêm một ô:

```text
capacity: 1 -> 2 -> 3 -> 4 -> 5 -> ... -> n
copy:           1    2    3    4   ...  n-1
```

Với `n` lần thêm vào mảng rỗng, tổng số phần tử cũ phải sao chép là:

\[
0+1+2+\dots+(n-1)=\frac{n(n-1)}2=O(n^2).
\]

Chỉ riêng công sao chép đã tăng theo bình phương số phần tử. Điều này xảy ra vì sau mỗi đợt mở rộng, mảng chỉ có **một ô trống** và sẽ đầy ngay sau lần thêm đó.

Với hệ số `g > 1` cố định, mỗi lần mở rộng cấp phát nhiều ô trống hơn. Ta không phải mở rộng ở mọi lần thêm: bộ đệm có dung lượng càng lớn thì số lần thêm có thể thực hiện trước đợt mở rộng tiếp theo càng nhiều.

```text
Minh họa tăng gấp đôi, khởi đầu từ capacity = 1:

capacity 1:  [A]                         đầy
capacity 2:  [A][B]                      đầy
capacity 4:  [A][B][C][ ]                còn 1 ô
             [A][B][C][D]                đầy
capacity 8:  [A][B][C][D][E][ ][ ][ ]    còn 3 ô

Một lần sao chép tốn công để đổi lấy nhiều lần thêm nhanh phía sau.
```

## 3. So sánh định lượng các hệ số 1,5; 2 và 3

Để so sánh công bằng, xét cùng mô hình:

1. Mảng ban đầu có `size = capacity = 0`.
2. Lần đầu thêm cấp phát một ô.
3. Những lần sau, khi đầy, dùng `newCapacity = ceil(g × oldCapacity)`.
4. Mỗi lần cấp phát lại, sao chép đúng `size` phần tử hợp lệ rồi mới thêm.
5. Không thực hiện xóa, chèn giữa hoặc thu nhỏ bộ đệm.

Sau **10 lần thêm cuối**:

| Hệ số `g` | Các mức dung lượng đã cấp phát | Số lần cấp phát | Tổng phần tử cũ được sao chép | Dung lượng cuối | Ô dư cuối |
| --- | --- | ---: | ---: | ---: | ---: |
| 1,5 | 1 → 2 → 3 → 5 → 8 → 12 | 6 | `1 + 2 + 3 + 5 + 8 = 19` | 12 | 2 |
| 2 | 1 → 2 → 4 → 8 → 16 | 5 | `1 + 2 + 4 + 8 = 15` | 16 | 6 |
| 3 | 1 → 3 → 9 → 27 | 4 | `1 + 3 + 9 = 13` | 27 | 17 |

Ta thấy một đánh đổi rõ ràng: hệ số nhỏ hơn sử dụng ít ô dư hơn tại thời điểm này, nhưng phải cấp phát nhiều lần hơn và sao chép nhiều phần tử cũ hơn.

Tuy nhiên, **không nên hiểu rằng hệ số lớn hơn luôn dẫn đến nhiều ô dư hơn ở mọi giá trị `size`**. Dung lượng tăng theo từng nấc; vị trí của `size` so với nấc gần nhất ảnh hưởng đáng kể. Với cùng quy tắc nhưng sau **20 lần thêm**:

| Hệ số `g` | Tổng phần tử cũ được sao chép | Dung lượng cuối | Ô dư cuối |
| --- | ---: | ---: | ---: |
| 1,5 | `1 + 2 + 3 + 5 + 8 + 12 + 18 = 49` | 27 | 7 |
| 2 | `1 + 2 + 4 + 8 + 16 = 31` | 32 | 12 |
| 3 | `1 + 3 + 9 = 13` | 27 | 7 |

Trong ví dụ 20 phần tử, `g = 3` và `g = 1,5` cùng kết thúc ở dung lượng 27, nhưng chính sách `g = 3` sao chép ít hơn nhiều. Điều cần xem xét là **xu hướng theo cả một dải quy mô**, chứ không chỉ kết quả tại một kích thước đơn lẻ.

## 4. Vì sao hệ số cố định lớn hơn 1 vẫn cho O(1) khấu hao?

Giả sử hệ số `g > 1` là một **hằng số** không phụ thuộc vào tổng số phần tử `n`, và mỗi đợt mở rộng luôn tăng dung lượng ít nhất theo hệ số đó.

Các mức dung lượng lần lượt tăng tối thiểu theo cấp số nhân. Khi nhìn từ lần cấp phát lớn nhất đã xảy ra ngược về các lần trước, dung lượng cũ của mỗi lần sao chép trước đó nhiều nhất bằng `1/g` lần dung lượng ở lần sau.

Gọi `L` là dung lượng cũ lớn nhất từng được sao chép trong một chuỗi `n` lần thêm. Nếu có lần sao chép đó, chắc chắn `L < n`, vì cần ít nhất `L + 1` phần tử để kích hoạt đợt mở rộng sau khi bộ đệm `L` ô đầy. Tổng sao chép được chặn trên bởi:

\[
\begin{aligned}
S(n)
&\leq L+\frac{L}{g}+\frac{L}{g^2}+\cdots\\
&<\frac{g}{g-1}L\\
&<\frac{g}{g-1}n.
\end{aligned}
\]

Với hệ số `g` cố định, `g/(g-1)` là một hằng số. Do đó:

\[
S(n)=O(n).
\]

Mỗi lần thêm còn ghi đúng một phần tử mới, tổng cộng `n` lần ghi. Cộng công ghi và công sao chép, cả chuỗi `n` lần thêm có chi phí **O(n)**. Suy ra **thêm cuối có chi phí O(1) khấu hao (*amortized*)**:

\[
\frac{O(n)}{n}=O(1).
\]

Đây là bảo đảm về **chi phí của cả chuỗi thao tác**, không phải bảo đảm mọi lần thêm riêng lẻ đều O(1). Một lần thêm kích hoạt mở rộng vẫn có thể phải sao chép O(n) phần tử.

### Hằng số ẩn thay đổi ra sao theo `g`?

Biểu thức `g/(g-1)` cho một chặn trên đơn giản về tổng số bản sao so với số lần thêm:

| `g` | `g/(g-1)` | Ý nghĩa định tính |
| --- | ---: | --- |
| 1,1 | 11 | Có thể sao chép nhiều do tăng dung lượng chậm |
| 1,5 | 3 | Số bản sao được chặn bởi hằng số nhân với `n` |
| 2 | 2 | Chặn trên nhỏ hơn |
| 3 | 1,5 | Chặn trên nhỏ hơn nữa |

Các số trong cột giữa là **hệ số của một bất đẳng thức chặn trên**, không phải số bản sao chính xác trung bình trên mỗi lần thêm hay thời gian chạy đo được. Việc làm tròn dung lượng, quản lý bộ nhớ, kích thước phần tử và đặc điểm cấp phát của runtime đều ảnh hưởng chi phí thực tế.

Nếu `g` tiến rất gần đến 1, chặn trên có thể rất lớn. Nếu chính sách tăng trưởng thực chất chỉ thêm một ô, không tồn tại một hệ số `g > 1` cố định dùng được cho mọi dung lượng, và phân tích khấu hao O(1) ở trên không còn áp dụng.

## 5. Đo lượng bộ nhớ dư: số ô và tỉ lệ

Ở một thời điểm, lượng chỗ dự trữ được đo bằng:

\[
\text{spare}=\text{capacity}-\text{size}.
\]

Khi `capacity > 0`, ta có thể đo tỉ lệ ô chưa dùng:

\[
\text{wasteRatio}=\frac{\text{capacity}-\text{size}}{\text{capacity}}.
\]

Ví dụ, mảng có `size = 10` và `capacity = 16` giữ sáu ô dự trữ; tỉ lệ ô chưa dùng là `6/16 = 37,5\%`. Đây là **tỉ lệ ô của bộ đệm**, không phải phần trăm bộ nhớ toàn chương trình.

Ngay sau khi mở rộng một bộ đệm `C` ô đang đầy rồi thêm một phần tử, ta có:

\[
\begin{aligned}
\text{size}_{\text{mới}}&=C+1,\\
\text{capacity}_{\text{mới}}&=\lceil gC\rceil,\\
\text{spare}_{\text{mới}}&=\lceil gC\rceil-(C+1).
\end{aligned}
\]

Với `C` lớn, bỏ qua sai số làm tròn và một phần tử vừa thêm, tỉ lệ ô dự trữ **ngay sau lần mở rộng** xấp xỉ:

\[
\frac{gC-C}{gC}=1-\frac{1}{g}.
\]

| Hệ số | Tỉ lệ dự trữ xấp xỉ ngay sau mở rộng lớn |
| --- | ---: |
| 1,5 | 33,3% |
| 2 | 50% |
| 3 | 66,7% |

Những con số này là mức xấp xỉ **ngay sau khi mở rộng**, không phải tỉ lệ dư cố định trong cả vòng đời mảng. Khi tiếp tục thêm vào các ô trống, `size` tăng còn `capacity` giữ nguyên, nên tỉ lệ ô dư giảm dần về 0 trước đợt mở rộng kế tiếp.

Nếu mỗi ô chiếm khoảng `b` byte, vùng lưu trữ ổn định cần xấp xỉ:

\[
\text{bufferBytes} \approx \text{capacity}\times b.
\]

Ví dụ, nếu mỗi ô lưu một tham chiếu 8 byte thì bộ đệm 16 ô chiếm khoảng 128 byte chỉ cho phần các ô. Đây là con số minh họa; kích thước tham chiếu phụ thuộc runtime và kiến trúc, còn dữ liệu đối tượng, phần đầu mảng và căn chỉnh bộ nhớ chưa được tính.

## 6. Bộ nhớ đỉnh khi phải sao chép có thể cao hơn

Mỗi lần cấp phát lại thường phải giữ **bộ đệm cũ** trong lúc tạo và sao chép sang **bộ đệm mới**. Nếu bộ đệm cũ có `C` ô và bộ đệm mới có `C' = \lceil gC\rceil` ô, số ô tồn tại đồng thời trong lúc chuyển có thể xấp xỉ:

\[
\text{peakBufferSlots}\approx C+C'\approx(1+g)C.
\]

Ví dụ, bộ đệm tám ô đã đầy, mỗi ô dài bốn byte:

| Hệ số | Bộ đệm mới | Tổng ô của hai bộ đệm tại thời điểm chuyển | Byte minh họa |
| --- | ---: | ---: | ---: |
| 1,5 | 12 ô | 20 ô | 80 byte |
| 2 | 16 ô | 24 ô | 96 byte |
| 3 | 24 ô | 32 ô | 128 byte |

Đây chỉ là bộ nhớ của **hai vùng ô** cần xét tại lần thay bộ đệm, không phải phép đo bộ nhớ đỉnh toàn tiến trình. Với runtime thu gom rác như Java, những bộ đệm cũ từ các đợt trước có thể chưa được thu hồi ngay; bộ nhớ đỉnh thực tế có thể cao hơn. Một trình cấp phát cũng có thể tạo ra chi phí quản lý và phân mảnh.

Hệ số lớn làm giảm số lần cấp phát lại, nhưng khi buộc phải mở rộng, yêu cầu vùng nhớ mới có thể lớn và gây tăng bộ nhớ đột ngột. Đây là lý do phải cân nhắc **giới hạn bộ nhớ** ngoài tổng công sao chép.

## 7. Ví dụ Java: kiểm tra cả số bản sao lẫn ô dư

Chương trình sau mô phỏng ba chính sách `g = 1,5`, `2` và `3`. Các bộ đếm chỉ ghi nhận **số phần tử logic cũ được sao chép**, **số lần cấp phát** và **số ô của hai bộ đệm cùng hiện diện khi thay vùng nhớ**; chúng không đo thời gian CPU hoặc bộ nhớ máy ảo thực tế.

```java
import java.util.Arrays;

public class GrowthFactorTradeoff {
    static final class DynamicIntArray {
        private final double factor;
        private int[] buffer = new int[0];
        private int size = 0;
        private long copiedElements = 0;
        private int allocationCount = 0;
        private long peakBufferSlots = 0;

        DynamicIntArray(double factor) {
            if (!Double.isFinite(factor) || factor <= 1.0) {
                throw new IllegalArgumentException("factor must be > 1");
            }
            this.factor = factor;
        }

        void append(int value) {
            if (size == buffer.length) {
                int oldCapacity = buffer.length;
                int newCapacity;

                if (oldCapacity == 0) {
                    newCapacity = 1;
                } else {
                    double target = Math.ceil(factor * oldCapacity);
                    if (target > Integer.MAX_VALUE || target <= oldCapacity) {
                        throw new IllegalStateException("capacity overflow");
                    }
                    newCapacity = (int) target;
                }

                int[] newBuffer = Arrays.copyOf(buffer, newCapacity);
                copiedElements += size;
                allocationCount++;
                peakBufferSlots = Math.max(
                    peakBufferSlots, (long) oldCapacity + newCapacity
                );
                buffer = newBuffer;
            }

            buffer[size] = value;
            size++;
        }

        void printStats() {
            System.out.println(
                "g=" + factor
                + ", size=" + size
                + ", capacity=" + buffer.length
                + ", spare=" + (buffer.length - size)
                + ", copied=" + copiedElements
                + ", allocations=" + allocationCount
                + ", peakSlots=" + peakBufferSlots
            );
        }
    }

    public static void main(String[] args) {
        for (double factor : new double[] {1.5, 2.0, 3.0}) {
            DynamicIntArray a = new DynamicIntArray(factor);
            for (int i = 0; i < 10; i++) {
                a.append(i);
            }
            a.printStats();
        }
    }
}
```

Kết quả dự kiến:

```text
g=1.5, size=10, capacity=12, spare=2, copied=19, allocations=6, peakSlots=20
g=2.0, size=10, capacity=16, spare=6, copied=15, allocations=5, peakSlots=24
g=3.0, size=10, capacity=27, spare=17, copied=13, allocations=4, peakSlots=36
```

Chẳng hạn, `peakSlots = 20` với `g = 1,5` xuất hiện ở đợt thay bộ đệm tám ô bằng bộ đệm 12 ô. Nếu yêu cầu mảng lớn hơn giới hạn mà runtime cho phép, hoặc hệ thống không đủ bộ nhớ, thao tác cấp phát vẫn có thể thất bại. Các thư viện thực tế thường có chiến lược xử lý giới hạn dung lượng riêng.

Khi sao chép `int[]`, phần tử được chuyển theo giá trị. Nếu mảng lưu **tham chiếu đối tượng** ở Java, sao chép các ô chỉ chép tham chiếu, không nhân bản sâu những đối tượng được trỏ tới. Với C++ `std::vector`, lần cấp phát lại có thể di chuyển/sao chép đối tượng và làm mất hiệu lực con trỏ, tham chiếu hoặc iterator gắn với bộ đệm cũ.

## 8. Chọn hệ số nào trong bài toán thực tế?

Không có một hệ số luôn tốt nhất. Quyết định phụ thuộc vào tần suất thêm, khả năng dự đoán kích thước, chi phí sao chép phần tử, độ trễ cho phép và giới hạn bộ nhớ:

| Hoàn cảnh | Hướng cân nhắc | Vì sao |
| --- | --- | --- |
| Thêm nhiều phần tử, bộ nhớ khá rộng | Tăng dung lượng theo hệ số vừa đến lớn | Giảm số lần cấp phát và chi phí sao chép tích lũy |
| Bộ nhớ giới hạn, dữ liệu có thể rất lớn | Cân nhắc hệ số vừa phải, giới hạn dung lượng và đo bộ nhớ đỉnh | Tránh xin vùng lưu trữ quá lớn khi mở rộng |
| Đã biết gần đúng số phần tử cuối | Dành sẵn dung lượng nếu API cho phép | Có thể giảm cấp phát lại trong chuỗi thêm |
| Cần độ trễ rất ổn định của từng thao tác | Xem xét trước đợt mở rộng hoặc cấu trúc lưu trữ khác | O(1) khấu hao không loại bỏ lần thêm O(n) |
| Mảng thường xuyên tăng rồi giảm mạnh | Xem xét chính sách thu nhỏ riêng | Giữ dung lượng lớn quá lâu tốn bộ nhớ; thu nhỏ quá thường xuyên lại gây sao chép |

Chẳng hạn, `std::vector::reserve(k)` ở C++ và `ArrayList.ensureCapacity(k)` ở Java cho phép yêu cầu chuẩn bị chỗ cho ít nhất `k` phần tử. **Dành sẵn dung lượng không làm `size` tăng lên `k`.** Bản thân thao tác dành chỗ cũng có thể cấp phát và sao chép một lần.

Khi xóa phần tử, nhiều mảng động **giữ nguyên `capacity`** để tái sử dụng. Khi đó tỉ lệ bộ nhớ dư có thể cao hơn mức xấp xỉ ngay sau mở rộng ở phần trước, vì các công thức ở đó giả định chỉ thêm và không thu nhỏ. Những thao tác như `shrink_to_fit` ở C++ hoặc `trimToSize` ở Java `ArrayList` có thể yêu cầu thu gọn, song chi tiết thực hiện tùy thư viện và có thể phát sinh công sao chép.

Không nên tự gán một hệ số tăng trưởng cụ thể cho thư viện nếu tài liệu của nó không cam kết. Ví dụ `ArrayList` ở Java không công bố `capacity()` để đọc trực tiếp dung lượng nội bộ; `list` ở Python cũng không có API chuẩn trả sức chứa hiện thời. Quy tắc cần nắm là **mảng động thường dành sẵn chỗ để đổi bộ nhớ lấy tốc độ thêm**, còn chính sách tăng thực tế do cài đặt quyết định.

## 9. Những hiểu lầm dễ gặp

1. **Hệ số lớn hơn luôn dùng nhiều bộ nhớ hơn ở mọi `size`.** Không chắc. Dung lượng tăng theo từng nấc; tại `size = 20`, hệ số `1,5` và `3` trong ví dụ đều kết thúc ở 27 ô.
2. **Hệ số nhỏ hơn luôn tốt vì tiết kiệm bộ nhớ.** Hệ số gần 1 có thể dẫn đến nhiều đợt cấp phát, nhiều phần tử bị sao chép và độ trễ tăng.
3. **Hệ số lớn làm mọi lần thêm đều O(1).** Một lần mở rộng vẫn cần sao chép O(n) phần tử cũ. O(1) là chi phí **khấu hao** cho cả chuỗi.
4. **Chỉ cần tính ô trống sau khi mở rộng.** Trong lúc thay bộ đệm có thể phải giữ đồng thời hai vùng lưu trữ, và runtime có thể chưa thu hồi ngay vùng cũ.
5. **Lượng bộ nhớ dư bằng `capacity × sizeof(element)`.** Đó là ước lượng cho **toàn bộ vùng ô**; bộ nhớ dành riêng cho ô dư chỉ xấp xỉ `(capacity - size) × sizeof(element)`, chưa tính chi phí khác.
6. **Có thể tính `newCapacity = floor(g × capacity)` mà không kiểm tra gì.** Với hệ số gần 1 và `capacity` nhỏ, kết quả có thể bằng dung lượng cũ, khiến thao tác không tiến triển. Làm tròn lên hoặc bảo đảm `newCapacity > capacity`.
7. **Phân tích khấu hao áp dụng cả khi mỗi lần thêm đều đi kèm thu nhỏ hoặc cấp phát tùy ý.** Chứng minh ở đây dành cho một chuỗi **chỉ thêm cuối**, không thu nhỏ, theo hệ số tăng trưởng cố định lớn hơn 1.

## 10. Tự kiểm tra

**Câu 1.** Một mảng có `size = capacity = 8`. Sau khi thêm một phần tử theo hệ số `g = 1,5`, `g = 2` và `g = 3`, dung lượng và số ô dư lần lượt là bao nhiêu?

**Đáp án:** Cả ba trường hợp có `size = 9`. Dung lượng mới lần lượt là `12, 16, 24`; số ô dư tương ứng là `3, 7, 15`.

**Câu 2.** Bắt đầu từ bộ đệm rỗng, cấp phát một ô ở lần thêm đầu. Với `g = 2` và 10 lần thêm, bộ đệm được cấp phát ở các dung lượng nào, và có bao nhiêu phần tử cũ được sao chép tổng cộng?

**Đáp án:** Các dung lượng `1, 2, 4, 8, 16`. Tổng phần tử cũ được sao chép là `1 + 2 + 4 + 8 = 15`.

**Câu 3.** Khi `capacity = 100`, `size = 100`, hệ số `g = 2`, sau khi mở rộng để thêm phần tử thứ 101, tỉ lệ ô dư xấp xỉ bao nhiêu?

**Đáp án:** Dung lượng mới 200, `size = 101`, số ô dư 99; tỉ lệ chính xác theo số ô là `99/200 = 49,5\%`, gần mức xấp xỉ 50% khi `C` lớn.

**Câu 4.** Một lần mở rộng từ 100 lên 150 ô xảy ra khi bộ đệm cũ đã đầy. Nếu mỗi ô chiếm 8 byte, hai bộ đệm có thể đồng thời chiếm khoảng bao nhiêu byte chỉ tính vùng ô?

**Đáp án:** `(100 + 150) × 8 = 2.000` byte. Chưa tính đầu mảng, bộ đếm, căn chỉnh hoặc các đối tượng được tham chiếu.

**Câu 5.** Vì sao `g = 1,5` và `g = 3` đều có thêm cuối O(1) khấu hao khi `g` là hằng số?

**Đáp án:** Tổng dung lượng cũ phải sao chép ở những lần mở rộng tạo thành một tổng bị chặn bởi cấp số nhân, nên tổng sao chép cho `n` lần thêm là O(n). Tuy vậy hằng số ẩn, số lần cấp phát, số ô dư và bộ nhớ đỉnh khác nhau.

**Câu 6.** Nếu dự kiến nhập 100.000 phần tử và thư viện hỗ trợ dành sẵn dung lượng, điều gì có thể cải thiện khi dùng `reserve(100000)` hoặc thao tác tương đương?

**Đáp án:** Có thể giảm các lần mở rộng và sao chép trong quá trình thêm. Dung lượng được đảm bảo ít nhất 100.000 ô sau khi dành chỗ thành công; số phần tử logic vẫn chỉ tăng khi các lệnh thêm thực sự chạy. Dành chỗ quá lớn so với nhu cầu sẽ giữ bộ nhớ dư.

Hệ số tăng trưởng là một **quyết định quản lý tài nguyên**: hệ số đủ lớn giúp tổng chi phí sao chép của nhiều lần thêm cuối chỉ là O(n), nhưng dùng thêm bộ nhớ để dự trữ và có thể tăng bộ nhớ đỉnh khi cấp phát lại. Khi lựa chọn chính sách, hãy đánh giá **cả số phần tử phải sao chép, số ô dư, thời điểm mở rộng và giới hạn bộ nhớ**, thay vì chỉ nhìn vào độ phức tạp O(1) khấu hao.
