# Lời giải khả thi hiện có và cận cho nhánh chưa xét

## Mục tiêu học tập

Trong **nhánh và cận** (*branch and bound*), ta không cố liệt kê đến tận cùng mọi lời giải có thể có. Thay vào đó, thuật toán duy trì một **lời giải đầy đủ đã biết là hợp lệ**, gọi là **incumbent** (nghiệm tốt nhất hiện có), và tính một **cận toán học** cho mỗi nhánh chưa xét hết. Nếu cận chứng minh rằng **không lời giải nào trong nhánh ấy có thể tốt hơn incumbent**, ta loại cả nhánh mà vẫn giữ được tính tối ưu.

Đây là kỹ thuật đặc biệt hữu ích cho các bài toán tối ưu tổ hợp như **ba lô 0/1, người du lịch (TSP), phân công công việc, lập lịch và chọn tập con có ràng buộc**.

Sau bài này, bạn có thể:

1. Phân biệt **nghiệm khả thi**, **incumbent**, **trạng thái/nhánh chưa xét**, **cận dưới**, **cận trên** và **cận tối ưu toàn cục**.
2. Chọn đúng chiều so sánh khi **cực tiểu hóa** hoặc **cực đại hóa** và chứng minh điều kiện cắt nhánh an toàn.
3. Khởi tạo một incumbent hợp lệ, cập nhật incumbent khi gặp nghiệm tốt hơn và hiểu vì sao một nghiệm tham lam **không cần tối ưu** vẫn có ích.
4. Thiết kế cận **lạc quan nhưng phải đúng chiều** bằng cách bỏ bớt ràng buộc (relaxation), đặc biệt cận **ba lô phân số** cho ba lô 0/1.
5. Cài đặt branch-and-bound bằng DFS với trạng thái **đã quyết định**, **số tài nguyên đã dùng**, **giá trị tích lũy**, cận của phần chưa quyết định và thao tác hoàn tác.
6. Hiểu tính đúng, trường hợp không có nghiệm khả thi, nhiều nghiệm đồng hạng, sai số số thực và điều kiện dừng.
7. Phân tích vì sao worst-case vẫn **theo hàm mũ**, dù cắt nhánh có thể giảm lượng tìm kiếm đáng kể.
8. Chạy một chương trình **Java 17+** đầy đủ, khôi phục tập phần tử tối ưu, kiểm tra chi phí và đọc thống kê số nút đã xét/bị cắt.
9. Tự thiết kế các bộ kiểm thử và tránh những cắt nhánh “có vẻ hợp lý” nhưng làm mất nghiệm tối ưu.

---

## 1. Nhánh và cận giải quyết vấn đề gì?

Một bài toán tối ưu tổ hợp thường có rất nhiều lựa chọn rời rạc. Ví dụ có n món hàng, mỗi món chỉ được **lấy hoặc không lấy**, thì có `2^n` tập con. Nếu mục tiêu là tìm tập có tổng giá trị lớn nhất trong giới hạn khối lượng, việc thử hết các tập con mất thời gian theo hàm mũ.

Một hướng đơn giản là **quay lui**:

```text
choose  -> chọn một quyết định
explore -> thử các lựa chọn kế tiếp
undo    -> hoàn tác để thử nhánh khác
```

Nhánh và cận bổ sung hai thông tin quyết định:

- **Nghiệm khả thi tốt nhất hiện có:** cho biết ngưỡng chất lượng cần vượt qua.
- **Cận của mỗi nhánh chưa xét hết:** cho biết **giới hạn tốt nhất mà nhánh đó còn có thể đạt**.

Nhờ vậy, ta tránh đi sâu vào những nhánh được **chứng minh chắc chắn** là không thể cải thiện nghiệm hiện có.

### 1.1. Ba loại thông tin khác nhau

Giả sử cần **cực đại hóa** tổng lợi ích.

1. Một tập đã chọn có giá trị 50 và thỏa mọi ràng buộc là **nghiệm khả thi**. Vì nó thực sự đạt giá trị 50, tối ưu toàn cục phải **ít nhất là 50**.
2. Một nhánh mới có **cận trên 46** nghĩa là mọi cách hoàn tất nhánh ấy đều có giá trị **không vượt quá 46**. Nhánh này không thể tốt hơn nghiệm 50; có thể cắt.
3. Một nhánh khác có **cận trên 70** có thể chứa nghiệm tốt hơn 50, nhưng không bảo đảm sẽ tìm được nghiệm 70; nhánh ấy vẫn cần được xét hoặc được chứng minh vô ích theo cách khác.

**Incumbent là nghiệm thực, cận là phát biểu về khả năng.** Không được dùng một giá trị cận lạc quan như thể đã có một lời giải đạt đúng giá trị đó.

### 1.2. Một sai lầm mang tính bản chất

Một nhánh được ước lượng sẽ đem lại **tối đa khoảng 46** nhưng con số ấy chỉ là **dự đoán thống kê**, chưa phải **cận trên được chứng minh**, thì cắt nhánh khi incumbent=50 có thể làm mất nghiệm đạt 80.

Kỹ thuật này chỉ **bảo đảm tối ưu** khi cận thực sự đúng đối với **mọi lời giải hợp lệ có thể hoàn tất từ nhánh**.

---

## 2. Nghiệm khả thi và incumbent là gì?

**Nghiệm khả thi** (*feasible solution*) là một **lời giải hoàn chỉnh** thỏa tất cả điều kiện của bài toán.

Ví dụ ba lô có sức chứa 8:

```text
Món A: khối lượng 2, giá trị 3
Món B: khối lượng 3, giá trị 4
Món C: khối lượng 4, giá trị 5
Món D: khối lượng 5, giá trị 8
```

Một tập `{A,D}` có khối lượng `2+5=7≤8` và giá trị `3+8=11` nên là **nghiệm khả thi**. Tập `{B,D}` có khối lượng `3+5=8` và giá trị `4+8=12` cũng khả thi, và tốt hơn nếu mục tiêu là cực đại hóa giá trị.

**Incumbent** là nghiệm khả thi **tốt nhất mà thuật toán đã tìm được cho tới thời điểm hiện tại**. Nó gồm ít nhất hai phần:

- **Giá trị mục tiêu** hiện tốt nhất, ví dụ 11 rồi được cập nhật thành 12.
- **Dữ liệu của lời giải thật** đạt giá trị đó: những món nào được chọn, đường đi nào được dùng, lịch công việc nào đã xếp, v.v.

Trong một triển khai chỉ hỏi giá trị tối ưu, có thể chỉ lưu giá trị; nhưng nếu cần trả lời giải cụ thể, phải lưu trạng thái/chỉ số tương ứng.

### 2.1. Tính đơn điệu của incumbent

- Với **cực tiểu hóa**, giá trị incumbent chỉ có thể **giảm** khi tìm được nghiệm khả thi tốt hơn.
- Với **cực đại hóa**, giá trị incumbent chỉ có thể **tăng**.

Đây là bất biến quan trọng: thuật toán không bao giờ được **thay incumbent bằng một nghiệm kém hơn**.

### 2.2. Khởi tạo incumbent bằng cách nào?

Có ba cách quen thuộc:

1. **Dùng nghiệm tầm thường luôn hợp lệ.** Trong ba lô 0/1 với khối lượng dương, giới hạn không âm và được phép không lấy gì, tập rỗng là nghiệm khả thi có giá trị 0.
2. **Dùng một heuristic/greedy để tìm nghiệm đầy đủ hợp lệ.** Nghiệm này không cần tối ưu; chỉ cần **đúng ràng buộc**. Nghiệm càng tốt, càng nhiều nhánh có thể được cắt sớm.
3. **Chưa có nghiệm khả thi.** Khi đó, đối với bài cực tiểu có thể dùng sentinel `+∞`, còn đối với bài cực đại dùng `−∞`, nhưng phải kèm **cờ chưa có nghiệm** và không được giả rằng sentinel là giá trị của một lời giải thật.

Ví dụ trong TSP có cạnh thiếu, có thể không tồn tại chu trình Hamilton nào. Không thể tự nhận “tour hiện có chi phí 0” là incumbent khi thực tế tour ấy không hợp lệ.

### 2.3. Vì sao một nghiệm tham lam chưa tối ưu vẫn hữu ích?

Với ba lô ở trên, một heuristic sắp các món theo tỷ số `giá trị/khối lượng` rồi chọn món vừa sức có thể tìm `{D,A}`, giá trị **11**.

Nghiệm ấy là **khả thi**, dù tối ưu là **12**. Nhờ biết chắc đã đạt 11, ta được quyền loại mọi nhánh có cận trên `≤11`. Khi sau đó tìm được nghiệm 12, ngưỡng cắt trở nên mạnh hơn: mọi nhánh có cận trên `≤12` có thể bị bỏ qua nếu chỉ cần **một** nghiệm tối ưu.

**Vai trò của heuristic:** cung cấp **incumbent tốt**, không cung cấp chứng minh tối ưu. **Vai trò của cận:** chứng minh nhánh không thể đánh bại incumbent, không tự xây ra nghiệm.

---

## 3. Cận dưới và cận trên: phải chọn đúng chiều

Gọi `F(N)` là tập các lời giải đầy đủ **khả thi** có thể hoàn tất từ trạng thái/nút N.

Với mục tiêu `f(x)`:

### 3.1. Bài toán cực tiểu (minimization)

Một **cận dưới hợp lệ** `LB(N)` phải thỏa:

\[
LB(N)\le f(x)\quad\text{với mọi }x\in F(N).
\]

Nếu incumbent hiện có giá trị `U` — đây là một **cận trên toàn cục** của giá trị tối ưu do đã có nghiệm khả thi — thì:

\[
\boxed{LB(N)\ge U\ \Longrightarrow\ \text{có thể cắt N}.}
\]

Vì mọi nghiệm trong N có chi phí `≥LB(N)≥U`, không nghiệm nào có **chi phí thấp hơn U**.

Ví dụ đang giải TSP cực tiểu:

- Đã có một tour hợp lệ chi phí **80** → incumbent=80.
- Một nhánh chưa xét có cận dưới đã chứng minh **84** → không thể tạo tour chi phí nhỏ hơn 84 → cắt.
- Một nhánh khác có cận dưới **65** → **chưa đủ thông tin để cắt**, dù thực tế nhánh đó có thể chỉ chứa những tour rất đắt.

### 3.2. Bài toán cực đại (maximization)

Một **cận trên hợp lệ** `UB(N)` phải thỏa:

\[
f(x)\le UB(N)\quad\text{với mọi }x\in F(N).
\]

