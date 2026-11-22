# Liệt kê tập con, tổ hợp và hoán vị

## Mục tiêu học tập

**Quay lui (backtracking)** là cách khám phá có hệ thống một không gian lựa chọn: ta **chọn một phương án**, đi sâu vào trạng thái mới, rồi **hoàn tác lựa chọn** để thử phương án tiếp theo. Ba bài toán kinh điển dùng cùng khuôn mẫu này là **liệt kê tập con**, **liệt kê tổ hợp chập k** và **liệt kê hoán vị**. Chúng khác nhau ở việc **có giữ thứ tự hay không**, **có bắt buộc chọn đúng k phần tử không**, **có được chọn lại vị trí không**, và **cách hiểu phần tử trùng**.

Sau bài này, bạn có thể:

1. Phân biệt chính xác **subset**, **combination**, **permutation** và **subsequence**.
2. Phát biểu cấu trúc cây tìm kiếm, trạng thái đang xây và bước **choose → explore → undo**.
3. Cài đặt ba thuật toán trên bằng **Java 17+**, vừa liệt kê theo vị trí vừa **khử trùng theo giá trị**.
4. Chứng minh không thiếu, không lặp (theo hợp đồng được chọn) và mọi kết quả đều hợp lệ.
5. Giải thích tại sao số kết quả là `2^n`, `\binom{n}{k}` và `n!`; phân tích thời gian **theo kích thước đầu ra**, không chỉ số lần gọi đệ quy.
6. Sử dụng **pruning** hợp lệ cho bài tổ hợp, dừng sớm khi chỉ cần một vài nghiệm, và tránh giữ mọi kết quả trong RAM.
7. Xử lý `n=0`, `k=0`, `k=n`, `k>n`, dữ liệu trùng, input không sắp, và giới hạn stack/bộ nhớ.
8. Nhận diện khi nào dùng quay lui, bitmask, thuật toán sinh kế tiếp hoặc công thức đếm mà **không cần liệt kê**.

---

## 1. Ba khái niệm khác nhau ở đâu?

Giả sử có ba phần tử **phân biệt**:

```text
a = [1, 2, 3]
n = 3
```

### 1.1. Tập con (subset)

Một tập con chọn **bất kỳ số phần tử nào từ 0 đến n**. Mỗi vị trí đầu vào được chọn hoặc không được chọn; **thứ tự chọn không có ý nghĩa**.

Tám tập con của `{1,2,3}`:

```text
[]
[1]
[1,2]
[1,2,3]
[1,3]
[2]
[2,3]
[3]
```

Danh sách trên viết một tập con bằng các giá trị theo thứ tự tăng cho dễ đọc. Các tập `{1,2}` và `{2,1}` là **cùng một tập con**, không phải hai kết quả.

Có `2^n` tập con vì mỗi trong n phần tử có hai lựa chọn độc lập: chọn hoặc không chọn.

### 1.2. Tổ hợp chập k (k-combination)

Tổ hợp chọn **đúng k phần tử**, không phân biệt thứ tự. Với `n=3` và `k=2`:

```text
[1,2]
[1,3]
[2,3]
```

Số tổ hợp:

\[
\binom nk=\frac{n!}{k!(n-k)!}
\quad\text{khi }0\le k\le n.
\]

Mỗi tổ hợp là một tập con có đúng k phần tử. Nói cách khác, liệt kê tổ hợp chập k là liệt kê **một lớp kích thước cố định** trong toàn bộ tập con.

### 1.3. Hoán vị (permutation)

Hoán vị dùng **tất cả n phần tử**, nhưng **thứ tự có ý nghĩa**. Với `[1,2,3]`:

```text
[1,2,3]
[1,3,2]
[2,1,3]
[2,3,1]
[3,1,2]
[3,2,1]
```

Có `n!` hoán vị nếu n **vị trí/phần tử là phân biệt**.

### 1.4. Bảng nhận diện nhanh

| Đặc điểm | Tập con | Tổ hợp chập k | Hoán vị đầy đủ |
| --- | --- | --- | --- |
| Số phần tử được chọn | `0..n` | **Đúng k** | **Đúng n** |
| Thứ tự có làm khác kết quả? | Không | Không | **Có** |
| Có được dùng một vị trí nhiều lần? | Không | Không | Không |
| Số kết quả khi n phần tử phân biệt | `2^n` | `\binom nk` | `n!` |
| Trạng thái thường dùng | Vị trí bắt đầu + đường chọn | Vị trí bắt đầu + số phần tử đã chọn | Mảng đánh dấu `used[]` hoặc đổi chỗ |
| Khi ghi kết quả | Mọi nút hợp lệ, hoặc lá cây quyết định | Khi đường chọn dài k | Khi đường chọn dài n |

**Không được tự động đồng nhất** hoán vị với tổ hợp. Ví dụ `[1,2]` và `[2,1]` là **một tổ hợp chập 2** nhưng **hai hoán vị** của hai phần tử.

---

## 2. Subsequence và tập con: gần nhưng không hoàn toàn giống

Nếu đầu vào là **mảng có thứ tự**, một *subsequence* là dãy nhận được bằng cách chọn các **chỉ số tăng dần**:

\[
0\le i_1<i_2<\cdots<i_t<n.
\]

Ví dụ với `[3,1,2]`, các dãy con theo chỉ số gồm `[]`, `[3]`, `[1]`, `[2]`, `[3,1]`, `[3,2]`, `[1,2]`, `[3,1,2]`.

Về số lựa chọn chỉ số, vẫn có `2^n` kết quả. Tuy nhiên:

- **Tập con** trong nghĩa toán học **không có thứ tự**.
- **Subsequence** giữ **thứ tự tương đối của những phần tử được chọn**.
- Với dữ liệu có **phần tử trùng**, nhiều lựa chọn chỉ số khác nhau có thể cho **cùng dãy giá trị**.

Ví dụ:

```text
a = [1, 1, 2]
Chọn chỉ số [0] -> [1]
Chọn chỉ số [1] -> [1]
```

Đây là **hai cách chọn vị trí khác nhau**, nhưng có **cùng kết quả giá trị** `[1]`.

Điều đó tạo ra **hai hợp đồng đầu ra** cần phân biệt:

1. **Liệt kê theo chỉ số/phần tử gắn danh tính:** mỗi vị trí là riêng biệt, dù giá trị trùng. Có đúng `2^n` tập con vị trí.
2. **Liệt kê các tập con giá trị khác nhau:** mỗi đa tập giá trị chỉ xuất hiện một lần. Phải khử trùng đúng cách.

Trong bài này, các hàm không có chữ `Unique` mặc định **phân biệt vị trí**; các hàm có chữ `Unique` chỉ xuất ra **danh sách giá trị khác nhau**.

---

## 3. Khung tư duy chung của quay lui

Hình dung ta xây một lời giải từng bước. Mỗi nút của cây tìm kiếm là một **trạng thái**; mỗi cạnh là một **quyết định**; lá (hoặc một số nút bên trong) có thể là kết quả cần xuất.

Khuôn mẫu:

```text
BACKTRACK(state):
    if state đã thỏa điều kiện xuất kết quả:
        emit(copy(state.path))
        if không cần mở rộng nữa:
            return

    for choice trong các lựa chọn hợp lệ:
        APPLY(choice)          // choose
        BACKTRACK(newState)    // explore
        UNDO(choice)           // undo
```

Ba bước cốt lõi:

- **Choose:** thêm một phần tử vào đường chọn, hoặc đánh dấu một vị trí là đã dùng.
- **Explore:** gọi đệ quy để tiếp tục xây kết quả dài hơn.
- **Undo:** hoàn tác mọi thay đổi đã thực hiện trong bước choose.

Nếu quên hoàn tác, khi quay về từ một nhánh, các nhánh kế tiếp **kế thừa sai trạng thái**.

### 3.1. Ví dụ về bất biến đường chọn

Giả sử `path` là danh sách các phần tử đã chọn.

Trước lời gọi đệ quy, `path` phản ánh các quyết định từ gốc đến nút hiện tại. Sau `path.add(x)`, nó phản ánh quyết định thêm x. Sau khi lời gọi đệ quy xong, `path.remove(path.size()-1)` đưa `path` về **đúng trạng thái trước khi chọn x**.

Đây là **bất biến hoàn tác**. Nó giúp dùng **một danh sách đang thay đổi** thay vì tạo bản sao trên mỗi cạnh của cây tìm kiếm.

### 3.2. Khi nào phải sao chép?

Nếu muốn lưu lại một lời giải:

```java
result.add(new ArrayList<>(path));
```

Không nên viết:

```java
result.add(path); // Sai nếu path còn bị sửa sau đó.
```

Bởi vì khi đó nhiều phần tử của `result` có thể cùng **trỏ tới một đối tượng List**. Sau các lần `remove` và `add`, những “kết quả đã lưu” sẽ đổi theo.

**Quy tắc:** sao chép `path` **khi ghi kết quả**, không nhất thiết sao chép ở mọi lời gọi đệ quy. Nếu chỉ phát kết quả qua callback, cũng cần tạo snapshot hoặc quy định rõ rằng callback chỉ được xem tức thời và không giữ tham chiếu tới đường chọn đang thay đổi.

### 3.3. Chọn trạng thái tối thiểu đủ

Đừng mang toàn bộ thông tin của lịch sử vào trạng thái nếu các bước tiếp theo chỉ cần:

- `start`: chỉ số nhỏ nhất được phép chọn tiếp — thường dùng cho **tập con/tổ hợp**.
- `path`: lời giải đang hình thành.
- `used[]`: các vị trí đã được sử dụng — thường dùng cho **hoán vị**.
- `remaining` hoặc `k-path.size()`: số phần tử còn cần chọn.
- Một giá trị tích lũy, nếu đề có ràng buộc tổng/chi phí.

