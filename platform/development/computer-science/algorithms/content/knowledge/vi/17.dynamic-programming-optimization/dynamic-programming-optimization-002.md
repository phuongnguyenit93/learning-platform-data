# Tổng tiền tố để gom các phép chuyển theo đoạn trong quy hoạch động

Trong nhiều bài **quy hoạch động (dynamic programming, DP)**, trạng thái hiện tại không chỉ nhận đóng góp từ một vài trạng thái trước, mà từ **mọi trạng thái trong một khoảng chỉ số liên tiếp**. Nếu cứ duyệt lại toàn bộ khoảng cho mỗi trạng thái, thuật toán dễ có độ phức tạp **O(n²)** hoặc **O(nK)**. Khi phép gộp là **cộng**, ta có thể dùng **tổng tiền tố của chính mảng DP** để lấy tổng một khoảng trong **O(1)**, qua đó giảm số phép chuyển từ hàng triệu lần lặp xuống một số hằng số mỗi trạng thái.

Đây là một mẫu thuộc nhóm **tối ưu quy hoạch động**, không đơn thuần là bài học về tổng tiền tố trên mảng dữ liệu tĩnh. Các giá trị DP được **tính dần**, và tổng tiền tố cũng phải được **duy trì theo đúng thứ tự phụ thuộc**.

Bài học sẽ triển khai bốn tình huống liên hệ chặt chẽ:

1. **Đếm số cách đến vị trí i bằng bước nhảy có độ dài trong [L,R]**: mỗi trạng thái nhận tổng từ một khoảng trạng thái trước.
2. **Giới hạn nhảy phụ thuộc vị trí xuất phát**: mỗi trạng thái gửi đóng góp tới một **đoạn đích**, dùng **mảng hiệu (difference array)** như cách tối ưu đối ngẫu.
3. **Đếm cách chọn các đồng tiền có số lượng giới hạn**: dùng **tổng cửa sổ trượt theo lớp đồng dư** để gộp nhiều chuyển.
4. **Mở rộng**: nhiều khoảng, tổng có trọng số tuyến tính, các phép gộp khác cộng và cách chọn giữa prefix sum, sliding window, Fenwick tree.

## 1. Khi nào nhìn một công thức DP và nghĩ đến tổng tiền tố?

Xét công thức tổng quát:

**dp[i] = ∑ dp[j]**, với mọi **j nằm trong đoạn [left(i), right(i)]**, trong đó các j đều **nhỏ hơn i**.

Nếu left(i), right(i) thay đổi theo i, cách trực tiếp là:

~~~text
for i = 1 .. n:
    dp[i] = 0
    for j = left(i) .. right(i):
        dp[i] += dp[j]
~~~

Khi một khoảng có O(n) phần tử, tổng cộng có thể phải cộng **O(n²)** lần.

Đặc điểm giúp tối ưu:

- Các trạng thái cần gộp có chỉ số tạo thành **một khoảng liên tiếp** hoặc **một số ít khoảng liên tiếp**.
- Mỗi trạng thái trong khoảng đóng góp với cùng một hệ số hoặc một hệ số có thể tách được.
- Phép gộp là cộng, nên tổng của một đoạn có thể lấy từ **hiệu hai tổng tiền tố**.
- Trạng thái nguồn đã được tính xong trước khi trạng thái đích cần dùng nó.

Nếu các chỉ số hợp lệ **rải rác không tạo thành khoảng**, hoặc có điều kiện phức tạp riêng cho từng j, ta **không được** tự thay bằng tổng của toàn bộ [left,right] vì sẽ cộng cả những chuyển không hợp lệ.

### Phân biệt hai loại tổng tiền tố

**Tổng tiền tố dữ liệu:** P[i] = tổng a[0..i) của đầu vào cố định. Đây là một cấu trúc cho truy vấn tổng dữ liệu.

**Tổng tiền tố DP:** P[i] = tổng dp[0..i). Các dp[i] chưa có ngay từ đầu; chúng được tính **từng bước theo thứ tự**, rồi cập nhật P. Đây là cấu trúc dùng để **tính các trạng thái DP tiếp theo nhanh hơn**.

Ở bài này, khi viết P[i] nếu không nói khác, ta dùng **tổng tiền tố của DP**, không phải tổng tiền tố của mảng đầu vào.

## 2. Quy ước chỉ số: đoạn nửa mở để tránh lệch biên

Giả sử mảng DP được đánh số từ **0**. Đặt:

**P[0] = 0**,

**P[t] = dp[0] + dp[1] + ... + dp[t−1]** với t ≥ 1.

Nói cách khác, **P[t] = ∑_{0≤j<t} dp[j]**.

Với đoạn chỉ số nửa mở **[l,r)**, 0≤l≤r:

**sum(dp[l..r)) = P[r] − P[l]**.

Nếu đề/recurrence dùng đoạn **đóng [l,r]**, thì:

**sum(dp[l..r]) = P[r+1] − P[l]**.

Ví dụ khi các giá trị DP đã tính là:

~~~text
index i:  0  1  2  3  4
dp[i]:    1  0  1  1  1
P[t]:     0  1  1  2  3  4
          0  1  2  3  4  5  <- chi so t cua P
~~~

Tổng dp[2]+dp[3]+dp[4] = **3**; theo công thức là **P[5]−P[2] = 4−1 = 3**.

**P có nhiều hơn dp một ô.** Nếu dp có n+1 trạng thái từ 0 đến n, P cần ít nhất n+2 ô để chứa P[n+1].

### Trật tự cập nhật đúng trong DP

Khi tính dp[i] từ các trạng thái j<i, ta đã có P[0]..P[i]. Sau khi tính xong dp[i], mới ghi:

**P[i+1] = P[i] + dp[i]**.

Đừng cập nhật P[i+1] trước khi dp[i] được xác định. Nếu công thức cho dp[i] vô tình đọc P[i+1], có thể đang đưa **chính dp[i]** vào phép tính, tạo một phụ thuộc vòng.

## 3. Bài toán chính: đếm cách đi tới n bằng bước dài từ L đến R

Có các vị trí 0,1,...,n. Bắt đầu ở 0. Mỗi bước phải tiến về phía trước một độ dài nguyên **d∈[L,R]**, với **1≤L≤R**. Hỏi có bao nhiêu **dãy bước có thứ tự** đưa ta đến đúng vị trí n?

Ví dụ với L=2, R=3 và n=8, có bốn dãy bước:

~~~text
2 + 2 + 2 + 2
2 + 3 + 3
3 + 2 + 3
3 + 3 + 2
~~~

Thứ tự bước **có ý nghĩa**, nên 2+3+3, 3+2+3 và 3+3+2 là ba cách khác nhau.

### 3.1. Định nghĩa trạng thái

**dp[i] = số dãy bước có tổng đúng bằng i**.

Cơ sở:

**dp[0]=1** vì có đúng **một dãy bước rỗng** đến vị trí 0.

Không được đặt dp[0]=0, bởi mọi dãy bước bắt đầu từ trạng thái này. Với i<0, coi dp[i]=0 khi viết công thức tổng quát; trong code tốt hơn là **cắt khoảng** thay vì truy cập mảng chỉ số âm.

### 3.2. Công thức chuyển trực tiếp

Một dãy kết thúc tại i có **bước cuối dài d**, trong đó L≤d≤R. Trước bước cuối, ta phải đứng ở **i−d**. Vì vậy:

**dp[i] = ∑_{d=L..R} dp[i−d]**, chỉ cộng các i−d≥0.