Nếu incumbent có giá trị `L` — một **cận dưới toàn cục** của giá trị tối ưu — thì:

\[
\boxed{UB(N)\le L\ \Longrightarrow\ \text{có thể cắt N}.}
\]

Vì mọi nghiệm trong N có giá trị `≤UB(N)≤L`, không nghiệm nào vượt qua giá trị tốt nhất đã biết.

Ví dụ ba lô:

- Incumbent=11.
- Nhánh có cận trên 10 → cắt.
- Nhánh có cận trên 13 → chưa thể cắt; tối đa **có thể** đạt 13, nhưng có thể thực tế chỉ đạt 11 hoặc 12.

### 3.3. Bảng ghi nhớ

| Tiêu chí | Cực tiểu | Cực đại |
| --- | --- | --- |
| Giá trị incumbent | Giá trị của nghiệm khả thi **nhỏ nhất** đã biết | Giá trị của nghiệm khả thi **lớn nhất** đã biết |
| Cận cần cho một nhánh | **Cận dưới** `LB(N)` | **Cận trên** `UB(N)` |
| Nhánh còn cơ hội cải thiện khi | `LB(N)<incumbent` | `UB(N)>incumbent` |
| Đủ điều kiện cắt (chỉ cần một nghiệm tối ưu) | `LB(N)≥incumbent` | `UB(N)≤incumbent` |
| Khi incumbent cải thiện | Giảm | Tăng |
| Giá trị cực trị toàn cục được incumbent chặn | `OPT≤incumbent` | `OPT≥incumbent` |

**Chú ý với dấu bằng:** nếu chỉ cần **giá trị tối ưu và một nghiệm tối ưu**, ta có thể cắt khi bằng nhau vì nhánh chỉ có thể **hòa**, không thể cải thiện. Nếu bài yêu cầu **liệt kê mọi nghiệm tối ưu** hoặc tối ưu thêm một tiêu chí phụ, cắt tất cả nhánh hòa có thể làm **mất các nghiệm cần trả**. Khi đó phải điều chỉnh điều kiện cắt và cách so sánh.

---

## 4. Mô hình nhánh và cận: search tree và trạng thái

Một nút N trong cây tìm kiếm biểu diễn **tập các quyết định đã cố định**, ví dụ:

```text
Nút gốc: chưa quyết định món nào.

Nhánh trái: lấy món A.
Nhánh phải: không lấy món A.

Ở mỗi nhánh lại quyết định món B, rồi C, rồi D.
```

Mỗi nút có thể lưu:

- **Quyết định đã chọn hoặc đã loại.**
- **Mức sâu/index:** số món hoặc công việc đã được quyết định.
- **Chi phí/lợi ích đã tích lũy.**
- **Tài nguyên đã dùng:** khối lượng ba lô, thời gian, số vị trí công việc, v.v.
- **Trạng thái có còn khả thi không?**
- **Cận lạc quan:** tối đa hoặc tối thiểu có thể đạt trong mọi phần tiếp nối.
- **Thông tin truy vết:** để khôi phục một nghiệm thực sự.

### 4.1. Ba lý do cắt nhánh khác nhau

**A. Không khả thi:** nhánh đã vi phạm một điều kiện **không thể sửa bằng các quyết định còn lại**. Ví dụ ba lô 0/1 chỉ có khối lượng dương, tổng khối lượng đã lấy vượt sức chứa; dù chọn/không chọn các món sau, tổng khối lượng không thể giảm.

**B. Bị incumbent đánh bại bởi cận:** nhánh còn có thể hợp lệ, nhưng **ngay cả trường hợp tốt nhất có thể** cũng không thắng được nghiệm đã biết.

**C. Bị trội bởi trạng thái khác:** nếu hai trạng thái có cùng khả năng tiếp nối và một trạng thái đã có chi phí/lợi ích kém hơn, có thể bỏ trạng thái bị trội; điều này đòi hỏi **chứng minh tính tương đương của thông tin tương lai**.

Bài này tập trung vào **B**, đồng thời phân biệt với **A** và **C** để tránh trộn lẫn các lý do cắt.

### 4.2. Có thể cắt ngay tại nút, không phải chờ đến lá

Nếu nút N có cận không thể thắng incumbent, **toàn bộ cây con** bên dưới N bị bỏ qua. Thuật toán không cần sinh các con và cháu để rồi loại từng nghiệm một.

Đây là lợi ích lớn của branch-and-bound so với việc chỉ kiểm tra tính hợp lệ sau khi sinh đủ lời giải.

---

## 5. Khung giả mã chung

Một skeleton cho bài **cực tiểu**:

```text
bestFound = false
incumbent = +INF

nếu tìm được nghiệm khả thi S0:
    bestFound = true
    incumbent = objective(S0)
    bestSolution = S0

SEARCH(node):
    if node chắc chắn không thể hoàn tất thành nghiệm hợp lệ:
        return

    lower = VALID_LOWER_BOUND(node)

    if bestFound and lower >= incumbent:
        return    // Cắt bằng cận; không thể cải thiện

    if node là một nghiệm đầy đủ:
        if !bestFound or objective(node) < incumbent:
            bestFound = true
            incumbent = objective(node)
            bestSolution = snapshot(node)
        return

    for mỗi quyết định tiếp theo hợp lệ:
        APPLY(decision)
        SEARCH(child)
        UNDO(decision)
```

Đối với **cực đại**, đổi:

- `incumbent=-INF` khi chưa có nghiệm.
- Dùng `upper=VALID_UPPER_BOUND(node)`.
- Cắt khi `upper<=incumbent`.
- Cập nhật khi giá trị nghiệm **lớn hơn** incumbent.

### 5.1. Thứ tự các thao tác

Một thứ tự thường hợp lý:

1. Kiểm tra trạng thái có **bất khả thi chắc chắn** không.
2. Tính **cận** của nhánh.
3. Nếu đã có incumbent và cận không thể cải thiện, **cắt**.
4. Nếu tới lá/nghiệm hoàn chỉnh, kiểm tra và **cập nhật incumbent**.
5. Nếu chưa tới lá, **phân nhánh** rồi đi tiếp.

Một số bài có thể cập nhật incumbent ngay ở **nút bên trong** nếu trạng thái đang có đã là một nghiệm hoàn chỉnh hợp lệ. Ví dụ ba lô 0/1: tập món đã chọn ở bất kỳ nút nào cũng có thể hoàn tất bằng cách **không chọn mọi món còn lại**, nên nó biểu diễn một nghiệm khả thi. Tuy nhiên, việc cập nhật sớm chỉ an toàn khi nghiệm phần này thực sự có thể được coi là **lời giải đầy đủ hợp lệ**, không được áp dụng máy móc cho TSP còn thiếu thành phố.

### 5.2. Không gán cận thành nghiệm

Dòng:

```text
incumbent = VALID_UPPER_BOUND(node)
```

**là sai cho cực đại** nếu chưa có một lời giải khả thi đạt giá trị cận ấy. Giá trị cận chỉ là **trần lý thuyết**; nó có thể dựa trên bài toán nới lỏng cho phép các lựa chọn không hợp lệ trong bài gốc.

Trong ba lô 0/1, cận có thể tính bằng cách lấy **một phần của một món**; nhưng nghiệm thật không được lấy lẻ món. Không được lưu phần giá trị lẻ ấy làm incumbent.

---

## 6. Thế nào là một cận hợp lệ và một cận mạnh?

Một **cận hợp lệ** (*valid bound*) là cận đúng chiều cho **mọi** cách hoàn tất nhánh. Một **cận mạnh** (*tight bound*) là cận gần với giá trị tốt nhất thực tế có thể đạt trong nhánh.

### 6.1. Cận lạc quan từ bài toán nới lỏng

Một cách thiết kế quan trọng là **relaxation**: bỏ bớt một số ràng buộc để nhận bài toán **dễ giải hơn**, có miền nghiệm **rộng hơn hoặc bằng** miền nghiệm gốc của nhánh.

- Với **cực tiểu**, cho phép thêm các lời giải có thể làm chi phí tốt nhất **nhỏ đi** → tối ưu của bài nới lỏng là **cận dưới**.
- Với **cực đại**, cho phép thêm các lời giải có thể làm lợi ích tốt nhất **lớn lên** → tối ưu của bài nới lỏng là **cận trên**.

Ví dụ cực đại ba lô 0/1: bài gốc chỉ được lấy **toàn bộ hoặc không lấy** mỗi món; bài toán nới lỏng cho phép lấy **một phần món**. Vì được phép nhiều lựa chọn hơn, giá trị tối ưu phân số **không thấp hơn** giá trị 0/1 tối ưu.

Đó là lý do dùng nghiệm **ba lô phân số** làm cận trên hợp lệ.

### 6.2. Cận quá lỏng vẫn đúng nhưng ít hiệu quả

Giả sử incumbent cực đại là 100:

- Nhánh thực ra đạt tốt nhất 80.
- Cận trên A = 1.000 → đúng nhưng **không cắt được**.
- Cận trên B = 105 → đúng, vẫn chưa cắt.
- Cận trên C = 98 → đúng và **cắt được**.

Không phải cận càng khó tính càng tốt. Một cận mạnh nhưng tính quá chậm trên mỗi nút có thể làm tổng thời gian tăng. Phải cân bằng **chi phí tính cận** với **số nút tiết kiệm được**.

### 6.3. Cận sai chiều là lỗi nghiêm trọng

Đối với cực tiểu, dùng một **chi phí tour được xây tham lam** làm “cận dưới cho nhánh” là sai: tour tham lam hợp lệ thường cho **cận trên**, vì nó chỉ chứng minh rằng ta có một cách làm chi phí ấy.

Đối với cực đại, một tập ba lô tham lam hợp lệ cũng cho **cận dưới của OPT**, không tự cho cận trên. Nếu cắt nhánh bằng những giá trị này như thể chúng là cận đối diện, có thể mất nghiệm tốt hơn.

---

## 7. Ví dụ cực đại: ba lô 0/1

Ta giải bài toán:

\[
\max \sum_{i=0}^{n-1}v_i x_i
\]

với ràng buộc:

\[
\sum_{i=0}^{n-1}w_i x_i\le C,\qquad x_i\in\{0,1\}.
\]

Giả thiết trong ví dụ:

- `w_i` là số nguyên **dương**.
- `v_i` là số nguyên **không âm**.
- `C≥0`.
- Mỗi món được lấy **tối đa một lần**.
- Tập rỗng hợp lệ, đạt giá trị 0.
- Nếu nhiều tập có cùng lợi ích tối ưu, chỉ cần **một** tập.

### 7.1. Dữ liệu minh họa

