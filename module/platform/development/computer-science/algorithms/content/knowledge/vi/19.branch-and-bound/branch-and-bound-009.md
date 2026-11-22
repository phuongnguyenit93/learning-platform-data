# Chứng minh không loại bỏ lời giải tối ưu trong nhánh và cận

## 1. Cắt nhánh nhanh là tốt, nhưng phải bảo toàn nghiệm tối ưu

**Nhánh và cận (Branch and Bound, B&B)** là kỹ thuật tìm kiếm lời giải tối ưu trong một không gian tổ hợp lớn. Ta chia bài toán thành các **nhánh** tương ứng với quyết định chưa thực hiện, đồng thời sử dụng **cận** để kết luận một số nhánh không thể giúp cải thiện lời giải đã biết. Nhờ đó, ta không cần mở rộng toàn bộ cây tìm kiếm.

Vấn đề quan trọng nhất không phải là “cắt được bao nhiêu nhánh”, mà là:

> **Làm sao chứng minh mọi nhánh bị loại đều không chứa một lời giải tốt hơn nghiệm khả thi tốt nhất đã tìm được?**

Nếu cận sai, chương trình có thể rất nhanh, trả một nghiệm hợp lệ, nhưng **không tối ưu**. Một phản ví dụ nhỏ đủ cho thấy thuật toán đã bỏ nhầm nhánh chứa đáp án tốt nhất.

Cần phân biệt hai mục tiêu:

1. **Tìm giá trị tối ưu và ít nhất một nghiệm đạt giá trị đó.** Khi một nhánh chỉ có thể tạo nghiệm **bằng hoặc kém** nghiệm hiện có, ta có thể loại bỏ.
2. **Liệt kê hoặc đếm tất cả nghiệm tối ưu.** Khi một nhánh có thể tạo nghiệm **bằng** nghiệm hiện có, không được loại chỉ vì không cải thiện giá trị, nếu các nghiệm bằng nhau vẫn phải được ghi nhận.

Bài học sẽ thiết lập chứng minh tổng quát cho hai dạng **min/max**, sau đó triển khai ví dụ Java 17 hoàn chỉnh cho **balo 0/1 tối đa hóa lợi nhuận**. Cận trên dùng bài toán **balo phân số** (fractional knapsack relaxation), được tính bằng phép toán số nguyên chính xác để tránh sai do làm tròn số thực. Ngoài ra ta dùng vét cạn làm **lời giải gốc** để đối chứng nhiều trường hợp.

## 2. Ba khái niệm phải tách bạch: trạng thái, nghiệm khả thi, cận

### 2.1. Trạng thái và những cách hoàn thiện nó

Một trạng thái `s` mô tả các quyết định đã chốt (ví dụ đã chọn hoặc loại một số đồ vật) cùng tài nguyên còn lại. Ký hiệu:

\[
\mathcal{F}(s)
\]

là tập tất cả **nghiệm hoàn chỉnh, khả thi** có thể thu được bằng cách tiếp tục từ trạng thái `s`.

Trạng thái gốc tương ứng chưa đưa ra quyết định nào. Hai nhánh “chọn” và “không chọn” một đồ vật tạo ra các trạng thái con. Nếu mọi nghiệm khả thi đều ứng với ít nhất một đường đi trong cây tìm kiếm, ta nói việc **phân nhánh đầy đủ**.

Một nhánh có thể bị loại an toàn vì:

- **Bất khả thi:** nó không thể hoàn thiện thành nghiệm hợp lệ (ví dụ đã vượt trọng lượng cho phép mà sau đó chỉ được thêm trọng lượng dương).
- **Cận không thể cải thiện:** ngay cả kết quả lý tưởng nhất của nhánh cũng không tốt hơn nghiệm khả thi đang có.
- **Thống trị đã chứng minh:** có một trạng thái/nhánh khác không kém ở mọi yếu tố liên quan và có thể thay thế toàn bộ các hoàn thiện của nhánh bị loại.

Các lý do này **khác nhau**. Không được viết chung một điều kiện “nhánh có vẻ kém” mà không chỉ ra bất đẳng thức hoặc phép ánh xạ bảo đảm an toàn.

### 2.2. Nghiệm tốt nhất đã tìm được: incumbent

**Incumbent** là nghiệm **khả thi đầy đủ** tốt nhất đã tìm được tại thời điểm hiện tại. Gọi `I` là **giá trị** của nghiệm đó.

- Với bài **tối đa hóa**, `I` là một **cận dưới toàn cục** cho giá trị tối ưu `OPT`, bởi `I\le OPT`.
- Với bài **tối thiểu hóa**, `I` là một **cận trên toàn cục** cho `OPT`, bởi `OPT\le I`.

Không được cập nhật `I` bằng điểm của một **trạng thái chưa hoàn thiện** nếu điểm ấy chưa tương ứng với một nghiệm thực sự khả thi. Một điểm tính theo bài toán nới lỏng cũng **không phải incumbent**, vì có thể không thể đạt được trong bài gốc.

Ví dụ với balo tối đa hóa lợi nhuận, nếu cho phép **không lấy món nào** và mọi giá trị không âm, nghiệm rỗng hợp lệ có giá trị `0`. Ta có thể khởi tạo `I=0`. Nếu bài có ràng buộc phải chọn một món, khởi tạo `0` không còn tự động đại diện cho nghiệm hợp lệ; phải thay đổi thiết kế.

### 2.3. Cận tại một trạng thái

Với bài **tối đa hóa**, cận trên `UB(s)` phải thỏa:

\[
\forall x\in\mathcal{F}(s),\quad
f(x)\le UB(s).
\]

Với bài **tối thiểu hóa**, cận dưới `LB(s)` phải thỏa:

\[
\forall x\in\mathcal{F}(s),\quad
LB(s)\le f(x).
\]

Đây là các **điều kiện có định lượng “với mọi hoàn thiện hợp lệ”**. Một công thức chỉ đúng với vài nghiệm từng thử hoặc chỉ là kết quả của một heuristic chưa đủ để gọi là cận an toàn.

**Cận tốt (tight bound)** giúp cắt nhiều nhánh hơn, nhưng **cận lỏng vẫn đúng** nếu bất đẳng thức nêu trên được bảo đảm. Ngược lại, một “cận rất chặt” nhưng đánh giá thiếu khả năng của nhánh có thể cắt mất nghiệm tối ưu.

## 3. Hai bất đẳng thức cắt nhánh phải nhớ

| Loại bài | Incumbent `I` | Cận tại trạng thái `s` | Có thể cắt `s` khi chỉ cần một nghiệm tối ưu |
|---|---|---|---|
| **Tối đa hóa** | Giá trị nghiệm khả thi đang tốt nhất | Cận trên `UB(s)` | **`UB(s)\le I`** |
| **Tối thiểu hóa** | Giá trị nghiệm khả thi đang tốt nhất | Cận dưới `LB(s)` | **`LB(s)\ge I`** |

Ví dụ tối đa hóa:

```text
Incumbent là một nghiệm khả thi có điểm 40.
Một nhánh có cận trên UB = 38.
=> Mọi nghiệm trong nhánh đều có điểm <= 38 < 40.
=> Loại nhánh không thể mất một nghiệm tốt hơn 40.

Nếu UB = 45:
=> Nhánh có thể chứa điểm 41..45; chưa được loại.
=> UB=45 KHÔNG khẳng định chắc chắn có nghiệm điểm 45.
```

Ví dụ tối thiểu hóa:

```text
Incumbent là một nghiệm khả thi chi phí 17.
Một nhánh có cận dưới LB = 20.
=> Mọi nghiệm trong nhánh đều có chi phí >= 20 > 17.
=> Loại nhánh an toàn.

Nếu LB = 9:
=> Nhánh có thể chứa nghiệm rẻ hơn 17; phải tiếp tục,
   trừ khi có chứng minh loại nhánh độc lập khác.
```

### Dấu bằng và yêu cầu liệt kê tất cả nghiệm tối ưu

Nếu chỉ cần **giá trị** hoặc **một nghiệm** đạt tối ưu, các dấu `UB\le I` và `LB\ge I` an toàn. Nhánh cho kết quả bằng `I` không làm giá trị tốt nhất tăng/giảm thêm.

Nếu muốn **liệt kê tất cả nghiệm đạt giá trị tối ưu**, phải giữ khả năng phát hiện nghiệm **bằng** incumbent. Khi chỉ dùng cận giá trị:

- Tối đa hóa: chỉ loại vì cận khi **`UB<I`**.
- Tối thiểu hóa: chỉ loại vì cận khi **`LB>I`**.

