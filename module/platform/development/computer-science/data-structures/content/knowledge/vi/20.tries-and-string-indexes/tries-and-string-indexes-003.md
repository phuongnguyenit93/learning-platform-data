# Tìm, chèn và xóa một khóa trong trie

> **Chương:** Trie và chỉ mục chuỗi · **Bài học:** Tìm, chèn và xóa một khóa trong trie

Hãy tưởng tượng một ứng dụng từ điển lưu các từ `an`, `anh`, `ao`, `ba` và `ban`. Khi người dùng tìm `an`, ứng dụng cần nhận ra đúng từ này; khi thêm `ang`, cấu trúc nên tận dụng đoạn `a → n` đã có; khi xóa `an`, từ `anh` vẫn phải được giữ nguyên. Ba yêu cầu tưởng đơn giản đó làm rõ bản chất của **trie** (*cây tiền tố*): khóa được biểu diễn bằng đường đi của các ký hiệu và việc chèn/xóa phải bảo toàn các đường dùng chung.

Bài học này tập trung vào ba thao tác cốt lõi: **tìm (search)**, **chèn (insert)** và **xóa (delete)** một khóa. Chúng ta sẽ đặc tả tiền điều kiện, hậu điều kiện, bất biến của trie; mô phỏng từng bước; xây cài đặt Python hoàn chỉnh; kiểm tra những tình huống biên và phân tích độ phức tạp theo **độ dài khóa** thay vì chỉ theo số khóa đang lưu.

Chủ đề thuộc chương **Trie và chỉ mục chuỗi** của mô-đun Cấu trúc dữ liệu (`COMPUTER_SCIENCE_DATA_STRUCTURES`), nơi mục tiêu là hiểu cấu trúc, bất biến, thao tác và chi phí thời gian–bộ nhớ của mảng, danh sách liên kết, Stack, Queue, bảng băm, cây, heap và đồ thị để chọn biểu diễn phù hợp với từng bài toán.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Mô tả cách một trie biểu diễn khóa bằng các cạnh ký hiệu và dấu **kết thúc khóa**.
2. Viết giả mã tìm, chèn và xóa cho một **tập khóa chuỗi không trùng**.
3. Giải thích chính xác sự khác nhau giữa đường đi tồn tại và khóa hoàn chỉnh được lưu.
4. Chèn từ ngắn sau từ dài hoặc ngược lại mà không làm mất từ cũ.
5. Xóa một khóa, dọn các nút không còn cần thiết nhưng vẫn giữ các nhánh có khóa khác.
6. Cài đặt và kiểm thử một `TrieSet` Python hỗ trợ khóa rỗng, chèn trùng và xóa khóa không tồn tại.
7. Chứng minh bất biến số khóa trong cây con được giữ sau mỗi thao tác.
8. Phân tích thời gian tìm/chèn/xóa theo độ dài khóa `L`; giải thích các giả định về dictionary, Unicode và bộ nhớ nút.
9. Đối chiếu trie với Hash Set, mảng sắp xếp và cây tìm kiếm cân bằng theo workload.

## 2. Nhắc lại mô hình trie không nén

Một **trie không nén** là cây có gốc với những quy tắc:

- Gốc tương ứng tiền tố rỗng `""`.
- Mỗi cạnh đi từ một nút sang nút con được gắn **đúng một ký hiệu**.
- Với mỗi nút, không có hai cạnh đi ra mang cùng một ký hiệu.
- Ghép nhãn các cạnh từ gốc đến một nút tạo thành đúng một tiền tố.
- Mỗi nút có cờ `terminal`, đánh dấu chuỗi trên đường đi đến nút đó có phải khóa hoàn chỉnh đang lưu hay không.

Ví dụ tập khóa:

```text
S = {"an", "anh", "ao", "ba", "ban"}
```

Trie tương ứng:

```text
                       root ("")
                        /       \
                       a         b
                     /   \        \
                   n(*)   o(*)     a(*)
                    |               |
                   h(*)            n(*)

(*) = terminal: khóa được lưu tại nút đó
```

Nút `an` vừa đánh dấu kết thúc khóa `"an"` vừa có nhánh tới `"anh"`. Nút `a` không terminal, dù nó là tiền tố của nhiều từ. Nút `ba` terminal và vẫn có con `n` vì `"ban"` cũng được lưu.

### 2.1. Hai câu hỏi không đồng nhất

| Câu hỏi | Điều kiện | Ví dụ với `S` ở trên |
| --- | --- | --- |
| “Có khóa `x` không?” | Đường `x` tồn tại **và** nút cuối terminal | `contains("an") = True`; `contains("a") = False` |
| “Có đường tiền tố `x` không?” | Đi được hết các cạnh của `x` | `starts_with("a") = True`; `starts_with("ax") = False` |

Nếu chương trình chỉ kiểm tra đường đi thì `contains("a")` sẽ trả sai. Nếu chương trình chỉ nhận khóa ở **nút lá**, nó sẽ bỏ sót `"an"` và `"ba"`.

### 2.2. Ký hiệu dùng trong bài

- `S`: tập các khóa hoàn chỉnh hiện có.
- `n=|S|`: số khóa phân biệt.
- `word`: khóa cần tìm, chèn hoặc xóa.
- `L=len(word)`: số ký hiệu của khóa theo cách biểu diễn đã chọn.
- `P=len(prefix)`: số ký hiệu của một tiền tố.
- `N`: số nút đang tồn tại, kể cả gốc.
- `T=\sum_{s\in S}|s|`: tổng số ký hiệu của các khóa đang lưu.

Trong phần mã Python, mỗi lần lặp qua chuỗi lấy **một Unicode code point**. `L` không nhất thiết bằng số byte UTF-8 hoặc số chữ người dùng nhìn thấy.

## 3. Đặc tả API và những quyết định cần chốt

Ta xây `TrieSet`, một kiểu dữ liệu trừu tượng lưu **tập các chuỗi**:

| Phép toán | Tiền điều kiện | Hậu điều kiện |
| --- | --- | --- |
| `contains(word)` | `word` là `str` | Trả True khi và chỉ khi `word∈S`; không sửa trạng thái |
| `insert(word)` | `word` là `str` | Nếu chưa có, chuyển `S` thành `S∪{word}` và trả True; nếu có sẵn, không đổi gì và trả False |
| `delete(word)` | `word` là `str` | Nếu đang có, chuyển `S` thành `S\{word}` và trả True; nếu không có, không đổi gì và trả False |
| `starts_with(prefix)` | `prefix` là `str` | Cho biết đường mang `prefix` có tồn tại |
| `count_prefix(prefix)` | `prefix` là `str` | Trả số khóa hoàn chỉnh có tiền tố `prefix` |
| `len(trie)` | Không | Trả số khóa phân biệt `n` |

Những quyết định bổ sung:

1. **Cho phép khóa rỗng `""`.** Gốc sẽ terminal nếu chính khóa rỗng được chèn.
2. **Không lưu bản sao trùng.** Hai lần chèn cùng một chuỗi chỉ tạo một khóa trong tập.
3. **Xóa khóa không tồn tại không ném lỗi.** Hàm trả False.
4. **Dọn nhánh chết sau xóa.** Nút không phải gốc chỉ được giữ nếu trong cây con có ít nhất một khóa.
5. **Không tự chuẩn hóa Unicode.** `insert` và `contains` xét các chuỗi Python theo code point; ứng dụng muốn chuẩn hóa cần làm nhất quán ở bên ngoài.

Các thư viện khác có thể chọn quy tắc khác (không cho khóa rỗng, ném `KeyError` khi xóa thiếu, hoặc lưu Map thay vì Set). **Hợp đồng phải được công bố trước khi tối ưu cài đặt.**

## 4. Biểu diễn nút và bất biến

Mỗi nút lưu ba thành phần:

```text
Node:
    children: ánh xạ ký hiệu -> Node
    terminal: Boolean
    subtree_count: số khóa hoàn chỉnh trong cây con
```

`subtree_count` không bắt buộc trong mọi trie; bài này thêm nó để thực hiện `count_prefix` và giúp nhận ra nút nào có thể bị cắt sau xóa.

### 4.1. Các bất biến cần duy trì

1. Có đúng một gốc và gốc tồn tại kể cả khi `S` rỗng.
2. Mỗi nút con có đúng một nút cha; các nhãn cạnh ra khỏi cùng nút là duy nhất.
3. Với mọi nút `v`, ghép nhãn trên đường gốc → `v` xác định duy nhất một tiền tố `label(v)`.
4. `terminal(v)=True` khi và chỉ khi `label(v)∈S`.
5. Mỗi nút có bộ đếm bằng số **khóa hoàn chỉnh** trong cây con:

\[
count(v)=\mathbf{1}_{terminal(v)}
+\sum_{u\in children(v)}count(u).
\]

6. Tại gốc, `count(root)=n`.
7. Ngoài gốc, không giữ nút có `count(v)=0` sau khi một thao tác đã hoàn tất.

### 4.2. Bảng đếm trên ví dụ

| Nút theo tiền tố | `terminal` | `subtree_count` | Khóa thuộc cây con |
| --- | --- | --- | --- |
| `""` (gốc) | False | 5 | `an, anh, ao, ba, ban` |
| `"a"` | False | 3 | `an, anh, ao` |
| `"an"` | True | 2 | `an, anh` |
| `"anh"` | True | 1 | `anh` |
| `"ao"` | True | 1 | `ao` |
| `"b"` | False | 2 | `ba, ban` |
| `"ba"` | True | 2 | `ba, ban` |
| `"ban"` | True | 1 | `ban` |

Một nút có thể có `subtree_count=2` nhưng chỉ có **một** cờ terminal. Bộ đếm ghi số khóa ở toàn cây con, không phải số lần chính nút đó kết thúc từ.

### 4.3. Tại sao nên giữ đường đã đi qua?

Thao tác tìm chỉ cần một biến trỏ tới nút hiện tại. Nhưng chèn hoặc xóa có thể phải cập nhật `subtree_count` của **tất cả nút trên đường**.

Có hai cách:

- Lưu danh sách `path` khi đi từ gốc xuống, rồi cập nhật.
- Duyệt lại đường từ gốc sau khi đã quyết định cập nhật.

Cài đặt trong bài dùng `path` để không phải dò lại và để có đường cha–con phục vụ việc dọn nhánh từ dưới lên.

## 5. Thuật toán tìm một khóa `search / contains`

Tìm chính xác một khóa có hai giai đoạn logic:

1. **Lần theo đường** của toàn bộ ký hiệu.
2. **Kiểm tra terminal** ở nút cuối.

### 5.1. Giả mã

```text
CONTAINS(root, word):
    node <- root

    for mỗi ký hiệu ch trong word:
        if ch không thuộc node.children:
            return FALSE
        node <- node.children[ch]

    return node.terminal
```

Không có thao tác thêm hoặc xóa ở đây. Vì thế sau lời gọi, toàn bộ bất biến và tập `S` phải giữ nguyên.

### 5.2. Vết tìm `"anh"` thành công

Với `S={"an","anh","ao","ba","ban"}`:

| Bước | Ký hiệu cần đi | Nút trước bước | Kết quả |
| --- | --- | --- | --- |
| 0 | — | Gốc | Bắt đầu |
| 1 | `a` | Gốc | Có cạnh `a` → tới nút `"a"` |
| 2 | `n` | `"a"` | Có cạnh `n` → tới `"an"` |
| 3 | `h` | `"an"` | Có cạnh `h` → tới `"anh"` |
| Kết thúc | — | `"anh"` | `terminal=True` → trả True |

### 5.3. Hai cách tìm thất bại

**Thiếu cạnh:** `contains("ang")` tìm được `a→n` nhưng không có cạnh `g`, nên trả False ngay tại ký hiệu thứ ba.

**Đường có đủ nhưng nút không terminal:** `contains("a")` đi được tới nút `a`, nhưng `terminal=False`, nên trả False.

Cần kiểm thử cả hai kiểu thất bại. Chỉ kiểm tra khóa không có cạnh sẽ không phát hiện lỗi bỏ qua `terminal`.

### 5.4. Tìm khóa rỗng

Với `word=""`, vòng lặp không chạy. Hàm trả `root.terminal`. Nếu chưa chèn `""` thì False; sau khi chèn thì True.

Không nên viết đoạn đặc biệt “khóa rỗng luôn không tồn tại” nếu hợp đồng đã cho phép lưu nó.

## 6. Thuật toán chèn một khóa `insert`

Khi chèn, các tiền tố đã có phải được **dùng lại**, và chỉ những đoạn chưa tồn tại mới tạo nút.

### 6.1. Giả mã có bộ đếm

```text
INSERT(root, word):
    node <- root
    path <- [root]

    for mỗi ký hiệu ch trong word:
        if ch không thuộc node.children:
            node.children[ch] <- NEW_NODE()
        node <- node.children[ch]
        path.append(node)

    if node.terminal == TRUE:
        return FALSE

    node.terminal <- TRUE
    for mỗi nút v trong path:
        v.subtree_count <- v.subtree_count + 1

    size <- size + 1
    return TRUE
```

Giả mã kiểm tra `terminal` **sau khi đi hết khóa**, vì đường đi tồn tại chưa chắc khóa đã có.

### 6.2. Chèn vào Trie rỗng

Ban đầu chỉ có gốc với `terminal=False` và `count=0`. Chèn `"an"`:

```text
root -> a -> n*
count: 1     1    1
```

Tạo hai nút mới, đánh dấu terminal tại `n`. Tăng bộ đếm tại gốc, `a` và `an` lên 1.

### 6.3. Chèn khóa có chung tiền tố

Sau khi đã có `"an"`, chèn `"anh"`:

```text
Trước: root -> a -> n*
Sau:   root -> a -> n* -> h*
```

Chỉ tạo nút `h`. Nút `an` vẫn terminal; bộ đếm tại gốc, `a` và `an` tăng thêm 1. Bộ đếm `h` mới là 1.

Chèn tiếp `"ao"`: dùng lại nút `a`, tạo nhánh `o`. Chèn `"ba"`: tạo nhánh mới `b→a`.

### 6.4. Chèn từ ngắn sau từ dài

Nếu ban đầu chỉ có `"anh"`, chèn `"an"` **không phải tạo nút nào**, nhưng vẫn làm tăng số khóa:

```text
Trước: root -> a -> n -> h*
Sau:   root -> a -> n* -> h*
```

Đây là trường hợp quan trọng: **đường đã tồn tại, nhưng khóa chưa tồn tại**. Nếu kiểm tra “đường đi đã có” để bỏ qua chèn, chương trình sẽ sai.

### 6.5. Chèn trùng và tính đúng của bộ đếm

Chèn `"anh"` hai lần không tạo hai khóa:

```text
INSERT("anh") -> TRUE    # Lần đầu
INSERT("anh") -> FALSE   # Lần thứ hai
```

Lần hai **không được tăng bất kỳ bộ đếm nào**. Nếu không, `count_prefix("an")` sẽ tăng dù tập `S` không đổi.

### 6.6. Chèn chuỗi rỗng

Với `word=""`, `path` chỉ chứa gốc. Chèn `""` lần đầu đặt `root.terminal=True`, tăng `root.subtree_count` và `size` lên 1. Không thêm cạnh.

Nếu trong trie đã có các khóa không rỗng, chúng vẫn giữ nguyên. Gốc có thể terminal và đồng thời có nhiều nút con.

## 7. Vết chèn nhiều khóa và sự biến đổi trạng thái

