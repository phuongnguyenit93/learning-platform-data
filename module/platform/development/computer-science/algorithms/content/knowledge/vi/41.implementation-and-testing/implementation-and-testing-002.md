# Chỉ số, khoảng nửa mở và quy tắc quản lý biên

**Lỗi lệch một đơn vị (off-by-one error)** là nguyên nhân phổ biến khiến một thuật toán đúng về ý tưởng nhưng sai khi cài đặt. Nó xuất hiện ở vòng lặp, truy vấn đoạn, binary search, two pointers, prefix sum, cây đoạn, chia để trị, xử lý chuỗi Unicode, duyệt ma trận và phân chia công việc cho nhiều worker.

Một quy ước nhất quán giúp giảm đáng kể loại lỗi này: **biểu diễn đoạn trong thuật toán bằng khoảng nửa mở [l,r)**, nghĩa là **l thuộc đoạn còn r không thuộc đoạn**.

Cho mảng dài n:

**0 ≤ l ≤ r ≤ n**.

- **Chỉ số phần tử hợp lệ:** 0..n−1.
- **Vị trí biên hợp lệ:** 0..n.
- **Độ dài [l,r):** r−l.
- **Đoạn rỗng:** l=r, kể cả [n,n).
- **Toàn mảng:** [0,n).
- **Một phần tử tại i:** [i,i+1), với 0≤i<n.

Bài thuộc nhóm **Cài đặt và kiểm thử**, nên trọng tâm không chỉ là ký hiệu toán học mà còn là **quy tắc quản lý biến biên, invariant và chứng minh dừng, validation, chuyển đổi chỉ số 0-based/1-based, thiết kế API Java 17, ca kiểm thử rỗng và oracle độc lập**.

Chương trình Java 17+ hoàn chỉnh minh họa tổng tiền tố, đổi đoạn đóng, binary search, slice/reverse, mảng hiệu, sliding window, segment tree và prefix 2D; phần đầu ra mẫu được kiểm tra bằng mô phỏng và phép tính độc lập.

## 1. Chỉ số phần tử khác vị trí cắt

Cho mảng n=6:

~~~text
Phần tử:      a[0]   a[1]   a[2]   a[3]   a[4]   a[5]
Giá trị:        3      -2      5      7      0     -4

Vị trí cắt:   0      1      2      3      4      5      6
              |  3   | -2   |  5   |  7   |  0   | -4   |
~~~

Có **6 phần tử** nhưng **7 vị trí cắt**. Khoảng [l,r) gồm các phần tử nằm giữa vị trí cắt l và vị trí cắt r.

- [1,4) chứa a[1],a[2],a[3].
- [0,6) chứa tất cả phần tử.
- [4,4) rỗng.
- [6,6) cũng rỗng và **hợp lệ**, dù **a[6] không tồn tại**.

Rất nhiều bug xuất hiện vì coi **right boundary n** cũng là một **index phần tử**. Nó chỉ là **điểm ngay sau phần tử cuối**.

### Ba miền cần kiểm tra riêng

- Element index i: **0≤i<n**.
- Boundary b: **0≤b≤n**.
- Range [l,r): **0≤l≤r≤n**.

Không nên dùng một hàm checkIndex cho cả ba.

## 2. Vì sao khoảng nửa mở dễ duy trì hơn?

Một vòng lặp nửa mở:

~~~java
for (int i = left; i < right; i++) {
    consume(a[i]);
}
~~~

Chạy đúng **right−left lần** nếu input hợp lệ.

- left=right: không chạy.
- left=0,right=n: duyệt toàn bộ.
- left=i,right=i+1: duyệt đúng một phần tử.

Không cần nhánh đặc biệt khi đoạn bắt đầu từ 0 hoặc kết thúc ở n.

### Ghép đoạn không trùng phần tử

Với l≤m≤r:

**[l,r) = [l,m) ∪ [m,r)**.

Ví dụ:

~~~text
[0,6) = [0,2) nối [2,6)
Phần trái:   phần tử 0,1
Phần phải:   phần tử 2,3,4,5
~~~

Phần tử m thuộc đoạn phải, không bị đếm hai lần. Đây là cơ sở thuận tiện cho merge sort, chia khối, phân trang, truy vấn dạng cây và parallel partition.

**Lưu ý:** không phải mọi đề bài và thư viện đều dùng nửa mở; điều đúng là **đổi về một convention tại ranh giới API rồi dùng nhất quán bên trong**.

## 3. Chuyển giữa 0-based, 1-based, đóng và nửa mở

Các cách mô tả phổ biến:

| Input | Miền phần tử được lấy | Đổi sang 0-based [l,r) |
| --- | --- | --- |
| 0-based [l,r) | l..r−1 | Giữ nguyên |
| 0-based đóng [l,r] | l..r | [l,r+1) |
| 1-based đóng [L,R] | thứ L..R | [L−1,R) |

Điều kiện để chuyển:

- 0-based đóng: **0≤l≤r<n**.
- 1-based đóng: **1≤L≤R≤n**.
- 0-based nửa mở: **0≤l≤r≤n**.

Ví dụ với:

~~~text
a = [3, -2, 5, 7, 0, -4]
~~~

- Đoạn 0-based đóng [2,4] = [5,7,0] = nửa mở [2,5).
- Đoạn 1-based đóng [2,5] = [−2,5,7,0] = nửa mở [1,5).
- Đoạn 1-based đóng [1,6] = toàn mảng [0,6).

### Validation trước phép cộng 1

Nếu chưa kiểm tra r<n, phép **r+1** có thể overflow với giá trị int không hợp lệ. Quy tắc an toàn:

1. Kiểm tra đầu vào **theo convention gốc**.
2. Chỉ chuyển biên khi đã hợp lệ.
3. Sử dụng half-open trong thuật toán nội bộ.

Với 1-based [L,R], việc biến R thành exclusive boundary không cần cộng thêm một lần nữa.

## 4. Đoạn rỗng, một phần tử và toàn mảng

Đây là ba loại ca tối thiểu mọi hàm xử lý đoạn phải xác định.

**Đoạn rỗng [i,i):**

- Length 0.
- Không được đọc a[i].
- Tổng bằng 0.
- Đếm phần tử bằng 0.
- Sort/reverse/slice không xử lý phần tử nào.
- [n,n) cũng rỗng.

**Đoạn một phần tử [i,i+1):**

- Length 1.
- Duyệt đúng một phần tử.
- Tổng bằng a[i].
- Reverse giữ nguyên thứ tự.

**Toàn mảng [0,n):**

- Length n.
- Vị trí cuối được đọc là n−1, không phải n.
- Khi n=0, toàn mảng cũng là đoạn rỗng [0,0).

| n | Đoạn | Hợp lệ? | Length |
| ---: | --- | :---: | ---: |
| 0 | [0,0) | Có | 0 |
| 1 | [0,0) | Có | 0 |
| 1 | [0,1) | Có | 1 |
| 1 | [1,1) | Có | 0 |
| 6 | [2,5) | Có | 3 |
| 6 | [6,6) | Có | 0 |
| 6 | [6,7) | Không | — |
| 6 | [4,3) | Không | — |
| 6 | [−1,1) | Không | — |

Nếu một bài chỉ kiểm thử [0,n) mà không kiểm tra [n,n), ca biên vẫn chưa đầy đủ.

## 5. Hàm kiểm tra đoạn và chỉ số riêng biệt

Một helper cho đoạn half-open:

~~~java
static void checkRange(int n, int left, int right) {
    if (left < 0 || right < left || right > n) {
        throw new IndexOutOfBoundsException(
                "Expected 0 <= left <= right <= n");
    }
}
~~~

Với n là length không âm, ba điều kiện trên đủ để đảm bảo 0≤left≤right≤n.

Một helper cho **element index**:

~~~java
static void checkIndex(int n, int index) {
    if (index < 0 || index >= n) {
        throw new IndexOutOfBoundsException(index);
    }
}
~~~

### Vì sao không tự chữa input sai?

Tự swap left/right, clamp chỉ số âm về 0 hay clamp right về n có thể làm output khác yêu cầu của caller và giấu bug.

Nếu ứng dụng thực sự cần clamp, hãy xây **một API riêng ghi rõ clamping**. Với API truy vấn chỉ số chính xác, **từ chối input sai** thường dễ kiểm thử và bảo trì hơn.

## 6. Loop invariant: vùng đã xử lý và chưa xử lý

Với vòng:

~~~java
for (int i = left; i < right; i++) {
    consume(a[i]);
}
~~~

Bất biến đầu mỗi vòng:

**[left,i) đã xử lý đúng một lần; [i,right) chưa xử lý.**

Cơ sở: khi i=left, vùng đã xử lý rỗng.

Bước lặp: xử lý a[i], rồi tăng i. Vùng đã xử lý trở thành [left,i+1).

Khi i=right: vùng chưa xử lý rỗng, kết quả bao trùm đúng [left,right).

### Điều kiện dừng

Nếu dùng while:

~~~text
i = left
while i < right:
    process a[i]
    i = i + 1
~~~

Khoảng cách **right−i** là đại lượng giảm nghiêm ngặt và không âm. Nếu i không tăng, có thể loop vô hạn; nếu tăng trước xử lý, có thể bỏ left và đọc right.

## 7. Di chuyển hai biên của cửa sổ [L,R)

Nhiều thuật toán dùng một cửa sổ hiện hành:

**a[L],a[L+1],...,a[R−1]**.

Các chuyển động chuẩn:

~~~text
Mở rộng trái:   add(--L)
Mở rộng phải:   add(R++)
Thu hẹp trái:   remove(L++)
Thu hẹp phải:   remove(--R)
~~~

Tại mỗi bước add/remove, trạng thái thống kê (sum, frequency, distinct...) phải được cập nhật đồng bộ với biên.

Một cách chuyển từ cửa sổ hiện tại [L,R) sang [l,r) an toàn cả với các đoạn không giao nhau:

~~~text
while L > l:  add(--L)
while R < r:  add(R++)
while L < l:  remove(L++)
while R > r:  remove(--R)
~~~

**Mở rộng trước khi thu hẹp** ngăn việc remove một phần tử chưa ở cửa sổ.

Ví dụ hiện tại [0,2), muốn chuyển sang [5,5). Nếu thu L tới 5 khi R vẫn là 2, sẽ cố remove a[2],a[3],a[4] chưa resident. Với thứ tự trên, ta mở R tới 5 rồi mới thu L tới 5.

### Điều kiện của từng thao tác

- add(--L) chỉ khi có vị trí L−1 hợp lệ.
- add(R++) chỉ khi R<n.
- remove(L++) chỉ khi L<R.
- remove(--R) chỉ khi L<R.

Một bất biến useful là **freq[v] phản ánh đúng số lần giá trị v trong [L,R)**, không chỉ đảm bảo biến L/R bằng số mong muốn.

## 8. Prefix sum với P có n+1 phần tử

Cho a độ dài n:

**P[0]=0**.

**P[i+1]=P[i]+a[i]**.

Khi đó:

**sum([l,r))=P[r]−P[l]**.

Ví dụ:

~~~text
a = [3, -2, 5, 7, 0, -4]
P = [0, 3, 1, 6, 13, 13, 9]

sum([1,5)) = 13 - 3 = 10
sum([2,2)) = 1 - 1 = 0
sum([0,6)) = 9 - 0 = 9
~~~

P[6] hợp lệ vì P dài 7, dù a[6] không tồn tại.

### Đoạn đóng

0-based đóng [l,r]:

**P[r+1]−P[l]**.

1-based đóng [L,R]:

**P[R]−P[L−1]**.

Validation theo hợp đồng trước khi chuyển đổi.

### Đánh đổi

Prefix sum xây O(n), truy vấn O(1) trên dữ liệu tĩnh. Nếu sửa a, prefix cũ là **snapshot lỗi thời**; phải cập nhật/rebuild hoặc dùng cấu trúc động.

## 9. Mảng hiệu dùng đúng hai vị trí cắt

Để cộng Δ vào mọi phần tử [l,r) khi nhiều cập nhật được gom rồi materialize, tạo difference array D dài n+1, ban đầu 0:

**D[l]+=Δ**.

**D[r]−=Δ**.

Duyệt từ trái sang phải, tổng tích lũy của D biểu thị lượng cần cộng vào từng a[i].

Ví dụ:

~~~text
a ban đầu: [3, -2, 5, 7, 0, -4]

Cộng +3 trên [1,4)
Cộng -2 trên [3,6)

Kết quả:  [3, 1, 8, 8, -2, -6]
~~~

Phần tử tại index=4 không nhận +3 vì r=4 là **exclusive**. Phần tử tại index=3 nhận cả hai updates.

### D[n] và đoạn rỗng

Với r=n, D[n] là vị trí đánh dấu kết thúc, dù khi khôi phục a[0..n−1] không dùng D[n] cho bất kỳ phần tử nào.

Với l=r, update không đổi dữ liệu. Có thể bỏ qua hai phép ghi D[l]+=Δ và D[r]−=Δ.

Difference array không tự hỗ trợ O(1) cho mọi query tổng xen kẽ updates; nó phù hợp khi **biết trước updates và dựng kết quả sau cùng**.

## 10. Lower bound: binary search trên miền biên

Giả sử a được sắp **không giảm**. **lowerBound(target)** là chỉ số đầu tiên i có:

**a[i]≥target**.

Nếu không có phần tử nào thỏa, đáp án là **n**, biểu diễn vị trí chèn cuối.

~~~java
int lo = 0;
int hi = a.length;

while (lo < hi) {
    int mid = lo + (hi - lo) / 2;

    if (a[mid] < target) {
        lo = mid + 1;
    } else {
        hi = mid;
    }
}

return lo;
~~~

### Vì sao hi=n hợp lệ?

lo/hi là **biên của vùng ứng viên**, không nhất thiết là element indexes sẽ được đọc. Khi lo<hi, midpoint luôn nhỏ hơn hi≤n nên a[mid] hợp lệ. Khi lo=hi=n, vòng dừng trước khi đọc a[n].

### Vì sao hi=mid, không phải mid−1?

Khi a[mid]≥target, mid **vẫn có thể là phần tử đầu tiên** thỏa điều kiện nên phải giữ nó. Trong khi khi a[mid]<target, mid đã bị loại và lo chuyển tới mid+1.

## 11. Bất biến và chứng minh dừng binary search

Với lower bound trên sorted array:

- Mọi i<lo có a[i]<target.
- Mọi i≥hi với i<n có a[i]≥target.
- Đáp án boundary đang nằm trong **[lo,hi]**.

Cơ sở: lo=0,hi=n, hai vùng phân loại đều rỗng.

Nếu a[mid]<target, vì sorted nên mọi i≤mid cũng nhỏ hơn target: đặt lo=mid+1.

Nếu a[mid]≥target, vì sorted nên mọi i≥mid cũng ≥target: đặt hi=mid.

