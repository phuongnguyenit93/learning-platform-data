# Lưu kết quả trung gian và đánh đổi thời gian–bộ nhớ

## 1. Ý tưởng: tính trước hoặc ghi nhớ để không làm lại

Trong nhiều bài toán thuật toán, một phép tính có thể được thực hiện **nhiều lần trên cùng dữ liệu**. Khi đó, thay vì tính lại từ đầu cho mỗi truy vấn, ta có thể lưu một kết quả trung gian và dùng lại. Cách làm này chuyển một phần chi phí từ **thời gian xử lý về sau** sang **thời gian tiền xử lý và dung lượng bộ nhớ**.

Ví dụ: cho mảng a có n số nguyên, cần trả lời q truy vấn tổng của đoạn [l,r).

- Không tiền xử lý: mỗi truy vấn cộng từng phần tử, mất O(r-l), trường hợp xấu nhất O(n).
- Có mảng **tổng tiền tố (prefix sums)**: dựng O(n) một lần, tốn O(n) bộ nhớ, sau đó mỗi tổng đoạn chỉ cần hai lần đọc và một phép trừ, O(1).
- Nếu mảng liên tục thay đổi, tổng tiền tố đã lưu có thể **lỗi thời**; phải xây lại, cập nhật phần bị ảnh hưởng, hoặc chọn cấu trúc dữ liệu động khác.

Vì vậy, câu hỏi không chỉ là “cách nào nhanh hơn?” mà là: **nhanh hơn ở loại thao tác nào, đổi lại bao nhiêu bộ nhớ và chi phí duy trì, và dữ liệu có giữ nguyên đủ lâu để tái sử dụng không?**

Trong chủ đề **biến đổi và tiền xử lý**, kết quả trung gian có thể là tổng tiền tố, bảng tra cứu, bảng quy hoạch động, chỉ mục tìm kiếm, mảng thống kê, trạng thái đã chuẩn hóa, hoặc bất kỳ dạng biểu diễn nào giúp các thao tác tiếp theo rẻ hơn.

## 2. Các cách lưu kết quả trung gian thường gặp

| Kỹ thuật | Lưu gì? | Khi nào hữu ích? | Điều cần lưu ý |
| --- | --- | --- | --- |
| **Precomputation** – tính trước | Tập kết quả có thể cần trong tương lai | Nhiều truy vấn trên cùng dữ liệu | Có thể tính nhiều trạng thái không bao giờ được hỏi |
| **Memoization** – ghi nhớ theo nhu cầu | Kết quả của các bài toán con đã thực sự gặp | Đệ quy có trạng thái con bị lặp | Phải có cache key đầy đủ, kiểm soát trạng thái thay đổi |
| **Tabulation** – lập bảng | Các trạng thái theo thứ tự phụ thuộc | Quy hoạch động, cần nhiều giá trị liên quan | Có thể cần cả bảng dù chỉ hỏi một giá trị |
| **Prefix/suffix aggregates** | Tổng, đếm, min/max hoặc thông tin gộp của tiền tố/hậu tố | Truy vấn đoạn, tách trường hợp tại ranh giới | Phép gộp nào hỗ trợ truy vấn O(1) phải được chứng minh |
| **Lookup table / index** | Vị trí, tần suất, ánh xạ giá trị sang danh sách vị trí | Tìm kiếm hoặc tra cứu lặp lại | Tốn bộ nhớ và chi phí cập nhật khi dữ liệu đổi |
| **Materialized result** | Kết quả của bước biến đổi tốn kém | Nhiều giai đoạn dùng lại đầu ra giống nhau | Dễ trả dữ liệu cũ nếu quên invalidation |
| **Cache có giới hạn** | Một phần kết quả được chọn | Dữ liệu lớn, không thể giữ tất cả | Có cache miss, eviction, overhead quản lý |

**Memoization** thường bắt đầu từ một hàm giải bài toán con, chỉ tính khi được gọi. **Tabulation** chủ động duyệt các trạng thái theo thứ tự để các giá trị phụ thuộc đã có sẵn. Cả hai đều có thể là quy hoạch động khi có trạng thái lặp lại; chúng không phải tên gọi thay thế cho mọi dạng tiền xử lý.

**Lưu kết quả trung gian khác lưu dữ liệu đầu vào**: bản sao của đầu vào không nhất thiết giúp truy vấn nhanh hơn. Một biểu diễn có giá trị khi nó giữ đúng **thông tin đủ để trả lời thao tác đích**, chẳng hạn bảng prefix cho tổng đoạn hoặc mảng chỉ mục cho truy vấn theo khóa.

## 3. Mô hình đánh đổi: chi phí xây, hỏi, cập nhật và bộ nhớ

Đặt:

- n: kích thước dữ liệu gốc.
- q: số truy vấn cần xử lý.
- u: số lần dữ liệu thay đổi.
- B(n): thời gian dựng cấu trúc tiền xử lý.
- Q(n): thời gian một truy vấn sau tiền xử lý.
- U(n): thời gian xử lý một cập nhật.
- S(n): bộ nhớ phụ duy trì cấu trúc.
- R_i: thời gian giải trực tiếp truy vấn thứ i nếu không lưu kết quả.