Bắt đầu từ trie rỗng. Lần lượt thực hiện:

```text
insert("an")
insert("anh")
insert("ao")
insert("an")   # Trùng
insert("ba")
insert("ban")
```

| Lời gọi | Tạo nút/cạnh mới | Có thêm khóa phân biệt? | `len` sau lời gọi |
| --- | --- | --- | --- |
| `insert("an")` | `a, n` | Có | 1 |
| `insert("anh")` | `h` sau `an` | Có | 2 |
| `insert("ao")` | `o` sau `a` | Có | 3 |
| `insert("an")` | Không | Không | 3 |
| `insert("ba")` | `b, a` | Có | 4 |
| `insert("ban")` | `n` sau `ba` | Có | 5 |

Tại thời điểm cuối:

- `contains("an") = True`.
- `contains("anh") = True`.
- `contains("a") = False`.
- `count_prefix("an") = 2`.
- `count_prefix("a") = 3`.
- `count_prefix("") = 5`.

Bộ đếm của nút `a` tăng từ 1 lên 2 khi thêm `anh`, rồi lên 3 khi thêm `ao`, **không tăng** trong lần thêm `an` trùng.

## 8. Thuật toán xóa một khóa `delete`: vấn đề chia sẻ đường

Xóa khó hơn tìm và chèn vì nhiều khóa có thể dùng chung cùng tiền tố. Ta phải xóa **đúng một khóa logic** mà không cắt đường của các khóa còn lại.

### 8.1. Ba tình huống quyết định

| Tình huống | Ví dụ | Cách xử lý |
| --- | --- | --- |
| Khóa không tồn tại | Xóa `"a"` khi chỉ lưu `"an"` | Trả False; không sửa |
| Khóa là tiền tố của khóa khác | Xóa `"an"` khi còn `"anh"` | Bỏ terminal ở `an`, giữ nút `an` và nhánh `h` |
| Khóa cuối cùng trong một nhánh | Xóa `"anh"` khi nhánh `an→h` không còn khóa khác | Bỏ terminal rồi cắt nút/nhánh không còn khóa từ dưới lên |

**Không được xóa cả đường chỉ vì khóa bị xóa đã kết thúc ở đó.** Cần biết còn khóa nào dựa vào mỗi đoạn đường hay không.

### 8.2. Giả mã dùng bộ đếm cây con

```text
DELETE(root, word):
    node <- root
    path <- [root]

    for mỗi ký hiệu ch trong word:
        if ch không thuộc node.children:
            return FALSE
        node <- node.children[ch]
        path.append(node)

    if node.terminal == FALSE:
        return FALSE

    node.terminal <- FALSE

    for mỗi nút v trong path:
        v.subtree_count <- v.subtree_count - 1

    for i từ len(word)-1 giảm dần tới 0:
        parent <- path[i]
        child <- path[i+1]

        if child.subtree_count > 0:
            break

        xóa parent.children[word[i]]

    size <- size - 1
    return TRUE
```

Bước kiểm tra tồn tại **phải hoàn tất trước khi thay đổi trạng thái**. Nếu đường thiếu hoặc nút cuối không terminal, hàm trả False và không làm giảm bộ đếm.

### 8.3. Vì sao duyệt ngược?

Muốn cắt một nhánh, phải biết nó **không còn khóa trong toàn cây con**. Sau khi bỏ terminal và giảm bộ đếm, kiểm tra từ nút cuối lên cha:

- Nếu `child.subtree_count=0`, không có khóa nào cần đường tới child, nên cạnh từ cha có thể bị xóa.
- Nếu `child.subtree_count>0`, ít nhất một khóa vẫn cần child, nên dừng.
- Gốc không bị xóa vì không có cha và là trạng thái hợp lệ của trie rỗng.

Với tập khóa phân biệt, mỗi lần xóa thành công làm `len` và `root.subtree_count` giảm đúng 1.

### 8.4. Cách xóa khác: kiểm tra `terminal` và `children`

Trong trie **không lưu bộ đếm** nhưng vẫn dọn nhánh chết, có thể cắt nút con khi:

```text
child.terminal == False
AND
child.children rỗng
```

Ta bắt đầu từ nút cuối và đi ngược: nếu nút vừa bỏ dấu terminal không còn con, xóa nó; tiếp tục xét cha. Nếu gặp nút terminal hoặc còn con, dừng.

Hai cách tương đương về mục đích dưới bất biến dọn nhánh, nhưng cách dùng `subtree_count` còn hỗ trợ `count_prefix` trong thời gian theo độ dài tiền tố.

## 9. Mô phỏng xóa qua bốn kịch bản

Ta bắt đầu với:

```text
S = {"an", "anh", "ao", "ba", "ban"}
```

### 9.1. Kịch bản A: xóa khóa cũng là tiền tố

Xóa `"an"`, còn `"anh"`:

```text
Trước: a -> n(*) -> h(*)
Sau:   a -> n    -> h(*)
```

Bỏ terminal ở `an`. Bộ đếm `root, a, an` giảm 1. Vì nút `an` vẫn chứa `anh` trong cây con nên **không cắt** nút `an`.

Kết quả:

- `contains("an") = False`.
- `starts_with("an") = True`.
- `contains("anh") = True`.
- `count_prefix("an") = 1`.

### 9.2. Kịch bản B: xóa khóa dài và dọn phần thừa

Tiếp tục xóa `"anh"`. Nhánh `a→n→h` không còn khóa nào, nhưng `a→o` vẫn giữ `"ao"`.

Ta xóa cạnh `n→h`, rồi cạnh `a→n`. Dừng ở nút `a` vì nó còn nhánh `o` với khóa `"ao"`.

Kết quả:

- `contains("anh") = False`.
- `starts_with("an") = False`.
- `starts_with("a") = True`.
- `contains("ao") = True`.

### 9.3. Kịch bản C: xóa khóa ngắn nhưng còn khóa dài

Với nhánh `b→a(*)→n(*)`, xóa `"ba"`:

```text
Trước: b -> a(*) -> n(*)
Sau:   b -> a    -> n(*)
```

Nút `ba` còn con `n` và bộ đếm cây con bằng 1, nên không được cắt. Khóa `"ban"` vẫn tồn tại.

### 9.4. Kịch bản D: xóa khóa cuối cùng của cả nhánh

Sau khi đã xóa `ba`, nếu xóa tiếp `ban` thì toàn bộ nhánh `b→a→n` không còn khóa. Có thể cắt lần lượt `n`, `a` và `b`.

Gốc vẫn tồn tại để biểu diễn tập rỗng hoặc các nhánh còn lại. Trong chuỗi này, nhánh `a→o` vẫn chứa `ao` nên trie chưa rỗng.

### 9.5. Kịch bản E: xóa từ không tồn tại

Nếu `contains("a") = False` nhưng đường `a` có tồn tại, lời gọi `delete("a")` phải trả False mà **không** đụng tới nhánh `ao` hay bộ đếm.

Một hàm sai thường chỉ kiểm tra “đã đi tới nút” rồi giảm bộ đếm; kịch bản này giúp phát hiện lỗi đó.

## 10. Cài đặt Python hoàn chỉnh cho ba thao tác

Cài đặt sử dụng `dict` để ánh xạ ký hiệu → nút con. Mỗi cạnh là một Unicode code point; việc tra dictionary thường có chi phí O(1) **kỳ vọng** trong mô hình hash phù hợp. Hàm không tự chuẩn hóa Unicode, để giữ chính xác hợp đồng đã nêu.

### 10.1. Lớp nút

```python
class TrieNode:
    __slots__ = ("children", "terminal", "subtree_count")

    def __init__(self):
        self.children = {}
        self.terminal = False
        self.subtree_count = 0
```

`__slots__` là lựa chọn quản lý thuộc tính của Python, không bắt buộc cho logic trie. Cốt lõi là `children`, `terminal` và `subtree_count`.

