# Bitset, bitmap nén và phân bố khóa

Khi lưu một **tập khóa số nguyên** thuộc miền hữu hạn, câu hỏi quan trọng không chỉ là “có bao nhiêu khóa đang có?” mà còn là “**những khóa đó phân bố như thế nào trong miền?**”. Hai tập có cùng 10.000 phần tử và cùng miền một triệu giá trị vẫn có thể khác xa về chi phí lưu trữ: một tập gồm 10 dải liên tiếp dài có thể nén thành vài khoảng, còn một tập rải rác ngẫu nhiên tạo ra hàng nghìn đoạn rất ngắn.

**Bitset** (*bit vector, bitmap dày đặc*) dành **một bit cho mỗi giá trị khóa có thể có**. Nó hỗ trợ thao tác thuộc tập, thêm, xóa, hợp và giao rất hiệu quả khi miền không quá lớn. **Bitmap nén** cố gắng giữ ý nghĩa “khóa nào đang có” nhưng tránh lưu những vùng lặp lại hoặc vùng rỗng không cần thiết. Hiệu quả nén phụ thuộc vào **mật độ, độ dài các dải liên tiếp và tính cục bộ của khóa**, chứ không chỉ tổng số phần tử.

Bài học trong chương **Khóa số nguyên** trình bày mô hình bitmap theo từ máy, phép bitwise và các truy vấn trên bit, so sánh bitset với mã hóa theo dải (*run-length encoding*, RLE), WAH/EWAH và Roaring Bitmap, phân tích phân bố khóa và bộ nhớ, rồi xây một ví dụ Java độc lập để quan sát sự khác nhau giữa **bitmap thường** và **biểu diễn bằng các khoảng khóa liên tiếp**.

## 1. Miền khóa `U`, số phần tử `n` và phân bố

Giả sử mọi khóa hợp lệ nằm trong đoạn nguyên đóng `[a,b]`. Kích thước miền là:

\[
U=b-a+1,\qquad \mathcal U=\{a,a+1,\ldots,b\}.
\]

Tập thực tế `S\subseteq\mathcal U` có `n=|S|` **khóa phân biệt**, nên `0\le n\le U`. Ta định nghĩa **mật độ**:

\[
\boxed{\rho=\frac{n}{U}.}
\]

Ví dụ một triệu ID khả dĩ nhưng chỉ 10.000 ID hiện có:

\[
U=1\,000\,000,\qquad n=10\,000,\qquad \rho=1\%.
\]

Tuy nhiên, mật độ **không mô tả đầy đủ hình dạng phân bố**.

### Cùng `U` và `n`, nhưng hình dạng khác nhau

Xét miền `0..31` và mỗi tập có đúng 8 khóa:

```text
Vị trí:        0         10        20        30
               |         |         |         |

A - một cụm:   11111111000000000000000000000000
    khóa:      0..7

B - cách đều:  10001000100010001000100010001000
    khóa:      0,4,8,12,16,20,24,28

C - hai cụm:   00001111000000000000111100000000
    khóa:      4..7 và 20..23
```

Cả ba tập có `\rho=8/32=25\%`. Nếu dùng **bitset dày đặc**, chúng cùng cần 32 bit payload. Nhưng nếu nén theo **dải khóa 1 liên tiếp**, A chỉ cần một dải, B cần tám dải, C cần hai dải.

Các đại lượng mô tả hình dạng hữu ích:

| Ký hiệu/đặc tính | Ý nghĩa |
| --- | --- |
| `U` | Số giá trị có thể có |
| `n` | Số khóa đang có |
| `\rho=n/U` | Mật độ |
| `r` | Số **dải liên tiếp tối đại** gồm các khóa đang có |
| Độ dài dải | Bao nhiêu khóa liên tiếp xuất hiện trong cùng một dải |
| Khoảng trống | Có bao nhiêu khóa không có mặt giữa các cụm |
| Phân bố theo khối | Các khóa tập trung vào vài vùng của miền hay trải đều |
| Tần suất cập nhật | Tập gần như bất biến hay thường xuyên thêm/xóa |

**Kết luận bước đầu:** muốn chọn định dạng bitmap tốt, phải xét thêm **`r` và phân bố theo vùng** ngoài `U`, `n`.

## 2. Bitset dày đặc: một bit cho mỗi khóa

Với miền được chuẩn hóa `0..U-1`, bitmap là dãy `U` bit:

\[
B[x]=
\begin{cases}
1,&x\in S,\\
0,&x\notin S.
\end{cases}
\]

Nếu khóa bắt đầu từ `a`, vị trí bit cho `x` là:

\[
\boxed{\operatorname{offset}(x)=x-a.}
\]

Ánh xạ này **một-một** trên đoạn `[a,b]`. Khóa âm hoàn toàn có thể dùng làm khóa nếu đổi sang offset không âm trước khi truy cập bitset.

Ví dụ `S=\{0,3,5,9\}` trong miền `0..15`:

```text
Chỉ số bit:  15 14 13 12 11 10  9  8  7  6  5  4  3  2  1  0
Trạng thái:   0  0  0  0  0  0  1  0  0  0  1  0  1  0  0  1

Mẫu bit viết từ cao xuống thấp: 0000 0010 0010 1001
Giá trị thập lục phân:          0x0229
```

Điểm mạnh của bitset là **không cần lưu từng khóa riêng**: vị trí bit đã thể hiện khóa. Nhưng số bit dành cho tập **phụ thuộc miền `U`**, kể cả khi chỉ có một bit 1.

### Tổ chức bitset theo từ máy

Với từ `w` bit, khóa đã chuẩn hóa `i` nằm trong:

\[
\operatorname{wordIndex}(i)=\left\lfloor\frac{i}{w}\right\rfloor,
\qquad
\operatorname{bitIndex}(i)=i\bmod w.
\]

Nếu `w=64` và `i=130`:

\[
130=2\cdot64+2,
\]

nên bit cần kiểm tra là **bit 2 của `words[2]`**.

```text
words[0] -> bit cho khóa 0..63
words[1] -> bit cho khóa 64..127
words[2] -> bit cho khóa 128..191
...
```

Dung lượng payload của bitmap theo từ máy:

\[
\boxed{
M_{\text{raw}}=
w\left\lceil\frac{U}{w}\right\rceil\text{ bit}
}
\]

Ví dụ dùng từ `long` Java 64 bit thì cần `8\lceil U/64\rceil` byte payload. Đây là **dung lượng mảng từ**; đối tượng `BitSet` của Java còn có header và metadata, đồng thời có thể chỉ cấp phát đến vùng bit cao nhất cần thiết.

## 3. Các phép toán trên bitmap

Giả sử có một mảng `long[] words` lưu `U` bit và đã kiểm tra `0\le i<U`. Với từ 64 bit:

```java
int wordIndex = i >>> 6;      // floor(i / 64)
int bitIndex = i & 63;        // i mod 64
long mask = 1L << bitIndex;

boolean present = (words[wordIndex] & mask) != 0L;
words[wordIndex] |= mask;     // Thêm khóa i.
words[wordIndex] &= ~mask;    // Xóa khóa i.
words[wordIndex] ^= mask;     // Đảo trạng thái, không phải "thêm".
```

**Lưu ý:** dịch bit trong Java có quy tắc lấy số vị trí dịch theo một số bit thấp của toán hạng. Với `long`, `1L << 64` **không** tạo bit thứ 64 mà tương đương dịch 0. Phải tách `wordIndex` và `bitIndex` trước khi dịch.

### Hợp, giao, hiệu tập

