# Giới hạn trường hợp xấu nhất của các bảo đảm kỳ vọng

Một cấu trúc dữ liệu có thời gian **O(log n) kỳ vọng** không có nghĩa **mọi** lần tìm chỉ mất O(log n). Một thuật toán có thời gian **O(n log n) kỳ vọng** không có nghĩa nó không bao giờ chạy Θ(n²). Sự khác biệt này đặc biệt quan trọng khi thiết kế hệ thống có thời hạn đáp ứng, xử lý đầu vào đối kháng, hoặc phải giới hạn bộ nhớ.

Bài **“Giới hạn trường hợp xấu nhất của các bảo đảm kỳ vọng”** nằm trong chương **Cấu trúc ngẫu nhiên** của module **COMPUTER_SCIENCE_DATA_STRUCTURES**. Trong phạm vi học cấu trúc dữ liệu từ mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap đến đồ thị, ta tiếp tục đánh giá **bất biến**, thao tác và **độ phức tạp thời gian/bộ nhớ**. Trọng tâm ở đây là đọc đúng chữ *kỳ vọng* và nhận ra **những điều mà bảo đảm ấy không hứa hẹn**.

Để học bài này, bạn chỉ cần biết tìm/chèn/xóa trong cây tìm kiếm nhị phân (BST), danh sách liên kết, cách hoạt động cơ bản của skip list hoặc bảng băm, cùng xác suất và ký hiệu Big-O.

**Sau bài, bạn có thể:**

- Phân biệt **worst-case**, **expected**, **amortized**, **average-input** và **high probability**.
- Viết đúng thứ tự các lượng từ trong bảo đảm ngẫu nhiên: cố định đầu vào, rồi lấy kỳ vọng theo lựa chọn của thuật toán.
- Dựng ví dụ xấu nhưng hợp lệ cho **treap**, **skip list**, **quicksort chọn pivot ngẫu nhiên** và **hashing**.
- Tính xác suất một trường hợp xấu cụ thể, dùng **Markov**, **union bound** và mô hình hình học để hiểu xác suất đuôi.
- Nêu được khi nào O(log n) kỳ vọng là đủ và khi nào cần **giới hạn worst-case**, deadline hoặc cơ chế fallback có chứng minh.
- Chạy ví dụ Python đo số phép so sánh/số bước trên đầu vào cố định mà không ngộ nhận rằng thực nghiệm chứng minh xác suất.
- Phân tích ảnh hưởng của seed/PRNG, giới hạn mức, lựa chọn ngẫu nhiên phụ thuộc đầu vào và đối thủ thích nghi.

## 1. Một lời hứa về hiệu năng phải nói rõ điều gì?

Giả sử thuật toán `A` nhận đầu vào `x` có kích thước `n` và dùng một chuỗi lựa chọn ngẫu nhiên `r`. Ta ký hiệu:

\[
T(x,r)
\]

là số bước hoặc chi phí thực thi, phụ thuộc **cả dữ liệu** lẫn **lựa chọn ngẫu nhiên**. Chúng ta có nhiều cách hỏi về T.

| Loại bảo đảm | Câu hỏi cần trả lời | Có thể tồn tại một lần chạy rất chậm? |
| --- | --- | --- |
| **Worst-case** | Chi phí lớn nhất trên các đầu vào và lựa chọn hợp lệ là gì? | Chỉ trong giới hạn worst-case đã chứng minh |
| **Expected over randomness** | Với đầu vào cố định, trung bình trên các lần rút random là gì? | **Có** |
| **Average over inputs** | Nếu đầu vào được lấy từ một phân phối giả định, trung bình là gì? | **Có**, và phụ thuộc phân phối đầu vào |
| **Amortized** | Phân bổ tổng chi phí qua một chuỗi thao tác như thế nào? | **Có** đối với từng thao tác |
| **High probability** | Xác suất vượt ngưỡng là bao nhiêu, theo n? | **Có**, nhưng có chặn xác suất cụ thể |
| **Hard deadline** | Có thể cam kết không vượt thời hạn trong mọi điều kiện được mô hình hóa không? | Không, nếu bảo đảm hợp lệ thực sự là cứng |

Bảng không nói worst-case và high-probability là hai cấu trúc dữ liệu; chúng là **hai kiểu phát biểu** về thuật toán và giả định.

### 1.1. Worst-case là chặn cho mọi tình huống được xét

Với một thuật toán ngẫu nhiên, một cách định nghĩa worst-case chi phí ở kích thước n là:

\[
W(n)=\sup_{|x|=n}\;\sup_{r}\;T(x,r).
\]

Nói `W(n)=O(\log n)` nghĩa là có một chặn logarit cho **mọi đầu vào và mọi chuỗi lựa chọn ngẫu nhiên** hợp lệ, với các hằng số không phụ thuộc n.

Nếu thuật toán có vòng lặp rút số lần không giới hạn, worst-case có thể không có chặn hữu hạn **chỉ theo n**: ngay một đầu vào rất nhỏ vẫn có thể gặp chuỗi rút kéo dài tùy ý.

### 1.2. Expected worst-input là chặn kỳ vọng cho từng đầu vào

Một bảo đảm ngẫu nhiên thường có dạng:

\[
\boxed{
E_{\max}(n)=
\sup_{|x|=n}\mathbb{E}_{R}[T(x,R)]
=O(\log n)
}.
\]

Cách đọc:

> Với **mỗi đầu vào cố định** có kích thước n, khi lấy trung bình trên random nội bộ được rút đúng mô hình, chi phí không vượt bậc logarit theo n.

Điều này **không** chặn mọi lựa chọn R. Một số lựa chọn có thể cho đường tìm dài Θ(n), miễn chúng đủ hiếm để kỳ vọng vẫn ở mức logarit.

Chú ý **thứ tự của phép lớn nhất và kỳ vọng**:

\[
\sup_x E_R[T(x,R)]
\;\le\;E_R[\sup_x T(x,R)].
\]

Không được lặng lẽ đổi chỗ hai toán tử này. Ở vế phải, một đối thủ có thể được hiểu là **chọn đầu vào x sau khi quan sát R**, mạnh hơn mô hình đầu vào cố định trước khi rút random.

### 1.3. Average-input không phải expected do thuật toán tự random

Một BST thường, không tự cân bằng, có thể có độ sâu trung bình tốt trên **thứ tự chèn ngẫu nhiên**. Nhưng nếu người dùng gửi khóa tăng dần, nó có thể suy biến thành đường thẳng.

Một **treap** hoặc **skip list** dùng random nội bộ để chọn priority/chiều cao có thể giữ kết quả expected logarit dưới các giả định thích hợp, **ngay cả khi** thứ tự khóa đầu vào tăng dần.

Đừng sử dụng kết quả phân tích trung bình với đầu vào ngẫu nhiên để thay cho chặn expected theo RNG trên **đầu vào tùy ý đã cố định**.

### 1.4. Đơn vị chi phí cũng là một phần của lời hứa

“O(log n)” thường đếm **số bước trừu tượng**, như phép so sánh, di chuyển qua cạnh, hoặc cập nhật liên kết. Nó không tự nói:

- Một thao tác mất bao nhiêu mili-giây trên máy cụ thể.
- Bao nhiêu cache miss hoặc page fault xảy ra.
- Hệ điều hành có trì hoãn tiến trình hay không.
- Có lỗi cấp phát hoặc dừng do giới hạn bộ nhớ hay không.
- Một dịch vụ concurrent chờ khóa bao lâu.

Muốn cam kết deadline thực tế, cần một mô hình chi phí và điều kiện vận hành **rõ hơn Big-O**.

## 2. Đúng với mọi seed, nhanh theo trung bình seed

Một cấu trúc ngẫu nhiên kiểu **Las Vegas** tách hai câu hỏi:

1. **Tính đúng:** mọi chuỗi random hợp lệ đều phải tạo kết quả đúng (giả sử code và môi trường không hỏng).
2. **Tốc độ:** các chuỗi random khác nhau có thể khiến số bước khác nhau; ta chứng minh kỳ vọng của số bước.

Ví dụ:

- Treap đúng bất biến BST và heap thì vẫn trả đúng khóa dù chiều cao của nó bằng n.
- Skip list có tầng 0 đầy đủ, các tầng khác là dãy con sorted thì vẫn tìm đúng dù mọi node cao một tầng.
- Quicksort chia và ghép đúng vẫn trả mảng sorted dù luôn chọn pivot nằm ở một đầu, dẫn đến số phép so sánh lớn.

Sự kiện **chậm** không đồng nghĩa sự kiện **sai kết quả**.

### 2.1. Monte Carlo là một loại bảo đảm khác

Một thuật toán **Monte Carlo** thường có giới hạn thời gian theo cách thiết kế nhưng **cho phép xác suất sai kết quả**. Ví dụ, một bộ lọc Bloom có thể trả **dương tính giả** theo các giả định hashing, nhưng không được xem xác suất đó là “thời gian chạy chậm”.

Không đánh đồng:

- `Pr(T>t)`: xác suất **chậm quá t**.
- `Pr(\text{kết quả sai})`: xác suất **sai**.
- `E[T]`: **chi phí trung bình** theo nguồn random.

Một hệ thống thực tế có thể vừa có giới hạn độ trễ vừa có xác suất sai, và phải công bố **từng loại rủi ro riêng**.

## 3. Ví dụ 1: treap có expected height O(log n) nhưng vẫn có đường dài Θ(n)

**Treap** kết hợp:

- **BST theo key**: khóa cây trái nhỏ hơn, khóa cây phải lớn hơn.
- **Heap theo priority**: chọn quy ước min-heap, priority cha nhỏ hơn priority con.

Mỗi khóa mới nhận một priority ngẫu nhiên độc lập, lý tưởng là lấy từ một phân phối liên tục để tránh hòa.

### 3.1. Một kết quả random cực xấu

Với n khóa `1,2,3,4,5`, giả sử priority tăng cùng key:

```text
key:        1   2   3   4   5
priority:   1   2   3   4   5

Treap min-priority:

1
 \
  2
   \
    3
     \
      4
       \
        5
```

Cây **vẫn đúng BST và min-heap**, nhưng chiều cao là `n-1` cạnh. Tìm 5 hoặc một khóa lớn hơn tất cả có thể phải đi qua **Θ(n)** node.

Vậy câu:

> “Treap tìm kiếm O(log n) trong mọi trạng thái hợp lệ.”

là **sai**.

Câu chính xác là:

> “Dưới mô hình priority độc lập phù hợp, treap có đường tìm và chiều cao **O(log n) kỳ vọng**; worst-case vẫn có thể là Θ(n).”

### 3.2. Trạng thái xấu có xác suất dương, không bị loại trừ

Trong mô hình n priority phân biệt, độc lập, cùng phân phối liên tục, tất cả n! thứ tự ưu tiên tương đối có xác suất như nhau.

Một thứ tự cụ thể — priority tăng theo key — có xác suất:

\[
\boxed{\Pr(\text{priority tăng hoàn toàn theo key})=\frac1{n!}}.
\]

Vì vậy đường lệch phải ở trên **có thể xảy ra**, dù xác suất rất nhỏ khi n lớn. Để chứng minh **tồn tại worst-case**, ta chỉ cần chỉ ra **một** cấu hình hợp lệ như vậy, không phải tính đầy đủ mọi cách tạo cây lệch.

**Cẩn thận:** `1/n!` là xác suất của **một mẫu thứ tự cụ thể**. Không tự nói đó là xác suất của **mọi trường hợp chiều cao Θ(n)**.

### 3.3. Phát biểu expected của treap đến từ đâu?

Sắp n khóa phân biệt theo thứ tự:

\[
x_1<x_2<\cdots<x_n.
\]

Trong treap min-priority, `x_j` là tổ tiên của `x_i` khi và chỉ khi priority của `x_j` nhỏ nhất trên đoạn khóa giữa `x_i` và `x_j` (với j khác i).

Do tính đối xứng của priority liên tục IID:

\[
\Pr(x_j\text{ là tổ tiên của }x_i)
=\frac1{|i-j|+1}.
\]

Độ sâu `D_i` bằng số tổ tiên thực sự của `x_i`, nên:

\[
\begin{aligned}
E[D_i]
&=\sum_{j<i}\frac1{i-j+1}
 +\sum_{j>i}\frac1{j-i+1}\\
&=H_i+H_{n-i+1}-2\\
&=O(\log n).
\end{aligned}
\]

Ở đây `H_m=1+1/2+\cdots+1/m` là **số điều hòa**, không phải chiều cao nút skip list ở phần sau.

Đây là chứng minh trực tiếp cho **độ sâu kỳ vọng của một khóa đã cố định**. Kết quả chuẩn **chiều cao cây kỳ vọng O(log n)** còn cần một phân tích xác suất mạnh hơn về nút sâu nhất; không được chỉ lấy `E[\max_iD_i]=\max_iE[D_i]` vì đẳng thức đó **không đúng nói chung**.

### 3.4. Thứ tự chèn không giải quyết worst-case bằng phép màu

Nếu dữ liệu `1,2,...,n` được chèn tăng dần, một BST thường không quay có thể lệch chắc chắn. Treap ngẫu nhiên hóa priority và quay để bảo toàn heap, nên phân phối hình dạng có thể tốt **theo kỳ vọng**.

Tuy nhiên, **randomization là một phân phối, không phải bất biến cân bằng cứng**. Một seed xấu hoặc một kịch bản lộ priority có thể dẫn tới đường tìm dài; không thể dựa vào “cây thường khá thấp” để đáp ứng một deadline worst-case.

## 4. Ví dụ 2: skip list có expected O(log n) nhưng vẫn có tầng đáy dài

Một **skip list** lưu mọi khóa ở tầng 0; những tầng cao là dãy con của tầng thấp. Mỗi nút bắt đầu cao `H=1`, sau đó được nâng thêm tầng với xác suất p, `0<p<1`.

Với mô hình hình học không trần:

\[
\Pr(H\ge k)=p^{k-1},\qquad
\Pr(H=1)=1-p.
\]

### 4.1. Sự kiện mọi nút chỉ có một tầng

Giả sử n nút bốc chiều cao độc lập. Xác suất tất cả đều có `H=1` là:

\[
\boxed{\Pr(\forall j,\ H_j=1)=(1-p)^n}.
\]

Khi ấy chỉ còn:

```text
L0: HEAD -> k1 -> k2 -> ... -> kn -> NULL
```

Tìm khóa lớn hơn mọi khóa hoặc khóa kn phải đi theo nhiều liên kết, tốn **Θ(n)** bước. Cấu trúc **không vi phạm bất biến**, chỉ **không có đường nhảy hữu ích**.

Với p=1/2 và n=10:

\[
\Pr(\text{tất cả H=1})=(1/2)^{10}=\frac1{1024}.
\]

Đây là một ví dụ hoàn toàn cụ thể: xác suất nhỏ không phải xác suất bằng 0.

### 4.2. Vì sao các tầng vẫn mang lại kỳ vọng logarit?

Một node đạt tầng chỉ số i nếu `H\ge i+1`, xác suất `p^i`. Với tập n node cố định, độc lập:

\[
E[N_i]=np^i.
\]

Các tầng cao thưa dần theo cấp số nhân, nên tìm kiếm có thể đi ngang qua những đoạn dài, rồi xuống các tầng thấp để tinh chỉnh vị trí. Khi **trần mức đủ cao so với quy mô n** và rút mức độc lập đúng mô hình, số bước tìm **O(log n) kỳ vọng**.

Điều này không loại trừ sự kiện all-H=1 và nhiều phân bố không thuận lợi khác.

### 4.3. Trần mức L giúp kiểm soát tài nguyên nhưng có đánh đổi

Cài đặt thường đặt `MAX_LEVEL=L`, do đó:

- Chiều cao node không vượt L.
- Tìm từ tầng cao xuống thấp có nhiều nhất L lần xử lý mức.
- Với n node, một lượt tìm đi ngang tối đa n lần vì mỗi bước tới khóa lớn hơn, nên worst-case theo trạng thái là **O(n+L)**.
- Nếu cấu trúc cấp `update[L]` cho chèn/xóa, thêm O(L) thời gian/bộ nhớ tạm phải được tính rõ.

Nhưng **L cố định quá thấp** cũng có thể làm mất bảo đảm expected O(log n) khi n tăng vô hạn.

Ở tầng cao nhất i=L−1:

\[
E[N_{L-1}]=np^{L-1}.
\]

Nếu p,L là hằng số và n tăng, số node trên tầng đỉnh tăng Θ(n). Truy vấn lớn hơn mọi khóa sẽ phải đi qua **tất cả** node trên tầng đỉnh trước khi xuống, nên kỳ vọng đã là **Ω(n)** đối với cấu hình L cố định.

**Kết luận kép:** L không được nhỏ quá khiến tầng đỉnh đông, cũng không được lớn một cách vô lý khiến cấp phát head/update tốn tài nguyên. Cần nêu **miền n được hỗ trợ** và chọn L phù hợp.

### 4.4. Không trần thì worst-case có thể không chặn được chỉ theo n

Nếu hàm bốc chiều cao có vòng:

```text
height = 1
while coin_is_heads():
    height += 1
```

không có `MAX_LEVEL`, thì một node vẫn có xác suất dương được nâng **k lần cho mọi k hữu hạn**. Do đó, xét worst-case trên **mọi chuỗi random**, số vòng bốc mức có thể lớn tùy ý **ngay khi n=1**. Không có chặn tất định hữu hạn chỉ theo n cho chính vòng bốc này.

Mặc dù:

\[
E[H]=\frac1{1-p}<\infty,
\]

đó là **kỳ vọng hữu hạn**, không phải giới hạn cứng. Trong hệ thống cần phân bổ bộ nhớ không vượt trần, hãy đặt trần và xử lý cấp phát lỗi rõ ràng.

## 5. Ví dụ 3: randomized quicksort có expected O(n log n) nhưng worst-case Θ(n²)

**Quicksort** chọn một phần tử **pivot**, phân chia các phần tử nhỏ/lớn hơn pivot, rồi sắp xếp hai phía. Một phiên bản randomized quicksort chọn pivot đồng đều từ những phần tử của đoạn hiện tại.

### 5.1. Khi pivot liên tục là cực trị

Với n khóa phân biệt, nếu mỗi lần chọn pivot lại là **nhỏ nhất hoặc lớn nhất** của đoạn hiện tại, phép chia thành hai phía có kích thước:

\[
(0,n-1),\ (0,n-2),\ldots.
\]

Số phép so sánh ở một hiện thực classic two-way partitioning có dạng:

\[
(n-1)+(n-2)+\cdots+1
=\frac{n(n-1)}2
=\Theta(n^2).
\]

Chọn pivot ngẫu nhiên **giảm xác suất** gặp chuỗi cực trị, nhưng **không cấm** chuỗi đó.

### 5.2. Xác suất một chuỗi pivot cực trị

Giả sử mỗi lần chia đoạn dài m có các khóa phân biệt và pivot đồng đều trên m vị trí. Xác suất pivot là **một trong hai cực trị** là `2/m` khi m≥2.

Để mọi lần chia còn lại đều cực trị, xác suất bằng:

\[
\boxed{
\prod_{m=2}^{n}\frac2m
=\frac{2^{n-1}}{n!}
}.
\]

Đây là xác suất của **sự kiện chia hoàn toàn một phía ở mọi bước** trong mô hình chuẩn (các lựa chọn random độc lập). Nó rất nhỏ khi n lớn nhưng **khác 0**.

Với chiến lược **pivot đầu tiên** trên mảng đã tăng dần, trường hợp này xảy ra một cách **tất định**, không cần chờ may rủi xấu.

### 5.3. Vì sao kỳ vọng lại O(n log n)?

Với n khóa phân biệt và pivot ngẫu nhiên đều, một phân tích theo cặp phần tử chỉ ra số phép so sánh kỳ vọng trong quicksort chuẩn:

\[
\boxed{
E[C_n]=2(n+1)H_n-4n
},
\]

trong đó `H_n=1+1/2+\cdots+1/n`. Vì `H_n=\Theta(\log n)`:

\[
E[C_n]=\Theta(n\log n).
\]

Công thức chính xác ở đây dành cho **mô hình quicksort chuẩn với khóa phân biệt và số so sánh cặp**. Biến thể chia ba ngăn bằng `<,=,>` hoặc ngôn ngữ/cài đặt khác có số phép so sánh cụ thể khác, dù vẫn có cùng xu hướng expected O(n log n) trong mô hình phù hợp.

### 5.4. Quicksort và treap có mối liên hệ

Một lần quicksort tạo **cây phân hoạch** dựa trên pivot. Treap tạo **hình dạng cây** dựa trên priority. Cả hai có liên hệ với random BST và đều có thể tạo cây dài trong một chuỗi lựa chọn xấu.

Nhưng quicksort là **thuật toán sắp xếp một lần**, còn treap là **cấu trúc tìm kiếm động** được duy trì qua tìm/chèn/xóa. Phải phân biệt ngữ nghĩa, bất biến và chi phí thao tác của chúng.

## 6. Ví dụ 4: randomized hashing giảm va chạm trung bình, không loại trừ va chạm

Bảng băm lưu khóa theo bucket. Nếu nhiều khóa rơi vào cùng bucket, độ dài chuỗi va chạm tăng hoặc số phép dò tăng.

Với **separate chaining** và bảng có m bucket, hệ số tải là `\alpha=n/m`. Dưới giả định phân bố hash đủ tốt, một truy vấn khóa cố định có chi phí kỳ vọng dạng:

\[
O(1+\alpha).
\]

Nếu tải `\alpha` được duy trì như hằng số, đó là **O(1) kỳ vọng**. Tuy nhiên:

- Một cấu hình va chạm nặng có thể tạo chuỗi dài Θ(n).
- Một hàm hash không phù hợp phân bố khóa thực tế có thể khiến giả định phân tích sai.
- **Resize** bảng có thể tốn O(n) cho một thao tác, ngay cả khi chèn có chi phí khấu hao O(1).
- Trong **open addressing**, clustering, tombstone và chính sách dò làm thay đổi mô hình chi phí; không được sao chép nguyên xi công thức của separate chaining.

### 6.1. Universal hashing giúp điều gì?

Một họ hàm băm ngẫu nhiên được gọi là **universal** (theo định nghĩa thường dùng) khi với hai khóa khác nhau `x\ne y`:

\[
\Pr_h[h(x)=h(y)]\le\frac1m.
\]

Với một tập n khóa cố định, dùng union bound cho tất cả các cặp:

\[
\Pr(\exists \text{ cặp va chạm})
\le {n\choose2}\frac1m.
\]

Chặn này có thể lớn hơn 1 nên khi dùng thực tế phải lấy min với 1; **không có nghĩa** mọi tập n khóa luôn không va chạm. Nó cũng **không tự nói** tất cả các hàm trong họ đều sinh ra trạng thái xấu như nhau.

Kỳ vọng chi phí có thể tốt với một truy vấn khóa cố định nhưng không phải chặn cho **mọi chuỗi thao tác được chọn sau khi biết hash seed**.

### 6.2. Mô hình đối thủ quan trọng hơn từ “random”

Một tác nhân chỉ gửi các khóa cố định **trước khi** seed được rút khác một tác nhân:

1. Có thể quan sát bucket hoặc độ trễ.
2. Dò tìm các khóa va chạm.
3. Gửi hàng nghìn khóa vừa tìm được để cố tình tạo một chuỗi dài.

Đối với hệ thống có yêu cầu chống tấn công độ phức tạp, phải định nghĩa mô hình quan sát, nguồn seed, quy tắc xoay seed và giới hạn tài nguyên. “Dùng hash có random” không phải chứng minh an toàn trước mọi adversary.


## 7. Vì sao kỳ vọng tốt vẫn có thể chứa rủi ro lớn?

Xét một thao tác ngẫu nhiên có chi phí `T_n`, với n≥2:

\[
T_n =
\begin{cases}
1 & \text{với xác suất }1-\frac1n,\\
n & \text{với xác suất }\frac1n.
\end{cases}
\]

Tính kỳ vọng:

\[
E[T_n]
=1\left(1-\frac1n\right)+n\frac1n
=2-\frac1n=O(1).
\]

Nhưng **worst-case** là `n`, tức **Θ(n)**. Một trong n kết quả rút ngẫu nhiên có thể tốn n bước dù kỳ vọng hằng số. Không có nghịch lý: chi phí hiếm được cân bởi xác suất nhỏ khi lấy trung bình.

### 7.1. Kỳ vọng O(log n) không tự cho “high probability”

Xét một biến khác, khi n đủ lớn:

\[
T_n =
\begin{cases}
1 & \text{với xác suất }1-\frac1{\log n},\\
(\log n)^2 & \text{với xác suất }\frac1{\log n}.
\end{cases}
\]

Khi đó:

\[
E[T_n]
=1-\frac1{\log n}+\log n
=O(\log n).
\]

Với mọi hằng c>0, khi n đủ lớn, xác suất `T_n>c\log n` vẫn là **`1/\log n`**, giảm chậm hơn nhiều so với `1/n^3`.

Đây là **phân phối minh họa về logic**, không phải phát biểu rằng treap hoặc skip list thực tế có thời gian đúng phân phối này. Nó cho thấy chỉ biết kỳ vọng thì **không thể tự suy ra một tail bound mạnh**.

### 7.2. Trạng thái xấu có thể kéo dài qua nhiều truy vấn

Nếu treap hoặc skip list dùng random để tạo hình dạng **một lần**, một seed bất lợi có thể làm nhiều truy vấn liên tiếp cùng tốn n bước. Kỳ vọng theo nhiều seed không sửa chữa hình dạng chậm của **seed đã được chọn**.

Vì vậy cần phân biệt:

- **Giá trị trung bình trên nhiều lần rút**.
- **Chi phí của một lần chạy cụ thể**.
- **Chi phí nhiều request sau khi cấu trúc đã hình thành**.

## 8. Markov, union bound và xác suất đuôi

Muốn hiểu trường hợp chậm hiếm đến đâu, cần hỏi về **xác suất vượt ngưỡng**, không chỉ kỳ vọng.

### 8.1. Bất đẳng thức Markov

Với `T\ge0` và `a>0`:

\[
\boxed{\Pr(T\ge a)\le\frac{E[T]}{a}}.
\]

Nếu `E[T]\le C\log n`, chọn `a=100C\log n`:

\[
\Pr(T\ge100C\log n)\le\frac1{100}.
\]

Đây là một **chặn xác suất tối đa 1%**, không phải `1/n^3`. Markov áp dụng rất rộng nhưng thường lỏng; không được diễn giải nó thành một chặn xác suất mạnh hơn khi chưa có chứng minh.

### 8.2. Union bound cho nhiều sự kiện

Với các sự kiện `A_1,\ldots,A_m`:

\[
\boxed{\Pr(A_1\cup\cdots\cup A_m)
\le\sum_{i=1}^m\Pr(A_i)}.
\]

Không cần các sự kiện độc lập. Nếu từng sự kiện xấu có xác suất ≤`\delta`:

\[
\Pr(\text{ít nhất một sự kiện xấu})\le\min(1,m\delta).
\]

Ví dụ m=1 triệu request, mỗi request có xác suất trễ không quá `10^{-9}` theo một chứng minh hợp lệ, thì xác suất có ít nhất một lần trễ không quá `10^{-3}`.

**Nhưng:** từ expected O(log n) không tự có `\delta=10^{-9}`. Phải tính chặn xác suất cho **ngưỡng độ trễ cụ thể** trước rồi mới áp dụng union bound.

### 8.3. Chặn đuôi thực sự cho chiều cao skip list

Với n node có chiều cao rút độc lập theo hình học:

\[
\Pr(H_j\ge k)=p^{k-1}.
\]

Đặt `M=\max(H_1,\ldots,H_n)`. Union bound cho:

\[
\boxed{\Pr(M\ge k)\le np^{k-1}}.
\]

Chọn `c>0` và:

\[
k=1+\left\lceil(1+c)\log_{1/p}n\right\rceil.
\]

Khi đó:

\[
np^{k-1}\le n^{-c}.
\]

Đây là phát biểu **high probability về chiều cao tối đa**. Nó không tự đồng nghĩa với một chặn như vậy cho **số bước tìm**: skip list rất thấp vẫn có thể có đường ngang dài. Cần một chứng minh riêng cho chi phí đường tìm nếu muốn high probability cho tìm kiếm.

### 8.4. Số node trên một tầng và chặn Chernoff

Tầng i của skip list chứa mỗi node với xác suất `p^i`, trong mô hình IID:

\[
N_i\sim\operatorname{Binomial}(n,p^i),
\qquad \mu_i=E[N_i]=np^i.
\]

Với `0<\varepsilon\le1`, một dạng chặn Chernoff:

\[
\Pr(|N_i-\mu_i|\ge\varepsilon\mu_i)
\le 2e^{-\varepsilon^2\mu_i/3}.
\]

Khi `\mu_i` lớn, số node thường tập trung quanh kỳ vọng; khi `\mu_i` gần 1, tầng ấy có thể rỗng rất thường xuyên. Các biến đếm **giữa những tầng khác nhau** không độc lập, vì nút ở tầng i+1 chắc chắn ở tầng i.

### 8.5. Bộ nhớ pointer: từ trung bình tới mức dao động

Nếu node cấp đúng H ô forward, số slot tổng `S=\sum_{j=1}^nH_j`. Với các H độc lập không trần:

\[
E[S]=\frac n{1-p},\qquad
Var(S)=\frac{np}{(1-p)^2}.
\]

Markov cho chặn thô, còn Chebyshev cho `\varepsilon>0`:

\[
\Pr(|S-E[S]|\ge\varepsilon n)
\le\frac{p}{\varepsilon^2(1-p)^2n}.
\]

Chặn này giảm O(1/n) khi p cố định. Nhưng pointer count không bằng byte đã cấp: cần tính thêm node header, payload, alignment, allocator, sentinel HEAD và lỗi quota. Một kỳ vọng bộ nhớ đẹp không bảo đảm mọi lần cấp phát vật lý đều thành công.

## 9. Một thao tác và một chuỗi thao tác: điều gì được phép cộng?

Gọi `T_i` là chi phí của thao tác thứ i trong chuỗi m thao tác, tổng `C_m=\sum_iT_i`. Luôn có:

\[
\boxed{E[C_m]=\sum_{i=1}^mE[T_i]}.
\]

Tuyến tính kỳ vọng **không cần các `T_i` độc lập**. Tuy nhiên, muốn kết luận expected tổng O(m log n), cần chặn các `E[T_i]` phù hợp với **chuỗi thao tác và mô hình random thực sự**.

### 9.1. Các lần chậm có thể phụ thuộc rất mạnh

Một skip list hình thành một lần rồi phục vụ m truy vấn không rút lại chiều cao cho mỗi lần `contains`. Nếu cấu trúc đang rất thấp, cả m lần tìm khóa lớn hơn mọi khóa có thể chậm.

Không được tính:

```text
Pr(m lần tìm cùng chậm)
  = Pr(lần tìm chậm)^m
```

khi mọi lần dùng **cùng hình dạng ngẫu nhiên**. Các sự kiện chậm có thể tương quan hoàn toàn. Có thể cộng kỳ vọng, nhưng không nhân xác suất khi thiếu độc lập.

### 9.2. Đối thủ oblivious và adaptive

**Oblivious adversary:** lịch thao tác được chọn không dựa vào random nội bộ chưa rút hoặc kết quả random mà thuật toán đang giữ bí mật.

**Adaptive adversary:** lựa chọn thao tác tiếp theo có thể dựa trên quan sát về hình dạng, độ trễ, khóa đã trả hoặc kết quả trước đó.

Ví dụ đối thủ quan sát chiều cao rồi **chỉ giữ các node thấp**, xóa các node cao. Tập node còn lại bị **chọn lọc theo height** và không có cùng phân phối IID như một tập khóa được cố định trước khi bốc chiều cao. Công thức `N_i\sim Binomial(n,p^i)` không tự còn đúng cho tập node sống ấy.

Một cấu trúc có thể có phân tích riêng trước một số dạng đối thủ thích nghi, nhưng không thể lấy một định lý cho tập khóa cố định rồi tuyên bố đã xử lý mọi adversary.

### 9.3. Expected có điều kiện mạnh hơn expected thông thường

