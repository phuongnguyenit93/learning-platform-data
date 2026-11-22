# Công việc tổng, độ dài đường phụ thuộc và khả năng tăng tốc

## Mục tiêu học tập

Trong nhóm **Thuật toán song song**, một chương trình có thể tạo rất nhiều tác vụ nhưng không vì thế mà tự động chạy nhanh hơn khi tăng số lõi CPU. Một số tác vụ **phải chờ kết quả của tác vụ khác**; một số khác độc lập nhưng lại cạnh tranh băng thông bộ nhớ, bộ nhớ đệm hoặc khóa đồng bộ. Để phân tích trước khi cài đặt, ta cần ba đại lượng:

- **Work — công việc tổng**, ký hiệu `W` hoặc `T_1`: tổng lượng công việc cần thực hiện nếu xét tất cả tác vụ.
- **Span — độ dài đường phụ thuộc dài nhất**, ký hiệu `S`, `D` hoặc `T_\infty`: thời gian nhỏ nhất về mặt phụ thuộc khi có số bộ xử lý không bị giới hạn, trong mô hình lý tưởng.
- **Parallelism — mức song song tiềm năng**, ký hiệu `W/S` khi S>0: số bộ xử lý trung bình có thể khai thác trước khi đường găng trở thành nút thắt.

Bất đẳng thức nền tảng với P bộ xử lý đồng nhất trong mô hình công việc được xác định rõ:

\[
\boxed{T_P\ge\max\left(\frac WP,\ S\right).}
\]

Hai giới hạn này có ý nghĩa khác nhau: **không thể làm xong nhiều công việc hơn năng lực tổng của P bộ xử lý**, và **không thể đi tắt qua một chuỗi phụ thuộc bắt buộc**.

Bài học giúp bạn:

1. Biểu diễn thuật toán song song bằng **DAG tác vụ có trọng số**.
2. Tính work và span, tìm **critical path** bằng sắp xếp topo và quy hoạch động trên DAG.
3. Phân biệt **số tác vụ**, **mức song song đồng thời** và **work/span parallelism**.
4. Suy ra cận dưới cho thời gian, cận trên cho tăng tốc, và giới hạn của lịch tham lam (*greedy scheduling*).
5. Hiểu ví dụ **tổng tuần tự so với phép cộng dạng cây** và phân biệt reduction với prefix scan.
6. Phân biệt **speedup**, **efficiency**, strong scaling, weak scaling và các mô hình Amdahl/Gustafson.
7. Chọn độ hạt tác vụ, ngưỡng chia việc và hiểu vai trò của **work stealing**.
8. Cài ví dụ **Java 17+ ForkJoinPool** đúng về phụ thuộc, dữ liệu và cách đếm phép cộng.
9. Tránh race condition, false sharing, đồng bộ quá mức và số liệu benchmark gây hiểu lầm.
10. Kiểm thử độc lập các bất biến work/span, output và xử lý tình huống biên.

---

## 1. Công việc tuần tự khác cấu trúc phụ thuộc

Xét tổng:

\[
1+2+3+4+5+6+7+8.
\]

Về mặt toán học, kết quả là:

\[
\boxed{36}.
\]

Có nhiều cách thực hiện phép cộng.

**Cộng tuần tự:**

```text
s = 1
s = s + 2
s = s + 3
...
s = s + 8
```

Có **7 phép cộng**, nhưng mỗi phép cộng cần kết quả của phép trước, tạo một chuỗi phụ thuộc dài 7 bước.

**Cộng theo cây cân bằng:**

```text
Tầng 1:    1+2     3+4     5+6     7+8
           (3)     (7)     (11)    (15)

Tầng 2:        3+7             11+15
               (10)            (26)

Tầng 3:                 10+26
                        (36)
```

Vẫn chỉ **7 phép cộng**, nhưng đường phụ thuộc dài nhất chỉ **3 phép cộng**. Các phép cộng ở cùng tầng có thể thực hiện đồng thời nếu có đủ tài nguyên.

Đây là khác biệt giữa:

\[
\text{Work}=7
\]

và:

\[
\text{Span}=3.
\]

**Hai thuật toán có work như nhau vẫn có span rất khác nhau.** Đó là lý do phân tích chỉ dựa vào độ phức tạp thời gian tuần tự O(n) không đủ để dự đoán khả năng chạy song song.

### 1.1. Tác vụ độc lập và tác vụ phụ thuộc

Nếu một phép cộng cần hai giá trị được tạo từ những phép cộng trước, nó không được bắt đầu cho đến khi **cả hai đầu vào sẵn sàng**.

- Hai phép cộng không dùng kết quả của nhau: có thể chạy đồng thời.
- Một phép cộng phụ thuộc vào kết quả của phép khác: phải theo đúng thứ tự.
- Cùng xuất hiện trong mã với hai lệnh `fork` không có nghĩa hai tác vụ **thực sự độc lập**.

Lập lịch song song phải tôn trọng những quan hệ trước–sau ấy.

### 1.2. Phạm vi của mô hình chi phí

Ở ví dụ cây cộng, ta **chỉ đếm phép cộng**, mỗi phép cộng có chi phí 1 đơn vị. Việc đọc phần tử từ bộ nhớ, tạo tác vụ Java, gửi việc cho thread pool, `fork`, `join` và bộ nhớ đệm chưa được tính trong W=7,S=3.

Nếu đếm cả các công việc ấy, work/span thực tế của chương trình sẽ khác. **Mô hình lý tưởng là công cụ phân tích cấu trúc**, không phải đồng hồ đo thời gian CPU ngoài đời.

---

## 2. Biểu diễn phụ thuộc bằng DAG

**DAG** (*directed acyclic graph*) là đồ thị có hướng không có chu trình. Trong mô hình tác vụ:

- Mỗi đỉnh v là một tác vụ cần chạy.
- Cạnh `u\to v` nghĩa là **v không thể bắt đầu trước khi u hoàn thành**.
- Trọng số `w(v)>0` là thời lượng hoặc lượng công việc được gán cho tác vụ v trong mô hình.
- Không có chu trình: nếu u chờ v và v lại chờ u qua một vòng, lịch không thể hoàn thành.

### 2.1. Work trên DAG có trọng số

Nếu mọi tác vụ đều phải thực hiện đúng một lần:

\[
\boxed{
W=\sum_{v\in V}w(v).
}
\]

Trong mô hình tác vụ đơn vị, `w(v)=1` và:

\[
W=|V|.
\]

Không nhầm **work** với **số cạnh**. Cạnh biểu diễn sự phụ thuộc; một cạnh không nhất thiết là tác vụ tốn thêm thời gian, trừ khi mô hình đã quy định có công việc truyền thông hoặc đồng bộ tương ứng.

### 2.2. Span: đường có tổng trọng số lớn nhất

Với mọi đường có hướng `\pi=v_1\to v_2\to\cdots\to v_k`:

\[
length(\pi)=\sum_{i=1}^{k}w(v_i).
\]

**Span** là:

\[
\boxed{
S=\max_{\pi\text{ là đường trong DAG}}
\sum_{v\in\pi}w(v).
}
\]

Đường đạt giá trị này gọi là **critical path** hoặc **đường găng**.

Vì các tác vụ trên cùng một đường phải hoàn tất theo thứ tự, không thể chạy DAG xong trong thời gian nhỏ hơn S dù có vô hạn bộ xử lý.

### 2.3. DAG không có một điểm đầu duy nhất

Một DAG có thể có nhiều **source** (đỉnh không có cạnh vào) và nhiều **sink** (đỉnh không có cạnh ra). Tất cả source có thể bắt đầu độc lập, còn thời điểm hoàn tất toàn bộ là thời điểm **tác vụ hoàn thành cuối cùng**.

Công thức span phải xét **mọi đường**, không chỉ đường bắt đầu từ một đỉnh 0 cố định.

### 2.4. Topological order

Một thứ tự topo đưa mọi tác vụ u **trước** mọi tác vụ v mà nó đi tới qua cạnh `u\to v`.

Có thể dùng thuật toán Kahn:

1. Đếm `indegree[v]`.
2. Đưa mọi đỉnh bậc vào 0 vào queue.
3. Lấy u khỏi queue, xử lý u.
4. Với mỗi `u\to v`, giảm indegree[v]; nếu về 0 thì thêm v.
5. Nếu xử lý chưa đủ |V| đỉnh, đồ thị có chu trình.

Kahn tốn:

\[
\boxed{O(|V|+|E|)}
\]

về thời gian, và O(|V|+|E|) bộ nhớ cho đồ thị và trạng thái cần thiết.

---

## 3. Tính critical path bằng quy hoạch động DAG

Với mỗi tác vụ v:

\[
start[v]=\max_{u\to v}finish[u],
\]

trong đó với source (không có predecessor), `start[v]=0`.

Khi ấy:

\[
\boxed{
finish[v]=start[v]+w(v).
}
\]

Span:

\[
\boxed{
S=\max_{v\in V}finish[v].
}
\]

Tính `finish` theo thứ tự topo sẽ đảm bảo mọi tiền nhiệm đã được tính trước khi cần cập nhật v.

### 3.1. Truy vết đường găng

Để biết không chỉ độ dài S mà còn **đường nào gây giới hạn**, lưu:

```text
predecessor[v] = u
```

khi `finish[u]` tạo giá trị lớn hơn `start[v]` trước đó.

Cuối cùng lấy v có `finish[v]=S` rồi lần theo predecessor ngược về source, đảo lại thứ tự.