Đổi biến **j=i−d**. Khi d chạy từ L đến R, j chạy qua đoạn đóng:

**j∈[i−R, i−L]**.

Sau khi chặn trong phạm vi hợp lệ:

**left = max(0, i−R)**,

**right = i−L**.

Nếu **right<left** thì không có bước cuối hợp lệ, đặt dp[i]=0. Ngược lại:

**dp[i] = ∑_{j=left..right} dp[j]**.

Đây chính là **tổng của một đoạn liên tiếp các trạng thái trước**.

### 3.3. Từ vòng lặp O(R−L+1) sang hiệu prefix O(1)

Từ định nghĩa P:

**dp[i] = P[right+1] − P[left]** nếu right≥left.

Sau khi tính xong:

**P[i+1] = P[i] + dp[i]**.

Pseudocode:

~~~text
dp[0] = 1
P[0] = 0
P[1] = 1

for i = 1 .. n:
    left  = max(0, i-R)
    right = i-L

    if right < left:
        dp[i] = 0
    else:
        dp[i] = P[right+1] - P[left]

    P[i+1] = P[i] + dp[i]
~~~

Vì L≥1 nên **right=i−L≤i−1**, tức **right+1≤i**. Nhờ thế, tại lúc tính dp[i], cả hai tổng tiền tố được đọc đều đã tồn tại. Đây là điểm quyết định bảo đảm thuật toán có **thứ tự phụ thuộc hợp lệ**.

### 3.4. Truy vết ví dụ L=2, R=3, n=8

| i | Khoảng nguồn [left,right] | Công thức | dp[i] |
| ---: | --- | --- | ---: |
| 0 | Cơ sở | Dãy rỗng | 1 |
| 1 | Rỗng | Không có bước ngắn như vậy | 0 |
| 2 | [0,0] | dp[0] | 1 |
| 3 | [0,1] | dp[0]+dp[1] | 1 |
| 4 | [1,2] | dp[1]+dp[2] | 1 |
| 5 | [2,3] | dp[2]+dp[3] | 2 |
| 6 | [3,4] | dp[3]+dp[4] | 2 |
| 7 | [4,5] | dp[4]+dp[5] | 3 |
| 8 | [5,6] | dp[5]+dp[6] | 4 |

Mảng kết quả:

~~~text
dp = [1, 0, 1, 1, 1, 2, 2, 3, 4]
~~~

Tổng các trạng thái trước có thể tiếp tục được tính từ P mà không quét lại đoạn [left,right]. Kết quả dp[8]=4 khớp với bốn dãy bước đã liệt kê.

### 3.5. Độ phức tạp

Nếu tính trực tiếp bằng vòng lặp theo d, mỗi trạng thái phải xét tối đa K=R−L+1 độ dài bước, nên tổng thời gian **O(nK)**, trường hợp K=Θ(n) là O(n²).

Dùng P:

- Mỗi trạng thái chỉ đọc **hai phần tử P**, trừ và cập nhật một ô.
- Thời gian **O(n)**.
- Bộ nhớ **O(n)** cho dp và P (có thể giảm nếu chỉ cần các giá trị đủ gần để cập nhật cửa sổ).

Đây là ví dụ điển hình của tối ưu **công thức chuyển**: không thay đổi trạng thái hay đáp án mà thay thế phép cộng lặp lại bằng một tổng tiền tố.

## 4. Chứng minh tính đúng của công thức và tối ưu

Có hai lớp lập luận.

### 4.1. Chứng minh recurrence đúng

Mỗi dãy bước hợp lệ tới i có **một bước cuối duy nhất** độ dài d∈[L,R]. Bỏ bước cuối ấy, ta được một dãy bước tới i−d. Ngược lại, nối d vào cuối một dãy hợp lệ tới i−d tạo đúng một dãy tới i.

Các nhóm lời giải phân biệt theo **giá trị bước cuối** không trùng nhau và bao phủ toàn bộ lời giải tới i. Do đó:

**dp[i] = tổng dp[i−d] trên mọi bước cuối hợp lệ**.

Trường hợp cơ sở dp[0]=1 biểu diễn dãy rỗng. Quy nạp theo i chứng minh mọi dp[i] đúng.

### 4.2. Chứng minh prefix không làm đổi giá trị

Giả sử P[t] đã đúng bằng tổng dp[0..t) tại mọi t≤i. Phép đổi biến j=i−d biến đúng tập nguồn hợp lệ thành **đoạn liên tiếp [left,right]**. Vì thế:

**∑_{j=left..right} dp[j] = P[right+1]−P[left]**.

Sau khi tính dp[i] bằng giá trị bằng nhau ấy, cập nhật P[i+1]=P[i]+dp[i] làm định nghĩa prefix đúng cho t=i+1. Quy nạp duy trì cả dp và P.

**Điều kiện ẩn cần kiểm tra:** công thức chỉ đúng khi **mọi j trong [left,right] là tiền nhiệm hợp lệ có cùng hệ số 1**. Nếu còn ràng buộc “đường đi không được qua ô cấm” hoặc “không được lặp loại bước vừa chọn”, cần thể hiện ràng buộc ấy trong trạng thái/chuyển, hoặc dùng tập tiền nhiệm phù hợp. Không được cộng cả khoảng một cách vô điều kiện.

## 5. Khoảng nguồn phụ thuộc vào đích i

Trong bài thực tế, mỗi vị trí i có thể có một **khoảng bước cuối riêng [Lᵢ,Rᵢ]**, hoặc đề đưa trực tiếp khoảng tiền nhiệm **[aᵢ,bᵢ]**.

Nếu công thức vẫn là:

**dp[i] = ∑_{j=aᵢ..bᵢ} dp[j]**, với **0≤aᵢ≤bᵢ<i**,

thì chỉ việc viết:

**dp[i] = P[bᵢ+1]−P[aᵢ]**.

Mỗi trạng thái vẫn **O(1)** sau khi biết hai biên, kể cả khi aᵢ và bᵢ thay đổi bất kỳ theo i.

Ví dụ cho dp[5], nếu các trạng thái hợp lệ chỉ là [1,4], ta tính **P[5]−P[1]**. Nếu với dp[6] khoảng đổi thành [0,2], ta tính **P[3]−P[0]**. Không cần sắp xếp lại các chỉ số nguồn hoặc xây một mảng prefix mới cho mỗi i.

### Nhiều khoảng nguồn

Nếu các tiền nhiệm hợp lệ là **hợp của hai đoạn rời nhau**:

**[a,b] ∪ [c,d]**, với b<c,

thì:

**dp[i] = (P[b+1]−P[a]) + (P[d+1]−P[c])**.

Thời gian O(số đoạn) thay vì O(tổng số phần tử trong các đoạn).

Nếu các đoạn **chồng lấn** nhưng mỗi trạng thái nguồn chỉ được tính **một lần**, trước tiên phải **hợp nhất** hoặc điều chỉnh phần giao. Nếu không, trạng thái ở phần giao sẽ bị đếm hai lần.

### Ví dụ ràng buộc không liên tục

Nếu chỉ được nhảy những độ dài **chẵn** trong [L,R], các tiền nhiệm tạo thành những chỉ số cách nhau 2, **không phải mọi chỉ số của một đoạn**. Tùy bài, có thể:

- Duy trì **prefix riêng cho từng lớp đồng dư modulo 2**.
- Đổi biến chỉ số để các nguồn hợp lệ trở thành liên tiếp.
- Dùng cấu trúc khác phù hợp tập chỉ số.

