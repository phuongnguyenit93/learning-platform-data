# Truy vấn tiền tố và từ điển bằng trie

## 1. Vì sao cần một cây tiền tố?

Một hệ thống có thể chứa hàng nghìn hoặc hàng triệu từ, tên người dùng, khóa cấu hình, mã sản phẩm hay truy vấn tìm kiếm. Ta muốn trả lời nhanh các câu hỏi:

- Từ `w` có tồn tại trong từ điển không?
- Có bao nhiêu **lần lưu** từ `w` nếu đầu vào cho phép trùng lặp?
- Có bao nhiêu từ được lưu bắt đầu bằng tiền tố `p`?
- Hãy gợi ý tối đa `k` từ bắt đầu bằng `p`, theo thứ tự từ điển.
- Thêm một từ mới, xóa một lần xuất hiện của từ, hoặc xóa hoàn toàn từ khi số lần xuất hiện về 0.

**Trie** (phát âm thường là “try”), còn gọi là **cây tiền tố / prefix tree**, được thiết kế cho các bài toán này. Điểm đặc trưng: đường đi từ gốc theo các nhãn ký tự biểu diễn **một tiền tố**. Những từ có chung phần đầu sẽ dùng chung đường đi thay vì lưu độc lập toàn bộ tiền tố ấy.

Ví dụ khi lưu `app`, `apple`, `apply` và `ape`, tất cả từ bắt đầu bằng `a` dùng chung nút `a`, nhiều từ dùng tiếp nhánh `ap`, còn `app`, `apple`, `apply` dùng chung nhánh `app`.

Một tìm kiếm từ chính xác hoặc tiền tố có độ dài `L` không cần so với từng mục từ trong từ điển. Nó chỉ lần theo **tối đa `L` ký tự** từ gốc; vì vậy độ phức tạp chủ yếu phụ thuộc **độ dài khóa truy vấn**, không phụ thuộc trực tiếp vào số từ đã lưu.

Trong bài này ta thiết kế trie **động** (có insert/delete), phân biệt **số lần xuất hiện** với **số từ khác nhau**, hỗ trợ **từ rỗng**, liệt kê gợi ý theo thứ tự Java `String.compareTo`, chứng minh bất biến và viết **Java 17+ hoàn chỉnh** có kiểm thử đối chứng bằng cấu trúc dữ liệu độc lập.

## 2. Mô hình trie bằng các nút và cạnh ký tự

Một trie thông thường có:

- **Nút gốc (root)** biểu diễn tiền tố rỗng `""`.
- Mỗi cạnh đi ra từ một nút được gắn nhãn **một ký tự**.
- Từ cùng một nút, không có hai cạnh con mang **cùng nhãn ký tự**.
- Đường đi từ root qua các nhãn `c_1,c_2,\ldots,c_L` biểu diễn tiền tố `c_1c_2\cdots c_L`.
- Một nút có thể đánh dấu **kết thúc từ** và đồng thời còn có nút con.

Ví dụ, trie lưu `app`, `apple`, `apply`, `ape`:

```text
(root)
  |
  a
  |
  p  [tiền tố "ap", chưa phải từ]
  | \
  p  e*        * nghĩa là kết thúc từ
  |
  p*           "app" là một từ
  |
  l
 / \
e*   y*

Từ lưu: "ape", "app", "apple", "apply"
```

**Lưu ý:** sơ đồ trên chỉ để minh họa đường chia sẻ tiền tố. Khi vẽ chính xác theo cạnh từng ký tự thì sau `"ap"` có nhánh `'e'` tới từ `"ape"` và nhánh `'p'` tới `"app"`. Từ `"app"` có nhánh `'l'`, rồi `'e'` và `'y'` tạo `"apple"` và `"apply"`.

Một cách hình dung cụ thể hơn:

```text
(root)
   |
  'a'
   |
  'p' -------- 'e' [END: ape]
   |
  'p' [END: app]
   |
  'l'
  / \
'e' 'y'
 |   |
END END
apple apply
```

**Điểm dễ nhầm:** nút ứng với `"app"` có thể là **nút kết thúc từ**, nhưng vẫn có các nút con vì `"apple"` và `"apply"` cũng bắt đầu bằng `"app"`. Do đó không thể xem “nút lá” là điều kiện duy nhất để xác định một từ có tồn tại.

### 2.1. Đường đi tồn tại chưa có nghĩa từ tồn tại

Nếu đã lưu `"apple"` thì đường đi `a\to p\to p` tồn tại. Nhưng chưa chắc từ `"app"` đã được lưu.

Hai câu hỏi khác nhau:

- `startsWith("app")`: có ít nhất một từ đã lưu bắt đầu bằng `"app"` không?
- `contains("app")`: có đúng từ `"app"` được lưu không?

Trong trie đơn giản, chỉ cần cờ `isEnd` để trả lời câu thứ hai. Trong trie hỗ trợ **từ trùng lặp**, dùng bộ đếm kết thúc từ để mô tả chính xác hơn.

## 3. Trie đa tập (multiset): passCount và endCount

Để hỗ trợ chèn cùng từ nhiều lần và xóa đúng **một lần xuất hiện**, mỗi nút có hai bộ đếm:

- `endCount(v)`: số lần lưu **chính xác** từ được biểu diễn bằng đường từ root tới `v`.
- `passCount(v)`: số lần lưu các từ có **tiền tố** là đường tới `v`, tính cả những từ kết thúc ngay tại `v`.

Ví dụ lưu:

```text
"app"   2 lần
"apple" 1 lần
"apply" 1 lần
"ape"   1 lần
```

Ta có:

| Đường từ root | `passCount` | `endCount` |
|---|---:|---:|
| `""` (root) | 5 | 0 |
| `"a"` | 5 | 0 |
| `"ap"` | 5 | 0 |
| `"ape"` | 1 | 1 |
| `"app"` | 4 | 2 |
| `"appl"` | 2 | 0 |
| `"apple"` | 1 | 1 |
| `"apply"` | 1 | 1 |

Cụ thể:

\[
countPrefix("ap")=5,
\]

vì có năm lần lưu từ bắt đầu bằng `ap` (từ `app` được tính **hai lần**).

\[
countExact("app")=2.
\]

Trong khi đó, nếu yêu cầu **số từ phân biệt** bắt đầu bằng `ap` thì chỉ có `4` từ: `ape, app, apple, apply`. Hai đại lượng không được đánh đồng.

### 3.1. Bất biến đếm quan trọng nhất

Ở mọi nút `v` đang tồn tại trong trie:

\[
\boxed{
passCount(v)=endCount(v)+
\sum_{u\text{ là con của }v}passCount(u).
}
\]

Vì mọi từ có tiền tố của `v` hoặc **kết thúc ngay ở `v`**, hoặc đi tiếp qua **đúng một cạnh con**, các tập trường hợp này không giao nhau. Đây là công thức cộng trực tiếp số lần xuất hiện.

Hệ quả:

\[
0\le endCount(v)\le passCount(v).
\]

Với root:

\[
\boxed{passCount(root)=\text{tổng số lần lưu từ}.}
\]

Nếu từ điển rỗng, `passCount(root)=0`.

### 3.2. Từ rỗng là một trường hợp hợp lệ nếu API cho phép

Đường biểu diễn `""` chỉ gồm **nút root**. Nếu chèn `""` một lần:

- `endCount(root)` tăng `1`.
- `passCount(root)` tăng `1`.
- Không cần tạo nút con.

Nếu lưu `""` và `"app"`, thì:

```text
countExact("")   = 1
countPrefix("")  = 2
countPrefix("a") = 1
```

Tiền tố rỗng là tiền tố của **mọi chuỗi**, nên `countPrefix("")` chính là tổng số lần lưu từ. Nhưng `startsWith("")` trong bài này được định nghĩa là **“có ít nhất một từ đã lưu bắt đầu bằng tiền tố rỗng”**, tức `countPrefix("")>0`. Với từ điển hoàn toàn rỗng, kết quả `startsWith("")=false`.

Một số API quy ước không cho phép từ rỗng; bài này cho phép và kiểm thử đầy đủ. Khi giải bài thi, cần tuân thủ quy ước của đề.

## 4. Chèn từ (insert)

Với từ `w=c_0c_1\ldots c_{L-1}`:

1. Bắt đầu tại root, tăng `root.passCount`.
2. Duyệt từng ký tự `c_i` từ trái sang phải.
3. Nếu nút hiện tại chưa có cạnh con mang nhãn `c_i`, tạo nút mới.
4. Đi tới nút con ấy và tăng `passCount` của nó.
5. Tại nút cuối cùng, tăng `endCount`.
6. Nếu trước khi tăng, `endCount=0`, đây là **từ phân biệt mới** nên tăng bộ đếm tổng số từ phân biệt.

Pseudocode:

```text
insert(word):
    node = root
    node.passCount += 1

    for c in word:
        if node.children[c] missing:
            node.children[c] = new Node()
        node = node.children[c]
        node.passCount += 1

    if node.endCount == 0:
        distinctWords += 1
    node.endCount += 1
```