Nếu có nhiều đường cùng độ dài tối đa, một thuật toán có thể trả **bất kỳ một đường găng hợp lệ**. Thứ tự chọn đỉnh hoặc cách xử lý hòa ảnh hưởng đường được trả nhưng **không làm thay đổi S**.

### 3.2. Thuật toán giả

```text
ANALYZE_DAG(durations, edges):
    validate positive task durations
    build adjacency lists and indegrees

    work = sum(durations)
    start[v] = 0 for all vertices
    predecessor[v] = -1 for all vertices

    queue = all zero-indegree vertices

    while queue not empty:
        u = remove-first(queue)
        finish = start[u] + durations[u]

        update global maximum finish

        for each edge (u -> v):
            if finish > start[v]:
                start[v] = finish
                predecessor[v] = u

            indegree[v]--
            if indegree[v] == 0:
                queue.add(v)

    if processed vertices != V:
        reject cycle

    reconstruct critical path
    return work, maximum finish, critical path
```

### 3.3. Độ phức tạp

Mỗi đỉnh xử lý một lần, mỗi cạnh xem một lần:

\[
\boxed{O(V+E)}
\]

thời gian; lưu danh sách kề, indegree và các mảng DP chiếm O(V+E).

Đây là **bài toán đường đi dài nhất trên DAG**, giải được bằng topo DP. Đừng nhầm với bài toán **đường đi dài nhất trên đồ thị có chu trình tùy ý**, vốn không có cùng công thức đơn giản.

### 3.4. Ví dụ DAG sáu tác vụ

Cho tác vụ và thời lượng:

| Tác vụ | ID | Thời lượng |
| --- | ---: | ---: |
| A | 0 | 2 |
| B | 1 | 3 |
| C | 2 | 4 |
| D | 3 | 5 |
| E | 4 | 2 |
| F | 5 | 3 |

Phụ thuộc:

```text
A(2) ----> C(4) -----+
           ^          |
           |          v
B(3) ------+        E(2) ---> F(3)
  |
  +-------> D(5) -----^
```

Chính xác là các cạnh:

```text
0 -> 2
1 -> 2
1 -> 3
2 -> 4
3 -> 4
4 -> 5
```

Work:

\[
W=2+3+4+5+2+3=\boxed{19}.
\]

Thời điểm bắt đầu sớm nhất và kết thúc sớm nhất:

| ID | start | finish | Căn cứ |
| ---: | ---: | ---: | --- |
| 0 | 0 | 2 | Source |
| 1 | 0 | 3 | Source |
| 2 | 3 | 7 | Chờ max(finish 0,finish 1)=3 |
| 3 | 3 | 8 | Chờ finish 1=3 |
| 4 | 8 | 10 | Chờ max(finish 2,finish 3)=8 |
| 5 | 10 | 13 | Chờ finish 4=10 |

Do đó:

\[
\boxed{S=13}.
\]

Một đường găng:

\[
\boxed{1\to3\to4\to5}
\]

với tổng:

\[
3+5+2+3=\boxed{13}.
\]

Mặc dù có sáu tác vụ, parallelism theo work/span chỉ:

\[
\boxed{\frac{19}{13}\approx1.461538}.
\]

Cấp hàng chục bộ xử lý không thể rút ngắn chuỗi tác vụ bắt buộc dài 13 đơn vị trong mô hình này.

---

## 4. Hai định luật cận dưới: work law và span law

Gọi `T_P` là thời gian hoàn thành một DAG trên P bộ xử lý đồng nhất, mỗi bộ xử lý có tốc độ 1 đơn vị work/đơn vị thời gian, với lịch thực thi tôn trọng phụ thuộc.

### 4.1. Work law

Tất cả các bộ xử lý có thể thực hiện tối đa P đơn vị work trong một đơn vị thời gian. Để hoàn thành W đơn vị:

\[
\boxed{T_P\ge\frac WP}.
\]

Ví dụ W=100,P=4 ⇒ không thể nhanh hơn 25 đơn vị thời gian, ngay cả khi mọi tác vụ đều độc lập.

### 4.2. Span law

Mọi tác vụ trên một đường phụ thuộc dài S phải lần lượt hoàn thành. Do đó:

\[
\boxed{T_P\ge S}.
\]

Ví dụ W=100,S=40,P=100 ⇒ vẫn không thể nhanh hơn 40 đơn vị chỉ vì có 100 bộ xử lý.

### 4.3. Kết hợp

\[
\boxed{T_P\ge\max(W/P,S).}
\]

Với tác vụ có thời gian nguyên theo đơn vị rời rạc, có thể làm tròn cận work lên:

\[
\boxed{T_P\ge\max(\lceil W/P\rceil,S).}
\]

**Cận dưới không phải thuật toán lập lịch.** Nó nói thời gian nào là không thể vượt qua, chứ chưa khẳng định có lịch chạy đạt đúng cận.

### 4.4. Cận cho speedup lý tưởng

Trong mô hình lý tưởng, chạy tuần tự cùng DAG có thời gian `T_1=W`, và:

\[
Speedup(P)=\frac{T_1}{T_P}.
\]

Từ hai cận dưới:

\[
\boxed{
Speedup(P)\le\min\left(P,\frac WS\right)
}
\]

nếu S>0.

Ở đây `W/S` là **parallelism trung bình** hay giới hạn tăng tốc do đường găng của DAG cố định khi có thêm bộ xử lý.

Không được hiểu `W/S` là số lõi thực tế đang sử dụng đồng thời ở mọi thời điểm. Ví dụ một tầng cây có bốn phép cộng độc lập, tầng sau hai, cuối một; số tác vụ sẵn sàng thay đổi theo thời gian.

### 4.5. Khi W hoặc S bằng 0

Nếu mô hình chỉ đếm phép cộng, bài toán tổng một phần tử có:

\[
W=0,\quad S=0
\]

vì không cần phép cộng nào. Khi ấy `W/S=0/0` **không xác định**. Điều đó không ngụ ý chương trình thực tế chạy trong 0 ns: còn chi phí đọc giá trị, gọi hàm, cấp phát, v.v.

Chỉ dùng tỉ số `W/S` khi S>0 và work/span được định nghĩa nhất quán.

---

## 5. Brent và lập lịch tham lam

Hai cận dưới chưa nói cách thực thi. Một kết quả nền tảng của lập lịch DAG là **định lý work–span/Brent**, thường được trình bày theo mô hình tác vụ đơn vị và lịch tham lam.

### 5.1. Lịch tham lam (*greedy schedule*)

Trong mỗi bước thời gian, chọn **tối đa P tác vụ đã sẵn sàng** để chạy. Một tác vụ sẵn sàng nếu tất cả predecessor đã hoàn thành.

Lịch "tham lam" ở đây nghĩa là:

- Nếu có ít nhất P tác vụ sẵn sàng, dùng đủ P bộ xử lý.
- Nếu có ít hơn P tác vụ sẵn sàng, chạy tất cả chúng; không cố tình để tác vụ sẵn sàng bị trì hoãn.

### 5.2. Cận trên trong mô hình unit-task

Với W tác vụ đơn vị, span S bước, một lịch tham lam thỏa:

\[
\boxed{
T_P\le\frac{W-S}{P}+S
}
\]

trong mô hình thời gian liên quan; có thể suy ra dạng ít chặt hơn:

\[
\boxed{T_P\le\frac WP+S.}
\]

Với các thời điểm rời rạc, T_P là số bước nguyên; bất đẳng thức vẫn có ý nghĩa khi vế phải là số thực và có thể thêm các dạng làm tròn tùy phát biểu.

### 5.3. Ý tưởng chứng minh

Chia các bước thời gian thành:

- **Full steps**: chạy đủ P tác vụ.
- **Non-full steps**: còn dưới P tác vụ sẵn sàng và chạy tất cả.

Ở một non-full step, mọi tác vụ sẵn sàng đều được thực thi. Một đường găng trong **DAG còn lại** phải bắt đầu tại một tác vụ sẵn sàng, nên span còn lại giảm ít nhất một. Vì vậy có **không quá S non-full steps**.

Gọi F là số full steps, I là số non-full steps. Tổng work:

\[
W\ge PF+I
\]

vì mỗi full step hoàn tất P tác vụ, mỗi non-full step có ít nhất một tác vụ.

Do đó:

\[
F\le\frac{W-I}{P}.
\]

Tổng thời gian:

\[
T_P=F+I
\le\frac WP+\left(1-\frac1P\right)I.
\]

Vì I≤S:

\[
\boxed{
T_P\le\frac WP+\left(1-\frac1P\right)S
=\frac{W-S}{P}+S.
}
\]

### 5.4. Phạm vi của định lý

Đây là phân tích cho mô hình **DAG các tác vụ chi phí đơn vị, P bộ xử lý đồng nhất, không tính overhead**. Với tác vụ có thời lượng khác nhau, preemption, giao tiếp, memory contention hoặc scheduler có overhead, phải quy định mô hình và áp dụng cận phù hợp; không lấy nguyên công thức như lời hứa về wall-clock time trong Java.

**Brent không bảo đảm mọi lịch tùy tiện đều đạt cận**. Một lịch cố tình trì hoãn công việc sẵn sàng có thể chậm hơn nhiều.

### 5.5. Khi P tăng rất lớn

Cận dưới `T_P\ge S` vẫn tồn tại. Khi `P\to\infty`, phần `W/P` tiến về 0, nhưng đường găng không mất.

Vì vậy giảm span thường quan trọng không kém giảm work. Một thuật toán có work tốt mà span tuyến tính có thể tăng tốc rất kém khi P lớn.

