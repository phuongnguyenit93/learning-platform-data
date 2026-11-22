# Lựa chọn thuật toán theo dữ liệu, bộ nhớ và yêu cầu ổn định

Không có thuật toán sắp xếp so sánh nào tốt nhất cho **mọi** tình huống. Một cách sắp xếp rất nhanh với vài triệu số nguyên có thể không phù hợp khi mỗi phần tử là một bản ghi lớn; một cách chỉ cần ít bộ nhớ có thể làm đảo thứ tự các bản ghi cùng khóa; và một thuật toán có độ phức tạp trung bình tốt vẫn có thể gặp đầu vào gây thời gian xấu nhất rất cao.

Để lựa chọn đúng, phải bắt đầu từ **đặc tả đầu ra** và **đặc điểm dữ liệu**, sau đó đánh đổi giữa thời gian, bộ nhớ bổ sung, tính ổn định (*stability*) và chi phí thao tác thực tế. Bài học tập trung vào **nhóm sắp xếp dựa trên so sánh**: insertion sort, selection sort, merge sort, heap sort, quicksort cùng các biến thể kết hợp. Counting sort hay radix sort là các kỹ thuật không hoàn toàn dựa trên phép so sánh; chúng chỉ nên được cân nhắc khi miền khóa và giả thiết dữ liệu phù hợp.

## 1. Trước khi chọn thuật toán: xác định yêu cầu chính xác

Giả sử có n phần tử và một phép so sánh khóa. Một kết quả sắp xếp đúng thường phải thỏa **hai điều kiện**:

1. Dãy đầu ra có thứ tự không giảm theo phép so sánh: với mọi i từ 1 đến n−1, `compare(a[i-1], a[i]) <= 0`.
2. Dãy đầu ra là **một hoán vị của đầu vào**: không mất, không thêm và không tự sửa các phần tử; số lần xuất hiện của mỗi phần tử được bảo toàn.

Nếu đề bài yêu cầu **ổn định**, phải thỏa thêm:

3. Với hai phần tử xuất hiện lần lượt ở vị trí i < j và **được comparator xem là bằng nhau** (`compare(x, y) == 0`), phần tử x vẫn đứng trước y trong đầu ra.

Điều kiện thứ ba quan trọng khi sắp xếp **bản ghi có danh tính**, chẳng hạn học sinh cùng điểm, giao dịch cùng ngày hoặc sự kiện cùng mức ưu tiên. Hai số nguyên giống nhau trong một mảng `int[]` nhìn không phân biệt được; nhưng hai đối tượng cùng điểm có thể mang mã và thông tin khác nhau.

Trước khi quyết định cấu trúc và thuật toán, hãy xác định:

- **Kích thước n:** vài chục, vài nghìn, hàng triệu hay vượt quá bộ nhớ RAM?
- **Kiểu phần tử:** giá trị primitive nhỏ, object lớn, chuỗi dài, cấu trúc có con trỏ? Cần sắp xếp dữ liệu hay chỉ sắp xếp các **tham chiếu/chỉ số** trỏ tới dữ liệu?
- **Đặc điểm thứ tự:** ngẫu nhiên, đã sắp, gần sắp, đảo ngược, gồm nhiều đoạn đã sắp sẵn, hay có rất nhiều khóa trùng?
- **Yêu cầu ổn định:** hai bản ghi bằng khóa có bắt buộc giữ thứ tự ban đầu không?
- **Giới hạn bộ nhớ phụ:** có thể cấp thêm mảng O(n) hay bắt buộc gần O(1)?
- **Mục tiêu thời gian:** ưu tiên hiệu năng trung bình, hay cần bảo đảm cận xấu nhất O(n log n)?
- **Hệ thống thực tế:** bộ nhớ đệm, cấp phát object, GC, đọc/ghi đĩa, tính đồng thời và chi phí comparator.
- **Phạm vi kết quả:** cần sắp xếp **toàn bộ**, chỉ cần k giá trị tốt nhất, hay chỉ cần thứ hạng của một phần tử?

Một đặc tả chỉ nói “sắp xếp tăng dần” chưa đủ để kết luận rằng dùng quicksort, merge sort hay heap sort là tối ưu về mọi tiêu chí.

## 2. Tính ổn định: điều kiện thay đổi lựa chọn

Xét các bản ghi có dạng `(điểm, mã)`:

~~~text
Đầu vào:
[(8, A), (6, B), (8, C), (6, D)]

Sắp theo điểm tăng dần và GIỮ thứ tự khi cùng điểm:
[(6, B), (6, D), (8, A), (8, C)]
~~~

B đứng trước D ở nhóm điểm 6; A đứng trước C ở nhóm điểm 8. Đó là sắp xếp **ổn định**. Một thuật toán không ổn định có thể cho:

~~~text
[(6, D), (6, B), (8, C), (8, A)]
~~~

Dãy vẫn tăng dần theo điểm và vẫn bảo toàn các bản ghi, nhưng **vi phạm yêu cầu giữ thứ tự**.

### Khi nào ổn định thực sự cần thiết?

- **Sắp nhiều khóa theo từng lượt.** Ví dụ đầu tiên sắp theo tên, sau đó sắp ổn định theo phòng ban: các tên trong cùng phòng ban vẫn giữ thứ tự đã sắp ở lượt trước. Nếu dùng một comparator đầy đủ `(phòng ban, tên)`, không nhất thiết cần chia thành hai lượt, nhưng thứ tự khi hai khóa chính/phụ bằng nhau vẫn tùy vào yêu cầu.
- **Hiển thị danh sách người dùng.** Khi nhiều bản ghi có cùng mức ưu tiên, có thể muốn giữ thứ tự xuất hiện/đăng ký để kết quả ít nhảy vị trí.
- **Dữ liệu sự kiện.** Các sự kiện cùng dấu thời gian cần giữ thứ tự nguồn để bảo toàn một quy ước nghiệp vụ.
- **Bản ghi có khóa phụ ngầm định.** Khi sắp theo một thuộc tính, những thuộc tính khác không thể thay thế cho thứ tự ban đầu nếu yêu cầu là “giữ thứ tự gốc”.

