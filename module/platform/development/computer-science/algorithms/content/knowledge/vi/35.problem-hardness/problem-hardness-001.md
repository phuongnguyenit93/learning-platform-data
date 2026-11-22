# Độ khó của bài toán và chi phí của một thuật toán cụ thể

Khi nghe một nhận xét như **“Bài toán này có độ phức tạp O(n²)”**, hãy hỏi ngay: **đang nói về bản thân bài toán, hay chỉ một thuật toán đang dùng để giải nó?**

Hai khái niệm liên quan nhưng không đồng nhất:

- **Chi phí của một thuật toán cụ thể** là số bước tính toán, lượng bộ nhớ, số phép truy cập, số lần hỏi oracle hoặc tài nguyên khác mà **một quy trình đã được định nghĩa** tiêu thụ trên đầu vào kích thước n. Ví dụ, một thuật toán vét cạn tìm hai phần tử có tổng bằng mục tiêu dùng O(n²) phép thử cặp trong trường hợp xấu.
- **Độ khó tính toán của một bài toán** xem xét tài nguyên cần thiết để giải **mọi đầu vào hợp lệ của bài toán**, cho phép lựa chọn **bất kỳ thuật toán hợp lệ nào** trong một mô hình tính toán xác định. Muốn chứng minh bài toán thật sự cần nhiều tài nguyên, thường phải có một **cận dưới** hoặc kết quả về lớp độ phức tạp, không chỉ một cài đặt chậm.

Một bài toán có lời giải O(n²) **không có nghĩa** mọi thuật toán giải bài ấy phải tốn Ω(n²). Nếu tìm được thuật toán O(n log n) hoặc O(n), ta đã cải thiện chi phí của lời giải, còn **bài toán được giải vẫn là cùng một bài toán**.

Ngược lại, tìm được một thuật toán rất chậm cho một bài toán dễ không khiến bài toán đó trở thành NP-hard. Ví dụ, sắp xếp n số bằng cách thử mọi hoán vị có thể tốn thời gian giai thừa, nhưng ta vẫn có **merge sort O(n log n)**.

Bài thuộc chủ đề **Độ khó bài toán**, trình bày chặt chẽ sự khác biệt giữa:

- Đặc tả bài toán, một thể hiện (instance), một thuật toán và một lần chạy.
- Cận trên/cận dưới, Big O/Ω/Θ và tính tối ưu.
- Chi phí theo thời gian, bộ nhớ và mô hình tính toán.
- Phân tích trường hợp xấu, trung bình, kỳ vọng ngẫu nhiên, tốt nhất và khấu hao.
- Quy mô n, kích thước input theo **bit**, mã hóa số và thuật toán giả đa thức.
- Lớp **P, NP, NP-hard, NP-complete**, phép quy giảm và giới hạn các kết luận có thể suy ra.
- Các ví dụ cùng bài toán có nhiều thuật toán với chi phí khác nhau.
- Chương trình **Java 17+ độc lập** so sánh ba thuật toán cho bài toán Two Sum, xử lý các ca biên số nguyên, kiểm thử độc lập và tiêu chí chọn thuật toán thực tế.

**Nguyên tắc đọc bài:** không gọi một chi phí O(f(n)) là “độ khó cố hữu của bài toán” chỉ vì đó là thuật toán đầu tiên nghĩ ra.

## 1. Bốn đối tượng cần phân biệt

### Bài toán (problem)

Bài toán là một **quy tắc ánh xạ từ tập đầu vào hợp lệ sang yêu cầu đầu ra**. Ví dụ:

**TWO-SUM-EXISTS**: cho một mảng n số nguyên và mục tiêu T, hỏi có tồn tại **hai chỉ số khác nhau** i<j sao cho a[i]+a[j]=T hay không.

Đầu ra chỉ là **true/false**.

### Thể hiện (instance)

Một thể hiện là **một dữ liệu cụ thể** của bài toán:

~~~text
array = [2, 7, 11, 15]
target = 9
answer = true
~~~

Một thể hiện khác:

~~~text
array = [1, 2, 3]
target = 100
answer = false
~~~

Hai thể hiện có cùng quy tắc bài toán, nhưng có thể dẫn đến số bước khác nhau trong một thuật toán.

### Thuật toán (algorithm)

Thuật toán là một quy trình hữu hạn, được đặc tả đủ rõ để tạo output đúng cho **mọi instance hợp lệ**.

TWO-SUM-EXISTS có nhiều thuật toán, ví dụ:

- Thử mọi cặp i<j.
- Sắp xếp bản sao mảng rồi dùng hai con trỏ.
- Quét một lần, lưu các số đã thấy trong HashSet.

### Lần thực thi (run)

Một run là việc áp dụng **một thuật toán cụ thể** lên **một instance cụ thể**, với một môi trường thực thi cụ thể. Nó có chi phí đo được như số phép so sánh, thời gian chạy, heap usage.

**Không được đồng nhất** thời gian của một run với độ phức tạp tiệm cận của thuật toán, hay với độ khó của cả bài toán.

## 2. Đặc tả bài toán quyết định khác bài toán tìm kiếm và liệt kê

Một chủ đề có thể có nhiều biến thể khác nhau về output:

| Bài toán | Input | Output |
| --- | --- | --- |
| Two Sum — quyết định | Mảng và T | Có/không có hai chỉ số khác nhau |
| Two Sum — tìm một lời giải | Mảng và T | Một cặp chỉ số hợp lệ hoặc không tồn tại |
| Two Sum — đếm | Mảng và T | Số cặp chỉ số i<j thỏa tổng |
| Two Sum — liệt kê | Mảng và T | Toàn bộ các cặp chỉ số |
| Two Sum — gần mục tiêu | Mảng và T | Cặp có tổng gần T nhất theo quy tắc cụ thể |

Các biến thể này **không mặc nhiên có cùng chi phí tối ưu**.

Ví dụ nếu mọi phần tử của mảng n phần tử đều bằng 0 và T=0, số cặp i<j là:

**n(n−1)/2**.

Nếu phải **in toàn bộ cặp**, chỉ riêng output đã có Θ(n²) phần tử. Một chương trình không thể xuất Θ(n²) cặp trong o(n²) thao tác ghi theo mô hình mỗi cặp cần ghi rõ.

Nhưng bài **chỉ quyết định có cặp hay không** có thể trả true rất sớm, và về tổng quát có lời giải tốt hơn việc liệt kê toàn bộ.

### Phân biệt mã định danh và chỉ số

Two Sum trong bài yêu cầu **hai vị trí khác nhau**. Hai phần tử có cùng giá trị vẫn có thể tạo một cặp nếu chúng nằm ở hai vị trí khác nhau.

~~~text
[3, 3], target=6 -> true
[3], target=6    -> false
~~~

Không được dùng một giá trị 3 duy nhất hai lần để tự tạo cặp.

## 3. Chi phí của một thuật toán là một hàm theo input

Cho thuật toán A và instance x. Gọi:

**T_A(x)** là số bước (hoặc một đại lượng thời gian trừu tượng) mà A thực hiện trên x.

Nếu n là kích thước input, thời gian trường hợp xấu được định nghĩa bằng cách lấy tối đa trên các instance cùng kích thước:

**T_A^worst(n)=max T_A(x) trên các x có kích thước n**,

khi tập instance cỡ n hữu hạn hoặc dùng supremum nếu phù hợp.

Tương tự:

**S_A(x)** là bộ nhớ dùng trên instance x, và:

**S_A^worst(n)** là trường hợp xấu theo kích thước n.

### Cần nói rõ “n” là gì

- Với mảng số nguyên 32-bit: n thường là **số phần tử**, kích thước encoding là Θ(n) word.
- Với đồ thị: input size có thể được mô tả bằng **V đỉnh và E cạnh**.
- Với một số nguyên N mã hóa nhị phân: kích thước input là **Θ(log N) bit**, không phải N.
- Với chuỗi: n là số ký tự, nhưng kích thước byte còn tùy encoding.
- Với bài hình học số lớn: thời gian phép nhân tọa độ còn tùy **bit-length** của các tọa độ.

Nếu ghi O(n) nhưng không xác định n đại diện cho gì, phân tích có thể gây hiểu nhầm.

