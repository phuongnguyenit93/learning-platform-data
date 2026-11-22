# Tìm kiếm hệ số phạt và điều kiện đơn điệu của lời giải

**Tìm kiếm hệ số phạt** là một kỹ thuật tối ưu quy hoạch động (dynamic programming, DP) dành cho những bài toán phải dùng **đúng K nhóm, đúng K đoạn hoặc đúng K lần chọn**, trong khi việc giữ thêm một chiều đếm số lần sử dụng khiến DP quá lớn. Ý tưởng là thay yêu cầu đúng K bằng một **phí λ cho mỗi lựa chọn**, giải bài toán đã phạt nhanh hơn, quan sát **số lựa chọn trong nghiệm tối ưu**, rồi tìm kiếm λ nhờ tính đơn điệu.

Trong lập trình thi đấu, kỹ thuật này thường được gọi là **WQS binary search**, **Aliens trick**, hoặc **Lagrangian relaxation** (nới lỏng Lagrange) trong bối cảnh rời rạc.

Điều quan trọng nhất là phân biệt ba mệnh đề:

1. **Số lựa chọn tối ưu thay đổi đơn điệu theo λ**: thường chứng minh được rất tổng quát.
2. **Tìm được λ tại ranh giới số lựa chọn K**: dùng binary search khi đã chứng minh tính đơn điệu và có cận hợp lệ.
3. **Thu hồi chính xác giá trị tối ưu với đúng K lựa chọn**: cần **điều kiện hỗ trợ** của hàm giá trị theo K; không tự suy ra từ hai mệnh đề trước.

Bài này triển khai bài chia dãy thành các đoạn có chi phí bình phương độ dài, chứng minh tính đơn điệu bằng bất đẳng thức, giải thích quy tắc phá hòa, trình bày Java 17+ hoàn chỉnh và chỉ ra phản ví dụ khi phép tìm hệ số phạt cho đáp án sai nếu thiếu điều kiện về **tính lồi rời rạc**.

## 1. Nhận biết bài toán có thể tối ưu bằng hệ số phạt

Một bài toán điển hình có dạng:

- Có nhiều lời giải hợp lệ khác nhau.
- Mỗi lời giải x có chi phí hoặc lợi nhuận **base(x)**.
- Mỗi lời giải có số lượng thành phần **count(x)**, chẳng hạn số đoạn đã chia.
- Yêu cầu **count(x)=K**.
- Nếu đưa K vào trạng thái, số trạng thái tăng từ O(n) lên O(nK), và số phép chuyển có thể tăng tương ứng.
- Nếu không buộc K mà chỉ thêm một phí cố định mỗi lần chọn, bài toán con có thể giải bằng DP ít chiều hơn.

Ví dụ: chia một dãy dài n thành **đúng K đoạn liên tiếp không rỗng**. Mỗi đoạn [j,i) có chi phí cost(j,i). DP đúng K thường là:

**exact[k][i] = min_{j<i} (exact[k−1][j] + cost(j,i))**,

với điều kiện chỉ dùng các j làm cho k đoạn đều không rỗng.

Số lượng k cần được ghi trong mỗi trạng thái, nên nếu xét tất cả j thì có đến O(Kn²) phép chuyển.

Thay vì lưu cả k, ta thử một hệ số phạt λ: **mỗi lần mở thêm một đoạn, cộng λ vào chi phí**. Khi ấy:

**dpλ[i] = min_{j<i} (dpλ[j] + cost(j,i) + λ)**.

Bài toán này chỉ có một chiều i. Tuy nhiên, để biết λ có tạo ra nhiều hay ít đoạn, DP phải trả **hai trường**: chi phí phạt tối ưu và số đoạn của phương án được chọn.

### Không phải trường hợp nào cũng phù hợp

Kỹ thuật sẽ không tự động áp dụng khi:

- Độ phức tạp của DP sau khi thêm phí vẫn quá lớn so với giới hạn.
- Không định nghĩa được chính xác **một lần sử dụng** là gì.
- Tập lời giải hợp lệ phụ thuộc vào λ theo một cách không kiểm soát.
- Không tìm được cận λ chứa sự chuyển đổi số lựa chọn cần thiết.
- Giá trị tối ưu đúng K **không được hỗ trợ** bởi một hệ số phạt tuyến tính.

Điều cuối là một bẫy toán học quan trọng: ngay cả khi count thay đổi đơn điệu, biểu thức thu hồi giá trị vẫn có thể **chỉ là một cận**, không phải đáp án.

## 2. Từ bài đúng K sang bài phạt

Cho tập lời giải khả thi S. Mỗi x∈S có:

- **cost(x)**: chi phí gốc.
- **cnt(x)**: số nhóm/đoạn/lần chọn.

Định nghĩa bài yêu cầu đúng k:

**f(k) = min{ cost(x) : x∈S và cnt(x)=k }**.

Khi k không khả thi, f(k) coi như +∞. Mục tiêu ban đầu là **f(K)**.

Cho λ là hệ số phạt, định nghĩa bài nới lỏng:

**F(λ) = min_{x∈S} [cost(x)+λ×cnt(x)]**.

Gộp các phương án theo số nhóm:

**F(λ) = min_k [f(k)+λ×k]**.

Ý nghĩa:

- λ dương: dùng nhiều nhóm phải trả nhiều phí hơn.
- λ tăng: nghiệm tối ưu thường dùng **ít nhóm hơn**.
- λ âm: dùng thêm nhóm có thể được thưởng trong mô hình minimization, nên có xu hướng tạo nhiều nhóm.
- Với cùng λ, nhiều số nhóm khác nhau có thể có **cùng tổng chi phí phạt**.

Ví dụ khi k=4 có cost gốc 16 và k=5 có cost gốc 14, tại λ=2:

~~~text
4 nhom: 16 + 2*4 = 24
5 nhom: 14 + 2*5 = 24
~~~

Tại điểm hòa, việc chọn phương án nào phụ thuộc **quy tắc phá hòa (tie-breaking)**. Quy tắc này phải được thiết kế nhất quán vì binary search cần biết **số nhóm được trả về**.