Nếu chèn `"app"` lần đầu, đường đi được tạo nếu chưa có. Nếu chèn `"app"` lần thứ hai, không tạo nhánh mới; chỉ tăng các bộ đếm trên đường hiện có.

### 4.1. Vì sao tăng passCount cả tại root và nút kết thúc?

Root đại diện cho tiền tố rỗng, của **mọi từ**. Nút kết thúc đại diện cho tiền tố đúng bằng từ, và **bản thân từ** cũng là một từ bắt đầu bằng tiền tố đó.

Nếu bỏ tăng `passCount` tại nút kết thúc, `countPrefix("app")` sẽ không tính những bản sao của từ `app`, dẫn tới sai.

### 4.2. Khi một từ là tiền tố của từ khác

Chèn `"app"` trước, sau đó chèn `"apple"`. Nút `"app"` có:

\[
endCount=1,\quad passCount=2.
\]

Một lần lưu kết thúc ngay ở `app`, một lần đi tiếp sang `apple`. Đây là trường hợp để kiểm tra bất biến `pass=end+\sum child.pass`.

## 5. Truy vấn từ chính xác và tiền tố

### 5.1. countExact(word)

Để tìm số lần xuất hiện **đúng từ `word`**:

- Đi từ root lần theo tất cả ký tự của `word`.
- Nếu thiếu bất kỳ cạnh nào, trả `0`.
- Nếu đi hết, trả `endCount` của nút cuối.

`contains(word)` có thể định nghĩa:

\[
\boxed{contains(word)\iff countExact(word)>0.}
\]

Ví dụ trie chỉ chứa `"apple"`:

```text
contains("apple") = true
contains("app")   = false
```

Đường `app` có tồn tại nhưng `endCount("app")=0`.

### 5.2. countPrefix(prefix)

Để đếm các **lần lưu từ** có tiền tố `prefix`:

- Đi theo đường ký tự của tiền tố.
- Nếu thiếu cạnh, trả `0`.
- Nếu có nút kết thúc đường, trả `passCount` của nút ấy.

`startsWith(prefix)` trong bài có nghĩa **tồn tại một từ đã lưu bắt đầu bằng prefix**:

\[
\boxed{startsWith(prefix)\iff countPrefix(prefix)>0.}
\]

Ví dụ:

```text
Lưu: "ape", "app", "app", "apple", "apply"

countExact("app")   = 2
countExact("ap")    = 0
countPrefix("ap")   = 5
countPrefix("app")  = 4
startsWith("ap")    = true
startsWith("cat")   = false
```

Một prefix có thể không phải là từ độc lập, nhưng vẫn có rất nhiều từ nằm dưới nhánh ấy.

### 5.3. Phân biệt “số lần lưu” và “số khóa duy nhất”

Với dữ liệu:

```text
app   x2
apple x1
apply x1
ape   x1
```

- `countPrefix("ap")=5` (theo **multiplicity**).
- `suggest("ap",10)` trả **4 từ phân biệt**: `[ape,app,apple,apply]`.
- `distinctWords=4`.

Nếu bài yêu cầu `distinctPrefix("ap")` trong `O(|prefix|)`, ta có thể duy trì thêm tại mỗi nút `distinctSubtreeCount`, tăng **chỉ khi** số lần lưu một từ chuyển từ 0 lên 1, giảm **chỉ khi** chuyển từ 1 về 0. Không thể lấy `passCount` làm số từ phân biệt trong trường hợp có bản sao.

Bản Java đầy đủ ở phần sau cung cấp tổng `distinctWords` toàn từ điển, còn danh sách gợi ý trả từ duy nhất theo thứ tự từ điển.

## 6. Xóa một lần xuất hiện an toàn (removeOne)

Thao tác xóa khó hơn chèn, bởi các nhánh có thể **được chia sẻ** bởi nhiều từ.

Giả sử đã lưu:

```text
"app"   2 lần
"apple" 1 lần
"apply" 1 lần
```

Nếu xóa **một lần** `"app"`:

```text
countExact("app"): 2 -> 1
countPrefix("app"): 4 -> 3
```

Nhánh `app` vẫn phải tồn tại vì còn một bản sao `app` và hai từ con.

Nếu xóa `"app"` lần hai:

```text
countExact("app"): 1 -> 0
countPrefix("app"): 3 -> 2
```

Nút `app` vẫn tồn tại vì `"apple"` và `"apply"` cần sử dụng nó. Chỉ `endCount` về `0`, không được xóa cả nhánh.

### 6.1. Thuật toán xóa đúng

1. **Kiểm tra từ tồn tại**: đi toàn bộ đường của `word` và xác nhận `endCount>0` ở nút cuối.
2. Nếu thiếu đường hoặc `endCount=0`: trả `false`, **không thay đổi bất kỳ bộ đếm nào**.
3. Lưu danh sách các nút trên đường (gồm root).
4. Giảm `endCount` ở nút cuối đúng `1`.
5. Giảm `passCount` ở root và mọi nút trên đường đúng `1`.
6. Nếu `endCount` chuyển từ `1` về `0`, giảm `distinctWords`.
7. Đi từ cuối đường ngược về gốc; nếu nút con có `passCount=0`, tháo cạnh nối từ nút cha đến nút con đó. Dừng khi gặp nút con vẫn có `passCount>0`.

Pseudocode:

```text
removeOne(word):
    path = [root]
    node = root

    for c in word:
        if node.children[c] missing:
            return false
        node = node.children[c]
        path.append(node)

    if node.endCount == 0:
        return false

    lastCopy = (node.endCount == 1)
    node.endCount -= 1

    for each x in path:
        x.passCount -= 1

    for i from word.length-1 downto 0:
        child = path[i+1]
        if child.passCount == 0:
            path[i].children.remove(word[i])
        else:
            break

    if lastCopy:
        distinctWords -= 1
    return true
```

### 6.2. Tại sao chỉ cắt khi passCount bằng 0?

Nếu `passCount(child)=0`, **không còn bất kỳ từ đã lưu nào** đi qua nút con ấy. Việc bỏ cả nhánh không làm mất từ.

Ngược lại, nếu `passCount(child)>0`, vẫn có từ đang sử dụng nhánh này. Cắt nhánh sẽ làm mất dữ liệu, kể cả khi `endCount(child)=0`.

Vì vậy, điều kiện dọn nhánh là:

\[
\boxed{passCount(child)=0}
\]

chứ **không phải** `endCount(child)=0`.

### 6.3. Xóa từ không tồn tại

Ví dụ trie chứa `"apple"` nhưng không chứa `"app"`. Gọi `removeOne("app")` phải trả `false`, dù đường `app` tồn tại. Không được giảm các bộ đếm theo đường này vì `endCount("app")=0`.

Nếu giảm `passCount` trước khi xác nhận tồn tại, ta có thể làm hỏng bất biến và thậm chí tạo bộ đếm âm.

### 6.4. Xóa từ rỗng

Với `word=""`, đường chỉ gồm root. Nếu `endCount(root)>0`:

- Giảm `endCount(root)`.
- Giảm `passCount(root)`.
- Không có cạnh con cần dọn.
- Nếu hết bản sao cuối của từ rỗng, giảm `distinctWords`.

Điều này nhất quán với công thức bất biến tại root.

## 7. Liệt kê từ theo tiền tố và gợi ý từ điển

Giả sử người dùng gõ `"app"`. Ta muốn gợi ý tối đa `k` từ phân biệt có tiền tố `"app"`.

Có hai giai đoạn:

1. Đi qua từng ký tự của `prefix` để tìm nút biểu diễn tiền tố. Nếu không tồn tại đường, trả danh sách rỗng.
2. Duyệt cây con bắt đầu từ nút đó theo thứ tự nhãn cạnh; với mỗi nút có `endCount>0`, ghi chuỗi của đường hiện tại vào kết quả.

Ví dụ:

```text
Các từ: "ape", "app", "apple", "apply"
prefix = "app"

Gợi ý theo thứ tự từ điển:
["app", "apple", "apply"]
```

### 7.1. Duyệt terminal trước các con

Một từ có thể là tiền tố của một từ dài hơn. Trong thứ tự từ điển thông thường so theo chuỗi đơn vị ký tự, từ ngắn hơn đứng trước khi toàn bộ tiền tố của nó trùng với từ dài hơn:

\[
"app"<"apple".
\]

Vì vậy, tại mỗi nút, nếu `endCount>0` thì phải **phát ra từ tại nút hiện tại trước** khi đi vào các cạnh con.

Sau đó duyệt các cạnh con theo thứ tự nhãn ký tự tăng dần. Khi đó DFS trả từ phân biệt theo thứ tự từ điển, không cần sắp xếp lại danh sách.

### 7.2. Tại sao dùng TreeMap trong Java?

Có nhiều cách lưu `children`:

- `HashMap<Character,Node>`: tra cứu trung bình gần `O(1)` nhưng thứ tự duyệt không được bảo đảm.
- `TreeMap<Character,Node>`: tra cứu `O(\log d)` với `d` nhánh ở nút, và **duyệt các nhãn có thứ tự tăng dần**.
- Mảng `Node[26]`: nhanh và đơn giản nếu miền ký tự được xác nhận chỉ gồm `a..z`; phải kiểm tra ký tự nằm trong miền.

