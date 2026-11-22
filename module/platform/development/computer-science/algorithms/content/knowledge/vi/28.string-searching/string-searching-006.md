# Va chạm băm, nhiều môđun và xác minh kết quả

Trong **tìm kiếm chuỗi (string matching)**, băm chuỗi giúp so sánh nhanh dấu vân tay của các đoạn văn bản. Thay vì duyệt từng ký tự của mọi đoạn dài m, ta có thể tính **hash của một đoạn** với thời gian O(1) sau khi tiền xử lý prefix hash và powers. Đây là ý tưởng đứng sau **Rabin–Karp**, so sánh substring bằng rolling hash và nhiều thuật toán trên chuỗi khác.

Tuy nhiên, một mã băm **không phải chính chuỗi gốc**. Hai chuỗi khác nhau vẫn có thể cho ra cùng hash: đó là **va chạm băm (hash collision)**. Vì vậy cần phân biệt ba mức bảo đảm:

1. **Một môđun:** so sánh một hash, nhanh nhưng có rủi ro va chạm.
2. **Nhiều môđun:** so sánh nhiều hash, thường giảm rủi ro trong giả định thống kê phù hợp, nhưng **không chứng minh hai chuỗi bằng nhau**.
3. **Xác minh ký tự gốc:** khi hash trùng, so lại nội dung thực tế. Đây là cách biến một bộ lọc có xác suất sai thành một **thuật toán tìm kiếm cho kết quả chính xác tuyệt đối**.

Bài học thuộc nhóm **Tìm kiếm chuỗi**, tập trung vào polynomial rolling hash, công thức prefix/substrings, cách chọn base và môđun, việc dùng hai môđun, xác minh kết quả, những giới hạn của mô hình xác suất và code **Java 17+ chạy độc lập**.

Ví dụ nổi bật: hai chuỗi **"Aa"** và **"BB"** khác nhau nhưng có **cùng hash đa thức với base 31**, ngay cả khi tính trên **hai môđun nguyên tố khác nhau**. Do đó, nhiều môđun **không thay thế** việc xác minh ký tự nếu bài đòi kết quả không sai.

## 1. Phân biệt chuỗi, hash và kết quả tìm kiếm

Bài toán cơ bản: cho văn bản **text** có n ký tự và mẫu **pattern** có m ký tự, tìm mọi vị trí i sao cho:

**text[i .. i+m−1] = pattern**.

Trong bài Java này, vị trí được tính theo **UTF-16 code units**, giống với **String.length()**, **String.charAt()**, **String.substring()** và **String.regionMatches()**. Vị trí đánh số từ 0.

Ví dụ:

~~~text
text    = abracadabra
pattern = abra
match positions (0-based) = [0, 7]
~~~

Định nghĩa ba khái niệm:

- **Exact match:** mọi ký tự của đoạn text và pattern đều bằng nhau.
- **Hash candidate:** hash của đoạn text bằng hash của pattern; chỉ cho biết đoạn **có thể** khớp.
- **False positive / va chạm gây nhận nhầm:** hash bằng nhau nhưng nội dung thực tế khác nhau.

Một thuật toán an toàn có thể dùng hash để **lọc nhanh ứng viên**, rồi dùng phép so sánh chuỗi để **quyết định chính thức**.

### Tính chất quan trọng

Nếu hai chuỗi cùng chiều dài và **thực sự giống nhau**, cùng công thức hash và cùng tham số chắc chắn tạo ra hash bằng nhau.

Chiều ngược lại **không đúng**:

**hash(A)=hash(B) không kéo theo A=B.**

Đây là bất đối xứng cơ bản. Hash khác nhau thì chắc chắn hai chuỗi khác nhau; hash trùng nhau thì cần thêm bằng chứng.

## 2. Va chạm băm là điều không thể loại trừ bằng môđun hữu hạn

Giả sử hash nhận giá trị trong tập **{0,1,...,p−1}**, chỉ có p kết quả có thể.

Trong khi đó, số chuỗi có thể tạo ra từ bảng chữ cái nhiều ký tự và độ dài tăng dần là vô hạn. Theo **nguyên lý Dirichlet (pigeonhole principle)**, sẽ tồn tại các chuỗi khác nhau cho cùng hash.

Ngay cả khi chỉ xét những chuỗi có một độ dài cố định L, nếu số chuỗi có thể có lớn hơn p, va chạm là tất yếu.

Với hai môđun p₁,p₂, một cặp hash nhiều nhất có **p₁p₂ khả năng**. Nếu không gian chuỗi lớn hơn số này, vẫn phải có va chạm.

**Kết luận:** tăng kích thước hash có thể làm va chạm ít gặp hơn trong mô hình ngẫu nhiên, nhưng **không thể biến hash hữu hạn thành một ánh xạ một-một trên mọi chuỗi**.

### Va chạm ngẫu nhiên khác va chạm có chủ đích

- **Dữ liệu thông thường:** các chuỗi có thể ít cấu trúc nhằm đánh vào hàm hash; môđun và base tốt giúp giảm xác suất false positive.
- **Dữ liệu đối kháng:** đối thủ có thể biết thuật toán/base và cố tình tạo chuỗi va chạm. Các tuyên bố kiểu "xác suất chỉ 1 trên 10¹⁸" không tự động đúng với dữ liệu được chọn sau khi biết tham số.

Trong các bài chấm thuật toán, nhiều trường hợp dữ liệu được thiết kế đặc biệt để bắt lỗi **coi hash bằng nhau là chuỗi bằng nhau**.

## 3. Ví dụ va chạm cụ thể: "Aa" và "BB"

Dùng polynomial hash của chuỗi hai ký tự với **base=31**, mã ký tự là giá trị Unicode UTF-16 và cộng thêm 1:

**H(s₀s₁) = (code(s₀)+1)·31 + (code(s₁)+1).**

Đối với **"Aa"**:

~~~text
'A' = 65, 'a' = 97
H("Aa") = 66*31 + 98 = 2144
~~~

Đối với **"BB"**:

~~~text
'B' = 66
H("BB") = 67*31 + 67 = 2144
~~~

Hai chuỗi **khác nhau** nhưng có cùng hash nguyên **2144**, thậm chí **trước khi lấy môđun**.

Bây giờ chọn **hai số nguyên tố khác nhau**:

- p₁=101 → 2144 mod 101 = **23**.
- p₂=103 → 2144 mod 103 = **84**.

Cặp hash của cả hai chuỗi đều là:

**(23,84)**.

Nếu text="BB", pattern="Aa" và chỉ tin vào hai hash, thuật toán sẽ báo sai rằng pattern xuất hiện ở vị trí 0.

Nếu kiểm tra ký tự:

**"BB" ≠ "Aa"**, nên kết quả đúng là **không có vị trí khớp**.

Đây là ví dụ thực tế để chứng minh:

> **Hai môđun với cùng base vẫn có thể va chạm đồng thời, thậm chí khi mỗi môđun là số nguyên tố.**

Sử dụng hai base khác nhau sẽ tránh chính ví dụ đồng nhất đa thức trên base=31, nhưng không tạo ra bảo đảm tuyệt đối cho mọi chuỗi.

### Liên hệ với String.hashCode() của Java

Java String.hashCode() cũng sử dụng lược đồ đa thức với hệ số 31 trong số học nguyên 32-bit. Cặp **"Aa"** và **"BB"** là ví dụ va chạm hashCode quen thuộc.

Điều quan trọng: **String.equals() không chỉ so hashCode()**. Hai String có hashCode trùng nhau nhưng nội dung khác nhau vẫn được phân biệt bởi equals().

Không được lấy hashCode() làm **định danh duy nhất** của một chuỗi.

## 4. Polynomial rolling hash: công thức chuẩn

Cho chuỗi s có độ dài n, mã hóa mỗi ký tự thành số nguyên aᵢ. Chọn **base B** và **môđun nguyên dương p**.

Ta dùng công thức hash theo chiều trái sang phải:

**H(s) = (a₀·B^(n−1) + a₁·B^(n−2) + ... + aₙ₋₁) mod p.**

Để mã ký tự không bằng 0, chương trình dùng:

**aᵢ = s.charAt(i) + 1**.

Đây là lựa chọn mã hóa; điều kiện bắt buộc là cách mã hóa **nhất quán** giữa text và pattern. Nếu một bên cộng 1 còn bên kia không cộng, kết quả sẽ sai.

### Tính tăng dần

Ta có thể tính hash từ trái sang phải:

~~~text
h = 0
for each character ch:
    h = (h * B + code(ch)) mod p
~~~

Mỗi bước dùng kết quả của prefix trước. Đây là tính chất làm hash "rolling" dễ tính.

Ví dụ với base=31, mã char+1 và chuỗi "Aa":

~~~text
h0 = 0
h1 = (0*31 + 66) = 66
h2 = (66*31 + 98) = 2144
~~~

Sau khi lấy môđun, số luôn nằm trong [0,p−1].

### Đặc điểm của mã hóa UTF-16

Java String.charAt() trả **một UTF-16 code unit**. Với ký tự ngoài Basic Multilingual Plane như emoji, Java dùng **hai code units (surrogate pair)**.

Nếu cần vị trí theo **Unicode code points**, phải chuyển cả text và pattern sang các dãy code points rồi định nghĩa lại chỉ số. Code trong bài giữ **String indexing semantics** vì đây là cách thường gặp ở bài xử lý String Java.

## 5. Prefix hash và power để lấy hash đoạn O(1)

Để so sánh nhiều substring, cần hai mảng:

- **prefix[i]**: hash của s[0..i−1], độ dài i.
- **power[k]**: B^k mod p.

Khởi tạo:

**prefix[0]=0**, **power[0]=1**.

Cập nhật:

**prefix[i+1] = (prefix[i]·B + aᵢ) mod p**.

**power[i+1] = (power[i]·B) mod p**.

Với đoạn **[l,r)** (l bao gồm, r không bao gồm):

**hash(l,r) = (prefix[r] − prefix[l]·power[r−l]) mod p**.

### Vì sao công thức đúng?

Hash của prefix dài r bao gồm:

- Hash phần s[0..l−1] nhưng được nhân thêm B^(r−l).
- Cộng hash của đoạn s[l..r−1].

Do đó:

**prefix[r] = prefix[l]·B^(r−l) + hash(l,r) (mod p)**.

Chuyển vế được công thức trên.

### Chuẩn hóa kết quả về [0,p−1]

Trong Java, phép % với số âm có thể cho kết quả âm. Vì thế dùng:

~~~java
long removed = prefix[l] * power[r - l] % mod;
long result = (prefix[r] - removed + mod) % mod;
~~~

Vì prefix[r] và removed đều trong [0,mod−1], hiệu nằm trong [−(mod−1),mod−1]. Cộng một mod là đủ để không âm trước phép %.

### Công thức dùng cho cả hash text và pattern

Ta tính hash của pattern cũng bằng cùng base/môđun; sau đó duyệt các vị trí i từ 0 tới n−m, so:

**hashText(i,i+m) == hashPattern(0,m).**

Nhờ công thức đã chuẩn hóa, hai đoạn cùng chiều dài có thể so trực tiếp mà không phụ thuộc vị trí trong chuỗi gốc.

## 6. Một môđun: nhanh nhưng chưa phải kiểm tra bằng nhau

Giả sử dùng p=1_000_000_007, B hợp lệ. Mỗi substring có một số hash trong khoảng 0..p−1.

Trong dữ liệu giống ngẫu nhiên và dưới một mô hình phân bố hash tương đối đều, hai chuỗi khác nhau có thể được kỳ vọng va chạm khoảng 1/p. Đây là **heuristic xác suất**, không phải định lý cho **mọi cặp chuỗi với base cố định**.

Nếu có T phép so sánh độc lập tương tự, rủi ro xuất hiện ít nhất một va chạm có thể tích lũy. Nếu một bài kiểm tra hàng triệu substring hoặc nhiều input do đối thủ thiết kế, chỉ tin vào một hash là nguy hiểm.

### Không đồng nhất xác suất với tính đúng

- **"Thường đúng":** kết quả dựa hoàn toàn vào hash, chấp nhận xác suất sai trong mô hình thích hợp.
- **"Luôn đúng":** kết quả được xác minh bằng nội dung gốc hoặc dùng thuật toán so khớp xác định.

Bài cần câu trả lời chính xác nên ưu tiên phương án **hash lọc ứng viên + xác minh** hoặc KMP/Z thay vì dùng lời hứa rằng "môđun đã lớn nên không thể collision".

## 7. Hai môđun: tăng độ tin cậy như thế nào?

Dùng đồng thời:

- Hash thứ nhất: **(B₁,p₁)**.
- Hash thứ hai: **(B₂,p₂)**.

Mỗi đoạn nhận một **cặp hash (h₁,h₂)**. Chỉ coi là ứng viên khi **cả hai thành phần bằng nhau**.

Ví dụ cấu hình mạnh hơn trong code:

~~~text
p1 = 1,000,000,007
B1 = 911,382,323

p2 = 1,000,000,009
B2 = 972,663,749
~~~

Hai p đều là số nguyên tố lớn, các base nằm trong miền hợp lệ 1<B<p và khác nhau.

