# Tổng tiền tố cho dữ liệu tĩnh và giới hạn khi cập nhật

**Tổng tiền tố (prefix sum)** là một kỹ thuật tiền xử lý rất mạnh khi có **nhiều truy vấn tổng trên cùng một dãy không thay đổi**. Thay vì cộng lại từng đoạn cho mỗi truy vấn, ta cộng dồn trước một lần rồi trả lời mỗi đoạn bằng **hiệu của hai tổng tiền tố**.

Tuy nhiên, **O(1) cho một truy vấn không có nghĩa O(1) cho mọi thao tác**. Khi một phần tử được sửa, những tiền tố chứa phần tử đó đều đổi; nếu duy trì nguyên một mảng prefix thông thường, ta có thể phải cập nhật **Θ(n)** ô. Đó là ranh giới quan trọng giữa bài toán **tĩnh (static)** và bài toán **động (dynamic)**.

Bài thuộc nhóm **Truy vấn và ngoại tuyến**, làm rõ bốn tình huống:

1. **Không có cập nhật:** xây prefix O(n), truy vấn tổng đoạn O(1).
2. **Có nhiều cập nhật đoạn nhưng chỉ cần kết quả sau cùng:** dùng **mảng hiệu (difference array)**, thêm mỗi đoạn O(1), khôi phục toàn bộ dữ liệu O(n).
3. **Có truy vấn xen kẽ sửa một điểm:** dùng **Fenwick tree / Binary Indexed Tree** hoặc segment tree để hỗ trợ O(log n) mỗi thao tác theo mô hình chuẩn.
4. **Có sửa đoạn và truy vấn tổng đoạn xen kẽ:** cân nhắc lazy segment tree, hai Fenwick tree với biến đổi thích hợp hoặc kỹ thuật khác.

Bài trình bày công thức 1D/2D, chứng minh đúng, cách chọn chỉ số, overflow, snapshot dữ liệu, truy vấn rỗng, mảng có số âm, tính đơn điệu chỉ khi dữ liệu không âm, đánh đổi thời gian–bộ nhớ, ví dụ có đáp án, mã **Java 17+ độc lập**, kiểm thử bằng oracle chậm nhưng dễ kiểm chứng và những lỗi thường gặp.

## 1. Bài toán cơ sở: nhiều tổng đoạn trên một dãy

Cho dãy số nguyên:

**a[0], a[1], ..., a[n−1]**.

Truy vấn hỏi tổng của các phần tử trong đoạn, ví dụ:

**sum(l,r)=a[l]+a[l+1]+...+a[r−1]**.

Bài dùng quy ước **đoạn nửa mở [l,r)**:

**0≤l≤r≤n**.

Đoạn này có **r−l phần tử**. Khi l=r, tổng đoạn rỗng bằng 0.

Ví dụ:

~~~text
a = [3, -2, 5, 7, 0, -4]
n = 6

sum[1,5) = -2 + 5 + 7 + 0 = 10
sum[2,5) = 5 + 7 + 0 = 12
sum[0,6) = 3 - 2 + 5 + 7 + 0 - 4 = 9
sum[3,3) = 0
~~~

Nếu mỗi truy vấn dùng vòng lặp từ l đến r−1 thì chi phí **O(r−l)**, trường hợp xấu **O(n)**. Với q truy vấn có thể mất **O(qn)** thời gian.

Nếu dữ liệu **không cập nhật**, ta có thể tiền xử lý một mảng prefix rồi giảm mỗi truy vấn thành **O(1)**.

## 2. Định nghĩa tổng tiền tố với phần tử 0 giả

Cách cài đặt ít lỗi nhất thường là một mảng **P có n+1 phần tử**:

**P[0]=0**.

**P[i+1]=P[i]+a[i]**, với **0≤i<n**.

Ý nghĩa:

**P[k]=tổng của k phần tử đầu tiên**, tức **a[0]+...+a[k−1]**.

Mảng mẫu:

~~~text
Index i:       0   1   2   3   4   5
a[i]:          3  -2   5   7   0  -4

Index k:   0   1   2   3   4   5   6
P[k]:      0   3   1   6  13  13   9
~~~

Từ định nghĩa, tổng đoạn [l,r) là:

**sum(l,r)=P[r]−P[l]**.

Ví dụ:

- [1,5): P[5]−P[1]=13−3=**10**.
- [2,5): P[5]−P[2]=13−1=**12**.
- [0,6): P[6]−P[0]=9−0=**9**.
- [3,3): P[3]−P[3]=**0**.

### Vì sao có P[0]=0?

Phần tử 0 giả là **tổng của đoạn rỗng đầu dãy**. Nhờ nó, đoạn bắt đầu từ vị trí 0 cũng dùng đúng công thức, không cần một nhánh xử lý đặc biệt.

Cách này tương thích tốt với Java vì array index bắt đầu từ 0 trong khi số phần tử đầu dãy có thể biểu diễn bằng chỉ số k của P.

## 3. Chứng minh công thức đoạn bằng phép triệt tiêu

Ta viết:

**P[r]=a[0]+...+a[l−1]+a[l]+...+a[r−1]**.

Trong khi:

**P[l]=a[0]+...+a[l−1]**.

Trừ hai vế:

**P[r]−P[l]=a[l]+...+a[r−1]**.

Đây chính là tổng đoạn [l,r).

Khi l=r, hai tổng giống nhau nên hiệu bằng 0. Khi l=0, P[0]=0 nên công thức vẫn đúng.

### Bất biến xây dựng prefix

Sau khi tính xong P[i], giá trị đó phải là tổng của **đúng i phần tử đầu**.

Cơ sở: P[0]=0 là tổng của 0 phần tử.

Bước quy nạp: giả sử P[i] là tổng i phần tử đầu; cộng a[i] tạo P[i+1], tổng i+1 phần tử đầu.

Suy ra mọi P[k] đúng; công thức đoạn theo phép triệt tiêu cũng đúng.

**Điều kiện thiết yếu:** dữ liệu a mà P đại diện **không bị thay đổi giữa lúc xây dựng và lúc truy vấn**, hoặc P phải được cập nhật đồng bộ theo các thay đổi đó.

## 4. Đoạn đóng [l,r] và đoạn nửa mở [l,r)

Hai kiểu chỉ số đều thường xuất hiện trong đề bài:

**Nửa mở [l,r):** gồm l,l+1,...,r−1.

**Đóng [l,r]:** gồm l,l+1,...,r.

Với mảng P kiểu n+1 của bài:

**sumHalfOpen(l,r)=P[r]−P[l]**, 0≤l≤r≤n.

**sumInclusive(l,r)=P[r+1]−P[l]**, 0≤l≤r<n.

Ví dụ:

- [2,4] có phần tử tại chỉ số 2,3,4.
- Tổng =5+7+0=12.
- Viết theo nửa mở thành **[2,5)**.

### Các lỗi off-by-one

- Dùng P[r]−P[l] cho yêu cầu **[l,r]** sẽ bỏ a[r].
- Dùng P[r+1]−P[l] cho yêu cầu **[l,r)** sẽ cộng thừa a[r] (và có thể vượt n).
- Khi r=n−1, truy vấn đóng cần P[n], hoàn toàn hợp lệ vì P có n+1 ô.
- Với đoạn nửa mở [n,n), tổng rỗng bằng 0; với đoạn đóng [n,n], chỉ số phần tử là không hợp lệ.

**Nên chuẩn hóa tất cả API nội bộ về [l,r)**, và chỉ chuyển đổi tại nơi nhận đề bài nếu cần.

## 5. Độ phức tạp của mảng tổng tiền tố tĩnh

Giả sử n phần tử và q truy vấn:

| Cách giải | Tiền xử lý | Một truy vấn [l,r) | Bộ nhớ phụ | Tổng với q truy vấn |
| --- | ---: | ---: | ---: | ---: |
| Cộng trực tiếp | O(1) | O(r−l), xấu nhất O(n) | O(1) | O(qn) xấu nhất |
| Prefix sum | **O(n)** | **O(1)** | **O(n)** | **O(n+q)** |

Phép tính P[i+1]=P[i]+a[i] chạy một vòng n bước. Mỗi truy vấn chỉ cần hai lần đọc P và một phép trừ.

### O(1) phụ thuộc mô hình số học

Nếu lưu tổng bằng **long** và các phép cộng/trừ long được coi là O(1) trên word-RAM, công thức có chi phí O(1).

