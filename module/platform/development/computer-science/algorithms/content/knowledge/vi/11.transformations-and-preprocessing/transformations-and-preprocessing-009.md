# Biến đổi khoảng, miền giá trị và cấu trúc đầu vào

## Mục tiêu học tập

Khi giải thuật toán, một bước tiền xử lý đúng có thể biến bài toán khó thao tác thành bài toán dễ chứng minh và cài đặt. Bài này tập trung vào ba loại chuyển đổi có liên quan chặt chẽ:

1. **Biến đổi khoảng:** đổi quy ước chỉ số, khoảng đóng/nửa mở, chuẩn hóa truy vấn và thao tác cập nhật đoạn.
2. **Biến đổi miền giá trị:** nén tọa độ/giá trị thưa, ánh xạ khóa về chỉ số nhỏ nhưng vẫn bảo toàn thứ tự, và xử lý ranh giới của những khoảng rất lớn.
3. **Biến đổi cấu trúc đầu vào:** chuyển dữ liệu từ dạng thuận tiện để nhập sang dạng thuận tiện để xử lý, ví dụ danh sách cạnh thành danh sách kề, lưới thành chỉ số một chiều, hoặc danh sách thao tác thành các sự kiện có thứ tự.

Sau bài học, bạn có thể chọn phép biến đổi phù hợp, phát biểu bất biến và điều kiện hợp lệ của phép biến đổi, kiểm soát mất mát thông tin, phân tích chi phí tiền xử lý, và dùng ví dụ **Java 17+** để áp dụng tổng tiền tố, mảng hiệu, nén tọa độ và chuyển cấu trúc đồ thị.

## 1. Vì sao cần biến đổi trước khi giải?

Giả sử một chương trình nhận rất nhiều truy vấn tổng trên các đoạn liên tiếp của mảng. Nếu tính lại tổng từng đoạn, mỗi truy vấn có thể mất thời gian tuyến tính theo độ dài đoạn. Nhưng nếu **tiền xử lý tổng tiền tố**, nhiều truy vấn có thể trả lời bằng hai phép tra cứu và một phép trừ.

Giả sử dữ liệu là hàng triệu tọa độ từ `-10^9` đến `10^9` nhưng chỉ có vài nghìn giá trị xuất hiện. Cấp phát một mảng theo toàn bộ miền có thể không khả thi. Ta có thể **nén giá trị** thành các chỉ số liên tiếp từ 0 tới số lượng giá trị phân biệt trừ một.

Giả sử dữ liệu đồ thị nhập dưới dạng các cạnh `(u,v)`, nhưng thuật toán BFS cần truy cập nhanh mọi đỉnh kề với `u`. Khi đó chuyển **edge list** thành **adjacency list** có thể tránh việc quét toàn bộ danh sách cạnh mỗi khi thăm một đỉnh.

| Dạng đầu vào | Dạng hữu ích sau tiền xử lý | Lợi ích chính |
| --- | --- | --- |
| Mảng cùng nhiều truy vấn tổng đoạn | Mảng tổng tiền tố | Truy vấn đoạn nhanh |
| Nhiều cập nhật cộng vào đoạn, cần kết quả cuối | Mảng hiệu | Ghi nhận mỗi cập nhật ở hai biên |
| Tọa độ rất lớn nhưng số tọa độ thực tế ít | Danh sách tọa độ sắp tăng, không trùng + ánh xạ rank | Dùng mảng nhỏ theo số giá trị phân biệt |
| Nhiều khoảng trên trục số rộng | Các mốc đầu/cuối, sự kiện và đoạn giữa các mốc | Quét theo các điểm thay đổi thay vì duyệt mọi điểm |
| Danh sách cạnh đồ thị | Danh sách kề hoặc ma trận kề | Tối ưu truy cập láng giềng theo loại bài toán |
| Lưới hai chiều | Tổng tiền tố 2D hoặc ánh xạ chỉ số một chiều | Hỗ trợ truy vấn hình chữ nhật/lưu trữ tuyến tính |

**Nguyên tắc:** phép biến đổi phải phục vụ loại thao tác sẽ làm tiếp theo. Không phải cứ biến đổi đầu vào nhiều lần thì thuật toán nhanh hơn; chi phí tiền xử lý, bộ nhớ và tính đúng đắn của ánh xạ phải được tính chung.

## 2. Chuẩn hóa khoảng và chỉ số

Một phần lớn lỗi thuật toán không nằm ở công thức cao cấp, mà ở việc không thống nhất **chỉ số bắt đầu từ đâu** và **cận nào được tính**.

### 2.1. Khoảng đóng, nửa mở và khoảng rỗng

Với chỉ số nguyên:

- `[L,R]` là **khoảng đóng**, gồm cả L và R. Nếu `L≤R`, số vị trí là `R-L+1`.
- `[L,R)` là **khoảng nửa mở**, gồm L, không gồm R. Nếu `L≤R`, số vị trí là `R-L`.
- `(L,R]` không gồm L, có gồm R; trên chỉ số nguyên có thể đổi thành `[L+1,R+1)` nếu cộng 1 không tràn.
- `[L,R)` với `L=R` là **rỗng**; `[L,L]` trên miền số nguyên là **một điểm**.

Đối với mảng Java độ dài `n`, quy ước tiện dụng là:

\[
0\le L\le R\le n,\qquad [L,R).
\]

Lúc đó đầu mảng là 0, cuối mảng là `n`, và **không bao giờ cần truy cập `a[n]`**. Độ dài đoạn luôn đúng bằng `R-L`, kể cả đoạn rỗng.

Ví dụ mảng `a=[3,1,4,1,5]`:

| Ý định | Dạng chỉ số | Phần tử được chọn | Độ dài |
| --- | --- | --- | ---: |
| Lấy chỉ số 1 đến 3, gồm cả 3 | `[1,3]` | `[1,4,1]` | 3 |
| Cùng đoạn ở dạng nửa mở | `[1,4)` | `[1,4,1]` | 3 |
| Lấy từ đầu đến hết | `[0,5)` | `[3,1,4,1,5]` | 5 |
| Không lấy phần tử nào tại vị trí 2 | `[2,2)` | `[]` | 0 |
| Chỉ phần tử chỉ số 2 | `[2,3)` | `[4]` | 1 |

**Quy tắc quan trọng với miền chỉ số nguyên:**

\[
[L,R]\longleftrightarrow[L,R+1).
\]

Tuy nhiên, phải kiểm soát kiểu số khi tính `R+1`. Nếu R có thể là `Integer.MAX_VALUE`, biểu thức `R+1` thực hiện trên `int` sẽ tràn; dùng `(long)R+1L` trước khi cộng. Nếu miền đã dùng `long` đến `Long.MAX_VALUE`, không thể biểu diễn `R+1` bằng `long`; phải dùng quy tắc biên khác, kiểu rộng hơn hoặc ký hiệu sentinel riêng.