Trạng thái ngắn giúp giảm lỗi và làm việc chứng minh bất biến rõ ràng hơn.

---

## 4. Liệt kê tập con bằng DFS với chỉ số bắt đầu

Một cách rất tiện là **xuất path ở mỗi nút** rồi thử thêm từng phần tử ở các chỉ số lớn hơn chỉ số cuối đã chọn.

```text
SUBSETS(a):
    path = []
    DFS(start=0)

DFS(start):
    output(copy(path))

    for i từ start đến n-1:
        path.add(a[i])
        DFS(i+1)
        path.removeLast()
```

Bất biến:

- Các **chỉ số đã chọn trong path tăng nghiêm ngặt**.
- Nếu lời gọi hiện tại có tham số start, mọi phần tử có thể chọn tiếp có chỉ số `>=start`.
- Mỗi vị trí input chỉ được chọn tối đa một lần.

Vì chỉ số chọn sau luôn lớn hơn chỉ số chọn trước, ta **không tạo cả `[1,2]` và `[2,1]`** như hai tập con khi input `[1,2,3]`. Mỗi tập con vị trí có **duy nhất một biểu diễn bằng dãy chỉ số tăng dần**.

### 4.1. Vết DFS trên [1,2,3]

Các lần xuất kết quả theo thứ tự duyệt `for` tăng:

```text
[]                 // nút gốc
[1]                // chọn i=0
[1,2]              // tiếp tục chọn i=1
[1,2,3]            // tiếp tục chọn i=2
[1,3]              // hoàn tác 2, chọn 3
[2]                // hoàn tác về gốc, chọn 2
[2,3]              // nối thêm 3
[3]                // về gốc, chọn 3
```

Đây là **thứ tự DFS theo chỉ số input**, không nhất thiết là **thứ tự theo độ dài**, và cũng không phải quy tắc chuẩn duy nhất để in tất cả tập con.

### 4.2. Chứng minh không thiếu/không thừa

Lấy một tập con chỉ số bất kỳ:

\[
S=\{i_1<i_2<\cdots<i_t\}.
\]

Thuật toán có đúng một đường đi chọn lần lượt `i_1,i_2,\ldots,i_t`, vì sau khi chọn `i_j`, lời gọi mới bắt đầu ở `i_j+1`. Khi đến nút ấy, thuật toán xuất `path`, nên **không thiếu** tập con nào.

Hai đường đi khác nhau phải khác ít nhất một chỉ số được chọn; vì dãy chỉ số ở mỗi đường đều tăng nghiêm ngặt, chúng biểu diễn hai tập con vị trí khác nhau. Vì vậy **không in trùng** theo chỉ số.

Với dữ liệu có các **giá trị bằng nhau**, hai tập con vị trí vẫn có thể in ra **cùng dãy giá trị**. Đó không phải lỗi nếu hợp đồng là phân biệt vị trí; muốn đầu ra duy nhất theo giá trị cần xử lý ở mục 8.

### 4.3. Một cách khác: chọn/không chọn từng vị trí

Có thể dùng cây nhị phân:

```text
DFS(i):
    if i == n:
        output(copy(path))
        return

    // Nhánh không chọn a[i]
    DFS(i+1)

    // Nhánh chọn a[i]
    path.add(a[i])
    DFS(i+1)
    path.removeLast()
```

Cách này tạo đúng `2^n` **lá**. Nó phù hợp với các bài mà mỗi vị trí là một quyết định nhị phân hoặc cần xử lý ràng buộc riêng.

**Khác biệt:** cách `for/start` xuất ở **mọi nút**, còn cây chọn/không chọn xuất ở **độ sâu n**. Hai cách liệt kê cùng các tập con vị trí, nhưng thứ tự và cấu trúc cây khác nhau.

---

## 5. Liệt kê tổ hợp chập k

Bài toán: chọn **đúng k chỉ số tăng dần** từ n vị trí.

Giữ trạng thái tương tự tập con nhưng chỉ ghi kết quả khi:

\[
path.size()=k.
\]

### 5.1. Giả mã cơ bản

```text
COMBINATIONS(a, k):
    yêu cầu: 0 <= k <= n
    path = []
    DFS(start=0)

DFS(start):
    if path.size() == k:
        output(copy(path))
        return

    for i từ start đến n-1:
        path.add(a[i])
        DFS(i+1)
        path.removeLast()
```

Với `[1,2,3]`, `k=2`:

```text
[1,2]
[1,3]
[2,3]
```

Đường chọn chỉ có `k` phần tử và các chỉ số tăng nghiêm ngặt, nên mỗi tổ hợp vị trí xuất đúng một lần.

### 5.2. Cắt nhánh bằng số vị trí còn lại

Cách cơ bản vẫn có thể đi vào một nhánh mà **không còn đủ phần tử để chọn tới k**.

Giả sử:

- `n` là số phần tử.
- `path.size()=p`.
- Cần thêm `need=k-p` phần tử.
- Đang thử chọn chỉ số `i`.

Sau khi chọn `i`, còn `n-i-1` vị trí ở sau nó. Để hoàn tất tổ hợp, cần:

\[
n-i\ge need.
\]

Suy ra:

\[
\boxed{i\le n-need}.
\]

Vòng lặp có thể rút gọn thành:

```text
need = k - path.size()
for i từ start đến n-need:
    choose a[i]
    DFS(i+1)
    undo
```

Đây là **pruning an toàn**, vì mọi i lớn hơn `n-need` chắc chắn không còn đủ vị trí để tạo một tổ hợp dài k. Ta chỉ bỏ nhánh **không thể đạt mục tiêu**, không bỏ nghiệm hợp lệ.

### 5.3. Ví dụ pruning

Với `n=5`, `k=3`, ban đầu `need=3`, nên chỉ cần thử chỉ số đầu tiên:

```text
i <= 5-3 = 2
```

Tức chỉ thử i=0,1,2. Nếu bắt đầu bằng i=3 hoặc i=4, phía sau không đủ thêm hai phần tử để có tổ hợp 3 phần tử, nên không cần gọi DFS.

Sau khi chọn i=1, `path.size()=1`, `need=2` và `start=2`. Khi ấy chỉ thử `i≤5-2=3`. Các nhánh tiếp theo tiếp tục được cắt theo số chỗ còn lại.

### 5.4. Các giá trị k đặc biệt

- `k=0`: có **một** tổ hợp rỗng `[]`.
- `k=n`: có đúng **một** tổ hợp gồm toàn bộ n vị trí.
- `k>n`: không tồn tại tổ hợp; API có thể trả kết quả rỗng hoặc từ chối input. Chương trình Java của bài **ném ngoại lệ** khi k không trong `[0,n]` để chỉ rõ hợp đồng.
- `k<0`: không hợp lệ.
- `n=0,k=0`: có đúng một kết quả rỗng.

Không được gộp hai trường hợp “**không có kết quả**” và “**có một kết quả rỗng**” thành cùng một giá trị. `[]` (danh sách kết quả rỗng) và `[[]]` (danh sách chứa một kết quả rỗng) là **hai cấu trúc khác nhau**.

---

## 6. Liệt kê hoán vị bằng mảng used[]

Hoán vị yêu cầu **chọn đủ n vị trí** và mỗi vị trí chỉ dùng một lần. Nhưng **không buộc chỉ số tăng dần**: bất kỳ vị trí chưa dùng nào cũng có thể được chọn tiếp.

Trạng thái:

- `path`: thứ tự các giá trị đã chọn.
- `used[i]`: đã chọn vị trí i hay chưa.

Giả mã:

```text
PERMUTATIONS(a):
    used[0..n-1] = false
    path = []
    DFS()

DFS():
    if path.size() == n:
        output(copy(path))
        return

    for i từ 0 đến n-1:
        if used[i]:
            continue

        used[i] = true
        path.add(a[i])

        DFS()

        path.removeLast()
        used[i] = false
```

### 6.1. Bất biến

Trong mỗi lời gọi `DFS`:

1. `used[i]==true` **khi và chỉ khi** vị trí i đã có trong đường chọn.
2. Mỗi vị trí xuất hiện **tối đa một lần** trong path.
3. `path.size()` đúng bằng số vị trí được đánh dấu `true`.
4. Sau khi hoàn tác nhánh i, cả `path` và `used[i]` trở lại trạng thái trước khi chọn.

Khi `path.size()==n`, đường chọn dùng **đủ n vị trí, mỗi vị trí đúng một lần**, nên đó là một hoán vị hợp lệ.

Mọi hoán vị vị trí `(i_1,i_2,\ldots,i_n)` tương ứng với duy nhất một đường đi của DFS lựa chọn các i theo đúng thứ tự đó. Vì vậy không thiếu và không trùng **hoán vị vị trí**.

### 6.2. Vết [1,2,3]

Nếu vòng `i` đi từ 0 đến n−1:

```text
[1,2,3]
[1,3,2]
[2,1,3]
[2,3,1]
[3,1,2]
[3,2,1]
```

**Khác với tập con/tổ hợp:** tại mọi độ sâu ta thử **tất cả vị trí chưa dùng**, không chỉ các vị trí sau `start`. Nếu dùng `start=i+1` trong hoán vị, ta sẽ không tạo được các thứ tự như `[3,1,2]`.

### 6.3. Hoán vị bằng swap tại chỗ

Một biến thể khác là hoán đổi phần tử:

```text
PERMUTE_SWAP(a, depth):
    if depth == n:
        output(copy(a))
        return

    for i từ depth đến n-1:
        swap(a[depth], a[i])
        PERMUTE_SWAP(a, depth+1)
        swap(a[depth], a[i])   // hoàn tác
```

Cách swap không cần `used[]` riêng và dùng bộ nhớ stack `O(n)`, nhưng **thay đổi mảng input trong khi chạy**, nên phải hoàn tác đúng và lưu snapshot khi xuất kết quả. Với phần tử trùng, swap đơn giản cũng sinh nhiều dãy giá trị trùng.

