# Phân biệt thứ tự chèn, thứ tự duyệt, chỉ số và thứ tự sắp xếp

Trong Java Collections, từ “thứ tự” có thể đang nói đến những điều khác nhau. Một tập hợp có thể giữ thứ tự chèn nhưng không có chỉ số. Một tập hợp khác có thể duyệt theo thứ tự sắp xếp nhưng không cho phép gọi `get(0)`. Một hàng đợi có thể lấy phần tử theo độ ưu tiên nhưng iterator lại không duyệt theo thứ tự ưu tiên đó.

Để chọn đúng cấu trúc dữ liệu và đọc đúng kết quả chương trình, cần tách bốn khái niệm: **thứ tự chèn**, **thứ tự duyệt**, **chỉ số** và **thứ tự sắp xếp**.

## 1. Bốn câu hỏi khác nhau

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| Thứ tự chèn (insertion order) | Các phần tử được thêm vào tập hợp theo trình tự nào, và tập hợp có giữ trình tự đó không? | Thêm `B`, rồi `A`, rồi `C` vào `LinkedHashSet`; duyệt nhận `B, A, C`. |
| Thứ tự duyệt (iteration order) | Trong một lượt duyệt, iterator trả về các phần tử theo trình tự nào? | `TreeSet` duyệt theo quy tắc so sánh, không theo lịch sử thêm. |
| Chỉ số (index) | Phần tử đang nằm tại vị trí đánh số nào trong một dãy? | Trong `List.of(30, 10, 20)`, chỉ số `1` chứa giá trị `10`. |
| Thứ tự sắp xếp (sorted order) | Các phần tử có tuân theo một quan hệ so sánh không? | Với số nguyên tăng dần: `10, 20, 30`. |

Bốn khái niệm có thể cùng xuất hiện, nhưng không thay thế nhau:

- Thứ tự chèn có thể quyết định thứ tự duyệt, như các thao tác thêm thông thường của `LinkedHashSet`.
- Thứ tự sắp xếp có thể quyết định thứ tự duyệt, như `TreeSet`.
- Chỉ số gắn với dãy có vị trí như `List`; thứ tự duyệt xác định không tự tạo ra API chỉ số.
- Một dãy có chỉ số có thể chưa được sắp xếp.

Chỉ nhìn kết quả `[10, 20, 30]` chưa đủ để biết dữ liệu đã được sắp xếp, được chèn sẵn theo thứ tự đó, hay tình cờ được duyệt như vậy.

## 2. Thứ tự chèn: lịch sử thêm và cam kết giữ thứ tự

Giả sử các lệnh được thực hiện theo trình tự:

~~~java
// Đoạn mã trong một phương thức; cần import java.util.LinkedHashSet.
LinkedHashSet<String> values = new LinkedHashSet<>();
values.add("B");
values.add("A");
values.add("C");

System.out.println(values); // [B, A, C]
~~~

Với các thao tác `add` thông thường này, `LinkedHashSet` giữ thứ tự chèn. Thứ tự duyệt phản ánh trình tự thêm `B`, `A`, `C`.

Điều đó không có nghĩa mọi phương thức tên `add` trên mọi loại tập hợp đều giữ lịch sử chèn theo cùng một cách.

### Thêm lại phần tử đã tồn tại

`Set` không thêm một bản sao chỉ vì gọi `add` lần nữa:

~~~java
// Tiếp tục với values ở trên.
System.out.println(values.add("A")); // false
System.out.println(values);          // [B, A, C]
~~~

Phần tử `A` đã có trong tập hợp. Lần gọi `add("A")` thông thường không chuyển nó xuống cuối.

Nhưng xóa rồi thêm lại là một tình huống khác:

~~~java
values.remove("A");
values.add("A");

System.out.println(values); // [B, C, A]
~~~

Sau khi bị xóa, `A` không còn vị trí cũ. Lần thêm mới đặt nó vào cuối thứ tự chèn hiện tại.

### List có thể chèn vào giữa

Một danh sách thường được tạo bằng cách thêm vào cuối nên ban đầu thứ tự của nó trùng với trình tự các lần thêm. Tuy nhiên, `List` còn cho chèn vào vị trí cụ thể:

~~~java
// Cần import java.util.ArrayList và java.util.List.
List<String> list = new ArrayList<>();
list.add("B");
list.add("C");
list.add(0, "A");

