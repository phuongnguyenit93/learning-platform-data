# Chọn chỉ mục theo số lượng truy vấn và kích thước văn bản

**Chọn chỉ mục theo số lượng truy vấn và kích thước văn bản** là bài toán quyết định **nên quét văn bản cho từng mẫu hay trả chi phí tiền xử lý để xây một cấu trúc tra cứu có thể dùng lại**. Cùng một thuật toán tìm kiếm chuỗi có thể rất phù hợp trong một bài có vài truy vấn, nhưng trở thành nút thắt khi có hàng nghìn truy vấn trên văn bản không thay đổi. Ngược lại, xây một chỉ mục nặng cho một truy vấn duy nhất có thể chậm hơn nhiều so với quét trực tiếp.

Bài thuộc nhóm **Xử lý chuỗi nâng cao** của Computer Science Algorithms. Ta sẽ thiết lập một mô hình chi phí theo kích thước văn bản, số truy vấn và bộ nhớ; so sánh tìm trực tiếp, KMP, Z-function, suffix array, suffix automaton, suffix tree, Aho–Corasick, rolling hash và chỉ mục nén; đưa ra quy trình quyết định thực tế; sau đó dùng **Java 17** để minh họa cách chọn chiến lược, tìm chính xác mọi vị trí mẫu bằng KMP hoặc suffix array, và kiểm chứng với oracle vét cạn.

**Thông điệp cốt lõi:** không có “chỉ mục tốt nhất” cho mọi bài. Cần xét **bài toán truy vấn cụ thể**, **số lần tái sử dụng chỉ mục**, **chi phí xây dựng**, **chi phí trả lời và xuất kết quả**, **bộ nhớ**, và **văn bản có bị cập nhật hay không**.

## 1. Xác định workload trước khi chọn thuật toán

Đặt:
- `n=|T|`: độ dài văn bản T. Trong phần Java của bài, độ dài đo bằng **Unicode code point**.
- `q`: tổng số truy vấn tìm mẫu trên cùng một phiên bản của T.
- `P_i`: mẫu ở truy vấn thứ i, có độ dài `m_i`.
- `k_i`: số vị trí khớp được trả về ở truy vấn thứ i.
- `M`: ngân sách bộ nhớ cho chỉ mục.
- `u`: số lần văn bản bị sửa trong khoảng thời gian sử dụng.
- `\Sigma`: bảng ký tự, ảnh hưởng tới cấu trúc chuyển cạnh và chi phí so sánh.

Hai tổng thường quan trọng:

\[
\sum_{i=1}^{q}m_i
\qquad\text{và}\qquad
\sum_{i=1}^{q}k_i.
\]

Không nên chỉ nhìn `n` rồi chọn thuật toán; cùng n nhưng `q=1` và `q=100000` có tính kinh tế tiền xử lý hoàn toàn khác nhau.

### Những câu hỏi cần trả lời

1. **Một mẫu hay nhiều mẫu?** Một mẫu duy nhất chạy một lần; nhiều mẫu biết sẵn và có thể xử lý đồng thời; hay mẫu đến dần sau khi văn bản đã chuẩn bị?
2. **Văn bản tĩnh hay động?** Một tệp không đổi, các phiên bản cập nhật thỉnh thoảng, hay luồng đang nhận dữ liệu liên tục?
3. **Loại câu hỏi:** mẫu có xuất hiện không; xuất hiện bao nhiêu lần; ở những vị trí nào; đoạn con bất kỳ; tiền tố chung; truy vấn xấp xỉ?
4. **Số kết quả:** một truy vấn trả 0 vị trí hay hàng triệu vị trí? Dù chỉ mục tra cứu rất nhanh, **ghi ra k kết quả cần ít nhất Ω(k)** thời gian.
5. **Bộ nhớ:** có đủ giữ chỉ mục O(n) phần tử hay không? Trong Java, `Integer[]`, đối tượng và HashMap có overhead không nhỏ.
6. **Ký tự và chuẩn hóa:** dữ liệu là byte ASCII, Unicode code point, UTF-16, token từ ngữ, hay thứ tự từ điển theo ngôn ngữ?
7. **Thời gian thực / latency:** cần trả một truy vấn cực nhanh, hay chỉ cần tổng thời gian cho cả batch nhỏ nhất?
8. **Cần định vị vị trí khớp hay chỉ đếm?** Một số chỉ mục có thể kiểm tra tồn tại/đếm nhanh nhưng muốn xuất vị trí lại cần dữ liệu bổ sung.

**Phải biết đầu ra trước khi tối ưu cấu trúc.** Ví dụ suffix automaton rất hợp để hỏi “P có là một chuỗi con của T không?” nhưng không tự cấp phát một danh sách các vị trí bắt đầu trong thời gian O(m+k) nếu chưa bổ sung cơ chế truy vết vị trí.

## 2. Quét trực tiếp, KMP và Z: không cần chỉ mục lớn

### Quét ngây thơ (naive search)

Với mỗi vị trí j từ 0 tới n−m, thử so mẫu P với đoạn T bắt đầu ở j, dừng ngay khi khác.

- Một truy vấn: **O(nm)** trong trường hợp xấu.
- Bộ nhớ phụ nếu không tính kết quả: **O(1)** cho con trỏ/so sánh.
- Rất dễ cài, hữu ích làm **oracle để kiểm chứng** thuật toán khác.
- Với mẫu ngắn và dữ liệu thực tế không đối kháng, nhiều phép so thất bại sớm; hiệu năng có thể tốt, nhưng **không được xem thời gian trung bình tốt là bảo đảm O(n)**.

Ví dụ `T="aaaaaaaa..."` và `P="aaaaab"` có thể gây rất nhiều phép so lại, làm quét trực tiếp tốn gần nm.

### KMP — xây thông tin cho mẫu, quét văn bản

KMP dùng prefix function/failure links để không so lại tiền tố của mẫu khi một bước khớp thất bại.

- Tiền xử lý **mẫu P**: O(m), lưu mảng `pi[]` O(m).
- Quét **một văn bản T**: O(n), tìm được mọi vị trí khớp, kể cả chồng lấn.
- Mỗi truy vấn mẫu độc lập: **O(n+m)** thời gian, O(m) bộ nhớ phụ ngoài các vị trí trả về.
- Có thể quét T theo **luồng** mà không phải lưu cả văn bản trong một mảng chỉ mục.

KMP rất phù hợp khi **q nhỏ**, T có thể đổi giữa các truy vấn, bộ nhớ hạn chế, hoặc cần triển khai an toàn với độ phức tạp tuyến tính được chứng minh.

### Z-function và chuỗi ghép

Một cách tương tự về độ phức tạp là tạo dãy `P + sentinel + T`, tính Z trên dãy, rồi kiểm tra `Z[m+1+j]≥m` cho mỗi vị trí j trong T.

- Mỗi truy vấn: **O(n+m)** thời gian.
- Bản lưu toàn bộ dãy ghép và mảng Z: **O(n+m)** bộ nhớ.
- Thuận tiện cho bài tiền tố khớp và xử lý chuỗi ghép; nhưng nếu chỉ cần quét T với ít bộ nhớ, **KMP thường thuận lợi hơn về không gian**.

**Điểm quan trọng:** việc xây mảng pi cho từng P không phải là xây một chỉ mục lớn dùng lại cho **mọi P trên T**. Với q mẫu khác nhau, KMP/Z vẫn duyệt T về cơ bản một lần **cho mỗi mẫu**.

## 3. Chỉ mục trên văn bản: suffix array

**Suffix array (SA)** lưu vị trí bắt đầu của tất cả **hậu tố không rỗng** của T, theo thứ tự từ điển. Sau khi xây, mọi hậu tố có tiền tố P tạo thành **một đoạn liên tiếp trong SA**.

Giả sử T="banana":

~~~text
SA = [5,3,1,0,4,2]

rank  start  suffix
0     5      a
1     3      ana
2     1      anana
3     0      banana
4     4      na
5     2      nana
~~~

Khi hỏi P="ana", chỉ cần **hai binary search** tìm hai biên của nhóm hậu tố bắt đầu bằng "ana". Vùng SA khớp chứa các vị trí [3,1] theo thứ tự từ điển; nếu muốn trả kết quả tăng theo vị trí văn bản, sort thành **[1,3]**.

### Chi phí bản prefix doubling trong Java

