# getFirst, getLast, removeFirst và removeLast

## 1. Đọc hai đầu và lấy bỏ hai đầu là hai nhu cầu khác nhau

Một ứng dụng có danh sách bước xử lý `[fetch, check, save]`. Màn hình xem trước cần biết bước mở đầu và bước kết thúc mà không đổi dữ liệu. Bộ xử lý lại có thể cần lấy bước đầu ra khỏi danh sách sau khi tiếp nhận công việc.

Hai nhu cầu ấy tương ứng với hai nhóm phương thức:

- `getFirst()` và `getLast()` **xem** phần tử ở hai đầu;
- `removeFirst()` và `removeLast()` **lấy bỏ**, đồng thời trả về phần tử vừa bỏ.

Từ Java 21, các phương thức này có mặt trong hợp đồng `SequencedCollection<E>`, giúp nhiều họ collection có thứ tự dùng chung cách diễn đạt. Các API tương tự trên `Deque` và `LinkedList` đã tồn tại trước đó; điểm mới của Java 21 là đưa chúng vào tầng hợp đồng chung và bổ sung cho những kiểu như `List`.

Bài này tập trung vào ý nghĩa của bốn thao tác: đầu nào được chọn, dữ liệu đổi ra sao, điều gì xảy ra khi rỗng hoặc không hỗ trợ xóa, và cách dùng đúng khi có `null`, phần tử đơn lẻ hay góc nhìn ngược. Ví dụ đầy đủ yêu cầu **Java 21 trở lên**, không dùng được với mục tiêu API Java 17.

## 2. “Đầu” và “cuối” được tính theo thứ tự nào?

**Thứ tự gặp phần tử (encounter order)** là trình tự logic từ phần tử đầu đến phần tử cuối của collection. Nó không phải vị trí vật lý trong bộ nhớ.

~~~text
trình tự hiện tại:    fetch ---- check ---- save
                     đầu                  cuối

getFirst()           fetch
getLast()                                 save
~~~

Thứ tự này do hợp đồng và trạng thái của cấu trúc quyết định:

| Cấu trúc | Cách hiểu đầu/cuối |
| --- | --- |
| `List` | Vị trí đầu và cuối của danh sách hiện tại |
| `Deque` | Đầu hàng đợi hai đầu và cuối hàng đợi hai đầu |
| `LinkedHashSet` dùng thêm thông thường | Đầu và cuối của thứ tự chèn các phần tử phân biệt |
| `SortedSet` | Đầu và cuối theo phép so sánh mà set sử dụng |
| View `reversed()` | Đầu/cuối theo chiều đã đảo của view |

`SequencedCollection` bảo đảm có trình tự để diễn đạt các thao tác này; nó không nói rằng mọi trình tự đều là thứ tự tăng dần hay thứ tự chèn. Bốn phương thức không có đối số vì vị trí cần xử lý đã được xác định bởi tên thao tác. [Java 21: SequencedCollection](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedCollection.html).

Một ví dụ cần nhớ: nếu tập hợp liên kết đang là `[z, a, m]`, `getFirst()` trả `z`, không tự tìm `a` là chữ nhỏ nhất. Nếu một tập hợp sắp xếp số theo chiều giảm đang là `[40, 30, 20, 10]`, phần tử đầu là `40`. Muốn hiểu kết quả, trước hết phải hiểu quy tắc thứ tự của nguồn.

## 3. Hợp đồng của từng phương thức

Cả bốn đều có kiểu trả về `E`, tức kiểu phần tử của collection. Chúng không trả về một collection mới và cũng không trả về cờ `boolean` thành công.

| Phương thức | Khi có phần tử phù hợp | Có lấy bỏ khỏi collection không? |
| --- | --- | --- |
| `E getFirst()` | Trả phần tử đầu hiện tại | Không |
| `E getLast()` | Trả phần tử cuối hiện tại | Không |
| `E removeFirst()` | Trả phần tử đầu vừa bị bỏ | Có, nếu thao tác được hỗ trợ |
| `E removeLast()` | Trả phần tử cuối vừa bị bỏ | Có, nếu thao tác được hỗ trợ |

### 3.1. getFirst và getLast giữ nguyên cấu trúc

Với một danh sách thông thường `[fetch, check, save]`:

~~~java
String first = steps.getFirst();
String last = steps.getLast();
~~~

Đây là đoạn minh họa Java 21 bên trong một phương thức, giả sử `steps` là `List<String>` không rỗng.

Sau hai lệnh:

- `first` bằng `"fetch"`;
- `last` bằng `"save"`;
- `steps` vẫn có ba phần tử theo cùng trình tự.

Nếu phần tử là đối tượng, kết quả là tham chiếu đến phần tử ấy, không phải bản sao sâu tự động. Gọi `getFirst` không tự xóa hay thay thế phần tử; nếu bạn sửa trạng thái của đối tượng được trả về, đó là một hành động khác cần đánh giá theo mô hình dữ liệu.

### 3.2. removeFirst và removeLast vừa lấy giá trị vừa đổi collection

Xét chuỗi thao tác sau trên một `ArrayList` có quyền xóa:

~~~text
ban đầu                         [fetch, check, save]

x = removeFirst()
x                               fetch
sau lần xóa đầu                 [check, save]

y = removeLast()
y                               save
sau lần xóa cuối                [check]
~~~