Khi lo<hi, ta có lo≤mid<hi. Mỗi nhánh giảm **hi−lo**, nên thuật toán kết thúc tại lo=hi là lower bound đúng.

### Lỗi vô hạn khi dùng lo=mid

Với hi=lo+1, mid=lo. Nếu nhánh không thỏa dùng lo=mid thì không tiến, vòng lặp có thể chạy mãi.

Phải dùng **lo=mid+1** trong biến thể này, trừ khi toàn bộ invariant và điều kiện vòng được thiết kế lại.

### Midpoint và overflow

**mid=lo+(hi−lo)/2** an toàn hơn (lo+hi)/2 khi lo,hi là index/boundary không âm trong [0,n], hi≥lo.

Nếu search trên miền tọa độ signed rộng có thể âm hoặc hiệu hi−lo vượt int, cần xử lý kiểu số và overflow riêng. Không có công thức midpoint đơn giản nào an toàn cho mọi miền tùy ý mà không xét giả thiết.

## 12. Upper bound và khoảng bằng target

**upperBound(target)** là vị trí đầu tiên i có:

**a[i]>target**.

Dùng cùng binary search nhưng thay nhánh:

~~~java
if (a[mid] <= target) {
    lo = mid + 1;
} else {
    hi = mid;
}
~~~

Với:

~~~text
a = [-3, -1, 0, 0, 2, 2, 5]
idx:  0   1  2  3  4  5  6
~~~

- lowerBound(2)=4.
- upperBound(2)=6.
- Mọi phần tử bằng 2 nằm tại **[4,6)**.
- Số lần xuất hiện của 2 = 6−4=2.
- lowerBound(4)=6.
- upperBound(8)=7.

**Arrays.binarySearch** trong Java không đảm bảo trả **vị trí đầu của một nhóm duplicates**. Nếu cần cả hai biên bằng nhau, dùng lower/upper bound đúng hợp đồng; không lấy bất kỳ vị trí match nào làm lower bound.

## 13. Two pointers trên mảng không âm

Xét bài **đếm số đoạn con không rỗng có tổng ≤K** khi mọi a[i]≥0.

Ta duy trì một cửa sổ gồm các phần tử [left,right+1) sau khi vừa thêm a[right]:

~~~text
if K < 0:
    return 0

left = 0
sum = 0
count = 0

for right = 0 .. n-1:
    sum += a[right]

    while sum > K:
        sum -= a[left]
        left++

    count += right-left+1
~~~

Khi tổng đã ≤K, mọi đoạn kết thúc tại right và bắt đầu từ left đến right đều thỏa, vì bỏ bớt những phần tử không âm không làm tổng tăng.

Có đúng **right−left+1** đoạn hợp lệ kết thúc tại right.

### Vì sao phải kiểm tra số âm?

Nếu một phần tử âm, loại nó khỏi bên trái có thể **làm tổng tăng**. Tính đơn điệu để dịch left không còn đúng; thuật toán có thể đếm sai.

### Trường hợp a[right]>K

Nếu một phần tử lớn hơn K, left có thể tiến đến right+1. Khi ấy cửa sổ rỗng, số đoạn mới:

**right−left+1=0**.

Đó là kết quả đúng, không phải bug.

## 14. Ví dụ số 0 trong cửa sổ trượt

Cho:

~~~text
a = [1, 2, 1, 0]
~~~

Số đoạn con không rỗng có tổng ≤K:

| K | Số đoạn |
| ---: | ---: |
| −1 | 0 |
| 0 | 1 |
| 1 | 4 |
| 3 | 8 |
| 5 | 10 |

Với K=3:

- Bắt đầu index 0: 2 đoạn.
- Bắt đầu index 1: 3 đoạn.
- Bắt đầu index 2: 2 đoạn.
- Bắt đầu index 3: 1 đoạn.

Tổng **8**.

Số 0 cuối dãy tạo thêm những đoạn có cùng tổng nhưng **khác cặp biên [l,r)**. Không được gộp chúng thành một chỉ vì giá trị tổng trùng nhau.

Với n=4, tổng số đoạn con **không rỗng** là n(n+1)/2=10; K=5 đã lớn hơn hoặc bằng tổng toàn dãy nên toàn bộ 10 đoạn hợp lệ.

## 15. Iterative segment tree với truy vấn [l,r)

Một **segment tree dạng mảng** có thể lưu n lá tại indices:

**n,n+1,...,2n−1**.

Truy vấn tổng [l,r) chuyển thành:

**L=l+n, R=r+n**.

Trong khi L<R:

- Nếu L lẻ, cộng tree[L] và L++.
- Nếu R lẻ, giảm R trước rồi cộng tree[R].
- Dịch hai biên lên cha bằng L>>=1 và R>>=1.

~~~text
sum = 0
L = l+n
R = r+n

while L < R:
    if L odd:
        sum += tree[L]
        L++

    if R odd:
        R--
        sum += tree[R]

    L = L/2
    R = R/2
~~~

### Vì sao phải --R trước khi lấy tree[R]?

R là **exclusive boundary**, nên node ngay bên trái R mới thuộc phần đang xét. Đọc tree[R] có thể lấy một node ngoài truy vấn.

### Update một phần tử

Dùng **index hợp lệ 0≤i<n**, cập nhật lá tree[n+i] rồi lần lượt tính lại các ancestors. Đừng dùng checkRange để validate một element index vì nó cho phép boundary n.

### n=0

Với tree độ dài 0, query [0,0) có thể được định nghĩa trả 0 vì không vào vòng. Mọi thao tác set(index,...) phải bị từ chối.

## 16. Chia để trị bằng hai đoạn không giao nhau

Một hàm xử lý [l,r) thường chọn:

**m=l+floor((r−l)/2)**.

Chia thành:

**[l,m)** và **[m,r)**.

Khi r−l≥2, hai đoạn con đều nhỏ hơn đoạn cha, nên có thể đệ quy an toàn.

**Base case:** r−l≤1.

### Vì sao dễ chứng minh?

- Không có phần tử bỏ sót.
- Không có phần tử trùng hai nhánh.
- Tổng length của hai con = (m−l)+(r−m)=r−l.
- Khi length≥2, cả hai con ngắn hơn.

### Lỗi trộn convention

Nếu gọi [l,m] và [m,r] theo đoạn đóng trong khi code còn lại dùng half-open, phần tử m có thể bị tính hai lần. Nếu dùng đoạn đóng [l,r], cần chia [l,m] và [m+1,r] cùng base case tương ứng.

**Đừng lấy công thức của hai convention rồi ghép nửa này với nửa kia.**

## 17. Giao và độ dài các khoảng

Cho A=[l₁,r₁), B=[l₂,r₂).

Đặt:

**L=max(l₁,l₂)**.

**R=min(r₁,r₂)**.

Nếu L<R, giao là [L,R). Nếu L≥R, giao rỗng.

Độ dài giao:

**max(0,R−L)**.

Ví dụ:

~~~text
A = [1,5), B = [3,7)
Intersection = [3,5), length=2

A = [1,3), B = [3,6)
Intersection = empty, length=0
~~~

Hai khoảng [1,3) và [3,6) **chạm nhau tại boundary 3** nhưng không chia sẻ phần tử. Vì vậy có thể ghép thành [1,6) mà không gây overlap.

### Thời gian và tọa độ liên tục

Với interval timestamps [start,end), độ dài end−start đo **khoảng thời gian**, không phải số event. Đừng đồng nhất đếm vị trí nguyên với thời gian thực hoặc số bản ghi nếu domain khác nhau.

