# So sánh chuỗi con bằng chỉ mục và dấu vân tay

**So sánh chuỗi con (substring comparison)** là thao tác xác định hai đoạn liên tiếp của chuỗi có **giống hệt nhau** hay không, đoạn nào **nhỏ hơn theo thứ tự từ điển**, hoặc chúng có **tiền tố chung dài nhất** (longest common extension / LCE) dài bao nhiêu. Nếu chỉ có một truy vấn, ta có thể duyệt từng ký tự. Nhưng khi cần hàng chục nghìn đến hàng triệu truy vấn trên **cùng một chuỗi không đổi**, việc so sánh từ đầu ở mỗi truy vấn rất tốn kém. Khi đó, nên **tiền xử lý thành chỉ mục (index)** hoặc **dấu vân tay (fingerprint/hash)**.

Bài học thuộc nhóm **Xử lý chuỗi nâng cao** của Computer Science Algorithms. Ta sẽ học cách mô tả đoạn bằng hai chỉ số, phép so sánh trực tiếp, **rolling hash đa thức** và công thức lấy hash một đoạn trong O(1), kỹ thuật **double hash** và giới hạn va chạm, so sánh thứ tự từ điển bằng tìm **LCP nhị phân**, cùng chỉ mục **suffix array + LCP (Kasai) + RMQ** để so sánh chính xác trong O(1) sau tiền xử lý. Bài có giải thích bằng chứng đúng, độ phức tạp, lỗi thường gặp và chương trình **Java 17+** độc lập, kiểm tra bằng các oracle trực tiếp và hàng nghìn truy vấn ngẫu nhiên.

## 1. Đặc tả chính xác: hai đầu chỉ số và ba loại câu hỏi

Cho chuỗi `S` dài `n`. Dùng quy ước **đoạn nửa mở**:

`S[l,r) = S[l] S[l+1] … S[r−1]`.

Với mọi truy vấn phải có:

`0 ≤ l ≤ r ≤ n`.

Độ dài đoạn là `len=r−l`; khi `l=r`, đoạn **rỗng**, và `S[n,n)` cũng hợp lệ. Quy ước [l,r) giúp nối các đoạn không chồng lên nhau, vì `S[a,c)=S[a,b)+S[b,c)` khi `a≤b≤c`.

Cho hai đoạn `A=S[a,b)` và `B=S[c,d)`. Có ba bài toán thường xuất hiện:

1. **Bằng nhau (equality):** cả hai có cùng độ dài và mọi ký tự tương ứng giống nhau?
2. **So sánh từ điển (lexicographic comparison):** A nhỏ hơn, bằng hay lớn hơn B?
3. **Tiền tố chung dài nhất (LCP of substrings):** có bao nhiêu ký tự đầu giống nhau trước khi một đoạn kết thúc hoặc xuất hiện khác biệt?

Ví dụ với `S="banana"`:

| Đoạn thứ nhất | Đoạn thứ hai | Kết quả |
| --- | --- | --- |
| `S[1,4)="ana"` | `S[3,6)="ana"` | Bằng nhau |
| `S[0,3)="ban"` | `S[2,5)="nan"` | "ban" nhỏ hơn "nan" |
| `S[1,6)="anana"` | `S[3,6)="ana"` | Có LCP dài 3; "ana" nhỏ hơn "anana" |
| `S[2,2)=""` | `S[6,6)=""` | Hai đoạn rỗng bằng nhau |

**Không được chỉ so hash mà quên độ dài.** Dù hai chuỗi có fingerprint giống nhau, kết luận bằng nhau chỉ có thể được xem xét khi độ dài bằng nhau.

### Thứ tự từ điển theo đơn vị nào?

Bài và code Java 17 dùng **UTF-16 code unit**, đúng thứ tự `String.compareTo` và chỉ số `String.substring`. Một emoji ngoài BMP chiếm hai `char`; chương trình vẫn có thể so đoạn cắt giữa surrogate pair nếu caller cung cấp chỉ số như vậy. Đây là **ngữ nghĩa dãy mã Java**, không phải phép so sánh theo Unicode grapheme cluster hoặc thứ tự từ điển của tiếng Việt theo ngôn ngữ học.

Nếu yêu cầu so **code point, grapheme cluster, không phân biệt hoa/thường hoặc tương đương Unicode NFC**, phải định nghĩa và tiền xử lý theo đơn vị/tính tương đương đó trước; không thể đổi nhãn kết quả UTF-16 thành kết quả grapheme một cách tùy tiện.

## 2. Cách đơn giản: so sánh trực tiếp từ hai vị trí

Nếu đoạn A và B cần kiểm tra **bằng nhau**, trước tiên so độ dài; nếu khác nhau, trả false. Nếu bằng nhau, so lần lượt:

~~~text
DIRECT_EQUAL(S, a, b, c, d):
    require 0 <= a <= b <= n and 0 <= c <= d <= n
    if b-a != d-c: return false
    for k = 0 to (b-a)-1:
        if S[a+k] != S[c+k]:
            return false
    return true
~~~

Với so sánh từ điển:

~~~text
DIRECT_COMPARE(S, a, b, c, d):
    m = min(b-a, d-c)
    for k = 0 to m-1:
        if S[a+k] < S[c+k]: return -1
        if S[a+k] > S[c+k]: return +1
    return sign((b-a) - (d-c))
~~~

Quy tắc: ở **vị trí khác đầu tiên**, đoạn có ký tự nhỏ hơn đứng trước. Nếu mọi ký tự của đoạn ngắn đều trùng, **đoạn ngắn là tiền tố** và đứng trước đoạn dài. Hai đoạn rỗng bằng nhau; đoạn rỗng đứng trước đoạn không rỗng.

**Chi phí:** tối đa `O(min(|A|,|B|))` lần so ký tự cho so từ điển; với equality cùng độ dài k, tối đa O(k). Trường hợp khác ngay ký tự đầu có thể rẻ, nhưng nếu có nhiều truy vấn trên đoạn dài giống nhau, chi phí lặp lại lớn.

### Khi nào direct là lựa chọn tốt?

- Chỉ vài truy vấn, hoặc các đoạn cực ngắn.
- Muốn kết quả **chính xác tuyệt đối**, không cần cấu trúc chỉ mục.
- Chuỗi thay đổi sau mỗi truy vấn, không đáng tiền xử lý.
- Dùng làm **oracle** độc lập để kiểm chứng thuật toán tối ưu.

Không phải mọi bài toán chuỗi đều cần rolling hash hoặc suffix array. Chỉ mục có chi phí tạo và bộ nhớ cần cân nhắc.

## 3. Chỉ số đoạn [l,r) chính là “index” đơn giản nhất

Để biểu diễn một chuỗi con, thường **không cần tạo String mới**. Thay vào đó, lưu bộ ba:

`(S, l, r)`.

Nhiều truy vấn có thể dùng cùng một chuỗi gốc và chỉ thay cặp chỉ số. Ưu điểm:

- Lấy độ dài trong O(1): `r-l`.
- Không phải cấp phát hoặc sao chép nội dung cho mỗi truy vấn.
- Không bị nhầm đoạn kết thúc bao gồm r hay không.
- Dễ dùng cho hash tiền tố, suffix-index và kiểm tra các đoạn chồng lấn.

**Ví dụ:** `S="aaaaa"`, `S[0,3)="aaa"`, `S[1,4)="aaa"` và `S[2,5)="aaa"` bằng nhau dù **chồng lấn**. Không được loại trừ so sánh chỉ vì hai khoảng có chung một phần ký tự; chúng được phép nằm trong cùng nguồn dữ liệu.

**Lưu ý về “index”:** trong thuật toán chuỗi, từ *index* còn chỉ một **cấu trúc tra cứu** như suffix array, suffix tree hay suffix automaton. Phần sau xây suffix array để trả lời LCE nhanh; nó khác với việc chỉ lưu hai vị trí [l,r).

## 4. Dấu vân tay đa thức (polynomial rolling hash)

Muốn so sánh nhiều đoạn nhanh, ta có thể mã hóa một chuỗi con thành một **giá trị hash**.

Cho cơ số `B` và mô-đun nguyên tố `M`. Mỗi đơn vị mã `x_i` được chuyển thành một số `v_i`, ở đây:

`v_i = (int)S.charAt(i) + 1`.

Cộng 1 giúp đơn vị mã 0 không trở thành hệ số 0; đây là quy ước mã hóa, không phải Unicode normalization.

Hash của đoạn `S[l,r)` dài k:

`H(l,r) = (v_l·B^(k−1) + v_(l+1)·B^(k−2) + ... + v_(r−1)) mod M`.

Với đoạn rỗng k=0, hash là 0. Ta tiền xử lý hai mảng:

- `pow[t]=B^t mod M`.
- `prefix[i]` là hash của `S[0,i)`.

Khởi tạo:

`pow[0]=1` và `prefix[0]=0`.

Cập nhật từ trái sang phải:

`pow[i+1] = pow[i]·B mod M`.

`prefix[i+1] = (prefix[i]·B + v_i) mod M`.

### Công thức tách một đoạn trong O(1)

Từ tính chất hash đa thức:

`prefix[r] = prefix[l]·B^(r−l) + H(l,r) (mod M)`.

Suy ra:

`H(l,r) = (prefix[r] − prefix[l]·pow[r−l]) mod M`.

Trong Java, phép trừ có thể cho số âm. Vì cả hai số hạng sau khi modulo thuộc `[0,M−1]`, tính an toàn theo dạng:

~~~java
long product = prefix[l] * power[r - l] % MOD;
long sliceHash = (prefix[r] - product + MOD) % MOD;
~~~

Đây là **mảnh mã**, các biến `prefix, power, MOD, l, r` phải được khởi tạo. Chương trình đầy đủ ở mục 13 triển khai riêng cho hai mô-đun.

**Lỗi hay gặp:** dùng `prefix[r]−prefix[l]` mà không nhân `B^(r−l)`. Cách đó không loại bỏ đúng đóng góp của tiền tố khi hash phụ thuộc vị trí các ký tự.

### Ví dụ tính bằng số nhỏ

Giả sử chỉ minh họa với `B=3`, `M=101`, chuỗi hai chữ "ab", với `v('a')=98`, `v('b')=99`:

`H("ab")=(98·3+99) mod 101=393 mod 101=90`.

Hash của `"b"` là `99 mod 101=99`. Nếu đã biết prefix[2] và prefix[1], lấy đoạn [1,2) bằng:

`(prefix[2]−prefix[1]·pow[1]) mod 101`

và nhận đúng 99 sau chuẩn hóa modulo. Đây là minh họa cho đại số loại tiền tố; **không dùng M=101 làm hash production** vì va chạm rất dễ.

## 5. Vì sao cần double hash?

Hash biến một tập rất lớn các chuỗi khả dĩ vào tập giá trị có kích thước M. Theo **nguyên lý chuồng bồ câu**, nếu số chuỗi khả dĩ nhiều hơn số hash thì chắc chắn có những chuỗi khác nhau nhận cùng giá trị: **collision**.

- Nếu hai chuỗi thực sự bằng nhau và dùng cùng quy ước B,M, hash **chắc chắn bằng nhau**.
- Nếu hai chuỗi khác nhau nhưng hash bằng nhau, đó là **va chạm**.
- Vì vậy hash bằng nhau **không phải chứng minh toán học** rằng hai chuỗi bằng nhau.

### Double hash

Tính hai fingerprint độc lập về mô-đun:

`F(l,r)=(H_1(l,r),H_2(l,r),r−l)`,

ví dụ:

- `M1=1 000 000 007`.
- `M2=1 000 000 009`.
- `B=911 382 323` (nhỏ hơn cả hai mô-đun).

So hai fingerprint đòi **cả hai hash và độ dài bằng nhau**. Việc dùng hai mô-đun khác nhau giảm nguy cơ va chạm ngẫu nhiên trong nhiều bối cảnh, nhưng **không loại bỏ hoàn toàn khả năng va chạm**; xác suất còn phụ thuộc mô hình chọn dữ liệu/cơ số và kẻ tấn công có thể cố ý tạo collision.

Cơ số được cố định trong demo để đầu ra và test tái lập. Trong môi trường đối kháng, cần xem xét **randomized base/seed phù hợp** (cùng thống nhất giữa các đối tượng được so) hoặc dùng chỉ mục/so sánh **chính xác tuyệt đối**, không hứa hẹn double hash sẽ chống mọi tấn công.

### Ví dụ collision cực nhỏ

Với hash một ký tự `v=(char+1) mod 5`:

- `hash("a")=98 mod 5=3`.
- `hash("f")=103 mod 5=3`.

Hai chuỗi **khác nhau** có cùng hash! Chương trình in `toyCollision=true exactEqual=false`. Đây là hash toy có mô-đun 5 để nhìn thấy va chạm, **không phải collision được chứng minh cho double hash production**.

### Kết quả cần chính xác tuyệt đối thì làm sao?

Có ba chiến lược:

1. **Hash làm bộ lọc:** nếu fingerprint khác nhau thì chắc chắn không bằng; nếu giống nhau, gọi `regionMatches`/so trực tiếp để **xác minh**. Phép xác minh có thể tốn O(k) trong các truy vấn cần thiết, nhưng cho đáp án đúng tuyệt đối.
2. **Suffix array + LCP + RMQ:** tiền xử lý sâu hơn để trả lời LCE và equality **không có rủi ro hash**.
3. **Dùng cấu trúc exact khác** tùy yêu cầu: suffix tree, deterministic LCE index, hoặc lưu trực tiếp các chuỗi đã chuẩn hóa.

**Không dùng fingerprint làm khóa duy nhất cho dữ liệu an toàn/bảo mật** nếu một va chạm có thể gây hậu quả; rolling hash của thuật toán chuỗi không phải hàm băm mật mã.

## 6. So sánh bằng dấu vân tay: bằng nhau và thứ tự từ điển

### 6.1. Kiểm tra equality

Với hai đoạn `A=S[a,b)` và `B=S[c,d)`:

~~~text
HASH_EQUAL(A, B):
    if b-a != d-c: return false
    return doubleHash(a,b) == doubleHash(c,d)
~~~

Sau tiền xử lý O(n), mỗi lần lấy fingerprint O(1); một equality query có **O(1)** thời gian hash (đổi lại là **kết quả xác suất** về độ chính xác nếu tin hash mà không đối chiếu nội dung).

Khi cần exact equality:

~~~text
VERIFIED_EQUAL(A, B):
    if b-a != d-c: return false
    if doubleHash(a,b) != doubleHash(c,d): return false
    return DIRECT_EQUAL(A, B)
~~~

Nếu hash khác, không có trường hợp bằng nhau thật bị loại, vì hash của hai chuỗi bằng nhau bắt buộc trùng. Nếu hash giống, kiểm chứng trực tiếp loại mọi va chạm.

### 6.2. So sánh từ điển không thể chỉ so thứ tự hash

**Giá trị số hash không có quan hệ thứ tự từ điển.** Không được viết `hash(A)<hash(B) ⇒ A<B`. Hash chỉ hỗ trợ **kiểm tra bằng nhau của các tiền tố**.

Để so thứ tự từ điển:

1. Đặt `limit=min(|A|,|B|)`.
2. Tìm độ dài tiền tố chung dài nhất `k∈[0,limit]` bằng **binary search**: một tiền tố độ dài x của A và B có fingerprint bằng nhau không?
3. Nếu `k=limit`, đoạn ngắn hơn đứng trước; nếu bằng chiều dài thì hai đoạn bằng nhau.
4. Nếu `k<limit`, so `S[a+k]` với `S[c+k]` — **ký tự khác đầu tiên** — để quyết định thứ tự.

Giả thiết “hai tiền tố có fingerprint giống nhau ⇒ giống nhau thật” là **xác suất**, do có thể xảy ra collision. Vì vậy cả giá trị LCP lẫn kết quả so từ điển của phương pháp hash này **không có bảo đảm tuyệt đối**. Nếu yêu cầu chính xác tuyệt đối, dùng suffix-index LCE hoặc direct compare để xác minh.

### Tại sao tìm LCP được bằng binary search?

Mệnh đề “hai tiền tố độ dài x bằng nhau” có dạng **đúng với tất cả x≤k** và **sai với tất cả x>k**, khi phép kiểm tra equality là **chính xác**. Với hash, ta dựa vào giả định không có collision ở các tiền tố đang xét. Phương pháp binary search tìm k trong O(log limit) lượt, mỗi lượt truy vấn hash O(1).

Nếu sai khác ngay ký tự đầu, k=0; nếu đoạn ngắn là tiền tố đoạn dài, k bằng độ dài đoạn ngắn. Khi limit=0, LCP bằng 0 và so theo độ dài.

## 7. Chỉ mục suffix array: so sánh chính xác theo hậu tố

**Hậu tố (suffix)** tại vị trí i là `S[i,n)`. **Suffix array (SA)** là danh sách các vị trí bắt đầu hậu tố, được sắp theo thứ tự từ điển của các hậu tố.