Bản minh họa xây SA bằng cách:
1. Gán rank ban đầu theo giá trị code point.
2. Lần lượt so cặp `(rank[i],rank[i+len])` với len = 1,2,4,8,...
3. Với `i+len≥n`, dùng sentinel hạng **−1**, đứng trước mọi code point.
4. Sort chỉ số hậu tố theo cặp rank cũ, nén rank mới, dừng khi mọi hậu tố khác hạng.

Nếu dùng `Arrays.sort(Integer[], comparator)`, mỗi vòng sort O(n log n), có O(log n) vòng:

\[
\boxed{\text{Xây SA: }O(n\log^2 n)\text{ thời gian, }O(n)\text{ bộ nhớ phụ}.}
\]

Đây là độ phức tạp **của bản Java trong bài**, không phải giới hạn tốt nhất. Có thể dùng counting/radix sort cặp hạng để đạt O(n log n), hoặc các thuật toán xây tuyến tính trong mô hình phù hợp.

Với mẫu dài m:
- **Có xuất hiện không / đếm số hậu tố khớp:** hai binary search, mỗi lần so có thể đọc tối đa m code point, nên **O(m log n)**.
- **Trả k vị trí theo thứ tự SA:** O(m log n + k).
- **Trả k vị trí tăng theo thứ tự trong T:** cần thêm sort k vị trí, thành **O(m log n + k log k)**.

Chỉ mục **không xóa đi chi phí xuất k kết quả**. Nếu `T="aaaa..."` và `P="a"`, k≈n, thì dù tìm hai biên cực nhanh vẫn phải trả gần n vị trí.

### Suffix array hợp với dạng truy vấn nào?

- Cùng một T **ít hoặc không đổi**, có nhiều mẫu P đến **lần lượt và không biết trước**.
- Cần tra tiền tố của hậu tố, đếm số lần xuất hiện, định vị vị trí.
- Cần thêm các truy vấn như LCP, số chuỗi con phân biệt, đoạn lặp, thứ tự từ điển của chuỗi con: có thể dùng thêm **LCP và RMQ** tùy câu hỏi.

Không nên xây SA chỉ vì T dài, nếu **q=1** và cần tìm một mẫu chính xác: bản KMP O(n+m) thường là lựa chọn cơ sở dễ triển khai hơn.

### LCP và các phần bổ trợ có chi phí

Mảng `LCP[r]` giữa hai hậu tố kề nhau theo SA có thể được xây O(n) bằng Kasai sau khi có SA. Một RMQ trên LCP giúp trả lời LCP của hai hậu tố bất kỳ, nhưng RMQ cũng cần tiền xử lý/bộ nhớ riêng. Không tính những phần bổ trợ này là “miễn phí” nếu workload không cần chúng.

## 4. Suffix automaton và suffix tree: khi truy vấn thay đổi

### Suffix automaton (SAM)

Suffix automaton biểu diễn tất cả **chuỗi con** của một T bằng trạng thái và chuyển cạnh.

- Xây dựng thường **O(n)** theo số ký tự trong mô hình giả định thao tác chuyển cạnh phù hợp; số state tối đa O(n) (thường không quá 2n−1 cho n≥2).
- Hỏi một P có xuất hiện dưới dạng chuỗi con hay không: đi theo các cạnh ký tự, **O(m)** kỳ vọng/được bảo đảm theo cấu trúc map, tùy kiểu chuyển cạnh.
- Có thể đếm số lần xuất hiện nếu xây thêm thông tin `endpos`/occurrence count và lan truyền đúng theo thứ tự độ dài.
- Muốn **liệt kê vị trí bắt đầu** cần thiết kế thêm phần truy vết, không thể coi mặc định mọi truy vấn vị trí đều O(m).

SAM rất đáng cân nhắc cho **rất nhiều truy vấn membership**, bài toán chuỗi con khác nhau, hoặc **văn bản chỉ được nối thêm ở cuối** và mô hình cập nhật phù hợp. Xóa/chèn giữa văn bản không thể tự giả định SAM cập nhật O(1).

### Suffix tree

Suffix tree nén trie của mọi hậu tố, cho phép lần theo cạnh theo các đoạn ký tự:
- Có thuật toán xây thời gian tuyến tính trong một số giả thiết bảng chữ cái và mô hình thao tác.
- Tìm mẫu về bản chất theo độ dài mẫu, thường **O(m)** để xác định locus, rồi còn chi phí **O(k)** nếu liệt kê k vị trí.
- Có thể dùng cho LCP, chuỗi lặp, nhiều truy vấn chuỗi con.

Đổi lại, cài đặt khá khó; số đối tượng, pointer và nhãn cạnh có thể làm bộ nhớ lớn hơn SA mảng trên thực tế. Không chọn suffix tree chỉ dựa vào cận Big-O đẹp khi bộ nhớ và độ phức tạp triển khai là hạn chế.

### Khi nào SAM hơn SA?

Nếu truy vấn chỉ hỏi **"P có tồn tại không?"** trên T lớn, nhiều lần, và bộ nhớ cho chuyển trạng thái phù hợp, SAM có thể trả lời O(m), không có nhân log n của binary search trên SA. Nếu cần thường xuyên **danh sách vị trí** hoặc **thứ tự từ điển của hậu tố**, SA thường là lựa chọn trực tiếp, dễ hình dung hơn.

## 5. Aho–Corasick: nhiều mẫu biết trước, quét văn bản một lượt

Đây là một trục quyết định **khác** với “xây chỉ mục trên T”. Nếu **cả bộ mẫu** `P_1,...,P_q` đã biết trước và cần tìm chúng trong **cùng T**, thay vì xây SA trên T, ta có thể xây **trie và failure links trên các mẫu** rồi duyệt T **một lần** bằng Aho–Corasick.

Đặt `L=\sum_i |P_i|` là tổng độ dài các mẫu, `K` là tổng số kết quả khớp của mọi mẫu.

Trong cách cài đặt có chuyển cạnh hiệu quả, độ phức tạp điển hình là:

\[
\boxed{O(L+n+K)\text{ cho xây bộ mẫu và quét văn bản},}
\]

với chi phí chuyển trạng thái phụ thuộc cách lưu bảng chữ cái và failure transitions. Bộ nhớ theo số nút trie và các cạnh chuyển; cách lưu dense transition table có thể tốn nhiều hơn sparse map, đặc biệt trên Unicode.

**Ưu thế thực tế:** thay vì q lần quét T bằng KMP, ta chỉ quét T một lượt cho cả q mẫu. Đây có thể là chiến lược tốt nhất khi **q rất lớn và tất cả mẫu đã được cho trước**.

Ví dụ một bộ 10.000 từ khóa đã cố định, cần tìm mọi lần chúng xuất hiện trong một log dài: Aho–Corasick là ứng viên tự nhiên. Nếu các mẫu tới **từng truy vấn độc lập theo thời gian**, không biết trước toàn bộ, việc xây lại automaton của cả bộ mỗi lần thay đổi không còn hấp dẫn như trong batch tĩnh.

**Chú ý:** kết quả có thể cực lớn khi nhiều mẫu có tiền tố/hậu tố trùng nhau và văn bản lặp; thuật toán vẫn phải trả `K` kết quả nếu đề yêu cầu liệt kê tất cả. Mẫu rỗng cần quy ước/hợp đồng riêng; nhiều thư viện Aho–Corasick thường không hỗ trợ mẫu rỗng giống cách đếm mọi ranh giới.

### Aho xây trên mẫu, SA/SAM xây trên văn bản

Đây là khác biệt chiến lược:
- **SA/SAM:** trả chi phí xây trên **T** để đáp ứng nhiều P bất kỳ.
- **Aho–Corasick:** trả chi phí xây trên **tập P biết trước** để quét **T một lượt**.
- **KMP/Z:** trả chi phí nhẹ theo từng P, duyệt T mỗi lần.

Vì thế trước khi hỏi “nên xây chỉ mục gì?”, hãy xác định **bên nào được tái sử dụng**: văn bản, tập mẫu, hay cả hai.

## 6. Rolling hash, n-gram và chỉ mục theo độ dài cố định

