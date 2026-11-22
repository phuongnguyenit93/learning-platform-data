# Thứ tự duyệt so với thứ tự lấy phần tử trong Queue và PriorityQueue

## 1. Duyệt nội dung và chọn phần tử tiếp theo là hai việc khác nhau

Khi sử dụng hàng đợi, có hai câu hỏi độc lập:

1. Nếu đi qua các phần tử bằng iterator, ta nhìn thấy chúng theo thứ tự nào?
2. Nếu liên tục lấy đầu bằng `poll()`, ta xử lý chúng theo thứ tự nào?

Với một FIFO cụ thể như `ArrayDeque` dùng qua thao tác hàng đợi, thứ tự duyệt từ đầu đến cuối có thể trùng với thứ tự lấy. Nhưng không được mang kết luận đó sang mọi cách triển khai `Queue`.

Điểm quan trọng với `PriorityQueue`:

- `peek()` và `element()` quan sát đầu theo quy tắc ưu tiên.
- `poll()` và `remove()` lấy và loại bỏ đầu theo quy tắc ấy.
- `iterator()` và spliterator không bảo đảm duyệt theo thứ tự ưu tiên.

[Tài liệu PriorityQueue](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/PriorityQueue.html) công bố giới hạn thứ tự duyệt này. Vì vậy, in một hàng đợi ra màn hình không phải bằng chứng rằng nó sẽ xử lý theo đúng dãy vừa in.

Bài dùng các API còn áp dụng hiện nay và mã Java 17+.

## 2. Cơ chế cần hiểu: heap không phải một danh sách đã sắp xếp

`PriorityQueue` dùng cấu trúc heap ưu tiên. Với heap nhỏ trước, quan hệ cần giữ là cha không lớn hơn các con theo quy tắc so sánh. Điều đó đủ để xác định phần tử nhỏ nhất ở đầu, nhưng không yêu cầu mọi vị trí trong cấu trúc đều nối thành một dãy tăng dần.

Một cấu hình heap nhỏ trước hợp lệ có thể là:

```text
          1
        /   \
       2     3
      / \   /
     7   5 9
```

Nhìn theo từng tầng trong hình ta thấy 1, 2, 3, 7, 5, 9. Dãy đó không tăng dần vì 7 đứng trước 5, nhưng không có mâu thuẫn: các quan hệ cha–con vẫn đúng.

Đây là hình minh họa một cấu hình hợp lệ, không phải hợp đồng rằng mọi JDK phải lưu và duyệt heap theo đúng hình.

Mỗi lần `poll()` lấy phần tử đầu, hàng đợi cập nhật lại cấu trúc để xác định đầu tiếp theo. Vì vậy, chuỗi các lần lấy có thể là 1, 2, 3, 5, 7, 9 dù một lượt duyệt cấu trúc hiện tại không hiện ra dãy đó.

Sự khác biệt nằm ở thao tác:

- **Duyệt:** lần lượt thăm các phần tử theo hợp đồng iterator.
- **Lấy đầu:** chọn phần tử phù hợp nhất hiện tại rồi thay đổi cấu trúc sau khi loại bỏ.

Không cần và không nên viết mã ứng dụng dựa vào bố cục heap nội bộ.

## 3. Những cách quan sát nào không tự sắp theo ưu tiên?

Đối với một `PriorityQueue`, các cách sau không tự tạo ra một dãy theo thứ tự ưu tiên:

```java
for (Integer value : queue) {
    System.out.println(value);
}

queue.forEach(System.out::println);
System.out.println(queue);
Object[] values = queue.toArray();
```

Đây là các mảnh minh họa, giả định đã có biến `queue`. Chúng không tương đương với việc liên tục gọi `poll()`.

| Cách đọc | Có loại bỏ phần tử? | Điều có thể dựa vào |
|---|---|---|
| `peek()` | Không | Đầu theo ưu tiên hoặc null nếu rỗng |
| `element()` | Không | Đầu theo ưu tiên; ném ngoại lệ nếu rỗng |
| `poll()` | Có | Lấy đầu theo ưu tiên |
| `remove()` không đối số | Có | Lấy đầu theo ưu tiên; ném ngoại lệ nếu rỗng |
| Iterator hoặc vòng `for` nâng cao | Không, nếu chỉ đọc | Không bảo đảm thứ tự ưu tiên của PriorityQueue |
| `toArray()` | Không | Bản chứa phần tử, không phải cam kết mảng đã sắp |
| `toString()` | Không | Biểu diễn nội dung, không phải lịch xử lý |
| Stream chưa `sorted` | Không, nếu mã xử lý không sửa nguồn | Không tự có thứ tự ưu tiên chỉ vì nguồn là PriorityQueue |

