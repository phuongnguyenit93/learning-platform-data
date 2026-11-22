# Cận dưới, cận trên và chiều tối ưu

**Nhánh và cận** (*branch and bound*) là kỹ thuật tìm nghiệm tối ưu của một bài toán tổ hợp bằng cách chia không gian lời giải thành các **nhánh**, đồng thời dùng **cận toán học** để chứng minh rằng một số nhánh không thể cải thiện nghiệm tốt nhất đã biết. Nhánh bị chứng minh vô ích sẽ không cần duyệt tới lá.

Điều dễ nhầm nhất là **cận dưới (lower bound)** và **cận trên (upper bound)** không tự quyết định cách cắt tỉa. Ta còn phải biết bài toán đang **tối thiểu hóa** hay **tối đa hóa**, cận đó áp dụng cho tập lời giải nào, và giá trị **nghiệm khả thi tốt nhất đã biết** (*incumbent*) được dùng để so sánh.

Quy tắc cốt lõi:

- **Tối thiểu hóa:** cần một **cận dưới lạc quan** cho mọi nghiệm hoàn thành của nhánh. Nếu cận dưới **không nhỏ hơn** giá trị nghiệm khả thi tốt nhất, nhánh không thể cải thiện.
- **Tối đa hóa:** cần một **cận trên lạc quan** cho mọi nghiệm hoàn thành của nhánh. Nếu cận trên **không lớn hơn** giá trị nghiệm khả thi tốt nhất, nhánh không thể cải thiện.

Tính đúng dựa trên **chứng minh bất đẳng thức**, không dựa vào việc một giá trị “trông có vẻ tốt/xấu”. Bài học trình bày ý nghĩa các cận, cách xây cận từ bài toán thư giãn, bất biến cắt tỉa, hướng duyệt, phản ví dụ và hai chương trình Java 17+ trong cùng một tệp: **0/1 knapsack tối đa hóa lợi ích** và **assignment tối thiểu hóa chi phí**.

## 1. Không gian nhánh và nghiệm hoàn thành

Giả sử lời giải gồm một dãy quyết định. Tại một nút tìm kiếm \(s\), một số quyết định đã được chốt và các quyết định còn lại chưa biết. Gọi:

\[
\mathcal{F}(s)=\{\text{mọi nghiệm hoàn chỉnh, khả thi, có tiền tố là }s\}.
\]

Đó là **tập hoàn thành khả thi** của nhánh. Có thể tập này rỗng: không có cách đi tiếp để tạo nghiệm hợp lệ.

Ta cần phân biệt:

1. **Giá trị hiện tại:** tổng chi phí/lợi ích của các quyết định đã chốt ở nút s. Nó chưa chắc là giá trị của một **nghiệm hoàn chỉnh**.
2. **Giá trị nghiệm khả thi (incumbent):** một lời giải đầy đủ đã được kiểm tra ràng buộc, đủ điều kiện làm mốc so sánh.
3. **Cận của nhánh:** một số bảo đảm giới hạn giá trị của **mọi nghiệm trong \(\mathcal{F}(s)\)**, dù chưa liệt kê từng nghiệm.

Ví dụ, trong bài phân công n người cho n việc, sau khi phân công 2 người đầu, chi phí đã trả là 5. Con số 5 **chưa phải nghiệm đầy đủ** cho n người. Nếu vẫn còn người bắt buộc phải phân công, ta không thể dùng 5 như incumbent để loại nhánh khác, nhất là khi các chi phí có thể âm hoặc những việc còn lại có chi phí khác 0.

Với bài chọn đồ vật trong giới hạn sức chứa, một tập đồ vật đang chọn **đã là nghiệm khả thi**, vì các đồ vật còn lại có thể bỏ. Do đó giá trị hiện tại **có thể** được dùng để cập nhật incumbent cho bài toán “không bắt buộc dùng hết sức chứa”.

**Câu hỏi đầu tiên khi viết nhánh và cận:** từ trạng thái dở dang này, nghiệm hoàn chỉnh có bắt buộc làm thêm quyết định nào không? Chỉ từ đó mới biết giá trị hiện tại có được dùng làm mốc nghiệm khả thi hay chưa.

## 2. Định nghĩa đúng cận dưới và cận trên

Cho một hàm mục tiêu \(f(x)\) và tập hoàn thành khả thi \(\mathcal{F}(s)\).

**Cận dưới** \(LB(s)\) thỏa:

\[
\forall x\in\mathcal{F}(s):\qquad LB(s)\le f(x).
\]

Nghĩa là mọi nghiệm hoàn thành trong nhánh đều có giá trị **ít nhất** bằng cận dưới.

**Cận trên** \(UB(s)\) thỏa:

\[
\forall x\in\mathcal{F}(s):\qquad f(x)\le UB(s).
\]

Nghĩa là mọi nghiệm hoàn thành trong nhánh đều có giá trị **nhiều nhất** bằng cận trên.

Nếu \(\mathcal{F}(s)\) rỗng, có thể loại nhánh bằng kiểm tra **không khả thi** thay vì cố gán một cận số học. Trong mã, cần xử lý nhánh bất khả thi rõ ràng; không nên giả vờ đó là chi phí 0.

### Cận nào cần cho chiều tối ưu nào?

| Mục tiêu | Incumbent B là gì? | Cận lạc quan cần có | Điều kiện loại nhánh khi chỉ cần một nghiệm tối ưu |
|---|---|---|---|
| **MIN** \(f(x)\) | **Cận trên toàn cục**: chi phí của một nghiệm hoàn chỉnh khả thi đã tìm thấy | **LB(s)** ≤ chi phí của mọi nghiệm hoàn thành nhánh | **LB(s) ≥ B** |
| **MAX** \(f(x)\) | **Cận dưới toàn cục**: lợi ích của một nghiệm hoàn chỉnh khả thi đã tìm thấy | **UB(s)** ≥ lợi ích của mọi nghiệm hoàn thành nhánh | **UB(s) ≤ B** |

Đây là hai trường hợp đối ngẫu nhưng **không đối xứng về phép so sánh**: bài MAX so **upper bound với lower bound toàn cục**, bài MIN so **lower bound với upper bound toàn cục**.

Nếu muốn **liệt kê mọi nghiệm đạt giá trị tối ưu**, cắt ngay ở dấu bằng có thể bỏ các nghiệm có giá trị **bằng** incumbent. Khi ấy có thể dùng điều kiện nghiêm ngặt hơn:

- MIN: chỉ loại bằng cận khi \(LB(s)>B\).
- MAX: chỉ loại bằng cận khi \(UB(s)<B\).

Ngoài ra phải ghi nhận các nghiệm hòa, không chỉ lưu nghiệm cải thiện. Nếu chỉ cần **giá trị tối ưu** hoặc **một nghiệm tối ưu**, quy tắc có dấu bằng ở bảng trên là hợp lệ.

## 3. Tại sao cắt tỉa bằng cận lại đúng?