**Rolling hash** có thể tính hash của những đoạn con bằng tiền tố băm và luỹ thừa, để so hash đoạn con trong O(1) sau tiền xử lý. Nó hữu ích cho:
- kiểm tra đoạn con bằng nhau sau nhiều truy vấn;
- binary search độ dài đoạn trùng;
- gom nhóm nhiều đoạn con độ dài cố định;
- xây bảng băm vị trí của các k-gram khi tất cả mẫu có cùng độ dài k.

Nhưng có hai lưu ý quan trọng:
1. **Hash collision:** hai chuỗi khác nội dung có thể có cùng giá trị hash. Với yêu cầu **không được sai**, cần xác minh ký tự thật khi hash bằng nhau hoặc dùng phương án có bảo đảm.
2. **Một bảng băm cho độ dài k** không tự nhiên là chỉ mục tổng quát tốt cho hàng nghìn mẫu với **mọi độ dài khác nhau**. Nếu tạo bảng cho mọi độ dài, chi phí lưu trữ có thể tăng đến O(n²).

Đối với nhiều truy vấn chứa từ hoặc token, **inverted index** (ánh xạ token → danh sách tài liệu/vị trí) có thể hợp hơn. Nó phục vụ tìm theo **từ/cụm từ** sau tokenization, **không đồng nhất** với phép tìm chuỗi con ký tự tùy ý. Ví dụ tìm "ana" trong "banana" là substring matching; chỉ mục token theo từ "banana" không tự trả ra kết quả substring "ana".

### FM-index và chỉ mục nén

Với tập văn bản rất lớn và bộ nhớ quan trọng, có thể cân nhắc **FM-index** dựa trên Burrows–Wheeler transform và cấu trúc rank. Nó cho phép **backward search** để đếm/kiểm tra mẫu với không gian nén trong các cài đặt phù hợp. Tuy nhiên:
- Chi phí thao tác phụ thuộc cấu trúc rank/select và cách mã hóa bảng chữ cái.
- Muốn **liệt kê vị trí**, cần thêm cấu trúc lấy mẫu SA hoặc hỗ trợ locate; không được coi vị trí xuất ra miễn phí.
- Xây chỉ mục nén, hỗ trợ Unicode/tập văn bản lớn, và cập nhật có thể phức tạp.

Nếu có giới hạn RAM nghiêm ngặt và dữ liệu chủ yếu đọc, FM-index là ứng viên để nghiên cứu/benchmark. Không thể chỉ so Big-O mà bỏ qua chi phí truy xuất, tỷ lệ nén, thời gian build và độ phức tạp bảo trì.

## 7. Bảng so sánh theo nhu cầu

| Phương án | Tiền xử lý | Một truy vấn mẫu dài m | Bộ nhớ chỉ mục (không tính kết quả) | Điểm phù hợp |
| --- | --- | --- | --- | --- |
| Quét trực tiếp | O(1) | O(nm) xấu nhất | O(1) | Thử nghiệm, oracle, mẫu nhỏ |
| KMP | O(m) cho từng mẫu | O(n+m) | O(m) | Ít truy vấn, streaming, T thay đổi |
| Z với P + sentinel + T | O(n+m) mỗi lần | O(n+m) | O(n+m) | Bài tiền tố, chuỗi ghép |
| Suffix array (bản comparator) | O(n log²n) cho T | O(m log n + k log k) để trả k vị trí tăng dần | O(n) | T tĩnh, nhiều P độc lập, cần vị trí |
| Suffix automaton | Thường O(n) trên T | O(m) tìm tồn tại, không gồm locate | O(n) state/transitions ở mô hình phù hợp | Nhiều truy vấn membership |
| Suffix tree | Có thuật toán O(n) xây | O(m+k) khi tìm và xuất vị trí | O(n), hằng số lớn | Truy vấn tiền tố hậu tố phức tạp |
| Aho–Corasick | O(L) hoặc có thêm chi phí theo alphabet | Quét một lượt T: O(n+K) sau build | O(L) nodes/transitions tùy cài đặt | Bộ nhiều mẫu **biết trước** |
| Hash k-gram | O(n) cho một k | Truy xuất hash và xác minh ứng viên, chi phí phụ thuộc số ứng viên | O(n) cho k cố định | Rất nhiều mẫu cùng chiều dài |
| FM-index | Theo cài đặt | Backward search theo m và cấu trúc rank; locate cộng thêm | Dạng nén | Văn bản rất lớn, truy vấn đọc |
| Inverted index | Theo số token/dữ liệu | Tra token/postings, không phải substring bất kỳ | Theo postings | Tìm từ/ngữ nghĩa token |

**Chú giải:** k trong cột thời gian là số lần khớp được trả về; L là tổng độ dài của các mẫu đã biết, K là tổng số kết quả khi quét nhiều mẫu. Các cận của SAM, suffix tree và Aho giả định cấu trúc chuyển cạnh tương ứng có chi phí phù hợp; trên bảng chữ cái Unicode hoặc sparse maps, hằng số/cận có thể thay đổi.

## 8. Công thức hòa vốn (break-even) cho chỉ mục

Để so một chiến lược **quét từng truy vấn** với một chiến lược **xây chỉ mục trên T**, đặt:
- `B`: chi phí xây chỉ mục một lần.
- `S`: chi phí quét một truy vấn **không có chỉ mục**.
- `R`: chi phí trả lời một truy vấn **sau khi có chỉ mục**.
- `q`: số truy vấn được thực hiện trên **cùng phiên bản văn bản**.

Tổng chi phí xấp xỉ:

\[
C_{scan}=qS,
\qquad
C_{index}=B+qR.
\]

Chỉ mục có lợi về tổng chi phí khi:

\[
B+qR<qS.
\]

Nếu `S>R`, chuyển vế:

\[
\boxed{q>\frac{B}{S-R}.}
\]

Đây là **ngưỡng số truy vấn hòa vốn**, về ý tưởng. Nếu `S≤R`, chỉ mục không có lợi theo mô hình chi phí đơn giản đó. Dĩ nhiên phải **đủ bộ nhớ** và không bị chi phí cập nhật làm mất lợi ích.

### Mô hình đơn vị thao tác minh họa cho SA

Đặt một truy vấn có mẫu trung bình dài `\bar m` và dùng bản SA comparator:

\[
B\approx n(\log_2 n)^2,\quad
S\approx n+\bar m,\quad
R\approx \bar m\log_2 n.
\]

Khi đó:

\[
C_{scan}\approx q(n+\bar m),\qquad
C_{SA}\approx n(\log_2 n)^2+
q\bar m\log_2 n.
\]

Đây **chỉ là mô hình tính toán/giáo dục**, không phải thời gian đo thực tế. Nó **bỏ qua** hằng số của comparator, cấp phát/GC trong Java, chi phí truy cập bộ nhớ, sort k vị trí kết quả, sự khác nhau của độ dài mẫu và các tối ưu chỉ mục khác.

Với `n=1.000.000`, `\bar m=8`, `\log_2 n≈20`:
- Xây SA theo mô hình: khoảng `1.000.000×20²=400.000.000` đơn vị.
- Một lần quét KMP: khoảng `1.000.008` đơn vị.
- Một truy vấn SA: khoảng `8×20=160` đơn vị chưa tính xuất kết quả.
- Ngưỡng hòa vốn theo mô hình nằm quanh **400 truy vấn**.

Vì thế:
- Chỉ **q=2** truy vấn: quét KMP hai lần là lựa chọn hợp lý.
- **q=5.000** truy vấn độc lập trên T tĩnh, bộ nhớ đủ: xây SA trở nên hấp dẫn.
- Nếu cả 5.000 mẫu đã biết sẵn và chỉ cần quét T một lần, **Aho–Corasick có thể còn phù hợp hơn**.

Không nên biến ngưỡng 400 thành một quy tắc cố định cho mọi máy hay dữ liệu. Nó thay đổi rất mạnh theo thuật toán xây SA, độ dài trung bình/độ phân bố mẫu, số kết quả, JVM warm-up, cache, cách đọc/ghi và ngân sách RAM.

### Những chi phí dễ bị quên

**Chi phí kết quả.** Nếu một mẫu xuất hiện k lần, dù chỉ mục xác định nhanh đoạn hậu tố khớp, vẫn phải tạo, lưu, truyền hoặc in k vị trí. Khi k gần n, phần xuất kết quả có thể áp đảo thời gian tra cứu.