Kể cả với dấu nghiêm ngặt, cần bảo đảm quá trình gộp trạng thái, quy tắc phá đối xứng, lựa chọn nhánh và lưu kết quả không loại mất các nghiệm mà đề muốn liệt kê.

Nếu có **mục tiêu phụ** như “lợi nhuận lớn nhất, rồi trong các nghiệm hòa chọn trọng lượng nhỏ nhất”, cắt khi `UB=I` có thể bỏ một nghiệm **cùng lợi nhuận nhưng tốt hơn theo tiêu chí phụ**. Hãy định nghĩa thứ tự mục tiêu đầy đủ, dùng cận cho cặp tiêu chí, hoặc không cắt những trường hợp hòa khi chưa có chứng minh.

## 4. Chứng minh hình thức: vì sao cắt nhánh không làm mất giá trị tối ưu?

Ta xét bài **tối đa hóa**. Giả sử:

1. **Phân nhánh đầy đủ:** mọi nghiệm khả thi hoàn chỉnh nằm trong ít nhất một nhánh của cây, trước khi cắt.
2. **Incumbent khả thi:** `I` luôn là giá trị của một nghiệm hợp lệ đã tìm thấy.
3. **Cận trên đúng:** với mọi trạng thái `s`, mọi hoàn thiện khả thi `x\in\mathcal{F}(s)` thỏa `f(x)\le UB(s)`.
4. Chỉ loại nhánh vì cận nếu `UB(s)\le I`, hoặc vì một lý do bất khả thi/thống trị được chứng minh độc lập.

Giả sử có một nghiệm tối ưu toàn cục `x^*` với giá trị `OPT`. Nếu một nhánh chứa `x^*` bị cắt ở trạng thái `s`, thì:

\[
OPT=f(x^*)\le UB(s)\le I.
\]

Nhưng `I` là giá trị của một nghiệm khả thi, nên:

\[
I\le OPT.
\]

Suy ra:

\[
OPT\le I\le OPT \quad\Longrightarrow\quad I=OPT.
\]

Nghĩa là **nếu nhánh chứa một nghiệm tối ưu bị cắt**, thì ngay lúc ấy ta **đã có** một nghiệm khả thi đạt đúng giá trị tối ưu. Vì vậy giá trị đáp án không bị ảnh hưởng.

Nếu chưa có nghiệm tối ưu nào được tìm ra, một nhánh chứa mọi nghiệm tối ưu **không thể** thỏa điều kiện cắt `UB(s)\le I` với cận đúng. Kết hợp tính đầy đủ của phân nhánh và việc tìm kiếm kết thúc sau hữu hạn quyết định, thuật toán cuối cùng trả đúng giá trị tối ưu.

Với bài **tối thiểu hóa**, lập luận đối xứng:

\[
OPT=f(x^*)\ge LB(s)\ge I,
\]

trong khi một nghiệm khả thi incumbent có `OPT\le I`, nên `OPT=I`.

**Tuyên bố được chứng minh là:** giữ lại **giá trị tối ưu và ít nhất một nghiệm tối ưu**. Không nhất thiết giữ lại **mọi** nghiệm tối ưu, vì cắt ở dấu bằng có thể bỏ các nghiệm tối ưu khác.

### Bất biến cần duy trì suốt tìm kiếm

- Incumbent luôn **khả thi** và chỉ cải thiện: không giảm ở bài max, không tăng ở bài min.
- Mọi nhánh chưa duyệt vẫn được biểu diễn trong cây tìm kiếm hoặc đã bị loại bằng điều kiện an toàn.
- Cận tại một nút bao trùm **mọi khả năng hoàn thiện hợp lệ** của nút, không chỉ một đường đi đang được thử.
- Mỗi quyết định phân nhánh duyệt hết các khả năng cần thiết. Khi loại trường hợp không thể chọn vì vượt sức chứa, phải chứng minh không có phép biến đổi sau đó khiến nó hợp lệ.
- Mọi giá trị dùng để so cận phải được tính **không tràn và không làm tròn thiếu** so với bất đẳng thức cần thiết.

## 5. Tìm cận an toàn từ bài toán nới lỏng

Một phương pháp phổ biến là **nới lỏng (relaxation)**: cho phép nhiều phương án hơn bài gốc, sao cho tập nghiệm của bài gốc là tập con của tập nghiệm bài nới lỏng.

Gọi `F` là tập nghiệm bài gốc, `R` là tập nghiệm nới lỏng:

\[
F\subseteq R.
\]

Khi đó:

- **Max:** `\max_{x\in F}f(x)\le\max_{x\in R}f(x)`. Tối ưu của bài nới lỏng là **cận trên**.
- **Min:** `\min_{x\in R}f(x)\le\min_{x\in F}f(x)`. Tối ưu của bài nới lỏng là **cận dưới**.

Điều kiện quyết định là **nới lỏng thêm lựa chọn**, không phải vô tình giới hạn bớt lựa chọn. Nếu tập “nới lỏng” nhỏ hơn tập nghiệm gốc, ta có thể thu một ước lượng **quá lạc quan sai hướng** và cắt nhầm.

### Cận rất dễ chứng minh nhưng lỏng

Trong balo 0/1 tối đa hóa giá trị không âm, tại một nút có lợi nhuận `p` và các món chưa xét có giá trị `v_j\ge0`, ta luôn có:

\[
UB_{\mathrm{sum}}=p+\sum_{j\text{ chưa xét}}v_j.
\]

Đây là cận trên vì ngay cả khi lấy hết mọi món còn lại (bỏ qua sức chứa), lợi nhuận cũng không thể vượt tổng này. Nó **an toàn** nhưng thường quá lớn, cắt rất ít nhánh.

Một cận tốt hơn có thể tính theo bài **balo phân số**: vẫn giới hạn sức chứa, nhưng cho phép lấy một phần của đồ vật. Bài nới lỏng có thêm lựa chọn nên tối ưu của nó không nhỏ hơn tối ưu 0/1. Đây là ví dụ sẽ dùng trong Java.

## 6. Ví dụ chi tiết: balo 0/1 tối đa hóa lợi nhuận

Cho `n` đồ vật. Đồ vật `i` có:

- Trọng lượng `w_i>0`.
- Lợi nhuận `v_i\ge0`.
- Sức chứa balo `C\ge0`.

Chọn tập chỉ số `X` sao cho:

\[
\sum_{i\in X}w_i\le C,
\]

và tối đa hóa:

\[
\sum_{i\in X}v_i.
\]

Mỗi món chỉ được chọn tối đa một lần. **Tập rỗng hợp lệ**, có trọng lượng `0` và lợi nhuận `0`. Nếu `C=0`, vì các trọng lượng đều dương nên tập rỗng là nghiệm duy nhất.

### 6.1. Trạng thái của cây nhánh và cận

Sắp các món theo **tỷ lệ `v_i/w_i` giảm dần** để tính cận phân số nhanh hơn. Việc sắp xếp chỉ thay **thứ tự quyết định**, không thay danh tính món. Mỗi món vẫn mang `originalIndex` để trả kết quả theo chỉ số đầu vào.

Trạng thái đệ quy:

```text
dfs(pos, usedWeight, currentProfit)
```

Ý nghĩa:

- Đã quyết định **chọn/bỏ** tất cả món ở các vị trí `0..pos-1` trong thứ tự đã sắp.
- `usedWeight` là tổng trọng lượng món đã chọn.
- `currentProfit` là tổng lợi nhuận món đã chọn.
- Các món ở `pos..n-1` chưa quyết định.
- Incumbent toàn cục là lợi nhuận tốt nhất của một tập con hợp lệ đã tìm.

Tại mỗi nút, có hai nhánh:

1. **Chọn** món `pos` nếu `usedWeight+w_{pos}\le C`.
2. **Không chọn** món `pos`.

Hai nhánh bao phủ mọi tập con hợp lệ theo lựa chọn món này. Khi đã vượt sức chứa, nhánh chọn là **bất khả thi** vì các trọng lượng dương và không có thao tác xóa các món đã chọn trong phần tiếp theo.

### 6.2. Vì sao phải dùng lợi nhuận phân số để làm cận trên?

Trong bài nới lỏng, mỗi món có thể được lấy một tỷ lệ `x_i`:

\[
0\le x_i\le1
\]

thay vì chỉ `x_i\in\{0,1\}`. Ta tối đa hóa:

\[
\sum v_ix_i
\quad\text{với}\quad
\sum w_ix_i\le \text{capacity còn lại}.
\]

Mọi lựa chọn 0/1 hợp lệ đều là một lựa chọn phân số hợp lệ. Do đó:

\[
OPT_{\mathrm{0/1}}(s)
\le OPT_{\mathrm{fractional}}(s).
\]