## 4. Big O, Big Omega và Big Theta

Ba ký hiệu tiệm cận có ý nghĩa khác nhau:

- **f(n)=O(g(n))**: một **cận trên** tiệm cận; tồn tại hằng số c,n₀ sao cho f(n)≤c·g(n) với n≥n₀.
- **f(n)=Ω(g(n))**: một **cận dưới** tiệm cận; tồn tại c>0,n₀ sao cho f(n)≥c·g(n) với n≥n₀.
- **f(n)=Θ(g(n))**: đồng thời có cận trên và cận dưới tương ứng.

Ví dụ:

**3n²+7n+10 = Θ(n²)**.

Do đó cũng đúng rằng hàm này là O(n³) và Ω(n), nhưng hai nhãn rộng ấy **không chặt**.

### Big O không tự có nghĩa “trường hợp xấu”

Ký hiệu Big O chỉ nói về quan hệ tiệm cận. Ta có thể viết:

- T_worst(n)=O(n²).
- T_average(n)=O(n).
- E[T_random(n)]=O(n log n).

Quan trọng là nói **hàm chi phí nào** đang được chặn bởi Big O.

### Không nhầm hai loại cận dưới

Một cận dưới trên **chi phí của thuật toán A** không đồng nghĩa cận dưới trên **mọi thuật toán giải bài toán P**. Để chứng minh bài toán thực sự cần Ω(g(n)) trong mô hình M, phải chứng minh mọi thuật toán hợp lệ trong M cần ít nhất mức tài nguyên đó ở một nghĩa được xác định.

## 5. Độ khó bài toán: tối ưu qua mọi thuật toán hợp lệ

Giả sử chọn một mô hình tính toán M và một cách đo chi phí. Một cách nhìn khái niệm về **độ khó thời gian** của bài toán P là xét:

**T*_P(n) = inf trên mọi thuật toán A giải P của T_A^worst(n)**,

với lưu ý đây là một **mô tả khái niệm**, còn lý thuyết độ phức tạp chính thức thường nghiên cứu các **lớp độ phức tạp, cận trên/cận dưới, mô hình máy và thời gian asymptotic** thay vì một biểu thức T* cụ thể có thể tính ngay.

Điều quan trọng:

- Chứng minh **tồn tại một thuật toán O(f(n))** tạo **cận trên** cho độ khó bài toán.
- Chứng minh **mọi thuật toán đều cần Ω(g(n))** tạo **cận dưới** cho bài toán theo mô hình đã chọn.
- Nếu cận trên và dưới khớp tới hằng số, có thể nói một mức độ phức tạp tối ưu **Θ(f(n))** trong mô hình đó.
- Nếu chưa có cận dưới khớp, **không nên khẳng định thuật toán đang có là tối ưu**.

### Một thuật toán chậm không phải chứng cứ bài toán khó

Nếu một người giải tìm kiếm một phần tử trong mảng bằng thuật toán kiểm tra tất cả các hoán vị, đó chỉ là một cách giải không hiệu quả. Không có lý do kết luận tìm kiếm đơn giản là bài toán khó chỉ từ cài đặt này.

Tương tự, một thuật toán O(2^n) cho một bài không chứng minh bài ấy **không thể** giải trong thời gian đa thức.

## 6. Ví dụ trung tâm: ba lời giải cùng bài toán Two Sum

Đặc tả cố định:

**Input:** mảng a gồm các số nguyên 32-bit có dấu, độ dài n, và target T kiểu long.

**Output:** true khi tồn tại i<j sao cho **(long)a[i]+(long)a[j]=T**, ngược lại false.

Ba thuật toán sau cùng trả lời **đúng một câu hỏi**, nhưng chi phí khác nhau.

| Thuật toán | Thời gian | Bộ nhớ phụ | Điều kiện |
| --- | --- | --- | --- |
| Vét cạn mọi cặp | O(n²) trường hợp xấu | O(1) | Không cần cấu trúc dữ liệu |
| Merge sort bản sao + hai con trỏ | O(n log n) trường hợp xấu | O(n) | Giữ bản gốc, dùng bộ nhớ sao chép |
| HashSet các giá trị đã thấy | O(n) **kỳ vọng** | O(n) | Phụ thuộc giả thiết chi phí/độ phân bố hashing |

Không có thuật toán nào đổi ý nghĩa bài toán: cả ba phải dùng **hai chỉ số khác nhau** và xử lý chính xác tổng số nguyên.

### Cần phân biệt độ phức tạp và kết quả trên một input

Với [2,7,11,15] và T=9, vét cạn có thể tìm cặp ngay ở lần thử đầu tiên. Trường hợp tốt nhất nhanh không biến độ phức tạp **trường hợp xấu** của vét cạn thành O(1) cho mọi instance.

## 7. Thuật toán A: thử mọi cặp

Cách đơn giản:

~~~text
for i = 0 .. n-1:
    for j = i+1 .. n-1:
        if a[i]+a[j] == T:
            return true

return false
~~~

### Chứng minh đúng

Nếu thuật toán trả true, nó vừa tìm thấy i<j và tổng bằng T, nên đáp án đúng.

Nếu trả false, thuật toán đã xét **mọi** cặp chỉ số i<j mà không thấy cặp hợp lệ. Do đó không tồn tại lời giải.

### Chi phí

Số cặp khác nhau là:

**n(n−1)/2**.

Nếu không có cặp nào thỏa, thuật toán kiểm tra toàn bộ, nên:

**T_worst(n)=Θ(n²)** với n≥2 theo mô hình mỗi phép so sánh/tổng word có chi phí O(1).

Bộ nhớ phụ O(1) nếu không tính mảng input.

### Khi nào chọn?

- n rất nhỏ.
- Cần code đơn giản và kiểm chứng dễ.
- Thiếu RAM cho cấu trúc dữ liệu bổ sung.
- Dùng làm **oracle vét cạn** kiểm tra những thuật toán tối ưu hơn.

**Không được kết luận Two Sum có độ khó Θ(n²)** chỉ từ lời giải vét cạn.

## 8. Thuật toán B: sắp xếp rồi hai con trỏ

Đầu tiên sao chép mảng và sắp xếp tăng dần:

**b₀≤b₁≤...≤bₙ₋₁**.

Đặt:

**left=0**, **right=n−1**.

Khi left<right:

- Tính **sum=(long)b[left]+b[right]**.
- Nếu sum=T, trả true.
- Nếu sum<T, tăng left.
- Nếu sum>T, giảm right.

Nếu hai con trỏ gặp nhau mà chưa thấy cặp, trả false.

### Vì sao loại con trỏ trái khi sum<T?

Vì mảng đã sắp tăng, với mọi j≤right:

**b[left]+b[j] ≤ b[left]+b[right] < T**.

Vậy phần tử tại left không thể tạo cặp với bất kỳ phần tử còn lại trong đoạn ứng viên. Loại nó là an toàn.

### Vì sao loại con trỏ phải khi sum>T?

Đối xứng, với mọi i≥left:

**b[i]+b[right] ≥ b[left]+b[right] > T**.

Vì vậy phần tử right không thể tham gia cặp hợp lệ trong đoạn hiện tại.

### Chi phí và bộ nhớ

- Merge sort: **O(n log n)** worst-case, O(n) bộ nhớ phụ.
- Hai con trỏ: **O(n)** thời gian, O(1) bộ nhớ phụ ngoài mảng đã sắp.
- Tổng: **O(n log n)** thời gian worst-case và **O(n)** bộ nhớ phụ.

Dùng **merge sort tự cài** trong chương trình Java để cận worst-case O(n log n) là rõ ràng, thay vì tự gán một cận worst-case không được chứng minh cho mọi biến thể QuickSort.

### Giữ nguyên input hay không?

Nếu được phép sửa input, có thể sắp xếp tại chỗ bằng một thuật toán phù hợp và tiết kiệm bộ nhớ sao chép tùy lựa chọn. Trong bài này chương trình **sắp xếp bản sao** để giữ nguyên input, vì đó là một yêu cầu thiết kế có thể ảnh hưởng chi phí.

## 9. Thuật toán C: bảng băm