**Chi phí cập nhật.** Với T sửa u lần, suffix array thường phải xây lại sau mỗi phiên bản mới nếu không có kỹ thuật duy trì động. Tổng chi phí có thể thành `(u+1)B`, chứ không còn B. Nếu mỗi phiên bản chỉ có vài truy vấn, việc tái xây chỉ mục nhiều lần không đáng.

**Bộ nhớ.** Big-O O(n) không tự bảo đảm vừa RAM. Trong Java, một mảng `int[]` n phần tử dùng khoảng 4n byte cho payload; nhiều mảng, `Integer[]`, object boxing, SA/LCP và overhead GC làm bộ nhớ thực tế cao hơn đáng kể. Khi n=10⁷ hoặc hơn, cần ước lượng byte và benchmark.

**Trạng thái cache và latency.** Chi phí tổng thời gian q truy vấn không đồng nghĩa độ trễ của **truy vấn đầu tiên**. Xây chỉ mục trước khi trả câu hỏi đầu có thể không phù hợp một hệ thống bắt buộc phản hồi ngay.

## 9. Quy trình chọn chiến lược

**Bước 1 — Xác định chính xác bài toán.** Nếu đề chỉ hỏi substring exact match, các phương án trên phù hợp. Nếu muốn tìm không dấu, fuzzy match, edit distance, token search hay xếp hạng tài liệu, phải thay đổi mô hình trước.

**Bước 2 — Kiểm tra tính sẵn có của mẫu.**
- **Một/một vài mẫu, chưa cần tái sử dụng:** KMP hoặc Z, đôi khi brute force đủ.
- **Rất nhiều mẫu biết trước và quét một văn bản/batch:** Aho–Corasick.
- **Mẫu đến về sau, độc lập, T dùng lâu và ít thay đổi:** chỉ mục trên T như SA hoặc SAM.

**Bước 3 — Chốt loại câu hỏi.**
- Chỉ tồn tại hay không: SAM có thể rất mạnh khi có nhiều truy vấn.
- Cần danh sách vị trí: SA hỗ trợ trực tiếp đoạn kết quả; KMP vẫn đơn giản cho q nhỏ.
- Cần LCP, thứ tự hậu tố, số chuỗi con phân biệt: SA + LCP đáng xem xét.
- Cần tìm token trong nhiều tài liệu: inverted index thay vì suffix structure của từng ký tự.
- Cần nén trên bộ dữ liệu rất lớn: cân nhắc FM-index và chi phí locate.

**Bước 4 — Kiểm tra vòng đời văn bản.**
- T tĩnh: index-build amortization dễ tính.
- T chỉ nối thêm: KMP streaming cho luồng truy vấn; SAM có thể hỗ trợ nối thêm với một số mục tiêu.
- T liên tục chèn/xóa giữa: SA tĩnh phải xây lại; xem xét phương án cập nhật động chuyên biệt hoặc quét theo lần.

**Bước 5 — Tính ngưỡng và bộ nhớ.** Ước lượng q, phân bố m, k, số phiên bản, byte index. Loại phương án vượt RAM hoặc latency. Đừng coi số truy vấn quá khứ là số truy vấn chắc chắn sẽ đến trong tương lai.

**Bước 6 — Benchmark trên dữ liệu đại diện.** Đo riêng thời gian build, thời gian từng truy vấn, tổng thời gian, p95 latency, peak memory/GC và tốc độ xuất kết quả. Warm-up JVM hợp lý; dùng cùng tập mẫu và cùng yêu cầu đầu ra khi so.

**Bước 7 — Xác minh tính đúng bằng oracle.** Với dữ liệu nhỏ, so tất cả vị trí của KMP/SA/Aho... với so khớp trực tiếp; có mẫu rỗng, Unicode và các lần khớp chồng lấn.

### Cây quyết định tóm tắt

~~~text
Có q truy vấn cần xử lý?
├─ Không → không cần xây chỉ mục
└─ Có
   ├─ T cập nhật thường xuyên?
   │  └─ Có → ưu tiên quét/KMP hoặc cấu trúc động phù hợp
   ├─ Bộ nhớ không đủ cho chỉ mục?
   │  └─ Có → KMP/streaming, cân nhắc cấu trúc nén
   ├─ Tất cả mẫu đã biết trước và cùng được quét?
   │  └─ Có → cân nhắc Aho–Corasick
   └─ Mẫu đến độc lập trên T tĩnh
      ├─ q dưới ngưỡng hòa vốn → KMP/Z
      └─ q vượt ngưỡng và đủ RAM
         ├─ Cần vị trí/thứ tự suffix → suffix array
         ├─ Chủ yếu hỏi tồn tại → suffix automaton
         └─ Corpus nén cực lớn → FM-index
~~~

Cây này giúp **thu hẹp lựa chọn**, không phải thuật toán chọn tuyệt đối. Trong trường hợp ranh giới, benchmark luôn có giá trị hơn việc dùng một ngưỡng cứng.

## 10. Case study: ba workload, cùng một văn bản

Giả sử hệ thống có T dài khoảng **một triệu code point**, mẫu trung bình dài 8.

| Workload | Mục tiêu | Lựa chọn cần cân nhắc |
| --- | --- | --- |
| **A:** 2 truy vấn, T đọc một lần | Tìm tất cả vị trí hai mẫu | KMP hai lần; xây SA khó hoàn vốn |
| **B:** 5.000 truy vấn đến từ người dùng theo thời gian, T không đổi | Tìm vị trí nhiều P khác nhau | SA có thể hoàn vốn và giảm thời gian truy vấn |
| **C:** 5.000 mẫu biết trước, cần tìm tất cả trong một lượt quét | Quét batch từ khóa | Aho–Corasick thường rất đáng cân nhắc |

Nếu T đổi sau mỗi 3 truy vấn, workload B trở thành nhiều phiên bản khác nhau. Phải tính lại lợi ích chỉ mục theo **q trên từng phiên bản**, không dùng q cộng gộp mọi phiên bản.

Nếu workload B chỉ hỏi **mẫu có tồn tại không**, không cần vị trí, một suffix automaton có thể thay đổi lựa chọn. Nếu workload B chủ yếu có mẫu "a" trong văn bản toàn chữ a, số vị trí kết quả k rất lớn, việc xây SA không loại bỏ thời gian xuất kết quả.

### Khi một truy vấn chỉ cần số lượng khớp

Trong suffix array, hai biên `[lo,hi)` chứa tất cả hậu tố bắt đầu bằng P, nên số lần xuất hiện bằng **hi−lo**, không cần sort/vật chất hóa k vị trí. Tùy ứng dụng, **đếm k** có thể nhanh hơn rất nhiều so với **liệt kê k**. Trong Java minh họa dưới đây, phương thức trả **tất cả vị trí**, vì thế còn chi phí sort kết quả.

## 11. Java 17: cùng một text, KMP và suffix array

Chương trình đầy đủ sau có ba phần tách biệt:
1. **Công cụ quyết định minh họa** `recommend` dùng mô hình chi phí build/quét/truy vấn, phân biệt T thay đổi, bộ mẫu biết trước, và giới hạn RAM. Nó chỉ trả **gợi ý**, không phải bằng chứng phương án nhanh nhất.
2. Hai thuật toán **đã cài đầy đủ và thực thi được**: KMP không xây chỉ mục trên T và prefix-doubling suffix array có thể dùng lại cho nhiều mẫu. Chương trình **không cài đặt Aho–Corasick**, dù bộ gợi ý có thể đề xuất nó cho workload nhiều mẫu biết trước.
3. Bộ kiểm thử độc lập dùng `naiveMatches` và `naiveSuffixArray` để so kết quả của KMP và SA.

Các vị trí trả về đều là **0-based Unicode code point offset**. Hàm đổi sang **UTF-16 Java String offset** được cung cấp riêng. Mẫu rỗng được quy định khớp tại **n+1 ranh giới**, kể cả sau ký tự cuối của text.

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

public class ChoosingTextIndexDemo {
    enum Recommendation {
        NO_QUERIES,
        KMP_PER_QUERY,
        AHO_CORASICK_BATCH,
        SUFFIX_ARRAY
    }

