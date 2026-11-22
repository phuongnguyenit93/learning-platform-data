# Luồng có cận dưới và bài toán tuần hoàn

**Luồng có cận dưới** (*flow with lower bounds*) mở rộng luồng mạng thông thường: thay vì chỉ yêu cầu lượng luồng trên mỗi cung không âm và không vượt quá sức chứa, ta còn bắt buộc phải vận chuyển **ít nhất một lượng tối thiểu** qua từng cung. **Bài toán luồng tuần hoàn khả thi** (*feasible circulation*) hỏi liệu có thể gán luồng cho **tất cả cung có hướng**, thỏa cận dưới, cận trên và **cân bằng luồng tại mọi đỉnh** hay không.

Đây là công cụ quan trọng trong bài toán phân phối, lịch làm việc, vận tải, ràng buộc tối thiểu–tối đa, cân đối cung–cầu và bài toán luồng từ nguồn tới đích có những cung bắt buộc dùng ít nhất L đơn vị.

Ý tưởng giải chuẩn biến bài toán có cận dưới thành **một bài max flow thông thường** bằng cách:

1. Với mỗi cung \(u\to v\) có cận dưới L và cận trên U, đặt **luồng bù** \(x(u,v)=f(u,v)-L\), nên \(0\le x\le U-L\).
2. Tính **độ mất cân bằng do phần luồng bắt buộc** tại mỗi đỉnh:
   \[
   b(v)=\sum_{u\to v}L(u,v)-\sum_{v\to w}L(v,w).
   \]
3. Thêm **siêu nguồn** SS, **siêu đích** TT và các cung điều chỉnh mất cân bằng.
4. Chạy max flow SS→TT trên mạng phụ trợ; **tuần hoàn khả thi khi và chỉ khi mọi cung rời SS được bão hòa**.
5. Phục hồi luồng gốc bằng \(f=L+x\), rồi kiểm tra các cận và phương trình bảo toàn.

Bài này giải thích kỹ **chiều của các cung SS/TT**, chứng minh tính tương đương, ví dụ có cả nghiệm và vô nghiệm, mở rộng có **yêu cầu cân đối tại đỉnh**, cách quy về tuần hoàn cho **luồng s–t có cận dưới**, chứng chỉ vô nghiệm qua min-cut, độ phức tạp và chương trình **Java 17+ chạy độc lập** sử dụng Dinic.

## 1. Bài toán chính xác: cận dưới, cận trên, bảo toàn

Cho mạng có hướng \(G=(V,E)\). Mỗi cung e=(u,v) có hai số nguyên:

\[
0\le L_e\le U_e.
\]

**Luồng gốc** \(f_e\) phải thỏa:

\[
\boxed{L_e\le f_e\le U_e.}
\]

Với **tuần hoàn thuần túy** (*circulation without external demands*), mọi đỉnh v thỏa **bảo toàn**:

\[
\boxed{\sum_{u\to v} f(u,v)=\sum_{v\to w} f(v,w).}
\]

Vế trái là **tổng luồng vào**, vế phải là **tổng luồng ra**. Khác bài max flow s–t truyền thống, **không có hai đỉnh nguồn/đích được miễn điều kiện bảo toàn**: mọi đỉnh đều là nút trung chuyển về mặt phương trình.

### Điều cần tìm là tính khả thi, chưa phải tối ưu

Đề bài có thể chỉ hỏi **có tồn tại nghiệm không**; nếu có, xuất **một bộ luồng f hợp lệ**. Tối đa hóa tổng luồng, giảm chi phí, hay tối ưu tổng vận chuyển là **bài toán khác** cần thêm mục tiêu.

Trong bài toán tuần hoàn khả thi **không gắn chi phí**, ta không cần chọn nghiệm nhỏ nhất/lớn nhất theo bất kỳ thứ tự nào. Nhiều bộ luồng khác nhau có thể đều đúng. Thuật toán max flow phụ trợ trả một nghiệm phụ thuộc thứ tự cung và cách tìm đường tăng, nhưng **tính khả thi** không phụ thuộc thứ tự đó.

### Cận dưới khiến luồng toàn 0 có thể sai

Với mạng chỉ có một cung:

~~~text
0 --[L=2,U=2]--> 1
~~~

Bắt buộc `f(0,1)=2`. Khi đó đỉnh 0 có luồng ra 2 nhưng vào 0; đỉnh 1 có luồng vào 2 nhưng ra 0. Vì yêu cầu **tuần hoàn tại cả hai đỉnh**, **không có nghiệm**, dù cung hoàn toàn hợp lệ về giới hạn.

Ngược lại, nếu thêm cung `1→0` có cận `[0,3]`, ta có thể chọn `f(0,1)=2`, `f(1,0)=2`; mọi đỉnh cân bằng và bài toán trở thành khả thi.

**Luồng có cận dưới** không đồng nghĩa “đường đi ngắn nhất có trọng số âm”: các cận ở đây là **lượng tối thiểu và tối đa**, không phải độ dài hay chi phí của cung.

## 2. Loại bỏ cận dưới bằng biến luồng bù

Xét một cung \(u\to v\) có cận \([L,U]\). Đặt:

\[
\boxed{x(u,v)=f(u,v)-L(u,v).}
\]

Khi đó:

\[
L\le f\le U
\quad\Longleftrightarrow\quad
\boxed{0\le x\le U-L.}
\]

Như vậy ta có thể thay mỗi cung gốc bằng một cung **dung lượng dư ban đầu** \(U-L\). Từ đây thuật toán max flow thông thường có thể làm việc với x **không âm**.

Nhưng một vấn đề mới xuất hiện: **mỗi đỉnh không nhất thiết cân bằng trên riêng luồng x**. Phần L bắt buộc đã tự tạo chênh lệch vào/ra; x phải bù đúng chênh lệch ấy.

Đặt:

\[
b(v)=\sum_{\text{cung vào }v} L_e-\sum_{\text{cung ra }v} L_e.
\]

Lấy phương trình tuần hoàn của f:

\[
\sum_{\text{vào }v}(L+x)
=
\sum_{\text{ra }v}(L+x).
\]

Chuyển vế, ta được:

\[
\sum_{\text{ra }v}x-\sum_{\text{vào }v}x
=
\sum_{\text{vào }v}L-\sum_{\text{ra }v}L
=
\boxed{b(v)}.
\]

**Công thức phải nhớ:**

\[
\boxed{out_x(v)-in_x(v)=b(v).}
\]

### Diễn giải dấu

- **b(v) > 0**: phần L bắt buộc làm v **nhận vào nhiều hơn đi ra**. Phần x phải **đi ra thêm b(v)** để cân bằng.
- **b(v) < 0**: phần L bắt buộc làm v **đi ra nhiều hơn nhận vào**. Phần x phải **đi vào thêm −b(v)**.
- **b(v) = 0**: riêng phần L đã cân bằng tại v; phần x cần bảo toàn tại v.

Đây là nguồn gốc của hướng các cạnh từ siêu nguồn và tới siêu đích. Không nên học thuộc chiều cạnh mà không dẫn xuất phương trình, vì các tài liệu có thể dùng quy ước biến cân bằng **ngược dấu**.

### Tổng b luôn bằng 0

Mỗi cận dưới L được cộng đúng một lần vào b ở **đỉnh nhận** và trừ đúng một lần ở b tại **đỉnh gửi**. Vì vậy:

\[
\boxed{\sum_{v\in V}b(v)=0.}
\]

Điều này cũng đúng với **self-loop u→u**, vì L vừa đi vào vừa đi ra cùng một đỉnh và hai đóng góp triệt tiêu.

Tổng b dương luôn bằng trị tuyệt đối của tổng b âm. Tuy nhiên **đẳng thức tổng không đủ bảo đảm khả thi**: còn cần các đường đi có đủ dung lượng dư để truyền luồng bù.

## 3. Tạo mạng phụ trợ với SS và TT

Sau khi thay mọi dung lượng cung gốc thành \(U-L\), thêm hai đỉnh mới:

- **SS**: siêu nguồn (*super source*).
- **TT**: siêu đích (*super sink*).

Với từng đỉnh v trong mạng gốc:

- Nếu \(b(v)>0\), thêm cung **\(\boxed{SS\to v}\)** với sức chứa b(v).
- Nếu \(b(v)<0\), thêm cung **\(\boxed{v\to TT}\)** với sức chứa −b(v).
- Nếu b(v)=0, không thêm cung điều chỉnh cho v.

Đặt:

\[
\boxed{B=\sum_{b(v)>0} b(v).}
\]

Chạy **max flow từ SS tới TT** trên mạng phụ trợ. Kết luận:

\[
\boxed{\text{Circulation khả thi}\iff\text{MaxFlow}(SS,TT)=B.}
\]

Tương đương: **mọi cung rời SS phải được bão hòa**. Do \(\sum b=0\), tổng dung lượng cung vào TT cũng bằng B. Nếu toàn bộ B được gửi đi, các cung điều chỉnh ở cả hai phía đều được sử dụng hết.

### Vì sao b dương nối từ SS?

Ở một đỉnh v có b(v)>0, ta cần:

\[
out_x(v)-in_x(v)=b(v).
\]

Trong mạng phụ trợ, nếu ta đưa **b(v) đơn vị vào v từ SS**, bảo toàn luồng tổng tại v buộc:

\[
in_x(v)+b(v)=out_x(v).
\]

Suy ra đúng \(out_x-in_x=b(v)\).

Tương tự, khi b(v)<0, thêm cạnh v→TT với luồng −b(v) để:

\[
in_x(v)=out_x(v)+(-b(v)),
\]

tức \(out_x-in_x=b(v)\).

Do đó quy tắc SS→v khi b dương và v→TT khi b âm là **kết quả của phương trình**, không phải một quy ước tùy ý.

### Một bảng dấu ngắn gọn

| b(v) | Ý nghĩa của các cận dưới | Luồng bù cần thiết | Cung phụ trợ |
|---:|---|---|---|
| +3 | Đã vào dư 3 | Phải gửi bù ra ngoài 3 | SS→v, capacity 3 |
| −2 | Đã ra dư 2 | Phải nhận bù vào 2 | v→TT, capacity 2 |
| 0 | Phần bắt buộc cân bằng | out_x=in_x | Không thêm cung |

**Sai dấu là lỗi rất phổ biến.** Một số tài liệu đặt \(\Delta(v)=out_L-in_L=-b(v)\), khi ấy chiều SS/TT được mô tả bằng \(\Delta\) với điều kiện ngược. Không có mâu thuẫn nếu công thức nhất quán. Bài này luôn dùng **b=in_L−out_L**.

## 4. Chứng minh tính tương đương hai chiều

Cần chứng minh phương pháp trên không bỏ mất nghiệm và không tạo nghiệm giả.

### Chiều 1: nếu có tuần hoàn f hợp lệ thì gửi được B

Giả sử có một luồng f thỏa toàn bộ \([L,U]\) và cân bằng ở mọi đỉnh. Đặt \(x=f-L\). Khi ấy:

\[
0\le x_e\le U_e-L_e.
\]

Với mỗi v, phương trình đã dẫn xuất cho:

\[
out_x(v)-in_x(v)=b(v).
\]

Ta đặt luồng trên các cung phụ trợ SS→v đúng b(v) khi b>0, và v→TT đúng −b(v) khi b<0. Khi đó **mọi đỉnh gốc đều cân bằng trong mạng phụ trợ**.

Tổng luồng rời SS bằng B. Vậy tồn tại một luồng SS→TT có giá trị B. Vì tổng sức chứa rời SS chỉ bằng B, max flow không thể lớn hơn B, nên **MaxFlow=B**.

### Chiều 2: nếu gửi được B thì có tuần hoàn f hợp lệ

Giả sử max flow phụ trợ đạt B. Tất cả cung rời SS phải bão hòa, và vì tổng vào TT cũng B, tất cả cung điều chỉnh ở phía TT cũng bão hòa.

Gọi x_e là luồng gửi trên cung gốc sau khi giảm sức chứa xuống \(U-L\). Mỗi x thỏa \(0\le x\le U-L\). Bảo toàn ở v trong mạng phụ trợ với các cung SS/TT đã bão hòa cho đúng:

\[
out_x(v)-in_x(v)=b(v).
\]

Đặt \(f_e=L_e+x_e\), ta có:

\[
L_e\le f_e\le U_e
\]

và:

\[
in_f(v)-out_f(v)
=
b(v)+in_x(v)-out_x(v)
=
b(v)-b(v)=0.
\]

Vậy f là một **tuần hoàn hợp lệ** của mạng gốc.

Hai chiều chứng minh **điều kiện MaxFlow=B vừa cần vừa đủ**.

### Nếu B=0 thì sao?

Nếu tất cả b(v)=0, các cận dưới **đã cân bằng** tại mọi đỉnh. Chọn \(x_e=0\) cho mọi cung, tức \(f_e=L_e\), là một nghiệm tuần hoàn ngay lập tức.

Mạng phụ trợ không cần gửi luồng nào; **MaxFlow=0=B**, nên kết quả phải là khả thi. Không được coi “max flow bằng 0” là thất bại một cách máy móc.

## 5. Ví dụ khả thi: bốn đỉnh và bảy cung

Xét mạng có hướng với các đỉnh 0,1,2,3. Các cung được liệt kê **theo đúng thứ tự** để đối chiếu luồng phục hồi trong Java:

| STT | Cung | Cận dưới L | Cận trên U | Dung lượng dư U−L |
|---:|---|---:|---:|---:|
| 1 | 0→1 | 3 | 5 | 2 |
| 2 | 1→2 | 1 | 4 | 3 |
| 3 | 2→0 | 1 | 3 | 2 |
| 4 | 1→3 | 1 | 3 | 2 |
| 5 | 3→0 | 1 | 4 | 3 |
| 6 | 0→2 | 0 | 2 | 2 |
| 7 | 2→3 | 0 | 2 | 2 |

Mạng có nhiều đường đi vòng về 0 nên có khả năng bù các luồng bắt buộc.

### Bước 1 — Chọn trước f=L

Nếu tạm đặt f bằng cận dưới trên mọi cung:

~~~text
f_lower = [3, 1, 1, 1, 1, 0, 0]
~~~

Tại từng đỉnh:

- Đỉnh 0: vào \(L(2,0)+L(3,0)=1+1=2\), ra \(L(0,1)+L(0,2)=3+0=3\). Vậy **b(0)=−1**.
- Đỉnh 1: vào \(L(0,1)=3\), ra \(L(1,2)+L(1,3)=1+1=2\). Vậy **b(1)=+1**.
- Đỉnh 2: vào \(L(1,2)+L(0,2)=1\), ra \(L(2,0)+L(2,3)=1\). Vậy **b(2)=0**.
- Đỉnh 3: vào \(L(1,3)+L(2,3)=1\), ra \(L(3,0)=1\). Vậy **b(3)=0**.

Tóm tắt:

~~~text
b = [-1, +1, 0, 0]
B = 1
~~~

### Bước 2 — Dựng mạng phụ trợ

Các cung gốc có dung lượng bằng cột U−L. Thêm:

~~~text
SS -> 1   capacity 1    // b(1)=+1
0  -> TT  capacity 1    // b(0)=-1
~~~

Muốn gửi một đơn vị từ SS tới TT, mạng phải tìm đường từ 1 tới 0 trên **các cung dư**. Một đường hợp lệ là:

~~~text
SS --1--> 1 --1--> 2 --1--> 0 --1--> TT
~~~

Dung lượng dư của 1→2 là 3 và của 2→0 là 2, nên có thể truyền một đơn vị. Do đó **max flow phụ trợ đạt B=1**, tức có nghiệm tuần hoàn.

### Bước 3 — Phục hồi f=L+x

Chọn luồng bù \(x(1,2)=1\), \(x(2,0)=1\), các x khác bằng 0. Khi đó:

~~~text
f = [3, 2, 2, 1, 1, 0, 0]
~~~

Kiểm tra tại từng đỉnh:

| Đỉnh | Tổng f vào | Tổng f ra | Kết luận |
|---:|---:|---:|---|
| 0 | 2+1=3 | 3+0=3 | Cân bằng |
| 1 | 3 | 2+1=3 | Cân bằng |
| 2 | 2+0=2 | 2+0=2 | Cân bằng |
| 3 | 1+0=1 | 1 | Cân bằng |

Mọi f cũng nằm trong đoạn \([L,U]\) của cung tương ứng. Đây là một **chứng cứ nghiệm cụ thể**: không chỉ tuyên bố tồn tại mà còn chỉ ra lượng luồng trên từng cung.

### Có thể có nghiệm khác không?

Có. Ta cũng có thể đưa x theo đường **1→3→0** nếu dung lượng dư cho phép. Khi ấy f trên các cung khác sẽ thay đổi nhưng mọi điều kiện vẫn đúng.

Vì không có hàm mục tiêu, **không cần cố chọn nghiệm này hay nghiệm kia**. Kết quả in trong Java phản ánh thứ tự duyệt cung của Dinic, và cả hai dạng đều là đáp án đúng nếu thỏa cận/bảo toàn.

