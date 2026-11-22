# Phân biệt có chứng minh tối ưu với kinh nghiệm chọn tốt

Trong thiết kế **thuật toán tham lam (greedy algorithms)**, chúng ta thường liên tục chọn một phương án có vẻ tốt nhất **ngay tại thời điểm hiện tại**: chọn công việc kết thúc sớm nhất, lấy đồng tiền mệnh giá lớn nhất, lấy vật có giá trị trên khối lượng cao nhất, hay chọn cạnh có trọng số nhỏ nhất.

Những quy tắc ấy có thể đơn giản, nhanh và đạt kết quả tốt trong nhiều thử nghiệm. Nhưng một chiến lược “có vẻ hợp lý”, “đã chạy đúng vài bộ dữ liệu” hoặc “luôn chọn phương án tốt nhất cục bộ” **không mặc nhiên tạo lời giải tối ưu toàn cục**. Cần phân biệt ba cấp độ kết luận:

1. **Tối ưu có chứng minh:** với mọi đầu vào thỏa đúng các giả thiết, chiến lược trả về lời giải hợp lệ đạt đúng giá trị mục tiêu tối ưu.
2. **Có bảo đảm gần tối ưu:** có chứng minh một tỷ lệ hoặc sai lệch so với tối ưu, nhưng không nhất thiết đạt tối ưu tuyệt đối.
3. **Kinh nghiệm chọn tốt (heuristic):** được lựa chọn vì trực giác hoặc hiệu năng quan sát được; có thể hữu ích, nhưng chưa có bằng chứng đạt tối ưu hoặc một mức xấp xỉ cho toàn bộ lớp đầu vào đang xét.

Bài học thuộc nhóm **Tham lam** trong Computer Science Algorithms. Trọng tâm không phải học thuộc các “mẹo tham lam”, mà là học cách **xác định điều kiện áp dụng, chứng minh hoặc bác bỏ quy tắc chọn**, tìm phản ví dụ nhỏ và diễn giải chính xác mức bảo đảm của kết quả.

## 1. Thế nào là một lời giải tối ưu?

Một bài toán tối ưu hóa gồm:

- **Đầu vào** và các ràng buộc hợp lệ.
- **Tập phương án khả thi:** mọi lời giải thỏa tất cả điều kiện.
- **Hàm mục tiêu:** giá trị muốn tối đa hóa hoặc tối thiểu hóa.
- **Đáp án tối ưu:** một phương án khả thi không kém bất kỳ phương án khả thi nào theo hàm mục tiêu.

Ví dụ: cho những khoảng thời gian của công việc, mỗi công việc có thời gian bắt đầu và kết thúc, cần chọn **nhiều công việc không giao nhau nhất**. Một tập công việc không giao nhau là **khả thi**. Tập có số công việc lớn nhất trong mọi tập khả thi là **tối ưu**.

Nếu một thuật toán trả ra 4 công việc hợp lệ thì ta đã biết nó giải được **điều kiện khả thi**. Nhưng để tuyên bố tối ưu, cần chứng minh **không tồn tại** tập 5 công việc hợp lệ. “Tôi thử vài cách khác và chưa thấy 5” chưa đủ cho một chứng minh tổng quát.

### Ba khái niệm không được đánh đồng

**Tối ưu của kết quả** hỏi: phương án đạt giá trị mục tiêu tốt nhất hay không?

**Độ phức tạp của thuật toán** hỏi: cần bao nhiêu thời gian và bộ nhớ? Một thuật toán O(n log n) có thể cho kết quả sai; một thuật toán quy hoạch động O(n²) vẫn có thể tối ưu. Tốc độ nhanh không thay thế tính đúng đắn.

**Bảo đảm trong trường hợp xấu nhất** hỏi: điều gì được cam kết với mọi đầu vào trong lớp đã mô tả? Thử nghiệm nhanh và đúng trên nhiều mảng chỉ cho bằng chứng thực nghiệm trên những mảng ấy, không phải khẳng định cho mọi mảng.

Với một bài **tối đa hóa** có giá trị tối ưu dương, một thuật toán gần đúng có thể có chứng minh `ALG >= OPT / c` với hằng số `c >= 1`. Đó là **bảo đảm xấp xỉ**, không phải tối ưu tuyệt đối trừ khi c=1 và giả thiết thích hợp. Với bài tối thiểu hóa, hướng bất đẳng thức thường thay đổi, chẳng hạn `ALG <= c * OPT`. Cần quy định rõ dấu và trường hợp OPT=0 trước khi sử dụng tỷ lệ.

Một heuristic có thể **tình cờ trả lời giải tối ưu** trên một đầu vào. Điều đó không làm heuristic thành thuật toán tối ưu cho **mọi** đầu vào.

## 2. Tư duy tham lam là gì và vì sao hấp dẫn?

Thuật toán tham lam thường lặp lại những thao tác:

1. Quan sát các lựa chọn còn khả thi.
2. Chọn một lựa chọn **tốt nhất theo quy tắc cục bộ**.
3. Cố định lựa chọn hoặc một phần trạng thái.
4. Thu hẹp bài toán và tiếp tục, thường không quay lui.

Ví dụ: chọn công việc có thời điểm kết thúc sớm nhất, sau đó chọn công việc tương thích tiếp theo cũng kết thúc sớm nhất.

Một số lợi điểm của thiết kế tham lam:
- Quy tắc đơn giản, thuận tiện cho sắp xếp rồi quét.
- Có thể tiết kiệm thời gian và bộ nhớ so với liệt kê mọi phương án.
- Có thể xử lý khối dữ liệu lớn khi phép chọn cục bộ rẻ.
- Khi có cấu trúc toán học thích hợp, **bất biến** và **định lý đổi chỗ** cho phép chứng minh tối ưu ngắn gọn.

Nhưng **quy tắc cục bộ** không chứa sẵn chứng minh về tác động của nó lên tương lai. Một quyết định hấp dẫn ngay bây giờ có thể làm mất nhiều lựa chọn tốt về sau. Chẳng hạn công việc dài bắt đầu sớm có thể chặn nhiều công việc ngắn, hoặc đồng tiền mệnh giá lớn nhất có thể khiến ta cần thêm nhiều đồng tiền nhỏ.

### Hai tính chất thường được xét