## 18. Prefix 2D dùng half-open ở cả hai trục

Với ma trận rows×cols, hình chữ nhật:

**[top,bottom)×[left,right)**

gồm các ô có top≤row<bottom, left≤col<right.

Tiền điều kiện:

**0≤top≤bottom≤rows**.

**0≤left≤right≤cols**.

Số ô:

**(bottom−top)(right−left)**.

Bảng prefix 2D P có kích thước (rows+1)×(cols+1). Khi ấy:

**rectSum = P[bottom][right]−P[top][right]−P[bottom][left]+P[top][left]**.

Ví dụ:

~~~text
1 2 3
4 5 6
7 8 9

[0,2) x [1,3):
2 3
5 6

Sum = 16
~~~

Hình [1,3)×[0,2) có tổng 24; hình [2,2)×[0,3) có tổng 0 vì chiều cao bằng 0.

Một công thức dùng bottom/right exclusive ở cả hai chiều tránh phải cộng 1 ở mỗi trục. Nếu input là hình chữ nhật đóng, nên convert cả bốn biên theo hợp đồng trước khi tính.

## 19. Java APIs dùng from-inclusive/to-exclusive

Một số API Java 17 quen thuộc:

| API | Convention |
| --- | --- |
| Arrays.copyOfRange(a,from,to) | [from,to) |
| Arrays.sort(a,from,to) | [from,to) |
| Arrays.fill(a,from,to,value) | [from,to) |
| Arrays.binarySearch(a,from,to,key) | Tìm trong [from,to) |
| String.substring(begin,end) | [begin,end) theo UTF-16 code units |
| List.subList(from,to) | [from,to), thường là view-backed |
| IntStream.range(start,end) | Exclusive end |
| IntStream.rangeClosed(start,end) | Inclusive end |

### copyOfRange có thể gây bất ngờ

Với một số overload mảng primitive, **Arrays.copyOfRange** có thể **đệm giá trị mặc định** khi to vượt quá độ dài nguồn, thay vì luôn từ chối ngay. Nếu contract yêu cầu đoạn nằm hoàn toàn trong mảng, gọi checkRange trước khi copy.

### subList có thể là view

List.subList thường trả **view được chống lưng bởi danh sách gốc**, không mặc nhiên là bản copy độc lập. Khi cần snapshot:

~~~java
List<Integer> snapshot =
        new ArrayList<>(source.subList(left, right));
~~~

Cần phân biệt **view** với **copy**, nhất là khi caller có thể sửa List gốc hoặc thay đổi cấu trúc danh sách.

## 20. String UTF-16 và biên của ký tự Unicode

Nhiều String APIs trong Java đánh index theo **UTF-16 code units**, không theo Unicode code points hay grapheme clusters.

Ví dụ:

~~~text
Chuỗi: "A😀B"

UTF-16 units:
A  = 1 unit
😀 = 2 units
B  = 1 unit

String.length() = 4
codePointCount(0,length()) = 3
~~~

**substring(1,3)** lấy đúng hai code units biểu diễn emoji. Nhưng **substring(1,2)** có thể cắt giữa surrogate pair, làm ra chuỗi chứa một surrogate không đầy đủ.

Nếu yêu cầu xử lý theo code points, chuyển code-point offset sang UTF-16 offset bằng phương thức như **offsetByCodePoints** trước khi substring. Nếu xử lý “ký tự người dùng nhìn thấy”, ngay cả code point cũng chưa chắc đủ: một grapheme có thể gồm nhiều code points kết hợp.

**[l,r) không có nghĩa nếu chưa xác định đơn vị index**: byte, UTF-16 unit, code point, grapheme, pixel, record hoặc timestamp.

## 21. Pagination: batch cuối và không overflow

Đọc n phần tử theo batch size k>0 có thể dùng:

**[start,end)**, với:

**end=min(n,start+k)**.

Để tránh overflow của start+k trên miền int lớn, có thể viết:

**end=start+min(k,n−start)**

khi 0≤start≤n và k>0.

~~~text
start = 0

while start < n:
    end = start + min(k, n-start)
    process [start,end)
    start = end
~~~

Bất biến: [0,start) đã xử lý một lần; [start,n) chưa xử lý. Vì k>0 nên start tiến nghiêm ngặt khi start<n.

Nếu n chia hết k, vòng cuối chấm dứt đúng start=n, không tạo batch rỗng [n,n). Nếu n không chia hết k, batch cuối ngắn hơn.

Khi đọc một stream không biết n, cần dựa trên **số byte/record thực sự được read thành công**; không xử lý đuôi buffer cũ như dữ liệu của lần đọc mới.

## 22. Chia n phần tử cho p worker

Khi chia việc cho p>0 worker, worker b nhận:

**start_b=floor(b·n/p)**.

**end_b=floor((b+1)·n/p)**.

Với b=0,...,p−1, các đoạn half-open này:

- Nối nhau liên tiếp.
- Không chồng lấn.
- Hợp bằng [0,n).
- Có thể rỗng nếu p>n.

Trong Java, tính tích bằng long trước:

~~~java
int start = (int) ((long) b * n / p);
int end = (int) ((long) (b + 1) * n / p);
~~~

Thay vì b*n/p thực hiện nhân int có thể overflow.

Không có write-write overlap giữa những ô thuộc hai đoạn disjoint **nếu** mỗi worker chỉ ghi vùng được giao. Điều này không tự đảm bảo thread-safety nếu còn có shared counters, caches hoặc object state chung không đồng bộ.

## 23. Reverse đoạn và giữ nguyên hai phía ngoài

Đảo [l,r) bằng hai con trỏ element indexes:

~~~text
i = l
j = r-1

while i < j:
    swap(a[i], a[j])
    i++
    j--
~~~

Ví dụ:

~~~text
Before: [3, -2, 5, 7, 0, -4]
Reverse [1,5)
After:  [3, 0, 7, 5, -2, -4]
~~~

a[0] và a[5] không thay đổi.

### Bất biến reverse

Sau mỗi bước, các vị trí đã xử lý ở hai đầu đoạn đã có giá trị chính xác như sau khi đảo toàn bộ; phần giữa chưa xử lý được rút ngắn.

Nếu l=r, j=r−1 nhỏ hơn i, vòng lặp không chạy; **không truy cập a[-1]** vì điều kiện i<j ngăn truy cập.

### Sort cũng là thao tác đoạn

Arrays.sort(a,l,r) sắp đúng [l,r). Nếu đề bài yêu cầu sắp **đoạn đóng [l,r]**, hãy validate rồi gọi Arrays.sort(a,l,r+1).

## 24. Kiểm tra hợp đồng ở ranh giới API

Bug thường xuất hiện khi hai tầng hệ thống dùng convention khác:

- UI nhận 1-based đóng.
- Business logic dùng 0-based half-open.
- Database API nhận offset và length.
- File API nhận byte offset và byte count.
- HTTP header hoặc log window có quy tắc timestamp riêng.

Nếu mỗi tầng tự cộng/trừ chỉ số, rất dễ **chuyển hai lần** hoặc **quên chuyển**.

### Cách thiết kế

- Đặt tên rõ **startInclusive**, **endExclusive** hoặc **offset**, **length**.
- Chuyển input về canonical [l,r) tại một điểm duy nhất.
- Dùng checkRange tại tầng nhận dữ liệu không đáng tin.
- Document rõ empty behavior và error policy.
- Không trộn inclusive/exclusive trong comment và code.

Nếu nhận offset,length:

**right=offset+length**,

hãy kiểm tra:

**0≤offset≤n** và **0≤length≤n−offset**,

sau đó mới tính right. Cách này tránh overflow do cộng trước validate.

### Window thời gian

[start,end) thường thích hợp cho log buckets: event đúng tại end thuộc bucket kế tiếp, tránh double-count giữa các khoảng liền kề. Nhưng timezone/DST và định nghĩa timestamp phải được xử lý riêng.

## 25. Aggregate trên đoạn rỗng không phải luôn là 0

Với các phép toán có **identity**, kết quả đoạn rỗng tự nhiên là identity:

- Sum: 0.
- Product: 1.
- XOR: 0.
- Count: 0.
- Nối chuỗi: chuỗi rỗng.

Nhưng một số aggregate không có giá trị thông thường trên đoạn rỗng:

- Min: có thể trả Optional.empty, +∞ sentinel hoặc ném lỗi.
- Average: mẫu số 0, cần hợp đồng riêng.
- Median/mode: có thể không xác định.
- Max: có thể dùng −∞ sentinel hoặc từ chối input rỗng.

**Khoảng rỗng hợp lệ về mặt chỉ số** không buộc mọi hàm aggregate phải **trả 0**. Nếu bài toán yêu cầu nonempty, ghi rõ tiền điều kiện **left<right** và kiểm tra.

## 26. Chương trình Java 17+ độc lập

Chương trình sử dụng thống nhất **[left,right)** trong các hàm nội bộ. Các phần minh họa:

- checkRange/checkIndex: phân biệt boundary với element index.
- prefix, sumRange, inclusiveSum, oneBasedInclusiveSum.
- slice, reverseRange và lowerBound/upperBound.
- rangeAddAll dùng difference array.
- countAtMostNonNegative với giả thiết mảng không âm.
- SegmentTree iterative hỗ trợ point set và range sum.
- prefix2D/rectangleSum cho rectangle half-open.
- main in ví dụ, kiểm tra đầu vào [4,3) bị từ chối.

**Tên tệp: HalfOpenBoundaryDemo.java**

~~~java
import java.util.Arrays;
import java.util.Objects;

public class HalfOpenBoundaryDemo {

    static void checkRange(int n, int left, int right) {
        if (left < 0 || right < left || right > n) {
            throw new IndexOutOfBoundsException(
                    "Expected 0 <= left <= right <= n");
        }
    }

    static void checkIndex(int n, int index) {
        if (index < 0 || index >= n) {
            throw new IndexOutOfBoundsException(index);
        }
    }

    static long[] prefix(int[] a) {
        Objects.requireNonNull(a, "a");
        long[] p = new long[a.length + 1];

        for (int i = 0; i < a.length; i++) {
            p[i + 1] = p[i] + a[i];
        }

        return p;
    }

    static long sumRange(
            long[] p, int left, int right) {
        Objects.requireNonNull(p, "p");
        checkRange(p.length - 1, left, right);
        return p[right] - p[left];
    }

    // Converts a 0-based inclusive [left,right] range.
    static long inclusiveSum(
            long[] p, int left, int right) {
        Objects.requireNonNull(p, "p");
        int n = p.length - 1;

        if (left < 0 || right < left || right >= n) {
            throw new IndexOutOfBoundsException(
                    "Invalid inclusive range");
        }

        return sumRange(p, left, right + 1);
    }

    // Converts a 1-based inclusive [L,R] range.
    static long oneBasedInclusiveSum(
            long[] p, int left1, int right1) {
        Objects.requireNonNull(p, "p");
        int n = p.length - 1;

        if (left1 < 1 || right1 < left1
                || right1 > n) {
            throw new IndexOutOfBoundsException(
                    "Invalid 1-based inclusive range");
        }

        return sumRange(p, left1 - 1, right1);
    }

    static int[] slice(
            int[] a, int left, int right) {
        Objects.requireNonNull(a, "a");
        checkRange(a.length, left, right);
        return Arrays.copyOfRange(a, left, right);
    }

    static void reverseRange(
            int[] a, int left, int right) {
        Objects.requireNonNull(a, "a");
        checkRange(a.length, left, right);

        int i = left;
        int j = right - 1;

        while (i < j) {
            int temp = a[i];
            a[i] = a[j];
            a[j] = temp;
            i++;
            j--;
        }
    }

    static int lowerBound(
            int[] sorted, int target) {
        Objects.requireNonNull(sorted, "sorted");
        int lo = 0;
        int hi = sorted.length;

        while (lo < hi) {
            int mid = lo + (hi - lo) / 2;

            if (sorted[mid] < target) {
                lo = mid + 1;
            } else {
                hi = mid;
            }
        }

        return lo;
    }

    static int upperBound(
            int[] sorted, int target) {
        Objects.requireNonNull(sorted, "sorted");
        int lo = 0;
        int hi = sorted.length;

        while (lo < hi) {
            int mid = lo + (hi - lo) / 2;

            if (sorted[mid] <= target) {
                lo = mid + 1;
            } else {
                hi = mid;
            }
        }

        return lo;
    }

    // Each update triple is [left,right,delta].
    static long[] rangeAddAll(
            int[] input, int[][] updates) {
        Objects.requireNonNull(input, "input");
        Objects.requireNonNull(updates, "updates");

        int n = input.length;
        long[] diff = new long[n + 1];

        for (int[] u : updates) {
            if (u == null || u.length != 3) {
                throw new IllegalArgumentException(
                        "Each update needs 3 integers");
            }

            int left = u[0];
            int right = u[1];
            long delta = u[2];

            checkRange(n, left, right);

            if (left == right || delta == 0) {
                continue;
            }

            diff[left] += delta;
            diff[right] -= delta;
        }

        long[] out = new long[n];
        long running = 0L;

        for (int i = 0; i < n; i++) {
            running += diff[i];
            out[i] = input[i] + running;
        }

        return out;
    }

    // Counts nonempty subarrays with sum <= limit.
    // All input values must be nonnegative.
    static long countAtMostNonNegative(
            int[] a, long limit) {
        Objects.requireNonNull(a, "a");

        for (int value : a) {
            if (value < 0) {
                throw new IllegalArgumentException(
                        "Two pointers require nonnegative values");
            }
        }

        if (limit < 0) {
            return 0L;
        }

        int left = 0;
        long sum = 0L;
        long count = 0L;

        for (int right = 0; right < a.length; right++) {
            sum += a[right];

            while (sum > limit) {
                sum -= a[left++];
            }

            count += right - left + 1L;
        }

        return count;
    }

    static final class SegmentTree {
        private final int n;
        private final long[] tree;

        SegmentTree(int[] a) {
            Objects.requireNonNull(a, "a");
            n = a.length;
            tree = new long[2 * n];

            for (int i = 0; i < n; i++) {
                tree[n + i] = a[i];
            }

            for (int i = n - 1; i > 0; i--) {
                tree[i] = tree[2 * i] + tree[2 * i + 1];
            }
        }

        void set(int index, int value) {
            checkIndex(n, index);

            int pos = n + index;
            tree[pos] = value;

            for (pos >>= 1; pos > 0; pos >>= 1) {
                tree[pos] =
                        tree[2 * pos] + tree[2 * pos + 1];
            }
        }

        long sumRange(int left, int right) {
            checkRange(n, left, right);

            int l = left + n;
            int r = right + n;
            long result = 0L;

            while (l < r) {
                if ((l & 1) != 0) {
                    result += tree[l++];
                }

                if ((r & 1) != 0) {
                    result += tree[--r];
                }

                l >>= 1;
                r >>= 1;
            }

            return result;
        }
    }

