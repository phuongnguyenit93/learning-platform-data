# Chuỗi, mẫu, bảng chữ cái và đơn vị so khớp

## 1. Bài toán tìm kiếm chuỗi bắt đầu từ đặc tả

**Tìm kiếm chuỗi (string matching)** thường được mô tả ngắn gọn là: tìm tất cả nơi mà **mẫu P** xuất hiện trong **văn bản T**. Tuy nhiên, để một lời giải thật sự đúng, cần thống nhất:

- **T là dãy phần tử gì?** Dữ liệu byte, Java char, Unicode code point, grapheme cluster hay token?
- **P là dãy phần tử gì?** Có dùng cùng biểu diễn và phép bằng nhau với T không?
- **Bảng chữ cái Σ** là tập những phần tử được phép.
- **Độ dài và chỉ số** đang tính theo đơn vị nào?
- **Một kết quả** có được nằm trong nửa ký tự UTF-16 hay bên trong một grapheme không?
- Có trả các lần khớp **chồng lấn** không?
- Mẫu rỗng khớp tại những vị trí nào?
- So khớp có **phân biệt hoa–thường**, có **chuẩn hóa Unicode**, hay coi ký tự giống nhau về mặt hình thức là bằng nhau không?

Đây không phải chỉ là vấn đề tên biến. Một kết quả đúng theo **UTF-16 offset** có thể là kết quả sai theo **code-point offset**. Khi text có emoji, việc đưa nhầm một chỉ số code point vào String.substring có thể cắt giữa một cặp surrogate. Khi chuẩn hóa Unicode, offset trên text sau chuẩn hóa không nhất thiết trỏ đúng cùng vị trí của text gốc.

Bài học này xây dựng định nghĩa chính xác cho chuỗi, mẫu và đơn vị so khớp; phân biệt byte/UTF-16/code point/grapheme/token; sau đó triển khai thuật toán naive và KMP độc lập bằng Java 17, với toàn bộ ví dụ kết quả có chỉ số nhất quán.

## 2. Chuỗi là một dãy ký hiệu trên bảng chữ cái

Trong mô hình hình thức, **bảng chữ cái (alphabet)** là tập các ký hiệu được phép, ký hiệu Σ. Một chuỗi là **dãy hữu hạn** ký hiệu thuộc Σ; tập tất cả các chuỗi hữu hạn ký hiệu là \(\Sigma^\ast\).

Đặt văn bản:

\[
T=(t_0,t_1,\ldots,t_{n-1})
\]

và mẫu:

\[
P=(p_0,p_1,\ldots,p_{m-1}).
\]

Một lần xuất hiện chính xác của P ở vị trí i có nghĩa:

\[
0\le i\le n-m,
\qquad t_{i+j}=p_j \quad \forall\,0\le j<m.
\]

Ở đây **n, m, i, j đều tính bằng cùng một loại ký hiệu**. Nếu các phần tử là byte thì m là số byte của mẫu; nếu phần tử là Unicode code point thì m là số code point; nếu phần tử là token thì m là số token.

**Σ không bắt buộc là A–Z hoặc chữ tự nhiên.** Những ví dụ hợp lệ:

| Lựa chọn Σ | Một ký hiệu được hiểu là | Ứng dụng |
|---|---|---|
| {0,1} | Một bit | Tìm mẫu bit |
| 0..255 | Một byte | Tìm kiếm trong file nhị phân |
| Các UTF-16 code unit | Một char 16 bit của Java | API dựa trên String/charAt |
| Unicode scalar value | Một code point hợp lệ ngoài vùng surrogate | Tìm kiếm trên mã Unicode |
| Grapheme cluster | Một cụm ký tự hiển thị | So khớp theo ký tự người dùng cảm nhận |
| Token từ tokenizer | Một từ/ID từ vựng | Tìm chuỗi token trong NLP |

Một số thuật toán (ví dụ bảng chuyển trạng thái hoặc bảng ký tự cuối) dùng bộ nhớ phụ thuộc kích thước Σ. Nếu Σ lớn, cần cân nhắc HashMap hoặc nén ID ký hiệu. **KMP không phải cấp phát bảng theo \(|\Sigma|\)**: nó chỉ dùng phép so sánh bằng nhau và một mảng dài m.

### Chuỗi, mẫu và phép bằng nhau

“Bằng nhau” có thể là:
- **Exact**: cùng mã ký hiệu từng vị trí.
- **Case-insensitive**: có một chính sách hoa/thường cụ thể.
- **Canonical equivalence**: chuẩn hóa Unicode NFC/NFD trước khi so.
- **Grapheme equality**: so các cụm hiển thị sau khi phân đoạn theo cùng một quy tắc.
- **Token equality**: so ID token theo tokenizer.

Thuật toán naive/KMP trong bài dùng **exact equality** sau khi chuyển hai String sang **cùng loại đơn vị**. Không tự chuẩn hóa hoặc đổi hoa/thường bên trong bộ tìm kiếm, vì các phép biến đổi ấy có thể làm thay đổi chiều dài và tọa độ.

## 3. Quy ước vị trí, chồng lấn và mẫu rỗng

### 3.1. Vị trí bắt đầu là số nguyên 0-based

Kết quả là **danh sách mọi chỉ số bắt đầu** của mẫu, sắp tăng dần. Ví dụ:

~~~text
Text:       b a n a n a
Index:      0 1 2 3 4 5
Pattern:      a n a
Pattern:          a n a
Starts:     [1, 3]
~~~

Trong "banana", mẫu "ana" có hai lần xuất hiện ở **1 và 3**, dùng chung ký tự ở vị trí 3. Đó là các **match chồng lấn (overlapping matches)**, hoàn toàn hợp lệ với bài toán tìm tất cả vị trí.

Với T="aaaa" và P="aa", đáp án **[0,1,2]**, không phải [0,2]. Nếu ứng dụng chỉ muốn các match không chồng lấn, phải công bố chính sách chọn; đó là một bài toán đầu ra khác.

