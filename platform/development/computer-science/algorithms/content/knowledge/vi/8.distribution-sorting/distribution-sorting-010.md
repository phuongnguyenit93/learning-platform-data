# Chọn giữa sắp xếp phân phối và sắp xếp so sánh

**Sắp xếp so sánh (comparison sorting)** quyết định thứ tự bằng cách so sánh các khóa với nhau. **Sắp xếp phân phối (distribution sorting)** tận dụng cấu trúc của khóa — như miền giá trị nguyên, chữ số, hoặc giả thiết phân bố — để đếm, phân loại hay đưa phần tử vào các nhóm trước khi xuất kết quả theo thứ tự. Không có họ thuật toán nào luôn thắng: tốc độ, bộ nhớ, tính ổn định, kiểu khóa và giới hạn đề bài quyết định lựa chọn.

Bài học này tập trung vào **cách ra quyết định**, không chỉ nhớ độ phức tạp của từng thuật toán. Các thuật toán đại diện là sắp xếp đếm (*counting sort*), sắp xếp cơ số (*radix sort*), sắp xếp theo thùng (*bucket sort*) và các thuật toán dựa trên so sánh như merge sort, heap sort, quicksort hoặc API sắp xếp của Java.

**Mục tiêu:** giải thích vì sao cận dưới Ω(n log n) chỉ áp dụng cho mô hình sắp xếp dựa trên so sánh; tính được kích thước miền khóa và chi phí O(n+k) của counting sort; nêu đúng giả thiết O(d(n+b)) của radix sort và chi phí kỳ vọng của bucket sort; so sánh yêu cầu ổn định, bộ nhớ và tính tổng quát; thực hiện quyết định có cơ sở bằng ví dụ Java 17+.

## 1. Làm rõ bài toán trước khi chọn thuật toán

Giả sử có `n` bản ghi cần sắp xếp theo một khóa. Trước khi chọn thuật toán, phải phân biệt:

- **Kiểu khóa:** số nguyên có giới hạn, số thực, chuỗi, cặp khóa hay đối tượng có `Comparator`? Khóa có thể âm, trùng nhau hoặc thay đổi kích thước không?
- **Miền khóa:** nếu là số nguyên trong `[min,max]`, số giá trị có thể có là `k=max−min+1`. Giá trị `k` khác hẳn số phần tử `n`.
- **Kiểu kết quả:** cần dãy số đã sắp xếp, hay các bản ghi nguyên vẹn và giữ thứ tự tương đối giữa các bản ghi có cùng khóa?
- **Dữ liệu tĩnh hay liên tục cập nhật:** sắp xếp một lần hay phải duy trì thứ tự khi thêm/xóa phần tử?
- **Ngân sách:** bao nhiêu RAM, thời gian, I/O; có được phép tạo mảng phụ độ dài `n` hoặc bộ đếm độ dài `k` không?
- **Đầu vào gần có thứ tự không:** nhiều thuật toán so sánh có thể khai thác các đoạn đã sắp xếp; không nên tự động coi mọi trường hợp đều ngẫu nhiên.

**Tính đúng đắn luôn ưu tiên:** nếu thuật toán giả định khóa là số nguyên trong một miền nhỏ nhưng dữ liệu thực tế không thỏa điều kiện đó, kết quả hoặc việc cấp phát có thể sai dù công thức Big-O trông hấp dẫn.

## 2. Sắp xếp so sánh: tổng quát và cận dưới

Một thuật toán sắp xếp **chỉ dựa vào các phép so sánh giữa khóa** dùng những kết quả như `a<b`, `a==b` hoặc `compare(a,b)` để quyết định thứ tự. Ví dụ:

- **Merge sort:** chia dãy thành các phần, sắp xếp rồi trộn; thời gian xấu nhất Θ(n log n), có thể thực hiện ổn định, thường cần bộ nhớ phụ Θ(n).
- **Heap sort:** khai thác heap; thời gian xấu nhất Θ(n log n), có thể thực hiện với O(1) bộ nhớ phụ trên mảng, nhưng bản tiêu chuẩn không ổn định.
- **Quicksort:** chọn pivot và phân hoạch; trung bình O(n log n) dưới các giả định thích hợp, bản đơn giản có trường hợp xấu Θ(n²). Biến thể và cách chọn pivot ảnh hưởng bảo đảm thực tế.
- **Các thư viện sắp xếp có tối ưu:** có thể khai thác nhiều đặc điểm của dữ liệu, có cơ chế chuyên biệt cho kiểu primitive hoặc đối tượng. Không suy luận rằng một API cụ thể dùng đúng một trong ba thuật toán lý thuyết trên trong mọi phiên bản.

### Vì sao thường xuất hiện Ω(n log n)?

Với `n` khóa **phân biệt**, có `n!` thứ tự đầu vào khả dĩ. Trong mô hình cây quyết định mà mỗi phép so sánh có tối đa một số hữu hạn kết quả (thường xét so sánh hai hướng với khóa phân biệt), để xác định đúng thứ tự trong trường hợp xấu, cây phải phân biệt ít nhất `n!` trường hợp. Độ sâu cần thiết có cận:

`Ω(log₂(n!)) = Ω(n log n)`.

