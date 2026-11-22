# Thuật toán Mo và chi phí di chuyển hai biên

**Thuật toán Mo (Mo's algorithm)** là một kỹ thuật **xử lý truy vấn đoạn ngoại tuyến** trên mảng, rất hữu ích khi các truy vấn hỏi một đại lượng của đoạn nhưng không có công thức tiền tố đơn giản để trả lời ngay. Thay vì tính lại từ đầu cho từng đoạn, Mo **sắp xếp lại thứ tự truy vấn** để hai biên của một cửa sổ hiện hành di chuyển ít hơn, và duy trì lời giải bằng các thao tác **thêm/bỏ một phần tử**.

Ví dụ: cho mảng có số âm, số trùng và q truy vấn **đếm số giá trị phân biệt** trong [l,r). Đếm trực tiếp từng đoạn có thể tốn O(qn). Mo có thể dùng một mảng tần suất, cho phép thêm hoặc bỏ một phần tử O(1), và sắp xếp truy vấn theo các khối của biên trái để giảm tổng số lần cập nhật cửa sổ. Với kích thước khối B≈√n và phép thêm/bỏ O(1), một cận thời gian điển hình là:

**O(n log n + q log q + qB + n⌈n/B⌉ + n)**,

trong đó **n log n** xuất hiện ở ví dụ cần nén giá trị bằng sắp xếp; nếu đầu vào đã có giá trị trong miền nhỏ thì có thể không cần bước ấy. Khi B≈√n, thành phần di chuyển thường được mô tả là **O((n+q)√n)**; chi phí sắp xếp truy vấn là **O(q log q)**.

Điều quan trọng: **Mo không làm một truy vấn độc lập thành O(1)**. Sau khi đã có trạng thái cửa sổ phù hợp, ta có thể **đọc đáp án hiện tại O(1)**, nhưng **di chuyển cửa sổ từ truy vấn trước tới truy vấn sau có chi phí**. Chính tổng chi phí di chuyển hai biên là cốt lõi của thuật toán.

Bài thuộc nhóm **Truy vấn và ngoại tuyến**. Nội dung bao gồm định nghĩa truy vấn tĩnh, bất biến cửa sổ [L,R), bốn vòng lặp add/remove, cách chia khối và sắp xếp lẻ–chẵn, chứng minh cận di chuyển trái/phải, vai trò của kích thước khối B, truy vấn rỗng, nén tọa độ, các hàm tổng hợp phù hợp, so sánh với prefix sum/Fenwick và thuật toán ngoại tuyến khác, mã **Java 17+ chạy độc lập** kèm **đầu ra mẫu chính xác**, cùng kiểm thử bằng oracle vét cạn.

## 1. Đặc tả bài toán và điều kiện ngoại tuyến

Cho mảng tĩnh **a[0..n−1]** và q truy vấn. Truy vấn thứ i hỏi một hàm trên đoạn:

**[lᵢ,rᵢ)**, với **0≤lᵢ≤rᵢ≤n**.

Trong bài ví dụ, câu hỏi là:

**distinct(l,r)=số giá trị khác nhau xuất hiện trong a[l],...,a[r−1]**.

Các truy vấn có thể được **đưa vào trước khi xử lý** và đáp án được trả lại theo **thứ tự ban đầu**. Đây là điều kiện quan trọng cho kỹ thuật offline.

Ví dụ:

~~~text
a = [4, -1, 4, 2, 2, -1, 3, 4, -5, 3, 0, 0]

Q0 = [0,12) -> 6 giá trị khác nhau
Q1 = [0, 4) -> 3 giá trị khác nhau
Q2 = [2, 9) -> 5 giá trị khác nhau
Q3 = [4, 8) -> 4 giá trị khác nhau
Q4 = [5, 5) -> 0 (đoạn rỗng)
~~~

Đầu ra phải tương ứng với các nhãn **Q0,Q1,...**, dù Mo **thực hiện Q1 trước Q0** hoặc theo thứ tự khác.

### Tại sao yêu cầu mảng tĩnh?

Mo cơ bản giả định mọi truy vấn đọc **cùng một phiên bản mảng**. Nếu có cập nhật chen giữa các truy vấn, việc tự đổi thứ tự query có thể làm thay đổi trạng thái dữ liệu mà truy vấn phải nhìn thấy. Khi ấy cần thuật toán khác hoặc **Mo with modifications** duy trì thêm trục thời gian.

### Mo là một kỹ thuật sắp xếp, không phải cấu trúc dữ liệu đơn lẻ

Mo không định nghĩa sẵn lời giải cho mọi hàm đoạn. Người triển khai cần tự cung cấp:

- **add(pos):** thêm a[pos] vào cửa sổ.
- **remove(pos):** bỏ a[pos] khỏi cửa sổ.
- **answer():** đọc đại lượng đang duy trì.

Độ phức tạp thực tế còn tùy **chi phí ba thao tác này**.

## 2. Vì sao duyệt trực tiếp thường chậm?

Với một truy vấn [l,r), ta có thể đưa các phần tử a[l..r−1] vào HashSet để đếm giá trị phân biệt:

~~~text
distinct_naive(a,l,r):
    seen = empty set
    for i = l .. r-1:
        seen.add(a[i])
    return seen.size()
~~~

Giả sử thao tác hash O(1) kỳ vọng:

**T_query=O(r−l)**.

Nếu có q truy vấn dài gần n, tổng chi phí có thể là:

**O(qn)**.

Ví dụ n=q=100000, việc quét lại gần 100000 phần tử cho từng truy vấn có thể dẫn tới hàng tỷ lần xử lý.

### Không thể lấy hiệu hai prefix distinct

Với tổng, có công thức:

**sum(l,r)=P[r]−P[l]**.

Nhưng nếu đặt **D[k]=số giá trị phân biệt trong [0,k)**, thì:

**distinct(l,r) ≠ D[r]−D[l]** nói chung.

Ví dụ:

~~~text
a = [7, 7, 8]

D = [0, 1, 1, 2]
distinct([1,3)) = 2
D[3] - D[1] = 2 - 1 = 1
~~~

Khi cắt bỏ đoạn đầu, những giá trị vừa có ở đoạn đầu vừa có ở đoạn còn lại không thể được xử lý bằng phép trừ đơn giản. Đây là lý do dùng kỹ thuật duy trì tần suất hoặc một cấu trúc offline khác.

## 3. Cửa sổ hiện tại là đoạn nửa mở [L,R)

Mo duy trì hai biến nguyên:

**L** = biên trái hiện tại.

**R** = biên phải **loại trừ** hiện tại.

Các phần tử đang nằm trong cửa sổ là:

**a[L],a[L+1],...,a[R−1]**.

Bất biến chỉ số:

**0≤L≤R≤n**.

Khởi tạo:

**L=0, R=0**,

tức cửa sổ rỗng.

Sau khi xử lý truy vấn [l,r), thuật toán cần đưa:

**L=l, R=r**,

và trạng thái thống kê phải đại diện **đúng** các phần tử của đoạn ấy.

### Tại sao dùng [L,R) thay vì [L,R]?

- Đoạn rỗng thể hiện tự nhiên bằng L=R.
- Kích thước cửa sổ là R−L.
- Một phần tử tại i là [i,i+1).
- Cập nhật R++ thêm đúng a[R] cũ.
- Cập nhật --R rồi bỏ a[R] mới bỏ đúng phần tử cuối trước đó.

Dùng đoạn đóng cũng được nếu cài đặt nhất quán; tuy nhiên trong Java, [L,R) thường giảm lỗi off-by-one.

## 4. Bốn phép di chuyển biên

Để biến cửa sổ [L,R) thành [l,r), một thứ tự an toàn là:

~~~text
while L > l:
    L = L - 1
    add(L)

while R < r:
    add(R)
    R = R + 1

while L < l:
    remove(L)
    L = L + 1

while R > r:
    R = R - 1
    remove(R)
~~~

Sau bốn vòng lặp:

**L=l và R=r**.

### Tại sao thứ tự này quan trọng?

Mở rộng trái và mở rộng phải **trước**, sau đó mới thu hẹp trái/phải, giúp giữ cửa sổ hợp lệ trên cả truy vấn rỗng hoặc các đoạn xa nhau.

Giả sử cửa sổ hiện tại [0,2), truy vấn kế là [5,5). Nếu thu hẹp trái ngay từ L=0 tới 5 mà R vẫn là 2, ta có thể gọi remove trên a[2],a[3],a[4] vốn không nằm trong cửa sổ. Thứ tự an toàn sẽ **mở rộng R tới 5 trước**, rồi bỏ lần lượt a[0..4].

**Chỉ thay biến L/R mà không gọi add/remove tương ứng là sai.** Trạng thái thống kê sẽ không còn phản ánh cửa sổ hiện tại.

## 5. Bất biến của thao tác add/remove

Trong bài đếm distinct, sau mọi bước, đặt:

**freq[v] = số lần giá trị v xuất hiện trong cửa sổ [L,R)**.

Và:

**distinct = số giá trị v có freq[v]>0**.

Khi thêm phần tử x:

~~~text
if freq[x] == 0:
    distinct++
freq[x]++
~~~

Khi bỏ phần tử x:

~~~text
freq[x]--
if freq[x] == 0:
    distinct--
~~~

Điều kiện tiên quyết của remove:

**freq[x]>0 trước phép trừ**,

vì chỉ được remove một phần tử đang thuộc cửa sổ.

### Ví dụ có phần tử trùng

Với cửa sổ chứa [4,−1,4]:

- freq[4]=2.
- freq[−1]=1.
- distinct=2.

Bỏ một số 4 còn freq[4]=1, **distinct vẫn là 2**.

Bỏ tiếp số 4 làm freq[4]=0, khi ấy **distinct giảm thành 1**.

**Không được tăng distinct mỗi khi add hoặc giảm distinct mỗi khi remove**, vì hai thao tác có thể thêm/bỏ bản sao của một giá trị đã tồn tại.

## 6. Khi dữ liệu âm hoặc rất lớn: nén tọa độ

Một mảng tần suất đơn giản:

~~~text
freq[value]
~~~

chỉ hợp lý nếu value nằm trong miền chỉ số nhỏ, không âm và đã biết.

Nhưng a[i] có thể bằng:

- −1 hoặc Integer.MIN_VALUE.
- Integer.MAX_VALUE.
- Hàng tỷ giá trị khác nhau với khoảng trống rất lớn.

Không thể cấp một mảng freq có chỉ số trực tiếp từ −2³¹ tới 2³¹−1.

### Coordinate compression

1. Sao chép và sắp xếp các giá trị của a.
2. Loại bản sao, tạo mảng **unique** gồm các giá trị phân biệt theo thứ tự tăng.
3. Mỗi giá trị a[i] được đổi thành **rank** từ 0 tới d−1, với d là số giá trị phân biệt toàn mảng.
4. Dùng **freq[rank]**, chỉ cần d ô.

Ví dụ:

~~~text
a      = [4, -1, 4, 2, -1]
unique = [-1, 2, 4]
rank   = [ 2, 0, 2, 1,  0]
~~~

Hai phần tử bằng nhau có cùng rank; các phần tử khác nhau có rank khác nhau. Do đó đếm số rank có tần suất dương **tương đương** đếm số giá trị gốc khác nhau.

### Chi phí

Với n số int:

- Sắp xếp: O(n log n).
- Tạo unique: O(n).
- Binary search để tìm rank cho mỗi phần tử: O(n log n).
- Bộ nhớ O(n).

Nếu input đã có miền nhỏ, có thể bỏ nén và cấp freq trực tiếp. Nếu dùng HashMap để lưu tần suất, có thể tránh bước sắp xếp nén nhưng đổi lại overhead, chi phí hashing và đặc tính bộ nhớ khác.

## 7. Vì sao đổi thứ tự truy vấn có thể tiết kiệm?

Nếu trả theo đúng thứ tự input, hai biên L,R có thể phải di chuyển qua lại gần như toàn bộ mảng nhiều lần.

Ví dụ các truy vấn xen kẽ:

~~~text
[0,n)
[n-1,n)
[0,n)
[n-1,n)
...
~~~

Trên mỗi cặp, biên trái có thể phải dịch gần n bước. Với q truy vấn, **chi phí di chuyển có thể Θ(qn)**.

Mo sắp xếp query theo một trật tự giúp giảm tổng quãng đường. Ý tưởng cổ điển:

1. Chia các chỉ số trái thành các **khối liên tiếp kích thước B**.
2. Sắp các truy vấn theo khối chứa l.
3. Trong cùng một khối, sắp theo r.

Nhờ đó L chỉ dao động trong vùng hẹp của một khối, còn R di chuyển tương đối có kiểm soát giữa các truy vấn của khối đó.

### Quan trọng: việc sắp xếp không đổi bài toán

Mo chỉ **đổi thứ tự tính toán**. Sau khi tính mỗi query, đáp án được ghi vào **answer[originalId]**.

Người dùng vẫn nhận kết quả theo đúng thứ tự mà họ gửi.

## 8. Chia khối theo biên trái

Chọn kích thước khối **B≥1**.

Với query [l,r), đặt:

**block(l)=floor(l/B)**.

Các vị trí:

- 0..B−1 thuộc khối 0.
- B..2B−1 thuộc khối 1.
- 2B..3B−1 thuộc khối 2.
- Và tiếp tục đến hết n.

Ta thường chọn:

**B≈floor(√n)**

để cân bằng hai loại di chuyển khi q tương đương n.

### Truy vấn rỗng ở cuối dãy

Với quy ước [l,r), [n,n) là một đoạn rỗng **hợp lệ**. Khi đó l=n có thể được gán vào một khối biên mới theo floor(n/B). Không có vấn đề về truy cập a[n] nếu các vòng lặp chỉ gọi add/remove trên phần tử thực sự thuộc cửa sổ.

### Trường hợp n=0

B phải giữ **ít nhất 1**, tránh phép chia cho B=0. Mọi truy vấn hợp lệ trên mảng rỗng chỉ có thể là [0,0).

Một cách chọn an toàn:

**B=max(1,floor(sqrt(max(1,n))))**.

## 9. Cách sắp xếp chuẩn và biến thể lẻ–chẵn

Cách chuẩn:

~~~text
Compare queries A,B:
    blockA = A.l / B
    blockB = B.l / B

    if blockA != blockB:
        sort by block increasing
    else:
        sort by r increasing
~~~

Trong pseudocode, ký hiệu B vừa có thể gây trùng tên **query B** và **block size B**; trong code thực nên đặt tên rõ **q1,q2,blockSize** để tránh mơ hồ.

### Biến thể odd–even

Một tối ưu thường dùng:

- Khối trái **chẵn**: sort r **tăng dần**.
- Khối trái **lẻ**: sort r **giảm dần**.

Ví dụ:

~~~text
Block 0: r small -> large
Block 1: r large -> small
Block 2: r small -> large
Block 3: r large -> small
~~~

Khi chuyển từ khối này sang khối kế, hướng quét r tiếp tục gần vị trí r hiện tại, thường giảm số bước nhảy lớn của R.

### Không đổi cận tiệm cận cơ bản

Odd–even sorting thường cải thiện **hằng số thực thi**, không tự chuyển Mo thành O(q) truy vấn. Trong phân tích worst-case, R vẫn có thể di chuyển O(n) trong mỗi khối và còn chi phí chuyển khối.

### Tie-break

Nếu hai truy vấn có cùng block và r, có thể so thêm **id gốc** để có thứ tự xác định. Điều này giúp kiểm thử log và sample output khớp qua các lần chạy.

## 10. Ví dụ sắp xếp 11 truy vấn với B=3

Xét mảng dài n=12:

~~~text
a = [4, -1, 4, 2, 2, -1, 3, 4, -5, 3, 0, 0]
B = 3
~~~

Các truy vấn theo thứ tự gốc:

| ID | Đoạn [l,r) | Distinct đúng |
| --- | --- | ---: |
| Q0 | [0,12) | 6 |
| Q1 | [0,4) | 3 |
| Q2 | [2,9) | 5 |
| Q3 | [4,8) | 4 |
| Q4 | [5,5) | 0 |
| Q5 | [8,12) | 3 |
| Q6 | [10,12) | 1 |
| Q7 | [12,12) | 0 |
| Q8 | [1,11) | 6 |
| Q9 | [3,7) | 3 |
| Q10 | [7,11) | 4 |

Theo sắp xếp **khối trái tăng, r tăng với khối chẵn và giảm với khối lẻ**, thứ tự xử lý là:

**Q1, Q2, Q8, Q0, Q3, Q9, Q4, Q10, Q5, Q6, Q7**.

Mảng ID đã sắp:

~~~text
[1, 2, 8, 0, 3, 9, 4, 10, 5, 6, 7]
~~~

Đáp án khi trả cho người dùng vẫn là thứ tự **Q0..Q10**:

~~~text
[6, 3, 5, 4, 0, 3, 1, 0, 6, 3, 4]
~~~

### Tại sao không in theo thứ tự đã sắp?

Nếu in lần lượt những giá trị khi duyệt sorted queries, giá trị thứ nhất sẽ là đáp án **Q1**, không phải **Q0**. API nhận danh sách query và trả một mảng answer phải dùng **answer[id]** để bảo toàn ngữ nghĩa.

## 11. Bảng chi tiết chi phí di chuyển hai biên

Khởi đầu L=0,R=0. Mỗi dòng đưa cửa sổ hiện tại về đoạn của query tiếp theo. Trong thứ tự điều khiển bốn vòng lặp ở mục 4, số bước di chuyển L và R bằng trị tuyệt đối của thay đổi hai biên giữa các query liên tiếp.

| Query xử lý | Đoạn đích | L sau | R sau | Bước L | Bước R | Distinct |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Q1 | [0,4) | 0 | 4 | 0 | 4 | 3 |
| Q2 | [2,9) | 2 | 9 | 2 | 5 | 5 |
| Q8 | [1,11) | 1 | 11 | 1 | 2 | 6 |
| Q0 | [0,12) | 0 | 12 | 1 | 1 | 6 |
| Q3 | [4,8) | 4 | 8 | 4 | 4 | 4 |
| Q9 | [3,7) | 3 | 7 | 1 | 1 | 3 |
| Q4 | [5,5) | 5 | 5 | 2 | 2 | 0 |
| Q10 | [7,11) | 7 | 11 | 2 | 6 | 4 |
| Q5 | [8,12) | 8 | 12 | 1 | 1 | 3 |
| Q6 | [10,12) | 10 | 12 | 2 | 0 | 1 |
| Q7 | [12,12) | 12 | 12 | 2 | 0 | 0 |
| **Tổng** | | | | **18** | **26** | |

Vậy:

**Tổng bước dịch L = 18**.

**Tổng bước dịch R = 26**.

**Tổng số bước di chuyển hai biên = 44**.

Với cửa sổ ban đầu rỗng và cũng kết thúc rỗng, chương trình gọi:

**22 lần add và 22 lần remove**.

Ta có bất biến kiểm toán:

**addCalls + removeCalls = leftMoves + rightMoves = 44**.

### Số add không nhất thiết bằng số remove

Trong ví dụ hai số bằng nhau vì cửa sổ đầu và cuối đều rỗng. Nếu truy vấn cuối giữ lại t phần tử, ta có:

**addCalls−removeCalls=t**,

với điều kiện mỗi lần add/remove ứng với một vị trí và cửa sổ ban đầu trống.

Đừng kết luận add=remove luôn đúng. Bất biến chung là tổng add+remove bằng số bước dịch từng biên.

## 12. Chứng minh số bước dịch biên trái

Với block size B, mọi l trong một khối có dạng:

**bB ≤ l < min((b+1)B,n+1)**.

Do các query đã sắp theo chỉ số khối tăng dần, ta chia chuyển động L thành:

1. **Trong cùng khối:** hai giá trị l bất kỳ chênh nhau ít hơn B (hoặc O(B)); do đó mỗi chuyển tiếp L trong khối tốn O(B). Có q query nên tổng O(qB).
2. **Khi chuyển sang khối mới:** chỉ số khối tăng. Các bước nhảy tiến qua các khối, cộng dồn không vượt quá O(n) cho phần tiến dài hạn giữa các nhóm; các dao động trong khối đã tính ở phần O(qB).

Vì vậy:

**Moves_L = O(qB+n)**.

Đây là **cận trên tổng quãng đường**, không phải cận cho từng query riêng lẻ. Một query ở khối mới vẫn có thể làm L nhảy xa; điểm quan trọng là các cú nhảy giữa nhóm không lặp qua lại vô hạn vì block index tăng.

### Không có sắp xếp theo khối thì sao?

Nếu l đi từ 0 tới n−1 rồi về 0 liên tục, tổng quãng đường có thể **Θ(qn)**. Sort theo block chính là cách loại bỏ dạng nhảy lớn lặp đi lặp lại.

## 13. Chứng minh số bước dịch biên phải

Xét các query có l thuộc **một khối cố định**.

Khi sắp theo r tăng dần, R có xu hướng đi **một chiều** trong khối ấy. Với odd–even sorting, chiều có thể giảm dần ở khối lẻ. Trên một khối, tổng quãng đường R khi xử lý các query của khối đó nhiều nhất **O(n)**, bỏ qua một bước chuyển vào khối.

Số khối l có query không vượt quá:

**O(⌈(n+1)/B⌉)**.

Việc chuyển R từ khối trước sang khối sau cũng tốn tối đa O(n) mỗi lần. Gộp lại:

**Moves_R=O(n⌈(n+1)/B⌉)**.

Thông thường ta viết ngắn:

**O(n²/B+n)**.

### Ý nghĩa của hai hạng tử

- B nhỏ ⇒ có nhiều khối ⇒ R có thể phải quét nhiều lần trên miền n.
- B lớn ⇒ ít khối ⇒ R di chuyển ít hơn, nhưng L có thể dao động rộng trong từng khối.

Đây chính là **tradeoff cần cân bằng**.

### Odd–even không cần cho chứng minh O(n²/B)

Sort r tăng dần trong mọi khối vẫn có cận O(n²/B). Biến thể lẻ–chẵn chủ yếu hạn chế bước nhảy R tại điểm chuyển khối, thường giúp benchmark nhưng không thay đổi định lý tổng quát.

## 14. Công thức tổng chi phí di chuyển

Đặt:

**M_L = số lần L tăng/giảm một đơn vị**.

**M_R = số lần R tăng/giảm một đơn vị**.

Nếu add/remove đều có chi phí O(1), thời gian cập nhật cửa sổ tỷ lệ với:

**M = M_L + M_R**.

Từ hai cận trên:

**M=O(qB+n²/B+n)**

với 1≤B≤n khi n>0.

Nếu B≈√n:

- qB=O(q√n).
- n²/B=O(n√n).

Do đó:

**M=O((n+q)√n)**.

### Không quên chi phí khác

Toàn bộ chương trình còn phải:

- Nén giá trị nếu cần: **O(n log n)**.
- Tạo thông tin query: **O(q)**.
- Sort query: **O(q log q)**.
- Ghi đáp án: **O(q)**.

Một cận đầy đủ cho bản Java có compression là:

**O(n log n + q log q + qB + n²/B + n)**.

Nếu add/remove có chi phí **T_update**, phần di chuyển trở thành:

**O((qB+n²/B+n)·T_update)**,

trong khi chi phí đọc answer có thể là O(q·T_answer).

Không được chỉ nhìn M mà quên chi phí thao tác tổng hợp trên cửa sổ.

## 15. Chọn kích thước khối B khi q khác n

B≈√n là mặc định dễ nhớ và thường hợp lý khi **q cùng bậc với n**.

Nhưng xét hàm dẫn đầu của phần di chuyển:

**f(B)=qB+n²/B**.

Nếu tạm xem B là số thực dương và bỏ các hằng số:

**f'(B)=q−n²/B²**.

Đặt bằng 0:

**B≈n/√q**.

Vì B phải là số nguyên dương và không lớn hơn kích thước có ý nghĩa của input, cần clamp vào khoảng phù hợp. Công thức này chỉ là một **cân bằng tiệm cận sơ bộ**, không nhất thiết tối ưu runtime thực.

### Tình huống q≪n

Nếu chỉ có một vài query, xây compression, sort query và tổ chức Mo có thể tốn hơn việc quét trực tiếp q đoạn. Có thể chọn B lớn hoặc đơn giản **không dùng Mo**.

### Tình huống q≫n

Kích thước khối nhỏ hơn có thể giảm thành phần qB. Tuy nhiên số query quá nhiều khiến chi phí sort q log q và ghi đáp án cũng rất lớn.

### Chọn bằng benchmark

Đo thử các B như:

**max(1,√n/2), √n, 2√n, n/√max(1,q)**

trên workload thực. Đếm số bước L/R để hiểu việc chọn B tác động thế nào, thay vì chỉ nhìn runtime tổng bị ảnh hưởng bởi cache/JVM/GC.

## 16. Vì sao Mo là offline và không xử lý được query ngay?

Cần có tập truy vấn để **sắp xếp lại trước khi chạy**. Nếu ứng dụng nhận một query rồi phải trả kết quả ngay trước khi biết query tiếp theo, không thể dùng cách sort toàn bộ batch như trên.

Đặc trưng:

- **Offline:** biết toàn bộ batch query; có thể reorder và trả theo original ID.
- **Online:** phải phản hồi tại thời điểm query xuất hiện; cần cấu trúc đã được duy trì như segment tree, Fenwick, persistent structure hoặc một index khác tùy hàm.

### Không phải mọi thuật toán offline đều là Mo

- Prefix sum trả tổng đoạn tĩnh O(1) mà không cần reorder.
- Sort các query theo r, dùng Fenwick trên **last occurrence** cũng có thể trả distinct count offline.
- Sweep line theo tọa độ x dùng cấu trúc dữ liệu tùy bài.
- Parallel binary search, CDQ divide-and-conquer và offline dynamic connectivity là những kỹ thuật khác.

Mo đặc biệt hấp dẫn khi có phép **add/remove rẻ** nhưng không có công thức query tĩnh đơn giản.

## 17. Khi nào Mo không phải lựa chọn tốt?

**Tổng đoạn thuần túy:** Prefix sum xây O(n), query O(1), thường tốt hơn Mo.

**XOR đoạn thuần túy:** Prefix XOR cũng cho query O(1).

**Đếm distinct tĩnh:** Mo là một lựa chọn dễ học và linh hoạt; nhưng có thuật toán offline theo **last occurrence + Fenwick tree** với O((n+q) log n) sau bước xử lý/ nén thích hợp. Không nên khẳng định Mo là lựa chọn tối ưu tuyệt đối cho mọi bộ distinct queries.

**Range min trên mảng tĩnh:** Sparse table tiền xử lý O(n log n), query min O(1) với phép min idempotent và các đoạn chồng lấp thích hợp. Cần so sánh yêu cầu bộ nhớ và loại truy vấn.

**Một query đơn:** Duyệt trực tiếp [l,r) có thể tốt hơn chi phí chuẩn bị Mo.

### Quy tắc chọn

Chỉ ưu tiên Mo nếu:

1. Query trên cùng một dữ liệu tĩnh.
2. Có thể xử lý offline.
3. Mỗi lần thêm/bỏ phần tử khỏi cửa sổ làm thay đổi aggregate **rẻ**.
4. Số lượng query đủ nhiều để chi phí sort và compression được bù.
5. Không có cấu trúc chuyên biệt tốt hơn rõ rệt cho chính phép toán đang hỏi.

## 18. Hàm cửa sổ nào duy trì được trong O(1)?

Mo không áp đặt công thức thống kê; mỗi bài cần tự tìm state phù hợp.

| Hàm trên đoạn | Thêm a[pos] | Bỏ a[pos] | Ghi chú |
| --- | --- | --- | --- |
| Tổng | sum+=x | sum−=x | Nhưng prefix sum tĩnh thường nhanh hơn |
| XOR | xor^=x | xor^=x | Nhưng prefix XOR giải nhanh hơn |
| Số distinct | Nếu freq[x]=0 thì distinct++ | Nếu sau giảm freq[x]=0 thì distinct-- | Cần freq và compression |
| Số phần tử bằng một giá trị v cố định | Tăng counter nếu x=v | Giảm counter nếu x=v | Có thể dùng prefix indicator |
| Tổng bình phương tần suất có trọng số | Cập nhật qua freq[x] trước khi tăng | Cập nhật qua freq[x] trước khi giảm | Ví dụ “powerful array” |
| Median/phần tử thứ k | Không luôn O(1) | Không luôn O(1) | Có thể cần BIT/tree O(log n) |
| Mode (giá trị có tần suất lớn nhất) | Không tự O(1) | Không tự O(1) | Cần cấu trúc phụ/chi phí cập nhật |

Một phép toán có **add rẻ nhưng remove khó** có thể không phù hợp với Mo tiêu chuẩn, bởi hai biên thường dịch **theo cả hai chiều**.

### Tính cộng giao hoán không đủ

Nhiều người nghĩ “chỉ cần phép gộp có tính kết hợp là dùng Mo O(1)”. Không đúng: khi bỏ một phần tử khỏi một aggregate, cần biết cách **đảo ảnh hưởng** của phần tử ấy.

Ví dụ min của một multiset không thể cập nhật O(1) chỉ từ giá trị min cũ nếu vừa xóa đúng phần tử đang đạt min và không biết phần tử nhỏ thứ hai.

## 19. Ví dụ mở rộng: powerful array

Một bài kinh điển hỏi:

**F(l,r)=Σ_v v·freq_v([l,r))²**,

với v là giá trị phần tử và freq_v là số lần v xuất hiện trong đoạn.

Nếu thêm một phần tử có giá trị x, trước đó freq[x]=f, thay đổi:

**ΔF = x·((f+1)²−f²)=x·(2f+1)**.

Nếu bỏ một phần tử x với tần suất cũ f≥1:

**ΔF = x·((f−1)²−f²)=−x·(2f−1)**.

Vì vậy:

~~~text
add(x):
    answer += x * (2*freq[x] + 1)
    freq[x]++

remove(x):
    answer -= x * (2*freq[x] - 1)
    freq[x]--
~~~

Mỗi lần add/remove chỉ cần O(1) thao tác số học với freq[x], nên Mo rất tự nhiên.

### Chú ý overflow

Nếu x có trị tuyệt đối lớn hoặc n lớn, F có thể vượt long. Phải phân tích cận toán học của mục tiêu, chọn long/BigInteger hoặc kiểm tra số học, không mặc định mọi tích và tổng đều an toàn trong int.

### Phân biệt giá trị và rank

Nếu đã nén tọa độ, **freq dùng rank** nhưng khi tính F vẫn cần **giá trị gốc x**, không được thay x bằng rank và làm đổi hàm mục tiêu.

## 20. Truy vấn rỗng, trùng, biên n và dữ liệu âm

Mo cần xử lý chuẩn các trường hợp:

**Mảng rỗng n=0:** chỉ query [0,0) là hợp lệ, distinct=0.

**Đoạn rỗng [l,l):** distinct=0, dù l=0, l=n hoặc l ở giữa mảng.

**Đoạn toàn phần [0,n):** số distinct toàn bộ mảng.

**Truy vấn một phần tử [i,i+1):** distinct=1.

**Truy vấn lặp lại:** mỗi query có id riêng; kết quả có thể giống nhau nhưng vẫn phải điền đúng answer[id].

**Giá trị âm hoặc cực trị int:** compression giải quyết tần suất mà không cấp mảng theo giá trị trực tiếp.

**Query không hợp lệ:** l<0, r>n hoặc l>r phải bị từ chối rõ ràng; không âm thầm đổi [l,r) thành [r,l) hoặc clamp biên.

### Đoạn rỗng không nhất thiết có chi phí chuyển cửa sổ bằng 0

Nếu cửa sổ hiện tại [0,n) và query kế là [n,n), thuật toán phải loại n phần tử. Đáp án cuối bằng 0, nhưng **chi phí để chuyển trạng thái** vẫn có thể Θ(n).

Ngược lại, từ [n,n) sang chính [n,n), chi phí di chuyển là 0.

## 21. Tại sao thứ tự bốn vòng lặp phải được kiểm tra kỹ?

Các biến thể Mo phổ biến có thể di chuyển R trước L hoặc L trước R, nhưng không phải **mọi thứ tự bốn vòng lặp** đều bảo toàn tính hợp lệ của trạng thái trung gian.

Xét cửa sổ [0,2), muốn đến [5,5):

- Nếu chạy **while L<5: remove(a[L++])** trước khi mở rộng R, ta sẽ thử remove a[2],a[3],a[4] khi những phần tử này chưa resident.
- Nếu mở rộng R tới 5 rồi thu hẹp L tới 5, mọi remove đều hợp lệ.

Code trong bài dùng thứ tự:

1. Mở rộng trái.
2. Mở rộng phải.
3. Thu hẹp trái.
4. Thu hẹp phải.

Đây là cách dễ kiểm chứng với các đoạn nửa mở bất kỳ, kể cả đoạn rỗng nằm xa vị trí hiện tại.

### Cần kiểm tra nửa mở trong code

- Mở trái: **add(--L)**.
- Mở phải: **add(R++)**.
- Thu trái: **remove(L++)**.
- Thu phải: **remove(--R)**.

Nhầm **remove(R--)** sẽ bỏ a[R] vốn **ở ngoài** cửa sổ [L,R) và có thể truy cập a[n].

## 22. Chứng minh đúng của Mo theo bất biến

Cần chứng minh hai phần độc lập.

### Phần A — Trạng thái cửa sổ luôn đúng

Bất biến:

**Sau mỗi lần add/remove được thực hiện ở một biên, freq phản ánh chính xác multiset các giá trị trong cửa sổ [L,R).**

Cơ sở: [0,0) rỗng, mọi freq bằng 0, distinct=0.

Bước quy nạp:

- Khi mở rộng trái/phải, thêm đúng một phần tử vừa đi vào cửa sổ; cập nhật freq và distinct đúng.
- Khi thu hẹp trái/phải, bỏ đúng một phần tử đang ở cửa sổ; cập nhật freq và distinct đúng.
- Không có bước nào thêm/bỏ một vị trí nằm ngoài cửa sổ theo thứ tự điều khiển đã chọn.

Vậy khi L=l,R=r, distinct là số giá trị khác nhau trong [l,r).

### Phần B — Mọi query được trả đúng vị trí

Mỗi query được gán id từ 0 tới q−1. Sắp xếp chỉ thay thứ tự duyệt **bản sao record**; không đổi l,r,id.

Khi cửa sổ đúng cho query có id=i, ghi:

**answer[i]=distinct**.

Vì mọi query được xử lý đúng một lần, mọi answer[i] là kết quả đúng cho truy vấn gốc thứ i.

### Tính đúng không phụ thuộc cách sort

Nếu các phép add/remove và window invariant đúng, Mo vẫn **tính đúng** khi sort query theo bất kỳ thứ tự nào. Sort theo khối là để **giảm chi phí**, không phải điều kiện logic để đáp án đúng.

## 23. Khác biệt giữa số bước di chuyển và thời gian chạy

Giả sử một run có:

**M_L=18, M_R=26, M=44**.

Điều này cho biết có 44 lần biên dịch qua một chỉ số, và nếu mỗi lần như vậy gọi đúng một add/remove thì có 44 lần cập nhật aggregate.

Nhưng thời gian chạy thực tế còn có:

- Nén 12 giá trị ban đầu.
- Cấp phát và sort 11 đối tượng query.
- Truy cập mảng freq/rank.
- Kiểm tra điều kiện while.
- Bố trí bộ nhớ, cache và hành vi JVM JIT.
- Ghi mảng kết quả và stdout.

Do đó **44 không phải số nano-giây hay số thao tác CPU chính xác**. Đó là một **thước đo logic để so sánh chính sách sắp xếp** trong cùng mô hình.

### Khi add/remove tốn O(log n)

Nếu mỗi lần phải cập nhật một Fenwick tree hoặc balanced tree, toàn bộ 44 lần tương ứng 44 cập nhật có chi phí tới O(log n), không còn O(44) theo nghĩa số học đơn vị.

Khi phân tích Mo cho một hàm phức tạp, hãy viết:

**O(sortCost + M·updateCost + q·answerCost)**,

rồi thay độ phức tạp thực của từng thành phần.

## 24. Java 17+ hoàn chỉnh: Mo đếm số giá trị phân biệt

Chương trình sau được thiết kế để biên dịch thành một file **MoTwoBoundaryMovesDemo.java**.

Nó có các thành phần:

1. **Range(left,right):** một query nửa mở [l,r).
2. **Query(left,right,id):** bản có id gốc để sort offline.
3. **Compressed:** nén giá trị int, hỗ trợ số âm và hai cực trị 32-bit.
4. **Window:** lưu freq, distinct và đếm số lần add/remove; ném lỗi nếu remove một phần tử không có trong cửa sổ.
5. **solve:** sắp theo block và r lẻ–chẵn; chạy đúng bốn vòng while, đếm chi phí L/R.
6. **bruteDistinct:** dùng HashSet độc lập để kiểm tra các ví dụ nhỏ.
7. **show:** in đáp án theo thứ tự gốc, thứ tự xử lý và số bước di chuyển.

**Không có cập nhật giá trị a trong thuật toán này.** Input được coi là tĩnh trong toàn bộ batch query.

~~~java
import java.util.Arrays;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class MoTwoBoundaryMovesDemo {

    record Range(int left, int right) {}

    record Query(int left, int right, int id) {}

    record Compressed(int[] ranks, int distinctValues) {}

    record Result(
            int[] answers,
            int[] processingOrder,
            long leftMoves,
            long rightMoves,
            long addCalls,
            long removeCalls,
            int blockSize) {}

    static final class Window {
        private final int[] ranks;
        private final int[] freq;
        private int distinct;
        private long adds;
        private long removes;

        Window(Compressed compressed) {
            ranks = compressed.ranks();
            freq = new int[compressed.distinctValues()];
        }

        void add(int pos) {
            int x = ranks[pos];

            if (freq[x] == 0) {
                distinct++;
            }

            freq[x]++;
            adds++;
        }

        void remove(int pos) {
            int x = ranks[pos];

            if (freq[x] <= 0) {
                throw new AssertionError(
                        "Removing a nonresident element");
            }

            freq[x]--;

            if (freq[x] == 0) {
                distinct--;
            }

            removes++;
        }

        int distinctCount() {
            return distinct;
        }

        long adds() {
            return adds;
        }

        long removes() {
            return removes;
        }
    }

    static Compressed compress(int[] values) {
        int[] sorted = values.clone();
        Arrays.sort(sorted);

        // Keep unique values at the front of sorted.
        int distinctValues = 0;

        for (int value : sorted) {
            if (distinctValues == 0
                    || sorted[distinctValues - 1] != value) {
                sorted[distinctValues++] = value;
            }
        }

        int[] unique =
                Arrays.copyOf(sorted, distinctValues);

        int[] ranks = new int[values.length];

        for (int i = 0; i < values.length; i++) {
            int rank = Arrays.binarySearch(
                    unique, values[i]);

            if (rank < 0) {
                throw new AssertionError(
                        "Compression lookup failed");
            }

            ranks[i] = rank;
        }

        return new Compressed(ranks, distinctValues);
    }

    static Result solve(
            int[] values, Range[] ranges, int blockSize) {

        Objects.requireNonNull(values, "values");
        Objects.requireNonNull(ranges, "ranges");

        if (blockSize <= 0) {
            throw new IllegalArgumentException(
                    "blockSize must be positive");
        }

        int n = values.length;
        Query[] ordered = new Query[ranges.length];

        for (int i = 0; i < ranges.length; i++) {
            Range range = Objects.requireNonNull(
                    ranges[i], "range");

            if (range.left() < 0
                    || range.right() < range.left()
                    || range.right() > n) {
                throw new IllegalArgumentException(
                        "invalid half-open query: " + range);
            }

            ordered[i] = new Query(
                    range.left(), range.right(), i);
        }

        Arrays.sort(ordered, (a, b) -> {
            int blockA = a.left() / blockSize;
            int blockB = b.left() / blockSize;

            if (blockA != blockB) {
                return Integer.compare(blockA, blockB);
            }

            // Even block: ascending right.
            // Odd block: descending right.
            int byRight = (blockA & 1) == 0
                    ? Integer.compare(a.right(), b.right())
                    : Integer.compare(b.right(), a.right());

            return byRight != 0
                    ? byRight
                    : Integer.compare(a.id(), b.id());
        });

        int[] answers = new int[ranges.length];
        int[] processingOrder = new int[ranges.length];

        // q=0: skip compression and all pointer work.
        if (ranges.length == 0) {
            return new Result(
                    answers, processingOrder,
                    0L, 0L, 0L, 0L, blockSize);
        }

        Compressed compressed = compress(values);
        Window window = new Window(compressed);

        int left = 0;
        int right = 0;
        long leftMoves = 0L;
        long rightMoves = 0L;

        for (int step = 0; step < ordered.length; step++) {
            Query query = ordered[step];
            processingOrder[step] = query.id();

            // Expand first, then shrink.
            while (left > query.left()) {
                window.add(--left);
                leftMoves++;
            }

            while (right < query.right()) {
                window.add(right++);
                rightMoves++;
            }

            while (left < query.left()) {
                window.remove(left++);
                leftMoves++;
            }

            while (right > query.right()) {
                window.remove(--right);
                rightMoves++;
            }

            if (left != query.left()
                    || right != query.right()) {
                throw new AssertionError(
                        "Window bounds do not match query");
            }

            answers[query.id()] =
                    window.distinctCount();
        }

        if (window.adds() + window.removes()
                != leftMoves + rightMoves) {
            throw new AssertionError(
                    "Pointer-movement accounting failed");
        }

        return new Result(
                answers,
                processingOrder,
                leftMoves,
                rightMoves,
                window.adds(),
                window.removes(),
                blockSize);
    }

    static int bruteDistinct(
            int[] values, Range range) {

        Set<Integer> unique = new HashSet<>();

        for (int i = range.left(); i < range.right(); i++) {
            unique.add(values[i]);
        }

        return unique.size();
    }

    static void show(
            String label, int[] values,
            Range[] queries, int blockSize) {

        int[] original = values.clone();
        Result result = solve(values, queries, blockSize);

        for (int i = 0; i < queries.length; i++) {
            int brute = bruteDistinct(values, queries[i]);

            if (result.answers()[i] != brute) {
                throw new AssertionError(
                        "Mo and brute disagree: " + label);
            }
        }

        if (!Arrays.equals(values, original)) {
            throw new AssertionError(
                    "Input array was modified");
        }

        long totalMoves =
                result.leftMoves() + result.rightMoves();

        System.out.println(
                label + " answers: "
                + Arrays.toString(result.answers()));

        System.out.println(
                label + " order: "
                + Arrays.toString(result.processingOrder()));

        System.out.println(
                label + " moves: L=" + result.leftMoves()
                + ", R=" + result.rightMoves()
                + ", add=" + result.addCalls()
                + ", remove=" + result.removeCalls()
                + ", total=" + totalMoves
                + ", block=" + result.blockSize());
    }

    public static void main(String[] args) {

        int[] mixed = {
                4, -1, 4, 2, 2, -1, 3, 4, -5, 3, 0, 0
        };

        Range[] mixedQueries = {
                new Range(0, 12),
                new Range(0, 4),
                new Range(2, 9),
                new Range(4, 8),
                new Range(5, 5),
                new Range(8, 12),
                new Range(10, 12),
                new Range(12, 12),
                new Range(1, 11),
                new Range(3, 7),
                new Range(7, 11)
        };

        show("Mixed", mixed, mixedQueries, 3);

        show("Repeated",
                new int[] {7, 7, 7, 7},
                new Range[] {
                        new Range(0, 4),
                        new Range(1, 3),
                        new Range(2, 2),
                        new Range(0, 1)
                },
                2);

        show("Extremes",
                new int[] {
                        Integer.MIN_VALUE,
                        Integer.MAX_VALUE,
                        Integer.MIN_VALUE,
                        0,
                        Integer.MAX_VALUE
                },
                new Range[] {
                        new Range(0, 5),
                        new Range(1, 4),
                        new Range(0, 3),
                        new Range(4, 4),
                        new Range(2, 5)
                },
                2);

        show("Empty array",
                new int[] {},
                new Range[] {
                        new Range(0, 0),
                        new Range(0, 0)
                },
                1);

        show("No queries",
                new int[] {4, -1, 4},
                new Range[] {},
                2);

        show("Single query",
                mixed,
                new Range[] {new Range(2, 7)},
                3);
    }
}
~~~

Biên dịch và chạy với **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 MoTwoBoundaryMovesDemo.java
java MoTwoBoundaryMovesDemo
~~~

**Đầu ra chuẩn, gồm 18 dòng:**

~~~text
Mixed answers: [6, 3, 5, 4, 0, 3, 1, 0, 6, 3, 4]
Mixed order: [1, 2, 8, 0, 3, 9, 4, 10, 5, 6, 7]
Mixed moves: L=18, R=26, add=22, remove=22, total=44, block=3
Repeated answers: [1, 1, 0, 1]
Repeated order: [3, 1, 0, 2]
Repeated moves: L=4, R=6, add=5, remove=5, total=10, block=2
Extremes answers: [3, 3, 2, 0, 3]
Extremes order: [2, 1, 0, 4, 3]
Extremes moves: L=6, R=6, add=6, remove=6, total=12, block=2
Empty array answers: [0, 0]
Empty array order: [0, 1]
Empty array moves: L=0, R=0, add=0, remove=0, total=0, block=1
No queries answers: []
No queries order: []
No queries moves: L=0, R=0, add=0, remove=0, total=0, block=2
Single query answers: [4]
Single query order: [0]
Single query moves: L=2, R=7, add=7, remove=2, total=9, block=3
~~~

### Đọc các dòng kết quả

**Mixed:** B=3; Mo xử lý theo 11 ID đã sắp nhưng vẫn trả 11 answer theo thứ tự gốc. Chi phí di chuyển hai biên 18+26=44.

**Repeated:** một giá trị lặp nhiều lần, nhưng distinct vẫn chỉ 1 với đoạn không rỗng. Query [2,2) bằng 0.

**Extremes:** dữ liệu chứa Integer.MIN_VALUE và Integer.MAX_VALUE; compression vẫn đúng vì không dùng trực tiếp giá trị làm chỉ số freq.

**Empty array:** có hai query rỗng hợp lệ, không thực hiện add/remove.

**No queries:** q=0, không cần nén giá trị hay di chuyển biên; kết quả và order đều là mảng rỗng.

**Single query:** Mo vẫn tính đúng, nhưng phải dịch biên tới [2,7) với 9 bước; duyệt trực tiếp đúng 5 phần tử có thể hợp lý hơn khi chỉ hỏi một lần.

## 25. Điều gì làm code Java đáng tin hơn một bản mô tả rút gọn?

Một bản giải ngắn thường chỉ có comparator và bốn vòng while. Bản đầy đủ cần thêm:

**Hợp đồng chỉ số:** kiểm tra 0≤l≤r≤n trước khi sort để từ chối query không hợp lệ.

**Nén số âm và cực trị:** dùng Arrays.sort + distinct + binarySearch để xây rank. Không dùng abs(value) hoặc value trực tiếp làm index.

**Độ dài rỗng:** khi n=0 và q>0, tất cả query hợp lệ phải là [0,0); không có thao tác truy cập array.

**Không đổi input:** compress làm việc trên bản sao của array, không sắp xếp original.

**Original ID:** comparator chỉ đổi thứ tự record; result lưu theo id gốc, ngăn trả nhầm.

**Tie-break rõ ràng:** comparator có bước so id, làm thứ tự mẫu tái lập được.

**Bảo đảm remove hợp lệ:** nếu freq[x]≤0 trước remove, ném AssertionError thay vì để tần suất âm rồi âm thầm trả distinct sai.

**Đo chi phí logic:** thống kê riêng leftMoves, rightMoves, adds, removes; kiểm tra tổng thống kê nhất quán.

**Bài toán đúng phạm vi:** function solve xử lý batch trên mảng tĩnh; không giả vờ hỗ trợ updates chen giữa.

### Về complexity của code

Nén O(n log n), sort q query O(q log q), di chuyển theo tổng bound. Bộ nhớ O(n+q), gồm ranks, sorted copy, freq, query records, order IDs và answer.

Với q=0, code trả ngay sau khi kiểm tra query và sort mảng trống, nên **không cần compression**. Với n=0 và q>0, compression tạo mảng rỗng và không có add/remove, hoàn toàn an toàn.

## 26. QA độc lập: đối chiếu với oracle trực tiếp

Một cách kiểm thử thuật toán Mo là viết một oracle đơn giản nhưng không tối ưu:

~~~text
BRUTE_DISTINCT(a,l,r):
    s = empty set
    for index = l .. r-1:
        s.add(a[index])
    return size(s)
~~~

Sinh hàng nghìn mảng ngẫu nhiên và nhiều query [l,r) hợp lệ. Với mỗi batch, xác minh:

**answerMo[i] == BRUTE_DISTINCT(a,query[i])**.

Oracle không dùng sorting theo block, không duy trì cửa sổ L/R và không dùng freq từ Mo, nên kiểm tra đúng loại lỗi off-by-one, trùng giá trị và sai thứ tự answer.

### Ca thử nên có

1. n=0, q=0.
2. n=0, có nhiều [0,0).
3. n=1, các query [0,0),[0,1),[1,1).
4. Mảng toàn một giá trị.
5. Mảng toàn giá trị khác nhau.
6. Mảng có số âm, 0 và cực trị Integer.MIN_VALUE/Integer.MAX_VALUE.
7. Query [0,n) và [n,n).
8. Query l=r ở giữa mảng.
9. Nhiều query trùng hệt nhau.
10. Query có l thuộc cùng một block nhưng r thay đổi mạnh.
11. Query ở các block liên tiếp và cách xa.
12. q nhỏ, q lớn; B=1,B≈√n,B=n và B>n.
13. Đảo thứ tự input query: answer phải đổi vị trí tương ứng nhưng giá trị từng đoạn không đổi.
14. Đổi tên các giá trị a bằng một song ánh: distinct answers không đổi.
15. Đếm tổng bước dịch và tổng add/remove phải khớp.
16. Query không hợp lệ phải bị từ chối, không tự sửa biên.

### Kiểm thử chi phí khác kiểm thử đáp án

Một comparator sai vẫn có thể trả **đúng distinct** vì bốn vòng di chuyển vẫn cuối cùng tới đúng [l,r); nhưng số bước có thể tăng thành Θ(qn).

Vì vậy QA cần **hai mục tiêu riêng**:

- Đúng câu trả lời bằng oracle.
- Đúng logic sort, các move counters và phân tích chi phí trên những trace đối kháng.

## 27. Các bất biến/metamorphic properties hữu ích

Với hàm distinct:

**0≤distinct(l,r)≤r−l**.

**distinct(l,l)=0**.

**Nếu r=l+1, distinct=1**.

**Nếu đoạn mở rộng thêm một phần tử:** số distinct tăng tối đa 1 và không giảm.

**Nếu đoạn thu hẹp bằng cách bỏ một phần tử:** số distinct giảm tối đa 1 và không tăng.

**Hoán vị tên giá trị theo song ánh:** số distinct giữ nguyên.

**Đổi thứ tự query:** tập answer tương ứng mỗi query không đổi, chỉ vị trí trong mảng output chuyển theo thứ tự mới.

**Lặp một query nhiều lần:** mọi bản sao phải có cùng đáp án.

### Bất biến trạng thái

**addCalls+removeCalls = leftMoves+rightMoves**.

Nếu cửa sổ bắt đầu rỗng:

**addCalls−removeCalls = độ dài cửa sổ cuối**.

Sau mỗi query được xử lý:

**L=query.left** và **R=query.right**.

Mọi tần suất **freq[x]≥0**, tổng các freq bằng **R−L**.

Những điều kiện này cho phép phát hiện lỗi logic cập nhật cửa sổ trước cả khi nhìn đáp án.

## 28. Vì sao ví dụ tổng đoạn không cần Mo?

Nếu mục tiêu là:

**sum(l,r)=Σ_{i=l}^{r−1}a[i]**,

ta xây mảng prefix:

**P[0]=0**, **P[i+1]=P[i]+a[i]**.

Sau đó:

**sum(l,r)=P[r]−P[l]**.

Độ phức tạp:

**O(n)** preprocess, **O(1)** mỗi query.

Với q query:

**O(n+q)** tổng, ngoài chi phí đọc và xuất dữ liệu.

Điều này thường vượt Mo về mặt tiệm cận cho bài tổng đoạn **tĩnh**. Mo vẫn có thể duy trì sum bằng add/remove, nhưng đó chỉ là một **minh họa kỹ thuật**, không phải lời giải nên chọn.

### Đếm distinct có giải pháp offline khác

Có thể sắp query theo r tăng và dùng Fenwick tree lưu indicator tại **lần xuất hiện cuối cùng** của mỗi giá trị:

1. Khi duyệt a[r], bỏ indicator ở lần xuất hiện trước của a[r], nếu có.
2. Đặt indicator=1 tại r.
3. Truy vấn tổng indicator trên [l,r+1) cho các query kết thúc tại r.

Với nén/HashMap tìm last occurrence và Fenwick, chi phí thông thường O((n+q)log n), cộng preprocessing tùy cách cài.

**Kết luận:** hiểu Mo để xử lý **những aggregate linh hoạt với add/remove rẻ**, nhưng trước khi dùng cần so với các phương pháp có cấu trúc bài toán đặc biệt.

## 29. Mo với cập nhật: thêm trục thời gian

Trong bài toán có **point modifications** chen giữa các query:

~~~text
Query [0,5) tại thời điểm t0
Set a[2] = 100
Query [0,5) tại thời điểm t1
~~~

Hai truy vấn có cùng [l,r) nhưng phải cho đáp án khác nếu phép set làm thay đổi distinct trong đoạn.

Mo nguyên bản chỉ có hai tọa độ l,r và sort lại query mà không xét t sẽ làm sai.

### Mo with modifications

Một biến thể mở rộng mỗi query thành:

**(l,r,t)**,

trong đó t là **số cập nhật đã xảy ra** trước query ấy.

Khi xử lý một query mới:

- Di chuyển L tới l.
- Di chuyển R tới r.
- Di chuyển **T** tới t bằng cách apply hoặc rollback các cập nhật.
- Nếu update ảnh hưởng một vị trí hiện đang thuộc [L,R), sửa aggregate tương ứng bằng remove old và add new.
- Nếu update nằm ngoài cửa sổ, chỉ đổi giá trị trong mảng trạng thái.

### Cần phân tích lại

Thao tác move T có chi phí, và sort trở thành bài toán sắp xếp các điểm **3 chiều** (l,r,t). Một chiến lược block cỡ n^(2/3) là mẫu quen thuộc trong trường hợp số query/update cùng bậc, nhưng không được lấy cận O((n+q)√n) của Mo 2D áp dụng nguyên cho biến thể này.

Một phiên bản học Mo cơ bản nên **đảm bảo correctness trên mảng tĩnh trước**, sau đó mới mở rộng sang modifications.

## 30. Odd–even, Hilbert order và lựa chọn thứ tự

**Classic Mo:** sort (block(l),r tăng).

**Odd–even Mo:** sort theo block(l), r tăng/giảm luân phiên.

**Hilbert order:** ánh xạ điểm (l,r) theo một thứ tự không gian nhằm gom các điểm gần nhau trên mặt phẳng truy vấn.

Hilbert order có thể giảm tổng pointer movement trên nhiều workload, nhưng:

- Việc tính Hilbert key phải đúng theo số bit, phạm vi tọa độ và thứ tự so sánh.
- Sorting vẫn có chi phí.
- Không có bảo đảm “luôn nhanh hơn” odd–even Mo cho mọi input.
- Các phân tích worst-case và giả thiết cụ thể cần được trình bày riêng.

### Nên tối ưu ở đâu trước?

1. Xác nhận add/remove đúng trên mọi case.
2. Đếm M_L/M_R cho input thực.
3. Chọn B phù hợp.
4. So classic và odd–even.
5. Sau cùng mới xem Hilbert order hoặc các tối ưu sâu, nếu benchmark cho thấy có lợi.

Trước khi tối ưu hằng số, hãy chắc rằng bài **không có prefix hoặc BIT offline nhanh hơn rõ rệt**.

## 31. Thực nghiệm công bằng và dấu hiệu bottleneck

Để benchmark Mo:

- Sinh cùng tập query cho mọi variant; không để thuật toán A nhận batch khác B.
- Dùng cùng dữ liệu, cùng giá trị n,q, cùng điều kiện số âm/duplicates.
- Đo riêng preprocessing compression, query sorting và window walking nếu cần.
- Đếm **L moves, R moves, total add/remove** như một công cụ kiểm chứng chi phí.
- Với Java, cân nhắc warm-up JIT và GC; đừng suy luận từ một run duy nhất.
- Không tính thời gian in ra từng query vào phần so sánh thuật toán nếu mục tiêu đo chỉ là core.
- Thử q≪n, q≈n và q≫n.
- Thử các query ngắn, dài, trùng, rỗng và xen kẽ ở các block.
- Kiểm tra đúng bằng brute oracle trước khi so tốc độ.
- Đo memory, đặc biệt với Query objects và sorted clones.

### Hai mức kiểm tra cần tách

**Analytical QA:** cận tổng dịch O(qB+n²/B+n) và chứng minh bất biến.

**Empirical QA:** trên một batch, ghi nhận chính xác từng move và thời gian. Hai loại bằng chứng bổ sung cho nhau, không thay thế nhau.

## 32. Các lỗi thường gặp

1. **Nhầm Mo là thuật toán online**, dù cần biết toàn bộ batch query để sắp xếp.
2. **Không lưu id gốc**, dẫn đến trả answer theo thứ tự đã sort.
3. **Dùng đoạn [l,r] ở input nhưng code hiểu [l,r)**, lệch biên phải.
4. **Khởi tạo R=−1 nhưng dùng logic [L,R)**, khiến mọi vòng lặp lệch.
5. **Gọi add(R++) trước khi kiểm tra R<n**, truy cập a[n].
6. **Gọi remove(R--) thay vì remove(--R)**, bỏ ngoài cửa sổ.
7. **Thu hẹp L trước khi mở rộng R trên các đoạn không giao nhau**, remove phần tử chưa resident.
8. **Quên cập nhật freq trên hit hoặc trên thao tác remove**, state sai.
9. **Tăng distinct trên mọi add**, đếm trùng thành nhiều giá trị.
10. **Giảm distinct trên mọi remove**, mất giá trị vẫn còn bản sao.
11. **Không kiểm tra freq[x]>0 khi remove**, biến âm lặng lẽ.
12. **Dùng value trực tiếp làm chỉ số freq với dữ liệu âm/lớn**, lỗi bộ nhớ hoặc index.
13. **Nén giá trị nhưng nhầm rank với giá trị gốc khi tính powerful array**, đổi hàm mục tiêu.
14. **Cho rằng sort query bằng r đơn thuần sẽ có bound Mo như sort block**, thiếu kiểm soát L.
15. **Nhầm block(l) với block(r)** trong comparator.
16. **Dùng kích thước khối 0 khi n=0**, chia cho 0.
17. **Sắp r tăng ở khối lẻ nhưng chú thích odd–even giảm**, không khớp log thử nghiệm.
18. **Bỏ tie-break mà đòi stdout order chính xác**, sample khó tái lập.
19. **Coi tổng số move là O(q√n) mà quên n√n**, bỏ R scans.
20. **Coi mọi query O(1)** chỉ vì đọc distinct O(1), bỏ window migration.
21. **Quên q log q của sorting**, phân tích thiếu.
22. **Quên n log n của coordinate compression**, phân tích thiếu.
23. **Gọi HashMap operations chắc chắn worst-case O(1)**, không nêu giả thiết.
24. **Coi O(n+q)√n là optimal cho mọi q**, bỏ việc chọn B và giải pháp khác.
25. **Coi B=√n là bắt buộc**, thực tế có thể thử B theo q/workload.
26. **Chạy Mo cho tổng đoạn tĩnh thay prefix sum O(n+q)** mà không có lý do.
27. **Cho rằng phép gộp associative đủ để remove O(1)**, sai với min/median/mode.
28. **Áp dụng Mo cơ bản lên mảng có updates chen giữa**, query đọc sai phiên bản.
29. **Dùng một thứ tự Hilbert sai bit-width rồi gọi là cải tiến**, có thể sai comparator hoặc cost.
30. **Không kiểm tra [n,n)**, bỏ mất đoạn rỗng cuối mảng.
31. **Không kiểm tra query trùng**, answer thiếu hoặc overwritten sai id.
32. **Không xử lý q=0**, cấp phát hoặc đọc query không tồn tại.
33. **Không xử lý n=0**, cố add/remove từ array rỗng.
34. **Quên copy input trước khi nén bằng sort**, phá thứ tự và kết quả.
35. **Đếm totalMoves sai khi biên đi hai chiều**, cần đếm mỗi bước chứ không lấy |L_final−L_start| của toàn batch.
36. **So totalMoves của hai thuật toán trên hai batch khác nhau**, benchmark không công bằng.
37. **Lấy random test làm chứng minh bound worst-case**, không thay phân tích theo khối.
38. **Tuyên bố algorithm không đổi input nhưng lại sort trực tiếp a**, vi phạm hợp đồng.
39. **Không ghi rõ initial window**, làm trace movements không tái lập.
40. **Đếm distinct bằng số phần tử trong đoạn**, quên multiplicity.
41. **Xử lý query sai [l,r) bằng cách tự swap l,r**, đổi ý nghĩa input.
42. **Dùng int cho số bước tổng khi q rất lớn**, có nguy cơ overflow; dùng long để đếm.
43. **Cho rằng Hilbert luôn thắng odd–even**, thiếu bằng chứng.
44. **Dùng updateCount O(1) trong phân tích Mo with modifications mà không tính trục thời gian**, đánh giá thiếu.
45. **Không phân biệt biến thể có modifications với truy vấn hoàn toàn static**, chọn mô hình không phù hợp.
46. **Chỉ kiểm tra đáp án mà không kiểm tra processing order/moves**, bỏ bug performance.
47. **Chỉ kiểm tra moves mà không đối chiếu oracle**, có thể nhanh nhưng sai.
48. **Không bảo toàn answer[id] khi có nhiều query cùng đoạn**, mất output gốc.

## 33. Bài tập tự luyện có đáp án

**Bài 1.** Mo yêu cầu input truy vấn online hay offline?  
**Đáp án:** Offline — biết trước batch để sort.

**Bài 2.** Cửa sổ [L,R) chứa bao nhiêu vị trí?  
**Đáp án:** R−L vị trí.

**Bài 3.** Với cửa sổ rỗng, nên khởi tạo L,R thế nào?  
**Đáp án:** L=R=0.

**Bài 4.** Khi mở rộng biên phải, biểu thức gọi add nào đúng?  
**Đáp án:** add(R++), dùng chỉ số R cũ.

**Bài 5.** Khi thu hẹp biên phải, remove nào đúng?  
**Đáp án:** remove(--R), dùng chỉ số R mới.

**Bài 6.** Vì sao phải ưu tiên mở rộng trước thu hẹp nếu hai đoạn xa nhau?  
**Đáp án:** Tránh remove phần tử chưa ở trong cửa sổ hiện hành.

**Bài 7.** Với [4,−1,4], distinct bằng bao nhiêu?  
**Đáp án:** 2.

**Bài 8.** Thêm số 4 lần thứ ba làm distinct tăng không?  
**Đáp án:** Không.

**Bài 9.** Bỏ một số 4 khi freq[4]=3 làm distinct giảm không?  
**Đáp án:** Không, còn bản sao.

**Bài 10.** Bỏ số 4 khi freq[4]=1 làm distinct thế nào?  
**Đáp án:** Giảm 1.

**Bài 11.** Với n=12,B=3, l=7 thuộc khối nào?  
**Đáp án:** floor(7/3)=2.

**Bài 12.** Khối lẻ trong odd–even Mo sort r theo chiều nào?  
**Đáp án:** Giảm dần.

**Bài 13.** Tổng moves ở ví dụ Mixed là bao nhiêu?  
**Đáp án:** L=18,R=26, tổng 44.

**Bài 14.** Bao nhiêu add và remove trên ví dụ Mixed?  
**Đáp án:** 22 add và 22 remove.

**Bài 15.** Bỏ các bước đổi R trong phân tích thì thiếu hạng tử nào?  
**Đáp án:** O(n²/B).

**Bài 16.** Chi phí L qua q truy vấn đã sort block?  
**Đáp án:** O(qB+n).

**Bài 17.** Chi phí R qua các khối?  
**Đáp án:** O(n²/B+n).

**Bài 18.** Với B≈√n, chi phí di chuyển tổng?  
**Đáp án:** O((n+q)√n).

**Bài 19.** Nếu add/remove mất O(log n), phần window walking có chi phí?  
**Đáp án:** O((qB+n²/B+n)log n).

**Bài 20.** Dùng Mo hay prefix cho sum query tĩnh?  
**Đáp án:** Prefix thường tốt hơn: O(n+q) tổng.

**Bài 21.** Có n=0 và query [0,0), distinct?  
**Đáp án:** 0.

**Bài 22.** Có query [n,n) hợp lệ không?  
**Đáp án:** Có với [l,r), đó là đoạn rỗng cuối.

**Bài 23.** Vì sao cần nén tọa độ với giá trị int cực đại?  
**Đáp án:** Không thể cấp freq theo miền giá trị khổng lồ; nén tạo rank 0..d−1.

**Bài 24.** Mo với point modifications cần thêm tọa độ nào?  
**Đáp án:** Thời gian t, tức số update đã xảy ra trước query.

**Bài 25.** Hàm powerful array có delta khi thêm x với tần suất cũ f?  
**Đáp án:** x(2f+1).

**Bài 26.** Nếu có q=1 trên n rất lớn, Mo chắc tối ưu hơn brute không?  
**Đáp án:** Không, chi phí sort/compression có thể lớn hơn việc quét đoạn một lần.

**Bài 27.** Nếu một query bị sort sang đầu batch, lưu đáp án tại đâu?  
**Đáp án:** answer[originalId], không phải answer[processingStep].

**Bài 28.** Một phép đổi tên các giá trị bằng song ánh có đổi distinct count không?  
**Đáp án:** Không.

**Bài 29.** Đếm số bước biên có cần tính từng cập nhật vị trí không?  
**Đáp án:** Có; không chỉ lấy chênh cuối batch so với đầu.

**Bài 30.** Có thể áp dụng Mo nguyên bản cho truy vấn theo nhiều phiên bản a không?  
**Đáp án:** Không; phải dùng biến thể theo thời gian hoặc cấu trúc khác.

## 34. Checklist triển khai và kết luận

Trước khi sử dụng Mo:

1. **Xác định dữ liệu có tĩnh không**, query có thể xử lý offline không.
2. **Kiểm tra hàm aggregate có add/remove rẻ** trên cả hai biên.
3. **Chuẩn hóa đoạn [l,r)** và kiểm tra 0≤l≤r≤n.
4. **Lưu original ID** cho từng query.
5. **Chọn B≥1**, tham khảo B≈√n hoặc n/√q tùy workload.
6. **Sort theo block(l)** và r, cân nhắc odd–even.
7. **Định nghĩa bất biến cửa sổ [L,R)** và trạng thái thống kê.
8. **Khởi tạo L=R=0** và state rỗng.
9. **Dùng đúng add(--L),add(R++),remove(L++),remove(--R)**.
10. **Mở rộng trước thu hẹp** nếu dùng thứ tự bốn vòng lặp minh họa.
11. **Khi add/remove, cập nhật freq và distinct theo 0↔1**, không theo mỗi bản sao.
12. **Nén tọa độ nếu value âm hoặc lớn**, không dùng value gốc làm index.
13. **Trả answer[originalId]**, dù xử lý đã reorder.
14. **Đếm riêng bước dịch L/R**, so tổng với số add/remove.
15. **Chứng minh L moves O(qB+n), R moves O(n²/B+n)** dưới sorting đã chọn.
16. **Tính thêm n log n compression và q log q sorting**.
17. **Không tự tuyên bố mọi query O(1)**; chỉ answer extraction có thể O(1).
18. **Nếu có updates theo thời gian, dùng mô hình đúng** thay vì đảo thứ tự query sai.
19. **Test q=0,n=0,đoạn rỗng,giá trị cực trị và query lặp**.
20. **Đối chiếu với brute oracle** trên dữ liệu nhỏ.
21. **Kiểm thử performance riêng**, không lẫn correctness với số move.
22. **So với prefix, BIT offline và sparse table trước khi chọn**.
23. **Đo memory, GC và cache locality** nếu triển khai Java ở quy mô lớn.
24. **Không nhầm lý thuyết cận trên với benchmark một trace**.

**Kết luận:** Mo biến nhiều truy vấn đoạn tĩnh thành **một hành trình có kiểm soát của hai biên L,R**. Tổng chi phí đến từ số lần add/remove khi chuyển cửa sổ, không phải chỉ từ thao tác đọc answer. Sắp query theo khối của biên trái giúp giới hạn dao động L bởi **O(qB+n)**; sắp biên phải có trật tự trong từng khối giúp giới hạn R bởi **O(n²/B+n)**. Khi B≈√n và add/remove O(1), ta có cách xử lý offline thường được mô tả bởi **O((n+q)√n)** bước dịch, cùng chi phí sort/preprocessing. Giá trị cốt lõi của thuật toán là **tận dụng một trạng thái cửa sổ tái sử dụng giữa các truy vấn**, còn chất lượng giải pháp phụ thuộc việc chọn đúng bài toán, update state chính xác và kiểm soát toàn bộ chi phí di chuyển.