Giả sử bài **tối thiểu hóa** đang có một nghiệm đầy đủ với chi phí B. Nếu chứng minh được:

\[
\forall x\in\mathcal{F}(s):\quad f(x)\ge LB(s)\ge B,
\]

thì **không một nghiệm nào trong nhánh s có chi phí nhỏ hơn B**. Loại s không thể làm mất cơ hội cải thiện B. Kể cả khi có nghiệm chi phí đúng B, ta vẫn đã giữ được ít nhất một nghiệm tối ưu có giá trị đó khi dừng tìm kiếm.

Với bài **tối đa hóa**, chứng minh tương tự:

\[
\forall x\in\mathcal{F}(s):\quad f(x)\le UB(s)\le B.
\]

Không nghiệm nào trong nhánh có lợi ích lớn hơn B, nên nhánh không thể cải thiện.

**Điểm cần nhớ:** cận **có thể lỏng** (không sát với nghiệm tốt nhất của nhánh) nhưng **không được sai hướng**. Một cận lỏng làm thuật toán duyệt nhiều hơn; một cận quá “lạc quan sai chiều” có thể **loại mất nghiệm tối ưu**.

Ví dụ MAX thực sự có nghiệm đạt 150 trong nhánh. Nếu dự đoán tùy tiện \(UB=130\), việc loại nhánh vì 130≤B=140 sẽ bỏ mất nghiệm 150. Giá trị 130 **không phải cận trên hợp lệ** vì không ≥ mọi nghiệm khả thi của nhánh.

## 4. Xây cận bằng cách thư giãn ràng buộc

Một cách xây cận chắc chắn đúng là giải **bài toán thư giãn** (*relaxation*): nới lỏng một số điều kiện để tập phương án cho phép **lớn hơn hoặc bằng** tập nghiệm hoàn thành thật.

Giả sử \(\mathcal{F}(s)\subseteq\mathcal{R}(s)\), với \(\mathcal{R}(s)\) là tập phương án của bài toán thư giãn. Khi đó:

**Bài MAX:**

\[
\max_{x\in\mathcal{F}(s)}f(x)
\le
\max_{y\in\mathcal{R}(s)}f(y)=UB(s).
\]

Nghiệm tối ưu của bài toán **dễ hơn do bỏ ràng buộc** là cận trên lạc quan cho bài toán gốc.

**Bài MIN:**

\[
\min_{y\in\mathcal{R}(s)}f(y)=LB(s)
\le
\min_{x\in\mathcal{F}(s)}f(x).
\]

Nghiệm tối ưu của bài toán thư giãn là cận dưới lạc quan cho bài toán gốc.

Ví dụ:

- **0/1 knapsack MAX:** cho phép lấy **một phần** đồ vật (fractional knapsack) ⇒ lợi ích tối ưu của bài thư giãn **ít nhất** lợi ích 0/1 tối ưu ⇒ có **UB**.
- **Phân công MIN:** tạm cho mỗi người chọn việc rẻ nhất **mà không cần khác việc nhau** ⇒ chi phí thư giãn **không lớn hơn** chi phí phân công thật ⇒ có **LB**.
- **TSP MIN:** có thể dùng một cấu trúc thư giãn rẻ hơn tour hợp lệ để tạo **LB**, nhưng phải chứng minh điều kiện liên hệ giữa lời giải thư giãn và mọi tour.
- **Chọn tập MAX:** bỏ một số ràng buộc xung đột, hoặc cộng toàn bộ lợi ích dương của các phần tử còn lại, có thể cho UB hợp lệ dù lỏng.

Không được tự động dùng kết quả của một bài toán phụ **không thật sự là thư giãn**. Nếu thuật toán “ước lượng” vô tình loại một số phương án hợp lệ, nó có thể trả số tốt theo sai hướng và làm mất tính đúng của cắt tỉa.

## 5. Ví dụ MAX: ba lô 0/1 và cận trên

Bài toán **0/1 knapsack**: cho n đồ vật, mỗi đồ vật i có trọng lượng \(w_i>0\), giá trị \(v_i\ge0\); sức chứa C. Chọn mỗi đồ vật **tối đa một lần**, tổng trọng lượng ≤C, tối đa tổng giá trị.

Dữ liệu:

| Chỉ số i | Trọng lượng \(w_i\) | Giá trị \(v_i\) | Mật độ \(v_i/w_i\) |
|---:|---:|---:|---:|
| 0 | 2 | 40 | 20 |
| 1 | 3 | 50 | 16⅔ |
| 2 | 5 | 100 | 20 |
| 3 | 4 | 60 | 15 |

Với **C=8**, phương án chọn **đồ vật 1 và 2** có tổng trọng lượng \(3+5=8\), tổng giá trị \(50+100=\boxed{150}\). Chỉ số ở đây là **chỉ số dữ liệu gốc**, không phải vị trí sau khi sắp xếp.

### Trạng thái tìm kiếm

Duyệt các đồ vật theo chỉ số tăng. Trạng thái gồm:

- `index`: đồ vật tiếp theo cần quyết định chọn hay bỏ;
- `usedWeight`: tổng trọng lượng đã chọn;
- `currentValue`: tổng giá trị đã chọn;
- `take[i]`: lựa chọn đã chốt ở các chỉ số trước index.

Tại mỗi đồ vật, thử nhánh **chọn** (nếu còn sức chứa) và nhánh **bỏ**. Bất kỳ tập đã chọn nào không vượt C đều là nghiệm khả thi: ta có thể bỏ tất cả đồ vật còn lại. Do đó `currentValue` là **cận dưới khả thi cho bài MAX toàn cục**, và có thể cập nhật `bestValue` ngay cả ở nút chưa tới cuối danh sách.

### Cận trên đơn giản, chắc chắn đúng

Tại một nút, ta có thể **bỏ qua ràng buộc sức chứa của các đồ vật còn lại** và giả vờ lấy được **toàn bộ** chúng. Vì mọi \(v_i\ge0\), mọi phương án tiếp theo thỏa:

\[
\boxed{UB(index,currentValue)=currentValue+\sum_{j=index}^{n-1}v_j.}
\]

Cận này hợp lệ vì không phương án hoàn chỉnh nào có thể thu lợi nhiều hơn tổng **toàn bộ giá trị không âm còn lại**. Nó có thể rất lỏng vì đã bỏ qua sức chứa, nhưng không thể vô tình đánh giá **thấp hơn** giá trị của một phương án thật.

Tại gốc, \(UB=40+50+100+60=\boxed{250}\). Đây **không phải đáp án**; đó chỉ là lời hứa lạc quan rằng tối ưu không thể vượt 250.

Nếu đã tìm được `bestValue=150` và tại một nhánh tính được `UB=140`, không cần đi sâu vào nhánh đó vì nó không thể cải thiện 150.