## 6. Ví dụ vô nghiệm và cách nhận ra nhanh

Xét mạng hai đỉnh:

~~~text
0 --[2,2]--> 1
~~~

Ta có \(b=[-2,+2]\), tổng B=2. Cung gốc sau khi trừ cận dưới có dung lượng \(U-L=0\), và các cung phụ trợ là:

~~~text
SS -> 1  capacity 2
0  -> TT capacity 2
~~~

**Không có đường đi từ đỉnh 1 về đỉnh 0** trong mạng dư, nên SS không thể gửi luồng tới TT. Kết quả:

\[
\boxed{\text{MaxFlow}=0 < B=2}.
\]

Do đó **không có tuần hoàn khả thi**.

Điểm dễ nhầm: mạng này có thể gửi **hai đơn vị luồng từ 0 tới 1** trong một bài **luồng s–t**, nhưng nó **không** là tuần hoàn. Bài tuần hoàn yêu cầu **bảo toàn ở cả đỉnh 0 và 1**, trong khi bài s–t cho phép nguồn có luồng ra ròng và đích có luồng vào ròng.

### Chứng chỉ thất bại qua đường cắt

Nếu max flow phụ trợ không đạt B, định lý **max-flow min-cut** cho một đường cắt phụ trợ có dung lượng nhỏ hơn B. Nó là chứng cứ không có đủ khả năng đưa luồng bù từ các đỉnh cần thoát b sang các đỉnh cần nhận b.

Một cách nhận biết bằng bất đẳng thức tập đỉnh: với \(X\subseteq V\), đặt:

- \(L(\delta^-(X))\): tổng cận dưới của các cung **đi vào X từ ngoài X**.
- \(U(\delta^+(X))\): tổng cận trên của các cung **đi ra X tới ngoài X**.

Trong tuần hoàn không có cung–cầu ngoài, để cân bằng X phải có:

\[
\boxed{L(\delta^-(X))\le U(\delta^+(X)).}
\]

Nếu lượng bắt buộc đi vào X đã vượt quá khả năng tối đa đi ra X, **không thể có nghiệm**, bất kể những cung nội bộ X được điều chỉnh thế nào.

Ví dụ vô nghiệm với X={1}: cận dưới đi vào X bằng 2, còn cận trên đi ra X bằng 0, nên \(2\le0\) là sai. Đây là một chứng cứ vô nghiệm dễ hiểu không cần liệt kê mọi bộ luồng.

Cũng cần kiểm tra chiều đối ngẫu (hoặc lấy tập bù của X). Hệ bất đẳng thức đường cắt cho mọi X là nền của định lý tồn tại **feasible circulation**.

## 7. Có cung–cầu ngoài ở các đỉnh: quy ước và công thức tổng quát

Một biến thể phổ biến yêu cầu tại mỗi đỉnh v:

\[
\boxed{in_f(v)-out_f(v)=d(v).}
\]

Trong bài học này:

- **d(v)>0**: đỉnh **nhận ròng** d(v) đơn vị (*demand/sink of supply*).
- **d(v)<0**: đỉnh **gửi ròng** −d(v) đơn vị (*supply/source of supply*).
- **d(v)=0**: đỉnh trung chuyển, bảo toàn bình thường.

Vì mỗi cung đóng góp một lần luồng vào và một lần luồng ra trên toàn mạng, **điều kiện bắt buộc** là:

\[
\boxed{\sum_v d(v)=0.}
\]

Nếu tổng d khác 0 và không có nguồn/sink bên ngoài mô hình, **không có nghiệm**. Có thể báo đầu vào mâu thuẫn trước khi chạy max flow.

### Sửa phương trình cho luồng bù

Với f=L+x:

\[
in_f(v)-out_f(v)=b(v)+in_x(v)-out_x(v)=d(v).
\]

Suy ra:

\[
\boxed{out_x(v)-in_x(v)=b(v)-d(v).}
\]

Đặt:

\[
\boxed{a(v)=b(v)-d(v).}
\]

**Quy tắc phụ trợ tổng quát** giống hệt trường hợp tuần hoàn:

- Nếu **a(v)>0**: thêm **SS→v** với capacity a(v).
- Nếu **a(v)<0**: thêm **v→TT** với capacity −a(v).
- Nếu a(v)=0: không thêm cạnh.
- Tổng cần bão hòa là \(\sum_{a(v)>0}a(v)\).

Khi tất cả d=0, ta có a=b và trở về thuật toán tuần hoàn thuần túy.

### Ví dụ mở rộng từ mạng 4 đỉnh

Giữ nguyên b=[−1,+1,0,0], nhưng yêu cầu:

~~~text
d = [+1, -1, 0, 0]
~~~

Đỉnh 0 cần **nhận ròng 1**, đỉnh 1 cần **gửi ròng 1**. Khi đó:

~~~text
a = b - d = [-2, +2, 0, 0]
B = 2
~~~

Cần đẩy **hai đơn vị luồng bù** từ 1 tới 0. Đường dư 1→2→0 có sức chứa nhỏ nhất là 2, nên đạt được B=2 và có nghiệm:

~~~text
f = [3, 3, 3, 1, 1, 0, 0]
~~~

Kiểm tra:

- Đỉnh 0: vào \(3+1=4\), ra \(3\), nên **in−out=+1**.
- Đỉnh 1: vào \(3\), ra \(3+1=4\), nên **in−out=−1**.
- Đỉnh 2 và 3 cân bằng.

**Đừng đảo nghĩa d khi đọc tài liệu khác.** Có tài liệu định nghĩa d dương là **supply** (out−in), trái với định nghĩa của bài này. Muốn áp dụng công thức phải xác định rõ **d là in−out hay out−in** trước.

## 8. Phục hồi luồng từ đồ thị dư

Trong một cài đặt max flow như Dinic, mỗi cung phụ trợ được biểu diễn bằng **cung thuận** với sức chứa còn lại và **cung ngược** lưu quyền hủy phần luồng đã gửi.

Với cung gốc e có sức chứa dư ban đầu:

\[
C_e=U_e-L_e,
\]

gọi \(\operatorname{remaining}_e\) là dung lượng còn lại trên **cung thuận gốc** sau max flow. Lượng luồng bù là:

\[
\boxed{x_e=C_e-\operatorname{remaining}_e.}
\]

Luồng phục hồi:

\[
\boxed{f_e=L_e+C_e-\operatorname{remaining}_e.}
\]

**Quan trọng:** phải lưu **tham chiếu đúng cung thuận của từng cung gốc**. Nếu mạng có **hai cung song song u→v**, không được cố truy vấn một ô `capacity[u][v]` rồi gán cùng một lưu lượng cho cả hai cung. Mỗi cung có **một vị trí riêng** trong adjacency list của mạng dư.

### Cung phụ trợ không phải dữ liệu đầu ra

Cung SS→v, v→TT phục vụ **điều chỉnh cân bằng**, không phải một cung của mạng gốc. Khi xuất nghiệm, chỉ in **f trên đúng E cung gốc**, theo thứ tự đầu vào. Không thêm hai đỉnh SS/TT vào tập đỉnh mạng mà người dùng nhận được.

### Nếu max flow không đạt B

Nếu phụ trợ không gửi đủ B, phần x đang có **không** thể bảo đảm ràng buộc gốc. **Không được xuất \(f=L+x\) như một nghiệm hợp lệ** trong trường hợp thất bại.

Chương trình trong bài trả `feasible=false`, `flows=null`, kèm `required` và `pushed` để giải thích kiểm tra. Đó là kết luận **không có nghiệm**, không phải lỗi của Dinic.

## 9. Chương trình Java 17: tuần hoàn cận dưới bằng Dinic

Mã sau cài một bộ giải cho cả hai trường hợp:

- `circulation(n, arcs)`: tuần hoàn thuần túy, **d=0**.
- `circulation(n, arcs, demand)`: yêu cầu **in−out=d[v]**, với \(\sum d=0\).
- Có thể có **cạnh song song** hoặc **self-loop**.
- Sức chứa và luồng dùng **`long`**, số học quan trọng dùng `Math.addExact`, `Math.subtractExact`, `Math.negateExact` để báo tràn thay vì trả lời sai.
- Mỗi cung gốc được giữ qua **EdgeHandle** để phục hồi đúng luồng kể cả khi có nhiều cung cùng cặp đỉnh.
- Mạng dư tự thêm cung ngược với sức chứa đầu 0; riêng self-loop cần tính **chỉ số cung ngược** cẩn thận vì cung thuận/ngược nằm trong **cùng một danh sách kề**.
- Dinic dùng BFS xây level graph và DFS gửi blocking flow. **DFS gửi luồng là đệ quy**; với đồ thị đường dài rất lớn cần bản Dinic lặp/giới hạn call stack phù hợp.
- Cài đặt kiểm tra 0≤L≤U, đầu mút hợp lệ, tổng nhu cầu d bằng 0 và định dạng mạng không có đỉnh ngoài miền.
- **N=0 với E=0** được xem là tuần hoàn rỗng khả thi; mảng kết quả rỗng.