System.out.println(list); // [A, B, C]
~~~

Lịch sử gọi thêm là `B, C, A`, nhưng dãy hiện tại là `A, B, C`. Phần tử mới không nhất thiết đứng sau phần tử cũ: thao tác chèn theo chỉ số có ý nghĩa riêng.

Vì vậy, khi đọc `List`, nên nói rõ **thứ tự vị trí hiện tại**. Không suy ra lịch sử tạo hoặc thêm phần tử chỉ từ kết quả duyệt sau nhiều thao tác chỉnh sửa.

### Deque cho thấy rõ sự khác nhau này

~~~java
// Cần import java.util.ArrayDeque và java.util.Deque.
Deque<String> deque = new ArrayDeque<>();
deque.addLast("B");
deque.addLast("C");
deque.addFirst("A");

System.out.println(deque); // [A, B, C]
~~~

Phần tử `A` được thêm sau cùng nhưng được đặt ở đầu. Iterator thông thường duyệt từ đầu đến cuối deque, nên thứ tự duyệt không trùng với lịch sử thời gian của các lời gọi thêm.

## 3. Thứ tự duyệt: điều iterator thực sự trả về

Thứ tự duyệt là trình tự phần tử quan sát được khi dùng iterator. For-each trên một `Iterable` sử dụng cơ chế đó:

~~~java
// Đoạn mã minh họa; source là một Iterable<String> đã có.
for (String value : source) {
    System.out.println(value);
}
~~~

Câu hỏi cần đặt ra không chỉ là “lần chạy này in gì?”, mà còn là “hợp đồng của loại tập hợp có cam kết trình tự đó không?”.

### Ba trường hợp điển hình

- `List`: iterator thông thường đi theo thứ tự vị trí của danh sách.
- `LinkedHashSet`: với các thao tác thêm thông thường, duyệt theo thứ tự chèn.
- `TreeSet`: duyệt theo thứ tự tăng dần của quan hệ so sánh đang dùng.

`HashSet` không cam kết thứ tự duyệt. Điều này không đồng nghĩa “mỗi lần duyệt đều ngẫu nhiên” hay “mỗi lần chạy chắc chắn khác nhau”.

Một `HashSet` có thể nhiều lần hiển thị cùng trình tự. Với một số dữ liệu số nguyên, trình tự tình cờ còn có thể trông như đã sắp xếp. Kết quả quan sát đó không trở thành cam kết API. Thay dữ liệu, thay lịch sử thêm/xóa, thay cấu trúc nội bộ hoặc thay phiên bản triển khai có thể làm kết quả khác đi.

Không viết kiểm thử dựa trên một thứ tự mà hợp đồng không cung cấp.

### toString không chứng minh có sắp xếp

Nhiều lớp tập hợp tạo chuỗi hiển thị dựa trên iterator. Nếu nhìn thấy:

~~~text
[10, 20, 30]
~~~

không thể kết luận nguồn có hợp đồng sắp xếp. Muốn kết luận, cần biết lớp triển khai, comparator nếu có, và thao tác đã thực hiện.

Việc sao chép `HashSet` sang `ArrayList` cũng chỉ lấy một thứ tự duyệt của nguồn tại lần sao chép đó:

~~~java
// Đoạn mã trong một phương thức; cần các import java.util tương ứng.
Set<Integer> source = new HashSet<>(List.of(30, 10, 20));
List<Integer> copy = new ArrayList<>(source);
~~~

`copy` có chỉ số và giữ dãy đã sao chép, nhưng thao tác này không khôi phục lịch sử chèn của `source` và không tự sắp xếp dữ liệu. Ví dụ giả định không có thay đổi đồng thời trong khi sao chép.

## 4. Chỉ số: vị trí hiện tại, không phải danh tính

Chỉ số của `List` bắt đầu từ `0`. Phần tử đầu tiên ở chỉ số `0`, phần tử thứ hai ở chỉ số `1`.

~~~java
List<Integer> values = new ArrayList<>(List.of(30, 10, 20));

System.out.println(values.get(1)); // 10
values.add(1, 99);

System.out.println(values);       // [30, 99, 10, 20]
System.out.println(values.get(1)); // 99
System.out.println(values.get(2)); // 10
~~~

