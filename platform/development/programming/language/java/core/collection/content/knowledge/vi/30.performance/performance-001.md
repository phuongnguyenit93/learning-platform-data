# So sánh độ phức tạp truy cập, tìm kiếm, thêm, xóa và duyệt

## 1. Bắt đầu từ thao tác cụ thể

Một cấu trúc dữ liệu không có một “độ phức tạp chung”. Cần hỏi: đang gọi phương thức nào, đã biết gì về phần tử cần xử lý, và thao tác đó lặp bao nhiêu lần?

Ví dụ, với một danh sách:

- Biết chỉ số `i`: lấy phần tử bằng `get(i)`.
- Biết giá trị `x`: tìm bằng `contains(x)` hoặc `indexOf(x)`.
- Biết vị trí hiện tại qua iterator: có thể xóa phần tử vừa đọc.
- Chỉ biết “xóa phần tử có giá trị x”: trước hết phải tìm ra nó.

Hai yêu cầu cuối có thể cùng tạo một kết quả nhưng chi phí khác nhau. Bài này so sánh các cấu trúc phổ biến trong Java 17: `ArrayList`, `LinkedList`, `ArrayDeque`, `PriorityQueue`, các tập hợp và các ánh xạ dựa trên bảng băm hoặc cây. Các cấu trúc đồng thời và phép toán hàng loạt cần mô hình riêng.

## 2. Đọc ký hiệu và giả định

Gọi:

- `n`: số phần tử đang có; với `Map`, là số cặp khóa–giá trị.
- `c`: dung lượng bảng băm, tức số ngăn chứa (bucket).
- `i`: chỉ số hợp lệ trong danh sách.
- Một lần đọc/ghi tham chiếu, so sánh, `equals` và `hashCode` được tạm coi là O(1). Phần 7 giải thích khi giả định này không phù hợp.

| Ký hiệu | Ý nghĩa tăng trưởng khi dữ liệu lớn |
| --- | --- |
| O(1) | Số bước không tăng theo n |
| O(log n) | Mỗi bước loại bỏ một phần đáng kể miền tìm kiếm |
| O(n) | Có thể phải xử lý số phần tử tỉ lệ với n |
| O(n log n) | Thường gặp khi sắp xếp hoặc lấy lần lượt n phần tử từ heap |
| O(n²) | Thường xuất hiện khi lặp n lần một thao tác tuyến tính |

Big O mô tả tốc độ tăng trưởng và bỏ qua hệ số hằng. O(1) vẫn có thể gồm nhiều bước; O(n) có thể rất nhanh khi n nhỏ. Dùng log n trong bảng là cách viết thông dụng cho n đủ lớn; không lấy log 0 để diễn giải một collection rỗng.

Phân biệt ba cách đánh giá:

1. **Trường hợp xấu nhất:** cận chi phí của một thao tác khi gặp đầu vào bất lợi.
2. **Trung bình/kỳ vọng:** cần giả định về dữ liệu, chẳng hạn mã băm phân bố tốt.
3. **Khấu hao (amortized):** chia tổng chi phí của một chuỗi thao tác cho số thao tác; không phải lấy trung bình xác suất của đầu vào.

Chẳng hạn, thêm cuối `ArrayList` có chi phí khấu hao O(1). Một lần thêm khi mảng đầy vẫn có thể cần O(n) để chuyển phần tử sang mảng lớn hơn. Ngược lại, O(1) kỳ vọng của tra cứu bảng băm dựa vào chất lượng phân bố khóa. Hai nhận định này có điều kiện khác nhau.

## 3. Danh sách: chỉ số, giá trị và vị trí iterator

Các ô không ghi “khấu hao” dưới đây là cận trường hợp xấu nhất cho thao tác đơn, với giả định ở phần 2.