Lưu tệp **LowerBoundCirculationDemo.java**:

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

public class LowerBoundCirculationDemo {
    record BoundEdge(int from, int to, long lower, long upper) {}
    record EdgeHandle(int from, int index, long initialCapacity) {}
    record Result(
        boolean feasible,
        long[] flows,
        long[] lowerNet,
        long required,
        long pushed
    ) {}

    static final class ResidualEdge {
        final int to;
        final int reverseIndex;
        long remaining;

        ResidualEdge(int to, int reverseIndex, long remaining) {
            this.to = to;
            this.reverseIndex = reverseIndex;
            this.remaining = remaining;
        }
    }

    static final class Dinic {
        final List<List<ResidualEdge>> graph;
        final int[] level;
        final int[] next;

        Dinic(int vertices) {
            graph = new ArrayList<>();
            for (int v = 0; v < vertices; v++) {
                graph.add(new ArrayList<>());
            }
            level = new int[vertices];
            next = new int[vertices];
        }

        EdgeHandle addEdge(int from, int to, long capacity) {
            if (capacity < 0) {
                throw new IllegalArgumentException("negative capacity");
            }

            int forwardIndex = graph.get(from).size();
            int reverseIndex = graph.get(to).size();

            // For a self-loop, adding forward also grows the
            // SAME adjacency list before adding reverse.
            if (from == to) {
                reverseIndex++;
            }

            ResidualEdge forward =
                new ResidualEdge(to, reverseIndex, capacity);
            ResidualEdge reverse =
                new ResidualEdge(from, forwardIndex, 0L);

            graph.get(from).add(forward);
            graph.get(to).add(reverse);
            return new EdgeHandle(from, forwardIndex, capacity);
        }

        private boolean bfs(int source, int sink) {
            Arrays.fill(level, -1);
            ArrayDeque<Integer> queue = new ArrayDeque<>();
            queue.add(source);
            level[source] = 0;

            while (!queue.isEmpty()) {
                int u = queue.remove();
                for (ResidualEdge e : graph.get(u)) {
                    if (e.remaining > 0 && level[e.to] == -1) {
                        level[e.to] = level[u] + 1;
                        queue.add(e.to);
                    }
                }
            }
            return level[sink] != -1;
        }

        private long dfs(int u, int sink, long limit) {
            if (u == sink) {
                return limit;
            }
            List<ResidualEdge> adjacent = graph.get(u);

            for (; next[u] < adjacent.size(); next[u]++) {
                ResidualEdge e = adjacent.get(next[u]);
                if (e.remaining == 0
                        || level[e.to] != level[u] + 1) {
                    continue;
                }

                long sent = dfs(
                    e.to, sink, Math.min(limit, e.remaining)
                );
                if (sent > 0) {
                    e.remaining -= sent;
                    ResidualEdge rev =
                        graph.get(e.to).get(e.reverseIndex);
                    rev.remaining = Math.addExact(rev.remaining, sent);
                    return sent;
                }
            }
            return 0L;
        }

        long maxFlow(int source, int sink) {
            long value = 0L;
            while (bfs(source, sink)) {
                Arrays.fill(next, 0);
                while (true) {
                    long sent = dfs(source, sink, Long.MAX_VALUE);
                    if (sent == 0) {
                        break;
                    }
                    value = Math.addExact(value, sent);
                }
            }
            return value;
        }

        long remaining(EdgeHandle h) {
            return graph.get(h.from()).get(h.index()).remaining;
        }
    }

    static Result circulation(
        int n, List<BoundEdge> arcs
    ) {
        if (n < 0 || n > Integer.MAX_VALUE - 2) {
            throw new IllegalArgumentException("invalid vertex count");
        }
        return circulation(n, arcs, new long[n]);
    }

    // Positive demand[v] means required net INflow at vertex v.
    static Result circulation(
        int n, List<BoundEdge> arcs, long[] demand
    ) {
        Objects.requireNonNull(arcs, "arcs");
        Objects.requireNonNull(demand, "demand");
        if (n < 0 || n > Integer.MAX_VALUE - 2
                || demand.length != n) {
            throw new IllegalArgumentException("invalid vertex count/demand");
        }

        long demandSum = 0L;
        for (long d : demand) {
            demandSum = Math.addExact(demandSum, d);
        }
        if (demandSum != 0L) {
            throw new IllegalArgumentException(
                "sum of demands must be zero"
            );
        }

        int superSource = n;
        int superSink = n + 1;
        Dinic network = new Dinic(n + 2);
        long[] lowerNet = new long[n];
        EdgeHandle[] handles = new EdgeHandle[arcs.size()];

        for (int i = 0; i < arcs.size(); i++) {
            BoundEdge e = arcs.get(i);
            if (e == null || e.from() < 0 || e.from() >= n
                    || e.to() < 0 || e.to() >= n) {
                throw new IllegalArgumentException("invalid edge endpoint");
            }
            if (e.lower() < 0L || e.upper() < e.lower()) {
                throw new IllegalArgumentException(
                    "invalid lower/upper bound"
                );
            }

            long extraCapacity =
                Math.subtractExact(e.upper(), e.lower());
            handles[i] = network.addEdge(
                e.from(), e.to(), extraCapacity
            );

            // b(v) = sum of IN lower - sum of OUT lower.
            lowerNet[e.from()] = Math.subtractExact(
                lowerNet[e.from()], e.lower()
            );
            lowerNet[e.to()] = Math.addExact(
                lowerNet[e.to()], e.lower()
            );
        }

        long required = 0L;
        for (int v = 0; v < n; v++) {
            // a(v) = b(v) - demand(v).
            long a = Math.subtractExact(lowerNet[v], demand[v]);
            if (a > 0L) {
                network.addEdge(superSource, v, a);
                required = Math.addExact(required, a);
            } else if (a < 0L) {
                network.addEdge(v, superSink, Math.negateExact(a));
            }
        }

        long pushed = network.maxFlow(superSource, superSink);
        if (pushed != required) {
            // Never publish a partially corrected lower-bound flow.
            return new Result(
                false, null, lowerNet.clone(), required, pushed
            );
        }

        long[] flows = new long[arcs.size()];
        for (int i = 0; i < arcs.size(); i++) {
            BoundEdge original = arcs.get(i);
            EdgeHandle h = handles[i];
            long used = Math.subtractExact(
                h.initialCapacity(), network.remaining(h)
            );
            flows[i] = Math.addExact(original.lower(), used);
        }
        return new Result(
            true, flows, lowerNet.clone(), required, pushed
        );
    }

    // Independent check of the original per-vertex equation.
    static long[] netInMinusOut(
        int n, List<BoundEdge> arcs, long[] flows
    ) {
        if (flows == null || flows.length != arcs.size()) {
            throw new IllegalArgumentException("invalid flow vector");
        }
        long[] net = new long[n];
        for (int i = 0; i < arcs.size(); i++) {
            BoundEdge e = arcs.get(i);
            long f = flows[i];
            if (f < e.lower() || f > e.upper()) {
                throw new IllegalArgumentException("flow violates bounds");
            }
            net[e.from()] = Math.subtractExact(net[e.from()], f);
            net[e.to()] = Math.addExact(net[e.to()], f);
        }
        return net;
    }