Giá trị `10` vẫn có trong danh sách nhưng chuyển từ chỉ số `1` sang chỉ số `2`. Điều này cho thấy chỉ số mô tả **vị trí ở thời điểm hiện tại**, không phải mã nhận dạng ổn định.

Các thao tác sau có thể thay đổi phần tử mà một chỉ số đang trỏ đến:

- Chèn hoặc xóa trước vị trí đó.
- Sắp xếp lại danh sách.
- Đảo dãy.
- Thay thế phần tử bằng `set(index, value)`.

Không lưu chỉ số của một đơn hàng rồi coi nó như ID của đơn hàng qua nhiều lần thay đổi danh sách. Khi cần nhận diện một thực thể, hãy dùng định danh thuộc về dữ liệu hoặc một cấu trúc tra cứu phù hợp.

### Thứ tự duyệt không kéo theo get(index)

`LinkedHashSet`, `TreeSet` và `ArrayDeque` có thể có thứ tự duyệt xác định, nhưng không cung cấp hợp đồng `List.get(index)`.

Có thể tự duyệt để đếm đến phần tử thứ ba, nhưng đó là một thuật toán duyệt, không phải bằng chứng rằng tập hợp có API truy cập theo chỉ số. Nếu tạo `new ArrayList<>(set)`, API chỉ số thuộc danh sách mới.

Ngược lại, có chỉ số cũng không bảo đảm chi phí truy cập luôn giống nhau: `ArrayList` và `LinkedList` đều triển khai `List`, nhưng cách tìm phần tử tại chỉ số khác nhau.

## 5. Thứ tự sắp xếp: cần một quy tắc so sánh

Một dãy được sắp xếp khi các phần tử tuân theo một quan hệ so sánh đã chọn. Quy tắc đó có thể là:

- Thứ tự tự nhiên của phần tử qua `Comparable`.
- Một `Comparator` do chương trình cung cấp.
- Nhiều tiêu chí ghép lại, chẳng hạn độ ưu tiên rồi đến mã tác vụ.

“Sắp xếp tăng dần” chỉ rõ ý nghĩa khi biết tăng theo thuộc tính nào.

Với số nguyên, thứ tự tự nhiên thường được hiểu là thứ tự giá trị số. Với `String`, thứ tự tự nhiên là thứ tự từ điển theo quy tắc so sánh của `String`, không mặc nhiên là thứ tự ngôn ngữ tự nhiên theo từng địa phương. Nếu nghiệp vụ cần thứ tự theo ngôn ngữ, phải chọn công cụ và quy tắc so sánh tương ứng.

### List không tự duy trì thứ tự sắp xếp

~~~java
// Đoạn mã trong một phương thức; cần import java.util.Comparator.
List<Integer> numbers = new ArrayList<>(List.of(30, 10, 20));
numbers.sort(Comparator.naturalOrder());

System.out.println(numbers); // [10, 20, 30]

numbers.add(5);
System.out.println(numbers); // [10, 20, 30, 5]
~~~

Sau `sort`, danh sách thỏa quy tắc tăng dần. Nhưng `List` không tự sắp lại mỗi khi thêm phần tử. Sau `add(5)`, kết quả không còn tăng dần.

Cần phân biệt “đã được sắp xếp ở bước này” với “cấu trúc dữ liệu luôn duy trì bất biến sắp xếp”.

### TreeSet duy trì quy tắc sắp xếp

~~~java
// Cần import java.util.Set và java.util.TreeSet.
Set<Integer> numbers = new TreeSet<>();
numbers.add(30);
numbers.add(10);
numbers.add(20);
numbers.add(5);

System.out.println(numbers); // [5, 10, 20, 30]
~~~

`TreeSet` đặt các phần tử theo quan hệ so sánh khi quản lý dữ liệu. Thêm `5` không có nghĩa nó sẽ đứng cuối thứ tự duyệt.

Khai báo biến bằng `Set<Integer>` không xóa hành vi của đối tượng `TreeSet`, nhưng làm mất khả năng gọi trực tiếp một số API riêng của các interface tập hợp sắp xếp qua biến đó. Nếu phương thức cần hợp đồng sắp xếp, nên biểu đạt điều đó bằng kiểu tham số phù hợp như `SortedSet` hoặc `NavigableSet`, thay vì chỉ dựa vào giả định ngầm.

