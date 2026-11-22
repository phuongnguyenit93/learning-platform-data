# get, set, add theo chỉ số và dịch chuyển phần tử

`List<E>` mô tả một dãy có vị trí. Khi làm việc theo chỉ số, ba thao tác có ý nghĩa khác nhau:

- `get(index)`: đọc phần tử đang có tại một vị trí.
- `set(index, value)`: thay phần tử ở một vị trí đã tồn tại.
- `add(index, value)`: chèn một phần tử mới vào dãy.

Chèn không phải thay thế. Thay thế không phải thêm một phần tử. Phân biệt đúng ba ý nghĩa này giúp tránh lỗi sai kích thước, mất dữ liệu hoặc dùng một chỉ số đã không còn trỏ đến phần tử dự định.

Ví dụ xuyên suốt dùng một danh sách có thể chỉnh sửa:

~~~java
// Đoạn mã trong một phương thức; cần import java.util.List và java.util.ArrayList.
List<String> values = new ArrayList<>(List.of("A", "B", "C"));
~~~

## 1. Chỉ số phần tử và vị trí chèn

Java dùng chỉ số bắt đầu từ `0`:

~~~text
Phần tử: A  B  C
Chỉ số:  0  1  2
size:    3
~~~

Danh sách có `n` phần tử thì:

- Chỉ số phần tử hợp lệ là từ `0` đến `n - 1`.
- Vị trí chèn hợp lệ là từ `0` đến `n`.

Có thể hình dung các khoảng trống để chèn:

~~~text
Khoảng:  0   1   2   3
         | A | B | C |
~~~

Khoảng `3` ở cuối hợp lệ để chèn, nhưng không có phần tử nào ở chỉ số `3` để đọc hoặc thay thế.

| Thao tác | Miền chỉ số hợp lệ khi size = n | Giá trị trả về | Kích thước sau khi thành công |
| --- | --- | --- | --- |
| `get(index)` | `0 <= index < n` | Phần tử ở vị trí đó | `n` |
| `set(index, value)` | `0 <= index < n` | Phần tử cũ bị thay | `n` |
| `add(index, value)` | `0 <= index <= n` | `void` | `n + 1` |

Bảng nói về tác động khi thao tác được nguồn hỗ trợ và hoàn tất thành công. Khả năng chỉnh sửa là điều kiện riêng, không chỉ dựa vào chỉ số hợp lệ. Các hợp đồng được nêu trong [List API của Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html).

## 2. get: đọc một phần tử, không xóa hay dịch dãy

~~~java
List<String> values = new ArrayList<>(List.of("A", "B", "C"));

String result = values.get(1);

System.out.println(result);        // B
System.out.println(values);        // [A, B, C]
System.out.println(values.size()); // 3
~~~

`get(1)` trả B, nhưng B vẫn nằm ở chỉ số `1`. Danh sách không bị tiêu thụ như một lượt duyệt iterator và cũng không bị xóa phần tử như một hàng đợi khi lấy đầu.

Có thể gọi `get(1)` nhiều lần để đọc lại vị trí đó, miễn danh sách và nội dung tại vị trí chưa thay đổi.

### get không trả null để báo chỉ số không tồn tại

~~~java
// values có size bằng 3.
values.get(3);  // IndexOutOfBoundsException
values.get(-1); // IndexOutOfBoundsException
~~~

Nếu nguồn cho phép phần tử `null`, `get` ở một chỉ số hợp lệ có thể trả `null` như dữ liệu. Điều đó khác với chỉ số không hợp lệ.

Không kiểm tra “vị trí có tồn tại không” bằng cách gọi `get` rồi so sánh với `null`. Với thao tác đọc thông thường, miền hợp lệ được xác định bằng `size()` và chỉ số.

Java không dùng `get(-1)` để lấy phần tử cuối như một số ngôn ngữ khác. Nếu cần phần tử cuối theo API theo chỉ số, chỉ số là `size() - 1` và phải có ít nhất một phần tử.

### Giá trị trả về có thể là tham chiếu dùng chung

Với phần tử là đối tượng, `get` trả tham chiếu tới phần tử, không tự sao chép sâu đối tượng đó.