| Món | Chỉ số gốc | Khối lượng | Giá trị | Giá trị / khối lượng |
| --- | ---: | ---: | ---: | ---: |
| A | 0 | 2 | 3 | 1,5 |
| B | 1 | 3 | 4 | 1,333… |
| C | 2 | 4 | 5 | 1,25 |
| D | 3 | 5 | 8 | 1,6 |

Sức chứa:

\[
C=8.
\]

Một nghiệm khả thi là chọn D và A:

\[
w(D)+w(A)=5+2=7\le8,\qquad
v(D)+v(A)=8+3=11.
\]

Vậy incumbent có thể khởi tạo bằng **11** và tập `{D,A}`.

Nhưng tập `{D,B}`:

\[
w(D)+w(B)=5+3=8,\qquad
v(D)+v(B)=8+4=12,
\]

còn tốt hơn. Tối ưu thật là **12**; ví dụ sẽ dùng nhánh và cận để tìm và chứng minh điều này.

---

## 8. Cận trên bằng ba lô phân số

Giả sử ở một nút ta đã quyết định một số món: một vài món **được lấy**, một vài món **bị loại**. Chỉ các món **chưa quyết định** mới có thể được thêm.

Gọi:

- `currentWeight`: tổng khối lượng đã lấy.
- `currentValue`: tổng giá trị đã lấy.
- `remainingCapacity=C-currentWeight`.
- `R`: tập món chưa quyết định.

Nếu cho phép lấy **một phần** món trong R, lời giải phân số có thể tốt bằng hoặc tốt hơn lời giải 0/1. Giá trị tối ưu của bài phân số cộng với `currentValue` là một **cận trên hợp lệ**.

### 8.1. Vì sao sắp theo tỷ số giá trị/khối lượng?

Để giải bài **ba lô phân số**, sắp các món chưa quyết định theo tỷ số:

\[
\frac{v_i}{w_i}
\]

từ **cao xuống thấp**, lấy toàn bộ các món vừa sức, rồi nếu còn chút sức chứa thì lấy **một phần** của món tiếp theo. Với trọng số không âm và khối lượng dương, đây là thuật toán tối ưu của relaxation phân số.

**Điều quan trọng:** nếu chỉ lấy các món còn lại **theo một thứ tự tùy ý**, giá trị phân số tìm được có thể **thấp hơn** mức tối ưu của relaxation. Khi đó nó **không chắc** là cận trên của bài 0/1 và việc cắt nhánh có thể sai.

### 8.2. Cận trên ở nút gốc

Sắp các món theo tỷ số giảm:

```text
D: weight 5, value 8, ratio 1.6
A: weight 2, value 3, ratio 1.5
B: weight 3, value 4, ratio 1.333...
C: weight 4, value 5, ratio 1.25
```

Với sức chứa 8:

1. Lấy hết D: khối lượng 5, giá trị 8, còn sức chứa 3.
2. Lấy hết A: khối lượng 7, giá trị 11, còn sức chứa 1.
3. Chỉ còn 1 đơn vị sức chứa, lấy **1/3 của B**: giá trị thêm `4/3`.

Cận phân số:

\[
UB_{\mathrm{fractional}}=8+3+\frac43
=\frac{37}{3}\approx12.333\ldots
\]

Mọi nghiệm 0/1 có giá trị nguyên đều không vượt giá trị này. Vì vậy:

\[
OPT_{\mathrm{0/1}}\le12.333\ldots
\quad\Rightarrow\quad OPT_{\mathrm{0/1}}\le12.
\]

Trong chương trình Java, ta dùng **cận nguyên làm tròn lên của relaxation**:

\[
UB_{\mathrm{int}}=\lceil12.333\ldots\rceil=13.
\]

Nó **lỏng hơn** cận chính xác ở trên nhưng vẫn là **cận trên an toàn** vì đã làm tròn **lên**, không làm tròn xuống. Với incumbent=11, 13 vẫn lớn hơn 11 nên chưa được cắt nút gốc.

### 8.3. Vì sao cố tình làm tròn lên thay vì dùng double?

Trong lập trình, so sánh số thực gần ranh giới tối ưu có thể bị ảnh hưởng bởi sai số làm tròn. Nếu một cận trên bị làm tròn **xuống quá thấp**, thuật toán có thể cắt sai một nhánh chứa nghiệm tốt.

Với khối lượng và giá trị là số nguyên nhỏ/vừa, ta có thể tính **trần của đóng góp phân số** bằng số nguyên:

\[
\left\lceil\frac{r\cdot v}{w}\right\rceil
=
\left\lfloor\frac{r\cdot v+w-1}{w}\right\rfloor,
\]

trong đó r là sức chứa còn lại. Code Java dùng `long` cho tích `r·v` và kiểm tra miền input để phép tính không tràn. Đây là **ước lượng trên**, nên khi so với incumbent vẫn an toàn.

**Không làm tròn xuống** đóng góp phân số rồi gọi đó là cận trên: phép làm tròn xuống có thể cho con số **nhỏ hơn** giá trị tối ưu 0/1 ở một số tình huống hoặc khi ghép nhiều phép làm tròn sai cách. Muốn làm chặt hơn nữa có thể dùng số hữu tỷ chính xác hoặc áp dụng thêm tính nguyên của giá trị tối ưu với một phép chứng minh rõ ràng.

### 8.4. Cận phải tôn trọng các quyết định đã cố định

Tại một nút, những món đã **loại** không được xuất hiện lại trong relaxation; những món đã **lấy** phải được giữ trong `currentWeight` và `currentValue`. Chỉ phần **chưa quyết định** mới có thể bị lấy phân số.

Nếu tính cận bằng cách bỏ qua cả quyết định đã loại hoặc buộc lấy món khác không đúng, cận có thể trở nên quá lỏng hoặc **không còn bao phủ mọi nghiệm của nhánh**. Trong chương trình, sắp các món **một lần theo tỷ số giảm**, rồi quyết định từng món theo thứ tự ấy; phần còn lại của mảng là các món chưa quyết định.

---

## 9. Minh họa việc cập nhật incumbent và cắt nhánh

Nhắc lại:

- Sức chứa 8.
- Greedy tìm `{D,A}` có giá trị **11**, khối lượng **7**.
- Cận gốc theo relaxation là `13` (làm tròn lên).

DFS thử nhánh **lấy món** trước, rồi mới thử nhánh **bỏ món**.

### 9.1. Bắt đầu từ món D

Nhánh lấy D có:

```text
Đã lấy: D
Khối lượng: 5
Giá trị: 8
Món còn lại: A, B, C
Sức chứa còn: 3
```

Relaxation có thể lấy hết A (giá trị 3), rồi phân số B (giá trị 4/3):

\[
UB\le8+3+\left\lceil\frac{1\cdot4}{3}\right\rceil=13.
\]

Do `13>11`, chưa thể cắt; thuật toán tiếp tục tìm kiếm.

### 9.2. Nhánh lấy D rồi lấy A

Lúc này:

```text
Đã lấy: D,A
Khối lượng: 7
Giá trị: 11
Sức chứa còn: 1
```

Không thể lấy nguyên B hoặc C; các nhánh ấy không tạo nghiệm tốt hơn 11. Cận làm tròn lên của các nút trước khi quyết định hết có thể vẫn lỏng, nên code vẫn đi qua một vài trạng thái rồi mới cắt.

Điều này **không phải lỗi**: cận an toàn có thể chưa đủ chặt để cắt sớm nhất có thể.

### 9.3. Nhánh lấy D, bỏ A, lấy B

Bỏ A nhưng lấy B cho:

\[
w(D)+w(B)=5+3=8,\qquad v(D)+v(B)=8+4=12.
\]

DFS đến một nghiệm hoàn chỉnh với các món khác được bỏ. **Incumbent cập nhật từ 11 lên 12** và lưu tập `{B,D}` theo chỉ số gốc `[1,3]`.

Từ đây, mọi nhánh có **cận trên ≤12** đều có thể bị loại nếu chỉ cần một nghiệm tối ưu.

### 9.4. Kết quả của thuật toán minh họa

Với quy tắc sắp theo tỷ số, thử lấy trước, chỉ cập nhật khi **tốt hơn nghiêm ngặt**, và cận làm tròn lên bằng số nguyên:

```text
Nghiệm khởi tạo bằng greedy: giá trị 11
Giá trị tối ưu được tìm:   12
Khối lượng nghiệm tối ưu:  8
Chỉ số gốc được chọn:     [1, 3]
```

Ví dụ code bên dưới còn đếm **10 nút DFS đã ghé** và **3 nút được cắt do cận**. Đây là số đếm của **cách cài và thứ tự duyệt cụ thể**, không phải tính chất bất biến của mọi chương trình branch-and-bound giải cùng bộ dữ liệu.

---

## 10. Java 17+: branch-and-bound hoàn chỉnh cho ba lô 0/1

Chương trình đầy đủ có tên **`KnapsackBranchBoundDemo.java`**. Nó:

- Nhận hai mảng `weights` và `values`, cùng sức chứa `capacity`.
- Kiểm tra mảng không null, cùng độ dài, mỗi khối lượng dương, mỗi giá trị không âm, sức chứa không âm.
- Giới hạn n≤30 để **minh họa**, nhưng vẫn cảnh báo worst-case theo hàm mũ.
- Sắp món theo tỷ số lợi ích/khối lượng **giảm**, phá hòa bằng **chỉ số input ban đầu**.
- Khởi tạo incumbent bằng **một nghiệm tham lam khả thi**, không mặc định đó là nghiệm tối ưu.
- Dùng **cận trên của ba lô phân số**, tính bằng **số nguyên long và làm tròn lên**.
- Duyệt **nhánh lấy trước, nhánh bỏ sau**, lưu lựa chọn hiện thời và snapshot nghiệm tốt nhất.
- Trả giá trị tối ưu, khối lượng nghiệm, các **chỉ số input gốc**, cùng thống kê.