    // Heuristic giao duc, KHONG phai benchmark.
    // canKeepIndex: du RAM cho persistent text index.
    static Recommendation recommend(
            long n, long q, long averagePatternLength,
            boolean textChanges,
            boolean allPatternsKnownTogether,
            boolean canKeepIndex) {
        if (n < 0 || q < 0 || averagePatternLength < 0) {
            throw new IllegalArgumentException(
                    "Nonnegative workload required");
        }
        if (q == 0) return Recommendation.NO_QUERIES;
        if (textChanges || !canKeepIndex) {
            return Recommendation.KMP_PER_QUERY;
        }
        if (allPatternsKnownTogether && q >= 4 && n > 0) {
            // Candidate: Aho-Corasick is NOT implemented below.
            return Recommendation.AHO_CORASICK_BATCH;
        }

        double lg = Math.log(Math.max(2.0, (double) n))
                / Math.log(2.0);
        double saBuild = n * lg * lg;
        double scanCost = q * (n + averagePatternLength);
        double indexedCost = saBuild
                + q * averagePatternLength * lg;

        return indexedCost < scanCost
                ? Recommendation.SUFFIX_ARRAY
                : Recommendation.KMP_PER_QUERY;
    }

    static int[] points(String text) {
        return Objects.requireNonNull(
                text, "text").codePoints().toArray();
    }

    static int[] listToArray(List<Integer> a) {
        int[] out = new int[a.size()];
        for (int i = 0; i < out.length; i++) {
            out[i] = a.get(i);
        }
        return out;
    }

    static int[] boundaries(int n) {
        int[] result = new int[n + 1];
        for (int i = 0; i <= n; i++) result[i] = i;
        return result;
    }

    // O(n+m), khong xay chi muc lau dai tren text.
    // Xuat moi vi tri, ke ca khop chong lan.
    static int[] kmp(int[] text, int[] p) {
        int n = text.length, m = p.length;
        if (m == 0) return boundaries(n);

        int[] pi = new int[m];
        for (int i = 1, j = 0; i < m; i++) {
            while (j > 0 && p[i] != p[j]) {
                j = pi[j - 1];
            }
            if (p[i] == p[j]) j++;
            pi[i] = j;
        }

        List<Integer> hits = new ArrayList<>();
        int j = 0;
        for (int i = 0; i < n; i++) {
            while (j > 0 && text[i] != p[j]) {
                j = pi[j - 1];
            }
            if (text[i] == p[j]) j++;
            if (j == m) {
                hits.add(i - m + 1);
                // Cho phep lan khop tiep theo CHONG LAN.
                j = pi[j - 1];
            }
        }
        return listToArray(hits);
    }

    static int[] naiveMatches(int[] text, int[] p) {
        List<Integer> hits = new ArrayList<>();
        for (int start = 0;
                start + p.length <= text.length;
                start++) {
            boolean same = true;
            for (int j = 0; j < p.length; j++) {
                if (text[start + j] != p[j]) {
                    same = false;
                    break;
                }
            }
            if (same) hits.add(start);
        }
        return listToArray(hits);
    }

    // So sanh suffix truc tiep, CHI DUNG LAM ORACLE.
    static int compareSuffix(int[] text, int a, int b) {
        while (a < text.length && b < text.length) {
            if (text[a] != text[b]) {
                return Integer.compare(text[a], text[b]);
            }
            a++;
            b++;
        }
        if (a == text.length && b == text.length) return 0;
        return a == text.length ? -1 : 1;
    }

    static int[] naiveSuffixArray(int[] text) {
        Integer[] order = new Integer[text.length];
        for (int i = 0; i < text.length; i++) {
            order[i] = i;
        }
        Arrays.sort(order,
                (a, b) -> compareSuffix(text, a, b));
        int[] sa = new int[text.length];
        for (int i = 0; i < sa.length; i++) {
            sa[i] = order[i];
        }
        return sa;
    }

    // Xay SA prefix doubling: O(n log^2 n) thoi gian.
    static int[] buildSuffixArray(int[] text) {
        int n = text.length;
        if (n == 0) return new int[0];

        Integer[] order = new Integer[n];
        int[] rank = Arrays.copyOf(text, n);
        for (int i = 0; i < n; i++) order[i] = i;

        for (int len = 1; len < n;
                len = len >= n / 2 ? n : len * 2) {
            final int step = len;
            final int[] oldRank = rank;

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
            if (rank[order[n - 1]] == n - 1) break;
        }

        int[] result = new int[n];
        for (int i = 0; i < n; i++) {
            result[i] = order[i];
        }
        return result;
    }

    static final class TextIndex {
        final String original;
        final int[] text;
        final int[] sa;

        TextIndex(String original) {
            this.original = Objects.requireNonNull(
                    original, "original");
            this.text = points(original);
            this.sa = buildSuffixArray(text);
        }

        int[] kmpFind(String pattern) {
            return kmp(text, points(pattern));
        }

        // 0 neu pattern la tien to cua suffix.
        int compareSuffixPrefix(int start, int[] p) {
            int available = text.length - start;
            for (int j = 0; j < p.length; j++) {
                if (j >= available) return -1;
                int diff = Integer.compare(
                        text[start + j], p[j]);
                if (diff != 0) return diff;
            }
            return 0;
        }

        // 2 binary search, sau do sort ket qua theo vi tri.
        int[] suffixArrayFind(String pattern) {
            int[] p = points(pattern);
            int n = sa.length;

            if (p.length == 0) return boundaries(n);
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
            Arrays.sort(hits);
            return hits;
        }

        // Doi 0-based code-point offset sang Java UTF-16.
        int[] toUtf16Offsets(int[] positions) {
            int[] offsets = new int[text.length + 1];
            for (int i = 0; i < text.length; i++) {
                offsets[i + 1] = offsets[i]
                        + Character.charCount(text[i]);
            }
            int[] out = new int[positions.length];
            for (int i = 0; i < positions.length; i++) {
                int p = positions[i];
                if (p < 0 || p > text.length) {
                    throw new IllegalArgumentException(
                            "Bad code point position");
                }
                out[i] = offsets[p];
            }
            return out;
        }
    }

    static List<String> allWords(
            String[] alphabet, int maxLength) {
        List<String> all = new ArrayList<>();
        List<String> layer = new ArrayList<>();
        all.add("");
        layer.add("");

        for (int length = 1;
                length <= maxLength;
                length++) {
            List<String> next = new ArrayList<>();
            for (String prefix : layer) {
                for (String symbol : alphabet) {
                    next.add(prefix + symbol);
                }
            }
            all.addAll(next);
            layer = next;
        }
        return all;
    }

    static final class Counter {
        int texts, queries;
    }
    record Stats(int texts, int queries) {}

    static void checkText(
            String text, List<String> patterns, Counter c) {
        TextIndex idx = new TextIndex(text);
        int[] expectedSA = naiveSuffixArray(idx.text);
        if (!Arrays.equals(idx.sa, expectedSA)) {
            throw new AssertionError(
                    "Bad suffix order: " + text);
        }
        c.texts++;

        for (String pattern : patterns) {
            int[] p = points(pattern);
            int[] truth = naiveMatches(idx.text, p);
            int[] byKmp = idx.kmpFind(pattern);
            int[] bySa = idx.suffixArrayFind(pattern);

            if (!Arrays.equals(truth, byKmp)
                    || !Arrays.equals(truth, bySa)) {
                throw new AssertionError(
                        "Mismatch text=" + text
                        + " pattern=" + pattern);
            }

            int[] utf16 = idx.toUtf16Offsets(bySa);
            for (int offset : utf16) {
                if (!text.startsWith(pattern, offset)) {
                    throw new AssertionError(
                            "Bad UTF-16 offset");
                }
            }
            c.queries++;
        }
    }

    static int randomState = 3902026;

    // Deterministic unsigned 32-bit LCG.
    static int randomInt(int bound) {
        randomState = randomState * 1664525
                + 1013904223;
        return (int) (Integer.toUnsignedLong(randomState)
                % bound);
    }

