# Phân biệt cấu trúc cho khóa số nguyên với cây chỉ dựa vào phép so sánh

Một tập hợp gồm 100.000 mã định danh có thể được lưu bằng **cây tìm kiếm cân bằng**, **bảng băm**, **bitset** hoặc **cấu trúc chuyên biệt cho khóa số nguyên**. Cùng hỗ trợ thao tác tìm kiếm, nhưng các cấu trúc này khác nhau ở thông tin chúng khai thác: cây tìm kiếm thông thường chỉ cần biết khóa nào nhỏ hơn, bằng hay lớn hơn; cấu trúc dành cho số nguyên còn có thể dùng **giá trị chỉ số, các bit của khóa và kích thước miền khóa**.

Điều này giải thích vì sao cây cân bằng có thời gian $O(\log n)$, trong khi mảng đánh chỉ số trực tiếp có thể kiểm tra tồn tại trong $O(1)$, hoặc một số cấu trúc nguyên hỗ trợ truy vấn tiền nhiệm trong $O(\log\log U)$. Các kết quả đó đúng trong **những mô hình tính toán và điều kiện bộ nhớ khác nhau**. Bài học này giúp phân biệt chúng và biết khi nào mỗi cách tiếp cận đáng sử dụng.

## 1. Khóa số nguyên có thêm thông tin gì?

Xét một từ điển lưu cặp $(k,v)$, trong đó $k$ là khóa và $v$ là dữ liệu gắn với khóa. Có hai kiểu thông tin mà thuật toán có thể sử dụng:

- **Thông tin thứ tự:** hỏi $a<b$, $a=b$ hay $a>b$. Điều này áp dụng cho số nguyên, chuỗi, ngày giờ hoặc bất kỳ loại khóa nào có phép so sánh nhất quán.
- **Thông tin biểu diễn:** dùng trực tiếp khóa để tính chỉ số mảng, lấy bit thứ $i$, tách một tiền tố nhị phân, tính giá trị băm hoặc chia miền khóa thành những đoạn số học.

Ví dụ, với bốn khóa $\{3,5,9,12\}$, một cây tìm kiếm cân bằng có thể tổ chức các khóa bằng các quan hệ $3<5<9<12$. Một trie theo bit lại phân biệt chúng qua biểu diễn 4 bit:

| Khóa | Biểu diễn 4 bit | Tiền tố 2 bit |
|---|---|---|
| 3 | `0011` | `00` |
| 5 | `0101` | `01` |
| 9 | `1001` | `10` |
| 12 | `1100` | `11` |

Trie có thể định hướng ngay theo bit đầu tiên, trong khi một cây tìm kiếm nhị phân dựa vào phép so sánh sẽ phân nhánh theo kết quả so với khóa đang nằm ở nút. Hai cách đều hợp lệ; khác biệt nằm ở **những phép toán được phép sử dụng để quyết định hướng đi**.

### Ba tham số cần biết

| Ký hiệu | Diễn giải |
|---|---|
| $n$ | Số khóa phân biệt **đang được lưu** trong tập hợp hoặc từ điển |
| $U$ | Số giá trị khóa có thể xuất hiện (*universe size*), thường chuẩn hóa thành $[0,U)$ |
| $w$ | Số bit của biểu diễn khóa mà thuật toán sử dụng |

Nếu biểu diễn vừa đủ thì $w=\lceil\log_2 U\rceil$ (với $U\ge2$). Trong một kiểu số nguyên 64 bit, ta vẫn có thể chỉ sử dụng miền $[0,1000)$, nên **không thể tự kết luận** $U=2^{64}$. Với khóa phân biệt, $n\le U$.

Khóa âm có thể chuẩn hóa bằng phép dịch miền; chẳng hạn khóa từ $-20$ đến $79$ được ánh xạ thành $0$ đến $99$ bằng cách cộng $20$. Việc chuẩn hóa cần giữ tính một-một, và nếu thao tác phụ thuộc thứ tự thì cần giữ đúng thứ tự số học.

## 2. Mô hình chỉ dựa vào phép so sánh