Một biến được khai báo kiểu `Queue<E>` cũng không bổ sung bảo đảm duyệt mà đối tượng thực tế không có. [Hợp đồng Queue](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Queue.html) định nghĩa đầu theo chính sách của từng cách triển khai.

## 4. Thí nghiệm: quan sát lượt duyệt và chuỗi poll

Lưu tệp `QueueTraversalObservation.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.PriorityQueue;

public class QueueTraversalObservation {
    public static void main(String[] args) {
        PriorityQueue<Integer> queue = new PriorityQueue<>();
        queue.addAll(List.of(7, 2, 9, 1, 5, 3));

        List<Integer> visited = new ArrayList<>();
        for (Integer value : queue) {
            visited.add(value);
        }
        System.out.println("iterator observed=" + visited);
        System.out.println("toString observed=" + queue);
        System.out.println("toArray observed=" + Arrays.toString(queue.toArray()));
        System.out.println("head=" + queue.peek() + ", size=" + queue.size());

        List<Integer> removed = new ArrayList<>();
        Integer value;
        while ((value = queue.poll()) != null) {
            removed.add(value);
        }
        System.out.println("poll order=" + removed);
        System.out.println("remaining=" + queue.size());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all -Werror QueueTraversalObservation.java
java QueueTraversalObservation
```

Kết quả đã quan sát trên JDK 21.0.9:

```text
iterator observed=[1, 2, 3, 7, 5, 9]
toString observed=[1, 2, 3, 7, 5, 9]
toArray observed=[1, 2, 3, 7, 5, 9]
head=1, size=6
poll order=[1, 2, 3, 5, 7, 9]
remaining=0
```

Ba dòng có chữ `observed` chỉ ghi lại cách lần chạy này duyệt hoặc trình bày nội dung. **Không dùng chúng làm kết quả bắt buộc cho mọi phiên bản hay cách triển khai.** Nếu một môi trường khác in dãy khác ở các dòng đó, điều cần kiểm tra là hợp đồng API, không phải ép hàng đợi về bố cục vừa quan sát.

Phần có thể dựa vào với các giá trị số nguyên khác nhau, thứ tự tự nhiên và không có thay đổi đồng thời là:

- Đầu hàng đợi là 1.
- Trước khi lấy, kích thước là 6.
- Liên tục `poll()` tạo dãy 1, 2, 3, 5, 7, 9.
- Sau khi lấy hết, kích thước là 0.

Phần duyệt không làm mất dữ liệu. Phần `poll` tiêu thụ dữ liệu; đây là một tác dụng cần được chủ động lựa chọn.

Nếu đầu ra duyệt tình cờ đã tăng dần với một bộ dữ liệu nhỏ, nó vẫn không chứng minh iterator có bảo đảm sắp xếp. Một thí nghiệm thuận lợi không thay thế hợp đồng.

## 5. Muốn xem theo ưu tiên nhưng giữ nguyên hàng đợi

Có hai hướng thông dụng:

### Cách 1: sao chép sang danh sách rồi sắp xếp

```java
List<Integer> snapshot = new ArrayList<>(source);
snapshot.sort(source.comparator());
```

Đây là mảnh mã với `source` có kiểu `PriorityQueue<Integer>`.

`new ArrayList<>(source)` mới chỉ sao chép phần tử; bản thân bước đó chưa tạo thứ tự ưu tiên. `sort` mới sắp xếp bản chụp theo comparator của nguồn.

Nếu `source.comparator()` trả null, nguồn đang dùng thứ tự tự nhiên; `List.sort(null)` cũng sử dụng thứ tự tự nhiên. Đó là ý nghĩa có chủ đích của null ở tham số comparator, không phải một phần tử null của hàng đợi.

Cách này tạo danh sách có thể duyệt nhiều lần mà không sửa cấu trúc hàng đợi gốc.

### Cách 2: tạo PriorityQueue bản sao rồi poll trên bản sao

```java
PriorityQueue<Integer> copy = new PriorityQueue<>(source);
Integer value;
while ((value = copy.poll()) != null) {
    System.out.println(value);
}
```