**Ổn định không phải là sắp theo khóa phụ.** Nếu comparator chỉ so điểm, hai bản ghi bằng điểm là ngang nhau; thuật toán ổn định giữ nguyên thứ tự gốc. Nếu comparator so cả điểm rồi mã, thứ tự theo mã là **quy tắc mới của comparator**, không phải tính ổn định. Hai lựa chọn có thể trùng đầu ra ở vài ví dụ, nhưng ngữ nghĩa khác nhau.

### Phản ví dụ ngắn cho selection sort dùng swap

Với các bản ghi [(2,A), (2,B), (1,C)], selection sort hoán đổi phần tử nhỏ nhất (1,C) với vị trí đầu (2,A), nhận [(1,C), (2,B), (2,A)]. Thứ tự A rồi B bị đảo thành B rồi A, nên phiên bản **đổi chỗ trực tiếp** không ổn định.

Một thuật toán ổn định điển hình trên mảng là **merge sort** nếu bước trộn ưu tiên phần tử từ nửa trái khi hai khóa bằng nhau. **Insertion sort** ổn định nếu chỉ dịch phần tử đứng trước khi khóa của nó **lớn hơn hẳn** khóa đang chèn; không dịch phần tử ngang khóa.

## 3. Bảng so sánh các lựa chọn thường gặp

Các cận dưới đây nói về những cách triển khai **phổ biến trên mảng**, giả sử phép so sánh tốn O(1). Nếu comparator rất đắt (ví dụ so chuỗi dài), thời gian thực còn phải tính chi phí comparator. Không nên coi bảng là cam kết cho mọi phiên bản hay mọi thư viện.

| Thuật toán | Thời gian tốt nhất | Trung bình / kỳ vọng | Xấu nhất | Bộ nhớ phụ điển hình | Ổn định? |
| --- | --- | --- | --- | --- | --- |
| Selection sort đổi chỗ | Θ(n²) | Θ(n²) | Θ(n²) | O(1) | Không |
| Insertion sort (dịch phần tử) | Θ(n) | Θ(n²) trên dữ liệu ngẫu nhiên | Θ(n²) | O(1) | Có nếu cài đúng |
| Bubble sort có cờ dừng | Θ(n) | Θ(n²) | Θ(n²) | O(1) | Có nếu chỉ swap khi > |
| Merge sort trên mảng | Θ(n log n) với bản chia đôi chuẩn | Θ(n log n) | Θ(n log n) | O(n) mảng đệm | Có nếu trộn đúng |
| Heap sort trên mảng | Θ(n log n) | Θ(n log n) | Θ(n log n) | O(1) với heap tại chỗ | Không |
| Quick sort thông dụng | Θ(n log n) | Θ(n log n) kỳ vọng với pivot thích hợp | Θ(n²) nếu phân hoạch mất cân bằng | O(log n) stack kỳ vọng; có thể O(n) xấu nhất | Thường không |
| TimSort / sắp xếp thích ứng theo run | O(n) khi dữ liệu thuận lợi | O(n log n) | O(n log n) | Có thể tới O(n) | Có |

**Giải thích những chỗ dễ gây nhầm:**

- **Big-O khác thời gian chạy thực.** O(n log n) thường phù hợp hơn O(n²) khi n lớn, nhưng một thuật toán có chi phí khởi tạo, cấp phát hoặc comparator cao có thể chậm hơn ở n rất nhỏ.
- **Quicksort có nhiều biến thể.** Cận Θ(n log n) trung bình phụ thuộc cách chọn pivot, cách phân hoạch, đầu vào và mô hình phân tích; bản chọn pivot kém có thể tốn Θ(n²). Dùng ngẫu nhiên hóa, lấy mẫu pivot hoặc chuyển sang heapsort khi đệ quy sâu là những biện pháp phổ biến, nhưng phải nói rõ biến thể nào mới có bảo đảm cụ thể.
- **Heapsort có cận thời gian xấu nhất tốt** và dùng O(1) bộ nhớ phụ trên mảng, nhưng nhìn chung không ổn định và có thể có đặc điểm truy cập bộ nhớ kém thân thiện cache hơn một số thuật toán khác.
- **Merge sort trên mảng** dễ đạt ổn định và cận Θ(n log n) ngay cả khi đầu vào không thuận lợi, đổi lại thường cần mảng đệm O(n).
- **TimSort** khai thác những đoạn đã có thứ tự (*runs*), vì thế có thể nhanh hơn trên dữ liệu gần sắp; nó không có nghĩa là mọi đầu vào đều chỉ cần O(n) thời gian.
- **Selection sort** ít swap (tối đa n−1 lượt swap thực sự) nhưng vẫn phải so sánh Θ(n²) — ít ghi không đồng nghĩa ít tính toán.

Với n = 100.000, selection sort phải thực hiện đúng n(n−1)/2 = **4.999.950.000** phép so sánh giá trị trong bản cài chuẩn. Đây là lý do nó chủ yếu phù hợp để học hoặc xử lý tập rất nhỏ, không phải lựa chọn mặc định cho dữ liệu quy mô lớn.

## 4. Dữ liệu đầu vào quyết định lợi thế của thuật toán

### 4.1. Mảng nhỏ: ưu tiên thuật toán đơn giản, overhead thấp

Với vài phần tử hoặc vài chục phần tử, **insertion sort** rất dễ cài, dùng O(1) bộ nhớ phụ, ổn định và có chi phí thao tác ban đầu nhỏ. Nhiều bộ sắp xếp kết hợp cũng dùng một thuật toán kiểu insertion sort cho các đoạn con nhỏ.

Không có ngưỡng kích thước “n ≤ 32” hay “n ≤ 64” đúng cho mọi máy, mọi loại phần tử và mọi comparator; ngưỡng nên được kiểm chứng trong ngữ cảnh thực tế.