**Tính lựa chọn tham lam (greedy-choice property):** tồn tại một lời giải tối ưu có thể bắt đầu bằng lựa chọn mà quy tắc tham lam đưa ra. Ta phải chứng minh lựa chọn ấy **an toàn**, tức có thể cố định mà không mất khả năng đạt tối ưu.

**Cấu trúc con tối ưu (optimal substructure):** sau khi cố định lựa chọn an toàn, phần còn lại của một lời giải tối ưu có thể được giải như một bài toán con tối ưu tương ứng.

Cấu trúc con tối ưu **một mình** không đủ để chứng minh một quy tắc tham lam. Nhiều bài toán quy hoạch động có cấu trúc con tối ưu nhưng một lựa chọn cục bộ tùy ý vẫn sai. Cần chứng minh **quy tắc cục bộ cụ thể** là an toàn.

## 3. Ví dụ tối ưu có chứng minh: chọn nhiều công việc không giao nhau nhất

### 3.1. Phát biểu chính xác

Có n công việc; mỗi công việc là một khoảng **nửa mở** `[start,end)` với `start < end`. Hai công việc có thể được chọn cùng nhau nếu **không có thời gian giao nhau**. Vì là đoạn nửa mở, công việc kết thúc lúc t và công việc khác bắt đầu lúc t là tương thích.

Giả sử:
- Mỗi công việc có **giá trị như nhau là 1**.
- Không có ràng buộc thêm như nhân sự, nhóm, chi phí hay thời hạn phức tạp.
- Mục tiêu là **tối đa số công việc** được chọn, không phải tổng thời lượng hay tổng tiền thưởng.
- Cho phép sắp xếp lại các công việc theo thời gian kết thúc.

Đây là bài **interval scheduling** không trọng số. Với đúng các giả thiết này, quy tắc tham lam **chọn công việc kết thúc sớm nhất còn tương thích** là tối ưu.

### 3.2. Thuật toán

1. Sắp các công việc theo **thời điểm kết thúc tăng dần**.
2. Đặt thời điểm kết thúc công việc đã chọn gần nhất là `lastEnd` đủ nhỏ.
3. Duyệt từ trái sang phải. Nếu `job.start >= lastEnd`, chọn công việc và cập nhật `lastEnd=job.end`. Nếu không, bỏ qua.
4. Trả danh sách đã chọn.

Ví dụ:

| Công việc | Khoảng nửa mở |
| --- | --- |
| A | [1,3) |
| B | [2,5) |
| C | [3,4) |
| D | [0,7) |
| E | [4,6) |
| F | [5,9) |
| G | [6,8) |
| H | [8,10) |

Thứ tự kết thúc là **A (3), C (4), B (5), E (6), D (7), G (8), F (9), H (10)**.

Quét lần lượt:
- Chọn **A [1,3)**; `lastEnd=3`.
- Chọn **C [3,4)**; `lastEnd=4`.
- B bắt đầu lúc 2, nhỏ hơn 4 → bỏ.
- Chọn **E [4,6)**; `lastEnd=6`.
- D bắt đầu lúc 0 → bỏ.
- Chọn **G [6,8)**; `lastEnd=8`.
- F bắt đầu lúc 5 → bỏ.
- Chọn **H [8,10)**; `lastEnd=10`.

Thu được **[A,C,E,G,H]**, tổng **5 công việc**. Điều quan trọng: thuật toán không chỉ “chạy đúng ví dụ”, mà có **chứng minh tối ưu tổng quát** ở phần sau.

### 3.3. Chứng minh bằng lập luận đổi chỗ (exchange argument)

Xét tập các công việc còn khả thi tại một bước, sau thời điểm kết thúc đã cố định từ các bước trước. Gọi **g** là công việc tương thích **kết thúc sớm nhất** mà tham lam chọn.

Chọn một lời giải tối ưu **O** cho phần bài toán còn lại. Nếu O đã chứa g ở vị trí đầu, không cần sửa. Nếu không, gọi **o** là công việc bắt đầu đầu tiên theo thứ tự thời gian trong O.

Vì g kết thúc sớm nhất trong mọi công việc còn tương thích:
\[
finish(g) \le finish(o).
\]

Ta thay **o bằng g** trong O. Tất cả công việc khác của O bắt đầu **không sớm hơn finish(o)** vì O khả thi, nên chúng cũng bắt đầu không sớm hơn finish(g). Như vậy chúng **vẫn tương thích** với g.

Việc thay thế:
- Không làm tăng số công việc được chọn: vẫn **đúng một** công việc thay cho một công việc.
- Không phá tính khả thi.
- Không làm giảm giá trị mục tiêu: mỗi công việc đều có trọng số 1, nên số công việc giữ nguyên.

Vì thế tồn tại **ít nhất một lời giải tối ưu** bắt đầu bằng **g**. Đây chính là **tính lựa chọn tham lam** được chứng minh, không phải giả định.

Sau khi chọn g, phần còn lại là bài toán cùng dạng chỉ trên các công việc có `start >= finish(g)`. Áp dụng lập luận tương tự một cách quy nạp, các lựa chọn tiếp theo cũng an toàn. Do đó toàn bộ thuật toán trả **số công việc tối đa**.

**Chú ý:** chứng minh này không nói g xuất hiện trong *mọi* lời giải tối ưu; chỉ cần chứng minh có **một** lời giải tối ưu tương thích với lựa chọn g. Đó là đủ cho việc cố định lựa chọn tham lam.

### 3.4. Độ phức tạp

Với n công việc:
- Sắp theo thời gian kết thúc: **O(n log n)**.
- Quét chọn tương thích: **O(n)**.
- Tổng: **O(n log n)**; nếu đầu vào đã được đảm bảo sắp theo end, lượt quét chỉ O(n).

Bộ nhớ tùy cách cài: nếu tạo danh sách các công việc được chọn, đầu ra tối đa O(n); nếu copy danh sách trước khi sort, bản sao cũng O(n). Không được gọi toàn bộ ví dụ là O(1) bộ nhớ chỉ vì phép lựa chọn quét cần vài biến.

## 4. Phản ví dụ: “chọn công việc ngắn nhất” không tối ưu

Một trực giác khác: **công việc càng ngắn càng ít chiếm thời gian**, nên cứ chọn công việc có **thời lượng nhỏ nhất** còn tương thích. Nghe hợp lý, nhưng sai với mục tiêu **tối đa số công việc không giao nhau**.

