# Kết hợp tìm kiếm nhị phân trên đáp án với phép kiểm tra khả thi

**Tìm kiếm nhị phân trên đáp án (binary search on answer)** là mẫu giải bài toán tối ưu hóa khi khó tính trực tiếp giá trị tốt nhất nhưng có thể kiểm tra một **giá trị ứng viên x** bằng câu hỏi Có/Không: **“Có tồn tại một phương án thỏa yêu cầu tại ngưỡng x không?”**

Sau khi biến bài tối ưu thành bài toán quyết định **F(x)**, ta dùng tính **đơn điệu** để loại bỏ nửa miền ứng viên trong mỗi lần kiểm tra. Độ khó lớn nhất thường không nằm ở vòng while, mà ở việc **chứng minh checker đúng và đầy đủ**, chọn các cận bao trùm đáp án và tính toán không tràn số.

Bài thuộc chủ đề **Thực hành tổng hợp** với các bài toán minh họa:

1. **Tìm sức chứa nhỏ nhất** để vận chuyển các kiện theo thứ tự trong D ngày.
2. **Tìm tốc độ nhỏ nhất** để hoàn thành các đống công việc trong H giờ.
3. **Tìm khoảng cách nhỏ nhất lớn nhất** khi chọn k điểm trên trục số.
4. **Chia mảng thành đúng k đoạn liên tiếp** để tổng đoạn lớn nhất nhỏ nhất.
5. **Tìm căn bậc hai nguyên** bằng kiểm tra điều kiện r²≤N không overflow.

Tất cả bài có ví dụ, phân tích độ phức tạp, giới hạn hợp đồng và code **Java 17+ chạy độc lập**. Các ví dụ Java dùng **int[]** cho dữ liệu đầu vào và **long** cho những tổng, khoảng cách, tốc độ hoặc dung lượng có thể vượt miền int.

## 1. Từ tối ưu hóa sang bài toán quyết định

Giả sử cần **minimize x** mà x là một ngưỡng tài nguyên. Ta định nghĩa:

**F(x)=true** nếu có một phương án hợp lệ sử dụng không quá ngưỡng x.

Nếu có cách làm ở x, nhiều bài toán cũng có cách làm ở mọi x'≥x. Khi đó:

~~~text
x tăng:    0  1  2  3  4  5  6  7  8
F(x):      F  F  F  F  T  T  T  T  T
                        ^
                     first true
~~~

**Đáp án tối ưu = vị trí true đầu tiên**.

Đối với bài **maximize x**, x thường là mức chất lượng tối thiểu cần đạt. Đòi mức cao hơn khó hơn:

~~~text
x tăng:    0  1  2  3  4  5  6  7  8
G(x):      T  T  T  T  T  F  F  F  F
                        ^
                     last true
~~~

**Đáp án tối ưu = vị trí true cuối cùng**.

Không nên nhầm tính đơn điệu của **predicate khả thi** với độ tăng/giảm của một hàm mục tiêu tùy ý. Thứ cần nhị phân hóa là **ranh giới chuyển trạng thái true/false**.

## 2. Ba điều kiện tiên quyết

Để binary search on answer đúng, phải có:

**(1) Miền đáp án có thứ tự và cận hữu hạn.** Ví dụ capacity là số nguyên không âm trong [maxItem,sumAll].

**(2) Predicate đơn điệu.** Với first true, x tăng không thể biến true thành false. Với last true, x tăng không thể biến false thành true.

**(3) Checker vừa sound vừa complete.**

- **Sound:** trả true ⇒ có một phương án thực sự hợp lệ.
- **Complete:** có phương án hợp lệ ⇒ checker trả true.

Một checker tham lam thất bại **không chứng minh không có phương án khác**, trừ khi đã chứng minh greedy là đầy đủ.

### Vì sao phải chứng minh đủ cả hai chiều?

Nếu checker thỉnh thoảng trả false dù có một phương án khác khả thi, binary search sẽ loại bỏ cả một khoảng chứa đáp án thật. Nếu checker trả true cho một phương án vi phạm điều kiện, thuật toán có thể trả ngưỡng quá nhỏ hoặc quá lớn.

Do đó phải **chứng minh thuật toán kiểm tra**, không chỉ chứng minh vòng binary search.

## 3. Hai dạng predicate đơn điệu

| Bài | F(x) có nghĩa gì? | x tăng | Mẫu tìm kiếm |
| --- | --- | --- | --- |
| Giao hàng | Giao hết trong ≤D ngày với capacity x | Dễ hơn | First true |
| Tốc độ xử lý | Xong trong ≤H giờ ở tốc độ x | Dễ hơn | First true |
| Chia mảng | Có ≤k đoạn với mỗi sum≤x | Dễ hơn | First true |
| Chọn k điểm | Mọi khoảng cách liên tiếp giữa điểm chọn ≥x | Khó hơn | Last true |
| Căn nguyên | x²≤N | Khó hơn | Last true |

Một cách tự kiểm tra trước khi code: viết câu **“Nếu F(x) đúng, điều gì chắc chắn đúng với F(x+1)?”**

- Nếu đúng kéo theo F(x+1) đúng ⇒ first true.
- Nếu F(x+1) đúng kéo theo F(x) đúng ⇒ last true.
- Nếu không chứng minh được chiều nào ⇒ cần mô hình/checker khác.

## 4. Mẫu first true — giá trị nhỏ nhất khả thi

Giả sử x thuộc **[lo,hi]** gồm các số nguyên và **F(hi)=true**. Predicate có dạng false→true.

~~~text
while lo < hi:
    mid = lo + floor((hi-lo)/2)

    if feasible(mid):
        hi = mid
    else:
        lo = mid + 1

return lo
~~~

### Bất biến

**Đáp án tối ưu x* luôn thuộc [lo,hi].**

Nếu F(mid)=true, mid có thể là true đầu tiên; giữ mid bằng hi=mid.

Nếu F(mid)=false, mọi x≤mid cũng false; bỏ tất cả bằng lo=mid+1.

### Vì sao kết thúc?

Khi lo<hi, midpoint lệch trái thỏa **lo≤mid<hi**. Nhánh hi=mid giảm hi; nhánh lo=mid+1 tăng lo. Chiều dài khoảng thu nhỏ nghiêm ngặt.

Số vòng **O(log(hi₀−lo₀+1))**.

### Chú ý đặc biệt

- **F(lo) có thể true**; khi ấy đáp án là lo, hoàn toàn hợp lệ.
- **hi phải chắc chắn khả thi**. Nếu hi chỉ là giá trị đoán, thuật toán có thể trả sai.
- Không dùng lo=mid ở nhánh false; nếu hi=lo+1 thì mid=lo và vòng có thể vô hạn.
- Không dùng hi=mid−1 khi mid khả thi, vì điều đó có thể loại mất đáp án mid.

## 5. Mẫu last true — giá trị lớn nhất khả thi

Giả sử F có dạng true→false trên **[lo,hi]** và **F(lo)=true**.

~~~text
while lo < hi:
    mid = lo + ceil((hi-lo)/2)

    if feasible(mid):
        lo = mid
    else:
        hi = mid - 1

return lo
~~~

Với lo,hi kiểu long trong một miền mà hi−lo+1 không tràn:

~~~java
long mid = lo + (hi - lo + 1L) / 2L;
~~~