Nếu hai tập `A` và `B` dùng **cùng miền và cách ánh xạ bit**:

| Phép toán trên tập | Phép toán từ máy |
| --- | --- |
| `A\cup B` | `wordsA[i] \| wordsB[i]` |
| `A\cap B` | `wordsA[i] & wordsB[i]` |
| `A\setminus B` | `wordsA[i] & ~wordsB[i]` |
| Hiệu đối xứng `A\triangle B` | `wordsA[i] ^ wordsB[i]` |

Ví dụ:

```text
A = {1, 2, 3, 8}
B = {3, 4, 8}

A ∪ B = {1, 2, 3, 4, 8}
A ∩ B = {3, 8}
A \ B = {1, 2}
A △ B = {1, 2, 4}
```

Với `U` bit chia cho từ rộng `w`, một phép hợp/giao toàn bitmap thường cần xử lý:

\[
O\left(\left\lceil\frac{U}{w}\right\rceil\right)
\]

từ. Nếu toàn miền vừa trong **một từ máy**, phép hợp/giao có thể là **một phép bitwise** trong mô hình Word-RAM.

### Phép bù và những bit không thuộc miền

Nếu `U=70` mà mảng có hai từ 64 bit, từ cuối có 58 bit dự trữ **không thuộc miền**. Phép `~word` sẽ bật cả những bit dự trữ nếu không che lại. Một tập bù hợp lệ phải được định nghĩa **chỉ trên `0..U-1`**:

\[
\overline{S}=\mathcal U\setminus S.
\]

Khi thao tác mức từ, phải **mask phần đuôi** của từ cuối. `java.util.BitSet` giúp quản lý bit cao hơn theo giao diện của thư viện, nhưng cài đặt bitmap tùy chỉnh vẫn phải xử lý rõ giới hạn miền.

## 4. Những truy vấn không tự động có O(1)

Truy cập **một bit** thuộc một từ máy là O(1) theo mô hình Word-RAM; nhưng đừng suy ra mọi phép toán trên **cả tập** đều O(1).

### Đếm phần tử: `popcount`

Số phần tử đang có:

\[
|S|=\sum_{j=0}^{\lceil U/w\rceil-1}\operatorname{popcount}(words[j]).
\]

Nếu phải duyệt toàn mảng từ, chi phí là O(⌈U/w⌉). Có thể duy trì một biến `size` được cập nhật **chỉ khi bit thực sự đổi trạng thái**, từ đó truy vấn số phần tử trở thành O(1), nhưng mỗi thao tác thêm/xóa phải quản lý biến đếm đúng.

### Tìm phần tử tiếp theo

`successor(x)` hoặc `ceiling(x)` là khóa nhỏ nhất trong tập **lớn hơn** hoặc **không nhỏ hơn** `x`, tùy định nghĩa API. Một cách phổ biến:

1. Che các bit nằm trước cận trong từ đầu.
2. Nếu phần còn lại khác 0, xác định bit 1 thấp nhất bằng `numberOfTrailingZeros`.
3. Nếu bằng 0, tìm từ tiếp theo khác 0 rồi lấy bit 1 thấp nhất.

Với nhiều từ rỗng liên tục, thuật toán có thể quét nhiều từ. Trường hợp xấu theo miền là O(⌈U/w⌉), **không phải O(1)**.

```text
Khóa đang có: {2, 5, 70, 120}

ceiling(6):
  words[0] không còn bit bật từ bit 6 trở lên;
  sang words[1], lấy bit 6 -> khóa 64+6 = 70.
```

Với Java, `Long.numberOfTrailingZeros(0L)` trả **64**, không phải một chỉ số bit hợp lệ. Cần kiểm tra từ khác 0 trước khi dùng vị trí được trả về.

### Rank, select và quét khoảng

- `rank(x)`: đếm số khóa không vượt `x` (hoặc nhỏ hơn `x`, tùy quy ước).
- `select(k)`: lấy khóa ở vị trí thứ `k` theo thứ tự tăng.
- `range(a,b)`: liệt kê khóa thuộc một khoảng.

Một bitmap thuần có thể đếm/quét qua nhiều từ để trả lời các truy vấn này. Để đạt các giới hạn nhanh hơn cho `rank/select`, cần **cấu trúc bổ trợ** như prefix counts hoặc chỉ mục thứ bậc chuyên biệt.

Với đoạn dài `\ell=b-a+1`, nếu **cài đặt phép quét giới hạn theo các từ giao với đoạn**, thời gian có thể ước tính:

\[
O\left(\left\lceil\frac{\ell}{w}\right\rceil+r+1\right)
\]

với `r` số khóa được xuất ra. Nhưng một API như `BitSet.nextSetBit(start)` **không nhận cận trên**; lời gọi cuối có thể quét xa hơn `b` trước khi thấy một khóa ngoài đoạn hoặc hết bitset. Không lấy công thức có giới hạn theo đoạn làm bảo đảm worst-case của mọi API.

## 5. Bộ nhớ bitset và chi phí của miền lớn

Giả sử bitset được cấp phát dày đặc theo toàn bộ `U`:

| Miền `U` | Bitset payload lý tưởng | Ghi chú |
| ---: | ---: | --- |
| 64 | 8 byte | Vừa một từ `long` |
| 1.024 | 128 byte | 16 từ 64 bit |
| 1.000.000 | 125.000 byte ≈ 122,1 KiB | Không phụ thuộc `n` |
| 1.000.000.000 | 125.000.000 byte ≈ 119,2 MiB | Có thể tốn nhiều RAM nếu chỉ có ít khóa |
| `2^{32}` | 536.870.912 byte = 512 MiB | Chỉ riêng dữ liệu bit |

Các số trong bảng là **payload lý tưởng** trước overhead đối tượng, làm tròn từ và đặc tính cấp phát. Mặc dù 512 MiB có thể không quá lớn với một số máy chủ, cấu trúc đó vẫn phải tương thích **giới hạn mảng/chỉ số của runtime**, chi phí khởi tạo và nhu cầu chứa nhiều bitmap đồng thời.

### Khi nào bitset thô là lựa chọn tốt?

- `U` đủ nhỏ hoặc vừa với ngân sách RAM.
- Truy vấn `contains` và thêm/xóa bit diễn ra thường xuyên.
- Cần giao/hợp/hiệu **nhiều tập trên cùng miền**.
- Tập không nhất thiết phải được duyệt theo thứ tự khóa liên tục.
- Phân bố rất phân tán làm nén theo dải ít hiệu quả.

Một bitmap không nén có kích thước **ổn định theo `U`**; tập rỗng và tập đầy vẫn có cùng payload nếu cấp phát cố định theo toàn miền.

## 6. Nén theo dải liên tiếp (RLE)

Thay vì lưu mỗi bit, ta có thể lưu một danh sách các **dải khóa 1 liên tiếp tối đại**. Gọi:

\[
R=\{[s_0,e_0],[s_1,e_1],\ldots,[s_{r-1},e_{r-1}]\}
\]

với các khoảng đóng, không rỗng và được sắp tăng. Khi chuẩn hóa:

\[
s_i\le e_i,\qquad e_i+1<s_{i+1}.
\]

Bất đẳng thức thứ hai nói rằng hai dải khác nhau không giao nhau **và không kề sát nhau**; nếu kề sát, chúng phải gộp thành một dải dài hơn.

Ví dụ:

```text
Bitmap trong miền 0..23:

000111110000000011100000
   3..7         16..18

Tập khóa: {3,4,5,6,7,16,17,18}
Biểu diễn dải: [(3,7), (16,18)]
```

