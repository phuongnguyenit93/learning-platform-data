# Kiểm tra tính khả thi, giá trị luồng và chi phí kết quả

Trong **luồng mạng** (*network flow*), một thuật toán có thể in ra một con số rất thuyết phục nhưng vẫn sai nếu luồng trả về **vượt sức chứa cạnh, không bảo toàn tại đỉnh trung gian, tính nhầm giá trị do có cạnh đi vào nguồn**, hoặc **bỏ sót chi phí của các cạnh đã mang luồng**. Ngay cả khi mọi ràng buộc đều thỏa, ta chỉ chứng minh được **luồng khả thi**, chưa chắc đó là **luồng cực đại** (*maximum flow*) hay **luồng có chi phí nhỏ nhất** (*minimum-cost flow*).

Bài học **“Kiểm tra tính khả thi, giá trị luồng và chi phí kết quả”** xây dựng một quy trình kiểm chứng **tách biệt khỏi thuật toán tạo luồng**, áp dụng cho mạng có hướng với sức chứa, **cận dưới tùy chọn** và chi phí trên mỗi đơn vị luồng. Ba câu hỏi cần được phân biệt:

1. **Luồng khả thi không?** Mỗi cạnh thỏa cận dưới–trên; mọi đỉnh trung gian bảo toàn luồng; nguồn và đích có giá trị ròng phù hợp.
2. **Giá trị luồng và tổng chi phí bằng bao nhiêu?** Giá trị tính bằng **luồng ròng qua nguồn/đích**, tổng chi phí tính trên **tất cả cạnh gốc**, không phải trên cạnh dư.
3. **Có chứng chỉ tối ưu không?** Không có đường tăng s→t trong **mạng dư** thì giá trị luồng cực đại; không có **chu trình âm trong mạng dư toàn cục** thì chi phí nhỏ nhất **trong số các luồng cùng giá trị**.

Nội dung gồm định nghĩa, công thức, ví dụ đúng–sai, kiểm tra mạng có cận dưới, điều kiện max-flow/min-cut, chứng chỉ min-cost bằng chu trình âm, khác biệt giữa **max flow** và **min-cost max-flow**, quy tắc số học không tràn, một chương trình **Java 17+ chạy độc lập**, kiểm thử đối chiếu với liệt kê hết trường hợp nhỏ, lỗi phổ biến và bài tập có đáp án.

**Giới hạn rõ ràng:** Chương trình Java minh họa là **bộ kiểm toán luồng** (*flow auditor*), không phải thuật toán tìm luồng tối ưu cho mạng lớn. Nó nhận **luồng ứng viên** từ một thuật toán bất kỳ, kiểm tra tính đúng và kiểm chứng tối ưu bằng mạng dư. Phần liệt kê brute force chỉ là oracle cho mạng rất nhỏ.

## 1. Mô hình mạng, ký hiệu và giả thiết

Cho mạng có hướng `G=(V,E)` với:

- `n=|V|` đỉnh đánh số 0..n−1;
- nguồn `s` và đích `t`, `s≠t`;
- mỗi **cạnh gốc có chỉ số riêng** `e=(u,v)`, sức chứa dưới `l_e` và trên `u_e`, `0≤l_e≤u_e`;
- chi phí đơn vị `c_e`, có thể **âm, bằng 0 hoặc dương**;
- luồng nguyên trên cạnh `f_e`.

Trong phạm vi bài này, giá trị luồng ròng từ nguồn tới đích cần **không âm**: `F≥0`. Tổng chi phí có thể âm.

**Điểm dễ nhầm:** Ký hiệu `u_e` là **sức chứa trên của cạnh**, còn ký hiệu u trong (u,v) là **đỉnh xuất phát**; chúng không phải cùng một loại đại lượng.

Một cạnh có thể là:

- Cạnh thường từ u sang v, u≠v.
- **Cạnh song song**: nhiều cạnh gốc cùng hai đầu u,v; **phải lưu riêng mỗi cạnh** nếu có sức chứa/chi phí khác nhau.
- **Khuyên u→u** (*self-loop*): luồng qua khuyên vừa vào vừa ra cùng đỉnh, nên không đổi cân bằng ròng; nhưng vẫn có thể **đóng góp chi phí** và tạo chu trình dư âm.

Đây là mô hình **có cận dưới**; max flow truyền thống là trường hợp `l_e=0` cho mọi cạnh.

### 1.1. Luồng là một vectơ gắn với cạnh gốc

Giả sử danh sách cạnh:

```text
e0: 0 -> 1, cap [0,3], cost 2
e1: 0 -> 2, cap [0,2], cost 4
e2: 1 -> 2, cap [0,2], cost -1
```

Vectơ `f=[2,1,1]` nghĩa là:

- Cạnh **e0** mang luồng 2;
- Cạnh **e1** mang luồng 1;
- Cạnh **e2** mang luồng 1.

Nếu hai cạnh có cùng u,v, không được chỉ dùng map `(u,v)→flow` khiến chúng ghi đè nhau. Mỗi cạnh gốc là một phần tử riêng trong mảng; thứ tự của `f` phải trùng thứ tự `edges`.

### 1.2. Ba tầng kiểm chứng

| Tầng | Cần chứng minh | Kết quả nếu đạt |
| --- | --- | --- |
| **Khả thi (feasibility)** | Cận cạnh, bảo toàn và nguồn–đích | `f` là một luồng hợp lệ |
| **Giá trị & chi phí** | Luồng ròng và tổng `f_e c_e` | Hai đại lượng `F,C` tính đúng |
| **Tối ưu (optimality)** | Không còn cải thiện theo tiêu chí đã nêu | Chứng chỉ max-flow, min-cost cùng F, hoặc cả hai |

**Luồng tối thiểu chi phí cùng F** và **luồng cực đại** là hai câu hỏi khác nhau. Một luồng có thể đạt cả hai, một trong hai, hoặc không đạt cái nào.

## 2. Kiểm tra sức chứa: từng cạnh phải thỏa cận

Với mỗi cạnh e:

```text
lower[e] <= flow[e] <= upper[e]
```

Nếu không có cận dưới trong đề, đặt `lower[e]=0`, nghĩa là `0≤flow[e]≤capacity[e]`.

Ví dụ:

```text
Edge e0: lower=1, upper=3

flow[e0]=1  -> hợp lệ
flow[e0]=2  -> hợp lệ
flow[e0]=3  -> hợp lệ
flow[e0]=0  -> SAI, thấp hơn lower
flow[e0]=4  -> SAI, vượt upper
```

### 2.1. Kiểm tra đúng thứ tự

Khi kiểm toán, trước tiên cần xác thực cấu trúc đầu vào:

- `n≥2`, `s,t` thuộc [0,n−1], `s≠t`;
- mỗi cạnh có hai đầu hợp lệ;
- `lower≥0` và `upper≥lower`;
- mảng luồng có **đúng số phần tử bằng số cạnh gốc**.

Sau đó duyệt từng cạnh và kiểm tra `lower≤flow≤upper`. Nếu không thỏa, **dừng kiểm toán**: các phép tính F/C tiếp theo không đủ ý nghĩa để chứng minh một luồng khả thi.

**Không được gộp cận của các cạnh song song rồi chỉ kiểm tra tổng.** Ví dụ e0 cap1 và e1 cap5 cùng nối 0→1, ứng viên `f0=2,f1=0` có tổng2≤6 nhưng **vượt cap riêng của e0**.

### 2.2. Vì sao không chỉ kiểm tra capacity?

Giả sử thuật toán cho:

```text
0 -> 1: flow=3, upper=3
1 -> 2: flow=1, upper=3
```

Mỗi cạnh đều không vượt cap. Nhưng đỉnh trung gian 1 nhận **3** đơn vị và chỉ chuyển đi **1** đơn vị: **không bảo toàn luồng**, nên kết quả vẫn sai. Phải kiểm tra điều kiện tiếp theo.

## 3. Kiểm tra bảo toàn luồng tại các đỉnh

Đặt cân bằng ròng tại v:

```text
balance[v] =
    SUM_{e đi RA từ v} flow[e]
  - SUM_{e đi VÀO v} flow[e]
```

Theo quy ước này, **out−in**:

- Với mọi đỉnh **trung gian** v≠s,t:

  ```text
  balance[v] = 0
  ```

- Với nguồn s:

  ```text
  balance[s] = F
  ```

- Với đích t:

  ```text
  balance[t] = -F
  ```

Với F≥0 theo giả thiết bài này.

### 3.1. Tính balance bằng một lượt duyệt cạnh

Khởi tạo `balance[v]=0` cho mọi v. Với mỗi cạnh e=(u,v) mang `f_e`:

```text
balance[u] += f_e
balance[v] -= f_e
```

Nếu u=v (self-loop), hai phép cập nhật trên **cùng một đỉnh** sẽ triệt tiêu: đúng vì self-loop không tạo ra hoặc tiêu thụ luồng ròng.

Với đồ thị n đỉnh, m cạnh, việc tính balance mất **O(n+m)** thời gian.

**Cảnh báo tràn số:** Dù `f_e` vừa kiểu long, tổng nhiều cạnh đi ra một đỉnh có thể vượt long. Mã Java dùng **BigInteger** cho balance để không mất tính đúng ở mạng có nhiều cạnh lớn.

### 3.2. Tổng balance luôn bằng 0

Mỗi cạnh thêm `+f_e` vào đầu ra và `−f_e` vào đầu vào, nên:

```text
SUM_{v thuộc V} balance[v] = 0
```

Đây là bất biến hữu ích để đối chiếu. Nếu mọi đỉnh trung gian có balance=0, thì:

```text
balance[s] + balance[t] = 0
```

Tuy nhiên, trong bộ kiểm toán thực tế vẫn nên kiểm tra **riêng** cả nguồn và đích, để thông báo lỗi rõ ràng và tránh nhầm dấu.

### 3.3. Cạnh đi vào nguồn và cạnh đi ra đích không bị cấm

Nhiều bài minh họa nguồn chỉ có cạnh đi ra, đích chỉ có cạnh đi vào, nhưng mô hình luồng tổng quát **không bắt buộc** như vậy.

Ví dụ:

```text
0 = nguồn, 2 = đích

e0: 0 -> 2, flow=5
e1: 2 -> 0, flow=2
```

Giá trị ròng là:

```text
F = out(0) - in(0) = 5 - 2 = 3

Kiểm tra từ đích:
in(2) - out(2) = 5 - 2 = 3
```

Nếu chỉ cộng các cạnh **đi ra nguồn** thì báo F=5, **sai**. Tương tự, chỉ cộng cạnh đi vào đích mà không trừ cạnh đi ra đích sẽ sai.

## 4. Giá trị luồng F và chi phí C