Không tự ý sửa thuộc tính dùng để so sánh khi đối tượng đang nằm trong `TreeSet`. Thay đổi bên trong phần tử không khiến cấu trúc tự tìm lại vị trí đúng. Khi cần đổi khóa sắp xếp, phải thiết kế thao tác cập nhật phù hợp, chẳng hạn lấy ra trước rồi thêm lại sau khi thay đổi.

## 6. Queue: thứ tự lấy chưa chắc là thứ tự duyệt

Với hàng đợi FIFO, thường có thể hình dung phần tử được thêm trước sẽ được lấy trước. Nhưng `PriorityQueue` chọn phần tử ở đầu theo độ ưu tiên.

~~~java
// Đoạn mã trong một phương thức; cần import Queue và PriorityQueue.
Queue<Integer> queue = new PriorityQueue<>(List.of(40, 10, 30, 20));
~~~

Với thứ tự tự nhiên của số nguyên:

- Liên tục gọi `poll()` sẽ lấy `10, 20, 30, 40`.
- For-each trên `queue` không được cam kết trả về trình tự `10, 20, 30, 40`.
- In trực tiếp `queue` không phải cách chứng minh toàn bộ các phần tử đã được sắp xếp.

`PriorityQueue` bảo đảm về phần tử ở đầu theo quy tắc của nó, không bảo đảm iterator là một danh sách ưu tiên đã sắp xếp hoàn chỉnh.

Muốn xử lý theo độ ưu tiên, dùng thao tác lấy của hàng đợi. Muốn tạo một bản hiển thị đã sắp xếp mà không tiêu thụ hàng đợi gốc, có thể sao chép dữ liệu rồi sắp xếp bản sao theo quy tắc mong muốn.

Nếu nhiều phần tử có cùng mức ưu tiên, `PriorityQueue` không tự bảo đảm xử lý chúng theo thứ tự chèn. Nếu nghiệp vụ yêu cầu “cùng độ ưu tiên thì ai đến trước được xử lý trước”, cần một tiêu chí phụ, chẳng hạn số thứ tự được cấp lúc tiếp nhận, và comparator phải xét tiêu chí đó.

## 7. So sánh các cấu trúc thường gặp

Bảng dưới xét các thao tác thông thường trong một luồng; không giả định có chỉnh sửa đồng thời.

| Cấu trúc | Điều quyết định trình tự hiện tại | Cam kết duyệt đáng chú ý | Có API chỉ số không? | Tự duy trì sắp xếp theo so sánh không? |
| --- | --- | --- | --- | --- |
| `ArrayList` | Các vị trí sau khi thêm, chèn, xóa, thay thế hoặc sắp xếp | Theo thứ tự vị trí danh sách | Có | Không |
| `LinkedList` khi dùng như `List` | Các vị trí của danh sách | Theo thứ tự vị trí danh sách | Có | Không |
| `HashSet` | Cấu trúc nội bộ; không có cam kết thứ tự duyệt | Không dựa vào một trình tự cụ thể | Không | Không |
| `LinkedHashSet` | Thứ tự chèn với các thao tác `add` thông thường | Theo thứ tự được giữ trong tập hợp | Không | Không |
| `TreeSet` | Quan hệ so sánh tự nhiên hoặc comparator | Theo thứ tự so sánh tăng dần | Không | Có |
| `ArrayDeque` | Các thao tác thêm/xóa ở đầu và cuối | Iterator thông thường đi từ đầu đến cuối | Không | Không |
| `PriorityQueue` | Quy tắc ưu tiên cho phần tử ở đầu | Iterator không cam kết theo thứ tự ưu tiên | Không | Không có cam kết sắp toàn bộ thứ tự duyệt; lấy đầu theo ưu tiên |

Một cấu trúc có thể có đầu và cuối mà không có chỉ số. Nó cũng có thể có phần tử nhỏ nhất ở đầu mà không có thứ tự duyệt đã sắp xếp.

## 8. Phần tử bằng nhau theo so sánh và sắp xếp ổn định

Khi comparator trả `0`, hai phần tử được xem là ngang nhau **theo tiêu chí so sánh đó**. Điều này không nhất thiết có nghĩa hai đối tượng `equals` nhau.

Giả sử các tác vụ ban đầu là:

~~~text
C:2, D:1, A:2, B:1
~~~

