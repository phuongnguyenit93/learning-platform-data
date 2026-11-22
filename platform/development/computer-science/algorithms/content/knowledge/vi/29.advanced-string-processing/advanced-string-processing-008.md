# Cây hậu tố và ý tưởng lập chỉ mục chuỗi

**Cây hậu tố** (*suffix tree*) là một cấu trúc dữ liệu lập chỉ mục **mọi hậu tố của một văn bản** trong một **cây tiền tố có nén đường đi** (*path-compressed trie*). Sau khi xây chỉ mục cho một chuỗi `T` cố định, ta có thể tìm một mẫu `P` mà không phải duyệt lại toàn bộ `T` ở mỗi truy vấn: đi theo nhãn cạnh của cây để kiểm tra `P`, rồi lấy những lá trong cây con để biết tất cả vị trí xuất hiện của `P`. Trên mô hình tra cứu cạnh thích hợp, việc **kiểm tra có tồn tại mẫu** mất `O(|P|)`, và việc **liệt kê k vị trí** mất `O(|P|+k)` trước khi sắp xếp các vị trí đầu ra. Cây còn giúp hiểu các câu hỏi như **chuỗi con lặp dài nhất**, **đoạn chung dài nhất giữa nhiều chuỗi**, thống kê tần suất mẫu và thiết kế các **chỉ mục chuỗi** dùng lại cho nhiều truy vấn.

Bài thuộc nhóm **Xử lý chuỗi nâng cao** trong Computer Science Algorithms, tập trung vào **Cây hậu tố và ý tưởng lập chỉ mục chuỗi**. Nội dung không chỉ nêu tên cấu trúc: ta xây lại cây từ **hậu tố**, giải thích vì sao phải thêm **ký hiệu kết thúc duy nhất**, cách nén cạnh thành đoạn tham chiếu `[start,end)` vào văn bản, tìm mẫu dừng **giữa một cạnh**, đếm/tìm vị trí xuất hiện ở các lá, suy ra chuỗi con lặp dài nhất từ nút phân nhánh, kiểm tra độ phức tạp và triển khai **Java 17+ chạy độc lập**. Cuối bài so sánh với **suffix array, LCP, suffix automaton, suffix trie và FM-index**, nêu các tình huống cần thuật toán xây dựng nhanh hơn như Ukkonen, vấn đề Unicode/offset và kiểm thử ngẫu nhiên độc lập.

**Điểm cần phân biệt ngay:** một **suffix tree nén đường** có **số nút/cạnh tuyến tính** theo độ dài chuỗi, nhưng **không phải bất kỳ cách xây nào cũng chạy tuyến tính**. Bản Java trong bài dùng cách **chèn từng hậu tố trực tiếp**, dễ kiểm chứng nhưng có thời gian xây **`O(n²)` trong trường hợp xấu**. Các thuật toán xây chuyên biệt như Ukkonen có thể đạt **`O(n)`** dưới những giả thiết phù hợp về bảng chữ cái, nhưng cần thêm active point, suffix links và các bất biến phức tạp.

## 1. Bài toán: nhiều truy vấn trên cùng một văn bản

Cho văn bản cố định `T` có n ký tự theo một hệ đơn vị đã chọn, và nhiều mẫu truy vấn `P₁,P₂,...`. Ta thường muốn biết:

- Mẫu P **có xuất hiện** trong T hay không?
- Nếu có, **ở những vị trí bắt đầu nào**?
- Có bao nhiêu lần xuất hiện, **có tính chồng lấn**?
- Mẫu nào lặp nhiều nhất? **Chuỗi con lặp dài nhất** có độ dài bao nhiêu?
- Hai vị trí bất kỳ có tiền tố chung dài đến đâu?
- Trong một hệ thống có nhiều tài liệu, mẫu nào nằm ở những tài liệu nào?

Một lần tìm bằng KMP có thể chạy `O(n+m)` với m=|P|, và đây thường là lựa chọn tốt cho **một hoặc vài truy vấn**. Nhưng nếu phải hỏi **hàng chục nghìn mẫu khác nhau trên cùng văn bản**, duyệt lại n ký tự cho từng mẫu tốn kém. Từ đó xuất hiện ý tưởng:

**Tiền xử lý T một lần để tạo chỉ mục; mỗi truy vấn chỉ đọc phần liên quan của chỉ mục.**

Đây là sự đánh đổi rõ ràng giữa **thời gian và bộ nhớ xây trước** với **thời gian truy vấn về sau**.

### Substring khác subsequence và suffix

- **Substring (chuỗi con liên tiếp)**: ký tự nằm liên tiếp trong T. Với T=`"banana"`, `"ana"` là substring tại 1 và 3.
- **Subsequence (dãy con không nhất thiết liên tiếp)**: được phép bỏ qua vị trí. Ví dụ `"bna"` là subsequence của `"banana"` nhưng **không** phải substring.
- **Suffix (hậu tố)**: đoạn liên tiếp từ vị trí i tới **cuối T**, ký hiệu `T[i..n−1]`.
- **Prefix (tiền tố)**: đoạn liên tiếp từ đầu T đến một vị trí.

Mọi substring `T[i..j]` đều là **prefix của hậu tố T[i..n−1]**. Đây là cầu nối lý thuyết khiến việc lập chỉ mục **mọi hậu tố** hỗ trợ truy vấn **mọi chuỗi con liên tiếp**.

## 2. Các hậu tố của “banana”

Với T=`"banana"`, n=6 và chỉ số 0-based:

| i | Hậu tố T[i..n−1] |
|---:|---|
| 0 | `banana` |
| 1 | `anana` |
| 2 | `nana` |
| 3 | `ana` |
| 4 | `na` |
| 5 | `a` |
| 6 | `""` (hậu tố rỗng) |

Nếu tạo một **trie** bằng cách chèn trực tiếp mọi hậu tố, mỗi cạnh mang một ký tự và các hậu tố chia sẻ tiền tố được gộp ở phần đầu đường đi. Tuy nhiên, trie chưa nén có thể có **`Θ(n²)` nút/cạnh** trong trường hợp xấu, vì tổng độ dài các hậu tố:

**`n+(n−1)+...+1=n(n+1)/2=Θ(n²)`.**

Cây hậu tố đúng nghĩa dùng **nén chuỗi cạnh đơn nhánh** để chỉ giữ các **điểm phân nhánh** và các **lá**. Ví dụ một đoạn gồm 50 ký tự không có phân nhánh có thể được biểu diễn bằng **một cạnh có nhãn dài 50**, thay vì 50 nút trung gian.

### Vì sao cần ký hiệu kết thúc duy nhất?

Ta thêm một **terminator** `⊥` không xuất hiện trong bất kỳ ký tự của T:

**`T' = T ⧺ ⊥`**.

Với T=banana:

~~~text
0: banana⊥
1: anana⊥
2: nana⊥
3: ana⊥
4: na⊥
5: a⊥
6: ⊥
~~~

Mỗi hậu tố của T' kết thúc bằng **đúng một** terminator. Nhờ ký hiệu này, không có một hậu tố nào là **tiền tố đúng** của hậu tố khác: các hậu tố đều có thể được biểu diễn bằng **lá riêng**, kể cả hậu tố rỗng của T chỉ chứa ⊥.

Nếu bỏ terminator, hậu tố `"a"` đồng thời là tiền tố của `"ana"`; muốn gắn vị trí kết thúc tại một nút trong cây sẽ phải thiết kế thêm dấu kết thúc ở nút nội bộ. Dùng terminator duy nhất đơn giản hóa chứng minh và cài đặt.

**Rất quan trọng:** ký hiệu ⊥ là ký hiệu trừu tượng. Nếu thật sự dùng một ký tự như `'$'` nhưng văn bản đã chứa `'$'`, nó không còn duy nhất, cấu trúc có thể sai. Bản Java dùng **giá trị số nguyên −1**, ngoài miền Unicode code point hợp lệ, để không đụng độ với bất kỳ ký tự hợp lệ nào.

## 3. Nén đường: suffix trie và suffix tree khác nhau thế nào?

Một **suffix trie chưa nén** lưu mỗi ký tự trên một cạnh và có thể dài bậc hai theo n. Một **suffix tree nén** chỉ giữ:

1. **Root (gốc)**: đại diện chuỗi rỗng.
2. **Internal node**: nơi có ít nhất **hai cạnh đi ra** mang ký tự đầu khác nhau.
3. **Leaf (lá)**: đại diện cho một hậu tố bắt đầu tại một vị trí cụ thể `suffixStart=i`.
4. **Edge (cạnh)**: không nhất thiết một ký tự; nó đại diện cho **một đoạn liên tiếp** của T'.

Cây có thuộc tính: từ một nút, **hai cạnh con không bắt đầu bằng cùng ký tự**. Đây là điều kiện giúp đi tìm một mẫu có **một hướng lựa chọn duy nhất** ở mỗi nút.

### Cách lưu nhãn cạnh không sao chép chuỗi

Không lưu `String label` mới cho từng cạnh. Lưu:

**`edge.start` và `edge.end`**, với **`[start,end)`** là một khoảng nửa kín trong mảng T' chung:

~~~text
T' = b a n a n a ⊥
     0 1 2 3 4 5 6

edge [1, 4)  = "ana"
edge [4, 7)  = "na⊥"
~~~

Một nhãn cạnh dài L vẫn chỉ cần hai chỉ số nguyên và con trỏ tới nút đích: **`O(1)` metadata cho cạnh**, không cần copy L ký tự.

**Không được** hiểu nhầm `edge.end` là chỉ số cuối **inclusive**. Trong mã này, `end` **exclusive** và độ dài nhãn là:

**`edge.end−edge.start`**.

Nếu có UTF-16 surrogate hay code point ngoài BMP, các chỉ số cạnh trong bài đo bằng **số Unicode code point trong mảng `int[]`**, không phải `String.charAt` index.

## 4. Cây có bao nhiêu nút và lá?

T'=T⊥ có `n+1` hậu tố, kể cả hậu tố bắt đầu tại vị trí terminator. Khi mỗi hậu tố được đại diện bởi một lá, cây có đúng **`L=n+1` lá**.

Trong cây đã nén, **mọi nút nội bộ khác lá có ít nhất hai con** (gốc cũng có thể chỉ có một con trong vài mô hình đặc biệt, nhưng bản chèn terminator ở đây có nhiều tình huống; cận tổng vẫn đúng khi xử lý gốc). Với một cây có L lá và các nút trong có bậc ít nhất 2, số nút trong nhiều nhất L−1, từ đó:

**Số nút ≤ 2L−1 = 2n+1** trong trường hợp n≥1 với gốc phân nhánh.

Khi n=0, ta có gốc và một lá terminator, tức **2 nút**; nên dùng cận tổng quát an toàn **`≤2(n+1)`** cho cả trường hợp rỗng.

Số cạnh = số nút−1 nên cũng **O(n)**. Nếu mỗi nút chứa một `HashMap<Integer,Edge>`, bộ nhớ lý thuyết vẫn O(n) cho các map entries/edges, nhưng **hằng số bộ nhớ Java có thể lớn** do object và HashMap overhead. Một suffix array thường tiết kiệm RAM thực tế hơn.

**Không suy ra thời gian xây O(n) từ số nút O(n).** Cách chèn hậu tố ngây thơ vẫn có thể đọc/so khớp n ký tự cho nhiều hậu tố, tổng O(n²).

## 5. Chèn một hậu tố vào cây nén

Ta duyệt các hậu tố T'[i..n], `i=0..n`, lần lượt. Để chèn hậu tố mới bắt đầu tại i:

1. Bắt đầu ở root và vị trí đang đọc `j=i` trong T'.
2. Từ nút hiện tại, tìm cạnh con có **ký tự đầu bằng T'[j]**.
3. **Chưa có cạnh:** tạo một cạnh mang đoạn `[j,n+1)` tới một lá có `suffixStart=i`. Hoàn tất.
4. **Có cạnh:** so sánh T'[j...] với các code point trên nhãn cạnh để tìm độ dài khớp k.
5. Nếu khớp **hết nhãn cạnh**, đi xuống nút con, tăng j thêm k rồi xét tiếp.
6. Nếu khác nhau **giữa nhãn cạnh**, phải **split edge**:
   - Tạo nút `mid`.
   - Cạnh cũ từ parent tới child được thay bằng cạnh parent→mid mang **phần khớp** `[oldStart,oldStart+k)`.
   - Gắn lại cạnh mid→oldChild mang **phần còn lại** của nhãn cũ `[oldStart+k,oldEnd)`.
   - Tạo cạnh mid→newLeaf mang phần hậu tố mới `[j+k,n+1)`.
   - Đặt `newLeaf.suffixStart=i`.
7. Không thêm hoặc xóa code point khỏi T'; chỉ **đổi các khoảng nhãn cạnh** và liên kết nút.

### Minh họa split

Giả sử root đã có một cạnh chứa nhãn `"banana⊥"`. Khi chèn hậu tố `"ana⊥"`, ký tự đầu khác b, tạo cạnh mới. Khi chèn `"nana⊥"` cũng tạo cạnh mới bắt đầu n. Đến hậu tố `"ana⊥"` trong cây đã có nhánh bắt đầu a với `"anana⊥"`, hai hậu tố này cùng tiền tố `"ana"` rồi khác:

~~~text
                 "ana"
root -------> (mid)
               / \
            "na⊥" "⊥"
              /     \
         suffix 1  suffix 3
~~~

Nút mid đại diện chuỗi `"ana"`. Nhánh từ mid đến suffixStart=1 mang phần `"na⊥"`; nhánh đến suffixStart=3 chỉ mang `"⊥"`. Đây cũng là lý do một điểm phân nhánh là dấu hiệu của **một chuỗi con xuất hiện ở nhiều vị trí**.

### Tại sao split không làm mất hậu tố cũ?

Trước split, đường root→oldChild đã chứa nhãn `oldLabel`. Sau split, nhãn đường mới là:

**`prefixOfOldLabel ⧺ suffixOfOldLabel = oldLabel`**.

Do đó đường đi tới **mọi lá cũ** không đổi chuỗi biểu diễn. Đường mới qua mid→newLeaf biểu diễn chính xác phần còn lại của hậu tố được chèn. Bất biến mọi hậu tố trước đó vẫn có trong cây được bảo toàn.

### Vì sao mã có thể giả định hậu tố mới cuối cùng sẽ tạo lá?

Vì ký hiệu kết thúc ⊥ là duy nhất, **hai hậu tố khác vị trí không thể trùng nhau hoặc là tiền tố đúng của nhau**. Do đó, khi chèn hậu tố i chưa có, đến một thời điểm nó phải đi vào một nhánh mới hoặc khác giữa một cạnh; không xảy ra trường hợp một suffix i khác vị trí nhưng hết ký tự tại một lá cũ mà không thể thêm lá.

Nếu bỏ terminator hoặc dùng terminator xuất hiện tự nhiên trong input, giả định này có thể bị phá vỡ.

## 6. Tìm một mẫu không cần quét toàn văn bản

Giả sử đã có cây của T⊥. Để tìm mẫu `P` có m code point:

1. Bắt đầu ở root và i=0 của P.
2. Chọn cạnh có ký tự đầu đúng bằng `P[i]`.
3. So sánh lần lượt các code point của P với các code point trên nhãn cạnh.
4. Nếu có ký tự khác, **không có lần xuất hiện nào** ⇒ trả rỗng.
5. Nếu hết nhãn cạnh nhưng chưa hết P, đi xuống nút con và tiếp tục.
6. Nếu đã tiêu thụ **hết P**, kể cả khi đang ở **giữa một nhãn cạnh**, đã tìm được đường biểu diễn P ⇒ P **tồn tại** trong T.
7. Để lấy tất cả vị trí, duyệt **mọi lá nằm dưới nút đích của cạnh đang khớp**, thu các `suffixStart` và sắp theo vị trí tăng dần nếu API yêu cầu.

**Không cần** ép P phải kết thúc chính xác ở một nút. Ví dụ một mẫu chỉ khớp **một phần nhãn của một cạnh dài** vẫn là một substring của T.

### Vì sao mọi lá bên dưới là một lần xuất hiện?

Một đường root→leaf biểu diễn toàn bộ một hậu tố T'[i..]. Nếu trên đường ấy đã khớp P, nghĩa là P chính là **tiền tố của hậu tố ở i**. Do đó:

**`T[i..i+m−1]=P`**,

tức P xuất hiện trong T ở vị trí i. Ngược lại, nếu P xuất hiện tại i thì P là tiền tố hậu tố i, nên đường từ root đến lá suffixStart=i bắt buộc đi qua đoạn nhãn biểu diễn P. Hai chiều cho biết các lá bên dưới đúng là **toàn bộ occurrences**, không thiếu và không thừa.

### Ví dụ trên “banana”

Với `T="banana"`:

| Pattern | Vị trí bắt đầu (0-based) |
|---|---|
| `ana` | [1,3] |
| `na` | [2,4] |
| `ban` | [0] |
| `a` | [1,3,5] |
| `banana` | [0] |
| `xyz` | [] |
| `bananas` | [] |

**Chồng lấn được tính.** `"ana"` ở 1..3 và ở 3..5 cùng dùng chữ a ở vị trí 3, nhưng vẫn là **hai lần xuất hiện khác vị trí bắt đầu**.

### Vậy truy vấn có thật sự O(m) không?

Nếu chỉ hỏi **`contains(P)`**, khi đã có cây, quá trình đi theo nhãn cạnh đọc tối đa m code point ⇒ kỳ vọng **O(m)** với tra cứu cạnh theo ký tự đầu gần O(1) bằng map. Nếu cần **liệt kê k vị trí**, phải phát k số ⇒ ít nhất **Ω(k)**; do đó có thể đạt **O(m+k)** trước sắp xếp. Nếu trả vị trí theo thứ tự số tăng dần bằng `Collections.sort`, thêm **`O(k log k)`**.

Không được quảng cáo hàm trả **mọi** vị trí trong O(m) vì output tự nó có thể dài Θ(n), ví dụ pattern `"a"` trong `"aaaaa..."`.

## 7. Một điểm khó: mẫu kết thúc giữa cạnh

Xét một cạnh có nhãn `"abcdef"`, pattern chỉ cần `"abc"`. Khi so khớp ba code point đầu, pattern đã hết nhưng cạnh còn `"def"`.

**Kết luận đúng:** P có trong văn bản, vì root→(điểm giữa cạnh) đã biểu diễn P. Mọi lá của nút ở **cuối cạnh** đều đại diện cho suffix có tiền tố `"abc"`.

Nếu code chỉ báo match khi vừa tới **cuối edge**, nó sẽ bỏ sót nhiều substring hợp lệ, đặc biệt trên văn bản có ít ký tự lặp khi mỗi cạnh gốc rất dài.

Mã dùng biến `i` cho vị trí trong pattern và `pos` cho vị trí trong mảng text tương ứng nhãn cạnh. Vòng lặp dừng khi **i==pattern.length**, cho dù `pos<edge.end`; lúc đó nó thu lá từ `edge.to`.