Chỉ cần ba công việc:

~~~text
L = [0,3)   (độ dài 3)
M = [3,6)   (độ dài 3)
S = [2,4)   (độ dài 2)
~~~

Quy tắc **thời lượng ngắn nhất trước**:
1. Chọn S vì độ dài 2 là nhỏ nhất.
2. S giao với L trên [2,3) và giao với M trên [3,4).
3. Không chọn thêm được L hoặc M. Kết quả **1** công việc.

Nhưng chọn **L rồi M** hoàn toàn khả thi, vì L kết thúc tại 3 và M bắt đầu tại 3. Kết quả **2** công việc, lớn hơn 1.

Vậy ví dụ này **bác bỏ mệnh đề** “chọn công việc ngắn nhất trước luôn tối ưu”. Chỉ cần **một phản ví dụ hợp lệ** là đủ để bác bỏ khẳng định với **mọi** đầu vào.

### Phản ví dụ khác: chọn bắt đầu sớm nhất

~~~text
X = [0,10)
Y = [1,2)
Z = [2,3)
W = [3,4)
~~~

Chọn **bắt đầu sớm nhất** sẽ lấy X và chỉ được 1 công việc. Chọn Y, Z, W được **3 công việc**, tốt hơn. Bởi vậy “bắt đầu sớm” không tương đương “để lại nhiều cơ hội” — cần chứng minh một **thuộc tính có liên quan trực tiếp đến khả năng chọn tiếp**. Thời điểm **kết thúc sớm nhất** có thuộc tính ấy, còn thời điểm bắt đầu sớm nhất thì không.

### Vì sao hai heuristics có thể vẫn chạy tốt trên nhiều dữ liệu?

Nếu dữ liệu tình cờ có các công việc ngắn cũng kết thúc sớm, hai quy tắc có thể cho cùng kết quả. Một heuristic có thể thường đạt giá trị gần tối ưu trên phân bố dữ liệu quen thuộc. Điều đó là **thông tin thực nghiệm**, không khôi phục một chứng minh tổng quát đã bị phản ví dụ bác bỏ.

Nếu thay đổi mục tiêu, ví dụ **tối thiểu tổng thời lượng của đúng k công việc**, hoặc thêm giới hạn số công việc cần chọn, phân tích phải thay đổi. Không thể dùng chứng minh của bài chọn **nhiều công việc nhất, không trọng số** cho một bài khác.

## 5. Phản ví dụ kinh điển: đổi tiền bằng đồng lớn nhất trước

Bài toán: có các đồng tiền với mệnh giá thuộc một tập số nguyên dương; được dùng mỗi mệnh giá **không giới hạn số lượng**. Với số tiền `amount`, cần dùng **ít đồng tiền nhất** để tạo đúng amount.

Một heuristic dễ nghĩ tới:
1. Lấy mệnh giá lớn nhất không vượt số tiền còn thiếu.
2. Trừ mệnh giá đó.
3. Lặp lại đến khi đủ tiền hoặc không thể tiếp tục.

**Đây là quy tắc tham lam theo mệnh giá lớn nhất.** Nó có thể tối ưu trên một số hệ mệnh giá cụ thể, nhưng **không tối ưu cho mọi hệ mệnh giá**.

### Phản ví dụ tối thiểu, dễ kiểm tra

~~~text
Mệnh giá: [1,3,4]
Số tiền:  6

Greedy lớn nhất trước: 4 + 1 + 1 = 6 -> 3 đồng
Phương án tốt hơn:     3 + 3     = 6 -> 2 đồng
~~~

Chỉ với một bộ dữ liệu, ta đã chứng minh quy tắc “luôn lấy mệnh giá lớn nhất trước” **không có bảo đảm tối ưu tổng quát**.

Có thể xác nhận 2 đồng là tối ưu: không có đồng nào trị giá 6, nên không thể trả bằng 1 đồng; hai đồng 3+3 tạo đúng 6. Vậy giá trị tối ưu là 2.

### Phản ví dụ không tìm ra nghiệm dù nghiệm tồn tại

Nếu mệnh giá là **[3,4]** và amount=6:
- Chọn 4 đầu tiên để lại 2; không có đồng nào mệnh giá ≤2, heuristic báo không hoàn thành.
- Nhưng **3+3=6** là phương án khả thi.

Vì vậy greedy không chỉ có thể dùng **nhiều đồng hơn** mà còn có thể **thất bại trong việc tìm phương án có tồn tại**, khi hệ mệnh giá không có đồng 1 hoặc không có cấu trúc phù hợp.

### Vì sao không được suy diễn từ một hệ tiền quen thuộc?

Nhiều hệ mệnh giá được thiết kế để phép lấy đồng lớn nhất trước hoạt động tốt, nhưng tính đúng cần phụ thuộc **tập mệnh giá và ràng buộc cụ thể**. Sự thành công trên một vài số tiền không chứng minh được tính đúng với mọi số tiền. Nếu bài cho một hệ mệnh giá bất kỳ, phải chứng minh hệ đó có thuộc tính cho phép greedy hoặc dùng phương pháp tổng quát khác.

Một cách giải có bảo đảm tối ưu cho các số tiền nguyên không âm vừa phải là **quy hoạch động**:

\[
dp[s] = 1 + \min_{c\in coins,\,c\le s} dp[s-c],
\]

với `dp[0]=0` và trạng thái không thể tạo có giá trị vô cùng. Công thức xét **mọi lựa chọn đồng tiền đầu tiên**, không cố định lựa chọn lớn nhất theo trực giác. Sau khi có `dp[amount]`, có thể lưu đồng đã chọn để khôi phục phương án.

Độ phức tạp khi duyệt từng số tiền từ 1 đến amount là **O(amount × m)** với m mệnh giá, bộ nhớ O(amount). Đây là chi phí **giả đa thức (pseudo-polynomial)** theo giá trị số tiền; không nên nói nó đa thức theo số bit biểu diễn amount trong mọi trường hợp.

## 6. Cùng một nguyên tắc tham lam có thể đúng ở bài này, sai ở bài khác

### 6.1. Fractional knapsack: chọn mật độ cao nhất là tối ưu

Bài có các vật với trọng lượng dương và giá trị không âm, giới hạn sức chứa W. **Được phép lấy một phần của mỗi vật** theo bất kỳ tỷ lệ nào từ 0 đến 1, và giá trị nhận được tỷ lệ tuyến tính với phần trọng lượng lấy. Mục tiêu là tối đa tổng giá trị.

