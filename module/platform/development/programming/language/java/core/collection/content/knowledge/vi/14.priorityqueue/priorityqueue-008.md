# Bài toán top-K và lựa chọn heap nhỏ hoặc heap lớn

## 1. Top-K là gì và khi nào cần đến?

Top-K là bài toán chọn tối đa K phần tử tốt nhất theo một tiêu chí từ N phần tử đầu vào. “Tốt nhất” có thể là giá trị lớn nhất, thời gian chờ ngắn nhất, điểm đánh giá cao nhất hoặc khoảng cách nhỏ nhất. Trước khi chọn cấu trúc dữ liệu, phải xác định chiều tốt hơn: một số lớn có thể tốt trong bài toán điểm số nhưng kém trong bài toán độ trễ.

Ví dụ, từ dãy:

~~~text
7, 2, 9, 4, 9, 1, 8, 5
~~~

Nếu mỗi lần xuất hiện được tính là một phần tử thì:

| Yêu cầu | Kết quả đã sắp theo thứ tự mong muốn |
| --- | --- |
| Ba phần tử lớn nhất | [9, 9, 8] |
| Ba phần tử nhỏ nhất | [1, 2, 4] |
| Giá trị lớn thứ ba, tính cả số trùng | 8 |
| Ba giá trị lớn nhất khác nhau | [9, 8, 7] |

Đó là các yêu cầu khác nhau. Một hàng đợi ưu tiên không tự quyết định có loại trùng hay không, và top-K theo số lần xuất hiện không đồng nghĩa top-K giá trị phân biệt.

Sắp xếp toàn bộ đầu vào rồi lấy K phần tử đầu là cách dễ hiểu. Tuy nhiên, nếu N rất lớn, K nhỏ, hoặc dữ liệu đến từng phần tử, ta muốn chỉ giữ những ứng viên còn có khả năng nằm trong kết quả. Heap giới hạn kích thước giúp thực hiện điều đó.

Trong bài này, “heap nhỏ” là heap có phần tử nhỏ nhất ở gốc theo thứ tự đang xét; “heap lớn” là heap có phần tử lớn nhất ở gốc theo thứ tự đó. Hai tên này nói về vị trí cực trị, không nói dung lượng heap. Cả hai đều có thể được giới hạn ở K phần tử.

Sau bài học, bạn cần tự trả lời được ba câu hỏi: phần tử nào đang yếu nhất trong nhóm được giữ; phần tử mới có tốt hơn nó không; và đầu heap phải chứa phần tử nào để quyết định thay thế nhanh?

## 2. Liên hệ với PriorityQueue của Java

`PriorityQueue` chọn đầu hàng đợi theo thứ tự tự nhiên hoặc `Comparator` được cung cấp. Đầu hàng đợi là phần tử đứng trước nhất theo thứ tự đó. Với số nguyên, thứ tự tự nhiên đưa số nhỏ nhất ra đầu; đảo thứ tự đưa số lớn nhất ra đầu. Khi các phần tử đồng hạng, hàng đợi không bảo đảm chọn phần tử được thêm sớm hơn. [Tài liệu PriorityQueue, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html).

Hai khai báo cơ bản:

~~~java
PriorityQueue<Integer> minHeap = new PriorityQueue<>();
PriorityQueue<Integer> maxHeap =
        new PriorityQueue<>(Comparator.reverseOrder());
~~~

Đây là hai cách cấu hình cùng một lớp. Java không cung cấp hai lớp tên `MinHeap` và `MaxHeap` cho trường hợp này.

Điều dễ nhầm nhất là chọn heap theo tên kết quả: “tìm lớn nhất thì dùng heap lớn”. Quy tắc đó phù hợp khi bạn giữ toàn bộ dữ liệu và muốn lấy ngay phần tử lớn nhất. Với thuật toán chỉ giữ K ứng viên, thao tác thường xuyên lại là loại ứng viên yếu nhất. Vì vậy, phải chọn đầu heap theo phần tử cần loại.

| Mục tiêu của heap giới hạn K | Phần tử yếu nhất trong nhóm đang giữ | Heap cần dùng cho số nguyên |
| --- | --- | --- |
| Giữ K phần tử lớn nhất | Nhỏ nhất trong nhóm | Heap nhỏ, thứ tự tự nhiên |
| Giữ K phần tử nhỏ nhất | Lớn nhất trong nhóm | Heap lớn, thứ tự đảo |

Hãy đọc hàng thứ nhất thành một câu: “Trong K số lớn nhất đang giữ, số nhỏ nhất là người dễ bị thay thế nhất; đưa nó lên đầu heap”.

## 3. Mô hình ngưỡng: đầu heap là ranh giới chấp nhận

Giả sử cần ba số lớn nhất và heap đang giữ:

~~~text
Các ứng viên: 7, 9, 9
Ngưỡng hiện tại: 7
~~~

Nếu đọc số 8, nó tốt hơn 7, vì thế loại 7 và thêm 8. Nếu đọc số 5, không có lý do loại bất kỳ ứng viên nào đang giữ để nhận 5.

Với heap nhỏ giới hạn K, `peek()` trả ngưỡng nhỏ nhất còn được chấp nhận trong nhóm hiện tại. Nó không nhất thiết là số nhỏ nhất của toàn bộ dữ liệu đã đọc, vì các số quá nhỏ đã bị loại.

Tương tự, khi cần ba số nhỏ nhất:

~~~text
Các ứng viên: 1, 2, 4
Ngưỡng hiện tại: 4
~~~

Số mới bằng 3 sẽ thay 4. Số mới bằng 8 bị bỏ qua. Heap lớn đưa 4 ra đầu để không phải tìm ứng viên yếu nhất bằng cách duyệt cả nhóm.

Trước khi đã nhận đủ K phần tử, `peek()` chỉ là cực trị của nhóm chưa đầy. Sau khi nhóm đủ K phần tử, nó mới đóng vai trò ranh giới của top-K hiện tại. Chẳng hạn, sau một số đầu tiên, không thể dùng đầu heap để kết luận đã có “số lớn thứ ba”.

Trong luồng chỉ có thêm phần tử, với top-K lớn nhất đã đầy, ngưỡng không giảm: mỗi lần thay thế đều nhận một số lớn hơn ngưỡng cũ. Với top-K nhỏ nhất, ngưỡng không tăng. Đây là hệ quả của chính quy tắc chọn, không phải một phép sắp xếp toàn bộ đầu vào.

## 4. Thuật toán giữ K phần tử lớn nhất

Giả sử K > 0 và các giá trị là số nguyên:

~~~text
Tạo heap nhỏ rỗng.
Với mỗi số x:
    Nếu heap chưa đủ K phần tử:
        thêm x.
    Nếu heap đã đủ K phần tử:
        lấy ngưỡng nhỏ nhất bằng peek().
        nếu x > ngưỡng:
            poll() để loại ngưỡng;
            offer(x).
        nếu x <= ngưỡng:
            bỏ qua x.
~~~

Mã cốt lõi, dùng trong chương trình đầy đủ ở phần sau:

~~~java
static void keepLargest(PriorityQueue<Integer> heap, int value, int k) {
    if (heap.size() < k) {
        heap.offer(value);
    } else if (value > heap.peek()) {
        heap.poll();
        heap.offer(value);
    }
}
~~~

