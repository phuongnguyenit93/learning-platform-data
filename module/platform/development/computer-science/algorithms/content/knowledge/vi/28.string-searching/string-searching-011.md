# Tìm mẫu trên dữ liệu nhận từng phần

**Tìm mẫu trên dữ liệu nhận từng phần** (*streaming / incremental pattern matching*) là bài toán xác định những vị trí xuất hiện của một mẫu `P` trong một luồng dữ liệu `T` khi **không có toàn bộ T trong bộ nhớ ngay từ đầu**. Dữ liệu có thể đến qua nhiều lượt đọc tệp, các gói mạng, một luồng log, tin nhắn WebSocket hoặc các khối ký tự do `Reader.read` trả về. Mỗi lượt chỉ cung cấp một **chunk** (mảnh) mới, có thể rất ngắn, rỗng hoặc bị cắt giữa hai ký tự tưởng như liền nhau.

Thử tìm `P="aba"` trong các mảnh:

~~~text
Chunk 1: "ab"
Chunk 2: "a"
Chunk 3: "ba"

Ghép logic: "ababa"
Vị trí mẫu (0-based): 0 và 2
~~~

Mẫu thứ nhất bắt đầu từ chunk 1 nhưng chỉ **hoàn thành khi nhận chunk 2**; mẫu thứ hai **chồng lấn** với mẫu thứ nhất và hoàn thành ở chunk 3. Nếu chỉ gọi `chunk.indexOf("aba")` trên từng chunk, ta **không tìm được cả hai lần xuất hiện**. Cách nối mọi chunk thành một chuỗi lớn rồi tìm kiếm thì đúng về mặt dữ liệu nhỏ nhưng có thể không khả thi khi luồng dài hàng gigabyte hoặc không kết thúc.

Kỹ thuật trọng tâm của bài là **KMP chạy tăng dần**: tiền xử lý mẫu bằng **hàm tiền tố** `pi`, giữ lại **độ dài tiền tố mẫu hiện đang khớp** `matched` sau mỗi chunk, và tiếp tục ngay ở trạng thái ấy khi chunk kế tiếp đến. Ta không cần lưu lại toàn bộ văn bản đã nhận. Để xử lý tiếng Việt và emoji đúng ngữ nghĩa, bài còn trình bày rành mạch cách đếm **Unicode code point** thay vì nhầm với **UTF-16 code unit**, cách giữ một nửa cặp surrogate ở ranh giới chunk, và sự khác nhau giữa offset ký tự, offset byte và ký tự hiển thị.

Bài thuộc nhóm **Tìm kiếm chuỗi** trong **Computer Science Algorithms**, tập trung vào chủ đề **Tìm mẫu trên dữ liệu nhận từng phần**. Nội dung bao gồm mô hình phát luồng, bất biến và chứng minh KMP, ví dụ chồng lấn/qua ranh giới, Java 17+ tự chạy, xử lý lỗi và kết thúc luồng, độ phức tạp, kiểm thử bằng thuật toán vét cạn độc lập, so sánh với rolling hash và Aho–Corasick, cùng các lưu ý triển khai trong đọc tệp/mạng.

**Mục tiêu học tập:** định nghĩa được vị trí match khi mẫu vắt qua nhiều chunk; chứng minh vì sao chỉ cần lưu trạng thái KMP; không bỏ sót match chồng lấn; viết vòng lặp feed/finish đúng; hiểu các offset Unicode; phân biệt lỗi giải mã, chuẩn hóa và thay đổi thứ tự chunk; chọn được giải pháp phù hợp cho một hoặc nhiều mẫu.

## 1. Mô hình chính xác của bài toán streaming

Cho **mẫu cố định** `P` độ dài `m>0` và luồng văn bản được giao lần lượt:

**`C₀,C₁,...,Cₖ`**.

Chuỗi logic cuối cùng là:

**`T=C₀ ⧺ C₁ ⧺ ... ⧺ Cₖ`**,

trong đó `⧺` là phép nối **theo đúng thứ tự**, không tự thêm newline, dấu cách hoặc ký tự phân cách.

Ta cần thông báo **mọi chỉ số bắt đầu i** thỏa:

**`T[i..i+m−1]=P`**,

với `0≤i≤|T|−m` trong hệ đơn vị chỉ số đã thống nhất. Một match có thể nằm hoàn toàn trong một chunk, có thể trải qua hai chunk, hoặc thậm chí **trải qua rất nhiều chunk** nếu mẫu dài.

**Không được** suy từ việc một chunk rỗng rằng luồng đã kết thúc. Chunk rỗng chỉ không thêm dữ liệu; sự kiện **kết thúc luồng (EOF/finish)** là một tín hiệu riêng.

### Hợp đồng một mẫu, một luồng

Phiên bản chính của bài:

- Một mẫu **literal** cố định, không wildcard/regex.
- Luồng được giao **theo đúng thứ tự**, không mất, lặp hoặc đảo chunk.
- Xuất **tất cả** lần xuất hiện, bao gồm match **chồng lấn**.
- Chỉ số bắt đầu **0-based**.
- Mẫu rỗng bị **từ chối** theo hợp đồng mã để tránh phải quyết định về vô số ranh giới chunk. Nếu đề muốn mẫu rỗng, phải định nghĩa rõ các match ở `|T|+1` vị trí khe ký tự.
- Code Java bên dưới so mẫu theo **Unicode code point chính xác**. Không tự chuyển chữ hoa/thường, không tự NFC/NFD và không coi các ký tự trông giống nhau là bằng nhau nếu mã code point khác.
- Bản mã **báo lỗi** khi gặp cặp UTF-16 surrogate không hợp lệ. Một high surrogate cuối chunk có thể được giữ tạm để ghép với low surrogate ở chunk kế tiếp; cuối toàn luồng mà vẫn còn high surrogate là lỗi.
- Trả vị trí dưới dạng `long` theo **số Unicode code point đã xử lý**, không phải byte offset hoặc `String.charAt` index.

### Bốn loại offset dễ bị nhầm

| Hệ chỉ số | Một “đơn vị” | Khi nào cần |
|---|---|---|
| **Byte offset** | Một byte trong UTF-8, UTF-16LE, tệp nhị phân... | Tìm vị trí trực tiếp trong file/protocol theo byte |
| **UTF-16 code-unit offset** | Một phần tử `char` của Java `String` | `String.length()`, `charAt`, `indexOf` |
| **Unicode code-point offset** | Một Unicode scalar value (trừ surrogate không hợp lệ) | Duyệt văn bản Unicode theo mã tự |
| **Grapheme-cluster offset** | Một cụm ký tự người đọc nhận ra | Cursor hoặc số “chữ hiển thị” trong giao diện |

Trong Java, một emoji như 🙂 dùng **hai UTF-16 code unit** nhưng **một Unicode code point**. Một chữ hiển thị có thể là **nhiều code point** nếu dùng combining mark, variation selector hoặc chuỗi ZWJ; code-point index vẫn chưa phải “vị trí ký tự hiển thị”.

**Chọn một quy ước và ghi rõ trong API.** Không đổi giữa đơn vị code point và code unit khi báo vị trí match.

## 2. Vì sao xử lý độc lập từng chunk là sai?

Xét mẫu `P="needle"` và các chunk:

~~~text
"xxnee" | "d" | "lezzneedle"
~~~

Chuỗi hoàn chỉnh là:

~~~text
xxneedlezzneedle
  ^       ^
  2       10
~~~

Cả hai match bắt đầu ở chỉ số code point 2 và 10.

Match đầu tiên chỉ có `"nee"` nằm cuối chunk 1, `"d"` ở chunk 2 và `"le"` ở chunk 3. Không có chunk riêng nào chứa toàn bộ `"needle"` lần thứ nhất. Nếu search từng chunk rồi cộng các offset, match ấy sẽ **mất hẳn**.

Một cách trực giác là giữ lại **tối đa m−1 ký tự cuối** chunk trước, nối với chunk mới rồi search. Cách đó có thể đúng khi triển khai cẩn thận, nhưng cần:

- Không thông báo lại các match **đã kết thúc** trong những lượt trước.
- Quy đổi vị trí từ buffer tạm sang **offset toàn luồng**.
- Xử lý mẫu dài hơn chunk và match trải qua nhiều chunk.
- Kiểm soát việc cắt giữa surrogate pairs hoặc giữa các byte UTF-8.
- Nếu dùng thuật toán tìm kiếm ngây thơ trên buffer, có thể làm nhiều phép so sánh thừa.

**KMP streaming** biểu diễn “đuôi liên quan của chuỗi đã đọc” bằng **một số nguyên** `matched` thay vì giữ tất cả m−1 ký tự quá khứ để so lại nhiều lần.

## 3. Nhắc lại KMP và hàm tiền tố

Cho mẫu `P[0..m−1]`. Hàm tiền tố (*prefix function*, còn gọi là failure function) tại vị trí i:

**`pi[i] = độ dài tiền tố đúng dài nhất của P[0..i] cũng là hậu tố của P[0..i]`.**

Một **tiền tố đúng** có độ dài nhỏ hơn cả đoạn đang xét. Vì vậy `pi[0]=0`.

Ví dụ `P="ababaca"`:

| i | P[i] | P[0..i] | pi[i] |
|---:|:---:|---|---:|
| 0 | a | a | 0 |
| 1 | b | ab | 0 |
| 2 | a | aba | 1 |
| 3 | b | abab | 2 |
| 4 | a | ababa | 3 |
| 5 | c | ababac | 0 |
| 6 | a | ababaca | 1 |

Mảng:

**`pi=[0,0,1,2,3,0,1]`**.

Nếu vừa khớp `"ababa"` (5 ký tự) nhưng ký tự tiếp theo không phù hợp, ta không cần quay lại đầu mẫu. Ta đã biết hậu tố `"aba"` (độ dài 3) cũng là tiền tố của mẫu, nên có thể thử tiếp từ trạng thái `matched=3`.

### Xây pi trong O(m)

Với mỗi i từ 1 tới m−1, đặt `j=pi[i−1]`. Nếu `P[i]≠P[j]`, lùi `j=pi[j−1]` cho đến khi bằng hoặc j=0. Nếu bằng, tăng j. Sau đó gán `pi[i]=j`.

~~~text
pi[0] = 0

for i = 1 .. m-1:
    j = pi[i-1]
    while j > 0 and P[i] != P[j]:
        j = pi[j-1]
    if P[i] == P[j]:
        j++
    pi[i] = j
~~~

Mỗi bước tiến của j được bù bằng những lần lùi theo pi; tổng phép so sánh là tuyến tính theo m trong phân tích KMP chuẩn. Vì vậy tiền xử lý **O(m)** thời gian và **O(m)** bộ nhớ.

**Lưu ý:** `pi` được xây một lần cho mẫu cố định. Khi chunk mới tới, **không tính lại pi**. Điều thay đổi trong lúc nhận stream chỉ là trạng thái khớp `matched` và vị trí toàn luồng.

## 4. Trạng thái KMP phải sống qua ranh giới chunk

Bộ tìm kiếm duy trì:

- `pattern[0..m−1]`: mẫu dưới dạng m code point.
- `pi[0..m−1]`: hàm tiền tố.
- `matched=j`: số code point đầu của mẫu hiện trùng với **hậu tố liên quan** của phần dữ liệu đã đọc, `0≤j<m` sau mỗi lần hoàn tất một match.
- `processed`: tổng số code point đã nhận xử lý hoàn chỉnh, tính từ đầu stream.
- `pendingHigh`: tối đa một UTF-16 high surrogate còn đợi low surrogate ở chunk sau.
- `finished`: cờ EOF, không cho nhận thêm dữ liệu sau khi đã kết thúc.

Khi một code point x mới tới:

~~~text
while matched > 0 and pattern[matched] != x:
    matched = pi[matched - 1]

if pattern[matched] == x:
    matched++

processed++

if matched == m:
    emit(processed - m)   // 0-based start position
    matched = pi[m - 1]   // preserve overlaps
~~~

**Không reset `matched=0` khi chuyển chunk**. Đây là sai lầm phổ biến nhất của phiên bản streaming.

### Ý nghĩa của `processed−m`

`processed` là **số code point đã hoàn tất xử lý** sau khi đọc x (không phải chỉ số của x). Nếu vừa kết thúc match độ dài m, nó chiếm các vị trí:

**`processed−m, ..., processed−1`**,

nên vị trí bắt đầu chính là **`processed−m`**.

Ví dụ mẫu `"aba"` trong `"ababa"`:

- Sau code point thứ ba: `processed=3` ⇒ match tại **0**.
- Sau code point thứ năm: `processed=5` ⇒ match tại **2**.

Nếu mỗi chunk chỉ dài một ký tự, công thức vẫn y hệt.

### Vì sao sau match phải gán `matched=pi[m−1]`?

Với `P="aba"`, có `pi[2]=1`. Khi vừa khớp `"aba"`, hậu tố `"a"` đồng thời là tiền tố `"a"` của P, nên một match mới **có thể bắt đầu tại ký tự a cuối cùng của match cũ**.

Trong `"ababa"`:

~~~text
T:       a b a b a
Match 1: a b a
Match 2:     a b a
Start:   0   2
~~~

Nếu sau match đặt j=0, ta bỏ qua khả năng chồng lấn và chỉ báo một vị trí. Nếu giữ j=m mà truy cập `pattern[j]` ở ký tự sau, sẽ truy cập ngoài mảng. **`j=pi[m−1]`** vừa giữ đúng hậu tố có ích vừa bảo đảm j<m.

## 5. Minh họa trạng thái được giữ qua nhiều chunk

### Trường hợp không có mẫu hoàn chỉnh trong chunk nào

Mẫu `"needle"`, chunk đầu `"xxnee"`:

- Hai ký tự x không khớp, j vẫn 0.
- Đọc n,e,e ⇒ j=3; chưa phát match.
- Hết chunk, **giữ j=3**.

Chunk thứ hai chỉ có `"d"`:

- Dùng j=3, pattern[3]='d' khớp ⇒ j=4.
- Hết chunk, **giữ j=4**.

Chunk thứ ba bắt đầu `"le"`:

- Đọc l ⇒ j=5.
- Đọc e ⇒ j=6=m, phát match ở **offset 2**.
- Gán j=pi[5] (0 với mẫu needle) rồi tiếp tục xử lý `"zzneedle"`.
- Đến cuối chunk thứ ba phát match thứ hai ở **offset 10**.

Không cần lưu lại `"xxnee"` hoặc `"d"` sau khi đã xử lý. Ta chỉ lưu j=3, rồi j=4, cùng tổng số code point đã nhận.

### Trường hợp match liên tục và chồng lấn

Mẫu `"aaa"`, stream `"aaaaa"`, các chunk `"a"|""|"aa"|"aa"`:

- Sau ba ký tự a đầu: match ở 0.
- Sau ký tự a thứ tư: match ở 1.
- Sau ký tự a thứ năm: match ở 2.

Kết quả **[0,1,2]**, không phải [0] hay [0,3]. Chunk rỗng `""` không thay đổi state và không tạo match mới.

### Trường hợp mẫu dài hơn từng chunk

Một mẫu dài 1000 code point vẫn có thể xuất hiện trong 1000 chunk mỗi chunk chứa một code point. KMP giữ j tăng dần qua từng chunk; không cần chunk nào có độ dài ≥m.

**Quan trọng:** trạng thái tìm kiếm không phải số ký tự đã nằm trong chunk cuối. Nó phụ thuộc **toàn bộ stream đã xử lý**, nhưng được nén thành một biến j nhờ cấu trúc tiền tố của mẫu.

## 6. Chứng minh tính đúng của KMP streaming

### Bất biến trạng thái

Sau khi đọc một tiền tố T[0..q−1] của stream, nếu một match hoàn chỉnh vừa được báo thì thuật toán đặt j về tiền tố đúng theo pi. Ngoài thời điểm phát match, j mô tả **độ dài hậu tố dài nhất của dữ liệu đã đọc là một tiền tố của P** mà còn có ích cho những match sẽ kết thúc sau này.

Bất biến thực thi quan trọng là:

**Các match đã kết thúc được phát đúng một lần; j lưu toàn bộ thông tin cần thiết về phần văn bản đã đọc để quyết định match với các code point kế tiếp.**

### Không bỏ sót

Giả sử một lần xuất hiện của P kết thúc ở code point x hiện tại. Trước x, phần đã đọc phải có một hậu tố trùng với `P[0..m−2]` (trừ m=1). Khi xử lý x, KMP thử trạng thái j đang giữ; nếu không khớp, nó **lùi theo chuỗi pi** qua mọi độ dài hậu tố có thể còn là tiền tố của P. Nó không bỏ qua một hậu tố ứng viên nào dài hơn hoặc bằng hậu tố cần thiết. Vì vậy nếu một match P có thể hoàn tất ở x, sẽ có thời điểm j đạt m và thuật toán phát kết quả.

Việc ranh giới chunk nằm ở đâu **không** thay đổi dãy code point mà thuật toán nhận, cũng không thay đổi j ở giữa các code point. Do đó một match nằm xuyên chunk không khác một match nằm trọn trong chunk theo cách nhìn của KMP.

### Không báo match giả

Một kết quả chỉ được phát khi j vừa tăng đến m. Do invariant của KMP, m code point gần nhất của stream trùng **từng code point** với P. Vì vậy `processed−m` thật sự là vị trí bắt đầu một lần xuất hiện. Trường hợp chồng lấn chỉ làm các khoảng xuất hiện giao nhau, không biến một khoảng sai thành đúng.

### Không trùng thông báo

Một lần xuất hiện được xác định bởi **vị trí kết thúc**. Với mỗi code point mới, thuật toán xét đúng một lần và chỉ có thể phát kết quả kết thúc tại vị trí ấy tối đa một lần cho một mẫu cố định. Sau đó nó chuyển về pi[m−1], nên match cũ không thể được phát lại chỉ vì có chunk mới.

### Độ phức tạp

Đặt N là số code point của toàn luồng, m là số code point của mẫu.

- Xây pi: **O(m)** thời gian.
- Xử lý N code point qua tất cả chunk: **O(N)** thời gian phân tích gộp của KMP.
- Tổng: **`O(N+m)`** ngoài chi phí phát/sử dụng các kết quả.
- Trạng thái matcher: **`O(m)`** cho pattern/pi, cộng O(1) cho j, processed và một surrogate đang chờ.
- Nếu API trả danh sách hits theo chunk, bộ nhớ tạm còn **O(số match phát trong chunk đó)**; caller cần giải phóng/tiêu thụ kết quả, không gom vô hạn nếu stream dài.

Độ phức tạp **không nhân số chunk với m** vì ta không tính lại pi hay tìm lại trên phần văn bản trước đó.

## 7. Unicode: điều gì xảy ra khi chunk chia đôi emoji?

Java `String` dùng **UTF-16**, nên một Unicode code point ngoài Basic Multilingual Plane có thể được biểu diễn bằng **hai `char`**: high surrogate và low surrogate.

Ví dụ emoji 🙂 có Unicode code point **U+1F642**. Trong Java, nó có:

- `"🙂".length()==2` (hai code unit).
- `"🙂".codePointCount(0,2)==1` (một code point).

Một `Reader.read(char[])` hoặc việc cắt `String.substring` theo chỉ số UTF-16 có thể chia cặp ấy thành **hai chunk**. Ví dụ stream logic:

~~~text
x🙂a🙂a

Chunk 1: "x" + high-surrogate(🙂)
Chunk 2: low-surrogate(🙂)
Chunk 3: "a"
Chunk 4: "🙂"
Chunk 5: "a"
~~~

Tìm mẫu `"🙂a"`:

- Offset bắt đầu theo **code point** là **[1,3]**.
- Offset bắt đầu theo **UTF-16 code unit** là **[1,4]**.
- Nếu stream được mã hóa UTF-8, byte offsets lại khác nữa (emoji thường chiếm bốn byte).

**Không được gọi `String.codePoints()` độc lập trên mỗi chunk rồi tưởng luôn an toàn**, vì một chunk có thể kết thúc bằng high surrogate, chunk sau bắt đầu bằng low surrogate. Cần **giữ high surrogate đang dở** rồi ghép đúng cặp trước khi đưa code point vào KMP.

### Quy tắc giải mã UTF-16 của code bên dưới

1. Nếu không có high surrogate đang chờ:
   - Gặp ký tự BMP thông thường: phát ngay một code point.
   - Gặp high surrogate và còn low surrogate ngay trong chunk: ghép thành một code point.
   - Gặp high surrogate ở cuối chunk: lưu vào `pendingHigh`, **chưa tăng processed**.
   - Gặp low surrogate không có high tương ứng: báo lỗi.
2. Nếu đang giữ high surrogate:
   - Chunk rỗng: tiếp tục chờ.
   - Ký tự đầu chunk kế là low surrogate: ghép, phát một code point, xóa pending.
   - Ký tự đầu không phải low surrogate: báo lỗi đầu vào.
3. Khi `finish()`:
   - Không còn pending: kết thúc hợp lệ.
   - Vẫn còn high surrogate: báo lỗi vì toàn luồng có Unicode không hợp lệ.

Khi có dữ liệu không hợp lệ, caller nên **bỏ hoặc tái khởi tạo matcher**; không giả định nó có thể tiếp tục xử lý chính xác từ giữa một chunk đã làm phương thức ném lỗi.

### Code point không đồng nghĩa chữ người đọc thấy

Ví dụ cùng chữ “é” có thể ở hai dạng:

- Dạng ghép sẵn: code point U+00E9.
- Dạng tách: `e` (U+0065) và dấu kết hợp `◌́` (U+0301).

Hai chuỗi có thể trông giống nhau nhưng **khác dãy code point**. Bản KMP literal trả “không khớp” nếu pattern là dạng ghép sẵn còn stream là dạng tách, trừ khi ta áp dụng **Unicode normalization** nhất quán.

**Không chuẩn hóa từng chunk độc lập** khi dấu kết hợp hoặc chuỗi cần ghép có thể cắt qua ranh giới. Nếu cần so khớp chuẩn hóa NFC/NFD trên dữ liệu streaming, phải thiết kế **bộ normalizer tăng dần giữ đủ ngữ cảnh ranh giới**, hoặc làm việc trên dữ liệu đã được nguồn bảo đảm chuẩn hóa từ trước. Nếu cần **không phân biệt hoa thường**, phải thêm bước Unicode case folding đúng ngữ nghĩa; `String.toLowerCase` tùy ngôn ngữ/locale và các biến đổi có thể đổi độ dài, nên offset phải được quản lý lại.

## 8. Khi luồng đầu vào là byte UTF-8, không phải String

Một `InputStream` trả **byte chunks**, có thể cắt ở giữa **một ký tự UTF-8 nhiều byte**. Nếu áp dụng KMP trên bytes, đó là bài **tìm chuỗi byte**, kết quả là **byte offsets**. Điều ấy hoàn toàn hợp lệ với bài tìm signature nhị phân hoặc giao thức xác định theo bytes, nhưng không đồng nghĩa tìm Unicode code point có chuẩn hóa.

Nếu muốn tìm **văn bản Unicode**:

1. Dùng một **bộ giải mã UTF-8 giữ trạng thái** giữa các lần đọc byte (ví dụ `InputStreamReader`/`CharsetDecoder`).
2. Nhận các `char` UTF-16 được bộ giải mã xuất ra.
3. Chuyển `char` thành code point có xử lý surrogate split như mục 7.
4. Đưa từng code point vào KMP, giữ j giữa mọi lượt feed.
5. Cuối luồng, hoàn tất decoder và gọi `finish()` của matcher.

Với dữ liệu không hợp lệ cần báo lỗi thay vì âm thầm thay ký tự, có thể dùng:

~~~java
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.Reader;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

// "source" là một InputStream đã mở; đây là đoạn minh họa
// để ghép vào chương trình có sẵn, không phải main độc lập.
var decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

try (Reader reader = new InputStreamReader(source, decoder)) {
    char[] buffer = new char[4096];
    int count;
    while ((count = reader.read(buffer)) != -1) {
        // Feed exactly [0,count) chars to the streaming matcher.
        // matcher.feed(new String(buffer, 0, count));
    }
}
// matcher.finish();
~~~

