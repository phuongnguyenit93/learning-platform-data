# ArrayBlockingQueue so với LinkedBlockingQueue

## 1. Cùng phối hợp sản xuất–tiêu thụ, khác cách lưu trữ và phối hợp bên trong

Trong một quy trình nhiều luồng, bên sản xuất tạo công việc rồi đặt vào hàng đợi; bên tiêu thụ lấy công việc ra để xử lý. Khi tốc độ hai bên khác nhau, hàng đợi giữ phần công việc đang chờ và tạo một nơi áp dụng chính sách khi chưa có dữ liệu hoặc không còn chỗ.

`ArrayBlockingQueue<E>` và `LinkedBlockingQueue<E>` đều thực hiện vai trò đó qua giao diện `BlockingQueue<E>`. Cả hai là hàng đợi FIFO: thêm ở cuối, lấy ở đầu. Cả hai có thể dùng với nhiều bên sản xuất và nhiều bên tiêu thụ.

Sự khác biệt quan trọng nằm ở ba câu hỏi:

1. Dung lượng được chọn và giới hạn thế nào?
2. Các tham chiếu đến phần tử được chứa trong mảng hay các nút liên kết?
3. Các thao tác thêm và lấy phối hợp bằng cơ chế khóa nào?

Các khác biệt ấy ảnh hưởng đến cách cấp phát bộ nhớ, tranh chấp và hiệu năng. Chúng không làm cho hợp đồng `put`, `take` hoặc timeout biến thành một bộ API khác.

Vì vậy, cần học theo hai lớp: hiểu hành vi chung để viết quy trình đúng, rồi hiểu đánh đổi của từng cài đặt để chọn và đo. Đừng chọn chỉ vì “mảng nhanh hơn” hoặc “hai khóa chắc chắn nhanh hơn một khóa”.

Bài này dùng Java 17 trở lên. Ba chương trình độc lập dưới đây đều có tên tệp, lệnh biên dịch và stdout. Các chương trình kiểm chứng hành vi và cách dùng chung giao diện; chúng không phải phép đo hiệu năng.

## 2. Bảng so sánh để xác định điều phải xem xét

| Khía cạnh | ArrayBlockingQueue | LinkedBlockingQueue |
|---|---|---|
| Cấu trúc chứa phần tử | Mảng tham chiếu có kích thước cố định | Các nút liên kết chứa tham chiếu |
| Dung lượng khi tạo | Phải chỉ định dung lượng | Có thể chỉ định; mặc định là `Integer.MAX_VALUE` |
| Dung lượng sau khi tạo | Không tự thay đổi | Giới hạn đã chọn cũng không tự thay đổi |
| Thứ tự phần tử | FIFO | FIFO |
| Tùy chọn công bằng qua constructor | Có cờ `fair` | Không có cờ tương ứng |
| Cấp phát cấu trúc chứa | Mảng được tạo trước theo dung lượng | Nút được cấp phát trong quá trình đưa phần tử |
| Phối hợp thêm/lấy trong OpenJDK 17 | Một khóa chính, hai điều kiện chờ | Khóa thêm và khóa lấy riêng, cùng phối hợp số đếm |
| Kết luận về tốc độ | Cần đo trên tải phù hợp | Cần đo trên tải phù hợp |

Các điểm về cấu trúc khóa ở đây mô tả cài đặt OpenJDK 17; phần dung lượng, FIFO và constructor là điều người dùng đọc qua hợp đồng API. Xem [ArrayBlockingQueue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html) và [LinkedBlockingQueue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/LinkedBlockingQueue.html).

“Linked” không có nghĩa dung lượng sẽ tự tăng không giới hạn nếu ứng dụng đã truyền giới hạn cụ thể. “Array” cũng không có nghĩa ứng dụng được truy cập vị trí bên trong như một danh sách đánh chỉ số. Cả hai vẫn được sử dụng như hàng đợi.

Trong phần còn lại, cần tách các thuộc tính dễ bị trộn:

- **Dung lượng:** tối đa bao nhiêu phần tử được hàng đợi giữ.
- **Số phần tử hiện có:** trạng thái tại một lần quan sát.
- **Bộ nhớ thực dùng:** gồm cấu trúc hàng đợi, dữ liệu phần tử và các tham chiếu khác còn giữ.
- **Khả năng xử lý:** tốc độ và độ trễ của cả quy trình.

Một thay đổi ở một thuộc tính chưa chứng minh các thuộc tính còn lại sẽ tốt hơn.

## 3. Dung lượng: khác biệt constructor có thể đổi chính sách vận hành

### 3.1. Khi cùng đặt giới hạn, cả hai đều là hàng đợi có giới hạn

Hai cách tạo sau đều chọn tối đa 100 phần tử được xếp hàng:

```java
// Mã minh họa trong một phương thức, chưa phải chương trình độc lập.
BlockingQueue<Job> array = new ArrayBlockingQueue<>(100);
BlockingQueue<Job> linked = new LinkedBlockingQueue<>(100);
```

Nếu đầy, `put` có thể chờ chỗ. Nếu không muốn chờ điều kiện đầy/rỗng, dùng `offer` hoặc `poll` và xử lý kết quả. Dạng có timeout cho phép chờ theo chính sách của bên gọi.

Dung lượng phải dương khi dùng các constructor có tham số dung lượng của hai lớp này. Không chọn dung lượng 0 để biểu diễn một cơ chế chuyển giao không có vùng đệm; đó là một yêu cầu khác với hai cấu trúc đang so sánh.

### 3.2. LinkedBlockingQueue mặc định chưa tạo một giới hạn nhỏ hữu ích