```java
import java.util.Arrays;
import java.util.Comparator;
import java.util.Objects;

public final class KnapsackBranchBoundDemo {

    private static final int MAX_ITEMS = 30;

    private record Item(int id, int weight, int value) {
    }

    public record Result(
            long bestValue,
            int totalWeight,
            int[] originalIndices,
            long greedyInitialValue,
            long visitedNodes,
            long prunedNodes) {
    }

    private final Item[] items;
    private final int capacity;
    private final boolean[] chosen;
    private final boolean[] bestChosen;

    private long bestValue = 0;
    private int bestWeight = 0;
    private long greedyInitialValue = 0;
    private long visitedNodes = 0;
    private long prunedNodes = 0;

    private KnapsackBranchBoundDemo(
            int[] weights, int[] values, int capacity) {

        Objects.requireNonNull(weights, "weights");
        Objects.requireNonNull(values, "values");

        if (weights.length != values.length) {
            throw new IllegalArgumentException(
                    "weights and values must have equal length");
        }
        if (capacity < 0) {
            throw new IllegalArgumentException(
                    "negative capacity");
        }
        if (weights.length > MAX_ITEMS) {
            throw new IllegalArgumentException(
                    "too many items for this demo");
        }

        int n = weights.length;
        items = new Item[n];

        for (int i = 0; i < n; i++) {
            if (weights[i] <= 0 || values[i] < 0) {
                throw new IllegalArgumentException(
                        "weights must be positive and values non-negative");
            }
            items[i] = new Item(i, weights[i], values[i]);
        }

        // Descending value / weight without floating-point error.
        // int * int fits in a signed long.
        Arrays.sort(items,
                Comparator.<Item>comparingLong(x -> 0)
                        .thenComparingInt(Item::id));

        Arrays.sort(items, (a, b) -> {
            long left = (long) a.value() * b.weight();
            long right = (long) b.value() * a.weight();

            // Higher ratio first.
            int cmp = Long.compare(right, left);
            return cmp != 0
                    ? cmp
                    : Integer.compare(a.id(), b.id());
        });

        chosen = new boolean[n];
        bestChosen = new boolean[n];

        initializeGreedyIncumbent();
    }

    // This is a feasible starting solution, NOT an optimality proof.
    private void initializeGreedyIncumbent() {
        int usedWeight = 0;
        long value = 0;

        for (int i = 0; i < items.length; i++) {
            Item item = items[i];

            if (item.weight() <= capacity - usedWeight) {
                bestChosen[i] = true;
                usedWeight += item.weight();
                value += item.value();
            }
        }

        bestWeight = usedWeight;
        bestValue = value;
        greedyInitialValue = value;
    }

    // Upper bound for all 0/1 completions of this node.
    // Exact integer arithmetic; fractional contribution rounds UP.
    private long upperBound(
            int index, int usedWeight, long earnedValue) {

        int free = capacity - usedWeight;
        long upper = earnedValue;

        for (int i = index; i < items.length; i++) {
            Item item = items[i];

            if (item.weight() <= free) {
                free -= item.weight();
                upper += item.value();
            } else {
                // Ceiling of free * value / weight.
                long numerator =
                        (long) free * item.value();
                long ceilPart =
                        (numerator + item.weight() - 1)
                                / item.weight();

                upper += ceilPart;
                break;
            }
        }

        return upper;
    }

    private void dfs(
            int index, int usedWeight, long earnedValue) {

        visitedNodes++;

        long optimistic =
                upperBound(index, usedWeight, earnedValue);

        // If equality is possible, an optimal tie need not be
        // explored because this API returns just ONE optimum.
        if (optimistic <= bestValue) {
            prunedNodes++;
            return;
        }

        if (index == items.length) {
            // A complete selection of include/exclude decisions.
            if (earnedValue > bestValue) {
                bestValue = earnedValue;
                bestWeight = usedWeight;
                System.arraycopy(
                        chosen, 0, bestChosen, 0, chosen.length);
            }
            return;
        }

        Item item = items[index];

        // Branch 1: include this item, if feasible.
        if (item.weight() <= capacity - usedWeight) {
            chosen[index] = true;
            dfs(index + 1,
                    usedWeight + item.weight(),
                    earnedValue + item.value());
            chosen[index] = false; // Undo.
        }

        // Branch 2: exclude this item.
        dfs(index + 1, usedWeight, earnedValue);
    }

    public static Result solve(
            int[] weights, int[] values, int capacity) {

        KnapsackBranchBoundDemo solver =
                new KnapsackBranchBoundDemo(
                        weights, values, capacity);

        solver.dfs(0, 0, 0);

        int selectedCount = 0;
        for (boolean selected : solver.bestChosen) {
            if (selected) {
                selectedCount++;
            }
        }

        int[] originalIndices = new int[selectedCount];
        int write = 0;

        for (int i = 0; i < solver.items.length; i++) {
            if (solver.bestChosen[i]) {
                originalIndices[write++] =
                        solver.items[i].id();
            }
        }

        Arrays.sort(originalIndices);

        return new Result(
                solver.bestValue,
                solver.bestWeight,
                originalIndices,
                solver.greedyInitialValue,
                solver.visitedNodes,
                solver.prunedNodes);
    }

    public static void main(String[] args) {
        int[] weights = {2, 3, 4, 5};
        int[] values = {3, 4, 5, 8};
        int capacity = 8;

        Result result = solve(weights, values, capacity);

        System.out.println(
                "Weights: " + Arrays.toString(weights));
        System.out.println(
                "Values: " + Arrays.toString(values));
        System.out.println(
                "Capacity: " + capacity);
        System.out.println(
                "Greedy incumbent: " + result.greedyInitialValue());
        System.out.println(
                "Optimal value: " + result.bestValue());
        System.out.println(
                "Optimal weight: " + result.totalWeight());
        System.out.println(
                "Chosen original indices: "
                        + Arrays.toString(result.originalIndices()));
        System.out.println(
                "Visited DFS nodes: " + result.visitedNodes());
        System.out.println(
                "Pruned by bound: " + result.prunedNodes());

        Result zero = solve(
                new int[]{2, 3}, new int[]{5, 7}, 0);
        System.out.println(
                "Zero capacity optimum: " + zero.bestValue());

        Result noFit = solve(
                new int[]{2, 3}, new int[]{5, 7}, 1);
        System.out.println(
                "No item fits optimum: " + noFit.bestValue());
    }
}
```

Biên dịch và chạy bằng **JDK 17 trở lên**:

```bash
javac KnapsackBranchBoundDemo.java
java KnapsackBranchBoundDemo
```

**Đầu ra chuẩn chính xác:**

```text
Weights: [2, 3, 4, 5]
Values: [3, 4, 5, 8]
Capacity: 8
Greedy incumbent: 11
Optimal value: 12
Optimal weight: 8
Chosen original indices: [1, 3]
Visited DFS nodes: 10
Pruned by bound: 3
Zero capacity optimum: 0
No item fits optimum: 0
```

### 10.1. Vì sao có hai lần sắp xếp trong ví dụ?

Ở đây **chỉ phép sắp thứ hai theo tỷ số** là cần thiết để tạo cận ba lô phân số. Nếu muốn mã ngắn hơn, có thể **xóa hoàn toàn lời gọi `Arrays.sort(items, Comparator...)` đầu tiên** vì nó không thay đổi kết quả cuối: lần sắp thứ hai đặt các món theo tỷ số và chỉ số gốc đã định nghĩa.

Lời gọi sort đầu tiên chỉ để minh họa rằng một thứ tự sắp không liên quan sẽ bị **thay thế** bởi comparator chính; chương trình chạy đúng nhưng làm thừa công. Trong code production, nên dùng **duy nhất sort theo tỷ số** như phần so sánh `Long.compare(right,left)` bên dưới.

### 10.2. Vì sao comparator không dùng phép chia double?

Nếu so sánh hai tỷ số `v_a/w_a` và `v_b/w_b`, với `w_a,w_b>0`, ta có thể so sánh:

\[
v_a\cdot w_b\quad\text{và}\quad v_b\cdot w_a.
\]

Code dùng `long` cho các tích `int×int` để tránh tràn `int` và tránh trường hợp hai tỷ số rất gần nhau bị nhận nhầm thứ tự do sai số `double`.

Trong một hệ thống cho phép `long` cực lớn ở cả tử và mẫu, các tích chéo có thể vượt `long`; khi đó cần dùng `BigInteger` hoặc phép so sánh phân số chính xác khác. Ví dụ này chỉ nhận trọng số và giá trị `int`.

### 10.3. Cận nguyên và trường hợp hòa

Cận tính bằng **làm tròn lên** phần lợi ích phân số, nên có thể hơi cao hơn giá trị tốt nhất thực sự. Nó vẫn là **cận trên**, chỉ có thể làm thuật toán xét thêm nhánh chứ không làm mất nghiệm tối ưu.

Điều kiện:

```java
if (optimistic <= bestValue) {
    prunedNodes++;
    return;
}
```

hợp lệ vì bài yêu cầu **một** tập tối ưu. Nếu muốn **tất cả** tập tối ưu hoặc nghiệm thứ cấp có trọng số nhỏ nhất khi bằng giá trị, cần thiết kế lại điều kiện cắt và cập nhật kết quả.

### 10.4. Nghiệm tham lam được lưu thế nào?

`initializeGreedyIncumbent` xây một lựa chọn cụ thể trong `bestChosen[]` và tính:

- `bestWeight`: tổng khối lượng của lựa chọn.
- `bestValue`: tổng giá trị.
- `greedyInitialValue`: snapshot giá trị incumbent ban đầu để báo cáo.

Khi DFS tìm ra một tập tốt hơn, nó thay `bestValue`, `bestWeight` và chép `chosen[]` vào `bestChosen[]`. Mảng trả `originalIndices` được sắp lại theo **chỉ số input ban đầu** để người gọi không nhầm với thứ tự sắp theo tỷ số.

### 10.5. Bảo đảm số học của code

Vì số món được giới hạn ≤30, từng giá trị là `int≥0` và từng khối lượng là `int>0`:

- Tổng giá trị tối đa của 30 món dưới khoảng `30(2^{31}-1)`, nhỏ hơn rất nhiều `Long.MAX_VALUE`.
- Tích `free × item.value` và tích chéo giữa hai số `int≥0` cũng nằm trong phạm vi `long` có dấu.
- Biểu thức `numerator + weight - 1` vẫn nằm trong `long` với các giới hạn đã cho.
- `usedWeight` không vượt `capacity≤Integer.MAX_VALUE` vì nhánh lấy món chỉ được gọi sau khi kiểm tra sức chứa.

Nếu bỏ ràng buộc số món hoặc nâng miền trọng số/giá trị thành `long`, phải **kiểm toán lại tràn số**, không tự dùng chứng minh an toàn số học của phiên bản này.

### 10.6. Giới hạn bộ nhớ của nghiệm

Chương trình chỉ lưu:

- Mảng món đã sắp.
- Mảng `chosen[]` đang duyệt.
- Mảng `bestChosen[]` cho incumbent.
- Các biến đếm và stack đệ quy.