Nếu đối tượng cho phép cập nhật nội dung, sửa đối tượng đã lấy có thể được quan sát qua danh sách vì danh sách vẫn giữ cùng tham chiếu. Ngược lại, gán biến cục bộ sang một đối tượng mới không tự thay ô trong danh sách.

Với ví dụ String, ta dùng các giá trị bất biến để tập trung vào thứ tự vị trí. Không suy ra mọi phần tử của mọi List cũng bất biến.

## 3. set: thay tại vị trí có sẵn

~~~java
List<String> values = new ArrayList<>(List.of("A", "B", "C"));

String old = values.set(1, "B*");

System.out.println(old);           // B
System.out.println(values);        // [A, B*, C]
System.out.println(values.size()); // 3
~~~

Ý nghĩa:

~~~text
Trước:
index  0   1   2
       A   B   C

set(1, "B*")

Sau:
index  0   1   2
       A   B*  C
~~~

A và C giữ nguyên chỉ số. Không có phần tử mới được chèn, không có dịch chuyển phần tử phía sau và size vẫn là `3`.

`set` trả phần tử cũ. Điều này có thể hữu ích nếu cần ghi nhận giá trị trước khi cập nhật hoặc thực hiện một quyết định dựa trên giá trị đã bị thay.

### set không tự mở rộng danh sách

~~~java
List<String> values = new ArrayList<>(List.of("A", "B", "C"));

// Không hợp lệ: chỉ số 3 chưa có phần tử.
values.set(3, "D");
~~~

Không có quy tắc “set vào đúng cuối thì tự thêm”. Muốn tạo vị trí mới, phải chọn thao tác thêm.

Tương tự, không thể dùng set ở chỉ số `10` để tự tạo các vị trí trống từ `3` đến `9`. Java List không mặc nhiên là một bảng thưa tự điền các khoảng thiếu.

### set không tự cập nhật biến đã đọc trước đó

~~~java
List<String> values = new ArrayList<>(List.of("A", "B"));
String saved = values.get(0);

values.set(0, "NEW");

System.out.println(saved);         // A
System.out.println(values.get(0));  // NEW
~~~

`saved` không phải một liên kết động tới “ô số 0”. Nó giữ giá trị tham chiếu nhận được tại lần `get`. Thay tham chiếu mà danh sách lưu không tự gán lại mọi biến đã từng đọc phần tử cũ.

Nếu biến khác trỏ tới chính danh sách:

~~~java
List<String> alias = values;
values.set(0, "HEAD");

System.out.println(alias.get(0)); // HEAD
~~~

`alias` nhìn thấy thay đổi vì hai biến đang tham chiếu cùng đối tượng List, không phải hai bản sao.

## 4. add theo chỉ số: chèn và dịch phần đuôi sang phải

~~~java
List<String> values = new ArrayList<>(List.of("A", "B", "C"));
values.add(1, "X");

System.out.println(values);        // [A, X, B, C]
System.out.println(values.size()); // 4
~~~

`add(1, "X")` đặt X ở chỉ số `1`, trước phần tử trước đó đang ở chỉ số `1`.

~~~text
Trước:
index  0   1   2
       A   B   C

add(1, "X")

Sau:
index  0   1   2   3
       A   X   B   C
~~~

B chuyển từ `1` sang `2`; C chuyển từ `2` sang `3`. A đứng trước điểm chèn nên vẫn ở `0`.

Quy tắc vị trí với chỉ số chèn `p`:

- Các phần tử cũ ở chỉ số nhỏ hơn `p` giữ chỉ số.
- Phần tử mới nhận chỉ số `p`.
- Các phần tử cũ từ `p` trở về sau tăng chỉ số thêm một.

Thứ tự tương đối của các phần tử cũ không thay đổi. B vẫn trước C; chỉ có X được chen vào trước B.

### Chèn ở đầu

~~~java
values.add(0, "HEAD");
~~~

Tất cả phần tử cũ tăng chỉ số thêm một. Đây là lý do lưu một chỉ số rồi tiếp tục dùng nó sau khi chèn ở đầu có thể đọc nhầm phần tử.

### Chèn ở cuối

~~~java
values.add(values.size(), "TAIL");
~~~

Không có phần tử cũ nào ở phía sau để dịch chỉ số. Phần tử mới nhận chỉ số bằng size cũ.

Nếu size ban đầu là `3`, phần tử thêm cuối ở chỉ số `3`, rồi size mới là `4`.