Từ tám khóa, ta chỉ lưu **hai khoảng**. Không cần lưu riêng `4,5,6,17` vì chúng đã được ngầm định trong các dải.

### Hai kiểu “RLE” dễ nhầm

**RLE cho cả chuỗi bit** có thể lưu luân phiên các đoạn 0 và 1:

```text
3 số 0, 5 số 1, 8 số 0, 3 số 1, 5 số 0.
```

**Danh sách các dải khóa 1** (dùng trong ví dụ Java của bài) chỉ lưu các đoạn 1:

```text
[(3,7), (16,18)]
```

Hai cách đều khai thác các đoạn lặp, nhưng **định dạng và overhead** khác nhau. Danh sách dải phải lưu **vị trí bắt đầu và kết thúc** hoặc `(start,length)`; RLE bit có thể lưu độ dài và quy tắc xen kẽ.

### Sức chứa theo số dải

Nếu mỗi cận của một dải được lưu bằng một số nguyên 32 bit, chi phí payload thô là:

\[
\boxed{M_{\text{runs}}=2r\cdot4=8r\text{ byte}.}
\]

Trong khi bitmap lý tưởng có `U/8` byte, bỏ qua làm tròn. Danh sách dải nhỏ hơn bitmap khi:

\[
8r<\frac{U}{8}
\quad\Longleftrightarrow\quad
\boxed{r<\frac{U}{64}}.
\]

Đây chỉ là **điểm hòa vốn về payload** cho **cặp cận 32 bit**, chưa tính metadata, căn chỉnh, chỉ mục khối, số bit cần để biểu diễn cận hoặc các cơ chế nén cận/độ dài.

**Điểm nổi bật:** `r`, không chỉ `n`, quyết định lợi ích của dạng lưu dải.

### Truy vấn và cập nhật trên danh sách dải

Nếu các dải được sắp và không giao nhau:

- `contains(x)`: tìm nhị phân dải ứng viên → O(log r).
- `cardinality()`: tổng các độ dài `e_i-s_i+1`, O(r) nếu tính lại; O(1) nếu duy trì biến đếm.
- Duyệt toàn bộ khóa: ít nhất O(n) vì phải xuất `n` khóa.
- Truy vấn số mục trong `[a,b]`: tìm dải đầu bằng nhị phân rồi xét các dải giao khoảng.
- Thêm `x`: có thể tạo dải mới, kéo dài hoặc **gộp hai dải**.
- Xóa `x`: có thể rút ngắn hoặc **tách một dải thành hai**.

Với danh sách dải lưu trong mảng, một lần chèn/xóa gây thay đổi số dải có thể phải **dịch O(r) ô**, ngay cả khi đã tìm được dải trong O(log r). Vì vậy **không được gọi mọi phép thêm/xóa trên RLE là O(log r)**. Dạng nén phù hợp nhất khi dữ liệu **tĩnh hoặc ít thay đổi**, hoặc khi bộ thư viện có cấu trúc cập nhật được tối ưu riêng.

### Cẩn thận với khóa cực đại

Nếu các dải lưu cận kiểu `int`, viết `end+1==nextStart` có thể tràn khi `end=Integer.MAX_VALUE`. Khi so sánh tính kề sát nên dùng:

```java
((long) end + 1L) == (long) nextStart
```

Tương tự, tổng `e-s+1` cho toàn bộ miền khóa `int` có thể lên đến `2^{32}`, vượt `int` có dấu; dùng `long` cho cardinality.

## 7. Phân bố khóa quyết định khả năng nén

### 7.1. Cụm liên tục

Nếu 10.000 khóa chiếm 10 dải, mỗi dải 1.000 khóa:

```text
U = 1.000.000
n = 10.000
r = 10

Bitmap raw: ~125.000 byte
Danh sách dải int32: 8*r = 80 byte payload
```

Đây là trường hợp **nén theo dải cực kỳ hiệu quả**. Chênh lệch chỉ nói về dữ liệu payload, không bao gồm overhead thực tế của đối tượng/mảng.

### 7.2. Thưa nhưng rải rác

Với 10.000 khóa nằm rải rác thành gần 10.000 dải đơn:

```text
U = 1.000.000
n = 10.000
r ≈ 10.000

Bitmap raw: ~125.000 byte
Danh sách dải int32: ~80.000 byte
Danh sách khóa int32: 40.000 byte
```

RLE có thể nhỏ hơn bitmap raw nhưng **lớn hơn mảng số nguyên đã sắp**, vì mỗi khóa đơn lẻ cần hai cận `start,end`. Một cấu trúc nén hỗn hợp có thể chọn **danh sách khóa** cho các vùng rất thưa thay vì cứ mã hóa mọi khóa thành một dải.

### 7.3. Đậm đặc nhưng rải rác những lỗ nhỏ

Giả sử các bit độc lập có xác suất bằng 1 là `p`. Một dải 1 bắt đầu ở vị trí đầu khi bit 0 bằng 1, hoặc tại vị trí `i>0` khi bit trước bằng 0 và bit hiện tại bằng 1. Với mô hình Bernoulli độc lập:

\[
\boxed{\mathbb E[r]=p+(U-1)p(1-p).}
\]

Nếu `p=0.5` và `U` rất lớn, số dải 1 kỳ vọng gần `U/4`. Với cặp cận 32 bit, chi phí dải xấp xỉ `2U` byte, trong khi bitset chỉ `U/8` byte — **lớn hơn khoảng 16 lần** theo mô hình payload đó.

Nếu `p=0.9`, số dải vẫn khoảng `0.09U`: các lỗ rải rác chia những đoạn 1 thành nhiều dải, khiến RLE theo cặp cận vẫn có thể kém hơn bitmap. **Mật độ cao không bảo đảm nén RLE tốt**.

### 7.4. Lặp theo chu kỳ

Các khóa “mỗi ID thứ 4” tạo nhiều dải ngắn:

```text
100010001000100010001000...
```

Mặc dù mẫu có quy luật, danh sách dải 1 vẫn cần gần một dải cho **mỗi khóa**. Muốn nén quy luật này tốt cần **định dạng khác** (ví dụ tham số cấp số cộng), không được mặc định RLE sẽ tìm ra mọi kiểu quy luật.

### Bảng đánh giá phân bố

| Phân bố | Tỷ lệ 1 | Số dải 1 `r` | Bitset raw | RLE theo dải | Biểu diễn đáng xem |
| --- | --- | --- | --- | --- | --- |
| Một dải liên tiếp | Có thể thấp/cao | Rất ít | Kích thước cố định | Rất tốt | Dải |
| Vài cụm dài | Bất kỳ | Ít | Ổn định | Thường tốt | Dải/Roaring run |
| Điểm đơn rải rác | Thấp | Gần `n` | Có thể lãng phí | Hai cận mỗi khóa | Array/sparse container |
| Ngẫu nhiên mật độ trung bình | Khoảng 50% | Rất nhiều | Thường tốt | Có thể phình lớn | Bitmap bitset |
| Gần đầy, ít lỗ lớn | Cao | Có thể ít | Tốt | Có thể rất tốt | Dải hoặc bù tập |
| Gần đầy, lỗ nhỏ phân tán | Cao | Nhiều | Tốt | Không chắc tốt | Bitmap |

## 8. WAH và EWAH: nén theo từ máy

**WAH** (*Word-Aligned Hybrid*) và **EWAH** (*Enhanced Word-Aligned Hybrid*) là các họ mã hóa bitmap nén được thiết kế để thao tác trên những vùng **từ máy** thay vì từng bit rời rạc.

