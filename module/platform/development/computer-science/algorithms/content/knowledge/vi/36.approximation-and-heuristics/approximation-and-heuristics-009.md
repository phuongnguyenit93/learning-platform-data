# Ủ mô phỏng (simulated annealing) và lịch giảm nhiệt

**Ủ mô phỏng** (*simulated annealing*, SA) là một phương pháp tìm kiếm cục bộ ngẫu nhiên dành cho bài toán tối ưu, đặc biệt hữu ích khi không gian phương án quá lớn để duyệt toàn bộ. Khác với tìm kiếm tham lam chỉ nhận bước cải thiện, SA **đôi lúc chấp nhận bước làm lời giải xấu hơn** theo xác suất phụ thuộc vào độ xấu đi và một tham số gọi là **nhiệt độ** `T`. Khi nhiệt độ cao, thuật toán khám phá linh hoạt; khi nhiệt độ giảm, thuật toán dần ưu tiên khai thác vùng nghiệm tốt đã tìm.

Phần khó không chỉ là viết `exp(-delta/T)`. Một cài đặt đúng cần xác định **hàm mục tiêu**, **láng giềng hợp lệ**, **phân phối đề xuất**, **quy tắc chấp nhận**, **lịch giảm nhiệt** (*cooling schedule*), **ngân sách thời gian**, cách ghi nhớ **nghiệm tốt nhất từng gặp** và cách **đánh giá chất lượng mà không nhầm thực nghiệm với bảo đảm tối ưu**.

Bài thuộc chủ đề **Xấp xỉ và kinh nghiệm**. Ví dụ xuyên suốt là bài toán người du lịch **TSP** trên 9 thành phố, khoảng cách Manhattan, với phép hoán đổi hai vị trí trong hành trình. Chương trình Java 17+ chạy đầy đủ hai lịch **geometric** và **linear**, kiểm tra bằng **oracle vét cạn 40.320 thứ tự thăm** cùng các bài kiểm thử tái lập. Ví dụ cho thấy cả hai lịch có thể tìm nghiệm tối ưu trên một instance nhỏ, nhưng **không được suy ra SA bảo đảm tìm nghiệm tối ưu trên mọi instance**.

## 1. Mô hình tối ưu và trạng thái

Cho một không gian trạng thái hữu hạn `S` gồm các nghiệm khả thi. Cần giải:

```text
minimize E(s),  s thuộc S.
```

`E(s)` thường được gọi là **năng lượng** (*energy*) hoặc **hàm chi phí** (*objective*). Nếu bài toán cần **maximize score(s)**, có thể chuyển sang `E(s)=-score(s)` để dùng quy tắc minimization một cách nhất quán.

Ví dụ:

| Bài toán | Trạng thái s | Năng lượng E(s) | Láng giềng |
| --- | --- | --- | --- |
| TSP | Một hoán vị thành phố | Tổng độ dài tour đóng | Đổi hai vị trí, đảo một đoạn (2-opt) |
| Lập lịch | Phân công công việc | Tổng độ trễ/phạt | Đổi thứ tự, chuyển công việc |
| Phân hoạch đồ thị | Gán nhóm cho đỉnh | Chi phí cạnh cắt/phạt | Di chuyển một đỉnh sang nhóm khác |
| Bố trí vị trí | Ánh xạ đối tượng vào ô | Tổng khoảng cách/phạt | Hoán đổi hai đối tượng |

**Quan trọng:** Trạng thái phải đáp ứng ràng buộc, hoặc cơ chế tạo láng giềng/repair phải quản lý ràng buộc rõ ràng. Nếu hàm `neighbor(s)` sinh trạng thái không hợp lệ nhưng vẫn tính năng lượng và nhận, thuật toán có thể trả một “nghiệm tốt” không giải bài toán ban đầu.

### 1.1. Láng giềng và cấu trúc không gian tìm kiếm

Một phép biến đổi từ trạng thái s sang s' được gọi là **move**; tập các s' tạo được từ s là **láng giềng** `N(s)`. Với TSP, đổi hai vị trí là một move đơn giản: nó giữ đúng mỗi thành phố xuất hiện một lần, không làm hỏng tính hợp lệ của tour.

Các câu hỏi cần trả lời trước khi viết SA:

- Move có **giữ tính khả thi** không?
- Có thể đi từ mọi nghiệm tới mọi nghiệm khác bằng hữu hạn move không (không gian láng giềng **liên thông**)?
- Phân phối chọn move có **đối xứng** không? Nếu không, công thức Metropolis đơn giản có thể cần điều chỉnh để bảo đảm một phân phối cân bằng mong muốn.
- Một move tốn bao nhiêu thời gian để cập nhật chi phí?
- Có cần giữ một điểm xuất phát cố định để tránh biểu diễn trùng do quay vòng tour?

Ở chương trình mẫu, thành phố `0` luôn đứng đầu; mọi move **hoán đổi hai vị trí khác nhau trong các chỉ số từ 1 đến n−1**. Phép hoán đổi giữ nguyên một hoán vị và có thể sinh mọi thứ tự thăm còn lại qua một chuỗi hoán đổi, nên láng giềng liên thông trong không gian tour neo tại 0.

## 2. Quy tắc chấp nhận Metropolis

Tại bước t, trạng thái hiện tại s, một move tạo ứng viên s'. Đặt:

```text
delta = E(s') - E(s).
```

Với bài toán **minimize** và nhiệt độ dương `T>0`:

```text
Nếu delta <= 0: chấp nhận s' với xác suất 1.

Nếu delta > 0:
  chấp nhận s' với xác suất
  p = exp(-delta/T).
```

Tức là:

```text
accept(s -> s', T) = min(1, exp(-(E(s')-E(s))/T)).
```

Đối với `delta<=0`, có thể trực tiếp trả true mà không gọi exp để tránh các bất tiện số học. Đối với `delta>0`, lấy `u` ngẫu nhiên đều trong `[0,1)` rồi nhận move khi `u<p`.

### 2.1. Vì sao đôi lúc chấp nhận một bước tệ hơn?

Một tìm kiếm tham lam có thể mắc tại **cực tiểu cục bộ**: không láng giềng nào tốt hơn, dù ở một nơi khác có nghiệm tốt hơn. Để thoát khỏi vùng đó, thuật toán có thể phải **tạm tăng chi phí** trước khi đi xuống một vùng sâu hơn. Với T cao, SA sẵn sàng nhận nhiều bước tăng chi phí; với T thấp, nó ngày càng giống tham lam.

Đây là **chiến lược khám phá**, không phải một bảo đảm tự động: nếu các move không kết nối được không gian, hoặc lịch làm lạnh quá nhanh trước khi vượt rào cản năng lượng, thuật toán vẫn có thể bị kẹt.

### 2.2. Ví dụ tính xác suất

Với `delta=4`:

| Nhiệt độ T | Xác suất chấp nhận tăng chi phí `exp(-4/T)` |
| ---: | ---: |
| 8 | Khoảng `0.606531` |
| 2 | Khoảng `0.135335` |
| 1 | Khoảng `0.018316` |
| 0.5 | Khoảng `0.000335` |

Khi **delta lớn hơn**, xác suất nhận nhỏ hơn tại cùng T; khi **T lớn hơn**, xác suất nhận lớn hơn đối với cùng `delta>0`.

Nếu `delta=0`, move ngang bằng được chấp nhận. Nếu `delta<0`, move cải thiện được chấp nhận chắc chắn. **Không được dùng `exp(+delta/T)`** cho bài toán minimization; dấu đảo sẽ làm tăng xác suất nhận move xấu và làm công thức vượt 1 nếu không chặn.

### 2.3. Đặt T=0 phải có nhánh riêng

Công thức dùng T **dương**. Trong chương trình, `Tmin=0.1` nên không có chia cho 0. Nếu một thuật toán muốn chuyển sang tối ưu tham lam khi nhiệt độ chạm 0, phải định nghĩa rõ:

```text
T <= 0:
  accept if delta<=0; otherwise reject.
```

Không gọi `Math.exp(-delta/0)` rồi mong hành vi trên NaN/Infinity là một thiết kế tốt. Dùng một `Tmin>0` và kết thúc sau một số bước đã định thường đơn giản hơn.