### 3.2. Pattern dài hơn text

Nếu m>n, không có chỉ số bắt đầu nào hợp lệ, trả **[]**. T="ab", P="abc" là ví dụ.

### 3.3. Pattern rỗng

Bài này chọn quy ước **mẫu rỗng xuất hiện ở tất cả ranh giới ký hiệu**. Nếu T có n đơn vị, trả:

\[
[0,1,\ldots,n],
\]

gồm **n+1** vị trí. Vì thế:
- T="abc", P="" → [0,1,2,3].
- T="", P="" → [0].
- T="", P="a" → [].

Một API có thể chọn cấm pattern rỗng hoặc chỉ trả vị trí đầu tiên, nhưng đó phải là quyết định có tài liệu. Không được để các hàm khác nhau trong cùng hệ thống có ngữ nghĩa mẫu rỗng mâu thuẫn mà không ghi rõ.

Điều đặc biệt quan trọng: cùng text Unicode có thể có **n UTF-16 khác n code point**; danh sách ranh giới khi pattern rỗng cũng khác nhau.

### 3.4. So khớp phân biệt hoa/thường

Với T="Javajava", P="java", exact matching trả [4]; chữ hoa J ở đầu không bằng chữ thường j. Không được tự dùng toLowerCase nếu đề chỉ yêu cầu exact matching.

## 4. Một String có mấy “ký tự”?

Trong văn bản Unicode cần phân biệt **byte UTF-8**, **UTF-16 code unit**, **Unicode code point** và **extended grapheme cluster**.

### 4.1. UTF-8 byte

UTF-8 mã hóa Unicode thành một dãy byte có độ dài biến thiên:
- ASCII thông thường: một byte.
- Nhiều ký tự có dấu: nhiều byte.
- Emoji ngoài BMP như 😀: bốn byte.

Byte thích hợp khi ta muốn vị trí trong **file hoặc luồng byte**. Byte offset không phải chỉ số của một Java String. Một pattern byte tùy ý có thể trùng vào một phần bên trong dãy byte mã hóa ký tự; nếu cần highlight văn bản Unicode, phải bảo đảm kết quả nằm ở ranh giới mã hóa hợp lệ.

### 4.2. Java UTF-16 code unit

Java String.length() đếm số **đơn vị UTF-16**, không phải số code point hay số grapheme. Java char đại diện một đơn vị 16 bit. Các code point ngoài BMP thường cần **hai code unit**, gồm high surrogate và low surrogate.

Ví dụ T="A😀B😀":

~~~text
UTF-16 index:       0     1           2       3     4           5
Code unit:          A   high(😀)    low(😀)    B    high(😀)    low(😀)
Code-point index:   0     1                    2     3
~~~

Kết quả:
- String.length() = **6**.
- Text có **4 code point**.
- Mẫu 😀 bắt đầu tại **[1,4] theo UTF-16**.

String.indexOf và String.substring trong Java dùng **tọa độ UTF-16**; vị trí Matcher.start() của Java regex cũng là offset trong Java String. Không được dùng code-point index như thể nó là UTF-16 offset.

### 4.3. Unicode code point

Một **Unicode code point** là một vị trí số trong không gian mã Unicode. Unicode scalar value **loại vùng surrogate U+D800..U+DFFF**.

Trong Java, String.codePoints().toArray() trả dãy int: cặp surrogate hợp lệ được gộp thành một code point. Với "A😀B😀", dãy có **4** phần tử; mẫu 😀 bắt đầu tại **[1,3] theo code point**.

Lưu ý: Java String có thể chứa **surrogate đứng lẻ**. Khi đó codePoints() vẫn có thể trả giá trị surrogate ấy dưới dạng int riêng, mặc dù nó **không phải Unicode scalar value hợp lệ**. Nếu hệ thống yêu cầu văn bản Unicode hợp lệ, phải kiểm tra well-formed UTF-16 hoặc có chính sách thay thế/loại bỏ lỗi mã hóa.

### 4.4. Grapheme cluster

Một **grapheme cluster** là cụm code point được xem như một đơn vị ký tự hiển thị theo quy tắc phân đoạn. Một cụm có thể gồm nhiều code point:
- "é" có thể là U+00E9 (một code point) hoặc U+0065 + U+0301 (chữ e và dấu kết hợp).
- Emoji kèm màu da gồm các code point khác nhau nhưng có thể là một cụm.
- Emoji gia đình có thể dùng nhiều ký tự liên kết bằng **ZWJ**.
- Một cờ có thể được tạo bằng hai **regional indicator**.

Vì vậy **code point không đồng nghĩa grapheme**, và grapheme không nhất thiết bằng số char.

Nếu bài yêu cầu tìm theo **extended grapheme cluster**, phải phân đoạn cả text và pattern theo cùng một quy tắc Unicode Standard Annex #29 (và phiên bản dữ liệu đã chọn), sau đó tìm trên dãy cụm. Java 17 có BreakIterator.getCharacterInstance nhưng không được mặc nhiên xem mọi bản JDK 17 đáp ứng mọi quy tắc grapheme hiện hành, đặc biệt các chuỗi emoji ZWJ. Với yêu cầu nghiêm ngặt/cross-platform, cần xác minh rule set hoặc dùng thư viện Unicode phù hợp như ICU4J.

### 4.5. Token

Một bài tìm kiếm NLP có thể xem **token** là đơn vị: từ, ID từ vựng, dấu câu hoặc một mảnh từ. Cần tokenizer có quy tắc rõ ràng; việc tách chỉ bằng dấu cách không luôn phù hợp với mọi ngôn ngữ. Nếu đầu ra phải trỏ về văn bản gốc, mỗi token cần mang **span gốc** (byte hoặc UTF-16).

## 5. Cùng một mẫu, ba hệ tọa độ

Với T="A😀B😀" và P="😀":

