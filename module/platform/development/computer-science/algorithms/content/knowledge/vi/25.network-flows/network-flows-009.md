# Nhiều nguồn, nhiều đích và mô hình nút nguồn–đích phụ

## 1. Từ luồng một nguồn–một đích đến mạng nhiều nguồn–nhiều đích

Trong bài toán **luồng cực đại (maximum flow)**, ta có đồ thị **có hướng** với dung lượng cạnh \(c(u,v)\ge0\). Luồng \(f(u,v)\) phải thỏa giới hạn dung lượng và bảo toàn luồng tại các đỉnh trung gian. Với **một nguồn s và một đích t**, mục tiêu là đưa lượng luồng lớn nhất từ s đến t.

Nhiều mạng thực tế không chỉ có một nơi phát và một nơi nhận:

- Nhiều nhà máy cùng đưa hàng vào một mạng vận chuyển; nhiều kho cùng nhận.
- Nhiều máy chủ cung cấp lưu lượng qua những đường truyền chia sẻ; nhiều cụm dịch vụ tiêu thụ.
- Nhiều trạm bơm cấp nước qua ống; nhiều khu vực cần nước.
- Nhiều vị trí xuất phát trên mạng giao thông có giới hạn thông lượng; nhiều điểm tập kết.
- Nhiều nhóm công việc đi vào hạ tầng xử lý chung rồi được phân phối tới các điểm hoàn thành.

Giả sử tập nguồn ban đầu là \(S=\{s_1,\ldots,s_p\}\), tập đích là \(T=\{t_1,\ldots,t_q\}\), với \(S\cap T=\varnothing\). Một luồng có thể phát sinh từ **bất kỳ nguồn nào** và kết thúc ở **bất kỳ đích nào**. Ta muốn tối đa hóa **tổng lượng luồng từ tất cả nguồn tới tất cả đích**, tôn trọng dung lượng mọi cung.

Nếu chỉ gọi max-flow riêng cho từng cặp \(s_i,t_j\) rồi cộng kết quả, các lần chạy có thể dùng **cùng một cạnh trung gian** vượt quá dung lượng thực tế. Đây là lỗi mô hình căn bản. Cần giải **một bài toán chung**, nơi mọi nguồn và đích cạnh tranh công bằng trên những cạnh dùng chung.

**Ý tưởng trung tâm:** thêm một **siêu nguồn** \(s^\ast\) (super-source) nối tới mọi nguồn thật, và một **siêu đích** \(t^\ast\) (super-sink) nhận từ mọi đích thật. Khi đó một thuật toán max-flow thông thường chạy **duy nhất một lần** từ \(s^\ast\) tới \(t^\ast\) giải bài toán nhiều nguồn, nhiều đích.

Bài học trình bày phép biến đổi, lựa chọn dung lượng cho cạnh phụ, chứng minh tương đương, mạng dư, lát cắt cực tiểu, giới hạn cấp/nhận, thuật toán Dinic Java 17, các trường hợp khó và bộ kiểm thử độc lập.

## 2. Ôn lại mạng luồng chuẩn

Với một mạng có hướng \(G=(V,E)\), mỗi cung \(e=(u,v)\) có **dung lượng** \(c(e)\), là lượng tối đa có thể vận chuyển theo chiều u→v.

Luồng hợp lệ trên cung thỏa:

\[
0\le f(e)\le c(e).
\]

Ở đỉnh **không phải nguồn/đích**, tổng luồng đi vào bằng tổng luồng đi ra:

\[
\sum_{e\in\delta^-(v)}f(e)
=
\sum_{e\in\delta^+(v)}f(e).
\]

Ở nguồn s của bài toán một nguồn, hiệu **đi ra trừ đi vào** là giá trị luồng. Ở đích t, hiệu **đi vào trừ đi ra** bằng cùng giá trị ấy.

Trong đồ thị có cung song song, mỗi cung có **ID và dung lượng riêng**. Ta cộng luồng theo từng cung chứ không chỉ theo cặp đỉnh, trừ khi đã chủ động gộp các cung cùng chiều bằng tổng dung lượng và biết rằng không còn ràng buộc riêng theo ID.

**Điều kiện dung lượng không âm** là bắt buộc đối với mô hình max-flow tiêu chuẩn. Đây là dung lượng, **không phải chi phí**; không được dùng “dung lượng âm” để biểu thị phần thưởng hoặc mức tiết kiệm. Bài toán min-cost flow có thể có **chi phí âm**, nhưng dung lượng cung vẫn phải không âm.

### Luồng không phải đường đi đơn duy nhất

Một luồng tổng có thể được **phân rã thành nhiều đường nguồn→đích** (và có thể có chu trình luồng nếu cách biểu diễn cho phép). Lượng luồng ở một đỉnh trung gian có thể đến từ nhiều nguồn và đi tới nhiều đích. Vì vậy không nên lưu một parent duy nhất cho mọi đỉnh như khi tìm một đường ngắn nhất.

Một đỉnh có thể được thăm nhiều lần trong những lần tăng luồng khác nhau; điều cần bảo toàn là **dung lượng dư** và tính cân bằng của luồng, không phải “đã thăm thì không sử dụng nữa”.

## 3. Phép biến đổi bằng siêu nguồn và siêu đích

Tạo hai đỉnh mới:

- **Siêu nguồn \(s^\ast\)**: một đỉnh **chỉ phát** vào mạng ban đầu.
- **Siêu đích \(t^\ast\)**: một đỉnh **chỉ nhận** từ mạng ban đầu.

Giữ nguyên **tất cả cung gốc và chiều của chúng**. Sau đó:
1. Với mỗi nguồn thật \(s_i\in S\), thêm cung **\(s^\ast\to s_i\)**.
2. Với mỗi đích thật \(t_j\in T\), thêm cung **\(t_j\to t^\ast\)**.
3. Chạy max-flow từ \(s^\ast\) tới \(t^\ast\).

Sơ đồ khái niệm:

~~~text
                 mạng gốc (có hướng)
                 +-----------------+
super-source     |                 |      super-sink
    s* -------> s1 ------> ... --> t1 --------> t*
     \           |                  ^          ^
      \--------> s2 -----> ... ---- t2 --------/
       \-------> ...                   ...
          các cung s*->si        các cung tj->t*
~~~

Trong ví dụ có n đỉnh thật đánh số 0..n−1, ta có thể đặt:

~~~text
s* = n
t* = n+1
V' = n+2 đỉnh
E' = E + |S| + |T| cung (bỏ qua self-loop vô ích nếu muốn)
~~~

**Chiều là điều kiện sống còn:**
- **Đúng:** super-source → source thật.
- **Đúng:** sink thật → super-sink.
- **Sai:** source thật → super-source hoặc super-sink → sink thật, vì chúng không tạo đường phát→nhận như mong muốn.

Không được tự thêm cung giữa mọi cặp nguồn–đích. Các cung trung gian, dung lượng, và khả năng kết nối phải vẫn do **mạng gốc** quyết định.

## 4. Dung lượng của các cung phụ: “vô hạn” là bao nhiêu?

Đây là phần thường bị lược bỏ nhưng dễ tạo kết quả sai hoặc overflow.

### 4.1. Không có hạn mức riêng ở nguồn và đích

Nếu mỗi nguồn thật được quyền phát lượng bất kỳ **miễn mạng gốc cho phép**, và mỗi đích thật được quyền nhận lượng bất kỳ **miễn mạng gốc cho phép**, các cung phụ cần có dung lượng đủ lớn để **không tự trở thành nút thắt**.

Sách thường viết:

\[
c(s^\ast,s_i)=+\infty,\qquad
c(t_j,t^\ast)=+\infty.
\]

Nhưng máy tính dùng số nguyên hữu hạn. Một lựa chọn an toàn là:

\[
\boxed{B=\sum_{e\in E,\ e\text{ không là self-loop}}c(e).}
\]

Sau đó đặt dung lượng mỗi cung phụ bằng **B**.

