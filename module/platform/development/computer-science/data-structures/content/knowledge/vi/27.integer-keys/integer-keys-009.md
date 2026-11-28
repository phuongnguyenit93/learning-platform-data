# Chi phí theo số phần tử, độ lớn miền khóa và số bit của khóa

Hai tập dữ liệu cùng lưu 100.000 khóa số nguyên có thể cần lượng bộ nhớ rất khác nhau. Nếu khóa chỉ nằm trong đoạn `0..999.999`, một bảng đánh chỉ số trực tiếp có thể khả thi. Nếu mỗi khóa là một số nguyên 32 bit bất kỳ, bảng tương tự phải dự phòng tới $2^{32}$ vị trí, dù số khóa thực sự xuất hiện vẫn chỉ là 100.000. Vì vậy, nói một cấu trúc có độ phức tạp “theo số phần tử” là chưa đủ khi khóa thuộc một **miền số nguyên hữu hạn**.

Bài học này phân biệt ba đại lượng quyết định chi phí của cấu trúc dữ liệu cho khóa số nguyên: số phần tử đang lưu, số khóa có thể xuất hiện và số bit dùng để biểu diễn khóa. Từ đó, ta so sánh bảng băm, cây tìm kiếm, bitset, trie, van Emde Boas và các cách sắp xếp số nguyên để chọn cấu trúc phù hợp.

## 1. Ba đại lượng phải xác định trước khi phân tích

| Ký hiệu | Ý nghĩa | Ví dụ |
|---|---|---|
| $n$ | Số khóa **phân biệt đang được lưu** trong một tập hợp hoặc từ điển. | Tập hợp hiện có 100.000 ID thì $n=100.000$. |
| $U$ | **Kích thước miền khóa** (*universe size*): số giá trị khóa có thể xuất hiện. Thường chuẩn hóa khóa về đoạn $[0,U)$. | Khóa không dấu 32 bit có $U=2^{32}$. |
| $w$ | Số bit trong biểu diễn khóa mà thuật toán xử lý. | Một khóa có biểu diễn cố định dài 32 bit thì $w=32$. |

Khi đang **sắp xếp một dãy** có thể có khóa trùng nhau, $n$ được hiểu là tổng số phần tử của dãy đầu vào; sự khác biệt này cần được nêu rõ vì một tập hợp chỉ lưu khóa phân biệt.

Với $n$ khóa phân biệt lấy từ miền $[0,U)$, luôn có $0\le n\le U$. Một biểu diễn nhị phân đủ để mã hóa mọi khóa trong miền cần ít nhất

\[
b=\lceil\log_2 U\rceil\quad\text{bit}\qquad(U\ge 2).
\]

Nếu chọn biểu diễn vừa đủ thì $w=b$. Trong thực tế, có thể dùng trường 64 bit để lưu khóa chỉ cần 20 bit; khi đó $w=64$ theo **định dạng được xử lý**, còn $b=20$ là số bit tối thiểu của miền. Ta có $U\le 2^w$, nhưng không được mặc định $U=2^w$.

Đối với khóa âm hoặc giá trị không liên tiếp, $U$ phải được xác định theo **tập giá trị hợp lệ**, không suy ra máy móc từ giá trị khóa lớn nhất. Ví dụ, các khóa từ `-500` đến `499` có đúng $U=1.000$ giá trị và có thể chuẩn hóa bằng cách cộng 500. Nếu giá trị hợp lệ rải rác trong khoảng cực lớn, việc ánh xạ chúng thành chỉ số nhỏ có thể đòi hỏi một bảng ánh xạ riêng.

Một đại lượng hữu ích khác là **mật độ miền khóa**:

\[
\rho=\frac{n}{U}.
\]

Mật độ nhỏ nghĩa là miền khóa *thưa*; mật độ gần 1 nghĩa là miền khóa *dày*. Hai bài toán có cùng $n$ nhưng mật độ khác nhau có thể cần những cấu trúc khác nhau.

## 2. Mô hình tính toán: một thao tác “hằng số” thực sự tốn gì?