Cần chứng minh phép đổi nhóm bao phủ **đúng tập chuyển hợp lệ**, không thêm phần tử sai.

## 6. Modulo: phép trừ prefix phải chuẩn hóa

Số cách đếm có thể rất lớn. Nhiều đề yêu cầu kết quả **mod M**, với M>0. Khi ấy duy trì mọi dp[i], P[i] **mod M**:

**dp[i] ≡ P[right+1]−P[left] (mod M)**,

**P[i+1] ≡ P[i]+dp[i] (mod M)**.

Các ngôn ngữ có quy tắc phép dư khác nhau. Trong Java, biểu thức **(a−b)%M** có thể âm nếu a−b âm. Vì vậy thường dùng:

~~~java
static long normalize(long x, long mod) {
    long r = x % mod;
    return r < 0 ? r + mod : r;
}
~~~

Nếu **a,b đều nằm trong [0,M)**, có thể tính **(a−b+M)%M** miễn việc cộng M không tràn kiểu số. Hàm normalize trong chương trình dùng kiểu long và modulo hằng nhỏ hơn nhiều Long.MAX_VALUE.

### Giá trị modulo bằng 0 có nghĩa gì?

**ways[i] mod M = 0 không đồng nghĩa không thể đến i**. Số cách thật có thể bằng M, 2M hoặc bội số khác của M. Nếu đề còn hỏi **tồn tại hay không**, không suy ra tính tồn tại từ kết quả đếm modulo; hãy lưu **reachable[]** riêng hoặc dùng logic truy cập trạng thái không phụ thuộc vào số cách modulo.

### Khi nào cần BigInteger?

Nếu đề yêu cầu **đếm chính xác** và số cách quá lớn cho long, có thể dùng **BigInteger**. Công thức prefix và phép trừ vẫn hợp lệ, nhưng mỗi phép cộng/trừ BigInteger có chi phí phụ thuộc **số bit của số cách**. Vì vậy phát biểu O(n) thời gian ở trên là cận trong **mô hình phép toán số học đơn vị** hoặc khi dùng modulo với các phép tính hằng thời gian.

## 7. Sliding window: cùng phép gộp, bộ nhớ có thể ít hơn

Với khoảng bước cố định [L,R]:

**dp[i] = dp[i−R]+...+dp[i−L]** (chỉ các chỉ số hợp lệ).

Khi tăng i lên 1, cửa sổ nguồn cũng dịch sang phải. Nếu định nghĩa **window[i]** là tổng các trạng thái trong khoảng hợp lệ của dp[i], ta có về mặt đại số:

**window[i+1] = window[i] + dp[i+1−L] − dp[i−R]**,

trong đó các chỉ số âm được xem là không đóng góp và chỉ thực hiện khi nguồn hợp lệ.

Cách này gọi là **tổng cửa sổ trượt**; mỗi bước chỉ thêm phần tử mới và bỏ phần tử cũ, cũng đạt **O(n)** thời gian.

Nó đặc biệt hữu ích khi:

- Cửa sổ có độ rộng K nhỏ so với n.
- Chỉ cần giữ một vòng đệm gồm các trạng thái còn nằm trong phạm vi có thể được dùng.
- Không cần truy vấn lại mọi prefix trong lịch sử.

Tuy nhiên, nếu biên thay đổi **không đơn điệu** (ví dụ lúc hỏi [1,10], lúc hỏi [0,3]), việc “dịch cửa sổ hiện tại” không còn đơn giản. Mảng P cho phép lấy **mọi đoạn đã hoàn tất** bằng hai lần đọc, là lựa chọn dễ cài và khó sai hơn cho khoảng nguồn thay đổi.

**Không nhầm sliding window sum với monotonic deque.** Tổng cửa sổ dùng **cộng/trừ**; nếu DP cần **min hoặc max của cửa sổ**, có thể dùng **deque đơn điệu** để hỗ trợ đưa phần tử vào và bỏ phần tử hết hạn. Prefix subtraction không tự làm được min/max.

## 8. Dạng đối ngẫu: một nguồn gửi đóng góp tới cả đoạn đích

Đến đây, mỗi đỉnh i **đi tìm tổng từ một đoạn nguồn**:

**dp[i] = sum(dp[j] của các j trong một đoạn trước i)**.

Có một dạng bài ngược lại:

> Khi đã biết dp[j], ta cần **cộng dp[j] vào tất cả dp[i] với i thuộc một đoạn đích**.

Ví dụ ở vị trí j được phép nhảy tiếp các độ dài trong **[Lⱼ,Rⱼ]**, khác nhau theo **vị trí xuất phát**. Tức dp[j] gửi một đóng góp tới mọi đích i trong:

**[j+Lⱼ, j+Rⱼ]**.

Nếu duyệt từng i đích cho mỗi j, có thể mất O(n²) vì một nguồn phát tới nhiều đích.

### Mảng hiệu (difference array) để gom phép cộng trên đoạn

Duy trì mảng **diff[]** sao cho cộng một giá trị x vào mọi đích trong đoạn **[l,r]** được biểu diễn bằng:

**diff[l] += x**,

**diff[r+1] -= x**.

Khi duyệt chỉ số đích từ nhỏ đến lớn, duy trì **running += diff[i]**. Khi đó running là **tổng mọi đóng góp đã được phát vào vị trí i**.

Đối với đường đi từ 0:

1. Đặt **dp[0]=1** làm cơ sở.
2. Tại mỗi vị trí i, cộng diff[i] vào running để có tổng đóng góp tới i.
3. Với i>0, đặt **dp[i]=running**.
4. Nếu i<n, phát dp[i] tới đoạn đích hợp lệ **[i+Lᵢ, min(n,i+Rᵢ)]** bằng hai cập nhật diff.
5. Không gửi đóng góp vượt n; nếu đoạn đích hoàn toàn vượt n thì bỏ qua.

Điều kiện **Lᵢ≥1** đảm bảo mọi cập nhật đều hướng tới chỉ số **lớn hơn i**. Nhờ vậy, lúc đi đến đích i, tất cả các nguồn j<i đã có cơ hội phát đóng góp tới i.

### Ví dụ cụ thể

Cần tới vị trí 5. Mỗi vị trí xuất phát có giới hạn bước như sau:

| Vị trí j | Bước được phép | Đích có thể tới |
| ---: | --- | --- |
| 0 | [1,2] | 1,2 |
| 1 | [1,2] | 2,3 |
| 2 | [2,3] | 4,5 |
| 3 | [1,2] | 4,5 |
| 4 | [1,1] | 5 |

Kết quả đếm đường đi có thứ tự:

~~~text
Vị trí:  0  1  2  3  4  5
Số cách: 1  1  2  1  3  6
~~~

Giải thích:

- dp[1]=dp[0]=1.
- dp[2]=dp[0]+dp[1]=2.
- dp[3]=dp[1]=1.
- dp[4]=dp[2]+dp[3]=2+1=3.
- dp[5]=dp[2]+dp[3]+dp[4]=2+1+3=**6**.

Trong ví dụ nhỏ ta vẫn dễ liệt kê; với n lớn, diff giúp mỗi vị trí thực hiện **hai cập nhật ranh giới**, không duyệt mọi đích.

**Phân biệt rõ:** prefix sum xử lý nhanh **truy vấn tổng một đoạn nguồn**; difference array xử lý nhanh **cộng một giá trị vào một đoạn đích** rồi khôi phục bằng tổng chạy. Hai kỹ thuật dựa trên cùng phép cộng nhưng phục vụ **hai chiều chuyển trạng thái** khác nhau.