Nếu cả hai hash cùng có phân bố gần đều và hành vi va chạm đủ độc lập, mô hình đơn giản cho rủi ro một cặp khác nhau trùng cả hai là khoảng **1/(p₁·p₂)**.

**Nhưng đây không phải bảo đảm phổ quát.** Hai phép băm có thể tương quan; đặc biệt nếu dùng cùng base, va chạm ở cấp đa thức có thể được bảo toàn ở **mọi môđun**, như "Aa" và "BB".

### Điều kiện cần khi dùng ước lượng xác suất

Một phân tích xác suất có ý nghĩa phải nêu:

- Tham số base có được chọn ngẫu nhiên không?
- Dữ liệu được cố định **trước hay sau** khi biết base?
- Hai lựa chọn base/môđun có độc lập không?
- Chuỗi có độ dài bao nhiêu?
- Mã ký tự có thể trùng modulo p không?
- Có bao nhiêu phép so sánh được thực hiện?

Không nêu điều kiện mà khẳng định double hash "chắc chắn không va chạm" là sai.

### Cận với base ngẫu nhiên

Với prime p đủ lớn so với mã ký tự và hai chuỗi khác nhau có cùng độ dài L, hiệu của hai đa thức hash là một đa thức **khác 0** bậc tối đa L−1 trên trường mod p.

Nếu base được chọn **đều ngẫu nhiên** từ các phần tử khác 0 của trường, xác suất hiệu đa thức bằng 0 có cận tối đa:

**min(1, (L−1)/(p−1))**.

Đây là hệ quả đa thức bậc d khác 0 có không quá d nghiệm trên trường. Nếu hai base được chọn độc lập trên hai prime phù hợp, có thể nhân các cận xác suất tương ứng **khi điều kiện độc lập thật sự thỏa**.

Cận này không áp dụng nguyên xi khi base được ấn định công khai trước và một đối thủ chọn chuỗi sau đó.

## 8. Có nên dùng cùng base trên hai môđun?

Cùng base với hai prime khác nhau thường vẫn là lựa chọn được thấy trong lời giải competitive programming; nó giảm nhiều va chạm do riêng phép lấy mod, nhưng **không khắc phục được các va chạm vốn đã có ở đa thức nguyên**.

Ví dụ "Aa" và "BB" base31 cho giá trị nguyên 2144 như nhau, nên cả:

**2144 mod 101 = 23** và **2144 mod 103 = 84**

đều như nhau.

Nếu dùng **hai base khác nhau**, chính cặp chuỗi trên có thể cho hash khác nhau. Điều này làm giảm một dạng tương quan đơn giản, nhưng chỉ cần không gian chuỗi đủ lớn vẫn tồn tại cặp va chạm ở cả hai cặp tham số.

### Quy tắc thực dụng

- Chọn base có giá trị lớn hơn 1 và nhỏ hơn mod.
- Dùng hai prime độc lập và có thể dùng hai base khác nhau.
- Nếu có yêu cầu **zero false positive**, vẫn phải **so sánh ký tự cuối cùng**.
- Nếu dữ liệu nhạy cảm/đối kháng, không coi các cặp polynomial hash cố định là cơ chế bảo mật.

## 9. Xác minh kết quả: tuyến phòng thủ quyết định

Khi hai hash bằng nhau, gọi một phép so sánh chính xác:

- Java: **text.regionMatches(i,pattern,0,m)**.
- Hoặc so từng ký tự bằng **charAt**.
- Hoặc tạo substring rồi gọi equals (nhưng cách này có thể gây cấp phát thêm).

Với regionMatches, nội dung được so trực tiếp và không cần tạo một String substring mới.

Pseudocode:

~~~text
patternHash = doubleHash(pattern)
for i from 0 to n-m:
    if doubleHash(text[i..i+m)) != patternHash:
        continue

    // Only a candidate until exact characters are checked.
    candidates++

    if text.regionMatches(i, pattern, 0, m):
        report i as an actual match
    else:
        rejectedCollisions++
~~~

### Vì sao chắc chắn không bỏ sót kết quả đúng?

Nếu text[i..i+m) thực sự bằng pattern, hai phép hash dùng **cùng tham số/mã hóa** sẽ cho cặp hash bằng nhau. Do đó mọi vị trí khớp thật **đều vượt qua bước lọc**.

### Vì sao chắc chắn không nhận nhầm?

Vị trí chỉ được đưa vào danh sách kết quả nếu **regionMatches trả true**. Dù cặp hash va chạm, việc xác minh nội dung sẽ loại ứng viên sai.

Như vậy thuật toán có **kết quả đúng tuyệt đối theo định nghĩa chuỗi đã chọn**, ngay cả khi cấu hình hash yếu hoặc có va chạm được tạo ra cố ý.

## 10. Rabin–Karp với rolling hash và xác minh

Rabin–Karp tìm các vị trí xuất hiện của pattern bằng hash của những cửa sổ độ dài m.

Có hai lối cài phổ biến:

1. **Sliding window:** giữ trực tiếp hash của cửa sổ hiện tại; khi cửa sổ trượt một ký tự thì trừ đóng góp của ký tự đầu và thêm ký tự cuối.
2. **Prefix hash:** tiền xử lý hash của toàn text và powers; lấy hash của mỗi cửa sổ [i,i+m) trong O(1).

Code Java dùng cách **prefix hash** vì dễ đối chiếu với công thức substring và dễ mở rộng tới các phép so sánh đoạn tùy ý.

Đối với mỗi i:

- Lấy hai hash đoạn text[i,i+m).
- So với hai hash của toàn pattern.
- Nếu khác một trong hai, bỏ.
- Nếu cả hai bằng, ghi nhận **candidate**.
- **Xác minh ký tự** để phân loại thành true match hay collision.

### Tìm nhiều lần xuất hiện chồng lấp

Nếu text="aaaaa" và pattern="aa", vị trí khớp là:

**[0,1,2,3]**.

Không được tăng chỉ số cửa sổ lên m sau khi gặp match nếu yêu cầu **mọi vị trí xuất hiện**. Mỗi bước trượt chỉ tăng i thêm 1.

Nếu text="ababa", pattern="aba", kết quả là **[0,2]**, hai match chồng lên nhau tại một ký tự.

## 11. Trường hợp đặc biệt: pattern rỗng và dài hơn text

Quy ước của chương trình:

- **Pattern rỗng:** khớp tại mọi **ranh giới UTF-16** trong text, từ 0 đến n, tổng **n+1 vị trí**.
- **m>n:** không có đoạn đủ dài, trả danh sách rỗng.
- **n=m:** kiểm tra đúng một ứng viên cửa sổ.
- **n=0,m=0:** một vị trí khớp ở 0.
- **text rỗng, pattern không rỗng:** không khớp.

