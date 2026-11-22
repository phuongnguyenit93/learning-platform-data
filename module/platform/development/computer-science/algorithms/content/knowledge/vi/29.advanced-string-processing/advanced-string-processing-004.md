# Mảng LCP và thuật toán Kasai

**LCP array (Longest Common Prefix array)** là mảng lưu độ dài **tiền tố chung dài nhất của hai hậu tố đứng kề nhau trong thứ tự từ điển**. Khi đã có **suffix array (SA)** của một chuỗi, thuật toán **Kasai** xây mảng LCP trong **O(n)** thời gian và O(n) bộ nhớ phụ.

Đây là kiến thức nền tảng của **Xử lý chuỗi nâng cao**, được dùng để đếm substring phân biệt, tìm substring lặp dài nhất, giải truy vấn LCP của hai suffix, nghiên cứu các đoạn lặp và làm tiền xử lý cho nhiều bài toán ghép chuỗi.

Ba ý tưởng phải hiểu đúng:

1. **Suffix array** sắp xếp các hậu tố của chuỗi theo thứ tự từ điển.
2. **LCP array** chỉ lưu LCP giữa **hai hậu tố kề nhau trong SA**, không phải hai vị trí kề nhau trong văn bản gốc.
3. **Kasai** đi qua **vị trí bắt đầu hậu tố theo thứ tự gốc 0,1,...,n−1**, dùng mảng **rank** để biết vị trí của từng hậu tố trong SA và tái sử dụng số ký tự khớp đã biết.

Câu ghi nhớ: **SA cho thứ tự, rank cho vị trí ngược, Kasai cho LCP giữa các suffix kề nhau trong SA.**

Trong bài, chỉ số Java đều bắt đầu từ **0** và xét chuỗi theo **UTF-16 code units**, tương ứng với String.length(), charAt(), substring() và compareTo(). Đây là định nghĩa cố ý: nếu đề yêu cầu vị trí theo Unicode code points, cần chuyển dữ liệu trước.

## 1. Suffix và thứ tự từ điển

Với chuỗi s dài n, một **suffix** bắt đầu ở vị trí i được ký hiệu:

**Sᵢ = s[i..n−1]**.

Nó bao gồm ký tự tại i và kéo dài đến cuối chuỗi. Trong cách đánh chỉ số half-open của Java, hậu tố đó chính là **s.substring(i)**.

Ví dụ s = "banana", n=6:

| Vị trí bắt đầu i | Suffix s[i..] |
| ---: | --- |
| 0 | banana |
| 1 | anana |
| 2 | nana |
| 3 | ana |
| 4 | na |
| 5 | a |

Sắp xếp suffix theo thứ tự từ điển chuẩn, với **chuỗi ngắn hơn đứng trước nếu là tiền tố của chuỗi dài hơn**:

| Rank từ điển r | SA[r] | Suffix |
| ---: | ---: | --- |
| 0 | 5 | a |
| 1 | 3 | ana |
| 2 | 1 | anana |
| 3 | 0 | banana |
| 4 | 4 | na |
| 5 | 2 | nana |

Mảng suffix array:

**SA = [5, 3, 1, 0, 4, 2]**.

SA[r] là **vị trí bắt đầu của suffix đứng thứ r**, không phải ký tự hay thứ tự xuất hiện của chúng trong chuỗi gốc.

### Không tự thêm ký tự sentinel vào chuỗi gốc

Một số thuật toán xây suffix array sử dụng ký tự kết thúc đặc biệt, ví dụ '$', và cả hậu tố rỗng. Trong bài này, chúng ta **không thêm sentinel thật** và **không đưa suffix rỗng vào SA**: có đúng n hậu tố bắt đầu tại 0..n−1.

Khi xây SA bằng so sánh cặp rank, phần nằm ngoài cuối chuỗi được xem là **rank ảo −1**, nhỏ hơn mọi giá trị ký tự hợp lệ. Đây chỉ là quy ước so sánh, không thêm ký tự nào vào dữ liệu gốc.

Nếu một bài dùng SA dài n+1 có suffix rỗng, mảng LCP sẽ khác chỉ số. Trước khi dùng công thức phải xác định quy ước.

## 2. LCP của hai chuỗi và hai suffix

**LCP(A,B)** là số ký tự liên tiếp giống nhau tính từ **đầu** hai chuỗi.

Ví dụ:

- LCP("anana","ana") = **3** vì cùng bắt đầu bằng "ana".
- LCP("banana","nana") = **0** vì ký tự đầu khác.
- LCP("aaaa","aa") = **2**.
- LCP("abc","abc") = **3**.
- LCP("abc","abx") = **2**.

Định nghĩa:

**LCP(Sᵢ,Sⱼ) = số k lớn nhất sao cho s[i..i+k) = s[j..j+k).**

Không được vượt phần cuối của một trong hai hậu tố:

**0 ≤ LCP(Sᵢ,Sⱼ) ≤ min(n−i,n−j)**.

Nếu i=j thì hai hậu tố giống nhau:

**LCP(Sᵢ,Sᵢ)=n−i**.

Trong Java, phép tính LCP trực tiếp của hai suffix có thể dùng vòng while:

~~~java
int k = 0;
while (i + k < s.length()
        && j + k < s.length()
        && s.charAt(i + k) == s.charAt(j + k)) {
    k++;
}
~~~

Cách trực tiếp có thể tốn O(n) cho một cặp. Mảng LCP cho **toàn bộ những cặp kề nhau trong SA** được Kasai xây tổng cộng trong **O(n)**, không phải O(n²).

## 3. Định nghĩa mảng LCP theo quy ước của bài

Có nhiều biến thể chỉ số, nên cần ghi rõ:

**LCP[0]=0**.

Với **1≤r<n**:

**LCP[r] = LCP(suffix bắt đầu tại SA[r−1], suffix bắt đầu tại SA[r]).**

Nói cách khác, LCP[r] đo mức khớp của hậu tố ở **hàng r−1 với hàng r trong suffix array**.

Với s="banana":

| r | SA[r] | Suffix | LCP[r] với suffix hàng trước |
| ---: | ---: | --- | ---: |
| 0 | 5 | a | 0 |
| 1 | 3 | ana | 1 |
| 2 | 1 | anana | 3 |
| 3 | 0 | banana | 0 |
| 4 | 4 | na | 0 |
| 5 | 2 | nana | 2 |

Vậy:

**LCP = [0, 1, 3, 0, 0, 2]**.

Ví dụ LCP[2]=3 vì SA[1]=3 ("ana") và SA[2]=1 ("anana") có tiền tố chung "ana".

LCP[5]=2 vì SA[4]=4 ("na") và SA[5]=2 ("nana") có tiền tố chung "na".

### Một quy ước khác

Một số sách dùng **height[r] = LCP(SA[r],SA[r+1])** cho 0≤r<n−1. Khi đó mảng có n−1 phần tử, hoặc thêm giá trị 0 ở cuối.

Hai định nghĩa **dịch nhau một vị trí**. Mã Java và tất cả công thức bên dưới chỉ dùng **LCP[0]=0, LCP[r]=LCP(SA[r−1],SA[r])**.