## 9. Đếm tiền với số lượng giới hạn: gom theo lớp đồng dư

Một mẫu tinh tế hơn xuất hiện trong **bounded knapsack / bounded coin change**.

Có m loại đồng tiền, loại t có:

- Mệnh giá nguyên dương **wₜ**.
- Giới hạn dùng tối đa **cₜ** đồng.

Hỏi có bao nhiêu **tổ hợp không phân biệt thứ tự** tạo đúng tổng T. Các loại mệnh giá được giả sử **phân biệt**, và mỗi loại chỉ được chọn 0..cₜ đồng.

Đặt **prev[s]** là số cách dùng các loại đã xử lý để tạo tổng s. Khi thêm loại mới mệnh giá w, giới hạn c:

**next[s] = ∑_{k=0..c, kw≤s} prev[s−k×w]**.

Cơ sở trước khi xử lý loại nào:

**prev[0]=1**, các s>0 bằng 0.

Mỗi tổ hợp sau khi thêm loại w chứa đúng k đồng loại w. Bỏ k đồng ấy tạo một tổ hợp từ các loại cũ có tổng s−kw. Các nhóm theo k rời nhau, nên công thức cộng là đúng.

### 9.1. Trực tiếp có thể tốn O(Tc) mỗi loại

Nếu tính mỗi next[s] bằng cách duyệt mọi k từ 0 đến c, thời gian có thể là **O(Tc)** cho mỗi mệnh giá. Với m loại, thành **O(mTc_max)** theo cận đơn giản, dù điều kiện kw≤s có thể giảm số phép cộng thực tế.

### 9.2. Nhóm các chỉ số theo phần dư modulo w

Các trạng thái có thể cộng vào next[s] là:

**s, s−w, s−2w, ...**.

Chúng đều có cùng **s mod w**. Vì vậy với mỗi phần dư r∈[0,w−1], xét dãy:

**prev[r], prev[r+w], prev[r+2w], ...**.

Gọi t là chỉ số trong dãy đồng dư. Ta có:

**next[r+t×w] = tổng của tối đa c+1 phần tử liên tiếp cuối cùng trong dãy prev cùng phần dư**.

Đây chính là bài toán **cửa sổ trượt**.

### 9.3. Công thức cửa sổ

Khi duyệt các tổng s=r+t×w theo thứ tự tăng:

1. **Thêm prev[s]** vào tổng cửa sổ.
2. Nếu có phần tử vượt khỏi cửa sổ c+1 vị trí, **trừ prev[s−(c+1)×w]**.
3. Gán **next[s]=window**.

Các phần dư r độc lập; mỗi tổng s thuộc **đúng một lớp đồng dư**, nên mỗi trạng thái s được xử lý đúng một lần cho mỗi loại tiền.

Do đó:

- Thời gian mỗi loại **O(T)**.
- Tổng m loại **O(mT)** phép cộng/trừ.
- Bộ nhớ **O(T)** để giữ prev và next.

### 9.4. Ví dụ mệnh giá và giới hạn

Các mệnh giá:

~~~text
Mệnh giá:     1  2  3
Số đồng tối đa 2  2  1
Tổng đích T = 5
~~~

Có **3 tổ hợp** tạo đúng 5:

~~~text
3 + 2
3 + 1 + 1
2 + 2 + 1
~~~

Đáp án không tính các hoán vị “2+3” và “3+2” thành hai tổ hợp khác nhau.

Nếu T=4, có ba tổ hợp khác: **2+2**, **3+1**, **2+1+1**.

Nếu T=0, có một tổ hợp rỗng dùng 0 đồng. Nếu loại tiền có c=0, chỉ có lựa chọn k=0 nên **next[s]=prev[s]**; công thức cửa sổ vẫn đúng khi thêm prev[s] và trừ phần tử vừa hết hạn của cùng lớp dư.

## 10. Java 17+: ba cách gom chuyển trạng thái trên cùng một chương trình

Chương trình sau triển khai:

- **countByLastStep(n,L,R)**: nguồn là một đoạn tiền nhiệm của mỗi dp[i], dùng prefix sum.
- **countWithVariableJumps(minStep,maxStep)**: mỗi dp[i] phát tới một đoạn đích, dùng difference array.
- **countBoundedCoins(target,values,limits)**: chuyển bounded knapsack, dùng sliding window trên các lớp đồng dư.

Các kết quả số cách được lấy **mod 1.000.000.007**, nên kiểu long an toàn cho cộng/trừ trong các phép modulo đơn lẻ. Chỉ dùng **bước nhảy/mệnh giá dương**; không có chuyển tự quay lại cùng trạng thái.

~~~java
import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;

public class PrefixGroupedTransitionsDemo {

    private static final long MOD = 1_000_000_007L;

    private static long norm(long x) {
        long r = x % MOD;
        return r < 0 ? r + MOD : r;
    }

    // dp[i] = sum(dp[j]) with j in [i-R, i-L] intersect [0,i).
    // Returns the whole DP table for inspection.
    static long[] countByLastStep(int target, int minStep, int maxStep) {
        if (target < 0 || minStep <= 0 || minStep > maxStep) {
            throw new IllegalArgumentException("Invalid step range");
        }

        long[] dp = new long[target + 1];
        long[] prefix = new long[target + 2];

        dp[0] = 1;
        prefix[0] = 0;
        prefix[1] = 1;

        for (int i = 1; i <= target; i++) {
            int left = (int) Math.max(0L, (long) i - maxStep);
            int right = i - minStep;

            if (right >= left) {
                dp[i] = norm(prefix[right + 1] - prefix[left]);
            } else {
                dp[i] = 0;
            }

            prefix[i + 1] = norm(prefix[i] + dp[i]);
        }
        return dp;
    }

    // Vertex 0 starts with one path; vertex n is the target.
    // Vertex i in [0,n) can jump d in [minStep[i],maxStep[i]].
    // A range update of dp[i] is recorded in delta.
    static long[] countWithVariableJumps(
            int[] minStep, int[] maxStep) {
        if (minStep == null || maxStep == null
                || minStep.length != maxStep.length) {
            throw new IllegalArgumentException("Invalid jump arrays");
        }

        int n = minStep.length;
        for (int i = 0; i < n; i++) {
            if (minStep[i] <= 0 || minStep[i] > maxStep[i]) {
                throw new IllegalArgumentException("Invalid jump rule");
            }
        }

        long[] dp = new long[n + 1];
        long[] delta = new long[n + 2];
        long running = 0;

        for (int i = 0; i <= n; i++) {
            running = norm(running + delta[i]);
            dp[i] = (i == 0) ? 1 : running;

            if (i == n) {
                continue;
            }

            // Calculate endpoints in long to avoid int overflow.
            long first = (long) i + minStep[i];
            long last = Math.min((long) n,
                                 (long) i + maxStep[i]);
            if (first > last) {
                continue;
            }

            int left = (int) first;
            int right = (int) last;

            delta[left] = norm(delta[left] + dp[i]);
            delta[right + 1] = norm(delta[right + 1] - dp[i]);
        }
        return dp;
    }