**Đoạn trên chỉ minh họa khâu giải mã** và cần biến `source`, `matcher` từ ứng dụng thật; mã Java chạy độc lập nằm ở mục 10. Nó không tự tạo kết quả vì chưa gắn nguồn dữ liệu thực.

### Byte offset và code-point offset không thể đổi bằng một phép nhân

UTF-8 dùng số byte thay đổi tùy code point. Muốn in **byte offset** cho từng match trong khi so theo code point, cần theo dõi thông tin vị trí byte của từng code point qua decoder, hoặc lưu một **vòng đệm metadata** đủ cho độ dài mẫu. Không thể nói “vị trí code point i tương ứng byte thứ i×2” hay dùng công thức chung cố định.

Tương tự, vị trí code point không luôn bằng `String.indexOf` offset của Java do ký tự supplementary chiếm hai UTF-16 code units.

## 9. Thiết kế API streaming: feed, finish và nhận kết quả

Một API rõ ràng có ba nhiệm vụ:

**Khởi tạo với mẫu cố định:**

- Từ chối mẫu rỗng nếu hợp đồng không hỗ trợ.
- Chuyển mẫu thành dãy code point hợp lệ.
- Xây pi một lần.
- Đặt j=0, processed=0 và không có surrogate pending.

**`feed(chunk)`:**

- Được gọi nhiều lần, kể cả với `""`.
- Không đặt lại j hay processed.
- Xử lý từng code point hoàn chỉnh của chunk.
- Trả những vị trí match **kết thúc trong lượt feed này**; vị trí bắt đầu có thể thuộc chunk trước.
- Nếu chunk chỉ chứa high surrogate cuối, chưa báo gì cho đến khi ghép thành code point hợp lệ.

**`finish()`:**

- Tín hiệu EOF, không giống feed chunk rỗng.
- Kiểm tra không còn một nửa Unicode đang dở.
- Khóa matcher để feed sau finish không được chấp nhận.
- Không tự phát thêm một match cho mẫu không rỗng vì không có code point mới.

### Trả kết quả hay gọi callback?

Với ví dụ ngắn, `List<Long> feed(String chunk)` dễ đọc và tiện kiểm thử. Nhưng nếu mẫu `"a"` xuất hiện hàng triệu lần, một danh sách giữ **mọi kết quả toàn stream** sẽ làm đầy RAM, dù thuật toán KMP chỉ tốn O(m) trạng thái.

Trong hệ thống thật có thể:

- Tiêu thụ danh sách match và giải phóng ngay sau mỗi feed.
- Thay return list bằng callback `LongConsumer onMatch` để phát từng offset cho downstream.
- Gửi kết quả qua queue có **backpressure**; tạm ngừng đọc nguồn khi bên xử lý đầu ra chậm.
- Đếm số match thay vì lưu tất cả, nếu đề chỉ hỏi số lượng; kiểm tra tràn counter khi cần.

**Lưu ý:** `List<Long>` trong mã ví dụ là bộ đệm **kết quả của một chunk**; nếu caller cộng hết các list vào một list toàn cục để in demo thì RAM đó thuộc **caller**, không thuộc yêu cầu lưu trạng thái KMP.

## 10. Java 17+ hoàn chỉnh: KMP tăng dần theo Unicode code point

Chương trình dưới đây chạy độc lập bằng **Java 17 trở lên**. Nó không dùng regex hay `String.indexOf` để thực hiện tìm kiếm; toàn bộ xử lý match nằm trong bộ máy KMP.

**Đầu vào của mỗi demo** là một pattern và mảng chunks. Bộ tìm kiếm kiểm tra UTF-16 hợp lệ, giữ cặp surrogate khi cần, xuất vị trí 0-based theo số Unicode code point.

Mô hình của mã:

- `pattern` là `int[]` code point đã giải mã từ mẫu.
- `pi` là `int[]` tiền tố KMP.
- `matched` là trạng thái KMP hiện tại.
- `processed` kiểu `long` là tổng code point hoàn chỉnh đã tiêu thụ.
- `pendingHigh` là một `char` high surrogate đang chờ.
- `finished` không cho feed sau EOF.
- Phương thức `feed` trả các match kết thúc trong chunk vừa nhận.
- Phương thức `finish` kiểm UTF-16 đầy đủ; gọi lặp finish là hợp lệ, nhưng không nhận thêm chunk sau đó.

Chương trình không tự chuẩn hóa Unicode hoặc case-fold; mẫu và stream phải là những code point muốn so sánh **nguyên văn**.

Lưu thành **`StreamingKmpDemo.java`**:

~~~java
import java.io.IOException;
import java.io.Reader;
import java.io.StringReader;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public final class StreamingKmpDemo {
    private static final class StreamingKmp {
        private final int[] pattern;
        private final int[] pi;

        private int matched;
        private long processed;
        private char pendingHigh; // 0 means none.
        private boolean finished;

        StreamingKmp(String literalPattern) {
            if (literalPattern == null
                    || literalPattern.isEmpty()) {
                throw new IllegalArgumentException(
                        "Pattern must be nonempty");
            }
            pattern = decodePattern(literalPattern);
            pi = buildPrefix(pattern);
        }

        // Unlike codePoints() on arbitrary chunks, this
        // rejects malformed surrogate sequences in the PATTERN.
        private static int[] decodePattern(String text) {
            int[] temp = new int[text.length()];
            int count = 0;

            for (int i = 0; i < text.length();) {
                char ch = text.charAt(i++);
                if (Character.isHighSurrogate(ch)) {
                    if (i >= text.length()
                            || !Character.isLowSurrogate(
                                    text.charAt(i))) {
                        throw new IllegalArgumentException(
                                "Unpaired high surrogate in pattern");
                    }
                    char low = text.charAt(i++);
                    temp[count++] =
                            Character.toCodePoint(ch, low);
                } else if (Character.isLowSurrogate(ch)) {
                    throw new IllegalArgumentException(
                            "Unpaired low surrogate in pattern");
                } else {
                    temp[count++] = ch;
                }
            }
            return Arrays.copyOf(temp, count);
        }

        private static int[] buildPrefix(int[] p) {
            int[] prefix = new int[p.length];

            for (int i = 1; i < p.length; i++) {
                int j = prefix[i - 1];
                while (j > 0 && p[i] != p[j]) {
                    j = prefix[j - 1];
                }
                if (p[i] == p[j]) {
                    j++;
                }
                prefix[i] = j;
            }
            return prefix;
        }

        private void processCodePoint(
                int cp, List<Long> matches) {
            while (matched > 0
                    && pattern[matched] != cp) {
                matched = pi[matched - 1];
            }
            if (pattern[matched] == cp) {
                matched++;
            }

            // Positions are in CODE POINTS, not UTF-16 chars.
            processed = Math.addExact(processed, 1L);

            if (matched == pattern.length) {
                matches.add(processed - pattern.length);
                // Preserve overlaps; never index pattern[m].
                matched = pi[matched - 1];
            }
        }

        List<Long> feed(String chunk) {
            if (finished) {
                throw new IllegalStateException(
                        "Cannot feed after finish");
            }
            if (chunk == null) {
                throw new IllegalArgumentException(
                        "Null chunk is not an empty chunk");
            }

            List<Long> matches = new ArrayList<>();
            int i = 0;

            // Finish an emoji/code point split at the
            // PREVIOUS chunk boundary, if possible.
            if (pendingHigh != 0 && !chunk.isEmpty()) {
                char low = chunk.charAt(0);
                if (!Character.isLowSurrogate(low)) {
                    throw new IllegalArgumentException(
                            "High surrogate not followed by low");
                }
                processCodePoint(
                        Character.toCodePoint(pendingHigh, low),
                        matches);
                pendingHigh = 0;
                i = 1;
            }

            while (i < chunk.length()) {
                char ch = chunk.charAt(i++);

                if (Character.isHighSurrogate(ch)) {
                    if (i == chunk.length()) {
                        pendingHigh = ch;
                        break; // Wait for next feed().
                    }
                    char low = chunk.charAt(i++);
                    if (!Character.isLowSurrogate(low)) {
                        throw new IllegalArgumentException(
                                "Malformed surrogate pair");
                    }
                    processCodePoint(
                            Character.toCodePoint(ch, low),
                            matches);
                } else if (Character.isLowSurrogate(ch)) {
                    throw new IllegalArgumentException(
                            "Unexpected low surrogate");
                } else {
                    processCodePoint(ch, matches);
                }
            }
            return List.copyOf(matches);
        }

        void finish() {
            if (pendingHigh != 0) {
                throw new IllegalArgumentException(
                        "Stream ended after high surrogate");
            }
            finished = true;
        }

        long processedCodePoints() {
            return processed;
        }
    }

    private static void show(
            String label, String pattern, String... chunks) {
        StreamingKmp matcher = new StreamingKmp(pattern);
        List<Long> all = new ArrayList<>();

        for (String chunk : chunks) {
            all.addAll(matcher.feed(chunk));
        }
        matcher.finish();

        System.out.println(
                label + ": matches=" + all
                + ", codePoints="
                + matcher.processedCodePoints());
    }

    private static void showReader() throws IOException {
        StreamingKmp matcher = new StreamingKmp("aba");
        List<Long> all = new ArrayList<>();

        // Only a TWO-char buffer: matches can cross read calls.
        try (Reader reader = new StringReader("xxababa!")) {
            char[] buffer = new char[2];
            int count;

            while ((count = reader.read(buffer)) != -1) {
                all.addAll(matcher.feed(
                        new String(buffer, 0, count)));
            }
        }

        matcher.finish();
        System.out.println(
                "Reader: matches=" + all
                + ", codePoints="
                + matcher.processedCodePoints());
    }

    public static void main(String[] args)
            throws IOException {
        show("Overlapping", "aba", "ab", "a", "ba");
        show("Repeated", "aaa", "a", "", "aa", "aa");
        show("Chunk boundary", "needle",
                "xxnee", "d", "lezzneedle");

        String emoji =
                new String(Character.toChars(0x1F642));
        String high = String.valueOf(emoji.charAt(0));
        String low = String.valueOf(emoji.charAt(1));

        show("Emoji split", emoji + "a",
                "x" + high, low, "a", emoji, "a");

        show("Vietnamese", "mẫu",
                "m", "ẫ", "u", " mẫ", "u");

        show("No match", "xyz", "ab", "abc");
        show("Empty chunks", "a", "", "", "");
        showReader();
    }
}
~~~