### Vì sao cần midpoint lệch phải?

Khi hi=lo+1, midpoint lệch trái bằng lo. Nếu F(lo)=true và gán lo=mid, không có tiến triển.

Midpoint lệch phải đảm bảo **mid>lo** khi lo<hi.

### Bất biến

**x*∈[lo,hi]**.

- F(mid)=true ⇒ có thể giữ mid và bỏ mọi ứng viên nhỏ hơn.
- F(mid)=false ⇒ mọi x≥mid không khả thi, nên bỏ cả mid bằng hi=mid−1.

**F(lo)=true** là điều kiện cho correctness; F(hi) có thể true hoặc false.

## 6. Chọn miền tìm kiếm: công việc quan trọng nhất trước vòng lặp

Cần lập luận được hai cận.

**First true:**

- lo phải không lớn hơn x*.
- hi phải không nhỏ hơn x*, và **hi khả thi**.

**Last true:**

- lo phải không lớn hơn x*, và **lo khả thi**.
- hi phải không nhỏ hơn x*.

Không nên chọn hi=1e9 theo thói quen. Những bài có tổng nhiều int có thể có đáp án lớn hơn 1e9 và thậm chí lớn hơn Integer.MAX_VALUE.

### Trường hợp không có nghiệm

Nếu bài không cho được một cận khả thi, có thể:

1. Dùng **exponential search** để nhân đôi cận cho tới khi đạt vùng true, nhưng phải tránh overflow và có cách phát hiện không thể đạt.
2. Kiểm tra điều kiện tồn tại nghiệm trước.
3. Trả kiểu Optional/giá trị sentinel được định nghĩa, hoặc ném lỗi hợp đồng.

Không được mặc định binary search “sẽ tự tìm ra” khi toàn miền false.

## 7. Bài 1 — Giao hàng theo thứ tự trong D ngày

Có mảng **weights[0..n−1]** gồm các trọng lượng **không âm**, bắt buộc giao theo đúng thứ tự. Mỗi ngày chở một đoạn liên tiếp của phần hàng còn lại và tổng trọng lượng không vượt **capacity C**.

Mục tiêu: tìm **C nhỏ nhất** để giao tất cả trong **không quá D ngày**, D≥1.

Ví dụ:

~~~text
weights = [1,2,3,4,5,6,7,8,9,10]
days = 5
answer = 15
~~~

Không được sắp xếp lại weights, bởi điều đó thay đổi ý nghĩa của bài vận chuyển theo thứ tự.

### Câu hỏi quyết định

Với một C cho trước:

**Có thể chia mảng thành ≤D nhóm liên tiếp, mỗi nhóm có tổng≤C không?**

Một checker O(n) là đủ để thử nhiều giá trị C bằng binary search.

## 8. Checker greedy: giao được với C không?

Giả sử C≥0:

~~~text
canShip(C):
    usedDays = 1
    load = 0

    for each weight:
        if weight > C:
            return false

        if load + weight > C:
            usedDays++
            load = weight
        else:
            load += weight

        if usedDays > D:
            return false

    return true
~~~

**Greedy nhét tiền tố dài nhất có thể vào ngày hiện tại**. Khi item kế không vừa, mới bắt đầu ngày sau.

### Chứng minh soundness

Nếu checker trả true, ta vừa xây dựng một lịch chia thành không quá D nhóm liên tiếp với mỗi tổng ≤C, nên lịch thật sự hợp lệ.

### Chứng minh completeness

So với bất kỳ lịch giao hàng hợp lệ với capacity C:

- Trong ngày đầu, greedy chở nhiều item đầu tiên nhất có thể. Lịch khác không thể chở hơn greedy vì item tiếp theo sẽ vượt C.
- Giả sử sau t ngày greedy đã giao ít nhất số item của lịch bất kỳ, thì ngày t+1, greedy tiếp tục lấy được tiền tố dài nhất của phần chưa giao.
- Suy ra bằng quy nạp, greedy dùng không nhiều ngày hơn lịch khác.

Nếu greedy vẫn cần >D ngày thì **không tồn tại lịch hợp lệ**. Với trọng lượng không âm và thứ tự cố định, checker là đầy đủ.

## 9. Đơn điệu, cận và trace của bài giao hàng

Nếu giao được với C, tăng capacity không làm lịch cũ mất hợp lệ. Vậy F(C) dạng false→true.

Cận dưới:

**lo=max(weights)**, vì một item không được chia.

Cận trên:

**hi=sum(weights)**, vì có thể giao tất cả trong một ngày.

Nếu mảng rỗng hoặc toàn số 0, code demo quy ước capacity=0 và D≥1.

Với weights=[1..10], D=5:

| Bước | lo | hi | mid | canShip(mid) | Khoảng tiếp |
| ---: | ---: | ---: | ---: | :---: | --- |
| 1 | 10 | 55 | 32 | true | [10,32] |
| 2 | 10 | 32 | 21 | true | [10,21] |
| 3 | 10 | 21 | 15 | true | [10,15] |
| 4 | 10 | 15 | 12 | false | [13,15] |
| 5 | 13 | 15 | 14 | false | [15,15] |

**Đáp án 15**.

Chứng nhận hai phía:

**canShip(14)=false**, **canShip(15)=true**.

Từ monotonicity và correctness của checker, 15 là capacity nhỏ nhất.

## 10. Ca biên và số lớn trong bài giao hàng

**D=1:** phải giao toàn bộ trong một ngày, capacity=sum(weights).

**D≥n>0:** mỗi item có thể dùng riêng một ngày, capacity=max(weights).

**Item bằng 0:** không làm tăng load.

**Mảng toàn 0:** capacity=0 đủ.

**Mảng rỗng:** trong API minh họa, capacity=0; một hệ thống khác có thể quy định input n=0 không hợp lệ, nhưng phải ghi rõ.

**Item âm:** không hợp đồng trọng lượng thông thường; code từ chối.

**D≤0:** không hợp lệ.

**Tổng vượt int:** ví dụ hai item Integer.MAX_VALUE phải giao cùng ngày:

**capacity=2147483647+2147483647=4294967294**.

Dùng long cho tổng, load và kết quả; **cast sau khi cộng int đã overflow là quá muộn**.

### Không nhầm đúng D với không quá D

Code dùng **≤D**. Nếu bài yêu cầu đúng D ngày có hàng, cần n≥D và lập luận có thể tách nhóm; không mặc định mọi input đều đáp ứng.

## 11. Bài 2 — Tốc độ nhỏ nhất để hoàn thành H giờ

Cho n đống công việc, mỗi đống **piles[i]>0**. Với tốc độ nguyên r>0, thời gian xử lý đống i là:

**ceil(piles[i]/r)** giờ.

Theo mô hình này, một giờ chỉ xử lý một đống; phần thời gian dư trong giờ không được dùng để làm đống tiếp theo.

Tìm r nhỏ nhất để tổng giờ xử lý **≤H**.

Ví dụ:

~~~text
piles = [3,6,7,11]
H = 8

r=3 -> 1+2+3+4=10 giờ -> false
r=4 -> 1+2+2+3=8 giờ  -> true

answer = 4
~~~

### Vì sao H≥n là tiền điều kiện?

Mỗi đống dương cần ít nhất một giờ, bất kể r lớn. Nếu H<n thì **không có tốc độ hữu hạn khả thi**. Code từ chối input này trước binary search.

