# Chi phí khấu hao với hàm nghịch đảo Ackermann

Khi học **Disjoint Set Union (DSU)**, còn gọi là **Union–Find**, ta thường gặp câu nói: “`find` và `union` gần như `O(1)`”. Cách nói đó hữu ích về mặt trực giác, nhưng chưa đủ chính xác để phân tích thuật toán. Một lời gọi `find(x)` đôi khi vẫn phải lần theo nhiều nút cha trước khi tới gốc. Điều đặc biệt của DSU tối ưu là: **xét toàn bộ một chuỗi nhiều phép tìm và hợp, tổng số công việc tăng rất chậm so với số thao tác**.

Kết quả này được mô tả bằng **độ phức tạp khấu hao (amortized complexity)** và **hàm nghịch đảo Ackermann**, thường ký hiệu `α(n)`. Hàm `α` tăng cực kỳ chậm; nhưng điều quan trọng hơn một con số nhỏ là hiểu **điều kiện để chặn đúng**, **ý nghĩa của khấu hao**, và **vì sao không thể suy ra mỗi lần tìm có thời gian hằng số trong trường hợp xấu**.

Bài thuộc chương **Tập hợp rời nhau** trong học phần **COMPUTER_SCIENCE_DATA_STRUCTURES**. Học phần xây dựng nền tảng cấu trúc dữ liệu qua mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị; nghiên cứu bất biến, thao tác cùng độ phức tạp thời gian, bộ nhớ để chọn cấu trúc phù hợp. Ở đây ta phân tích sâu một ví dụ tiêu biểu: **DSU dùng rừng mảng cha, hợp theo kích thước hoặc hạng, và nén đường đi**.

## 1. Mục tiêu học tập và quy ước

Sau bài này, bạn cần có thể:

1. Phân biệt **worst-case**, **average-case** và **amortized cost**.
2. Giải thích tại sao `find` trong DSU chưa tối ưu có thể mất `Θ(n)`, và tại sao **union by size/rank** một mình chặn chiều cao cây bởi `O(log n)`.
3. Trình bày cơ chế **path compression** làm các truy vấn tiếp theo nhanh hơn nhưng có thể khiến một lần tìm ban đầu vẫn tốn công.
4. Hiểu hàm Ackermann tăng nhanh thế nào, và ý nghĩa của **Ackermann ngược** `α` mà không nhầm với `1/A(n)`.
5. Đọc đúng một định lý **khấu hao trên chuỗi `m` thao tác**, không dùng nó như chặn worst-case cho từng lời gọi.
6. Triển khai DSU với các bất biến đầy đủ, biết cách đo số bước và chọn đúng cấu trúc khi xử lý đồ thị.

Ký hiệu dùng trong bài:

| Ký hiệu | Ý nghĩa |
|---|---|
| `n` | Số phần tử của DSU, giả sử đã khởi tạo ban đầu |
| `m` | Số phép `find`, `union` hoặc các truy vấn xây trên chúng trong chuỗi đang xét |
| `h` | Chiều cao cây cha tại thời điểm một phép tìm được gọi |
| `α(n)` | Một dạng hàm nghịch đảo Ackermann theo quy ước phân tích |
| `parent[x]` | Nút cha của x; ở gốc r có `parent[r]=r` |
| `size[r]`, `rank[r]` | Metadata chỉ được diễn giải như thông tin của **gốc hiện tại** |

Một phép `union(x,y)` gọi `find` cho cả x và y rồi, nếu hai gốc khác nhau, gộp hai cây. Trong phân tích, ta có thể đếm `union` như một thao tác mức cao với **hai lần tìm gốc**, nên khác một hằng số nhân so với cách đếm các lời gọi `find` riêng lẻ.

## 2. Nhắc lại cấu trúc rừng cha của Union–Find

Cho tập phần tử:

\[
U=\{0,1,\ldots,n-1\}.
\]

DSU duy trì một **phân hoạch** của U thành những nhóm không giao nhau. Mỗi nhóm được biểu diễn bởi **một cây có gốc**:

```text
Nhóm A                 Nhóm B

      0                     5
     / \                   / \
    1   2                 6   7
        |
        3

Gốc A = 0              Gốc B = 5
```

Mỗi phần tử lưu một giá trị `parent`. Để xác định nhóm của x, ta đi theo cha đến gốc:

```text
find(x):
    while parent[x] != x:
        x = parent[x]
    return x
```

Hai phần tử cùng nhóm khi và chỉ khi:

\[
\operatorname{find}(x)=\operatorname{find}(y).
\]

Một phép hợp phải nối **hai gốc**, không nối tùy ý hai nút:

```text
union(x, y):
    rx = find(x)
    ry = find(y)

    if rx == ry:
        return false

    parent[ry] = rx
    return true
```

Nếu hai gốc trùng nhau, phép hợp là **no-op**: không tạo thêm nhóm, không giảm số nhóm và không cộng kích thước nhóm lần nữa.

### Bất biến cần giữ

- Mọi con trỏ `parent[x]` nằm trong miền.
- Mỗi cây có một gốc tự trỏ `parent[r]=r`.
- Không tồn tại chu trình cha nhiều nút.
- Đường cha từ mỗi x kết thúc ở gốc của nhóm chứa x.
- Những cây khác nhau không chia sẻ phần tử.
- `union` thành công làm số nhóm giảm đúng một.

Hai tối ưu `union by size/rank` và `path compression` chỉ điều chỉnh **hình dạng các cây và đường đi**, không làm thay đổi ngữ nghĩa phân hoạch.

## 3. Mô hình chi phí: đếm những việc gì?

Trong mô hình RAM thường dùng khi phân tích cấu trúc dữ liệu, ta xem mỗi phép đọc/ghi một ô mảng, so sánh hai chỉ số, gán một con trỏ hoặc thực hiện phép toán từ máy đơn giản có chi phí `O(1)`.

Một phép `find(x)` trên cây cao `h` cần lần theo đường dài tối đa `h` cạnh:

\[
T_{\mathrm{find}}(x)=O(h).
\]

Điều này khác việc đọc một ô `parent[x]`, vốn là `O(1)`. Nếu `parent[x]` chưa phải gốc, cần **nhiều lần đọc liên tiếp**.

Một phép `union(x,y)` có:

\[
T_{\mathrm{union}}(x,y)
= T_{\mathrm{find}}(x)+T_{\mathrm{find}}(y)+O(1).
\]

Phần `O(1)` là việc so sánh hai gốc, sửa một con trỏ cha và cập nhật vài trường metadata nếu phép hợp thành công.

Nếu tất cả lời gọi luôn có chi phí không quá `C`, thì m thao tác tốn `O(mC)`. Nhưng chặn `C` của một thao tác riêng lẻ có thể quá bi quan: **những thao tác đắt đôi khi làm cấu trúc trở nên dễ truy vấn hơn trong tương lai**.

Đó là lý do cần phân tích khấu hao.

## 4. Ba cách đánh giá chi phí không giống nhau

| Loại phân tích | Câu hỏi | Cần giả định xác suất? |
|---|---|---|
| **Worst-case cho một thao tác** | Lần gọi đơn lẻ tốn nhiều nhất bao nhiêu, xét mọi trạng thái hợp lệ? | Không |
| **Average-case** | Chi phí kỳ vọng nếu trạng thái/đầu vào theo một phân phối xác suất đã xác định? | Có, phải nêu phân phối |
| **Amortized** | Trên **mọi chuỗi thao tác hợp lệ**, tổng chi phí có thể chặn tốt tới đâu, kể cả khi một số thao tác riêng lẻ đắt? | Không cần phân phối xác suất |

