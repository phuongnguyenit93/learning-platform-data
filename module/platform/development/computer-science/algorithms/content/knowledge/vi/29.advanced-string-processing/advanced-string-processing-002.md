# Mảng hậu tố và thứ tự từ điển của các hậu tố

**Mảng hậu tố** (*suffix array*, viết tắt `SA`) là một hoán vị của các vị trí bắt đầu trong một chuỗi, được sắp xếp sao cho **các hậu tố tương ứng tăng dần theo thứ tự từ điển**. Cấu trúc này biến những bài tưởng phải so sánh rất nhiều chuỗi con thành bài toán **sắp xếp và tìm kiếm trên các hậu tố**. Nó thường đi cùng **mảng LCP** (*longest common prefix*) và tìm kiếm nhị phân để tìm mẫu, phân tích các đoạn lặp, đếm số chuỗi con phân biệt và hỗ trợ nhiều bài xử lý chuỗi nâng cao.

Bài thuộc nhóm **Xử lý chuỗi nâng cao** trong Computer Science Algorithms. Ta sẽ xây dựng định nghĩa chuẩn xác, học cách so sánh hai hậu tố, thuật toán **prefix doubling** với cặp hạng `(rank[i], rank[i+len])`, chứng minh vì sao thứ tự đúng, phân tích độ phức tạp, tính LCP bằng **Kasai**, tìm mẫu nhờ tìm kiếm nhị phân trên mảng hậu tố, rồi triển khai một chương trình **Java 17 độc lập**. Mã dùng **Unicode code point** và được đối chiếu với cách duyệt ngây thơ trên hàng nghìn chuỗi.

## 1. Hậu tố và thứ tự từ điển

Cho chuỗi S dài n, đánh chỉ số từ **0**. **Hậu tố bắt đầu ở i** là:

\[
suffix(i)=S[i..n-1],\quad 0\le i<n.
\]

Ví dụ `S="banana"` có n=6:

| Vị trí i | Hậu tố S[i..n−1] |
| ---: | --- |
| 0 | banana |
| 1 | anana |
| 2 | nana |
| 3 | ana |
| 4 | na |
| 5 | a |

Một chuỗi độ dài n có **n hậu tố không rỗng**. Có thể xét thêm hậu tố rỗng `S[n..n-1]` trong một số định nghĩa/thư viện, nhưng **bài này chỉ đưa n hậu tố không rỗng vào SA**. Ta sẽ xử lý mẫu rỗng riêng.

### Thứ tự từ điển (lexicographic order)

Khi so sánh hai chuỗi X, Y:
1. Xét các ký tự ở hai chuỗi từ trái sang phải.
2. Ở ký tự đầu tiên khác nhau, chuỗi có ký tự nhỏ hơn đứng trước.
3. Nếu tất cả ký tự của chuỗi ngắn hơn đều trùng với đầu chuỗi dài hơn, **chuỗi ngắn hơn đứng trước**.

Ví dụ:
- `"a" < "ana"` vì "a" là tiền tố thật của "ana".
- `"ana" < "anana"` vì "ana" là tiền tố của "anana".
- `"banana" < "na"` vì ký tự đầu b đứng trước n.
- `"na" < "nana"` vì "na" ngắn hơn và là tiền tố của "nana".

**Thứ tự này không phải thứ tự theo độ dài, vị trí xuất hiện hay tần suất.** Nó so từng ký tự từ trái sang phải, và chỉ quan tâm độ dài khi một chuỗi là tiền tố của chuỗi kia.

### Unicode trong bài

Để có một quy ước rõ ràng, các chương trình ở đây so **giá trị Unicode code point** tại từng vị trí. Ví dụ emoji `🍎` được xem là **một code point**. Cách này không đồng nhất trong mọi trường hợp với `String.compareTo` của Java vì `String.compareTo` so theo **UTF-16 code unit**. Nó cũng không phải thứ tự từ điển theo ngôn ngữ tự nhiên (collation tiếng Việt). Đối với bài thuật toán, phải **chốt cùng một quy tắc so sánh ở mọi bước**.

Ký tự có dấu dựng sẵn và chuỗi gồm chữ cái cơ sở + dấu kết hợp có thể có code point khác nhau dù nhìn giống nhau. Mã không tự chuẩn hóa Unicode hoặc bỏ dấu. Nếu đề có yêu cầu chuẩn hóa NFC, so không phân biệt hoa/thường hoặc collation theo ngôn ngữ, cần tiền xử lý nhất quán và xem lại ý nghĩa vị trí đầu ra.

## 2. Mảng hậu tố SA là gì?

Mảng hậu tố `SA` dài n là một hoán vị của `[0,1,...,n-1]` sao cho:

\[
suffix(SA[0]) < suffix(SA[1]) < \dots < suffix(SA[n-1]).
\]

Các hậu tố ở vị trí bắt đầu khác nhau đều là các chuỗi khác nhau, nên khi so theo chuỗi đầy đủ, thứ tự là **nghiêm ngặt**.

Với `S="banana"`, sắp các hậu tố:

| Hạng r trong SA | SA[r] | Hậu tố | Vì sao đứng tại đây |
| ---: | ---: | --- | --- |
| 0 | 5 | a | Ngắn nhất trong các hậu tố bắt đầu bằng a |
| 1 | 3 | ana | Sau "a", trước "anana" |
| 2 | 1 | anana | Bắt đầu bằng a |
| 3 | 0 | banana | b đứng sau a, trước n |
| 4 | 4 | na | Tiền tố của "nana" |
| 5 | 2 | nana | Bắt đầu bằng n |

Kết quả:

\[
\boxed{SA=[5,3,1,0,4,2].}
\]

**Ý nghĩa chỉ số:** `SA[r]` là **vị trí bắt đầu của hậu tố có hạng từ điển r**. Nó **không** phải ký tự tại r, không phải số lần xuất hiện, và không phải độ dài hậu tố.

Mảng hạng ngược `rank[pos]` cho biết hậu tố bắt đầu tại pos đứng hạng nào trong SA. Với "banana", `rank[5]=0`, `rank[3]=1`, `rank[1]=2`, `rank[0]=3`, `rank[4]=4`, `rank[2]=5`. Mảng hạng ngược hữu ích khi tính LCP bằng Kasai và trả lời các truy vấn theo vị trí.

## 3. Cách đơn giản: sắp xếp các hậu tố trực tiếp

Một ý tưởng đầu tiên:
1. Tạo danh sách `0,1,...,n−1`.
2. Sắp xếp các chỉ số bằng comparator: so `S[i..]` và `S[j..]` ký tự theo ký tự.
3. Trả các vị trí sau khi sắp.

Cách này **đúng về mặt định nghĩa**, nhưng comparator có thể phải so **O(n)** ký tự mỗi lần. Với một thuật toán sort so sánh cần O(n log n) lần comparator, thời gian trường hợp xấu có thể là **O(n² log n)**. Nếu mỗi lần còn tạo `substring(i)` mới, ta dễ phát sinh sao chép bộ nhớ và đối tượng tạm không cần thiết.

Ví dụ `S="aaaaaaaa..."` có rất nhiều hậu tố trùng nhau ở tiền tố dài; comparator sẽ phải đi xa mới phân biệt vì hậu tố ngắn hơn đứng trước. Do đó cần cách **tái sử dụng kết quả so sánh**.

## 4. Prefix doubling — xếp hạng các tiền tố dài dần

Thuật toán **prefix doubling** xây thứ tự của các hậu tố bằng cách tăng dần độ dài tiền tố đã phân biệt: từ 1, 2, 4, 8, 16, … ký tự. Sau khoảng O(log n) vòng, độ dài so sánh đã đủ bao trùm hậu tố.

Ý tưởng trọng tâm là **thay so sánh chuỗi dài bằng so sánh cặp hai hạng số nguyên**.

### Hạng ban đầu của một ký tự