### 10.2. Lớp TrieSet

```python
class TrieSet:
    def __init__(self):
        self._root = TrieNode()
        self._size = 0

    @staticmethod
    def _check_text(text):
        if not isinstance(text, str):
            raise TypeError("khóa/tiền tố phải là chuỗi str")

    def __len__(self):
        return self._size

    def _follow(self, text):
        """Trả nút cuối của đường text hoặc None nếu thiếu cạnh."""
        node = self._root
        for char in text:
            node = node.children.get(char)
            if node is None:
                return None
        return node

    def contains(self, word):
        self._check_text(word)
        node = self._follow(word)
        return node is not None and node.terminal

    def starts_with(self, prefix):
        """Kiểm tra đường tiền tố, kể cả đường rỗng tại root."""
        self._check_text(prefix)
        return self._follow(prefix) is not None

    def count_prefix(self, prefix):
        self._check_text(prefix)
        node = self._follow(prefix)
        return 0 if node is None else node.subtree_count

    def insert(self, word):
        """Chèn mới -> True; đã có -> False."""
        self._check_text(word)

        node = self._root
        path = [node]

        for char in word:
            child = node.children.get(char)
            if child is None:
                child = TrieNode()
                node.children[char] = child
            node = child
            path.append(node)

        if node.terminal:
            return False

        node.terminal = True
        for ancestor in path:
            ancestor.subtree_count += 1
        self._size += 1
        return True

    def delete(self, word):
        """Xóa khóa có sẵn -> True; thiếu khóa -> False."""
        self._check_text(word)

        node = self._root
        path = [node]

        for char in word:
            node = node.children.get(char)
            if node is None:
                return False
            path.append(node)

        if not node.terminal:
            return False

        node.terminal = False
        for ancestor in path:
            ancestor.subtree_count -= 1

        # Cắt các cạnh tới cây con không còn khóa nào.
        for i in range(len(word) - 1, -1, -1):
            parent = path[i]
            child = path[i + 1]

            if child.subtree_count > 0:
                break
            del parent.children[word[i]]

        self._size -= 1
        return True

    def keys_with_prefix(self, prefix="", limit=None):
        """Liệt kê các khóa theo thứ tự code point."""
        self._check_text(prefix)

        if limit is not None:
            if not isinstance(limit, int) or limit < 0:
                raise ValueError("limit phải không âm")
            if limit == 0:
                return []

        node = self._follow(prefix)
        if node is None:
            return []

        results = []
        stack = [(prefix, node)]

        while stack:
            current, current_node = stack.pop()

            if current_node.terminal:
                results.append(current)
                if limit is not None and len(results) >= limit:
                    break

            # LIFO: đẩy nhánh nhãn lớn trước để thăm nhỏ trước.
            for char in sorted(current_node.children, reverse=True):
                stack.append(
                    (current + char, current_node.children[char])
                )

        return results
```

Các phương thức trọng tâm là `contains`, `insert` và `delete`. `count_prefix` và `keys_with_prefix` được thêm để kiểm tra sâu hơn tính đúng và minh họa vì sao việc duy trì đường tiền tố có ích.

**Lưu ý về `keys_with_prefix`:** Mã tạo chuỗi trung gian bằng `current + char`, nên chi phí liệt kê còn có sao chép tiền tố và sắp nhãn con. Không nên suy rằng toàn bộ thao tác liệt kê chỉ O(P) theo độ dài tiền tố.

### 10.3. Vì sao chèn trước rồi mới cập nhật bộ đếm?

Trong `insert`, ta đi tới nút cuối và kiểm tra `node.terminal`. Nếu khóa đã tồn tại, trả False trước khi tăng bộ đếm. Nếu chưa, chỉ có **một khóa mới** được thêm, nên mọi nút trên đường được tăng đúng một đơn vị.

Điều này đúng ngay cả khi không tạo nút nào, như trường hợp thêm `"an"` vào trie đang chứa `"anh"`.

### 10.4. Vì sao xóa có thể cắt nhánh dựa trên bộ đếm?

Sau khi xóa thành công, nút có `subtree_count=0` không còn chứa một khóa hoàn chỉnh nào trong toàn bộ cây con. Cắt cạnh từ cha tới nút ấy vì thế không làm mất bất kỳ khóa còn sống nào.

Nếu bộ đếm dương thì ít nhất một khóa còn cần nhánh này, và thuật toán dừng. Nó không bắt buộc nút đang xét phải terminal; nút trung gian không terminal vẫn được giữ khi còn khóa sâu hơn.

### 10.5. Chi phí bộ nhớ tạm của đường `path`

Hàm `insert` và `delete` giữ danh sách `path` chứa tối đa `L+1` tham chiếu. Vì vậy bộ nhớ phụ tối đa O(L+1) theo số ký hiệu của khóa.

Nếu dùng một cài đặt không lưu `path`, có thể tiết kiệm một số tham chiếu nhưng phải cân nhắc cách giảm bộ đếm hoặc dọn ngược. Chặn thời gian và bộ nhớ phải theo **cài đặt thật**, không chỉ theo tên thao tác.

## 11. Chạy ví dụ chức năng bằng các phép assert

Các đoạn sau đặt **sau hai lớp** ở mục 10 trong cùng tệp Python.

### 11.1. Tìm và chèn

```python
trie = TrieSet()

assert len(trie) == 0
assert trie.starts_with("")
assert not trie.contains("")
assert trie.count_prefix("") == 0

for word in ["an", "anh", "ao", "ba", "ban"]:
    assert trie.insert(word)

assert len(trie) == 5
assert trie.contains("an")
assert trie.contains("anh")
assert trie.contains("ao")
assert trie.contains("ba")
assert trie.contains("ban")

assert not trie.contains("a")
assert not trie.contains("b")
assert not trie.contains("ang")
assert trie.starts_with("a")
assert trie.starts_with("an")
assert not trie.starts_with("ax")

assert trie.count_prefix("") == 5
assert trie.count_prefix("a") == 3
assert trie.count_prefix("an") == 2
assert trie.count_prefix("b") == 2
assert trie.count_prefix("x") == 0
```

### 11.2. Chèn trùng và chèn từ ngắn đã có đường

```python
assert not trie.insert("an")
assert len(trie) == 5
assert trie.count_prefix("an") == 2

other = TrieSet()
assert other.insert("anh")
assert not other.contains("an")
assert other.starts_with("an")

# Đã có đường, nhưng chưa có khóa hoàn chỉnh "an".
assert other.insert("an")
assert other.contains("an")
assert other.contains("anh")
assert len(other) == 2
assert other.count_prefix("an") == 2
```

### 11.3. Xóa từ là tiền tố và xóa nhánh dài

```python
assert trie.delete("an")
assert not trie.contains("an")
assert trie.contains("anh")
assert trie.starts_with("an")
assert trie.count_prefix("an") == 1
assert len(trie) == 4

assert trie.delete("anh")
assert not trie.contains("anh")
assert not trie.starts_with("an")
assert trie.contains("ao")
assert trie.starts_with("a")
assert trie.count_prefix("a") == 1
assert len(trie) == 3

assert not trie.delete("an")  # Không được giảm count lần nữa.
assert trie.count_prefix("a") == 1
assert len(trie) == 3
```

### 11.4. Xóa khóa ngắn trong nhánh khác

```python
assert trie.delete("ba")
assert not trie.contains("ba")
assert trie.contains("ban")
assert trie.starts_with("ba")
assert trie.count_prefix("ba") == 1
assert len(trie) == 2

assert trie.delete("ban")
assert not trie.starts_with("b")
assert trie.count_prefix("b") == 0
assert trie.contains("ao")
assert len(trie) == 1

assert trie.delete("ao")
assert len(trie) == 0
assert trie.count_prefix("") == 0
assert not trie.starts_with("a")
assert trie.starts_with("")  # Gốc vẫn tồn tại.
```