### Cách DP lưu trạng thái

Một trạng thái DP phạt thường là cặp:

**State = (penalizedCost, groups)**.

Khi chọn thêm một đoạn có chi phí gốc c:

**candidateCost = previous.penalizedCost + c + λ**,

**candidateGroups = previous.groups + 1**.

So sánh các ứng viên theo **penalizedCost trước**, chỉ dùng groups để phá hòa. Không được ưu tiên ít nhóm trước khi tối ưu chi phí phạt: như thế đã thay đổi bài toán.

## 3. Chứng minh số nhóm tối ưu không tăng khi λ tăng

Đây là nền tảng của **tìm kiếm nhị phân trên hệ số phạt**, và là phần có thể chứng minh mà không cần công thức chuyển DP cụ thể.

Lấy hai hệ số phạt **λ₁<λ₂**.

Gọi A là một nghiệm tối ưu tại λ₁; nó có chi phí gốc a và số nhóm p.

Gọi B là một nghiệm tối ưu tại λ₂; nó có chi phí gốc b và số nhóm q.

A tối ưu tại λ₁ nên:

**a+λ₁p ≤ b+λ₁q**.  (1)

B tối ưu tại λ₂ nên:

**b+λ₂q ≤ a+λ₂p**.  (2)

Cộng (1) và (2), rồi chuyển vế:

**(λ₂−λ₁)(q−p) ≤ 0**.

Vì λ₂−λ₁>0, suy ra **q≤p**.

**Kết luận:** Với bài minimization có phí +λ×cnt, tăng λ không thể làm số nhóm tối ưu tăng. Mệnh đề còn đúng khi chọn những nghiệm tối ưu bất kỳ ở hai λ **khác nhau**.

Điều này tạo một hàm kiểm tra có tính đơn điệu, ví dụ:

**good(λ) = [count(λ) ≥ K]**.

Khi λ tăng, good có dạng:

~~~text
true, true, true, ..., true, false, false, ..., false
~~~

Nếu có hai cận bao phủ điểm chuyển, có thể tìm **giá trị λ lớn nhất còn good**.

### Các điều KHÔNG được suy ra

- Số nhóm không nhất thiết giảm **từng đơn vị**; nó có thể nhảy từ 8 xuống 4.
- Không bảo đảm có λ khiến DP trả chính xác **K nhóm**.
- Không bảo đảm mọi k khả thi đều đạt minimum trong bài phạt tại một λ nào đó.
- Không bảo đảm từ nghiệm phạt có count khác K có thể dựng ngay một phương án đúng K.
- Không bảo đảm f(K)=F(λ)−λK nếu không có điều kiện hỗ trợ.

**Đơn điệu giúp tìm điểm chuyển; tính đúng của giá trị khôi phục là một vấn đề khác.**

## 4. Quy tắc phá hòa: chọn nhiều hay ít nhóm?

Bài học này sử dụng quy tắc thống nhất:

**Đầu tiên tối thiểu hóa chi phí phạt; nếu bằng nhau thì chọn phương án có số nhóm LỚN HƠN**.

Gọi là **MORE tie-breaker**.

~~~text
better(a,b):
    neu a.penalizedCost < b.penalizedCost: chon a
    neu a.penalizedCost > b.penalizedCost: chon b
    neu a.groups > b.groups:          chon a
    neu a.groups < b.groups:          chon b
    neu van hoa: chon phuong an xac dinh
~~~

Với MORE, ta sẽ tìm **hệ số phạt nguyên lớn nhất** mà count(λ)≥K. Tại một điểm hai số lượng nhóm có cùng chi phí phạt, MORE giữ phương án **nhiều nhóm hơn**, tức điểm hòa được coi là còn thuộc phía good của một số ngưỡng.

Có thể thiết kế ngược lại, **FEWER**, ưu tiên ít nhóm hơn. Khi ấy hướng tìm kiếm biên và việc lấy giá trị tại λ hoặc λ−1 có thể khác. Không lấy nguyên logic của MORE rồi thay dấu so sánh groups mà không xem lại biên.

Quy tắc phá hòa **không thay đổi giá trị F(λ)**, nhưng có thể thay đổi **count(λ)**. Đây là lý do phải lưu cả hai trường trong DP.

## 5. Đối ngẫu: F(λ)−λK là cận dưới, chưa chắc là đáp án

Với mọi nghiệm đúng K, đặc biệt nghiệm đạt f(K), nó cũng là một phương án hợp lệ khi bỏ ràng buộc đúng K. Vì vậy:

**F(λ) ≤ f(K)+λK**.

Suy ra:

**F(λ)−λK ≤ f(K)**.

Đây là **cận dưới** cho bài cần **tối thiểu hóa chi phí với đúng K nhóm**. Có thể tìm λ để cận dưới ấy mạnh nhất, nhưng không được mặc định cận luôn bằng đáp án.

### Điều kiện dấu bằng

Nếu có một nghiệm tối ưu của bài phạt tại λ dùng **đúng K nhóm**, thì:

**F(λ)=f(K)+λK**,

và do đó:

**f(K)=F(λ)−λK**.

Chứng minh: Nếu một nghiệm tối ưu phạt dùng K nhóm mà còn có phương án đúng K rẻ hơn về cost gốc, phương án rẻ hơn cũng có cost phạt thấp hơn, mâu thuẫn với tối ưu.

Điều thú vị là **DP có thể chọn một nghiệm count>K do tie-break**, trong khi **một nghiệm phạt khác có đúng K nhóm**. Lúc đó công thức vẫn chính xác. Phải xét **tập mọi nghiệm đồng tối ưu**, không chỉ count được DP chọn trả về.

Nếu không có λ làm k=K đạt minimum của f(k)+λk, công thức thu hồi **có độ chênh đối ngẫu** và có thể sai.

## 6. Tính lồi rời rạc là một điều kiện đủ quan trọng

Với bài tối thiểu hóa, đặt giá trị tối ưu đúng k là f(k). Khi tất cả số nhóm k=1..n đều khả thi, một điều kiện đủ phổ biến là f có **tính lồi rời rạc (discrete convexity)**:

**f(k−1)+f(k+1) ≥ 2f(k)**,

tương đương:

**f(k−1)−f(k) ≥ f(k)−f(k+1)**.

Nếu thêm nhiều nhóm giúp giảm chi phí, điều kiện này nói **lợi ích của mỗi nhóm bổ sung không tăng** khi số nhóm đã có tăng lên.

Với k nằm giữa miền khả thi, chọn hệ số phạt trong khoảng:

**f(k)−f(k+1) ≤ λ ≤ f(k−1)−f(k)**.

Khi f lồi rời rạc, khoảng này không rỗng và k là một minimizer của **f(t)+λt** trên mọi t khả thi, dù có thể hòa với các t khác. Do đó:

**F(λ)=f(k)+λk**, suy ra công thức thu hồi đúng.

Nếu chi phí nguyên, f(k) nguyên, các cận sai phân nguyên; có thể chọn **λ nguyên**. Nếu chi phí thực, điểm hỗ trợ có thể là số thực không nguyên.

**Điểm quan trọng:** count(λ) không tăng là một hệ quả tổng quát của tối ưu phạt, **không có nghĩa** f(k) đã lồi. Tính lồi/được hỗ trợ phải được chứng minh từ tính chất riêng của bài toán.

### Đường thẳng hỗ trợ

Mỗi số nhóm k tạo một đường thẳng theo λ:

**Lₖ(λ)=f(k)+kλ**.

Khi ấy **F(λ)=minₖ Lₖ(λ)** là **bao dưới** của các đường thẳng. Một k được hỗ trợ khi đường của nó chạm bao dưới ở một λ nào đó.

Nếu điểm (K,f(K)) nằm **trên** bao dưới phù hợp, công thức F−λK có thể khôi phục giá trị đúng. Nếu nằm **cao hơn**, không λ nào chọn được count=K là tối ưu phạt, và chỉ thu được cận dưới.

Đây là liên hệ giữa WQS, nới lỏng Lagrange và **hình học của hàm giá trị theo số lựa chọn**.

## 7. Ví dụ có chứng minh hỗ trợ: chia n phần tử thành K đoạn liên tiếp

Có n phần tử trên một dãy. Cần chia thành **K đoạn liên tiếp không rỗng**, không bỏ sót phần tử, mỗi đoạn có độ dài nguyên d>0. Chi phí đoạn dài d là:

**cost(d)=d²**.

Tổng chi phí của một cách chia là **∑ dᵢ²**, trong đó ∑dᵢ=n và số đoạn là K.

Ví dụ n=8,K=3:

~~~text
Chia theo do dai: 3, 3, 2
Tong chi phi:  9 + 9 + 4 = 22
~~~

Ví dụ n=8,K=5:

~~~text
Chia theo do dai: 2, 2, 2, 1, 1
Tong chi phi:  4 + 4 + 4 + 1 + 1 = 14
~~~

Đây là mô hình minh họa có công thức đáp án đóng, nhằm **kiểm chứng kỹ thuật tìm hệ số phạt**. Trong bài thực tế, chi phí đoạn có thể phụ thuộc dữ liệu trong đoạn và công thức đơn giản như dưới đây không còn tồn tại.

### 7.1. Chứng minh các đoạn phải cân bằng

Nếu có hai đoạn dài a,b với a≥b+2, chuyển một phần tử từ đoạn dài sang đoạn ngắn sẽ làm thay đổi tổng chi phí:

**(a−1)²+(b+1)²−a²−b²=−2(a−b)+2<0**.

Vậy một phương án có hai đoạn lệch nhau từ 2 trở lên **không thể tối ưu**. Các đoạn của phương án tối ưu có độ dài khác nhau nhiều nhất 1.

Đặt:

**q=floor(n/K)** và **r=n mod K**.

Khi đó có K−r đoạn dài q và r đoạn dài q+1. Giá trị tối ưu:

**f(K)=(K−r)q² + r(q+1)²**.

Công thức này được dùng làm **chuẩn tham chiếu độc lập** khi kiểm thử code WQS và exact-K DP.

Trong mô hình bình phương độ dài, có thể kiểm tra từ công thức cân bằng rằng các sai phân **f(k)−f(k+1)** không tăng theo k; vì thế **f lồi rời rạc**. Do đó mọi K giữa 1 và n được hỗ trợ, và công thức WQS trả **đúng giá trị** f(K).

### 7.2. DP đúng K thông thường

Đặt:

**exact[g][i] = chi phí nhỏ nhất khi chia i phần tử đầu thành đúng g đoạn không rỗng**.

Cơ sở:

- exact[0][0]=0.
- Những trạng thái chưa hợp lệ bằng +∞.

Công thức khi g≥1, i≥g:

**exact[g][i]=min_{g−1≤j<i} (exact[g−1][j]+(i−j)²)**.

Đoạn cuối là [j,i), có độ dài i−j. Phần trước phải chia thành đúng g−1 đoạn.

Bản trực tiếp:

- O(Kn) trạng thái.
- O(n) ứng viên j cho mỗi trạng thái.
- **O(Kn²)** thời gian, **O(Kn)** bộ nhớ.

Đây là một lời giải đúng độc lập với kỹ thuật phạt, hữu ích để kiểm tra và khi f không được hỗ trợ.

### 7.3. DP phạt chỉ còn một chiều

Đặt best[i] là tổng chi phí phạt nhỏ nhất để chia **i phần tử** thành một số đoạn bất kỳ.

**best[0]=0**, count[0]=0.

Với i≥1:

**best[i]=min_{0≤j<i} [best[j]+(i−j)²+λ]**.

Mỗi chuyển chọn đoạn cuối [j,i) nên tăng count thêm 1. Với quy tắc MORE, nếu các ứng viên có chi phí bằng nhau, chọn ứng viên có **count lớn hơn**.

Mỗi lần evaluate(λ):

- Thời gian **O(n²)**.
- Bộ nhớ **O(n)**.
- Trả **(F(λ),count(λ))**.