    public static void main(String[] args) {
        List<BoundEdge> arcs = List.of(
            new BoundEdge(0, 1, 3, 5),
            new BoundEdge(1, 2, 1, 4),
            new BoundEdge(2, 0, 1, 3),
            new BoundEdge(1, 3, 1, 3),
            new BoundEdge(3, 0, 1, 4),
            new BoundEdge(0, 2, 0, 2),
            new BoundEdge(2, 3, 0, 2)
        );

        Result ordinary = circulation(4, arcs);
        System.out.println("Feasible circulation: "
            + ordinary.feasible());
        System.out.println("Lower net in-out: "
            + Arrays.toString(ordinary.lowerNet()));
        System.out.println("Required auxiliary flow: "
            + ordinary.required());
        System.out.println("Actual auxiliary flow: "
            + ordinary.pushed());
        System.out.println("Recovered edge flows: "
            + Arrays.toString(ordinary.flows()));
        System.out.println("Node net in-out: "
            + Arrays.toString(
                netInMinusOut(4, arcs, ordinary.flows())
            ));

        long[] demand = {1, -1, 0, 0};
        Result withDemand = circulation(4, arcs, demand);
        System.out.println("Demand variant feasible: "
            + withDemand.feasible());
        System.out.println("Demand variant edge flows: "
            + Arrays.toString(withDemand.flows()));
        System.out.println("Demand variant net in-out: "
            + Arrays.toString(
                netInMinusOut(4, arcs, withDemand.flows())
            ));

        Result impossible = circulation(2, List.of(
            new BoundEdge(0, 1, 2, 2)
        ));
        System.out.println("Impossible circulation feasible: "
            + impossible.feasible());
        System.out.println("Impossible auxiliary flow: "
            + impossible.pushed() + " / " + impossible.required());

        Result loop = circulation(1, List.of(
            new BoundEdge(0, 0, 2, 2)
        ));
        System.out.println("Self-loop feasible: " + loop.feasible());
        System.out.println("Self-loop flow: "
            + Arrays.toString(loop.flows()));

        Result zeroLower = circulation(3, List.of(
            new BoundEdge(0, 1, 0, 7),
            new BoundEdge(1, 2, 0, 4)
        ));
        System.out.println("Zero-lower feasible: "
            + zeroLower.feasible());
        System.out.println("Zero-lower flow: "
            + Arrays.toString(zeroLower.flows()));

        System.out.println("Empty network feasible: "
            + circulation(0, List.of()).feasible());

        try {
            circulation(2, List.of(new BoundEdge(0, 1, 3, 2)));
        } catch (IllegalArgumentException ex) {
            System.out.println("Invalid bound rejected: "
                + ex.getMessage());
        }
    }
}
~~~

Biên dịch/chạy bằng **JDK 17 trở lên**:

~~~bash
javac LowerBoundCirculationDemo.java
java LowerBoundCirculationDemo
~~~

**Stdout kỳ vọng chính xác theo thứ tự cung và cách duyệt Dinic trên:**

~~~text
Feasible circulation: true
Lower net in-out: [-1, 1, 0, 0]
Required auxiliary flow: 1
Actual auxiliary flow: 1
Recovered edge flows: [3, 2, 2, 1, 1, 0, 0]
Node net in-out: [0, 0, 0, 0]
Demand variant feasible: true
Demand variant edge flows: [3, 3, 3, 1, 1, 0, 0]
Demand variant net in-out: [1, -1, 0, 0]
Impossible circulation feasible: false
Impossible auxiliary flow: 0 / 2
Self-loop feasible: true
Self-loop flow: [2]
Zero-lower feasible: true
Zero-lower flow: [0, 0]
Empty network feasible: true
Invalid bound rejected: invalid lower/upper bound
~~~

### Đọc code theo phép biến đổi toán học

**Lưu từng cung riêng.** `BoundEdge` biểu diễn một cung có hướng và hai cận. `EdgeHandle` lưu vị trí của **cung thuận** trong mạng dư. Điều này đặc biệt quan trọng với cung song song cùng cặp đỉnh và self-loop.

**Mạng dư dùng sức chứa U−L.** Cung thuận có `remaining=U-L`, cung ngược đầu 0. Sau khi max flow hoàn tất, `used=(U-L)-remaining`; từ đó phục hồi `f=L+used`.

**Bảng cân bằng b.** Khi duyệt cung u→v cận dưới L, mã **trừ L khỏi b[u]**, **cộng L vào b[v]**. Vì vậy b chính xác là `sumLowerIn-sumLowerOut`, không bị đảo dấu.

**Nhu cầu ngoài d.** Mã đặt `a=b-demand`. Đỉnh a dương nhận cung SS→v; a âm phát cung v→TT. Khi d=0, a=b.

**Điều kiện khả thi.** `pushed==required` là điều kiện đủ và cần; kết quả thất bại trả **không có vector f**, không phát tán nghiệm tạm thời.

**Cộng số exact.** Tính tổng dung lượng, cận dưới và khôi phục kết quả bằng toán tử có kiểm tra. Nếu dữ liệu đòi số học lớn hơn long, chương trình **không âm thầm cho kết quả tràn**; cần chuyển sang kiểu lớn hơn hoặc áp giới hạn đầu vào phù hợp.

**Self-loop.** Mạng gốc có thể có cung u→u. Nó vừa vào vừa ra u nên không ảnh hưởng b. Trong mạng dư, cung thuận và cung ngược của self-loop nằm **cùng adjacency list**; `addEdge` điều chỉnh `reverseIndex` để hai cung trỏ đúng tới nhau. Bỏ qua chi tiết này dễ làm sai mạng dư ở trường hợp biên.

**Kiểm tra nghiệm.** `netInMinusOut` hoàn toàn không dùng SS/TT hay b; nó tính lại tổng vào–ra trên các cung gốc, đồng thời kiểm tra `L<=f<=U`. Khi d=0, mảng phải toàn 0; khi có demand, mảng phải bằng d.

## 10. Dinic trên mạng phụ trợ: tính đúng và hạn chế

Mạng phụ trợ có \(N+2\) đỉnh và tối đa \(E+N\) cung thuận mới, ngoài các cung ngược trong biểu diễn residual. Từng cung gốc được biến đổi thành sức chứa không âm U−L, nên có thể dùng **bất kỳ thuật toán max flow đúng** (Dinic, Edmonds–Karp, Push–Relabel, ...).

Mã minh họa dùng Dinic:

1. **BFS** xây mức `level[v]` trên các cung dư có `remaining>0`.
2. **DFS** chỉ đi tới đỉnh có level lớn hơn đúng 1, để gửi luồng trong mạng mức.
3. Khi hết đường tăng trong mạng mức, BFS mới.
4. Dừng khi TT không còn tới được từ SS trong mạng dư.

Giá trị `maxFlow` là lượng đã gửi từ SS tới TT. Nếu bằng B, khôi phục nghiệm tuần hoàn; nếu nhỏ hơn B, vô nghiệm theo chứng minh phần 4.

### Vì sao reverse edge quan trọng?

Một đường tăng trong giai đoạn đầu có thể dùng cung mà về sau cần **giảm lại lượng đã gửi** để tạo đường tăng khác. Cung ngược cho phép hủy một phần luồng đã đưa đi, bảo đảm thuật toán không “kẹt” vì quyết định đường tăng ban đầu.

Đối với cung gốc có cận dưới, **quyền giảm** trên phần x đã gửi tương ứng với dung lượng **x**, không phải toàn bộ f. Ta không được dùng cung ngược để giảm f xuống **dưới L**. Việc giải trên x trong \([0,U-L]\) tự bảo đảm giới hạn này.

### Độ phức tạp

Gọi \(V'=N+2\) và \(E'=E+O(N)\) là số **cung thuận** của mạng phụ trợ (chưa kể các cung ngược trong residual).

- Tính b và dựng mạng phụ trợ: **O(N+E)**.
- Dinic có cận tổng quát **O(V'^2 E')** trên mạng sức chứa tổng quát.
- Phục hồi E giá trị f: **O(E)**.

Vì vậy cận xấu nhất thông dụng của pipeline:

\[
\boxed{O((N+2)^2(E+N))}
\]

theo Dinic tổng quát, và bộ nhớ đồ thị dư, level, current-edge và danh sách kết quả **O(N+E)**. Một số loại mạng/capacity có cận tốt hơn, nhưng không nên tự tuyên bố O(E√V) trong mọi trường hợp khi không có giả thiết đặc biệt.

**DFS đệ quy của Dinic** có thể sâu tới O(N), nên trên JVM cần cân nhắc stack. Java có thể ném `StackOverflowError` cho mạng rất dài dù độ phức tạp lý thuyết đúng; phiên bản Dinic lặp hoặc kỹ thuật max flow khác phù hợp sẽ an toàn hơn ở quy mô cực lớn.

**Số học:** B và giá trị luồng có thể vượt phạm vi 64-bit nếu mạng quá lớn hoặc có nhiều cung dung lượng gần `Long.MAX_VALUE`; mã ném lỗi nếu tràn. Không dùng sentinel “INF” không được chứng minh cho tổng capacity.

## 11. Luồng từ s tới t có cận dưới: thêm cạnh ngược t→s

Bài toán luồng s–t với cận dưới khác tuần hoàn thuần túy:

- Có hai đỉnh đặc biệt s,t.
- Các đỉnh khác phải bảo toàn luồng.
- Giá trị luồng thường định nghĩa:
  \[
  F=out_f(s)-in_f(s)=in_f(t)-out_f(t).
  \]