Cách tạo không tham số của `LinkedBlockingQueue` dùng `Integer.MAX_VALUE`. Con số ấy không phải lời hứa có đủ bộ nhớ để chứa hơn hai tỷ công việc. Tài nguyên có thể cạn trước rất nhiều.

Nếu thay một hàng đợi dung lượng 100 bằng `new LinkedBlockingQueue<>()`, ứng dụng đã đổi cả giới hạn chấp nhận công việc, không chỉ đổi cách lưu trữ. Bên sản xuất có thể tiếp tục gửi trong lúc bên tiêu thụ chậm, làm số công việc chờ và thời gian chờ tăng lên.

Vì vậy, trước khi nói về bộ nhớ hoặc tốc độ, phải kiểm tra constructor thật sự được gọi.

### 3.3. Chương trình đối chiếu dung lượng và thứ tự

Tệp `QueueCapacityComparisonDemo.java`:

```java
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;

public class QueueCapacityComparisonDemo {
    static void inspect(String label, BlockingQueue<Integer> queue) {
        boolean first = queue.offer(10);
        boolean second = queue.offer(20);
        boolean third = queue.offer(30);
        System.out.println(label + ": offers=" + first + "," + second + "," + third
                + "; remaining=" + queue.remainingCapacity());
        System.out.println(label + ": poll=" + queue.poll() + ","
                + queue.poll() + "," + queue.poll());
    }

    public static void main(String[] args) {
        inspect("array-2", new ArrayBlockingQueue<>(2));
        inspect("linked-2", new LinkedBlockingQueue<>(2));

        var defaultLinked = new LinkedBlockingQueue<Integer>();
        System.out.println("defaultLinkedInitial=" +
                defaultLinked.remainingCapacity());
        defaultLinked.offer(99);
        System.out.println("defaultLinkedAfterOne=" +
                defaultLinked.remainingCapacity());

        List<Integer> seed = List.of(10, 20);
        var seededArray = new ArrayBlockingQueue<Integer>(2, false, seed);
        var seededLinked = new LinkedBlockingQueue<Integer>(seed);
        System.out.println("seededArrayRemaining=" +
                seededArray.remainingCapacity());
        System.out.println("seededLinkedRemaining=" +
                seededLinked.remainingCapacity());
        System.out.println("seededArrayOffer30=" + seededArray.offer(30));
        System.out.println("seededLinkedOffer30=" + seededLinked.offer(30));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 QueueCapacityComparisonDemo.java
java QueueCapacityComparisonDemo
```

Stdout:

```text
array-2: offers=true,true,false; remaining=0
array-2: poll=10,20,null
linked-2: offers=true,true,false; remaining=0
linked-2: poll=10,20,null
defaultLinkedInitial=2147483647
defaultLinkedAfterOne=2147483646
seededArrayRemaining=0
seededLinkedRemaining=2147483645
seededArrayOffer30=false
seededLinkedOffer30=true
```

Hai lời gọi `inspect` đầu cùng dùng dung lượng 2. Cả hai nhận 10, 20, từ chối 30 bằng `false`, rồi lấy ra 10, 20 theo FIFO. Sau hai lần lấy, lần `poll` thứ ba trả `null`.

Phần `defaultLinked` chỉ thêm đúng một phần tử. Chương trình không thử lấp đầy giới hạn mặc định. Các số lớn được in là giới hạn số lượng còn lại theo API, không phải lượng bộ nhớ còn dùng được.

### 3.4. Constructor nhận collection không có nghĩa lấy size làm capacity

Một lỗi thay thế dễ bỏ sót là cho rằng khởi tạo `LinkedBlockingQueue` từ collection hai phần tử sẽ tạo dung lượng 2. Thực tế, constructor này cũng dùng giới hạn `Integer.MAX_VALUE` rồi nạp nội dung ban đầu.

Trong chương trình:

- `seededArray` được chỉ định dung lượng 2 và nạp đủ hai phần tử, nên không nhận thêm 30 bằng `offer`.
- `seededLinked` nhận cùng collection ban đầu nhưng giới hạn không phải 2, nên nhận thêm 30.

Để giữ giới hạn mong muốn khi khởi tạo dữ liệu cho một hàng đợi liên kết, có thể tạo bằng constructor dung lượng rồi nạp dữ liệu theo quy trình phù hợp. Việc nạp cũng phải kiểm tra số phần tử và chính sách khi đầy.

Đừng thay constructor trong một lần đổi lớp mà bỏ qua sự khác biệt này; đây có thể là thay đổi hành vi quan trọng hơn cả chênh lệch hiệu năng.

## 4. Mảng vòng và nút liên kết: hiểu đúng chi phí bộ nhớ

### 4.1. ArrayBlockingQueue giữ một mảng tham chiếu

Mô hình khái niệm của hàng đợi mảng:

```text
Các ô của một mảng đã được tạo trước
    [ tham chiếu ][ tham chiếu ][ ô trống ][ ô trống ]

Vị trí lấy và vị trí thêm di chuyển trong mảng.
Đi đến cuối thì quay lại đầu để tái sử dụng ô trống.
```

Đây là mảng chứa tham chiếu tới đối tượng, không phải một vùng đã cấp phát sẵn mọi đối tượng công việc. Tạo hàng đợi dung lượng 1.000 chưa tạo 1.000 đối tượng `Job`.

Các ô được tái sử dụng khi phần tử được lấy ra. Đường thêm/lấy thông thường không cần tạo một nút liên kết mới cho mỗi phần tử. Tuy nhiên, không được biến điều đó thành câu “mọi lời gọi đều không cấp phát gì”: ứng dụng vẫn có thể tạo công việc, dùng iterator hoặc gọi thao tác trả bản sao dữ liệu.