Chạy O(log B) lần với miền phạt có kích thước B sẽ tốn **O(n² log B)** với bản minh họa. Nếu có kỹ thuật tối ưu DP theo đường thẳng/convex hull trick, chi phí mỗi lần có thể giảm sâu hơn.

## 8. Ví dụ quan trọng: count có thể nhảy qua K mà vẫn thu hồi đúng

Với n=8, các giá trị f(k) là:

| k | f(k) | Các đoạn tối ưu |
| ---: | ---: | --- |
| 1 | 64 | [8] |
| 2 | 32 | [4,4] |
| 3 | 22 | [3,3,2] |
| 4 | 16 | [2,2,2,2] |
| 5 | 14 | [2,2,2,1,1] |
| 6 | 12 | [2,2,1,1,1,1] |
| 7 | 10 | [2,1,1,1,1,1,1] |
| 8 | 8 | [1,1,1,1,1,1,1,1] |

Xét **λ=2**:

~~~text
k=4: f(4)+2*4 = 16+8  = 24
k=5: f(5)+2*5 = 14+10 = 24
k=6: f(6)+2*6 = 12+12 = 24
k=7: f(7)+2*7 = 10+14 = 24
k=8: f(8)+2*8 = 8+16  = 24
~~~

Do đó **F(2)=24**. Có nhiều số nhóm cùng tối ưu, nhưng quy tắc MORE sẽ trả **count(2)=8**.

Ta đang muốn K=5, vậy count đã chọn **không bằng K**. Tuy nhiên, k=5 cũng thuộc nhóm các nghiệm phạt đồng tối ưu (do tính lồi), nên:

**f(5)=F(2)−2×5=24−10=14**.

Tại **λ=3**, nghiệm dùng k=4 nhóm trở thành tốt hơn:

- k=4: 16+3×4=28.
- k=5: 14+3×5=29.
- k=8: 8+3×8=32.

Vì vậy λ=2 là **hệ số phạt nguyên lớn nhất với count(λ)≥5** theo MORE. Count có thể nhảy từ **8 xuống 4** mà không trả 5,6,7 trong các nghiệm được DP chọn, nhưng **giá trị đúng K=5 vẫn thu hồi được**.

Một trường hợp khác:

**n=8,K=3,λ=10**: k=2 và k=3 cùng có chi phí phạt **52**. MORE trả k=3, nên f(3)=52−10×3=22.

**n=7,K=3,λ=8**: F(8)=41, count=3 và f(3)=41−8×3=17.

**Không bắt buộc count được trả về phải bằng K**, nhưng bắt buộc có chứng minh rằng **k=K được hỗ trợ** trước khi dùng công thức thu hồi.

## 9. Binary search hệ số phạt với quy tắc MORE

Ta sử dụng bài **minimize cost+λcount**, phá hòa theo **nhiều nhóm hơn**. Khi λ tăng, count không tăng. Đặt:

**good(λ) = [count(λ)≥K]**.

Tìm **λ nguyên lớn nhất còn good**.

~~~text
lo = he_so_nho_nhat_chac_chan_good
hi = can_tren_du_de_bao_phu_diem_chuyen

while lo < hi:
    mid = lo + (hi-lo+1)/2   // chia nguyen, lam tron len

    state = evaluate(mid)

    if state.groups >= K:
        lo = mid
    else:
        hi = mid-1

lambda = lo
state = evaluate(lambda)
answer = state.penalizedCost - lambda*K
~~~

### Vì sao phải làm tròn mid lên?

Nếu lo+1=hi và lấy mid=(lo+hi)/2 làm tròn xuống, ta được mid=lo. Khi good(mid) đúng và cập nhật lo=mid, lo không tăng, tạo **vòng lặp vô hạn**. Công thức làm tròn lên bảo đảm luôn kiểm tra hi khi chỉ còn hai giá trị.

### Chọn cận trong ví dụ bình phương độ dài

Với n>0 và 1≤K≤n:

- **λ=0**: n đoạn dài 1 là tối ưu, nên count(0)=n≥K.
- **λ=n²**: một đoạn là tối ưu hoặc không kém mọi cách chia nhiều đoạn; với chi phí bình phương dương của ví dụ, cách dùng một đoạn chiếm ưu thế cho n≥2. Với K=1, mọi count≥1 nên điều kiện good đúng trên toàn miền — trả hi vẫn hợp lệ.

Vì vậy có thể tìm trong **[0,n²]**. Đây là cận **được chứng minh riêng cho ví dụ** chứ không phải cận chung của Aliens trick.

Với bài tổng quát, phải tìm cận dựa trên giới hạn chi phí hoặc mở rộng dần miền thử một cách an toàn. Có những bài cần **λ âm** mới khuyến khích đủ nhiều nhóm. Không tự gán [0,10⁹] rồi coi đó là định lý.

### Trường hợp λ nguyên và thực

Nếu f(k) là các số nguyên và lồi rời rạc, khoảng hỗ trợ có các cận nguyên nên tồn tại λ nguyên thích hợp. Nếu chi phí có phần thập phân, λ hỗ trợ có thể không nguyên; dùng binary search nguyên rồi tuyên bố chính xác là không hợp lệ.

Với số thực, phép so sánh khi hòa và việc trừ λK có thể có sai số. Ưu tiên phép toán số nguyên hoặc hữu tỉ khi bài cho phép.

## 10. Java 17+: chương trình chạy độc lập

Chương trình dưới đây cài ba cách giải **độc lập để đối chiếu**:

1. **WQS penalty search**: DP phạt một chiều, binary search hệ số nguyên, phá hòa theo MORE.
2. **Exact-K DP**: bảng dp[g][i] trực tiếp, làm chuẩn tham chiếu.
3. **Công thức chia cân bằng**: tính f(K) từ độ dài q và q+1.

Mã hỗ trợ n=0,K=0 như trường hợp rỗng riêng; với n>0 yêu cầu 1≤K≤n. Giới hạn n≤2000 chỉ để bản Java minh họa tránh dùng quá nhiều thời gian/bộ nhớ với DP O(n²log n) và exact-K O(Kn²), không phải điều kiện toán học của WQS.