Với `S="banana"`:

~~~text
Suffix tại 0: banana
Suffix tại 1: anana
Suffix tại 2: nana
Suffix tại 3: ana
Suffix tại 4: na
Suffix tại 5: a

Sắp từ điển:
SA[0] = 5 -> a
SA[1] = 3 -> ana
SA[2] = 1 -> anana
SA[3] = 0 -> banana
SA[4] = 4 -> na
SA[5] = 2 -> nana

SA = [5, 3, 1, 0, 4, 2]
~~~

Tạo mảng `rank[pos]` là vị trí của hậu tố bắt đầu tại `pos` trong SA. Từ đây, biết thứ tự hậu tố trong O(1). Nhưng **rank của hậu tố không đủ để trực tiếp so hai chuỗi con có độ dài giới hạn**, vì một đoạn có thể là **tiền tố** của đoạn kia dù thứ tự hậu tố kéo dài sau đoạn ấy.

Ví dụ `S[1,4)="ana"` và `S[3,6)="ana"` bằng nhau, mặc dù hậu tố tại 1 là "anana" và tại 3 là "ana", có rank khác nhau. Cần thêm **LCP/LCE**.

## 8. Mảng LCP kề nhau và truy vấn min (RMQ)

Cho SA đã sắp. Định nghĩa:

`adjLCP[k] = LCP(S[SA[k],n),S[SA[k+1],n))`.

Với `banana`:

~~~text
SA       = [5, 3, 1, 0, 4, 2]
adjLCP   = [1, 3, 0, 0, 2]

"a"     vs "ana"     -> 1
"ana"   vs "anana"   -> 3
"anana" vs "banana"  -> 0
"banana"vs "na"      -> 0
"na"    vs "nana"    -> 2
~~~

**Tính chất nền tảng:** nếu hai hậu tố tại vị trí i,j có rank SA lần lượt p<q, thì:

`LCE(i,j) = min(adjLCP[p],adjLCP[p+1],...,adjLCP[q−1])`.

Khi i=j, LCE là `n−i`. Nếu một hậu tố bắt đầu tại n thì nó rỗng, LCE bằng 0 trừ trường hợp hai vị trí cùng n (cũng 0).

### Vì sao min LCP giữa hai rank là đúng?

Các hậu tố đứng cạnh nhau trong thứ tự từ điển có tiền tố chung được ghi trong adjLCP. Nếu mọi cặp hậu tố kề nhau từ rank p tới q đều chung ít nhất k ký tự, thì **tất cả hậu tố trong khoảng** chia sẻ tiền tố k ấy, nên hai đầu cũng chia sẻ ít nhất k. Ngược lại, nếu hai hậu tố đầu-cuối chia sẻ k ký tự, mọi hậu tố nằm **giữa chúng trong thứ tự từ điển** cũng phải bắt đầu bằng tiền tố k; nếu không, nó sẽ nằm ngoài khoảng từ điển. Vì vậy tiền tố chung hai đầu chính bằng **LCP kề nhau nhỏ nhất trên khoảng rank**.

### Kasai xây adjLCP trong O(n)

Sau khi có SA và rank, thuật toán **Kasai** duyệt các vị trí bắt đầu hậu tố theo thứ tự vị trí gốc:

1. Với hậu tố tại i, lấy hậu tố kế tiếp trong SA là `j=SA[rank[i]+1]`.
2. So từ độ dài tiền tố chung hiện tại h.
3. Ghi `adjLCP[rank[i]]=h`.
4. Khi chuyển từ hậu tố bắt đầu tại i sang i+1, có thể bắt đầu với `max(0,h−1)` thay vì so lại từ 0, vì nếu hai hậu tố bắt đầu bằng h ký tự giống nhau thì bỏ ký tự đầu vẫn còn ít nhất h−1 ký tự giống nhau.

Do h tăng nhiều nhất n lần trong toàn lượt và giảm có kiểm soát, Kasai chạy **O(n)** thời gian và O(n) không gian sau SA.

### Sparse table cho RMQ O(1)

Dựng **sparse table** trên `adjLCP` để trả lời giá trị nhỏ nhất của một khoảng:

`min(adjLCP[L..R))`.

Lưu `st[k][i]` là min trên đoạn dài `2^k` bắt đầu tại i. Công thức:

`st[0][i]=adjLCP[i]`.

`st[k][i]=min(st[k−1][i],st[k−1][i+2^(k−1)])`.

Với khoảng dài t>0, đặt `k=floor(log2(t))` và lấy min hai đoạn độ dài `2^k` từ hai đầu (có thể chồng lấn). Phép min **idempotent** nên chồng lấn không làm sai kết quả.

- Tiền xử lý RMQ: O(n log n) thời gian, O(n log n) bộ nhớ.
- Mỗi LCE giữa hai hậu tố: **O(1)** qua một RMQ.
- LCP hai chuỗi con: `min(|A|,|B|,LCE(a,c))`.
- Equality hai chuỗi con: chiều dài bằng nhau và LCP đoạn bằng chiều dài.
- Lex order: nếu LCP đoạn bằng độ dài đoạn ngắn, so chiều dài; nếu không, so hai code unit ở vị trí khác đầu tiên.

**Kết quả exact, không có va chạm hash.**

## 9. Xây suffix array trong Java theo prefix doubling

Có nhiều thuật toán xây SA với độ phức tạp khác nhau. Để ưu tiên mã dễ hiểu, chương trình demo sử dụng **prefix doubling**:

1. Khởi tạo rank của hậu tố tại i theo code unit `S[i]`.
2. Với độ dài bước `k=1,2,4,8,...`, sắp các vị trí i theo cặp khóa:

   `(rank[i], rank[i+k])`

   với thành phần thứ hai là `−1` nếu vượt n (sentinel nhỏ hơn mọi rank hợp lệ).

3. Gán rank mới tăng dần cho các khóa phân biệt; nếu đã có n rank phân biệt, dừng.
4. Sau khi chiều dài tiền tố đã đủ để phân biệt mọi hậu tố, SA chứa thứ tự chính xác.

**Vì sao phải có sentinel?** Trong so sánh hậu tố, một hậu tố kết thúc sớm hơn và là tiền tố của hậu tố khác phải đứng trước. Giá trị `−1` nhỏ hơn mọi rank hợp lệ tạo đúng thứ tự ấy.

Mã minh họa dùng `Arrays.sort(Integer[], comparator)` cho mỗi vòng doubling. Mỗi vòng sắp O(n log n), có O(log n) vòng, nên:

`O(n log² n)` thời gian xây SA trong mô hình so cặp rank O(1).

Kasai thêm O(n), sparse table thêm O(n log n). Tổng tiền xử lý của **demo** là **O(n log² n)**; bộ nhớ **O(n log n)** do RMQ. Có những cách xây SA hiệu quả hơn, nhưng không nên gán sai cận O(n log n) cho chính cài đặt đang dùng `Arrays.sort` ở mỗi vòng.

## 10. So sánh ba cách một cách thực dụng

| Thuật toán | Tiền xử lý (một chuỗi dài n) | Equality hai đoạn | Lex comparison hai đoạn | Độ chính xác |
| --- | --- | --- | --- | --- |
| So trực tiếp | O(1) | O(k) khi cùng độ dài k | O(min độ dài) | Tuyệt đối |
| Double rolling hash | O(n) | O(1) theo fingerprint | O(log(min độ dài)) bằng LCP nhị phân | Xác suất, trừ khi xác minh |
| Suffix array + Kasai + RMQ | O(n log² n) trong demo | O(1) | O(1) | Tuyệt đối |

**Bộ nhớ bổ sung**: direct O(1) ngoài đầu vào/đầu ra, double hash O(n) cho tiền tố/lũy thừa, SA+LCP+sparse table O(n log n).

Khi truy vấn ít, direct thường đơn giản và rẻ. Khi nhiều truy vấn equality và đầu vào tin cậy, double hash có thể rất hiệu quả. Khi cần lượng truy vấn lớn **và đúng tuyệt đối**, suffix index có lợi, miễn chấp nhận chi phí tiền xử lý/bộ nhớ.

### Tại sao fingerprint không dùng để sắp xếp trực tiếp?

Nếu dùng giá trị hash làm khóa sắp xếp, bạn đang sắp theo số modulo, **không phải thứ tự từ điển**. Có thể dùng hash để **tìm tiền tố khác đầu tiên**, rồi so ký tự tại vị trí ấy, nhưng kể cả cách này vẫn có xác suất sai do collision. SA+LCP đưa ra thứ tự từ điển chuẩn theo code unit mà không cần hash.