**Quan trọng:** cận `currentValue + tổng mọi giá trị còn lại` như trên đòi **giá trị đồ vật không âm**. Nếu có giá trị âm và được phép bỏ đồ vật, cộng **cả** giá trị âm có thể làm UB thấp hơn nghiệm khả thi. Khi cho phép giá trị âm, có thể dùng tổng \(\sum\max(0,v_j)\) hoặc một cận khác được chứng minh; mã Java phía dưới **từ chối giá trị âm** để công thức không bị dùng sai.

### Cận trên mạnh hơn bằng fractional knapsack

Cho phép lấy **một phần** của đồ vật còn lại, rồi lấp sức chứa bằng thứ tự giảm dần của \(v/w\), ta thu được nghiệm tối ưu của bài fractional knapsack, cũng là **cận trên hợp lệ** cho bài 0/1.

Ở gốc ví dụ, lấy đầy đủ các đồ vật có mật độ 20: đồ vật 0 (2,40) và 2 (5,100). Đã dùng 7 đơn vị trọng lượng, còn 1. Có thể lấy **1/3 đồ vật 1** với lợi ích \(50/3\). Cận thư giãn:

\[
UB_{\text{fractional}}=40+100+\frac{50}{3}
=\frac{470}{3}\approx156.67.
\]

Đây là cận **chặt hơn 250**, vẫn ≥ giá trị tối ưu 0/1 là 150. Nếu giá trị mục tiêu là số nguyên, có thể dùng \(\lfloor470/3\rfloor=156\) làm cận trên nguyên, miễn phép tính phân số và làm tròn được thực hiện **chính xác**.

Ví dụ Java phía dưới **chủ động dùng cận 250 kiểu tổng giá trị còn lại**, vì dễ chứng minh và cài đặt bằng số nguyên có kiểm tra overflow. Muốn thay bằng fractional UB trong sản phẩm thực tế, cần sắp theo mật độ, tính phần lẻ, giữ đúng điều kiện phần đã chọn và cẩn thận với sai số `double`: làm tròn xuống sai có thể tạo một UB quá nhỏ và **prune sai**. Có thể dùng số nguyên/phân số chính xác hoặc làm tròn lên an toàn sau khi chứng minh.

## 6. Ví dụ MIN: phân công công việc và cận dưới

Cho ma trận `cost[row][col]`: chi phí giao **người row** cho **công việc col**. Mỗi người phải nhận **đúng một việc**, mỗi việc được giao cho **đúng một người**. Mục tiêu là tối thiểu hóa tổng chi phí.

Ma trận 4×4:

| Người \ Việc | 0 | 1 | 2 | 3 |
|---:|---:|---:|---:|---:|
| 0 | 9 | **2** | 7 | 8 |
| 1 | **6** | 4 | 3 | 7 |
| 2 | 5 | 8 | **1** | 8 |
| 3 | 7 | 6 | 9 | **4** |

Một phương án tối ưu:

~~~text
Người 0 -> việc 1: chi phí 2
Người 1 -> việc 0: chi phí 6
Người 2 -> việc 2: chi phí 1
Người 3 -> việc 3: chi phí 4
Tổng: 2 + 6 + 1 + 4 = 13
~~~

Vì mỗi việc khác nhau, đây là một **nghiệm hoàn chỉnh và khả thi** chi phí **13**, dùng được làm incumbent **B=13**.

### Trạng thái

Xử lý các người theo thứ tự 0,1,...,n-1. Tại nút có:

- `row`: người tiếp theo cần gán;
- `usedColumns[c]`: việc c đã được giao hay chưa;
- `currentCost`: chi phí những người trước row;
- `assignment[row]`: việc đã chọn cho từng người đã xử lý.

Ở mỗi row, chọn một việc **chưa dùng**. Khi gán đủ n người, ta có một phương án đầy đủ. **Chỉ lúc đó** mới cập nhật incumbent. Không được xem `currentCost` của một prefix chưa đủ n người như tổng chi phí cuối cùng.

### Cận dưới bằng cách bỏ ràng buộc cạnh tranh việc

Ở một nút, giả sử tập công việc chưa dùng là U. Đối với mỗi người r còn lại, lấy **chi phí nhỏ nhất trong U**:

\[
m_r=\min_{c\in U}cost[r][c].
\]

Tính:

\[
\boxed{LB(row,currentCost)
=currentCost+\sum_{r=row}^{n-1}m_r.}
\]

Đây là **cận dưới**, vì mỗi người còn lại trong mọi phương án thật phải lấy một việc trong U, nên chi phí người đó ≥ \(m_r\). Bài toán thư giãn cho nhiều người **cùng chọn một việc rẻ nhất**, trong khi phân công thật phải khác việc nhau; việc bỏ ràng buộc chỉ có thể làm chi phí thư giãn nhỏ hơn hoặc bằng tối ưu thật.

Tại **gốc** (chưa dùng việc nào), các chi phí nhỏ nhất theo hàng lần lượt là \(2,3,1,4\), nên:

\[
LB_{\text{root}}=2+3+1+4=\boxed{10}.
\]

Giá trị 10 **không phải một phương án phân công hợp lệ**: người 1 thích việc 2 với chi phí 3, nhưng người 2 cũng thích việc 2 với chi phí 1. Do đó không thể tự kết luận đáp án bằng 10. Bài toán thật có nghiệm tối ưu 13 và thỏa bất đẳng thức \(10\le13\).

Giả sử đã tìm được phương án đủ n người chi phí **13**. Nếu một nhánh khác có `LB=15`, tất cả phương án hoàn thành nhánh ấy có chi phí ít nhất 15; có thể loại nhánh mà không bỏ mất nghiệm nào cải thiện 13.

### Chi phí âm có làm sai cận dưới này không?

Không. Với **bài phân công bắt buộc mỗi người nhận một việc**, mỗi người còn lại luôn phải nhận một cột trong U; dù chi phí âm, giá trị thực của họ vẫn ≥ min trong U. Cận tổng các min hàng **vẫn đúng** nếu dùng số học không tràn. Vì vậy mã Java minh họa có thể chấp nhận chi phí âm.

Ngược lại, quy tắc **“nếu currentCost ≥ bestCost thì prune”** không an toàn nếu có thể gặp các chi phí âm ở những hàng chưa gán. Ví dụ prefix đã tốn 10 nhưng hàng tiếp theo có chi phí -8; tổng có thể giảm xuống 2. Phải dùng **cận dưới đúng cho mọi phần hoàn thành**, không chỉ tổng chi phí hiện tại.

## 7. Bất biến về incumbent và kiểm tra hướng tối ưu

**Incumbent** phải là giá trị của ít nhất một nghiệm **hoàn chỉnh, khả thi**; trừ trường hợp có thể xây một nghiệm mặc định hợp lệ như tập rỗng ở knapsack MAX.

Trong bài MIN, incumbent là **cận trên toàn cục**:

\[
OPT_{\min}\le B,
\]