Khi chọn dung lượng rất lớn, mảng tham chiếu được tạo trước cũng là một khoản bộ nhớ phải chấp nhận ngay, kể cả khi hàng đợi phần lớn rỗng.

### 4.2. LinkedBlockingQueue giữ chuỗi nút

Mô hình khái niệm của hàng đợi liên kết:

```text
Đầu → [ nút: tham chiếu A ] → [ nút: tham chiếu B ] → Cuối

Mỗi nút mang liên kết đến nút tiếp theo.
Đối tượng A, B vẫn là dữ liệu riêng ở bên ngoài nút.
```

Trong OpenJDK 17, nút chứa trường phần tử và trường nối đến nút kế tiếp. Dung lượng là một giới hạn số lượng; không có một mảng tham chiếu dài bằng giới hạn đó được tạo trước. Nút được cấp phát theo đường thêm dữ liệu. Xem [cài đặt LinkedBlockingQueue của OpenJDK 17](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/concurrent/LinkedBlockingQueue.java).

Điều này tạo ra một đánh đổi cần đo: không phải trả trước cho một mảng dài bằng dung lượng, nhưng có thêm các đối tượng nút và hoạt động cấp phát/thu hồi trong quá trình sử dụng.

Không gán một số byte cố định cho mỗi nút trên mọi JVM. Kích thước đối tượng, căn chỉnh và cách biểu diễn tham chiếu phụ thuộc cấu hình máy ảo.

### 4.3. So sánh cấu trúc rỗng và cấu trúc gần đầy là hai tình huống khác

Nếu dung lượng chọn rất lớn nhưng mức chiếm dụng thường nhỏ, mảng được cấp phát trước có thể đáng kể. Nếu hàng đợi liên tục giữ nhiều phần tử hoặc luân chuyển rất nhanh, chi phí nút và thu hồi bộ nhớ của cách liên kết lại cần được xem xét.

Đó là các tình huống suy luận để đặt giả thuyết đo, không phải kết luận một bên luôn ít bộ nhớ hơn ở mọi trạng thái.

Cũng phải tính dữ liệu mà từng phần tử giữ. Một công việc mang ảnh, bộ đệm lớn hoặc một đồ thị đối tượng có thể chiếm phần lớn bộ nhớ, vượt xa chi phí ô tham chiếu hay nút hàng đợi.

Một ô mảng trống không tạo ra công việc, còn một tham chiếu trong hàng đợi có thể giữ cả dữ liệu lớn sống lâu hơn mong muốn.

### 4.4. Capacity chưa là giới hạn toàn bộ bộ nhớ của quy trình

Dung lượng giới hạn số phần tử đã xếp trong hàng đợi. Nó không giới hạn số luồng đang bị giữ, số đối tượng mà bên sản xuất đã tạo trước khi gửi, hoặc công việc đã được bên tiêu thụ lấy ra nhưng chưa xử lý xong.

Ví dụ suy luận: hàng đợi có dung lượng 100 nhưng hàng nghìn tác vụ sản xuất mỗi tác vụ đã tạo một công việc lớn rồi gọi `put`. Các công việc đang nằm ngoài hàng đợi mà tác vụ còn giữ cũng dùng bộ nhớ.

Tương tự, nhiều bên tiêu thụ có thể cùng giữ công việc đang xử lý. Chỉ quan sát `queue.size()` không cho biết tổng số công việc chưa hoàn tất.

Khi đặt mục tiêu giới hạn bộ nhớ hoặc số công việc đang hoạt động, cần định nghĩa ranh giới đầy đủ của quy trình. Hai hàng đợi không tự quản lý mọi đối tượng ngoài phần tử đã xếp của mình.

## 5. Một khóa và hai khóa: khác biệt tạo cơ hội, không tạo bảo đảm tốc độ

### 5.1. ArrayBlockingQueue phối hợp qua một khóa chính

Trong OpenJDK 17, `ArrayBlockingQueue` bảo vệ trạng thái mảng, số đếm và vị trí thêm/lấy bằng một `ReentrantLock` chính. Nó có hai điều kiện `notEmpty` và `notFull` để chờ dữ liệu hoặc chờ chỗ. Xem [cài đặt ArrayBlockingQueue của OpenJDK 17](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/concurrent/ArrayBlockingQueue.java).

Mô hình để hình dung:

```text
Thêm  → khóa chính → cập nhật mảng/số đếm → nhả khóa
Lấy   → khóa chính → cập nhật mảng/số đếm → nhả khóa

Rỗng/đầy → chờ điều kiện phù hợp
```

Một khóa chính không có nghĩa một luồng `take` đang chờ rỗng sẽ giữ khóa mãi khiến bên sản xuất không vào được. Cơ chế chờ điều kiện phải cho phép bên khác thay đổi điều kiện.

Nó cũng không có nghĩa toàn bộ xử lý công việc của người dùng nằm bên trong khóa hàng đợi. Sau khi `take` trả phần tử, mã xử lý riêng của ứng dụng không tự bị gói trong vùng khóa nội bộ đó.

### 5.2. LinkedBlockingQueue tách đường thêm và đường lấy

Trong cài đặt OpenJDK 17, `LinkedBlockingQueue` có khóa riêng cho bên thêm và bên lấy, cùng số đếm nguyên tử để phối hợp. Một số thao tác cần phối hợp cả hai phía. Đây là chi tiết cài đặt giúp giải thích khả năng chồng lấp một số hoạt động, không phải API khóa để ứng dụng dựa vào.

```text
Thêm → khóa thêm → cập nhật phía cuối
                    ↕ phối hợp số đếm và tín hiệu
Lấy  → khóa lấy  → cập nhật phía đầu
```