Biên dịch và chạy, chỉ rõ mã hóa nguồn để tiếng Việt/emoji trong Java source không bị sai trên môi trường mặc định khác UTF-8:

~~~bash
javac -encoding UTF-8 StreamingKmpDemo.java
java StreamingKmpDemo
~~~

**Stdout chính xác:**

~~~text
Overlapping: matches=[0, 2], codePoints=5
Repeated: matches=[0, 1, 2], codePoints=5
Chunk boundary: matches=[2, 10], codePoints=16
Emoji split: matches=[1, 3], codePoints=5
Vietnamese: matches=[0, 4], codePoints=7
No match: matches=[], codePoints=5
Empty chunks: matches=[], codePoints=0
Reader: matches=[2, 4], codePoints=8
~~~

### Giải thích 8 trường hợp

**Overlapping:** các chunk tạo `"ababa"`. Mẫu `"aba"` xuất hiện ở 0 và 2. Sau match đầu, j quay về `pi[2]=1`, bảo toàn phần hậu tố `"a"` làm đầu match kế.

**Repeated:** `"aaa"` trong năm chữ a liên tục có ba lần xuất hiện chồng lấn tại 0,1,2. Chunk rỗng không làm thay đổi gì.

**Chunk boundary:** match `"needle"` đầu tiên vắt qua cả ba chunk và kết thúc ở hai ký tự `"le"` đầu chunk cuối. Match thứ hai nằm ở cuối chunk thứ ba. Vị trí toàn stream là 2 và 10.

**Emoji split:** mẫu gồm hai code point `🙂` và `a`. Lượt feed đầu chứa ký tự x và **chỉ high surrogate** của emoji, lượt feed sau chứa low surrogate. Matcher chỉ tăng `processed` cho emoji khi ghép đủ; match bắt đầu ở code-point offsets [1,3], không phải UTF-16 offsets [1,4].

**Vietnamese:** chuỗi logic là `"mẫu mẫu"`, dài bảy code point. Mẫu `"mẫu"` có ba code point và xuất hiện ở 0,4. Các chunk có thể cắt giữa các chữ cái bất kỳ mà kết quả không đổi.

**No match:** văn bản `"ababc"` không chứa `"xyz"`. Hàm không phát bất kỳ vị trí nào.

**Empty chunks:** không có code point thực sự được nhận, matcher kết thúc sạch và không phát match của mẫu không rỗng.

**Reader:** `StringReader` trả tối đa hai UTF-16 code unit mỗi lần. Chương trình không cần biết ranh giới chunk trước khi tìm; `"aba"` xuất hiện tại 2 và 4 trong `"xxababa!"`.

## 11. Một số cạm bẫy Java cụ thể

### `String.length()` và độ dài mẫu

Nếu pattern là `"🙂a"`, `String.length()` trả **3 UTF-16 code units** (emoji 2 + a 1), nhưng `pattern[]` trong matcher có **2 code point**. Đó là lý do chương trình dùng `pattern.length` sau khi giải mã sang `int[]`, không trừ thẳng `String.length()` khi tính code-point offset match.

### Surrogate bị cắt ở ranh giới feed

Một `String` trong Java **có thể chứa nửa surrogate đơn lẻ**; `substring` hoặc `new String(char[],...)` không tự bảo đảm đoạn là một dãy Unicode hoàn chỉnh. Nếu mỗi chunk gọi `chunk.codePoints()` riêng, high surrogate lẻ thường bị lộ thành một giá trị không mong muốn rồi low ở chunk sau lại là một giá trị khác, làm hỏng so khớp theo code point.

Code giữ một high surrogate, sau đó dùng `Character.toCodePoint(high,low)` chỉ khi low hợp lệ. Một chuỗi malformed bị từ chối thay vì lặng lẽ so khớp không đúng.

### Mẫu rỗng

Về toán học, chuỗi rỗng có thể được coi là xuất hiện ở **mọi khe** của luồng, tức `N+1` vị trí nếu có N code point. Trong streaming, cần quyết định khi nào phát khe ban đầu, khe cuối và không phát lại cùng khe qua các chunk rỗng. Bài này **chủ động từ chối mẫu rỗng** để API có nghĩa đơn giản và tránh công bố một quy ước không được yêu cầu.

### Khi feed lỗi giữa chừng

Ví dụ một chunk có vài code point hợp lệ rồi tới surrogate sai. `feed` có thể đã xử lý phần đầu trước khi ném `IllegalArgumentException`. Vì thế không được giả định thao tác feed **atomic** và có thể thử lại nguyên chunk mà không tạo match lặp. Caller nên coi stream/matcher đã lỗi, **khởi tạo lại với dữ liệu đã xác nhận** nếu muốn phục hồi.

Nếu giao thức đòi atomic feed, phải có bước **xác thực/giải mã chunk trước khi thay state**, hoặc cơ chế checkpoint/rollback đầy đủ; đó là yêu cầu bổ sung ngoài bản KMP tối giản.

### `finish()` không phải feed rỗng

Không có lỗi khi feed `""`, kể cả giữa high và low surrogate. Nhưng gọi `finish()` ngay sau high surrogate lẻ là dữ liệu Unicode chưa hoàn tất, nên ném lỗi. Sau finish hợp lệ, feed thêm chunk phải bị từ chối để caller không vô tình nối một stream khác vào stream cũ.

### Giới hạn long cho offset

`processed` là `long` và tăng bằng `Math.addExact`. Luồng trên thực tế khó có thể dài tới giới hạn của long, nhưng dùng cộng có kiểm tra giúp tránh offset bị wrap sang số âm nếu một hệ thống đặc biệt xử lý rất lâu. Khi cần vị trí bytes, `processed` không được tự đổi sang byte bằng một phép nhân.