Mỗi cặp có dạng `mã:độ_ưu_tiên`. Comparator chỉ xét độ ưu tiên, từ nhỏ đến lớn.

### Stable sort giữ thứ tự tương đối trước khi sort

`List.sort` có tính ổn định: các phần tử được comparator xem là bằng nhau giữ thứ tự tương đối trước khi sắp xếp.

Kết quả:

~~~text
D:1, B:1, C:2, A:2
~~~

`D` vẫn đứng trước `B` trong nhóm ưu tiên `1`; `C` vẫn đứng trước `A` trong nhóm ưu tiên `2`.

“Ổn định” ở đây nói đến thứ tự của dãy ngay trước lần sort, không phải lịch sử chèn ban đầu của toàn bộ vòng đời dữ liệu. Nếu dãy đã bị đảo hoặc chỉnh sửa, thứ tự được bảo toàn trong các nhóm bằng nhau là thứ tự sau những thao tác đó.

Stable sort cũng không tự làm dữ liệu đầu vào có thứ tự xác định. Nếu danh sách được lấy từ nguồn không cam kết thứ tự, các phần tử cùng mức ưu tiên có thể xuất hiện theo thứ tự khác nhau ở các lần chạy; stable sort chỉ giữ thứ tự đầu vào mà nó nhận được.

### Tiêu chí phụ tạo ra quy tắc rõ ràng hơn

Nếu muốn cùng độ ưu tiên thì sắp theo mã tác vụ:

~~~java
// Job là kiểu có các phương thức priority() và id().
Comparator<Job> order = Comparator.comparingInt(Job::priority)
        .thenComparing(Job::id);
~~~

Kết quả cho dữ liệu trên là:

~~~text
B:1, D:1, A:2, C:2
~~~

Đây không phải stable sort bị thay đổi hành vi. Comparator đã phân biệt thêm các phần tử mà trước đây nó xem là bằng nhau.

Đối với phân trang hoặc kết quả cần tái lập, nên chọn tiêu chí phụ đủ để xác định thứ tự theo yêu cầu nghiệp vụ. Chỉ sắp theo một thuộc tính có nhiều giá trị trùng thường chưa đủ để có ranh giới trang ổn định.

### TreeSet dùng so sánh để quyết định trùng phần tử

Với cùng bốn tác vụ và comparator chỉ xét độ ưu tiên, `TreeSet` chỉ giữ một phần tử cho mỗi mức ưu tiên. Theo thứ tự thêm `C:2, D:1, A:2, B:1`, kết quả là:

~~~text
[D:1, C:2]
~~~

`A:2` và `B:1` không được thêm như phần tử độc lập vì comparator trả `0` khi so với phần tử đã có ở cùng mức ưu tiên.

Nếu các tác vụ có mã khác nhau phải được xem là khác nhau, comparator chỉ xét ưu tiên là không phù hợp cho `TreeSet`. Với kiểu `Job` trong chương trình dưới đây, `equals` còn xét mã; comparator chỉ xét ưu tiên không nhất quán với `equals`, nên không đáp ứng đầy đủ hợp đồng chung của `Set`.

Có thể:

- Dùng `List` rồi sort nếu cần giữ tất cả các tác vụ, kể cả những tác vụ ngang nhau theo tiêu chí.
- Hoặc dùng comparator có tiêu chí phụ phù hợp với định nghĩa duy nhất của dữ liệu khi thật sự cần `TreeSet`.

Không chuyển từ “danh sách cần được sắp xếp” sang `TreeSet` chỉ vì muốn các phần tử có thứ tự; thao tác đó có thể làm mất dữ liệu theo quy tắc trùng của tập hợp.

## 9. Từ Java 21: sequenced không có nghĩa là indexed hay sorted

Java 21 bổ sung các interface như `SequencedCollection` và `SequencedSet` để biểu đạt tập hợp có thứ tự duyệt xác định, cùng các thao tác liên quan đến đầu, cuối và góc nhìn đảo thứ tự.

Cần giữ ba ranh giới:

1. **Sequenced không đồng nghĩa sorted.** Một dãy `B, A, C` có thứ tự duyệt xác định nhưng không nhất thiết thỏa một comparator.
2. **Sequenced không đồng nghĩa indexed.** `LinkedHashSet` có thể có đầu và cuối nhưng không trở thành `List` có `get(index)`.
3. **Có API chung không có nghĩa mọi thao tác thay đổi đều được hỗ trợ.** Một tập hợp có quy tắc sắp xếp phải bảo toàn quy tắc đó, không thể mặc nhiên cho chèn tùy ý vào đầu hoặc cuối.