Các bên sản xuất vẫn có thể tranh chấp cùng khóa thêm. Các bên tiêu thụ vẫn có thể tranh chấp cùng khóa lấy. Hai phía cũng không hoàn toàn độc lập vì phải chia sẻ trạng thái và đánh thức đúng bên đang chờ.

Vì vậy, hai khóa không có nghĩa mọi `put` và `take` luôn chạy song song, càng không có nghĩa thông lượng phải gấp đôi. Các thao tác như xóa tùy ý, tạo một số dạng kết quả quan sát hoặc xử lý hàng loạt có thể có đường phối hợp khác với thêm/lấy đầu cuối.

### 5.3. Không lớp nào trở thành cấu trúc không khóa chỉ vì tên Concurrent

Cả hai lớp đang so sánh đều là hàng đợi có thể chặn luồng. Dùng `offer(e)` để không đợi chỗ trống không tự biến đường thực thi bên trong thành thuật toán không khóa.

Tốc độ quan sát được còn chịu ảnh hưởng của lịch thực thi, số luồng hoạt động, mức chiếm dụng hàng đợi, việc đánh thức luồng và cấp phát. Chi tiết cấu trúc giúp đặt giả thuyết, nhưng không thay thế phép đo.

Nếu thay lớp và tốc độ khác đi, cần tìm nguyên nhân trong cùng một cấu hình dung lượng và cùng mô hình tải, thay vì gán kết quả ngay cho số khóa.

## 6. FIFO và công bằng là hai khái niệm riêng

FIFO nói về thứ tự phần tử trong hàng đợi: phần tử được đưa vào trước đứng trước phần tử được đưa vào sau theo thứ tự chèn được hàng đợi xác lập.

Công bằng nói về chính sách cấp quyền cho các luồng đang chờ cạnh tranh thao tác. `ArrayBlockingQueue` có constructor với cờ `fair`; mặc định không bật chính sách công bằng. `LinkedBlockingQueue` không có constructor có cờ tương ứng.

Các cách tạo minh họa, chưa phải chương trình độc lập:

```java
BlockingQueue<Job> normal = new ArrayBlockingQueue<>(100);
BlockingQueue<Job> fair = new ArrayBlockingQueue<>(100, true);
BlockingQueue<Job> linked = new LinkedBlockingQueue<>(100);
```

Cờ công bằng không đổi FIFO của phần tử thành một thứ tự mới. Nó cũng không đảm bảo thứ tự hoàn tất công việc của nhiều bên tiêu thụ.

Ví dụ suy luận:

```text
Bên tiêu thụ A lấy công việc 1 → xử lý lâu
Bên tiêu thụ B lấy công việc 2 → xử lý nhanh → hoàn tất trước
```

Không có mâu thuẫn với FIFO: thứ tự lấy và thứ tự xử lý xong là hai chuyện khác nhau.

Tài liệu `ArrayBlockingQueue` mô tả công bằng thường làm giảm thông lượng nhưng giảm biến động và tránh một số bên chờ bị thiếu cơ hội. Không coi đó là lời hứa thời gian chờ tối đa theo số mili giây hay quyền được CPU ngay lập tức.

Muốn đánh giá cờ này, quan sát cả phân bố thời gian chờ giữa các bên, không chỉ tổng số phần tử mỗi giây. Một lần chạy với vài luồng in ra trước/sau hoặc đặt `Thread.sleep` không chứng minh được toàn bộ chính sách công bằng.

Khi đổi từ một `ArrayBlockingQueue` đã bật công bằng sang `LinkedBlockingQueue`, cần ghi nhận đây là một thay đổi điều kiện so sánh. Không âm thầm coi hai cấu hình ấy có cùng chính sách chờ.

## 7. Giữ nguyên chính sách chờ khi đổi lớp triển khai

### 7.1. API chung giữ hành vi mà bên gọi dựa vào

Với cùng giới hạn và trạng thái:

- `put(e)` có thể chờ chỗ; `take()` có thể chờ dữ liệu.
- `offer(e)` báo không thêm được bằng `false`.
- `poll()` báo chưa lấy được phần tử bằng `null`.
- Dạng có timeout cho phép chờ trong một khoảng theo đơn vị đã chọn.
- Các thao tác chờ có khả năng báo `InterruptedException`.
- Không lớp nào nhận phần tử `null`.

Đây là hợp đồng qua `BlockingQueue`, không phải khác biệt cần dùng để chọn một trong hai. Xem [BlockingQueue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html).

Tệp `QueueWaitingPolicyDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

public class QueueWaitingPolicyDemo {
    static void inspect(String label, BlockingQueue<String> queue)
            throws InterruptedException {
        queue.put("A");
        boolean accepted = queue.offer("B", 20, TimeUnit.MILLISECONDS);
        String first = queue.take();
        String missing = queue.poll(20, TimeUnit.MILLISECONDS);

        System.out.println(label + ": fullOffer=" + accepted
                + "; taken=" + first + "; emptyPoll=" + missing);
        System.out.println(label + ": immediateOffer=" + queue.offer("C")
                + "; next=" + queue.take()
                + "; remaining=" + queue.remainingCapacity());
    }

    public static void main(String[] args) throws InterruptedException {
        inspect("array-1", new ArrayBlockingQueue<>(1));
        inspect("linked-1", new LinkedBlockingQueue<>(1));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 QueueWaitingPolicyDemo.java
java QueueWaitingPolicyDemo
```

Stdout:

```text
array-1: fullOffer=false; taken=A; emptyPoll=null
array-1: immediateOffer=true; next=C; remaining=1
linked-1: fullOffer=false; taken=A; emptyPoll=null
linked-1: immediateOffer=true; next=C; remaining=1
```