### Chèn vào danh sách rỗng

~~~java
List<String> values = new ArrayList<>();
values.add(0, "first");

System.out.println(values); // [first]
~~~

Với size `0`, chỉ có một vị trí chèn hợp lệ là `0`. Nhưng không có chỉ số hợp lệ nào để gọi get hoặc set trước khi thêm.

## 5. Hai overload add có kiểu trả về khác nhau

| Lời gọi | Ý nghĩa | Kiểu trả về |
| --- | --- | --- |
| `add(element)` | Thêm vào cuối | `boolean` |
| `add(index, element)` | Chèn tại vị trí xác định | `void` |

Ví dụ:

~~~java
List<String> values = new ArrayList<>(List.of("A", "B"));

boolean changed = values.add("C");
values.add(1, "X");

System.out.println(changed); // true
System.out.println(values);  // [A, X, B, C]
~~~

Không gán kết quả của overload hai tham số vào biến:

~~~java
// Không biên dịch: add(index, element) trả void.
// boolean changed = values.add(1, "X");
~~~

Về nội dung kết quả của danh sách thông thường hỗ trợ thêm, `add(e)` có tác dụng thêm cuối như `add(size(), e)`. Nhưng chúng là hai chữ ký khác nhau, với kiểu trả về khác nhau.

### List<Integer>: vị trí vẫn là tham số thứ nhất

~~~java
List<Integer> numbers = new ArrayList<>(List.of(10, 20, 30));

numbers.add(1, 99);
System.out.println(numbers); // [10, 99, 20, 30]
~~~

Số `1` là chỉ số chèn, `99` là phần tử được boxing thành Integer. Không có cách hiểu “chèn 1 tại giá trị 99” chỉ vì cả hai tham số đều viết bằng số.

Tương tự:

~~~java
int old = numbers.set(2, 77);

System.out.println(old);     // 20
System.out.println(numbers); // [10, 99, 77, 30]
~~~

Chỉ số nói vị trí trong dãy, không nói giá trị cần tìm.

## 6. Nhiều lần chèn và sự dịch chuyển của chỉ số

Bắt đầu:

~~~text
[A, B, C]
~~~

Hai lần chèn tại cùng chỉ số:

~~~java
values.add(1, "X");
values.add(1, "Y");
~~~

Kết quả:

~~~text
[A, Y, X, B, C]
~~~

Lần đầu X ở chỉ số `1`. Lần sau Y chèn trước phần tử hiện ở chỉ số `1`, chính là X. Vì vậy Y đứng trước X.

Nếu muốn X rồi Y:

~~~java
values.add(1, "X");
values.add(2, "Y");
~~~

Kết quả từ nguồn ban đầu là:

~~~text
[A, X, Y, B, C]
~~~

Cần tính chỉ số theo trạng thái danh sách **sau mỗi bước**, không theo một ảnh ban đầu đã hết đúng.

Với nhu cầu chèn cả một dãy tại một vị trí, API như `addAll(index, collection)` có thể diễn đạt ý định rõ hơn. Khi chèn nhiều lần, phải kiểm tra cả nội dung lẫn thứ tự của những phần tử thêm, không chỉ size cuối.

### Chỉ số không phải định danh ổn định

Trong chương trình hoàn chỉnh:

~~~text
[A, B*, C]        -> B* ở 1
[A, X, B*, C]     -> B* ở 2
[H, A, X, B*, C]  -> B* ở 3
~~~

B* không đổi nội dung, nhưng chỉ số đổi hai lần.

Nếu ứng dụng lưu “người dùng đang chọn hàng số 1” rồi dữ liệu được chèn trước đó, vị trí `1` có thể không còn là thực thể cũ. Khi cần theo dõi thực thể, dùng định danh thuộc về dữ liệu; khi cần theo dõi vị trí, phải cập nhật vị trí theo đúng quy tắc thay đổi.

`indexOf(value)` có thể tìm một vị trí theo phép so sánh giá trị của danh sách, nhưng không tự trở thành định danh duy nhất. Nếu có phần tử trùng, nó chỉ cho một kết quả theo hợp đồng tìm kiếm của List.

## 7. Vì sao capacity không mở rộng miền chỉ số?

~~~java
ArrayList<String> values = new ArrayList<>(10);

