# Phân tích một thiết kế sai do chọn cấu trúc không phù hợp

Một chương trình có thể **cho ra kết quả đúng với dữ liệu mẫu**, không chứa vòng lặp vô hạn và vẫn thất bại khi đưa vào vận hành. Nguyên nhân đôi khi không nằm ở một dòng mã lỗi: **cấu trúc dữ liệu được chọn không phù hợp với những thao tác xảy ra thường xuyên nhất**. Tối ưu vài câu lệnh, thêm bộ nhớ đệm hoặc thay thuật toán sắp xếp có thể không giải quyết được vấn đề gốc.

Bài học thuộc chương **Kiểm chứng và thực hành** trong module **COMPUTER_SCIENCE_DATA_STRUCTURES**. Mục tiêu của module là xây nền tảng cấu trúc dữ liệu qua mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị; hiểu **bất biến, thao tác và độ phức tạp thời gian–bộ nhớ** để chọn cấu trúc đúng theo bài toán. Ta sẽ thực hiện đúng một quy trình phân tích thiết kế: tái dựng yêu cầu và tải, chỉ ra vì sao phương án cũ sai **về lựa chọn cấu trúc**, chứng minh giới hạn chi phí, thiết kế lại có bất biến, rồi kiểm chứng độc lập bằng mã và các ca biên.

**Ca chính:** một dịch vụ quản lý tác vụ theo hạn xử lý. Thiết kế ban đầu lưu mọi tác vụ trong **một mảng đã sắp theo hạn** vì muốn lấy tác vụ sớm nhất nhanh. Khi lượng thêm mới, hủy và đổi hạn tăng, chương trình chậm nghiêm trọng. Thiết kế lại dùng **bảng băm theo ID + min-heap + cây Fenwick** cho miền hạn rời rạc hữu hạn; cùng một dữ liệu logic được phục vụ bằng **nhiều chỉ mục hỗ trợ những thao tác khác nhau**.

> **Thông điệp trung tâm:** Không chọn cấu trúc dựa trên tên gọi quen thuộc hoặc độ phức tạp của **một** phép toán. Hãy viết rõ bất biến, tất cả thao tác, tần suất, ràng buộc miền khóa, yêu cầu trả kết quả; rồi tính **tổng chi phí theo workload** và thử những trường hợp khiến cấu trúc bất lợi.

## 1. Mục tiêu học tập và tiêu chí đánh giá

Sau bài này, người học cần làm được năm việc:

1. **Phát biểu hợp đồng dữ liệu:** ID, hạn, trường hợp trùng hạn, ý nghĩa biên và thao tác hợp lệ.
2. **Phân tích phương án đang có:** không chỉ nêu Big-O mà giải thích cụ thể thao tác nào buộc dịch mảng, tìm tuyến tính hoặc cập nhật metadata.
3. **Phát hiện bất biến sai và chỗ dễ mất dữ liệu:** đặc biệt sau hủy, đổi hạn, tái sử dụng ID hoặc thay đổi đối tượng chứa khóa.
4. **Đề xuất phương án tương ứng workload:** chỉ mục theo ID cho lookup, cấu trúc ưu tiên cho minimum, cấu trúc tổng hợp có thứ tự cho đếm theo khoảng.
5. **Kiểm chứng giải pháp:** đối chiếu với mô hình đơn giản độc lập, thử tình huống xấu, đo chi phí thực và nêu giả thiết của phân tích.

Một phân tích thiết kế chỉ được xem là đầy đủ khi phân biệt:

- **Correctness:** chương trình trả đúng đáp án theo hợp đồng.
- **Performance:** chương trình tiêu thụ thời gian/bộ nhớ/I/O phù hợp khối lượng thao tác.
- **Maintainability:** việc cập nhật, kiểm thử và thay đổi workload không khiến bất biến trở nên quá khó kiểm soát.

**Một thiết kế chậm không nhất thiết sai kết quả; một thiết kế nhanh nhưng bỏ sót bản ghi không phải là tối ưu hợp lệ.**

## 2. Bối cảnh: dịch vụ điều phối tác vụ theo hạn

Một dịch vụ nhận các tác vụ gửi thông báo, hết hạn đặt chỗ hoặc thực thi công việc theo phút. Mỗi tác vụ có:

\[
\boxed{Task=(id,deadline).}
\]

Trong bản đơn giản:

- **id:** chuỗi không rỗng, duy nhất trong các tác vụ **đang hoạt động**.
- **deadline:** số nguyên phút, thuộc miền \(\{0,1,\ldots,U-1\}\) của một kỳ vận hành đã xác định.
- Nhiều tác vụ **được phép cùng deadline**.
- Nếu hai tác vụ cùng deadline, tác vụ có **ID nhỏ hơn theo thứ tự từ điển** đứng trước. Đây là quy tắc ví dụ, không phải chính sách công bằng chung cho mọi hệ thống.
- Hủy một tác vụ rồi tạo lại cùng ID là hợp lệ; bản cũ phải **không sống lại**.

Ta xét sáu thao tác:

| Thao tác | Hợp đồng | Kết quả kỳ vọng |
| --- | --- | --- |
| **schedule(id,t)** | Thêm ID mới đang chưa tồn tại, hạn hợp lệ | Thành công hoặc báo ID trùng |
| **cancel(id)** | Hủy ID đang hoạt động | True nếu đã hủy, False nếu không tồn tại |
| **reschedule(id,t)** | Đổi hạn của ID đang hoạt động | Giữ đúng một bản ghi cùng ID |
| **get(id)** | Đọc deadline hiện tại | Trả số phút hoặc None |
| **peek_next()** | Xem tác vụ có khóa \((deadline,id)\) nhỏ nhất | Trả tác vụ, không lấy ra |
| **count_range(a,b)** | Đếm deadline nằm trong đoạn đóng \([a,b]\) | Số nguyên, kể cả hai biên |

Thao tác **take_next()** có thể được bổ sung để lấy và xóa tác vụ sớm nhất trong một lần, bảo đảm không trả lại cùng ID nếu không được schedule lại.

### Giả định phạm vi

Miền thời gian \([0,U-1]\) là **chỉ số phút trong một kỳ**, không tự động là thời điểm UTC trên toàn cầu. Ví dụ hệ thống có \(U=10\,080\) phút cho một tuần. Những tác vụ nằm ngoài kỳ phải được **từ chối hoặc chuyển sang chỉ mục kỳ khác**; không được âm thầm cắt deadline về biên để vừa mảng Fenwick.

Không có yêu cầu truy vấn **liệt kê tất cả ID trong một khoảng** ở hợp đồng chính: ta chỉ cần **đếm**. Đó là khác biệt quan trọng vì **đếm \(k\) bản ghi** có thể được hỗ trợ bằng tổng tiền tố, trong khi **xuất k ID** luôn cần ít nhất \(\Omega(k)\) thao tác.

## 3. Workload thực: phương án tối ưu thao tác hiếm trở thành điểm nghẽn

Giả sử một instance có:

| Đại lượng | Giá trị minh họa |
| --- | ---: |
| Số tác vụ đang hoạt động \(n\) | 100.000 |
| schedule/reschedule/cancel | 4.000 thao tác/giây |
| peek_next/take_next | 100 thao tác/giây |
| get(id) | 1.000 thao tác/giây |
| count_range(a,b) | 200 thao tác/giây |
| Miền deadline \(U\) | 10.080 phút |

Đây là **workload giả định để phân tích**, không phải số đo production. Các giới hạn cần quan tâm: độ trễ cập nhật p95/p99, CPU, bộ nhớ, thời gian dừng do garbage collection và tốc độ mở rộng khi n tăng.

Điểm quan trọng nhất không phải chỉ là \(n=100\,000\), mà là **số lần phải thay đổi tập dữ liệu mỗi giây rất lớn**. Nếu mỗi thay đổi cần dịch một phần đáng kể mảng dài n, tổng công việc theo giây sẽ tăng rất nhanh.

Trong một phân tích chính thức, ta nên ký hiệu:

\[
\boxed{
q_{\mathrm{ins}},q_{\mathrm{del}},q_{\mathrm{move}},
q_{\mathrm{id}},q_{\min},q_{\mathrm{count}}
}
\]

cho số lượng từng thao tác trên một đơn vị thời gian. Hai thiết kế có cùng độ phức tạp **worst-case một truy vấn** vẫn có thể khác nhau rất xa về tổng chi phí nếu tần suất thao tác khác nhau.

## 4. Thiết kế ban đầu: một mảng được giữ luôn có thứ tự

Nhóm triển khai chọn **dynamic array** sắp theo cặp khóa:

\[
\boxed{K(task)=(deadline,id).}
\]

Ví dụ:

~~~text
Index  0         1         2         3         4
Task  A@2       B@4       C@4       D@7       E@9
      ^ min -> peek_next() lấy phần tử đầu

Thứ tự: (2,A) < (4,B) < (4,C) < (7,D) < (9,E)
~~~

Nhóm lập luận rằng:

- Mảng **tối ưu cục bộ cho CPU/cache** và đơn giản để serialize.
- Đã sắp thì **peek_next** chỉ cần đọc phần tử đầu, \(O(1)\).
- Tìm vị trí deadline bằng **binary search**, \(O(\log n)\).
- Count khoảng deadline có thể dùng hai lần binary search.

Những nhận định ấy **đúng cho từng bước riêng**, nhưng kết luận “mọi thao tác sẽ nhanh” là sai.

### Bất biến của mảng sắp

Gọi \(A[0],A[1],\ldots,A[n-1]\) là các bản ghi:

\[
\boxed{K(A[i])\le K(A[i+1])
\quad \forall\,0\le i<n-1.}
\]

Mỗi ID đang hoạt động phải xuất hiện **đúng một lần**. Trả min đúng nếu mảng không rỗng và bản ghi tại A[0] là cặp khóa nhỏ nhất.

Hợp đồng yêu cầu **cập nhật** mảng trong khi vẫn giữ bất biến ấy. Đây là chỗ chi phí ẩn xuất hiện.

## 5. Bóc tách chi phí thực của từng thao tác trên mảng sắp

### 5.1. schedule: tìm vị trí nhanh, nhưng dịch phần tử chậm

Giả sử muốn chèn X@5 vào mảng:

~~~text
Trước: [A@2, B@4, C@4, D@7, E@9]

Binary search -> vị trí 3.
Phải dịch D@7, E@9 sang phải một ô:

Sau:   [A@2, B@4, C@4, X@5, D@7, E@9]
~~~

Binary search chỉ tìm được **vị trí chèn**:

\[
\boxed{T_{\mathrm{find\ pos}}=O(\log n).}
\]

Nhưng dynamic array có các phần tử nằm liên tiếp. Nếu chèn giữa mảng, phải dịch các phần tử phía sau:

\[
\boxed{T_{\mathrm{shift}}=O(n).}
\]

Vì thế:

\[
\boxed{T_{\mathrm{schedule}}=O(n)}
\]

trong trường hợp xấu, dù đã sử dụng binary search. Câu “dùng bisect nên insert \(O(\log n)\)” là sai vì bỏ qua **bước di chuyển dữ liệu**.

### 5.2. cancel: tìm ID không được index trực tiếp

Mảng sắp theo \((deadline,id)\), **không sắp theo id riêng**. Nếu cancel("D") chỉ biết ID, binary search theo ID không dùng được. Phải:

1. Duyệt để tìm ID D, trường hợp xấu \(O(n)\).
2. Xóa tại vị trí đã tìm, dịch các phần tử phía sau, trường hợp xấu \(O(n)\).

\[
\boxed{T_{\mathrm{cancel}}=O(n).}
\]