---

## 6. Ví dụ định lượng: reduction tám phần tử

Chỉ tính **các phép cộng** cho dãy tám giá trị.

### 6.1. Cộng tuần tự

- Work: `W=7` phép cộng.
- Span: `S=7` phép cộng.
- Parallelism: `W/S=1`.

Ngay cả khi có P=8 bộ xử lý, đường găng vẫn cần 7 phép cộng theo mô hình này. **Không có cấu trúc cộng độc lập** để khai thác.

### 6.2. Cộng dạng cây

Với n=8 là lũy thừa của hai:

\[
\boxed{W=n-1=7}.
\]

Độ sâu cây cân bằng:

\[
\boxed{S=\log_2 n=3}.
\]

Parallelism:

\[
\boxed{W/S=7/3\approx2.333333}.
\]

Các tầng cần lần lượt 4, 2 và 1 phép cộng, nhưng các phép cùng tầng là độc lập.

### 6.3. Giới hạn với P bộ xử lý

| P | Cận dưới nguyên max(ceil(W/P),S) | Lịch chạy theo từng tầng | Speedup của lịch | Efficiency |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 7 | 7 | 7/7 = 1 | 1 |
| 2 | 4 | 4 | 7/4 = 1.75 | 7/8 = 0.875 |
| 4 | 3 | 3 | 7/3 ≈ 2.333333 | 7/12 ≈ 0.583333 |
| 8 | 3 | 3 | 7/3 ≈ 2.333333 | 7/24 ≈ 0.291667 |

**Cách tính lịch tầng:** với m phép cộng độc lập trong một tầng, P bộ xử lý cần `\lceil m/P\rceil` bước. Các tầng phải nối tiếp:

\[
T_P^{\mathrm{level}}
=\sum_{\ell}\left\lceil\frac{m_\ell}{P}\right\rceil.
\]

Với P=2:

\[
\lceil4/2\rceil+\lceil2/2\rceil+\lceil1/2\rceil
=2+1+1=\boxed4.
\]

Với P=4:

\[
1+1+1=\boxed3.
\]

Ở ví dụ này, lịch theo tầng đạt đúng cận dưới. Nhưng không được tổng quát hóa rằng **mọi DAG** hoặc **mọi lịch tầng** đều đạt cận `max(W/P,S)`.

### 6.4. Tại sao P=8 không nhanh hơn P=4?

Tầng cuối chỉ có **một** phép cộng; đường găng có ba tầng. Từ P=4 lên P=8 không thể thực hiện cùng một phép cộng cuối trước khi hai kết quả con có sẵn.

Những bộ xử lý thêm không thay đổi cấu trúc phụ thuộc nên **không xóa span**.

### 6.5. Với n không phải lũy thừa của hai

Ta có thể chia gần đều thành hai nửa rồi giảm tiếp:

- Work vẫn n−1 phép cộng nếu mỗi phần tử chỉ được gộp một lần.
- Span với cây nhị phân cân bằng gần:
  \[
  \boxed{\lceil\log_2 n\rceil}
  \]
  phép cộng trên đường dài nhất, khi n≥2 và mỗi nút trong là một phép cộng.

Ví dụ n=6 có 5 phép cộng và span3; không cần đệm thành tám phần tử với phép cộng giả nếu cách chia cây hỗ trợ hai nửa không bằng nhau.

---

## 7. Work-efficient và span-efficient

Khi cải tiến song song, không nên chỉ đếm số tầng.

### 7.1. Work-efficient

Một thuật toán song song **work-efficient** nếu tổng work có cùng bậc tiệm cận với thuật toán tuần tự tốt nhất đang so sánh.

Ví dụ reduction:

- Tuần tự: O(n) phép cộng.
- Cây song song: O(n) phép cộng.
- Span giảm từ O(n) xuống O(log n).

Đây là một thiết kế tốt: **không tăng work theo bậc** để giảm span.

### 7.2. Span-efficient

Một thuật toán span-efficient có chuỗi phụ thuộc ngắn. Nhưng có thuật toán giảm span bằng cách làm nhiều phép tính thừa.

Ví dụ tính tất cả prefix sum bằng cách độc lập tính `sum(a[0..i])` cho mỗi i:

- Nếu mỗi prefix được tính bằng một cây riêng, span của mỗi truy vấn có thể O(log n).
- Tổng work của n prefix riêng lẻ có thể là O(n²), vì các phần tử bị tính lại nhiều lần.

Tốc độ với ít bộ xử lý có thể **tệ hơn** một thuật toán work-efficient, dù span nhỏ.

### 7.3. Tối ưu đồng thời hai mục tiêu

Giả sử hai thuật toán giải cùng một bài:

| Thuật toán | Work | Span |
| --- | --- | --- |
| A | O(n) | O(n) |
| B | O(n) | O(log n) |
| C | O(n log n) | O(log n) |

Với P đủ lớn và bỏ qua overhead, B thường là thiết kế hấp dẫn: giảm span mạnh mà không nhân thêm work theo bậc. C không chắc tốt hơn B vì span tương đương nhưng work lớn hơn.

Không thể đánh giá chỉ từ một trong hai đại lượng nếu mục tiêu là thời gian trên P hữu hạn.

---

## 8. Reduction và prefix scan khác nhau

### 8.1. Reduction

Input:

```text
[1,2,3,4,5,6,7,8]
```

Output duy nhất:

```text
36
```

Một reduction cộng dạng cây có:

\[
W=n-1,\quad S=O(\log n).
\]

### 8.2. Prefix scan

**Inclusive prefix scan** yêu cầu tất cả tổng tiền tố:

```text
Input:  [1,2,3,4,5,6,7,8]
Output: [1,3,6,10,15,21,28,36]
```

Đầu ra có n giá trị, khác với reduction.

### 8.3. Hillis–Steele scan

Ở vòng k, mỗi phần tử cộng một giá trị cách `2^k` vị trí từ **mảng của vòng trước**, cần dùng snapshot hoặc bộ đệm để tránh đọc giá trị đã bị cập nhật trong cùng vòng.

- Span: O(log n) vòng song song.
- Work: O(n log n) phép cộng.

Đây là ví dụ giảm span nhưng **không work-efficient** so với scan tuần tự O(n).

### 8.4. Blelloch scan

Thuật toán Blelloch dùng hai pha:

1. **Upsweep:** gộp tổng theo cây.
2. **Downsweep:** phân phối các prefix thích hợp theo cây.

Với phép cộng và bản cài đầy đủ đúng:

\[
\boxed{W=O(n),\quad S=O(\log n).}
\]

Đây là scan song song work-efficient, thường được trình bày trước hết dưới dạng **exclusive scan** (giá trị i là tổng các phần tử trước i). Có thể chuyển sang inclusive bằng cách cộng `a[i]` vào exclusive result.

**Không nhầm reduction với scan:** reduction xuất một số, scan xuất n số; cách đếm work khác nhau.

### 8.5. Phép toán phải hợp kết hợp

Các cây reduction/scan có thể đổi cách đặt ngoặc khi phép toán **kết hợp**:

\[
(a\oplus b)\oplus c=a\oplus(b\oplus c).
\]

Cộng số nguyên theo số học toán học là kết hợp. Nhưng với `double` hữu hạn, việc đổi thứ tự phép cộng có thể đổi các bit kết quả do làm tròn; parallel sum có thể sai khác nhỏ với sequential sum mà không phải race condition.

Với số nguyên `long`, phép cộng có thể tràn; dùng `Math.addExact` để phát hiện thay vì âm thầm wrap-around nếu ứng dụng yêu cầu tổng toán học chính xác trong miền long.

---

## 9. Speedup, efficiency và mô hình đo

### 9.1. Speedup

Với cùng bài toán kích thước cố định và cùng tiêu chuẩn đúng:

\[
\boxed{
Speedup(P)=\frac{T_{\mathrm{seq}}}{T_P}.
}
\]

Ở đây `T_{\mathrm{seq}}` nên là thời gian baseline tuần tự được chọn rõ ràng; không nhất thiết đồng nhất với work W nếu baseline là thuật toán khác hoặc môi trường khác.

Ví dụ baseline 80 ms, phiên bản P=4 mất 25 ms:

\[
Speedup(4)=80/25=3.2.
\]

### 9.2. Efficiency

\[
\boxed{
Efficiency(P)=\frac{Speedup(P)}P.
}
\]

Ví dụ speedup3.2 trên P=4:

\[
Efficiency=3.2/4=0.8=80\%.
\]

Efficiency cho biết mức khai thác năng lực P bộ xử lý **so với baseline đã chọn**, không phải % CPU usage trực tiếp từ hệ điều hành.

### 9.3. Lý thuyết và số đo thực khác nhau

Trong mô hình DAG lý tưởng cùng work:

\[
T_1=W,\qquad T_\infty=S.
\]

Nhưng chương trình chạy thực có:

- Tạo và hủy tác vụ.
- Chia công việc, đồng bộ, `join`.
- Cache miss, băng thông và độ trễ bộ nhớ.
- Contention giữa thread.
- Scheduler, hệ điều hành, CPU frequency scaling.
- GC, JIT warmup và phân bổ đối tượng ở Java.

Do đó không được lấy `W/S` làm speedup **đã đo được**. Nó là cận cấu trúc dưới giả thiết rõ ràng.

### 9.4. Superlinear speedup trong thực nghiệm