## 12. Checker cho tốc độ: tổng ceil division

Định nghĩa:

**neededHours(r) = Σ ceil(pile/r)**.

**F(r)=(neededHours(r)≤H)**.

Khi r tăng, mỗi ceil(pile/r) không tăng, nên F dạng false→true.

Biên:

**lo=1**.

**hi=max(piles)**.

Nếu r=max(piles), mỗi đống mất đúng một giờ, tổng n≤H, vì vậy upper bound chắc chắn khả thi.

### Tránh overflow

Công thức phổ biến:

**ceil(a/b) = (a+b−1)/b**

có nguy cơ tràn nếu a+b−1 được tính trong int.

Với **a>0,b>0**, dùng:

**ceil(a/b) = (a−1)/b+1**.

Trong Java:

~~~java
long hoursForPile = (pile - 1L) / rate + 1L;
~~~

Trong checker có thể **trả false sớm** ngay khi neededHours>H, vì các đống còn lại chỉ có thể tăng tổng số giờ.

### Khi tốc độ tối thiểu bằng 1?

Nếu H đủ lớn để xử lý tất cả các đống ở tốc độ 1, first true phải trả ngay 1. Không cần yêu cầu F(lo) ban đầu false.

## 13. Bài 3 — Tối đa hóa khoảng cách tối thiểu

Cho n vị trí nguyên trên một trục, chọn **k bản ghi vị trí** sao cho khoảng cách nhỏ nhất giữa những điểm được chọn là lớn nhất.

Đây là mô hình **aggressive cows / maximize minimum distance**.

Giả thiết:

**2≤k≤n**.

Nếu k=1, không có cặp điểm để định nghĩa khoảng cách nhỏ nhất; code từ chối thay vì tùy ý đặt 0 hoặc vô hạn.

Ví dụ:

~~~text
positions = [1,2,8,4,9]
sorted    = [1,2,4,8,9]
k = 3

Chọn [1,4,8]:
gap 3,4 -> minimum gap 3

answer = 3
~~~

Khác với bài capacity, ở đây ngưỡng d càng lớn càng khó đạt.

## 14. Checker greedy: đặt đủ k điểm cách ít nhất d

Sau khi sort positions tăng dần:

1. Chọn vị trí đầu tiên (nhỏ nhất).
2. Đi từ trái sang phải.
3. Chọn vị trí sớm nhất có khoảng cách từ điểm vừa chọn **≥d**.
4. Nếu chọn được ít nhất k điểm thì true.

~~~text
canPlace(d):
    count = 1
    last = first position

    for position in remaining positions:
        if position-last >= d:
            count++
            last = position
            if count >= k:
                return true

    return count >= k
~~~

### Chứng minh bằng trao đổi

Xét bất kỳ cách đặt k điểm khả thi x₁≤...≤xₖ với gap≥d.

Greedy chọn g₁≤x₁. Giả sử g_j≤x_j. Điểm x_{j+1} cách g_j ít nhất d, vì x_{j+1}−g_j ≥ x_{j+1}−x_j ≥d. Greedy chọn vị trí hợp lệ **sớm nhất**, nên g_{j+1}≤x_{j+1}.

Theo quy nạp, nếu có phương án chọn k điểm, greedy cũng chọn được k điểm. Checker không chỉ đúng khi true, mà còn đầy đủ khi false.

### Hướng đơn điệu

Nếu đặt được k điểm với gap≥d, chính phương án ấy cũng đáp ứng mọi d'≤d. Do đó F(d) dạng:

**true,true,...,false**.

Cần **last true**.

## 15. Biên và trace bài khoảng cách

Cận dưới:

**lo=0**, chắc khả thi vì có n≥k bản ghi vị trí.

Cận trên:

**hi=max(position)−min(position)**.

Khoảng cách nhỏ nhất của k điểm không thể vượt toàn bộ span tọa độ.

Với positions=[1,2,4,8,9], k=3:

| Bước | lo | hi | mid lệch phải | canPlace(mid) | Khoảng sau |
| ---: | ---: | ---: | ---: | :---: | --- |
| 1 | 0 | 8 | 4 | false | [0,3] |
| 2 | 0 | 3 | 2 | true | [2,3] |
| 3 | 2 | 3 | 3 | true | [3,3] |

**Đáp án 3**.

Chứng nhận:

**canPlace(3)=true**, **canPlace(4)=false**.

### Duplicates không phải lỗi tự động

Input:

~~~text
positions = [1,1,1]
k=3
answer=0
~~~

Nếu các bản ghi là ba vị trí được phép chọn dù cùng tọa độ, d=0 khả thi. Không nên tự loại duplicates, vì như vậy số lượng ứng viên thay đổi.

Nếu bài thực tế yêu cầu tọa độ phải phân biệt, hãy thêm validation theo đúng hợp đồng đó.

### Khoảng cách vượt int

Nếu có hai vị trí **Integer.MIN_VALUE** và **Integer.MAX_VALUE**:

**span=4294967295**.

Cần:

~~~java
long span = (long) sorted[n - 1] - sorted[0];
~~~

Cast **trước** phép trừ.

## 16. Bài 4 — Chia thành đúng k đoạn liên tiếp

Cho mảng số **không âm** a độ dài n≥1 và k thỏa 1≤k≤n.

Chia mảng thành **đúng k đoạn liên tiếp không rỗng**, phủ hết a, nhằm:

**Minimize giá trị lớn nhất trong các tổng đoạn**.

Ví dụ:

~~~text
a=[7,2,5,10,8]
k=2

[7,2,5] | [10,8]
sum=14   | sum=18

largest sum=18
answer=18
~~~

### Biến thành feasibility

Với threshold T, hỏi:

**Có thể chia a thành ≤k nhóm liên tiếp, mỗi nhóm có tổng ≤T không?**

Dùng **≤k** trong checker vì greedy tìm **số nhóm ít nhất**. Khi tất cả a[i]≥0 và 1≤k≤n, nếu có ≤k nhóm hợp lệ thì có thể **chia thêm** các nhóm có từ hai phần tử thành đúng k nhóm không rỗng mà không làm tổng nhóm nào tăng. Vì vậy predicate ≤k tương đương tồn tại phân hoạch đúng k trong mô hình này.

## 17. Checker greedy và cận bài chia mảng

Với T:

~~~text
canPartition(T):
    parts = 1
    running = 0

    for value in a:
        if value > T:
            return false

        if running + value > T:
            parts++
            running = value
        else:
            running += value

        if parts > k:
            return false

    return true
~~~

Với phần tử không âm và yêu cầu liên tiếp, greedy nhét **tiền tố dài nhất** vào từng nhóm, nên dùng **ít nhóm nhất**.

Cận dưới:

**lo=max(a)**.

Cận trên:

**hi=sum(a)**.

Nếu T khả thi, T'>T cũng khả thi: predicate dạng false→true, tìm first true.

Ví dụ:

~~~text
a=[7,2,5,10,8], k=2

T=17: [7,2,5] | [10] | [8]
      cần 3 nhóm -> false

T=18: [7,2,5] | [10,8]
      cần 2 nhóm -> true

answer=18
~~~

## 18. Những giả thiết không được bỏ trong greedy chia mảng