### Mẫu dài hơn văn bản

Nếu P dài hơn T, nó chắc chắn không thể là một substring của T. Trong cây có terminal −1 ở cuối hậu tố, việc so sánh P với nhãn bao gồm −1 sẽ thất bại, vì P chỉ gồm Unicode scalar hợp lệ (≥0) nên không thể chứa −1. Chương trình trả `[]`, không gây tràn chỉ số.

### Mẫu rỗng

Bản Java chọn quy ước có ý nghĩa rõ:

**Chuỗi rỗng xuất hiện ở mọi ranh giới code point, tổng cộng n+1 vị trí `[0,1,...,n]`.**

Chẳng hạn T=banana có 7 ranh giới và `find("")=[0,1,2,3,4,5,6]`. Với T rỗng, `find("")=[0]`. Đây là **quy ước API**, không phải một tính chất bắt buộc của mọi thư viện tìm chuỗi; một hệ thống khác có thể chủ động từ chối pattern rỗng nếu đề yêu cầu.

**Không** lẫn lá suffixStart=n (hậu tố chỉ gồm terminator) vào kết quả của **pattern không rỗng**. Nó chỉ tương ứng với ranh giới cuối khi pattern rỗng theo quy ước.

## 8. Chuỗi con lặp dài nhất: nhìn vào internal node

Một **repeated substring** là chuỗi con xuất hiện ở **ít nhất hai vị trí bắt đầu khác nhau**. Theo định nghĩa này, **hai occurrences được phép chồng lấn**. Ví dụ `"aaaa"` xuất hiện trong `"aaaaa"` ở vị trí 0 và 1; đây là repeated substring độ dài 4 dù các khoảng overlap.

Trong suffix tree có terminator:

- Mỗi **nút phân nhánh** có từ hai lá hậu tố bên dưới.
- Nhãn đường từ root tới nút ấy là tiền tố chung của ít nhất hai hậu tố ⇒ substring xuất hiện ít nhất hai lần.
- Độ dài substring đó bằng **tổng độ dài nhãn các cạnh** trên đường root→nút.
- Ngược lại, substring lặp dài nhất luôn tương ứng với **một điểm phân nhánh**, vì nếu hai hậu tố cùng thêm được một ký tự thì điểm chung có thể kéo dài; độ dài lặp lớn nhất dừng tại chỗ hai hậu tố tách nhau (hoặc tương đương một điểm nội bộ đã được nén).

Do đó có thể tìm **longest repeated substring (LRS)** bằng cách duyệt cây và chọn **internal node có path depth lớn nhất**. Một lá bên dưới cho ta vị trí bắt đầu của substring, còn truy vấn find cho substring ấy cho ta tất cả occurrences.

### Ví dụ

| Văn bản | Một LRS | Vị trí |
|---|---|---|
| `banana` | `ana` | [1,3] |
| `mississippi` | `issi` | [1,4] |
| `aaaaa` | `aaaa` | [0,1] |
| `🙂a🙂a` | `🙂a` | [0,2] theo code point |
| `abcdef` | chuỗi rỗng (không có đoạn lặp không rỗng) | [] |

**LRS có thể không duy nhất:** nhiều substring cùng đạt độ dài lặp lớn nhất. Mã bên dưới chỉ trả **một** LRS; vì duyệt các cạnh trong `HashMap`, không cam kết tie-break từ điển nếu nhiều LRS đồng độ dài. Các ví dụ cố định ở đây có đáp án dài nhất duy nhất.

### Vì sao không dùng lá cho LRS?

Một lá đại diện cho **một hậu tố đầy đủ**, có thể có đường root→lá rất dài nhưng chỉ có **một lần xuất hiện**. Chỉ những đường đến **internal node có từ hai nhánh hậu tố** mới bảo đảm đoạn được chia sẻ. Nếu chọn nút có độ sâu lớn nhất bất kể lá, ta có thể trả cả văn bản dù nó xuất hiện một lần — sai định nghĩa lặp.

### Tại sao không cộng terminator vào LRS?

Terminator chỉ xuất hiện một lần ở cuối mảng T'. Không có hai hậu tố **khác nhau** nào có thể cùng chia sẻ ký hiệu ⊥ như phần còn lại của một tiền tố chung, nên nó **không thuộc đường dẫn đến một internal node** trong suffix tree hợp lệ. Vì vậy path depth của các internal node trong bản cài là độ dài substring **trong văn bản gốc**.

## 9. Cách cài đơn giản và cách xây tuyến tính khác nhau

### Chèn từng suffix: dễ hiểu, chi phí xây O(n²)

Có n+1 hậu tố. Tổng số code point trên chúng là:

**`Σ_{i=0}^n(n−i+1)=Θ(n²)`.**

Chèn trực tiếp một hậu tố có thể cần quét độ dài hậu tố ấy qua nhiều nhãn cạnh. Vì vậy tổng thời gian xây của bản đơn giản là **`O(n²)`**, dù số node/edge được tạo chỉ **`O(n)`**. Đây là lựa chọn tốt cho học thuật, dữ liệu vừa phải, bài cần quan sát split và tính đúng.

**Không nên** dùng bản naive nếu xây index cho chuỗi dài hàng triệu code point hoặc cần cập nhật thời gian thực; công đoạn build có thể trở thành nút thắt.

### Ukkonen: ý tưởng tăng dần với suffix links

Thuật toán **Ukkonen** xây suffix tree theo các **pha mở rộng từng ký tự mới của text**, dùng:

- **Implicit/explicit suffix tree:** có thể tạm chưa có lá cho từng hậu tố trong các pha trung gian; terminator giúp kết thúc với cây tường minh.
- **Active point (activeNode, activeEdge, activeLength):** vị trí hiện tại của phần hậu tố cần xử lý, có thể ở giữa một edge.
- **Suffix links:** nối một internal node biểu diễn `xα` tới vị trí biểu diễn `α` (bỏ ký tự đầu thích hợp), giúp chuyển nhanh giữa các hậu tố liên quan mà không quay về root và quét lại toàn bộ.
- **Remainder:** số hậu tố còn cần xử lý trong pha.
- **Open-ended leaf edges:** các lá dùng một biến `leafEnd` chia sẻ để “mọc dài” cùng văn bản, tránh cập nhật từng lá sau mỗi ký tự.

Với phép tìm cạnh theo ký tự hiệu quả và một alphabet được xử lý phù hợp, Ukkonen có thể đạt **O(n)** thời gian xây (kỳ vọng với một số cách dùng hashing; hoặc dùng cấu trúc tra cứu/chuyển bảng chữ cái có cận phù hợp), và O(n) bộ nhớ. Đây là thuật toán khó hơn nhiều so với chèn suffix trực tiếp; **bản mã Java trong bài không tự nhận là Ukkonen và không có cận O(n) build**.

Các thuật toán cổ điển khác gồm **Weiner** và **McCreight**. Chọn xây tuyến tính chỉ khi dữ liệu đủ lớn và chi phí cài đặt/kiểm chứng xứng đáng.

### Tại sao cứ cần “online” là dùng ngay Ukkonen?

Không hẳn. Nếu dữ liệu đến từng chunk và chỉ cần **tìm một mẫu đang biết** trên stream, **KMP streaming** có thể duy trì O(m) bộ nhớ mà không lập chỉ mục toàn bộ dữ liệu. Suffix tree hữu ích khi ta muốn **giữ kho văn bản lớn để hỗ trợ nhiều truy vấn hậu kỳ**, hoặc cần nhiều loại câu hỏi về substring. Một online suffix tree động sẽ phải quản lý **nội dung chỉ mục đang tăng**, chứ không phải cứ lấy cây static xây với terminator cũ rồi nối thêm ký tự là xong.

## 10. Java 17+ hoàn chỉnh: cây hậu tố nén, search và LRS

Chương trình sau xây suffix tree nén cho **một văn bản cố định**. Cài đặt cố tình sử dụng cách **naive suffix insertion** để học và debug đơn giản. Nó vẫn có **O(n) node/edge storage** sau khi xây, không tạo suffix trie chưa nén O(n²) node.

**Hợp đồng:**

- Đầu vào là chuỗi Java `String` (không null), có thể rỗng.
- So sánh **chính xác Unicode code point**; không chuẩn hóa NFC/NFD, không bỏ dấu/không đổi hoa–thường.
- Nếu pattern/text có **unpaired UTF-16 surrogate**, API từ chối bằng `IllegalArgumentException` thay vì tự chèn mã Unicode không hợp lệ.
- Terminator là số nguyên **−1** trong mảng code point, không xuất hiện trong dữ liệu người dùng.
- Mỗi suffix i từ 0..n tạo một lá có `suffixStart=i`, kể cả terminator-only suffix ở i=n.
- Pattern không rỗng trả các vị trí bắt đầu **trong T gốc** theo code point; kết quả được **sắp tăng**.
- Pattern rỗng trả **tất cả n+1 ranh giới** code point.
- Phương thức `longestRepeated` trả **một chuỗi con lặp dài nhất** (cho phép chồng lấn), kèm các vị trí xuất hiện.
- Mã dùng stack duyệt cây **tường minh** khi gom lá và tìm LRS để tránh đệ quy duyệt cây sâu; xây cây bằng vòng lặp. Bộ nhớ bổ sung lúc duyệt O(n).

### Các lớp dữ liệu