    static long[][] prefix2D(int[][] grid) {
        Objects.requireNonNull(grid, "grid");
        int rows = grid.length;
        int cols = rows == 0
                ? 0 : Objects.requireNonNull(
                        grid[0], "grid row").length;

        for (int[] r : grid) {
            if (r == null || r.length != cols) {
                throw new IllegalArgumentException(
                        "Grid must be rectangular");
            }
        }

        long[][] p = new long[rows + 1][cols + 1];

        for (int row = 0; row < rows; row++) {
            for (int col = 0; col < cols; col++) {
                p[row + 1][col + 1] =
                        grid[row][col]
                        + p[row][col + 1]
                        + p[row + 1][col]
                        - p[row][col];
            }
        }

        return p;
    }

    static long rectangleSum(
            long[][] p,
            int top, int bottom,
            int left, int right) {
        int rows = p.length - 1;
        int cols = p[0].length - 1;

        checkRange(rows, top, bottom);
        checkRange(cols, left, right);

        return p[bottom][right]
                - p[top][right]
                - p[bottom][left]
                + p[top][left];
    }

    public static void main(String[] args) {
        int[] a = {3, -2, 5, 7, 0, -4};
        long[] p = prefix(a);

        System.out.println("Array: "
                + Arrays.toString(a));
        System.out.println("Prefix: "
                + Arrays.toString(p));
        System.out.println("Sum [1,5): "
                + sumRange(p, 1, 5));
        System.out.println("Inclusive [2,4]: "
                + inclusiveSum(p, 2, 4));
        System.out.println("One-based [2,5]: "
                + oneBasedInclusiveSum(p, 2, 5));
        System.out.println("Empty [3,3): "
                + sumRange(p, 3, 3));
        System.out.println("Tail [6,6): "
                + sumRange(p, 6, 6));
        System.out.println("Full [0,6): "
                + sumRange(p, 0, 6));

        System.out.println("Slice [2,5): "
                + Arrays.toString(slice(a, 2, 5)));

        int[] reversed = a.clone();
        reverseRange(reversed, 1, 5);
        System.out.println("Reverse [1,5): "
                + Arrays.toString(reversed));

        int[] sorted = {-3, -1, 0, 0, 2, 2, 5};
        System.out.println("lowerBound(2): "
                + lowerBound(sorted, 2));
        System.out.println("upperBound(2): "
                + upperBound(sorted, 2));
        System.out.println("Equal range for 2: ["
                + lowerBound(sorted, 2) + ","
                + upperBound(sorted, 2) + ")");
        System.out.println("lowerBound(4): "
                + lowerBound(sorted, 4));
        System.out.println("upperBound(8): "
                + upperBound(sorted, 8));

        long[] after = rangeAddAll(
                a,
                new int[][] {
                        {1, 4, 3},
                        {3, 6, -2}
                });
        System.out.println("Range updates: "
                + Arrays.toString(after));

        System.out.println("At-most-3 subarrays: "
                + countAtMostNonNegative(
                        new int[] {1, 2, 1, 0}, 3));
        System.out.println("At-most-0 subarrays: "
                + countAtMostNonNegative(
                        new int[] {1, 2, 1, 0}, 0));

        SegmentTree tree = new SegmentTree(a);
        System.out.println("Tree sum [1,5): "
                + tree.sumRange(1, 5));
        tree.set(2, 10);
        System.out.println("Tree after set(2,10) [1,5): "
                + tree.sumRange(1, 5));
        System.out.println("Tree full after set: "
                + tree.sumRange(0, 6));

        int[][] grid = {
                {1, 2, 3},
                {4, 5, 6},
                {7, 8, 9}
        };
        long[][] rect = prefix2D(grid);

        System.out.println("2D [0,2)x[1,3): "
                + rectangleSum(rect, 0, 2, 1, 3));
        System.out.println("2D empty: "
                + rectangleSum(rect, 2, 2, 0, 3));

        System.out.println("Substring [1,4): "
                + "ABCDE".substring(1, 4));

        boolean rejected = false;
        try {
            checkRange(a.length, 4, 3);
        } catch (IndexOutOfBoundsException e) {
            rejected = true;
        }
        System.out.println("Invalid [4,3) rejected: "
                + rejected);
    }
}
~~~

Biên dịch và chạy với **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 HalfOpenBoundaryDemo.java
java HalfOpenBoundaryDemo
~~~

**Đầu ra chuẩn:**

~~~text
Array: [3, -2, 5, 7, 0, -4]
Prefix: [0, 3, 1, 6, 13, 13, 9]
Sum [1,5): 10
Inclusive [2,4]: 12
One-based [2,5]: 10
Empty [3,3): 0
Tail [6,6): 0
Full [0,6): 9
Slice [2,5): [5, 7, 0]
Reverse [1,5): [3, 0, 7, 5, -2, -4]
lowerBound(2): 4
upperBound(2): 6
Equal range for 2: [4,6)
lowerBound(4): 6
upperBound(8): 7
Range updates: [3, 1, 8, 8, -2, -6]
At-most-3 subarrays: 8
At-most-0 subarrays: 1
Tree sum [1,5): 10
Tree after set(2,10) [1,5): 15
Tree full after set: 14
2D [0,2)x[1,3): 16
2D empty: 0
Substring [1,4): BCD
Invalid [4,3) rejected: true
~~~

### Ý nghĩa của từng lớp hàm

**Prefix:** long[] P với n+1 phần tử, giữ snapshot độc lập sau khi xây.

**inclusiveSum và oneBasedInclusiveSum:** validate theo convention gốc rồi mới đổi sang [l,r).

**slice:** checkRange trước khi dùng Arrays.copyOfRange, tránh endpoint vượt độ dài bị padding.

**lowerBound/upperBound:** trả một boundary hợp lệ trong [0,n], không bao giờ đọc a[n].

**rangeAddAll:** gom các cập nhật đoạn vào diff, sau đó materialize kết quả cuối; không xử lý query xen kẽ.

**countAtMostNonNegative:** từ chối phần tử âm, bảo đảm tiền điều kiện monotonicity của two pointers.

**SegmentTree:** query range dùng biên phải exclusive, update điểm dùng checkIndex; n=0 cho query rỗng nhưng không cho set.

**prefix2D:** rectangular matrix với hàng/cột zero prefix, hình rỗng cho tổng 0.

Chương trình sử dụng **int** cho giá trị phần tử và **long** cho tổng, nhằm tránh overflow trong các ví dụ chứa nhiều số int lớn. Với input long hoặc rất nhiều updates long, vẫn cần kiểm tra cận và có thể dùng BigInteger.

## 27. Thiết kế oracle kiểm thử độc lập

Một oracle tổng đoạn trực tiếp:

~~~text
bruteSum(a,l,r):
    answer = 0
    for i = l .. r-1:
        answer += a[i]
    return answer
~~~

Không dùng lại chính công thức prefix trong oracle, vì hai implementation có cùng bug vẫn có thể khớp.

### Các phép đối chiếu

- Prefix: P[r]−P[l] đúng bằng bruteSum.
- Đóng [l,r]: đúng bằng bruteSum(a,l,r+1).
- 1-based [L,R]: đúng bằng bruteSum(a,L−1,R).
- Slice: đúng a.slice(l,r).
- Reverse: đoạn [l,r) đảo, ngoài đoạn giữ nguyên, đảo hai lần trả input.
- Lower bound: scan tuyến tính tìm index đầu có a[i]≥x.
- Upper bound: scan tuyến tính tìm index đầu có a[i]>x.
- Range add: áp dụng trực tiếp từng update lên bản sao.
- Sliding window: liệt kê mọi cặp 0≤l<r≤n và đếm đoạn có tổng≤K.
- Segment tree: duy trì một mảng naive, so sau từng set/query.
- Prefix 2D: hai vòng lặp row/column tính rectangle sum.