vì tối ưu không thể tệ hơn một nghiệm khả thi đã tìm thấy. Khi tìm nghiệm mới có chi phí nhỏ hơn, B **giảm**.

Trong bài MAX, incumbent là **cận dưới toàn cục**:

\[
OPT_{\max}\ge B,
\]

vì tối ưu ít nhất bằng lợi ích của một nghiệm khả thi. Khi tìm nghiệm có lợi ích lớn hơn, B **tăng**.

Đừng nhầm cận toàn cục với cận trên/dưới **của từng nhánh**. Cả hai đều là các đại lượng số học, nhưng có vai trò ngược nhau trong phép cắt tỉa.

| Điều kiện | MIN | MAX |
|---|---|---|
| Tìm được nghiệm khả thi tốt hơn | `value < best` | `value > best` |
| Cận cho một nhánh chưa duyệt hết | **LB** lạc quan | **UB** lạc quan |
| Nhánh không thể cải thiện incumbent | `LB >= best` | `UB <= best` |
| Incumbent cải thiện theo thời gian | **Giảm dần** | **Tăng dần** |
| Ưu tiên thăm nhánh hứa hẹn | LB **nhỏ hơn** | UB **lớn hơn** |

Một cách nhớ: **MAX hỏi “tối đa có thể đạt bao nhiêu?”; MIN hỏi “tối thiểu bắt buộc phải tốn bao nhiêu?”**. Trả lời hai câu hỏi bằng cận có chứng minh rồi so với nghiệm tốt nhất đang giữ.

## 8. Sinh nhánh, đánh giá cận và thứ tự thăm

Một vòng lặp branch-and-bound có dạng:

~~~text
search(state):
    if state mô tả một nghiệm hoàn chỉnh:
        updateIncumbentIfBetter(state)
        return

    bound = optimisticBound(state)

    if incumbent đã tồn tại AND bound không thể vượt incumbent:
        return

    for choice in availableChoices(state):
        apply(choice)
        search(nextState)
        undo(choice)
~~~

Ở một số bài MAX như knapsack, trạng thái hiện tại đã là một nghiệm khả thi, nên `updateIncumbentIfBetter` có thể chạy **trước khi đến lá**. Nhưng phải khẳng định được phần còn lại có thể bỏ mà vẫn thỏa đặc tả.

### Nhánh nào trước?

Thứ tự thăm không làm thay đổi **tính đúng** nếu cận hợp lệ và tất cả nhánh không bị loại được duyệt. Nhưng nó ảnh hưởng rất lớn tới số nút:

- MAX: thử nhánh **có thể tạo giá trị lớn sớm**, giúp incumbent tăng; từ đó nhiều UB của nhánh khác sẽ ≤B.
- MIN: thử nhánh **có thể tạo chi phí nhỏ sớm**, giúp incumbent giảm; từ đó nhiều LB của nhánh khác sẽ ≥B.
- Với các bài toán lớn, có thể duy trì hàng đợi ưu tiên (*best-first search*) theo UB giảm dần cho MAX hoặc LB tăng dần cho MIN, thay vì DFS.

Mã Java phía dưới dùng **DFS và thứ tự đơn giản** để dễ chứng minh. Có thể cải tiến bằng cách thử lựa chọn hứa hẹn trước, nhưng **heuristic chỉ được đổi thứ tự**, không được tự loại nhánh khi chưa có cận hợp lệ.

### Cận tốt và chi phí tính cận

Cận càng **chặt**, thường càng cắt được nhiều nhánh. Tuy nhiên một cận mạnh hơn có thể mất nhiều thời gian để tính. Tổng hiệu năng là kết quả của đánh đổi giữa:

1. Chi phí tính cận ở mỗi nút.
2. Số nút được cắt bớt.
3. Tốc độ tìm được nghiệm khả thi tốt.
4. Chi phí lưu trạng thái và thứ tự ưu tiên nhánh.

Một cận yếu nhưng rất rẻ đôi khi tốt hơn một cận mạnh mà mỗi lần tính quá đắt. **Tính đúng** chỉ cần cận đúng hướng; **hiệu năng** còn cần thực nghiệm trên đầu vào đại diện.

## 9. Java 17+: cả MAX lẫn MIN với cận đúng hướng

Chương trình gồm hai bộ giải độc lập:

- **Knapsack MAX:** dùng UB = giá trị hiện tại + **tổng giá trị mọi đồ vật chưa xét**, bỏ ràng buộc sức chứa; cập nhật incumbent từ mọi tập đã chọn hợp lệ. Lựa chọn theo chỉ số gốc.
- **Assignment MIN:** dùng LB = chi phí hiện tại + **tổng chi phí nhỏ nhất của từng người còn lại trên các công việc chưa giao**, tạm bỏ ràng buộc mỗi công việc chỉ giao một người ở phần còn lại; chỉ cập nhật incumbent khi đủ n người.

Để tránh nhầm trạng thái không có nghiệm và nghiệm có giá trị rất lớn/nhỏ, phần MIN dùng cờ `found`. Các phép cộng `long` dùng **`Math.addExact`** để báo lỗi nếu tràn số; chương trình không im lặng cho kết quả sai. Demo chấp nhận **giá trị đồ vật không âm**, **trọng lượng đồ vật dương**, **chi phí phân công có thể âm**.

Lưu tệp **BranchBoundBoundsDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

public class BranchBoundBoundsDemo {
    record KnapsackResult(long maxValue, List<Integer> selectedIndices) {}
    record AssignmentResult(long minCost, List<Integer> columnByRow) {}

    static KnapsackResult maxKnapsack(
        int[] weights, long[] values, int capacity
    ) {
        Objects.requireNonNull(weights, "weights");
        Objects.requireNonNull(values, "values");
        if (weights.length != values.length || capacity < 0) {
            throw new IllegalArgumentException("invalid knapsack inputs");
        }
        for (int i = 0; i < weights.length; i++) {
            if (weights[i] <= 0 || values[i] < 0) {
                throw new IllegalArgumentException(
                    "weights must be positive, values nonnegative"
                );
            }
        }
        return new KnapsackSearch(weights, values, capacity).run();
    }

    static final class KnapsackSearch {
        private final int[] weight;
        private final long[] value;
        private final int capacity;
        private final boolean[] chosen;
        private boolean[] bestChosen;
        private long bestValue = 0L;  // Empty set is feasible.

        KnapsackSearch(int[] weight, long[] value, int capacity) {
            this.weight = weight;
            this.value = value;
            this.capacity = capacity;
            chosen = new boolean[weight.length];
            bestChosen = new boolean[weight.length];
        }

        KnapsackResult run() {
            search(0, 0, 0L);
            List<Integer> indices = new ArrayList<>();
            for (int i = 0; i < bestChosen.length; i++) {
                if (bestChosen[i]) {
                    indices.add(i);
                }
            }
            return new KnapsackResult(bestValue, List.copyOf(indices));
        }