~~~java
import java.util.Arrays;

public class PenaltySearchDpDemo {

    private static final int MAX_N = 2000;

    record State(long penalizedCost, int groups) {}

    record Answer(long minimumCost, long penalty,
                  long relaxedCost, int relaxedGroups) {}

    // Minimize sum(length^2 + lambda); tie: more groups.
    static State evaluate(int n, long lambda) {
        long[] dp = new long[n + 1];
        int[] groups = new int[n + 1];

        dp[0] = 0;
        groups[0] = 0;

        for (int i = 1; i <= n; i++) {
            long best = Long.MAX_VALUE;
            int chosenGroups = -1;

            for (int j = 0; j < i; j++) {
                long length = (long) i - j;
                long candidate = dp[j] + length * length + lambda;
                int candidateGroups = groups[j] + 1;

                if (candidate < best
                        || (candidate == best
                            && candidateGroups > chosenGroups)) {
                    best = candidate;
                    chosenGroups = candidateGroups;
                }
            }

            dp[i] = best;
            groups[i] = chosenGroups;
        }

        return new State(dp[n], groups[n]);
    }

    static Answer solveWqs(int n, int k) {
        validate(n, k);

        if (n == 0) {
            return new Answer(0, 0, 0, 0);
        }

        long lo = 0;
        long hi = (long) n * n;

        while (lo < hi) {
            long mid = lo + (hi - lo + 1) / 2;
            State state = evaluate(n, mid);

            if (state.groups() >= k) {
                lo = mid;
            } else {
                hi = mid - 1;
            }
        }

        State chosen = evaluate(n, lo);
        return new Answer(
                chosen.penalizedCost() - lo * k,
                lo, chosen.penalizedCost(), chosen.groups());
    }

    // Exact number of segments: independent DP oracle.
    static long solveExactDp(int n, int k) {
        validate(n, k);
        if (n == 0) {
            return 0;
        }

        long inf = Long.MAX_VALUE / 4;
        long[][] dp = new long[k + 1][n + 1];

        for (long[] row : dp) {
            Arrays.fill(row, inf);
        }
        dp[0][0] = 0;

        for (int g = 1; g <= k; g++) {
            for (int i = g; i <= n; i++) {
                for (int j = g - 1; j < i; j++) {
                    if (dp[g - 1][j] == inf) {
                        continue;
                    }
                    long length = (long) i - j;
                    long candidate = dp[g - 1][j] + length * length;
                    if (candidate < dp[g][i]) {
                        dp[g][i] = candidate;
                    }
                }
            }
        }
        return dp[k][n];
    }

    // For square-length costs, balanced lengths are optimal.
    static long balancedFormula(int n, int k) {
        validate(n, k);
        if (n == 0) {
            return 0;
        }

        long q = n / k;
        long r = n % k;
        return (k - r) * q * q + r * (q + 1) * (q + 1);
    }

    private static void validate(int n, int k) {
        if (n < 0 || n > MAX_N || k < 0 || k > n
                || (n > 0 && k == 0)) {
            throw new IllegalArgumentException(
                    "Expected n from 0 to 2000; k=0 iff n=0, "
                    + "else 1<=k<=n");
        }
    }

    public static void main(String[] args) {
        int[][] tests = {
                {8, 5},
                {8, 3},
                {7, 3},
                {8, 1},
                {1, 1},
                {0, 0}
        };

        for (int[] test : tests) {
            int n = test[0];
            int k = test[1];

            Answer wqs = solveWqs(n, k);
            long exact = solveExactDp(n, k);
            long formula = balancedFormula(n, k);

            if (wqs.minimumCost() != exact || exact != formula) {
                throw new AssertionError("Mismatch: n=" + n
                        + ", k=" + k);
            }

            System.out.println("n=" + n + ", k=" + k
                    + ": " + wqs
                    + " | exactDP=" + exact
                    + " | formula=" + formula);
        }
    }
}
~~~

Lưu đúng tên **PenaltySearchDpDemo.java**, biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac PenaltySearchDpDemo.java
java PenaltySearchDpDemo
~~~

Đầu ra dự kiến chính xác:

~~~text
n=8, k=5: Answer[minimumCost=14, penalty=2, relaxedCost=24, relaxedGroups=8] | exactDP=14 | formula=14
n=8, k=3: Answer[minimumCost=22, penalty=10, relaxedCost=52, relaxedGroups=3] | exactDP=22 | formula=22
n=7, k=3: Answer[minimumCost=17, penalty=8, relaxedCost=41, relaxedGroups=3] | exactDP=17 | formula=17
n=8, k=1: Answer[minimumCost=64, penalty=64, relaxedCost=128, relaxedGroups=1] | exactDP=64 | formula=64
n=1, k=1: Answer[minimumCost=1, penalty=1, relaxedCost=2, relaxedGroups=1] | exactDP=1 | formula=1
n=0, k=0: Answer[minimumCost=0, penalty=0, relaxedCost=0, relaxedGroups=0] | exactDP=0 | formula=0
~~~

### Giải thích các thành phần

**State** giữ penalizedCost và groups. Khi chuyển từ j đến i, thêm đoạn [j,i) có chi phí **(i−j)²** và phí **λ**. Candidate sử dụng thêm một nhóm. Nếu chi phí phạt bằng nhau, chọn **candidateGroups lớn hơn**.

**evaluate** không có chiều K; mỗi hệ số phạt tạo một DP O(n²), rồi trả cả giá trị và số đoạn. Cần giữ quy tắc phá hòa trong mọi lần thử λ, không chỉ lần cuối.

**solveWqs** tìm λ lớn nhất còn groups≥K bằng mid làm tròn lên. Sau khi tìm, nó tính lại evaluate(λ), rồi lấy **penalizedCost−λK**, không phải penalizedCost−λ×groups được DP trả về.

**solveExactDp** có chiều K rõ ràng. Nó không phụ thuộc vào kết quả tìm kiếm phạt, nên có thể dùng làm chuẩn kiểm chứng khi n nhỏ.