| Hệ tọa độ | Độ dài T | Độ dài P | Vị trí bắt đầu P |
|---|---:|---:|---|
| UTF-8 byte | 10 | 4 | [1,6] |
| Java UTF-16 code unit | 6 | 2 | [1,4] |
| Unicode code point | 4 | 1 | [1,3] |
| Grapheme cluster trong ví dụ này | 4 | 1 | [1,3] |

Hai emoji đơn ở đây mỗi cái là một grapheme; **đó không phải kết luận tổng quát cho mọi emoji kết hợp**.

Để giải thích vị trí byte:
- 'A' có 1 byte.
- Emoji đầu có 4 byte, bắt đầu tại offset 1.
- 'B' có 1 byte, nằm sau 1+4=5 byte.
- Emoji thứ hai bắt đầu tại offset 6.
- Tổng 10 byte.

Để giải thích vị trí UTF-16:
- 'A' dùng một code unit index 0.
- Emoji đầu dùng indices 1,2.
- 'B' ở index 3.
- Emoji thứ hai dùng indices 4,5.

Để giải thích code point:
- 'A' ở 0, emoji đầu ở 1, 'B' ở 2, emoji sau ở 3.

### Khớp nửa emoji ở UTF-16

Nếu pattern chỉ chứa **low surrogate** của emoji 😀, so khớp theo char UTF-16 sẽ tìm thấy ở code-unit index **[2,5]** của text. Nhưng pattern low surrogate đứng lẻ **không phải Unicode scalar value hợp lệ**; so khớp theo dãy code point trên text có emoji hợp lệ sẽ trả **[]**.

Đây là một ví dụ cố ý cho thấy sự khác biệt giữa **matching trên các đơn vị char** và **matching trên ký tự Unicode hợp lệ**. Không nên lấy kết quả UTF-16 nằm giữa surrogate pair rồi đưa cho UI như ranh giới ký tự.

## 6. Chuẩn hóa Unicode và phép bằng nhau

### 6.1. Canonical equivalence: NFC/NFD

Có hai cách mã hóa thường gặp của dấu é:

~~~text
Composed:   U+00E9       (é)
Decomposed: U+0065 U+0301 (e + dấu kết hợp)
~~~

Hai dãy **không bằng nhau khi so code point từng phần tử**. Nếu ứng dụng yêu cầu coi chúng là tương đương chuẩn tắc, có thể dùng Normalizer.normalize trên **cả text và pattern** trước khi tìm:

~~~java
String normalizedText =
        Normalizer.normalize(text, Normalizer.Form.NFC);
String normalizedPattern =
        Normalizer.normalize(pattern, Normalizer.Form.NFC);
~~~

Với text "café" dùng é dựng sẵn và pattern "e" + dấu kết hợp:
- Tìm trực tiếp theo code point: **[]**.
- Chuẩn hóa cả hai về NFC: **[3]**.

NFC và NFD là các dạng chuẩn hóa **canonical**. NFKC/NFKD còn chuẩn hóa **compatibility**, có thể gộp những phân biệt quan trọng đối với ứng dụng; không tự chọn NFKC khi bài toán chỉ yêu cầu canonical equivalence.

### 6.2. Offset sau normalize thuộc về text mới

Chuẩn hóa có thể thay đổi số code point hoặc UTF-16 code unit. Ví dụ hai nhóm "e"+"dấu" có thể biến thành hai "é" dựng sẵn; nhóm thứ hai bắt đầu ở code-point index **2** trong bản phân rã nhưng ở index **1** trong bản NFC.

Vì vậy, **offset của kết quả sau normalize không tự động trỏ đúng text gốc**. Nếu cần tô sáng vùng khớp trong tài liệu gốc, phải tạo và giữ bản đồ ánh xạ vị trí hoặc provenance qua bước biến đổi.

### 6.3. Case-insensitive không đơn giản là lowercase tất cả

Yêu cầu tìm không phân biệt chữ hoa/thường cần một chính sách rõ:
- ASCII-only case-insensitive khác full Unicode case folding.
- Quy tắc hoa/thường có thể phụ thuộc **locale**.
- Một phép đổi hoa/thường có thể thay đổi **số code point**.
- Chỉ lowercase text mà không xử lý pattern tương ứng là sai.

toLowerCase(Locale.ROOT) hữu ích cho một số trường hợp nhưng **không được tuyên bố nó là full Unicode case folding**, và cũng không tự bảo toàn offset của văn bản gốc.

Các ký tự trông giống nhau nhưng thuộc hệ chữ khác nhau (homoglyph) không tự động bằng nhau theo Unicode exact matching; đó là bài toán bảo mật/chuẩn hóa khác.

## 7. Thuật toán naive trên dãy đơn vị đã chọn

Thuật toán trực tiếp thử mọi điểm bắt đầu i và so từng phần tử:

~~~text
naiveAll(T, P):
    n = number of symbols in T
    m = number of symbols in P

    if m == 0:
        return [0, 1, ..., n]

    positions = []
    for i = 0 .. n-m:
        equal = true
        for j = 0 .. m-1:
            if T[i+j] != P[j]:
                equal = false
                break
        if equal:
            positions.add(i)

    return positions
~~~

Nếu m>n, vòng ngoài không chạy và trả [].

**Thời gian xấu nhất:** O(nm) phép so sánh ký hiệu, với n,m tính trong **cùng đơn vị**. **Bộ nhớ phụ:** O(1) ngoài danh sách kết quả nếu T,P đã ở dạng mảng; thêm O(n+m) nếu cần chuyển từ String sang mảng code point.

Naive rất hữu ích như **oracle độc lập** để kiểm thử một thuật toán nhanh hơn. Với text ngắn và pattern ngắn, dễ kiểm chứng tất cả match chồng lấn cùng các trường hợp biên.

## 8. KMP: tiền tố, hậu tố và xử lý overlap