Do đó mọi thuật toán **sắp xếp tổng quát, dựa thuần trên so sánh**, có cận dưới Ω(n log n) về số phép so sánh trong trường hợp xấu. Đây không phải là phát biểu “không thể sắp xếp nhanh hơn O(n log n)”. Sắp xếp phân phối có thể sử dụng thông tin về **biểu diễn và miền của khóa**, chứ không chỉ quan hệ lớn-bé giữa hai khóa, nên không bị ràng buộc bởi cận dưới này theo cùng một mô hình.

Cận dưới cũng không có nghĩa mọi đầu vào đều cần Ω(n log n) phép so sánh: dữ liệu đã sắp xếp, miền giá trị bị giới hạn, hoặc một giả thiết bổ sung khác có thể cho phép xử lý nhanh hơn. Cần phân biệt **cận dưới xấu nhất cho bài toán tổng quát** với **chi phí trên một lớp đầu vào đã có cấu trúc**.

## 3. Counting sort: chọn khi miền giá trị đủ nhỏ

**Counting sort** thích hợp khi khóa là số nguyên hoặc có thể ánh xạ chính xác tới các **chỉ số nguyên rời rạc** trên một miền có thể cấp phát được.

Đặt `min` là khóa nhỏ nhất, `max` là khóa lớn nhất, `k=max−min+1`. Dùng mảng `count[0..k−1]`, trong đó khóa `x` tương ứng vị trí:

`index(x)=x−min`.

Có hai nhu cầu cần tách bạch.

**Nếu chỉ sắp xếp các giá trị số nguyên**, có thể đếm tần suất, sau đó xuất từng giá trị đúng số lần. Không cần giữ đối tượng ban đầu. Nếu chỉ cần dãy số, cách này đơn giản.

**Nếu sắp xếp các bản ghi có dữ liệu đi kèm**, cần giữ bản ghi và có thể cần **ổn định**. Phiên bản counting sort ổn định xây các vị trí kết thúc tích lũy rồi duyệt đầu vào **từ phải sang trái** để đặt mỗi bản ghi vào vị trí thích hợp trong mảng đầu ra. Nhờ đó các bản ghi có cùng khóa vẫn giữ thứ tự trước-sau như ban đầu.

### Ví dụ có khóa âm và bản ghi trùng khóa

Cho dãy bản ghi `(key,id)`:

`[(3,A),(-1,B),(3,C),(0,D),(-1,E),(2,F)]`.

Ở đây `min=-1`, `max=3`, `k=5`. Mảng đếm theo khóa `[-1,0,1,2,3]` là:

`count=[2,1,0,1,2]`.

Tổng tích lũy số phần tử có khóa ≤ từng khóa là:

`end=[2,3,3,4,6]`.

Duyệt ngược và đặt bản ghi vào `output[--end[index(key)]]` thu được:

`[(-1,B),(-1,E),(0,D),(2,F),(3,A),(3,C)]`.

Hai bản ghi khóa -1 vẫn theo thứ tự B trước E; khóa 3 vẫn A trước C. Đây là **ổn định**. Nếu chỉ so sánh giá trị khóa mà không quan tâm ID, thứ tự các bản ghi bằng khóa không hiển thị được, nên ví dụ cặp `(key,id)` hữu ích để kiểm chứng.

### Độ phức tạp và đánh đổi

- Duyệt đầu vào để lấy min/max: O(n) nếu cần.
- Khởi tạo mảng đếm kích thước k: Θ(k).
- Đếm các khóa: Θ(n).
- Tính tổng tích lũy: Θ(k) khi cần kết quả ổn định.
- Đưa n bản ghi vào mảng đầu ra: Θ(n).

Tổng thời gian **Θ(n+k)**, bộ nhớ phụ **Θ(n+k)** cho phiên bản ổn định lưu bản ghi. Nếu chỉ đếm và ghi các **giá trị khóa** trở lại mảng đầu vào, có thể dùng **O(k)** bộ nhớ phụ, nhưng không bảo đảm duy trì thứ tự các bản ghi đi kèm theo nghĩa ổn định.

**Điểm mấu chốt:** counting sort không phải O(n) một cách vô điều kiện. Nếu `k=Θ(n)` hoặc nhỏ hơn, `Θ(n+k)=Θ(n)`. Nếu `k≫n`, việc cấp phát và khởi tạo mảng `count` có thể áp đảo, thậm chí vượt bộ nhớ.

Ví dụ:

| Quy mô | Miền khóa | `k` | Đánh giá ban đầu |
|---|---|---:|---|
| `n=200.000`, điểm trong 0..1000 | 0..1000 | 1.001 | Counting sort là ứng viên mạnh |
| `n=1.000`, khóa trong -1.000.000..1.000.000 | -1.000.000..1.000.000 | 2.000.001 | Miền lớn so với n; chưa đáng tạo mảng count |
| `n=10`, khóa trải từ `Integer.MIN_VALUE` tới `Integer.MAX_VALUE` | Toàn miền int có dấu | 4.294.967.296 | Không thể cấp phát mảng đếm một phần tử cho mỗi giá trị trong Java |

Đối với trường hợp có ít **giá trị khác nhau** nhưng độ lệch giữa min và max lớn, không thể kết luận counting sort trực tiếp rẻ chỉ vì số khóa phân biệt nhỏ; k vẫn được tính theo **độ rộng miền**. Có thể cân nhắc nén tọa độ hay ánh xạ khóa, nhưng việc nén thường cần thêm công việc sắp xếp hoặc xử lý khóa riêng, nên phải tính cả chi phí đó.

### Cẩn thận với tràn số và bộ nhớ trong Java

Biểu thức sau có thể tràn `int` trước khi cấp phát:

~~~java
int width = maxKey - minKey + 1; // Có thể tràn int.
~~~

Tính bằng `long` trước:

~~~java
long width = (long) maxKey - minKey + 1L;
if (width <= 0 || width > 1_000_000L) {
    throw new IllegalArgumentException("Range too wide");
}
int[] count = new int[(int) width];
~~~

Giới hạn `1_000_000` ở đây chỉ là **chính sách bộ nhớ minh họa**, không phải quy định của counting sort. Khi chọn thuật toán thực tế, còn phải xét mảng kết quả, mảng count, cấu trúc bản ghi, heap JVM và các vùng dữ liệu tạm khác.

## 4. Radix sort: khóa có thể chia thành chữ số hoặc nhóm bit

**Radix sort** không đòi hỏi miền giá trị nguyên liên tục nhỏ như counting sort. Thay vào đó, nó xử lý **d chữ số (digits)** của mỗi khóa trong cơ số **b**, qua nhiều lượt phân phối. Ví dụ với số nguyên 32-bit và cơ số 256, mỗi chữ số tương đương một byte; có tối đa 4 lượt cho 4 byte.

Ở biến thể **LSD (least significant digit first)**, xử lý từ chữ số ít quan trọng nhất tới chữ số quan trọng nhất. **Mỗi lượt phải ổn định** để thứ tự đã thiết lập bởi các chữ số thấp không bị phá bởi lượt xử lý chữ số cao.

Với d lượt và b giá trị chữ số, nếu mỗi lượt dùng counting sort ổn định trên n phần tử:

**`T(n,d,b)=O(d(n+b))`**, bộ nhớ phụ thường **O(n+b)**.

Đây là cận theo **số lượt và cơ số**, không phải lời hứa “mọi kiểu dữ liệu đều sắp xếp trong O(n)”. Khi d hoặc b tăng theo độ dài khóa, thời gian cũng tăng. Cơ số lớn có thể giảm số lượt nhưng tăng kích thước bộ đếm và chi phí bộ nhớ; cơ số nhỏ giảm bộ đếm nhưng cần thêm lượt.

**Ví dụ:** với `int` 32-bit, dùng b=256, d=4 có thể đạt thời gian O(4(n+256)) và bộ nhớ phụ O(n+256), trong mô hình thao tác trên từ máy. Tuy nhiên, còn có chi phí xử lý bit, đọc/ghi nhiều lượt và bộ đệm trung gian. Với n rất nhỏ, thuật toán so sánh đơn giản có thể nhanh hơn dù Big-O không đẹp bằng.

### Xử lý số nguyên âm

Sắp xếp số nguyên có dấu không thể lấy các byte một cách ngây thơ rồi coi thứ tự unsigned giống thứ tự signed. Với `int` có dấu của Java, một cách ánh xạ hữu ích khi radix theo byte là:

`transformed = key ^ Integer.MIN_VALUE`.

Nếu **so sánh `transformed` theo thứ tự 32-bit không dấu**, các khóa `int` có dấu được xếp đúng thứ tự tăng dần sau phép ánh xạ. Với mỗi byte:

~~~java
// Một bước minh họa lấy chữ số 0..255; shift là 0, 8, 16 hoặc 24.
int digit = ((key ^ Integer.MIN_VALUE) >>> shift) & 0xFF;
~~~

Lưu ý: phép XOR **không biến phép so sánh int có dấu** thông thường thành cùng thứ tự; nó làm thay đổi biểu diễn để xử lý theo **thứ tự unsigned của các nhóm bit**. Khi triển khai LSD, cần chạy các lượt từ byte thấp đến byte cao và bảo đảm từng lượt phân phối ổn định.

Với **chuỗi có độ dài thay đổi**, radix sort cần quy tắc xử lý ký tự thiếu, chữ số, cách so sánh Unicode và thứ tự từ điển. Không suy ra số lượt bằng hằng số nếu độ dài khóa không bị chặn.

### Khi nào radix là lựa chọn tốt?

Radix thường đáng cân nhắc khi số khóa rất lớn, kiểu khóa có độ rộng cố định (ví dụ nhiều `int`, `long`) hoặc cấu trúc chữ số xử lý thuận tiện, và có đủ bộ nhớ cho các lượt phân phối. Nếu đối tượng có comparator tùy biến phức tạp hoặc khóa không có biểu diễn chữ số phù hợp, thuật toán so sánh thường dễ bảo đảm tính đúng và bảo trì hơn.

## 5. Bucket sort: lợi thế dựa vào phân bố, không chỉ miền

**Bucket sort** phân phối phần tử vào các **thùng** dựa trên giá trị hoặc khoảng giá trị, sau đó sắp xếp trong mỗi thùng và nối các thùng theo thứ tự. Nó đặc biệt hữu ích khi dữ liệu phân bố tương đối đều trên miền biết trước.

Giả sử có n số thực trong `[0,1)` và chọn b thùng. Một ánh xạ đơn giản là:

`bucketIndex(x) = floor(b·x)`.

Khi `0≤x<1`, chỉ số nằm trong `0..b−1`. Điều kiện **x<1** rất quan trọng: nếu x=1, công thức cho chỉ số b, vượt phạm vi. Nếu miền bao gồm biên phải, phải điều chỉnh quy tắc hoặc chặn chỉ số một cách có chủ đích.