        void search(int index, int usedWeight, long currentValue) {
            // This prefix is a complete feasible subset if we skip
            // every remaining item: it may improve the incumbent.
            if (currentValue > bestValue) {
                bestValue = currentValue;
                bestChosen = chosen.clone();
            }

            // An optimistic UPPER BOUND for MAX: pretend all
            // remaining items are free to take regardless of weight.
            long upperBound = currentValue;
            for (int j = index; j < value.length; j++) {
                upperBound = Math.addExact(upperBound, value[j]);
            }
            if (upperBound <= bestValue || index == weight.length) {
                return;
            }

            // Branch 1: take this item, if it fits.
            if (weight[index] <= capacity - usedWeight) {
                chosen[index] = true;
                search(index + 1,
                    usedWeight + weight[index],
                    Math.addExact(currentValue, value[index]));
                chosen[index] = false;  // Undo the choice.
            }

            // Branch 2: skip this item.
            search(index + 1, usedWeight, currentValue);
        }
    }

    static AssignmentResult minAssignment(int[][] costs) {
        Objects.requireNonNull(costs, "costs");
        int n = costs.length;
        if (n == 0) {
            throw new IllegalArgumentException("nonempty matrix required");
        }
        for (int[] row : costs) {
            if (row == null || row.length != n) {
                throw new IllegalArgumentException(
                    "cost matrix must be square"
                );
            }
        }
        return new AssignmentSearch(costs).run();
    }

    static final class AssignmentSearch {
        private final int[][] cost;
        private final int n;
        private final boolean[] usedColumn;
        private final int[] current;
        private int[] bestAssignment;
        private boolean found = false;
        private long bestCost = 0L;

        AssignmentSearch(int[][] cost) {
            this.cost = cost;
            n = cost.length;
            usedColumn = new boolean[n];
            current = new int[n];
            Arrays.fill(current, -1);
        }

        AssignmentResult run() {
            search(0, 0L);
            if (!found) {
                throw new IllegalStateException("no assignment found");
            }
            List<Integer> result = new ArrayList<>();
            for (int col : bestAssignment) {
                result.add(col);
            }
            return new AssignmentResult(bestCost, List.copyOf(result));
        }

        // Optimistic LOWER BOUND for MIN. Each remaining person may
        // choose the cheapest still-unused column independently.
        long lowerBound(int row, long currentCost) {
            long lb = currentCost;
            for (int person = row; person < n; person++) {
                long min = Long.MAX_VALUE;
                for (int col = 0; col < n; col++) {
                    if (!usedColumn[col]) {
                        min = Math.min(min, cost[person][col]);
                    }
                }
                if (min == Long.MAX_VALUE) {
                    throw new IllegalStateException("no available column");
                }
                lb = Math.addExact(lb, min);
            }
            return lb;
        }

        void search(int row, long currentCost) {
            if (row == n) {
                // Only a FULL assignment is feasible for the MIN
                // problem, so update the incumbent at a leaf.
                if (!found || currentCost < bestCost) {
                    found = true;
                    bestCost = currentCost;
                    bestAssignment = current.clone();
                }
                return;
            }

            if (found && lowerBound(row, currentCost) >= bestCost) {
                return;
            }

            for (int col = 0; col < n; col++) {
                if (usedColumn[col]) {
                    continue;
                }

                usedColumn[col] = true;
                current[row] = col;

                search(row + 1,
                    Math.addExact(currentCost, cost[row][col]));

                current[row] = -1;
                usedColumn[col] = false;
            }
        }
    }

    public static void main(String[] args) {
        KnapsackResult bag = maxKnapsack(
            new int[] {2, 3, 5, 4},
            new long[] {40, 50, 100, 60}, 8
        );
        System.out.println("Knapsack max value: " + bag.maxValue());
        System.out.println("Knapsack indices: " + bag.selectedIndices());
        System.out.println("Empty knapsack: "
            + maxKnapsack(new int[0], new long[0], 0).maxValue());

        int[][] costs = {
            {9, 2, 7, 8},
            {6, 4, 3, 7},
            {5, 8, 1, 8},
            {7, 6, 9, 4}
        };
        AssignmentResult plan = minAssignment(costs);
        System.out.println("Assignment min cost: " + plan.minCost());
        System.out.println("Assignment columns: " + plan.columnByRow());

        System.out.println("Negative assignment cost: "
            + minAssignment(new int[][] {{-7}}).minCost());
    }
}
~~~

Biên dịch và chạy với **JDK 17 trở lên**:

~~~bash
javac BranchBoundBoundsDemo.java
java BranchBoundBoundsDemo
~~~

**Stdout chính xác:**

~~~text
Knapsack max value: 150
Knapsack indices: [1, 2]
Empty knapsack: 0
Assignment min cost: 13
Assignment columns: [1, 0, 2, 3]
Negative assignment cost: -7
~~~

### Vì sao phần Java không đổi nhầm chiều cận?

**Knapsack:** `upperBound` là cận **trên** của mọi phương án có thể kéo dài trạng thái, vì nó cho phép lấy mọi đồ vật còn lại kể cả khi không đủ sức chứa. Khi `upperBound <= bestValue`, không có nghiệm tốt hơn incumbent. `bestValue` bắt đầu từ **0**, vì tập rỗng là nghiệm hợp lệ trong bài chọn không quá sức chứa C với giá trị không âm.

**Assignment:** `lowerBound` là cận **dưới** vì nó cho phép các người còn lại cùng chọn công việc rẻ nhất nếu muốn, bỏ ràng buộc không được trùng công việc. Khi `lowerBound >= bestCost`, nhánh không thể cho lời giải có chi phí thấp hơn incumbent. `found=false` cho tới lá đầu tiên, vì prefix chưa phân công hết không phải nghiệm hoàn chỉnh. Cận được kiểm tra ngay cả khi một số chi phí âm, thay vì dùng quy tắc `currentCost >= bestCost` không an toàn.

**Hoàn tác:** khi bỏ một đồ vật đã chọn, `chosen[index]` trở về false. Khi rời một phân công, `current[row]=-1` và `usedColumn[col]=false`. Mỗi nhánh anh em đều bắt đầu với trạng thái cha như ban đầu.

**Số học:** mã dùng `Math.addExact` để phát hiện tràn `long`; nếu tổng vượt miền biểu diễn, chương trình báo lỗi thay vì tạo cận/đáp án sai. Với dữ liệu đầu vào lớn đến mức không thể cấp phát bảng hoặc stack đệ quy quá sâu, cần thiết kế thêm kiểm tra tài nguyên và có thể dùng `BigInteger` cho giá trị lớn.

## 10. Phân tích tính đúng của cả hai bộ giải

### 10.1. Knapsack MAX

Bất biến tại `search(index, usedWeight, currentValue)`:

- `chosen[0..index-1]` biểu diễn đúng những quyết định chọn/bỏ đã chốt.
- `usedWeight <= capacity`.
- `currentValue` là tổng giá trị những đồ vật đã chọn và chính nó là một nghiệm khả thi nếu bỏ tất cả đồ vật còn lại.
- `bestValue` là giá trị lớn nhất của những nghiệm khả thi đã được ghi nhận cho tới lúc đó.