Ý tưởng khái quát:

- Một số từ chứa các bit hỗn hợp và được giữ như **literal word**.
- Những đoạn dài các từ giống nhau, đặc biệt từ **toàn 0** hoặc **toàn 1**, có thể được mô tả bằng **fill/run word**.
- Bộ mã hóa thường dùng các trường bit/metadata để phân biệt từ literal và từ mô tả số lượng từ lặp.

Ví dụ:

```text
Các từ 64 bit logic:

0000...0000
0000...0000
0000...0000
1010...0011
1111...1111
1111...1111

Mô hình nén:
  "3 từ 0" + "1 literal hỗn hợp" + "2 từ 1"
```

Không nên hiểu WAH/EWAH là một giao thức nhị phân duy nhất với các trường bit giống hệt nhau: **chi tiết mã hóa tùy biến thể và thư viện**. Nhưng mục tiêu chung là **giảm dung lượng cho những chuỗi từ lặp dài** trong khi vẫn có thể thực hiện phép toán bitmap theo dòng, không cần giải nén toàn bộ từng bit trước.

### Khi chúng hoạt động tốt và kém

**Thuận lợi:** khóa phân bố theo các vùng lớn đầy/rỗng, nhiều từ 0 hoặc 1 liên tiếp, cần hợp/giao của các bitmap lớn.

**Bất lợi:** các từ liên tục chứa mẫu bit hỗn hợp hoặc ngẫu nhiên; khi đó có ít đoạn từ lặp để nén. Metadata fill/literal có thể khiến dữ liệu nén **không nhỏ hơn** bitmap gốc.

Khác với RLE từng bit hay danh sách dải `(start,end)`, WAH/EWAH thường đặt trọng tâm ở **ranh giới từ máy**. Một dải 1 ngắn lệch ranh giới có thể trở thành literal, chứ không nhất thiết được biểu diễn bằng một dải hoàn hảo.

## 9. Roaring Bitmap: chia miền thành khối và chọn container

**Roaring Bitmap** là một họ cấu trúc bitmap nén phân vùng các khóa 32 bit thành nhiều **khối theo các bit cao**, rồi dùng biểu diễn thích hợp cho phần **bit thấp** của mỗi khối.

Ở mức khái niệm, một khóa 32 bit không dấu `x` được tách:

\[
high=x\gg16,\qquad low=x\ \&\ 0xffff.
\]

Các khóa có cùng `high` thuộc cùng một miền con rộng `2^{16}=65\,536` giá trị thấp. Mỗi miền con có thể chọn container theo phân bố:

| Loại container | Lưu gì? | Phù hợp khi |
| --- | --- | --- |
| **Array container** | Danh sách `low` đang có, thường đã sắp | Ít khóa trong khối |
| **Bitmap container** | Một bit cho từng `low` trong khối 65.536 khóa | Khối khá đậm đặc |
| **Run container** | Các dải liên tiếp của `low` | Khóa trong khối có nhiều đoạn dài |

Ví dụ:

```text
Các khóa 32 bit không dấu:

  high=0x0012:
      low = {5, 100, 500}       -> array thuận lợi.

  high=0x0034:
      low = {0..60000}          -> bitmap hoặc run.

  high=0x0056:
      low = {100..200, 500..900} -> run thuận lợi.

Một chỉ mục cấp cao ánh xạ high -> container tương ứng.
```

**Ý tưởng chủ chốt:** hai vùng của **cùng một bitmap** có thể có mật độ rất khác nhau. Roaring không bắt buộc chọn một định dạng cho toàn bộ miền; nó chọn theo **từng khối**.

### Vì sao ranh giới 4.096 phần tử thường được nhắc đến?

Một bitmap container gồm 65.536 bit, tức:

\[
65536/8=8192\text{ byte}.
\]

Một array container lưu mỗi `low` bằng 16 bit (2 byte) cần `2c` byte cho `c` khóa. Về payload:

\[
2c=8192\Rightarrow c=4096.
\]

Do đó khoảng `c=4096` là **ngưỡng hòa vốn payload** hay gặp khi chọn array/bitmap container. Thư viện thực tế còn xét overhead, run containers, việc cập nhật và quy tắc chuyển dạng; đừng xem `4096` là bắt buộc tuyệt đối cho mọi triển khai Roaring.

### Khóa có dấu trong cấu trúc dùng bit 32 không dấu

Java `int` có dấu. Nếu cấu trúc được định nghĩa theo thứ tự **không dấu**, các phép tách bit vẫn làm việc trên mẫu bit, nhưng thứ tự số học của `int` âm và dương khác thứ tự không dấu. Muốn bảo toàn thứ tự **có dấu**, có thể biến đổi khóa bằng cách đảo bit dấu rồi so sánh kết quả theo thứ tự không dấu, hoặc dùng bộ so sánh/chuẩn hóa của thư viện.

Không trộn thứ tự có dấu/không dấu giữa bước mã hóa, tìm vị trí và quét kết quả.

### Những đánh đổi của Roaring

- **Tiết kiệm bộ nhớ** nếu nhiều khối thưa hoặc nhiều dải liên tiếp.
- **Thao tác tập hợp** có thể chọn thuật toán phù hợp với từng cặp container (array-array, array-bitmap, bitmap-bitmap…).
- Cần metadata, quản lý nhiều container và xử lý chuyển loại khi mật độ thay đổi.
- Thời gian và kích thước phụ thuộc **phân bố theo khối**, không chỉ `U,n`; không có một mức nén cố định cho mọi đầu vào.

Những khái niệm ở đây đủ để lựa chọn định dạng; bài này **không triển khai lại định dạng nhị phân chuẩn** của một thư viện Roaring cụ thể.

## 10. Mô hình so sánh bộ nhớ có điều kiện

Với `U=1\,000\,000` và khóa biểu diễn bằng 32 bit, xem các phép tính **payload** sau:

| Trường hợp | `n` | `r` | Raw bitmap (`U/8`) | Sorted int keys (`4n`) | Run pairs (`8r`) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Ít cụm liên tục | 10.000 | 10 | 125.000 B | 40.000 B | **80 B** |
| 10.000 khóa rời rạc | 10.000 | 10.000 | 125.000 B | **40.000 B** | 80.000 B |
| Trung bình 50% ngẫu nhiên | ≈500.000 | ≈250.000 | **125.000 B** | ≈2.000.000 B | ≈2.000.000 B |
| 900.000 khóa, vài dải dài | 900.000 | 2 | 125.000 B | 3.600.000 B | **16 B** |

Các cột áp dụng **những định dạng khác nhau** nhưng chưa cộng overhead mảng, header, chỉ mục dải, container và vùng dự trữ. Không so một cột payload lý tưởng với số byte bộ nhớ thực của thư viện rồi kết luận thư viện kém.

### Vì sao `r` quan trọng hơn “thưa/đậm đặc” với RLE?

Với RLE dạng cặp cận, chi phí là `8r` byte bất kể mỗi dải dài một hay một triệu khóa. Vì vậy:

- **Tập thưa, theo cụm**: có thể nén rất tốt.
- **Tập thưa, các điểm rời**: dải có thể kém hơn một mảng khóa.
- **Tập đậm đặc, liền mạch**: có thể nén cực tốt.
- **Tập đậm đặc, nhiều lỗ lẻ**: RLE có thể phình lớn.

Đối với **WAH/EWAH**, quan sát cần thêm số lượng từ toàn 0/toàn 1 liên tiếp. Đối với **Roaring**, cần xem số khóa và số dải **trong từng khối 2^16**.