Quét các phần tử từ trái sang phải, lưu vào HashSet những giá trị đã gặp.

Với phần tử hiện tại x, cần biết trước đó có số:

**need=T−x**

hay không.

~~~text
seen = empty set

for each x in array:
    if (T-x) is in seen:
        return true
    add x to seen

return false
~~~

### Chứng minh đúng

Tại thời điểm xét chỉ số j, tập seen chứa đúng những giá trị ở các chỉ số i<j (có thể bỏ qua bản sao giá trị nhưng vẫn biểu diễn sự tồn tại).

Nếu need nằm trong seen, có một i<j sao cho a[i]=T−a[j], tức a[i]+a[j]=T.

Nếu quét hết mà không tìm thấy, không có cặp i<j; vì mọi cặp có một chỉ số lớn hơn j đều đã được kiểm tra khi đến phần tử ở chỉ số lớn hơn.

### Vì sao phải kiểm tra trước khi thêm x?

Với input:

~~~text
[3], T=6
~~~

nếu thêm 3 rồi kiểm tra need=3, thuật toán có thể dùng **chính một phần tử hai lần** và trả true sai.

Thứ tự đúng là **contains(need) trước, add(x) sau**.

### Chi phí

Nếu các thao tác HashSet có chi phí **O(1) kỳ vọng** theo mô hình và giả thiết hashing được chọn, tổng thời gian kỳ vọng là **O(n)**.

Bộ nhớ phụ chứa tối đa n giá trị khác nhau: **O(n)**.

Không gọi chi phí O(n) này là bảo đảm **worst-case độc lập với hashing**. Xung đột băm, phân bố khóa, cấu trúc bảng và các chi phí cấp phát có thể ảnh hưởng thực tế.

### Vì sao có thể nhanh hơn nhưng tốn RAM?

HashSet cần object/bucket metadata, bộ nhớ phân bổ và tính hash. Vét cạn chỉ cần hai vòng lặp và một vài biến. Khi n nhỏ, constant overhead của HashSet có thể khiến nó chạy chậm hơn dù asymptotic tốt hơn.

## 10. Vì sao ba thuật toán không chứng minh độ khó tối ưu của Two Sum?

Ba thuật toán đưa ra các **cận trên** cho bài toán Two Sum trong các mô hình tương ứng:

- O(n²) bằng vét cạn.
- O(n log n) bằng sắp xếp trộn.
- O(n) kỳ vọng bằng hashing.

Một cận trên tốt hơn **thay thế** cận trên cũ khi cùng điều kiện áp dụng. Nhưng một bảng các thuật toán không tự chứng minh **cận dưới khớp**.

Cần xem **mô hình tính toán**:

- Trên word-RAM với số nguyên 32-bit, có thể còn có các kỹ thuật khai thác tập khóa hữu hạn, radix/counting-based methods.
- Trên mô hình chỉ cho phép so sánh, cấu trúc bài và các lower bound phải được phân tích riêng.
- Nếu số là arbitrary-precision integer, phép trừ và hash phụ thuộc độ dài bit của các số; phép toán không còn mặc nhiên O(1).

Không thể suy ra **Two Sum có độ khó Θ(n)** chỉ từ việc thấy một phiên bản HashSet chạy kỳ vọng O(n) mà không phát biểu thêm các giả thiết tương ứng và cận dưới cần thiết.

### Cận dưới đọc input

Với một bài phải phân biệt nhiều input khác nhau, có thể chứng minh cần đọc một lượng thông tin tối thiểu ở trường hợp xấu trong mô hình xác định. Nhưng một khẳng định Ω(n) phải đi kèm **lập luận adversary/decision-tree hoặc mô hình truy cập**, không phải chỉ vì “mảng có n phần tử” nên mọi thuật toán đều phải chạm mọi ô trong mọi lần chạy.

## 11. Ví dụ cận dưới khớp: sắp xếp bằng so sánh

Bài toán sắp xếp n khóa phân biệt bằng những câu hỏi **so sánh hai khóa** là một ví dụ chuẩn về cận dưới.

Có **n!** hoán vị đầu vào cần phân biệt. Một thuật toán so sánh xác định có thể được mô tả bằng **cây quyết định nhị phân**; để xác định đúng thứ tự ở trường hợp xấu, cây cần đủ lá phân biệt hoán vị.

Vì vậy độ sâu trường hợp xấu ít nhất:

**ceil(log₂(n!))=Ω(n log n)**.

Merge sort đạt cận trên:

**O(n log n)** so sánh ở trường hợp xấu.

Suy ra trong **mô hình comparison sorting**, bài toán có độ phức tạp:

**Θ(n log n)** theo số phép so sánh trường hợp xấu.

### Vì sao Counting Sort không mâu thuẫn?

Counting sort cho n số nguyên trong miền giá trị gồm K giá trị có thể chạy:

**O(n+K)**.

Nó **không chỉ dùng so sánh**, mà khai thác trực tiếp cấu trúc giá trị để lập bảng đếm. Nó cũng phụ thuộc K và bộ nhớ O(n+K) hoặc O(K) cho các biến thể.

Cận dưới Ω(n log n) của **comparison sorting** không áp dụng cho một thuật toán nằm ngoài mô hình so sánh thuần túy.

Đây là ví dụ nổi bật cho thấy **độ khó phải gắn với mô hình tính toán và hợp đồng input**.

## 12. Giới hạn đầu vào làm thay đổi bài toán

Hãy so hai bài:

- **Sorting-A:** sắp xếp n khóa chỉ có thể so sánh, không biết biểu diễn bên trong.
- **Sorting-B:** sắp xếp n số nguyên 0..255.

Sorting-B có thêm cấu trúc miền giá trị; Counting Sort chỉ cần 256 bộ đếm và n phần tử output nếu cần ổn định. Sorting-A không có khả năng truy cập chỉ số bảng theo giá trị như vậy.

Tương tự:

- Đường đi ngắn nhất trên **đồ thị không trọng số** có thể giải bằng BFS.
- Đường đi ngắn nhất với **trọng số không âm** có thể dùng Dijkstra với cấu trúc dữ liệu phù hợp.
- Nếu cho phép cạnh âm nhưng không có chu trình âm gây ảnh hưởng tới đích, cần thuật toán đúng với giả thiết khác như Bellman–Ford.

Đổi ràng buộc input có thể thay đổi **lớp bài toán**, không chỉ thay implementation detail. Không được áp dụng một thuật toán nhanh hơn nhưng chỉ đúng trên dữ liệu con để tuyên bố đã giải **bài tổng quát**.

## 13. Worst-case, average-case, expected và best-case

Cho cùng một thuật toán, có nhiều loại chi phí:

**Best-case:** đầu vào thuận lợi nhất theo n.

**Worst-case:** đầu vào bất lợi nhất theo n.

**Average-case:** trung bình theo **một phân phối xác suất trên các input** đã được quy định. Không thể nói average-case O(n) nếu chưa nêu phân phối hoặc giả thiết.

**Expected runtime của thuật toán randomized:** kỳ vọng theo **nguồn ngẫu nhiên nội tại của thuật toán**, có thể xét với một input cố định.

### Phân biệt expected với average-case

- Randomized QuickSort có phân tích số phép so sánh **kỳ vọng O(n log n)** với cơ chế pivot ngẫu nhiên phù hợp.
- QuickSort xác định có thể O(n²) worst-case nếu pivot chọn tệ với một họ input.
- HashSet thường được phân tích O(1) expected cho thao tác dưới giả thiết hash table; đó không phải một chứng minh rằng mọi run đều dùng O(1) phép xử lý.

Trên một input, hai run của thuật toán randomized có thể tốn thời gian khác nhau. Average-case theo input và expected theo randomness không phải cùng một mệnh đề.

## 14. Độ phức tạp khấu hao (amortized)

**Amortized complexity** xem tổng chi phí của một **chuỗi thao tác** để phân bổ chi phí thỉnh thoảng rất lớn cho nhiều thao tác nhỏ.

Ví dụ dynamic array tăng gấp đôi capacity khi đầy:

- Một lần append có thể phải copy O(n) phần tử.
- Nhưng nếu chiến lược tăng capacity gấp đôi và môi trường đáp ứng hợp đồng thông thường, **n lần append** có tổng O(n) thao tác sao chép/chèn.
- Do đó append có **O(1) khấu hao**.

Điều này không đồng nghĩa:

- Mọi lần append thực tế đều O(1).
- Chỉ cần random input thì append kỳ vọng O(1).
- Amortized O(1) là một lower bound của bài toán.

Amortized là cách **phân tích chi phí qua nhiều thao tác của một thuật toán/cấu trúc dữ liệu**, không phải một lớp độ khó mới của bài toán.

## 15. Thời gian và bộ nhớ: một lời giải có nhiều loại chi phí

Cùng một thuật toán có thể được đánh giá bằng:

- **Thời gian**: số bước hoặc phép toán.
- **Bộ nhớ phụ**: ngoài dữ liệu input, chưa tính output tùy quy ước.
- **Lượng dữ liệu ghi/đọc**: số thao tác I/O hoặc cache misses.
- **Số phép so sánh**, **số phép hash**, **số queries tới oracle**, **chi phí mạng**.
- **Tính khả song song**: độ sâu span, tổng work, số máy.
- **Độ chính xác và xác suất thành công** cho randomized/approximation algorithms.

Vét cạn Two Sum dùng O(1) bộ nhớ phụ; merge sort dùng O(n); hash set cũng dùng O(n). Nếu RAM rất hạn chế, một thuật toán chậm hơn về thời gian có thể là lựa chọn hợp lý.

### Không coi Big O là một số giây cụ thể

O(n log n) không cho biết:

- Một lần so sánh mất bao lâu.
- HashSet cấp phát bao nhiêu object và gây GC thế nào.
- Dữ liệu có nằm trong CPU cache không.
- JVM JIT đã warm up chưa.
- Tốc độ I/O và cấu hình môi trường.

Big O mô tả **xu hướng tiệm cận**, không thay được benchmark và profiling thực nghiệm.

## 16. Kích thước input theo bit và chi phí phép toán

Một sai lầm lý thuyết rất quan trọng là dùng giá trị số **N** làm kích thước input dù N được viết bằng chỉ:

**L=Θ(log₂ N)** bit.

Ví dụ thuật toán lặp i từ 1 đến N tốn O(N) bước. Nhưng nếu input chỉ là N mã hóa nhị phân, thì:

**N có thể xấp xỉ 2^L**.

Do đó O(N) là **hàm mũ theo chiều dài bit L**, không phải đa thức theo L.

### Mô hình word-RAM

Khi phần tử là int 32-bit và phép cộng/so sánh trên word cố định được tính O(1), các bảng O(n) hay O(n²) có ý nghĩa quen thuộc.

### Bit complexity

Khi số nguyên có B bit, cộng/trừ có thể cần Θ(B) bit operations, còn nhân/chia phụ thuộc thuật toán số học được dùng. Nếu n số có bit-length khác nhau, chi phí đọc, so sánh, hash và tính tổng cũng phải xét tới kích thước bit.

**Không thể đổi toàn bộ số từ int sang BigInteger và giữ nguyên mọi khẳng định O(1) cho phép toán số học** mà không thay mô hình.

## 17. Giả đa thức: ví dụ Subset Sum và Knapsack

Cho các số nguyên **không âm** a₁,...,aₙ và mục tiêu S, bài quyết định **SUBSET SUM** hỏi có tập con tổng đúng S hay không.

Một quy hoạch động cơ bản đánh dấu các tổng có thể đạt từ 0 đến S:

**O(nS) thời gian**, **O(S) bộ nhớ** cho biến thể 1D phù hợp.

Nhìn theo n và giá trị số S, đây có vẻ là đa thức.

Nhưng S được mã hóa nhị phân bằng:

**Θ(log(S+1)) bit**.

Khi S lớn kiểu 2^n, O(nS) là **hàm mũ theo số bit biểu diễn S**. Vì vậy ta gọi thuật toán này là **giả đa thức (pseudo-polynomial)**, không phải thuật toán đa thức tổng quát theo chiều dài input.

### Liên hệ độ khó

SUBSET SUM quyết định với input nhị phân tổng quát là một bài toán **NP-complete**. Sự tồn tại của DP O(nS) **không mâu thuẫn** với kết quả đó, vì O(nS) không bắt buộc đa thức theo số bit đầu vào.

Bài Knapsack 0/1 cũng có các DP giả đa thức theo capacity hoặc tổng giá trị tùy biến thể, nhưng phải nêu rõ variant và miền giá trị.

### Khi nào DP vẫn hữu ích?

Nếu S nhỏ (ví dụ vài chục nghìn) dù n lớn vừa phải, DP O(nS) có thể rất nhanh trong thực tế. Việc một bài NP-complete không có nghĩa **mọi instance đều khó**.

## 18. Lớp P: tồn tại ít nhất một thuật toán đa thức

Trong lý thuyết độ phức tạp, **P** là lớp các **bài toán quyết định** giải được bằng máy Turing xác định trong thời gian đa thức theo **chiều dài input**.

Một điều kiện quan trọng:

> Bài toán thuộc P nếu **tồn tại một thuật toán đúng cho mọi instance** và chạy trong thời gian đa thức theo kích thước input.

Không phải mọi thuật toán giải bài ấy đều cần đa thức.

Ví dụ:

- Một thuật toán vét cạn không hiệu quả có thể tốn O(2^n).
- Nếu đã có một thuật toán khác O(n³), bài toán vẫn thuộc P.

Do đó, **“thuật toán A có thời gian mũ” không chứng minh bài toán không thuộc P**.

### Two Sum là ví dụ trong P

Với dữ liệu là mảng int và target long, thuật toán merge sort + hai con trỏ chạy O(n log n) trên word-RAM, thể hiện một lời giải đa thức. Có thể diễn đạt bằng mô hình máy chuẩn tương ứng để chứng minh bài quyết định này trong P.

Ngay cả nếu ai đó viết một phiên bản thử mọi cách ghép cặp có thời gian rất lớn, điều đó không làm thay đổi kết luận tồn tại lời giải đa thức.

## 19. Lớp NP: có chứng chỉ kiểm tra được trong thời gian đa thức

**NP** là lớp các bài toán quyết định có thể được kiểm tra **chứng chỉ YES** trong thời gian đa thức bằng một verifier xác định, với kích thước chứng chỉ cũng đa thức theo input.

Một cách tương đương là lớp bài toán quyết định giải được trong thời gian đa thức bởi mô hình máy Turing phi xác định.

### Ví dụ SAT

Cho một công thức Boolean. Hỏi có phép gán true/false cho các biến làm công thức đúng không?

Một chứng chỉ YES là một **phép gán biến**. Ta có thể thay giá trị biến và tính công thức trong thời gian đa thức theo độ dài công thức.

Do đó SAT thuộc NP.

Điều này **không nói rằng mọi chứng chỉ NO cũng kiểm tra theo cách tương tự**, cũng không mặc nhiên nói đã có thuật toán xác định đa thức để tìm phép gán.

### P là tập con của NP

Nếu giải bài quyết định được trong thời gian đa thức, ta có thể dùng luôn thuật toán giải làm verifier, nên:

**P ⊆ NP**.

Câu hỏi **P có bằng NP hay không** vẫn là vấn đề mở. Không được khẳng định P≠NP đã được chứng minh.

## 20. NP-hard và NP-complete

**NP-hard** (theo quy giảm đa thức phù hợp, thường là many-one reductions) nghĩa là mọi bài toán trong NP đều có thể quy giảm về bài đang xét trong thời gian đa thức.

**NP-complete** nghĩa là đồng thời:

1. Bài thuộc **NP**.
2. Bài **NP-hard**.

### Ví dụ

- **SAT** (quyết định) là NP-complete.
- **3-SAT** là NP-complete.
- **SUBSET SUM quyết định** với dữ liệu nhị phân tổng quát là NP-complete.
- **Hamiltonian Cycle quyết định** là NP-complete.
- **Traveling Salesperson quyết định** (có tour với tổng chi phí ≤B hay không, theo mã hóa đầu vào thích hợp) là NP-complete.