**Selection sort** cũng dễ hiểu, nhưng cùng với việc phải quét toàn bộ suffix ở mỗi lượt, nó khó tận dụng dữ liệu gần sắp. Chọn selection sort khi muốn minh họa bất biến chọn min, cần hạn chế swap hoặc đề bài yêu cầu thuật toán đó; không vì thấy nó đơn giản mà mặc định nhanh nhất với n nhỏ.

### 4.2. Mảng gần sắp: insertion sort và thuật toán thích ứng

Insertion sort lấy phần tử tiếp theo và dịch trái những phần tử **lớn hơn** nó đến khi tìm được vị trí chèn. Nếu mảng đã tăng dần, mỗi phần tử chỉ cần một phép kiểm tra chính và không phải dịch giá trị nào: thời gian Θ(n). Nếu chỉ có ít cặp bị đảo thứ tự, số lần dịch cũng ít.

Gọi **inversion** là một cặp chỉ số i < j nhưng a[i] > a[j]. Trong insertion sort kiểu dịch từng phần tử liền kề, mỗi lần dịch qua một phần tử lớn hơn tương ứng với việc loại một inversion. Với comparator nhất quán, số lần dịch chính xác bằng số inversion theo khóa; số phép so sánh thường cùng bậc **O(n + số inversion)**.

Ví dụ:

~~~text
Ban đầu:        [1, 2, 4, 3, 5]
Chỉ có một inversion: (4, 3)
Chèn 3 trước 4: [1, 2, 3, 4, 5]
~~~

Dữ liệu gần sắp có thể xuất hiện sau khi chỉ một bản ghi đổi vị trí, khi thêm ít phần tử mới vào danh sách đã có thứ tự, hoặc khi dữ liệu gồm nhiều *run* tăng dần. Trong những trường hợp như vậy, thuật toán thích ứng như TimSort đáng được cân nhắc hơn một quicksort đơn giản không nhận diện run.

### 4.3. Mảng đảo ngược hoặc phân bố khó

Với n phần tử phân biệt theo thứ tự giảm dần, insertion sort phải dịch gần n(n−1)/2 lần, khiến thời gian Θ(n²). Quicksort chọn **pivot ở đầu hoặc cuối một cách ngây thơ** cũng có thể chia mảng thành hai phía rất mất cân bằng trên dữ liệu đã sắp/đảo, dẫn tới Θ(n²).

Nếu đầu vào có thể bị chủ động lựa chọn để gây chậm hoặc giới hạn thời gian xấu nhất nghiêm ngặt, nên cân nhắc:
- Merge sort hoặc heap sort với cận O(n log n) cho phiên bản chuẩn.
- **Introsort:** bắt đầu giống quicksort nhưng chuyển sang heap sort khi đệ quy quá sâu; thường thêm insertion sort cho đoạn nhỏ. Cần phân biệt một thư viện cụ thể có sử dụng introsort hay không, không suy đoán từ tên API.
- Một bộ sắp xếp thư viện có triển khai được kiểm thử kỹ thay vì viết quicksort chốt pivot đơn giản.

### 4.4. Nhiều giá trị trùng

Nếu khóa chỉ có một vài giá trị, đặc biệt với các đối tượng có cùng khóa, hãy hỏi:
- Có yêu cầu **ổn định** giữa các bản ghi cùng khóa không?
- Comparator xem hai giá trị là ngang nhau trong những trường hợp nào?
- Thuật toán phân hoạch có xử lý hiệu quả phần tử bằng pivot không?

Quicksort phân hoạch hai phía đơn giản có thể không hiệu quả với nhiều phần tử bằng pivot, tùy cách cài. **Phân hoạch ba phía (< pivot, = pivot, > pivot)** là hướng xử lý hữu ích. Nó không tự làm quicksort trở thành ổn định; các phép đổi chỗ vẫn có thể đảo bản ghi bằng khóa.

Nếu chỉ có các **khóa nguyên trong miền nhỏ đã biết**, có thể cân nhắc counting sort hoặc radix sort như lựa chọn ngoài nhóm so sánh, nhưng chúng có tiền điều kiện, bộ nhớ và yêu cầu ổn định riêng; không thể áp dụng nguyên xi cho mọi comparator.

### 4.5. Bản ghi lớn, comparator đắt

Sắp xếp một mảng tham chiếu tới object khác với liên tục sao chép cả bản ghi lớn. Nếu bản ghi nằm trên đĩa hay có cấu trúc phức tạp, có thể:
1. Sắp xếp **chỉ số hoặc tham chiếu** theo khóa thay vì di chuyển toàn bộ dữ liệu.
2. Tính trước khóa đắt tiền khi hợp lý (ví dụ khóa chuẩn hóa) thay vì tính lại ở mỗi lần compare.
3. Tạo comparator nhất quán, không phụ thuộc trạng thái dễ thay đổi trong lúc sắp.
4. Ưu tiên thuật toán ít phải so sánh khóa đắt, nhưng vẫn phải xét chi phí ghi và bộ nhớ phụ.

Cần đo hiệu năng với dữ liệu thực tế: cùng số phép so sánh, chi phí truy cập và cách biểu diễn dữ liệu có thể làm thời gian chạy khác biệt đáng kể.

## 5. Bộ nhớ: O(1) không có nghĩa là không có bất kỳ chi phí nào

Phân tích bộ nhớ nên tách:

- **Bộ nhớ chứa đầu vào:** O(n) để giữ các phần tử hoặc tham chiếu, có mặt trước khi sắp xếp.
- **Bộ nhớ phụ của thuật toán:** mảng đệm, biến tạm, ngăn xếp đệ quy, vùng làm việc.
- **Bộ nhớ đối tượng/cấu trúc dữ liệu:** overhead của object, mảng tham chiếu, boxing/unboxing, cache tạm; có thể lớn hơn nhiều so với kích thước khóa.

### In-place và stack

**Selection sort, insertion sort và heapsort** đều có thể cài trên mảng với O(1) bộ nhớ phụ. Nhưng **quicksort đệ quy** thường cần stack O(log n) trung bình/kỳ vọng khi các phân hoạch cân bằng và có thể lên tới O(n) khi phân hoạch lệch nặng, trừ khi phiên bản có kỹ thuật bảo đảm khác.

