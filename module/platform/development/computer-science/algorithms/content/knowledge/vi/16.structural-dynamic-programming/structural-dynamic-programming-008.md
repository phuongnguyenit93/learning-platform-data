# Bài toán người du lịch trên tập đỉnh nhỏ

## Mục tiêu học tập

**Bài toán người du lịch** (*Traveling Salesperson Problem — TSP*) yêu cầu tìm một hành trình có tổng chi phí nhỏ nhất, xuất phát từ một thành phố, **đi qua mỗi thành phố đúng một lần** rồi **quay về nơi xuất phát**. Trong phiên bản tổng quát, đây là bài toán tối ưu tổ hợp rất khó khi số đỉnh lớn. Tuy nhiên, nếu tập đỉnh cần xét **nhỏ**, ta có thể dùng **quy hoạch động trên tập con — bitmask DP**, thường được gọi là **thuật toán Held–Karp**.

Sau bài này, bạn sẽ:

1. Phát biểu TSP chính xác trên đồ thị có hướng/không hướng, trọng số và cạnh có thể thiếu.
2. Hiểu vì sao thử hết thứ tự thăm đỉnh có độ phức tạp giai thừa và khi nào bitmask DP phù hợp.
3. Biểu diễn tập đỉnh đã thăm bằng một số nguyên `mask`; kiểm tra, thêm và bỏ đỉnh bằng phép toán bit.
4. Xây công thức `dp[mask][v]` — chi phí nhỏ nhất xuất phát từ 0, thăm đúng tập `mask` và kết thúc ở `v`.
5. Hiểu điều kiện khởi tạo, chuyển trạng thái, đóng chu trình và cách xử lý trạng thái không thể đạt.
6. Chứng minh tính đúng bằng **nguyên lý tối ưu Bellman** và quy nạp theo kích thước tập đã thăm.
7. Phân tích `O(n²2^n)` thời gian, `O(n2^n)` bộ nhớ, cùng các giới hạn thực tế.
8. Khôi phục **một chu trình tối ưu thực sự**, không chỉ giá trị chi phí.
9. Cài đặt chương trình **Java 17+** hoàn chỉnh; kiểm thử với trọng số không đối xứng, không có chu trình, số đỉnh 1 và 2.
10. Phân biệt TSP với đường đi ngắn nhất, đường Hamilton không quay về, TSP trên các điểm quan trọng và những biến thể có ràng buộc khác.

---

## 1. Định nghĩa chính xác bài toán

Cho một đồ thị có `n` đỉnh, đánh số từ `0` tới `n-1`. Gọi:

\[
w[u][v]=\text{chi phí đi trực tiếp từ đỉnh }u\text{ đến đỉnh }v.
\]

Trong ví dụ Java, `w[u][v]` là **số nguyên không âm**; giá trị `-1` nghĩa là **không có cạnh trực tiếp**. Trọng số 0 vẫn là một cạnh hợp lệ.

Ta cần tìm thứ tự các đỉnh:

\[
(0,v_1,v_2,\ldots,v_{n-1},0)
\]

sao cho:

- `v_1,\ldots,v_{n-1}` là một hoán vị của tất cả đỉnh khác 0.
- Mỗi cặp liên tiếp trong hành trình có **cạnh hợp lệ**.
- Hành trình kết thúc tại 0.
- Tổng chi phí là nhỏ nhất:

\[
\operatorname{cost}=
w[0][v_1]+
\sum_{i=1}^{n-2}w[v_i][v_{i+1}]+w[v_{n-1}][0].
\]

Chu trình thỏa các điều kiện này là **một tour Hamilton** (theo quy ước chu trình TSP), và bài toán tối ưu chọn tour có chi phí nhỏ nhất.

### 1.1. Vì sao cố định đỉnh bắt đầu là 0?

Một chu trình đi qua mọi đỉnh có thể được viết bắt đầu từ bất kỳ đỉnh nào bằng cách **xoay vị trí xuất phát**. Vì thế, đối với bài toán tìm **chu trình khép kín** không có ràng buộc riêng theo thời điểm hay điểm xuất phát, chọn đỉnh 0 làm điểm bắt đầu **không loại bỏ nghiệm tối ưu**.

Điều này giúp trạng thái DP đơn giản hơn: bit của đỉnh 0 luôn được bật. Nếu đề bài ấn định xuất phát ở một đỉnh khác `s`, có thể thay 0 bằng s trong toàn bộ công thức hoặc đổi nhãn đỉnh.

**Cẩn thận:** với bài toán **đường đi Hamilton không cần quay về**, điểm bắt đầu có thể ảnh hưởng đáp án. Không tự cố định 0 nếu đề yêu cầu chọn tự do điểm xuất phát và kết thúc cho một đường đi không khép kín.

### 1.2. Có hướng và không hướng

- **Đồ thị có hướng (asymmetric TSP):** `w[u][v]` có thể khác `w[v][u]`. Tour đi chiều ngược có thể tốn chi phí khác hoặc không tồn tại.
- **Đồ thị vô hướng (symmetric TSP):** mỗi cạnh có chi phí như nhau ở hai chiều, thường biểu diễn bằng ma trận đối xứng `w[u][v]=w[v][u]`.
- **Không đầy đủ:** có thể thiếu cạnh. Khi đó một thứ tự đỉnh có thể **không hợp lệ**, và thậm chí toàn bộ bài toán không có tour Hamilton.
- **Đồ thị đầy đủ:** mọi cặp đỉnh khác nhau đều có cạnh. Khi `n≥2`, luôn có thể viết thứ tự thăm tất cả đỉnh rồi quay về theo cạnh có sẵn.

Trong một chương trình quản lý tuyến đường thực tế, chi phí có thể là quãng đường, thời gian, năng lượng hoặc một đại lượng khác. Hợp đồng phải nói rõ **được phép đi qua đỉnh nào, có được quay lại đỉnh trung gian không và chi phí cạnh có thỏa các giả thiết cần dùng hay không**.

### 1.3. TSP khác bài toán đường đi ngắn nhất

Đường đi ngắn nhất từ `u` đến `v` thường chỉ yêu cầu **đến đích với chi phí nhỏ nhất**, không bắt buộc thăm mọi đỉnh. Trong đồ thị có trọng số không âm, Dijkstra là một lựa chọn quen thuộc cho đường đi ngắn nhất từ một nguồn.

TSP lại yêu cầu **thăm tất cả đỉnh đúng một lần và quay về**. Vì vậy trạng thái chỉ gồm “đang ở đỉnh v” là **chưa đủ**: hai hành trình cùng kết thúc tại v nhưng đã thăm các tập đỉnh khác nhau có những lựa chọn tiếp theo khác nhau.

Muốn giải TSP chính xác cần lưu cả **tập đã thăm**. Đây chính là cơ sở của `dp[mask][v]`.

---

## 2. Ví dụ trực quan với bốn thành phố

Giả sử bốn thành phố `0,1,2,3` có ma trận chi phí đối xứng:

| Từ / đến | 0 | 1 | 2 | 3 |
| --- | ---: | ---: | ---: | ---: |
| **0** | 0 | 10 | 15 | 20 |
| **1** | 10 | 0 | 35 | 25 |
| **2** | 15 | 35 | 0 | 30 |
| **3** | 20 | 25 | 30 | 0 |

Một tour:

```text
0 -> 1 -> 2 -> 3 -> 0
10 + 35 + 30 + 20 = 95
```

Một tour tốt hơn:

```text
0 -> 2 -> 3 -> 1 -> 0
15 + 30 + 25 + 10 = 80
```

Một tour khác có cùng chi phí:

```text
0 -> 1 -> 3 -> 2 -> 0
10 + 25 + 30 + 15 = 80
```

Đáp án tối ưu là **80**. Có **nhiều tour tối ưu**; thuật toán không cần chọn một tour duy nhất trừ khi đặc tả có quy tắc phá hòa.

### 2.1. Vì sao số phương án tăng rất nhanh?

Với điểm xuất phát cố định là 0, có `(n-1)!` hoán vị của `n-1` đỉnh còn lại. Trên đồ thị có hướng, về cơ bản phải xem xét tới `(n-1)!` thứ tự nếu vét cạn trực tiếp.

| n | Số thứ tự thăm với điểm đầu cố định, `(n-1)!` |
| ---: | ---: |
| 4 | 6 |
| 8 | 5.040 |
| 10 | 362.880 |
| 12 | 39.916.800 |
| 15 | 87.178.291.200 |
| 20 | 121.645.100.408.832.000 |

Với đồ thị **vô hướng** và `n≥3`, hai hướng đi ngược trên cùng chu trình thường tương đương khi chỉ đếm chu trình không phân biệt chiều; có thể chia đôi số chu trình khác nhau. Nhưng dù có giảm hệ số 2, số phương án vẫn tăng **giai thừa**.

Vét cạn có thể dùng cho n rất nhỏ và có ưu điểm dễ kiểm chứng. Nhưng khi n tăng, ta cần khai thác **các bài toán con lặp lại**: rất nhiều thứ tự thăm khác nhau dẫn đến **cùng một tập đỉnh đã thăm và cùng một đỉnh kết thúc**.

---

## 3. Nhận diện trạng thái lặp: tập đã thăm và đỉnh cuối

Xét hai đường đi từ 0:

```text
0 -> 1 -> 2 -> 3
0 -> 2 -> 1 -> 3
```