Đặt `rank[i]` bằng giá trị code point của ký tự tại i, hoặc bằng mã nén của ký tự. Khi đó so `rank[i]` chính là so tiền tố dài 1 của hậu tố bắt đầu ở i.

Trong Java của bài:
- `int[] codePoints` lưu từng code point của chuỗi.
- `rank[i]` ban đầu bằng code point ở i, không cần nén trước.
- Hạng giả của phần **ngoài chuỗi** là `−1`, nhỏ hơn mọi code point không âm.

Nếu hai hậu tố đã hết cùng một đoạn so sánh và một hậu tố hết sớm hơn, **−1** bảo đảm hậu tố ngắn hơn đứng trước.

### Từ len ký tự sang 2×len ký tự

Giả sử `rank[i]` hiện mã hóa thứ tự của đoạn **tối đa len ký tự** bắt đầu ở i; nếu đã chạm cuối chuỗi, phần ngắn hơn được so theo quy tắc kết thúc chuỗi. Ta muốn sắp theo đoạn dài tối đa 2×len:

\[
\boxed{key(i)=(rank[i],\ rank[i+len]).}
\]

Nếu `i+len\ge n`, hạng thứ hai là **−1**.

Lý do: tiền tố dài 2×len được chia thành hai nửa:
- Nửa đầu bắt đầu ở i, có thứ tự được mã bởi `rank[i]`.
- Nửa sau bắt đầu ở i+len, có thứ tự được mã bởi `rank[i+len]`.
- So cặp theo thứ tự từ điển là so nửa đầu trước, nếu hòa thì so nửa sau.

Sau khi sort các chỉ số theo cặp, ta **nén cặp bằng nhau thành cùng hạng mới** 0,1,2,... Tất cả các hậu tố có cùng tiền tố dài tối đa 2×len và cùng tình trạng kết thúc chuỗi nhận cùng hạng.

Không được **dùng ngay hạng mới** để so những cặp tiếp theo **trong cùng lượt**; mọi phép so của một vòng phải dựa trên snapshot `oldRank`. Chỉ sau khi đã gán toàn bộ `newRank` mới thay hạng cũ.

### Vì sao dùng −1 khi vượt cuối?

Ví dụ so các hậu tố `"a"` và `"ana"`. Sau khi cùng có phần đầu a, hậu tố "a" đã hết; hạng phần sau là −1, còn "ana" còn ký tự tiếp theo. Vì −1 nhỏ hơn hạng của một ký tự hợp lệ, "a" đứng trước "ana". Nếu dùng 0 bừa bãi trong khi hạng hợp lệ cũng bắt đầu từ 0, có thể vô tình **coi kết thúc chuỗi ngang với một hạng ký tự**, dẫn tới thứ tự sai. Chọn −1 tách biệt rõ ràng.

### Minh họa hai lượt trên "banana"

Ở lượt `len=1`, so từng cặp (ký tự hiện tại, ký tự kế tiếp) với phần ngoài chuỗi mang −1:

| i | Cặp 1+1 ký tự | Diễn giải |
| ---: | --- | --- |
| 0 | (b,a) | "ba" |
| 1 | (a,n) | "an" |
| 2 | (n,a) | "na" |
| 3 | (a,n) | "an" |
| 4 | (n,a) | "na" |
| 5 | (a,−1) | "a" đã hết |

Thứ tự theo cặp sau lượt đầu có thể là `[5,1,3,0,2,4]`: các hậu tố ở 1 và 3 còn hòa vì cùng bắt đầu bằng "an"; 2 và 4 còn hòa vì cùng "na". Hạng mới theo vị trí là:

~~~text
i:          0 1 2 3 4 5
rank after: 2 1 3 1 3 0
~~~

Ở lượt `len=2`, xét cặp hạng của hai khối dài 2:
- i=1: (rank[1],rank[3])=(1,1).
- i=3: (rank[3],rank[5])=(1,0). Vậy hậu tố i=3 đứng trước i=1.
- i=2: (3,3).
- i=4: (3,−1). Vậy hậu tố i=4 đứng trước i=2.

Sau sắp xếp, thứ tự hoàn chỉnh là:

\[
\boxed{SA=[5,3,1,0,4,2].}
\]

Vì tất cả hạng đã phân biệt (0..n−1), ta **dừng sớm** mà không cần thêm vòng.

## 5. Giả mã prefix doubling

~~~text
buildSuffixArray(codePoints):
    n = length(codePoints)
    if n == 0: return []

    SA = [0,1,...,n-1]
    rank = copy(codePoints)

    len = 1
    while len < n:
        sort SA by pair:
            (rank[i], rank[i+len] if i+len<n else -1)

        newRank[SA[0]] = 0
        for r = 1 .. n-1:
            prev = SA[r-1]
            now = SA[r]
            if pair(prev) != pair(now):
                newRank[now] = newRank[prev] + 1
            else:
                newRank[now] = newRank[prev]

        rank = newRank
        if rank[SA[n-1]] == n-1:
            break
        len *= 2

    return SA
~~~

Trong bản Java, ta dùng `Arrays.sort(Integer[],Comparator)` để sort các chỉ số theo cặp; `rank[]` được thay **sau khi** sort và nén xong. Trường `step` và tham chiếu `oldRank` của mỗi lượt là `final`, giúp comparator không vô tình đọc một hạng đã thay giữa chừng.

### Khi nào có thể dừng?

Nếu hạng cuối sau khi sort là `n−1`, ta đã có **n lớp hạng khác nhau**. Mọi hậu tố đã được phân biệt nên thứ tự hiện tại chính là thứ tự từ điển hoàn chỉnh.

Nếu chưa phân biệt hết, tăng `len` gấp đôi. Trong trường hợp xấu, sau O(log n) vòng, độ dài tiền tố đã xét không nhỏ hơn n nên mọi hậu tố khác nhau do vị trí kết thúc chuỗi. Với n=0 hoặc n=1 không cần sort.

### Độ phức tạp bản cài đặt Java trong bài

Mỗi vòng:
- `Arrays.sort` O(n log n) lần so sánh cặp.
- Một phép so cặp chỉ dùng **O(1)** phép truy cập hạng.
- Nén hạng O(n).

Có O(log n) vòng, nên:

\[
\boxed{O(n\log^2 n)\text{ thời gian, }O(n)\text{ bộ nhớ phụ}.}
\]

Đây là độ phức tạp của **bản dùng sort comparator** trong bài, không phải giới hạn tốt nhất của mọi thuật toán xây suffix array.

Có thể cải thiện thành **O(n log n)** bằng sort theo hai khóa nguyên bằng counting/radix sort trong mỗi vòng, hoặc dùng các thuật toán xây suffix array tuyến tính trong những mô hình nhất định (ví dụ SA-IS hoặc DC3). Các thuật toán này phức tạp hơn; phiên bản comparator dễ đọc và chứng minh cho người học Java.

**Phân biệt với cách sort trực tiếp suffix:** comparator prefix-doubling so **hai số nguyên**, không quét cả hậu tố, do đó tránh cận xấu O(n² log n) của việc so chuỗi đầy đủ trong mọi phép so.

## 6. Chứng minh thuật toán xây SA đúng

Ta chứng minh bằng bất biến sau mỗi vòng.

**Bất biến:** khi `rank[i]` đã được xây cho độ dài `len`, so sánh `rank[i]` và `rank[j]` cho đúng thứ tự từ điển của **tối đa len ký tự đầu** của hai hậu tố, có tính đến việc hậu tố nào hết sớm hơn.

**Cơ sở:** ban đầu len=1, `rank[i]` là code point ký tự đầu tiên. Hai ký tự khác nhau được xếp theo code point, ký tự giống nhau nhận hạng bằng nhau. Bất biến đúng.

**Bước quy nạp:** giả sử đúng cho len. Tiền tố dài tối đa 2len gồm hai khối len liên tiếp. Cặp `(rank[i],rank[i+len])` mã hóa thứ tự khối đầu và thứ tự khối sau. So cặp theo thứ tự từ điển chính là so tiền tố dài 2len, vì chỉ dùng khối sau khi khối đầu hòa. Nếu hậu tố kết thúc trước khi có khối sau, hạng −1 khiến nó đứng trước hậu tố dài hơn. Sort cặp và nén những cặp bằng nhau thành cùng hạng mới duy trì bất biến cho 2len.