Sau khi kiểm tra hợp lệ:

### 4.1. Giá trị luồng

```text
F = SUM_{e ra khỏi s} f_e
  - SUM_{e đi vào s} f_e

  = SUM_{e đi vào t} f_e
  - SUM_{e ra khỏi t} f_e
```

Đây là **giá trị luồng ròng**. Trong mô hình ở đây, nếu F âm thì ứng viên không thuộc lớp s→t flow không âm mà bài quy định; có thể cần đổi vai trò s,t hoặc dùng mô hình khác nếu đề cho phép giá trị âm.

### 4.2. Tổng chi phí

Mỗi cạnh gốc e có chi phí `c_e` cho một đơn vị luồng. Khi mang `f_e` đơn vị, đóng góp là `f_e c_e`. Tổng:

```text
C(f) = SUM_{e thuộc E_gốc} f_e * c_e
```

Cần lưu ý:

- Chi phí có thể **âm** nếu cạnh có cost âm và mang luồng dương.
- Cạnh có **flow=0** không đóng góp chi phí.
- Cạnh **có cận dưới** có thể bắt buộc mang luồng; phần luồng tối thiểu ấy **vẫn đóng góp chi phí**.
- Một cạnh **self-loop** mang luồng vẫn phải tính `f_e c_e`.
- Cạnh **dư** (*residual reverse edge*) **không phải cạnh gốc mới**, nên không được cộng một lần nữa vào tổng chi phí cuối.
- Để tránh tràn `flow×cost` và cộng nhiều tích lớn, dùng `BigInteger` khi cần tính **chính xác tuyệt đối**.

### 4.3. Bài toán có nhiều tiêu chí

Ba mục tiêu thường gặp:

1. **Max flow:** Tối đa hóa `F`; chi phí không nằm trong tiêu chí tối ưu.
2. **Min-cost flow of required value K:** Ràng buộc `F=K`, sau đó tối thiểu hóa `C(f)`.
3. **Min-cost max-flow:** Trước hết tối đa hóa `F`, rồi trong số các luồng có F lớn nhất, tối thiểu hóa `C(f)`.

**Không đồng nhất** ba mục tiêu. Ví dụ một luồng F=4,C=14 có thể là min-cost trong số các luồng giá trị 4, nhưng vẫn chưa phải max-flow nếu mạng cho phép F=6. Ngược lại F=6,C=32 có thể cực đại, nhưng cần chứng chỉ min-cost ở F=6 trước khi kết luận là min-cost max-flow.

## 5. Ví dụ mạng cơ bản: luồng hợp lệ nhưng chi phí khác nhau

Cho mạng 4 đỉnh s=0,t=3 với sáu cạnh có **cận dưới bằng 0**:

| id | Cạnh | lower | upper | cost |
| --- | --- | ---: | ---: | ---: |
| e0 | 0→1 | 0 | 3 | 2 |
| e1 | 0→2 | 0 | 2 | 4 |
| e2 | 1→2 | 0 | 2 | −1 |
| e3 | 1→3 | 0 | 2 | 3 |
| e4 | 2→3 | 0 | 3 | 1 |
| e5 | 0→3 | 0 | 1 | 10 |

Sơ đồ hướng và chi phí:

```text
       (2, cap 3)       (3, cap 2)
  0 ----------------> 1 ----------------> 3
  |                    |                  ^
  |                    | (-1, cap 2)      |
  | (4, cap 2)         v                  | (1, cap 3)
  +------------------> 2 -----------------+
  |
  +-------------------------------------> 3
              (10, cap 1)

Mỗi nhãn = (cost/đơn vị, upper capacity)
```

### 5.1. Luồng A: hợp lệ, F=4, C=20

```text
f_A = [2, 2, 0, 2, 2, 0]
```

Kiểm tra bảo toàn:

```text
0: ra 2+2 = 4                => balance[0]=+4
1: vào 2, ra 0+2=2           => balance[1]=0
2: vào 2+0=2, ra 2           => balance[2]=0
3: vào 2+2+0=4               => balance[3]=-4
```

Chi phí:

```text
C_A = 2*2 + 2*4 + 0*(-1)
    + 2*3 + 2*1 + 0*10
    = 4+8+0+6+2+0
    = 20
```

Không có cạnh nào vượt cap. Vậy **A là luồng khả thi** với F=4,C=20. Nhưng chưa thể khẳng định A tối ưu.

### 5.2. Luồng B: cùng F=4 nhưng chi phí thấp hơn, C=14

```text
f_B = [3, 1, 2, 1, 3, 0]
```

Kiểm tra:

```text
0: ra 3+1=4                  => +4
1: vào 3, ra 2+1=3           =>  0
2: vào 1+2=3, ra 3           =>  0
3: vào 1+3+0=4               => -4
```

Chi phí:

```text
C_B = 3*2 + 1*4 + 2*(-1)
    + 1*3 + 3*1 + 0*10
    = 6+4-2+3+3
    = 14
```

Vì A và B cùng giá trị F=4 nhưng `14<20`, A **chắc chắn không phải min-cost flow giá trị 4**. B có thực sự min-cost không? Cần một chứng chỉ không còn chu trình dư âm hoặc đối chiếu với lời giải đầy đủ; phần sau sẽ kiểm tra.

### 5.3. Luồng C: F=6, C=32

```text
f_C = [3, 2, 1, 2, 3, 1]
```

Kiểm tra:

```text
0: ra 3+2+1=6                => +6
1: vào 3, ra 1+2=3           =>  0
2: vào 2+1=3, ra 3           =>  0
3: vào 2+3+1=6               => -6
```

Chi phí:

```text
C_C = 3*2 + 2*4 + 1*(-1)
    + 2*3 + 3*1 + 1*10
    = 6+8-1+6+3+10
    = 32
```

Mọi cạnh ra khỏi nguồn 0 đã đạt upper: e0=3,e1=2,e5=1. Vì vậy không thể tăng giá trị luồng lên quá 6; C đạt F=6 nên **là max flow**.

Tuy nhiên, chỉ nhìn thấy nguồn hết capacity vẫn chưa chứng minh **min-cost ở F=6**. Trong ví dụ nhỏ này, các sức chứa làm luồng F=6 được xác định duy nhất, nhưng với mạng lớn có nhiều đường lựa chọn cần kiểm tra **chu trình dư âm**.

### 5.4. Đối chiếu liệt kê hết trên mạng nhỏ

Nếu liệt kê tất cả vectơ luồng nguyên theo cận cạnh, rồi lọc điều kiện cân bằng:

| Giá trị F | Chi phí nhỏ nhất ở F |
| ---: | ---: |
| 0 | 0 |
| 1 | 2 |
| 2 | 4 |
| 3 | 9 |
| 4 | 14 |
| 5 | 22 |
| 6 | 32 |

Do đó:

- `F_max=6`.
- Min-cost flow yêu cầu F=4 có `C_min=14`.
- Min-cost max-flow có cặp `(F,C)=(6,32)`.

**Liệt kê chỉ hợp lý cho mẫu nhỏ.** Không dùng brute force để thay thế thuật toán luồng ở dữ liệu lớn; số vectơ có thể là tích `∏(upper−lower+1)`, tăng theo cấp số nhân của số cạnh.

## 6. Kiểm chứng luồng cực đại bằng mạng dư

Cho một luồng **đã khả thi** f, mỗi cạnh gốc e=(u,v) với cận [l,u] tạo ra tối đa hai cung dư:

- **Dư thuận u→v** nếu `f_e<u_e`, sức chứa dư `u_e−f_e`.
- **Dư ngược v→u** nếu `f_e>l_e`, sức chứa dư `f_e−l_e`.

Đây là điều chỉnh chính xác cho **cận dưới**. Trong mạng không cận dưới, dư ngược là `f_e`; nhưng nếu lower>0, không thể hoàn trả luồng xuống dưới lower.

```text
Cạnh gốc u -> v, lower=1, upper=5, flow=3:

Dư thuận u -> v: cap=5-3=2
Dư ngược v -> u: cap=3-1=2
```

### 6.1. Vì sao có cung dư ngược?

Một cung dư ngược **không nhất thiết là cạnh thật** trong đồ thị gốc. Nó biểu diễn quyền **giảm lượng luồng đã gán trên cạnh gốc**, ví dụ điều chỉnh luồng từ 3 về 2 mà không vi phạm lower=1.

Cung dư ngược rất quan trọng vì một lời giải sơ bộ có thể đi theo đường chưa tốt; thuật toán có thể **hủy một phần lựa chọn cũ** để chuyển dòng qua đường tốt hơn.

Nếu có hai cạnh gốc ngược chiều nhau, cung ngược dư của cạnh thứ nhất và cung thuận gốc của cạnh thứ hai là **hai hành động khác nhau**, dù cùng hướng trong mạng dư. Cần giữ thông tin cạnh gốc khi cập nhật luồng.

### 6.2. Đường tăng s→t và định lý max-flow

Một **đường tăng** (*augmenting path*) là một đường s→t trong mạng dư chỉ dùng cung có capacity dư dương. Nếu tồn tại đường như vậy, có thể tăng luồng theo đường thêm một lượng:

```text
delta = MIN(residualCapacity trên đường)
```

Trong mô hình nguyên, `delta≥1`. Kết quả vẫn thỏa cận và bảo toàn, với giá trị F tăng delta.

Nếu **không còn đường tăng** s→t từ một luồng đã khả thi, thì luồng ấy có **giá trị cực đại**. Đây là một cách kiểm chứng độc lập với việc thuật toán nào sinh ra f.

**Phải kiểm tra tính khả thi trước.** Một vectơ vi phạm bảo toàn nhưng tình cờ không còn đường s→t trong mạng dư **không phải chứng chỉ max-flow**.

### 6.3. Chứng chỉ min-cut bằng tập S

Chạy BFS/DFS từ s trong mạng dư, thu tập S gồm các đỉnh có thể tới được. Nếu t∉S, cặp (S,T=V∖S) là một lát cắt xác nhận luồng cực đại.

Với mạng **không có cận dưới**, sức chứa lát cắt là tổng upper của các cạnh **từ S sang T**.

Với mạng **có cận dưới**, cận trên đúng cho giá trị luồng là:

```text
F <= CUT_BOUND(S,T)

CUT_BOUND(S,T) =
    SUM_{e: from in S, to in T} upper[e]
  - SUM_{e: from in T, to in S} lower[e]
```

Lý do: tổng luồng ròng qua lát cắt bằng F; cạnh S→T tối đa bằng upper, cạnh T→S tối thiểu bằng lower, nên hiệu bị chặn như công thức.

Nếu `t∉S` và các cung dư từ S sang T đều không còn capacity thuận, các cung gốc S→T đã ở upper và các cung gốc T→S đã ở lower. Vì vậy:

```text
F = CUT_BOUND(S,T)
```

Đó là chứng chỉ tối ưu trực tiếp. **Không được quên phần trừ lower của cạnh T→S** khi bài cho cận dưới.

### 6.4. Khi t vẫn tới được trong mạng dư

Nếu BFS từ s chạm t, f **chưa phải max-flow**. Khi đó tập S theo BFS chứa cả t nên nó **không phải một lát cắt s–t**. Không nên in cut bound của S như một chứng chỉ max-flow; mã trả `cut=NA` trong trường hợp này.

### 6.5. Giới hạn kiểm tra “không còn đường tăng”

Điều kiện không còn đường tăng là chứng chỉ **giá trị luồng cực đại**, không xét mục tiêu chi phí. Một luồng cực đại vẫn có thể chứa những vòng tuần hoàn đắt đỏ không cần thiết và bị cải thiện chi phí mà không thay đổi F.

## 7. Kiểm tra tối ưu chi phí với giá trị F cố định

Cho luồng khả thi f với F cố định, ngoài capacity dư, mỗi cung dư còn có **chi phí điều chỉnh**:

- Dư thuận u→v có chi phí `+c_e`: tăng luồng trên cạnh gốc thêm một đơn vị làm tổng cost tăng c_e.
- Dư ngược v→u có chi phí `−c_e`: giảm luồng cạnh gốc một đơn vị làm tổng cost **giảm** c_e.

Ví dụ cạnh gốc u→v có cost=7:

```text
Tăng f_e thêm 1: cost tăng +7
Giảm f_e đi 1:  cost thay đổi -7
```

Nếu cost gốc là −3, giảm luồng trên cạnh ấy làm tổng cost **tăng +3**. Đây là dấu đảo cần thiết; cung dư ngược không đơn giản mang cùng chi phí với cạnh thuận.

### 7.1. Chu trình âm trong mạng dư

Nếu mạng dư có một **chu trình có tổng chi phí âm**, ta có thể tăng luồng theo chu trình ấy một lượng delta dương (tối đa bằng capacity dư nhỏ nhất trên chu trình).

Do mỗi đỉnh trên chu trình nhận và gửi cùng delta, các cân bằng đỉnh **không đổi**. Vì vậy:

```text
F_new = F_old

C_new = C_old + delta * cost(cycle)
      < C_old  (vì cost(cycle) < 0)
```

Luồng vẫn khả thi, giá trị F giữ nguyên, nhưng chi phí giảm. Do đó luồng ban đầu **chưa tối ưu chi phí** ở giá trị F ấy.

Ngược lại, nếu **không có chu trình âm** trong toàn bộ mạng dư, luồng khả thi f có **chi phí tối thiểu trong số các luồng cùng F**. Vì hiệu giữa hai luồng khả thi cùng F là một tuần hoàn có thể phân rã thành những chu trình trong mạng dư; nếu có một luồng khác rẻ hơn, ít nhất một chu trình trong phân rã phải âm, trái với giả thiết.

Đây là **điều kiện cần và đủ** cho min-cost flow với giá trị F cố định trong mô hình sức chứa hữu hạn, chi phí tuyến tính, nguyên.

### 7.2. Phải kiểm tra chu trình âm ở mọi thành phần dư

Một lỗi rất thường gặp là chỉ chạy Bellman–Ford từ **nguồn s**. Nhưng một chu trình âm có thể nằm trong một thành phần mạng dư **không tới được từ s**, vẫn có thể bổ sung tuần hoàn rẻ hơn mà không đổi F.

Muốn phát hiện chu trình âm **ở bất cứ đâu**, có thể:

- Tạo **siêu nguồn giả** nối tới mọi đỉnh bằng cung chi phí 0; hoặc
- Khởi tạo `distance[v]=0` cho **mọi v**, tương đương siêu nguồn giả, rồi thực hiện Bellman–Ford qua **mọi cung dư**.

Nếu còn cập nhật ở lượt thứ n, tồn tại chu trình âm. Nếu một lượt hoàn toàn không thay đổi, kết thúc sớm và không có chu trình âm.

Trong mã Java, dùng **BigInteger** cho các giá trị Bellman–Ford của chứng chỉ, để không tràn khi cộng các chi phí rất lớn hoặc đổi dấu `Long.MIN_VALUE`.

### 7.3. Ví dụ max-flow nhưng chưa min-cost

Xét s=0,t=2:

| id | Cạnh | lower | upper | cost |
| --- | --- | ---: | ---: | ---: |
| e0 | 0→2 | 0 | 1 | 5 |
| e1 | 0→1 | 0 | 1 | 0 |
| e2 | 1→0 | 0 | 1 | −3 |

Luồng:

```text
f = [1,0,0]
F = 1
C = 1*5 = 5
```

Cạnh duy nhất vào t là e0, cap1, nên **F=1 đã cực đại**.

Nhưng trong mạng dư còn hai cung thuận:

```text
0 -> 1, cost 0
1 -> 0, cost -3
```

Chúng tạo chu trình chi phí `0+(−3)=−3`. Đẩy một đơn vị quanh chu trình, ta được:

```text
f' = [1,1,1]
F' = 1  (không đổi)
C' = 5+0-3 = 2
```

Vậy f **max-flow nhưng không min-cost max-flow**. Sau khi vòng âm bị bão hòa, f' không còn chu trình dư âm và đạt min-cost tại F=1.

**Thông điệp:** Từ “max flow” **không** suy ra “min cost”; cần hai chứng chỉ độc lập.

## 8. Giải thích chứng chỉ min-cost bằng potential

Định lý không chu trình âm có thể diễn đạt thêm bằng **thế năng đỉnh** (*vertex potentials*).

Nếu mạng dư không có chu trình âm, tồn tại các thế năng `π[v]` sao cho với mọi cung dư u→v có chi phí c:

```text
reducedCost(u,v) =
    c(u,v) + π[u] - π[v]
    >= 0
```

Có thể tìm π từ khoảng cách Bellman–Ford chạy với siêu nguồn giả chi phí 0 đến mọi đỉnh. Tính chất đường ngắn nhất là:

```text
π[v] <= π[u] + c(u,v)

=> c(u,v) + π[u] - π[v] >= 0
```

Vì tổng chênh lệch thế năng trên một chu trình là 0, một chu trình âm không thể tồn tại nếu mọi reduced cost đều không âm.

Đây là liên hệ giữa **chứng chỉ chu trình dư** và các thuật toán **min-cost flow dùng potentials / reduced costs**, giúp hiểu tại sao có thể kiểm chứng lời giải bằng điều kiện đối ngẫu thay vì chạy lại toàn bộ thuật toán sinh luồng.

**Không tự dùng potential của Dijkstra trên mạng có cạnh âm khi chưa xử lý:** Cạnh giảm chi phí trong mạng dư có thể âm. Một cài đặt min-cost max-flow dùng Dijkstra với potentials cần điều kiện khởi tạo và cập nhật thế năng đúng; bài này dùng Bellman–Ford cho kiểm chứng nên không cần giả định mọi residual cost không âm.

## 9. Kiểm tra luồng với cận dưới

Nhiều đề cho mỗi cạnh một khoảng:

```text
lower[e] <= flow[e] <= upper[e]
```

Một luồng thỏa mỗi cận cạnh **chưa chắc thỏa cân bằng**, và đôi khi **không tồn tại** luồng nào thỏa tất cả cận dưới.

### 9.1. Ví dụ cận dưới ảnh hưởng min-cut

Cho n=3, s=0,t=2:

| id | Cạnh | lower | upper | cost |
| --- | --- | ---: | ---: | ---: |
| e0 | 0→1 | 1 | 3 | 1 |
| e1 | 1→2 | 0 | 3 | 2 |
| e2 | 2→1 | 1 | 1 | 0 |
| e3 | 0→2 | 0 | 2 | 4 |

Ứng viên:

```text
f = [2,3,1,2]
```

Cân bằng:

```text
balance[0] = +2 +2 = +4
balance[1] = +3 -2 -1 = 0
balance[2] = -3 +1 -2 = -4

F = 4
C = 2*1 + 3*2 + 1*0 + 2*4
  = 2+6+0+8 = 16
```

Trong mạng dư:

- 0→1 còn capacity 1 nên từ s tới được đỉnh 1.
- 1→2 đã bão hòa e1, nên không đi tiếp tới 2.
- e2 gốc 2→1 đang ở **lower=1**, nên cung dư ngược 1→2 của e2 có capacity `f−lower=0`.
- 0→2 đã bão hòa e3.

Vì thế tập tới được từ s là:

```text
S={0,1}, T={2}
```

Cận trên lát cắt:

```text
SUM upper(S->T) = upper(e1)+upper(e3)
                = 3+2 = 5

SUM lower(T->S) = lower(e2)
                = 1

CUT_BOUND = 5-1 = 4
```

Ứng viên đạt F=4 bằng cut bound, nên **max-flow**. Nếu bỏ phép trừ lower của e2, ta báo cut=5 và tưởng còn tăng được một đơn vị, **sai**.

### 9.2. Luồng sai do thấp hơn lower

Với cùng mạng, `f=[0,0,0,0]` vi phạm lower của e0 và e2; dù cân bằng mọi đỉnh bằng 0, đó **không phải** một luồng khả thi vì không tuân thủ cận dưới.

### 9.3. Tính khả thi của **bài toán** khác tính khả thi của **ứng viên**

Có hai câu hỏi:

- **Audit(candidate):** Vectơ f cụ thể có thỏa ràng buộc không?
- **Feasible(instance):** Có **bất kỳ** vectơ f nào thỏa ràng buộc hay không?

Kiểm tra một ứng viên không đạt **không chứng minh** bài toán không có luồng khả thi. Để quyết định sự tồn tại với lower bounds, có thể chuyển về **circulation with demands**.

### 9.4. Kỹ thuật chuyển cận dưới về circulation

Đặt:

```text
f_e = lower[e] + x_e

0 <= x_e <= upper[e] - lower[e]
```

Với mỗi đỉnh v, tính:

```text
b[v] =
    SUM_{e đi VÀO v} lower[e]
  - SUM_{e đi RA v} lower[e]
```

Muốn bảo toàn sau khi đặt cận dưới, phần luồng bổ sung x phải có:

```text
SUM_{x đi RA v} x
- SUM_{x đi VÀO v} x
= b[v]
```

Xây mạng phụ:

1. Mỗi cạnh gốc e thay bằng cạnh có capacity `upper[e]−lower[e]`.
2. Thêm siêu nguồn SS, siêu đích TT.
3. Nếu `b[v]>0`, thêm `SS→v` capacity b[v].
4. Nếu `b[v]<0`, thêm `v→TT` capacity −b[v].
5. Chạy max flow SS→TT. Nếu **tất cả các cạnh rời SS đều bão hòa**, tìm được circulation thỏa các cận dưới.