Nếu giá trị là số nguyên tùy ý có hàng triệu bit, các phép BigInteger.add/subtract có chi phí theo **độ dài bit**, nên không được nói O(1) tuyệt đối mà không nêu mô hình.

### Chi phí thiết lập có đáng không?

Với chỉ một truy vấn đoạn dài 3 phần tử, cộng trực tiếp thường đơn giản hơn xây O(n) prefix. Prefix đặc biệt phù hợp khi **nhiều lần hỏi tổng đoạn khác nhau trên cùng dữ liệu tĩnh**.

## 6. Tại sao số âm không làm sai prefix sum?

Prefix sum dùng **tính kết hợp của phép cộng** và phép trừ để loại đoạn đầu. Nó **không yêu cầu a[i]≥0**.

Ví dụ:

~~~text
a = [3, -2, 5, 7, 0, -4]
P = [0, 3, 1, 6, 13, 13, 9]
~~~

P không đơn điệu: từ 3 xuống 1, rồi từ 13 xuống 9. Nhưng mọi truy vấn P[r]−P[l] vẫn đúng.

**Phân biệt hai ý:**

- **Tính đúng của tổng đoạn:** hoạt động với số âm và số dương.
- **Dùng binary search trên P:** chỉ phù hợp khi đã có giả thiết về **tính đơn điệu** của P, ví dụ mọi a[i] không âm.

Không được suy từ việc prefix sum luôn tính đúng tổng mà kết luận có thể áp dụng lower_bound trên prefix của bất kỳ mảng số âm.

## 7. Overflow: dùng long khi phần tử là int

Nếu phần tử là int 32-bit, tổng nhiều phần tử có thể vượt miền **Integer.MIN_VALUE..Integer.MAX_VALUE**.

Ví dụ:

**a=[2_000_000_000,2_000_000_000]**.

Tổng toán học là:

**4_000_000_000**, vượt Integer.MAX_VALUE.

Nếu dùng mảng prefix int, phép cộng tràn có thể làm giá trị đổi dấu. Dù một số phép trừ modulo 2³² có trường hợp tình cờ cho phần dư đúng, nó không đáp ứng hợp đồng tính tổng nguyên chính xác.

### Quy tắc Java

Dùng:

~~~java
long[] prefix = new long[n + 1];

for (int i = 0; i < n; i++) {
    prefix[i + 1] = prefix[i] + (long) a[i];
}
~~~

Nếu chỉ chứa n phần tử int và mảng Java có kích thước hợp lệ, tổng của n giá trị int nằm trong miền long cho các kích thước khả thi; còn các bài có giá trị ban đầu dạng long hoặc thực hiện nhiều cập nhật long lớn vẫn có thể tràn long.

Khi cần bảo đảm số nguyên không giới hạn, cân nhắc **BigInteger**, đồng thời ghi rõ chi phí phép toán theo bit.

### Tràn trước khi ép kiểu

Sai:

~~~java
long sum = a[i] + a[j];
~~~

Hai toán hạng int được cộng ở kiểu int **trước**, sau đó mới chuyển kết quả (có thể đã tràn) sang long.

Đúng:

~~~java
long sum = (long) a[i] + a[j];
~~~

Trong code prefix, biểu thức prefix[i]+a[i] đã có toán hạng prefix[i] kiểu long, nên Java tự nâng phần tử int lên long trước phép cộng.

## 8. Prefix sum là một snapshot, không phải view tự động cập nhật

Giả sử ta xây:

~~~text
a = [3, -2, 5, 7, 0, -4]
P = [0, 3, 1, 6, 13, 13, 9]
~~~

Rồi sửa a[2] từ 5 thành 10.

Dữ liệu mới:

~~~text
a' = [3, -2, 10, 7, 0, -4]
~~~

Đoạn [1,5) mới có tổng:

**−2+10+7+0=15**.

Nhưng P cũ vẫn cho:

**P[5]−P[1]=13−3=10**.

Đây không phải lỗi công thức. **P là tiền tố của một phiên bản dữ liệu khác**.

### Thiết kế an toàn

Có hai kiểu giao diện:

- **Snapshot immutable:** đối tượng prefix được tạo từ dữ liệu gốc và không tự thay đổi. Khi dữ liệu cập nhật, tạo đối tượng mới.
- **Mutable index:** chủ động duy trì cấu trúc dữ liệu mỗi khi thay đổi, chẳng hạn Fenwick tree hoặc segment tree.

Không nên xây P rồi để mã bên ngoài thay đổi a và vẫn tuyên bố P phản ánh trạng thái mới.

## 9. Một cập nhật điểm ảnh hưởng những tiền tố nào?

Giả sử a[p] tăng thêm Δ:

**a'[p]=a[p]+Δ**.

Với k≤p, tổng của k phần tử đầu không chứa a[p], nên:

**P'[k]=P[k]**.

Với k≥p+1, tổng tiền tố có chứa a[p], nên:

**P'[k]=P[k]+Δ**.

Vậy **toàn bộ các ô P[p+1],...,P[n]** phải đổi.

Số ô chịu ảnh hưởng:

**n−p**.

Nếu p=0, có n ô cần thay. Nếu p=n−1, chỉ cần đổi P[n].

### Hệ quả chi phí

- **Một cập nhật điểm p với mảng prefix thuần túy:** O(n−p), xấu nhất Θ(n).
- **Một truy vấn đoạn sau khi đã cập nhật toàn bộ P đúng:** O(1).
- **Xây lại nguyên P từ a:** O(n), dễ triển khai nhưng có thể làm nhiều việc không cần thiết so với cập nhật suffix.

**Đánh đổi:** prefix sum cố định ưu tiên truy vấn, không ưu tiên sửa đổi xen kẽ.

### Khi nào O(n) cập nhật vẫn chấp nhận được?

Nếu dữ liệu được sửa hiếm, ví dụ một lần mỗi ngày nhưng cần phục vụ hàng triệu truy vấn giữa hai lần sửa, xây lại prefix một lần O(n) có thể là kiến trúc hợp lý.

Không phải lúc nào thay bằng cấu trúc động cũng tốt hơn trên thực tế.

## 10. Chi phí khi có q truy vấn và u cập nhật

Với n phần tử, q truy vấn tổng đoạn và u lần cập nhật điểm:

**Cách 1 — Prefix materialized, cập nhật suffix:**

- Xây ban đầu O(n).
- Mỗi update O(n) worst-case.
- Mỗi query O(1).
- Tổng xấu nhất **O(n+un+q)**.

**Cách 2 — Fenwick tree:**

- Xây O(n) bằng thuật toán dựng tuyến tính hoặc O(n log n) bằng cách add từng phần tử.
- Mỗi update điểm O(log n).
- Mỗi query tổng đoạn O(log n).
- Tổng **O(n+(u+q)log n)** với bản build tuyến tính.

**Cách 3 — Cộng trực tiếp sau mỗi sửa:**

- Update a[p] O(1).
- Query tổng đoạn O(n) worst-case.
- Tổng **O(u+qn)**.

Đây là các **cận trên** cho ba cách triển khai, không phải một chứng minh rằng bài toán động bắt buộc có cận dưới Ω(log n) trong mọi mô hình máy.

### Chọn theo tỷ lệ thao tác

Nếu q≫u, prefix có thể rất hấp dẫn. Nếu q và u đều lớn, Fenwick tree thường là lựa chọn đơn giản, hiệu quả. Nếu q rất ít và u cực nhiều, giữ mảng gốc và cộng khi hỏi có thể đủ.

Phân tích còn phụ thuộc mảng có thưa không, số lượng phần tử, cache CPU, giới hạn bộ nhớ và yêu cầu latency.

## 11. Nhiều lần sửa rồi mới hỏi: phân biệt xử lý ngoại tuyến

**Ngoại tuyến (offline)** ở đây nghĩa là **có thể gom các sửa đổi và xử lý thành một đợt**, không nhất thiết phải trả lời mỗi truy vấn ngay khi tới.

Ví dụ người dùng gửi:

~~~text
Ban đầu: [3, -2, 5, 7, 0, -4]

Cộng +3 trên [1,4)
Cộng -2 trên [3,6)
Cộng +1 trên [0,2)

Sau cùng mới hỏi tổng trên [1,5).
~~~

Nếu có thể xử lý mọi range add trước rồi mới query, ta có thể dùng **difference array**, dựng lại một bản dữ liệu cuối cùng, sau đó xây prefix cho bản ấy.

Nếu người dùng hỏi sau **từng cập nhật**, không thể cứ gom hết rồi trả đáp án cuối. Đó là bài toán **online/dynamic queries** và cần chiến lược cập nhật ngay hoặc một cách biểu diễn truy vấn có thể tính đủ nhanh.