- `Node.out`: map từ **code point đầu của cạnh** đến đối tượng Edge.
- `Node.suffixStart`: vị trí bắt đầu suffix nếu là lá; −1 nếu là internal node.
- `Edge.start` và `Edge.end`: khoảng nhãn **[start,end)** trong mảng text đã thêm terminator.
- `Edge.child`: nút ở cuối cạnh.
- `SuffixTreeIndex.index[]`: toàn bộ code point của văn bản cộng sentinel −1.
- `nodeCount`: số nút được tạo (chỉ để dễ QA).
- `Repeat(value,positions)`: giá trị một LRS và các vị trí xuất hiện.

Lưu thành **`SuffixTreeIndexDemo.java`**:

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public final class SuffixTreeIndexDemo {
    private static final int TERMINATOR = -1;

    private record Repeat(String value, List<Integer> positions) {}
    private record Frame(Node node, int depth) {}

    private static final class Node {
        final Map<Integer, Edge> out = new HashMap<>();
        final int suffixStart; // -1 means internal node.

        Node(int suffixStart) {
            this.suffixStart = suffixStart;
        }
    }

    private static final class Edge {
        final int start;   // Inclusive index in index[].
        final int end;     // Exclusive index in index[].
        final Node child;

        Edge(int start, int end, Node child) {
            this.start = start;
            this.end = end;
            this.child = child;
        }
    }

    private static int[] strictCodePoints(String text) {
        if (text == null) {
            throw new IllegalArgumentException("Null text/pattern");
        }

        int[] buffer = new int[text.length()];
        int count = 0;

        for (int i = 0; i < text.length();) {
            char ch = text.charAt(i++);
            if (Character.isHighSurrogate(ch)) {
                if (i >= text.length()
                        || !Character.isLowSurrogate(
                                text.charAt(i))) {
                    throw new IllegalArgumentException(
                            "Invalid high surrogate");
                }
                buffer[count++] =
                        Character.toCodePoint(ch, text.charAt(i++));
            } else if (Character.isLowSurrogate(ch)) {
                throw new IllegalArgumentException(
                        "Invalid low surrogate");
            } else {
                buffer[count++] = ch;
            }
        }

        return Arrays.copyOf(buffer, count);
    }

    private static final class SuffixTreeIndex {
        private final int[] index; // Original code points + -1.
        private final int n;       // Original code point count.
        private final Node root = new Node(-1);
        private int nodeCount = 1;

        SuffixTreeIndex(String text) {
            int[] points = strictCodePoints(text);
            if (points.length == Integer.MAX_VALUE) {
                throw new IllegalArgumentException(
                        "Index too large for sentinel");
            }
            n = points.length;
            index = Arrays.copyOf(points, n + 1);
            index[n] = TERMINATOR;

            for (int start = 0; start <= n; start++) {
                addSuffix(start);
            }
        }

        int length() {
            return n;
        }

        int nodes() {
            return nodeCount;
        }

        private void addSuffix(int suffixStart) {
            Node current = root;
            int cursor = suffixStart;

            while (true) {
                Edge edge = current.out.get(index[cursor]);
                if (edge == null) {
                    Node leaf = new Node(suffixStart);
                    nodeCount++;
                    current.out.put(index[cursor],
                            new Edge(cursor, index.length, leaf));
                    return;
                }

                // Count common code points on this edge.
                int common = 0;
                while (edge.start + common < edge.end
                        && cursor + common < index.length
                        && index[edge.start + common]
                               == index[cursor + common]) {
                    common++;
                }

                if (edge.start + common == edge.end) {
                    // Matched all of this compressed edge.
                    cursor += common;
                    current = edge.child;
                    continue;
                }

                // Unique sentinel guarantees a different suffix
                // must diverge before its own end.
                if (cursor + common >= index.length) {
                    throw new IllegalStateException(
                            "Missing unique terminator");
                }

                Node middle = new Node(-1);
                nodeCount++;

                // Preserve the old suffixes under the new middle.
                Edge oldTail = new Edge(
                        edge.start + common,
                        edge.end, edge.child);
                middle.out.put(index[oldTail.start], oldTail);

                // New suffix branches off at the first mismatch.
                Node leaf = new Node(suffixStart);
                nodeCount++;
                Edge newTail = new Edge(
                        cursor + common, index.length, leaf);
                middle.out.put(index[newTail.start], newTail);

                // Replace parent's former edge with its prefix.
                current.out.put(index[edge.start],
                        new Edge(edge.start,
                                edge.start + common, middle));
                return;
            }
        }

        private void collectLeaves(Node from,
                                   List<Integer> result) {
            ArrayDeque<Node> stack = new ArrayDeque<>();
            stack.push(from);

            while (!stack.isEmpty()) {
                Node node = stack.pop();
                if (node.suffixStart >= 0) {
                    // The sentinel-only suffix does not match
                    // a nonempty Unicode pattern.
                    if (node.suffixStart < n) {
                        result.add(node.suffixStart);
                    }
                } else {
                    for (Edge edge : node.out.values()) {
                        stack.push(edge.child);
                    }
                }
            }
        }

        List<Integer> find(String pattern) {
            int[] p = strictCodePoints(pattern);

            if (p.length == 0) {
                List<Integer> boundaries = new ArrayList<>();
                for (int i = 0; i <= n; i++) {
                    boundaries.add(i);
                }
                return List.copyOf(boundaries);
            }

            Node current = root;
            int i = 0;

            while (i < p.length) {
                Edge edge = current.out.get(p[i]);
                if (edge == null) {
                    return List.of();
                }

                int pos = edge.start;
                while (pos < edge.end && i < p.length) {
                    if (index[pos] != p[i]) {
                        return List.of();
                    }
                    pos++;
                    i++;
                }

                if (i == p.length) {
                    // Pattern may END INSIDE this edge.
                    List<Integer> result = new ArrayList<>();
                    collectLeaves(edge.child, result);
                    Collections.sort(result); // Text order.
                    return List.copyOf(result);
                }

                // Edge ended before the query: descend.
                current = edge.child;
            }

            throw new IllegalStateException(
                    "Nonempty query ended without matching edge");
        }

        // Deepest internal node encodes one longest repeat.
        Repeat longestRepeated() {
            Node bestNode = null;
            int bestLength = 0;
            ArrayDeque<Frame> stack = new ArrayDeque<>();
            stack.push(new Frame(root, 0));

            while (!stack.isEmpty()) {
                Frame frame = stack.pop();
                for (Edge edge : frame.node().out.values()) {
                    int depth = frame.depth()
                            + edge.end - edge.start;

                    if (edge.child.suffixStart < 0) {
                        if (depth > bestLength) {
                            bestLength = depth;
                            bestNode = edge.child;
                        }
                        stack.push(new Frame(edge.child, depth));
                    }
                }
            }

            if (bestNode == null) {
                return new Repeat("", List.of());
            }

            // Find one suffix leaf below the selected node.
            ArrayDeque<Node> descend = new ArrayDeque<>();
            descend.push(bestNode);
            int suffixStart = -1;

            while (!descend.isEmpty() && suffixStart < 0) {
                Node node = descend.pop();
                if (node.suffixStart >= 0) {
                    suffixStart = node.suffixStart;
                } else {
                    for (Edge edge : node.out.values()) {
                        descend.push(edge.child);
                    }
                }
            }

            if (suffixStart < 0) {
                throw new IllegalStateException(
                        "Internal node without a suffix leaf");
            }

            // No internal path contains TERMINATOR.
            String value = new String(index,
                    suffixStart, bestLength);
            return new Repeat(value, find(value));
        }
    }

    private static void show(
            String label, String text, String... patterns) {
        SuffixTreeIndex tree = new SuffixTreeIndex(text);
        Repeat repeat = tree.longestRepeated();

        System.out.println(label
                + ": codePoints=" + tree.length()
                + ", nodes=" + tree.nodes()
                + ", longestRepeat=\"" + repeat.value()
                + "\" at " + repeat.positions());

        for (String pattern : patterns) {
            System.out.println(
                    "  find(\"" + pattern + "\") = "
                    + tree.find(pattern));
        }
    }

    public static void main(String[] args) {
        show("banana", "banana",
                "ana", "na", "", "banana", "xyz");

        show("mississippi", "mississippi",
                "issi", "ss", "pi");

        show("repeated", "aaaaa",
                "aa", "aaaa");

        show("unicode", "🙂a🙂a",
                "🙂a", "🙂", "");

        show("empty", "",
                "", "a");

        show("distinct", "abcdef",
                "abc", "cde", "z");
    }
}
~~~

Biên dịch/chạy bằng **JDK 17+**, với mã hóa nguồn UTF-8 cho phần ví dụ chứa emoji:

~~~bash
javac -encoding UTF-8 SuffixTreeIndexDemo.java
java SuffixTreeIndexDemo
~~~

**Stdout chính xác cho các ví dụ này:**

~~~text
banana: codePoints=6, nodes=11, longestRepeat="ana" at [1, 3]
  find("ana") = [1, 3]
  find("na") = [2, 4]
  find("") = [0, 1, 2, 3, 4, 5, 6]
  find("banana") = [0]
  find("xyz") = []
mississippi: codePoints=11, nodes=19, longestRepeat="issi" at [1, 4]
  find("issi") = [1, 4]
  find("ss") = [2, 5]
  find("pi") = [9]
repeated: codePoints=5, nodes=11, longestRepeat="aaaa" at [0, 1]
  find("aa") = [0, 1, 2, 3]
  find("aaaa") = [0, 1]
unicode: codePoints=4, nodes=8, longestRepeat="🙂a" at [0, 2]
  find("🙂a") = [0, 2]
  find("🙂") = [0, 2]
  find("") = [0, 1, 2, 3, 4]
empty: codePoints=0, nodes=2, longestRepeat="" at []
  find("") = [0]
  find("a") = []