Khi mọi hậu tố khác hạng, thứ tự hiện tại là **thứ tự từ điển đầy đủ**, có thể dừng. Nếu không, sau đủ số vòng để len≥n thì không hậu tố nào còn có thể hòa do độ dài khác nhau, thuật toán kết thúc.

**Điểm dễ mắc:** nếu so nửa sau bằng `rank[i+len]` mà quên kiểm tra i+len<n, sẽ truy cập vượt mảng. Nếu sentinel hạng −1 không tách biệt với hạng hợp lệ, so hậu tố tiền tố có thể sai. Nếu cập nhật rank tại chỗ trước khi nén hết, so cặp ở cuối lượt dùng thông tin khác với đầu lượt, phá bất biến.

## 7. Mảng LCP giữa các hậu tố kề nhau

Có suffix array, ta thường muốn biết **hai hậu tố đứng cạnh nhau trong thứ tự từ điển có tiền tố chung dài bao nhiêu**.

Định nghĩa:

\[
LCP[r]=\operatorname{lcp}(suffix(SA[r-1]),suffix(SA[r]))
\quad\text{với }r\ge1.
\]

Đặt `LCP[0]=0` theo quy ước. Mảng LCP có cùng n phần tử với SA.

Với "banana":

| r | SA[r] | Hậu tố | LCP với hậu tố ngay trước |
| ---: | ---: | --- | ---: |
| 0 | 5 | a | 0 |
| 1 | 3 | ana | 1 (a) |
| 2 | 1 | anana | 3 (ana) |
| 3 | 0 | banana | 0 |
| 4 | 4 | na | 0 |
| 5 | 2 | nana | 2 (na) |

Kết quả:

\[
\boxed{LCP=[0,1,3,0,0,2].}
\]

Lưu ý `LCP[r]` **không** phải độ dài hậu tố SA[r], cũng không phải LCP của hậu tố đứng cùng vị trí trong văn bản. Nó so **hai hậu tố kề nhau trong SA**.

### Tính LCP bằng Kasai trong O(n)

Kasai dùng mảng `rank[pos]` là thứ hạng **cuối cùng** của hậu tố pos trong SA. Duyệt vị trí gốc i từ 0 đến n−1, xét hậu tố ngay trước nó trong SA:

~~~text
rank[SA[r]] = r

k = 0
for i = 0 .. n-1:
    r = rank[i]
    if r == 0:
        k = 0
        continue

    j = SA[r-1]
    while i+k<n and j+k<n and S[i+k]==S[j+k]:
        k++
    LCP[r] = k

    if k > 0:
        k--
~~~

**Vì sao có thể giữ lại k−1?** Nếu hai hậu tố bắt đầu ở i và j có chung k ký tự, khi bỏ ký tự đầu, hậu tố ở i+1 và j+1 vẫn có chung ít nhất k−1 ký tự. Trong thứ tự từ điển, LCP của hậu tố ở i+1 với **hậu tố kề trước thực sự của nó** không nhỏ hơn k−1 theo tính chất các suffix nằm giữa một cặp có chung tiền tố. Vì vậy khi i tăng lên một, ta có thể bắt đầu so từ k−1 thay vì 0. Từng lần tăng k làm tiến thêm một ký tự chưa được tính, tổng các lần tăng trên toàn bộ vòng lặp chỉ O(n); mỗi lượt giảm k nhiều nhất 1.

Kết quả: **Kasai O(n) thời gian, O(n) bộ nhớ** (rank ngược và LCP).

### Đoạn lặp dài nhất

Giá trị lớn nhất trong LCP là độ dài của một **chuỗi con xuất hiện ít nhất hai lần** dài nhất. Với "banana", `max(LCP)=3`, một chuỗi lặp dài nhất là `"ana"`. Với "aaaa", `max(LCP)=3`, một chuỗi lặp dài nhất là `"aaa"` (các lần xuất hiện có thể chồng lấn).

Nếu bài yêu cầu các lần xuất hiện **không chồng lấn**, chỉ lấy max LCP không đủ; cần thêm ràng buộc khoảng cách giữa vị trí bắt đầu.

## 8. Đếm số chuỗi con phân biệt bằng SA và LCP

Một chuỗi độ dài n có tổng `n(n+1)/2` đoạn con **không rỗng theo vị trí** (có thể trùng nội dung). Ta muốn đếm số **nội dung chuỗi con khác nhau**.

Khi duyệt các hậu tố theo SA:
- Hậu tố bắt đầu ở SA[r] có `n−SA[r]` tiền tố không rỗng, mỗi tiền tố là một chuỗi con của S.
- `LCP[r]` tiền tố đầu đã xuất hiện trong những hậu tố đứng trước; do thứ tự từ điển, số nội dung **mới** mà hậu tố này mang lại là `(n−SA[r])−LCP[r]`.

Vì vậy:

\[
\boxed{\operatorname{distinctSubstrings}(S)=
\sum_{r=0}^{n-1}(n-SA[r]-LCP[r])
=\frac{n(n+1)}{2}-\sum_{r=0}^{n-1}LCP[r].}
\]

Ví dụ `S="banana"`:
- Tổng đoạn con theo vị trí: `6×7/2=21`.
- Tổng LCP: `0+1+3+0+0+2=6`.
- Số chuỗi con không rỗng phân biệt: **21−6=15**.

Với `S="aaaa"`:
- Tổng đoạn theo vị trí =10.
- LCP `[0,1,2,3]`, tổng=6.
- Có **4** chuỗi con phân biệt: "a", "aa", "aaa", "aaaa".

Với chuỗi rỗng, theo quy ước chỉ đếm chuỗi con **không rỗng** nên kết quả 0. Nếu đề hỏi cả chuỗi rỗng, cộng thêm 1.

### Vì sao chỉ trừ LCP kề trước là đủ?

Trong danh sách hậu tố đã sort, mọi hậu tố bắt đầu bằng cùng một tiền tố tạo thành một **đoạn liên tiếp**. Khi xét suffix mới SA[r], phần tiền tố đã thấy ở các suffix đứng trước có độ dài tối đa chính bằng LCP với hậu tố **liền trước** SA[r−1]. Vì vậy chỉ cần trừ LCP[r], không phải so suffix mới với mọi suffix cũ.

Đó là ứng dụng cốt lõi của việc **sắp xếp hậu tố theo từ điển**.

## 9. Tìm một mẫu P bằng tìm kiếm nhị phân trên SA

Giả sử có văn bản S đã xây SA và mẫu P. Ta muốn tìm những vị trí j sao cho:

\[
S[j..j+|P|-1]=P.
\]

Các hậu tố bắt đầu bằng P tạo thành **một đoạn liên tiếp trong SA**, vì chúng nằm gần nhau theo thứ tự từ điển.

Ta có thể dùng **hai lần binary search** để tìm đoạn đó:
- `lowerBound`: hậu tố đầu tiên **không nhỏ hơn P** theo phép so khớp tiền tố.
- `upperBound`: vị trí đầu tiên **lớn hơn P** theo cùng phép so.

Phép so đặc biệt giữa hậu tố và mẫu:
1. So từng code point từ đầu hai chuỗi.
2. Nếu gặp ký tự khác, trả dấu thứ tự tại ký tự ấy.
3. Nếu đọc hết mẫu P mà không khác, trả **0 (mẫu là tiền tố của hậu tố)**.
4. Nếu hậu tố kết thúc trước khi đọc hết P, hậu tố nhỏ hơn mẫu (trả −1).

Như vậy mọi hậu tố có tiền tố P cho comparator trả 0, tạo thành đoạn `[lowerBound,upperBound)` trong SA.

### Vị trí xuất hiện theo thứ tự nào?