Constructor nhận `PriorityQueue` giữ quy tắc so sánh của nguồn. Vòng lặp chỉ làm rỗng bản sao.

Điểm quan trọng: **sao chép thành một PriorityQueue không làm iterator của bản sao trở thành iterator đã sắp xếp**. Muốn lấy theo ưu tiên, vẫn phải gọi `poll()` trên bản sao.

Hai cách đều sao chép các tham chiếu phần tử, không tự sao chép sâu đối tượng bên trong. Nếu phần tử có thuộc tính thay đổi, cần xem xét nó có ảnh hưởng tới dữ liệu quan sát và quy tắc so sánh hay không.

## 6. Chương trình so sánh bản chụp, bản sao và comparator

Lưu tệp `QueueOrderedViewDemo.java`:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.PriorityQueue;

public class QueueOrderedViewDemo {
    static <E> List<E> drain(PriorityQueue<E> queue) {
        List<E> result = new ArrayList<>();
        E item;
        while ((item = queue.poll()) != null) {
            result.add(item);
        }
        return result;
    }

    public static void main(String[] args) {
        PriorityQueue<Integer> source =
                new PriorityQueue<>(Comparator.reverseOrder());
        source.addAll(List.of(8, 3, 6, 1));

        List<Integer> snapshot = new ArrayList<>(source);
        snapshot.sort(source.comparator());
        System.out.println("sorted snapshot=" + snapshot);
        System.out.println("poll copy=" + drain(new PriorityQueue<>(source)));

        PriorityQueue<Integer> rebuiltFromList =
                new PriorityQueue<>(new ArrayList<>(source));
        System.out.println("rebuilt from list=" + drain(rebuiltFromList));
        System.out.println("stream natural=" + source.stream().sorted().toList());
        System.out.println("stream comparator="
                + source.stream().sorted(source.comparator()).toList());
        System.out.println("source size=" + source.size()
                + ", head=" + source.peek());
    }
}
```

Chạy:

```shell
javac --release 17 -Xlint:all -Werror QueueOrderedViewDemo.java
java QueueOrderedViewDemo
```

Stdout:

```text
sorted snapshot=[8, 6, 3, 1]
poll copy=[8, 6, 3, 1]
rebuilt from list=[1, 3, 6, 8]
stream natural=[1, 3, 6, 8]
stream comparator=[8, 6, 3, 1]
source size=4, head=8
```

### Bản chụp và bản sao giữ quy tắc nguồn

Nguồn dùng `Comparator.reverseOrder()`, nên số lớn được xếp trước theo quy tắc của hàng đợi.

- Danh sách được sắp bằng `source.comparator()` cho 8, 6, 3, 1.
- Bản sao `new PriorityQueue<>(source)`, khi được lấy bằng `poll()`, cũng cho 8, 6, 3, 1.
- Nguồn vẫn có 4 phần tử và đầu vẫn là 8.

### Đi qua ArrayList có thể làm mất thông tin comparator

Đoạn:

```java
new PriorityQueue<>(new ArrayList<>(source))
```

tạo hàng đợi mới từ một `ArrayList`. Danh sách không mang comparator của `PriorityQueue` nguồn. Với các số nguyên trong chương trình, hàng đợi mới dùng thứ tự tự nhiên và lấy ra 1, 3, 6, 8.

Đây là lý do không được thay tùy ý đường sao chép rồi kỳ vọng quy tắc ưu tiên vẫn giữ nguyên.

Đừng rút gọn thành kết luận “mọi constructor nhận `Collection` đều bỏ comparator”. Constructor `PriorityQueue(Collection)` có quy tắc riêng khi đối tượng collection nguồn là `PriorityQueue` hoặc `SortedSet`. Trong thí nghiệm, đối tượng nguồn trực tiếp của constructor là một `ArrayList`, nên trường hợp đó không giữ thông tin so sánh từ hàng đợi ban đầu.

### Stream cần được sắp xếp tường minh

`source.stream().sorted()` sử dụng thứ tự tự nhiên, vì vậy chương trình in tăng dần. Nó không tự kế thừa comparator đảo thứ tự của hàng đợi.

`source.stream().sorted(source.comparator())` sử dụng comparator đã cung cấp, nên chương trình in giảm dần. Với nguồn dùng thứ tự tự nhiên và `comparator() == null`, dùng `sorted()` hoặc chọn comparator tự nhiên phù hợp; không truyền null vào overload `Stream.sorted(Comparator)`.

Phân biệt:

- `List.sort(null)` có ý nghĩa dùng thứ tự tự nhiên.
- `Stream.sorted(null)` không có quy ước đó.

Các overload `sorted` có hợp đồng riêng trong [tài liệu Stream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Stream.html#sorted(java.util.Comparator)).

Sau khi đã sắp stream, nếu xử lý bằng một pipeline song song, `forEach` không phải cách yêu cầu giữ thứ tự gặp của các lần gọi xử lý. Có thể thu về một danh sách có thứ tự như ví dụ hoặc dùng `forEachOrdered` khi thật sự cần. Đây là một lớp quy tắc của stream, độc lập với việc `PriorityQueue` chọn đầu.

## 7. Phần tử ngang mức ưu tiên cần tiêu chí phụ

Khi comparator xem hai phần tử bằng nhau, `PriorityQueue` không bảo đảm FIFO giữa chúng. Vì thế, hai cách quan sát hợp lệ có thể đều tuân theo ưu tiên nhưng khác thứ tự các đối tượng ngang mức.

Một bản sắp xếp ổn định trên dữ liệu được duyệt từ hàng đợi cũng không tự khôi phục thứ tự thêm ban đầu. Nó chỉ giữ thứ tự đầu vào của những phần tử bằng nhau; thứ tự đầu vào ấy vốn không phải lịch sử thêm đã được hàng đợi cam kết.

Nếu cần thứ tự có thể dự đoán giữa các công việc cùng độ khẩn cấp, hãy lưu một tiêu chí phụ và đưa nó vào comparator.

Lưu tệp `QueueTieOrderDemo.java`:

```java
import java.util.Comparator;
import java.util.List;
import java.util.PriorityQueue;