Đôi khi kết quả đo có `Speedup(P)>P` do cache footprint hoặc yếu tố hệ thống thay đổi khi dùng nhiều bộ xử lý. Điều đó không bác bỏ work law trong **mô hình lý tưởng cố định**: khi so những cấu hình thực tế, chi phí memory/cache và cả lượng công việc hiệu dụng có thể khác.

Cần phân tích và công bố thiết lập benchmark thay vì tuyên bố định lý đã sai.

---

## 10. Định luật Amdahl: tỉ lệ phần tuần tự

Trong một mô hình đơn giản, giả sử:

- Phần `f` thời gian tuần tự của một chương trình **không thể song song hóa**.
- Phần `1-f` có thể chia đều lý tưởng cho P bộ xử lý.
- Không có overhead mới.

Khi ấy:

\[
\boxed{
Speedup_{\mathrm{Amdahl}}(P)
\le\frac{1}{f+(1-f)/P}.
}
\]

Trong trường hợp mô hình lý tưởng này đạt các giả định, dấu ≤ trở thành giá trị dự đoán của mô hình.

### 10.1. Ví dụ f=0.2 và P=8

\[
S_8\le\frac{1}{0.2+0.8/8}
=\frac1{0.3}
=\boxed{3.333333\ldots}.
\]

Ngay cả với số bộ xử lý tăng vô hạn:

\[
\lim_{P\to\infty}S_P\le\frac1f.
\]

Với f=0.2:

\[
\boxed{S_\infty\le5.}
\]

**Không phải** có tám lõi thì chắc chắn nhanh gấp tám lần.

### 10.2. Quan hệ với work/span

Amdahl nhìn chương trình như hai phần "tuần tự + có thể chia đều"; work/span nhìn **toàn bộ đồ thị phụ thuộc**.

Trong một số trường hợp mô hình, span của DAG gồm phần tuần tự cộng với đường phụ thuộc bên trong phần có thể chia; ta có thể dùng hai cách nhìn để phát hiện nút thắt. Nhưng **f không tự bằng S/W trong mọi bài toán**, vì f của Amdahl được định nghĩa theo cấu phần tuần tự và giả thiết về tốc độ baseline; DAG có cấu trúc phụ thuộc phức tạp hơn một đoạn tuần tự rồi một đoạn song song hoàn hảo.

### 10.3. Giảm phần tuần tự có tác dụng lớn

Khi f giảm, giới hạn `1/f` tăng nhanh. Đôi khi đầu tư cải tiến một **phân đoạn không thể song song hóa** (lock, barrier, serial initialization, merge cuối) giúp tăng tốc tốt hơn việc thêm số lượng thread.

---

## 11. Gustafson và strong/weak scaling

### 11.1. Strong scaling

**Strong scaling**: giữ cố định kích thước bài toán, tăng số bộ xử lý P và xem thời gian thay đổi thế nào.

Work W và span S của thuật toán lý tưởng có thể coi cố định. Khi P tăng, cận `W/P` giảm, nhưng `S` không giảm, nên dần gặp giới hạn đường găng.

### 11.2. Weak scaling

**Weak scaling**: tăng kích thước bài toán theo số bộ xử lý, thường để lượng công việc mỗi bộ xử lý xấp xỉ giữ nguyên.

Do W và có thể cả S **đều thay đổi theo kích thước**, một hệ thống có thể xử lý dữ liệu lớn hơn với thời gian gần tương đương, dù speedup trên một input cố định không còn tăng nhiều.

Không được lấy đồ thị weak-scaling làm bằng chứng trực tiếp về strong-scaling speedup.

### 11.3. Định luật Gustafson

Trong một mô hình scaled-size, ký hiệu α là **tỉ lệ thời gian tuần tự trong lần chạy song song trên P bộ xử lý**, tỉ lệ này được định nghĩa theo runtime ở cấu hình P trong mô hình. Công thức scaled speedup thường được viết:

\[
\boxed{
S_{\mathrm{Gustafson}}(P)=P-\alpha(P-1).
}
\]

Nếu α=0.1 và P=8:

\[
S_G=8-0.1\cdot7=\boxed{7.3}.
\]

**α trong Gustafson không nhất thiết cùng đại lượng với f trong Amdahl**, vì chúng được đo/định nghĩa trong các mô hình cơ sở khác nhau. Không thế số tùy tiện giữa hai công thức rồi kết luận chúng mâu thuẫn.

### 11.4. Tình huống ứng dụng

Ví dụ xử lý 100 ảnh lớn trên bốn máy thay vì 25 ảnh trên một máy, với thời gian gần nhau, là một quan sát kiểu weak scaling.

Ngược lại, giữ đúng 100 ảnh và tăng từ một lên bốn máy rồi so thời gian là strong scaling. Phải chỉ rõ mình đang tối ưu **độ trễ một bài** hay **throughput của toàn hệ thống**.

---

## 12. Song song hóa có overhead: mô hình bổ sung

Một xấp xỉ thực tế:

\[
T_P\approx\frac WP + \text{phần do phụ thuộc}
+\text{overhead}(P,n).
\]

Đây là sơ đồ tư duy chứ **không phải công thức chính xác chung**. "Phần do phụ thuộc" không được cộng cơ học bằng S nếu công việc trên đường găng đã được tính trong W/P; các cận work/span dùng `max(W/P,S)`, còn Brent cung cấp một dạng cận trên trong mô hình khác.

Overhead có thể bao gồm:

### 12.1. Tạo tác vụ quá nhỏ

Nếu một phép cộng chỉ mất vài chu kỳ CPU nhưng mỗi `fork` cần quản lý task, queue và `join`, tạo một task cho từng phép cộng thường **đắt hơn tự tính tuần tự** với n nhỏ.

Chọn **threshold**: khi đoạn đủ nhỏ, xử lý trực tiếp trong một task thay vì tiếp tục tách.

### 12.2. Đồng bộ quá mức

Nếu nhiều task phải vào một `synchronized` block để cập nhật tổng toàn cục, chúng có thể trở thành chuỗi phụ thuộc qua lock.

Reduction tốt thường để mỗi task tính một **partial sum riêng**, rồi gộp tại các điểm phụ thuộc đã định trong cây. Tránh việc tất cả thread cùng tăng một biến chia sẻ một cách không đồng bộ.

### 12.3. Race condition

Ví dụ:

```java
// Không an toàn nếu nhiều thread cùng làm:
sharedSum += partial;
```

Đọc–sửa–ghi không nguyên tử trong bối cảnh đồng thời; một số cập nhật có thể bị mất.

Mã Java trong bài dùng `RecursiveTask<Long>` trả kết quả từng nhánh và `join` trước khi cộng, không dùng biến tổng chia sẻ để giảm nguy cơ data race.

### 12.4. False sharing

Hai thread có thể sửa **hai biến khác nhau**, nhưng các biến nằm chung một cache line. Khi ấy phần cứng liên tục chuyển quyền sở hữu cache line giữa các lõi, làm giảm thông lượng.

Đây không phải lỗi kết quả logic mà là nút thắt hiệu năng. Các kỹ thuật như padding, phân vùng dữ liệu và thiết kế giảm cập nhật chung có thể giúp, nhưng cần đo trên phần cứng cụ thể.

### 12.5. Băng thông và locality

Nhiều lõi cùng đọc dữ liệu lớn có thể chạm giới hạn băng thông RAM. Khi đó tăng P không tăng thông lượng tuyến tính. Duyệt dữ liệu liên tục theo vùng, giảm cấp phát và tránh copy không cần thiết thường quan trọng.

### 12.6. Load imbalance

Nếu một task rất nặng trong khi task khác rất nhỏ, nhiều worker rảnh chờ task nặng. Tổng work có thể lớn nhưng **phân bổ không đều**.

Chia việc cân bằng và lập lịch động có thể giảm chênh lệch tải, nhưng không thể xóa những phụ thuộc thật trên đường găng.

---

## 13. Work stealing trong ForkJoinPool

**ForkJoinPool** của Java hỗ trợ việc một task chia thành các task con; các worker có thể lấy việc từ queue của worker khác (*work stealing*) để cải thiện cân bằng tải.

Một mẫu quen thuộc:

```text
compute(segment):
    if segment small:
        process sequentially
    else:
        split into left and right
        left.fork()
        rightResult = right.compute()
        leftResult = left.join()
        return combine(leftResult, rightResult)
```

### 13.1. Fork và join nghĩa là gì?

- `fork()` lên lịch task có thể chạy đồng thời.
- `compute()` trên nhánh phải cho thread hiện tại làm việc hữu ích thay vì đứng chờ.
- `join()` lấy kết quả nhánh trái, **chờ** nếu nhánh đó chưa hoàn tất.
- `combine` chỉ được làm sau khi hai kết quả con hợp lệ.

Điều này phù hợp cây reduction: hai nhánh độc lập cho tới lúc cần cộng hai partial sums.

### 13.2. ForkJoinPool(4) không đảm bảo speedup4

Cấu hình parallelism=4 thể hiện số lượng worker mục tiêu trong pool, **không** hứa rằng chương trình sẽ đồng thời đạt bốn lõi vật lý hoặc nhanh gấp bốn lần.

Với input chỉ tám phần tử, overhead tạo task và gọi ForkJoinPool có thể lớn hơn phép cộng. Đây là ví dụ **đúng về mô hình phụ thuộc**, không phải benchmark tốc độ.

### 13.3. Threshold quyết định độ hạt

Với threshold=2:

- Một task xử lý đoạn dài 1 hoặc 2 tuần tự.
- Đoạn dài hơn được tách gần đều.
- Với n=8, có bốn đoạn lá dài 2; mỗi đoạn lá tính một phép cộng, rồi ba phép cộng gộp ở các nút trong.

Tổng vẫn:

\[
W=4\cdot1+3=7.
\]

Span từ lá tới gốc:

\[
S=1+1+1=3.
\]

Với threshold lớn hơn, ít task hơn nhưng span phần tuần tự tại lá có thể tăng. Với threshold quá nhỏ, chi phí quản lý task tăng. Chọn threshold bằng **đo đạc trên kích thước dữ liệu và phần cứng thật**.

---

## 14. Java 17+: phân tích DAG và ForkJoin reduction

Tệp chạy độc lập: **`WorkSpanSpeedupDemo.java`**.

Chương trình gồm:

1. `ReductionTask` dùng `RecursiveTask<Long>`, chia đôi mảng và gộp partial sums sau `join`.
2. `profileReduction` tính **work/span trên cây phép cộng** mà task tạo ra, đếm phép cộng chứ **không** tính chi phí `fork`, `join` hoặc đọc bộ nhớ.
3. `levelRounds` mô phỏng lịch **theo tầng** cho reduction n là lũy thừa của hai, không giả làm số đo runtime.
4. `analyzeDag` dùng Kahn + DP để tính work, span và một critical path của DAG có thời lượng tác vụ dương.
5. `idealLowerBound` tính `max(ceil(W/P),S)` trên task durations nguyên.
6. Ví dụ Amdahl `f=0.2`, `P=8`, kiểm tra DAG có chu trình và cấu hình bộ xử lý không hợp lệ.
7. Trường hợp chỉ một số trong phép cộng, khi **work/span đếm phép cộng là 0/0**.

### 14.1. Mã nguồn đầy đủ

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;

public final class WorkSpanSpeedupDemo {

    // Work/span counts ADDITIONS ONLY, not task overhead.
    public record Profile(long work, int span) {
    }

    public record DagAnalysis(
            long work,
            long span,
            int[] criticalPath) {
    }

    public static final class ReductionTask
            extends RecursiveTask<Long> {

        private final long[] values;
        private final int lo;
        private final int hi;
        private final int threshold;

        public ReductionTask(
                long[] values,
                int lo,
                int hi,
                int threshold) {

            if (values == null
                    || lo < 0
                    || hi > values.length
                    || lo >= hi
                    || threshold < 1) {
                throw new IllegalArgumentException(
                        "Invalid reduction task");
            }

            this.values = values;
            this.lo = lo;
            this.hi = hi;
            this.threshold = threshold;
        }

        @Override
        protected Long compute() {
            int length = hi - lo;

            if (length <= threshold) {
                // The first input needs no addition.
                long total = values[lo];

                for (int i = lo + 1; i < hi; i++) {
                    total = Math.addExact(total, values[i]);
                }

                return total;
            }

            int mid = lo + length / 2;

            ReductionTask left =
                    new ReductionTask(
                            values, lo, mid, threshold);

            ReductionTask right =
                    new ReductionTask(
                            values, mid, hi, threshold);

            // Left may run on another worker.
            left.fork();

            // Current worker keeps doing useful work.
            long rightTotal = right.compute();

            // Join is a dependency boundary.
            long leftTotal = left.join();

            return Math.addExact(leftTotal, rightTotal);
        }
    }

    // Describes the arithmetic dependency tree only.
    public static Profile profileReduction(
            int length, int threshold) {

        if (length < 1 || threshold < 1) {
            throw new IllegalArgumentException(
                    "Length and threshold must be positive");
        }

        if (length <= threshold) {
            return new Profile(length - 1L, length - 1);
        }

        int leftLength = length / 2;
        int rightLength = length - leftLength;

        Profile left =
                profileReduction(leftLength, threshold);

        Profile right =
                profileReduction(rightLength, threshold);

        long work = Math.addExact(
                Math.addExact(left.work(), right.work()),
                1L);

        int span = Math.addExact(
                Math.max(left.span(), right.span()),
                1);

        return new Profile(work, span);
    }

    // A particular level-by-level schedule.
    // Valid for a complete balanced power-of-two tree.
    public static long levelRounds(int n, int processors) {
        if (n < 1
                || (n & (n - 1)) != 0
                || processors < 1) {
            throw new IllegalArgumentException(
                    "n must be power of two; P >= 1");
        }

        long rounds = 0L;

        for (int ready = n / 2; ready > 0; ready /= 2) {
            long required = ready / processors;

            if (ready % processors != 0) {
                required++;
            }

            rounds = Math.addExact(rounds, required);
        }

        return rounds;
    }

    // P-processor theoretical LOWER bound.
    public static long idealLowerBound(
            long work, long span, int processors) {

        if (work < 0L
                || span < 0L
                || processors < 1) {
            throw new IllegalArgumentException(
                    "Invalid work/span/P");
        }

        long workBound = work / processors;

        if (work % processors != 0L) {
            workBound++;
        }

        return Math.max(workBound, span);
    }

    // Longest weighted path on an acyclic task graph.
    // Edge u->v means v waits for u.
    public static DagAnalysis analyzeDag(
            long[] duration, int[][] edges) {

        if (duration == null
                || duration.length == 0
                || edges == null) {
            throw new IllegalArgumentException(
                    "Need nonempty tasks and edge list");
        }

        int n = duration.length;

        List<List<Integer>> outgoing = new ArrayList<>();
        int[] indegree = new int[n];
        long[] earliestStart = new long[n];
        int[] predecessor = new int[n];

        Arrays.fill(predecessor, -1);

        long work = 0L;

        for (int v = 0; v < n; v++) {
            if (duration[v] <= 0L) {
                throw new IllegalArgumentException(
                        "Task durations must be positive");
            }

            work = Math.addExact(work, duration[v]);
            outgoing.add(new ArrayList<>());
        }

        for (int[] edge : edges) {
            if (edge == null || edge.length != 2) {
                throw new IllegalArgumentException(
                        "Edge must have two endpoints");
            }

            int from = edge[0];
            int to = edge[1];

            if (from < 0 || from >= n
                    || to < 0 || to >= n) {
                throw new IllegalArgumentException(
                        "Edge endpoint out of bounds");
            }

            outgoing.get(from).add(to);
            indegree[to]++;
        }

        ArrayDeque<Integer> queue = new ArrayDeque<>();

        for (int v = 0; v < n; v++) {
            if (indegree[v] == 0) {
                queue.addLast(v);
            }
        }

        int processed = 0;
        long span = 0L;
        int endpoint = -1;

        while (!queue.isEmpty()) {
            int u = queue.removeFirst();
            processed++;

            long finish = Math.addExact(
                    earliestStart[u], duration[u]);

            if (finish > span) {
                span = finish;
                endpoint = u;
            }

            for (int v : outgoing.get(u)) {
                if (finish > earliestStart[v]) {
                    earliestStart[v] = finish;
                    predecessor[v] = u;
                }

                indegree[v]--;

                if (indegree[v] == 0) {
                    queue.addLast(v);
                }
            }
        }

        if (processed != n) {
            throw new IllegalArgumentException(
                    "Dependency graph has a cycle");
        }

        // Reconstruct one critical path.
        ArrayList<Integer> backwards = new ArrayList<>();

        for (int v = endpoint; v != -1;
                v = predecessor[v]) {
            backwards.add(v);
        }

        int[] path = new int[backwards.size()];

        for (int i = 0; i < backwards.size(); i++) {
            path[i] = backwards.get(
                    backwards.size() - 1 - i);
        }

        return new DagAnalysis(work, span, path);
    }