| Thao tác | ArrayList | LinkedList |
| --- | --- | --- |
| `get(i)`, `set(i, x)` | O(1) | O(n); đi từ đầu hoặc cuối gần hơn |
| `contains(x)`, `indexOf(x)` | O(n) | O(n) |
| Thêm cuối bằng `add(x)` | O(1) khấu hao; một lần tăng mảng O(n) | O(1) |
| Thêm đầu bằng `add(0, x)` | O(n) | O(1) |
| Thêm vào vị trí bên trong bằng `add(i, x)` | O(n) | O(n), gồm bước tìm vị trí |
| Xóa cuối bằng `remove(size() - 1)` | O(1) | O(1) |
| Xóa đầu bằng `remove(0)` | O(n) | O(1) |
| Xóa tại vị trí bên trong bằng `remove(i)` | O(n) | O(n), gồm bước tìm vị trí |
| Xóa theo giá trị bằng `remove(Object)` | O(n) | O(n) |
| Duyệt đủ n phần tử bằng iterator | O(n) | O(n) |

### 3.1. Vì sao ArrayList truy cập nhanh nhưng chèn giữa chậm?

`ArrayList` giữ phần tử trong mảng tham chiếu. Biết chỉ số là biết ngay ô mảng cần đọc. Ngược lại, chèn vào vị trí `i` phải dịch các phần tử phía sau để tạo chỗ; xóa tại `i` phải lấp khoảng trống.

Nếu bỏ qua tăng dung lượng, số phần tử cần dịch gần bằng:

- Thêm tại `i`: `n - i`.
- Xóa tại `i`: `n - i - 1`.

Vì vậy, xóa phần tử cuối khác rõ xóa phần tử đầu dù cùng gọi `remove(int)`. `set(i, x)` chỉ thay một tham chiếu, không phải thao tác chèn. Chính sách tăng dung lượng cụ thể không phải điều kiện mà mã ứng dụng nên dựa vào. [Tài liệu ArrayList của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html)

### 3.2. “LinkedList thêm/xóa O(1)” thiếu điều kiện nào?

`LinkedList` là danh sách liên kết đôi. Sau khi đã đứng tại nút cần sửa, việc nối hoặc tháo liên kết chỉ cần O(1). Nhưng `add(i, x)` hay `remove(i)` phải tìm đến nút trước.

Với `get(i)`, số bước di chuyển xấp xỉ `min(i, n - 1 - i)`; cộng chi phí xử lý cố định ta có O(1 + min(i, n - 1 - i)). Truy cập sát đầu/cuối rẻ, truy cập giữa có thể O(n).

Một `ListIterator` của `LinkedList` đã ở đúng vị trí có thể `add(x)` hoặc `remove()` hợp lệ với O(1). Nếu tạo mới `listIterator(i)` trước mỗi lần sửa, chi phí tìm vị trí lại xuất hiện. `remove()` của iterator chỉ được gọi theo trạng thái hợp lệ, chẳng hạn sau `next()`, và không được gọi hai lần liên tiếp nếu chưa di chuyển lại. [Tài liệu LinkedList của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html)

### 3.3. Cùng một vòng lặp, tổng chi phí khác nhau

Đoạn sau là phương thức minh họa, cần đặt trong một lớp Java:

~~~java
static long sumByIndex(java.util.List<Integer> values) {
    long sum = 0;
    for (int i = 0; i < values.size(); i++) {
        sum += values.get(i);
    }
    return sum;
}
~~~

Với `ArrayList`, n lần `get(i)` O(1) cho tổng O(n). Với `LinkedList`, tổng số bước đi qua các nút tăng theo n², dù mỗi lần truy cập chọn đầu gần hơn.

Duyệt tuần tự bằng iterator tránh việc tìm lại vị trí từ đầu hoặc cuối:

~~~java
static long sumSequentially(java.util.List<Integer> values) {
    long sum = 0;
    for (int value : values) {
        sum += value;
    }
    return sum;
}
~~~

Với hai triển khai trên, phương thức thứ hai là O(n), giả sử mỗi phép cộng và đọc một phần tử có chi phí hằng. Việc đổi kiểu biến từ `LinkedList` thành giao diện `List` không làm đổi cấu trúc thực tế hay chi phí `get(i)`.

## 4. Hàng đợi hai đầu và hàng đợi ưu tiên

Hai cấu trúc này giải quyết hai yêu cầu khác nhau:

- `ArrayDeque`: lấy/thêm ở đầu hoặc cuối theo vị trí trong dãy.
- `PriorityQueue`: lấy phần tử có mức ưu tiên cao nhất theo quy tắc so sánh; với thứ tự tự nhiên tăng dần, đó là phần tử nhỏ nhất.

