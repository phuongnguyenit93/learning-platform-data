# Cây tìm kiếm ba nhánh cho ký tự

> **Chương:** Trie và chỉ mục chuỗi · **Bài học:** Cây tìm kiếm ba nhánh cho ký tự

Giả sử một ứng dụng quản lý các từ `an`, `anh`, `ang`, `ao`, `ba` và `ban`. Nó cần kiểm tra một từ có tồn tại không, tìm những từ bắt đầu bằng `an` và xuất gợi ý theo thứ tự ký tự. Có thể dùng **Trie**, nhưng mỗi nút trie thường phải quản lý một tập các cạnh con, đôi khi bằng mảng lớn hoặc Hash Map.

**Cây tìm kiếm ba nhánh cho ký tự** (*Ternary Search Tree*, viết tắt **TST**) kết hợp hai tư tưởng: một **cây tìm kiếm nhị phân theo ký tự ở cùng vị trí** và một **đường nối ký tự kế tiếp giống trie**. Mỗi nút chứa đúng một ký tự khóa và có tối đa ba liên kết:

- **Trái (`left`):** tìm ký tự nhỏ hơn ký tự tại nút, **không** tăng vị trí trong từ.
- **Giữa (`eq` hoặc `mid`):** đã khớp ký tự tại nút; chuyển sang **vị trí kế tiếp** trong từ.
- **Phải (`right`):** tìm ký tự lớn hơn ký tự tại nút, **không** tăng vị trí trong từ.

Vì thế TST không đơn thuần là một trie có ba ký tự trong bảng chữ cái, cũng không đơn thuần là một BST lưu toàn bộ chuỗi. Tính đúng của nó dựa trên việc **chỉ tăng chỉ số ký tự khi đi nhánh giữa**, phân biệt **nút terminal** với nút trung gian, và không lẫn tập từ ở các nhánh trái/phải với các từ có cùng tiền tố.

Bài thuộc chương **Trie và chỉ mục chuỗi** của mô-đun `COMPUTER_SCIENCE_DATA_STRUCTURES`, hướng tới hiểu bất biến, thao tác và độ phức tạp thời gian–bộ nhớ để chọn cấu trúc phù hợp giữa mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị. Ta sẽ xây TST từ đặc tả, vẽ vết chèn/tìm, phân tích trường hợp xấu, cài đặt Python, rồi thảo luận Unicode, gợi ý tìm kiếm và chi phí của việc xóa nút.

## 1. Mục tiêu học tập

Sau khi học, bạn có thể:

1. Giải thích ý nghĩa của ba liên kết `left`, `eq`, `right` trong TST.
2. Phân biệt việc **so sánh ký tự cùng tầng** với việc **đọc ký tự tiếp theo của khóa**.
3. Phát biểu bất biến BST theo ký tự trong mỗi tầng và bất biến terminal cho từ đã lưu.
4. Mô phỏng tìm, thêm và xóa một khóa bằng TST.
5. Giải thích vì sao một đường đi qua nhánh trái/phải **không có nghĩa** đã khớp ký tự của nút đang xét.
6. Cài đặt TST dạng **Set các chuỗi phân biệt**, hỗ trợ khóa rỗng theo một quy ước rõ.
7. Liệt kê từ theo tiền tố đúng **thứ tự code point Unicode** bằng DFS lặp.
8. Duy trì **bộ đếm số khóa mang tiền tố** mà không tính nhầm các nhánh trái/phải.
9. So sánh độ phức tạp TST với Trie dùng Hash Map/mảng con và BST lưu chuỗi nguyên vẹn.
10. Phân tích ảnh hưởng của thứ tự chèn đến các đường trái/phải và lý do TST **không tự cân bằng**.
11. Nhận biết vì sao việc xóa chỉ dọn lá rỗng có thể giữ lại **nút phân nhánh đã hết khóa**, làm hiệu năng suy giảm theo lịch sử cập nhật.
12. Đánh giá Unicode, chuẩn hóa và chi phí tạo kết quả autocomplete.

## 2. Bài toán và đặc tả thao tác

Ta giả sử `K` là **tập khóa chuỗi phân biệt** hiện được lưu. Một khóa có thể rỗng, và mỗi ký tự trong Python `str` được xem là một Unicode code point.

Những thao tác cơ bản:

\[
contains(w)\iff w\in K.
\]

\[
countPrefix(p)=|\{w\in K:p\text{ là tiền tố của }w\}|.
\]

\[
matches(p)=\operatorname{sort}\{w\in K:w\text{ bắt đầu bằng }p\}.
\]

Các phép thêm và xóa có ngữ nghĩa Set:

- `insert(w)` trả `True` nếu thêm một khóa mới, `False` nếu đã có.
- `delete(w)` trả `True` nếu xóa được khóa, `False` nếu khóa không tồn tại.
- `len(tree)` là **số khóa phân biệt hiện còn**, không phải số nút.
- `autocomplete(p,k)` trả tối đa `k` khóa đầu tiên theo thứ tự đã chọn.

### 2.1. Ví dụ hợp đồng

Với:

```text
K = {"an", "ang", "anh", "ao", "ba", "ban"}
```

ta cần:

| Truy vấn | Kết quả | Giải thích |
| --- | --- | --- |
| `contains("an")` | `True` | Nút cuối khóa `an` là terminal |
| `contains("a")` | `False` | `a` là tiền tố, chưa phải khóa |
| `countPrefix("a")` | 4 | `an, ang, anh, ao` |
| `countPrefix("an")` | 3 | `an, ang, anh` |
| `matches("an")` | `[an, ang, anh]` | Khóa tiền tố đứng trước hậu duệ |
| `matches("b")` | `[ba, ban]` | Cùng ký tự đầu `b` |
| `matches("ax")` | `[]` | Không có khóa phù hợp |
| `matches("")` | Toàn bộ `K` tăng theo ký tự | Chuỗi rỗng là tiền tố mọi khóa |

“Trả theo thứ tự từ điển” trong bài có nghĩa **theo Unicode code point**, không mặc nhiên là quy tắc collation tiếng Việt. Ta sẽ quy định cách chuẩn hóa riêng nếu ứng dụng cần.

### 2.2. Tại sao có thêm `countPrefix`?

Một dịch vụ gợi ý thường muốn trả số lượng kết quả hoặc kiểm tra có kết quả trước khi xuất danh sách. Nếu đã tìm đúng nút của tiền tố, ta có thể lưu một bộ đếm để **không phải duyệt toàn bộ các từ** chỉ để trả số lượng.

Nhưng ở TST, bộ đếm phải tính theo đường **ký tự khớp (`eq`)**; các nhánh trái/phải còn có những ký tự **khác** ở cùng vị trí, không chia sẻ tiền tố hiện tại.

## 3. Nút TST chứa gì?

Một nút TST có dạng:

```text
TSTNode:
    char           # ký tự tại vị trí hiện đang xét
    left           # thử ký tự NHỎ HƠN, cùng vị trí
    eq             # đã khớp char, sang vị trí kế tiếp
    right          # thử ký tự LỚN HƠN, cùng vị trí
    terminal       # từ kết thúc ngay sau khi khớp char?
    through_count  # số khóa hiện còn khớp qua char này
```

Nút **không lưu cả từ**. Chuỗi khóa được khôi phục bằng các ký tự trên đường mà ta đã đi qua liên kết **giữa**. Các lần đi trái/phải chỉ đang tìm **lựa chọn khác ở cùng độ sâu**, nên không thêm ký tự vào tiền tố đang dựng.

### 3.1. Ba nhánh mang ba ý nghĩa khác nhau

Giả sử nút hiện tại có `char='m'` và chương trình đang đọc `word[i]`:

```text
                  [m]
                /  |  \
             left  eq right
              <m   =m   >m
           giữ i  i+1  giữ i
```

- Nếu `word[i]='a'`, đi `left`, vẫn tiếp tục so **chính ký tự `a`** tại nút mới.
- Nếu `word[i]='z'`, đi `right`, vẫn so **chính ký tự `z`** tại nút mới.
- Nếu `word[i]='m'`, ký tự này đã khớp. Nếu còn ký tự tiếp theo, đi `eq` và tăng `i`.

**Bất biến quan trọng:** `i` chỉ tăng khi `word[i]==node.char` và ta đi xuống `eq`. Tăng `i` trên nhánh trái/phải sẽ bỏ qua ký tự chưa khớp và dẫn tới kết quả sai.

### 3.2. Nút terminal có thể có nhiều nhánh

TST lưu cả `"an"` và `"anh"` cần một nút tương ứng với ký tự `n` ở vị trí thứ hai và `terminal=True`. Nút ấy vẫn có thể có `eq` dẫn tới ký tự `h` để biểu diễn `anh`.

Tương tự như trie, **nút có con không có nghĩa nó không thể terminal**.

### 3.3. Không phải mọi nút có ký tự đều tạo ra một khóa

Nút `a` tại đầu `anh` không chứng minh `a` đã được lưu. Khi tìm chính xác `"a"`, phải trả `node.terminal` tại ký tự cuối cùng đã khớp, không được trả True chỉ vì đường ký tự tồn tại.

## 4. Sơ đồ TST với tập khóa nhỏ

Cho `K={"an","at","be"}` và lần lượt chèn `an`, `at`, `be`. Một TST hợp lệ có thể có hình:

```text
                   [a]                 vị trí 0
                  / | \
                ∅  |  [b]             b > a, cùng vị trí 0
                   |   |
                 eq|   |eq
                   v   v
                  [n*] [e*]            vị trí 1
                    \
                   right
                      \
                      [t*]             t > n, vẫn vị trí 1

* = terminal
```

Đường tìm `at`:

1. Tại nút `a`, ký tự đầu `a` khớp → đi `eq`, tăng chỉ số từ 0 lên 1.
2. Tại nút `n`, ký tự `t` lớn hơn `n` → đi `right`, **giữ nguyên chỉ số 1**.
3. Tại nút `t`, ký tự `t` khớp, đây là ký tự cuối.
4. `t.terminal=True` → khóa `at` tồn tại.

Đường tìm `be`:

1. Tại `a`, `b>a` → đi phải, chỉ số vẫn 0.
2. Tại `b`, ký tự `b` khớp → đi giữa, tăng lên 1.
3. Tại `e`, ký tự cuối khớp và terminal → tồn tại.

### 4.1. Chú ý khi vẽ hình