    // Counts combinations, not ordered sequences.
    // Each denomination is distinct and has a bounded quantity.
    static long countBoundedCoins(
            int target, int[] values, int[] limits) {
        if (target < 0 || values == null || limits == null
                || values.length != limits.length) {
            throw new IllegalArgumentException("Invalid coin arrays");
        }

        Set<Integer> seen = new HashSet<>();
        for (int i = 0; i < values.length; i++) {
            if (values[i] <= 0 || limits[i] < 0
                    || !seen.add(values[i])) {
                throw new IllegalArgumentException(
                        "Denominations must be distinct and positive");
            }
        }

        long[] previous = new long[target + 1];
        previous[0] = 1;

        for (int type = 0; type < values.length; type++) {
            int value = values[type];
            int limit = limits[type];
            long[] next = new long[target + 1];

            // Each residue has an independent sliding window.
            for (int residue = 0;
                    residue < value && residue <= target;
                    residue++) {
                long window = 0;

                for (long s = residue; s <= target; s += value) {
                    int index = (int) s;
                    window = norm(window + previous[index]);

                    long expired = s - ((long) limit + 1L) * value;
                    if (expired >= 0) {
                        window = norm(
                                window - previous[(int) expired]);
                    }

                    next[index] = window;
                }
            }
            previous = next;
        }

        return previous[target];
    }

    public static void main(String[] args) {
        System.out.println("Fixed steps [2,3], target 8: "
                + Arrays.toString(countByLastStep(8, 2, 3)));
        System.out.println("Fixed steps [2,3], target 0: "
                + Arrays.toString(countByLastStep(0, 2, 3)));
        System.out.println("Fixed steps [3,5], target 1: "
                + Arrays.toString(countByLastStep(1, 3, 5)));

        int[] low = {1, 1, 2, 1, 1};
        int[] high = {2, 2, 3, 2, 1};
        System.out.println("Variable jumps: "
                + Arrays.toString(countWithVariableJumps(low, high)));

        int[] coins = {1, 2, 3};
        int[] limits = {2, 2, 1};
        System.out.println("Bounded coins, target 5: "
                + countBoundedCoins(5, coins, limits));
        System.out.println("Bounded coins, target 4: "
                + countBoundedCoins(4, coins, limits));
        System.out.println("Bounded coins, target 0: "
                + countBoundedCoins(0, coins, limits));
        System.out.println("Bounded [2] x1, target 4: "
                + countBoundedCoins(4,
                        new int[] {2}, new int[] {1}));
    }
}
~~~

Lưu mã nguồn với tên **PrefixGroupedTransitionsDemo.java** và chạy bằng **JDK 17 trở lên**:

~~~bash
javac PrefixGroupedTransitionsDemo.java
java PrefixGroupedTransitionsDemo
~~~

**Đầu ra chính xác:**

~~~text
Fixed steps [2,3], target 8: [1, 0, 1, 1, 1, 2, 2, 3, 4]
Fixed steps [2,3], target 0: [1]
Fixed steps [3,5], target 1: [1, 0]
Variable jumps: [1, 1, 2, 1, 3, 6]
Bounded coins, target 5: 3
Bounded coins, target 4: 3
Bounded coins, target 0: 1
Bounded [2] x1, target 4: 0
~~~

### Giải thích vì sao ba hàm không thể hoán đổi tùy ý

**countByLastStep:** Ở mỗi vị trí i, **đích i thu từ một đoạn nguồn** [i−R,i−L]. Mảng prefix đã có kết quả của mọi j<i. Mỗi dp[i] đọc đúng hai giá trị prefix và cập nhật prefix[i+1].

**countWithVariableJumps:** Ở vị trí i, **nguồn i phát tới một đoạn đích** [i+minStep[i],i+maxStep[i]]. Không cần duyệt từng đích để cộng dp[i]; thay vào đó ghi dấu +dp[i] ở đầu đoạn và −dp[i] ngay sau cuối đoạn. Khi tới đích k, running là tổng đóng góp đã phát vào k từ mọi nguồn trước đó.

**countBoundedCoins:** Một nguồn cho tổng s có thể đến từ **s−k×value** với nhiều k. Các nguồn này **không liên tiếp theo chỉ số s**, nhưng liên tiếp nếu chỉ xét một **lớp đồng dư modulo value**. Sliding window giữ tối đa limit+1 phần tử cùng lớp dư, tương ứng số lượng đồng mới k từ 0 đến limit.

Cả ba đều dùng phép **cộng** để gộp chuyển, nhưng **tập chỉ số nguồn, hướng cập nhật và thứ tự duyệt** khác nhau. Đây là những yếu tố phải xác định trước khi chọn cấu trúc tối ưu.

## 11. Chi tiết đúng/sai của Java và các trường hợp biên

### Dãy bước và tổng tiền tố

- **target=0:** dp[0]=1 cho đúng một dãy bước rỗng.
- **i<L:** không có bước cuối hợp lệ nên dp[i]=0.
- **L=R:** chỉ có một độ dài bước được phép; recurrence chỉ còn tối đa một nguồn.
- **L>R hoặc L≤0:** chương trình từ chối vì không đúng mô hình tiến lên và đoạn bước dương.
- **R>target:** không sao; left=max(0,i−R) cắt bỏ những vị trí âm.
- **Modulo:** prefix lưu phần dư, nên dp[i] phải được chuẩn hóa sau phép trừ.

### Nhảy theo vị trí xuất phát

- Mảng minStep/maxStep có độ dài **n**, mô tả quy tắc cho các vị trí **0..n−1**. Vị trí **n là đích**, không có quy tắc phát tiếp.
- Nếu n=0, hai mảng rỗng tạo dp=[1]: đã đứng ở đích mà không cần bước.
- Mọi bước phải **dương**, nên mọi chuyển đi từ chỉ số nhỏ sang chỉ số lớn; không có phụ thuộc ngược.
- Đoạn đích bị cắt ở n; các đích lớn hơn n không ảnh hưởng đến bài hỏi đúng vị trí n.
- Dùng kiểu **long** khi cộng i+maxStep[i] để tránh tràn int trước khi cắt n.
- Nếu hai nguồn khác nhau cùng đến một đích, các đường đi được **cộng số cách**; không chỉ đánh dấu boolean có/không.
- Trường hợp ways[i] modulo M bằng 0, phát đóng góp modulo 0 là đủ cho kết quả đếm modulo; nếu muốn biết đích có đạt được thật sự hay không, cần theo dõi khả thi riêng.

### Bounded coin change

- Mỗi loại tiền có **mệnh giá dương**, giới hạn **không âm**, và các loại phân biệt theo mệnh giá.
- Giới hạn 0 nghĩa là loại đó không được sử dụng; công thức chỉ giữ k=0.
- Nếu mệnh giá >T, chỉ lớp dư 0..T có thể xuất hiện; không cần cấp mảng cỡ mệnh giá.
- Khi T=0, cách chọn rỗng được đếm là 1.
- Hai loại cùng mệnh giá cần làm rõ bản chất: nếu là một loại tiền có tổng số lượng cho phép, có thể **gộp giới hạn** trước; nếu là các nhóm vật phân biệt, mô hình đếm theo nhóm có thể khác. Ví dụ từ điển đầu vào lặp mệnh giá không tự tạo một tổ hợp mới.
- Nếu số cách phải tính chính xác mà không lấy modulo, đổi cấu trúc số sang BigInteger và xét lại chi phí cộng/trừ; không giữ kiểu long khi có nguy cơ tràn.

## 12. Chứng minh tính đúng của mảng hiệu đối với phép chuyển theo đoạn

Đặt **dp[i]** là số đường đi từ 0 tới i. Mỗi nguồn j<i đã tính xong sẽ phát dp[j] đến mọi đích nằm trong khoảng hợp lệ của j.

Một phép cập nhật diff[l]+=x, diff[r+1]−=x tạo ra tổng chạy:

- **0** trước l;
- **x** tại mọi chỉ số từ l đến r;
- **0** sau r.