**Không áp dụng máy móc công thức `[L,R]→[L,R+1)` cho các khoảng trên số thực.** Trên số thực, `[2,5]` và `[2,6)` là những tập khác nhau. Phép cộng 1 chỉ có ý nghĩa để chuyển một khoảng **các điểm nguyên rời rạc** sang dạng nửa mở biểu diễn cùng tập điểm nguyên.

### 2.2. Chuyển từ 1-based sang 0-based

Một số đề bài nhập vị trí từ **1 đến n**, trong khi mảng Java dùng chỉ số từ **0 đến n-1**. Nếu yêu cầu tổng từ vị trí 1-based `p` đến `q`, tính cả hai đầu, đoạn tương ứng trong mảng 0-based là:

\[
[p-1,\;q).
\]

Ví dụ với `a=[3,1,4,1,5]`, truy vấn “vị trí 2 đến 4” (đánh số từ 1) là các giá trị `1,4,1`. Sau đổi thành chỉ số 0-based nửa mở, dùng `[1,4)`. Hai quy ước cho cùng tập phần tử nếu chuyển đúng.

**Lỗi phổ biến:** chuyển cả hai cận bằng cách trừ 1 rồi lại dùng `[L,R)`, khiến mất phần tử cuối; hoặc chuyển cận phải cộng 1 hai lần.

### 2.3. Chuẩn hóa ngay tại ranh giới nhập

Một thiết kế API rõ ràng thường:

1. Đọc quy ước trong đề bài/định dạng dữ liệu.
2. Kiểm tra `0≤L≤R≤n` sau khi chuyển.
3. Lưu một quy ước **nội bộ duy nhất**, chẳng hạn nửa mở `[L,R)`.
4. Chỉ chuyển lại khi xuất kết quả nếu người dùng yêu cầu quy ước khác.

Không nên để một hàm nhận khoảng đóng còn hàm khác mặc định nửa mở mà không ghi trong tên hoặc hợp đồng.

## 3. Tổng tiền tố: biến truy vấn tổng đoạn thành phép trừ

Với mảng `a` có `n` phần tử, định nghĩa mảng tổng tiền tố `prefix` dài `n+1`:

\[
prefix[0]=0,\qquad
prefix[i+1]=prefix[i]+a[i],\quad 0\le i<n.
\]

Vậy `prefix[i]` là tổng của các phần tử trong đoạn nửa mở `a[0..i)`. Tổng đoạn `[L,R)` là:

\[
\operatorname{sum}(L,R)=prefix[R]-prefix[L].
\]

**Lập luận:** `prefix[R]` chứa tổng từ 0 đến `R-1`; `prefix[L]` chứa tổng từ 0 đến `L-1`. Lấy hiệu triệt tiêu phần trước L, chỉ giữ lại các phần tử L đến `R-1`.

Ví dụ:

```text
a:       [3, 1, 4, 1, 5]
prefix:  [0, 3, 4, 8, 9, 14]
             |        |
sum [1,4) = prefix[4] - prefix[1] = 9 - 3 = 6
```

Có hai bước chi phí:

- **Tiền xử lý:** `O(n)` thời gian và `O(n)` bộ nhớ.
- **Mỗi truy vấn tổng đoạn:** `O(1)` thời gian sau tiền xử lý.

Nếu có `q` truy vấn trên mảng **không đổi**, tổng thời gian là `O(n+q)`, thay vì có thể `O(nq)` nếu mỗi lần cộng lại cả một đoạn dài.

### 3.1. Bất biến của tổng tiền tố

Sau khi xây xong vị trí `prefix[i]`:

\[
prefix[i]=\sum_{j=0}^{i-1}a[j].
\]

Cơ sở `prefix[0]=0` đúng với tổng rỗng. Bước quy nạp thêm đúng `a[i]` vào `prefix[i]` để nhận `prefix[i+1]`. Bởi vậy công thức trả lời đoạn là chính xác.

**Chú ý:** tổng tiền tố giải truy vấn tổng trên mảng **tĩnh** tốt, nhưng nếu nhiều lần cập nhật phần tử thì các giá trị tiền tố phía sau phải đổi. Với cập nhật và truy vấn xen kẽ, có thể phải dùng Fenwick tree hoặc segment tree thay vì tính lại prefix.

### 3.2. Tổng 2D cho truy vấn hình chữ nhật

Với ma trận `rows×cols`, có thể tạo mảng `P` kích thước `(rows+1)×(cols+1)` với:

\[
P[r+1][c+1]=A[r][c]+P[r][c+1]+P[r+1][c]-P[r][c].
\]

Tổng hình chữ nhật nửa mở có góc trên trái `(r_1,c_1)` và góc dưới phải không bao gồm `(r_2,c_2)` là:

\[
P[r_2][c_2]-P[r_1][c_2]-P[r_2][c_1]+P[r_1][c_1].
\]

Đây là cùng một nguyên tắc chuẩn hóa biên, mở rộng từ một chiều sang hai chiều. Xây tổng tiền tố 2D tốn `O(rows×cols)`, mỗi truy vấn hình chữ nhật tốn `O(1)` sau khi có bảng.

## 4. Mảng hiệu: biến cập nhật đoạn thành hai thay đổi ở biên

Nếu có nhiều thao tác “**cộng d vào mọi phần tử trong đoạn**” và chỉ cần tạo kết quả cuối sau tất cả cập nhật, mảng hiệu (difference array) là một tiền xử lý rất hữu ích.

Với mảng cập nhật cộng d vào đoạn nửa mở `[L,R)`, thay vì cộng từng phần tử, ghi:

```text
diff[L] += d
diff[R] -= d
```

Sau khi xử lý hết các cập nhật, quét tổng tiền tố của `diff` để lấy lượng thay đổi tại từng vị trí.

**Vì sao đúng?** Tại một chỉ số `i`, tổng các sự kiện trong `diff[0..i]` đã cộng d khi bước qua vị trí L và sẽ trừ d khi bước tới vị trí R. Do đó đóng góp của cập nhật chỉ tồn tại khi `L≤i<R`.

Nếu đề bài nhập khoảng **đóng `[L,R]`**, đổi thành `[L,R+1)`. Khi mảng dài n, nên tạo `diff` có **n+1 vị trí** để sự kiện tại `R+1=n` được ghi hợp lệ.

### Ví dụ

Mảng gốc:

```text
a = [3, 1, 4, 1, 5]
```

Hai cập nhật, chỉ số 0-based và **khoảng đóng**:

1. Cộng 2 cho `[1,3]`.
2. Trừ 1 cho `[0,0]`.

Ghi mảng hiệu n+1:

```text
Bước đầu:        diff = [ 0, 0, 0, 0, 0, 0]
Cộng 2 [1,3]:   diff = [ 0, 2, 0, 0,-2, 0]
Trừ 1 [0,0]:    diff = [-1, 3, 0, 0,-2, 0]
```