Ví dụ:

~~~text
text = abc
pattern = (empty)
matches = [0, 1, 2, 3]
~~~

Nếu dùng chuẩn khác (ví dụ pattern rỗng không được phép), phải sửa hợp đồng API và test tương ứng. Không nên bỏ qua trường hợp này vì nó ảnh hưởng vòng lặp i≤n−m và số lượng kết quả.

### Các ký tự Unicode

Java String.indexing dùng UTF-16 code units. Với text gồm một emoji, một ký tự x, rồi một emoji nữa:

~~~text
text = 😀x😀
pattern = 😀
UTF-16 start positions = [0, 3]
~~~

Mỗi emoji ở đây chiếm **hai code units**, vì thế vị trí thứ hai là 3 chứ không phải 2.

Nếu yêu cầu **chỉ số code point** hoặc **vị trí grapheme cluster hiển thị**, cần một lớp chuyển đổi chỉ số riêng. Đừng so kết quả 0-based UTF-16 với các vị trí tính bằng code point mà cho rằng thuật toán sai.

## 12. Chọn hash parameters và tránh tràn số

Mã Java dùng hai prime:

**p₁=1_000_000_007**, **p₂=1_000_000_009**.

Các base:

**B₁=911_382_323**, **B₂=972_663_749**.

Vì mọi phần dư nhỏ hơn khoảng 10⁹+9, phép nhân của hai giá trị nhỏ hơn môđun không vượt khoảng 10¹⁸, **nằm trong phạm vi long 64-bit có dấu** (Long.MAX_VALUE xấp xỉ 9,22×10¹⁸).

Trong code, constructor HashParameters giới hạn mod≤1_000_000_009 và 1<base<mod. Điều này cho phép:

~~~java
long productMod = (x * base) % mod;
~~~

mà không tràn long trong miền tham số được khai báo.

**Không áp dụng công thức ấy nguyên xi cho môđun gần 2⁶³**. Khi x và base cùng lớn, phép nhân long có thể tràn trước khi lấy %. Khi đó cần modular multiplication an toàn bằng chia/tách hoặc BigInteger tùy yêu cầu.

### Vì sao không dùng Math.pow?

Math.pow trả double. Lũy thừa lớn sẽ mất độ chính xác nguyên và overflow dạng floating-point. Cần tiền xử lý:

**power[i+1]=power[i]·base mod p**,

mỗi bước dùng số học nguyên.

### Vì sao cộng mod một lần trước %?

Với công thức substring, hiệu **prefix[r]−removed** có thể âm. Cộng mod rồi % đưa về [0,mod−1] và tránh false negative khi hai đoạn thực sự bằng nhau nhưng cách chuẩn hóa sai.

### Dấu cộng +1 ở ký tự

Công thức dùng **charAt(i)+1L**: chuyển mã UTF-16 0..65535 thành 1..65536. Đây không phải biện pháp chống collision hoàn toàn; nó chỉ là một lựa chọn mã hóa nhất quán và tránh hệ số đầu bằng 0 ở một số trường hợp.

## 13. Chương trình Java 17+: double hash và xác minh

Chương trình dưới đây triển khai đầy đủ:

- HashParameters gồm hai môđun và hai base.
- HashIndex tính hai prefix và hai mảng power.
- HashPair đại diện chữ ký băm kép.
- SearchResult lưu **hash candidates** và **exact matches** tách biệt.
- Hàm search chỉ đưa vị trí vào **matches** sau khi **String.regionMatches** xác nhận.
- Trường hợp pattern rỗng, pattern dài hơn text và Unicode.
- Demo cố ý dùng cấu hình **WEAK** với base31, p=101 và 103 để cho thấy "Aa" và "BB" va chạm ngay ở cả hai hash.
- Demo **STRONG** có hai môđun lớn, hai base khác nhau; vẫn xác minh kết quả, không dựa vào lời hứa xác suất.