Sau mỗi lần xóa thành công, kích thước giảm một. Bước thứ hai dùng **trạng thái sau bước thứ nhất**, không làm việc trên một ảnh chụp chung tự động.

Không cần gọi `getFirst` rồi mới gọi `removeFirst` chỉ để nhận giá trị vừa lấy bỏ. `removeFirst` đã trả về giá trị đó. Viết thêm một lần đọc có thể vừa thừa vừa khiến người đọc hiểu nhầm có một giao dịch chung giữa hai thao tác.

### 3.3. Một phần tử vừa là đầu vừa là cuối

Với `[only]`, `getFirst()` và `getLast()` đều thấy `only`. Nhưng sau `removeFirst()`, collection trở thành rỗng. Gọi tiếp `removeLast()` trên một collection sửa được như `ArrayList` sẽ không lấy lại cùng phần tử; nó ném `NoSuchElementException`.

Do đó “lấy bỏ hai đầu” không nhất thiết có nghĩa “luôn trả đúng hai giá trị”. Phải quyết định chính sách cho các kích thước 0, 1 và ít nhất 2. Trong chương trình bên dưới, hàm `takeEnds` lấy mỗi phần tử biên đang tồn tại đúng một lần: đầu vào một phần tử chỉ cho ra một kết quả.

## 4. Collection rỗng: không có giá trị mặc định cho bốn thao tác này

Trên một `ArrayList` rỗng, cả bốn lệnh sau đều ném `NoSuchElementException`:

~~~java
empty.getFirst();
empty.getLast();
empty.removeFirst();
empty.removeLast();
~~~

Đây là bốn tình huống độc lập để minh họa. Nếu đặt liên tiếp trong cùng một luồng lệnh mà không bắt ngoại lệ, chương trình dừng ở lệnh thất bại đầu tiên; ba lệnh sau không tự chạy.

### 4.1. getFirst khác get(0) ở trường hợp rỗng

Trên `List` không rỗng, có thể hiểu kết quả của `getFirst()` tương ứng với `get(0)`, còn `getLast()` tương ứng với `get(size() - 1)`. Nhưng khi danh sách rỗng, API biên dùng `NoSuchElementException`, trong khi truy cập một chỉ số không hợp lệ dùng `IndexOutOfBoundsException`.