Những ví dụ này cần hiểu đúng biến thể **decision** và giả thiết encoding.

### NP-hard không tự có nghĩa “nằm trong NP”

Một bài tối ưu, một bài không quyết định hoặc thậm chí bài không quyết định được có thể NP-hard theo một định nghĩa reduction thích hợp. Vì vậy:

**NP-hard không đồng nghĩa NP-complete.**

### NP-complete không tự nói mọi instance đều khó

Một số instance SAT rất dễ, ví dụ công thức chứa x∧¬x thì có thể nhận ra ngay một mâu thuẫn. Độ khó trong lớp phức tạp là phát biểu về **cả họ instance và cận tài nguyên**, thường worst-case, không dự đoán thời gian của một input bất kỳ.

## 21. Hướng của phép quy giảm rất quan trọng

Để chứng minh bài mới B **NP-hard**, một cách chuẩn là chọn bài A đã biết NP-hard và xây một quy giảm đa thức:

**A ≤ₚ B**.

Điều này có nghĩa: có thể biến đổi **mọi instance của A** thành instance của B trong thời gian đa thức sao cho kết quả YES/NO được bảo toàn.

Nếu B có thuật toán đa thức, ta dùng reduction rồi chạy thuật toán B để giải A đa thức. Vì A đã NP-hard, như vậy B ít nhất “khó” theo nghĩa reduction.

### Phản hướng sai thường gặp

Nếu chỉ chứng minh:

**B ≤ₚ A**

với A NP-hard, ta chỉ cho thấy B **không khó hơn A** theo kiểu reduction ấy. Điều này **không đủ** chứng minh B là NP-hard.

Ví dụ một bài dễ có thể quy giảm về một bài khó; hướng ấy không làm bài dễ trở nên NP-hard.

### Để chứng minh NP-complete

Cần hai phần độc lập:

- Chứng minh **B ∈ NP** bằng chứng chỉ/verifier đa thức.
- Chứng minh **A ≤ₚ B** từ một bài A đã biết NP-hard.

Viết “vì chưa tìm được thuật toán đa thức cho B nên B NP-hard” là **không hợp lệ**.

## 22. Vì sao “chưa có thuật toán nhanh” không phải cận dưới?

Có thể một bài toán được nghiên cứu nhiều năm mà chưa biết thuật toán O(n²) hay O(n log n) tối ưu. Điều đó không tự chứng minh mọi thuật toán nhanh hơn đều bất khả thi.

Để lập **cận dưới** cần một lập luận:

- Cây quyết định trong mô hình so sánh.
- Lập luận adversary về số lượng thông tin phải đọc.
- Phép quy giảm từ bài toán đã có lower bound/lớp hardness.
- Các phương pháp đại số, thông tin hoặc kỹ thuật complexity chuyên biệt.

Với nhiều bài toán, **khoảng cách giữa cận trên tốt nhất và cận dưới biết được vẫn còn**.

### Một thuật toán chạy nhanh trong benchmark cũng không phải chứng minh

Nếu chạy 10.000 trường hợp và thấy gần tuyến tính, ta có một kết quả thực nghiệm. Nó không chứng minh worst-case O(n), bởi có thể tồn tại những input hiếm gây O(n²).

Tương tự, nếu đo một thuật toán O(n log n) chậm hơn O(n²) với n=20, điều đó không bác bỏ phân tích tiệm cận.

## 23. Kết quả phân lớp phụ thuộc biến thể

Một chủ đề có thể có:

- Bản **quyết định**.
- Bản **tìm một lời giải**.
- Bản **tối ưu**.
- Bản **đếm số lời giải**.
- Bản **liệt kê toàn bộ lời giải**.
- Bản **xấp xỉ trong sai số cho phép**.

Các bản có thể liên hệ bằng reduction, nhưng không thể chuyển kết quả phân lớp **tùy tiện**.

Ví dụ:

- SAT: hỏi có phép gán thỏa hay không (decision).
- #SAT: đếm số phép gán thỏa; đây là vấn đề đếm, không nên gắn nhãn “NP-complete” như một bài quyết định nếu không giải thích phép chuyển dạng.
- Một bài tối ưu TSP có thể NP-hard, còn biến thể decision với một ngưỡng B phù hợp là NP-complete.

### Output size có thể là cận dưới

Nếu bài yêu cầu in 2^n tập con, chỉ riêng output có kích thước ít nhất Ω(2^n), dù việc kiểm tra tồn tại một tập con theo điều kiện đơn giản có thể nhanh.

Không được so một thuật toán liệt kê với một thuật toán quyết định rồi tuyên bố thuật toán quyết định nhanh hơn đã giải được toàn bộ yêu cầu liệt kê.

## 24. Quy mô thực tế, tham số và thuật toán FPT

Một thuật toán thời gian:

**O(2^k · n³)**

là **fixed-parameter tractable (FPT)** theo tham số k nếu n là phần còn lại của input size và k được xem như tham số được phân biệt.

Nó có thể hiệu quả khi k nhỏ, dù thuật toán là hàm mũ theo k. Ngược lại, nếu k tăng cùng n, phần 2^k có thể chi phối hoàn toàn.

### Tại sao điều này không mâu thuẫn với độ khó cổ điển?

Complexity cổ điển thường đo mọi đầu vào theo tổng chiều dài bit. Parameterized complexity thêm một **tham số cấu trúc** có thể phản ánh vì sao nhiều instance thực tế dễ hơn trường hợp xấu tổng quát.

Ví dụ, một số bài khó trên đồ thị có thể có thuật toán nhanh khi **treewidth, kích thước nghiệm, số đỉnh ngoại lệ hoặc một tham số khác** nhỏ. Không được tự tuyên bố một bài NP-hard đã thành P chỉ vì có thuật toán FPT theo k.

### Số nhỏ và pseudo-polynomial

Điều kiện “S nhỏ” trong Subset Sum DP là một dạng khai thác cấu trúc số học của input. Bài tổng quát vẫn có thể NP-complete.

## 25. Đọc đúng độ phức tạp trong bài toán đồ thị

Trên đồ thị có V đỉnh, E cạnh:

**BFS:** O(V+E) với danh sách kề và thao tác queue phù hợp. Nhưng nếu input cung cấp **ma trận kề V×V**, chỉ việc quét cạnh có thể cần O(V²) trong biểu diễn đó.

**Dijkstra:** trên trọng số không âm, chi phí phụ thuộc cấu trúc priority queue, ví dụ O((V+E) log V) với heap nhị phân trong mô hình thích hợp và cài đặt phù hợp.

**Bellman–Ford:** thường O(VE), có thể xử lý cạnh âm và phát hiện chu trình âm đạt được từ nguồn theo cách chuẩn.

Không thể nói “độ khó tìm đường ngắn nhất là O(VE)” chỉ vì đã viết Bellman–Ford, hoặc nói “Dijkstra giải mọi đồ thị nhanh hơn” khi trọng số âm làm điều kiện áp dụng không còn đúng.

### Định nghĩa input và lời giải phải giữ nguyên

Khi so hai thuật toán, cần bảo đảm chúng giải **cùng output** trên **cùng lớp dữ liệu hợp lệ**. Nếu một thuật toán nhanh chỉ giải trường hợp hẹp hơn, đó là một tradeoff của giả thiết đầu vào, không tự động là một cải tiến cho bài toán tổng quát.

## 26. Mã Java 17+ độc lập: cùng bài toán, ba chi phí khác nhau

Chương trình minh họa **TWO-SUM-EXISTS** trên mảng int và target long.

Nó có:

1. **bruteForce:** vét cạn các cặp i<j, O(n²) worst-case, O(1) phụ.
2. **mergeSortTwoPointers:** copy input, merge sort O(n log n) worst-case rồi hai con trỏ O(n), O(n) phụ.
3. **hashSetOnePass:** quét một lần, kiểm tra trước khi thêm vào HashSet, O(n) kỳ vọng, O(n) bộ nhớ.
4. Mười ba ca đầu vào gồm số âm, giá trị trùng, mảng rỗng, hai giá trị Integer.MIN_VALUE/MAX_VALUE, target Long.MIN_VALUE.
5. Đối chiếu kết quả ba cách trong mỗi ví dụ; nếu khác nhau, ném AssertionError.