### 11.5. Khóa rỗng

```python
assert trie.insert("")
assert trie.contains("")
assert trie.count_prefix("") == 1
assert len(trie) == 1
assert trie.keys_with_prefix("") == [""]

assert not trie.insert("")
assert len(trie) == 1

assert trie.insert("a")
assert trie.contains("")
assert trie.contains("a")
assert trie.count_prefix("") == 2

assert trie.delete("")
assert not trie.contains("")
assert trie.contains("a")
assert trie.count_prefix("") == 1
assert trie.delete("a")
assert len(trie) == 0
```

Các bài kiểm thử này bám trực tiếp vào **hậu điều kiện** của từng thao tác. Nếu một cài đặt khác có cùng hợp đồng nhưng dùng mảng con thay vì dictionary, các kết quả quan sát được vẫn phải giống nhau.

## 12. Kiểm chứng bất biến bằng mô hình tham chiếu

Một cách mạnh để kiểm tra `TrieSet` là dùng `set[str]` làm **nguồn chân lý** cho tập khóa logic. Ta chỉ dùng nó trong kiểm thử, không dùng thay cho trie cần học.

### 12.1. Đối chiếu trạng thái với Set

```python
def check_against_reference(trie, reference, probes):
    assert len(trie) == len(reference)
    assert trie.count_prefix("") == len(reference)

    for text in probes:
        assert trie.contains(text) == (text in reference)
        expected = sum(
            key.startswith(text) for key in reference
        )
        assert trie.count_prefix(text) == expected


operations = [
    ("insert", "an"),
    ("insert", "anh"),
    ("insert", "an"),     # Trùng
    ("insert", ""),
    ("delete", "an"),
    ("insert", "ao"),
    ("delete", "missing"),  # Không có
    ("delete", "anh"),
    ("delete", ""),
    ("delete", "ao"),
]

test_trie = TrieSet()
reference = set()

for action, key in operations:
    if action == "insert":
        changed = test_trie.insert(key)
        expected_change = key not in reference
        reference.add(key)
    else:
        changed = test_trie.delete(key)
        expected_change = key in reference
        reference.discard(key)

    assert changed == expected_change
    check_against_reference(
        test_trie, reference, ["", "a", "an", "anh", "ao", "x"]
    )
```

Hàm `check_against_reference` có thể quét toàn bộ `reference` để tính số khóa theo tiền tố, nên không dùng làm benchmark hiệu năng của trie. Mục đích là kiểm tra **tính đúng** bằng một biểu diễn độc lập.

### 12.2. Kiểm tra bộ đếm nút và nhánh chết

Đối với kiểm thử phát triển, ta có thể duyệt toàn bộ nút để kiểm tra:

```python
def validate_internal(trie):
    """Xác minh count(v) và không có nhánh chết."""
    seen = set()
    totals = {}
    stack = [(trie._root, False)]

    while stack:
        node, expanded = stack.pop()

        if not expanded:
            assert node not in seen  # Không có chu trình/chia sẻ nút.
            seen.add(node)
            stack.append((node, True))

            for char, child in node.children.items():
                assert isinstance(char, str) and len(char) == 1
                stack.append((child, False))
        else:
            subtotal = int(node.terminal)
            for child in node.children.values():
                assert child.subtree_count > 0
                subtotal += totals[child]

            assert subtotal == node.subtree_count
            totals[node] = subtotal

    assert totals[trie._root] == len(trie)


sample = TrieSet()
for item in ["", "an", "anh", "ao", "ba", "ban"]:
    sample.insert(item)
    validate_internal(sample)

for item in ["an", "anh", "ba", "", "ban", "ao"]:
    sample.delete(item)
    validate_internal(sample)

assert len(sample) == 0
```

Trong Python, đối tượng `TrieNode` ở mã trên có thể được dùng làm khóa trong `set` hoặc `dict` theo danh tính đối tượng vì lớp không định nghĩa lại quy tắc `__eq__`/`__hash__`.

Hàm kiểm tra này duyệt toàn bộ cấu trúc và giữ bảng phụ theo nút, nên chi phí ít nhất O(N); nó là công cụ **debug**, không phải thao tác cần thực hiện sau mỗi cập nhật trong sản phẩm.

## 13. Chứng minh tính đúng của tìm, chèn và xóa

### 13.1. Tìm: bất biến của vòng lặp

Trong `contains(word)`, sau khi đọc `i` ký hiệu đầu tiên, nếu chưa thất bại thì biến `node` trỏ tới nút biểu diễn chính tiền tố `word[:i]`.

- **Khởi tạo:** với `i=0`, `node=root` biểu diễn `""`.
- **Duy trì:** nếu có cạnh mang ký hiệu tiếp theo, đi theo nó làm nút mới biểu diễn tiền tố dài `i+1`; nếu không có, không thể có khóa với đường đó.
- **Kết thúc:** khi đã đọc đủ `L` ký hiệu, `node` biểu diễn `word`. Khóa có tồn tại khi và chỉ khi `node.terminal=True`.

Vì không có phép ghi trạng thái, `contains` không làm thay đổi tập `S`.

### 13.2. Chèn: vì sao số khóa tăng đúng một?

Giả sử trie trước thao tác biểu diễn tập `S` hợp lệ.

**Nếu `word∈S`:** đường tồn tại, nút cuối terminal. Hàm trả False mà không cập nhật trạng thái. Tập sau vẫn là `S`.

**Nếu `word∉S`:** hàm tạo các cạnh còn thiếu tới khóa rồi đặt terminal ở nút cuối. Những khóa cũ có terminal không bị thay đổi. Tập sau là:

\[
S' = S\cup\{word\}.
\]

Mỗi nút trên đường từ gốc đến `word` có thêm **chính một khóa** trong cây con nên bộ đếm tăng 1 là đúng; các nút khác không đổi. Vì vậy mọi bất biến được giữ.

### 13.3. Xóa: vì sao không mất khóa khác?

**Nếu `word∉S`:** đường thiếu hoặc nút cuối không terminal; hàm trả False trước khi sửa bất kỳ trạng thái nào.

**Nếu `word∈S`:** bỏ terminal tại nút của `word`, làm tập khóa thành:

\[
S'=S\setminus\{word\}.
\]

Chỉ các nút thuộc đường đi của `word` mất một khóa trong cây con, nên chỉ bộ đếm của chúng giảm 1.

Khi cắt cạnh `parent→child`, thuật toán yêu cầu `child.subtree_count=0`. Theo bất biến, không có khóa còn lại nào trong cây con đó; việc cắt không làm mất khóa thuộc `S'`. Khi bộ đếm dương, nó dừng và giữ các nhánh dùng chung.

Gốc được giữ lại trong mọi trường hợp. Do đó cấu trúc vẫn biểu diễn đúng `S'` và thỏa các bất biến sau xóa.

### 13.4. Quy nạp trên chuỗi thao tác

Trie rỗng ban đầu thỏa bất biến. Nếu tìm giữ nguyên trạng thái, chèn và xóa đều bảo toàn bất biến như trên, thì theo quy nạp số thao tác, bất biến vẫn đúng sau **mọi chuỗi thao tác hợp lệ** của `contains`, `insert` và `delete`.

Đây là cơ sở để tin rằng các bài kiểm thử không chỉ đúng với năm từ minh họa, dù kiểm thử vẫn cần thiết để tìm lỗi cài đặt.

## 14. Phân tích độ phức tạp thời gian

Giả sử mỗi nút dùng dictionary ánh xạ một ký hiệu đã được đọc tới nút con, thao tác lấy/chèn/xóa một mục dictionary có chi phí **O(1) kỳ vọng** trong điều kiện băm phù hợp, và kiểm tra/đổi cờ terminal, cập nhật một bộ đếm có chi phí O(1).