Để giải bài phân số với trọng lượng dương và giá trị không âm, ta tham lam lấy món theo tỷ lệ `v_i/w_i` từ cao xuống thấp, lấy trọn món khi còn đủ chỗ, và lấy **một phần** của món đầu tiên không vừa.

**Chứng minh bằng trao đổi:** nếu một nghiệm phân số đang dành một lượng trọng lượng cho món có tỷ lệ thấp trong khi món có tỷ lệ cao còn chưa lấy hết, chuyển một lượng trọng lượng nhỏ từ món thấp sang món cao không làm lợi nhuận giảm. Lặp thao tác đó, ta thu được nghiệm phân số theo thứ tự tỷ lệ giảm mà không kém nghiệm ban đầu. Vì thế cách tham lam này cho **tối ưu của bài phân số**, không phải tối ưu của bài 0/1.

### 6.3. Một ví dụ có thể tính bằng tay

```text
Chỉ số gốc:     0    1    2    3
Trọng lượng:    2    3    4    5
Lợi nhuận:      3    4    5    8
Sức chứa C = 8
```

Các tỷ lệ lợi nhuận/trọng lượng:

```text
Món 3: 8/5 = 1.6
Món 0: 3/2 = 1.5
Món 1: 4/3 ≈ 1.333
Món 2: 5/4 = 1.25
```

Ở nút gốc, balo phân số lấy trọn món `3` (trọng lượng `5`, lợi nhuận `8`), trọn món `0` (trọng lượng `2`, lợi nhuận `3`), rồi còn `1` đơn vị sức chứa nên lấy `1/3` món `1`, thêm `4/3` lợi nhuận.

Giá trị nới lỏng:

\[
8+3+\frac43=12+\frac13.
\]

Vì lợi nhuận của mọi nghiệm 0/1 là **số nguyên**, có thể dùng một cận nguyên an toàn theo hướng làm tròn lên:

\[
UB_{\mathrm{root}}=\left\lceil12+\frac13\right\rceil=13.
\]

Đây là cận trên, **không khẳng định** có một tập con 0/1 đạt giá trị `13`. Thực tế nghiệm tối ưu là chọn chỉ số gốc `[1,3]`, có trọng lượng `3+5=8` và lợi nhuận `4+8=12`.

Bảng so sánh:

| Phương án | Giá trị | Vai trò |
|---|---:|---|
| Tập rỗng | 0 | Incumbent khả thi ban đầu |
| Chọn các chỉ số `[1,3]` | 12 | Một nghiệm 0/1 khả thi, thực tế tối ưu |
| Lấy phân số ở nút gốc | `12+1/3` | Tối ưu của bài nới lỏng |
| Cận nguyên dùng trong mã | 13 | Cận trên an toàn (có thể lỏng hơn số thực) |
| Tổng mọi lợi nhuận | 20 | Một cận trên dễ tính nhưng lỏng |

Khi đã biết một nghiệm có giá trị `12`, mọi nhánh có `UB\le12` đều có thể bị cắt nếu chỉ cần **một nghiệm tối ưu**. Nhánh có `UB=13` chưa thể bị cắt dựa riêng vào cận, dù có thể không chứa nghiệm tốt hơn.

## 7. Phản ví dụ: cận “tham lam 0/1” không phải cận trên

Một lỗi rất phổ biến là giải bài 0/1 bằng cách **tham lam lấy nguyên món theo tỷ lệ** rồi gọi kết quả ấy là “cận trên”.

Xét hai món:

```text
C = 3

Món A: weight=2, value=6, ratio=3
Món B: weight=3, value=7, ratio=7/3

Tham lam 0/1 theo ratio:
  lấy A -> còn sức chứa 1, không lấy được B
  profit = 6

Nghiệm tối ưu 0/1:
  chỉ lấy B -> profit = 7
```

Giá trị `6` là lợi nhuận của **một nghiệm khả thi**, tức **cận dưới** đối với bài **max**, chứ **không phải cận trên**. Nếu dùng `UB_{\mathrm{sai}}=6` ở một nhánh thật sự có khả năng đạt `7`, và incumbent bên ngoài nhánh có giá trị `6`, điều kiện sai `UB_{\mathrm{sai}}\le I` sẽ **cắt mất nghiệm tối ưu `7`**.

Ngược lại, bài balo phân số có thể lấy cả món A và `1/3` trọng lượng của B:

\[
6+\frac13\cdot7=8+\frac13.
\]

Cận này lớn hơn hoặc bằng `7` nên không thể tạo quyết định cắt nhầm trong trường hợp trên.

**Bài học:** một heuristic thường cho ta **nghiệm khả thi tốt** để cập nhật incumbent; nó không tự động cho **cận ở phía ngược lại**. Với bài tối đa hóa, muốn cắt phải có **cận trên** thật sự. Với bài tối thiểu hóa, muốn cắt phải có **cận dưới** thật sự.

## 8. Tính cận chính xác trong Java: tránh lỗi số thực và tràn số

### 8.1. Tại sao dùng `BigInteger`?

Các lợi nhuận và trọng lượng có thể lớn. So sánh hai tỷ lệ bằng `double` có thể mất thông tin khi số gần giới hạn `long`:

```text
vA / wA  so với  vB / wB
```

Ta có thể so sánh chính xác bằng phép nhân chéo:

\[
\frac{v_A}{w_A} \gtreqless \frac{v_B}{w_B}
\iff v_Aw_B \gtreqless v_Bw_A,
\]

vì `w_A,w_B>0`. Nhưng nhân hai số `long` trực tiếp có thể tràn. Trong mã, ta dùng `BigInteger` cho hai tích.

Khi chỉ còn `r` đơn vị sức chứa và phải lấy một phần món có lợi nhuận `v`, trọng lượng `w`, lợi nhuận phân số là:

\[
\frac{vr}{w}.
\]

Ta cộng một số nguyên **làm tròn lên chính xác**:

\[
\operatorname{ceilDiv}(vr,w)=
\left\lceil\frac{vr}{w}\right\rceil
=\frac{vr+w-1}{w}
\quad\text{(chia nguyên, với }vr\ge0,w>0\text{)}.
\]

Tính tử số bằng `BigInteger` tránh tràn và làm tròn số thực. **Làm tròn lên không làm cận nhỏ hơn giá trị phân số thực**, nên cận vẫn an toàn. Nó có thể bớt chặt nhưng không tạo lỗi cắt nhầm.

**Lưu ý:** ở đây ta xây cận bằng cách cộng giá trị của các món lấy trọn, rồi cộng phần phân số **làm tròn lên** ở món cuối. Vì chỉ có tối đa **một món lấy phân số** trong thuật toán tham lam này, công thức là rõ ràng.

### 8.2. Khác biệt giữa tính cận và cập nhật incumbent

- Cận `UB` có thể dựa trên **nghiệm phân số không hợp lệ** với bài 0/1.
- Incumbent `I` **chỉ** cập nhật từ **một tập con 0/1 thực sự khả thi**.
- Không được lấy `UB` gán thành `I`.
- Không được dùng `Math.min`/`Math.max` một cách máy móc mà không xác định đang ở bài min hay max.
- Không được chuyển từ `BigInteger` sang `int`/`long` bằng cách làm mất bit rồi so cận.

Ví dụ minh họa dùng `long` cho trọng lượng và sức chứa, `BigInteger` cho lợi nhuận tích lũy/cận, tránh tràn số ngay cả khi tổng lợi nhuận vượt `Long.MAX_VALUE`.

### 8.3. Trọng lượng bằng 0 và giá trị âm

Ví dụ này yêu cầu `weight>0`, `value>=0`. Đây là **điều kiện của cài đặt**, không phải định nghĩa duy nhất của balo 0/1:

- Trọng lượng `0` khiến tỷ lệ `v/w` không xác định; phải tách xử lý các món miễn trọng lượng hoặc dùng một thiết kế bound khác.
- Giá trị âm có thể khiến các lập luận tham lam “cứ lấp đầy sức chứa” cần thay đổi. Nếu được bỏ món, thông thường không có lý do chọn món có lợi nhuận âm khi chỉ tối đa lợi nhuận, nhưng ta vẫn cần chứng minh/cài đặt đúng đặc tả.
- Sức chứa âm là đầu vào không hợp lệ.
- Khi chỉ được lấy nguyên món và tập rỗng hợp lệ, mục tiêu max với các lợi nhuận không âm **luôn có ít nhất một nghiệm khả thi**.

Không tự áp dụng một chứng minh có giả định `w_i>0, v_i>=0` cho bài có số âm, mục tiêu buộc phải chọn đúng `k` món, hoặc có ràng buộc phụ mà bài toán nới lỏng chưa mô tả.