**Merge sort trên mảng** có thể cần mảng đệm O(n) để trộn hai nửa một cách ổn định; bản đệ quy còn có stack O(log n). Nếu yêu cầu “bộ nhớ phụ không vượt vài kilobyte”, không thể bỏ qua mảng đệm này chỉ vì thời gian của merge sort tốt.

### Tình huống thực tế

Mảng 10 triệu số nguyên 32-bit dùng xấp xỉ **40 MB** chỉ cho phần dữ liệu int (chưa tính overhead mảng), còn việc dùng đối tượng wrapper `Integer` và mảng tham chiếu có thể tiêu tốn nhiều hơn, tùy runtime và cách khởi tạo. Một mảng đệm có cùng số phần tử có thể làm tăng đáng kể mức sử dụng RAM.

Nếu không đủ chỗ cho mảng phụ cùng kích thước n, các lựa chọn gồm:
- Dùng primitive arrays thay cho object nếu dữ liệu cho phép.
- Chọn heap sort tại chỗ khi cần cận O(n log n) với ít bộ nhớ phụ và không cần ổn định.
- Sắp xếp **chỉ số** hoặc dữ liệu có thể lưu gọn hơn nếu bản ghi lớn.
- Khi dữ liệu vượt RAM, chuyển sang **external sorting** thay vì cố đưa toàn bộ vào bộ nhớ.

**Đừng tuyên bố một API thư viện dùng O(1) bộ nhớ chỉ vì nó nhận mảng và trả void.** Chữ ký hàm không cho biết bộ nhớ tạm bên trong.

## 6. Tình huống cần ổn định và nhiều khóa

Nếu cần giữ thứ tự của các bản ghi có khóa bằng nhau, hãy chọn một thuật toán/cách cài **có bảo đảm ổn định**. Trên mảng đối tượng, merge sort và TimSort là những lựa chọn tiêu biểu. Insertion sort cũng ổn định ở bản cài đúng, nhất là với dãy nhỏ.

### Ví dụ: sắp hai mức ưu tiên

Có các bản ghi (tên, phòng ban, thời điểm đến), muốn xếp theo:
1. Phòng ban tăng dần.
2. Trong cùng phòng ban, giữ thứ tự đến ban đầu.

Nếu dữ liệu đầu vào đã được lưu theo thời điểm đến, có thể **sắp ổn định chỉ theo phòng ban** để giữ thứ tự đến. Nhưng nếu dữ liệu ban đầu **không còn theo thời điểm đến**, tính ổn định đơn thuần không tự sửa thứ tự; phải đưa thời điểm đến vào comparator hoặc sắp chuẩn hóa trước.

Nếu muốn hai khóa `(phòng ban, tên)`, có hai cách:
- Comparator ghép khóa trực tiếp: so phòng ban, nếu bằng thì so tên.
- Sắp ổn định theo **khóa phụ trước**, rồi sắp ổn định theo **khóa chính sau**. Lần sau giữ thứ tự khóa phụ trong các nhóm có khóa chính bằng nhau.

Thứ tự **phụ trước, chính sau** là điều kiện quan trọng. Làm ngược có thể phá hiệu ứng mong muốn. Hai lần sắp còn có thêm chi phí, nên comparator ghép khóa trực tiếp thường đơn giản hơn nếu không cần tận dụng kết quả sắp trung gian.

### Tại sao chỉ “thêm chỉ số gốc vào khóa” là một đánh đổi?

Khi sắp theo `(khóa chính, chỉ số gốc)`, ngay cả thuật toán vốn không ổn định cũng có thể tạo thứ tự như một phép sắp ổn định về mặt kết quả, vì các khóa ghép là duy nhất. Nhưng lúc ấy:
- Comparator đã đổi ngữ nghĩa từ “chỉ theo khóa chính” thành “khóa chính rồi thứ tự gốc”.
- Cần lưu hoặc suy ra chỉ số gốc một cách đúng đắn; có thể làm tăng bộ nhớ.
- Nếu người dùng mong đợi giữ thứ tự **hiện tại** sau những lần sắp trước, chỉ số gốc của dữ liệu từ thời điểm nào phải được xác định.

Cách này không chứng minh thuật toán nền tự nó có tính ổn định.

## 7. Java 17: API sắp xếp phù hợp với kiểu dữ liệu

Trong Java, hãy ưu tiên API chuẩn khi mục tiêu là **giải quyết bài toán thực tế** thay vì tự viết thuật toán để học.

### 7.1. Mảng kiểu nguyên thủy

`Arrays.sort(int[])`, `Arrays.sort(long[])`, `Arrays.sort(double[])`... sắp xếp trực tiếp mảng theo thứ tự tự nhiên tương ứng của từng kiểu. Trên JDK 17, họ thuật toán sắp xếp mảng primitive được tối ưu theo loại dữ liệu và chi tiết triển khai; ví dụ có các kỹ thuật quicksort hai pivot. **Không nên gán một hợp đồng ổn định cho `int[]`**: hai giá trị int bằng nhau vốn không mang thông tin danh tính hay thứ tự phụ cần giữ.

Một vài lưu ý:
- `Arrays.sort(int[])` sửa trực tiếp mảng đầu vào và không trả một mảng mới.
- Nếu thông tin về thứ tự nguồn nằm trong một mảng dữ liệu **song song**, chỉ sắp `int[]` có thể làm mất quan hệ ghép cặp với bản ghi khác. Nên sắp đối tượng chứa đủ trường hoặc một mảng chỉ số rồi áp dụng cùng hoán vị.
- Không thể suy ra thuật toán thư viện luôn là quicksort cổ điển, heapsort hoặc hoàn toàn in-place chỉ từ tên `sort`. Cần đọc hợp đồng và, khi cần, tài liệu triển khai đúng phiên bản JDK.

### 7.2. Mảng đối tượng