## 3. Trạng thái hiện tại khác nghiệm tốt nhất từng thấy

SA lưu ít nhất hai khái niệm:

```text
current: trạng thái đang được di chuyển
best: nghiệm có chi phí thấp nhất từng gặp
```

Vì thuật toán **có thể nhận move xấu hơn**, sau một số bước:

```text
E(current) > E(best).
```

Nếu chỉ trả `current` cuối cùng, bạn có thể **đánh mất một nghiệm tốt đã tìm được từ trước**. Do đó mỗi khi nhận một trạng thái có năng lượng thấp hơn best, cần **sao chép** nghiệm vào `best` và ghi chi phí tương ứng.

**Bất biến:**

```text
E(best) <= E(current)
E(best) <= E(initial)
```

với quy ước best được cập nhật khi tìm được nghiệm tốt hơn. `bestCost` là một **cận trên** đối với giá trị tối ưu của bài toán minimize, vì nó là chi phí của một nghiệm khả thi đã tìm được. Nó **không phải** cận dưới và không tự chứng minh khoảng cách tới tối ưu.

### 3.1. Revert đúng khi từ chối

Đối với phép swap trực tiếp trên một mảng:

1. Hoán đổi hai vị trí trong `current`.
2. Tính `candidateCost`.
3. Quyết định nhận hoặc từ chối theo delta/T.
4. Nếu **nhận**: cập nhật `currentCost`, và `best` nếu tốt hơn.
5. Nếu **từ chối**: **swap lại** để trả mảng về trạng thái trước move.

Quên bước 5 sẽ khiến dữ liệu thực tế đã đổi dù chi phí/biến `current` vẫn ghi trạng thái cũ, phá hỏng kết quả. Chương trình Java ở dưới kiểm tra lại `cost(current)` và `cost(best)` để phát hiện lỗi này.

## 4. “Nhiệt độ” không phải một đơn vị vật lý tùy ý

T trong SA là tham số số học có **cùng thang đo với delta của hàm mục tiêu**: với `p=exp(-delta/T)`, thương `delta/T` phải vô thứ nguyên. Nếu nhân tất cả chi phí với 100 nhưng giữ nguyên T, các xác suất chấp nhận thay đổi mạnh.

Ví dụ năng lượng là tổng **mét đường đi**, T có thang đo tương ứng với mét. Nếu năng lượng là **số vi phạm quy tắc**, T cần được hiệu chỉnh theo mức thay đổi số vi phạm. Không sao chép `T0=100` từ một bài khác rồi mặc định phù hợp.

### 4.1. Hiệu chỉnh T0 từ mức tăng chi phí điển hình

Giả sử một move xấu đi có mức tăng điển hình `delta0>0`, ta muốn xác suất chấp nhận lúc bắt đầu xấp xỉ `p0`, với `0<p0<1`:

```text
p0 = exp(-delta0/T0)

ln(p0) = -delta0/T0

T0 = -delta0/ln(p0).
```

Với:

```text
delta0=8, p0=0.8

T0 = -8/ln(0.8)
   ≈ 35.851.
```

Ở nhiệt độ này, **move cụ thể tăng đúng 8 đơn vị** được nhận với xác suất 0.8. Nó không có nghĩa **80% mọi move** được nhận: tỷ lệ nhận tổng thể còn phụ thuộc phân phối delta, số move cải thiện/ngang bằng, và trạng thái hiện tại.

**Cách chọn delta0:** Có thể lấy mẫu các move hợp lệ từ vài trạng thái ban đầu, tính các delta dương, rồi chọn một thống kê như trung vị hoặc một phân vị phù hợp. Nếu gần như không có move tăng chi phí, cách hiệu chỉnh này không có dữ liệu đủ; cần chọn quy tắc khác.

## 5. Lịch giảm nhiệt là gì?

**Cooling schedule** là hàm cho biết nhiệt độ `T(t)` ở bước t. Một lịch cần nêu rõ:

- `T0`: nhiệt độ bắt đầu;
- `Tmin`: nhiệt độ kết thúc, thường **dương**;
- `N`: tổng số lần **đề xuất move** hoặc số mức nhiệt nhân số move mỗi mức;
- Công thức `T(t)` hoặc quy tắc điều chỉnh theo quan sát;
- Tiêu chí dừng và chính sách có **hâm nóng** (*reheating*) hay không.

Hai chương trình cùng ghi “alpha=0.99” vẫn có thể hành xử khác nếu một chương trình giảm nhiệt **mỗi move** còn chương trình kia giảm **mỗi 100 move**.

### 5.1. Lịch hình học (geometric cooling)

Cách thường dùng:

```text
T(t) = T0 * alpha^t,  0<alpha<1.
```

Nếu có chính xác `N>=2` bước, đánh chỉ số `t=0..N−1`, muốn bước đầu là T0 và bước cuối là Tmin, chọn:

```text
alpha = (Tmin/T0)^(1/(N-1)).

T(t) = T0 * exp( ln(Tmin/T0) * t/(N-1) ).
```

Đây là công thức dùng trong Java. T(t) luôn dương, giảm đều theo **tỷ lệ nhân**, chứ không giảm một lượng tuyệt đối cố định mỗi bước.

**Ví dụ:** `T0=100`, `Tmin=1`, `N=5`:

```text
alpha=(1/100)^(1/4) ≈ 0.316228.

T(0)=100
T(1)≈31.623
T(2)=10
T(3)≈3.162
T(4)=1.
```

### 5.2. Lịch tuyến tính (linear cooling)

Với cùng giới hạn đầu và cuối:

```text
T(t) = T0 + (Tmin-T0)*t/(N-1),
t=0..N-1.
```

Độ giảm tuyệt đối mỗi bước là `(T0−Tmin)/(N−1)`. Nếu người viết để `T(t)=T0−beta*t` mà không giới hạn số bước, T có thể âm; khi ấy cần dừng hoặc clamp theo hợp đồng. Trong ví dụ Java, bước cuối **đúng Tmin dương** nên không xảy ra T âm.

**Ví dụ:** `T0=100`, `Tmin=1`, `N=5`:

```text
T(0)=100
T(1)=75.25
T(2)=50.5
T(3)=25.75
T(4)=1.
```

Dù cùng `T0`, `Tmin`, `N`, hình học và tuyến tính **không có nhiệt độ giữa kỳ giống nhau**. Với `T0>>Tmin`, lịch tuyến tính thường giữ nhiệt cao hơn ở phần lớn giai đoạn giữa so với lịch hình học hiệu chỉnh cùng endpoints.

### 5.3. Lịch logarithmic

Một dạng lịch chậm thường được thảo luận trong phân tích lý thuyết:

```text
T(t)=c/log(t+t0)
```

với `t0>1`, `c>0`. Nó giảm rất chậm khi t lớn. Một số **định lý hội tụ tiệm cận** của simulated annealing trên không gian hữu hạn sử dụng lịch giảm nhiệt cỡ `c/log(t)`, với điều kiện về kết nối trạng thái, xác suất đề xuất, **hằng số c đủ lớn so với rào cản năng lượng**, và mô hình chuỗi Markov thích hợp.

**Không được** viết “lịch log luôn tìm tối ưu sau N bước”. Định lý liên quan tới **giới hạn khi thời gian tiến tới vô hạn**, dưới giả thiết toán học cụ thể; không đem lại một deadline hữu hạn thực dụng và không tự áp dụng với mọi c hay mọi neighborhood.

### 5.4. Lịch nhiều mức nhiệt, thích nghi và hâm nóng

Các biến thể thực tế có thể:

- Giữ một nhiệt độ trong L move để thực hiện nhiều bước tại cùng T, rồi mới giảm.
- Thử **tăng L** khi T thấp để tìm kỹ vùng nghiệm.
- Theo dõi tỷ lệ nhận move xấu để hiệu chỉnh nhịp giảm nhiệt.
- **Reheat** khi không cải thiện sau một số bước, rồi tiếp tục giảm.
- Dùng nhiều lần khởi tạo ngẫu nhiên (*multi-start*) và giữ best toàn cục.
- Thử nhiều loại neighborhood: swap, insert, reverse, 2-opt.