**Vì sao B đủ lớn?** Tổng luồng cần đi qua các cung **thật** của mạng. Mỗi cung thật vận chuyển không quá dung lượng của nó. Do các tập nguồn và đích không giao nhau, tổng luồng từ siêu nguồn tới siêu đích **không thể vượt tổng dung lượng mọi cung thật**, tức không vượt B. Bởi vậy đặt mỗi cung phụ bằng B không cắt bớt bất kỳ giá trị max-flow khả thi nào.

Nếu E rỗng hoặc chỉ có cung dung lượng 0/self-loop thì B=0 và luồng cực đại bằng 0, hoàn toàn hợp lý.

**Giới hạn biểu diễn:** Khi tính B bằng long, dùng **Math.addExact** để từ chối tổng vượt miền số nguyên. Không dùng một hằng số ngẫu nhiên như 1.000.000.000 và coi đó là vô hạn: nếu luồng thật vượt hằng số này, kết quả bị giảm giả.

### 4.2. Có hạn mức phát riêng cho mỗi nguồn

Giả sử nguồn \(s_i\) chỉ được **bơm thêm tối đa \(a_i\)** đơn vị từ bên ngoài vào mạng. Khi đó đặt:

\[
\boxed{c(s^\ast,s_i)=a_i.}
\]

Tổng lượng phát từ nguồn i qua cung phụ không vượt \(a_i\). Nếu a_i=0, nguồn i không bơm luồng mới, nhưng theo mô hình giữ nguyên mạng gốc, nó **vẫn có thể là điểm trung chuyển** cho luồng đi từ nguồn khác.

Cần hiểu hạn mức \(a_i\) là **lượng bơm thêm từ siêu nguồn**, không nhất thiết là **tổng lưu lượng đi ra khỏi đỉnh nguồn i** nếu đỉnh đó nhận luồng từ nơi khác.

### 4.3. Có hạn mức nhận riêng cho mỗi đích

Nếu đích \(t_j\) chỉ được **rút tối đa \(b_j\)** đơn vị ra khỏi mạng:

\[
\boxed{c(t_j,t^\ast)=b_j.}
\]

Lưu lượng đi qua cung phụ này là lượng đích j **nhận thực tế** từ mạng. Nếu b_j=0, nó không được rút luồng, nhưng vẫn có thể là điểm trung chuyển khi còn cung đi ra trong mạng gốc.

Vì vậy:
- **Giới hạn phát**: dung lượng \(s^\ast\to s_i\).
- **Giới hạn nhận**: dung lượng \(t_j\to t^\ast\).
- **Không giới hạn riêng**: dùng B an toàn, có chứng minh.

### 4.4. Giới hạn trên không phải nhu cầu tối thiểu

Cung phụ \(t_j\to t^\ast\) có dung lượng b_j chỉ đảm bảo **nhận không quá b_j**. Nó **không bắt buộc** đích j phải nhận ít nhất b_j hoặc chính xác b_j.

Nếu đề có **nhu cầu tối thiểu**, ví dụ kho A phải nhận ≥5 và kho B phải nhận ≥7, chỉ thêm cạnh phụ với capacity 5 và 7 **không đủ** để bảo đảm từng kho nhận đúng yêu cầu. Bài đó có **cận dưới luồng** hoặc **luồng khả thi với cung/cầu bắt buộc**, cần biến đổi riêng sang circulation with lower bounds.

Ngược lại, nếu chỉ hỏi “có thể giao **tổng** ít nhất K đơn vị không?”, chỉ cần tính max-flow F và so F≥K. Nhưng điều này vẫn không chứng minh **mỗi đích** đã được cấp đủ theo một quota riêng.

## 5. Chứng minh phép biến đổi tương đương

Giả sử mạng gốc có các tập nguồn S và đích T **không giao nhau**, luồng hợp lệ được hiểu theo **cân bằng ròng (net injection/withdrawal)** tại các terminal, không cấm trung chuyển.

### Chiều 1: Từ lời giải nhiều nguồn–nhiều đích sang mạng phụ

Có luồng hợp lệ trên các cung gốc và lượng bơm ròng \(x_i\ge0\) tại nguồn \(s_i\), lượng rút ròng \(y_j\ge0\) tại đích \(t_j\), thỏa giới hạn nếu có.

Thêm:
- Luồng \(f(s^\ast,s_i)=x_i\).
- Luồng \(f(t_j,t^\ast)=y_j\).

Ở mỗi đỉnh thật, cân bằng luồng được bảo đảm vì luồng ròng được bù đúng bởi cung phụ. Giá trị từ siêu nguồn là:

\[
F=\sum_i x_i=\sum_j y_j.
\]

Nếu các cung phụ không giới hạn, B đủ lớn để chứa từng x_i,y_j; nếu có hạn mức, x_i≤a_i và y_j≤b_j theo hợp đồng. Ta đã có luồng hợp lệ từ s* đến t* với **cùng tổng F**.

### Chiều 2: Từ mạng phụ trở lại nhiều nguồn–nhiều đích

Có luồng hợp lệ từ s* đến t*. Xóa hai đỉnh phụ và các cung phụ về mặt mô hình, giữ lại luồng trên các cung gốc.

Khi đó:
- Ở một đỉnh **không thuộc S hoặc T**, bảo toàn luồng như cũ.
- Ở nguồn \(s_i\), hiệu **đi ra qua cung gốc trừ đi vào qua cung gốc** bằng lượng luồng đã được bơm qua \(s^\ast\to s_i\), không âm.
- Ở đích \(t_j\), hiệu **đi vào qua cung gốc trừ đi ra qua cung gốc** bằng lượng được rút qua \(t_j\to t^\ast\), không âm.

Tổng luồng bơm bằng tổng luồng rút và bằng giá trị max-flow của mạng phụ. Các giới hạn riêng được thực thi bởi dung lượng cung phụ.

Vậy **hai mô hình tương đương về giá trị tối ưu và tính khả thi**, với điều kiện hợp đồng nguồn/đích đúng như trên.

**Lưu ý:** Nếu mô hình thực tế **cấm một nguồn nhận luồng từ nơi khác** hoặc **cấm đích chuyển tiếp luồng ra ngoài**, ta phải xóa/cấm các cung tương ứng hoặc mô hình hóa ràng buộc nút riêng. Phép biến đổi mặc định **không tự áp đặt** chính sách “nguồn chỉ có cạnh đi ra, đích chỉ có cạnh đi vào”.

## 6. Định lý max-flow min-cut và lát cắt ở mạng phụ

Trong mạng một nguồn–một đích, **định lý max-flow min-cut** nói:

\[
\max |f|=\min_{(A,B)}\sum_{u\in A,v\in B}c(u,v),
\]

với \(s^\ast\in A\), \(t^\ast\in B\), và các cung được tính **theo chiều A→B**.

Sau phép biến đổi, lát cắt có thể cắt:
- Cung gốc nằm giữa hai phần.
- **Cung từ siêu nguồn tới một nguồn thật** nếu nguồn thật nằm phía B.
- **Cung từ một đích thật tới siêu đích** nếu đích thật nằm phía A.

Điều này đặc biệt quan trọng khi các cung phụ có **hạn mức**. Khi có quotas, một lát cắt cực tiểu có thể có giá trị bằng **tổng hạn mức nhận**, ngay cả khi mạng gốc có khả năng truyền nhiều hơn.

Trong cài đặt Dinic, sau khi tìm luồng cực đại, duyệt các cung **còn dung lượng dư dương** từ siêu nguồn. Đặt A là tập đỉnh còn tới được, B là phần còn lại. Vì không còn đường tăng luồng tới siêu đích, t* không thuộc A. Tổng dung lượng ban đầu của mọi cung từ A sang B là **chứng chỉ min-cut** đúng bằng luồng cực đại.

Chúng ta sẽ in cả **maxFlow** và **minCutCapacity**. Nếu hai số không bằng nhau trên một bài toán max-flow đã xử lý xong, cài đặt có lỗi trong cập nhật mạng dư, tính đường tăng hoặc tính lát cắt.

## 7. Ví dụ chính: hai nguồn, hai đích, có cạnh chia sẻ