distinct: codePoints=6, nodes=8, longestRepeat="" at []
  find("abc") = [0]
  find("cde") = [2]
  find("z") = []
~~~

### Đọc kết quả mẫu

**banana:** có 7 lá suffix vì n+1=7; cây được nén còn 11 node. `ana` có hai lần xuất hiện ở 1 và 3; LRS cũng là `ana`. Mẫu rỗng có 7 ranh giới.

**mississippi:** `issi` xuất hiện tại 1 và 4, là một LRS dài 4; `ss` xuất hiện tại 2 và 5; `pi` bắt đầu ở 9.

**repeated:** `aa` trong `aaaaa` xuất hiện tại 0,1,2,3, đều tính dù chồng lấn. `aaaa` lặp tại 0 và 1 nên là LRS dài 4.

**unicode:** `🙂a🙂a` dài **4 Unicode code point** nhưng dài **6 UTF-16 code units** vì mỗi 🙂 chiếm hai `char`. Mẫu `🙂a` xuất hiện ở code-point positions 0,2. Trong chỉ số `String` UTF-16, vị trí thứ hai bắt đầu ở code-unit index 3, **khác** 2. Bản mã cố tình trả 2 theo hợp đồng code point.

**empty:** văn bản rỗng vẫn có một ranh giới và một suffix terminator. `find("")=[0]` theo quy ước; không có repeated substring không rỗng.

**distinct:** không có substring không rỗng nào xuất hiện ở hai vị trí, nên trả Repeat với value rỗng và positions rỗng (khác với `find("")`, vốn trả các ranh giới). Các truy vấn substring bình thường vẫn hoạt động.

### Cách dùng `find` cho câu hỏi contains và count

Nếu chỉ cần `contains(P)`, có thể đổi hàm tìm thành trả boolean khi **đã tiêu thụ hết P**, không cần duyệt lá hay sắp xếp. Nếu chỉ cần số occurrences, có thể tiền xử lý `leafCount` tại mỗi node; khi mẫu kết thúc giữa edge, số occurrences là số lá phía dưới edge.child (không tính sentinel-only leaf đối với mẫu không rỗng). Việc này tránh liệt kê k kết quả và cho thời gian truy vấn O(m).

Mã minh họa luôn **tìm tất cả rồi sắp** để dễ quan sát và đối chiếu. Không được coi độ phức tạp của chính hàm `find` trong mã là O(m) khi k có thể lớn.

## 11. Chứng minh cài đặt biểu diễn đúng mọi suffix

### Bất biến sau mỗi lần chèn

Sau khi chèn các hậu tố bắt đầu tại 0,1,...,i, có đúng i+1 lá đã tạo, mỗi lá gắn một `suffixStart` khác nhau, và nhãn đường root→lá là chính xác hậu tố T'[suffixStart..n]. Mỗi nút có tối đa một cạnh bắt đầu bằng một code point cụ thể.

**Khởi tạo:** trước chèn, root không có cạnh và chưa có lá, bất biến hiển nhiên.

**Bước chèn i:**

- **Không có cạnh bắt đầu T'[cursor]:** thêm cạnh mang phần hậu tố còn lại tới lá mới; không ảnh hưởng nhãn đường tới lá cũ.
- **Cạnh có cùng ký tự đầu và khớp trọn label:** đi xuống, không đổi cấu trúc cho tới chỗ cần thêm nhánh.
- **Cạnh chỉ khớp một phần:** tách thành đoạn tiền tố chung và hai đoạn khác nhau từ mid. Nhãn đường tới các lá cũ không đổi; nhãn đường tới lá i là đúng hậu tố mới. Hai cạnh từ mid bắt đầu bằng **hai code point khác nhau** tại chỗ mismatch, nên tính duy nhất khóa child được bảo toàn.

Nhờ terminator riêng, suffix i sẽ phát sinh **một lá mới**, không kết thúc hoàn toàn ở lá của một hậu tố khác. Vì vậy bất biến đúng sau mọi lần chèn.

Kết thúc `i=n` có n+1 lá, tương ứng đủ tất cả suffix của T'.

### Tính đúng của find

**Nếu báo một vị trí s:** thuật toán đã so toàn bộ P thành công trên nhãn đường từ root tới một cạnh; lá s nằm dưới cạnh đó nên nhãn đường tới lá s có tiền tố P. Vì nhãn lá s là T'[s..], P xuất hiện ở s trong T.

**Nếu P xuất hiện ở s:** P là prefix hậu tố T'[s..]; đường root→lá s là một trong các đường được index. Mọi ký tự P đều khớp dọc đường đó, nên thuật toán không thể rẽ sai ở một nút (cạnh có ký tự đầu duy nhất) hoặc báo mismatch trước khi đọc hết P. Lá s sẽ nằm trong cây con được gom ⇒ s được báo.

**Không có vị trí lặp:** mỗi suffixStart là ID của đúng một lá; khi gom cây con, mỗi lá chỉ thăm một lần. Nếu P có nhiều occurrences overlap, chúng vẫn là các suffixStart **khác nhau** nên đều được báo.

### Tính đúng của longestRepeated

Mỗi internal node có ít nhất hai lá dưới nó. Nhãn root→node là prefix chung của ít nhất hai suffix khác vị trí ⇒ substring lặp. Mọi substring lặp có ít nhất hai occurrences, tương ứng hai suffix chia sẻ một prefix. Prefix chung dài nhất của hai suffix đạt tới nút phân nhánh của chúng, và độ sâu nút ấy ≥ độ dài substring đang xét. Vì thế internal node sâu nhất có độ dài bằng **LRS optimum**. Chọn một lá bên dưới cung cấp một occurrence hợp lệ, và tìm lại substring bằng find cho đủ các occurrences.

## 12. Độ phức tạp: build, query, output, lưu trữ

Đặt n=|T| theo Unicode code point, m=|P|, k= số lần P xuất hiện.

| Thao tác | Cài naive trong bài | Ghi chú |
|---|---|---|
| Chuyển T thành code point | O(n) | Đếm theo code point, quét UTF-16 |
| Xây index bằng chèn mọi suffix | **O(n²) worst-case** | Không phải Ukkonen |
| Số nút/cạnh sau nén | **O(n)** | Có n+1 lá và O(n) internal nodes |
| Bộ nhớ index | **O(n)** | Bỏ overhead HashMap/object constant factors |
| Kiểm tra mẫu có tồn tại | **O(m)** expected | Đi cạnh theo ký tự đầu bằng HashMap |
| Liệt kê k vị trí chưa cần thứ tự | **O(m+k)** expected | Output tự nó dài k |
| `find` mã Java trả vị trí đã sắp | **O(m+k log k)** expected | `Collections.sort` |
| Duyệt tìm LRS | **O(n)** trên cây đã xây | Chọn internal node sâu nhất |
| LRS kèm mọi vị trí đã sắp | O(n + ℓ + k log k) | ℓ=độ dài LRS, gọi find |
| Cây của text rỗng | 2 nodes | Root + lá terminator |

Cận truy vấn O(m) dựa trên giả thiết lấy cạnh theo một code point trong map có chi phí trung bình O(1). Nếu dùng một cấu trúc cân bằng theo alphabet với O(log σ) mỗi lần lookup, phải tính thêm chi phí tra cứu đó theo số lần rẽ nhánh; nếu dùng mảng cạnh cỡ σ cố định ở mỗi node, overhead có thể thành O(nσ) thay vì O(n).

### Chi phí thực tế và bộ nhớ

Trong Java, **mỗi Node có HashMap**, mỗi Edge là một object, và nhiều liên kết/entry gây overhead bộ nhớ. Dù số phần tử tuyến tính, cây có thể tiêu tốn RAM lớn hơn suffix array dựa trên mảng primitive. Với text lớn, nên đo **thời gian build, throughput truy vấn, peak heap, GC pressure và độ dài output**, thay vì chỉ nhìn ký hiệu Big-O.

Khi một pattern quá phổ biến như `"a"` trong cả triệu ký tự a, phần thời gian phát/sắp k≈n vị trí có thể chi phối hoàn toàn. Có thể chỉ giữ count nếu ứng dụng không cần positions.

## 13. Suffix array và LCP: một cách chỉ mục khác

**Suffix array (SA)** là mảng chứa **vị trí bắt đầu của mọi suffix**, sắp theo **thứ tự từ điển của suffix**. Không lưu cây, chỉ lưu một dãy số nguyên độ dài n+1 (nếu tính terminator-only suffix).

Với `T'=banana⊥` và ký hiệu ⊥ được xem là nhỏ hơn mọi chữ:

| i | SA[i] | Hậu tố | LCP với hậu tố trước |
|---:|---:|---|---:|
| 0 | 6 | `⊥` | 0 |
| 1 | 5 | `a⊥` | 0 |
| 2 | 3 | `ana⊥` | 1 |
| 3 | 1 | `anana⊥` | 3 |
| 4 | 0 | `banana⊥` | 0 |
| 5 | 4 | `na⊥` | 0 |
| 6 | 2 | `nana⊥` | 2 |

**`SA=[6,5,3,1,0,4,2]`**.

**LCP (Longest Common Prefix)** của hai suffix là số code point giống nhau tính từ đầu hai suffix. Ví dụ `LCP(ana⊥,anana⊥)=3`. Mảng LCP của các suffix **liền kề trong SA** theo bảng trên là:

**`LCP=[0,0,1,3,0,0,2]`**,

trong đó phần tử đầu quy ước là 0.

### Tìm pattern bằng suffix array