Nếu thêm một **bảng băm ID → vị trí mảng** thì bước tìm có thể \(O(1)\) trung bình, nhưng mỗi lần insert/delete ở giữa làm vị trí **rất nhiều ID khác thay đổi**. Cập nhật đầy đủ bảng vị trí có thể vẫn \(O(n)\); nếu không cập nhật, bảng vị trí trở thành **stale và sai**.

### 5.3. reschedule: thường là một xóa và một chèn

Đổi C từ deadline 4 thành 12:

~~~text
Trước: [A@2, B@4, C@4, D@7, E@9]
Xóa C: [A@2, B@4, D@7, E@9]
Chèn: [A@2, B@4, D@7, E@9, C@12]
~~~

Việc xóa/chèn có thể phải dịch một phần lớn mảng. Nếu chỉ sửa trường **deadline của C tại vị trí cũ** mà không đặt lại theo thứ tự, ta phá bất biến:

~~~text
SAI: [A@2, B@4, C@12, D@7, E@9]
                     ^ 12 > 7
~~~

Khi mảng không còn sắp đúng, **peek_next** hoặc các truy vấn bằng binary search có thể trả **sai kết quả**, không chỉ chậm.

### 5.4. get, peek và count

| Thao tác | Trên mảng chỉ sắp theo deadline | Ghi chú |
| --- | --- | --- |
| get(id) | \(O(n)\) worst-case | Không có index ID |
| peek_next | \(O(1)\) | Nếu mảng còn giữ đúng thứ tự |
| count_range(a,b) | \(O(\log n)\) | Hai lần binary search theo deadline |
| take_next | \(O(n)\) worst-case | Xóa A[0] dịch toàn bộ phần sau |
| schedule | \(O(n)\) | Tìm vị trí \(O(\log n)\), insert giữa \(O(n)\) |
| cancel | \(O(n)\) | Tìm ID và dịch phần tử |
| reschedule | \(O(n)\) | Tìm, xóa, chèn lại |

Điều nghịch lý: **peek_next nhanh nhưng take_next chậm**. Hệ thống điều phối không chỉ cần “xem” tác vụ đầu mà thường phải **lấy ra và xóa nó**. Thiết kế đã tối ưu một lát cắt nhỏ của vòng đời tác vụ.

## 6. Ước lượng tải: tính tần suất nhân chi phí, không chỉ đọc Big-O

Với \(n=100\,000\), một lần insert ở một vị trí phân bố gần đều có thể phải dịch trung bình khoảng:

\[
\boxed{n/2=50\,000}
\]

tham chiếu. Nếu workload có 4.000 thay đổi/giây mà **mỗi thay đổi** có một bước dịch mảng cỡ trung bình như vậy, mô hình khối lượng công việc là:

\[
\boxed{4\,000\times50\,000
=200\,000\,000}
\]

**lượt dịch tham chiếu/giây**, chưa tính tìm ID, cấp phát, khóa, giao dịch hoặc các phép dịch bổ sung khi reschedule.

Đây là **phép ước lượng lý thuyết trên một workload giả định**, **không phải benchmark đã đo**. Vị trí insert/cancel thực tế không nhất thiết phân bố đều; mảng có thể dùng memmove tối ưu ở mức thấp; khả năng đáp ứng còn phụ thuộc CPU, bộ nhớ và hệ thống chạy.

Dù vậy, phép tính làm lộ vấn đề bậc độ lớn: nếu một thao tác tần suất cao đòi di chuyển số phần tử **tỷ lệ với n**, tốc độ cập nhật không dễ mở rộng theo n.

### Chẩn đoán nguyên nhân gốc

Không phải “binary search triển khai sai” hay “dynamic array luôn chậm”. Dynamic array có thể rất tốt khi:

- Dữ liệu **hầu như tĩnh**.
- Chủ yếu thực hiện **tìm kiếm theo khóa**, **duyệt tuần tự** hoặc truy vấn khoảng.
- Có thể **gom cập nhật thành lô** rồi sắp xếp lại một lần.

Thiết kế sai vì chọn cấu trúc **phù hợp một workload đọc tĩnh**, rồi áp vào workload **ghi thường xuyên và nhiều kiểu truy vấn**.

## 7. Phản ví dụ: chỉ thêm HashMap vị trí chưa chắc sửa được thiết kế

Sau khi tìm ra chi phí cancel, nhóm đề xuất thêm:

~~~text
by_id["A"] = 0
by_id["B"] = 1
by_id["C"] = 2
by_id["D"] = 3
by_id["E"] = 4
~~~

Ban đầu, bảng này cho phép truy ra vị trí ID trong mảng nhanh. Nhưng khi chèn X@5 ở vị trí 3, các entry D,E dịch sang phải:

~~~text
Trước: [A@2, B@4, C@4, D@7, E@9]
       D -> 3, E -> 4

Sau:   [A@2, B@4, C@4, X@5, D@7, E@9]
       D -> 4, E -> 5
~~~

Nếu chỉ cập nhật vị trí của X, bảng **D → 3** vẫn trỏ vào X, khiến cancel("D") có thể xóa **nhầm tác vụ**. Nếu cập nhật đầy đủ vị trí mọi phần tử đã dịch, chi phí cập nhật chỉ mục phụ vẫn **\(O(n)\)**.

### Phân biệt vị trí lưu trữ và danh tính

**ID** là danh tính logic bền vững. **Vị trí trong dynamic array** chỉ là metadata vật lý, có thể thay đổi sau insert/delete. Chỉ dùng **vị trí** làm khóa ổn định khi có cơ chế duy trì ánh xạ chính xác và chi phí duy trì được tính đủ.

Một phương án tinh vi hơn như **cấu trúc cây tìm kiếm cân bằng có node tham chiếu ổn định** có thể giúp tránh dời phần lớn bản ghi. Nhưng đổi từ dynamic array sang cây nghĩa là **thay cấu trúc dữ liệu**, không phải thêm một HashMap để che chi phí dịch mảng.

### “Sửa tối thiểu” có thể phù hợp khi nào?

Nếu thực tế 99,99% thao tác là đọc theo deadline, hầu như không hủy/đổi hạn, mảng sắp vẫn có thể là lựa chọn rất tốt. Cần đặt lại câu hỏi workload trước khi bác bỏ toàn bộ cấu trúc.

## 8. Phân rã yêu cầu thành ba abstract data types

Thay vì tìm một cấu trúc “giỏi mọi thứ”, ta tách các cách truy cập logic:

1. **Dictionary / Map:** từ ID tới deadline hiện hành.
2. **Priority queue:** tìm hoặc lấy phần tử có deadline sớm nhất.
3. **Range-sum index:** đếm số deadline trong một đoạn.

| Yêu cầu | Cấu trúc phù hợp trong điều kiện của bài | Lợi ích chủ đạo |
| --- | --- | --- |
| get(id), kiểm tra ID trùng | **HashMap** ID → record | Lookup trung bình \(O(1)\) |
| peek_next, take_next | **Min-heap** theo \((deadline,id)\) | Truy xuất minimum, thêm mới \(O(\log H)\) |
| count_range(a,b) | **Fenwick tree** của đếm theo phút | Tổng tiền tố/range \(O(\log U)\) |
| Hủy/đổi hạn bất kỳ ID | HashMap là nguồn chân lý, heap dùng **lazy invalidation** | Không cần tìm vị trí ID trong heap |

**Nguồn chân lý (source of truth)** là ánh xạ:

\[
\boxed{Active:id\mapsto(deadline,token).}
\]

Heap chỉ là **chỉ mục phụ** có thể chứa bản ghi cũ; Fenwick tree là **chỉ mục tổng hợp** chứa số tác vụ hiện hành mỗi phút.

### Vì sao không dùng riêng min-heap?

Min-heap tìm minimum hiệu quả, nhưng không có tra cứu ID tùy ý \(O(1)\) nếu không có chỉ mục bổ sung. Nó cũng không hỗ trợ trực tiếp **đếm tất cả deadline trong đoạn bất kỳ** bằng \(O(\log n)\) như một cây tổng hợp có thứ tự.

### Vì sao không dùng riêng HashMap?

HashMap giải quyết get/cancel, nhưng nếu chỉ có HashMap thì mỗi lần tìm minimum deadline thường phải **quét mọi ID đang hoạt động**, \(O(n)\). Đếm theo khoảng cũng cần quét toàn bộ nếu không có metadata có thứ tự.

### Vì sao dùng Fenwick tree được?

Trong ca này, deadline là **số nguyên phút trong miền giới hạn \(0\le t<U\)**. Vì vậy ta có thể duy trì mảng tần suất:

\[
\boxed{freq[t]=\#\{id\in Active:\ deadline(id)=t\}.}
\]

Fenwick tree hỗ trợ cộng/trừ một tại vị trí phút và tổng tiền tố trong \(O(\log U)\). Nếu deadline là số thực tùy ý hoặc nằm trên trục thời gian mở không giới hạn, cần một phương án khác như **balanced BST/augmented tree**, chia buckets, nén tọa độ có chính sách rebuild hoặc chỉ mục theo khoảng của cơ sở dữ liệu.

## 9. Bất biến của thiết kế mới: một ID sống, nhiều biểu diễn nhất quán

Thiết kế có nhiều chỉ mục chỉ tốt nếu biết rõ **cái nào có quyền quyết định trạng thái hiện hành**.

### Bất biến A — ID là duy nhất

\[
\boxed{\forall id,\quad id\in Active
\ \Leftrightarrow\ id\text{ là tác vụ đang hoạt động}.}
\]

Không có hai record hiện hành khác nhau mang cùng ID. Nếu muốn hỗ trợ upsert, đó phải là thao tác có hợp đồng rõ; **schedule** không được âm thầm ghi đè ID đang tồn tại.

### Bất biến B — Tần suất trong Fenwick đúng với Active

\[
\boxed{
\forall t\in[0,U-1],\quad
freq[t]=|\{id:Active[id].deadline=t\}|.
}
\]

Khi hủy hoặc đổi hạn, Fenwick phải được cộng/trừ tương ứng. Nếu quên trừ một lần, count_range trả **thừa** dù heap vẫn có thể trả đúng minimum.

### Bất biến C — Heap chứa một entry hợp lệ cho mỗi ID sống

Heap lưu các bộ ba:

\[
\boxed{(deadline,id,token).}
\]

Một heap-entry h hợp lệ khi và chỉ khi:

\[
\boxed{
Active[h.id]=(h.deadline,h.token).
}
\]

Các entry **không hợp lệ** (từ trước khi cancel/reschedule) có thể vẫn nằm trong heap, nhưng không bao giờ được trả ra như tác vụ hiện hành. Việc giữ entry cũ là một **kỹ thuật tối ưu bảo trì**, không phải thay đổi ngữ nghĩa của Active.

### Bất biến D — Token là duy nhất theo từng thế hệ

Mỗi lần schedule/reschedule sinh một token mới, không tái sử dụng ngay cả khi ID đã bị hủy và được tạo lại.

Tại sao cần vậy? Xét:

~~~text
1) schedule("A", 10), token = 7
   heap có (10,"A",7)
2) cancel("A")
   heap vẫn giữ (10,"A",7) dưới dạng stale
3) schedule("A", 10), token = 8
   heap có thêm (10,"A",8)
~~~

Nếu token **đặt lại bằng 1 mỗi khi ID được tạo lại**, heap-entry cũ có thể vô tình khớp Active mới khi deadline trùng. Đây là biến thể của lỗi **ABA / tái sử dụng định danh thế hệ**. Dùng bộ đếm token tăng đều hoặc một generation ID không tái sử dụng trong vòng đời chỉ mục giúp phân biệt chúng.