Nếu cần **giữ nguyên input trong mọi thời điểm** (không chỉ khôi phục sau hàm), dùng `used[]` với `path` hoặc sao chép trước khi dùng swap.

---

## 7. Tại sao quay lui là bài toán sinh kết quả, không chỉ tìm kiếm?

Một số bài quay lui như Sudoku, N-Queens hoặc tìm một đường đi có thể **dừng ngay khi gặp một nghiệm**. Nhưng khi người dùng yêu cầu **liệt kê tất cả**, ta không thể dừng khi gặp nghiệm đầu tiên.

Số kết quả có thể rất lớn:

| n | `2^n` tập con | `n!` hoán vị |
| ---: | ---: | ---: |
| 5 | 32 | 120 |
| 10 | 1.024 | 3.628.800 |
| 15 | 32.768 | 1.307.674.368.000 |
| 20 | 1.048.576 | 2.432.902.008.176.640.000 |
| 25 | 33.554.432 | Lớn hơn `10^{25}` |

**Đây là giới hạn kích thước đầu ra**, không chỉ do thuật toán cài đặt chưa tối ưu. Nếu bài yêu cầu in mọi hoán vị của 20 phần tử phân biệt, bản thân lượng đầu ra đã quá lớn cho nhiều ứng dụng.

### 7.1. Đếm kết quả không cần liệt kê

Nếu chỉ hỏi:

- Có bao nhiêu tập con? → `2^n`.
- Có bao nhiêu tổ hợp chập k? → `\binom nk`.
- Có bao nhiêu hoán vị n phần tử phân biệt? → `n!`.

Thường nên dùng **công thức đếm**, không chạy DFS để đếm từng kết quả. Với n lớn, giá trị vượt `int` hoặc `long`, nên cân nhắc `BigInteger` trong Java.

Đừng gọi một thuật toán liệt kê `n!` hoán vị rồi chỉ trả `size()` nếu yêu cầu duy nhất là **số lượng**.

### 7.2. Phân tích theo số phần tử thực sự xuất

Khi sinh một lời giải dài k và muốn **in hoặc sao chép toàn bộ k giá trị**, riêng thao tác xuất đã tốn ít nhất `\Omega(k)` thời gian cho nghiệm ấy.

Vì vậy phân tích độ phức tạp phải xét **số kết quả và chiều dài kết quả**, không chỉ chi phí một nút DFS.

---

## 8. Dữ liệu có phần tử trùng: phân biệt vị trí và giá trị

Xét:

```text
a = [1, 1, 2]
```

Ba vị trí input vẫn phân biệt:

```text
chỉ số: 0  1  2
giá trị: 1  1  2
```

Nếu liệt kê **tập con vị trí** thì có `2³=8` kết quả. Nhưng chỉ có **6 tập con giá trị khác nhau**, vì hai vị trí mang giá trị 1 có thể tạo cùng dãy kết quả.

Tương tự:

- Tổ hợp **hai vị trí** có `\binom32=3` lựa chọn vị trí, nhưng chỉ có **2 tổ hợp giá trị khác nhau**: `[1,1]` và `[1,2]`.
- Hoán vị **ba vị trí** có `3!=6` thứ tự vị trí, nhưng chỉ có **3 dãy giá trị khác nhau**: `[1,1,2]`, `[1,2,1]`, `[2,1,1]`.

**Đầu vào có giá trị trùng chưa đủ để tự quyết định khử trùng.** Nếu các phần tử là nhân viên khác id nhưng cùng điểm, có thể cần giữ từng id; nếu là dãy giá trị và yêu cầu mỗi kết quả giá trị xuất một lần, mới dùng cơ chế khử trùng.

### 8.1. Khử trùng tập con bằng cách sort và skip cùng độ sâu

Để chỉ xuất các tập con giá trị phân biệt:

1. **Sao chép input** nếu không được thay đổi dữ liệu nguồn.
2. Sắp xếp bản sao tăng dần.
3. Trong vòng lặp ở một lời gọi `DFS(start)`, bỏ phần tử thứ i nếu:

```java
if (i > start && a[i] == a[i - 1]) {
    continue;
}
```

**Ý nghĩa điều kiện `i>start`:** tại **cùng một độ sâu/lời gọi**, nếu hai giá trị cạnh nhau bằng nhau, chỉ thử người đại diện đầu tiên. Nhưng khi đã chọn một số 1 và đệ quy sang `start=i+1`, ta vẫn **được phép chọn số 1 tiếp theo** để sinh `[1,1]`.

Nếu chỉ kiểm tra `i>0 && a[i]==a[i-1]` **không xét start**, ta sẽ loại luôn cách chọn hai số 1, làm **thiếu** tập con `[1,1]`.

Kết quả unique subsets theo thứ tự DFS của bản sort `[1,1,2]`:

```text
[]
[1]
[1,1]
[1,1,2]
[1,2]
[2]
```

### 8.2. Khử trùng tổ hợp chập k

Dùng **cùng điều kiện skip ở một lời gọi DFS**:

```java
if (i > start && a[i] == a[i - 1]) {
    continue;
}
```

Nhưng chỉ xuất khi `path.size()==k`. Với `[1,1,2]`, `k=2`:

```text
[1,1]
[1,2]
```

Điều kiện này không loại `[1,1]`, vì hai số 1 được chọn ở **hai độ sâu khác nhau**. Nó chỉ ngăn chọn “số 1 thứ hai” làm nhánh bắt đầu thay cho “số 1 thứ nhất” tại cùng độ sâu, khi cả hai sẽ tạo cùng một tổ hợp giá trị.

### 8.3. Khử trùng hoán vị: khác với tập con/tổ hợp

Trong hoán vị, mỗi vị trí có thể được chọn ở bất kỳ độ sâu nào **miễn chưa dùng**. Quy tắc skip khác:

```java
if (i > 0 && a[i] == a[i - 1] && !used[i - 1]) {
    continue;
}
```

Sau khi **sắp input**, quy tắc này có ý nghĩa:

> Nếu đang định chọn một phần tử có giá trị bằng phần tử ngay trước nó trong bản sắp, hãy buộc **bản sao đứng trước phải được chọn trước**, trước khi cho phép chọn bản sao hiện tại.

Với `a=[1,1,2]`:

- Ở gốc, chưa dùng vị trí 0 nên không được mở đầu bằng **vị trí 1** cũng mang giá trị 1: nhánh này sẽ trùng với nhánh mở đầu bằng vị trí 0.
- Sau khi đã dùng vị trí 0 ở một độ sâu trước, vị trí 1 được dùng ở độ sâu tiếp theo, nên `[1,1,2]` **vẫn hợp lệ**.
- Chọn `2` trước cũng hợp lệ; khi tới các số 1, quy tắc ưu tiên bản sao đứng trước vẫn loại các hoán vị giá trị trùng.

Ba hoán vị giá trị duy nhất:

```text
[1,1,2]
[1,2,1]
[2,1,1]
```

**Vì sao không dùng `i>start` ở đây?** Hoán vị không có tham số `start` theo nghĩa chỉ được chọn các chỉ số tăng, vì cách đó sẽ làm mất mọi thứ tự đảo. Thay vào đó, `used[]` giúp xác định phần tử nào đã nằm trong tiền tố của hoán vị.

### 8.4. Mô hình toán học của phần tử trùng

Giả sử có r giá trị phân biệt, mỗi giá trị có số lần xuất hiện `f_1,\ldots,f_r`, tổng `n=\sum f_i`.

- Số **tập con giá trị khác nhau**:

\[
\prod_{j=1}^r(f_j+1).
\]

Với mỗi giá trị j, chọn 0 tới `f_j` lần xuất hiện của giá trị ấy.

- Số **hoán vị giá trị khác nhau**:

\[
\frac{n!}{\prod_{j=1}^r f_j!}.
\]

- Số **tổ hợp giá trị khác nhau có đúng k phần tử** là hệ số của `x^k` trong:

\[
\prod_{j=1}^r(1+x+x^2+\cdots+x^{f_j}).
\]

Ví dụ `[1,1,2]` có `f_1=2,f_2=1`:

\[
\text{Unique subsets}=(2+1)(1+1)=6,
\]

\[
\text{Unique permutations}=\frac{3!}{2!1!}=3.
\]

Hệ số `x^2` trong `(1+x+x²)(1+x)` bằng 2, khớp hai tổ hợp giá trị `[1,1]` và `[1,2]`.

**Nhớ:** các công thức này đếm kết quả **phân biệt theo giá trị**, khác công thức theo **chỉ số** `2^n`, `\binom nk` và `n!`.

---

## 9. Một ví dụ cây tìm kiếm và quá trình hoàn tác

Xét tổ hợp `k=2` của `[1,2,3]`.

```text
                         []
                 /        |         \
             chọn 1     chọn 2     chọn 3
               [1]       [2]        [3]
              /   \        \
           [1,2] [1,3]   [2,3]
            xuất   xuất    xuất
```

Ở nhánh `[1]`:

1. Chọn `2` → `path=[1,2]`.
2. Path đủ k=2 → **sao chép** và xuất `[1,2]`.
3. Quay lại → **bỏ phần tử 2**, còn `path=[1]`.
4. Chọn `3` → `path=[1,3]` → xuất.
5. Quay lại → bỏ 3, còn `[1]`.
6. Về gốc → bỏ 1, `path=[]`.
7. Chọn `2` → tiếp tục các nhánh xuất `[2,3]`.

Nếu bước 3 quên bỏ 2, trước khi chọn 3 đường chọn sẽ thành `[1,2,3]` và chương trình sẽ sai. Nếu quên hoàn tác khi về gốc, các nhánh sau có thể chứa phần tử thuộc nhánh trước.

### 9.1. Bất biến chung