**KMP (Knuth–Morris–Pratt)** giải exact string matching bằng cách lưu mảng **LPS (longest proper prefix also suffix)** của mẫu.

Với P và index k, lps[k] là độ dài tiền tố thực sự dài nhất của P[0..k] đồng thời là hậu tố của đoạn ấy.

Ví dụ:

~~~text
P:    a b a b a c a
LPS:  0 0 1 2 3 0 1
~~~

### 8.1. Xây LPS

~~~text
buildLps(P):
    lps[0] = 0
    len = 0

    for i = 1 .. m-1:
        while len > 0 and P[i] != P[len]:
            len = lps[len-1]
        if P[i] == P[len]:
            len++
        lps[i] = len

    return lps
~~~

Sau mismatch, fallback len=lps[len−1] giữ lại ứng viên dài nhất còn có thể là tiền tố khớp. Nó tránh so lại từ đầu những ký hiệu mà ta đã biết là giống nhau.

### 8.2. Quét text

~~~text
kmpAll(T, P):
    if P is empty:
        return [0 .. length(T)]

    lps = buildLps(P)
    j = 0
    matches = []

    for i = 0 .. length(T)-1:
        while j > 0 and T[i] != P[j]:
            j = lps[j-1]

        if T[i] == P[j]:
            j++

        if j == length(P):
            matches.add(i - length(P) + 1)
            j = lps[j-1]

    return matches
~~~

Điểm quan trọng là **sau khi khớp hết mẫu, j=lps[m−1]**, không tự đặt j=0. Nhờ đó KMP tìm đủ các lần chồng lấn: "aa" trong "aaaa" có [0,1,2].

### 8.3. Vì sao KMP đúng?

Bất biến: j là độ dài tiền tố mẫu dài nhất đang khớp với hậu tố của đoạn text đã duyệt, với j<m sau khi đã báo match đầy đủ.

- Nếu ký hiệu mới bằng P[j], tăng j một.
- Nếu mismatch, mọi lựa chọn tiền tố dài hơn lps[j−1] đều không thể khớp vì một đoạn đã đối chiếu trước đó cố định. Fallback giữ ứng viên có thể đúng mà không bỏ match nào.
- Khi j=m, m ký hiệu vừa duyệt liên tiếp bằng P; chỉ số bắt đầu đúng là i−m+1.
- Sau khi báo, fallback về lps[m−1] giữ thông tin cần thiết cho những match chồng lấn.

KMP sử dụng **phép bằng nhau trên ký hiệu**, không phụ thuộc ký hiệu là ASCII, UTF-16 char, code point hay token.

### 8.4. Chi phí và giới hạn khái niệm

Tạo LPS **O(m)**; duyệt text **O(n)**; tổng **O(n+m)** phép so sánh ký hiệu và **O(m)** bộ nhớ LPS, cộng bộ nhớ lưu kết quả.

Các số n,m phải đo **cùng đơn vị mà KMP nhận vào**. Nếu chuyển text và pattern từ Java String thành int[] ký hiệu, cần thêm thời gian/bộ nhớ chuyển đổi. Nếu sau đó chuyển offset code point về byte/UTF-16, đó là công đoạn khác, không nằm trong chứng minh cốt lõi của KMP.

## 9. Java String: chuyển giữa các hệ tọa độ

### 9.1. Khi caller cần UTF-16 offset

Tách text, pattern thành các int đại diện từng charAt(i). KMP trên các mảng này trả chỉ số UTF-16 giống kiểu tọa độ mà String.substring sử dụng.

Lưu ý char-level matching có thể khớp giữa surrogate pair nếu mẫu bị malformed. Trong ứng dụng yêu cầu ký tự Unicode hợp lệ, nên xác thực hoặc dùng code point matching.

### 9.2. Khi caller cần code-point offset

Tách String bằng codePoints().toArray(); KMP trên hai mảng int trả chỉ số code point. Một emoji ngoài BMP có đúng một phần tử.

**Code point không phải grapheme**, nên điều này chưa giải yêu cầu so khớp theo ký tự người dùng cảm nhận khi có dấu kết hợp/emoji modifier/ZWJ.

### 9.3. Từ code point tới UTF-16 offset

Với một code-point index k, có thể gọi:

~~~java
int utf16Offset = text.offsetByCodePoints(0, k);
~~~

Nếu cần quy đổi rất nhiều kết quả, lặp thao tác từ đầu text nhiều lần có thể tốn thời gian. Cách tốt hơn là tiền xử lý một mảng **mapCpToUtf16**: mỗi phần tử map[k] là offset UTF-16 của ranh giới trước code point k. Tạo map trong một lượt O(n), sau đó tra O(1) cho mỗi kết quả.

Với "A😀B😀", mapCpToUtf16=[0,1,3,4,6], nên code-point starts [1,3] chuyển thành UTF-16 starts [1,4].

### 9.4. Từ code point tới byte UTF-8

Tương tự, có thể tiền xử lý mapCpToUtf8 từ độ dài byte của từng code point khi mã hóa UTF-8.

Với "A😀B😀", mapCpToUtf8=[0,1,5,6,10], nên code-point starts [1,3] thành byte starts [1,6].

**Không có công thức chung** “UTF-16 index ×2 = byte offset” hoặc “code-point index ×4 = byte offset”. Cả UTF-16 và UTF-8 dùng số đơn vị biến thiên theo ký hiệu.

Nếu text chứa surrogate đứng lẻ, bộ mã hóa có thể thay ký tự lỗi theo một chính sách riêng. Để trả byte offset có ý nghĩa nhất quán của **Unicode hợp lệ**, code mẫu dưới đây kiểm tra well-formed UTF-16 trước khi tính byte map.

## 10. Chương trình Java 17: cùng KMP, UTF-16 và code point