Trong **mô hình so sánh** (*comparison model*), thuật toán chỉ biết thứ tự các khóa thông qua các phép so sánh. Nó không được sử dụng trực tiếp mẫu bit hoặc giá trị của khóa làm chỉ số để rẽ nhánh. Ví dụ, mã sinh viên là chuỗi hay số nguyên đều có thể lưu trong cùng một cây đỏ-đen, miễn là tồn tại một thứ tự so sánh hợp lệ.

Cây tìm kiếm nhị phân duy trì bất biến:

- Mọi khóa trong cây con trái nhỏ hơn khóa của nút hiện tại.
- Mọi khóa trong cây con phải lớn hơn khóa của nút hiện tại.
- Nếu cấu trúc cho phép khóa trùng, cần định nghĩa cách xử lý phần tử trùng hoặc gắn nhiều giá trị vào một khóa; trong ví dụ này ta giả sử khóa phân biệt.

Cây nhị phân tìm kiếm **không cân bằng** có thể cao tới $n$ khi chèn khóa theo thứ tự tăng dần, dẫn đến tìm/chèn/xóa $O(n)$ trong trường hợp xấu nhất. AVL hoặc cây đỏ-đen bổ sung bất biến cân bằng nên chiều cao luôn $O(\log n)$, và các thao tác này có thời gian $O(\log n)$ trong trường hợp xấu nhất, khi mỗi lần so sánh khóa được tính là $O(1)$.

### Vì sao xuất hiện $\Omega(\log n)$?

Giả sử đã có $n$ khóa phân biệt được sắp thứ tự $k_1<k_2<\cdots<k_n$, và miền truy vấn có các giá trị nằm giữa những khóa liên tiếp. Một truy vấn **tiền nhiệm** của $x$ (khóa lớn nhất nhỏ hơn $x$) phải phân biệt $n+1$ khoảng:

1. $x<k_1$;
2. $k_i<x<k_{i+1}$, với mỗi $i$ từ $1$ đến $n-1$;
3. $x>k_n$.

Nếu chỉ dùng các phép so sánh nhị phân để xác định vị trí trong những khoảng đó, cây quyết định có ít nhất $n+1$ lá; độ sâu lớn nhất ít nhất $\lceil\log_2(n+1)\rceil$. Vì vậy, truy vấn tiền nhiệm có **cận dưới trường hợp xấu nhất** $\Omega(\log n)$ theo số phép so sánh trong mô hình này. Nếu miền nguyên quá hẹp để có giá trị ở tất cả những khoảng, việc xác định đúng thứ hạng của truy vấn bằng so sánh vẫn phải phân biệt tới $n$ khóa đầu vào khác nhau; cận dưới theo bậc $\Omega(\log n)$ vẫn thể hiện giới hạn của mô hình so sánh.

Đây là một **giới hạn của mô hình thuật toán**. Nó không nói rằng mọi cấu trúc có khóa số nguyên đều phải mất $\Omega(\log n)$: một thuật toán được phép dùng phép toán bit, bảng tra hoặc đánh chỉ số có thể tránh việc ra quyết định hoàn toàn qua so sánh.

### Ưu điểm và giới hạn của cây so sánh

**Ưu điểm:** không cần biết trước miền khóa $U$; bộ nhớ thường là $O(n)$ nút; hỗ trợ thứ tự tăng/giảm, tìm min/max, tiền nhiệm, kế nhiệm và truy vấn khoảng. Thời gian $O(\log n)$ của cây cân bằng là bảo đảm trường hợp xấu nhất cho các thao tác chuẩn.

**Giới hạn:** cây chỉ tận dụng quan hệ thứ tự. Nếu tất cả khóa nằm trong một miền nguyên nhỏ, nó không tự khai thác được việc ta có thể truy cập trực tiếp ô thứ $k$. Chi phí của phép so sánh cũng phải tính thêm khi một khóa dài hơn từ máy và không thể so sánh trong một thao tác.

## 3. Mô hình word-RAM cho khóa số nguyên

Nhiều phân tích cấu trúc khóa số nguyên dùng mô hình **word-RAM**: một từ máy chứa $W$ bit; cộng/trừ, so sánh, AND, OR, XOR, dịch bit và truy cập mảng tại chỉ số hợp lệ của một từ máy được tính là $O(1)$.