Sau mỗi lần lời gọi DFS con trả về, **trạng thái của lời gọi cha phải giống hệt trước lúc thêm quyết định tạo nhánh ấy**.

Với subset và combination, chỉ cần bỏ phần tử vừa `add`. Với permutation, phải vừa bỏ phần tử khỏi `path`, vừa đặt `used[i]=false`. Với swap-based permutation, phải swap ngược hai vị trí ban đầu.

### 9.2. Tại sao không thể hoàn tác tùy ý?

Giả sử chọn phần tử i làm tăng một biến `sum`:

```text
sum += a[i]
path.add(a[i])
DFS(...)
path.removeLast()
sum -= a[i]
```

Nếu chỉ bỏ path mà không khôi phục sum, những nhánh sau sẽ bị tính sai tổng. **Mọi thay đổi của trạng thái phải được hoàn tác**, không chỉ thay đổi danh sách các phần tử được chọn.

---

## 10. Java 17+ — Sáu hàm liệt kê chạy độc lập

Chương trình đầy đủ **`EnumerateBacktrackingDemo.java`** dưới đây có sáu API:

1. `subsets` — tất cả tập con **theo chỉ số**, không khử kết quả giá trị trùng.
2. `combinations` — tổ hợp **k chỉ số**, giữ thứ tự input trong mỗi kết quả.
3. `permutations` — hoán vị **theo vị trí**, mỗi vị trí dùng đúng một lần.
4. `uniqueSubsets` — các tập con **không trùng theo giá trị**.
5. `uniqueCombinations` — các tổ hợp chập k **không trùng theo giá trị**.
6. `uniquePermutations` — các hoán vị **không trùng theo giá trị**.

Các hàm unique sắp **bản sao input**, không sửa mảng gốc. Các API liệt kê lưu tất cả nghiệm trong RAM, phù hợp **ví dụ nhỏ**; với n lớn, cần thiết kế cơ chế xuất trực tuyến ở mục 13.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

public class EnumerateBacktrackingDemo {

    // All index subsets. Duplicated values may be printed.
    public static List<List<Integer>> subsets(int[] input) {
        Objects.requireNonNull(input, "input");

        List<List<Integer>> result = new ArrayList<>();
        dfsSubsets(input, 0, new ArrayList<>(), result, false);
        return result;
    }

    // Unique value subsets. Input remains unchanged.
    public static List<List<Integer>> uniqueSubsets(int[] input) {
        Objects.requireNonNull(input, "input");

        int[] sorted = input.clone();
        Arrays.sort(sorted);

        List<List<Integer>> result = new ArrayList<>();
        dfsSubsets(sorted, 0, new ArrayList<>(), result, true);
        return result;
    }

    private static void dfsSubsets(
            int[] a,
            int start,
            List<Integer> path,
            List<List<Integer>> result,
            boolean unique) {

        result.add(new ArrayList<>(path));

        for (int i = start; i < a.length; i++) {
            if (unique && i > start && a[i] == a[i - 1]) {
                continue;
            }

            path.add(a[i]);
            dfsSubsets(a, i + 1, path, result, unique);
            path.remove(path.size() - 1);
        }
    }

    // Choose exactly k indices, without regarding their order.
    public static List<List<Integer>> combinations(
            int[] input, int k) {

        Objects.requireNonNull(input, "input");
        checkK(k, input.length);

        List<List<Integer>> result = new ArrayList<>();
        dfsCombinations(
                input, 0, k, new ArrayList<>(), result, false);
        return result;
    }

    // Choose exactly k values, with duplicate value results removed.
    public static List<List<Integer>> uniqueCombinations(
            int[] input, int k) {

        Objects.requireNonNull(input, "input");
        checkK(k, input.length);

        int[] sorted = input.clone();
        Arrays.sort(sorted);

        List<List<Integer>> result = new ArrayList<>();
        dfsCombinations(
                sorted, 0, k, new ArrayList<>(), result, true);
        return result;
    }

    private static void checkK(int k, int n) {
        if (k < 0 || k > n) {
            throw new IllegalArgumentException(
                    "k must be in [0, input.length]");
        }
    }

    private static void dfsCombinations(
            int[] a,
            int start,
            int k,
            List<Integer> path,
            List<List<Integer>> result,
            boolean unique) {

        if (path.size() == k) {
            result.add(new ArrayList<>(path));
            return;
        }

        int need = k - path.size();

        // If i > n - need, not enough positions remain.
        for (int i = start; i <= a.length - need; i++) {
            if (unique && i > start && a[i] == a[i - 1]) {
                continue;
            }

            path.add(a[i]);
            dfsCombinations(
                    a, i + 1, k, path, result, unique);
            path.remove(path.size() - 1);
        }
    }

    // All position permutations, including duplicate value lists
    // if the input contains equal values.
    public static List<List<Integer>> permutations(int[] input) {
        Objects.requireNonNull(input, "input");

        List<List<Integer>> result = new ArrayList<>();
        boolean[] used = new boolean[input.length];

        dfsPermutations(
                input, used, new ArrayList<>(), result, false);
        return result;
    }

    // Unique value permutations, using sorted order and used[].
    public static List<List<Integer>> uniquePermutations(
            int[] input) {

        Objects.requireNonNull(input, "input");

        int[] sorted = input.clone();
        Arrays.sort(sorted);

        List<List<Integer>> result = new ArrayList<>();
        boolean[] used = new boolean[sorted.length];

        dfsPermutations(
                sorted, used, new ArrayList<>(), result, true);
        return result;
    }

    private static void dfsPermutations(
            int[] a,
            boolean[] used,
            List<Integer> path,
            List<List<Integer>> result,
            boolean unique) {

        if (path.size() == a.length) {
            result.add(new ArrayList<>(path));
            return;
        }

        for (int i = 0; i < a.length; i++) {
            if (used[i]) {
                continue;
            }

            // Of equal values, choose earlier unused copy first.
            if (unique && i > 0
                    && a[i] == a[i - 1]
                    && !used[i - 1]) {
                continue;
            }

            used[i] = true;
            path.add(a[i]);

            dfsPermutations(a, used, path, result, unique);

            path.remove(path.size() - 1);
            used[i] = false;
        }
    }