So sánh tổng chi phí:

~~~text
Khong luu ket qua:
    T_direct = sum_{i=1..q} R_i + chi_phi_cap_nhat_du_lieu_goc

Co tien xu ly:
    T_preprocessed = B(n) + q * Q(n) + u * U(n)
    Extra_memory   = S(n)
~~~

Đây là **mô hình**, không phải phép biến đổi tự động áp dụng được cho mọi bài. Nếu truy vấn có độ dài khác nhau, không thể thay tất cả R_i bằng O(n) một cách máy móc. Nếu cập nhật làm n thay đổi, các hàm chi phí và kích thước có thể thay đổi theo thời gian.

### Khi nào tiền xử lý hòa vốn?

Với tổng đoạn trên mảng bất biến:

- Quét trực tiếp: tổng chi phí là tổng độ dài các đoạn được hỏi, tức O(Σ(r_i-l_i)).
- Prefix sums: dựng O(n), sau đó O(q), bộ nhớ O(n).

Nếu q rất lớn và các đoạn thường dài, prefix sums thường có lợi rõ rệt. Nếu chỉ có một truy vấn đoạn ngắn, tạo thêm n+1 phần tử prefix có thể tốn hơn quét trực tiếp. Nếu q=0, không nên xây bảng chỉ để rồi không dùng, trừ khi có mục tiêu khác.

Giả sử minh họa n=100.000 và q=100.000 truy vấn, mỗi đoạn dài xấp xỉ n/2: quét cần xấp xỉ 5×10⁹ phép cộng; prefix chỉ cần quét n phần tử một lần, rồi mỗi truy vấn vài thao tác. Các con số này là **đếm thao tác minh họa**, không phải benchmark thời gian thực tế; chi phí cấp phát, cache CPU và thực thi máy ảo còn ảnh hưởng đến tốc độ.

**Không có nguyên tắc “dùng thêm bộ nhớ luôn nhanh hơn”.** Bộ nhớ tăng có thể gây GC, mất locality CPU hoặc vượt giới hạn RAM. Cần xét cả chi phí đọc/ghi bảng đã lưu, chứ không chỉ Big-O.

## 4. Prefix sums: ví dụ chuẩn về biến đổi không mất thông tin cần thiết

Với a[0..n-1], dựng mảng long prefix có n+1 phần tử:

~~~text
prefix[0] = 0
prefix[i+1] = prefix[i] + a[i]           (0 <= i < n)

sum(l, r) = prefix[r] - prefix[l]        (0 <= l <= r <= n)
~~~

Ở đây [l,r) là đoạn **nửa mở**: gồm các chỉ số l đến r-1. Đoạn rỗng [l,l) có tổng bằng 0. Nếu đề bài dùng đoạn **đóng** [l,r], công thức là prefix[r+1]-prefix[l], với 0≤l≤r<n.

Ví dụ:

~~~text
a      = [ 3, -1,  4,  2, -2 ]
prefix = [ 0,  3,  2,  6,  8,  6 ]

sum(1,4) = prefix[4] - prefix[1] = 8 - 3 = 5
sum(0,5) = prefix[5] - prefix[0] = 6 - 0 = 6
sum(3,3) = prefix[3] - prefix[3] = 0
~~~

### Vì sao công thức đúng?

prefix[r] là tổng a[0]+...+a[r-1]. prefix[l] là tổng a[0]+...+a[l-1]. Trừ hai tổng thì mọi phần tử trước l triệt tiêu, còn lại đúng các phần tử trong [l,r). Đây là phép rút gọn đại số, không phụ thuộc các số dương, âm hay trùng nhau.

**Độ phức tạp:** dựng O(n), mỗi truy vấn O(1), thêm O(n) bộ nhớ cho mảng prefix. Cần dùng long khi cộng các int để tránh tràn int. Việc cast sang long **sau khi đã cộng bằng int** không khắc phục được tràn.

### Prefix là ảnh chụp của dữ liệu tại thời điểm dựng

Nếu đã tạo prefix rồi sửa a[1] từ -1 thành 100, prefix cũ **không tự cập nhật**. Tổng đoạn cũ [0,5) vẫn trả 6 mặc dù tổng mới là 107. Phải nêu rõ hợp đồng API:

- **Snapshot bất biến:** dữ liệu hoặc bảng kết quả chỉ phản ánh thời điểm tạo; tạo snapshot mới nếu đầu vào thay đổi.
- **View động:** khi giá trị thay đổi, cập nhật cấu trúc theo quy tắc đúng trước khi cho truy vấn mới.
- **Đọc dữ liệu có phiên bản:** gắn version cho bảng kết quả, từ chối hoặc xây lại khi version đầu vào khác.