**Khấu hao không phải trung bình xác suất.** Ta không giả định người dùng “thường” truy vấn thuận lợi hoặc dữ liệu “gần ngẫu nhiên”. Phân tích khấu hao phải bảo đảm chặn trên tổng công việc cho **bất kỳ chuỗi thao tác hợp lệ nào** trong mô hình đã chọn.

Giả sử chi phí thật của các thao tác lần lượt là `c_1,c_2,\ldots,c_m`. Một phân tích khấu hao tìm cách chứng minh:

\[
\sum_{i=1}^{m}c_i
\leq C(m,n),
\]

với `C(m,n)` nhỏ hơn cách nhân máy móc m với mức đắt nhất `\max_i c_i`.

Nếu thu được:

\[
\sum_{i=1}^{m}c_i=O(m\alpha(n)),
\]

ta nói mỗi thao tác có **chi phí `O(α(n))` khấu hao**, với điều kiện `n` và cách đếm m trong định lý tương ứng. Điều này **không** có nghĩa mọi `c_i≤O(\alpha(n))`.

## 5. Trực giác khấu hao qua một đường cha dài

Xét rừng hợp lệ nhưng chưa tối ưu:

```text
7 → 6 → 5 → 4 → 3 → 2 → 1 → 0
                                ^ gốc
```

Mảng:

```text
parent = [0,0,1,2,3,4,5,6]
```

Nếu `find` **không nén đường đi**, mỗi lần `find(7)` lại đi qua bảy cạnh cha. Gọi 100 lần vẫn phải đi qua tổng cộng **700 cạnh**.

Nếu `find` dùng **full path compression**, lần đầu nó vẫn phải đi qua bảy cạnh để tới gốc, nhưng sau đó:

```text
parent = [0,0,0,0,0,0,0,0]
```

Những lần `find(7)` tiếp theo chỉ đi qua một cạnh `7→0`.

Nếu chỉ đếm số cạnh của **lượt tìm gốc**, tổng trên 100 lần là:

\[
7+99\cdot1=106,
\]

so với 700 khi không nén. **Đây chưa phải tổng chi phí toàn bộ thuật toán**, vì full compression ở lần đầu còn phải đi lượt thứ hai để cập nhật cha; nhưng cả việc đọc và ghi vẫn chỉ thêm một lượng công việc tỷ lệ với đường đã đi.

### Bài học từ ví dụ

- Một thao tác có thể đắt hơn bình thường nhưng **mang lại lợi ích lâu dài**.
- Không phải mọi thao tác sẽ nén cùng một đường; các phép `union` sau đó có thể tạo thêm những đường mới.
- Ví dụ gọi cùng một `find` lặp lại **chỉ minh họa trực giác**. Nó **không tự chứng minh** chặn nghịch đảo Ackermann cho mọi chuỗi `find`/`union` xen kẽ.

Để có chặn lý thuyết mạnh, ta còn cần hạn chế cách tạo cây mới bằng **union by size hoặc union by rank**.

## 6. Vì sao không nên để `union` nối gốc tùy ý?

Nếu `union` luôn gắn gốc của đối số thứ hai dưới gốc của đối số thứ nhất, có thể tạo chuỗi:

```text
union(1,0)
union(2,1)
union(3,2)
union(4,3)
union(5,4)

0 → 1 → 2 → 3 → 4 → 5
                        ^ gốc
```

Với n phần tử, một cây như vậy có thể cao `n-1`. Không nén đường đi, một lần `find(0)` có chi phí `Θ(n)`.

**Path compression một mình** có thể cải thiện nhiều trường hợp, nhưng không được tự động gán cho nó chặn `O(α(n))` khấu hao **dành cho sự kết hợp hai kỹ thuật** mà chưa xét điều kiện của định lý. Tương tự, **union by size/rank một mình** cho chặn logarithmic mà chưa nhất thiết cho chặn Ackermann ngược.

Hai tối ưu giải quyết hai phần khác nhau của vấn đề:

- **Hợp theo size/rank:** ngăn những phép `union` mới dựng lên cây quá cao.
- **Nén đường đi:** giảm những quãng đường cha phải đi lại khi truy vấn.

## 7. Hợp theo kích thước: giới hạn chiều cao bằng lập luận gấp đôi

**Union by size** lưu `size[root]` là số thành viên của nhóm có gốc root, và chỉ gắn gốc nhóm **nhỏ hơn hoặc bằng** dưới gốc nhóm lớn hơn:

```text
union_by_size(x, y):
    rx = find(x)
    ry = find(y)

    if rx == ry:
        return false

    if size[rx] < size[ry]:
        swap(rx, ry)

    parent[ry] = rx
    size[rx] += size[ry]
    return true
```

Giả sử cây A có a phần tử, cây B có b phần tử với `a≤b`. Khi cây A nối dưới B:

- Độ sâu của mọi phần tử thuộc A có thể tăng một.
- Kích thước nhóm mới chứa các nút đó là `a+b≥2a`.

Do vậy, **mỗi lần độ sâu một phần tử tăng do phép hợp, kích thước nhóm chứa nó ít nhất gấp đôi**. Sau k lần như thế, nhóm chứa nó có ít nhất `2^k` phần tử.

Vì nhóm có tối đa n phần tử:

\[
2^k\le n
\quad\Rightarrow\quad
k\le\lfloor\log_2 n\rfloor.
\]

Suy ra, **ngay cả khi chưa nén đường đi**, union by size giữ chiều cao cây ở mức:

\[
h=O(\log n).
\]

Vì mỗi `union` cần hai `find`, các phép `find` và `union` đều có **`O(log n)` worst-case cho một lần gọi** trong mô hình mảng cha này.

### Tại sao chặn logarithmic hữu ích?

Ta đã loại bỏ các cây hình chuỗi `Θ(n)` từ cách nối tùy ý. Nhưng với n lớn, vẫn có một số đường dài `Θ(log n)`. Nén đường đi giúp khai thác **lịch sử các lần tìm** để giảm tổng chi phí hơn nữa.

## 8. Hợp theo hạng: rank tăng có kiểm soát

**Union by rank** dùng `rank[root]` thay cho `size[root]`. Khởi đầu:

```text
parent[x] = x
rank[x] = 0
```

Khi hợp hai nhóm:

```text
union_by_rank(x, y):
    rx = find(x)
    ry = find(y)

    if rx == ry:
        return false

    if rank[rx] < rank[ry]:
        swap(rx, ry)

    parent[ry] = rx

    if rank[rx] == rank[ry]:
        rank[rx] += 1

    return true
```

**Chỉ tăng rank khi hai rank trước khi gộp bằng nhau.** Khi rank của hai gốc khác nhau, gốc rank cao hơn giữ vai trò đại diện và rank **không tăng**.

Một bất biến cơ bản của union by rank là:

\[
\#\text{phần tử trong nhóm có gốc }r
\ge 2^{\mathrm{rank}[r]}.
\]

Lập luận quy nạp:

1. Nhóm đơn có rank 0, kích thước 1, nên `1=2^0`.
2. Hợp cây rank thấp dưới cây rank cao: rank của gốc giữ nguyên, kích thước không giảm.
3. Hợp hai cây cùng rank k: mỗi nhóm có ít nhất `2^k` nút; nhóm mới có ít nhất `2^{k+1}` nút và rank tăng thành k+1.

Vì nhóm có tối đa n phần tử:

\[
\mathrm{rank}[r]\le\lfloor\log_2 n\rfloor.
\]

Không dùng compression, rank của gốc phản ánh chiều cao theo quy tắc union chuẩn. Sau khi nén, rank **không tự giảm**; nó có thể lớn hơn chiều cao hiện tại nhưng vẫn là chặn trên có ích.

### Rank tăng nghiêm ngặt theo đường cha

Trong union by rank chuẩn, khi gốc r trở thành con của gốc s:

- Nếu hai rank cũ khác nhau, `rank[s]>rank[r]`.
- Nếu bằng nhau, rank của s được tăng một, nên sau phép hợp vẫn `rank[s]>rank[r]`.

Vì rank của nút không phải gốc không được tăng nữa và các phép nén chỉ nối tới tổ tiên có rank cao hơn, một đường cha từ nút con lên gốc có các rank **tăng nghiêm ngặt**.

Tính chất này rất quan trọng trong những lập luận khấu hao tinh vi: khi một liên kết cha bị thay bằng một tổ tiên cao hơn, ta thường tạo được **một bước nhảy đáng kể theo hạng**, dù không nhất thiết nhảy ngay tới gốc.

## 9. Nén đường đi thay đổi tương lai, không làm đổi nhóm

**Full path compression** cập nhật cha của tất cả nút trên đường tìm gốc thành chính gốc:

```text
find(x):
    root = x
    while parent[root] != root:
        root = parent[root]

    while parent[x] != x:
        old_parent = parent[x]
        parent[x] = root
        x = old_parent

    return root
```

Việc lưu `old_parent` trước khi cập nhật là cần thiết: nếu chỉ viết `x=parent[x]` sau khi đặt `parent[x]=root`, vòng lặp sẽ nhảy ngay tới gốc và bỏ qua nhiều nút cần nén.

### Vì sao phép nén luôn bảo toàn phân hoạch?

Giả sử đường cũ là:

```text
x → p → q → ... → root
```

Thay `parent[x]=root` chỉ làm x **đi tắt tới một tổ tiên của chính nó**. Các nút p, q và những nút khác vẫn ở cùng cây. Không phần tử nào bị chuyển nhóm, không tạo chu trình, và không sinh thêm gốc.

Do đó:

\[
\mathrm{root}_{\text{after}}(v)
=\mathrm{root}_{\text{before}}(v)
\quad\text{cho mọi phần tử }v.
\]

Suy ra mọi câu trả lời `same(x,y)` không đổi khi chỉ thực hiện `find`. `size[root]`, `componentCount` và rank được duy trì theo quy tắc union cũng không thay đổi vì phép nén.

### Path halving và path splitting

Có các biến thể một lượt thường được dùng:

```text
find_halving(x):
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x
```

```text
find_splitting(x):
    while parent[x] != x:
        old_parent = parent[x]
        parent[x] = parent[old_parent]
        x = old_parent
    return x
```

Cả hai đều cho nút trỏ tới ông/bà, nhưng **halving nhảy tới cha mới**, còn **splitting tiếp tục đi từ cha cũ**. Chúng cũng làm ngắn đường cha và có những định lý khấu hao tương tự khi kết hợp quy tắc union chuẩn. Mảng `parent` cuối có thể khác full compression, nhưng phân hoạch phải giống nhau.

## 10. Hàm Ackermann tăng nhanh đến mức nào?

Để hiểu tại sao `α` nhỏ, trước hết cần hình dung một họ hàm **Ackermann** tăng rất nhanh.

Có nhiều quy ước định nghĩa. Một phiên bản hai đối số trên các số nguyên không âm là:

\[
\begin{aligned}
A(0,j)&=j+1,\\
A(i+1,0)&=A(i,1),\\
A(i+1,j+1)&=A\bigl(i,A(i+1,j)\bigr).
\end{aligned}
\]

Đây là một phiên bản cụ thể của hàm Ackermann–Péter. Đừng nhầm các chỉ số `i,j` và định nghĩa này với cách định nghĩa nhanh hơn/chậm hơn ở các giáo trình khác.

Các hàng đầu tiên của hàm có dạng:

\[
\begin{aligned}
A(0,j)&=j+1,\\
A(1,j)&=j+2,\\
A(2,j)&=2j+3,\\
A(3,j)&=2^{j+3}-3.
\end{aligned}
\]

Ví dụ:

| Biểu thức | Giá trị |
|---|---:|
| `A(0,0)` | 1 |
| `A(1,1)` | 3 |
| `A(2,2)` | 7 |
| `A(3,3)` | 61 |
| `A(4,1)` | 65.533 |

Sang hàng `i=4`, hàm tăng theo một tháp lũy thừa; `A(4,4)` đã lớn đến mức không phù hợp biểu diễn thông thường. Các hàng tiếp theo tăng nhanh hơn nữa.

**Điểm chính:** để tạo một giá trị n khổng lồ, đôi khi chỉ cần chỉ số hàng i rất nhỏ. Khi “đảo” quá trình theo mức tăng này, ta nhận một hàm tăng cực chậm.

## 11. Nghịch đảo Ackermann không phải `1/A(n)`

Trong phân tích cấu trúc dữ liệu, **hàm nghịch đảo Ackermann** trả lời một câu hỏi kiểu:

> Cần đi lên bao nhiêu *mức* trong một hệ hàm tăng cực nhanh để mức đó đủ lớn so với n?

Một định nghĩa **minh họa** dựa trên phiên bản Ackermann ở trên là:

\[
\alpha_{\mathrm{diag}}(n)
=
\min\{i\ge0:A(i,i)\ge n\},
\quad n\ge1.
\]

Đây là **nghịch đảo theo đường chéo** của một họ hàm hai đối số, không phải phép lấy nghịch đảo số học `1/A(n)`. Định nghĩa này hữu ích để nhìn mức tăng; **không phải mọi chứng minh Union–Find đều dùng đúng dạng `α_{\mathrm{diag}}` này**.

Theo quy ước minh họa:

| Miền n | `α_diag(n)` |
|---|---:|
| `n=1` | 0 |
| `2≤n≤3` | 1 |
| `4≤n≤7` | 2 |
| `8≤n≤61` | 3 |
| `62≤n≤A(4,4)` | 4 |

Vì `A(4,4)` cực kỳ lớn, `α_diag(n)` chỉ bằng 4 cho một miền giá trị n rộng đến mức vượt xa hầu hết những kích thước có thể biểu diễn trong máy tính.

### Tại sao tài liệu khác có thể cho những con số khác?

Có nhiều cách:

- Chuẩn hóa hàm Ackermann với các giá trị khởi đầu khác nhau.
- Dùng hàm nghịch đảo một biến `α(n)`.
- Dùng hàm hai tham số `α(m,n)` trong các định lý chính xác hơn về Union–Find.
- Đổi cách đánh chỉ số hàng bắt đầu từ 0 hay 1, hoặc đổi những ngưỡng thấp.

Những lựa chọn đó có thể làm **con số nhỏ cụ thể** khác nhau. Điều cần nhớ cho phân tích Big-O là **dạng tăng cực chậm** và **định lý áp dụng dưới các giả định cụ thể**. Không nên lấy bảng minh họa ở trên để tuyên bố một bộ thư viện nhất định luôn thực hiện đúng bốn bước.

## 12. Định lý độ phức tạp khấu hao của Union–Find

Với một DSU chuẩn trên n phần tử, sử dụng:

1. **Union by size hoặc union by rank**, và
2. **Path compression đầy đủ** (hoặc các biến thể chuẩn được phân tích tương ứng),