    public static void main(String[] args) {
        int[] different = {1, 2, 3};
        int[] duplicate = {1, 1, 2};

        System.out.println(
                "Subsets: " + subsets(different));
        System.out.println(
                "Combinations k=2: "
                        + combinations(different, 2));
        System.out.println(
                "Permutations: " + permutations(different));

        System.out.println(
                "Unique subsets: " + uniqueSubsets(duplicate));
        System.out.println(
                "Unique combinations k=2: "
                        + uniqueCombinations(duplicate, 2));
        System.out.println(
                "Unique permutations: "
                        + uniquePermutations(duplicate));

        System.out.println(
                "Empty subsets: " + subsets(new int[0]));
        System.out.println(
                "Empty permutations: "
                        + permutations(new int[0]));
        System.out.println(
                "Combinations k=0: "
                        + combinations(different, 0));
        System.out.println(
                "Input unchanged: " + Arrays.toString(duplicate));
    }
}
```

Chạy bằng **JDK 17 trở lên**:

```bash
javac EnumerateBacktrackingDemo.java
java EnumerateBacktrackingDemo
```

**Đầu ra chuẩn**, theo đúng thứ tự duyệt DFS và `List.toString()` của Java:

```text
Subsets: [[], [1], [1, 2], [1, 2, 3], [1, 3], [2], [2, 3], [3]]
Combinations k=2: [[1, 2], [1, 3], [2, 3]]
Permutations: [[1, 2, 3], [1, 3, 2], [2, 1, 3], [2, 3, 1], [3, 1, 2], [3, 2, 1]]
Unique subsets: [[], [1], [1, 1], [1, 1, 2], [1, 2], [2]]
Unique combinations k=2: [[1, 1], [1, 2]]
Unique permutations: [[1, 1, 2], [1, 2, 1], [2, 1, 1]]
Empty subsets: [[]]
Empty permutations: [[]]
Combinations k=0: [[]]
Input unchanged: [1, 1, 2]
```

### 10.1. Tại sao từng hàm đúng?

**`subsets`:** trạng thái `start` giữ chỉ số tối thiểu được phép chọn tiếp. Kết quả được ghi tại mọi nút. Mỗi dãy chỉ số tăng dần tương ứng với một và chỉ một đường DFS.

**`combinations`:** cùng cách giữ chỉ số tăng, nhưng chỉ ghi khi đủ k. Vòng `i<=n-need` loại các nhánh không đủ phần tử còn lại, nên không mất tổ hợp hoàn chỉnh nào.

**`permutations`:** `used[]` đánh dấu các vị trí đã chọn. Mỗi lá dùng đủ n vị trí đúng một lần; mỗi thứ tự vị trí dẫn đến một đường DFS duy nhất.

**`uniqueSubsets` và `uniqueCombinations`:** input được sort để các giá trị bằng nhau đứng cạnh nhau. Điều kiện `i>start && a[i]==a[i-1]` chỉ cắt các nhánh trùng ở **cùng một độ sâu**, vẫn cho phép chọn nhiều lần giá trị ấy từ các **vị trí khác nhau** ở các độ sâu kế tiếp.

**`uniquePermutations`:** input được sort; nếu có hai bản sao bằng nhau, quy tắc `!used[i-1]` không cho phép bản sao phía sau xuất hiện trước bản sao phía trước trong quá trình chọn. Nhờ chọn một đại diện chuẩn của mỗi hoán vị giá trị, ta không xuất trùng.

### 10.2. Tại sao dùng bản sao input?

Các hàm không unique có thể duyệt trực tiếp input mà không thay nó. Các hàm unique cần `Arrays.sort(sorted)` để đưa các giá trị bằng nhau về sát nhau, nên dùng:

```java
int[] sorted = input.clone();
Arrays.sort(sorted);
```

Như vậy mảng gốc không đổi. Nếu hợp đồng cho phép sửa input thì có thể sort trực tiếp để tiết kiệm bản sao, nhưng phải nói rõ hành vi đó cho người gọi.

### 10.3. API trả về List, không trả về Set

Ở `unique...`, “không trùng” được bảo đảm **bằng cấu trúc thuật toán**, không bằng cách đẩy mọi kết quả vào `HashSet` rồi xóa trùng. Cách làm này:

- Tránh sinh hàng loạt nghiệm trùng ngay từ đầu.
- Giữ được thứ tự xuất xác định theo DFS trên bản đã sort.
- Không cần lưu hai cấu trúc `Set` và `List` để lọc lại toàn bộ kết quả.

Đối với các bài có ràng buộc phức tạp, việc khử trùng bằng canonical-state hoặc memoization có thể hợp lý, nhưng không nên coi dùng `Set` để xóa trùng **sau khi sinh tất cả** là luôn đủ hiệu quả.

---

## 11. Phân tích độ phức tạp đúng theo kích thước đầu ra

Gọi `n` là số vị trí đầu vào, `k` là số phần tử phải chọn cho tổ hợp.

### 11.1. Tập con

Có đúng:

\[
2^n
\]

tập con vị trí.

Nếu chỉ duyệt cây, số nút là `\Theta(2^n)`. Nhưng trong chương trình, mỗi nút **sao chép path**. Tổng số giá trị được đưa vào các bản sao là:

\[
\sum_{S\subseteq\{0,\ldots,n-1\}}|S|
=n\,2^{n-1}
\quad(n\ge1).
\]

Vì mỗi vị trí thuộc đúng một nửa số tập con, ta có chặn:

- **Thời gian sinh và lưu mọi tập con:** `\Theta(n2^n)` với `n≥1` trong mô hình thao tác cơ bản theo phần tử.
- **Bộ nhớ nếu lưu tất cả:** `\Theta(n2^n)` cho các phần tử đầu ra (chưa tính overhead của `ArrayList`).
- **Bộ nhớ làm việc khi phát từng tập con:** `O(n)` cho path và stack đệ quy, không tính bộ nhớ output/callback.

Với `n=0`, chỉ có **một tập con rỗng**, chi phí hằng số.

### 11.2. Tổ hợp chập k

Số kết quả:

\[
\binom nk.
\]

Mỗi kết quả dài k, nên việc **sao chép toàn bộ kết quả** cần ít nhất:

\[
\Omega\left(k\binom nk\right)
\]

thao tác ghi phần tử khi `k>0`.

Với thuật toán DFS đã pruning để chỉ đi vào tiền tố còn có thể hoàn tất đủ k phần tử, số nút và chi phí duyệt được chặn cùng bậc theo **chiều sâu tối đa k** và số tổ hợp. Một cách diễn đạt hữu dụng:

- **Thời gian:** `O((k+1)\binom nk)` cho `0≤k≤n`, bỏ qua chi phí xuất định dạng và giả sử các thao tác List cơ bản hằng số khấu hao.
- **Bộ nhớ làm việc:** `O(k)` cho đường chọn và stack DFS, không tính input.
- **Nếu lưu tất cả:** thêm `O((k+1)\binom nk)` ô/tham chiếu kết quả (bao gồm danh sách/metadata); riêng phần tử giá trị là `\Theta(k\binom nk)`.

Với `k=0` chỉ có một nghiệm rỗng, mất `O(1)`. Nếu `k=n`, chỉ có một tổ hợp, việc sao chép cần `\Theta(n)` thời gian và không gian kết quả.

**Cẩn trọng:** công thức `\binom nk` có thể rất lớn ngay khi n vừa phải và k gần n/2. Ví dụ `\binom{30}{15}` đã vượt 155 triệu; không phải cứ `n=30` là có thể lưu mọi tổ hợp.

### 11.3. Hoán vị

Có `n!` hoán vị vị trí. Mỗi nghiệm dài n, nên riêng phần xuất:

\[
\Omega(n\cdot n!).
\]

Với code dùng `used[]`, có tối đa n lần kiểm tra ứng viên ở mỗi nút DFS; tổng số nút là:

\[
\sum_{j=0}^{n}\frac{n!}{(n-j)!}=O(n!),
\]

và số lần quét ứng viên trên tất cả nút tạo chặn `O(n\cdot n!)`. Tổng:

- **Thời gian sinh và sao chép:** `\Theta(n\cdot n!)` với n dương.
- **Bộ nhớ làm việc:** `O(n)` cho `used[]`, path và stack.
- **Nếu lưu tất cả kết quả:** `\Theta(n\cdot n!)` phần tử kết quả, chưa kể metadata đối tượng.

### 11.4. Các hàm unique

Khi dữ liệu có trùng:

- Unique subsets có `\prod_j(f_j+1)` kết quả.
- Unique permutations có `n!/\prod_j f_j!` kết quả.
- Unique combinations dài k có số kết quả bằng hệ số `x^k` của `\prod_j(1+x+\cdots+x^{f_j})`.

Tuy nhiên, vì mỗi mức DFS còn có thể phải **quét các vị trí để kiểm tra skip**, **không được tự lấy số kết quả unique nhân độ dài rồi tuyên bố đó là cận thời gian chặt** cho mọi cách cài. Chặn đơn giản từ thuật toán theo vị trí vẫn áp dụng làm giới hạn trên, cộng thời gian sắp `O(n log(n+1))`; mức tiết kiệm thực tế phụ thuộc số giá trị trùng và cấu trúc vòng lặp.

Với rất nhiều giá trị trùng, biểu diễn theo **tần suất mỗi giá trị** và lựa chọn số bản sao của từng loại có thể giảm chi phí kiểm tra hơn cách duyệt từng vị trí. Đó là tối ưu nâng cao hữu ích khi n lớn nhưng số loại giá trị phân biệt r nhỏ.

---

## 12. Backtracking với tần suất: một lựa chọn khác khi trùng nhiều

Nếu dữ liệu có nhiều phần tử trùng, có thể dùng mảng:

```text
values = [giá trị phân biệt đã sắp]
count  = [số lần xuất hiện của từng giá trị]
```

Ví dụ `[1,1,1,2,2]`:

```text
values = [1,2]
count  = [3,2]
```

Đối với **hoán vị unique**, tại mỗi độ sâu:

1. Chọn một giá trị `values[j]` còn `count[j]>0`.
2. Giảm `count[j]` đi 1.
3. Thêm giá trị ấy vào path rồi đệ quy.
4. Hoàn tác: bỏ giá trị khỏi path và tăng `count[j]` lại 1.

```text
UNIQUE_PERM_WITH_COUNTS(values, count, path):
    if path.length == n:
        emit(copy(path))
        return

    for j từ 0 đến r-1:
        if count[j] == 0:
            continue

        count[j]--
        path.add(values[j])
        DFS(...)
        path.removeLast()
        count[j]++
```

Vì mỗi giá trị phân biệt chỉ có **một nhánh tương ứng** tại một trạng thái, thuật toán tránh tạo các nhánh chỉ khác nhau bởi danh tính các bản sao bằng nhau.

Đối với **tập con unique**, có thể chọn số lần xuất hiện `t_j` của mỗi giá trị j, từ `0` đến `f_j`, rồi đệ quy sang giá trị tiếp theo. Mọi bộ số lượng `(t_1,\ldots,t_r)` tạo đúng một đa tập giá trị.

**Chú ý:** chọn số lượng cho mỗi giá trị là cách sinh các **đa tập giá trị**, không phải liệt kê từng tập con vị trí. Nếu bài cần danh tính từng phần tử, không được nén mất thông tin vị trí.

---

## 13. Liệt kê trực tuyến và giới hạn tài nguyên

Các ví dụ `List<List<Integer>>` rất tiện để học, nhưng có thể tiêu thụ rất nhiều RAM. Khi chỉ cần in từng kết quả, ghi vào tệp hoặc đẩy qua một pipeline, nên **phát từng nghiệm khi tới trạng thái hoàn chỉnh**, thay vì lưu mọi nghiệm.

### 13.1. Dùng Consumer trong Java

Phần dưới là **mẫu minh họa** có thể ghép vào class Java đã có; nó không tự là chương trình độc lập:

```java
static void emitSubsets(
        int[] input,
        java.util.function.Consumer<java.util.List<Integer>> sink) {

    java.util.Objects.requireNonNull(input, "input");
    java.util.Objects.requireNonNull(sink, "sink");

    emitDfs(input, 0, new java.util.ArrayList<>(), sink);
}