Các liên kết `left`/`right` của TST tạo **cây nhị phân tìm kiếm giữa các ký tự ở cùng vị trí**, trong khi `eq` tạo **tầng ký tự mới**.

Do đó một hình TST có thể trông giống cây nhị phân, nhưng một đường đi từ gốc tới lá không đồng nghĩa với việc **mọi nút trên đường đều đóng góp ký tự vào khóa**.

## 5. Bất biến biểu diễn của TST

Để phân tích đúng, cần tách hai quan hệ:

1. **Quan hệ BST ngang** ở **một vị trí ký tự**.
2. **Quan hệ tiền tố dọc** khi ký tự khớp và đi theo `eq`.

Cho nút `v` có ký tự `c`.

### 5.1. Bất biến tìm kiếm theo ký tự

Trong cây nhị phân của cùng vị trí:

- Mọi ký tự thuộc cây con `left(v)` nhỏ hơn `c`.
- Mọi ký tự thuộc cây con `right(v)` lớn hơn `c`.
- `eq(v)` **không** thuộc cùng cây BST ngang ấy: nó bắt đầu một tầng ký tự tiếp theo, với quan hệ so sánh mới.

Quan hệ nhỏ/lớn phải đúng cho **toàn bộ cây con trái/phải**, không chỉ nút con trực tiếp. Ví dụ nếu nút `m` có con trái `g`, một ký tự `z` không thể nằm ở nhánh phải của `g` mà vẫn thuộc toàn bộ nhánh trái của `m`.

### 5.2. Bất biến đường khớp

Mỗi khi một ký tự `word[i]` khớp `v.char`:

- Ký tự ấy được **tiêu thụ**.
- Nếu đây là ký tự cuối, `v.terminal` nói khóa có tồn tại không.
- Nếu còn ký tự, tra trong cây BST ngang bắt đầu ở `v.eq`.

Đi trái/phải chỉ giúp tìm ký tự phù hợp **trước khi tiêu thụ ký tự**.

### 5.3. Bất biến terminal

Với khóa không rỗng `w`:

\[
w\in K
\iff
\text{đi qua các nút khớp từng ký tự của }w
\text{ và nút khớp cuối có }terminal=True.
\]

Nếu các ký tự đều khớp nhưng terminal=False, `w` chỉ là tiền tố, chưa phải khóa hoàn chỉnh.

### 5.4. Đặc tả khóa rỗng

TST theo ký tự không có ký tự nào để tạo nút cho `""`. Ta giữ cờ độc lập:

```text
empty_terminal: Boolean
```

Nó chỉ cho biết `""` có thuộc Set không. `root` có thể là None nếu không có **khóa không rỗng**, ngay cả khi `empty_terminal=True`.

### 5.5. Không có node chia sẻ và chu trình

Mỗi nút có tối đa một cha trong cấu trúc liên kết, không có chu trình. Một ký tự có thể xuất hiện ở nhiều nút khác nhau nếu ở **những vị trí tiền tố khác nhau**; đó không phải vi phạm.

## 6. Bộ đếm tiền tố: vì sao không được gộp trái/phải?

Đặt `through_count(v)` là số khóa **đã khớp dãy ký tự tiền tố tới `v`, bao gồm `v.char`**.

Ta cần hai hàm khái niệm khác nhau:

- `M(v)`: số khóa khớp đi qua ký tự `v.char` ở nút `v`.
- `T(v)`: tổng số khóa nằm trong **toàn cây con TST** bắt đầu tại `v`, bao gồm các lựa chọn trái, giữa và phải.

Với `T(None)=0`:

\[
M(v)=\mathbf 1_{terminal(v)}+T(eq(v)).
\]

\[
T(v)=T(left(v))+M(v)+T(right(v)).
\]

Trong bài, ta lưu **`through_count(v)=M(v)`**, không lưu `T(v)`.

### 6.1. Ví dụ lý do phải phân biệt

Ở vị trí đầu tiên, giả sử cây có nút `a` và nhánh phải `b`, còn các khóa:

```text
an
ao
ba
ban
```

Nút `a` có thể có:

- `through_count(a)=2` vì chỉ `an,ao` bắt đầu bằng `a`.
- Toàn cây con có gốc `a` chứa cả `ba,ban` qua nhánh phải, tổng `T(a)=4`.

Nếu báo `countPrefix("a")=T(a)=4` thì sai: hai khóa `ba,ban` không mang tiền tố `a`.

### 6.2. Công thức cho một tiền tố

Nếu việc tìm `prefix=p` đã khớp hết ký tự cuối tại nút `v`:

\[
countPrefix(p)=throughCount(v).
\]

Không cần duyệt `eq` để đếm, vì bộ đếm đã được cập nhật khi thêm/xóa. Với `p=""`, kết quả là kích thước tổng `|K|`.

### 6.3. Quy tắc cập nhật đếm

Khi thêm một **khóa mới** `w`, chỉ tăng `through_count` ở các nút mà thuật toán **thật sự khớp** ký tự `w[i]`.

Những nút chỉ được lướt qua bằng `left` hoặc `right` **không được tăng**.

Khi xóa một khóa đang tồn tại, giảm chính các nút đã khớp trên đường từ ký tự đầu tới ký tự cuối. Khi chèn trùng hoặc xóa thiếu, **không thay đổi bộ đếm nào**.

## 7. Tìm chính xác một từ

Giả mã:

```text
CONTAINS(word):
    if word == "":
        return empty_terminal

    node = root
    i = 0

    while node != NONE:
        if word[i] < node.char:
            node = node.left             # giữ nguyên i

        else if word[i] > node.char:
            node = node.right            # giữ nguyên i

        else:
            # Đã khớp word[i].
            if i == len(word) - 1:
                return node.terminal
            i = i + 1
            node = node.eq

    return FALSE
```

### 7.1. Hai kiểu thất bại

Một từ có thể không tồn tại vì:

1. **Không có nút với ký tự cần tìm** trong cây BST ngang hiện tại.
2. Đi qua được mọi ký tự nhưng **nút cuối không terminal**.

Ví dụ lưu `anh` nhưng không lưu `an`. `contains("an")` có thể tìm đúng nút `n`, nhưng phải trả False.

### 7.2. Bất biến của vòng lặp

Ở mỗi lượt:

- `i` là vị trí ký tự **chưa được tiêu thụ**.
- Nếu đi trái/phải, `i` không thay đổi.
- Nếu ký tự khớp, tiền tố `word[:i+1]` đã được xác nhận.
- Nếu từ chưa hết, chuyển tới `eq` để xử lý `word[i+1]`.

Vì `left`/`right` tạo BST theo ký tự ở vị trí `i`, tìm đúng nút khớp là điều kiện cần để tiếp tục từ các ký tự phía sau.

## 8. Chèn từ: tạo nút ở đúng vị trí

Một thao tác `insert(word)` cần giải quyết hai công việc:

1. Tìm hoặc tạo nút mang **ký tự đang xét** trong cây BST ngang.
2. Khi khớp ký tự, chuyển tới **tầng tiếp theo qua `eq`** nếu còn ký tự.

### 8.1. Thiếu nút ở nhánh trái/phải

Nếu đang ở nút `m` mà ký tự cần tìm `c<m`:

- Đi `left`.
- Nếu `left=None`, tạo nút mới mang `c` ở **cùng vị trí ký tự**.
- **Không tăng `i`**.

Tương tự với nhánh phải khi `c>m`.

### 8.2. Khớp ký tự và còn phần đuôi

Nếu `c==node.char` nhưng còn ký tự phía sau:

- Ghi nhận nút vào danh sách **các nút đã khớp** để tăng bộ đếm nếu chèn thành công.
- Tăng `i`.
- Đi `eq`, tạo nút cho ký tự kế tiếp nếu chưa có.

### 8.3. Khớp ký tự cuối

Nếu đây là ký tự cuối:

- Nếu `terminal=True`, khóa đã có; trả False, **không tăng count**.
- Nếu `terminal=False`, đặt terminal=True, tăng số khóa và tăng bộ đếm ở mỗi nút **đã khớp** trên đường; trả True.

### 8.4. Ví dụ chèn `an` rồi `anh`

Sau `insert("an")`:

```text
[a] --eq--> [n*]
```

Sau `insert("anh")`:

```text
[a] --eq--> [n*] --eq--> [h*]
```

Nút `n` vẫn terminal vì `an` còn được lưu. Bộ đếm:

```text
through_count(a) = 2    # an, anh
through_count(n) = 2    # an, anh
through_count(h) = 1    # anh
```

### 8.5. Thêm khóa bắt đầu bằng ký tự khác

Sau đó chèn `ba`. Nếu nút đầu là `a`, ký tự `b` lớn hơn `a`, nên tạo nhánh `right` của `a` chứa `b`, rồi `b.eq` chứa `a`.

`through_count(a)` ở nút gốc vẫn là 2; khóa `ba` không bắt đầu bằng `a`.

## 9. Tìm và đếm theo tiền tố

TST có thể hỗ trợ tìm tiền tố bằng chính logic so ký tự của `contains`, nhưng **không đòi nút cuối terminal**.

### 9.1. Định vị ký tự cuối của tiền tố

Cho `p` không rỗng. Bắt đầu từ gốc, đi trái/phải nếu ký tự đang xét nhỏ/lớn hơn nút; đi giữa và tăng vị trí khi bằng, cho tới khi khớp ký tự cuối `p[-1]`.

Nếu không tìm được nút này, không có khóa nào mang `p` làm tiền tố.

Nếu tìm được nút `v`:

- `v.terminal=True`: chính `p` là một khóa.
- Các khóa dài hơn `p` nằm trong cây bắt đầu từ **`v.eq`**, không phải `v.left` hay `v.right`.
- Số khóa bắt đầu bằng `p` là **`v.through_count`**.

### 9.2. Ví dụ `K={an,ang,anh,ao,ba,ban}`

- `countPrefix("a")=4`.
- `countPrefix("an")=3`.
- `countPrefix("ang")=1`.
- `countPrefix("ao")=1`.
- `countPrefix("b")=2`.
- `countPrefix("ba")=2`.
- `countPrefix("ax")=0`.

### 9.3. Prefix rỗng

`""` là tiền tố của mọi từ, kể cả chính từ rỗng. Vì vậy:

\[
countPrefix("")=|K|.
\]

Để liệt kê mọi khóa, bắt đầu duyệt **toàn TST từ gốc**, đồng thời xuất `""` trước nếu `empty_terminal=True`.