Quét tổng tích lũy của `diff` cho chỉ số 0..4 thu được `[-1,2,2,2,0]`. Cộng vào mảng gốc:

```text
Kết quả = [2, 3, 6, 3, 5]
```

Với `q` cập nhật đoạn, nếu chỉ cần **materialize kết quả một lần ở cuối**, tổng chi phí là `O(n+q)` thời gian, `O(n)` bộ nhớ. Nếu yêu cầu đọc giá trị hoặc tính tổng đoạn **ngay sau mỗi cập nhật**, mảng hiệu thuần túy không trả các truy vấn trực tuyến đó trong `O(1)`: cần cấu trúc dữ liệu khác hoặc một quy trình xử lý lại.

### 4.1. Bất biến và giới hạn

Mỗi cập nhật có đúng một sự kiện bắt đầu và một sự kiện kết thúc. Khi quét `diff`, biến `active` bằng tổng các cập nhật đang có hiệu lực tại chỉ số hiện tại. Vì vậy giá trị cuối của ô i bằng `a[i]+active`.

Số lần cộng d có thể lớn hoặc phần tử có thể gần giới hạn `int`. Trong Java, nên dùng `long` để lưu tổng tiền tố và các chênh lệch nếu phạm vi dữ liệu có thể vượt `int`; cũng cần quy định rõ hành vi khi tổng thực sự vượt `long`.

## 5. Miền giá trị rất rộng nhưng dữ liệu thưa

Giả sử dãy chỉ có các giá trị:

```text
[1_000_000_000, -5, 1_000_000_000, 7]
```

Nếu dùng **giá trị** trực tiếp làm chỉ số mảng, ta có vấn đề:

- Có giá trị âm.
- Khoảng từ min đến max rất lớn.
- Chỉ có **ba giá trị phân biệt** nhưng miền trải rộng trên hơn một tỷ đơn vị.

Với những bài toán chỉ cần so sánh **thứ tự tương đối**, ta có thể dùng **nén giá trị/coordinate compression**:

1. Sao chép toàn bộ giá trị.
2. Sắp xếp bản sao tăng dần.
3. Loại phần tử trùng, thu danh sách `unique`.
4. Ánh xạ mỗi giá trị `x` thành vị trí của nó trong `unique`, gọi là `rank(x)`.

```text
unique tăng: [-5, 7, 1_000_000_000]
rank:         0   1        2

input: [1_000_000_000, -5, 1_000_000_000, 7]
ranks: [2, 0, 2, 1]
```

Điều được **bảo toàn**:

\[
x<y\quad\Longleftrightarrow\quad rank(x)<rank(y)
\]

đối với các giá trị nằm trong tập đã nén, và:

\[
x=y\quad\Longleftrightarrow\quad rank(x)=rank(y).
\]

Do đó số giá trị phân biệt, thứ tự và tính bằng nhau của các khóa được giữ nguyên. Có thể dùng rank làm chỉ số của Fenwick tree, segment tree, mảng tần suất hoặc bảng đếm.

**Điều không được bảo toàn:** khoảng cách số học giữa các giá trị. Trong ví dụ, `7-(-5)=12`, còn `rank(7)-rank(-5)=1`. Vì vậy **không thể lấy hiệu rank để tính độ dài thực, khoảng cách, tổng tọa độ hoặc diện tích**, trừ khi phép tính được định nghĩa ngay trên không gian rank.

### 5.1. Chi phí nén giá trị

Với n phần tử và u giá trị phân biệt (`u≤n`):

- Sao chép và sắp xếp: `O(n log n)` thời gian.
- Loại trùng: `O(n)`.
- Ánh xạ từng phần tử bằng tìm kiếm nhị phân trên `unique`: `O(n log u)`.
- Bộ nhớ phụ: `O(n)` cho bản sao và ánh xạ; nếu chỉ lưu bảng giá trị phân biệt thì `O(u)` cho bảng.

Có thể dùng hash map ánh xạ từ giá trị sang rank sau khi đã sắp unique để mỗi lần tra cứu có chi phí trung bình `O(1)`, nhưng cần tính overhead và giả thiết hash. Nếu chỉ có vài phần tử, nén dữ liệu có thể tốn hơn lợi ích mang lại.

### 5.2. Rank không phải giá trị gốc

Nếu bài toán cần **trả lại tọa độ** cho người dùng, phải giữ mảng `unique` để giải nén: `originalValue = unique[rank]`. Nếu bỏ bảng này, dữ liệu không còn đủ để phục hồi giá trị gốc chỉ từ rank.

Với dữ liệu cập nhật xuất hiện **giá trị mới chưa có trong unique**, không thể tự dùng rank cũ cho giá trị đó. Cần xây lại phép nén, dùng cấu trúc động, hoặc chuẩn bị toàn bộ giá trị có thể xuất hiện trong quá trình xử lý offline.

## 6. Nén các mốc của khoảng: không duyệt từng tọa độ

Một bài toán khác: cho nhiều khoảng trên trục số nguyên, yêu cầu tính:

- Bao nhiêu **điểm nguyên** thuộc ít nhất một khoảng?
- Có bao nhiêu khoảng cùng phủ lên một điểm?
- Tổng số lần phủ nếu đếm một điểm nhiều lần khi nằm trong nhiều khoảng?

Ví dụ có ba khoảng **đóng trên số nguyên**:

```text
[2,5], [4,8], [10,10]
```

Các điểm nguyên được phủ là `2,3,4,5,6,7,8,10`, tổng cộng **8 điểm khác nhau**. Hai khoảng đầu cùng phủ `4` và `5` nên mức phủ lớn nhất là **2**. Nếu đếm số lần phủ có lặp, tổng là `4+5+1=10`.

### 6.1. Chuyển về các khoảng nửa mở trên miền nguyên

Đầu/cuối của các khoảng đóng được chuyển:

```text
[2,5]   -> [2,6)
[4,8]   -> [4,9)
[10,10] -> [10,11)
```

Các mốc nơi mức phủ có thể thay đổi là:

```text
[2, 4, 6, 9, 10, 11]
```

Đây là danh sách **tọa độ thực** đã được sắp và loại trùng, không phải rank thuần túy. Giữa hai mốc liên tiếp, không có điểm bắt đầu hoặc kết thúc khoảng mới, nên mức phủ là hằng số.

### 6.2. Dùng mảng hiệu trên các mốc đã nén

Gọi `xs` là mảng mốc tăng dần không trùng. Với mỗi khoảng `[L,R)`:

- Tìm chỉ số `i=lowerBound(xs,L)`.
- Tìm chỉ số `j=lowerBound(xs,R)`.
- Ghi `change[i]+=1`, `change[j]-=1`.

Khi quét từ mốc `xs[t]` sang mốc `xs[t+1]`, tổng tích lũy của các thay đổi là **số khoảng phủ** lên toàn bộ đoạn nửa mở `[xs[t], xs[t+1])`.