private static void emitDfs(
        int[] input,
        int start,
        java.util.List<Integer> path,
        java.util.function.Consumer<java.util.List<Integer>> sink) {

    // Give the consumer a stable snapshot.
    sink.accept(new java.util.ArrayList<>(path));

    for (int i = start; i < input.length; i++) {
        path.add(input[i]);
        emitDfs(input, i + 1, path, sink);
        path.remove(path.size() - 1);
    }
}
```

Nếu consumer chỉ in và không giữ kết quả, bộ nhớ cho path và stack vẫn khoảng `O(n)`, không tính bộ đệm của hệ thống xuất. Nhưng **thời gian và kích thước luồng xuất vẫn là cấp số mũ**: không thể tạo `2^n` bản ghi trong thời gian đa thức theo n.

### 13.2. Dừng sớm khi không cần tất cả

Đôi khi đề yêu cầu:

- Chỉ tìm **một** kết quả thỏa ràng buộc.
- In tối đa `limit` kết quả.
- Tìm kết quả đầu tiên theo một thứ tự ưu tiên.
- Kiểm tra **có tồn tại** nghiệm hay không.

Khi đó có thể chuyển DFS thành hàm trả `boolean` để báo tìm thấy/dừng, hoặc dùng một biến đếm kết quả đã phát. Phải bảo đảm việc dừng sớm vẫn **hoàn tác trạng thái** trên mọi nhánh đang hoạt động, nhất là khi dùng mảng `used[]` hoặc swap.

Nếu API hứa liệt kê **tất cả**, tự áp đặt limit mà không thông báo sẽ tạo một danh sách **thiếu nghiệm**. Hãy tách rõ chế độ “tất cả”, “tối đa L nghiệm” và “một nghiệm”.

### 13.3. Bộ nhớ và stack

- Độ sâu đệ quy tối đa bằng **n** cho tập con/hoán vị; bằng k cho tổ hợp.
- Java có giới hạn stack cho mỗi thread. Với n rất lớn, ngay cả khi số kết quả bị giới hạn, việc đệ quy sâu có thể gây `StackOverflowError`.
- Cách liệt kê lặp bằng bitmask, chỉ số tổ hợp hoặc thuật toán sinh hoán vị kế tiếp có thể tránh một phần giới hạn stack, nhưng không làm giảm **số kết quả phải xuất**.
- Nên ước lượng **số kết quả** trước khi lưu; nếu số lượng khổng lồ, cần điều chỉnh yêu cầu bài toán hoặc chỉ tính số lượng.

---

## 14. Các cách liệt kê khác ngoài DFS

### 14.1. Tập con bằng bitmask

Nếu n đủ nhỏ và một kiểu số nguyên biểu diễn được các bit, có thể duyệt:

```text
for mask từ 0 đến (1<<n)-1:
    subset = []
    for i từ 0 đến n-1:
        if bit i của mask bật:
            subset.add(a[i])
    emit(subset)
```

Ví dụ n=3:

```text
mask 000 -> []
mask 001 -> [1]
mask 010 -> [2]
mask 011 -> [1,2]
mask 100 -> [3]
mask 101 -> [1,3]
mask 110 -> [2,3]
mask 111 -> [1,2,3]
```

Đây là **thứ tự mask tăng dần**, khác thứ tự DFS ở mục 4.

Trong Java, phải kiểm tra giới hạn:

- Với `int`, `1<<n` có vấn đề khi n quá lớn; `1<<32` không tạo `2^{32}` vì số bit shift bị giới hạn.
- Với `long`, có thể biểu diễn nhiều bit hơn nhưng vẫn không thể duyệt `2^n` kết quả khi n lớn.
- **Bitmask không tự khử trùng theo giá trị**; nó chỉ phân biệt vị trí.

### 14.2. Tổ hợp bằng chỉ số tăng

Một tổ hợp chập k có thể biểu diễn bằng dãy chỉ số:

\[
0\le c_0<c_1<\cdots<c_{k-1}<n.
\]

Bắt đầu từ:

```text
c = [0,1,...,k-1]
```

Để sinh tổ hợp kế tiếp theo thứ tự từ điển của chỉ số:

1. Tìm vị trí p lớn nhất sao cho `c_p<n-k+p`.
2. Tăng `c_p` thêm 1.
3. Với mọi `j>p`, đặt `c_j=c_{j-1}+1`.
4. Nếu không có vị trí p, đã ở tổ hợp cuối.

Ví dụ n=5,k=3:

```text
[0,1,2] -> [0,1,3] -> [0,1,4]
        -> [0,2,3] -> [0,2,4] -> [0,3,4]
        -> [1,2,3] -> [1,2,4] -> [1,3,4]
        -> [2,3,4]