## 11. Hiệu năng phép toán: bộ nhớ không phải tiêu chí duy nhất

Một định dạng có dung lượng nhỏ không nhất thiết thực thi mọi phép toán nhanh nhất.

| Nhu cầu | Bitset raw | RLE theo cặp dải | WAH/EWAH | Roaring |
| --- | --- | --- | --- | --- |
| `contains(x)` | O(1) truy cập từ trong Word-RAM | O(log r) nếu dải đã sắp | Tùy chỉ mục/khả năng định vị đoạn | Phụ thuộc tìm container + loại container |
| `add/remove(x)` | O(1) cho bit đã có vùng nhớ | Có thể O(r) vì dịch danh sách dải | Có thể cần sửa run/literal | Phụ thuộc container, chuyển dạng |
| `A∩B` / `A∪B` | Duyệt O(U/w) từ | Quét/trộn các dải của hai tập | Xử lý dòng từ nén | Phối hợp thuật toán theo container |
| Duyệt `n` khóa | Quét từ + xuất phần tử | O(n+r) để sinh các khóa | Phụ thuộc đoạn nén và kết quả | Phụ thuộc số container/khóa |
| Bộ nhớ | O(U) bit | O(r) cặp cận | Phụ thuộc độ dài dải từ | Phụ thuộc phân bố container |
| Điểm mạnh | Bitwise nhanh, đơn giản | Dải dài, dữ liệu ít sửa | Dòng bitmap có đoạn từ lặp | Phân bố hỗn hợp theo khối |

Các biểu thức là **mô hình thuật toán** của các biểu diễn nêu trong bài, không phải benchmark hay hợp đồng độ phức tạp của tất cả thư viện. Cùng tên cấu trúc có thể có cách đánh chỉ mục phụ, bộ nhớ đệm hoặc lựa chọn container khác nhau.

### Tập thường xuyên cập nhật

Nếu mỗi thao tác thêm/xóa thay một bit trong mảng đủ nhỏ, bitset thô có lợi thế **sửa tại chỗ**. Với danh sách dải, thêm một khóa có thể làm **gộp hai dải**, xóa có thể làm **tách một dải**, và mảng dải có thể cần dịch nhiều phần tử.

Nếu bitmap được dùng chủ yếu cho **lọc phân tích**, hợp/giao tập và truy vấn lặp đi lặp lại trên dữ liệu ít đổi, các định dạng nén có thể bù chi phí duy trì bằng giảm dung lượng và I/O.

### Đọc dữ liệu từ đĩa

Lưu ít byte hơn có thể giảm số trang và lượng I/O, nhưng giải mã đòi CPU. Kết quả thực tế còn phụ thuộc cache, thiết bị lưu trữ, mức độ phân tán khóa và tốc độ các phép toán SIMD/bitwise. **Đừng chọn chỉ theo tỷ lệ nén mà không đo thông lượng truy vấn.**

## 12. Java hoàn chỉnh: bitmap giới hạn và nén thành các dải

Chương trình tự chứa dưới đây minh họa **hai biểu diễn trên cùng tập khóa**:

1. `BoundedBitmap` dùng `java.util.BitSet`, ánh xạ khóa `int` trong đoạn có thể âm sang offset không âm.
2. `RunSet` dùng các cặp `(start,end)` đã sắp tăng và không giao nhau, xây từ danh sách khóa đang có; `contains` dùng tìm nhị phân trên cận cuối các dải.

Chương trình hỗ trợ:

- `add/remove/contains` và biến đếm `size` đối với bitmap.
- `range` và `union/intersection/difference` của các bitset **cùng miền**.
- Mã hóa thành các dải liên tiếp tối đại, `contains` và `countInRange` trên danh sách dải.
- Ví dụ một tập **theo cụm** và một tập **rời rạc**, cùng các phép toán tập hợp.

**Giới hạn:** `RunSet` trong ví dụ được **xây lại từ tập khóa**, chưa triển khai cập nhật nén tại chỗ; nó là một **biểu diễn RLE kiểu danh sách dải**, không phải WAH/EWAH/Roaring. `BitSet` dùng chỉ số `int`, nên constructor áp giới hạn `maxUniverse` của ví dụ để tránh yêu cầu cấp phát quá lớn.