Nếu cần **luồng s→t có giá trị đúng K**, thêm cạnh phụ `t→s` với **cận dưới = cận trên = K** trước khi thực hiện phép chuyển. Đối với giá trị F không cố định nhưng yêu cầu F≥0, có thể thêm `t→s` với lower0 và upper đủ lớn được **chứng minh** làm cận trên cho F, rồi tìm circulation.

**Cẩn thận:** Bài toán nguồn–đích có thêm cạnh t→s chỉ là một cách khép kín thành circulation **để kiểm tra sự tồn tại**. Cạnh phụ ấy **không phải cạnh gốc** để tính chi phí kết quả; nếu bài yêu cầu min cost còn cần xử lý chi phí cận dưới và thuật toán tối ưu tương ứng.

### 9.5. Khôi phục chi phí khi loại lower

Với `f_e=l_e+x_e`, chi phí gốc:

```text
C(f) = SUM_e (l_e + x_e) * c_e
     = SUM_e l_e*c_e + SUM_e x_e*c_e
```

Vế đầu là **chi phí nền bắt buộc** do lower. Nếu thuật toán chạy trên capacity dư chỉ trả `Σx_e c_e` mà quên `Σl_e c_e`, tổng chi phí báo cáo sai.

## 10. Cạnh song song, khuyên, cung ngược và chu trình

### 10.1. Cạnh song song

Hai cạnh 0→1:

```text
e0: upper=2, cost=8
e1: upper=3, cost=1
```

Nếu muốn gửi 3 đơn vị, phân bổ sang e1 rẻ hơn có thể cho C=3; phân bổ e0=2,e1=1 cho C=17. Chỉ lưu một giá trị capacity/cost cho cặp (0,1) sẽ đánh mất các phương án và phá bài toán min-cost.

Mỗi cạnh song song gốc vẫn có **một cặp cung dư riêng**. Khi tìm chu trình dư, hai cung cùng hướng có chi phí khác nhau phải được giữ phân biệt để xét đúng lợi ích điều chỉnh.

### 10.2. Hai cạnh gốc ngược hướng

Nếu đồng thời có e0: u→v và e1: v→u, một cung dư v→u của e0 **khác** cung gốc v→u của e1:

- Giảm e0 một đơn vị làm chi phí thay đổi **−cost(e0)**.
- Tăng e1 một đơn vị làm chi phí thay đổi **+cost(e1)**.

Hai hành động có thể kết hợp thành một chu trình điều chỉnh. Không được “hợp nhất” theo hai đầu đỉnh rồi áp một chi phí tùy ý.

### 10.3. Khuyên có chi phí âm

Xét s=0,t=1, cạnh gốc 0→1 mang F=1, và một khuyên 0→0 có upper1,cost−5. Luồng trên khuyên không đổi F nhưng đẩy một đơn vị lên khuyên làm **giảm chi phí 5**. Một max-flow hợp lệ với f_khuyên=0 **chưa chắc min-cost** nếu còn cung dư khuyên âm.

Kiểm tra chu trình âm **toàn cục** phát hiện cả chu trình một đỉnh (self-loop), không chỉ các chu trình độ dài ít nhất 2.

### 10.4. Chi phí bằng 0

Một chu trình dư có tổng cost0 không chứng minh f chưa min-cost; đẩy quanh nó không đổi chi phí. Có thể có **nhiều luồng cùng giá trị, cùng chi phí tối ưu**. Không yêu cầu nghiệm tối ưu phải duy nhất.

## 11. Số học an toàn khi kiểm toán

Sức chứa và lượng luồng thường có kiểu số nguyên. Nếu chỉ dùng int/long, có ba nơi dễ tràn:

1. Cộng rất nhiều cạnh tại một đỉnh để tính balance.
2. Nhân `flow[e]×cost[e]` để tính chi phí trên cạnh.
3. Cộng nhiều tích để tính tổng cost, hoặc tính cận lát cắt gồm nhiều upper/lower.
4. Đổi dấu chi phí trong cung dư ngược, đặc biệt `−Long.MIN_VALUE` không biểu diễn được bằng long.
5. Cộng nhiều residual cost khi tìm chu trình âm.

Trong Java, phép cộng/nhân số nguyên primitive thông thường có thể wraparound mà không ném ngoại lệ.

**Chính sách mã mẫu:**

- `lower,upper,flow,cost` của **mỗi cạnh** dùng long; cận và flow đều không âm.
- `balance[v]` dùng **BigInteger** vì có thể là tổng nhiều long.
- `F` và `C` dùng **BigInteger**; mỗi tích `flow×cost` được nhân trong BigInteger trước khi cộng.
- Chi phí cung dư ngược được tính bằng `BigInteger.valueOf(cost).negate()`, an toàn cả khi cost=Long.MIN_VALUE.
- Bellman–Ford trên mạng dư dùng BigInteger cho khoảng cách để tránh tràn.
- Sức chứa dư `upper−flow` và `flow−lower` vẫn vừa long khi các cận đều thỏa và không âm.

**Không dùng sentinel INF hữu hạn cho phép cộng cost.** Trong Bellman–Ford phát hiện chu trình âm toàn cục, có thể khởi tạo mọi dist=BigInteger.ZERO vì tương đương có một siêu nguồn nối cost0 tới mọi đỉnh; không cần vô cực.

### 11.1. Ví dụ cost vượt long nhưng vẫn chính xác

Một cạnh 0→1 có:

```text
lower=0
upper=2
cost=Long.MIN_VALUE
flow=2
```

Tổng chi phí toán học:

```text
C = 2 * (-9223372036854775808)
  = -18446744073709551616
```

Giá trị này không vừa long, nhưng **BigInteger biểu diễn chính xác**. Bộ kiểm toán không được báo số dương do overflow hay nhầm đây là một mã lỗi.

## 12. Quy trình kiểm toán kết quả sau khi chạy thuật toán

Dù thuật toán sinh luồng là Ford–Fulkerson, Edmonds–Karp, Dinic, push–relabel, min-cost max-flow bằng potentials hay một mô hình quy hoạch tuyến tính, nên kiểm tra hậu nghiệm:

**Bước 1. Kiểm tra dữ liệu gốc.** Xác thực đỉnh, cạnh, cận dưới–trên, cost, s/t và độ dài vectơ f.

**Bước 2. Kiểm tra capacity từng cạnh.** `lower[e]≤f[e]≤upper[e]`. Không gộp cạnh song song.

**Bước 3. Kiểm tra conservation.** Tính `balance[v]` bằng out−in. Mọi đỉnh trừ s,t phải bằng0; balance[s]=−balance[t]≥0.

**Bước 4. Tính F,C từ cạnh gốc.** `F=balance[s]`; `C=Σ f_e c_e`, kể cả cận dưới và self-loop.

**Bước 5. Nếu đề hỏi MAX FLOW:** Dựng mạng dư bằng `upper−flow` và `flow−lower`; BFS từ s. Nếu t không tới được, in tập S và lát cắt chứng chỉ `F=CUT_BOUND(S,V∖S)`.

**Bước 6. Nếu đề hỏi MIN COST Ở F CỤ THỂ:** Dựng mạng dư có chi phí ±cost; kiểm tra **không có chu trình âm ở bất cứ đâu** bằng Bellman–Ford toàn cục/potentials. Không dùng riêng BFS from s để chứng minh min-cost.

**Bước 7. Nếu đề hỏi MIN-COST MAX-FLOW:** Phải có cả bước 5 **và** bước 6; một chứng chỉ đơn lẻ chưa đủ.

**Bước 8. Đối chiếu test nhỏ.** Với m và capacity nhỏ, liệt kê mọi vectơ luồng nguyên trong cận; tính F,C; so max F và min C theo từng F với các chứng chỉ của bộ kiểm toán.

**Bước 9. Lưu dấu vết lỗi.** Báo rõ cạnh nào sai bounds, đỉnh nào sai conservation, hoặc phát hiện đường tăng/chu trình âm; không chỉ in “Wrong Answer” khi có thông tin chẩn đoán cụ thể.

### Bảng phân biệt các kết luận

| Kết quả kiểm tra | Kết luận hợp lệ |
| --- | --- |
| Bounds sai | Không phải luồng khả thi |
| Bounds đúng nhưng conservation sai | Không phải luồng khả thi |
| Khả thi, t tới được trong mạng dư | Chưa cực đại giá trị |
| Khả thi, t không tới được trong mạng dư | **Cực đại giá trị F** |
| Khả thi, còn chu trình dư âm | Chưa tối thiểu chi phí **ở F hiện tại** |
| Khả thi, không có chu trình dư âm | **Chi phí tối thiểu ở F hiện tại** |
| Max-flow và min-cost cùng F | **Min-cost max-flow** |
| Feasible, F=K và min-cost cùng F | **Min-cost flow với yêu cầu đúng K** |

## 13. Chương trình Java 17+: kiểm tra luồng và chứng chỉ

Chương trình **FlowResultAuditDemo.java** gồm:

- `audit(n,s,t,edges,flow)`: kiểm tra cận cạnh và conservation; tính chính xác F,C bằng BigInteger.
- `maxCertificate(...)`: trên **luồng đã khả thi**, xây mạng dư, tìm tập S reachable từ s và cận lát cắt có trừ lower của cạnh T→S; kết luận maximum khi t không reachable.
- `minCostCertificate(...)`: trên **luồng đã khả thi**, dùng Bellman–Ford từ siêu nguồn ngầm để tìm chu trình âm trong **toàn bộ mạng dư**, kể cả self-loop và thành phần tách rời.
- `bruteSmall(...)`: liệt kê mọi vectơ luồng nguyên cho **mạng nhỏ** để đối chiếu chi phí tối thiểu của một F và giá trị max F.
- `randomizedCrossCheck()`: 150 mạng nhỏ với cạnh song song/khuyên, lower/upper và cost âm/dương, so kết quả chứng chỉ với liệt kê hết.

**Đây là bộ kiểm toán, không tự tạo nghiệm cho mạng lớn.** Cần truyền một vectơ flow ứng viên, ví dụ do Dinic hoặc thuật toán min-cost trả về. Với luồng không khả thi, chương trình chỉ báo lỗi bounds/conservation và **không phát chứng chỉ tối ưu**.

### 13.1. Hợp đồng dữ liệu

