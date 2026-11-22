# Tổng tiền tố song song (parallel scan)

**Parallel scan** là phép biến đổi một dãy thành các **tổng tích lũy theo tiền tố**, nhưng phân phối phép tính lên nhiều luồng xử lý thay vì buộc một luồng cộng tuần tự từ đầu đến cuối. Đây là một **parallel primitive** quan trọng: ngoài tổng tiền tố, cùng mẫu thuật toán được dùng cho stream compaction, radix sort, dựng chỉ mục, xử lý vector, phân đoạn dữ liệu và nhiều phép tổng hợp song song trên CPU/GPU.

Điểm cốt lõi: tổng tiền tố tuần tự có **O(n) công việc (work)** nhưng cũng có chuỗi phụ thuộc dài O(n) nếu trực tiếp cập nhật từng phần tử. Thuật toán song song tổ chức phép tính thành **cây và nhiều pha đồng bộ**, nhằm rút ngắn **đường phụ thuộc dài nhất (span/depth)** xuống **O(log n)**, đôi khi phải đánh đổi thêm work.

Bài thuộc nhóm **Thuật toán song song**, làm rõ:

- **Inclusive scan** khác **exclusive scan** thế nào.
- Phép toán kết hợp (associative operator) và phần tử đơn vị (identity) là điều kiện cần cho scan tổng quát.
- **Hillis–Steele** (còn thường thấy dưới dạng kiểu Kogge–Stone) có O(n log n) work, O(log n) span với bộ đệm riêng từng pha.
- **Blelloch scan** theo **upsweep/downsweep** có O(n) work và O(log n) span trong mô hình song song lý tưởng.
- **Blocked scan** thực dụng trên CPU: scan cục bộ song song, scan các tổng khối, cộng offset.
- API **Arrays.parallelPrefix** của Java 17, cách tổ chức đồng bộ để tránh race và lý do bài nhỏ có thể chạy chậm hơn tuần tự.
- Ứng dụng: truy vấn tổng đoạn tĩnh, stream compaction, segmented scan, prefix cho mảng 2D và chuẩn bị dữ liệu trên GPU.
- Chương trình **Java 17+ độc lập**, ví dụ đầu ra, kiểm chứng bằng oracle tuần tự và kiểm thử ngẫu nhiên.

Các minh họa chính dùng mảng **int[]** và tính tổng bằng **long** để tránh tràn int. Phân tích work/span giả sử phép cộng word có chi phí O(1); thời gian chạy Java thực tế còn phụ thuộc lập lịch, độ lớn mảng, băng thông bộ nhớ và số lõi.

## 1. Nhắc lại tổng tiền tố tuần tự

Cho dãy:

**a=[a₀,a₁,...,aₙ₋₁]**.

Định nghĩa tổng tiền tố **bao gồm phần tử hiện tại (inclusive)**:

**S[i]=Σ_{j=0}^{i} a[j]**, với 0≤i<n.

Định nghĩa tổng tiền tố **không bao gồm phần tử hiện tại (exclusive)**:

**E[i]=Σ_{j=0}^{i−1} a[j]**, với 0≤i<n và E[0]=0.

Với dãy:

~~~text
a = [3, -2, 5, 7, 0, -4]

Inclusive S:
    [3, 1, 6, 13, 13, 9]

Exclusive E:
    [0, 3, 1, 6, 13, 13]
~~~

Nếu muốn một mảng prefix quen thuộc để truy vấn đoạn nửa mở, có thể tạo P độ dài n+1:

**P[0]=0** và **P[i+1]=S[i]**.

Vậy:

~~~text
P = [0, 3, 1, 6, 13, 13, 9]
~~~

Với 0≤l≤r≤n:

**sum[l,r)=P[r]−P[l]**.

### Thuật toán tuần tự

~~~text
P[0] = 0
for i from 0 to n-1:
    P[i+1] = P[i] + a[i]
~~~

Tổng cộng n phép cộng, nên **work Θ(n)**. Nhưng vì P[i+1] phụ thuộc P[i], nếu dùng đúng vòng lặp này thì **span Θ(n)**. Để chạy song song hiệu quả, cần một **sơ đồ phụ thuộc khác**, không phải đơn giản thêm nhiều threads quanh vòng lặp phụ thuộc.

## 2. Điều kiện toán học: monoid

Scan không chỉ dành cho phép cộng. Xét một tập giá trị và toán tử nhị phân:

**x ⊕ y**.

Muốn dùng các thuật toán scan dạng cây một cách tổng quát, ta cần:

**Tính kết hợp (associativity):**

**(a⊕b)⊕c = a⊕(b⊕c)**.

**Phần tử đơn vị e (identity):**

**e⊕a=a⊕e=a**.

Một tập cùng toán tử có hai tính chất ấy gọi là **monoid**.

Ví dụ:

| Phép toán | Identity | Có thể scan dạng cây? |
| --- | --- | --- |
| Tổng số nguyên | 0 | Có |
| Tích số nguyên trong miền được quy định | 1 | Có |
| XOR bitwise | 0 | Có |
| OR bitwise | 0 | Có |
| Min trên miền có +∞ | +∞ | Có |
| Max trên miền có −∞ | −∞ | Có |
| Nối chuỗi theo thứ tự | Chuỗi rỗng | Có, nhưng phải giữ thứ tự |

**Không yêu cầu tính giao hoán.** Nối chuỗi nói chung có a⊕b khác b⊕a, nhưng vẫn kết hợp. Vì thế thuật toán scan phải giữ đúng **thứ tự trái trước phải** khi gộp các đoạn.

### Vì sao không dùng mọi phép toán?

Phép trừ và phép chia không có tính kết hợp chung. Với chúng, đổi cách đặt ngoặc sẽ đổi kết quả; một parallel reduction hình cây không thể tự động thay thế phép tính tuần tự mà vẫn giữ cùng semantics.

### Số thực dấu phẩy động

Phép cộng float/double không kết hợp **một cách chính xác về mặt bit** do làm tròn:

**(a+b)+c** có thể khác **a+(b+c)**.

Vì vậy một parallel scan số thực có thể có sai khác làm tròn so với cộng tuần tự. Cần quy định tolerance, thứ tự cố định khi muốn reproducibility, hoặc sử dụng kỹ thuật tăng ổn định số học; không tuyên bố kết quả floating-point luôn bitwise giống nhau.

## 3. Work, span và speedup

Để đánh giá thuật toán song song, dùng ít nhất ba khái niệm:

**Work W(n):** tổng số thao tác được thực hiện bởi tất cả worker.

**Span S(n):** độ dài đường phụ thuộc dài nhất nếu có đủ bộ xử lý và thao tác cơ bản đồng thời hoàn hảo.

**Thời gian T_p(n):** thời gian chạy với p bộ xử lý thực tế.

Một lower bound phổ biến:

**T_p(n)≥max(W(n)/p,S(n))**,

nếu bỏ qua các hằng số và overhead đặc thù.

### Ví dụ

- Vòng lặp prefix tuần tự: W=Θ(n), S=Θ(n).
- Hillis–Steele: W=Θ(n log n), S=Θ(log n) trong mô hình ideal parallel rounds.
- Blelloch: W=Θ(n), S=Θ(log n).
- Blocked scan với p khối và scan tổng khối **tuần tự**: W=Θ(n+p), span/critical time ở mô hình p workers khoảng **O(n/p+p)**.

### Vì sao cần cả W và S?

Một thuật toán có span ngắn nhưng dùng n log n work có thể kém trên máy ít lõi hoặc dataset khổng lồ. Một thuật toán work-efficient có thể tốt hơn về tổng tài nguyên nhưng vẫn bị overhead đồng bộ làm chậm ở kích thước nhỏ.