Bài này chọn:

```java
TreeMap<Character, Node> children = new TreeMap<>();
```

để `suggest(prefix,limit)` có thứ tự **tương thích với `String.compareTo` của Java trên các đơn vị UTF-16**, và không giới hạn chỉ chữ cái Latin thường.

### 7.3. Limit là giới hạn số từ phân biệt, không phải số bản sao

Nếu `"app"` lưu 100 lần, nhưng `"apple"` một lần, thì `suggest("app",2)` trả:

```text
["app", "apple"]
```

chứ **không** trả `"app"` hai lần.

Muốn gợi ý theo **tần suất** hoặc điểm xếp hạng, ta cần một mô hình khác: duyệt các từ khớp rồi sắp xếp theo `endCount`, hoặc lưu metadata top-k ở mỗi nút và cập nhật nó khi thêm/xóa. Trie dùng `TreeMap` mặc định chỉ có thứ tự từ điển, **không phải bảng xếp hạng độ phổ biến**.

### 7.4. Có thể giới hạn đúng k kết quả

Trong DFS, mỗi khi số kết quả đã bằng `k` thì dừng. Vì vậy không cần liệt kê tất cả từ trong cây con rồi cắt danh sách.

Nhưng không nên nói chi phí luôn là `O(k)`: có thể phải đi qua nhiều nút trung gian trước khi gặp terminal, và việc tạo mỗi chuỗi kết quả tốn thời gian theo chiều dài từ đó.

Nếu `k=0`, trả danh sách rỗng ngay. Nếu `k<0`, API mẫu ném `IllegalArgumentException`.

### 7.5. Cách duyệt đệ quy và giới hạn độ sâu

Mã Java minh họa dùng DFS **đệ quy** cho dễ hiểu. Độ sâu ngăn xếp tối đa tương ứng chiều dài hậu tố sâu nhất được duyệt. Với một từ cực dài, chương trình có thể `StackOverflowError` dù truy vấn tìm từ thông thường vẫn an toàn vì nó dùng vòng lặp.

Trong hệ thống nhận khóa rất dài, có thể thay DFS đệ quy bằng **stack tường minh có iterator tại mỗi nút**, hoặc giới hạn độ dài khóa có căn cứ. Đây là giới hạn triển khai, không phải giới hạn của trie về mặt lý thuyết.

## 8. Mô phỏng cả chèn, truy vấn và xóa

Xét các thao tác theo thứ tự:

```text
insert("")
insert("app")
insert("apple")
insert("app")
insert("apply")
insert("ape")
insert("bat")
insert("banana")
insert("banana")
insert("bán")
insert("áo")
```

Tổng số lần lưu:

\[
1+2+1+1+1+1+2+1+1=11.
\]

Tổng số từ phân biệt là **9**:

```text
""
"ape"
"app"
"apple"
"apply"
"banana"
"bat"
"bán"
"áo"
```

Ở đây thứ tự hiển thị theo `String.compareTo` của Java, không phải thứ tự ngôn ngữ học tiếng Việt.

### 8.1. Kết quả truy vấn trước khi xóa

| Truy vấn | Kết quả | Lý do |
|---|---:|---|
| `totalWords()` | 11 | Tính cả từ lặp |
| `distinctWords()` | 9 | Mỗi khóa khác nhau tính một |
| `countExact("app")` | 2 | Chèn hai lần |
| `countExact("ap")` | 0 | Chỉ là tiền tố, chưa lưu thành từ |
| `countPrefix("ap")` | 5 | `ape` 1 + `app` 2 + `apple` 1 + `apply` 1 |
| `countPrefix("app")` | 4 | `app` 2 + `apple` 1 + `apply` 1 |
| `countPrefix("")` | 11 | Root đếm toàn bộ |
| `contains("apple")` | true | Một từ đầy đủ |
| `startsWith("ban")` | true | Có `banana` |
| `startsWith("cat")` | false | Không có nhánh này |

Gợi ý:

```text
suggest("ap",3) = ["ape","app","apple"]
suggest("app",10) = ["app","apple","apply"]
suggest("",4) = ["","ape","app","apple"]
```

Từ rỗng được liệt kê đầu tiên trong truy vấn tiền tố rỗng vì nó là terminal tại root; từ ngắn hơn đứng trước mọi từ dài hơn bắt đầu bằng nó.

### 8.2. Xóa bản sao đầu tiên của app

```text
removeOne("app") = true
countExact("app") = 1
totalWords() = 10
distinctWords() = 9
```

Từ `app` vẫn còn một bản sao nên số từ phân biệt không đổi.

### 8.3. Xóa bản sao thứ hai của app

```text
removeOne("app") = true
removeOne("app") lần nữa = false

countExact("app") = 0
countPrefix("app") = 2
suggest("app",10) = ["apple","apply"]
```

Nút `app` vẫn tồn tại nhờ `apple` và `apply`, nhưng `endCount("app")=0`. Đây là ví dụ quan trọng nhất để tránh lỗi “xóa mất tất cả từ bắt đầu cùng một tiền tố”.

### 8.4. Xóa từ rỗng và banana

```text
removeOne("") = true
countPrefix("") = 8

removeOne("banana") = true
countExact("banana") = 1

removeOne("banana") = true
countExact("banana") = 0

totalWords() = 6
distinctWords() = 6
```

Sau hai lần xóa `banana`, nếu không có từ nào khác dùng nhánh `banan...`, những nút không còn từ đi qua được dọn khỏi trie. Những từ `bat` và `bán` vẫn còn vì đi trên các nhánh khác.

## 9. Java 17+ đầy đủ: trie có bộ đếm, xóa và autocomplete

Bài toán minh họa thống nhất hợp đồng:

- Phân biệt **chính xác** các đơn vị ký tự, có phân biệt chữ hoa/thường và dấu.
- Cho phép từ rỗng `""`.
- Cho phép chèn cùng từ nhiều lần; `insert` tăng số lần lưu.
- `countExact` và `countPrefix` trả **số lần lưu**, kiểu `long`.
- `removeOne` xóa **một bản sao**, trả `false` và không sửa gì nếu từ vắng mặt.
- `suggest(prefix,limit)` trả **từ phân biệt theo thứ tự `String.compareTo`**, tối đa `limit` kết quả; `limit=0` trả `[]`, `limit<0` bị từ chối.
- `null` bị từ chối bằng `NullPointerException`.
- Mã dùng `charAt` và `TreeMap<Character,...>`, nghĩa là nhánh trie theo **đơn vị UTF-16**, không tự chuẩn hóa Unicode hay dùng thứ tự từ điển tiếng Việt.
- Bộ đếm kiểu `long` bảo vệ trường hợp tổng số lần chèn đã bằng `Long.MAX_VALUE`; không cho chèn thêm để tránh tràn.

**Tệp độc lập:** `TriePrefixDictionaryDemo.java`.

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Random;
import java.util.TreeMap;

public final class TriePrefixDictionaryDemo {
    private TriePrefixDictionaryDemo() {
    }

    private static final class Node {
        final TreeMap<Character, Node> children =
            new TreeMap<>();

        long passCount;
        long endCount;
    }

    public static final class Trie {
        private final Node root = new Node();
        private long distinct;

        public long totalWords() {
            return root.passCount;
        }

        public long distinctWords() {
            return distinct;
        }

        private Node walk(String key) {
            Objects.requireNonNull(key, "key");

            Node node = root;
            for (int i = 0; i < key.length(); i++) {
                node = node.children.get(key.charAt(i));
                if (node == null) {
                    return null;
                }
            }
            return node;
        }

        public void insert(String word) {
            Objects.requireNonNull(word, "word");

            // Moi nut con deu co passCount <= root.passCount.
            // Khi tong chua tran, tang cac bo dem deu an toan.
            if (root.passCount == Long.MAX_VALUE) {
                throw new ArithmeticException(
                    "too many stored word occurrences"
                );
            }

            Node node = root;
            node.passCount++;

            for (int i = 0; i < word.length(); i++) {
                char c = word.charAt(i);
                node = node.children.computeIfAbsent(
                    c, ignored -> new Node()
                );
                node.passCount++;
            }

            if (node.endCount == 0) {
                distinct++;
            }
            node.endCount++;
        }

        public long countExact(String word) {
            Node node = walk(word);
            return node == null ? 0 : node.endCount;
        }

        public long countPrefix(String prefix) {
            Node node = walk(prefix);
            return node == null ? 0 : node.passCount;
        }

        public boolean contains(String word) {
            return countExact(word) > 0;
        }

        public boolean startsWith(String prefix) {
            return countPrefix(prefix) > 0;
        }