Một điều muốn chứng minh cho từng lịch sử `\mathcal H_{i-1}` là:

\[
E[T_i\mid \mathcal H_{i-1}]
\le C\log(n+1).
\]

Đây là phát biểu **có điều kiện trên lịch sử**. Nó mạnh hơn một chặn kỳ vọng **không điều kiện** đối với một chuỗi thao tác cố định.

Nếu lịch sử đã hé lộ hình dạng cao n, truy vấn tiếp theo có thể có chi phí **đã biết chắc là Θ(n)**; không thể giả vờ rằng độ sâu của chính trạng thái đã quan sát vẫn là một biến có kỳ vọng logarit.

### 9.4. Amortized khác cộng expected

Một mảng động tăng capacity theo hệ số có `push_back` **O(1) amortized** dù một lần reallocate mất O(n): đó là phân tích **phân bổ tổng công việc**, không cần RNG.

Treap và skip list có expected O(log n) trên random cấu trúc. Dù ta cộng kỳ vọng của nhiều thao tác, kết quả vẫn là **expected**, không phải bảo đảm amortized worst-case tất định.

## 10. Độ trễ, phân vị và deadline của hệ thống

Một hệ thống có throughput trung bình tốt vẫn có thể vi phạm yêu cầu độ trễ hiếm gặp.

### 10.1. Ví dụ trung bình thấp nhưng tail cao

Giả sử thời gian một request là:

- 1 ms với xác suất 99,5%.
- 200 ms với xác suất 0,5%.

Thời gian trung bình:

\[
E[T]=0{,}995\cdot1+0{,}005\cdot200
=1{,}995\text{ ms}.
\]

Nhưng phân vị 99,9% là 200 ms (trong khi phân vị 99% là 1 ms). Một lời hứa “trung bình dưới 2 ms” không đồng nghĩa “P99,9 dưới 2 ms”.

### 10.2. Worst-case số bước vẫn chưa đủ để cam kết thời gian thực

Ngay cả cây AVL/đỏ–đen bảo đảm O(log n) worst-case **số bước** vẫn chịu chi phí:

- So sánh khóa dài, cấp phát và garbage collection.
- Cache miss, page fault, I/O.
- Chờ mutex hoặc scheduling của hệ điều hành.
- Quota bộ nhớ, phân mảnh, lỗi allocation.
- Tải đồng thời và giao tiếp mạng.

Vì vậy cam kết deadline đòi kiểm soát **toàn bộ mô hình thực thi**, không chỉ Big-O.

### 10.3. Chọn cấu trúc theo loại bảo đảm cần thiết

| Yêu cầu | Cấu trúc/chiến lược phù hợp để xem xét | Chú ý |
| --- | --- | --- |
| Throughput trung bình, chấp nhận tail hiếm | Treap, skip list | Random model, seed, memory |
| Worst-case tra cứu/chèn/xóa O(log n) | AVL, red-black tree | Bất biến cân bằng tất định |
| Sort với worst-case O(n log n) | Heapsort, mergesort, hybrid có fallback đúng | Bộ nhớ, tính ổn định |
| Hash trong môi trường đối kháng | Bucket có chặn worst-case hoặc biện pháp phòng vệ rõ ràng | Seed, collision, resize |
| Dữ liệu theo dải khóa trên đĩa | B-tree/B+ tree | Fanout, I/O, layout |
| Hard deadline | Thuật toán và môi trường có chứng minh giới hạn bước/tài nguyên | Scheduling, locking, GC |

Chọn cấu trúc dựa trên **loại bảo đảm cần**, chứ không chỉ nhìn mức O(log n) được quảng bá.


## 11. Các chiến lược cải thiện worst-case — và những điều phải chứng minh

Một hệ thống có thể giữ ngẫu nhiên hóa để được hiệu năng trung bình tốt, đồng thời giảm rủi ro trường hợp xấu. Tuy nhiên, **không phải mọi biện pháp dự phòng đều tạo ra một chặn worst-case**.

### 11.1. Chọn cấu trúc có bất biến cân bằng cứng

Nếu mục tiêu là tra cứu, chèn và xóa khóa theo thứ tự với **O(log n) worst-case**, các cấu trúc như AVL và red-black tree là lựa chọn tiêu biểu.

- AVL duy trì giới hạn chênh lệch chiều cao giữa cây con.
- Red-black tree duy trì các bất biến màu và độ cao đen.
- Khi code đúng, những bất biến ấy giới hạn **chiều cao trong mọi trạng thái hợp lệ**, không cần lấy kỳ vọng qua RNG.

Đây là khác biệt cốt lõi với treap: BST+heap theo random priority **không tự chặn chiều cao** của cây hiện tại.

**Đánh đổi:** logic quay/rebalance, metadata và chi phí bảo trì code có thể khác. Không được kết luận cây tất định luôn nhanh hơn trên mọi workload; ưu điểm chính ở đây là **loại bảo đảm**.

### 11.2. Fallback sắp xếp: chiến lược kiểu introsort

Một chiến lược lai thường gọi là **introspective sorting** theo dõi độ sâu phân hoạch. Nó có thể:

1. Dùng quicksort/pivot để có hiệu năng thường tốt.
2. Giới hạn độ sâu phân chia ở bậc `c\log n`.
3. Khi nhánh chưa xong đạt ngưỡng, chuyển sang thuật toán sắp xếp có **worst-case O(m log m)** cho đoạn còn lại, ví dụ heapsort.

Phác thảo:

```text
SORT(segment, remaining_depth):
    if segment rất nhỏ:
        dùng insertion sort trên đoạn nhỏ (ngưỡng hằng số)
    else if remaining_depth == 0:
        dùng heapsort trên segment
    else:
        chọn pivot, partition
        SORT(left, remaining_depth - 1)
        SORT(right, remaining_depth - 1)
```

**Vì sao worst-case O(n log n)?**

Ở mỗi độ sâu phân hoạch, các đoạn đang xử lý **rời nhau** và tổng kích thước không vượt n. Nếu chỉ cho phép O(log n) tầng partition, tổng công việc chia ở các tầng đó là O(n log n).

Các đoạn còn lại đưa cho heapsort có tổng kích thước ≤n; chi phí:

\[
\sum_j O(m_j\log m_j)\le O(n\log n).
\]

Tổng worst-case là O(n log n) theo mô hình so sánh khóa chuẩn. **Fallback là lý do có giới hạn cứng; không phải random pivot tự có giới hạn ấy.**

### 11.3. Giới hạn độ cao treap: phát hiện không đồng nghĩa sửa được worst-case

Giả sử sau chèn, ta kiểm tra nếu chiều cao treap vượt `c\log n` thì **xây lại** từ các khóa đã sắp xếp.

Một cây mới cân bằng có thể giúp **các lượt tìm sau** ngắn. Nhưng chính lần chèn kích hoạt rebuild có thể phải tốn **O(n)** để xây lại. Do đó quy tắc “rebuild ngay khi quá cao” **không cho** worst-case O(log n) cho mọi lần chèn.

Còn nếu rút lại priority đến khi chiều cao đạt ngưỡng, cần chặn:

- Số lần thử lại.
- Chi phí mỗi lần xây/kiểm tra.
- Điều gì xảy ra khi hết budget.
- Chất lượng của phân phối sau khi **có điều kiện được chấp nhận**.

Không có giới hạn số lần rút thì worst-case thời gian vẫn có thể vô hạn theo các chuỗi lựa chọn random hợp lệ.

### 11.4. Cắt độ cao skip list không biến expected thành worst-case logarit

Đặt `MAX_LEVEL=L` giúp:

- Giới hạn tối đa chiều cao node.
- Chặn số bước xuống tầng bởi L.
- Chặn bộ nhớ slot forward mỗi node (nếu cấp theo chiều cao) bởi L.

Nhưng **chiều ngang** vẫn có thể dài: nếu mọi node H=1 thì tìm Θ(n). Và L cố định quá nhỏ với n tăng vô hạn còn làm expected search có thể tuyến tính.

Vậy câu “đặt MAX_LEVEL=32 là đã bảo đảm worst-case O(log n)” là **sai**. Chỉ có chặn tổng quát O(n+L) cho đường tìm của phiên bản tuần tự thông thường.

### 11.5. Rehash/resize không tự là fallback worst-case

Khi bảng băm có bucket quá dài, có thể chọn seed mới và rehash tất cả khóa. Cách này **có thể cải thiện hình dạng** nếu random mới phù hợp, nhưng:

- Một lần rehash tốn công đọc/ghi lại O(n) khóa.
- Rút seed mới có thể lại tạo va chạm bất lợi.
- Rehash lặp lại vô hạn không có chặn worst-case.
- Đối thủ biết seed hoặc quan sát va chạm có thể tiếp tục cố ý gây tải xấu.

Muốn công bố bảo đảm worst-case, cần một chiến lược cụ thể được phân tích, chẳng hạn **bucket được tổ chức bằng cấu trúc cân bằng** với điều kiện so sánh khóa rõ ràng, hoặc thuật toán bảng băm có bảo đảm chuyên biệt trong mô hình áp dụng.

### 11.6. Giới hạn bước và dừng sớm cũng thay đổi hợp đồng API

Một cách cưỡng chế deadline là **dừng thao tác sau B bước**. Nếu không xử lý tiếp, ta có thể nhận:

- `TIMEOUT` hoặc `RETRY` thay vì kết quả tìm chính xác.
- Một phép chèn chưa hoàn tất hoặc cần được rollback.
- Một tác vụ được lên lịch tiếp ở lượt sau.

Dừng sớm không tự giữ đồng thời **tính đúng luôn có câu trả lời** và **thời gian logarit worst-case**. Muốn bảo đảm cả hai, phải có phương án tiếp tục/fallback cùng **bất biến giao dịch** được chứng minh.

## 12. Python: nhìn thấy quicksort bị suy biến qua số phép so sánh

Mã dưới đây phục vụ minh họa, dùng Python 3.10+, chỉ thư viện chuẩn. Nó:

- Nhận một dãy số nguyên và một hàm chọn pivot.
- Chia ba nhóm **nhỏ hơn, bằng, lớn hơn** pivot.
- Đếm số lần so sánh với pivot được thực hiện trong code.
- Đo độ sâu lời gọi `sort`.
- Trả danh sách đã sắp xếp, không sửa đầu vào.

Ba nhóm giúp xử lý khóa trùng rõ ràng. Vì mỗi phần tử có thể được kiểm tra `<` rồi `>`, **số so sánh đo được không trùng công thức chính xác cho quicksort hai ngăn cổ điển**, nhưng vẫn phơi bày xu hướng bình phương khi chọn pivot xấu.

### 12.1. Bản mã tự chạy

