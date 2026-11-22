# Vì sao iterator không duyệt theo thứ tự ưu tiên

## 1. Hai ý nghĩa khác nhau của “phần tử tiếp theo”

Một ứng dụng giữ công việc trong `PriorityQueue` và cần hiển thị danh sách theo mức ưu tiên. Lập trình viên viết vòng `for`, thấy một phần tử kém ưu tiên xuất hiện trước phần tử tốt hơn và nghi rằng hàng đợi bị hỏng.

Vấn đề thường nằm ở kỳ vọng đối với phép duyệt.

Trong `PriorityQueue`:

- **Phần tử tiếp theo được lấy bằng `poll()`** là đầu hàng đợi theo quy tắc ưu tiên.
- **Phần tử tiếp theo được trả bằng `Iterator.next()`** là phần tử tiếp theo của lượt duyệt; API không cam kết nó có ưu tiên tốt nhất trong số phần tử chưa duyệt.

Iterator không phải một vòng `poll()` được giấu bên trong. Một bên đọc các phần tử; bên kia lấy/xóa đầu và sửa lại cấu trúc để đầu mới tiếp tục đúng.

Sau bài này, người học cần giải thích được nguồn gốc khác biệt đó, biết nhận ra các cách viết không tự sắp xếp, và chọn được cách xem theo ưu tiên với tác động dữ liệu phù hợp.

## 2. PriorityQueue bảo đảm điều gì?

### 2.1. Bảo đảm ở đầu hàng đợi

Theo thứ tự tự nhiên của `Integer`, số nhỏ hơn đứng trước. Nếu hàng đợi chứa 12, 4, 9, 1, 7, 3, 6 thì `peek()` cho 1. Lấy hết bằng `poll()` cho các giá trị theo thứ tự:

```text
1, 3, 4, 6, 7, 9, 12
```

Nếu dùng comparator đảo chiều, giá trị lớn hơn có thể đứng trước. “Ưu tiên trước” luôn phải được hiểu theo comparator hoặc thứ tự tự nhiên đang áp dụng.

`peek()` xem đầu mà không lấy ra. `poll()` lấy đầu và thay đổi hàng đợi. Đây là những phép gắn trực tiếp với quy tắc chọn đầu.

### 2.2. Không có bảo đảm tương tự cho toàn bộ lượt duyệt