## 11. Các trường hợp biên cần định nghĩa trước

### Đoạn rỗng

Nếu `a=b` và `c=d`, hai đoạn rỗng bằng nhau dù vị trí bắt đầu khác nhau. LCP hai **đoạn** bằng 0 và lex comparison bằng 0. Hash đoạn rỗng cũng phải cho giá trị thống nhất (0,0,length0).

Nếu một đoạn rỗng và đoạn kia không rỗng, equality=false; đoạn rỗng **nhỏ hơn** đoạn không rỗng.

### Đoạn chồng lấn

Ví dụ `S="aaaaa"`, ba đoạn [0,3), [1,4), [2,5) đều là "aaa". Tiền xử lý hash và LCP hoạt động bình thường dù các khoảng chồng lấn; không cần nhân bản dữ liệu hay tách riêng chuỗi.

### Đoạn tại cuối chuỗi

`S[n,n)=""` là hợp lệ. SA thông thường có **n hậu tố không rỗng**, bắt đầu ở 0..n−1; khi cần LCE(i,j), có thể thêm xử lý đặc biệt cho i=n hoặc j=n. Không đọc `rank[n]`, vì chỉ có n phần tử rank hợp lệ.

### Đoạn đầy đủ

`S[0,n)` phải được trả nguyên văn; index/rolling hash cần cho phép r=n mà không đọc `S[n]`. Với n=0, mọi truy vấn hợp lệ có [0,0).

### Chỉ số sai

Các khoảng như `[−1,2)`, `[2,1)`, `[0,n+1)` là không hợp lệ. Thay vì lặng lẽ cắt biên hoặc trả false như một chuỗi bình thường, code demo **ném IllegalArgumentException** để người gọi biết dữ liệu đầu vào sai.

### Unicode và surrogate pair

`"A🙂B🙂"` dài **6 UTF-16 code unit**; hai emoji giống nhau ở [1,3) và [4,6), so sánh chính xác bằng nhau, LCP dài 2 **theo code unit**. Hai đoạn [1,2) và [4,5) cũng bằng nhau nếu chỉ xét high-surrogate code unit — nhưng chúng **không phải hai emoji hoàn chỉnh**. Nếu API yêu cầu Unicode code point/grapheme thì phải dùng biên giới phần tử phù hợp.

### Chuẩn hóa làm thay đổi vị trí

`"é"` có thể biểu diễn khác `"e\u0301"` dù nhìn tương đương. Demo **không chuẩn hóa** và cố ý làm việc theo dãy code unit. Nếu muốn so tương đương Unicode, chuẩn hóa **trước khi tạo chỉ mục/hash** và ghi rõ index được đo trên **chuỗi đã chuẩn hóa**; khi cần offset gốc phải có ánh xạ gốc–đích tin cậy. Không được dùng trực tiếp offset sau NFC làm vị trí ban đầu khi chuỗi đổi chiều dài.

## 12. Từ mô hình đến mã: chọn API rõ ràng

Để kết quả dễ xác minh, chương trình Java có ba thành phần:

- `RollingHash`: lưu hai mảng prefix và power cho hai mô-đun; `fingerprint(l,r)`, `same(l1,r1,l2,r2)` và `compare(l1,r1,l2,r2)`.
- `SuffixIndex`: xây SA bằng prefix doubling, Kasai adjacent LCP, sparse RMQ; `lce(i,j)`, `lcpSlices`, `same`, `compare` chính xác.
- `Direct`: `directSame` và `directCompare` là oracle chính xác bằng so code unit; dùng `String.substring(...).compareTo(...)` trong kiểm thử để đối chiếu.

**Với double hash:** so fingerprint là thao tác nhanh; `verifiedSame` xác nhận trực tiếp khi hai fingerprint trùng. Riêng phương pháp `hash.compare` **không** tự trở thành exact vì LCP nhị phân cũng dựa trên hash. Nếu không được phép sai dù tỷ lệ collision cực nhỏ, dùng `SuffixIndex.compare` hoặc `directCompare`.

**Với index:** cùng một đối tượng `SuffixIndex` chỉ so các đoạn của **một chuỗi cố định** mà nó xây chỉ mục. Nếu chuỗi thay đổi, phải xây lại; nếu muốn so chéo hai văn bản, cần mô hình chung (ví dụ ghép hai chuỗi có separator an toàn) hoặc cấu trúc/thuật toán thích hợp.

## 13. Java 17+ hoàn chỉnh: fingerprint kép và suffix-index exact

Lưu tệp **`SubstringIndexFingerprintDemo.java`** bằng UTF-8:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Random;

public class SubstringIndexFingerprintDemo {
    private static void requireRange(
            String s, int l, int r) {
        if (l < 0 || r < l || r > s.length()) {
            throw new IllegalArgumentException(
                    "Invalid half-open range [" + l + "," + r + ")");
        }
    }

    static boolean directSame(String s,
            int a, int b, int c, int d) {
        requireRange(s, a, b);
        requireRange(s, c, d);
        int len = b - a;
        return len == d - c && s.regionMatches(a, s, c, len);
    }

    // Return exactly -1, 0, +1 in UTF-16 String order.
    static int directCompare(String s,
            int a, int b, int c, int d) {
        requireRange(s, a, b);
        requireRange(s, c, d);
        int lenA = b - a, lenB = d - c;
        int limit = Math.min(lenA, lenB);
        for (int k = 0; k < limit; k++) {
            char x = s.charAt(a + k);
            char y = s.charAt(c + k);
            if (x != y) return Character.compare(x, y) < 0 ? -1 : 1;
        }
        return Integer.compare(lenA, lenB);
    }

    record Fingerprint(long h1, long h2, int length) {}

    static final class RollingHash {
        // BASE*(MOD2-1) is less than Long.MAX_VALUE.
        private static final long BASE = 911_382_323L;
        private static final long MOD1 = 1_000_000_007L;
        private static final long MOD2 = 1_000_000_009L;
        private final String s;
        private final long[][] prefix;
        private final long[][] power;

        RollingHash(String s) {
            this.s = s;
            int n = s.length();
            prefix = new long[2][n + 1];
            power = new long[2][n + 1];
            power[0][0] = power[1][0] = 1L;
            for (int i = 0; i < n; i++) {
                long code = (long) s.charAt(i) + 1L;
                power[0][i + 1] = power[0][i] * BASE % MOD1;
                power[1][i + 1] = power[1][i] * BASE % MOD2;
                prefix[0][i + 1] =
                        (prefix[0][i] * BASE + code) % MOD1;
                prefix[1][i + 1] =
                        (prefix[1][i] * BASE + code) % MOD2;
            }
        }

        private long subHash(int mod, int l, int r) {
            long modulus = mod == 0 ? MOD1 : MOD2;
            long remove = prefix[mod][l] *
                    power[mod][r - l] % modulus;
            return (prefix[mod][r] - remove + modulus) % modulus;
        }

        Fingerprint fingerprint(int l, int r) {
            requireRange(s, l, r);
            return new Fingerprint(
                    subHash(0, l, r),
                    subHash(1, l, r),
                    r - l);
        }

        boolean same(int a, int b, int c, int d) {
            return fingerprint(a, b).equals(fingerprint(c, d));
        }

        boolean verifiedSame(int a, int b, int c, int d) {
            if (!same(a, b, c, d)) return false;
            // Exact verification rejects all hash collisions.
            return directSame(s, a, b, c, d);
        }

        int lcpSlices(int a, int b, int c, int d) {
            requireRange(s, a, b);
            requireRange(s, c, d);
            int lo = 0, hi = Math.min(b - a, d - c);
            while (lo < hi) {
                int mid = lo + (hi - lo + 1) / 2;
                boolean equalPrefix = fingerprint(
                        a, a + mid).equals(
                        fingerprint(c, c + mid));
                if (equalPrefix) lo = mid;
                else hi = mid - 1;
            }
            return lo;
        }

        int compare(int a, int b, int c, int d) {
            int lenA = b - a, lenB = d - c;
            int k = lcpSlices(a, b, c, d);
            int limit = Math.min(lenA, lenB);
            if (k == limit) return Integer.compare(lenA, lenB);
            return Character.compare(
                    s.charAt(a + k), s.charAt(c + k)) < 0
                    ? -1 : 1;
        }
    }

    static final class SuffixIndex {
        private final String s;
        private final int[] sa;
        private final int[] rank;
        private final int[] adjacentLcp;
        private final int[] logarithm;
        private final int[][] minimum;