        public boolean removeOne(String word) {
            Objects.requireNonNull(word, "word");

            List<Node> path =
                new ArrayList<>(word.length() + 1);
            Node node = root;
            path.add(root);

            for (int i = 0; i < word.length(); i++) {
                node = node.children.get(word.charAt(i));
                if (node == null) {
                    return false;
                }
                path.add(node);
            }
            if (node.endCount == 0) {
                return false;
            }

            boolean removedLastCopy = node.endCount == 1;
            node.endCount--;
            for (Node item : path) {
                item.passCount--;
            }

            // Don nhung nhanh khong con tu nao di qua.
            for (int i = word.length() - 1; i >= 0; i--) {
                Node child = path.get(i + 1);
                if (child.passCount == 0) {
                    path.get(i).children.remove(
                        word.charAt(i)
                    );
                } else {
                    break;
                }
            }

            if (removedLastCopy) {
                distinct--;
            }
            return true;
        }

        private static void collect(
                Node node, StringBuilder current,
                List<String> output, int limit) {
            if (output.size() >= limit) {
                return;
            }

            // Tu ket thuc tai nut nay dung truoc hau duoi.
            if (node.endCount > 0) {
                output.add(current.toString());
            }
            if (output.size() >= limit) {
                return;
            }

            for (Map.Entry<Character, Node> entry
                    : node.children.entrySet()) {
                current.append(entry.getKey());
                collect(
                    entry.getValue(), current, output, limit
                );
                current.setLength(current.length() - 1);

                if (output.size() >= limit) {
                    return;
                }
            }
        }

        public List<String> suggest(
                String prefix, int limit) {
            Objects.requireNonNull(prefix, "prefix");
            if (limit < 0) {
                throw new IllegalArgumentException(
                    "limit must be nonnegative"
                );
            }
            if (limit == 0) {
                return List.of();
            }

            Node node = walk(prefix);
            if (node == null || node.passCount == 0) {
                return List.of();
            }
            List<String> results = new ArrayList<>();
            collect(
                node, new StringBuilder(prefix),
                results, limit
            );
            return results;
        }

        // Chi dung cho test: kiem tra lai moi node bang
        // cong thuc pass=end+sum(pass cua cac con).
        private record Counts(long total, long distinct) {
        }

        private static Counts inspect(Node node) {
            long total = node.endCount;
            long different = node.endCount > 0 ? 1 : 0;

            for (Node child : node.children.values()) {
                if (child.passCount <= 0) {
                    throw new AssertionError(
                        "unpruned empty child"
                    );
                }
                Counts sub = inspect(child);
                total += sub.total();
                different += sub.distinct();
            }

            if (node.passCount != total
                    || node.endCount < 0
                    || node.endCount > node.passCount) {
                throw new AssertionError(
                    "trie count invariant violated"
                );
            }
            return new Counts(total, different);
        }

        public void assertInvariants() {
            Counts counts = inspect(root);
            if (counts.total() != root.passCount
                    || counts.distinct() != distinct) {
                throw new AssertionError(
                    "global counters disagree"
                );
            }
        }
    }

    // Oracle doc lap: map tu -> so lan luu.
    // Khong dung node, passCount hay failure/cay.
    private static long referencePrefix(
            Map<String, Integer> dictionary,
            String prefix) {
        long count = 0;

        for (Map.Entry<String, Integer> entry
                : dictionary.entrySet()) {
            if (entry.getKey().startsWith(prefix)) {
                count += entry.getValue();
            }
        }
        return count;
    }

    private static List<String> referenceSuggest(
            Map<String, Integer> dictionary,
            String prefix, int limit) {
        return dictionary.keySet().stream()
            .filter(word -> word.startsWith(prefix))
            .sorted()
            .limit(limit)
            .toList();
    }

    private static long referenceTotal(
            Map<String, Integer> dictionary) {
        long total = 0;
        for (int count : dictionary.values()) {
            total += count;
        }
        return total;
    }

    private static String randomWord(
            Random random, int tokens) {
        String[] alphabet = {"a", "b", "á", "🙂"};
        StringBuilder result = new StringBuilder();

        for (int i = 0; i < tokens; i++) {
            result.append(
                alphabet[random.nextInt(alphabet.length)]
            );
        }
        return result.toString();
    }

    private static String quoted(List<String> words) {
        return words.stream()
            .map(word -> "\"" + word + "\"")
            .toList()
            .toString();
    }

    private static void require(
            boolean condition, String description) {
        if (!condition) {
            throw new AssertionError(description);
        }
    }