Phân tích phổ biến dựa trên mô hình **word-RAM**: máy xử lý được một *từ máy* gồm $W$ bit, và các thao tác cơ bản trên một từ như cộng, so sánh, AND, dịch bit, truy cập mảng theo chỉ số hợp lệ được coi là $O(1)$. Ở đây, $W$ là độ rộng từ máy; nó có thể khác $w$, độ dài biểu diễn khóa.

Nếu một khóa vừa trong một từ máy ($w\le W$), so sánh hoặc truy xuất bit trong khóa thường được tính là một số hữu hạn thao tác cơ bản. Nếu khóa dài tùy ý, phải lưu trên $k=\lceil w/W\rceil$ từ máy: so sánh hai khóa có thể cần $O(k)$ thao tác trong trường hợp xấu nhất; băm toàn bộ khóa cũng phải đọc các từ chứa khóa. Vì thế, một phép toán được xem là $O(1)$ trong mô hình khóa vừa một từ chưa chắc còn $O(1)$ khi $w$ được phép tăng không giới hạn.

Đơn vị bộ nhớ cũng cần ghi rõ:

- **$O(n)$ từ máy** tương ứng $O(nW)$ bit, ngoài các chi tiết cấp phát và đối tượng của ngôn ngữ lập trình.
- **$O(U)$ bit** chỉ cần khoảng $U/8$ byte, còn **$O(U)$ từ máy** có thể lớn hơn khoảng $W$ lần.
- **$O(1)$ cho một thao tác** không có nghĩa là thời gian khởi tạo hay giải phóng toàn bộ cấu trúc cũng là $O(1)$.

Khi nêu độ phức tạp kỳ vọng của bảng băm hay các cấu trúc ngẫu nhiên, cần hiểu đó là kỳ vọng dưới giả định về hàm băm, phân phối ngẫu nhiên hoặc cơ chế tái cân bằng được sử dụng; không phải bảo đảm tuyệt đối cho mọi chuỗi thao tác.

## 3. So sánh các cấu trúc lưu tập khóa số nguyên

Giả sử yêu cầu chính là kiểm tra một khóa có tồn tại hay không, chèn và xóa khóa. Với truy vấn **tiền nhiệm** (*predecessor*), ta muốn tìm khóa lớn nhất nhỏ hơn $x$; với **kế nhiệm** (*successor*), ta muốn tìm khóa nhỏ nhất lớn hơn $x$. Những truy vấn có thứ tự này làm thay đổi lựa chọn cấu trúc.

| Cấu trúc | Tìm/chèn/xóa một khóa | Bộ nhớ điển hình | Điểm cần nhớ |
|---|---|---|---|
| Mảng không sắp | Tìm $O(n)$; thêm cuối $O(1)$ khấu hao; xóa theo khóa $O(n)$ | $O(n)$ phần tử | Đơn giản, phù hợp tập rất nhỏ. |
| Bảng băm (*hash table*) | $O(1)$ **kỳ vọng**; có thể $O(n)$ trong trường hợp xấu | $O(n)$ từ máy | Tốt cho tra cứu chính xác; không tự cung cấp thứ tự khóa. |
| Cây tìm kiếm cân bằng | $O(\log n)$ trường hợp xấu | $O(n)$ nút/từ máy | Hỗ trợ duyệt theo thứ tự, tiền nhiệm, kế nhiệm, truy vấn khoảng. |
| Mảng đánh chỉ số trực tiếp | $O(1)$ | $\Theta(U)$ ô | Khóa được dùng làm chỉ số; tốn bộ nhớ theo cả miền khóa. |
| Bitset/bitmap | $O(1)$ với khóa hợp lệ | $\Theta(\lceil U/W\rceil)$ từ máy, tức $\Theta(U)$ bit | Chỉ lưu **có/không**, không tự lưu giá trị gắn với khóa. |
| Trie nhị phân theo bit | $O(w)$ với khóa dài $w$ bit | Tối đa $O(nw)$ nút nếu không nén đường đi | Chi phí gắn với chiều dài khóa; có thể hỗ trợ thao tác theo tiền tố. |
| van Emde Boas (dạng cơ bản) | $O(\log\log U)$ | $O(U)$ từ máy | Hỗ trợ tiền nhiệm/kế nhiệm nhanh nhưng tốn bộ nhớ miền khóa. |