## 9. Java 17+ hoàn chỉnh: nhánh và cận đúng, có nghiệm và kiểm thử vét cạn

Chương trình sau bao gồm:

1. `branchAndBound`: B&B 0/1 knapsack tối đa hóa lợi nhuận, giữ incumbent khả thi và cận trên từ balo phân số.
2. `fractionalUpperBound`: tính cận bằng `BigInteger` chính xác; quét các món chưa quyết định theo tỷ lệ giảm dần.
3. `bruteForce`: liệt kê tất cả tập con cho `n\le20` và lấy lợi nhuận tốt nhất, làm **lời giải gốc** độc lập với cận.
4. `verifyAnswer`: kiểm tra tập chỉ số trả về không trùng, tổng trọng lượng hợp lệ, lợi nhuận thực bằng giá trị công bố.
5. `main`: thử ca mẫu, cạnh biên, số lợi nhuận rất lớn và **300 ca ngẫu nhiên có seed cố định** đối chiếu B&B với vét cạn.

**Quy tắc phá hòa:** ví dụ chỉ cập nhật nghiệm khi tìm được **lợi nhuận lớn hơn nghiêm ngặt**. Với nhiều nghiệm tối ưu, hàm trả **một nghiệm**, không cam kết trọng lượng nhỏ nhất hoặc thứ tự từ điển. Để làm rõ, danh sách chỉ số gốc được **sắp tăng** trước khi trả.

**Điều kiện đầu vào:** hai mảng cùng độ dài và khác `null`, `capacity>=0`, mọi `weight>0`, mọi `value>=0`. Mảng rỗng hợp lệ. Chương trình có thể trở nên chậm trong trường hợp xấu; phép cắt nhánh không thay thế phân tích độ phức tạp xấu nhất.

Lưu tệp **`SafeBranchAndBoundDemo.java`**:

```java
import java.math.BigInteger;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Objects;
import java.util.Random;

public final class SafeBranchAndBoundDemo {
    private SafeBranchAndBoundDemo() {
    }

    private record Item(int originalIndex, long weight, long value) {
    }

    public record Answer(
            BigInteger bestValue,
            long totalWeight,
            List<Integer> indices,
            long visitedNodes,
            long prunedNodes) {
        public Answer {
            indices = List.copyOf(indices);
        }
    }

    private static void validate(
            long[] weights, long[] values, long capacity) {
        Objects.requireNonNull(weights, "weights");
        Objects.requireNonNull(values, "values");
        if (weights.length != values.length || capacity < 0) {
            throw new IllegalArgumentException(
                "length mismatch or negative capacity"
            );
        }
        for (int i = 0; i < weights.length; i++) {
            if (weights[i] <= 0 || values[i] < 0) {
                throw new IllegalArgumentException(
                    "weights must be positive and values nonnegative"
                );
            }
        }
    }

    public static Answer branchAndBound(
            long[] weights, long[] values, long capacity) {
        validate(weights, values, capacity);

        Item[] items = new Item[weights.length];
        for (int i = 0; i < items.length; i++) {
            items[i] = new Item(i, weights[i], values[i]);
        }

        // Sắp theo value/weight giảm, so chính xác bằng nhân chéo.
        Arrays.sort(items, (a, b) -> {
            BigInteger left = BigInteger.valueOf(a.value())
                .multiply(BigInteger.valueOf(b.weight()));
            BigInteger right = BigInteger.valueOf(b.value())
                .multiply(BigInteger.valueOf(a.weight()));
            int cmp = right.compareTo(left);
            return cmp != 0
                ? cmp
                : Integer.compare(a.originalIndex(), b.originalIndex());
        });

        Search search = new Search(items, capacity);
        search.dfs(0, 0L, BigInteger.ZERO);
        return new Answer(
            search.bestValue,
            search.bestWeight,
            search.bestIndices,
            search.visitedNodes,
            search.prunedNodes
        );
    }

    private static final class Search {
        final Item[] items;
        final long capacity;
        final boolean[] chosen;

        BigInteger bestValue = BigInteger.ZERO;
        long bestWeight = 0L;
        List<Integer> bestIndices = List.of();
        long visitedNodes = 0L;
        long prunedNodes = 0L;

        Search(Item[] items, long capacity) {
            this.items = items;
            this.capacity = capacity;
            this.chosen = new boolean[items.length];
        }

        // Cận trên: tối ưu balo PHÂN SỐ từ các món chưa quyết định.
        // Dùng ceil với BigInteger => không đánh giá THẤP khả năng.
        BigInteger fractionalUpperBound(
                int position, long remaining,
                BigInteger currentProfit) {
            BigInteger upper = currentProfit;

            for (int j = position;
                    j < items.length && remaining > 0; j++) {
                Item x = items[j];

                if (x.weight() <= remaining) {
                    remaining -= x.weight();
                    upper = upper.add(BigInteger.valueOf(x.value()));
                } else {
                    BigInteger numerator =
                        BigInteger.valueOf(x.value())
                            .multiply(BigInteger.valueOf(remaining));
                    BigInteger denominator =
                        BigInteger.valueOf(x.weight());
                    // ceil(numerator / denominator), mẫu dương.
                    BigInteger roundedUp =
                        numerator.add(denominator)
                            .subtract(BigInteger.ONE)
                            .divide(denominator);
                    upper = upper.add(roundedUp);
                    break;
                }
            }
            return upper;
        }

        void dfs(
                int position, long usedWeight,
                BigInteger currentProfit) {
            visitedNodes++;

            BigInteger upper = fractionalUpperBound(
                position,
                capacity - usedWeight,
                currentProfit
            );
            if (upper.compareTo(bestValue) <= 0) {
                prunedNodes++;
                return; // Không thể cải thiện incumbent khả thi.
            }

            if (position == items.length) {
                // Do upper>bestValue và không còn món, profit>best.
                bestValue = currentProfit;
                bestWeight = usedWeight;

                List<Integer> selected = new ArrayList<>();
                for (int j = 0; j < items.length; j++) {
                    if (chosen[j]) {
                        selected.add(items[j].originalIndex());
                    }
                }
                Collections.sort(selected);
                bestIndices = List.copyOf(selected);
                return;
            }

            Item x = items[position];

            // Nhánh chọn: chỉ mở khi trọng lượng còn đủ.
            // Dùng phép trừ để tránh overflow khi so sánh.
            if (x.weight() <= capacity - usedWeight) {
                chosen[position] = true;
                dfs(
                    position + 1,
                    usedWeight + x.weight(),
                    currentProfit.add(BigInteger.valueOf(x.value()))
                );
                chosen[position] = false;
            }

            // Nhánh bỏ: luôn hợp lệ nếu trạng thái cha hợp lệ.
            dfs(position + 1, usedWeight, currentProfit);
        }
    }

    // Oracle vét cạn cho n<=20: xét tất cả tập con theo chỉ số.
    public static BigInteger bruteForce(
            long[] weights, long[] values, long capacity) {
        validate(weights, values, capacity);
        int n = weights.length;
        if (n > 20) {
            throw new IllegalArgumentException(
                "bruteForce supports at most 20 items"
            );
        }

        BigInteger best = BigInteger.ZERO;
        long subsets = 1L << n;

        for (long mask = 0; mask < subsets; mask++) {
            long remaining = capacity;
            BigInteger profit = BigInteger.ZERO;
            boolean feasible = true;

            for (int i = 0; i < n; i++) {
                if ((mask & (1L << i)) == 0L) {
                    continue;
                }
                if (weights[i] > remaining) {
                    feasible = false;
                    break;
                }
                remaining -= weights[i];
                profit = profit.add(BigInteger.valueOf(values[i]));
            }

            if (feasible && profit.compareTo(best) > 0) {
                best = profit;
            }
        }
        return best;
    }

    // Kiểm tra chỉ số, trọng lượng và lợi nhuận nghiệm đã trả.
    public static boolean verifyAnswer(
            Answer answer,
            long[] weights, long[] values, long capacity) {
        validate(weights, values, capacity);
        boolean[] seen = new boolean[weights.length];
        long remaining = capacity;
        BigInteger profit = BigInteger.ZERO;

        for (int index : answer.indices()) {
            if (index < 0 || index >= weights.length || seen[index]) {
                return false;
            }
            seen[index] = true;
            if (weights[index] > remaining) {
                return false;
            }
            remaining -= weights[index];
            profit = profit.add(BigInteger.valueOf(values[index]));
        }

        return profit.equals(answer.bestValue())
            && capacity - remaining == answer.totalWeight();
    }

    public static void main(String[] args) {
        long[] weight = {2, 3, 4, 5};
        long[] value = {3, 4, 5, 8};
        Answer example = branchAndBound(weight, value, 8);

        System.out.println("Example best value: "
            + example.bestValue());
        System.out.println("Example total weight: "
            + example.totalWeight());
        System.out.println("Example indices: "
            + example.indices());
        System.out.println("Example brute value: "
            + bruteForce(weight, value, 8));
        System.out.println("Example witness valid: "
            + verifyAnswer(example, weight, value, 8));
        System.out.println("Example pruned some nodes: "
            + (example.prunedNodes() > 0));

        System.out.println("All overweight: "
            + branchAndBound(
                new long[] {5, 7}, new long[] {6, 8}, 4
            ).bestValue());
        System.out.println("Empty items: "
            + branchAndBound(
                new long[0], new long[0], 10
            ).bestValue());
        System.out.println("Capacity zero: "
            + branchAndBound(
                new long[] {1, 2}, new long[] {7, 8}, 0
            ).bestValue());
        System.out.println("Tie profit: "
            + branchAndBound(
                new long[] {2, 2}, new long[] {5, 5}, 2
            ).bestValue());
        System.out.println("Zero profits: "
            + branchAndBound(
                new long[] {1, 2}, new long[] {0, 0}, 2
            ).bestValue());
        System.out.println("Large exact profit: "
            + branchAndBound(
                new long[] {1, 1},
                new long[] {Long.MAX_VALUE, Long.MAX_VALUE},
                2
            ).bestValue());

        Random random = new Random(256L);
        int checked = 0;

        for (int trial = 0; trial < 300; trial++) {
            int n = random.nextInt(11); // 0..10
            long[] w = new long[n];
            long[] v = new long[n];

            for (int i = 0; i < n; i++) {
                w[i] = 1 + random.nextInt(9);
                v[i] = random.nextInt(19);
            }

            long cap = random.nextInt(30);
            Answer fast = branchAndBound(w, v, cap);
            BigInteger slow = bruteForce(w, v, cap);

            if (!fast.bestValue().equals(slow)
                    || !verifyAnswer(fast, w, v, cap)) {
                throw new AssertionError(
                    "Mismatch at trial " + trial
                );
            }
            checked++;
        }

        System.out.println("Random oracle checks: " + checked);

        boolean rejected = false;
        try {
            branchAndBound(
                new long[] {0}, new long[] {5}, 1
            );
        } catch (IllegalArgumentException expected) {
            rejected = true;
        }
        System.out.println("Zero weight rejected: " + rejected);
    }
}
```