public class QueueTieOrderDemo {
    record Request(String id, int urgency, long arrival) {
    }

    public static void main(String[] args) {
        Comparator<Request> order = Comparator.comparingInt(Request::urgency)
                .reversed()
                .thenComparingLong(Request::arrival);
        PriorityQueue<Request> requests = new PriorityQueue<>(order);
        requests.addAll(List.of(
                new Request("R3", 4, 3),
                new Request("R1", 4, 1),
                new Request("R2", 1, 2)));

        System.out.println("ordered snapshot=" + requests.stream()
                .sorted(order).map(Request::id).toList());

        PriorityQueue<Request> copy = new PriorityQueue<>(requests);
        Request request;
        while ((request = copy.poll()) != null) {
            System.out.println("next=" + request.id());
        }
        System.out.println("original size=" + requests.size());
    }
}
```

Chạy:

```shell
javac --release 17 -Xlint:all -Werror QueueTieOrderDemo.java
java QueueTieOrderDemo
```

Kết quả:

```text
ordered snapshot=[R1, R3, R2]
next=R1
next=R3
next=R2
original size=3
```

Comparator có hai mức:

1. `urgency` lớn hơn được xếp trước.
2. Cùng `urgency`, `arrival` nhỏ hơn được xếp trước.

Dù R3 được thêm trước R1 trong danh sách thử nghiệm, tiêu chí `arrival` quy định R1 đứng trước R3. Giá trị thứ tự đến là dữ liệu nghiệp vụ được cấp rõ ràng, không phải thứ mà iterator đoán lại từ cấu trúc heap.

Trong ví dụ, tiêu chí phụ phân biệt các yêu cầu ngang độ khẩn cấp nên bản chụp đã sắp và chuỗi `poll` của bản sao cho cùng dãy mã yêu cầu. Nếu cả các tiêu chí phụ vẫn bằng nhau, cần chấp nhận thứ tự hòa không được xác định hoặc bổ sung quy tắc phù hợp.

## 8. Duyệt và sửa hàng đợi trong cùng lúc

Không kết hợp một iterator đang chạy với thao tác `poll()` trực tiếp trên cùng `PriorityQueue` rồi dựa vào kết quả:

```java
// Ví dụ cách làm cần tránh:
for (Integer value : queue) {
    queue.poll();
}
```

Vòng `for` nâng cao dùng iterator, còn `poll` thay đổi cấu trúc ở ngoài iterator đó. Điều này có thể dẫn đến `ConcurrentModificationException`; cơ chế phát hiện sửa đổi không phải giao thức bảo đảm xử lý đúng.

Nếu mục tiêu là tiêu thụ theo ưu tiên, dùng một vòng `poll` riêng. Nếu mục tiêu là chỉ đọc một bản xem đã sắp, tạo bản chụp rồi duyệt bản chụp. Nếu cần loại bỏ có điều kiện qua iterator, phải theo hợp đồng iterator và vẫn không suy ra thứ tự ưu tiên từ lượt duyệt đó.

`PriorityQueue` không tự an toàn cho nhiều luồng sửa dữ liệu đồng thời. Việc tạo bản sao hoặc danh sách từ một nguồn đang bị sửa cũng không tự tạo ra một bản chụp nguyên tử. Cần một cách phối hợp phù hợp với toàn bộ luồng truy cập; không dùng ngoại lệ fail-fast làm điều kiện đúng đắn của chương trình.

Các ví dụ trong bài chạy trong một luồng, không thay đổi nguồn ở nơi khác trong lúc đọc hoặc sao chép.

## 9. Chọn thao tác theo mục tiêu

| Mục tiêu | Cách thực hiện phù hợp |
|---|---|
| Xem công việc ưu tiên kế tiếp | `peek()` hoặc `element()` |
| Lấy và xử lý công việc kế tiếp | `poll()` hoặc `remove()` không đối số |
| Tiêu thụ hết theo ưu tiên | Lặp lấy đầu trên chính hàng đợi |
| Kiểm tra có những phần tử nào, không cần thứ tự | Duyệt trực tiếp theo hợp đồng iterator |
| Hiển thị theo ưu tiên, giữ nguyên hàng đợi | Sắp xếp một bản chụp với comparator phù hợp |
| Mô phỏng chuỗi lấy, giữ nguyên hàng đợi | Sao chép PriorityQueue giữ comparator rồi lặp `poll` trên bản sao |
| Giữ thứ tự xác định giữa các phần tử ngang ưu tiên | Lưu tiêu chí phụ và đưa vào comparator |
| Chứng minh lịch xử lý | Kiểm tra chuỗi lấy đầu hoặc bản sắp theo hợp đồng; không dựa vào chuỗi in heap |

Bản chụp đã sắp chỉ mô tả các phần tử hiện tại theo một quy tắc so sánh. Nếu sau đó có phần tử mới được thêm, ưu tiên bị cập nhật hoặc dữ liệu thay đổi, bản chụp cũ không tự trở thành lịch xử lý tương lai.

## 10. Tự kiểm tra

### Câu 1

Một `PriorityQueue<Integer>` có `peek() == 1`, nhưng in ra dãy không tăng dần. Có thể kết luận hàng đợi sai không?

**Đáp án:** Không. Cần kiểm tra hợp đồng chọn đầu và các lần lấy. Thứ tự duyệt không được bảo đảm là thứ tự ưu tiên.

### Câu 2

`new ArrayList<>(queue)` có tạo sẵn danh sách theo thứ tự ưu tiên không?

**Đáp án:** Không. Bước này sao chép phần tử theo lượt duyệt nguồn. Muốn sắp theo ưu tiên, còn phải áp dụng comparator phù hợp.

### Câu 3

Tạo `new PriorityQueue<>(queue)` rồi dùng vòng `for` có giải quyết vấn đề thứ tự duyệt không?

**Đáp án:** Không. Bản sao vẫn có hợp đồng iterator của PriorityQueue. Cần `poll` trên bản sao hoặc sắp xếp một bản chụp.

### Câu 4

Nguồn dùng comparator đảo thứ tự. `queue.stream().sorted()` có tự dùng comparator đó không?

**Đáp án:** Không. `sorted()` dùng thứ tự tự nhiên; muốn cùng quy tắc nguồn phải dùng comparator phù hợp ở overload nhận comparator.

### Câu 5

Hai công việc cùng mức ưu tiên sẽ được `poll` theo thứ tự thêm vì `List.sort` ổn định: lập luận này đúng không?

**Đáp án:** Không. Tính ổn định của phép sắp danh sách không thay hợp đồng hòa của hàng đợi và không khôi phục lịch sử thêm từ lượt duyệt không có bảo đảm ấy.

Khi nhìn một dãy phần tử, hãy hỏi **dãy này đến từ iterator, bản chụp đã sắp hay chuỗi lấy đầu → comparator nào được dùng → nguồn có bị tiêu thụ không → phần tử hòa được phân định thế nào**. Những câu hỏi đó xác định chính xác điều mà đầu ra đang chứng minh.