## 4. Vì sao tính từng LCP một cách ngây thơ là chậm?

Sau khi đã có SA, một cách đơn giản là:

~~~text
for r = 1 .. n-1:
    i = SA[r-1]
    j = SA[r]
    k = 0
    while i+k < n and j+k < n
          and s[i+k] == s[j+k]:
        k++
    LCP[r] = k
~~~

Nếu chuỗi có nhiều ký tự lặp, các cặp suffix có thể chung tiền tố dài. Ví dụ:

~~~text
s = aaaaa
suffix order:
a
aa
aaa
aaaa
aaaaa
LCP = [0,1,2,3,4]
~~~

Cách tính ngây thơ thực hiện 1+2+3+4 phép so khớp thành công, và tổng quát có thể tốn **Θ(n²)** với một chuỗi "aaaa...a" dài n.

Kasai tránh việc **khởi tạo k=0 rồi quét lại từ đầu** ở mọi cặp. Nó dùng một bất biến đặc biệt: khi chuyển từ suffix bắt đầu i sang suffix bắt đầu i+1, **độ dài LCP cần kiểm tra thường không nhỏ hơn giá trị đã biết trừ 1**.

## 5. Mảng rank: phép ánh xạ ngược của SA

Đặt:

**rank[i] = vị trí r sao cho SA[r]=i**.

Như vậy:

**rank[SA[r]] = r** và **SA[rank[i]] = i**.

Với "banana", SA=[5,3,1,0,4,2]:

| i | Suffix | rank[i] |
| ---: | --- | ---: |
| 0 | banana | 3 |
| 1 | anana | 2 |
| 2 | nana | 5 |
| 3 | ana | 1 |
| 4 | na | 4 |
| 5 | a | 0 |

**rank = [3,2,5,1,4,0]**.

Lưu ý rank ở đây là **inverse suffix array**. Trong thuật toán xây SA bằng doubling, cũng có một mảng rank tạm đại diện cho **nhóm tương đương của các tiền tố độ dài 2ᵏ**. Hai loại rank có liên quan nhưng **không nên trộn lẫn** khi giải thích/cài đặt:

- **Doubling rank:** tạm thay đổi khi xây SA.
- **Inverse SA rank:** mảng cuối cùng để Kasai biết vị trí của suffix trong SA.

### Tra suffix đứng trước trong thứ tự từ điển

Nếu rank[i]=r>0, suffix đứng ngay trước Sᵢ trong SA bắt đầu ở:

**j=SA[r−1]**.

Kasai so Sᵢ với Sⱼ. Nếu rank[i]=0, suffix Sᵢ là nhỏ nhất theo từ điển, không có suffix đứng trước; không cần so và đặt h=0.

## 6. Ý tưởng cốt lõi của Kasai: giảm k nhiều nhất một đơn vị

Giả sử tại suffix bắt đầu i, ta đã biết **LCP(Sᵢ, suffix đứng trước nó trong SA)=h**, h>0.

Gọi suffix đứng trước Sᵢ là Sⱼ. Vì h>0, hai suffix bắt đầu bằng cùng một ký tự. Sau khi **bỏ ký tự đầu**, ta có:

**Sᵢ₊₁ và Sⱼ₊₁ có ít nhất h−1 ký tự đầu bằng nhau.**

Từ Sⱼ < Sᵢ và hai suffix có ký tự đầu giống nhau, suy ra **Sⱼ₊₁ < Sᵢ₊₁** theo thứ tự từ điển.

Suffix đứng trước **ngay sát** Sᵢ₊₁ trong SA là phần tử lớn nhất trong các suffix nhỏ hơn Sᵢ₊₁. Khi một suffix nhỏ hơn Sᵢ₊₁ đã chung prefix dài h−1, suffix đứng sát Sᵢ₊₁ cũng phải có ít nhất prefix dài ấy, do **các chuỗi có cùng tiền tố dài k tạo thành một đoạn liên tiếp trong thứ tự từ điển**.

Do đó:

**LCP của Sᵢ₊₁ với suffix đứng sát nó trong SA ≥ h−1**, nếu h>0.

Nói cách khác, khi tăng vị trí xuất phát từ i lên i+1, ta không cần so lại h−1 ký tự đầu đã biết chắc chắn bằng nhau.

### Cách duy trì biến k

- Sau khi tính xong LCP của suffix i, nếu k>0 thì **k--** trước khi xử lý suffix i+1.
- Trong suffix kế tiếp, dùng k làm **cận dưới ban đầu**, rồi so thêm từng ký tự trong vòng while.
- Nếu suffix i đang có rank 0, đặt k=0 vì không có suffix đứng trước trong SA.

Ký hiệu k trong Kasai là **số ký tự đang biết khớp**, không phải vị trí suffix hoặc số vòng xây SA.

### Chi tiết quan trọng

Đừng lấy nguyên k từ cặp cũ mà không giảm 1. Hai suffix mới đã bỏ một ký tự đầu, nên chỉ còn đảm bảo **k−1** ký tự đầu trùng.

Đừng giảm k xuống âm: dùng **if(k>0) k--**.

Đừng thay rank[i] bằng rank[i−1]; Kasai duyệt suffix theo **i=0..n−1**, còn suffix đứng trước trong thứ tự từ điển là **SA[rank[i]−1]**.

## 7. Pseudocode Kasai: O(n) sau khi có SA

Giả sử s có n ký tự và SA là một **hoán vị chính xác của 0..n−1** đã sắp suffix theo từ điển.

~~~text
KASAI(s, SA):
    n = length(s)
    rank[0..n-1] = new array
    LCP[0..n-1] = 0

    for r = 0 .. n-1:
        rank[SA[r]] = r

    k = 0

    for i = 0 .. n-1:
        r = rank[i]

        if r == 0:
            k = 0
            continue

        j = SA[r-1]

        while i+k < n and j+k < n
              and s[i+k] == s[j+k]:
            k++

        LCP[r] = k

        if k > 0:
            k--

    return LCP
~~~

**Điểm mấu chốt:** vòng for **duyệt i theo thứ tự vị trí gốc**, không duyệt r theo thứ tự SA. Nhờ vậy khi chuyển từ i sang i+1, tính chất k giảm tối đa 1 mới áp dụng được.

Nếu làm vòng ngoài trên r=0..n−1, các hậu tố kế tiếp theo SA có thể bắt đầu ở những vị trí gốc rất xa nhau. Khi đó không có quyền tái sử dụng k theo công thức trên.

### Dữ liệu cần có

- s: chuỗi gốc.
- SA: suffix array đã sắp đúng.
- rank: inverse SA.
- LCP: output, độ dài n.
- k: số ký tự khớp được duy trì.

Cả rank và LCP đều chiếm O(n) bộ nhớ. Không cần lưu một bản String riêng cho mỗi suffix.

## 8. Truy vết Kasai với "banana"

Ta có:

~~~text
s     = banana
SA    = [5, 3, 1, 0, 4, 2]
rank  = [3, 2, 5, 1, 4, 0]