| Phép toán | Số bước phụ thuộc khóa | Thời gian theo mô hình | Bộ nhớ phụ |
| --- | --- | --- | --- |
| `contains(word)` | Theo tối đa `L` cạnh | O(L+1) kỳ vọng | O(1) |
| `starts_with(prefix)` | Theo tối đa `P` cạnh | O(P+1) kỳ vọng | O(1) |
| `count_prefix(prefix)` | Theo `P` cạnh rồi đọc count | O(P+1) kỳ vọng | O(1) |
| `insert(word)` | Theo/tạo tối đa `L` cạnh; cập nhật `L+1` nút | O(L+1) kỳ vọng | O(L+1) cho `path`, chưa kể nút mới |
| `delete(word)` | Đi xuống và có thể dọn lên tối đa `L` nút | O(L+1) kỳ vọng | O(L+1) cho `path` |
| `len(trie)` | Đọc một biến đếm | O(1) | O(1) |

Ký hiệu `+1` bao quát trường hợp khóa hoặc tiền tố rỗng; trong bối cảnh `L≥1` người ta thường viết ngắn gọn O(L).

### 14.1. Tại sao không phải O(log n) như BST?

Trong trie, đường tìm một khóa dài `L` đi theo ký hiệu **trong khóa**, nên số bước phụ thuộc `L`, không trực tiếp là chiều cao của BST theo số nút chứa khóa đầy đủ.

Một BST cân bằng lưu `n` khóa có thể tìm trong O(log n) **lần so sánh khóa**. Nhưng nếu khóa là chuỗi dài, một phép so sánh có thể phải đọc nhiều ký hiệu. Vì vậy muốn so sánh thời gian thật phải tính cả **giá một phép so sánh**.

### 14.2. Tại sao O(L) không phải chặn xấu nhất tuyệt đối?

Nếu dictionary được dùng làm bảng con, chi phí lấy một cạnh được phân tích theo mô hình hash. Một phát biểu O(L) **kỳ vọng** cần giả định việc chọn cạnh trung bình O(1). Trong trường hợp xấu nhất của một bảng băm tổng quát, nhiều va chạm có thể khiến thời gian tăng.

Nếu bảng chữ cái nhỏ và cố định, dùng **mảng con trực tiếp** có thể bảo đảm chọn một cạnh O(1) theo mô hình RAM, nhưng trả thêm bộ nhớ cho các ô con không dùng.

### 14.3. Chi phí do cấp phát và dọn nhánh

Một lần `insert` có thể tạo tới `L` nút và dictionary mới. Một lần `delete` có thể cắt tới `L` cạnh và làm tối đa `L` nút trở nên không còn được tham chiếu từ trie.

Thời gian cấp phát/thu hồi cụ thể phụ thuộc runtime. Khi phát biểu O(L), ta dùng mô hình phổ thông trong đó tạo và kết nối một nút nhỏ có chi phí O(1) mỗi nút; đó không phải lời hứa về độ trễ từng lần cấp phát của Python hay bộ quản lý bộ nhớ.

### 14.4. Đếm chính xác số nút được tạo mới

Nếu chèn một khóa dài `L` và tiền tố dài nhất đã tồn tại trong trie có độ dài `r`, số nút mới là:

\[
L-r,
\]

với `0≤r≤L`, miễn là trước chèn đường tồn tại đến đúng `r` ký hiệu và thiếu ký hiệu tiếp theo. Nếu toàn bộ đường đã có nhưng nút cuối chưa terminal, ta có `r=L` và tạo **0 nút**, dù thêm được một khóa mới.

Khi chèn một từ đã có sẵn, cũng tạo 0 nút và không tăng số khóa.

## 15. Phân tích bộ nhớ và chia sẻ tiền tố

Gọi `T` là tổng độ dài của các khóa phân biệt hiện có, `N` là số nút của trie không nén tính cả gốc.

Mỗi lần chèn một khóa dài `L` tạo **nhiều nhất `L` nút mới**, nên:

\[
1\le N\le T+1.
\]

Nếu nhiều khóa cùng chia sẻ tiền tố dài, số nút có thể nhỏ hơn đáng kể tổng số ký hiệu của các chuỗi. Nhưng mỗi nút trong cài đặt Python còn chứa:

- Đối tượng `TrieNode`.
- Dictionary `children`, kể cả khi chưa có con.
- Cờ `terminal`.
- Số nguyên `subtree_count`.
- Overhead của runtime và bộ cấp phát.

Vì thế, kết luận “trie chỉ cần O(T) nút” **không đồng nghĩa** “luôn tiết kiệm byte hơn một Hash Set lưu chuỗi”. Cần xem phân bố tiền tố và số byte mỗi nút.

### 15.1. Ví dụ số nút

Với `S={"an","anh","ao","ba","ban"}`:

- Tổng độ dài khóa: `T=2+3+2+2+3=12`.
- Các tiền tố không rỗng phân biệt: `a, an, anh, ao, b, ba, ban` — tổng 7 nút.
- Cộng gốc: `N=8`.

Nhờ dùng chung tiền tố, không cần một đường riêng dài tổng cộng 12 ký hiệu. Nhưng một chuỗi được lưu trong mảng có thể có biểu diễn compact hơn so với nhiều đối tượng nút, nên không thể so sánh byte chỉ từ `N`.

### 15.2. Sau khi xóa có còn nút chết không?

Với bất biến dọn nhánh, sau khi xóa khóa cuối cùng của một nhánh, các nút `subtree_count=0` trên nhánh đó đều bị cắt. Số nút còn lại tương ứng các tiền tố vẫn được dùng và gốc.

Nếu một cài đặt chọn **không dọn nhánh**, bộ nhớ có thể tăng theo lịch sử các khóa đã từng chèn, không còn chặn tốt theo `T` của tập khóa **hiện tại**. Đồng thời `starts_with` chỉ kiểm tra đường có thể trả True cho tiền tố không còn khóa sống. Phải điều chỉnh hợp đồng hoặc cách kiểm tra nếu giữ nút chết.

### 15.3. Mảng con cố định và dictionary con

| Biểu diễn bảng con | Ưu điểm | Đánh đổi |
| --- | --- | --- |
| Mảng `σ` ô trên mỗi nút | Truy cập cạnh O(1) RAM theo chỉ số ký hiệu | Có thể dùng O(σN) ô ngay cả khi nhiều cạnh thiếu |
| Dictionary con | Chỉ lưu cạnh thực có, linh hoạt Unicode | Overhead hash và O(1) kỳ vọng thay vì bảo đảm RAM thuần |
| Danh sách các cặp ký hiệu–con | Tiết kiệm với ít con và cấu trúc đơn giản | Chọn cạnh bằng quét có thể O(d) với `d` con |
| Danh sách con đã sắp | Có thể tìm nhị phân theo nhãn | Chèn vào danh sách mảng có thể phải dịch |

Bài toán “tìm/chèn/xóa khóa” có thể có cùng API ở mọi biểu diễn, nhưng chi phí chọn một cạnh và số byte mỗi nút khác nhau.

## 16. Unicode, chữ hoa và khái niệm “cùng một khóa”

Cài đặt `TrieSet` ở trên dùng `for char in word`. Trong Python, biến `char` lấy từng **Unicode code point**, không phải từng byte UTF-8 hay grapheme cluster.

Hai chuỗi có thể nhìn giống nhau nhưng khác dãy code point. Ví dụ:

```python
composed = "café"
decomposed = "cafe\u0301"

assert composed != decomposed
```

Nếu ứng dụng muốn xem chúng là **cùng một khóa**, phải chuẩn hóa **trước mọi thao tác**, không chỉ trước chèn.

### 16.1. Chuẩn hóa nhất quán