```python
from __future__ import annotations

import random
from collections.abc import Callable


PivotPolicy = Callable[[list[int], random.Random], int]


def first_pivot(xs: list[int], rng: random.Random) -> int:
    return xs[0]


def random_pivot(xs: list[int], rng: random.Random) -> int:
    return xs[rng.randrange(len(xs))]


def quicksort_metrics(
    values: list[int],
    rng: random.Random,
    pivot_policy: PivotPolicy,
) -> tuple[list[int], int, int]:
    """(sorted_values, number_of_key_comparisons, max_call_depth)."""
    comparisons = 0
    max_depth = 0

    def sort(xs: list[int], depth: int) -> list[int]:
        nonlocal comparisons, max_depth
        max_depth = max(max_depth, depth)

        if len(xs) <= 1:
            return xs.copy()

        pivot = pivot_policy(xs, rng)
        smaller: list[int] = []
        equal: list[int] = []
        larger: list[int] = []

        for value in xs:
            comparisons += 1
            if value < pivot:
                smaller.append(value)
                continue

            comparisons += 1
            if value > pivot:
                larger.append(value)
            else:
                equal.append(value)

        return (
            sort(smaller, depth + 1)
            + equal
            + sort(larger, depth + 1)
        )

    ordered = sort(list(values), 1)
    return ordered, comparisons, max_depth


def demonstrate() -> None:
    for n in (16, 32, 64, 128, 256):
        # Đầu vào CỐ ĐỊNH, tăng dần.
        values = list(range(n))

        ordered_bad, comparisons_bad, depth_bad = quicksort_metrics(
            values, random.Random(1), first_pivot
        )
        assert ordered_bad == values

        random_counts = []
        random_depths = []

        for seed in range(30):
            ordered, comparisons, depth = quicksort_metrics(
                values, random.Random(seed), random_pivot
            )
            assert ordered == values
            random_counts.append(comparisons)
            random_depths.append(depth)

        print(
            "n:", n,
            "first-pivot comps:", comparisons_bad,
            "first-pivot depth:", depth_bad,
            "random mean comps:",
            sum(random_counts) / len(random_counts),
            "random max depth observed:", max(random_depths),
        )

    # Các khóa trùng vẫn được xử lý đúng.
    values = [3, 1, 3, 2, 3, 1, 4, 4]
    result, _, _ = quicksort_metrics(
        values, random.Random(2026), random_pivot
    )
    assert result == sorted(values)


if __name__ == "__main__":
    demonstrate()
```

### 12.2. Điều gì được dự đoán sẽ thấy?

Với dãy tăng và `first_pivot`:

- Pivot đầu tiên là khóa nhỏ nhất ở mỗi lần chia.
- `smaller` luôn rỗng, `larger` chứa gần toàn bộ phần tử còn lại.
- Độ sâu đạt Θ(n).
- Tổng phép so sánh là Θ(n²) với n khóa phân biệt.

Với `random_pivot`:

- Các lần rút tạo nhiều phân hoạch khác nhau.
- Trung bình số phép so sánh tăng theo bậc `n\log n` trong mô hình random đúng.
- Vẫn có thể gặp seed khiến một số đoạn chia rất lệch.

**Không chạy ví dụ này với n quá lớn ở chế độ pivot đầu tiên.** Nó dùng đệ quy Python và có thể gặp `RecursionError` trước khi bạn quan sát hết dữ liệu. Điều này cũng minh họa một chi phí cụ thể của thực thi: một thuật toán worst-case có độ sâu tuyến tính có thể vượt giới hạn call stack.

### 12.3. Vì sao bộ đo không tự chứng minh kỳ vọng?

Ba mươi seed chỉ là **30 mẫu**. Một trạng thái hiếm xác suất `1/n!` có thể không xuất hiện trong một thử nghiệm với số seed hữu hạn. Kết quả bình quân mẫu là chứng cứ thực nghiệm về xu hướng, không thay cho công thức xác suất hoặc chứng minh thuật toán.

Thêm nữa, mảng được tạo bằng list comprehension và nối list, nên thời gian CPU bao gồm cấp phát/copy; **đếm phép so sánh** giúp tách một phần chi phí thuật toán khỏi overhead Python.

## 13. Python: hybrid có giới hạn độ sâu và fallback

Để thấy rõ fallback thực sự thay loại bảo đảm, ta có thể dùng một ví dụ **quicksort chia ba nhóm, nhưng giới hạn độ sâu** rồi chuyển đoạn còn lại sang `sorted` của Python.

Đây là **mô phỏng hybrid cho mục đích học**, không phải implementation introsort in-place được tối ưu. Trong môi trường yêu cầu thuật toán có chặn worst-case một cách độc lập với thư viện, có thể thay `sorted` bằng heapsort/mergesort có chứng minh riêng.

### 13.1. Bản mã

```python
import random


def guarded_quicksort(values: list[int], seed: int = 2026) -> list[int]:
    rng = random.Random(seed)

    # Giới hạn số cấp partition dọc mỗi nhánh.
    depth_limit = 2 * max(0, len(values).bit_length() - 1)

    def sort(xs: list[int], budget: int) -> list[int]:
        if len(xs) <= 1:
            return xs.copy()

        if budget == 0:
            # Built-in sorted có worst-case O(m log m)
            # trong mô hình so sánh khóa nhất quán.
            return sorted(xs)

        pivot = xs[rng.randrange(len(xs))]

        left: list[int] = []
        equal: list[int] = []
        right: list[int] = []

        for value in xs:
            if value < pivot:
                left.append(value)
            elif value > pivot:
                right.append(value)
            else:
                equal.append(value)

        return (
            sort(left, budget - 1)
            + equal
            + sort(right, budget - 1)
        )

    return sort(list(values), depth_limit)


if __name__ == "__main__":
    for n in (0, 1, 2, 32, 128, 256):
        values = list(range(n))
        assert guarded_quicksort(values) == values
        assert guarded_quicksort(list(reversed(values))) == values

    duplicates = [5, 1, 5, 3, 5, 2, 3, 3]
    assert guarded_quicksort(duplicates) == sorted(duplicates)
```

### 13.2. Vì sao worst-case so sánh là O(n log n)?

- Độ sâu partition tối đa O(log n).
- Tại một độ sâu, các nhóm chưa sắp xếp **rời nhau**; tổng số phần tử được partition không quá n, nên tổng chi phí O(n) mỗi tầng.
- Qua O(log n) tầng, phần partition tối đa O(n log n).
- Các đoạn còn lại đưa cho `sorted` có tổng kích thước ≤n, mỗi đoạn độ dài m có worst-case O(m log m); tổng các fallback là O(n log n).

Do đó, với comparator nhất quán và theo mô hình so sánh chuẩn, toàn bộ hybrid có **worst-case O(n log n)** thời gian. Việc chọn pivot ngẫu nhiên là phương tiện cho hiệu năng thông thường; **giới hạn độ sâu + fallback** mới tạo bảo đảm worst-case.

### 13.3. Điều hybrid này chưa hứa hẹn

- Không phải thuật toán in-place: bản dùng list phụ và nối các list.
- Không hứa hẹn O(1) bộ nhớ phụ; lượng cấp phát phụ thuộc quá trình chia.
- Không tự bảo đảm deadline theo mili-giây, vì còn runtime, allocator và scheduling.
- Không có ý nghĩa bảo mật chỉ vì seed được chọn.
- Không phải sửa chữa treap/skip list; đây là **một ví dụ riêng của bài toán sort** để hiểu chiến lược fallback.

**Bài học:** muốn đổi **loại bảo đảm**, phải đổi thuật toán và có **lập luận cho toàn bộ đường chạy**, không chỉ thêm lệnh kiểm tra “đã chậm chưa?”.


## 14. Python: dựng một skip list xấu nhưng hoàn toàn đúng

Một skip list chỉ có tầng đáy vẫn là **skip list hợp lệ theo bất biến liên kết**. Ta có thể dựng trường hợp đó không cần ngẫu nhiên và đếm số bước tìm. Mã dưới đây chỉ dùng **mô hình chỉ số** để vẽ đường liên kết; đây không phải implementation sản phẩm của skip list, mà là bộ đo nhỏ cho việc học worst-case.

### 14.1. Tạo con trỏ forward từ chiều cao đã cho

```python
from __future__ import annotations


def search_path(
    keys: list[int],
    heights: list[int],
    target: int,
) -> tuple[bool, int, int]:
    """(found, horizontal_moves, visited_levels).

    HEAD được biểu diễn bằng chỉ số -1.
    Danh sách keys phải sorted và không có khóa trùng.
    """
    if len(keys) != len(heights):
        raise ValueError("Một chiều cao cho mỗi khóa")
    if keys != sorted(set(keys)):
        raise ValueError("Keys phải tăng chặt")
    if any(h < 1 for h in heights):
        raise ValueError("Chiều cao phải >=1")

    levels = max(heights, default=1)
    forward: list[dict[int, int | None]] = []

    # Tạo cạnh next riêng cho từng tầng.
    for level in range(levels):
        present = [
            idx for idx, height in enumerate(heights)
            if height > level
        ]
        nxt: dict[int, int | None] = {
            -1: present[0] if present else None
        }

        for pos, idx in enumerate(present):
            nxt[idx] = (
                present[pos + 1]
                if pos + 1 < len(present)
                else None
            )

        forward.append(nxt)

    current = -1  # HEAD
    horizontal_moves = 0

    for level in range(levels - 1, -1, -1):
        next_idx = forward[level].get(current)

        while next_idx is not None and keys[next_idx] < target:
            current = next_idx
            horizontal_moves += 1
            next_idx = forward[level].get(current)

    candidate = forward[0].get(current)
    found = candidate is not None and keys[candidate] == target
    return found, horizontal_moves, levels


if __name__ == "__main__":
    keys = list(range(20))

    # Một dãy chiều cao bất lợi: chỉ L0.
    all_low = [1] * len(keys)
    found, moves, levels = search_path(keys, all_low, 20)
    assert not found
    assert moves == 20 and levels == 1

    # Một cách tổ chức có các mốc cao để đi tắt.
    mixed = [
        1, 2, 1, 3, 1,
        2, 1, 4, 1, 2,
        1, 3, 1, 2, 1,
        4, 1, 2, 1, 3,
    ]
    found2, moves2, levels2 = search_path(keys, mixed, 20)
    assert not found2
    assert levels2 == 4
    assert moves2 < moves

    # Bất kể các chiều cao, cùng một set có cùng kết quả.
    for target in (-1, 0, 7, 19, 20, 100):
        expected = target in set(keys)
        assert search_path(keys, all_low, target)[0] == expected
        assert search_path(keys, mixed, target)[0] == expected
```

### 14.2. Những điều bộ đo cho thấy

- Nếu mọi node cao 1, tìm khóa lớn hơn max phải đi qua **n bước ngang**.
- Nếu có mốc ở các tầng cao, số bước có thể nhỏ hơn đáng kể.
- Cả hai cấu trúc có **cùng keys** và đều đúng về kết quả tìm.
- Việc cải thiện hình dạng phụ thuộc **mức được chọn**, không chỉ đầu vào sorted hay unsorted.