Nếu sắp theo **mật độ giá trị `value/weight` giảm dần** rồi lấy nhiều nhất có thể theo thứ tự đó, lời giải là tối ưu.

**Lập luận đổi chỗ:** giả sử lời giải khả thi lấy một lượng dương từ vật mật độ thấp `d_low`, trong khi vật có mật độ cao hơn `d_high` vẫn còn có thể lấy thêm. Chuyển một lượng trọng lượng `epsilon` từ vật thấp sang vật cao sẽ tăng giá trị thêm `epsilon × (d_high - d_low) > 0`. Vậy trong một lời giải tối ưu không thể xảy ra tình huống bỏ trống cơ hội lấy mật độ cao mà lại lấy mật độ thấp hơn. Điều đó dẫn tới chiến lược chọn mật độ cao trước.

Điều kiện **được phép chia nhỏ vật** là then chốt cho phép ta “đổi một lượng epsilon”. Nếu vật không thể chia, phép đổi có thể không hợp lệ.

### 6.2. 0/1 knapsack: quy tắc mật độ cao nhất có thể sai

Giả sử sức chứa W=50 và ba vật:

| Vật | Trọng lượng | Giá trị | Giá trị / trọng lượng |
| --- | ---: | ---: | ---: |
| A | 10 | 60 | 6 |
| B | 20 | 100 | 5 |
| C | 30 | 120 | 4 |

Với quy tắc “mật độ cao nhất trước” trong **0/1 knapsack**:
- Chọn A (10,60) và B (20,100), tổng trọng lượng 30, giá trị 160.
- C có trọng lượng 30, không thể thêm vào 20 chỗ còn lại.
- Tổng chỉ **160**.

Nhưng chọn **B+C** có tổng trọng lượng 50 và tổng giá trị **220**, lớn hơn 160. Quy tắc tham lam theo mật độ **không tối ưu** cho bài 0/1 này.

Với **fractional knapsack**, có thể chọn A, B và **2/3 vật C**, dùng đủ 50 trọng lượng, đạt giá trị `60+100+80=240`; đây chính là ví dụ mà quy tắc mật độ cao nhất đúng nhờ được chia nhỏ vật.

Cùng tiêu chí “giá trị trên trọng lượng cao nhất”, nhưng **tập phương án khả thi khác nhau** làm tính đúng đắn đổi hoàn toàn. Vì thế không thể bỏ qua câu “được chia vật hay không” trong đề bài.

### 6.3. Các bài có điều kiện tiền đề tương tự

Một số thuật toán nổi tiếng sử dụng lựa chọn cục bộ có chứng minh tối ưu **khi đúng tiền điều kiện**:

- **Kruskal** chọn cạnh nhẹ nhất không tạo chu trình để xây cây khung nhỏ nhất trong đồ thị vô hướng có trọng số; chứng minh dựa trên tính chất lát cắt và phép đổi cạnh.
- **Dijkstra** chọn đỉnh chưa chốt có khoảng cách tạm thời nhỏ nhất; bảo đảm đúng đường đi ngắn nhất khi trọng số cạnh **không âm** theo giả thiết chuẩn.
- **Huffman** lặp lại việc ghép hai trọng số/tần suất nhỏ nhất để xây mã tiền tố có tổng độ dài có trọng số tối ưu trong mô hình phù hợp.

Không được hiểu rằng mọi quy tắc “nhỏ nhất trước” đều đúng, hoặc điều kiện của một thuật toán này tự chuyển sang thuật toán khác. Trong mỗi bài phải xem **hàm mục tiêu, tập nghiệm khả thi và lập luận đổi chỗ/bất biến riêng**.

## 7. Cách chứng minh một thuật toán tham lam thực sự tối ưu

Một khung suy luận hữu ích:

### Bước 1 — Định nghĩa chính xác dữ liệu, tính khả thi và mục tiêu

Ghi rõ cách đánh chỉ số, có cho phép trùng, có cho phép chia nhỏ hay không, khoảng đóng hay nửa mở, mỗi lựa chọn có trọng số hay bằng nhau, và bài cần tối đa hay tối thiểu.

Chỉ một thay đổi nhỏ trong hợp đồng có thể phá hỏng chứng minh. Với lịch công việc, “tối đa số công việc” và “tối đa tổng lợi ích” là hai mục tiêu khác nhau.

### Bước 2 — Phát biểu quy tắc chọn dưới dạng toán học

Ví dụ: “chọn công việc tương thích có **finish nhỏ nhất**”, không nói mơ hồ “chọn công việc tốt nhất”. Nếu có nhiều công việc cùng finish, phải quy định có thể chọn bất kỳ hay cần một quy tắc phá hòa cụ thể.

Một quy tắc phải đủ rõ để áp dụng cho mọi trạng thái hợp lệ và được cài bằng điều kiện xác định.

### Bước 3 — Phát biểu **bất biến** và bài toán còn lại

Sau khi chọn một phần của lời giải, điều gì được giữ đúng? Phần chưa chọn còn tạo một bài toán cùng loại không? Nếu có trạng thái đã chốt, mọi lựa chọn tiếp theo có bị hạn chế bằng điều kiện đơn giản nào không?

Với chọn lịch, sau công việc kết thúc ở t, chỉ những công việc bắt đầu ở thời điểm ≥t mới được xem xét.

### Bước 4 — Chứng minh greedy-choice property

Có thể dùng nhiều phương pháp:

**Lập luận đổi chỗ (exchange argument):** lấy một lời giải tối ưu bất kỳ, chứng minh có thể thay một lựa chọn của nó bằng lựa chọn greedy **mà không giảm giá trị mục tiêu và không phá khả thi**. Sau thay thế, tồn tại lời giải tối ưu có chung bước đầu với greedy.

**Phương pháp “luôn dẫn trước” (stays ahead):** chứng minh sau mỗi k bước, trạng thái greedy không kém bất kỳ phương án cạnh tranh nào theo một đại lượng phù hợp. Với lịch không trọng số, thời điểm kết thúc của công việc thứ k do greedy chọn không muộn hơn thời điểm kết thúc công việc thứ k của bất kỳ lịch khả thi có ít nhất k công việc. Từ đó suy ra không lịch nào chọn được nhiều công việc hơn greedy.