**Không âm:** Nếu có số âm, một nhóm có thể tạm vượt T rồi giảm khi thêm số âm phía sau. Greedy cắt ngay khi vượt ngưỡng sẽ sai.

Ví dụ [10,−9] có tổng 1≤5 nhưng checker nhìn 10>5 có thể trả false. Đây là một bài toán khác.

**Liên tiếp:** Nếu cho phép gom các phần tử bất kỳ không theo thứ tự, bài toán cân bằng các nhóm có thể yêu cầu dynamic programming hoặc những phương pháp khó hơn.

**Đúng k không rỗng:** Nếu k>n, không thể chia thành k nhóm chứa ít nhất một phần tử. Code từ chối.

**Không giới hạn độ dài nhóm bổ sung:** Nếu có giới hạn số phần tử tối thiểu/tối đa ở mỗi nhóm, lập luận “cứ chia nhỏ” không còn tự đúng.

Bài toán feasibility phải được xây từ **đúng đề**, không chỉ từ mô hình có tên gần giống.

## 19. Một ví dụ cuối: căn bậc hai nguyên

Cho N≥0 kiểu long. Cần tìm r nguyên lớn nhất sao cho:

**r²≤N**.

Predicate true→false theo r≥0, nên dùng last true.

Tuy nhiên:

~~~java
mid * mid <= value
~~~

có thể overflow long và cho kết quả sai.

Với mid>0, tương đương:

~~~java
mid <= value / mid
~~~

Dùng phép chia để kiểm tra.

### Cận hữu hạn

Với N≤Long.MAX_VALUE:

**floor(sqrt(N))≤3037000499**.

Có thể đặt:

**lo=0**.

**hi=min(N,3037000499)**.

Khi N=0, vòng không chạy, kết quả 0. Khi N>0 và lo<hi, midpoint lệch phải luôn ≥1 nên phép chia N/mid hợp lệ.

Các ví dụ:

~~~text
sqrtFloor(0)=0
sqrtFloor(15)=3
sqrtFloor(16)=4
sqrtFloor(Long.MAX_VALUE)=3037000499
~~~

### Chứng nhận

Kết quả r thỏa:

**r²≤N<(r+1)²**,

nhưng nếu dùng phép nhân trên long để kiểm tra ở biên lớn, chính phép kiểm tra có thể tràn. Dùng BigInteger hoặc so sánh chia nguyên để xác minh.

## 20. Độ phức tạp: binary search nhân với chi phí checker

Gọi:

- **U=hi−lo+1** là số ứng viên nguyên trong miền ban đầu.
- **T_check(n)** là thời gian mỗi predicate.
- **T_pre(n)** là thời gian tiền xử lý.

Khi có tính đơn điệu:

**T_total = T_pre(n)+O(T_check(n)·log U)**.

Ví dụ:

| Bài | Tiền xử lý | Checker | Tổng |
| --- | --- | --- | --- |
| Shipping | O(n) lấy max/sum | O(n) | O(n log U) |
| Eating | O(n) lấy max | O(n) | O(n log maxPile) |
| Max gap | O(n log n) sort | O(n) | O(n log n+n log(span+1)) |
| Split array | O(n) lấy max/sum | O(n) | O(n log U) |
| Căn nguyên | O(1) | O(1) | O(log N) |

Bộ nhớ các checker trên thường O(1) ngoài input; max gap cần O(n) để clone/sort vị trí.

**Không gọi tổng thời gian O(log n)** chỉ vì vòng binary search chạy O(log U) bước. Mỗi bước có thể quét n phần tử.

### Số vòng thực tế

Tìm trên khoảng độ rộng 10¹² cần xấp xỉ 40 lần kiểm tra, nhưng mỗi lần có thể O(n). Nếu n lớn, chi phí checker mới là phần chi phối.

### Tái sử dụng tiền xử lý

Trong bài gap, sort positions **một lần trước binary search**, không sort lại trong mỗi lời gọi canPlace. Nếu sort ở mỗi checker, tổng chi phí có thể tăng không cần thiết.

## 21. Một template chung nhưng đừng giấu semantics

Có thể viết các helper tổng quát nhận LongPredicate:

~~~java
// Conceptual snippet, not the standalone program.
static long firstTrue(long lo, long hi,
                      LongPredicate f) {
    while (lo < hi) {
        long mid = lo + (hi - lo) / 2;
        if (f.test(mid)) {
            hi = mid;
        } else {
            lo = mid + 1;
        }
    }
    return lo;
}
~~~

Nhưng **caller phải chứng minh f(hi)=true và f đơn điệu**. Một thư viện search không thể tự biết ngưỡng có khả thi hay không.

Trong bài học, chương trình Java viết vòng lặp rõ trong từng lời giải để người đọc nhìn trực tiếp sự liên hệ giữa câu hỏi feasibility và cập nhật lo/hi.

### Tại sao không luôn dùng một template?

Một helper trả ranh giới đúng về cú pháp nhưng đôi khi che mất:

- Feasible direction.
- Feasible boundary.
- Giới hạn của miền đáp án.
- Có thể không có nghiệm.
- Checker cần dữ liệu sort hay thứ tự gốc.
- Kiểu int/long của khoảng cách.

Khi mới học, thiết kế đúng từng bài quan trọng hơn tái sử dụng một vòng while rất ngắn.

## 22. Kiểm soát overflow trong checker và biên

**(1) Sum int:** tổng nhiều int có thể lớn hơn Integer.MAX_VALUE.

**(2) Midpoint:** dùng lo+(hi−lo)/2 nếu hi−lo không tràn. Mẫu last true dùng hi−lo+1, cần miền đủ nhỏ để phép cộng an toàn.

**(3) Gap:** cast long trước khi trừ tọa độ.

**(4) Ceil division:** dùng (p−1L)/r+1 thay vì p+r−1 với int.

**(5) Bình phương:** dùng r≤N/r (r>0) thay vì r*r≤N nếu r*r có thể tràn.

**(6) Phép cộng trong checker:** dùng long cho runningSum, hoursUsed và capacity.

### Long không phải không giới hạn

Với bài có input **long[]** hoặc dữ liệu ngoài bộ nhớ với số phần tử khổng lồ, tổng có thể vượt long. Khi đó cần checked arithmetic hoặc BigInteger. Không nên tuyên bố đổi int sang long luôn giải quyết mọi overflow.

### Early exit đúng

Trong các predicate tổng những lượng không âm, nếu đã vượt ngưỡng thì có thể trả false ngay. Điều này vừa tiết kiệm thời gian vừa hạn chế việc tích lũy tiếp những số lớn không cần thiết.

## 23. Vì sao input validation là một phần của correctness?

Một API rõ ràng nên kiểm tra các tiền điều kiện:

- Shipping: days≥1, weights không âm; n=0 được code demo định nghĩa answer=0.
- Eating: ít nhất một đống, mỗi đống >0, H≥n.
- Gap: 2≤k≤n; duplicates được phép, vì mỗi phần tử của input là một ứng viên chọn riêng.
- Split: n>0, 1≤k≤n, mọi a[i]≥0.
- Sqrt: N≥0.

Nếu nhập sai, **ném IllegalArgumentException** rõ ràng hơn trả một “đáp án” không có nghĩa.

### Phân biệt public entrypoint và helper