Hàm phụ này có tiền điều kiện: `k > 0`, heap dùng thứ tự tự nhiên, không có `null` và trước mỗi lần gọi kích thước không lớn hơn K. Hàm tổng quát ở phần sau kiểm tra K và xử lý K = 0 trước khi lặp; không gọi hàm phụ với K = 0.

Phải kiểm tra chưa đầy trước khi so sánh với `peek()`. Khi heap rỗng, `peek()` trả `null`; nếu tự động mở hộp `Integer` thành `int` trong phép `>`, chương trình sẽ ném `NullPointerException`.

Tại sao dùng `>` thay vì `>=`? Trong bài toán chỉ xếp hạng theo giá trị số, một số bằng ngưỡng không cải thiện các giá trị trong kết quả. Bỏ qua nó khi heap đầy giúp tránh hai thao tác heap không cần thiết. Điều này không loại bỏ tất cả phần tử trùng: các lần xuất hiện bằng nhau vẫn có thể được thêm khi heap chưa đầy hoặc tốt hơn ngưỡng.

Ví dụ `[9, 9, 9, 8]` với K = 2 vẫn cho `[9, 9]`. Nếu cần phân biệt danh tính giữa các bản ghi bằng điểm, phải thêm tiêu chí phụ thay vì suy diễn từ dấu `>`.

### Theo dõi toàn bộ ví dụ

Bảng dưới sắp các phần tử được giữ theo chiều giảm để dễ đọc. Đây là cách trình bày kết quả trung gian, không mô tả thứ tự của mảng nội bộ heap.

| Bước | Số mới | Hành động | Các giá trị được giữ | Đầu heap nhỏ |
| --- | --- | --- | --- | --- |
| 1 | 7 | Chưa đầy, thêm | [7] | 7 |
| 2 | 2 | Chưa đầy, thêm | [7, 2] | 2 |
| 3 | 9 | Chưa đầy, thêm | [9, 7, 2] | 2 |
| 4 | 4 | 4 > 2, thay 2 | [9, 7, 4] | 4 |
| 5 | 9 | 9 > 4, thay 4 | [9, 9, 7] | 7 |
| 6 | 1 | 1 <= 7, bỏ qua | [9, 9, 7] | 7 |
| 7 | 8 | 8 > 7, thay 7 | [9, 9, 8] | 8 |
| 8 | 5 | 5 <= 8, bỏ qua | [9, 9, 8] | 8 |

Điểm quyết định là so với ngưỡng, không so với số đến ngay trước đó và không so với số lớn nhất đang giữ.

Một hình heap nhỏ hợp lệ cho nhóm cuối:

~~~text
       8
      / \
     9   9
~~~

Hai số 9 không cần có thứ tự trước sau. Chỉ cần gốc cho biết ứng viên yếu nhất là 8.

## 5. Đổi sang K phần tử nhỏ nhất

Để giữ K số nhỏ nhất, đổi đồng thời hai yếu tố:

1. Đưa số lớn nhất trong nhóm ra đầu bằng thứ tự đảo.
2. Chỉ nhận số mới nếu nó nhỏ hơn đầu heap.

Mã minh họa độc lập về cơ chế, chưa bao gồm kiểm tra đầu vào:

~~~java
PriorityQueue<Integer> heap =
        new PriorityQueue<>(Comparator.reverseOrder());

for (int value : input) {
    if (heap.size() < k) {
        heap.offer(value);
    } else if (value < heap.peek()) {
        heap.poll();
        heap.offer(value);
    }
}
~~~

Đoạn này giả sử `input` đã có và `k > 0`. Nếu chỉ đảo comparator mà giữ nguyên dấu so sánh của trường hợp K lớn nhất, thuật toán sẽ nhận sai ứng viên.

Với cùng dãy và K = 3, nhóm cuối là `[1, 2, 4]`. Một heap lớn hợp lệ:

~~~text
       4
      / \
     1   2
~~~

Đầu heap bằng 4 là số nhỏ thứ ba trong dữ liệu đã đọc khi đã đủ ba phần tử. Nó không phải số nhỏ nhất; số nhỏ nhất là phần tử tốt nhất, còn đầu heap được đặt ở phần tử yếu nhất để phục vụ thay thế.

Có thể kiểm tra chiều comparator bằng hai giá trị rất đơn giản. Nếu đang tìm số nhỏ nhất nhưng `peek()` của nhóm `[1, 2, 4]` lại là 1, hãy xem lại liệu bạn có đưa đúng phần tử cần loại lên đầu chưa.

## 6. Vì sao thuật toán đúng?

Một bất biến là điều luôn đúng tại ranh giới giữa các vòng lặp. Với top-K lớn nhất, sau khi đọc t phần tử, heap phải:

- Có đúng `min(K, t)` phần tử.
- Giữ một nhóm có các giá trị lớn nhất trong t phần tử đã đọc, tính cả số lần xuất hiện.
- Không có phần tử bị loại nào tốt hơn phần tử yếu nhất đang giữ, khi heap đã đầy.

Chứng minh bằng từng bước:

**Ban đầu:** chưa đọc phần tử nào, heap rỗng. Nhóm lớn nhất kích thước 0 là rỗng, nên bất biến đúng.

**Khi chưa đầy:** số phần tử đã đọc chưa vượt K. Tất cả chúng đều phải thuộc nhóm kết quả, nên thêm phần tử mới là đúng.

**Khi đã đầy và x không lớn hơn ngưỡng:** đã có K phần tử được giữ đều lớn hơn hoặc bằng ngưỡng, và do đó đều lớn hơn hoặc bằng x. Không cần nhận x để có K giá trị lớn nhất. Nếu x bằng ngưỡng, thay hay không thay có thể đổi danh tính lần xuất hiện, nhưng không đổi tập đa hợp các giá trị được chọn.

**Khi đã đầy và x lớn hơn ngưỡng:** x tốt hơn phần tử yếu nhất trong nhóm. Loại một phần tử ở ngưỡng rồi thêm x cho nhóm tốt hơn. Những phần tử đã bị loại trước đây không thể đột nhiên vượt các ứng viên hiện tại chỉ vì có thêm x; các giá trị cũ không thay đổi. Nhóm mới tiếp tục là một lựa chọn top-K hợp lệ.

Khi hết đầu vào, t = N, nên heap giữ `min(K, N)` phần tử lớn nhất. Đổi quan hệ lớn hơn thành nhỏ hơn và đổi loại heap cho chứng minh đối xứng của top-K nhỏ nhất.

Bất biến này mạnh hơn “heap không vượt K”. Một thuật toán có thể giữ đúng K phần tử nhưng chọn sai K phần tử. Ví dụ giữ K số lớn nhất trong heap lớn rồi cứ tràn là `poll()` sẽ loại chính số tốt nhất.

## 7. Hai kiểu cập nhật và lỗi chọn nhầm heap

Có hai kiểu viết phổ biến cho K lớn nhất.

**Kiểu so ngưỡng trước:** khi đầy, chỉ `poll()` rồi `offer()` nếu số mới tốt hơn ngưỡng. Heap không vượt K phần tử ở bất kỳ thời điểm nào trong vòng lặp.

**Kiểu thêm trước, cắt sau:** dùng heap nhỏ, thêm mọi phần tử rồi bỏ phần tử nhỏ nhất nếu kích thước vượt K.

~~~java
PriorityQueue<Integer> heap = new PriorityQueue<>();
for (int value : input) {
    heap.offer(value);
    if (heap.size() > k) {
        heap.poll();
    }
}
~~~