    static Stats verify() {
        Counter c = new Counter();

        // 255 text (do dai 0..7) va 63 mau (0..5).
        List<String> texts2 =
                allWords(new String[]{"a", "b"}, 7);
        List<String> pats2 =
                allWords(new String[]{"a", "b"}, 5);
        for (String text : texts2) {
            checkText(text, pats2, c);
        }

        // 364 text (0..5) va 121 mau (0..4).
        List<String> texts3 =
                allWords(new String[]{"a", "b", "c"}, 5);
        List<String> pats3 =
                allWords(new String[]{"a", "b", "c"}, 4);
        for (String text : texts3) {
            checkText(text, pats3, c);
        }

        // 1.200 cap Unicode xac dinh, code-point dai 0..19/0..7.
        String[] symbols = {
            "a", "b", "🙂", "🍎", "ắ", "é", "#", "𝄞"
        };
        for (int test = 0; test < 1200; test++) {
            int n = randomInt(20);
            int m = randomInt(8);
            StringBuilder t = new StringBuilder();
            StringBuilder p = new StringBuilder();
            for (int i = 0; i < n; i++) {
                t.append(symbols[randomInt(symbols.length)]);
            }
            for (int i = 0; i < m; i++) {
                p.append(symbols[randomInt(symbols.length)]);
            }
            checkText(t.toString(),
                    List.of(p.toString()), c);
        }

        // 255 + 364 + 1200 = 1819 van ban.
        // 255*63 + 364*121 + 1200 = 61309 truy van.
        if (c.texts != 1819 || c.queries != 61309) {
            throw new AssertionError(
                    "Unexpected verification counts");
        }
        return new Stats(c.texts, c.queries);
    }

    public static void main(String[] args) {
        TextIndex banana = new TextIndex("banana");
        System.out.println("banana.sa="
                + Arrays.toString(banana.sa));
        System.out.println("banana.KMP(ana)="
                + Arrays.toString(
                    banana.kmpFind("ana")));
        System.out.println("banana.SA(ana)="
                + Arrays.toString(
                    banana.suffixArrayFind("ana")));

        TextIndex idx =
                new TextIndex("banana🍎banana");
        System.out.println(
                "text.codePoints=" + idx.text.length);
        System.out.println("text.utf16Length="
                + idx.original.length());

        int[] ana = idx.kmpFind("ana");
        System.out.println("KMP(ana)="
                + Arrays.toString(ana));
        System.out.println("SA(ana)="
                + Arrays.toString(
                    idx.suffixArrayFind("ana")));
        System.out.println("UTF16(ana)="
                + Arrays.toString(
                    idx.toUtf16Offsets(ana)));
        System.out.println("KMP(ban)="
                + Arrays.toString(idx.kmpFind("ban")));
        System.out.println("SA(ban)="
                + Arrays.toString(
                    idx.suffixArrayFind("ban")));
        System.out.println("KMP(empty)="
                + Arrays.toString(idx.kmpFind("")));
        System.out.println("SA(empty)="
                + Arrays.toString(
                    idx.suffixArrayFind("")));
        System.out.println("SA(missing)="
                + Arrays.toString(
                    idx.suffixArrayFind("zz")));

        System.out.println("recommend.few="
                + recommend(1_000_000, 2, 8,
                            false, false, true));
        System.out.println("recommend.many="
                + recommend(1_000_000, 5000, 8,
                            false, false, true));
        System.out.println("recommend.batch="
                + recommend(1_000_000, 5000, 8,
                            false, true, true));
        System.out.println("recommend.mutable="
                + recommend(1_000_000, 5000, 8,
                            true, false, true));
        System.out.println("recommend.lowMemory="
                + recommend(1_000_000, 5000, 8,
                            false, false, false));
        System.out.println("recommend.zero="
                + recommend(1_000_000, 0, 8,
                            false, false, true));

        Stats s = verify();
        System.out.println("verifiedTexts=" + s.texts());
        System.out.println("verifiedQueries=" + s.queries());
    }
}
~~~

Lưu mã vào tệp **ChoosingTextIndexDemo.java** và chạy bằng JDK 17 trở lên:

~~~bash
javac ChoosingTextIndexDemo.java
java ChoosingTextIndexDemo
~~~

**Đầu ra dự kiến chính xác:**

~~~text
banana.sa=[5, 3, 1, 0, 4, 2]
banana.KMP(ana)=[1, 3]
banana.SA(ana)=[1, 3]
text.codePoints=13
text.utf16Length=14
KMP(ana)=[1, 3, 8, 10]
SA(ana)=[1, 3, 8, 10]
UTF16(ana)=[1, 3, 9, 11]
KMP(ban)=[0, 7]
SA(ban)=[0, 7]
KMP(empty)=[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]
SA(empty)=[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]
SA(missing)=[]
recommend.few=KMP_PER_QUERY
recommend.many=SUFFIX_ARRAY
recommend.batch=AHO_CORASICK_BATCH
recommend.mutable=KMP_PER_QUERY
recommend.lowMemory=KMP_PER_QUERY
recommend.zero=NO_QUERIES
verifiedTexts=1819
verifiedQueries=61309
~~~

### Giải thích output

- `banana.sa=[5,3,1,0,4,2]` là thứ tự vị trí bắt đầu các hậu tố của "banana" theo từ điển.
- Với mẫu "ana" trong "banana", KMP và suffix array đều tìm vị trí `[1,3]`. Trong "banana🍎banana", hai thuật toán cùng trả `[1,3,8,10]` theo **code point**.
- Chuỗi "banana🍎banana" có **13 code point nhưng 14 UTF-16 char**, vì 🍎 là một code point ngoài BMP, chiếm hai char. Vị trí "ana" theo UTF-16 là `[1,3,9,11]`.
- Mẫu "ban" nằm tại `[0,7]` theo code point; mẫu rỗng trả mọi ranh giới `0..13`; mẫu "zz" không có lần xuất hiện.
- `recommend.few` khuyến nghị KMP vì quá ít truy vấn để bù chi phí xây chỉ mục; `recommend.many` gợi ý suffix array với q lớn, text tĩnh và đủ RAM.
- `recommend.batch` gợi ý **Aho–Corasick** khi mẫu đã biết trước. **Không có code Aho–Corasick trong chương trình**; đây chỉ là nhánh khuyến nghị theo workload.
- `recommend.mutable` ưu tiên KMP khi T thay đổi; `recommend.lowMemory` chọn cách không giữ chỉ mục; `recommend.zero` không xây gì khi không có truy vấn.
- `verifiedTexts` và `verifiedQueries` là số kiểm thử thực hiện, **không phải benchmark thời gian**.

### Hai điểm kỹ thuật đáng chú ý trong Java

**1. KMP với khớp chồng lấn.** Sau khi đã khớp hết m ký tự, chương trình đặt `j=pi[j−1]`, không đặt về 0. Nhờ đó với T="aaaa", P="aa" nó trả `[0,1,2]`.

**2. Suffix array với snapshot rank cũ.** Trong mỗi vòng doubling, comparator giữ tham chiếu `oldRank` cố định; chỉ sau khi sort và nén rank mới thay rank. Các hạng ngoài mảng là −1, đảm bảo hậu tố ngắn hơn đứng trước khi tiền tố bằng nhau.

Một chi tiết khác: `suffixArrayFind` dùng comparator trả **0 khi P là tiền tố của suffix**, không đòi cả suffix bằng P. Đó là điều kiện đúng để các suffix chứa mẫu tạo một đoạn liên tiếp, sau đó tìm hai biên bằng binary search.

## 12. Kiểm thử độc lập trên 61.309 truy vấn

Để phát hiện lỗi so sánh, ranh giới, chồng lấn và Unicode, bài dùng **oracle độc lập**:
- `naiveSuffixArray` sort hậu tố bằng cách so trực tiếp từng code point tới khi khác nhau hoặc có hậu tố kết thúc.
- `naiveMatches` thử mọi vị trí bắt đầu và so từng ký tự của P với T.
- `kmp` tính prefix function và quét T mà không dùng suffix array.
- `suffixArrayFind` dùng hai binary search trên SA do prefix doubling tạo.

Với từng văn bản, mã kiểm tra SA khớp **hoàn toàn** với naïve sort. Với từng mẫu, **toàn bộ danh sách vị trí** của KMP và SA phải **bằng đúng** oracle — bao gồm vị trí, thứ tự tăng dần và khớp chồng lấn.

Các nhóm kiểm thử:

| Nhóm dữ liệu | Văn bản | Mẫu trên mỗi văn bản | Số truy vấn |
| --- | ---: | ---: | ---: |
| Alphabet {a,b}, T dài 0..7, P dài 0..5 | 255 | 63 | 16.065 |
| Alphabet {a,b,c}, T dài 0..5, P dài 0..4 | 364 | 121 | 44.044 |
| Unicode giả ngẫu nhiên xác định, n=0..19, m=0..7 | 1.200 | 1 | 1.200 |
| **Tổng** | **1.819** | | **61.309** |