## 12. Đọc dữ liệu từ tệp và socket mà không nối toàn bộ văn bản

Một mẫu xử lý đọc file văn bản rất dài:

~~~text
open text Reader (UTF-8 decoder with defined malformed policy)
create StreamingKmp once for pattern
allocate reusable char buffer

repeat:
    n = reader.read(buffer)
    if n == -1: break
    feed exactly buffer[0..n)
    publish matches returned from this feed

finish matcher
close Reader
~~~

Mỗi lượt `Reader.read` **không nhất thiết lấp đầy buffer**. Phải dùng chính `n` được trả về, không được tạo `new String(buffer)` khi phần sau buffer vẫn chứa dữ liệu cũ từ lượt trước.

Khi đọc log **theo dòng** bằng `readLine()`, newline đã bị loại. Nếu cần tìm mẫu có `'\n'` hoặc tính offset bao gồm dòng mới, phải **tự đưa lại đúng delimiter** hoặc đọc bằng buffer giữ nguyên stream; không tự thêm `'\n'` vì dữ liệu gốc có thể dùng CRLF `"\r\n"` hoặc không có newline cuối.

### Mỗi kết nối cần một state riêng

Một bộ mẫu `P` và pi có thể được chia sẻ ở dạng **immutable** cho nhiều kết nối, nhưng các biến:

- `matched`;
- `processed`;
- `pendingHigh`;
- `finished`;

là **trạng thái riêng của từng stream**. Không dùng chung một đối tượng matcher thay đổi giữa hai socket, nếu không hậu tố của kết nối A có thể vô tình ghép với tiền tố của kết nối B và tạo false positive.

Trong môi trường đa luồng, giữ mỗi matcher chỉ được feed tuần tự theo đúng thứ tự; nếu nhiều thread cùng feed một stream, cần **đồng bộ và bảo đảm thứ tự**. Các chunk đến đảo thứ tự sẽ làm biến T logic, nên kể cả KMP hoàn toàn đúng cũng trả kết quả cho **chuỗi sai**.

### Khôi phục sau mất kết nối

Với nguồn có thể resume, muốn checkpoint matcher cần ghi đủ:

- ID/phiên bản của **mẫu** và cách so sánh Unicode.
- `matched`, `processed`.
- `pendingHigh` nếu đang chờ cặp surrogate.
- Vị trí nguồn đã được **xác nhận tiêu thụ** (byte offset/record sequence).
- Trạng thái **UTF-8 decoder** nếu đang giải mã byte dở.
- Vị trí kết quả match đã được downstream xác nhận nhận, nếu yêu cầu **exactly once**.

Chỉ ghi `matched` mà không biết nguồn đang ở byte nào có thể gây phát match lặp khi replay. Chỉ ghi byte offset mà mất j có thể bỏ sót match đang vắt qua điểm checkpoint.

## 13. Khi mẫu có ký tự đặc biệt, newline, case và normalization

KMP của bài tìm **mẫu literal**: ký tự nào trong pattern cũng được xem là code point cần bằng chính xác, không có wildcard.

- `P="a.b"` tìm ba ký tự `a`, dấu chấm, `b`, **không phải regex `a.b`**.
- `P="a\nb"` yêu cầu newline thật; nếu luồng bị tách theo line và bỏ newline thì sẽ không match.
- `P="Test"` không match `"test"` nếu không có chính sách case folding.
- `P="é"` không tự match `"e" + U+0301` nếu không chuẩn hóa.
- `P="🙂"` match theo code point U+1F642; một emoji ghép nhiều code point (ZWJ sequence) cần mẫu chứa đầy đủ chuỗi code point muốn tìm.

Nếu bài đòi **so khớp theo từ ngữ/hình thái**, chẳng hạn không phân biệt dấu tiếng Việt, phải mô tả phép biến đổi trước so khớp. Phép chuyển có thể **thay đổi độ dài chuỗi và offset**, nên cần cơ chế ánh xạ vị trí trong chuỗi chuẩn hóa về vị trí gốc; không chỉ thay pattern và bỏ qua vấn đề vị trí.

### Chuẩn hóa từng chunk vì sao nguy hiểm?

Giả sử chunk 1 kết thúc bằng `e`, chunk 2 bắt đầu bằng dấu kết hợp U+0301. Nếu chuẩn hóa NFC từng chunk riêng:

- NFC("e") = "e".
- NFC(U+0301) vẫn là dấu kết hợp.

Nối hai kết quả lại chưa chắc bằng **NFC("e"+U+0301)**, vốn có thể là ký tự `é` ghép sẵn. Vì vậy thao tác normalize có **phụ thuộc ranh giới chunk**, và một implementation streaming đúng cần giữ phần đuôi có thể kết hợp với dữ liệu tới sau.

**Không tự coi `String.equalsIgnoreCase`, `toLowerCase` hoặc regex case-insensitive là bộ chuẩn hóa Unicode tổng quát.** Ngữ nghĩa so khớp cần được lựa chọn theo ứng dụng.

## 14. Cách khác: cửa sổ trượt, Rabin–Karp và Aho–Corasick

### Giữ m−1 ký tự đuôi

Với một mẫu có m code point, có thể giữ `m−1` code point cuối phần stream đã xử lý, nối với chunk mới, chạy thuật toán tìm mẫu trên buffer ấy và chỉ báo **match kết thúc trong dữ liệu mới**.

Ưu điểm: dễ dùng các hàm tìm kiếm sẵn có sau khi xử lý offset và Unicode. Nhược điểm: phải quản lý cửa sổ, copy buffer, phân biệt match đã báo/chưa báo; nếu dùng tìm kiếm ngây thơ có thể tốn O(m) cho mỗi vị trí.

**Độ phức tạp:** phụ thuộc thuật toán tìm kiếm chạy trên mỗi cửa sổ; không mặc định tuyến tính chỉ vì giữ m−1 ký tự. Một cửa sổ với thuật toán tuyến tính hoặc cấu trúc phù hợp vẫn có thể hiệu quả.

### Rabin–Karp / rolling hash

Dùng một **cửa sổ độ dài m** trên stream, giữ giá trị băm lăn của m phần tử gần nhất. Khi nhận phần tử mới:

- Bỏ đóng góp phần tử cũ nhất.
- Nhân cơ số và thêm phần tử mới (theo công thức hash đã chọn).
- So hash của cửa sổ với hash của pattern.
- Nếu hash bằng nhau, thường **so sánh thật** các code point của cửa sổ với pattern để loại trừ hash collision.

Bộ nhớ O(m) để biết phần tử bị đẩy ra và xác minh. Rolling hash có thể hữu ích khi nhiều vị trí cần sàng lọc nhanh, nhưng **hash bằng nhau không phải bằng chứng tuyệt đối** nếu không xác minh hoặc không có một thiết kế hash collision-free phù hợp miền đầu vào.

Với stream không tin cậy, kẻ tấn công có thể tạo nhiều va chạm làm hiệu năng xấu. KMP **không có false positive do collision**, có cận tuyến tính trường hợp xấu cho một mẫu literal.

### Aho–Corasick khi có nhiều mẫu

Nếu cần tìm đồng thời một tập mẫu `P₁,P₂,...,P_k`:

- Xây **trie** của các mẫu.
- Tính **failure links** và danh sách output tương ứng ở các node.
- Giữ **một trạng thái automaton** qua các chunk.
- Khi nhận ký tự mới, cập nhật node theo transition/failure links rồi phát tất cả mẫu kết thúc tại vị trí hiện tại.

Một automaton Aho–Corasick cho nhiều mẫu thường tiết kiệm hơn chạy k KMP độc lập khi k lớn. Chi phí tiền xử lý và bộ nhớ phụ thuộc tổng độ dài mẫu và cách lưu bảng chuyển, còn thời gian stream được phân tích theo số ký tự **cộng số kết quả phát ra**. Một vị trí có thể kết thúc nhiều mẫu khác nhau.

**KMP streaming** là lựa chọn tự nhiên cho **một mẫu literal cố định**; Aho–Corasick tự nhiên hơn cho nhiều mẫu. Không cần dùng regex engine tổng quát khi chỉ tìm một literal và muốn kiểm soát chính xác trạng thái/chunk/offset.