```python
import unicodedata


def normalized_key(text):
    if not isinstance(text, str):
        raise TypeError("cần chuỗi str")
    return unicodedata.normalize("NFC", text)


trie = TrieSet()
assert trie.insert(normalized_key("café"))
assert trie.contains(normalized_key("cafe\u0301"))
assert not trie.insert(normalized_key("cafe\u0301"))
assert trie.delete(normalized_key("cafe\u0301"))
assert not trie.contains(normalized_key("café"))
```

Nếu quên chuẩn hóa tại `delete`, ta có thể không xóa được khóa đã lưu; nếu quên tại `contains`, ta có thể báo thiếu một từ mà người dùng thấy giống hệt.

### 16.2. Phân biệt hoa/thường và dấu là lựa chọn riêng

- `NFC` xử lý những dạng biểu diễn Unicode tương đương theo chuẩn này.
- `casefold()` có thể giúp tìm không phân biệt một số khác biệt hoa/thường, nhưng nó cũng có thể làm đổi dãy ký hiệu.
- Bỏ dấu để tìm gần đúng là một quy tắc khác, có thể làm hai khóa khác nhau bị hợp nhất.

Không có lựa chọn nào tự đúng cho mọi từ điển. **Ngữ nghĩa khóa và thứ tự chuẩn hóa là một phần của hợp đồng**; độ phức tạp phải xét độ dài sau khi chuẩn hóa hoặc cộng chi phí chuẩn hóa riêng.

### 16.3. Cẩn thận với byte và code point

Nếu trie lưu byte UTF-8 thay cho chuỗi Python, một ký tự tiếng Việt có thể chiếm nhiều cạnh byte. Khi đó `L` phải là số byte thay vì số code point.

Hai cài đặt vẫn có thể cùng hành vi nếu chuẩn hóa và giải mã thống nhất, nhưng số bước, bộ nhớ và cách xử lý tiền tố trong lúc nhập liệu có thể khác nhau.

## 17. So sánh ba thao tác với các cấu trúc khác

| Cấu trúc | Tìm khóa chính xác | Chèn khóa | Xóa khóa | Điểm cần cân nhắc |
| --- | --- | --- | --- | --- |
| Trie không nén | O(L) kỳ vọng theo cạnh | O(L) kỳ vọng | O(L) kỳ vọng | Tốt cho tiền tố; nhiều nút và metadata |
| Hash Set | O(1) kỳ vọng theo số khóa nếu hash/so sánh O(1) | O(1) kỳ vọng/khấu hao theo giả định | O(1) kỳ vọng | Với chuỗi dài, tính hash có thể O(L); không tự hỗ trợ prefix |
| Mảng chưa sắp | O(n) lần so sánh khóa | Thêm cuối O(1) khấu hao | Có thể O(n) để tìm rồi xóa | Gọn và duyệt liên tiếp, nhưng tìm tuyến tính |
| Mảng đã sắp | O(log n) lần so sánh khóa | O(n) khi cần dịch phần tử | O(n) khi cần dịch phần tử | Thuận tiện duyệt theo thứ tự |
| BST tự cân bằng | O(log n) phép so sánh khóa | O(log n) phép so sánh + cập nhật | O(log n) phép so sánh + cập nhật | Có thứ tự và chặn theo chiều cao |

**Các đơn vị không hoàn toàn giống nhau:** Trie đếm lần theo ký hiệu, BST đếm phép so sánh **toàn khóa**, còn Hash Set phụ thuộc phép băm/so sánh khóa. Nếu khóa rất dài, phải tính chi phí xử lý ký tự khi so sánh các cấu trúc.

### 17.1. Khi Trie có lợi

Một hệ thống có nhiều truy vấn kiểu:

- Kiểm tra một từ đã lưu.
- Hỏi có từ nào bắt đầu bằng một tiền tố.
- Đếm từ theo tiền tố.
- Gợi ý một số từ có tiền tố đã gõ.

Trie phù hợp vì ba thao tác trọng tâm xây dựng cùng hệ thống đường tiền tố và mở đường cho truy vấn tiền tố mà không cần quét toàn bộ khóa.

### 17.2. Khi Hash Set có thể đơn giản hơn

Nếu workload chỉ gồm **tìm chính xác, chèn, xóa** khóa nguyên vẹn và không cần truy vấn tiền tố, Hash Set có thể đơn giản hơn và dùng bộ nhớ hiệu quả hơn trong nhiều môi trường.

Tuy nhiên, chặn kỳ vọng phụ thuộc mô hình băm và khóa. Không nên nói “Hash Set luôn tốt hơn Trie” hoặc ngược lại mà chưa biết tần suất thao tác, độ dài khóa và giới hạn bộ nhớ.

## 18. Những lỗi thường gặp và cách khắc phục

| Lỗi | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Tìm chỉ kiểm tra đường đi | `"a"` bị coi là khóa khi chỉ có `"an"` | Kiểm tra `terminal` ở nút cuối |
| Coi chỉ nút lá mới kết thúc khóa | Bỏ sót `"an"` khi còn `"anh"` | Cho phép terminal tại nút có con |
| Chèn từ dài làm bỏ terminal của từ ngắn | Mất khóa là tiền tố của khóa mới | Không sửa terminal của nút cũ trên đường |
| Chèn trùng vẫn tăng `size/count` | Đếm sai số khóa | Chỉ tăng khi nút cuối chưa terminal |
| Xóa một khóa bằng cách cắt toàn bộ đường | Làm mất khóa khác chung tiền tố | Chỉ cắt cây con không còn khóa |
| Xóa từ dài chỉ bỏ terminal, không dọn nhánh | Giữ đường chết, `starts_with` có thể báo sai | Dọn nhánh hoặc sửa hợp đồng prefix |
| Xóa tiền tố chưa terminal vẫn giảm count | Bộ đếm âm hoặc thiếu khóa | Kiểm tra terminal trước khi sửa |
| Không giữ gốc khi trie rỗng | Các thao tác sau không còn điểm bắt đầu | Gốc là trạng thái thường trực |
| Xử lý `""` như từ bất hợp lệ dù API cho phép | Hành vi không nhất quán | Chèn/xóa qua terminal tại gốc |
| Tra bảng con bằng cách tạo nút vô điều kiện | Tốn bộ nhớ/cấp phát không cần thiết | Chỉ tạo nút khi thiếu cạnh |
| Không chuẩn hóa Unicode nhất quán | Tìm/xóa thiếu khóa nhìn giống nhau | Chuẩn hóa trước mọi thao tác |
| Chỉ thử khóa phân biệt không có tiền tố chung | Bỏ sót lỗi xóa nhánh | Thử khóa là tiền tố của nhau |
| Chạy DFS đệ quy cho khóa cực dài | Có thể vượt giới hạn đệ quy | Dùng vòng lặp và đường `path` như bài |
| Gọi O(L) là xấu nhất cho mọi dictionary | Thiếu giả định hash và cấp phát | Nêu mô hình và loại chặn |

## 19. Bài tập vận dụng kèm gợi ý

### Bài 1 — Truy vết tìm thành công

Trie lưu `{"an","anh","ao","ba"}`. Hãy viết các nút được đi qua khi tìm `"anh"` và giải thích điều kiện trả True.

**Gợi ý:** Gốc → `a` → `an` → `anh`. Mỗi cạnh tồn tại và nút cuối `anh` terminal=True.

### Bài 2 — Hai kiểu tìm thất bại

Với cùng trie, giải thích vì sao `contains("a")` và `contains("ang")` đều False nhưng thất bại ở các bước khác nhau.

**Gợi ý:** `a` có đường đi nhưng terminal=False; `ang` thiếu cạnh `g` sau nút `an`.

### Bài 3 — Chèn từ dài sau từ ngắn

Ban đầu `S={"an"}`. Chèn `"anh"`. Có bao nhiêu nút mới và điều gì xảy ra với `contains("an")`?

**Gợi ý:** Chỉ tạo nút `h`. `an` vẫn terminal, nên `contains("an")` tiếp tục True. Số khóa tăng từ 1 lên 2.