Một helper canPlace có thể giả định positions đã sorted và k hợp lệ vì entrypoint luôn chuẩn bị điều đó. Nếu công khai helper cho caller bất kỳ, cần kiểm tra riêng các tiền điều kiện. Đừng coi một checker với input ngoài hợp đồng là chứng minh cho bài tối ưu.

### Checker cần cùng một dữ liệu qua mọi lần gọi

Nếu một predicate vô tình sort/mutate hoặc xóa phần tử trong input, những lần kiểm tra sau có thể thấy **bài toán khác**. Tính đơn điệu lý thuyết giả định đầu vào cố định, nên code nên giữ input immutable trong suốt quá trình search.

## 24. Java 17+ độc lập: bốn bài tối ưu và căn nguyên

Chương trình dưới đây triển khai **first true** cho shipping, eating và split; **last true** cho gap và căn nguyên. Các giới hạn và kiểu số được xác định rõ, không bỏ trường hợp rỗng/mức 0 hoặc tọa độ cực trị.

**Tên tệp: BinaryAnswerFeasibilityDemo.java**

~~~java
import java.util.Arrays;
import java.util.Objects;

public class BinaryAnswerFeasibilityDemo {

    static long minShipCapacity(int[] weights, int days) {
        Objects.requireNonNull(weights, "weights");

        if (days < 1) {
            throw new IllegalArgumentException(
                    "days must be positive");
        }

        long low = 0L;
        long high = 0L;

        for (int weight : weights) {
            if (weight < 0) {
                throw new IllegalArgumentException(
                        "weights must be nonnegative");
            }

            low = Math.max(low, weight);
            high += weight;
        }

        while (low < high) {
            long mid = low + (high - low) / 2L;

            if (canShip(weights, days, mid)) {
                high = mid;
            } else {
                low = mid + 1L;
            }
        }

        return low;
    }

    // Assumes weights are nonnegative and days >= 1.
    static boolean canShip(
            int[] weights, int days, long capacity) {

        if (capacity < 0L || days < 1) {
            return false;
        }

        int usedDays = 1;
        long load = 0L;

        for (int weight : weights) {
            if (weight > capacity) {
                return false;
            }

            if (load + weight > capacity) {
                usedDays++;
                load = weight;
            } else {
                load += weight;
            }

            if (usedDays > days) {
                return false;
            }
        }

        return true;
    }

    static long minEatingSpeed(int[] piles, long hours) {
        Objects.requireNonNull(piles, "piles");

        if (piles.length == 0 || hours < piles.length) {
            throw new IllegalArgumentException(
                    "No feasible positive speed");
        }

        long low = 1L;
        long high = 1L;

        for (int pile : piles) {
            if (pile <= 0) {
                throw new IllegalArgumentException(
                        "Each pile must be positive");
            }

            high = Math.max(high, pile);
        }

        while (low < high) {
            long mid = low + (high - low) / 2L;

            if (canEat(piles, hours, mid)) {
                high = mid;
            } else {
                low = mid + 1L;
            }
        }

        return low;
    }

    // Assumes positive piles; rate is required positive.
    static boolean canEat(
            int[] piles, long hours, long rate) {

        if (rate <= 0L) {
            return false;
        }

        long needed = 0L;

        for (int pile : piles) {
            needed += (pile - 1L) / rate + 1L;

            if (needed > hours) {
                return false;
            }
        }

        return true;
    }

    static long maxMinDistance(int[] positions, int k) {
        Objects.requireNonNull(positions, "positions");

        if (k < 2 || k > positions.length) {
            throw new IllegalArgumentException(
                    "Require 2 <= k <= number of positions");
        }

        int[] sorted = positions.clone();
        Arrays.sort(sorted);

        long low = 0L;
        long high =
                (long) sorted[sorted.length - 1] - sorted[0];

        while (low < high) {
            long mid = low + (high - low + 1L) / 2L;

            if (canPlace(sorted, k, mid)) {
                low = mid;
            } else {
                high = mid - 1L;
            }
        }

        return low;
    }

    // Assumes sorted nondecreasing, 2<=k<=n.
    static boolean canPlace(
            int[] sorted, int k, long minimumGap) {

        if (minimumGap < 0L) {
            return false;
        }

        int placed = 1;
        long last = sorted[0];

        for (int i = 1; i < sorted.length; i++) {
            long position = sorted[i];

            if (position - last >= minimumGap) {
                placed++;
                last = position;

                if (placed >= k) {
                    return true;
                }
            }
        }

        return placed >= k;
    }

    static long minLargestPartSum(int[] values, int k) {
        Objects.requireNonNull(values, "values");

        if (values.length == 0
                || k < 1 || k > values.length) {
            throw new IllegalArgumentException(
                    "Require 1 <= k <= n, n > 0");
        }

        long low = 0L;
        long high = 0L;

        for (int value : values) {
            if (value < 0) {
                throw new IllegalArgumentException(
                        "Values must be nonnegative");
            }

            low = Math.max(low, value);
            high += value;
        }

        while (low < high) {
            long mid = low + (high - low) / 2L;

            if (canPartition(values, k, mid)) {
                high = mid;
            } else {
                low = mid + 1L;
            }
        }

        return low;
    }

    // Assumes nonnegative values and 1<=k<=n.
    static boolean canPartition(
            int[] values, int k, long capacity) {

        if (capacity < 0L || k < 1) {
            return false;
        }

        int usedParts = 1;
        long running = 0L;

        for (int value : values) {
            if (value > capacity) {
                return false;
            }

            if (running + value > capacity) {
                usedParts++;
                running = value;
            } else {
                running += value;
            }

            if (usedParts > k) {
                return false;
            }
        }

        return true;
    }

    static long floorSqrt(long value) {
        if (value < 0L) {
            throw new IllegalArgumentException(
                    "Square root requires nonnegative input");
        }

        long low = 0L;
        long high = Math.min(value, 3037000499L);

        while (low < high) {
            long mid = low + (high - low + 1L) / 2L;

            // mid>0 here; division avoids mid*mid overflow.
            if (mid <= value / mid) {
                low = mid;
            } else {
                high = mid - 1L;
            }
        }

        return low;
    }