| Đoạn giữa hai mốc | Độ dài số điểm nguyên | Số khoảng phủ | Đóng góp vào tổng số lần phủ |
| --- | ---: | ---: | ---: |
| `[2,4)` | 2 | 1 | 2 |
| `[4,6)` | 2 | 2 | 4 |
| `[6,9)` | 3 | 1 | 3 |
| `[9,10)` | 1 | 0 | 0 |
| `[10,11)` | 1 | 1 | 1 |

Suy ra:

\[
\text{Số điểm nguyên được phủ} =2+2+3+1=8,
\]

\[
\text{Tổng số lần phủ} =2+4+3+0+1=10,
\]

\[
\text{Mức phủ lớn nhất}=2.
\]

**Bất biến của sweep:** sau khi cộng mọi sự kiện tại `xs[t]`, biến `active` bằng số khoảng bao phủ các điểm nguyên trong `[xs[t],xs[t+1])`. Vì không có ranh giới nằm trong đoạn này, `active` không đổi cho đến mốc tiếp theo.

### 6.3. Vì sao phải giữ độ dài thật giữa hai mốc?

Một lỗi nghiêm trọng là xem hai mốc liên tiếp trong `xs` như “cách nhau đúng một đơn vị”. Thực tế `xs[2]=6` và `xs[3]=9` cách nhau **3**. Đoạn `[6,9)` chứa các điểm nguyên `6,7,8`, không phải một điểm.

Vì vậy:

- **Rank/index** dùng để tìm vị trí trong cấu trúc nén.
- **Giá trị tọa độ gốc** dùng để tính độ dài `xs[t+1]-xs[t]`.
- Tính độ phủ bằng tổng `active×độ dài thật`.

Nén tọa độ làm số vị trí cần xử lý nhỏ lại mà **không được thay đổi thước đo** của trục gốc.

### 6.4. Chi phí

Với q khoảng:

1. Tạo `2q` mốc đầu/cuối: `O(q)`.
2. Sắp, loại trùng các mốc: `O(q log q)`.
3. Ánh xạ hai mốc cho mỗi khoảng bằng tìm kiếm nhị phân: `O(q log q)`.
4. Ghi mảng hiệu và quét các đoạn: `O(q)`.

Tổng thời gian `O(q log q)`, bộ nhớ `O(q)`, **không phụ thuộc vào độ rộng số học của miền tọa độ**. So với việc duyệt trực tiếp hàng tỷ điểm nguyên, lợi ích có thể rất lớn khi số khoảng ít.

Nếu bài toán cần trả về **giá trị mức phủ tại từng điểm trong một miền rất lớn**, không thể in hàng tỷ giá trị trong thời gian `O(q log q)`; phép nén hỗ trợ biểu diễn kết quả **theo từng đoạn có mức phủ cố định** hoặc phục vụ truy vấn có chọn lọc.

## 7. Độ dài, số điểm và xử lý biên không phải một thứ

Phải phân biệt chính xác ba kiểu bài toán:

1. **Điểm nguyên rời rạc:** khoảng đóng `[2,5]` chứa 4 điểm nguyên `2,3,4,5`. Đổi sang `[2,6)` rồi lấy hiệu hai mốc là 4 là hợp lệ.
2. **Độ dài liên tục trên trục thực:** khoảng `[2,5]` có độ dài 3, không phải 4. Phần tử biên đóng/mở không đổi độ dài Lebesgue, nhưng có thể ảnh hưởng tính giao tại một điểm.
3. **Đếm số khoảng đồng thời chứa một điểm biên:** hai khoảng `[1,3)` và `[3,5)` không cùng phủ tại x=3; hai khoảng đóng `[1,3]` và `[3,5]` cùng chứa điểm 3.

Do đó cùng một bộ tọa độ có thể yêu cầu **quy tắc sự kiện khác nhau** khi hai sự kiện có cùng tọa độ. Nếu dùng sweep line cho khoảng nửa mở `[L,R)` và cần trạng thái tại mốc, phải loại khoảng kết thúc tại R khỏi mức phủ tại R; khi xét khoảng đóng và muốn đếm giao chỉ tại điểm biên, cần xử lý sự kiện theo chính sách tương ứng.

Bài Java ở mục 10 tính **số điểm nguyên được phủ** bằng cách chuyển các khoảng đóng nguyên sang nửa mở `[L,R+1)`, nên không có nhập nhằng kiểu này. Không lấy cùng công thức để tính độ dài liên tục của một khoảng đóng trên số thực.

## 8. Sắp xếp và chuẩn hóa các khoảng khi cần hợp nhất

Một phép biến đổi khoảng phổ biến khác là **gộp những đoạn chồng nhau** để giảm số đoạn cần xử lý.

Ví dụ các khoảng nửa mở:

```text
[1,4), [2,6), [8,10), [9,12)
```

Sau khi sắp theo cận trái rồi hợp nhất các khoảng giao nhau:

```text
[1,6), [8,12)
```

Mẫu thuật toán:

1. Kiểm tra mỗi đoạn có `L≤R` và thống nhất quy ước.
2. Sắp các đoạn theo `L` tăng, rồi `R` tăng để kết quả xác định.
3. Giữ một đoạn hiện tại `[start,end)`.
4. Nếu đoạn tiếp theo có `L<end`, hai đoạn **giao nhau với độ dài dương**; thay `end=max(end,R)`.
5. Nếu không, xuất đoạn hiện tại rồi bắt đầu đoạn mới.

**Chính sách tại điểm chạm phải được định nghĩa riêng.** Hai khoảng `[1,3)` và `[3,5)` không giao nhau dưới quy ước nửa mở; nhưng nếu bài toán chỉ cần biểu diễn **hợp tập không có khoảng trống** bằng ít đoạn, có thể gộp chúng thành `[1,5)` khi `L≤end`. Không có một điều kiện `<`/`<=` đúng cho mọi bài toán; chọn theo yêu cầu “chồng lên nhau” hay “liền nhau cũng gộp”.

Độ phức tạp điển hình là `O(q log q)` để sắp và `O(q)` để quét; bộ nhớ phụ tùy cách sắp và lưu kết quả.

Không được nhầm **gộp khoảng** với **đếm mức phủ**: sau khi gộp, bạn vẫn biết hợp của các khoảng, nhưng đã mất số lượng khoảng ban đầu chồng lên nhau tại từng điểm. Nếu bài toán cần mức phủ lớn nhất, cần giữ sự kiện hoặc cấu trúc phù hợp thay vì chỉ giữ các đoạn đã gộp.

## 9. Biến đổi cấu trúc đầu vào: danh sách cạnh thành danh sách kề

Không phải mọi tiền xử lý đều liên quan đến số hoặc khoảng. Đôi khi **cấu trúc lưu dữ liệu** quyết định thuật toán chạy nhanh hay chậm.

Cho đồ thị có V đỉnh đánh số `0..V-1` và E cạnh có hướng. Định dạng đầu vào thường là **edge list**:

```text
V = 4
Các cạnh:
0 -> 1
0 -> 2
2 -> 3
1 -> 3
```

Nếu giữ nguyên danh sách cạnh, muốn biết những đỉnh đi ra từ đỉnh 0 có thể phải quét toàn bộ E cạnh. Với BFS/DFS, thao tác tra láng giềng diễn ra nhiều lần, nên có thể chuyển sang **adjacency list**:

```text
adj[0] = [1,2]
adj[1] = [3]
adj[2] = [3]
adj[3] = []
```

Việc chuyển đổi:

1. Tạo V danh sách trống.
2. Với mỗi cạnh có hướng `(u,v)`, kiểm tra `0≤u,v<V`.
3. Thêm v vào cuối `adj[u]`.

Độ phức tạp xây danh sách kề là `O(V+E)` thời gian và `O(V+E)` bộ nhớ để lưu cả đỉnh lẫn các cạnh. Trong các triển khai dùng danh sách kề, BFS/DFS chuẩn cũng chạy `O(V+E)` vì mỗi đỉnh/cạnh được xét số lần bị chặn.

### 9.1. Giữ đúng ngữ nghĩa đồ thị

- **Đồ thị có hướng:** từ `u→v` chỉ thêm `v` vào `adj[u]`.
- **Đồ thị vô hướng:** mỗi cạnh thường được lưu theo **hai chiều**: thêm `v` vào `adj[u]` và `u` vào `adj[v]`. Phải xử lý vòng tự khép `u=v` theo quy ước lưu trữ của bài toán.
- **Cạnh lặp:** nếu input có hai bản ghi `(u,v)`, code đơn giản có thể lưu cả hai; nếu bài toán yêu cầu đồ thị đơn không cạnh lặp, phải loại trùng có chủ ý.
- **Trọng số cạnh:** phải lưu cả cặp `(đỉnh đích, trọng số)`; không được bỏ trọng số khi chuyển đổi.
- **Đỉnh được đánh số từ 1:** phải chuẩn hóa về 0-based **đúng một lần** nếu mảng nội bộ dùng 0-based.
- **Thứ tự kề:** thêm theo thứ tự đọc không đồng nghĩa danh sách kề được sắp. Nếu thứ tự duyệt láng giềng quan trọng, cần sắp từng danh sách hoặc dùng chính sách riêng.

### 9.2. Edge list, adjacency list và adjacency matrix

| Cấu trúc | Không gian điển hình | Truy xuất láng giềng của u | Kiểm tra cạnh cụ thể u→v |
| --- | --- | --- | --- |
| Edge list | `O(E)`, chưa kể danh sách đỉnh | Có thể phải quét `O(E)` | Có thể `O(E)` |
| Adjacency list | `O(V+E)` | `O(outdegree(u))` để duyệt hết | `O(outdegree(u))` nếu danh sách chưa có chỉ mục |
| Adjacency matrix | `O(V²)` | Quét một hàng `O(V)` | `O(1)` |

Đồ thị thưa (`E` nhỏ so với `V²`) thường phù hợp với adjacency list. Đồ thị rất dày hoặc bài toán hỏi sự tồn tại của cạnh rất nhiều lần có thể cân nhắc ma trận kề. Nếu đang chạy BFS trên edge list và phải quét tất cả cạnh ở mỗi đỉnh, việc chuyển sang adjacency list có thể giúp giảm đáng kể tổng thời gian.

**Đây là một ví dụ điển hình của biến đổi cấu trúc đầu vào:** dữ liệu biểu diễn cùng một đồ thị, nhưng chi phí phép toán sau tiền xử lý đã khác.

## 10. Java 17+ — Ví dụ độc lập và có thể chạy

Tệp **`RangeDomainInputDemo.java`** sau minh họa bốn phép biến đổi trong một chương trình:

1. Tổng tiền tố và truy vấn đoạn `[L,R)`.
2. Mảng hiệu cho cập nhật cộng trên khoảng đóng nguyên.
3. Nén giá trị và nén mốc khoảng để tính số điểm nguyên được phủ.
4. Chuyển **danh sách cạnh có hướng** thành danh sách kề.

Chương trình dùng `long` cho tổng, mốc kết thúc sau khi cộng 1 và độ dài đoạn; không sửa các mảng input.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

public class RangeDomainInputDemo {

    static long[] prefixSums(int[] input) {
        Objects.requireNonNull(input, "input");

        long[] prefix = new long[input.length + 1];
        for (int i = 0; i < input.length; i++) {
            prefix[i + 1] = prefix[i] + input[i];
        }
        return prefix;
    }

    // Queries a half-open interval [left, rightExclusive).
    static long rangeSum(
            long[] prefix, int left, int rightExclusive) {

        Objects.requireNonNull(prefix, "prefix");
        if (left < 0 || rightExclusive < left
                || rightExclusive >= prefix.length) {
            throw new IllegalArgumentException("invalid range");
        }

        return prefix[rightExclusive] - prefix[left];
    }

    // Each update is {left, rightInclusive, delta}.
    static long[] applyRangeAdds(int[] input, int[][] updates) {
        Objects.requireNonNull(input, "input");
        Objects.requireNonNull(updates, "updates");

        long[] change = new long[input.length + 1];

        for (int[] update : updates) {
            if (update == null || update.length != 3) {
                throw new IllegalArgumentException("invalid update");
            }

            int left = update[0];
            int right = update[1];
            int delta = update[2];

            if (left < 0 || left > right
                    || right >= input.length) {
                throw new IllegalArgumentException("invalid range");
            }

            change[left] += delta;
            change[right + 1] -= delta;
        }

        long[] result = new long[input.length];
        long active = 0;

        for (int i = 0; i < input.length; i++) {
            active += change[i];
            result[i] = (long) input[i] + active;
        }

        return result;
    }

    // Equal original values map to the same rank.
    static int[] compressValues(int[] input) {
        Objects.requireNonNull(input, "input");

        int[] unique = input.clone();
        Arrays.sort(unique);

        int count = 0;
        for (int i = 0; i < unique.length; i++) {
            if (count == 0 || unique[count - 1] != unique[i]) {
                unique[count++] = unique[i];
            }
        }

        int[] dictionary = Arrays.copyOf(unique, count);
        int[] ranks = new int[input.length];

        for (int i = 0; i < input.length; i++) {
            ranks[i] = Arrays.binarySearch(dictionary, input[i]);
        }
        return ranks;
    }

    // These intervals are CLOSED over integer points: [left, right].
    record CoverageSummary(
            long[] endpoints,
            long coveredPoints,
            long multiplicityPoints,
            long maxOverlap) {
    }