| Thao tác | ArrayDeque | PriorityQueue |
| --- | --- | --- |
| Đọc đầu bằng `peek()` | O(1) | O(1) |
| Đọc cuối bằng `peekLast()` | O(1) | Không có thao tác tương đương |
| Thêm đầu/cuối | O(1) khấu hao | Không hỗ trợ ngữ nghĩa hai đầu |
| Thêm bằng `offer(x)` | O(1) khấu hao, thêm cuối | O(log n) cho điều chỉnh heap; xem lưu ý tăng mảng |
| Lấy và xóa đầu bằng `poll()` | O(1) | O(log n) |
| Tìm bằng `contains(x)` | O(n) | O(n) |
| Xóa giá trị bằng `remove(x)` | O(n) | O(n) |
| Duyệt toàn bộ bằng iterator | O(n), theo thứ tự dãy | O(n), không bảo đảm thứ tự ưu tiên |
| Truy cập bằng chỉ số tùy ý | Không có `get(i)` | Không có `get(i)` |

`ArrayDeque` dùng mảng vòng: tiến đầu/cuối thường chỉ cập nhật vị trí. Khi thêm làm đầy mảng, một lần tăng dung lượng có thể tốn O(n). `iterator.remove()` của nó cũng có thể O(n); không áp dụng kết luận xóa tại iterator của `LinkedList` cho mọi collection. [Tài liệu ArrayDeque của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html)

`PriorityQueue` dùng heap. Đường đi từ lá tới gốc hoặc ngược lại dài O(log n), nhưng heap không bảo đảm toàn bộ mảng đã được sắp xếp. Do đó tìm một giá trị bất kỳ vẫn phải quét; `peek()` nhanh không kéo theo `contains(x)` nhanh. Gọi `poll()` đến hết n phần tử có tổng chi phí O(n log n), đồng thời làm rỗng hàng đợi. [Tài liệu PriorityQueue của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html)

**Lưu ý về một lần offer:** ghi chú API nêu O(log n) cho thao tác thêm vào heap. Nếu tính cả sao chép mảng nền khi tăng dung lượng, một lần `offer` trong OpenJDK có thể O(n); O(log n) là cận khấu hao khi cộng chi phí tăng mảng vào chuỗi lần thêm. Đây là phân tích từ triển khai, không phải lời hứa về thời gian thực của mỗi lời gọi. [Mã nguồn PriorityQueue trong OpenJDK 17](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/PriorityQueue.java)

## 5. Set: kiểm tra thành viên và thứ tự duyệt

`Set` không cung cấp truy cập vị trí như `get(i)`. “Truy cập một phần tử” cần được chuyển thành yêu cầu rõ ràng: kiểm tra thành viên, lấy phần tử đầu theo thứ tự, hay tìm phần tử gần một mốc.

| Triển khai | `contains(x)` | `add(x)` | `remove(x)` | Duyệt toàn bộ | Thứ tự |
| --- | --- | --- | --- | --- | --- |
| `HashSet` | O(1) kỳ vọng | O(1) kỳ vọng, khấu hao | O(1) kỳ vọng | O(n + c) | Không bảo đảm |
| `LinkedHashSet` | O(1) kỳ vọng | O(1) kỳ vọng, khấu hao | O(1) kỳ vọng | O(n) | Thứ tự thêm |
| `TreeSet` | O(log n) | O(log n) | O(log n) | O(n) | Theo comparator/thứ tự tự nhiên |

Bảng băm cần mã băm phân bố tốt; thêm có thể kích hoạt tăng dung lượng. Với cây, các cận O(log n) là cận trường hợp xấu nhất của thao tác cơ bản dưới giả định so sánh O(1).

`HashSet` phải đi qua cả các ngăn trong bảng nền khi duyệt. Nếu đã cấp dung lượng rất lớn nhưng chỉ giữ ít phần tử, không thể bỏ qua c. Khi c cùng bậc n, O(n + c) rút gọn thành O(n). [Tài liệu HashSet của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html)

`LinkedHashSet` duy trì liên kết qua các phần tử đang có, nên chi phí duyệt không phụ thuộc dung lượng bảng. Đổi lại, nó cần thêm bộ nhớ và công việc duy trì liên kết. [Tài liệu LinkedHashSet của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html)