Lưu thành **StringMatchingUnitsDemo.java**. Code dùng:
- MatchUnit.UTF16 và MatchUnit.CODE_POINT.
- KMP chung trên mảng int[].
- Pattern rỗng tại mọi ranh giới.
- Mọi kết quả chồng lấn.
- Hai bản đồ code point→UTF-16 và code point→UTF-8.
- Kiểm tra surrogate đứng lẻ trước phép đổi sang UTF-8.
- Ví dụ Unicode normalization chỉ thực hiện khi caller chủ động yêu cầu.

~~~java
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public final class StringMatchingUnitsDemo {
    private StringMatchingUnitsDemo() {
    }

    public enum MatchUnit {
        UTF16,
        CODE_POINT
    }

    private static int[] symbols(String s, MatchUnit unit) {
        if (unit == MatchUnit.CODE_POINT) {
            return s.codePoints().toArray();
        }

        int[] result = new int[s.length()];
        for (int i = 0; i < s.length(); i++) {
            result[i] = s.charAt(i);
        }
        return result;
    }

    private static int[] buildLps(int[] p) {
        int[] lps = new int[p.length];
        int len = 0;

        for (int i = 1; i < p.length; i++) {
            while (len > 0 && p[i] != p[len]) {
                len = lps[len - 1];
            }
            if (p[i] == p[len]) {
                len++;
            }
            lps[i] = len;
        }
        return lps;
    }

    private static List<Integer> kmp(int[] text, int[] pattern) {
        int n = text.length;
        int m = pattern.length;
        List<Integer> found = new ArrayList<>();

        if (m == 0) {
            for (int boundary = 0; boundary <= n; boundary++) {
                found.add(boundary);
            }
            return List.copyOf(found);
        }

        int[] lps = buildLps(pattern);
        int j = 0;

        for (int i = 0; i < n; i++) {
            while (j > 0 && text[i] != pattern[j]) {
                j = lps[j - 1];
            }

            if (text[i] == pattern[j]) {
                j++;
            }

            if (j == m) {
                found.add(i - m + 1);
                j = lps[m - 1]; // giữ các match chồng lấn
            }
        }
        return List.copyOf(found);
    }

    public static List<Integer> findAll(
            String text, String pattern, MatchUnit unit) {
        Objects.requireNonNull(text, "text");
        Objects.requireNonNull(pattern, "pattern");
        Objects.requireNonNull(unit, "unit");
        return kmp(symbols(text, unit), symbols(pattern, unit));
    }

    private static int[] codePointBoundariesUtf16(String text) {
        int count = text.codePointCount(0, text.length());
        int[] result = new int[count + 1];
        int utf16 = 0;

        for (int i = 0; i < count; i++) {
            result[i] = utf16;
            int codePoint = text.codePointAt(utf16);
            utf16 += Character.charCount(codePoint);
        }
        result[count] = utf16;
        return result;
    }

    public static List<Integer> codePointMatchesAsUtf16(
            String text, String pattern) {
        List<Integer> matches =
                findAll(text, pattern, MatchUnit.CODE_POINT);
        int[] map = codePointBoundariesUtf16(text);
        List<Integer> result = new ArrayList<>();
        for (int index : matches) {
            result.add(map[index]);
        }
        return List.copyOf(result);
    }

    private static void requireWellFormedUtf16(String text) {
        for (int i = 0; i < text.length(); i++) {
            char c = text.charAt(i);
            if (Character.isHighSurrogate(c)) {
                if (i + 1 == text.length()
                        || !Character.isLowSurrogate(
                                text.charAt(i + 1))) {
                    throw new IllegalArgumentException(
                            "Unpaired high surrogate");
                }
                i++;
            } else if (Character.isLowSurrogate(c)) {
                throw new IllegalArgumentException(
                        "Unpaired low surrogate");
            }
        }
    }

    private static int[] codePointBoundariesUtf8(String text) {
        requireWellFormedUtf16(text);
        int[] utf16 = codePointBoundariesUtf16(text);
        int[] result = new int[utf16.length];

        for (int i = 0; i < utf16.length - 1; i++) {
            String point = text.substring(utf16[i], utf16[i + 1]);
            int bytes = point.getBytes(StandardCharsets.UTF_8).length;
            result[i + 1] = Math.addExact(result[i], bytes);
        }
        return result;
    }

    public static List<Integer> codePointMatchesAsUtf8Bytes(
            String text, String pattern) {
        requireWellFormedUtf16(text);
        requireWellFormedUtf16(pattern);
        List<Integer> matches =
                findAll(text, pattern, MatchUnit.CODE_POINT);
        int[] map = codePointBoundariesUtf8(text);
        List<Integer> result = new ArrayList<>();
        for (int index : matches) {
            result.add(map[index]);
        }
        return List.copyOf(result);
    }

    public static void main(String[] args) {
        System.out.println("Banana UTF16: "
                + findAll("banana", "ana", MatchUnit.UTF16));
        System.out.println("Banana code points: "
                + findAll("banana", "ana", MatchUnit.CODE_POINT));
        System.out.println("Overlap: "
                + findAll("aaaa", "aa", MatchUnit.CODE_POINT));

        String emoji = "\uD83D\uDE00";
        String text = "A" + emoji + "B" + emoji;

        System.out.println("Lengths UTF16/code points/UTF8: "
                + text.length() + "/"
                + text.codePointCount(0, text.length()) + "/"
                + text.getBytes(StandardCharsets.UTF_8).length);

        System.out.println("Emoji UTF16: "
                + findAll(text, emoji, MatchUnit.UTF16));
        System.out.println("Emoji code points: "
                + findAll(text, emoji, MatchUnit.CODE_POINT));
        System.out.println("Emoji CP as UTF16: "
                + codePointMatchesAsUtf16(text, emoji));
        System.out.println("Emoji CP as UTF8 bytes: "
                + codePointMatchesAsUtf8Bytes(text, emoji));

        System.out.println("Empty UTF16: "
                + findAll(text, "", MatchUnit.UTF16));
        System.out.println("Empty code points: "
                + findAll(text, "", MatchUnit.CODE_POINT));

        String lowSurrogate = String.valueOf('\uDE00');
        System.out.println("Low surrogate UTF16: "
                + findAll(text, lowSurrogate, MatchUnit.UTF16));
        System.out.println("Low surrogate code points: "
                + findAll(text, lowSurrogate, MatchUnit.CODE_POINT));

        try {
            codePointMatchesAsUtf8Bytes(text, lowSurrogate);
            System.out.println("Malformed pattern rejected: false");
        } catch (IllegalArgumentException expected) {
            System.out.println("Malformed pattern rejected: true");
        }

        String composed = "caf\u00E9";
        String decomposedPattern = "e\u0301";

        System.out.println("Before NFC: "
                + findAll(composed, decomposedPattern,
                        MatchUnit.CODE_POINT));

        String normalizedText = Normalizer.normalize(
                composed, Normalizer.Form.NFC);
        String normalizedPattern = Normalizer.normalize(
                decomposedPattern, Normalizer.Form.NFC);

        System.out.println("After NFC: "
                + findAll(normalizedText, normalizedPattern,
                        MatchUnit.CODE_POINT));

        System.out.println("Case sensitive: "
                + findAll("Javajava", "java", MatchUnit.CODE_POINT));
        System.out.println("Both empty: "
                + findAll("", "", MatchUnit.CODE_POINT));
        System.out.println("Longer pattern: "
                + findAll("ab", "abc", MatchUnit.CODE_POINT));
    }
}
~~~

