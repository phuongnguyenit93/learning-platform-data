# Trộn tối ưu và mã Huffman

## Mục tiêu học tập

Hai bài toán tưởng khác nhau — **trộn nhiều tệp với tổng chi phí nhỏ nhất** và **gán mã nhị phân có độ dài trung bình nhỏ nhất** — có cùng một cấu trúc tham lam: **lấy hai trọng số nhỏ nhất, gộp chúng, rồi đưa trọng số tổng trở lại hàng đợi ưu tiên**.

Sau bài này, bạn có thể:

1. Mô hình hóa **optimal merge pattern** (bài toán trộn tối ưu) với trọng số không âm và chi phí mỗi lần gộp bằng tổng trọng số.
2. Dùng **min-heap / priority queue** xây kế hoạch gộp có tổng chi phí nhỏ nhất, phân tích thời gian và bộ nhớ.
3. Xây **cây Huffman** từ tần suất ký hiệu để có mã **prefix-free** (không mã nào là tiền tố của mã khác).
4. Chứng minh lựa chọn tham lam bằng **hai phần tử nhẹ nhất ở độ sâu lớn nhất**, lập luận hoán đổi và cấu trúc con tối ưu.
5. Nhận ra hai công thức tương đương: **tổng chi phí các nút trộn** và **tổng trọng số × độ sâu lá**.
6. Cài đặt Java 17+ cho trộn tối ưu, tạo mã Huffman, mã hóa/giải mã và kiểm thử các trường hợp biên.
7. Phân biệt **tính tối ưu theo mô hình toán học** với các giới hạn thực tế như metadata của bảng mã, số ký hiệu, chi phí I/O, nhiều đường trộn và yêu cầu thứ tự.

## 1. Bài toán trộn tối ưu: mô hình chính xác

Có `n` tệp hoặc khối dữ liệu với kích thước:

\[
w_1,w_2,\ldots,w_n,\qquad w_i\ge0.
\]

Ở mỗi bước, ta được chọn **bất kỳ hai** khối hiện có có kích thước `x` và `y` để trộn thành một khối mới kích thước `x+y`. Chi phí của lần trộn **đúng bằng `x+y`**. Hai khối cũ bị thay bằng khối mới, và quá trình tiếp diễn đến khi còn một khối duy nhất.

**Mục tiêu:** chọn thứ tự trộn sao cho **tổng chi phí của tất cả lần trộn là nhỏ nhất**.

Nếu ban đầu có `n≥1` khối, cần đúng `n-1` lần trộn nhị phân. Với `n=0` hoặc `n=1`, không có gì để trộn và chi phí trộn là **0**.

Ví dụ có bốn tệp với kích thước:

```text
A=4, B=6, C=8, D=12
```

Một kế hoạch tốt:

```text
Bước 1:  4 + 6 = 10      Chi phí 10
Bước 2:  8 +10 = 18      Chi phí 18
Bước 3: 12 +18 = 30      Chi phí 30

Tổng chi phí = 10 + 18 + 30 = 58
```

Một kế hoạch kém hơn:

```text
Bước 1: 12 + 8 = 20      Chi phí 20
Bước 2: 20 + 6 = 26      Chi phí 26
Bước 3: 26 + 4 = 30      Chi phí 30

Tổng chi phí = 20 + 26 + 30 = 76
```

Cả hai kế hoạch đều tạo một khối cuối kích thước 30. Nhưng **tổng lượng dữ liệu đã đi qua các lần trộn** khác nhau. Ở kế hoạch thứ hai, một số khối lớn bị đem đi trộn nhiều lần, làm tăng chi phí.

**Bản chất của bài toán:** không chỉ quan tâm kích thước kết quả cuối; phải tối ưu **tổng kích thước của mọi kết quả trung gian**.

### 1.1. Giả định làm nên bài toán này

Chiến lược tham lam “hai nhỏ nhất trước” được chứng minh tối ưu khi:

- Mỗi lần gộp **đúng hai** khối.
- Có thể chọn **bất kỳ cặp** khối hiện còn; không có ràng buộc phải là hai khối kề nhau.
- Kích thước khối mới bằng **tổng** kích thước hai khối cũ.
- Chi phí của mỗi lần trộn bằng **tổng** kích thước hai khối đó, không cộng phí khác phụ thuộc thứ tự, đĩa, máy, thời gian chờ hoặc số lần gọi.
- Mọi trọng số **không âm**, và không có giới hạn tài nguyên làm mất khả năng chọn cặp.

Nếu hệ thống chỉ cho phép trộn các khối **liền kề theo một thứ tự cố định**, cho phép gộp **ba hay nhiều khối cùng lần**, hoặc có chi phí khác với `x+y`, bài toán cần xem xét lại. Không được dùng cùng chứng minh để khẳng định một thuật toán tối ưu cho mọi hệ thống trộn dữ liệu.

## 2. Lựa chọn tham lam: luôn trộn hai nhỏ nhất

Quy tắc:

> Tại mỗi bước, lấy **hai khối có trọng số nhỏ nhất hiện tại**, trộn chúng, cộng trọng số khối mới vào tổng chi phí, rồi đưa khối mới vào tập khối còn lại.

Trên `[4,6,8,12]`, hai nhỏ nhất đầu tiên là `4` và `6`, tạo 10. Tập hiện có thành `[8,10,12]`; hai nhỏ nhất tiếp theo là `8` và `10`, tạo 18; cuối cùng trộn `12` và `18`, tạo 30. Tổng 58.

**Điểm cần chú ý:** sau mỗi lần gộp phải đưa **trọng số mới** vào tập và **tìm lại hai nhỏ nhất**. Không phải cứ sắp dữ liệu gốc một lần rồi trộn các cặp liên tiếp theo thứ tự ban đầu là đúng. Trọng số mới có thể nhỏ hơn một số khối gốc còn lại và phải tiếp tục tham gia so sánh.

### 2.1. Vì sao min-heap là cấu trúc phù hợp?

Ta thường xuyên thực hiện ba thao tác:

1. Lấy trọng số nhỏ nhất.
2. Lấy trọng số nhỏ nhất tiếp theo.
3. Thêm trọng số tổng mới tạo ra.

**Min-heap** hỗ trợ lấy/xóa phần tử nhỏ nhất và chèn phần tử trong `O(log n)` thời gian, với truy cập đỉnh `O(1)`. Trong Java, `PriorityQueue<Long>` dùng thứ tự tự nhiên chính là một min-heap.

Giả mã:

```text
OPTIMAL_MERGE(weights):
    yêu cầu: mọi trọng số không âm
    heap <- min-heap chứa tất cả trọng số
    total <- 0

    while heap.size() > 1:
        x <- heap.removeMin()
        y <- heap.removeMin()
        merged <- x + y
        total <- total + merged
        heap.insert(merged)

    return total
```

**Bất biến sau mỗi vòng:**

- Heap chứa đúng những khối **hiện chưa được trộn tiếp**, không thêm/bớt sai trọng số.
- `total` bằng tổng chi phí của tất cả lần trộn đã thực hiện.
- Mỗi bước làm số khối hiện có giảm đúng 1.

Khi heap còn một phần tử, tất cả khối đã được gộp vào một khối; giá trị `total` là tổng chi phí của kế hoạch. Tính **tối ưu** của việc luôn chọn hai nhỏ nhất sẽ được chứng minh riêng ở mục 7.

### 2.2. Độ phức tạp

Với `n` khối:

- Thêm từng trọng số vào `PriorityQueue`: tối đa `O(n log(n+1))`; nếu có một thao tác xây heap từ mảng phù hợp, có thể xây heap trong `O(n)`.
- Có `n-1` lần trộn; mỗi lần hai lần xóa-min và một lần chèn, tối đa `O(log(n+1))`.
- **Tổng thời gian:** `O(n log(n+1))`.
- **Bộ nhớ phụ:** `O(n)` cho hàng đợi.
- Với `n=0` hoặc `n=1`, vòng trộn không chạy và trả 0.

Mỗi số có thể rất lớn. Nếu dùng `int` cho kích thước và tổng chi phí, dễ tràn số; Java nên dùng `long` và cân nhắc `Math.addExact` để phát hiện khi tổng vượt miền `long`.

## 3. Cây trộn: mô hình giúp thấy cấu trúc tối ưu

Mỗi kế hoạch trộn nhị phân có thể biểu diễn bằng một **cây nhị phân đầy đủ**:

- **Lá** biểu diễn các khối gốc.
- **Nút trong** biểu diễn một lần trộn hai khối con.
- **Trọng số nút trong** bằng tổng trọng số của các lá nằm dưới nó.
- **Gốc** biểu diễn khối đã trộn tất cả dữ liệu.

Với `[4,6,8,12]`, kế hoạch tham lam có thể vẽ:

```text
                 (30)
                /    \
             D:12    (18)
                    /    \
                  C:8    (10)
                        /    \
                      A:4    B:6
```

Chi phí các nút trong là `10`, `18` và `30`, tổng **58**.

Quan sát một khối gốc:

- A kích thước 4 được tính trong 3 nút trộn tổ tiên: 10, 18, 30.
- B kích thước 6 cũng được tính 3 lần.
- C kích thước 8 được tính 2 lần.
- D kích thước 12 được tính 1 lần.

Tổng theo các lá:

\[
4\cdot3+6\cdot3+8\cdot2+12\cdot1
=12+18+16+12
=58.
\]

**Đẳng thức nền tảng**:

\[
\boxed{\text{Tổng chi phí trộn}
 =\sum_{\text{nút trong }v}weight(v)
 =\sum_{\text{lá }i}w_i\cdot depth(i)}
\]

trong đó `depth(i)` là số cạnh từ gốc đến lá i, cũng là số lần khối gốc i tham gia vào một lần trộn.

Đẳng thức đúng vì mỗi lá i đóng góp `w_i` vào trọng số **mọi nút trong tổ tiên** của nó, tổng cộng đúng `depth(i)` lần. Đổi thứ tự cộng từ “theo nút trong” sang “theo lá” cho hai vế bằng nhau.

Điều này gợi ý trực giác tham lam: **trọng số lớn nên xuất hiện ở độ sâu nhỏ, trọng số nhỏ có thể chịu độ sâu lớn hơn**. Không nhất thiết là mỗi trọng số lớn nhất luôn ở độ sâu nhỏ nhất duy nhất (do ràng buộc hình dạng cây), nhưng lựa chọn hai nhỏ nhất để làm anh em sâu là cấu trúc có thể chứng minh an toàn.

## 4. Mã Huffman: cũng là bài toán chọn cây có trọng số

Trong nén dữ liệu, mỗi ký hiệu có một **tần suất** hoặc xác suất xuất hiện. Một **mã nhị phân độ dài biến đổi** gán cho mỗi ký hiệu một chuỗi bit (ví dụ `0`, `1100`, `111`).

Nếu gán mã tùy tiện, luồng bit nối các mã có thể **không giải mã duy nhất**.

Ví dụ bộ mã:

```text
A -> 0
B -> 01
```

Bit `01` có thể làm bộ giải mã thiếu rõ ràng khi đọc từ trái sang phải, vì `0` đã là mã hoàn chỉnh của A nhưng đồng thời là tiền tố của mã B. Để dễ giải mã tức thời, ta dùng **prefix-free code**:

> Không từ mã của một ký hiệu nào là tiền tố của từ mã của một ký hiệu khác.

Mã Huffman là một cách xây **mã nhị phân prefix-free có tổng độ dài có trọng số tối thiểu** trong mô hình mã cây nhị phân, khi biết tần suất các ký hiệu.

### 4.1. Cây mã

Với cây Huffman nhị phân:

- Mỗi **lá** gắn một ký hiệu.
- Mỗi **nút trong** có hai nhánh.
- Gán `0` cho cạnh trái, `1` cho cạnh phải.
- Từ mã của một ký hiệu là chuỗi các bit trên đường từ gốc đến lá ấy.

Do các ký hiệu đều đặt ở **lá**, đường đi đến lá này không thể là tiền tố đường đi đến một lá khác. Vì vậy mã thu được luôn prefix-free.

Gọi `f_i` là tần suất ký hiệu i và `l_i` là độ dài từ mã của nó. Nếu tệp gồm đúng `f_i` lần xuất hiện ký hiệu i, tổng bit phần **payload** là:

\[
B=\sum_i f_i\,l_i.
\]

Bài toán Huffman tối ưu giá trị này, **không** tự động tối ưu mọi khoản chi phí truyền/lưu trữ khác như bảng mã, tiêu đề tệp, đệm bit cuối, checksum hoặc nén đa ký hiệu.

### 4.2. Vì sao lại trộn hai tần suất nhỏ nhất?

Khởi đầu, mỗi ký hiệu có tần suất dương là một nút lá. Ta dùng min-heap và lặp:

1. Lấy hai nút có tần suất/trọng số nhỏ nhất.
2. Tạo một nút cha có trọng số bằng **tổng** trọng số hai nút con.
3. Đặt một nút làm con trái, nút còn lại làm con phải.
4. Đưa nút cha vào heap.
5. Khi còn một nút, đó là gốc cây Huffman.

Đây **chính là cấu trúc trộn tối ưu**. Sự khác biệt ở mục tiêu hiển thị đầu ra: bài trộn tối ưu chỉ cần tổng chi phí hoặc thứ tự trộn; Huffman cần giữ **cây và đường đi bit** để xây bảng mã.

## 5. Ví dụ Huffman kinh điển với sáu ký hiệu

Cho tần suất:

| Ký hiệu | a | b | c | d | e | f | Tổng |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Tần suất | 5 | 9 | 12 | 13 | 16 | 45 | 100 |

Dùng min-heap:

| Bước | Hai trọng số nhỏ nhất | Nút mới | Trọng số còn trong heap (viết tăng) |
| ---: | --- | ---: | --- |
| Ban đầu | — | — | `[5,9,12,13,16,45]` |
| 1 | `5+9` | `14` | `[12,13,14,16,45]` |
| 2 | `12+13` | `25` | `[14,16,25,45]` |
| 3 | `14+16` | `30` | `[25,30,45]` |
| 4 | `25+30` | `55` | `[45,55]` |
| 5 | `45+55` | `100` | `[100]` |

Tổng chi phí trộn:

\[
14+25+30+55+100=\boxed{224}.
\]

Khi quy ước con trái mang bit `0`, con phải mang bit `1` theo thứ tự lấy hai phần tử nhỏ nhất, ta thu cây:

```text
                      (100)
                     /     \
                 0 /         \ 1
                 f:45        (55)
                            /    \
                          0/      \1
                         (25)     (30)
                        /   \     /   \
                      0/    1\   0/   1\
                    c:12  d:13  (14)  e:16
                               /    \
                             0/      \1
                            a:5      b:9
```

Bảng mã tương ứng:

| Ký hiệu | Tần suất | Mã Huffman | Độ dài | Số bit đóng góp |
| --- | ---: | --- | ---: | ---: |
| a | 5 | `1100` | 4 | 20 |
| b | 9 | `1101` | 4 | 36 |
| c | 12 | `100` | 3 | 36 |
| d | 13 | `101` | 3 | 39 |
| e | 16 | `111` | 3 | 48 |
| f | 45 | `0` | 1 | 45 |
| **Tổng** | **100** | — | — | **224** |

Ta kiểm tra bằng công thức:

\[
B=5\cdot4+9\cdot4+12\cdot3+13\cdot3+
16\cdot3+45\cdot1=\boxed{224}.
\]

**Kết quả quan trọng:** tổng chi phí trộn `224` **bằng** tổng số bit có trọng số `224` do chúng dùng **cùng một cây nhị phân** và cùng hàm mục tiêu `sum weight×depth`.

Nếu gán **mã nhị phân cố định 3 bit** cho mỗi trong 6 ký hiệu, payload 100 ký hiệu cần `100×3=300` bit. Huffman dùng 224 bit, ít hơn 76 bit, tức khoảng `25,33%` của phần payload 300 bit.

**Cảnh báo về so sánh nén:** đây mới là số bit của các ký hiệu. Một tệp thật còn phải mang thông tin để phía giải mã biết cây/bảng mã (trừ khi đã thỏa thuận trước), có thể thêm thông tin về độ dài, byte padding và định dạng tệp. Với tệp ngắn, tổng kích thước cuối có thể lớn hơn payload.

### 5.1. Ví dụ mã hóa một chuỗi

Với bảng mã trên:

```text
"face"
f -> 0
a -> 1100
c -> 100
e -> 111

Bit được ghép: 0 1100 100 111
Kết quả:       01100100111
```

Giải mã bằng cách đi trên cây từ gốc:

- Đọc `0`, đến lá f → xuất `f`, quay về gốc.
- Đọc `1100`, đến lá a → xuất `a`.
- Đọc `100`, đến lá c → xuất `c`.
- Đọc `111`, đến lá e → xuất `e`.

Thu lại chuỗi `face` mà không cần dấu phân cách giữa các từ mã, vì bộ mã **prefix-free**.

### 5.2. Các mã Huffman có thể không duy nhất

Nếu có nhiều nút cùng trọng số, thứ tự lấy hai nút hòa hoặc cách gắn nhánh trái/phải có thể khác. Thậm chí khi không hòa, đổi nhãn bit 0 và 1 trên một số nút vẫn tạo bộ mã khác có cùng độ dài. Vì vậy:

- **Độ dài tối ưu có thể giống nhau** nhưng chuỗi bit cụ thể khác.
- Để có đầu ra lặp lại chính xác trong test, phải quy định **quy tắc phá hòa** và hướng trái/phải.
- Mã Huffman trong chương trình minh họa dùng so sánh: trọng số tăng, ký hiệu nhỏ nhất trong cây con tăng, rồi thứ tự tạo nút. Đây là quy tắc xác định, không phải quy tắc duy nhất.
- Trong định dạng nén thật, có thể dùng **canonical Huffman** để tạo biểu diễn bảng mã gọn hơn từ độ dài mã; đây là bước biểu diễn riêng, không thay đổi tính tối ưu của độ dài.

Nếu đề bài chỉ yêu cầu **tổng số bit tối ưu** mà không yêu cầu bitstring cụ thể, không được chấm một bảng mã khác là sai chỉ vì khác nhánh 0/1, miễn mã prefix-free và có cùng tổng chi phí tối ưu.

## 6. Mối liên hệ sâu giữa trộn tối ưu và Huffman

Đây là cốt lõi lý thuyết của bài học.

Trong trộn tệp, mỗi lá chứa một khối kích thước `w_i`. Khi khối đó tham gia vào một trộn ở tổ tiên, toàn bộ `w_i` được cộng vào chi phí một lần.

Trong Huffman, mỗi lá chứa ký hiệu tần suất `f_i`. Mỗi cạnh từ gốc xuống lá làm độ dài từ mã tăng một bit, và bit đó xuất hiện `f_i` lần trong payload. Vì thế mỗi cấp sâu đóng góp `f_i` bit.

Với **cùng cây**:

\[
\begin{aligned}
\operatorname{mergeCost}(T)
 &= \sum_{v\text{ nút trong}}weight(v)\\
 &= \sum_{i\text{ lá}}w_i\,depth_T(i)\\
 &= \operatorname{weightedPathLength}(T).
\end{aligned}
\]

Nếu đặt `w_i=f_i`, đây cũng là chi phí bit Huffman.

Do đó tối ưu **kế hoạch trộn** và tối ưu **cây mã prefix-free** với cùng các trọng số dương là **cùng một bài toán tối ưu cây nhị phân đầy đủ** (ngoại lệ biểu diễn một ký hiệu sẽ nói ở mục 11).

**Bài học về tư duy thuật toán:** cùng một mô hình toán học có thể xuất hiện dưới các ngữ cảnh dữ liệu, nén thông tin và cây khác nhau. Nhận diện hàm mục tiêu và cấu trúc con tối ưu giúp tái sử dụng phép chứng minh đúng, không chỉ tái sử dụng mã nguồn.

## 7. Chứng minh tham lam luôn chọn hai nhỏ nhất là tối ưu

Một chiến lược nghe có vẻ hợp lý **chưa đủ** để là greedy đúng. Ta cần chứng minh **greedy-choice property** và **optimal substructure**.

Giả sử có ít nhất hai trọng số **dương** `w_1,\ldots,w_n`. Phép chứng minh cho các khối không âm có thể xử lý trọng số bằng 0 tương tự; với Huffman ta thường bỏ các ký hiệu có tần suất 0 vì chúng không xuất hiện trong dữ liệu cần mã hóa.

### 7.1. Bổ đề lựa chọn tham lam

**Bổ đề:** tồn tại một cây tối ưu mà **hai lá có trọng số nhỏ nhất** là **hai anh em cùng cha** tại độ sâu lớn nhất.

**Lập luận hoán đổi:**

1. Lấy một cây nhị phân đầy đủ tối ưu bất kỳ. Chọn một lá ở độ sâu lớn nhất. Do cây đầy đủ, anh em của lá này cũng phải là **lá** ở cùng độ sâu: nếu anh em là nút trong, nó sẽ có hậu duệ sâu hơn, trái với việc lá đầu tiên sâu nhất.
2. Gọi hai lá anh em sâu nhất là `x` và `y`. Gọi hai trọng số nhỏ nhất là `a≤b`.
3. Hoán đổi nhãn/trọng số các lá sao cho `a` và `b` nằm ở vị trí `x` và `y`. Vì `depth(x)` và `depth(y)` là lớn nhất, đặt trọng số nhỏ hơn vào độ sâu lớn hơn **không làm tăng** tổng `sum_i w_i depth(i)`. Lập luận này có thể thực hiện bằng những phép đổi chỗ giữa hai lá có trọng số và độ sâu phù hợp.
4. Ta thu được một cây vẫn tối ưu, trong đó hai trọng số nhỏ nhất cùng nằm ở một cặp lá anh em sâu nhất.

Vì tồn tại cây tối ưu với hai nhỏ nhất là anh em, ta có thể **gộp hai nhỏ nhất ngay từ đầu** mà không loại bỏ mọi lời giải tối ưu.

### 7.2. Cấu trúc con tối ưu