### Regex hoặc biểu thức có wildcard

Một pattern như `a.*b` không phải chuỗi literal. Chiều dài phần match có thể không giới hạn; giữ một số j KMP cho literal không đủ. Cần máy trạng thái NFA/DFA hoặc một trình regex có **giao thức streaming** phù hợp, đồng thời quyết định greedy/non-greedy, độ dài lookbehind, đa dòng, EOF và cách giới hạn tài nguyên. Không thể tự dùng `String.matches` từng chunk rồi cho rằng đã hỗ trợ regex xuyên chunk.

## 15. Định nghĩa đầu ra cho bài toán thực tế

Trong sản phẩm thật, câu “tìm mẫu trên stream” chưa đủ để biết nên trả gì. Cần xác định:

1. **Một hay tất cả lần xuất hiện?** Nếu chỉ hỏi “có không”, có thể dừng khi gặp match đầu tiên. Nếu cần tất cả thì tiếp tục.
2. **Có cho phép overlap?** KMP chuẩn hỗ trợ overlap nhờ `pi[m−1]`; nếu không được overlap, sau match có thể chuyển trạng thái theo chính sách không chồng lấn, nhưng phải định nghĩa rõ.
3. **Chỉ số bắt đầu hay kết thúc?** Bản mã trả **bắt đầu**, không phải processed hiện tại hoặc vị trí cuối.
4. **0-based hay 1-based?** Bản mã là 0-based; nếu đề yêu cầu 1-based, đổi `start+1` khi xuất kết quả.
5. **Theo byte, UTF-16 code unit, code point hay grapheme?** Bản mã là code point.
6. **Có phân biệt chữ hoa/thường/dấu/normalization?** Bản mã phân biệt mọi code point.
7. **Đường truyền có thể retry/duplicate/reorder?** Caller phải xử lý tầng truyền tải trước khi feed.
8. **Khi dữ liệu malformed?** Bản mã ném lỗi nghiêm ngặt, không tự thay U+FFFD.
9. **Mẫu rỗng?** Bản mã không nhận.
10. **Khi EOF?** Bắt buộc gọi `finish()` để phát hiện surrogate dang dở.

Các quyết định này là **một phần của hợp đồng thuật toán**. Thay đổi chúng có thể làm vị trí hoặc số match khác nhau dù cùng dữ liệu trông thấy.

## 16. Kiểm thử độc lập bằng tìm kiếm vét cạn

Cách kiểm tốt nhất cho KMP streaming là đối chiếu với **oracle khác cơ chế** trên dữ liệu nhỏ.

### Oracle sau khi ghép toàn bộ dữ liệu

Trong test, được phép ghép chunks thành chuỗi T rồi giải mã thành **dãy Unicode code point hợp lệ**. Với mỗi vị trí i từ 0 tới N−m:

- So sánh từng phần tử `T[i+j]` với `P[j]`, `0≤j<m`.
- Nếu tất cả bằng nhau, thêm i vào danh sách expected.
- So `expected` với toàn bộ offsets mà streaming KMP phát.

Oracle này tốn **O(N·m)** thời gian và **O(N)** RAM trong test nhưng hoàn toàn không dùng `pi` hay state KMP, nên thích hợp làm đối chiếu độc lập.

### Random chunk boundaries

Để bắt lỗi biên chunk, không chỉ sinh vài chunk đẹp. Hãy:

1. Sinh văn bản gồm nhiều code point, bao gồm ASCII, chữ tiếng Việt, dấu combining, emoji và ký tự lặp.
2. Sinh mẫu ngẫu nhiên không rỗng; đôi khi chọn một đoạn liên tiếp từ văn bản để bảo đảm có match.
3. Chuyển văn bản thành UTF-16 Java String.
4. Chia theo **chỉ số UTF-16 bất kỳ**, kể cả đúng giữa high và low surrogate của emoji.
5. Chèn thêm các chunk rỗng tại vị trí ngẫu nhiên.
6. Feed tuần tự vào KMP, gọi finish cuối cùng.
7. So toàn bộ offsets với oracle tìm trên dãy code point hoàn chỉnh.

**Thuộc tính bất biến:** với cùng pattern và T, **thay cách chia chunk không được đổi tập match và vị trí**. Đây là property-based test rất hiệu quả cho streaming.

### Ca cố định không được bỏ

| Mẫu | Chunk đầu vào | Kết quả code-point offset |
|---|---|---|
| `aba` | `ab | a | ba` | [0,2] |
| `aaa` | `a | "" | aa | aa` | [0,1,2] |
| `needle` | `xxnee | d | lezzneedle` | [2,10] |
| `mẫu` | `m | ẫ | u | " mẫ" | u` | [0,4] |
| `xyz` | `ab | abc` | [] |
| `a` | ba chunk rỗng | [] |
| `🙂a` | high surrogate ở cuối chunk, low đầu chunk kế | [1,3] trong `x🙂a🙂a` |

Để kiểm lỗi, thử mẫu rỗng, low surrogate lẻ, high surrogate cuối stream, high surrogate không được theo sau bằng low, và gọi feed sau finish. API của bài **phải từ chối** các tình huống không hợp lệ ấy theo hợp đồng.

### Kiểm đếm và thứ tự

Với một mẫu không rỗng và N code point, số match tối đa là:

**`max(0,N−m+1)`**.

Danh sách offsets phải **tăng nghiêm ngặt** vì mỗi match mới kết thúc ở một vị trí code point tăng. Các match có thể overlap nhưng không được trùng offset. Nếu pattern dài hơn stream, kết quả rỗng.

Có thể kiểm mỗi offset `i` thỏa `0≤i≤N−m` và đoạn con bắt đầu ở i thực sự bằng pattern.

## 17. Những lỗi thường gặp

1. **Tìm riêng trên từng chunk:** bỏ sót mẫu cắt qua ranh giới.
2. **Reset j=0 khi nhận chunk mới:** mất trạng thái hậu tố đang khớp.
3. **Sau match reset j=0:** bỏ sót những lần xuất hiện chồng lấn.
4. **Sau match giữ j=m rồi truy cập pattern[m]:** lỗi ngoài mảng.
5. **Tính lại pi trên mỗi chunk:** tốn công và không giải quyết ranh giới đúng.
6. **Nhầm processed là chỉ số 0-based cuối cùng:** offset đầu phải là `processed−m` khi processed đếm số code point đã tiêu thụ.
7. **Chỉ dùng offset tương đối chunk:** trả sai vị trí match bắt đầu ở chunk trước.
8. **Ghép tất cả chunk để search:** bộ nhớ tăng theo độ dài stream, không còn streaming thật.
9. **Tưởng một chunk rỗng là EOF:** kết thúc sớm hoặc phát kết quả sai.
10. **Không gọi finish ở EOF:** không phát hiện UTF-16 high surrogate cuối cùng chưa hoàn tất.
11. **Đếm `String.length()` như code point:** sai từ vị trí emoji trở đi.
12. **Gọi codePoints() riêng trên mỗi chunk có thể bị cắt surrogate:** làm hỏng một code point.
13. **Chấp nhận low surrogate không có high tương ứng:** xử lý Unicode sai.
14. **Tách byte UTF-8 rồi decode từng byte chunk độc lập:** có thể tạo U+FFFD giả hoặc mất ký tự.
15. **Giả định UTF-8 byte offset bằng code-point offset:** sai với văn bản đa byte.
16. **Không thống nhất NFC/NFD giữa pattern và stream:** bỏ sót chữ hiển thị giống nhau.
17. **Normalize từng chunk khi dấu combining có thể nằm ở chunk kế:** kết quả có thể khác normalize toàn chuỗi.
18. **Không làm rõ case-sensitive hay case-insensitive:** kết quả không theo yêu cầu.
19. **Tưởng một code point luôn là một grapheme người đọc thấy:** sai với combining/ZWJ.
20. **Dùng rolling hash mà không xác minh collision:** có thể phát false positive.
21. **Dùng KMP literal cho regex có wildcard:** sai bài toán.
22. **Dùng chung mutable matcher cho nhiều luồng:** dữ liệu kết nối này nối vào trạng thái kết nối khác.
23. **Feed chunk đảo thứ tự hoặc retry trùng:** trả match cho chuỗi đã bị thay đổi.
24. **Lưu mọi match vô hạn vào một List:** memory tăng theo số kết quả, dù matcher O(m).
25. **Không quản lý backpressure:** downstream chậm làm buffer kết quả tăng không giới hạn.
26. **Không phân biệt readLine và đọc char stream nguyên vẹn:** làm biến mất newline hoặc CRLF.
27. **Dùng toàn bộ char buffer khi read trả ít hơn capacity:** đưa ký tự còn sót từ lần trước vào matcher.
28. **Không nêu offset 0-based/1-based:** sai output dù match đúng.
29. **Tiếp tục dùng matcher sau lỗi feed giữa chunk như thể chưa xử lý gì:** có thể phát match trùng hoặc lệch.
30. **Tưởng KMP luôn phải giữ nguyên m−1 ký tự cuối text:** thực tế KMP giữ j và pi, không cần giữ tail text.
31. **Cho rằng pattern không thể xuyên hơn hai chunk:** mẫu dài có thể trải nhiều chunk.
32. **Không xét mẫu dài hơn stream:** phải trả rỗng, không ném lỗi tùy tiện.
33. **Tuyên bố thời gian O(N) nhưng âm thầm kiểm tra toàn bộ mẫu tại mỗi vị trí:** có thể thành O(Nm).
34. **Nhầm tiền tố/hậu tố của văn bản với tiền tố/hậu tố của mẫu:** pi được xây từ P, j mô tả quan hệ giữa suffix của T đã đọc và prefix của P.
35. **Không test overlap:** bỏ lỡ bug j=0 sau match.
36. **Không test surrogate split giữa hai feed:** không kiểm soát độ tin cậy Unicode.
37. **Không checkpoint decoder khi resume byte stream:** có thể giải mã sai tại vị trí cắt byte.
38. **Không lưu nguồn offset khi resume:** kết quả có thể thiếu/trùng dù j được lưu.
39. **Áp dụng cùng một đối tượng matcher song song không khóa:** thay đổi j/processed có race.
40. **Đưa dấu ngắt tự tạo giữa hai chunk:** nội dung stream bị biến đổi, tạo hoặc phá match.