Những chiến lược này có thể hiệu quả với bài toán cụ thể, nhưng **không có một bộ tham số tối ưu cho mọi bài**. Khi dùng adaptive schedule, cần mô tả rõ biến phản hồi, giới hạn thay đổi và điều kiện dừng; không thể suy trực tiếp tính chất của lịch hình học cố định cho lịch thích nghi.

## 6. Chọn lịch nhiệt theo ngân sách

Giả sử chỉ được phép `N=2000` đề xuất move. Cần lựa chọn:

1. **Thước đo chi phí:** một đề xuất move có độ phức tạp bao nhiêu?
2. **T0:** đủ cao để tạo xác suất vượt rào cản cần thiết, nhưng không quá cao khiến duyệt ngẫu nhiên vô ích.
3. **Tmin:** đủ thấp để gần hành vi tham lam, vẫn dương nếu dùng công thức Metropolis thông thường.
4. **N:** cân bằng chất lượng và thời gian thực thi.
5. **Lịch:** geometric thường giảm mạnh trong miền nhiệt thấp; linear giữ nhiệt tương đối cao tới muộn hơn khi hai endpoint cách xa.
6. **Số lần restart và seed:** một nghiệm duy nhất dễ bị ảnh hưởng bởi vùng khởi tạo. Có thể chạy nhiều seed nếu thời gian cho phép.

Với bài TSP mẫu:

```text
delta0 = 8
p0 = 0.8
T0 ≈ 35.851
Tmin = 0.1
N = 2000

t = 0 ... 1999
```

Ở bước 1000, nhiệt độ minh họa:

```text
GEOMETRIC ≈ 1.891
LINEAR    ≈ 17.967.
```

Vì tuyến tính còn nóng hơn rất nhiều ở giữa quá trình, các move tăng năng lượng có thể được chấp nhận nhiều hơn tại cùng delta. Đây là **hệ quả của hai công thức**, không phải khẳng định lịch tuyến tính luôn tốt hơn; một lịch giữ nhiệt quá cao còn có thể đi loanh quanh và làm nghiệm cuối kém, dù best-so-far vẫn được giữ.

### 6.1. Đừng chọn alpha mà bỏ N

Nếu geometric dùng `alpha=0.99`:

```text
T(100)=T0*0.99^100 ≈ 0.366*T0
T(1000)=T0*0.99^1000 ≈ 0.000043*T0.
```

Một lịch như thế có thể đông cứng gần như hoàn toàn trước khi hết ngân sách 10.000 bước. Ngược lại `alpha=0.9999` giữ nhiệt rất cao sau 1.000 bước. Vì thế nên **thiết kế từ T0, Tmin, N**, rồi suy alpha, thay vì bê nguyên alpha từ ví dụ không liên quan.

## 7. Ví dụ TSP: trạng thái, năng lượng và neighbor

Cho n thành phố với tọa độ nguyên `(x_i,y_i)` và khoảng cách **Manhattan**:

```text
d(i,j)=|x_i-x_j|+|y_i-y_j|.
```

Trạng thái là một hoán vị `tour=[v0,v1,...,v(n-1)]`; tour **đóng vòng** nên phải cộng cạnh cuối về thành phố đầu:

```text
E(tour) =
    d(v0,v1)+d(v1,v2)+...+
    d(v(n-2),v(n-1))+d(v(n-1),v0).
```

Ví dụ 4 thành phố tạo hình vuông cạnh 2:

```text
(0,0),(2,0),(2,2),(0,2)

Tour [0,1,2,3]:
  2+2+2+2 = 8.

Tour [0,2,1,3]:
  4+2+4+2 = 12.
```

Nếu quên cạnh quay về điểm xuất phát, thuật toán tối ưu **Hamiltonian path**, không phải tour TSP. Điều này thay đổi bài toán.

### 7.1. Giữ thành phố 0 cố định

Một chu trình không có điểm bắt đầu hình học duy nhất. Mã luôn đặt thành phố **0 ở vị trí đầu** để tránh biểu diễn lặp do quay chu trình. Vì khoảng cách Manhattan đối xứng, đi ngược hướng cũng có cùng chi phí; mã **không loại** đối xứng hướng ngược, nhưng điều đó không làm sai nghiệm, chỉ lặp một số tour tương đương trong oracle vét cạn.

Với n=9, sau khi cố định thành phố 0 còn:

```text
(n-1)! = 8! = 40320
```

thứ tự thăm các thành phố khác. Mã vét cạn tất cả để biết **optimum thật sự** của instance nhỏ. Trên n lớn, `(n-1)!` trở nên không thể chấp nhận, nên simulated annealing chỉ là phương pháp tìm một nghiệm tốt theo ngân sách.

### 7.2. Move swap hai chỉ số khác nhau

Mã chọn đều hai **chỉ số khác nhau** trong 1..n−1, rồi đổi vị trí. Move này:

- Không đổi độ dài mảng.
- Không làm mất hoặc lặp thành phố.
- Không đổi vị trí đầu tiên 0.
- Đảo move bằng chính phép swap ấy để backtrack khi từ chối.
- Có phân phối đề xuất đối xứng giữa hai tour kề nhau theo phép swap.
- Có thể kết nối mọi hoán vị của n−1 vị trí qua một chuỗi swap.

Vì n≥3, luôn có ít nhất hai vị trí khác nhau để đổi. Cách chọn trong Java lấy `i` đều từ 1..n−1, sau đó lấy `j` đều trong **các vị trí còn lại**; tránh vòng lặp “rút cho tới khi j≠i” nhưng vẫn có phân phối cặp vị trí hợp lệ.

### 7.3. Swap khác 2-opt

**Swap** hoán đổi hai thành phố trong thứ tự thăm. **2-opt** chọn hai cạnh rồi đảo một đoạn thứ tự để loại giao cắt/tái nối tour. Hai neighborhood khác nhau có cảnh quan tối ưu cục bộ khác nhau; **không dùng công thức delta của 2-opt** cho swap.

Chương trình minh họa tính lại toàn bộ chi phí tour trong `O(n)` sau mỗi swap, dễ kiểm tra tính đúng. Có thể tối ưu với delta cục bộ theo các cạnh bị ảnh hưởng để đạt `O(1)` cho một số kiểu move và hàm chi phí thích hợp, nhưng phải xử lý các vị trí kề nhau, cạnh đóng vòng và việc đếm trùng cạnh. Khi dạy cơ chế SA, tính đúng rõ ràng quan trọng hơn một delta tối ưu hóa dễ sai.

## 8. Pseudocode simulated annealing có lưu best

```text
SIMULATED_ANNEALING(initial, N, T0, Tmin, schedule):
    current = copy(initial)
    currentCost = E(current)
    best = copy(current)
    bestCost = currentCost

    for t=0..N-1:
        T = schedule(t,T0,Tmin,N)
        candidate = randomValidNeighbor(current)
        candidateCost = E(candidate)
        delta = candidateCost - currentCost

        if delta<=0:
            accept = true
        else:
            u = Uniform[0,1)
            accept = (u < exp(-delta/T))

        if accept:
            current = candidate
            currentCost = candidateCost
            if currentCost < bestCost:
                best = copy(current)
                bestCost = currentCost

    return best, bestCost
```

Điểm cần lưu ý:

- `current` là trạng thái để tiếp tục khám phá; `best` là **kết quả sẽ trả**.
- Phải có nghiệm **khả thi** ngay từ đầu; các move luôn giữ tính khả thi.
- Với `N` cố định, thuật toán dừng đúng sau N đề xuất, nhưng có thể chưa tới tối ưu.
- Không nhất thiết phải nhận một move chỉ vì nó chưa bị đề xuất trước đó.
- Nếu dùng **in-place move**, khi từ chối phải đảo ngược thay đổi, không giữ candidate trong current.
- Nếu hàm mục tiêu có nhiều thành phần với trọng số, scale của delta/T cần được hiểu đúng.

## 9. Metropolis, phân phối Boltzmann và phạm vi lý thuyết

Với **nhiệt độ cố định** T>0, không gian trạng thái hữu hạn, và cơ chế đề xuất láng giềng **đối xứng** `q(s→s')=q(s'→s)`, quy tắc Metropolis có quan hệ chi tiết với phân phối Gibbs/Boltzmann:

```text
pi_T(s) =
    exp(-E(s)/T) / Z(T),

Z(T) = sum_{x in S} exp(-E(x)/T).
```

Giải thích: những trạng thái có năng lượng thấp được gán trọng số lớn hơn; khi T nhỏ, tỷ trọng nghiêng về các trạng thái tối ưu. Với các điều kiện về kết nối và tính chất chuỗi Markov thích hợp, phân phối có thể được xem là phân phối cân bằng khi giữ T cố định đủ lâu.

Một kiểm tra xác suất cặp láng giềng:

```text
If E(s')>E(s):

accept(s->s')=exp(-(E(s')-E(s))/T)
accept(s'->s)=1.
```

Khi nhân với trọng số `exp(-E/T)`, dòng xác suất qua hai chiều cân bằng vì:

```text
exp(-E(s)/T) * exp(-(E(s')-E(s))/T)
    = exp(-E(s')/T).
```

**Giới hạn rất quan trọng:** Một thuật toán đang giảm T theo thời gian **không phải** một Markov chain đồng nhất tại T cố định. “Gibbs concentration near optimum” không chứng minh rằng một lịch làm lạnh bất kỳ với 2.000 bước sẽ tìm optimum. Lịch logarithmic có các định lý hội tụ tiệm cận dưới giả thiết nhất định; geometric/linear thường dùng theo thực nghiệm và **không tự mang bảo đảm tối ưu hữu hạn**.

### 9.1. Tính liên thông và tính bất biến

Nếu neighborhood tách không gian nghiệm thành hai vùng không thể chuyển qua lại, SA không thể tới nghiệm tối ưu ở vùng khác bất kể T cao bao nhiêu. T lớn chỉ giúp **chấp nhận move được đề xuất**, không tạo ra loại move mà bộ sinh hàng xóm không bao giờ sinh.

Nếu phân phối đề xuất **không đối xứng**, để hướng tới phân phối mục tiêu có thể cần một quy tắc kiểu Metropolis–Hastings có thêm tỷ số proposal, thay vì tự động áp `exp(-delta/T)`. Trong thực hành heuristic, có thể chọn nhiều move không đối xứng mà không nhằm sampling chính xác, nhưng khi viện dẫn định lý Gibbs/detailed balance phải kiểm tra giả thiết.

## 10. Ghi chẩn đoán để hiểu quá trình giảm nhiệt

Một lần chạy SA nên thu thập:

| Chỉ số | Ý nghĩa | Không được hiểu nhầm thành |
| --- | --- | --- |
| `initialCost` | Chi phí tour lúc bắt đầu | Chi phí tối ưu |
| `current/finalCost` | Chi phí trạng thái cuối | Nghiệm tốt nhất từng gặp |
| `bestCost` | Nhỏ nhất trong các nghiệm đã gặp | Giá trị optimum nếu chưa có oracle |
| `accepted/N` | Tỷ lệ **mọi move được nhận** | Xác suất tối ưu |
| `uphillAccepted/uphillProposed` | Tỷ lệ move tăng chi phí được nhận trong mẫu | Cùng một hằng số trên mọi nhiệt độ |
| `bestImprovements` | Số lần best được cải thiện | Số cực tiểu toàn cục |
| `temperature(t)` | Lịch nhiệt đã đặt | Nhiệt động lực học được đo từ dữ liệu |

Để so sánh các lịch công bằng, giữ **cùng mô hình chi phí, cùng tập thành phố, cùng số đề xuất, cùng nguồn seed/số lần thử**, và báo phân phối kết quả trên nhiều seed thay vì chỉ chọn một run thắng đẹp.

**Đọc đúng tỷ lệ:** `accepted/N` bao gồm move cải thiện và ngang bằng được chấp nhận; `uphillAccepted/uphillProposed` có mẫu số **chỉ những move đề xuất làm tăng chi phí**. Hai tỷ lệ có thể rất khác và không phải ước lượng trực tiếp của `p0` calibrate, vì nhiệt độ và phân phối delta thay đổi qua các bước.

### 10.1. Chọn điểm dừng

Những quy tắc thường dùng:

- Ngân sách **N đề xuất** cố định, dễ so sánh và chặn thời gian.
- Dừng khi đạt `Tmin` hoặc khi số mức nhiệt đạt giới hạn đã định.
- Dừng nếu best không cải thiện sau L move, nhưng điều này **không chứng minh tối ưu**.
- Dừng khi đã đạt một ngưỡng mục tiêu có xác minh hoặc lower bound thích hợp.
- Dùng nhiều restart và lấy best cuối cùng, khi chi phí cho phép.

Trong mã Java, có đúng `N=2000` đề xuất cho mỗi lịch; không dừng sớm khi tìm nghiệm tốt và không hâm nóng.

## 11. Java 17+ đầy đủ: geometric và linear trên TSP

Lưu chương trình vào **`SimulatedAnnealingCoolingDemo.java`**. Mỗi trạng thái là một tour đóng trên 9 thành phố với **đường đi Manhattan**. Chương trình:

- Khởi tạo tour bằng Fisher–Yates với thành phố 0 cố định.
- Tính tổng chi phí chính xác dưới dạng `long`.
- Dùng Metropolis để quyết định nhận move xấu.
- Lưu `bestTour` độc lập với `current`.
- Triển khai geometric và linear với cùng điểm đầu, điểm cuối và số bước.
- Hiệu chỉnh T0 từ `delta0=8`, xác suất mục tiêu `p0=0.8`.
- Vét cạn 8! = **40.320** thứ tự thăm để tìm optimum của instance nhỏ, dùng làm oracle.
- Kiểm thử 1.000 tour ngẫu nhiên với hai cách tính chi phí và 120 lượt chạy SA, kiểm tra tour luôn hợp lệ và không tốt hơn giá trị optimum thật.
- Đối chiếu chạy lại cùng seed để kiểm tra tính tái lập; **không dùng một seed cố định để tuyên bố thuật toán tốt trên mọi trường hợp**.

Mã chỉ nhận mảng thành phố có **n≥3** đối với hàm anneal; thành phố 0 phải neo ở vị trí đầu và các chỉ số khác xuất hiện đúng một lần. Tọa độ là số nguyên nhỏ; phép trừ khoảng cách được ép về `long` trước để tránh overflow do trừ `int`. Hàm `cost` tính lại `O(n)` ở mỗi đề xuất; tối ưu hóa delta không nằm trong ví dụ này.