Khi $w\le W$, khóa số nguyên có thể nằm trong một từ máy. Khi $w>W$, biểu diễn một khóa cần ít nhất $\lceil w/W\rceil$ từ, nên những phép toán phải quét toàn khóa không còn là $O(1)$ theo tham số $w$. Cũng không thể giả định có thể cấp phát một mảng độ dài $U$ chỉ vì một thao tác truy cập theo chỉ số được tính là hằng số.

Mô hình word-RAM cho phép nhiều kỹ thuật:

| Khả năng | Ý tưởng sử dụng |
|---|---|
| Đánh chỉ số từ khóa | Truy cập trực tiếp vị trí `table[k]` |
| Lấy bit thứ $i$ | Chọn nhánh 0/1 trong trie nhị phân |
| Tách phần cao và thấp của khóa | Chia đệ quy miền khóa trong van Emde Boas |
| Băm biểu diễn khóa | Tra cứu trung bình nhanh trong bảng băm |
| Xử lý nhiều cờ trong một từ | Dùng bitset và các phép toán bit song song |

**Bảng băm không chỉ dành cho số nguyên**: chuỗi và nhiều loại đối tượng khác cũng có thể băm được. Điểm liên quan ở đây là bảng băm cho phép tra cứu bằng một phép ánh xạ khóa, thay vì chỉ lần lượt so sánh thứ tự trong một cây. Độ phức tạp kỳ vọng của bảng băm đòi hỏi các giả định thích hợp về hàm băm, tải bảng và xử lý va chạm.

## 4. Những cấu trúc khai thác miền khóa và bit

### 4.1. Mảng đánh chỉ số trực tiếp (*direct-address table*)

Nếu khóa hợp lệ thuộc $[0,U)$ và đủ khả năng cấp phát $U$ ô, ta dùng khóa làm chỉ số:

```text
table = mảng U ô, ban đầu đều rỗng

contains(k):
    nếu k < 0 hoặc k >= U: trả_về false
    trả_về table[k] không rỗng

insert(k, value):
    yêu_cầu 0 <= k < U
    table[k] = value

erase(k):
    yêu_cầu 0 <= k < U
    table[k] = rỗng
```

Cả ba thao tác tốn $O(1)$ sau khi cấp phát. Nhưng **khởi tạo và bộ nhớ** phụ thuộc $U$: $O(U)$ ô hoặc từ máy, kể cả khi chỉ lưu vài khóa. Nếu giá trị gắn với khóa có thể là `null`, phải dùng cờ hiện diện hoặc cách mã hóa ô trống riêng.

### 4.2. Bitset

Nếu chỉ cần biết khóa **có trong tập hay không**, mỗi khóa có thể biểu diễn bằng một bit. Với từ máy $W$ bit, bit của khóa $k$ nằm ở:

$$
\text{wordIndex}=\lfloor k/W\rfloor,\qquad
\text{bitIndex}=k\bmod W.
$$

Tra cứu, chèn và xóa chỉ cần đọc hoặc cập nhật một từ máy, tức $O(1)$ trong mô hình đã cấp phát, với khóa hợp lệ. Bộ nhớ là $\Theta(U)$ **bit**, hay $\Theta(\lceil U/W\rceil)$ từ máy. Bitset không tự lưu `value` cho từng khóa.

Với bitset **không có chỉ mục bổ sung**, muốn tìm tiền nhiệm của $k$ có thể phải quét nhiều từ máy trước vị trí $k$. Trong trường hợp xấu nhất, việc quét có thể kiểm tra $O(\lceil U/W\rceil)$ từ máy; nếu giả định có thao tác tìm bit bật cao nhất trong một từ là $O(1)$ (như trên nhiều CPU với độ rộng từ cố định), đó cũng là chặn trên của thời gian quét. Không được đồng nhất tra cứu hiện diện $O(1)$ với tiền nhiệm $O(1)$.

### 4.3. Trie nhị phân theo bit

Mỗi mức trong trie xét một bit. Với khóa dài $w$ bit, đường từ gốc đến khóa có tối đa $w$ cạnh. Một thao tác tra cứu có thể viết bằng giả mã:

```text
contains(x):
    node = root
    cho i từ w - 1 xuống 0:
        bit = (x >> i) & 1
        node = node.child[bit]
        nếu node là rỗng: trả_về false
    trả_về node.terminal
```