ta có chặn tổng chi phí rất nhỏ cho một chuỗi phép `find` và `union`.

Dạng phát biểu dễ dùng trong phân tích thuật toán là:

\[
\boxed{
T(n,m)=O\bigl(n+m\,\alpha(n)\bigr)
}
\]

trong cách định nghĩa thông dụng của `α`, với n là số phần tử đã khởi tạo, m là số thao tác mức cao và mô hình RAM chuẩn. Đây là **dạng chặn trên đơn giản**, bao gồm `O(n)` khởi tạo; các định lý chi tiết có thể dùng `α(m,n)` và quy ước đếm thao tác khác.

Một dạng chặn trên thận trọng, thuận tiện khi muốn tránh các chi tiết tham số là:

\[
T(n,m)=O\bigl((n+m)\,\alpha(n+m)\bigr)
\]

với miền đầu vào và quy ước `α` phù hợp. Điểm quan trọng là **tổng công gần tuyến tính** theo số phần tử và số phép toán.

### Điều gì được bảo đảm?

Với n cố định và nhiều thao tác:

\[
\frac{T(n,m)-O(n)}{m}
=O\bigl(\alpha(n)\bigr)
\]

theo cách đọc khấu hao thông thường, bỏ qua hằng số ẩn và chi phí khởi tạo đã tách ra.

Nói đơn giản: **tính trung bình công việc theo số thao tác trong một chuỗi bất kỳ, số công tăng cực chậm theo n**.

### Điều gì KHÔNG được bảo đảm?

Không được suy:

\[
\forall i:\quad c_i=O(\alpha(n)).
\]

Một lần `find` riêng lẻ trên cây có đường sâu `Θ(log n)` vẫn có thể tốn **`Θ(log n)`** trước khi nén, dù DSU dùng union by rank và compression.

Cũng không được suy rằng:

- Thuật toán dùng thời gian `O(1)` toán học tuyệt đối trên mọi kích thước n.
- Một lần `union` có thể bỏ qua hai lần `find`.
- Có thể bỏ union by size/rank mà vẫn tự động có đúng chặn trên từ định lý này.
- Kết quả liên thông vẫn đúng nếu thao tác `parent` làm hỏng bất biến cây.

## 13. Vì sao chặn mạnh hơn `O(log n)` xuất hiện?

Chứng minh chặn Ackermann ngược đầy đủ là một kết quả toán học tinh vi, thường gắn với phân tích Union–Find của Tarjan và các biến thể. Dưới đây là **trực giác có cấu trúc**, không giả làm một chứng minh đầy đủ.

### Tầng 1 — Rank chặn độ sâu và số nút

Nhờ union by rank, một gốc rank r có ít nhất `2^r` thành viên:

\[
2^r\le n
\quad\Rightarrow\quad
r\le\log_2 n.
\]

Quan trọng hơn, rank **tăng nghiêm ngặt** khi đi theo cha. Do đó, dù có nhiều nút, một đường cha không thể đi qua nhiều nút với cùng rank.

### Tầng 2 — Một lần nén tạo bước nhảy theo rank

Giả sử trên đường cha:

```text
x → p → q → ... → r
```

Sau compression, `parent[x]=r`. Nếu gốc có rank cao hơn, một lần đọc `parent[x]` sau này **bỏ qua toàn bộ các mức rank trung gian**.

Các lần nén trên những đường khác có thể chia sẻ lợi ích này. Việc nén một đoạn đường không chỉ giúp phần tử x, mà có thể giúp cả những phần tử về sau đi qua các nút từng được rút ngắn.

### Tầng 3 — Nhóm các rank thành các khoảng tăng cực nhanh

Để chứng minh chặn tốt hơn `O(log n)`, ta không chỉ chia rank thành những khoảng đều nhau. Thay vào đó, phân chia thành các **mức** theo một họ ngưỡng tăng rất nhanh liên quan đến hàm Ackermann.

Trong quá trình duyệt một đường cha, có thể quy nạp và **tính phí (charge)** cho các bước truy cập theo việc:

- Bước đi vượt qua **một mức rank**.
- Bước đi trong cùng mức nhưng khiến lần nén sau **tăng đáng kể rank của nút cha**.
- Một số bước đặc biệt sát gốc, có số lượng bị chặn riêng.

Vì các mức tăng siêu nhanh, số mức cần cho n phần tử chỉ là `α(n)` theo quy ước tương ứng. Một nút không thể liên tục tạo ra quá nhiều bước “đắt” trong cùng mức mà không làm thay đổi điều kiện dùng để tính phí.

### Tầng 4 — Cộng chi phí trên cả chuỗi

Khi cộng các khoản phí trên **mọi lần tìm và hợp**, số bước được giới hạn bởi một lượng tỷ lệ với `m\alpha(n)`, cộng chi phí tạo các phần tử/khởi tạo.

**Điểm không thể bỏ qua:** chặn này sử dụng **cả việc rank/size tăng có kiểm soát và việc các đường cha được rút ngắn sau truy vấn**. Chỉ nói “mỗi lần nén làm cây ngắn hơn” chưa đủ để chứng minh một chặn mạnh với các phép hợp xen kẽ.

Nếu cần chứng minh hình thức chi tiết, phải nêu chính xác **hàm Ackermann đang dùng, cách phân hoạch các mức rank, quy tắc charge hoặc hàm thế, và cách đếm m/n**. Bài này tập trung vào việc áp dụng định lý đúng và nắm các bất biến hỗ trợ chứng minh.

## 14. Ba phương pháp phân tích khấu hao thường gặp

Khi học độ phức tạp khấu hao nói chung, ta có thể dùng ba kỹ thuật:

| Phương pháp | Ý tưởng | Dùng vào việc gì? |
|---|---|---|
| **Tổng gộp (aggregate analysis)** | Chặn trực tiếp tổng chi phí của m thao tác | Phân tích một chuỗi thao tác, rồi chia cho m |
| **Phương pháp kế toán (accounting)** | Gán chi phí khấu hao cho thao tác; phần “tín dụng” dư trả cho thao tác đắt về sau | Trực giác lưu công để trả sau |
| **Phương pháp thế (potential method)** | Dùng hàm thế `Φ` đo trạng thái; chi phí khấu hao `ĉ_i=c_i+Φ_i−Φ_{i-1}` | Chứng minh tổng chi phí qua hiệu số thế triệt tiêu |

Với phương pháp thế:

\[
\sum_{i=1}^{m}\hat c_i
=
\sum_{i=1}^{m}c_i+\Phi_m-\Phi_0.
\]

Nếu `Φ_m≥Φ_0`, thì:

\[
\sum_{i=1}^{m}c_i
\le
\sum_{i=1}^{m}\hat c_i.
\]

Điều này giải thích cách một phép toán **tốn công thật nhiều nhưng làm giảm tiềm năng công việc tương lai** có thể có chi phí khấu hao thấp.

### Áp dụng ý tưởng vào DSU

- Một đường cha dài cho thấy có thể cần nhiều công trong `find`.
- Nén đường làm một số lần đi qua các đường ấy về sau ngắn hơn.
- Union by rank giới hạn số mức và cách chúng có thể được tạo lại.

Tuy nhiên, **không được tự đặt `Φ` bằng tổng số cạnh cha rồi tuyên bố đã chứng minh `O(α(n))`**. Số cạnh cha tổng thể không đo đủ các thay đổi và cấu trúc nhiều mức rank. Một chứng minh chính xác cần một hàm thế hoặc phương pháp charge tinh vi hơn.