Đây là đoạn minh họa, yêu cầu `k >= 0`. Với K = 0, mỗi số được thêm rồi bị lấy ra ngay; kết quả rỗng nhưng vẫn duyệt hết đầu vào. Với K âm, đoạn này không thể hiện một hợp đồng hợp lệ; cần từ chối K âm trước vòng lặp.

Kiểu thêm trước có thể giữ tạm K + 1 phần tử, vẫn là O(K + 1) bộ nhớ phụ. Nó ngắn và dễ chứng minh: trong K + 1 ứng viên, loại số nhỏ nhất. Kiểu so ngưỡng trước tránh thao tác heap cho ứng viên chắc chắn bị loại, phù hợp khi có nhiều dữ liệu kém hơn ngưỡng. Cả hai đều dùng heap nhỏ cho K lớn nhất.

Xét lỗi dùng heap lớn với kiểu thêm trước, cắt sau:

~~~text
Dữ liệu: 7, 2, 9, 8
K: 3
Thêm đủ bốn số vào heap lớn.
poll() lấy 9 ra.
Còn lại: 8, 7, 2.
Kết quả đúng phải là: 9, 8, 7.
~~~

Lỗi không nằm ở khả năng tìm cực trị của heap lớn; nó tìm đúng số lớn nhất. Lỗi nằm ở việc đem phần tử tốt nhất đi loại. Cách chọn heap chỉ đúng khi gắn với vai trò cụ thể của `poll()`.

Nếu chọn cách giữ toàn bộ N phần tử rồi lấy K lần, K lớn nhất có thể dùng heap lớn. Khi đó `poll()` phục vụ xuất kết quả tốt nhất, không phục vụ cắt bớt nhóm ứng viên. Hai thiết kế có mục đích khác nhau và bộ nhớ khác nhau.

## 8. Tổng quát hóa: thứ tự kết quả và thứ tự của heap

Với dữ liệu đối tượng, viết hai thuật toán gần giống nhau dễ gây đảo dấu sai. Có thể thống nhất bằng một `Comparator` gọi là `bestFirst`:

~~~text
bestFirst.compare(a, b) < 0  nghĩa là a tốt hơn b.
bestFirst.compare(a, b) > 0  nghĩa là a kém hơn b.
bestFirst.compare(a, b) == 0 nghĩa là đồng hạng theo các tiêu chí đã chọn.
~~~

`bestFirst` cũng là thứ tự sắp kết quả đầu ra: phần tử tốt nhất đứng trước.

Để phần tử yếu nhất nằm ở đầu heap, dùng thứ tự đảo của toàn bộ `bestFirst`:

~~~java
PriorityQueue<T> heap = new PriorityQueue<>(bestFirst.reversed());
~~~

Khi heap đầy, phép kiểm tra thống nhất là:

~~~java
if (bestFirst.compare(value, heap.peek()) < 0) {
    heap.poll();
    heap.offer(value);
}
~~~

Một ứng viên tốt hơn đầu heap theo `bestFirst` mới được nhận. Đừng dùng comparator đảo của heap trong biểu thức này rồi giữ nguyên dấu `< 0`; như vậy bạn đã đảo cả ý nghĩa “tốt hơn”.

| Bài toán số nguyên | bestFirst dùng để xếp kết quả | Thứ tự heap = bestFirst.reversed() |
| --- | --- | --- |
| K lớn nhất | `Comparator.reverseOrder()` | Thứ tự tự nhiên, heap nhỏ |
| K nhỏ nhất | `Comparator.naturalOrder()` | Thứ tự đảo, heap lớn |

Phương thức `reversed()` đảo thứ tự; `thenComparing(...)` bổ sung tiêu chí khi các tiêu chí trước chưa phân hạng được. Những phép ghép này giữ mã so sánh dễ đọc hơn so với tự đổi dấu số học. [Tài liệu Comparator, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html).

### Đồng điểm và danh tính bản ghi

Giả sử mỗi ứng viên có `id` và `score`. Yêu cầu: điểm cao hơn đứng trước; nếu bằng điểm, mã có thứ tự chữ nhỏ hơn đứng trước.

~~~java
Comparator<Candidate> bestFirst = Comparator
        .comparingInt(Candidate::score).reversed()
        .thenComparing(Candidate::id);
~~~

Thứ tự kết quả là điểm giảm, mã tăng. Thứ tự heap là đảo của cả chuỗi trên, tức điểm tăng và khi bằng điểm thì mã giảm. Nhờ vậy, trong nhóm điểm 90 gồm A, B, C, bản ghi C là ứng viên yếu nhất khi cần giữ những mã nhỏ hơn.

Với dữ liệu `C:90, B:90, A:90, D:70, E:100` và K = 3, kết quả là `[E:100, A:90, B:90]`.

Nếu chỉ so sánh điểm, A, B và C đồng hạng. Kết quả vẫn có thể đúng theo điểm nhưng danh tính các bản ghi được giữ không có bảo đảm ổn định. Việc bỏ qua ứng viên bằng ngưỡng không biến heap thành một cấu trúc ổn định: khi một điểm cao hơn đến, heap có thể chọn bất kỳ bản ghi nào đang đồng hạng ở đầu để loại.

Nếu cần ưu tiên bản ghi đến sớm khi đồng điểm, gắn số thứ tự đến tăng dần vào từng bản ghi và đưa nó vào tiêu chí phụ. Nếu muốn kết quả độc lập thứ tự nhập, dùng một mã định danh ổn định làm tiêu chí phụ. Hai yêu cầu này không giống nhau.

Các khóa dùng để xếp hạng nên bất biến khi nằm trong heap. Đổi trực tiếp `score` của đối tượng đã được thêm không tự sắp lại heap. Một comparator phụ thuộc vào cấu hình đang thay đổi giữa vòng lặp cũng phá vỡ lập luận về ngưỡng.

### Không dùng phép trừ để đảo thứ tự

Tránh:

~~~java
Comparator<Integer> unsafe = (a, b) -> b - a;
~~~

Ví dụ `b = Integer.MAX_VALUE` và `a = -1` làm phép trừ vượt miền `int`. Kết quả bị tràn có thể mang dấu sai, dẫn đến so sánh trái ý định.