Giả sử các phần tử độc lập và phân bố gần đều, `b=Θ(n)`, và trong từng thùng dùng thuật toán có chi phí phù hợp (chẳng hạn insertion sort cho thùng rất nhỏ). Khi đó bucket sort có thể đạt **thời gian kỳ vọng O(n+b)=O(n)**. Nếu nhiều phần tử rơi vào cùng một thùng và sắp xếp thùng đó bằng insertion sort, trường hợp xấu có thể là **Θ(n²)**.

**Điểm không được bỏ qua:** bucket sort **không có bảo đảm O(n) xấu nhất** chỉ vì dữ liệu thuộc `[0,1)`. Miền giá trị và phân bố xác suất là hai giả thiết khác nhau. Dữ liệu tập trung gần một giá trị, nhiều phần tử trùng hoặc ánh xạ phân thùng không phù hợp có thể gây mất cân bằng. Nếu trong mỗi thùng dùng thuật toán so sánh có bảo đảm O(s log s) cho thùng kích thước s, cận xấu nhất sẽ khác nhưng vẫn phải tính chi phí sắp xếp thùng.

Bucket sort còn phải xác định rõ **thứ tự giữa các thùng**: mọi giá trị của thùng thấp phải không lớn hơn mọi giá trị ở thùng cao theo comparator dùng để xuất kết quả. Nếu phân thùng theo tiêu chí không nhất quán với thứ tự cần sắp xếp, việc nối các thùng không đảm bảo kết quả đã sắp xếp.

## 6. So sánh trực diện ba kiểu phân phối và sắp xếp so sánh

| Tiêu chí | Counting sort | LSD radix sort | Bucket sort | So sánh tổng quát |
|---|---|---|---|---|
| Điều kiện khóa | Số nguyên/miền rời rạc k đủ nhỏ | Chia được thành d chữ số, b giá trị mỗi chữ số | Ánh xạ được sang các thùng có thứ tự; kỳ vọng nhanh thường cần phân bố thuận lợi | Có thứ tự so sánh nhất quán |
| Chi phí thường phân tích | Θ(n+k) | O(d(n+b)) | Kỳ vọng O(n+b) dưới giả thiết thích hợp | O(n log n) với thuật toán chuẩn có bảo đảm; quicksort đơn giản có worst Θ(n²) |
| Bộ nhớ phụ | Θ(n+k) nếu ổn định với bản ghi | O(n+b) cho bản cài đặt thông dụng | O(n+b) hoặc tùy cách lưu và xử lý thùng | Tùy thuật toán: O(1) cho heap sort, O(n) cho merge sort thông dụng |
| Ổn định | Có thể thiết kế ổn định | LSD yêu cầu phân phối ổn định mỗi lượt | Phụ thuộc xử lý thùng và thứ tự phần tử cùng khóa | Tùy thuật toán; merge sort có thể ổn định |
| Thế mạnh | Miền khóa nhỏ so với n | Khóa số/chữ số độ rộng hữu hạn, n lớn | Dữ liệu có phân bố thuận lợi | Linh hoạt với khóa và comparator phức tạp |
| Rủi ro | k quá lớn, cấp phát/tràn chỉ số | Nhiều lượt, dấu âm, bộ đệm | Thùng mất cân bằng, giả thiết phân bố sai | Giới hạn so sánh Ω(n log n) xấu nhất cho bài toán tổng quát |

**Đọc bảng một cách cẩn trọng:** “O(n log n)” không mô tả chính xác mọi API Java trên mọi kiểu dữ liệu; đó là cận thường dùng khi chọn một thuật toán so sánh có bảo đảm tương ứng. Phải biết phiên bản, kiểu phần tử và hợp đồng sử dụng. Các giá trị Big-O không tính tự động chi phí I/O, boxing, truy cập đĩa hoặc tạo kết quả in ra.

## 7. Tính ổn định (stability) và vì sao nó ảnh hưởng quyết định

Một thuật toán sắp xếp **ổn định** bảo toàn thứ tự tương đối của các bản ghi có khóa bằng nhau. Ví dụ dãy:

`[(2,A),(1,B),(2,C)]`

sắp xếp tăng theo khóa và ổn định sẽ thành:

`[(1,B),(2,A),(2,C)]`.

Nếu thuật toán thay đổi `(2,A)` và `(2,C)` thành thứ tự ngược, nó không ổn định, dù các khóa vẫn tăng dần.

Tính ổn định quan trọng khi:

- Dữ liệu đã sắp xếp trước theo một tiêu chí phụ, rồi sắp xếp theo tiêu chí chính. Thuật toán ổn định giữ thứ tự theo tiêu chí phụ bên trong các nhóm có cùng tiêu chí chính.
- Bản ghi có thứ tự thời gian/ưu tiên gốc và muốn giữ thứ tự đó với các khóa bằng nhau.
- Dùng LSD radix sort: kết quả của các lượt xử lý chữ số thấp phải được giữ trong nhóm có chữ số cao bằng nhau.

**Không nhầm ổn định với luôn “có đúng một kết quả”:** nếu yêu cầu chỉ sắp xếp mảng `int[]`, hai giá trị bằng nhau không mang ID riêng để quan sát thứ tự; tính ổn định ít ý nghĩa thực tế. Nhưng khi sắp xếp `Item(key,id)`, đổi vị trí bản ghi có cùng key có thể làm sai hợp đồng.