Giả sử hai trọng số nhỏ nhất là `a` và `b`, nằm ở hai lá anh em trong một cây tối ưu. Co hai lá này và cha của chúng thành **một lá mới** có trọng số `a+b`. Cây còn lại là một cây trộn trên tập trọng số:

\[
W'=(W\setminus\{a,b\})\cup\{a+b\}.
\]

So sánh hai chi phí:

\[
\operatorname{cost}(T)=
(a+b)+\operatorname{cost}(T'),
\]

bởi việc tách lá `a+b` thành hai lá `a`, `b` làm tổng độ sâu có trọng số tăng đúng `a+b`.

Nếu `T'` không tối ưu cho `W'`, ta có thể thay bằng một cây tốt hơn, rồi tách lá `a+b` để tạo một cây tốt hơn cho bài toán gốc. Điều đó mâu thuẫn với tính tối ưu của `T`. Do vậy `T'` cũng tối ưu.

### 7.3. Quy nạp và kết luận

- Với một khối, chi phí trộn bằng 0.
- Với ít nhất hai khối, tồn tại kế hoạch tối ưu gộp hai nhỏ nhất trước.
- Sau khi gộp, bài toán còn lại có cùng dạng, chỉ giảm số khối đi một.
- Áp dụng lập luận lặp lại, tại **mỗi bước** đều có thể chọn hai nhỏ nhất mà vẫn giữ được một lời giải tối ưu.

Vì vậy thuật toán dùng min-heap để **liên tục gộp hai trọng số nhỏ nhất là tối ưu** cho mô hình trộn nhị phân đã nêu. Cùng chứng minh áp dụng cho độ dài mã Huffman prefix-free.

### 7.4. Những điều chứng minh không nói

Chứng minh trên **không** khẳng định:

- Hai trọng số nhỏ nhất bắt buộc phải là anh em trong **mọi** cây tối ưu (có thể có nhiều lời giải tối ưu).
- Cách gán bit 0/1 hoặc thứ tự các ký hiệu có cùng trọng số là duy nhất.
- Greedy đúng khi buộc hai phần tử trộn phải liền nhau trong danh sách gốc.
- Greedy vẫn tối ưu nếu chi phí mỗi lần trộn không còn bằng tổng trọng số.
- Huffman tối ưu hơn **mọi dạng nén dữ liệu có thể tồn tại**; nó tối ưu trong lớp mã nhị phân prefix-free theo hàm mục tiêu đã đặc tả.

Chứng minh greedy luôn cần đi cùng **giả thiết của bài toán**, không thể chỉ ghi “tham lam vì chọn nhỏ nhất là tốt nhất”.

## 8. Java 17+ — trộn tối ưu và xây Huffman trong một chương trình

Tệp đầy đủ dưới đây có tên **`OptimalMergeHuffmanDemo.java`** và chạy với **JDK 17 trở lên**. Nó:

1. Tính chi phí trộn tối ưu bằng `PriorityQueue<Long>`.
2. Xây cây Huffman từ các ký hiệu và tần suất, có quy tắc phá hòa xác định.
3. Ghi lại thứ tự các lần gộp.
4. Duyệt cây để lấy mã của từng ký hiệu.
5. Tính tổng số bit có trọng số và đối chiếu với tổng chi phí trộn.
6. Mã hóa/giải mã một chuỗi sử dụng bảng mã.
7. Chặn trọng số âm, ký hiệu trùng trong bảng tần suất và tràn `long` ở các phép cộng/nhân được kiểm soát.

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.PriorityQueue;
import java.util.Set;
import java.util.TreeMap;

public class OptimalMergeHuffmanDemo {

    static long optimalMergeCost(long[] weights) {
        Objects.requireNonNull(weights, "weights");

        PriorityQueue<Long> heap = new PriorityQueue<>();
        for (long weight : weights) {
            if (weight < 0) {
                throw new IllegalArgumentException("negative weight");
            }
            heap.offer(weight);
        }

        long total = 0;

        while (heap.size() > 1) {
            long first = heap.remove();
            long second = heap.remove();
            long combined = Math.addExact(first, second);

            total = Math.addExact(total, combined);
            heap.offer(combined);
        }

        return total;
    }

    static final class Node {
        final long weight;
        final Character symbol; // null means internal node
        final char smallestSymbol;
        final long serial;
        final Node left;
        final Node right;

        Node(long weight, Character symbol, char smallestSymbol,
             long serial, Node left, Node right) {
            this.weight = weight;
            this.symbol = symbol;
            this.smallestSymbol = smallestSymbol;
            this.serial = serial;
            this.left = left;
            this.right = right;
        }

        static Node leaf(char symbol, long weight, long serial) {
            return new Node(weight, symbol, symbol,
                    serial, null, null);
        }

        static Node parent(Node left, Node right, long serial) {
            return new Node(
                    Math.addExact(left.weight, right.weight),
                    null,
                    (char) Math.min(left.smallestSymbol,
                                    right.smallestSymbol),
                    serial,
                    left,
                    right);
        }
    }

    record HuffmanResult(
            Node root,
            Map<Character, String> codes,
            List<String> steps,
            long mergeCost,
            long weightedBits) {
    }

    static HuffmanResult buildHuffman(
            char[] symbols, long[] frequencies) {

        Objects.requireNonNull(symbols, "symbols");
        Objects.requireNonNull(frequencies, "frequencies");

        if (symbols.length != frequencies.length) {
            throw new IllegalArgumentException(
                    "symbols/frequencies length mismatch");
        }

        PriorityQueue<Node> heap = new PriorityQueue<>(
                Comparator.comparingLong((Node n) -> n.weight)
                        .thenComparingInt(n -> n.smallestSymbol)
                        .thenComparingLong(n -> n.serial));

        Set<Character> seen = new HashSet<>();
        long nextSerial = 0;

        for (int i = 0; i < symbols.length; i++) {
            if (!seen.add(symbols[i])) {
                throw new IllegalArgumentException(
                        "duplicate symbol: " + symbols[i]);
            }
            if (frequencies[i] < 0) {
                throw new IllegalArgumentException(
                        "negative frequency");
            }

            // Symbols that never occur need no payload code.
            if (frequencies[i] > 0) {
                heap.offer(Node.leaf(
                        symbols[i], frequencies[i], nextSerial++));
            }
        }

        Map<Character, String> codes = new TreeMap<>();
        List<String> steps = new ArrayList<>();
        long mergeCost = 0;

        if (heap.isEmpty()) {
            return new HuffmanResult(
                    null, codes, steps, 0, 0);
        }

        while (heap.size() > 1) {
            Node first = heap.remove();
            Node second = heap.remove();
            Node parent = Node.parent(
                    first, second, nextSerial++);

            mergeCost = Math.addExact(mergeCost, parent.weight);
            steps.add("Merge " + first.weight + " + "
                    + second.weight + " = " + parent.weight);
            heap.offer(parent);
        }

        Node root = heap.remove();
        assignCodes(root, new StringBuilder(), codes);

        long weightedBits = 0;
        for (int i = 0; i < symbols.length; i++) {
            if (frequencies[i] > 0) {
                int length = codes.get(symbols[i]).length();
                long contribution = Math.multiplyExact(
                        frequencies[i], (long) length);

                weightedBits = Math.addExact(
                        weightedBits, contribution);
            }
        }

        return new HuffmanResult(
                root, codes, steps, mergeCost, weightedBits);
    }

    // DFS: left edge = 0; right edge = 1.
    private static void assignCodes(
            Node node, StringBuilder path,
            Map<Character, String> output) {

        if (node.symbol != null) {
            // Practical convention for one distinct symbol.
            output.put(node.symbol,
                    path.length() == 0 ? "0" : path.toString());
            return;
        }

        path.append('0');
        assignCodes(node.left, path, output);
        path.setLength(path.length() - 1);

        path.append('1');
        assignCodes(node.right, path, output);
        path.setLength(path.length() - 1);
    }

    static String encode(
            String message, Map<Character, String> codes) {

        Objects.requireNonNull(message, "message");
        Objects.requireNonNull(codes, "codes");

        StringBuilder bits = new StringBuilder();

        for (int i = 0; i < message.length(); i++) {
            char symbol = message.charAt(i);
            String code = codes.get(symbol);

            if (code == null) {
                throw new IllegalArgumentException(
                        "symbol absent from codebook: " + symbol);
            }

            bits.append(code);
        }

        return bits.toString();
    }

    static String decode(String bits, Node root) {
        Objects.requireNonNull(bits, "bits");

        if (root == null) {
            if (!bits.isEmpty()) {
                throw new IllegalArgumentException(
                        "non-empty bits with empty tree");
            }
            return "";
        }

        StringBuilder output = new StringBuilder();

        // One symbol: we chose code "0" for each occurrence.
        if (root.symbol != null) {
            for (int i = 0; i < bits.length(); i++) {
                if (bits.charAt(i) != '0') {
                    throw new IllegalArgumentException(
                            "invalid bit for one-symbol code");
                }
                output.append(root.symbol.charValue());
            }
            return output.toString();
        }

        Node current = root;
        for (int i = 0; i < bits.length(); i++) {
            char bit = bits.charAt(i);

            if (bit == '0') {
                current = current.left;
            } else if (bit == '1') {
                current = current.right;
            } else {
                throw new IllegalArgumentException(
                        "bits must contain only 0 or 1");
            }

            if (current.symbol != null) {
                output.append(current.symbol.charValue());
                current = root;
            }
        }

        if (current != root) {
            throw new IllegalArgumentException(
                    "incomplete last codeword");
        }

        return output.toString();
    }

    public static void main(String[] args) {
        long[] sizes = {4, 6, 8, 12};
        System.out.println("Optimal merge [4, 6, 8, 12]: "
                + optimalMergeCost(sizes));

        char[] symbols = {'a', 'b', 'c', 'd', 'e', 'f'};
        long[] frequencies = {5, 9, 12, 13, 16, 45};
        HuffmanResult result = buildHuffman(
                symbols, frequencies);

        System.out.println("Huffman merge steps:");
        for (String step : result.steps()) {
            System.out.println(step);
        }

        System.out.println("Codes:");
        for (char symbol : symbols) {
            System.out.println(symbol + ": "
                    + result.codes().get(symbol));
        }

        System.out.println("Huffman merge cost: "
                + result.mergeCost());
        System.out.println("Weighted encoded bits: "
                + result.weightedBits());
        System.out.println("Fixed 3-bit payload: 300");

        String message = "face";
        String bits = encode(message, result.codes());
        System.out.println("Encode face: " + bits);
        System.out.println("Decode: "
                + decode(bits, result.root()));
    }
}
```

Biên dịch và chạy:

```bash
javac OptimalMergeHuffmanDemo.java
java OptimalMergeHuffmanDemo
```

**Đầu ra chuẩn chính xác** của ví dụ trên:

```text
Optimal merge [4, 6, 8, 12]: 58
Huffman merge steps:
Merge 5 + 9 = 14
Merge 12 + 13 = 25
Merge 14 + 16 = 30
Merge 25 + 30 = 55
Merge 45 + 55 = 100
Codes:
a: 1100
b: 1101
c: 100
d: 101
e: 111
f: 0
Huffman merge cost: 224
Weighted encoded bits: 224
Fixed 3-bit payload: 300
Encode face: 01100100111
Decode: face
```

### 8.1. Đọc hiểu các phần quan trọng của code

- `PriorityQueue<Long>` lưu kích thước của các khối hiện tại. Mỗi vòng trộn lấy hai phần tử nhỏ nhất, tính `combined` rồi đưa lại heap.
- `Math.addExact` phát hiện tràn khi cộng hai kích thước hoặc cộng vào tổng chi phí. Thay vì âm thầm cho giá trị sai, Java sẽ ném `ArithmeticException`.
- Mỗi `Node` chứa trọng số, ký hiệu nếu là lá, cây con trái/phải, ký hiệu nhỏ nhất trong cây con và số thứ tự tạo. Ký hiệu nhỏ nhất và `serial` chỉ phục vụ **phá hòa xác định**.
- Trong `buildHuffman`, tần suất âm bị từ chối; ký hiệu trùng trong danh sách đầu vào cũng bị từ chối. Ký hiệu có tần suất 0 không cần mã payload nên không được đưa vào heap.
- Thứ tự ưu tiên là **trọng số → ký hiệu nhỏ nhất → thứ tự tạo**. Khi lấy `first` và `second`, đặt chúng lần lượt làm con trái và con phải, nên kết quả bit của ví dụ có thể dự đoán.
- `assignCodes` duyệt DFS. Gọi đệ quy sang trái với bit 0, sang phải với bit 1; dùng `StringBuilder` và xóa bit vừa thêm khi quay lui.
- `encode` ghép các chuỗi bit từ bảng mã. Nếu ký hiệu của thông điệp không nằm trong bảng mã, nó ném lỗi thay vì tự tạo mã.
- `decode` nhận **đúng chuỗi bit payload** và **đúng cây mã**. Nó đi theo 0/1, xuất ký hiệu tại lá, rồi trở lại gốc. Nếu hết dữ liệu khi đang ở giữa một đường đi, chương trình báo lỗi từ mã chưa đủ.
- Chương trình dùng `char` Java, phù hợp bộ ký hiệu `a..f` và các ký hiệu một đơn vị UTF-16. Nếu cần mã hóa toàn bộ Unicode gồm ký tự ngoài BMP, nên thay biểu diễn ký hiệu bằng **Unicode code point** (`int`) hoặc các byte của một bộ mã hóa đã quy định, không coi mọi ký tự hiển thị đều là một `char`.
- `Fixed 3-bit payload: 300` là giá trị đối chứng của **100 ký hiệu với 6 loại**, không phải một bộ nén hoàn chỉnh; không tính overhead truyền bảng mã.

### 8.2. Phân tích chi phí chương trình

Gọi `n` là số khối cần trộn và `m` là số ký hiệu có **tần suất dương** cần mã hóa.

| Thành phần | Thời gian | Bộ nhớ phụ |
| --- | --- | --- |
| `optimalMergeCost` trên n trọng số | `O(n log(n+1))` | `O(n)` |
| Xây cây Huffman từ m lá bằng heap | `O(m log(m+1))` | `O(m)` nút và heap |
| Duyệt cây ghi bảng mã | `O(\sum_i l_i)` để xuất các từ mã | `O(\sum_i l_i)` lưu bit mã dưới dạng chuỗi, cộng stack DFS |
| Mã hóa một thông điệp | Tỷ lệ với số ký hiệu tra cứu cộng số bit tạo ra | `O(\text{số bit đầu ra})` |
| Giải mã payload | `O(\text{số bit được đọc})` | `O(\text{số ký hiệu đầu ra})` để xây chuỗi |

Với cây Huffman nhị phân m lá và `m≥2`, có đúng `m-1` nút trong và tổng `2m-1` nút. Từ mã dài nhất có thể dài tới `m-1` bit; vì thế **danh sách tất cả chuỗi mã** có thể chiếm nhiều hơn `O(m)` bộ nhớ. Khi chỉ cần **tổng chi phí tối ưu**, không nhất thiết dựng/lưu toàn bộ mã; trộn trọng số bằng heap đã đủ.

Trong chương trình Java, số lượng ký hiệu truyền vào ở mảng `symbols` có thể lớn hơn m do một số tần suất bằng 0. Việc duyệt kiểm tra đầu vào và tính tổng sau khi xây cây còn có chi phí tuyến tính theo **tổng số ký hiệu được khai báo**; phân tích `O(m log m)` cho cây chỉ xét các ký hiệu có tần suất dương.

Lời gọi DFS đệ quy sử dụng stack có độ sâu theo **chiều cao cây**. Với cây rất lệch và bảng ký hiệu rất lớn, cần cân nhắc duyệt lặp thay vì đệ quy nếu giới hạn stack thực tế có thể bị vượt.

## 9. Đặc điểm mã Huffman và giới hạn nén

### 9.1. Prefix-free bảo đảm giải mã đơn nghĩa

Với mã Huffman:

- Mỗi từ mã được gán cho một **lá**, không phải nút trong.
- Không từ mã nào là tiền tố của từ mã khác.
- Bộ giải mã có thể đọc bit từ trái sang phải và **xuất ký hiệu ngay khi đến lá**.

Tính prefix-free là một điều kiện **đủ** để giải mã tức thời và đơn nghĩa, không phải điều kiện duy nhất của mọi bộ mã có thể giải mã duy nhất. Có những bộ mã giải mã duy nhất nhưng không prefix-free; Huffman lựa chọn cấu trúc prefix-free để có thuật toán mã hóa/giải mã rõ ràng và tối ưu trong lớp đó.

### 9.2. Tần suất và xác suất

Nếu tần suất dương là `f_i` và tổng số ký hiệu là:

\[
N=\sum_i f_i,
\qquad p_i=\frac{f_i}{N},
\]

thì độ dài mã trung bình:

\[
\bar L=\sum_i p_i l_i
=\frac{\sum_i f_i l_i}{N}.
\]

Với ví dụ sáu ký hiệu:

\[
\bar L=\frac{224}{100}=2.24\ \text{bit/ký hiệu}.
\]

Một bảng mã cố định 3 bit cho 6 ký hiệu cần trung bình 3 bit/ký hiệu. Sự cải thiện xuất hiện vì `f` có tần suất lớn 45% nên được gán mã ngắn nhất, chỉ 1 bit.

**Huffman tối ưu độ dài trung bình trong lớp mã nhị phân prefix-free theo các xác suất được cho.** Nó không nhất thiết vượt được những công nghệ mã hóa khác xử lý **cả chuỗi, mô hình ngữ cảnh, hoặc khối nhiều ký hiệu**. Nếu phân bố tần suất thay đổi mạnh theo thời gian, một bảng mã Huffman tĩnh xây từ thống kê cũ có thể không còn phù hợp.

### 9.3. Cần lưu hoặc biết bảng mã

Chỉ có chuỗi bit `01100100111` chưa đủ để giải mã nếu phía nhận không biết cây tương ứng. Trong thực tế có thể:

- Gửi cây mã hoặc cấu trúc tương đương cùng dữ liệu.
- Gửi bảng độ dài từ mã rồi dựng mã Huffman canonical theo quy ước chung.
- Dùng một bảng mã chuẩn đã biết trước.
- Dùng mô hình thích nghi mà bộ mã hóa và giải mã cập nhật trạng thái đồng bộ.

Cũng cần một cách biết **khi nào payload kết thúc**: độ dài số bit thật, số ký hiệu dự kiến, một ký hiệu kết thúc riêng, hoặc một định dạng khung dữ liệu thích hợp. Nếu bitstream được đóng vào byte, các bit đệm ở cuối **không tự động** là nội dung cần giải mã.

### 9.4. Trường hợp chỉ một ký hiệu

Nếu bảng tần suất chỉ có một ký hiệu `A` với tần suất 7:

- Không có lần trộn nào, nên **chi phí trộn = 0**.
- Cây Huffman chỉ có một lá ở độ sâu 0. Trong mô hình thuần lý thuyết có biết số lượng ký hiệu, có thể biểu diễn mọi lần xuất hiện bằng **chuỗi bit rỗng**, vì mỗi ký hiệu được suy ra từ metadata.
- Trong nhiều bộ mã triển khai, ta gán cho `A` từ mã **`0`** dài 1 bit để việc mã hóa từng lần xuất hiện và giải mã payload dễ xử lý. Khi đó 7 lần xuất hiện tạo **7 bit**, không bằng chi phí trộn 0.

**Đây là ngoại lệ cần công bố** khi nói “merge cost bằng weighted code length”: đẳng thức trực tiếp áp dụng cho cây nhị phân có ít nhất **hai lá dương** và độ dài đúng bằng độ sâu; với một ký hiệu, lựa chọn thực dụng `0` có độ dài 1 khác độ sâu 0.

Chương trình Java dùng quy ước thực dụng `A→0`, nên `buildHuffman` với một ký hiệu sẽ trả `mergeCost=0` và `weightedBits=7`. Điều đó **không phải lỗi** của thuật toán, mà là khác biệt hợp đồng mã hóa một ký hiệu.

### 9.5. Các ký hiệu tần suất 0

Nếu một ký hiệu **không bao giờ xuất hiện**, nó không cần từ mã trong payload đang xét. Ví dụ code bỏ tần suất 0 để tập lá chỉ gồm các ký hiệu hoạt động. Nếu một giao thức vẫn yêu cầu có từ mã cho **tất cả ký hiệu trong alphabet**, kể cả tần suất 0, phải định nghĩa thêm cách đưa chúng vào cây; đây là điều kiện định dạng khác với việc chỉ tối ưu phần payload có tần suất dương.

Không được giả định bộ mã đã học từ một mẫu chỉ có ký hiệu `a..f` sẽ mã hóa được ký hiệu `g` mà không xây lại hoặc cập nhật bảng mã.

## 10. Trộn hai đường và nhiều đường: không nhầm bài toán

Thuật toán trên giải **trộn nhị phân không giới hạn thứ tự**. Trong hệ thống thật có những biến thể:

### 10.1. Trộn k đường

Nếu một lần được gộp **d khối cùng lúc**, chi phí vẫn bằng tổng trọng số d khối, bài toán thuộc lớp **d-ary optimal merge / d-ary Huffman**, không phải cứ dùng y nguyên giải pháp “lấy hai nhỏ nhất”.

Với cây d phân đầy đủ và số lá n, cần thỏa:

\[
n\equiv1\pmod{d-1}.
\]

Đối với số lá không thỏa, có thể bổ sung các lá giả trọng số 0 để đạt điều kiện, rồi dùng thuật toán tham lam d-ngả thích hợp. Việc thay đổi số đường trộn sẽ làm thay đổi cây và tổng số lần trộn.

**Chú ý:** số đường trộn thực tế còn phụ thuộc giới hạn RAM, vùng đệm, ổ đĩa, đọc/ghi I/O và xử lý song song. Mô hình chi phí chỉ bằng tổng kích thước có thể không đầy đủ đối với hệ thống thực.

### 10.2. Chỉ được trộn các khối liền kề

Nếu thứ tự ban đầu của các khối phải được giữ và chỉ được trộn **hai khối kề nhau**, không còn tự do chọn bất kỳ hai nhỏ nhất. Ví dụ nếu khối nhỏ nhất nằm xa nhau trong dãy, hai khối đó không thể trộn trực tiếp. Bài toán có thể cần quy hoạch động cho kế hoạch trộn đoạn liên tiếp và không thể áp dụng nguyên lập luận anh em “đặt hai nhỏ nhất ở đâu cũng được”.

### 10.3. Chi phí trộn không thuần tuyến tính

Nếu trộn `x` và `y` tốn một hàm như:

\[
c(x,y)\ne x+y,
\]

hoặc có chi phí phụ thuộc vào việc khối đã được nén, nằm trên ổ đĩa nào hay được chạy ở máy nào, cây tối ưu có thể khác. Không được gán một khối nặng trọng số bằng “ước lượng công việc” rồi tự nhận chứng minh Huffman vẫn đúng nếu hàm chi phí thật không còn cộng tuyến tính theo trọng số.

## 11. Trường hợp biên cần đặc tả rõ

| Dữ liệu / tình huống | Kết quả đúng hoặc cách xử lý |
| --- | --- |
| Không có khối cần trộn `[]` | Tổng chi phí trộn 0 |
| Một khối `[9]` | Tổng chi phí trộn 0 |
| Hai khối `[4,6]` | Một lần trộn 10, tổng 10 |
| Ba khối `[5,5,5]` | Trộn 5+5=10, rồi 5+10=15, tổng 25 |
| Bốn khối `[1,1,1,1]` | 2+2+4=8 |
| Khối không âm `[0,0,5]` | Trộn 0+0=0, rồi 0+5=5, tổng 5 |
| Một trọng số âm | Ngoài mô hình; hàm Java từ chối |
| Trọng số quá lớn gây tràn `long` | `Math.addExact` ném ngoại lệ; cần `BigInteger` nếu bài toán hỗ trợ số lớn hơn |
| Huffman không có ký hiệu tần suất dương | Cây rỗng, bảng mã rỗng, 0 bit |
| Huffman có một ký hiệu dương tần suất 7 | Quy ước ví dụ: mã `0`, weighted bits 7; chi phí trộn 0 |
| Nhiều ký hiệu cùng tần suất | Có thể có nhiều bảng mã tối ưu; quy tắc phá hòa quyết định chuỗi bit cụ thể |
| Thông điệp có ký hiệu ngoài bảng mã | Cần báo lỗi hoặc xây lại bảng mã |
| Chuỗi bit kết thúc giữa một từ mã | Báo lỗi dữ liệu không đầy đủ |
| Bản mã hóa cần hỗ trợ Unicode đầy đủ | Dùng code point/byte có quy ước, không mặc định một Java `char` là một ký tự hiển thị |

Một bài toán trộn file **có các kích thước bằng 0** vẫn có thể xử lý bằng min-heap, vì các nút trộn trọng số 0 không làm chi phí tăng; với Huffman, chương trình minh họa **loại ký hiệu tần suất 0** do chúng không đóng góp bit payload. Hai lựa chọn này phù hợp với hai hợp đồng khác nhau.

## 12. Những lỗi tư duy và cài đặt thường gặp

1. **Chỉ lấy hai nhỏ nhất của đầu vào ban đầu một lần.** Phải đưa trọng số gộp trở lại và chọn tiếp trong tập hiện tại.
2. **Không cộng chi phí trung gian.** Chỉ lấy trọng số gốc (tổng kích thước cuối) là sai mục tiêu; phải cộng kích thước của **mọi nút trộn**.
3. **Dùng max-heap thay vì min-heap** trong bài toán nhị phân này.
4. **Gộp hai khối lớn nhất trước** vì nghĩ “xử lý việc nặng sớm cho xong”; ví dụ 4,6,8,12 cho 76 thay vì 58.
5. **Cho rằng tham lam hiển nhiên đúng.** Cần chứng minh hai nhỏ nhất có thể là lá anh em sâu nhất và có cấu trúc con tối ưu.
6. **Quên các giả thiết của phép chứng minh:** được chọn cặp bất kỳ, không giới hạn thứ tự, chi phí mỗi trộn bằng tổng trọng số.
7. **Nhầm tổng chi phí trộn với trọng số gốc.** Gốc có trọng số bằng tổng khối, còn tổng chi phí bằng tổng trọng số **tất cả nút trong**, thường lớn hơn nhiều.
8. **Dùng `int` cho số byte hoặc tổng chi phí** khi dữ liệu có thể vượt 2 tỷ.
9. **Dùng phép trừ trong comparator** kiểu `(int)(a.weight-b.weight)` để so sánh trọng số, dễ tràn; nên dùng `Long.compare` hoặc `Comparator.comparingLong`.
10. **Không xử lý trường hợp một ký hiệu Huffman**, làm từ mã rỗng khiến ví dụ mã hóa/giải mã theo bit gặp khó khăn.
11. **Tưởng Huffman luôn cho một bảng bit duy nhất**; cách phá hòa hoặc đổi nhánh 0/1 có thể làm bảng mã khác mà vẫn tối ưu.
12. **Nhầm mã prefix-free với mã có độ dài bằng nhau**; Huffman cố ý tạo mã dài ngắn khác nhau.
13. **Không gửi/không biết bảng mã khi giải mã**; chỉ có bit payload không đủ thông tin.
14. **Đếm cả overhead rồi kết luận tỷ lệ nén bằng riêng tần suất × độ dài.** Số 224 bit trong ví dụ mới là payload lý thuyết.
15. **Dùng một `char` Java để đại diện mọi ký tự Unicode**; ký tự ngoài BMP có thể gồm hai code unit UTF-16.
16. **Không quy định số bit thực trước padding**, khiến bit đệm ở cuối byte có thể được đọc thành ký hiệu ngoài ý muốn.
17. **Chuyển bài toán sang trộn k đường hoặc trộn khối liền kề** mà vẫn dùng nguyên chứng minh trộn hai khối tự do.
18. **Nói heap luôn dùng `O(1)` bộ nhớ**; heap cần lưu các trọng số khối còn lại, `O(n)`.
19. **Đồng nhất chi phí tạo cây Huffman với chi phí mã hóa thông điệp.** Xây cây phụ thuộc kích thước alphabet; mã hóa payload phụ thuộc số ký hiệu và tổng bit đầu ra.

## 13. Checklist chọn mô hình và kiểm thử

Trước khi dùng thuật toán này, hãy kiểm tra:

1. **Đối tượng tối ưu** là chi phí trộn, số bit trung bình, hay một hàm khác?
2. **Chi phí trộn** có đúng bằng `x+y`, hay có thành phần phụ?
3. **Có thể chọn hai khối tùy ý** hay phải trộn liền kề / nhiều đường?
4. **Trọng số** có không âm và vừa kiểu số lưu trữ không?
5. **Input rỗng / một phần tử** phải cho kết quả thế nào?
6. **Ký hiệu trùng** trong bảng tần suất được gộp tần suất trước hay coi là lỗi đầu vào?
7. **Ký hiệu tần suất 0** có cần có mã trong định dạng đầu ra không?
8. **Có cần bảng mã xác định** để kiểm thử chính xác bitstring không? Nếu có, công bố quy tắc phá hòa và gán 0/1.
9. **Bản tin có thể chứa ký hiệu ngoài alphabet đã học** không?
10. **Giải mã** nhận cây/bảng mã và số bit thực bằng cách nào?
11. **Chi phí vận hành thực tế** có bị chi phối bởi bộ nhớ, I/O hay số lượng bộ đệm thay vì chỉ tổng kích thước?
12. **Chứng minh** có đủ greedy-choice, optimal substructure và điều kiện dừng không?

### Kiểm thử đối chiếu độc lập trên dữ liệu nhỏ

Với `n≤7` khối trọng số không âm, có thể dùng phép thử brute-force:

1. Liệt kê mọi cặp hai khối hiện có.
2. Trộn chúng, cộng chi phí, đệ quy giải bài toán còn lại.
3. Lấy tổng nhỏ nhất trong mọi lựa chọn.
4. So kết quả với `optimalMergeCost` dựa trên heap.

Brute-force rất đắt khi n lớn, nhưng hữu ích làm **oracle** kiểm chứng lập luận greedy trên những tập nhỏ, đặc biệt khi có trọng số bằng nhau và bằng 0.

Đối với Huffman:

- Mã của các ký hiệu hoạt động phải là **prefix-free**.
- `encode(message)` rồi `decode(bits)` phải khôi phục đúng thông điệp trong bảng mã hợp lệ.
- Với từ hai ký hiệu dương trở lên, `mergeCost` phải bằng `weightedBits` (nếu dùng cùng tập trọng số/tần suất).
- Với sáu ký hiệu mẫu, tổng phải là 224; với bốn khối 4,6,8,12, tổng trộn phải là 58.
- Với một ký hiệu, kiểm tra riêng quy ước mã `0`.
- Với nhiều trọng số bằng nhau, kết quả tổng chi phí không đổi dù bảng mã bit có thể khác giữa các quy tắc phá hòa.

## 14. Bài tập tự kiểm tra

**Bài 1 — Trộn bốn khối.** Cho kích thước `[4,6,8,12]`. Hãy liệt kê hai nhỏ nhất tại từng bước, trọng số mới và tổng chi phí. Vì sao lấy hai lớn nhất trước cho chi phí cao hơn?

**Bài 2 — Trọng số trùng.** Cho `[5,5,5]`. Hãy chọn lịch trộn tối ưu và tính tổng. Tại sao có thể có nhiều cách chọn cặp đầu nhưng cùng tổng?

**Bài 3 — Chi phí theo cây.** Với cây gộp `[4,6,8,12]` ở mục 3, hãy tính `sum_i w_i depth(i)` và kiểm tra bằng tổng các nút trong.

**Bài 4 — Huffman sáu ký hiệu.** Với `a:5,b:9,c:12,d:13,e:16,f:45`, hãy lập bảng các lần trộn, dựng cây, tìm một bộ mã prefix-free tối ưu và tính tổng số bit.

**Bài 5 — Giải mã.** Với bảng `a=1100,b=1101,c=100,d=101,e=111,f=0`, hãy giải mã `01100100111` và giải thích vì sao có thể biết lúc nào một ký hiệu kết thúc.

**Bài 6 — Kỳ vọng và cố định.** Với tổng tần suất 100 và 6 ký hiệu như bài 4, mã cố định cần bao nhiêu bit/ký hiệu? Tổng payload là bao nhiêu? So với Huffman, giảm bao nhiêu bit? Tại sao chưa thể khẳng định kích thước tệp cuối giảm đúng bằng chừng đó?

**Bài 7 — Một ký hiệu.** Với chỉ ký hiệu `X` xuất hiện 20 lần, chi phí trộn tối ưu là bao nhiêu? Nếu chọn từ mã thực dụng `X→0`, số bit payload là bao nhiêu? Vì sao hai số khác nhau?

**Bài 8 — Chứng minh greedy.** Phát biểu bổ đề “hai nhỏ nhất là anh em sâu nhất trong một cây tối ưu” và giải thích phép co hai lá thành lá có trọng số tổng làm bài toán còn lại cùng dạng ra sao.

**Bài 9 — Phá vỡ giả thiết.** Nếu chỉ được trộn hai khối **kề nhau**, tại sao không được áp dụng nguyên phương pháp “lấy hai trọng số nhỏ nhất toàn cục” mà không kiểm tra thêm điều kiện?

**Bài 10 — Độ phức tạp.** Với n khối trộn nhị phân và heap, có bao nhiêu lần trộn? Thời gian và bộ nhớ phụ là gì? Nếu chỉ cần chi phí tối ưu mà không cần cây mã, có bắt buộc lưu toàn bộ nút Huffman không?

### Đáp án gợi ý

1. Trộn `4+6=10`, `8+10=18`, `12+18=30`; tổng `58`. Nếu trộn `12+8=20`, `20+6=26`, `26+4=30`, tổng `76` vì khối nặng tham gia nhiều lần.
2. Trộn `5+5=10`, rồi `5+10=15`; tổng **25**. Các trọng số bằng nhau có thể tráo danh tính mà không đổi mục tiêu.
3. `4×3+6×3+8×2+12×1=58`, bằng `10+18+30`.
4. Các trọng số mới `14,25,30,55,100`, tổng **224**. Một bộ mã: `a=1100,b=1101,c=100,d=101,e=111,f=0`; tổng đóng góp bit lần lượt `20,36,36,39,48,45`, bằng 224.
5. Giải mã thành **face**. Vì mỗi mã gắn một lá và không mã nào là tiền tố của mã khác, bộ giải mã có thể xuất khi đến lá rồi quay về gốc.
6. Cần `ceil(log₂6)=3` bit/ký hiệu, tổng `300` bit. Huffman dùng `224` bit, ít hơn **76 bit**. Chưa tính overhead cây/bảng mã và định dạng.
7. Chi phí trộn **0** vì không trộn hai khối nào. Từ mã `0` tạo **20 bit**; nó là quy ước lưu trữ một ký hiệu, còn độ sâu cây một lá là 0.
8. Hai nhỏ nhất có thể đặt ở hai lá anh em sâu nhất bằng hoán đổi không tăng tổng `weight×depth`. Co chúng thành lá `a+b` làm chi phí còn lại đúng bài toán cùng loại, cộng thêm `a+b`.
9. Hai nhỏ nhất có thể không đứng cạnh nhau; không có phép trộn như vậy trong miền lời giải hợp lệ, nên chứng minh greedy gốc không còn áp dụng trực tiếp.
10. Với `n≥1` có `n-1` lần trộn; heap cho `O(n log(n+1))` thời gian và `O(n)` bộ nhớ. Nếu chỉ cần tổng chi phí, lưu các **trọng số trong heap** là đủ, không cần toàn bộ cây mã.

## Ghi nhớ

**Optimal merge và Huffman dùng chung một mẫu tham lam:** lấy **hai trọng số nhỏ nhất**, cộng chúng, ghi nhận chi phí, rồi đưa tổng trở lại **min-heap**. Kế hoạch này tối ưu khi được phép trộn **hai khối bất kỳ** và chi phí mỗi lần đúng bằng **tổng trọng số**. Cây trộn có tổng chi phí bằng `sum weight×depth` của các lá; khi trọng số là tần suất ký hiệu, đây chính là **tổng số bit của một mã Huffman prefix-free**. Thuật toán heap xây kế hoạch/cây trong `O(n log(n+1))` thời gian; cách gán mã có thể không duy nhất, và hiệu quả nén thực còn phụ thuộc metadata, quy ước một ký hiệu và định dạng bitstream. Luôn phân biệt **lý do greedy đúng theo mô hình** với các ràng buộc hệ thống thực tế.