Dùng `Comparator.reverseOrder()`, `Integer.compare(b, a)` hoặc `Comparator.comparingInt(...)`. Khi đảo comparator có sẵn, dùng `reversed()`; không tự viết `-comparator.compare(a, b)` vì giá trị trả về có thể là `Integer.MIN_VALUE`. [Tài liệu Integer.compare, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html#compare(int,int)).

## 9. Chương trình Java 17+ hoàn chỉnh

Tệp `TopKHeapDemo.java` dưới đây có một hàm tổng quát dùng được với `Iterable`. Nó trả kết quả đã sắp theo `bestFirst`, không sửa cấu trúc đầu vào, không yêu cầu biết trước N và không cấp phát sẵn mảng có K chỗ.

Hợp đồng của `topK`:

- `k < 0`: ném `IllegalArgumentException`.
- `k == 0`: trả danh sách rỗng, không duyệt các phần tử nguồn.
- `k > N`: trả toàn bộ N phần tử theo thứ tự yêu cầu.
- `input` và `bestFirst` phải khác `null`, kể cả khi K = 0.
- Với K > 0, mỗi phần tử được đọc phải khác `null` và comparator phải so sánh được chúng.
- Phần tử trùng được tính theo từng lần xuất hiện; hàm không khử trùng.
- Kết quả là một danh sách giá trị được chọn; không có cam kết về khả năng sửa đổi danh sách trả về. Đặc biệt, nhánh K = 0 dùng `List.of()`.

Đoạn kiểm chứng so sánh kết quả với cách sắp toàn bộ một bản sao rồi lấy tối đa K phần tử. Nó kiểm tra cả hai chiều xếp hạng, dữ liệu trùng, số âm, dãy rỗng, K lớn hơn N và các số ở biên `int`. Đây là kiểm tra tính đúng của kết quả, không phải phép đo tốc độ.

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.PriorityQueue;
import java.util.Random;

public class TopKHeapDemo {
    record Candidate(String id, int score) {
        @Override
        public String toString() {
            return id + ":" + score;
        }
    }

    static <T> List<T> topK(
            Iterable<? extends T> input,
            int k,
            Comparator<? super T> bestFirst) {
        Objects.requireNonNull(input, "input");
        Objects.requireNonNull(bestFirst, "bestFirst");
        if (k < 0) {
            throw new IllegalArgumentException("k must be >= 0");
        }
        if (k == 0) {
            return List.of();
        }

        PriorityQueue<T> heap = new PriorityQueue<>(bestFirst.reversed());
        for (T value : input) {
            Objects.requireNonNull(value, "element");
            if (heap.size() < k) {
                heap.offer(value);
            } else if (bestFirst.compare(value, heap.peek()) < 0) {
                heap.poll();
                heap.offer(value);
            }
        }
        List<T> result = new ArrayList<>(heap);
        result.sort(bestFirst);
        return result;
    }

    static void keepLargest(PriorityQueue<Integer> heap, int value, int k) {
        if (heap.size() < k) {
            heap.offer(value);
        } else if (value > heap.peek()) {
            heap.poll();
            heap.offer(value);
        }
    }

    static List<Integer> descendingSnapshot(PriorityQueue<Integer> heap) {
        List<Integer> copy = new ArrayList<>(heap);
        copy.sort(Comparator.reverseOrder());
        return copy;
    }

    static List<Integer> expected(
            List<Integer> input, int k, Comparator<Integer> order) {
        List<Integer> copy = new ArrayList<>(input);
        copy.sort(order);
        return new ArrayList<>(copy.subList(0, Math.min(k, copy.size())));
    }

    static void check(boolean condition) {
        if (!condition) {
            throw new AssertionError("top-K mismatch");
        }
    }

    static int selfCheck() {
        Random random = new Random(20261019L);
        int checks = 0;
        for (int test = 0; test < 250; test++) {
            int n = random.nextInt(25);
            int k = random.nextInt(31);
            List<Integer> input = new ArrayList<>();
            for (int i = 0; i < n; i++) {
                input.add(random.nextInt(21) - 10);
            }
            List<Integer> before = new ArrayList<>(input);
            for (Comparator<Integer> order : List.of(
                    Comparator.<Integer>naturalOrder(),
                    Comparator.<Integer>reverseOrder())) {
                check(topK(input, k, order).equals(expected(input, k, order)));
                check(input.equals(before));
                checks++;
            }
        }

        List<Integer> extremes = List.of(
                Integer.MIN_VALUE, 0, Integer.MAX_VALUE, -1, 1);
        for (int k = 0; k <= 6; k++) {
            for (Comparator<Integer> order : List.of(
                    Comparator.<Integer>naturalOrder(),
                    Comparator.<Integer>reverseOrder())) {
                check(topK(extremes, k, order).equals(expected(extremes, k, order)));
                checks++;
            }
        }
        return checks;
    }

    public static void main(String[] args) {
        List<Integer> input = List.of(7, 2, 9, 4, 9, 1, 8, 5);
        List<Integer> before = new ArrayList<>(input);
        PriorityQueue<Integer> heap = new PriorityQueue<>();
        int step = 0;
        for (int value : input) {
            keepLargest(heap, value, 3);
            System.out.println("step=" + (++step)
                    + " value=" + value
                    + " kept=" + descendingSnapshot(heap)
                    + " boundary=" + heap.peek());
        }
        System.out.println("largest 3=" + topK(input, 3, Comparator.reverseOrder()));
        System.out.println("smallest 3=" + topK(input, 3, Comparator.naturalOrder()));
        System.out.println("source unchanged=" + input.equals(before));
        System.out.println("k=0=" + topK(input, 0, Comparator.reverseOrder()));
        System.out.println("k>n=" + topK(List.of(4, 1), 5, Comparator.reverseOrder()));
        System.out.println("empty=" + topK(List.<Integer>of(), 3, Comparator.naturalOrder()));
        System.out.println("duplicates="
                + topK(List.of(9, 9, 9, 8), 2, Comparator.reverseOrder()));

        List<Integer> extremes = List.of(
                Integer.MIN_VALUE, 0, Integer.MAX_VALUE, -1, 1);
        System.out.println("largest extremes="
                + topK(extremes, 2, Comparator.reverseOrder()));
        System.out.println("smallest extremes="
                + topK(extremes, 2, Comparator.naturalOrder()));
        System.out.println("largest 1=" + topK(input, 1, Comparator.reverseOrder()));

        List<Integer> pollOrder = new ArrayList<>();
        PriorityQueue<Integer> copy = new PriorityQueue<>(heap);
        while (!copy.isEmpty()) {
            pollOrder.add(copy.poll());
        }
        System.out.println("min-heap poll order=" + pollOrder);
        System.out.println("original heap size=" + heap.size());

        List<Candidate> candidates = List.of(
                new Candidate("C", 90),
                new Candidate("B", 90),
                new Candidate("A", 90),
                new Candidate("D", 70),
                new Candidate("E", 100));
        Comparator<Candidate> bestFirst = Comparator
                .comparingInt(Candidate::score).reversed()
                .thenComparing(Candidate::id);
        System.out.println("candidates=" + topK(candidates, 3, bestFirst));

        try {
            topK(input, -1, Comparator.naturalOrder());
        } catch (IllegalArgumentException exception) {
            System.out.println("negative k=" + exception.getMessage());
        }
        System.out.println("reference checks=" + selfCheck());
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~shell
javac --release 17 -encoding UTF-8 TopKHeapDemo.java
java TopKHeapDemo
~~~

Lệnh `javac --release 17` yêu cầu JDK 17 hoặc mới hơn hỗ trợ phiên bản đích này. Chương trình chỉ dùng API và cú pháp có từ Java 17 trở về trước.

Stdout chính xác:

~~~text
step=1 value=7 kept=[7] boundary=7
step=2 value=2 kept=[7, 2] boundary=2
step=3 value=9 kept=[9, 7, 2] boundary=2
step=4 value=4 kept=[9, 7, 4] boundary=4
step=5 value=9 kept=[9, 9, 7] boundary=7
step=6 value=1 kept=[9, 9, 7] boundary=7
step=7 value=8 kept=[9, 9, 8] boundary=8
step=8 value=5 kept=[9, 9, 8] boundary=8
largest 3=[9, 9, 8]
smallest 3=[1, 2, 4]
source unchanged=true
k=0=[]
k>n=[4, 1]
empty=[]
duplicates=[9, 9]
largest extremes=[2147483647, 1]
smallest extremes=[-2147483648, -1]
largest 1=[9]
min-heap poll order=[8, 9, 9]
original heap size=3
candidates=[E:100, A:90, B:90]
negative k=k must be >= 0
reference checks=514
~~~

### Đọc kết quả để đối chiếu cơ chế

`kept` được tạo bằng cách sao chép heap sang danh sách rồi sắp giảm, nên có thứ tự dễ kiểm tra. Đây là thao tác phục vụ in dấu vết; nó không tham gia quyết định nhận hay loại phần tử.

Tám dòng `step` khớp bảng theo dõi ở trên. Sau bước 5, ngưỡng là 7; bước 6 gặp 1 nên nhóm giữ nguyên; bước 7 gặp 8 nên thay 7. Dòng `largest 3` và `smallest 3` thể hiện cùng hàm tổng quát với hai comparator khác nhau.

`min-heap poll order=[8, 9, 9]` cho thấy một điểm cần phân biệt: heap giữ ba số lớn nhất nhưng lấy ra theo thứ tự tăng. Đó là hệ quả của việc đặt ứng viên yếu nhất ở đầu. Chương trình lấy trên một bản sao, nên `original heap size=3` xác nhận heap ban đầu chưa bị tiêu thụ.

`candidates` kiểm tra tiêu chí phụ bằng mã. `reference checks=514` gồm 250 bộ ngẫu nhiên với hai chiều so sánh, cộng bảy giá trị K từ 0 đến 6 trên bộ dữ liệu biên với hai chiều. Bất kỳ khác biệt nào với kết quả sắp toàn bộ sẽ ném `AssertionError` thay vì in một số kiểm tra thành công.

Các bộ ngẫu nhiên giúp bắt lỗi đảo chiều và xử lý biên, còn chứng minh bằng bất biến giải thích tại sao thuật toán đúng cho dữ liệu ngoài các bộ thử.


## 10. Xuất kết quả: chọn đúng phần tử chưa đồng nghĩa đã có đúng thứ tự

Có hai đầu việc riêng: chọn các phần tử cần giữ và sắp chúng theo thứ tự muốn trình bày. Trong hàm `topK`, heap giải quyết đầu việc thứ nhất; `result.sort(bestFirst)` giải quyết đầu việc thứ hai.

Không được coi `heap.toString()`, vòng `for-each` hoặc `heap.stream().toList()` là danh sách đã xếp hạng. Chúng duyệt các phần tử của heap, không mô phỏng chuỗi `poll()`. Nếu cần thứ tự rõ ràng, hãy sao chép rồi sắp hoặc lấy lần lượt từ heap. Chương trình đã chọn cách sao chép rồi sắp để tránh phụ thuộc vào thứ tự duyệt.

Ba cách xuất thường gặp:

| Cách xuất | Thứ tự thu được | Ảnh hưởng đến heap |
| --- | --- | --- |
| Sao chép sang danh sách rồi `sort(bestFirst)` | Tốt nhất trước | Giữ nguyên heap |
| `poll()` liên tục từ heap giới hạn K | Yếu nhất trước | Tiêu thụ heap |
| Sao chép heap, `poll()` hết rồi đảo danh sách | Tốt nhất trước, trừ thứ tự giữa các phần tử đồng hạng chưa được phân biệt | Giữ nguyên heap gốc |

Ví dụ heap nhỏ chứa ba số lớn nhất `[9, 9, 8]`. Chuỗi `poll()` là `8, 9, 9`. Nếu muốn kết quả giảm dần, đảo chuỗi đó hoặc sắp danh sách sao chép theo thứ tự giảm.

Khi chỉ cần giá trị lớn thứ K, không cần sắp các ứng viên: sau khi đã đọc ít nhất K phần tử và K > 0, `peek()` của heap nhỏ là đáp án. Với giá trị nhỏ thứ K, dùng `peek()` của heap lớn. Nếu dữ liệu chưa đủ K phần tử, không có phần tử thứ K dù heap vẫn có một đầu hợp lệ.

Nếu chỉ cần một nhóm ứng viên mà thứ tự không quan trọng, có thể bỏ bước sắp kết quả để tiết kiệm chi phí. Hãy thể hiện điều đó trong hợp đồng hàm; đừng trả một `List` chưa sắp nhưng mô tả nó là bảng xếp hạng.

Hàm trong bài sao chép các tham chiếu đối tượng, không sao chép sâu đối tượng. Việc không thay đổi cấu trúc đầu vào không bảo vệ được kết quả khỏi các thay đổi sau này trên chính những đối tượng có thể sửa được.

## 11. Phân tích chi phí theo số phần tử thực sự giữ

Gọi N là số phần tử đầu vào và M = min(K, N), với K > 0. Tạm giả sử đọc một phần tử và so sánh hai phần tử có chi phí O(1).

Heap chỉ giữ tối đa M phần tử. Phép so với ngưỡng không cần tìm kiếm cả heap. Việc đưa một phần tử lên hoặc xuống theo đường từ gốc tới lá có số mức tăng theo logarit kích thước heap; có thể đối chiếu các thao tác `siftUp` và `siftDown` trong [mã nguồn PriorityQueue của OpenJDK 17](https://raw.githubusercontent.com/openjdk/jdk/jdk-17%2B35/src/java.base/share/classes/java/util/PriorityQueue.java).

| Công việc trong thuật toán | Chi phí |
| --- | --- |
| Đọc mỗi phần tử và so với ngưỡng khi đã đầy | O(1) cho phần quyết định |
| Thêm hoặc thay thế ứng viên | O(log(M + 1)) theo phân tích heap |
| Duyệt và chọn trên toàn bộ N phần tử | O(N log(M + 1)) ở trường hợp xấu nhất |
| Sao chép M phần tử kết quả | O(M) |
| Sắp M phần tử theo thứ tự đầu ra | O(M log(M + 1)) |
| Bộ nhớ phụ cho heap và danh sách trả về | O(M + 1), không tính nguồn đầu vào |

Dùng `log(M + 1)` để biểu thức vẫn mô tả đúng trường hợp K = 1. Viết “O(N log K)” là cách nói quen thuộc khi `2 <= K <= N`, nhưng thay K = 1 vào rồi kết luận chi phí bằng 0 là sai. Ta vẫn phải đọc N phần tử để tìm cực trị.

Vì M <= N, toàn bộ hàm với bước sắp kết quả có giới hạn O(N log(M + 1)) cho K > 0, nhưng tách chi phí chọn và chi phí xuất giúp hiểu rõ yêu cầu nào đang tiêu tốn công việc. Với K = 0, hàm đã cho trả ngay sau kiểm tra tham chiếu và K; không có lượt duyệt đầu vào.

Kiểu so ngưỡng trước có thể làm ít thao tác heap hơn giới hạn trường hợp xấu nhất. Nếu sau khi heap đầy có rất ít ứng viên tốt hơn ngưỡng, phần lớn phần tử chỉ được đọc rồi so sánh một lần. Nếu R là số lần thay thế sau khi đã đầy, phần lựa chọn có thể được mô tả chi tiết bằng O(N + (M + R) log(M + 1)). Đây là cách tách công việc, không phải lời bảo đảm rằng dữ liệu thực tế luôn khiến R nhỏ.

Các đánh giá trên nói về thuật toán. Mảng nội bộ của hàng đợi đôi lúc phải tăng dung lượng và sao chép khi nhận thêm phần tử; không diễn giải ký hiệu logarit thành lời hứa rằng mọi lời gọi `offer` đều có cùng độ trễ. Khi nhóm đã đầy và cách cập nhật luôn `poll` trước `offer`, số phần tử không tăng thêm so với kích thước đã đạt.

Nếu comparator tính một đại lượng đắt tiền mỗi lần so, chi phí của nó cũng phải được tính. Ví dụ, không nên phân tích lại một chuỗi JSON hay gọi dịch vụ bên ngoài trong mỗi phép so sánh. Tính trước khóa xếp hạng một lần, lưu cùng bản ghi bất biến, rồi so các khóa có chi phí rõ ràng.

Bộ nhớ O(K) là lợi ích của quá trình chọn khi K nhỏ; nó không xóa chi phí của một danh sách N phần tử đã được tải sẵn. Với dữ liệu rất lớn, cần nối hàm với nguồn có thể duyệt từng phần tử thay vì luôn tạo cả `List` đầu vào. Đồng thời, một nguồn vô hạn sẽ không làm hàm trả về: muốn quan sát top-K liên tục, phải duy trì bộ tích lũy và cung cấp thao tác chụp kết quả riêng.

### Chi phí in dấu vết không phải chi phí cốt lõi

Trong chương trình minh chứng, mỗi dòng `step` gọi `descendingSnapshot`, tức sao chép và sắp nhóm đang giữ để in đẹp. Nếu làm việc này cho mọi phần tử của một luồng lớn, nó cộng chi phí khoảng O(N K log(K + 1)) khi K <= N, cùng chi phí xuất văn bản.

Vì vậy, không dùng thời gian chạy của phần in dấu vết để kết luận chi phí chọn top-K. Hàm `topK` chỉ sắp một lần ở cuối. Khi triển khai thực tế, có thể bỏ in từng bước hoặc chỉ chụp ở những thời điểm cần quan sát.

## 12. Hợp đồng biên và các yêu cầu dễ bị đánh đồng

### K bằng 0, âm hoặc lớn hơn N

K = 0 là yêu cầu chọn không phần tử nào. Trả rỗng ngay là một hợp đồng tiện dụng, nhưng nó cũng có nghĩa không đọc và không kiểm tra các phần tử bên trong nguồn. Một nguồn có phần tử `null` sẽ chưa bị phát hiện ở nhánh này; không được mô tả hàm là đã kiểm tra toàn bộ dữ liệu khi K = 0.

K âm không biểu diễn số phần tử cần lấy. Từ chối nó bằng ngoại lệ làm lỗi của nơi gọi lộ rõ. Nếu ứng dụng muốn coi K âm như 0, phải công bố hợp đồng khác thay vì để hành vi phát sinh ngẫu nhiên từ vòng lặp.

K lớn hơn N có hai lựa chọn thiết kế thường gặp: trả tối đa K phần tử, hoặc bắt buộc đủ K và báo lỗi nếu không đủ. Hàm trong bài chọn “tối đa K”, nên `topK([4, 1], 5, giảm)` trả `[4, 1]`. Đối với API “phần tử lớn thứ năm”, cùng dữ liệu phải báo không tồn tại; không được lấy `peek()` rồi gọi 1 là phần tử lớn thứ năm.

Không nên dùng `new PriorityQueue<>(k)` như cách áp giới hạn. Tham số đó là dung lượng ban đầu, không phải số phần tử tối đa. Nó còn không nhận 0 và có thể cấp phát quá lớn nếu K do đầu vào bên ngoài cung cấp. Hàm tổng quát dùng constructor nhận comparator và tự giới hạn số phần tử bằng điều kiện trong vòng lặp.

### Đúng K phần tử và lấy tất cả phần tử đồng hạng ở ngưỡng

Với `[100, 90, 90, 90, 80]` và K = 2:

- “Lấy đúng tối đa hai phần tử” có thể trả `[100, 90]`.
- “Lấy hai mức điểm cao nhất” trả các mức `[100, 90]` nhưng đó là hai giá trị điểm phân biệt.
- “Lấy top hai và tất cả người đồng điểm với người đứng thứ hai” có thể phải trả bốn bản ghi.

Yêu cầu cuối không còn giới hạn kết quả ở K phần tử. Nếu N bản ghi cùng điểm và chính sách yêu cầu giữ tất cả người đồng hạng ở ngưỡng, kích thước kết quả có thể là N. Không hứa bộ nhớ chỉ O(K) cho toàn bộ kết quả của yêu cầu đó.

Có thể cần hai lượt: lượt đầu xác định ngưỡng, lượt sau lấy tất cả bản ghi đạt ngưỡng, nếu nguồn cho phép đọc lại. Nếu chỉ có một lượt và không thể phục hồi dữ liệu đã bỏ, phải thiết kế lưu trữ phù hợp với chính sách đồng hạng ngay từ đầu.

### Top-K giá trị phân biệt

`PriorityQueue` không phải `Set`. Với `[9, 9, 8, 7]`, K = 3, bài toán đếm từng lần xuất hiện trả `[9, 9, 8]`; bài toán giá trị phân biệt trả `[9, 8, 7]`.

Một cách đơn giản cho dữ liệu hữu hạn là khử trùng bằng `HashSet` trước rồi chạy chọn. Nếu có D giá trị phân biệt, bộ nhớ cho bước khử trùng có thể là O(D), nên không được tiếp tục quảng bá cả quy trình là chỉ dùng O(K) bộ nhớ.

Có những thiết kế phối hợp heap với một tập các giá trị đang được giữ để tránh lưu tất cả giá trị từng thấy. Đó là một thuật toán cần duy trì đồng bộ khi thêm và loại ứng viên; không thể đạt được chỉ bằng cách đặt tên biến là “distinct”. Trong phạm vi bài này, hàm chạy được cố ý giữ nguyên từng lần xuất hiện.

### Top-K theo tần suất

Tìm ba số lớn nhất không giống tìm ba số xuất hiện nhiều nhất. Tần suất là thuộc tính của toàn bộ quá trình đếm, không phải độ lớn của từng số.

Một lời giải cho dữ liệu hữu hạn thường có hai giai đoạn: dùng `Map` tính tần suất theo giá trị, sau đó xếp hạng các cặp giá trị–tần suất bằng heap giới hạn K. Bộ nhớ gồm bản đồ tần suất, không chỉ heap. Nếu cập nhật tần suất trực tiếp của đối tượng đã nằm trong heap mà không sửa lại cấu trúc, ngưỡng có thể sai.

### Đổi dữ liệu đã đọc, xóa phần tử và cửa sổ trượt

Bất biến top-K trong bài giả định mỗi giá trị xếp hạng giữ nguyên và dữ liệu chỉ được thêm. Khi điểm cũ thay đổi hoặc một phần tử rời cửa sổ thời gian, những ứng viên đã loại có thể cần quay lại.

Ví dụ K = 2, từng đọc `10, 9, 8`, heap chỉ còn `[10, 9]`. Nếu 10 hết hạn, kết quả đúng là `[9, 8]`, nhưng heap đã bỏ 8 và không tự tái tạo được nó. Không thể giải top-K cửa sổ trượt chính xác chỉ bằng trạng thái của heap top-K thêm mới này.

Cần giữ thêm dữ liệu, chỉ mục hoặc cấu trúc cho các phần tử ngoài nhóm được chọn. Việc đổi sang hàng đợi ưu tiên an toàn luồng cũng không tự giải quyết thiếu dữ liệu hay làm cả chuỗi “kiểm tra ngưỡng → loại → thêm” trở thành một thao tác nguyên tử.

## 13. Chọn cách làm theo yêu cầu thực tế

Heap giới hạn K là một công cụ phù hợp khi chỉ cần một nhóm nhỏ và có thể đọc tuần tự. Nó không mặc định là phương án tốt nhất cho mọi kích thước K.

| Tình huống | Hướng xử lý hợp lý | Điều cần tính thêm |
| --- | --- | --- |
| K nhỏ hơn nhiều so với N, cần một lượt đọc | Heap giới hạn K | Bước sắp K kết quả nếu cần thứ tự |
| K = 1 | Duyệt giữ một cực trị | O(N) thời gian, O(1) trạng thái; không nhất thiết cần heap |
| K gần N và cần toàn bộ kết quả theo thứ tự | Sắp bản sao đầu vào | Heap vẫn đúng nhưng có thể không đem lại lợi ích |
| Đã cần lưu toàn bộ heap để liên tục lấy phần tử tốt nhất | Heap toàn bộ dữ liệu | O(N) bộ nhớ cho heap, mục đích khác với cắt top-K |
| Mảng đã ở bộ nhớ, chỉ cần một lần chọn ngưỡng | Thuật toán phân hoạch chọn hạng có thể phù hợp | Cách phân hoạch, trường hợp xấu, khả năng sửa mảng và sắp phần kết quả |
| Đầu vào đã được sắp theo đúng thứ tự tốt nhất trước | Lấy tối đa K phần tử đầu | Chỉ dừng sớm khi có bảo đảm thứ tự nguồn |

Không nên đọc K phần tử đầu của nguồn chưa sắp rồi dừng. Dù K số ban đầu đều rất lớn, một số tốt hơn vẫn có thể xuất hiện ở cuối. Với dữ liệu không có bảo đảm bổ sung, phải xét toàn bộ nguồn hữu hạn để kết luận top-K chính xác.

Nếu dùng heap toàn bộ dữ liệu bằng cách `offer` từng phần tử, riêng bước dựng theo cách này có giới hạn O(N log(N + 1)), rồi lấy K lần tốn thêm các thao tác logarit. Không nhầm cách dựng đó với một thuật toán dựng heap hàng loạt có phân tích khác. Để quyết định dùng heap giới hạn K, lợi ích rõ nhất là số ứng viên được giữ chỉ khoảng K khi K nhỏ.

Việc chọn theo điểm cao nhất, khoảng cách ngắn nhất hoặc thời gian nhanh nhất có thể dùng cùng hàm tổng quát. Thay đổi `bestFirst` cho đúng ngữ nghĩa, rồi kiểm tra bằng một cặp ví dụ: bản ghi nào tốt hơn phải có kết quả `compare` âm khi đứng ở đối số thứ nhất.

Ví dụ với khoảng cách nguyên đã tính sẵn, khoảng cách nhỏ hơn tốt hơn thì `Comparator.comparingInt(Item::distance)` là thứ tự kết quả. Heap phải dùng thứ tự đảo để đưa khoảng cách xa nhất trong nhóm đang chọn ra đầu. Nếu tự tính bình phương khoảng cách từ tọa độ nguyên, còn phải xử lý tràn số của phép tính khóa trước khi bàn đến heap; comparator tốt không sửa được một khóa đã bị tính sai.

## 14. Lỗi thường gặp và cách tự phát hiện

| Lỗi | Dấu hiệu quan sát được | Cách sửa |
| --- | --- | --- |
| Giữ K lớn nhất bằng heap lớn và tràn là `poll` | Số lớn nhất biến mất | Đặt phần tử cần loại ở đầu: heap nhỏ |
| Đổi loại heap nhưng quên đổi chiều nhận | Ứng viên kém lại được thêm | So sánh theo một `bestFirst` duy nhất |
| So với `peek` khi heap rỗng | Ngoại lệ do mở hộp `null` | Xử lý K = 0 và nhánh chưa đầy trước |
| Luôn nhận mọi số nhưng không cắt bớt | Kết quả vượt K, bộ nhớ tăng theo N | Duy trì bất biến kích thước sau mỗi bước |
| Dùng `contains` để loại trùng tùy tiện | Thay đổi ngữ nghĩa và thêm tìm kiếm tuyến tính | Quyết định rõ đếm lần xuất hiện hay giá trị phân biệt |
| Dùng `remove(value)` để loại ngưỡng | Tìm kiếm không cần thiết và có thể hiểu nhầm overload | Dùng `poll()` để loại đầu heap |
| In trực tiếp heap làm kết quả đã sắp | Nhìn thấy một dãy không đúng thứ tự mong muốn | Sao chép rồi sắp hoặc lấy hết có kiểm soát |
| Gọi `poll` trên heap còn dùng tiếp | Kích thước và trạng thái bị mất | Chụp bản sao trước khi xuất theo cách tiêu thụ |
| Comparator dùng phép trừ số nguyên | Sai ở giá trị biên dù ví dụ nhỏ đúng | Dùng các hàm so sánh an toàn |
| Cho rằng đồng điểm tự giữ thứ tự đến | Danh tính ở ranh giới thay đổi | Thêm khóa phụ đúng chính sách |
| Thay đổi khóa điểm khi đối tượng còn trong heap | `peek` không còn là ngưỡng đúng | Giữ khóa bất biến hoặc thiết kế cập nhật cấu trúc |
| Coi dung lượng ban đầu là giới hạn K | Hàng đợi vẫn nhận quá K phần tử | Áp điều kiện kích thước trong thuật toán |

Một cách kiểm tra nhanh rất hiệu quả là dùng dữ liệu `[7, 2, 9, 8]` với K = 3, rồi thử K = 0, K = 1, K > N, dãy toàn số bằng nhau và dãy có `Integer.MIN_VALUE`/`Integer.MAX_VALUE`. Sau đó đối chiếu kết quả đã sắp với một lời giải đơn giản bằng sắp toàn bộ. Dữ liệu ngẫu nhiên nên là phần bổ sung cho các trường hợp biên có chủ đích.

## 15. Bài tập và lời giải

### Bài 1 — Chọn heap theo phần tử cần loại

Cần giữ năm sản phẩm có điểm đánh giá cao nhất. Điểm cao hơn tốt hơn. Dùng heap nhỏ hay heap lớn nếu chỉ giữ tối đa năm ứng viên?

**Lời giải:** dùng heap nhỏ theo điểm. Trong năm ứng viên, sản phẩm có điểm thấp nhất là ứng viên yếu nhất; đưa nó ra đầu để so với sản phẩm mới. Nếu cần chọn theo điểm rồi mã sản phẩm, phải đảo đúng toàn bộ thứ tự kết quả để làm comparator của heap.

### Bài 2 — Theo dõi K nhỏ nhất

Dữ liệu `[6, 3, 8, 1, 5, 2]`, K = 3. Hãy ghi các giá trị được giữ sau mỗi bước và đầu heap.

**Lời giải:** dùng heap lớn. Trình bày nhóm theo thứ tự tăng cho dễ đọc:

| Số vừa đọc | Nhóm được giữ | Đầu heap lớn |
| --- | --- | --- |
| 6 | [6] | 6 |
| 3 | [3, 6] | 6 |
| 8 | [3, 6, 8] | 8 |
| 1 | [1, 3, 6] | 6 |
| 5 | [1, 3, 5] | 5 |
| 2 | [1, 2, 3] | 3 |

Khi đầy, ứng viên mới phải nhỏ hơn đầu heap mới được nhận. Đáp án cuối là `[1, 2, 3]`.

### Bài 3 — Tìm phản ví dụ cho heap sai chiều

Một chương trình muốn giữ hai số lớn nhất, dùng heap lớn; sau mỗi lần thêm, nếu kích thước vượt hai thì gọi `poll()`. Cho phản ví dụ ngắn.

**Lời giải:** `[1, 2, 3]`. Sau lần thêm thứ ba, heap lớn lấy 3 ra và giữ 1, 2; đáp án đúng phải là 3, 2. Thuật toán đã loại phần tử tốt nhất.

### Bài 4 — Phần tử lớn thứ K

Với heap nhỏ đang giữ ba số lớn nhất của dữ liệu đã đọc, `peek()` bằng 8. Có thể kết luận giá trị lớn thứ ba là 8 không?

**Lời giải:** có, nếu K = 3, đã đọc ít nhất ba phần tử, heap đang giữ đúng bất biến và tính cả các lần xuất hiện trùng. Nếu mới chỉ đọc một hoặc hai phần tử, không có phần tử lớn thứ ba. Nếu bài toán yêu cầu ba giá trị phân biệt, phải kiểm tra một bất biến khác có khử trùng.

### Bài 5 — Trùng giá trị và đồng hạng

Dữ liệu `[10, 10, 9, 8]`, K = 2. So sánh kết quả của top-K lần xuất hiện và top-K giá trị phân biệt.

**Lời giải:** lần xuất hiện cho `[10, 10]`; giá trị phân biệt cho `[10, 9]`. `PriorityQueue` không tự loại trùng. Chỉ thay điều kiện `>` thành `>=` không biến bài toán đầu thành bài toán thứ hai.

### Bài 6 — Tiêu chí phụ ở ranh giới

Dữ liệu `C:90, B:90, A:90, E:100`, K = 2. Yêu cầu điểm giảm, mã tăng. Đáp án là gì và phần tử nào yếu hơn giữa A:90 và B:90?

**Lời giải:** đáp án `[E:100, A:90]`. Giữa hai bản ghi điểm 90, B:90 yếu hơn A:90 vì mã B đứng sau mã A. Nếu chỉ so điểm, chương trình không có căn cứ chọn A thay B theo yêu cầu này.

### Bài 7 — Đảo comparator toàn bộ hay một tiêu chí?

Cho thứ tự kết quả “điểm giảm, mã tăng”. Nếu heap dùng “điểm tăng, mã tăng”, đã đúng chưa?

**Lời giải:** chưa. Trong nhóm cùng điểm, heap này đưa mã nhỏ lên đầu, tức đưa bản ghi tốt hơn ra trước để loại. Heap đúng phải là đảo toàn bộ thứ tự kết quả: điểm tăng, mã giảm. Dùng `bestFirst.reversed()` tránh bỏ sót tiêu chí phụ.

### Bài 8 — Thứ tự lấy ra khỏi heap

Heap nhỏ giữ ba số lớn nhất, các giá trị là 12, 8, 10. `poll()` liên tục trả gì? Cần làm gì để trả danh sách giảm dần mà vẫn giữ heap?

**Lời giải:** chuỗi lấy ra là `8, 10, 12`. Sao chép các phần tử sang danh sách rồi sắp theo thứ tự giảm, hoặc sao chép cả heap, lấy hết bản sao rồi đảo danh sách. Không dùng thứ tự `for-each` như một bảo đảm xếp hạng.

### Bài 9 — K = 0 có đọc phần tử không?

Với hàm `topK` trong bài, gọi K = 0 trên một nguồn hợp lệ nhưng phần tử bên trong có thể chứa `null`. Hàm có phát hiện `null` không?

**Lời giải:** không duyệt nguồn nên không phát hiện phần tử `null` bên trong. Nó vẫn kiểm tra tham chiếu `input` và `bestFirst` trước khi trả rỗng. Nếu nghiệp vụ bắt buộc xác thực toàn bộ nguồn dù không chọn kết quả nào, cần thiết kế một bước xác thực riêng hoặc thay đổi hợp đồng.

### Bài 10 — Chi phí khi K rất nhỏ

N = một triệu, K = 10. Có cần giữ cả một triệu phần tử trong heap không? Nếu chỉ muốn ngưỡng lớn thứ mười thì cần sắp danh sách kết quả không?

**Lời giải:** không cần giữ toàn bộ; heap giới hạn chỉ giữ tối đa mười phần tử, còn bộ nhớ của nguồn phụ thuộc cách đọc. Sau khi đọc đủ và hoàn tất, ngưỡng là `peek()` của heap nhỏ; không cần sắp mười phần tử nếu chỉ cần giá trị ngưỡng. Vẫn phải đọc toàn bộ nguồn chưa sắp để bảo đảm không bỏ sót số tốt hơn.

### Bài 11 — Vì sao không dùng lại trực tiếp cho cửa sổ trượt?

K = 2, đã đọc 10, 9, 8 và chỉ giữ 10, 9. Khi 10 hết hạn, cần kết quả gì và vì sao heap hiện tại chưa đủ?

**Lời giải:** cần 9, 8, nhưng 8 đã bị bỏ. Heap không thể suy ra lại một dữ liệu không còn được lưu. Cần cấu trúc bổ sung cho các phần tử trong cửa sổ và cách xử lý phần tử hết hạn; chỉ xóa 10 khỏi heap không hoàn thành bài toán.

### Bài 12 — Mở rộng phép đối chiếu

Hãy thêm vào chương trình một phép kiểm tra danh sách ứng viên có cùng điểm nhưng mã khác nhau, so kết quả `topK` với bản sao sắp theo `bestFirst` rồi lấy đầu. Nêu thêm một điều không được kết luận từ việc kiểm tra thành công.

**Lời giải:** dùng lại `candidates` và `bestFirst`, tạo `ArrayList<Candidate>`, sắp nó bằng `bestFirst`, lấy `subList(0, Math.min(k, size))` rồi so danh sách kết quả. Lặp K từ 0 đến lớn hơn số ứng viên để kiểm tra cả biên. Thành công không chứng minh comparator của mọi nghiệp vụ đều đúng, không đo được tốc độ, và không cho phép kết luận heap ổn định nếu đã bỏ tiêu chí phụ.

## 16. Tự kiểm tra trước khi áp dụng

Trước khi viết mã, hãy phát biểu bằng lời: “Tôi giữ tối đa K phần tử tốt nhất theo thứ tự nào; phần tử yếu nhất trong nhóm là gì; ứng viên mới phải thỏa điều kiện nào để thay nó”. Nếu ba câu này chưa nhất quán, việc chọn heap theo trực giác rất dễ sai.

Khi rà soát lời giải, kiểm tra riêng bốn điều: nhóm được chọn có đúng giá trị và số lần xuất hiện không; kích thước có đúng hợp đồng K không; thứ tự kết quả có được tạo một cách rõ ràng không; và các trường hợp đồng hạng đã có chính sách phù hợp chưa.

Quy tắc cần nhớ cho heap giới hạn K là đưa **ứng viên yếu nhất đang giữ** lên đầu. Với K số lớn nhất, đó là heap nhỏ; với K số nhỏ nhất, đó là heap lớn. Thứ tự xuất kết quả được xử lý sau khi đã chọn đúng nhóm.