    public static void main(String[] args) {
        long[] values = {1, 2, 3, 4, 5, 6, 7, 8};
        int threshold = 2;
        int workers = 4;

        ForkJoinPool pool = new ForkJoinPool(workers);
        long sum;

        try {
            sum = pool.invoke(
                    new ReductionTask(
                            values, 0, values.length,
                            threshold));
        } finally {
            pool.shutdown();
        }

        Profile reduction =
                profileReduction(values.length, threshold);

        System.out.println(
                "Input: " + Arrays.toString(values));
        System.out.println("Parallel sum: " + sum);
        System.out.println(
                "Reduction arithmetic work: "
                        + reduction.work());
        System.out.println(
                "Reduction arithmetic span: "
                        + reduction.span());

        System.out.printf(
                Locale.ROOT,
                "Reduction parallelism: %.6f%n",
                (double) reduction.work() / reduction.span());

        for (int p : new int[] {1, 2, 4}) {
            System.out.println(
                    "Reduction lower bound P=" + p + ": "
                            + idealLowerBound(
                                    reduction.work(),
                                    reduction.span(),
                                    p));
        }

        System.out.println(
                "Level schedule P=2: "
                        + levelRounds(8, 2));
        System.out.println(
                "Level schedule P=4: "
                        + levelRounds(8, 4));

        long[] durations = {2, 3, 4, 5, 2, 3};
        int[][] edges = {
                {0, 2},
                {1, 2},
                {1, 3},
                {2, 4},
                {3, 4},
                {4, 5}
        };

        DagAnalysis dag = analyzeDag(durations, edges);

        System.out.println("DAG work: " + dag.work());
        System.out.println("DAG span: " + dag.span());
        System.out.println(
                "DAG critical path: "
                        + Arrays.toString(dag.criticalPath()));
        System.out.println(
                "DAG lower bound P=2: "
                        + idealLowerBound(
                                dag.work(), dag.span(), 2));

        System.out.printf(
                Locale.ROOT,
                "DAG parallelism: %.6f%n",
                (double) dag.work() / dag.span());

        double f = 0.2;
        int p = 8;
        double amdahl = 1.0 / (f + (1.0 - f) / p);

        System.out.printf(
                Locale.ROOT,
                "Amdahl f=0.2 P=8: %.6f%n",
                amdahl);

        boolean cycleRejected = false;

        try {
            analyzeDag(
                    new long[] {1, 1},
                    new int[][] {{0, 1}, {1, 0}});
        } catch (IllegalArgumentException ex) {
            cycleRejected = true;
        }

        System.out.println(
                "Cycle rejected: " + cycleRejected);

        boolean invalidPRejected = false;

        try {
            idealLowerBound(10, 5, 0);
        } catch (IllegalArgumentException ex) {
            invalidPRejected = true;
        }

        System.out.println(
                "Invalid P rejected: " + invalidPRejected);

        long singleton = new ReductionTask(
                new long[] {42}, 0, 1, 2).compute();

        Profile one = profileReduction(1, 2);

        System.out.println("Singleton sum: " + singleton);
        System.out.println(
                "Singleton arithmetic work/span: "
                        + one.work() + "/" + one.span());
    }
}
```

### 14.2. Biên dịch và chạy

Cần **JDK 17 trở lên**:

```bash
javac WorkSpanSpeedupDemo.java
java WorkSpanSpeedupDemo
```

**Stdout kỳ vọng:**

```text
Input: [1, 2, 3, 4, 5, 6, 7, 8]
Parallel sum: 36
Reduction arithmetic work: 7
Reduction arithmetic span: 3
Reduction parallelism: 2.333333
Reduction lower bound P=1: 7
Reduction lower bound P=2: 4
Reduction lower bound P=4: 3
Level schedule P=2: 4
Level schedule P=4: 3
DAG work: 19
DAG span: 13
DAG critical path: [1, 3, 4, 5]
DAG lower bound P=2: 13
DAG parallelism: 1.461538
Amdahl f=0.2 P=8: 3.333333
Cycle rejected: true
Invalid P rejected: true
Singleton sum: 42
Singleton arithmetic work/span: 0/0
```

### 14.3. Vì sao kết quả song song vẫn bằng 36?

`ReductionTask` chia mảng thành hai nửa không chồng nhau. Mỗi tác vụ con chỉ **đọc** dữ liệu đầu vào, không sửa mảng hay biến tổng toàn cục. Sau khi hai nhánh hoàn thành, kết quả được gộp bằng:

```java
return Math.addExact(leftTotal, rightTotal);
```

Không có phép cộng nào bị bỏ, không đếm trùng phần tử, và `join` đảm bảo `leftTotal` là kết quả hoàn thành trước khi dùng nó.

### 14.4. Work/span được phân tích, không được đo

`profileReduction` mô phỏng cấu trúc **phép cộng**:

- Đoạn dài L≤threshold được cộng tuần tự, nên work=L−1 và span=L−1.
- Đoạn lớn được chia đôi; hai nhánh có thể chạy đồng thời, rồi có một phép cộng gộp, nên:
  \[
  W(L)=W(L_1)+W(L_2)+1,
  \]
  \[
  S(L)=\max(S(L_1),S(L_2))+1.
  \]

Với tám số, threshold=2:

\[
W=7,\qquad S=3.
\]

Đây là **các đại lượng trong DAG phép cộng**. Chúng không phải giá trị ms/ns của `ForkJoinPool`. Task creation, buffer/array access và scheduler không được tính vào profile.

### 14.5. Đếm work đúng khi leaf dùng vòng lặp

Leaf của chương trình bắt đầu bằng:

```java
long total = values[lo];
```

rồi cộng từng phần tử còn lại. Vì vậy leaf dài L có **L−1 phép cộng**, không phải L phép cộng thêm vào một tổng ban đầu bằng 0. Mô hình profile và mã Java thống nhất về cách đếm.

### 14.6. Vai trò của Math.addExact

`Math.addExact` ném `ArithmeticException` nếu một phép cộng long vượt miền biểu diễn. Điều đó tốt hơn việc lặng lẽ wrap-around khi ứng dụng yêu cầu phát hiện overflow.

Trong DAG, work và thời điểm finish cũng dùng `Math.addExact` để tránh âm thầm tràn số. Không có nghĩa mọi input lớn đều chạy được: tài nguyên bộ nhớ và số tác vụ vẫn hữu hạn.

### 14.7. Kahn và thứ tự khôi phục đường găng

`analyzeDag` nhận hai mảng:

- `duration[v]`: thời lượng dương của tác vụ v.
- `edges[]`: mỗi cặp `{u,v}` nghĩa u phải xong trước v.

Mã tính độ bắt đầu sớm nhất cho từng v, giữ predecessor tạo đường dài nhất, sau đó khôi phục một critical path. Nếu có chu trình, số đỉnh được Kahn xử lý nhỏ hơn n và mã từ chối rõ.

Mã không cố thực sự chạy những tác vụ DAG này trên thread; `analyzeDag` là **phân tích phụ thuộc lý thuyết**. Chỉ phần `ReductionTask` là tính tổng bằng ForkJoinPool.

### 14.8. Vì sao pool tạo bốn worker nhưng không hứa thời gian bằng ba?

`Level schedule P=4: 3` là kết quả của **lịch tưởng tượng với mỗi phép cộng tốn một bước và overhead bằng 0**.

Chương trình thật cần tạo task, đọc bộ nhớ, lên lịch, `fork` và `join`. Thậm chí một CPU có thể không có đủ bốn lõi vật lý; cấu hình pool chỉ là một yếu tố. Do đó không in một thời gian ms "3" rồi nói đo được.

### 14.9. Giới hạn ứng dụng của chương trình

- Dãy input cho reduction phải **không rỗng**; đầu vào trống bị từ chối.
- `threshold≥1`.
- `profileReduction` mô hình hóa phép cộng, với một phần tử work/span bằng 0.
- `levelRounds` chỉ dành cho n là **lũy thừa của hai**.
- Tác vụ DAG phải có thời lượng dương, ID cạnh trong phạm vi, và không có chu trình.
- Các trọng số DAG là **đơn vị thời gian quy ước**, không nhất thiết là thời gian thực của một hệ thống.
- Nếu DAG có nhiều đường găng đồng hạng, mã trả một đường cụ thể do thứ tự queue.
- `ForkJoinPool` chỉ dùng cho phần reduction, không phải scheduler cho DAG sáu tác vụ.

---

## 15. Bài toán khác: nơi span là nút thắt

### 15.1. BFS theo frontier

BFS trên đồ thị có thể xử lý nhiều đỉnh trong **cùng lớp khoảng cách** đồng thời. Nhưng lớp k+1 phụ thuộc vào kết quả tìm được của lớp k.

- Work có thể liên quan O(V+E) khi thăm mỗi đỉnh/cạnh hữu hạn lần.
- Span chịu ảnh hưởng số lớp BFS, kích thước frontier và chi phí đồng bộ.
- Một đồ thị dạng đường thẳng có frontier mỗi lớp rất nhỏ, nên dù nhiều lõi cũng khó khai thác song song từ một nguồn.

Khi nhiều thread khám phá cùng một đỉnh, cần bảo đảm việc đánh dấu visited hoặc ghi distance đúng bằng cơ chế đồng bộ/atomic thích hợp; nếu không có thể xử lý trùng hoặc sai dữ liệu.

### 15.2. DP trên DAG

Một truy hồi kiểu:

\[
dp[v]=\max_{u\to v}(dp[u]+w(v))
\]

có thể tính theo topo. Những đỉnh đã đủ predecessor và độc lập có thể xử lý song song. Nhưng đường găng của phụ thuộc vẫn là cận dưới.

Không phải "tất cả đỉnh có chỉ số khác nhau" đều chạy cùng lúc nếu chúng có cạnh phụ thuộc.

### 15.3. Ma trận và tích vô hướng

Nhân hai ma trận cho phép tính nhiều ô đầu ra độc lập. Tuy nhiên, từng ô đầu ra cần tổng nhiều tích; nếu tích lũy tuần tự, span mỗi ô dài theo kích thước chiều trong. Nếu dùng reduction dạng cây trong mỗi ô, span có thể giảm với giá trị work tiệm cận tương tự.

Thời gian thực còn bị chi phối bởi locality, cache blocking và băng thông bộ nhớ; một thuật toán với span lý thuyết rất thấp chưa chắc nhanh nếu truy cập RAM không hiệu quả.

### 15.4. Pipeline

Một pipeline có các giai đoạn xử lý theo thứ tự (đọc, giải mã, biến đổi, ghi). Các phần tử dữ liệu khác nhau có thể nằm ở giai đoạn khác nhau, giúp tăng **throughput**.

Nhưng **latency** của một phần tử vẫn phải trải qua các giai đoạn phụ thuộc. Pipeline tăng số phần tử hoàn thành mỗi giây không nhất thiết giảm độ dài đường phụ thuộc của một phần tử.

---

## 16. Chọn thuật toán theo W và S

Giả sử cùng một mục tiêu tính toán, ta có:

| Phương án | Work | Span | Nhận xét |
| --- | --- | --- | --- |
| A | O(n) | O(n) | Ít overhead, nhưng ít khả năng song song |
| B | O(n) | O(log n) | Work-efficient, span thấp |
| C | O(n log n) | O(log n) | Span tương tự B nhưng làm thêm work |
| D | O(n) | O(√n) | Trung gian giữa A và B |

Với P=1, work thường là một yếu tố quyết định. Với P rất lớn, span trở nên quan trọng hơn. Với P hữu hạn, phải xét **cả W/P và S**, chưa kể overhead.

### 16.1. Lựa chọn thuật toán theo P

Không phải mọi lần tăng P đều đáng giá. Nếu `W/S≈2`, tăng từ 4 lên 64 worker có thể chủ yếu làm tăng overhead.

Ngược lại, khi `W/S` rất lớn nhưng số tác vụ quá nhỏ hoặc phân chia lệch, chương trình có thể vẫn không đạt tốc độ lý tưởng. Khi ấy nút thắt nằm ở **cách tạo và lập lịch tác vụ**, không chỉ ở DAG trừu tượng.

### 16.2. Giảm span có thể cần đổi thuật toán

Cách cộng tuần tự n số có span n−1; chỉ bọc nó trong một thread không giảm span. Muốn giảm span phải **thay cấu trúc phụ thuộc**, ví dụ chuyển từ accumulator tuần tự sang reduction cây.

Tương tự, thay vòng for bằng `parallel()` không tự làm một truy hồi phụ thuộc liên tiếp trở nên độc lập.

### 16.3. Kiểm tra mức song song thực dụng

Một checklist:

1. Mỗi tác vụ có đầu vào gì?
2. Tác vụ nào phải chạy trước tác vụ nào?
3. Những kết quả nào có thể tính độc lập?
4. Gộp kết quả có phải là phép kết hợp không?
5. Work tăng bao nhiêu so với thuật toán tốt nhất tuần tự?
6. Span còn dài đến mức nào?
7. Độ hạt tác vụ có đủ lớn để bù overhead không?
8. Có shared mutable state, lock hoặc contention không?
9. Dữ liệu có đủ locality để tránh nghẽn memory không?
10. Cấu hình P có phù hợp số lõi và giới hạn tài nguyên không?

---

## 17. Kiểm thử độc lập

### 17.1. Reduction đúng kết quả

Với mảng ngắn, tính tổng tuần tự bằng một vòng lặp độc lập rồi so với `ForkJoinPool.invoke`.

Chú ý so sánh trên số nguyên trong phạm vi long. Nếu dùng floating point, kết quả song song có thể khác vài bit do thứ tự cộng dù thuật toán đúng về mô hình toán học.

### 17.2. Work của cây giảm

Với mọi n≥1 và threshold≥1, nếu cây chia các đoạn không rỗng, mỗi phần tử xuất hiện đúng một lần và mỗi phép gộp hai tổng cần một phép cộng, thì:

\[
\boxed{W=n-1}.
\]

Có thể kiểm tra điều này bằng hàm profile cho n=1..60 với các threshold khác nhau.

Một mô hình độc lập đã thử **600 tổ hợp** n từ 1 đến 60 và threshold từ 1 đến 10: work luôn bằng n−1, còn span không vượt work (với n≥1).

### 17.3. Critical path oracle

Trên DAG nhỏ, có thể **liệt kê tất cả các đường** từ các source tới các sink để tìm tổng trọng số lớn nhất, rồi so với kết quả topo DP. Oracle liệt kê đường có thể có độ phức tạp lớn, chỉ dùng cho test nhỏ.

Hoặc dùng cách khác: sinh một DAG có thứ tự topo trước, dựng `edges` chỉ từ ID nhỏ sang ID lớn, rồi tính DP theo thứ tự ID và đối chiếu với Kahn. Tránh xây oracle bằng đúng cùng logic và cùng lỗi chỉ số của phiên bản cần kiểm thử.

### 17.4. Test có chu trình

```text
0 -> 1
1 -> 0
```

Không có thứ tự topo. Hàm `analyzeDag` phải từ chối, không được trả span hữu hạn như đồ thị hợp lệ.

### 17.5. Test DAG nhiều source

Ví dụ:

```text
0 -> 2
1 -> 2
```

Tác vụ 0 và 1 có thể bắt đầu đồng thời. `start[2]` là max finish của 0 và 1, không phải tổng hai finish.

Nếu thuật toán cộng thời lượng của **mọi predecessor** thành thời gian bắt đầu, nó sẽ tính sai span.

### 17.6. Test DAG không có cạnh

Với ba task thời lượng [2,5,3] và không có cạnh:

\[
W=2+5+3=10,\quad S=\max(2,5,3)=\boxed5.
\]

Cả ba task có thể bắt đầu đồng thời khi có đủ ba bộ xử lý; span không phải 10.

### 17.7. Test reduction n=1

Với mảng `[42]`, tổng là 42. Nếu chỉ đếm phép cộng:

\[
W=0,\quad S=0.
\]

Không được in `W/S` vì sẽ là 0/0.

### 17.8. Test n không là lũy thừa hai

Với n=5, cây chia hai phần 2 và 3; tổng vẫn đúng, work=4 phép cộng, span (threshold1) bằng3 phép cộng. Không cần tự bổ sung các phần tử dữ liệu ảo trừ khi thuật toán được thiết kế rõ ràng với padding.

### 17.9. Test overflow

Với dữ liệu chứa `Long.MAX_VALUE` và số dương khác, `Math.addExact` sẽ phát hiện một phép cộng vượt long. Không được lấy giá trị âm tràn làm tổng đúng.

Nếu bài toán yêu cầu cộng các số cực lớn mà vẫn trả kết quả toán học chính xác, thay `long` bằng `BigInteger` và phân tích lại overhead/cost model.

### 17.10. Test benchmark thật

Khi muốn đo tốc độ Java:

- Cho JIT warmup trước khi đo.
- Chạy nhiều lần và báo phân bố (median, percentile hoặc độ lệch phù hợp).
- Dùng input đủ lớn, tránh để overhead áp đảo phép tính.
- Có baseline tuần tự độc lập.
- Cùng dữ liệu, cùng máy, cùng điều kiện tải hệ thống.
- Báo P, threshold, phiên bản JDK, CPU, kích thước dữ liệu.
- Chú ý GC, cấp phát task và CPU turbo/frequency scaling.
- Không lấy stdout `Level schedule P=4: 3` làm thời gian chạy thật.

---

## 18. Những lỗi phổ biến

1. **Nhầm work với thời gian trên P bộ xử lý**.
2. **Nhầm span với tổng work** khi có tác vụ độc lập.
3. **Nhầm span với số cạnh dài nhất** khi các đỉnh có thời lượng khác nhau.
4. **Cộng thời lượng mọi predecessor** thay vì lấy max để tính earliestStart.
5. **Tính DAG có chu trình như DAG**, không kiểm tra topo.
6. **Chỉ xét critical path bắt đầu từ ID0**, bỏ các source khác.
7. **Quên rằng DAG có thể có nhiều critical path đồng hạng**.
8. **Cho rằng có n task thì chạy nhanh trên n lõi**, không phân tích cạnh phụ thuộc.
9. **Dùng W/S khi S=0**, gây chia cho 0.
10. **Dùng `W/S` làm thời gian tăng tốc đã đo**, không phải.
11. **Cho rằng `T_P=max(W/P,S)` là đẳng thức luôn đạt**, dù mới là cận dưới.
12. **Áp cận Brent unit-task như lời hứa wall-clock Java**, bỏ overhead và tác vụ không đều.
13. **Cho rằng mọi scheduler bất kỳ đều có cận của greedy schedule**, sai.
14. **Giả định ForkJoinPool(8) là tám lõi vật lý luôn hoạt động**.
15. **Tạo task cho từng phép cộng nhỏ** rồi kỳ vọng nhanh hơn vòng lặp.
16. **Không dùng threshold**, làm cấp phát task quá lớn.
17. **Dùng ngưỡng quá lớn**, hầu hết công việc lại tuần tự.
18. **Cộng vào biến chia sẻ không đồng bộ**, gây lost updates.
19. **Dùng synchronized/lock cho từng phần tử**, làm giảm khả năng song song.
20. **Không join task trước khi dùng kết quả của nó**, đọc kết quả chưa sẵn sàng.
21. **Gọi join ở nơi không cần thiết khiến các tác vụ độc lập thành tuần tự**.
22. **Không xét false sharing và băng thông RAM**, speedup thấp dù work/span đẹp.
23. **Đo chương trình tám phần tử rồi suy ra sức mạnh CPU**, overhead chiếm phần lớn.
24. **Không warm up JIT hoặc báo đúng một số đo**, benchmark thiếu tin cậy.
25. **So baseline khác thuật toán hoặc khác input mà không nói rõ**, speedup sai nghĩa.
26. **Nhầm efficiency với % sử dụng CPU**, hai đại lượng khác.
27. **Nhầm strong scaling với weak scaling**, dữ liệu đo không tương đương.
28. **Dùng α của Gustafson như f của Amdahl vô điều kiện**, sai mô hình.
29. **Tuyên bố Amdahl cho tốc độ chính xác của mọi chương trình**, bỏ giả thiết.
30. **Nhầm reduction với prefix scan**, yêu cầu đầu ra khác.
31. **Đổi thứ tự cộng double và đòi bằng bit tuyệt đối**, quên làm tròn.
32. **Dùng phép toán không kết hợp trong cây reduction mà không phân tích lại**, có thể đổi kết quả.
33. **Quên phát hiện overflow long trong phép cộng số nguyên**.
34. **Nói mọi parallel algorithm có work thấp là span thấp**, không đúng.
35. **Chỉ tối ưu span và cho work tăng quá lớn**, chậm với P nhỏ.
36. **Đếm số task Java như số phép cộng**, sai khi threshold khác một.
37. **Không chỉ rõ phần nào của profile đã bỏ overhead**, so lý thuyết với ms sai.
38. **Đồng nhất throughput pipeline với latency của một mục dữ liệu**, không chính xác.
39. **Không kiểm thử DAG không cạnh/nhiều source**, bug start/finish dễ bị bỏ sót.
40. **Chỉ kiểm thử kết quả số mà không kiểm tra critical path hợp lệ**, bỏ lỗi truy vết.
41. **Phớt lờ thời điểm task sẵn sàng trong lịch**, vi phạm phụ thuộc.
42. **Không phân biệt cận trên của một lịch cụ thể với cận dưới cho mọi lịch**.

---

## 19. Bài tập tự kiểm tra

### Bài 1
Work W là gì trong một DAG tác vụ có thời lượng dương?

### Bài 2
Span S được tính theo đường nào của DAG?

### Bài 3
Nếu một DAG có ba tác vụ độc lập thời lượng 2,5,3, W và S bằng bao nhiêu?

### Bài 4
Vì sao vòng cộng tuần tự tám số có span7 phép cộng?

### Bài 5
Cây cộng cân bằng tám số có work và span bằng bao nhiêu?

### Bài 6
Giải thích tại sao hai phép cộng ở cùng tầng có thể chạy đồng thời.

### Bài 7
Viết cận dưới theo work cho T_P.

### Bài 8
Viết cận dưới theo span cho T_P.

### Bài 9
Kết hợp hai cận dưới, cho biểu thức T_P.

### Bài 10
Với W=100,S=40,P=4, cận dưới T_P là bao nhiêu?

### Bài 11
Trong mô hình T1=W, cận lý tưởng của speedup trên P là gì?

### Bài 12
Với W=7,S=3,P=4, speedup tối đa theo cận là bao nhiêu?

### Bài 13
Tại sao `W/S` không phải số thread chạy đồng thời tại mọi thời điểm?

### Bài 14
Lập lịch theo tầng với reduction tám số và P=2 cần bao nhiêu bước?

### Bài 15
Lập lịch theo tầng với cùng reduction và P=4 cần bao nhiêu bước?

### Bài 16
Với P=4 ở ví dụ trên, efficiency của lịch tầng bằng bao nhiêu?

### Bài 17
Phát biểu điều kiện của một lịch tham lam trên DAG đơn vị.

### Bài 18
Viết một cận Brent cho greedy schedule trong mô hình unit-task.

### Bài 19
Vì sao non-full steps của lịch tham lam có nhiều nhất S bước?

### Bài 20
Với DAG thời lượng [2,3,4,5,2,3] và cạnh mục 3, tính W và S.

### Bài 21
Nêu một critical path của DAG sáu tác vụ.

### Bài 22
DAG có chu trình có được phân tích bằng topo DP này không?

### Bài 23
Viết công thức start[v] và finish[v].

### Bài 24
Vì sao start[v] dùng max thay vì sum các tiền nhiệm?

### Bài 25
Tính speedup nếu tuần tự80 ms và chạy P=4 mất25 ms.

### Bài 26
Tính efficiency ở bài25.

### Bài 27
Theo Amdahl, f=0.2,P=8 cho cận speedup nào?

### Bài 28
Với f=0.2, P→∞ có giới hạn tăng tốc nào?

### Bài 29
Gustafson với α=0.1,P=8 cho scaled speedup nào?

### Bài 30
Phân biệt strong scaling và weak scaling.

### Bài 31
Reduction và inclusive prefix scan trên [1,2,3,4] cho output khác nhau thế nào?

### Bài 32
Hillis–Steele scan và Blelloch scan khác nhau về work bậc nào?

### Bài 33
Vì sao việc gọi fork không xóa quan hệ phụ thuộc giữa hai task?

### Bài 34
Nêu vai trò của `join` và trường hợp có thể gây race khi bỏ nó.

### Bài 35
Threshold nhỏ và threshold lớn đánh đổi điều gì?

### Bài 36
Một dòng `sharedSum += partial` được nhiều thread gọi không đồng bộ có nguy cơ gì?

### Bài 37
False sharing là gì?

### Bài 38
Vì sao cùng W,S nhưng thực tế P=8 có thể chậm hơn P=4?

### Bài 39
Với một số đầu vào, nếu chỉ đếm phép cộng, W,S bằng gì và W/S có định nghĩa không?

### Bài 40
Đưa ra phương pháp kiểm thử độc lập cho critical path trên DAG nhỏ.

### Đáp án gợi ý

1. `W=\sum_{v\in V}w(v)`, tổng công việc các tác vụ cần thực hiện.
2. Đường có tổng trọng số tác vụ lớn nhất trong DAG.
3. W=10,S=5.
4. Mỗi phép cộng cần kết quả từ phép trước nên tạo chuỗi 7 bước.
5. W=7,S=3.
6. Không có cạnh phụ thuộc trực tiếp/gián tiếp bắt buộc giữa các phép cùng tầng trong cây reduction đã định.
7. `T_P\ge W/P`.
8. `T_P\ge S`.
9. `T_P\ge\max(W/P,S)`.
10. `max(100/4,40)=40`.
11. `Speedup(P)\le\min(P,W/S)` nếu S>0.
12. `min(4,7/3)=7/3≈2.333333`.
13. Vì số tác vụ sẵn sàng thay đổi theo từng thời điểm; W/S là tỉ lệ tổng và đường găng.
14. `2+1+1=4` bước.
15. `1+1+1=3` bước.
16. `(7/3)/4=7/12≈0.583333`.
17. Mỗi bước chạy tối đa P tác vụ sẵn sàng; không trì hoãn tác vụ sẵn sàng khi còn bộ xử lý rảnh.
18. `T_P\le(W-S)/P+S`, hoặc dạng yếu `T_P\le W/P+S`.
19. Vì ở bước không đầy, mọi task sẵn sàng chạy, làm span của phần DAG còn lại giảm ít nhất một.
20. W=19,S=13.
21. `1\to3\to4\to5` với trọng số `3+5+2+3=13`.
22. Không; cần phát hiện và xử lý chu trình trước, vì không có topo order.
23. `start[v]=\max_{u\to v}finish[u]`, source có start0; `finish[v]=start[v]+w(v)`.
24. Các tiền nhiệm có thể chạy đồng thời; v chỉ cần chờ tiền nhiệm kết thúc **muộn nhất**.
25. `80/25=3.2`.
26. `3.2/4=0.8=80%`.
27. `1/(0.2+0.8/8)=1/0.3≈3.333333`.
28. `1/f=5`.
29. `8-0.1(8-1)=7.3`.
30. Strong scaling giữ nguyên bài toán và tăng P; weak scaling tăng workload theo P.
31. Reduction trả10; inclusive scan trả `[1,3,6,10]`.
32. Hillis–Steele có O(n log n) work, Blelloch có O(n) work; cả hai có O(log n) span trong mô hình chuẩn.
33. Nếu task con cần output task khác, nó vẫn phải chờ dù cả hai được đưa vào scheduler.
34. `join` chờ kết quả task; bỏ đồng bộ mà dùng trạng thái được ghi song song có thể đọc dữ liệu chưa sẵn sàng hoặc gây race.
35. Threshold nhỏ tăng parallel tasks nhưng overhead cao; threshold lớn ít overhead nhưng span phần tuần tự cao.
36. Lost update/data race, tổng có thể thiếu phần đóng góp.
37. Hai dữ liệu khác nhau bị nhiều lõi cập nhật nhưng cùng cache line, làm tăng lưu lượng coherency.
38. Overhead, contention, memory bandwidth hoặc cache/GC có thể tăng dù cận phụ thuộc không đổi.
39. W=0,S=0; `W/S` không xác định, không nói thời gian thực bằng 0.
40. Liệt kê tất cả đường đi trên DAG nhỏ hoặc dùng một DP oracle độc lập theo topo khác rồi so tổng trọng số lớn nhất và tính hợp lệ của đường trả về.

---

## Ghi nhớ

**Work W** là lượng công việc phải làm; **span S** là độ dài đường găng bắt buộc; **parallelism W/S** là khả năng tăng tốc cấu trúc theo mô hình lý tưởng khi S>0.

Hai định luật:

\[
\boxed{
T_P\ge\frac WP,\qquad T_P\ge S.
}
\]

Kết hợp:

\[
\boxed{
T_P\ge\max(W/P,S).
}
\]

Trong mô hình DAG tác vụ đơn vị và lịch tham lam, một cận trên điển hình:

\[
\boxed{
T_P\le(W-S)/P+S.
}
\]

Từ đó, với cùng DAG lý tưởng:

\[
\boxed{
Speedup(P)\le\min(P,W/S).
}
\]

**Ví dụ dễ nhớ:** reduction tám số bằng cây cân bằng có work7, span3, song song tiềm năng7/3; lịch theo tầng với P=2 cần4 bước và P=4 cần3 bước. DAG sáu tác vụ ở bài có W19,S13, đường găng `1\to3\to4\to5`, nên khả năng tăng tốc vốn hạn chế dù có nhiều worker.

Để có hiệu quả thật, phải **giảm span mà không làm work tăng quá nhiều**, chọn task đủ lớn, giảm chia sẻ dữ liệu và đồng bộ, tôn trọng quan hệ phụ thuộc, và **đo wall-clock time riêng** thay vì xem các con số work/span như benchmark.