Xét mạng có **8 đỉnh thật 0..7**:
- **Nguồn:** S={0,1}.
- **Đích:** T={6,7}.
- **Trung gian:** 2,3,4,5.

Các cung có hướng:

| Cung | Dung lượng | Vai trò |
|---|---:|---|
| 0→2 | 7 | Cấp từ nguồn 0 |
| 0→3 | 4 | Cấp từ nguồn 0 |
| 1→2 | 3 | Cấp từ nguồn 1 |
| 1→4 | 8 | Cấp từ nguồn 1 |
| 2→3 | 2 | Chuyển giữa nhánh |
| 2→5 | 6 | Vào nút tập trung 5 |
| 3→5 | 7 | Vào nút tập trung 5 |
| 4→3 | 3 | Liên kết qua nhánh 3 |
| 4→5 | 5 | Vào nút tập trung 5 |
| 5→6 | 8 | Đưa đến đích 6 |
| 5→7 | 6 | Đưa đến đích 7 |
| 3→6 | 2 | Đường bổ sung tới 6 |
| 4→7 | 3 | Đường bổ sung tới 7 |
| 0→2 | 1 | **Cung song song** có dung lượng độc lập |

Mạng có tổng dung lượng cung gốc:

\[
B=65.
\]

Thêm:
- Siêu nguồn **8** với cung 8→0 và 8→1 có dung lượng 65 mỗi cung nếu không có hạn mức.
- Siêu đích **9** với cung 6→9 và 7→9 có dung lượng 65 mỗi cung.

Chỉ có một lần gọi max-flow **8→9**, không chạy bốn cặp 0→6, 0→7, 1→6, 1→7 riêng biệt.

### 7.1. Không giới hạn lượng bơm/nhận riêng

Luồng cực đại:

\[
\boxed{F=19}.
\]

Có thể xem ngay một **cận trên** bằng tổng dung lượng các cung **đi vào hai đích** của mạng gốc:

\[
c(5,6)+c(3,6)+c(5,7)+c(4,7)
=8+2+6+3=\boxed{19}.
\]

Thuật toán thực sự tìm được luồng tổng 19, nên đây cũng là cận dưới khả thi và do đó là đáp án tối ưu.

Với thứ tự cung trong chương trình:
- Lượng **bơm từ siêu nguồn** tới nguồn 0 và 1 lần lượt là **[11,8]**.
- Lượng **rút vào siêu đích** từ đích 6 và 7 lần lượt là **[10,9]**.
- Hai tổng đều bằng 19.

Lát cắt sau max-flow có các đỉnh thật còn tới được từ siêu nguồn:

~~~text
[0, 1, 2, 3, 4, 5]
~~~

Hai đích 6,7 ở phía bên kia. Cắt bốn cung 5→6, 3→6, 5→7 và 4→7 có tổng 19. Đúng với max-flow min-cut.

### 7.2. Có hạn mức riêng của nguồn và đích

Bây giờ giữ nguyên mọi cung gốc, nhưng thêm:
- Nguồn 0 được bơm tối đa **7**.
- Nguồn 1 được bơm tối đa **6**.
- Đích 6 nhận tối đa **5**.
- Đích 7 nhận tối đa **7**.

Tương ứng:

~~~text
c(8,0)=7, c(8,1)=6,
c(6,9)=5, c(7,9)=7.
~~~

Cận trên theo tổng khả năng bơm là 7+6=13. Cận trên theo tổng khả năng nhận là 5+7=**12**. Vì thế F≤12. Thuật toán tìm được một luồng đạt **12**:

\[
\boxed{F_{\mathrm{capped}}=12}.
\]

Một kết quả cụ thể do Dinic với thứ tự cung của chương trình:
- Nguồn 0,1 bơm **[7,5]**.
- Đích 6,7 nhận **[5,7]**.
- Tổng vẫn 12.

Lát cắt cực tiểu lúc này có thể cắt **hai cung từ các đích vào siêu đích**, tổng 5+7=12. Nghẽn cổ chai không còn là bốn cung vào đích của mạng gốc, mà là **quota nhận** của hai đích.

**Thông điệp:** mô hình super-source/super-sink không chỉ “gom các nguồn và đích”. **Dung lượng cung phụ là ràng buộc kinh doanh**. Đặt nhầm dung lượng có thể làm thay đổi bài toán và đáp án.

## 8. Mạng dư và tại sao phải có cung ngược

Với mỗi cung gốc u→v dung lượng c, một thuật toán augmenting path lưu:
- **Cung xuôi dư** với dung lượng c−f.
- **Cung ngược dư** với dung lượng f (ban đầu 0).

Cung ngược trong **mạng dư** cho phép **hủy/điều chỉnh một phần luồng đã đẩy trước đó** khi tìm một cách phân phối tốt hơn. Nó **không** có nghĩa đồ thị vật lý ban đầu cho phép vận chuyển ngược chiều u←v.

Nếu ban đầu đẩy 3 đơn vị qua u→v, dung lượng dư xuôi giảm 3, dung lượng dư ngược tăng 3. Một đường tăng sau này có thể đi qua cung ngược để thu hồi 1 đơn vị của luồng cũ rồi phân phối lại.

**Phải phân biệt:**
- Một cung gốc ngược chiều v→u nếu nó thật sự tồn tại trong dữ liệu, có dung lượng vật lý riêng.
- Cung ngược dư được tạo ra bởi thuật toán khi thêm mỗi cung gốc, ban đầu có dung lượng 0.

Chúng không phải cùng một đối tượng, dù có thể trùng cặp hai đầu mút. Khi có cung song song, mỗi cung cũng có **một cặp cạnh dư riêng**.

Việc thêm siêu nguồn và siêu đích không thay đổi quy tắc mạng dư: các cung phụ cũng có cung ngược dư để có thể điều chỉnh lượng cấp giữa những nguồn hoặc nhận giữa những đích trong các lần tăng luồng.

## 9. Thuật toán Dinic trên mạng đã biến đổi

**Dinic** là thuật toán luồng cực đại sử dụng:
1. BFS trên mạng dư để xây **đồ thị mức (level graph)** từ siêu nguồn.
2. DFS trên các cung dư đi từ mức k sang k+1 để đẩy **blocking flow**.
3. Lặp lại khi vẫn có đường từ siêu nguồn tới siêu đích trong mạng dư.

Một lần BFS:
- Đặt level[s*]=0.
- Duyệt cung có residual>0.
- Với v chưa có mức, gán level[v]=level[u]+1.
- Nếu level[t*]==−1, không còn đường tăng, thuật toán kết thúc.

Một lần DFS:
- Chỉ đi qua cung còn dư và level[v]==level[u]+1.
- Đẩy lượng nhỏ nhất giữa lượng yêu cầu và dung lượng dư của cung.
- Giảm residual cung xuôi, tăng residual cung ngược.
- Dùng mảng con trỏ **next[u]** để không thử lại những cung đã hết khả năng đẩy trong một lượt BFS.

Giả mã:

~~~text
while bfsBuildLevels(superSource, superSink):
    next[u] = 0 for every u

    while (pushed = dfsPush(superSource, superSink, INF)) > 0:
        totalFlow += pushed

return totalFlow
~~~

**Không phải BFS tìm đường ngắn nhất của bài đường đi ngắn nhất.** Level graph chỉ dùng để tìm đường tăng trong **mạng dư**; giá trị tối ưu là **lượng luồng**, không phải tổng chiều dài đường.

### Vì sao dùng Dinic thay vì chạy luồng từng cặp?

Chạy một lần Dinic trên mạng phụ cho phép thuật toán tự điều phối mọi nguồn và đích trên những cạnh chung. Cung phụ biểu diễn quota hoặc giới hạn không ràng buộc, còn Dinic giải toàn cục.

Nếu muốn xuất chính xác lượng vận chuyển từ từng nguồn tới từng đích, chỉ biết tổng max-flow và lượng qua mỗi cung phụ **chưa đủ** để tạo ma trận nguồn–đích. Cần **phân rã luồng cuối cùng thành các đường** từ s* tới t* (hoặc giải mô hình có biến gắn commodity nếu có thêm yêu cầu phân biệt hàng hóa/nguồn). Bài toán max-flow thông thường **không phân biệt luồng là hàng hóa khác nhau**.