Đây là hệ quả của phép cộng tiền tố trên mảng hiệu: dấu + bắt đầu hiệu lực tại l, dấu − kết thúc hiệu lực sau r. Với nhiều đoạn phát, hiệu ứng cộng tuyến tính nên tổng chạy tại i bằng **tổng dp[j] qua mọi nguồn j<i có cạnh j→i**.

Cơ sở dp[0]=1. Do tất cả các cạnh đều đi tới chỉ số lớn hơn, khi duyệt i tăng dần, mọi nguồn j<i đã phát xong trước lúc xác định dp[i]. Bởi vậy dp[i] nhận **đúng tổng các đường đi đến i**, không thiếu, không lặp; điều này chứng minh tính đúng bằng quy nạp theo i.

**Vì sao không dùng diff để tự động xử lý mọi loại DP?** Diff hỗ trợ phép **cộng cùng một giá trị lên một đoạn đích**, không trực tiếp thực hiện **min của nhiều ứng viên khác nhau**, so sánh tối ưu có điều kiện, hoặc các chuyển có hệ số phụ thuộc từng đích mà chưa được phân tích. Tương tự, prefix sum không tự giải min đoạn.

## 13. Chứng minh cửa sổ đồng dư cho bounded knapsack

Khi thêm loại tiền (w,c), mọi tổ hợp tạo tổng s có **một số lượng k đồng loại w xác định duy nhất**, 0≤k≤c. Sau khi bỏ k đồng loại w, phần còn lại dùng các loại đã xử lý trước đó, có tổng s−kw.

Do đó công thức:

**next[s] = ∑_{k=0..min(c,⌊s/w⌋)} prev[s−kw]**

bao phủ đầy đủ các tổ hợp và các nhóm theo k không trùng nhau.

Xét riêng phần dư r=s mod w. Viết **s=r+t×w**, thì các nguồn trong công thức có dạng:

**r+t×w, r+(t−1)×w, ..., r+(t−c)×w**,

bỏ các chỉ số âm. Chúng là **c+1 phần tử liên tiếp** trong dãy prev thuộc cùng phần dư r.

Khi t tăng lên 1:

- Thêm phần tử mới **prev[r+t×w]**.
- Nếu t−c−1≥0, bỏ phần tử đã quá c bước phía sau: **prev[r+(t−c−1)×w]**.

Đó chính là công thức window trong Java, vì:

**r+(t−c−1)×w = s−(c+1)×w**.

Mỗi s trong 0..T thuộc đúng một lớp dư r; các vòng quét không bỏ sót hoặc ghi đè hai lần. Sau khi hoàn thành loại tiền, next trở thành previous để chuyển sang loại tiếp theo, bảo đảm **đếm tổ hợp theo từng loại**, không phân biệt thứ tự đồng tiền.

**Điểm cần lưu ý:** nếu viết chung trong một mảng rồi dùng ngay giá trị đang được cập nhật thay cho previous[s−kw], ta có thể **tái sử dụng cùng loại tiền vượt giới hạn** hoặc đếm sai. Mã dùng **previous và next tách biệt** cho mỗi loại.

## 14. Tổng tiền tố có trọng số: mở rộng khi đóng góp không đều

Không phải lúc nào công thức cũng là tổng dp[j] với hệ số 1. Giả sử:

**dp[i] = ∑_{j=l(i)..r(i)} (a×i + b×j) × dp[j]**,

với a,b là các hằng số và các nguồn j<i.

Ta có thể tách thành:

**dp[i] = a×i × ∑dp[j] + b × ∑j×dp[j]** trên cùng khoảng.

Duy trì **hai mảng prefix**:

**P[t] = ∑_{0≤j<t} dp[j]**,

**W[t] = ∑_{0≤j<t} j×dp[j]**.

Khi đó:

**dp[i] = a×i×(P[r+1]−P[l]) + b×(W[r+1]−W[l])**.

Mỗi trạng thái vẫn có thể được tính O(1) nếu các hệ số phù hợp phép số học dùng và các prefix đã được xây trước.

Sau khi tính dp[i]:

**P[i+1]=P[i]+dp[i]**,

**W[i+1]=W[i]+i×dp[i]**.

Đây là một mẫu tổng quát quan trọng: khi trọng số phụ thuộc vào j theo **một tổ hợp tuyến tính của vài hàm đơn giản**, ta có thể giữ **một prefix cho mỗi thành phần**.

Ví dụ nếu trọng số theo j là đa thức bậc hai **A+Bj+Cj²**, có thể cần prefix của **dp[j]**, **j×dp[j]** và **j²×dp[j]**, miễn việc mở rộng phù hợp giới hạn số và modulo.

**Không suy rằng mọi hàm trọng số đều tách được thành ít thành phần.** Nếu hệ số phụ thuộc tùy ý vào cả i và j, một số ít mảng prefix có thể không đủ.

## 15. Cộng không phải phép tổng hợp duy nhất của DP

Tối ưu chuyển theo đoạn thường dựa vào một cấu trúc đại số phù hợp với câu hỏi.

| Công thức chuyển trên khoảng nguồn | Kỹ thuật thường phù hợp | Lưu ý |
| --- | --- | --- |
| **Tổng dp[j]** | Prefix sum | Trả bằng hiệu P[r+1]−P[l] |
| **XOR dp[j]** | Prefix XOR | Dùng phép XOR hai prefix |
| **Đếm số trạng thái reachable[j]** | Prefix count của boolean | Đếm số true trong đoạn |
| **Có tồn tại j đạt được? (OR)** | Prefix count, hoặc cấu trúc hỗ trợ OR | Chỉ cần số true trong đoạn >0 |
| **Min dp[j]** | Monotonic deque nếu cửa sổ trượt; sparse table nếu dữ liệu tĩnh | Không lấy min của hai prefix rồi trừ |
| **Max dp[j]** | Monotonic deque, segment tree, cấu trúc phù hợp | Phụ thuộc mô hình cập nhật và truy vấn |
| **Tổng một số lớp đồng dư** | Prefix/sliding window riêng từng phần dư | Tập nguồn không liên tiếp trong chỉ số gốc |
| **Gộp trạng thái phức tạp có phép kết hợp** | Segment tree hoặc monoid phù hợp | Có thể không tồn tại phép nghịch đảo |

### Vì sao không dùng prefix min để tính min đoạn?

Giả sử biết **minimum của dp[0..r)** và minimum của dp[0..l)**. Không có phép trừ nào để loại bỏ minimum trước l và thu minimum còn lại. Ví dụ dãy [1,10,9] và [1,2,9] có cùng min các tiền tố dài 1 và dài 3, nhưng min trên đoạn [1,3) khác nhau (9 so với 2).

**Max/min không có phép nghịch đảo kiểu phép cộng**, nên cần cấu trúc khác. Nếu khoảng nguồn [i−R,i−L] dịch đều, dùng **monotonic deque** để giữ ứng viên cực trị trên cửa sổ có thể giảm từ O(nR) xuống O(n) tương tự tinh thần sliding window, nhưng cần chứng minh quy tắc loại bỏ phần tử và xử lý chỉ số hết hạn.

## 16. Prefix sum, Fenwick tree và segment tree: chọn cái nào?

**Prefix sum theo DP** đặc biệt mạnh khi:

- Các dp[i] được **chốt** một lần theo i tăng dần.
- Mọi truy vấn dp[i] chỉ dùng các trạng thái **đã chốt j<i**.
- Cần tổng các đoạn của các trạng thái đã chốt.
- Không sửa lại dp[j] đã tính.