**Tên tệp:** DoubleHashVerifiedSearchDemo.java

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class DoubleHashVerifiedSearchDemo {

    record HashParameters(long mod1, long mod2,
                          long base1, long base2) {
        HashParameters {
            if (mod1 <= 2 || mod2 <= 2
                    || mod1 > 1_000_000_009L
                    || mod2 > 1_000_000_009L
                    || base1 <= 1 || base2 <= 1
                    || base1 >= mod1 || base2 >= mod2) {
                throw new IllegalArgumentException(
                        "Require 1 < base < mod <= 1000000009");
            }
        }
    }

    record HashPair(long h1, long h2) {}

    record SearchResult(List<Integer> candidates,
                        List<Integer> matches) {
        String describe() {
            int rejected = candidates.size() - matches.size();
            return "matches=" + matches
                    + ", candidates=" + candidates.size()
                    + ", rejected=" + rejected;
        }
    }

    static final HashParameters STRONG =
            new HashParameters(
                    1_000_000_007L,
                    1_000_000_009L,
                    911_382_323L,
                    972_663_749L);

    // Educational weak configuration: deliberate collision.
    static final HashParameters WEAK =
            new HashParameters(101L, 103L, 31L, 31L);

    static final class HashIndex {
        final HashParameters config;
        final int n;
        final long[] prefix1, prefix2;
        final long[] power1, power2;

        HashIndex(String s, HashParameters config) {
            Objects.requireNonNull(s, "string");
            this.config = Objects.requireNonNull(config, "config");
            this.n = s.length();

            prefix1 = new long[n + 1];
            prefix2 = new long[n + 1];
            power1 = new long[n + 1];
            power2 = new long[n + 1];

            power1[0] = 1;
            power2[0] = 1;

            for (int i = 0; i < n; i++) {
                long value = s.charAt(i) + 1L;

                prefix1[i + 1] = (
                        prefix1[i] * config.base1() + value
                ) % config.mod1();

                prefix2[i + 1] = (
                        prefix2[i] * config.base2() + value
                ) % config.mod2();

                power1[i + 1] = (
                        power1[i] * config.base1()
                ) % config.mod1();

                power2[i + 1] = (
                        power2[i] * config.base2()
                ) % config.mod2();
            }
        }

        HashPair segment(int left, int right) {
            if (left < 0 || right < left || right > n) {
                throw new IndexOutOfBoundsException();
            }

            int len = right - left;

            long rem1 = (
                    prefix1[left] * power1[len]
            ) % config.mod1();

            long rem2 = (
                    prefix2[left] * power2[len]
            ) % config.mod2();

            long h1 = (
                    prefix1[right] - rem1 + config.mod1()
            ) % config.mod1();

            long h2 = (
                    prefix2[right] - rem2 + config.mod2()
            ) % config.mod2();

            return new HashPair(h1, h2);
        }
    }

    static HashPair digest(String s, HashParameters config) {
        HashIndex index = new HashIndex(s, config);
        return index.segment(0, s.length());
    }

    static SearchResult search(
            String text, String pattern,
            HashParameters config) {

        Objects.requireNonNull(text, "text");
        Objects.requireNonNull(pattern, "pattern");
        Objects.requireNonNull(config, "config");

        int n = text.length();
        int m = pattern.length();

        List<Integer> candidates = new ArrayList<>();
        List<Integer> matches = new ArrayList<>();

        if (m == 0) {
            for (int i = 0; i <= n; i++) {
                candidates.add(i);
                matches.add(i);
            }
            return new SearchResult(
                    List.copyOf(candidates),
                    List.copyOf(matches));
        }

        if (m > n) {
            return new SearchResult(List.of(), List.of());
        }

        HashIndex textHash = new HashIndex(text, config);
        HashPair target = digest(pattern, config);

        for (int i = 0; i <= n - m; i++) {
            HashPair window = textHash.segment(i, i + m);

            if (!window.equals(target)) {
                continue;
            }

            // A hash match is a CANDIDATE only.
            candidates.add(i);

            // Exact verification eliminates all false positives.
            if (text.regionMatches(i, pattern, 0, m)) {
                matches.add(i);
            }
        }

        return new SearchResult(
                List.copyOf(candidates),
                List.copyOf(matches));
    }

    static void show(String label,
                     String text, String pattern,
                     HashParameters config) {

        System.out.println(label + ": "
                + search(text, pattern, config).describe());
    }

    public static void main(String[] args) {
        System.out.println(
                "Weak Aa: " + digest("Aa", WEAK));
        System.out.println(
                "Weak BB: " + digest("BB", WEAK));

        SearchResult collision =
                search("BB", "Aa", WEAK);

        System.out.println(
                "Weak hash-only candidates (unsafe): "
                + collision.candidates());
        System.out.println(
                "Weak verified: " + collision.describe());

        show("Strong abracadabra",
                "abracadabra", "abra", STRONG);
        show("Strong repeats",
                "aaaaa", "aa", STRONG);
        show("Strong overlap",
                "ababa", "aba", STRONG);
        show("Strong case",
                "Hello, hello!", "hello", STRONG);
        show("Strong Unicode",
                "😀x😀", "😀", STRONG);
        show("Strong empty pattern",
                "abc", "", STRONG);
        show("Strong longer pattern",
                "abc", "abcd", STRONG);
        show("Strong no match",
                "abracadabra", "xyz", STRONG);
    }
}
~~~

Biên dịch và chạy với **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 DoubleHashVerifiedSearchDemo.java
java DoubleHashVerifiedSearchDemo
~~~

**Đầu ra chính xác:**

~~~text
Weak Aa: HashPair[h1=23, h2=84]
Weak BB: HashPair[h1=23, h2=84]
Weak hash-only candidates (unsafe): [0]
Weak verified: matches=[], candidates=1, rejected=1
Strong abracadabra: matches=[0, 7], candidates=2, rejected=0
Strong repeats: matches=[0, 1, 2, 3], candidates=4, rejected=0
Strong overlap: matches=[0, 2], candidates=2, rejected=0
Strong case: matches=[7], candidates=1, rejected=0
Strong Unicode: matches=[0, 3], candidates=2, rejected=0
Strong empty pattern: matches=[0, 1, 2, 3], candidates=4, rejected=0
Strong longer pattern: matches=[], candidates=0, rejected=0
Strong no match: matches=[], candidates=0, rejected=0
~~~

### Giải thích các trường kết quả

- **candidates:** những vị trí có cả hai hash của cửa sổ bằng hash pattern. Đây mới là ứng viên.
- **matches:** những ứng viên đã vượt qua so sánh ký tự regionMatches.
- **rejected:** số ứng viên hash bị từ chối do nội dung khác nhau.

Ở ví dụ va chạm "BB" tìm "Aa": hash-only candidates là [0], nhưng matches rỗng và rejected=1. Chương trình không báo sai nhờ bước xác minh.

### Vì sao có hai mảng power?

Một môđun dùng một base, nên mỗi cặp (B,p) cần riêng cả prefix và power. Nếu vô tình dùng **power1** trong công thức loại prefix của hash thứ hai, cùng substring cũng có thể tính ra hash sai và tạo false negative.

### Tại sao String.regionMatches tốt ở đây?

Nó so khớp nội dung thật từ vị trí i mà không cần cấp phát String con. Kết quả dựa trên đúng các UTF-16 code units của Java, không dựa trên xác suất của hash.

## 14. Độ phức tạp có và không có xác minh

Gọi:

- n = độ dài text.
- m = độ dài pattern.
- C = số cửa sổ có **cả hai hash trùng** và trở thành ứng viên.
- K = số match thật, K≤C.

Chương trình làm:

1. Tính prefix và power của text: **O(n)**.
2. Tính hash pattern: **O(m)**.
3. Xét n−m+1 cửa sổ; mỗi cửa sổ so cặp hash O(1): **O(n)**.
4. Với C ứng viên, xác minh từng đoạn bằng regionMatches, tối đa **O(m)** cho một ứng viên.

Do đó tổng thời gian:

**O(n + m + C·m)**.

Bộ nhớ:

- Hai prefix và hai powers của text: **O(n)**.
- HashIndex pattern: **O(m)**, trong code digest có mảng trung gian này.
- Hai danh sách vị trí candidates/matches: **O(C+K)**, hay O(C).
- Tổng **O(n+m+C)**, không tính bộ nhớ chứa String đầu vào.

### Vì sao xác minh có thể làm bài chậm O(nm)?

Với text="aaaa...a" và pattern="aaaa...a" ngắn hơn text một ít, nhiều cửa sổ **thực sự khớp**. C có thể gần n, mỗi lần xác minh lại m ký tự:

**O(nm)** trong trường hợp xấu.

Điều này đúng **ngay cả khi không có hash collision nào**, vì tất cả ứng viên đều là true matches.

Nếu yêu cầu **bảo đảm thời gian O(n+m) trong trường hợp xấu**, hãy cân nhắc **KMP hoặc Z-algorithm**, thay vì dựa trên hash + xác minh từng cửa sổ.

### Khi nào hashing + verify vẫn nhanh?

Nếu pattern đủ dài và số ứng viên C rất nhỏ, đa số cửa sổ được loại trong O(1), còn xác minh xảy ra hiếm. Khi cần so sánh rất nhiều substring bất kỳ, prefix hash cũng cho tốc độ lọc tốt.