```java
import java.util.ArrayList;
import java.util.BitSet;
import java.util.List;
import java.util.TreeSet;

public class IntegerBitmapDistributionDemo {

    static final class BoundedBitmap {
        private final int minKey;
        private final int maxKey;
        private final int universe;
        private final BitSet bits;
        private int size;

        BoundedBitmap(int minKey, int maxKey, int maxUniverse) {
            if (minKey > maxKey || maxUniverse < 1) {
                throw new IllegalArgumentException("Invalid universe");
            }
            long u = (long) maxKey - (long) minKey + 1L;
            if (u > Integer.MAX_VALUE || u > maxUniverse) {
                throw new IllegalArgumentException(
                    "Universe exceeds implementation budget");
            }
            this.minKey = minKey;
            this.maxKey = maxKey;
            this.universe = (int) u;
            this.bits = new BitSet(universe);
        }

        private int offset(int key) {
            if (key < minKey || key > maxKey) {
                throw new IllegalArgumentException(
                    "Key outside universe: " + key);
            }
            return (int) ((long) key - (long) minKey);
        }

        int size() {
            return size;
        }

        int universeSize() {
            return universe;
        }

        boolean contains(int key) {
            return bits.get(offset(key));
        }

        boolean add(int key) {
            int i = offset(key);
            if (bits.get(i)) {
                return false;
            }
            bits.set(i);
            size++;
            return true;
        }

        boolean remove(int key) {
            int i = offset(key);
            if (!bits.get(i)) {
                return false;
            }
            bits.clear(i);
            size--;
            return true;
        }

        List<Integer> values() {
            List<Integer> out = new ArrayList<>(size);
            // universe is capped to an int range in this demo.
            for (int i = bits.nextSetBit(0);
                    i >= 0;
                    i = bits.nextSetBit(i + 1)) {
                out.add((int) ((long) minKey + i));
            }
            return out;
        }

        List<Integer> range(int from, int to, int limit) {
            if (limit < 0) {
                throw new IllegalArgumentException("Negative limit");
            }
            List<Integer> out = new ArrayList<>();
            if (from > to || limit == 0) {
                return out;
            }
            long low = Math.max((long) minKey, (long) from);
            long high = Math.min((long) maxKey, (long) to);
            if (low > high) {
                return out;
            }
            int first = (int) (low - (long) minKey);
            int last = (int) (high - (long) minKey);
            // nextSetBit lacks an upper-bound parameter.
            for (int i = bits.nextSetBit(first);
                    i >= 0 && i <= last && out.size() < limit;
                    i = bits.nextSetBit(i + 1)) {
                out.add((int) ((long) minKey + i));
            }
            return out;
        }

        private void requireSameUniverse(BoundedBitmap other) {
            if (other == null || this.minKey != other.minKey
                    || this.maxKey != other.maxKey) {
                throw new IllegalArgumentException(
                    "Both sets must use identical key universe");
            }
        }

        private BoundedBitmap emptyLike() {
            return new BoundedBitmap(minKey, maxKey, universe);
        }

        BoundedBitmap union(BoundedBitmap other) {
            requireSameUniverse(other);
            BoundedBitmap out = emptyLike();
            out.bits.or(this.bits);
            out.bits.or(other.bits);
            out.size = out.bits.cardinality();
            return out;
        }

        BoundedBitmap intersection(BoundedBitmap other) {
            requireSameUniverse(other);
            BoundedBitmap out = emptyLike();
            out.bits.or(this.bits);
            out.bits.and(other.bits);
            out.size = out.bits.cardinality();
            return out;
        }

        BoundedBitmap difference(BoundedBitmap other) {
            requireSameUniverse(other);
            BoundedBitmap out = emptyLike();
            out.bits.or(this.bits);
            out.bits.andNot(other.bits);
            out.size = out.bits.cardinality();
            return out;
        }

        void verifySize() {
            if (size != bits.cardinality()
                    || bits.nextSetBit(universe) >= 0) {
                throw new IllegalStateException("Invalid bitmap");
            }
        }
    }

    // Immutable, sorted list of maximal inclusive runs.
    static final class RunSet {
        private final int[] starts;
        private final int[] ends;
        private final long cardinality;

        private RunSet(int[] starts, int[] ends, long cardinality) {
            this.starts = starts;
            this.ends = ends;
            this.cardinality = cardinality;
        }

        static RunSet fromKeys(List<Integer> input) {
            TreeSet<Integer> sorted = new TreeSet<>(input);
            List<Integer> s = new ArrayList<>();
            List<Integer> e = new ArrayList<>();
            long count = 0;

            boolean hasRun = false;
            int runStart = 0;
            int runEnd = 0;
            for (int key : sorted) {
                count++;
                if (!hasRun) {
                    runStart = key;
                    runEnd = key;
                    hasRun = true;
                } else if ((long) runEnd + 1L == (long) key) {
                    runEnd = key;
                } else {
                    s.add(runStart);
                    e.add(runEnd);
                    runStart = key;
                    runEnd = key;
                }
            }
            if (hasRun) {
                s.add(runStart);
                e.add(runEnd);
            }
            int[] starts = new int[s.size()];
            int[] ends = new int[e.size()];
            for (int i = 0; i < s.size(); i++) {
                starts[i] = s.get(i);
                ends[i] = e.get(i);
            }
            return new RunSet(starts, ends, count);
        }

        int runCount() {
            return starts.length;
        }

        long cardinality() {
            return cardinality;
        }

        long estimatedPayloadBytes() {
            return 8L * starts.length; // two int32 bounds per run
        }

        // First run whose end is >= key, or runCount.
        private int firstEndingAtOrAfter(int key) {
            int lo = 0, hi = ends.length;
            while (lo < hi) {
                int mid = lo + (hi - lo) / 2;
                if (ends[mid] < key) {
                    lo = mid + 1;
                } else {
                    hi = mid;
                }
            }
            return lo;
        }

        boolean contains(int key) {
            int i = firstEndingAtOrAfter(key);
            return i < starts.length && starts[i] <= key;
        }

        // Count without materializing every key in the interval.
        long countInRange(int from, int to) {
            if (from > to) {
                return 0L;
            }
            long total = 0L;
            for (int i = firstEndingAtOrAfter(from);
                    i < starts.length && starts[i] <= to;
                    i++) {
                long left = Math.max((long) starts[i], (long) from);
                long right = Math.min((long) ends[i], (long) to);
                if (left <= right) {
                    total += right - left + 1L;
                }
            }
            return total;
        }

        @Override
        public String toString() {
            List<String> pieces = new ArrayList<>();
            for (int i = 0; i < starts.length; i++) {
                pieces.add("[" + starts[i] + "," + ends[i] + "]");
            }
            return pieces.toString();
        }
    }

    public static void main(String[] args) {
        BoundedBitmap clustered = new BoundedBitmap(0, 1023, 2048);
        for (int key = 10; key <= 19; key++) {
            clustered.add(key);
        }
        for (int key = 200; key <= 209; key++) {
            clustered.add(key);
        }
        for (int key = 500; key <= 509; key++) {
            clustered.add(key);
        }

        BoundedBitmap scattered = new BoundedBitmap(0, 1023, 2048);
        for (int key : new int[] {3, 23, 44, 64, 87,
                                 108, 130, 151, 177, 199,
                                 220, 247}) {
            scattered.add(key);
        }

        RunSet clusterRuns = RunSet.fromKeys(clustered.values());
        RunSet scatterRuns = RunSet.fromKeys(scattered.values());

        System.out.println("Cluster n=" + clustered.size()
            + ", runs=" + clusterRuns.runCount()
            + ", representation=" + clusterRuns);
        System.out.println("Scatter n=" + scattered.size()
            + ", runs=" + scatterRuns.runCount());
        System.out.println("Raw bitmap bytes="
            + (clustered.universeSize() / 8));
        System.out.println("Cluster run-pair payload="
            + clusterRuns.estimatedPayloadBytes() + " bytes");
        System.out.println("Scatter run-pair payload="
            + scatterRuns.estimatedPayloadBytes() + " bytes");

        System.out.println("cluster contains(205)="
            + clusterRuns.contains(205));
        System.out.println("cluster count[15,205]="
            + clusterRuns.countInRange(15, 205));
        System.out.println("cluster range[16,203] limit 8="
            + clustered.range(16, 203, 8));

        System.out.println("union size="
            + clustered.union(scattered).size());
        System.out.println("intersection="
            + clustered.intersection(scattered).values());
        System.out.println("difference size="
            + clustered.difference(scattered).size());

        System.out.println("remove(205)=" + clustered.remove(205));
        System.out.println("contains(205)=" + clustered.contains(205));
        System.out.println("readd(205)=" + clustered.add(205));
        clustered.verifySize();
        scattered.verifySize();
        System.out.println("Invariant checks: OK");
    }
}
```

Kết quả dự kiến:

```text
Cluster n=30, runs=3, representation=[[10,19], [200,209], [500,509]]
Scatter n=12, runs=12
Raw bitmap bytes=128
Cluster run-pair payload=24 bytes
Scatter run-pair payload=96 bytes
cluster contains(205)=true
cluster count[15,205]=11
cluster range[16,203] limit 8=[16, 17, 18, 19, 200, 201, 202, 203]
union size=42
intersection=[]
difference size=30
remove(205)=true
contains(205)=false
readd(205)=true
Invariant checks: OK
```

### Vì sao các kết quả đúng?

**Số dải theo cụm:** mỗi đoạn 10–19, 200–209, 500–509 tạo một dải tối đại, nên `r=3`. Với `n=30`, danh sách dải chỉ cần 3 cặp cận. Các khóa của `scattered` cách nhau ít nhất một khóa vắng mặt, nên mỗi khóa tạo **một dải riêng**, `r=12`.

**`count[15,205]`:** phần giao với dải 10–19 là 15–19 có 5 khóa; với dải 200–209 là 200–205 có 6 khóa; dải 500–509 không giao. Tổng là **11 khóa**.

**Phép giao:** 12 khóa rải rác ở `scattered` không trùng bất kỳ khóa nào trong ba cụm. Vì vậy giao rỗng, hợp có `30+12=42` khóa và hiệu `clustered\setminus scattered` vẫn còn 30 khóa.

**`RunSet.contains`:** tìm nhị phân theo **cận cuối** của dải. Dải đầu có `end>=key` là ứng viên duy nhất; nếu `start<=key` thì khóa thuộc dải.

**`RunSet.countInRange`:** cộng độ dài các phần giao giữa đoạn truy vấn và những dải đang có, không tạo ra một danh sách chứa mọi khóa thuộc đoạn trước khi đếm.

### Độ phức tạp của ví dụ Java