`TreeSet` duy trì thứ tự bằng cây. Nó phù hợp khi cần các phép tìm lân cận như `floor`, `ceiling` hoặc xử lý theo miền giá trị. Comparator quyết định hai phần tử có được xem là cùng vị trí trong cây hay không; thiết kế comparator thiếu nhất quán với `equals` có thể làm sai kỳ vọng của người dùng về tính duy nhất. [Tài liệu TreeSet của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html)

## 6. Map: truy cập theo khóa khác tìm theo giá trị

`map.get(k)` là tra cứu bằng khóa, không phải lấy phần tử ở chỉ số k. Kể cả khi khóa là `Integer`, `get(5)` vẫn có nghĩa “khóa bằng 5”.

| Thao tác | HashMap | LinkedHashMap | TreeMap |
| --- | --- | --- | --- |
| `get(k)`, `containsKey(k)` | O(1) kỳ vọng | O(1) kỳ vọng | O(log n) |
| `put(k, v)` | O(1) kỳ vọng, khấu hao khi thêm khóa mới | O(1) kỳ vọng, khấu hao khi thêm khóa mới | O(log n) |
| `remove(k)` | O(1) kỳ vọng | O(1) kỳ vọng | O(log n) |
| `containsValue(v)` | O(n + c) trường hợp xấu nhất | O(n) | O(n) |
| Duyệt `entrySet()` đầy đủ | O(n + c) | O(n) | O(n) |
| Thứ tự duyệt | Không bảo đảm | Thường là thứ tự thêm; có chế độ thứ tự truy cập | Thứ tự khóa |

`HashMap` lập chỉ mục bằng khóa, nên tra giá trị không được hưởng cùng đường đi. Muốn truy vấn ngược theo giá trị thường xuyên, cần cân nhắc chỉ mục bổ sung và chi phí đồng bộ chỉ mục đó. Trong cách dùng thông thường c = O(n), cận của `containsValue` hay duyệt bảng băm được viết ngắn là O(n). [Tài liệu HashMap của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html), [triển khai containsValue trong OpenJDK 17](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/HashMap.java)

`LinkedHashMap` nối các mục đang có để duyệt O(n). Với chế độ thứ tự truy cập, một lần `get(k)` thành công có thể cập nhật vị trí mục trong dãy; vẫn không có việc sắp xếp toàn bộ map ở mỗi lần đọc. [Tài liệu LinkedHashMap của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html)

`TreeMap` tổ chức cây theo khóa. Nó bảo đảm O(log n) cho tra cứu, thêm, xóa bằng khóa, nhưng không tạo chỉ mục thứ hai theo giá trị. Việc đã biết khóa gần một giá trị nào đó cũng không có nghĩa biết chỉ số thứ hạng của khóa trong O(1). [Tài liệu TreeMap của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html)

## 7. Những chi phí ẩn sau một ô O(1)

### 7.1. Va chạm băm và tăng dung lượng

Nhiều khóa có cùng mã băm có thể làm thao tác chậm hơn O(1). Java có cơ chế giảm tác động của va chạm trong một số tình huống, nhưng không nên suy ra “mọi thao tác HashMap luôn O(log n) trong trường hợp xấu nhất” chỉ từ việc có ngăn dạng cây. API công bố điều kiện phân bố băm tốt cho chi phí hằng của thao tác cơ bản.

Khi tăng bảng, phải cấp bảng mới và phân phối lại các mục; chi phí còn phụ thuộc dung lượng bảng. Trong mô hình dung lượng tỉ lệ với số mục, một đợt tăng bảng là tuyến tính theo n. Cấp sẵn dung lượng hợp lý có thể giảm số lần tăng, nhưng cấp quá dư lại tốn bộ nhớ và làm duyệt `HashMap`/`HashSet` đắt hơn.

Khóa trong bảng băm cần giữ ổn định các thông tin dùng cho `hashCode` và `equals` khi đang lưu. Thay đổi chúng có thể khiến tra cứu không tìm được mục đã thêm; đó là lỗi tính đúng đắn trước khi là vấn đề tốc độ.

### 7.2. HashCode, equals và comparator không miễn phí