**Bất biến lát cắt/cấu trúc:** trong một số bài đồ thị, dùng tính chất lát cắt hoặc chu trình để chứng minh một lựa chọn có thể có trong nghiệm tối ưu.

Một chứng minh phải nói rõ **vì sao không mất khả năng đạt tối ưu** khi cố định lựa chọn cục bộ. Câu “chọn nhỏ nhất nên tốt nhất” không phải chứng minh.

### Bước 5 — Giải bài toán con và chứng minh kết thúc

Khi đã chứng minh bước greedy an toàn, cần cho thấy bài toán còn lại có đúng dạng cần giải, thuật toán thu hẹp trạng thái và cuối cùng dừng. Kết hợp các bước an toàn theo quy nạp mới suy ra tính tối ưu toàn cục.

### Bước 6 — Tìm phản ví dụ trước khi quá tin tưởng

Khi chưa tìm được chứng minh, hãy tìm những đầu vào nơi lựa chọn cục bộ **xung đột với tương lai**. Đặc biệt quan tâm:
- Một lựa chọn dài chặn nhiều lựa chọn ngắn.
- Lựa chọn lớn nhất trước để lại phần dư khó xử lý.
- Lựa chọn theo tỷ lệ tốt nhưng kích thước không thể chia.
- Có nhiều giá trị bằng nhau khiến quy tắc phá hòa ảnh hưởng kết quả.
- Các ràng buộc bổ sung như trọng số, deadline, giới hạn số lượng.

Phản ví dụ không chỉ phát hiện sai; nó còn giúp tìm đúng **giả thiết cần thêm** hoặc một thuật toán khác thích hợp.

## 8. Kiểm thử có ích gì nếu không thay thế chứng minh?

**Kiểm thử** giúp phát hiện lỗi cài đặt, trường hợp biên, điều kiện so sánh sai và phản ví dụ của một phỏng đoán.

**Kiểm thử vét cạn trên dữ liệu nhỏ** có thể tìm ra phản ví dụ rất nhanh:
1. Sinh mọi tập lịch nhỏ hoặc các mẫu ngẫu nhiên hợp lệ.
2. Chạy thuật toán greedy cần kiểm tra.
3. Dùng brute force để duyệt mọi tập con, tính đáp án tối ưu chuẩn.
4. So sánh cả **tính khả thi** và **giá trị mục tiêu**.
5. Khi khác nhau, rút gọn đầu vào để được phản ví dụ dễ hiểu.

Với bài đổi tiền, dùng quy hoạch động làm oracle trên số tiền vừa phải; với lịch công việc, duyệt mọi tập con với n nhỏ là oracle hợp lý.

Nhưng dù kiểm tra một triệu bộ dữ liệu đều đúng, điều đó cũng chỉ nói về **một triệu bộ dữ liệu đã thử**. Không chứng minh được một mệnh đề cho vô hạn đầu vào hoặc toàn bộ lớp đầu vào lớn. Khi viết báo cáo, phân biệt rõ “tested with no failures” và “proven optimal”.

Mặt khác, một phản ví dụ nhỏ **đã đủ** bác bỏ khẳng định “mọi đầu vào đều tối ưu” nếu phản ví dụ thỏa tất cả tiền điều kiện của khẳng định ấy.

## 9. Java 17: phân biệt thuật toán có chứng minh và heuristic

Chương trình hoàn chỉnh minh họa:
- **Chọn lịch theo finish sớm nhất** trên khoảng nửa mở: có chứng minh tối ưu cho mục tiêu tối đa số công việc.
- **Chọn thời lượng ngắn nhất trước**: heuristic có phản ví dụ ngay trên ba công việc.
- **Đổi tiền bằng mệnh giá lớn nhất trước**: heuristic cho 3 đồng trên bộ [1,3,4], amount=6.
- **Quy hoạch động** cho số đồng tối thiểu: tìm đúng đáp án 2 đồng [3,3] trên cùng đầu vào.

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;

public class GreedyProofVsHeuristicDemo {
    record Interval(String id, int start, int end) {
        Interval {
            if (id == null || start >= end) {
                throw new IllegalArgumentException("Invalid interval");
            }
        }
    }

    // Tối ưu khi mục tiêu là số khoảng nửa mở không giao tối đa.
    static List<Interval> earliestFinish(List<Interval> input) {
        List<Interval> sorted = new ArrayList<>(input);
        sorted.sort(Comparator.comparingInt(Interval::end)
                .thenComparingInt(Interval::start)
                .thenComparing(Interval::id));

        List<Interval> chosen = new ArrayList<>();
        int lastEnd = Integer.MIN_VALUE;

        for (Interval current : sorted) {
            if (current.start() >= lastEnd) {
                chosen.add(current);
                lastEnd = current.end();
            }
        }
        return chosen;
    }

    // Heuristic: chọn thời lượng ngắn nhất còn tương thích.
    static List<Interval> shortestFirst(List<Interval> input) {
        List<Interval> sorted = new ArrayList<>(input);
        sorted.sort(Comparator
                .comparingLong((Interval i) ->
                        (long) i.end() - i.start())
                .thenComparingInt(Interval::start)
                .thenComparing(Interval::id));

        List<Interval> chosen = new ArrayList<>();
        for (Interval current : sorted) {
            boolean compatible = true;
            for (Interval picked : chosen) {
                boolean overlap = current.start() < picked.end()
                        && picked.start() < current.end();
                if (overlap) {
                    compatible = false;
                    break;
                }
            }
            if (compatible) {
                chosen.add(current);
            }
        }
        return chosen;
    }

    static String ids(List<Interval> items) {
        return items.stream().map(Interval::id).toList().toString();
    }

    static void validateCoins(int[] coins, int amount) {
        if (coins == null || amount < 0) {
            throw new IllegalArgumentException("Invalid coins/amount");
        }
        for (int coin : coins) {
            if (coin <= 0) {
                throw new IllegalArgumentException("Nonpositive coin");
            }
        }
    }

    // Heuristic: luôn chọn đồng lớn nhất không vượt số tiền còn lại.
    static List<Integer> greedyCoins(int[] coins, int amount) {
        validateCoins(coins, amount);
        int[] sorted = coins.clone();
        Arrays.sort(sorted);
        List<Integer> result = new ArrayList<>();
        int remaining = amount;

        for (int i = sorted.length - 1; i >= 0; i--) {
            int coin = sorted[i];
            while (remaining >= coin) {
                result.add(coin);
                remaining -= coin;
            }
        }
        return remaining == 0 ? result : null;
    }