`Arrays.sort(T[], Comparator)` có bảo đảm **stable sort**: các phần tử mà comparator đánh giá bằng nhau không bị đảo thứ tự tương đối. Với sắp xếp theo thứ tự tự nhiên của đối tượng có thể so sánh, `Arrays.sort(Object[])` cũng bảo đảm ổn định theo hợp đồng.

Trong Java 17, cách triển khai sắp xếp đối tượng thường tận dụng các run đã có thứ tự (dòng TimSort). Đó là chi tiết triển khai có thể thay đổi theo bản JDK; **hợp đồng ổn định** mới là điều quan trọng để phụ thuộc vào khi viết chương trình.

Các API khác:
- `List.sort(comparator)` thực hiện sắp xếp ổn định theo hợp đồng của List; `Collections.sort(list, comparator)` cũng dùng cách sắp xếp ổn định.
- Khi dùng `Comparator.comparingInt`, `thenComparing`, `Comparator.naturalOrder()`, hãy bảo đảm comparator tuân thủ quan hệ thứ tự nhất quán.
- Tránh comparator kiểu `(a, b) -> a.score() - b.score()` vì phép trừ có thể tràn int. Dùng `Integer.compare` hoặc `Comparator.comparingInt`.
- Nếu giá trị khóa có thể là null, phải định nghĩa chính sách trước, ví dụ `Comparator.nullsFirst(...)`; không giả định mọi comparator tự xử lý null.

**Ghi nhớ:** dùng một thuật toán ổn định không thể sửa được comparator sai. Nếu comparator không bắc cầu, đọc trạng thái thay đổi liên tục, hoặc cho kết quả mâu thuẫn giữa các lần gọi, việc sắp xếp có thể cho kết quả không đáng tin hoặc bị từ chối trong một số cách triển khai.

## 8. Ví dụ Java 17 hoàn chỉnh: ba quyết định khác nhau

Chương trình dưới đây minh họa:

1. Sắp một mảng **primitive int[]** bằng `Arrays.sort`.
2. Sắp **bản ghi có danh tính** theo mức ưu tiên nhưng vẫn giữ thứ tự gốc khi bằng khóa, nhờ stable sort của `Arrays.sort(T[], Comparator)`.
3. Dùng **insertion sort** trên một mảng gần như đã có thứ tự, đồng thời đếm số lần so sánh và dịch phần tử.

~~~java
import java.util.Arrays;
import java.util.Comparator;
import java.util.StringJoiner;

public class SortingChoiceDemo {
    record Task(String id, int priority) {}
    record Stats(long comparisons, long shifts) {}

    static Stats insertionSort(int[] a) {
        long comparisons = 0;
        long shifts = 0;

        for (int i = 1; i < a.length; i++) {
            int key = a[i];
            int j = i - 1;

            while (j >= 0) {
                comparisons++;
                if (a[j] <= key) {
                    break;
                }

                a[j + 1] = a[j];
                shifts++;
                j--;
            }
            a[j + 1] = key;
        }
        return new Stats(comparisons, shifts);
    }

    static String describe(Task[] tasks) {
        StringJoiner joiner = new StringJoiner(", ");
        for (Task task : tasks) {
            joiner.add(task.id() + ":" + task.priority());
        }
        return joiner.toString();
    }

    public static void main(String[] args) {
        int[] numbers = {5, 1, 4, 1, 3};
        Arrays.sort(numbers);
        System.out.println("primitive=" + Arrays.toString(numbers));

        Task[] tasks = {
            new Task("A", 2),
            new Task("B", 1),
            new Task("C", 2),
            new Task("D", 1)
        };

        Arrays.sort(tasks, Comparator.comparingInt(Task::priority));
        System.out.println("stable=" + describe(tasks));

        int[] nearlySorted = {1, 2, 4, 3, 5};
        Stats stats = insertionSort(nearlySorted);
        System.out.println("insertion=" + Arrays.toString(nearlySorted)
                + " comparisons=" + stats.comparisons()
                + " shifts=" + stats.shifts());
    }
}
~~~

Lưu thành tệp **SortingChoiceDemo.java** và chạy bằng **JDK 17 trở lên**:

~~~bash
javac SortingChoiceDemo.java
java SortingChoiceDemo
~~~

Đầu ra chính xác:

~~~text
primitive=[1, 1, 3, 4, 5]
stable=B:1, D:1, A:2, C:2
insertion=[1, 2, 3, 4, 5] comparisons=5 shifts=1
~~~

**Giải thích:**
- Mảng primitive đã được sắp theo giá trị tăng dần, và hai số 1 vẫn hiện diện; kết quả không làm mất phần tử trùng.
- Comparator của `Task` chỉ xét `priority`. B và D cùng ưu tiên 1 nên **B còn trước D**; A và C cùng ưu tiên 2 nên **A còn trước C**, đúng tính ổn định của API sắp object.
- Mảng gần sắp chỉ có một inversion là (4, 3). Insertion sort cần **1 lần dịch** (dịch 4 sang phải). Bốn lượt ngoài thực hiện tổng **5 phép so sánh khóa**: lần lượt 1, 1, 2, 1. Đây là số đếm của **đoạn mã cụ thể**, không phải một cận chung cho mọi insertion sort.
- Với insertion sort, điều kiện **`a[j] <= key` thì dừng** tương đương chỉ dịch khi `a[j] > key`. Bởi không dịch qua phần tử bằng nhau, phiên bản dành cho bản ghi nếu viết tương tự sẽ bảo toàn thứ tự ngang khóa.
- `record` là tính năng có trong Java 17; hai record ở đây giữ dữ liệu bất biến sau khi tạo. Không dùng bộ đếm int cho số lần so sánh tích lũy để tránh tràn với các phép kiểm thử lớn.

Mã minh họa chỉ nhận mảng hợp lệ (không null); nếu muốn thiết kế API thư viện, hãy định nghĩa thêm hành vi khi tham số null, chính sách comparator và các điều kiện tiền xử lý.

## 9. Một khung quyết định theo nhu cầu

Có thể bắt đầu theo trình tự sau thay vì cố nhớ thuật toán “nhanh nhất”:

### Bước 1 — Có thật sự cần sắp toàn bộ không?