### Bất biến E — Minimum thực sự là bản ghi sống nhỏ nhất

Sau khi bỏ những heap-entry stale ở đỉnh, heap-entry hợp lệ đầu tiên tại root có khóa \((deadline,id)\) nhỏ nhất trong Active. Lập luận: mọi ID sống có một heap-entry hợp lệ; heap luôn đặt khóa nhỏ nhất trong các entry còn tồn tại lên đỉnh, còn những entry stale chỉ được loại trước khi công bố kết quả.

**Không được dừng chỉ vì đỉnh heap đang stale.** Phải bỏ nó và tiếp tục cho tới khi tìm được đỉnh hợp lệ hoặc heap rỗng.

## 10. Chèn, hủy, đổi hạn: quy trình giữ ba chỉ mục đồng bộ

### schedule(id,t)

~~~text
Nếu id đã có trong Active: lỗi DuplicateID
Nếu t ngoài [0,U-1]: lỗi InvalidDeadline
token = NEW_UNIQUE_TOKEN()
Active[id] = (t, token)
Fenwick.add(t, +1)
Heap.push((t, id, token))
Có thể kiểm tra điều kiện cần compact heap
~~~

Với dữ liệu tuần tự và bộ nhớ đủ, sau thao tác Active, Fenwick và heap phải cùng mô tả một trạng thái logic. Trong ứng dụng đồng thời hoặc có khả năng lỗi giữa chừng, cần giao dịch/rollback, chứ không chỉ chạy ba bước độc lập rồi hy vọng không ai đọc xen vào.

### cancel(id)

~~~text
old = Active.remove(id)
Nếu không có old: return False
Fenwick.add(old.deadline, -1)
Không tìm/xóa trực tiếp old entry trong heap
Có thể compact heap nếu stale quá nhiều
return True
~~~

Heap-entry cũ sẽ bị phát hiện là stale khi tới đỉnh; không cần quét heap để tìm ID. Cập nhật Fenwick làm việc theo **deadline cũ**, không phải thời điểm cancel.

### reschedule(id,new_t)

~~~text
old = Active[id]  // Lỗi nếu id chưa tồn tại
Nếu new_t ngoài miền: lỗi InvalidDeadline
Fenwick.add(old.deadline, -1)
new_token = NEW_UNIQUE_TOKEN()
Active[id] = (new_t, new_token)
Fenwick.add(new_t, +1)
Heap.push((new_t, id, new_token))
Có thể compact heap
~~~

**Ngay cả khi new_t bằng old.deadline**, tạo token mới vẫn làm entry heap cũ stale. Một triển khai khác có thể **trả về sớm** nếu không đổi hạn, nhưng cần định nghĩa rõ reschedule cùng hạn có ý nghĩa “tạo thế hệ mới” hay không. Trong mã minh họa, mỗi reschedule tạo thế hệ mới cho nhất quán và dễ kiểm tra.

### peek_next và take_next

~~~text
DISCARD_STALE_TOP():
    while heap not empty:
        top = heap.min()
        if Active[top.id] == (top.deadline, top.token):
            return
        heap.pop_min()

PEEK_NEXT():
    DISCARD_STALE_TOP()
    return None nếu heap rỗng
    return (heap.min().id, heap.min().deadline)

TAKE_NEXT():
    DISCARD_STALE_TOP()
    nếu heap rỗng: return None
    item = heap.pop_min()  // item chắc chắn hợp lệ
    Active.remove(item.id)
    Fenwick.add(item.deadline, -1)
    return (item.id, item.deadline)
~~~

Phân biệt **peek** (xem) với **take** (lấy ra). Một thiết kế ưu tiên cần đáp ứng cả hai mà không gây dịch toàn bộ mảng.

## 11. Fenwick tree: đếm theo đoạn mà không quét mọi tác vụ

Chỉ mục Fenwick lưu tần suất theo deadline trong mảng có \(U\) phần tử. Nếu dùng chỉ số ngoài từ 0, công thức API tổng tiền tố:

\[
\boxed{
prefix(k)=\sum_{0\le t<k}freq[t],
\quad 0\le k\le U.
}
\]

Với đoạn đóng \([a,b]\):

\[
\boxed{
count\_range(a,b)=prefix(b+1)-prefix(a).
}
\]

Ví dụ tại các phút:

~~~text
t      0  1  2  3  4  5  6
freq   0  1  0  2  1  0  1

count[3,4] = freq[3]+freq[4] = 2+1 = 3
             prefix(5)-prefix(3) = 4-1 = 3
~~~

### Tại sao cộng/trừ cần đúng deadline cũ?

Giả sử tác vụ X chuyển từ phút 3 sang phút 6. Nếu chỉ cộng +1 tại phút 6 mà quên trừ 1 tại phút 3, tổng Fenwick tăng thêm 1 dù số tác vụ Active không đổi. Query \([3,3]\) có thể đếm X ở vị trí cũ, còn \([6,6]\) lại đếm thêm lần nữa.

### Dùng mảng tần suất thôi có được không?

Được, nếu U nhỏ hoặc rất ít query:

- Cập nhật freq tại một phút: \(O(1)\).
- Đếm đoạn \([a,b]\): \(O(b-a+1)\) nếu cộng trực tiếp.

Fenwick đánh đổi **cập nhật \(O(\log U)\)** để đếm đoạn **\(O(\log U)\)**. Nếu U=10.080, chiều cao bitwise của Fenwick chỉ cỡ 14 mức; nếu U hàng tỷ với phần lớn phút không có dữ liệu, cấp phát Fenwick dày có thể không hợp lý.

### Count khác Range Reporting

Fenwick trong thiết kế này chỉ biết **số lượng theo từng phút**, **không chứa danh sách ID**. Muốn **liệt kê mọi ID có hạn trong \([a,b]\)**, cần cấu trúc bổ sung như ordered map theo deadline với bucket ID, cây thứ tự cân bằng, hoặc chấp nhận quét Active.

Không được ghi “Fenwick hỗ trợ trả danh sách mọi ID trong đoạn bằng \(O(\log U)\)” khi nó chỉ có tần suất tổng hợp.

## 12. Lazy deletion: tại sao heap có thể chứa nhiều phần tử hơn n?

Min-heap chỉ biết so khóa ở đỉnh; tìm một ID bất kỳ trong heap thường không có đường đi hỗ trợ \(O(\log n)\). Ta tránh **arbitrary removal** bằng cách để entry đã hủy/đổi hạn nằm lại cho tới khi chạm đỉnh.

Gọi:

- \(n=|Active|\): số tác vụ sống.
- \(H=|Heap|\): số entry vật lý trong heap, **bao gồm stale**.

Có thể \(H\gg n\) nếu nhiều lần reschedule nhưng ít lần peek/take. Ví dụ một ID được đổi hạn 100.000 lần có thể để lại rất nhiều entry stale nếu không có compact.

### Chính sách compact

Một ngưỡng minh họa:

\[
\boxed{
H>\max(16,2n)
\ \Longrightarrow\
\text{rebuild heap từ Active}.
}
\]

Rebuild tạo heap mới chứa **chính xác một entry hợp lệ cho mỗi ID đang hoạt động**, thông qua thao tác heapify trên mảng có n entry:

\[
\boxed{T_{\mathrm{heapify}}=O(n).}
\]

Tại thời điểm rebuild, heap cũ có độ dài \(H=O(n+16)\) ngay sau kiểm tra ngưỡng ở các thao tác đơn giản, nhưng một cài đặt production cần kiểm soát cả **tần suất compact** và lượng update đột biến.

### Phân tích chi phí khấu hao

Sau compact, H=n. Muốn H vượt khoảng \(2n\), cần tích lũy nhiều stale entry hoặc làm n giảm đáng kể do cancel. Những entry stale ấy xuất hiện từ các thao tác trước đó. Do đó công việc heapify thường có thể **khấu hao lên những update tạo ra stale**, thay vì tính như chi phí \(O(n)\) cho **mọi** cancel/reschedule.

Tuy nhiên, một lần update riêng lẻ **vẫn có thể kích hoạt \(O(n)\) heapify**, nên không được hứa update có độ trễ worst-case \(O(\log n)\) trong triển khai compact đồng bộ này. Nếu SLA update cần tail latency nghiêm ngặt, cân nhắc indexed heap có vị trí cập nhật chính xác, compact từng phần hoặc cơ chế làm nền có tính nhất quán phù hợp.

### Số phút U và kích thước heap H là hai đại lượng khác nhau

Fenwick dùng \(O(U)\) bộ nhớ. Heap có thể chứa tới \(O(n)\) entry **sau compact**, còn trước compact có thêm một số stale; HashMap có \(O(n)\) record. Nhầm H với U có thể dẫn đến đánh giá bộ nhớ sai khi số tác vụ cực lớn nhưng miền deadline chỉ vài nghìn phút.

## 13. Bảng độ phức tạp: cùng hợp đồng, hai kiến trúc

Đặt \(n\) là số tác vụ sống, \(H\) là kích thước heap vật lý (kể cả stale), \(U\) là số phút được index. Bảng giả định thao tác bảng băm **\(O(1)\) trung bình**, phép so sánh ID có chi phí coi như hằng số với ID độ dài giới hạn và chưa tính khóa/I/O. “Không compact” nghĩa là chỉ xét thao tác heap/Fenwick thông thường.

| Thao tác | Một mảng sắp theo (deadline,ID) | HashMap + heap + Fenwick |
| --- | --- | --- |
| schedule | \(O(n)\) | \(O(\log H+\log U)\) khi không compact |
| cancel theo ID | \(O(n)\) | \(O(\log U)\) trung bình khi không compact |
| reschedule | \(O(n)\) | \(O(\log H+\log U)\) khi không compact |
| get(id) | \(O(n)\) | \(O(1)\) trung bình |
| peek_next | \(O(1)\) | \(O(1)\) nếu đỉnh hợp lệ; có thể dọn nhiều stale, khấu hao theo các lần pop |
| take_next | \(O(n)\) | \(O(\log H+\log U)\) cộng chi phí dọn stale |
| count_range | \(O(\log n)\) | \(O(\log U)\) |
| Bộ nhớ | \(O(n)\) | \(O(n+H+U)\), với compact kiểm soát H |

### Vì sao độ phức tạp của peek không chỉ \(O(1)\)?

Nếu đỉnh heap còn hợp lệ, chỉ cần đọc một phần tử. Nhưng nếu có một chuỗi \(s\) entry stale ở đỉnh, một lần peek phải gọi pop_min \(s\) lần, tốn tới \(O(s\log H)\). Không được báo worst-case \(O(1)\).

Đổi lại, **mỗi stale entry chỉ bị loại khỏi heap một lần**, nên có thể tính chi phí dọn của nhiều lần peek/take về cho các update tạo ra nó. Compact giúp chặn sự phình to H, nhưng một lần compact vẫn tạo một đỉnh độ trễ \(O(n)\).

### Khi nào tổng chi phí tốt hơn?

Mô hình tổng tải:

\[
\boxed{
C_{\mathrm{workload}}=
\sum_{\mathrm{op}}q_{\mathrm{op}}\cdot
T_{\mathrm{op}}
+C_{\mathrm{build}}
+C_{\mathrm{maintenance}}.
}
\]

Trong ca của bài, schedule/cancel/reschedule và get xảy ra **thường xuyên**, nên thay các thao tác \(O(n)\) bằng \(O(\log H+\log U)\) hoặc \(O(1)\) trung bình có thể mang lại lợi ích đáng kể. Nhưng đây là **kết luận từ phân tích mô hình**, không phải khẳng định tốc độ thực tế đã được benchmark trên môi trường cụ thể.