Biên dịch và chạy bằng **JDK 17 trở lên**, lưu tệp nguồn UTF-8:

```bash
javac -encoding UTF-8 SafeBranchAndBoundDemo.java
java SafeBranchAndBoundDemo
```

**Đầu ra chuẩn:**

```text
Example best value: 12
Example total weight: 8
Example indices: [1, 3]
Example brute value: 12
Example witness valid: true
Example pruned some nodes: true
All overweight: 0
Empty items: 0
Capacity zero: 0
Tie profit: 5
Zero profits: 0
Large exact profit: 18446744073709551614
Random oracle checks: 300
Zero weight rejected: true
```

### Tại sao chương trình trả một tập chỉ số hợp lệ?

Mỗi món được quyết định đúng một lần ở một vị trí trong mảng `items` đã sắp. Mảng `chosen[]` theo dõi những quyết định “chọn” trên đường đệ quy hiện tại. Khi xét nhánh chọn, chương trình kiểm tra `weight<=capacity-usedWeight`, sau đó mới cộng vào `usedWeight`.

Tại một **lá** (đã quyết định toàn bộ món), `chosen[]` xác định đúng một tập con, không lặp chỉ số. Mã chỉ lưu nó khi lợi nhuận lớn hơn incumbent, nên `bestIndices` luôn đi kèm một nghiệm khả thi có giá trị `bestValue`.

Khi quay lui, `chosen[position]=false` hoàn tác quyết định vừa thử trước khi đi nhánh bỏ. Nếu quên hoàn tác, các phần tử của nhánh trước có thể “rò” sang nhánh sau, làm lời giải sai dù công thức cận đúng.

### Tại sao sắp theo tỷ lệ không làm đổi bài toán?

Balo 0/1 chỉ yêu cầu chọn một **tập món theo chỉ số**, không yêu cầu thứ tự chọn món. Sắp xếp chỉ thay thứ tự tạo quyết định trong cây. Mỗi món giữ `originalIndex`, nên mọi tập chỉ số gốc vẫn được biểu diễn bởi một đường đi chọn/bỏ các món đã sắp.

Nếu bài có ràng buộc phụ theo thứ tự, ví dụ bắt buộc giữ thứ tự đầu vào hoặc có chi phí chuyển giữa hai món, phép sắp xếp có thể phá mô hình. Không được áp dụng cùng cách phân nhánh nếu chưa chứng minh nó giữ đầy đủ nghiệm hợp lệ.

### Vì sao phiên bản này không dùng `double` làm cận?

Cận là một điều kiện **tính đúng**, không chỉ là mẹo tăng tốc. Nếu số thực làm tròn thiếu khiến một cận thật sự lớn hơn incumbent bị tính xuống nhỏ hơn hoặc bằng incumbent, chương trình có thể cắt nhầm. Tích và phép chia `BigInteger` trong ví dụ xây **cận nguyên không thấp hơn tối ưu phân số**, tránh phụ thuộc độ chính xác nhị phân của `double` trong phép cắt.

Hệ quả là tính cận có chi phí số học lớn hơn và một cận làm tròn lên có thể lỏng hơn cận thực. Đó là một đánh đổi **an toàn – hiệu năng** hợp lý trong bài học về chứng minh không bỏ nghiệm tối ưu.

## 10. Chứng minh đầy đủ tính đúng của chương trình balo

### 10.1. Cây tìm kiếm bao trùm mọi tập con

Sau khi sắp các món, mỗi đồ vật có một vị trí duy nhất `pos`. Ở mỗi vị trí ta phân nhánh “chọn” hoặc “bỏ”:

- Mọi tập con của `n` món tương ứng chính xác một dãy `n` quyết định nhị phân.
- Nếu nhánh chọn bị bỏ vì không đủ sức chứa, mọi cách hoàn thiện giữ nguyên món vừa chọn vẫn vượt sức chứa: các món còn lại có trọng lượng dương, không có thao tác giảm trọng lượng đã chọn.
- Do đó cắt nhánh không đủ sức chứa **chỉ loại những tập con bất khả thi**.

Vậy trước khi dùng cận lợi nhuận, mọi tập con khả thi đều được bao phủ bởi ít nhất một đường đi trong cây.

### 10.2. Cận phân số không thấp hơn mọi hoàn thiện 0/1

Ở trạng thái `s=(pos,usedWeight,currentProfit)`:

- Tất cả món đã chọn trước `pos` được **cố định**.
- Chỉ các món ở vị trí `pos,\ldots,n-1` được quyết định tiếp.
- Sức chứa còn lại là `R=C-usedWeight\ge0`.
- Mọi hoàn thiện 0/1 của `s` là một lựa chọn `x_j\in\{0,1\}` cho những món còn lại với `\sum w_jx_j\le R`.

Bài nới lỏng thay `\{0,1\}` bằng `[0,1]`, chứa **toàn bộ** những hoàn thiện 0/1. Tham lam theo tỷ lệ `v/w` giải tối ưu phân số do lập luận trao đổi; cộng lợi nhuận hiện có cho một giá trị `F(s)` thỏa:

\[
\forall x\in\mathcal F(s),\quad f(x)\le F(s).
\]

Hàm `fractionalUpperBound` dùng các phép tính chính xác và làm tròn lên phần phân số, cho `UB(s)\ge F(s)`. Suy ra:

\[
\forall x\in\mathcal F(s),\quad f(x)\le UB(s).
\]

Đây là bất biến cận cần thiết. **Tính đúng không yêu cầu cận bằng tối ưu 0/1**, chỉ cần không đánh giá thấp nó.

### 10.3. Incumbent luôn là nghiệm khả thi

Ban đầu tập rỗng có lợi nhuận `0`, trọng lượng `0\le C`, nên `bestValue=0` là khả thi.

Mỗi lần cập nhật tốt hơn chỉ xảy ra ở **lá** và sau một chuỗi quyết định đã kiểm tra trọng lượng không vượt sức chứa. Giá trị `currentProfit` là tổng thật của các món đã chọn; `bestIndices` được sao chép từ các quyết định hiện tại. Vậy `bestValue` luôn gắn với một nghiệm khả thi.

### 10.4. Phép cắt `UB\le incumbent` không mất giá trị tối ưu

Nếu một nhánh chứa tập con tối ưu `x^*` bị cắt:

\[
OPT=f(x^*)\le UB(s)\le bestValue.
\]