Mỗi đồ vật tiếp theo có đúng hai khả năng: **lấy nếu vừa sức chứa** hoặc **không lấy**. Tất cả tập đồ vật hợp lệ nằm trong ít nhất một đường từ gốc tới lá. Vì giá trị không âm và mọi lợi ích của phần còn lại được cộng vào UB, không nghiệm hoàn thành nào trong nhánh có giá trị >UB. Nếu UB≤bestValue, không bỏ mất cải thiện tối ưu; nếu UB>bestValue, ta tiếp tục thử hai nhánh tương ứng.

Mọi lần cập nhật `bestValue` đều đi kèm `chosen.clone()`, giữ một nghiệm có giá trị đúng đó. Sau khi toàn bộ cây tìm kiếm hoặc các nhánh bị loại an toàn được xử lý, giá trị trả về là tối ưu MAX.

### 10.2. Assignment MIN

Bất biến tại `search(row,currentCost)`:

- Những người 0..row-1 đã được gán mỗi người một việc khác nhau.
- `usedColumn` đánh dấu chính xác các việc đó.
- `currentCost` là tổng chi phí các phân công đã chốt.
- Nếu `found=true`, `bestCost` thuộc về **một phân công đầy đủ** được lưu trong `bestAssignment`.

Mọi phân công hợp lệ phải chọn một cột chưa dùng cho người hiện tại; vòng lặp thử **toàn bộ** các cột chưa dùng. Với những người chưa gán, mỗi chi phí thực tế ≥ chi phí rẻ nhất trong U. Vì vậy `lowerBound` ≤ tổng chi phí của mọi cách hoàn thành. Cắt khi `LB>=bestCost` không thể bỏ một phân công tốt hơn incumbent.

Mã cập nhật incumbent chỉ tại `row==n`, nên không dùng prefix thiếu người làm nghiệm. Sau khi xét hết các lựa chọn không bị cắt, `bestCost` là tối ưu MIN và `bestAssignment` là một phân công tương ứng.

### 10.3. Vì sao hai bài đều cần undo đúng?

Các nhánh ở cùng độ sâu chia sẻ mảng chọn/đánh dấu. Nếu không khôi phục `chosen[index]` hoặc `usedColumn[col]`, nhánh tiếp theo sẽ bị hiểu là đã có một quyết định mà nó chưa chọn, làm `generateChoices` và điều kiện hợp lệ sai. Cắt tỉa có thể hoàn toàn đúng nhưng toàn thuật toán vẫn sai vì **trạng thái rò rỉ**. Bất biến của quay lui là điều kiện đi cùng với chứng minh của cận.

## 11. Điều kiện dừng tối ưu: khi nào biết đã chứng minh xong?

Một số bài nhánh và cận chỉ trả được một nghiệm **tốt**, chưa chắc tối ưu, nếu tự dừng theo thời gian hoặc giới hạn số nút. Muốn chứng minh **tối ưu**, phải:

- Đã thăm đủ mọi nhánh cần thiết; hoặc
- Chứng minh mọi nhánh chưa thăm đều **không thể cải thiện incumbent** bằng cận hợp lệ.

Khi tập nhánh cần xét rỗng, và mọi nhánh bị loại có cận đúng, incumbent chính là tối ưu. Nếu hết thời gian trước khi hoàn tất, ta chỉ có thể báo **nghiệm tốt nhất hiện biết** cùng **cận toàn cục còn hiệu lực** và mức chênh lệch (*optimality gap*), nếu được duy trì chính xác.

Ví dụ MAX có incumbent 150 và các nhánh chưa thăm có UB lớn nhất 170: ta biết tối ưu nằm trong **[150,170]**, chưa thể nói 150 là tối ưu. Với MIN có incumbent 13 và các nhánh chưa thăm có LB nhỏ nhất 10: tối ưu nằm trong **[10,13]**, chưa thể khẳng định 13 tối ưu nếu chưa xử lý các nhánh hứa hẹn còn lại.

Để dùng cận toàn cục này khi dừng sớm, cần bảo đảm bộ dữ liệu nhánh chưa xử lý thực sự đại diện cho toàn bộ không gian chưa thăm; không được lấy cận của một nhánh riêng lẻ rồi gọi đó là cận của toàn bộ bài toán.

## 12. Độ phức tạp: cắt tỉa không bảo đảm đa thức

Nếu không cắt được nhánh nào đáng kể:

- **0/1 knapsack** có tối đa \(2^n\) phương án lấy/bỏ; cây nhị phân có \(O(2^n)\) nút. Mã tính UB bằng cách cộng đến n phần tử tại mỗi nút ⇒ cận thời gian **O(n·2^n)**. Có thể dùng mảng tổng hậu tố `suffixValue[index]` để tính UB **O(1)** mỗi nút, giảm một hệ số n khi chỉ xét chi phí bound; tổng thể vẫn có thể là hàm mũ.
- **Assignment n×n** có n! hoán vị gán cột. Ở mỗi nút, thuật toán tính LB bằng cách quét các người và cột còn lại, tối đa **O(n²)** công việc, còn khi sinh lựa chọn quét O(n) cột. Cận trên dễ hiểu là **O(n²·n!)** cho phiên bản chưa tối ưu; các cận chặt hơn có thể có khi phân tích số nút cụ thể.
- **Bộ nhớ làm việc** của hai ví dụ gồm mảng chọn/đánh dấu và stack đệ quy sâu tối đa n ⇒ **O(n)** ngoài dữ liệu đầu vào và một bản sao nghiệm tốt nhất. Nếu dùng **priority queue best-first** lưu nhiều nút, bộ nhớ có thể lớn hơn nhiều.
- Với MAX knapsack, việc sao chép mảng `chosen` mỗi lần cải thiện incumbent tốn O(n). Số lần cải thiện bị chặn bởi số nút đã thăm; phần này không làm thay đổi cận tổng quát O(n·2^n).
- Với Assignment, sao chép mảng `current` tại lá tối ưu mới tốn O(n), vẫn nằm trong cận O(n²·n!).

**Cắt tỉa giúp giảm số nút thường phải thăm**, đôi khi giảm rất mạnh, nhưng **không phải chứng minh thời gian đa thức** cho mọi đầu vào. Với các bài toán tổ hợp khó, nhánh và cận là công cụ tìm tối ưu chính xác dựa trên cấu trúc và cận; không phải phép màu loại bỏ độ khó.

## 13. Những lỗi nguy hiểm khi xây cận

### 13.1. Đảo cận theo chiều tối ưu

- MAX mà dùng `LB >= best` để cắt: LB là giá trị có thể **đã đạt**, không nói nhánh **không thể đạt hơn**. Không đúng.
- MIN mà dùng `UB <= best` để cắt: UB chỉ nói có một mức chi phí giới hạn phía trên, không chứng minh các nghiệm khác không thể thấp hơn. Không đúng.