**Speedup(p)=T_1/T_p** không được bảo đảm bằng p. Memory bandwidth, synchronization và số thread thực có thể là nút cổ chai.

## 4. Hillis–Steele: cộng theo khoảng cách gấp đôi

Hillis–Steele xây inclusive scan theo **các pha**. Ở pha thứ d, mỗi phần tử cộng thêm giá trị cách nó **2^d** vị trí về bên trái, nếu tồn tại.

Gọi X^(0)[i]=a[i]. Với offset=1,2,4,8,...:

**X_new[i] = X_old[i]** nếu i<offset.

**X_new[i] = X_old[i−offset] + X_old[i]** nếu i≥offset.

Sau ceil(log₂ n) pha, X là inclusive scan.

### Vì sao tăng offset gấp đôi?

- Sau offset=1, mỗi phần tử tổng hợp tối đa 2 phần tử gần nhất.
- Sau offset=2, mỗi phần tử tổng hợp tối đa 4 phần tử gần nhất.
- Sau offset=4, mỗi phần tử tổng hợp tối đa 8 phần tử gần nhất.
- Tiếp tục tới khi phạm vi che phủ đủ n phần tử.

Cách này biến chuỗi phụ thuộc dài thành **logarithmic number of globally synchronized stages**.

## 5. Ví dụ từng pha Hillis–Steele

Với dãy sáu phần tử:

~~~text
Initial:
[3, -2, 5, 7, 0, -4]

Offset 1:
[3, 1, 3, 12, 7, -4]

Offset 2:
[3, 1, 6, 13, 10, 8]

Offset 4:
[3, 1, 6, 13, 13, 9]
~~~

Sau offset 4, ta được inclusive scan đúng:

**[3,1,6,13,13,9]**.

Ví dụ ở phần tử cuối:

- Sau offset 1, −4 chưa cộng được giá trị xa hơn một vị trí.
- Sau offset 2, nó đã cộng ảnh hưởng từ một nhóm gồm tối đa 4 phần tử.
- Sau offset 4, nó cộng nốt nhóm đầu dãy và đạt tổng 9.

### Quan trọng: luôn đọc dữ liệu của pha trước

Trong mỗi pha, các phép cộng phải cùng đọc **X_old**, không dùng giá trị vừa bị một thread khác sửa trong chính pha ấy.

Nếu cập nhật in-place tùy tiện và cho các thread chạy tự do, kết quả phụ thuộc thứ tự chạy, có thể không còn là Hillis–Steele hợp lệ.

Mã Java dùng **hai mảng old/new mỗi pha** và một rào đồng bộ khi terminal operation của parallel stream kết thúc.

## 6. Chi phí Hillis–Steele

Với n là lũy thừa của hai, tại offset=2^d có khoảng:

**n−2^d phép cộng**.

Tổng các pha:

**Σ_{d=0}^{log₂n−1}(n−2^d) = nlog₂n−(n−1)**.

Với n=8:

- Offset 1: 7 phép cộng.
- Offset 2: 6 phép cộng.
- Offset 4: 4 phép cộng.
- Tổng: **17 phép cộng**, ngoài các phép copy.

Vì thế:

**Work W(n)=Θ(n log n)**.

Các phép toán trong cùng một pha độc lập về dữ liệu cũ; có khoảng log n pha phụ thuộc nối tiếp:

**Span S(n)=Θ(log n)**

trong mô hình đủ processors, mỗi thao tác O(1).

### Khi nào cách này vẫn hữu ích?

- Mô tả đơn giản, dễ kiểm chứng.
- Hợp với một số mô hình SIMD/GPU khi chi phí đồng bộ giữa phases và truy cập memory phù hợp.
- Có thể nhanh cho kích thước dữ liệu vừa phải và kiến trúc cụ thể.

Nhưng vì work không tối ưu, nó thường không phải phương án đầu tiên khi tối ưu tổng throughput cho dữ liệu lớn.

## 7. Blelloch scan: hai lượt trên cây

**Blelloch scan** tổ chức phép tính trên cây nhị phân cân bằng với hai pha:

1. **Upsweep (reduce):** từ lá lên gốc, mỗi node chứa tổng của một đoạn con.
2. **Downsweep:** từ gốc xuống lá, phân phối cho mỗi node lượng tổng đứng **trước** đoạn con ấy.

Kết quả downsweep tại lá là **exclusive scan**. Inclusive có thể nhận được bằng:

**S[i]=E[i]+a[i]**,

hoặc tạo mảng prefix P độ dài n+1 theo:

**P[i]=E[i]** với 0≤i<n,

và **P[n]=E[n−1]+a[n−1]** nếu n>0.

### Đệm đến lũy thừa hai

Để giải thích chỉ số cây bằng mảng dễ hơn, đặt:

**m=2^{ceil(log₂ max(1,n))}**.

Sao chép n phần tử vào mảng dài m; phần tử còn lại gán **identity=0**.

Padding bằng 0 không đổi tổng các phần tử thật.

Với n=6, m=8:

~~~text
Original: [3, -2, 5, 7, 0, -4]
Padded:   [3, -2, 5, 7, 0, -4, 0, 0]
~~~

Vì **n≤m<2n** với n>0, padding không làm độ phức tạp vượt bậc O(n).

## 8. Upsweep: tích lũy theo các nhánh

Ở mức đầu tiên, cộng từng cặp lá. Ở mức tiếp theo, cộng kết quả của hai đoạn dài 2. Sau đó là các đoạn dài 4,8,...

Với n=8 và m=8:

~~~text
for halfSpan = 1, 2, 4:
    groupSize = 2 * halfSpan

    parallel for each group:
        right = last index of group
        left  = right - halfSpan
        tree[right] += tree[left]
~~~

Các right nodes ở cùng một mức thuộc **những đoạn không giao nhau**, nên cập nhật được song song mà không tranh ghi.

Sau tất cả các mức, **tree[m−1]** là tổng toàn bộ dãy đã padding.

### Chứng minh bằng quy nạp trên độ dài nhóm

- Ban đầu, mỗi lá đại diện đúng một phần tử.
- Nếu hai đoạn con trái/phải mỗi đoạn có tổng đúng, phép cộng ở node cha cho tổng toàn đoạn ghép.
- Sau log₂m mức, root chứa tổng của tất cả m phần tử.

Với phép toán không giao hoán, thứ tự phải là **left ⊕ right**, không tùy tiện đảo vị trí.

## 9. Downsweep: mang tổng từ trái sang phải

Sau upsweep, đặt:

**tree[m−1]=0**,

vì tổng **trước toàn bộ dãy** là identity.

Đi từ nhóm lớn xuống nhóm nhỏ:

~~~text
for halfSpan = m/2, m/4, ..., 1:
    groupSize = 2 * halfSpan

    parallel for each group:
        right = last index of group
        left = right - halfSpan

        t = tree[left]
        tree[left] = tree[right]
        tree[right] = tree[right] + t
~~~

Ý nghĩa:

- Node bên trái nhận tổng đứng **trước cả nhóm**.
- Node bên phải nhận tổng đứng trước cả nhóm **cộng tổng đoạn con trái**.

Khi tới lá i, giá trị tại lá là tổng tất cả phần tử đứng trước a[i], tức **E[i]**.

### Ví dụ

Với [3,−2,5,7,0,−4] được padding lên 8:

~~~text
Exclusive for padded 8 leaves:
[0, 3, 1, 6, 13, 13, 9, 9]

Exclusive for 6 original values:
[0, 3, 1, 6, 13, 13]

Full prefix P of length n+1:
[0, 3, 1, 6, 13, 13, 9]
~~~

Các số 0 padding **không đại diện phần tử đầu vào mới**; loại chúng khỏi kết quả cuối.

## 10. Chứng minh work/span của Blelloch

Cây đủ m lá có **m−1 node trong**.