**balancedFormula** dùng định lý các độ dài tối ưu khác nhau không quá 1; đây là cách kiểm tra thứ ba, độc lập cả hai DP.

Trường hợp **n=8,K=5** cố tình có **relaxedGroups=8**, nhằm nhấn mạnh rằng công thức lấy giá trị vẫn đúng trong ví dụ được hỗ trợ, mặc dù cấu trúc nghiệm phạt được chọn chưa có đúng K đoạn.

## 11. Có thể tối ưu mỗi lần chạy DP phạt bằng CHT

Với chi phí đoạn bình phương:

**dp[i] = min_{j<i} [dp[j]+(i−j)²+λ]**.

Khai triển:

**(i−j)² = i²−2ij+j²**.

Do đó:

**dp[i] = i²+λ + min_{j<i} [(−2j)×i + dp[j]+j²]**.

Với mỗi j đã hoàn thành, xem:

- **Hệ số góc mⱼ=−2j**.
- **Hệ số tự do bⱼ=dp[j]+j²**.
- Truy vấn giá trị đường thẳng **mⱼ×i+bⱼ** tại x=i.

Khi j tăng, hệ số góc giảm; khi i tăng, tọa độ truy vấn tăng. Với cấu trúc **Convex Hull Trick (CHT)** thích hợp, có thể tối ưu truy vấn minimum bằng hull và con trỏ đơn điệu trong một số mô hình, giảm chi phí mỗi lần evaluate về **O(n) khấu hao**.

Tuy nhiên, bài WQS cần cả **giá trị minimum lẫn count theo tie-breaker**. Nếu hull chỉ giữ một đường thẳng có giá trị tốt nhất nhưng bỏ mất các đường **hòa giá trị** tạo count lớn hơn, giá trị F(λ) vẫn có thể đúng trong khi count(λ) sai, làm hỏng binary search.

Khi cài CHT:

1. Đường thẳng phải mang thông tin count của trạng thái nguồn.
2. Phép so sánh tại giao điểm phải ưu tiên chi phí nhỏ trước, rồi count lớn.
3. Quy tắc loại đường thẳng khỏi hull không được làm mất ứng viên cần thiết ở các điểm hòa.
4. Tránh lỗi chia số nguyên khi tính giao điểm và nguy cơ tràn tích chéo.

Nếu evaluate giảm xuống O(n) và miền phạt có B giá trị nguyên, tổng thời gian có thể là **O(n log B)**. Nhưng hiệu năng chỉ là một nửa vấn đề: tính đúng của count và tính hỗ trợ của f(K) vẫn phải được chứng minh.

## 12. Phản ví dụ: đơn điệu chưa đủ để thu hồi đúng K

Xét bài chia 3 phần tử thành đoạn liên tiếp với chi phí nhân tạo:

- Đoạn độ dài 1: chi phí **0**.
- Đoạn độ dài 2: chi phí **10**.
- Đoạn độ dài 3: chi phí **0**.

Khi đó:

| K | Một cách chia | f(K) |
| ---: | --- | ---: |
| 1 | [3] | 0 |
| 2 | [1,2] hoặc [2,1] | 10 |
| 3 | [1,1,1] | 0 |

Ta muốn **đúng K=2**, đáp án thật là **10**.

Hàm đã phạt:

**F(λ)=min(λ, 10+2λ, 3λ)**.

- Nếu λ>0: một đoạn có giá trị λ và tối ưu.
- Nếu λ<0: ba đoạn có giá trị 3λ và tối ưu.
- Nếu λ=0: k=1 và k=3 cùng có giá trị 0, quy tắc MORE chọn k=3.

Count tối ưu là:

~~~text
lambda am:   count=3
lambda = 0:  count=3 (tie MORE)
lambda duong: count=1
~~~

Hàm count vẫn **không tăng** theo λ. Nhưng **không có λ nào khiến k=2 tối ưu**, vì chi phí của k=2 luôn cao hơn một trong k=1 và k=3.

Tìm λ nguyên lớn nhất với count≥2 cho kết quả λ=0; F(0)=0; biểu thức thu hồi:

**F(0)−0×2=0**,

trong khi **f(2)=10**. Công thức chỉ tạo **cận dưới 0**, không phải giá trị đúng.

Lý do là **f không lồi rời rạc**:

**f(1)+f(3)=0 < 2f(2)=20**.

Điểm k=2 không nằm trên bao dưới có thể được một đường thẳng phạt hỗ trợ.

**So sánh hai hiện tượng:**

- n=8,K=5 với chi phí bình phương: count có thể nhảy qua K nhưng **giá trị vẫn đúng** vì K được hỗ trợ.
- Ví dụ chi phí [0,10,0]: count nhảy qua K và **giá trị sai** vì K không được hỗ trợ.

Không thể dựa vào số lượng có nhảy qua K hay không để quyết định tính đúng; phải xem **cấu trúc hàm f(k)**.

## 13. Bài toán cực đại và dấu hệ số phạt

Nếu bài gốc cần **tối đa hóa lợi nhuận** reward(x) với đúng K nhóm, có thể đặt:

**G(λ)=max_x [reward(x)−λ×cnt(x)]**.

Tăng λ vẫn phạt việc dùng nhiều nhóm, nên count tối ưu cũng không tăng theo λ.

Với bất kỳ nghiệm đúng K:

**G(λ)≥reward(x)−λK**,

suy ra nếu g(K) là reward cực đại đúng K:

**g(K)≤G(λ)+λK**.

Lúc này G(λ)+λK là một **cận trên**, trong khi F(λ)−λK ở bài cực tiểu là **cận dưới**. Dấu bằng cần điều kiện hỗ trợ tương ứng, thường liên quan đến **tính lõm rời rạc** của g(k).

| Mục tiêu | Bài đã phạt | Count khi λ tăng | Giá trị dùng để kiểm tra |
| --- | --- | --- | --- |
| Min cost đúng K | min(cost+λcount) | Không tăng | F(λ)−λK, cận dưới |
| Max reward đúng K | max(reward−λcount) | Không tăng | G(λ)+λK, cận trên |