Mỗi hàng đợi đều có dung lượng 1. Khi đang giữ A và không có bên lấy, thử đưa B có timeout thất bại bằng `false`. Sau khi lấy A và không có bên thêm, lần `poll` có timeout trả `null`.

Khi có chỗ, C được đưa và lấy bình thường. Kết quả giống nhau cho thấy mã dùng giao diện có thể giữ chính sách ở điểm gọi khi đổi lớp.

Chương trình không in thời gian thực tế. Timeout 20 mili giây là tham số cho phép chờ, không phải một kỳ vọng stdout về độ chính xác của bộ lập lịch.

### 7.2. Những thứ vẫn phải được xử lý ở bên gọi

Đổi từ mảng sang liên kết không sửa được các lỗi sau:

- Bỏ qua `false` từ `offer` và coi như công việc đã được nhận.
- Nuốt `InterruptedException` rồi tiếp tục chờ vô hạn.
- Kiểm tra `remainingCapacity()` trước rồi coi đã giữ chỗ.
- Nhìn `isEmpty()` rồi kết luận nguồn đã hết công việc.
- Tự khóa bên ngoài rồi chờ `put`, trong khi bên tiêu thụ cần chính khóa đó.
- Đưa cả bên sản xuất đang chờ và bên tiêu thụ chưa chạy vào một nhóm thực thi không còn luồng rảnh.

Các lỗi này thuộc quan hệ phối hợp và vòng đời tác vụ. Cách lưu phần tử không tự phá một vòng phụ thuộc ở tầng ứng dụng.

### 7.3. Chia sẻ đối tượng và kết thúc nguồn cũng giữ nguyên ranh giới

Cả hai chuyển giao tham chiếu qua hàng đợi. Bảo đảm tính nhìn thấy tại điểm chuyển giao không tự làm dữ liệu con có thể thay đổi trở thành đối tượng dùng chung an toàn.

Nếu bên sản xuất tiếp tục sửa công việc sau khi gửi và bên tiêu thụ đồng thời đọc, ứng dụng cần một quy ước sở hữu, dữ liệu bất biến hoặc đồng bộ riêng.

Cả hai cũng không có một lệnh đóng hàng đợi chung để tự kết thúc nguồn. Thông điệp dừng hoặc gián đoạn phải nằm trong một giao thức rõ. Một lần `poll` hết thời gian không phải bằng chứng mọi bên sản xuất đã hoàn tất.

Đừng sửa các quy tắc xử lý dữ liệu và kết thúc chỉ vì thay constructor.

## 8. Cùng một quy trình cho hai lớp

### 8.1. Hai bên sản xuất, hai bên tiêu thụ

Chương trình sau đặt cùng dung lượng 4 cho cả hai lớp. Hai bên sản xuất đưa các mã 1 đến 20 và 21 đến 40. Hai bên tiêu thụ cùng lấy dữ liệu.

Số 0 được dành riêng làm tín hiệu dừng; dữ liệu thật trong ví dụ luôn là số dương. Luồng chính chỉ gửi hai tín hiệu sau khi cả hai bên sản xuất đã hoàn tất, tương ứng một tín hiệu cho mỗi bên tiêu thụ.

Tệp `CommonQueuePipelineDemo.java`:

```java
import java.util.HashSet;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.Executors;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

public class CommonQueuePipelineDemo {
    record Result(int received, int unique, int sum, boolean allIds, int remaining) {}

    static int consume(BlockingQueue<Integer> queue,
            ConcurrentLinkedQueue<Integer> received, CyclicBarrier start)
            throws Exception {
        start.await(10, TimeUnit.SECONDS);
        int sum = 0;
        while (true) {
            int value = queue.take();
            if (value == 0) {
                return sum;
            }
            received.add(value);
            sum += value;
        }
    }

    static Void produce(BlockingQueue<Integer> queue, int from, int to,
            CyclicBarrier start) throws Exception {
        start.await(10, TimeUnit.SECONDS);
        for (int id = from; id <= to; id++) {
            queue.put(id);
        }
        return null;
    }

    static Result run(BlockingQueue<Integer> queue) throws Exception {
        var received = new ConcurrentLinkedQueue<Integer>();
        var start = new CyclicBarrier(4);
        var pool = Executors.newFixedThreadPool(4);

        try {
            var firstConsumer = pool.submit(() -> consume(queue, received, start));
            var secondConsumer = pool.submit(() -> consume(queue, received, start));
            var firstProducer = pool.submit(() -> produce(queue, 1, 20, start));
            var secondProducer = pool.submit(() -> produce(queue, 21, 40, start));

            firstProducer.get(10, TimeUnit.SECONDS);
            secondProducer.get(10, TimeUnit.SECONDS);
            queue.put(0);
            queue.put(0);

            int sum = firstConsumer.get(10, TimeUnit.SECONDS)
                    + secondConsumer.get(10, TimeUnit.SECONDS);
            var unique = new HashSet<>(received);
            boolean allIds = true;
            for (int id = 1; id <= 40; id++) {
                allIds &= unique.contains(id);
            }
            return new Result(received.size(), unique.size(), sum,
                    allIds, queue.size());
        } finally {
            pool.shutdownNow();
        }
    }

    static void print(String label, Result result) {
        System.out.println(label + ": received=" + result.received()
                + "; unique=" + result.unique()
                + "; sum=" + result.sum()
                + "; allIds=" + result.allIds()
                + "; remaining=" + result.remaining());
    }

    public static void main(String[] args) throws Exception {
        print("array-4", run(new ArrayBlockingQueue<>(4)));
        print("linked-4", run(new LinkedBlockingQueue<>(4)));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 CommonQueuePipelineDemo.java
java CommonQueuePipelineDemo
```