Cả hai đều:

- Đã thăm tập `{0,1,2,3}`.
- Đang ở đỉnh `3`.
- Còn cùng một tập đỉnh chưa thăm.

Giả sử đường thứ nhất có chi phí lớn hơn đường thứ hai. Khi hai đường đã thăm **đúng cùng tập** và đều kết thúc tại `3`, **mọi cách đi tiếp hợp lệ** của chúng đều giống nhau về khả năng chọn đỉnh mới. Vì thế ta chỉ cần giữ đường có chi phí nhỏ hơn.

Đây là tính **trạng thái trội** trong quy hoạch động:

> Với cùng cặp **(tập đỉnh đã thăm, đỉnh cuối)**, một hành trình có chi phí cao hơn không thể trở thành phương án tối ưu nhờ bất kỳ phần tiếp nối hợp lệ nào, vì chi phí tiếp nối phụ thuộc vào trạng thái hiện tại chứ không phụ thuộc thứ tự đã đi trước đó.

Chính nhờ việc **gộp nhiều hoán vị vào cùng một trạng thái** mà bitmask DP tránh được duyệt toàn bộ `(n-1)!` hoán vị.

### 3.1. Vì sao chỉ lưu tập đỉnh là chưa đủ?

Giả sử đã thăm `{0,1,2}`. Nếu đang ở `1`, chi phí đi tiếp đến `3` là `w[1][3]`; nếu đang ở `2`, chi phí đi tiếp là `w[2][3]`. Chúng có thể khác nhau.

Vì vậy trạng thái phải nhớ cả **đỉnh cuối**. `dp[mask]` chỉ lưu một giá trị cho tập `mask` mà không ghi đỉnh cuối thường **không đủ thông tin** để tính đúng bước tiếp theo.

### 3.2. Vì sao không cần lưu toàn bộ thứ tự đã thăm?

Để tính chi phí đi tiếp, ta chỉ cần biết:

- Đỉnh nào **chưa** thăm, để tránh lặp.
- Đang ở **đỉnh nào**, để lấy trọng số cạnh tiếp theo.

Tổng chi phí tốt nhất đã đạt được được lưu ngay trong DP. Toàn bộ thứ tự trước đó chỉ cần thêm nếu đề bài muốn **khôi phục tour**, khi ấy ta lưu con trỏ cha thay vì đưa toàn bộ chuỗi đường đi vào mỗi trạng thái.

---

## 4. Biểu diễn tập đỉnh bằng bitmask

Với `n` đỉnh, một số nguyên `mask` có n bit thấp đại diện cho tập:

- Bit thứ i bằng `1`: đỉnh i **đã được thăm**.
- Bit thứ i bằng `0`: đỉnh i **chưa được thăm**.

Ví dụ có bốn đỉnh:

```text
Các bit:     3 2 1 0
mask = 0001  => đã thăm {0}
mask = 0101  => đã thăm {0,2}
mask = 1101  => đã thăm {0,2,3}
mask = 1111  => đã thăm {0,1,2,3}
```

Trong Java với `int`:

| Thao tác | Biểu thức | Ý nghĩa |
| --- | --- | --- |
| Mask chỉ gồm đỉnh 0 | `1 << 0` | `000...001` |
| Kiểm tra i đã thăm | `(mask & (1 << i)) != 0` | Bit i bật |
| Kiểm tra i chưa thăm | `(mask & (1 << i)) == 0` | Bit i tắt |
| Thêm đỉnh i | `mask \| (1 << i)` | Bật bit i |
| Bỏ đỉnh i, khi biết i đã thăm | `mask ^ (1 << i)` | Lật bit i từ 1 về 0 |
| Mask gồm mọi đỉnh | `(1 << n) - 1` | n bit thấp đều bằng 1 |

**Chú ý:** dùng XOR (`^`) để **bỏ** đỉnh chỉ đúng khi bit đó **đang bằng 1**; nếu bit chưa bật, XOR sẽ **thêm** đỉnh thay vì bỏ. Cách xóa bit an toàn hơn khi không biết trước trạng thái là `mask & ~(1 << i)`.

Nếu mask đang là `0101` và muốn thêm đỉnh 3:

```text
0101 | 1000 = 1101
```

### 4.1. Số lượng tập con

Mỗi đỉnh có hai trạng thái “đã thăm/chưa thăm”, nên có `2^n` mask. Nhưng vì bắt đầu ở 0 và không rời rồi quay lại sớm, mọi trạng thái hợp lệ của hành trình từ 0 đều phải **chứa bit 0**. Số mask chứa 0 là `2^{n-1}`.

Đối với mỗi mask, có tối đa n lựa chọn đỉnh cuối, nên có chặn `O(n2^n)` trạng thái. Không phải tất cả trạng thái đều khả đạt hoặc có ý nghĩa, nhưng cấp phát mảng hai chiều `dp[1<<n][n]` thường là cách cài dễ hiểu cho n nhỏ.

### 4.2. Giới hạn của `1 << n` trong Java

Kiểu `int` có 32 bit và biểu thức shift của Java chỉ dùng 5 bit thấp của số dịch đối với `int`. Ví dụ `1 << 32` **không** tạo `2^{32}` mà có hành vi tương đương dịch 0 bit. Với `n=31`, `1 << n` còn đổi dấu.

Do đó:

- Không dùng `1 << n` tùy tiện khi n lớn.
- Nếu cần biểu diễn mask tới hơn 30 đỉnh bằng `long`, vẫn phải xét giới hạn shift của `long` và **đặc biệt** là bộ nhớ DP `2^n`, vốn đã không khả thi từ lâu.
- Chương trình Java của bài giới hạn `1≤n≤16` để minh họa an toàn với một máy thông thường. Đây là **giới hạn triển khai mẫu**, không phải ranh giới toán học cố định của thuật toán.

Không được nghĩ “n chỉ 40 nên dùng `long` là giải xong”: `2^{40}` tập con đã quá lớn cho một DP bảng đầy đủ trong thực tế.

---

## 5. Trạng thái Held–Karp và công thức quy hoạch động

Định nghĩa:

\[
dp[mask][v]
=\text{chi phí nhỏ nhất của một đường đi bắt đầu tại 0,}
\]

\[
\text{thăm đúng các đỉnh trong }mask\text{, kết thúc tại }v.
\]

Trong định nghĩa này:

- Bit 0 phải bật trong `mask`.
- Bit v phải bật trong `mask`.
- Mỗi đỉnh thuộc mask được thăm **đúng một lần**.
- Đường đi **chưa đóng chu trình về 0**, trừ trường hợp khởi tạo đơn lẻ.
- Nếu không có đường đi thỏa mãn, giá trị là `INF`.

### 5.1. Khởi tạo

Ta bắt đầu ở đỉnh 0, chưa đi cạnh nào:

\[
\boxed{dp[1<<0][0]=0}.
\]

Mọi trạng thái còn lại khởi tạo bằng `INF`.

Ví dụ n=4:

```text
dp[0001][0] = 0
dp[0011][1] = INF lúc đầu
dp[0101][2] = INF lúc đầu
...
```

Ta không mở rộng một tour đã quay về 0 trong quá trình DP. Đỉnh 0 chỉ xuất hiện là **đỉnh cuối ở trạng thái khởi tạo**, rồi các bước tiếp theo chỉ thêm đỉnh khác 0. Việc quay về 0 được xét **duy nhất ở bước kết thúc**.

### 5.2. Công thức chuyển theo đỉnh trước

Với `v≠0` và `v∈mask`:

\[
\boxed{
dp[mask][v]
=
\min_{\substack{u\in mask\setminus\{v\}\\
(u,v)\text{ có cạnh}}}
\left(
dp[mask\setminus\{v\}][u]+w[u][v]
\right).
}
\]

Ý nghĩa:

1. Chọn đỉnh `u` ngay trước đỉnh cuối `v`.
2. Phần đường đi trước cạnh `u→v` đã thăm đúng `mask\setminus\{v\}` và kết thúc tại u.
3. Nếu phần trước có chi phí tối ưu là `dp[mask\setminus\{v\}][u]`, thêm cạnh `u→v` tạo ứng viên cho `dp[mask][v]`.
4. Lấy min trên các u hợp lệ.

Nếu mọi ứng viên đều `INF` hoặc không có cạnh hợp lệ, trạng thái đích không thể đạt.

### 5.3. Dạng chuyển tiến trong chương trình

Thực tế code thường duyệt mask từ nhỏ tới lớn và **mở rộng**:

\[
\boxed{
dp[mask\cup\{v\}][v]
=
\min\left(
dp[mask\cup\{v\}][v],
dp[mask][u]+w[u][v]
\right)
}
\]

với điều kiện:

- `dp[mask][u]` hữu hạn.
- `u∈mask`.
- `v∉mask`.
- `v≠0`.
- Có cạnh `u→v`.

Dạng này tương đương với công thức chọn đỉnh trước: ta chỉ viết các ứng viên theo thứ tự **trạng thái nguồn → trạng thái đích**.

Khi thêm một đỉnh v chưa thăm, giá trị mask mới luôn lớn hơn mask cũ vì bật một bit 0 thành 1. Bởi vậy, nếu duyệt mask tăng dần, mọi trạng thái nguồn cần thiết sẽ được xử lý trước khi mở rộng trạng thái đích; ta cũng có thể duyệt theo **số bit bật** để thể hiện rõ thứ tự tập con.