### 9.4. Tại sao không đếm bằng `count(v.left)+count(v.right)`?

Nút cuối của tiền tố đã khớp `v.char`. Các nút ở `v.left`/`v.right` biểu diễn **ký tự khác tại chính vị trí vừa khớp**, nên không chia sẻ tiền tố. Chúng chỉ là phương án dự phòng trong lúc tìm ký tự.

Đếm prefix tại `v` phải chỉ xem **chính `v.terminal` và toàn bộ `v.eq`**, hoặc dùng `through_count(v)` đã lưu.

## 10. Liệt kê từ có tiền tố: thứ tự DFS nào là đúng?

Để liệt kê các khóa tăng theo code point, ta cần một thứ tự duyệt **đặc biệt**.

Tại một nút `v` ở cùng vị trí ký tự, thực hiện:

1. Duyệt **`left`** trước: các ký tự nhỏ hơn `v.char`.
2. Xử lý **chính `v.char`**:
   - Nối ký tự này vào đường khóa hiện tại.
   - Nếu `v.terminal`, phát khóa này.
   - Duyệt **`eq`** để lấy các khóa dài hơn có ký tự đầu giống nhau.
3. Bỏ ký tự `v.char` khỏi đường hiện tại.
4. Duyệt **`right`**: các ký tự lớn hơn.

Có thể viết ký hiệu:

```text
TRAVERSE(v, prefix):
    if v == NONE:
        return

    TRAVERSE(v.left, prefix)

    current = prefix + v.char
    if v.terminal:
        EMIT(current)
    TRAVERSE(v.eq, current)

    TRAVERSE(v.right, prefix)
```

Lưu ý `left` và `right` nhận **prefix cũ**, còn `eq` nhận **prefix + v.char`.

### 10.1. Tại sao phải phát terminal trước nhánh giữa?

Theo thứ tự từ điển, `"an" < "ang"` vì `an` là tiền tố của `ang`. Do đó nếu nút `n` là terminal thì phải phát `an` **trước khi** đi theo `n.eq` đến các ký tự tiếp theo.

Nếu chỉ duyệt `eq` rồi phát terminal, thứ tự sẽ không còn đúng.

### 10.2. Tại sao không nối ký tự khi đi trái/phải?

`v.left` và `v.right` đang tìm **lựa chọn khác cho vị trí hiện tại**. Nếu nối `v.char` trước khi duyệt chúng, có thể tạo ra những chuỗi sai chưa từng được chèn.

### 10.3. Liệt kê theo tiền tố không được đi cả `v.left` và `v.right`

Nếu đã khớp toàn bộ tiền tố tại nút `v`, các từ có tiền tố ấy là:

- Chính `prefix` nếu `v.terminal=True`.
- Các khóa trong **`v.eq`** gắn thêm ký tự phía sau.

Đi vào `v.left` hoặc `v.right` ở bước này là đi sang **ký tự cuối khác** với ký tự cuối của tiền tố, nên sẽ trả những từ không khớp.

### 10.4. DFS đệ quy và lặp

Giả mã đệ quy dễ đọc, nhưng trong Python, một cây bị lệch mạnh hoặc một từ rất dài có thể vượt giới hạn đệ quy.

Phần cài đặt sẽ dùng **Stack sự kiện vào/ra** để duy trì danh sách ký tự đường đi và duyệt từ điển mà không phải gọi đệ quy sâu.

## 11. Xóa từ: thay đổi terminal và dọn nút an toàn

Một phép `delete(word)` phải:

1. Tìm đúng **nút terminal** của khóa.
2. Nếu không tồn tại, trả False và **không sửa dữ liệu**.
3. Nếu tồn tại, đặt terminal=False.
4. Giảm `through_count` của các nút đã **khớp ký tự** trên đường.
5. Xóa những nút không còn terminal và **không còn bất kỳ liên kết con nào**.

### 11.1. Ví dụ xóa từ là tiền tố của từ khác

Đang có `an` và `anh`:

```text
[a] --eq--> [n*] --eq--> [h*]
```

Xóa `an`:

- `n.terminal=False`.
- Giữ `n.eq` vì `anh` vẫn tồn tại.
- Giảm `through_count(a)` và `through_count(n)` từ 2 xuống 1.

Sau xóa, `contains("an")=False` nhưng `countPrefix("an")=1` và `matches("an")=["anh"]`.

### 11.2. Ví dụ xóa một lá ở cuối nhánh

Nếu từ `anh` là khóa duy nhất sử dụng nút `h` ở cuối đường, sau xóa nút `h`:

- Không terminal.
- `left`, `eq`, `right` đều là None.

Có thể gỡ nó khỏi liên kết cha. Nếu cha sau đó cũng trở thành nút rỗng, tiếp tục dọn ngược.

### 11.3. Nút không terminal nhưng còn nhánh ngang

Đây là điểm khác với trie thông thường. Giả sử hai khóa một ký tự `a` và `b` được chèn theo thứ tự `a`, rồi `b`:

```text
[a*] --right--> [b*]
```

Xóa `a` khiến nút `a` không terminal, nhưng vẫn giữ nhánh phải tới `b`. Không được xóa `a` đơn giản bằng cách đặt liên kết tới nó thành None, vì sẽ làm mất `b`.

Có thể thực hiện **thuật toán xóa nút BST** để thay thế `a` bằng một nút ngang phù hợp, nhưng cách đó có nhiều tình huống hơn. Bản cài đặt giáo dục chọn cách **chỉ loại nút đã thật sự không còn con**.

### 11.4. Hệ quả của cách dọn đơn giản

Sau nhiều lần chèn/xóa, có thể còn **nút trung gian theo nhánh trái/phải** mà `through_count=0`, bản thân nó không đóng góp khóa nào nhưng vẫn cần làm nút tìm đường tới ký tự khác.

Cấu trúc vẫn **đúng về tập khóa**, song có thể giữ nhiều nút dư. Muốn nén/giảm bộ nhớ hơn cần:

- Xóa nút ngang theo quy tắc BST (chọn con thay thế đúng).
- Cân bằng lại các cây BST ngang, hoặc
- Xây lại TST từ tập khóa còn sống khi phù hợp.

**Không được** gắn nhãn “sau mọi lần xóa vẫn chỉ dùng O(tổng độ dài các khóa hiện còn)” cho bản chỉ dọn lá: những nút theo **lịch sử cập nhật** có thể vẫn tồn tại.

## 12. Cài đặt Python hoàn chỉnh: lớp nút và TST dạng Set

Ta sẽ xây một lớp `TernarySearchTree` với những API:

```text
insert(word)                   -> bool
contains(word)                 -> bool
delete(word)                   -> bool
count_prefix(prefix)           -> int
has_key_with_prefix(prefix)    -> bool
iter_words(prefix="")          -> generator[str]
autocomplete(prefix="",limit)  -> list[str]
len(tree)                      -> int
```

Điểm thiết kế:

- Khóa là `str`, mỗi đơn vị so sánh là **Unicode code point**.
- Khóa rỗng được lưu qua `empty_terminal`, không tạo nút `char=""`.
- `through_count` đếm khóa qua **nhánh khớp ký tự**, không bao gồm hai nhánh ngang.
- Duyệt từ điển bằng Stack lặp, giữ `path` dạng danh sách để tránh nối chuỗi tại mọi nút.
- Không tự cân bằng cây ngang; xóa chỉ dọn các nút thật sự không còn liên kết.

### 12.1. Nút chứa ký tự và ba con

```python
from itertools import islice


class TSTNode:
    __slots__ = (
        "char", "left", "eq", "right",
        "terminal", "through_count",
    )

    def __init__(self, char):
        self.char = char
        self.left = None
        self.eq = None
        self.right = None
        self.terminal = False

        # Số khóa khớp đầy đủ qua ký tự của node;
        # không tính các khóa thuộc left/right.
        self.through_count = 0
```

### 12.2. Khởi tạo và hàm định vị ký tự cuối

Các phương thức sau được đặt trong **cùng một lớp**:

```python
class TernarySearchTree:
    def __init__(self):
        self.root = None
        self.empty_terminal = False
        self._size = 0

    @staticmethod
    def _validate_text(text):
        if not isinstance(text, str):
            raise TypeError("word và prefix phải là str")

    @staticmethod
    def _validate_limit(limit):
        if limit is not None and (
            type(limit) is not int or limit < 0
        ):
            raise ValueError("limit phải là None hoặc int >= 0")

    def __len__(self):
        return self._size

    def _find_last_char_node(self, text):
        """Tìm nút khớp ký tự cuối của text không rỗng."""
        if text == "":
            return None

        node = self.root
        i = 0

        while node is not None:
            ch = text[i]

            if ch < node.char:
                node = node.left
            elif ch > node.char:
                node = node.right
            else:
                if i == len(text) - 1:
                    return node

                i += 1
                node = node.eq

        return None

    def contains(self, word):
        self._validate_text(word)

        if word == "":
            return self.empty_terminal

        node = self._find_last_char_node(word)
        return node is not None and node.terminal
```

Hàm `_find_last_char_node` chỉ tăng `i` trong nhánh ký tự khớp; khi đi trái/phải, vẫn tra cùng ký tự `text[i]`.

### 12.3. Thêm một khóa mới

Bổ sung vào lớp:

```python
    def insert(self, word):
        """True nếu thêm khóa mới; False nếu khóa đã có."""
        self._validate_text(word)

        if word == "":
            if self.empty_terminal:
                return False

            self.empty_terminal = True
            self._size += 1
            return True

        if self.root is None:
            self.root = TSTNode(word[0])

        node = self.root
        i = 0
        matched = []  # Chỉ các nút đã khớp một ký tự.

        while True:
            ch = word[i]

            if ch < node.char:
                if node.left is None:
                    node.left = TSTNode(ch)
                node = node.left

            elif ch > node.char:
                if node.right is None:
                    node.right = TSTNode(ch)
                node = node.right

            else:
                matched.append(node)

                if i == len(word) - 1:
                    if node.terminal:
                        return False

                    node.terminal = True
                    self._size += 1

                    # Từ mới đi qua đúng các nút matched.
                    for item in matched:
                        item.through_count += 1

                    return True

                i += 1

                if node.eq is None:
                    node.eq = TSTNode(word[i])

                node = node.eq