## 10. Java 17: Dinic cùng mô hình siêu nguồn/siêu đích

Chương trình dưới đây là **một tệp chạy độc lập**. Nó cung cấp:
- Cung có hướng dạng **{from,to,capacity}** trong mảng long[][].
- Đỉnh gốc 0..n−1; siêu nguồn n, siêu đích n+1.
- Tập nguồn và đích **không rỗng, không trùng ID trong từng tập, không giao nhau**.
- Mảng giới hạn **sourceLimits** và **sinkLimits** tùy chọn; truyền null nghĩa là **không có quota riêng**, dùng B đã chứng minh đủ lớn.
- Cung song song được giữ như các cung khác nhau; **self-loop được bỏ** vì không ảnh hưởng giá trị luồng cực đại.
- Dung lượng âm bị từ chối; dung lượng 0 hợp lệ.
- Dinic BFS mức và DFS blocking flow với **cung ngược dư**.
- Trả max-flow, giá trị min-cut, lượng bơm/nhận theo thứ tự tập nguồn/đích và danh sách các đỉnh thật còn tới được từ siêu nguồn trong mạng dư.
- Dùng **Math.addExact** để báo lỗi khi tổng dung lượng, tổng luồng hoặc tổng lát cắt vượt long.

Lưu tệp **MultiSourceMultiSinkFlowDemo.java**:

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public final class MultiSourceMultiSinkFlowDemo {
    private MultiSourceMultiSinkFlowDemo() {
    }

    private record Arc(int from, int to, long capacity) {
    }

    private static final class ResidualEdge {
        final int to;
        final int reverseIndex;
        long residual;

        ResidualEdge(int to, int reverseIndex, long residual) {
            this.to = to;
            this.reverseIndex = reverseIndex;
            this.residual = residual;
        }
    }

    private record TerminalLink(long capacity, ResidualEdge edge) {
    }

    public record Result(
            long maxFlow,
            long minCutCapacity,
            List<Long> sourceSent,
            List<Long> sinkReceived,
            List<Integer> residualReachableOriginal) {
    }

    private static final class Dinic {
        final List<List<ResidualEdge>> graph;
        final int[] level;
        final int[] next;

        Dinic(int vertexCount) {
            graph = new ArrayList<>();
            for (int u = 0; u < vertexCount; u++) {
                graph.add(new ArrayList<>());
            }
            level = new int[vertexCount];
            next = new int[vertexCount];
        }

        ResidualEdge addEdge(int from, int to, long capacity) {
            // Self-loop của mạng gốc đã bị loại ở lớp solve.
            if (from == to || capacity < 0) {
                throw new IllegalArgumentException("Invalid arc");
            }

            ResidualEdge forward = new ResidualEdge(
                    to, graph.get(to).size(), capacity);
            ResidualEdge reverse = new ResidualEdge(
                    from, graph.get(from).size(), 0L);

            graph.get(from).add(forward);
            graph.get(to).add(reverse);
            return forward;
        }

        boolean bfs(int source, int sink) {
            Arrays.fill(level, -1);
            ArrayDeque<Integer> queue = new ArrayDeque<>();
            queue.add(source);
            level[source] = 0;

            while (!queue.isEmpty()) {
                int u = queue.remove();
                for (ResidualEdge e : graph.get(u)) {
                    if (e.residual > 0 && level[e.to] == -1) {
                        level[e.to] = level[u] + 1;
                        queue.add(e.to);
                    }
                }
            }
            return level[sink] != -1;
        }

        long dfs(int u, int sink, long pushed) {
            if (pushed == 0) {
                return 0;
            }
            if (u == sink) {
                return pushed;
            }

            List<ResidualEdge> adjacent = graph.get(u);
            while (next[u] < adjacent.size()) {
                ResidualEdge e = adjacent.get(next[u]);

                if (e.residual > 0
                        && level[e.to] == level[u] + 1) {
                    long sent = dfs(
                            e.to, sink, Math.min(pushed, e.residual));
                    if (sent > 0) {
                        e.residual -= sent;

                        ResidualEdge reverse = graph
                                .get(e.to).get(e.reverseIndex);
                        reverse.residual = Math.addExact(
                                reverse.residual, sent);
                        return sent;
                    }
                }
                next[u]++;
            }
            return 0;
        }

        long maxFlow(int source, int sink) {
            long total = 0;
            while (bfs(source, sink)) {
                Arrays.fill(next, 0);
                long sent;
                while ((sent = dfs(source, sink,
                                   Long.MAX_VALUE)) > 0) {
                    total = Math.addExact(total, sent);
                }
            }
            return total;
        }

        boolean[] reachableFrom(int source) {
            boolean[] seen = new boolean[graph.size()];
            ArrayDeque<Integer> queue = new ArrayDeque<>();
            queue.add(source);
            seen[source] = true;

            while (!queue.isEmpty()) {
                int u = queue.remove();
                for (ResidualEdge e : graph.get(u)) {
                    if (e.residual > 0 && !seen[e.to]) {
                        seen[e.to] = true;
                        queue.add(e.to);
                    }
                }
            }
            return seen;
        }
    }

    public static Result solve(
            int n,
            long[][] inputArcs,
            int[] sources,
            int[] sinks,
            long[] sourceLimits,
            long[] sinkLimits) {
        if (n < 1 || n > Integer.MAX_VALUE - 2
                || inputArcs == null
                || sources == null || sinks == null
                || sources.length == 0 || sinks.length == 0) {
            throw new IllegalArgumentException(
                    "Need valid nodes and nonempty terminals");
        }

        if ((sourceLimits != null
                && sourceLimits.length != sources.length)
                || (sinkLimits != null
                    && sinkLimits.length != sinks.length)) {
            throw new IllegalArgumentException(
                    "Limit array length mismatch");
        }

        int[] role = new int[n];
        for (int s : sources) {
            if (s < 0 || s >= n || role[s] != 0) {
                throw new IllegalArgumentException(
                        "Duplicate or invalid source");
            }
            role[s] = 1;
        }
        for (int t : sinks) {
            if (t < 0 || t >= n || role[t] != 0) {
                throw new IllegalArgumentException(
                        "Overlapping or invalid sink");
            }
            role[t] = 2;
        }

        // B là cận trên hữu hạn, an toàn cho các cung phụ.
        // Self-loop không có đóng góp vào luồng s* -> t*.
        long bound = 0;
        List<Arc> original = new ArrayList<>();

        for (long[] row : inputArcs) {
            if (row == null || row.length != 3) {
                throw new IllegalArgumentException(
                        "Expected {from,to,capacity}");
            }

            long from = row[0];
            long to = row[1];
            long capacity = row[2];

            if (from < 0 || from >= n
                    || to < 0 || to >= n || capacity < 0) {
                throw new IllegalArgumentException(
                        "Invalid endpoint or negative capacity");
            }

            if (from != to) {
                bound = Math.addExact(bound, capacity);
                original.add(new Arc(
                        (int) from, (int) to, capacity));
            }
        }

        final int superSource = n;
        final int superSink = n + 1;
        Dinic dinic = new Dinic(n + 2);
        List<Arc> extendedArcs = new ArrayList<>(original);

        for (Arc arc : original) {
            dinic.addEdge(
                    arc.from(), arc.to(), arc.capacity());
        }

        List<TerminalLink> sourceLinks = new ArrayList<>();
        for (int i = 0; i < sources.length; i++) {
            long capacity = sourceLimits == null
                    ? bound : sourceLimits[i];
            if (capacity < 0) {
                throw new IllegalArgumentException(
                        "Negative source limit");
            }

            ResidualEdge edge = dinic.addEdge(
                    superSource, sources[i], capacity);
            sourceLinks.add(new TerminalLink(capacity, edge));
            extendedArcs.add(new Arc(
                    superSource, sources[i], capacity));
        }

        List<TerminalLink> sinkLinks = new ArrayList<>();
        for (int i = 0; i < sinks.length; i++) {
            long capacity = sinkLimits == null
                    ? bound : sinkLimits[i];
            if (capacity < 0) {
                throw new IllegalArgumentException(
                        "Negative sink limit");
            }

            ResidualEdge edge = dinic.addEdge(
                    sinks[i], superSink, capacity);
            sinkLinks.add(new TerminalLink(capacity, edge));
            extendedArcs.add(new Arc(
                    sinks[i], superSink, capacity));
        }

        long flow = dinic.maxFlow(superSource, superSink);
        boolean[] reachable = dinic.reachableFrom(superSource);

        long cutCapacity = 0;
        for (Arc arc : extendedArcs) {
            if (reachable[arc.from()] && !reachable[arc.to()]) {
                cutCapacity = Math.addExact(
                        cutCapacity, arc.capacity());
            }
        }

        List<Long> sent = new ArrayList<>();
        long sumSent = 0;
        for (TerminalLink link : sourceLinks) {
            long used = link.capacity() - link.edge().residual;
            sent.add(used);
            sumSent = Math.addExact(sumSent, used);
        }

        List<Long> received = new ArrayList<>();
        long sumReceived = 0;
        for (TerminalLink link : sinkLinks) {
            long used = link.capacity() - link.edge().residual;
            received.add(used);
            sumReceived = Math.addExact(sumReceived, used);
        }

        if (flow != cutCapacity
                || flow != sumSent || flow != sumReceived) {
            throw new IllegalStateException(
                    "Flow/cut/conservation certificate mismatch");
        }

        List<Integer> reachableOriginal = new ArrayList<>();
        for (int u = 0; u < n; u++) {
            if (reachable[u]) {
                reachableOriginal.add(u);
            }
        }

        return new Result(
                flow, cutCapacity, List.copyOf(sent),
                List.copyOf(received),
                List.copyOf(reachableOriginal));
    }

    private static String score(Result r) {
        return "flow=" + r.maxFlow()
                + ", cut=" + r.minCutCapacity();
    }

    public static void main(String[] args) {
        long[][] main = {
                {0, 2, 7}, {0, 3, 4},
                {1, 2, 3}, {1, 4, 8},
                {2, 3, 2}, {2, 5, 6},
                {3, 5, 7}, {4, 3, 3},
                {4, 5, 5}, {5, 6, 8},
                {5, 7, 6}, {3, 6, 2},
                {4, 7, 3}, {0, 2, 1}
        };

        Result unbounded = solve(
                8, main,
                new int[] {0, 1}, new int[] {6, 7},
                null, null);

        System.out.println("Main unbounded: "
                + score(unbounded)
                + ", sent=" + unbounded.sourceSent()
                + ", received=" + unbounded.sinkReceived()
                + ", residualReachable="
                + unbounded.residualReachableOriginal());

        Result capped = solve(
                8, main,
                new int[] {0, 1}, new int[] {6, 7},
                new long[] {7, 6}, new long[] {5, 7});

        System.out.println("Main capped: "
                + score(capped)
                + ", sent=" + capped.sourceSent()
                + ", received=" + capped.sinkReceived()
                + ", residualReachable="
                + capped.residualReachableOriginal());

        Result parallel = solve(
                2, new long[][] {{0, 1, 4}, {0, 1, 3}},
                new int[] {0}, new int[] {1}, null, null);
        System.out.println("Parallel: " + score(parallel));

        Result disconnected = solve(
                4, new long[][] {{0, 1, 8}, {2, 3, 7}},
                new int[] {0, 2}, new int[] {1, 3},
                null, null);
        System.out.println("Disconnected routes: "
                + score(disconnected));

        Result zero = solve(
                3, new long[][] {{0, 1, 0}, {1, 2, 9}},
                new int[] {0}, new int[] {2}, null, null);
        System.out.println("Zero bottleneck: " + score(zero));

        Result noRoute = solve(
                4, new long[][] {{0, 2, 4}, {1, 3, 4}},
                new int[] {0}, new int[] {3}, null, null);
        System.out.println("No route: " + score(noRoute));

        Result selfLoop = solve(
                2, new long[][] {{0, 0, 100}, {0, 1, 4}},
                new int[] {0}, new int[] {1}, null, null);
        System.out.println("Self-loop ignored: " + score(selfLoop));

        Result quota = solve(
                2, new long[][] {{0, 1, 9}},
                new int[] {0}, new int[] {1},
                new long[] {4}, new long[] {6});
        System.out.println("Direct quota: " + score(quota));

        Result transit = solve(
                4, new long[][] {
                        {0, 1, 6}, {1, 2, 6}, {2, 3, 5}
                },
                new int[] {0, 1}, new int[] {3},
                new long[] {6, 2}, new long[] {8});
        System.out.println("Source as transit: "
                + score(transit)
                + ", sent=" + transit.sourceSent());

        try {
            solve(2, new long[][] {{0, 1, 5}},
                    new int[] {0}, new int[] {0},
                    null, null);
            System.out.println("Overlap rejected: false");
        } catch (IllegalArgumentException expected) {
            System.out.println("Overlap rejected: true");
        }

        try {
            solve(2, new long[][] {{0, 1, -1}},
                    new int[] {0}, new int[] {1},
                    null, null);
            System.out.println("Negative rejected: false");
        } catch (IllegalArgumentException expected) {
            System.out.println("Negative rejected: true");
        }

        try {
            solve(2, new long[][] {{0, 1, 5}},
                    new int[] {}, new int[] {1},
                    null, null);
            System.out.println("Empty sources rejected: false");
        } catch (IllegalArgumentException expected) {
            System.out.println("Empty sources rejected: true");
        }

        try {
            solve(2, new long[][] {{0, 1, 5}},
                    new int[] {0}, new int[] {},
                    null, null);
            System.out.println("Empty sinks rejected: false");
        } catch (IllegalArgumentException expected) {
            System.out.println("Empty sinks rejected: true");
        }
    }
}
~~~