Các suffix bắt đầu bằng cùng pattern P tạo thành **một đoạn liên tiếp** trong SA theo thứ tự từ điển. Ta dùng **hai lần binary search** để tìm đầu/cuối đoạn suffix có prefix P, rồi xuất các `SA[i]` tương ứng.

- Không cần lưu toàn bộ suffix string; so sánh bằng vị trí SA[i] và mảng text gốc.
- Với cách so sánh nhiều nhất m ký tự cho mỗi bước binary search, thời gian query thường viết **O(m log n+k)** để liệt kê k vị trí **theo thứ tự suffix lexicographic**.
- Nếu muốn trả vị trí theo **thứ tự xuất hiện trong văn bản**, phải **sort k chỉ số**, thêm O(k log k) trừ khi có chỉ mục bổ sung hỗ trợ thứ tự text.
- Mảng SA có bộ nhớ cơ sở **O(n)** với hằng số thấp hơn tree node/object; thuật toán xây SA có nhiều biến thể với độ phức tạp khác nhau.
- LCP giúp giải bài substring lặp; **giá trị LCP lớn nhất giữa hai suffix kề nhau** bằng **độ dài LRS**.

### Chứng minh vì sao max LCP giữa các suffix kề là LRS

Nếu hai suffix bất kỳ cùng chia sẻ prefix dài ℓ, tất cả suffix có prefix ấy xuất hiện trong một **khối liên tiếp** của SA. Trong khối có ít nhất hai suffix, tồn tại một cặp **kề nhau** có LCP≥ℓ. Ngược lại mọi LCP>0 giữa hai suffix là một repeated substring. Do vậy:

**`max_i LCP[i]=độ dài longest repeated substring`**.

Trong banana, max LCP=3 ⇒ LRS length3, phù hợp cây hậu tố.

### Dùng cái nào?

| Đặc điểm | Suffix tree | Suffix array + LCP |
|---|---|---|
| Cấu trúc | Cây nén với labels theo đoạn | Các mảng chỉ số |
| Truy vấn mẫu | Đi theo nhãn, O(m) expected cho existence | Binary search, thường O(m log n) |
| Liệt kê occurrences | Duyệt lá của subtree | Lấy đoạn liên tiếp trong SA |
| LRS | Internal node sâu nhất | Max LCP |
| RAM thực tế | Nhiều node/map/object | Mảng primitive, locality tốt |
| Xây đơn giản | Chèn suffix O(n²) | Sort suffix cơ bản có thể tốn kém |
| Xây tối ưu | Ukkonen/Weiner/McCreight | Thuật toán suffix-array chuyên dụng |
| Định dạng dễ lưu tệp | Cần serialize đồ thị | Mảng thường dễ serialize |
| Bài học cốt lõi | Chia sẻ tiền tố của hậu tố bằng nén cây | Thứ tự từ điển và prefix-interval |

**Không nhầm:** suffix array không phải mảng các chuỗi hậu tố được copy; nó là mảng **vị trí bắt đầu** trong văn bản chung.

## 14. Suffix automaton, suffix trie, BWT/FM-index

### Suffix automaton (SAM)

**Suffix automaton** là một automaton hữu hạn tối thiểu cho **các substring** của một chuỗi. Nó có cấu trúc state, transition, suffix links và thuộc tính `maxLen`; có thể xây trực tuyến trong O(n) dưới giả thiết dữ liệu/transition phù hợp và có O(n) states/transitions. Với một mẫu P, đi theo transition để biết **P có xuất hiện hay không**.

Nhưng SAM **không lưu sẵn mọi vị trí xuất hiện** giống lá suffix tree. Muốn đếm hoặc truy vết các vị trí, cần thêm thông tin `endpos`, propagating counts, hoặc cấu trúc phụ. Một SAM cài không đủ metadata không tự trả `[1,3]` cho pattern ana.

### Suffix trie chưa nén

Chèn tất cả hậu tố vào trie ký tự thông thường rất dễ cài và dễ hình dung, nhưng có thể tốn **O(n²) bộ nhớ** và O(n²) thời gian. Cây hậu tố nén có thể giữ **O(n) node/edge** nhờ ghép các chuỗi một con thành một cạnh gắn interval; đó là khác biệt bản chất.

### BWT và FM-index

**Burrows–Wheeler Transform (BWT)** sắp xếp chuỗi một cách đặc biệt liên quan đến thứ tự suffix; **FM-index** là một chỉ mục nén thường xây quanh BWT, rank/select và mẫu đếm ký tự, cho phép **backward search** theo pattern. Nó có thể hỗ trợ truy vấn substring trong **không gian tiết kiệm hơn** so với một cây nhiều object, đặc biệt quan trọng trong dữ liệu sinh học và cơ sở dữ liệu văn bản lớn.

Nhưng **FM-index không chỉ là “suffix tree đặt trong mảng”**: nó dựa trên các phép đếm/rank trong biểu diễn nén, và việc **locate occurrences** thường cần **sampling** hoặc bước giải mã bổ sung. Khi chọn cấu trúc, phân biệt **count, locate, extract, memory và update**.

### Prefix trie thường để làm gì?

Trie chứa **từ khóa/pattern** hỗ trợ tìm một tiền tố trong từ điển. Suffix tree chứa **mọi hậu tố của một văn bản** để hỗ trợ tìm mọi substring của văn bản ấy. Cùng dùng cây có nhãn ký tự nhưng **đối tượng được index khác nhau**: một bên là tập từ độc lập, bên kia là toàn bộ suffix của một text.

## 15. Các ứng dụng khác của ý tưởng lập chỉ mục suffix

1. **Substring existence:** hỏi P có trong T trong O(m) expected sau build.
2. **Occurrence count:** lưu số lá ở mỗi subtree, trả số lần P xuất hiện sau O(m) tìm cạnh (không cần enumerate).
3. **Occurrence positions:** thu suffixStart của lá dưới đoạn khớp; sắp nếu cần thứ tự văn bản.
4. **Longest repeated substring:** internal node có path depth lớn nhất.
5. **Longest common substring giữa hai chuỗi:** dùng **generalized suffix tree** của hai chuỗi với terminator riêng, đánh dấu mỗi node có lá của cả hai tài liệu, tìm node sâu nhất được cả hai màu.
6. **LCP của hai suffix:** dùng cây và bài toán **LCA** của hai lá suffixStart=i,j; độ sâu ký tự của LCA là LCP. Với tiền xử lý LCA thích hợp, truy vấn LCP có thể rất nhanh sau build.
7. **Tìm substring chung giữa nhiều tài liệu:** gắn mã tài liệu cho mỗi lá; tại node thống kê các document IDs xuất hiện bên dưới.
8. **Nghiên cứu dữ liệu sinh học:** tìm motif/đoạn lặp trong chuỗi DNA/protein; alphabet nhỏ giúp cấu trúc transition thuận tiện nhưng tổng text có thể rất lớn.
9. **Phát hiện đoạn văn bản trùng:** dùng các chỉ mục suffix hoặc fingerprint để tìm các đoạn chung dài, rồi lọc theo ngữ nghĩa/chuẩn hóa.
10. **Compression:** những đoạn lặp dài giúp gợi ý cách tái sử dụng thông tin; nhiều thuật toán nén thực tế dùng cấu trúc liên quan nhưng không nhất thiết dùng suffix tree đầy đủ.

### Generalized suffix tree cần terminal riêng cho từng văn bản

Nếu index hai chuỗi A và B cùng nhau, thường tạo:

**`A ⊥₁ B ⊥₂`**,

trong đó ⊥₁ và ⊥₂ **khác nhau** và không xuất hiện trong cả hai input. Gắn cho mỗi lá thông tin **document ID và offset nội bộ**. Nếu cho các văn bản dùng chung một ký hiệu kết thúc và không quản lý điểm phân cách đúng, một đường trong cây có thể đại diện cho substring **băng qua ranh giới tài liệu**, dẫn tới false positive.

Bản Java hiện tại cố tình chỉ nhận **một text** và một terminator −1. Muốn dùng generalized tree, cần mở rộng mô hình source ID/offset và sentinel để không trả match bắt đầu ở tài liệu này nhưng kết thúc ở tài liệu khác.

## 16. Unicode, chuẩn hóa và đơn vị offset

Trong Java, `String` sử dụng **UTF-16**:

- Một code point BMP thông thường chiếm một `char`.
- Một emoji ngoài BMP như 🙂 chiếm **hai `char`** (surrogate pair).
- Có ký tự trông như một chữ nhưng gồm nhiều code point, ví dụ `e` + combining acute accent hoặc một chuỗi emoji ZWJ.

Cây trong bài **giải mã text thành int[] Unicode scalar values**, rồi tất cả `edge.start/end`, `suffixStart` và kết quả `find` đều đo theo **code point offset**. Lấy T=`"🙂a🙂a"`:

~~~text
Code points:  🙂   a   🙂   a
Indices:       0   1    2   3

UTF-16 units: [hi lo] a [hi lo] a
Indices:       0  1   2  3  4   5
~~~

Mẫu `"🙂a"` xuất hiện tại code-point offsets **[0,2]**, nhưng tại UTF-16 code-unit offsets **[0,3]**. Kết quả code-point offset không được dùng trực tiếp làm tham số `String.substring` vì phương thức ấy nhận **UTF-16 indices**, có thể cắt giữa một surrogate pair.

### Tại sao dùng sentinel −1?

Giá trị của Unicode scalar nằm trong miền 0..0x10FFFF nhưng **loại bỏ surrogate code points**. Giá trị −1 **không hợp lệ như một Unicode code point**, nên không thể va chạm với bất kỳ ký tự text thật, kể cả ký tự '$', '#' hoặc '⊥'. Khi so pattern, chỉ các scalar không âm được đưa vào, nên query không thể match terminator.