System.out.println(values.size()); // 0

// values.set(0, "A"); // IndexOutOfBoundsException
values.add(0, "A");    // Hợp lệ.
~~~

Tham số `10` đặt sức chứa ban đầu của ArrayList, không tạo mười phần tử.

Phân biệt:

- **Size:** số phần tử hiện thuộc danh sách.
- **Capacity:** sức chứa của vùng lưu trữ nội bộ ở một thời điểm.

Miền chỉ số công khai của get/set/add được xác định bởi **size**, không bởi số ô mà mảng nội bộ có thể còn chứa được.

Một mảng `new String[10]` có độ dài `10` và các ô ban đầu mang giá trị `null`. Một ArrayList có capacity `10` nhưng size `0` vẫn là danh sách rỗng. Hai cách khởi tạo không có cùng ý nghĩa.

Không dùng nhiều lần set để lấp sức chứa đã đặt trước. Nếu ý định là thêm phần tử, hãy dùng add theo đúng miền vị trí chèn.

## 8. Dịch chuyển logic và cách lưu trữ vật lý

Hợp đồng List xác định các chỉ số sau khi chèn. Nó không bắt buộc mọi lớp List phải lưu bằng mảng và sao chép phần tử theo cùng một thuật toán.

### Với ArrayList

Có thể hình dung một mảng nội bộ đang chứa:

~~~text
A B C D _
~~~

Chèn X tại chỉ số `2` cần giữ C và D, tạo chỗ cho X:

~~~text
Trước: A B C D _
Sau:   A B X C D
~~~

Phần đuôi từ vị trí chèn phải được dời trong mảng lưu trữ. Nếu vùng lưu không còn đủ, còn có chi phí tạo vùng lưu lớn hơn và chuyển dữ liệu sang đó.

Đây là mô hình để hiểu chi phí, không phải hướng dẫn tự truy cập mảng nội bộ của ArrayList. Tốc độ tăng capacity là chi tiết triển khai; không dựa vào một hệ số cụ thể để viết logic ứng dụng. Xem [ArrayList API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html).

### Với LinkedList

LinkedList có thể tìm tới nút ở vị trí cần thiết rồi thay đổi các liên kết. Các phần tử phía sau vẫn có chỉ số logic tăng một, dù không phải dịch từng phần tử sang một ô mảng khác.

Do đó câu “chèn làm dịch các chỉ số phía sau” đúng ở mức List. Câu “mọi List đều phải sao chép toàn bộ phần đuôi trong bộ nhớ” không đúng.

Việc tìm nút theo chỉ số cũng có chi phí. Không từ “thêm nút nhanh khi đã biết vị trí nút” suy ra `add(index, value)` ở một chỉ số bất kỳ luôn là hằng số. Xem đặc điểm truy cập theo chỉ số trong [LinkedList API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html).

### Bảng chi phí để định hướng

Với các triển khai thông thường, n là số phần tử, p là vị trí:

| Thao tác | ArrayList | LinkedList |
| --- | --- | --- |
| get/set tại chỉ số bất kỳ | Truy cập vị trí mảng, thường O(1) | Cần tìm nút, O(n) trong trường hợp xấu nhất |
| Chèn đầu | Phải dời phần đuôi, O(n) | Có thể thao tác trực tiếp ở đầu, O(1) |
| Chèn giữa bằng chỉ số | Chi phí dời phần đuôi, thường O(n - p), có thể thêm chi phí mở rộng | Tìm vị trí có thể O(n), rồi nối nút |
| Thêm cuối | O(1) khấu hao, nhưng một lần mở rộng có thể O(n) | Có thể thao tác trực tiếp ở cuối, O(1) |

Bảng không phải lời khuyên luôn chọn lớp này hay lớp kia. Kích thước dữ liệu, kiểu truy cập, tính cục bộ bộ nhớ và toàn bộ mẫu xử lý đều ảnh hưởng lựa chọn.

Nếu chỉ cần duyệt toàn bộ một List mà không biết lớp thực tế, for-each hoặc iterator tránh việc ép thuật toán phụ thuộc truy cập ngẫu nhiên qua get. Lặp `get(i)` trên LinkedList có thể làm tổng chi phí tăng lên O(n²).

## 9. Chỉ số đúng chưa đủ: nguồn có cho sửa không?