### 5.4. Bước kết thúc: đóng chu trình

Đặt:

\[
FULL=(1<<n)-1.
\]

Sau khi đã thăm tất cả đỉnh, đường đi đang kết thúc ở một đỉnh `v≠0`. Phải **thêm chi phí cạnh quay về 0**:

\[
\boxed{
OPT=\min_{\substack{1\le v<n\\
dp[FULL][v]<INF\\
(v,0)\text{ có cạnh}}}
\left(dp[FULL][v]+w[v][0]\right).
}
\]

Nếu không có v thỏa mãn, bài toán không có tour Hamilton theo các cạnh hợp lệ.

**Lỗi rất thường gặp:** trả ngay `min_v dp[FULL][v]` mà **quên cạnh quay về 0**. Khi đó đang giải bài toán **đường đi thăm đủ đỉnh** chứ không phải TSP chu trình.

Đối với n=1, chương trình mẫu quy ước hành trình tầm thường `[0,0]` có chi phí **0**, không cần cạnh tự khép `0→0`. Đối với n≥2, bước đóng chu trình như công thức trên là bắt buộc.

---

## 6. Minh họa trạng thái trên ma trận bốn đỉnh

Dùng lại ma trận:

```text
        0   1   2   3
0:      0  10  15  20
1:     10   0  35  25
2:     15  35   0  30
3:     20  25  30   0
```

Khởi tạo:

```text
dp[0001][0] = 0
```

Từ đỉnh 0, đi đến mỗi đỉnh khác:

```text
dp[0011][1] = 10     Tour tạm: 0 -> 1
dp[0101][2] = 15     Tour tạm: 0 -> 2
dp[1001][3] = 20     Tour tạm: 0 -> 3
```

Từ trạng thái `dp[0101][2]=15` (đã thăm 0,2; đang ở 2), có thể thêm 3:

```text
newMask = 0101 | 1000 = 1101
candidate = dp[0101][2] + w[2][3]
          = 15 + 30
          = 45

dp[1101][3] = 45   // 0 -> 2 -> 3
```

Sau đó thêm đỉnh 1:

```text
newMask = 1101 | 0010 = 1111
candidate = dp[1101][3] + w[3][1]
          = 45 + 25
          = 70

dp[1111][1] = 70   // 0 -> 2 -> 3 -> 1
```

Khi đóng chu trình:

```text
dp[1111][1] + w[1][0] = 70 + 10 = 80
```

Các đỉnh cuối khác cho:

| Đỉnh cuối v | `dp[1111][v]` | Chi phí `w[v][0]` | Tổng tour |
| ---: | ---: | ---: | ---: |
| 1 | 70 | 10 | **80** |
| 2 | 65 | 15 | **80** |
| 3 | 75 | 20 | 95 |

Vì thế `OPT=80`. Nếu duyệt đỉnh cuối theo thứ tự tăng và chỉ cập nhật khi chi phí **nhỏ hơn nghiêm ngặt**, chương trình có thể chọn v=1, dẫn đến tour:

```text
0 -> 2 -> 3 -> 1 -> 0
Tổng chi phí = 15 + 30 + 25 + 10 = 80
```

Nhận xét: nhiều đường đi dẫn đến cùng trạng thái `dp[mask][v]`, nhưng chỉ giữ **chi phí tốt nhất** là đủ cho mục tiêu tối thiểu; những đường đắt hơn sẽ không đem lại phần tiếp nối có lợi thế vì đều có cùng đỉnh cuối và tập đỉnh còn lại.

---

## 7. Cài đặt bitmask DP bằng giả mã

```text
TSP_HELD_KARP(w, n):
    yêu cầu: 1 <= n; w là ma trận n x n
    nếu n == 1:
        return (cost=0, tour=[0,0])

    FULL = (1 << n) - 1

    tạo dp[0..FULL][0..n-1], điền INF
    dp[1][0] = 0

    for mask từ 1 đến FULL:
        if bit 0 của mask chưa bật:
            continue

        for u từ 0 đến n-1:
            if u chưa thuộc mask hoặc dp[mask][u] == INF:
                continue

            for v từ 1 đến n-1:
                if v đã thuộc mask:
                    continue
                if cạnh (u,v) không tồn tại:
                    continue

                next = mask | (1 << v)
                dp[next][v] = min(
                    dp[next][v],
                    dp[mask][u] + w[u][v]
                )

    answer = INF
    for v từ 1 đến n-1:
        if dp[FULL][v] hữu hạn và có cạnh (v,0):
            answer = min(answer, dp[FULL][v] + w[v][0])

    nếu answer == INF: return không có tour
    return answer
```

Đây là bản chỉ tính chi phí. Để **khôi phục tour**, ta cần lưu `parent[next][v]=u` mỗi khi một ứng viên **cải thiện** `dp[next][v]`. Nếu hai ứng viên bằng nhau, có thể giữ cha cũ để kết quả xác định theo thứ tự duyệt.

### 7.1. Bất biến khi mở rộng trạng thái

Mỗi trạng thái hữu hạn `dp[mask][u]` phải biểu diễn một đường đi hợp lệ:

- Bắt đầu tại 0.
- Đã thăm **đúng** các đỉnh có bit bật.
- Không lặp đỉnh.
- Đang ở u.
- Có tổng chi phí bằng giá trị lưu.

Khi chọn `v∉mask` và có cạnh `u→v`, nối v tạo một đường đi hợp lệ cho `nextMask`. Vì mọi trạng thái trước đó đã đúng, việc chuyển trạng thái không thể tự tạo ra một đường đi lặp đỉnh hoặc dùng cạnh thiếu.

Tuy nhiên **tính hợp lệ** chưa đủ để suy ra **tính tối ưu**; điều đó cần chứng minh dùng tất cả lựa chọn đỉnh trước, trình bày ở mục 9.

### 7.2. Các phép kiểm tra phải làm trước phép cộng

Không thực hiện:

```text
candidate = INF + w[u][v]
```

rồi hy vọng kết quả tự mang nghĩa vô hạn. Với số nguyên hữu hạn, phép cộng có thể **tràn số** và cho một giá trị âm nhỏ, làm DP ghi nhận nghiệm giả.

Hãy kiểm tra:

1. Trạng thái nguồn có hữu hạn không?
2. Cạnh `u→v` có tồn tại không?
3. Trọng số tổng có nằm trong phạm vi kiểu số không?

Chương trình Java chọn sentinel `INF` lớn và **giới hạn trọng số hợp lệ** để mọi đường đi/tour được xem xét có chi phí nhỏ hơn `INF`. Nhờ đó có thể cộng `long` mà không nhầm trạng thái không thể đạt với chi phí hợp lệ.

---

## 8. Khôi phục tour tối ưu bằng parent

Khi chỉ cần **giá trị chi phí**, đủ dùng `dp`. Nhưng nhiều đề yêu cầu in hành trình, tức một hoán vị đỉnh hợp lệ quay về 0.

Thêm mảng:

\[
parent[mask][v]=u
\]

nghĩa là: trong đường đi tối ưu đang lưu cho `dp[mask][v]`, đỉnh ngay trước v là u.

Mỗi khi cập nhật tốt hơn:

```text
if candidate < dp[nextMask][v]:
    dp[nextMask][v] = candidate
    parent[nextMask][v] = u
```

Sau khi tìm được đỉnh cuối `last` tạo tổng tour nhỏ nhất, bắt đầu từ:

```text
mask = FULL
current = last
```

Lần ngược:

1. Ghi current vào cuối phần hành trình chưa dựng.
2. Lấy `previous=parent[mask][current]`.
3. Bỏ current khỏi mask: `mask ^= (1<<current)`.
4. Đặt `current=previous`.
5. Lặp đến khi đã truy ngược về đỉnh 0.

Cuối cùng thêm 0 ở **hai đầu** của biểu diễn chu trình.

### 8.1. Ví dụ truy vết

Trên ma trận bốn thành phố, giả sử nghiệm được chọn có đỉnh cuối `last=1`:

```text
mask 1111, current 1
parent[1111][1] = 3
=> bỏ bit 1, mask thành 1101

mask 1101, current 3
parent[1101][3] = 2
=> bỏ bit 3, mask thành 0101

mask 0101, current 2
parent[0101][2] = 0
=> bỏ bit 2, mask thành 0001

current = 0; dừng
```

Các đỉnh được truy ngược là `1,3,2`; đảo ngược và ghép điểm đầu/cuối:

```text
[0, 2, 3, 1, 0]
```

### 8.2. Vì sao không thể chỉ nhớ đỉnh cuối?

Nếu lưu mỗi `last` mà không lưu `parent`, ta biết tour kết thúc ở đỉnh nào nhưng **không biết thứ tự đỉnh trước đó** đã tạo nên chi phí tối ưu. Có thể tái tính một số trạng thái để khôi phục, nhưng bản truy vết trực tiếp cần lưu quan hệ cha (hoặc thông tin tương đương).

Mảng `parent` bổ sung `O(n2^n)` bộ nhớ trong cách cài mảng đầy đủ. Khi n đã ở giới hạn bộ nhớ, việc lưu cả `dp` và `parent` có thể là nguyên nhân chính làm chương trình không chạy được; lúc đó phải cân nhắc chỉ trả chi phí, nén bộ nhớ hoặc tính lại phần đường đi.