Một lỗi đặc biệt nguy hiểm là **trả giá trị có vẻ hợp lệ nhưng đã lỗi thời**. Bài kiểm thử cần cố ý thay đổi đầu vào sau tiền xử lý để kiểm tra hợp đồng này.

## 5. Các phép tổng hợp tiền xử lý khác và giới hạn của chúng

### Prefix count và bảng tần suất

Với điều kiện Boolean như a[i] > 0, ta có thể biến mỗi phần tử thành 0/1 rồi lấy prefix sums để trả lời số phần tử dương trong [l,r) bằng hai lần đọc. Nếu cần đếm từng giá trị x trên nhiều đoạn, có thể dựng bảng prefix theo từng giá trị **khi miền giá trị nhỏ**; chi phí lưu trữ có thể lên tới O(nR) với R giá trị, nên không phù hợp nếu khóa quá nhiều hoặc thưa.

Một HashMap đếm tần suất toàn dãy giúp trả lời “x xuất hiện bao nhiêu lần trong cả dãy?” nhanh, nhưng **không trả lời trực tiếp tần suất trong đoạn [l,r)**. Muốn truy vấn đoạn, có thể lưu danh sách **vị trí đã sắp** cho mỗi khóa và dùng binary search để đếm số vị trí thuộc đoạn; khi ấy truy vấn một khóa có thể O(log f_x) thay vì cần bảng n×R, với f_x là tần suất của khóa đó.

### Prefix sums 2D

Với ma trận H×W, có thể dựng P kích thước (H+1)×(W+1) sao cho P[r][c] là tổng hình chữ nhật từ góc trên trái đến ngay trước hàng r và cột c:

~~~text
P[r+1][c+1] = value[r][c]
            + P[r][c+1] + P[r+1][c] - P[r][c]

sumRowsCols(r1,r2,c1,c2)
    = P[r2][c2] - P[r1][c2] - P[r2][c1] + P[r1][c1]
~~~

Miền truy vấn gồm các hàng [r1,r2), cột [c1,c2). Dựng O(HW), mỗi truy vấn hình chữ nhật O(1), bộ nhớ O(HW). Cần quản lý đúng biên và kiểu số; một lỗi dấu trong công thức bao hàm–loại trừ (inclusion–exclusion) làm sai nhiều truy vấn.

### Tiền xử lý cho min/max trên mảng tĩnh

Phép lấy min không có phép nghịch đảo kiểu “min(prefix[r]) - min(prefix[l])”. Vì vậy **không thể** áp dụng nguyên công thức trừ hai prefix để lấy min của một đoạn bất kỳ.

Một **sparse table** trên mảng tĩnh có thể dùng O(n log n) thời gian/bộ nhớ để tiền xử lý, rồi truy vấn min/max đoạn trong O(1), tận dụng tính **idempotent** của min/max (gộp cùng một phần tử nhiều lần không đổi kết quả). Nhưng cách ghép hai đoạn **chồng lặp** dùng cho min/max không thể mang nguyên xi sang tổng vì tổng sẽ bị đếm trùng. Với tổng đoạn tĩnh, prefix sums thường đơn giản hơn.

### Phép chuẩn hóa và ánh xạ khóa

Tiền xử lý còn có thể biến các giá trị hoặc khóa thành dạng thuận tiện hơn:

- **Nén tọa độ:** ánh xạ các giá trị phân biệt sang chỉ số thứ hạng 0..u-1, giúp dùng mảng/Fenwick thay vì cấp phát theo miền số rộng.
- **Bảng vị trí:** ánh xạ khóa x tới các chỉ số xuất hiện, phục vụ truy vấn lặp lại theo khóa.
- **Tiền xử lý đồ thị:** lập adjacency list hoặc một chỉ mục phù hợp cho phép duyệt hàng xóm nhanh hơn so với mỗi lần quét lại tất cả cạnh.

Mỗi biến đổi chỉ có lợi khi **bảo toàn những thông tin và quan hệ thứ tự cần dùng về sau**. Nếu quá trình nén/lập chỉ mục bỏ mất thông tin cần thiết, truy vấn có thể không còn giải được.

## 6. Memoization: lưu kết quả của bài toán con khi thực sự được hỏi

Xét Fibonacci với quy ước F(0)=0, F(1)=1, F(n)=F(n-1)+F(n-2) với n≥2.

**Đệ quy ngây thơ** gọi đi gọi lại cùng trạng thái:

~~~text
fib(5)
  fib(4)
    fib(3)
      fib(2)
      fib(1)
    fib(2)
  fib(3)
    fib(2)
    fib(1)
~~~

Trong cây lời gọi, fib(3) và fib(2) xuất hiện nhiều lần. Với phép tính cộng hằng số, phiên bản ngây thơ có thời gian theo cấp số mũ theo n (chặn trên O(2^n)), dù chỉ có n+1 trạng thái khác nhau.

**Memoization** lưu fib(k) sau lần tính đầu:

~~~text
fib(n):
    neu n <= 1: return n
    neu fib(n) da co trong cache: return cache[n]
    cache[n] = fib(n-1) + fib(n-2)
    return cache[n]