**Upsweep** thực hiện một phép gộp ở mỗi node trong:

**m−1 phép kết hợp**.

**Downsweep** xử lý mỗi node trong một lần, với một phép gộp và một số phép gán:

**m−1 bước xử lý node**.

Do m<2n khi n>0:

**Work = Θ(m)=Θ(n)**.

Chiều cao cây:

**log₂m=Θ(log n)**.

Upsweep đi lên log₂m mức; downsweep đi xuống log₂m mức. Từng mức có thể chạy các nhóm song song nên:

**Span = Θ(log n)**

trong mô hình ideal PRAM không tính chi phí scheduling/memory barriers.

### Khác biệt quan trọng

Hillis–Steele giảm span nhưng **tăng tổng work lên Θ(n log n)**.

Blelloch vừa có **work Θ(n)** như tuần tự, vừa có **span Θ(log n)** — đó là ý nghĩa của **work-efficient parallel scan**.

Không nên biến kết quả này thành phát biểu “Java dùng parallel stream luôn đạt T=O(log n)”: trên p lõi thực, phải tính W/p và overhead, không có vô hạn processors.

## 11. Chuyển exclusive scan thành inclusive và P

Với n>0:

**S[i]=E[i]⊕a[i]**.

Với phép cộng:

**S[i]=E[i]+a[i]**.

Muốn có mảng P độ dài n+1:

**P[0]=0**,

**P[i+1]=S[i]**.

Có thể tạo P từ Blelloch theo cách giảm công:

- Ghi E[0..n−1] vào P[0..n−1].
- Tính P[n]=E[n−1]+a[n−1].

Với n=0, mảng prefix chuẩn là:

**P=[0]**.

### Truy vấn đoạn

Một khi P được xây đúng:

**sum(l,r)=P[r]−P[l]**, 0≤l≤r≤n.

Việc dựng P song song chỉ giúp **giai đoạn tiền xử lý**, không đổi bản chất query O(1) của prefix tổng đoạn tĩnh.

Nếu a bị cập nhật, P cũng không tự động thay đổi. Parallel scan thường hữu ích khi tạo mới prefix cho **một batch dữ liệu hoặc một phiên bản snapshot**, không phải phép màu khiến point updates tự có O(1).

## 12. Blocked parallel scan: cách tiếp cận thực dụng

Trên máy nhiều lõi, tạo một task cho từng node ở mỗi mức cây có thể tạo overhead lớn. Một cách gần với triển khai CPU hơn là **chia dãy thành p khối liên tục**.

Ba bước:

1. **Local scan:** song song tính prefix cục bộ của mỗi khối, giả sử mỗi khối bắt đầu từ 0; đồng thời lưu tổng khối.
2. **Scan block totals:** tính tổng của các khối đứng trước mỗi khối, tức **offset**.
3. **Fix-up:** song song cộng offset của khối vào mọi prefix cục bộ trong khối ấy.

Ví dụ với:

~~~text
a = [3, -2, 5, 7, 0, -4]

Block 0 = [3, -2]
Block 1 = [5, 7]
Block 2 = [0, -4]

Local inclusive:
Block 0: [3, 1], total=1
Block 1: [5, 12], total=12
Block 2: [0, -4], total=-4

Block offsets:
[0, 1, 13]

After adding offsets:
Block 0: [3, 1]
Block 1: [6, 13]
Block 2: [13, 9]
~~~

Ghép lại inclusive:

**[3,1,6,13,13,9]**.

### Vì sao local scan của block b cần offset?

Local scan chỉ biết phần tử trong block b. Mỗi phần tử ở block b còn phải cộng tổng của **toàn bộ block 0..b−1**. Offset đó chính là exclusive scan của mảng block totals.

## 13. Phân tích blocked scan theo cách tính offsets

Giả sử chia n phần tử vào p khối tương đối đều, p≤n.

**Local scan song song:** mỗi worker xử lý khoảng n/p phần tử; tổng work O(n).

**Scan p block totals:**

- Nếu làm tuần tự: O(p) work, span O(p).
- Nếu dùng parallel tree scan: O(p) work, span O(log p).

**Fix-up song song:** mỗi worker cập nhật khoảng n/p phần tử, work O(n).

Vậy với offsets **tuần tự** như mã Java trong bài:

**Work Θ(n+p)=Θ(n)** khi p≤n.

**Span/time theo mô hình p processors ≈ O(n/p+p)**.

Nếu scan block totals cũng được triển khai bằng work-efficient parallel scan, có thể đạt:

**Span ≈ O(n/p+log p)**

trong mô hình ideal đủ workers, không tính scheduler/memory overhead.

### Lựa chọn p

Không nên đặt p=n cho mọi input: khi mỗi khối chỉ có một phần tử, bước scan offsets tuần tự lại trở thành O(n).

Thường có thể dùng số khối gần số worker thực, hoặc nhiều khối hơn một chút để cân bằng tải rồi **scan block totals song song** nếu cần. Hiệu quả phụ thuộc p, kích thước batch và băng thông RAM.

## 14. Java Arrays.parallelPrefix

Java 17 có API trong **java.util.Arrays**:

**Arrays.parallelPrefix(array, operator)**.

Với mảng **long[]** và phép cộng:

~~~java
Arrays.parallelPrefix(values, Long::sum);
~~~

Kết quả là **inclusive scan tại chỗ** trên mảng values.

Ví dụ:

~~~text
Before: [3, -2, 5, 7, 0, -4]
After:  [3, 1, 6, 13, 13, 9]
~~~

### Chú ý

- API này là **inclusive**; nếu cần P độ dài n+1, đặt P[0]=0 rồi copy kết quả vào P[1..n].
- API có quyền cập nhật mảng truyền vào, nên hãy **clone/copy** nếu muốn giữ dữ liệu gốc.
- Phép operator phải **associative** theo hợp đồng thuật toán.
- API có thể dùng ForkJoin common pool và tối ưu riêng; không bắt buộc mọi input nhỏ đều thực sự được xử lý trên nhiều lõi.
- Không coi performance hoặc quy tắc scheduling nội bộ là cố định giữa các phiên bản JVM.

Trong bài, Arrays.parallelPrefix đóng vai trò **API production-oriented để đối chiếu** với hai triển khai tự học Hillis–Steele và Blelloch.

## 15. Race condition và rào đồng bộ giữa các mức

Thuật toán song song đúng không chỉ cần một công thức toán học đúng; còn phải đảm bảo **hành vi bộ nhớ** đúng.

### Hillis–Steele

Trong một mức:

- Mọi worker **đọc mảng old** chỉ đọc.
- Mỗi worker ghi **một chỉ số riêng** của mảng next.
- Sau khi tất cả worker hoàn thành, mới hoán đổi old/next.

Nếu cho worker ghi thẳng lên old rồi một worker khác đọc một ô vừa đổi, kết quả có thể phụ thuộc interleaving.

### Blelloch

Tại một mức upsweep hoặc downsweep:

- Mỗi nhóm là một đoạn con không giao nhau với nhóm khác.
- Chỉ những vị trí của nhóm ấy được ghi.
- Sau khi hết mức, toàn bộ tác vụ phải hoàn thành trước khi bắt đầu mức kế tiếp.

Trong code, mỗi lời gọi terminal:

**IntStream.range(...).parallel().forEach(...)**

chỉ trả về sau khi xử lý xong các phần tử của stream. Vì vậy vòng lặp mức kế tiếp không bắt đầu trước khi mức hiện tại kết thúc.

### Không dùng parallel cho vòng lặp có phụ thuộc thực

Đoạn code:

~~~java
for (int i = 0; i < n; i++) {
    prefix[i + 1] = prefix[i] + a[i];
}
~~~