SA sắp **theo hậu tố từ điển**, vì vậy nếu lấy trực tiếp `SA[lo..hi)`, các vị trí có thể không tăng theo vị trí trong văn bản. Chương trình bài này **sắp lại các vị trí khớp tăng dần** trước khi trả.

Ví dụ với `S="banana"`, mẫu `P="ana"` xuất hiện tại **[1,3]** theo vị trí văn bản. Trong SA, hai suffix khớp là `SA[1]=3` ("ana") và `SA[2]=1` ("anana"), nên vùng kết quả ban đầu có thứ tự **[3,1]**. Sau sort tăng theo vị trí, kết quả là `[1,3]`.

Các ví dụ:
- `find("ana", "banana")=[1,3]`.
- `find("na", "banana")=[2,4]`.
- `find("aa", "aaaa")=[0,1,2]` — các kết quả **chồng lấn** vẫn hợp lệ.
- `find("x", "banana")=[]`.

### Mẫu rỗng

Bài định nghĩa `SA` chỉ gồm n hậu tố **không rỗng**. Nhưng mẫu rỗng theo quy ước tìm chuỗi có thể khớp tại **n+1 ranh giới** `0,1,...,n`, kể cả sau ký tự cuối. Vì vậy chương trình xử lý `P=""` riêng, không tìm mẫu rỗng bằng cách duyệt SA thuần túy.

### Độ phức tạp tìm kiếm

Nếu mỗi so sánh hậu tố với mẫu P dài m mất tối đa O(m):
- Hai lần binary search trên n hậu tố: **O(m log n)**.
- Có k lần khớp, việc thu k vị trí và sắp chúng **theo vị trí trong văn bản** tốn O(k log k) nếu dùng sort so sánh.

Vì vậy bản API trả **vị trí tăng dần trong văn bản** có cận:

\[
\boxed{O(m\log n+k\log k)\text{ thời gian/truy vấn}.}
\]

Nếu chỉ muốn biết có xuất hiện hay không, có thể dừng ở đoạn khớp không rỗng sau O(m log n). Nếu chấp nhận thứ tự từ điển của các hậu tố, việc trả toàn bộ k kết quả chỉ thêm O(k) mà không cần sort. Với n=0, mẫu không rỗng không có kết quả; mẫu rỗng trả [0].

Có thể cải thiện tìm kiếm nhị phân bằng thông tin LCP, nhưng cần cài đặt và chứng minh những tối ưu đó riêng; không nên tuyên bố bản tìm kiếm comparator đơn giản ở đây đạt O(m+log n).

## 10. Ví dụ đối chiếu các loại chuỗi

### Chuỗi "mississippi"

Mảng hậu tố 0-based:

~~~text
SA  = [10,7,4,1,0,9,8,6,3,5,2]
LCP = [0,1,1,4,0,0,1,0,2,1,3]
~~~

Ta có n=11, tổng đoạn con theo vị trí `11×12/2=66`; tổng LCP bằng 13, nên **53** chuỗi con không rỗng phân biệt. Đoạn lặp dài nhất có độ dài 4, một đáp án là `"issi"`. Mẫu `"issi"` xuất hiện tại các vị trí **[1,4]**.

### Chuỗi "aaaa"

~~~text
SA  = [3,2,1,0]
LCP = [0,1,2,3]
~~~

Hậu tố ngắn hơn luôn đứng trước khi là tiền tố của hậu tố dài hơn. Đây là phản ví dụ tốt cho việc so cặp hạng mà không dùng sentinel −1. Mẫu "aa" xuất hiện tại [0,1,2].

### Chuỗi "abab"

~~~text
SA  = [2,0,3,1]
LCP = [0,2,0,1]
~~~

Hậu tố "ab" ở vị trí 2 đứng trước "abab" ở vị trí 0. Tổng đoạn theo vị trí là 10, tổng LCP 3, nên có **7** chuỗi con phân biệt.

### Chuỗi có Unicode ngoài BMP

Với `S="🍎a🍎a"`, theo **code point** S dài 4:

~~~text
Code point positions: [🍎, a, 🍎, a]
SA  = [3,1,2,0]
LCP = [0,1,0,2]
~~~

Mẫu `"🍎a"` xuất hiện tại vị trí code point **[0,2]**. Nhưng vì emoji đầu chiếm **2 UTF-16 code unit**, offset tương ứng trong Java String là **[0,3]**, không phải [0,2]. Nếu muốn gọi `String.substring`, phải chuyển vị trí code point sang UTF-16 offset, chứ không lấy trực tiếp chỉ số SA.

## 11. Java 17: suffix array, Kasai, tìm mẫu và kiểm thử

Chương trình này **chạy độc lập**, không cần thư viện ngoài JDK:
- `Index` nhận một String và chuyển thành `int[] codePoints`.
- `buildSuffixArray` sort các hạng theo **cặp rank cũ** trong từng lượt nhân đôi.
- `buildLcp` cài Kasai tuyến tính trên mảng code point.
- `occurrences` dùng **hai binary search** để tìm các hậu tố bắt đầu bằng mẫu P, trả vị trí **tăng dần theo code point**.
- `toUtf16Offsets` đổi vị trí đó sang offset UTF-16 nếu cần dùng API String.
- `distinctSubstrings` đếm số chuỗi con không rỗng khác nhau bằng SA/LCP.
- `longestRepeated` lấy một chuỗi con lặp dài nhất từ max LCP, cho phép những lần xuất hiện chồng lấn.
- `naiveSuffixArray`, `naiveLcp`, `naiveOccurrences` và `naiveDistinct` là các oracle nhỏ **không sử dụng prefix doubling/Kasai/binary search**.
- `verify` kiểm thử tập chuỗi nhị phân, tam phân và Unicode xác định.

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

public class SuffixArrayLexicographicDemo {
    static final class Index {
        final String source;
        final int[] codePoints;
        final int[] sa;
        final int[] lcp;
        final int[] utf16Offset;

        Index(String source) {
            this.source = Objects.requireNonNull(
                    source, "source");
            this.codePoints = source.codePoints().toArray();
            this.sa = buildSuffixArray(codePoints);
            this.lcp = buildLcp(codePoints, sa);

            utf16Offset = new int[codePoints.length + 1];
            for (int i = 0; i < codePoints.length; i++) {
                utf16Offset[i + 1] = utf16Offset[i]
                        + Character.charCount(codePoints[i]);
            }
        }

        // O(n log^2 n) voi Arrays.sort(comparator).
        static int[] buildSuffixArray(int[] s) {
            int n = s.length;
            if (n == 0) return new int[0];

            Integer[] order = new Integer[n];
            int[] rank = Arrays.copyOf(s, n);
            for (int i = 0; i < n; i++) order[i] = i;

            for (int len = 1; len < n;
                    len = len >= n / 2 ? n : len * 2) {
                final int step = len;
                final int[] oldRank = rank;

                // Tat ca comparator trong VONG nay
                // phai doc cung mot snapshot oldRank.
                Arrays.sort(order, (a, b) -> {
                    int first = Integer.compare(
                            oldRank[a], oldRank[b]);
                    if (first != 0) return first;

                    int a2 = step < n - a
                            ? oldRank[a + step] : -1;
                    int b2 = step < n - b
                            ? oldRank[b + step] : -1;
                    return Integer.compare(a2, b2);
                });

                int[] nextRank = new int[n];
                nextRank[order[0]] = 0;

                for (int r = 1; r < n; r++) {
                    int a = order[r - 1];
                    int b = order[r];

                    int a2 = step < n - a
                            ? oldRank[a + step] : -1;
                    int b2 = step < n - b
                            ? oldRank[b + step] : -1;
                    boolean different =
                            oldRank[a] != oldRank[b]
                            || a2 != b2;

                    nextRank[b] = nextRank[a]
                            + (different ? 1 : 0);
                }

                rank = nextRank;
                if (rank[order[n - 1]] == n - 1) {
                    break;
                }
            }

            int[] result = new int[n];
            for (int i = 0; i < n; i++) {
                result[i] = order[i];
            }
            return result;
        }