LCP sau khi tinh xong = [0, 1, 3, 0, 0, 2]
~~~

Đi từng **i trong chuỗi gốc**:

| i | Suffix i | rank[i] | j=SA[rank[i]−1] | So khớp | LCP[rank[i]] | k sau giảm |
| ---: | --- | ---: | ---: | --- | ---: | ---: |
| 0 | banana | 3 | 1 | banana / anana | 0 | 0 |
| 1 | anana | 2 | 3 | anana / ana | 3 | 2 |
| 2 | nana | 5 | 4 | nana / na | 2 | 1 |
| 3 | ana | 1 | 5 | ana / a | 1 | 0 |
| 4 | na | 4 | 0 | na / banana | 0 | 0 |
| 5 | a | 0 | — | không có predecessor | — | 0 |

Lưu ý thứ tự **điền mảng LCP** là các vị trí r: **3,2,5,1,4**, không phải 1,2,3,4,5.

Ví dụ khi i=1, LCP=3, Kasai giảm k còn 2. Khi i=2, suffix "nana" và predecessor "na" đã chắc chắn trùng **hai ký tự đầu**, nên có thể nhận LCP=2 mà không cần bắt đầu so lại từ vị trí 0.

### Kiểm tra cách đọc bảng

Cột "k sau giảm" là k **chuẩn bị cho vòng i+1**, không phải giá trị LCP vừa lưu. Giá trị thật của LCP tại rank[i] được ghi **trước khi giảm**.

## 9. Chứng minh Kasai chạy O(n)

Điều dễ gây nhầm: trong Kasai vẫn có một vòng **while so từng ký tự** bên trong một vòng for n phần tử. Nhưng **không phải mọi vòng while đều bắt đầu k từ 0**, nên tổng không thành O(n²).

Xét biến k:

1. Ban đầu k=0.
2. Mỗi lần vòng while so thành công một cặp ký tự, k tăng đúng 1.
3. Sau mỗi suffix, thuật toán giảm k **nhiều nhất 1** (hoặc reset k=0 nếu rank[i]=0).
4. Trong mọi trạng thái, 0≤k≤n.
5. Do k không thể âm, tổng số lần tăng k trên n vòng ngoài bị chặn bởi **O(n)**, cộng phần tăng ban đầu tối đa n và những lần giảm tổng tối đa n. Lần reset k=0 chỉ có thể xảy ra khi xử lý đúng **một suffix nhỏ nhất** trong SA, nên không tạo nhiều lần reset lớn.

Mỗi vòng ngoài còn có tối đa một phép so ký tự không thành công hoặc chạm cuối chuỗi trước khi dừng while.

Vậy tổng phép so là O(n), và cả thuật toán:

**Kasai time = O(n)**.

Bộ nhớ thêm:

**rank[n] + LCP[n] = O(n)**.

### Phân biệt với thời gian dựng suffix array

Kasai yêu cầu **SA đã có sẵn**. Nếu tạo SA bằng một thuật toán mất O(n log²n), rồi mới chạy Kasai O(n), toàn pipeline vẫn có tổng thời gian:

**O(n log²n + n) = O(n log²n)**.

Không được viết “thuật toán trong ví dụ dựng cả SA và LCP trong O(n)” khi phần dựng SA có chi phí cao hơn.

Các thuật toán xây SA nâng cao như SA-IS hoặc DC3 có thể đạt O(n) theo mô hình phù hợp, nhưng **Kasai không tự xây SA**.

## 10. Dựng suffix array cho demo: doubling

Để có chương trình Java tự chạy độc lập, bài này dùng thuật toán **prefix doubling** xây SA trước khi gọi Kasai.

Ở vòng có độ dài khối k:

- Mỗi suffix được so bằng cặp:

**(rank[i], rank[i+k])**,

trong đó phần ngoài chuỗi có rank **−1**.

- Hai cặp được so từ điển: thành phần đầu trước, nếu bằng nhau thì thành phần sau.
- Sau khi sắp xếp vị trí suffix theo cặp, cấp rank nhóm mới: những cặp bằng nhau nhận cùng rank; cặp khác nhau nhận rank mới.
- Nhân đôi k: 1,2,4,8,... đến khi các rank phân biệt hết hoặc độ dài khối đủ bao phủ chuỗi.

Mỗi vòng so các cặp rank độ dài O(1). Bản Java dùng **Arrays.sort(Integer[], comparator)**, mất **O(n log n)** cho mỗi vòng; có O(log n) vòng:

**Time build SA = O(n log²n)**, **extra memory O(n)** ngoài những đối tượng boxed Integer[] của Java.

Nếu dùng radix/counting sort để sắp các cặp rank trong mỗi vòng, có thể xây SA trong **O(n log n)** với giả thiết bảng chữ cái và phép toán số nguyên phù hợp.

### Một chi tiết dễ sai khi có tie

Khi hai cặp rank bằng nhau, comparator phải trả **0**. Nếu dùng vị trí i để phá tie trong comparator rồi **cũng dùng comparator đó để gán nhóm rank mới**, ta có thể tách những cặp thực ra tương đương thành hai rank khác nhau.

Trong code, phần gán nhóm chỉ xét **hai thành phần rank** của cặp, không xét vị trí i như một tiêu chí phân biệt.

### Tại sao rank ngoài chuỗi = −1?

Vì mọi rank ký tự hợp lệ đều không âm. Khi một hậu tố kết thúc sớm hơn, đoạn ngoài cuối được xem nhỏ hơn ký tự tiếp theo của hậu tố dài; đảm bảo quy tắc **chuỗi ngắn hơn đứng trước nếu là tiền tố của chuỗi dài hơn**.

## 11. Ứng dụng 1 — đếm số substring phân biệt

Một chuỗi dài n có:

**n(n+1)/2** đoạn substring không rỗng nếu phân biệt theo **vị trí bắt đầu và kết thúc**, chưa loại các đoạn có nội dung trùng.

Một suffix bắt đầu tại i có **n−i tiền tố không rỗng**; mỗi tiền tố ấy là một substring của chuỗi gốc.

Khi duyệt các suffix theo SA từ nhỏ đến lớn, những prefix của suffix ở rank r mà **đã xuất hiện trước đó** có độ dài từ 1 đến **LCP[r]**. Vì vậy suffix này đóng góp:

**(n−SA[r]) − LCP[r]** substring mới.

Cộng tất cả:

**distinctSubstrings(s) = n(n+1)/2 − Σ LCP[r]**.

### Ví dụ "banana"

n=6, tổng substring theo vị trí:

**6·7/2 = 21**.

LCP=[0,1,3,0,0,2], tổng LCP:

**0+1+3+0+0+2=6**.

Vậy số substring khác nhau:

**21−6=15**.

### Ví dụ "aaaaa"

Có tổng 5·6/2=15 đoạn theo vị trí nhưng các substring khác nhau chỉ là:

"a", "aa", "aaa", "aaaa", "aaaaa".

LCP=[0,1,2,3,4], tổng 10. Kết quả:

**15−10=5**.

### Lưu ý overflow trong Java

Công thức nên dùng **long**:

~~~java
long total = (long) n * (n + 1L) / 2L;
for (int h : lcp) total -= h;
~~~

Nếu viết n*(n+1)/2 bằng **int**, phép nhân có thể overflow ngay cả khi kết quả thực vẫn nằm trong long.

## 12. Ứng dụng 2 — substring lặp dài nhất

Một substring xuất hiện tại **hai vị trí bắt đầu khác nhau** khi và chỉ khi nó là tiền tố chung của ít nhất hai suffix.

Theo thứ tự từ điển, những suffix chung một prefix tạo thành một đoạn liên tiếp. Nếu có hai suffix chung prefix dài L, trong đoạn SA giữa chúng sẽ có ít nhất một **cặp kề nhau** chung prefix dài ≥L.

Vậy:

**Độ dài longest repeated substring = max LCP[r]**, với r=1..n−1.

Để lấy một substring minh họa, tìm một r có LCP[r] lớn nhất và lấy:

**s.substring(SA[r], SA[r]+LCP[r])**.

### Ví dụ

- "banana": max LCP=3, substring lặp dài nhất **"ana"**, xuất hiện ở các vị trí 1 và 3.
- "mississippi": max LCP=4, substring lặp dài nhất **"issi"**, xuất hiện ở các vị trí 1 và 4.
- "aaaaa": max LCP=4, substring lặp dài nhất **"aaaa"**, xuất hiện ở 0 và 1.
- "abc": max LCP=0, không có substring **không rỗng** lặp lại.

Trong định nghĩa này, hai lần xuất hiện **được phép chồng lấp**. Nếu bài yêu cầu hai đoạn **không giao nhau**, không thể chỉ lấy max LCP; phải kiểm tra thêm khoảng cách vị trí.

### Khi có nhiều đáp án

Có thể có nhiều substring cùng độ dài tối đa. Bản Java quét LCP từ trái sang phải và chỉ cập nhật khi tìm thấy độ dài **lớn hơn**, trả một đáp án xác định theo thứ tự duyệt.

Nếu đề yêu cầu **đáp án nhỏ nhất từ điển** khi hòa, cần nêu và chứng minh tie-breaking phù hợp; nếu yêu cầu vị trí xuất hiện nhỏ nhất thì dùng tiêu chí khác.

## 13. Ứng dụng 3 — LCP của hai suffix bất kỳ bằng RMQ

Mảng LCP trực tiếp chỉ chứa LCP giữa **hai suffix kề nhau trong SA**. Nhưng ta có thể tìm LCP của hai suffix bắt đầu ở vị trí **i và j bất kỳ**.

Gọi:

**a=rank[i]**, **b=rank[j]**.

Giả sử a<b. Khi đó:

**LCP(Sᵢ,Sⱼ) = min(LCP[a+1], LCP[a+2], ..., LCP[b])**.

Nếu a>b, đổi chỗ hai rank. Nếu i=j, đáp án là **n−i**.

### Vì sao dùng min?

Các suffix được sắp theo từ điển. Mọi chuỗi trong một khoảng SA từ rank a tới rank b đều chia sẻ với hai đầu khoảng một prefix dài ít nhất bằng **minimum của các LCP kề nhau** trên khoảng đó.

Ngược lại, nếu hai đầu chia sẻ prefix dài L thì mọi suffix nằm giữa chúng trong thứ tự từ điển cũng có prefix dài L. Vì vậy tất cả LCP kề nhau trong khoảng ít nhất L.

Hai chiều suy ra đẳng thức.

### Ví dụ với "banana"

SA=[5,3,1,0,4,2], rank=[3,2,5,1,4,0], LCP=[0,1,3,0,0,2].

- LCP suffix bắt đầu **1** ("anana") và **3** ("ana"): rank lần lượt 2 và 1, min(LCP[2])=**3**.
- LCP suffix bắt đầu **2** ("nana") và **4** ("na"): rank 5 và 4, min(LCP[5])=**2**.
- LCP suffix bắt đầu **0** ("banana") và **2** ("nana"): rank 3 và 5, min(LCP[4],LCP[5])=min(0,2)=**0**.
- LCP suffix bắt đầu **0** với chính nó: **n−0=6**.

### Range Minimum Query (RMQ)

Để hỏi minimum trên nhiều đoạn LCP:

- **Quét trực tiếp:** O(n) mỗi query, không cần cấu trúc phụ.
- **Segment Tree:** tiền xử lý O(n), query O(log n), thêm O(n) bộ nhớ.
- **Sparse Table:** tiền xử lý O(n log n), query **O(1)**, thêm O(n log n) bộ nhớ, phù hợp vì mảng LCP **tĩnh** sau khi xây.

Mã Java dùng **Sparse Table** để minh họa truy vấn LCP hai suffix O(1) sau tiền xử lý.

### Cảnh báo ở công thức chỉ số

Đoạn RMQ là:

**[min(rank[i],rank[j])+1, max(rank[i],rank[j])]**, hai đầu **bao gồm**.

Nếu dùng [a,b] thay vì [a+1,b] theo định nghĩa LCP[0]=0 thì có thể nhận 0 sai cho những suffix thực sự có prefix chung.

## 14. Ứng dụng 4 — so sánh hai đoạn, tìm kiếm và cấu trúc nâng cao

### So sánh hai substring cùng độ dài

Với hai đoạn [i,i+len) và [j,j+len), cả hai nằm trong chuỗi, ta có thể hỏi:

**LCP(Sᵢ,Sⱼ) ≥ len**?

Nếu đúng thì hai đoạn bằng nhau. Với rank + RMQ đã chuẩn bị, phép kiểm tra này O(1).

Nếu hỏi **thứ tự từ điển** của hai substring, cần so ký tự đầu tiên sau phần prefix chung, trừ khi một đoạn hết trước. Có thể dùng LCP để tìm vị trí khác nhau đầu tiên trong O(1) sau tiền xử lý.

### Tìm pattern bằng suffix array

Sau khi có SA, dùng **hai phép binary search** trên thứ tự suffix để tìm khoảng các suffix bắt đầu bằng pattern:

- Mọi suffix có prefix bằng pattern tạo thành **một đoạn liên tiếp** trong SA.
- Lấy lower bound và upper bound theo comparator tiền tố đúng quy tắc.
- Với mỗi so sánh trực tiếp pattern-suffix có thể cần O(m) ký tự, nên tìm khoảng có thể mất **O(m log n)**.

Có thể tối ưu hơn bằng LCP hoặc cấu trúc khác, nhưng đây là ứng dụng của SA; Kasai **không tự thay thế binary search**.

### Các đề nâng cao liên quan

- Longest common substring giữa hai chuỗi: xây **generalized suffix array** cho chuỗi ghép có ký tự phân cách/sentinel an toàn, kiểm tra LCP của suffix thuộc hai chuỗi khác nhau.
- Tìm số substring xuất hiện ít nhất k lần: phân tích các cửa sổ/khoảng SA có LCP tối thiểu đủ lớn.
- Lexicographically smallest repeated substring: kết hợp LCP và quy tắc tie.
- Phân tích độ lặp và dựng cấu trúc khoảng LCP.
- Suffix tree: có liên hệ sâu với SA+LCP; nhưng không nên coi một vector LCP là toàn bộ suffix tree mà không xây cấu trúc tương ứng.