```

**Tính đúng của `through_count`:** ta chỉ thêm nút vào `matched` khi ký tự hiện tại đúng bằng `node.char`. Khi chèn thành công, mọi prefix tương ứng với đường khớp có thêm đúng một khóa; khi chèn trùng, không tăng lần nào.

### 12.4. Đếm và kiểm tra có từ theo tiền tố

```python
    def count_prefix(self, prefix):
        self._validate_text(prefix)

        if prefix == "":
            return self._size

        node = self._find_last_char_node(prefix)
        return 0 if node is None else node.through_count

    def has_key_with_prefix(self, prefix):
        return self.count_prefix(prefix) > 0
```

Ở đây `node.through_count` không cần cộng `left/right`. Nếu nút vẫn tồn tại nhưng `through_count=0` sau một số phép xóa, kết quả tiền tố là 0, đúng với tập khóa đang sống.

## 13. DFS lặp để liệt kê khóa đúng thứ tự

Ta dùng một Stack chứa các **sự kiện** thay vì đệ quy:

- `visit`: thăm một nút TST ở tầng ký tự hiện tại.
- `self`: đã xử lý nhánh trái; thêm ký tự nút, phát terminal và duyệt nhánh giữa.
- `pop`: đã xử lý nhánh giữa; bỏ ký tự vừa thêm, rồi để Stack tiếp tục nhánh phải.

Thứ tự logic tại mỗi nút vẫn là:

```text
left -> char terminal -> eq -> right
```

### 13.1. Mã generator

Bổ sung các phương thức vào `TernarySearchTree`:

```python
    @staticmethod
    def _walk_level(level_root, initial_path):
        """DFS theo ký tự tăng, trả từng khóa.

        level_root là gốc của các lựa chọn ký tự
        ở cùng một vị trí (bao gồm left/right).
        """
        path = list(initial_path)
        stack = [("visit", level_root)]

        while stack:
            kind, node = stack.pop()

            if kind == "visit":
                if node is None:
                    continue

                # Stack LIFO: trái trước, rồi chính node,
                # rồi giữa được lập lịch ở "self",
                # cuối cùng mới tới phải.
                stack.append(("visit", node.right))
                stack.append(("self", node))
                stack.append(("visit", node.left))

            elif kind == "self":
                path.append(node.char)

                if node.terminal:
                    yield "".join(path)

                # Phải bỏ ký tự TRƯỚC khi thăm right.
                stack.append(("pop", None))
                stack.append(("visit", node.eq))

            else:
                # kind == "pop"
                path.pop()

    def iter_words(self, prefix=""):
        """Generator khóa bắt đầu bằng prefix, có thứ tự."""
        self._validate_text(prefix)

        if prefix == "":
            if self.empty_terminal:
                yield ""

            yield from self._walk_level(self.root, [])
            return

        node = self._find_last_char_node(prefix)

        if node is None or node.through_count == 0:
            return

        # Khóa prefix có thể là khóa hoàn chỉnh.
        if node.terminal:
            yield prefix

        # Chỉ phần eq mới giữ nguyên prefix này.
        yield from self._walk_level(node.eq, list(prefix))

    def autocomplete(self, prefix="", limit=None):
        """Lấy tối đa limit từ, theo code point Unicode."""
        self._validate_text(prefix)
        self._validate_limit(limit)

        if limit == 0:
            return []

        values = self.iter_words(prefix)

        if limit is None:
            return list(values)

        return list(islice(values, limit))
```

### 13.2. Tại sao dùng hai sự kiện `self` và `pop`?

Tại nút `n`, muốn thăm các từ có ký tự thứ hai nhỏ hơn `n` trước, sau đó các từ bắt đầu bằng `an`, rồi những từ có ký tự thứ hai lớn hơn `n`.

Khi xử lý chính `n`, ta thêm `n` vào `path` để:

- Phát `an` nếu terminal.
- Đi `eq` để phát `ang`, `anh` nếu chúng tồn tại.

Sau khi duyệt xong `eq`, ta **bỏ `n`** rồi mới thăm `right` để xử lý các khóa có ký tự thứ hai khác, ví dụ `ao`.

Nếu không dùng sự kiện `pop` mà giữ `n` khi thăm `right`, các chuỗi phát ra sẽ bị thêm nhầm ký tự.

### 13.3. Vì sao dùng `join` khi terminal?

Trong Python, `str` bất biến. Nếu dùng `prefix+ch` tại từng cạnh và mỗi lần tạo chuỗi mới, một đường dài có thể sinh nhiều bản sao tiền tố trung gian.

Ở mã trên, `path.append` và `path.pop` cập nhật danh sách ký tự. Ta tạo `"".join(path)` **chỉ khi phát một khóa**. Nếu cần xuất `C` khóa có tổng chiều dài `Z` ký tự, riêng việc tạo nội dung đầu ra đã có cận dưới:

\[
\Omega(Z).
\]

Do đó, một truy vấn autocomplete trả hàng nghìn khóa dài không thể có tổng thời gian chỉ O(độ dài tiền tố).

### 13.4. Kết quả giới hạn

`autocomplete("a",limit=2)` lấy đúng hai khóa đầu theo thứ tự. Generator dừng khi `islice` không yêu cầu thêm kết quả.

Tuy nhiên, `limit=2` **không tự bảo đảm O(2)**: phải tìm tiền tố, có thể đi qua nhiều nút ngang/dọc, rồi mới phát được hai nút terminal.

## 14. Xóa từ và dọn nút rỗng

Cài đặt `delete` dùng một danh sách `path` ghi **mọi nút đã đi qua**, kèm cha và tên liên kết từ cha tới nó. Đồng thời ghi riêng `matched` là các nút đã **khớp ký tự của từ**.

Điểm khác nhau:

- `path` dùng để dọn các nút rỗng từ dưới lên.
- `matched` dùng để giảm đúng bộ đếm tiền tố.

### 14.1. Mã xóa

Bổ sung vào `TernarySearchTree`:

```python
    def delete(self, word):
        """True nếu xóa khóa; False nếu khóa thiếu."""
        self._validate_text(word)

        if word == "":
            if not self.empty_terminal:
                return False

            self.empty_terminal = False
            self._size -= 1
            return True

        i = 0
        parent = self
        link = "root"
        node = self.root

        path = []       # (parent, link, current_node)
        matched = []    # Các nút đã khớp ký tự.

        while node is not None:
            path.append((parent, link, node))
            ch = word[i]

            if ch < node.char:
                parent, link = node, "left"
                node = node.left

            elif ch > node.char:
                parent, link = node, "right"
                node = node.right

            else:
                matched.append(node)

                if i == len(word) - 1:
                    break

                i += 1
                parent, link = node, "eq"
                node = node.eq

        if node is None or not node.terminal:
            return False

        # Từ tồn tại: sửa terminal và bộ đếm.
        node.terminal = False
        self._size -= 1

        for item in matched:
            item.through_count -= 1

        # Dọn nút không terminal và KHÔNG có con.
        for prev, attr, current in reversed(path):
            if (
                current.terminal
                or current.left is not None
                or current.eq is not None
                or current.right is not None
            ):
                break

            setattr(prev, attr, None)

        return True
```

### 14.2. Vì sao `setattr(prev,attr,None)` là an toàn ở đây?

Chỉ khi một nút:

- Không terminal.
- Không có `left`, `eq` hay `right`.

thì không có khóa sống nào còn cần đến nút đó hoặc các nhánh của nó. Ta gỡ nó khỏi liên kết của cha. Nếu cha cũng trở thành nút rỗng, tiếp tục gỡ.

Nếu nút còn ít nhất một con, **dừng dọn**. Xóa cả nút ấy mà không tái nối con có thể làm mất một nhóm khóa khác.

### 14.3. Những nút còn sống nhưng `through_count=0`

Giả sử chèn lần lượt `"a"`, `"b"`, `"c"`. Gốc có thể là chuỗi:

```text
[a*] --right--> [b*] --right--> [c*]
```

Sau khi xóa `a` và `b`, các nút `a`, `b` vẫn có nhánh phải nên không bị gỡ bằng cách dọn đơn giản, dù `through_count(a)=through_count(b)=0`.

`contains("c")` và `autocomplete("")` vẫn đúng. Nhưng muốn tìm `c`, chương trình phải đi qua các nút `a` và `b` đã hết khóa.

**Đây là một đánh đổi có chủ ý của mã minh họa.** Nó giữ thao tác xóa dễ kiểm chứng, nhưng không hứa bộ nhớ hay độ sâu còn tối ưu sau lịch sử cập nhật dài.

## 15. Kiểm thử chức năng: từ khóa ngắn, dài và tiền tố

Sau khi ghép các phương thức `contains`, `insert`, `delete`, `count_prefix`, `iter_words` và `autocomplete` vào **một lớp `TernarySearchTree`**, chạy các đoạn sau.

### 15.1. Chèn và sắp từ điển

```python
tree = TernarySearchTree()

words = [
    "an", "anh", "ang", "ao",
    "ba", "ban", "bao", "car", "cat",
]

for word in words:
    assert tree.insert(word)

assert len(tree) == 9
assert not tree.insert("an")
assert len(tree) == 9

assert tree.autocomplete("") == [
    "an", "ang", "anh", "ao",
    "ba", "ban", "bao", "car", "cat",
]

assert tree.contains("an")
assert tree.contains("ang")
assert tree.contains("car")
assert not tree.contains("a")
assert not tree.contains("c")
assert not tree.contains("can")
```

### 15.2. Truy vấn theo tiền tố

```python
assert tree.count_prefix("") == 9
assert tree.count_prefix("a") == 4
assert tree.count_prefix("an") == 3
assert tree.count_prefix("ang") == 1
assert tree.count_prefix("ao") == 1
assert tree.count_prefix("b") == 3
assert tree.count_prefix("ba") == 3
assert tree.count_prefix("car") == 1
assert tree.count_prefix("ca") == 2
assert tree.count_prefix("ax") == 0

assert tree.has_key_with_prefix("an")
assert not tree.has_key_with_prefix("az")

assert tree.autocomplete("an") == ["an", "ang", "anh"]
assert tree.autocomplete("ba") == ["ba", "ban", "bao"]
assert tree.autocomplete("ca") == ["car", "cat"]
assert tree.autocomplete("an", limit=2) == ["an", "ang"]
assert tree.autocomplete("a", limit=0) == []
assert tree.autocomplete("missing") == []
```

### 15.3. Xóa từ là tiền tố của từ khác

```python
assert tree.delete("an")
assert not tree.contains("an")
assert tree.contains("ang")
assert tree.contains("anh")
assert tree.count_prefix("an") == 2
assert tree.autocomplete("an") == ["ang", "anh"]