Với trie nhị phân không nén, tìm/chèn/xóa có chặn trên $O(w)$ và bộ nhớ có thể lên tới $O(nw)$ nút. Nếu lưu thông tin cây con không rỗng, có thể tìm tiền nhiệm/kế nhiệm theo các nhánh bit trong $O(w)$ bước. **Trie nén đường đi (Patricia trie)** tiết kiệm các đoạn chỉ có một nhánh và có thể dùng $O(n)$ nút, nhưng độ phức tạp truy vấn vẫn phụ thuộc cách biểu diễn và cài đặt.

Cây so sánh có chiều cao phụ thuộc **số khóa** $n$; trie nhị phân có số mức phụ thuộc **độ dài khóa** $w$. Nếu $w=32$ và số khóa rất lớn, 32 mức là một giới hạn dễ hình dung. Nếu khóa có độ dài hàng nghìn bit và chỉ vài khóa, cây so sánh có thể phù hợp hơn.

### 4.4. van Emde Boas và y-fast trie

**van Emde Boas (vEB)** tổ chức khóa bằng cách chia miền thành các cụm theo phần bit cao/thấp, và dùng cấu trúc đệ quy để quản lý các cụm có phần tử. Trong phiên bản cổ điển, với miền thường giả định có kích thước là lũy thừa của 2, tìm/chèn/xóa và tiền nhiệm/kế nhiệm chạy trong $O(\log\log U)$; bộ nhớ là $O(U)$ từ máy.

**y-fast trie** là ví dụ cấu trúc nâng cao đạt tiền nhiệm/kế nhiệm **kỳ vọng** $O(\log w)$, với không gian $O(n)$ từ máy và thời gian cập nhật khấu hao kỳ vọng $O(\log w)$, trong mô hình word-RAM và với cơ chế băm thích hợp. Nó tiết kiệm không gian trên miền thưa nhưng cài đặt khó hơn cây cân bằng.

Các biểu thức $\log\log U$ và $\log w$ chỉ tương đương về bậc tăng khi $w=\Theta(\log U)$. Nếu dùng trường khóa 64 bit để lưu miền hợp lệ rất nhỏ, hãy phân biệt **độ dài biểu diễn** và **miền khóa thực tế**.

## 5. Bảng so sánh các lựa chọn

Giả sử khóa vừa một từ máy, cấu trúc đã được khởi tạo, và thao tác truy vấn là tra cứu chính xác hoặc tìm tiền nhiệm. Chữ “không trực tiếp” nghĩa là muốn thực hiện truy vấn cần thuật toán hoặc chỉ mục bổ sung.

| Cấu trúc | Tra cứu hiện diện | Tiền nhiệm/kế nhiệm | Không gian điển hình | Bảo đảm chính |
|---|---|---|---|---|
| Cây AVL / đỏ-đen | $O(\log n)$ | $O(\log n)$ | $O(n)$ nút | Trường hợp xấu nhất |
| Mảng đã sắp xếp | $O(\log n)$ bằng tìm kiếm nhị phân | $O(\log n)$ bằng tìm kiếm nhị phân | $O(n)$ ô | Chèn/xóa có thể $O(n)$ do dịch phần tử |
| Bảng băm | $O(1)$ kỳ vọng | Không trực tiếp | $O(n)$ từ máy | Giả định băm/tải phù hợp; trường hợp xấu có thể $O(n)$ |
| Bảng trực tiếp | $O(1)$ | Quét đến ô gần nhất: $O(U)$ trường hợp xấu | $O(U)$ ô | Tra cứu nhanh, dùng bộ nhớ theo miền |
| Bitset cơ bản | $O(1)$ | Có thể quét $O(\lceil U/W\rceil)$ từ máy; thời gian phụ thuộc phép tìm bit trong một từ | $\Theta(U)$ bit | Gọn khi chỉ lưu cờ hiện diện |
| Trie nhị phân không nén | $O(w)$ | $O(w)$ nếu duy trì đủ thông tin nhánh | Tối đa $O(nw)$ nút | Chi phí phụ thuộc bit khóa |
| van Emde Boas cổ điển | $O(\log\log U)$ | $O(\log\log U)$ | $O(U)$ từ máy | Giả định miền nguyên hữu hạn, cấu trúc đệ quy |
| y-fast trie | $O(\log w)$ kỳ vọng | $O(\log w)$ kỳ vọng | $O(n)$ từ máy | Cập nhật khấu hao kỳ vọng; cài đặt phức tạp |