Nếu workload thay đổi thành **đọc rất nhiều, gần như không cập nhật**, mảng sắp có thể lại đáng cân nhắc vì cấu trúc liên tiếp, ít overhead và count khoảng nhanh.

## 14. Vì sao không chọn một cấu trúc khác?

Một cuộc review thiết kế tốt không chỉ trình bày một đáp án mà còn xét các phương án **cạnh tranh**.

### Balanced BST có augmentation

Một **cây tìm kiếm cân bằng** (AVL, red-black hoặc B-tree theo ngữ cảnh) sắp theo khóa \((deadline,id)\) có thể hỗ trợ:

- Thêm/xóa/đổi hạn: \(O(\log n)\) worst-case nếu được triển khai và cân bằng đúng.
- Peek min: \(O(\log n)\) khi đi từ root xuống trái; có thể giữ con trỏ min để giảm chi phí nhìn min.
- Count khoảng: dùng **subtree size** và thao tác rank, \(O(\log n)\) cho mỗi rank.
- Liệt kê ID theo khoảng: \(O(\log n+k)\) trong mô hình balanced ordered index phù hợp.

Thêm HashMap ID → tham chiếu node hoặc record giúp tra ID nhanh hơn. Tuy nhiên Python chuẩn không có một **ordered balanced tree API** tự động đảm bảo tất cả các tính chất trên; phải dùng thư viện hoặc tự cài với kiểm thử invariants.

**Phù hợp hơn Fenwick** khi deadline không bị chặn trong một miền nguyên nhỏ hoặc cần **range reporting theo ID**; trả giá bằng con trỏ, cân bằng node và chi phí bộ nhớ/cache.

### Indexed heap

Một min-heap có bảng **ID → vị trí heap** có thể hỗ trợ update/remove một ID trong \(O(\log n)\), không cần tombstone. Nhưng cần cập nhật bảng vị trí **mỗi lần hoán đổi heap** trong sift-up/sift-down, kể cả khi pop_min.

Nếu quên sửa index sau một phép swap, cancel(id) có thể xóa nhầm entry. Indexed heap giúp giảm H phình và độ trễ dọn stale, đổi lại code và bất biến phức tạp hơn. Nó **vẫn không tự giải quyết count_range**; cần Fenwick hoặc ordered aggregate index.

### Bucket theo phút với ordered set

Khi U=10.080 và nhiều ID chia sẻ cùng phút, một phương án khác là:

- Mảng/bảng băm **phút → tập ID**.
- Một cấu trúc nhanh tìm **phút không rỗng sớm nhất** (bitset nhiều cấp, Fenwick tìm prefix, hoặc ordered set các phút đang hoạt động).
- Fenwick đếm theo phút như trước.

Điều cần kiểm tra: tie theo **ID nhỏ nhất trong phút**. Hash set không tự trả ID nhỏ nhất theo thứ tự từ điển; nếu cần đúng quy tắc tie, mỗi bucket phải hỗ trợ chọn ID nhỏ nhất hoặc một cấu trúc bổ sung.

### Quét tuyến tính

Nếu \(n\) chỉ vài trăm và hệ thống rất ít truy vấn, giữ một HashMap và quét để tìm minimum hoặc đếm khoảng có thể **đơn giản và đủ nhanh**. Big-O tốt hơn chưa chắc thắng chi phí thực vì heap, Fenwick và kiểm tra token có overhead.

### Bảng chọn theo ràng buộc

| Phương án | Điểm mạnh | Hạn chế nổi bật |
| --- | --- | --- |
| Mảng sắp | Đọc min trực tiếp, range count nhanh, locality tốt | Insert/delete giữa mảng \(O(n)\) |
| HashMap đơn | Exact lookup/cancel trung bình nhanh | Min/range count thường \(O(n)\) |
| Heap đơn | Min/take hiệu quả | Cancel tùy ID, range count khó |
| HashMap + heap | Exact lookup và min động | Không có aggregate khoảng, quản lý stale hoặc index vị trí |
| HashMap + heap + Fenwick | Phù hợp hợp đồng bài khi deadline nguyên hữu hạn | Bộ nhớ \(O(U)\); phải đồng bộ ba index |
| HashMap + balanced BST có size | Miền khóa linh hoạt, min và rank động | Triển khai/cân bằng/metadata phức tạp hơn |

## 15. Phản ví dụ thay đổi yêu cầu: thiết kế tối ưu hiện tại cũng có giới hạn

Thiết kế ba chỉ mục là lựa chọn **có điều kiện**, không phải khuyến nghị vô hạn.

### Hạn là số thực hoặc thời điểm mở rộng vô hạn

Nếu deadline là timestamp tùy ý trên nhiều năm, một Fenwick dày theo từng millisecond là không khả thi. **Nén tọa độ tĩnh** chỉ hiệu quả khi tập khóa biết trước; nếu deadline mới xuất hiện liên tục, cần chiến lược tái xây hoặc ordered aggregate tree.

### Count thay bằng list

Nếu product yêu cầu **liệt kê toàn bộ ID trong \([a,b]\)** chứ không chỉ đếm, Fenwick tần suất không đủ. Có thể dùng balanced BST theo \((deadline,id)\) hoặc map phút → tập ID, nhưng vẫn phải mất \(\Omega(k)\) để xuất k ID.

### Ưu tiên không chỉ theo hạn

Nếu khóa mới là \((priority,deadline,id)\), heap có thể đổi khóa so sánh. Nhưng Fenwick theo deadline **không tự trả** count theo khoảng priority và deadline kết hợp. Có thể cần chỉ mục đa chiều hoặc nhiều aggregate được thiết kế riêng. Thêm một chiều truy vấn thường thay đổi đáng kể lựa chọn cấu trúc.

### Deadline có thể bị chỉnh về quá khứ

Nếu có quy tắc chỉ chạy các task với deadline \(\le now\), một minimum heap vẫn trả task sớm nhất; điều kiện due được kiểm tra **sau** khi peek. Không được thực thi task chỉ vì nó là min nếu deadline còn ở tương lai.

### Tái sử dụng ID và lỗi ABA

Hủy A@10 rồi schedule lại A@10 có thể khiến hai heap-entry cùng \((deadline,id)\). Nếu không dùng token **thế hệ**, ta không phân biệt được chúng. Trong các hệ thống có ID tái sử dụng, generation phải được lưu đủ lâu hoặc bảo đảm không đụng token cho những entry stale còn tồn tại.

**Bài học:** Khi một ràng buộc nền tảng của thiết kế đổi, phải phân tích lại **bất biến và chi phí**, không chỉ vá một điều kiện if.

## 16. Python: cài đặt thiết kế ban đầu đúng nhưng đắt

Mã minh họa dùng **Python 3.10+** và thư viện chuẩn. Lớp dưới đây giữ đúng bất biến mảng được sắp theo \((deadline,id)\), chứ không cố tình tạo một chương trình sai kết quả.

Mục tiêu là tách hai khái niệm: **đúng chức năng** và **phù hợp hiệu năng**. Nếu chương trình baseline trả sai, việc so sánh tốc độ với thiết kế mới sẽ mất ý nghĩa.

~~~python
from bisect import bisect_left, insort_right


class SortedArrayScheduler:
    def __init__(self, U: int):
        if type(U) is not int or U < 1:
            raise ValueError("U phải là số nguyên dương")
        self.U = U
        self.items: list[tuple[int, str]] = []

    def _time(self, deadline: int):
        if type(deadline) is not int:
            raise TypeError("deadline phải là số nguyên")
        if not (0 <= deadline < self.U):
            raise ValueError("deadline ngoài [0,U-1]")

    @staticmethod
    def _id(item_id: str):
        if not isinstance(item_id, str) or not item_id:
            raise ValueError("ID phải là chuỗi không rỗng")

    def get(self, item_id: str) -> int | None:
        # Mảng sắp theo deadline, không có chỉ mục riêng theo ID.
        for deadline, key in self.items:
            if key == item_id:
                return deadline
        return None

    def schedule(self, item_id: str, deadline: int):
        self._id(item_id)
        self._time(deadline)
        if self.get(item_id) is not None:
            raise ValueError("ID đang hoạt động")
        insort_right(self.items, (deadline, item_id))

    def cancel(self, item_id: str) -> bool:
        for i, (_, key) in enumerate(self.items):
            if key == item_id:
                self.items.pop(i)  # Dịch phần tử sau vị trí i.
                return True
        return False

    def reschedule(self, item_id: str, deadline: int):
        self._time(deadline)
        for i, (_, key) in enumerate(self.items):
            if key == item_id:
                self.items.pop(i)
                insort_right(self.items, (deadline, item_id))
                return
        raise KeyError(item_id)

    def peek_next(self):
        if not self.items:
            return None
        deadline, item_id = self.items[0]
        return (item_id, deadline)

    def take_next(self):
        if not self.items:
            return None
        deadline, item_id = self.items.pop(0)
        return (item_id, deadline)

    def count_range(self, a: int, b: int) -> int:
        self._time(a)
        self._time(b)
        if a > b:
            raise ValueError("a không được lớn hơn b")
        # ID luôn không rỗng; (t,"") đứng trước mọi (t,ID).
        left = bisect_left(self.items, (a, ""))
        right = bisect_left(self.items, (b + 1, ""))
        return right - left

    def validate(self):
        if self.items != sorted(self.items):
            raise AssertionError("Mảng mất thứ tự")
        if len({item_id for _, item_id in self.items}) != len(
            self.items
        ):
            raise AssertionError("ID bị nhân bản")
        for deadline, item_id in self.items:
            self._time(deadline)
            self._id(item_id)
        return True
~~~

### Vì sao cài đặt này chính xác?

- Mọi schedule/reschedule đều đưa cặp \((deadline,id)\) vào **đúng vị trí sắp**.
- Mọi cancel/take đều xóa **một entry** và dịch các entry còn lại, nên thứ tự không bị phá.
- **ID duy nhất** được kiểm tra trước khi thêm.
- Count đoạn đóng dùng **vị trí trước phút a** và **vị trí trước phút b+1**, nên tính đúng cả hai biên.

### Vì sao vẫn không đáp ứng tốt workload?

Các thao tác insort và pop ở giữa dynamic array có thể di chuyển \(O(n)\) tham chiếu; get và cancel theo ID phải quét một danh sách sắp theo **khóa khác**. Không có lỗi thuật toán cần “sửa” ở đây: chi phí là hệ quả của cấu trúc dữ liệu và hợp đồng thao tác.

## 17. Python: Fenwick tree đếm số tác vụ theo hạn

Fenwick dùng mảng nội bộ **1-based**, nhưng API của bài nhận deadline **0-based** và tổng tiền tố loại trừ cận trên.

~~~python
class Fenwick:
    def __init__(self, U: int):
        if type(U) is not int or U < 1:
            raise ValueError("U phải là số nguyên dương")
        self.U = U
        self.bit = [0] * (U + 1)

    def add(self, deadline: int, delta: int):
        if not (0 <= deadline < self.U):
            raise ValueError("Deadline ngoài miền Fenwick")
        i = deadline + 1
        while i <= self.U:
            self.bit[i] += delta
            i += i & -i

    def prefix(self, exclusive: int) -> int:
        """Tổng freq[0..exclusive-1]."""
        if not (0 <= exclusive <= self.U):
            raise ValueError("Cận prefix ngoài [0,U]")
        result = 0
        i = exclusive
        while i > 0:
            result += self.bit[i]
            i -= i & -i
        return result

    def count_closed(self, a: int, b: int) -> int:
        if not (0 <= a <= b < self.U):
            raise ValueError("Đoạn [a,b] không hợp lệ")
        return self.prefix(b + 1) - self.prefix(a)