### Separator cho nhiều chuỗi

Nếu ghép A + '#' + B, ký tự '#' phải **không xung đột với dữ liệu gốc**. Chọn dấu '#' một cách tùy tiện có thể sai nếu input cũng chứa '#'. Một cách an toàn hơn là làm việc trên dãy **mã số nguyên** với các sentinel phân biệt nằm ngoài bảng chữ cái, hoặc escape/encode dữ liệu.

## 15. Java 17+: chương trình hoàn chỉnh SA + Kasai + Sparse Table

Chương trình dưới đây tạo:

1. **SA** bằng prefix doubling + Arrays.sort comparator: O(n log²n).
2. **LCP** bằng thuật toán **Kasai: O(n)**.
3. **rank** cuối để tra vị trí suffix trong SA: O(n).
4. **Sparse Table RMQ** trên LCP: O(n log n) tiền xử lý, O(1) query.
5. Hàm đếm distinct substrings và lấy longest repeated substring.

Đây là chương trình **độc lập**, chỉ dùng thư viện chuẩn Java 17, không cần nhập stdin. Để tránh mơ hồ, mọi vị trí kết quả là **chỉ số UTF-16 0-based**; chuỗi rỗng có SA=[] và LCP=[].

**Lưu tệp: KasaiLcpDemo.java**

~~~java
import java.util.Arrays;
import java.util.Objects;

public class KasaiLcpDemo {

    // Suffix array: O(n log^2 n) with comparator-based doubling.
    static int[] buildSuffixArray(String s) {
        int n = s.length();
        Integer[] order = new Integer[n];
        int[] rank = new int[n];
        int[] nextRank = new int[n];

        for (int i = 0; i < n; i++) {
            order[i] = i;
            rank[i] = s.charAt(i); // UTF-16 code-unit order.
        }

        for (int step = 1; step < n; step *= 2) {
            final int shift = step;
            final int[] old = rank;

            Arrays.sort(order, (a, b) -> {
                int cmp = Integer.compare(old[a], old[b]);
                if (cmp != 0) return cmp;

                int left = a + shift < n
                        ? old[a + shift] : -1;
                int right = b + shift < n
                        ? old[b + shift] : -1;
                return Integer.compare(left, right);
            });

            int groups = 1;
            nextRank[order[0]] = 0;

            for (int i = 1; i < n; i++) {
                int prev = order[i - 1];
                int curr = order[i];

                int prevSecond = prev + step < n
                        ? rank[prev + step] : -1;
                int currSecond = curr + step < n
                        ? rank[curr + step] : -1;

                if (rank[prev] != rank[curr]
                        || prevSecond != currSecond) {
                    groups++;
                }

                nextRank[curr] = groups - 1;
            }

            int[] temp = rank;
            rank = nextRank;
            nextRank = temp;

            if (groups == n) break;
        }

        int[] sa = new int[n];
        for (int i = 0; i < n; i++) {
            sa[i] = order[i];
        }
        return sa;
    }

    // Kasai: O(n) given a correct suffix array.
    static int[] buildKasai(String s, int[] sa) {
        int n = s.length();
        int[] inverse = new int[n];
        int[] lcp = new int[n];

        for (int r = 0; r < n; r++) {
            inverse[sa[r]] = r;
        }

        int k = 0;

        for (int i = 0; i < n; i++) {
            int r = inverse[i];

            if (r == 0) {
                k = 0;
                continue;
            }

            int j = sa[r - 1];

            while (i + k < n && j + k < n
                    && s.charAt(i + k) == s.charAt(j + k)) {
                k++;
            }

            lcp[r] = k;
            if (k > 0) k--;
        }

        return lcp;
    }

    static final class SparseMin {
        final int[] lg;
        final int[][] table;

        SparseMin(int[] a) {
            int n = a.length;
            lg = new int[n + 1];

            for (int i = 2; i <= n; i++) {
                lg[i] = lg[i / 2] + 1;
            }

            int levels = n == 0 ? 0 : lg[n] + 1;
            table = new int[levels][];

            if (n > 0) {
                table[0] = a.clone();

                for (int k = 1; k < levels; k++) {
                    int length = 1 << k;
                    int half = length >>> 1;
                    table[k] = new int[n - length + 1];

                    for (int i = 0; i + length <= n; i++) {
                        table[k][i] = Math.min(
                                table[k - 1][i],
                                table[k - 1][i + half]);
                    }
                }
            }
        }

        int min(int left, int right) {
            int n = lg.length - 1;

            if (left < 0 || left > right || right >= n) {
                throw new IndexOutOfBoundsException(
                        "Invalid RMQ interval");
            }

            int len = right - left + 1;
            int k = lg[len];

            return Math.min(
                    table[k][left],
                    table[k][right - (1 << k) + 1]);
        }
    }

    static final class Index {
        final String text;
        final int[] sa;
        final int[] lcp;
        final int[] rank;
        final SparseMin rmq;

        Index(String text) {
            this.text = Objects.requireNonNull(text, "text");
            this.sa = buildSuffixArray(text);
            this.lcp = buildKasai(text, sa);

            rank = new int[text.length()];
            for (int r = 0; r < sa.length; r++) {
                rank[sa[r]] = r;
            }

            rmq = new SparseMin(lcp);
        }

        // LCP of suffixes starting at original positions i and j.
        int lcpSuffixes(int i, int j) {
            int n = text.length();

            if (i < 0 || i >= n || j < 0 || j >= n) {
                throw new IndexOutOfBoundsException(
                        "Suffix start outside 0..n-1");
            }

            if (i == j) return n - i;

            int a = rank[i];
            int b = rank[j];
            int left = Math.min(a, b) + 1;
            int right = Math.max(a, b);

            return rmq.min(left, right);
        }

        long distinctSubstrings() {
            long n = text.length();
            long answer = n * (n + 1L) / 2L;

            for (int value : lcp) {
                answer -= value;
            }

            return answer;
        }

        String longestRepeated() {
            int length = 0;
            int start = 0;

            for (int r = 1; r < lcp.length; r++) {
                if (lcp[r] > length) {
                    length = lcp[r];
                    start = sa[r];
                }
            }

            return text.substring(start, start + length);
        }
    }

    static void show(String label, Index idx) {
        System.out.println(label + " SA: "
                + Arrays.toString(idx.sa));
        System.out.println(label + " LCP: "
                + Arrays.toString(idx.lcp));
        System.out.println(label + " distinct: "
                + idx.distinctSubstrings());

        String repeated = idx.longestRepeated();
        System.out.println(label + " longest repeat: "
                + (repeated.isEmpty() ? "(none)" : repeated));
    }