### Liên hệ với mảng động

Khi mảng động tăng `capacity` theo hệ số, phần lớn phép `append` rẻ, đôi khi phải sao chép toàn bộ mảng. Tổng công qua nhiều `append` vẫn có thể `O(m)`, nên `append` có `O(1)` **khấu hao**, dù một lần mở rộng riêng lẻ mất `O(n)`.

DSU có trực giác tương tự về **một số thao tác đắt giúp giảm công tương lai**, nhưng chặn cụ thể phức tạp hơn và là `α(n)` chứ không tự động `1`.

## 15. So sánh chính xác các phương án DSU

| Chiến lược | `find` worst-case một lần | `union` worst-case một lần | Chặn khấu hao quen dùng | Bộ nhớ |
|---|---|---|---|---|
| Mảng cha, gắn gốc tùy ý, không nén | `O(n)` | `O(n)` | Không có chặn Ackermann ngược từ định lý kết hợp | `O(n)` |
| Union by size, không nén | `O(log n)` | `O(log n)` | `O(log n)` trên mỗi thao tác theo chặn trên trực tiếp | `O(n)` |
| Union by rank, không nén | `O(log n)` | `O(log n)` | `O(log n)` theo chặn trực tiếp | `O(n)` |
| Union by size + full compression | `O(log n)` | `O(log n)` | `O(α(n))` | `O(n)` |
| Union by rank + full compression | `O(log n)` | `O(log n)` | `O(α(n))` | `O(n)` |
| Union by size/rank + halving/splitting chuẩn | `O(log n)` | `O(log n)` | Các chặn nghịch đảo Ackermann tương ứng | `O(n)` |

**Vì sao hàng có compression vẫn ghi worst-case `O(log n)`?** Vì một lần tìm đầu trên cây cao `Θ(log n)` vẫn có thể đi qua đường đó trước khi rút ngắn. Path compression không khiến mọi đường dài biến mất **trước** lần đầu ta truy vấn nó.

**Bộ nhớ phụ:** các phiên bản `find` lặp dùng `O(1)` biến tạm mỗi lời gọi; toàn bộ DSU vẫn cần mảng `parent` và `size`/`rank` dài n, tức `O(n)` bộ nhớ. Phiên bản `find` đệ quy có thể dùng thêm `O(h)` bộ nhớ stack.

## 16. Triển khai Python: DSU tối ưu và đếm số bước

Một cách trực quan để **quan sát** khấu hao là viết DSU có đếm số cạnh cha đã đi qua. Ví dụ dưới dùng **union by size + full path compression** dạng lặp.

Ta đếm hai loại hoạt động:

- `hops`: số lần đi từ một nút sang cha của nó trong **lượt tìm gốc**.
- `rewrites`: số lần **thật sự đổi** `parent[x]` sang gốc trong lượt nén, bỏ qua các phép gán không làm đổi giá trị.

Hai bộ đếm **không phải** bộ đếm chính xác chu kỳ CPU. Chúng giúp quan sát xu hướng công việc; thời gian thực còn gồm đọc bộ nhớ, so sánh, cấp phát và nhiều yếu tố khác.

```python
class MeasuredDSU:
    def __init__(self, n: int):
        if not isinstance(n, int) or isinstance(n, bool):
            raise TypeError("n phải là số nguyên")
        if n < 0:
            raise ValueError("n phải không âm")

        self.parent = list(range(n))
        self.size = [1] * n
        self.components = n
        self.hops = 0
        self.rewrites = 0

    def _check(self, x: int) -> None:
        if not isinstance(x, int) or isinstance(x, bool):
            raise TypeError("Chỉ số phải là số nguyên")
        if not 0 <= x < len(self.parent):
            raise IndexError("Phần tử ngoài miền")

    def find(self, x: int) -> int:
        self._check(x)

        root = x

        # Lượt 1: truy gốc và đo số cạnh.
        while self.parent[root] != root:
            root = self.parent[root]
            self.hops += 1

        # Lượt 2: nén toàn bộ đường cũ.
        while self.parent[x] != x:
            old_parent = self.parent[x]

            if old_parent != root:
                self.parent[x] = root
                self.rewrites += 1

            x = old_parent

        return root

    def union(self, x: int, y: int) -> bool:
        rx = self.find(x)
        ry = self.find(y)

        if rx == ry:
            return False

        if self.size[rx] < self.size[ry]:
            rx, ry = ry, rx

        self.parent[ry] = rx
        self.size[rx] += self.size[ry]
        self.components -= 1
        return True

    def same(self, x: int, y: int) -> bool:
        return self.find(x) == self.find(y)

    def component_size(self, x: int) -> int:
        return self.size[self.find(x)]


dsu = MeasuredDSU(8)

# Tạo một cây nhị phân tương đối cân bằng,
# rồi mới tìm phần tử sâu 7.
for x, y in [
    (0, 1), (2, 3), (0, 2),
    (4, 5), (6, 7), (4, 6),
    (0, 4)
]:
    assert dsu.union(x, y)

assert dsu.components == 1
assert dsu.component_size(0) == 8

# Trước khi tìm 7: đường là 7 -> 6 -> 4 -> 0.
hops_before = dsu.hops
assert dsu.find(7) == 0
first_hops = dsu.hops - hops_before
assert first_hops == 3

# Full compression đổi parent[7] và parent[6] về 0.
assert dsu.parent[7] == 0
assert dsu.parent[6] == 0

hops_before = dsu.hops
assert dsu.find(7) == 0
second_hops = dsu.hops - hops_before
assert second_hops == 1

# Hợp trùng không làm sai số nhóm/kích thước.
assert dsu.union(3, 7) is False
assert dsu.components == 1
assert dsu.component_size(7) == 8

print(first_hops, second_hops)  # 3 1
```

### Giải thích con số đo được

Trong chuỗi hợp này, sau `union(0,4)`, gốc cuối là 0. Nút 7 có đường cha:

```text
7 → 6 → 4 → 0
```

Nên lần `find(7)` đầu đi qua **3 cạnh**, và lần thứ hai sau nén chỉ qua **1 cạnh**. Bộ đếm `rewrites` tăng khi sửa các nút có cha cũ chưa phải gốc.

**Lưu ý quan trọng:** ví dụ dùng n nhỏ để thấy cơ chế, không thể bằng một vài phép đo mà “xác minh” định lý `O(α(n))`. Định lý là chặn cho **mọi chuỗi thao tác hợp lệ**, và một phép benchmark chỉ cho biết hiệu năng ở những chuỗi đã thử.

## 17. Đối chiếu với DSU chưa có hai tối ưu

Có thể tạo một cây chuỗi trên n phần tử bằng cách **luôn gắn gốc nhóm chứa đối số thứ hai dưới gốc nhóm chứa đối số thứ nhất**, không xét kích thước:

```python
class NaiveDSU:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            x = self.parent[x]
        return x

    def union(self, x: int, y: int) -> None:
        rx = self.find(x)
        ry = self.find(y)
        if rx != ry:
            self.parent[ry] = rx


naive = NaiveDSU(8)
for i in range(1, 8):
    naive.union(i, i - 1)

assert naive.parent == [1, 2, 3, 4, 5, 6, 7, 7]
assert naive.find(0) == 7
```

Nếu gọi `find(0)` nhiều lần, bản `NaiveDSU` **lặp lại đường dài** vì không có path compression.