Trong Java, `Arrays.sort(T[], Comparator)` trên **mảng đối tượng** được tài liệu hóa là ổn định. Điều đó khác với việc mặc định coi mọi biến thể `Arrays.sort` trên mảng primitive có tính ổn định của bản ghi. Với primitive, các khóa bằng nhau không có ID đi kèm để đánh giá sự bảo toàn bản ghi. Nếu cần sắp xếp đối tượng theo khóa và giữ thứ tự bằng nhau, dùng comparator phù hợp và một API có hợp đồng ổn định, hoặc thiết kế counting/radix ổn định.

## 8. Chi phí RAM, số phép ghi, khả năng mở rộng

Big-O theo số thao tác có thể che mất khác biệt quan trọng về bộ nhớ:

- `int[k]` dành khoảng `4k` byte cho **phần tử đếm** (ngoài header và căn chỉnh của mảng Java). Với k=1.000.000, phần tử đếm đã vào khoảng 4 MB.
- Nếu cần mảng đầu ra chứa n tham chiếu tới bản ghi, còn có chi phí khoảng `n×` độ rộng tham chiếu, chưa kể bản thân các đối tượng. Với `Item[]`, hệ số phụ thuộc JVM và chế độ nén tham chiếu.
- Radix sort LSD dùng vùng đầu ra trung gian qua nhiều lượt; dù bộ đếm b nhỏ, thao tác đọc/ghi cả n phần tử lặp lại d lần. Băng thông bộ nhớ và tính cục bộ có thể quyết định hiệu năng.
- Bucket sort có thể cần lưu cấu trúc thùng và danh sách phần tử từng thùng; nếu dùng nhiều đối tượng nhỏ, việc cấp phát và GC có thể đắt.
- Thuật toán so sánh có thể sắp xếp ngay trong mảng với bộ nhớ bổ sung nhỏ (ví dụ heap sort), hoặc cần O(n) bộ nhớ phụ để đổi lấy tính ổn định và tốc độ phù hợp.

**Dữ liệu lớn hơn RAM:** nếu không thể giữ toàn bộ dữ liệu/mảng đếm trong bộ nhớ, cần xét thuật toán sắp xếp ngoài bộ nhớ (*external sorting*), ví dụ external merge sort với các lượt đọc/ghi khối. Một thuật toán tuyến tính về số phép CPU chưa chắc tốt nếu nó cần mảng đếm quá lớn hoặc truy cập bộ nhớ/đĩa không phù hợp.

**Giới hạn kiểu số:** counting sort cần tính width từ min/max bằng kiểu rộng hơn, kiểm tra trước khi ép xuống `int` hoặc cấp phát. Khi tính ngưỡng như `4*n` với n kiểu `int`, dùng `4L*n` để tránh tràn trước phép so sánh. Một thuật toán đúng về lý thuyết vẫn có thể sai hoàn toàn vì phép toán chỉ số tràn trong Java.

## 9. Quy trình chọn phương pháp có thể thực hiện từng bước

Một chiến lược đáng tin cậy là:

1. **Xác định hợp đồng thứ tự:** tăng/giảm, khóa nào, cho phép trùng không, có cần ổn định không, comparator có phức tạp không?
2. **Xác định quy mô:** n, giới hạn thời gian, RAM, số lần cần sắp xếp; mảng chứa primitive hay đối tượng?
3. **Phân tích miền khóa:** nếu khóa là số nguyên, tính `k=(long)max-(long)min+1` mà không tràn. Nếu k nhỏ và đủ RAM, cân nhắc counting.
4. **Phân tích cấu trúc chữ số:** nếu khóa có độ rộng cố định và số phần tử lớn, cân nhắc radix với b và d hợp lý; kiểm tra xử lý số âm và độ ổn định.
5. **Phân tích phân bố:** chỉ cân nhắc giả thiết kỳ vọng của bucket nếu có chứng cứ/đặc tả về phân bố; phải tính phương án xấu nếu dữ liệu lệch.
6. **Nếu không có lợi thế cấu trúc rõ ràng:** dùng một thuật toán so sánh với bảo đảm phù hợp, thường là API Java đã kiểm thử, thay vì tự viết bản phân phối dễ lỗi.
7. **Đánh giá tổng chi phí:** thêm tiền xử lý, cấp phát, số lượt đọc/ghi, trường hợp xấu, tính ổn định và công sức bảo trì.
8. **Kiểm thử với dữ liệu thực:** đo trên JVM và giới hạn bộ nhớ đại diện, có warmup nếu benchmark ngắn, tránh kết luận từ một lần chạy. Công thức tiệm cận là lý do phân tích, không thay thế đo đạc.

### Một số tình huống điển hình

| Dữ liệu / yêu cầu | Lựa chọn nên cân nhắc | Lý do chính |
|---|---|---|
| 200.000 bài kiểm tra, điểm nguyên 0..1000, cần sắp điểm | Counting sort | k=1001 rất nhỏ so với n, O(n+k) |
| 1.000 số nguyên trải trong -10⁹..10⁹ | Thuật toán so sánh | k có thể gần 2×10⁹, không thực tế cho count |
| Hàng triệu số nguyên 32-bit, đủ RAM, cần throughput | Radix sort, đối chiếu benchmark với sort chuẩn | 4 lượt theo byte là một hướng có chi phí tuyến tính theo n |
| Danh sách người dùng sắp theo tên có quy tắc so sánh riêng | So sánh ổn định trên đối tượng | Comparator và tính ổn định quan trọng hơn một phép ánh xạ số học |
| Số thực gần đều trên [0,1), n lớn | Bucket sort nếu giả thiết phân bố đáng tin | Có thể cho kỳ vọng tuyến tính; cần kiểm thử bucket lệch |
| Khóa nguyên đã gần có thứ tự, số lượng vừa phải | API so sánh phù hợp có khả năng khai thác runs | Tránh tiền xử lý không cần thiết; đo thực tế |
| Bộ nhớ hạn chế, k rất lớn | Không dùng counting trực tiếp | Mảng count không khả thi, kể cả khi n nhỏ |
| Dữ liệu phải sắp xếp ổn định và giữ ID | Counting ổn định, radix ổn định hoặc sort đối tượng ổn định | Chỉ sắp khóa mà làm mất thứ tự ID là sai yêu cầu |