### Bảo đảm không tràn số

Tổng hai giá trị int có thể vượt int:

**Integer.MAX_VALUE + Integer.MAX_VALUE = 4294967294**.

Do đó brute và two-pointer ép sang **long trước phép cộng**.

Thuật toán HashSet tính need=T−x. Để tránh overflow khi target là một long cực trị, chương trình trước hết kiểm tra:

**2·Integer.MIN_VALUE ≤ T ≤ 2·Integer.MAX_VALUE**.

Nếu T nằm ngoài khoảng này, không thể có hai số int nào có tổng bằng T; trả false ngay. Sau kiểm tra, T−(long)x có cận nhỏ và chắc chắn vừa long; chỉ ép need sang int sau khi kiểm tra miền int.

**Lưu tệp: ProblemVsAlgorithmCostDemo.java**

~~~java
import java.util.Arrays;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class ProblemVsAlgorithmCostDemo {

    static final long MIN_PAIR_SUM =
            2L * Integer.MIN_VALUE;

    static final long MAX_PAIR_SUM =
            2L * Integer.MAX_VALUE;

    // A: O(n^2) worst-case time, O(1) extra memory.
    static boolean bruteForce(int[] values, long target) {
        Objects.requireNonNull(values, "values");

        for (int i = 0; i < values.length; i++) {
            for (int j = i + 1; j < values.length; j++) {
                long sum = (long) values[i] + values[j];

                if (sum == target) {
                    return true;
                }
            }
        }

        return false;
    }

    // Stable merge sort on a COPY of the input array.
    // The sorting phase has O(n log n) worst-case time.
    static int[] sortedCopy(int[] values) {
        int[] sorted = Arrays.copyOf(values, values.length);
        int[] buffer = new int[sorted.length];

        mergeSort(sorted, buffer, 0, sorted.length);
        return sorted;
    }

    // [from,to) is a half-open interval.
    static void mergeSort(
            int[] a, int[] buffer, int from, int to) {

        if (to - from <= 1) {
            return;
        }

        int middle = from + (to - from) / 2;

        mergeSort(a, buffer, from, middle);
        mergeSort(a, buffer, middle, to);

        int i = from;
        int j = middle;
        int k = from;

        while (i < middle && j < to) {
            if (a[i] <= a[j]) {
                buffer[k++] = a[i++];
            } else {
                buffer[k++] = a[j++];
            }
        }

        while (i < middle) {
            buffer[k++] = a[i++];
        }

        while (j < to) {
            buffer[k++] = a[j++];
        }

        System.arraycopy(
                buffer, from, a, from, to - from);
    }

    // B: O(n log n) worst-case time, O(n) extra memory.
    static boolean mergeSortTwoPointers(
            int[] values, long target) {

        Objects.requireNonNull(values, "values");

        int[] sorted = sortedCopy(values);
        int left = 0;
        int right = sorted.length - 1;

        while (left < right) {
            long sum = (long) sorted[left] + sorted[right];

            if (sum == target) {
                return true;
            }

            if (sum < target) {
                left++;
            } else {
                right--;
            }
        }

        return false;
    }

    // C: O(n) expected time under hashing assumptions,
    // O(n) extra memory; worst-case hashing is distinct.
    static boolean hashSetOnePass(
            int[] values, long target) {

        Objects.requireNonNull(values, "values");

        // Any pair of int values must sum to this range.
        // The check also keeps target - value within long.
        if (target < MIN_PAIR_SUM
                || target > MAX_PAIR_SUM) {
            return false;
        }

        Set<Integer> seen = new HashSet<>();

        for (int value : values) {
            long needed = target - (long) value;

            if (needed >= Integer.MIN_VALUE
                    && needed <= Integer.MAX_VALUE
                    && seen.contains((int) needed)) {
                return true;
            }

            // Add AFTER checking to require distinct indices.
            seen.add(value);
        }

        return false;
    }

    static void show(
            String label, int[] values, long target) {

        boolean brute = bruteForce(values, target);
        boolean merge = mergeSortTwoPointers(values, target);
        boolean hash = hashSetOnePass(values, target);

        if (brute != merge || brute != hash) {
            throw new AssertionError(
                    "Methods disagree on " + label);
        }

        System.out.println(label
                + ": target=" + target
                + ", brute=" + brute
                + ", merge=" + merge
                + ", hash=" + hash);
    }

    public static void main(String[] args) {

        show("Basic",
                new int[] { 2, 7, 11, 15 }, 9L);

        show("Duplicate pair",
                new int[] { 3, 3 }, 6L);

        show("Single item",
                new int[] { 3 }, 6L);

        show("Negative values",
                new int[] { -4, 10, 6 }, 2L);

        show("Two max ints",
                new int[] {
                        Integer.MAX_VALUE,
                        Integer.MAX_VALUE
                },
                2L * Integer.MAX_VALUE);

        show("Two min ints",
                new int[] {
                        Integer.MIN_VALUE,
                        Integer.MIN_VALUE
                },
                2L * Integer.MIN_VALUE);

        show("Impossible",
                new int[] { 1, 2, 3 }, 100L);

        show("Opposite extremes",
                new int[] {
                        Integer.MAX_VALUE,
                        Integer.MIN_VALUE
                },
                -1L);

        show("Empty",
                new int[] {}, 0L);

        show("Three zeroes",
                new int[] { 0, 0, 0 }, 0L);

        show("Opposite values",
                new int[] { 8, -8 }, 0L);

        show("Single max",
                new int[] { Integer.MAX_VALUE },
                2L * Integer.MAX_VALUE);

        show("Out of range",
                new int[] { 10, 2, -3, 1 },
                Long.MIN_VALUE);
    }
}
~~~

Biên dịch và chạy với **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 ProblemVsAlgorithmCostDemo.java
java ProblemVsAlgorithmCostDemo
~~~

**Đầu ra chuẩn của chương trình:**

~~~text
Basic: target=9, brute=true, merge=true, hash=true
Duplicate pair: target=6, brute=true, merge=true, hash=true
Single item: target=6, brute=false, merge=false, hash=false
Negative values: target=2, brute=true, merge=true, hash=true
Two max ints: target=4294967294, brute=true, merge=true, hash=true
Two min ints: target=-4294967296, brute=true, merge=true, hash=true
Impossible: target=100, brute=false, merge=false, hash=false
Opposite extremes: target=-1, brute=true, merge=true, hash=true
Empty: target=0, brute=false, merge=false, hash=false
Three zeroes: target=0, brute=true, merge=true, hash=true
Opposite values: target=0, brute=true, merge=true, hash=true
Single max: target=4294967294, brute=false, merge=false, hash=false
Out of range: target=-9223372036854775808, brute=false, merge=false, hash=false
~~~

### Điểm cần hiểu từ code

**Cùng output, khác quy trình.** Cả ba hàm dùng cùng đặc tả Two Sum và trả boolean, nên kết quả phải thống nhất.

**Vét cạn là oracle tốt.** Thuật toán O(n²) không nên vứt bỏ hoàn toàn: với test nhỏ, cách duyệt mọi cặp rất dễ kiểm tra và làm lời giải tham chiếu độc lập.

**Merge sort có cận worst-case.** Code tự triển khai merge sort trên bản sao, nên nhãn O(n log n) worst-case không phụ thuộc giả định về một biến thể thư viện sort cụ thể.

**HashSet có kỳ vọng.** Không ghi đơn giản “chắc chắn O(n) trường hợp xấu” khi không có chứng minh bound của hashing và triển khai.

**Dùng hai chỉ số khác nhau.** Vét cạn lấy j>i, hai con trỏ chỉ hoạt động khi left<right, HashSet kiểm tra trước khi thêm.

**Bảo toàn input.** Merge sort làm việc trên copy, không sửa giá trị/cách sắp xếp của mảng gốc. Cả ba hàm đều không làm biến đổi input.

**Cận target.** Hai số int cộng lại có miền tổng từ 2·Integer.MIN_VALUE đến 2·Integer.MAX_VALUE; target ngoài miền chắc chắn false, không cần phép trừ có nguy cơ overflow.