Khi đó chỉ cần cập nhật P[i+1] sau mỗi trạng thái; cả xây và truy vấn có tổng **O(n)**.

**Fenwick tree (Binary Indexed Tree)** hữu ích khi:

- Cần cập nhật **một vị trí đã xử lý** nhiều lần.
- Có truy vấn tổng tiền tố/tổng đoạn xen kẽ.
- Không thể chỉ nối thêm giá trị mới ở cuối một prefix cố định.

Khi dùng Fenwick, cập nhật điểm và truy vấn prefix thường **O(log n)**. Nếu DP có phép chuyển cộng đến nhiều vị trí không theo thứ tự thuận lợi, Fenwick có thể phù hợp hơn mảng P.

**Segment tree** dùng được khi cần gộp những phép **min/max/sum** hoặc một **trạng thái nhiều trường**, đồng thời có cập nhật; thời gian thường O(log n) mỗi truy vấn/cập nhật điểm.

**Difference array** phù hợp đặc biệt nếu các chuyển là **cộng vào một đoạn đích** và ta sẽ duyệt lần lượt các đích để tích lũy; nó có thể đưa chi phí mỗi lần phát đoạn xuống O(1), như mục 8.

**Không chọn cấu trúc nặng hơn nếu không cần.** Nếu các trạng thái chỉ được bổ sung tuần tự và câu hỏi luôn là tổng một đoạn nguồn đã chốt, mảng P thường đơn giản và nhanh hơn Fenwick/segment tree về cả thời gian và độ khó code.

## 17. Hai chiều và các mẫu chuyển theo hình chữ nhật

Ý tưởng prefix có thể mở rộng sang DP hai chiều nếu nhiều chuyển là **tổng trên một hình chữ nhật của các trạng thái đã hoàn tất**.

Ví dụ một trạng thái dp[i][j] cần tổng các dp[x][y] trong hình chữ nhật:

**x∈[r1,r2), y∈[c1,c2)**,

và toàn bộ những trạng thái nguồn ấy **đã được tính trước** theo thứ tự DP được chọn.

Đặt tổng tiền tố hai chiều:

**P[i+1][j+1] = dp[i][j] + P[i][j+1] + P[i+1][j] − P[i][j]**.

Khi đó tổng hình chữ nhật là:

**P[r2][c2] − P[r1][c2] − P[r2][c1] + P[r1][c1]**.

Nếu chỉ cần dùng kết quả modulo M, chuẩn hóa sau khi cộng/trừ.

### Cảnh báo về phụ thuộc

Công thức hình chữ nhật O(1) **không tự bảo đảm một quy hoạch động hai chiều hợp lệ**. Nếu hình chữ nhật chứa **chính dp[i][j]** hoặc các trạng thái ở “tương lai” chưa tính, việc gộp sẽ tạo phụ thuộc vòng hoặc đọc giá trị chưa sẵn sàng.

Hãy viết **thứ tự tô-pô** của các trạng thái trước, rồi mới xây cấu trúc prefix theo đúng thứ tự ấy. Trong vài bài, cách dùng **DP cộng dồn theo hàng** hoặc mảng prefix chỉ trên những hàng đã hoàn thành dễ đúng hơn việc tạo một bảng P 2D toàn cục ngay từ đầu.

## 18. Lỗi thường gặp khi tối ưu chuyển theo đoạn

1. **Nhầm tổng tiền tố dữ liệu với tổng tiền tố DP.** Một prefix của mảng đầu vào không tự trả tổng các cách dp[j].
2. **Dùng sai đoạn đóng/mở.** Tổng dp[l..r] phải là P[r+1]−P[l], không phải P[r]−P[l].
3. **Không khởi tạo dp[0]=1 cho bài đếm dãy bước.** Làm mất mọi cách xuất phát từ 0.
4. **Quên cập nhật P[i+1] sau khi tính dp[i].** Những trạng thái sau đọc prefix thiếu dp[i].
5. **Đọc P[i+1] để tính dp[i] khi L=0.** Tự phụ thuộc vào trạng thái đang tính; không phải DP một chiều tiến lên chuẩn.
6. **Cho phép chỉ số nguồn âm.** Phải cắt left bằng max(0,i−R), hoặc kiểm tra từng j.
7. **Không xử lý khoảng rỗng.** Khi right<left, tổng bằng 0, không được truy cập P[right+1] vô nghĩa.
8. **Gộp cả đoạn khi chỉ một số chỉ số trong đoạn được phép chuyển.** Kết quả đếm thừa; phải phân hoạch nguồn đúng điều kiện.
9. **Tính một trạng thái nhiều lần vì các khoảng chồng lấn.** Hợp các khoảng phải được xử lý theo đúng ngữ nghĩa có/không tính trùng.
10. **Áp dụng công thức modulo rồi để kết quả âm trong Java.** Chuẩn hóa phép trừ.
11. **Dùng kết quả đếm modulo 0 để kết luận vô nghiệm.** Số cách thật có thể khác 0.
12. **Cộng các giá trị trước modulo bằng int khi có nguy cơ tràn.** Chọn long hoặc phép toán an toàn với giới hạn M.
13. **Dùng prefix subtraction để lấy min/max.** Không có phép nghịch đảo như cộng.
14. **Đảo hướng chuyển nguồn/đích.** “Đích hỏi tổng từ đoạn nguồn” khác “nguồn cộng vào đoạn đích”; một bên hợp prefix, bên kia hợp difference array.
15. **Quên dấu trừ tại r+1 trong mảng hiệu.** Đóng góp bị kéo dài sang các đích ngoài khoảng.
16. **Phát chuyển đến i hoặc chỉ số nhỏ hơn i.** Nếu không có cấu trúc xử lý vòng, thứ tự trái sang phải không còn hợp lệ.
17. **Duyệt bounded knapsack như unbounded coin.** Có thể sử dụng vượt giới hạn số lượng một loại tiền.
18. **Nhầm hai giá trị cùng mệnh giá là hai loại phân biệt.** Cần xác định có đếm theo loại/vật hay theo tổ hợp mệnh giá.
19. **Quên phần tử s−(c+1)w hết hạn khi trượt cửa sổ.** Sẽ dùng quá c đồng.
20. **Chỉ xử lý phần dư 0 của bounded coin.** Mọi s đều thuộc một lớp s mod w; bỏ lớp khác làm sai kết quả.
21. **Không tách prev và next theo loại tiền.** Đọc giá trị đã cập nhật của cùng loại có thể làm trùng cách hoặc vượt giới hạn.
22. **Tuyên bố O(n) nhưng thao tác gộp không hằng thời gian.** BigInteger, cấu trúc trạng thái lớn hoặc map phức tạp có thể tăng chi phí.
23. **Không tính giới hạn bộ nhớ.** Prefix một chiều là O(n), prefix 2D là O(RC), còn nhiều lớp dư có thể cần cấu trúc quản lý hợp lý.
24. **Tối ưu trước khi chứng minh recurrence.** Một thuật toán nhanh cho công thức chuyển sai vẫn trả đáp án sai.

## 19. Kiểm thử bằng cách đối chiếu với phép chuyển trực tiếp

Để bảo đảm tối ưu chỉ thay đổi **cách tính**, không thay đổi **kết quả**, nên giữ một phiên bản chậm nhưng rõ ràng cho các ca nhỏ.

### Bài bước nhảy cố định

~~~text
slow[0] = 1
for i = 1..n:
    slow[i] = 0
    for d = L..R:
        if i-d >= 0:
            slow[i] += slow[i-d]