        // Kasai O(n), lcp[0]=0.
        static int[] buildLcp(int[] s, int[] sa) {
            int n = s.length;
            int[] lcp = new int[n];
            int[] rank = new int[n];
            for (int r = 0; r < n; r++) {
                rank[sa[r]] = r;
            }

            int common = 0;
            for (int i = 0; i < n; i++) {
                int r = rank[i];
                if (r == 0) {
                    common = 0;
                    continue;
                }

                int j = sa[r - 1];
                while (i + common < n && j + common < n
                        && s[i + common] == s[j + common]) {
                    common++;
                }
                lcp[r] = common;
                if (common > 0) common--;
            }
            return lcp;
        }

        // So suffix S[start..] voi PATTERN.
        // 0 nghia la pattern la tien to cua suffix.
        private int compareSuffixPrefix(int start, int[] p) {
            int suffixLength = codePoints.length - start;
            for (int j = 0; j < p.length; j++) {
                if (j >= suffixLength) return -1;
                int compare = Integer.compare(
                        codePoints[start + j], p[j]);
                if (compare != 0) return compare;
            }
            return 0;
        }

        // Vi tri 0-based theo Unicode CODE POINT;
        // ket qua tang dan theo vi tri trong van ban.
        int[] occurrences(String pattern) {
            Objects.requireNonNull(pattern, "pattern");
            int[] p = pattern.codePoints().toArray();
            int n = sa.length;

            // Khong dua hau to rong vao SA, nhung mau
            // rong khop tai n+1 ranh gioi.
            if (p.length == 0) {
                int[] result = new int[n + 1];
                for (int i = 0; i <= n; i++) result[i] = i;
                return result;
            }
            if (p.length > n) return new int[0];

            int lo = 0, hi = n;
            while (lo < hi) {
                int mid = lo + (hi - lo) / 2;
                if (compareSuffixPrefix(sa[mid], p) < 0) {
                    lo = mid + 1;
                } else {
                    hi = mid;
                }
            }
            int first = lo;

            hi = n;
            while (lo < hi) {
                int mid = lo + (hi - lo) / 2;
                if (compareSuffixPrefix(sa[mid], p) <= 0) {
                    lo = mid + 1;
                } else {
                    hi = mid;
                }
            }

            int[] hits = Arrays.copyOfRange(sa, first, lo);
            Arrays.sort(hits); // Tra theo vi tri van ban.
            return hits;
        }

        int[] toUtf16Offsets(int[] codePointPositions) {
            int[] out = new int[codePointPositions.length];
            for (int i = 0; i < out.length; i++) {
                int position = codePointPositions[i];
                if (position < 0
                        || position >= utf16Offset.length) {
                    throw new IllegalArgumentException(
                            "Invalid code point position");
                }
                out[i] = utf16Offset[position];
            }
            return out;
        }

        // SA khong chua suffix rong. Khong dem substring rong.
        long distinctSubstrings() {
            long n = codePoints.length;
            long total = n * (n + 1L) / 2L;
            for (int value : lcp) total -= value;
            return total;
        }

        String suffixAt(int rankIndex) {
            int start = sa[rankIndex];
            return new String(codePoints, start,
                    codePoints.length - start);
        }

        int longestRepeatedLength() {
            int best = 0;
            for (int x : lcp) best = Math.max(best, x);
            return best;
        }

        // Tra mot longest repeated substring, "" neu khong co.
        String longestRepeated() {
            int best = longestRepeatedLength();
            if (best == 0) return "";

            for (int r = 1; r < lcp.length; r++) {
                if (lcp[r] == best) {
                    return new String(
                            codePoints, sa[r], best);
                }
            }
            throw new AssertionError("Broken LCP array");
        }
    }

    // Oracle: so truc tiep hai suffix theo tung code point.
    static int compareSuffixes(int[] s, int a, int b) {
        while (a < s.length && b < s.length) {
            if (s[a] != s[b]) {
                return Integer.compare(s[a], s[b]);
            }
            a++;
            b++;
        }
        if (a == s.length && b == s.length) return 0;
        return a == s.length ? -1 : 1;
    }

    static int[] naiveSuffixArray(int[] s) {
        Integer[] order = new Integer[s.length];
        for (int i = 0; i < s.length; i++) order[i] = i;
        Arrays.sort(order,
                (a, b) -> compareSuffixes(s, a, b));
        int[] result = new int[s.length];
        for (int i = 0; i < result.length; i++) {
            result[i] = order[i];
        }
        return result;
    }

    static int[] naiveLcp(int[] s, int[] sa) {
        int[] result = new int[sa.length];
        for (int r = 1; r < sa.length; r++) {
            int i = sa[r - 1], j = sa[r];
            while (i + result[r] < s.length
                    && j + result[r] < s.length
                    && s[i + result[r]] == s[j + result[r]]) {
                result[r]++;
            }
        }
        return result;
    }

    static int[] naiveOccurrences(int[] s, int[] p) {
        List<Integer> positions = new ArrayList<>();
        for (int i = 0; i + p.length <= s.length; i++) {
            boolean equal = true;
            for (int j = 0; j < p.length; j++) {
                if (s[i + j] != p[j]) {
                    equal = false;
                    break;
                }
            }
            if (equal) positions.add(i);
        }
        int[] result = new int[positions.size()];
        for (int i = 0; i < result.length; i++) {
            result[i] = positions.get(i);
        }
        return result;
    }

    static long naiveDistinctSubstrings(int[] s) {
        Set<String> seen = new HashSet<>();
        for (int start = 0; start < s.length; start++) {
            for (int len = 1; start + len <= s.length; len++) {
                seen.add(new String(s, start, len));
            }
        }
        return seen.size();
    }

    static List<String> allWords(
            String[] alphabet, int maxLength) {
        List<String> out = new ArrayList<>();
        List<String> layer = new ArrayList<>();
        out.add("");
        layer.add("");

        for (int len = 1; len <= maxLength; len++) {
            List<String> next = new ArrayList<>();
            for (String prefix : layer) {
                for (String symbol : alphabet) {
                    next.add(prefix + symbol);
                }
            }
            out.addAll(next);
            layer = next;
        }
        return out;
    }

    static final class Counter {
        int strings, patternQueries;
    }
    record Stats(int strings, int patternQueries) {}

    static void check(
            String text, List<String> patterns, Counter c) {
        Index index = new Index(text);
        int[] s = text.codePoints().toArray();

        int[] expectedSa = naiveSuffixArray(s);
        if (!Arrays.equals(index.sa, expectedSa)) {
            throw new AssertionError("Suffix array: " + text);
        }
        if (!Arrays.equals(
                index.lcp, naiveLcp(s, expectedSa))) {
            throw new AssertionError("LCP: " + text);
        }
        if (index.distinctSubstrings()
                != naiveDistinctSubstrings(s)) {
            throw new AssertionError(
                    "Distinct substrings: " + text);
        }
        c.strings++;

        for (String pattern : patterns) {
            int[] actual = index.occurrences(pattern);
            int[] expected = naiveOccurrences(
                    s, pattern.codePoints().toArray());
            if (!Arrays.equals(actual, expected)) {
                throw new AssertionError(
                        "Pattern " + pattern + " in " + text);
            }

            // Offset UTF-16 phai dung voi Java String API.
            int[] offsets = index.toUtf16Offsets(actual);
            for (int offset : offsets) {
                if (!text.startsWith(pattern, offset)) {
                    throw new AssertionError(
                            "Bad UTF-16 offset");
                }
            }
            c.patternQueries++;
        }
    }

    static int randomState = 3802026;
    static int randomInt(int bound) {
        randomState = randomState * 1664525
                + 1013904223;
        return (int) (Integer.toUnsignedLong(randomState)
                % bound);
    }