Các ô độ phức tạp trong bảng mô tả thao tác trên **cấu trúc đã được khởi tạo**, với điều kiện khóa biểu diễn và truy cập được trong mô hình đang xét. Chi phí khởi tạo mảng trực tiếp là $\Theta(U)$ ô; chi phí làm sạch bitset là $\Theta(\lceil U/W\rceil)$ từ máy. Những chi phí ấy vẫn tồn tại kể cả khi $n=0$.

Điểm khác biệt lớn nhất là: bảng băm và cây cân bằng thường tăng bộ nhớ theo **số khóa thực sự lưu** $n$; mảng trực tiếp và van Emde Boas dạng cơ bản tăng bộ nhớ theo **toàn bộ miền** $U$; trie nhị phân có thể chịu chi phí theo **số bit** $w$ trên từng khóa.

### Tại sao $O(\log n)$ và $O(\log\log U)$ không thể thay thế cho nhau?

Nếu $U=2^{32}$ thì $\log_2\log_2 U=\log_2 32=5$, nhưng con số này không khiến van Emde Boas mặc nhiên tốt hơn cây cân bằng: cách triển khai cơ bản có thể yêu cầu không gian tỷ lệ $2^{32}$. Ngược lại, nếu chỉ có $n=100.000$, cây cân bằng có chiều cao $O(\log n)$ (vì $\log_2 100.000\approx16{,}6$) và chỉ lưu số nút tỷ lệ với 100.000.

Khi $w=\lceil\log_2 U\rceil$, có thể viết $O(\log\log U)=O(\log w)$ với $U\ge4$. Nhưng nếu định dạng khóa rộng hơn nhiều so với miền thực tế ($w\gg\log U$), hai biểu thức không còn diễn tả đúng cùng một tham số. Luôn ghi giả định trước khi đổi từ $U$ sang $w$.

## 4. Dự toán bộ nhớ: chênh lệch giữa bit, ô và từ máy

Giả sử hệ thống lưu **100.000 ID không dấu 32 bit phân biệt**, có thể nhận bất kỳ giá trị nào trong $[0,2^{32})$. Khi ấy:

\[
n=100.000,\qquad U=2^{32}=4.294.967.296,\qquad w=32.
\]

- **Bitset:** mỗi khóa chiếm một bit, cần $2^{32}/8=536.870.912$ byte, tức **512 MiB** (chưa kể metadata).
- **Bảng trực tiếp với con trỏ 8 byte/ô:** cần $2^{32}\times8=34.359.738.368$ byte, tức **32 GiB** chỉ cho các ô.
- **Bảng băm hoặc cây cân bằng:** số mục lưu tỷ lệ với 100.000, cộng chi phí mảng bucket, nút, con trỏ và quản lý bộ nhớ. Hằng số bộ nhớ phụ thuộc triển khai nên không thể suy ra số byte chỉ từ ký hiệu $O(n)$.

Như vậy, ngay cả bitset vốn tiết kiệm bit cũng có thể quá lớn cho một tập khóa **rất thưa**. Một cấu trúc có thao tác $O(1)$ vẫn có thể bị loại bởi giới hạn RAM, chi phí khởi tạo hoặc số trang bộ nhớ phải truy cập.

Ngược lại, nếu $U=1.000.000$ và $n=800.000$ thì bitset chỉ cần $1.000.000/8=125.000$ byte (khoảng **122 KiB**) để biểu diễn sự hiện diện của toàn bộ khóa. Trong bài toán **chỉ cần kiểm tra tồn tại**, cách biểu diễn đặc này rất hấp dẫn; nếu cần gắn đối tượng hoặc giá trị tùy ý với mỗi khóa, phải chọn cấu trúc có thể lưu payload.

### Minh họa cách bitset đánh đổi bộ nhớ lấy thao tác

Với $W=64$, mỗi từ máy chứa 64 cờ hiện diện. Đây là giả mã cho một miền cố định $[0,U)$:

```text
khởi_tạo(U):
    words = mảng ceil(U / 64) từ 64-bit, ban đầu đều bằng 0

vị_trí(x):                    // yêu cầu 0 <= x < U
    i = x div 64              // chỉ số từ máy
    mask = uint64(1) << (x mod 64)
    trả_về (i, mask)

có_chứa(x):
    (i, mask) = vị_trí(x)
    trả_về (words[i] & mask) != 0

thêm(x):
    (i, mask) = vị_trí(x)
    words[i] = words[i] | mask

xóa(x):
    (i, mask) = vị_trí(x)
    words[i] = words[i] & (~mask)
```

Một lần `có_chứa`, `thêm` hay `xóa` chỉ dùng vài thao tác trên từ máy, nên có độ phức tạp $O(1)$ khi miền đã cấp phát và $x$ hợp lệ. Tuy nhiên, quét tất cả các từ để liệt kê khóa có thể tốn $O(U/W+n)$ thao tác, tùy cách tìm các bit đã bật. Bitset cơ bản cũng **không bảo đảm tiền nhiệm/kế nhiệm $O(1)$** trên miền rất lớn chỉ nhờ thao tác bit; muốn đạt truy vấn thứ tự tốt hơn thường phải bổ sung chỉ mục nhiều tầng hoặc dùng cấu trúc khác.

## 5. Chi phí khi sắp xếp khóa số nguyên

Sắp xếp cho thấy rõ lý do phải nhìn đồng thời $n$, $U$ và $w$. Khác với các thuật toán dựa hoàn toàn vào so sánh, thuật toán số nguyên có thể khai thác giá trị hoặc các chữ số nhị phân của khóa.

| Cách sắp xếp | Thời gian | Bộ nhớ phụ thường gặp | Khi nào đáng cân nhắc? |
|---|---|---|---|
| Sắp xếp dựa trên so sánh (merge sort, heap sort, …) | $O(n\log n)$ cho các thuật toán điển hình bảo đảm chặn trên này | Tùy thuật toán, từ $O(1)$ đến $O(n)$ | Miền khóa lớn, dữ liệu tùy ý, cần giải pháp tổng quát. |
| Counting sort | $\Theta(n+U)$ | $\Theta(n+U)$ cho bản ổn định thông dụng | $U$ đủ nhỏ để cấp phát mảng đếm. |
| LSD radix sort với mỗi lượt xử lý $r$ bit | $\Theta(d(n+B))$, $B=2^r,\ d=\lceil w/r\rceil$ | $O(n+B)$ cho cách dùng counting sort ổn định | Khóa dài cố định; chọn kích thước chữ số để cân bằng số lượt và bucket. |

**Counting sort** tạo các bộ đếm cho $U$ giá trị khóa. Khi $U\gg n$, việc khởi tạo và duyệt bảng đếm có thể đắt hơn nhiều so với xử lý dữ liệu thật. Việc nói “counting sort chạy $O(n)$” chỉ đúng khi đã giả định $U=O(n)$.

**Radix sort** chia khóa thành $d$ chữ số, mỗi chữ số có $B=2^r$ giá trị. Mỗi lượt phải quét $n$ phần tử và quản lý $B$ bucket. Với các khóa 32 bit và $r=8$:

\[
B=256,\qquad d=\lceil32/8\rceil=4,\qquad T=\Theta(4(n+256)).
\]

Radix sort không cần mảng $2^{32}$ bucket ở ví dụ trên. Nếu tăng $r$, số lượt giảm nhưng số bucket $2^r$ tăng theo hàm mũ. Nếu dữ liệu thực chỉ dùng $b<w$ bit có ý nghĩa, một cách mã hóa phù hợp có thể xử lý $b$ bit thay vì toàn bộ $w$ bit; với số nguyên có dấu cần đảm bảo phép biến đổi biểu diễn vẫn giữ đúng thứ tự số học. Để LSD radix sort hoạt động đúng, phép sắp xếp từng chữ số phải **ổn định**.

Mệnh đề “sắp xếp so sánh cần $\Omega(n\log n)$” áp dụng cho bài toán tổng quát với các phần tử phân biệt trong **mô hình chỉ được so sánh**. Counting sort và radix sort khai thác tính chất của khóa số nguyên nên không bị ràng buộc bởi cận dưới của mô hình đó; đổi lại chúng trả chi phí theo $U$, $w$ hoặc $B$.