**Chú ý chi phí thật.** HashSet có thể tốn RAM/GC hơn, merge sort cấp mảng bổ sung, và brute có thể chạy rất nhanh cho n nhỏ. Không có một “tốt nhất tuyệt đối” cho mọi yêu cầu thời gian, RAM và dữ liệu.

## 27. Kiểm thử bằng oracle độc lập

Khi có ba thuật toán, cách kiểm chứng tốt là dùng **vét cạn** làm oracle rồi tạo rất nhiều input nhỏ để so kết quả của merge sort và hashing.

### Các họ test

1. Mảng rỗng, mảng một phần tử.
2. Hai phần tử bằng nhau, cần dùng cả hai vị trí.
3. Nhiều bản sao của cùng một giá trị.
4. Số âm, số 0, số dương.
5. Mảng đã sắp tăng, sắp giảm, hoàn toàn bằng nhau.
6. Target âm, bằng 0, dương.
7. Target bằng Integer.MIN_VALUE hoặc Integer.MAX_VALUE.
8. Target ở biên tổng hai int: −4294967296 và 4294967294.
9. Target ngoài miền tổng int: Long.MIN_VALUE hoặc Long.MAX_VALUE.
10. Cặp đáp án xuất hiện đầu mảng, cuối mảng hoặc không có.
11. Random arrays có độ dài từ 0 đến vài chục, chứa lặp, cực trị và target lấy từ tổng hai phần tử được chọn.
12. Kiểm tra **input không bị thay đổi** bởi phiên bản merge sort.

### Bất biến hữu ích

- Với n<2, đáp án luôn false.
- Hoán vị mảng không thay đổi **tính tồn tại** của cặp.
- Nếu đã có cặp đáp án, thêm một phần tử khác không làm mất cặp đó.
- Nếu tất cả phần tử là 0 thì đáp án true khi và chỉ khi n≥2 và T=0.
- Nếu target ngoài miền tổng của hai int, đáp án false.
- Mọi thuật toán phải trả cùng boolean cho cùng dữ liệu đầu vào hợp lệ.

### Tránh QA vòng tròn

Không nên chỉ so hai hàm hashing gần như giống hệt nhau; chúng có thể mắc cùng lỗi xử lý duplicate hoặc overflow.

Vét cạn dùng hai vòng lặp i<j, merge sort dùng tính đơn điệu của thứ tự, HashSet dùng complement và một tập giá trị đã thấy. Đây là ba cách nhìn đủ khác nhau để kiểm thử chéo có giá trị.

## 28. Phân tích thực nghiệm: khi nào benchmark có ý nghĩa?

Một benchmark có giá trị cần:

- Nêu kích thước n và phân phối input.
- Nêu kiểu dữ liệu/target và tỷ lệ instance có nghiệm.
- Đo nhiều lần, có warm-up JVM JIT nếu phù hợp.
- Kiểm soát tối thiểu biến động của GC, CPU và môi trường.
- Báo cả time và memory khi có tradeoff.
- Tránh tính thời gian sinh dữ liệu/ghi output lẫn vào phần cần so nếu không đó là mục tiêu đo.
- Với đo hashing, không sử dụng tập input chỉ có một kiểu giá trị rồi suy rộng sang mọi phân phối.
- Với việc kiểm thử đúng, phải so kết quả trước khi so thời gian.

### Vì sao benchmark không chứng minh Big O?

Nếu đo n=100,1000,10000 và thấy thời gian tăng chậm, đó chỉ là bằng chứng thực nghiệm trên các n ấy. Các hiệu ứng cache và warm-up có thể lấn át asymptotic trong đoạn nhỏ.

Để chứng minh thời gian worst-case, phải phân tích số vòng, số phép gọi, cấu trúc dữ liệu và những input bất lợi, không chỉ fit một đường cong qua các số đo.

### Có thể chọn brute cho n=15 không?

Có. Số cặp nhiều nhất chỉ:

**15·14/2=105**.

Chi phí tạo HashSet và object có thể không đáng so với 105 phép cộng/so sánh. Đây là quyết định tối ưu **thực tế** chứ không làm thay đổi cận tiệm cận O(n²) của brute.

## 29. Những lỗi lập luận thường gặp

1. **“Tôi có code O(n²), vậy độ khó bài toán là Θ(n²).”** Sai: mới có cận trên từ một thuật toán.
2. **“Một thuật toán exponential ⇒ bài toán NP-hard.”** Sai: phải chứng minh hardness bằng reduction hay lập luận phù hợp.
3. **“Chưa ai tìm được thuật toán đa thức ⇒ bài toán không thuộc P.”** Sai: không có chứng minh cận dưới.
4. **“NP nghĩa là không giải được trong đa thức.”** Sai: NP là lớp có verifier YES đa thức, P⊆NP.
5. **“NP-hard nghĩa là nằm trong NP.”** Sai: NP-hard không tự đảm bảo membership.
6. **“NP-complete đã chứng minh không có thuật toán P.”** Sai: câu hỏi P=NP vẫn mở.
7. **“Muốn chứng minh B NP-hard, chỉ cần quy giảm B về một bài NP-hard A.”** Sai hướng: thường cần A≤ₚB.
8. **“Big O là thời gian thực tế tính bằng giây.”** Sai: Big O là quan hệ tiệm cận.
9. **“Big O luôn mô tả worst-case.”** Sai: phải chỉ định hàm chi phí đang phân tích.
10. **“O(n) kỳ vọng của HashSet là bảo đảm worst-case O(n).”** Sai nếu thiếu giả thiết và phân tích hashing cụ thể.
11. **“Thuật toán nhanh hơn ở n nhỏ ⇒ asymptotic tốt hơn.”** Sai: constant factors và memory ảnh hưởng.
12. **“Thuật toán O(n log n) luôn tốt hơn O(n²) ở mọi n.”** Sai ở kích thước nhỏ.
13. **“Cứ xài Dijkstra là giải được mọi cạnh âm.”** Sai điều kiện input.
14. **“Cận dưới sorting Ω(n log n) cấm Counting Sort O(n+K).”** Sai mô hình.
15. **“O(nS) là đa thức theo input nhị phân của S.”** Sai: S có thể là mũ theo số bit.
16. **“Bài NP-complete thì mọi instance đều khó.”** Sai: worst-case là trên một họ instance.
17. **“Một bài liệt kê Θ(n²) output có thể in trong O(n) thời gian.”** Không trong mô hình output tường minh.
18. **“Một chứng chỉ YES dễ kiểm tra nghĩa là tìm lời giải cũng dễ.”** Không suy ra thuật toán P.
19. **“Chỉ một số benchmark là chứng minh thuật toán tối ưu.”** Không có lower bound.
20. **“Chi phí thời gian là thước đo duy nhất.”** Bỏ RAM, I/O, latency và constraints.
21. **“Bộ nhớ của HashSet là O(1) vì chỉ có một biến seen.”** Sai: tập chứa O(n) giá trị.
22. **“Sắp xếp bản gốc không có chi phí phụ.”** Có thể phá yêu cầu giữ nguyên input.
23. **“Nếu array chứa một số 3, có thể dùng nó hai lần để đạt 6.”** Sai khi hai chỉ số phải khác nhau.
24. **“Java int+int tự lên long nếu gán vào long.”** Sai: phép cộng xảy ra ở int trước.
25. **“T−x luôn an toàn với long.”** Sai khi T gần Long.MIN_VALUE và x dương, hoặc T gần Long.MAX_VALUE và x âm.
26. **“HashSet phải chứa cả phần tử hiện tại rồi mới kiểm tra.”** Sai: có thể trùng chỉ số.
27. **“Dùng phép so sánh giá trị rồi bỏ qua negative/duplicates là đủ.”** Sai với nhiều ca biên.
28. **“Tất cả các bài toán gần giống nhau có cùng độ khó.”** Sai: đổi ràng buộc hoặc output có thể đổi lớp.
29. **“Nếu thuật toán dùng BigInteger thì vẫn O(1) mỗi phép nhân.”** Sai trong mô hình bit.
30. **“O(n) thời gian đọc mảng không thể bị ảnh hưởng bởi input encoding.”** Sai nếu word/byte layout thay đổi.
31. **“Amortized O(1) nghĩa là mỗi thao tác đều O(1).”** Sai: có thao tác resize O(n).
32. **“Average-case không cần phân phối input.”** Sai: phải có mô hình xác suất.
33. **“Randomized expected và input average là một.”** Sai: nguồn xác suất khác nhau.
34. **“Một thuật toán FPT theo k có nghĩa tổng quát là P.”** Sai: 2^k có thể lớn.
35. **“Bài toán decision có cùng output size với enumeration.”** Sai: enumeration có thể xuất rất nhiều kết quả.
36. **“Một thuật toán mới O(n log n) chứng minh có cận dưới Ω(n log n).”** Sai: chỉ thêm cận trên.
37. **“Lower bound của một thuật toán đủ kết luận lower bound của bài toán.”** Sai: cần phát biểu về tất cả thuật toán trong mô hình.
38. **“Nếu một thuật toán không chạy được với n=10^9 thì bài toán không khả thi.”** Sai: có thể có thuật toán, cấu trúc hay model khác.
39. **“Bài P nhất thiết có mọi cài đặt đa thức.”** Sai: membership chỉ yêu cầu tồn tại một thuật toán.
40. **“Quy giảm ngược chiều có thể thay thế chứng minh membership NP.”** Sai: membership và hardness là hai điều kiện riêng.