Tương tự, phương thức mặc định của `List` diễn đạt xóa đầu bằng vị trí `0`, xóa cuối bằng `size() - 1` khi có phần tử, nhưng xử lý rỗng theo hợp đồng các thao tác biên. Lớp triển khai có thể ghi đè để dùng cách thực hiện riêng. [Java 21: List, các thao tác tại hai đầu](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html#getFirst()).

Vì vậy, khi chuyển mã cũ từ `get(0)` sang `getFirst()`, hãy xem lại phần bắt ngoại lệ. Kết quả với dữ liệu hợp lệ có thể giống nhau, nhưng hợp đồng thất bại không nên bị bỏ qua.

### 4.2. Xử lý rỗng theo ý nghĩa nghiệp vụ

Có ba cách thường gặp:

1. **Rỗng là vi phạm điều kiện:** cứ gọi thao tác biên và để lớp gọi xử lý ngoại lệ thích hợp, hoặc kiểm tra rồi ném lỗi nghiệp vụ rõ ràng.
2. **Rỗng là kết quả bình thường:** trả một kết quả thể hiện không có dữ liệu, hoặc chọn API hàng đợi có quy ước phù hợp.
3. **Cần chờ dữ liệu:** dùng cơ chế hàng đợi/chặn phù hợp; bốn phương thức này không tự chờ phần tử xuất hiện.

Một đoạn `if (!items.isEmpty())` rồi gọi `getFirst` phù hợp khi bạn có quyền truy cập độc quyền trong suốt đoạn xử lý. Nó không biến hai lời gọi riêng thành một thao tác nguyên tử khi nhiều luồng cùng sửa collection.

### 4.3. Không bỏ qua giới hạn xóa khi diễn giải ngoại lệ

`removeFirst` và `removeLast` là các thao tác tùy chọn. Nếu nguồn không hỗ trợ xóa, có thể nhận `UnsupportedOperationException`. Đừng thiết kế mã tổng quát bằng suy luận “rỗng thì chắc chắn luôn ưu tiên `NoSuchElementException` trước mọi ngoại lệ khác” cho mọi cách triển khai.

Các collection không sửa được có quy tắc riêng về phương thức thay đổi dữ liệu. Tài liệu `Collection` nêu rằng cách triển khai có thể từ chối thao tác không được hỗ trợ ngay cả khi thao tác đó sẽ không làm thay đổi dữ liệu. [Java 21: Collection, thao tác tùy chọn](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collection.html).

Bảng kết quả rỗng trong chương trình này dùng một `ArrayList` mới, nên không trộn hai câu hỏi “không có phần tử” và “không được phép xóa”.

## 5. Giá trị null không có nghĩa là collection rỗng

Một số cách triển khai cho phép phần tử `null`. Với danh sách `[null, tail]`:

- `getFirst()` trả `null` nhưng kích thước vẫn là 2;
- `removeFirst()` trả `null` và thực sự lấy bỏ một phần tử, còn `[tail]`;
- chỉ sau khi tiếp tục lấy bỏ `tail` thì danh sách mới rỗng.

`ArrayList` cho phép phần tử `null`, nên đây là một trạng thái dữ liệu hợp lệ của lớp này. [Java 21: ArrayList](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ArrayList.html).

Điều nguy hiểm là tự viết helper trả `null` cho cả “không có phần tử” lẫn “có phần tử mang giá trị `null`”. Hai trạng thái khác nhau bị gộp lại, khiến bên gọi không biết liệu thao tác đã lấy bỏ dữ liệu hay chưa.

### 5.1. Optional cũng cần một chính sách về null

Đoạn minh họa sau có thể làm mất thông tin:

~~~java
return java.util.Optional.ofNullable(items.removeFirst());
~~~

Nếu phần tử đầu là `null`, lệnh xóa thành công nhưng kết quả là `Optional.empty()`. Điều đó không thể phân biệt với một quy ước “không có phần tử để xóa”.

`Optional.ofNullable` được định nghĩa là trả `Optional` rỗng khi đối số là `null`. [Java 21: Optional](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Optional.html#ofNullable(T)).

Nếu miền dữ liệu cấm `null`, một helper trả `Optional<E>` có thể hợp lý với hợp đồng rõ ràng. Nếu cần giữ khả năng có `null`, hãy dùng kiểu kết quả tách **có phần tử hay không** khỏi **giá trị phần tử**, như `Removal<E>(boolean present, E value)` trong chương trình đầy đủ.

Đó là kiểu phục vụ ví dụ của bài, không phải kiểu chuẩn có sẵn trong JDK. Helper kiểm tra rồi xóa ở đây yêu cầu không có thay đổi đồng thời trong suốt thao tác.

### 5.2. Phân biệt null phần tử với null tham chiếu nguồn

Nếu chính biến `items` là `null`, gọi `items.getFirst()` gây `NullPointerException` vì không có đối tượng nhận lời gọi. Đó không phải cách báo collection rỗng.

Đối với đầu vào công khai, có thể xác định rõ “không nhận nguồn `null`” rồi kiểm tra bằng `Objects.requireNonNull`. Đừng bắt mọi `RuntimeException` và đổi thành “không có dữ liệu”; cách đó có thể che lỗi truyền tham số hay nguồn không hỗ trợ thao tác.

## 6. Cùng phương thức nhưng quyền xóa khác nhau

Kiểu tĩnh `List<E>` hay `SequencedCollection<E>` không cam kết mọi cách triển khai đều cho phép xóa. Cần xem nguồn dữ liệu cụ thể.

| Nguồn ví dụ | Xem hai đầu khi không rỗng | Lấy bỏ hai đầu |
| --- | --- | --- |
| `new ArrayList<>(...)` | Có | Có |
| `new LinkedList<>(...)` | Có | Có |
| `new ArrayDeque<>(...)` | Có | Có |
| `Arrays.asList(...)` | Có | Không hỗ trợ đổi kích thước |
| `List.of(...)` | Có | Không hỗ trợ |
| Lớp bọc không sửa được | Có | Không hỗ trợ qua lớp bọc |

### 6.1. Arrays.asList có kích thước cố định, không phải hoàn toàn bất biến

`Arrays.asList(array)` trả một danh sách dựa trên mảng đã cho, với kích thước cố định. `set` có thể thay phần tử và thay đổi nhìn thấy trong mảng; thao tác thêm/xóa làm đổi kích thước không được hỗ trợ. [Java 21: Arrays.asList](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Arrays.html#asList(T...)).

Do đó một danh sách có thể vừa cho `getFirst`, `getLast` và `set`, vừa từ chối `removeFirst`, `removeLast`. Chỉ hỏi “nó có sửa được không?” còn quá chung; cần hỏi **thao tác nào** được phép.

Khi thật sự cần một bản sao có quyền đổi kích thước, có thể tạo `new ArrayList<>(fixed)`. Đây là quyết định sao chép và sở hữu dữ liệu, không phải một phép ép kiểu để mở quyền cho nguồn ban đầu.

### 6.2. List.of và lớp bọc không sửa được

Danh sách từ `List.of` không cho thêm, xóa hay thay phần tử. Chương trình minh họa đọc cuối thành công nhưng lấy bỏ cuối thất bại.

`Collections.unmodifiableList(source)` và các lớp bọc tương ứng chặn thao tác sửa qua view. Việc chặn xóa không tự tạo bản sao độc lập; nguồn phía dưới vẫn có thể được đổi qua tham chiếu khác. [Java 21: Collections](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html).

Nếu hàm chỉ cần xem biên, không nên đòi nguồn phải xóa được. Nếu hàm cần lấy bỏ biên, phải nêu yêu cầu ấy trong hợp đồng thay vì để người dùng phát hiện muộn qua ngoại lệ.

## 7. Tập hợp liên kết, tập hợp sắp xếp và view đảo chiều

### 7.1. LinkedHashSet: lấy theo vị trí trong trình tự của set

Một `LinkedHashSet` tạo từ `[z, a, m]` cho đầu là `z`, cuối là `m`. `removeLast()` trả `m` và set còn `[z, a]`.

Đây là lấy bỏ phần tử biên, không phải tìm một phần tử có giá trị lớn nhất. `LinkedHashSet` duy trì thứ tự chèn thông thường và cung cấp các thao tác hai đầu trong Java 21. [Java 21: LinkedHashSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashSet.html).

Tính duy nhất của set vẫn giữ nguyên. Nếu bạn từng thêm một giá trị trùng, không suy rằng có thêm một lần xuất hiện để hai phương thức xóa lần lượt lấy ra.

### 7.2. SortedSet: hai đầu do phép so sánh quyết định

`SortedSet` dùng thứ tự tự nhiên hoặc một `Comparator`. `getFirst` tương ứng phần tử đầu theo thứ tự ấy, `getLast` tương ứng phần tử cuối. Với chiều giảm của số nguyên, chúng lần lượt là giá trị lớn nhất và nhỏ nhất theo cách hiểu số học thông thường.

Xóa biên vẫn có thể được hỗ trợ ở một set sắp xếp sửa được. Việc `addFirst`/`addLast` không được hỗ trợ do áp đặt vị trí không có nghĩa `removeFirst`/`removeLast` cũng bị cấm. Xóa một phần tử đã có không yêu cầu đặt dữ liệu trái quy tắc sắp xếp. [Java 21: SortedSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SortedSet.html).

Đừng ghi cứng rằng `getFirst` luôn là số nhỏ nhất. Hãy đọc bộ so sánh. Chương trình chính cố tình dùng `Comparator.reverseOrder()` để kiểm chứng điểm này.

### 7.3. View ngược đổi cả đầu đọc lẫn đầu xóa

Với một danh sách sửa được và view `reversed()`:

~~~text
nguồn:                    [1, 2, 3, 4]
view ngược:               [4, 3, 2, 1]

view.getFirst()           4
view.getLast()            1

view.removeFirst()        trả 4, nguồn còn [1, 2, 3]
view.removeLast()         trả 1, nguồn còn [2, 3]
~~~

Một thao tác xóa trên view được phép sẽ truyền về cấu trúc nguồn. Nó không chỉ làm mất phần tử trong một bản sao tưởng tượng.

Tuy nhiên, hợp đồng chung của view ngược để lại một số đặc điểm quan sát thay đổi cho cách triển khai; không tự gán mọi tính chất của một `ArrayList` cho tất cả `SequencedCollection`. Trong ví dụ này, nguồn và view đều là cách dùng danh sách được kiểm chứng bằng chương trình.

## 8. Đối chiếu với peek và poll của Deque

`Deque` có hai phong cách xử lý thiếu dữ liệu:

| Ý định | Báo bằng ngoại lệ khi rỗng | Trả giá trị đặc biệt khi rỗng |
| --- | --- | --- |
| Xem đầu | `getFirst()` | `peekFirst()` trả `null` |
| Xem cuối | `getLast()` | `peekLast()` trả `null` |
| Lấy bỏ đầu | `removeFirst()` | `pollFirst()` trả `null` |
| Lấy bỏ cuối | `removeLast()` | `pollLast()` trả `null` |

`peek` không lấy bỏ, `poll` có lấy bỏ. Đây là nhóm API của `Deque`; đừng gọi `peekFirst` trên một biến chỉ khai báo `SequencedCollection` rồi cho rằng giao diện chung cũng có phương thức ấy. [Java 21: Deque](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Deque.html).

Nếu “hàng đợi hiện chưa có việc” là tình huống thường xuyên, `pollFirst` thường thể hiện ý định tốt hơn việc cứ gọi `removeFirst` rồi bắt ngoại lệ để điều khiển vòng lặp. Nhưng quy ước `null` chỉ dễ diễn giải khi nguồn không lưu `null`.

`ArrayDeque` cấm `null` và không an toàn cho nhiều luồng cùng sửa nếu thiếu cơ chế bên ngoài. Phần lớn các thao tác của nó có chi phí hằng số theo phân tích khấu hao; các thao tác tìm theo giá trị hoặc xóa qua vị trí iterator là những trường hợp khác. [Java 21: ArrayDeque](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ArrayDeque.html).

Ngược lại, `LinkedList` cho phép `null`. Nếu dùng nó như `Deque` rồi chèn `null`, kết quả `pollFirst() == null` có thể là phần tử vừa bị lấy bỏ, không đủ nói nguồn đã rỗng. [Java 21: LinkedList](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedList.html).

### 8.1. “Xem rồi xóa” không phải một giao dịch giữa nhiều luồng

Lịch xen kẽ có thể như sau:

~~~text
Luồng A: getFirst() thấy công việc X
Luồng B: removeFirst() lấy X
Luồng A: removeFirst() lấy công việc Y hoặc gặp nguồn rỗng
~~~

Ngay cả khi mỗi lời gọi trên một cấu trúc đồng thời là an toàn riêng lẻ, hai lời gọi của A vẫn không tự gắn với cùng một phần tử.

Nếu mục tiêu là nhận quyền xử lý phần tử vừa lấy ra, dùng một thao tác lấy bỏ trả về phần tử; chọn cơ chế đồng thời phù hợp. `ConcurrentLinkedDeque` cho phép thêm/xóa/đọc đồng thời an toàn và không cho phần tử `null`, nên một lần `pollFirst` có quy ước rỗng rõ hơn. Nó không biến một chuỗi nhiều lời gọi thành giao dịch nguyên tử. [Java 21: ConcurrentLinkedDeque](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ConcurrentLinkedDeque.html).

Nếu phải cùng lúc xem, kiểm tra nhiều điều kiện và lấy bỏ nhiều phần tử như một đơn vị, cần một thiết kế đồng bộ phù hợp với toàn bộ yêu cầu. Không dùng `isEmpty` hoặc `size` làm bằng chứng rằng trạng thái sẽ giữ nguyên ở lời gọi kế tiếp.

## 9. Chương trình đầy đủ để kiểm chứng các trường hợp biên

Lưu toàn bộ mã dưới vào **`EndOperationsDemo.java`**.

Chương trình chạy một luồng. Hai helper `takeFirstIfPresent` và `takeEnds` giả định được truy cập độc quyền trong suốt thao tác, đồng thời nguồn hỗ trợ các lần xóa thực sự được gọi. Chúng không cung cấp rollback nếu một cách triển khai tùy biến cho phép bước đầu nhưng từ chối bước sau.

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.Deque;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.SequencedCollection;
import java.util.SequencedSet;
import java.util.TreeSet;

public class EndOperationsDemo {
    record Removal<E>(boolean present, E value) {}

    // Requires exclusive access for the whole check-and-remove operation.
    static <E> Removal<E> takeFirstIfPresent(SequencedCollection<E> items) {
        if (items.isEmpty()) {
            return new Removal<>(false, null);
        }
        return new Removal<>(true, items.removeFirst());
    }

    // Removes each existing boundary once, including the singleton case.
    // Requires supported removals and exclusive access for the whole method.
    static <E> List<E> takeEnds(SequencedCollection<E> items) {
        List<E> removed = new ArrayList<>();
        if (!items.isEmpty()) {
            removed.add(items.removeFirst());
        }
        if (!items.isEmpty()) {
            removed.add(items.removeLast());
        }
        return removed;
    }

    static String failure(Runnable action) {
        try {
            action.run();
            return "no exception";
        } catch (NoSuchElementException | UnsupportedOperationException
                 | IndexOutOfBoundsException ex) {
            return ex.getClass().getSimpleName();
        }
    }

    public static void main(String[] args) {
        List<String> plan = new ArrayList<>(List.of("fetch", "check", "save"));
        System.out.println("read bounds: " + plan.getFirst() + " / " + plan.getLast());
        System.out.println("after reads: " + plan + ", size=" + plan.size());
        String first = plan.removeFirst();
        String last = plan.removeLast();
        System.out.println("removed bounds: " + first + " / " + last);
        System.out.println("remaining plan: " + plan);

        List<String> empty = new ArrayList<>();
        System.out.println("empty getFirst: " + failure(() -> empty.getFirst()));
        System.out.println("empty getLast: " + failure(() -> empty.getLast()));
        System.out.println("empty removeFirst: " + failure(() -> empty.removeFirst()));
        System.out.println("empty removeLast: " + failure(() -> empty.removeLast()));
        System.out.println("empty get(0): " + failure(() -> empty.get(0)));

        List<String> nullable =
                new ArrayList<>(Arrays.asList((String) null, "tail"));
        System.out.println("nullable getFirst: " + nullable.getFirst()
                + ", size=" + nullable.size());
        Removal<String> taken = takeFirstIfPresent(nullable);
        System.out.println("nullable removal: " + taken + ", remaining=" + nullable);
        System.out.println("nullable removeLast: " + nullable.removeLast());
        System.out.println("absent removal: " + takeFirstIfPresent(nullable));

        String[] backing = {"left", "right"};
        List<String> fixed = Arrays.asList(backing);
        System.out.println("fixed bounds: " + fixed.getFirst() + " / " + fixed.getLast());
        fixed.set(0, "changed");
        System.out.println("fixed set changes array: " + Arrays.toString(backing));
        System.out.println("fixed removeFirst: " + failure(() -> fixed.removeFirst()));

        List<String> readOnly = List.of("north", "south");
        System.out.println("read-only last: " + readOnly.getLast());
        System.out.println("read-only removeLast: " + failure(() -> readOnly.removeLast()));

        SequencedSet<String> selected =
                new LinkedHashSet<>(List.of("z", "a", "m"));
        System.out.println("linked set bounds: " + selected.getFirst()
                + " / " + selected.getLast());
        System.out.println("linked set removeLast: " + selected.removeLast());
        System.out.println("linked set remains: " + selected);

        SequencedSet<Integer> descending = new TreeSet<>(Comparator.reverseOrder());
        descending.addAll(List.of(10, 40, 20, 30));
        System.out.println("sorted bounds: " + descending.getFirst()
                + " / " + descending.getLast());
        int high = descending.removeFirst();
        int low = descending.removeLast();
        System.out.println("sorted removed: " + high + " / " + low
                + ", remaining=" + descending);

        List<Integer> source = new ArrayList<>(List.of(1, 2, 3, 4));
        List<Integer> backwards = source.reversed();
        System.out.println("reverse bounds: " + backwards.getFirst()
                + " / " + backwards.getLast());
        int reverseFirst = backwards.removeFirst();
        int reverseLast = backwards.removeLast();
        System.out.println("reverse removed: " + reverseFirst + " / " + reverseLast);
        System.out.println("source and reverse: " + source + " / " + backwards);

        List<String> singleton = new ArrayList<>(List.of("only"));
        System.out.println("singleton taken: " + takeEnds(singleton)
                + ", remaining=" + singleton);
        List<Integer> four = new ArrayList<>(List.of(1, 2, 3, 4));
        System.out.println("two ends taken: " + takeEnds(four) + ", remaining=" + four);

        Deque<String> queue = new ArrayDeque<>();
        System.out.println("deque empty getFirst: " + failure(() -> queue.getFirst()));
        System.out.println("deque empty peek/poll: " + queue.peekFirst()
                + " / " + queue.pollFirst());
        queue.addAll(List.of("W1", "W2", "W3"));
        List<String> drained = new ArrayList<>();
        String job;
        while ((job = queue.pollFirst()) != null) {
            drained.add(job);
        }
        System.out.println("deque drained: " + drained + ", empty=" + queue.isEmpty());
    }
}
~~~

Biên dịch bằng JDK 21 trở lên và chạy trên Java 21 trở lên:

~~~shell
javac --release 21 -encoding UTF-8 EndOperationsDemo.java
java EndOperationsDemo
~~~

Không cần `--enable-preview`. Ví dụ đã được biên dịch với mức release 21 và chạy thành công bằng OpenJDK 24.0.2. Kết quả dùng chuỗi ASCII để không phụ thuộc khả năng hiện dấu của terminal.

Stdout chính xác:

~~~text
read bounds: fetch / save
after reads: [fetch, check, save], size=3
removed bounds: fetch / save
remaining plan: [check]
empty getFirst: NoSuchElementException
empty getLast: NoSuchElementException
empty removeFirst: NoSuchElementException
empty removeLast: NoSuchElementException
empty get(0): IndexOutOfBoundsException
nullable getFirst: null, size=2
nullable removal: Removal[present=true, value=null], remaining=[tail]
nullable removeLast: tail
absent removal: Removal[present=false, value=null]
fixed bounds: left / right
fixed set changes array: [changed, right]
fixed removeFirst: UnsupportedOperationException
read-only last: south
read-only removeLast: UnsupportedOperationException
linked set bounds: z / m
linked set removeLast: m
linked set remains: [z, a]
sorted bounds: 40 / 10
sorted removed: 40 / 10, remaining=[30, 20]
reverse bounds: 4 / 1
reverse removed: 4 / 1
source and reverse: [2, 3] / [3, 2]
singleton taken: [only], remaining=[]
two ends taken: [1, 4], remaining=[2, 3]
deque empty getFirst: NoSuchElementException
deque empty peek/poll: null / null
deque drained: [W1, W2, W3], empty=true
~~~

### 9.1. Nhóm đọc và nhóm xóa

Hai dòng đầu cho thấy xem đầu/cuối không đổi danh sách. Sau đó, giá trị trả về từ hai lần xóa là `fetch` và `save`; phần tử giữa `check` còn lại.

Hãy để ý chương trình giữ giá trị vừa xóa vào biến trước khi in. Cách viết này làm thứ tự thay đổi rõ ràng, thuận lợi cho kiểm thử và tránh nhìn một biểu thức dài có nhiều tác dụng phụ.

### 9.2. Nhóm rỗng và nhóm null

Năm dòng về rỗng phân biệt ngoại lệ của thao tác biên với ngoại lệ truy cập chỉ số.

Hai đối tượng `Removal` có cùng `value=null` nhưng khác `present`: trường hợp đầu đã lấy bỏ một phần tử hợp lệ, trường hợp sau không có phần tử. Cờ riêng giúp bên gọi không suy sai từ giá trị `null`.

### 9.3. Nhóm quyền sửa và ý nghĩa thứ tự

Danh sách kích thước cố định đọc được và thay thế phần tử được, nhưng không xóa đầu được. Danh sách chỉ đọc cũng đọc cuối được nhưng từ chối xóa cuối.

Set liên kết lấy biên theo trình tự chèn; set sắp xếp giảm lấy biên theo bộ so sánh. View đảo chiều xóa khỏi nguồn ở đầu đối diện. Các kết quả này minh họa cùng tên phương thức nhưng nguồn vẫn giữ quy tắc riêng.

### 9.4. Nhóm phần tử đơn lẻ và vòng lặp deque

`takeEnds` kiểm tra lại sau lần xóa đầu. Vì vậy, phần tử đơn lẻ không bị yêu cầu xóa lần thứ hai. Với bốn phần tử, hàm trả hai biên và giữ phần giữa.

Vòng lặp dùng `ArrayDeque.pollFirst` tiếp nhận mỗi công việc đúng theo lần lấy bỏ. Điều kiện dừng bằng `null` dựa trên chính sách không cho `null` của nguồn đã chọn; không chép nguyên cách này sang một nguồn cho phép `null` mà không xem lại hợp đồng.

## 10. Cơ chế mặc định và chi phí thực tế

Một giao diện cung cấp từ vựng chung, không đồng nhất mọi thuật toán bên dưới.

Ở mức `SequencedCollection`, phương thức mặc định lấy đầu qua iterator, lấy cuối qua iterator của view ngược; xóa lấy phần tử rồi dùng thao tác xóa của iterator. Những nhánh như `List` và các lớp cụ thể có thể có cách triển khai phù hợp hơn.

Đối với `ArrayList`, đọc hai biên không phải lý do để thay mảng động bằng một cấu trúc khác. Nhưng nếu bạn xóa đầu liên tục, các phần tử còn lại phải dịch về trước. Với n phần tử, việc lấy bỏ đầu cho đến hết có thể cần số lần dịch theo tổng:

~~~text
(n - 1) + (n - 2) + ... + 1
= n * (n - 1) / 2
~~~

Đây là phân tích số phần tử cần dịch của cách dùng mảng động, không phải số đo thời gian từ một benchmark. Tổng tăng bậc hai theo n. Đổi tên `remove(0)` thành `removeFirst()` không loại bỏ công việc dịch ấy.

Khi nghiệp vụ chủ yếu thêm/lấy bỏ ở hai đầu, một `Deque` phù hợp có thể là lựa chọn tốt hơn. Khi cần truy cập chỉ số nhiều, danh sách dựa trên mảng vẫn có lợi thế riêng. Chọn theo tập thao tác thực tế, không chỉ theo việc cả hai đều có `removeFirst`.

Một hàm tổng quát nhận `SequencedCollection` không được hứa bốn thao tác luôn có thời gian hằng số. Muốn nêu bảo đảm hiệu năng, phải dựa vào tài liệu của nguồn và giới hạn cách dùng.

## 11. Cách áp dụng vào mã nghiệp vụ

### 11.1. Chỉ đọc thông tin biên: giữ quyền sửa bên ngoài hàm

Một hàm tóm tắt có thể nhận `SequencedCollection<? extends E>` rồi chỉ gọi các phương thức đọc. Nó vẫn nên xác định chính sách rỗng và tránh hứa đầu/cuối đại diện cho một ảnh chụp nhất quán nếu dữ liệu đang thay đổi.

Không gọi `removeFirst` chỉ vì muốn một phần tử để hiển thị. Sai lựa chọn đó có thể khiến giao diện “xem trước” vô tình tiêu thụ công việc.

### 11.2. Tiêu thụ công việc: dùng giá trị do thao tác xóa trả về

Nếu đã được phép lấy bỏ, hãy xử lý phần tử thực sự nhận từ `removeFirst` hoặc `pollFirst`. Đừng xử lý một giá trị từ lần `getFirst` trước rồi xóa một phần tử khác sau đó.

Cũng phải quyết định khi việc xử lý thất bại sau khi lấy bỏ: có đưa công việc trở lại, ghi vào nguồn thử lại hay lưu trạng thái khác không? Collection chỉ thực hiện thao tác dữ liệu; nó không tự bảo đảm một quy trình giao dịch hay “xử lý đúng một lần” cho nghiệp vụ.

### 11.3. Hai đầu không phải hai lần xuất hiện của cùng một giá trị

Với `[A, B, A]`, xem đầu và cuối cùng trả giá trị `A`, nhưng đó là hai vị trí. Lấy bỏ đầu rồi cuối thành công hai lần để lại `[B]`.

Với `[A]`, có đúng một vị trí. Chính sách “lấy mỗi phần tử biên một lần” cần phân biệt hai trường hợp. Không dùng `first.equals(last)` để đoán collection chỉ có một phần tử, vì hai vị trí khác nhau có thể chứa các phần tử bằng nhau hoặc cùng tham chiếu.

### 11.4. Đừng nhầm với API biên của map

`SequencedMap` dùng `firstEntry`, `lastEntry`, `pollFirstEntry` và `pollLastEntry` cho các ánh xạ khóa–giá trị. Nó không phải `SequencedCollection` của các entry; không gọi `map.getFirst()` theo suy đoán từ tên bài này.

Các phương thức entry biên của `SequencedMap` có thể trả `null` khi map rỗng, khác quy ước ngoại lệ của bốn phương thức collection đang học. [Java 21: SequencedMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedMap.html).

## 12. Lỗi thường gặp và cách nhận ra

| Lỗi | Hậu quả hoặc dấu hiệu | Cách sửa theo hợp đồng |
| --- | --- | --- |
| Dùng `getFirst` khi muốn tiếp nhận công việc | Phần tử vẫn nằm trong nguồn | Dùng thao tác lấy bỏ phù hợp |
| Dùng `removeLast` để xem trước | Dữ liệu mất khỏi cuối | Dùng `getLast` |
| Cho rằng rỗng trả `null` | Gặp `NoSuchElementException` ở nguồn sửa được | Chọn chính sách rỗng hoặc API phù hợp |
| Thấy kết quả `null` thì kết luận rỗng | Bỏ sót phần tử `null` hợp lệ | Tách trạng thái hiện diện khỏi giá trị |
| Gọi xóa hai đầu vô điều kiện | Thất bại ở đầu vào 0 hoặc 1 phần tử | Xác định và xử lý từng trường hợp |
| Xóa trên `Arrays.asList` | `UnsupportedOperationException` | Dùng nguồn hỗ trợ xóa hoặc tạo bản sao đúng mục đích |
| Xem đầu là phần tử nhỏ nhất với mọi set | Kết quả sai ở trình tự chèn hoặc bộ so sánh giảm | Đọc quy tắc thứ tự của nguồn |
| Xóa từ view ngược rồi tưởng nguồn giữ nguyên | Nguồn bị đổi ở đầu đối diện | Nhận diện view và quyền sở hữu dữ liệu |
| Liên tục xóa đầu `ArrayList` lớn | Tốn công dịch phần tử | Xem lại cấu trúc theo khối lượng thao tác |
| Kiểm tra rỗng rồi coi trạng thái đã được giữ chỗ | Lỗi khi có luồng khác xen vào | Thiết kế đồng bộ hoặc dùng thao tác đồng thời phù hợp |

Khi gặp lỗi, hãy tách ba câu hỏi: **đang nhìn theo hướng nào, nguồn hiện có phần tử không, và thao tác xóa có được hỗ trợ không?** Chúng độc lập; sửa một câu hỏi chưa chắc giải quyết được hai câu còn lại.

## 13. Thực hành có đáp án

### Bài 1 — Dự đoán trạng thái sau từng lệnh

Một `ArrayList<Integer>` có `[7, 8, 9]`. Lần lượt gọi `getLast()`, `removeFirst()`, `getFirst()`, `removeLast()`. Giá trị trả về và dữ liệu cuối là gì?

**Đáp án:** lần lượt trả `9`, `7`, `8`, `9`. Sau lần đọc đầu tiên, danh sách chưa đổi. Sau hai lần xóa, còn `[8]`.

### Bài 2 — Phần tử đơn lẻ

Một danh sách sửa được có `[X]`. Có thể viết `List.of(items.removeFirst(), items.removeLast())` để lấy cả hai biên không?

**Đáp án:** không phù hợp. Lần xóa đầu làm nguồn rỗng, lần xóa cuối ném ngoại lệ. Biểu thức không trở thành một thao tác nguyên tử hay tự rollback. Ngoài ra `List.of` không nhận `null`, nên cách tạo kết quả đó còn đặt thêm điều kiện về dữ liệu. Hãy định nghĩa chính sách kích thước 0/1/n và dùng cấu trúc kết quả phù hợp.

### Bài 3 — Giá trị null

Nguồn là một `ArrayList<String>` chứa đúng một phần tử `null`. `removeFirst()` trả gì, và làm sao biết nó đã xóa thành công?

**Đáp án:** trả `null` và nguồn trở thành rỗng. Bản thân giá trị trả về không có nghĩa “thất bại”. Trong ngữ cảnh truy cập độc quyền, có thể dựa vào thao tác hoàn tất bình thường và một kết quả hiện diện rõ ràng như helper trong bài. Không dùng `Optional.ofNullable` để bảo toàn đầy đủ hai trạng thái nếu miền dữ liệu cho `null`.

### Bài 4 — Quyền đọc và quyền đổi kích thước

Cho `String[] a = {"L", "R"}` và `List<String> x = Arrays.asList(a)`. Vì sao `x.getFirst()` và `x.set(0, "N")` có thể thành công nhưng `x.removeFirst()` thất bại?

**Đáp án:** danh sách dựa trên mảng có kích thước cố định. Đọc và thay thế phần tử không làm đổi kích thước; xóa thì có. Sau `set`, mảng cũng chứa `"N"` ở vị trí đầu. Muốn xóa trong một bản sao độc lập về cấu trúc, có thể tạo `new ArrayList<>(x)` rồi xóa trên bản sao, nếu đó đúng mục đích nghiệp vụ.

### Bài 5 — Bộ so sánh giảm

Một `TreeSet<Integer>` dùng `Comparator.reverseOrder()` chứa `2, 5, 1`. `getFirst()` và `removeLast()` trả gì? Còn gì sau lần xóa?

**Đáp án:** trình tự là `[5, 2, 1]`. `getFirst()` trả `5` và không đổi nguồn. `removeLast()` trả `1`, còn `[5, 2]`. “Đầu” phải theo bộ so sánh, không mặc định theo giá trị nhỏ nhất thông thường.

### Bài 6 — Xóa từ view ngược

Nguồn là `[P, Q, R]`. Lấy view ngược `v`, rồi gọi `v.removeLast()`. Giá trị nào bị lấy bỏ và nguồn còn gì?

**Đáp án:** view là `[R, Q, P]` nên cuối view là `P`. Lời gọi lấy bỏ `P` khỏi nguồn, nguồn còn `[Q, R]`; view còn `[R, Q]`. Đây là thao tác trên view có quyền sửa, không phải trên bản sao.

### Bài 7 — Chọn API cho hàng đợi không cho null

Một vòng lặp lấy công việc từ `ArrayDeque` và dừng khi không có việc. Nên dùng cặp `isEmpty` rồi `removeFirst` hay một lần `pollFirst` trong điều kiện?

**Đáp án:** trong ngữ cảnh phù hợp với `ArrayDeque`, `pollFirst` diễn đạt trực tiếp “lấy nếu có”, trả `null` khi rỗng; quy ước rõ vì nguồn cấm `null`. Nếu nhiều luồng cùng dùng, phải thay cấu trúc/đồng bộ phù hợp, không coi `ArrayDeque` tự an toàn. Với `LinkedList` chứa `null`, cần xem lại điều kiện dừng.

### Bài 8 — Kiểm chứng hợp đồng và hiệu năng

Bạn thay vòng lặp xóa `list.remove(0)` bằng `list.removeFirst()` trên một `ArrayList` lớn. Có thể tuyên bố thuật toán đã đổi từ bậc hai thành tuyến tính không? Kiểm thử nào còn cần cho thay đổi?

**Đáp án:** không. Tên API mới không loại bỏ việc dịch phần tử khi xóa đầu mảng động. Cần đánh giá lại cấu trúc theo khối lượng công việc. Kiểm thử hành vi phải có nguồn rỗng, một phần tử, nhiều phần tử, dữ liệu `null` nếu được phép và nguồn không hỗ trợ xóa nếu hàm nhận loại đó; xem lại loại ngoại lệ nếu mã cũ dựa vào `IndexOutOfBoundsException`.

Sau khi chạy ví dụ, hãy thay dữ liệu đầu vào của `takeEnds` bằng các trường hợp 0, 1, 2 và 3 phần tử. Ghi trạng thái sau mỗi lần xóa và giải thích vì sao hàm không thể lấy bỏ cùng một vị trí hai lần khi nguồn chỉ có một phần tử.