    public static void main(String[] args) {
        Trie empty = new Trie();
        System.out.println(
            "Empty dictionary: total=" + empty.totalWords()
            + " prefixEmpty=" + empty.countPrefix("")
            + " startsWithEmpty=" + empty.startsWith("")
            + " suggest=" + empty.suggest("", 3)
        );

        Trie trie = new Trie();
        String[] input = {
            "", "app", "apple", "app", "apply",
            "ape", "bat", "banana", "banana",
            "bán", "áo"
        };
        for (String word : input) {
            trie.insert(word);
        }

        System.out.println(
            "Initial: total=" + trie.totalWords()
            + " distinct=" + trie.distinctWords()
        );
        System.out.println(
            "Exact: app=" + trie.countExact("app")
            + " ap=" + trie.countExact("ap")
        );
        System.out.println(
            "Prefix: ap=" + trie.countPrefix("ap")
            + " app=" + trie.countPrefix("app")
            + " empty=" + trie.countPrefix("")
        );
        System.out.println(
            "Boolean: apple=" + trie.contains("apple")
            + " ban=" + trie.startsWith("ban")
            + " cat=" + trie.startsWith("cat")
        );
        System.out.println(
            "Suggest ap 3: " + trie.suggest("ap", 3)
        );
        System.out.println(
            "Suggest app 10: " + trie.suggest("app", 10)
        );
        System.out.println(
            "Suggest empty 4: "
            + quoted(trie.suggest("", 4))
        );

        boolean removed = trie.removeOne("app");
        System.out.println(
            "Remove app 1: " + removed
            + " exact=" + trie.countExact("app")
            + " total=" + trie.totalWords()
        );
        boolean removed2 = trie.removeOne("app");
        boolean removed3 = trie.removeOne("app");

        System.out.println(
            "Remove app 2: " + removed2
            + " remove app 3: " + removed3
        );
        System.out.println(
            "After app: prefix=" + trie.countPrefix("app")
            + " suggest=" + trie.suggest("app", 10)
        );
        System.out.println(
            "Remove empty: " + trie.removeOne("")
            + " total=" + trie.totalWords()
        );
        System.out.println(
            "Remove banana 1: "
            + trie.removeOne("banana")
            + " exact=" + trie.countExact("banana")
        );
        System.out.println(
            "Remove banana 2: "
            + trie.removeOne("banana")
            + " exact=" + trie.countExact("banana")
        );
        trie.assertInvariants();
        System.out.println(
            "Final: total=" + trie.totalWords()
            + " distinct=" + trie.distinctWords()
        );

        boolean negativeLimitRejected = false;
        try {
            trie.suggest("a", -1);
        } catch (IllegalArgumentException expected) {
            negativeLimitRejected = true;
        }
        System.out.println(
            "Negative limit rejected: "
            + negativeLimitRejected
        );

        Trie tested = new Trie();
        Map<String, Integer> oracle = new HashMap<>();
        Random random = new Random(379L);

        int operations = 0;
        int queryChecks = 0;

        for (int trial = 0; trial < 4_000; trial++) {
            String word = randomWord(
                random, random.nextInt(8)
            );
            int operation = random.nextInt(5);

            if (operation <= 1) {
                tested.insert(word);
                oracle.merge(word, 1, Integer::sum);
            } else if (operation == 2) {
                int previous = oracle.getOrDefault(word, 0);
                boolean expected = previous > 0;
                boolean actual = tested.removeOne(word);

                require(actual == expected,
                    "remove mismatch trial=" + trial
                );

                if (previous == 1) {
                    oracle.remove(word);
                } else if (previous > 1) {
                    oracle.put(word, previous - 1);
                }
            }

            tested.assertInvariants();
            operations++;

            // Truy van sau moi thao tac, so voi map doc lap.
            String candidate = randomWord(
                random, random.nextInt(8)
            );
            String prefix = candidate.substring(
                0, random.nextInt(candidate.length() + 1)
            );
            int limit = random.nextInt(7);

            long expectedPrefix =
                referencePrefix(oracle, prefix);
            long expectedExact =
                oracle.getOrDefault(word, 0);

            require(tested.countExact(word) == expectedExact,
                "countExact mismatch trial=" + trial
            );
            require(tested.contains(word)
                    == (expectedExact > 0),
                "contains mismatch trial=" + trial
            );
            require(tested.countPrefix(prefix)
                    == expectedPrefix,
                "countPrefix mismatch trial=" + trial
            );
            require(tested.startsWith(prefix)
                    == (expectedPrefix > 0),
                "startsWith mismatch trial=" + trial
            );
            require(tested.suggest(prefix, limit).equals(
                    referenceSuggest(oracle, prefix, limit)),
                "suggest mismatch trial=" + trial
            );

            require(tested.totalWords()
                    == referenceTotal(oracle),
                "total mismatch trial=" + trial
            );
            require(tested.distinctWords()
                    == oracle.size(),
                "distinct mismatch trial=" + trial
            );
            queryChecks++;
        }

        System.out.println(
            "Random operations verified: " + operations
        );
        System.out.println(
            "Random query checks: " + queryChecks
        );
    }
}
```

Biên dịch và chạy bằng **JDK 17 hoặc mới hơn**:

```bash
javac -encoding UTF-8 TriePrefixDictionaryDemo.java
java TriePrefixDictionaryDemo
```

**Đầu ra chuẩn:**

```text
Empty dictionary: total=0 prefixEmpty=0 startsWithEmpty=false suggest=[]
Initial: total=11 distinct=9
Exact: app=2 ap=0
Prefix: ap=5 app=4 empty=11
Boolean: apple=true ban=true cat=false
Suggest ap 3: [ape, app, apple]
Suggest app 10: [app, apple, apply]
Suggest empty 4: ["", "ape", "app", "apple"]
Remove app 1: true exact=1 total=10
Remove app 2: true remove app 3: false
After app: prefix=2 suggest=[apple, apply]
Remove empty: true total=8
Remove banana 1: true exact=1
Remove banana 2: true exact=0
Final: total=6 distinct=6
Negative limit rejected: true
Random operations verified: 4000
Random query checks: 4000
```

### 9.1. Vì sao mã lưu `passCount` trên cả root?

`totalWords()` chính là `root.passCount`. Mỗi lần `insert` tăng root một, mỗi `removeOne` thành công giảm root một. Với prefix rỗng, `walk("")` trả root ngay, nên `countPrefix("")=totalWords()`.

### 9.2. Vì sao distinct chỉ đổi khi endCount chuyển qua 0?

Nếu `app` đã lưu một lần rồi được chèn lần hai, ta chỉ thêm một **bản sao**, không có từ phân biệt mới. `distinct` tăng khi `endCount` trước chèn bằng `0`.

Khi xóa, nếu `endCount` đang bằng `2` rồi giảm còn `1`, từ vẫn tồn tại nên distinct không đổi. Chỉ giảm distinct khi `endCount` từ `1` trở về `0`.

### 9.3. Tại sao không dọn nút khi endCount=0?

Trong ví dụ, sau khi xóa hết bản sao `app`, nút biểu diễn `app` có `endCount=0` nhưng `passCount=2` vì `apple` và `apply` vẫn còn. Điều kiện cắt nhánh theo `passCount=0` giữ lại đường tiền tố cần thiết.

### 9.4. Vì sao TreeMap và terminal-before-children cho thứ tự từ điển?

Với hai từ phân biệt:

- Nếu một từ là tiền tố của từ kia, từ ngắn hơn được phát ra ở nút terminal trước khi DFS đi sâu xuống các con.
- Nếu chúng khác nhau tại một vị trí, hai nhánh có nhãn `char` khác nhau; `TreeMap` duyệt nhãn nhỏ hơn trước.

Đó chính là quy tắc so `String.compareTo` theo các đơn vị UTF-16. Kết quả `suggest` không lặp bản sao và được sắp đúng thứ tự này.

### 9.5. Tại sao dùng long thay vì int cho bộ đếm?

Với nhiều thao tác insert, tổng số **lần lưu** có thể vượt `Integer.MAX_VALUE` ngay cả khi số nút không quá nhiều; ví dụ chèn cùng `"a"` hàng tỷ lần.

`long` tăng khoảng đếm. Bản mẫu bảo vệ trước khi `root.passCount` đạt `Long.MAX_VALUE` để không cho lần chèn tiếp theo gây tràn. Tính chất `passCount(node)\le root.passCount` và `endCount(node)\le passCount(node)` đảm bảo các bộ đếm con không tràn khi root còn chỗ.

Nếu hệ thống thật yêu cầu số lần lưu vượt cả `long`, cần mô hình dữ liệu và bộ đếm khác (ví dụ `BigInteger`, lưu trữ phân tán), không âm thầm để tràn kiểu số.

### 9.6. Vì sao có thể dùng HashMap làm oracle?

`HashMap<String,Integer>` lưu **từng từ đầy đủ** và số lần xuất hiện, không dùng trie hay các nút `passCount`. Oracle tự duyệt tất cả khóa để đếm prefix và tạo danh sách gợi ý bằng lọc `startsWith` rồi `sorted`.

Do đó nếu trie xóa sai một nút con, đếm sai bản sao, hay liệt kê sai thứ tự, kết quả sẽ khác cách cài độc lập này. Cách kiểm thử đó mạnh hơn việc so hai trie có cùng lỗi.

## 10. Chứng minh các thao tác giữ bất biến

### 10.1. Cơ sở

Trie rỗng chỉ có root:

\[
passCount(root)=endCount(root)=0.
\]

Không có con nên:

\[
passCount(root)=endCount(root)+0.
\]

`distinctWords=0` và `totalWords=0`.

### 10.2. Bước chèn

Xét từ `w` có đường qua các nút `v_0=root,v_1,\ldots,v_L`.

- Ở nút kết thúc `v_L`, tăng `endCount` một và tăng `passCount` một. Hai vế công thức bất biến cùng tăng một.
- Ở mỗi nút trung gian `v_i`, một nút con của nó có `passCount` tăng một, đồng thời `passCount(v_i)` tăng một. Công thức vẫn đúng.
- Các nút không nằm trên đường không đổi.
- Nếu có nút mới, ban đầu bộ đếm đều `0`, sau cập nhật đường chèn cũng thỏa công thức.

Vậy thao tác insert bảo toàn:

\[
passCount(v)=endCount(v)+\sum child.passCount.
\]

### 10.3. Bước xóa có từ tồn tại

Khi xóa một bản sao `w`:

- Ở nút cuối, `endCount` và `passCount` cùng giảm một.
- Ở nút trung gian, `passCount` giảm một và `passCount` của đúng một nhánh con giảm một.
- Những nút nằm ngoài đường giữ nguyên.

Vì đã xác nhận `endCount(w)>0`, mọi `passCount` trên đường đều ít nhất `1`, nên không tạo bộ đếm âm.

Nếu một nhánh đạt `passCount=0`, không còn từ nào dùng nó. Ta có thể bỏ nhánh ấy; phần đóng góp vào tổng con bằng `0`, nên cắt cũng không phá bất biến tại cha.

### 10.4. Đúng của truy vấn

Đường root→node biểu diễn chính xác tiền tố. Vì vậy:

- `countExact(w)` trả số lần lưu từ kết thúc **tại node(w)**, tức `endCount`.
- `countPrefix(p)` trả số lần lưu đi qua **node(p)**, tức `passCount`.
- Nếu không có đường cho truy vấn, không thể có từ nào đã lưu bắt đầu bằng đường ấy.
- DFS ở nhánh của `p` phát ra đúng các terminal còn lưu ở dưới, tức đúng những từ có tiền tố `p`.

Đây là chứng minh theo **ý nghĩa của mỗi nút** và bất biến bộ đếm, không phụ thuộc một thứ tự chèn cụ thể.

## 11. Độ phức tạp: độ dài truy vấn, số nhánh và số kết quả

Đặt:

- `L`: số đơn vị ký tự của từ cần insert/delete.
- `p`: độ dài tiền tố truy vấn.
- `d`: số nhánh con nhiều nhất của một nút.
- `N`: số nút của trie.
- `R`: tổng số ký tự của các từ thực sự được trả về trong danh sách gợi ý.
- `V_s`: số nút được DFS thăm khi tạo gợi ý.

Với `TreeMap<Character,Node>`, mỗi lần đi theo cạnh bằng `get/computeIfAbsent/remove` tốn `O(\log(d+1))` trong trường hợp xấu (tại nút có `d` nhánh).

| Thao tác | Thời gian, không tính chi phí phân bổ bất thường | Bộ nhớ phụ |
|---|---|---|
| `insert(word)` | `O(L\log(d+1))` | Tối đa `O(L)` nút mới |
| `countExact(word)` | `O(L\log(d+1))` | `O(1)` |
| `countPrefix(prefix)` | `O(p\log(d+1))` | `O(1)` |
| `contains` / `startsWith` | Như truy vấn tương ứng | `O(1)` |
| `removeOne(word)` | `O(L\log(d+1))` | `O(L)` để lưu đường cha |
| `suggest(prefix,k)` | `O(p\log(d+1)+V_s+R)` | `O(h+R)` cho stack + kết quả |
| `totalWords` / `distinctWords` | `O(1)` | `O(1)` |

Ở đây `h` là độ sâu DFS tối đa. Nếu dùng một bảng băm `HashMap` và giả định thời gian tra cứu trung bình `O(1)`, các truy vấn đi theo đường có thể trung bình gần `O(L)`. Nếu bảng chữ cái cố định và được mã hóa trực tiếp bằng mảng, cũng có thể đạt `O(L)` với độ lớn bảng chữ cái hằng.

**Lưu ý:** khi `d` lớn mà một số nhánh không có terminal gần, `suggest` vẫn có thể đi qua nhiều nút trước khi phát đủ `k` kết quả; không được tự khẳng định chi phí chỉ `O(p+k)`. Việc tạo chuỗi đầu ra đòi `O(R)` công việc.

### 11.1. Bộ nhớ của trie

Mỗi **tiền tố phân biệt** tương ứng tối đa một nút, nên:

\[
\boxed{
N\le 1+\sum_{\text{word phân biệt}}|word|.
}
\]

Các từ dùng chung tiền tố giúp tiết kiệm nút so với việc dựng cây đường đi riêng cho mỗi từ, nhưng mỗi nút lại mang chi phí đối tượng, map và liên kết. Khi nhiều từ rất ngắn hoặc bảng chữ cái lớn, overhead có thể đáng kể.

Chèn từ trùng **không** làm tăng số nút nếu đường đã có; nó chỉ tăng bộ đếm.

Tổng bộ nhớ cho trie là `O(N)` đối tượng nút và cạnh, nhưng hằng số phụ thuộc cách biểu diễn `children`.

### 11.2. Trie không mặc định tiết kiệm hơn HashMap

Nếu chỉ cần kiểm tra **một từ chính xác**, `HashSet<String>` hoặc `HashMap<String,Integer>` thường có triển khai đơn giản, gọn và nhanh trên nhiều tập dữ liệu. Trie đặc biệt hấp dẫn khi có nhiều truy vấn theo **tiền tố**, gợi ý/tìm từ cùng phần đầu, hoặc cần khai thác cấu trúc đường ký tự.

Không phải mọi hệ thống từ điển đều nên chuyển sang trie. Hãy xét mẫu truy vấn, kích thước dữ liệu, alphabet, phân bổ bộ nhớ và yêu cầu sắp thứ tự.

## 12. Unicode, tiếng Việt và “thứ tự từ điển” là những khái niệm khác nhau

### 12.1. Java char và UTF-16

Java `String` lưu các **đơn vị UTF-16**. Một ký tự Unicode ngoài Basic Multilingual Plane, ví dụ emoji `🙂`, thường dùng **hai đơn vị `char`** (surrogate pair).

Bản trie này tạo một cạnh cho mỗi `charAt(i)`, nên emoji có thể đi qua hai cạnh. Việc insert, lookup, prefix và gợi ý vẫn nhất quán với **`String.startsWith` và `String.compareTo` trên đơn vị UTF-16**, miễn là mọi hàm cùng áp dụng chính một quy tắc.

Nhưng “độ dài từ” ở đây là **số code units**, không nhất thiết là số Unicode code points hoặc số ký tự người dùng nhìn thấy.

Nếu đề yêu cầu trie theo **code point**, có thể sinh các `int codePoint` bằng `String.codePoints()`, lưu cạnh `Map<Integer,Node>` và khôi phục chuỗi bằng `appendCodePoint`. Khi đó phải xác định lại quy tắc sắp xếp và cách xử lý prefix ở giữa surrogate pair.

### 12.2. Dấu tiếng Việt và Unicode normalization

Hai chuỗi hiển thị gần giống nhau có thể được mã hóa khác nhau:

- Một nguyên âm có dấu dựng sẵn dưới một code point.
- Cùng nguyên âm biểu diễn bằng ký tự cơ sở cộng dấu kết hợp.

Trie khớp **chuỗi mã chính xác**, nên hai biểu diễn không tự động được xem là một từ. Nếu muốn đồng nhất, cần **chuẩn hóa cả dữ liệu chèn và dữ liệu truy vấn** (ví dụ NFC) theo một chính sách thống nhất.

Nếu hệ thống muốn tìm không phân biệt dấu, cũng phải định nghĩa rõ cách loại dấu, xử lý chữ `đ`, chuẩn hóa hoa/thường và ánh xạ kết quả về dạng gốc. Đây là logic tầng ứng dụng, không phải tính năng có sẵn của trie.

### 12.3. Sắp theo UTF-16 không phải theo bảng chữ cái tiếng Việt

`TreeMap<Character,...>` duyệt nhãn theo giá trị `char`; `String.compareTo` so chuỗi theo UTF-16 code units. Vì vậy chuỗi có dấu như `"áo"` không nhất thiết đứng ngay cạnh mọi từ bắt đầu bằng `"a"` theo cảm nhận ngôn ngữ.

Nếu cần xếp thứ tự theo quy tắc tiếng Việt, có thể dùng `java.text.Collator` với locale phù hợp ở tầng sắp xếp gợi ý, hoặc thiết kế khóa chuẩn hóa/sắp xếp riêng. Khi dùng collator cho toàn từ, **thứ tự DFS theo TreeMap của từng code unit không bảo đảm trùng thứ tự Collator**. Không được gắn nhãn kết quả này là “thứ tự từ điển tiếng Việt chuẩn”.

### 12.4. Phân biệt literal prefix với autocomplete tìm gần đúng

Trie theo tiền tố chỉ tìm các từ bắt đầu **chính xác** bằng prefix. Nếu người dùng gõ sai một ký tự hoặc bỏ dấu, cách tìm literal có thể trả danh sách rỗng.

Gợi ý theo fuzzy matching, edit distance, ngữ cảnh ngôn ngữ, tần suất sử dụng hoặc thứ hạng cá nhân hóa cần lớp thuật toán bổ sung. Trie có thể là cấu trúc ứng viên, nhưng không tự giải mọi yêu cầu tìm kiếm.

## 13. Các cách lưu children và biến thể cấu trúc

### 13.1. Mảng cố định 26 ký tự

Khi đề bảo đảm mọi từ chỉ gồm `a..z`, có thể dùng:

```java
Node[] children = new Node[26];
int id = c - 'a';
```

Ưu điểm: đi cạnh `O(1)` và thao tác đơn giản. Nhược điểm: mỗi nút dành chỗ cho 26 con dù phần lớn không dùng; không hỗ trợ chữ có dấu, hoa, số hoặc emoji nếu không đổi mô hình.

Bắt buộc kiểm tra `'a'<=c<='z'` trước khi tính chỉ số và truy cập mảng. Nếu đề cho chữ hoa hoặc dữ liệu Unicode, biểu thức `c-'a'` có thể âm hoặc vượt 25.

### 13.2. HashMap<Character,Node>

Tiết kiệm bảng con khi nhánh thưa, tra cứu trung bình gần `O(1)`. Tuy nhiên thứ tự duyệt của `HashMap` **không xác định theo thứ tự từ điển**. Nếu cần gợi ý có thứ tự, phải sắp các khóa con tại thời điểm duyệt hoặc sử dụng cấu trúc sắp xếp như TreeMap.

### 13.3. TreeMap<Character,Node>

Được dùng trong mã mẫu: các nhánh có thứ tự, thuận tiện cho autocomplete theo `String.compareTo`, đổi lại tra cứu `O(\log d)` và overhead cao hơn mảng trong một số trường hợp.

### 13.4. Compressed trie / radix tree

Nếu nhiều nút chỉ có **một con** và không đánh dấu kết thúc từ, có thể nén một chuỗi nhiều cạnh thành một cạnh mang **chuỗi ký tự**. Cấu trúc đó thường gọi là **radix tree / compressed trie**.

Ưu điểm: giảm số nút và overhead khi có các đoạn dài không phân nhánh. Nhược điểm: insert/delete phải chia/gộp nhãn cạnh khi có khóa rẽ nhánh, và cần so nhiều ký tự trên một cạnh.

Đừng dùng công thức đếm `pass=end+\sum child.pass` một cách máy móc nếu cấu trúc và semantics đã thay đổi; phải định nghĩa lại bất biến cho mỗi cạnh nén/terminal.

### 13.5. Suffix trie và suffix tree không phải trie từ điển thông thường

Một trie của các **từ trong từ điển** phục vụ truy vấn **tiền tố**. Muốn truy vấn một chuỗi bất kỳ **xuất hiện bên trong** văn bản, có thể xét các cấu trúc như suffix trie/suffix tree/suffix array hoặc automaton. Không thể dùng trie từ điển tiền tố rồi mặc định giải mọi truy vấn substring.

## 14. Tình huống ứng dụng và chọn API phù hợp

### 14.1. Autocomplete khi người dùng đang gõ

Sau mỗi ký tự người dùng nhập, ta truy vấn:

```text
suggest(prefix, 5)
```

Đường đi theo prefix giúp xác định nhanh nhánh gợi ý. Nếu từ điển biến động, insert/removeOne cập nhật các bộ đếm để gợi ý không chứa từ đã xóa hết.

Tuy nhiên, hệ thống thực cần cân nhắc Unicode normalization, xếp hạng, bảo mật dữ liệu nhạy cảm, số lượng người dùng đồng thời và cập nhật từ điển trong lúc đọc.

### 14.2. Kiểm tra từ tồn tại

`contains(word)` trả boolean. Nếu phải đếm tần suất từ, `countExact(word)` lưu multiplicity, nhưng cần chắc rằng tần suất được hiểu là số lần chèn chứ không phải số lần người dùng tra cứu.

### 14.3. Đếm tiền tố cho thống kê

`countPrefix(prefix)` trả số lần lưu các từ có prefix, hữu ích cho thống kê khóa, kiểm tra số lượng mã hay nhóm tên bắt đầu bằng chuỗi nào đó. Khi cần **số khóa duy nhất**, phải duy trì bộ đếm phân biệt riêng hoặc duyệt terminal.

### 14.4. Xóa dữ liệu không phá nhánh chung

Trong danh bạ chứa `"An"`, `"Anh"`, `"Anita"`, xóa `"An"` không được làm mất hai tên dài hơn. Đây là lý do phải phân biệt `endCount` với `passCount` khi xóa.

### 14.5. Truy vấn tiền tố không phải truy vấn tất cả chuỗi chứa substring

`startsWith("cat")` tìm từ bắt đầu bằng `cat`; không trả từ `"educate"` chỉ vì có đoạn `cat` ở giữa. Nếu yêu cầu chứa substring, trie tiền tố thông thường không thể trả lời nhanh trực tiếp nếu không thêm chỉ mục/cấu trúc khác.

## 15. QA và kiểm thử ngẫu nhiên độc lập

Một chương trình đúng không chỉ trả lời đúng vài ví dụ. Các thao tác insert/delete đan xen có thể gây lỗi bộ đếm sau nhiều vòng.

### 15.1. Oracle tham chiếu đơn giản

Dùng `HashMap<String,Integer>` độc lập với trie:

- `insert(w)`: `map[w]++`.
- `removeOne(w)`: nếu `map[w]>0` thì giảm; nếu về `0`, xóa khóa; nếu không có khóa, trả `false`.
- `countExact(w)`: `map.getOrDefault(w,0)`.
- `countPrefix(p)`: duyệt tất cả entry, cộng số lần lưu nếu `word.startsWith(p)`.
- `suggest(p,k)`: lấy các khóa có `startsWith(p)`, sắp bằng `String.compareTo` rồi giữ tối đa `k` khóa.
- `distinctWords`: `map.size()`; `totalWords`: tổng các value.

Đây là cách chậm hơn ở truy vấn tiền tố, nhưng đơn giản và **không phụ thuộc thuật toán trie**, phù hợp làm oracle trên dữ liệu nhỏ.

### 15.2. Sau mỗi thao tác hãy kiểm tra invariant

Mã có `assertInvariants()`, duyệt mọi nút để tính lại:

\[
passCount(node)=endCount(node)+\sum_{child}passCount(child).
\]

Đồng thời so:

\[
distinctWords=\#\{node:endCount(node)>0\},
\]

\[
totalWords=passCount(root).
\]

Việc kiểm toàn bộ cây có thể tốn `O(N)`, vì vậy đây là công cụ **test/diagnostic**, không nhất thiết gọi sau mọi thao tác trong môi trường production.

### 15.3. Sinh dữ liệu chứa từ trùng, rỗng và Unicode

Chương trình Java dùng `Random(379L)` để tạo **4.000 thao tác ngẫu nhiên**, với alphabet gồm:

```text
"a", "b", "á", "🙂"
```

Từ có thể có độ dài token `0..7`, nên có cả từ rỗng, các tiền tố chung và emoji (hai UTF-16 code units). Các thao tác có chèn, xóa một lần, hoặc chỉ truy vấn.

Sau mỗi thao tác:

1. So kết quả `removeOne` (nếu có) với oracle.
2. Xác minh bất biến của mọi nút.
3. So `countExact`, `contains`, `countPrefix` và `startsWith`.
4. So `suggest(prefix,limit)` với danh sách độc lập đã sắp xếp.
5. So tổng lần lưu và tổng từ phân biệt.

Trong phép sinh prefix thử nghiệm, cắt `String.substring` tại một UTF-16 boundary bất kỳ; có thể trúng giữa surrogate pair. Điều đó vẫn hợp lệ trong **hợp đồng thao tác trên code units** của chương trình, và giúp phát hiện cài đặt vô tình trộn các đơn vị chỉ số khác nhau. Nếu ứng dụng yêu cầu chỉ prefix ở ranh giới Unicode code point, cần một bộ sinh truy vấn khác.

### 15.4. Các trường hợp biên quan trọng

```text
Trie rỗng:
  totalWords=0
  distinctWords=0
  countPrefix("")=0
  startsWith("")=false
  suggest("",10)=[]