Các API mới còn cho phép định vị lại phần tử trong một số cấu trúc. Chẳng hạn, `LinkedHashSet` từ Java 21 có `addFirst` và `addLast` để đặt phần tử vào đầu hoặc cuối. Vì vậy, khi phân tích thứ tự của một đối tượng thực tế, phải xét các thao tác đã được gọi; không chỉ nhìn tên lớp rồi giả định mọi thay đổi đều đơn thuần nối theo thời gian chèn.

`reversed()` cung cấp một góc nhìn đảo thứ tự, không phải cách truy xuất “lịch sử thêm theo thời gian ngược”, và không phải lệnh tự sắp xếp.

Chương trình ở phần tiếp theo chỉ dùng API có từ Java 17 để có thể chạy trên Java 17 trở lên. Những phân biệt giữa bốn khái niệm vẫn áp dụng khi dùng Java 21.

## 10. Chương trình hoàn chỉnh

Lưu thành **OrderDimensionsDemo.java**:

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.Deque;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.PriorityQueue;
import java.util.Queue;
import java.util.Set;
import java.util.TreeSet;

public class OrderDimensionsDemo {
    record Job(String id, int priority) {
        @Override
        public String toString() {
            return id + ":" + priority;
        }
    }

    public static void main(String[] args) {
        List<Integer> positions = new ArrayList<>(List.of(30, 10, 20));
        System.out.println("List initial = " + positions);
        System.out.println("Index 1 before insert = " + positions.get(1));
        positions.add(1, 99);
        System.out.println("List after insert = " + positions);
        System.out.println("Index 1 after insert = " + positions.get(1));
        System.out.println("Old value 10 now has index = " + positions.indexOf(10));

        LinkedHashSet<String> insertion = new LinkedHashSet<>();
        insertion.add("B");
        insertion.add("A");
        insertion.add("C");
        System.out.println("Adding existing A = " + insertion.add("A"));
        System.out.println("LinkedHashSet = " + insertion);
        insertion.remove("A");
        insertion.add("A");
        System.out.println("Remove then add A = " + insertion);

        Set<Integer> sortedSet = new TreeSet<>(List.of(30, 10, 20));
        System.out.println("TreeSet = " + sortedSet);

        Set<Integer> hashSet = new HashSet<>(List.of(30, 10, 20));
        List<Integer> sortedCopy = new ArrayList<>(hashSet);
        sortedCopy.sort(Comparator.naturalOrder());
        System.out.println("HashSet sorted copy = " + sortedCopy);

        Deque<String> ends = new ArrayDeque<>();
        ends.addLast("B");
        ends.addLast("C");
        ends.addFirst("A");
        System.out.println("Deque encounter order = " + ends);

        Queue<Integer> priorityQueue =
                new PriorityQueue<>(List.of(40, 10, 30, 20));
        List<Integer> polled = new ArrayList<>();
        Integer value;
        while ((value = priorityQueue.poll()) != null) {
            polled.add(value);
        }
        System.out.println("PriorityQueue poll order = " + polled);

        List<Job> jobs = List.of(
                new Job("C", 2),
                new Job("D", 1),
                new Job("A", 2),
                new Job("B", 1)
        );
        Comparator<Job> byPriority = Comparator.comparingInt(Job::priority);

        List<Job> stable = new ArrayList<>(jobs);
        stable.sort(byPriority);
        System.out.println("Stable sort = " + stable);

        Comparator<Job> byPriorityThenId = byPriority.thenComparing(Job::id);
        List<Job> explicit = new ArrayList<>(jobs);
        explicit.sort(byPriorityThenId);
        System.out.println("Sort with tie-breaker = " + explicit);

        Set<Job> priorityOnly = new TreeSet<>(byPriority);
        priorityOnly.addAll(jobs);
        System.out.println("TreeSet priority only = " + priorityOnly);

        Set<Job> priorityAndId = new TreeSet<>(byPriorityThenId);
        priorityAndId.addAll(jobs);
        System.out.println("TreeSet priority then id = " + priorityAndId);
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~shell
javac --release 17 -encoding UTF-8 OrderDimensionsDemo.java
java OrderDimensionsDemo
~~~

Stdout:

~~~text
List initial = [30, 10, 20]
Index 1 before insert = 10
List after insert = [30, 99, 10, 20]
Index 1 after insert = 99
Old value 10 now has index = 2
Adding existing A = false
LinkedHashSet = [B, A, C]
Remove then add A = [B, C, A]
TreeSet = [10, 20, 30]
HashSet sorted copy = [10, 20, 30]
Deque encounter order = [A, B, C]
PriorityQueue poll order = [10, 20, 30, 40]
Stable sort = [D:1, B:1, C:2, A:2]
Sort with tie-breaker = [B:1, D:1, A:2, C:2]
TreeSet priority only = [D:1, C:2]
TreeSet priority then id = [B:1, D:1, A:2, C:2]
~~~

### Vì sao chương trình cho kết quả này?

- Danh sách ban đầu giữ dãy `30, 10, 20`; chèn `99` vào chỉ số `1` làm giá trị `10` chuyển sang chỉ số `2`.
- `LinkedHashSet.add("A")` không thay đổi vị trí khi `A` đã tồn tại. Xóa rồi thêm lại đưa `A` xuống cuối.
- `TreeSet` duyệt số theo thứ tự tự nhiên, dù thứ tự thêm không tăng dần.
- Dòng `HashSet sorted copy` in **bản sao đã được sort**, không in thứ tự duyệt của `HashSet`. Vì vậy stdout không dựa vào một trình tự mà `HashSet` không cam kết.
- `ArrayDeque` đặt `A` ở đầu dù `A` được thêm sau `B` và `C`.
- Dòng `PriorityQueue poll order` được tạo bằng cách lấy lần lượt qua `poll()`, không bằng iterator.
- `List.sort` giữ cả bốn tác vụ; comparator chỉ ưu tiên cho kết quả ổn định theo thứ tự trước khi sort.
- `TreeSet` với comparator chỉ ưu tiên gộp các tác vụ có cùng mức ưu tiên thành một vị trí. Comparator xét thêm mã phân biệt đủ bốn tác vụ trong ví dụ.

Trong chương trình, `Job` là một record bất biến. `toString()` được viết lại chỉ để kết quả hiển thị gọn dạng `mã:độ_ưu_tiên`; nó không quyết định thứ tự hay tính duy nhất.

## 11. Áp dụng theo nhu cầu thực tế

| Nhu cầu | Cách chọn hoặc xử lý |
| --- | --- |
| Giữ một dãy và cho truy cập phần tử ở vị trí cụ thể | Dùng `List`; xác định rõ những thao tác có thể đổi vị trí. |
| Loại phần tử trùng nhưng giữ thứ tự xuất hiện đầu tiên qua các lần thêm thông thường | Dùng `LinkedHashSet` với `add` thông thường; kiểm tra hành vi khi xóa rồi thêm lại. |
| Chỉ cần kiểm tra thành viên, không có yêu cầu về trình tự | Có thể dùng `HashSet`; kiểm thử theo nội dung, không theo chuỗi hiển thị. |
| Cần duyệt tập hợp duy nhất theo thứ tự so sánh | Cân nhắc `TreeSet`, sau khi xác định comparator và ý nghĩa “trùng”. |
| Cần tất cả phần tử, có thể trùng, được hiển thị theo comparator | Dùng danh sách hoặc bản sao danh sách rồi sort. |
| Cần xử lý tác vụ ưu tiên nhất tiếp theo | Dùng `PriorityQueue` và các thao tác lấy đầu; thêm tiêu chí phụ nếu cần FIFO trong cùng ưu tiên. |
| Cần kiểm thử, xuất dữ liệu hoặc phân trang theo thứ tự tái lập | Quy định một thứ tự rõ ràng và tiêu chí xử lý hòa; không dựa vào thứ tự tình cờ của nguồn. |

### Các thao tác giống nhau về kết quả tạm thời nhưng khác ý nghĩa

| Thao tác | Điều thực sự xảy ra |
| --- | --- |
| `new ArrayList<>(source)` | Tạo dãy từ trình tự nguồn cung cấp lúc sao chép; không tự sort. |
| `list.sort(comparator)` | Thay thứ tự của danh sách có thể sửa theo comparator. |
| `Collections.reverse(list)` | Đảo dãy hiện tại; không tự chọn quy tắc so sánh. |
| `deque.addFirst(value)` | Đặt phần tử ở đầu; không có ý nghĩa sắp xếp theo giá trị. |
| `stream.sorted(comparator)` | Tạo bước sắp xếp trong pipeline; không tự sắp xếp lại collection nguồn. |

Với stream song song, `forEach` không bảo đảm hành động quan sát được diễn ra theo encounter order. Nếu cần hành động tuân theo thứ tự duyệt đã xác định của pipeline, xem xét `forEachOrdered`. Tuy nhiên, `forEachOrdered` không tạo lại thứ tự chèn đã mất từ một nguồn không cam kết thứ tự; muốn một quy tắc sắp xếp cụ thể vẫn cần định nghĩa quy tắc đó.

Nếu đang cần một dãy mới được sắp xếp mà không đổi nguồn, hãy tạo bản sao phù hợp rồi sort, hoặc dùng pipeline tạo kết quả mới. Không gọi sort trực tiếp lên một danh sách không hỗ trợ thay đổi rồi kỳ vọng mọi `List` đều thực hiện được.

## 12. Lỗi thường gặp và cách tự kiểm tra

| Hiểu nhầm | Điều cần sửa |
| --- | --- |
| “Thêm `30, 10, 20` thì tập hợp nào cũng duyệt đúng thứ tự đó.” | Chỉ tin thứ tự chèn khi hợp đồng và thao tác cụ thể bảo đảm. |
| “`HashSet` đã in tăng dần nên có thể dựa vào kết quả đó.” | Một kết quả quan sát được không phải cam kết sắp xếp. |
| “Có thứ tự duyệt thì chắc gọi được `get(2)`.” | API chỉ số thuộc các hợp đồng như `List`, không thuộc mọi tập hợp có thứ tự. |
| “Chỉ số là mã cố định của phần tử.” | Chèn, xóa, thay thế hoặc sort có thể đổi phần tử tại chỉ số. |
| “List đã sort thì thêm gì vào cũng tự đứng đúng chỗ.” | `List` không tự duy trì bất biến sắp xếp. |
| “Duyệt PriorityQueue là lấy các phần tử theo ưu tiên.” | Hợp đồng lấy đầu và hợp đồng iterator khác nhau. |
| “Stable sort luôn cho kết quả giống nhau giữa các lần chạy.” | Nó giữ thứ tự tương đối của đầu vào với các phần tử so sánh bằng nhau; đầu vào có thể không xác định. |
| “TreeSet là List đã sort và loại các đối tượng equals nhau.” | `TreeSet` dùng so sánh để xác định trùng, nên comparator phải phù hợp với dữ liệu và hợp đồng `Set`. |

Hãy tự giải các tình huống sau:

1. Thêm `C`, `A`, `B` vào `LinkedHashSet`; thêm lại `A`; sau đó xóa `C` rồi thêm `C` một lần nữa. Viết thứ tự duyệt sau từng bước.
2. Cho danh sách `[8, 3, 5]`. Chèn `1` vào chỉ số `0`, rồi sort tăng dần. Giá trị ở chỉ số `1` thay đổi như thế nào?
3. Cần in các mã không trùng theo thứ tự xuất hiện đầu tiên trong đầu vào. Vì sao `HashSet` hoặc `TreeSet` có thể không đáp ứng đúng yêu cầu?
4. Cần xử lý các tác vụ theo ưu tiên, cùng ưu tiên thì theo số thứ tự tiếp nhận. Comparator cần xét những thuộc tính nào?
5. Từ một nguồn không cam kết thứ tự, sort danh sách người dùng chỉ theo tuổi. Vì sao những người cùng tuổi có thể đổi vị trí giữa các lần xuất dữ liệu?
6. Cần giữ mọi bản ghi nhưng sắp theo ngày tạo. Điều gì có thể xảy ra nếu dùng `TreeSet` với comparator chỉ xét ngày tạo?

Với mỗi tình huống, hãy nêu riêng: nguồn có cam kết thứ tự chèn không, iterator duyệt theo quy tắc nào, có API chỉ số không, và quy tắc so sánh có làm hai phần tử khác nhau được xem là bằng nhau không.