- Mọi cung gốc vẫn thỏa \(L_e\le f_e\le U_e\).

Muốn dùng phép giảm về **feasible circulation**, ta có thể thêm một **cung nhân tạo**:

\[
\boxed{t\to s,\quad [0,M]},
\]

với M là một **giới hạn trên hữu hạn đủ lớn** của giá trị F không âm cần xét. Khi tìm một tuần hoàn trên mạng mở rộng, luồng chạy trên cung t→s đóng vai trò **hoàn trả** đúng F để cân bằng s và t.

### Vì sao cách này đúng?

Tại s, trước khi thêm cạnh nhân tạo, luồng gốc có **out−in=F**. Cạnh t→s đưa F vào s, nên sau khi thêm:

\[
in_{\text{mở rộng}}(s)=out_{\text{mở rộng}}(s).
\]

Tại t, luồng gốc có **in−out=F**. Cạnh nhân tạo lấy F đơn vị ra t, nên t cũng cân bằng. Các đỉnh khác vốn đã bảo toàn.

Chiều ngược cũng đúng: từ một tuần hoàn trên mạng có t→s, bỏ cạnh nhân tạo ta có một luồng s–t gốc với giá trị **F bằng luồng trên t→s**, không âm vì cận dưới của cung nhân tạo bằng 0.

**Giới hạn của phép giảm này:** nó chỉ cho nghiệm s–t với **F≥0**. Nếu mô hình cho phép/quan tâm giá trị F âm (thực chất luồng ngược từ t về s), phải xử lý riêng hoặc biến đổi lại bài toán.

### Chọn M thế nào?

Không nên dùng bừa `Long.MAX_VALUE` rồi cộng tổng capacity không kiểm tra overflow. Với cận gốc không âm, mọi giá trị s–t không âm đều thỏa:

\[
F\le \sum_{e:\,from(e)=s} U_e,
\]

vì \(F=out(s)-in(s)\le out(s)\). Do đó có thể chọn tổng cận trên cung đi ra s làm một M hợp lệ **nếu tính được trong miền số học**. Có thể chọn cận trên chặt hơn khi biết thêm điều kiện.

### Muốn tối đa hóa F sau khi tìm nghiệm khả thi

Việc thêm cạnh t→s và giải feasible circulation **chỉ tìm một luồng s–t hợp lệ**, **chưa chắc là luồng lớn nhất**.

Một quy trình hai pha đúng:

1. Thêm cung nhân tạo t→s [0,M] và giải tuần hoàn khả thi trên mạng mở rộng.
2. Nếu vô nghiệm, không có luồng s–t thỏa ràng buộc và F≥0 theo mô hình ấy.
3. Nếu khả thi, lưu `F0=f(t,s)` trên cung nhân tạo. Bỏ cung nhân tạo và **toàn bộ cung SS/TT phụ trợ** khỏi bài toán tối ưu tiếp theo.
4. Giữ luồng f hiện tại trên **các cung gốc**. Dựng **mạng dư theo chính luồng f có cận dưới**:
   - Cung thuận u→v có dung lượng **\(U_e-f_e\)**.
   - Cung ngược v→u có dung lượng **\(f_e-L_e\)**.
5. Chạy max flow tăng thêm từ **s tới t** trên mạng dư này. Nếu tăng được \(\Delta\), giá trị lớn nhất là **\(F_0+\Delta\)**, và các cung gốc vẫn không ra ngoài \([L,U]\).

**Tuyệt đối không để cung t→s nhân tạo hoặc cung SS/TT trong mạng dư của pha tối đa hóa**. Nếu còn chúng, đường tăng có thể thao tác với cạnh giả, tạo giá trị không phản ánh một luồng s–t hợp lệ của mạng gốc.

### Nếu yêu cầu F ít nhất A hoặc chính xác A

- **Ít nhất A≥0:** có thể đặt cận nhân tạo t→s là **[A,M]**, rồi giải tuần hoàn khả thi.
- **Chính xác A≥0:** đặt cạnh nhân tạo t→s là **[A,A]**.
- Sau đó kiểm tra như tuần hoàn cận dưới thông thường.

Với mô hình có cung–cầu ngoài tại các đỉnh, cần kết hợp đúng dấu và bảo toàn tại từng đỉnh; không được dùng cạnh t→s tùy tiện nếu định nghĩa F/demand khác đã thay đổi.

## 12. Điều kiện cut tổng quát và chứng chỉ vô nghiệm

Với ràng buộc cung–cầu theo quy ước:

\[
in_f(v)-out_f(v)=d(v),\quad \sum_vd(v)=0,
\]

lấy một tập đỉnh X. Mọi cung **nội bộ X** triệt tiêu khi cộng phương trình tại các đỉnh trong X. Do đó:

\[
d(X):=\sum_{v\in X}d(v)
=
f(\delta^-(X))-f(\delta^+(X)).
\]

Vì các cung đi vào X có cận dưới/trên, các cung đi ra X cũng vậy, ta có:

\[
\boxed{
L(\delta^-(X))-U(\delta^+(X))
\le d(X)
\le
U(\delta^-(X))-L(\delta^+(X)).
}
\]

Đây là điều kiện cần trực tiếp từ cận cung. Với mọi tập X cùng với \(\sum d=0\) và cận hợp lệ, hệ bất đẳng thức cut còn liên hệ với **định lý tồn tại tuần hoàn khả thi**; phép giảm về max flow cung cấp một cách kiểm tra hữu hạn và thuật toán để dựng nghiệm.

Trong trường hợp d=0, bất đẳng thức trái cho:

\[
L(\delta^-(X))\le U(\delta^+(X)),
\]

và bất đẳng thức phải cho:

\[
L(\delta^+(X))\le U(\delta^-(X)).
\]

Điều kiện cho X và cho tập bù X phản ánh nhau. Không phải chỉ cần kiểm một tập X tùy chọn là đủ kết luận khả thi; nhưng **chỉ một tập vi phạm** đã là chứng cứ vô nghiệm.

### Quan hệ với min-cut phụ trợ

Nếu max flow SS→TT không đạt B, thuật toán max-flow min-cut xác định một tập đỉnh phía SS của một cut tối thiểu. Cut này chứng minh mạng dư không có đủ khả năng chuyển luồng điều chỉnh từ những nơi thiếu cân bằng sang nơi dư cân bằng. Từ nó có thể suy ra một bất đẳng thức không thỏa trên một tập đỉnh gốc.

Đây là góc nhìn **đối ngẫu** với phép dựng nghiệm: một mặt max flow cho ta f hợp lệ; mặt khác min-cut cho ta lý do thiếu dung lượng và không tồn tại f nào.

## 13. Bài toán tuần hoàn có chi phí: đừng nhầm với feasible circulation

Có những bài thêm chi phí \(cost_e\) trên mỗi đơn vị luồng và muốn:

\[
\min\sum_e cost_e f_e
\]

dưới cùng các cận và phương trình bảo toàn. Đây là **minimum-cost circulation with lower bounds**, không chỉ là bài kiểm tra khả thi.

Vẫn có thể viết \(f=L+x\), và:

\[
\sum_e cost_e f_e
=
\underbrace{\sum_e cost_e L_e}_{\text{chi phí phần bắt buộc}}
+
\sum_e cost_e x_e.
\]

Bước trừ cận dưới vẫn đúng cho constraints. Nhưng khi giải cần dùng **min-cost flow/circulation** hoặc thuật toán tối ưu thích hợp thay vì Dinic max flow thông thường.

Dinic có thể tìm một nghiệm khả thi rất nhanh trên nhiều mạng, nhưng **không bảo đảm chi phí nhỏ nhất** nếu các cung có chi phí khác nhau. Nếu trong đồ thị chi phí có chu trình giảm chi phí, bài tối ưu còn cần xử lý tính tối ưu theo chi phí; điều đó khác với **chu trình âm của đường đi ngắn nhất** khi không có ràng buộc cận luồng.

### Tách ba câu hỏi

1. **Có nghiệm không?** → feasible circulation với cận dưới, SS/TT và max flow.
2. **Giá trị luồng s–t lớn nhất là bao nhiêu?** → feasible s–t dưới cận dưới + mạng dư tăng luồng như phần 11.
3. **Chi phí tổng thấp nhất là bao nhiêu?** → thuật toán min-cost flow/circulation, chú ý phần chi phí cố định \(\sum cost\cdot L\).

Không được thay mục tiêu số 2 hoặc 3 bằng kết quả `required` của mạng phụ trợ. `required=B` chỉ là tổng mất cân bằng cần bù do cận dưới/demand, **không phải** giá trị tối ưu của mạng gốc.