### 10.1. Biên dịch và chạy

Sử dụng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 MultiSourceMultiSinkFlowDemo.java
java MultiSourceMultiSinkFlowDemo
~~~

**Stdout đúng với thứ tự cung và cách duyệt của chương trình:**

~~~text
Main unbounded: flow=19, cut=19, sent=[11, 8], received=[10, 9], residualReachable=[0, 1, 2, 3, 4, 5]
Main capped: flow=12, cut=12, sent=[7, 5], received=[5, 7], residualReachable=[0, 1, 2, 3, 4, 5, 6, 7]
Parallel: flow=7, cut=7
Disconnected routes: flow=15, cut=15
Zero bottleneck: flow=0, cut=0
No route: flow=0, cut=0
Self-loop ignored: flow=4, cut=4
Direct quota: flow=4, cut=4
Source as transit: flow=5, cut=5, sent=[3, 2]
Overlap rejected: true
Negative rejected: true
Empty sources rejected: true
Empty sinks rejected: true
~~~

### 10.2. Cách đọc output

**Main unbounded:** tổng 19, bằng min-cut 19; hai nguồn bơm 11 và 8, hai đích nhận 10 và 9. Các đỉnh 0..5 nằm phía tới được của lát cắt cực tiểu.

**Main capped:** tổng giảm còn 12, đúng tổng quota nhận 5+7. Nguồn 0 dùng hết quota 7, nguồn 1 bơm 5 trong tối đa 6. Hai đích nhận đúng [5,7].

**Parallel:** hai cung 0→1 dung lượng 4 và 3 được dùng tổng 7. Không tự xóa cung thứ hai vì trùng cặp đỉnh.

**Disconnected routes:** có hai thành phần rời nhau 0→1 và 2→3, nhưng cả hai có nguồn và đích được nối vào siêu nút. Tổng 8+7=15. Bản thân đồ thị gốc **không cần liên thông** mới áp dụng max-flow nhiều terminal.

**Zero bottleneck:** cung 0→1 dung lượng 0 khóa đường tới đích; max-flow bằng 0 dù phía sau có cung dung lượng 9.