~~~

Giờ mỗi trạng thái k chỉ được tính từ các phụ thuộc một lần: O(n) thời gian, O(n) bộ nhớ cache; nếu dùng đệ quy, stack cũng có độ sâu O(n) trong trường hợp này.

### Cache key và giá trị rỗng

Cache key phải mô tả **đầy đủ trạng thái mà kết quả phụ thuộc vào**. Với Fibonacci đơn giản, n là đủ. Với một hàm tính đường đi phụ thuộc vào đồ thị, đỉnh đích, tập cạnh bị chặn và phiên bản đồ thị, chỉ lưu “đỉnh bắt đầu” làm khóa là không đủ nếu các yếu tố kia thay đổi.

Đừng coi giá trị kết quả 0 là “chưa tính” nếu **0 là kết quả hợp lệ**. Dùng một mảng boolean computed[] riêng, kiểu Optional, sentinel chắc chắn không nằm trong miền giá trị, hoặc containsKey của Map. Trong mã Java bên dưới, mọi F(n) đều không âm nên -1L được dùng làm sentinel **trong miền n được giới hạn**, và cache[0]=0 được nhận diện là đã tính.

### Tabulation và tối ưu bộ nhớ

Với Fibonacci, tabulation có thể đi từ i=2 lên n:

~~~text
dp[0] = 0; dp[1] = 1
for i=2..n:
    dp[i] = dp[i-1] + dp[i-2]
~~~

Bảng dp đầy đủ cần O(n) bộ nhớ nếu phải truy cập nhiều F(k). Nhưng **nếu chỉ cần F(n)**, ta chỉ cần giữ hai số gần nhất, dùng O(1) bộ nhớ và O(n) thời gian. Như vậy “đổi thời gian lấy bộ nhớ” không phải lúc nào cũng phải tăng bộ nhớ: khi không cần toàn bộ trạng thái, có thể **nén trạng thái** mà vẫn giữ thời gian tốt.

**Giới hạn kiểu số:** Fibonacci tăng rất nhanh. Trong long có dấu của Java, F(92) = 7.540.113.804.746.346.429 còn nằm trong miền; F(93) vượt Long.MAX_VALUE. Ví dụ sau giới hạn n≤92. Với n lớn hơn cần BigInteger hoặc công thức/thuật toán khác phù hợp, và phải tính cả chi phí của phép toán số lớn.

## 7. Chọn cache hay tính trước: độ phủ truy vấn quyết định

Có ba kiểu tải công việc khác nhau:

1. **Ít truy vấn, khó đoán trước:** memoization theo nhu cầu tránh lấp đầy các ô trạng thái không bao giờ dùng.
2. **Rất nhiều truy vấn phủ gần toàn bộ miền:** tabulation hoặc precomputation đầy đủ có thể tiết kiệm overhead của tra cứu động, giảm độ sâu đệ quy và giúp truy vấn sau này đơn giản.
3. **Truy vấn lặp tập trung vào vài khóa nóng:** cache kích thước giới hạn có thể giữ kết quả nóng, chấp nhận tính lại khi cache miss.

Ví dụ xử lý một hệ thống câu hỏi “số nguyên x có phải số nguyên tố không?”:

- Với một vài x rất lớn, kiểm tra riêng từng x có thể kinh tế hơn dựng bảng từ 1 đến giới hạn cực lớn.
- Với rất nhiều truy vấn x trong miền [0,M] và M vừa phải, **sàng Eratosthenes** tiền xử lý O(M log log M), lưu O(M), rồi trả lời tra bảng O(1) có thể hợp lý.
- Nếu dữ liệu hoặc định nghĩa truy vấn thay đổi theo phiên bản, bảng tiền xử lý cần đi kèm chính sách cập nhật.

Một phép tính có thể cần **truy xuất nguồn** hoặc tính ngẫu nhiên; lưu cache mà không lưu ngữ cảnh/phiên bản có thể khiến kết quả không tái lập. Đối với tác vụ có tác dụng phụ (gửi thông báo, ghi cơ sở dữ liệu), không thể tự động memoize như một hàm thuần mà không thay đổi ngữ nghĩa.

## 8. Đánh đổi khi dữ liệu được cập nhật

Prefix sums rất mạnh với **dãy tĩnh**, nhưng khá đắt với **dãy động**:

- Nếu thay một giá trị a[i] thêm delta, mọi prefix[j] với j>i phải tăng delta.
- Nếu cứ sửa toàn bộ prefix sau mỗi lần cập nhật, thời gian một cập nhật có thể O(n).
- Nếu xây lại từ đầu sau từng thay đổi, cũng mất O(n) mỗi lần.

Khi có nhiều cập nhật và truy vấn tổng đoạn xen kẽ, hãy cân nhắc:

| Cấu trúc | Dựng | Hỏi tổng đoạn | Cập nhật một phần tử | Bộ nhớ phụ |
| --- | --- | --- | --- | --- |
| Quét trực tiếp | O(1) thêm | O(độ dài đoạn) | O(1) | O(1) |
| Prefix sums tĩnh | O(n) | O(1) | O(n) nếu duy trì ngay | O(n) |
| Fenwick tree (BIT) | O(n) nếu xây tuyến tính, hoặc O(n log n) nếu chèn từng điểm | O(log n) | O(log n) | O(n) |
| Segment tree tổng | O(n) | O(log n) | O(log n) | O(n) |

Fenwick tree và segment tree không **đơn giản hơn** prefix sums; chúng dùng thêm logic cập nhật để đổi O(1) truy vấn tĩnh thành O(log n) truy vấn và O(log n) cập nhật. Đây là một đánh đổi khác, tối ưu cho **loại thao tác đang xuất hiện**.

### Cập nhật lô và xử lý ngoài tuyến

Nếu có nhiều truy vấn giữa các đợt cập nhật, có thể dùng **rebuild theo lô**: sau mỗi đợt thay đổi, xây lại bảng một lần rồi phục vụ nhiều truy vấn trên snapshot mới. Chi phí tốt hay không phụ thuộc số lần rebuild, số truy vấn giữa các đợt, chi phí đồng bộ và độ trễ cho phép.

Nếu biết **toàn bộ truy vấn trước khi chạy** (offline), đôi khi có thể sắp xếp, nhóm hoặc biến đổi thứ tự xử lý để dùng ít bộ nhớ hoặc thời gian hơn. Nếu truy vấn đến trực tuyến (online) và phải trả ngay, không thể tùy ý gom chúng rồi trả sau.

**Không nên tự “vá” một bảng tiền xử lý** nếu không chứng minh được những ô nào bị ảnh hưởng bởi thay đổi; dữ liệu sai âm thầm có thể khó phát hiện hơn việc chấp nhận một thuật toán chậm hơn.

## 9. Cache correctness: không được để kết quả trung gian thành nguồn sai

Lưu kết quả giúp tiết kiệm thời gian, nhưng làm xuất hiện những rủi ro mà thuật toán tính lại trực tiếp không có.

### Chìa khóa cache phải đầy đủ

Nếu hàm f phụ thuộc vào (x,y,version), cache key chỉ chứa x sẽ trả sai khi y hoặc version khác. Nếu hàm phụ thuộc cấu hình, đơn vị đo, locale hay quy tắc làm tròn, các yếu tố đó cũng có thể ảnh hưởng đến kết quả.

Ví dụ normalizeName(text, locale, strength) không thể dùng mỗi text làm cache key nếu locale hoặc độ nhạy dấu/hoa khác nhau. Tương tự, cache shortestPath(start,end,graph) phải gắn với **phiên bản đồ thị** nếu cạnh/trọng số có thể đổi.

### Invalidation và vòng đời dữ liệu

Phải trả lời: khi đầu vào đổi, ai đánh dấu cache cũ vô hiệu? Các cơ chế thường gặp:

- **Immutable snapshot:** bảng trả kết quả theo đúng phiên bản dữ liệu tại thời điểm tạo; muốn dữ liệu mới thì tạo snapshot mới.
- **Versioned cache:** khóa chứa version hoặc mỗi lần dữ liệu đổi, xóa những entry liên quan.
- **Update-through:** thao tác cập nhật tự duy trì chỉ mục/bảng phụ, như Fenwick tree.
- **TTL/LRU:** giới hạn thời gian sống hoặc số entry để giảm rủi ro dữ liệu cũ/chiếm RAM. TTL **không tự bảo đảm** tính nhất quán tuyệt đối.

Một bảng kết quả có thể đúng ở thời điểm xây nhưng sai ở thời điểm đọc; đó là lỗi **đồng bộ trạng thái**, không phải lỗi công thức.

### Dữ liệu thay đổi và đối tượng có thể chỉnh sửa

Nếu cache giữ tham chiếu tới mảng/List có thể bị sửa ở bên ngoài, lần đọc sau có thể trả nội dung khác mà cache không được thông báo. Có thể chọn sao chép phòng vệ (defensive copy), đối tượng bất biến, copy-on-write hoặc ràng buộc API “caller không được sửa”; mỗi cách có chi phí và hợp đồng khác nhau.

**Tính đồng thời:** HashMap và các mảng thông thường không tự an toàn khi nhiều luồng cùng cập nhật. ConcurrentHashMap có thể giúp an toàn cho các thao tác map cụ thể, nhưng không tự biến một thuật toán gồm nhiều bước thành giao dịch nguyên tử. Cache stampede (nhiều luồng đồng thời tính cùng entry chưa có) cũng cần cân nhắc khi phép tính đắt.

### Thứ tự truy cập và không gian bộ nhớ

Một cache có kích thước không giới hạn dễ tăng dần theo số khóa duy nhất, làm tăng GC và nguy cơ hết bộ nhớ. Nếu số entry lớn, cần chọn:

- Có lưu toàn bộ trạng thái hay chỉ trạng thái đang nóng?
- Dùng mảng trực tiếp cho miền khóa dày và nhỏ, hay HashMap cho khóa thưa?
- Kích thước một entry gồm cả key, value, object header và cấu trúc bảng băm là bao nhiêu?
- Cần eviction LRU/LFU hay TTL không? Mỗi chính sách có chi phí vận hành, không giải quyết mọi kiểu tải.

Không nên chỉ so sánh O(n) với O(n) khi hai cấu trúc có hệ số nhớ thực tế khác nhau rất lớn.

## 10. Ví dụ Java 17: Prefix snapshot và Fibonacci memoization

Chương trình sau minh họa hai cách lưu kết quả trung gian khác nhau:

1. **PrefixSnapshot** tính trước tổng của mọi tiền tố trong một mảng long[], trả tổng đoạn nửa mở O(1). Nó không giữ tham chiếu đến dữ liệu đầu vào nên kết quả là **ảnh chụp** tại lúc tạo.
2. **FibonacciMemo** chỉ tính các trạng thái thực sự được hỏi qua lời gọi đệ quy, lưu chúng vào cache[] để các lần hỏi sau không phải tính lại.

Lưu vào tệp **IntermediateResultsDemo.java**:

~~~java
import java.util.Arrays;
import java.util.Objects;

public class IntermediateResultsDemo {
    static final class PrefixSnapshot {
        private final long[] prefix;

        PrefixSnapshot(int[] values) {
            Objects.requireNonNull(values, "values");
            prefix = new long[values.length + 1];
            for (int i = 0; i < values.length; i++) {
                prefix[i + 1] = prefix[i] + values[i];
            }
        }

        // Tong cua [from, to), voi 0 <= from <= to <= n.
        long sum(int from, int to) {
            int n = prefix.length - 1;
            if (from < 0 || to < from || to > n) {
                throw new IllegalArgumentException(
                        "require 0 <= from <= to <= n");
            }
            return prefix[to] - prefix[from];
        }
    }

    static final class FibonacciMemo {
        private final long[] cache = new long[93]; // F(0)..F(92).
        private int computedStates = 0;

        FibonacciMemo() {
            Arrays.fill(cache, -1L); // F(n) khong am; -1 la sentinel.
            cache[0] = 0L;
            cache[1] = 1L;
        }

        long fib(int n) {
            if (n < 0 || n > 92) {
                throw new IllegalArgumentException("n must be in [0,92]");
            }
            return compute(n);
        }

        private long compute(int n) {
            if (cache[n] >= 0) {
                return cache[n];
            }
            long value = compute(n - 1) + compute(n - 2);
            cache[n] = value;
            computedStates++;
            return value;
        }

        int computedStates() {
            return computedStates;
        }
    }