Stdout:

```text
array-4: received=40; unique=40; sum=820; allIds=true; remaining=0
linked-4: received=40; unique=40; sum=820; allIds=true; remaining=0
```

Bốn tác vụ có bốn luồng thực thi, cùng đi qua cổng bắt đầu. Các bên tiêu thụ có thể chạy khi các bên sản xuất đang phải chờ chỗ. Chương trình không đặt mọi luồng vào trạng thái sản xuất bị chặn rồi mới mong một tác vụ tiêu thụ trong cùng nhóm bắt đầu.

Luồng chính lấy kết quả của cả hai bên sản xuất trước khi gửi tín hiệu dừng. Vì vậy, không có dữ liệu mới được một bên sản xuất hợp lệ của thí nghiệm đặt sau các tín hiệu đó.

Sau khi mọi bên tiêu thụ hoàn tất, kết quả được kiểm tra theo các thuộc tính không phụ thuộc lịch phân chia công việc:

- Nhận đủ 40 phần tử dữ liệu.
- Có 40 mã khác nhau và đủ miền 1 đến 40.
- Tổng các mã là 820.
- Hàng đợi không còn phần tử.

Không in mỗi bên tiêu thụ nhận những mã nào, vì phần phân chia đó có thể thay đổi giữa các lần chạy.

### 8.2. Chương trình chứng minh điều gì và chưa chứng minh điều gì?

Nó kiểm chứng rằng cùng một quy trình dùng `BlockingQueue` chạy đúng trên cả hai lớp với giới hạn giống nhau. Nó kiểm tra không thiếu/trùng mã trong thí nghiệm có điều kiện nguồn đã xác định.

Nó không đo hay kết luận:

- Lớp nào có thông lượng cao hơn.
- Lớp nào có độ trễ cuối phân bố thấp hơn.
- Mức cấp phát của một tải dài.
- Mức công bằng giữa các tác vụ.
- Mọi lịch thực thi của một ứng dụng khác đều không có lỗi.

Các số nguyên nhỏ và công việc cộng số ở đây giúp tập trung vào phối hợp; chúng không đại diện cho kích thước và thời gian xử lý mọi công việc thật.

Nếu một bên tiêu thụ hỏng trong ứng dụng thật, bên sản xuất có thể tiếp tục chờ `put`. Một quy trình đầy đủ còn cần báo lỗi và hủy để các bên khác biết cách dừng. Việc chọn mảng hay liên kết không tự bổ sung đường lỗi đó.

### 8.3. Không suy ra thứ tự tổng từ thứ tự mã của nhiều bên sản xuất

Mỗi bên sản xuất có vòng lặp tăng dần riêng. Nhưng hai bên cùng đưa vào nên thứ tự xen kẽ không bắt buộc là 1, 2, 3 rồi đến hết 40.

FIFO áp dụng cho thứ tự chèn được xác lập ở hàng đợi. Nó không tự sắp mã số tăng dần và cũng không sắp theo thời điểm một luồng bắt đầu nghĩ đến việc gửi dữ liệu.

Nếu nghiệp vụ cần thứ tự theo một số thứ tự toàn cục, hãy thiết kế việc cấp và công bố số đó, hoặc chọn cơ chế xử lý phù hợp. Không lấy tính FIFO để hứa một thứ tự khác chưa được định nghĩa.

## 9. Chọn lớp và đo hiệu năng mà không đổi câu hỏi giữa chừng

### 9.1. Những hướng lựa chọn có căn cứ

| Điều đang ưu tiên | Hướng cân nhắc |
|---|---|
| Muốn dung lượng bắt buộc rõ và tái sử dụng vùng mảng tham chiếu | Xem `ArrayBlockingQueue` |
| Muốn lựa chọn công bằng qua constructor | Xem `ArrayBlockingQueue` với cờ phù hợp |
| Muốn cấu trúc nút theo lượng dữ liệu thay vì cấp một mảng bằng capacity ngay từ đầu | Xem `LinkedBlockingQueue`, vẫn chọn giới hạn có chủ ý |
| Có tải thêm/lấy nhiều luồng cần kiểm tra khả năng chồng lấp hai phía | Đo `LinkedBlockingQueue` cùng cấu hình tải với phương án mảng |
| Bên tiêu thụ chậm hơn nguồn một cách kéo dài | Xem lại năng lực xử lý và chính sách đầy; đổi lớp không đủ |
| Cần độ bền sau khi tiến trình dừng hoặc xác nhận xử lý | Cần thêm cơ chế ngoài hai hàng đợi trong bộ nhớ |

Đây là các hướng đặt giả thuyết lựa chọn. Không có một hàng duy nhất trong bảng đủ để thay thế các yêu cầu vận hành thực tế.

Một mảng được cấp trước có thể phù hợp với mức tải ổn định và mong muốn kiểm soát cấu trúc bộ nhớ. Một hàng đợi liên kết có thể là ứng viên cần đo khi số luồng và đường thêm/lấy làm tranh chấp trở thành yếu tố đáng kể. Cả hai quyết định vẫn phải xét dữ liệu phần tử, giới hạn và độ trễ.

### 9.2. So sánh phải giữ cùng chính sách dung lượng

Một phép đo dùng `new ArrayBlockingQueue<>(100)` đối chiếu với `new LinkedBlockingQueue<>()` có thể đang so sánh một bên bị buộc chờ với một bên tiếp tục tích lũy dữ liệu.