Trong khi `bestValue\le OPT` vì luôn là nghiệm khả thi. Vậy `bestValue=OPT` trước khi cắt. Không có trường hợp ta loại nhánh chứa nghiệm tối ưu khi chưa có một nghiệm tối ưu khác (hoặc chính nghiệm ấy) đã đạt được.

Vì cây có hữu hạn `2^n` dãy quyết định và các nhánh bất khả thi cũng đã bị loại đúng, quá trình tìm kiếm kết thúc với giá trị **toàn cục tối ưu**. Một tập chỉ số gốc đã được lưu đi kèm giá trị ấy.

**Phạm vi chứng minh:** tối đa hóa tổng lợi nhuận với các giả định `weight>0, value>=0, capacity>=0`, không có ràng buộc phụ ngoài sức chứa, và chỉ cần **một** nghiệm tối ưu. Chứng minh không cho phép sửa điều kiện sang `UB<I+\varepsilon`, áp dụng cận tính thiếu, hoặc yêu cầu liệt kê mọi nghiệm tối ưu mà vẫn cắt tại dấu bằng.

## 11. Hiểu đúng ba mức cắt nhánh

### 11.1. Cắt do bất khả thi

Ví dụ trong balo: đã dùng `7` đơn vị trọng lượng, sức chứa `8`, món kế tiếp nặng `3`. Nhánh **chọn** món này sẽ có trọng lượng `10>8`, không thể là một phần của nghiệm hợp lệ. Không mở nhánh ấy là đúng.

Nhưng trong bài toán khác có thể có thao tác xóa/chuyển nguồn lực về sau, hoặc trọng lượng âm nếu mô hình cho phép. Lúc đó phép kết luận “vượt một lần thì mãi vượt” **cần được chứng minh lại**.

### 11.2. Cắt do cận

Giả sử incumbent lợi nhuận `12` và một nút có `UB=11`. Cận này chứng minh mọi hoàn thiện của nút có lợi nhuận tối đa `11`, nên không thể vượt `12`. Cắt là đúng.

Tại nút có `UB=13`, dù vừa thử một nhánh không tìm ra nghiệm tốt hơn `12`, **không được tự động cắt mọi nhánh anh em** dựa trên kết quả thử nhánh ấy. Cận của mỗi nhánh phải bao phủ **mọi hoàn thiện thuộc chính nhánh đó**.

### 11.3. Cắt do thống trị

Một lập luận thống trị điển hình:

> Nếu hai trạng thái có **cùng tập quyết định còn lại** và một trạng thái dùng **không nhiều tài nguyên hơn** nhưng đã có **lợi nhuận không thấp hơn**, thì trạng thái còn lại có thể bị thống trị.

Cần đủ điều kiện:

- Mọi quyết định có thể tiếp tục từ trạng thái yếu đều có thể tiếp tục từ trạng thái mạnh.
- Với cùng cách tiếp tục, giá trị cuối từ trạng thái mạnh không kém.
- Các yếu tố phụ như số món bắt buộc, thời gian, nhãn, chi phí chuyển tiếp và mục tiêu phụ không phá quan hệ này.

Chỉ so `currentProfit` hoặc `usedWeight` riêng lẻ **không đủ** nếu hai trạng thái còn những món khác nhau để lựa chọn.

Trong bài dùng `dfs(pos,usedWeight,profit)`, hai trạng thái ở **cùng `pos`** có cùng danh sách món còn lại. Nếu trạng thái A có `usedWeight_A\le usedWeight_B` và `profit_A\ge profit_B`, mọi tập món còn lại vừa với B đều vừa với A và tổng lợi nhuận của A không kém B. Bởi vậy, B bị thống trị đối với mục tiêu chỉ tìm **giá trị tối đa**. Đây có thể là một tối ưu bổ sung, nhưng chương trình Java ở trên **không** tự thực hiện memoization/thống trị để tránh trộn nhiều kỹ thuật khi đang chứng minh cận.

## 12. Cận đúng và cận sai trong một số bài toán khác

### 12.1. Bài tối thiểu hóa chi phí phân công

Giả sử có một số công việc còn chưa được gán và một số nhân viên còn trống. Mỗi công việc phải gán cho **một** nhân viên khác nhau, chi phí `c[task][worker]`.

Một **cận dưới đơn giản** cho phần chưa gán là:

\[
LB(s)=costSoFar+
\sum_{task\text{ còn lại}}
\min_{worker\text{ còn trống}}c[task][worker].
\]

Tại sao an toàn? Trong mọi cách hoàn thiện hợp lệ, mỗi công việc phải chọn **một nhân viên thuộc tập còn trống**, nên chi phí thực của công việc đó không nhỏ hơn giá trị min tương ứng. Cộng các bất đẳng thức cho từng công việc được cận dưới.

Cách nới lỏng đã **bỏ qua xung đột** khi nhiều công việc cùng chọn một nhân viên làm min. Nó có thể cho kết quả quá thấp nhưng vẫn là cận dưới an toàn.

Nếu incumbent là một phân công hợp lệ chi phí `20` và `LB(s)=23`, không có hoàn thiện nào rẻ hơn `20`, nên có thể cắt. Nếu `LB(s)=15`, nhánh vẫn có thể chứa lời giải tốt hơn; không được loại chỉ vì “thử vài cách đều đắt”.

### 12.2. Traveling Salesperson Problem (TSP)

Với TSP tối thiểu hóa chi phí hành trình, nhiều cách cận dưới dựa trên việc **nới lỏng ràng buộc** (ví dụ các cấu trúc cây khung/1-tree thích hợp) rồi chứng minh chi phí nới lỏng không lớn hơn chi phí mọi chu trình Hamilton hợp lệ. Không thể lấy tùy tiện **chi phí một chu trình đã tìm** làm cận dưới; đó là **cận trên khả thi** cho bài minimization.

Nếu đồ thị có trọng số âm, bất đối xứng hoặc thiếu cạnh, công thức cận và chứng minh phải phù hợp với **đúng phiên bản TSP**. Không áp dụng máy móc một công thức thiết kế cho TSP đối xứng đầy đủ.

### 12.3. Max clique và tô màu

Trong bài tìm clique lớn nhất, một cận trên có thể suy ra từ một phép tô màu hợp lệ của đồ thị con ứng viên: kích thước clique không thể vượt **số màu** của một cách tô hợp lệ. Nhưng phải chứng minh phép tô dùng đúng đồ thị và mọi cạnh của clique buộc hai đỉnh khác màu.

Một thuật toán tham lam **tìm được clique** chỉ đưa ra **cận dưới** cho bài tìm max clique; không được dùng kích thước clique tham lam làm **cận trên** để cắt nhánh.

Ví dụ này lặp lại cùng nguyên tắc: **giải một bài nới lỏng bao trùm các lựa chọn còn lại** hoặc chứng minh một bất đẳng thức áp dụng cho **tất cả hoàn thiện**.

## 13. Các lỗi làm thuật toán cắt mất nghiệm tối ưu