Nó **không lưu toàn bộ cây tìm kiếm**. Do đó bộ nhớ làm việc khoảng `O(n)`, nhưng **thời gian worst-case vẫn tăng theo hàm mũ**. Giới hạn n≤30 là hàng rào ví dụ, **không hứa** mọi đầu vào n=30 sẽ chạy nhanh.

---

## 11. Chứng minh cận ba lô phân số là an toàn

Để bảo đảm branch-and-bound đúng, điều quan trọng nhất là chứng minh `upperBound` **không thấp hơn** lợi ích của bất kỳ phần tiếp nối 0/1 hợp lệ nào.

Giả sử ở một nút N đã:

- Chọn một số món, tổng khối lượng W và lợi ích V.
- Loại một số món.
- Còn các món chưa quyết định R.
- Còn sức chứa `C-W≥0`.

Mọi nghiệm hợp lệ hoàn tất từ N có tập món thêm `T⊆R` và:

\[
\sum_{i\in T}w_i\le C-W.
\]

Nghiệm `T` cũng là một lựa chọn hợp lệ của bài **ba lô phân số** trên R, vì bài phân số cho phép mỗi phần tử có hệ số trong `[0,1]`, bao gồm hai giá trị 0 và 1. Do đó:

\[
\max_{\text{0/1 hoàn tất}}(V+\sum_{i\in T}v_i)
\le
V+\max_{\text{phân số}} \sum_{i\in R} v_i y_i.
\]

Với `v_i≥0,w_i>0`, thuật toán lấy theo tỷ số giảm cho tối ưu của relaxation phân số. Nếu lấy toàn bộ các món cho tới khi không còn đủ chỗ, rồi lấy một phần của món kế tiếp, ta thu **cận trên thực** của mọi nghiệm 0/1.

Code thay phần lợi ích phân số cuối cùng bằng **giá trị nguyên làm tròn lên**, nên kết quả không nhỏ hơn cận thực:

\[
UB_{\mathrm{code}}(N)
\ge UB_{\mathrm{fractional}}(N)
\ge\max_{x\in F(N)}f(x).
\]

Vì vậy, khi `UB_code(N)≤bestValue`, mọi nghiệm hợp lệ trong N đều có giá trị `≤bestValue`. Cắt N là **an toàn**.

### 11.1. Vì sao phải sort các món theo tỷ số trước?

Phương pháp “lấy phần tử phân số đầu tiên không vừa” chỉ tính đúng **giá trị tối ưu phân số** nếu các món trong suffix đã được sắp theo `v/w` giảm. Nếu không sort, việc chọn một món tỷ số thấp trước có thể tiêu thụ sức chứa, khiến kết quả phân số tìm được thấp hơn một nghiệm 0/1 đang ẩn ở phần còn lại.

Do đó, chỉ thay comparator hoặc chỉ bỏ sort vì “không ảnh hưởng kết quả DFS” có thể **phá chứng minh cận**. Thứ tự phân nhánh có thể tùy ý **nếu bạn thay công thức cận bằng một cận vẫn hợp lệ**; riêng công thức fractional-greedy yêu cầu trình tự tỷ số đúng.

### 11.2. Cận có thể bằng incumbent dù vẫn còn nghiệm tối ưu khác

Giả sử incumbent=12 và một nhánh có `UB=12`. Nhánh có thể chứa **một** nghiệm mới cũng đạt 12, nhưng không có nghiệm nào đạt **lớn hơn 12**.

Nếu mục tiêu là **một nghiệm tối ưu**, cắt được. Nếu cần **đếm tất cả** nghiệm giá trị 12 hoặc chọn nghiệm có một tiêu chí phụ, phải xem nhánh hòa có còn cần xét hay không.

### 11.3. Không được tính cận dựa trên nghiệm tham lam 0/1

Một tập món tham lam 0/1 là **một nghiệm khả thi**, nên giá trị của nó **không lớn hơn** tối ưu 0/1; đây là **cận dưới** cho bài cực đại. Không được dùng trực tiếp nó làm cận trên để cắt nhánh.

Ta dùng **hai vai trò khác nhau**:

- Greedy 0/1 → cung cấp **incumbent khả thi**.
- Fractional knapsack → cung cấp **cận trên cho phần chưa xét**.

---

## 12. Chứng minh tính đúng của toàn bộ branch-and-bound

Đặt tập nghiệm tối ưu của bài là `X^*`. Ta cần chứng minh rằng sau khi thuật toán duyệt xong, nó lưu một nghiệm khả thi đạt giá trị tối ưu.

### 12.1. Bất biến incumbent

Ở mọi thời điểm, incumbent phải là **một nghiệm hoàn chỉnh khả thi**. Trong ví dụ ba lô:

- Seed greedy chọn những món vừa sức, nên khối lượng không vượt C.
- Mỗi lần cập nhật tại lá, mảng `chosen[]` mô tả các quyết định lấy/bỏ của **tất cả món**, không lấy một món quá một lần.
- Nhánh lấy chỉ được thực hiện khi khối lượng mới không vượt C.
- Vì vậy mọi snapshot vào `bestChosen[]` đều là nghiệm khả thi.

Giá trị của incumbent không giảm vì chỉ cập nhật khi `earnedValue>bestValue`.

### 12.2. Bất biến cận

Tại mọi nút N:

\[
UB(N)\ge\max_{x\in F(N)}f(x).
\]

Bất biến này được bảo đảm bởi chứng minh relaxation ở mục 11. Dù cận hơi lỏng do làm tròn lên, nó vẫn đúng.

### 12.3. An toàn của bước cắt

Nếu một nút bị cắt khi:

\[
UB(N)\le incumbent,
\]

thì mọi nghiệm trong N có giá trị `≤incumbent`. Vì incumbent đã đạt được bởi một nghiệm thật, bỏ N **không thể bỏ mất một nghiệm tốt hơn**.

Nếu nút bị bỏ vì không khả thi, rõ ràng không có nghiệm hợp lệ nào bên dưới. Những nút còn lại được DFS mở rộng và xét từng quyết định, nên không mất nghiệm nào ngoài các nhánh đã được chứng minh không cần.

### 12.4. Kết thúc và tính tối ưu

Cây có hữu hạn n quyết định nhị phân. Mỗi lời gọi tăng index, nên sau hữu hạn bước DFS kết thúc.

Giả sử vẫn tồn tại một nghiệm khả thi có giá trị **lớn hơn** incumbent cuối cùng. Theo cây phân nhánh, nghiệm ấy nằm trên một đường từ gốc đến lá. Nó không thể nằm trong nhánh cắt do bất khả thi, vì bản thân là nghiệm hợp lệ. Nó cũng không thể nằm trong nhánh cắt do cận, vì cận ở thời điểm cắt đã chứng minh mọi nghiệm trong nhánh không tốt hơn incumbent tại thời điểm đó; incumbent về sau chỉ tăng. Vậy đường ấy phải được khám phá tới lá và cập nhật incumbent — mâu thuẫn.

Do đó incumbent cuối cùng đạt **giá trị tối ưu toàn cục**.

---

## 13. Chọn thứ tự duyệt: DFS, breadth-first và best-first

Các chiến lược duyệt khác nhau **không thay đổi điều kiện cắt đúng**, nhưng có thể thay đổi rất lớn lượng công việc thực tế.

### 13.1. DFS: đi sâu trước

Ưu điểm:

- Dễ cài bằng đệ quy.
- Chỉ cần lưu đường đi đang duyệt, thường `O(depth)` bộ nhớ ngoài dữ liệu bài.
- Dễ tìm một nghiệm hoàn chỉnh sớm, đặc biệt nếu ưu tiên nhánh **có triển vọng**.

Nhược điểm:

- Có thể mắc lâu trong một nhánh chất lượng kém.
- Nếu incumbent ban đầu yếu, cận chưa đủ mạnh để cắt sớm.

Chương trình Java dùng **DFS, lấy món trước, bỏ món sau**, và seed greedy để có incumbent ban đầu.

### 13.2. Best-first branch-and-bound

Có thể đặt các nút chưa xét vào một **priority queue**:

- **Cực tiểu:** ưu tiên nút có **cận dưới nhỏ nhất**.
- **Cực đại:** ưu tiên nút có **cận trên lớn nhất**.

Ý tưởng là xét trước các nhánh còn **khả năng cải thiện** tốt nhất, với hy vọng sớm tìm incumbent tốt hoặc xác lập khoảng tối ưu nhỏ.

Ưu điểm: có thể giúp phát hiện/phủ định các nhánh hứa hẹn nhanh; dễ theo dõi một **cận toàn cục của frontier**.

Nhược điểm: phải lưu nhiều nút đang chờ, có thể dùng **bộ nhớ rất lớn**. Một node cũng phải lưu đủ trạng thái/cha để tiếp tục mở rộng.

**Không đồng nhất:** best-first dùng cận để **xếp lịch khám phá**, còn điều kiện **cắt đúng** vẫn dựa trên so sánh cận và incumbent.

### 13.3. BFS: theo độ sâu

BFS mở rộng các nút cùng mức trước. Nó dễ tổ chức theo số quyết định đã chốt nhưng có thể phải lưu số lượng rất lớn các nút cùng một mức. Đối với bài tối ưu tổ hợp, BFS thường không có lợi thế phổ quát so với DFS hay best-first, trừ khi cấu trúc bài toán hoặc yêu cầu đầu ra phù hợp.

### 13.4. Chọn nhánh có triển vọng trước

Với ba lô, thử **lấy món tỷ số lợi ích/khối lượng cao** trước có thể đưa đến một nghiệm mạnh sớm. Với TSP, thử cạnh ngắn trước có thể giúp tìm một tour có chi phí thấp, làm incumbent tốt hơn.

Đây là **heuristic thứ tự duyệt**, không phải chứng minh rằng những lựa chọn đầu tiên là tối ưu. Dù nhánh “xấu” được xét sau, nó vẫn phải được giữ lại nếu cận chưa đủ để cắt.

---

## 14. Cận toàn cục, chứng nhận tối ưu và khoảng chênh

Trong branch-and-bound, ngoài incumbent, ta có thể theo dõi cận của **tập các nút chưa xử lý** (*frontier / open nodes*).

### 14.1. Cực tiểu

Giả sử incumbent khả thi có chi phí U, và các nút chưa xét có cận dưới `LB(N)`. Đặt:

\[
L_{\mathrm{frontier}}=\min_{N\in frontier}LB(N).
\]

Mọi nghiệm tốt hơn incumbent hiện tại, nếu tồn tại, phải nằm trong một nhánh còn mở. Vì thế:

\[
OPT\ge \min(U,L_{\mathrm{frontier}}),\qquad OPT\le U.
\]