Nếu chỉ đếm số lần bên sản xuất gửi xong, kết quả không cho biết bên nào xử lý công việc nhanh hơn hay có giữ độ trễ chấp nhận được không. Dữ liệu chưa xử lý có thể đang dồn trong bộ nhớ.

Điểm so sánh công bằng về câu hỏi cần trả lời là cùng dung lượng, cùng chính sách khi đầy, cùng số bên sản xuất/tiêu thụ và cùng công việc. Nếu chủ ý so hai chính sách khác nhau, phải nêu rõ đó là thí nghiệm về chính sách.

Cờ công bằng của phương án mảng cũng là một biến cấu hình phải được ghi lại.

### 9.3. Những đại lượng cần đo riêng

- **Thông lượng chấp nhận:** bao nhiêu phần tử được đưa vào thành công mỗi đơn vị thời gian.
- **Thông lượng hoàn tất:** bao nhiêu công việc đã được xử lý xong.
- **Thời gian chờ đưa vào:** bên sản xuất bị giữ bao lâu khi đầy hoặc khi tranh chấp.
- **Thời gian nằm trong hàng đợi:** từ lúc được nhận đến lúc được lấy.
- **Độ trễ toàn bộ:** đến khi việc xử lý thực sự hoàn tất.
- **Cấp phát và thu hồi bộ nhớ:** cấu trúc hàng đợi và dữ liệu cần được phân biệt.
- **Trạng thái tải:** số phần tử đang xếp, số đang xử lý, số gửi thất bại hoặc hết thời gian.

Một phép đo `offer` trên hàng đợi luôn đầy có thể báo rất nhiều lời gọi mỗi giây chỉ vì chúng nhanh chóng trả `false`. Nếu bỏ qua số lần thành công, con số cao ấy dễ bị hiểu sai thành năng lực xử lý dữ liệu.

Tương tự, số công việc đã nhận cao nhưng thời gian nằm trong hàng đợi tăng mãi là một tình trạng khác với quy trình theo kịp tải.

### 9.4. Đừng dùng một vòng lặp và nanoTime để kết luận chung

Máy ảo cần có điều kiện chạy ổn định; kết quả có thể chịu ảnh hưởng của biên dịch JIT, tối ưu hóa, cấp phát, bộ thu gom rác, CPU và lịch thực thi. Một phép in nhật ký trong mỗi thao tác cũng có thể làm chi phí in lấn át chi phí hàng đợi.