---

## 9. Chứng minh Held–Karp cho đáp án tối ưu

Để chứng minh đúng, ta sử dụng **quy nạp theo số đỉnh đã thăm**.

### 9.1. Mệnh đề

Với mỗi trạng thái hợp lệ chứa đỉnh 0 và đỉnh cuối v, `dp[mask][v]` bằng chi phí nhỏ nhất của mọi đường đi:

- Bắt đầu ở 0.
- Đi qua **mỗi đỉnh trong mask đúng một lần**.
- Không đi qua đỉnh ngoài mask.
- Kết thúc tại v.

Nếu không có đường đi hợp lệ, trạng thái mang giá trị `INF`.

### 9.2. Cơ sở

Khi `mask={0}` và `v=0`, đường đi chỉ gồm đỉnh 0, chưa dùng cạnh, có chi phí 0. Vì vậy:

\[
dp[\{0\}][0]=0
\]

là chính xác. Các trạng thái khác có cùng tập `{0}` nhưng đỉnh cuối không phải 0 là không hợp lệ và giữ `INF`.

### 9.3. Bước quy nạp

Giả sử mệnh đề đúng cho mọi tập đã thăm chứa ít hơn k đỉnh. Xét trạng thái `dp[S][v]` với `|S|=k` và `v≠0`.

Bất kỳ đường đi hợp lệ nào cho trạng thái này đều có một **đỉnh áp chót u** thuộc `S\setminus\{v\}` và một cạnh cuối `u→v`. Phần đường đi trước cạnh cuối:

- Bắt đầu ở 0.
- Thăm đúng `S\setminus\{v\}`.
- Kết thúc ở u.

Theo giả thiết quy nạp, chi phí phần đó **không thể nhỏ hơn** `dp[S\setminus\{v\}][u]`.

Vì vậy chi phí mọi đường đi tới `(S,v)` bị chặn dưới bởi một ứng viên:

\[
dp[S\setminus\{v\}][u]+w[u][v].
\]

Ngược lại, nếu trạng thái tiền nhiệm hữu hạn và cạnh `u→v` tồn tại, ta có thể nối v vào đường đi tối ưu của trạng thái tiền nhiệm để tạo một đường đi **hợp lệ** với chi phí **đúng bằng ứng viên**.

Do đó, lấy min trên **tất cả** u hợp lệ cho đúng chi phí tối ưu của `dp[S][v]`. Mệnh đề được chứng minh cho tập có k đỉnh.

### 9.4. Đóng chu trình

Một tour Hamilton bất kỳ n≥2 phải có một đỉnh `v≠0` đứng ngay trước khi quay về 0.

- Bỏ **cạnh cuối `v→0`** khỏi tour, ta được một đường đi thăm tất cả đỉnh và kết thúc ở v.
- Chi phí của đường đi ấy không thể nhỏ hơn `dp[FULL][v]`.
- Ngược lại, bất kỳ đường đi tối ưu `dp[FULL][v]` nào có thêm cạnh `v→0` hợp lệ đều tạo một tour.

Vậy lấy min `dp[FULL][v]+w[v][0]` qua mọi v có cạnh quay về 0 là **đúng chi phí TSP tối ưu**. Nếu không có ứng viên hữu hạn, không tồn tại tour.

### 9.5. Tính dừng

Có hữu hạn `2^n` mask, mỗi mask xét hữu hạn n đỉnh cuối và n đỉnh kế tiếp. Mỗi chuyển trạng thái luôn **bật thêm một bit** nên không thể quay lại một trạng thái có ít đỉnh đã thăm hơn. Vòng tính DP kết thúc.

Lần ngược parent có tối đa `n-1` bước; mỗi bước bỏ đúng bit của đỉnh hiện tại và đi đến một chỉ số tiền nhiệm trong tập còn lại, nên cũng kết thúc.

---

## 10. Phân tích độ phức tạp

### 10.1. So sánh với vét cạn

Vét cạn thứ tự thăm:

\[
\text{Số hoán vị}=(n-1)!.
\]

Nếu tính tổng tour từ đầu cho mỗi hoán vị thì có thêm yếu tố n; nếu cập nhật chi phí khi backtrack, thời gian vẫn có tăng trưởng **giai thừa** theo n.

Bitmask DP dùng nhiều nhất `n2^n` trạng thái. Với mỗi trạng thái `(mask,u)`, thử tối đa n đỉnh v chưa thăm:

\[
\boxed{\text{Thời gian }O(n^2 2^n)}.
\]

Lưu `dp[mask][v]` cho mỗi trạng thái:

\[
\boxed{\text{Bộ nhớ }O(n2^n)}.
\]

Nếu lưu `parent[mask][v]` cùng `dp`, bậc bộ nhớ vẫn `O(n2^n)` nhưng **hằng số tăng đáng kể**.

### 10.2. Tại sao gọi là quy hoạch động trên tập con?

Chỉ số mask chạy qua **các tập con** của tập đỉnh. Mỗi trạng thái kết hợp một tập con và đỉnh cuối, chuyển tới tập con lớn hơn một phần tử. Đây là quy hoạch động trên cấu trúc tổ hợp, thay vì trên một chỉ số tuyến tính hay số tiền.

Hàm `dp[S][v]` gộp nhiều đường đi đã dùng **chính xác tập S** vào một kết quả tốt nhất. Khai thác các trạng thái lặp này làm số bài toán con giảm từ rất nhiều **hoán vị** xuống số cặp **(tập con, đỉnh cuối)**.

### 10.3. Bảng ước lượng bộ nhớ

Nếu cấp phát một giá trị `long` và một chỉ số `int` cho mỗi ô `(mask,v)`, chỉ tính dung lượng phần tử lý thuyết, chưa tính overhead mảng Java:

| n | Số mask `2^n` | Số ô `n2^n` | `dp` long[] (8 byte/ô) | `parent` int[] (4 byte/ô) |
| ---: | ---: | ---: | ---: | ---: |
| 10 | 1.024 | 10.240 | khoảng 80 KiB | khoảng 40 KiB |
| 15 | 32.768 | 491.520 | khoảng 3,75 MiB | khoảng 1,88 MiB |
| 16 | 65.536 | 1.048.576 | khoảng 8 MiB | khoảng 4 MiB |
| 20 | 1.048.576 | 20.971.520 | khoảng 160 MiB | khoảng 80 MiB |

**Trong Java thực tế**, mảng hai chiều là mảng chứa các tham chiếu tới các mảng con; object header, căn chỉnh, tham chiếu, GC và dữ liệu khác làm mức dùng RAM cao hơn số byte lý thuyết. Thời gian cũng tăng rất mạnh khi n tăng.

Đây là lý do nói thuật toán phù hợp với **tập đỉnh nhỏ**, thường ở mức khoảng **15–20** tùy giới hạn máy và bài toán, chứ không phải thuật toán mặc định cho hàng trăm thành phố.

### 10.4. Tối ưu bộ nhớ và cách cài

- **Chỉ cần chi phí:** có thể không lưu parent.
- **Theo lớp số bit bật:** giữ hai lớp DP liên tiếp theo số đỉnh đã thăm có thể giảm bộ nhớ ở một số cách tổ chức, nhưng truy vết sẽ khó hơn và vẫn có nhiều tập con ở lớp giữa.
- **Dùng map cho trạng thái thưa:** khi đồ thị thiếu nhiều cạnh, chỉ giữ trạng thái có thể đạt có thể tiết kiệm bộ nhớ; overhead hash map và độ phức tạp thực tế phải được tính.
- **Bỏ qua cạnh thiếu hoặc trạng thái INF:** không thay đổi đáp án và thường giảm công.
- **Đổi nhãn cố định đỉnh xuất phát:** không ảnh hưởng bậc độ phức tạp nhưng giúp loại các mask không có điểm bắt đầu.
- **Quay về đầu chỉ một lần:** không thêm các trạng thái lặp đỉnh 0 trước khi thăm đủ tập.

Không có tối ưu đơn giản nào khiến `O(n^2 2^n)` trở thành thuật toán đa thức theo n cho TSP tổng quát. Với n lớn cần cân nhắc phương pháp khác: branch and bound, cắt nhánh theo cận dưới, heuristic, local search, approximation trong điều kiện thích hợp hoặc giải tối ưu chuyên dụng.

---

## 11. Java 17+: Held–Karp có khôi phục tour

Chương trình sau dùng:

- Đỉnh bắt đầu **0**.
- Ma trận `long[][]` với chi phí nguyên **không âm**.
- Giá trị `-1` cho **cạnh không tồn tại**.
- **Không dùng cạnh tự khép** `w[i][i]` trong các chuyển trạng thái.
- **Có thể là đồ thị có hướng**: không ép ma trận đối xứng.
- Số đỉnh trong khoảng **1..16** để tránh cấp phát bảng quá lớn ở ví dụ.
- Sentinel `INF = Long.MAX_VALUE / 4`; đầu vào được kiểm tra để tổng tối đa n cạnh luôn **nhỏ hơn INF**. Nhờ đó phân biệt chi phí hợp lệ và trạng thái không thể đạt.
- Mảng `parent` để trả về một chu trình tối ưu `[0,...,0]`.

Tệp đầy đủ là **`TspBitmaskDemo.java`**.