Tuy nhiên, đừng kết luận “cài đặt có compression luôn nhanh hơn trong mọi lời gọi”: trên dữ liệu rất nhỏ, các phép kiểm tra và ghi bổ sung có thể có hằng số chi phí đáng kể. Chúng ta dùng Big-O để hiểu khả năng mở rộng, rồi đo thực tế khi tối ưu hiệu năng.

### Vì sao không dùng cây ví dụ này để suy chặn worst-case của DSU tối ưu?

DSU có union by size/rank **không thể tạo đường cao n−1 từ khởi tạo nhóm đơn** bằng chính chuỗi phép hợp đó. Cây chuỗi cho thấy vấn đề của *phiên bản ngây thơ*; không phải trạng thái có thể hình thành khi các heuristic chuẩn được áp dụng đúng từ đầu.

## 18. C++17: union by rank và path halving

Các chặn khấu hao không phụ thuộc riêng vào Python. Với mảng số nguyên trong C++ có thể áp dụng cùng nguyên tắc:

```cpp
#include <algorithm>
#include <cstddef>
#include <iostream>
#include <numeric>
#include <stdexcept>
#include <vector>

class DSU {
public:
    explicit DSU(std::size_t n)
        : parent_(n), rank_(n, 0), components_(n) {
        std::iota(parent_.begin(), parent_.end(), std::size_t{0});
    }

    std::size_t find(std::size_t x) {
        if (x >= parent_.size()) {
            throw std::out_of_range("DSU index out of range");
        }

        // Path halving: cha mới là ông/bà.
        while (parent_[x] != x) {
            parent_[x] = parent_[parent_[x]];
            x = parent_[x];
        }
        return x;
    }

    bool unite(std::size_t x, std::size_t y) {
        x = find(x);
        y = find(y);

        if (x == y) return false;
        if (rank_[x] < rank_[y]) std::swap(x, y);

        parent_[y] = x;

        if (rank_[x] == rank_[y]) {
            ++rank_[x];
        }

        --components_;
        return true;
    }

    bool same(std::size_t x, std::size_t y) {
        return find(x) == find(y);
    }

    std::size_t component_count() const {
        return components_;
    }

private:
    std::vector<std::size_t> parent_;
    std::vector<unsigned> rank_;
    std::size_t components_;
};

int main() {
    DSU dsu(6);

    dsu.unite(0, 1);
    dsu.unite(2, 3);
    dsu.unite(0, 2);

    std::cout << dsu.same(1, 3) << '\n';       // 1
    std::cout << dsu.same(0, 5) << '\n';       // 0
    std::cout << dsu.component_count() << '\n'; // 3
}
```

Mã này:

- Khởi tạo `parent[x]=x`, `rank[x]=0`.
- Dùng path halving để đi lên các liên kết cha nhanh hơn trong các truy vấn lặp.
- Chỉ nối **hai gốc khác nhau**.
- Chỉ tăng rank khi **hai rank bằng nhau**.
- Chỉ giảm số nhóm sau một phép hợp thành công.

`find` có halving **ghi vào `parent_`**, nên không được mặc định là thao tác chỉ đọc hoặc an toàn đồng thời trên một DSU dùng chung. Trong C++ nếu hai luồng truy cập cùng vùng nhớ mà ít nhất một luồng ghi và thiếu đồng bộ, có thể xảy ra **data race**.

## 19. Phát biểu tổng chi phí trong các bài toán đồ thị

### 19.1. Xử lý chuỗi thêm cạnh và hỏi liên thông

Giả sử đồ thị vô hướng có `V` đỉnh và trải qua `E` phép thêm cạnh cùng `Q` lần truy vấn liên thông.

Ta:

1. Khởi tạo DSU với `V` nhóm đơn.
2. Với mỗi cạnh mới `(u,v)`, gọi `union(u,v)`.
3. Với mỗi truy vấn “u liên thông v?”, kiểm tra `find(u)==find(v)`.

Tổng số thao tác mức cao xấp xỉ `E+Q`. Với union by size/rank và compression, một dạng chặn trên là:

\[
O\Bigl(V+(E+Q)\alpha(V)\Bigr)
\]

cho thao tác DSU, theo quy ước `α` và m đủ thích hợp; không tính chi phí riêng của việc đọc dữ liệu đầu vào, lưu cạnh hoặc ánh xạ ID.

**Không được nói chặn này trả lời đường đi cụ thể.** DSU chỉ duy trì thông tin **cùng thành phần**, không lưu đủ cạnh để dựng đường đi.

### 19.2. Thuật toán Kruskal

Trong Kruskal tìm cây khung nhỏ nhất của đồ thị vô hướng có trọng số:

1. Sắp xếp `E` cạnh theo trọng số tăng dần.
2. Với mỗi cạnh `(u,v)`, chọn cạnh chỉ nếu hai đầu ở **hai thành phần khác nhau**.
3. Sau khi chọn cạnh, hợp hai thành phần.

Chi phí DSU gần:

\[
O(E\alpha(V)+V).
\]

Nhưng việc sắp xếp so sánh các cạnh thường mất:

\[
O(E\log E).
\]

Do đó, khi phân tích tổng thể Kruskal, **không được bỏ qua bước sắp xếp** chỉ vì DSU có chặn Ackermann ngược rất nhỏ.

### 19.3. Truy vấn được xử lý offline

Một số bài toán có xóa cạnh nhưng truy vấn đã biết trước có thể được **đảo thời gian hoặc xử lý offline** để biến những thao tác khó thành những phép hợp. Tuy nhiên, phải có kế hoạch xây dựng trạng thái rõ ràng; DSU chuẩn không có phép tách và không tự biến mọi bài toán xóa thành bài toán thêm.

Với các bài toán cần undo, có thể dùng **rollback DSU** với cấu trúc lưu thay đổi, thường **tránh path compression** vì nén có thể sửa nhiều con trỏ và làm undo khó hơn. Khi ấy chặn thời gian cần được phân tích lại, thường dựa trên union by size/rank và chiều cao logarithmic, **không áp chặn α từ DSU chuẩn một cách máy móc**.

## 20. Khi nào chặn Ackermann ngược không áp dụng trực tiếp?

Bảng sau giúp tránh dùng một câu nói “DSU là `O(α(n))`” cho mọi tình huống.

| Tình huống | Vấn đề | Cách phân tích phù hợp |
|---|---|---|
| Nối hai gốc tùy ý, không có compression | Có thể tạo cây chiều cao `Θ(n)` | `find` worst-case `O(n)` |
| Chỉ union by size/rank, không nén | Cây không quá cao nhưng còn đường `Θ(log n)` | `O(log n)` worst-case |
| Chỉ path compression, không có quy tắc hợp | Thiếu một giả định trong định lý kết hợp thường dùng | Cần định lý riêng, không mặc định `O(α(n))` |
| Hợp và tìm đúng chuẩn, đồng thời không đồng bộ | Có thể làm hỏng bất biến, nhất là trên bộ nhớ dùng chung | Chứng minh/thiết kế concurrent DSU riêng |
| Hợp trên các ID chưa đăng ký | Không có cây hợp lệ cho ID đó | Khởi tạo/ánh xạ ID và kiểm tra miền |
| Xóa/tách nhóm | DSU chuẩn không có thao tác split | Dynamic connectivity, rollback/offline thích hợp |
| Trả cả danh sách thành viên sau mỗi thao tác | Cần xuất nhiều phần tử, không thể chỉ trả đại diện | Tính thêm chi phí duyệt/ghi đầu ra |
| Ánh xạ ID chuỗi từ bên ngoài | Có thêm hash map/cấp phát | Cộng chi phí ánh xạ và lưu ID |
| `find` đệ quy trên cây sâu | Có thêm bộ nhớ stack và nguy cơ tràn | `O(h)` stack; cân nhắc bản lặp |