~~~

Đối chiếu **mọi slow[i]** với dp[i] tính từ prefix, không chỉ đối chiếu riêng dp[n].

### Bài nguồn phát tới đoạn đích

~~~text
slow[0] = 1
for i = 0..n-1:
    for d = minStep[i]..maxStep[i]:
        if i+d <= n:
            slow[i+d] += slow[i]
~~~

Vì mọi bước dương, nguồn i được xử lý trước đích, nên đây là một chuẩn tham chiếu đúng.

### Bài bounded coin

~~~text
prev[0] = 1; các prev[s>0] = 0

for mỗi loại (w,c):
    next[*] = 0
    for s = 0..T:
        for k = 0..c:
            if k*w <= s:
                next[s] += prev[s-k*w]
    prev = next
~~~

Phiên bản chậm có thể chạy trên T nhỏ để so với sliding-window DP. Nhớ dùng **cùng quy tắc modulo hoặc số nguyên chính xác** trong hai phiên bản so sánh.

### Những ca biên cần ưu tiên

| Trường hợp | Kết quả/điều cần kiểm tra |
| --- | --- |
| target=0 | Một cách rỗng, dp[0]=1 |
| L=R | Chỉ một loại bước nhảy |
| target<L | Không đến được đích dương |
| R rất lớn hơn target | Chặn nguồn âm và đích vượt n đúng |
| Vị trí có minStep>khoảng còn lại | Không phát tới đích vượt n |
| Nhiều nguồn cùng đích | Phải cộng tất cả |
| Khoảng nguồn rỗng | dp[i]=0 |
| Bounded loại tiền có limit=0 | Không thay đổi số cách |
| Bounded mệnh giá >target | Không chọn loại đó |
| Bounded target=0 | Một tổ hợp rỗng |
| Các đường chuyển có trọng số âm/zero-step | Không tự áp dụng DP tiến lên nếu phụ thuộc không còn acyclic |
| Modulo gây tổng bằng 0 | Không suy ra không có lời giải |

## 20. Bài tập tự kiểm tra

**Câu 1.** Cho dp[0..4]=[1,0,1,1,1], P[0]=0. Tổng dp[2]+dp[3]+dp[4] lấy bằng hiệu prefix nào?  
**Đáp án:** **P[5]−P[2]=4−1=3**.

**Câu 2.** Có các bước dài 2 hoặc 3, hỏi số cách đến vị trí 8.  
**Đáp án:** **4**: 2+2+2+2, 2+3+3, 3+2+3, 3+3+2.

**Câu 3.** Với bước cuối trong [L,R], khoảng chỉ số nguồn j cho dp[i] là gì?  
**Đáp án:** **[max(0,i−R), i−L]** nếu đầu trái không vượt đầu phải; nếu không thì không có nguồn.

**Câu 4.** Vì sao phải có L≥1 trong công thức DP tiến lên theo chỉ số i?  
**Đáp án:** Để mọi nguồn j=i−d < i, tức giá trị nguồn đã được tính trước; với bước 0 có thể xuất hiện tự phụ thuộc.

**Câu 5.** Cho P[7]=5 và P[3]=2 theo modulo M=7. Tổng dp[3..6] modulo 7 bằng bao nhiêu?  
**Đáp án:** **(5−2) mod 7 = 3**.

**Câu 6.** Nếu P[r+1]=2 và P[l]=5 theo modulo 7, tổng đoạn bằng bao nhiêu?  
**Đáp án:** **(2−5) mod 7 = 4**, không phải −3.

**Câu 7.** Khi một nguồn j có thể gửi cùng đóng góp tới các đích [l,r], cập nhật difference array thế nào?  
**Đáp án:** **diff[l]+=dp[j]**, **diff[r+1]−=dp[j]**; trong lượt quét đích lấy tổng chạy của diff.

**Câu 8.** Với biến thể nhảy theo vị trí xuất phát trong mục 8, dp[5] là bao nhiêu?  
**Đáp án:** **6** vì dp[5]=dp[2]+dp[3]+dp[4]=2+1+3.

**Câu 9.** Trong bounded coin, vì sao gộp theo phần dư s mod w?  
**Đáp án:** Các nguồn s−k×w của cùng một trạng thái đều có cùng phần dư modulo w; chúng là một cửa sổ liên tiếp khi duyệt lớp đồng dư ấy.

**Câu 10.** Với đồng tiền [1,2,3], giới hạn [2,2,1], tổng 5 có bao nhiêu tổ hợp?  
**Đáp án:** **3**: 3+2, 3+1+1, 2+2+1.

**Câu 11.** Có thể dùng prefix min rồi lấy hiệu để tìm min trên đoạn như khi tính tổng không?  
**Đáp án:** **Không**, vì phép min không có phép nghịch đảo loại bỏ tiền tố đã bỏ đi.

**Câu 12.** Nếu dp[i] nhận tổng từ hai đoạn nguồn rời nhau, có phải duyệt toàn bộ các chỉ số không?  
**Đáp án:** Không. Tính **hai hiệu prefix** rồi cộng; thời gian O(2)=O(1).

**Câu 13.** Khi một trạng thái j có đóng góp trọng số (a×i+b×j)×dp[j] vào dp[i], có thể giữ những prefix nào?  
**Đáp án:** Prefix của **dp[j]** và prefix của **j×dp[j]**, vì trọng số có thể tách thành hai thành phần tuyến tính.

**Câu 14.** Khi số cách đếm modulo M bằng 0, có thể kết luận trạng thái không đạt được không?  
**Đáp án:** Không. Số cách thật có thể là một bội số dương của M; cần theo dõi tính tồn tại riêng nếu bài yêu cầu.

## 21. Ghi nhớ

**Tổng tiền tố để gom các phép chuyển theo đoạn** là kỹ thuật nhìn công thức DP ở cấp **tập tiền nhiệm**:

- Nếu **dp[i] là tổng của một đoạn trạng thái trước**, duy trì **P[t]=sum(dp[0..t))** và tính **dp[i]=P[right+1]−P[left]** trong O(1).
- Nếu **dp[i] phải cộng đến cả đoạn đích**, dùng **difference array**: thêm ở đầu đoạn, trừ ngay sau cuối đoạn, quét một lần để nhận tổng đóng góp.
- Nếu nguồn có dạng **s,s−w,s−2w,...**, hãy **nhóm theo lớp đồng dư modulo w**; bounded knapsack có thể dùng cửa sổ trượt thay vì duyệt từng số lượng k.
- Khi kết quả đếm lấy modulo, **chuẩn hóa phép trừ** và không đánh đồng số cách modulo 0 với trạng thái vô nghiệm.
- **Chứng minh tập nguồn chính xác và thứ tự phụ thuộc đúng** trước khi tối ưu: không cộng nhầm chuyển bất hợp lệ, không tự phụ thuộc, không đếm trùng.
- Tối ưu chỉ làm giảm chi phí **tính cùng một recurrence**, không được âm thầm thay đổi ý nghĩa của dp hay cách đếm lời giải.

Khi gặp một DP quá chậm vì **mỗi trạng thái đều phải lặp lại phép cộng trên một vùng chỉ số**, hãy thử **đổi biến để các tiền nhiệm thành một đoạn**, rồi đặt câu hỏi: “Có thể lấy toàn bộ đoạn này bằng **hai tổng tiền tố** hay không?”. Đây thường là bước biến một lời giải O(n²) thành **O(n)** một cách đơn giản và có chứng minh.