Nếu `L_frontier≥U` (hoặc frontier rỗng), không nhánh nào có thể tốt hơn incumbent; **U đã tối ưu**.

Ví dụ:

```text
Tour hiện có: cost U=80 (hợp lệ)
Frontier có các cận dưới: 75, 88, 96
=> Chưa thể kết luận tối ưu, vì nhánh LB=75 còn hy vọng.

Sau khi xử lý nhánh LB=75:
Frontier còn các LB: 88, 96
=> Tất cả LB >= 80, có thể kết luận U=80 tối ưu.
```

### 14.2. Cực đại

Giả sử incumbent khả thi đạt L, còn các nút mở có cận trên `UB(N)`. Đặt:

\[
U_{\mathrm{frontier}}=\max_{N\in frontier}UB(N).
\]

Ta có:

\[
L\le OPT\le\max(L,U_{\mathrm{frontier}}).
\]

Nếu `U_frontier≤L` (hoặc frontier rỗng), incumbent đã đạt tối ưu.

### 14.3. Khoảng chênh tuyệt đối khi dừng sớm

Trong một số ứng dụng cần dừng theo giới hạn thời gian thay vì chứng minh tối ưu:

- **Cực tiểu:** đã có nghiệm chi phí U và cận dưới toàn cục hợp lệ L, khoảng chênh tuyệt đối tối đa là `U-L≥0` (sau khi bảo đảm L≤U).
- **Cực đại:** đã có nghiệm giá trị L và cận trên toàn cục hợp lệ U, khoảng chênh tối đa là `U-L≥0`.

Những con số này giúp công bố mức chưa chắc chắn. Nhưng **không được tự gọi incumbent là tối ưu chính xác** khi cận trên/dưới còn khoảng cách.

Nếu không có nghiệm khả thi nào, chưa thể công bố một incumbent hữu hạn hoặc tỷ lệ gap theo nghiệm hiện có; nếu frontier còn mở, bài toán có thể vẫn chưa biết là khả thi hay bất khả thi.

### 14.4. Quy ước khi frontier rỗng

Khi không còn nút chưa xét:

- Nếu **đã có incumbent hợp lệ**, nghiệm ấy tối ưu (mọi nhánh còn lại đều đã xét/cắt đúng).
- Nếu **chưa có nghiệm**, bài toán **không khả thi** theo những ràng buộc đã được bao phủ.

Không được dùng công thức `min/max` trên tập rỗng mà quên định nghĩa trường hợp kết thúc này.

---

## 15. Những điều kiện khiến cận sai

### 15.1. Cắt bằng chi phí đã tích lũy trong bài có phần chi phí âm

Trong cực tiểu với các chi phí cộng **không âm**, nếu chi phí đường đi đã chọn đã ≥ incumbent, và mọi phần tiếp nối không thể làm tổng giảm, có thể cắt.

Nhưng nếu những quyết định tương lai có **chi phí âm hoặc phần thưởng âm**, tổng chi phí hoàn chỉnh có thể **nhỏ hơn** chi phí hiện tại. Ví dụ:

```text
Incumbent cực tiểu = 10
Chi phí đã tích lũy = 12
Một quyết định tương lai có chi phí = -5
Tổng hoàn chỉnh = 7 < 10
```

Cắt chỉ vì `12≥10` sẽ **sai**. Cần cận dưới đúng có tính đến mọi khả năng giảm chi phí.

### 15.2. Cắt bằng lợi ích đã tích lũy trong bài cực đại

Ở cực đại, nếu đã đạt 11 và một nhánh hiện có lợi ích 8, không được bỏ chỉ vì `8<11`. Những quyết định còn lại có thể đem thêm 20 lợi ích, đạt 28.

Ta cần **cận trên cho toàn bộ phần tiếp nối**, không phải so trực tiếp giá trị hiện tại.

### 15.3. Cận bỏ qua một ràng buộc theo hướng sai

Nới lỏng bài toán có thể tạo cận đúng nếu bỏ ràng buộc theo hướng **mở rộng miền nghiệm**. Nhưng nếu cách tính “cận” vô tình **giới hạn thêm** lựa chọn, nghiệm tối ưu của bài đơn giản hóa có thể thấp hơn tối ưu gốc trong cực đại hoặc cao hơn trong cực tiểu, khiến cắt nhánh sai.

Ví dụ dùng một heuristic 0/1 chọn được 11 và gán “UB=11” cho bài ba lô có optimum 12 là **sai cận**.

### 15.4. Sai số số thực

Một cận trên cực đại bị **làm tròn xuống** hoặc một cận dưới cực tiểu bị **làm tròn lên** quá mức có thể cắt sai. Đối với các phép tính số thực:

- Chọn cách làm tròn bảo thủ đúng chiều.
- Nếu cần, dùng số hữu tỷ/số nguyên chính xác.
- Kiểm tra biên tràn và NaN.
- Với bài số nguyên, tận dụng tính nguyên của mục tiêu bằng một phép biến đổi có chứng minh.

### 15.5. Phá hòa không đúng yêu cầu

Nếu cần **mọi nghiệm tối ưu**, cắt khi cận bằng incumbent có thể làm thiếu các nghiệm hòa. Nếu cần chọn nghiệm có **chi phí phụ thấp nhất** sau khi tối ưu tiêu chí chính, so sánh chỉ theo một scalar của tiêu chí chính cũng có thể loại nhầm nghiệm tốt hơn về tiêu chí phụ.

Cần xác định mục tiêu và cách phá hòa **trước khi thiết kế cận**.

---

## 16. Ứng dụng: bài toán người du lịch cực tiểu

Với TSP trên một đồ thị có hướng hoặc vô hướng, lời giải khả thi là **một chu trình Hamilton thật**: bắt đầu, thăm các đỉnh yêu cầu theo ràng buộc rồi quay về điểm đầu qua các cạnh hợp lệ.

Một tour tham lam kiểu **nearest neighbor** có thể cung cấp một incumbent nhanh nếu nó thực sự đi đủ đỉnh và quay về được. Nó không nhất thiết tối ưu, và trên đồ thị có cạnh thiếu có thể mắc kẹt; không được nhận một hành trình không hoàn chỉnh làm incumbent.

### 16.1. Cận dưới cần chứng minh

Với TSP **đối xứng, không âm, đồ thị đầy đủ** và một đường đi một phần từ gốc tới đỉnh u, còn tập đỉnh R chưa thăm, một dạng cận dưới trực quan (khi `R` không rỗng) là:

\[
LB=
costSoFar
+MST(R)
+\min_{r\in R}w[u][r]
+\min_{r\in R}w[r][start].
\]

Trong đó:

- `MST(R)` là chi phí cây khung nhỏ nhất nối các đỉnh chưa thăm R theo trọng số vô hướng.
- `min w[u][r]` là chi phí ít nhất có thể dùng để đi từ đầu mút hiện tại sang một đỉnh chưa thăm.
- `min w[r][start]` là chi phí ít nhất có thể đi từ một đỉnh chưa thăm về điểm xuất phát.

**Vì sao là cận dưới?** Trong mọi tour hợp lệ hoàn tất đường đi hiện tại, đoạn đi qua tất cả R phải chứa một cách nối các đỉnh R; những cạnh nội bộ của tour đó tạo một cây nối R nên có chi phí không nhỏ hơn `MST(R)`. Ngoài ra phải có cạnh từ u vào R và cạnh từ R về start. Do đó mọi tour hoàn chỉnh phải tốn ít nhất tổng ba thành phần cộng chi phí đã đi.

Khi `R` chỉ có một đỉnh, quy ước `MST(R)=0`, hai cạnh nối vẫn bắt buộc. Khi `R` rỗng, cận là `costSoFar+w[u][start]` nếu cạnh đóng tour tồn tại, không được tiếp tục dùng phép min trên tập rỗng.

**Giới hạn:** công thức ở đây dành cho TSP đối xứng có những giả thiết đã nêu; không dùng nguyên `MST` vô hướng làm cận dưới cho TSP **có hướng** hoặc bài có ràng buộc thời gian/tải trọng mà không chứng minh lại.

### 16.2. Ví dụ dùng incumbent và cận

```text
Đã có tour hợp lệ: chi phí 95.
Nhánh A: cận dưới 100 -> cắt.
Nhánh B: cận dưới 93  -> chưa thể cắt.
Nhánh C: cận dưới 70  -> chưa thể cắt.
```

Nếu sau đó tìm được tour hợp lệ chi phí **82**, incumbent giảm thành 82. Khi đó nhánh B với cận dưới 93 cũng bị cắt; nhánh C vẫn chưa đủ điều kiện cắt.

**Đây là lý do incumbent và bound tác động lẫn nhau:** incumbent tốt hơn làm ngưỡng cắt mạnh hơn; cận chặt hơn giúp bỏ nhiều nhánh; thứ tự duyệt tốt giúp tìm incumbent mạnh sớm.

---

## 17. Ứng dụng: phân công công việc cho người thực hiện

Giả sử có n người và n việc. Mỗi người phải nhận **đúng một việc**, mỗi việc giao cho **đúng một người**, và `cost[i][j]` là chi phí người i làm việc j. Mục tiêu là **cực tiểu tổng chi phí**.

Một nút quyết định đã giao xong k người đầu, còn tập công việc chưa dùng. Phần chi phí đã chọn là `currentCost`.

Một cận dưới đơn giản:

\[
LB(N)=currentCost+
\sum_{\text{người }i\text{ chưa giao}}
\min_{\text{việc }j\text{ chưa dùng}}cost[i][j].
\]

Vì sao đúng?

- Mỗi người còn lại cuối cùng phải nhận **một** việc chưa dùng.
- Chi phí của họ không thể nhỏ hơn **mức nhỏ nhất trong những việc chưa dùng**.
- Cộng những mức tối thiểu này tạo **cận dưới** cho mọi cách phân công hoàn chỉnh.

Có thể cận này chọn **cùng một công việc** làm rẻ nhất cho nhiều người, dù nghiệm thật không được giao một việc cho hai người. Điều đó khiến cận **lạc quan**, nhưng vẫn hợp lệ: bài cận **bỏ bớt** ràng buộc các người phải nhận công việc khác nhau.

Nếu đã có phân công khả thi chi phí 25 và một nút có cận dưới 28, ta cắt nút đó. Nếu cận dưới 20, chưa cắt được vì có thể vẫn tồn tại một phân công hoàn chỉnh tốt hơn 25.

**Chú ý:** nếu ma trận có những cặp người–việc bị cấm, phải tính min trên **các lựa chọn còn hợp lệ**. Nếu một người không có việc hợp lệ nào còn lại, có thể xác định nhánh không khả thi. Nếu chỉ dùng giá trị sentinel vô hạn rồi cộng thiếu kiểm soát, code có thể tràn hoặc tạo cận giả.