Nếu chỉ cần:
- **Giá trị nhỏ nhất/lớn nhất:** quét mảng một lần O(n).
- **k phần tử lớn nhất với k ≪ n:** min-heap kích thước k có thể đạt O(n log(k + 1)) thời gian và O(k) bộ nhớ.
- **Phần tử đứng thứ k:** thuật toán chọn như quickselect có thời gian kỳ vọng O(n) trong các mô hình chuẩn nhưng không sắp toàn bộ, cần cân nhắc cận xấu nhất.
- **Nhiều truy vấn thứ tự trên dữ liệu ít thay đổi:** có thể sắp một lần rồi dùng tìm kiếm nhị phân hoặc cấu trúc chỉ mục.

Sắp toàn bộ khi chỉ cần một cực trị có thể là công việc dư thừa.

### Bước 2 — Nếu cần sắp, có yêu cầu ổn định không?

**Có:** ưu tiên API sắp xếp object ổn định, merge sort ổn định hoặc thuật toán thích ứng ổn định. Nếu cần O(1) bộ nhớ và n nhỏ, insertion sort ổn định có thể đủ; với n lớn, phải tính kỹ đánh đổi bộ nhớ.

**Không:** có thêm lựa chọn heapsort/quicksort và sắp primitive trực tiếp. Tuy nhiên “không yêu cầu ổn định” không đồng nghĩa “phải chọn thuật toán không ổn định”; nếu API ổn định đã phù hợp các yêu cầu khác thì vẫn có thể dùng.

### Bước 3 — Bộ nhớ phụ cho phép tới đâu?

- **Có RAM cho bộ đệm O(n):** merge sort/TimSort ổn định trên object là lựa chọn hợp lý nếu cần thứ tự nguồn.
- **Bắt buộc O(1) bộ nhớ phụ và n lớn:** heapsort tại chỗ có cận thời gian xấu nhất O(n log n); tính ổn định phải được đánh đổi hoặc giải quyết riêng.
- **Đầu vào lớn hơn RAM:** xem xét external merge sort; cần sắp các phần có thể chứa trong RAM rồi trộn bằng đĩa/bộ đệm.

### Bước 4 — Dữ liệu có đặc điểm gì?

- **Rất nhỏ/gần sắp:** cân nhắc insertion sort hoặc thuật toán thích ứng.
- **Rất nhiều khóa trùng:** chú ý ổn định và hiệu quả xử lý khóa bằng nhau; tránh quicksort phân hoạch tệ.
- **Đã có nhiều run:** thuật toán khai thác run có thể có lợi.
- **Dữ liệu lớn, không có đặc điểm đặc biệt:** ưu tiên bộ sắp xếp thư viện đã được tối ưu và kiểm thử cho đúng kiểu phần tử.
- **Comparator đắt:** cân nhắc tính trước khóa hoặc cách biểu diễn ít gọi comparator hơn.

### Bước 5 — Cần bảo đảm cận xấu nhất?

Nếu dữ liệu có thể mang tính đối kháng, hoặc thời gian vượt ngưỡng gây hậu quả nghiêm trọng, phải xem **worst case**, không chỉ trung bình/kỳ vọng. Merge sort và heap sort có cận O(n log n) với các cài đặt chuẩn; quicksort thuần có thể O(n²) nhưng có các biến thể khắc phục.

### Bước 6 — Xác minh đúng rồi mới tối ưu

Với mỗi phương án, kiểm tra **thứ tự**, **bảo toàn đa tập**, **tính ổn định** khi cần, **bộ nhớ đỉnh**, **thời gian trên dữ liệu mục tiêu**, và **các trường hợp biên**. Sử dụng dữ liệu đại diện chứ không chỉ benchmark trên một mảng ngẫu nhiên.

## 10. Một số kịch bản lựa chọn cụ thể

| Kịch bản | Hướng lựa chọn | Điều không được quên |
| --- | --- | --- |
| 30 số nguyên, gần như đã tăng | Insertion sort hoặc API chuẩn | Mảng nhỏ; không cần tự viết nếu không có lý do |
| 2 triệu `int` cần sắp tăng, không có metadata đi kèm | `Arrays.sort(int[])` | Dữ liệu primitive; đo RAM và thời gian thực |
| Bản ghi học sinh cần giữ thứ tự khi điểm bằng nhau | Stable sort trên object/merge sort | So theo điểm, giữ thứ tự gốc trong nhóm bằng điểm |
| Mảng lớn, yêu cầu thời gian xấu nhất O(n log n) và gần O(1) bộ nhớ phụ | Heapsort tại chỗ | Không ổn định; hằng số và đặc điểm cache có thể bất lợi |
| Nhiều đoạn đã có thứ tự, mảng object | Thuật toán thích ứng như TimSort | Đánh giá run thực tế và bộ nhớ đệm |
| Mảng có rất nhiều phần tử trùng | Thuật toán chuẩn có xử lý tốt, hoặc phân hoạch ba phía nếu tự viết quicksort | Không suy ra ổn định từ phân hoạch ba phía |
| File dữ liệu quá lớn để nạp toàn bộ RAM | External merge sort | I/O, fan-in, bộ đệm, file tạm và thứ tự hòa |
| Chỉ cần 100 giá trị lớn nhất trong hàng triệu số | Min-heap 100 phần tử | Không nhất thiết phải sắp toàn bộ |

### Ví dụ quyết định có xung đột

Một dịch vụ cần sắp 5 triệu bản ghi theo điểm, **bắt buộc ổn định**, nhưng chỉ cho vài MB bộ nhớ phụ. Lựa chọn “merge sort chuẩn trên mảng” có cận thời gian tốt và ổn định nhưng thường cần O(n) bộ nhớ phụ; heapsort tại chỗ lại không ổn định. Không có quyền bỏ một trong hai ràng buộc chỉ vì thuật toán quen thuộc.