### Một lời nhắc về mô hình chi phí

Chặn `α(n)` được nêu trong mô hình thuật toán trừu tượng với thao tác cơ bản trên từ máy có chi phí hằng số. Nó không tự nói rằng toàn bộ ứng dụng là `O(α(n))` nếu còn:

- Đọc file hoặc truy vấn cơ sở dữ liệu.
- Giải mã và chuẩn hóa ID.
- Sắp xếp cạnh.
- Cấp phát đối tượng phức tạp.
- Xuất danh sách hàng triệu phần tử.
- Đồng bộ luồng hoặc mạng.

**Phân tích đúng phải cộng đủ những phần công việc liên quan.**

## 21. Cách kiểm thử hiệu năng và bất biến có ý nghĩa

Không nên chỉ chạy benchmark với các phép hợp ngẫu nhiên rồi kết luận mọi cài đặt đều giống nhau. Để quan sát lợi ích của các heuristic, nên thử nhiều mẫu:

| Mẫu thử | Điều cần quan sát |
|---|---|
| Khởi tạo n nhóm đơn | Bộ nhớ và thời gian tạo `parent`/`size` |
| Hợp tuần tự theo thứ tự xấu cho bản ngây thơ | Cây có thể thành chuỗi; phép tìm sâu rất tốn |
| Hợp các cặp cây bằng kích thước | Union by size/rank tạo đường cao `Θ(log n)` trước compression |
| Gọi đi gọi lại `find` trên nút sâu | Số lần đi theo cha giảm sau nén |
| Xen kẽ hợp và truy vấn nhiều nút | Thể hiện hiệu quả trên một chuỗi thao tác thực tế |
| Gọi `union(x,y)` khi đã cùng nhóm | Không tăng size/rank sai, không giảm số nhóm |
| Truy vấn trên nhiều thành phần | Nén trong một thành phần không đổi phần tử của thành phần khác |

### Các bất biến nên đối chiếu

Sau mỗi lô thao tác nhỏ:

- Mọi `parent[x]` là chỉ số hợp lệ.
- Mọi nút có đường cha đến một gốc tự trỏ.
- `componentCount` bằng số gốc hiện tại.
- Tổng `size[root]` trên các gốc bằng n nếu dùng union by size.
- Hai nút được xác định cùng nhóm trong mô hình tham chiếu phải có cùng `find`.
- Nếu dùng rank, ở từng gốc r phải có `size(G_r)≥2^{rank[r]}` theo cách đếm thành viên độc lập.

### Kiểm thử đúng khác với đo nhanh

Có thể dùng **mảng nhãn nhóm** làm bản tham chiếu đơn giản cho n nhỏ. Mỗi lần hợp, quét đổi nhãn của cả nhóm trong bản tham chiếu; sau đó so sánh kết quả `same` của tất cả cặp phần tử với DSU. Bản tham chiếu có thể chậm nhưng dễ kiểm chứng.

Khi đo hiệu năng, hãy ghi **số phần tử n, số thao tác m, tỉ lệ union/find, dữ liệu và nền tảng**, thay vì chỉ ghi “DSU mất 0,01 giây”. Đừng dùng một lần đo thực nghiệm để thay thế chứng minh giới hạn khấu hao.

## 22. Những ngộ nhận dễ dẫn tới sai thuật toán

### “`α(n)` nhỏ, vậy `find` chắc chắn `O(1)` worst-case”

Sai. `α(n)` mô tả **chi phí khấu hao của cả chuỗi** trong định lý áp dụng. Một lần `find` trên cây còn đường dài `Θ(log n)` vẫn có thể tốn `Θ(log n)`.

### “Khấu hao nghĩa là chọn đầu vào ngẫu nhiên rồi lấy trung bình”

Sai. Đó là tư duy **average-case** với phân phối xác suất. Chặn khấu hao không cần giả định ngẫu nhiên về thứ tự thao tác.

### “Cứ dùng nén đường đi là đủ cho chặn Ackermann ngược”

Không được kết luận như vậy từ định lý thường học. Chặn chuẩn được trình bày cho **kết hợp union by size/rank với compression**. Những cấu hình khác cần phân tích riêng.

### “Rank bằng chiều cao thật sau mỗi `find`”

Sai sau compression. Rank có thể giữ giá trị lớn hơn độ cao thực vì các đường cha đã được rút ngắn; thuật toán union by rank không giảm rank trong `find`.

### “Mỗi `find` phải cộng `size` do có thêm nút trỏ về gốc”

Sai. Nút đó **đã thuộc cùng nhóm**. Nén chỉ thay cha; số thành viên không tăng. Chỉ phép hợp **hai gốc khác nhau** mới cộng kích thước.

### “Một lần `find` có thể tự thay đại diện nhóm”

Trong DSU rừng cha chuẩn, **compression không đổi gốc của cây**. Chỉ `union` có thể khiến một gốc cũ trở thành con của gốc mới. Vì vậy giá trị `find(x)` có thể thay đổi qua các lần union, nhưng không phải chỉ vì nén đường trong cùng một nhóm.

### “Một số đo nhanh chứng minh được chặn `O(α(n))`”

Sai. Benchmark minh họa một workload cụ thể; định lý phức tạp khẳng định chặn trên **mọi chuỗi hợp lệ** trong mô hình phân tích.

## 23. Quy trình chọn phương án trong ứng dụng

Hãy trả lời lần lượt:

1. **Các nhóm thực sự là một phân hoạch không?** Mỗi phần tử chỉ ở một nhóm, các phép hợp có tính bắc cầu?
2. **Thao tác chủ đạo là gì?** Nhiều lần hợp và hỏi cùng nhóm hay thường xuyên tách nhóm, xuất tất cả thành viên?
3. **ID có thể ánh xạ sang `0..n-1` không?** Nếu không, phải cộng chi phí hash map/remapping.
4. **Có cần kích thước nhóm?** Nếu cần, union by size cung cấp `size[find(x)]` trực tiếp.
5. **Có cần truy vấn và cập nhật với hiệu năng tốt trên nhiều bước?** Chọn union by size/rank cùng một biến thể compression chuẩn.
6. **Có cần worst-case cụ thể cho một lời gọi không?** Đừng thay chặn worst-case bằng chặn khấu hao; nếu chỉ có union by size/rank và không compression, `O(log n)` worst-case dễ diễn giải.
7. **Có đồng thời, rollback hoặc xóa cạnh không?** Cần thiết kế riêng và phân tích đúng phiên bản được chọn.

Trong nhiều bài toán thành phần liên thông chỉ **thêm cạnh**, một DSU mảng cha với **union by size + find nén đường lặp** là lựa chọn rõ ràng: ngắn, có bất biến dễ kiểm thử, cung cấp kích thước nhóm và có chặn thời gian khấu hao rất tốt.

## 24. Bài tập tự kiểm tra có lời giải

**Câu 1.** Một phép `find` trên cây có chiều cao `h` có thời gian worst-case bao nhiêu trước khi tính lợi ích của các lần nén về sau?

**Đáp án:** `O(h)`. Một lần tìm có thể phải đi từ nút sâu tới gốc, qua tối đa h cạnh.

**Câu 2.** Bản Union–Find chỉ nối gốc tùy ý và không compression có thể có chiều cao xấu nhất là bao nhiêu?

**Đáp án:** `Θ(n)`. Dãy thao tác hợp có thể tạo một chuỗi gồm n nút với đường sâu n−1.