    // Đáp án tối ưu bằng DP; amount không âm và đủ nhỏ để cấp mảng.
    static List<Integer> optimalCoinsDP(int[] coins, int amount) {
        validateCoins(coins, amount);
        if (amount == Integer.MAX_VALUE) {
            throw new IllegalArgumentException("Amount too large");
        }

        int unreachable = amount + 1;
        int[] dp = new int[amount + 1];
        int[] lastCoin = new int[amount + 1];
        Arrays.fill(dp, unreachable);
        dp[0] = 0;

        for (int sum = 1; sum <= amount; sum++) {
            for (int coin : coins) {
                if (coin <= sum && dp[sum - coin] != unreachable
                        && dp[sum - coin] + 1 < dp[sum]) {
                    dp[sum] = dp[sum - coin] + 1;
                    lastCoin[sum] = coin;
                }
            }
        }

        if (dp[amount] == unreachable) {
            return null;
        }

        List<Integer> result = new ArrayList<>();
        for (int sum = amount; sum > 0; sum -= lastCoin[sum]) {
            result.add(lastCoin[sum]);
        }
        return result;
    }

    public static void main(String[] args) {
        List<Interval> schedule = List.of(
            new Interval("D", 0, 7),
            new Interval("B", 2, 5),
            new Interval("H", 8, 10),
            new Interval("A", 1, 3),
            new Interval("F", 5, 9),
            new Interval("C", 3, 4),
            new Interval("G", 6, 8),
            new Interval("E", 4, 6)
        );
        List<Interval> chosen = earliestFinish(schedule);
        System.out.println("schedule=" + ids(chosen)
                + " count=" + chosen.size());

        List<Interval> counterexample = List.of(
            new Interval("L", 0, 3),
            new Interval("M", 3, 6),
            new Interval("S", 2, 4)
        );
        List<Interval> heuristic = shortestFirst(counterexample);
        List<Interval> optimal = earliestFinish(counterexample);
        System.out.println("shortestFirst=" + ids(heuristic)
                + " count=" + heuristic.size());
        System.out.println("earliestFinish=" + ids(optimal)
                + " count=" + optimal.size());

        int[] coins = {1, 3, 4};
        List<Integer> greedy = greedyCoins(coins, 6);
        List<Integer> best = optimalCoinsDP(coins, 6);
        System.out.println("greedyCoins6=" + greedy
                + " count=" + greedy.size());
        System.out.println("optimalCoins6=" + best
                + " count=" + best.size());
    }
}
~~~

Lưu thành tệp **GreedyProofVsHeuristicDemo.java**, chạy bằng **JDK 17 trở lên**:

~~~bash
javac GreedyProofVsHeuristicDemo.java
java GreedyProofVsHeuristicDemo
~~~

**Đầu ra dự kiến chính xác:**

~~~text
schedule=[A, C, E, G, H] count=5
shortestFirst=[S] count=1
earliestFinish=[L, M] count=2
greedyCoins6=[4, 1, 1] count=3
optimalCoins6=[3, 3] count=2
~~~

### Đọc đúng kết quả

- Thuật toán **earliestFinish** sắp theo end, chọn **A,C,E,G,H**. Đây là một lời giải có **bảo đảm tối ưu** vì đã có chứng minh đổi chỗ cho lớp bài không trọng số, nửa mở và tương thích như phát biểu.
- Heuristic **shortestFirst** chọn S trước vì độ dài 2 nhỏ hơn 3, rồi không còn khoảng nào không giao; nó chỉ lấy 1. Lựa chọn theo finish lấy L,M được 2.
- Greedy tiền mệnh giá lớn trước cho **4+1+1** gồm 3 đồng, trong khi DP xét mọi lựa chọn hợp lệ cho **3+3** gồm 2 đồng.
- Hàm `optimalCoinsDP` lưu `dp[sum]`: số đồng ít nhất để tạo sum, và `lastCoin[sum]` để truy ngược. Nó không dựa vào giả thiết hệ mệnh giá “chuẩn”.
- `greedyCoins` có thể trả `null` khi không thể hoàn tất theo chiến lược đã chọn; điều đó **không chứng minh** bài toán không có lời giải (ví dụ coins=[3,4], amount=6).
- `optimalCoinsDP` cũng có thể trả `null`, nhưng lúc ấy mọi trạng thái đã được DP kiểm tra theo công thức nên **không có cách đổi tiền hợp lệ** trong bài đổi tiền không giới hạn số lượng đồng.
- `shortestFirst` kiểm tra giao với **tất cả** khoảng đã chọn vì thứ tự thời lượng không bảo đảm thứ tự thời gian. Với `earliestFinish`, thứ tự end tăng cho phép chỉ dùng `lastEnd` để kiểm tra.
- Mã dùng `(long)end-start` khi so thời lượng để tránh tràn int ở các khoảng có mốc cực trị; dùng `Integer.MIN_VALUE` làm `lastEnd` là an toàn cho các khoảng có `start<end`.

**Phạm vi ví dụ:** `Interval` không cho phép khoảng rỗng `start==end`, còn DP tiền sử dụng mệnh giá nguyên dương và số tiền nguyên không âm có thể cấp mảng được. Đây không phải thư viện sắp lịch có trọng số, không xử lý nhiều tài nguyên, và không tối ưu bộ nhớ cho số tiền rất lớn.

## 10. So sánh độ phức tạp và độ bảo đảm

| Cách giải | Mục tiêu | Độ phức tạp thông dụng | Bảo đảm về chất lượng |
| --- | --- | --- | --- |
| Chọn công việc finish sớm nhất | Nhiều khoảng không giao nhất, cùng trọng số | O(n log n) gồm sort | **Tối ưu**, có chứng minh đổi chỗ |
| Chọn công việc ngắn nhất trước | Cùng bài trên | O(n log n + n²) với cách kiểm tra mọi khoảng đã chọn trong ví dụ | **Không tối ưu** nói chung |
| Đổi tiền greedy mệnh giá lớn trước | Ít đồng nhất, hệ mệnh giá bất kỳ | O(m log m + số đồng được chọn) với cách liệt kê đồng trong ví dụ | **Không tối ưu** nói chung; đôi khi không tìm được nghiệm |
| Đổi tiền DP | Ít đồng nhất, mệnh giá nguyên dương | O(amount×m), O(amount) bộ nhớ | **Tối ưu** theo mô hình được phát biểu |
| Fractional knapsack theo mật độ | Tổng giá trị lớn nhất, được chia vật | O(n log n) gồm sort | **Tối ưu** với giá trị tỷ lệ tuyến tính |
| 0/1 knapsack theo mật độ | Tổng giá trị lớn nhất, không chia vật | O(n log n) theo greedy thông thường | **Không tối ưu** nói chung |