| Phương thức | Mức chi phí |
| --- | --- |
| `BoundedBitmap.contains/add/remove` | O(1) truy cập bit trong mô hình Word-RAM với vùng lưu đã cấp phát |
| `BoundedBitmap.union/intersection/difference` | Phụ thuộc số từ bitset mà thư viện xử lý; không phải O(1) cho toàn `U` |
| `BoundedBitmap.values` | Phụ thuộc số từ được duyệt và `n` |
| `RunSet.fromKeys` | O(n log n) trường hợp xấu để đưa khóa vào `TreeSet`, rồi O(n) tạo dải |
| `RunSet.contains` | O(log r) |
| `RunSet.countInRange` | O(log r+q) với `q` số dải giao/cần xét |
| `RunSet.estimatedPayloadBytes` | O(1) |

**Giới hạn của ví dụ:** mã không triển khai định dạng RLE có cấu trúc siêu dữ liệu tối ưu, WAH/EWAH, Roaring, chỉ mục rank/select hay truy cập đồng thời. Phép cộng giới hạn chỉ tính trên miền nhỏ và dữ liệu minh họa, không là kết quả benchmark CPU/I/O. Các hạn chế cấp phát của Java có thể thấp hơn cả `maxUniverse` nếu môi trường không đủ RAM.

## 13. Cách chọn biểu diễn theo workload

Nên bắt đầu từ các câu hỏi cụ thể:

1. **Miền `U` lớn đến đâu?** Một bitmap dày đặc sẽ chiếm khoảng `U/8` byte, cộng phần phụ.
2. **Có bao nhiêu khóa `n` và độ dài các dải ra sao?** Hãy đo `r` hoặc thống kê số khóa/cụm.
3. **Các khóa phân bố đều hay tập trung theo khối?** Roaring có thể chọn container khác nhau cho các khối khác nhau.
4. **Tập cập nhật thường xuyên không?** Bitset thô có thao tác thay bit rất đơn giản; RLE phải có logic tách/gộp dải.
5. **Thao tác quan trọng là gì?** Kiểm tra thuộc tập, hợp/giao, quét khoảng, rank/select hay truy vấn kế tiếp.
6. **Mục tiêu chính là RAM, dung lượng đĩa hay thời gian truy vấn?** Nén tốt có thể giảm I/O nhưng tăng CPU.

| Workload | Lựa chọn đáng cân nhắc | Cần kiểm tra thêm |
| --- | --- | --- |
| Miền nhỏ, nhiều phép membership và cập nhật | **Bitset raw** | Bộ nhớ `U`, tốc độ truy cập bit |
| Nhiều tập cùng miền, hợp/giao rất thường xuyên | **Bitset raw**, WAH/EWAH hoặc Roaring | Tốc độ AND/OR, I/O, mật độ |
| Tập gần như tĩnh gồm các dải dài | **RLE/danh sách dải** hoặc run containers | `r` và chi phí truy vấn |
| Tập thưa với khóa rời rạc | **Mảng khóa đã sắp**, HashSet/cây hoặc Roaring array | Cần thứ tự hay không, cập nhật nhiều không |
| Phân bố khác nhau rõ rệt giữa các khối | **Roaring Bitmap** | Container, metadata và thao tác chính |
| Dữ liệu ngẫu nhiên khá đậm đặc | **Bitset raw/bitmap containers** | RLE có thể phình, kiểm tra thực tế |
| Khóa 64 bit cực thưa trong miền rất rộng | Cấu trúc thưa/chỉ mục phân cấp hoặc biến thể bitmap 64 bit phù hợp | Không cấp phát trực tiếp `2^{64}` bit |
| Truy vấn predecessor/successor phức tạp | Cây cân bằng hoặc cấu trúc tiền nhiệm chuyên biệt | Worst-case, thứ tự, độ trễ |

Nếu dùng thư viện nén hiện có, cần đo kích thước sau nén, thời gian tạo/cập nhật, độ trễ các truy vấn tiêu biểu và chi phí giải tuần tự hóa. **Không có một phương pháp nén luôn thắng** trên mọi phân bố khóa.

## 14. Kiểm tra tính đúng đắn khi đổi biểu diễn

Cho tập chuẩn `S` trong `TreeSet<Integer>` và bitmap được tạo từ chính các khóa của `S`. Một bộ test có thể:

1. Thêm/xóa khóa ở những vị trí **đầu/cuối của từ máy**: 0, 63, 64, 127, 128…
2. Thử các khóa âm qua `offset(x)=x-a`; xác minh cận thấp và cận cao.
3. So sánh `contains(x)` cho mọi khóa thuộc một miền kiểm thử nhỏ.
4. So sánh `bitmap.values()` với danh sách đã sắp từ `TreeSet`.
5. Mã hóa thành `RunSet`, rồi kiểm tra mọi khóa trong miền: kết quả membership phải **giống bitmap**.
6. Với các khoảng ngẫu nhiên, so sánh `countInRange(a,b)` với số khóa trong oracle thuộc đoạn.
7. Với hai tập, đối chiếu `OR/AND/AND NOT` với phép hợp/giao/hiệu của hai oracle.
8. Thử tập **rỗng**, tập **đầy**, chỉ một khóa, các dải dài, dải cách đúng một lỗ, và dữ liệu rải rác.

### Bất biến của danh sách dải

Với `RunSet` lưu `r` dải:

\[
\begin{aligned}
starts[i]&\le ends[i],\\
ends[i]+1&<starts[i+1]\quad(0\le i<r-1),\\
cardinality&=\sum_{i=0}^{r-1}\bigl(ends[i]-starts[i]+1\bigr).
\end{aligned}
\]

Tất cả phép tính khoảng và cardinality cần thực hiện trong kiểu đủ rộng, chẳng hạn `long` nếu khóa là `int`. Bộ kiểm tra phải phát hiện **dải giao nhau, dải kề nhau chưa gộp, thứ tự dải sai và bộ đếm không khớp**.

### Tránh lỗi đặc biệt khi dùng `BitSet`

`BitSet` nhận chỉ số bit kiểu `int`. Một số nguyên `int` bất kỳ **không thể** tự động dùng làm chỉ số nếu miền có số âm hoặc lớn hơn giới hạn. Cần ánh xạ đúng và kiểm tra ngân sách.

`nextSetBit` trả `-1` khi không tìm thấy; không được dùng `-1` làm một khóa có mặt. Nếu muốn biểu diễn khóa âm `-1`, phải ánh xạ và trả về giá trị khóa **sau khi** xử lý trạng thái không tìm thấy riêng.

## 15. Sai lầm phổ biến