### Không nhầm correctness với performance

Binary search và segment tree đúng cần có cả:

1. **Đáp án đúng** với oracle.
2. **Miền tìm kiếm/cửa sổ giảm** và bất biến hợp lệ.
3. **Chi phí đúng** O(log n) cho các vòng cần chứng minh.

Random tests hỗ trợ tìm bug nhưng không thay chứng minh bất biến cho mọi input.

## 28. Property-based testing: những đẳng thức phải giữ

**Độ dài:**

**length([l,r))=r−l**.

**Tách đoạn:**

Với l≤m≤r:

**sum([l,r))=sum([l,m))+sum([m,r))**.

**Đoạn rỗng:**

**sum([i,i))=0**, 0≤i≤n.

**Một phần tử:**

**sum([i,i+1))=a[i]**, 0≤i<n.

**Reverse involution:**

**reverse(reverse(a,[l,r)),[l,r))=a**.

**Phần tử ngoài đoạn không đổi** sau reverse/sort range.

**Binary search bounds:**

**0≤lowerBound(x)≤upperBound(x)≤n**.

**Difference array:**

Sau batch updates, vật hóa mảng phải bằng áp dụng trực tiếp từng update.

**Rectangle decomposition:**

Với top≤mid≤bottom, tổng rectangle bằng tổng hai rectangle chia tại mid.

**Tính từ chối input sai:**

Hàm checkRange phải từ chối l<0, r>n hoặc l>r, thay vì trả một giá trị được làm tròn.

### Các ca rỗng và một phần tử

n=0 và n=1 là những trường hợp có giá trị kiểm thử cao vì chúng làm lộ việc một implementation ngầm cho rằng luôn có phần tử thứ nhất hoặc cuối.

## 29. Bộ ca biên nên dùng khi review code

1. n=0: chỉ [0,0) hợp lệ.
2. n=1: [0,0), [0,1), [1,1).
3. [0,n): toàn bộ.
4. [n,n): đoạn rỗng cuối.
5. [i,i): đoạn rỗng giữa.
6. [i,i+1): một phần tử.
7. l>r: từ chối.
8. l<0 hoặc r>n: từ chối.
9. 0-based đóng với r=n−1: chuyển tới right=n.
10. 1-based đóng với L=1,R=n: chuyển tới [0,n).
11. Dãy toàn âm: prefix vẫn đúng; two pointers nonnegative từ chối.
12. Dãy toàn số 0: sliding window phải đếm các đoạn khác nhau.
13. Giá trị Integer.MIN_VALUE và Integer.MAX_VALUE: long sum.
14. Sorted array rỗng: lower=upper=0.
15. Sorted array toàn duplicates: lower=0,upper=n với target tương ứng.
16. Target nhỏ hơn mọi phần tử: lower=0.
17. Target lớn hơn mọi phần tử: lower=upper=n.
18. Reverse đoạn rỗng và singleton: không thay input.
19. Reverse toàn mảng: hoán đổi đúng.
20. Range add [n,n): không đổi.
21. Range add [0,n): cập nhật toàn bộ.
22. Segment tree n=0: query 0, set từ chối.
23. Prefix2D có 0 hàng hoặc 0 cột: rectangle rỗng.
24. Ma trận ragged: từ chối nếu hợp đồng rectangular.
25. String chứa surrogate pairs: không cắt khi yêu cầu code points.
26. Pagination n chia hết k: không thêm batch thừa.
27. Pagination n không chia hết k: batch cuối ngắn hơn.
28. Chia p worker với p>n: đoạn rỗng vẫn hợp lệ.
29. Snapshot không bị ảnh hưởng do caller sửa input.
30. Kiểm thử nhiều random ranges và đối chiếu oracle không dùng lại cùng code.

## 30. Lỗi thường gặp và hướng sửa

1. **Dùng i≤right cho [left,right):** đọc thừa phần tử right.
2. **Dùng i<right cho đoạn đóng [left,right]:** bỏ phần tử cuối.
3. **Nhầm length với lastIndex:** n phần tử thì lastIndex=n−1.
4. **Coi boundary n là index phần tử:** a[n] gây lỗi.
5. **Từ chối [n,n) dù hợp lệ:** checkRange phải cho right=n.
6. **Dùng P[r]−P[l] cho đoạn đóng:** thiếu a[r].
7. **Chuyển 1-based [L,R] thành [L,R+1):** sai hai biên.
8. **Cộng r+1 trước validate:** có thể tràn số.
9. **Tự clamp dữ liệu sai mà không có hợp đồng:** che bug.
10. **Lấy i=1 làm phần tử đầu của array Java:** lệch 1-based.
11. **Chia [l,m] và [m,r] theo convention half-open:** chồng lấn.
12. **Nhánh đệ quy không nhỏ hơn đoạn cha:** nguy cơ vô hạn.
13. **Lower bound dùng lo=mid khi mid sai:** không tiến.
14. **Lower bound dùng hi=mid−1:** có thể loại đáp án.
15. **Tính midpoint bằng (lo+hi)/2 với int lớn:** overflow.
16. **Coi insertion point n là phần tử a[n].**
17. **Coi Arrays.binarySearch trả lần xuất hiện đầu tiên của duplicates.**
18. **Mở R mà không add a[R] cũ.**
19. **Thu R bằng remove(R--) thay vì remove(--R).**
20. **Thu L trước khi mở R trên hai đoạn xa nhau:** remove nonresident.
21. **Dùng sliding window nonnegative trên dữ liệu âm:** sai monotonicity.
22. **Tự thêm một đoạn khi phần tử lớn hơn K:** thực ra có thể 0.
23. **Bỏ qua các đoạn có zero vì cùng tổng:** sai số lượng subarrays.
24. **Difference array chỉ có n ô mà ghi D[n]:** vượt chỉ số.
25. **Difference array cộng tại D[r] thay vì trừ.**
26. **Không xử lý l=r trong update để tránh phép tính thừa.**
27. **Segment tree đọc tree[R] khi R exclusive.**
28. **Point update cho index=n:** không hợp lệ.
29. **Sort đoạn bằng Arrays.sort(a,l,r) rồi mong bao gồm r.**
30. **Arrays.copyOfRange to>length tự padding mà bị coi như validation.**
31. **Nhầm subList là bản sao độc lập.**
32. **Substring cắt surrogate pair.**
33. **Coi code-point index như UTF-16 code-unit index.**
34. **Prefix2D trộn row/column hoặc thiếu góc +P[top][left].**
35. **Không xác định rectangle empty behavior.**
36. **Pagination với batch size 0:** vòng lặp không tiến.
37. **Tính start+k hoặc b*n/p bằng int không xét overflow.**
38. **Nhiều worker cùng xử lý end của đoạn trước:** double work/race.
39. **Áp một helper checkRange cho element index:** lỡ cho index=n.
40. **Trả 0 cho min/average của đoạn rỗng không có hợp đồng.**
41. **Giả định long sum đủ cho mọi đầu vào long.**
42. **Chỉ test input ngẫu nhiên không thử các biên n=0,n=1.**
43. **So hai implementation giống hệt nhau:** dễ cùng mắc bug.
44. **Không chứng minh vòng lặp giảm miền ứng viên:** nguy cơ infinite loop.
45. **Comment endpoint inclusive nhưng code thực hiện exclusive.**
46. **Thay đổi cấu trúc List gốc khi còn dùng subList view:** hành vi không đúng mong đợi.
47. **Dùng khoảng thời gian [start,end] cho hai bucket kề nhau:** có thể đếm trùng event tại ranh giới.
48. **Nhầm unit index byte, code unit và code point:** làm sai cắt chuỗi.