---

## 18. Nhánh và cận so với quay lui, tham lam và quy hoạch động

| Phương pháp | Ý tưởng chính | Bảo đảm tối ưu trong bài tổng quát? |
| --- | --- | --- |
| Vét cạn | Xem mọi phương án, chọn tốt nhất | Có, nếu liệt kê đúng hết và tính mục tiêu đúng |
| Quay lui | Xây nghiệm từng bước, hoàn tác, cắt nhánh vi phạm điều kiện | Có khi vẫn xét mọi nghiệm khả thi cần thiết |
| Tham lam | Chọn quyết định “tốt ngay” theo quy tắc | Chỉ khi có chứng minh greedy đúng |
| Quy hoạch động | Gộp trạng thái con có cấu trúc lặp | Có khi trạng thái/chuyển đúng và đủ |
| Nhánh và cận | Kết hợp nghiệm khả thi tốt nhất với cận cho nhánh chưa xét | Có khi cận hợp lệ, phân nhánh bao phủ nghiệm và thuật toán hoàn tất |

**Quan hệ:** branch-and-bound có thể được xây trên một bộ khung backtracking và bổ sung điều kiện cắt dựa trên incumbent/bound. Nó cũng có thể kết hợp DP, dominance, memoization hoặc relaxations mạnh.

### 18.1. Vì sao không thể gộp mọi trạng thái giống DP?

Nếu hai trạng thái có cùng “đỉnh hiện tại” nhưng khác tập đã thăm, chúng có thể có những phần tiếp nối khác nhau. Gộp sai trạng thái làm mất nghiệm.

Để dùng dominance hoặc memoization, phải chứng minh hai trạng thái có **cùng thông tin tương lai** và chỉ khác một giá trị tích lũy có thể so sánh. Đây là điều kiện sâu hơn việc thấy hai nút có tên đỉnh hoặc độ sâu giống nhau.

### 18.2. Khi nào dùng branch-and-bound?

Phù hợp khi:

- Không gian nghiệm là tập rời rạc rất lớn, nhưng có thể xây một **cây quyết định**.
- Có thể tìm **một nghiệm khả thi tốt** đủ nhanh.
- Có **cận lạc quan tính được rẻ** và đủ chặt để cắt nhiều nhánh.
- Cần **bảo đảm tối ưu** hơn là chỉ cần một heuristic.

Không nên kỳ vọng branch-and-bound luôn nhanh: trong bài toán khó, cận có thể quá lỏng và thuật toán vẫn phải xét gần như toàn bộ cây.

---

## 19. Phân tích thời gian và bộ nhớ

### 19.1. Cận xấu nhất

Với ba lô 0/1, nếu quyết định lấy/bỏ cho n món, cây nhị phân đầy đủ có tối đa:

\[
1+2+\cdots+2^n=2^{n+1}-1
\]

nút. Cận có thể không cắt được nhiều nhánh trong dữ liệu xấu nhất.

Trong chương trình Java:

- Sort n món theo tỷ số: `O(n\log(n+1))`.
- Mỗi lời gọi DFS tính cận bằng cách quét tối đa n món còn lại: `O(n)`.
- Số nút DFS worst-case: `O(2^n)`.

Do đó một cận trên an toàn cho thời gian:

\[
\boxed{O(n2^n)}.
\]

Bộ nhớ:

- Mảng món, `chosen[]` và `bestChosen[]`: `O(n)`.
- Stack đệ quy sâu tối đa n: `O(n)`.
- Tổng bộ nhớ làm việc ngoài input: `O(n)`, không lưu tất cả các nút của cây.

Best-first branch-and-bound có thể dùng nhiều bộ nhớ hơn vì phải lưu frontier của nhiều nút cùng lúc.

### 19.2. Không có bảo đảm thời gian đa thức cho mọi đầu vào

Việc chạy nhanh trên một số ví dụ không chứng minh thuật toán có độ phức tạp tốt nhất đa thức. TSP, ba lô và nhiều bài tối ưu tổ hợp thuộc lớp bài toán khó trong trường hợp tổng quát. Hiệu quả thực tế phụ thuộc:

- Sức mạnh của incumbent ban đầu.
- Độ chặt của bound.
- Thứ tự chọn biến và nhánh.
- Mức độ hạn chế của các ràng buộc.
- Chi phí tính bound tại mỗi nút.
- Khả năng phát hiện dominance và nhánh bất khả thi.

Mẫu Java giới hạn n≤30 để học, nhưng ngay cả 30 quyết định có thể tạo tới khoảng **hơn một tỷ lá** nếu cận quá lỏng. Không dùng giới hạn đó như bảo đảm hoàn thành trong thời gian ngắn.

---

## 20. Kiểm thử đúng đắn

Không chỉ so kết quả với một giá trị mẫu; cần kiểm tra **nghiệm khôi phục thực sự hợp lệ** và **giá trị cận đủ bảo thủ**.

### 20.1. Các test cơ bản cho Java

| Input | Kết quả mong đợi |
| --- | --- |
| `weights=[2,3,4,5],values=[3,4,5,8],C=8` | Giá trị tối ưu **12**, chọn chỉ số `[1,3]` trong code mẫu |
| `weights=[],values=[],C=0` | Nghiệm rỗng, giá trị 0 |
| `weights=[2,3],values=[5,7],C=0` | Không lấy món nào, giá trị 0 |
| `weights=[2,3],values=[5,7],C=1` | Không món nào vừa, giá trị 0 |
| `weights=[1],values=[5],C=1` | Chọn món 0, giá trị 5 |
| `weights=[1,1],values=[5,5],C=1` | Giá trị 5; có nhiều tập tối ưu |
| `weights=[3,4],values=[0,0],C=10` | Giá trị tối ưu 0 |
| `weights=[2,2],values=[4,5],C=2` | Chọn món giá trị 5, tổng 5 |
| `weights=[2],values=[5],C=-1` | Báo lỗi vì sức chứa âm |
| Mảng weights/values khác độ dài | Báo lỗi input |
| Có khối lượng 0 hoặc âm | Code mẫu báo lỗi input |
| Có giá trị âm | Code mẫu báo lỗi input theo hợp đồng |
| n>30 | Code mẫu từ chối theo giới hạn demo |

**Nhớ:** trong bài ba lô, tập rỗng là nghiệm hợp lệ. Nhưng trong TSP chu trình với n>1, không có tour thì **không thể** trả 0 như một nghiệm hợp lệ.

### 20.2. Thuộc tính của kết quả tối ưu ba lô

Giả sử kết quả trả `bestValue`, `totalWeight` và `originalIndices`:

1. Mỗi chỉ số nằm trong `[0,n)`.
2. Không có chỉ số nào xuất hiện hai lần.
3. Tổng `weights[id]` của các chỉ số bằng `totalWeight`.
4. `totalWeight≤capacity`.
5. Tổng `values[id]` của các chỉ số bằng `bestValue`.
6. `bestValue≥greedyInitialValue` vì incumbent chỉ cải thiện.
7. `prunedNodes≤visitedNodes`.
8. Giá trị `bestValue` bằng đáp án vét cạn nếu n đủ nhỏ để kiểm chứng.

### 20.3. Oracle vét cạn cho n nhỏ

Với n≤20 hoặc nhỏ hơn tùy tốc độ:

```text
BRUTE_FORCE_01_KNAPSACK(items, C):
    best = 0
    for mask từ 0 tới (1<<n)-1:
        weight = sum(weights[i] nếu bit i bật)
        value  = sum(values[i] nếu bit i bật)

        if weight <= C:
            best = max(best, value)

    return best
```

Bài thử ngẫu nhiên nên tạo nhiều bộ có:

- Khối lượng nhỏ, nhiều bộ vừa sức.
- Giá trị bằng nhau hoặc bằng 0.
- Sức chứa 0 hoặc thấp hơn tất cả khối lượng.
- Sức chứa rất lớn để lấy tất cả món.
- Nhiều món có tỷ số gần nhau.
- Nhiều nghiệm cùng giá trị.

So `bestValue` của branch-and-bound với brute force. Nếu khác, nguyên nhân thường là **cận sai chiều, cắt sai hoặc cập nhật/truy vết incumbent sai**.

### 20.4. Kiểm tra tính an toàn của bound bằng oracle

Ở mỗi nút giả lập của dữ liệu nhỏ:

1. Cố định tất cả quyết định trong tiền tố.
2. Liệt kê mọi cách lấy/bỏ các món **còn lại** mà không vượt sức chứa.
3. Tính giá trị tối ưu thật `trueBestCompletion` của nhánh.
4. Khẳng định `upperBound(node)≥trueBestCompletion`.

Đây là một kiểm thử rất mạnh cho **tính admissible của cận**. Nếu phát hiện dù chỉ một nút mà `upperBound<trueBestCompletion`, điều kiện cắt có thể không an toàn; phải sửa công thức cận trước khi dùng cho bài toán tối ưu.

---

## 21. Những lỗi thường gặp