Chèn từ rỗng:
  endCount(root) tăng
  passCount(root) tăng
  suggest("",10) có từ ""

Chèn cùng từ hai lần:
  countExact(word)=2
  distinctWords chỉ tăng 1

Từ là tiền tố của từ khác:
  insert("app")
  insert("apple")
  removeOne("app")
  contains("apple") vẫn true

Xóa từ không tồn tại:
  removeOne(word)=false
  mọi bộ đếm giữ nguyên

Xóa bản sao cuối:
  distinctWords giảm đúng 1
  nhánh chỉ bị cắt nếu passCount=0

Prefix không tồn tại:
  countPrefix=0
  suggest=[]

Prefix bằng toàn từ:
  countPrefix(word) tính cả word và các từ dài hơn

Limit bằng 0:
  suggest(prefix,0)=[]

Limit âm:
  throw IllegalArgumentException

Từ có dấu hoặc emoji:
  khớp literal theo UTF-16
  không tự bỏ dấu hay chuẩn hóa

Nhiều từ trùng:
  suggest chỉ liệt kê mỗi từ phân biệt một lần
```

### 15.5. Vì sao random tests không thay chứng minh?

Nếu 4.000 thao tác đều khớp oracle, ta có bằng chứng thực nghiệm mạnh về implementation trên tập dữ liệu thử, đặc biệt lỗi xóa nhánh chung. Nhưng chứng minh ở phần 10 mới giải thích **vì sao** passCount/endCount luôn đúng cho mọi chuỗi thao tác hợp lệ.

Kết hợp kiểm thử và chứng minh giúp thiết kế một cấu trúc dữ liệu có hành vi rõ ràng và dễ bảo trì hơn.

## 16. Sai lầm thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Chỉ dùng `isEnd` khi đề cho nhiều từ trùng | Không biết số lần lưu chính xác | Dùng `endCount` |
| Coi đường đi tồn tại là từ tồn tại | `contains("app")` trả true dù chỉ lưu `apple` | Kiểm tra `endCount>0` |
| Không tăng `passCount` tại nút terminal | `countPrefix(word)` thiếu chính từ đó | Tăng trên mọi nút của đường gồm root |
| Không tăng `passCount(root)` | `countPrefix("")` sai | Root biểu diễn tiền tố rỗng |
| Nhầm multiplicity với số từ phân biệt | Kết quả đếm prefix sai | Phân biệt `passCount` và `distinct` |
| Khi xóa kiểm tra đường tồn tại nhưng không kiểm tra endCount | Có thể xóa nhầm một tiền tố chưa lưu | Xác nhận `endCount>0` trước |
| Giảm bộ đếm trước khi kiểm tra tồn tại | Bộ đếm có thể âm hoặc không còn nhất quán | Kiểm tra rồi mới sửa |
| Cắt nhánh khi `endCount=0` | Mất các từ dài hơn dùng chung tiền tố | Chỉ cắt khi `passCount=0` |
| Xóa hết nhánh khi chỉ xóa một bản sao | Làm mất bản sao và từ con | `removeOne` chỉ giảm 1 |
| Không giảm `distinct` khi xóa bản sao cuối | Thống kê từ phân biệt sai | Chỉ giảm tại `endCount:1\to0` |
| Gợi ý lặp từ theo số bản sao | Kết quả autocomplete trùng mục | Phát terminal một lần |
| Duyệt nút con trước terminal | `apple` có thể đứng trước `app` | Phát terminal trước children |
| Dùng `HashMap` rồi giả định thứ tự duyệt có sắp xếp | Gợi ý thất thường | `TreeMap` hoặc sort các nhánh |
| Nói gợi ý theo tần suất trong khi chỉ DFS từ điển | Sai tiêu chí thứ hạng | Thêm metadata ranking |
| Không xử lý prefix rỗng | Sai tổng hoặc bỏ sót từ rỗng | Quy ước root rõ ràng |
| Dùng `c-'a'` cho ký tự bất kỳ | Lỗi chỉ số với hoa, dấu, emoji | Kiểm tra alphabet hoặc dùng Map |
| Tưởng `charAt` trả Unicode code point | Sai kỳ vọng độ dài emoji | Nêu rõ UTF-16 code units |
| Tưởng TreeMap sắp theo tiếng Việt chuẩn | Thứ tự dấu/emoji không theo locale | Sắp bằng Collator nếu cần |
| Chuẩn hóa chỉ lúc insert, không lúc query | Truy vấn không tìm thấy dữ liệu | Cùng normalization policy |
| Không chặn `limit<0` | Có thể trả rỗng mơ hồ hoặc lỗi không nhất quán | Xác định hợp đồng và validate |
| Đệ quy DFS trên từ rất sâu | Có thể StackOverflowError | Stack tường minh hoặc giới hạn khóa |
| Đặt bộ đếm int nhưng chèn quá nhiều | Tràn và trả số âm | Dùng long/kiểm tra tràn |
| Dùng trie để hỏi mọi substring | Trie prefix không giải bài substring trực tiếp | Chọn chỉ mục substring phù hợp |
| Test xóa chỉ với một từ độc lập | Không phát hiện lỗi nhánh chung | Test `app` và `apple`, từ trùng |
| Test trie bằng một bản trie gần giống | Cùng sai invariant vẫn qua | Dùng HashMap + lọc/sort độc lập |

## 17. Bài tập tự luyện kèm đáp án

**Bài 1 — Cấu trúc.** Trie là gì và vì sao từ có chung phần đầu dùng chung đường đi?

*Đáp án:* Trie là cây cạnh ký tự, mỗi nút ứng với một tiền tố. Hai từ có cùng tiền tố đi cùng chuỗi cạnh đến nút của tiền tố ấy, chỉ rẽ khi ký tự khác nhau.

**Bài 2 — Đường khác từ.** Đã lưu `apple` nhưng chưa lưu `app`. `countExact("app")` bằng bao nhiêu?

*Đáp án:* `0`, dù đường `app` tồn tại. `countPrefix("app")` bằng `1` nếu chỉ lưu một `apple`.

**Bài 3 — Từ trùng.** Lưu `app` 2 lần, `apple` 1 lần. `countExact("app")` và `countPrefix("app")`?

*Đáp án:* `2` và `3`.

**Bài 4 — Prefix rỗng.** Lưu `""` một lần và `"a"` hai lần. `countPrefix("")`?

*Đáp án:* `3`. Root có `passCount=3`; `countExact("")=1`.

**Bài 5 — Terminal.** Tại sao nút biểu diễn `app` có thể vừa `endCount>0` vừa có nút con?

*Đáp án:* `app` là một từ được lưu; `apple` hoặc `apply` cũng có thể được lưu và tiếp tục qua các con từ cùng nút.

**Bài 6 — Xóa bản sao.** `endCount("app")=3`, gọi `removeOne("app")` một lần. `endCount` mới và số từ phân biệt thay đổi thế nào?

*Đáp án:* `endCount=2`; số từ phân biệt **không đổi**.

**Bài 7 — Xóa bản sao cuối.** `endCount("app")=1`, xóa đúng một lần. Khi nào được cắt nút `app`?

*Đáp án:* khi sau xóa `passCount("app")=0`; nếu có `apple`, `passCount` vẫn dương và không được cắt.

**Bài 8 — Xóa từ vắng mặt.** Chỉ lưu `apple`. Gọi `removeOne("app")` phải trả gì?

*Đáp án:* `false`; giữ nguyên mọi bộ đếm và nhánh vì từ `app` chưa được lưu.

**Bài 9 — Công thức nút.** Viết bất biến giữa `passCount`, `endCount` và các nút con.

*Đáp án:*

\[
passCount(v)=endCount(v)+\sum_{child}passCount(child).
\]

**Bài 10 — Gợi ý.** Lưu `ape,app,app,apple,apply`. `suggest("ap",3)` trả gì?

*Đáp án:* `[ape,app,apple]`, mỗi từ phân biệt một lần, theo thứ tự từ điển.

**Bài 11 — Giới hạn.** `suggest("app",0)` trả gì? `suggest("app",-1)`?

*Đáp án:* `[]` và ném `IllegalArgumentException` theo hợp đồng bài.

**Bài 12 — Độ phức tạp.** Vì sao `countPrefix(p)` không cần duyệt mọi từ dưới nhánh `p`?

*Đáp án:* số lần lưu đã được duy trì trong `passCount` tại nút của `p`; chỉ lần theo `|p|` ký tự rồi đọc bộ đếm.

**Bài 13 — Multiplicity và distinct.** Lưu `app` ba lần, `apple` một lần. Số lần lưu có tiền tố `app` và số từ phân biệt dưới tiền tố là gì?

*Đáp án:* `4` lần lưu, `2` từ phân biệt.

**Bài 14 — TreeMap.** Vì sao TreeMap có lợi nếu muốn gợi ý theo thứ tự Java `String.compareTo`?

*Đáp án:* nó duyệt các nhãn con theo thứ tự `char` tăng dần. Kết hợp phát từ tại terminal trước các con, DFS cho thứ tự từ điển theo UTF-16.

**Bài 15 — Tiếng Việt.** Vì sao thứ tự TreeMap không nhất thiết đúng thứ tự từ điển tiếng Việt?

*Đáp án:* TreeMap so `char` theo UTF-16, không theo quy tắc ghép/chữ có dấu/collation của tiếng Việt.

**Bài 16 — Emoji.** Vì sao emoji `🙂` có thể đi qua hai cạnh trong trie Java này?

*Đáp án:* nó được biểu diễn bằng hai UTF-16 code units; mã duyệt `word.charAt(i)` chứ không duyệt code points.

**Bài 17 — Unicode normalization.** Hai chuỗi nhìn giống nhau nhưng có mã Unicode khác có được trie coi là một từ không?

*Đáp án:* không mặc định. Phải chuẩn hóa đồng nhất trước khi insert và query nếu ứng dụng yêu cầu coi chúng tương đương.

**Bài 18 — Mảng con.** Khi nào có thể dùng `Node[26]`?

*Đáp án:* khi bảng chữ cái đầu vào được bảo đảm chỉ gồm `a..z` (hoặc có phép ánh xạ hữu hạn hợp lệ); cần kiểm tra chỉ số và chấp nhận overhead tại mỗi nút.

**Bài 19 — Autocomplete theo độ phổ biến.** Chỉ dùng TreeMap và DFS đã đủ để xếp từ được tìm nhiều nhất lên đầu chưa?

*Đáp án:* chưa. DFS cho thứ tự từ điển. Cần metadata tần suất và quy tắc top-k riêng để xếp theo độ phổ biến.

**Bài 20 — Test tham chiếu.** Vì sao dùng `HashMap<String,Integer>` và lọc bằng `startsWith` có giá trị kiểm tra trie?

*Đáp án:* HashMap lưu từ đầy đủ, không dùng cấu trúc nút/path-count; kết quả đếm/lọc/sort độc lập giúp phát hiện lỗi bảo trì trie.

## 18. Checklist khi giải truy vấn tiền tố với trie

1. Đề hỏi từ chính xác, tiền tố, hay chuỗi con **bất kỳ**?
2. Từ có thể trùng không? Cần `boolean` hay **multiplicity**?
3. Có cần số **từ phân biệt** riêng với số lần xuất hiện?
4. Root có đại diện prefix `""` và có đếm đầy đủ từ rỗng không?
5. Mỗi nút có `endCount` và `passCount` đúng nghĩa?
6. Sau insert/delete, có giữ `pass=end+\sum child.pass`?
7. `countExact` có kiểm tra terminal chứ không chỉ đường đi tồn tại?
8. `countPrefix` có trả `passCount` ở nút prefix?
9. `startsWith` được định nghĩa là **có một từ đã lưu bắt đầu bằng prefix**?
10. Trước khi xóa, đã xác nhận `endCount>0`?
11. Xóa chỉ **một bản sao**, không phải xóa hết từ, nếu API là `removeOne`?
12. Chỉ cắt nhánh khi `passCount=0`, không cắt vì `endCount=0`?
13. Distinct tăng khi `end:0\to1` và giảm khi `end:1\to0`?
14. Nếu gợi ý, có trả từ tại terminal trước các từ dài hơn?
15. Nút con có được duyệt theo thứ tự phù hợp với tiêu chí sắp xếp?
16. `limit` có được xử lý với `0`, âm và lớn hơn số kết quả?
17. Có biết gợi ý hiện tại là **từ điển**, không phải popularity ranking?
18. Java String có dùng `charAt`/UTF-16, và ứng dụng có yêu cầu code point hoặc chuẩn hóa tiếng Việt không?
19. Có kiểm tra độ phức tạp theo **độ dài key**, số nhánh, số node được duyệt và tổng chiều dài kết quả?
20. Có thử từ trùng, từ rỗng, một từ là tiền tố của từ khác, xóa sai, xóa bản sao cuối và Unicode?
21. Có kiểm chứng mỗi thao tác với oracle Map độc lập và bất biến tại mọi nút?

## Ghi nhớ

Một nút trie biểu diễn một **tiền tố**. Với mô hình đa tập có hai bộ đếm:

\[
\boxed{endCount(v)=\text{số lần lưu từ kết thúc tại }v,}
\]

\[
\boxed{passCount(v)=\text{số lần lưu từ đi qua }v.}
\]

Bất biến quan trọng:

\[
\boxed{
passCount(v)=endCount(v)+\sum_{child}passCount(child).
}
\]

Tra từ chính xác đọc `endCount`, tra tiền tố đọc `passCount`. Khi xóa một bản sao, chỉ được cắt nhánh **không còn từ đi qua** (`passCount=0`). Khi gợi ý theo thứ tự từ điển Java, duyệt **terminal trước, con theo TreeMap tăng dần**, và dừng sau `k` từ phân biệt.

Trie phù hợp khi có **nhiều truy vấn tiền tố**; các thao tác đi theo đường có chi phí tỷ lệ với độ dài từ/tiền tố (và chi phí tra cứu nhánh). Hãy phân biệt thứ tự từ điển UTF-16 với sắp xếp tiếng Việt, và không nhầm bộ đếm bản sao với số khóa phân biệt.

**Điều quyết định sự đúng đắn không phải sơ đồ cây, mà là ý nghĩa nhất quán của từng nút, công thức bộ đếm và thao tác xóa không làm mất nhánh chung.**