Trong bảng, “tra cứu hiện diện” ở bảng trực tiếp/bitset không tính thời gian khởi tạo toàn bộ miền. Tương tự, $O(n)$ từ máy của bảng băm không nói rõ hệ số chiếm chỗ do bucket, vùng trống và metadata.

## 6. Một tập khóa, nhiều cách trả lời truy vấn

Xét $S=\{3,5,9,12\}$ trên miền $[0,16)$, nên $n=4$, $U=16$, $w=4$. Ta cần trả lời:

| Truy vấn | Kết quả |
|---|---|
| `contains(9)` | `true` |
| `contains(10)` | `false` |
| `predecessor(10)` | $9$ |
| `successor(10)` | $12$ |
| `range(4,10)` | $\{5,9\}$ nếu lấy khoảng đóng $[4,10]$ |

**Cây tìm kiếm cân bằng:** Dựa vào so sánh với một số khóa trên đường đi. Các truy vấn nêu trên có thể làm trong $O(\log n)$ để định vị; khi liệt kê $k$ kết quả trong khoảng, tổng chi phí thường là $O(\log n+k)$.

**Bảng trực tiếp hoặc bitset:** Kiểm tra `contains(9)` bằng một chỉ số hoặc một bit. Muốn trả lời `predecessor(10)`, có thể quét từ 9 xuống 0 đến khóa có cờ hiện diện; giải pháp này phù hợp khi $U=16$, nhưng không mặc nhiên tốt nếu $U$ lên tới hàng tỷ.

**Trie theo bit:** `contains(9)` đi theo nhánh `1 → 0 → 0 → 1`. Để tìm tiền nhiệm của 10 (nhị phân `1010`), ta tìm nhánh có khóa lớn nhất vẫn nhỏ hơn 10; kết quả là `1001` tương ứng 9. Các quyết định dựa vào từng bit, thay vì so sánh 10 với một khóa nguyên nằm ở mỗi nút.

Ví dụ này cho thấy tính chất **có thứ tự** và tính chất **được đánh chỉ số** là hai yêu cầu khác nhau. Một bảng băm có thể trả lời `contains(9)` nhanh nhưng không tự biết rằng 9 đứng ngay trước 10 trong tập.

## 7. Số nguyên còn thay đổi mô hình sắp xếp

Phân biệt mô hình không chỉ áp dụng cho từ điển. Trong mô hình **sắp xếp chỉ bằng so sánh**, việc sắp xếp $n$ phần tử phân biệt có cận dưới $\Omega(n\log n)$ lần so sánh trong trường hợp xấu nhất.

Nếu khóa là số nguyên có miền đã biết, thuật toán có thể khai thác trực tiếp giá trị:

- **Counting sort:** $O(n+U)$ thời gian và $O(n+U)$ bộ nhớ phụ ở phiên bản ổn định thường gặp. Hữu ích khi $U$ nhỏ; sẽ tốn kém nếu $U$ cực lớn so với $n$.
- **Radix sort:** chia khóa $w$ bit thành $d=\lceil w/r\rceil$ chữ số, mỗi chữ số có $B=2^r$ giá trị. Dùng counting sort ổn định ở mỗi lượt cho thời gian $O(d(n+B))$ và bộ nhớ phụ $O(n+B)$.

Chẳng hạn, với khóa 32 bit và $r=8$, ta có $d=4$ lượt và $B=256$ bucket ở mỗi lượt. Cách này không cần một mảng có $2^{32}$ ô đếm. Nếu khóa có dấu, mã hóa chữ số phải được xử lý sao cho thứ tự sau cùng đúng với thứ tự số học.

Counting sort và radix sort không mâu thuẫn với cận dưới $\Omega(n\log n)$ vì chúng **sử dụng các phép toán ngoài so sánh** và trả thêm chi phí theo miền khóa hoặc biểu diễn khóa.

## 8. Phân tích ví dụ bộ nhớ và tốc độ

Giả sử cần lưu $n=100.000$ khóa 32 bit phân biệt, mỗi khóa nằm bất kỳ trong $[0,2^{32})$. Với $U=2^{32}$:

- Bitset cần $2^{32}$ bit, tức **512 MiB**, kể cả khi chỉ có 100.000 bit bật.
- Bảng trực tiếp với mỗi ô 8 byte cần $2^{32}\times8$ byte, tức **32 GiB** chỉ riêng các ô.
- Cây cân bằng dùng $O(n)$ nút, với $n=100.000$; số byte cụ thể phụ thuộc con trỏ, payload và cách cấp phát.
- Bảng băm dùng $O(n)$ mục/cấu trúc phụ ở tải thích hợp, với $n=100.000$, và cho tra cứu hiện diện kỳ vọng $O(1)$.

Một cây cân bằng có độ sâu $O(\log n)$; $\log_2(100.000)\approx16{,}6$ giúp ước lượng bậc số phép so sánh. vEB có $O(\log\log U)$, và $\log_2\log_2(2^{32})=5$, nhưng **5 không phải số lần truy cập RAM chính xác**; hơn nữa, cấu trúc vEB cổ điển có chi phí bộ nhớ tỷ lệ với toàn miền.

Đổi tình huống: khóa nằm trong $[0,65536)$, và tập hiện diện có tới 40.000 khóa. Bitset cần $65536/8=8192$ byte, tức **8 KiB**. Trong trường hợp này, ưu thế của miền nhỏ rất lớn; nếu chỉ lưu trạng thái có/không, bitset có thể phù hợp hơn nhiều cấu trúc nút động.

Có một giới hạn thực nghiệm: hai thuật toán có cùng bậc $O(\cdot)$ có thể chênh lệch thời gian do truy cập bộ nhớ, cache, phân nhánh CPU, chi phí cấp phát và phân phối khóa. Sau khi loại phương án không đáp ứng giới hạn bộ nhớ hoặc bảo đảm thời gian, nên đo trên dữ liệu đại diện cho tải thực tế.

## 9. Khi nào chọn cây so sánh, khi nào chọn cấu trúc khóa nguyên?

| Nhu cầu | Lựa chọn ban đầu hợp lý | Lý do |
|---|---|---|
| Khóa có kiểu bất kỳ, cần sắp thứ tự và truy vấn khoảng | Cây AVL hoặc đỏ-đen | Chỉ cần phép so sánh; có chặn trên $O(\log n)$ trường hợp xấu |
| Chỉ cần tra cứu/chèn/xóa khóa, miền rất thưa | Bảng băm | Bộ nhớ theo $n$, tìm kiếm kỳ vọng nhanh |
| Khóa là chỉ số trong miền nhỏ, có payload | Bảng đánh chỉ số trực tiếp | Truy cập $O(1)$ với chi phí $O(U)$ ô chấp nhận được |
| Miền nhỏ/vừa và chỉ lưu trạng thái có/không | Bitset | Chỉ $U$ bit, phép thao tác tập hợp có thể xử lý theo từ |
| Khóa là chuỗi bit có cấu trúc tiền tố đáng khai thác | Trie nhị phân hoặc Patricia trie | Rẽ nhánh theo bit và nhóm khóa chung tiền tố |
| Cần tiền nhiệm/kế nhiệm rất nhanh trên miền nguyên thích hợp | Cân nhắc vEB hoặc y-fast trie | Khai thác cấu trúc miền và bit; cần đánh giá bộ nhớ và độ phức tạp triển khai |
| Cần sắp xếp nhiều số nguyên độ rộng cố định | Thử radix sort | Có thể khai thác chữ số nhị phân để giảm số phép so sánh |

Quy trình chọn thực tế gồm: xác định tập thao tác cần hỗ trợ; ghi rõ $n$, $U$, $w$ và độ rộng từ máy $W$; tính bộ nhớ theo **bit, ô hoặc từ máy**; phân biệt trường hợp xấu, kỳ vọng và khấu hao; cuối cùng đo thời gian trên dữ liệu đại diện.

Nếu dữ liệu **tĩnh**, có thể nén tọa độ từ các giá trị nguyên lớn sang thứ hạng $0,\ldots,n-1$ để dùng cấu trúc trên miền nhỏ. Tuy nhiên, muốn biến một truy vấn tiền nhiệm trên khóa gốc thành truy vấn trên thứ hạng, ta vẫn phải xác định được vị trí thứ tự của khóa truy vấn; một bảng băm từ khóa sang thứ hạng không đủ để giải quyết mọi truy vấn tiền nhiệm. Khi liên tục thêm khóa mới, việc cập nhật thứ hạng cũng có chi phí riêng.