Nhưng benchmark phải tính cả chi phí build arrays và xác minh; không nên chỉ đếm phép so hash.

## 15. Một hash, hai hash và so sánh trực tiếp: bảng quyết định

| Cách kiểm tra | Rủi ro sai kết quả | Chi phí so hai đoạn cùng độ dài sau tiền xử lý | Khi nào dùng |
| --- | --- | --- | --- |
| So trực tiếp từng ký tự | Không | O(L) trong trường hợp xấu | Cần chính xác tuyệt đối, số lần so vừa |
| Một polynomial hash | Có collision | O(1) | Bộ lọc nhanh hoặc bài cho phép xác suất sai |
| Hai polynomial hash | Vẫn có collision | O(1) | Giảm false positive theo mô hình phù hợp |
| Hai hash + so trực tiếp | Không false positive | O(1) cho phần lớn trường hợp; O(L) khi candidate | Cần kết quả đúng, muốn lọc trước |
| KMP/Z | Không collision | O(n+m) cho tìm pattern | Một pattern trong text, yêu cầu bảo đảm worst-case |
| Suffix array/tree/automaton | Không dựa trên collision khi triển khai chuẩn | Phụ thuộc cấu trúc/truy vấn | Nhiều truy vấn substring, yêu cầu bảo đảm chắc |

Không phải lúc nào double hash là chọn tốt nhất. Nếu chỉ tìm một pattern và muốn thuật toán đơn giản, bảo đảm O(n+m), **KMP** có thể phù hợp hơn.

Nếu phải trả lời hàng nghìn câu hỏi “hai đoạn này có giống nhau không?”, rolling hash có thể là một **bộ lọc** rất nhanh, nhưng nếu cần chắc chắn, phải có cơ chế xác minh khi trùng.

## 16. So sánh với KMP và Z-algorithm

**KMP (Knuth–Morris–Pratt)** xây prefix function cho pattern, rồi quét text một lần. Độ phức tạp **O(n+m)**, không cần hash, không có false positive và trả vị trí xuất hiện chính xác.

**Z-algorithm** cũng xử lý các cấu trúc tiền tố/đoạn trùng khớp. Có thể ghép pattern + ký tự phân cách an toàn + text, rồi tìm các Z-values đạt m để biết match. Cũng có thể đạt **O(n+m)**.

### Khi nào Rabin–Karp vẫn đáng học?

- Hiểu cơ chế hashing, prefix powers và truy vấn đoạn.
- So nhiều đoạn tại các vị trí khác nhau sau một lần tiền xử lý.
- Làm rolling windows hoặc kết hợp tìm kiếm với các cấu trúc băm.
- Đưa ra bộ lọc thực tế với xác minh cuối cùng.

KMP/Z không nhất thiết thuận tiện khi bài hỏi **nhiều cặp substring tùy ý**, trong khi prefix hash cho O(1) để lọc một cặp đoạn cùng chiều dài.

### Aho–Corasick khi có nhiều pattern

Nếu có rất nhiều pattern cần tìm trong cùng text, **Aho–Corasick** cho phép xử lý đa mẫu bằng automaton, đạt cận gần tuyến tính theo text, tổng độ dài pattern và số lần xuất hiện. Chạy Rabin–Karp riêng cho từng pattern có thể không phải phương án tốt nhất.

Chọn cấu trúc theo **dạng truy vấn và bảo đảm đúng/sai**, không chỉ theo độ quen thuộc của tên thuật toán.

## 17. So sánh hai đoạn bất kỳ và bài LCP

Sau khi có HashIndex của một chuỗi s, ta có thể lấy hash(s[l..r)) trong O(1) cho mỗi cặp (base,mod).

Nếu cần so hai đoạn có cùng độ dài L:

1. So hash ở hai môđun.
2. Nếu khác, kết luận **không bằng nhau**.
3. Nếu bằng, **xác minh ký tự** nếu yêu cầu kết luận chính xác.

### Bài Longest Common Prefix (LCP)

Có thể dùng binary search trên độ dài L, mỗi lần hỏi “hai suffix có chung prefix dài ít nhất L không?” bằng hash.

Nếu dùng hash-only, một false positive ở một độ dài trung gian có thể khiến binary search đi sai nhánh và trả **LCP lớn hơn thật**.

**Xác minh chỉ kết quả cuối** không nhất thiết đủ để sửa được binary search đã đi nhánh sai ở các mức trước đó. Nếu cần **tính đúng xác định**, phải bảo đảm mỗi phép quyết định trong binary search chính xác hoặc dùng thuật toán LCP xác định khác.

### Bài longest common substring

Khi dùng binary search theo độ dài và lưu hash của nhiều substring, cùng một key hash có thể đại diện cho nhiều chuỗi khác nhau.

Hash map nên lưu **các vị trí gốc hoặc các chuỗi ứng viên**, không chỉ một boolean “hash này tồn tại”. Khi hash trùng, kiểm tra thực sự hai substring có giống nhau hay không.

Nếu một collision xuất hiện trong một lượt tìm độ dài L và ta coi nó là bằng nhau, binary search có thể bị lệch. Các điểm quyết định về **sự tồn tại một substring chung** cần được xác minh theo đúng định nghĩa.

## 18. Hash và an ninh: không sử dụng sai mục đích

Polynomial rolling hash tối ưu cho **tính nhanh** trong thuật toán chuỗi, không phải cho **bảo mật**.

Nó không phải hash mật mã vì:

- Có thể xây va chạm và quan hệ đại số.
- Không có yêu cầu chống tìm tiền ảnh/tiền ảnh thứ hai theo chuẩn cryptographic hash.
- Nếu base/mod được biết, đối thủ có thể tận dụng cấu trúc công thức.
- Số kết quả hữu hạn và cấu trúc tuyến tính khiến nhiều tấn công dễ hơn so với hash mật mã chuẩn.

**Không dùng rolling hash để xác minh mật khẩu, chữ ký số, tính toàn vẹn dữ liệu chống giả mạo hoặc làm MAC.** Các bài bảo mật cần primitive phù hợp, ví dụ password hashing chuyên dụng cho mật khẩu và HMAC/AEAD/signatures cho xác thực tùy ngữ cảnh.

Ngay cả hash mật mã cũng không phải “chứng minh toán học rằng hai file chắc chắn bằng nhau” chỉ từ một giá trị digest hữu hạn; nhưng mục tiêu thiết kế và khả năng chống tấn công hoàn toàn khác rolling hash.

### HashMap và equals()