**No route:** có những cung dung lượng dương nhưng nguồn thật 0 không đi được tới đích thật 3; đáp án 0.

**Self-loop ignored:** cung 0→0 dung lượng 100 không chuyển hàng sang đỉnh khác, nên không nâng max-flow; chỉ cung 0→1 dung lượng 4 tạo luồng.

**Direct quota:** đường gốc có dung lượng 9, nguồn được cấp tối đa 4 và đích nhận tối đa 6 nên luồng tối đa 4.

**Source as transit:** nguồn thật 1 vừa bơm 2 đơn vị từ siêu nguồn, vừa nhận 3 đơn vị từ nguồn thật 0, rồi chuyển tổng 5 qua mạng. Vì vậy output sent=[3,2], chứ không phải [5,0]. Điều này phản ánh **hạn mức bơm ròng**, không phải cấm nguồn có luồng đi vào.

**Rejected:** code từ chối một đỉnh đồng thời nằm trong tập nguồn và đích, dung lượng âm, và tập nguồn/đích rỗng. Đây là **hợp đồng API**, không phải lời khẳng định mọi phiên bản bài toán đều cấm tập rỗng về mặt toán học.

### 10.3. Vì sao kiểm tra source/sink trùng nhau?

Nếu một đỉnh x vừa thuộc S vừa thuộc T, phép biến đổi đơn giản tạo:

~~~text
s* -> x -> t*
~~~

Đường này có thể truyền luồng **không qua bất kỳ cung gốc nào**, tạo kết quả không phản ánh vận chuyển thực. Vì vậy code **yêu cầu S và T rời nhau**.

Nếu đề cho cùng một địa điểm vừa phát vừa nhận, phải quy định **lượng luồng nào là phát nội bộ, nhận nội bộ và có cho tự triệt tiêu hay không**; có thể cần tách vai trò thành hai nút/cổng riêng và mô hình hóa các cung giữa chúng. Không được bỏ qua vấn đề này rồi chấp nhận một đường s*→x→t* giả.

### 10.4. Vì sao có thể bỏ self-loop?

Một cung u→u tạo 0 biến thiên ròng ở đỉnh u, không giúp đưa luồng từ một nguồn tới một đích khác. Bỏ self-loop không thay đổi giá trị max-flow chuẩn. Mã **vẫn kiểm tra dung lượng self-loop phải không âm**, nhưng không thêm nó vào mạng dư hoặc cận trên B.

Cách bỏ self-loop cũng tránh lỗi chỉ số cung ngược khi cả cung xuôi và cung ngược nằm trong cùng danh sách kề. Nếu muốn lưu self-loop để báo cáo riêng, phải xử lý hai chỉ số ngược thật cẩn thận.

### 10.5. Vì sao tính min-cut từ dung lượng gốc?

Dung lượng dư sau max-flow không bằng dung lượng ban đầu. Để chứng minh min-cut, chương trình lưu danh sách **extendedArcs** gồm cung gốc và cung phụ với dung lượng **ban đầu**, rồi tính tổng capacity của những cung đi từ phía còn tới được sang phía không tới được.

Không cộng dung lượng của **cung ngược dư** vào lát cắt; chúng là cấu trúc thuật toán, không phải những cung vật lý gốc có capacity riêng.

### 10.6. Cung phụ và kết quả bơm/nhận

Hàm addEdge trả tham chiếu đến cung xuôi dư. Nếu cung phụ ban đầu có capacity C và sau khi chạy chỉ còn residual R, lượng luồng ròng qua cung ấy là **C−R**.

Code dùng công thức này để in sourceSent và sinkReceived, rồi kiểm tra:

\[
\sum sourceSent_i
=
\sum sinkReceived_j
=
maxFlow
=
minCutCapacity.
\]

Đây là bốn cách kiểm chứng quan trọng và độc lập về mặt ý nghĩa.

## 11. Dung lượng, hạn mức và các ràng buộc ở nút

Các cung phụ thực thi **lượng phát/nhận ròng**, nhưng không tự giới hạn tổng lưu lượng đi qua một nút.

Ví dụ nguồn thật 1 có:
- 2 đơn vị **bơm từ siêu nguồn**.
- 3 đơn vị **nhận từ nguồn thật khác**.
- 5 đơn vị **đẩy đi tới trung gian**.

Giới hạn phát a_1=2 vẫn được tuân thủ vì chỉ tính **lượng mới đưa từ ngoài mạng vào**, không tính luồng được chuyển tiếp.

Nếu bài thực tế ghi “mỗi nhà máy tối đa **xử lý** 2 đơn vị trên mọi cung đi qua” thì đây là **dung lượng nút**, không phải đơn thuần dung lượng cung super-source→source. Một kỹ thuật phổ biến:

~~~text
v_in --[nodeCapacity]--> v_out
~~~

- Chuyển mọi cung đi vào v sang **v_in**.
- Chuyển mọi cung đi ra v từ **v_out**.
- Thêm cung v_in→v_out với dung lượng xử lý của nút.
- Gắn các cung phụ của nguồn/đích vào cổng đúng theo ngữ nghĩa.

Cần định nghĩa rõ nguồn có được trung chuyển hay không và tổng nào bị giới hạn để chọn đúng cách nối.

**Nếu cấm trung chuyển ở nguồn:** không cho phép cung gốc đi vào nguồn hoặc tách vai trò phát/điểm trung gian thành những nút khác nhau, tùy đề.

**Nếu cấm trung chuyển ở đích:** không cho phép cung gốc đi ra đích hoặc tách vai trò nhận/điểm trung gian.

**Nếu yêu cầu tất cả hàng của nguồn i phải tới đúng đích j được chỉ định:** đó có thể là bài toán **luồng nhiều hàng hóa (multi-commodity flow)** hoặc gắn nhãn luồng, phức tạp hơn max-flow một loại hàng. Phép biến đổi siêu nguồn/siêu đích giải bài toán **tổng luồng không phân biệt nguồn–đích cụ thể**.

## 12. Vì sao không cộng kết quả cho từng cặp nguồn–đích?

Xét hai nguồn A và B cùng đưa hàng qua **một cung hẹp** x→y dung lượng 5 rồi tới một hoặc nhiều đích. Nếu chạy riêng:
- Max-flow từ A tới một đích có thể đạt 5.
- Max-flow từ B tới đích khác cũng có thể đạt 5.

Cộng hai kết quả 5+5=10 là sai khi cả hai phương án đều dùng cùng cung x→y capacity 5. **Mạng chung chỉ cho tối đa 5 qua cung ấy**, nên tối ưu tổng phải giải đồng thời.

Ngay cả việc ưu tiên nguồn A trước bằng cách chạy max-flow rồi “đóng băng” luồng A và sau đó chạy nguồn B cũng có thể bỏ lỡ phương án phân phối tốt hơn: max-flow có thể cần **hủy và chuyển hướng** một phần luồng cũ bằng cung ngược dư.

**Siêu nguồn** không ưu tiên một nguồn nào theo bản chất thuật toán; nó chỉ gom toàn bộ quyền cấp vào một bài toán. Nếu cần ưu tiên một nguồn, công bằng theo tỷ lệ, hoặc tối đa hóa số đích được phục vụ đủ quota, phải thêm hàm mục tiêu/ràng buộc khác, không tự suy từ một nghiệm max-flow bất kỳ.

## 13. Giới hạn số và cách chọn INF an toàn

Trong nhiều mẫu code, người ta viết:

~~~java
long INF = Long.MAX_VALUE;
~~~

cho cung phụ. Điều này có thể dùng được nếu mọi phép cộng và tổng luồng được kiểm soát, nhưng nó **không phải vô hạn toán học**. Nếu nhiều cung lớn và tổng thật vượt long, tổng tích lũy có thể tràn.