### Offline không có nghĩa là bắt buộc chạy chậm

Ngoại tuyến thường giúp **đổi thứ tự/ghép nhóm** các thao tác để giảm chi phí. Nhưng nếu thứ tự các sự kiện có ý nghĩa logic (ví dụ một query cần trạng thái trước một update), không được tự chuyển query qua update và làm sai ngữ nghĩa.

## 12. Mảng hiệu 1D: cập nhật đoạn O(1) khi gom lô

Cho mảng ban đầu a độ dài n. Tạo **D có n+1 phần tử**, ban đầu toàn 0. Một yêu cầu cộng Δ vào mọi phần tử trong đoạn [l,r) được biểu diễn:

**D[l] += Δ**.

**D[r] -= Δ**.

Sau khi gom tất cả cập nhật, duyệt từ trái sang phải:

**running=Σ_{j=0}^i D[j]**.

**result[i]=a[i]+running**.

Như vậy mỗi range add chỉ thay **hai mốc biên**, thay vì chạm tất cả phần tử bên trong đoạn.

### Vì sao có D[n]?

Nếu cập nhật đoạn kết thúc ở r=n, ta cần ghi D[n] để biểu diễn điểm kết thúc ảnh hưởng. Trong quá trình khôi phục result[0..n−1], D[n] không tham gia vào phần tử nào, nhưng giúp công thức biên nhất quán.

Một cách triển khai khác dùng diff dài n và bỏ thao tác D[n] nếu r=n. Bản n+1 trong bài là cách nhất quán và ít nhánh đặc biệt.

### Đoạn rỗng

Nếu l=r, phép cộng một đoạn rỗng phải **không đổi dữ liệu**. Có thể trả ngay; tránh ghi D[l]+=Δ và D[l]−=Δ nếu muốn hạn chế các sự kiện overflow trung gian với Δ cực lớn.

## 13. Chứng minh mảng hiệu đúng

Xét đúng một cập nhật [l,r), giá trị Δ.

Sau thay đổi D:

- Với i<l: tổng D[0..i] không chứa Δ, nên bằng 0.
- Với l≤i<r: tổng chứa +Δ tại l nhưng chưa chứa −Δ tại r, nên bằng Δ.
- Với i≥r: tổng chứa cả +Δ và −Δ, nên bằng 0.

Vì vậy khi khôi phục, đúng các vị trí:

**l,l+1,...,r−1**

được cộng Δ.

Với nhiều cập nhật, phép cộng có tính tuyến tính; ảnh hưởng của mọi update được cộng lại tại từng vị trí. Do đó thuật toán trả đúng mảng sau **tất cả cập nhật đoạn**.

### Giới hạn

Khôi phục cả mảng cần **O(n)**; difference array không làm các truy vấn tổng đoạn **O(1) ở mọi thời điểm giữa các update**.

Nếu cần trả query xen kẽ, có thể phải tính thêm các update chưa materialize, rebuild theo khối hoặc dùng cấu trúc động như lazy segment tree/hai Fenwick tree.

## 14. Ví dụ cập nhật đoạn bằng difference array

Mảng ban đầu:

~~~text
a = [3, -2, 5, 7, 0, -4]
~~~

Áp dụng ba cập nhật, theo đoạn nửa mở:

1. Cộng **+3** vào [1,4): các chỉ số 1,2,3.
2. Cộng **−2** vào [3,6): các chỉ số 3,4,5.
3. Cộng **+1** vào [0,2): các chỉ số 0,1.

Từng bước:

~~~text
Ban đầu:             [ 3, -2,  5,  7,  0, -4]
Sau +3 trên [1,4):  [ 3,  1,  8, 10,  0, -4]
Sau -2 trên [3,6):  [ 3,  1,  8,  8, -2, -6]
Sau +1 trên [0,2):  [ 4,  2,  8,  8, -2, -6]
~~~

Kết quả cuối:

**[4,2,8,8,−2,−6]**.

Nếu xây prefix cho bản mới:

~~~text
P_final = [0, 4, 6, 14, 22, 20, 14]
~~~

Thì:

**sum_final[1,5)=P_final[5]−P_final[1]=20−4=16**.

### Chi phí tổng

Với u cập nhật đoạn và q truy vấn sau cùng:

- Ghi mỗi update vào diff: O(1).
- Khôi phục mảng: O(n).
- Xây prefix trên mảng đã khôi phục: O(n).
- Trả mỗi query: O(1).

Tổng **O(u+n+q)**, bộ nhớ O(n), so với việc cộng trực tiếp từng đoạn có thể tốn O(un).

**Phạm vi:** tất cả query phải hỏi **trạng thái sau cùng**, hoặc được nhóm theo các thời điểm có rebuild phù hợp; không được di chuyển query qua update tùy tiện.

## 15. Dạng mảng hiệu gốc và quan hệ nghịch đảo với prefix

Với một mảng a, ta cũng có thể tạo hiệu của chính dữ liệu:

**d[0]=a[0]**.

**d[i]=a[i]−a[i−1]**, với i≥1.

Khi lấy prefix d:

**a[i]=d[0]+d[1]+...+d[i]**.

Đây là hai biến đổi ngược nhau theo nghĩa:

- **Difference:** biến giá trị theo vị trí thành các thay đổi tại biên.
- **Prefix scan:** tích lũy các thay đổi từ trái sang phải.

Trong bài minh họa, D ban đầu bằng 0 vì nó chỉ lưu **các thay đổi cần cộng thêm vào a**, không phải bản difference representation của a. Phân biệt hai cách dùng D này để tránh cộng dữ liệu gốc hai lần.

### Cập nhật đoạn là hai sự kiện biên

Một range add [l,r) tạo một “sự kiện bật” tại l và “sự kiện tắt” tại r. Việc prefix scan các sự kiện làm lộ ra ảnh hưởng tại từng phần tử.

Cách tư duy này áp dụng rộng hơn cho interval coverage counting, sweep-line đơn giản và nhiều bài query offline.

## 16. Prefix sum 2D cho ma trận tĩnh

Với ma trận **R hàng, C cột** gồm các phần tử a[r][c], định nghĩa P kích thước:

**(R+1)×(C+1)**.

P[i][j] là tổng của hình chữ nhật:

**[0,i)×[0,j)**.

Hàng 0 và cột 0 của P toàn 0.

Công thức xây:

**P[r+1][c+1] = a[r][c] + P[r][c+1] + P[r+1][c] − P[r][c]**.

Có thể hiểu là:

- Tổng vùng bên trên.
- Cộng vùng bên trái.
- Trừ vùng giao bị tính hai lần.
- Cộng ô hiện tại.

### Cách xây khác bằng tổng từng hàng

Với mỗi hàng r, giữ **rowRunning** là tổng của a[r][0..c], rồi:

**P[r+1][c+1]=P[r][c+1]+rowRunning**.

Hai cách tương đương trong số học nguyên chính xác. Cách rowRunning đôi khi rõ hơn trong code và tránh một vài phép cộng/trừ trung gian, nhưng không làm thay đổi chi phí O(RC).

## 17. Truy vấn hình chữ nhật bằng bốn góc

Với hình chữ nhật nửa mở:

**[top,bottom)×[left,right)**,

điều kiện:

**0≤top≤bottom≤R** và **0≤left≤right≤C**.

Tổng hình chữ nhật:

**sumRect = P[bottom][right] − P[top][right] − P[bottom][left] + P[top][left]**.

Công thức inclusion–exclusion:

1. Lấy toàn bộ hình từ gốc đến (bottom,right).
2. Trừ dải bên trên top.
3. Trừ dải bên trái left.
4. Cộng lại vùng trên-trái đã bị trừ hai lần.

### Ví dụ 3×3

~~~text
1 2 3
4 5 6
7 8 9
~~~

Hỏi [0,2)×[1,3):

~~~text
2 + 3
5 + 6 = 16
~~~

Hỏi [1,3)×[0,2):

~~~text
4 + 5
7 + 8 = 24
~~~

Toàn bộ [0,3)×[0,3)=45.

Hình chữ nhật có top=bottom hoặc left=right là rỗng, tổng bằng 0.

### Độ phức tạp

- Xây P: **O(RC)**.
- Truy vấn: **O(1)**.
- Bộ nhớ: **O(RC)**.

Nếu ma trận rất lớn nhưng thưa, cấp phát đủ (R+1)(C+1) ô có thể quá tốn RAM. Khi đó cần đánh giá coordinate compression, sparse structures hoặc truy vấn offline khác.