    static Stats verify() {
        Counter c = new Counter();

        List<String> binaryTexts =
                allWords(new String[]{"a", "b"}, 8);
        List<String> binaryPatterns =
                allWords(new String[]{"a", "b"}, 5);
        for (String text : binaryTexts) {
            check(text, binaryPatterns, c);
        }

        List<String> ternaryTexts =
                allWords(new String[]{"a", "b", "c"}, 6);
        List<String> ternaryPatterns =
                allWords(new String[]{"a", "b", "c"}, 4);
        for (String text : ternaryTexts) {
            check(text, ternaryPatterns, c);
        }

        String[] symbols = {
            "a", "b", "🙂", "🍎", "é", "ắ", "#", "𝄞"
        };
        for (int test = 0; test < 2000; test++) {
            int n = randomInt(15);
            int m = randomInt(7);
            StringBuilder text = new StringBuilder();
            StringBuilder pat = new StringBuilder();
            for (int i = 0; i < n; i++) {
                text.append(symbols[randomInt(symbols.length)]);
            }
            for (int i = 0; i < m; i++) {
                pat.append(symbols[randomInt(symbols.length)]);
            }
            check(text.toString(),
                    List.of(pat.toString()), c);
        }

        // 511 + 1093 + 2000 = 3604 texts.
        // 511*63 + 1093*121 + 2000 = 166446 queries.
        if (c.strings != 3604 || c.patternQueries != 166446) {
            throw new AssertionError("Unexpected test count");
        }
        return new Stats(c.strings, c.patternQueries);
    }

    public static void main(String[] args) {
        Index banana = new Index("banana");
        System.out.println("banana.sa="
                + Arrays.toString(banana.sa));
        System.out.println("banana.lcp="
                + Arrays.toString(banana.lcp));
        System.out.println("banana.distinct="
                + banana.distinctSubstrings());
        System.out.println("banana.longestRepeated="
                + banana.longestRepeated());
        System.out.println("banana.find(ana)="
                + Arrays.toString(banana.occurrences("ana")));
        System.out.println("banana.find(na)="
                + Arrays.toString(banana.occurrences("na")));
        System.out.println("banana.find(x)="
                + Arrays.toString(banana.occurrences("x")));

        System.out.println("banana suffixes:");
        for (int rank = 0; rank < banana.sa.length; rank++) {
            System.out.println(rank + ": " + banana.sa[rank]
                    + " -> " + banana.suffixAt(rank)
                    + " (LCP=" + banana.lcp[rank] + ")");
        }

        Index mississippi = new Index("mississippi");
        System.out.println("mississippi.sa="
                + Arrays.toString(mississippi.sa));
        System.out.println("mississippi.lcp="
                + Arrays.toString(mississippi.lcp));
        System.out.println("mississippi.distinct="
                + mississippi.distinctSubstrings());
        System.out.println("mississippi.longestRepeated="
                + mississippi.longestRepeated());
        System.out.println("mississippi.find(issi)="
                + Arrays.toString(
                    mississippi.occurrences("issi")));

        Index repeated = new Index("aaaa");
        System.out.println("aaaa.sa="
                + Arrays.toString(repeated.sa));
        System.out.println("aaaa.lcp="
                + Arrays.toString(repeated.lcp));
        System.out.println("aaaa.distinct="
                + repeated.distinctSubstrings());
        System.out.println("aaaa.find(aa)="
                + Arrays.toString(repeated.occurrences("aa")));

        Index empty = new Index("");
        System.out.println("empty.sa="
                + Arrays.toString(empty.sa));
        System.out.println("empty.find(empty)="
                + Arrays.toString(empty.occurrences("")));

        Index unicode = new Index("🍎a🍎a");
        System.out.println("unicode.sa="
                + Arrays.toString(unicode.sa));
        System.out.println("unicode.lcp="
                + Arrays.toString(unicode.lcp));
        int[] hits = unicode.occurrences("🍎a");
        System.out.println("unicode.codePointMatches="
                + Arrays.toString(hits));
        System.out.println("unicode.utf16Matches="
                + Arrays.toString(
                    unicode.toUtf16Offsets(hits)));

        Stats stats = verify();
        System.out.println("testedStrings=" + stats.strings());
        System.out.println(
                "testedPatternQueries=" + stats.patternQueries());
    }
}
~~~

Lưu chương trình vào tệp **SuffixArrayLexicographicDemo.java**. Chạy bằng **JDK 17 trở lên**:

~~~bash
javac SuffixArrayLexicographicDemo.java
java SuffixArrayLexicographicDemo
~~~

**Đầu ra dự kiến chính xác theo mã:**

~~~text
banana.sa=[5, 3, 1, 0, 4, 2]
banana.lcp=[0, 1, 3, 0, 0, 2]
banana.distinct=15
banana.longestRepeated=ana
banana.find(ana)=[1, 3]
banana.find(na)=[2, 4]
banana.find(x)=[]
banana suffixes:
0: 5 -> a (LCP=0)
1: 3 -> ana (LCP=1)
2: 1 -> anana (LCP=3)
3: 0 -> banana (LCP=0)
4: 4 -> na (LCP=0)
5: 2 -> nana (LCP=2)
mississippi.sa=[10, 7, 4, 1, 0, 9, 8, 6, 3, 5, 2]
mississippi.lcp=[0, 1, 1, 4, 0, 0, 1, 0, 2, 1, 3]
mississippi.distinct=53
mississippi.longestRepeated=issi
mississippi.find(issi)=[1, 4]
aaaa.sa=[3, 2, 1, 0]
aaaa.lcp=[0, 1, 2, 3]
aaaa.distinct=4
aaaa.find(aa)=[0, 1, 2]
empty.sa=[]
empty.find(empty)=[0]
unicode.sa=[3, 1, 2, 0]
unicode.lcp=[0, 1, 0, 2]
unicode.codePointMatches=[0, 2]
unicode.utf16Matches=[0, 3]
testedStrings=3604
testedPatternQueries=166446
~~~

### Đọc kết quả

- `banana.sa` là dãy **vị trí bắt đầu** của các hậu tố đã sort, không phải chỉ số chữ cái.
- `banana.lcp` là độ dài tiền tố chung với hậu tố **đứng ngay trước trong SA**, nên phần tử đầu bằng 0.
- `banana.distinct=15` được tính từ `n(n+1)/2−sum(LCP)`.
- `banana.longestRepeated=ana` là một đoạn lặp dài nhất có độ dài 3; các lần xuất hiện có thể chồng lấn.
- `banana.find(ana)=[1,3]` đã được **sort theo vị trí văn bản**; trong chính SA thứ tự hai hậu tố tương ứng lại là [3,1].
- `mississippi.distinct=53` và `aaaa.distinct=4` là các đối chiếu hữu ích cho phần lý thuyết.
- `empty.find(empty)=[0]` là quy ước mẫu rỗng khớp ở mọi ranh giới; với văn bản rỗng chỉ có một ranh giới.
- `unicode.codePointMatches=[0,2]` nhưng `unicode.utf16Matches=[0,3]` cho thấy **khác biệt code point và UTF-16 offset**.

### Lưu ý phạm vi API

`Index` giả định dữ liệu chuỗi **không thay đổi** sau khi xây; Java String vốn bất biến. Nếu văn bản T thay đổi, phải xây lại Index hoặc dùng cấu trúc chuyên xử lý cập nhật động. Chương trình không áp dụng cho một suffix array đã xây từ văn bản cũ nhưng dùng như thể T được sửa.

Chương trình không dùng sentinel trong chính chuỗi đầu vào để sort. Nó dùng **giá trị −1 cho hạng ngoài biên** khi xét cặp rank; mọi code point từ String là số nguyên không âm nên không trùng. Vì vậy văn bản có ký tự `#`, ký tự null hay emoji vẫn không va chạm với sentinel. Lưu ý đây là sentinel **nội bộ trong comparator**, không phải ký tự chèn vào văn bản.