```java
import java.util.Arrays;
import java.util.Objects;

public class TspBitmaskDemo {

    private static final long INF = Long.MAX_VALUE / 4;
    private static final int MAX_N = 16;

    public record TourResult(
            boolean possible,
            long cost,
            int[] route) {
    }

    private static void validate(long[][] w) {
        Objects.requireNonNull(w, "weight matrix");

        int n = w.length;
        if (n < 1 || n > MAX_N) {
            throw new IllegalArgumentException(
                    "n must be between 1 and " + MAX_N);
        }

        // A tour uses at most n edges. This strict bound
        // ensures valid total costs stay below INF.
        long maxSingleEdgeExclusive = INF / n;

        for (int u = 0; u < n; u++) {
            if (w[u] == null || w[u].length != n) {
                throw new IllegalArgumentException(
                        "matrix must be square");
            }

            for (int v = 0; v < n; v++) {
                long c = w[u][v];

                if (c < -1 || c >= maxSingleEdgeExclusive) {
                    throw new IllegalArgumentException(
                            "edge cost out of supported range");
                }
            }
        }
    }

    public static TourResult solve(long[][] w) {
        validate(w);
        int n = w.length;

        // Convention: the single-city tour costs zero.
        if (n == 1) {
            return new TourResult(
                    true, 0L, new int[]{0, 0});
        }

        int states = 1 << n;
        int full = states - 1;

        long[][] dp = new long[states][n];
        int[][] parent = new int[states][n];

        for (int mask = 0; mask < states; mask++) {
            Arrays.fill(dp[mask], INF);
            Arrays.fill(parent[mask], -1);
        }

        // Only the start city has been visited.
        dp[1][0] = 0;

        // Enumerate only masks whose bit 0 is set.
        for (int mask = 1; mask < states; mask += 2) {
            for (int last = 0; last < n; last++) {
                if ((mask & (1 << last)) == 0
                        || dp[mask][last] == INF) {
                    continue;
                }

                for (int next = 1; next < n; next++) {
                    if ((mask & (1 << next)) != 0) {
                        continue; // Already visited.
                    }

                    long edge = w[last][next];
                    if (edge == -1) {
                        continue; // No direct edge.
                    }

                    int nextMask = mask | (1 << next);
                    long candidate = dp[mask][last] + edge;

                    if (candidate < dp[nextMask][next]) {
                        dp[nextMask][next] = candidate;
                        parent[nextMask][next] = last;
                    }
                }
            }
        }

        // Complete the tour by returning to city 0.
        long best = INF;
        int finalCity = -1;

        for (int last = 1; last < n; last++) {
            if (dp[full][last] == INF || w[last][0] == -1) {
                continue;
            }

            long total = dp[full][last] + w[last][0];
            if (total < best) {
                best = total;
                finalCity = last;
            }
        }

        if (finalCity == -1) {
            return new TourResult(
                    false, -1L, new int[0]);
        }

        // Backtrack the optimal path in reverse order.
        int[] route = new int[n + 1];
        route[0] = 0;
        route[n] = 0;

        int mask = full;
        int current = finalCity;

        for (int pos = n - 1; pos >= 1; pos--) {
            route[pos] = current;

            int previous = parent[mask][current];
            mask ^= (1 << current);

            current = previous;
        }

        if (current != 0 || mask != 1) {
            throw new AssertionError("broken parent chain");
        }

        return new TourResult(true, best, route);
    }

    public static void main(String[] args) {
        long[][] symmetric = {
                {0, 10, 15, 20},
                {10, 0, 35, 25},
                {15, 35, 0, 30},
                {20, 25, 30, 0}
        };

        TourResult first = solve(symmetric);
        System.out.println(
                "Symmetric optimal cost: " + first.cost());
        System.out.println(
                "Symmetric tour: "
                        + Arrays.toString(first.route()));

        long[][] directed = {
                {0, 3, 8, 5},
                {5, 0, 2, 7},
                {1, 4, 0, 2},
                {6, 5, 3, 0}
        };

        TourResult second = solve(directed);
        System.out.println(
                "Directed optimal cost: " + second.cost());
        System.out.println(
                "Directed tour: "
                        + Arrays.toString(second.route()));

        long[][] impossible = {
                {0, 2, -1},
                {-1, 0, 3},
                {-1, -1, 0}
        };

        TourResult third = solve(impossible);
        System.out.println(
                "No cycle possible: " + third.possible());
        System.out.println(
                "No cycle route: "
                        + Arrays.toString(third.route()));

        long[][] twoCities = {
                {0, 7},
                {5, 0}
        };

        TourResult fourth = solve(twoCities);
        System.out.println(
                "Two cities cost: " + fourth.cost());
        System.out.println(
                "Two cities tour: "
                        + Arrays.toString(fourth.route()));

        TourResult single = solve(new long[][]{{0}});
        System.out.println(
                "One city cost: " + single.cost());
        System.out.println(
                "One city tour: "
                        + Arrays.toString(single.route()));
    }
}
```

Biên dịch và chạy trên **JDK 17+**:

```bash
javac TspBitmaskDemo.java
java TspBitmaskDemo
```

**Đầu ra chuẩn chính xác:**

```text
Symmetric optimal cost: 80
Symmetric tour: [0, 2, 3, 1, 0]
Directed optimal cost: 13
Directed tour: [0, 3, 1, 2, 0]
No cycle possible: false
No cycle route: []
Two cities cost: 12
Two cities tour: [0, 1, 0]
One city cost: 0
One city tour: [0, 0]
```

### 11.1. Giải thích các kết quả

**Ví dụ đối xứng:** `[0,2,3,1,0]` có chi phí:

\[
15+30+25+10=80.
\]

Một chu trình đảo chiều `[0,1,3,2,0]` cũng có chi phí 80. Do vòng xét đỉnh cuối theo thứ tự tăng và chỉ cập nhật khi ứng viên **nhỏ hơn** giá trị cũ, chương trình chọn một trong những lời giải tối ưu là `[0,2,3,1,0]`.

**Ví dụ có hướng:** `[0,3,1,2,0]` có chi phí:

\[
5+5+2+1=13.
\]

Đường quay về `2→0` chỉ tốn 1, còn đường khác có thể tốn nhiều hơn; không được thay `w[u][v]` bằng `w[v][u]` nếu ma trận không đối xứng.

**Không có tour:** đường duy nhất theo các cạnh dương có thể đi `0→1→2`, nhưng không có cạnh `2→0`. Vì phải quay về 0, bài toán **không có nghiệm**, nên `possible=false` và route rỗng. Không được trả chi phí 5 của đường `0→1→2` như một chu trình hợp lệ.

**Hai thành phố:** tour `0→1→0` có chi phí `7+5=12`. Với đồ thị có hướng, hai chiều có thể khác giá. Với đồ thị vô hướng hai đỉnh và một cạnh, quy ước “tour TSP đóng” đi qua cạnh đó theo hai chiều; nếu một đề yêu cầu **chu trình đơn theo định nghĩa đồ thị vô hướng** thì trường hợp n=2 có thể được xử lý theo quy ước khác.

**Một thành phố:** tour tầm thường `[0,0]` được định nghĩa là không di chuyển, chi phí 0. Đây là một quy ước lập trình phổ biến để tránh cần cạnh tự khép.

### 11.2. Vì sao đầu ra có tính xác định?

Trong chương trình:

- Mask được duyệt theo giá trị tăng, chỉ mask chứa đỉnh 0.
- Đỉnh cuối và đỉnh tiếp theo được duyệt theo chỉ số tăng.
- Một trạng thái chỉ cập nhật parent nếu `candidate < oldValue`, **không ghi đè khi bằng nhau**.
- Đỉnh cuối đóng chu trình cũng chỉ được thay khi tổng chi phí **nhỏ hơn nghiêm ngặt**.

Vì vậy với cùng ma trận và cùng quy tắc duyệt, chương trình chọn cùng một tour tối ưu. Nhưng **điều này không chứng minh tour được chọn là nhỏ nhất theo từ điển** trong tất cả tour tối ưu. Nếu bài yêu cầu quy tắc hòa phức tạp, cần bổ sung logic và chứng minh riêng.

### 11.3. Kiểu số, sentinel và giới hạn thực tế

`w[u][v]=-1` nghĩa là **không có cạnh**. Giá trị 0 là một cạnh chi phí 0 hợp lệ. Chương trình cấm các trọng số âm khác.

Dùng `INF=Long.MAX_VALUE/4` và giới hạn:

\[
0\le w[u][v]<\frac{INF}{n}
\]

cho các cạnh tồn tại. Vì một tour có tối đa n cạnh, mọi tổng chi phí hợp lệ được xem xét trong thuật toán nhỏ hơn INF. Việc cộng hai đại lượng `long` trong DP vì thế không tràn trong miền input được chấp nhận.

Đây là **giới hạn số học của chương trình minh họa**, không phải yêu cầu của bài toán TSP trên số nguyên nói chung. Nếu hệ thống cần trọng số cực lớn, có thể dùng kiểm tra tràn `Math.addExact` kết hợp biểu diễn reachability riêng hoặc `BigInteger`, và phải tránh sử dụng một giá trị hợp lệ làm sentinel.

Số đỉnh tối đa 16 là giới hạn minh họa để giữ bộ nhớ trong phạm vi tương đối hợp lý. Không nên bỏ giới hạn này mà không đo và tính lại `n2^n`, vì n tăng vài đơn vị có thể làm bộ nhớ tăng gấp nhiều lần.