        SuffixIndex(String s) {
            this.s = s;
            int n = s.length();
            sa = buildSuffixArray(s);
            rank = new int[n];
            for (int order = 0; order < n; order++)
                rank[sa[order]] = order;

            // Kasai: LCP of adjacent suffixes in SA order.
            adjacentLcp = new int[Math.max(0, n - 1)];
            int common = 0;
            for (int start = 0; start < n; start++) {
                int pos = rank[start];
                if (pos == n - 1) {
                    common = 0;
                    continue;
                }
                int other = sa[pos + 1];
                while (start + common < n &&
                        other + common < n &&
                        s.charAt(start + common) ==
                        s.charAt(other + common)) {
                    common++;
                }
                adjacentLcp[pos] = common;
                if (common > 0) common--;
            }

            int m = adjacentLcp.length;
            logarithm = new int[Math.max(2, n)];
            for (int i = 2; i < logarithm.length; i++)
                logarithm[i] = logarithm[i / 2] + 1;

            int levels = m == 0 ? 0 : logarithm[m] + 1;
            minimum = new int[levels][];
            if (m > 0) {
                minimum[0] = adjacentLcp.clone();
                for (int k = 1; k < levels; k++) {
                    int span = 1 << k;
                    int half = span >> 1;
                    minimum[k] = new int[m - span + 1];
                    for (int i = 0; i + span <= m; i++) {
                        minimum[k][i] = Math.min(
                                minimum[k - 1][i],
                                minimum[k - 1][i + half]);
                    }
                }
            }
        }

        // Prefix doubling with comparator sorting:
        // O(n log^2 n) time, not the optimized linear SA build.
        private static int[] buildSuffixArray(String s) {
            int n = s.length();
            Integer[] order = new Integer[n];
            int[] ranks = new int[n];
            for (int i = 0; i < n; i++) {
                order[i] = i;
                ranks[i] = s.charAt(i);
            }

            for (int step = 1; step < n; ) {
                final int hop = step;
                final int[] old = ranks;
                Arrays.sort(order, (x, y) -> {
                    int first = Integer.compare(old[x], old[y]);
                    if (first != 0) return first;
                    int sx = x + hop < n ? old[x + hop] : -1;
                    int sy = y + hop < n ? old[y + hop] : -1;
                    return Integer.compare(sx, sy);
                });

                int[] newer = new int[n];
                for (int i = 1; i < n; i++) {
                    int x = order[i - 1], y = order[i];
                    int sx = x + hop < n ? old[x + hop] : -1;
                    int sy = y + hop < n ? old[y + hop] : -1;
                    boolean different =
                            old[x] != old[y] || sx != sy;
                    newer[y] = newer[x] + (different ? 1 : 0);
                }
                ranks = newer;
                if (ranks[order[n - 1]] == n - 1) break;
                if (step >= n - step) break;
                step *= 2;
            }

            int[] result = new int[n];
            for (int i = 0; i < n; i++) result[i] = order[i];
            return result;
        }

        int[] suffixArray() { return sa.clone(); }
        int[] adjacentLcp() { return adjacentLcp.clone(); }

        private int rmq(int left, int right) {
            // Half-open nonempty interval [left, right).
            int span = right - left;
            int k = logarithm[span];
            return Math.min(
                    minimum[k][left],
                    minimum[k][right - (1 << k)]);
        }

        int lce(int i, int j) {
            int n = s.length();
            if (i < 0 || j < 0 || i > n || j > n)
                throw new IllegalArgumentException("Invalid suffix");
            if (i == j) return n - i;
            if (i == n || j == n) return 0;
            int x = rank[i], y = rank[j];
            return rmq(Math.min(x, y), Math.max(x, y));
        }

        int lcpSlices(int a, int b, int c, int d) {
            requireRange(s, a, b);
            requireRange(s, c, d);
            return Math.min(
                    Math.min(b - a, d - c), lce(a, c));
        }

        boolean same(int a, int b, int c, int d) {
            requireRange(s, a, b);
            requireRange(s, c, d);
            int len = b - a;
            return len == d - c &&
                    lcpSlices(a, b, c, d) == len;
        }

        int compare(int a, int b, int c, int d) {
            int k = lcpSlices(a, b, c, d);
            int lenA = b - a, lenB = d - c;
            int limit = Math.min(lenA, lenB);
            if (k == limit) return Integer.compare(lenA, lenB);
            return Character.compare(
                    s.charAt(a + k), s.charAt(c + k)) < 0
                    ? -1 : 1;
        }
    }

    static void show(String name, String s,
                     int a, int b, int c, int d) {
        RollingHash hash = new RollingHash(s);
        SuffixIndex index = new SuffixIndex(s);

        boolean exact = directSame(s, a, b, c, d);
        boolean hashOnly = hash.same(a, b, c, d);
        boolean verified = hash.verifiedSame(a, b, c, d);
        boolean indexed = index.same(a, b, c, d);
        int direct = directCompare(s, a, b, c, d);
        int usingHash = hash.compare(a, b, c, d);
        int usingIndex = index.compare(a, b, c, d);
        int lcp = index.lcpSlices(a, b, c, d);

        if (exact != verified || exact != indexed ||
                direct != usingIndex ||
                (hashOnly != exact || usingHash != direct) &&
                        s.length() < 100) {
            throw new AssertionError("Demo methods disagree");
        }

        System.out.println(name
                + " exact=" + exact
                + " hash=" + hashOnly
                + " verified=" + verified
                + " index=" + indexed
                + " lcp=" + lcp
                + " directCmp=" + direct
                + " hashCmp=" + usingHash
                + " indexCmp=" + usingIndex);
    }

    // Toy collision is NOT a collision for the double hash above.
    static int toySingleCharHash(String s) {
        if (s.length() != 1)
            throw new IllegalArgumentException(
                    "Toy function expects one UTF-16 unit");
        return (s.charAt(0) + 1) % 5;
    }

    static void checkIndexAgainstOracle(
            String s, SuffixIndex index) {
        int n = s.length();
        Integer[] oracleOrder = new Integer[n];
        for (int i = 0; i < n; i++) oracleOrder[i] = i;
        Arrays.sort(oracleOrder,
                (x, y) -> s.substring(x).compareTo(
                        s.substring(y)));
        int[] actualSA = index.suffixArray();
        int[] actualAdj = index.adjacentLcp();

        for (int k = 0; k < n; k++) {
            if (actualSA[k] != oracleOrder[k])
                throw new AssertionError("Suffix order mismatch");
            if (k + 1 < n) {
                int left = actualSA[k], right = actualSA[k + 1];
                int common = 0;
                while (left + common < n && right + common < n
                        && s.charAt(left + common) ==
                        s.charAt(right + common)) common++;
                if (actualAdj[k] != common)
                    throw new AssertionError("Kasai LCP mismatch");
            }
        }
    }

    static void randomCheck() {
        Random random = new Random(2026L);
        String[] atoms = {
            "a", "b", "n", "🙂", "é", "a\u0301"
        };
        int queries = 0;

        for (int test = 0; test < 300; test++) {
            StringBuilder builder = new StringBuilder();
            int tokenCount = random.nextInt(12);
            for (int i = 0; i < tokenCount; i++)
                builder.append(atoms[random.nextInt(atoms.length)]);
            String s = builder.toString();
            int n = s.length();

            RollingHash hash = new RollingHash(s);
            SuffixIndex index = new SuffixIndex(s);
            checkIndexAgainstOracle(s, index);

            for (int q = 0; q < 60; q++) {
                int a = random.nextInt(n + 1);
                int c = random.nextInt(n + 1);
                int b = a + random.nextInt(n - a + 1);
                int d = c + random.nextInt(n - c + 1);

                String left = s.substring(a, b);
                String right = s.substring(c, d);
                boolean expectedEq = left.equals(right);
                int expectedCmp = Integer.signum(
                        left.compareTo(right));

                if (directSame(s, a, b, c, d) != expectedEq
                        || hash.same(a, b, c, d) != expectedEq
                        || hash.verifiedSame(a, b, c, d) != expectedEq
                        || index.same(a, b, c, d) != expectedEq
                        || directCompare(s, a, b, c, d)
                                != expectedCmp
                        || hash.compare(a, b, c, d)
                                != expectedCmp
                        || index.compare(a, b, c, d)
                                != expectedCmp) {
                    throw new AssertionError(
                            "Random mismatch at test " + test);
                }

                int limit = Math.min(b - a, d - c);
                int k = 0;
                while (k < limit &&
                        s.charAt(a + k) == s.charAt(c + k)) k++;
                if (index.lcpSlices(a, b, c, d) != k ||
                        hash.lcpSlices(a, b, c, d) != k) {
                    throw new AssertionError("Random LCP mismatch");
                }
                queries++;
            }
        }

        System.out.println("randomCheck=PASS (300 strings, "
                + queries + " queries)");
    }