Không sao chép dấu cộng/trừ từ minimization sang maximization mà không xác định lại **hàm mục tiêu và chiều bất đẳng thức**.

## 14. Thu hồi giá trị khác phục hồi phương án

WQS thường trả **giá trị tối ưu** trong bài đúng K, nhưng một nghiệm được DP phạt chọn có thể dùng **khác K nhóm**.

Chẳng hạn n=8,K=5, λ=2, DP MORE chọn **8 đoạn đơn vị**, nhưng giá trị bài đúng K là **14**. Để **in một cách chia 5 đoạn** trong mô hình đặc biệt, dùng các độ dài cân bằng:

~~~text
Do dai: [2,2,2,1,1]
Doan:   [0,2), [2,4), [4,6), [6,7), [7,8)
Chi phi: 4+4+4+1+1 = 14
~~~

Không thể lấy nguyên 8 đoạn của nghiệm phạt rồi tuyên bố đó là “lời giải đúng K”. Với bài khác, việc phục hồi có thể cần:

- Lưu bảng exact-K và truy vết khi giới hạn đủ nhỏ.
- Thiết kế quy tắc xây dựng từ các nghiệm phạt đồng tối ưu, có chứng minh giữ nguyên tổng chi phí.
- Dùng tính chất riêng của bài toán để dựng đúng K nhóm.
- Giữ thêm thông tin tiền nhiệm/đường đi nếu có thể truy vết số nhóm mong muốn.

**Có f(K) chưa đồng nghĩa có một phương án đạt f(K)**. Yêu cầu đầu ra của đề quyết định có cần thêm thuật toán truy vết hay không.

## 15. Độ phức tạp, miền tìm kiếm và tràn số

| Cách làm với chi phí đoạn d² | Thời gian | Bộ nhớ |
| --- | --- | --- |
| DP đúng K trực tiếp | **O(Kn²)** | O(Kn) |
| Mỗi lần evaluate(λ) bằng DP 1D | **O(n²)** | O(n) |
| WQS + binary search trên B giá trị λ | **O(n² log B)** | O(n) |
| WQS nếu evaluate được tối ưu O(n) | **O(n log B)** | Tùy cấu trúc |
| Công thức cân bằng riêng cho d² | **O(1)** | O(1) |

Chú ý: với ví dụ d² có công thức O(1), **WQS không phải phương pháp nhanh nhất**; mục đích của ví dụ là minh họa và kiểm chứng kỹ thuật. Lợi ích thật xuất hiện ở những bài mà f(K) không có công thức đóng, nhưng evaluate(λ) có thể giải nhanh hơn DP có thêm chiều K.

### Chọn kiểu số

- Chi phí đoạn dài d là d², nên phải ép kiểu long **trước khi nhân** nếu d có thể lớn.
- Tổng chi phí phạt có thêm **λ×count**, có thể vượt int.
- Nếu dùng sentinel INF, không cộng vào INF khi trạng thái nguồn vô nghiệm.
- Không dùng phép trừ hai long trong comparator nếu có nguy cơ tràn; dùng Long.compare.
- Mã minh họa giới hạn n≤2000 nên các phép tính nằm an toàn trong long. Bài có chi phí rất lớn cần phân tích cận riêng.

### Chọn cận cho bài khác

Không có một hằng số hi chuẩn áp dụng mọi đề. Cần xét cận tổng chi phí, số nhóm tối đa và dấu của λ. Nếu λ âm, tìm biên phải hỗ trợ cả hai phía trục số. Nếu sử dụng số thực, epsilon và tie-breaker phải được thiết kế dựa trên sai số, không làm theo cảm tính.

## 16. Lỗi thường gặp

1. **Tin count đơn điệu thì công thức thu hồi chắc đúng.** Thiếu điều kiện hỗ trợ của K.
2. **Quên cộng λ đúng một lần khi thêm nhóm.** Count và phí bị lệch.
3. **Đếm số điểm cắt thay vì số đoạn** nhưng vẫn trừ λ×K. K đoạn có K−1 điểm cắt nội bộ.
4. **Chỉ lưu chi phí phạt, không lưu số nhóm.** Không thể binary search theo count.
5. **Không có quy tắc hòa**, hoặc mỗi lần evaluate dùng quy tắc khác nhau.
6. **Ưu tiên count trước cost**, làm DP không còn tối ưu hàm phạt.
7. **Tìm biên sai phía** khi đổi MORE thành FEWER.
8. **Mid làm tròn xuống** khi tìm true lớn nhất bằng lo=mid, gây lặp vô hạn.
9. **Không chứng minh cận λ**; kết quả có thể chạm biên giả.
10. **Mặc định λ phải không âm** dù bài có thể cần thưởng nhóm bằng λ âm.
11. **Count nhảy qua K thì tuyên bố sai ngay**, bỏ qua trường hợp nhiều count đồng tối ưu.
12. **Count nhảy qua K thì tuyên bố luôn đúng**, bỏ qua phản ví dụ không lồi.
13. **Trừ phí theo count thực tế** thay vì theo K khi cần f(K).
14. **Nhầm cận dưới và cận trên** giữa min và max.
15. **Coi nghiệm phạt có count khác K là phương án đúng K**, dù giá trị thu hồi có thể đúng.
16. **Quên K không khả thi**, như K>n với các đoạn bắt buộc không rỗng.
17. **Đặt cost vô nghiệm bằng 0** thay vì INF/cờ hợp lệ.
18. **Dùng int cho chi phí bình phương và λK**, gây tràn.
19. **Tối ưu bằng CHT nhưng bỏ mất tie count** khi hai đường thẳng cùng giá trị.
20. **Soạn một công thức WQS cho mọi bài** mà không phân tích cấu trúc hàm giá trị theo số nhóm.

## 17. Kiểm thử và đối chiếu bằng bài toán chậm

Đối với dữ liệu nhỏ, cách chắc chắn nhất để kiểm tra việc biến đổi và tìm λ là giữ một **bản exact-K DP chậm nhưng đúng**.