Java HashMap sử dụng hashCode để chọn bucket, nhưng **equals** xác định sự bằng nhau giữa key khi cần. Vì vậy HashMap vẫn phân biệt được "Aa" và "BB" dù hashCode trùng nhau.

Nếu tự xây Map<Long,Boolean> theo một polynomial hash rồi xem key là định danh duy nhất của substring, ta đã **bỏ mất bước equals** mà HashMap chuẩn vốn có.

## 19. Chọn base ngẫu nhiên và xử lý dữ liệu đối kháng

Để giảm việc đối thủ biết trước một base cố định, có thể chọn một base ngẫu nhiên khi chương trình bắt đầu.

Tuy nhiên cần lưu ý:

- Base phải được chọn trong miền hợp lệ, thường **1<base<p**.
- Không chọn base=0 hoặc 1: chúng tạo hash rất yếu.
- Cần tính lại **mọi prefix/power** với base đã chọn.
- Muốn hai hash hành xử gần độc lập, chọn hai base phù hợp và độc lập trong mô hình xác suất.
- Cần nguồn ngẫu nhiên thích hợp nếu mô hình đối thủ có thể thích nghi.
- Không được coi randomized hashing là **bằng chứng chắc chắn** cho mọi trường hợp.

Một chương trình dùng **hai prime lớn và base ngẫu nhiên** có thể rất đáng tin trong bài cho phép xác suất lỗi nhỏ. Nhưng nếu đặc tả yêu cầu **không bao giờ in match sai**, việc xác minh ký tự vẫn là hàng rào cuối.

### Rủi ro ở nhiều phép so

Một cặp khác nhau được so một lần không giống với hàng chục triệu cặp được so. Nếu xác suất va chạm cho từng phép có một cận p nhỏ, cần tính **xác suất hợp của các sự kiện lỗi** qua mọi truy vấn. Union bound cho phép lấy tổng các cận xác suất mà không đòi độc lập giữa mọi truy vấn.

Nếu không có mô hình xác suất hợp lệ, không nên tự nhân/chia các xác suất rồi đưa ra một tỷ lệ “gần như không thể” như sự thật tuyệt đối.

## 20. Các lỗi triển khai thường gặp

1. **Coi hash bằng nhau là chuỗi bằng nhau**, bỏ qua collision.
2. **Dùng hai môđun rồi tuyên bố hoàn toàn không va chạm**.
3. **Không nhận ra cùng base có thể va chạm trước khi lấy mod**, ví dụ "Aa" và "BB".
4. **Dùng một base quá yếu như 0 hoặc 1**.
5. **Thay đổi base/mod ở giữa quá trình** nhưng không xây lại prefix/powers.
6. **Dùng khác cách mã hóa char ở text và pattern**.
7. **Nhầm prefix[i] là hash bao gồm ký tự i**, sai off-by-one.
8. **Dùng power[r] thay cho power[r−l]** trong công thức substring.
9. **So hai đoạn khác độ dài chỉ bằng hash**, gây kết luận sai.
10. **Quên cộng mod trước phép % trong Java**, tạo hash đoạn âm.
11. **Dùng Math.pow kiểu double** để tính B^k, làm mất chính xác nguyên.
12. **Dùng long nhân hai số quá lớn mà không kiểm tra overflow**.
13. **Dùng cùng mảng power cho hai base khác nhau**, tính hash thứ hai sai.
14. **Quên xác minh bằng regionMatches/equals** khi output phải tuyệt đối đúng.
15. **Xác minh bằng so một vài ký tự đầu/cuối**, không loại hết collision.
16. **Dùng substring tạo String mới cho mọi cửa sổ**, có thể cấp phát nhiều.
17. **Nhảy i+=m sau khi tìm một match**, bỏ qua match chồng lấp.
18. **Không xử lý pattern rỗng**, trả sai số vị trí.
19. **Không xử lý m>n**, truy cập ngoài bounds.
20. **Nhầm chỉ số UTF-16 với chỉ số Unicode code point** khi có emoji.
21. **Bỏ qua chuẩn hóa Unicode**: hai cách mã hóa chữ có dấu có thể hiển thị giống nhưng không bằng String.
22. **Cho rằng xác minh hash candidate vẫn O(n+m) worst-case**, dù C·m có thể lớn.
23. **Coi HashMap hashCode là unique ID**, bỏ qua equals.
24. **Dùng rolling hash cho chứng thực mật khẩu/chữ ký**, nhầm với crypto hash.
25. **Chỉ kiểm tra các ví dụ ngẫu nhiên mà không thử va chạm cố ý**, không phát hiện lỗi hash-only.
26. **Đếm nhầm candidates thành matches**, báo thừa vị trí.
27. **Chỉ xác minh kết quả cuối của binary search LCP**, dù các quyết định trước đã có thể sai.
28. **Không kiểm tra tổng số candidates và rejected**, khó phát hiện collision trong test.
29. **Khẳng định xác suất 1/(p₁p₂) dù base cố định và đầu vào đối kháng**, không có điều kiện độc lập.
30. **Nhầm Java % với modulo toán học trên số âm**, không chuẩn hóa đầy đủ.

## 21. Kiểm thử bằng oracle độc lập và property-based tests

Muốn QA thuật toán rolling hash có xác minh, cách tốt nhất là **so với tìm kiếm trực tiếp bằng ký tự**, không dùng hash trong oracle.

Oracle đơn giản:

~~~text
BRUTE_FORCE(text, pattern):
    n = text.length
    m = pattern.length

    if m == 0:
        return positions [0, 1, ..., n]
    if m > n:
        return []

    result = []
    for i in 0 .. n-m:
        equal = true
        for j in 0 .. m-1:
            if text.charAt(i+j) != pattern.charAt(j):
                equal = false
                break
        if equal:
            result.add(i)

    return result
~~~

### Những thuộc tính nên kiểm tra

- **Mọi vị trí match thật đều xuất hiện trong candidates**.
- **matches là tập con của candidates**.
- **Mọi matches đều bằng oracle**.
- **Hash của hai đoạn bằng nhau thật sự** phải bằng nhau ở cả hai môđun.
- **Công thức prefix segment** phải cho kết quả bằng hash tính trực tiếp từ đoạn, với cả hai base.
- **rejected = candidates − matches**.
- Các vị trí trả về phải tăng dần và nằm trong [0,n−m], hoặc [0,n] với pattern rỗng.

### Bộ test gợi ý

| Text | Pattern | Exact matches (0-based) |
| --- | --- | --- |
| abracadabra | abra | [0,7] |
| aaaaa | aa | [0,1,2,3] |
| ababa | aba | [0,2] |
| Hello, hello! | hello | [7] |
| 😀x😀 | 😀 | [0,3] theo UTF-16 |
| abc | chuỗi rỗng | [0,1,2,3] |
| abc | abcd | [] |
| BB | Aa | [] dù weak hash cùng cặp |
| Aa | Aa | [0] |
| chuỗi rỗng | chuỗi rỗng | [0] |