---

## 12. Thiết kế kiểm thử đầy đủ

Một cài đặt TSP nên được kiểm thử cả **giá trị chi phí**, **tính hợp lệ của chu trình** và **trường hợp không có nghiệm**.

### 12.1. Các test biên

| Input | Kết quả mong đợi | Lưu ý |
| --- | --- | --- |
| Một thành phố `[[0]]` | Chi phí 0, tour `[0,0]` | Trường hợp đặc biệt theo quy ước |
| Hai thành phố `[[0,7],[5,0]]` | Chi phí 12, `[0,1,0]` | Cần cả hai hướng |
| 4 thành phố đối xứng ở mục 2 | Chi phí **80** | Có nhiều tour tối ưu |
| 4 thành phố có hướng ở mục 11 | Chi phí **13** | Không giả định hai chiều bằng nhau |
| 3 thành phố chỉ có `0→1→2` | Không có tour | Thiếu cạnh quay về 0 |
| Một số cạnh có trọng số 0 | Vẫn hợp lệ | 0 không phải sentinel |
| Đồ thị không có cạnh giữa các đỉnh khác nhau | Không có tour nếu `n≥2` | Không được trả chi phí 0 |
| Ma trận không vuông | Báo lỗi input | `w[u][v]` không được xác định đầy đủ |
| Trọng số `-2` | Báo lỗi input | Chỉ `-1` được dùng là cạnh thiếu |
| n=0 theo chương trình mẫu | Báo lỗi input | Không tự dùng `dp[1][0]` |
| n>16 theo chương trình mẫu | Báo lỗi input | Tránh quá hạn bộ nhớ demo |

### 12.2. Thuộc tính của tour hợp lệ

Với n≥2 và `result.possible()==true`:

1. `result.route().length==n+1`.
2. `route[0]==0` và `route[n]==0`.
3. Mỗi đỉnh trong `0..n-1` xuất hiện **đúng một lần** ở `route[0..n)`.
4. Mọi cạnh `route[i]→route[i+1]` tồn tại theo **đúng chiều**.
5. Tổng các trọng số cạnh theo thứ tự tour bằng `result.cost()`.
6. Chi phí đó không lớn hơn chi phí của bất kỳ tour hợp lệ nào khác (đây là điều kiện tối ưu, cần oracle/brute force cho n nhỏ hoặc chứng minh thuật toán).

Với `possible=false`, mảng route phải rỗng trong hợp đồng của ví dụ; không được in một đường đi dở dang như một tour.

### 12.3. Vét cạn làm oracle khi n nhỏ

Có thể viết bộ kiểm thử độc lập cho `n≤8`:

1. Cố định điểm đầu 0.
2. Liệt kê mọi hoán vị các đỉnh `1..n-1`.
3. Bỏ những hoán vị dùng cạnh không tồn tại.
4. Cộng chi phí các cạnh của đường đi và **cạnh quay về 0**.
5. Lấy giá trị nhỏ nhất; nếu không có tour hợp lệ, báo không có nghiệm.
6. So với kết quả Held–Karp và kiểm tra chu trình được khôi phục.

Brute force có chi phí giai thừa nên chỉ dùng cho n nhỏ như một **oracle kiểm thử**, không nên dùng thay Held–Karp khi n đã đủ lớn để cần tối ưu.

### 12.4. Test trên đồ thị ngẫu nhiên

Với đồ thị có 4–8 đỉnh, tạo các ma trận:

- Có hướng, chi phí hai chiều độc lập.
- Vô hướng, ma trận đối xứng.
- Đầy đủ.
- Thiếu ngẫu nhiên một số cạnh.
- Có nhiều cạnh cùng trọng số (để kiểm tra tie).
- Có cạnh chi phí 0.
- Có một đỉnh không thể đến hoặc không thể đi về.

Với mỗi ma trận, chạy cả **brute force** lẫn **Held–Karp**, so giá trị tối ưu/trạng thái không có nghiệm và kiểm tra tour trả về. Một test ví dụ thành công không thay thế được kiểm tra trên đa dạng cấu trúc.

---

## 13. Những lỗi thường gặp trong bitmask DP TSP

1. **Quên điểm xuất phát trong mask:** khởi tạo `dp[0][0]=0` nhưng định nghĩa trạng thái yêu cầu đã thăm 0; dễ làm sai số đỉnh và truy vết.
2. **Cho phép quay về 0 trong vòng chuyển:** có thể quay về quá sớm, thăm lại điểm xuất phát rồi tạo đường đi không Hamilton.
3. **Không kiểm tra đỉnh next đã thăm:** tạo đường đi lặp đỉnh và phá điều kiện “đúng một lần”.
4. **Chỉ lưu `dp[mask]`, không lưu đỉnh cuối:** không biết dùng cạnh nào để mở rộng đúng.
5. **Trả `min_v dp[FULL][v]` mà quên cạnh `v→0`:** đang giải Hamiltonian path, không phải tour.
6. **Bỏ qua cạnh thiếu:** dùng `-1` trực tiếp như chi phí âm, vô tình làm đường đi “không tồn tại” trở nên rất rẻ.
7. **Dùng 0 làm sentinel cạnh thiếu:** làm mất các cạnh thật sự có chi phí 0.
8. **Cộng INF với trọng số:** có thể tràn số hoặc ghi nhận nghiệm giả.
9. **Giả định ma trận đối xứng:** sai trên đồ thị có hướng hoặc đường một chiều.
10. **Tính sai vị trí bit:** bit i phải ứng với đúng đỉnh i, không lẫn số thứ tự 1-based của đề.
11. **Dùng `1 << n` không kiểm tra n:** với n quá lớn, kết quả shift hoặc bộ nhớ không hợp lệ.
12. **Vòng lặp mask sai thứ tự:** nếu dùng cập nhật tiến, phải bảo đảm trạng thái nguồn được xử lý trước trạng thái đích; mask tăng hoặc theo popcount đều đáp ứng cách làm chuẩn.
13. **Cập nhật parent khi chi phí không cải thiện mà không có quy tắc:** có thể làm truy vết không nhất quán hoặc làm kết quả khó tái hiện.
14. **Truy ngược nhưng không bỏ bit của đỉnh hiện tại:** parent được đọc bằng mask sai và có thể tạo chu trình truy vết vô hạn.
15. **Không đảo thứ tự truy vết:** nhận đường đi từ đỉnh cuối về đầu thay vì từ đầu đến cuối.
16. **Bỏ qua n=1:** vòng chọn đỉnh cuối rỗng rồi báo không có tour dù có thể định nghĩa tour tầm thường chi phí 0.
17. **Nhầm TSP với shortest path:** dùng Dijkstra từ 0 trở về 0 có thể cho kết quả 0 mà không đi qua các thành phố còn lại.
18. **Nhầm TSP chu trình với Hamiltonian path:** bỏ cạnh quay về hoặc cho phép điểm cuối tự do mà vẫn gọi là cùng bài toán.
19. **Giả định n≈30 là đủ nhỏ:** `2^{30}` mask làm DP bảng đầy đủ vượt khả năng RAM thông thường.
20. **Không kiểm thử khi có nhiều lời giải tối ưu:** chỉ đối chiếu một mảng route cụ thể thay vì xét tính hợp lệ và chi phí tối ưu.

---

## 14. Biến thể: không cần quay về điểm xuất phát

Đôi khi đề yêu cầu:

> Xuất phát ở 0, thăm mọi đỉnh đúng một lần, **không bắt buộc quay về 0**.

Đây là bài toán **đường đi Hamilton có chi phí nhỏ nhất** với điểm đầu cố định, không phải tour TSP chu trình.

Ta giữ nguyên trạng thái:

\[
dp[mask][v]=\text{chi phí đường đi bắt đầu tại 0, thăm }mask,\text{ kết thúc ở }v.
\]

Nhưng **đáp án** đổi thành:

\[
\boxed{OPT_{path}=\min_{0\le v<n}dp[FULL][v]}.
\]

Không cộng `w[v][0]`.

Ví dụ với đồ thị có đường đi `0→1→2` mà không có cạnh `2→0`:

- Bài Hamiltonian path từ 0 có thể **có nghiệm**.
- Bài TSP chu trình **không có nghiệm**.

Nếu còn được phép chọn **đỉnh bắt đầu và kết thúc tùy ý**, có thể dùng các trạng thái khởi đầu `dp[1<<s][s]=0` cho mọi s, hoặc thêm nguồn giả theo một thiết kế rõ ràng, rồi lấy min các trạng thái đầy đủ. Không tự dùng công thức xuất phát cố định từ 0 trong bài có start tự do mà không chứng minh phép biến đổi hợp lệ.

---

## 15. Biến thể: tập điểm quan trọng nhỏ trong một đồ thị lớn

Nhiều bài toán thực tế nói “đi qua k điểm bắt buộc” trên một mạng đường có thể có hàng nghìn hoặc hàng triệu giao lộ. Số **điểm quan trọng** k có thể nhỏ, dù số đỉnh mạng ban đầu `V` rất lớn.

Một cách tiếp cận có điều kiện:

1. Chọn tập k điểm bắt buộc, gồm điểm xuất phát.
2. Tính **đường đi ngắn nhất giữa mọi cặp điểm quan trọng**:
   - Dijkstra từ từng điểm quan trọng nếu trọng số cạnh không âm, hoặc
   - Một thuật toán đường đi ngắn nhất khác phù hợp loại đồ thị và trọng số.
3. Xây ma trận khoảng cách `dist[i][j]` giữa các điểm quan trọng.
4. Chạy Held–Karp trên **k điểm** thay vì V đỉnh.
5. Khôi phục thứ tự điểm quan trọng, rồi mở rộng mỗi cạnh `i→j` thành đường đi thật đã lưu ở bước 2.

### 15.1. Vì sao phải kiểm tra ngữ nghĩa?

Đường đi ngắn nhất từ một điểm quan trọng tới điểm khác **có thể đi qua một điểm quan trọng thứ ba** hoặc đi lại các giao lộ đã qua. Vì vậy phép rút gọn này giải một dạng **lộ trình ghé các điểm bắt buộc**, nhưng có thể **không tương đương** với yêu cầu “đi qua mỗi đỉnh của đồ thị gốc đúng một lần”.

Nếu bài yêu cầu **chu trình Hamilton đơn trên toàn bộ mạng gốc** hoặc cấm ghé điểm quan trọng ngoài thứ tự chỉ định, việc lấy khoảng cách ngắn nhất qua đồ thị rồi dùng TSP có thể thay đổi miền nghiệm.

**Kết luận:** thuật toán trên ma trận khoảng cách giữa k đỉnh là hợp lý khi bài cho phép các đoạn hành trình đi qua đỉnh trung gian, có thể lặp lại những đỉnh không bị hạn chế và định nghĩa ghé thăm phù hợp. Phải xác nhận những điều kiện này trước khi áp dụng.

### 15.2. Chi phí của phép rút gọn

Nếu dùng Dijkstra k lần trên một đồ thị thưa có trọng số không âm, chi phí tiền xử lý phụ thuộc `V,E` và cấu trúc hàng đợi, điển hình `O(k(E+V)\log V)` với cài đặt heap phổ biến. Sau đó Held–Karp tốn `O(k²2^k)`.

Sự hữu ích đến từ việc **k nhỏ**, không phải vì toàn bộ đồ thị ban đầu nhỏ. Khi k đã lớn, bước TSP vẫn có độ phức tạp mũ theo k.

---

## 16. TSP có thêm ràng buộc: khi trạng thái (mask,v) chưa đủ

Bài cơ bản có **nguyên lý Markov**: phần tương lai chỉ phụ thuộc **tập đã thăm** và **đỉnh hiện tại**. Khi thêm ràng buộc mới, đôi khi phải mở rộng trạng thái.

### 16.1. Thời gian mở cửa / khung giờ

Nếu mỗi thành phố chỉ cho phép thăm trong một khoảng thời gian, hai đường đi đến cùng `(mask,v)` nhưng **thời điểm đến khác nhau** có thể có tập lựa chọn tiếp theo khác nhau.

Một giá trị “chi phí nhỏ nhất” duy nhất cho mỗi `(mask,v)` không luôn đủ. Có thể cần lưu thời gian, các cặp `(chi phí, thời gian)` không trội nhau, hoặc thiết kế DP tài nguyên cụ thể.

### 16.2. Sức chứa và giao hàng

Nếu người du lịch còn phải mang hàng có khối lượng thay đổi theo thứ tự ghé, trạng thái có thể cần lưu tải hiện tại, số lần nạp hoặc tài nguyên liên quan. Không thể áp dụng nguyên công thức nếu tính hợp lệ của cạnh tiếp theo phụ thuộc thông tin đã bị loại khỏi `(mask,v)`.

### 16.3. Phải thăm một số đỉnh trước đỉnh khác

Ví dụ đỉnh a phải được thăm **trước** b. Khi chuyển sang b, kiểm tra bit của a đã bật chưa. Nếu ràng buộc chỉ là **quan hệ thứ tự đã thăm** và không thêm một đại lượng tài nguyên nào khác, có thể giữ nguyên `dp[mask][v]` và chỉ **lọc chuyển trạng thái** hợp lệ.

### 16.4. Chỉ cần thăm một tập con không bắt buộc

Nếu một số đỉnh là tùy chọn và có thưởng/phạt khi ghé, hoặc chỉ được chọn đúng r đỉnh trong n, hàm mục tiêu và điều kiện kết thúc thay đổi. Có thể vẫn dùng bitmask DP nhưng phải phát biểu lại tập trạng thái, giá trị khởi tạo và cách kết thúc; không mặc định `FULL` luôn là điều kiện dừng.

### 16.5. K đỉnh là điểm bắt buộc, còn các điểm khác không bắt buộc

Đây có thể là một biến thể thích hợp cho tiền xử lý khoảng cách như mục 15, nhưng phải hiểu rõ việc **đi qua** khác với **ghé thăm theo lịch**. Một lời giải tối ưu trên đồ thị rút gọn không tự bảo đảm cùng đường đi hợp lệ dưới mọi ràng buộc của bài toán gốc.

---

## 17. Khi n lớn: dùng gì thay Held–Karp?

TSP tổng quát là bài toán **NP-hard**. Không có thuật toán đa thức theo n được biết cho mọi trường hợp tổng quát, nên Held–Karp cũng là một thuật toán mũ, chỉ khả thi khi n đủ nhỏ.

Một số hướng thay thế hoặc bổ sung:

### 17.1. Vét cạn và branch-and-bound

Với n rất nhỏ, vét cạn `(n-1)!` tour là oracle tuyệt vời cho kiểm thử. Với n lớn hơn một chút, **branch-and-bound** có thể cắt những nhánh mà cận dưới của chi phí đã không thể đánh bại tour tốt nhất hiện tại.

Hiệu quả cắt nhánh phụ thuộc rất mạnh vào dữ liệu và cận dưới được chọn; worst-case vẫn có thể tăng theo hàm mũ hoặc giai thừa.

### 17.2. Heuristic và local search

Các phương án **nearest neighbor**, **2-opt**, **3-opt**, hoặc những heuristic khác có thể nhanh chóng tạo tour tốt trên nhiều bộ dữ liệu. Chúng **không có cùng bảo đảm tối ưu tuyệt đối** như Held–Karp cho TSP tổng quát.

Nếu đề yêu cầu **chi phí nhỏ nhất chính xác**, không được thay bằng nearest neighbor mà không công bố rằng kết quả chỉ là heuristic.

### 17.3. Approximation trên metric TSP

Trong **metric TSP**, chi phí không âm, đối xứng và thỏa **bất đẳng thức tam giác**:

\[
w[u][v]\le w[u][x]+w[x][v].
\]

Có thể áp dụng các thuật toán xấp xỉ có bảo đảm nhất định, chẳng hạn chiến lược dựa trên MST hoặc Christofides trong điều kiện phù hợp.

Nhưng với **TSP có hướng không đối xứng**, **cạnh thiếu** hoặc chi phí không thỏa bất đẳng thức tam giác, không được lấy các bảo đảm của metric TSP rồi áp dụng máy móc.

### 17.4. Chọn thuật toán từ yêu cầu

| Dạng yêu cầu | Hướng cân nhắc |
| --- | --- |
| n rất nhỏ, muốn kiểm chứng | Vét cạn/backtracking |
| n nhỏ, cần nghiệm **tối ưu chính xác** | Held–Karp bitmask DP |
| k điểm quan trọng nhỏ trong mạng lớn | Tiền xử lý khoảng cách + Held–Karp, nếu ngữ nghĩa cho phép |
| n lớn, chỉ cần một hành trình tương đối tốt | Heuristic / local search |
| n lớn, cần tối ưu chính xác và có tài nguyên | Solver tối ưu chuyên dụng, cắt nhánh/cận và mô hình hóa chặt chẽ |
| Có time windows / sức chứa / thứ tự đặc biệt | DP mở rộng hoặc phương pháp tối ưu phù hợp ràng buộc |

Độ khó của thuật toán phải được đánh giá theo **số đỉnh thực sự được đưa vào trạng thái tập con**, cùng các ràng buộc và tính chất ma trận chi phí.

---

## 18. Quy trình giải một bài TSP bằng bitmask DP

Khi gặp một đề bài “người du lịch” hoặc “thăm tất cả các đỉnh”, hãy làm theo checklist:

1. **Hành trình phải quay về điểm đầu không?** Nếu có, đó là tour; nếu không, dùng biến thể đường đi.
2. **Phải thăm mỗi đỉnh đúng một lần hay chỉ cần ghé qua tất cả điểm bắt buộc?** Hai bài khác nhau nếu cho phép đi qua các đỉnh trung gian nhiều lần.
3. **Đồ thị có hướng hay vô hướng?** Không giả định `w[u][v]=w[v][u]` khi đề không nói.
4. **Cạnh có thể thiếu không?** Phải có sentinel hoặc cấu trúc riêng cho cạnh không tồn tại.
5. **Số đỉnh n lớn cỡ nào?** Ước lượng `n2^n` ô bộ nhớ **trước khi cấp phát**.
6. **Chọn điểm đầu:** cố định 0 nếu giải tour và có thể xoay chu trình; hoặc dùng điểm đầu do đề ấn định.
7. **Chốt trạng thái:** `dp[mask][last]` và ý nghĩa của mask.
8. **Khởi tạo:** `dp[1][0]=0`; các trạng thái khác `INF`.
9. **Chuyển:** chỉ sang **đỉnh chưa thăm**, không quay về 0 sớm; kiểm tra cạnh hợp lệ và tổng chi phí.
10. **Kết thúc:** lấy min trên đỉnh cuối và **cạnh quay về 0**.
11. **Nếu cần tour:** lưu parent khi cải thiện trạng thái và truy ngược từ `(FULL,last)`.
12. **Kiểm thử:** đồ thị nhỏ đối xứng, không đối xứng, thiếu cạnh, cạnh 0, n=1/n=2, nhiều nghiệm tối ưu.
13. **Đối chiếu:** trên n rất nhỏ, so với brute-force và kiểm tra mọi điều kiện Hamilton.
14. **Kiểm soát giới hạn:** không cố cấp phát `2^n` trạng thái khi n vượt giới hạn RAM.