```java
import java.util.*;

public class SimulatedAnnealingCoolingDemo {
    record Point(int x, int y) {}
    enum Schedule { GEOMETRIC, LINEAR }

    static final Point[] CITIES = {
            new Point(0, 0), new Point(4, 1),
            new Point(7, 0), new Point(9, 4),
            new Point(7, 8), new Point(3, 7),
            new Point(0, 6), new Point(2, 4),
            new Point(5, 3)
    };

    static long distance(Point a, Point b) {
        return Math.abs((long) a.x() - b.x())
                + Math.abs((long) a.y() - b.y());
    }

    static long cost(Point[] points, int[] tour) {
        long total = 0;
        for (int i = 0; i < tour.length; i++) {
            int j = (i + 1) % tour.length;
            total += distance(points[tour[i]], points[tour[j]]);
        }
        return total;
    }

    static void validate(Point[] points, int[] tour) {
        if (points.length != tour.length || tour.length < 3
                || tour[0] != 0) {
            throw new IllegalArgumentException(
                    "Tour must anchor city 0 and have >=3 cities");
        }
        boolean[] seen = new boolean[tour.length];
        for (int v : tour) {
            if (v < 0 || v >= tour.length || seen[v]) {
                throw new IllegalArgumentException("Invalid permutation");
            }
            seen[v] = true;
        }
    }

    static int[] randomTour(int n, SplittableRandom rng) {
        int[] tour = new int[n];
        for (int i = 0; i < n; i++) tour[i] = i;
        for (int i = n - 1; i > 1; i--) {
            int j = 1 + rng.nextInt(i);
            swap(tour, i, j);
        }
        return tour;
    }

    static void swap(int[] a, int i, int j) {
        int t = a[i]; a[i] = a[j]; a[j] = t;
    }

    static double initialTemperature(
            double uphillIncrease, double targetAcceptance) {
        if (!(uphillIncrease > 0.0)
                || !(targetAcceptance > 0.0)
                || !(targetAcceptance < 1.0)) {
            throw new IllegalArgumentException("Bad calibration");
        }
        return -uphillIncrease / Math.log(targetAcceptance);
    }

    static double temperature(
            Schedule schedule, double start, double end,
            int step, int steps) {
        if (!(start > end) || !(end > 0)
                || steps < 2 || step < 0 || step >= steps) {
            throw new IllegalArgumentException("Invalid schedule");
        }
        double fraction = (double) step / (steps - 1);
        return switch (schedule) {
            case GEOMETRIC -> start
                    * Math.exp(Math.log(end / start) * fraction);
            case LINEAR -> start + (end - start) * fraction;
        };
    }

    record Result(
            long initialCost, long finalCost, long bestCost,
            int accepted, int uphillProposed, int uphillAccepted,
            int bestImprovements, int[] bestTour) {}

    static Result anneal(
            Point[] points, int[] initialTour,
            Schedule schedule, double start, double end,
            int steps, SplittableRandom rng) {
        Objects.requireNonNull(rng);
        validate(points, initialTour);
        int[] current = initialTour.clone();
        int[] best = current.clone();
        long currentCost = cost(points, current);
        long initialCost = currentCost, bestCost = currentCost;
        int accepted = 0, uphillProposed = 0;
        int uphillAccepted = 0, bestImprovements = 0;
        int n = current.length;

        for (int step = 0; step < steps; step++) {
            double temp = temperature(
                    schedule, start, end, step, steps);
            int i = 1 + rng.nextInt(n - 1);
            int j = 1 + rng.nextInt(n - 2);
            if (j >= i) j++; // choose a distinct index uniformly
            swap(current, i, j);
            long candidateCost = cost(points, current);
            long delta = candidateCost - currentCost;
            if (delta > 0) uphillProposed++;

            boolean take = delta <= 0
                    || rng.nextDouble()
                    < Math.exp(-((double) delta) / temp);
            if (take) {
                accepted++;
                if (delta > 0) uphillAccepted++;
                currentCost = candidateCost;
                if (currentCost < bestCost) {
                    bestCost = currentCost;
                    best = current.clone();
                    bestImprovements++;
                }
            } else {
                swap(current, i, j); // roll back rejected move
            }
        }

        validate(points, best);
        validate(points, current);
        if (cost(points, current) != currentCost
                || cost(points, best) != bestCost
                || bestCost > currentCost
                || bestCost > initialCost) {
            throw new AssertionError("Broken annealing invariant");
        }
        return new Result(
                initialCost, currentCost, bestCost,
                accepted, uphillProposed, uphillAccepted,
                bestImprovements, best);
    }

    record Exact(long optimum, long tourCount) {}
    static class ExactState {
        long minimum = Long.MAX_VALUE;
        long count;
    }

    // Independent exhaustive oracle, fixing city 0 as the start.
    static void enumerate(
            Point[] points, boolean[] used,
            int last, int depth, long prefix,
            ExactState state) {
        if (depth == points.length) {
            state.count++;
            long closed = prefix
                    + distance(points[last], points[0]);
            state.minimum = Math.min(state.minimum, closed);
            return;
        }
        for (int next = 1; next < points.length; next++) {
            if (!used[next]) {
                used[next] = true;
                enumerate(points, used, next, depth + 1,
                        prefix + distance(points[last],
                                points[next]), state);
                used[next] = false;
            }
        }
    }

    static Exact exactOptimum(Point[] points) {
        ExactState state = new ExactState();
        boolean[] used = new boolean[points.length];
        used[0] = true;
        enumerate(points, used, 0, 1, 0L, state);
        return new Exact(state.minimum, state.count);
    }

    static long independentCost(Point[] points, int[] tour) {
        long[][] distanceTable = new long[points.length][points.length];
        for (int i = 0; i < points.length; i++) {
            for (int j = 0; j < points.length; j++) {
                distanceTable[i][j] = distance(points[i], points[j]);
            }
        }
        long total = distanceTable[tour[tour.length - 1]][tour[0]];
        for (int i = 1; i < tour.length; i++) {
            total += distanceTable[tour[i - 1]][tour[i]];
        }
        return total;
    }

    static void selfTest(
            Point[] points, double start, double end, int steps,
            Exact exact) {
        Point[] square = {
                new Point(0, 0), new Point(2, 0),
                new Point(2, 2), new Point(0, 2)
        };
        if (cost(square, new int[] {0, 1, 2, 3}) != 8
                || cost(square, new int[] {0, 2, 1, 3}) != 12) {
            throw new AssertionError("Hand-calculated route cost");
        }

        for (Schedule schedule : Schedule.values()) {
            double previous = Double.POSITIVE_INFINITY;
            for (int t = 0; t < steps; t++) {
                double temp = temperature(
                        schedule, start, end, t, steps);
                if (!(temp > 0) || temp > previous + 1e-10) {
                    throw new AssertionError("Cooling not monotone");
                }
                if (t == 0 && Math.abs(temp - start) > 1e-9
                        || t == steps - 1
                        && Math.abs(temp - end) > 1e-9) {
                    throw new AssertionError("Cooling endpoint mismatch");
                }
                previous = temp;
            }
        }
        if (!(Math.exp(-8.0 / end)
                < Math.exp(-8.0 / start))
                || Math.abs(
                        Math.exp(-8.0
                                / initialTemperature(8, 0.8))
                                - 0.8) > 1e-12) {
            throw new AssertionError("Metropolis probability");
        }

        SplittableRandom rng = new SplittableRandom(51777);
        for (int t = 0; t < 1000; t++) {
            int[] tour = randomTour(points.length, rng);
            validate(points, tour);
            if (cost(points, tour) != independentCost(points, tour)) {
                throw new AssertionError("Route cost discrepancy");
            }
        }

        if (exact.tourCount() != 40320) {
            throw new AssertionError("Oracle did not enumerate 8!");
        }
        for (int t = 0; t < 60; t++) {
            int[] tour = randomTour(points.length, rng);
            for (Schedule schedule : Schedule.values()) {
                Result result = anneal(points, tour, schedule,
                        start, end, steps,
                        new SplittableRandom(10000L + t));
                if (result.bestCost() < exact.optimum()
                        || result.bestCost() > result.initialCost()
                        || result.uphillAccepted()
                        > result.uphillProposed()) {
                    throw new AssertionError(
                            "Optimization or counter inconsistency");
                }
            }
        }
        System.out.println(
                "QA: PASS (40320 exact tours, 1000 route checks, "
                + "120 annealing runs)");
    }

    static void show(String name, Result result, long optimum,
                     int steps) {
        System.out.println(name + ": initial="
                + result.initialCost() + ", final="
                + result.finalCost() + ", best="
                + result.bestCost() + ", gap="
                + (result.bestCost() - optimum)
                + ", accepted=" + result.accepted() + "/" + steps
                + ", uphill=" + result.uphillAccepted()
                + "/" + result.uphillProposed());
        System.out.println(name + " best route: "
                + Arrays.toString(result.bestTour()));
    }

    public static void main(String[] args) {
        int steps = 2000;
        double targetAcceptance = 0.8;
        double start = initialTemperature(8, targetAcceptance);
        double end = 0.1;
        Exact exact = exactOptimum(CITIES);
        int[] startTour = randomTour(
                CITIES.length, new SplittableRandom(20261110L));
        System.out.println(
                "TSP: cities=" + CITIES.length
                + ", exactOptimum=" + exact.optimum()
                + ", exactTours=" + exact.tourCount());
        System.out.println("Initial route: "
                + Arrays.toString(startTour)
                + ", cost=" + cost(CITIES, startTour));
        System.out.printf(Locale.ROOT,
                "Calibration: uphillDelta=8, target=0.8, T0=%.3f, "
                + "Tmin=%.1f, steps=%d%n", start, end, steps);
        System.out.printf(Locale.ROOT,
                "Schedule midpoint temperatures: "
                + "geometric=%.3f, linear=%.3f%n",
                temperature(Schedule.GEOMETRIC,
                        start, end, steps / 2, steps),
                temperature(Schedule.LINEAR,
                        start, end, steps / 2, steps));

        Result geometric = anneal(
                CITIES, startTour, Schedule.GEOMETRIC,
                start, end, steps,
                new SplittableRandom(77231));
        Result linear = anneal(
                CITIES, startTour, Schedule.LINEAR,
                start, end, steps,
                new SplittableRandom(77231));
        show("GEOMETRIC", geometric, exact.optimum(), steps);
        show("LINEAR", linear, exact.optimum(), steps);

        Result repeat = anneal(
                CITIES, startTour, Schedule.GEOMETRIC,
                start, end, steps,
                new SplittableRandom(77231));
        boolean reproducible =
                repeat.bestCost() == geometric.bestCost()
                && repeat.finalCost() == geometric.finalCost()
                && repeat.accepted() == geometric.accepted()
                && Arrays.equals(repeat.bestTour(),
                        geometric.bestTour());
        System.out.println("Same-seed reproducible: " + reproducible);
        if (!reproducible) {
            throw new AssertionError("Seed reproducibility");
        }
        selfTest(CITIES, start, end, steps, exact);
    }
}
```