```

Đây là cách liệt kê **lặp**, không cần DFS. Nó vẫn sinh đúng `\binom nk` kết quả và cần `O(k)` bộ nhớ cho dãy chỉ số đang dùng.

### 14.3. Hoán vị kế tiếp theo thứ tự từ điển

Nếu muốn các **hoán vị giá trị phân biệt** theo thứ tự từ điển, có thể bắt đầu bằng bản sao **đã sắp tăng** rồi lặp `nextPermutation`:

1. Tìm vị trí i lớn nhất sao cho `a[i]<a[i+1]`.
2. Nếu không có, đang ở hoán vị cuối.
3. Tìm j lớn nhất ở bên phải với `a[j]>a[i]`.
4. Đổi `a[i]` và `a[j]`.
5. Đảo ngược đoạn đuôi sau i.

Mỗi bước xử lý `O(n)` vị trí trong bản đơn giản. Bắt đầu từ dãy đã sắp, phương pháp này sinh mỗi **hoán vị giá trị khác nhau** đúng một lần ngay cả khi input có giá trị trùng, vì dãy không giảm ban đầu và quy tắc “kế tiếp lớn hơn” không lặp lại một cách biểu diễn giá trị.

**Khác biệt với `used[]`:** `nextPermutation` sinh hoán vị của **dãy giá trị được sắp**, còn `used[]` có thể sinh hoán vị **theo vị trí** cho dù các giá trị trùng nhau. Chọn cách nào phải dựa trên hợp đồng của đề.

### 14.4. Khi nào dùng phương pháp nào?

| Yêu cầu | Cách thường phù hợp |
| --- | --- |
| Mọi tập con vị trí, muốn DFS và dễ thêm ràng buộc | `start + path` |
| Mọi tập con vị trí, n nhỏ, muốn duyệt lặp | Bitmask |
| Tổ hợp đúng k, có thể cắt nhánh | DFS với `start` và `need` |
| Tổ hợp đúng k, chỉ muốn sinh tuần tự theo chỉ số | Thuật toán tổ hợp kế tiếp |
| Hoán vị theo vị trí | `used[]` hoặc swap |
| Hoán vị giá trị duy nhất | Sort + `used[]` + skip, hoặc `nextPermutation` |
| Nhiều giá trị trùng | Mảng tần suất theo giá trị |
| Chỉ cần số lượng | Công thức tổ hợp/hoán vị hoặc DP đếm |
| Chỉ cần một nghiệm thỏa ràng buộc | Backtracking có điều kiện dừng sớm |

---

## 15. Thêm ràng buộc và pruning cho bài quay lui

Ba bài toán sinh thuần túy là nền tảng của nhiều bài tìm kiếm có ràng buộc:

- Chọn một tập con có tổng bằng S.
- Chọn đúng k phần tử với tổng không vượt B.
- Sinh hoán vị thỏa điều kiện kề nhau.
- Sinh lịch sắp xếp công việc với ràng buộc thứ tự.
- Bài xếp quân hậu, ghép cặp, chọn đường đi.

Khi thêm ràng buộc, có thể loại nhánh sớm nếu **chứng minh nhánh ấy không thể dẫn tới nghiệm hợp lệ hoặc tốt hơn**.

### 15.1. Một ví dụ pruning an toàn

Giả sử các số trong input đều **không âm**, ta cần tìm một tập con có tổng **đúng S**, và tại một trạng thái tổng đã chọn là `current`.

Nếu:

\[
current>S,
\]

thì việc chọn thêm các số không âm **không làm tổng giảm**, nên có thể cắt nhánh ngay.

**Nhưng nếu input có số âm**, điều kiện trên không còn đúng: một số âm được chọn sau có thể đưa tổng từ lớn hơn S về đúng S. Vì thế pruning chỉ đúng khi **giả thiết số không âm được đảm bảo**.

### 15.2. Cận trên/cận dưới khi chọn đúng k

Nếu chọn đúng k phần tử và còn thiếu `need`, việc chỉ còn ít hơn `need` vị trí là một **cận cấu trúc** không phụ thuộc giá trị phần tử. Đây là lý do `i<=n-need` luôn an toàn cho tổ hợp chọn vị trí tăng.

Nếu muốn cắt thêm bằng tổng tối thiểu/tối đa có thể đạt, phải chứng minh cận dựa trên giá trị đã sắp hoặc dữ liệu còn lại. Không thể giả định một cận từ số lượng phần tử mà bỏ qua các giá trị âm hoặc các ràng buộc phụ.

### 15.3. Backtracking không phải dynamic programming

Backtracking **duyệt các nhánh lựa chọn** và dùng hoàn tác; DP thường **gộp các trạng thái tương đương** để tránh tính lại. Khi yêu cầu **liệt kê tất cả lời giải**, không thể chỉ lưu một số trạng thái tối ưu rồi bỏ các nhánh khác nếu những nhánh ấy tạo những kết quả khác nhau cần in.

Có thể kết hợp memoization/pruning với backtracking để kiểm tra tính khả thi hoặc giảm lặp, nhưng phải đảm bảo không loại nhầm những nghiệm khác nhau mà người dùng yêu cầu liệt kê.

---

## 16. Chứng minh ba thuật toán bằng bất biến

### 16.1. Tập con

**Bất biến:** path chứa các vị trí tăng nghiêm ngặt đã chọn trước start. Mọi phần tử có thể thêm tiếp có chỉ số ≥start.

- **Hợp lệ:** mỗi vị trí được chọn nhiều nhất một lần, và danh sách kết quả là tập con vị trí.
- **Đầy đủ:** mọi tập con có duy nhất danh sách chỉ số tăng dần, nên có một đường chọn tương ứng.
- **Không lặp theo vị trí:** đường chỉ số tăng dần của một tập con là duy nhất.
- **Dừng:** mỗi lời gọi con tăng start và số phần tử input hữu hạn.

### 16.2. Tổ hợp

**Bất biến:** path có các chỉ số tăng, độ dài không vượt k.

- **Hợp lệ:** chỉ xuất khi path dài chính xác k.
- **Đầy đủ:** với một tổ hợp vị trí có thứ tự chỉ số tăng, ở mỗi độ sâu luôn còn đủ vị trí để hoàn tất. Vì thế điều kiện pruning `i<=n-need` không loại đường đi của nó.
- **Không lặp theo vị trí:** mỗi bộ chỉ số tăng xác định một nhánh duy nhất.
- **Dừng:** số phần tử được chọn tăng ở mỗi lần đệ quy, không vượt k.

### 16.3. Hoán vị

**Bất biến:** `used[i]` đúng khi vị trí i nằm trong path, mỗi vị trí xuất tối đa một lần.

- **Hợp lệ:** khi path dài n, nó là một thứ tự của toàn bộ n vị trí.
- **Đầy đủ:** mọi thứ tự vị trí có thể được chọn lần lượt vì tại bước của nó, vị trí tương ứng chưa dùng.
- **Không lặp theo vị trí:** hai thứ tự vị trí khác nhau phải rẽ sang hai nhánh khác nhau.
- **Dừng:** số vị trí đánh dấu tăng mỗi bước, tối đa n.

### 16.4. Chứng minh khử trùng với dữ liệu đã sort

**Unique subset/combination:** các vị trí bằng nhau xuất hiện liên tiếp. Tại cùng lời gọi, thử bản sao sau của một giá trị chưa được chọn trước trong path sẽ tạo các kết quả giá trị có thể tạo từ bản sao đầu. Giữ **nhánh đại diện đầu tiên** của mỗi giá trị tại một độ sâu là đủ; các bản sao còn lại vẫn có thể được chọn ở độ sâu sau.

**Unique permutation:** khi các bản sao bằng nhau đứng cạnh nhau, buộc thứ tự sử dụng các bản sao ấy là **từ chỉ số nhỏ tới lớn**. Mọi hoán vị giá trị đều có một cách gán chỉ số thỏa quy tắc chuẩn này, trong khi các cách gán chỉ số chỉ khác thứ tự những bản sao bằng nhau bị cắt. Do đó mỗi hoán vị giá trị xuất đúng một lần.

**Cảnh báo về nghĩa "unique":** nếu kết quả phải giữ danh tính hoặc id gắn với từng phần tử, phép khử theo giá trị có thể **làm mất nghiệm được xem là khác nhau trong đề**.

---

## 17. Kiểm thử các trường hợp biên

| Input / yêu cầu | Kết quả đúng |
| --- | --- |
| `a=[]`, liệt kê tập con | `[[]]` |
| `a=[]`, tổ hợp k=0 | `[[]]` |
| `a=[]`, liệt kê hoán vị | `[[]]` |
| `a=[5]`, tập con | `[[],[5]]` |
| `a=[5]`, tổ hợp k=1 | `[[5]]` |
| `a=[5]`, hoán vị | `[[5]]` |
| `a=[1,2,3]`, tổ hợp k=2 | `[[1,2],[1,3],[2,3]]` |
| `a=[1,2,3]`, tổ hợp k=0 | `[[]]` |
| `a=[1,2,3]`, tổ hợp k=3 | `[[1,2,3]]` |
| `a=[1,2,3]`, tổ hợp k=4 | Code mẫu báo ngoại lệ vì k>n |
| `a=[1,1,2]`, unique subsets | 6 kết quả khác nhau theo giá trị |
| `a=[1,1,2]`, unique combinations k=2 | `[[1,1],[1,2]]` |
| `a=[1,1,2]`, unique permutations | 3 kết quả |
| `a=[2,2,2]`, unique subsets | `[],[2],[2,2],[2,2,2]` — 4 kết quả |
| `a=[2,2,2]`, unique permutations | `[[2,2,2]]` — 1 kết quả |
| `a=[-1,0,1]`, hoán vị | 6 kết quả vị trí, dấu âm không ảnh hưởng |
| Input là mảng null | Code mẫu báo `NullPointerException` có thông báo tham số |

### 17.1. Kiểm thử thuộc tính thay vì chỉ so văn bản

Nếu input gồm n phần tử **phân biệt**:

- `subsets(a).size()==2^n`, trong phạm vi mà số kết quả có thể tạo.
- `combinations(a,k).size()==\binom nk`.
- `permutations(a).size()==n!`.

Với **mỗi tập con/tổ hợp**:

- Các chỉ số gốc phải tăng nếu bạn lưu kèm chỉ số.
- Không vị trí nào dùng quá một lần.
- Với tổ hợp, số phần tử phải đúng k.

Với **mỗi hoán vị**:

- Độ dài đúng n.
- Mỗi vị trí input được dùng đúng một lần.
- Nếu có giá trị trùng và chỉ lưu giá trị, kiểm tra **đa tập tần suất** của kết quả bằng đa tập input thay vì so set các giá trị.

Với hàm `unique...`:

- Không có hai danh sách kết quả bằng nhau theo giá trị và thứ tự đã chuẩn hóa.
- Tổng số kết quả khớp công thức theo tần suất hoặc đối chiếu với thuật toán đơn giản dùng Set trên input nhỏ.
- Input ban đầu không thay đổi nếu đó là hợp đồng.

### 17.2. Kiểm thử ngẫu nhiên bằng oracle

Trên n nhỏ (ví dụ 0 tới 8), sinh ngẫu nhiên các mảng có giá trị trong khoảng hẹp `[-2,2]` để có nhiều trùng:

1. Liệt kê tất cả **chỉ số** tập con bằng bitmask.
2. Từ các tập con có đúng k phần tử, tạo oracle tổ hợp.
3. Liệt kê hoán vị vị trí bằng một thuật toán độc lập như swap.
4. Chuẩn hóa thứ tự giá trị khi cần rồi dùng Set cho **oracle unique**.
5. So tập kết quả của code đang kiểm thử với oracle; không cần đòi thứ tự in phải giống nếu đề không quy định.
6. Với mỗi input, kiểm tra các hàm unique thực sự không thay đổi input.

Đây là kiểm thử **chéo thuật toán**: oracle trên n nhỏ có thể chậm nhưng dễ kiểm tra. Với n lớn, dùng các thuộc tính, không thử xuất toàn bộ hoán vị làm kiểm thử thường xuyên.

---

## 18. Những lỗi thường gặp

1. **Nhầm subset và permutation:** in `[1,2]` và `[2,1]` như hai tập con khác nhau.
2. **Nhầm tổ hợp k với tập con tự do:** xuất các đường chọn có độ dài nhỏ hơn k.
3. **Quên undo:** `path` hoặc `used[]` từ một nhánh rò rỉ sang nhánh tiếp theo.
4. **Lưu tham chiếu path thay vì bản sao:** mọi kết quả cùng trỏ tới một danh sách đang thay đổi.
5. **Dùng start tăng cho permutation:** ngăn các vị trí được chọn theo thứ tự đảo.
6. **Không tăng start cho subset/combination:** có thể lặp lại một vị trí hoặc xuất trùng cách chọn.
7. **Dùng `i>0 && a[i]==a[i-1]` để skip subset:** cắt luôn `[1,1]` khi input có hai số 1.
8. **Dùng `i>start` cho permutation:** không biểu diễn được quy tắc khử trùng đúng vì hoán vị dùng `used[]` chứ không có thứ tự chỉ số tăng.
9. **Dùng điều kiện skip trùng trên mảng chưa sắp:** các giá trị bằng nhau không nhất thiết đứng kề nhau.
10. **Xóa trùng bằng Set sau khi sinh `n!` bản ghi:** có thể đã tốn phần lớn thời gian và RAM trước khi lọc.
11. **Không phân biệt giá trị trùng với phần tử có id khác:** khử theo giá trị có thể làm thiếu các kết quả gắn danh tính.
12. **Không xử lý k=0:** bỏ lỡ nghiệm rỗng.
13. **Không xử lý input rỗng:** kết luận sai rằng tập rỗng không có tập con hoặc không có hoán vị.
14. **Báo `[]` thay cho `[[]]`:** làm mất một nghiệm rỗng duy nhất.
15. **Đếm số lượng bằng `int` mà không xét tràn:** `n!` và `2^n` tăng rất nhanh.
16. **Trộn lẫn độ phức tạp tìm kiếm và chi phí in:** liệt kê n! hoán vị dài n cần ít nhất `\Omega(n n!)` thao tác đầu ra.
17. **Pruning không có chứng minh:** cắt khi tổng vượt mục tiêu dù dữ liệu có số âm.
18. **Sửa input bằng sort mà không thông báo:** phá hợp đồng giữ nguyên mảng nguồn.
19. **Dùng danh sách kết quả trong RAM cho n quá lớn:** `OutOfMemoryError` hoặc thời gian cực dài.
20. **Tưởng DFS luôn cho thứ tự từ điển của giá trị:** nếu input chưa sort, thứ tự DFS theo chỉ số không nhất thiết theo giá trị.
21. **Không phân biệt liệt kê hết với tìm một nghiệm:** dừng sau nghiệm đầu khi đề yêu cầu tất cả.
22. **Hoán vị swap nhưng quên đổi lại hai phần tử:** các nhánh sau bị thay đổi thứ tự input và sinh sai.

---

## 19. Quy trình áp dụng cho bài thực tế

Khi gặp đề “liệt kê các cách chọn/sắp xếp”, hãy dùng checklist:

1. **Đếm bao nhiêu phần tử phải chọn?** Bất kỳ, đúng k hay tất cả?
2. **Thứ tự có ý nghĩa không?** Nếu có, nghĩ tới permutation; nếu không, subset/combination.
3. **Phân biệt theo chỉ số hay theo giá trị?** Các giá trị trùng nhưng id khác có được xem là nghiệm khác không?
4. **Có thể tái sử dụng một phần tử không?** Ba bài chuẩn ở đây **không** chọn lại cùng vị trí; nếu cho phép lặp, thuật toán khác.
5. **Nên dùng trạng thái gì?** `start` cho chỉ số tăng, `used[]` hoặc swap cho mọi thứ tự.
6. **Khi nào xuất kết quả?** Mọi nút cho subsets, độ dài k cho combinations, độ dài n cho permutations.
7. **Các bước undo là gì?** Liệt kê toàn bộ biến bị sửa rồi khôi phục đúng.
8. **Có phần tử trùng không?** Sort bản sao và áp dụng điều kiện skip phù hợp, hoặc dùng bảng tần suất.
9. **Có pruning nào được chứng minh an toàn không?** Ví dụ còn không đủ vị trí cho tổ hợp.
10. **Số nghiệm ước tính bao nhiêu?** Nếu quá lớn, chỉ tính số lượng, phát trực tuyến, dừng sớm theo hợp đồng hoặc đổi yêu cầu.
11. **Kiểm thử thế nào?** Input rỗng, k=0, phần tử trùng, âm, n nhỏ đối chiếu bitmask/swap.
12. **Thứ tự xuất có bắt buộc không?** Nếu có, đảm bảo thứ tự duyệt/sort phản ánh đúng quy tắc yêu cầu.

---

## 20. Bài tập tự kiểm tra

**Bài 1 — Định nghĩa.** Với `[1,2,3]`, hãy liệt kê mọi tập con vị trí, tổ hợp k=2 và hoán vị đầy đủ. Mỗi nhóm có bao nhiêu kết quả?

**Bài 2 — Cây nhị phân.** Viết giả mã sinh tập con theo hai lựa chọn “không chọn/chọn”. Vì sao có `2^n` lá? Khi nào xuất kết quả để không bị trùng?

**Bài 3 — Pruning tổ hợp.** Với n=7,k=3, tại gốc có thể thử chỉ số đầu tiên i tới tối đa bao nhiêu? Nếu path đã dài 2 và start=5, có thể thử những i nào để chọn đủ k=3?

**Bài 4 — Phần tử trùng.** Với `[1,1,2]`, liệt kê các tập con giá trị khác nhau, tổ hợp giá trị k=2 và hoán vị giá trị khác nhau. Tính số lượng bằng công thức tần suất.

**Bài 5 — Sai lầm về skip.** Vì sao điều kiện `if (i>0 && a[i]==a[i-1]) continue` sẽ làm mất `[1,1]` khi liệt kê tập con unique? Điều kiện đúng là gì?

**Bài 6 — Hoán vị unique.** Giải thích ý nghĩa của `!used[i-1]` trong điều kiện skip hoán vị với input đã sắp. Điều gì xảy ra nếu bỏ điều kiện mà giữ mỗi `used[i]`?

**Bài 7 — Kết quả rỗng.** Với n=0, tập con có bao nhiêu kết quả? Hoán vị rỗng có bao nhiêu? Tổ hợp k=0 có bao nhiêu? Vì sao `[[]]` khác `[]`?

**Bài 8 — Độ phức tạp.** Vì sao một thuật toán sinh 2^n tập con **và sao chép từng path** tốn `\Theta(n2^n)` chứ không thể chỉ nói `O(2^n)` cho toàn bộ công việc xuất? Tương tự cho n! hoán vị dài n.

**Bài 9 — Kiểm thử trạng thái.** Với hàm hoán vị dùng `used[]`, hãy viết ba bất biến cần kiểm tra khi bước vào DFS và sau khi quay lui.

**Bài 10 — Sinh thay vì lưu.** Có cần lưu mọi hoán vị trong `List<List<Integer>>` nếu nhiệm vụ chỉ là in lần lượt ra file? Có thể dùng cấu trúc nào để phát từng nghiệm và bộ nhớ phụ là bao nhiêu?

**Bài 11 — Đếm không liệt kê.** Tính số tổ hợp chọn 3 phần tử từ 8 vị trí, số tập con của 8 vị trí và số hoán vị của 8 vị trí. Khi n rất lớn nên dùng kiểu số nào trong Java để tính số đếm chính xác?

**Bài 12 — Pruning có điều kiện.** Một bài cần tìm tập con có tổng S. Nếu mọi số không âm, khi tổng hiện tại > S có được cắt nhánh không? Nếu có số âm thì sao?

**Bài 13 — Sinh tổ hợp kế tiếp.** Với n=5,k=3 và chỉ số `[0,2,4]`, tổ hợp kế tiếp theo thứ tự từ điển là gì? Tại sao phải đặt lại các chỉ số phía sau một vị trí vừa tăng?

**Bài 14 — Dữ liệu trùng nhiều.** Với `[2,2,2,5,5]`, có bao nhiêu tập con giá trị khác nhau và bao nhiêu hoán vị giá trị khác nhau? Có lợi gì khi biểu diễn input thành `values=[2,5], count=[3,2]`?

**Bài 15 — Xác định hợp đồng.** Một dữ liệu có hai nhân viên khác id nhưng cùng điểm 10. Nếu đề yêu cầu liệt kê “mọi tổ hợp nhân viên”, có được loại trùng hai kết quả chỉ vì danh sách điểm giống nhau không?

**Bài 16 — Chọn phương pháp.** Nếu đề yêu cầu chọn đúng 4 phần tử không xét thứ tự và kèm ràng buộc tổng, bạn chọn bitmask, DFS `start` hay permutation? Giải thích dựa trên số lựa chọn và pruning.

### Đáp án gợi ý

1. Có `2³=8` tập con, `\binom32=3` tổ hợp k=2 và `3!=6` hoán vị. Danh sách đầy đủ ở các mục 1 và 10.
2. Với mỗi i có hai nhánh độc lập (chọn hoặc không), tạo `2^n` lá. Chỉ xuất khi `i==n` để mỗi quyết định đầy đủ xuất một lần.
3. Ở gốc `need=3`, chỉ thử `i≤7-3=4`. Khi path dài 2, `need=1`, `start=5`, thử i=5 và i=6.
4. Tập con unique: `[],[1],[1,1],[1,1,2],[1,2],[2]`; tổ hợp k=2: `[1,1],[1,2]`; hoán vị: `[1,1,2],[1,2,1],[2,1,1]`. Số lượng lần lượt 6, 2, 3.
5. Điều kiện ấy loại mọi bản sao giá trị 1 ở vị trí sau, kể cả khi phải chọn hai bản sao ở hai độ sâu. Dùng `i>start && a[i]==a[i-1]` trong bản đã sort.
6. Chỉ cho phép chọn bản sao giá trị trùng **sau** khi bản sao đứng trước đã dùng, tức cố định cách gán id của các bản sao bằng nhau. Nếu bỏ, sẽ sinh nhiều hoán vị vị trí khác nhau nhưng dãy giá trị trùng.
7. Mỗi trường hợp có **một** nghiệm rỗng, nên danh sách kết quả là `[[]]`. `[]` là không có nghiệm nào.
8. Có n2^{n-1} vị trí giá trị được ghi khi sao chép mọi tập con; với n! hoán vị dài n là n·n! giá trị cần xuất. Không thể bỏ chi phí đầu ra.
9. Số bit true của used bằng path.size; không vị trí nào được chọn hai lần; sau hoàn tác path và used quay về trạng thái trước nhánh.
10. Không cần. Dùng callback/Consumer, iterator hoặc ghi từng bản sao ra bộ xuất; stack và path cần khoảng `O(n)` bộ nhớ phụ, chưa tính bộ đệm output.
11. `\binom83=56`, `2^8=256`, `8!=40320`. Với số đếm lớn, dùng `BigInteger` thay vì `int`/`long` khi không được phép tràn.
12. Với mọi số không âm, tổng chỉ có thể giữ nguyên hoặc tăng, nên current>S là nhánh không đạt. Có số âm, kết luận này không còn an toàn.
13. `[0,3,4]`. Tìm vị trí có thể tăng từ phải sang trái rồi đặt phần đuôi thành dãy chỉ số liên tiếp nhỏ nhất lớn hơn giá trị trước nó để bảo toàn thứ tự tăng và không bỏ tổ hợp.
14. Unique subsets `(3+1)(2+1)=12`; unique permutations `5!/(3!2!)=10`. Biểu diễn bằng tần suất giảm việc thử các bản sao cùng giá trị như những nhánh tương đương.
15. **Không.** Hai nhân viên khác id là hai đối tượng phân biệt; trùng điểm không làm các tổ hợp nhân viên trở thành cùng một kết quả nếu hợp đồng phân biệt danh tính.
16. Chọn DFS với `start` và `path` độ dài k=4 để không sinh hoán vị trùng thứ tự, có thể cắt nhánh khi không đủ vị trí và áp dụng cận tổng nếu chứng minh an toàn. Bitmask cũng đúng nhưng có thể xét nhiều tập con không đủ 4 phần tử; permutation tạo thừa các thứ tự.

---

## Ghi nhớ

**Liệt kê tập con, tổ hợp và hoán vị** dùng chung tư duy **choose → explore → undo**, nhưng khác trạng thái và điều kiện xuất:

- **Tập con:** mỗi vị trí chọn hoặc không, số kết quả `2^n`; DFS với `start` xuất ở **mọi nút**.
- **Tổ hợp chập k:** chọn đúng k vị trí theo **thứ tự chỉ số tăng**, số kết quả `\binom nk`; chỉ xuất ở độ sâu k, có thể prune khi không đủ vị trí còn lại.
- **Hoán vị:** chọn đủ n vị trí theo **mọi thứ tự**, số kết quả `n!`; dùng `used[]` hoặc swap, chỉ xuất ở độ sâu n.
- **Dữ liệu trùng:** phải phân biệt **vị trí/id** và **giá trị**; với đầu ra unique, subset/combination dùng `i>start && a[i]==a[i-1]` trên bản sort, còn permutation dùng `used[]` kết hợp `i>0 && a[i]==a[i-1] && !used[i-1]`.
- **Đúng đắn:** giữ bất biến, hoàn tác mọi thay đổi, sao chép path khi xuất; chứng minh đầy đủ và không trùng theo hợp đồng.
- **Giới hạn:** số kết quả tăng theo hàm mũ/giai thừa; phải tính cả **chi phí xuất** và chọn phát từng nghiệm hoặc tính số lượng nếu không cần lưu tất cả.
