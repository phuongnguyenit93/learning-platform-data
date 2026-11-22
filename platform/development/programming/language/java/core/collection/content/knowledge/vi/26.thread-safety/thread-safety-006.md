# Iterator nhất quán yếu và iterator dùng ảnh chụp

## 1. Vì sao collection an toàn đa luồng vẫn có nhiều cách duyệt?

Giả sử chương trình đang duyệt danh sách người nhận thông báo thì một bên đăng ký thêm người mới. Lượt thông báo hiện tại nên gửi cho danh sách đã xác định lúc bắt đầu, hay có thể nhận thêm người vừa đăng ký? Nếu một người hủy đăng ký giữa lượt, lời gọi đang chờ tới người đó có bị hủy ngay không?

Một tình huống khác là duyệt một bảng trạng thái có rất nhiều cập nhật. Chương trình có thể chấp nhận một báo cáo gần với thời điểm hiện tại để theo dõi, nhưng bản đối soát cuối kỳ lại cần dữ liệu cùng một phiên bản.

Các tình huống đó cần những **cam kết về kết quả duyệt** khác nhau. Chọn collection an toàn đa luồng mới chỉ trả lời được một phần câu hỏi. Bạn còn phải biết iterator quan sát phiên bản nào, có phản ánh thay đổi trong lúc duyệt không, và có được sửa collection thông qua iterator không.

Hai cơ chế chính trong bài là:

- **Iterator nhất quán yếu (weakly consistent iterator):** cho phép duyệt cùng lúc với các thao tác khác theo hợp đồng của lớp, nhưng không cố định toàn bộ lượt duyệt vào một phiên bản duy nhất.
- **Iterator dùng ảnh chụp (snapshot iterator):** duyệt trạng thái cấu trúc đã được chốt tại lúc iterator được tạo. Thay đổi cấu trúc về sau không đổi tập tham chiếu mà iterator đó đang duyệt.

“Ảnh chụp” ở đây cần hiểu đúng độ sâu. Một mảng tham chiếu cố định không tự làm trạng thái của mọi đối tượng phần tử bất biến.

Sau bài này, bạn cần phân biệt được ba câu hỏi: **có thể duyệt an toàn không**, **đang nhìn phiên bản nào**, và **kết quả có đủ nhất quán cho yêu cầu ứng dụng không**. Chúng liên quan nhưng không thay thế nhau.

Các chương trình dùng Java 17 trở lên. Kiến thức nền gồm `Iterator`, `List`, `Map`, tham chiếu đối tượng và vòng lặp `for-each`. Phần thí nghiệm hai luồng giải thích các điểm chờ ngay trong bài.

## 2. Mô hình tinh thần: collection đang sống và một lượt duyệt

### 2.1. Collection, view và iterator có vòng đời khác nhau

Một collection là đối tượng chứa dữ liệu. Một **khung nhìn (view)** là một cách truy cập dữ liệu liên quan, chẳng hạn `map.keySet()`. Một iterator là đối tượng giữ tiến trình của **một lượt duyệt**.

Đoạn minh họa sau tạo hai lượt duyệt khác nhau trên cùng một danh sách:

```java
Iterator<String> first = names.iterator();
names.add("Lan");
Iterator<String> second = names.iterator();
```

Đây là đoạn mã minh họa, giả sử `names` là `CopyOnWriteArrayList<String>`. `first` và `second` được tạo ở hai thời điểm khác nhau. Chúng không nhất thiết duyệt cùng một phiên bản. `first` không được “làm mới” chỉ vì chương trình gọi `iterator()` để tạo `second`.

Vòng lặp nâng cao `for (String name : names)` lấy một iterator khi bắt đầu vòng lặp. Nó không lấy lại một iterator mới cho mỗi phần tử. Vì vậy, thời điểm bắt đầu vòng lặp có ý nghĩa với iterator dạng ảnh chụp.