~~~

### Kiểm tra công thức bằng tay

Giả sử có:

~~~text
minute       0  1  2  3  4  5  6  7
freq         0  1  0  2  1  0  1  0

prefix(3) = 0+1+0 = 1
prefix(5) = 0+1+0+2+1 = 4
count_closed(3,4) = 4-1 = 3
~~~

Trong hệ thống thật, **Fenwick không là nguồn dữ liệu duy nhất**. Nó chỉ lưu aggregate; phải đồng bộ với bảng Active. Nếu delta âm làm tần suất của một phút âm, hầu như chắc chắn đã có bug trong lifecycle hoặc phép xóa lặp (trừ khi nghiệp vụ định nghĩa một loại signed count khác).

## 18. Python: phiên bản cải tiến HashMap + heap + Fenwick

Ví dụ sau sử dụng lại lớp Fenwick ở mục 17. Các entry heap cũ được giữ theo **lazy invalidation**, nhận dạng bằng token thế hệ. Để tránh heap tăng vô hạn vì update liên tục, triển khai compact khi số entry vật lý vượt một ngưỡng so với số ID sống.

~~~python
from heapq import heapify, heappop, heappush
from itertools import count


class IndexedScheduler:
    def __init__(self, U: int):
        if type(U) is not int or U < 1:
            raise ValueError("U phải là số nguyên dương")
        self.U = U
        self.active: dict[str, tuple[int, int]] = {}
        self.heap: list[tuple[int, str, int]] = []
        self.frequency = Fenwick(U)
        self._tokens = count(1)
        self.compactions = 0

    def _validate_time(self, deadline):
        if type(deadline) is not int:
            raise TypeError("Deadline phải là số nguyên")
        if not (0 <= deadline < self.U):
            raise ValueError("Deadline ngoài [0,U-1]")

    @staticmethod
    def _validate_id(item_id):
        if not isinstance(item_id, str) or not item_id:
            raise ValueError("ID phải là chuỗi không rỗng")

    def _is_live(self, entry):
        deadline, item_id, token = entry
        return self.active.get(item_id) == (deadline, token)

    def _prune_stale(self):
        while self.heap and not self._is_live(self.heap[0]):
            heappop(self.heap)

    def _compact_if_needed(self):
        n = len(self.active)
        if len(self.heap) > max(16, 2 * n):
            self.heap = [
                (deadline, item_id, token)
                for item_id, (deadline, token)
                in self.active.items()
            ]
            heapify(self.heap)
            self.compactions += 1

    def get(self, item_id):
        record = self.active.get(item_id)
        return None if record is None else record[0]

    def schedule(self, item_id: str, deadline: int):
        self._validate_id(item_id)
        self._validate_time(deadline)
        if item_id in self.active:
            raise ValueError("ID đang hoạt động")

        token = next(self._tokens)
        self.active[item_id] = (deadline, token)
        self.frequency.add(deadline, +1)
        heappush(self.heap, (deadline, item_id, token))
        self._compact_if_needed()

    def cancel(self, item_id: str):
        if item_id not in self.active:
            return False
        deadline, _ = self.active.pop(item_id)
        self.frequency.add(deadline, -1)
        # Entry cũ trong heap sẽ bị loại khi lên đỉnh.
        self._compact_if_needed()
        return True

    def reschedule(self, item_id: str, new_deadline: int):
        self._validate_time(new_deadline)
        if item_id not in self.active:
            raise KeyError(item_id)

        old_deadline, _ = self.active[item_id]
        self.frequency.add(old_deadline, -1)
        token = next(self._tokens)
        self.active[item_id] = (new_deadline, token)
        self.frequency.add(new_deadline, +1)
        heappush(
            self.heap, (new_deadline, item_id, token)
        )
        self._compact_if_needed()

    def peek_next(self):
        self._prune_stale()
        if not self.heap:
            return None
        deadline, item_id, _ = self.heap[0]
        return (item_id, deadline)

    def take_next(self):
        self._prune_stale()
        if not self.heap:
            return None
        deadline, item_id, token = heappop(self.heap)
        if self.active.get(item_id) != (deadline, token):
            raise AssertionError("Đỉnh không còn hợp lệ")
        del self.active[item_id]
        self.frequency.add(deadline, -1)
        self._compact_if_needed()
        return (item_id, deadline)

    def count_range(self, a: int, b: int):
        self._validate_time(a)
        self._validate_time(b)
        if a > b:
            raise ValueError("a không được lớn hơn b")
        return self.frequency.count_closed(a, b)

    def validate(self):
        """Dùng trong bài tập, không chạy sau mọi update thật."""
        expected = [0] * self.U
        for item_id, (deadline, token) in self.active.items():
            self._validate_id(item_id)
            self._validate_time(deadline)
            if type(token) is not int or token < 1:
                raise AssertionError("Token không hợp lệ")
            expected[deadline] += 1

        # So tổng đếm từng phút với dict đang sống.
        for t, count_at_t in enumerate(expected):
            got = self.frequency.count_closed(t, t)
            if got != count_at_t:
                raise AssertionError("Fenwick lệch Active")
        if self.frequency.prefix(self.U) != len(self.active):
            raise AssertionError("Sai tổng số task")

        # Heap property: mỗi cha <= hai con nếu chúng có mặt.
        for i in range(1, len(self.heap)):
            if self.heap[(i - 1) // 2] > self.heap[i]:
                raise AssertionError("Heap property bị phá")

        # Với mỗi ID sống phải có đúng một entry heap hợp lệ.
        live_counts = {item_id: 0 for item_id in self.active}
        for entry in self.heap:
            if self._is_live(entry):
                live_counts[entry[1]] += 1
        if any(count != 1 for count in live_counts.values()):
            raise AssertionError("Thiếu/trùng entry heap hợp lệ")

        # Kiểm tra peek không bắt buộc trong validate vì thao tác
        # ấy tự dọn stale ở đỉnh, làm thay đổi heap vật lý.
        return True
~~~

### Tại sao dùng token toàn cục?

Nếu A@10 bị hủy rồi A@10 được thêm lại, cả hai entry có cùng \((deadline,id)\), nhưng token khác nhau. Bản cũ bị phát hiện stale. Nếu token chỉ được reset khi tạo lại ID, lỗi ABA có thể khiến một bản cũ trở nên có vẻ hợp lệ.

### Vì sao không xóa trực tiếp khỏi heap mỗi khi cancel?

Min-heap chuẩn không có chỉ số ID tùy ý. Quét heap tìm ID là \(O(H)\); xóa rồi sửa heap đúng vị trí cũng cần biết index. Lazy invalidation giữ thao tác cancel chủ yếu là **HashMap + Fenwick**, còn chi phí dọn stale được trả sau hoặc thông qua compact.

### Vì sao hàm validate đắt?

Nó dựng lại tần suất từ Active, kiểm tra từng phút \(0..U-1\) và quét mọi heap-entry. Vì vậy validate là **công cụ kiểm thử/giám sát có kiểm soát**, không nên được gọi mặc định sau mọi thao tác của hệ thống hiệu năng cao.

### Giới hạn của ví dụ

Đây là mã **đơn luồng, trong RAM**. Trong hệ thống có nhiều writer/reader, ba chỉ mục cần được cập nhật nhất quán theo transaction, locking hoặc snapshot; lỗi xảy ra giữa thao tác HashMap/Fenwick/heap cần rollback hay một giao thức phục hồi. Không suy ra thread-safety từ việc từng cấu trúc riêng có những thao tác nhanh.

## 19. Trace bằng tay: cùng trạng thái logic, thứ tự vật lý khác nhau

Bắt đầu với \(U=16\) và các thao tác:

~~~text
schedule("A",7)
schedule("B",3)
schedule("C",3)
schedule("D",1)
~~~

Trạng thái logic:

| ID | Deadline |
| --- | ---: |
| A | 7 |
| B | 3 |
| C | 3 |
| D | 1 |

Mảng sắp:

~~~text
[D@1, B@3, C@3, A@7]
~~~

Heap của thiết kế mới có thể có thứ tự mảng vật lý **khác hoàn toàn** nhưng root vẫn là D@1. Fenwick có:

~~~text
freq[1]=1, freq[3]=2, freq[7]=1; các phút khác = 0
~~~

Các kết quả phải khớp:

\[
\boxed{
peek\_next()=(D,1),\quad
count\_range(3,7)=3.
}
\]

Tiếp tục:

~~~text
reschedule("B",9)
cancel("D")
schedule("D",1)       // Tái sử dụng ID với thế hệ mới.
take_next()           // Phải trả D@1 thế hệ mới, chỉ một lần.
~~~

Trạng thái còn lại:

| ID | Deadline |
| --- | ---: |
| C | 3 |
| A | 7 |
| B | 9 |

Thiết kế mảng có thể chỉ còn ba cặp khóa tương ứng. Thiết kế heap có thể **vẫn chứa** entry cũ B@3 và D@1 với token trước khi cancel, nhưng những entry này **không hợp lệ** và không được phép xuất hiện trong đáp án.

### Điểm kiểm chứng quan trọng

Đừng so **mảng nội bộ** của hai thiết kế rồi kết luận một bên sai; chúng không cùng biểu diễn vật lý. Hãy so **hợp đồng bên ngoài**: tập ID đang hoạt động, deadline mỗi ID, peek/take và count theo khoảng.

## 20. Python: so kết quả hai thiết kế với oracle độc lập

Một kiểm thử tốt dùng ba vai trò:

1. **Oracle:** dictionary đơn giản ID → deadline; mọi phép hỏi được tính bằng quét độc lập.
2. **Baseline:** mảng sắp, đúng chức năng nhưng chậm.
3. **Thiết kế mới:** HashMap + heap + Fenwick.

Oracle không dùng Fenwick, heap hay binary search nên giảm nguy cơ hai triển khai mắc cùng một lỗi và cùng cho kết quả sai.

### Kiểm thử xác định trước

Đoạn sau **nối tiếp** các lớp ở mục 16–18:

~~~python
baseline = SortedArrayScheduler(U=16)
improved = IndexedScheduler(U=16)

for item_id, t in [
    ("A", 7), ("B", 3), ("C", 3), ("D", 1)
]:
    baseline.schedule(item_id, t)
    improved.schedule(item_id, t)

assert baseline.validate()
assert improved.validate()
assert baseline.peek_next() == ("D", 1)
assert improved.peek_next() == ("D", 1)
assert baseline.count_range(3, 7) == 3
assert improved.count_range(3, 7) == 3

for index in (baseline, improved):
    index.reschedule("B", 9)
    assert index.cancel("D")
    index.schedule("D", 1)
    assert index.take_next() == ("D", 1)
    assert index.peek_next() == ("C", 3)
    assert index.get("B") == 9
    assert index.count_range(0, 15) == 3
    assert index.count_range(3, 7) == 2
    assert index.validate()

# Hai ID chung deadline: ưu tiên ID nhỏ hơn.
for index in (baseline, improved):
    index.schedule("AA", 3)
    assert index.peek_next() == ("AA", 3)
    assert index.take_next() == ("AA", 3)

# Reschedule cùng deadline: không làm xuất hiện ID hai lần.
for index in (baseline, improved):
    index.reschedule("C", 3)
    assert index.count_range(3, 3) == 1
    assert index.peek_next() == ("C", 3)
    assert index.validate()

# Tái sử dụng ID nhiều lần với cùng deadline.
for index in (baseline, improved):
    for _ in range(20):
        assert index.cancel("C")
        index.schedule("C", 3)
        assert index.peek_next() == ("C", 3)
        assert index.validate()

# Hủy hết, kể cả các entry stale nằm sâu trong heap.
for index in (baseline, improved):
    for item_id in ("A", "B", "C"):
        assert index.cancel(item_id)
    assert index.peek_next() is None
    assert index.take_next() is None
    assert index.count_range(0, 15) == 0
    assert index.validate()

# Miền nhỏ nhất U=1 và cả hai biên.
for cls in (SortedArrayScheduler, IndexedScheduler):
    sched = cls(U=1)
    sched.schedule("only", 0)
    assert sched.count_range(0, 0) == 1
    assert sched.peek_next() == ("only", 0)
    assert sched.take_next() == ("only", 0)
    assert sched.peek_next() is None
    assert sched.validate()
~~~

### Kiểm thử differential có sinh thao tác ngẫu nhiên tái lập

Đặt seed cố định để người đọc tái lập cùng chuỗi. Đừng chỉ kiểm tra kết quả cuối: cần kiểm tra **sau mỗi thao tác**, để tìm được bước đầu tiên phá bất biến.

~~~python
from random import Random

random = Random(2026)
U = 32
oracle = {}  # ID -> deadline, không lưu thứ tự.
old = SortedArrayScheduler(U)
new = IndexedScheduler(U)


def oracle_peek():
    if not oracle:
        return None
    deadline, item_id = min(
        (deadline, item_id)
        for item_id, deadline in oracle.items()
    )
    return (item_id, deadline)


def oracle_count(a, b):
    return sum(a <= t <= b for t in oracle.values())


def assert_everything():
    assert old.validate()
    assert new.validate()
    assert len(old.items) == len(oracle) == len(new.active)

    for item_id in [f"T{i:02d}" for i in range(30)]:
        assert old.get(item_id) == oracle.get(item_id)
        assert new.get(item_id) == oracle.get(item_id)

    assert old.peek_next() == oracle_peek()
    assert new.peek_next() == oracle_peek()
    for a, b in [(0, 0), (0, U - 1), (5, 12), (20, 20)]:
        assert old.count_range(a, b) == oracle_count(a, b)
        assert new.count_range(a, b) == oracle_count(a, b)


for step in range(400):
    item_id = f"T{random.randrange(30):02d}"
    deadline = random.randrange(U)
    action = random.randrange(5)

    if action == 0:  # schedule nếu chưa tồn tại
        if item_id not in oracle:
            old.schedule(item_id, deadline)
            new.schedule(item_id, deadline)
            oracle[item_id] = deadline
    elif action == 1:  # cancel
        existed = item_id in oracle
        assert old.cancel(item_id) == existed
        assert new.cancel(item_id) == existed
        oracle.pop(item_id, None)
    elif action == 2:  # reschedule nếu tồn tại
        if item_id in oracle:
            old.reschedule(item_id, deadline)
            new.reschedule(item_id, deadline)
            oracle[item_id] = deadline
    elif action == 3:  # take_next
        expected = oracle_peek()
        assert old.take_next() == expected
        assert new.take_next() == expected
        if expected is not None:
            del oracle[expected[0]]
    else:  # read-only peek
        assert old.peek_next() == oracle_peek()
        assert new.peek_next() == oracle_peek()

    assert_everything()

# Kiểm tra rằng compact không thay đổi trạng thái logic.
snapshot = dict(oracle)
new._compact_if_needed()
assert_everything()
assert oracle == snapshot
~~~

### Những gì test chứng minh và không chứng minh

Nếu người học chạy thành công, các test làm tăng niềm tin rằng hai cài đặt tuân thủ cùng hợp đồng trên những ca đã thử. Chúng **không phải chứng minh hình thức** cho mọi chuỗi thao tác, không kiểm tra đồng thời và không đo benchmark hiệu năng.

Theo ràng buộc của tác vụ **STEP 4**, những mã Python này được **biên soạn** làm tài liệu; tác giả **không chạy Python hoặc vòng Content QA chuyên môn** trong bước này. Các câu lệnh assert là tiêu chuẩn kiểm tra dành cho người đọc/QA ở bước khác, không phải lời khẳng định thử nghiệm đã được thực thi.

## 21. Kiểm thử lỗi: những ca nào cần thiết hơn nhiều dữ liệu ngẫu nhiên?

Random thường ít tạo đúng các trường hợp hiếm nhưng nguy hiểm. Bộ kiểm thử nên thêm các ca chủ đích:

| Ca | Điều phải đúng |
| --- | --- |
| Hai ID cùng deadline | Peek/take tie theo ID nhỏ hơn |
| U=1, deadline=0 | Hợp lệ; count [0,0] đúng |
| Deadline=-1 hoặc U | Từ chối trước khi sửa trạng thái |
| Hủy ID không tồn tại | False, không làm âm Fenwick |
| Chèn ID đã có | Không nhân bản; báo lỗi theo hợp đồng |
| Đổi hạn ID không tồn tại | Báo lỗi, không sinh ghost task |
| Reschedule A@5 thành A@5 | Vẫn chỉ một ID sống, token mới không làm hiện bản cũ |
| Hủy A@5, tạo lại A@5 | Entry heap thế hệ cũ bị nhận diện stale |
| Đổi hạn từ 0 sang U-1 | Tần suất hai biên thay đổi đúng |
| Hủy toàn bộ | Peek/take trả None, tổng Fenwick bằng 0 |
| Stale nằm ở đỉnh heap | Peek phải loại rồi xét tiếp |
| Heap bị đầy entry stale | Compact giữ nguyên tập task hiện hành |
| take_next liên tục tới rỗng | Không lặp ID bị lấy ra |
| Count [a,b] đóng | Nhận cả hai biên, xử lý a=b |
| Range a>b | Báo lỗi, không tự đổi chỗ nếu hợp đồng không cho phép |

**Kiểm thử tính đúng trước tối ưu:** Một phiên bản mới có thể ít thao tác CPU hơn do quên cập nhật Fenwick hoặc quên kiểm tra stale. Nó không phải “nhanh hơn” nếu count hoặc peek trả sai.

## 22. Benchmark: thiết kế thí nghiệm để kiểm tra giả thuyết hiệu năng

Một câu báo cáo kiểu “phiên bản mới nhanh hơn 100 lần” chỉ đáng tin khi ghi rõ **môi trường, dữ liệu, workload và cách đo**. Bài học này không cần số liệu đo thực tế để kết luận Big-O, nhưng muốn quyết định triển khai production phải benchmark.

### 22.1. Hai loại benchmark riêng biệt

**Microbenchmark:** đo chi phí từng thao tác trên những kích thước n:

- schedule ở **đầu, giữa và cuối** thứ tự deadline.
- cancel một ID ở **đầu, giữa và cuối** mảng.
- reschedule từ đầu sang cuối và ngược lại.
- get một ID tồn tại hoặc không tồn tại.
- peek_next khi heap có ít hoặc nhiều stale ở đỉnh.
- count_range với khoảng ngắn, khoảng rộng và hai biên trùng nhau.

**Workload benchmark:** chạy tỷ lệ thao tác gần thực tế, có phân bố deadline và ID giống hệ thống vận hành. Ví dụ 4.000 cập nhật/giây, 1.000 get, 200 count và 100 peek/take trong mô hình tải được kiểm soát.

Microbenchmark làm rõ **nguyên nhân**. Workload benchmark đánh giá **tổng chi phí** khi các thao tác tương tác, gồm heap compaction, cache, cấp phát và tranh chấp tài nguyên.

### 22.2. Các phân bố deadline nên thử

| Phân bố | Vì sao quan trọng |
| --- | --- |
| Gần đều trên \([0,U-1]\) | Baseline cho vị trí insert trong mảng |
| Hầu hết deadline nhỏ | Chèn gần đầu mảng gây dịch dài |
| Hầu hết deadline lớn | Chèn gần cuối có thể rẻ hơn, nhưng cancel/get vẫn khó |
| Tất cả deadline bằng nhau | Tie theo ID; hoạt động của token và heap |
| ID bị reschedule lặp lại | Heap stale và compact |
| Hủy nhiều ID liên tiếp | Ngưỡng compact, Fenwick không được âm |
| Miền U tăng dần | Chi phí \(O(U)\) và bộ nhớ Fenwick |
| Chỉ schedule, rất ít cancel | Mảng sắp có thể cạnh tranh khi hầu hết chèn cuối |

### 22.3. Chỉ số phải ghi

**Throughput:** số thao tác hoàn thành mỗi giây, theo từng loại.

**Latency:** p50/p95/p99, **kể cả update gây compact heap**.

**Bộ nhớ:** active records, H vật lý, U Fenwick, bộ nhớ tạm compact, các object Python/allocator.

**Counter nội bộ:** số lần shift mảng, số heappush/heappop stale, số compact, H/n, số Fenwick add/prefix.

**Correctness:** số sai lệch so oracle; yêu cầu là **0**.

**Độ bền dữ liệu:** nếu bài toán production cần persistence, đo WAL/fsync/recovery ngoài các cấu trúc trong RAM.

### 22.4. Không trộn thời gian xây và thời gian truy vấn

Ví dụ mảng sắp có thể được dựng từ tập task có sẵn bằng **một lần sort**:

\[
\boxed{O(n\log n)}
\]

trong khi thêm từng task bằng insort có thể tích lũy \(O(n^2)\) lần dịch tham chiếu nếu phải chèn giữa nhiều lần. Hai cách xây có chi phí khác nhau dù kết quả vật lý cuối giống nhau.

Tương tự, Fenwick có thể được xây từ một mảng tần suất bằng một thủ tục tuyến tính \(O(U)\), thay vì gọi add cho mọi ID; và heapify từ một danh sách n entry có \(O(n)\) thời gian. Không nên ghi “phải insert n lần \(O(n\log n)\)” khi giao diện có **bulk-build** hiệu quả hơn.

### 22.5. Cách đọc kết quả

Nếu baseline thắng ở n=100 nhưng thua rất mạnh ở n=100.000, đây là dấu hiệu **crossover** giữa overhead cố định và chi phí bậc lớn.

Nếu IndexedScheduler có p99 update cao do compact, không có nghĩa toàn bộ thiết kế sai; cần xem công việc có thể chuyển thành **các bước compact gia tăng** hay thay heap lazy bằng **indexed heap**.

Nếu count_range hiếm đến mức gần như không được dùng, Fenwick có thể là một chỉ mục phụ không đáng duy trì. Khi đó chỉ dùng HashMap + heap có thể giảm overhead ghi và bộ nhớ; đây là quyết định dựa trên **workload mới**, không phải phủ nhận thuật toán Fenwick.

## 23. Kiểm chứng bất biến bằng chứng minh quy nạp

Các test cung cấp bằng chứng trên những chuỗi hữu hạn. Để hiểu sâu hơn, ta thử chứng minh thiết kế IndexedScheduler đúng theo **quy nạp trên số thao tác**.

### Trường hợp cơ sở

Khi vừa khởi tạo:

\[
Active=\varnothing,\quad Heap=\varnothing,\quad
\forall t,\ freq[t]=0.
\]

Vậy ID là duy nhất, Fenwick đúng, và min không tồn tại: peek/take trả None.

### Bước schedule

Giả sử bất biến đúng trước schedule(id,t), với id chưa sống:

1. Thêm id một lần vào Active với token mới.
2. Cộng đúng 1 tại freq[t] nên Fenwick vẫn khớp Active.
3. Thêm đúng một heap-entry khớp bản ghi mới vào heap.
4. Token mới không trùng thế hệ cũ, nên các entry cũ vẫn stale.

Suy ra các bất biến được giữ.

### Bước cancel

Nếu ID không sống, không thay đổi gì. Nếu ID sống:

1. Xóa đúng một bản ghi Active.
2. Trừ đúng 1 tại deadline cũ trong Fenwick.
3. Heap-entry tương ứng lập tức trở thành stale vì Active không còn ID.
4. Những ID sống khác vẫn có entry hợp lệ của riêng chúng.

Do đó không có bản ghi đã hủy được peek/take trả hợp lệ.

### Bước reschedule

Đổi ID từ \(t_{old}\) sang \(t_{new}\):

1. Trừ freq[\(t_{old}\)].
2. Thay Active[id] bằng cặp deadline/token mới.
3. Cộng freq[\(t_{new}\)].
4. Đưa entry mới vào heap; entry cũ không còn khớp Active.

Hàm tổng tần suất không đổi vì một -1 đi cùng một +1. ID vẫn có một phiên bản sống. Nếu hạn mới bằng hạn cũ, hai lần cộng/trừ tại cùng vị trí tự triệt tiêu.

### Bước take_next

Đầu tiên loại mọi stale entry ở đỉnh. Vì mỗi ID sống có entry hợp lệ và heap duy trì thứ tự khóa, entry hợp lệ đầu tiên ở đỉnh có cặp \((deadline,id)\) nhỏ nhất của Active. Sau khi pop, xóa Active và trừ Fenwick tại hạn tương ứng. Bất biến cho các ID còn lại vẫn đúng.

### Bước compact

Heap mới được tạo **chỉ từ Active**, mỗi ID đúng một entry, sau đó heapify. Vì Active/Fenwick không đổi, compact không thay trạng thái logic hoặc kết quả query; nó chỉ loại entry stale và tái tổ chức bộ nhớ.

### Phạm vi của chứng minh

Lập luận giả định:

- Thao tác chạy **tuần tự, không bị quan sát giữa chừng**.
- Bộ nhớ và số học không gặp lỗi ngoài mô hình.
- Heap operations duy trì min-heap property.
- HashMap không đánh mất khóa; token không va chạm trong vòng đời cần xét.
- Mọi cập nhật Fenwick được thực hiện đầy đủ.

Nếu thêm concurrency, exceptions giữa các bước hoặc persistence, phải **mở rộng bất biến và chứng minh tính nguyên tử/phục hồi**, không thể tái sử dụng nguyên xi lập luận tuần tự.

## 24. Các thiết kế sai tương tự trong những cấu trúc khác

Ca điều phối tác vụ chỉ là một ví dụ của một mô thức rộng hơn: **chọn một cấu trúc vì một thao tác thuận lợi rồi bỏ qua thao tác chiếm phần lớn workload**.

| Thiết kế dễ mắc | Vì sao có thể sai | Lựa chọn cần xem xét |
| --- | --- | --- |
| Dùng dynamic array và xóa đầu làm FIFO queue | Mỗi lần xóa đầu dịch \(O(n)\) phần tử | Ring buffer hoặc deque |
| Dùng linked list để phục vụ truy cập ngẫu nhiên theo chỉ số liên tục | Đi đến phần tử i tốn \(O(i)\); locality kém | Dynamic array khi random access chiếm ưu thế |
| Dùng unsorted array làm priority queue với rất nhiều extract-min | Mỗi extract-min cần quét \(O(n)\) | Min-heap hoặc cấu trúc có thứ tự |
| Dùng hash map để đáp ứng nhiều truy vấn khoảng \([a,b]\) theo khóa | Hashing không duy trì thứ tự | Balanced BST, B-tree, segment/Fenwick phù hợp miền |
| Dùng BST không tự cân bằng cho khóa chèn đã sắp | Có thể tạo đường dài \(\Theta(n)\) | AVL/red-black tree hoặc bulk build cân bằng |
| Dùng stack để mô phỏng hàng chờ BFS | LIFO khác FIFO, thay đổi thứ tự duyệt/đường đi | Queue/deque |
| Dùng DSU để hỗ trợ xóa cạnh đồ thị tùy ý và hỏi connected ngay | DSU tiêu chuẩn hỗ trợ hợp tập, không hỗ trợ split sau xóa | Dynamic connectivity hoặc xử lý offline phù hợp |
| Dùng Bloom filter làm nguồn chân lý duy nhất cho membership chính xác | Có false positive, không lưu ID/giá trị đầy đủ | Hash set/map nguồn dữ liệu; Bloom chỉ là tầng lọc |
| Dùng k-d tree điểm cho truy vấn giao nhiều đa giác lớn mà không thiết kế hộp bao | Chỉ mục điểm không tự trả lời giao hình có diện tích | R-tree hoặc chỉ mục MBR + refine hình |
| Dùng sorted array cho bảng giá cập nhật từng mili-giây | Insert/delete ở giữa dịch nhiều phần tử | Balanced ordered index, log-structured/batch tùy workload |

### Một ví dụ cực ngắn về queue

Giả sử dịch vụ nhận 500.000 tin nhắn và liên tục xử lý phần tử đầu. Với một dynamic array, thao tác xóa index 0 có thể khiến gần 500.000 phần tử còn lại dịch trái. Nếu thay bằng **ring buffer**, ta chỉ tăng head modulo capacity:

\[
\boxed{head=(head+1)\bmod capacity.}
\]

Lấy đầu của ring buffer có thể \(O(1)\) trên bộ nhớ đã cấp phát. Nhưng ring buffer cần quản lý **head, tail, size, vòng quay và resize**, nên việc chọn cấu trúc mới cũng đòi kiểm chứng bất biến.

### Không thần thánh hóa cấu trúc “đúng”

HashMap thường có thao tác trung bình \(O(1)\) nhưng không có thứ tự; AVL bảo đảm cân bằng nhưng chứa overhead con trỏ; B-tree tốt cho page/block; heap hỗ trợ min nhưng không trực tiếp range count. Một giải pháp đúng là **cấu trúc thích hợp nhất với các thao tác và ràng buộc đang có**, chứ không phải danh sách cấu trúc được xem là “nâng cao”.

## 25. Quy trình review một thiết kế sai: từ yêu cầu tới quyết định

Khi gặp một hệ thống chậm, reviewer có thể dùng quy trình tám bước:

1. **Định nghĩa dữ liệu logic và bất biến.** ID nào duy nhất? Biên khoảng đóng/mở? Khóa ưu tiên tie thế nào? Hủy rồi tạo lại có hợp lệ không?
2. **Liệt kê toàn bộ thao tác.** Không bỏ qua xóa, cập nhật khóa, lấy ra khỏi cấu trúc hay query thứ tự/khoảng.
3. **Đo tần suất và phân bố dữ liệu.** Ví dụ 4.000 update/giây chứ không chỉ nói “đọc nhiều”.
4. **Viết bảng chi phí từng thao tác trên cấu trúc hiện tại.** Tách tìm vị trí và **dịch phần tử**, phân biệt average/worst/amortized.
5. **Tái tạo một trường hợp gây suy giảm.** Chèn giữa mảng, xóa đầu, khóa trùng, cập nhật ID cũ.
6. **Đưa ra ít nhất hai phương án sửa.** Ví dụ indexed heap+Fenwick và balanced tree có subtree size; đánh giá bộ nhớ/độ phức tạp duy trì.
7. **Chứng minh và kiểm thử tính đúng trước benchmark.** Có oracle độc lập, differential tests, thử các biên, xác nhận không double-count/stale.
8. **Benchmark cùng workload, lập kế hoạch migration.** So p95/p99, bộ nhớ, chi phí xây/cập nhật, khả năng rollback và kết quả nghiệp vụ.

### Một báo cáo review ngắn nên có gì?

~~~text
Symptom:
  p99 của cancel/reschedule tăng khi số task tăng.

Root cause:
  Mảng sắp theo deadline; cancel tìm ID tuyến tính,
  insert/delete dịch nhiều phần tử O(n).

Correctness risk:
  Map ID->index dễ stale sau insert; reschedule sửa tại chỗ
  có thể phá thứ tự mảng.

Candidate:
  HashMap ID->(deadline,token), min-heap lazy,
  Fenwick đếm deadline theo miền 0..U-1.

Tradeoffs:
  Bộ nhớ thêm O(U+H), cần compact và đồng bộ ba index.

Validation:
  Cùng chuỗi thao tác với oracle; test ID trùng deadline,
  hủy/tạo lại, count biên, nhiều stale và take_next tới rỗng.

Performance:
  Đo throughput, p50/p95/p99, tần suất compact và H/n
  trên workload giống production; không suy speedup từ Big-O.
~~~

## 26. Bài tập thực hành và lời giải

### Câu 1. Tìm lỗi trong câu “đã dùng binary search nên chèn \(O(\log n)\)”

Một nhóm dùng binary search để tìm vị trí rồi insert vào dynamic array có n phần tử. Hãy chỉ ra chi phí thực.

**Lời giải:** Binary search tìm vị trí \(O(\log n)\), nhưng chèn vào giữa phải dịch tới \(O(n)\) phần tử. Vì:

\[
\boxed{O(\log n)+O(n)=O(n),}
\]

nên khẳng định tổng chi phí chèn \(O(\log n)\) là **sai**.

### Câu 2. Đếm số phần tử phải dịch

Mảng có 10 phần tử (index 0..9). Chèn một phần tử tại index 3 khiến bao nhiêu phần tử cũ phải dịch sang phải?

**Lời giải:** Các phần tử cũ tại index 3..9 phải dịch, tổng cộng:

\[
\boxed{10-3=7\text{ phần tử}.}
\]

Đây là minh họa chi phí dịch chứ không phải số phép so sánh của binary search.

### Câu 3. Xóa phần tử đầu mảng

Một dynamic array có 100.000 task. Thao tác take_next xóa A[0] cần dời bao nhiêu phần tử còn lại nếu giữ liên tiếp?

**Lời giải:** Cần dịch **99.999 phần tử** về trái một vị trí, là \(O(n)\). Ngược lại một min-heap có thể pop minimum rồi sửa heap trong \(O(\log H)\).

### Câu 4. Tại sao HashMap ID → vị trí chưa đủ?

Mảng [A@2,B@4,D@7,E@9] có by_id[D]=2. Chèn X@5 trước D, nhưng không cập nhật by_id[D]. Khi cancel(D), chương trình dùng vị trí 2. Nó có thể xóa gì?

**Lời giải:** Sau chèn, index 2 chứa **X@5**; D chuyển sang index 3. Dùng by_id[D]=2 có thể **xóa nhầm X**, làm mất dữ liệu đúng. Cập nhật vị trí tất cả entry bị dời cũng có chi phí \(O(n)\).

### Câu 5. Reschedule sai tại chỗ

Mảng [A@1,B@3,C@7] được sắp theo deadline. Chương trình thay trực tiếp B@3 thành B@10 nhưng không di chuyển entry. Bất biến nào bị phá?

**Lời giải:** Mảng thành [A@1,B@10,C@7], nên \(K(B)>K(C)\) ở hai phần tử liên tiếp. Bất biến **sắp tăng dần** bị phá; binary search và peek/take theo mảng sắp không còn được bảo đảm.

### Câu 6. Tính tải dịch tham chiếu giả định

Có 4.000 update/giây. Mỗi update giả định dịch trung bình 50.000 tham chiếu. Tính số lượt dịch trong một giây.

**Lời giải:**

\[
\boxed{4\,000\times50\,000=200\,000\,000.}
\]

Đây là **ước lượng workload**, không phải số đo CPU hay benchmark. Nó cho thấy vì sao update \(O(n)\) có thể không phù hợp n lớn.

### Câu 7. Một min-heap có đủ đáp ứng get(id) không?

Một heap chỉ có các cặp \((deadline,id)\). Người dùng hỏi deadline của ID X bất kỳ. Có thể bảo đảm \(O(\log n)\) chỉ dựa trên min-heap property không?

**Lời giải:** **Không.** Heap property chỉ cho quan hệ ưu tiên giữa cha và con, không sắp theo ID. Không có index phụ, có thể phải tìm tuyến tính \(O(n)\). Thêm **HashMap ID → record** giải quyết lookup trung bình.

### Câu 8. HashMap đơn có đủ đáp ứng peek_next không?

HashMap lưu deadline cho 100.000 ID. Không có heap/cấu trúc theo thứ tự. Để tìm deadline nhỏ nhất chính xác, phải làm gì?

**Lời giải:** Thường phải quét **mọi bản ghi**, \(O(n)\). HashMap không tự duy trì thứ tự deadline. Dùng min-heap hoặc một ordered structure để hỗ trợ minimum.

### Câu 9. Count khác list theo khoảng

Fenwick lưu tần suất số tác vụ theo phút. Nó cho biết count_range(4,7)=200. Có thể liệt kê 200 ID chỉ từ các số tần suất không?

**Lời giải:** **Không.** Aggregate theo phút không lưu danh tính. Cần chỉ mục bổ sung để tìm các ID; dù có chỉ mục phù hợp, xuất 200 ID vẫn cần \(\Omega(200)\) thao tác.

### Câu 10. Tính đoạn đóng

Cho freq[0..6]=[0,1,0,2,1,0,1]. Count trên \([3,4]\) là bao nhiêu?

**Lời giải:** \(freq[3]+freq[4]=2+1=\boxed{3}\). Công thức:

\[
\boxed{prefix(5)-prefix(3)=4-1=3.}
\]

### Câu 11. Cập nhật Fenwick khi đổi hạn

X chuyển từ deadline 3 sang 6. Hãy ghi hai update bắt buộc lên Fenwick.

**Lời giải:**

~~~text
Fenwick.add(3, -1)
Fenwick.add(6, +1)
~~~

Tổng task không đổi. Nếu quên bước -1, count theo hạn cũ và tổng số task sẽ bị tăng sai.

### Câu 12. Hai biên của miền deadline

U=8. Deadline hợp lệ nhỏ nhất/lớn nhất là gì? Count đoạn đóng \([0,7]\) tính theo prefix nào?

**Lời giải:** Hợp lệ là **0 và 7**. Với quy ước tổng tiền tố loại trừ cận trên:

\[
\boxed{count\_range(0,7)=prefix(8)-prefix(0).}
\]

Deadline=8 nằm ngoài miền, phải bị từ chối hoặc được xử lý bởi một chính sách mở rộng miền rõ ràng.

### Câu 13. Tác vụ có cùng hạn

Có A@5, C@5, B@5. Theo tie-break \((deadline,id)\), peek_next trả ID nào?

**Lời giải:** **A**, vì cả ba cùng deadline 5 và A là ID nhỏ nhất theo thứ tự từ điển. Tác vụ B đứng trước C nhưng sau A.

### Câu 14. Vì sao token cần không tái sử dụng?

Heap còn stale entry (10,"A",1). Hủy A rồi schedule lại A@10 và cũng cấp token=1. Chuyện gì có thể xảy ra?

**Lời giải:** Cả entry cũ và mới đều khớp Active (10,1); cùng ID có thể bị xem hợp lệ **hai lần**. Có nguy cơ trả trùng sau take. Token phải khác giữa các thế hệ còn có thể cùng tồn tại trong heap.

### Câu 15. Cancel không cần tìm ID trong heap

Giả sử heap có 500.000 entry, nhưng HashMap đang giữ A → (7,token). Để hủy A trong thiết kế lazy, cần cập nhật những gì ngay lập tức?

**Lời giải:** Xóa A khỏi **Active** và Fenwick.add(7,-1); heap-entry A trở thành **stale**. Không phải duyệt 500.000 entry để tìm A. Sau đó có thể compact nếu vượt ngưỡng.

### Câu 16. Đỉnh heap stale

Heap có top entry A@1 đã cancel, còn B@2 đang sống. Peek_next nên trả gì?

**Lời giải:** Loại A@1 khỏi đỉnh vì không khớp Active, rồi tiếp tục kiểm tra heap. Kết quả đúng là **B@2**, không phải None hay A@1.

### Câu 17. Ngưỡng compact

Chính sách compact khi \(H>\max(16,2n)\). Với \(n=20,H=41\), có compact không? Với \(n=20,H=40\) thì sao?

**Lời giải:** Ngưỡng là \(\max(16,40)=40\). **H=41** kích hoạt compact; **H=40** không, vì điều kiện là dấu **lớn hơn nghiêm ngặt**.

### Câu 18. Chi phí một lần compact

Heap cũ H=200.000 entry, chỉ 50.000 ID sống. Rebuild bằng heapify từ 50.000 entry hợp lệ có chi phí theo Big-O nào?

**Lời giải:** Dựng danh sách từ Active và heapify có:

\[
\boxed{O(n)=O(50\,000)}
\]

thao tác ở mô hình hằng số cho các khóa, không phải \(O(n\log n)\) nếu dùng **heapify** đúng cách. Một update kích hoạt compact vẫn có spike \(O(n)\).

### Câu 19. Average và worst-case khác nhau

HashMap thường cho get(id) trung bình \(O(1)\). Có nên báo **worst-case luôn \(O(1)\)** cho mọi bảng băm và mọi dữ liệu không?

**Lời giải:** **Không.** Chi phí phụ thuộc hash function, collision, rehash và giả thiết tải. Phát biểu an toàn ở đây là **\(O(1)\) trung bình dưới giả thiết bảng băm phù hợp**; trường hợp xấu có thể tốn hơn.

### Câu 20. Miền deadline không còn hữu hạn

Do sản phẩm đổi yêu cầu, deadline có thể là timestamp bất kỳ trong 100 năm với độ chính xác nanosecond. Vì sao Fenwick dày theo từng đơn vị không phù hợp?

**Lời giải:** Miền chỉ số U trở nên quá lớn, cần **\(O(U)\) bộ nhớ**. Có thể xem **augmented balanced BST**, ordered index, bucket theo thời gian hoặc một chiến lược nén tọa độ có cập nhật/rebuild rõ ràng.

### Câu 21. Viết một oracle cho peek_next

Với dictionary Active đơn giản ID → deadline, viết công thức toán học cho peek_next; nếu không có tác vụ thì trả gì?

**Lời giải:**

\[
\boxed{
id^*=\arg\min_{id\in Active}(Active[id],id).
}
\]

Nếu Active rỗng trả **None**. Oracle có thể duyệt toàn bộ dictionary trong \(O(n)\), nhưng độc lập với cấu trúc tối ưu.

### Câu 22. Chứng minh count không âm

Khi nào có thể khẳng định Fenwick đếm theo từng deadline không âm?

**Lời giải:** Khi mọi cancel/take chỉ trừ cho **ID đang hoạt động đúng một lần**, mọi reschedule luôn trừ deadline cũ và cộng deadline mới, còn schedule chỉ cộng cho ID chưa có. Khi ấy:

\[
\boxed{freq[t]=\#\{id\in Active:deadline(id)=t\}\ge0.}
\]

Nếu một phép cancel trừ hai lần, bất biến bị phá.

### Câu 23. Sự khác nhau giữa peek và take

Min-heap và mảng sắp đều peek minimum nhanh. Vì sao so riêng peek_next có thể cho quyết định chọn cấu trúc sai?

**Lời giải:** Dịch vụ thường phải **lấy ra và xóa** tác vụ đã xử lý. Mảng sắp take_next bằng xóa phần tử đầu có chi phí \(O(n)\), trong khi min-heap pop có \(O(\log H)\) cộng việc dọn stale. Cần benchmark **toàn vòng đời**.

### Câu 24. Chọn lại cấu trúc khi workload đổi

Hệ thống nay chỉ cập nhật vài lần mỗi ngày, nhưng có hàng triệu lần **liệt kê toàn bộ task trong một đoạn deadline**. Fenwick đếm đơn thuần và min-heap có đủ không? Hãy đề xuất hướng thay.

**Lời giải:** **Không đủ để range reporting hiệu quả.** Fenwick trả count nhưng không lưu danh sách ID theo đoạn; heap cũng không duyệt ordered interval thuận lợi. Với ít update, có thể cân nhắc **mảng sắp** và binary search hai biên rồi duyệt \(k\) phần tử, hoặc **balanced ordered tree/B-tree** nếu vẫn cần nhiều update. Quyết định theo \(q_{\mathrm{range}}\), \(q_{\mathrm{update}}\), n và chi phí build/rebuild.

## 27. Kết luận: phát hiện cấu trúc sai bằng bất biến và workload

Thiết kế ban đầu dùng **một mảng đã sắp** vì phép peek minimum có vẻ rất nhanh. Nhưng hệ thống còn phải **chèn, hủy, đổi hạn và lấy phần tử sớm nhất ra** ở tần suất cao. Binary search chỉ giảm thời gian **tìm vị trí**, không loại bỏ chi phí \(O(n)\) **dịch phần tử** của dynamic array; cancel theo ID còn phải tìm tuyến tính nếu mảng sắp theo deadline.

Thiết kế mới phân rã yêu cầu:

\[
\boxed{
\underbrace{HashMap}_{\text{ID lookup}}
\quad+\quad
\underbrace{MinHeap}_{\text{minimum}}
\quad+\quad
\underbrace{Fenwick}_{\text{count theo phút}}.
}
\]

Với miền deadline nguyên hữu hạn, cách này chuyển phần lớn update từ \(O(n)\) sang \(O(\log H+\log U)\) hoặc \(O(\log U)\) khi **không compact**, và get sang \(O(1)\) trung bình. Chi phí đổi lại là **bộ nhớ chỉ mục phụ**, bất biến đồng bộ, stale heap-entry, compaction và độ phức tạp triển khai.

**Lựa chọn không đúng theo tên cấu trúc mà đúng theo hợp đồng.** Nếu cần interval reporting hoặc timestamp không giới hạn, một **ordered balanced tree có subtree size**, B-tree hay chiến lược index khác có thể phù hợp hơn. Nếu n nhỏ hoặc cập nhật rất ít, sorted array hay quét tuần tự có thể hoàn toàn hợp lý.

Khi review một thiết kế, nên luôn trả lời:

1. **Những thao tác nào phải đúng?** ID trùng, biên đoạn, tie, hủy/tạo lại và dữ liệu rỗng xử lý ra sao?
2. **Những thao tác nào xảy ra nhiều nhất?** Tần suất và phân bố tải ảnh hưởng tổng chi phí thế nào?
3. **Cấu trúc hiện tại giữ bất biến bằng công việc gì?** Tìm, dịch mảng, cân bằng cây, sift heap, cập nhật Fenwick hay rebuild?
4. **Có phản ví dụ cụ thể không?** Một lần insert giữa mảng, map vị trí stale hoặc token bị tái sử dụng có thể chứng minh sai lầm rõ hơn một câu khẳng định chung.
5. **Giải pháp mới được kiểm chứng ra sao?** Chứng minh bất biến, oracle độc lập, differential tests, test biên và benchmark cùng workload.

> **Bài học cuối:** Một cấu trúc dữ liệu không “tốt” hoặc “xấu” độc lập với bài toán. Thiết kế đúng là thiết kế **giữ toàn vẹn dữ liệu, hỗ trợ những thao tác thực sự cần thiết và có chi phí phù hợp với workload**, kể cả khi workload thay đổi trong tương lai.