assert tree.delete("ang")
assert tree.count_prefix("an") == 1
assert tree.autocomplete("an") == ["anh"]

assert tree.delete("anh")
assert tree.count_prefix("an") == 0
assert tree.autocomplete("an") == []
assert tree.contains("ao")
assert tree.count_prefix("a") == 1

assert not tree.delete("an")
assert len(tree) == 6
```

Sau khi xóa ba khóa `an,ang,anh`, còn 6 khóa: `ao,ba,ban,bao,car,cat`. `through_count` của các nút gắn với tiền tố `an` phải bằng 0 hoặc nút đã bị dọn; nhưng nhánh `ao` vẫn phải còn.

### 15.4. Xóa các từ còn lại

```python
for word in ["ao", "ba", "ban", "bao", "car", "cat"]:
    assert tree.delete(word)

assert len(tree) == 0
assert tree.autocomplete("") == []
assert tree.count_prefix("") == 0
assert not tree.contains("cat")
assert not tree.delete("cat")
```

Với mã dọn đơn giản, sau khi xóa **toàn bộ** khóa không rỗng, các nút chỉ còn làm trung gian không thể tồn tại mãi nếu mọi nhánh con của chúng cũng đã bị dọn: cây cuối cùng trở về `root=None`. Nhưng trong giai đoạn còn **một số** khóa sống, các nút ngang dư từ lịch sử có thể tồn tại.

## 16. Khóa rỗng và giới hạn kết quả

Khóa rỗng không có nút ký tự riêng. Nó được quản lý bằng `empty_terminal`.

### 16.1. Ví dụ

```python
tree = TernarySearchTree()

assert tree.autocomplete("") == []
assert tree.count_prefix("") == 0
assert not tree.contains("")

assert tree.insert("")
assert tree.contains("")
assert len(tree) == 1
assert tree.autocomplete("") == [""]
assert tree.count_prefix("") == 1

assert tree.insert("a")
assert tree.insert("an")
assert tree.autocomplete("") == ["", "a", "an"]
assert tree.autocomplete("", limit=2) == ["", "a"]
assert tree.autocomplete("a") == ["a", "an"]
assert tree.count_prefix("a") == 2

assert tree.delete("")
assert not tree.contains("")
assert tree.autocomplete("") == ["a", "an"]
assert tree.count_prefix("") == 2
```

### 16.2. Kiểm tra giới hạn

```python
assert tree.autocomplete("a", limit=0) == []
assert tree.autocomplete("a", limit=100) == ["a", "an"]

try:
    tree.autocomplete("a", limit=-1)
except ValueError:
    pass
else:
    raise AssertionError("limit âm phải bị từ chối")

try:
    tree.autocomplete("a", limit=True)
except ValueError:
    pass
else:
    raise AssertionError("bool không được coi là limit int")
```

Trong Python, `bool` là lớp con của `int`. Vì vậy mã dùng `type(limit) is int` thay vì `isinstance(limit,int)` để không diễn giải `True` thành 1 gợi ý một cách ngầm định.

### 16.3. Khóa rỗng có phải một nút terminal ở gốc?

Trong biến thể hiện tại, **không**. Gốc hoặc là None, hoặc là một nút mang một ký tự thực. Cờ `empty_terminal` thuộc đối tượng cây tổng thể.

Một biến thể khác có thể tạo nút gốc giả với `terminal` và một cây TST bên dưới, nhưng không được trộn hai mô hình mà không điều chỉnh các phép tìm và đếm.

## 17. Kiểm tra bất biến cấu trúc và bộ đếm

Kiểm thử kết quả API vẫn có thể bỏ sót lỗi bên trong. Chẳng hạn, nếu lỡ tăng `through_count` trên nhánh phải, `contains` có thể đúng nhưng `count_prefix` sai.

Ta sẽ viết một bộ kiểm tra toàn TST bằng **DFS hậu tự lặp** để đối chiếu hai đại lượng:

\[
M(v)=\mathbf 1_{terminal(v)}+T(eq(v))
\]

và

\[
T(v)=T(left(v))+M(v)+T(right(v)).
\]

### 17.1. Validator

```python
def validate_tst(tree):
    totals = {}
    seen = set()
    stack = []

    if tree.root is not None:
        # (node, expanded, lower_char, upper_char)
        stack.append((tree.root, False, None, None))

    while stack:
        node, expanded, lower, upper = stack.pop()

        if not expanded:
            assert id(node) not in seen
            seen.add(id(node))

            assert isinstance(node.char, str)
            assert len(node.char) == 1

            # BST ngang: mọi ký tự ở left nhỏ hơn,
            # mọi ký tự ở right lớn hơn ký tự nút.
            if lower is not None:
                assert lower < node.char
            if upper is not None:
                assert node.char < upper

            stack.append((node, True, lower, upper))

            if node.left is not None:
                stack.append((
                    node.left, False, lower, node.char
                ))

            if node.eq is not None:
                # Tầng ký tự mới, reset giới hạn BST.
                stack.append((node.eq, False, None, None))

            if node.right is not None:
                stack.append((
                    node.right, False, node.char, upper
                ))

        else:
            left_count = (
                totals[id(node.left)]
                if node.left is not None else 0
            )
            eq_count = (
                totals[id(node.eq)]
                if node.eq is not None else 0
            )
            right_count = (
                totals[id(node.right)]
                if node.right is not None else 0
            )

            # Chỉ terminal và eq có cùng tiền tố
            # đến char tại node.
            matched_count = int(node.terminal) + eq_count
            assert node.through_count == matched_count

            # left/right là những ký tự thay thế ở
            # cùng vị trí, thuộc toàn cây ngang.
            total = left_count + matched_count + right_count
            assert total > 0
            totals[id(node)] = total

    live_nonempty = (
        totals[id(tree.root)]
        if tree.root is not None else 0
    )
    expected_size = live_nonempty + int(tree.empty_terminal)
    assert len(tree) == expected_size
```

### 17.2. Vì sao giới hạn BST của nhánh giữa được reset?

Nếu nút `m` ở vị trí `i` có `eq` dẫn sang vị trí `i+1`, ký tự tiếp theo của khóa **không cần** lớn hơn hay nhỏ hơn `m`.

Ví dụ từ `ma` có ký tự đầu `m`, ký tự thứ hai `a`; `a<m` là hoàn toàn hợp lệ. Vì vậy validator chỉ truyền ràng buộc `lower/upper` xuống các nhánh **trái/phải** cùng tầng, và **reset** khi đi `eq`.

### 17.3. Một nút có `through_count=0` chưa chắc vô hiệu

Sau xóa, nút `a` có thể đã hết khóa bắt đầu bằng `a` nhưng vẫn có nhánh `right` tới từ bắt đầu bằng `b`. Khi đó:

- `through_count(a)=0` là hợp lệ.
- `T(a)>0` vì còn khóa trong nhánh phải.

Do đó validator **không** yêu cầu `through_count>0` ở mọi nút. Nó chỉ yêu cầu **toàn cây con T(v) có ít nhất một khóa sống** cho mỗi nút còn được giữ.

## 18. Đối chiếu với tập tham chiếu qua vết cập nhật

Một `set[str]` của Python rất thích hợp làm mô hình logic để kiểm thử TST. Bộ kiểm tra dùng `startswith` và `sorted`, độc lập với ba nhánh của cây.

### 18.1. Hàm kiểm tra

```python
def check_against_set(tree, reference, prefixes):
    assert len(tree) == len(reference)
    assert tree.autocomplete("") == sorted(reference)

    for prefix in prefixes:
        expected = sorted(
            word
            for word in reference
            if word.startswith(prefix)
        )
        assert tree.autocomplete(prefix) == expected
        assert tree.count_prefix(prefix) == len(expected)
        assert tree.has_key_with_prefix(prefix) == bool(expected)

    validate_tst(tree)
```

### 18.2. Thử nhiều trường hợp chèn và xóa

```python
tree = TernarySearchTree()
reference = set()
prefixes = [
    "", "a", "an", "ang", "b", "ba",
    "c", "ca", "x", "zz",
]

operations = [
    ("insert", "an"),
    ("insert", "anh"),
    ("insert", "ang"),
    ("insert", "ao"),
    ("insert", "ba"),
    ("insert", "ban"),
    ("insert", "bao"),
    ("insert", ""),
    ("insert", "an"),    # Trùng.
    ("delete", "ax"),    # Thiếu.
    ("delete", "an"),
    ("delete", "anh"),
    ("insert", "car"),
    ("insert", "cat"),
    ("delete", "ba"),
    ("delete", ""),
    ("delete", "ang"),
    ("delete", "ao"),
    ("delete", "ban"),
    ("delete", "bao"),
    ("delete", "car"),
    ("delete", "cat"),
]

for action, word in operations:
    if action == "insert":
        expected_change = word not in reference
        actual_change = tree.insert(word)
        reference.add(word)
    else:
        expected_change = word in reference
        actual_change = tree.delete(word)
        reference.discard(word)

    assert actual_change == expected_change
    check_against_set(tree, reference, prefixes)