### 10.1. Biên dịch và chạy

Với **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 StringMatchingUnitsDemo.java
java StringMatchingUnitsDemo
~~~

**Stdout dự kiến:**

~~~text
Banana UTF16: [1, 3]
Banana code points: [1, 3]
Overlap: [0, 1, 2]
Lengths UTF16/code points/UTF8: 6/4/10
Emoji UTF16: [1, 4]
Emoji code points: [1, 3]
Emoji CP as UTF16: [1, 4]
Emoji CP as UTF8 bytes: [1, 6]
Empty UTF16: [0, 1, 2, 3, 4, 5, 6]
Empty code points: [0, 1, 2, 3, 4]
Low surrogate UTF16: [2, 5]
Low surrogate code points: []
Malformed pattern rejected: true
Before NFC: []
After NFC: [3]
Case sensitive: [4]
Both empty: [0]
Longer pattern: []
~~~

### 10.2. Ý nghĩa của các phương thức

**symbols:** hai cách chuyển Java String thành dãy int[] ký hiệu. UTF16 lưu từng charAt; CODE_POINT sử dụng codePoints(). Mọi độ dài n,m trong KMP lấy từ hai mảng này, không trộn với độ dài của biểu diễn khác.

**buildLps:** mỗi giá trị lps[i] là độ dài tiền tố thực sự đồng thời là hậu tố của prefix kết thúc tại i. Nó chỉ so số nguyên bằng nhau và hoạt động không phụ thuộc bảng chữ cái lớn hay nhỏ.

**kmp:** mẫu rỗng trả mọi ranh giới; mẫu không rỗng giữ trạng thái tiền tố sau mỗi match để tìm overlap. Kết quả luôn theo **đơn vị của mảng đầu vào**.

**codePointBoundariesUtf16:** xây bảng từ code-point boundary sang UTF-16 boundary. Với "A😀B😀" map là [0,1,3,4,6]; matches [1,3] được chuyển thành [1,4].

**codePointBoundariesUtf8:** kiểm tra đầu vào hợp lệ, lấy từng code point và cộng số byte thực khi mã hóa UTF-8. Với "A😀B😀", map byte là [0,1,5,6,10], nên hai vị trí emoji là [1,6]. Dùng String đoạn nhỏ cho dễ hiểu; nếu phải xử lý file khổng lồ, có thể dùng decoder/encoder streaming và giữ offset gốc ngay trong pipeline.

**requireWellFormedUtf16:** high surrogate bắt buộc phải được theo ngay bởi low surrogate; low surrogate không được đứng lẻ. Các phương thức tìm theo raw UTF16 vẫn cho phép chuỗi malformed theo ngữ nghĩa code unit, nhưng phương thức xuất offset UTF-8 nghiêm ngặt sẽ từ chối.

**Low surrogate example:** mẫu là riêng low surrogate, không phải emoji Unicode hoàn chỉnh. Nó khớp hai code unit [2,5], nhưng không khớp một code point nào của text hợp lệ. Điều này có chủ ý để làm rõ hợp đồng.

**Normalizer:** không nằm trong KMP. Caller chỉ chuẩn hóa khi yêu cầu equivalence rõ ràng; offset sau NFC thuộc về normalizedText, **không mặc định thuộc text gốc**.

### 10.3. Tên kiểu kết quả nên nói rõ đơn vị

API chỉ trả List<Integer> dễ bị gọi nhầm. Trong chương trình:
- findAll(..., UTF16) → **UTF-16 offsets**.
- findAll(..., CODE_POINT) → **code-point offsets**.
- codePointMatchesAsUtf16 → match trên code point nhưng trả **UTF-16 offsets**.
- codePointMatchesAsUtf8Bytes → match trên code point nhưng trả **UTF-8 byte offsets**.

Khi thiết kế thư viện lớn, có thể định nghĩa các record riêng như Utf16Offset, CodePointOffset, ByteOffset, để hệ thống kiểu ngăn sử dụng nhầm một số nguyên ở hai hệ tọa độ.

## 11. Độ phức tạp thực tế

Với n,m là số phần tử **trong dãy đã chọn**:
- Dựng LPS O(m).
- KMP quét O(n).
- Tổng O(n+m) phép so sánh.
- Bộ nhớ riêng LPS O(m), danh sách k kết quả O(k).