Trong dữ liệu cực lớn, chi phí boxing các chỉ số thành `Integer[]` và `Arrays.sort` có thể đáng kể; có thể chuyển sang radix/counting sort hai hạng để giảm bộ nhớ đối tượng và cải thiện tốc độ. Về cơ bản, độ phức tạp n log²n vẫn đủ tốt cho nhiều ví dụ học tập và bài tập cỡ vừa, nhưng không nên mặc định đáp ứng mọi ràng buộc n rất lớn.

## 12. Kiểm thử độc lập

Mã có nhiều oracle đơn giản:
- `naiveSuffixArray` sắp hậu tố bằng comparator đọc trực tiếp từng code point từ hai vị trí đầu tới lúc khác hoặc hết chuỗi.
- `naiveLcp` so trực tiếp từng cặp hậu tố kề nhau sau khi sort.
- `naiveOccurrences` quét mọi vị trí, so trực tiếp mẫu với đoạn con.
- `naiveDistinctSubstrings` liệt kê mọi đoạn con không rỗng vào `HashSet<String>`, đếm nội dung khác nhau.

Những oracle này chậm hơn thuật toán tối ưu nhưng **không sử dụng cặp rank, Kasai, phép đếm theo LCP hoặc binary search**, nên có ích để phát hiện lỗi một cách tương đối độc lập.

### Bộ vét cạn

| Nhóm | Chuỗi văn bản | Mẫu mỗi văn bản | Số truy vấn mẫu |
| --- | ---: | ---: | ---: |
| Bảng chữ cái {a,b}, văn bản dài 0..8 | 511 | 63 mẫu dài 0..5 | 32.193 |
| Bảng chữ cái {a,b,c}, văn bản dài 0..6 | 1.093 | 121 mẫu dài 0..4 | 132.253 |
| Unicode giả ngẫu nhiên xác định, độ dài 0..14 | 2.000 | 1 mẫu dài 0..6 | 2.000 |
| **Tổng** | **3.604** | | **166.446** |

Các ký hiệu Unicode dùng trong nhóm cuối gồm chữ ASCII, dấu `#`, chữ có dấu như `é`, `ắ`, emoji `🙂`, `🍎` và ký tự ngoài BMP `𝄞`. Chương trình dùng bộ sinh số xác định để tạo kết quả có thể lặp lại.

Với **mỗi** trong 3.604 văn bản:
1. So toàn bộ `SA` với danh sách hậu tố được sort trực tiếp.
2. So toàn bộ `LCP` với phép đếm tiền tố chung trực tiếp.
3. So số chuỗi con phân biệt theo SA/LCP với kết quả tạo `Set<String>` từ mọi đoạn con.
4. Với từng mẫu được giao, so **toàn bộ danh sách vị trí tìm thấy** bằng hai cách.
5. Chuyển các vị trí code point sang UTF-16 offset và xác minh `text.startsWith(pattern,offset)`.

Tổng **166.446 truy vấn mẫu** đã đối chiếu. Bản Java cũng kiểm tra đúng các con số thống kê kỳ vọng để phát hiện nếu vòng sinh dữ liệu bị sửa mà không cập nhật QA.

**Giới hạn của kiểm thử:** Đây không phải bằng chứng cho mọi chuỗi có thể có; độ đúng tổng quát dựa trên bất biến prefix doubling, tính đúng Kasai và tính đơn điệu của các hậu tố có cùng tiền tố trong SA. Chương trình Java được lập luận và đối chiếu với mô hình thuật toán độc lập; nếu dùng trong sản xuất, vẫn nên biên dịch, chạy unit test và benchmark theo môi trường triển khai.

## 13. Các lỗi thường gặp và cách tránh

| Lỗi | Tác hại | Cách khắc phục |
| --- | --- | --- |
| Ghi SA là các hậu tố dạng String | Lãng phí bộ nhớ, khó nối với vị trí | Lưu **vị trí bắt đầu** |
| Hiểu SA[r] là hạng của hậu tố r | Đảo chiều mảng SA/rank | SA[hạng]=vị trí, rank[vị trí]=hạng |
| So suffix theo độ dài | Không còn thứ tự từ điển | So ký tự đầu tiên khác nhau |
| Hậu tố ngắn là tiền tố của dài nhưng đặt sau | Đảo "a" và "ana" | Kết thúc chuỗi đứng trước |
| Sentinel trùng một hạng hợp lệ | Gộp nhầm hậu tố hết sớm | Dùng −1 và hạng không âm |
| Sort cặp nhưng thay rank ngay trong comparator | Các phép so đọc hạng không nhất quán | Dùng snapshot oldRank |
| Không nén cặp bằng nhau thành cùng rank | Mất bất biến hạng tiền tố | Cặp bằng nhau nhận cùng rank |
| Không nhân đôi len | Không xét đủ hậu tố | len: 1,2,4,8,... |
| Không kiểm tra i+len<n | Out-of-bounds | Hạng thứ hai −1 khi ngoài |
| Nhầm O(n log²n) thành O(n log n) với comparator sort | Đánh giá thời gian sai | Counting/radix sort để đạt O(n log n) |
| Tính LCP giữa vị trí liền kề trong văn bản | Không phải LCP của SA | So hậu tố SA[r−1] và SA[r] |
| Quên đặt LCP[0]=0 | Giả định phần tử đầu vô nghĩa | Công bố quy ước |
| Trong Kasai không giảm k khi i tăng | Có thể đếm LCP sai và mất tuyến tính | Sau lượt i giảm k tối đa 1 |
| Đếm chuỗi con khác nhau mà quên trừ LCP | Đếm trùng nội dung | Dùng n(n+1)/2−sum(LCP) |
| Binary search dùng comparator hậu tố đầy đủ nhưng kiểm tra match sai | Đoạn tìm không như mong đợi | Dùng comparator dừng khi hết mẫu |
| Trả thứ tự SA nhưng nói là thứ tự vị trí T | Kết quả không tăng theo văn bản | Sort các vị trí khớp nếu cần |
| Không xét mẫu rỗng | Thiếu ranh giới n | Trả n+1 vị trí theo hợp đồng |
| Dùng String.length như số code point | Lệch trên emoji | Chọn rõ code point hoặc UTF-16 |
| So Unicode bằng quy tắc khác nhau giữa build/search | Kết quả không ổn định | Đồng nhất thứ tự so sánh |
| Dùng int cho số chuỗi con với n lớn | Có thể tràn | Dùng long cho n(n+1)/2 |

### Ràng buộc bộ nhớ và số học

Một Java String có độ dài UTF-16 khác số code point khi có ký tự ngoài BMP. `codePoints().toArray()` tạo mảng `int[]` và bản Index còn cần SA, LCP, rank tạm, order tạm. Tất cả đều O(n) phần tử nhưng có hệ số bộ nhớ đáng kể. Kiểm tra giới hạn heap và số phần tử trước khi chạy với văn bản rất dài.

Công thức số lượng đoạn con phải nhân bằng `long`, ví dụ `((long)n*(n+1L))/2`. Mã dùng `long` cho tổng và cho số lượng đoạn con phân biệt; nếu dùng `int` khi n lớn có thể tràn.

Đối với những ứng dụng yêu cầu so theo **thứ tự từ điển ngôn ngữ tự nhiên**, suffix array theo code point của bài là một mô hình **khác**. Các chuẩn hóa/collation có thể thay đổi tính liền mạch hoặc quan hệ tiền tố; không được áp dụng thứ tự khác vào comparator tìm mẫu khi SA đã xây theo code point.

## 14. Bài tập có đáp án

**Bài 1 — liệt kê hậu tố.** Với S="abc", các hậu tố không rỗng là gì?

*Đáp án:* "abc" ở 0, "bc" ở 1, "c" ở 2.

**Bài 2 — sắp thứ tự.** S="aba", suffix array 0-based là gì?

*Đáp án:* Hậu tố "a" ở 2, "aba" ở 0, "ba" ở 1. SA=[2,0,1].

**Bài 3 — hậu tố tiền tố.** Giữa "a" và "anana", chuỗi nào đứng trước?