Nếu khóa là cấu trúc lớn, một lần tính mã băm hoặc kiểm tra bằng nhau có thể phải xử lý nhiều trường hay nhiều ký tự. Nếu mỗi lần so sánh tốn O(L), đường tìm kiếm cây có thể tốn O(L log n). Tìm tuần tự một giá trị trong danh sách có thể tốn O(nL).

Có thể hình dung chi phí tra bảng băm là: chi phí tính mã băm + chi phí xác định ngăn + chi phí so sánh các ứng viên. Ký hiệu O(1) theo n không nói rằng kích thước bản thân khóa không ảnh hưởng.

### 7.3. Duyệt gồm cả phần việc trong vòng lặp

Duyệt O(n) chỉ đếm chi phí đi qua collection. Nếu mỗi phần tử lại thực hiện một truy vấn O(n), toàn bộ đoạn mã có thể O(n²).

Ví dụ, với hai danh sách kích thước n và m, gọi `otherList.contains(x)` cho từng x trong danh sách thứ nhất có cận O(nm). Nếu chuyển danh sách thứ hai thành tập băm trước, tổng chi phí kỳ vọng có thể là O(m + n), kèm bộ nhớ bổ sung và yêu cầu hợp đồng bằng nhau/băm đúng.

Việc chuyển đổi cũng có chi phí. Với chỉ một truy vấn nhỏ, xây một tập mới có thể không mang lại lợi ích.

### 7.4. Sắp xếp trước chỉ có lợi khi được dùng lại

`contains` của một `ArrayList` đã sắp xếp vẫn tìm tuần tự; nó không tự đổi sang tìm nhị phân. Muốn tìm nhị phân phải dùng thuật toán phù hợp và bảo đảm dữ liệu đã sắp xếp theo đúng quy tắc.