**Kiểm thử có chủ đích** với "BB" và "Aa" là rất quan trọng: nó chứng minh thuật toán thật sự xác minh nội dung chứ không chỉ tin vào hai hash.

### Random testing

Sinh hàng trăm hoặc hàng nghìn cặp text/pattern từ bảng chữ cái nhỏ, gồm:

- Lặp nhiều ký tự ("aaa...").
- Chuỗi xen kẽ ("abab...").
- Mẫu không xuất hiện.
- Mẫu dài hơn text.
- Mẫu rỗng.
- Các ký tự ngoài ASCII và surrogate pairs.
- Các cấu hình hash nhỏ để tăng tỷ lệ collision kiểm thử.

So toàn bộ kết quả verified với oracle trực tiếp. Với cấu hình nhỏ, sẽ có nhiều candidate sai; đó **không phải lỗi** nếu các candidate ấy bị xác minh từ chối.

### QA về số học

Ngoài kết quả tìm kiếm, thử các đoạn [l,r) bất kỳ:

1. Tính prefix-based hash(l,r).
2. Tính polynomial hash trực tiếp bằng vòng lặp trên chính các code units s[l..r).
3. Hai kết quả phải bằng nhau ở **cả hai môđun**.

Kiểm tra này bắt các lỗi ít lộ khi chỉ thử tìm kiếm, đặc biệt lỗi **power index**, dấu modulo, và cách mã hóa ký tự.

## 22. Câu hỏi tự kiểm tra

**Câu 1.** Va chạm băm là gì?  
**Đáp án:** Hai chuỗi khác nhau cho cùng giá trị hash.

**Câu 2.** Hash khác nhau có thể là hai chuỗi bằng nhau không, khi cùng tham số và mã hóa?  
**Đáp án:** Không; hai chuỗi bằng nhau luôn có hash bằng nhau.

**Câu 3.** Hai hash bằng nhau có đảm bảo hai chuỗi bằng nhau không?  
**Đáp án:** Không. Double hashing cũng có thể collision.

**Câu 4.** Vì sao "Aa" và "BB" va chạm với base31?  
**Đáp án:** Mã char+1 cho cả hai đều tạo giá trị đa thức 2144.

**Câu 5.** Hash cặp của "Aa" và "BB" theo mod101,mod103,base31 là gì?  
**Đáp án:** Cùng là (23,84).

**Câu 6.** Công thức hash substring [l,r) là gì?  
**Đáp án:** (prefix[r]−prefix[l]·power[r−l]) mod p.

**Câu 7.** Tại sao cần cộng mod trước % trong Java?  
**Đáp án:** Để loại số âm do phép trừ, chuẩn hóa hash về [0,p−1].

**Câu 8.** Tại sao phải dùng cùng base/mod và mã hóa để so text với pattern?  
**Đáp án:** Nếu khác tham số, hash của hai chuỗi bằng nhau không nhất thiết bằng nhau.

**Câu 9.** Sau khi hai hash trùng, làm gì để kết luận chắc chắn?  
**Đáp án:** So khớp chính xác ký tự, ví dụ regionMatches.

**Câu 10.** Nếu dùng double hash + regionMatches, còn false positive không?  
**Đáp án:** Không, theo định nghĩa String/UTF-16 của API.

**Câu 11.** Vì sao time worst-case sau xác minh có thể là O(nm)?  
**Đáp án:** Có thể có O(n) candidates, mỗi candidate so tới m ký tự.

**Câu 12.** Thuật toán nào bảo đảm O(n+m) cho một pattern mà không cần hash?  
**Đáp án:** KMP hoặc Z-algorithm.

**Câu 13.** Pattern "aa" trong text "aaaaa" xuất hiện ở đâu?  
**Đáp án:** [0,1,2,3], gồm cả các xuất hiện chồng lấp.

**Câu 14.** Với pattern rỗng và text dài n, code chọn bao nhiêu vị trí?  
**Đáp án:** n+1, từ 0 tới n.

**Câu 15.** Trong Java, emoji thường chiếm bao nhiêu char positions?  
**Đáp án:** Ký tự ngoài BMP thường chiếm 2 UTF-16 code units.

**Câu 16.** Nếu hai heuristic xác suất được thực hiện trên cùng base, có thể nhân rủi ro collision như độc lập không?  
**Đáp án:** Không được mặc định; ví dụ collision đa thức nguyên tồn tại ở cả hai prime.

**Câu 17.** Dùng rolling hash để xác minh mật khẩu có phù hợp không?  
**Đáp án:** Không; đó không phải primitive password hashing bảo mật.

**Câu 18.** Tại sao không đủ để chỉ xác minh kết quả cuối của binary search LCP?  
**Đáp án:** False positive ở bước giữa đã có thể khiến binary search rẽ sai nhánh.

## 23. Tổng kết và quy tắc ra quyết định

Đối với bài **tìm kiếm chuỗi bằng rolling hash**, cách làm đáng tin:

1. Định nghĩa **chỉ số và quan hệ bằng nhau** của chuỗi (UTF-16, code points, case sensitivity, Unicode normalization).
2. Chọn một hoặc hai cặp base/mod hợp lệ, nhất quán giữa text và pattern.
3. Xây prefix hash và power để lấy hash của cửa sổ O(1).
4. Duyệt mọi cửa sổ độ dài m, không bỏ qua những match chồng lấp.
5. Dùng **double hash** để giảm số ứng viên cần kiểm tra trong mô hình phù hợp.
6. **Khi hash trùng, so ký tự gốc** nếu cần đúng tuyệt đối.
7. Kiểm soát overflow long và chuẩn hóa phép trừ modulo.
8. Xử lý pattern rỗng, m>n và khác biệt giữa UTF-16 positions với Unicode code points.
9. Đánh giá thời gian theo **O(n+m+C·m)** nếu xác minh từng candidate.
10. Nếu cần bảo đảm worst-case O(n+m), cân nhắc KMP/Z.
11. Nếu input đối kháng, đừng biến cặp polynomial hash thành cơ chế bảo mật hoặc định danh duy nhất.
12. QA bằng oracle so ký tự và cố ý thử collision "Aa"/"BB".

**Kết luận:** một hash giúp **lọc**, nhiều môđun thường giúp **lọc tin cậy hơn**, còn **xác minh ký tự** mới giúp **kết luận đúng tuyệt đối**. Ba bước này là ba mức bảo đảm khác nhau, không thể thay thế lẫn nhau.