Nếu cần đo ở mức vi mô, có thể dùng [JMH của OpenJDK](https://github.com/openjdk/jmh) để tổ chức phép đo, rồi kết hợp đo quy trình ứng dụng thực. Không lấy một con số từ thí nghiệm chức năng trong bài làm số liệu hiệu năng.

Thiết kế tải nên bao gồm các trạng thái có ý nghĩa: gần rỗng, mức chiếm dụng trung bình và thường xuyên đầy; một bên sản xuất–một bên tiêu thụ và nhiều bên mỗi phía; công việc nhỏ và dữ liệu đại diện.

Giữ cùng việc tạo phần tử ở hai phương án. Nếu một bên tạo payload lớn mới mỗi lần, bên kia tái sử dụng đối tượng nhỏ, phép đo đã thay cả chi phí dữ liệu.

### 9.5. Tăng capacity không sửa được chênh lệch tốc độ dài hạn

Xét mô hình đơn giản: bên sản xuất đưa 600 công việc mỗi giây, bên tiêu thụ chỉ hoàn tất tương đương 400 công việc mỗi giây, các tốc độ coi như ổn định và không có cơ chế từ chối.

Phần chờ tăng khoảng 200 công việc mỗi giây. Một vùng trống cho thêm 1.000 công việc chỉ hấp thụ được khoảng 5 giây theo mô hình này. Đây là phép ước lượng để hiểu xu hướng, không phải dự đoán chính xác lịch thực thi hay độ trễ của một hàng đợi Java.

Đổi mảng sang liên kết có thể thay chi phí phối hợp, nhưng không tự làm một nguồn chậm ngoài hàng đợi xử lý đủ 600 công việc mỗi giây. Cần xem nút nghẽn thực sự, khả năng tăng xử lý, điều tiết nguồn và chính sách quá tải.

Hàng đợi lớn giúp hấp thụ đợt tăng ngắn trong một số trường hợp, đồng thời có thể giữ nhiều dữ liệu hơn và làm công việc chờ lâu hơn. Dung lượng là một quyết định về vận hành, không chỉ một tham số tối ưu.

## 10. Các thao tác phụ và những giả định không nên mang theo

### 10.1. Xóa tùy ý khác lấy đầu/cuối

Một hàng đợi liên kết không tự có tra cứu theo giá trị O(1). Muốn tìm một đối tượng tùy ý để xóa vẫn phải xác định vị trí của nó. Với hàng đợi mảng, xóa mục ở giữa có thể đòi hỏi sắp lại phần tham chiếu liên quan trong cài đặt.

Vì vậy, nếu mô hình thường xuyên tìm và hủy theo mã công việc, cần đánh giá riêng đường đó. Đừng đo chỉ `put`/`take` rồi suy ra mọi thao tác hủy đều có cùng chi phí.

### 10.2. Lấy theo lô không tạo một giao dịch xử lý

`drainTo` có thể lấy những phần tử hiện có sang collection đích để xử lý một nhóm. Điều đó chưa có nghĩa phần xử lý phía sau là nguyên tử hoặc chắc chắn hoàn tất.

Nếu collection đích hoặc bước xử lý lỗi, ứng dụng cần hiểu dữ liệu đã được chuyển đến đâu. Cũng không dùng một collection đích đang bị nhiều bên sửa thiếu đồng bộ chỉ vì nguồn là một hàng đợi an toàn nhiều luồng.

Kích thước lô là một biến cấu hình khác: lô lớn có thể đổi phân chia công việc, thời gian giữ tài nguyên và độ trễ. Khi so sánh hai lớp, giữ hoặc ghi rõ biến này.

### 10.3. Duyệt hàng đợi không phải cơ chế nhận việc

Iterator dùng để quan sát có tính nhất quán yếu trong lúc cập nhật. Đừng dùng một lần duyệt rồi tự xem mỗi phần tử là đã được giao độc quyền cho người đọc.

Nếu đúng nhu cầu là nhận và bỏ phần tử khỏi hàng đợi, dùng thao tác lấy phù hợp. Nếu cần báo cáo trên một trạng thái cố định, hãy định nghĩa cách ổn định hoặc sao chép dữ liệu và mức nhất quán được yêu cầu.

Việc in được danh sách phần tử trông hợp lý không chứng minh mọi cập nhật đồng thời đã xuất hiện trong cùng một ảnh chụp.

## 11. Thực hành để tự kiểm tra lựa chọn

### Bài 1: constructor đã đổi điều gì?

Một ứng dụng đang dùng `new ArrayBlockingQueue<>(200)`. Người viết thay thành `new LinkedBlockingQueue<>()` rồi thấy bên sản xuất ít chờ hơn.

Hãy giải thích vì sao chưa thể kết luận cấu trúc liên kết nhanh hơn. Cần đo thêm gì về số phần tử tồn, số công việc hoàn tất, bộ nhớ và thời gian chờ?

Hướng giải thích: giới hạn chấp nhận dữ liệu đã thay đổi. Trước tiên cần đối chiếu hai cấu hình cùng capacity hoặc mô tả rõ sự khác biệt chính sách đang được thử.

### Bài 2: tải rỗng nhiều và tải luân chuyển cao

Một cấu hình có capacity rất lớn nhưng thường chỉ giữ ít phần tử. Cấu hình khác luôn có dữ liệu luân chuyển với tốc độ cao.

Vì sao hai cấu hình có thể có đánh đổi bộ nhớ khác nhau giữa mảng tạo trước và nút cấp phát theo đường thêm? Các dữ liệu nào cần thu thập trước khi quyết định?

Hướng giải thích: xem bộ nhớ của mảng rỗng, số nút đang sống, tốc độ cấp phát, tác động thu hồi và kích thước payload. Không gán số byte hoặc kết luận cố định khi chưa xác định JVM và tải.

### Bài 3: hai khóa có nghĩa nhanh gấp đôi không?

Một bên sản xuất và một bên tiêu thụ thực hiện công việc chậm ngoài hàng đợi. Đổi sang cơ chế có khóa thêm/lấy riêng nhưng tổng thời gian gần như không đổi.

Điều này có mâu thuẫn với cơ chế của `LinkedBlockingQueue` không? Hãy chỉ ra phần thời gian nào có thể đang chiếm ưu thế.

Hướng giải thích: cơ hội chồng lấp các thao tác hàng đợi chưa làm tăng tốc mọi phần của quy trình. Công việc ngoài hàng đợi hoặc một nguồn tài nguyên khác có thể là nơi quyết định tốc độ.

### Bài 4: FIFO hay công bằng?

Hai bên tiêu thụ cùng nhận việc từ một hàng đợi FIFO. Một bên hoàn tất nhiều hơn bên còn lại.

Có thể dựa riêng vào số lượng đó để kết luận hàng đợi không FIFO không? Bật công bằng có đảm bảo hai bên hoàn tất bằng nhau không?

Hướng giải thích: thứ tự phần tử, quyền truy cập khi chờ và tốc độ xử lý riêng của mỗi bên là ba yếu tố khác nhau. Cần chọn phép quan sát đúng với điều muốn đánh giá.

### Bài 5: giữ nguyên giao thức khi đổi lớp

Lấy `CommonQueuePipelineDemo`, thay hai constructor bằng cùng một dung lượng khác, vẫn giữ bốn tác vụ và hai tín hiệu dừng.

Hãy nêu những kết quả chức năng phải giữ và những thuộc tính không được khẳng định: phân chia mã cho từng bên, thời gian chạy, mức công bằng hay thứ tự hoàn tất.

Sau đó giả sử một bên tiêu thụ ném lỗi trước khi nhận tín hiệu dừng. Chỉ đổi lớp hàng đợi có đủ làm các bên còn lại thoát khỏi mọi lời gọi chờ không? Cần một cơ chế báo lỗi và hủy nào ở tầng phối hợp?

### Những câu hỏi trước khi chốt lựa chọn

1. Constructor thật sự đặt giới hạn nào?
2. Mức dữ liệu tồn thường gặp và mức đột biến là bao nhiêu?
3. Chi phí nằm ở hàng đợi hay ở công việc được xử lý?
4. Mục tiêu bộ nhớ có tính cả payload, bên sản xuất chờ và việc đang xử lý không?
5. Có cần chính sách công bằng riêng không?
6. Khi đầy, ứng dụng chờ, từ chối hay thử lại theo ngân sách nào?
7. Phép đo có giữ cùng dung lượng, tải, chính sách và dữ liệu không?
8. Giao thức kết thúc và xử lý lỗi có hoạt động trên cả hai lớp không?

Chọn giữa hai lớp là chọn một đánh đổi lưu trữ và phối hợp trong một quy trình đã được định nghĩa rõ. Hợp đồng đúng, dung lượng có chủ ý và phép đo phù hợp giúp quyết định có căn cứ hơn tên lớp hay một kết quả thời gian đơn lẻ.