    public static void main(String[] args) {
        int[] values = {3, -1, 4, 2, -2};
        PrefixSnapshot snapshot = new PrefixSnapshot(values);

        System.out.println("sum [0,5) = " + snapshot.sum(0, 5));
        System.out.println("sum [1,4) = " + snapshot.sum(1, 4));
        System.out.println("sum [3,3) = " + snapshot.sum(3, 3));

        values[1] = 100; // Thay du lieu goc, snapshot khong doi.
        System.out.println("old snapshot = " + snapshot.sum(0, 5));
        PrefixSnapshot updated = new PrefixSnapshot(values);
        System.out.println("new snapshot = " + updated.sum(0, 5));

        FibonacciMemo memo = new FibonacciMemo();
        System.out.println("fib(10) = " + memo.fib(10) +
                "; computed = " + memo.computedStates());
        System.out.println("fib(8) = " + memo.fib(8) +
                "; computed = " + memo.computedStates());
        System.out.println("fib(12) = " + memo.fib(12) +
                "; computed = " + memo.computedStates());

        try {
            snapshot.sum(4, 2);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid range: " + ex.getMessage());
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac IntermediateResultsDemo.java
java IntermediateResultsDemo
~~~

**Stdout chính xác:**

~~~text
sum [0,5) = 6
sum [1,4) = 5
sum [3,3) = 0
old snapshot = 6
new snapshot = 107
fib(10) = 55; computed = 9
fib(8) = 21; computed = 9
fib(12) = 144; computed = 11
invalid range: require 0 <= from <= to <= n
~~~

### Vì sao các con số trên đúng?

- PrefixSnapshot dựng prefix=[0,3,2,6,8,6]. Do đó sum(0,5)=6; sum(1,4)=prefix[4]-prefix[1]=8-3=5; sum(3,3)=0.
- Sau khi đổi values[1] từ -1 thành 100, tổng thật tăng 101 thành 107. Snapshot cũ vẫn dựa trên dữ liệu tại thời điểm xây, nên trả 6. Snapshot mới được tạo lại trả 107.
- Với memo, F(0)=0 và F(1)=1 đã có sẵn; để tính F(10), đúng chín trạng thái mới F(2)..F(10) được tính lần đầu. Hỏi F(8) là cache hit, bộ đếm giữ 9. Hỏi F(12) chỉ cần tính F(11),F(12), bộ đếm thành 11.
- sum(4,2) sai vì cận trên nhỏ hơn cận dưới, nên bị từ chối có chủ đích. Không có truy cập ngoài mảng.

### Độ phức tạp và vòng đời

| Thành phần | Xây/tính lần đầu | Truy vấn sau đó | Bộ nhớ phụ |
| --- | --- | --- | --- |
| PrefixSnapshot trên n phần tử | O(n) | O(1) mỗi tổng đoạn | O(n) |
| FibonacciMemo cho một n≤92 | O(n) khi tính lần đầu, theo số trạng thái cần thiết | O(1) nếu giá trị đã cache | O(n) trạng thái và O(n) stack theo n nói chung |

Trong mã FibonacciMemo, mảng cache được cố định 93 phần tử vì miền n được giới hạn; về mặt phân tích thuật toán tổng quát, nếu n là một tham số lớn có biểu diễn số đủ rộng, ta cần O(n) trạng thái và có thể gặp stack sâu O(n). Mã ví dụ **không** tự mở rộng giới hạn long bằng việc thêm phần tử cache.

Mặc dù PrefixSnapshot không giữ tham chiếu đến values, nó vẫn chứa **kết quả tính từ values cũ**. Đây là thiết kế snapshot rõ ràng, chứ không phải cache tự biết dữ liệu đã thay đổi.

## 11. Các lỗi phổ biến trong đánh đổi thời gian–bộ nhớ

1. **Lưu kết quả nhưng không tính chi phí dựng:** tuyên bố một truy vấn O(1) mà bỏ qua O(n) tiền xử lý và O(n) bộ nhớ.
2. **Không xét số truy vấn và độ dài truy vấn:** dựng prefix cho một câu hỏi rất nhỏ có thể không lợi.
3. **Nhầm kiểu đoạn:** [l,r] và [l,r) dùng công thức prefix khác nhau; dễ off-by-one.
4. **Tràn số trước khi lưu:** biến sum kiểu int có thể tràn; cần cộng bằng long ngay từ đầu.
5. **Áp dụng phép trừ prefix cho min/max:** min không có phép nghịch đảo như tổng.
6. **Xem cache như dữ liệu luôn mới:** bỏ quên invalidation/rebuild khi nguồn thay đổi.
7. **Cache key thiếu tham số hoặc version:** trả kết quả của bài toán khác có cùng một phần khóa.
8. **Dùng 0 làm sentinel khi 0 là kết quả hợp lệ:** khiến trạng thái cache bị hiểu sai.
9. **Memoize hàm không thuần mà không xét tác dụng phụ:** có thể làm bỏ mất các thao tác cần thực hiện.
10. **Cache không giới hạn:** tiêu tốn RAM và chi phí GC, có thể chậm hơn tính lại.
11. **Giữ toàn bộ bảng DP khi chỉ cần hai trạng thái cuối:** bỏ lỡ cơ hội tối ưu bộ nhớ.
12. **Đọc/ghi cache đồng thời mà không kiểm soát:** race condition, dữ liệu không nhất quán hoặc tính trùng.
13. **Dùng prefix sums tĩnh cho dữ liệu động:** cập nhật một phần tử nhưng không duy trì những prefix chịu ảnh hưởng.
14. **Coi mọi tiền xử lý là O(n):** bảng 2D tốn O(HW), sparse table có thể O(n log n), bảng theo cả vị trí và giá trị có thể O(nR).

**Tư duy đúng:** luôn công bố chi phí theo bốn chiều **dựng – truy vấn – cập nhật – lưu trữ**, kèm hợp đồng về phiên bản dữ liệu. Big-O đơn lẻ của câu hỏi truy vấn chưa phản ánh toàn bộ bài toán.

## 12. Kiểm thử theo tính chất và các tình huống biên

### Với prefix sums

- Với mọi 0≤l≤r≤n, sum(l,r) phải bằng tổng quét trực tiếp của các phần tử a[l..r-1] tại thời điểm tạo snapshot.
- sum(l,l)=0; sum(0,n)=tổng toàn dãy.
- Với 0≤l≤m≤r≤n, sum(l,r)=sum(l,m)+sum(m,r).
- Dãy rỗng có prefix=[0], nên sum(0,0)=0; không được thử đọc a[0].
- Dãy có số âm, số 0 và giá trị trùng phải vẫn đúng.
- Khi dữ liệu gốc bị sửa, snapshot cũ phải vẫn trả **đúng dữ liệu cũ**, không phải tự đổi theo mảng mới.
- Với đoạn bất hợp lệ (l<0, r>n, l>r), hàm phải từ chối theo hợp đồng, không đọc ngoài phạm vi.

### Với memoization

- Fibonacci n=0 trả 0, n=1 trả 1, n=10 trả 55, n=12 trả 144.
- Cùng một n được hỏi nhiều lần không tăng số trạng thái mới tính.
- Hỏi n lớn rồi hỏi n nhỏ đã được tính không cần chạy lại cây đệ quy.
- Cận n âm hoặc >92 phải bị từ chối trước khi truy cập cache.
- Phải tránh nhầm giá trị 0 hoặc 1 là “chưa có”.

### Bảng kiểm thử mẫu

| Kịch bản | Kết quả quan trọng |
| --- | --- |
| a=[] | PrefixSnapshot.sum(0,0)=0 |
| a=[5] | sum(0,1)=5, sum(1,1)=0 |
| a=[3,-1,4,2,-2] | sum(1,4)=5, sum(0,5)=6 |
| a=[Integer.MAX_VALUE,Integer.MAX_VALUE] | Tổng là 4294967294 (long), không bị tràn int |
| a=[-9,-4,-7] | Prefix và hiệu hai prefix vẫn cho tổng âm đúng |
| Lệnh cập nhật a[1] sau khi tạo snapshot | Snapshot cũ không đổi; tạo lại để nhận dữ liệu mới |
| fib(10) rồi fib(8) | Bộ đếm trạng thái mới không tăng |
| fib(92) | 7540113804746346429, còn trong long |
| fib(93) | Từ chối; không trả kết quả tràn dấu |
| sum(l,r) với l>r | Ném IllegalArgumentException |

Nếu tạo bộ kiểm thử ngẫu nhiên, hãy so nhiều truy vấn đoạn với lời giải O(n) đơn giản trên mảng nhỏ. Đối với bảng/đồ thị lớn, cần kiểm thử cả **điểm trong vòng đời**: trước khi cập nhật, ngay sau cập nhật, sau rebuild và khi đọc đồng thời (nếu thiết kế hỗ trợ).

## 13. Câu hỏi thực hành và checklist lựa chọn

1. Cho a=[2,-3,5,1,4] và các truy vấn tổng đoạn [0,5), [1,4), [2,2). Tự dựng prefix và tính từng đáp án; ghi rõ quy tắc đoạn nửa mở.
2. Một dãy 100.000 phần tử nhận 10 truy vấn đoạn ngắn và chỉ tồn tại trong một thao tác. So chi phí với 100.000 truy vấn đoạn dài trên cùng dãy; khi nào dựng prefix mới có lợi?
3. Khi thay đổi a[i] thêm delta, những phần tử prefix nào cần cập nhật? So với Fenwick tree khi có 10.000 cập nhật xen giữa 10.000 truy vấn.
4. Viết memoization cho hàm đếm số cách leo cầu thang với bước 1 hoặc 2, chú ý các base case và overflow. Nếu trạng thái gồm (i,remaining), dùng khóa nào?
5. So sánh memory của bảng DP đầy đủ và biến trạng thái cuốn chiếu khi chỉ cần nghiệm cuối. Nêu một tình huống buộc phải giữ bảng để truy vết đường đi.
6. Với bài toán đếm số lần xuất hiện của x trên nhiều đoạn, so bảng prefix theo mọi giá trị, HashMap chứa danh sách vị trí, và quét trực tiếp. Vì sao bảng prefix n×R không phù hợp khi R rất lớn?
7. Một ứng dụng cache kết quả truy vấn sau khi dữ liệu đã đổi. Đề xuất version key, invalidation hoặc snapshot; kiểm thử kết quả sai âm thầm được phát hiện thế nào?
8. Cho mảng 2D 3×4, tự dựng prefix 2D và áp dụng bốn góc để lấy tổng hình chữ nhật; chứng minh tránh đếm trùng bằng bao hàm–loại trừ.

**Checklist khi quyết định dùng bộ nhớ để tiết kiệm thời gian:**

- Truy vấn nào lặp lại? Có bao nhiêu truy vấn, và độ dài/chi phí tính trực tiếp của chúng?
- Có thể xây kết quả trung gian nào trả lời đúng các truy vấn ấy? Công thức hoặc bất biến là gì?
- Tổng chi phí B(n)+qQ(n)+uU(n) so với cách trực tiếp thế nào? S(n) có nằm trong giới hạn RAM không?
- Dữ liệu có thay đổi sau tiền xử lý? Chính sách invalidation, rebuild hoặc versioning là gì?
- Có cần giữ mọi trạng thái, hay chỉ vài trạng thái gần nhất hoặc vài khóa được truy cập nhiều?
- Các trường hợp rỗng, chỉ số biên, tràn số, đồng thời và sai khác kiểu dữ liệu đã được kiểm thử chưa?

**Kết luận:** lưu kết quả trung gian là kỹ thuật **đổi công tính lặp thành dữ liệu tái sử dụng**. Prefix sums, memoization, tabulation và các chỉ mục đều có thể giảm thời gian truy vấn, nhưng hiệu quả và tính đúng phụ thuộc vào **số lần tái sử dụng, cấu trúc trạng thái, bộ nhớ cho phép và cách đồng bộ khi dữ liệu thay đổi**. Không phải cứ thêm cache là tối ưu; tối ưu là chọn đúng thông tin cần lưu để đáp ứng đúng tải công việc.