Với mỗi n nhỏ và mọi K khả thi:

1. Tính f(K) trực tiếp theo số nhóm.
2. Tính kết quả WQS với MORE, so **F(λ)−λK** với f(K).
3. So với **công thức cân bằng** nếu bài có công thức độc lập.
4. Duyệt một khoảng λ để xác nhận **count(λ) không tăng**.
5. Tại λ biên, kiểm tra count(λ)≥K và ở λ+1 count<K khi tồn tại điểm chuyển.
6. Thử các trường hợp **n=0,K=0**, **n=1,K=1**, **K=1**, **K=n**.
7. Thử điểm hòa kéo dài, đặc biệt n=8,K=5.
8. Thử một f không lồi như [0,10,0] để tránh khẳng định dấu bằng khi chỉ có cận đối ngẫu.

Bảng kỳ vọng của chương trình Java:

| n | K | λ biên | F(λ) | Count theo MORE | f(K) |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 8 | 5 | 2 | 24 | 8 | 14 |
| 8 | 3 | 10 | 52 | 3 | 22 |
| 7 | 3 | 8 | 41 | 3 | 17 |
| 8 | 1 | 64 | 128 | 1 | 64 |
| 1 | 1 | 1 | 2 | 1 | 1 |
| 0 | 0 | 0 | 0 | 0 | 0 |

Một bài kiểm thử chỉ xác minh **giá trị F(λ)** mà không xác minh **count(λ)** có thể bỏ sót lỗi tie-breaking. Cũng vậy, kiểm thử thấy count đơn điệu không chứng minh được **độ lồi của f(K)** trong bài tổng quát.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Trong bài tối thiểu hóa cost+λcount, khi λ tăng, count của nghiệm tối ưu biến đổi theo chiều nào?  
**Đáp án:** **Không tăng**. Chứng minh bằng hai bất đẳng thức tối ưu tại λ₁<λ₂.

**Câu 2.** Vì sao DP phạt phải trả cặp (cost,count) thay vì chỉ cost?  
**Đáp án:** Vì binary search cần kiểm tra số nhóm đang dùng để biết λ còn thuộc miền count≥K hay không.

**Câu 3.** Khi hai nghiệm có cùng chi phí phạt nhưng dùng 4 và 8 nhóm, quy tắc MORE chọn nghiệm nào?  
**Đáp án:** Nghiệm **8 nhóm**.

**Câu 4.** Với minimization, F(λ)−λK là cận dưới hay trên của f(K)?  
**Đáp án:** **Cận dưới**, vì F(λ)≤f(K)+λK.

**Câu 5.** Với n=8,K=5, tại λ=2 có F=24, count được chọn 8. Giá trị f(5) là gì?  
**Đáp án:** **14**, bằng 24−2×5; hợp lệ vì k=5 được hỗ trợ.

**Câu 6.** Có cần count trả về bằng K để suy ra giá trị đúng K không?  
**Đáp án:** Không nhất thiết. Nhưng phải chứng minh tồn tại một nghiệm phạt đồng tối ưu có đúng K, hoặc điều kiện hỗ trợ tương đương.

**Câu 7.** Vì sao ví dụ f(1)=0,f(2)=10,f(3)=0 làm WQS không thu hồi được f(2)?  
**Đáp án:** Vì k=2 không nằm trên bao dưới được hỗ trợ; số nhóm có thể nhảy từ 3 xuống 1 mà k=2 không tối ưu phạt tại λ nào.

**Câu 8.** Tính lồi rời rạc của f(k) có điều kiện sai phân nào?  
**Đáp án:** f(k−1)+f(k+1)≥2f(k).

**Câu 9.** Tại sao binary search tìm λ true lớn nhất dùng mid làm tròn lên?  
**Đáp án:** Để không mắc kẹt khi lo+1=hi.

**Câu 10.** Nếu bài cần max reward, đặt G(λ)=max(reward−λcount), công thức cận đúng K ra sao?  
**Đáp án:** g(K)≤G(λ)+λK; đây là **cận trên**.

**Câu 11.** Vì sao kết quả f(K) chưa đủ để in lời giải?  
**Đáp án:** DP phạt có thể chọn count khác K. Muốn xuất chính xác K nhóm cần phục hồi hoặc dựng một phương án đúng K riêng.

**Câu 12.** Nếu evaluate(λ) được tối ưu O(n) và binary search trên B giá trị phạt, tổng thời gian là gì?  
**Đáp án:** **O(n log B)** trong mô hình thao tác DP hằng thời gian.

## 19. Tổng kết

**Tìm kiếm hệ số phạt** biến ràng buộc đúng K thành một tham số ảnh hưởng tới số lần lựa chọn:

- Nới lỏng bài toán: **F(λ)=min_x(cost(x)+λcnt(x))**.
- Trong DP phạt, giữ **(chi phí phạt, số nhóm)**.
- Dùng một quy tắc hòa cố định, ví dụ **ưu tiên nhiều nhóm**.
- Chứng minh **count không tăng** khi λ tăng.
- Tìm **λ nguyên lớn nhất còn count≥K** với cận phù hợp.
- Chỉ dùng **f(K)=F(λ)−λK** khi **K được hỗ trợ**; một điều kiện đủ phổ biến là **f(k) lồi rời rạc**.
- Phân biệt **giá trị tối ưu** với **việc xuất phương án có đúng K nhóm**.
- Với bài cực đại, dùng dấu phạt và bất đẳng thức cận phù hợp.
- Nếu f không được hỗ trợ, WQS có thể chỉ cung cấp **cận đối ngẫu**; hãy chuyển về exact-K DP hoặc kỹ thuật khác đã chứng minh.

**Tư duy cần nhớ:** đơn điệu giúp tìm hệ số phạt nhanh, nhưng **định lý hỗ trợ mới cho phép biến kết quả đã phạt thành đáp án đúng K**. Hai phần ấy phải được kiểm tra riêng trước khi áp dụng Aliens trick vào một bài quy hoạch động mới.