**Chương trình Java ở đây** chuyển cả text và pattern sang int[], tốn thêm O(n+m) thời gian/bộ nhớ. Đó là khác biệt giữa độ phức tạp cốt lõi KMP và một pipeline triển khai cụ thể.

Bảng cp→UTF-16 có O(n) ranh giới, xây qua từng code point. Bảng cp→UTF-8 có thêm chi phí mã hóa các đoạn một code point và bộ nhớ O(n). Với dữ liệu malformed, code báo lỗi thay vì âm thầm trả offset dựa trên ký tự thay thế.

Một giải pháp streaming có thể tránh giữ toàn bộ text trong mảng; nhưng nếu cần trả tất cả match, bản thân kết quả có thể cần O(k) bộ nhớ, với k≤n+1.

**Không nói KMP O(n+m) theo byte** nếu n,m trong chứng minh là code point; phải gọi tên đơn vị mỗi khi diễn giải hiệu năng.

## 12. Matching theo grapheme hoặc token cần tiền xử lý riêng

KMP chung có thể chạy trên dãy **bất kỳ ký hiệu**. Nếu mục tiêu là grapheme:
1. Chọn rule set và phiên bản Unicode rõ ràng.
2. Phân đoạn cả text và pattern thành các extended grapheme cluster.
3. Xác định phép bằng nhau giữa các cụm: exact hay sau chuẩn hóa.
4. Chuyển mỗi cụm sang một ID hoặc dùng so sánh token.
5. Chạy naive/KMP trên dãy cụm.
6. Lưu span gốc của từng cụm để chuyển kết quả về vị trí trong String hoặc byte stream.

Nếu mục tiêu là token:
1. Chạy cùng tokenizer/chính sách tiền xử lý trên text và pattern.
2. Giữ offset gốc cho từng token.
3. KMP trên token ID.
4. Kết quả trả về **token index** hoặc span nguồn được ánh xạ.

Tuyệt đối không nhầm “code point” với “grapheme” hoặc “token”. Một chuỗi rất dài theo code point có thể ngắn hơn nhiều theo grapheme; một câu dài theo char có thể ngắn hơn theo token.

## 13. Kiểm thử đúng ngữ nghĩa và offset

Có hai loại kiểm thử bổ sung:

**Kiểm thử thuật toán:** so KMP với naive chạy trên **cùng dãy ký hiệu**. Cả hai phải trả cùng danh sách match, kể cả overlap, empty pattern và pattern dài hơn text. Không cần ép danh sách UTF16 và code point giống nhau vì chúng có đơn vị khác.

**Kiểm thử chuyển đổi offset:** với một code-point index k hợp lệ:
- mapUtf16[0]=0, mapUtf16[codePointCount]=String.length().
- mapUtf16[k] nằm trên ranh giới code point, không giữa surrogate pair.
- mapUtf8[0]=0, mapUtf8[codePointCount]=tổng byte UTF-8.
- Hai map tăng đơn điệu khi có ký hiệu thật.
- Nếu pattern dài m code point khớp tại k, đoạn gốc UTF16 là [mapUtf16[k],mapUtf16[k+m]) đối với **chính text đang match**.

### Các trường hợp cần có trong test

| Test | Kết quả / điều kiện |
|---|---|
| T="banana", P="ana" | [1,3] |
| T="aaaa", P="aa" | [0,1,2] |
| T="", P="" | [0] |
| T="ab", P="abc" | [] |
| Text "A😀B😀", mẫu 😀 | UTF16 [1,4], code point [1,3] |
| Cùng match emoji theo byte | UTF-8 [1,6] |
| Mẫu low surrogate đứng lẻ | UTF16 [2,5], code point [] |
| Text "café", P=e+dấu | Direct [], sau NFC [3] |
| T="Javajava", P="java" | [4] nếu phân biệt hoa/thường |
| Pattern có tiền tố/hậu tố lặp | LPS fallback vẫn tìm đủ |
| Kết quả sau normalize | Được diễn giải trên text đã biến đổi |

Có thể sinh các String ngẫu nhiên từ dãy ký hiệu thử gồm 'a','b','c','é', dấu kết hợp U+0301, emoji U+1F600 và ZWJ U+200D, rồi so **KMP với brute-force naive** trên cả dãy UTF-16 và dãy code point. Đây là cách phát hiện bug unit mismatch mà chỉ test ASCII không thấy.

Khi làm so khớp với Unicode phức tạp hơn, cần thêm các bộ kiểm thử chính thức từ phiên bản Unicode/rule set đã chọn, đặc biệt cho grapheme segmentation và locale/case folding.

## 14. Những lỗi phổ biến