- Đỉnh đánh số từ 0, n≥2, s/t hợp lệ và khác nhau.
- Cạnh cho phép self-loop và parallel edges; mỗi cạnh có id là vị trí trong List.
- `0≤lower≤upper≤Long.MAX_VALUE`. Flow ứng viên lưu long và phải thuộc [lower,upper].
- Cost mỗi đơn vị lưu long có thể âm. F,C và cost dư được tính BigInteger.
- Chi phí tuyến tính trên mỗi đơn vị, không có fixed charge, không có điều kiện phi tuyến hoặc luồng nhiều loại hàng hóa.
- Không bắt buộc `flow[s→t]` toàn bộ đi theo một đường: có thể có nhiều đường phân nhánh và các circulation.
- Thời gian audit O(n+m), maxCertificate O(n+m); minCostCertificate dùng Bellman–Ford **O(nm)** theo số cung dư tối đa 2m; bộ nhớ O(n+m), trừ bộ đếm tùy số bit BigInteger.
- BruteSmall có độ phức tạp gần tích `∏_e(upper[e]−lower[e]+1)`; chỉ dùng với miền nhỏ, giới hạn tối đa số tổ hợp trong code.
- Nếu không có luồng khả thi nào, bruteSmall trả `feasible=false` và không có max F.

### 13.2. Toàn bộ chương trình

Lưu tệp **`FlowResultAuditDemo.java`**:

```java
import java.math.BigInteger;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Random;
import java.util.TreeMap;

public class FlowResultAuditDemo {
    record Edge(
            int from, int to,
            long lower, long upper, long cost) {}

    record Audit(
            boolean feasible, String reason,
            BigInteger value, BigInteger totalCost) {}

    record Residual(
            int from, int to, BigInteger cost) {}

    record MaxProof(
            boolean maximum,
            List<Integer> sourceSide,
            BigInteger cutBound) {}

    record MinProof(
            boolean minimumCostAtFixedValue) {}

    record BruteResult(
            boolean feasible,
            BigInteger maxFlow,
            BigInteger minCostAtTarget,
            BigInteger minCostAtMax) {}

    // Cau truc input: khong tu sua mang flow/edge.
    static void validate(
            int n, int source, int sink,
            List<Edge> edges) {
        if (n < 2) {
            throw new IllegalArgumentException(
                    "n must be at least 2");
        }
        if (source < 0 || source >= n
                || sink < 0 || sink >= n) {
            throw new IllegalArgumentException(
                    "source or sink out of range");
        }
        if (source == sink) {
            throw new IllegalArgumentException(
                    "source and sink must differ");
        }

        Objects.requireNonNull(
                edges, "edges must not be null");

        for (Edge e : edges) {
            Objects.requireNonNull(
                    e, "edge must not be null");
            if (e.from() < 0 || e.from() >= n
                    || e.to() < 0 || e.to() >= n) {
                throw new IllegalArgumentException(
                        "vertex index out of range");
            }
            if (e.lower() < 0
                    || e.upper() < e.lower()) {
                throw new IllegalArgumentException(
                        "lower must be between 0 and upper");
            }
        }
    }

    // Feasibility truoc, F/C sau.
    static Audit audit(
            int n, int source, int sink,
            List<Edge> edges, long[] flow) {
        validate(n, source, sink, edges);
        Objects.requireNonNull(
                flow, "flow must not be null");

        if (flow.length != edges.size()) {
            return new Audit(
                    false,
                    "flow array length must equal edge count",
                    null, null);
        }

        BigInteger[] balance = new BigInteger[n];
        Arrays.fill(balance, BigInteger.ZERO);
        BigInteger cost = BigInteger.ZERO;

        for (int i = 0; i < edges.size(); i++) {
            Edge e = edges.get(i);
            long f = flow[i];

            if (f < e.lower() || f > e.upper()) {
                return new Audit(
                        false,
                        "edge " + i + " violates bounds",
                        null, null);
            }

            BigInteger amount = BigInteger.valueOf(f);
            balance[e.from()] =
                    balance[e.from()].add(amount);
            balance[e.to()] =
                    balance[e.to()].subtract(amount);

            BigInteger contribution =
                    amount.multiply(
                            BigInteger.valueOf(e.cost()));
            cost = cost.add(contribution);
        }

        for (int v = 0; v < n; v++) {
            if (v != source && v != sink
                    && balance[v].signum() != 0) {
                return new Audit(
                        false,
                        "conservation failed at vertex " + v,
                        null, null);
            }
        }

        BigInteger value = balance[source];
        if (value.signum() < 0) {
            return new Audit(
                    false,
                    "source flow value must be nonnegative",
                    null, null);
        }

        if (!balance[sink].equals(value.negate())) {
            return new Audit(
                    false,
                    "source/sink imbalance",
                    null, null);
        }

        return new Audit(true, "", value, cost);
    }

    // Cung du THUAN: u->v neu flow<upper,
    // cost = +cost cua canh goc.
    // Cung du NGUOC: v->u neu flow>lower,
    // cost = -cost cua canh goc.
    static List<Residual> residualArcs(
            List<Edge> edges, long[] flow) {
        List<Residual> arcs = new ArrayList<>();

        for (int i = 0; i < edges.size(); i++) {
            Edge e = edges.get(i);
            long f = flow[i];
            BigInteger c = BigInteger.valueOf(e.cost());

            if (f < e.upper()) {
                arcs.add(new Residual(
                        e.from(), e.to(), c));
            }
            if (f > e.lower()) {
                arcs.add(new Residual(
                        e.to(), e.from(), c.negate()));
            }
        }
        return arcs;
    }

    static MaxProof maxCertificate(
            int n, int source, int sink,
            List<Edge> edges, long[] flow) {
        Audit a = audit(
                n, source, sink, edges, flow);
        if (!a.feasible()) {
            throw new IllegalArgumentException(
                    "not feasible: " + a.reason());
        }

        List<List<Integer>> adj = new ArrayList<>();
        for (int v = 0; v < n; v++) {
            adj.add(new ArrayList<>());
        }
        for (Residual r : residualArcs(edges, flow)) {
            adj.get(r.from()).add(r.to());
        }

        boolean[] seen = new boolean[n];
        ArrayDeque<Integer> q = new ArrayDeque<>();
        seen[source] = true;
        q.addLast(source);

        while (!q.isEmpty()) {
            int u = q.removeFirst();
            for (int v : adj.get(u)) {
                if (!seen[v]) {
                    seen[v] = true;
                    q.addLast(v);
                }
            }
        }

        List<Integer> side = new ArrayList<>();
        for (int v = 0; v < n; v++) {
            if (seen[v]) {
                side.add(v);
            }
        }

        if (seen[sink]) {
            // Chua la s-t cut vi sink thuoc S.
            return new MaxProof(false, side, null);
        }

        BigInteger cut = BigInteger.ZERO;
        for (Edge e : edges) {
            if (seen[e.from()] && !seen[e.to()]) {
                cut = cut.add(
                        BigInteger.valueOf(e.upper()));
            } else if (!seen[e.from()] && seen[e.to()]) {
                cut = cut.subtract(
                        BigInteger.valueOf(e.lower()));
            }
        }

        if (!cut.equals(a.value())) {
            throw new AssertionError(
                    "residual cut does not equal flow value");
        }

        return new MaxProof(true, side, cut);
    }

    // Bellman-Ford voi sieu nguon ngam:
    // dist[v]=0 cho MOI v de bat chu trinh am
    // o bat ky thanh phan du nao.
    static MinProof minCostCertificate(
            int n, int source, int sink,
            List<Edge> edges, long[] flow) {
        Audit a = audit(
                n, source, sink, edges, flow);
        if (!a.feasible()) {
            throw new IllegalArgumentException(
                    "not feasible: " + a.reason());
        }

        List<Residual> arcs =
                residualArcs(edges, flow);

        BigInteger[] dist = new BigInteger[n];
        Arrays.fill(dist, BigInteger.ZERO);

        for (int pass = 0; pass < n; pass++) {
            boolean changed = false;

            for (Residual r : arcs) {
                BigInteger candidate =
                        dist[r.from()].add(r.cost());
                if (candidate.compareTo(
                        dist[r.to()]) < 0) {
                    dist[r.to()] = candidate;
                    changed = true;
                }
            }

            if (!changed) {
                return new MinProof(true);
            }
            if (pass == n - 1) {
                return new MinProof(false);
            }
        }

        return new MinProof(true);
    }

    static void show(
            String title, int n,
            int source, int sink,
            List<Edge> edges, long[] flow) {
        Audit a = audit(n, source, sink, edges, flow);

        if (!a.feasible()) {
            System.out.println(
                    title + ": INVALID (" + a.reason() + ")");
            return;
        }

        MaxProof max = maxCertificate(
                n, source, sink, edges, flow);
        MinProof min = minCostCertificate(
                n, source, sink, edges, flow);

        System.out.println(title
                + ": VALID F=" + a.value()
                + " C=" + a.totalCost()
                + ", maximum=" + max.maximum()
                + ", minAtF=" + min.minimumCostAtFixedValue()
                + ", sourceSide=" + max.sourceSide()
                + ", cut=" + (max.cutBound() == null
                        ? "NA" : max.cutBound()));
    }

    // Oracle cham: duyet tat ca vector flow
    // nam trong [lower,upper], CHI cho test nho.
    static List<long[]> enumerateAll(
            List<Edge> edges, long limit) {
        BigInteger product = BigInteger.ONE;
        for (Edge e : edges) {
            BigInteger choices =
                    BigInteger.valueOf(e.upper())
                            .subtract(
                                    BigInteger.valueOf(e.lower()))
                            .add(BigInteger.ONE);
            product = product.multiply(choices);
            if (product.compareTo(
                    BigInteger.valueOf(limit)) > 0) {
                throw new IllegalArgumentException(
                        "too many flow assignments to brute force");
            }
        }

        List<long[]> assignments = new ArrayList<>();
        enumerateAt(
                edges, 0, new long[edges.size()],
                assignments);
        return assignments;
    }

    static void enumerateAt(
            List<Edge> edges, int index,
            long[] candidate, List<long[]> assignments) {
        if (index == edges.size()) {
            assignments.add(candidate.clone());
            return;
        }

        Edge e = edges.get(index);
        // Break TRUOC x++ khi x==upper, de khong
        // tran long neu upper=Long.MAX_VALUE.
        for (long x = e.lower(); ; x++) {
            candidate[index] = x;
            enumerateAt(
                    edges, index + 1, candidate, assignments);
            if (x == e.upper()) {
                break;
            }
        }
    }

    static BruteResult bruteSmall(
            int n, int source, int sink,
            List<Edge> edges, BigInteger targetF) {
        validate(n, source, sink, edges);
        Objects.requireNonNull(
                targetF, "targetF must not be null");

        List<long[]> assignments = enumerateAll(
                edges, 200_000);

        TreeMap<BigInteger, BigInteger> best =
                new TreeMap<>();

        for (long[] f : assignments) {
            Audit a = audit(
                    n, source, sink, edges, f);
            if (a.feasible()) {
                best.merge(
                        a.value(), a.totalCost(),
                        BigInteger::min);
            }
        }

        if (best.isEmpty()) {
            return new BruteResult(
                    false, null, null, null);
        }

        BigInteger max = best.lastKey();
        return new BruteResult(
                true,
                max,
                best.get(targetF),
                best.get(max));
    }

    static void showBrute(
            String title,
            int n, int source, int sink,
            List<Edge> edges, long targetF) {
        BruteResult b = bruteSmall(
                n, source, sink, edges,
                BigInteger.valueOf(targetF));

        System.out.println(title
                + ": minCost(F=" + targetF + ")="
                + b.minCostAtTarget()
                + ", maxF=" + b.maxFlow()
                + ", minCostAtMax=" + b.minCostAtMax());
    }

    // Voi moi mang flow KHA THI duoc liet ke:
    // - khong co duong tang iff F bang brute maxF
    // - khong co chu trinh am iff C bang brute minC(F)
    static void randomizedCrossCheck() {
        Random rng = new Random(20261110L);

        for (int trial = 0; trial < 150; trial++) {
            int n = 2 + rng.nextInt(4);
            int m = rng.nextInt(7);

            List<Edge> edges = new ArrayList<>();
            for (int i = 0; i < m; i++) {
                int from = rng.nextInt(n);
                int to = rng.nextInt(n);
                long upper = rng.nextInt(3);
                long lower = rng.nextInt((int) upper + 1);
                long cost = rng.nextInt(7) - 3;

                edges.add(new Edge(
                        from, to, lower, upper, cost));
            }

            int source = 0;
            int sink = n - 1;
            List<long[]> all = enumerateAll(
                    edges, 200_000);

            TreeMap<BigInteger, BigInteger> best =
                    new TreeMap<>();

            for (long[] flow : all) {
                Audit a = audit(
                        n, source, sink, edges, flow);
                if (a.feasible()) {
                    best.merge(
                            a.value(), a.totalCost(),
                            BigInteger::min);
                }
            }

            if (best.isEmpty()) {
                continue; // Instance khong co luong kha thi.
            }

            BigInteger maximumValue = best.lastKey();

            for (long[] flow : all) {
                Audit a = audit(
                        n, source, sink, edges, flow);
                if (!a.feasible()) {
                    continue;
                }

                boolean actualMax = maxCertificate(
                        n, source, sink, edges, flow)
                        .maximum();
                boolean expectedMax =
                        a.value().equals(maximumValue);

                boolean actualMin = minCostCertificate(
                        n, source, sink, edges, flow)
                        .minimumCostAtFixedValue();
                boolean expectedMin =
                        a.totalCost().equals(
                                best.get(a.value()));

                if (actualMax != expectedMax
                        || actualMin != expectedMin) {
                    throw new AssertionError(
                            "oracle mismatch in trial " + trial
                            + ": F=" + a.value()
                            + ", C=" + a.totalCost());
                }
            }
        }

        System.out.println(
                "Random exhaustive: PASS (150 graphs)");
    }

    public static void main(String[] args) {
        List<Edge> base = List.of(
                new Edge(0, 1, 0, 3, 2),
                new Edge(0, 2, 0, 2, 4),
                new Edge(1, 2, 0, 2, -1),
                new Edge(1, 3, 0, 2, 3),
                new Edge(2, 3, 0, 3, 1),
                new Edge(0, 3, 0, 1, 10));

        show("Expensive F4", 4, 0, 3,
                base, new long[]{2, 2, 0, 2, 2, 0});
        show("Cheap F4", 4, 0, 3,
                base, new long[]{3, 1, 2, 1, 3, 0});
        show("Max F6", 4, 0, 3,
                base, new long[]{3, 2, 1, 2, 3, 1});
        show("Invalid capacity", 4, 0, 3,
                base, new long[]{4, 0, 0, 0, 0, 0});
        show("Invalid balance", 4, 0, 3,
                base, new long[]{2, 1, 0, 1, 1, 0});

        List<Edge> lowerNetwork = List.of(
                new Edge(0, 1, 1, 3, 1),
                new Edge(1, 2, 0, 3, 2),
                new Edge(2, 1, 1, 1, 0),
                new Edge(0, 2, 0, 2, 4));

        show("Lower-bound max", 3, 0, 2,
                lowerNetwork, new long[]{2, 3, 1, 2});
        show("Below lower", 3, 0, 2,
                lowerNetwork, new long[]{0, 0, 0, 0});

        List<Edge> cycleNetwork = List.of(
                new Edge(0, 2, 0, 1, 5),
                new Edge(0, 1, 0, 1, 0),
                new Edge(1, 0, 0, 1, -3));

        show("Cycle not cancelled", 3, 0, 2,
                cycleNetwork, new long[]{1, 0, 0});
        show("Cycle cancelled", 3, 0, 2,
                cycleNetwork, new long[]{1, 1, 1});

        List<Edge> extreme = List.of(
                new Edge(
                        0, 1, 0, 2, Long.MIN_VALUE));
        show("Extreme cost", 2, 0, 1,
                extreme, new long[]{2});

        showBrute("Brute base", 4, 0, 3,
                base, 4);
        showBrute("Brute lower", 3, 0, 2,
                lowerNetwork, 4);
        showBrute("Brute cycle", 3, 0, 2,
                cycleNetwork, 1);

        try {
            audit(2, 0, 1,
                    List.of(new Edge(0, 1, 2, 1, 0)),
                    new long[]{1});
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "Bad spec: " + ex.getMessage());
        }

        try {
            audit(2, 0, 1,
                    List.of(new Edge(0, 2, 0, 1, 0)),
                    new long[]{1});
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "Bad endpoint: " + ex.getMessage());
        }

        try {
            audit(2, 0, 0, List.of(), new long[0]);
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "Bad source: " + ex.getMessage());
        }

        randomizedCrossCheck();
    }
}
```