## 10. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “Dùng khóa kiểu `int` trong cây đỏ-đen là đã có cấu trúc chuyên biệt cho số nguyên.” | Nếu cây chỉ dùng các phép $<$, $=$, $>$, nó vẫn là cấu trúc dựa trên so sánh. |
| “Mọi thao tác với số nguyên phải tốn ít nhất $\Omega(\log n)$.” | Cận dưới chỉ áp dụng trong mô hình chỉ so sánh và với loại truy vấn đang xét. |
| “$O(1)$ luôn tốt hơn $O(\log n)$.” | Phải xem chi phí bộ nhớ, khởi tạo, mô hình máy và thao tác thực tế. |
| “Có $n$ khóa nên bảng trực tiếp tốn $O(n)$.” | Bảng trực tiếp tốn $O(U)$ ô, ngay cả khi $n\ll U$. |
| “Bitset cho mọi truy vấn trong $O(1)$.” | Bitset cơ bản hỗ trợ hiện diện, còn tiền nhiệm/kế nhiệm có thể đòi hỏi quét hoặc chỉ mục bổ sung. |
| “Bảng băm thay thế hoàn toàn cây cân bằng.” | Bảng băm thông thường không tự hỗ trợ thứ tự, tiền nhiệm hay truy vấn khoảng. |
| “$O(\log\log U)$ chắc chắn nhanh hơn cây cân bằng.” | Đây là bậc thời gian trong mô hình cụ thể; còn bộ nhớ, hằng số và cài đặt. |
| “Sắp xếp số nguyên $O(n)$ phá vỡ cận dưới sắp xếp so sánh.” | Counting/radix sort sử dụng giá trị hoặc bit của khóa, tức nằm ngoài mô hình chỉ so sánh. |

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Một cây đỏ-đen lưu khóa kiểu số nguyên 64 bit, nhưng mỗi thao tác chỉ gọi hàm `compare(a,b)`. Nó có tận dụng kỹ thuật đặc thù cho khóa số nguyên không?

**Trả lời:** Không. Dù dữ liệu là số nguyên, cấu trúc chỉ dùng quan hệ thứ tự nên độ sâu tìm kiếm vẫn được phân tích theo $n$.

**Câu 2.** Với $n=500$ khóa trong miền $U=10^9$, một bitset và một cây AVL khác nhau thế nào về không gian?

**Trả lời:** Bitset cần khoảng $10^9/8=125.000.000$ byte, tức khoảng 119,2 MiB chỉ cho cờ hiện diện; cây AVL dùng $O(500)$ nút. Nếu cần thứ tự và ít khóa, cây thường là ứng viên hợp lý hơn.

**Câu 3.** Nếu chỉ cần hỏi khóa có tồn tại trong miền $[0,4096)$, tại sao bitset đáng cân nhắc?

**Trả lời:** Bitset chỉ cần $4096/8=512$ byte, hỗ trợ truy cập trực tiếp cờ của từng khóa. Không cần chi phí con trỏ, so sánh dọc cây hay mảng các ô chứa payload.

**Câu 4.** Một thuật toán tìm tiền nhiệm đạt thời gian kỳ vọng $O(\log w)$ trên khóa nguyên có mâu thuẫn với cận dưới $\Omega(\log n)$ của mô hình so sánh không?

**Trả lời:** Không. Thuật toán khai thác biểu diễn bit, băm hoặc các thao tác word-RAM; cận dưới $\Omega(\log n)$ được chứng minh cho mô hình quyết định chỉ bằng so sánh.

Phân biệt cốt lõi là **nguồn thông tin mà cấu trúc được phép sử dụng**. Cây so sánh giải quyết bài toán thứ tự với chi phí chủ yếu theo $n$. Những cấu trúc cho khóa số nguyên có thể khai thác $U$ và $w$ để tăng tốc một số thao tác, nhưng thường đánh đổi bằng bộ nhớ, giả định về máy tính hoặc độ phức tạp triển khai. Chọn đúng cấu trúc nghĩa là chọn đúng bộ thao tác, giới hạn tài nguyên và mô hình bảo đảm hiệu năng cho bài toán.