```

Các phép quét `reference` và validator có thể tốn O(tổng kích thước dữ liệu) mỗi vòng. Đó là chi phí **bộ kiểm thử trên ví dụ nhỏ**, không phải việc cần chạy ở môi trường phục vụ hàng triệu yêu cầu.

### 18.3. Thử thứ tự chèn khác nhau

TST không tự cân bằng, nên nên thử:

- Chèn từ theo thứ tự tăng.
- Chèn từ theo thứ tự giảm.
- Chèn theo một thứ tự trộn.
- Xóa từ ở đầu/giữa/cuối một chuỗi nhánh phải dài.
- Chèn lại một từ đã xóa.

Kết quả `contains`, `count_prefix` và `autocomplete` phải như nhau đối với **cùng một tập khóa**, dù hình dạng và chi phí tìm kiếm khác nhau.

## 19. Phân tích thời gian: không thể luôn gọi TST là O(L)

Đặt:

- `L`: số ký tự của từ được tìm/chèn/xóa.
- `P`: số ký tự tiền tố truy vấn.
- `σ`: số ký tự có thể xuất hiện tại một vị trí.
- `h_i`: số nút ký tự cần so sánh trong **BST ngang** ở vị trí `i` trên đường tìm.
- `N`: tổng số nút TST hiện được giữ trong bộ nhớ.
- `V`: số nút TST được duyệt khi liệt kê kết quả.
- `C`: số khóa thực sự được phát ra.
- `Z`: tổng độ dài các chuỗi kết quả được tạo.

### 19.1. Tìm một từ

Tại mỗi vị trí `i`:

1. Chạy tìm trong **BST ngang** của các ký tự cạnh tranh tại vị trí ấy.
2. Khi gặp ký tự khớp, đi `eq` và tăng `i`.

Bỏ qua chi phí chuẩn hóa ký tự bên ngoài API, thời gian có dạng:

\[
T_{\mathrm{contains}}
=O\left(1+\sum_{i\text{ đã xét}}h_i\right).
\]

Cộng tổng `h_i` là điều cần thiết. Không thể giả định mỗi ký tự của từ chỉ cần một phép so sánh vì tại vị trí đó có thể phải đi nhiều lần trái/phải.

### 19.2. Nếu các BST ngang cân bằng

Nếu các BST ngang có chiều cao O(log(σ+1)), và truy vấn đọc tối đa `L` ký tự:

\[
T_{\mathrm{contains}}=O(L\log(\sigma+1)).
\]

Nếu `σ` là hằng số nhỏ cố định, biểu thức này rút về O(L). Nhưng giả định **cân bằng** không tự đúng với cấu trúc chèn đơn giản trong bài.

### 19.3. Trường hợp xấu khi bị lệch

Nếu chèn các từ một ký tự theo thứ tự:

```text
"a", "b", "c", "d", ...
```

ta có thể thu một chuỗi `right` dài:

```text
[a] --right--> [b] --right--> [c] --right--> [d] ...
```

Tìm ký tự cuối có thể cần đi qua tất cả các nút ngang, dù `L=1`.

Với `N` nút trong toàn cấu trúc, một truy vấn tìm đi theo một đường đơn nên có chặn thô O(N+1) phép thăm nút trong trường hợp xấu. Có thể diễn đạt bằng O(Σ h_i) để thấy nguyên nhân của chi phí.

### 19.4. Chèn và xóa

Trong mã:

- Chèn đi theo đường tìm, tạo các nút chưa có, rồi tăng `through_count` ở tối đa `L` nút đã khớp.
- Xóa đi theo đường tìm, lưu `path`, giảm bộ đếm và dọn ngược tối đa số nút đã thăm.

Do đó:

\[
T_{\mathrm{insert}},T_{\mathrm{delete}}
=O\left(1+\sum_i h_i+L\right)
\]

trong mô hình thao tác nút/ký tự O(1). Vì mỗi ký tự thực sự khớp phải qua ít nhất một nút, biểu thức thường được giản lược thành O(1+Σ h_i) cho đầu vào không rỗng.

Không có bước cân bằng lại, không có xoay BST hoặc nén nhãn cạnh trong bản cài đặt này.

### 19.5. Đếm tiền tố

Nhờ `through_count`:

\[
T_{\mathrm{countPrefix}}
=O\left(1+\sum_{i<P}h_i\right).
\]

Nếu tìm tiền tố thất bại, có thể dừng sớm. Nếu thành công, đọc một bộ đếm O(1), **không cần duyệt mọi khóa phù hợp**.

### 19.6. Liệt kê có chi phí theo đầu ra

Sau khi tìm tiền tố, thuật toán DFS:

- Thăm `V` nút (bao gồm các nút ngang thay thế ở các tầng phía dưới).
- Phát `C` khóa.
- Tạo chuỗi có tổng chiều dài `Z` bằng `join`.

Một chặn trên hữu ích:

\[
T_{\mathrm{autocomplete}}
=O\left(
1+\sum_{i<P}h_i+V+Z
\right).
\]

Nếu `limit=k`, `V` là số nút **thực tế được thăm trước khi đủ `k` khóa**, không nhất thiết là toàn bộ cây con. Tuy nhiên, số nút phải đi qua để tìm kết quả có thể lớn hơn `k` rất nhiều.

### 19.7. Bộ nhớ tạm của DFS

- `path` chứa các ký tự trên một đường khớp: O(H), với `H` là chiều dài khóa lớn nhất trên đường duyệt.
- Stack sự kiện giữ nhánh chờ xử lý: có chặn tổng quát O(V) đối tượng sự kiện trong lời gọi.
- Nếu `autocomplete` trả danh sách chuỗi, bộ nhớ **đầu ra** phụ thuộc `Z`.
- `iter_words` là generator nên không phải giữ toàn bộ danh sách kết quả cùng lúc.

DFS lặp tránh giới hạn đệ quy, nhưng không có nghĩa nó dùng **O(1)** bộ nhớ.

## 20. Chi phí bộ nhớ và tác động của thứ tự chèn

### 20.1. Số nút theo các tiền tố phân biệt khi xây mới

Mỗi nút TST tương ứng với **một lựa chọn ký tự tại một vị trí** sau một chuỗi ký tự đã khớp. Trong một cây được xây bằng việc chèn khóa và chưa bị lịch sử xóa làm giữ nút ngang dư, có thể xem số nút bị chặn bởi số **tiền tố không rỗng phân biệt** của các khóa đã được chèn.

Gọi `S=\sum_{w\in K}|w|` là tổng độ dài các khóa đang có. Với cây mới xây từ đúng tập khóa `K`:

\[
N\le S.
\]

TST chia sẻ những tiền tố giống nhau, nên thực tế có thể nhỏ hơn nhiều so với `S`.

### 20.2. Các thành phần trong một nút

Mỗi nút trong bản minh họa giữ:

- Một ký tự `char`.
- Ba tham chiếu `left`, `eq`, `right`.
- Một cờ `terminal`.
- Một số nguyên `through_count`.
- Overhead của đối tượng Python và bộ cấp phát.

Vì vậy, khi ước lượng RAM thực tế, **không** chỉ lấy số ký tự của văn bản. Cần tính cả kích thước đối tượng, con trỏ và bộ đếm.

### 20.3. Không cấp mảng σ ô cho mỗi nút

Một trie dùng mảng con cố định cho bảng chữ cái kích thước `σ` có thể tốn O(σ) ô con trỏ **mỗi nút**, kể cả khi chỉ có một vài nhánh.

TST dùng tối đa **ba** liên kết/nút. Điều này có thể tiết kiệm bộ nhớ khi bảng ký hiệu lớn hoặc cấu trúc thưa, nhưng số nút, độ sâu và overhead Python vẫn ảnh hưởng kết quả.

### 20.4. So với trie Hash Map con

Trie với dictionary con có thể có một nút cho mỗi tiền tố và chỉ lưu các cạnh hiện diện. Nó thường đạt tra cạnh O(1) **kỳ vọng** nếu phép hash phù hợp, nhưng mỗi dictionary có overhead riêng.

TST tránh dictionary ở mỗi nút, đổi lại phải tìm ký tự bằng các nhánh BST ngang, có nguy cơ bị lệch. **Không có phương án nào luôn ít byte hoặc luôn nhanh hơn** trên mọi tập khóa và runtime.

### 20.5. Lịch sử xóa làm thay đổi chặn bộ nhớ

Với phương thức `delete` chỉ dọn nút rỗng, một nút có `through_count=0` nhưng vẫn còn `left/right` có thể được giữ để dẫn tới lựa chọn khác cùng vị trí.

Ví dụ chèn liên tiếp 1.000 khóa một ký tự theo thứ tự tăng (với bảng ký hiệu đủ rộng), sau đó xóa 999 khóa đầu. Cây có thể vẫn giữ một chuỗi ngang dài gần 1.000 nút dù **chỉ còn một khóa**.

Do đó, đối với mã minh họa, bộ nhớ có thể phụ thuộc số nút được tạo trong **toàn bộ lịch sử**, không chỉ tổng chiều dài khóa hiện còn. Nếu muốn chặn theo tập khóa đang sống, cần thuật toán xóa BST ngang đầy đủ hoặc định kỳ **xây lại** cấu trúc.

## 21. Cân bằng, thứ tự chèn và những lựa chọn cải tiến

### 21.1. TST không tự cân bằng

Bản TST thường được cài đặt bằng ba con trỏ **không có xoay cây**. Nếu dữ liệu tới theo thứ tự gần tăng/giảm tại một tầng ký tự, các nhánh ngang có thể rất dài.

Trái với suy nghĩ “cây nên có O(log n)”, ở đây **không có bất biến AVL hay Red–Black** để bảo đảm chiều cao logarithmic.

### 21.2. Điều gì quyết định độ cao ngang?

- Số ký tự khác nhau có thể xuất hiện ở vị trí đang xét.
- Thứ tự những ký tự ấy lần đầu được chèn vào BST ngang.
- Các thao tác xóa khiến nút trung gian cũ còn lại.
- Có dùng chiến lược cân bằng/rebuild hay không.

Ngay cả khi chuỗi khóa rất ngắn, có thể phải đi qua nhiều nhánh ngang ở ký tự đầu nếu thứ tự chèn bất lợi.

### 21.3. Cải tiến bằng BST cân bằng ở từng tầng

Có thể dùng các quy tắc AVL hoặc Red–Black để bảo đảm các nút ký tự cùng tầng có chiều cao logarithmic. Nhưng khi đó:

- Phải duy trì metadata cân bằng.
- Các phép xoay chỉ tác động các liên kết **ngang `left/right`**.
- Mỗi nút vẫn mang `eq` là cây ký tự **tầng tiếp theo**, không được nhầm nó với một con ngang trong phép xoay.
- Cập nhật `through_count` cần được thiết kế để giữ đúng các khóa thuộc từng nút ký tự.

Cách này phức tạp hơn bản TST cơ sở nhưng có thể kiểm soát trường hợp xấu.

### 21.4. Xây lại khi dữ liệu ổn định

Nếu dữ liệu có đợt nạp hàng loạt và ít cập nhật, một chiến lược là xây TST có các ký tự ngang được chèn tương đối cân bằng, chẳng hạn chọn ký tự giữa trong tập ký tự phân biệt của một tầng trước.

Không nên tự động sắp tất cả **từ nguyên vẹn** rồi chèn theo thứ tự tăng; điều ấy có thể làm đường ngang ký tự đầu bị lệch mạnh.

### 21.5. TST có phải ternary search algorithm không?

Tên *ternary search* còn được dùng cho thuật toán chia khoảng thành ba vùng khi tìm cực trị của hàm unimodal, hoặc **3-way string quicksort** dùng ba nhóm nhỏ hơn/bằng/lớn hơn ký tự pivot.

Các ý tưởng so sánh ba ngả có liên hệ, nhưng:

- TST là **cấu trúc dữ liệu lưu nhiều khóa và hỗ trợ cập nhật/truy vấn**.
- Ternary search trên hàm unimodal là **thuật toán tìm kiếm số học**.
- 3-way string quicksort là **thuật toán sắp xếp**, không phải cây chỉ mục giữ lâu dài.

Không nên áp độ phức tạp của một thuật toán có tên gần giống cho TST mà không xét biểu diễn cụ thể.

## 22. Unicode, chuẩn hóa và thứ tự từ điển

### 22.1. Unicode code point trong Python

Trong mã, một ký tự là một phần tử khi duyệt `str`:

```python
word = "bàn"
for ch in word:
    print(ch)