Các hướng cần đánh giá là: có thể tăng ngân sách bộ nhớ không, có thể dùng một cấu trúc dữ liệu chỉ chứa tham chiếu/offset không, có thể chuyển sang chiến lược lưu đĩa không, hoặc có thuật toán ổn định tại chỗ phức tạp hơn đáp ứng được các giới hạn thực tế không. **Nói rõ sự xung đột** là một phần của thiết kế đúng.

## 11. Sắp xếp dữ liệu vượt RAM: vì sao phải xét I/O?

Khi dữ liệu lớn hơn bộ nhớ khả dụng, một thuật toán trên RAM có O(n log n) chưa phản ánh chi phí đọc/ghi đĩa. Phương pháp phổ biến là **external merge sort**:

1. Đọc một lượng bản ghi vừa RAM thành một **chunk**.
2. Sắp chunk trong RAM bằng thuật toán thích hợp.
3. Ghi chunk đã sắp ra file tạm dưới dạng một **run**.
4. Đọc đầu mỗi run và thực hiện **k-way merge** bằng cấu trúc chọn phần tử nhỏ nhất (ví dụ min-heap), chỉ giữ một lượng dữ liệu/bộ đệm nhỏ của mỗi run.
5. Ghi dãy đã trộn ra kết quả; có thể cần nhiều lượt trộn nếu số run vượt mức có thể mở đồng thời.

Mục tiêu là truy cập tuần tự theo khối, giảm số lượt đọc/ghi và tránh truy cập ngẫu nhiên đắt đỏ. Chọn kích thước chunk, số run trộn cùng lúc, số file mở và bộ đệm dựa trên RAM và thiết bị lưu trữ.

Nếu yêu cầu **ổn định toàn cục**, cần duy trì cả **thứ tự gốc** khi nhiều bản ghi bằng khóa đến từ các run khác nhau. Một cách là dùng khóa phụ `(thứ tự run gốc, vị trí trong run)` cho các phần tử cùng khóa và sắp ổn định ngay từ lúc tạo run; hoặc lưu số thứ tự gốc cho từng bản ghi. Chỉ dùng heap so khóa chính rồi không có quy tắc hòa sẽ **không tự bảo toàn** thứ tự gốc.

## 12. Kiểm tra độ đúng và đo hiệu năng có ý nghĩa

### 12.1. Bộ kiểm thử đúng

Các dạng đầu vào nên có:

- **Rỗng và một phần tử:** [] và [5].
- **Đã tăng:** [1,2,3,4]; **đảo ngược:** [4,3,2,1].
- **Nhiều khóa trùng:** [2,2,1,1]; tất cả bằng nhau [7,7,7].
- **Âm và số cực trị:** [Integer.MAX_VALUE, 0, Integer.MIN_VALUE].
- **Gần sắp:** [1,2,4,3,5]; nhiều run tăng được ghép nối.
- **Phân bố lệch:** nhiều giá trị giống nhau và vài ngoại lệ.
- **Bản ghi có cùng khóa:** kiểm tra danh tính và thứ tự gốc riêng, không chỉ các khóa đã sắp.

Để kiểm tra một thuật toán tự cài, tạo một bản sao dữ liệu, sắp bằng một API chuẩn phù hợp rồi so đầu ra **và bảo toàn bội số**. Nếu yêu cầu ổn định, gắn ID/thứ tự nguồn để kiểm tra từng nhóm khóa bằng nhau vẫn đúng thứ tự. So với thư viện là một **oracle thử nghiệm**, nhưng vẫn cần hiểu bất biến để chứng minh tính đúng cho mọi đầu vào hợp lệ.

### 12.2. Đo benchmark

Đo hiệu năng Java cần tính tới **JIT compilation, warmup, GC, cấp phát, cache và nhiễu hệ thống**. Nếu so sánh nghiêm túc, nên dùng JMH hoặc một quy trình benchmark có warmup, nhiều lần chạy và thống kê, thay vì chỉ đo một lần bằng `System.nanoTime()`.

Đặc biệt:
- Cấp **bản sao dữ liệu tương đương** cho mỗi lần chạy. Nếu thuật toán A sắp xếp đầu vào trước, thuật toán B nhận một mảng đã sắp sẽ không còn phép so sánh công bằng.
- Dùng nhiều phân bố: ngẫu nhiên, gần sắp, đảo ngược, nhiều khóa trùng, dữ liệu thực.
- Phân biệt thời gian **tạo/đọc dữ liệu**, **tính khóa**, **sắp xếp**, **sao chép đầu vào**, và **xuất kết quả**; đo đúng thứ muốn tối ưu.
- Theo dõi **bộ nhớ đỉnh** và hoạt động GC nếu có giới hạn RAM.
- Không kết luận từ một kích thước n hoặc một hệ máy rồi áp dụng cho mọi môi trường.

Kết quả benchmark hỗ trợ chọn triển khai, còn phân tích độ phức tạp giúp dự đoán khả năng mở rộng và cận xấu nhất.

## 13. Sai lầm phổ biến khi chọn thuật toán

**“O(n log n) luôn nhanh hơn O(n²).”** Sai ở n nhỏ hoặc trên những dữ liệu đặc thù; nhưng khi n lớn, độ phức tạp vẫn là căn cứ rất quan trọng. Cần xét hằng số, comparator, cache và phân bố.

**“Quicksort luôn O(n log n).”** Quicksort thuần có trường hợp xấu nhất Θ(n²). Kỳ vọng O(n log n) cần giả thiết về pivot hoặc phân bố và không thay thế cam kết cận xấu nhất.

**“Sắp tăng dần là đủ.”** Nếu các bản ghi cùng khóa cần giữ thứ tự, kết quả tăng theo khóa nhưng đảo thứ tự bản ghi vẫn sai đặc tả.

**“Merge sort luôn dùng O(1) bộ nhớ.”** Bản merge sort chuẩn trên mảng thường cần vùng đệm O(n); có các biến thể khác nhưng phải phân tích riêng.

**“In-place có nghĩa là không cần RAM.”** Mảng đầu vào vẫn cần bộ nhớ; ngoài ra thuật toán đệ quy có stack và runtime có overhead.