`get` là thao tác đọc. `set` và `add` là các thao tác thay đổi có thể không được nguồn hỗ trợ.

| Nguồn | get ở chỉ số hợp lệ | set | add làm tăng kích thước |
| --- | --- | --- | --- |
| ArrayList có thể sửa | Được | Được | Được |
| LinkedList có thể sửa | Được | Được | Được |
| Arrays.asList(array) | Được | Được; thay đổi phản ánh về mảng | Không hỗ trợ |
| List.of / List.copyOf | Được | Không hỗ trợ | Không hỗ trợ |
| Góc nhìn Collections.unmodifiableList | Được | Không hỗ trợ qua góc nhìn | Không hỗ trợ qua góc nhìn |

Ví dụ danh sách có kích thước cố định:

~~~java
String[] array = {"L", "R"};
List<String> fixed = Arrays.asList(array);

fixed.set(0, "L*");

System.out.println(fixed);                  // [L*, R]
System.out.println(Arrays.toString(array)); // [L*, R]

// fixed.add(1, "M"); // UnsupportedOperationException
~~~

Nó có thể thay một phần tử nhưng không đổi kích thước. Không gọi mọi danh sách từ `Arrays.asList` là hoàn toàn không sửa được. Xem [Arrays.asList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...)).

Với danh sách không cho sửa đổi, muốn chỉnh sửa một dãy mới có thể tạo bản sao:

~~~java
List<String> editable = new ArrayList<>(source);
editable.add(0, "new");
~~~

Tạo bản sao không biến nguồn thành có thể sửa; nó tạo một đối tượng danh sách khác. Các phần tử dạng đối tượng vẫn có thể được chia sẻ do đây không phải sao chép sâu.

### Giới hạn phần tử là điều kiện riêng

Một nguồn có thể giới hạn `null`, kiểu runtime hoặc giá trị hợp lệ. Không suy ra “chỉ số đúng và có hỗ trợ add” nghĩa mọi phần tử đều được chấp nhận.

Với generic, trình biên dịch giúp kiểm tra kiểu phần tử, nhưng các lớp bao bọc kiểm tra hoặc nguồn chuyên biệt còn có thể có quy tắc runtime riêng. Hãy phân biệt lỗi miền chỉ số với lỗi thao tác không được hỗ trợ và lỗi dữ liệu bị từ chối.

## 10. Chèn khi đang duyệt: tránh quản lý sai tiến độ

Một vòng lặp đọc theo chỉ số:

~~~java
for (int i = 0; i < values.size(); i++) {
    String value = values.get(i);
    System.out.println(value);
}
~~~

Khi danh sách không bị chỉnh sửa trong vòng lặp, ý nghĩa vị trí thường dễ hiểu. Nhưng nếu chèn trước phần tử hiện tại:

~~~java
// Minh họa một bẫy logic, không phải mẫu xử lý nên dùng.
for (int i = 0; i < values.size(); i++) {
    if (needsMarker(values.get(i))) {
        values.add(i, "marker");
    }
}
~~~

`needsMarker` là một điều kiện minh họa do ứng dụng cung cấp.

Sau khi chèn tại `i`, phần tử vừa được kiểm tra chuyển sang `i + 1`. Vòng lặp tăng i rồi có thể kiểm tra lại chính phần tử đó. Nếu điều kiện tiếp tục đúng, danh sách có thể liên tục tăng mà thuật toán không tiến qua phần tử gốc như dự định.

Cần thiết kế rõ có muốn duyệt các phần tử mới chèn hay không. Những lựa chọn khác gồm:

- Dùng ListIterator để điều khiển chèn/thay theo vị trí duyệt.
- Tạo danh sách kết quả mới từ nguồn không đổi.
- Thu các thay đổi rồi áp dụng ở giai đoạn sau.
- Tính quy tắc cập nhật chỉ số thật rõ nếu chỉ số là phần thiết yếu của thuật toán.

Không sửa trực tiếp cấu trúc List trong for-each rồi chỉ kiểm tra xem có ngoại lệ hay không. Không có ngoại lệ không chứng minh thuật toán duyệt đúng, và fail-fast không phải công cụ điều khiển việc chèn.

### Chỉ số của view là tương đối với view