```

TST so `ch < node.char` theo thứ tự Unicode code point. Đây là một thứ tự **toàn phần có thể thực thi**, nhưng không phải collation tiếng Việt theo một locale.

### 22.2. Dấu kết hợp và NFC

Hai chuỗi hiển thị giống nhau có thể dùng dãy code point khác nhau:

```python
import unicodedata

composed = "bàn"
decomposed = "ba\u0300n"

assert composed != decomposed
assert (
    unicodedata.normalize("NFC", composed)
    == unicodedata.normalize("NFC", decomposed)
)
```

Nếu muốn coi chúng là **một khóa**, phải chuẩn hóa nhất quán trước mọi `insert`, `delete`, `contains` và `autocomplete`.

### 22.3. Ví dụ lớp bao chuẩn hóa

```python
import unicodedata


def normalize_key(text):
    if not isinstance(text, str):
        raise TypeError("khóa phải là str")
    return unicodedata.normalize("NFC", text.casefold())


tree = TernarySearchTree()
tree.insert(normalize_key("Bàn"))

assert tree.contains(normalize_key("ba\u0300n"))
assert tree.autocomplete(normalize_key("BÀ")) == ["bàn"]
```

`casefold` giúp hỗ trợ tìm không phân biệt chữ hoa/chữ thường, nhưng có thể làm thay đổi dãy code point và chiều dài khóa. `NFC` ghép những dạng tổ hợp tương đương; **không** đồng nghĩa bỏ dấu.

### 22.4. Tại sao không mặc nhiên sắp đúng từ điển tiếng Việt?

Thứ tự code point có thể khác trật tự chữ cái trong quy tắc ngôn ngữ. Nếu giao diện cần gợi ý theo thứ tự ngôn ngữ tự nhiên:

- Xác định quy tắc chuẩn hóa và collation.
- Có thể cần một **sort key** riêng.
- Có thể phải sắp kết quả theo collation sau khi liệt kê, thay vì tin rằng DFS TST theo code point tự cho thứ tự mong muốn.

Nếu thay cách so sánh ký tự sau khi cây đã được xây, bất biến BST ngang có thể không còn đúng. **Quan hệ so sánh phải nhất quán khi xây, tìm và cập nhật**.

### 22.5. Byte, code point và grapheme cluster

Một “ký tự người dùng nhìn thấy” có thể gồm nhiều code point. Nếu muốn TST theo **byte UTF-8**, phải mã hóa khóa, so byte và giải mã kết quả nhất quán. Nếu muốn theo **grapheme cluster**, phải phân đoạn chuỗi trước khi đưa vào cây.

Thông số `L` trong độ phức tạp phải được gắn với **đơn vị ký hiệu thực sự xử lý**, không chỉ với số chữ hiển thị.

## 23. Ứng dụng autocomplete và xếp hạng gợi ý

TST tự nhiên hỗ trợ tìm những khóa có cùng tiền tố. Nhưng trong sản phẩm tìm kiếm, “gợi ý tốt nhất” có thể không có nghĩa “khóa tăng theo code point”.

### 23.1. Gợi ý theo thứ tự ký tự

Hàm `autocomplete(prefix,limit)` trong bài:

1. Tìm nút khớp ký tự cuối tiền tố.
2. Phát chính tiền tố nếu là khóa terminal.
3. Duyệt `eq` theo thứ tự trái–chính nút–giữa–phải.
4. Dừng khi đủ `limit`.

Lợi điểm: dễ kiểm chứng, có thể dừng sớm, không cần giữ mọi kết quả nếu dùng generator.

### 23.2. Gợi ý theo điểm/tần suất

Giả sử những từ có điểm:

| Từ | Điểm |
| --- | ---: |
| `an` | 10 |
| `ang` | 5 |
| `anh` | 30 |

Theo thứ tự ký tự, ta có `an,ang,anh`. Theo điểm giảm dần, cần `anh,an,ang`.

TST chỉ mục **tiền tố**, không tự xếp thứ hạng theo điểm. Để có top-k theo điểm, có thể:

- Liệt kê toàn bộ ứng viên trong cây con tiền tố, rồi dùng **Heap** giữ k phần tử tốt nhất.
- Duy trì metadata điểm tối đa ở các cây con để cắt nhánh.
- Cache top-k ở các nút tiền tố nếu truy vấn lặp lại nhiều và cập nhật ít.

### 23.3. Heap chọn top-k vẫn phải xét ứng viên

Nếu chưa có metadata để bỏ qua các nhánh điểm thấp, việc dùng Heap chỉ giảm số ứng viên phải **giữ** trong bộ nhớ lựa chọn, không tự tránh việc **duyệt** các khóa phù hợp.

Với `C` ứng viên và `k` kết quả, cách duyệt hết rồi chọn bằng Heap có thể cần O(C log(k+1)) phép xử lý chọn, **cộng** chi phí đi cây và dựng khóa.

### 23.4. Cache top-k cần chính sách cập nhật

Nếu lưu top-5 ngay tại từng tiền tố:

- Chèn một từ phổ biến có thể thay đổi cache của **mọi tiền tố** dọc đường.
- Xóa một từ đang ở top-5 phải tìm từ thay thế.
- Thay điểm cần cập nhật hoặc vô hiệu hóa các cache liên quan.
- Bộ nhớ tăng vì một từ có thể xuất hiện trong cache của nhiều nút.

Đây là đánh đổi đọc nhanh ↔ cập nhật và RAM, không phải một tối ưu miễn phí.

### 23.5. Prefix không có nghĩa substring

`autocomplete("an")` tìm những từ **bắt đầu bằng `an`**. Nó không tự tìm mọi từ **chứa `an` ở giữa**. Nếu cần tìm đoạn con ở mọi vị trí, cân nhắc suffix array, suffix tree, suffix automaton hoặc một chỉ mục phù hợp khác.

## 24. Các sai lầm triển khai thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Tăng chỉ số ký tự khi đi trái/phải | Bỏ qua ký tự chưa khớp | Chỉ tăng `i` khi đi `eq` |
| Coi `left`/`right` là ký tự tiếp theo | Xây sai đường khóa | Trái/phải ở **cùng vị trí** |
| Nhận từ chỉ vì tìm được nút cuối | Nhận nhầm tiền tố chưa lưu | Kiểm tra `terminal` |
| Không cho nút terminal có `eq` | Không lưu được `an` và `anh` cùng lúc | Terminal và nhánh giữa độc lập |
| Gán `through_count` bằng tổng cả ba nhánh | Đếm nhầm khóa có ký tự khác | `through_count=terminal+T(eq)` |
| Chèn trùng vẫn tăng count | `count_prefix` vượt số khóa thật | Kiểm tra terminal trước khi tăng |
| Xóa thiếu vẫn giảm bộ đếm | Bộ đếm âm hoặc sai | Xác nhận terminal trước khi sửa |
| Duyệt `eq` mà quên phát terminal | Thiếu từ là tiền tố của từ dài hơn | Phát terminal trước nhánh giữa |
| Duyệt trái/phải với `path` chứa char của nút cha ngang | Tạo chuỗi sai | Chỉ append char trong sự kiện `self` |
| Duyệt `v.left/right` khi đã khớp prefix ở `v` | Trả từ không có prefix cần tìm | Chỉ xét `v` terminal và `v.eq` |
| Xóa nút có nhánh ngang mà không nối lại | Mất nhiều khóa | Chỉ dọn nút không còn con, hoặc xóa BST đúng |
| Nói TST luôn O(L) | Bỏ qua BST ngang có thể lệch | Tính tổng số so ký tự `Σh_i` |
| Nói TST luôn O(log n) | Không có bất biến cân bằng | Phân biệt TST với BST cân bằng |
| Nói bộ nhớ chỉ theo khóa hiện còn sau xóa | Nút pivot ngang cũ có thể tồn tại | Dùng xóa BST đầy đủ hoặc rebuild |
| Nối chuỗi tại mọi bước DFS mà bỏ chi phí | Copy tiền tố trung gian | Dùng `path` + `join` tại terminal |
| Cho limit=k rồi tuyên bố O(k) | Bỏ chi phí tìm/duyệt tới kết quả | Tính nút thăm `V` và đầu ra `Z` |
| Không chuẩn hóa Unicode đồng nhất | Các dạng biểu diễn một chữ khác đường | Quy định NFC/casefold thống nhất |
| Tuyên bố DFS code point đúng thứ tự tiếng Việt | Collation có thể khác code point | Dùng thứ tự sản phẩm quy định |
| Xem TST là ternary search hàm unimodal | Áp sai thuật toán/độ phức tạp | Phân biệt cấu trúc và thuật toán có tên gần giống |

## 25. Bài tập vận dụng có gợi ý giải

### Bài 1 — Quy tắc tăng vị trí

Tại nút `m`, đang tìm ký tự `a` của từ và `a<m`. Đi nhánh nào, và có tăng vị trí trong từ không?

**Gợi ý:** Đi `left`, **không** tăng chỉ số. Chưa khớp ký tự `a`.

### Bài 2 — Khác biệt giữa ba con

Giải thích ngắn ý nghĩa `left`, `eq` và `right`.

**Gợi ý:** Trái/phải tìm ký tự nhỏ/lớn hơn ở cùng vị trí; giữa nghĩa là ký tự hiện tại đã khớp, nên sang vị trí tiếp theo.

### Bài 3 — Vết tìm `at`

Cho TST chứa `an,at,be` như mục 4. Vẽ đường tìm `at`.

**Gợi ý:** Gốc `a` khớp, đi `eq` tới `n`, đi `right` tới `t` mà vẫn ở ký tự thứ hai, kiểm tra terminal.

### Bài 4 — Prefix không phải khóa

TST chỉ lưu `anh`. `contains("an")` và `count_prefix("an")` lần lượt là gì?

**Gợi ý:** `False` và 1. Nút `n` chưa terminal nhưng có đường `eq` tới `h` terminal.

### Bài 5 — Nút terminal có con

Cho `K={"an","anh"}`. Có cần giữ `terminal=True` tại nút `n` sau khi thêm `anh` không?

**Gợi ý:** Có. Nếu bỏ terminal `n` thì mất khóa `an`.

### Bài 6 — Đếm tiền tố đúng

TST lưu `an,ao,ba,ban`. Nút đầu `a` có nhánh phải dẫn tới `b`. `through_count(a)` bằng 2 hay 4?

**Gợi ý:** Bằng 2; chỉ `an` và `ao` khớp ký tự `a`. Các khóa `ba,ban` ở nhánh phải không có tiền tố `a`.

### Bài 7 — Chèn trùng

TST đang lưu `an` và `anh`. Gọi `insert("an")` lần nữa. Kích thước và `count_prefix("an")` thay đổi không?

**Gợi ý:** Không. `insert` trả False; kích thước là 2 và bộ đếm tiền tố là 2.

### Bài 8 — Thứ tự liệt kê

Với `K={"an","ang","anh","ao"}`, `autocomplete("a")` theo thứ tự code point là gì?

**Gợi ý:** `["an","ang","anh","ao"]`. Terminal của `an` đứng trước các hậu duệ `ang,anh`.

### Bài 9 — Lỗi khi duyệt nhánh phải

Khi thăm nút `n` trong tầng ký tự thứ hai của tiền tố `a`, tại sao phải bỏ `n` khỏi `path` trước khi duyệt `right` đến `o`?

**Gợi ý:** `right` đại diện **ký tự khác tại cùng vị trí**, không phải ký tự sau `n`. Nếu giữ `n` sẽ tạo `ano` thay vì `ao`.

### Bài 10 — Xóa tiền tố

TST lưu `an,anh,ang`. Sau `delete("an")`, `contains("an")` và `autocomplete("an")` là gì?

**Gợi ý:** `False` và `["ang","anh"]`. Không được xóa các nhánh dài hơn của tiền tố `an`.

### Bài 11 — Xóa nút ngang có con

TST một ký tự chứa `a,b`, nút `a` có nhánh phải `b`. Xóa `a` có được gỡ toàn bộ nút `a` và bỏ con phải không?

**Gợi ý:** Không. Phải giữ đường tới `b` hoặc thay bằng thao tác xóa BST ngang đúng. Mã bài giữ nút `a` làm pivot.

### Bài 12 — Đếm khi xóa

TST lưu `an,ang,anh,ao`. Xóa lần lượt `an`, `ang`, `anh`. `count_prefix("an")` và `count_prefix("a")` còn bao nhiêu?

**Gợi ý:** `0` và `1`, vì còn `ao`.

### Bài 13 — Thứ tự chèn bất lợi

Chèn các khóa một ký tự `a,b,c,d,e` theo thứ tự tăng. Tìm `e` có cần đúng một bước vì `L=1` không?

**Gợi ý:** Không. Có thể đi qua chuỗi `right` dài, nên cần nhiều phép so ký tự tại cùng vị trí.

### Bài 14 — Ước lượng theo BST ngang

Một khóa có độ dài 10, ở mỗi tầng BST ngang được bảo đảm chiều cao O(log σ). Độ phức tạp tìm là gì?

**Gợi ý:** O(10 log(σ+1)), hay O(L log(σ+1)) tổng quát. Nếu `σ` cố định nhỏ, xem là O(L).

### Bài 15 — Bộ nhớ sau lịch sử xóa

Vì sao bản `delete` chỉ dọn nút không còn con có thể giữ nhiều nút hơn số ký tự trong các khóa hiện còn?

**Gợi ý:** Các nút không terminal có `through_count=0` nhưng vẫn giữ nhánh trái/phải làm đường tìm tới khóa sống, nên không bị dọn.

### Bài 16 — Khóa rỗng

Theo hợp đồng bài, sau `insert("")` rồi `insert("a")`, `autocomplete("")` và `count_prefix("")` là gì?

**Gợi ý:** `["","a"]` và 2. Cờ `empty_terminal` độc lập với nút ký tự.

### Bài 17 — Unicode

Hai chuỗi `"bàn"` và `"ba\u0300n"` hiển thị gần giống nhưng có thể không tìm thấy lẫn nhau. Tại sao? Sửa bằng cách nào?

**Gợi ý:** Khác dãy code point. Chuẩn hóa theo cùng quy tắc, ví dụ NFC, trước chèn và truy vấn.

### Bài 18 — TST hay Hash Map Trie?

Một bảng chữ cái lớn, mỗi nút chỉ có vài nhánh, và truy vấn nhiều tiền tố. Hãy phân tích hai phương án TST và trie dùng dictionary con.

**Gợi ý:** TST dùng ba con trỏ cố định nhưng có thể đi nhiều nhánh ngang; dictionary con có overhead mỗi nút nhưng chọn cạnh kỳ vọng O(1). Đo RAM, độ cao ngang, độ dài từ, số lần cập nhật và phân bố tiền tố để quyết định.

### Bài 19 — Top-k theo điểm

Nếu `an` có điểm 5, `ang` có điểm 30, `anh` có điểm 10, thứ tự autocomplete từ điển có tự đưa `ang` lên đầu không?

**Gợi ý:** Không. Phải thêm điểm và thuật toán chọn top-k, ví dụ duyệt ứng viên rồi dùng Heap, hoặc cache/metadata phục vụ pruning.

### Bài 20 — Kiểm chứng bất biến

Hãy nêu hai công thức dùng trong `validate_tst` để kiểm tra bộ đếm.

**Gợi ý:** `M(v)=terminal(v)+T(eq(v))` và `T(v)=T(left(v))+M(v)+T(right(v))`. `through_count(v)` phải bằng `M(v)`, không bằng toàn bộ `T(v)`.

## 26. Checklist khi thiết kế TST

```text
1. Hợp đồng:
   - Lưu Set, Map hay Multiset?
   - Có cho phép khóa rỗng, chèn trùng, xóa thiếu?
   - Trả gợi ý theo code point, collation hay điểm?
   - Có giới hạn số lượng và phân trang?