**Giới hạn của ví dụ:** bộ dựng mô hình cấp nhiều cấu trúc `dict` và lọc node qua từng tầng, nên chi phí **xây đồ thị test** không đại diện cho bộ nhớ/chi phí production. Hàm chỉ dùng để **đếm đường tìm trên một trạng thái đã chỉ định**.

### 14.3. Biến một kiểm thử thành phản ví dụ worst-case

Để bác bỏ phát biểu “mọi skip list tìm O(log n)”, chỉ cần một họ đầu vào và hình dạng hợp lệ với chi phí tuyến tính:

```text
Với mỗi n:
    keys = [0, 1, ..., n-1]
    heights = [1, 1, ..., 1]
    target = n

Số bước ngang = n.
```

Dù với p=1/2 sự kiện mọi H=1 có xác suất `2^{-n}`, nó **không phải sự kiện bất khả thi** trong mô hình random. Do đó bất biến skip list không thể ngăn worst-case tuyến tính chỉ bằng việc bốc mức.

## 15. Thiết kế giới hạn rủi ro trong môi trường thực tế

Một ứng dụng production cần xem **randomization, an toàn tài nguyên và quan sát vận hành** như các trách nhiệm riêng.

### 15.1. Phát biểu một cam kết kỹ thuật có thể kiểm thử

Thay vì:

> “Skip list luôn tìm trong 1 ms vì O(log n).”

hãy ghi rõ theo cấu trúc:

- **Hợp đồng ngữ nghĩa:** tìm trả đúng thành viên trong tập khi thao tác hoàn thành; không mất khóa qua insert/remove.
- **Giả định dữ liệu:** n tối đa, loại khóa, chi phí comparator, tỉ lệ chèn/xóa.
- **Random model:** xác suất nâng p, các lần rút độc lập theo mô hình nào, seed được quản lý thế nào.
- **Giới hạn tài nguyên:** `MAX_LEVEL`, node bytes, số bucket/khóa, behavior khi allocation fail.
- **Loại bảo đảm:** expected O(log n), hay worst-case O(n+L), hay high-probability với chứng minh tail riêng.
- **SLO vận hành:** phân vị P99/P99,9 hoặc tỷ lệ lỗi/timeout được phép, **không suy ra trực tiếp từ Big-O**.

Đây là một hợp đồng có thể đánh giá; số 1 ms nếu chưa có phép đo/giới hạn hệ thống là một dự đoán không có căn cứ.

### 15.2. Có thể dùng công tắc chuyển sang cấu trúc tất định

Một hệ thống có thể giữ một chỉ mục cân bằng tất định làm **đường dự phòng**, hoặc chọn cây đỏ–đen ngay khi workload có deadline cứng. Nhưng phải phân tích:

- Khi nào chuyển?
- Dữ liệu đã tồn tại được di chuyển trong bao nhiêu bước?
- Có cấp thêm O(n) bộ nhớ tạm không?
- Trong lúc chuyển, read/write có nhất quán không?
- Một thao tác khởi động chuyển đổi có phải chịu toàn bộ chi phí O(n) không?
- Khi đồng thời nhiều luồng, ai sở hữu node và iterator cũ?

Ví dụ chỉ nói “treap cao quá thì rebuild thành AVL” **chưa chứng minh worst-case O(log n) per insert**. Để bảo đảm từng bước, có thể cần incremental migration với giới hạn công việc mỗi request và một thiết kế hỗ trợ truy vấn qua hai trạng thái; đó là thuật toán phức tạp cần chứng minh riêng.

### 15.3. Timeout có thể hợp lý nếu API công bố được phép thất bại

Đối với truy vấn tìm kiếm không phải lúc nào cũng buộc trả kết quả ngay, một API có thể trả:

```text
FOUND(value)
NOT_FOUND
RETRY_LATER
TIME_BUDGET_EXCEEDED
```

Khi đã vượt ngân sách bước, việc trả trạng thái timeout giúp chặn **thời gian của nỗ lực hiện tại**. Nhưng không được quảng bá nó là “tìm chính xác O(log n) worst-case”, vì có thể **không trả được kết quả chính xác** trong lần gọi ấy.

Đối với **chèn/xóa**, cần giữ **atomicity hoặc rollback** theo hợp đồng: không để trạng thái một node được nối ở một số tầng nhưng không có cơ chế hoàn tất/khôi phục trong khi trả timeout.

### 15.4. Đừng nhầm seed cố định và randomness chống đối kháng

Một seed cố định hữu ích để tái tạo lỗi trong test. Nhưng khi seed được biết hoặc dự đoán được, tác nhân bên ngoài có thể đoán hình dạng hoặc chọn input theo lựa chọn random.

Nếu yêu cầu bảo mật chống tấn công độ phức tạp:

- Không dùng `random.Random(seed)` như nguồn random bảo mật mặc định.
- Đánh giá những kênh có thể lộ hình dạng hoặc hash state.
- Dùng nguồn random phù hợp threat model khi cần, nhưng **không** mặc nhiên kết luận CSPRNG bảo đảm worst-case; nó vẫn cho những chuỗi xấu với xác suất dương.
- Giới hạn tài nguyên và chọn thuật toán có bảo đảm phù hợp cho hậu quả khi worst-case xảy ra.

CSPRNG cải thiện **khả năng dự đoán của đối thủ** theo mục tiêu bảo mật; nó không biến một định lý expected thành chặn tất định cho mọi chuỗi random.

### 15.5. Không loại bỏ “các mẫu chậm” khỏi benchmark

Khi benchmark randomized structure:

1. Cố định tập khóa, n và tỷ lệ thao tác; chạy nhiều seed.
2. Ghi cả **trung bình, median, phân vị cao và max quan sát**.
3. Phân biệt max quan sát trong mẫu với worst-case toán học.
4. Thu số bước trừu tượng song song với thời gian CPU.
5. Ghi giới hạn L, chi phí metadata, cache, allocator và chính sách GC.
6. Có test bất biến sau các chuỗi chèn/xóa; **không benchmark một cấu trúc bị mất liên kết**.
7. Giữ riêng chi phí dựng cấu trúc so với chi phí phục vụ truy vấn nếu đang đo steady-state.
8. Test cả dữ liệu sorted, reversed, duplicate và dữ liệu đối kháng phù hợp quyền hạn test.

Không được bỏ qua seed chậm bằng cách gọi chúng là “outlier không hợp lệ” khi chính thuật toán cho phép kết quả ấy.

## 16. Bảng lỗi lập luận thường gặp

| Phát biểu nhầm | Điểm sai | Cách sửa |
| --- | --- | --- |
| “Expected O(log n) nghĩa là mọi thao tác O(log n)” | Thay kỳ vọng bằng worst-case | Nêu worst-case độc lập |
| “Xác suất xấu rất nhỏ nên không tồn tại worst-case” | Xác suất dương vẫn là khả năng hợp lệ | Worst-case xét mọi trường hợp khả dĩ |
| “BST thường trên input random giống treap random cho mọi input” | Average-input khác randomness nội bộ | Cố định input, lấy kỳ vọng qua RNG |
| “Treap heap đúng nên chiều cao logarit cứng” | BST+heap không chặn chiều cao | Có thể tạo cây đường thẳng |
| “Chiều cao từng node treap kỳ vọng log ⇒ chiều cao lớn nhất cũng vậy” | `E[\max]` không bằng `\max E` nói chung | Cần phân tích maximum/tail |
| “Một node skip list có kỳ vọng H=2 ⇒ không node nào cao 100” | Kỳ vọng không chặn tối đa | Dùng `Pr(H≥k)` hoặc MAX_LEVEL |
| “Mọi node H=1 thì skip list sai” | Bất biến vẫn đúng | Phân biệt correctness/performance |
| “Cắt MAX_LEVEL nhỏ ⇒ worst-case logarit” | Tầng đỉnh có thể rất đông | Worst-case O(n+L), chọn L theo n |
| “Không đặt trần vẫn có worst-case theo n” | Số lần bốc mức có thể tùy ý lớn | Gắn thêm H hoặc đặt giới hạn |
| “Random pivot không bao giờ gây Θ(n²)” | Một chuỗi pivot cực trị vẫn có xác suất dương | Expected O(n log n), worst Θ(n²) |
| “Rehash khi chậm ⇒ mọi insert O(1) worst-case” | Một lần rehash có thể O(n) | Phân tích cả fallback và lịch sử |
| “Chiều cao treap quá lớn thì rebuild ngay ⇒ insert O(log n)” | Rebuild có thể O(n) | Tách post-state và chi phí thao tác |
| “Một thao tác có chặn Markov 1% ⇒ m thao tác cùng chậm với xác suất 0,01^m” | Thiếu độc lập | Dùng union bound hoặc mô hình phụ thuộc |
| “P99 thấp nghĩa là không bao giờ trễ” | Phân vị không phải hard bound | Công bố xác suất/trần cụ thể |
| “Markov bảo đảm xác suất ≤1/n³ ở ngưỡng Clog n” | Markov chỉ cho E[T]/a | Chứng minh tail mạnh riêng |
| “CSPRNG làm mọi cấu trúc có worst-case tốt” | Random bảo mật vẫn có chuỗi xấu | Tách độ bí mật khỏi chặn thuật toán |
| “Cấp L pointer/node vẫn là khoảng 2n slot” | Nhầm slot dùng và slot cấp | Fixed-size node dùng nL slot |
| “Benchmark 100 seed không thấy n² ⇒ không có worst-case” | Hiếm không bằng không thể | Tạo trường hợp xấu hoặc chứng minh |
| “O(log n) số bước tự bảo đảm 1 ms” | Không tính runtime/I/O/lock/GC | Phân tích deadline toàn hệ thống |
| “Timeout sau B bước là tìm chính xác worst-case B” | Có thể trả timeout thay vì kết quả | Thay hợp đồng API hoặc fallback đúng |

**Quy trình rà một tuyên bố hiệu năng:** xác định đại lượng đo, lượng từ trên input, nguồn random, loại bảo đảm, ngưỡng rủi ro, khả năng thay đổi trạng thái, và toàn bộ chi phí fallback. Chỉ khi cả bảy rõ ràng mới nên đưa số liệu vào đặc tả kỹ thuật.


## 17. Bài tập thực hành có lời giải

### Bài 1. Expected có phải worst-case không?

Một hàm tìm có `E[T(n)]=O(\log n)`. Có được kết luận `T(n)=O(\log n)` cho mọi lần chạy không?

**Lời giải:** Không. Kỳ vọng lấy trung bình theo phân phối lựa chọn ngẫu nhiên. Một số kết quả random có thể cho chi phí Θ(n) hoặc lớn hơn, miễn đủ hiếm. Cần chứng minh riêng chặn **worst-case trên mọi lần rút**.

### Bài 2. Viết đúng định nghĩa có lượng từ

Viết biểu thức cho worst-case và expected worst-input của thuật toán ngẫu nhiên `T(x,R)`.