    public static void main(String[] args) {

        int[] ship1 = {
                1,2,3,4,5,6,7,8,9,10
        };

        System.out.println("Ship example 1: "
                + minShipCapacity(ship1, 5));
        System.out.println("Ship example 2: "
                + minShipCapacity(
                        new int[] {3,2,2,4,1,4}, 3));
        System.out.println("Ship example 3: "
                + minShipCapacity(
                        new int[] {1,2,3,1,1}, 4));
        System.out.println("Ship all zeros: "
                + minShipCapacity(
                        new int[] {0,0,0}, 2));
        System.out.println("Ship large total: "
                + minShipCapacity(
                        new int[] {
                                Integer.MAX_VALUE,
                                Integer.MAX_VALUE
                        }, 1));
        System.out.println("Ship empty: "
                + minShipCapacity(new int[] {}, 4));
        System.out.println("Ship single: "
                + minShipCapacity(new int[] {5}, 7));

        System.out.println("Eating example 1: "
                + minEatingSpeed(
                        new int[] {3,6,7,11}, 8));
        System.out.println("Eating example 2: "
                + minEatingSpeed(
                        new int[] {30,11,23,4,20}, 5));
        System.out.println("Eating example 3: "
                + minEatingSpeed(
                        new int[] {30,11,23,4,20}, 6));
        System.out.println("Eating ones: "
                + minEatingSpeed(
                        new int[] {1,1,1}, 3));
        System.out.println("Eating int max: "
                + minEatingSpeed(
                        new int[] {Integer.MAX_VALUE}, 1));

        int[] stalls = {1,2,8,4,9};
        int[] original = stalls.clone();

        System.out.println("Distance example 1: "
                + maxMinDistance(stalls, 3));
        System.out.println("Distance example 2: "
                + maxMinDistance(
                        new int[] {1,2,4,8,9}, 2));
        System.out.println("Distance duplicates: "
                + maxMinDistance(
                        new int[] {1,1,1}, 3));
        System.out.println("Distance extremes: "
                + maxMinDistance(
                        new int[] {
                                Integer.MIN_VALUE,
                                Integer.MAX_VALUE
                        }, 2));
        System.out.println("Distance negatives: "
                + maxMinDistance(
                        new int[] {-5,-1,0,4,11}, 3));
        System.out.println("Gap input preserved: "
                + Arrays.equals(stalls, original));

        System.out.println("Split example 1: "
                + minLargestPartSum(
                        new int[] {7,2,5,10,8}, 2));
        System.out.println("Split example 2: "
                + minLargestPartSum(
                        new int[] {1,4,4}, 3));
        System.out.println("Split all zeros: "
                + minLargestPartSum(
                        new int[] {0,0,0}, 2));
        System.out.println("Split large total: "
                + minLargestPartSum(
                        new int[] {
                                Integer.MAX_VALUE,
                                Integer.MAX_VALUE
                        }, 1));
        System.out.println("Split single: "
                + minLargestPartSum(
                        new int[] {10}, 1));

        System.out.println("Ship boundary 14/15: "
                + canShip(ship1, 5, 14)
                + " -> " + canShip(ship1, 5, 15));
        System.out.println("Eating boundary 3/4: "
                + canEat(new int[] {3,6,7,11}, 8, 3)
                + " -> "
                + canEat(new int[] {3,6,7,11}, 8, 4));

        int[] sortedStalls = stalls.clone();
        Arrays.sort(sortedStalls);

        System.out.println("Distance boundary 3/4: "
                + canPlace(sortedStalls, 3, 3)
                + " -> " + canPlace(sortedStalls, 3, 4));

        int[] split = {7,2,5,10,8};
        System.out.println("Split boundary 17/18: "
                + canPartition(split, 2, 17)
                + " -> " + canPartition(split, 2, 18));

        System.out.println("Sqrt(0): " + floorSqrt(0));
        System.out.println("Sqrt(15): " + floorSqrt(15));
        System.out.println("Sqrt(16): " + floorSqrt(16));
        System.out.println("Sqrt(Long.MAX_VALUE): "
                + floorSqrt(Long.MAX_VALUE));

        boolean rejected = false;

        try {
            minLargestPartSum(new int[] {1,-1}, 1);
        } catch (IllegalArgumentException e) {
            rejected = true;
        }

        System.out.println("Negative split rejected: "
                + rejected);
    }
}
~~~

Biên dịch/chạy với **JDK 17+**:

~~~bash
javac -encoding UTF-8 BinaryAnswerFeasibilityDemo.java
java BinaryAnswerFeasibilityDemo
~~~

**Đầu ra mẫu:**

~~~text
Ship example 1: 15
Ship example 2: 6
Ship example 3: 3
Ship all zeros: 0
Ship large total: 4294967294
Ship empty: 0
Ship single: 5
Eating example 1: 4
Eating example 2: 30
Eating example 3: 23
Eating ones: 1
Eating int max: 2147483647
Distance example 1: 3
Distance example 2: 8
Distance duplicates: 0
Distance extremes: 4294967295
Distance negatives: 7
Gap input preserved: true
Split example 1: 18
Split example 2: 4
Split all zeros: 0
Split large total: 4294967294
Split single: 10
Ship boundary 14/15: false -> true
Eating boundary 3/4: false -> true
Distance boundary 3/4: true -> false
Split boundary 17/18: false -> true
Sqrt(0): 0
Sqrt(15): 3
Sqrt(16): 4
Sqrt(Long.MAX_VALUE): 3037000499
Negative split rejected: true
~~~

### Đọc code theo invariant

Ba hàm minimize dùng:

**mid lệch trái**, trả true ⇒ hi=mid, trả false ⇒ lo=mid+1.

Hai hàm maximize dùng:

**mid lệch phải**, trả true ⇒ lo=mid, trả false ⇒ hi=mid−1.

**canShip** và **canPartition** gom tiền tố liên tiếp nhiều nhất có thể; chúng không thay thứ tự phần tử.

**canEat** tính tổng ceil division bằng long và dừng sớm nếu vượt H.

**canPlace** dùng khoảng cách long, sort một clone và xử lý cả tọa độ trùng/âm.

**floorSqrt** tránh phép nhân mid*mid có thể overflow.

Các dòng boundary cho thấy khi tìm first true, sát dưới đáp án false và tại đáp án true; khi tìm last true, tại đáp án true và sát trên false.

### Có phải chương trình đã kiểm tra mọi input trong helper?

Các entrypoints minShipCapacity, minEatingSpeed, maxMinDistance, minLargestPartSum và floorSqrt validate các tiền điều kiện cốt lõi. Các checker **canShip, canEat, canPlace, canPartition** giả định input đã được entrypoint hợp lệ chuẩn bị. Chúng được gọi trực tiếp trong main với dữ liệu xác định hợp lệ chỉ để in chứng nhận.

Nếu đưa helper ra thành API công khai, cần validate lại sortedness, miền k và giá trị đầu vào; không coi hành vi ngoài hợp đồng là kết quả của bài toán.

## 25. Kiểm thử bằng brute oracle độc lập

Một chương trình tìm kiếm nhị phân có thể trả kết quả trông hợp lý ngay cả khi checker greedy sai. Vì vậy cần oracle chậm nhưng **độc lập về thuật toán** để thử dữ liệu nhỏ.

### Shipping

Liệt kê mọi cách đặt vạch ngăn giữa các item. Với n item có n−1 khe, mỗi khe có thể cắt hoặc không, nên có **2^(n−1)** cách chia. Chỉ giữ những cách có ≤D nhóm, tính maximum group sum của mỗi cách và lấy minimum qua các cách.

Đây là oracle độc lập với checker tham lam.

### Eating

Thử lần lượt r=1..maxPile. Với mỗi tốc độ r, tính tổng ceil(pile/r) trực tiếp. Tốc độ đầu tiên đáp ứng H là đáp án.

### Max gap

Với n nhỏ, liệt kê mọi tổ hợp k chỉ số trong n vị trí. Sort các vị trí đã chọn, tính minimum gap giữa những điểm kế cận, rồi lấy **maximum** qua mọi tổ hợp.

Không gọi lại canPlace để tự xác minh.

### Split array

Liệt kê mọi tổ hợp **k−1 vị trí cắt** trong n−1 khe giữa các phần tử. Tính tổng từng đoạn, lấy maximum của mỗi phân hoạch, rồi lấy **minimum** trong các phân hoạch.

### Căn nguyên