1. **Chỉ dựa trên `n/U` để đo khả năng nén.** Hai tập cùng mật độ có thể có số dải `r` rất khác.
2. **Gọi mọi bitmap nén là RLE.** WAH/EWAH và Roaring có định dạng và chiến lược riêng.
3. **Cho rằng dữ liệu thưa luôn nén tốt thành dải.** Các khóa rời rạc có thể cần một cặp cận cho mỗi khóa.
4. **Cho rằng dữ liệu đậm đặc luôn nén RLE tốt.** Nhiều lỗ nhỏ gây nhiều dải.
5. **Nhầm `U` với `n`.** Bitset raw cấp phát theo số khả năng, không theo số khóa hiện có.
6. **Không tính metadata/container.** Payload lý tưởng không bằng dung lượng bộ nhớ thật.
7. **Dùng `1L<<64` để bật bit 64.** Phép dịch Java quay theo số bit thấp; phải chọn từ kế tiếp và bit 0.
8. **Quên che bit ngoài miền sau phép NOT.** Có thể tạo khóa không hợp lệ ở cuối từ.
9. **Cho rằng mọi `popcount` trên cả bitmap đều O(1).** Đếm lại toàn bitmap có thể đi qua O(U/w) từ.
10. **Cho rằng tìm `successor` O(1) vì truy cập một bit O(1).** Có thể quét nhiều từ rỗng.
11. **Áp độ phức tạp quét có cận lên `BitSet.nextSetBit` không có cận trên.** Lời gọi cuối có thể đi xa hơn đoạn hỏi.
12. **Tính độ dài dải bằng `end-start+1` trong `int` ở cận cực trị.** Có thể tràn; dùng `long`.
13. **Gộp dải bằng phép `end+1` trong `int`.** Nếu `end` là max int, phép tính có thể tràn.
14. **Cho rằng danh sách dải hỗ trợ thêm/xóa O(log r) do tìm nhị phân.** Mảng dải vẫn có thể phải dịch O(r) phần tử.
15. **So sánh những bitmap có miền hoặc quy ước dấu khác nhau mà không chuẩn hóa.** OR/AND có thể ghép các vị trí không cùng ý nghĩa.
16. **Giả định ngưỡng 4096 của container là luật cố định mọi thư viện Roaring.** Overhead và chiến lược triển khai có thể khác.
17. **Dùng dấu bit cao để so sánh khóa không dấu bằng phép so sánh `int` có dấu.** Thứ tự sẽ sai ở nửa miền.
18. **Nghĩ rằng định dạng nhỏ nhất luôn có truy vấn nhanh nhất.** Giải mã, cache, SIMD và cập nhật đều ảnh hưởng.
19. **Bỏ qua chi phí tạo chỉ mục/nén.** Dữ liệu cập nhật liên tục có thể tốn công chuyển dạng container và bảo trì dải.
20. **Lưu dữ liệu theo bitmap nhưng quên xác minh cardinality và phép tập hợp.** Mỗi thao tác phải giữ đúng tập khóa.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Miền `[0,999]` có bao nhiêu vị trí bit nếu dùng bitset thô?

**Đáp án:** `U=1000` bit, tương đương 125 byte payload lý tưởng trước làm tròn từ máy và metadata.

**Câu 2.** Nếu `U=1\,000\,000` và `n=10\,000`, mật độ là bao nhiêu?

**Đáp án:** `n/U=1\%`.

**Câu 3.** Hai tập cùng `U` và `n` có bắt buộc nén RLE tốt như nhau không?

**Đáp án:** Không. Hiệu quả nén dải phụ thuộc **số dải liên tiếp tối đại `r`** và độ dài của chúng.

**Câu 4.** Trong mảng từ 64 bit, vị trí bit `130` thuộc từ nào và bit nào?

**Đáp án:** `wordIndex=130/64=2`, `bitIndex=130\bmod64=2`.

**Câu 5.** Bitset có các bit bật `\{0,3,5,9\}` trong miền `0..15` có mẫu bit 16 bit là gì khi viết từ cao xuống thấp?

**Đáp án:** `0000\,0010\,0010\,1001`, tức `0x0229`.

**Câu 6.** Hợp và giao của hai bitmap cùng miền sử dụng phép toán bitwise nào?

**Đáp án:** OR cho hợp, AND cho giao.

**Câu 7.** Vì sao phải mask những bit dư trong từ cuối khi lấy bù bitmap?

**Đáp án:** NOT có thể bật cả bit ở các vị trí `\ge U`; những vị trí đó không tương ứng khóa hợp lệ.

**Câu 8.** `contains(x)` trên một bitset thô có thể O(1), nhưng `successor(x)` có luôn O(1) không?

**Đáp án:** Không. `successor` có thể phải quét nhiều từ toàn 0.

**Câu 9.** Với bitmap `000111110000000011100000` trên miền 0..23, danh sách dải khóa 1 là gì?

**Đáp án:** `[(3,7),(16,18)]`.

**Câu 10.** Danh sách dải gồm `r=10` cặp cận 32 bit chiếm bao nhiêu byte payload?

**Đáp án:** `10\times8=80` byte, chưa tính overhead.

**Câu 11.** Trong mô hình raw bitmap `U/8` byte và dải `8r` byte, RLE nhỏ hơn raw bitmap khi nào?

**Đáp án:** Khi `8r<U/8`, tức `r<U/64`, theo mô hình payload đã giả định.

**Câu 12.** Tại sao tập có 10.000 khóa rời trong một triệu khả năng có thể phù hợp với mảng khóa đã sắp hơn RLE theo cặp cận?

**Đáp án:** Mảng khóa 32 bit cần khoảng 40 KB, còn 10.000 dải đơn cần khoảng 80 KB payload.

**Câu 13.** Với bit độc lập xác suất bằng 1 là `p` trên `U` vị trí, công thức số dải 1 kỳ vọng là gì?

**Đáp án:** `\mathbb E[r]=p+(U-1)p(1-p)`.

**Câu 14.** WAH/EWAH chủ yếu nén dạng lặp nào?

**Đáp án:** Các đoạn nhiều **từ máy toàn 0 hoặc toàn 1**, kết hợp từ literal chứa bit hỗn hợp.

**Câu 15.** Ba loại container thông dụng trong Roaring Bitmap là gì?

**Đáp án:** Array container, bitmap container và run container.

**Câu 16.** Tại sao ngưỡng 4096 phần tử thường xuất hiện khi so array và bitmap container của khối 16 bit?

**Đáp án:** 4096 số `low`, mỗi số 2 byte, cần 8192 byte, bằng một bitmap 65.536 bit. Đây là hòa vốn payload điển hình.

**Câu 17.** Trong mã Java, `RunSet.contains` tìm vị trí dải bằng cách nào?

**Đáp án:** Tìm nhị phân dải đầu có `end\ge key` rồi kiểm tra `start\le key`.

**Câu 18.** Với các dải `[10,19]` và `[200,209]`, có bao nhiêu khóa thuộc `[15,205]`?

**Đáp án:** 5 khóa `15..19` và 6 khóa `200..205`, tổng 11 khóa.

**Câu 19.** Vì sao thêm/xóa trên danh sách dải lưu bằng mảng có thể tốn O(r)?

**Đáp án:** Thêm có thể tạo/gộp dải, xóa có thể tách dải; cần dịch các cặp cận trong mảng.

**Câu 20.** Nếu dữ liệu gồm vài cụm rất dài nhưng thường xuyên thay đổi từng khóa, nên cân nhắc những yếu tố nào trước khi chọn RLE?

**Đáp án:** Bên cạnh tỷ lệ nén và số dải `r`, cần đo chi phí **tách/gộp dải khi cập nhật**, độ trễ membership, phép tập hợp, cache và nhu cầu đồng bộ.

**Điểm ghi nhớ:** **Bitset thô** dùng một bit cho mỗi khóa trong miền `U`, có truy cập bit và thao tác AND/OR nhanh nhưng chi phí bộ nhớ phụ thuộc `U`. **Bitmap nén** tận dụng cấu trúc phân bố: **RLE** hiệu quả khi có ít dải dài, **WAH/EWAH** tận dụng những đoạn từ 0/1 lặp, còn **Roaring** chọn array/bitmap/run theo từng khối. Không thể chỉ nhìn mật độ `n/U` để dự đoán mức nén: phải đo **số dải `r`, phân bố theo khối và workload cập nhật/truy vấn**. Luôn tính cả bộ nhớ thực, chi phí giải mã và hiệu năng phép toán trước khi quyết định.