## 18. Cập nhật trong 2D cũng phá prefix toàn cục

Nếu sửa a[r][c] thêm Δ, mọi P[i][j] với:

**i≥r+1 và j≥c+1**

đều phải cộng Δ.

Đó là một **hình chữ nhật hậu tố** của bảng tiền tố, có thể chứa **Θ(RC)** ô.

Do vậy, prefix 2D thường phù hợp khi ma trận tĩnh hoặc chỉ được xây lại theo đợt.

### Nếu có cập nhật điểm và query hình chữ nhật

Cân nhắc:

- **Fenwick tree 2D:** point add và rectangle sum O(log R·log C), với cách triển khai phù hợp.
- **Segment tree 2D:** có thể hỗ trợ động nhưng thường khá tốn memory/implementation.
- **Offline updates:** gom cập nhật rồi materialize hoặc coordinate-compress khi được phép.

### Mảng hiệu 2D cho range add ngoại tuyến

Với update cộng Δ vào hình chữ nhật [r1,r2)×[c1,c2), trên bảng hiệu D kích thước (R+1)×(C+1):

**D[r1][c1]+=Δ**.

**D[r2][c1]−=Δ**.

**D[r1][c2]−=Δ**.

**D[r2][c2]+=Δ**.

Sau khi gom update, lấy tổng tiền tố 2D của D để khôi phục lượng cộng tại từng ô, rồi cộng với ma trận gốc.

Đây là mở rộng tự nhiên của **hai mốc biên** thành **bốn góc**, nhưng vẫn cần O(RC) để materialize toàn bộ.

## 19. Vì sao Fenwick tree phù hợp với cập nhật điểm?

**Fenwick tree (Binary Indexed Tree — BIT)** lưu tổng của những đoạn có kích thước là lũy thừa của hai theo cấu trúc chỉ số 1-based.

Một vị trí i trong bit (1≤i≤n) giữ tổng của đoạn:

**[i−lowbit(i),i)**

theo chỉ số nửa mở 0-based của a, với:

**lowbit(i)=i & (−i)**.

Ví dụ:

- bit[1] tổng của a[0].
- bit[2] tổng của a[0..1].
- bit[4] tổng của a[0..3].
- bit[6] tổng của a[4..5].

### Truy vấn tiền tố

Muốn tổng [0,end):

1. Bắt đầu i=end.
2. Cộng bit[i].
3. Trừ lowbit(i) khỏi i.
4. Lặp cho tới i=0.

Mỗi lần bỏ bớt một bit 1 trong biểu diễn nhị phân của chỉ số, nên số lần lặp **O(log n)**.

### Cập nhật một điểm

Nếu a[index] tăng thêm Δ:

1. Bắt đầu i=index+1.
2. Cộng Δ vào bit[i].
3. Tăng i thêm lowbit(i).
4. Lặp đến khi i>n.

Mỗi bước chuyển tới một nút tổ tiên chứa vị trí vừa cập nhật, tổng cộng **O(log n)**.

### Truy vấn đoạn

**sum(l,r)=prefix(r)−prefix(l)**.

Vì tính mỗi prefix O(log n), truy vấn đoạn cũng O(log n).

Đây là khác biệt cơ bản: Fenwick **hi sinh tốc độ query O(1)** của mảng prefix tĩnh để đổi lấy **update điểm O(log n)**.

## 20. Fenwick hỗ trợ set hay add?

Hai kiểu update dễ bị nhầm:

**Point add:** tăng a[index] thêm Δ.

**Point set:** thay a[index] bằng newValue.

Fenwick cơ bản hỗ trợ **add Δ**. Muốn triển khai set, cần biết giá trị cũ:

**Δ=newValue−oldValue**.

Sau đó gọi pointAdd(index,Δ), rồi lưu oldValue=newValue trong bộ nhớ riêng.

### Vì sao không trực tiếp cộng newValue vào bit?

Nếu a[index] đang là 5 và người dùng set thành 10:

- Thay đổi thực là **+5**.
- Nếu cộng thẳng +10 vào Fenwick, tổng bị tăng quá 5.

### Xây Fenwick O(n)

Có hai cách phổ biến:

- Khởi tạo bit=0, gọi add cho từng phần tử: **O(n log n)**.
- Dùng phép truyền giá trị từ node i sang parent i+lowbit(i): **O(n)**.

Chương trình Java dưới đây dùng phương án O(n), không nhầm build cost O(n log n) với lựa chọn tuyến tính.

## 21. Segment tree và lazy propagation

**Segment tree** lưu thông tin tổng của những đoạn con trong một cây nhị phân. Thông thường:

- Xây O(n).
- Query tổng đoạn O(log n).
- Update một điểm O(log n).
- Bộ nhớ O(n).

Fenwick thường ngắn gọn và tiết kiệm hằng số khi chỉ cần tổng cộng dồn và point updates.

### Khi có range add và range sum xen kẽ

Một Fenwick cơ bản chỉ dành cho **point add + prefix/range sum** không tự cho range add + range sum O(log n).

Các lựa chọn thường dùng:

- **Lazy segment tree:** lưu pending range add và propagate khi cần, hỗ trợ range add/query sum O(log n).
- **Hai Fenwick tree:** biến đổi đại số để hỗ trợ range add + prefix sum, và do đó range sum, O(log n) với các hệ số chỉ số thích hợp.
- **Sqrt decomposition:** chia khối, cân bằng thời gian update/query theo khoảng √n.
- **Periodic rebuild:** giữ prefix tĩnh và một danh sách cập nhật pending ngắn, gom/khôi phục theo chu kỳ phù hợp.

### Vì sao difference array chưa đủ?

Difference array thêm update đoạn O(1), nhưng sau mỗi lần update muốn trả tổng một đoạn bất kỳ vẫn có thể phải tích lũy toàn bộ thay đổi ảnh hưởng tới đoạn. Nếu query liên tục xen kẽ, bắt buộc phân tích lại chi phí query.

## 22. Bảng chọn cấu trúc dữ liệu theo thao tác

| Dữ liệu và thao tác | Cấu trúc phù hợp | Update | Query tổng đoạn |
| --- | --- | --- | --- |
| Tĩnh, nhiều truy vấn tổng | Prefix sum 1D | Không cập nhật | O(1) |
| Ma trận tĩnh, truy vấn hình chữ nhật | Prefix sum 2D | Không cập nhật | O(1) |
| Một số cập nhật điểm rất hiếm | Rebuild prefix | O(n) mỗi lần | O(1) |
| Cập nhật điểm và hỏi tổng xen kẽ | Fenwick | O(log n) | O(log n) |
| Cập nhật điểm, nhiều loại aggregate khác | Segment tree | O(log n) | O(log n) với phép gộp phù hợp |
| Nhiều range add, chỉ lấy kết quả cuối | Difference array | O(1) mỗi range add | Sau materialize và prefix: O(1) |
| Range add + range sum xen kẽ | Lazy segment tree / hai BIT | O(log n) | O(log n) |
| Dữ liệu cực thưa, tọa độ lớn | Compression / sparse index | Tùy cấu trúc | Tùy cấu trúc |

Các chi phí trong bảng dùng mô hình RAM chuẩn với phép cộng/so sánh số nguyên cố định O(1). Khi dữ liệu có giá trị BigInteger rất lớn hoặc bộ nhớ ngoài, phải xét thêm chi phí thao tác số học và I/O.

### Không thể thay mọi cấu trúc bằng prefix

Prefix cộng dồn chỉ làm việc trực tiếp cho những phép toán có cách lấy “đoạn” từ hai giá trị tích lũy.

Tổng có phép nghịch đảo cộng/trừ nên dễ: P[r]−P[l].

Với **minimum**, không có công thức tổng quát nào lấy min(a[l..r)) từ chỉ hai giá trị min tiền tố bằng một phép “trừ min”. Nếu cần range minimum queries trên mảng tĩnh, cân nhắc sparse table hoặc cấu trúc RMQ thích hợp.

## 23. Đếm tần suất và truy vấn số lượng phần tử

Prefix sum không nhất thiết cộng chính các giá trị gốc. Có thể biến mỗi phần tử thành một chỉ báo:

**b[i]=1 nếu a[i] thỏa điều kiện; ngược lại 0**.

Xây prefix của b, ta trả được số phần tử thỏa điều kiện trong [l,r) bằng:

**P_b[r]−P_b[l]**.

Ví dụ với a=[3,−2,5,7,0,−4], muốn đếm số dương:

~~~text
b = [1, 0, 1, 1, 0, 0]
P_b = [0, 1, 1, 2, 3, 3, 3]
~~~

Số phần tử dương trong [1,5):

**P_b[5]−P_b[1]=3−1=2**.

### Đếm ký tự, trạng thái hoặc điều kiện

Với chuỗi ký tự, ta có thể xây mỗi prefix cho một ký tự quan tâm; chi phí memory có thể tăng thành O(σn) nếu có σ loại ký tự.

Với điều kiện thay đổi tùy truy vấn, ví dụ “đếm phần tử ≤x” với x khác nhau, một prefix cố định trên một điều kiện có thể chưa đủ. Khi đó cần cấu trúc khác, sắp xếp offline queries hoặc các kỹ thuật nâng cao.

## 24. Dùng prefix cho tổng con và số đoạn thỏa điều kiện

Mỗi tổng đoạn [l,r) bằng:

**P[r]−P[l]**.

Vì vậy nhiều bài subarray có thể chuyển thành bài toán trên **cặp giá trị prefix**.

### Đếm đoạn có tổng đúng K

Muốn P[r]−P[l]=K, ta cần:

**P[l]=P[r]−K**.

Duyệt từ trái sang phải, lưu số lần một giá trị prefix đã xuất hiện trong HashMap:

1. Khởi tạo count[0]=1.
2. Với mỗi phần tử, cập nhật running prefix.
3. Cộng count[running−K] vào đáp án.
4. Tăng count[running] lên 1.

Có thể đạt O(n) kỳ vọng với HashMap trong mô hình thao tác hash thông dụng, cả khi a có số âm.

### Điểm khác biệt

Đây là thuật toán **đếm subarrays** dùng prefix cùng hash, không chỉ là trả một sum query O(1). Cần phân biệt complexity của toàn bài với complexity của một phép lấy hiệu P[r]−P[l].

## 25. Binary search trên prefix chỉ khi có tính đơn điệu

Nếu **a[i]≥0 với mọi i**, P không giảm:

**P[0]≤P[1]≤...≤P[n]**.

Khi ấy có thể dùng lower_bound trên P để tìm vị trí đầu tiên có prefix sum ít nhất X. Độ phức tạp O(log n) sau O(n) preprocessing.

Nếu **mọi a[i]>0**, P tăng nghiêm ngặt, không có các đoạn phẳng do số 0.

Nhưng nếu có số âm, P có thể giảm:

~~~text
a = [3, -2, 5]
P = [0, 3, 1, 6]
~~~

Đây **không phải** một mảng sorted. Không được binary search lower_bound bằng comparator yêu cầu tăng dần rồi tin kết quả đúng.

### Một biến thể khác: sliding window

Nếu mọi phần tử không âm, nhiều bài tìm đoạn thỏa tổng ngưỡng có thể dùng two pointers/sliding window.

Khi có số âm, cửa sổ có thể không còn đơn điệu theo độ dài; cần phương pháp khác như prefix+hash, prefix+deque hoặc ordered structure tùy bài.

## 26. Ngoại tuyến truy vấn khác gì ngoại tuyến cập nhật?

Có hai kiểu xử lý offline phổ biến:

**Offline updates:** gom nhiều phép cộng đoạn, dùng difference array rồi build dữ liệu cuối.

**Offline queries:** biết trước toàn bộ truy vấn nên có thể **sắp xếp lại thứ tự xử lý** để giảm chi phí, miễn vẫn trả kết quả theo thứ tự yêu cầu gốc.

Ví dụ Mo's algorithm sắp xếp các truy vấn đoạn để giảm số lần di chuyển biên cửa sổ trong những bài aggregate có thao tác add/remove phù hợp.

### Prefix sum không cần sắp xếp query

Với các truy vấn tổng trên mảng tĩnh, prefix đã trả O(1) nên không cần Mo's algorithm. Dùng Mo's algorithm cho tổng đoạn thuần túy thường phức tạp hơn mà không đem lại lợi ích.

### Nếu query và update xen kẽ