Mẫu code ở trên chủ động:
1. Cộng dung lượng **các cung gốc hữu ích** thành bound B bằng Math.addExact.
2. Nếu không có hạn mức riêng, mỗi cung phụ dùng **B**.
3. Nếu có hạn mức riêng, cung phụ dùng đúng giá trị quota không âm.
4. Tổng luồng và min-cut dùng Math.addExact.
5. Mọi phép trừ/cộng mạng dư duy trì trong miền số vì luồng trên mỗi cung không vượt dung lượng ban đầu và tổng luồng bị chặn bởi B.

**Điều kiện năng lực số học:** tổng dung lượng cung gốc hữu ích phải biểu diễn được bằng long trong phiên bản này. Nếu vượt giới hạn, cần BigInteger hoặc một phiên bản thiết kế cho số rất lớn; không im lặng đặt B thấp hơn thực tế.

Lựa chọn B còn giúp diễn giải dễ: nếu luồng qua toàn mạng không thể vượt tổng dung lượng mọi cung, một cung phụ dung lượng B **không thể là nút thắt giả** của giá trị tối ưu.

## 14. Độ phức tạp

Đặt:
- n = số đỉnh thật.
- m = số cung thật có hướng (không tính self-loop bị bỏ).
- p = số nguồn.
- q = số đích.

Sau biến đổi:

\[
V'=n+2,\qquad E'=m+p+q.
\]

**Xây mạng** mất O(V'+E') thời gian và bộ nhớ. Với mỗi cung thật hoặc cung phụ, cấu trúc mạng dư có **hai đối tượng**: cung xuôi và cung ngược, nên tổng đối tượng cạnh là 2E' (nhân 2 không đổi bậc phức tạp).

**Dinic trong mạng có dung lượng tổng quát** có cận trên thời gian:

\[
\boxed{O(V'^2 E')}.
\]

Đây là cận tệ nhất tiêu chuẩn cho Dinic trên mạng luồng có hướng tổng quát. Trên một số lớp mạng đặc biệt, Dinic có cận tốt hơn, nhưng không được áp dụng cận chuyên biệt khi chưa có giả thiết đó.

**Bộ nhớ thuật toán**:

\[
\boxed{O(V'+E')}.
\]