`Collections.binarySearch` trên danh sách truy cập ngẫu nhiên như `ArrayList` là O(log n). Với danh sách liên kết lớn, Java dùng cách dựa trên iterator, có O(n) bước đi qua liên kết dù chỉ O(log n) lần so sánh. Nếu phải sắp xếp từ đầu cho một lần tìm, chi phí chuẩn bị vẫn phải tính vào tổng. [Tài liệu Collections.binarySearch của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#binarySearch(java.util.List,T))

## 8. Chương trình minh họa chạy được

Ví dụ sau làm rõ ba loại thao tác: truy cập theo chỉ số, sửa tại vị trí iterator và lấy theo ưu tiên. Nó minh họa hành vi và kết quả; không dùng thời gian chạy của vài phần tử để chứng minh Big O.

Lưu thành `CollectionCostDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedList;
import java.util.List;
import java.util.ListIterator;
import java.util.Map;
import java.util.PriorityQueue;

public class CollectionCostDemo {
    public static void main(String[] args) {
        List<Integer> numbers =
                new ArrayList<>(List.of(10, 20, 30, 40));

        System.out.println("get(2) = " + numbers.get(2));
        System.out.println("contains(30) = " + numbers.contains(30));

        // Chon remove(Object), khong phai remove(int index).
        numbers.remove(Integer.valueOf(20));
        System.out.println("after remove value = " + numbers);

        LinkedList<String> tasks =
                new LinkedList<>(List.of("A", "B", "C", "D"));

        // Viec tao iterator tai vi tri 2 cung co chi phi tim vi tri.
        ListIterator<String> cursor = tasks.listIterator(2);
        String removed = cursor.next();
        cursor.remove();
        cursor.add("X");

        System.out.println("removed by iterator = " + removed);
        System.out.println("tasks = " + tasks);

        Map<String, Integer> scores = new LinkedHashMap<>();
        scores.put("Lan", 9);
        scores.put("Minh", 7);

        System.out.println("get key = " + scores.get("Minh"));
        System.out.println("contains value = " + scores.containsValue(7));

        PriorityQueue<Integer> queue =
                new PriorityQueue<>(List.of(7, 2, 5, 1));
        List<Integer> ordered = new ArrayList<>();

        while (!queue.isEmpty()) {
            ordered.add(queue.poll());
        }

        System.out.println("poll order = " + ordered);
        System.out.println("remaining size = " + queue.size());
    }
}
~~~

Biên dịch và chạy trên JDK 17 trở lên:

~~~shell
javac --release 17 CollectionCostDemo.java
java CollectionCostDemo
~~~

Stdout chính xác:

~~~text
get(2) = 30
contains(30) = true
after remove value = [10, 30, 40]
removed by iterator = C
tasks = [A, B, X, D]
get key = 7
contains value = true
poll order = [1, 2, 5, 7]
remaining size = 0
~~~

Đối chiếu với mô hình:

- `get(2)` của `ArrayList` đi thẳng tới vị trí; `contains(30)` phải tìm theo giá trị.
- Xóa số 20 cần tìm nó và dịch phần phía sau. Viết `remove(20)` sẽ chọn overload nhận chỉ số, có thể ném `IndexOutOfBoundsException`.
- Tạo `listIterator(2)` phải xác định vị trí. Khi iterator đã đứng đó, xóa C và chèn X không phải tìm lại từ đầu.
- `scores.get("Minh")` tra bằng khóa; `containsValue(7)` có thể cần quét các mục.
- Thứ tự lấy từ `poll()` được bảo đảm theo ưu tiên. Không thay vòng lặp này bằng việc in `queue` rồi mặc định kết quả đã tăng dần.

## 9. Chọn cấu trúc theo công việc chi phối

| Công việc chính | Lựa chọn cần cân nhắc | Cơ sở |
| --- | --- | --- |
| Đọc theo chỉ số, thêm cuối, duyệt nhiều | `ArrayList` | Truy cập vị trí O(1), thêm cuối khấu hao O(1) |
| Xử lý FIFO hoặc ngăn xếp, thao tác hai đầu | `ArrayDeque` | Thêm hai đầu khấu hao O(1), lấy hai đầu O(1) |
| Duyệt và liên tục sửa tại vị trí con trỏ đã có | `LinkedList` với `ListIterator` | Thay liên kết tại vị trí O(1); vẫn tính đường đi tới vị trí |
| Kiểm tra trùng/thành viên nhiều lần | `HashSet` | O(1) kỳ vọng cho kiểm tra thành viên |
| Tra dữ liệu bằng khóa | `HashMap` | O(1) kỳ vọng cho tra khóa |
| Cần giữ thứ tự thêm khi duyệt | `LinkedHashSet` hoặc `LinkedHashMap` | Duyệt O(n) với thứ tự xác định |
| Cần dữ liệu theo thứ tự và tìm lân cận | `TreeSet` hoặc `TreeMap` | Các thao tác cơ bản O(log n) |
| Liên tục chọn phần tử ưu tiên nhất | `PriorityQueue` | Đọc đầu O(1), lấy đầu O(log n) |

Không dùng bảng như một bảng xếp hạng tốc độ tuyệt đối. Cần xét kích thước dữ liệu, tỉ lệ đọc/ghi, bộ nhớ, thứ tự, tính duy nhất và yêu cầu đồng thời. Hai cấu trúc có cùng O(n) khi duyệt vẫn khác nhau về số đối tượng, khả năng tận dụng bộ nhớ đệm CPU và áp lực thu gom rác.

## 10. Tự kiểm tra cách phân tích

1. **Xóa đầu ArrayList n lần đến khi rỗng:** O(n²), vì số phần tử dịch lần lượt gần n - 1, n - 2, …, 0. Với `ArrayDeque.pollFirst()`, tổng là O(n).
2. **Duyệt LinkedList bằng get(i):** O(n²). Duyệt bằng iterator là O(n).
3. **Tìm một giá trị trong TreeMap bằng containsValue:** O(n), dù `get(key)` là O(log n).
4. **Duyệt HashSet sau khi cấp dung lượng rất lớn:** cần tính O(n + c); số phần tử ít không bảo đảm duyệt rẻ.
5. **Lấy tất cả phần tử PriorityQueue theo thứ tự bằng poll:** O(n log n), không phải O(n) như duyệt iterator.
6. **Thêm cuối ArrayList một triệu lần:** tổng O(n) theo mô hình khấu hao; không bảo đảm mỗi lần gọi có cùng độ trễ.

Khi đọc một đoạn mã, hãy ghi rõ phương thức, triển khai thực tế, điều kiện đánh giá và số lần lặp. Bốn thông tin đó giúp biến một nhận xét mơ hồ như “collection này nhanh” thành một lập luận kiểm chứng được.