Trong bài toán có dấu thời gian, việc sắp xếp query theo biên mà bỏ qua thứ tự update sẽ khiến câu trả lời sai. Các thuật toán offline có updates (ví dụ Mo's algorithm with modifications) phải theo dõi cả chiều thời gian.

**Offline không trao quyền thay đổi ý nghĩa thời điểm của một query.**

## 27. Chương trình Java 17+ chạy độc lập

Chương trình gồm bốn thành phần tách biệt:

- **Prefix1D:** snapshot mảng int, prefix long; truy vấn [l,r) và [l,r] O(1); cập nhật bằng **tạo bản snapshot mới** O(n).
- **Prefix2D:** prefix long theo ma trận int hình chữ nhật; truy vấn hình chữ nhật O(1).
- **DiffOffline:** gom cập nhật cộng đoạn [l,r) vào diff long[], rồi materialize bản dữ liệu sau cùng O(n).
- **Fenwick:** dựng tuyến tính O(n), update điểm kiểu set O(log n), query tổng đoạn O(log n).

Các input gốc **không bị sửa** khi xây prefix; các phương thức có kiểm tra chỉ số; dùng long cho tổng.

**Tên tệp: StaticPrefixAndUpdatesDemo.java**

~~~java
import java.util.Arrays;
import java.util.Objects;

public class StaticPrefixAndUpdatesDemo {

    static final class Prefix1D {
        private final int[] values;
        private final long[] prefix;

        Prefix1D(int[] input) {
            Objects.requireNonNull(input, "input");
            values = input.clone();
            prefix = new long[values.length + 1];

            for (int i = 0; i < values.length; i++) {
                prefix[i + 1] = prefix[i] + values[i];
            }
        }

        private void checkRange(int left, int right) {
            if (left < 0 || right < left
                    || right > values.length) {
                throw new IndexOutOfBoundsException(
                        "invalid half-open range");
            }
        }

        long sumRange(int left, int right) {
            checkRange(left, right);
            return prefix[right] - prefix[left];
        }

        long sumInclusive(int left, int right) {
            if (left < 0 || right < left
                    || right >= values.length) {
                throw new IndexOutOfBoundsException(
                        "invalid inclusive range");
            }

            return sumRange(left, right + 1);
        }

        long[] prefixCopy() {
            return prefix.clone();
        }

        // Rebuilds an independent snapshot in O(n).
        Prefix1D withSet(int index, int newValue) {
            if (index < 0 || index >= values.length) {
                throw new IndexOutOfBoundsException(index);
            }

            int[] next = values.clone();
            next[index] = newValue;
            return new Prefix1D(next);
        }
    }

    static final class Prefix2D {
        private final int rows;
        private final int cols;
        private final long[][] prefix;

        Prefix2D(int[][] grid) {
            Objects.requireNonNull(grid, "grid");
            rows = grid.length;
            cols = rows == 0
                    ? 0 : Objects.requireNonNull(
                            grid[0], "grid row").length;

            for (int r = 0; r < rows; r++) {
                Objects.requireNonNull(grid[r], "grid row");
                if (grid[r].length != cols) {
                    throw new IllegalArgumentException(
                            "ragged grid is not supported");
                }
            }

            prefix = new long[rows + 1][cols + 1];

            for (int r = 0; r < rows; r++) {
                long rowRunning = 0L;

                for (int c = 0; c < cols; c++) {
                    rowRunning += grid[r][c];
                    prefix[r + 1][c + 1] =
                            prefix[r][c + 1] + rowRunning;
                }
            }
        }

        long sumRect(
                int top, int bottom,
                int left, int right) {

            if (top < 0 || bottom < top
                    || bottom > rows
                    || left < 0 || right < left
                    || right > cols) {
                throw new IndexOutOfBoundsException(
                        "invalid rectangle");
            }

            return prefix[bottom][right]
                    - prefix[top][right]
                    - prefix[bottom][left]
                    + prefix[top][left];
        }
    }

    static final class DiffOffline {
        private final int[] original;
        private final long[] diff;

        DiffOffline(int[] input) {
            Objects.requireNonNull(input, "input");
            original = input.clone();
            diff = new long[original.length + 1];
        }

        // O(1) per range addition, materialize later.
        void addRange(int left, int right, long delta) {
            if (left < 0 || right < left
                    || right > original.length) {
                throw new IndexOutOfBoundsException(
                        "invalid update range");
            }

            if (left == right || delta == 0L) {
                return;
            }

            // Calculate both before committing them.
            // ArithmeticException prevents silent overflow.
            long newLeft = Math.addExact(diff[left], delta);
            long newRight = Math.subtractExact(
                    diff[right], delta);

            diff[left] = newLeft;
            diff[right] = newRight;
        }

        // O(n): apply every range update to a fresh result.
        long[] materialize() {
            long[] out = new long[original.length];
            long running = 0L;

            for (int i = 0; i < original.length; i++) {
                running = Math.addExact(running, diff[i]);
                out[i] = Math.addExact(
                        (long) original[i], running);
            }

            return out;
        }
    }

    static final class Fenwick {
        private final int[] values;
        private final long[] tree;

        Fenwick(int[] input) {
            Objects.requireNonNull(input, "input");
            values = input.clone();
            tree = new long[values.length + 1];

            // Linear-time Fenwick construction.
            for (int i = 1; i < tree.length; i++) {
                tree[i] += values[i - 1];
                long parent = (long) i + (i & -i);

                if (parent <= values.length) {
                    tree[(int) parent] += tree[i];
                }
            }
        }

        // A point assignment converted to a point delta.
        void set(int index, int newValue) {
            if (index < 0 || index >= values.length) {
                throw new IndexOutOfBoundsException(index);
            }

            long delta = (long) newValue - values[index];
            values[index] = newValue;

            for (long i = (long) index + 1;
                    i <= values.length;
                    i += i & -i) {

                tree[(int) i] += delta;
            }
        }

        long prefixExclusive(int end) {
            if (end < 0 || end > values.length) {
                throw new IndexOutOfBoundsException(end);
            }

            long sum = 0L;

            for (int i = end; i > 0; i -= i & -i) {
                sum += tree[i];
            }

            return sum;
        }

        long sumRange(int left, int right) {
            if (left < 0 || right < left
                    || right > values.length) {
                throw new IndexOutOfBoundsException(
                        "invalid Fenwick range");
            }

            return prefixExclusive(right)
                    - prefixExclusive(left);
        }
    }

    public static void main(String[] args) {
        int[] data = {3, -2, 5, 7, 0, -4};

        Prefix1D snapshot = new Prefix1D(data);

        System.out.println("Base: "
                + Arrays.toString(data));
        System.out.println("Prefix: "
                + Arrays.toString(snapshot.prefixCopy()));

        System.out.println("Static sum [1,5): "
                + snapshot.sumRange(1, 5));

        System.out.println("Static inclusive [2,4]: "
                + snapshot.sumInclusive(2, 4));

        System.out.println("Empty [3,3): "
                + snapshot.sumRange(3, 3));

        System.out.println("Full [0,6): "
                + snapshot.sumRange(0, 6));

        // Mutating input must not mutate an old snapshot.
        data[0] = 999;
        System.out.println("Snapshot after external edit: "
                + snapshot.sumRange(0, 6));
        data[0] = 3;

        Prefix1D revised = snapshot.withSet(2, 10);

        System.out.println("Old snapshot [1,5): "
                + snapshot.sumRange(1, 5));
        System.out.println("Rebuilt snapshot [1,5): "
                + revised.sumRange(1, 5));

        int[][] grid = {
                {1, 2, 3},
                {4, 5, 6},
                {7, 8, 9}
        };

        Prefix2D rectangle = new Prefix2D(grid);

        System.out.println("2D [0,2)x[1,3): "
                + rectangle.sumRect(0, 2, 1, 3));

        System.out.println("2D [1,3)x[0,2): "
                + rectangle.sumRect(1, 3, 0, 2));

        System.out.println("2D full: "
                + rectangle.sumRect(0, 3, 0, 3));

        System.out.println("2D empty: "
                + rectangle.sumRect(2, 2, 0, 3));

        DiffOffline offline = new DiffOffline(data);

        offline.addRange(1, 4, 3L);
        offline.addRange(3, 6, -2L);
        offline.addRange(0, 2, 1L);

        long[] afterBatch = offline.materialize();

        System.out.println("Offline range adds: "
                + Arrays.toString(afterBatch));

        long offlineSubrange = 0L;
        for (int i = 1; i < 5; i++) {
            offlineSubrange += afterBatch[i];
        }

        System.out.println("Offline sum [1,5): "
                + offlineSubrange);

        Fenwick dynamic = new Fenwick(data);

        System.out.println("Fenwick initial [1,5): "
                + dynamic.sumRange(1, 5));

        dynamic.set(2, 10);
        System.out.println("Fenwick after set(2,10) [1,5): "
                + dynamic.sumRange(1, 5));

        dynamic.set(0, -1);
        System.out.println("Fenwick after set(0,-1) full: "
                + dynamic.sumRange(0, 6));

        System.out.println("Fenwick prefix [0,3): "
                + dynamic.prefixExclusive(3));

        System.out.println("Original snapshot still [1,5): "
                + snapshot.sumRange(1, 5));
    }
}
~~~

Biên dịch và chạy với **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 StaticPrefixAndUpdatesDemo.java
java StaticPrefixAndUpdatesDemo
~~~

**Đầu ra chuẩn:**

~~~text
Base: [3, -2, 5, 7, 0, -4]
Prefix: [0, 3, 1, 6, 13, 13, 9]
Static sum [1,5): 10
Static inclusive [2,4]: 12
Empty [3,3): 0
Full [0,6): 9
Snapshot after external edit: 9
Old snapshot [1,5): 10
Rebuilt snapshot [1,5): 15
2D [0,2)x[1,3): 16
2D [1,3)x[0,2): 24
2D full: 45
2D empty: 0
Offline range adds: [4, 2, 8, 8, -2, -6]
Offline sum [1,5): 16
Fenwick initial [1,5): 10
Fenwick after set(2,10) [1,5): 15
Fenwick after set(0,-1) full: 10
Fenwick prefix [0,3): 7
Original snapshot still [1,5): 10
~~~

### Lý do chọn bốn lớp tách biệt

**Prefix1D** không có update mutation; với withSet nó tạo đối tượng mới O(n). Code minh họa một **snapshot** mà client có thể đọc an toàn dù mảng input bên ngoài bị sửa sau constructor.

**Prefix2D** lưu bảng tích lũy, không giữ tham chiếu ma trận gốc để phụ thuộc vào dữ liệu có thể đổi; đầu vào được kiểm tra rectangular.

**DiffOffline** chỉ lưu update và trả **mảng kết quả cuối** khi materialize. Nó không giả vờ trả tổng O(1) ở mọi thời điểm xen kẽ update. Math.addExact/subtractExact được dùng cho diff để từ chối các phép cộng vượt long thay vì wrap âm thầm.

**Fenwick** giữ bản giá trị riêng; với set phải lấy delta=(long)new−old. Phương thức set thay đổi trạng thái động O(log n), mọi sumRange sau đó phản ánh trạng thái mới.

### Lưu ý xử lý overflow trong ví dụ

- Với mảng int, các tổng số lượng phần tử hợp lệ thực tế nằm trong long; phép cộng trong ví dụ an toàn.
- DiffOffline cho phép delta kiểu long; những giá trị quá lớn gây overflow sẽ ném ArithmeticException, không tạo ra kết quả wrap. Việc kiểm tra cả hai mốc biên trước khi gán giúp một update không bị ghi nửa vời nếu riêng hai phép thay diff ở biên gặp overflow.
- Nếu bài đòi thao tác trên long[] với một số lượng rất lớn giá trị long, việc dùng long để chứa tổng có thể vẫn tràn; cần thêm kiểm tra hoặc BigInteger.

### Mã Java biểu diễn phương pháp, không tự chứng minh mọi biến thể

Mã dùng half-open intervals, không tự hỗ trợ truy vấn min/max hay update đoạn trực tuyến bằng một Fenwick. Để giải bài khác, cần chọn đúng phép kết hợp và đúng lớp cấu trúc, không chỉ đổi tên phương thức.

## 28. Kiểm thử prefix 1D bằng oracle cộng trực tiếp

Một oracle đơn giản:

~~~text
BRUTE_SUM(a,l,r):
    answer = 0
    for i from l to r-1:
        answer += a[i]
    return answer
~~~

Sinh nhiều mảng ngẫu nhiên có số âm, số 0 và số dương; với mỗi mảng, chọn nhiều đoạn [l,r) hợp lệ và kiểm tra:

**prefix.sumRange(l,r)=BRUTE_SUM(a,l,r)**.

### Những trường hợp nên có

1. Mảng rỗng n=0, chỉ query [0,0).
2. Mảng một phần tử.
3. Mảng toàn 0.
4. Mảng toàn số âm.
5. Mảng tăng/giảm.
6. Đoạn [0,n) phủ toàn mảng.
7. Đoạn [l,l) rỗng.
8. Một phần tử [i,i+1).
9. Giá trị Integer.MIN_VALUE và Integer.MAX_VALUE.
10. Phép sửa data bên ngoài sau khi build prefix: snapshot phải giữ tổng cũ.
11. Tạo snapshot mới sau set: tổng phải đổi chính xác bằng delta trong các đoạn chứa index.
12. Với query đóng [l,r], so với oracle dùng chỉ số i từ l tới r bao gồm r.

**Không cần so hai phiên bản prefix giống nhau.** Oracle vòng lặp là cách tính độc lập, dễ xác định sai sót off-by-one.

## 29. Kiểm thử prefix 2D bằng oracle vòng lặp lồng nhau

Với ma trận nhỏ R×C, sinh ngẫu nhiên bốn chỉ số:

**0≤top≤bottom≤R**.

**0≤left≤right≤C**.

Oracle:

~~~text
BRUTE_RECT(grid,top,bottom,left,right):
    sum = 0
    for r from top to bottom-1:
        for c from left to right-1:
            sum += grid[r][c]
    return sum
~~~

So với công thức bốn góc trong Prefix2D.

### Test quan trọng

- Ma trận 0 hàng.
- Ma trận có hàng nhưng 0 cột.
- Ma trận một hàng hoặc một cột.
- Hình chữ nhật rỗng theo chiều hàng hoặc cột.
- Hình chữ nhật phủ toàn ma trận.
- Ma trận chứa giá trị âm.
- Ma trận jagged (hàng dài khác nhau) phải bị từ chối nếu hợp đồng yêu cầu rectangular.
- Ma trận bị sửa sau khi build prefix: snapshot prefix cũ vẫn đại diện dữ liệu lúc xây.

Các lỗi hay gặp là quên P[top][left] hoặc đảo thứ tự r/c.

## 30. Kiểm thử difference array và Fenwick bằng oracle động

### Difference array

Sinh một mảng gốc và bản sao naive. Với mỗi cập nhật [l,r), Δ:

- Trong diff: gọi addRange(l,r,Δ) O(1).
- Trong naive: cộng Δ trực tiếp cho mọi i từ l tới r−1.

Sau toàn bộ cập nhật:

**diff.materialize() phải bằng naive tại mọi chỉ số**.

Đặc biệt kiểm tra đoạn:

- [0,n) cập nhật toàn bộ.
- [l,l) không đổi.
- [n,n) rỗng.
- [n−1,n) sửa phần tử cuối.
- Nhiều cập nhật chồng lấp và Δ âm.

### Fenwick

Sinh một mảng mutable naive và một Fenwick xây từ cùng dữ liệu. Lặp các thao tác:

- **set(index,newValue):** sửa cả hai.
- **sumRange(l,r):** so Fenwick với vòng lặp naive.
- **prefixExclusive(end):** so với tổng a[0..end).

Cần kiểm tra **query sau từng update**, không chỉ query sau tất cả các update. Đó là điểm khác biệt bản chất giữa Fenwick và difference array.

### Bất biến tự kiểm tra

- prefix[0]=0.
- prefix[i+1]−prefix[i]=a[i] trên snapshot.
- sumRange(l,l)=0.
- sumRange(l,r)+sumRange(r,t)=sumRange(l,t), với l≤r≤t.
- Fenwick point set vào cùng giá trị cũ không đổi tổng.
- Materialize difference array không tự đổi mảng gốc.
- Truy vấn tổng của bản snapshot cũ vẫn phản ánh đúng phiên bản cũ.

## 31. Cận dưới về số lượng query và locality

Nếu chỉ có một truy vấn, cần đọc phần tử trong đoạn để tính tổng trừ khi có tiền xử lý/kiến thức khác. Với q truy vấn tĩnh, prefix tận dụng việc đọc một lần và lưu các tổng tích lũy.

**Tối ưu theo tổng công việc** và **tối ưu latency một query** khác nhau:

- Prefix mất O(n) thời gian khởi tạo nhưng sau đó query O(1).
- Direct scan không mất phí xây prefix nhưng query dài.
- Fenwick cân bằng giữa update và query.
- Một hệ thống có dữ liệu rất lớn ngoài RAM có thể ưu tiên block-prefix hoặc các chỉ mục thưa để giảm số lần đọc đĩa.

### Cache CPU và bộ nhớ

Một mảng prefix long n+1 thường chiếm khoảng 8(n+1) bytes dữ liệu nguyên thủy, chưa tính overhead của array Java. Với n=10^7, riêng vùng payload xấp xỉ 80 MB. Nếu data int còn giữ riêng, thêm khoảng 40 MB payload.

Các số này dựa trên kích thước int/long của Java, chưa tính alignment, headers, compressed references và bộ nhớ heap cần thiết cho JVM.

### Điểm dừng thực dụng

Không cần biến mọi bài thành Fenwick. Nếu dữ liệu immutable và query thuần tổng đoạn, prefix sum đơn giản, dễ kiểm chứng và thường nhanh hơn nhờ truy cập liên tiếp bộ nhớ.

## 32. Lỗi thường gặp

1. **Nhầm [l,r) với [l,r]**, cộng thiếu/thừa phần tử biên phải.
2. **Không tạo P[0]=0**, phải viết nhánh đặc biệt cho đoạn bắt đầu 0.
3. **Dùng int cho tổng của nhiều int lớn**, dẫn đến overflow.
4. **Ép kiểu long sau một phép int+int đã tràn**, không sửa được kết quả.
5. **Bỏ kiểm tra l≤r**, làm một đoạn đảo chiều bị dùng như truy vấn hợp lệ.
6. **Quên đoạn rỗng [l,l) phải trả 0**.
7. **Cho rằng số âm làm prefix sum sai**, thật ra chỉ làm mất tính đơn điệu.
8. **Binary search prefix khi có số âm**, giả thiết sorted không đúng.
9. **Cho rằng prefix tự đổi khi sửa mảng gốc**, vi phạm snapshot.
10. **Cập nhật a[p] nhưng không sửa P[p+1..n]**, trả query stale.
11. **Nói point update của prefix là O(1)** chỉ vì sửa đúng một ô a[p], quên các prefix sau nó.
12. **Rebuild O(n) sau mọi update mà không phân tích tổng u·n**, không phù hợp workload.
13. **Dùng difference array cho query xen kẽ update rồi gọi mọi query O(1)**, bỏ chi phí materialization.
14. **Ghi D[r] khi diff chỉ dài n và r=n**, vượt chỉ số.
15. **Không xử lý [l,l) hoặc delta=0**, làm thao tác không cần thiết.
16. **Cộng D[r] thay vì trừ D[r]**, ảnh hưởng lan quá đoạn.
17. **Khôi phục diff mà quên cộng mảng gốc**, đánh mất dữ liệu ban đầu.
18. **Cộng lại dữ liệu gốc hai lần** khi dùng difference representation của chính a.
19. **Dùng prefix cũ sau offline range updates**, trả kết quả cho phiên bản sai.
20. **Chuyển query qua update khi xử lý offline**, làm sai thời điểm.
21. **Quên hàng 0/cột 0 của prefix 2D**, sai truy vấn sát biên.
22. **Thiếu góc cộng lại P[top][left]**, inclusion–exclusion sai.
23. **Nhầm hàng và cột trong prefix 2D**, tạo index ngoài mảng.
24. **Không kiểm tra ma trận jagged**, code 2D truy cập sai.
25. **Coi prefix 2D memory O(R+C)**, thật ra O(RC).
26. **Dùng một Fenwick point-update để tuyên bố hỗ trợ range-add/range-sum O(log n)**, thiếu biến đổi.
27. **Coi phép set(index,value) như cộng thêm value**, thay vì dùng delta.
28. **Không lưu current value cho point set Fenwick**, không tính được delta.
29. **Dùng lowbit(i) ở chỉ số 0**, vòng lặp update không tiến vì lowbit(0)=0.
30. **Tạo BIT bằng n lần add nhưng ghi build O(n)**, trong khi cách đó O(n log n).
31. **Gọi mọi loại truy vấn aggregate có phép trừ tiền tố**, không đúng với min.
32. **Cho rằng binary search trên prefix luôn hợp lệ**, thiếu nonnegative invariant.
33. **Không tính cost của phép BigInteger**, mặc nhiên O(1) cho số tùy ý.
34. **Coi kết quả snapshot immutable phản ánh dữ liệu realtime**, sai hợp đồng.
35. **Bỏ concurrency/snapshot versioning** trong hệ thống đa luồng, đọc tổng ở phiên bản không nhất quán.
36. **Chỉ benchmark q=1 nhưng xây O(n) prefix**, không cân nhắc overhead.
37. **Không dùng oracle đơn giản cho test**, dễ sót sai off-by-one.
38. **Chỉ thử mảng số dương**, không phát hiện vấn đề dấu hoặc assumed monotonicity.
39. **Không thử n=0 hoặc kênh update rỗng**, dễ lỗi index.
40. **So hai cách build prefix giống hệt nhau** rồi gọi là kiểm thử độc lập.
41. **Cập nhật diff bằng long delta cực lớn mà để overflow im lặng**, gây kết quả wrap.
42. **Giữ một mảng prefix 2D dày đặc cho dữ liệu rất thưa**, lãng phí RAM.
43. **Không nêu mục tiêu query sau cùng hay query xen kẽ**, chọn cấu trúc sai.
44. **Nhầm O(1) query với O(1) toàn bài**, bỏ O(n) preprocessing và memory.
45. **Nói thuật toán tiền tố “không cần dữ liệu gốc” nhưng API lại tham chiếu mảng mutable**, dễ gây lỗi lifecycle.
46. **Dùng tiền tố cho giá trị floating point mà giả định phép cộng hoàn toàn kết hợp**, sai vì roundoff có thể làm P[r]−P[l] nhạy với cancellation.

## 33. Bài tập tự luyện

**Bài 1.** Với a=[3,−2,5,7,0,−4], hãy tính P.  
**Đáp án:** [0,3,1,6,13,13,9].

**Bài 2.** Tính sum[1,5).  
**Đáp án:** P[5]−P[1]=13−3=10.

**Bài 3.** Tính tổng đoạn đóng [2,4].  
**Đáp án:** 5+7+0=12, tương đương nửa mở [2,5).

**Bài 4.** Tính sum[3,3).  
**Đáp án:** 0.

**Bài 5.** Prefix xây O(n). q truy vấn tổng có chi phí bao nhiêu?  
**Đáp án:** O(n+q).

**Bài 6.** Nếu a[2] tăng 5, những P nào cần sửa?  
**Đáp án:** P[3]..P[n], mỗi ô tăng 5.

**Bài 7.** Có u point updates xen q queries, rebuild prefix mỗi lần tốn xấu nhất?  
**Đáp án:** O(n+un+q).

**Bài 8.** Có nhiều sửa điểm/query xen kẽ, dùng cấu trúc nào đơn giản hơn?  
**Đáp án:** Fenwick cho tổng, O(log n) mỗi update/query.

**Bài 9.** Với mảng có số âm, sumRange bằng hiệu prefix có đúng không?  
**Đáp án:** Có.

**Bài 10.** Với mảng có số âm, P luôn tăng không?  
**Đáp án:** Không, nên không tự binary search.

**Bài 11.** Với grid 3×3 chứa 1..9 theo hàng, query [0,2)×[1,3)?  
**Đáp án:** 16.

**Bài 12.** Query [1,3)×[0,2) của grid ấy?  
**Đáp án:** 24.

**Bài 13.** Viết công thức rectangle sum 2D.  
**Đáp án:** P[bottom][right]−P[top][right]−P[bottom][left]+P[top][left].

**Bài 14.** Range add +3 lên [1,4) đổi diff thế nào?  
**Đáp án:** D[1]+=3, D[4]−=3.

**Bài 15.** Sau ba update minh họa, mảng cuối là gì?  
**Đáp án:** [4,2,8,8,−2,−6].

**Bài 16.** Tổng [1,5) sau ba update?  
**Đáp án:** 16.

**Bài 17.** Vì sao difference array không giải ngay query xen kẽ update với O(1) mỗi truy vấn?  
**Đáp án:** Cần tính tích lũy các update đã ghi, có chi phí materialize hoặc cấu trúc phụ.

**Bài 18.** Fenwick set a[2] từ 5 thành 10, delta là bao nhiêu?  
**Đáp án:** +5.

**Bài 19.** Fenwick set a[0] từ 3 thành −1, delta là bao nhiêu?  
**Đáp án:** −4.

**Bài 20.** Sau hai point sets trong ví dụ, full sum là bao nhiêu?  
**Đáp án:** 10.

**Bài 21.** Một mảng gồm các số int bằng 2 tỷ, prefix nên dùng kiểu nào?  
**Đáp án:** long, nếu bound tổng nằm trong long.

**Bài 22.** Vì sao prefix không thay được range minimum query bằng phép trừ?  
**Đáp án:** Min không có phép nghịch đảo phù hợp để khôi phục min đoạn từ hai min tiền tố.

**Bài 23.** Khi nào lower_bound trên P hữu ích?  
**Đáp án:** Khi P đã được bảo đảm không giảm, ví dụ mọi a[i]≥0.

**Bài 24.** Có R×C ma trận tĩnh, xử lý q rectangle sum queries tốn bao nhiêu?  
**Đáp án:** O(RC+q) thời gian, O(RC) bộ nhớ.

**Bài 25.** Range add và range sum xen kẽ nên cân nhắc gì?  
**Đáp án:** Lazy segment tree hoặc hai Fenwick tree với biến đổi đúng, O(log n) thao tác.

**Bài 26.** Query tổng hậu cập nhật nhưng dữ liệu đã đổi ngoài đối tượng prefix thì sao?  
**Đáp án:** Phải tạo snapshot mới hoặc chủ động maintain cấu trúc động.

## 34. Checklist và kết luận

Trước khi chọn prefix sum trong một hệ thống truy vấn:

1. **Xác định dữ liệu có thật sự tĩnh không.**
2. **Định nghĩa rõ đoạn [l,r) hay [l,r].**
3. **Dùng P[0]=0 và P[i+1]=P[i]+a[i].**
4. **Kiểm tra các biên 0≤l≤r≤n.**
5. **Chọn long/BigInteger phù hợp tổng lớn**, không để overflow.
6. **Nếu có số âm, đừng giả định prefix tăng.**
7. **Nếu query nhiều và update ít, cân nhắc snapshot/rebuild.**
8. **Nếu point updates xen queries, cân nhắc Fenwick/segment tree.**
9. **Nếu range updates đều xảy ra trước queries, cân nhắc difference array.**
10. **Nếu range add và range sum xen kẽ, dùng cấu trúc dynamic phù hợp.**
11. **Với 2D, tạo hàng/cột 0 và áp dụng inclusion–exclusion đúng.**
12. **Kiểm tra bộ nhớ O(n) hoặc O(RC)** trước khi cấp phát.
13. **Giữ nguyên phiên bản dữ liệu khi snapshot được dùng đồng thời**, tránh đọc chỉ mục stale.
14. **Tách preprocessing cost và per-query cost** khi phân tích.
15. **Đếm đúng số lượng update và query**, không chỉ nhìn Big O của query.
16. **Không dùng prefix subtraction cho mọi phép gộp**, xem có phép nghịch đảo hay không.
17. **Làm QA bằng direct-scan oracle**, không chỉ một code prefix khác.
18. **Thử số âm, giá trị biên int, đoạn rỗng, full-range và dữ liệu rỗng.**
19. **Với difference array, đối chiếu mảng cuối bằng cách cập nhật trực tiếp trên bản sao.**
20. **Với Fenwick, đối chiếu mỗi query sau mỗi update**, không chỉ trạng thái cuối.
21. **Nếu truy vấn ngoại tuyến, giữ nguyên ngữ nghĩa thời điểm của query.**
22. **Ghi rõ giới hạn bài toán**: phép cộng số nguyên, dữ liệu tĩnh, điểm update hay đoạn update.

**Kết luận:** prefix sum là một cách **đổi O(n) thời gian và bộ nhớ tiền xử lý lấy O(1) cho mỗi truy vấn tổng đoạn trên dữ liệu tĩnh**. Một cập nhật điểm làm thay đổi cả hậu tố của mảng P, nên việc duy trì trực tiếp có thể tốn Θ(n). Khi nhiều update được gom trước khi hỏi, **difference array** giúp cập nhật đoạn O(1) và khôi phục O(n). Khi update và query xen kẽ, **Fenwick tree hoặc segment tree** trả lại sự cân bằng O(log n). Điều quan trọng không chỉ là biết công thức P[r]−P[l], mà là **chọn đúng cấu trúc theo lịch trình truy vấn và cập nhật thực tế**.