| Lỗi | Vì sao nguy hiểm | Cách khắc phục |
|---|---|---|
| Dùng nghiệm heuristic làm `UB` cho bài max | Heuristic 0/1 thường là **cận dưới**, có thể thấp hơn tối ưu | Tính cận trên từ bài nới lỏng hoặc bất đẳng thức đúng |
| Dùng nghiệm khả thi làm `LB` cho bài min | Nghiệm đó thường là **cận trên**, không phải cận dưới | Chứng minh `LB\le` mọi hoàn thiện |
| Cập nhật incumbent bằng nghiệm nới lỏng | Incumbent có thể không khả thi, làm cắt sai | Chỉ cập nhật từ nghiệm gốc hoàn chỉnh, hợp lệ |
| Dùng cận phụ thuộc vào một nhánh con để kết luận về toàn bộ nút cha | Các nhánh khác có thể tốt hơn | Cận nút cha phải bao phủ **mọi** nhánh con |
| Dùng `double` sai chính xác ở biên cắt | Cận có thể bị đánh giá thiếu | Dùng số học chính xác hoặc cách làm tròn có chứng minh |
| Nhân chéo hai số `long` trực tiếp khi so tỷ lệ | Có thể tràn, dẫn tới sắp tỷ lệ sai | Dùng `BigInteger` cho tích |
| Quên quy tắc dấu `max/min` | Cắt ngược chiều | Max cắt khi `UB<=I`; min cắt khi `LB>=I` |
| Chỉ cần một nghiệm nhưng lại tưởng cắt dấu bằng là sai | Dấu bằng **được phép** khi chỉ quan tâm giá trị | Chốt rõ yêu cầu đầu ra |
| Cần **mọi nghiệm tối ưu** nhưng vẫn cắt dấu bằng | Bỏ các nghiệm khác đạt cùng giá trị | Dùng cận nghiêm ngặt hoặc chứng minh cách đếm/khai triển |
| Có tiêu chí phụ nhưng chỉ dùng cận lợi nhuận | Có thể bỏ nghiệm hòa tốt hơn ở tiêu chí phụ | Xây cận theo thứ tự mục tiêu đầy đủ |
| Quên hoàn tác `chosen[]` khi quay lui | Quyết định nhánh cũ rò sang nhánh mới | Đặt lại trạng thái sau đệ quy |
| Sắp món rồi trả chỉ số theo thứ tự mới | Trả sai danh tính phần tử | Lưu `originalIndex` |
| Bỏ nhánh chọn vì quá sức chứa nhưng bài có phép giảm trọng lượng sau này | Lập luận bất khả thi không còn đúng | Xác định mọi thao tác có thể thực hiện trong tương lai |
| Tính cận bằng cách chỉ xét vài lựa chọn “có vẻ tốt” | Có thể **đánh giá thấp** max thật của nhánh | Dùng cận chứng minh được cho tất cả hoàn thiện |
| Bị lỗi `long` khi cộng lợi nhuận | Incumbent hoặc cận biến thành số âm giả | Dùng `BigInteger` hoặc phép cộng kiểm tra tràn |
| Chỉ so lời giải cuối trên vài input | Có thể chưa gặp nhánh bị cắt sai | Sinh ca ngẫu nhiên, kiểm tra theo nút và phản ví dụ |
| Coi “đã qua test” là một chứng minh | Kiểm thử hữu hạn không bao quát mọi input | Chứng minh tính đúng của cận và phân nhánh |
| Chỉ đếm số nút ít đi rồi tuyên bố tối ưu chính xác | Chạy nhanh không có nghĩa đúng | Đối chiếu với vét cạn/baseline và chứng minh cận |
| Bài có ràng buộc phụ nhưng dùng cận của bài khác | Không còn chắc tập nghiệm gốc nằm trong bài nới lỏng | Xác định rõ phép nới lỏng và kiểm tra bao hàm |

## 14. Kiểm thử đối chứng và tìm phản ví dụ một cách có hệ thống

### 14.1. Lời giải gốc độc lập

Với `n` nhỏ (ví dụ `n\le20`), duyệt tất cả `2^n` tập con theo bitmask. Một mask có bit `i` bật khi chọn món `i`. Tính:

\[
W(mask)=\sum_{i:\,bit_i(mask)=1}w_i,\qquad
V(mask)=\sum_{i:\,bit_i(mask)=1}v_i.
\]

Chỉ xem mask hợp lệ khi `W(mask)\le C`. Lấy max `V(mask)` trên những mask hợp lệ. Đây là một **oracle** không dùng cận, không sắp tỷ lệ và không dùng chung logic loại nhánh với B&B.

Đối chiếu:

- `B\&B.bestValue == bruteForce.bestValue`.
- Tập chỉ số của B&B không lặp và nằm trong miền `0..n-1`.
- Tổng trọng lượng của tập chỉ số không vượt sức chứa.
- Tổng lợi nhuận của các chỉ số bằng đúng `bestValue` được công bố.
- Nếu có phép cắt vì `UB\le I` ở một nút, ta có thể với dữ liệu rất nhỏ liệt kê mọi hoàn thiện từ nút đó để xác nhận **không hoàn thiện nào vượt `UB`**.

Lưu ý: không bắt buộc nghiệm được chọn bởi hai thuật toán giống nhau khi có nhiều nghiệm cùng lợi nhuận tối ưu. Khi cần một nghiệm, **giá trị tối ưu** và **tính hợp lệ của nghiệm** là hai điều kiện trọng tâm.

### 14.2. Những ca biên nên có

1. **Không có món:** nghiệm rỗng, lợi nhuận `0`.
2. **Sức chứa `0`:** khi mọi trọng lượng dương, chỉ nghiệm rỗng hợp lệ.
3. **Mọi món nặng hơn sức chứa:** đáp án `0`, không được tạo một nhánh chọn bất khả thi.
4. **Một món vừa đúng sức chứa:** phải được phép chọn vì `weight<=remaining`.
5. **Hai món cùng lợi nhuận tối ưu:** kiểm tra không hứa trả tất cả nghiệm.
6. **Nhiều món giá trị `0`:** incumbent ban đầu `0` đã đủ tối ưu nếu mọi lợi nhuận `0`.
7. **Nhiều món trùng tỷ lệ `v/w`:** bảo đảm so sánh hòa chính xác và sắp xếp không làm mất món.
8. **Lợi nhuận gần `Long.MAX_VALUE`:** tổng có thể vượt `long`; cận và kết quả phải không tràn.
9. **Trọng lượng bằng `0` hoặc âm:** bị từ chối theo hợp đồng ví dụ.
10. **Số lượng món tăng:** đánh giá tốc độ và số nút cắt, nhưng không dùng benchmark thay chứng minh.

### 14.3. Test ngẫu nhiên có thể tái hiện

Dùng seed cố định để tạo hàng trăm bộ:

```text
n ngẫu nhiên trong [0,10]
weight[i] trong [1,9]
value[i] trong [0,18]
capacity trong [0,29]
```

Với mỗi bộ, chạy B&B và vét cạn, kiểm tra bằng nhau cùng tính hợp lệ của witness. Khi có lệch:

1. In mảng trọng lượng, lợi nhuận, sức chứa và seed/trial.
2. Tìm nút đầu tiên bị cắt mà một hoàn thiện của nó đạt giá trị lớn hơn cận.
3. Kiểm tra lại thứ tự sắp, phép nhân chéo, cận phân số và điều kiện `UB\le I`.
4. Thu nhỏ số món và độ lớn các giá trị, giữ nguyên lỗi.
5. Biến phản ví dụ thành test cố định để chạy lại mỗi lần sửa.

**Phản ví dụ greedy 0/1 ở phần 7** là một regression test đặc biệt tốt: nó bắt lỗi nhầm **nghiệm khả thi** thành **cận trên**.

## 15. Độ phức tạp và những giới hạn thực tế

Với `n` món:

- Sắp tỷ lệ dùng `O(n\log n)` phép so sánh, trong đó phép nhân `BigInteger` có chi phí phụ thuộc độ dài số; không được mặc nhiên coi số học chính xác trên số tùy ý lớn là miễn phí.
- Mỗi nút tính cận bằng cách quét tối đa `O(n)` món còn lại và thực hiện các phép tính số học.
- Số nút cây nhị phân ở trường hợp xấu có thể tăng theo **`O(2^n)`**; do đó một chặn đơn giản cho thời gian là **`O(n2^n)`** phép xử lý mức từ/số học (chưa tính chi phí số lớn). Branch and Bound **không bảo đảm đa thức trong trường hợp tổng quát**.
- Ngăn xếp đệ quy sâu tối đa `n`, `chosen[]`, `items[]`, danh sách nghiệm tốt nhất cần **`O(n)`** chỗ lưu cấu trúc, cộng các đối tượng `BigInteger` tạm và biểu diễn giá trị.
- Hàm oracle vét cạn cần tới `2^n` mask và `O(n2^n)` công việc trong cách tính trực tiếp; chỉ nên dùng cho `n` nhỏ.
- Incumbent tốt sớm và cận chặt giúp **thực nghiệm** cắt nhiều nhánh, nhưng **thứ tự duyệt không thay tính đúng** nếu bất biến và cận giữ nguyên.

### Có thể cải tiến thêm như thế nào?

- **Tìm nghiệm khả thi tốt sớm** bằng heuristic greedy hoặc local search rồi đặt làm incumbent. Mọi nghiệm dùng để khởi tạo incumbent phải **thực sự khả thi**.
- **Tính cận chặt hơn** bằng bài nới lỏng tốt hơn, nhưng phải chứng minh nó vẫn là cận đúng hướng.
- **Sắp thứ tự nhánh** để ưu tiên nhánh hứa hẹn, tăng cơ hội có incumbent tốt sớm.
- **Memoization/thống trị** nếu có thể mô tả các trạng thái tương đương/tốt hơn và chứng minh an toàn.
- **Best-first search** ưu tiên nút có cận hứa hẹn nhất, thay DFS; cần quản lý hàng đợi ưu tiên và bộ nhớ.
- **Giới hạn thời gian** có thể trả incumbent hiện tại kèm cận toàn cục của các nút chưa xét, nhưng không được gọi là tối ưu tuyệt đối nếu chưa chứng minh khoảng cách tối ưu đã bằng `0`.