Nếu thao tác trên một `subList`, chỉ số `0` là đầu của view đó, không mặc nhiên là đầu danh sách gốc. Thay đổi qua view có thể phản ánh về nguồn phía sau.

Vì vậy, khi truyền một chỉ số giữa các tầng, cần biết nó thuộc dãy nào và tại thời điểm nào. Một số nguyên không tự mang thông tin về nguồn mà nó mô tả.

### Kiểm tra rồi thao tác không tự nguyên tử

Trong môi trường nhiều luồng, kiểm tra `index < size()` rồi gọi `get/set/add` ở bước sau không tự bảo đảm nguồn không bị đổi giữa hai bước. Đây là vấn đề về giao thức truy cập đồng thời, cần giải quyết riêng; các miền chỉ số vẫn đúng nhưng không tạo khóa cho chuỗi thao tác.

## 11. Chương trình hoàn chỉnh

Lưu thành **ListIndexOperationsDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class ListIndexOperationsDemo {
    public static void main(String[] args) {
        List<String> values = new ArrayList<>(List.of("A", "B", "C"));
        show("Initial", values);

        String read = values.get(1);
        System.out.println("get(1) = " + read);
        show("After get", values);

        String replaced = values.set(1, "B*");
        System.out.println("set(1) returned = " + replaced);
        show("After set", values);

        values.add(1, "X");
        show("After add(1, X)", values);
        System.out.println("B* now has index = " + values.indexOf("B*"));

        values.add(0, "H");
        show("After add(0, H)", values);
        System.out.println("B* after another insertion = "
                + values.indexOf("B*"));

        values.add(values.size(), "T");
        show("After add(size, T)", values);
        boolean changed = values.add("U");
        System.out.println("add(U) returned = " + changed);
        show("After append", values);

        String oldFirst = values.get(0);
        List<String> alias = values;
        values.set(0, "HEAD");
        System.out.println("Saved old first = " + oldFirst);
        System.out.println("Alias first = " + alias.get(0));

        expectIndexError("get(size)", () -> values.get(values.size()));
        expectIndexError("set(size)",
                () -> values.set(values.size(), "bad"));
        expectIndexError("add(size + 1)",
                () -> values.add(values.size() + 1, "bad"));
        expectIndexError("get(-1)", () -> values.get(-1));

        ArrayList<String> reserved = new ArrayList<>(10);
        System.out.println("Reserved capacity, size = " + reserved.size());
        expectIndexError("set on empty", () -> reserved.set(0, "first"));
        reserved.add(0, "first");
        show("Empty list after add(0)", reserved);

        List<Integer> numbers = new ArrayList<>(List.of(10, 20, 30));
        numbers.add(1, 99);
        System.out.println("Integer list after add(1, 99) = " + numbers);
        int oldNumber = numbers.set(2, 77);
        System.out.println("Integer set returned = " + oldNumber);
        System.out.println("Integer list after set(2, 77) = " + numbers);

        String[] array = {"L", "R"};
        List<String> fixed = Arrays.asList(array);
        fixed.set(0, "L*");
        System.out.println("Fixed-size after set = " + fixed);
        System.out.println("Backing array = " + Arrays.toString(array));
        expectUnsupported("Fixed-size indexed add",
                () -> fixed.add(1, "M"));

        List<String> unmodifiable = List.of("A", "B");
        System.out.println("Unmodifiable get(1) = " + unmodifiable.get(1));
        expectUnsupported("Unmodifiable set",
                () -> unmodifiable.set(1, "B*"));
    }

    private static void show(String label, List<?> values) {
        System.out.println(label + " = " + values + "; size=" + values.size());
    }

    private static void expectIndexError(String label, Runnable operation) {
        try {
            operation.run();
            throw new AssertionError("Expected IndexOutOfBoundsException");
        } catch (IndexOutOfBoundsException exception) {
            System.out.println(label + " -> "
                    + exception.getClass().getSimpleName());
        }
    }

    private static void expectUnsupported(String label, Runnable operation) {
        try {
            operation.run();
            throw new AssertionError("Expected UnsupportedOperationException");
        } catch (UnsupportedOperationException exception) {
            System.out.println(label + " -> "
                    + exception.getClass().getSimpleName());
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~shell
javac --release 17 -encoding UTF-8 ListIndexOperationsDemo.java
java ListIndexOperationsDemo
~~~

Stdout:

~~~text
Initial = [A, B, C]; size=3
get(1) = B
After get = [A, B, C]; size=3
set(1) returned = B
After set = [A, B*, C]; size=3
After add(1, X) = [A, X, B*, C]; size=4
B* now has index = 2
After add(0, H) = [H, A, X, B*, C]; size=5
B* after another insertion = 3
After add(size, T) = [H, A, X, B*, C, T]; size=6
add(U) returned = true
After append = [H, A, X, B*, C, T, U]; size=7
Saved old first = H
Alias first = HEAD
get(size) -> IndexOutOfBoundsException
set(size) -> IndexOutOfBoundsException
add(size + 1) -> IndexOutOfBoundsException
get(-1) -> IndexOutOfBoundsException
Reserved capacity, size = 0
set on empty -> IndexOutOfBoundsException
Empty list after add(0) = [first]; size=1
Integer list after add(1, 99) = [10, 99, 20, 30]
Integer set returned = 20
Integer list after set(2, 77) = [10, 99, 77, 30]
Fixed-size after set = [L*, R]
Backing array = [L*, R]
Fixed-size indexed add -> UnsupportedOperationException
Unmodifiable get(1) = B
Unmodifiable set -> UnsupportedOperationException
~~~

Các hàm bắt ngoại lệ trong chương trình phục vụ kiểm chứng ca lỗi. Nếu thao tác không ném như dự kiến, chương trình chủ động ném AssertionError để ví dụ không âm thầm coi một kết quả khác là đúng.

## 12. Đọc kết quả theo từng thao tác

### Đọc rồi thay thế

get(1) trả B nhưng dãy và size không đổi. set(1, B*) trả B cũ và thay đúng vị trí `1`, vẫn size `3`.

### Chèn ở giữa rồi ở đầu

add(1, X) làm B* từ `1` sang `2`. Thêm H vào đầu làm B* sang `3`. Đây là hai lần đổi chỉ số của cùng nội dung, không phải B* tự bị thay giá trị.

### Hai cách thêm cuối

add(size, T) thêm T vào cuối. add(U) cũng thêm cuối nhưng trả boolean true. Chương trình không gán kết quả của overload hai tham số vì nó trả void.

### Biến đã lưu và alias của danh sách

Biến oldFirst nhận H trước khi phần tử đầu được thay thành HEAD. Nó vẫn giữ H. Biến alias trỏ cùng List nên alias.get(0) nhận HEAD sau thay đổi.

### Miền chỉ số lỗi

get(size), set(size), add(size + 1) và get(-1) đều không nằm trong miền tương ứng. Chương trình chỉ kiểm tra tên loại ngoại lệ, không phụ thuộc toàn văn thông điệp lỗi có thể khác theo phiên bản.

### Capacity ban đầu

new ArrayList(10) chưa tạo phần tử; size vẫn `0`. set(0) thất bại, nhưng add(0) tạo phần tử đầu.

### Danh sách số nguyên

add(1, 99) chèn `99` trước `20`. Sau đó set(2, 77) thay `20` bằng `77` và trả lại `20`. Chỉ số và giá trị số là hai vai trò riêng.

### Nguồn có giới hạn

Arrays.asList cho thay L thành L*, phản ánh về mảng, nhưng từ chối chèn. List.of cho đọc B ở chỉ số hợp lệ nhưng từ chối set. Khả năng sửa không được suy ra chỉ từ kiểu khai báo `List<String>`.

## 13. Cách kiểm tra một thuật toán dùng chỉ số

Với mỗi thao tác, hãy viết trạng thái trước và sau:

1. Size trước thao tác là bao nhiêu?
2. Thao tác cần một phần tử có sẵn hay một khoảng trống để chèn?
3. Chỉ số có trong miền đúng không?
4. Nguồn có hỗ trợ thay đổi không?
5. Phần tử nào đổi giá trị, phần tử nào đổi chỉ số?
6. Chỉ số đang lưu ở nơi khác còn đúng với ý định không?

Các ca nhỏ hữu ích:

- Danh sách rỗng: get/set đều không có chỉ số hợp lệ; add chỉ có vị trí `0`.
- Một phần tử: get/set ở `0`; add ở `0` hoặc `1`.
- Danh sách nhiều phần tử: thao tác đầu, giữa và cuối.
- Chỉ số `-1`, `size()`, `size() + 1`.
- Set rồi kiểm tra phần tử cũ được trả về và size không đổi.
- Add rồi kiểm tra toàn bộ thứ tự phần đuôi, không chỉ phần tử vừa thêm.
- Hai lần chèn cùng vị trí.
- Các phần tử trùng để tránh coi giá trị là định danh duy nhất.
- Nguồn cố định kích thước hoặc không cho sửa đổi.

Khi một chỉ số được tính từ một bước tìm kiếm hoặc lựa chọn của người dùng, hãy kiểm tra nó còn mô tả đúng trạng thái hiện tại trước khi thực hiện cập nhật.

## 14. Lỗi thường gặp

| Hiểu nhầm hoặc cách viết | Vấn đề | Cách sửa |
| --- | --- | --- |
| Dùng set để thêm phần tử ở cuối | Chỉ số chưa có phần tử | Dùng add cho vị trí mới. |
| Dùng add để cập nhật một giá trị | Dữ liệu cũ bị đẩy, size tăng | Dùng set nếu muốn thay thế. |
| Cho rằng get(size) lấy phần tử cuối | Chỉ số cuối là size - 1 khi không rỗng | Phân biệt số lượng với chỉ số lớn nhất. |
| Nghĩ add(size, e) cũng vượt miền | Vị trí chèn được phép bằng size | Dùng miền riêng cho add. |
| Dùng get(-1) | Java không có quy tắc chỉ số âm ở đây | Tính chỉ số cuối và kiểm tra danh sách không rỗng. |
| Đặt capacity rồi gọi set vào phần tử chưa có | Capacity không phải size | Tạo phần tử bằng thao tác thêm. |
| Chèn nhiều lần cùng chỉ số và mong thứ tự thêm được giữ | Mỗi lần mới đều chèn trước vị trí hiện tại | Tăng vị trí hoặc dùng thao tác thêm cả dãy phù hợp. |
| Lưu chỉ số như ID lâu dài | Chèn/xóa/sắp xếp có thể đổi phần tử tại vị trí | Theo dõi định danh dữ liệu hoặc cập nhật vị trí. |
| Mọi List đều truy cập chỉ số O(1) | Hợp đồng List không áp đặt cách lưu | Xét triển khai và mẫu truy cập. |
| Mọi List có thể get thì đều có thể set/add | Khả năng sửa là tùy chọn | Kiểm tra nguồn hoặc tạo bản sao có thể sửa. |
| Muốn loại bỏ ngoại lệ nên đổi sang vòng lặp chỉ số | Vẫn có thể sai về tiến độ hoặc đồng thời | Kiểm tra nội dung và số lần xử lý, không chỉ ngoại lệ. |

## 15. Thực hành

1. Với `[A, B, C, D]`, dự đoán kết quả và size sau get(2), set(2, X), add(2, Y). Ghi riêng giá trị trả về của từng phương thức.
2. Từ danh sách rỗng, tạo `[A, B, C]` bằng add theo chỉ số. Chỉ ra vị trí hợp lệ ở từng bước.
3. Chèn X rồi Y tại cùng chỉ số `0`. Viết thứ tự cuối, sau đó sửa cách gọi để giữ X trước Y.
4. Lưu chỉ số của B trong `[A, B, C]`, thêm hai phần tử trước B rồi quan sát chỉ số cũ trỏ tới đâu.
5. So sánh set và add trên ArrayList, Arrays.asList và List.of. Phân biệt sai chỉ số với thao tác không được hỗ trợ.
6. Viết một hàm nhận List và vị trí chèn do người dùng chọn. Định nghĩa rõ miền vị trí, chính sách lỗi và việc hàm sửa nguồn hay tạo dãy mới.
7. Đánh giá chi phí một vòng get(i) trên ArrayList và LinkedList, rồi chọn cách duyệt khi chỉ cần xử lý mọi phần tử.

Khi đọc một lời gọi theo chỉ số, hãy xác định trước nó đang **đọc**, **thay vị trí có sẵn** hay **tạo vị trí mới**. Sau đó dùng size hiện tại để kiểm tra miền và cập nhật mọi suy luận về những phần tử phía sau điểm chèn.