1. **Nhầm một cận lạc quan với một nghiệm khả thi.** Cận có thể dùng phần tử phân số hoặc bỏ ràng buộc nên không tạo được lời giải thật.
2. **Dùng cận trên để cắt bài cực tiểu** hoặc cận dưới để cắt bài cực đại, mà không chứng minh đó là cận cần thiết.
3. **Cắt bài cực tiểu khi `LB≤incumbent`** — ngược dấu; đúng là `LB≥incumbent`.
4. **Cắt bài cực đại khi `UB≥incumbent`** — ngược dấu; đúng là `UB≤incumbent`.
5. **Khởi tạo incumbent bằng một giá trị không có nghiệm thật**, ví dụ TSP có cạnh thiếu nhưng đặt incumbent=0.
6. **Cho rằng heuristic phải tối ưu mới được dùng làm incumbent.** Không cần; chỉ cần khả thi và lưu lời giải thật.
7. **Không cải thiện incumbent khi tìm thấy nghiệm tốt hơn** hoặc cập nhật bằng nghiệm không thỏa ràng buộc.
8. **Tính bound quá yếu** nên phải duyệt gần như mọi nút, rồi kết luận branch-and-bound “sai”.
9. **Tính bound quá đắt** khiến tổng thời gian tệ hơn một cận đơn giản.
10. **Dùng giá trị greedy 0/1 làm cận trên ba lô**, dù nó chỉ là một nghiệm khả thi và có thể thấp hơn tối ưu.
11. **Không sort theo tỷ số trước khi dùng fractional-greedy bound**, khiến giá trị tính ra có thể không phải cận trên.
12. **Làm tròn cận trên xuống vì tiện**, dẫn đến nguy cơ mất nhánh có nghiệm tốt.
13. **Bỏ qua quyết định đã cố định khi tính bound**, làm cận không còn phản ánh đúng tập phần tiếp nối.
14. **Cắt nhánh dựa trên chi phí đã đi khi tương lai có thể giảm tổng**, ví dụ còn chi phí âm.
15. **Không hoàn tác trạng thái**, khiến một nhánh dùng quyết định của nhánh trước.
16. **Lưu tham chiếu đến mảng đang thay đổi thay vì snapshot incumbent**, nên lời giải cuối không khớp giá trị đã ghi.
17. **Trả giá trị bound như giá trị tối ưu** khi frontier vẫn còn nhánh có thể cải thiện.
18. **Quên xử lý nhánh không khả thi và trường hợp chưa có incumbent**.
19. **Cắt khi bằng incumbent dù đề yêu cầu tất cả nghiệm tối ưu** hoặc quy tắc phụ.
20. **Dùng số thực không kiểm soát và phép cộng tràn số**, làm bất đẳng thức bound không còn đáng tin.
21. **Xem số nút bị cắt nhiều là chứng minh đúng**; chỉ có tính hợp lệ của bound và quy tắc phân nhánh mới đảm bảo đúng.
22. **Đồng nhất “chưa tìm được nghiệm” với “không tồn tại nghiệm”** khi frontier còn chưa xét.
23. **Không kiểm tra nghiệm được trả**, dẫn đến giá trị đúng nhưng tập chọn/đường đi bị sai.
24. **Đánh giá sai độ phức tạp** vì chỉ đếm số nút mà quên chi phí tính cận ở mỗi nút.

---

## 22. Bài tập tự kiểm tra

**Bài 1 — Chiều cắt.** Một bài cực tiểu có incumbent=50. Hai nhánh có cận dưới 52 và 43. Nhánh nào được cắt? Giải thích.

**Bài 2 — Cực đại.** Một bài cực đại có incumbent=80, các nút có UB lần lượt 79, 80, 95. Nếu chỉ cần một nghiệm tối ưu, các nút nào có thể cắt?

**Bài 3 — Greedy và cận.** Với ba lô khối lượng `[2,3,4,5]`, giá trị `[3,4,5,8]`, sức chứa 8, chọn một nghiệm khả thi có giá trị 11. Vì sao 11 không phải cận trên của bài?

**Bài 4 — Relaxation phân số.** Sắp các món bài 3 theo tỷ số giá trị/khối lượng giảm. Tính giá trị fractional knapsack ở gốc và cận nguyên làm tròn lên. Cận nào chặt hơn?

**Bài 5 — Tập tối ưu.** Tìm một tập món tối ưu trong bài 3, ghi chỉ số gốc, khối lượng và giá trị.

**Bài 6 — An toàn của bound.** Giả sử `UB(node)=12` và incumbent cực đại=12. Có được cắt khi chỉ cần một nghiệm tối ưu không? Nếu cần liệt kê mọi tập cùng giá trị 12 thì sao?

**Bài 7 — Cận sai.** Cho một nhánh ba lô có nghiệm tốt nhất thật là 15 nhưng một heuristic chỉ tìm được 10. Tại sao không được gán `UB(node)=10` rồi cắt nếu incumbent=12?

**Bài 8 — Chi phí âm.** Trong bài cực tiểu, incumbent=10, costSoFar=12, nhưng còn khả năng cộng −5. Có thể cắt chỉ vì 12≥10 không? Cần gì để cắt đúng?

**Bài 9 — Phân công.** Với bài phân công n người–n việc, hãy nêu một cận dưới đơn giản khi đã phân công k người. Vì sao việc lấy min chi phí riêng cho từng người còn lại không vi phạm điều kiện “cận dưới”, dù có thể chọn cùng một việc trong tính toán?

**Bài 10 — Chứng minh.** Phát biểu hai bất biến: incumbent luôn khả thi và cận đúng chiều. Dùng chúng để chứng minh một nhánh bị cắt không thể chứa nghiệm tốt hơn incumbent hiện có.

**Bài 11 — Khoảng chênh.** Một bài cực tiểu có incumbent khả thi U=120; tất cả nhánh mở có cận dưới nhỏ nhất là 108. Hãy nêu khoảng chứa OPT. Khi nào kết luận nghiệm 120 tối ưu?

**Bài 12 — Chiến lược duyệt.** So sánh DFS và best-first về bộ nhớ và thứ tự xem nhánh. Thay đổi thứ tự duyệt có làm phép chứng minh cắt nhánh mất hiệu lực không?

**Bài 13 — Độ phức tạp.** Bài ba lô có n quyết định lấy/bỏ. Vì sao worst-case là `O(n2^n)` với code dùng bound quét suffix, dù nhiều ví dụ thực tế ít nút hơn nhiều?

**Bài 14 — Kiểm thử cận.** Hãy thiết kế một oracle brute-force trên n nhỏ để kiểm tra không có trạng thái nào mà cận trên của code thấp hơn nghiệm 0/1 tốt nhất thật của nhánh.

**Bài 15 — Hai nghiệm bằng nhau.** Có hai tập món khác nhau cùng đạt lợi ích tối ưu 20, nhưng một tập nhẹ hơn. Nếu đề yêu cầu “giá trị tối đa, rồi **nhẹ nhất** khi hòa”, điều kiện cắt `UB≤bestValue` có cần xem lại không?

### Đáp án gợi ý

1. Cắt nhánh LB=52 vì không thể giảm dưới incumbent=50. Không cắt LB=43; nó vẫn có thể chứa nghiệm có chi phí dưới 50.
2. Cắt UB=79 và UB=80. Không cắt UB=95 vì còn khả năng đạt trên 80.
3. `{A,D}` hợp lệ và đạt 11, nhưng `{B,D}` đạt 12. Nghiệm greedy chỉ chứng minh `OPT≥11`, không chứng minh `OPT≤11`.
4. Sắp D (1,6), A (1,5), B (4/3), C (1,25). Lấy D+A đầy đủ (giá trị 11) rồi lấy 1/3 B (thêm 4/3) cho `37/3≈12,333`. Cận 13 sau làm tròn lên yếu hơn nhưng vẫn an toàn.
5. Chọn chỉ số gốc `[1,3]`: khối lượng `3+5=8`, giá trị `4+8=12`.
6. Có, nếu chỉ cần một nghiệm tối ưu. Nếu cần mọi nghiệm có cùng giá trị 12, cắt dấu bằng có thể làm mất nghiệm.
7. Heuristic tạo nghiệm giá trị 10 chỉ là cận **dưới** cho optimum của nhánh; true optimum 15 vượt cả incumbent=12, nên “UB=10” sẽ cắt sai.
8. Không. Tổng hoàn chỉnh có thể là `12-5=7<10`. Cần cận dưới tính được cho mọi phần tiếp nối, kể cả các chi phí âm.
9. `currentCost + sum_i min_j cost[i][j]` trên người chưa giao và việc chưa dùng. Việc tạm cho nhiều người chọn cùng việc chỉ **nới lỏng** ràng buộc, có thể cho chi phí quá thấp nhưng không cao hơn lời giải hợp lệ.
10. Incumbent luôn là giá trị của nghiệm thật. Với cực đại, `UB(N)≥f(x)` cho mọi hoàn tất x. Nếu `UB(N)≤incumbent`, không x nào tốt hơn; lập luận tương tự cho cực tiểu.
11. `108≤OPT≤120` (giả sử 108 là cận dưới hợp lệ nhỏ nhất của các nhánh còn mở và đã xét đúng các nhánh cắt). Chứng minh 120 tối ưu khi mọi nhánh mở đều có LB≥120 hoặc đã được xử lý/cắt đúng.
12. DFS thường dùng ít bộ nhớ, đi sâu; best-first ưu tiên nút có cận triển vọng nhất và có thể lưu rất nhiều nút. Thứ tự duyệt không làm điều kiện cắt mất hiệu lực nếu cận và incumbent đều hợp lệ.
13. Có tối đa `O(2^n)` nút và tính một bound có thể quét `O(n)` món, tổng `O(n2^n)`. Bộ nhớ DFS `O(n)` ngoài dữ liệu.
14. Với từng tiền tố quyết định, vét cạn mọi cách lấy/bỏ phần còn lại, chỉ giữ các hoàn tất vừa sức và tìm lợi ích thật tối ưu. Khẳng định `upperBound(node)≥trueBestCompletion`.
15. **Có.** Nếu chỉ so tiêu chí lợi ích và cắt khi UB bằng bestValue, ta có thể bỏ nghiệm cùng lợi ích nhưng nhẹ hơn. Cần điều kiện hòa giữ nhánh còn cơ hội cải thiện tiêu chí phụ hoặc xây cận/so sánh theo mục tiêu từ điển hai tiêu chí.

---

## Ghi nhớ

**Nhánh và cận** chỉ cắt nhánh khi có **chứng minh** rằng không lời giải nào trong nhánh còn khả năng thắng **nghiệm khả thi tốt nhất hiện có (incumbent)**.

- **Cực tiểu:** incumbent là một **cận trên toàn cục**, còn mỗi nhánh cần một **cận dưới**; cắt khi `LB(N)≥incumbent`.
- **Cực đại:** incumbent là một **cận dưới toàn cục**, còn mỗi nhánh cần một **cận trên**; cắt khi `UB(N)≤incumbent`.
- **Incumbent phải là nghiệm thật và khả thi**; heuristic/greedy có thể giúp khởi tạo nó nhưng không tự chứng minh tối ưu.
- **Cận phải đúng chiều với mọi phần tiếp nối**. Một cận nới lỏng như ba lô phân số có thể quá lạc quan nhưng vẫn an toàn; cận sai có thể loại mất nghiệm tối ưu.
- **Cập nhật incumbent càng sớm và tính cận càng chặt** thường giúp giảm lượng tìm kiếm, nhưng worst-case vẫn có thể theo hàm mũ.
- Nếu cần **mọi nghiệm hòa** hoặc tối ưu thêm tiêu chí phụ, không được mặc định cắt khi cận **bằng** incumbent.
- Khi tất cả các nhánh đã xét hoặc được cắt đúng, nghiệm khả thi tốt nhất còn giữ là **nghiệm tối ưu toàn cục**. Khi dừng sớm, cần báo cả incumbent và cận còn mở thay vì tuyên bố tối ưu khi chưa chứng minh.