**Chỉ cắt khi cận lạc quan không còn cơ hội cải thiện**: MAX dùng **UB≤best**, MIN dùng **LB≥best**.

### 13.2. Dùng “ước lượng” không có chứng minh

Một heuristic ước lượng tốt không nhất thiết là **cận**. Ví dụ knapsack MAX có thể đoán “nhánh này chắc chỉ đạt 140” nhưng nhánh thật có thể đạt 150. Dùng 140 như UB gây bỏ nghiệm tối ưu.

Được phép dùng heuristic để **chọn nhánh thăm trước**; chỉ dùng để **loại nhánh** khi chứng minh nó không vượt quá hay thấp hơn mọi nghiệm thật theo chiều cần thiết.

### 13.3. Lấy tổng hiện tại làm cận không đúng

- MIN với **chi phí âm**: tổng hiện tại có thể giảm về sau, nên `currentCost >= incumbent` chưa chứng minh không thể cải thiện.
- MAX với **lợi ích âm** và bắt buộc chọn thêm: giá trị hiện tại chưa chắc là một nghiệm đầy đủ, nên không thể mặc nhiên dùng làm incumbent.
- Trong bài MIN với các chi phí phần còn lại **không âm**, tổng hiện tại là một LB hợp lệ, nhưng thường **lỏng hơn** LB cộng các chi phí tối thiểu còn lại.

### 13.4. Bỏ ràng buộc nhưng dùng ngược kết quả thư giãn

Tập nghiệm thư giãn lớn hơn tập nghiệm thật:

- MAX: tối ưu thư giãn **cao hơn hoặc bằng**, tạo **UB**, không phải LB.
- MIN: tối ưu thư giãn **thấp hơn hoặc bằng**, tạo **LB**, không phải UB.

Nắm vững quan hệ bao hàm tập nghiệm \(\mathcal{F}\subseteq\mathcal{R}\) giúp tránh đảo dấu.

### 13.5. Làm tròn số thực sai hướng

Nếu UB của MAX được tính bằng số thực không chính xác rồi **làm tròn xuống quá mức**, kết quả có thể nhỏ hơn nghiệm thật, làm sai phép cắt. Nếu LB của MIN được **làm tròn lên quá mức**, nó có thể lớn hơn nghiệm thật, cũng gây cắt sai.

Với giá trị mục tiêu nguyên, có thể làm tròn bằng số học chính xác theo tính chất của cận (chẳng hạn floor của **UB thực chính xác** vẫn là UB nguyên). Không nên áp dụng quy tắc này cho kết quả floating-point đã có sai số mà không đánh giá độ an toàn.

### 13.6. Cắt dấu bằng khi phải tìm mọi nghiệm tối ưu

Nếu MAX đã biết best=150 và một nhánh có UB=150, nó có thể vẫn chứa **một nghiệm khác đạt 150**. Cắt là hợp lệ nếu chỉ cần **một** nghiệm tối ưu; không hợp lệ nếu bài yêu cầu **liệt kê tất cả** nghiệm hòa.

Tương tự MIN với LB=best. Hợp đồng đầu ra phải được xác định trước khi chọn điều kiện `<=` hoặc `>=`.

### 13.7. Không phân biệt trạng thái không khả thi

Nếu một nhánh không còn khả năng hoàn thành, nó có thể bị loại trực tiếp. Không được dùng số 0 làm đại diện chung cho “không tồn tại nghiệm”, nhất là với mục tiêu có thể nhận giá trị âm/0 hoặc với bài toán bắt buộc gán đủ quyết định.

Trong Assignment, `found` giúp bảo đảm `bestCost` chỉ được dùng sau khi đã có ít nhất một phân công đầy đủ. Khi chưa có incumbent, không có giá trị B hợp lệ cho kiểm tra `LB>=B`.

## 14. Các tối ưu nâng cao và đánh đổi

**Tìm incumbent tốt sớm.** Có thể dùng một heuristic xây một nghiệm đầy đủ khả thi trước (ví dụ một lựa chọn tham lam có kiểm tra ràng buộc), rồi khởi tạo B bằng giá trị đó. Phải xác nhận tính khả thi; một phép gán trùng công việc **không thể** tạo incumbent cho Assignment.

**Tiền tính cận.** Knapsack MAX có thể tính `suffixSum[i]` là tổng giá trị từ i tới n-1, nên `UB=currentValue+suffixSum[index]` được tính O(1). Cần xử lý overflow của tổng; phương pháp vẫn là cận lỏng bỏ sức chứa.

**Cận fractional.** Càng bám sát sức chứa, càng có cơ hội cắt nhánh. Nếu thực hiện với tỷ lệ nguyên, có thể dùng phép so sánh tích chéo bằng kiểu số đủ rộng hoặc `BigInteger` để tránh sai thứ tự mật độ khi tích vượt miền.

**Cận assignment chặt hơn.** Thư giãn “mỗi hàng chọn min độc lập” có thể nhiều người chọn một cột. Nếu giải chính xác bài assignment còn lại trên các cột chưa dùng, giá trị đó thực chất là chi phí tối ưu của **phần còn lại**, cận cực chặt nhưng việc giải bài con có thể đắt; đây là đánh đổi thời gian. Các relaxation khác (ví dụ ràng buộc tuyến tính) có thể cho cận tốt với chi phí phù hợp.

**Best-first và DFS.** DFS ít bộ nhớ, dễ hoàn tác; best-first chọn nút có bound hứa hẹn nhất nhưng thường phải lưu trạng thái nhiều nút trong hàng đợi ưu tiên. Cần đảm bảo mỗi trạng thái lưu trong hàng đợi là một bản sao độc lập hoặc một biểu diễn bất biến, không dùng chung mảng mutable sẽ bị undo ở DFS.

**Giảm đối xứng.** Nếu nhiều nhánh tương đương về ý nghĩa lời giải và việc chọn một đại diện được chứng minh đầy đủ, có thể bỏ nhánh đối xứng. Nhưng ràng buộc phá đối xứng không được bỏ một nghiệm quan trọng theo tiêu chí đầu ra.

## 15. Quy trình áp dụng vào bài toán mới