**Câu 3.** Union by size không compression cho `find` worst-case nào?

**Đáp án:** `O(log n)`, nhờ nhóm chứa một nút ít nhất gấp đôi mỗi lần độ sâu của nó tăng.

**Câu 4.** Trong DSU dùng union by rank, một gốc có rank 5 phải có ít nhất bao nhiêu thành viên?

**Đáp án:** Ít nhất `2^5=32` phần tử, theo bất biến `size(G)≥2^{rank(root)}`.

**Câu 5.** Vì sao rank của gốc có thể lớn hơn chiều cao thật của cây?

**Đáp án:** Path compression rút ngắn đường cha nhưng **không giảm rank**; rank giữ vai trò chặn trên phục vụ heuristic union.

**Câu 6.** Một chuỗi có 100 lần `find(7)` trên cây đường dài bảy cạnh, không có `union` xen kẽ. Bỏ qua các ghi nén, số cạnh duyệt được nếu không compression và nếu dùng full compression là bao nhiêu?

**Đáp án:** Không compression: `100·7=700`. Full compression: lần đầu 7, 99 lần sau mỗi lần 1, tổng `7+99=106`. Khi tính thời gian đầy đủ phải cộng công ghi nén ở lần đầu.

**Câu 7.** Average-case và amortized cost có giống nhau vì đều chia tổng cho số phép toán không?

**Đáp án:** Không. Average-case cần phân phối xác suất của đầu vào/trạng thái; khấu hao chặn tổng công **cho mọi chuỗi hợp lệ**, không giả định dữ liệu ngẫu nhiên.

**Câu 8.** Trong câu `O(mα(n))` khấu hao, có thể suy ra mỗi phép `find` riêng lẻ tốn không quá `O(α(n))` không?

**Đáp án:** Không. Một số phép có thể đắt hơn, và chi phí của chúng được bù bởi những thao tác rẻ khác khi xét cả chuỗi.

**Câu 9.** `α(n)` trong phân tích Union–Find có phải bằng `1/A(n)` không?

**Đáp án:** Không. Nó là một **hàm nghịch đảo theo mức tăng** của một họ hàm Ackermann tăng rất nhanh, chứ không phải nghịch đảo số học.

**Câu 10.** Với định nghĩa minh họa `α_diag(n)=min{i≥0:A(i,i)≥n}` của bài, `α_diag(61)` và `α_diag(62)` bằng bao nhiêu?

**Đáp án:** `α_diag(61)=3` vì `A(3,3)=61`; `α_diag(62)=4` vì vượt ngưỡng 61 nhưng thấp xa `A(4,4)`. Kết quả cụ thể phụ thuộc quy ước định nghĩa.

**Câu 11.** Nén đường đi có làm `componentCount` giảm một không?

**Đáp án:** Không. Nén chỉ thay các con trỏ cha bên trong cùng nhóm; số nhóm không đổi.

**Câu 12.** Nếu hai phần tử đã cùng gốc, `union(x,y)` có được cộng `size[root]` lần nữa không?

**Đáp án:** Không. Đây là hợp trùng; cộng size sẽ đếm hai lần thành viên của cùng nhóm và phá metadata.

**Câu 13.** Muốn biết kích thước nhóm của x khi dùng union by size, đọc `size[x]` có luôn đúng không?

**Đáp án:** Không. Nếu x không phải gốc, `size[x]` có thể là giá trị cũ. Phải dùng `size[find(x)]`.

**Câu 14.** Tại sao chỉ nén đường mà không có chiến lược hợp phù hợp chưa đủ để viện dẫn chặn Ackermann ngược chuẩn?

**Đáp án:** Định lý quen dùng dựa trên **cả** việc giới hạn độ sâu/cấp bậc khi hợp (size/rank) và việc rút ngắn đường khi tìm. Bỏ một giả định phải dùng phân tích khác.

**Câu 15.** Với `V` đỉnh, `E` cạnh và `Q` truy vấn liên thông của đồ thị vô hướng chỉ thêm cạnh, phần DSU được chặn gần đúng bởi biểu thức nào?

**Đáp án:** `O(V+(E+Q)α(V))` theo dạng trình bày thông dụng khi dùng union by size/rank kết hợp compression, chưa tính chi phí ngoài DSU.

**Câu 16.** Trong Kruskal, vì sao tổng thời gian không chỉ là `O(Eα(V))`?

**Đáp án:** Cần sắp xếp các cạnh theo trọng số, thường mất `O(E log E)` trong mô hình so sánh; chi phí DSU chỉ là một thành phần.

**Câu 17.** Có thể dùng path compression tùy ý trong DSU có rollback rồi luôn giữ được chi phí undo hằng số không?

**Đáp án:** Không. Nén có thể sửa nhiều liên kết cha trong một phép tìm, khiến việc hoàn tác cần lưu/khôi phục nhiều thay đổi. Rollback DSU thường chọn quy tắc khác và cần phân tích riêng.

**Câu 18.** Một phép `find` bằng full compression đệ quy trên đường dài h dùng bao nhiêu bộ nhớ stack?

**Đáp án:** Có thể dùng `O(h)` stack. Bản lặp hai lượt, halving và splitting có thể dùng `O(1)` bộ nhớ phụ mỗi lời gọi.

**Câu 19.** Nếu hai chương trình có mảng `parent` khác nhau sau cùng chuỗi `union`, có đủ để kết luận một chương trình sai không?

**Đáp án:** Không. Các chính sách chọn gốc và nén đường có thể tạo hình dạng rừng khác nhau. Cần so sánh **phân hoạch, kết quả `same`, metadata và bất biến**.

**Câu 20.** Một ứng dụng cần liên tục xóa cạnh và tách nhóm. Có thể coi kết quả `O(α(n))` của DSU chuẩn là lời giải đầy đủ không?

**Đáp án:** Không. DSU chuẩn hỗ trợ hợp và tìm đại diện, không trực tiếp tách nhóm. Phải chọn thuật toán liên thông động hoặc offline/rollback thích hợp và tính lại chi phí.

## Ghi nhớ

- **Chi phí khấu hao** chặn tổng chi phí của **một chuỗi thao tác bất kỳ**, không phải trung bình xác suất và không phải worst-case của một lời gọi.
- **Union by size/rank** giữ chiều cao cây `O(log n)` khi chưa nén. **Path compression** rút ngắn đường cha trong những phép `find` và cải thiện các truy vấn tiếp theo.
- Kết hợp hai kỹ thuật cho chặn thường trình bày là **`O(n+mα(n))`** đối với n phần tử và m thao tác, với `α` là **hàm nghịch đảo Ackermann** tăng cực kỳ chậm; các định lý chính xác có thể dùng `α(m,n)` và những quy ước khác nhau.
- **`O(α(n))` khấu hao không có nghĩa `O(1)` worst-case mỗi lần**. Một lần `find` vẫn có thể đi qua `Θ(log n)` cạnh trước khi nén.
- **Nén đường không thay đổi phân hoạch, size, rank hay số nhóm.** Phép `union` chỉ cập nhật kích thước/hạng và giảm số nhóm khi **hai gốc khác nhau**.
- Khi áp dụng DSU trong đồ thị, Kruskal hay hệ thống thực tế, cần cộng **chi phí khởi tạo, sắp xếp, ánh xạ ID và các thao tác khác**; không áp dụng chặn Ackermann ngược một cách máy móc cho rollback, xóa cạnh hoặc truy cập đa luồng không đồng bộ.