## 14. Tình huống biên và quyết định thiết kế

| Trường hợp | Cách xử lý |
|---|---|
| E=0, mọi d=0 | f rỗng/0 là tuần hoàn khả thi |
| N=0,E=0 | Theo ví dụ: tuần hoàn rỗng khả thi |
| Một cung L=U | Dung lượng dư 0, f bắt buộc bằng L |
| Tất cả cận dưới bằng 0, d=0 | f=0 khả thi, B=0 |
| Cận trên nhỏ hơn cận dưới | Đầu vào không hợp lệ; báo lỗi |
| Cận dưới âm | Không thuộc hợp đồng \(0\le L\le U\) của bài; phải mở rộng mô hình nếu muốn cho phép |
| Cung song song | Mỗi cung có cận/luồng riêng, không gộp ngầm |
| Self-loop u→u | Không ảnh hưởng cân bằng b; f vẫn phải nằm trong \([L,U]\) |
| Mạng không liên thông | Vẫn xử lý toàn mạng; mỗi thành phần phải tự thỏa các cân bằng có liên quan |
| Đỉnh cô lập, d=0 | Không cần gửi luồng, không gây vô nghiệm |
| Đỉnh cô lập, d≠0 | Thường vô nghiệm nếu không có cung vào/ra để đáp ứng yêu cầu |
| \(\sum d\ne0\) | Ràng buộc toàn mạng mâu thuẫn; từ chối |
| b=0 khắp nơi | Chọn x=0, f=L đã khả thi |
| MaxFlow SS→TT nhỏ hơn B | Không có nghiệm tuần hoàn; không phục hồi f như nghiệm |
| Nhiều nghiệm | Trả bất kỳ nghiệm nào thỏa cận và cân bằng |
| Dữ liệu trọng số chi phí | Không ảnh hưởng feasible, nhưng phải dùng thuật toán khác nếu tối ưu chi phí |
| Tổng dung lượng vượt long | Báo overflow hoặc dùng số học lớn hơn; không để tràn im lặng |

### Cạnh song song và tự nối

**Cung song song** có thể có cùng from/to nhưng cận khác nhau, nên cần được xem là những biến luồng riêng. Nếu tùy tiện gộp thành một cung với tổng cận mà sau đó bài yêu cầu xuất f cho từng cung gốc, ta không còn cách phục hồi phân bổ mà không giải một bài toán bổ sung.

**Self-loop u→u** có cùng một đóng góp vào và ra tại u. Nó **không giúp chuyển mất cân bằng giữa các đỉnh**, nhưng có thể có cận dưới dương như \([2,2]\) và vẫn không làm mạng vô nghiệm. Trường hợp này khác MST, nơi self-loop không bao giờ là cạnh của cây.

### Cẩn thận với chữ “INF”

Khi giảm bài s–t thành tuần hoàn, nhiều hướng dẫn thêm cạnh t→s với cận trên **INF**. Trong một chương trình số nguyên, INF là một giá trị **hữu hạn đã chọn**. Nếu chọn quá nhỏ, có thể loại nghiệm hợp lệ; nếu chọn quá lớn và tổng vượt kiểu số, có thể tạo overflow. Tốt hơn là xác định một **cận trên toán học** cho F trong bài cụ thể, rồi biểu diễn cận ấy an toàn.

## 15. Những lỗi thường gặp

1. **Nhầm luồng tuần hoàn với luồng s–t**, cho phép hai đỉnh có vào≠ra dù bài circulation yêu cầu mọi đỉnh cân bằng.
2. **Không trừ cận dưới** trước khi chạy max flow, rồi phục hồi f sai hoặc tạo cung không có capacity không âm.
3. **Tính b bằng outLower−inLower** nhưng vẫn dùng quy tắc SS→v khi b>0 dành cho quy ước ngược dấu.
4. **Cộng L hai lần** khi phục hồi f, hoặc quên cộng L và chỉ in x.
5. **Không lưu tham chiếu từng cung gốc**, khiến các cung song song bị gộp hoặc đọc nhầm cung ngược.
6. **So sánh max flow với số cung, với tổng cận trên hoặc với 0**, thay vì \(\sum_{b>0}b\) hoặc \(\sum_{a>0}a\).
7. **Bỏ các đỉnh cô lập khỏi mảng cân bằng**, làm dữ liệu d tại những đỉnh ấy bị quên.
8. **Đánh đồng b=0 với mạng không có cung**, trong khi b=0 chỉ nói phần L đã cân bằng.
9. **Đảo chiều SS và TT** mà không đổi định nghĩa b/d, tạo bài toán khác.
10. **Quên kiểm tra tổng d=0**, trong khi không cung nào có thể tạo/tiêu hủy tổng luồng ròng trên toàn mạng.
11. **Cho rằng maxflow dương là đủ**, dù cần bão hòa **toàn bộ** yêu cầu B.
12. **Xuất f=L+x khi maxflow<B**, dù x chưa bù đủ mất cân bằng.
13. **Không thêm reverse edges cho max flow**, khiến các quyết định đường tăng cũ không thể được hủy và thuật toán có thể sai.
14. **Bị lỗi chỉ số cung ngược với self-loop**, khi cung thuận và ngược cùng nằm trong một adjacency list.
15. **Không cho phép L=U**, dù đây là trường hợp cung có luồng bắt buộc chính xác.
16. **Cho rằng cạnh có capacity U−L=0 phải bị bỏ khỏi nghiệm gốc**, trong khi nó vẫn có thể mang f=L>0.
17. **Tự gộp cung song song** mà không giữ khả năng phục hồi các biến f ban đầu.
18. **Không kiểm tra tràn số** của b, d, B hoặc `f=L+used`.
19. **Quên bỏ cung t→s giả** trước pha tối đa hóa luồng s–t, dẫn tới augment sai.
20. **Cho rằng gửi được B là đã có max s–t**, nhầm nghiệm khả thi với nghiệm tối ưu.
21. **Không kiểm tra F≥0** khi dùng cạnh t→s cận [0,M]; nghiệm s–t có giá trị âm không nằm trong mô hình ấy.
22. **Nhầm nhu cầu d dương là supply** trong khi code quy định d dương là **in−out**.
23. **Tự gán INF trong ma trận năng lực** mà không chứng minh giới hạn số tối đa.
24. **Áp điều kiện không có cạnh âm của Dijkstra** vào bài cận luồng, trong khi đây là các đại lượng sức chứa, không phải chi phí.
25. **Quên điều kiện cân bằng ở thành phần không liên thông**, dẫn tới kết luận “có đường ở một thành phần” là đủ cho toàn mạng.
26. **Không kiểm tra nghiệm bằng tổng vào–ra trên cung gốc**, chỉ dựa vào kết quả trả của max flow phụ trợ.

## 16. Quy trình giải chuẩn để áp dụng trong bài mới

1. **Đọc đúng định nghĩa bài.** Đây là circulation tất cả đỉnh cân bằng, hay s–t flow có nguồn/đích được phép mất cân bằng? Có nhu cầu ngoài d không?
2. **Chốt dấu d.** Nếu dùng \(in-out=d\), d>0 là đỉnh nhận ròng, d<0 là đỉnh gửi ròng. Ghi rõ nếu đề dùng quy ước khác.
3. **Kiểm tra mọi cung có hướng.** Xác nhận ID đỉnh, \(0\le L\le U\), self-loop và cạnh song song.
4. **Tính b.** Với mỗi cung u→v cận dưới L: `b[u]-=L`, `b[v]+=L`.
5. **Giảm capacity.** Tạo cung phụ trợ cùng hướng u→v, sức chứa U−L, lưu handle của cung thuận để phục hồi f.
6. **Tính a=b−d** (nếu d=0 thì a=b). Kiểm tra \(\sum d=0\).
7. **Tạo SS và TT.** Với a>0 thêm SS→v capacity a; với a<0 thêm v→TT capacity −a. Tổng cần bão hòa \(B=\sum_{a>0}a\).
8. **Chạy max flow.** Dùng thuật toán phù hợp quy mô: Dinic, Edmonds–Karp, Push–Relabel, v.v.
9. **Kiểm điều kiện MaxFlow=B.** Nếu nhỏ hơn B, kết luận **không có nghiệm**; có thể cung cấp min-cut làm chứng cứ.
10. **Nếu khả thi, phục hồi từng cung gốc** bằng `f=L+initialResidual-remainingForward`.
11. **Đối chiếu cận và cân bằng** trên graph gốc: `L<=f<=U`, `in−out=d` tại mọi đỉnh.
12. **Nếu bài thêm mục tiêu tối ưu**, chuyển sang pha thích hợp (max s–t, min-cost) và không nhầm thuật toán khả thi với thuật toán tối ưu.
13. **Đánh giá độ phức tạp và số học.** Chú ý số đỉnh/cung phụ, bộ nhớ residual, sâu đệ quy Dinic, overflow.
14. **Kiểm thử bằng mạng nhỏ** với B=0, mạng không thông, cung bắt buộc nhưng không có đường bù, self-loop, cạnh song song và nhu cầu có dấu.