Tài liệu của `PriorityQueue` nêu rõ iterator không bảo đảm trả các phần tử theo một thứ tự cụ thể. Spliterator và các cách đọc dựa trên nó cũng không tạo bảo đảm thứ tự ưu tiên. Xem [PriorityQueue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html#iterator()).

Điều này không có nghĩa iterator được phép tùy ý bỏ sót các phần tử hoặc tự thêm phần tử. Trong một lượt đọc bình thường, khi hàng đợi không bị thay đổi, iterator cho phép đi qua các lần xuất hiện đang chứa. Điều không được cam kết ở đây là **thứ tự giữa những lần xuất hiện đó**.

Cũng không được suy ra iterator luôn trả đúng thứ tự thêm vào, luôn tăng dần, hoặc luôn có một bố trí cố định giữa các phiên bản cài đặt.

“Không bảo đảm thứ tự” không đồng nghĩa với “mỗi lần duyệt đều phải ngẫu nhiên”. Một chương trình có thể thấy cùng một thứ tự nhiều lần. Sự lặp lại quan sát được không biến thành hợp đồng của API.

## 3. Nguyên nhân cấu trúc: heap chỉ duy trì thứ tự từng nhánh

### 3.1. Gốc nhỏ nhất chưa làm toàn bộ mảng tăng dần

Một mô hình min-heap hợp lệ:

```text
             1
           /   \
          4     3
         / \   / \
        12  7 9   6
```

Điều kiện quan trọng là mỗi nút cha không lớn hơn các nút con:

```text
1 ≤ 4 và 1 ≤ 3
4 ≤ 12 và 4 ≤ 7
3 ≤ 9 và 3 ≤ 6
```

Nhờ tính bắc cầu của thứ tự, 1 không lớn hơn mọi phần tử dưới nó. Như vậy heap đủ thông tin để biết phần tử nhỏ nhất ở gốc.

Nhưng không có điều kiện bắt buộc rằng con trái 4 phải nhỏ hơn con phải 3. Cũng không có điều kiện buộc lá 7 ở nhánh trái phải đứng trước lá 6 ở nhánh phải theo giá trị.

### 3.2. Đọc theo vị trí lưu trữ không phải đọc theo hạng ưu tiên

Heap nhị phân có thể được biểu diễn bằng mảng theo từng mức:

```text
Chỉ số:    0  1  2   3  4  5  6
Giá trị:  [1, 4, 3, 12, 7, 9, 6]
```

Nếu đọc mảng từ trái sang phải, ngay sau 1 sẽ gặp 4, mặc dù 3 có ưu tiên tốt hơn 4. Đó là một phản ví dụ đủ để thấy:

```text
đúng tính chất heap
    không kéo theo
đúng thứ tự tăng dần của toàn bộ dãy đọc
```

Hình và mảng trên giải thích cơ chế. Mảng heap không phải một API chỉ số công khai của `PriorityQueue`, và bố trí cụ thể không phải đầu ra bắt buộc của iterator.

### 3.3. Một đường đọc không tự chọn tốt nhất giữa mọi nhánh

Để đọc theo ưu tiên, sau khi đã chọn gốc 1, cần quyết định phần tử tốt nhất còn lại giữa các nhánh. Việc đơn giản tăng chỉ số sang phần tử 4 không thực hiện quyết định đó.

Min-heap được thiết kế để cập nhật đầu hiệu quả sau khi thêm/lấy phần tử, thay vì duy trì toàn bộ dữ liệu như một danh sách đã sắp xếp. Nếu bắt iterator tự trả toàn bộ theo ưu tiên, nó phải làm thêm công việc như giữ một cấu trúc phụ hoặc sắp xếp một bản sao. Hợp đồng iterator hiện tại không yêu cầu công việc đó.

Trong OpenJDK 17u, lượt iterator chỉ đọc thông thường đi qua các vị trí của mảng heap. Lớp còn xử lý riêng tình huống xóa qua iterator; vì vậy không nên biến mô tả đường đọc thông thường thành một công thức áp dụng cho mọi lượt duyệt có sửa đổi. Có thể đối chiếu [lớp iterator trong mã nguồn PriorityQueue OpenJDK 17u](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/PriorityQueue.java).

## 4. Vì sao poll lặp lại tạo được thứ tự ưu tiên?

Với heap mô hình ở trên, lấy 1 ra không đơn giản là nhảy qua ô đầu của mảng.

Một cách duy trì heap thực hiện:

1. Giữ 1 làm kết quả.
2. Đưa phần tử cuối 6 lên gốc và bỏ vị trí cuối cũ.
3. So sánh để đẩy 6 xuống vị trí hợp lệ.
4. Đặt phần tử phù hợp ở gốc mới.

Trạng thái tạm và trạng thái sau sửa:

```text
Trước khi lấy:              [1, 4, 3, 12, 7, 9, 6]
Đưa phần tử cuối lên gốc:   [6, 4, 3, 12, 7, 9]
Sửa quan hệ cha–con:        [3, 4, 6, 12, 7, 9]
```

Sau đó, phần tử được chọn cho lần `poll()` tiếp theo là 3. Lấy tiếp lại sửa heap để 4 trở thành đầu.

| Thao tác | Có tìm đầu ưu tiên hiện tại? | Có lấy phần tử ra? | Có duy trì lại heap sau lần lấy? |
| --- | --- | --- | --- |
| `peek()` | Xem đầu hiện có | Không | Không cần vì chỉ đọc |
| `poll()` | Có | Có | Có khi còn phần tử |
| `Iterator.next()` | Không có hợp đồng chọn ưu tiên | Không | Không thực hiện bước lấy đầu |

Chính sự kết hợp “lấy đầu rồi sửa cấu trúc” tạo ra dãy ưu tiên khi lặp `poll()`. Iterator không làm hai bước đó nên không có cùng bảo đảm.

Bảo đảm này giả định quy tắc so sánh và khóa ưu tiên không bị thay đổi tùy ý trong lúc phần tử đang nằm trong hàng đợi. Nếu sửa trực tiếp khóa làm heap không còn phù hợp, không thể dùng kết quả đó để đánh giá quy tắc duyệt bình thường.

## 5. Chương trình quan sát: cùng dữ liệu, hai thứ tự khác nhau

Lưu mã sau vào **PriorityIterationObservation.java**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.Iterator;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.PriorityQueue;

public class PriorityIterationObservation {
    private static List<Integer> pollAll(PriorityQueue<Integer> queue) {
        List<Integer> result = new ArrayList<>();
        Integer value;
        while ((value = queue.poll()) != null) {
            result.add(value);
        }
        return result;
    }

    public static void main(String[] args) {
        List<Integer> input = List.of(12, 4, 9, 1, 7, 3, 6);
        PriorityQueue<Integer> queue = new PriorityQueue<>();
        queue.addAll(input);

        System.out.println("insertion order: " + input);
        System.out.println("head before iteration: " + queue.peek());

        List<Integer> visited = new ArrayList<>();
        Iterator<Integer> iterator = queue.iterator();
        while (iterator.hasNext()) {
            visited.add(iterator.next());
        }
        System.out.println("observed iterator order: " + visited);
        System.out.println("size after iteration: " + queue.size());
        System.out.println("head after iteration: " + queue.peek());

        List<Integer> sortedVisited = new ArrayList<>(visited);
        Collections.sort(sortedVisited);
        List<Integer> sortedInput = new ArrayList<>(input);
        Collections.sort(sortedInput);
        System.out.println("same elements: " + sortedVisited.equals(sortedInput));

        PriorityQueue<Integer> copy = new PriorityQueue<>(queue);
        System.out.println("poll order on copy: " + pollAll(copy));
        System.out.println("original size after copy: " + queue.size());
        System.out.println("poll order on original: " + pollAll(queue));
        System.out.println("original size after polling: " + queue.size());

        Iterator<Integer> empty = queue.iterator();
        System.out.println("empty iterator hasNext: " + empty.hasNext());
        try {
            empty.next();
        } catch (NoSuchElementException ex) {
            System.out.println("empty iterator next: " + ex.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 PriorityIterationObservation.java
java PriorityIterationObservation
```

Chương trình đã được biên dịch với `--release 17` và chạy trên OpenJDK 24.0.2. Stdout quan sát được chính xác trong lần kiểm tra:

```text
insertion order: [12, 4, 9, 1, 7, 3, 6]
head before iteration: 1
observed iterator order: [1, 4, 3, 12, 7, 9, 6]
size after iteration: 7
head after iteration: 1
same elements: true
poll order on copy: [1, 3, 4, 6, 7, 9, 12]
original size after copy: 7
poll order on original: [1, 3, 4, 6, 7, 9, 12]
original size after polling: 0
empty iterator hasNext: false
empty iterator next: NoSuchElementException
```

Dòng `observed iterator order` là kết quả quan sát của môi trường đã nêu, **không phải một thứ tự mà mọi Java 17+ phải tạo ra**. Cờ `--release 17` kiểm tra việc dùng ngôn ngữ/API mục tiêu và tạo bytecode tương ứng; nó không đổi JVM chạy ví dụ thành Java 17.

Những điểm có giá trị học tập:

- Thứ tự thêm bắt đầu bằng 12, nhưng đầu là 1.
- Trong kết quả quan sát, iterator trả 4 trước 3 và 12 trước 7. Dãy đó chưa được sắp xếp theo ưu tiên.
- Kích thước và đầu giữ nguyên sau lượt iterator chỉ đọc.
- Sắp xếp bản các phần tử đã đọc cho kết quả bằng sắp xếp đầu vào: iterator vẫn đọc đủ dữ liệu.
- Lấy hết từ bản sao cho thứ tự ưu tiên và không làm giảm kích thước bản gốc.
- Lấy hết từ bản gốc cũng cho thứ tự đó nhưng làm hàng đợi rỗng.
- Iterator rỗng trả `false` từ `hasNext()`; gọi `next()` khi không còn phần tử báo `NoSuchElementException`, không trả `null`.

Hàm `pollAll` dùng `null` làm dấu dừng vì `PriorityQueue` cấm phần tử `null`. Không suy nguyên xi cách dừng này thành quy tắc cho mọi kiểu collection hoặc iterator.

## 6. Những cách viết trông khác nhau nhưng không tự sắp xếp

### 6.1. Enhanced for chỉ che cách gọi iterator

Đoạn sau minh họa một lượt đọc:

```java
// queue là PriorityQueue<Integer> đã có dữ liệu.
for (Integer value : queue) {
    System.out.println(value);
}
```

Enhanced for không chuyển thành thuật toán lấy đầu ưu tiên. Với một đối tượng `Iterable` như hàng đợi, nó dùng iterator để đi qua phần tử.

Vì vậy việc đổi từ vòng `while (iterator.hasNext())` sang `for` không sửa được yêu cầu hiển thị tăng dần.

### 6.2. forEach, toArray và toString cũng chưa đủ

| Cách đọc | Có tự sắp xếp theo ưu tiên không? |
| --- | --- |
| `queue.iterator()` | Không |
| `for (E e : queue)` | Không |
| `queue.forEach(action)` | Không |
| `queue.toArray()` | Không |
| `new ArrayList<>(queue)` | Không |
| `System.out.println(queue)` | Không |
| `queue.stream().toList()` | Không |

“Không” ở bảng nghĩa là không có một bước và một hợp đồng sắp xếp theo ưu tiên. Kết quả vẫn có thể tình cờ trông đúng trên dữ liệu nào đó.

Chuyển dữ liệu sang một kiểu chứa khác không tự bổ sung quy tắc thứ tự. Nếu giao diện cần một danh sách đã xếp, phải có bước xếp hoặc có cách lấy theo ưu tiên rõ ràng.

### 6.3. forEachOrdered không phải tên khác của sorted

Trong stream, `forEachOrdered` giữ thứ tự gặp của stream khi stream có thứ tự gặp được xác định. Nó không tự hỏi comparator của `PriorityQueue` rồi sắp xếp.

Vì nguồn hàng đợi này không cam kết thứ tự gặp theo ưu tiên, gọi:

```java
// Không bổ sung bảo đảm thứ tự ưu tiên:
queue.stream().forEachOrdered(System.out::println);
```

chưa giải quyết yêu cầu. Nếu cần xếp, dùng `sorted(comparator)`. Nếu kết hợp stream song song và cần in theo thứ tự sau bước xếp, dùng thao tác cuối tôn trọng thứ tự đó.

Các ý nghĩa này được mô tả trong [tài liệu Stream Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#forEachOrdered(java.util.function.Consumer)).

## 7. Ba cách đúng để xem theo ưu tiên mà giữ bản gốc

### 7.1. Sao chép PriorityQueue rồi poll bản sao

Một phương thức tiện ích có thể đặt trong lớp của ứng dụng:

```java
static <E> List<E> orderedByPolling(PriorityQueue<E> source) {
    PriorityQueue<E> copy = new PriorityQueue<>(source);
    List<E> result = new ArrayList<>();
    while (!copy.isEmpty()) {
        result.add(copy.poll());
    }
    return result;
}
```

Đây là phương thức minh họa, cần import `List`, `ArrayList` và `PriorityQueue`; chương trình đầy đủ bên dưới có một biến thể tương đương.

Constructor nhận `PriorityQueue` giữ quy tắc so sánh của nguồn. Vòng `poll()` tác động lên bản sao, nên cấu trúc hàng đợi nguồn không bị rút cạn.

Cách này bám sát đúng câu hỏi: “Nếu liên tục lấy đầu, thứ tự sẽ là gì?” Nó đặc biệt dễ hiểu khi muốn xem một vài phần tử ưu tiên đầu tiên thay vì toàn bộ.

### 7.2. Sao chép sang List rồi sort bằng đúng comparator

Nếu đã biết comparator `order` đang dùng:

```java
// Đoạn lệnh minh họa; queue, order và kiểu Task đã được định nghĩa.
List<Task> ordered = new ArrayList<>(queue);
ordered.sort(order);
```

Danh sách riêng cho phép xếp mà không xóa dữ liệu khỏi hàng đợi. Cần giữ comparator của nghiệp vụ như một giá trị có thể dùng lại, thay vì viết một quy tắc tương tự ở nhiều chỗ rồi để chúng lệch nhau.

Với `PriorityQueue<Integer>` dùng thứ tự tự nhiên, có thể dùng:

```java
List<Integer> ordered = new ArrayList<>(queue);
ordered.sort(Comparator.naturalOrder());
```

Hai đoạn trên là những ngữ cảnh riêng; không khai báo cả hai biến `ordered` trong cùng một phạm vi.

### 7.3. Stream có sorted rõ ràng

Với comparator tường minh:

```java
List<Task> ordered = queue.stream()
        .sorted(order)
        .toList();
```

`sorted(order)` mới là bước yêu cầu thứ tự. `toList()` thu kết quả; nó không tự đọc comparator từ hàng đợi.

Nếu chỉ gọi `sorted()`, Java dùng thứ tự tự nhiên. Điều này có thể khác quy tắc của hàng đợi:

```java
// Đoạn lệnh minh họa:
PriorityQueue<Integer> highestFirst =
        new PriorityQueue<>(Comparator.reverseOrder());
highestFirst.addAll(List.of(8, 1, 5));

List<Integer> natural = highestFirst.stream().sorted().toList();
List<Integer> priority = highestFirst.stream()
        .sorted(Comparator.reverseOrder())
        .toList();

// natural  là [1, 5, 8]
// priority là [8, 5, 1]
// highestFirst.peek() vẫn là 8
```

Một kiểu đối tượng không triển khai `Comparable` còn có thể gây `ClassCastException` nếu yêu cầu sắp xếp tự nhiên thay vì cung cấp comparator phù hợp.

### 7.4. Nếu lấy comparator từ queue, phải xét null

`queue.comparator()` trả `null` khi hàng đợi dùng thứ tự tự nhiên. Không đưa thẳng giá trị này vào `stream.sorted(comparator)`: phương thức stream cần comparator không null.

Một cách an toàn, dễ đọc là phân nhánh theo ngữ cảnh kiểu phần tử hoặc giữ comparator tường minh ngay từ lúc tạo hàng đợi. Sao chép `PriorityQueue` rồi `poll()` cũng tránh phải tự viết lại logic chọn thứ tự tự nhiên hay comparator riêng.

Với `List.sort(null)`, hợp đồng lại là dùng thứ tự tự nhiên; xem [List.sort Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#sort(java.util.Comparator)). Không khái quát ý nghĩa `null` giữa các API chỉ vì cùng có thao tác sắp xếp.

## 8. Chương trình chạy: ba cách cho cùng kết quả

Lưu thành **PriorityOrderedViews.java**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.PriorityQueue;

public class PriorityOrderedViews {
    record Task(String label, int rank, long ticket) {
        @Override
        public String toString() {
            return label + ":" + rank + ":" + ticket;
        }
    }

    private static <E> List<E> pollCopy(PriorityQueue<E> source) {
        PriorityQueue<E> copy = new PriorityQueue<>(source);
        List<E> ordered = new ArrayList<>();
        E value;
        while ((value = copy.poll()) != null) {
            ordered.add(value);
        }
        return ordered;
    }

    public static void main(String[] args) {
        Comparator<Task> order =
                Comparator.comparingInt(Task::rank)
                          .reversed()
                          .thenComparingLong(Task::ticket);
        PriorityQueue<Task> queue = new PriorityQueue<>(order);
        queue.addAll(List.of(
                new Task("report", 2, 0),
                new Task("alert", 9, 1),
                new Task("repair", 9, 2),
                new Task("backup", 4, 3)));

        List<Task> byPolling = pollCopy(queue);
        List<Task> bySorting = new ArrayList<>(queue);
        bySorting.sort(order);
        List<Task> byStream = queue.stream().sorted(order).toList();

        System.out.println("copy plus poll: " + byPolling);
        System.out.println("list plus sort: " + bySorting);
        System.out.println("stream plus sorted: " + byStream);
        System.out.println("all equal: "
                + (byPolling.equals(bySorting) && bySorting.equals(byStream)));
        System.out.println("source size: " + queue.size());
        System.out.println("source head: " + queue.peek());

        PriorityQueue<Integer> duplicates =
                new PriorityQueue<>(List.of(5, 2, 5, 1));
        System.out.println("duplicates preserved: " + pollCopy(duplicates));
        System.out.println("duplicate source size: " + duplicates.size());
    }
}
```

Lệnh chạy:

```shell
javac --release 17 -encoding UTF-8 PriorityOrderedViews.java
java PriorityOrderedViews
```

Stdout chính xác:

```text
copy plus poll: [alert:9:1, repair:9:2, backup:4:3, report:2:0]
list plus sort: [alert:9:1, repair:9:2, backup:4:3, report:2:0]
stream plus sorted: [alert:9:1, repair:9:2, backup:4:3, report:2:0]
all equal: true
source size: 4
source head: alert:9:1
duplicates preserved: [1, 2, 5, 5]
duplicate source size: 4
```

Ở đây quy ước là `rank` lớn hơn đứng trước. Nếu cùng rank, `ticket` nhỏ hơn đứng trước. Vì vậy alert đứng trước repair, rồi backup và report.

Ba cách cùng trả kết quả giống nhau vì cùng dùng một thứ tự đủ phân biệt các tác vụ mẫu:

1. Bản sao PriorityQueue giữ comparator của nguồn rồi lấy đầu.
2. Danh sách riêng được xếp bằng comparator `order`.
3. Stream có `sorted(order)`.

Cả ba chỉ đọc cấu trúc nguồn. Kích thước vẫn là 4 và đầu vẫn là alert. Ví dụ số ở cuối giữ đủ cả hai số 5; không có bước biến dữ liệu thành tập hợp để làm mất lần xuất hiện.

`Stream.toList()` có từ trước Java 17 nên dùng được trong bài. Danh sách kết quả của phương thức đó không hỗ trợ thay đổi cấu trúc; hai danh sách tạo bằng `ArrayList` trong chương trình có khả năng sửa khác. Sự khác biệt này không ảnh hưởng đến phép so sánh nội dung đang thực hiện.

## 9. Hòa ưu tiên: sắp xếp đúng vẫn có thể khác thứ tự danh tính

### 9.1. Comparator bằng 0 chưa tạo quy tắc đến trước

Giả sử comparator chỉ xét mức ưu tiên. A và B có cùng mức 1. Khi lấy đầu, cả hai đều hợp lệ để được chọn trước phần tử mức 2, nhưng không có bảo đảm A phải được lấy trước B chỉ vì A được thêm trước.

Việc sắp xếp một bản danh sách cũng không tự khôi phục lịch sử thêm. Ngay cả một thuật toán sắp xếp ổn định cũng chỉ có thể giữ thứ tự đầu vào của những phần tử hòa; đầu vào được sao chép từ iterator vốn chưa có bảo đảm thứ tự đến.

Không dùng tính ổn định của sort để suy ra tính FIFO cho PriorityQueue.

### 9.2. Tiêu chí phụ phải là dữ liệu thật

Nếu cần FIFO trong từng nhóm ưu tiên, cấp số thứ tự nhận việc rồi ghép vào comparator, như trường `ticket` trong chương trình:

```java
Comparator.comparingInt(Task::rank)
          .reversed()
          .thenComparingLong(Task::ticket)
```

Đây là biểu thức trong ngữ cảnh kiểu `Task` đã định nghĩa. Số thứ tự phải diễn đạt đúng quy tắc của ứng dụng và đủ phân biệt các phần tử cần xếp. Nếu cả rank lẫn ticket vẫn hòa, vấn đề thứ tự giữa những phần tử đó vẫn chưa được giải quyết.

Tính duy nhất của ticket trong ví dụ là do ứng dụng cấp, không phải đặc tính tự có của PriorityQueue.

### 9.3. Đừng dùng TreeSet chỉ để làm một bản in đã xếp

Chuyển sang `TreeSet` có thể làm mất những phần tử mà comparator coi là tương đương. Với dữ liệu số `[5, 2, 5, 1]`, bản danh sách đã xếp giữ `[1, 2, 5, 5]`; một tập hợp chỉ giữ một giá trị 5.

Nếu yêu cầu là xem mọi công việc và mọi lần xuất hiện, chọn cấu trúc kết quả giữ được chúng. “Có thứ tự” không đủ nếu thao tác chuyển đổi còn thay đổi số lượng dữ liệu.

## 10. Chọn cách theo chi phí và tác động dữ liệu

Bảng sau xét n phần tử, comparator có chi phí hằng số, và không có nơi khác sửa dữ liệu trong quá trình đọc:

| Nhu cầu | Cách phù hợp | Tác động bản gốc | Chi phí chính |
| --- | --- | --- | --- |
| Đi qua mọi phần tử, không cần thứ tự | Iterator | Giữ nguyên nếu chỉ đọc | O(n) |
| Chỉ xem phần tử đầu ưu tiên | `peek()` | Giữ nguyên | O(1) |
| Lấy hết theo ưu tiên để xử lý | Lặp `poll()` | Bị rút cạn | O(n log n) |
| Xem toàn bộ theo ưu tiên | Sao chép rồi `poll()` | Giữ nguyên | O(n log n), thêm bộ nhớ |
| Xem toàn bộ theo ưu tiên trong danh sách | Sao chép rồi `sort` | Giữ nguyên | O(n log n), thêm bộ nhớ |
| Xem k phần tử tốt nhất | Sao chép rồi lấy tối đa k lần | Giữ nguyên | Chi phí sao chép cộng các lần lấy |

Với cách cài đặt thông thường của OpenJDK, sao chép một hàng đợi n phần tử cần O(n) thời gian và bộ nhớ; sau đó lấy k phần tử cần O(k log n). Vì thế không gọi toàn bộ cách “sao chép rồi lấy k” là O(k log n) mà bỏ qua bước sao chép.

Một vòng iterator chỉ đọc không cần tạo danh sách chứa toàn bộ n phần tử. Nếu muốn cộng một tổng, đếm hoặc tìm theo điều kiện mà không cần thứ tự, đừng bắt buộc sắp xếp chỉ vì dữ liệu đang ở PriorityQueue.

Ngược lại, một giao diện hiển thị theo ưu tiên phải có bước tạo thứ tự rõ ràng; không nên tối ưu bằng cách xóa mất yêu cầu rồi dùng iterator.

### Chỉ lấy vài phần tử đầu trên bản sao

Đoạn lệnh minh họa, `queue` là `PriorityQueue<Integer>` đã có dữ liệu và `k` là số không âm:

```java
PriorityQueue<Integer> copy = new PriorityQueue<>(queue);
List<Integer> first = new ArrayList<>();

for (int count = 0; count < k && !copy.isEmpty(); count++) {
    first.add(copy.poll());
}
```

Không dùng `queue.stream().limit(k)` rồi cho rằng đó là k phần tử ưu tiên nhất. `limit` không sắp xếp phần nguồn trước khi chọn.

## 11. Iterator chỉ đọc không phải bản chụp độc lập

### 11.1. Không trộn next với poll trên cùng hàng đợi

Ví dụ dễ sai:

```java
// Ví dụ sai về cách thay đổi nguồn trong khi đang duyệt:
Iterator<Integer> iterator = queue.iterator();
while (iterator.hasNext()) {
    System.out.println(iterator.next());
    queue.poll();
}
```

Iterator không có nghĩa “mỗi lần đọc rồi loại đầu thì tự cập nhật thành một lượt ưu tiên”. Việc sửa nguồn ngoài iterator làm lượt duyệt không còn tuân theo cách sử dụng bình thường. Có thể gặp `ConcurrentModificationException`; không dựa vào việc ngoại lệ có xuất hiện ở một lần chạy hay không để coi mã là đúng.

Nếu muốn lấy ưu tiên, dùng vòng `poll()` riêng. Nếu muốn vừa duyệt vừa xóa theo điều kiện, dùng cơ chế xóa được iterator hỗ trợ và hiểu rằng đó vẫn không tạo ra thứ tự ưu tiên.

Theo [hợp đồng Iterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Iterator.html#remove()), `remove()` của iterator xóa phần tử được `next()` trả gần nhất; nó không mang ý nghĩa “xóa đầu ưu tiên”. Với iterator hỗ trợ xóa, mỗi lần `next()` thành công cho tối đa một lần xóa tương ứng.

### 11.2. Bản sao cấu trúc vẫn có thể dùng chung đối tượng phần tử

`new PriorityQueue<>(queue)`, `new ArrayList<>(queue)` và stream trong ví dụ giữ các tham chiếu tới đối tượng phần tử. Chúng không tự sao chép sâu các đối tượng đó.

Thêm/xóa vào bản sao không thêm/xóa cấu trúc nguồn. Nhưng sửa một đối tượng thay đổi được đang được cả hai nơi tham chiếu vẫn có thể được quan sát từ cả hai nơi. Đặc biệt, sửa khóa ưu tiên có thể làm giả định thứ tự không còn đúng.

Các Task mẫu dùng trường kiểu nguyên thủy và String trong record để giữ khóa so sánh ổn định.

### 11.3. Sao chép không tự giải quyết truy cập đồng thời

PriorityQueue không an toàn cho việc nhiều luồng cùng truy cập khi có luồng sửa mà thiếu đồng bộ thích hợp. Một dòng tạo bản sao không tự tạo điểm chụp nguyên tử của một nguồn đang bị sửa.

Trong ứng dụng đồng thời, trước hết phải xác định cách có được một lần đọc hợp lệ theo thiết kế đồng bộ hoặc cấu trúc đang dùng. Sau đó mới chọn phương án sắp xếp/hiển thị. Các ví dụ trong bài được chạy trong một luồng với dữ liệu không bị sửa từ bên ngoài.

## 12. Kiểm thử đúng hợp đồng thay vì đóng đinh bố trí heap

### 12.1. Kiểm thử một lượt iterator chỉ đọc

Có thể kiểm tra các thuộc tính:

- Đọc đủ số lần xuất hiện mong đợi.
- Các giá trị và số lượng từng giá trị khớp nguồn.
- Kích thước và đầu không đổi sau khi chỉ đọc.
- Iterator hết phần tử đúng lúc; `next()` khi hết báo ngoại lệ theo hợp đồng.

Không nên viết kiểm thử sản phẩm yêu cầu một dãy iterator cụ thể như `[1, 4, 3, ...]` chỉ vì đã quan sát được dãy đó trên máy. Kiểm thử như vậy trói vào chi tiết bố trí thay vì yêu cầu nghiệp vụ.

Trong ví dụ quan sát, stdout ghi dãy thực tế để minh họa phản ví dụ. Nó không phải đề nghị dùng dãy đó làm một hợp đồng đa phiên bản.

### 12.2. Kiểm thử một danh sách được yêu cầu theo ưu tiên

Khi kiểm thử phương thức tạo danh sách theo ưu tiên, nên kiểm tra đồng thời:

1. Danh sách chứa đủ mọi lần xuất hiện.
2. Mỗi cặp phần tử liên tiếp không đi ngược comparator.
3. Nguồn được bảo toàn nếu hợp đồng là chỉ xem.
4. Quy tắc hòa được xác định nếu nghiệp vụ yêu cầu thứ tự danh tính cụ thể.

Không đổi cả hai phía thành `Set` để kiểm tra “cùng phần tử”, vì cách đó bỏ mất số lần xuất hiện. Sắp xếp các bản danh sách hoặc dùng bảng đếm phù hợp có thể giữ thông tin này.

Nếu comparator chỉ xét một phần dữ liệu và cho nhiều phần tử hòa, không buộc mọi phương án đúng phải trả cùng thứ tự danh tính. Muốn kiểm tra exact một thứ tự như chương trình Task, hãy có tiêu chí phụ đủ phân biệt trước.

## 13. Lỗi phổ biến và cách sửa

| Hiện tượng | Suy luận sai | Cách xử lý |
| --- | --- | --- |
| Iterator trả phần tử 4 trước 3 | Hàng đợi chắc đã hỏng | Kiểm tra đầu và hiểu bất biến heap |
| Vòng for không tăng dần | Đổi sang forEach sẽ sửa được | Thêm bước sort hoặc lấy đầu từ bản sao |
| In queue thấy dãy lộn xộn | toString phải in theo ưu tiên | Xem đó là hiển thị nội dung chưa có hợp đồng xếp |
| toArray vẫn không tăng dần | Chuyển sang mảng tự sắp xếp | Sắp xếp mảng hoặc danh sách theo quy tắc phù hợp |
| forEachOrdered chưa theo ưu tiên | Từ “Ordered” nghĩa là tự dùng comparator | Dùng sorted với comparator tường minh |
| Hàng đợi số lớn trước nhưng stream nhỏ trước | sorted() tự dùng thứ tự của queue | sorted() mặc định dùng thứ tự tự nhiên |
| Hiển thị làm mất công việc chờ | poll trên bản gốc khi chỉ muốn xem | Poll trên bản sao hoặc sort danh sách riêng |
| Hai việc hòa đổi vị trí | Sort ổn định phải khôi phục FIFO | Thêm số thứ tự nhận việc vào comparator |
| Một số việc biến mất sau khi đổi cấu trúc | Dùng TreeSet để xếp mọi lần xuất hiện | Dùng kết quả giữ trùng như List |
| Iterator kết hợp poll gặp lỗi | Tưởng iterator tự đồng bộ với lấy đầu | Chọn riêng lượt đọc hoặc lượt tiêu thụ |

## 14. Bài tập tự kiểm tra có lời giải

### Bài 1: Heap hay danh sách đã xếp?

Một heap có mảng mô hình `[1, 4, 3, 12, 7, 9, 6]`. Vì sao 4 đứng trước 3 vẫn hợp lệ?

**Lời giải:** 4 và 3 là hai con của 1. Min-heap chỉ yêu cầu 1 không lớn hơn mỗi con, không buộc con trái nhỏ hơn con phải. Đọc mảng theo chỉ số vì thế có thể gặp 4 trước 3.

### Bài 2: next và poll

Có hàng đợi số nguyên dùng thứ tự tự nhiên. Một vòng iterator và một vòng poll đều đọc bảy giá trị. Vòng nào phải cho dãy không giảm? Trạng thái hàng đợi sau mỗi vòng?

**Lời giải:** vòng poll cho dãy không giảm và lấy hết phần tử ra. Vòng iterator chỉ đọc giữ nguyên hàng đợi nhưng không có bảo đảm dãy không giảm. Hai vòng đều có thể đọc đủ phần tử mà khác cả thứ tự lẫn tác động dữ liệu.

### Bài 3: Hai phần tử đầu tiên

Muốn xem hai công việc ưu tiên nhất mà giữ nguyên nguồn. Có được dùng `queue.stream().limit(2).toList()` không?

**Lời giải:** cách đó chưa yêu cầu xếp theo ưu tiên, nên không bảo đảm chọn đúng hai phần tử cần xem. Có thể sao chép PriorityQueue rồi poll tối đa hai lần, hoặc sorted theo comparator trước khi limit. Phải xét cả chi phí tạo bản sao hoặc sắp xếp.

### Bài 4: Comparator đảo chiều

Hàng đợi chứa 8, 1, 5 và dùng `Comparator.reverseOrder()`. `queue.stream().sorted().toList()` trả gì? Có giống thứ tự poll không?

**Lời giải:** sorted() dùng thứ tự tự nhiên nên cho `[1, 5, 8]`. Poll theo quy tắc của hàng đợi cho `[8, 5, 1]`. Dùng sorted với comparator đảo chiều nếu muốn cùng thứ tự ưu tiên.

### Bài 5: Hòa ưu tiên và tính ổn định

A và B có cùng ưu tiên. Danh sách được tạo từ iterator rồi dùng sort ổn định. Có chứng minh được A đến trước sẽ đứng trước B không?

**Lời giải:** không. Sort ổn định giữ thứ tự đầu vào giữa các phần tử hòa, nhưng thứ tự iterator không cam kết lịch sử thêm. Cần dữ liệu thứ tự tiếp nhận và tiêu chí phụ phù hợp.

### Bài 6: Giữ các lần xuất hiện

Hàng đợi chứa `[5, 2, 5, 1]` xét theo các giá trị đang có. Hai kết quả `[1, 2, 5]` và `[1, 2, 5, 5]` đều đã xếp. Kết quả nào là bản xem đầy đủ đúng?

**Lời giải:** `[1, 2, 5, 5]`. Bản xem phải giữ cả hai lần xuất hiện của 5. Một kết quả có thứ tự nhưng thiếu dữ liệu vẫn sai yêu cầu.

### Bài 7: Một lần chạy đã xếp

Đầu vào nhỏ khiến iterator tình cờ trả `[1, 2, 3]`. Có thể bỏ bước sắp xếp trong chức năng hiển thị không?

**Lời giải:** không. Một quan sát không tạo ra bảo đảm thứ tự cho các dữ liệu hay bản cài đặt khác. Chức năng cần thứ tự phải thể hiện bằng thao tác có hợp đồng phù hợp.

### Bài 8: comparator null

Hàng đợi dùng thứ tự tự nhiên nên `queue.comparator()` là null. Gọi `queue.stream().sorted(queue.comparator())` có phải cách tổng quát đúng không?

**Lời giải:** không. Biến thể sorted nhận comparator cần đối số không null. Hãy xử lý trường hợp thứ tự tự nhiên rõ ràng hoặc sao chép PriorityQueue rồi lấy đầu trên bản sao.

## 15. Tài liệu đối chiếu

- [PriorityQueue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html): phân biệt hợp đồng đầu hàng đợi với hợp đồng duyệt.
- [Mã nguồn PriorityQueue OpenJDK 17u](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/PriorityQueue.java): xem cách tổ chức heap và đường đọc iterator thông thường.
- [Iterator Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Iterator.html): thao tác đọc, trạng thái hết phần tử và quy tắc xóa.
- [Stream Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html): phân biệt sorted, limit và forEachOrdered.

Khi cần thứ tự ưu tiên, hãy chọn thao tác thực sự tạo ra thứ tự đó. Tên PriorityQueue bảo đảm cách chọn đầu; iterator phục vụ việc đi qua nội dung và không tự thực hiện cả một lượt lấy đầu ưu tiên.