    public static void main(String[] args) {
        Index banana = new Index("banana");
        show("banana", banana);

        System.out.println("banana rank: "
                + Arrays.toString(banana.rank));
        System.out.println("banana LCP(1,3): "
                + banana.lcpSuffixes(1, 3));
        System.out.println("banana LCP(2,4): "
                + banana.lcpSuffixes(2, 4));
        System.out.println("banana LCP(0,2): "
                + banana.lcpSuffixes(0, 2));
        System.out.println("banana LCP(0,0): "
                + banana.lcpSuffixes(0, 0));

        show("mississippi", new Index("mississippi"));
        show("aaaaa", new Index("aaaaa"));
        show("abracadabra", new Index("abracadabra"));
        show("single", new Index("z"));
        show("empty", new Index(""));
    }
}
~~~

Biên dịch/chạy bằng **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 KasaiLcpDemo.java
java KasaiLcpDemo
~~~

**Đầu ra chính xác:**

~~~text
banana SA: [5, 3, 1, 0, 4, 2]
banana LCP: [0, 1, 3, 0, 0, 2]
banana distinct: 15
banana longest repeat: ana
banana rank: [3, 2, 5, 1, 4, 0]
banana LCP(1,3): 3
banana LCP(2,4): 2
banana LCP(0,2): 0
banana LCP(0,0): 6
mississippi SA: [10, 7, 4, 1, 0, 9, 8, 6, 3, 5, 2]
mississippi LCP: [0, 1, 1, 4, 0, 0, 1, 0, 2, 1, 3]
mississippi distinct: 53
mississippi longest repeat: issi
aaaaa SA: [4, 3, 2, 1, 0]
aaaaa LCP: [0, 1, 2, 3, 4]
aaaaa distinct: 5
aaaaa longest repeat: aaaa
abracadabra SA: [10, 7, 0, 3, 5, 8, 1, 4, 6, 9, 2]
abracadabra LCP: [0, 1, 4, 1, 1, 0, 3, 0, 0, 0, 2]
abracadabra distinct: 54
abracadabra longest repeat: abra
single SA: [0]
single LCP: [0]
single distinct: 1
single longest repeat: (none)
empty SA: []
empty LCP: []
empty distinct: 0
empty longest repeat: (none)
~~~

### Các lựa chọn cài đặt cần hiểu

**buildSuffixArray** nhận String và trả một hoán vị SA của 0..n−1. Dùng rank của ký tự UTF-16 và ghép đôi rank ở vị trí cách k, với sentinel ảo −1 ở ngoài cuối chuỗi.

**buildKasai** nhận SA và tính LCP[0]=0; nếu rank[i]>0, so suffix i với suffix tại SA[rank[i]−1]. Biến k giảm tối đa 1 sau mỗi vòng. Độ phức tạp của **riêng hàm này** là O(n).

**SparseMin** lưu min trên các khoảng có độ dài 2ᵏ; dùng hai khoảng phủ [left,right] để trả min O(1). Vì phép min là **idempotent**, hai khoảng phủ có thể chồng lên nhau mà không làm thay đổi đáp án.

**Index.lcpSuffixes** không nhận vị trí rank; nó nhận **hai vị trí bắt đầu trong String gốc**. Nó tự đổi sang rank, rồi gọi RMQ đúng đoạn.

**Index.distinctSubstrings** dùng long để chứa n(n+1)/2 mà không tràn int.

**Index.longestRepeated** trả chuỗi rỗng nếu không có đoạn không rỗng lặp lại. Hàm không trả vị trí xuất hiện hay yêu cầu hai lần xuất hiện không chồng lấp.

### Quy tắc chạy với input lớn

Code này ưu tiên dễ học, không tối ưu tối đa. Arrays.sort(Integer[]) tạo boxed references, comparator được gọi nhiều lần; với n rất lớn có thể tốn thời gian/RAM. Trong bài đòi hiệu năng cao, cân nhắc radix/counting sort cho doubling hoặc thuật toán xây SA tuyến tính, và dùng primitive arrays.

Nếu chỉ cần LCP array sau khi **đề đã cho s và SA**, bỏ hẳn bước buildSuffixArray; Kasai vẫn chạy O(n). Nếu cần RMQ mà hạn chế RAM, dùng Segment Tree thay cho Sparse Table.

## 16. Ví dụ thứ hai: "mississippi"

Với s="mississippi", n=11:

~~~text
SA  = [10,7,4,1,0,9,8,6,3,5,2]
LCP = [0,1,1,4,0,0,1,0,2,1,3]
~~~

Các hậu tố đầu theo thứ tự:

~~~text
i
ippi
issippi
ississippi
mississippi
pi
ppi
sippi
sissippi
ssippi
ssissippi
~~~

Đoạn **"issi"** xuất hiện trong cả suffix bắt đầu tại 4 và suffix bắt đầu tại 1:

- S₄="issippi".
- S₁="ississippi".
- LCP của chúng là **4**.

Vì vậy mảng LCP có giá trị 4 ở rank của cặp kề nhau này; đó cũng là giá trị LCP lớn nhất, suy ra substring lặp dài nhất có độ dài 4.

Tổng substring theo vị trí: **11·12/2=66**.

Tổng LCP: **13**.

Số substring phân biệt: **66−13=53**.

### Lưu ý với các cặp LCP bằng nhau

Mảng LCP có thể chứa nhiều phần tử cùng giá trị. Điều này không có nghĩa đó là cùng một substring: cần nhìn thêm suffix tương ứng hoặc nội dung prefix.

Từ **LCP[r]=k**, ta chỉ biết hai suffix kề nhau có chung **ít nhất đúng k ký tự đầu (và không chung ký tự tiếp theo khi cả hai còn ký tự)**. Muốn biết substring cụ thể, lấy prefix dài k từ một trong hai suffix ấy.

## 17. Trường hợp toàn ký tự giống nhau

Cho s="aaaaa":

~~~text
suffixes sorted:
a
aa
aaa
aaaa
aaaaa

SA  = [4,3,2,1,0]
LCP = [0,1,2,3,4]
~~~

Đây là bài kiểm tra rất tốt:

- Nếu Kasai khởi tạo k=0 mỗi vòng, số ký tự phải so tăng lên đáng kể, lộ lỗi tối ưu thời gian.
- Nếu đặt rank sentinel sai, có thể sắp suffix dài trước suffix ngắn.
- Nếu quên giới hạn i+k<n hoặc j+k<n, sẽ truy cập ngoài String.
- Nếu dùng quy ước LCP lệch chỉ số, kết quả có thể là [1,2,3,4,0] thay vì [0,1,2,3,4].
- Distinct substring phải là **5**, không phải 15.
- Longest repeated substring là **"aaaa"**, được phép chồng lấp khi xuất hiện tại 0 và 1.

Với chuỗi rỗng, không có suffix bắt đầu ở vị trí hợp lệ:

**SA=[]**, **LCP=[]**, **distinct=0**, **longestRepeated=""**.

Với một ký tự, SA=[0], LCP=[0], distinct=1, không có repeated substring không rỗng.

## 18. Unicode, sentinel, dấu cách và ký tự đặc biệt

Java String được lưu theo **UTF-16 code units**. Khi có ký tự ngoài BMP như emoji, một ký tự hiển thị có thể chiếm **hai char**.

Trong demo:

- s.length() đếm code units.
- Mọi SA[r] là chỉ số char 0-based.
- LCP[r] là **số code units**, không nhất thiết là số code points hiển thị.
- String.compareTo() và comparator theo charAt dùng cùng thứ tự code units.

Điều này nhất quán cho chương trình, nhưng nếu bài yêu cầu vị trí theo Unicode code points, cần:

1. Chuyển String sang **int[] codePoints**.
2. Xây suffix array trên dãy số nguyên ấy.
3. Chạy Kasai trên int[].
4. Chuyển chỉ số trở lại UTF-16 offset nếu cần truy cập String gốc.

### Chuỗi hiển thị giống nhau nhưng mã Unicode khác nhau

Ví dụ chữ có dấu có thể được biểu diễn bằng **một code point dựng sẵn** hoặc **chữ cơ sở cộng dấu kết hợp**. Hai cách có thể trông như nhau nhưng không bằng nhau ở cấp code units.

Muốn tìm theo **ngữ nghĩa Unicode đã chuẩn hóa**, cần thống nhất normalization (như NFC) **trước khi** xây SA/LCP. Khi chuẩn hóa có thể thay đổi độ dài và vị trí chỉ số, nên phải xác định rõ điều đề bài muốn.

### Dấu xuống dòng, khoảng trắng, ký tự 0

Suffix array không cần dữ liệu chỉ là chữ cái a..z. Bản doubling so sánh theo mã UTF-16, nên các khoảng trắng và ký tự điều khiển cũng có thể được sắp xếp hợp lệ.

Virtual sentinel rank −1 khác với ký tự mã 0 thật; vì vậy một String chứa ký tự NUL cũng không bị nhầm với kết thúc chuỗi.

## 19. Các lỗi phổ biến khi học Kasai

1. **Hiểu LCP[r] là LCP của vị trí r và r−1 trong chuỗi gốc**, thay vì của SA[r] và SA[r−1].
2. **Nhầm SA[r] là rank của suffix bắt đầu r**, trong khi SA[r] là vị trí bắt đầu suffix thứ r.
3. **Không xây inverse rank[]**, rồi tìm vị trí suffix trong SA bằng duyệt O(n) ở mỗi vòng.
4. **Duyệt suffix theo r của SA**, nhưng dùng tối ưu k-- vốn chỉ đúng khi tăng vị trí gốc i.
5. **Lấy j=SA[rank[i]+1]** dù quy ước đang dùng predecessor SA[rank[i]−1].
6. **Không xử lý rank[i]=0**, truy cập SA[-1].
7. **Quên k-- sau khi lưu LCP**, khiến lcp tiếp theo bị tính quá lớn.
8. **Giảm k xuống âm** khi k=0.
9. **Reset k=0 cho mọi i**, làm mất ưu thế tuyến tính.
10. **Không kiểm tra giới hạn i+k<n và j+k<n**, truy cập ngoài.
11. **Dùng LCP[0] không nhất quán**, làm sai RMQ hoặc công thức đếm substring.
12. **Bỏ +1 trong RMQ [rankLow+1,rankHigh]**, đưa cả một LCP không thuộc đoạn.
13. **Trả min LCP của cả mảng cho mọi cặp suffix**, thay vì đúng khoảng giữa hai rank.
14. **Không xử lý i=j trong truy vấn LCP**, tạo khoảng RMQ rỗng dù đáp án là n−i.
15. **Coi max LCP là longest repeated non-overlapping substring**, mặc dù hai lần xuất hiện có thể chồng nhau.
16. **Đếm distinct bằng tổng n−SA[r] nhưng không trừ LCP[r]**, đếm trùng prefix cũ.
17. **Dùng int cho n(n+1)/2**, gây overflow với n lớn.
18. **Nhầm thời gian Kasai O(n) với thời gian toàn pipeline có build SA**.
19. **Dùng sentinel ký tự có thể xuất hiện trong dữ liệu**, sai thứ tự suffix.
20. **Cho mọi cặp rank bằng nhau thành rank khác nhau trong doubling**, phá việc so prefix.
21. **Đánh giá mã Java Arrays.sort comparator là O(n log n) cho toàn bộ SA**, quên có O(log n) vòng doubling.
22. **Nhầm ký tự Unicode code point với UTF-16 char positions**, làm output lệch khi có emoji.
23. **Dùng String.substring ở mọi lần so suffix trong construction**, tạo cấp phát nhiều và tốn thời gian.
24. **Chỉ thử "banana" mà không thử "aaaaa", chuỗi rỗng, một ký tự, ký tự trùng nhau**.
25. **So chính xác nội dung longestRepeated khi có nhiều đáp án hòa mà không xét tie-break**, báo sai cho một kết quả vẫn hợp lệ.
26. **Quên rằng SA có n hậu tố không rỗng nếu không thêm sentinel**, làm sai kích thước mảng.
27. **Trộn lẫn giá trị LCP (số ký tự) với vị trí trong SA**, dẫn tới so sánh chỉ số sai.
28. **Dùng binary search theo pattern nhưng so comparator toàn suffix sai quy ước prefix**, bỏ sót kết quả có pattern là tiền tố.
29. **Giữ SA/LCP cũ sau khi chỉnh sửa ký tự của chuỗi**, dù dữ liệu tiền xử lý đã lỗi thời.
30. **Kết luận mọi substring chung có thể đọc trực tiếp từ max LCP một cặp**, bỏ qua yêu cầu nhiều lần xuất hiện hay nhiều chuỗi.

## 20. Chiến lược kiểm thử độc lập

Cần xác minh **cả suffix array lẫn mảng Kasai**, vì Kasai có thể làm đúng với một SA đúng nhưng kết quả pipeline vẫn sai nếu SA được sắp sai.

Với chuỗi ngắn, tạo oracle không tối ưu:

1. Sinh các vị trí 0..n−1.
2. Sắp xếp các vị trí bằng cách so **toàn bộ s.substring(i)** theo lex order.
3. Với mỗi cặp suffix kề trong SA oracle, đếm LCP từ ký tự đầu tới khi khác hoặc hết chuỗi.
4. So **SA** và **LCP** của code với hai mảng oracle.
5. Kiểm tra rank[SA[r]]=r và SA[rank[i]]=i.
6. Với nhiều cặp i,j, so **lcpSuffixes(i,j)** với LCP tính trực tiếp.
7. Đếm distinct substrings bằng **HashSet<String>** của mọi s.substring(i,j) trên n nhỏ, rồi so với công thức.
8. Tìm longest repeat bằng vét cạn cặp vị trí i<j, so **độ dài** với max LCP; xác nhận chuỗi kết quả thật sự xuất hiện ở ít nhất hai vị trí.

### Các ca nên thử

| Chuỗi | Điều kiểm tra |
| --- | --- |
| "" | SA/LCP đều rỗng, distinct=0 |
| "a" | SA=[0], LCP=[0], distinct=1 |
| "banana" | SA=[5,3,1,0,4,2], LCP=[0,1,3,0,0,2] |
| "aaaaa" | SA=[4,3,2,1,0], LCP=[0,1,2,3,4] |
| "mississippi" | LRS="issi", distinct=53 |
| "abracadabra" | LRS="abra", distinct=54 |
| "abababab" | LCP tăng theo các nhóm hậu tố |
| "zZ0" | thứ tự chữ hoa/thường/số theo UTF-16 |
| "😀a😀" | chỉ số, LCP tính theo UTF-16 |
| "a\u0000a" | ký tự code unit 0 thật, không trùng sentinel ảo |