    static CoverageSummary summarizeIntegerRanges(int[][] ranges) {
        Objects.requireNonNull(ranges, "ranges");

        if (ranges.length == 0) {
            return new CoverageSummary(new long[0], 0, 0, 0);
        }
        if (ranges.length > Integer.MAX_VALUE / 2) {
            throw new IllegalArgumentException("too many ranges");
        }

        long[] endpoints = new long[2 * ranges.length];

        for (int i = 0; i < ranges.length; i++) {
            int[] range = ranges[i];

            if (range == null || range.length != 2
                    || range[0] > range[1]) {
                throw new IllegalArgumentException("invalid interval");
            }

            endpoints[2 * i] = (long) range[0];
            endpoints[2 * i + 1] = (long) range[1] + 1L;
        }

        Arrays.sort(endpoints);

        int count = 0;
        for (int i = 0; i < endpoints.length; i++) {
            if (count == 0
                    || endpoints[count - 1] != endpoints[i]) {
                endpoints[count++] = endpoints[i];
            }
        }

        long[] xs = Arrays.copyOf(endpoints, count);
        long[] diff = new long[xs.length];

        for (int[] range : ranges) {
            int begin = Arrays.binarySearch(xs, (long) range[0]);
            int end = Arrays.binarySearch(
                    xs, (long) range[1] + 1L);

            diff[begin]++;
            diff[end]--;
        }

        long active = 0;
        long covered = 0;
        long multiplicity = 0;
        long maxOverlap = 0;

        for (int i = 0; i + 1 < xs.length; i++) {
            active += diff[i];
            long width = xs[i + 1] - xs[i];

            if (active > 0) {
                covered += width;
            }

            multiplicity += active * width;
            maxOverlap = Math.max(maxOverlap, active);
        }

        return new CoverageSummary(
                xs, covered, multiplicity, maxOverlap);
    }

    // Directed edge list -> adjacency list.
    static List<List<Integer>> directedAdjacency(
            int vertexCount, int[][] edges) {

        if (vertexCount < 0) {
            throw new IllegalArgumentException("negative vertex count");
        }
        Objects.requireNonNull(edges, "edges");

        List<List<Integer>> adj = new ArrayList<>(vertexCount);
        for (int v = 0; v < vertexCount; v++) {
            adj.add(new ArrayList<>());
        }

        for (int[] edge : edges) {
            if (edge == null || edge.length != 2) {
                throw new IllegalArgumentException("invalid edge");
            }

            int from = edge[0];
            int to = edge[1];

            if (from < 0 || from >= vertexCount
                    || to < 0 || to >= vertexCount) {
                throw new IllegalArgumentException("vertex out of range");
            }

            adj.get(from).add(to);
        }

        return adj;
    }