    public static void main(String[] args) {
        String s = "banana";
        SuffixIndex banana = new SuffixIndex(s);
        System.out.println("banana sa="
                + Arrays.toString(banana.suffixArray())
                + " lcp=" + Arrays.toString(
                        banana.adjacentLcp()));

        show("bananaSame", s, 1, 4, 3, 6);
        show("bananaLess", s, 0, 3, 2, 5);
        show("bananaPrefix", s, 1, 6, 3, 6);
        show("bananaEmpty", s, 2, 2, 6, 6);
        show("bananaEmptyLess", s, 0, 0, 1, 2);
        show("bananaEmptySame", s, 0, 0, 0, 0);

        String repeated = "aaaaa";
        SuffixIndex repeatIndex = new SuffixIndex(repeated);
        System.out.println("repeat sa="
                + Arrays.toString(repeatIndex.suffixArray())
                + " lcp=" + Arrays.toString(
                        repeatIndex.adjacentLcp()));
        show("repeatEqual", repeated, 0, 3, 2, 5);

        String unicode = "A🙂B🙂";
        show("unicodeEmoji", unicode, 1, 3, 4, 6);
        show("unicodeHighUnit", unicode, 1, 2, 4, 5);

        boolean toyCollision =
                toySingleCharHash("a") == toySingleCharHash("f");
        System.out.println("toyCollision=" + toyCollision
                + " exactEqual=" + "a".equals("f"));

        try {
            directSame("abc", 0, 4, 0, 0);
            throw new AssertionError("Expected invalid range");
        } catch (IllegalArgumentException expected) {
            System.out.println("invalidRange=rejected");
        }

        show("emptyText", "", 0, 0, 0, 0);
        randomCheck();
    }
}
~~~

### Biên dịch và chạy

Yêu cầu **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 SubstringIndexFingerprintDemo.java
java SubstringIndexFingerprintDemo
~~~

**Đầu ra kỳ vọng** với thứ tự duyệt và bộ dữ liệu được định nghĩa trong `main`:

~~~text
banana sa=[5, 3, 1, 0, 4, 2] lcp=[1, 3, 0, 0, 2]
bananaSame exact=true hash=true verified=true index=true lcp=3 directCmp=0 hashCmp=0 indexCmp=0
bananaLess exact=false hash=false verified=false index=false lcp=0 directCmp=-1 hashCmp=-1 indexCmp=-1
bananaPrefix exact=false hash=false verified=false index=false lcp=3 directCmp=1 hashCmp=1 indexCmp=1
bananaEmpty exact=true hash=true verified=true index=true lcp=0 directCmp=0 hashCmp=0 indexCmp=0
bananaEmptyLess exact=false hash=false verified=false index=false lcp=0 directCmp=-1 hashCmp=-1 indexCmp=-1
bananaEmptySame exact=true hash=true verified=true index=true lcp=0 directCmp=0 hashCmp=0 indexCmp=0
repeat sa=[4, 3, 2, 1, 0] lcp=[1, 2, 3, 4]
repeatEqual exact=true hash=true verified=true index=true lcp=3 directCmp=0 hashCmp=0 indexCmp=0
unicodeEmoji exact=true hash=true verified=true index=true lcp=2 directCmp=0 hashCmp=0 indexCmp=0
unicodeHighUnit exact=true hash=true verified=true index=true lcp=1 directCmp=0 hashCmp=0 indexCmp=0
toyCollision=true exactEqual=false
invalidRange=rejected
emptyText exact=true hash=true verified=true index=true lcp=0 directCmp=0 hashCmp=0 indexCmp=0
randomCheck=PASS (300 strings, 18000 queries)
~~~

### Diễn giải test

- **bananaSame:** cả hai đoạn là "ana", cùng chiều dài và LCP bằng 3; direct, double hash và suffix-index cho equality true và comparison 0.
- **bananaLess:** "ban" đứng trước "nan" theo code unit; khác ở ký tự đầu nên LCP=0 và kết quả so từ điển là −1.
- **bananaPrefix:** "ana" là tiền tố của "anana"; LCP=3, đoạn dài hơn đứng sau, nên so "anana" với "ana" trả +1.
- **bananaEmpty / bananaEmptySame:** hai đoạn rỗng luôn bằng nhau, kể cả ở hai vị trí khác nhau hoặc cùng một vị trí.
- **bananaEmptyLess:** đoạn rỗng đứng trước "a"; không đọc ký tự tại vị trí kết thúc n.
- **repeat:** nhiều hậu tố của "aaaaa" chia sẻ các tiền tố rất dài; SA và adjacent LCP phát triển có quy luật. Hai đoạn "aaa" chồng lấn vẫn bằng nhau.
- **unicodeEmoji:** emoji chiếm 2 đơn vị mã UTF-16; so hai đoạn [1,3) và [4,6) bằng nhau, LCP=2.
- **unicodeHighUnit:** so hai high-surrogate code unit riêng lẻ vẫn bằng nhau **theo UTF-16**, nhưng không có nghĩa đó là hai ký tự hiển thị hoàn chỉnh.
- **toyCollision:** có collision thật với mô-đun cực nhỏ 5; minh họa lý do không dùng hash bằng nhau như một chứng minh tuyệt đối.
- **invalidRange:** chỉ số ngoài chuỗi bị từ chối bằng ngoại lệ thay vì âm thầm cắt biên.
- **emptyText:** code xử lý n=0 mà không truy cập `sa[0]` hoặc RMQ rỗng.
- **randomCheck:** tạo 300 chuỗi ngẫu nhiên có thể chứa ASCII, dấu dựng sẵn, dấu kết hợp và emoji. Mỗi chuỗi có 60 truy vấn khoảng nửa mở, tổng **18.000 truy vấn**, đối chiếu từng equality/lexicographic comparison với `String.substring(...).equals/compareTo`, đối chiếu SA với cách sắp hậu tố trực tiếp, LCP kề và LCP đoạn với phép đếm ký tự trực tiếp. Vì test có thể chọn các chỉ số nằm giữa surrogate pair, nó cố ý kiểm tra **đúng ngữ nghĩa code unit** của bản demo.

### Vì sao kiểm thử đủ độc lập để phát hiện lỗi điển hình?

**Oracle thứ nhất:** `substring` tạo đoạn thật và `String.equals/compareTo` so theo quy tắc Java; các hàm tối ưu không được xem giá trị oracle trước khi tính kết quả.

**Oracle thứ hai:** sắp các hậu tố bằng `s.substring(i).compareTo(s.substring(j))` rồi so với suffix array xây theo prefix doubling. Kiểm tra thêm từng adjacent LCP bằng cách duyệt ký tự trực tiếp.

**Oracle thứ ba:** đếm tiền tố chung của từng cặp đoạn bằng vòng so `charAt`, rồi đối chiếu với LCE từ RMQ và kết quả LCP nhị phân từ hash.

**Phạm vi:** bộ test chứng minh tính nhất quán trên các dữ liệu đã thử, không thể biến rolling hash thành thuật toán exact trong mọi trường hợp. Với chuỗi dài hoặc đầu vào đối kháng, va chạm vẫn có thể tồn tại. Nếu exact correctness là yêu cầu bắt buộc, dùng suffix-index hoặc verified equality.

## 14. Tính đúng của các cấu trúc

### 14.1. Rolling hash đoạn

Bất biến sau khi xử lý i đơn vị đầu:

`prefix[i] = H(S[0,i))` và `pow[i]=B^i mod M`.

Công thức cập nhật nối v_i vào cuối nên giữ đúng định nghĩa đa thức. Khi loại phần đầu dài l, `prefix[l]·B^(r−l)` chính là đóng góp của các ký tự trước l trong hash tiền tố r; trừ nó theo modulo lấy đúng hash đoạn [l,r). Do vậy mỗi fingerprint **được tính đúng theo hàm hash đã định nghĩa**. Chứng minh này **không** suy ra “fingerprint bằng nhau ⇒ chuỗi bằng nhau”, vì hàm hash hữu hạn có collision.

### 14.2. Suffix array prefix doubling