### Tại sao strictCodePoints cần thiết?

`String.codePoints()` có thể đẩy surrogate lẻ như một đơn vị không phải Unicode scalar trong một số trường hợp chuỗi lỗi. Chương trình minh họa chủ động kiểm tra cặp high/low và **từ chối** văn bản hoặc mẫu malformed. Điều này giúp bảo vệ hợp đồng “index trên Unicode scalar values” thay vì âm thầm biến dữ liệu hỏng thành một ký tự bất thường.

### NFC, NFD và chữ trông giống nhau

Hai chuỗi có thể nhìn giống mà khác code point:

- `é` (U+00E9) là một scalar.
- `e` (U+0065) + U+0301 là hai scalar.

Bản tree so **chính xác code point**; nó **không tự normalize**. Nếu ứng dụng yêu cầu tương đương Unicode canonical, phải dùng **cùng chính sách normalize** cho cả text lúc xây và pattern lúc query. Quá trình chuẩn hóa có thể thay độ dài code point, nên offset trả về sẽ nằm trong **text đã chuẩn hóa**, không mặc định tương đương offset trong source gốc.

Muốn trả vị trí source gốc, cần xây **bảng ánh xạ offset** hoặc pipeline giữ metadata tương ứng. Tương tự khi chuyển chữ hoa–thường hoặc loại dấu: một số phép biến đổi có thể thay đổi độ dài/kết hợp ký tự.

### Byte offset và grapheme index

Một index UTF-8 byte có thể được xây trực tiếp trên bytes nếu bài yêu cầu so khớp **mẫu byte**; lúc đó bản chất suffix tree không đổi nhưng alphabet là byte, kết quả là byte positions. Một **grapheme cluster** lại có thể gồm nhiều code points, nên code-point offset chưa phải vị trí “ký tự hiển thị” trong editor. Không tự suy bằng phép nhân cố định giữa các hệ offset.

## 17. Lập chỉ mục chuỗi động khác chuỗi tĩnh

Cây minh họa được xây trên **văn bản cố định** T và một terminator ở cuối. Nếu nối thêm ký tự x vào T thành Tx, terminator cần được **dời tới cuối mới**, nghĩa là các suffix của chuỗi mới khác suffix cũ. Không thể chỉ giữ cây đã xây rồi thêm một lá cho x và xem như đã có index mới.

Một hệ thống cập nhật liên tục cần chiến lược rõ:

- **Rebuild theo batch:** gom dữ liệu mới, định kỳ xây lại index; đơn giản nhưng tốn build.
- **Online suffix tree/automaton:** dùng thuật toán hỗ trợ cập nhật từng ký tự, cài đặt phức tạp và phải quản lý trạng thái trung gian.
- **Nhiều segment index:** xây index riêng cho từng segment rồi xử lý truy vấn đi qua ranh giới segment bằng cơ chế bổ sung; nếu chỉ search từng segment sẽ bỏ sót pattern xuyên ranh giới.
- **Streaming matcher khi pattern cố định:** không cần xây index toàn stream; KMP streaming hoặc Aho–Corasick streaming có thể phù hợp hơn.

### Khi nào không nên dùng suffix tree?

- Văn bản nhỏ và chỉ có **một** query: `String.indexOf` hoặc KMP đủ đơn giản.
- Chỉ kiểm nhiều pattern cố định trên **luồng đến liên tục**: Aho–Corasick streaming có thể tốt hơn index T.
- RAM rất hạn chế: suffix array, SA+LCP hoặc FM-index thường đáng cân nhắc.
- Dữ liệu đang thay đổi không ngừng: cây static cần xây lại hoặc online algorithm thực sự.
- Cần **fuzzy matching/edit distance**: suffix tree literal không tự giải bài phép sửa, cần thuật toán bổ sung.
- Cần regex/wildcard: không phải chỉ là đi theo một nhãn duy nhất trên tree.
- Cần substring theo **từ/ngữ nghĩa** chứ không phải code point literal: phải định nghĩa tokenizer/normalization/semantics ngoài cấu trúc index.

## 18. Kiểm thử độc lập: tìm kiếm ngây thơ và brute-force LRS

Một chỉ mục suffix có thể có **số nút hợp lý** nhưng vẫn sai ở một nhãn cạnh, một lá suffixStart hay chỗ split. Để tin kết quả, cần so với **oracle không dùng cây** trên text nhỏ.

### Oracle truy vấn substring

Cho văn bản code point `T[0..n−1]` và mẫu `P[0..m−1]`:

1. Nếu m=0, trả mọi vị trí `0..n` theo cùng hợp đồng.
2. Với từng i từ 0 tới n−m, so `T[i+j]` với `P[j]` cho mọi j từ 0 tới m−1.
3. Nếu tất cả bằng, thêm i.
4. Đối chiếu danh sách với kết quả `find(P)` từ cây.

Oracle này có chi phí **O(nm)**, nhưng không dùng nén cạnh hoặc pi, nên **độc lập** với lỗi thao tác cây.

### Oracle LRS bằng so từng cặp suffix

Với mỗi cặp vị trí i<j:

1. Đếm k lớn nhất sao cho `T[i..i+k−1]=T[j..j+k−1]`.
2. Ghi nhận độ dài k lớn nhất toàn bộ cặp.
3. Mọi prefix chung dài tối đa là một ứng viên LRS; kiểm giá trị trả về từ cây có độ dài đúng bằng k, xuất hiện ít nhất hai lần, và không gồm terminator.

Phương pháp này cố ý chậm, dùng cho n nhỏ; nó không dùng internal node, suffix links hoặc suffix array.

### Kiểm tra cấu trúc cây

Sau build T⊥:

- Đếm chính xác **n+1 lá**.
- Kiểm mỗi suffixStart i∈[0,n] được ghi đúng một lần.
- Mọi edge có `0≤start<end≤n+1`.
- Ký tự đầu `index[start]` phải bằng **khóa** lưu trong map của parent.
- Mọi nút internal khác root có ít nhất **hai nhánh**.
- Nhãn root→leaf i phải bằng **T'[i..n]**.
- Mỗi edge chỉ được lưu bằng **một interval**, không tạo chuỗi mới.
- Với n≥1, tổng số nút không vượt `2(n+1)`.
- Kết quả `find` phải có chỉ số tăng dần (vì API đã sort), không trùng, và không vượt n−m đối với m>0.

### Sinh dữ liệu ngẫu nhiên

Với alphabet nhỏ như {a,b,c,🙂,ẫ,中} cùng chữ lặp, sinh text dài 0..21 code point. Sau đó:

1. Xây cây.
2. Sinh pattern có độ dài 0..8; một phần pattern chọn từ substring thật để chắc chắn có match.
3. So `find` với oracle naive.
4. So độ dài LRS với brute force trên mọi cặp suffix.
5. Thử text rỗng, một ký tự, toàn ký tự giống nhau, mọi ký tự khác nhau và văn bản có emoji.
6. Thử sample banana, mississippi, aaaaa, ababa và mẫu dài hơn text.
7. Đảo thứ tự các truy vấn: index là immutable sau build, nên đáp án không đổi.
8. Với Unicode, so **code point positions**, không dùng UTF-16 String.indexOf làm oracle offset trực tiếp.

Nếu làm property-based tests đủ rộng, lỗi split ở cạnh giữa, sai end exclusive, bỏ terminator hoặc mất lá của suffix ngắn sẽ lộ rất nhanh.

### Một số ca quan trọng phải đúng

| Text | Pattern | Kỳ vọng |
|---|---|---|
| `banana` | `ana` | [1,3] |
| `banana` | `na` | [2,4] |
| `banana` | `""` | [0,1,2,3,4,5,6] |
| `mississippi` | `issi` | [1,4] |
| `aaaaa` | `aa` | [0,1,2,3] |
| `aaaaa` | `aaaa` | [0,1] |
| `🙂a🙂a` | `🙂a` | [0,2] |
| `abcdef` | `xyz` | [] |
| `""` | `""` | [0] |
| `""` | `a` | [] |

## 19. Các lỗi thường gặp