*Đáp án:* "a" vì nó là tiền tố của "anana" và ngắn hơn.

**Bài 4 — banana.** Với S="banana", SA và hậu tố ở hạng 2?

*Đáp án:* SA=[5,3,1,0,4,2]. Hạng 2 là SA[2]=1, hậu tố "anana".

**Bài 5 — hạng ngược.** Với SA của "banana", rank[4] bằng mấy?

*Đáp án:* Hậu tố bắt đầu ở 4 ("na") có hạng 4, nên rank[4]=4.

**Bài 6 — cặp hạng.** Nếu len=2, i=4 và n=6, hạng thứ hai lấy ở đâu?

*Đáp án:* i+len=6 ngoài chuỗi, nên dùng −1.

**Bài 7 — hai nửa.** Vì sao cặp `(rank[i],rank[i+len])` mô tả tiền tố tối đa 2len?

*Đáp án:* Tiền tố được chia thành hai khối len: so khối đầu, nếu hòa mới so khối sau; rank mã hóa đúng thứ tự của từng khối theo bất biến.

**Bài 8 — hạng còn hòa.** Nếu nhiều suffix còn cùng hạng sau lượt len=1, có được dừng vì SA đã có một thứ tự không?

*Đáp án:* Không. Cần tiếp tục nhân đôi tới khi mọi suffix khác hạng hoặc đã xét đủ chiều dài; thứ tự nội bộ nhóm hòa chưa được xác định.

**Bài 9 — LCP banana.** LCP của "ana" và "anana" bằng bao nhiêu?

*Đáp án:* 3, vì ba ký tự đầu "ana" trùng.

**Bài 10 — LCP mảng.** Với SA=[5,3,1,0,4,2] trên "banana", LCP là gì?

*Đáp án:* [0,1,3,0,0,2].

**Bài 11 — đoạn lặp.** S="aaaa", đoạn con lặp dài nhất (cho phép chồng lấn) dài bao nhiêu?

*Đáp án:* 3, đó là "aaa" tại vị trí 0 và 1.

**Bài 12 — số chuỗi con.** S="banana" có bao nhiêu chuỗi con không rỗng phân biệt?

*Đáp án:* n(n+1)/2−sum(LCP)=21−6=15.

**Bài 13 — chuỗi rỗng.** SA của S="" là gì? Tìm mẫu rỗng trong chuỗi rỗng trả kết quả nào ở bài?

*Đáp án:* SA=[], và mẫu rỗng khớp tại ranh giới duy nhất [0].

**Bài 14 — vị trí mẫu.** S="banana", P="ana". Vì sao hai suffix chứa mẫu đứng cạnh nhau dù vị trí văn bản [1,3] không nằm theo thứ tự đó trong SA?

*Đáp án:* Vì tất cả suffix bắt đầu bằng cùng tiền tố P tạo thành đoạn liên tiếp theo thứ tự từ điển; SA có [3,1] trong đoạn, nhưng API sort kết quả thành [1,3].

**Bài 15 — khớp chồng lấn.** Với S="aaaa", P="aa", các vị trí?

*Đáp án:* [0,1,2]. Không bỏ lần khớp nào dù các đoạn trùng nhau.

**Bài 16 — Unicode.** S="🍎a🍎a", P="🍎a". Chỉ số code point và UTF-16?

*Đáp án:* [0,2] theo code point; [0,3] theo UTF-16 String.

**Bài 17 — độ phức tạp.** Bản prefix doubling dùng Arrays.sort comparator mỗi vòng có thời gian thế nào?

*Đáp án:* O(n log²n). Kasai thêm O(n). Có thể đạt O(n log n) nếu sort cặp hạng nguyên bằng counting/radix sort đúng.

**Bài 18 — tìm mẫu.** Nếu đã có SA và mẫu dài m, cần tìm và in k vị trí theo thứ tự tăng trong văn bản, thời gian bản bài là gì?

*Đáp án:* O(m log n + k log k) trong cách cài hai binary search và sort kết quả k vị trí.

**Bài 19 — công thức distinct.** Vì sao không cần so suffix mới với mọi suffix trước để trừ chuỗi con trùng?

*Đáp án:* Do các suffix cùng tiền tố tạo thành đoạn liền nhau trong SA; độ dài tiền tố trùng lớn nhất với tập trước được quyết định bởi suffix kề ngay trước.

**Bài 20 — Unicode normalization.** Hai chuỗi có thể nhìn giống nhau nhưng khác code point. Thuật toán này tự coi chúng bằng nhau không?

*Đáp án:* Không. Muốn coi bằng nhau phải định nghĩa và thực hiện chuẩn hóa nhất quán trước khi xây chỉ mục và tìm kiếm, đồng thời xử lý mapping vị trí về văn bản gốc.

## 15. Checklist trước khi dùng suffix array

1. Chốt rõ hậu tố có gồm hậu tố **rỗng** hay không; bài này không gồm.
2. Chốt hệ chỉ số **0-based** và định nghĩa chính xác `SA[rank]=startPosition`.
3. Chốt thứ tự so sánh: trong mã là **code point lexicographic**, không phải Java UTF-16 compareTo hay collation tiếng Việt.
4. Với prefix doubling, giữ snapshot `oldRank`, so cặp `(oldRank[i],oldRank[i+len])`, ngoài biên là −1.
5. Nén cùng cặp thành cùng hạng; chỉ dừng khi n hậu tố đã khác hạng.
6. Phân biệt cận của bản comparator sort O(n log²n) với bản radix sort O(n log n).
7. Khi cần LCP, xây rank ngược rồi dùng **Kasai O(n)**; LCP[0]=0.
8. Đếm chuỗi con phân biệt bằng `n(n+1)/2−sum(LCP)`, dùng `long`.
9. Khi tìm mẫu, nhớ các suffix có tiền tố P tạo thành **đoạn liên tiếp trong SA**; tìm hai biên.
10. So hậu tố với P dừng **ngay khi hết P**, coi đó là khớp; trả mọi vị trí có thể chồng lấn.
11. Nếu yêu cầu kết quả theo vị trí văn bản tăng dần, sort riêng các start position tìm được.
12. Mẫu rỗng và văn bản rỗng cần hợp đồng rõ ràng, không suy từ SA không chứa hậu tố rỗng.
13. Với Unicode, phân biệt code point offset và UTF-16 String offset; chuẩn hóa chỉ khi đề yêu cầu.
14. Kiểm tra với "banana", "aaaa", "mississippi", chuỗi rỗng, ký tự lặp, emoji và mẫu không xuất hiện.
15. Đối chiếu SA/LCP/occurrences/distinct với oracle ngây thơ trên chuỗi nhỏ; sau đó mới tối ưu hiệu năng.

## Ghi nhớ

- `SA` là **hoán vị vị trí bắt đầu hậu tố**, sao cho các hậu tố được xếp **theo thứ tự từ điển**.
- Nếu một hậu tố là **tiền tố** của hậu tố khác, hậu tố ngắn hơn phải đứng trước.
- **Prefix doubling** so hai hạng của hai khối liên tiếp, tăng độ dài khối 1→2→4→8…; bản sort comparator Java tốn **O(n log²n)** và O(n) bộ nhớ phụ.
- **Kasai** tính LCP giữa hai suffix kề nhau trong SA bằng **O(n)**.
- **Số chuỗi con không rỗng phân biệt** là `n(n+1)/2−sum(LCP)`.
- **Tất cả hậu tố bắt đầu bằng mẫu P** tạo thành một đoạn liên tiếp trong SA; dùng **hai tìm kiếm nhị phân** để xác định đoạn, rồi sắp vị trí kết quả nếu cần theo thứ tự văn bản.
- Với Unicode, chương trình trả chỉ số **code point**; có thể đổi sang **UTF-16 offset** để dùng API Java String.
- Các bộ kiểm thử độc lập trên **3.604 chuỗi** và **166.446 truy vấn mẫu** giúp phát hiện lỗi hạng, sentinel, LCP, thứ tự và chuyển chỉ số.