Sau vòng có bước k, mỗi hậu tố được xếp theo **hai đoạn rank dài k**, tức tiền tố dài tới 2k. Thành phần rank ngoài biên được coi là −1 để hậu tố kết thúc sớm đứng trước. Khi không còn rank trùng hoặc độ dài xét đã bao trùm mọi hậu tố, các thứ tự rank chính là thứ tự từ điển toàn bộ hậu tố. Suy ra SA chính xác theo ký tự UTF-16.

### 14.3. Kasai và RMQ

Kasai duy trì độ dài tiền tố chung đã biết, giảm tối đa một đơn vị khi dịch vị trí hậu tố, chỉ tăng khi cần; nó tính đúng LCP của từng cặp hậu tố liền kề trong SA. Tính chất min trên khoảng rank chứng minh LCE của hai hậu tố bằng RMQ trên adjacentLCP. Sparse table tính min qua hai đoạn phủ hết khoảng yêu cầu, nên kết quả LCE chính xác.

### 14.4. Equality và lex comparison của hai chuỗi con

Nếu `k=min(|A|,|B|,LCE(a,c))`:

- Với độ dài bằng nhau k=|A|, tất cả ký tự của cả hai đoạn bằng nhau, vậy equality=true.
- Nếu k nhỏ hơn chiều dài đoạn ngắn, tại vị trí k hai đoạn khác nhau; so hai ký tự ấy cho thứ tự từ điển.
- Nếu k bằng chiều dài đoạn ngắn, đoạn ngắn là tiền tố của đoạn dài; thứ tự từ điển do độ dài quyết định.

Như vậy phương pháp suffix-index đưa ra equality, LCP và lex order **đúng tuyệt đối**, miễn chuỗi gốc và chỉ mục không bị thay đổi sau tiền xử lý.

## 15. Mở rộng và các lựa chọn khác

### 15.1. Nhiều chuỗi và so chéo

Rolling hash có thể áp dụng cho nhiều chuỗi khác nhau nếu chúng dùng **cùng cơ số, mô-đun và quy ước mã hóa**. Nếu muốn dùng suffix-array/LCE để so chéo hai văn bản, có thể xây **generalized suffix array** hoặc ghép văn bản với các ký hiệu phân cách mà không xuất hiện trong dữ liệu; cần bảo đảm ranh giới không cho LCE đi xuyên qua hai nguồn không mong muốn.

Không được gọi một `SuffixIndex` xây từ chuỗi A để so các offset trên chuỗi B; đó là hai không gian chỉ số khác nhau.

### 15.2. Cập nhật ký tự trong chuỗi

Prefix-hash và suffix array tĩnh được tính từ dữ liệu ban đầu. **Sửa một ký tự** có thể ảnh hưởng nhiều prefix hash, suffix order và adjacent LCP; không thể chỉ đổi `s` trong một đối tượng bất biến rồi tiếp tục trả lời như cũ.

Nếu có cập nhật động và truy vấn hash đoạn, có thể cân nhắc **segment tree** với phép ghép hash; chi phí mỗi update/query thường O(log n), tùy cách biểu diễn. Nhưng exact lex comparison động khó hơn nhiều, cần thiết kế riêng.

### 15.3. Tìm đoạn chung dài nhất / LCE

Sau khi có suffix-index, truy vấn `LCE(i,j)` giữa hai hậu tố bất kỳ mất O(1), qua rank+RMQ. Từ đó:

- Kiểm tra hai substring dài k bằng nhau trong O(1).
- So từ điển hai substring tùy độ dài trong O(1).
- Tính số ký tự trùng đầu của hai đoạn trong O(1).
- Hỗ trợ các thuật toán truy vấn lặp, tìm chuỗi con lặp và xử lý khoảng.

**Cẩn thận:** truy vấn *longest common substring giữa hai văn bản khác nhau* là bài toán lớn hơn, không chỉ gọi LCE của một chỉ mục từ một chuỗi.

### 15.4. Khi cần an toàn tuyệt đối

Dùng **direct/verified equality** hoặc một chỉ mục deterministic. Double polynomial hash là công cụ tối ưu thuật toán dựa trên xác suất va chạm thấp trong các giả thiết phù hợp, không phải bằng chứng ngữ nghĩa và không phải kiểm tra toàn vẹn mật mã. Nếu dữ liệu do đối phương kiểm soát, có thể cần thuật toán exact hoặc hashing với tính chất bảo mật cụ thể bên ngoài phạm vi rolling hash.

## 16. Sai lầm phổ biến

1. Nhầm `[l,r)` với `[l,r]`, tạo lỗi lệch một ký tự.
2. Cho phép `r>n` hoặc `l>r` mà không báo dữ liệu sai.
3. Lấy độ dài `r-l+1` cho đoạn nửa mở.
4. Dùng `substring` tạo bản sao ở mọi truy vấn lớn và bỏ qua chi phí.
5. So hai hash mà không so độ dài.
6. Tin rằng hai hash bằng nhau là hai chuỗi chắc chắn bằng nhau.
7. Dùng một mô-đun quá nhỏ rồi bỏ qua va chạm.
8. Tuyên bố double hash loại bỏ mọi collision.
9. So số hash để suy ra thứ tự từ điển.
10. Quên `pow[r-l]` trong công thức tách hash.
11. Quên chuẩn hóa giá trị âm sau phép trừ modulo.
12. Dùng `int` cho phép nhân hash với mô-đun khoảng 10^9, gây tràn số.
13. Chọn `long` nhưng không kiểm tra tích `BASE×MOD` có vượt giới hạn 64 bit hay không.
14. Trộn hai cơ số hoặc quy ước mã hóa khác nhau rồi so fingerprint như cùng hệ.
15. Dùng binary search LCP với hash mà không nhắc tới rủi ro collision.
16. Tính LCP hai đoạn nhưng quên chặn theo độ dài đoạn ngắn.
17. Khi một đoạn là tiền tố của đoạn kia, đọc ký tự ở ngoài đoạn để phân định thứ tự.
18. Dùng rank hậu tố để kết luận hai substring bằng nhau dù chiều dài bị giới hạn.
19. Nhầm adjacent LCP với LCP của mọi cặp hậu tố tùy ý.
20. Lấy `max` thay `min` trên khoảng rank khi tính LCE.
21. Sai khoảng RMQ: cần kề từ rank nhỏ tới trước rank lớn.
22. Không có xử lý `i=j` trong LCE, khiến query khoảng RMQ rỗng.
23. Truy cập `rank[n]` khi so đoạn bắt đầu ở cuối chuỗi.
24. Không xử lý n=0 hoặc n=1 khi dựng SA/Kasai/sparse table.
25. Bỏ sentinel −1 trong prefix doubling, khiến thứ tự hậu tố ngắn sai.
26. Gán rank mới dựa vào vị trí ban đầu thay vì thứ tự đã sort.
27. Giả định sorting comparator trên toàn substring ở mọi vòng có O(1).
28. Tuyên bố code prefix doubling `Arrays.sort` là O(n log n) tổng quát, trong khi demo O(n log² n).
29. Tuyên bố sparse table RMQ dùng O(n) bộ nhớ, bỏ qua O(n log n).
30. Không kiểm tra những đoạn bằng nhau nhưng chồng lấn.
31. Đánh đồng UTF-16 code unit với Unicode grapheme.
32. So emoji theo nửa surrogate nhưng lại gắn nhãn “so ký tự hiển thị”.
33. Chuẩn hóa Unicode sau khi dựng chỉ mục nhưng vẫn dùng hash/SA cũ.
34. Trả offset bản chuẩn hóa như offset gốc mà không có mapping.
35. Dùng thư viện hash mật mã một cách mù quáng mà không xét chi phí/truy vấn, hoặc ngược lại dùng rolling hash cho xác thực.
36. Tái sử dụng chỉ mục cũ sau khi sửa chuỗi.
37. Cho rằng suffix array xây một văn bản tự động tra cứu substring của văn bản khác.
38. Chỉ test những chuỗi khác ngay ký tự đầu, bỏ qua tiền tố dài và periodic strings.
39. Chỉ kiểm thử equality mà không kiểm thử lex order và LCP.
40. Coi bộ test ngẫu nhiên là bằng chứng rolling hash không bao giờ xảy ra collision.

## 17. Bài tập có lời giải

**Bài 1.** Với S="banana", đoạn `[1,4)` là gì? **Đáp án:** "ana", dài 3.

**Bài 2.** Đoạn `[3,6)` có bằng `[1,4)` không? **Đáp án:** có, cả hai là "ana".

**Bài 3.** Với n=6, đoạn `[6,6)` có hợp lệ không? **Đáp án:** có, là chuỗi rỗng.