1. **Nhầm suffix tree với trie các từ độc lập:** suffix tree lập chỉ mục các hậu tố của **một văn bản**.
2. **Nhầm substring và subsequence:** suffix tree literal giải chuỗi con **liên tiếp**, không giải dãy con bỏ qua ký tự.
3. **Bỏ terminator:** suffix này có thể là tiền tố suffix khác, khiến lá và vị trí kết thúc khó xử lý hoặc mất.
4. **Chọn '$' làm terminator dù text có '$':** không còn duy nhất, phá chứng minh cấu trúc.
5. **Lưu cả chuỗi suffix trên mỗi cạnh:** copy nhiều dữ liệu, mất lợi ích `O(n)` space của path compression.
6. **Nhầm cạnh [start,end) với [start,end]:** độ dài sai, đọc thừa hoặc thiếu ký tự.
7. **Khi split chỉ sửa cạnh mới mà bỏ nhánh cũ:** mất các suffix đã index trước đó.
8. **Không tạo internal node giữa edge khi cần:** hai suffix có tiền tố chung không được biểu diễn đúng.
9. **Hai cạnh cùng nút bắt đầu bằng cùng code point:** truy vấn không còn một đường tra cứu duy nhất.
10. **Quên tạo lá terminator-only tại n:** sai số suffix và quy ước mẫu rỗng.
11. **Lưu suffixStart ở internal node theo một suffix cụ thể:** có thể nhầm node phân nhánh với lá.
12. **Buộc mẫu phải kết thúc ở node:** bỏ sót pattern kết thúc **giữa edge**.
13. **Thu lá toàn cây thay vì đúng cây con sau khi khớp P:** trả false positives.
14. **Trả k occurrences trong O(m) mà không tính chi phí output:** không thực tế với k=Θ(n).
15. **Sort vị trí nhưng không tính O(k log k):** phân tích phức tạp thiếu.
16. **Nhầm số nút O(n) với thời gian build O(n):** naive insertion vẫn O(n²).
17. **Gọi bản naive là Ukkonen:** thiếu active point/suffix links và cận tuyến tính.
18. **Cho rằng suffix tree tìm substring khác nhau với hậu tố vì phải khớp tới lá:** mẫu chỉ cần là prefix **của một suffix**.
19. **Không cho phép occurrences overlap:** sai khi tìm `aa` trong `aaaaa`.
20. **LRS chọn lá sâu nhất:** đó có thể chỉ là toàn bộ văn bản xuất hiện một lần.
21. **LRS gồm terminator:** không thuộc substring hợp lệ của T.
22. **LRS tối ưu không nhất thiết duy nhất:** code có thể trả một trong nhiều đáp án.
23. **Không định nghĩa mẫu rỗng:** mỗi thư viện có thể có chính sách khác nhau.
24. **Không phân biệt code point với UTF-16 char:** sai offset từ emoji.
25. **Dùng UTF-16 substring(index) với code-point offset:** có thể cắt giữa surrogate pair.
26. **Cho text có surrogate lẻ mà không định nghĩa xử lý:** mẫu và index có thể không còn cùng alphabet.
27. **Normalize text nhưng không normalize pattern:** kết quả không nhất quán.
28. **Normalize xong nhưng báo vị trí nguồn gốc trực tiếp:** offset đã thay đổi.
29. **Gộp nhiều tài liệu mà dùng terminator không phân biệt:** có thể tạo match băng qua boundary.
30. **Thêm ký tự mới vào text nhưng không cập nhật cây đúng:** index static đã hết hiệu lực.
31. **Áp suffix tree literal cho regex/fuzzy mà không mở rộng giải thuật:** đáp án không theo yêu cầu.
32. **Bỏ dấu hiệu suffixStart riêng ở lá khi có nhiều suffix trùng prefix:** không tìm được mọi vị trí.
33. **Dùng HashMap mà bỏ qua overhead RAM:** có thể hết heap trước khi n lý thuyết quá lớn.
34. **Chỉ kiểm có match chứ không kiểm vị trí:** split sai có thể chỉ bộc lộ khi liệt kê.
35. **Không test text toàn 'a':** đây là trường hợp suffix chia sẻ rất dài và dễ lộ bug terminator.
36. **Không test pattern trống/longer-than-text:** biên thường lỗi index.
37. **So Unicode với oracle String.indexOf mà quên hệ đơn vị khác:** đánh dấu false failure hoặc bỏ bug thật.
38. **Không kiểm nhãn root→leaf chính là suffix được gắn:** số node đúng nhưng cấu trúc sai vẫn có thể xảy ra.
39. **Tưởng suffix array là copy mọi chuỗi hậu tố:** thực ra nó là mảng chỉ số.
40. **Tưởng suffix automaton tự có mọi occurrence positions:** cần metadata/truy vết bổ sung.

## 20. Bài tập thực hành

**Bài 1 — Vẽ suffix tree.** Cho T=`"aba"`, thêm terminator ⊥ rồi chèn các suffix `aba⊥,ba⊥,a⊥,⊥`. Vẽ cây nén với nhãn cạnh interval và gắn suffixStart cho từng lá. Kiểm số lá là n+1=4.

**Bài 2 — Đếm occurrences không enumerate.** Sau build, duyệt hậu tự và lưu `leafCount[node]`. Viết `count(P)` để khi pattern kết thúc giữa edge, trả số lá của edge.child mà không tạo List vị trí. Với P rỗng, theo quy ước của bài trả n+1.

**Bài 3 — Kiểm tra một hậu tố.** Viết `isSuffix(P)` (P có đúng ở cuối T hay không) và `isSubstring(P)`. Giải thích vì sao một substring tồn tại không nhất thiết là một suffix; cây phải kiểm kết thúc ở lá đúng vị trí n−m để trả isSuffix.

**Bài 4 — LRS không overlap.** Yêu cầu hai occurrences của một substring **không giao nhau**. Chỉ chọn internal node sâu nhất chưa đủ: với mỗi node, cần xét suffixStart nhỏ nhất/lớn nhất bên dưới và điều kiện chênh lệch vị trí ≥ độ dài substring. Hãy thiết kế tìm kiếm có chứng minh, so với brute-force.

**Bài 5 — Suffix array banana.** Lập SA và LCP cho `banana⊥`, kiểm SA=[6,5,3,1,0,4,2] và LCP=[0,0,1,3,0,0,2]. Tìm `ana` bằng khoảng suffix có prefix ấy.

**Bài 6 — Hai tài liệu.** Cho A=`"abracadabra"` và B=`"cadab"`. Xây generalized suffix tree với hai terminal riêng, gắn màu tài liệu ở lá và tìm longest common substring. Kiểm không lấy substring đi xuyên điểm nối A/B.

**Bài 7 — Unicode offsets.** Với `T="🙂a🙂a"`, giải thích vì sao code-point starts của `"🙂a"` là [0,2] nhưng UTF-16 code-unit starts là [0,3]. Viết hàm đổi code-point position sang UTF-16 char index bằng `offsetByCodePoints` khi thật sự cần trả substring Java.

**Bài 8 — Ukkonen.** Nghiên cứu active point, remainder, suffix link và open-ended edges. So build time/memory của bản naive với bản chuyên dụng trên các chuỗi dài `aaaa...` và chuỗi ngẫu nhiên; kiểm hai bản trả cùng occurrences.

**Bài 9 — KMP hay suffix tree?** Một luồng dữ liệu rất lớn và chỉ có một pattern cố định cần phát match ngay khi đến. Đề xuất dùng KMP streaming với state O(m) và chứng minh vì sao không bắt buộc giữ toàn bộ data để xây suffix tree.

**Bài 10 — Case folding.** Xây một chỉ mục không phân biệt hoa–thường cho dữ liệu đa ngôn ngữ. Phân tích cách biến đổi Unicode, tác động đến độ dài text, và cách trả offset về bản gốc mà không lẫn code point/code unit.

## 21. Checklist trước khi sử dụng

- Bài hỏi **substring liên tiếp**, một văn bản hay nhiều văn bản?
- Có cần **nhiều pattern queries** để chi phí xây index xứng đáng?
- Đã chọn rõ hệ đơn vị ký tự: UTF-8 bytes, UTF-16 units hay Unicode code points?
- Text và pattern có cùng chính sách chuẩn hóa/case folding không?
- Terminator có thật sự **không thể trùng** ký tự hợp lệ?
- Có index đủ **n+1 hậu tố**, gồm terminator-only suffix?
- Các nhãn cạnh dùng **[start,end)** trong một mảng text chung, không copy chuỗi dài?
- Mỗi internal node có từ hai nhánh khác nhau và mỗi nhánh bắt đầu bằng code point riêng?
- Khi split edge, đường tới lá cũ có giữ nguyên text suffix?
- Mỗi lá có suffixStart riêng và đường root→lá bằng suffix thực?
- Search cho phép pattern kết thúc **giữa cạnh**, không chỉ ở node?
- Khi tìm occurrences, có duyệt **đúng subtree** và không tính terminator-only leaf cho P không rỗng?
- Có ghi rõ chính sách **mẫu rỗng** và **match overlap**?
- Đã tính `O(k)` chi phí trả k kết quả và `O(k log k)` nếu sort?
- Đã phân biệt **O(n) storage** với **O(n²) naive build**?
- Nếu cần build nhanh, có cân nhắc Ukkonen hoặc suffix array?
- Với LRS, có chọn **internal node sâu nhất**, không chọn lá?
- Có lưu ý LRS có thể không duy nhất, và cho phép overlap hay không?
- Với generalized tree, có terminal riêng/document ID/offset nội bộ?
- Nếu text thay đổi, có kế hoạch rebuild hoặc online index đúng?
- Đã kiểm oracle naive cho query và brute-force LRS trên text ngẫu nhiên?
- Đã thử banana, mississippi, toàn ký tự lặp, mọi ký tự khác, text rỗng, emoji?
- Đã đo RAM thực tế của HashMap/Node khi n lớn?

**Kết luận:** cây hậu tố thực hiện một ý tưởng lập chỉ mục mạnh: **mọi substring của text là một tiền tố của một suffix**, nên ta index mọi suffix trong một **cây trie nén đường**. Thêm terminator duy nhất tạo lá riêng cho mỗi hậu tố; lưu nhãn cạnh bằng interval trên mảng text chung giữ **O(n) số nút/cạnh**. Truy vấn đi theo nhãn cạnh và gom các lá dưới đoạn khớp, trả đúng những vị trí xuất hiện kể cả overlap; internal node sâu nhất cho một chuỗi con lặp dài nhất. Phải tách biệt **cấu trúc O(n) bộ nhớ** và **thuật toán xây**: bản chèn từng suffix O(n²), trong khi Ukkonen có thể tuyến tính với các giả thiết phù hợp. Khi làm hệ thống thật, lựa chọn giữa suffix tree, suffix array/LCP, suffix automaton và FM-index phụ thuộc vào loại truy vấn, số lần truy vấn, RAM, khả năng cập nhật, và việc xử lý nhất quán Unicode/offset.