### 11.1. Biên dịch và chạy

Với JDK 17 trở lên:

```bash
javac SimulatedAnnealingCoolingDemo.java
java SimulatedAnnealingCoolingDemo
```

**Stdout chính xác với seed trong chương trình:**

```text
TSP: cities=9, exactOptimum=44, exactTours=40320
Initial route: [0, 5, 8, 3, 6, 2, 1, 7, 4], cost=78
Calibration: uphillDelta=8, target=0.8, T0=35.851, Tmin=0.1, steps=2000
Schedule midpoint temperatures: geometric=1.891, linear=17.967
GEOMETRIC: initial=78, final=44, best=44, gap=0, accepted=698/2000, uphill=270/1572
GEOMETRIC best route: [0, 7, 8, 1, 2, 3, 4, 5, 6]
LINEAR: initial=78, final=44, best=44, gap=0, accepted=1502/2000, uphill=589/1087
LINEAR best route: [0, 1, 8, 2, 3, 4, 5, 6, 7]
Same-seed reproducible: true
QA: PASS (40320 exact tours, 1000 route checks, 120 annealing runs)
```

### 11.2. Giải thích kết quả

**`exactOptimum=44`:** Oracle độc lập liệt kê đủ 40.320 thứ tự thăm còn lại sau khi cố định thành phố 0, tính tour có cạnh trở về 0 và tìm chi phí tối thiểu **44**. Sự đảo chiều một tour có thể tạo biểu diễn khác cùng chi phí, nhưng không làm sai việc tìm cực tiểu.

**`Initial...cost=78`:** Tour khởi tạo ngẫu nhiên được dùng chung cho cả hai lịch, nên so sánh hai lịch có cùng trạng thái ban đầu và cùng 2.000 move. Tuy nhiên, kết quả vẫn phụ thuộc vào seed và đặc tính instance, nên một lần so không đủ để chọn lịch tối ưu.

**`T0=35.851`:** Dựa trên giả thiết move tăng điển hình 8 và xác suất mục tiêu 0.8. Đây là **calibration cho một delta**, không phải tỷ lệ nhận move thực tế toàn bộ thời gian.

**`midpoint`:** Geometric ở giữa còn khoảng 1.891, linear còn khoảng 17.967. Vì vậy lịch linear có xu hướng chấp nhận nhiều move tăng chi phí ở giai đoạn giữa hơn khi các điều kiện khác tương đương.

**`GEOMETRIC`:** Nhận 698 trên 2.000 đề xuất, trong đó 270 move tăng chi phí được nhận trong 1.572 move tăng chi phí đã được đề xuất. Tour cuối cũng là best, chi phí 44; **gap=0 được biết là thật chỉ vì có oracle**.

**`LINEAR`:** Nhận 1.502 trên 2.000 đề xuất, trong đó 589 move tăng chi phí được nhận trong 1.087 move tăng chi phí đề xuất. Best có chi phí 44; tour tương đương tối ưu nhưng thứ tự khác. Lịch linear có tỷ lệ nhận cao hơn trong **lần chạy cụ thể này**, không chứng minh nó luôn tốt hơn cho mọi dữ liệu hoặc mọi ngân sách.

**`Same-seed reproducible=true`:** Với cùng tour ban đầu, cùng lịch, cùng số bước và cùng seed PRNG, kết quả đã xác minh khớp nhau. Mục đích của seed cố định là **debug và kiểm thử**, không tạo chứng minh xác suất hoặc bảo mật.

**`QA PASS`:** Chi phí route hình vuông kiểm tra bằng tay (8 và 12), hai lịch đều dương, giảm đơn điệu và khớp endpoints, công thức calibration khớp `exp(-8/T0)=0.8`; 1.000 tour được so hai cách tính cost; 120 lượt annealing được kiểm tra giá trị best nằm giữa optimum và initial, witness hợp lệ, thống kê uphill nhất quán. Không có phép kiểm thử nào được dùng để tuyên bố **mọi lần chạy** đều có gap=0.

## 12. Phân tích độ phức tạp

Gọi n là số thành phố, N là số move SA được đề xuất.

Trong **chương trình minh họa**:

| Phần | Thời gian | Bộ nhớ |
| --- | --- | --- |
| Sinh tour khởi tạo | `O(n)` Fisher–Yates | `O(n)` |
| Đề xuất swap hai vị trí | `O(1)` | `O(1)` |
| Tính lại chi phí một tour | `O(n)` | `O(1)` |
| Một vòng Metropolis | `O(n)` do tính lại E | `O(1)`, trừ bản sao best khi cải thiện |
| N bước annealing | `O(N*n)` | `O(n)` giữ current/best |
| Oracle vét cạn | Tăng giai thừa theo n, cỡ `O(n!)` đối với duyệt permutation | `O(n)` stack/đánh dấu |
| Bộ kiểm thử | Tăng theo số trường hợp test; không phải chi phí của bộ giải SA dùng thực tế | Tùy harness |

Chương trình `enumerate` tính tăng dần từng cạnh trong DFS, rồi đóng tour ở lá; số nút của cây hoán vị cùng bậc giai thừa. Nó chỉ dùng để **kiểm chứng n=9**, không phải thành phần cần có của SA đối với n lớn.

Nếu tính **delta của swap bằng những cạnh bị ảnh hưởng**, một move có thể cập nhật chi phí trong `O(1)` đối với TSP với cấu trúc/điều kiện thích hợp, do chỉ vài cạnh thay đổi. Khi đó có thể gần `O(N+n)` cho phần annealing sau khởi tạo, nhưng phải xử lý đúng swap kề nhau và cạnh vòng; không áp cận ấy cho mã đang **tính lại O(n)**.

### 12.1. Tối ưu hóa chất lượng khác giới hạn lý thuyết

SA trong N bước chặn được thời gian theo số move, nhưng **không có tỷ lệ xấp xỉ tổng quát** kiểu “luôn ≤1.1 lần optimum” cho mọi bài toán chỉ nhờ dùng lịch hình học hoặc tuyến tính. Nếu muốn một bảo đảm xấp xỉ đã được chứng minh, cần thuật toán thiết kế cho bài toán cụ thể với định lý phù hợp. Ví dụ `bestCost=44` bằng tối ưu trên instance nhỏ là một quan sát có oracle, **không phải định lý của SA**.

## 13. Chứng minh các bất biến của chương trình

### 13.1. Tính hợp lệ của tour

Tour đầu là một hoán vị có đúng một thành phố 0 ở đầu. Swap hai vị trí trong 1..n−1 giữ nguyên đa tập phần tử và không đụng thành phố 0. Khi move bị từ chối, swap lại trả về tour trước đó. Vì vậy, bằng quy nạp theo số bước, `current` luôn là một tour hợp lệ.

### 13.2. Chi phí hiện tại khớp tour

Khởi tạo `currentCost=cost(current)`. Với move được nhận, `candidateCost` được tính từ tour sau swap rồi gán vào `currentCost`. Với move bị từ chối, mảng được hoàn nguyên và `currentCost` giữ nguyên. Do đó bất biến:

```text
currentCost == cost(current)
```

luôn đúng. Mã kiểm tra lại bất biến khi kết thúc một run.

### 13.3. Best không xấu hơn mọi trạng thái đã nhận

Khởi đầu `best=current` và `bestCost=currentCost`. Khi nhận một trạng thái có chi phí thấp hơn best, mã clone tour vào `best` và cập nhật `bestCost`; nếu không, giữ nguyên best. Vì vậy:

```text
bestCost <= initialCost
bestCost <= finalCost
```

và best là một nghiệm khả thi đã gặp. Điều này **không chứng minh** best là nghiệm tối ưu; chỉ chứng minh thuật toán không quên nghiệm tốt nhất từng thấy.

### 13.4. Lịch nhiệt dương và endpoints

Geometric:

```text
T(0)=T0
T(N-1)=T0*exp(log(Tmin/T0))=Tmin.
```

Với `Tmin<T0`, hàm log của tỷ số âm nên T giảm theo t và luôn dương.

Linear:

```text
T(0)=T0
T(N-1)=T0+(Tmin-T0)=Tmin.
```

Với cùng giả thiết, nhiệt giảm tuyến tính và vẫn dương. Mã kiểm thử **từng bước** tính nhiệt dương, không tăng và gần đúng endpoints tới sai số double.

### 13.5. Vì sao QA không phải chứng minh tối ưu?

Oracle vét cạn trên n=9 cho một **chứng cứ chính xác** rằng chi phí tối ưu của **instance này** là 44. Nó không chứng minh rằng SA trên **instance khác** hoặc seed khác sẽ tìm optimum. Bộ kiểm thử xác minh correctness của thao tác/chi phí và quan sát kết quả mẫu; bảo đảm xác suất hội tụ cần mô hình Markov và lịch làm lạnh riêng, không suy ra từ việc chạy test thành công.

## 14. Lỗi thường gặp và cách phòng tránh

1. Nhầm simulated annealing với một thuật toán tối ưu chính xác luôn tìm optimum.
2. Quên đặt bài toán là minimize hay maximize trước khi tính delta.
3. Dùng dấu `exp(+delta/T)` cho bài toán minimize.
4. Coi move tăng năng lượng là sai và cấm toàn bộ chúng, biến SA thành greedy.
5. Tự động chấp nhận mọi move tăng năng lượng khi T cao mà không dùng xác suất Metropolis.
6. Không kiểm tra T>0 trước khi tính `delta/T`.
7. Đặt Tmin=0 nhưng không định nghĩa rõ hành vi greedy khi nhiệt về 0.
8. Giữ `current` mà không lưu `best`, làm mất nghiệm tốt đã gặp.
9. Quên clone mảng best, khiến sửa current làm đổi cả best.
10. Quên rollback swap khi từ chối move.
11. Cập nhật `currentCost` dù move đã bị từ chối.
12. Tính delta dựa trên chi phí cũ không khớp tour sau swap.
13. Dùng neighbor có thể làm lặp hoặc mất thành phố.
14. Cho phép swap vị trí 0 nhưng vẫn giả định thành phố 0 luôn cố định.
15. Dùng `rng.nextInt(0)` khi số vị trí hoán đổi không đủ.
16. Không bảo đảm có thể đi giữa các thành phần của không gian nghiệm bằng neighborhood đã chọn.
17. Suy phân phối Gibbs từ proposal không đối xứng mà không kiểm tra điều kiện.
18. Đánh đồng T với xác suất chấp nhận; T là tham số scale của delta.
19. Dùng T0 từ bài khác trong khi đơn vị/scale chi phí khác.
20. Gọi `p0=0.8` là tỷ lệ nhận tổng thể 80% ở mọi bước.
21. Giảm nhiệt mỗi move nhưng báo alpha như lịch giảm mỗi batch 100 move.
22. Chọn alpha mà không quan tâm số bước N và Tmin thực tế.
23. Dùng lịch tuyến tính cho T âm khi chạy quá số bước thiết kế.
24. Coi lịch log bất kỳ có bảo đảm optimum sau hữu hạn lần thử.
25. Coi geometric luôn tốt hơn linear hoặc ngược lại trên mọi bài toán.
26. Đánh giá lịch chỉ bằng một seed và một instance.
27. So hai lịch với số đề xuất move khác nhau rồi quy nguyên kết quả cho lịch.
28. So kết quả final thay vì best-so-far trong bài minimize khi cho phép move xấu.
29. Coi tỷ lệ accepted/N bằng tỷ lệ uphill accepted/uphill proposed.
30. Quên cộng cạnh cuối về điểm đầu trong TSP.
31. So sánh distance của đường Manhattan với oracle Euclidean và cho rằng kết quả sai.
32. Tính khoảng cách với phép trừ int có thể tràn khi tọa độ cực trị.
33. Tối ưu delta O(1) cho swap nhưng không xử lý các cạnh bị đếm trùng/kề nhau.
34. Coi một chương trình seeded tái lập được là bằng chứng thuật toán luôn tìm optimum.
35. Coi 40.320 tour của n=9 có thể vét cạn dễ dàng khi n tăng rất lớn.
36. Đánh đồng một lần chạy có gap=0 với tỷ lệ xấp xỉ được chứng minh.
37. Nhầm lỗi timeout/cutoff với kết luận không tồn tại nghiệm tốt.
38. Đo sai số chi phí nhưng không kiểm tra nghiệm vẫn khả thi.
39. Không thử các tour đơn giản có đáp án tính tay.
40. Không kiểm tra lịch dương và khớp T0/Tmin ở hai đầu.
41. Chỉ nhìn chất lượng cuối mà không theo dõi số move xấu được nhận.
42. Dùng `Math.random` không kiểm soát seed trong QA rồi không tái lập được lỗi.
43. Không thử nhiều khởi tạo khi bài có nhiều cực tiểu cục bộ.
44. Coi nghiệm SA là cận dưới của optimum trong bài minimization; nó là **cận trên khả thi**.
45. Hứa hẹn hội tụ lý thuyết nhưng không nêu tính liên thông, tính chất Markov và tốc độ giảm nhiệt.

## 15. Bài tập tự luyện có đáp án

**Bài 1.** SA giải loại bài toán nào?

**Đáp án:** Là một metaheuristic tìm nghiệm tốt cho bài toán tối ưu trên không gian trạng thái có neighborhood; không có bảo đảm tìm optimum hữu hạn cho mọi bài toán.

**Bài 2.** Đối với minimize, định nghĩa delta?

**Đáp án:** `delta=E(candidate)-E(current)`.

**Bài 3.** Nếu delta=-3, xác suất nhận move bằng bao nhiêu?

**Đáp án:** 1, vì move cải thiện chi phí.

**Bài 4.** Nếu delta=0, theo quy tắc đang dùng thì sao?

**Đáp án:** Chấp nhận chắc chắn.

**Bài 5.** Nếu delta=4 và T=2, xác suất nhận?

**Đáp án:** `exp(-2)≈0.135335`.

**Bài 6.** Nếu delta=4 và T=8?

**Đáp án:** `exp(-0.5)≈0.606531`.

**Bài 7.** Cùng delta dương, khi T giảm thì xác suất chấp nhận đổi thế nào?

**Đáp án:** Giảm; SA dần ưu tiên khai thác hơn khám phá.

**Bài 8.** Vì sao SA có thể chấp nhận move xấu?

**Đáp án:** Để vượt rào cản năng lượng và thoát khỏi một số cực tiểu cục bộ, dù không bảo đảm thành công.

**Bài 9.** Khi finalCost=60 nhưng từng có bestCost=50, nên trả gì?

**Đáp án:** Trả nghiệm bestCost=50 nếu mục tiêu là tìm tour tốt nhất.

**Bài 10.** Nếu current là mảng và best=current (không clone), nguy cơ?

**Đáp án:** Các swap trên current cũng sửa best, mất nghiệm tốt nhất.

**Bài 11.** Nếu move swap bị từ chối, cần làm gì?

**Đáp án:** Swap lại hai vị trí để khôi phục trạng thái và giữ currentCost cũ.