không thể đơn thuần đổi thành parallel forEach theo i, bởi prefix[i+1] **đọc kết quả của iteration trước**. Cần dùng Hillis–Steele, cây Blelloch hoặc partition + offsets như các mục trên.

## 16. False sharing, bandwidth và granularity

Ngay cả khi các worker ghi các chỉ số **khác nhau**, chúng vẫn có thể tranh giành đường truyền cache nếu các chỉ số nằm trên **cùng cache line**.

Hiện tượng **false sharing** xảy ra khi nhiều core ghi những vùng độc lập về logic nhưng cùng nằm trong đơn vị coherence, làm cache line ping-pong.

Các yếu tố thực tế:

- **Granularity:** task quá nhỏ có chi phí scheduling lớn.
- **Memory bandwidth:** scan thường chỉ làm vài phép cộng cho mỗi phần tử, nên có thể bị giới hạn bởi tốc độ di chuyển dữ liệu.
- **Allocation:** Hillis–Steele tạo mảng next mỗi mức, tăng lượng copy và áp lực GC.
- **Cache locality:** blocked scan đi qua các đoạn liên tục, thường thuận lợi cho CPU caches.
- **Synchronization:** mỗi level cần barrier; log n level vẫn có overhead.
- **NUMA:** nhiều socket có latency truy cập bộ nhớ khác nhau.

Bởi vậy, **span O(log n)** trong lý thuyết không có nghĩa một scan 100 phần tử trên Java sẽ nhanh hơn vòng for. Benchmark cần làm ở kích thước đủ lớn và điều kiện tải phù hợp.

## 17. Prefix cho truy vấn tổng đoạn sau khi dựng song song

Dù prefix được tạo bằng tuần tự, Blelloch, blocked hoặc Arrays.parallelPrefix, kết quả P phải giống nhau trong số học nguyên chính xác:

**P[0]=0**.

**P[k]=Σ_{i=0}^{k−1}a[i]**.

Sau đó:

**rangeSum(l,r)=P[r]−P[l]**.

Ví dụ:

~~~text
a = [3, -2, 5, 7, 0, -4]
P = [0, 3, 1, 6, 13, 13, 9]

sum[1,5) = P[5]-P[1] = 13-3 = 10
sum[2,6) = P[6]-P[2] = 9-1 = 8
sum[3,3) = 0
~~~

### Tại sao không tính query bằng scan mỗi lần?

Nếu a không thay đổi và có nhiều range-sum queries, xây P một lần có lợi hơn chạy scan lại cho mỗi query.

Parallel scan đặc biệt thích hợp khi **n rất lớn, có nhiều tài nguyên song song** và chi phí khởi tạo prefix chiếm phần đáng kể của pipeline.

Với q truy vấn nhỏ và n cũng nhỏ, một vòng lặp tuần tự có thể đơn giản, nhanh và ít overhead hơn.

## 18. Ứng dụng stream compaction

**Stream compaction** giữ các phần tử thỏa một predicate nhưng vẫn bảo toàn thứ tự tương đối ban đầu.

Cho:

~~~text
a = [4, -1, 0, 7, -3, 2]
Keep positive values (>0).
Flags = [1, 0, 0, 1, 0, 1]
~~~

Tính **exclusive scan của flags**:

~~~text
Positions = [0, 1, 1, 1, 2, 2]
~~~

Mỗi phần tử có flag=1 sẽ được scatter đến chỉ số Positions[i]:

- a[0]=4 → output[0].
- a[3]=7 → output[1].
- a[5]=2 → output[2].

Kết quả:

**[4,7,2]**.

Tổng số phần tử được giữ:

**count = Positions[n−1] + Flags[n−1] = 3**,

hoặc dùng P[n] từ full exclusive prefix độ dài n+1.

### Tại sao scatter không đụng nhau?

Các vị trí có flag=1 được gán chỉ số bằng số phần tử được giữ trước đó. Vì thế mỗi phần tử được giữ có một vị trí output **duy nhất** và các vị trí tăng theo thứ tự input.

Điều này làm compaction có thể thực hiện song song: mỗi thread tính predicate cục bộ, dùng scan để tìm output offsets, rồi ghi vào output riêng không chồng lấp.

### Edge cases

Nếu không có phần tử được giữ, output dài 0. Nếu tất cả được giữ, Positions là [0,1,...,n−1]. Nếu input rỗng, count=0, không truy cập Positions[−1].

## 19. Ứng dụng trong parallel radix sort

Một lượt của **radix sort** thường phân loại phần tử theo bit hoặc chữ số hiện tại.

Với bản **binary stable partition** theo một bit:

1. Tính bit flag của mỗi phần tử.
2. Scan các flag để biết thứ tự nội bộ trong nhóm bit=1.
3. Từ số lượng phần tử bit=0, tính vị trí bắt đầu nhóm bit=1.
4. Scatter mỗi phần tử tới vị trí duy nhất, giữ thứ tự ban đầu trong từng nhóm.

Ví dụ với bit=1:

**oneBefore(i)=exclusiveScan(flag)[i]**.

**zeroBefore(i)=i−oneBefore(i)**.

Nếu tổng số zeros là Z:

- Phần tử bit=0 → dest=zeroBefore(i).
- Phần tử bit=1 → dest=Z+oneBefore(i).

Nhờ các destination không trùng và thứ tự trong nhóm tăng dần, phép phân vùng **ổn định (stable)**.

Một radix sort nhiều bit sẽ lặp nhiều lượt partition theo digit/bit, kết hợp scan, histogram và scatter.

### Không tự suy ra radix sort luôn O(n)

Nếu số digits cố định và mỗi lượt O(n), tổng có thể tuyến tính theo n; nhưng phải tính cả **số lượt digits**, kích thước key, bộ nhớ phụ và bandwidth. Scan chỉ là một primitive trong pipeline.

## 20. Segmented scan: nhiều prefix độc lập trong một dãy

Trong nhiều bài, input là các nhóm liên tiếp (segments), mỗi nhóm cần prefix riêng.

Ví dụ:

~~~text
a     = [3, -2, 5 | 7, 0 | -4]
start = [1,  0, 0 | 1, 0 |  1]
~~~

**Inclusive segmented sums:**

~~~text
[3, 1, 6 | 7, 7 | -4]
~~~

**Exclusive segmented sums:**

~~~text
[0, 3, 1 | 0, 7 | 0]
~~~

Ở đầu mỗi segment, tổng phải bắt đầu lại từ identity thay vì nhận prefix của segment trước.

### Có thể biến thành scan trên cặp trạng thái

Mỗi phần tử được biểu diễn bằng cặp:

**(value, startFlag)**.

Với hai cặp (x,hx) và (y,hy), định nghĩa phép gộp theo thứ tự trái→phải:

**(x,hx) ⊗ (y,hy) = (hy ? y : x+y, hx OR hy)**.

Nếu vế phải chứa một điểm bắt đầu segment mới, giá trị tích lũy của segment cuối nằm hoàn toàn trong vế phải, nên bỏ tích lũy bên trái. Nếu không, cộng tiếp từ trái.

Toán tử này kết hợp khi hiểu mỗi cặp là summary của một đoạn, và identity là **(0,false)**. Vì vậy có thể sử dụng cùng kiến trúc parallel scan, nhưng state và proof khác phép cộng thường.

### Ứng dụng

- Prefix theo từng nhóm khóa đã sort.
- Ragged batches, xử lý dữ liệu dạng CSR.
- Thống kê theo phân đoạn tín hiệu.
- Grouped running totals trên GPU.

Không được dùng scan toàn dãy rồi chỉ trừ một hằng số nếu boundary metadata thay đổi bất kỳ mà không chứng minh phép biến đổi tương đương.

## 21. Parallel scan hai chiều

Với ma trận tĩnh R×C, prefix 2D có thể dựng từ hai nhóm scan 1D:

1. Scan theo hàng để nhận tổng từ cột 0 tới cột hiện tại.
2. Scan theo cột trên các kết quả ấy để tích lũy các hàng trước.

Sau khi thêm hàng 0/cột 0, truy vấn rectangle có công thức:

**sum([r1,r2)×[c1,c2))=P[r2][c2]−P[r1][c2]−P[r2][c1]+P[r1][c1]**.

### Hai trục song song khác nhau

Các hàng độc lập có thể scan đồng thời. Khi scan theo cột, những cột độc lập cũng có thể làm song song, nhưng truy cập memory theo cột có thể kém liên tục hơn trên dữ liệu row-major.

Tối ưu có thể cần tiling/transposition hoặc thực hiện scan theo block để tăng locality. Chi phí overhead và memory layout đôi khi quan trọng hơn số mức log.

### Ma trận động

Nếu giá trị ma trận thường xuyên thay đổi, một bảng prefix đã materialize trở thành snapshot cũ. Parallel scan giúp **rebuild nhanh hơn khi đủ tài nguyên**, không tự hỗ trợ point updates/rectangle queries động ở O(1).

## 22. Parallel scan trên GPU

GPU thường có nhiều thread và chi phí truy cập bộ nhớ khác CPU. Parallel scan là primitive chuẩn vì:

- Nhiều nhóm có thể xử lý từng tile độc lập.
- Mỗi tile có thể thực hiện upsweep/downsweep trong shared memory.
- Các tile totals được scan ở cấp cao hơn.
- Kết quả được cộng offsets để hoàn tất global prefix.

### Những vấn đề cần xử lý

- **Synchronization:** thread trong cùng block có barrier, giữa blocks cần nhiều kernel launches hoặc các giao thức an toàn.
- **Memory coalescing:** các thread lân cận nên truy cập địa chỉ gần nhau.
- **Bank conflicts:** tổ chức shared memory không phù hợp gây tranh chấp.
- **Occupancy:** tile quá lớn chiếm nhiều register/shared memory.
- **Multi-level scan:** dataset lớn hơn một block cần scan block totals ở cấp cao hơn.
- **Determinism:** floating-point reduction tree có thể làm thay đổi thứ tự cộng.

Khái niệm Blelloch work-efficient rất hữu ích, nhưng code Java với parallel streams **không phải CUDA kernel**. Đừng sao chép cận memory/latency từ GPU sang Java CPU mà không đo.

## 23. Quản lý lỗi tràn và kiểu số

Trong Java, int là signed 32-bit; long là signed 64-bit.

Ví dụ:

~~~text
a = [2147483647, 2147483647, -2147483648, 1]
P = [0, 2147483647, 4294967294, 2147483646, 2147483647]
~~~

Nếu cộng hai int đầu tiên bằng toán tử int:

**2147483647+2147483647**

sẽ overflow int, làm hỏng tổng toán học chính xác.

Cách an toàn hơn khi input là int[]:

- Sao chép từng a[i] vào long trước khi cộng.
- Dùng long[] cho cây/prefix.
- Khi input là long[] hoặc tổng vượt miền long, cân nhắc Math.addExact để phát hiện overflow hoặc BigInteger để tính chính xác.

### Tính kết hợp modulo và tính kết hợp toán học

Phép cộng long overflow trong Java theo modulo 2^64 vẫn có tính kết hợp modulo, nhưng kết quả không còn là tổng số nguyên toán học nếu vượt miền long.

Bài demo dùng n phần tử int với số lượng phần tử mà Java có thể lưu trong mảng, nên tổng của các int vẫn nằm trong long theo các giới hạn kích thước mảng thực tế. Đây không phải bảo đảm cho mọi kiểu input hoặc mô hình số học mở rộng.

## 24. Chương trình Java 17+ độc lập: bốn cách scan

Chương trình sau triển khai:

1. **sequentialPrefix**: oracle tuần tự, trả P độ dài n+1.
2. **hillisSteeleInclusive**: song song theo từng offset, dùng mảng next riêng mỗi pha, trả inclusive n phần tử.
3. **blellochPrefix**: upsweep/downsweep theo cây đã padding, trả full prefix n+1, không làm đổi input.
4. **blockedPrefix**: chia thành số khối do người gọi chọn, local scan/fix-up song song, scan block totals **tuần tự**, trả full prefix n+1.
5. **libraryPrefix**: gọi **Arrays.parallelPrefix** của Java 17, chuyển kết quả inclusive thành P.
6. **show**: so từng kết quả với oracle và in prefix cho các input gồm số âm, cực trị int, n=0, n=1, n không là lũy thừa hai.

**Tên tệp: ParallelScanDemo.java**

~~~java
import java.util.Arrays;
import java.util.Objects;
import java.util.stream.IntStream;

public class ParallelScanDemo {

    // Sequential oracle, O(n) work and O(n) span.
    static long[] sequentialPrefix(int[] input) {
        Objects.requireNonNull(input, "input");

        long[] result = new long[input.length + 1];

        for (int i = 0; i < input.length; i++) {
            result[i + 1] = result[i] + input[i];
        }

        return result;
    }

    // Inclusive scan: O(n log n) work and O(log n)
    // ideal span. Each stage reads an immutable old array.
    static long[] hillisSteeleInclusive(int[] input) {
        Objects.requireNonNull(input, "input");
        int n = input.length;

        long[] current = new long[n];

        for (int i = 0; i < n; i++) {
            current[i] = input[i];
        }

        // long offset avoids overflow if n is very large.
        for (long offset = 1; offset < n; offset *= 2) {
            final int shift = (int) offset;
            final long[] previous = current;
            long[] next = new long[n];

            IntStream.range(0, n).parallel().forEach(i -> {
                long left = i >= shift
                        ? previous[i - shift] : 0L;
                next[i] = previous[i] + left;
            });

            // All tasks of this phase have finished.
            current = next;
        }

        return current;
    }

    // Work-efficient exclusive scan via upsweep/downsweep.
    // Returns P with length n+1.
    static long[] blellochPrefix(int[] input) {
        Objects.requireNonNull(input, "input");
        int n = input.length;

        if (n == 0) {
            return new long[] {0L};
        }

        int size = 1;

        while (size < n) {
            if (size > (1 << 29)) {
                throw new IllegalArgumentException(
                        "padded scan array too large");
            }
            size <<= 1;
        }

        long[] tree = new long[size];

        for (int i = 0; i < n; i++) {
            tree[i] = input[i];
        }

        // UPSWEEP: right node accumulates left subtree.
        for (int span = 1; span < size; span *= 2) {
            final int half = span;
            final int groupSize = 2 * span;
            final int groups = size / groupSize;

            IntStream.range(0, groups)
                    .parallel().forEach(group -> {
                int right =
                        (group + 1) * groupSize - 1;
                int left = right - half;

                tree[right] += tree[left];
            });
        }

        // Identity at the root starts exclusive prefix.
        tree[size - 1] = 0L;

        // DOWNSWEEP: distribute the prefix before each
        // subtree. Different groups write disjoint nodes.
        for (int span = size / 2; span >= 1; span /= 2) {
            final int half = span;
            final int groupSize = 2 * span;
            final int groups = size / groupSize;

            IntStream.range(0, groups)
                    .parallel().forEach(group -> {
                int right =
                        (group + 1) * groupSize - 1;
                int left = right - half;

                long oldLeft = tree[left];
                tree[left] = tree[right];
                tree[right] += oldLeft;
            });
        }

        long[] prefix = new long[n + 1];

        // First n results are exclusive prefixes.
        System.arraycopy(tree, 0, prefix, 0, n);

        // Complete the prefix P[n].
        prefix[n] = prefix[n - 1] + input[n - 1];
        return prefix;
    }