1. **Không định nghĩa text T, mẫu P và bảng chữ cái Σ**, khiến đơn vị ký hiệu mơ hồ.
2. **Dùng độ dài byte làm số phần tử code point** hoặc ngược lại.
3. **Gọi String.length() là số Unicode code point**, sai khi có emoji ngoài BMP.
4. **Cho rằng Java char luôn là một ký tự hiển thị**, sai với surrogate và dấu kết hợp.
5. **Cho rằng một code point luôn là một grapheme**, sai với emoji ZWJ hoặc dấu kết hợp.
6. **Đưa code-point index vào String.substring**, cắt nhầm offset UTF-16.
7. **Nhân code-point index với 2 hoặc 4 để đổi hệ**, không đúng với mã hóa biến độ dài.
8. **Không kiểm tra surrogate đứng lẻ**, để bộ mã hóa UTF-8 thay dữ liệu lỗi mà không báo.
9. **Cho phép char-level match trúng low surrogate rồi xem đó là match Unicode hoàn chỉnh**.
10. **Bỏ qua mẫu rỗng**, gây lỗi vòng lặp hoặc trả sai số ranh giới.
11. **Không trả overlap**, bỏ mất match "ana" tại 3 hoặc "aa" tại 1.
12. **Trong KMP đặt j=0 sau khi khớp hết**, làm mất overlap.
13. **Trong KMP thiếu lps fallback khi mismatch**, làm sai hoặc tăng chi phí.
14. **Tính LPS như tiền tố bằng toàn bộ đoạn**, phá định nghĩa proper prefix.
15. **Normalize chỉ một phía** hoặc normalize với hai dạng khác nhau.
16. **Normalize xong trả offset như offset nguồn gốc**, không giữ ánh xạ vị trí.
17. **Dùng lower-case không xét locale rồi cho rằng là Unicode case folding đầy đủ**.
18. **Coi ký tự giống hình đồng nghĩa cùng mã**, bỏ qua vấn đề homoglyph.
19. **Dùng regex cho pattern literal nhưng không quote ký tự đặc biệt**, khiến dấu '.' hoặc '*' đổi nghĩa.
20. **Dùng BreakIterator mà không kiểm tra rule set/phiên bản Unicode**, rồi khẳng định mọi emoji được tách theo extended grapheme mới nhất.
21. **Tách theo dấu cách như tokenizer chung cho mọi ngôn ngữ**, làm sai ranh giới từ.
22. **So KMP trên code point với oracle trên UTF-16 và yêu cầu index bằng nhau**, tạo false failure.
23. **Cấp phát bảng theo toàn không gian Unicode không cần thiết** khi KMP chỉ cần LPS.
24. **Bỏ chi phí bản đồ offset** khi chuyển rất nhiều match sang tọa độ khác.
25. **Không kiểm tra text rỗng, pattern dài hơn text và pattern toàn ký hiệu lặp**.
26. **Nhầm first occurrence với all occurrences**, làm hợp đồng API thay đổi.
27. **Không nêu offset đầu ra cho caller**, khiến một số nguyên đúng bị dùng ở hệ sai.
28. **Cho rằng không phân biệt hoa/thường chỉ là ASCII lower-case**, dù dữ liệu Unicode có quy tắc phức tạp.
29. **Nhầm UTF-8 byte offset với UTF-16 offset vì cả hai là int**, trong khi ý nghĩa hoàn toàn khác.
30. **Không lưu provenance sau tokenize/normalize**, không thể tô sáng chính xác văn bản gốc.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** T và P trong bài tìm kiếm chuỗi là gì?

**Đáp án:** Hai dãy ký hiệu thuộc bảng chữ cái Σ đã chọn; P xuất hiện tại i nếu các ký hiệu liên tiếp T[i..i+m) đúng bằng P.

**Câu 2.** Alphabet có bắt buộc là A–Z không?

**Đáp án:** Không. Có thể dùng byte, bit, UTF-16, code point, grapheme cluster hoặc token.

**Câu 3.** Vì sao "ana" trong "banana" có hai kết quả?

**Đáp án:** Vì hai match tại 1 và 3 chồng lấn, và đặc tả cho phép báo tất cả match.

**Câu 4.** Pattern rỗng có bao nhiêu match?

**Đáp án:** Theo quy ước bài, n+1 tại mọi ranh giới của n ký hiệu.

**Câu 5.** Java String.length() đếm gì?

**Đáp án:** Số UTF-16 code unit, không phải số code point hay grapheme.

**Câu 6.** Text "A😀B😀" có bao nhiêu đơn vị?

**Đáp án:** 6 UTF-16 code unit, 4 code point, 10 byte UTF-8.

**Câu 7.** Vì sao hai emoji ở vị trí UTF16 [1,4] nhưng code point [1,3]?

**Đáp án:** Mỗi emoji ngoài BMP dùng hai code unit nhưng chỉ một code point.

**Câu 8.** Low surrogate đứng lẻ có là một Unicode scalar value không?

**Đáp án:** Không. Raw UTF-16 matching có thể tìm nó như char đơn lẻ, nhưng đó không phải ký tự Unicode hợp lệ.

**Câu 9.** Grapheme khác code point?

**Đáp án:** Một grapheme có thể gồm nhiều code point, ví dụ e+dấu kết hợp hoặc emoji ghép bằng ZWJ.

**Câu 10.** Vì sao hai dạng mã hóa của é không exact-match?

**Đáp án:** Dãy code point khác nhau. Có thể chuẩn hóa cả T và P về NFC/NFD nếu bài muốn canonical equivalence.

**Câu 11.** Offset sau NFC có chắc trỏ đúng text gốc không?

**Đáp án:** Không. Chuẩn hóa có thể thay độ dài; phải giữ map hoặc trả offset thuộc text đã chuẩn hóa.

**Câu 12.** KMP dùng LPS để làm gì?

**Đáp án:** Tái sử dụng tiền tố mẫu vẫn có thể trùng hậu tố text đã duyệt, không cần so lại từ đầu sau mismatch.

**Câu 13.** Vì sao sau match KMP đặt j=lps[m−1]?

**Đáp án:** Để tiếp tục tìm các match chồng lấn.

**Câu 14.** Độ phức tạp KMP là gì?

**Đáp án:** O(n+m) phép so sánh ký hiệu, O(m) bộ nhớ LPS; n,m phải đo theo cùng đơn vị ký hiệu.

**Câu 15.** Từ code-point index k sang UTF-16 offset làm thế nào?

**Đáp án:** Dùng offsetByCodePoints(0,k) hoặc map cp boundary→UTF16 boundary tạo trước.

**Câu 16.** Regex và literal pattern khác nhau thế nào?

**Đáp án:** Regex có meta-character; KMP coi pattern là dãy ký hiệu literal. Muốn tìm literal bằng regex, dùng Pattern.quote.

**Ghi nhớ:** **Text, pattern và alphabet phải dùng cùng đơn vị so khớp**. Không đánh đồng UTF-8 byte, Java UTF-16 char, Unicode code point, grapheme cluster và token. KMP tìm exact match trong O(n+m) trên dãy ký hiệu đã chọn; **normalize, case folding, grapheme segmentation và quy đổi offset** là những bước riêng phải được quy định rõ theo yêu cầu ứng dụng.