## 30. Bài tập tự luyện có đáp án

**Câu 1.** Vét cạn Two Sum chạy O(n²). Có thể kết luận bài toán cần Ω(n²) không?  
**Đáp án:** Không; O(n²) của vét cạn chỉ là cận trên từ một thuật toán.

**Câu 2.** Hai lời giải O(n²) và O(n log n) giải cùng bài toán. Điều gì thay đổi?  
**Đáp án:** Thuật toán và cận trên tốt nhất biết được; đặc tả bài toán không đổi.

**Câu 3.** Khi nào có thể khẳng định Θ(n log n) tối ưu cho sắp xếp?  
**Đáp án:** Khi nói rõ mô hình sắp xếp bằng so sánh, có lower bound Ω(n log n) và upper bound O(n log n).

**Câu 4.** Counting Sort O(n+K) có mâu thuẫn lower bound comparison sorting không?  
**Đáp án:** Không, vì dùng cấu trúc giá trị và phụ thuộc K, không bị ràng buộc chỉ so sánh.

**Câu 5.** Two Sum trên [3,3], T=6 có đáp án không?  
**Đáp án:** Có, vì có hai chỉ số khác nhau.

**Câu 6.** Two Sum trên [3], T=6 có đáp án không?  
**Đáp án:** Không, vì chỉ có một chỉ số.

**Câu 7.** Vì sao HashSet cần kiểm tra complement trước khi add?  
**Đáp án:** Để không dùng một phần tử hai lần.

**Câu 8.** Vì sao target và phép cộng hai int cần dùng long?  
**Đáp án:** Hai int cực đại có tổng 4294967294, vượt Integer.MAX_VALUE.

**Câu 9.** Bài có thuật toán O(n³) thuộc P không?  
**Đáp án:** Nếu đây là bài quyết định và thuật toán chạy đa thức theo kích thước input cho mọi instance, thì có.

**Câu 10.** Có thuật toán exponential cho một bài thuộc P được không?  
**Đáp án:** Có; một thuật toán chậm không thay đổi membership P của bài toán.

**Câu 11.** Điều kiện chứng minh NP-complete?  
**Đáp án:** Membership NP và NP-hardness theo reduction đa thức phù hợp.

**Câu 12.** Để chứng minh B NP-hard từ A đã biết NP-hard, reduction theo hướng nào?  
**Đáp án:** A≤ₚB.

**Câu 13.** SAT thuộc NP vì sao?  
**Đáp án:** Một phép gán YES có thể được kiểm tra trong thời gian đa thức.

**Câu 14.** P có chắc khác NP không?  
**Đáp án:** Chưa có chứng minh, đây là câu hỏi mở.

**Câu 15.** O(nS) với S nhập nhị phân có nhất thiết đa thức theo input length không?  
**Đáp án:** Không; S có thể là hàm mũ theo log₂ S bit.

**Câu 16.** Nếu bài yêu cầu in mọi cặp chỉ số của mảng toàn số 0, chi phí output?  
**Đáp án:** Θ(n²) cặp khi T=0.

**Câu 17.** Expected hashing O(n) có đồng nghĩa worst-case O(n) không?  
**Đáp án:** Không; expected phụ thuộc giả thiết/phân phối thao tác hash.

**Câu 18.** Amortized append O(1) có nghĩa mỗi append đều O(1) không?  
**Đáp án:** Không; resize có thể tốn O(n) cho một lần.

**Câu 19.** Vì sao phân tích BigInteger khác với int?  
**Đáp án:** Các phép số học còn có chi phí theo số bit, không còn word O(1) tùy tiện.

**Câu 20.** Khi nào chọn brute O(n²) thay hash O(n) kỳ vọng?  
**Đáp án:** Khi n nhỏ, RAM hạn chế, hoặc cần oracle đơn giản; vẫn phải xét dữ liệu và môi trường.

## 31. Checklist giải bài và kết luận

Trước khi phát biểu **“độ khó của bài toán”** hoặc **“độ phức tạp của thuật toán”**, hãy hỏi:

1. **Đặc tả bài toán chính xác là gì?** Quyết định, tìm kiếm, tối ưu, đếm hay liệt kê?
2. **Instance hợp lệ gồm những gì?** Có số âm, trùng, trọng số âm, số nguyên lớn, dữ liệu đã sắp chưa?
3. **Kích thước input được đo bằng gì?** n phần tử, V và E, hay L bit?
4. **Đang phân tích một thuật toán cụ thể hay mọi thuật toán?**
5. **Chi phí nào quan tâm?** Time, space, comparisons, I/O, queries hay output size?
6. **Mô hình tính toán là gì?** Word-RAM, comparison, bit operations, random access hay external memory?
7. **Big O đang chặn hàm chi phí nào?** Worst-case, average, randomized expected, amortized?
8. **Có bằng chứng thuật toán đúng cho mọi input hợp lệ không?** Không chỉ benchmark.
9. **Cận trên đã chứng minh gì?** Tồn tại một cách giải dùng tối đa mức tài nguyên đó.
10. **Cận dưới đã chứng minh gì?** Mọi thuật toán trong mô hình cần ít nhất mức nào?
11. **Có lower bound khớp upper bound không?** Nếu không, đừng gọi đang có là tối ưu.
12. **Có thay đổi bài toán khi thêm giả thiết không?** Ví dụ integer bounded, graph nonnegative hoặc input sorted.
13. **Nếu nói P/NP/NP-hard/NP-complete, đã đúng biến thể decision và hướng reduction chưa?**
14. **Một thuật toán giả đa thức có thật sự đa thức theo bit-length không?**
15. **Nếu dùng HashSet, đã tách expected và worst-case chưa?**
16. **Nếu output nhiều phần tử, đã tính chi phí xuất output chưa?**
17. **Nếu RAM hạn chế, có tradeoff với thời gian cần đánh giá không?**
18. **Nếu benchmark, có thử dữ liệu đối kháng, warm-up, memory và correctness không?**
19. **Có oracle độc lập cho các thuật toán tối ưu hơn không?**
20. **Kết luận đã nói rõ phạm vi chứng minh và giả thiết không?**

**Kết luận:** chi phí của một thuật toán là thuộc tính của **quy trình đang chạy**, còn độ khó của bài toán là câu hỏi về **những gì có thể đạt được với mọi thuật toán hợp lệ trong một mô hình và lớp input đã định nghĩa**. Việc tìm được lời giải nhanh hơn cho cùng một bài toán chứng minh một **cận trên tốt hơn**, không tự cung cấp cận dưới. Hiểu đúng sự phân biệt này là nền tảng để phân tích thuật toán, chứng minh tối ưu, sử dụng các lớp P/NP đúng nghĩa và lựa chọn lời giải phù hợp về thời gian lẫn bộ nhớ.