**Độ phức tạp tốt và tính tối ưu kết quả là hai tuyên bố độc lập.** Thuật toán sắp lịch greedy có cả thời gian tốt và bảo đảm tối ưu. Heuristic thời lượng ngắn có thể làm nhiều phép kiểm tra hơn mà còn cho kết quả kém. DP đổi tiền có thể tốn nhiều công việc hơn greedy nhưng cung cấp lời giải tối ưu cho miền số tiền phù hợp.

## 11. Các trường hợp biên và điều kiện tiền đề

### 11.1. Lịch công việc

- **Không có công việc:** lời giải tối ưu rỗng, giá trị 0.
- **Một công việc hợp lệ:** chọn chính công việc ấy, giá trị 1.
- **Hai công việc chạm biên:** [1,3) và [3,5) tương thích theo quy ước nửa mở.
- **Công việc có end bằng nhau:** có thể phá hòa bằng start hoặc id; chứng minh vẫn dựa trên end nhỏ nhất, không nhất thiết duy nhất.
- **Công việc có cùng khoảng:** chỉ chọn tối đa một trong các bản sao nếu khoảng không rỗng.
- **Thời điểm âm:** vẫn hợp lệ nếu start<end, sort bằng `Integer.compare` để không tràn.
- **Công việc có trọng số khác nhau:** không được áp dụng kết luận tối ưu của bài **đếm số công việc**. Cần xét bài weighted interval scheduling và các kỹ thuật tương ứng.
- **Khoảng đóng:** nếu dùng [start,end] trong thời gian thực thì hai công việc chạm đầu mút **giao nhau**; điều kiện tương thích phải thay đổi.

### 11.2. Đổi tiền

- **amount=0:** không dùng đồng nào, tối ưu 0 đồng.
- **Mệnh giá không dương:** không hợp lệ theo mô hình này; đồng 0 gây vòng lặp vô nghĩa cho greedy, mệnh giá âm phá trạng thái DP.
- **Không có đồng 1:** có thể có số tiền không thể tạo, DP cần trạng thái không thể đạt tới.
- **Mệnh giá trùng nhau:** không đổi tập phương án về giá trị nhưng có thể gây lặp trong xử lý; có thể loại trùng để tối ưu.
- **Amount lớn:** DP `O(amount×m)` và O(amount) bộ nhớ có thể không phù hợp; phải chọn phương án theo ràng buộc đầu vào thực tế.
- **Đồng tiền có giới hạn số lượng:** công thức DP không giới hạn số đồng cần thay đổi; không dùng nguyên công thức cho bounded coin change.
- **Mục tiêu không phải số đồng:** nếu phí giao dịch/độ ưu tiên khác nhau, phải thay đổi hàm mục tiêu.

### 11.3. Tính đúng của so sánh

Đừng viết comparator `a.end-b.end` bằng int trong Java vì phép trừ có thể **tràn số**, đảo sai thứ tự. Dùng `Comparator.comparingInt(Interval::end)`, `Integer.compare` hoặc phép so sánh đúng kiểu.

Khi cài thuật toán tham lam, các lỗi **`<` so với `<=`**, nhầm đoạn đóng/nửa mở, quên xử lý khóa bằng nhau, hoặc dùng thứ tự đầu vào chưa sắp có thể khiến một chiến lược **vốn đúng về mặt lý thuyết** bị cài sai.

Bởi vậy cần tách **chứng minh thuật toán trừu tượng** khỏi **chứng minh bản cài tuân thủ đúng quy tắc và tiền điều kiện**.

## 12. Tối ưu có chứng minh, xấp xỉ có chứng minh và heuristic thực nghiệm

Có thể chia báo cáo kết quả thành ba loại:

| Mức khẳng định | Ví dụ phát biểu đúng | Điều cần có |
| --- | --- | --- |
| **Tối ưu** | “Với lịch không trọng số và khoảng nửa mở, chọn finish sớm nhất đạt số công việc tối đa.” | Chứng minh tổng quát theo điều kiện cụ thể |
| **Có bảo đảm xấp xỉ** | “Đối với lớp đầu vào xác định, giá trị của thuật toán không kém một tỷ lệ đã chứng minh so với tối ưu.” | Bất đẳng thức hoặc cận xấp xỉ áp dụng cho mọi đầu vào hợp lệ |
| **Heuristic** | “Trên tập kiểm thử này, quy tắc thời lượng ngắn thường chọn được nhiều công việc.” | Dữ liệu thử nghiệm và giới hạn của kết luận; không suy diễn thành chứng minh |

Một heuristic có thể được ưu tiên trong sản phẩm nếu đầu vào thực tế thuận lợi, yêu cầu thời gian chặt hoặc lời giải tối ưu quá tốn tài nguyên. Nhưng phải nói rõ **đánh đổi**, đặc biệt khi kết quả ảnh hưởng đến chi phí, công bằng hoặc độ tin cậy của hệ thống.

Ngược lại, không nên bác bỏ mọi heuristic vì một phản ví dụ: phản ví dụ chỉ bác bỏ **bảo đảm tối ưu tổng quát**, không chứng minh chiến lược vô ích trên mọi phân bố. Một lựa chọn kỹ thuật tốt có thể kết hợp heuristic nhanh, kiểm tra khả thi, và nếu cần thì dùng thuật toán tối ưu để xác minh hay cải thiện đáp án.

## 13. Quy trình đánh giá một chiến lược greedy mới

Khi gặp một đề chưa biết, hãy thử theo trình tự:

1. **Viết bài toán bằng lời và công thức:** đầu vào, ràng buộc, mục tiêu, giá trị tối ưu cần đạt.
2. **Đề xuất 2–3 quy tắc cục bộ** có liên quan đến mục tiêu: ví dụ finish sớm, start sớm, thời lượng ngắn.
3. **Tìm đầu vào phân biệt các quy tắc**, nhất là trường hợp chúng chọn phần tử đầu tiên khác nhau.
4. **Dùng brute force trên n nhỏ** để tìm optimum và kiểm tra các quy tắc. Khi gặp sai khác, tìm phản ví dụ nhỏ nhất có thể.
5. **Với quy tắc còn triển vọng, phát biểu bất biến** và thử chứng minh phép chọn đầu không làm mất một nghiệm tối ưu.
6. **Kiểm tra bài toán con và kết thúc:** sau khi chốt lựa chọn đầu, vấn đề còn lại có cùng cấu trúc và giảm kích thước không?
7. **Phân tích thời gian, bộ nhớ và cài đặt:** sort trước theo khóa nào, xử lý hòa và các đầu mút ra sao, số học có tràn không?
8. **Phát biểu đúng mức kết luận:** “tối ưu có chứng minh” chỉ khi có chứng minh đầy đủ; nếu chưa có, gọi đúng là heuristic hoặc kết quả thực nghiệm trên tập đã thử.

Đây là quy trình nghiên cứu một phương án, không phải bản thân một chứng minh. Đặc biệt, “không tìm được phản ví dụ nhỏ” **không tương đương** “không tồn tại phản ví dụ”.

## 14. Bài tập tự luyện có đáp án

**Bài 1 — xác định quy tắc đúng.** Có các công việc [0,3), [3,6), [2,4). Muốn chọn nhiều công việc không giao nhau nhất, quy tắc thời lượng ngắn nhất chọn bao nhiêu? Có phương án tốt hơn không?

*Đáp án:* Chọn [2,4) được 1; chọn [0,3) và [3,6) được 2. Do vậy thời lượng ngắn nhất trước không bảo đảm tối ưu.

**Bài 2 — phát biểu exchange argument.** Khi chọn công việc kết thúc sớm nhất g, tại sao có thể thay công việc đầu o của một lịch tối ưu bằng g?

*Đáp án:* Vì `finish(g)<=finish(o)`. Những công việc còn lại của lịch tối ưu bắt đầu sau finish(o), nên cũng bắt đầu sau finish(g), không mất tính khả thi. Số công việc được chọn không đổi.

**Bài 3 — đổi tiền.** Với mệnh giá [1,3,4] và số tiền 6, hãy viết lời giải greedy và lời giải tối ưu.

*Đáp án:* Greedy là 4+1+1, cần 3 đồng. Tối ưu là 3+3, cần 2 đồng. Phản ví dụ bác bỏ greedy cho hệ mệnh giá bất kỳ.

**Bài 4 — điều kiện mô hình.** Vì sao quy tắc lấy vật theo mật độ giá trị có thể được chứng minh tối ưu trong fractional knapsack nhưng không trong 0/1 knapsack?

*Đáp án:* Fractional cho phép chuyển một lượng nhỏ trọng lượng giữa hai vật để cải thiện giá trị bằng lập luận đổi chỗ. 0/1 bắt buộc lấy cả vật, nên phép chuyển một phần có thể không hợp lệ; ví dụ W=50 với các vật (10,60), (20,100), (30,120) làm greedy chỉ được 160 thay vì 220.

**Bài 5 — kiểm thử và chứng minh.** Bạn thử 10.000 mảng và một heuristic luôn cho kết quả trùng optimum. Có thể công bố “thuật toán tối ưu cho mọi đầu vào” không?

*Đáp án:* Chưa. Kết luận hợp lệ là “trùng optimum trên 10.000 trường hợp đã thử”. Muốn chứng minh tổng quát, cần lập luận toán học cho mọi đầu vào thỏa tiền điều kiện. Một phản ví dụ hợp lệ đã đủ bác bỏ kết luận tổng quát nếu có.

**Bài 6 — thay đổi trọng số.** Nếu mỗi công việc mang một giá trị thưởng khác nhau và mục tiêu là tối đa tổng thưởng, chứng minh finish sớm nhất ở phần 3 có còn dùng được không?

*Đáp án:* Không. Bước đổi một công việc lấy một công việc khác giữ **số lượng** nhưng có thể giảm tổng thưởng. Bài có trọng số cần kỹ thuật phù hợp, chẳng hạn weighted interval scheduling bằng quy hoạch động.

**Bài 7 — xác định mức bảo đảm.** Một thuật toán có chứng minh luôn đạt ít nhất 90% OPT cho bài tối đa hóa với OPT dương. Nó có tối ưu không?

*Đáp án:* Không nhất thiết. Nó có **bảo đảm xấp xỉ** chứ không bảo đảm bằng đúng OPT. Nếu trên một đầu vào cụ thể nó đạt OPT, điều đó chỉ chứng minh tối ưu trên đầu vào ấy khi có cách kiểm chứng giá trị tối ưu.

## Ghi nhớ

- **Tham lam** là một phương pháp chọn cục bộ; **tối ưu** là kết luận về giá trị toàn cục. Hai khái niệm không đồng nghĩa.
- **Chứng minh tối ưu** cần chỉ ra tính **lựa chọn tham lam an toàn** và cấu trúc con cho phép lặp lựa chọn đó, thường bằng **exchange argument**, **stays-ahead** hoặc một bất biến đặc thù.
- **Earliest finish** tối ưu cho **chọn nhiều khoảng không giao nhau nhất, không trọng số**; chọn **thời lượng ngắn nhất** hoặc **bắt đầu sớm nhất** không tối ưu nói chung.
- **Đổi tiền lấy mệnh giá lớn nhất trước** có thể thất bại với hệ [1,3,4] và amount=6; **DP** tìm số đồng tối thiểu trong miền giá trị vừa phải.
- **Fractional knapsack** cho phép chứng minh tham lam theo mật độ; **0/1 knapsack** không cho phép dùng nguyên chứng minh ấy.
- **Một phản ví dụ hợp lệ** đủ bác bỏ bảo đảm tối ưu tổng quát; **nhiều kiểm thử đúng** không thay thế chứng minh.
- Hãy công bố đúng mức: **tối ưu có chứng minh**, **xấp xỉ có bảo đảm**, hay **heuristic dựa trên kinh nghiệm**, cùng với các **tiền điều kiện** của kết luận.