    public static void main(String[] args) {
        int[] a = {3, 1, 4, 1, 5};
        long[] prefix = prefixSums(a);

        System.out.println("Prefix: " + Arrays.toString(prefix));
        System.out.println("Sum [1,4): " + rangeSum(prefix, 1, 4));

        int[][] updates = {{1, 3, 2}, {0, 0, -1}};
        System.out.println("After updates: "
                + Arrays.toString(applyRangeAdds(a, updates)));

        int[] sparse = {1_000_000_000, -5, 1_000_000_000, 7};
        System.out.println("Ranks: "
                + Arrays.toString(compressValues(sparse)));

        int[][] integerRanges = {{2, 5}, {4, 8}, {10, 10}};
        CoverageSummary summary =
                summarizeIntegerRanges(integerRanges);

        System.out.println("Compressed endpoints: "
                + Arrays.toString(summary.endpoints()));
        System.out.println("Covered integer points: "
                + summary.coveredPoints());
        System.out.println("Total multiplicity: "
                + summary.multiplicityPoints());
        System.out.println("Maximum overlap: "
                + summary.maxOverlap());

        int[][] directedEdges = {
                {0, 1}, {0, 2}, {2, 3}, {1, 3}
        };

        System.out.println("Adjacency: "
                + directedAdjacency(4, directedEdges));
        System.out.println("Original: " + Arrays.toString(a));
    }
}
```

Biên dịch và chạy bằng **JDK 17 trở lên** từ thư mục chứa tệp:

```bash
javac RangeDomainInputDemo.java
java RangeDomainInputDemo
```

Đầu ra chuẩn:

```text
Prefix: [0, 3, 4, 8, 9, 14]
Sum [1,4): 6
After updates: [2, 3, 6, 3, 5]
Ranks: [2, 0, 2, 1]
Compressed endpoints: [2, 4, 6, 9, 10, 11]
Covered integer points: 8
Total multiplicity: 10
Maximum overlap: 2
Adjacency: [[1, 2], [3], [3], []]
Original: [3, 1, 4, 1, 5]
```

### 10.1. Những điểm cần chú ý trong chương trình

- `prefixSums` tạo mảng dài `n+1`, nên `prefix[0]=0` cho đoạn rỗng và `prefix[n]` cho tổng toàn bộ mảng.
- `rangeSum` nhận **cận phải không bao gồm**; `rightExclusive` được phép bằng `n` nhưng không vượt `n`.
- `applyRangeAdds` lại nhận cập nhật **khoảng đóng [left,rightInclusive]**; vì thế dùng sự kiện `change[right+1]-=delta`. Tên biến và bình luận phân biệt rõ hai quy ước.
- `change` và kết quả là `long[]` để tránh tràn `int` trong nhiều trường hợp cộng dồn. Chương trình vẫn giả định tổng toán học nằm trong giới hạn `long`.
- `compressValues` sắp trên **bản sao**, loại trùng và dùng tìm kiếm nhị phân. Giá trị nguyên dù âm hay rất lớn vẫn được nén mà không dùng giá trị trực tiếp làm chỉ số mảng.
- `summarizeIntegerRanges` chuyển cận phải đóng sang `long` **trước khi cộng 1**. Vì vậy một khoảng kết thúc tại `Integer.MAX_VALUE` không bị tràn `int` tại bước chuẩn hóa.
- Hai vị trí của mỗi khoảng được tìm trên **mảng mốc gốc đã sắp**, còn độ dài mỗi đoạn vẫn là `xs[i+1]-xs[i]`, không phải 1.
- `directedAdjacency` chỉ tạo cạnh từ `from` đến `to`. Nếu cần đồ thị vô hướng, phải thêm cạnh ngược; chương trình hiện tại giữ cạnh lặp và vòng tự khép nếu input có chúng.
- Mảng `a` không thay đổi trong các phép tính; chương trình in lại nó ở dòng cuối để minh họa hợp đồng.
- Chương trình dùng kiểu record `CoverageSummary`, có trong Java 17. Mã ví dụ không cần framework hoặc thư viện ngoài JDK.

### 10.2. Chi phí của từng phương thức

| Phương thức | Thời gian | Bộ nhớ phụ |
| --- | --- | --- |
| `prefixSums` | `O(n)` | `O(n)` |
| `rangeSum` sau prefix | `O(1)` | `O(1)` |
| `applyRangeAdds` với q cập nhật | `O(n+q)` | `O(n)` |
| `compressValues` | `O(n log(n+1))` | `O(n)` |
| `summarizeIntegerRanges` với q khoảng | `O(q log(q+1))` | `O(q)` |
| `directedAdjacency` với V đỉnh và E cạnh | `O(V+E)` | `O(V+E)` |

Các chặn giả định truy cập mảng/chỉ số và phép toán số nguyên có chi phí cơ bản hằng số, chưa tính chi phí hiển thị kết quả. Với đồ thị dùng đối tượng Java, overhead lưu các danh sách cũng cần cân nhắc khi hệ thống thật có tài nguyên hạn chế.

## 11. Phân biệt biến đổi tương đương và biến đổi mất thông tin

**Một phép biến đổi tốt không nhất thiết giữ mọi thông tin đầu vào.** Điều bắt buộc là giữ đúng phần thông tin bài toán cần.

| Biến đổi | Bảo toàn | Có thể mất/thay đổi |
| --- | --- | --- |
| `[L,R]` → `[L,R+1)` trên chỉ số nguyên | Cùng tập điểm nguyên | Cách biểu diễn biên, không áp dụng y hệt cho số thực |
| Tổng tiền tố | Khôi phục giá trị từng ô bằng hiệu hai prefix khi không tràn | Chi phí cập nhật tức thời không còn rẻ |
| Mảng hiệu | Tổng tác động của các cập nhật đoạn | Không trực tiếp có giá trị từng ô trước bước quét |
| Nén giá trị thành rank kèm `unique` | Thứ tự, so sánh bằng nhau, khả năng giải nén | Khoảng cách số học không nằm trong rank |
| Nén mốc để quét khoảng | Các điểm chuyển trạng thái và độ dài thật khi giữ `xs` | Nếu chỉ giữ rank sẽ mất độ dài thật |
| Hợp nhất các khoảng | Hợp của các đoạn | Số lần phủ và danh tính khoảng gốc |
| Edge list → adjacency list | Cấu trúc cạnh có hướng nếu chuyển đúng, kể cả số lần lặp | Thứ tự liệt kê toàn cục của các cạnh có thể thay đổi khi nhóm theo đỉnh |

Điều này dẫn đến một quy tắc thiết kế:

> Trước khi tiền xử lý, hãy viết rõ **đầu ra nào cần bảo toàn**. Nếu bước sau cần thông tin đã bị loại bỏ, phép biến đổi hiện tại chưa phù hợp.

Ví dụ: chỉ cần biết hai giá trị có bằng nhau và ai lớn hơn thì rank là đủ; nếu cần tính khoảng cách giữa chúng, phải giữ giá trị gốc. Nếu chỉ cần tổng độ dài hợp các khoảng, gộp khoảng có thể đủ; nếu muốn mức chồng lấp tối đa, gộp khoảng trước sẽ làm mất thông tin đếm chồng lấp.

## 12. Tiền xử lý offline và xử lý online

Một yếu tố ảnh hưởng trực tiếp đến lựa chọn biến đổi là **liệu ta đã biết toàn bộ dữ liệu/truy vấn trước hay chưa**.

### Offline

Ta biết toàn bộ cập nhật, khoảng hoặc giá trị có thể xuất hiện trước khi tính đáp án. Khi đó có thể:

- Thu thập mọi mốc rồi nén tọa độ.
- Sắp xếp toàn bộ sự kiện theo vị trí.
- Ghi mảng hiệu cho tất cả cập nhật, quét một lần để dựng kết quả.
- Chuyển edge list thành adjacency list trước khi chạy BFS.

Chi phí tiền xử lý có thể được phân bổ cho nhiều thao tác tiếp theo. Ví dụ tổng tiền tố giúp q truy vấn tổng trên mảng tĩnh thành `O(n+q)`.

### Online

Truy vấn xuất hiện liên tục và có thể cần trả ngay; dữ liệu mới chưa được biết trước. Khi ấy:

- Mảng hiệu chỉ ghi cập nhật rồi quét cuối **không giải quyết** được việc hỏi giá trị hiện tại sau mỗi cập nhật.
- Coordinate compression tĩnh có thể cần xây lại khi xuất hiện giá trị mới.
- Mảng tổng tiền tố có thể phải tính lại nếu thay đổi phần tử.
- Có thể cần Fenwick tree, segment tree, ordered map, cấu trúc động hoặc chiến lược cập nhật gia tăng phù hợp.

Đừng đánh giá một thuật toán offline là “nhanh hơn” trong trường hợp hệ thống buộc phải phục vụ truy vấn online. **Thời điểm cần đáp án** là một phần của đặc tả.

## 13. Lỗi thường gặp khi biến đổi khoảng/miền/cấu trúc

1. **Lẫn khoảng đóng và nửa mở.** Dùng công thức `R-L` trên `[L,R]` sẽ thiếu một phần tử.
2. **Lẫn 1-based và 0-based.** Đổi cả cận của truy vấn 1-based đóng bằng cách trừ 1 rồi dùng nửa mở làm lệch cận phải.
3. **Tràn số khi lấy `R+1`.** Ép kiểu sau phép cộng là quá muộn nếu phép cộng đã tràn `int`.
4. **Áp dụng `+1` cho khoảng liên tục trên số thực.** Công thức chuyển này chỉ giữ nguyên tập điểm trên miền số nguyên rời rạc.
5. **Dùng prefix cho dữ liệu đã thay đổi mà không cập nhật prefix.** Kết quả truy vấn trở nên cũ.
6. **Cập nhật mảng hiệu nhưng quên bước quét.** Mảng hiệu chứa các sự kiện, không phải giá trị cuối tại từng ô.
7. **Dùng mảng hiệu offline cho truy vấn online.** Chưa cộng dồn thì không có trạng thái đầy đủ ở mỗi chỉ số.
8. **Dùng trực tiếp khóa rất lớn làm chỉ số.** Có thể gây thiếu bộ nhớ hoặc chỉ số âm.
9. **Nén rank nhưng dùng hiệu rank tính độ dài.** Mất khoảng cách giữa các giá trị gốc.
10. **Không đưa đủ mọi biên vào danh sách tọa độ nén.** Không thể ánh xạ đúng một khoảng nếu một mốc đầu/cuối chưa được chuẩn bị.
11. **Sắp xếp dữ liệu nhưng không bảo toàn thông tin phụ.** Nếu bản ghi có `id`/trọng số, phải giữ chúng đi cùng khóa.
12. **Gộp các khoảng rồi vẫn định tính số lần phủ.** Gộp đã loại bỏ số lượng khoảng đang chồng.
13. **Xử lý sai sự kiện có cùng tọa độ.** Khoảng đóng và nửa mở khác nhau ở cách hiểu điểm biên.
14. **Chuyển đồ thị vô hướng như đồ thị có hướng.** Chỉ thêm một chiều làm mất một nửa quan hệ kề.
15. **Đổi nhãn đỉnh 1-based sang 0-based nhiều lần.** Tạo chỉ số sai, có thể âm.
16. **Cho rằng adjacency list luôn tốt hơn adjacency matrix.** Tùy mật độ đồ thị và loại truy vấn.
17. **Không tính chi phí tiền xử lý.** Nén giá trị `O(n log n)` có thể không đáng làm cho một truy vấn tuyến tính đơn giản.
18. **Không có hợp đồng lỗi đầu vào.** Khoảng đảo cận, tọa độ vượt miền hoặc cạnh đến đỉnh không tồn tại phải được xử lý có chủ ý.

## 14. Checklist thiết kế phép biến đổi

Trước khi viết code:

1. **Đầu ra thật sự cần gì?** Tổng đoạn, mức phủ, số lần phủ, danh sách láng giềng hay thứ hạng giá trị?
2. **Chỉ số và cận:** 0-based hay 1-based, đóng hay nửa mở, đoạn rỗng có hợp lệ không?
3. **Miền dữ liệu:** số nguyên hay số thực, có âm, giá trị cực trị, khóa trùng hay phần tử mới chưa biết?
4. **Biến đổi nào bảo toàn đúng thông tin cần dùng?** Có phải lưu ánh xạ ngược, giá trị gốc hoặc danh tính bản ghi?
5. **Thao tác tiếp theo là gì?** Nhiều truy vấn, nhiều cập nhật, truy vấn online, quét sự kiện hay BFS?
6. **Kiểu dữ liệu số:** `int` có đủ không; phép nhân, cộng cận phải, tổng độ dài và tổng chồng lấp có thể tràn không?
7. **Chi phí tiền xử lý:** thời gian và bộ nhớ ban đầu có được bù bởi các truy vấn sau không?
8. **Bất biến:** sau chuẩn hóa, nén, chuyển đổi, điều gì luôn đúng và đủ để chứng minh kết quả?
9. **Trường hợp biên:** đầu vào rỗng, tất cả trùng, nhiều khoảng cùng biên, chỉ một điểm, giá trị min/max, đồ thị không cạnh, đỉnh cô lập.
10. **Kiểm thử đối chiếu:** trên đầu vào nhỏ, có thể dùng thuật toán đơn giản hơn nhưng chắc chắn đúng để so sánh không?

## 15. Bài tập tự kiểm tra

**Bài 1 — Quy ước khoảng.** Với `a=[3,1,4,1,5]`, hãy đổi truy vấn vị trí **1-based đóng [2,4]** sang dạng 0-based nửa mở. Tính tổng đoạn bằng prefix.

**Bài 2 — Mảng hiệu.** Với `a=[3,1,4,1,5]`, thực hiện hai cập nhật đóng: cộng 2 cho `[1,3]` và trừ 1 cho `[0,0]`. Hãy ghi các sự kiện trong `diff` rồi tính mảng cuối.

**Bài 3 — Nén giá trị.** Với dãy `[1_000_000_000,-5,1_000_000_000,7]`, hãy tìm `unique` và mảng rank. Tại sao `rank(7)-rank(-5)` không thể thay cho khoảng cách số học giữa 7 và -5?

**Bài 4 — Nén mốc.** Với các khoảng nguyên đóng `[2,5],[4,8],[10,10]`, liệt kê mốc nửa mở sau khi chuẩn hóa, số điểm nguyên được phủ, tổng số lần phủ và mức phủ tối đa.

**Bài 5 — Miền cực trị.** Vì sao trong Java `(long)right+1L` an toàn hơn `(long)(right+1)` khi `right=Integer.MAX_VALUE`? Có thể mở rộng công thức tương tự khi `right=Long.MAX_VALUE` mà không dùng kiểu số lớn hơn không?

**Bài 6 — Cấu trúc đồ thị.** Đồ thị có hướng với bốn cạnh `0→1,0→2,2→3,1→3` và bốn đỉnh `0..3` có adjacency list nào? Nếu đề bài đổi sang đồ thị vô hướng, thao tác chuyển đổi phải thay gì?

**Bài 7 — Mất thông tin.** Nếu chỉ giữ rank đã nén mà bỏ `unique`, có thể phục hồi giá trị đầu vào hay không? Nếu gộp các khoảng thành hợp, còn biết số khoảng phủ tối đa hay không?

**Bài 8 — Online/offline.** Có q cập nhật cộng vào đoạn trên mảng dài n, và chỉ hỏi mảng cuối sau tất cả cập nhật. Nên chọn cách nào? Nếu cần hỏi tổng đoạn ngay sau mỗi cập nhật, lựa chọn đó còn bảo đảm trả nhanh không?

### Đáp án gợi ý

1. Chuyển sang `[1,4)`. Với `prefix=[0,3,4,8,9,14]`, tổng là `prefix[4]-prefix[1]=9-3=6`.
2. `diff=[-1,3,0,0,-2,0]`. Quét được thay đổi `[-1,2,2,2,0]` và kết quả `[2,3,6,3,5]`.
3. `unique=[-5,7,1_000_000_000]`; rank `[2,0,2,1]`. Rank chỉ bảo toàn thứ tự, không bảo toàn khoảng cách; `7-(-5)=12` nhưng hiệu rank là 1.
4. Các mốc `[2,4,6,9,10,11]`; số điểm nguyên có phủ là **8**; tổng số lần phủ **10**; phủ tối đa **2**.
5. Với phép cộng trong `int`, `right+1` tràn trước khi ép kiểu. Ép sang `long` trước thì cộng được. Nếu `right=Long.MAX_VALUE`, bản thân `long` không biểu diễn giá trị kế tiếp; cần cách định nghĩa/kiểu khác.
6. Danh sách kề có hướng `[[1,2],[3],[3],[]]`. Với đồ thị vô hướng phải thêm cạnh ngược cho mỗi cạnh theo quy ước lưu trữ.
7. Không; cần bảng ánh xạ ngược `unique` để khôi phục giá trị gốc. Gộp khoảng chỉ giữ hợp, thường không còn biết số lần chồng lấp.
8. Dùng **mảng hiệu** cho q cập nhật rồi quét một lần: `O(n+q)`. Nếu cần trả truy vấn sau mỗi cập nhật, cần cơ chế online, ví dụ Fenwick tree/segment tree tùy dạng cập nhật và truy vấn.

## Ghi nhớ

**Biến đổi khoảng** giúp thống nhất cách hiểu chỉ số và sử dụng prefix/difference arrays đúng biên. **Biến đổi miền giá trị** giúp đưa dữ liệu thưa về chỉ số nhỏ bằng nén tọa độ nhưng phải giữ tọa độ gốc khi cần tính độ dài. **Biến đổi cấu trúc đầu vào** như edge list sang adjacency list giúp các thao tác tiếp theo phù hợp với cách truy cập. Một tiền xử lý đáng giá khi nó **bảo toàn đủ thông tin cho đầu ra**, có bất biến đúng, xử lý ranh giới an toàn, và tiết kiệm chi phí trên toàn bộ chuỗi thao tác/truy vấn, chứ không chỉ làm dữ liệu trông gọn hơn.