    // Three-stage block scan. The offsets step is
    // deliberately sequential: span O(n/p + p).
    static long[] blockedPrefix(
            int[] input, int requestedBlocks) {

        Objects.requireNonNull(input, "input");

        if (requestedBlocks < 1) {
            throw new IllegalArgumentException(
                    "requestedBlocks must be positive");
        }

        int n = input.length;

        if (n == 0) {
            return new long[] {0L};
        }

        final int blocks = Math.min(requestedBlocks, n);
        final long[] prefix = new long[n + 1];
        final long[] blockSums = new long[blocks];

        // Step 1: scan each block with local offset zero.
        IntStream.range(0, blocks)
                .parallel().forEach(block -> {
            int start = (int) ((long) block * n / blocks);
            int end =
                    (int) ((long) (block + 1) * n / blocks);

            long running = 0L;

            for (int i = start; i < end; i++) {
                running += input[i];
                prefix[i + 1] = running;
            }

            blockSums[block] = running;
        });

        // Step 2: exclusive prefix of the block totals.
        long[] offsets = new long[blocks];
        long running = 0L;

        for (int block = 0; block < blocks; block++) {
            offsets[block] = running;
            running += blockSums[block];
        }

        // Step 3: add the correct offset to each block.
        IntStream.range(0, blocks)
                .parallel().forEach(block -> {
            int start = (int) ((long) block * n / blocks);
            int end =
                    (int) ((long) (block + 1) * n / blocks);

            long offset = offsets[block];

            for (int i = start; i < end; i++) {
                prefix[i + 1] += offset;
            }
        });

        return prefix;
    }

    // Java 17 library inclusive scan, adapted to P[0]=0.
    static long[] libraryPrefix(int[] input) {
        Objects.requireNonNull(input, "input");

        long[] inclusive = new long[input.length];

        for (int i = 0; i < input.length; i++) {
            inclusive[i] = input[i];
        }

        Arrays.parallelPrefix(inclusive, Long::sum);

        long[] result = new long[input.length + 1];
        System.arraycopy(
                inclusive, 0, result, 1, input.length);

        return result;
    }

    static void show(
            String label, int[] input, int blocks) {

        int[] original = input.clone();
        long[] expected = sequentialPrefix(input);
        long[] blelloch = blellochPrefix(input);
        long[] blocked = blockedPrefix(input, blocks);
        long[] library = libraryPrefix(input);
        long[] hillis = hillisSteeleInclusive(input);

        long[] hillisAsPrefix =
                new long[input.length + 1];

        System.arraycopy(
                hillis, 0, hillisAsPrefix, 1, hillis.length);

        if (!Arrays.equals(expected, blelloch)
                || !Arrays.equals(expected, blocked)
                || !Arrays.equals(expected, library)
                || !Arrays.equals(expected, hillisAsPrefix)) {
            throw new AssertionError(
                    "Scan mismatch: " + label);
        }

        if (!Arrays.equals(input, original)) {
            throw new AssertionError(
                    "Input array was modified");
        }

        System.out.println(
                label + " blocks=" + blocks
                + ": prefix=" + Arrays.toString(expected)
                + ", total=" + expected[input.length]);
    }