**“Hai giá trị int bằng nhau cũng có thông tin thứ tự gốc tự thân.”** Không. Chỉ khi có bản ghi/metadata gắn kèm mới phát sinh yêu cầu ổn định có thể quan sát được.

**“Cứ dữ liệu gần sắp là selection sort nhanh.”** Số so sánh của selection sort vẫn Θ(n²). Insertion sort mới tận dụng được ít inversion bằng ít phép dịch.

**“Không cần ổn định thì phải dùng thuật toán không ổn định.”** Không đúng. Tính ổn định là một bảo đảm bổ sung; nếu API ổn định phù hợp về thời gian và bộ nhớ, vẫn có thể dùng.

**“Comparator lấy a − b là cách nhanh để so int.”** Phép trừ có thể tràn số; sử dụng `Integer.compare` hoặc các builder comparator của Java.

**“Dùng một benchmark trên mảng ngẫu nhiên là đủ.”** Sai: nhiều thuật toán nhạy với dữ liệu đã sắp, khóa trùng, phân bố, chi phí comparator và bộ nhớ.

**“Sort chỉ có một nghĩa là thứ tự tăng.”** Đặc tả có thể cần giảm dần, nhiều khóa, ổn định, xử lý null, định dạng theo locale hoặc thứ tự tùy chỉnh. Cần định nghĩa comparator và hậu điều kiện chính xác.

## 14. Câu hỏi tự luyện và đáp án định hướng

**Bài 1 — chọn thuật toán theo độ gần sắp.** Mảng gồm 20 phần tử, chỉ có một cặp liền kề bị đảo. So sánh insertion sort với selection sort.

*Định hướng:* Insertion sort chỉ cần rất ít lần dịch; số phép so sánh thường gần tuyến tính. Selection sort chuẩn vẫn so sánh chính xác 20×19/2 = **190** lần, dù không có nhiều swap.

**Bài 2 — tính ổn định.** Cho [(3,A),(1,B),(3,C),(1,D)], yêu cầu sắp theo số tăng và giữ thứ tự ban đầu nếu cùng số. Kết quả cần là gì?

*Đáp án:* [(1,B),(1,D),(3,A),(3,C)]. Một kết quả [(1,D),(1,B),(3,A),(3,C)] vẫn tăng theo số nhưng không ổn định.

**Bài 3 — bộ nhớ.** Có 2 triệu phần tử và không được phép cấp mảng phụ kích thước n. Bài yêu cầu cận xấu nhất O(n log n), không yêu cầu ổn định. Thuật toán nào đáng cân nhắc?

*Đáp án:* Heapsort tại chỗ phù hợp về cận thời gian và O(1) bộ nhớ phụ. Cần đánh giá thêm yếu tố hiệu năng thực tế và giới hạn bộ nhớ lưu đầu vào.

**Bài 4 — nhiều khóa.** Danh sách đã sắp theo tên. Muốn sắp theo phòng ban, giữ thứ tự tên trong mỗi phòng. Làm thế nào nếu dùng hai lượt sort?

*Đáp án:* Lượt cuối phải là **stable sort theo phòng ban** để giữ thứ tự tên đã thiết lập. Nếu ban đầu chưa sắp tên, hãy sắp ổn định theo tên trước rồi theo phòng ban; hoặc dùng comparator kết hợp (phòng ban, tên).

**Bài 5 — Java.** Vì sao `Arrays.sort(Task[], Comparator.comparingInt(Task::priority))` có thể giữ B trước D khi hai task có cùng mức ưu tiên?

*Đáp án:* Overload sắp mảng object có hợp đồng **stable sort**. Comparator xem B và D là bằng nhau theo priority, nên thứ tự tương đối từ đầu vào được giữ.

**Bài 6 — dữ liệu vượt RAM.** Có 100 GB dữ liệu nhưng chỉ 2 GB RAM. Vì sao không chỉ chọn heapsort vì nó dùng O(1) bộ nhớ phụ?

*Đáp án:* Heapsort tại chỗ giả định dữ liệu có thể truy cập ngẫu nhiên trong bộ nhớ; khi tập dữ liệu nằm trên đĩa, I/O trở thành chi phí chính. External merge sort với các run vừa RAM và trộn theo khối thường phù hợp hơn.

**Bài 7 — chỉ cần top-k.** Có một triệu số, chỉ cần 50 số lớn nhất và không cần sắp thứ tự trong nhóm. Có cần sắp toàn bộ không?

*Đáp án:* Không nhất thiết. Min-heap giữ 50 ứng viên tốn O(n log 50) thời gian và O(50) bộ nhớ bổ sung, thường tiết kiệm hơn so với sắp toàn bộ.

## Ghi nhớ

**Chọn thuật toán sắp xếp** bắt đầu từ đặc tả — dữ liệu nào, thứ tự nào, có cần ổn định hay không — rồi mới cân nhắc thời gian trung bình/xấu nhất, chi phí bộ nhớ và hiệu năng thực tế.

- **Insertion sort:** đơn giản, in-place, ổn định khi cài đúng, hiệu quả cho mảng nhỏ hoặc gần sắp; trường hợp xấu nhất O(n²).
- **Merge sort/TimSort:** phù hợp khi cần ổn định hoặc khai thác các run, thường đổi lấy bộ nhớ phụ.
- **Heapsort:** O(n log n) xấu nhất, O(1) bộ nhớ phụ trên mảng, nhưng không ổn định.
- **Quicksort:** thường nhanh với phân hoạch tốt, nhưng phải xem xét trường hợp xấu nhất và xử lý phần tử trùng.
- **API Java 17:** `Arrays.sort(int[])` tiện cho primitive; `Arrays.sort(Object[], Comparator)` bảo đảm ổn định cho bản ghi.
- **Dữ liệu lớn hơn RAM:** cân nhắc external sorting và chi phí I/O, không chỉ Big-O trên RAM.

Một lựa chọn tốt không chỉ tạo đúng thứ tự, mà còn **bảo toàn dữ liệu, đáp ứng yêu cầu ổn định và giới hạn tài nguyên**, có giải thích rõ ràng về những đánh đổi được chấp nhận.