Trên số nhỏ có thể thử r=0,1,...; với long lớn dùng **BigInteger** hoặc một oracle Newton nguyên để xác minh r²≤N<(r+1)² mà không tràn số.

**Chỉ chạy brute với n nhỏ**, vì số tổ hợp/phân hoạch tăng theo hàm mũ. Việc oracle chậm không phải vấn đề với unit tests nhỏ.

## 26. Kiểm thử đơn điệu riêng biệt

Kiểm thử đáp án chỉ chứng minh một số kết quả; nên kiểm tra **dạng true/false của predicate**.

Với first true:

~~~text
seenTrue = false
for x from lower to upper:
    if seenTrue and not F(x):
        FAIL
    if F(x):
        seenTrue = true
~~~

Điều này cho phép chuỗi false→true nhưng từ chối true→false.

Với last true:

~~~text
seenFalse = false
for x from lower to upper:
    if seenFalse and F(x):
        FAIL
    if not F(x):
        seenFalse = true
~~~

### Chứng nhận boundary sau khi tìm

First true trả x*:

- **F(x*)=true**.
- Nếu x*>lower bound, **F(x*−1)=false**.

Last true trả x*:

- **F(x*)=true**.
- Nếu x*<upper bound, **F(x*+1)=false**.

Khi cả predicate đúng, bounds bao phủ và monotonicity được chứng minh, những kiểm tra này giúp xác nhận chính xác ranh giới được tìm.

### Vì sao random test không thay chứng minh?

Một checker có thể đơn điệu trên 1000 test nhưng sai tại một trường hợp đặc biệt không được sinh. Cần cả proof của greedy, domain validation và oracle để giảm rủi ro.

## 27. Các ca biên quan trọng

1. Shipping n=0: convention answer=0 với days≥1.
2. Shipping n=1: capacity bằng item.
3. Shipping D=1: capacity=sum.
4. Shipping D≥n: capacity=max.
5. Shipping toàn 0: capacity=0.
6. Shipping negative weights: từ chối.
7. Shipping sum vượt int: dùng long.
8. Eating n=0: từ chối.
9. Eating H<n: không có tốc độ hữu hạn.
10. Eating H=n: speed=maxPile.
11. Eating H rất lớn: speed có thể 1.
12. Eating piles=0 hoặc âm: từ chối.
13. Eating pile Integer.MAX_VALUE: ceil division an toàn.
14. Gap k=1: không định nghĩa min pair distance, từ chối.
15. Gap k>n: từ chối.
16. Gap toàn cùng vị trí: answer=0.
17. Gap k=2: có thể chọn hai đầu xa nhất.
18. Gap có vị trí âm và cực trị int.
19. Gap input chưa sort: sort clone.
20. Split k=1: answer=sum.
21. Split k=n: answer=max.
22. Split tất cả 0: answer=0.
23. Split có số âm: từ chối.
24. Split n=0/k>n: từ chối.
25. Miền first true F(lo)=true: trả lo.
26. Miền last true F(hi)=true: trả hi.
27. Khoảng tìm chỉ có một ứng viên: vòng không chạy.
28. Predicate toàn false trong miền: không được giả đáp án.
29. Căn N=0,1 và perfect squares.
30. Căn Long.MAX_VALUE.
31. Input duplicates.
32. F(answer±1) ở hai phía.
33. Upper bound lớn hơn Integer.MAX_VALUE.
34. Số lần kiểm tra không phụ thuộc chỉ vào n.
35. Checker không làm biến đổi input qua các lượt.
36. Các trường hợp không đáp ứng hợp đồng phải bị từ chối.

## 28. Lỗi thường gặp trong bài nhị phân trên đáp án

1. **Chưa chứng minh predicate đơn điệu.**
2. **Nhầm minimize với maximize, đổi hướng cập nhật.**
3. **Midpoint lệch trái trong last true, gán lo=mid khiến không tiến.**
4. **Midpoint lệch phải thiếu điều kiện dừng hoặc overflow.**
5. **Đặt hi=mid−1 khi F(mid)=true ở first true, loại mid.**
6. **Đặt lo=mid khi F(mid)=false ở first true, không loại mid.**
7. **Đặt hi theo cảm tính mà không chứng minh feasible.**
8. **Không có phương án nhưng vẫn trả một số.**
9. **Trộn capacity lớn hơn dễ hơn với min distance lớn hơn khó hơn.**
10. **Greedy checker chỉ sound nhưng không complete.**
11. **Sort weights của shipping làm đổi bài toán thứ tự.**
12. **Cho phép tách item dù checker giả sử không được tách.**
13. **Quên item>capacity, dẫn tới checker true sai.**
14. **Dùng int sum, capacity hoặc currentLoad bị tràn.**
15. **Koko dùng floor thay ceil.**
16. **Koko dùng pile+rate−1 trong int có thể overflow.**
17. **Koko cho phép H<n mặc dù mỗi pile cần ít nhất một giờ.**
18. **Koko không dừng sớm khi totalHours>H.**
19. **Max gap không sort positions.**
20. **Max gap tính hiệu hai tọa độ trong int.**
21. **Max gap xử lý k=1 tùy tiện.**
22. **Xóa duplicates dù các bản ghi được chọn độc lập.**
23. **Sort input caller ngoài ý muốn.**
24. **Split áp dụng greedy cho số âm.**
25. **Split cho phép nhóm không liên tiếp nhưng dùng checker liên tiếp.**
26. **Split không giải thích đúng k so với ≤k.**
27. **Split k>n vẫn tìm kết quả.**
28. **Báo O(log n) mà quên chi phí checker O(n).**
29. **Quên preprocessing sort O(n log n) ở bài gap.**
30. **Không test F(answer−1)/F(answer+1).**
31. **Oracle dùng lại chính greedy checker.**
32. **Chỉ thử số nhỏ không thử extreme int/long.**
33. **Checker mutate input, làm F không cố định.**
34. **Dùng mid*mid≤N kiểu long, overflow.**
35. **Chia N/mid với mid=0.**
36. **Dùng hi+1 sentinel khi hi=Long.MAX_VALUE, overflow.**
37. **Đổi đơn vị thời gian/vận tốc không thống nhất.**
38. **Sai dấu ≥/≤ trong predicate.**
39. **Không phân biệt giá trị tối ưu với một phương án cụ thể.**
40. **Làm binary search trên miền thực nhưng cập nhật ±1 như số nguyên.**
41. **Không xét float rounding/NaN làm predicate không ổn định.**
42. **Tự khẳng định sort+greedy giải mọi scheduling**, nhiều bài khó hơn rất nhiều.
43. **Không báo upper bound chắc khả thi, đặc biệt khi sum=0.**
44. **Không kiểm tra D=1 hoặc K=n.**
45. **Dùng y=x*2 trong exponential search mà không xét overflow.**
46. **Coi brute oracle là production algorithm.**
47. **Coi performance một input duy nhất là worst-case proof.**
48. **Không kiểm tra hàm trả lời có tôn trọng hợp đồng dữ liệu.**

## 29. Binary search với đáp án thực

Đối với x thực, không có khái niệm “ứng viên kế tiếp” x+1. Một mẫu first true khi lo bất khả thi, hi khả thi:

~~~text
repeat a fixed number of iterations:
    mid = lo + (hi - lo) / 2

    if F(mid):
        hi = mid
    else:
        lo = mid

return hi
~~~