    public static void main(String[] args) {

        int[] base = {3, -2, 5, 7, 0, -4};

        show("Base", base, 3);
        show("Empty", new int[] {}, 2);
        show("Single", new int[] {7}, 4);
        show("Zeros", new int[] {0, 0, 0, 0}, 3);
        show("Extremes", new int[] {
                Integer.MAX_VALUE,
                Integer.MAX_VALUE,
                Integer.MIN_VALUE,
                1
        }, 3);
        show("Odd", new int[] {5, -3, 4, 1, 9}, 2);
        show("PowerTwo", new int[] {
                6, -1, 2, 5, 0, -3, 4, 7
        }, 4);

        long[] prefix = blockedPrefix(base, 3);
        System.out.println(
                "Base range [1,5): "
                + (prefix[5] - prefix[1]));

        System.out.println(
                "All four scan methods match "
                + "the sequential oracle.");
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 ParallelScanDemo.java
java ParallelScanDemo
~~~

**Đầu ra chính xác dự kiến:**

~~~text
Base blocks=3: prefix=[0, 3, 1, 6, 13, 13, 9], total=9
Empty blocks=2: prefix=[0], total=0
Single blocks=4: prefix=[0, 7], total=7
Zeros blocks=3: prefix=[0, 0, 0, 0, 0], total=0
Extremes blocks=3: prefix=[0, 2147483647, 4294967294, 2147483646, 2147483647], total=2147483647
Odd blocks=2: prefix=[0, 5, 2, 6, 7, 16], total=16
PowerTwo blocks=4: prefix=[0, 6, 5, 7, 12, 12, 9, 13, 20], total=20
Base range [1,5): 10
All four scan methods match the sequential oracle.
~~~

### Lý do chọn cấu trúc code này

**Hillis–Steele** được triển khai bằng mảng mới ở từng pha để tránh đọc/ghi chéo và làm rõ O(n log n) work.

**Blelloch** dùng mảng long đã padding và các groups không giao nhau trong từng mức. Khi n=0, kết quả là [0]. Khi n>0, P[n] được khôi phục từ exclusive prefix và phần tử cuối.

**Blocked** không sao chép toàn dãy theo mỗi pha. Các khối ghi các đoạn riêng của prefix; bước offset chạy một vòng p khối tuần tự, nên phần giới hạn span là O(n/p+p), không giả là O(n/p+log p).

**Arrays.parallelPrefix** nhận long[] và toán tử Long::sum, tránh tràn int trong chuỗi mẫu.

**show** đối chiếu cả bốn phương án với oracle tuần tự và kiểm tra mảng input không bị thay đổi.

### Không nhầm demo với một benchmark

Ví dụ đo tính đúng, không dùng các mảng chỉ vài phần tử để kết luận speedup. Java parallel stream và ForkJoinPool có overhead đáng kể với input nhỏ. Muốn đo performance cần dùng benchmark riêng với warmup, mảng lớn, nhiều lần lặp và số worker thích hợp.

## 25. Kiểm chứng từng biến thể bằng oracle độc lập

Oracle đáng tin nhất cho prefix tổng số nguyên trên mảng nhỏ là vòng lặp:

~~~text
P[0] = 0
for i = 0 .. n-1:
    P[i+1] = P[i] + a[i]
~~~

Khi kiểm thử parallel scan, không chỉ so hai thuật toán tree với nhau vì chúng có thể cùng mắc lỗi indexing.

Các phép so:

- **Hillis inclusive[i] == P[i+1]**.
- **Blelloch fullPrefix[i] == P[i]** cho i=0..n.
- **Blocked fullPrefix[i] == P[i]** cho i=0..n.
- **Arrays.parallelPrefix inclusive[i] == P[i+1]**.
- **Input array không đổi** nếu API wrapper cam kết không mutate.
- **Range sum P[r]−P[l]** bằng tổng trực tiếp qua [l,r).

### Test quan trọng

1. n=0, output [0].
2. n=1, ví dụ [7] → [0,7].
3. n=2,4,8,16 đúng lũy thừa hai.
4. n=3,5,6,7,9 chưa phải lũy thừa hai — kiểm tra padding.
5. Toàn số 0.
6. Toàn số âm.
7. Mixed signs.
8. Giá trị Integer.MIN_VALUE và Integer.MAX_VALUE.
9. Một phần tử cực trị ở cuối.
10. Requested blocks lớn hơn n.
11. Requested blocks bằng 1.
12. n nhỏ hơn số worker có sẵn.
13. Chia n cho p có dư.
14. Một số khối có kích thước khác khối kế.
15. Cùng một mảng với nhiều giá trị p khác nhau.
16. Truy vấn đoạn rỗng, toàn mảng và một phần tử.

Không thể khẳng định code thread-safe chỉ vì random tests chạy đúng; điều kiện ghi disjoint, dữ liệu chỉ đọc giữa barrier và thứ tự phases phải được chứng minh độc lập.

## 26. Bất biến cụ thể của Hillis và Blelloch

**Hillis–Steele** sau pha với offset 2^d:

Mỗi X[i] là tổng của tối đa **2^{d+1} phần tử gần nhất kết thúc ở i**. Khi số phần tử được bao phủ ≥n, đó là inclusive prefix.

**Blelloch upsweep**:

Sau mức với groupSize g, ô đại diện nhóm chứa tổng của **g phần tử tương ứng**. Các nhóm không chồng lấp ở cùng mức.

**Blelloch downsweep**:

Trước khi xử lý một nhóm, node root của nhóm chứa tổng của **mọi phần tử đứng trước nhóm**. Con trái nhận nguyên prefix ấy; con phải nhận prefix ấy cộng tổng đoạn con trái.

**Blocked**:

- Local scan đúng trong từng khối.
- Offset[b] bằng tổng của tất cả block đứng trước b.
- Sau fix-up, mỗi phần tử nhận tổng toàn bộ phần tử trước hoặc bằng nó.

Viết các bất biến này giúp tách lỗi tính toán khỏi lỗi lập lịch khi triển khai parallel scan trên môi trường khác Java.

## 27. Cách đánh giá performance công bằng

Muốn so sequentialPrefix với các biến thể song song:

1. Dùng **cùng dữ liệu** cho mọi thuật toán.
2. Tách chi phí **cấp phát, copy input, padding** nếu muốn đo riêng kernel; hoặc tính chúng nhất quán nếu so API end-to-end.
3. Chạy JVM warm-up trước đo; với công việc Java đáng kể, cân nhắc benchmark framework như JMH.
4. Đo nhiều lần, báo phân phối thời gian thay vì một số duy nhất.
5. Tránh đo cả lúc JVM đang bị các tác vụ khác chiếm hết cores.
6. Thử n từ rất nhỏ đến rất lớn, gồm n không là lũy thừa hai.
7. Ghi số core, tình trạng CPU load, heap/GC và memory bandwidth.
8. Tránh chạy nhiều benchmark song song tự cạnh tranh băng thông.
9. Kiểm tra kết quả với oracle **trước** khi tối ưu.
10. Phân biệt thông số **work/span lý thuyết** với throughput đo được.

### Điều gì có thể xảy ra?

Với n=100, vòng for tuần tự có thể thắng mọi cách parallel vì overhead.

Với n lớn, blocked scan có thể có locality tốt và tránh tạo mảng mới qua nhiều phases.

Blelloch đạt work-efficient về mặt phép toán nhưng triển khai parallel stream theo mỗi mức có thể phát sinh overhead; một implementation tối ưu có thể dùng chunk-level parallelism và phân phối offsets khác.

### Không đánh đồng tốc độ với số luồng

Thêm threads không làm phép cộng nhanh hơn nếu workload đã memory-bandwidth-bound. Speedup có thể bão hòa trước khi dùng hết cores.

## 28. Các lỗi lập trình song song phổ biến

1. **Đổi vòng for prefix tuần tự thành parallel forEach trực tiếp**, tạo dependency race.
2. **Cập nhật Hillis–Steele in-place trong cùng pha** mà không bảo đảm đọc snapshot old.
3. **Không chờ tất cả workers của một pha**, mức sau đọc dữ liệu chưa hoàn tất.
4. **Cho hai nhóm Blelloch ghi cùng một vị trí**, không còn disjoint.
5. **Nhầm inclusive với exclusive**, làm lệch mọi chỉ số.
6. **Quên identity=0 cho phép cộng**, khiến padding làm hỏng total.
7. **Padding bằng phần tử bất kỳ thay vì identity**, làm sai root total.
8. **Không xử lý n=0**, đọc tree[-1] hoặc dùng log₂0.
9. **Không xử lý n=1**, thực hiện downsweep sai.
10. **Cắt bỏ padding nhưng quên P[n]**, thiếu tổng toàn bộ input.
11. **Không dùng kiểu long**, tổng int có thể overflow.
12. **Cho rằng long không bao giờ overflow với mọi input long[]**, không đúng.
13. **Dùng toán tử không kết hợp**, kết quả thay đổi theo cây.
14. **Dùng double rồi đòi bitwise identical với kết quả cộng tuần tự**, bỏ roundoff.
15. **Nhầm work với span**, quảng cáo O(log n) tổng phép cộng cho Blelloch.
16. **Gọi Hillis–Steele O(n) work**, thực tế O(n log n).
17. **Cho rằng blocked scan với offsets tuần tự có span O(log p)**, thực tế có đoạn O(p).
18. **Chọn p=n với offset scan tuần tự**, tạo nút cổ chai O(n).
19. **Coi mọi parallel stream đều chạy đồng thời trên n lõi**, không đúng.
20. **Benchmark mảng quá nhỏ rồi kết luận parallel scan vô ích ở mọi cỡ**, thiếu dữ liệu lớn.
21. **Benchmark mảng quá lớn nhưng không tính GC/padding**, so không công bằng.
22. **Giữ reference vào input và sửa input ngoài luồng khi scan đang chạy**, dữ liệu cạnh tranh.
23. **Ghi đè input bằng Arrays.parallelPrefix dù caller muốn immutable**, vi phạm API contract.
24. **Gộp đoạn theo thứ tự phải→trái với toán tử không giao hoán**, phá ngữ nghĩa.
25. **Scan nội bộ các block nhưng không cộng offsets**, chỉ có local prefixes.
26. **Cộng sai offsets vào cả P[0]**, làm đoạn đầu không còn 0.
27. **Tính start/end block bằng int multiplication có thể overflow**, nên tính trung gian long.
28. **Giả sử n chia hết p**, bỏ đuôi hoặc ghi ngoài mảng.
29. **Gọi local prefix inclusive nhưng xử lý như exclusive**, lệch một vị trí.
30. **Nhầm offset của block b với chính blockSum[b]**, phải dùng tổng các block trước b.
31. **Dùng scan số thực mà không quan tâm tính ổn định số**, có thể gây sai số lớn khi hiệu hai prefix gần nhau.
32. **Không kiểm tra tính đúng cho n không là lũy thừa hai**, bỏ bug padding.
33. **Không kiểm tra extremes int**, phát sinh lỗi dấu.
34. **Nhầm parallel scan với parallel reduction**, reduction chỉ trả tổng một giá trị, scan trả mọi tiền tố.
35. **Cho rằng mọi range query sau khi scan tĩnh vẫn đúng nếu dữ liệu cập nhật**, prefix cũ là snapshot.
36. **Tự áp dụng kết quả GPU work/span cho Java CPU**, bỏ layout/barriers/overhead.
37. **Cho rằng mọi phép loại trừ phần tử khỏi tổng quát monoid đều có inverse**, monoid không bắt buộc có phép nghịch đảo.
38. **Dùng exclusive scan nhưng muốn stream compaction mà không lưu số phần tử cuối**, không biết output size.
39. **Dùng segmented scan không reset ở head flag**, nối nhầm hai nhóm.
40. **Tối ưu tốc độ trước khi kiểm chứng bất biến**, dẫn tới code nhanh nhưng sai ngẫu nhiên.
41. **Đếm thời gian toàn bộ chương trình in stdout như thời gian scan**, bị I/O console chi phối.
42. **Không tách độ phức tạp CPU và băng thông RAM**, giải thích speedup sai.

## 29. Bài tập tự luyện kèm đáp án

**Bài 1.** Với a=[3,−2,5,7,0,−4], inclusive scan là gì?  
**Đáp án:** [3,1,6,13,13,9].

**Bài 2.** Exclusive scan của dãy ấy?  
**Đáp án:** [0,3,1,6,13,13].

**Bài 3.** Full prefix P độ dài n+1?  
**Đáp án:** [0,3,1,6,13,13,9].

**Bài 4.** Tổng [1,5)?  
**Đáp án:** P[5]−P[1]=13−3=10.

**Bài 5.** Tại sao không đơn giản parallelize vòng lặp P[i+1]=P[i]+a[i]?  
**Đáp án:** Iteration i+1 phụ thuộc giá trị được iteration i tính, tạo data race nếu chạy tùy ý.

**Bài 6.** Hillis–Steele dùng các offset nào với n=6?  
**Đáp án:** 1,2,4.

**Bài 7.** Hillis–Steele có work và ideal span thế nào?  
**Đáp án:** Work O(n log n), span O(log n).

**Bài 8.** Với n=8, Hillis–Steele có bao nhiêu phép cộng theo các offset?  
**Đáp án:** 7+6+4=17, không tính copy.

**Bài 9.** Blelloch có hai pha nào?  
**Đáp án:** Upsweep (reduce) và downsweep (distribute exclusive prefixes).

**Bài 10.** Blelloch có work và ideal span thế nào?  
**Đáp án:** Work O(n), span O(log n).

**Bài 11.** Khi upsweep kết thúc, root giữ gì?  
**Đáp án:** Tổng của tất cả phần tử sau padding với identity.

**Bài 12.** Tại sao đặt root=0 trước downsweep?  
**Đáp án:** Prefix đứng trước toàn bộ dãy là empty sum, bằng 0.

**Bài 13.** Tại sao padding n=6 lên 8 bằng 0 không đổi tổng?  
**Đáp án:** 0 là identity của phép cộng.

**Bài 14.** Với n=0, full prefix nên là gì?  
**Đáp án:** [0].

**Bài 15.** Với n=1,a=[7], full prefix là gì?  
**Đáp án:** [0,7].

**Bài 16.** Blocked scan gồm những bước nào?  
**Đáp án:** Local scans, scan block totals để lấy offsets, fix-up mỗi block.

**Bài 17.** Có p blocks, offsets tính tuần tự, ideal critical time?  
**Đáp án:** O(n/p+p) khi p worker xử lý các blocks tương đối đều.

**Bài 18.** Nếu parallelize scan block totals work-efficient, lý tưởng có thể có critical time?  
**Đáp án:** O(n/p+log p), với giả thiết tài nguyên và scheduling phù hợp.

**Bài 19.** Arrays.parallelPrefix trả inclusive hay exclusive?  
**Đáp án:** Inclusive.

**Bài 20.** Java Long::sum có cần commutative để scan đúng?  
**Đáp án:** Monoid tổng không cần commutativity cho scan nói chung, chỉ cần associativity và identity; phép cộng số nguyên đồng thời commutative.

**Bài 21.** Toán tử nối chuỗi có dùng scan được không?  
**Đáp án:** Có, vì kết hợp và có identity chuỗi rỗng, nhưng phải giữ thứ tự.

**Bài 22.** Floating-point scan có nhất thiết bitwise giống tuần tự?  
**Đáp án:** Không, do cách đặt ngoặc/phép làm tròn.

**Bài 23.** Stream compaction của [4,−1,0,7,−3,2] giữ số dương cho kết quả?  
**Đáp án:** [4,7,2].

**Bài 24.** Flags [1,0,0,1,0,1] có exclusive scan nào?  
**Đáp án:** [0,1,1,1,2,2].

**Bài 25.** Với radix stable binary partition, oneBefore(i) lấy từ đâu?  
**Đáp án:** Exclusive scan của bit flags.

**Bài 26.** Segmented inclusive scan của [3,−2,5 | 7,0 | −4]?  
**Đáp án:** [3,1,6 | 7,7 | −4].

**Bài 27.** Tại sao parallel scan có thể không nhanh hơn tuần tự với n=100?  
**Đáp án:** Scheduling/barriers/allocation overhead có thể lớn hơn công việc cộng.

**Bài 28.** Nếu input có giá trị Integer.MAX_VALUE lặp, nên dùng prefix kiểu nào?  
**Đáp án:** long nếu bound tổng vẫn trong miền long.

**Bài 29.** Parallel scan có tự giải quyết point updates cho prefix tĩnh không?  
**Đáp án:** Không; cần rebuild hoặc cấu trúc cập nhật động.

**Bài 30.** Nếu dùng query đoạn [l,r), công thức tổng sau scan là gì?  
**Đáp án:** P[r]−P[l].

## 30. Checklist triển khai và kết luận

Trước khi sử dụng parallel scan trong Java hoặc môi trường song song khác:

1. **Xác định inclusive hay exclusive**, không nhập nhằng chỉ số.
2. **Định nghĩa toán tử có tính kết hợp** và phần tử đơn vị.
3. **Giữ đúng thứ tự trái→phải** nếu toán tử không giao hoán.
4. **Chọn kiểu dữ liệu đủ lớn**, phân biệt integer exact và floating-point rounded.
5. **Nêu work và span riêng**, không gọi O(log n) span là O(log n) tổng work.
6. **Hillis–Steele phải đọc snapshot pha trước**, không sửa in-place vô rào chắn.
7. **Blelloch phải upsweep đúng, root=identity, downsweep đúng**.
8. **Padding bằng identity**, cắt bỏ các lá đệm khỏi kết quả cuối.
9. **Xử lý n=0,n=1 và n không là lũy thừa hai**.
10. **Phân chia các nhóm không chồng lấp ở từng level**, tránh race.
11. **Chờ xong level trước khi chạy level mới**.
12. **Nếu blocked, tính offsets bằng exclusive scan của block totals**, không lấy nhầm tổng block hiện tại.
13. **Phân tích span O(n/p+p) nếu offsets tính tuần tự**, không quảng cáo O(n/p+log p).
14. **Chọn p không quá lớn so với n và số worker**, tránh overhead.
15. **Nếu dùng Arrays.parallelPrefix, copy input khi cần immutability**.
16. **Kiểm chứng với oracle tuần tự và nhiều kích thước**, đặc biệt các biên.
17. **So sum(l,r) với direct scan**, không chỉ so hai implementation prefix.
18. **Kiểm tra stream compaction/segmented scan với head flags**, nếu bài ứng dụng cần.
19. **Đo throughput và latency thực**, không suy speedup chỉ từ số lõi.
20. **Theo dõi memory bandwidth, GC và task synchronization**.
21. **Tránh đọc/ghi đồng thời vào cùng dữ liệu đang được sử dụng làm input snapshot**.
22. **Chọn API thư viện ổn định khi production phù hợp**, dùng code minh họa để học thuật toán.
23. **Xem xét layout/blocking khi chuyển CPU sang GPU**, không áp dụng thẳng chi phí.
24. **Xác nhận đúng version dữ liệu nếu có updates**, scan trả prefix của một snapshot.

**Kết luận:** parallel scan là một ví dụ tiêu biểu về việc **thay đổi cấu trúc phụ thuộc** để biến một phép tính tiền tố tưởng như tuần tự thành công việc có thể phân phối. Hillis–Steele đơn giản với O(log n) pha nhưng trả giá O(n log n) work; Blelloch dùng upsweep/downsweep để đạt **O(n) work và O(log n) span** trong mô hình song song lý tưởng. Blocked scan và Arrays.parallelPrefix giúp kết nối ý tưởng với CPU Java thực tế. Hiểu đúng work/span, barrier, inclusive/exclusive và đặc tính toán tử là nền tảng để sử dụng scan an toàn trong truy vấn, xử lý dữ liệu, stream compaction, radix sort và pipeline song song.