---

## 19. Bài tập tự kiểm tra

### Bài 1 — Xác định bài toán

Một đề cho n thành phố, phải xuất phát từ 0, thăm tất cả các thành phố rồi kết thúc tại bất kỳ thành phố nào. Đây đã phải là TSP chu trình chưa? Điều kiện kết thúc DP khác gì?

### Bài 2 — Mã hóa tập bằng bitmask

Với n=5, mask biểu diễn tập `{0,2,4}` là số nhị phân nào và giá trị thập phân bao nhiêu? Sau khi thêm đỉnh 3, mask mới là gì? Kiểm tra đỉnh 1 chưa thăm bằng biểu thức nào?

### Bài 3 — Công thức chuyển

Viết ý nghĩa `dp[mask][v]` và công thức chuyển khi thêm đỉnh `next` chưa thăm. Vì sao đỉnh 0 không được thêm lần nữa trước khi có đầy đủ tập đã thăm?

### Bài 4 — Vết bốn thành phố

Với ma trận ở mục 2, hãy tính `dp[0001][0]`, `dp[0101][2]`, `dp[1101][3]`, `dp[1111][1]` và tổng tour khi quay từ đỉnh 1 về 0.

### Bài 5 — Truy vết parent

Giả sử `parent[1111][1]=3`, `parent[1101][3]=2`, `parent[0101][2]=0`. Hãy viết tour đầy đủ và tính tổng chi phí.

### Bài 6 — Cạnh thiếu

Đồ thị có cạnh `0→1` chi phí 2, `1→2` chi phí 3, nhưng không có cạnh `2→0`, và không có các cạnh khác giữa ba đỉnh. Có Hamiltonian path bắt đầu 0 không? Có TSP tour không?

### Bài 7 — Đồ thị có hướng

Với ma trận:

```text
[ [0,3,8,5],
  [5,0,2,7],
  [1,4,0,2],
  [6,5,3,0] ]
```

Kiểm tra chi phí của tour `0→3→1→2→0`. Có được giả định tour đảo chiều cũng cùng chi phí không?

### Bài 8 — Độ phức tạp

Với n=20, có bao nhiêu mask và bao nhiêu ô `dp[mask][v]` nếu cấp phát bảng đầy đủ? Ước lượng riêng byte cho mảng long và mảng int parent, chưa tính overhead Java.

### Bài 9 — Đếm tour và tối ưu tour

Với bốn thành phố và điểm bắt đầu cố định, có bao nhiêu hoán vị cần xét khi vét cạn TSP có hướng? Nếu hai tour cùng chi phí thấp nhất, có cần lưu cả hai khi đề chỉ yêu cầu một tour tối ưu?

### Bài 10 — Tìm lỗi

Một đoạn mã trả `min_v dp[FULL][v]` và gọi đó là chi phí TSP chu trình. Lỗi ở đâu? Hãy sửa công thức kết thúc.

### Bài 11 — Giới hạn trạng thái

Một lập trình viên dùng `int mask` với `n=32` và cấp phát `long[1 << n][n]`. Hãy chỉ ra ít nhất hai vấn đề độc lập của thiết kế này.

### Bài 12 — Đồ thị lớn, ít điểm quan trọng

Một mạng đường có 10.000 giao lộ nhưng chỉ có 12 điểm bắt buộc. Khi nào có thể tính khoảng cách ngắn nhất giữa 12 điểm rồi áp dụng Held–Karp? Khi nào phép rút gọn đó có thể làm sai điều kiện “thăm đúng một lần”?

### Bài 13 — Kiểm chứng nghiệm

Hãy viết tập điều kiện kiểm tra `route` của một kết quả có `possible=true`: chiều dài mảng, đỉnh đầu/cuối, tính duy nhất các đỉnh, các cạnh hợp lệ, tổng chi phí.

### Bài 14 — Biến thể ràng buộc

Nếu mỗi thành phố có một giờ đóng cửa và thời gian đến phụ thuộc vào thứ tự đi, tại sao trạng thái `dp[mask][v]` chỉ lưu **chi phí nhỏ nhất** có thể chưa đủ? Cần giữ thêm thông tin gì?

### Đáp án gợi ý

1. Chưa phải tour TSP chu trình vì không yêu cầu quay về 0. Đáp án là `min_v dp[FULL][v]`, không cộng cạnh `v→0`.
2. Mask `10101₂=21`. Thêm đỉnh 3: `11101₂=29`. Kiểm tra đỉnh 1 chưa thăm bằng `(mask & (1 << 1)) == 0`.
3. `dp[mask][v]` là chi phí nhỏ nhất của đường đi từ 0, thăm đúng mask, kết thúc tại v. Chuyển sang `nextMask=mask|(1<<next)` và cập nhật min với `dp[mask][v]+w[v][next]` khi next chưa thăm, next≠0 và có cạnh. Quay về 0 chỉ xét sau khi thăm đủ đỉnh.
4. `dp[0001][0]=0`; `dp[0101][2]=15`; `dp[1101][3]=45`; `dp[1111][1]=70`. Thêm `w[1][0]=10` được tổng `80`.
5. Truy ngược `1←3←2←0`; tour `[0,2,3,1,0]` có chi phí `15+30+25+10=80`.
6. Có đường Hamilton `0→1→2` chi phí 5, nhưng không có tour vì không quay được từ 2 về 0.
7. Chi phí `5+5+2+1=13`. Không; ma trận có hướng không nhất thiết đối xứng.
8. `2^{20}=1.048.576` mask, `20.971.520` ô. Mảng long cần khoảng **160 MiB**, parent int thêm **80 MiB**, chưa tính overhead.
9. `(4-1)!=6` thứ tự. Không cần lưu cả hai nếu bài chỉ yêu cầu **một** tour tối ưu; giá trị min vẫn đúng.
10. Thiếu chi phí cạnh quay về 0. Sửa thành `min_{v=1..n-1}(dp[FULL][v]+w[v][0])` trên các cạnh hợp lệ, với trường hợp n=1 xử lý riêng.
11. `1<<32` không tạo `2^{32}` do quy tắc dịch bit của Java; ngoài ra kích thước bảng `2^{32}×32` là phi thực tế với RAM và giới hạn độ dài mảng Java.
12. Có thể rút gọn nếu các đoạn giữa điểm bắt buộc được phép đi qua các giao lộ trung gian, không bị ràng buộc “mỗi đỉnh đúng một lần”. Nếu đường ngắn nhất đi qua những điểm bắt buộc ngoài thứ tự hoặc tái sử dụng đỉnh bị cấm, việc rút gọn có thể không tương đương.
13. Route dài `n+1`; bắt đầu/kết thúc ở 0; mỗi đỉnh xuất hiện đúng một lần trong `n` vị trí đầu; mọi cạnh liên tiếp tồn tại; tổng trọng số bằng cost. Tối ưu có thể đối chiếu với brute-force khi n nhỏ.
14. Hai đường đi cùng tập đã thăm và đỉnh cuối nhưng đến vào các giờ khác nhau có thể có cơ hội đi tiếp khác nhau. Cần lưu thời gian đến hoặc các trạng thái `(chi phí, thời gian)` không trội nhau, cùng quy tắc ràng buộc giờ mở cửa.

---

## Ghi nhớ

**TSP trên tập đỉnh nhỏ** là ví dụ tiêu biểu của **quy hoạch động trên tập con**. Vét cạn xét tới `(n-1)!` thứ tự ghé thăm, nhưng Held–Karp gộp các hành trình có cùng **tập đỉnh đã thăm** và **đỉnh cuối** thành một trạng thái `dp[mask][v]` tốt nhất. Khởi tạo `dp[1][0]=0`, chỉ mở rộng sang đỉnh chưa thăm, rồi kết thúc bằng **cạnh quay về 0**. Thuật toán có `O(n²2^n)` thời gian, `O(n2^n)` bộ nhớ và có thể khôi phục một tour tối ưu bằng mảng `parent`. Cần xác nhận chính xác **chu trình hay đường đi**, **có hướng hay vô hướng**, **cạnh có thể thiếu**, **trọng số và sentinel**, **quy tắc n=1/n=2**, và **giới hạn bộ nhớ**. Khi tập đỉnh rất lớn, bitmask DP không khả thi; khi chỉ có một **tập điểm quan trọng nhỏ**, có thể tiền xử lý khoảng cách rồi chạy Held–Karp nếu phép biến đổi vẫn bảo toàn đúng ngữ nghĩa lộ trình.