Có thể dừng khi hi−lo≤epsilon nếu precision và termination được thiết kế rõ.

### Những khác biệt quan trọng

- Không dùng mid+1 hoặc mid−1.
- Số lần lặp phải dựa trên range và tolerance.
- Floating-point midpoint có thể làm tròn thành lo hoặc hi.
- Predicate có NaN hoặc dao động do sai số làm tròn có thể phá tính đơn điệu thực tế.
- Không hứa kết quả bitwise chính xác của số thực như khi tìm giá trị nguyên.

Nếu bài yêu cầu **đáp án nguyên chính xác**, ưu tiên binary search trên long với các chứng nhận boundary.

## 30. Bài tập tự luyện có đáp án

**Câu 1.** F(x)=false,false,true,true, minimize x dùng mẫu nào?  
**Đáp án:** First true.

**Câu 2.** F(x)=true,true,false,false, maximize x dùng mẫu nào?  
**Đáp án:** Last true.

**Câu 3.** First true tại F(mid)=true cập nhật?  
**Đáp án:** hi=mid.

**Câu 4.** First true tại F(mid)=false cập nhật?  
**Đáp án:** lo=mid+1.

**Câu 5.** Last true tại F(mid)=true cập nhật?  
**Đáp án:** lo=mid, dùng midpoint lệch phải.

**Câu 6.** Last true tại F(mid)=false cập nhật?  
**Đáp án:** hi=mid−1.

**Câu 7.** Cận nào của first true phải chắc chắn feasible?  
**Đáp án:** hi.

**Câu 8.** Cận nào của last true phải chắc chắn feasible?  
**Đáp án:** lo.

**Câu 9.** Shipping [1,2,...,10], D=5, đáp án?  
**Đáp án:** 15.

**Câu 10.** canShip(14) và canShip(15)?  
**Đáp án:** false và true.

**Câu 11.** Vì sao lo=max(weights)?  
**Đáp án:** Không thể chia một item thành nhiều ngày.

**Câu 12.** Vì sao hi=sum(weights)?  
**Đáp án:** Có thể giao tất cả trong một ngày khi D≥1.

**Câu 13.** Hai item Integer.MAX_VALUE, D=1, capacity?  
**Đáp án:** 4294967294.

**Câu 14.** Eating [3,6,7,11], H=8, speed nhỏ nhất?  
**Đáp án:** 4.

**Câu 15.** Ceil(11/4) bằng mấy?  
**Đáp án:** 3 giờ.

**Câu 16.** Ceil division không tràn khi a,b dương?  
**Đáp án:** (a−1)/b+1.

**Câu 17.** H<n với mọi pile>0 có nghiệm không?  
**Đáp án:** Không.

**Câu 18.** Max gap [1,2,8,4,9], k=3?  
**Đáp án:** 3.

**Câu 19.** canPlace(3),canPlace(4)?  
**Đáp án:** true rồi false.

**Câu 20.** Vì sao gap dùng last true?  
**Đáp án:** Đòi khoảng cách càng lớn càng khó khả thi.

**Câu 21.** Span của INT_MIN và INT_MAX?  
**Đáp án:** 4294967295.

**Câu 22.** Vì sao không tự xóa duplicate stall coordinates?  
**Đáp án:** Mỗi bản ghi input có thể là ứng viên riêng biệt.

**Câu 23.** Split [7,2,5,10,8] thành k=2, answer?  
**Đáp án:** 18.

**Câu 24.** Checker split dùng ≤k hay đúng k?  
**Đáp án:** ≤k; với input không âm và k≤n có thể chia thêm thành đúng k nhóm.

**Câu 25.** Vì sao greedy split với số âm sai?  
**Đáp án:** Tổng tạm vượt T có thể giảm lại khi thêm phần tử âm.

**Câu 26.** Checker O(n), miền U ứng viên, complexity?  
**Đáp án:** O(n log U), cộng preprocessing.

**Câu 27.** Floor sqrt Long.MAX_VALUE?  
**Đáp án:** 3037000499.

**Câu 28.** Vì sao r*r≤N có thể sai trên long lớn?  
**Đáp án:** Phép nhân overflow.

**Câu 29.** Min answer x* phải kiểm tra gì tại boundary?  
**Đáp án:** F(x*) true và nếu x*>lo thì F(x*−1) false.

**Câu 30.** Max answer x* phải kiểm tra gì?  
**Đáp án:** F(x*) true và nếu x*<hi thì F(x*+1) false.

## 31. Checklist trước khi nộp

1. Mục tiêu minimize hay maximize?
2. Đã xác định ý nghĩa chính xác của x?
3. Feasible(x) có hợp đồng rõ không?
4. Có chứng minh tính đơn điệu theo đúng hướng không?
5. Checker có cả soundness và completeness không?
6. Nếu dùng greedy, đã có lập luận trao đổi hoặc induction chưa?
7. Các điều kiện liên tiếp, thứ tự cố định, số không âm có được giữ không?
8. Đã phân biệt đúng k với ≤k khi cần?
9. Có cách phát hiện input vô nghiệm không?
10. Cận dưới không cao hơn đáp án?
11. Cận trên không thấp hơn đáp án?
12. First true có hi feasible?
13. Last true có lo feasible?
14. Midpoint không tràn trong miền thực tế?
15. First true dùng hi=mid và lo=mid+1?
16. Last true dùng lo=mid và hi=mid−1 cùng upper midpoint?
17. Trường hợp lo=hi được xử lý không?
18. Sử dụng long cho tổng, khoảng cách, capacity?
19. Ceil division được tính đúng và an toàn?
20. Có early exit khi checker chắc chắn fail?
21. Checker không mutate input giữa các lần gọi?
22. Nếu cần sort, có sort một lần trước binary search?
23. Có phân tích O(T_check log U + T_pre)?
24. Đã test empty/singleton/zero/duplicates?
25. Đã test impossible input và invalid bounds?
26. Đã test int extremes, long sqrt?
27. Đã dùng brute oracle độc lập cho n nhỏ?
28. Đã kiểm tra monotonicity trên các miền nhỏ?
29. Đã kiểm tra boundary F(answer±1)?
30. Đã phân biệt tìm số thực xấp xỉ với số nguyên chính xác?

## 32. Kết luận

**Binary search on answer** là cách biến tối ưu hóa thành một loạt câu hỏi khả thi có trật tự. Khi **miền đáp án hữu hạn, cận tìm kiếm đúng, predicate đơn điệu và phép kiểm tra sound/complete**, mỗi lần binary search loại một nửa ứng viên và chỉ còn O(log U) lần gọi checker.

Có hai mô hình cần nhớ: **first true** cho ngưỡng nhỏ nhất khi tăng tài nguyên làm dễ hơn, và **last true** cho chất lượng lớn nhất khi tăng ngưỡng làm khó hơn. Những ví dụ shipping, eating speed, max-min distance và split array cùng dùng một ý tưởng nhị phân nhưng khác nhau ở **chiều đơn điệu, chứng minh greedy và xử lý biên**.

Muốn viết lời giải đáng tin cậy trong Java, hãy bắt đầu bằng **chứng minh feasibility**, sau đó mới chọn lo/hi, kiểu long, midpoint và cuối cùng kiểm tra đáp án bằng brute oracle cùng chứng nhận hai bên ranh giới.