Biên dịch và chạy với **JDK 17 trở lên**:

```bash
javac FlowResultAuditDemo.java
java FlowResultAuditDemo
```

**Stdout chính xác:**

```text
Expensive F4: VALID F=4 C=20, maximum=false, minAtF=false, sourceSide=[0, 1, 2, 3], cut=NA
Cheap F4: VALID F=4 C=14, maximum=false, minAtF=true, sourceSide=[0, 1, 2, 3], cut=NA
Max F6: VALID F=6 C=32, maximum=true, minAtF=true, sourceSide=[0], cut=6
Invalid capacity: INVALID (edge 0 violates bounds)
Invalid balance: INVALID (conservation failed at vertex 1)
Lower-bound max: VALID F=4 C=16, maximum=true, minAtF=true, sourceSide=[0, 1], cut=4
Below lower: INVALID (edge 0 violates bounds)
Cycle not cancelled: VALID F=1 C=5, maximum=true, minAtF=false, sourceSide=[0, 1], cut=1
Cycle cancelled: VALID F=1 C=2, maximum=true, minAtF=true, sourceSide=[0, 1], cut=1
Extreme cost: VALID F=2 C=-18446744073709551616, maximum=true, minAtF=true, sourceSide=[0], cut=2
Brute base: minCost(F=4)=14, maxF=6, minCostAtMax=32
Brute lower: minCost(F=4)=16, maxF=4, minCostAtMax=16
Brute cycle: minCost(F=1)=2, maxF=1, minCostAtMax=2
Bad spec: lower must be between 0 and upper
Bad endpoint: vertex index out of range
Bad source: source and sink must differ
Random exhaustive: PASS (150 graphs)
```

### 13.3. Giải thích các dòng output

**Expensive F4:** Tất cả ràng buộc thỏa; giá trị4 và cost20 tính đúng. Nhưng còn đường tăng tới t, nên không max. Còn chu trình âm trong mạng dư giúp giảm chi phí cùng F, nên không min-cost.

**Cheap F4:** Cùng F=4 nhưng cost14; không còn chu trình dư âm nên **min-cost tại F=4**. Chưa max vì có thể tăng từ F=4 tới F=6.

**Max F6:** Tất cả đường ra khỏi nguồn bão hòa, BFS residual không tới đích. Cut từ S={0} có bound6, bằng F6. Mạng dư không có chu trình âm nên luồng **min-cost trong các luồng F=6**.

**Invalid capacity:** Cạnh e0 chỉ có upper3 nhưng mang4, lỗi ngay từ bounds. Không phát chứng chỉ dù một số phép tính khác có thể vẫn ra số.

**Invalid balance:** Mọi cạnh đều nằm trong cận nhưng đỉnh1 nhận2 và chỉ gửi1, nên lỗi bảo toàn. Đây là lỗi hoàn toàn khác lỗi cap.

**Lower-bound max:** F4,C16 là luồng hợp lệ. S={0,1}, cut bound bằng 3+2−1=4; phép trừ lower của cạnh 2→1 là thiết yếu.

**Below lower:** Cạnh e0 có lower1 nhưng flow0, nên ứng viên sai; không suy ra **cả mạng** vô nghiệm.

**Cycle not cancelled:** F1 là cực đại vì cạnh duy nhất tới t có cap1, nhưng C5 chưa tối ưu: chu trình dư 0→1→0 có cost−3. Sau đẩy chu trình, **Cycle cancelled** vẫn F1 nhưng C2 và là min-cost.

**Extreme cost:** Cạnh có cost=Long.MIN_VALUE, mang hai đơn vị. BigInteger trả đúng `−18446744073709551616`, vượt miền long mà không tràn.

**Brute base/lower/cycle:** Liệt kê hết với capacity nhỏ xác nhận maxF và minCost tại F tương ứng, độc lập với chứng chỉ dựa trên mạng dư.

**Random exhaustive:** 150 đồ thị nhỏ ngẫu nhiên, trong đó có thể có khuyên, cạnh song song, cận dưới và cost âm. Với mỗi luồng khả thi được liệt kê, chương trình so:

```text
maxCertificate.maximum == (F == bruteMaxF)

minCostCertificate.minimum ==
    (C == bruteMinimumCostAtThisF)
```

Nếu có bất kỳ sai khác, chương trình ném AssertionError chứ không in PASS. Đây là một kiểm thử mạnh cho **logic chứng chỉ**, không chỉ kiểm tra vài output mẫu.

### 13.4. Vì sao mã không tính direct max-flow bằng Dinic?

Mục tiêu của bài là **kiểm tra kết quả**, không phải triển khai thêm một solver khác. Bộ kiểm toán chỉ cần:

- Một luồng ứng viên đã được sinh bởi thuật toán bên ngoài.
- Điều kiện feasibility từ cạnh gốc.
- Đồ thị residual để kiểm tra còn đường tăng hay không.
- Chi phí residual để kiểm tra còn chu trình âm hay không.