Với `ConcurrentHashMap`, `keySet` là view liên kết với map, còn iterator của view là nhất quán yếu. Gọi view không đồng nghĩa chụp một bản sao độc lập của tất cả khóa. [ConcurrentHashMap — keySet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html#keySet())

### 2.2. Ba trục cần xem riêng

| Trục xem xét | Ví dụ câu hỏi | Không được suy luận tự động |
| --- | --- | --- |
| Chính sách quan sát thay đổi | Thêm sau khi tạo iterator có xuất hiện trong lượt này không? | Không ném ngoại lệ nghĩa là luôn thấy dữ liệu mới |
| Thứ tự duyệt | Theo chỉ số, thứ tự khóa, FIFO hay không có thứ tự cam kết? | Nhất quán yếu nghĩa là thứ tự hoàn toàn tùy ý |
| Quyền sửa qua iterator | `remove`, `set`, `add` có được hỗ trợ không? | Duyệt an toàn nghĩa là iterator chỉ đọc |

Một map có khóa được sắp xếp vẫn có thể dùng iterator nhất quán yếu. Một danh sách có thứ tự theo chỉ số vẫn có thể dùng iterator ảnh chụp. Hai đặc tính “thứ tự” và “phiên bản quan sát” không phải một.

### 2.3. Đối chiếu nhanh với iterator fail-fast

Iterator của các cấu trúc thông thường như `HashMap` có cơ chế **phát hiện sửa đổi sớm (fail-fast)** khi phát hiện thay đổi cấu trúc ngoài giao thức mà nó cho phép. Cơ chế này chỉ cố gắng phát hiện lỗi; không được dùng việc có hay không có `ConcurrentModificationException` để chứng minh an toàn đa luồng. [HashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html)

Ngoại lệ này có thể xuất hiện ngay cả khi chỉ một luồng vừa duyệt vừa sửa sai cách; chữ “Concurrent” trong tên ngoại lệ không có nghĩa phải có ít nhất hai luồng.

Ngược lại, iterator nhất quán yếu và iterator ảnh chụp được thiết kế với chính sách khác để xử lý thay đổi liên quan. Việc chúng không ném `ConcurrentModificationException` vì thay đổi cấu trúc nguồn không có nghĩa mọi kiểu sử dụng chương trình đều đúng.

Tên “fail-safe iterator” hay xuất hiện trong các bài viết không chính thức, nhưng không nên dùng nó như một hợp đồng chung để gom mọi iterator không fail-fast vào cùng một loại. Hãy dùng tên chính sách và cam kết mà tài liệu lớp thực tế đưa ra.

## 3. Iterator ảnh chụp: chốt cấu trúc tại lúc tạo

### 3.1. Cơ chế của `CopyOnWriteArrayList`

`CopyOnWriteArrayList` dùng cơ chế sao chép khi ghi (copy-on-write). Iterator giữ tham chiếu tới phiên bản mảng ở lúc nó được tạo. Cập nhật danh sách tạo/đưa vào sử dụng một phiên bản phù hợp cho danh sách hiện tại; iterator cũ tiếp tục nhìn phiên bản cũ.

Iterator của lớp này không phản ánh thêm/xóa/thay phần tử của danh sách sau thời điểm tạo. Nó không hỗ trợ `remove`; `ListIterator` cũng không hỗ trợ `set` và `add`. Các thao tác đó ném `UnsupportedOperationException`. [CopyOnWriteArrayList Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html)

Có thể hình dung bằng hai phiên bản:

```text
t0: list -> [An, Binh, Chi]
             ^
             iterator cu giu phien ban nay

t1: list -> [An, Binh-moi, Dung]

iterator cu:  An, Binh, Chi
iterator moi: An, Binh-moi, Dung
```

Không có bước “đồng bộ lại” để iterator cũ nhảy sang mảng mới. Điều đó làm lượt duyệt có một phạm vi cấu trúc ổn định, nhưng kết quả có thể cũ so với danh sách hiện tại.

### 3.2. Chương trình đầy đủ: phiên bản cũ và tham chiếu cũ

Lưu thành **`SnapshotIteratorDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.ListIterator;
import java.util.concurrent.CopyOnWriteArrayList;

public class SnapshotIteratorDemo {
    public static void main(String[] args) {
        CopyOnWriteArrayList<String> names =
                new CopyOnWriteArrayList<>(List.of("An", "Binh", "Chi"));
        Iterator<String> old = names.iterator();

        names.set(1, "Binh-moi");
        names.remove("Chi");
        names.add("Dung");

        List<String> oldNames = drain(old);
        require(oldNames.equals(List.of("An", "Binh", "Chi")), "old snapshot");
        System.out.println("old iterator = " + oldNames);
        System.out.println("new iterator = " + drain(names.iterator()));
        System.out.println("current list = " + names);
        System.out.println("iterator.remove = " + unsupported(old::remove));

        ListIterator<String> editableCursor = names.listIterator();
        editableCursor.next();
        System.out.println("listIterator.set = "
                + unsupported(() -> editableCursor.set("X")));
        System.out.println("listIterator.add = "
                + unsupported(() -> editableCursor.add("Y")));

        Item apple = new Item("apple", 1);
        Item banana = new Item("banana", 2);
        CopyOnWriteArrayList<Item> items =
                new CopyOnWriteArrayList<>(List.of(apple, banana));
        Iterator<Item> itemSnapshot = items.iterator();

        items.set(0, new Item("new-apple", 7));
        items.remove(banana);
        apple.quantity = 99;

        List<Item> oldItems = drain(itemSnapshot);
        require(oldItems.get(0) == apple, "element reference was copied deeply");
        require(oldItems.get(1) == banana, "removed reference was lost");
        require(oldItems.get(0).quantity == 99, "field change was not visible");
        System.out.println("old item references = " + oldItems);
        System.out.println("current item references = " + items);
        System.out.println("same original apple = " + (oldItems.get(0) == apple));
    }

    private static <T> List<T> drain(Iterator<T> iterator) {
        List<T> result = new ArrayList<>();
        iterator.forEachRemaining(result::add);
        return result;
    }

    private static String unsupported(Runnable action) {
        try {
            action.run();
            throw new AssertionError("expected UnsupportedOperationException");
        } catch (UnsupportedOperationException ex) {
            return ex.getClass().getSimpleName();
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static final class Item {
        private final String name;
        private int quantity;

        private Item(String name, int quantity) {
            this.name = name;
            this.quantity = quantity;
        }

        @Override
        public String toString() {
            return name + ":" + quantity;
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all SnapshotIteratorDemo.java
java SnapshotIteratorDemo
```

Stdout khi chạy thành công:

```text
old iterator = [An, Binh, Chi]
new iterator = [An, Binh-moi, Dung]
current list = [An, Binh-moi, Dung]
iterator.remove = UnsupportedOperationException
listIterator.set = UnsupportedOperationException
listIterator.add = UnsupportedOperationException
old item references = [apple:99, banana:2]
current item references = [new-apple:7]
same original apple = true
```

Chương trình có hai thí nghiệm riêng.

**Thí nghiệm tên người:** iterator được tạo trước khi sửa danh sách. Sau đó chương trình thay `Binh`, xóa `Chi`, thêm `Dung`. Iterator cũ vẫn đi qua ba tham chiếu của phiên bản cũ. Iterator mới và đối tượng danh sách hiện tại nhìn phiên bản mới.

Các lệnh `remove`, `set`, `add` được thử qua iterator chỉ để minh chứng thao tác không được hỗ trợ. Chúng không thay đổi danh sách. Muốn cập nhật danh sách, gọi phương thức trên `CopyOnWriteArrayList`, rồi hiểu rằng lượt duyệt hiện tại vẫn theo ảnh chụp của nó.

**Thí nghiệm hàng hóa:** iterator giữ tham chiếu tới `apple` và `banana` ban đầu. Danh sách hiện tại thay `apple` bằng một đối tượng mới rồi xóa `banana`, nhưng hai tham chiếu cũ vẫn nằm trong ảnh chụp. Khi sửa `apple.quantity = 99`, iterator cũ đọc chính đối tượng đó nên in `apple:99`.

Biểu thức `oldItems.get(0) == apple` kiểm tra danh tính đối tượng, chứng minh ảnh chụp không tạo một bản sao sâu cho `apple`.

### 3.3. Ảnh chụp cấu trúc không phải ảnh chụp sâu

Hãy tách ba điều sau:

| Điều được giữ | Ví dụ | Có phải snapshot iterator tự cung cấp không? |
| --- | --- | --- |
| Tập tham chiếu và thứ tự của phiên bản danh sách | Vẫn chứa tham chiếu `banana` đã bị xóa khỏi danh sách hiện tại | Có, với iterator của `CopyOnWriteArrayList` |
| Trạng thái bên trong mỗi phần tử | `apple.quantity` luôn giữ số 1 | Không |
| Quan hệ nhất quán giữa nhiều đối tượng ngoài danh sách | Tổng hàng hóa và cấu hình thuộc cùng một phiên bản nghiệp vụ | Không |

Nếu phần tử là `String` bất biến, việc giữ tham chiếu làm ví dụ dễ quan sát: bản thân chuỗi không đổi nội dung. Với đối tượng có trường thay đổi, câu chuyện khác hẳn.

Chương trình trên chỉ dùng **một luồng** khi sửa và đọc `quantity`. Nó minh chứng sự chia sẻ tham chiếu, không minh chứng rằng các lần đọc/ghi trường thường giữa nhiều luồng đã được đồng bộ đúng.

Nếu nhiều luồng sửa trạng thái phần tử, cần giao thức riêng: đối tượng bất biến, `volatile`/kiểu atomic cho trạng thái phù hợp, hoặc khóa bảo vệ đủ phạm vi. Đặt đối tượng vào một collection concurrent không tự đồng bộ mọi thay đổi tương lai trên đối tượng đó.

Các concurrent collection có bảo đảm công bố dữ liệu theo hợp đồng bộ nhớ của chúng; điều này không thay thế giao thức cho các lần sửa xảy ra sau đó. [java.util.concurrent — Memory Consistency Properties](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html#MemoryVisibility)

### 3.4. Chi phí và vòng đời của ảnh chụp

Đọc nhiều, cập nhật ít là hoàn cảnh thường phù hợp với copy-on-write. Một thay đổi thực sự đối với danh sách có thể cần sao chép mảng; nếu ghi liên tục hoặc danh sách lớn, chi phí cấp phát và sao chép cần được đo với khối lượng thực tế.

Tạo iterator không đồng nghĩa sao chép sâu từng phần tử. Từ việc iterator giữ phiên bản mảng cũ, có thể suy ra rằng một iterator sống lâu còn giữ các tham chiếu của phiên bản đó. Xóa phần tử khỏi danh sách hiện tại không buộc iterator cũ nhả tham chiếu ngay.

Khi không còn tham chiếu có thể truy cập tới phiên bản cũ, bộ thu gom rác mới có thể thu hồi nó theo cơ chế của JVM. Không nên giữ iterator lâu trong bộ nhớ đệm hay một tác vụ chờ kéo dài nếu không cần.

`CopyOnWriteArraySet` cũng dùng iterator dựa trên ảnh chụp mảng và không hỗ trợ xóa qua iterator. Nó phù hợp với tập thường nhỏ, số lần đọc vượt nhiều so với cập nhật; không phải giải pháp mặc định cho mọi tập dữ liệu concurrent. [CopyOnWriteArraySet Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArraySet.html)

## 4. Iterator nhất quán yếu: cho phép cập nhật mà không chốt một phiên bản toàn cục

### 4.1. Những điều có thể dựa vào

Tài liệu `java.util.concurrent` mô tả nhiều iterator concurrent là nhất quán yếu: có thể tiếp tục cùng với các thao tác khác, không dùng `ConcurrentModificationException` để báo sửa đổi nguồn, và có thể nhưng không bắt buộc phản ánh thay đổi sau khi iterator được tạo. Cần đọc thêm cam kết của lớp cụ thể. [java.util.concurrent — Concurrent Collections](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html)

Ở `ConcurrentHashMap`, kết quả iterator phản ánh trạng thái map ở các thời điểm tại hoặc sau lúc iterator được tạo; không có cam kết rằng toàn bộ lượt duyệt là một ảnh chụp duy nhất. Mỗi iterator được thiết kế cho một luồng sử dụng tại một thời điểm. [ConcurrentHashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)

Một cách đọc hữu ích là: **được phép đi qua cấu trúc đang hoạt động, nhưng không được tự nâng mức bảo đảm thành báo cáo cùng một phiên bản**.

Điều này không có nghĩa iterator được phép trả dữ liệu tùy tiện, bỏ qua mọi quy tắc thứ tự hay trả các phần tử chưa từng thuộc nguồn. Hợp đồng của từng lớp vẫn ràng buộc kết quả. Những phần tử ổn định không bị thêm/xóa/thay trong lượt duyệt là điểm tốt để thiết kế kiểm tra; những phần tử bị thay đổi cần xem đúng điều gì API hứa.

### 4.2. Một kết quả duyệt có thể ghép nhiều giai đoạn

Giả sử một lượt duyệt đã đọc dòng A. Trước khi nó đọc dòng B, một tác vụ khác cập nhật dữ liệu. Phần sau của lượt duyệt có thể chịu ảnh hưởng từ giai đoạn sau, trong khi phần đã trả về không tự được tính lại.

Vì vậy, tổng cộng dồn từ iterator không nhất thiết là tổng của toàn bộ hệ thống tại một thời điểm. Ngay cả khi từng giá trị `Integer` riêng lẻ bất biến, **thời điểm lấy các ánh xạ** vẫn có thể khác nhau.

Tương tự, khi khóa `session-7` bị xóa hoặc thay giá trị, việc iterator từng thấy nó không chứng minh phiên đó còn đang đăng ký khi bạn xử lý xong. Kết quả duyệt là quan sát để quyết định công việc tiếp theo, không phải quyền giữ tài nguyên.

“Nhất quán yếu” cũng không tự có nghĩa “iterator đã đi hết rồi sẽ tiếp tục cập nhật cho tới khi thấy mọi thay đổi mới”. Một iterator là một lượt duyệt có tiến trình; nó không phải kênh theo dõi sự kiện hay đăng ký nhận mọi thay đổi.

### 4.3. Thứ tự vẫn phụ thuộc loại collection

| Collection/view | Chính sách iterator | Điểm về thứ tự cần nhớ |
| --- | --- | --- |
| `ConcurrentHashMap.keySet/values/entrySet` | Nhất quán yếu | Không dựa vào thứ tự khóa của bảng băm |
| `ConcurrentLinkedQueue` | Nhất quán yếu | Queue có thứ tự FIFO theo hợp đồng của nó |
| `ConcurrentSkipListMap` và các view | Nhất quán yếu | Khóa vẫn theo thứ tự tự nhiên hoặc comparator |
| `CopyOnWriteArrayList` | Ảnh chụp | Theo thứ tự chỉ số của phiên bản được chụp |

`ConcurrentLinkedQueue` quy định iterator có thể hoạt động cùng các thao tác khác; các cam kết về phần tử/thứ tự phải đọc theo tài liệu queue. `ConcurrentSkipListMap` quy định iterator nhất quán yếu dù bản thân map vẫn sắp xếp khóa. [ConcurrentLinkedQueue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentLinkedQueue.html), [ConcurrentSkipListMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentSkipListMap.html)

Bảng này chỉ nêu những lớp cụ thể. Đừng suy rằng mọi lớp có tiền tố `Concurrent` đều dùng một thuật toán iterator, hoặc mọi cấu trúc trong `java.util.concurrent` đều là ảnh chụp.

## 5. Thí nghiệm hai luồng với iterator nhất quán yếu

### 5.1. Thiết kế bài thử theo điều được cam kết

Một bài thử sai thường làm như sau: tạo iterator, thêm một khóa mới rồi khẳng định iterator chắc chắn thấy khóa đó. Cách khẳng định ấy tự áp đặt một cam kết mạnh hơn hợp đồng nhất quán yếu.

Chương trình sau chia khóa thành hai nhóm:

- `base-a`, `base-b` được thêm trước khi tạo iterator và không bị sửa/xóa trong toàn bộ lượt duyệt.
- `changing-0`, `changing-1`, `changing-2` được thay đổi theo hai giai đoạn sau khi tạo iterator.

Bài thử chỉ kiểm tra chắc chắn các khóa ổn định được tìm thấy, không có khóa lạ hay khóa lặp trong lịch cập nhật này. Nó **không khẳng định một tập cố định các khóa changing phải xuất hiện**.

Chỉ một tác vụ sở hữu iterator. Tác vụ kia chỉ sửa map. Các `CountDownLatch` xác định thứ tự các giai đoạn; không dùng `Thread.sleep` để đoán lúc luồng kia đã chạy.

### 5.2. Chương trình đầy đủ

Lưu thành **`WeakIteratorDemo.java`**:

```java
import java.util.HashSet;
import java.util.Iterator;
import java.util.Set;
import java.util.TreeSet;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class WeakIteratorDemo {
    public static void main(String[] args) throws Exception {
        ConcurrentHashMap<String, Integer> map = new ConcurrentHashMap<>();
        map.put("base-a", 1);
        map.put("base-b", 2);
        map.put("changing-0", 0);

        CountDownLatch created = new CountDownLatch(1);
        CountDownLatch phaseOneDone = new CountDownLatch(1);
        CountDownLatch firstVisited = new CountDownLatch(1);
        CountDownLatch phaseTwoDone = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            Future<Set<String>> traversal = pool.submit(() -> {
                Iterator<String> iterator = map.keySet().iterator();
                created.countDown();
                await(phaseOneDone);

                Set<String> seen = new HashSet<>();
                require(iterator.hasNext(), "stable entries must be available");
                require(seen.add(iterator.next()), "repeated first key");
                firstVisited.countDown();
                await(phaseTwoDone);

                while (iterator.hasNext()) {
                    require(seen.add(iterator.next()), "repeated key");
                }
                return seen;
            });

            Future<?> updates = pool.submit(() -> {
                await(created);
                map.remove("changing-0");
                map.put("changing-1", 1);
                phaseOneDone.countDown();

                await(firstVisited);
                map.remove("changing-1");
                map.put("changing-2", 2);
                phaseTwoDone.countDown();
                return null;
            });

            Set<String> seen = traversal.get(10, TimeUnit.SECONDS);
            updates.get(10, TimeUnit.SECONDS);
            Set<String> stable = Set.of("base-a", "base-b");
            Set<String> universe = Set.of(
                    "base-a", "base-b",
                    "changing-0", "changing-1", "changing-2");

            require(seen.containsAll(stable), "stable entry was missed");
            require(universe.containsAll(seen), "unknown key");
            System.out.println("stable keys found = " + seen.containsAll(stable));
            System.out.println("observed keys are known = "
                    + universe.containsAll(seen));
            System.out.println("repeated keys = false");
            System.out.println("changing-key subset = not asserted");
            System.out.println("final keys = " + new TreeSet<>(map.keySet()));
        } finally {
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("pool did not terminate");
            }
        }
    }

    private static void await(CountDownLatch latch) throws InterruptedException {
        if (!latch.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("latch timed out");
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
```

Lệnh chạy:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all WeakIteratorDemo.java
java WeakIteratorDemo
```

Stdout khi chạy thành công:

```text
stable keys found = true
observed keys are known = true
repeated keys = false
changing-key subset = not asserted
final keys = [base-a, base-b, changing-2]
```

Giải thích thứ tự phối hợp:

1. Tác vụ duyệt tạo iterator rồi mở cổng `created`.
2. Tác vụ cập nhật thay `changing-0` bằng `changing-1`, sau đó mở `phaseOneDone`.
3. Tác vụ duyệt lấy một phần tử, mở `firstVisited`, rồi chờ.
4. Tác vụ cập nhật thay `changing-1` bằng `changing-2`, mở `phaseTwoDone`.
5. Tác vụ duyệt đi hết phần còn lại. Luồng chính lấy kết quả và kiểm tra các điều kiện đã chọn.

Trong lịch này, một phần tử được trả về trước giai đoạn cập nhật thứ hai, phần còn lại sau giai đoạn đó. Tập `seen` của tác vụ duyệt là dữ liệu riêng của nó, không bị tác vụ cập nhật sửa.

Dòng `changing-key subset = not asserted` **không phải một tập kết quả quan sát được**. Nó thông báo rõ rằng bài thử không áp đặt kết quả cố định cho nhóm đang thay đổi. Bạn có thể tự in `new TreeSet<>(seen)` để khảo sát, nhưng kết quả của phần đó không phải stdout cố định mà hợp đồng chung bắt buộc.

Dòng `final keys` được đọc sau khi cả hai tác vụ hoàn tất. Khi ấy không còn bên sửa map, nên in các khóa cuối bằng `TreeSet` cho thứ tự rõ ràng. Đây là trạng thái cuối, không phải tuyên bố rằng iterator cũ đã duyệt đúng tập cuối đó.

Các giới hạn chờ giúp chương trình báo lỗi thay vì treo nếu một tác vụ không thể tiến triển. Mọi lỗi kiểm tra trong tác vụ được chuyển về luồng chính qua `Future.get`. Bài thử không bắt lỗi rồi tiếp tục in kết quả như đã thành công.

### 5.3. Điều không được suy ra từ một lần chạy

Nếu máy của bạn in ra đủ tất cả khóa mới, điều đó không biến “có thể phản ánh thay đổi” thành “bắt buộc phản ánh mọi thay đổi”. Nếu lần chạy khác chỉ thấy một phần thay đổi, cũng không có nghĩa iterator bị hỏng.

Không nên khẳng định một chuỗi khóa cụ thể dựa vào cách phân bố băm hoặc thứ tự các ô nội bộ mà bạn quan sát trên một bản JDK. Đó có thể chỉ là hệ quả của cách triển khai/lịch chạy hiện tại. Thứ tự không được cam kết của `ConcurrentHashMap` không phải thứ tự cần học thuộc.

Bài thử đồng bộ hóa lịch chỉ ở các điểm cần thiết để đặt thay đổi vào giữa lượt duyệt. Không khóa cả map để loại bỏ hoàn toàn cập nhật, vì như vậy bài thử sẽ không còn khảo sát tình huống cần phân biệt.

## 6. So sánh trực tiếp hai chính sách

| Câu hỏi | Iterator nhất quán yếu | Iterator ảnh chụp của copy-on-write |
| --- | --- | --- |
| Duyệt cùng lúc với cập nhật nguồn? | Có theo hợp đồng lớp | Có, lượt cũ giữ phiên bản đã chốt |
| Chốt toàn bộ lượt vào phiên bản lúc tạo? | Không được mặc định như vậy | Có đối với cấu trúc/tham chiếu của phiên bản được chụp |
| Thay đổi sau lúc tạo có thể hiện ra? | Có thể; không phải mọi thay đổi đều bắt buộc hiện ra | Không làm đổi cấu trúc mà iterator cũ đang duyệt |
| Ném `ConcurrentModificationException` vì những thay đổi nguồn đã được chính sách cho phép? | Không | Không |
| Có sao chép sâu mọi phần tử không? | Không có cam kết đó | Không |
| Có được sửa qua iterator không? | Phụ thuộc lớp và thao tác cụ thể | `remove` không hỗ trợ; list iterator cũng không hỗ trợ `set/add` |
| Dữ liệu trả về còn là hiện trạng khi xử lý xong không? | Không có bảo đảm chung | Không; phiên bản có thể đã cũ |
| Có làm công việc nhiều bước thành một giao dịch không? | Không | Không |

Hai chính sách giải quyết những nhu cầu khác nhau. Một lượt duyệt listener có thể muốn tập người nhận cố định cho một đợt. Một bảng theo dõi trạng thái có thể ưu tiên tiếp tục hoạt động trong lúc cập nhật thay vì dừng tất cả bên ghi để lấy một bản chụp toàn cục.

Nhưng một phép kiểm kê cần chứng minh các số thuộc cùng một phiên bản sẽ không thể chỉ nói “iterator không ném ngoại lệ”. Yêu cầu nhất quán của ứng dụng quyết định bạn có chấp nhận kết quả đó được không.

### 6.1. Không nhầm ảnh chụp một entry với ảnh chụp cả iterator

Tài liệu `ConcurrentSkipListMap` mô tả các `Map.Entry` trả về là ảnh chụp ánh xạ tại lúc chúng được tạo, và không hỗ trợ `Entry.setValue`. Đồng thời, iterator của map vẫn là nhất quán yếu. [ConcurrentSkipListMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentSkipListMap.html)

Hai điều này không mâu thuẫn: entry A có thể được tạo ở thời điểm t1, entry B ở thời điểm t2. Mỗi cặp khóa–giá trị được giữ lại không tự chứng minh cả tập các cặp thuộc cùng thời điểm.

Từ “snapshot” luôn cần hỏi tiếp: ảnh chụp **cái gì**, ở **thời điểm nào**, và **độ sâu nào**? Với entry chứa một tham chiếu tới đối tượng có thể sửa, trạng thái bên trong đối tượng đó vẫn là câu hỏi riêng.

### 6.2. Sửa qua iterator là một phần hợp đồng riêng

Interface `Iterator` cho phép `remove` là thao tác tùy chọn. Mặc định có thể không hỗ trợ; quy tắc sửa đổi khi đang duyệt còn tùy chính sách lớp triển khai. [Iterator Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Iterator.html#remove())

`ConcurrentHashMap` hỗ trợ xóa qua iterator của view, còn iterator copy-on-write đã thử ở trên không hỗ trợ. Do đó, không thể dùng nhãn “không fail-fast” để đoán quyền sửa.

Nếu yêu cầu là **chỉ xóa khi giá trị hiện tại vẫn bằng giá trị đã quan sát**, hãy diễn đạt điều kiện đó bằng thao tác có điều kiện phù hợp. Đoạn minh họa không độc lập sau giả sử `states` là `ConcurrentHashMap<String, String>`:

```java
for (Map.Entry<String, String> entry : states.entrySet()) {
    if ("STALE".equals(entry.getValue())) {
        states.remove(entry.getKey(), entry.getValue());
    }
}
```

`ConcurrentMap.remove(key, expectedValue)` thực hiện kiểm tra giá trị và xóa theo một thao tác nguyên tử. Nó kiểm tra theo quy tắc bằng nhau của giá trị, không tự mang một số phiên bản. Nếu giá trị thay đổi rồi trở lại bằng giá trị cũ, một yêu cầu theo phiên bản cần thêm dữ liệu phiên bản trong thiết kế. [ConcurrentMap — remove có điều kiện](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentMap.html#remove(java.lang.Object,java.lang.Object))

Cũng không suy từ việc một thao tác xóa được phép sang bảo đảm “toàn bộ lượt dọn dẹp là một giao dịch”. Các cập nhật khác vẫn có thể diễn ra giữa những lần xử lý entry khác nhau.

## 7. Ứng dụng: một lượt gửi thông báo có tập listener cố định

### 7.1. Quy tắc mong muốn

Giả sử một lượt phát sự kiện lấy danh sách listener ở lúc bắt đầu. Trong khi đang gọi listener A, A hủy đăng ký B và thêm C.

Với chính sách ảnh chụp, một lựa chọn hợp lý là:

- Lượt hiện tại tiếp tục gọi A rồi B vì đó là danh sách đã chốt.
- Lượt tiếp theo gọi A rồi C.
- Không cần giữ khóa collection trong suốt thời gian chạy mã listener chỉ để bảo vệ iterator.

Điều này mô tả **quy tắc của ví dụ**, không phải yêu cầu phù hợp với mọi hệ thống. Nếu hủy đăng ký phải ngăn ngay mọi lời gọi chưa bắt đầu, ảnh chụp đơn thuần chưa đáp ứng.

### 7.2. Chương trình đầy đủ

Lưu thành **`ListenerSnapshotDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

public class ListenerSnapshotDemo {
    public static void main(String[] args) {
        CopyOnWriteArrayList<Runnable> listeners = new CopyOnWriteArrayList<>();
        List<String> calls = new ArrayList<>();

        Runnable listenerB = () -> calls.add("B");
        Runnable listenerC = () -> calls.add("C");
        Runnable listenerA = () -> {
            calls.add("A");
            listeners.remove(listenerB);
            listeners.addIfAbsent(listenerC);
        };

        listeners.add(listenerA);
        listeners.add(listenerB);

        dispatch(listeners);
        require(calls.equals(List.of("A", "B")), "first round");
        System.out.println("round 1 = " + calls);
        calls.clear();

        dispatch(listeners);
        require(calls.equals(List.of("A", "C")), "second round");
        System.out.println("round 2 = " + calls);
        System.out.println("registered listeners = " + listeners.size());
    }

    private static void dispatch(CopyOnWriteArrayList<Runnable> listeners) {
        for (Runnable listener : listeners) {
            listener.run();
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
```

Lệnh chạy:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all ListenerSnapshotDemo.java
java ListenerSnapshotDemo
```

Stdout khi chạy thành công:

```text
round 1 = [A, B]
round 2 = [A, C]
registered listeners = 2
```

Vòng `for-each` tạo iterator trước khi gọi A. Khi A sửa danh sách, iterator của lượt đầu vẫn chứa B. C được thêm vào danh sách hiện tại để lượt sau nhìn thấy.

`addIfAbsent(listenerC)` giúp ví dụ không đăng ký lại cùng đối tượng C mỗi lần A chạy. Đây là thao tác riêng phục vụ quản lý danh sách; chính sách ảnh chụp không tự ngăn thêm trùng bằng các đường `add` khác.

Ví dụ chủ động dùng **một luồng phát sự kiện**. `calls` là `ArrayList` chỉ do luồng này đọc/ghi. Nếu cho nhiều luồng gọi `dispatch` cùng lúc, cần xét riêng tính an toàn của listener, dữ liệu nhật ký và trạng thái mà listener truy cập.

### 7.3. Các yêu cầu bổ sung không được snapshot tự giải quyết

Ảnh chụp danh sách không làm mã hàm được gọi (callback) an toàn đa luồng. Hai lượt phát đồng thời vẫn có thể gọi cùng một listener ở hai luồng.

Nó cũng không bảo đảm mọi listener đều được gọi thành công. Trong chương trình trên, nếu một `listener.run()` ném ngoại lệ mà không có nơi xử lý phù hợp, vòng lặp kết thúc tại đó. Tập tham chiếu ổn định không đồng nghĩa xử lý mọi phần tử sẽ hoàn tất.

Nếu quy tắc hủy đăng ký mạnh hơn, có thể cần trạng thái đăng ký, kiểm tra quyền gọi hoặc cơ chế phối hợp tác vụ đang chạy. Cần chỉ rõ thời điểm “hủy có hiệu lực” và cách xử lý lời gọi đã bắt đầu. Đổi collection không tự định nghĩa các điều đó.

Tương tự, listener bị xóa khỏi danh sách hiện tại vẫn có thể được ảnh chụp của lượt đang chạy giữ tham chiếu. Việc tháo đăng ký và việc không còn bất kỳ tham chiếu nào là hai sự kiện khác nhau.

## 8. Khi cần bản chụp nhất quán thật sự

### 8.1. Sao chép sau một lượt duyệt yếu không làm nguồn trở thành một phiên bản

Đoạn minh họa sau tạo một map mới:

```java
Map<String, Integer> copy = new HashMap<>(concurrentMap);
```

Giả sử `concurrentMap` là `ConcurrentHashMap<String, Integer>` đang được cập nhật. Bản `copy` có cấu trúc riêng sau khi tạo, nhưng dữ liệu đi vào nó vẫn được lấy trong lúc nguồn có thể thay đổi.

Vì vậy, cần tách hai thuộc tính:

- **Độc lập sau khi sao chép:** thay một ánh xạ của bản mới không tự thay ánh xạ nguồn.
- **Nhất quán lúc thu thập:** mọi ánh xạ đã thu có thuộc cùng một phiên bản nguồn không?

Thuộc tính thứ nhất không chứng minh thuộc tính thứ hai. Sắp xếp bản sao bằng `TreeMap` chỉ đổi cách trình bày thứ tự, không sửa lịch sử thu thập dữ liệu. Bọc bản sao bằng một view không cho sửa cũng không nâng mức nhất quán của nguồn.

Nếu bạn dừng/phối hợp mọi bên ghi rồi lấy bản sao, lập luận thay đổi: lúc đó nguồn không chuyển phiên bản trong khi thu thập. Điều cần chứng minh nằm ở cơ chế dừng/phối hợp, không ở tên constructor sao chép.

### 8.2. Lấy bản sao dưới một khóa được mọi đường truy cập tôn trọng

Ví dụ minh họa không độc lập:

```java
Map<String, Integer> shared =
        Collections.synchronizedMap(new HashMap<>());

Map<String, Integer> snapshot;
synchronized (shared) {
    snapshot = new HashMap<>(shared);
}
```

Mọi truy cập map nền phải đi qua cùng đối tượng bọc, và các công việc nhiều bước cần giữ đúng monitor cho toàn bộ công việc đó. Việc sao chép nằm trong khối khóa nên các bên sửa qua đối tượng bọc ở luồng khác phải chờ. Với các khóa `String` và giá trị `Integer` bất biến trong ví dụ, bản sao không chia sẻ các trường phần tử có thể sửa.

Tài liệu synchronized map yêu cầu giữ khóa map trả về trong suốt lượt duyệt các collection view; không khóa riêng `keySet` thay cho map. [Collections — synchronizedMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedMap(java.util.Map))

Nếu nguồn là `ConcurrentHashMap`, tùy tiện `synchronized (concurrentMap)` quanh lúc chụp không khiến các luồng chỉ gọi `put` phải chờ monitor ngoài đó. Khóa chỉ phối hợp được những đường truy cập thực sự tuân thủ giao thức khóa. Một lớp bao riêng tư có thể giữ map không thoát ra ngoài và cung cấp các phương thức cập nhật/chụp dùng cùng khóa.

Khi cần ảnh chụp sâu, phải sao chép trạng thái phần tử trong lúc trạng thái đó cũng được bảo vệ. Sao chép từng đối tượng ở các thời điểm rời rạc không tự tạo tính nhất quán cho quan hệ giữa chúng.

### 8.3. Công bố trạng thái bất biến theo phiên bản

Một hướng khác là xây dựng trọn một trạng thái bất biến rồi công bố một tham chiếu tới phiên bản mới qua cơ chế đồng bộ phù hợp. Người đọc giữ một phiên bản trong suốt công việc.

Cách đó chỉ thuyết phục nếu dữ liệu liên quan thật sự được gom trong phiên bản và không có tham chiếu sửa được đi vòng. Nếu hai danh sách được công bố độc lập, mỗi danh sách có snapshot iterator vẫn chưa chứng minh chúng thuộc cùng một phiên bản nghiệp vụ.

Không có lựa chọn nào bắt buộc cho mọi ứng dụng. Hãy bắt đầu từ yêu cầu: theo dõi xấp xỉ trong lúc hoạt động, gửi cho tập đã chốt, hay đối chiếu dữ liệu cùng thời điểm. Sau đó chọn cơ chế có mức bảo đảm đủ cho yêu cầu ấy.

## 9. Không suy rộng hợp đồng iterator sang mọi cách truy cập

### 9.1. Vòng lặp chỉ số không phải iterator ảnh chụp

Đoạn minh họa dưới đây không tạo snapshot iterator, dù `names` là `CopyOnWriteArrayList<String>`:

```java
for (int i = 0; i < names.size(); i++) {
    System.out.println(names.get(i));
}
```

Mỗi `size` và `get` là một lần gọi riêng trên danh sách hiện tại. Giữa lúc kiểm tra `i < names.size()` và `get(i)`, một luồng khác có thể xóa phần tử, làm chỉ số không còn hợp lệ. Ngay cả khi không lỗi chỉ số, hai lần `get` có thể quan sát hai phiên bản khác nhau.

Vòng `for-each` hoặc một iterator đã tạo có chính sách khác vì nó giữ tiến trình trên nguồn mà hợp đồng iterator quy định. Đừng thay vòng lặp ảnh chụp bằng vòng chỉ số rồi cho rằng cùng mức bảo đảm.

### 9.2. View không cho sửa không có nghĩa là ảnh chụp

Bọc một danh sách sống bằng `Collections.unmodifiableList` chỉ chặn một số đường sửa thông qua view đó. Nó không tự tách dữ liệu khỏi danh sách nền, không tạo khóa cho bên ghi và không nâng iterator nền thành snapshot iterator. [Collections — unmodifiableList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List))

Tương tự, một `subList` là view với hợp đồng riêng. Đối với `CopyOnWriteArrayList.subList`, tài liệu nêu ngữ nghĩa view trở nên không xác định nếu danh sách nền bị sửa qua đường khác với view đó. Không được suy “list gốc có snapshot iterator” thành “mọi thao tác với mọi view đều giữ phiên bản cũ vô điều kiện”. [CopyOnWriteArrayList — subList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html#subList(int,int))

Hãy luôn xác định đối tượng thật sự đang dùng: list gốc, view, iterator đã tạo, hay bản sao độc lập.

### 9.3. `Spliterator` và stream cần đọc đúng điểm gắn với nguồn

Stream thường lấy dữ liệu qua `Spliterator`. Hai đặc tính hay gặp là:

- `CONCURRENT`: nguồn cho phép thay đổi đồng thời theo chính sách của nó.
- `IMMUTABLE`: nguồn mà spliterator đang duyệt không thể bị sửa cấu trúc trong lượt đó.

`CONCURRENT` không có nghĩa mọi luồng được tự do cùng gọi một instance spliterator, và không hứa bản chụp toàn cục. `IMMUTABLE` nói về nguồn/phiên bản mà spliterator duyệt, không tự chứng minh trạng thái bên trong từng đối tượng phần tử là bất biến. [Spliterator Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Spliterator.html)

Ví dụ, spliterator của `CopyOnWriteArrayList` báo `IMMUTABLE` và giữ ảnh chụp tại lúc spliterator được tạo, dù đối tượng list vẫn cho phép thêm/xóa về sau. Spliterator của các view `ConcurrentHashMap` báo `CONCURRENT`. Đây là hai cách quản lý thay đổi nguồn khác nhau.

Không mặc định mọi `stream()` chốt dữ liệu ngay tại lúc gọi phương thức, hoặc mọi stream đều chờ tới terminal operation mới chọn nguồn. Điểm gắn với nguồn phụ thuộc nguồn và cách tạo spliterator/stream; có nguồn gắn muộn, có nguồn giữ ảnh chụp sớm.

Hàm trong chuỗi xử lý (pipeline) vẫn phải tuân thủ yêu cầu không can thiệp không hợp lệ vào nguồn và quản lý trạng thái đúng cách. Cho phép nguồn concurrent được cập nhật không làm mọi tác dụng phụ trong lambda an toàn. [java.util.stream — Non-interference](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/package-summary.html#NonInterference)

Nếu mục tiêu bài toán chỉ cần một lượt duyệt tuần tự, nắm đúng `Iterator` trước. Không cần đổi sang parallel stream để “sửa” một yêu cầu nhất quán mà nguồn chưa đáp ứng.

### 9.4. Không chia sẻ một con trỏ duyệt chỉ vì collection an toàn

Một đối tượng iterator có trạng thái tiến trình, chẳng hạn vị trí hiện tại và phần tử cuối đã trả về. Khả năng cho phép **một luồng duyệt trong khi luồng khác sửa collection** không đồng nghĩa **hai luồng cùng dùng một iterator** là an toàn.

Cách thông thường là mỗi tác vụ có iterator riêng, hoặc chuyển việc phân chia phần tử cho một cơ chế được thiết kế cho việc đó. Nếu cần dùng chung con trỏ, phải có hợp đồng/giao thức đồng bộ riêng; không lấy tính an toàn của collection làm bằng chứng thay thế.

Điều tương tự áp dụng cho dữ liệu thu thập: một `ArrayList` cục bộ chỉ do một tác vụ ghi như trong thí nghiệm không thể được biến thành bộ chứa kết quả dùng chung mà không xem xét lại cơ chế phối hợp.

## 10. Chọn cơ chế theo yêu cầu quan sát

| Yêu cầu | Lựa chọn có thể phù hợp | Giới hạn cần chấp nhận hoặc giải quyết |
| --- | --- | --- |
| Duyệt bảng trạng thái trong khi cập nhật liên tục, chấp nhận quan sát các giai đoạn khác nhau | Iterator nhất quán yếu trên collection phù hợp | Không dùng kết quả như một ảnh chụp đối soát toàn cục |
| Chốt tập người nhận cho một lượt, số lần đăng ký thay đổi ít | Snapshot iterator của copy-on-write | Hủy đăng ký không tự rút phần tử khỏi ảnh chụp đang chạy |
| Duyệt nhiều, dữ liệu ít thay đổi, cần thứ tự danh sách | `CopyOnWriteArrayList` | Chi phí sao chép khi cập nhật và giữ phiên bản cũ |
| Tập nhỏ, đọc nhiều, không cần phần tử trùng | `CopyOnWriteArraySet` | Đánh giá chi phí tìm kiếm/cập nhật với kích thước thực tế |
| Báo cáo cần mọi số cùng phiên bản | Chụp dưới khóa chung hoặc công bố trạng thái bất biến | Mọi đường ghi và trạng thái phần tử phải cùng giao thức |
| Chỉ muốn cấm người gọi sửa qua một view | View không cho sửa | Không có snapshot/đồng bộ mới chỉ vì view không có quyền sửa |

Khi lựa chọn, hãy xác định mức cũ mà ứng dụng chấp nhận. Một ảnh chụp ổn định nhưng quá cũ có thể không phù hợp với yêu cầu điều khiển hiện thời. Một lượt duyệt mới hơn từng phần nhưng trộn phiên bản có thể không phù hợp với phép đối chiếu.

Hiệu năng cũng cần đúng dạng tải: số phần tử, tỷ lệ đọc/ghi, số lượt duyệt giữ đồng thời, thời gian xử lý mỗi phần tử và chi phí trạng thái phần tử. Không suy từ một vòng lặp nhỏ trong ví dụ thành kết luận một collection luôn nhanh nhất.

## 11. Luyện tập: xác định chính xác phạm vi bảo đảm

### Bài 1 — Xóa người nhận giữa lượt

Danh sách copy-on-write có A, B, C. Iterator được tạo; sau khi trả A, bên khác xóa B và thêm D. Các phần tử là chuỗi bất biến.

**Câu hỏi:** Iterator cũ bắt buộc phản ánh thao tác xóa/thêm mới không? Tạo một iterator mới sau cập nhật có cùng ý nghĩa với tiếp tục iterator cũ không?

**Đối chiếu:** Iterator cũ tiếp tục phiên bản A, B, C đã chốt; sau khi A đã trả về, phần còn lại là B, C. Iterator mới lấy phiên bản sau cập nhật. Hai lượt có thời điểm chụp khác nhau.

### Bài 2 — Ảnh chụp có phần tử thay đổi

Một snapshot iterator giữ tham chiếu `Order` có trường `status`. Sau khi tạo iterator, một luồng khác thay `status`.

**Câu hỏi:** Có thể khẳng định iterator luôn đọc trạng thái cũ không? Có thể khẳng định mọi lần đọc trường đã an toàn không?

**Đối chiếu:** Không thể khẳng định cả hai chỉ từ snapshot iterator. Ảnh chụp giữ tham chiếu, không chụp sâu trường. Cần xem tính bất biến và cơ chế đồng bộ của `Order`; nếu có quan hệ bất biến nhiều trường thì một trường volatile riêng lẻ chưa tự giải quyết toàn bộ.

### Bài 3 — Tổng từ concurrent map

Một luồng duyệt các giá trị trong `ConcurrentHashMap` để cộng tổng. Luồng khác đang di chuyển một đơn vị giữa hai khóa bằng hai cập nhật.

**Câu hỏi:** Không có `ConcurrentModificationException` có đủ chứng minh tổng thuộc cùng một phiên bản không?

**Đối chiếu:** Không. Iterator nhất quán yếu hỗ trợ lượt duyệt trong bối cảnh cập nhật, không biến hai lần sửa hay cả lượt cộng thành một giao dịch. Cần một giao thức giữ bất biến và cách đọc/chụp tương ứng nếu tổng phải có nghĩa tại một thời điểm.

### Bài 4 — Entry có ảnh chụp, iterator vẫn yếu

Một `ConcurrentSkipListMap` trả entry thứ nhất rồi entry thứ hai. Tài liệu gọi entry là snapshot của ánh xạ.

**Câu hỏi:** Có thể lấy đó làm bằng chứng hai entry thuộc cùng một phiên bản toàn map không?

**Đối chiếu:** Không. Mỗi entry có thời điểm được tạo riêng; ảnh chụp một ánh xạ không phải ảnh chụp toàn bộ lượt duyệt. Thứ tự khóa được sắp xếp cũng không gộp thời điểm quan sát.

### Bài 5 — Bài thử ép một kết quả không có trong hợp đồng

Một bài thử tạo iterator của concurrent map, thêm khóa `late`, rồi yêu cầu mọi lần chạy phải thấy `late`.

**Câu hỏi:** Bài thử đang xác minh điều gì sai?

**Đối chiếu:** Nó đã biến một thay đổi có thể được phản ánh thành một thay đổi bắt buộc được phản ánh. Nên kiểm tra những cam kết thật sự cần cho thuật toán hoặc đổi cơ chế nếu yêu cầu ứng dụng bắt buộc bao gồm khóa đó.

### Bài 6 — Cờ `IMMUTABLE`

Một spliterator của `CopyOnWriteArrayList` có cờ `IMMUTABLE`, nhưng chương trình vẫn gọi `list.add` thành công.

**Câu hỏi:** Hai điều đó có mâu thuẫn không?

**Đối chiếu:** Không. Cờ mô tả nguồn/phiên bản spliterator đang duyệt; đối tượng list hiện tại có thể chuyển sang phiên bản khác. Cờ đó cũng không đóng băng trường của mọi đối tượng phần tử.

## 12. Tài liệu để đối chiếu khi đổi collection

Các chương trình và tình huống trong bài được xây dựng để phân biệt cam kết về phiên bản quan sát. Khi áp dụng cho lớp khác, đọc chính sách iterator/spliterator và quyền sửa của đúng lớp đó:

- [java.util.concurrent Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html): nhất quán yếu và công bố dữ liệu.
- [CopyOnWriteArrayList Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html), [CopyOnWriteArraySet Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArraySet.html): snapshot iterator và giới hạn cập nhật.
- [ConcurrentHashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html), [ConcurrentLinkedQueue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentLinkedQueue.html), [ConcurrentSkipListMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentSkipListMap.html): cam kết của từng cấu trúc cụ thể.
- [Iterator Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Iterator.html), [Spliterator Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Spliterator.html): con trỏ duyệt, thao tác tùy chọn và đặc tính nguồn.
- [Collections Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html): view và yêu cầu khóa đối tượng bọc đồng bộ.