**Bài 4.** Hai đoạn rỗng ở vị trí khác nhau có bằng nhau không? **Đáp án:** có, đều dài 0 và chứa cùng dãy ký tự rỗng.

**Bài 5.** "ana" và "anana" đoạn nào nhỏ hơn theo thứ tự từ điển? **Đáp án:** "ana" nhỏ hơn vì là tiền tố ngắn hơn.

**Bài 6.** "ban" và "nan" đoạn nào nhỏ hơn? **Đáp án:** "ban" nhỏ hơn ngay ở ký tự đầu.

**Bài 7.** Công thức chiều dài đoạn `[l,r)`? **Đáp án:** `r-l`.

**Bài 8.** Có cần sao chép substring để lưu truy vấn không? **Đáp án:** không; có thể lưu chuỗi gốc và cặp chỉ số.

**Bài 9.** Trên S="aaaaa", ba đoạn `[0,3),[1,4),[2,5)` có bằng nhau không? **Đáp án:** có, đều "aaa" dù chồng lấn.

**Bài 10.** Công thức prefix polynomial hash? **Đáp án:** `pref[i+1]=(pref[i]·B+v_i) mod M`, `pow[i+1]=pow[i]·B mod M`.

**Bài 11.** Công thức hash đoạn `[l,r)`? **Đáp án:** `H=(pref[r]−pref[l]·pow[r-l]) mod M`, chuẩn hóa kết quả về không âm.

**Bài 12.** Vì sao cần lưu `pow`? **Đáp án:** để loại phần đóng góp của prefix dài l khỏi hash đến r trong O(1).

**Bài 13.** Hash equality khi có n truy vấn sau tiền xử lý là O(?) mỗi truy vấn? **Đáp án:** O(1), theo giả thiết độ rộng số và số mô-đun hằng.

**Bài 14.** Hai fingerprint trùng nhau có bảo đảm hai chuỗi trùng không? **Đáp án:** không, có thể collision.

**Bài 15.** Vì sao ví dụ hash("a")=hash("f") mod 5? **Đáp án:** với mã char+1, 98 và 103 đều dư 3 khi chia 5.

**Bài 16.** Double hash có làm collision không thể xảy ra? **Đáp án:** không; chỉ giảm rủi ro trong điều kiện phù hợp.

**Bài 17.** Muốn equality **chính xác tuyệt đối** sau khi hash trùng, làm gì? **Đáp án:** so thực tế `regionMatches` hoặc dùng chỉ mục exact.

**Bài 18.** Có được so trị số hash để suy ra thứ tự từ điển không? **Đáp án:** không.

**Bài 19.** Hash hỗ trợ so từ điển ra sao? **Đáp án:** binary search độ dài tiền tố chung bằng equality hash, sau đó so ký tự khác đầu tiên hoặc độ dài.

**Bài 20.** Độ phức tạp tìm LCP bằng double hash? **Đáp án:** O(log(min độ dài)) truy vấn hash, chưa tính rủi ro collision.

**Bài 21.** Suffix array của "banana" là gì? **Đáp án:** `[5,3,1,0,4,2]`.

**Bài 22.** Adjacent LCP của "banana"? **Đáp án:** `[1,3,0,0,2]`.

**Bài 23.** Rank SA dùng để làm gì? **Đáp án:** ánh xạ vị trí bắt đầu hậu tố sang vị trí của nó trong thứ tự SA.

**Bài 24.** LCE(i,j) lấy từ adjacent LCP thế nào? **Đáp án:** min của đoạn adjacent LCP giữa hai rank của hai hậu tố; nếu i=j thì n−i.

**Bài 25.** Tại sao RMQ sparse table cho min có thể dùng hai đoạn chồng lấn? **Đáp án:** phép min idempotent; lặp lại phần tử không làm đổi kết quả.

**Bài 26.** Kasai tính mảng LCP trong bao lâu sau SA? **Đáp án:** O(n).

**Bài 27.** Prefix doubling dùng `Arrays.sort` comparator mỗi vòng có cận thời gian xây SA? **Đáp án:** O(n log² n).

**Bài 28.** Truy vấn equality/lex order bằng SA + Kasai + sparse RMQ mất bao lâu? **Đáp án:** O(1) sau tiền xử lý, theo mô hình code unit.

**Bài 29.** Bộ nhớ sparse table RMQ? **Đáp án:** O(n log n).

**Bài 30.** Với S="A🙂B🙂", hai emoji ở những khoảng UTF-16 nào? **Đáp án:** `[1,3)` và `[4,6)`.

**Bài 31.** Vì sao hai đoạn high surrogate riêng lẻ cũng có thể bằng nhau trong code demo? **Đáp án:** code so **đơn vị mã UTF-16**, không tự phân đoạn grapheme.

**Bài 32.** Nếu chuẩn hóa NFC làm thay đổi độ dài, offset hash/index dùng được cho chuỗi gốc không? **Đáp án:** không mặc định; cần xây index trên bản tương ứng hoặc mapping.

**Bài 33.** Sửa một ký tự của S rồi vẫn dùng prefix hash/suffix array cũ có đúng không? **Đáp án:** không; chỉ mục tĩnh đã lỗi thời.

**Bài 34.** Nhiều truy vấn equality, yêu cầu đúng tuyệt đối và có đủ bộ nhớ: chọn gì? **Đáp án:** SA+LCP+RMQ hoặc phương pháp exact khác; double hash không đủ chứng nhận tuyệt đối.

**Bài 35.** Vì sao test nên dùng substring compare trực tiếp làm oracle? **Đáp án:** so theo cách đơn giản độc lập để phát hiện lỗi chỉ số, prefix/hash hoặc RMQ.

## 18. Checklist trước khi triển khai

1. Đã quy ước `[l,r)`, chỉ số 0-based và đơn vị UTF-16/code point/grapheme chưa?
2. Mọi truy vấn có `0≤l≤r≤n`, kể cả r=n và đoạn rỗng không?
3. Chỉ cần equality, hay cả LCP/lexicographic comparison?
4. Chuỗi có **bất biến** suốt đời sống của chỉ mục không?
5. Số truy vấn có đủ lớn để bù tiền xử lý không?
6. Có cần **chính xác tuyệt đối** hay chấp nhận rủi ro rolling hash?
7. Nếu dùng hash, cả hai bên có chung B, M và mã hóa ký tự không?
8. Đã lưu prefix, power đúng và chuẩn hóa modulo sau phép trừ chưa?
9. Đã kiểm tra nhân `BASE×MOD` không tràn kiểu dữ liệu chưa?
10. Fingerprint có đính kèm **độ dài đoạn** khi so equality không?
11. Có xem hai fingerprint trùng nhau là **ứng viên match**, không phải chứng minh exact không?
12. Nếu cần exact equality, có bước xác minh trực tiếp hoặc index xác định không?
13. Nếu cần lex comparison từ hash, có tìm LCP rồi so ký tự, thay vì so hash số học không?
14. LCP hai đoạn đã chặn theo độ dài đoạn ngắn chưa?
15. Suffix array có xử lý sentinel và các hậu tố kết thúc sớm chính xác không?
16. Kasai có đúng hướng và adjacent LCP dài n−1 không?
17. RMQ có lấy **min trên khoảng rank** và xử lý i=j/i=n không?
18. Có nhớ sparse table dùng O(n log n) bộ nhớ?
19. Đã kiểm tra trên `banana`, chuỗi lặp `aaaaa`, chuỗi rỗng và emoji chưa?
20. Với Unicode, có định nghĩa offset trên bản gốc hay sau chuẩn hóa chưa?
21. Có test so sánh đoạn chồng lấn và đoạn là tiền tố nhau không?
22. Đã kiểm thử cả equality, LCP và lex order bằng oracle độc lập chưa?
23. Khi so hai chuỗi khác nhau, đã xây cấu trúc/định dạng chung phù hợp chưa?
24. Nếu dữ liệu thay đổi, đã chọn tái dựng hoặc cấu trúc động thay vì dùng index cũ chưa?

**Ghi nhớ:** cặp chỉ số **[l,r)** giúp biểu diễn chuỗi con không cần sao chép; **double rolling hash** cho equality rất nhanh sau tiền xử lý nhưng vẫn có **collision**; **suffix array + Kasai LCP + sparse-table RMQ** cho phép xác định **tiền tố chung và so sánh từ điển chính xác** trên cùng chuỗi tĩnh. Trước khi tối ưu tốc độ, phải thống nhất **đơn vị ký tự, ranh giới, mức độ bảo đảm đúng và hệ offset của dữ liệu**.