Việc **không sinh nghiệm mới** làm bộ kiểm toán có thể được dùng như một lớp test độc lập cho nhiều lời giải Dinic, Edmonds–Karp, Push–Relabel, min-cost-flow hoặc bộ giải tối ưu khác, miễn output có cùng quy ước.

Nếu cần tự tìm một luồng tối ưu trên mạng lớn, hãy dùng thuật toán phù hợp **rồi đưa vectơ f thu được vào hàm audit**; không chạy `bruteSmall` trên input lớn.

## 14. Độ phức tạp và giới hạn triển khai

Gọi n là số đỉnh, m là số cạnh gốc. Mạng dư có tối đa 2m cung.

| Thao tác | Thời gian | Bộ nhớ phụ |
| --- | --- | --- |
| Kiểm tra cấu trúc, bounds, conservation và tính F,C | O(n+m) phép toán BigInteger | O(n) balances |
| Xây residual arcs | O(m) | O(m) |
| BFS tìm đường tăng và tập S | O(n+m) | O(n+m) |
| Tính cut bound | O(m) | O(1) ngoài kết quả |
| Bellman–Ford toàn cục tìm chu trình âm | O(nm) | O(n+m) |
| Liệt kê mọi luồng trong cận | Gần `∏(upper−lower+1)` vectơ, mỗi vectơ audit O(n+m) | Có thể rất lớn, chỉ dùng cho test nhỏ |

**Độ phức tạp BigInteger:** Các con số O(...) là theo **số thao tác số học**, mỗi phép cộng/so sánh/nhân BigInteger có chi phí phụ thuộc độ dài bit. Trong mạng có cost rất lớn hoặc rất nhiều cạnh, cần tính cả chi phí xử lý số lớn; mã cố ý ưu tiên **tính đúng và chứng chỉ kiểm toán** hơn tối ưu hằng số.

**BruteSmall không áp dụng cho capacity lớn.** Chương trình giới hạn tích số lựa chọn để tránh một vòng lặp không kết thúc trong thực tế; đây là công cụ kiểm thử, không phải thuật toán giải tối ưu đa thức.

### 14.1. Chứng chỉ có cần cắt hết mọi cạnh không?

Để chứng minh max-flow, chỉ cần một s–t cut có capacity bound bằng F. Không bắt buộc đó là lát cắt duy nhất, cũng không bắt buộc S={s}. Tập reachable từ s trong residual là lựa chọn tiện lợi và tự nhiên vì cung dư từ S sang T không còn capacity.

### 14.2. Một lời giải cost tối ưu có nhất thiết duy nhất không?

Không. Nếu residual có chu trình tổng cost0, có thể điều chỉnh luồng quanh chu trình ấy mà giữ cả F và C. Vì vậy hai vectơ flow khác nhau nhưng cùng F,C vẫn có thể đều tối ưu.

### 14.3. Nếu capacity/cost là số thực

Các chứng chỉ toán học vẫn có phiên bản cho dữ liệu thực trong những giả thiết thích hợp, nhưng code dùng **long/BigInteger** để đạt kết quả **chính xác** cho luồng nguyên. Nếu dùng double, sai số khi kiểm tra `balance==0`, so sánh cap hoặc xác định chu trình âm có thể gây kết luận sai. Khi input là số tiền decimal, cân nhắc nhân tỉ lệ sang số nguyên, BigDecimal hoặc rational và định nghĩa tolerance phù hợp. **Không** dùng EPS tùy tiện trong comparator của cấu trúc dữ liệu.

## 15. Những lỗi thường gặp

1. **Chỉ kiểm tra total flow mà không kiểm tra từng cạnh.** Tổng có vẻ hợp lý nhưng một cạnh có thể vượt cap.
2. **Chỉ kiểm tra upper mà quên lower.** Luồng dưới cận dưới không hợp lệ.
3. **Gộp các cạnh song song thành một cạnh rồi kiểm tra tổng cap.** Một cạnh riêng có thể đang vi phạm.
4. **Không kiểm tra conservation ở mọi đỉnh trung gian.** Luồng có thể “biến mất” hoặc “tự sinh ra” tại đỉnh.
5. **Tính value bằng tổng cạnh ra khỏi nguồn mà không trừ cạnh đi vào.** Sai nếu có circulation hoặc cung quay về s.
6. **Tính value bằng tổng cạnh vào đích mà không trừ cạnh đi ra.** Sai nếu t có cạnh ra.
7. **Đổi nhầm dấu balance thành in−out nhưng dùng công thức out−in.** Nguồn/đích sẽ đảo dấu.
8. **Cho rằng mọi cạnh từ s đều phải có flow dương.** Luồng hợp lệ có thể không dùng một số cạnh.
9. **Cho rằng mỗi luồng phải đi theo một đường đơn duy nhất.** Flow có thể chia nhánh và chứa các tuần hoàn.
10. **Coi một candidate lỗi là bằng chứng instance vô nghiệm.** Có thể tồn tại candidate khác hợp lệ.
11. **Chỉ đếm số cạnh mang luồng thay vì tổng lượng luồng.** Một cạnh flow5 là năm đơn vị, không phải một.
12. **Quên nhân cost với flow.** Chi phí của cạnh là `f_e*c_e`.
13. **Đếm thêm chi phí của cung dư ngược vào output cuối.** Reverse residual chỉ là quyền điều chỉnh flow của cạnh gốc.
14. **Quên chi phí nền của lower bounds.** Khi dùng `f=l+x`, cần cộng cả `Σl*c`.
15. **Dùng long nhân flow*cost dù tích có thể tràn.** Chuyển lên BigInteger trước nhân.
16. **Tính balance bằng int khi nhiều cạnh lớn.** Tổng có thể vượt int/long.
17. **Coi chi phí âm là input sai.** Min-cost flow có thể có chi phí đơn vị âm, nhưng phải xử lý đúng chu trình âm.
18. **Từ max-flow suy ra min-cost max-flow.** Max chứng minh F, không chứng minh C.
19. **Từ min-cost cùng F suy ra F cực đại.** Có thể tăng F nữa.
20. **Dùng dư ngược bằng flow thay vì flow−lower.** Có thể làm flow mới thấp hơn lower.
21. **Dùng dư thuận bằng upper thay vì upper−flow.** Có thể tăng quá cap.
22. **Không dựng cung dư ngược.** Không thể sửa những lựa chọn luồng cũ.
23. **Nhầm cung dư ngược với cạnh gốc có hướng ngược.** Chúng là hai cách thay đổi luồng khác nhau.
24. **Quên đảo dấu cost ở cung dư ngược.** Tính sai chi phí khi hủy luồng.
25. **Xem còn đường tăng s→t là chứng chỉ đã cực đại.** Ngược lại: còn đường tăng nghĩa là **chưa** cực đại.
26. **Tính min-cut như tổng upper một chiều khi có lower của cạnh T→S.** Cần trừ `Σ lower(T→S)`.
27. **In cut bound khi t vẫn ở tập reachable S.** S đó chưa phải một s–t cut.
28. **Dùng min-cut trước khi chứng minh f khả thi.** Một cut không hợp thức hóa các conservation sai.
29. **Chỉ tìm chu trình âm reachable từ s.** Chu trình âm ở nơi khác cũng có thể cải thiện fixed-F cost.
30. **Tưởng không còn đường tăng là không còn chu trình âm.** Hai điều kiện khác nhau.
31. **Nhầm chu trình cost0 với chu trình âm.** Cycle cost0 tạo nghiệm khác cùng chi phí, không chứng minh chưa tối ưu.
32. **Xóa self-loop khỏi phép tính cost.** Self-loop mang flow vẫn làm thay đổi tổng cost.
33. **Bỏ qua self-loop âm khi kiểm tra min-cost.** Nó là chu trình dư một đỉnh.
34. **Dùng `-Long.MIN_VALUE` trong long.** Giá trị toán học không biểu diễn được; dùng BigInteger.negate.
35. **Sử dụng `Long.MAX_VALUE` làm INF để kiểm toán cost tổng quát.** Cost có thể bằng hoặc vượt nó; BigInteger và trạng thái riêng tốt hơn.
36. **Làm tròn chi phí thực rồi tuyên bố chứng chỉ exact.** Sai số có thể đổi dấu chu trình gần 0.
37. **Cho rằng mọi bài min-cost đều phải maximize F.** Có bài yêu cầu đúng K đơn vị, không phải max.
38. **Nhầm min-cost tại F với min-cost khi F không bị ràng buộc.** Nếu không bắt buộc gửi hàng, f=0 có thể là lựa chọn, nhưng cost âm có thể khiến một circulation khác tốt hơn.
39. **Quên giới hạn các cạnh sau khi biến đổi lower bounds.** Capacity mới là upper−lower.
40. **Thêm t→s trong circulation reduction rồi tính nó như cạnh gốc.** Cạnh phụ chỉ dùng để xét khả thi.
41. **Nhập b[v] sai dấu trong chuyển đổi lower.** Với b=inLower−outLower, phải thêm SS→v nếu b>0.
42. **Không bão hòa tất cả cạnh từ SS nhưng vẫn báo feasible.** Điều kiện circulation reduction chưa thỏa.
43. **Nhầm capacity còn lại với luồng đã gửi.** Residual capacity không phải f của cạnh gốc.
44. **Không lưu ID cạnh khi có parallel edges.** Không thể kiểm toán từng cạnh.
45. **Bỏ cận F≥0 trong mô hình s→t đang dùng.** Một tuần hoàn có thể tạo giá trị ròng âm nếu cho phép mà không điều chỉnh mục tiêu.
46. **Kết luận “không có âm cycle” từ một BFS hoặc Dijkstra không xử lý cạnh âm.** Cần phép kiểm tra negative cycle toàn cục đúng.
47. **Chỉ kiểm thử mạng không cost âm và không lower.** Các trường hợp này không phát hiện nhiều lỗi quan trọng.
48. **Dùng brute force cho mạng lớn.** Số gán có thể tăng theo cấp số nhân.
49. **Không thử luồng bằng 0, capacity0, self-loop và các cạnh song song.** Đây là những ca phát hiện lỗi mảng và cập nhật residual.
50. **Không tách kiểm toán khỏi thuật toán sinh luồng.** Dùng lại chính logic lỗi của solver để tự kiểm tra có thể bỏ lọt lỗi; chứng chỉ độc lập đáng tin hơn.

## 16. Bài tập có đáp án

**Bài 1.** Nêu hai ràng buộc cơ bản để một vectơ f là luồng khả thi khi không có lower bounds.

**Đáp án:** Mỗi cạnh `0≤f_e≤capacity_e`; mọi đỉnh trung gian có tổng flow vào bằng tổng flow ra. Nguồn/đích phải có flow ròng đối nhau và F≥0 theo mô hình này.