## 6. Khi nào số bit của khóa là tham số chi phối?

Trong **trie nhị phân**, mỗi bước xét một bit của khóa và chọn nhánh 0 hoặc 1. Với biểu diễn dài $w$ bit, tra cứu/chèn một khóa có thể đi qua $w$ mức nên tốn $O(w)$ bước; nếu không nén các đường chỉ có một nhánh, việc lưu $n$ khóa có thể tạo đến $O(nw)$ nút. Trie có nén đường đi có thể giảm mạnh số nút, nhưng không được tự suy rằng mọi thao tác của mọi biến thể đều trở thành $O(1)$.

Trong cấu trúc **van Emde Boas**, thuật toán khai thác miền khóa hữu hạn bằng cách chia khóa thành các phần cao/thấp và tổ chức đệ quy. Độ sâu phụ thuộc số lần lấy căn bậc hai kích thước miền nên các thao tác thứ tự đạt $O(\log\log U)$; đổi lại, phiên bản cơ bản sử dụng $O(U)$ từ máy. Những cấu trúc cải tiến như **y-fast trie** cho thấy có thể đạt thời gian tiền nhiệm/kế nhiệm kỳ vọng $O(\log w)$ cùng không gian kỳ vọng $O(n)$ từ máy dưới các giả định word-RAM và băm phù hợp; cách triển khai phức tạp hơn nhiều so với bảng băm hay cây cân bằng.

Trường hợp khóa có hàng trăm hoặc hàng nghìn bit còn đặt ra vấn đề khác: nếu CPU xử lý từng từ 64 bit, đọc, so sánh, tính hash hoặc xử lý toàn bộ khóa phải xét nhiều từ. Chẳng hạn, khóa dài 256 bit chiếm ít nhất bốn từ 64 bit. Khi độ dài 256 bit được **cố định**, đây chỉ là một hằng số trong phân tích theo $n$; khi nghiên cứu một họ bài toán mà $w$ tăng, không thể bỏ chi phí phụ thuộc $w$ ấy.

## 7. Chọn cấu trúc theo mật độ, thao tác và giới hạn thực tế

Hãy xem ba tình huống với cùng mục tiêu quản lý khóa số nguyên:

**Tình huống A — miền lớn, tập thưa.** Hệ thống quản lý 100.000 ID 32 bit, cần kiểm tra ID tồn tại và gắn dữ liệu với ID. Với $U=2^{32}$, bảng trực tiếp tốn hàng chục GiB. **Bảng băm** thường là điểm khởi đầu tốt nếu chỉ cần tra cứu chính xác; **cây cân bằng** phù hợp hơn nếu cần liệt kê ID theo thứ tự hoặc tìm ID gần nhất.

**Tình huống B — miền nhỏ, tập dày.** Một dịch vụ lưu cờ đã xử lý của các mã `0..999999`, gần như toàn bộ mã có thể xuất hiện. **Bitset** lưu một triệu cờ trong khoảng 122 KiB và truy cập trực tiếp theo chỉ số; nếu mỗi mã cần giữ một bản ghi, dùng **mảng trực tiếp** có thể phù hợp khi tổng bộ nhớ cho các ô chấp nhận được.

**Tình huống C — sắp xếp số lượng lớn khóa có độ dài cố định.** Cần sắp xếp hàng triệu số nguyên 32 bit. **Radix sort** với chữ số 8 bit là một ứng viên để thử; counting sort theo toàn bộ miền $2^{32}$ thường không hợp lý vì bảng đếm quá lớn. Kết quả cuối cùng còn phụ thuộc hiệu năng bộ nhớ, cache, cấp phát và thư viện sắp xếp đang dùng.

Một quy trình lựa chọn thực tế:

1. **Xác định ba tham số** $n,U,w$, độ rộng từ máy $W$, khóa có âm/trùng hay không và có thể chuẩn hóa thành $[0,U)$ hay không.
2. **Xác định thao tác chính**: tra cứu chính xác, lưu payload, tìm tiền nhiệm/kế nhiệm, duyệt thứ tự, xử lý khoảng hay sắp xếp hàng loạt.
3. **Ước lượng bộ nhớ bằng đơn vị thật**: $U$ bit, $U$ ô hay $n$ nút/từ máy; tính cả chi phí khởi tạo và cấu trúc phụ.
4. **So sánh bảo đảm thời gian**: trường hợp xấu, kỳ vọng và khấu hao là ba loại phát biểu khác nhau; không đánh đồng chúng.
5. **Đo trên tải dữ liệu tiêu biểu** sau khi đã loại các phương án vượt ngân sách bộ nhớ, vì hằng số, tính liên tục bộ nhớ, cache và phân phối khóa đều tác động đến thời gian thực.

## 8. Những nhầm lẫn thường gặp

| Nhận định dễ nhầm | Cách hiểu đúng |
|---|---|
| “Có $n$ khóa thì mọi cấu trúc đều tốn $O(n)$ bộ nhớ.” | Bảng trực tiếp và van Emde Boas cơ bản có thể tốn $O(U)$; trie chưa nén có thể tốn $O(nw)$ nút. |
| “Khóa 32 bit nên $U=32$.” | 32 là số bit biểu diễn; nếu mọi bit đều được phép thay đổi thì có tới $2^{32}$ giá trị. |
| “Thao tác $O(1)$ nghĩa là cấu trúc nhỏ và khởi tạo nhanh.” | Mảng trực tiếp có tra cứu $O(1)$ nhưng kích thước, khởi tạo và làm sạch vẫn phụ thuộc $U$. |
| “Bảng băm $O(1)$ trong mọi trường hợp.” | Thông thường đó là thời gian trung bình/kỳ vọng dưới giả định thích hợp; trường hợp xấu có thể là $O(n)$. |
| “Bitset tìm mọi loại truy vấn trong $O(1)$.” | Một bit cho biết một khóa có hiện diện hay không; tiền nhiệm/kế nhiệm hoặc lưu payload là yêu cầu khác. |
| “$O(\log\log U)$ luôn nhanh hơn $O(\log n)$.” | Chỉ nhìn ký hiệu thời gian bỏ qua bộ nhớ, điều kiện mô hình và chi phí triển khai. |
| “Radix sort luôn là $O(n)$.” | Tổng quát là $O(d(n+2^r))$; khi $w,r$ và $B$ được coi là hằng số mới rút gọn thành $O(n)$. |

## 9. Tự kiểm tra bằng ba câu hỏi

**Câu 1.** Một tập chứa $n=2^{15}$ khóa 32 bit, chỉ cần kiểm tra tồn tại. Hãy tính dung lượng bitset nếu cho phép toàn bộ $U=2^{32}$ khóa. **Giải thích:** dung lượng là $2^{32}$ bit = 512 MiB, không giảm khi $n$ chỉ là $2^{15}$. Bảng băm dùng không gian tăng theo $n$ thường hợp lý hơn.

**Câu 2.** Một bài toán sắp xếp $n=10^6$ số nguyên trong $[0,999]$. Cấu trúc mảng đếm của counting sort có bao nhiêu ô? **Giải thích:** $U=1.000$, cần 1.000 ô đếm; thời gian $\Theta(n+1.000)=\Theta(n)$ theo quy mô đã nêu. Không được thay $U$ bằng $2^{32}$ chỉ vì biến trong chương trình có kiểu 32 bit.

**Câu 3.** Khi nào nên đổi bảng băm sang cây tìm kiếm cân bằng dù bảng băm có thời gian tìm kiếm kỳ vọng $O(1)$? **Gợi ý:** khi bài toán cần duyệt tăng dần, tìm tiền nhiệm/kế nhiệm hoặc xử lý truy vấn khoảng và cần bảo đảm độ phức tạp $O(\log n)$ trong trường hợp xấu.

Khi phân tích cấu trúc dữ liệu theo khóa số nguyên, hãy viết đầy đủ chi phí dưới dạng hàm của **$n$, $U$, $w$** và nói rõ đơn vị bộ nhớ, mô hình máy, loại thao tác cũng như giả định xác suất. Đó là cơ sở để phân biệt thuật toán có thời gian đẹp trên lý thuyết với cấu trúc thật sự vừa bộ nhớ và đáp ứng yêu cầu truy vấn.