Nhóm Unicode có các ký hiệu `a, b, 🙂, 🍎, ắ, é, #, 𝄞`. Bộ sinh số giả ngẫu nhiên với seed cố định giúp tái tạo đúng đầu vào. Từng offset theo code point sau khi tìm được đổi sang **offset UTF-16**, đối chiếu với `String.startsWith(pattern,offset)` để xác minh các vị trí dùng được với Java String API.

Trong những truy vấn exhaustive, có cả:
- Chuỗi và mẫu rỗng;
- Mẫu dài hơn văn bản;
- Văn bản lặp cùng ký tự;
- Khớp nhiều lần, kể cả chồng lấn;
- Mẫu không xuất hiện;
- Unicode ngoài BMP và dấu #;
- Hậu tố ngắn là tiền tố của hậu tố dài.

**Kiểm thử hữu hạn không thay chứng minh thuật toán.** Nó giúp bắt lỗi cài đặt, còn bảo đảm trên input bất kỳ đến từ tính đúng của prefix function KMP, bất biến prefix doubling và tính đơn điệu của đoạn các suffix cùng tiền tố.

## 13. Tính đúng: vì sao hai cách tìm vị trí tương đương

### A. KMP quét đúng và không bỏ khớp chồng lấn

`pi[j−1]` là độ dài tiền tố thích hợp dài nhất của mẫu đồng thời là hậu tố của phần vừa khớp. Khi có mismatch, KMP chuyển j tới border thích hợp thay vì thử lại một đoạn đã chắc chắn trùng. Nhờ thế nó không bỏ qua vị trí nào có thể khớp, đồng thời mỗi bước chỉ tiến/giảm j một số lần amortized O(n+m).

Khi đủ m ký tự, vị trí bắt đầu là `i−m+1`. Chuyển j về `pi[m−1]` giữ phần khớp chung có thể dùng tiếp, do đó không bỏ những lần xuất hiện chồng lấn.

### B. Suffix array giữ đúng thứ tự từ điển

Ban đầu rank phân biệt các tiền tố dài 1. Giả sử rank đúng thứ tự của các khối dài tối đa len. Tiền tố dài 2len gồm hai khối liên tiếp, nên so cặp `(rank[i],rank[i+len])` là so đúng thứ tự từ điển của tiền tố dài 2len; phần ngoài chuỗi mang hạng −1 để hậu tố ngắn hơn đứng trước. Sort cặp và gán rank mới giữ bất biến. Khi mọi hậu tố khác hạng (hoặc len đã bao phủ chuỗi), SA đúng.

### C. Các hậu tố chứa P nằm liên tiếp

Trong thứ tự từ điển, tất cả chuỗi có tiền tố P nằm trong cùng một khoảng: nếu A và B đều bắt đầu bằng P thì bất kỳ chuỗi X nằm giữa A và B theo thứ tự từ điển cũng bắt đầu bằng P. Do đó sau khi sort suffix, các hậu tố có tiền tố P tạo **một đoạn liên tiếp**.

Comparator trong chương trình trả:
- âm nếu suffix nhỏ hơn P ở ký tự khác đầu tiên, hoặc suffix kết thúc trước khi P hết;
- 0 khi P là tiền tố của suffix;
- dương nếu suffix lớn hơn P ở ký tự khác đầu tiên.

Những giá trị này tạo ba vùng theo thứ tự **âm, bằng 0, dương**, nên lower/upper bound tìm đúng đoạn bằng 0. Các SA positions trong đoạn là **mọi vị trí xuất hiện** của P, không thiếu/không thừa.

### D. Mẫu rỗng

Theo quy ước đề bài, mẫu rỗng khớp tại mọi ranh giới của n code point, gồm `0..n`. Mã KMP và SA đều xử lý riêng bằng `boundaries(n)`, nên hoàn toàn nhất quán; không phải suy ra từ SA chỉ gồm n hậu tố không rỗng.

## 14. Những lỗi chọn chỉ mục thường gặp

| Lỗi tư duy/triển khai | Hậu quả | Cách sửa |
| --- | --- | --- |
| Thấy n lớn nên xây SA cho q=1 | Build có thể đắt hơn quét | Xem cả n, q, m, k |
| Có q rất lớn nhưng T sửa liên tục | Mỗi phiên bản có thể phải rebuild | Tính q **trên từng phiên bản** |
| Đã biết toàn bộ mẫu nhưng vẫn quét T q lần | Lãng phí batch matching | Xem Aho–Corasick |
| Dùng SAM để hứa trả mọi vị trí O(m) | Bỏ qua công tìm location | Phân biệt membership/count/locate |
| So chỉ thời gian truy vấn SA, bỏ thời gian build | Kết luận sai tổng chi phí | Đo tổng build+queries |
| Bỏ qua bộ nhớ chỉ mục | OOM hoặc GC nặng | Ước lượng byte/heap |
| Bỏ qua số kết quả k | Benchmark không so công bằng | Tính/đo output cost |
| Gọi mọi thuật toán SA là O(n log n) | Sai với bản comparator doubling | Dùng O(n log²n) cho mã này |
| Dùng chỉ mục token như substring index | Không tìm được mẫu nằm giữa một token | Chọn abstraction đúng |
| Tin rolling hash không có collision | Có thể báo khớp giả | Xác minh hoặc chấp nhận xác suất rõ ràng |
| KMP đặt j=0 sau một lần khớp | Bỏ lần khớp chồng lấn | Đặt j=pi[m−1] |
| SA comparator so toàn bộ suffix ở mỗi vòng doubling | Trở về chi phí so đắt | So hai rank số nguyên |
| SA binary search so suffix == pattern đầy đủ | Không tìm các suffix có P làm tiền tố | Comparator dừng khi hết P |
| Dùng rank ngoài biên bằng 0 trùng hạng hợp lệ | Xếp sai hậu tố ngắn | Dùng −1 |
| Gộp code point với UTF-16 offset | Sai vị trí khi có emoji | Chuyển chỉ số rõ ràng |
| Không làm rõ mẫu rỗng | Hai triển khai trả kết quả khác nhau | Chốt quy ước n+1 ranh giới |
| Tự gán ngưỡng cố định q=100 cho mọi bài | Không phản ánh runtime/cấu trúc/dữ liệu | Dùng mô hình + benchmark |
| Chỉ đo latency sau warm-up, bỏ latency đầu | Chỉ mục trả chậm lần đầu | Đo cả build / cold start |
| Bỏ qua normalization và case folding | Tìm thiếu hoặc sai theo yêu cầu | Chuẩn hóa hai phía nhất quán |

### Không tự đồng nhất các loại chỉ mục

“Chỉ mục chuỗi” có thể chỉ những cấu trúc rất khác nhau:
- Mảng hậu tố cho văn bản tĩnh;
- Automaton cho tập chuỗi con;
- Trie/failure links cho nhiều mẫu biết trước;
- Posting lists cho token;
- BWT/rank cho chỉ mục nén;
- Hash k-gram cho đoạn cố định;
- Chỉ mục động chuyên biệt khi cần cập nhật.

Chọn đúng **đối tượng được lập chỉ mục** và **hợp đồng truy vấn** quan trọng hơn việc thuộc tên cấu trúc.

## 15. Bài tập tự luyện kèm đáp án

**Bài 1 — q nhỏ.** T dài 10⁶ ký tự, chỉ có một mẫu dài 15. Nên bắt đầu với KMP hay xây suffix array comparator?

*Đáp án:* KMP O(n+m) thường là lựa chọn cơ sở. Xây SA O(n log²n) để dùng một lần khó hoàn vốn, trừ khi index còn phục vụ nhiều tác vụ khác.

**Bài 2 — nhiều truy vấn độc lập.** T không đổi nhiều ngày, 50.000 mẫu được hỏi từng lúc, cần vị trí. Phương án nào đáng cân nhắc?

*Đáp án:* Suffix array (hoặc cấu trúc văn bản khác), vì chi phí build được chia cho nhiều truy vấn. Phải xét bộ nhớ và tổng số vị trí đầu ra.

**Bài 3 — nhiều mẫu biết trước.** Có 8.000 từ khóa và cần quét một log dài đúng một lượt. Nên cân nhắc gì?

*Đáp án:* Aho–Corasick xây từ tập mẫu, quét T một lượt; không bắt buộc xây suffix array trên T.