**Bài 2.** Một cạnh có lower=2, upper=5, f=1. Hợp lệ không?

**Đáp án:** Không, vì 1<2. Kiểm tra conservation không thể sửa lỗi vi phạm cận này.

**Bài 3.** Mạng có cạnh 0→1 flow5 và 1→0 flow2, với s=0,t=1. Giá trị F bằng bao nhiêu?

**Đáp án:** `F=5−2=3`, không phải 5.

**Bài 4.** Ở một đỉnh trung gian v, tổng vào là 7, tổng ra là 5. Có phải luồng khả thi không?

**Đáp án:** Không, vì balance[v]=5−7=−2, vi phạm bảo toàn.

**Bài 5.** Chi phí một cạnh cost=−3, f=4 là bao nhiêu?

**Đáp án:** `4×(−3)=−12`. Cost âm được phép trong mô hình min-cost.

**Bài 6.** Với vectơ f_A=[2,2,0,2,2,0] của mạng sáu cạnh, F và C là gì?

**Đáp án:** `F=4,C=20`. Mọi cạnh thỏa cận và các đỉnh trung gian cân bằng, nhưng chưa tối ưu.

**Bài 7.** Vì sao f_B=[3,1,2,1,3,0] rẻ hơn f_A?

**Đáp án:** Cùng F=4, f_B có cost14 thay vì20; nó dùng cạnh 1→2 có cost−1 và phân bổ luồng tốt hơn theo capacity các cạnh khác.

**Bài 8.** Giá trị max F trên mạng sáu cạnh là bao nhiêu?

**Đáp án:** `F_max=6`, do tổng capacity các cạnh rời nguồn0 là 3+2+1=6 và có luồng hợp lệ đạt bằng6.

**Bài 9.** Nếu một luồng đã khả thi mà vẫn tồn tại đường s→t trong residual network, nó có max-flow không?

**Đáp án:** Không. Có thể tăng một lượng dương theo đường dư đó, nên F chưa cực đại.

**Bài 10.** Công thức capacity dư thuận và ngược cho cạnh lower l, upper u, flow f?

**Đáp án:** Dư thuận `u−f`; dư ngược `f−l`. Chỉ thêm cung nếu capacity tương ứng >0.

**Bài 11.** Cho cạnh u→v cost7, nếu giảm flow 1 bằng cung dư ngược v→u thì cost thay đổi thế nào?

**Đáp án:** Tổng cost giảm7; residual cost của cung ngược là −7.

**Bài 12.** Một chu trình dư có cost−4 và residual capacity nhỏ nhất3. Đẩy δ=2 quanh chu trình làm F,C đổi thế nào?

**Đáp án:** F giữ nguyên, C giảm `2×4=8`.

**Bài 13.** Tại sao không có chu trình dư âm là chứng chỉ min-cost khi cố định F?

**Đáp án:** Hiệu giữa hai luồng khả thi cùng F là tuần hoàn trong residual; nếu tồn tại nghiệm rẻ hơn, tuần hoàn cải thiện phải chứa chu trình có cost âm. Không có chu trình âm thì không có cải thiện.

**Bài 14.** Có thể chỉ tìm chu trình âm từ nguồn s không?

**Đáp án:** Không. Một chu trình âm ở thành phần khác cũng có thể thêm circulation giảm cost mà không đổi F; cần phát hiện toàn cục.

**Bài 15.** Khi dùng Bellman–Ford để tìm chu trình âm mọi nơi, khởi tạo dist[v] ra sao?

**Đáp án:** Đặt dist[v]=0 cho tất cả v, tương đương có một siêu nguồn cost0 tới mọi đỉnh. Nếu còn relax ở lượt thứ n thì có chu trình âm.

**Bài 16.** Một luồng đã max F nhưng vẫn có chu trình dư âm. Nó có phải min-cost max-flow không?

**Đáp án:** Không. Nó có giá trị F cực đại nhưng còn có thể giảm C mà giữ F không đổi.

**Bài 17.** Với mạng nhỏ gồm 0→2 cap1,cost5; 0→1 cap1,cost0; 1→0 cap1,cost−3, f=[1,0,0], chứng minh chưa min-cost.

**Đáp án:** Chu trình 0→1→0 có cost−3 và dư capacity1. Thêm một đơn vị ở hai cạnh tạo f'=[1,1,1], F vẫn1 nhưng C từ5 xuống2.

**Bài 18.** Viết công thức min-cut khi có lower bounds.

**Đáp án:** `cutBound(S,T)=Σupper(S→T)−Σlower(T→S)`. Luồng ròng F không thể vượt cận này.

**Bài 19.** Trong ví dụ lower bounds, S={0,1}, T={2}, upper(S→T)=5 và lower(T→S)=1. Cận cut là?

**Đáp án:** `5−1=4`; ứng viên đạt F4 nên cực đại.

**Bài 20.** f=[0,0,0,0] trên mạng có lower e0=1 và e2=1 có khả thi không?

**Đáp án:** Không. Dù mọi balance=0, luồng vi phạm cận dưới của hai cạnh.

**Bài 21.** Khi đặt f=l+x, capacity của x và chi phí tổng sau biến đổi là gì?

**Đáp án:** `0≤x≤upper−lower`; tổng cost `Σlower*c + Σx*c`.

**Bài 22.** Với b[v]=sumInLower−sumOutLower, trường hợp nào thêm cạnh SS→v?

**Đáp án:** Khi `b[v]>0`, thêm SS→v capacity b[v]; khi b[v]<0 thêm v→TT capacity −b[v].

**Bài 23.** Muốn kiểm tra có tồn tại luồng s→t đúng K bằng circulation reduction, cần thêm cạnh phụ nào?

**Đáp án:** Thêm cạnh t→s có lower=upper=K, rồi chuyển lower bounds thành demands và kiểm tra bão hòa cạnh từ SS. Không tính cạnh phụ vào chi phí luồng gốc.

**Bài 24.** Nếu có hai cạnh song song cùng từ u sang v nhưng capacity và cost khác nhau, có thể chỉ lưu một số f(u,v) không?

**Đáp án:** Không nếu cần kiểm tra từng cạnh/cost chính xác. Phải có một flow theo **mỗi id cạnh gốc**.

**Bài 25.** Một self-loop có cost âm và chưa bão hòa có thể làm hỏng kết luận min-cost không?

**Đáp án:** Có. Nó là chu trình dư âm độ dài1, đẩy circulation qua self-loop giảm C mà không đổi F.

**Bài 26.** Nếu một residual cycle có cost0, luồng hiện tại có chắc chưa tối ưu không?

**Đáp án:** Không. Đẩy theo cycle cost0 không làm giảm C; có thể có nhiều nghiệm tối ưu bằng nhau.

**Bài 27.** Luồng cực đại và chi phí nhỏ nhất tại giá trị K khác nhau ở điểm nào?

**Đáp án:** Max-flow tối đa F; min-cost fixed-K yêu cầu F=K và tối thiểu C. Có thể có min-cost ở K<F_max, không phải max-flow.

**Bài 28.** Khi nào một luồng được gọi là min-cost max-flow?

**Đáp án:** Nó khả thi, đạt **giá trị F lớn nhất**, và trong các luồng có giá trị ấy có **tổng chi phí C nhỏ nhất**; cần cả chứng chỉ không đường tăng và không chu trình dư âm.

**Bài 29.** Vì sao `Long.MIN_VALUE` có thể gây lỗi khi dựng residual cost ngược?

**Đáp án:** Giá trị `−Long.MIN_VALUE` không biểu diễn được bằng long, nên tính nguyên thủy có thể tràn; BigInteger.negate xử lý đúng.

**Bài 30.** BruteSmall trả nghiệm cho toàn bộ mạng thực tế không?

**Đáp án:** Không. Nó liệt kê gần `∏(upper−lower+1)` vectơ luồng, chỉ dùng làm oracle khi mỗi upper−lower nhỏ và số cạnh ít.

## 17. Mẫu checklist cuối bài

Trước khi chấp nhận output của một lời giải luồng mạng, kiểm tra:

- [ ] Có đúng n đỉnh, s≠t, endpoints hợp lệ và flow ứng với đúng các cạnh gốc.
- [ ] Mọi cạnh thỏa `lower≤flow≤upper`, không đánh mất cạnh song song.
- [ ] Mọi đỉnh trung gian có `Σout−Σin=0`.
- [ ] Nguồn có balance=F≥0 và đích có balance=−F.
- [ ] Tổng cost là `Σ(flow[e]×cost[e])`, bao gồm lower bắt buộc và self-loop.
- [ ] Chọn kiểu số đủ miền cho balance, F, total cost và residual cost.
- [ ] Nếu mục tiêu là max-flow: chứng minh t không reachable từ s trong residual.
- [ ] Nếu có lower bounds: cut bound dùng `Σupper(S→T)−Σlower(T→S)`.
- [ ] Nếu mục tiêu là min-cost ở F: không còn chu trình âm ở **bất cứ thành phần** nào của residual.
- [ ] Nếu mục tiêu là min-cost max-flow: có cả hai chứng chỉ.
- [ ] Với test nhỏ: so kết quả với liệt kê hết hoặc một oracle độc lập.
- [ ] Không coi một ứng viên không khả thi là bằng chứng bài toán không tồn tại nghiệm.

## Kết luận

**Kiểm tra tính khả thi, giá trị luồng và chi phí kết quả** là ba việc phải làm **theo đúng thứ tự** và tách biệt với việc tìm một lời giải:

1. **Khả thi:** `lower≤f≤upper` cho từng cạnh, bảo toàn ở tất cả đỉnh trung gian, cân bằng nguồn–đích.
2. **Đại lượng:** `F=out(s)−in(s)=in(t)−out(t)`, `C=Σ_e f_e c_e` trên **các cạnh gốc**, tính bằng kiểu số không tràn.
3. **Tối ưu:** Không có đường tăng trong mạng dư để chứng minh **F cực đại**; không có chu trình âm trong toàn bộ mạng dư để chứng minh **C nhỏ nhất ở F cố định**. Một lời giải min-cost max-flow cần **cả hai**.

Cận dưới thay đổi capacity dư ngược thành `f−lower` và công thức lát cắt thành `Σupper(S→T)−Σlower(T→S)`. Cạnh song song, self-loop, circulation và chi phí âm đều hợp lệ theo mô hình, nên cần được kiểm tra đúng chứ không loại bỏ tùy tiện.

Khi lập trình Java, một bộ **auditor độc lập**, dùng **BigInteger** cho tổng luồng/chi phí và đối chiếu test nhỏ với brute force là cách hiệu quả để phát hiện các lỗi tính toán mà một kết quả số cuối cùng khó bộc lộ.