**Đừng chọn chỉ bằng khẩu hiệu:** “Counting sort O(n) nên luôn nhanh hơn O(n log n)” bỏ qua k, bộ nhớ và hệ số khởi tạo. “Bucket sort luôn O(n)” bỏ qua giả thiết phân bố. “Quicksort luôn O(n log n)” bỏ qua trường hợp xấu của bản chuẩn đơn giản. Và “Radix dùng 4 vòng nên chắc chắn nhanh” bỏ qua chi phí mỗi vòng và bộ nhớ.

## 10. Java 17+ hoàn chỉnh: tự động chọn counting ổn định hoặc sort so sánh

Ví dụ sau không cố tự viết một thư viện sắp xếp tổng quát. Nó minh họa một **quy tắc chọn có kiểm soát** giữa:

- **Counting sort ổn định** khi khóa nguyên có miền đủ nhỏ.
- **`Arrays.sort(T[], Comparator)`** khi miền khóa quá rộng so với n hoặc vượt ngưỡng cấp phát.

Mỗi bản ghi là `Item(key,id)`, vì vậy có thể nhìn thấy rõ thứ tự các bản ghi trùng khóa. Hàm không sửa mảng đầu vào; kết quả được trả qua `SortResult`.

**Chính sách minh họa:** chỉ dùng counting khi `k≤1.000.000` và `k≤4n`. Đây là ngưỡng đơn giản để chứng minh cách chọn; **không phải ngưỡng tối ưu phổ quát**, không bảo đảm counting nhanh hơn trong mọi lần chạy hoặc đủ RAM ở mọi môi trường. Khi hệ thống có cấu hình bộ nhớ cụ thể, cần chọn ngưỡng dựa trên giới hạn thực tế.