Gồm danh sách kề mạng dư, mảng level, next, queue BFS và stack đệ quy DFS theo đường tăng. Độ sâu DFS có thể tới O(V'). Trên mạng có đường tăng rất dài, **đệ quy Java có nguy cơ StackOverflowError**; khi cần xử lý đồ thị cực sâu, có thể cài blocking-flow DFS bằng **stack tường minh** thay vì đệ quy.

**Tính min-cut sau max-flow** dùng một BFS nữa O(V'+E'), rồi duyệt danh sách cung gốc + cung phụ O(E'). Thống kê lượng bơm/nhận tốn O(p+q).

Nếu bài chỉ yêu cầu max-flow và không cần chứng chỉ/các thống kê, có thể bỏ danh sách extendedArcs, các TerminalLink và bước tính min-cut để giảm bộ nhớ phụ, nhưng nên giữ khi học và debug.

## 15. Kiểm chứng độc lập bằng min-cut trên mạng nhỏ

Một cách kiểm thử **khác thuật toán Dinic** là liệt kê mọi lát cắt trên mạng phụ khi n nhỏ.

Có V'=n+2 đỉnh, với s* phải nằm bên nguồn của lát cắt và t* phải nằm bên đích. Mọi đỉnh thật có thể nằm ở một trong hai phía, nên chỉ có:

\[
2^n
\]

cách chia cần xét (mỗi bit ứng với một đỉnh thật).

Với từng cách chia, tính tổng dung lượng **các cung ban đầu từ phía s* sang phía t***, kể cả cung phụ. Giá trị nhỏ nhất là **min-cut oracle**.

Giả mã:

~~~text
arcsExtended = all original directed arcs
for each source si:
    arcsExtended.add(superSource -> si, sourceLimit[si] or B)
for each sink tj:
    arcsExtended.add(tj -> superSink, sinkLimit[tj] or B)

bestCut = +INF
for each bitMask over n original vertices:
    A = {superSource} plus vertices selected in bitMask
    Bside = all remaining vertices plus {superSink}

    cutCapacity = 0
    for each arc (u, v, capacity) in arcsExtended:
        if u in A and v in Bside:
            cutCapacity += capacity

    bestCut = min(bestCut, cutCapacity)

assert DinicMaxFlow == bestCut
~~~

Cần tính lát cắt theo **chiều**, không cộng cung từ Bside quay về A. Nếu có hai cung song song cùng chiều, **cả hai đều góp dung lượng** khi cắt giữa hai đầu.

Ví dụ n=8, chỉ có \(2^8=256\) cách chia đỉnh thật — đủ nhỏ để kiểm tra kết quả F=19 và F=12 độc lập. Phương pháp này **không cần chạy một thuật toán max-flow khác**; nó dựa vào định nghĩa min-cut và định lý max-flow min-cut.

### Kiểm tra thêm bất biến

Với Result của Java:
- maxFlow ≥0.
- maxFlow == minCutCapacity.
- Tổng mọi sourceSent bằng maxFlow.
- Tổng mọi sinkReceived bằng maxFlow.
- 0≤sourceSent[i]≤sourceLimits[i] nếu có quota, tương tự sinkReceived.
- Không có cung thật nào được dùng vượt dung lượng.
- Đỉnh siêu đích **không** còn tới được từ siêu nguồn theo các cung dư dương.
- Nếu không có đường nào từ bất kỳ nguồn thật tới bất kỳ đích thật, maxFlow=0.
- Thêm một cung **có dung lượng 0** không thể tăng max-flow.
- Đổi thứ tự cung input **không làm đổi giá trị max-flow** (dù phân phối nguồn/đích có thể khác).
- Tăng một dung lượng cung mà không thay ràng buộc khác **không thể làm giảm giá trị tối ưu**.
- Với các nguồn/đích rời nhau, giá trị không vượt tổng quota nguồn, tổng quota đích hoặc bound B.

Lưu ý: **minCutCapacity được tính trên toàn mạng phụ**, không phải chỉ tổng cung gốc; khi có hạn mức, cung phụ có thể chính là các cung quyết định lát cắt.

## 16. Những lỗi phổ biến

1. **Chạy max-flow cho từng cặp nguồn–đích rồi cộng kết quả**, dùng trùng dung lượng cung trung gian.
2. **Nối ngược chiều cung phụ** thành nguồn thật→siêu nguồn hoặc siêu đích→đích thật.
3. **Dùng một hằng INF quá nhỏ**, vô tình giới hạn max-flow thật.
4. **Dùng Long.MAX_VALUE vô điều kiện mà không kiểm tra overflow**, khiến tổng luồng hoặc min-cut có thể tràn.
5. **Đặt cap của siêu nguồn bằng 1 cho mỗi nguồn** khi đề không nói mỗi nguồn chỉ phát một đơn vị.
6. **Đặt cap của đích phụ bằng quota nhận và tưởng đó là nhu cầu tối thiểu**; nó chỉ là giới hạn trên.
7. **Cho cùng một đỉnh nằm trong cả tập nguồn và đích** mà không xử lý đường s*→x→t* nhân tạo.
8. **Không loại nguồn/đích trùng ID trong từng tập**, dễ tạo nhiều cung phụ cho cùng terminal và làm sai quota.
9. **Xem nguồn là nút không thể nhận luồng hoặc đích không thể chuyển tiếp** mà vẫn giữ các cung gốc trái với chính sách ấy.
10. **Cho nguồn quota a nhưng lại coi đó là tổng lượng đi ra**, dù nó còn nhận luồng từ nguồn khác.
11. **Lẫn cung ngược dư với cung ngược vật lý**, làm sai mô hình mạng có hướng.
12. **Không cập nhật cung ngược khi tăng luồng**, khiến thuật toán không hủy/phân phối lại luồng cũ.
13. **Cho phép dung lượng âm**, không thuộc mô hình max-flow chuẩn.
14. **Bỏ cung song song vì hai đầu trùng**, làm giảm tổng dung lượng khả dụng.
15. **Coi self-loop có dung lượng rất lớn làm tăng max-flow**, dù nó không chuyển luồng tới đích khác.
16. **Đánh dấu một đỉnh đã thăm vĩnh viễn trên mọi lần tăng luồng**, chặn những đường khác có thể dùng lại một phần khả năng dư.
17. **Không làm mới mảng next khi BFS xây level graph mới**, khiến Dinic bỏ sót cung.
18. **Không kiểm tra residual>0 trước khi đi cạnh**, tạo đường tăng không hợp lệ.
19. **Dùng BFS level theo cung vật lý nhưng không xét cung ngược dư**, bỏ mất đường tăng điều chỉnh luồng.
20. **Tính min-cut bằng dung lượng dư còn lại thay vì dung lượng ban đầu**, làm mất chứng chỉ tối ưu.
21. **Tính lát cắt trên cung ngược dư như cung gốc**, báo sai dung lượng cắt.
22. **Không tách giới hạn tổng lưu lượng qua nút với giới hạn phát ròng/nhận ròng**, áp sai quota.
23. **Tuyên bố đã đáp ứng mọi nhu cầu tối thiểu chỉ vì maxFlow lớn**, bỏ qua từng ràng buộc đích.
24. **Không phân biệt luồng một loại hàng với multi-commodity flow**, tưởng mỗi nguồn được gắn riêng một đích mà không thêm biến/ràng buộc.
25. **Dùng int cho tổng dung lượng lớn**, overflow tạo giá trị âm và phá thuật toán.
26. **Không xem xét đồ thị gốc không liên thông**, trong khi hai cụm nguồn–đích độc lập vẫn có thể đóng góp luồng.
27. **Quên kiểm chứng tổng sourceSent và sinkReceived**, không phát hiện lỗi bảo toàn luồng.
28. **Dùng DFS đệ quy không kiểm soát độ sâu** trên mạng rất lớn và gặp StackOverflowError.
29. **Không ghi rõ mỗi cung input là có hướng**, rồi tự động thêm chiều ngược vật lý khi không có trong đề.
30. **Nhầm tối đa hóa tổng luồng với tối đa hóa số đích được cấp đủ**, là hai hàm mục tiêu khác nhau.

## 17. Bài tập tự kiểm tra

**Câu 1.** Nhiều nguồn và nhiều đích được biến thành bài toán một nguồn một đích như thế nào?

**Đáp án:** Thêm siêu nguồn s*, nối s*→mỗi nguồn thật; thêm siêu đích t*, nối mỗi đích thật→t*. Giữ nguyên cung gốc, chạy max-flow một lần từ s* tới t*.

**Câu 2.** Vì sao không cộng kết quả max-flow của từng cặp nguồn–đích?

**Đáp án:** Những luồng riêng có thể cùng dùng một cung trung gian và vượt dung lượng thật. Cần một bài toán tổng thể chia sẻ các cung.

**Câu 3.** Nếu không có quota riêng, nên gán dung lượng cung phụ bằng gì?

**Đáp án:** Có thể lấy B bằng **tổng dung lượng các cung gốc hữu ích** (bỏ self-loop), tính bằng số nguyên đủ lớn và kiểm tra overflow. Mọi luồng tối đa không thể vượt B nên cung phụ không làm nghẽn giả.

**Câu 4.** Nguồn thật i có quota 7 trên cung s*→i thì 7 giới hạn đại lượng gì?

**Đáp án:** Giới hạn **lượng bơm ròng từ ngoài mạng qua siêu nguồn**. Nếu i có luồng đi vào từ đỉnh thật khác, tổng luồng đi ra khỏi i có thể lớn hơn 7 mà không vi phạm quota bơm ròng.

**Câu 5.** Cung t_j→t* có dung lượng 5 có bắt buộc đích j nhận ít nhất 5 không?

**Đáp án:** Không. Nó chỉ giới hạn nhận **tối đa 5**. Nhu cầu tối thiểu cần mô hình có cận dưới/luồng khả thi riêng.

**Câu 6.** Nếu một đỉnh vừa là nguồn vừa là đích, vì sao cần xử lý riêng?

**Đáp án:** Có thể xuất hiện đường s*→x→t* không qua mạng gốc, tạo luồng giả. Cần đặt hợp đồng terminal rời nhau hoặc tách vai trò bằng cấu trúc phù hợp.

**Câu 7.** Trong mạng 8 đỉnh ở mục 7, max-flow không quota bằng bao nhiêu?

**Đáp án:** **19**. Bốn cung vào hai đích có tổng capacity 8+2+6+3=19 và thuật toán tìm được luồng đạt 19.

**Câu 8.** Khi giới hạn nguồn [7,6] và đích [5,7], kết quả là gì?

**Đáp án:** **12**, vì tổng quota nhận là 12 và tồn tại luồng đạt 12. Một phương án bơm [7,5], nhận [5,7].

**Câu 9.** Tại sao cung ngược dư ban đầu có capacity 0?

**Đáp án:** Ban đầu chưa có luồng để hủy. Khi đẩy f qua cung xuôi, cung ngược dư tăng f để biểu diễn khả năng hoàn tác/điều chỉnh luồng đã gửi.

**Câu 10.** Vì sao sau Dinic phải có maxFlow == minCutCapacity?

**Đáp án:** Theo định lý max-flow min-cut, khi không còn đường tăng, tập đỉnh tới được từ s* trong mạng dư tạo một lát cắt có dung lượng đúng bằng luồng cực đại.

**Câu 11.** Có nhiều cung song song 0→1 capacity 4 và 3. Max-flow từ 0 tới 1 (không quota) là bao nhiêu?

**Đáp án:** **7**, vì hai cung là hai đường truyền độc lập; không được bỏ cung trùng đầu mút.

**Câu 12.** Mạng gốc có bắt buộc liên thông không?

**Đáp án:** Không. Các thành phần có cặp nguồn–đích của riêng mình vẫn có thể đóng góp luồng; ví dụ hai tuyến rời nhau có capacity 8 và 7 cho tổng 15.

**Câu 13.** Nếu một đỉnh có giới hạn xử lý tổng là 10, chỉ đặt cung s*→đỉnh ấy capacity 10 đã đủ chưa?

**Đáp án:** Chưa chắc. Nó giới hạn lượng **phát ròng**, không giới hạn lưu lượng nhận từ nơi khác rồi chuyển tiếp. Cần mô hình dung lượng nút, thường tách v_in và v_out.

**Câu 14.** Độ phức tạp tệ nhất của Dinic trên mạng phụ là gì?

**Đáp án:** Với V'=n+2 và E'=m+|S|+|T|, cận thời gian **O(V'^2 E')**, bộ nhớ **O(V'+E')**.

**Câu 15.** Nếu không có đường từ bất kỳ nguồn thật nào tới bất kỳ đích thật nào thì chuyện gì xảy ra?

**Đáp án:** Max-flow **0**, kể cả khi có các cung gốc dung lượng dương trong thành phần không liên quan. Siêu nguồn không tạo ra kết nối qua các cung gốc còn thiếu.

**Câu 16.** Muốn biết mỗi nguồn i giao bao nhiêu cho mỗi đích j, Result chỉ có sourceSent/sinkReceived đã đủ chưa?

**Đáp án:** Chưa. Hai danh sách chỉ chứa **tổng theo nguồn** và **tổng theo đích**; để khôi phục phân phối theo từng cặp cần **phân rã luồng trên các đường từ siêu nguồn tới siêu đích**, hoặc mô hình khác nếu nhiều loại hàng hóa phải được giữ riêng.

**Ghi nhớ:** Với **nhiều nguồn, nhiều đích**, thêm **siêu nguồn s*→mọi nguồn** và **mọi đích→siêu đích t***, giữ nguyên mạng gốc và chạy **một lần max-flow**. Cung phụ mang dung lượng B đủ lớn nếu không hạn mức, hoặc đúng quota cấp/nhận nếu có. Kết quả phải thỏa bảo toàn luồng và **max-flow = min-cut**. Đừng nhầm giới hạn trên với nhu cầu tối thiểu, đừng dùng chung một đỉnh làm cả nguồn và đích mà không xử lý, và đừng cộng các max-flow từng cặp trên cùng mạng.