**Bài 4 — streaming.** Văn bản đến liên tục từng ký tự, mẫu P cố định, cần báo vị trí ngay khi khớp. Thuật toán thuận tiện?

*Đáp án:* KMP có thể duy trì trạng thái j và xử lý theo stream O(1) amortized cho mỗi ký tự, sau O(m) tiền xử lý.

**Bài 5 — chỉ hỏi tồn tại.** Một văn bản tĩnh và hàng triệu truy vấn hỏi P có phải substring không, không cần vị trí. Lựa chọn khác SA?

*Đáp án:* Suffix automaton có thể trả lời membership bằng đi theo các chuyển cạnh của P trong O(m) tùy cấu trúc chuyển, sau khi build.

**Bài 6 — dữ liệu cập nhật.** T thay đổi sau mỗi 2 truy vấn; tại sao không thể chỉ lấy q tổng cả tháng để tính hòa vốn SA?

*Đáp án:* Chỉ mục cũ thường không còn hợp lệ cho T mới. Phải chia q theo từng phiên bản và cộng chi phí rebuild.

**Bài 7 — ngưỡng hòa vốn.** Build B=1000 đơn vị, quét S=100 đơn vị/truy vấn, index R=10. Từ bao nhiêu truy vấn index có lợi?

*Đáp án:* `q>1000/(100−10)=11,11…`; với q nguyên, bắt đầu từ **12** truy vấn.

**Bài 8 — không hòa vốn.** Nếu R≥S trong cùng mô hình và B>0, có khi nào chỉ mục giúp giảm tổng chi phí không?

*Đáp án:* Không theo mô hình đơn giản B+qR so với qS; cần thay đổi phương án, dữ liệu hoặc yêu cầu.

**Bài 9 — output size.** T là một triệu chữ a, P="a". Tại sao không thể trả tất cả vị trí trong O(log n) tổng thời gian?

*Đáp án:* Có k≈n vị trí. Riêng việc xuất k kết quả đã cần Ω(k).

**Bài 10 — thứ tự kết quả.** SA tìm được đoạn chứa vị trí [3,1]. API yêu cầu vị trí tăng dần. Làm gì?

*Đáp án:* Sort các start positions thành [1,3], chịu thêm O(k log k).

**Bài 11 — suffix automaton.** Build xong SAM và kiểm tra P tồn tại O(m). Có được nói luôn trả mọi vị trí O(m) không?

*Đáp án:* Không. Muốn locate phải có cấu trúc/phép truy xuất và tính thêm chi phí k.

**Bài 12 — rolling hash.** Hai đoạn có hash bằng nhau có chắc chắn bằng nhau không?

*Đáp án:* Không, có thể va chạm; muốn exact thì xác minh nội dung hoặc dùng thuật toán bảo đảm.

**Bài 13 — token vs substring.** Một inverted index theo từ có trả trực tiếp vị trí "ana" trong "banana" không?

*Đáp án:* Không mặc định; chỉ mục token khác với substring index ký tự.

**Bài 14 — Z vs KMP.** Cả hai tìm một mẫu dài m trong T dài n trong bao lâu?

*Đáp án:* O(n+m). KMP có thể dùng O(m) bộ nhớ phụ và quét luồng; Z với chuỗi ghép thường giữ O(n+m) bộ nhớ.

**Bài 15 — so cặp rank.** Prefix doubling đang ở len=4, hạng thứ hai cho hậu tố bắt đầu ở i lấy từ đâu?

*Đáp án:* `rank[i+4]` nếu i+4<n; nếu vượt cuối chuỗi dùng −1.

**Bài 16 — chọn kết quả.** Chỉ cần **đếm** số vị trí khớp. SA có cần sort danh sách k vị trí không?

*Đáp án:* Không. Hai biên SA cho số lần khớp bằng hi−lo.

**Bài 17 — Unicode.** T="banana🍎banana", P="ana". Vị trí theo code point là gì, theo UTF-16?

*Đáp án:* Code point `[1,3,8,10]`, UTF-16 `[1,3,9,11]`.

**Bài 18 — mẫu rỗng.** Với T có n=4 code point, chương trình trả vị trí nào cho P=""?

*Đáp án:* `[0,1,2,3,4]`, tức n+1 ranh giới.

**Bài 19 — throughput và latency.** Vì sao SA có thể tốt cho 10.000 truy vấn nhưng tệ cho truy vấn đầu?

*Đáp án:* Build trả chi phí lớn trước câu hỏi đầu, nhưng tổng chi phí build được amortize qua nhiều truy vấn; đo riêng cold-start latency và tổng throughput.

**Bài 20 — memory.** Một suffix array O(n) có mặc nhiên nhẹ hơn một thuật toán O(n log n) khác không?

*Đáp án:* Không. Big-O không phản ánh hằng số byte, boxing, object pointers, sparse/dense transitions, GC và áp lực heap.

**Bài 21 — text động.** Văn bản chỉ nối thêm ở cuối, cần membership nhiều chuỗi con. Có cấu trúc nào có thể phát triển cùng văn bản?

*Đáp án:* Suffix automaton có thể cập nhật theo kiểu append trong mô hình xây SAM chuẩn; nhưng nếu cần chèn/xóa giữa, không tự giả định vẫn rẻ.

**Bài 22 — chỉ mục nén.** Với văn bản rất lớn chủ yếu đọc, cần tiết kiệm RAM và đếm mẫu, nên tìm hiểu chỉ mục nào?

*Đáp án:* FM-index/BWT với rank structure; nhớ kiểm tra chi phí locate nếu cần vị trí.

## 16. Checklist cuối cùng

1. **Viết lại hợp đồng truy vấn:** exact substring, token, membership, count, locate hay fuzzy.
2. **Đo đúng n, q, m_i, k_i**, và q theo **mỗi phiên bản văn bản**.
3. **Chốt pattern availability:** các mẫu biết trước trong một batch hay đến dần.
4. **Chốt tính động:** tĩnh, append-only, cập nhật giữa, số lần rebuild.
5. **Ước lượng build + queries + output**, không chỉ tra cứu sau khi có chỉ mục.
6. **Tính ngưỡng hòa vốn** và kiểm tra chỉ mục có lợi theo q thực tế.
7. **Ước lượng byte RAM** theo cấu trúc cụ thể, không chỉ Big-O.
8. **Phân biệt** KMP/Z không index text, Aho index mẫu, SA/SAM index văn bản.
9. **Không mặc định** SAM trả vị trí ngay, rolling hash không collision, token index tìm substring.
10. **Bảo toàn tính đúng**: thử mẫu chồng lấn, rỗng, mẫu dài hơn T, ký tự Unicode, và vị trí theo code point/UTF-16.
11. **Benchmark cùng dữ liệu, cùng đầu ra**, bao gồm build, cold start, warm queries, peak memory và GC.
12. **Dùng oracle nhỏ** để so toàn bộ danh sách vị trí khi thay cấu trúc.

## Ghi nhớ

- **Ít truy vấn / văn bản thay đổi:** KMP hoặc Z thường đơn giản, tuyến tính theo n+m, không cần chỉ mục text lớn.
- **Nhiều mẫu đã biết trước cần quét đồng thời:** Aho–Corasick xây trên tập mẫu, có thể quét T một lượt.
- **Nhiều truy vấn độc lập trên T tĩnh:** suffix array là lựa chọn chuẩn nếu đủ bộ nhớ; suffix automaton nổi bật khi chủ yếu hỏi sự tồn tại chuỗi con.
- **Text rất lớn và RAM hạn chế:** cân nhắc chỉ mục nén như FM-index; **token search** nên xét inverted index thay vì chỉ mục substring.
- **Thời gian thực tế** là tổng **tiền xử lý + số truy vấn × chi phí trả lời + chi phí xuất kết quả + chi phí cập nhật**.
- **Điểm hòa vốn** thay đổi theo implementation/data; heuristic chỉ là khởi đầu, benchmark mới giúp chốt lựa chọn.
- Chương trình Java 17 dùng KMP và suffix array so sánh chính xác cùng mẫu, đồng thời minh họa một heuristic workload. Bộ đối chiếu độc lập **61.309 truy vấn trên 1.819 văn bản** kiểm tra equality kết quả, nhưng **không đo tốc độ** hay chứng minh heuristic luôn nhanh nhất.