### Tại sao oracle độc lập?

Nếu oracle tính LCP bằng chính hàm Kasai, cả hai có thể mắc cùng lỗi k--. So suffix bằng **substring trực tiếp** và LCP bằng **vòng lặp từng ký tự** dùng cơ chế khác hẳn, dễ phát hiện sai số.

Với dữ liệu dài, oracle brute-force quá chậm; chọn **n nhỏ nhưng nhiều cấu hình ngẫu nhiên**, đủ bắt lỗi indexing và các điều kiện biên. Sau đó thử thêm chuỗi dài dạng lặp để kiểm tra runtime.

### Property testing

Hai thuộc tính đặc biệt mạnh:

**SA là một hoán vị:** mọi giá trị từ 0 đến n−1 xuất hiện đúng một lần.

**Suffixes tăng chặt theo lex order:** với mọi r>0, s.substring(SA[r−1]) < s.substring(SA[r]) vì các vị trí bắt đầu khác nhau cho các suffix **khác nhau** của một chuỗi hữu hạn (hai suffix có thể có nội dung bằng nhau không? Nếu độ dài khác nhau thì không thể, nên thứ tự là chặt).

Mọi LCP[r] phải thỏa:

**0≤LCP[r]≤min(n−SA[r−1],n−SA[r])** với r>0.

Mọi truy vấn LCP(i,j) trả kết quả trong [0,min(n−i,n−j)] và đối xứng theo i,j.

## 21. Câu hỏi tự kiểm tra

**Câu 1.** Mảng LCP trong bài được định nghĩa thế nào?  
**Đáp án:** LCP[0]=0; LCP[r]=LCP của hai suffix bắt đầu tại SA[r−1] và SA[r], với r≥1.

**Câu 2.** SA của "banana" là gì?  
**Đáp án:** [5,3,1,0,4,2].

**Câu 3.** LCP của "banana" theo quy ước trên?  
**Đáp án:** [0,1,3,0,0,2].

**Câu 4.** rank[i] nghĩa là gì?  
**Đáp án:** Vị trí của suffix s[i..] trong SA; rank[SA[r]]=r.

**Câu 5.** Vì sao Kasai duyệt i=0..n−1 thay vì thứ tự SA?  
**Đáp án:** Tính chất tái sử dụng prefix k−1 áp dụng khi bỏ ký tự đầu và chuyển suffix i sang suffix i+1.

**Câu 6.** Kasai làm gì khi rank[i]=0?  
**Đáp án:** Không có predecessor trong SA; đặt k=0 và bỏ qua.

**Câu 7.** Vì sao Kasai có độ phức tạp O(n) dù chứa while bên trong for?  
**Đáp án:** Tổng lần tăng k bằng số so khớp thành công là O(n), vì k giảm tối đa 1 mỗi vòng, không thể âm và chỉ có tối đa một lần reset ở rank0.

**Câu 8.** Distinct substrings tính bằng công thức nào?  
**Đáp án:** n(n+1)/2−ΣLCP[r].

**Câu 9.** "banana" có bao nhiêu substring phân biệt?  
**Đáp án:** 15.

**Câu 10.** Longest repeated substring của "banana" là gì?  
**Đáp án:** "ana", độ dài 3.

**Câu 11.** Hai suffix tùy ý có rank a<b thì LCP bằng gì?  
**Đáp án:** min LCP[a+1..b].

**Câu 12.** Nếu so một suffix với chính nó, LCP bằng bao nhiêu?  
**Đáp án:** n−i với suffix bắt đầu tại i.

**Câu 13.** Khi dùng Sparse Table cho RMQ trên LCP, complexity?  
**Đáp án:** O(n log n) thời gian/bộ nhớ tiền xử lý và O(1) mỗi query.

**Câu 14.** Code xây SA bằng comparator-based doubling có complexity?  
**Đáp án:** O(n log²n), khác với Kasai O(n).

**Câu 15.** LRS max LCP có bảo đảm hai lần xuất hiện không chồng nhau không?  
**Đáp án:** Không; yêu cầu không chồng lấp cần xử lý bổ sung.

**Câu 16.** Java String.length() đếm gì với emoji?  
**Đáp án:** UTF-16 code units, không nhất thiết đếm Unicode code points.

**Câu 17.** Vì sao hậu tố rỗng không nằm trong SA của bài?  
**Đáp án:** Quy ước chỉ lấy các vị trí bắt đầu 0..n−1; không thêm sentinel thật.

**Câu 18.** Nếu cần SA+LCP sau khi chuỗi thay đổi ký tự, có dùng mảng cũ không?  
**Đáp án:** Không; tiền xử lý tĩnh không còn phản ánh chuỗi mới, phải xây lại hoặc dùng cấu trúc động thích hợp.

## 22. Tổng kết và checklist áp dụng

Để giải một bài có **mảng LCP/Kasai**:

1. **Xác nhận quy ước SA và LCP:** số hậu tố, sentinel, 0-based hay 1-based, LCP[0] là gì.
2. **Dựng SA đúng thứ tự từ điển** trên cùng cách mã hóa ký tự.
3. Xây **inverse rank**: rank[SA[r]]=r.
4. Với i tăng từ 0 tới n−1, so suffix i với **SA[rank[i]−1]** khi rank[i]>0.
5. **Tái sử dụng k và giảm k tối đa 1 sau mỗi suffix**, nhờ đó Kasai O(n).
6. Khi đếm substring phân biệt, dùng **n(n+1)/2−ΣLCP** và kiểu long.
7. Khi tìm repeated substring dài nhất, dùng **max LCP**, nhớ có thể chồng lấp.
8. Khi hỏi LCP(i,j) tùy ý, truy vấn **min trên LCP[rankLow+1..rankHigh]**; tự xử lý i=j.
9. Dùng **Segment Tree** cho O(log n) RMQ hoặc **Sparse Table** cho O(1) query khi LCP tĩnh.
10. Tách riêng complexity của **xây SA** với complexity của **Kasai**.
11. QA bằng cách so toàn suffix và tính LCP trực tiếp trên chuỗi nhỏ; thử cả chuỗi rỗng, một ký tự, toàn ký tự trùng và Unicode.
12. Nếu đề nói code points thay vì UTF-16 positions, đổi cách mã hóa ngay từ đầu.

**Tổng kết:** SA biến các suffix thành một danh sách có thứ tự; LCP mô tả mức khớp của những suffix kề nhau; thuật toán Kasai tận dụng quan hệ giữa suffix i và i+1 để xây LCP **trong O(n)**. Kết hợp rank và RMQ, ta có thể trả LCP của **bất kỳ hai suffix** nhanh, từ đó giải nhiều bài toán lặp chuỗi và đếm substring.