### Oracle độc lập cho mạng rất nhỏ

Với V và E rất nhỏ, có thể **liệt kê mọi lượng luồng nguyên** \(f_e\in[L_e,U_e]\), rồi kiểm tra:

\[
in_f(v)-out_f(v)=d(v)
\]

cho mọi v. Nếu có ít nhất một cấu hình hợp lệ, oracle trả feasible. So sánh boolean này với kết quả của phép giảm max flow SS→TT trên nhiều đồ thị nhỏ ngẫu nhiên.

Cách brute force có chi phí tích các độ rộng \((U-L+1)\), chỉ phù hợp kiểm thử chứ không phù hợp dữ liệu lớn. Nhưng nó **độc lập với cách dựng SS/TT**, nên rất hữu ích để phát hiện lỗi đảo dấu hoặc sai việc khôi phục luồng.

Nếu feasible, kiểm thêm từng `f_e` do chương trình trả để bảo đảm nó nằm đúng khoảng và thỏa tất cả phương trình. Nếu infeasible, có thể kiểm bằng bất đẳng thức cut ở mạng nhỏ để giải thích nguyên nhân.

## 17. Bài tập tự kiểm tra

**Bài 1 — Một cung bắt buộc.** Mạng 0→1 cận [2,2], không có cung khác. Có tuần hoàn không?

*Đáp án:* **Không**. f bắt buộc là 2, nhưng đỉnh 0 và 1 không cân bằng. Mạng phụ trợ cần B=2 nhưng không có đường bù từ 1 về 0.

**Bài 2 — Thêm cung hoàn trả.** Giữ 0→1 [2,2], thêm 1→0 [0,3]. Một nghiệm tuần hoàn là gì?

*Đáp án:* **f(0,1)=2, f(1,0)=2**, tất cả cận hợp lệ và hai đỉnh cân bằng.

**Bài 3 — Định nghĩa b.** Với một cung u→v cận dưới L=5, nó đóng góp bao nhiêu vào b[u] và b[v]?

*Đáp án:* **b[u] giảm 5**, **b[v] tăng 5**, vì \(b=inLower-outLower\).

**Bài 4 — b dương.** Nếu b[v]=+3, nên thêm cung nào?

*Đáp án:* **SS→v capacity 3**. Phần luồng bù x phải có out−in=+3 ở v.

**Bài 5 — b âm.** Nếu b[v]=−2, cung phụ trợ là gì?

*Đáp án:* **v→TT capacity 2**. Phần x cần nhận ròng 2 vào v.

**Bài 6 — Khả thi.** Nếu tổng dung lượng rời SS là B=7 nhưng max flow SS→TT chỉ đạt 6, có thể phục hồi một nghiệm circulation không?

*Đáp án:* **Không**. Ít nhất một cung điều chỉnh không bão hòa; bài tuần hoàn vô nghiệm.

**Bài 7 — f từ x.** Cung gốc [L=3,U=9] có luồng dư bù x=4. Luồng gốc f là bao nhiêu?

*Đáp án:* **7**, vì f=L+x=3+4; vẫn nằm trong [3,9].

**Bài 8 — Capacity dư.** Cung gốc [L=3,U=9] được đưa vào mạng phụ trợ với capacity bao nhiêu?

*Đáp án:* **6**, bằng U−L, không phải 9.

**Bài 9 — Ví dụ bốn đỉnh.** Với b=[−1,+1,0,0], B bằng bao nhiêu, và có thể dùng đường bù nào?

*Đáp án:* **B=1**, một đường bù là **SS→1→2→0→TT**.

**Bài 10 — Nhu cầu ngoài.** Theo quy ước d dương là in−out, với b[v]=+3 và d[v]=+1, a[v]=b−d bằng bao nhiêu và nối gì?

*Đáp án:* **a=+2**, thêm **SS→v capacity 2**.

**Bài 11 — Tổng d.** Nếu \(\sum_v d(v)\ne0\), mạng có thể có nghiệm theo phương trình in−out=d ở mọi v không?

*Đáp án:* **Không**, vì tổng vào và tổng ra của mọi cung trên toàn mạng triệt tiêu nhau.

**Bài 12 — B=0.** Nếu b[v]=0 tại mọi đỉnh trong circulation d=0, có cần gửi luồng từ SS sang TT không?

*Đáp án:* **Không**. Chọn `f=L` đã là nghiệm, max flow phụ trợ bằng 0=B.

**Bài 13 — Self-loop.** Một mạng một đỉnh và cung 0→0 [2,2] có khả thi không?

*Đáp án:* **Có**. Cung tự nối vừa vào vừa ra cùng một đỉnh, nên f=2 cân bằng.

**Bài 14 — S–t flow.** Muốn kiểm tra tồn tại luồng s–t có cận dưới và giá trị không âm, vì sao thêm cung nhân tạo t→s?

*Đáp án:* Cung t→s hoàn trả lượng luồng ròng F, khiến s và t trở thành đỉnh cân bằng trong tuần hoàn mở rộng. Luồng trên cung nhân tạo bằng F.

**Bài 15 — Tối đa hóa.** Sau khi tìm được tuần hoàn trên mạng có t→s, có thể lấy ngay luồng t→s và gọi đó là giá trị cực đại không?

*Đáp án:* **Không**. Đó chỉ là **một giá trị khả thi**. Để tối đa, bỏ các cung giả, dựng mạng dư trên các cung gốc với thuận U−f và ngược f−L rồi tăng luồng s→t.

**Bài 16 — Bất đẳng thức cut.** Với X={1} trong mạng chỉ có 0→1 [2,2], tại sao vô nghiệm?

*Đáp án:* Bắt buộc đi vào X ít nhất 2 nhưng không có cung ra X, tức \(L(\delta^-(X))=2>U(\delta^+(X))=0\).

**Bài 17 — Nhiều cung song song.** Vì sao không nên phục hồi luồng bằng một biến `flow[u][v]` nếu input có nhiều cung u→v?

*Đáp án:* Mỗi cung có cận riêng và là một biến luồng riêng; phải giữ đúng handle của **từng cung thuận** trong residual graph.

**Bài 18 — Chi phí.** Thuật toán Dinic SS→TT có tìm được circulation chi phí thấp nhất không?

*Đáp án:* **Không được bảo đảm**. Nó chỉ kiểm tra tính khả thi. Muốn tối ưu chi phí, cần phương pháp min-cost flow/circulation với hàm mục tiêu.

**Bài 19 — Nghiệm có demand.** Với d=[+1,−1,0,0] và các cung của ví dụ, `[3,3,3,1,1,0,0]` có hợp lệ không?

*Đáp án:* **Có**. Đỉnh 0 có in−out=+1, đỉnh 1 có in−out=−1, hai đỉnh còn lại cân bằng; tất cả luồng trong cận.

**Bài 20 — Bảo toàn và cận.** Có thể xác nhận nghiệm chỉ bằng cách thấy mọi f nằm trong [L,U] không?

*Đáp án:* **Không**. Phải kiểm tra thêm `in−out=d` tại từng đỉnh. Cận hợp lệ không tự bảo đảm tuần hoàn.

**Tổng kết:** Để giải **tuần hoàn có cận dưới**, đặt **\(f=L+x\)**, giảm sức chứa từng cung thành **U−L**, tính **\(b=inLower−outLower\)** và, nếu có nhu cầu ngoài, **\(a=b−d\)** theo quy ước \(in−out=d\). Với a>0 thêm **SS→v**, với a<0 thêm **v→TT**; chạy max flow SS→TT. Bài toán khả thi **khi và chỉ khi** max flow đạt **\(B=\sum_{a>0}a\)**. Khi thành công, phục hồi **\(f=L+x\)** và kiểm tra mọi cận/bảo toàn; khi thất bại, không xuất luồng tạm như nghiệm. Muốn giải **luồng s–t có cận dưới**, thêm cạnh hoàn trả **t→s** để kiểm tra tính khả thi rồi dùng mạng dư đúng các cận nếu cần tối đa hóa; muốn tối ưu chi phí, cần thuật toán min-cost riêng.