**Bài 12.** Với delta0=8 và p0=0.8, tính T0?

**Đáp án:** `T0=-8/ln(0.8)≈35.851`.

**Bài 13.** T0 ở bài 12 bảo đảm nhận 80% **mọi move** không?

**Đáp án:** Không; chỉ bảo đảm p=0.8 đối với move tăng đúng delta0=8 tại T0, trong mô hình rút ngẫu nhiên đồng đều.

**Bài 14.** Viết lịch hình học từ T0, Tmin, N.

**Đáp án:** `T(t)=T0*(Tmin/T0)^(t/(N-1))`, với `t=0..N−1`, `N>=2`.

**Bài 15.** Viết lịch tuyến tính từ T0, Tmin, N.

**Đáp án:** `T(t)=T0+(Tmin−T0)*t/(N−1)`.

**Bài 16.** T0=100, Tmin=1, N=5, nhiệt geometric ở t=2?

**Đáp án:** 10.

**Bài 17.** Cùng ví dụ, nhiệt linear ở t=2?

**Đáp án:** 50.5.

**Bài 18.** Với geometric, tính alpha từ endpoints?

**Đáp án:** `alpha=(Tmin/T0)^(1/(N−1))`.

**Bài 19.** Nếu `alpha=0.99` nhưng tăng N lên rất nhiều, chuyện gì xảy ra?

**Đáp án:** Nhiệt có thể giảm xuống gần 0 quá sớm; cần thiết kế lại alpha theo N và Tmin.

**Bài 20.** Lịch `c/log(t+t0)` có chắc đạt optimum sau 2.000 bước?

**Đáp án:** Không; các kết quả hội tụ liên quan tới vô hạn thời gian và điều kiện kỹ thuật, không phải deadline hữu hạn.

**Bài 21.** Vì sao cần neighborhood liên thông?

**Đáp án:** Nếu một nghiệm tốt nằm ở thành phần không thể tới bằng move, tăng nhiệt cũng không giúp SA đi tới đó.

**Bài 22.** TSP 9 thành phố, cố định thành phố 0, có bao nhiêu thứ tự thăm còn lại?

**Đáp án:** `8!=40320` (gồm các hướng đảo tương đương về chi phí trong metric đối xứng).

**Bài 23.** Tour Manhattan hình vuông cạnh 2 theo thứ tự quanh biên có cost?

**Đáp án:** 8.

**Bài 24.** Tour `[0,2,1,3]` của hình vuông mẫu có cost?

**Đáp án:** 12.

**Bài 25.** Nếu tour ban đầu cost78, best44, oracle optimum44, gap?

**Đáp án:** `best-optimum=0`; chỉ instance đã có oracle mới xác nhận gap thật.

**Bài 26.** Khi `accepted=698/2000`, đó có phải xác suất sai 34.9%?

**Đáp án:** Không; đó là tỷ lệ move được nhận trong một lần chạy, không liên quan trực tiếp đến lỗi thuật toán.

**Bài 27.** `uphill=270/1572` đo điều gì?

**Đáp án:** Tỷ lệ các move tăng chi phí được chấp nhận trong số move tăng chi phí đã đề xuất của run đó.

**Bài 28.** Nếu linear giữ T cao ở giữa, nó luôn có best tốt hơn geometric không?

**Đáp án:** Không; phụ thuộc cảnh quan năng lượng, neighborhood, seed và ngân sách.

**Bài 29.** Độ phức tạp của N bước SA khi tính lại toàn tour O(n) sau mỗi move?

**Đáp án:** `O(N*n)` thời gian, `O(n)` bộ nhớ cho current/best.

**Bài 30.** Một run SA tìm optimum có chứng minh tỷ lệ xấp xỉ hữu hạn cho mọi input không?

**Đáp án:** Không; cần định lý riêng cho bài toán/thuật toán và phạm vi input.

**Bài 31.** Nếu proposal không đối xứng, có thể tự động viện dẫn detailed balance của quy tắc Metropolis đơn giản không?

**Đáp án:** Không; có thể cần tỷ số proposal kiểu Metropolis–Hastings và các giả thiết chuỗi Markov thích hợp.

**Bài 32.** Độ dài tour Manhattan có bắt buộc là số thực không?

**Đáp án:** Không; với tọa độ nguyên nhỏ, từng khoảng cách và tổng có thể tính chính xác bằng long.

**Bài 33.** Vì sao phải giữ `Tmin>0` trong lịch của mã?

**Đáp án:** Để công thức `exp(-delta/T)` không có phép chia cho 0 và bảo đảm nhiệt dương.

**Bài 34.** Nếu muốn dùng 2-opt thay swap, cần thay gì?

**Đáp án:** Thay bộ sinh neighborhood và logic áp/revert move; nếu tối ưu delta, cần công thức cập nhật đúng cho 2-opt.

**Bài 35.** Nêu hai mục tiêu độc lập khi kiểm thử SA.

**Đáp án:** Xác minh **tính đúng trạng thái/chi phí/lịch nhiệt**, và đánh giá **chất lượng nghiệm trên nhiều seed/instance**; không suy chất lượng tổng quát chỉ từ một run.

## 16. Checklist trước khi áp dụng SA

- [ ] Hàm mục tiêu đang minimize hay maximize đã được quy đổi nhất quán?
- [ ] Mọi trạng thái và láng giềng có hợp lệ không?
- [ ] Neighborhood có thể tới những vùng nghiệm cần thiết không?
- [ ] Đề xuất neighbor có đối xứng nếu dùng diễn giải Metropolis/Gibbs không?
- [ ] Delta có đúng dấu và sử dụng đơn vị phù hợp với T không?
- [ ] T>0, T0>Tmin, N≥2 và endpoints của lịch đúng không?
- [ ] T0 đã được hiệu chỉnh theo mức tăng chi phí điển hình chưa?
- [ ] Đã thống nhất giảm nhiệt mỗi move hay mỗi batch?
- [ ] Move bị từ chối có rollback dữ liệu và giữ nguyên currentCost?
- [ ] `best` được clone và cập nhật riêng current?
- [ ] Cost có tính đúng cạnh đóng vòng/đủ ràng buộc bài toán?
- [ ] Có test hand-calculated và test oracle cho instance nhỏ?
- [ ] Có đo accepted, uphill acceptance, best vs final và nhiệt theo bước?
- [ ] Đã dùng cùng ngân sách N khi so các lịch?
- [ ] Có thử nhiều seed và nhiều instance nếu cần khuyến nghị lịch?
- [ ] Có tách riêng quan sát thực nghiệm khỏi bảo đảm tối ưu/xấp xỉ?
- [ ] Đã tính đúng độ phức tạp một move và ngân sách tổng?
- [ ] Nếu dựa vào lý thuyết hội tụ, đã nêu đủ điều kiện về neighborhood, proposal và cooling?

## Kết luận

**Ủ mô phỏng** là một chiến lược tối ưu hóa ngẫu nhiên kết hợp **bước cải thiện chắc chắn được nhận** với **bước xấu đi đôi khi được nhận**:

```text
delta = E(candidate)-E(current)

accept = true                      if delta<=0
accept with probability exp(-delta/T) if delta>0.
```

Lịch **geometric**, **linear** hoặc **logarithmic** quyết định cách T giảm, từ đó ảnh hưởng trực tiếp đến cân bằng khám phá–khai thác. Không có lịch cố định nào tốt nhất cho mọi bài; thông số phải được chọn theo **scale hàm mục tiêu, neighborhood và ngân sách**.

Trong ví dụ TSP 9 thành phố, cả hai lịch đã tìm được cost tối ưu **44** được xác nhận bằng vét cạn 40.320 thứ tự. Đây là một **kết quả kiểm thử trên một instance**, không phải bảo đảm SA luôn tối ưu. Muốn dùng SA đáng tin cậy, hãy giữ best-so-far, kiểm tra tính hợp lệ của move, hiệu chỉnh T theo delta, ghi chẩn đoán, thử nhiều seed và phân biệt rõ **heuristic tìm nghiệm tốt** với **thuật toán có chứng minh tỷ lệ xấp xỉ hoặc tính tối ưu**.