### Bài 4 — Chèn từ ngắn sau từ dài

Ban đầu `S={"anh"}`. Chèn `"an"`. Có cần tạo nút không? Bộ đếm nào tăng?

**Gợi ý:** Không tạo nút mới; đặt terminal ở nút `an`. Tăng bộ đếm của gốc, `a` và `an`, mỗi nút đúng 1. Bộ đếm của `anh` không đổi.

### Bài 5 — Chèn trùng

Trie đang lưu `{"an","anh","ao"}`. Gọi `insert("an")` thêm ba lần. Hãy tính `len` và `count_prefix("an")` cuối cùng.

**Gợi ý:** `len=3`, `count_prefix("an")=2`. TrieSet lưu khóa phân biệt, nên chèn trùng không tăng `size` hay bộ đếm.

### Bài 6 — Xóa tiền tố và giữ hậu duệ

Ban đầu `S={"an","anh","ang"}`. Xóa `"an"`. Nút nào còn? Kết quả của `starts_with("an")` và `contains("an")` là gì?

**Gợi ý:** Giữ nút `an` và hai nhánh `h,g` vì `anh` và `ang` còn sống. `starts_with("an")=True`, `contains("an")=False`.

### Bài 7 — Xóa nhánh cuối

Ban đầu `S={"cat","car","dog"}`. Xóa `"cat"` rồi `"car"`. Nhánh nào có thể bị dọn và nhánh nào phải còn nguyên?

**Gợi ý:** Sau xóa `cat`, nhánh `t` mất, `c→a→r` còn. Sau xóa `car`, toàn bộ nhánh `c→a→r` không còn khóa nên có thể bị cắt. Nhánh `d→o→g` phải còn nguyên.

### Bài 8 — Xóa từ không phải khóa

Trie chỉ lưu `"anh"`. Gọi `delete("an")`. Kết quả và trạng thái bộ đếm sau thao tác ra sao?

**Gợi ý:** Trả False, vì nút `an` không terminal. Mọi bộ đếm và dấu terminal giữ nguyên; `contains("anh")` vẫn True.

### Bài 9 — Xử lý chuỗi rỗng

Trie rỗng cho phép lưu `""`. Sau `insert("")`, điều gì xảy ra với `root.terminal`, `root.subtree_count` và `len`? Sau `delete("")` thì sao?

**Gợi ý:** Sau thêm: terminal=True, count=1, len=1; không tạo cạnh. Sau xóa: terminal=False, count=0, len=0; vẫn giữ gốc.

### Bài 10 — Phân tích số nút tạo mới

Một trie đã có đường `a→b→c` nhưng không có nhánh `d` sau `abc`. Chèn `"abcde"` tạo bao nhiêu nút mới? Chỉ rõ tiền tố chung dài nhất.

**Gợi ý:** Tiền tố chung `"abc"` dài 3; khóa mới dài 5, tạo hai nút `d,e`. Công thức `L-r=5-3=2`.

### Bài 11 — Độ phức tạp

Giả sử khóa dài `L=100` ký hiệu, mỗi tra dictionary con tốn O(1) kỳ vọng. Hãy nêu chi phí tìm/chèn/xóa và bộ nhớ tạm của cài đặt dùng `path`.

**Gợi ý:** Thời gian mỗi thao tác O(L+1) kỳ vọng; `contains` bộ nhớ phụ O(1); `insert/delete` giữ `path` O(L+1). Chèn có thể tạo tối đa `L` nút mới, khác với bộ nhớ phụ tạm.

### Bài 12 — Unicode và xóa

Một trie lưu khóa chuẩn hóa NFC từ `"café"` nhưng nhận yêu cầu xóa bằng `"cafe\u0301"` chưa chuẩn hóa. Vì sao có thể trả False?

**Gợi ý:** Dãy code point khác nhau. Phải dùng cùng quy tắc chuẩn hóa NFC trước khi chèn, tìm, xóa.

### Bài 13 — Kiểm thử bất biến

Cho `S={"an","anh","ao","ba"}`. Hãy tính `subtree_count` ở gốc, `a` và `an`. Sau khi xóa `"an"`, các bộ đếm đổi thế nào?

**Gợi ý:** Trước xóa: gốc 4, `a` 3, `an` 2. Sau xóa: gốc 3, `a` 2, `an` 1; nút `an` vẫn tồn tại vì còn `anh`.

### Bài 14 — Chọn cấu trúc

Một hệ thống chỉ cần tìm/chèn/xóa mã đơn lẻ; hệ thống khác còn cần gợi ý các mã bắt đầu bằng tiền tố. Hãy nêu lý do cân nhắc Hash Set hoặc Trie.

**Gợi ý:** Hash Set phù hợp cho truy vấn khóa đầy đủ nếu băm tốt và không cần tiền tố. Trie tổ chức theo đường tiền tố, nên thuận lợi cho gợi ý và đếm theo tiền tố nhưng có overhead nút, bảng con. Quyết định phụ thuộc workload, bộ nhớ và cách chuẩn hóa khóa.

## 20. Mẫu phân tích trước khi cài đặt tìm/chèn/xóa

Khi thực hiện một bài tập mới về trie, hãy tự trả lời:

```text
1. Hợp đồng:
   - Lưu Set, Multiset hay Map?
   - Khóa trùng được bỏ qua, cộng tần suất hay cập nhật giá trị?
   - Cho phép khóa rỗng không?
   - Xóa khóa thiếu trả False hay ném lỗi?

2. Biểu diễn:
   - Mỗi cạnh là code point, byte hay nhóm ký tự?
   - children là dictionary, mảng hay cấu trúc khác?
   - Mỗi nút có terminal và subtree_count?
   - Gốc có được giữ khi không còn khóa?

3. Bất biến:
   - Một ký hiệu có tối đa một cạnh từ cùng nút?
   - terminal(v) biểu diễn đúng khóa label(v)?
   - subtree_count(v) bằng terminal(v) + tổng count con?
   - Nhánh không còn khóa có được cắt?

4. Tìm:
   - Có kiểm tra cạnh thiếu trước khi đi tiếp?
   - Có kiểm tra terminal sau khi đọc hết word?
   - Có thay đổi trạng thái ngoài ý muốn?

5. Chèn:
   - Có dùng lại các cạnh đã tồn tại?
   - Chỉ tạo nút khi thực sự thiếu?
   - Khóa trùng có giữ nguyên size/count?
   - Khóa rỗng có đặt terminal ở root?

6. Xóa:
   - Có kiểm tra nút cuối terminal trước khi sửa?
   - Chỉ giảm count trên đường của khóa được xóa?
   - Chỉ cắt child khi không còn khóa trong cây con?
   - Có giữ các khóa chung tiền tố?

7. Chi phí và kiểm thử:
   - Độ dài khóa L, tổng ký hiệu T, số nút N?
   - O(L) là theo giả định hash hay truy cập mảng trực tiếp?
   - Path giữ bao nhiêu bộ nhớ phụ?
   - Test khóa thiếu, chèn trùng, xóa tiền tố và Unicode?
```

**Kết luận:** Tìm, chèn và xóa trong trie đều bắt đầu bằng việc đi theo **các ký hiệu của khóa**. Tìm phải kiểm tra dấu `terminal` ở nút cuối; chèn phải dùng lại các tiền tố và chỉ tăng số khóa khi thực sự thêm mới; xóa phải xác nhận khóa tồn tại rồi cắt **chỉ những nhánh không còn được khóa khác sử dụng**. Khi kết hợp ba thuật toán với bất biến bộ đếm, hợp đồng chuỗi rỗng, chuẩn hóa Unicode và mô hình độ phức tạp theo chiều dài khóa, ta có một cấu trúc chỉ mục chuỗi vừa đúng về hành vi vừa có cơ sở rõ ràng để đánh giá hiệu năng.