Lưu tệp **`SortChoiceDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.Comparator;

public final class SortChoiceDemo {
    record Item(int key, String id) {}
    enum Strategy { COUNTING, COMPARISON }
    record SortResult(Item[] items, Strategy strategy) {}

    private static final int MAX_RANGE = 1_000_000;

    static SortResult sort(Item[] input) {
        if (input == null) {
            throw new IllegalArgumentException("Input must not be null");
        }

        for (Item item : input) {
            if (item == null) {
                throw new IllegalArgumentException("Null item");
            }
        }

        if (input.length == 0) {
            return new SortResult(new Item[0], Strategy.COMPARISON);
        }

        int min = input[0].key();
        int max = min;

        for (Item item : input) {
            if (item.key() < min) {
                min = item.key();
            }
            if (item.key() > max) {
                max = item.key();
            }
        }

        long width = (long) max - min + 1L;
        if (width <= MAX_RANGE && width <= 4L * input.length) {
            return new SortResult(
                    stableCountingSort(input, min, (int) width),
                    Strategy.COUNTING);
        }

        Item[] copy = input.clone();
        Arrays.sort(copy, Comparator.comparingInt(Item::key));
        return new SortResult(copy, Strategy.COMPARISON);
    }

    private static Item[] stableCountingSort(
            Item[] input, int min, int width) {
        int[] end = new int[width];

        for (Item item : input) {
            int index = (int) ((long) item.key() - min);
            end[index]++;
        }

        // end[i] là số bản ghi có khóa <= (min+i).
        for (int i = 1; i < width; i++) {
            end[i] += end[i - 1];
        }

        Item[] output = new Item[input.length];

        // Duyệt ngược giúp giữ thứ tự tương đối khi key trùng.
        for (int i = input.length - 1; i >= 0; i--) {
            Item item = input[i];
            int index = (int) ((long) item.key() - min);
            output[--end[index]] = item;
        }

        return output;
    }

    private static String display(Item[] input) {
        StringBuilder result = new StringBuilder("[");
        for (int i = 0; i < input.length; i++) {
            if (i > 0) {
                result.append(", ");
            }
            result.append(input[i].key())
                  .append(":")
                  .append(input[i].id());
        }
        return result.append("]").toString();
    }

    public static void main(String[] args) {
        Item[] narrow = {
            new Item(3, "A"),
            new Item(-1, "B"),
            new Item(3, "C"),
            new Item(0, "D"),
            new Item(-1, "E"),
            new Item(2, "F")
        };

        Item[] wide = {
            new Item(-1_000_000, "X"),
            new Item(5, "Y"),
            new Item(-1_000_000, "Z")
        };

        SortResult first = sort(narrow);
        SortResult second = sort(wide);

        System.out.println("Narrow strategy: " + first.strategy());
        System.out.println("Narrow result: " + display(first.items()));
        System.out.println("Wide strategy: " + second.strategy());
        System.out.println("Wide result: " + display(second.items()));
        System.out.println("Input preserved: " + display(narrow));
    }
}
~~~

Biên dịch và chạy trên JDK 17 hoặc mới hơn:

~~~bash
javac SortChoiceDemo.java
java SortChoiceDemo
~~~

Kết quả chuẩn:

~~~text
Narrow strategy: COUNTING
Narrow result: [-1:B, -1:E, 0:D, 2:F, 3:A, 3:C]
Wide strategy: COMPARISON
Wide result: [-1000000:X, -1000000:Z, 5:Y]
Input preserved: [3:A, -1:B, 3:C, 0:D, -1:E, 2:F]
~~~

**Giải thích:**

- `narrow` có n=6, min=-1, max=3 nên k=5; k≤1.000.000 và k≤24. Chương trình dùng counting sort ổn định, cho thứ tự B trước E và A trước C.
- `wide` có n=3, min=-1.000.000, max=5 nên k=1.000.006. Mảng đếm vượt chính sách `MAX_RANGE=1_000_000` và cũng lớn hơn `4n=12`, nên chọn nhánh comparison. `Arrays.sort` trên `Item[]` giữ X trước Z, vì cả hai có khóa -1.000.000.
- Mảng `narrow` ban đầu vẫn giữ đúng thứ tự, vì counting tạo `output[]` mới còn nhánh so sánh sắp xếp trên `clone()`.
- Trong counting ổn định, `end[]` ban đầu là số phần tử có khóa không lớn hơn mỗi giá trị. Sau khi đặt một bản ghi vào `output[--end[index]]`, vị trí kết thúc của nhóm giảm một. Việc đi từ phải sang trái khiến bản ghi xuất hiện sau được đặt ở vị trí sau.
- Dùng `long width=(long)max-min+1L` tránh tràn trên toàn miền `int`; chỉ ép về `int` sau khi đã kiểm tra ngưỡng. Việc tính `4L*input.length` cũng tránh tràn khi nhân kích thước.
- Nếu đầu vào rỗng, hàm trả mảng rỗng và gắn nhãn COMPARISON theo chính sách mặc định; không có phần tử nào cần sắp xếp.

**Độ phức tạp:** để chọn chiến lược cần quét n phần tử lấy min/max, tốn O(n). Trong nhánh counting, tổng là **Θ(n+k)** thời gian và Θ(n+k) bộ nhớ phụ. Trong nhánh comparison, sao chép tốn Θ(n), còn việc sắp xếp đối tượng bằng API có giới hạn kiểu so sánh và chi phí tương ứng; với comparator số nguyên hằng số và thuật toán so sánh ổn định có bảo đảm O(n log n), thời gian tổng O(n log n) khi n lớn, bộ nhớ phụ có thể O(n). Ví dụ cố tình không đưa bucket/radix vào cùng nhánh tự động vì lựa chọn chúng còn cần cấu trúc dữ liệu và các giả thiết khác.

**Giới hạn của ví dụ:** `Item` dùng đối tượng nên có overhead so với `int[]`. Ngưỡng heuristic chỉ tránh tạo bảng đếm quá rộng theo một chính sách đơn giản, không giới hạn tổng bộ nhớ cho mảng kết quả hay bản ghi. Không dùng trực tiếp chương trình này như bộ tối ưu tự động cho dữ liệu nhiều tỷ phần tử hoặc môi trường cực kỳ hạn chế RAM.

## 11. Ví dụ quyết định sai và cách sửa

### 11.1. “k nhỏ” bị đánh giá nhầm bằng số phần tử phân biệt

Giả sử `a=[-1_000_000_000, 0, 1_000_000_000]`. Chỉ có ba giá trị khác nhau, nhưng `k=2.000.000.001`. Nếu cấp phát `count[k]` theo miền liên tục sẽ cần hơn 8 GB chỉ để lưu các phần tử `int` của mảng đếm, chưa xét đối tượng khác và khả năng cấp phát mảng Java.

**Sửa:** tính `k` từ **max−min+1** bằng `long`; khi k rất lớn, chọn so sánh hoặc chiến lược ánh xạ/nén có phân tích tổng chi phí.

### 11.2. “Radix bốn lượt chắc chắn là O(n) cho mọi số”

Với `int` cố định 32-bit, có thể dùng đúng 4 lượt theo byte, nên thời gian theo n là tuyến tính với các thao tác từ máy phù hợp. Nhưng với số nguyên tùy ý có hàng triệu bit, số lượt `d` tăng theo chiều dài bit; không thể giữ d=4. Các thao tác trên `BigInteger` còn có chi phí phụ thuộc chiều dài toán hạng.

**Sửa:** nêu rõ độ rộng khóa, cơ số b, số lượt d, cách xử lý dấu và bộ nhớ trung gian.

### 11.3. “Bucket sort có thời gian tuyến tính bất kể dữ liệu”

Nếu tất cả n phần tử rơi vào một thùng, thuật toán không còn nhận lợi ích của phân bố đều. Với insertion sort trong thùng đó, chi phí có thể Θ(n²).

**Sửa:** dùng phân bố kỳ vọng chỉ khi có giả thiết phù hợp; nếu cần cận xấu nhất mạnh, chọn thuật toán phù hợp cho từng thùng hoặc dùng phương án so sánh có bảo đảm.

### 11.4. “Sắp xếp xong là đủ, không cần ổn định”

Cho danh sách `[(2,A),(1,B),(2,C)]` cần giữ thứ tự trong các khóa bằng nhau. Một cách xuất kết quả chỉ gồm `[1,2,2]` đã làm mất ID, không phải sắp xếp bản ghi. Một thuật toán không ổn định có thể đảo C trước A.

**Sửa:** định nghĩa chính xác đối tượng cần sắp xếp, kiểm tra tính ổn định của thuật toán/API và dùng bài kiểm thử có nhiều bản ghi cùng khóa, ID khác nhau.

### 11.5. “Sắp xếp bằng Java API nào cũng như nhau”

`Arrays.sort(int[])` làm việc với dữ liệu primitive, trong khi `Arrays.sort(Item[], Comparator)` sắp các tham chiếu tới đối tượng theo comparator, có hợp đồng ổn định. `Collections.sort(List)` và `List.sort(Comparator)` hoạt động trên danh sách. Các chi phí phụ như boxing, tạo comparator, bộ nhớ tạm và tính cục bộ khác nhau; bảng Big-O không thể thay thế việc hiểu API.

**Sửa:** xác định đúng kiểu phần tử, thuật toán hợp đồng, số lần sort và dữ liệu gần thực tế trước khi kết luận.

## 12. Kiểm thử chất lượng lựa chọn và tính đúng

**Các trường hợp biên nên kiểm thử:**

1. **Dãy rỗng:** trả mảng rỗng, không đọc phần tử đầu hoặc tính min/max trên dữ liệu không tồn tại.
2. **Một phần tử:** kết quả giữ nguyên; chi phí không cần có nhiều lượt phân phối.
3. **Tất cả khóa bằng nhau:** counting có k=1; kết quả ổn định phải bảo toàn chính xác thứ tự ID.
4. **Khóa âm và 0:** kiểm tra phép chuyển `key−min` bằng `long`, không dùng key làm chỉ số trực tiếp.
5. **Hai đầu miền `int`:** `Integer.MIN_VALUE` và `Integer.MAX_VALUE` làm k=4.294.967.296; nhánh counting phải bị loại trước khi cấp phát.
6. **Miền rộng nhưng n nhỏ:** so sánh với phương án `Arrays.sort` để tránh bảng đếm lớn.
7. **Nhiều khóa trùng với ID khác nhau:** xác minh các bản ghi cùng khóa giữ nguyên thứ tự đầu vào.
8. **Khóa tăng, giảm, ngẫu nhiên và gần sắp xếp:** kiểm tra hiệu năng và tính đúng với các phân bố khác nhau.
9. **Đầu vào lệch về một nhóm:** không được gọi bucket sort là kỳ vọng tuyến tính nếu dữ liệu không theo giả thiết.
10. **Dữ liệu lớn gần giới hạn RAM:** tính cả count, output, tham chiếu bản ghi và chi phí GC.
11. **Nhiều lượt radix:** kiểm tra mỗi lượt ổn định và kết quả số âm/giá trị cực trị.
12. **Comparator có khóa phụ hoặc thứ tự bất thường:** sắp xếp phân phối theo riêng khóa nguyên không đủ nếu comparator yêu cầu thứ tự khác.

### Kiểm thử đối chiếu (differential testing)

Với mảng nhỏ, có thể:

1. Sinh nhiều `Item(key,id)` có khóa nguyên cả âm/dương và nhiều giá trị trùng.
2. Tạo kết quả tham chiếu bằng một API so sánh **ổn định** với `Comparator.comparingInt(Item::key)`.
3. Chạy counting ổn định trên những mảng có miền khóa vừa giới hạn.
4. So sánh **toàn bộ thứ tự bản ghi**, không chỉ dãy khóa, để kiểm tra ổn định.
5. Chạy dữ liệu vượt ngưỡng để đảm bảo nhánh fallback sử dụng thuật toán so sánh và không cấp phát bảng đếm.
6. Thử miền cực rộng với kiểu `int` để bắt lỗi tràn khi tính width.

### Checklist lựa chọn trước khi nộp bài

- `n` là bao nhiêu, miền khóa `k` có tính bằng kiểu đủ rộng chưa?
- Có yêu cầu sắp **đối tượng có ID** hay chỉ sắp giá trị primitive?
- Cần bảo toàn thứ tự giữa các khóa bằng nhau không?
- Khóa có thể phân chia thành `d` chữ số cơ số `b` để dùng radix không; số âm được xử lý thế nào?
- Bucket sort có giả thiết phân bố được nêu rõ không; trường hợp xấu khi nhiều phần tử chung thùng là gì?
- Cần cận xấu nhất hay hiệu năng trung bình/kỳ vọng?
- Bộ nhớ O(k), O(n+k) hoặc O(n+b) có thực sự cấp phát được không?
- Tổng chi phí có tính tiền xử lý, cấp phát, sao chép, I/O và số lượt chạy không?
- Có phương án so sánh ổn định và đáng tin làm lựa chọn mặc định khi đặc tả không có lợi thế phân phối không?

**Kết luận:** Chọn sắp xếp phân phối khi **miền khóa hoặc cấu trúc chữ số thật sự tạo ra lợi thế** và chi phí bộ nhớ chấp nhận được. Chọn sắp xếp so sánh khi cần **tính tổng quát, comparator linh hoạt, bộ nhớ/bảo đảm rõ ràng hoặc một phương án mặc định tin cậy**. Điều quyết định không phải chỉ là O(n) so với O(n log n), mà là **tập giả thiết đã chứng minh và tổng chi phí trên dữ liệu thực tế**.