**Lời giải:** Có thể dùng:

\[
W(n)=\sup_{|x|=n}\sup_R T(x,R),\quad
E_{\max}(n)=\sup_{|x|=n}E_R[T(x,R)].
\]

Hai biểu thức lấy supremum và kỳ vọng **theo thứ tự khác nhau**; chúng không có cùng ngữ nghĩa.

### Bài 3. Một kỳ vọng hằng số nhưng worst-case tuyến tính

Biến `T_n` bằng 1 với xác suất `1-1/n` và bằng n với xác suất `1/n`. Tính kỳ vọng và worst-case.

**Lời giải:**

\[
E[T_n]=(1-1/n)\cdot1+(1/n)\cdot n
=2-1/n=O(1).
\]

Worst-case là `n=Θ(n)`. Hai kết quả cùng đúng.

### Bài 4. Vì sao `sup E≤E sup`?

Giả sử có hai đầu vào a,b và hai trạng thái random r0,r1 đồng xác suất. Chi phí:

| | r0 | r1 |
| --- | ---: | ---: |
| a | 100 | 1 |
| b | 1 | 100 |

So `\sup_xE[T(x,R)]` với `E[\sup_xT(x,R)]`.

**Lời giải:** Với đầu vào a hoặc b cố định, kỳ vọng đều là `(100+1)/2=50{,}5`. Vậy `\sup_xE[T]=50{,}5`. Nếu được quan sát random trước khi chọn đầu vào, ở cả r0 và r1 có một đầu vào tốn 100, nên `E[\sup_xT]=100`. Đổi thứ tự lựa chọn làm mô hình đối thủ mạnh hơn.

### Bài 5. Input ngẫu nhiên khác random nội bộ

Một BST thường cân bằng tương đối tốt khi nhận khóa theo thứ tự chèn ngẫu nhiên. Với dãy tăng `1,2,\ldots,n`, kết luận “tìm O(log n) expected” còn tự đúng không?

**Lời giải:** Không. BST thường không bốc random nội bộ hoặc tự cân bằng; chèn tăng dần có thể tạo cây lệch phải, tìm worst Θ(n). Chặn trung bình trên **phân phối input** không áp dụng cho input cố định khác phân phối ấy.

### Bài 6. Treap lệch vẫn hợp lệ

Một treap min-priority có key `1,2,3,4` với priority cũng tăng `1,2,3,4`. Chiều cao và tìm xấu nhất?

**Lời giải:** Cây là đường lệch phải, cao 3 cạnh, tìm khóa cuối tốn Θ(n). Nó vẫn thỏa BST theo key và min-heap theo priority. Do vậy tính đúng của treap **không bắt buộc** chiều cao logarit.

### Bài 7. Xác suất priority tăng hoàn toàn

Với n=5 priority IID liên tục, xác suất các priority theo key tăng hoàn toàn là bao nhiêu?

**Lời giải:** Mỗi trong `5!=120` thứ tự tương đối có xác suất như nhau, nên xác suất **một thứ tự tăng cụ thể** là `1/120`. Không được nói `1/120` là xác suất của **mọi** hình dạng xấu.

### Bài 8. Độ sâu kỳ vọng và chiều cao kỳ vọng của treap

Nếu mọi khóa cố định có độ sâu kỳ vọng O(log n), có được tự viết `E[\max_iD_i]=\max_iE[D_i]` không?

**Lời giải:** Không. Đẳng thức ấy **sai nói chung**; cực đại và kỳ vọng không giao hoán. Chặn chiều cao cần phân tích xác suất về **nút sâu nhất**. Kết quả chuẩn của treap random IID là expected height O(log n), nhưng không được lấy nó từ đẳng thức sai.

### Bài 9. Skip list mọi node chỉ cao 1

Với n node, p=1/2 độc lập, xác suất tất cả node có H=1 là bao nhiêu? Với n=12?

**Lời giải:** `Pr(H=1)=1/2`, nên:

\[
\Pr(\text{tất cả H=1})=(1/2)^n.
\]

Với n=12: `1/4096`. Khi sự kiện ấy xảy ra, skip list vẫn là một danh sách sorted hợp lệ.

### Bài 10. Tìm trên skip list không có đường nhảy

Có n khóa tăng dần và mọi node H=1. Tìm khóa lớn hơn mọi khóa tốn bao nhiêu bước ngang?

**Lời giải:** Tốn **n bước ngang** trên L0, tức Θ(n). Đây là một phản ví dụ đủ để bác bỏ worst-case O(log n) cho skip list random thông thường.

### Bài 11. Vòng bốc chiều cao không giới hạn

Một node skip list cứ được nâng nếu đồng xu tiếp tục ngửa, không có MAX_LEVEL. Với n=1, có chặn cứng số lần tung chỉ theo n không?

**Lời giải:** Không. Có xác suất dương tung thành công k lần với mọi k hữu hạn. Kỳ vọng số tầng `1/(1-p)` hữu hạn, nhưng supremum trên mọi chuỗi random không có chặn hữu hạn chỉ theo n.

### Bài 12. Trần L=8 có bảo đảm tìm worst-case logarit không?

Một skip list có `MAX_LEVEL=8` cho mọi n. Có thể tuyên bố mỗi truy vấn worst O(log n) không?

**Lời giải:** Không. Tất cả node vẫn có thể chỉ nằm ở L0. Với n node, một lượt tìm có worst O(n+8)=O(n), không phải O(log n).

### Bài 13. Số node kỳ vọng ở tầng đỉnh

Với n=1024, p=1/2 và L=8, số node kỳ vọng ở tầng cao nhất là bao nhiêu?

**Lời giải:** Tầng cao nhất có chỉ số 7:

\[
E[N_7]=1024(1/2)^7=8.
\]

Đây là số node **kỳ vọng**, không phải chắc chắn có đúng 8.

### Bài 14. Chọn L để tầng đỉnh có kỳ vọng 1 node

Với n=1024, p=1/2, chọn L theo `1+\log_2n`. L bằng bao nhiêu?

**Lời giải:** `\log_2(1024)=10`, nên `L=11`. Tầng đỉnh i=10 có `E[N_{10}]=1024/1024=1`. Cấu hình này không tạo worst-case logarit cứng.

### Bài 15. Vì sao L cố định bị mất expected logarit khi n→∞?

Giữ p=1/2 và L=10. Số node tầng đỉnh theo n là gì?

**Lời giải:**

\[
E[N_9]=n/512=\Theta(n).
\]

Một truy vấn lớn hơn mọi khóa quét qua toàn bộ tầng đỉnh, nên riêng phần này có kỳ vọng Θ(n). Không thể giữ expected O(log n) cho mọi n với L cố định.

### Bài 16. Randomized quicksort vẫn có trường hợp bình phương

Quicksort có pivot ngẫu nhiên đều trên khóa phân biệt. Nếu mỗi lần pivot là khóa nhỏ nhất, độ sâu phân hoạch và số so sánh worst là gì?

**Lời giải:** Phân hoạch liên tiếp có kích thước n−1, n−2, ..., 1; độ sâu Θ(n) và số so sánh:

\[
(n-1)+(n-2)+\cdots+1=n(n-1)/2=\Theta(n^2).
\]

Tính random chỉ làm trường hợp ấy hiếm hơn, không loại bỏ nó.

### Bài 17. Xác suất mọi pivot đều là cực trị

Với n=5 khóa phân biệt và pivot ngẫu nhiên đều, xác suất pivot luôn là một trong hai cực trị của đoạn chưa sắp là bao nhiêu?

**Lời giải:**

\[
\prod_{m=2}^{5}\frac2m
=\frac{2^4}{5!}=\frac{16}{120}=\frac2{15}.
\]

Đây là xác suất của chuỗi phân hoạch **hoàn toàn một phía ở mọi bước** trong mô hình chuẩn.

### Bài 18. Quicksort pivot đầu trên mảng sorted

Với n=5, pivot luôn là phần tử đầu của đoạn, đầu vào đã tăng dần. Tổng so sánh kiểu classic là bao nhiêu?

**Lời giải:** `4+3+2+1=10`. Tổng quát `n(n-1)/2=Θ(n²)`. Một lựa chọn pivot tất định theo vị trí không có khả năng tự phá trường hợp input tăng dần này.

### Bài 19. Công thức kỳ vọng so sánh quicksort

Trong quicksort chuẩn trên n khóa phân biệt với pivot ngẫu nhiên đều, dùng công thức nào?

**Lời giải:**

\[
E[C_n]=2(n+1)H_n-4n=\Theta(n\log n),
\]

với `H_n=\sum_{k=1}^n1/k`. Đây là **kỳ vọng so sánh** của mô hình chuẩn, không phải khẳng định worst-case.

### Bài 20. Markov cho ngưỡng chậm

Biết chi phí T≥0 có `E[T]≤20`. Chặn trên `Pr(T≥200)` bằng Markov là gì?

**Lời giải:**

\[
\Pr(T\ge200)\le20/200=0{,}1.
\]

Đây là chặn **10%**, có thể lỏng. Nó không nói xác suất thật đúng bằng 10%.

### Bài 21. Markov có đủ chứng minh `1/n^3` không?

Biết `E[T]\le C\log n`, có thể dùng Markov ở ngưỡng `10C\log n` để kết luận xác suất vượt ngưỡng ≤`1/n^3` không?

**Lời giải:** Không. Markov cho chặn `1/10` ở ngưỡng này. Cần chứng minh thêm tail riêng để nhận `1/n^3`.

### Bài 22. Union bound cho nhiều request

Có 100 request, mỗi request có xác suất trễ ≤0,001. Chặn xác suất có ít nhất một request trễ là gì? Có cần độc lập không?

**Lời giải:** Union bound cho `100\times0{,}001=0{,}1`, tức ≤10%. **Không cần** độc lập giữa các sự kiện trễ.

### Bài 23. Nếu các request độc lập thì sao?

Với 100 sự kiện trễ **độc lập** có xác suất trễ đúng 0,001 mỗi sự kiện, xác suất có ít nhất một là bao nhiêu?

**Lời giải:**

\[
1-(1-0{,}001)^{100}
=1-0{,}999^{100}\approx0{,}0952.
\]

Nó nhỏ hơn chặn union 0,1. Nhưng nếu các request dùng chung một hình dạng skip list, giả định độc lập có thể sai.

### Bài 24. Xác suất chiều cao skip list quá lớn

Có n=1024, p=1/2. Dùng union bound chặn `Pr(M≥21)`.

**Lời giải:**

\[
\Pr(M\ge21)\le1024\cdot2^{-20}
=1/1024.
\]

Đây là chặn về **maximum height**, không trực tiếp về số bước tìm.

### Bài 25. Chọn k để đạt xác suất `n^{-2}`

Cho n=1024, p=1/2, muốn `Pr(M≥k)≤n^{-2}` theo union bound. Chọn k theo công thức tổng quát.

**Lời giải:** Với c=2:

\[
k=1+\lceil3\log_2n\rceil
=1+3\cdot10=31.
\]

Khi ấy `np^{k-1}≤n^{-2}`. Đây là ngưỡng đủ theo union bound, không nhất thiết tối ưu.

### Bài 26. Có thể suy tail đường tìm từ tail chiều cao không?

Nếu biết skip list có `Pr(M>c\log n)≤n^{-3}`, có được tự kết luận `Pr(T_{\rm search}>c'\log n)≤n^{-3}` không?

**Lời giải:** Không. Một cấu trúc rất thấp vẫn có thể có đường ngang n. Muốn chặn số bước tìm, cần lập luận bổ sung về **khoảng cách giữa các mốc ở từng tầng**, không chỉ cực đại M.

### Bài 27. Tổng pointer kỳ vọng của skip list

Với p=1/2, mỗi node cấp đúng H forward slot, n node có kỳ vọng tổng slot bao nhiêu?

**Lời giải:** `E[H]=1/(1-p)=2`, nên `E[S]=2n`. Không phải O(n log n), vì đa số node rất thấp. Nếu mỗi node cấp L slot cố định, số slot **đã cấp** lại là nL.

### Bài 28. Markov với bộ nhớ pointer

Biết `E[S]=2n`. Dùng Markov chặn xác suất `S≥10n`.

**Lời giải:** `Pr(S≥10n)≤E[S]/(10n)=2n/(10n)=1/5`. Chặn 20% có thể rất lỏng; muốn tốt hơn có thể dùng phương sai và các bất đẳng thức tập trung.

### Bài 29. Universal hashing có loại bỏ va chạm không?

Một họ hash thỏa `Pr(h(x)=h(y))≤1/m` với hai khóa phân biệt. Có thể nói mọi hàm băm rút ra đều không va chạm không?

**Lời giải:** Không. Đó là giới hạn **xác suất qua phép chọn h**, không phải ràng buộc cho mọi h. Vẫn có thể xảy ra va chạm theo các hàm trong họ phù hợp với định nghĩa.

### Bài 30. Union bound va chạm có thể vô dụng

Với n=100 khóa và m=1000 bucket, union bound cho “có một cặp va chạm” theo universal hashing là bao nhiêu?

**Lời giải:**

\[
{100\choose2}\frac1{1000}
=\frac{4950}{1000}=4{,}95.
\]

Vì xác suất ≤1, chặn thực tế trở thành **min(1,4,95)=1**, tức không cung cấp thông tin hữu ích. Một chặn lớn hơn 1 không có nghĩa xác suất lớn hơn 100%.

### Bài 31. Truy vấn trên cùng một treap có độc lập không?

Một treap được xây từ một tập priority. Có 100 lượt tìm cùng một khóa khó. Có thể nhân xác suất 100 lần tìm cùng chậm như `q^{100}` không?

**Lời giải:** Không nếu chúng dùng **cùng cây đã xây**. Một cây xấu có thể khiến cả 100 lượt cùng chậm. Không có 100 lần rút hình dạng độc lập mới, nên không đủ điều kiện nhân xác suất.

### Bài 32. Đối thủ chọn khóa theo hình dạng đã thấy

Một đối thủ biết các nút nào của skip list cao, rồi xóa các nút cao để giữ lại hầu hết node H=1. Các công thức IID về số node tầng i có tự còn đúng không?

**Lời giải:** Không. Việc chọn giữ/xóa **phụ thuộc vào random đã xảy ra**, làm phân phối các node còn sống bị thiên lệch. Cần phân tích theo mô hình đối thủ này, không tái sử dụng công thức cho tập khóa cố định độc lập với random.

### Bài 33. Seed cố định là bảo đảm gì?

Hai lần chạy cùng thuật toán PRNG và seed, có cùng thứ tự gọi RNG. Kết quả thường có lợi ích gì? Có an toàn trước đối thủ không?

**Lời giải:** Chúng có thể tái tạo cùng chuỗi lựa chọn, rất hữu ích để debug/test. Nhưng tính tái lập **không** tự có tính bảo mật và không tạo worst-case bound; một seed công khai có thể giúp đối thủ đoán trạng thái trong một mô hình cụ thể.

### Bài 34. Rebuild treap khi cao quá

Giả sử sau một lần insert, treap cao hơn ngưỡng và chương trình rebuild toàn bộ n node thành cây cân bằng. Có thể nói lần insert này worst-case O(log n) không?

**Lời giải:** Không. Chính lần insert kích hoạt rebuild có thể tốn O(n), chưa kể cấp phát và xử lý iterator. Trạng thái **sau rebuild** có thể cân bằng nhưng **thời gian thao tác kích hoạt** chưa được chặn logarit.

### Bài 35. Timeout là bảo đảm gì?

Một API tìm dừng sau B bước và trả `TIMEOUT` nếu chưa xác định thành viên. Có thể gọi đây là tìm thành viên chính xác trong O(B) worst-case không?

**Lời giải:** Không theo hợp đồng trả **FOUND/NOT_FOUND bắt buộc**. Nó là API có **ngân sách bước** và được phép trả trạng thái thứ ba. Muốn bảo đảm trả kết quả chính xác, cần xử lý tiếp/fallback với chứng minh chi phí và bất biến.

### Bài 36. Vì sao hybrid sort có thể có worst-case O(n log n)?

Giải thích vai trò của ngưỡng độ sâu và fallback heapsort.

**Lời giải:** Nếu chỉ cho partition O(log n) tầng, mỗi tầng xử lý tổng O(n) phần tử, nên partition tối đa O(n log n). Các đoạn rời còn lại đưa vào heapsort, tổng O(n log n) vì `\sum m_i\log m_i≤n\log n`. Đây là chặn cho **toàn thuật toán**, không phụ thuộc việc pivot có bị xấu.

### Bài 37. Dừng và chạy lại với seed mới có worst-case hữu hạn không?

Một thuật toán luôn rút lại seed cho tới khi chiều cao cấu trúc dưới ngưỡng, không giới hạn số lần thử. Có thể khẳng định worst-case thời gian hữu hạn theo n không?

**Lời giải:** Không. Dù xác suất mỗi lần thành công lớn, vẫn có các chuỗi thử thất bại tùy ý dài. Muốn worst-case hữu hạn cần giới hạn thử và xử lý **đường fallback sau khi hết ngân sách**.

### Bài 38. Expected khác amortized

Một dynamic array có `append` worst O(n) vì realloc nhưng amortized O(1). Có phải kết quả ấy đến từ RNG như skip list không?

**Lời giải:** Không. Amortized phân bổ tổng chi phí giữa các thao tác trong một chuỗi; không bắt buộc có ngẫu nhiên. Skip list có expected O(log n) vì phân tích trên random levels của cấu trúc.

### Bài 39. Chọn cấu trúc cho deadline cứng

Một dịch vụ cần exact-key search có thứ tự và yêu cầu **worst-case O(log n) số phép so sánh** cho mỗi lần truy vấn. Nên ưu tiên điều gì?

**Lời giải:** Một cấu trúc cân bằng tất định như AVL/red-black tree, với comparator/implementation phù hợp, hoặc giải pháp khác có worst-case đã chứng minh. Treap và skip list random chỉ có expected O(log n) theo mô hình chuẩn nên chưa đủ cho yêu cầu này.

### Bài 40. Trình bày một báo cáo benchmark đúng

Một nhóm đo treap với 20 seed, không lần nào có độ sâu quá 30, rồi tuyên bố “treap worst-case depth ≤30”. Lập luận sai ở đâu?

**Lời giải:** Max quan sát trong **một mẫu 20 seed** không phải supremum trên mọi kết quả random và n. Cần phân biệt **max observed**, trung bình/phân vị qua mẫu và **worst-case toán học**. Để bác bỏ giới hạn ≤30, có thể dựng treap hợp lệ dạng đường với n lớn hơn 31.

## 18. Tổng kết: đọc đúng một bảo đảm kỳ vọng

Những kết quả quan trọng nhất:

| Đối tượng | Bảo đảm thường được dùng | Trường hợp xấu vẫn có thể xảy ra |
| --- | --- | --- |
| Treap với priority IID phù hợp | Find/insert/delete và height **O(log n) kỳ vọng** | Cây đường dài, tìm Θ(n) |
| Skip list với mức ngẫu nhiên và giới hạn phù hợp n | Find/insert/delete **O(log n) kỳ vọng** | Mọi node thấp, tìm Θ(n); unbounded level còn có chi phí bốc mức dài |
| Randomized quicksort trên khóa phân biệt | Số so sánh **O(n log n) kỳ vọng** | Pivot liên tục cực trị, Θ(n²) |
| Separate-chaining hashing với hàm hash đủ tốt, tải được kiểm soát | Exact-key **O(1) kỳ vọng** | Va chạm nặng, tìm Θ(n) trong cấu hình xấu |
| AVL/red-black tree chuẩn | Find/insert/delete **O(log n) worst-case** | Không có đường tìm tuyến tính nếu giữ đúng bất biến |
| Hybrid sort có depth guard + fallback heapsort | Sort **O(n log n) worst-case** | Pivot vẫn có thể xấu nhưng fallback giới hạn tổng chi phí |

**Năm nguyên tắc cần ghi nhớ:**

1. **Expected không phải worst-case.** Một kết quả hiếm nhưng hợp lệ vẫn thuộc worst-case.
2. **Nói rõ random đến từ đâu.** Trung bình theo đầu vào, theo seed/priority/level, hay theo chuỗi thao tác là những phát biểu khác nhau.
3. **Chặn tail cần chứng minh riêng.** Kỳ vọng không tự cung cấp P99,9 hoặc xác suất `1/n^c` ở ngưỡng logarit.
4. **Fallback phải tính đủ chi phí.** Rebuild, rehash và retry có thể cải thiện trạng thái tương lai nhưng vẫn khiến một thao tác đơn lẻ tốn O(n) hoặc không có chặn hữu hạn nếu retry vô hạn.
5. **Tính đúng phải độc lập với may rủi.** Treap/skip list phải luôn giữ bất biến và trả kết quả đúng; ngẫu nhiên chỉ được dùng để cải thiện chi phí, không để hợp thức hóa việc mất khóa.

Khi đánh giá một cấu trúc ngẫu nhiên, hãy hỏi:

> **Với dữ liệu cố định, lựa chọn random nào khiến thuật toán chậm nhất; xác suất của lựa chọn ấy là bao nhiêu; và ứng dụng của mình có chấp nhận hậu quả của nó không?**

Nếu câu trả lời đòi **không bao giờ vượt một giới hạn** thay vì **hiếm khi vượt**, hãy dùng một thuật toán hoặc fallback có **worst-case được chứng minh**, rồi xác minh thêm các yếu tố hệ thống như bộ nhớ, đồng bộ và độ trễ thực tế. Đó là cách sử dụng các bảo đảm kỳ vọng một cách chính xác khi lựa chọn cấu trúc dữ liệu.