## 31. Bài tập tự luyện có đáp án

**Câu 1.** Mảng n=7 có bao nhiêu element indexes và boundaries hợp lệ?  
**Đáp án:** 7 element indexes 0..6, 8 boundaries 0..7.

**Câu 2.** Length của [2,6)?  
**Đáp án:** 4.

**Câu 3.** [n,n) hợp lệ không?  
**Đáp án:** Có, đoạn rỗng cuối.

**Câu 4.** a[n] hợp lệ không?  
**Đáp án:** Không.

**Câu 5.** 0-based đóng [2,5] chuyển sang half-open?  
**Đáp án:** [2,6).

**Câu 6.** 1-based đóng [2,5] chuyển sang 0-based half-open?  
**Đáp án:** [1,5).

**Câu 7.** Với a=[3,−2,5,7,0,−4], sum[1,5)?  
**Đáp án:** 10.

**Câu 8.** Sum của 0-based đóng [2,4]?  
**Đáp án:** 12.

**Câu 9.** Prefix của a mẫu?  
**Đáp án:** [0,3,1,6,13,13,9].

**Câu 10.** P[6] hợp lệ dù a[6] không hợp lệ vì sao?  
**Đáp án:** P dài n+1, a dài n.

**Câu 11.** Range add +3 trên [1,4) sửa diff ở đâu?  
**Đáp án:** D[1]+=3 và D[4]−=3.

**Câu 12.** Thu R trong cửa sổ nửa mở phải remove phần tử nào?  
**Đáp án:** R−1, dùng remove(--R).

**Câu 13.** lowerBound(2) trên [-3,−1,0,0,2,2,5]?  
**Đáp án:** 4.

**Câu 14.** upperBound(2) trên mảng ấy?  
**Đáp án:** 6.

**Câu 15.** Có bao nhiêu phần tử bằng 2?  
**Đáp án:** 2.

**Câu 16.** Nếu không có phần tử nào ≥target, lowerBound trả?  
**Đáp án:** n.

**Câu 17.** Vì sao lowerBound phải có lo=mid+1 khi a[mid]<target?  
**Đáp án:** mid chắc chắn không thể là đáp án, và miền phải thu nhỏ.

**Câu 18.** Reverse [1,5) của a mẫu ra gì?  
**Đáp án:** [3,0,7,5,−2,−4].

**Câu 19.** Giao [1,3) và [3,6)?  
**Đáp án:** Rỗng.

**Câu 20.** Chia [0,8) tại m=4?  
**Đáp án:** [0,4) và [4,8).

**Câu 21.** [1,2,1,0] có bao nhiêu đoạn con không rỗng tổng≤3?  
**Đáp án:** 8.

**Câu 22.** Có số âm thì two pointers nonnegative vẫn đúng không?  
**Đáp án:** Không có bảo đảm, phải dùng thuật toán phù hợp khác.

**Câu 23.** Rectangle [0,2)×[1,3) của grid 1..9 theo hàng?  
**Đáp án:** 16.

**Câu 24.** Arrays.sort(a,from,to) có lấy phần tử to không?  
**Đáp án:** Không.

**Câu 25.** String.substring có thể cắt emoji giữa surrogate pair?  
**Đáp án:** Có nếu index cắt giữa hai UTF-16 code units.

**Câu 26.** Công thức chia cho p worker?  
**Đáp án:** Worker b nhận [floor(bn/p),floor((b+1)n/p)).

**Câu 27.** Pagination đã đến start=n có nên xử lý [n,n) thêm không?  
**Đáp án:** Không, vòng while start<n phải kết thúc.

**Câu 28.** Min đoạn rỗng tự động bằng 0 đúng không?  
**Đáp án:** Không; cần identity/sentinel/exception theo hợp đồng.

**Câu 29.** Những ca quan trọng nhất khi unit test range?  
**Đáp án:** n=0, [0,n), [n,n), [i,i+1), invalid bounds.

**Câu 30.** Oracle cho lower/upper bound nên làm gì?  
**Đáp án:** Quét tuyến tính tìm vị trí đầu thỏa điều kiện.

## 32. Checklist trước khi hoàn thành

1. **Đơn vị index là gì?** Phần tử, byte, code unit, code point, pixel hay timestamp?
2. **Input là 0-based hay 1-based?**
3. **Input là đoạn đóng hay nửa mở?**
4. **Đã chuẩn hóa về [l,r) tại boundary API chưa?**
5. **Đã phân biệt 0..n−1 với 0..n chưa?**
6. **n=0 có được xử lý hợp lệ không?**
7. **[l,l) và [n,n) có hợp đồng rõ không?**
8. **Một phần tử [i,i+1) có được duyệt đúng một lần không?**
9. **Loop dùng i<right và có chứng minh dừng không?**
10. **Khi dịch cửa sổ, add/remove có đúng chỉ số không?**
11. **Chuyển đoạn đóng có validate trước phép r+1 không?**
12. **Binary search có bất biến và thu nhỏ miền ở mọi vòng không?**
13. **Midpoint có tránh overflow int trung gian không?**
14. **Có chấp nhận insertion point n của lower/upper bound không?**
15. **Prefix và diff arrays có slot cho boundary n không?**
16. **Segment tree dùng --right trước khi đọc right-exclusive không?**
17. **Chia để trị có hai đoạn con không overlap và nhỏ hơn cha không?**
18. **Rectangle dùng half-open ở cả hai chiều không?**
19. **Các Java API được đọc đúng hợp đồng endpoint không?**
20. **String dùng UTF-16 hay code points/graphemes?**
21. **Các worker/chunks có vùng ghi không overlap không?**
22. **Pagination có k>0 và tiến về n không?**
23. **Kiểu tổng có tránh overflow với input dự kiến không?**
24. **Aggregate rỗng như min/average có hợp đồng không?**
25. **Đã so các thuật toán với oracle trực tiếp chưa?**
26. **Đã thử empty/full/singleton/invalid ranges chưa?**
27. **Các bản copy/snapshot có giữ input nguyên vẹn không?**
28. **Tên tham số và comments có ghi rõ endpoint exclusive không?**

## 33. Kết luận

**Khoảng nửa mở [l,r)** là một **hợp đồng nhất quán về số phần tử, vị trí biên, điều kiện dừng và cách chia việc**, không chỉ là một kiểu ký hiệu. Nó cho công thức length=r−l, phép truy vấn P[r]−P[l], phép chia [l,m)+[m,r), vị trí chèn n trong binary search và bốn thao tác add(--L),add(R++),remove(L++),remove(--R) với ý nghĩa rõ ràng.

Điểm then chốt để giảm lỗi off-by-one không phải chỉ chọn [l,r), mà là **giữ đúng convention từ đầu vào đến tất cả các hàm nội bộ, validate trước khi chuyển chỉ số, chứng minh bất biến và tiến độ vòng lặp, rồi kiểm thử các biên rỗng/full/singleton bằng oracle độc lập**. Khi các quy tắc này thành thói quen, việc cài đặt và review thuật toán Java trở nên đáng tin cậy hơn đáng kể.