1. **Chốt bài MIN hay MAX** và định nghĩa hàm mục tiêu, ràng buộc đầy đủ.
2. **Định nghĩa trạng thái nhánh**: những quyết định đã chốt, tài nguyên đã dùng, ứng viên còn lại.
3. **Nêu rõ tập hoàn thành khả thi** \(\mathcal{F}(s)\) trong trạng thái đó.
4. **Tìm một nghiệm đầy đủ khả thi**, hoặc xác định khi nào một tiền tố đã tự là nghiệm hợp lệ, để thiết lập incumbent đúng.
5. **Xây cận lạc quan có chứng minh**: MAX cần UB, MIN cần LB.
6. **Kiểm tra hướng bất đẳng thức** với một ví dụ nhỏ đã biết tối ưu.
7. **Chọn thứ tự nhánh** để sớm có incumbent tốt, nhưng không dùng heuristic vô chứng minh để prune.
8. **Sửa trạng thái, đệ quy, hoàn tác đầy đủ**. Trước mỗi nhánh anh em, dữ liệu phải bằng trạng thái cha ban đầu.
9. **Cắt đúng điều kiện**: MAX `UB<=best`; MIN `LB>=best` khi chỉ cần một nghiệm tối ưu.
10. **Lưu lời giải hoàn chỉnh** khi cần; không chỉ lưu giá trị mục tiêu nếu đầu ra đòi phương án.
11. **Chú ý số âm, overflow, làm tròn và tie**, vì chúng ảnh hưởng tính hợp lệ của cận hoặc điều kiện cắt.
12. **Đánh giá hiệu năng** qua số nút được thăm, số nút bị cắt và thời gian tính cận trên đầu vào đại diện.
13. **Kiểm tra bằng vét cạn trên đầu vào nhỏ**, đối chiếu cả giá trị tối ưu và tính khả thi của phương án.

Một câu hỏi tự kiểm rất hiệu quả: **“Từ nhánh này, mọi nghiệm hoàn thành tốt nhất có thể tốt đến mức nào?”** Nếu không thể chứng minh bound trả lời đúng theo chiều tối ưu, chưa được dùng nó để loại nhánh.

## 16. Bài tập tự kiểm tra

**Bài 1 — Chiều cận.** Với bài MIN đã tìm nghiệm chi phí 40, một nhánh có LB=45. Có cắt được không? Nếu bài MAX đã tìm lợi ích 40, một nhánh có UB=45 thì sao?

*Đáp án:* **MIN cắt được**, vì mọi nghiệm nhánh có chi phí ≥45>40. **MAX chưa cắt được**, vì UB=45 vẫn cho phép tồn tại nghiệm nhánh có lợi ích >40.

**Bài 2 — Dấu bằng.** Bài MAX chỉ cần giá trị tối ưu, best=100 và UB của một nhánh đúng 100. Có cắt không? Nếu cần liệt kê mọi nghiệm tối ưu?

*Đáp án:* **Có thể cắt** khi chỉ cần một nghiệm hoặc giá trị tối ưu, vì nhánh không thể cải thiện. **Không thể cắt chỉ dựa vào dấu bằng** nếu vẫn phải tìm mọi nghiệm hòa.

**Bài 3 — Relaxation.** Bỏ ràng buộc sức chứa của knapsack MAX và lấy tổng giá trị còn lại tạo LB hay UB? Vì sao?

*Đáp án:* **UB**, vì bài thư giãn có thể chọn nhiều đồ vật hơn, nên lợi ích tối đa của nó không nhỏ hơn lợi ích của mọi phương án 0/1 khả thi.

**Bài 4 — Phân công.** Ở gốc ma trận 4×4 trong bài, LB=10 có phải một phương án phân công hoàn chỉnh đạt 10 không?

*Đáp án:* **Không.** Các giá trị min từng hàng có thể cùng dùng một cột, trái ràng buộc một việc chỉ giao một người. 10 chỉ là **cận dưới hợp lệ**; nghiệm tối ưu thật có chi phí 13.

**Bài 5 — Số âm.** Với Assignment MIN, prefix có chi phí 10, đã biết best=8, nhưng người còn lại có thể nhận việc chi phí -5. Có thể cắt chỉ vì currentCost=10≥8 không?

*Đáp án:* **Không.** Hoàn thành có thể có chi phí 5<8. Phải dùng LB có tính đến chi phí âm của các quyết định còn lại.

**Bài 6 — Giá trị âm trong knapsack.** Nếu một đồ vật chưa xét có giá trị -20 nhưng ta được quyền bỏ nó, dùng UB = currentValue + tổng **tất cả** giá trị còn lại có luôn đúng không?

*Đáp án:* **Không**, vì phương án thật có thể bỏ đồ vật -20, đạt giá trị cao hơn số tổng có cả -20. Có thể cộng \(\max(0,v_i)\) hoặc giới hạn bài vào `value>=0` như chương trình minh họa.

**Bài 7 — Incumbent.** Vì sao knapsack “chọn không quá C” có thể cập nhật best từ tiền tố, còn assignment bắt buộc gán đủ n người không thể cập nhật từ tiền tố?

*Đáp án:* Tập đồ vật đang chọn đã là phương án **đầy đủ khả thi** nếu quyết định bỏ phần còn lại. Nhưng phân công chưa đủ n người vẫn thiếu các quyết định bắt buộc nên chưa phải nghiệm hợp lệ.

**Bài 8 — Độ phức tạp.** Nếu knapsack có n vật và cận quá lỏng để cắt nhánh, vì sao bản Java có thể mất O(n·2^n) thay vì O(2^n)?

*Đáp án:* Cây có O(2^n) nút, nhưng mỗi nút cộng các giá trị còn lại để tính UB, tốn tới O(n). Tiền tính tổng hậu tố sẽ giúp mỗi bound O(1), song số nhánh vẫn có thể theo hàm mũ.

**Bài 9 — Bằng nhau trong MIN.** Với best=13 và LB=13 của một nhánh khác, quy tắc `LB>=best` loại được nhánh khi chỉ cần một phân công tối ưu không? Kết quả sẽ ra sao nếu cần mọi phân công tối ưu?

*Đáp án:* **Có**, khi chỉ cần một phương án tối ưu. Nếu cần mọi phương án đạt 13, phải tiếp tục xét những nhánh có thể **hòa** ở 13, thay điều kiện cắt tương ứng và bổ sung cơ chế lưu nghiệm hòa.

**Bài 10 — Tính đúng của cận.** Điều gì nguy hiểm hơn: cận lỏng nhưng đúng, hay cận rất chặt nhưng đôi khi sai hướng?

*Đáp án:* **Cận sai hướng nguy hiểm hơn**, vì nó có thể loại mất nghiệm tối ưu và biến thuật toán thành sai. Cận lỏng đúng chỉ khiến tìm kiếm chậm hơn.

**Tổng kết:** Trong **nhánh và cận**, cận phải áp dụng cho **mọi nghiệm hoàn thành của nhánh**. Với **MIN**, một cận dưới lạc quan không thể đánh bại **chi phí nghiệm đầy đủ tốt nhất** thì loại nhánh khi \(LB\ge B\). Với **MAX**, một cận trên lạc quan không thể vượt **lợi ích nghiệm khả thi tốt nhất** thì loại nhánh khi \(UB\le B\). Tìm nghiệm khả thi tốt sớm giúp cắt mạnh hơn; kiểm tra hợp lệ, hoàn tác trạng thái và chứng minh bất đẳng thức giúp thuật toán **đúng**, không chỉ có vẻ nhanh.