2. Bất biến:
   - left/right là BST ngang cùng vị trí ký tự?
   - eq chỉ dành cho ký tự tiếp theo sau khi khớp?
   - terminal biểu diễn khóa hoàn chỉnh tại node?
   - through_count chỉ tính terminal và toàn eq subtree?
   - Các nút không có chu trình và không chia sẻ cha?

3. Tìm/chèn:
   - Đi left/right có giữ nguyên i?
   - Chỉ tăng i sau khi khớp char?
   - Chèn trùng có giữ nguyên size/count?
   - Tạo nút đúng ký tự và đúng tầng?

4. Prefix:
   - Tìm đúng node của ký tự cuối?
   - Count đọc through_count, không cộng left/right?
   - Liệt kê prefix terminal trước rồi đi eq?
   - Prefix rỗng lấy toàn bộ tập khóa?

5. Duyệt:
   - Thứ tự left -> terminal -> eq -> right?
   - Path chỉ chứa ký tự đã khớp?
   - Có pop char trước khi thăm right?
   - Đã tính V và tổng chiều dài đầu ra Z?
   - Generator/limit có dừng sớm đúng?

6. Xóa:
   - Xác nhận terminal trước khi sửa?
   - Chỉ giảm count ở các node đã khớp?
   - Chỉ gỡ node không terminal không có con?
   - Nếu muốn gỡ pivot ngang, đã cài BST delete đúng?
   - Có cần rebuild sau lịch sử xóa dài?

7. Hiệu năng:
   - Đã tính tổng chi phí tìm ngang h_i?
   - Có bảo đảm cân bằng ngang hay không?
   - So chi phí với trie dictionary/mảng con?
   - Đã đo RAM đối tượng và cache locality?
   - Có yêu cầu top-k theo điểm ngoài thứ tự chữ?

8. Kiểm thử:
   - "an" và "anh" cùng tồn tại?
   - Prefix có nhưng không là khóa hoàn chỉnh?
   - Chèn trùng, xóa thiếu, xóa prefix rồi giữ hậu duệ?
   - Khóa rỗng, Unicode, ký tự nhiều dạng chuẩn hóa?
   - So autocomplete và count_prefix với Set tham chiếu?
   - Chèn tăng/giảm và lịch sử xóa có làm sai kết quả?
```

## 27. Tổng kết

**Ternary Search Tree (TST)** kết hợp **BST theo ký tự ở cùng vị trí** với đường **`eq` tiến sang ký tự tiếp theo**. Mỗi nút chỉ có ba liên kết `left`, `eq`, `right` cùng dấu terminal, nên có thể chỉ mục nhiều từ chung tiền tố mà không phải giữ một mảng con kích thước toàn bảng chữ cái tại từng nút.

Ba điểm then chốt:

- **Tính đúng:** Chỉ tiêu thụ ký tự khi so sánh **bằng** và đi `eq`; trái/phải là lựa chọn **ký tự khác ở cùng vị trí**. Terminal quyết định khóa hoàn chỉnh, không phải việc đường ký tự tồn tại.
- **Tiền tố:** Khi đã khớp ký tự cuối của prefix, chỉ **terminal của nút ấy và `eq` bên dưới** có cùng tiền tố. Bộ đếm `through_count` phản ánh đúng tập này và không được cộng nhầm trái/phải.
- **Hiệu năng:** TST **không tự cân bằng**. Thời gian tìm phụ thuộc tổng chiều cao các BST ngang, chứ không tự là O(L) hay O(log n). Duyệt và gợi ý còn phụ thuộc số nút thăm và tổng ký tự xuất ra; xóa chỉ dọn lá có thể giữ lại pivot ngang từ lịch sử cập nhật.

Với bất biến rõ, cài đặt kiểm thử độc lập, quy tắc Unicode nhất quán và phân tích theo workload, TST là một lựa chọn hữu ích giữa trie với bảng con và BST lưu khóa nguyên vẹn — đặc biệt khi cần tìm theo tiền tố và muốn kiểm soát cấu trúc nhánh ở mức ký tự.