Trong thực tế, một kết quả “đã tìm được nghiệm lợi nhuận `100`, cận trên toàn cục còn lại `115`” là một **nghiệm khả thi với khoảng cách chưa chứng minh bằng 0**, không phải chứng nhận tối ưu.

## 16. Bài tập tự luyện

**Bài 1 — Phân biệt hướng cận.** Trong bài tối đa hóa, incumbent lợi nhuận `20`, một nút có cận trên `18`. Có thể cắt không? Nếu cận trên `23` thì sao?

*Đáp án:* cắt khi `UB=18` vì mọi hoàn thiện `\le18<20`. Khi `UB=23`, chưa thể kết luận nhánh không cải thiện incumbent.

**Bài 2 — Bài tối thiểu hóa.** Incumbent chi phí `15`. Một nút có `LB=18`, nút khác `LB=9`. Nút nào có thể cắt bằng cận?

*Đáp án:* nút `LB=18` cắt được; nút `LB=9` còn có thể có nghiệm rẻ hơn `15`.

**Bài 3 — Dấu bằng.** Với bài max, incumbent `10` và `UB(s)=10`. Có thể cắt khi chỉ cần một nghiệm tối ưu không? Có thể cắt nếu đề yêu cầu **đếm mọi nghiệm tối ưu** không?

*Đáp án:* có thể cắt trong mục tiêu thứ nhất; không được cắt chỉ vì dấu bằng khi cần đếm mọi nghiệm tối ưu, trừ khi có cách đếm bù/đối xứng đã được chứng minh riêng.

**Bài 4 — Nới lỏng.** Vì sao bài balo phân số cho cận trên cho bài balo 0/1 tối đa hóa?

*Đáp án:* mỗi lựa chọn nguyên `0/1` là một lựa chọn phân số hợp lệ; bài phân số có tập nghiệm rộng hơn, nên tối ưu phân số không thể nhỏ hơn tối ưu 0/1.

**Bài 5 — Tính cận gốc.** Với `weight=[2,3,4,5]`, `value=[3,4,5,8]`, `C=8`, tính cận trên phân số tại gốc và nghiệm nguyên tối ưu.

*Đáp án:* phân số đạt `12+1/3`, cận nguyên làm tròn lên `13`. Nghiệm nguyên tốt nhất chọn chỉ số `[1,3]`, lợi nhuận `12`, trọng lượng `8`.

**Bài 6 — Phản ví dụ heuristic.** Với món A `(weight=2,value=6)`, B `(weight=3,value=7)`, `C=3`, tham lam nguyên theo tỷ lệ cho lợi nhuận nào? Đó là cận trên hay cận dưới?

*Đáp án:* tham lam nguyên đạt `6`, trong khi tối ưu đạt `7`. `6` là giá trị của một nghiệm khả thi, tức **cận dưới** của bài max, không phải cận trên.

**Bài 7 — Tính khả thi.** Vì sao khi một món nặng hơn sức chứa còn lại, có thể không mở nhánh “chọn” trong bài toán của chương trình?

*Đáp án:* tất cả trọng lượng đều dương và các món đã chọn không được bỏ đi trong phần còn lại, nên tổng trọng lượng không thể giảm; mọi hoàn thiện của nhánh chọn đều vượt sức chứa.

**Bài 8 — Mục tiêu phụ.** Nếu đề muốn lợi nhuận lớn nhất rồi trọng lượng nhỏ nhất, vì sao cắt ở `UB=incumbentProfit` có thể sai?

*Đáp án:* nút có thể chứa nghiệm hòa về lợi nhuận nhưng nhẹ hơn nghiệm đang giữ. Phải giữ các khả năng hòa hoặc bổ sung cận/so sánh cho tiêu chí phụ.

**Bài 9 — Trọng lượng bằng 0.** Tại sao mã mẫu từ chối `weight=0`? Làm thế nào để mở rộng cho món có trọng lượng `0` và lợi nhuận dương?

*Gợi ý:* tỷ lệ `value/weight` không xác định. Có thể tách những món `weight=0,value>0`, luôn chọn chúng vì tăng lợi nhuận mà không tốn sức chứa trong bài không có ràng buộc phụ, rồi giải phần còn lại; cần lưu chỉ số và kiểm tra khi tính lợi nhuận.

**Bài 10 — Tự kiểm thử cận.** Với `n\le8`, tại một nút bất kỳ hãy liệt kê mọi tập con của phần món chưa xét, chỉ lấy những hoàn thiện vừa sức chứa. Kiểm tra giá trị lớn nhất trong các hoàn thiện có vượt `fractionalUpperBound` không.

*Đáp án mong đợi:* không; nếu có, cận đã đánh giá thiếu và quy tắc cắt không an toàn. Đừng chỉ so kết quả cuối của toàn thuật toán.

**Bài 11 — Tự viết bản minimization.** Xây bài phân công công việc cho `n\le8`, cận dưới là tổng min chi phí riêng của từng công việc chưa gán trên các nhân viên còn trống. Chứng minh cận an toàn, rồi đối chiếu với vét cạn mọi hoán vị nhân viên.

*Gợi ý:* mỗi chi phí thực của một công việc không nhỏ hơn min riêng của công việc đó; việc nhiều công việc cùng chọn một nhân viên trong bài nới lỏng chỉ có thể làm cận thấp hơn, không làm cận cao hơn tối ưu thật.

## 17. Checklist trước khi công nhận một phép cắt nhánh

Trước khi đưa một điều kiện cắt vào code, hãy tự trả lời bằng một mệnh đề rõ ràng:

1. **Nghiệm còn lại là gì?** Tập `\mathcal F(s)` chứa chính xác những hoàn thiện nào?
2. **Incumbent có khả thi không?** Điểm hiện tại đã tương ứng một nghiệm đầy đủ, đáp ứng tất cả ràng buộc chưa?
3. **Cận đúng hướng không?** Max cần `UB\ge` mọi hoàn thiện; min cần `LB\le` mọi hoàn thiện.
4. **Cận có bao phủ mọi lựa chọn chưa quyết định không?** Có bỏ sót một loại phương án trong lúc ước lượng?
5. **Có chứng minh phép nới lỏng không?** Mọi nghiệm gốc có nằm trong miền nghiệm nới lỏng?
6. **Số học có an toàn không?** Tràn số, chia nguyên và làm tròn có thể đánh giá cận thiếu?
7. **Dấu so sánh có đúng mục tiêu không?** Giá trị tối ưu hay tất cả nghiệm tối ưu? Có tiêu chí phá hòa?
8. **Phân nhánh có đầy đủ không?** Mọi nghiệm hợp lệ có đường đi tương ứng? Cắt do bất khả thi có thực sự bất khả thi?
9. **Trạng thái có ràng buộc phụ không?** Thời gian, số món chính xác, nhãn, thứ tự, chi phí âm có phá bất đẳng thức?
10. **Đã có đối chứng độc lập chưa?** Brute force/baseline trên ca nhỏ, các ca biên, phản ví dụ và seed tái lập.

Chỉ khi các điều kiện về **bất biến, cận và phân nhánh** được chứng minh, ta mới có thể nói cắt nhánh “không loại bỏ lời giải tối ưu” theo nghĩa **giữ nguyên giá trị tối ưu**.

## Ghi nhớ

Trong **nhánh và cận**, muốn chứng minh một nút có thể bị bỏ mà không ảnh hưởng kết quả, cần ba mắt xích:

\[
\boxed{\text{Incumbent khả thi}\quad+\quad
\text{Cận đúng cho mọi hoàn thiện}\quad+\quad
\text{Phân nhánh đầy đủ}.}
\]

Với bài **max**, cắt khi `UB(s)\le incumbent`; với bài **min**, cắt khi `LB(s)\ge incumbent`, miễn chỉ cần **một nghiệm tối ưu**. Nếu phải đếm/liệt kê mọi nghiệm tối ưu hoặc tối ưu thêm tiêu chí phụ, phải xử lý trường hợp hòa cẩn thận.

**Cận trên** của balo max có thể lấy từ **balo phân số**, vì nó nới lỏng ràng buộc nguyên. Ngược lại, một nghiệm balo 0/1 tìm được bằng tham lam chỉ là **cận dưới khả thi**, không được gọi là cận trên. Mã Java sử dụng `BigInteger` và phép làm tròn lên chính xác để cận không bị tính thiếu do tràn hoặc số thực.

**Cắt một nhánh chứa nghiệm tối ưu chỉ an toàn nếu đã có một nghiệm tối ưu khác đạt ít nhất cùng giá trị.** Bất đẳng thức cận chứng minh chính điều đó; kiểm thử đối chứng với lời giải gốc giúp xác nhận mã đã thực hiện đúng chứng minh.