## 18. Bài tập vận dụng

**Bài 1 — Chỉ đếm match.** Chuyển API từ `List<Long> feed` sang bộ đếm `long totalMatches`, tăng khi matched==m. Chứng minh vẫn O(m) trạng thái và O(N+m) thời gian, không cần giữ các vị trí. Kiểm tràn long nếu dữ liệu cực dài.

**Bài 2 — Callback streaming.** Nhận một `LongConsumer` để gọi khi có kết quả. Điều chỉnh `feed` không tạo List cho mỗi chunk; đối chiếu callback offsets với List-based demo trên chuỗi `"aaaaa"` và mẫu `"aaa"`.

**Bài 3 — Mẫu rỗng.** Thiết kế một quy ước cho pattern rỗng: mỗi khe giữa N code point, kể cả trước ký tự đầu và sau ký tự cuối, là một match. Dùng state để không phát lặp các khe tại ranh giới các chunk rỗng; chứng minh tổng có đúng N+1 kết quả sau EOF.

**Bài 4 — Chuẩn hóa NFC streaming.** Mẫu `"é"` và text `"e"+U+0301` phải match. Hãy chỉ ra vì sao normalize mỗi chunk riêng có thể sai; thiết kế buffer giữ ngữ cảnh kết hợp và ánh xạ offset text chuẩn hóa về text gốc.

**Bài 5 — Nhiều mẫu.** Cho 1000 từ khóa dài khác nhau. So bộ nhớ/thời gian chạy 1000 KMP độc lập với Aho–Corasick. Nêu cách automaton giữ state xuyên chunk và cách in vị trí bắt đầu cho mỗi mẫu.

**Bài 6 — Resume với checkpoint.** Stream byte UTF-8 có thể bị reconnect. Thiết kế một bản ghi checkpoint gồm vị trí byte nguồn, decoder partial bytes, `matched`, `processed`, surrogate pending và offset match đã xác nhận. Mô tả rủi ro khi replay một chunk hai lần.

**Bài 7 — So khớp byte thuần.** Thay int[] code point bằng byte[] pattern và feed byte chunks, xuất byte offsets. Chứng minh cùng bất biến KMP vẫn đúng cho dãy byte và không cần giải mã Unicode nếu chính bài toán yêu cầu signature theo bytes.

**Bài 8 — Tìm mẫu chỉ trong cửa sổ mới nhất.** Chỉ quan tâm match có điểm kết thúc nằm trong W code point gần nhất. Giữ KMP để phát sự kiện, rồi duy trì deque positions đã phát và loại các sự kiện quá cũ. Đừng nhầm cửa sổ lưu kết quả với trạng thái cần để khớp.

## 19. Checklist thiết kế và nộp bài

- Đã định nghĩa stream nối theo **đúng thứ tự** và không tự thêm separator?
- Mẫu là **literal** hay regex/wildcard? Một hay nhiều mẫu?
- Đã ghi rõ match **chồng lấn** có được trả không?
- Mẫu rỗng được từ chối hay có quy ước N+1 khe?
- Code trả **vị trí bắt đầu** và quy ước **0-based**?
- Đơn vị offset là byte, UTF-16 unit, Unicode code point hay grapheme?
- pi được xây **một lần** từ mẫu, không xây lại từng chunk?
- j và processed **được giữ giữa các feed**?
- Sau match, có dùng `j=pi[m−1]` thay vì j=0?
- Offset global có được tính theo tổng code point đã tiêu thụ, không phải vị trí chunk?
- Chunk rỗng có giữ nguyên trạng thái và không tạo match giả?
- Có hỗ trợ một mẫu trải qua **nhiều chunk liên tiếp**?
- Với String/Reader UTF-16, surrogate cắt ngang chunk có được ghép đúng không?
- `finish()` có bắt lỗi high surrogate dang dở và cấm feed sau EOF?
- Với byte UTF-8, có decoder giữ trạng thái giữa các lượt đọc?
- Nếu muốn normalize Unicode/case-fold, có xử lý **ranh giới chunk và ánh xạ offset** đúng?
- Caller có tiêu thụ kết quả theo luồng, tránh giữ List vô hạn?
- Nếu nhiều luồng, mỗi luồng có matcher state riêng?
- Nếu reconnect/retry, có checkpoint chính xác vị trí nguồn và state?
- Có test overlap, dài hơn stream, chunk rỗng, ranh giới emoji, pattern không có trong text?
- Đã đối chiếu **với oracle vét cạn trên văn bản hoàn chỉnh** khi test dữ liệu nhỏ?
- Đã thay cách phân chunk ngẫu nhiên và chứng minh kết quả không đổi?
- Đã phân tích O(N+m) thời gian, O(m) trạng thái và chi phí output?
- Đã nêu rõ giải pháp KMP cho một mẫu, rolling hash cho kiểm cửa sổ và Aho–Corasick cho nhiều mẫu?

**Kết luận:** khi tìm một mẫu literal trên dữ liệu nhận từng phần, điều quan trọng không phải kích thước chunk, mà là **giữ đúng trạng thái so khớp ở ranh giới chunk**. KMP tiền xử lý mẫu bằng `pi`, rồi cập nhật `matched` cho từng code point mới, phát offset `processed−m` khi match hoàn tất và trở về `pi[m−1]` để giữ các lần xuất hiện chồng lấn. Luồng có thể dài vô hạn về mặt thiết kế mà matcher chỉ cần **O(m) bộ nhớ** và **O(N+m) thời gian** trên N code point đã nhận (chưa tính lưu toàn bộ kết quả bên ngoài). Khi dữ liệu là văn bản thật, cần xác định rõ UTF-8/UTF-16, đơn vị offset, xử lý Unicode bị cắt, chuẩn hóa, lỗi, EOF và giao thức truyền tải; đây là những điều kiện để một thuật toán đúng trên chuỗi hoàn chỉnh cũng **đúng khi chạy trực tuyến**.