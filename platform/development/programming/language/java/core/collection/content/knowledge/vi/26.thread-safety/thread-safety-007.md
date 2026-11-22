# Vì sao fail-fast không phải cơ chế đồng bộ hoặc kiểm tra đúng đắn

Một vòng lặp chạy hết mà không có `ConcurrentModificationException` chỉ cho biết lần chạy đó đã không ném ngoại lệ ấy. Nó chưa trả lời được ba câu hỏi quan trọng: các luồng có truy cập dữ liệu theo một quy tắc an toàn không, vòng lặp đã quan sát tập dữ liệu nào, và kết quả có thỏa yêu cầu của chương trình không.

Trong Java Collections Framework, **fail-fast** là cách một số iterator phát hiện việc sửa đổi không phù hợp với lượt duyệt đang diễn ra và dừng bằng ngoại lệ. Cơ chế này giúp tìm lỗi sử dụng collection. Để xây dựng chương trình đa luồng đúng, vẫn phải chọn cơ chế đồng bộ, quy tắc quan sát dữ liệu và thao tác nguyên tử phù hợp.

Bài học đi từ một iterator trong một luồng đến trường hợp nhiều luồng cùng dùng collection. Các thuật ngữ cần phân biệt là:

- **Lượt duyệt:** quá trình sử dụng một iterator hoặc spliterator cụ thể để đọc các phần tử.
- **Sửa đổi cấu trúc:** thay đổi ảnh hưởng đến tổ chức collection và tính hợp lệ của lượt duyệt; tiêu chí cụ thể phụ thuộc lớp triển khai.
- **Đồng bộ:** thiết lập quyền truy cập và quan hệ nhìn thấy dữ liệu giữa các luồng.
- **Tính nguyên tử:** một thao tác cần được quan sát như một đơn vị, không bị thao tác cạnh tranh chen vào giữa các bước quan trọng.
- **Bất biến nghiệp vụ:** điều kiện mà chương trình phải giữ, chẳng hạn mỗi mã đăng ký chỉ xuất hiện một lần.
- **Chẩn đoán:** phát hiện dấu hiệu sai để hỗ trợ sửa chương trình; một dấu hiệu chẩn đoán không tự thực thi các điều kiện trên.

## 1. Hợp đồng thực sự của fail-fast

`ConcurrentModificationException` có thể xuất hiện khi một đối tượng phát hiện sửa đổi không được phép trong tình huống hiện tại. Chữ “Concurrent” trong tên ngoại lệ không chứng minh rằng có hai luồng: một luồng tự sửa collection trực tiếp trong khi giữ iterator cũ cũng có thể gây lỗi.

Javadoc nêu rõ việc phát hiện chỉ là **best effort**, nghĩa là cố gắng phát hiện trong khả năng của triển khai, không có bảo đảm phát hiện mọi trường hợp sửa đổi đồng thời thiếu đồng bộ. Không được lấy ngoại lệ này làm điều kiện bảo đảm chương trình đúng. [Java 17: ConcurrentModificationException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ConcurrentModificationException.html)

Ví dụ sau là một đoạn minh họa trong phương thức, với các kiểu từ `java.util`:

~~~java
List<String> names = new ArrayList<>(List.of("An", "Binh"));
Iterator<String> cursor = names.iterator();

names.add("Chi");
String next = cursor.next();
~~~

Iterator được tạo trước `add`. Lần `next` sau đó dùng một lượt duyệt đã bị thay đổi cấu trúc của `ArrayList` làm mất hiệu lực. Với triển khai được kiểm chứng trong chương trình bên dưới, `next` ném `ConcurrentModificationException`.

Cùng thao tác thêm ấy, nếu thực hiện trước khi tạo iterator thì iterator mới bắt đầu trên trạng thái mới. Vấn đề cần phân tích là quan hệ giữa sửa đổi và **tuổi thọ iterator**, không phải riêng tên phương thức `add`.

Hai suy luận thường gặp đều không hợp lệ:

~~~text
Có ConcurrentModificationException
    => chắc chắn hai luồng truy cập collection cùng lúc.

Không có ConcurrentModificationException
    => collection đã được dùng an toàn và kết quả đã đúng.
~~~

Suy luận thứ nhất sai vì lỗi có thể do một luồng. Suy luận thứ hai sai vì bộ phát hiện không kiểm tra mọi loại lỗi, mọi thao tác hay mọi yêu cầu nghiệp vụ.

## 2. Vì sao cơ chế phát hiện hữu ích nhưng không đủ

Giả sử danh sách lệnh cần xử lý là `[A, B, C]`. Sau khi xử lý `A`, một đoạn mã thêm `D` vào danh sách. Iterator cũ đang giữ vị trí, giả định về cấu trúc và các thông tin nội bộ của lượt duyệt trước đó.

Nếu tiếp tục như chưa có thay đổi, chương trình phải tự trả lời những câu hỏi khó: có đọc `D` không, chỉ số còn tương ứng với phần tử nào, phần tử đã bị xóa có cần xử lý nữa không? Một iterator fail-fast không cố tạo ra chính sách duyệt động cho mọi tình huống này. Khi phát hiện trạng thái không khớp, nó báo lỗi để người viết chương trình thiết kế lại cách sử dụng.

Giá trị của cơ chế nằm ở chỗ lỗi xuất hiện gần thao tác đang dùng iterator. Tuy nhiên:

- Nó không ngăn việc thêm `D` đã xảy ra.
- Nó không thu hồi công việc xử lý `A`.
- Nó không quyết định `D` thuộc lượt xử lý hiện tại hay lượt sau.
- Nó không biết yêu cầu của ứng dụng là xử lý một lần, ít nhất một lần, hay chỉ xử lý một bản chụp đầu vào.
- Nó không thay người viết chương trình chọn khóa hoặc loại collection phù hợp.

Đó là những quyết định thiết kế có trước việc bắt ngoại lệ.

## 3. Mô hình bộ đếm: hiểu để đọc lỗi, không dùng làm giao thức đồng bộ

Nhiều lớp kế thừa `AbstractList` dùng trường `modCount` để hỗ trợ phát hiện thay đổi cấu trúc. `AbstractList` cho phép lớp con sử dụng hoặc không sử dụng cơ chế này; nó không phải yêu cầu rằng mọi collection phải dùng cùng một bộ đếm. [Java 17: AbstractList.modCount](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractList.html#modCount)

Có thể hình dung một lượt duyệt bằng mô hình sau. Đây là mô hình giải thích, không phải mã để thay thế iterator của JDK:

~~~text
Collection có dấu thay đổi: revision = 8
Iterator ghi nhớ:          expected = 8

Có sửa đổi được theo dõi:
    revision = 9

Đến một điểm kiểm tra của iterator:
    nếu revision khác expected thì báo lỗi
~~~

Số được ghi nhớ không phải bản sao toàn bộ dữ liệu. Việc hai giá trị bằng nhau cũng không thực hiện một phép kiểm chứng ngữ nghĩa trên từng phần tử.

Trong `ArrayList` của OpenJDK 17, iterator giữ một giá trị mong đợi và kiểm tra ở những đường đi nhất định. `hasNext` dùng vị trí hiện tại và kích thước, trong khi `next` có đường kiểm tra thay đổi. Vì vậy không thể suy từ tên “fail-fast” rằng mọi lời gọi đều kiểm tra ngay lập tức. Đây là chi tiết triển khai để lý giải quan sát, không phải hợp đồng áp dụng cho tất cả iterator. [Mã nguồn OpenJDK 17: ArrayList.Itr](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/ArrayList.java)

### 3.1. Bộ đếm không phải khóa

So sánh hai số không buộc luồng ghi phải chờ. Một luồng khác vẫn có thể thay đổi dữ liệu ở khoảng giữa lần kiểm tra và lần sử dụng dữ liệu. Nếu các truy cập vốn thiếu đồng bộ, chính việc đọc bộ đếm cũng không tự tạo một quan hệ công bố dữ liệu đầy đủ.

Ngược lại, khóa chung xác định đoạn mã nào được vào vùng bảo vệ và khi nào. Theo mô hình bộ nhớ Java, mở khóa một monitor xảy ra trước về quan hệ nhìn thấy dữ liệu đối với lần khóa tiếp theo trên cùng monitor. `volatile` và các công cụ trong `java.util.concurrent` cũng có hợp đồng riêng. So sánh một trường số thông thường không có những tác dụng này. [JLS 17, mục 17.1 và 17.4.5](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html)

Ngay cả ý tưởng “đổi bộ đếm thành `volatile`” cũng chưa giải quyết bài toán: nhìn thấy một số mới không làm cho thao tác kiểm tra rồi đọc nhiều phần tử trở thành một đơn vị nguyên tử. Cần thiết kế giao thức truy cập, không chỉ làm dấu hiệu thay đổi dễ nhìn thấy hơn.

### 3.2. Nội dung quay lại như cũ không phục hồi iterator cũ

Bắt đầu với `[A, B]`, tạo iterator, thêm `TEMP` rồi xóa `TEMP`. Danh sách cuối lại là `[A, B]`. Điều này không có nghĩa iterator đã hợp lệ trở lại.

Tình huống ấy phân biệt **bằng nhau về nội dung ở hai thời điểm** với **không có sửa đổi trong khoảng thời gian đó**. Cơ chế theo dõi thay đổi không phải phép so sánh danh sách cuối cùng với một bản sao ban đầu. Chương trình đầy đủ sẽ cho thấy iterator cũ vẫn báo lỗi.

Không nên đọc hoặc sửa bộ đếm nội bộ để “hợp thức hóa” iterator. Ứng dụng phải tuân thủ API và chính sách sửa đổi của collection đang dùng.

### 3.3. “Không đổi kích thước” không phải quy tắc tổng quát

Với `ArrayList`, việc thay tham chiếu ở một vị trí bằng `set` không được xem là sửa đổi cấu trúc theo mô tả lớp. Trong khi đó những thao tác quản lý cấu trúc khác có thể ảnh hưởng đến lượt duyệt mà không thể được đánh giá chỉ bằng `size` trước và sau. [Java 17: ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html)

Do đó, cách kiểm tra bằng `oldSize == list.size()` không phải bản thay thế cho hợp đồng iterator. Cũng không suy rộng quy tắc `set` của `ArrayList` cho mọi collection, mọi view hay mọi thuật toán.

## 4. Ba tầng phải được đánh giá độc lập

| Tầng cần đánh giá | Câu hỏi cụ thể | Fail-fast trả lời được gì? |
|---|---|---|
| An toàn truy cập | Có các truy cập đọc/ghi xung đột thiếu đồng bộ không? | Không kiểm chứng toàn bộ giao thức giữa các luồng. |
| Hợp đồng duyệt | Iterator này cho phép những sửa đổi nào? | Có thể phát hiện một số vi phạm theo chính sách của lớp. |
| Đúng yêu cầu | Có bỏ sót, xử lý trùng, sai tổng, sai điều kiện duy nhất không? | Không biết bất biến hay ý nghĩa nghiệp vụ. |

Một chương trình có thể đạt tầng đầu nhưng vi phạm tầng thứ hai. Chẳng hạn tất cả thao tác nằm trong cùng một khối khóa, nhưng chính luồng giữ khóa gọi `list.add` rồi tiếp tục dùng iterator cũ.

Một chương trình khác có thể dùng các phương thức riêng lẻ an toàn giữa nhiều luồng nhưng vi phạm tầng thứ ba: hai luồng đều kiểm tra “chưa có” rồi cùng thêm một mã. Nếu không có lượt duyệt nào trong đoạn này thì không có lý do để chờ một bộ phát hiện của iterator can thiệp.

Để chứng minh tính đúng, cần nói rõ **điều gì phải luôn đúng**, **thao tác nào duy trì điều đó**, và **các truy cập cạnh tranh được phối hợp ra sao**. Việc không thấy ngoại lệ không thay thế ba phần ấy.

## 5. Một chương trình kiểm chứng các ranh giới

Tệp `FailFastBoundaryDemo.java` dưới đây là chương trình chạy độc lập, dùng API có trong Java 17. Chương trình đã được biên dịch bằng `javac --release 17` và chạy trên OpenJDK Zulu 24.0.2; đây không phải tuyên bố đã chạy trên một JVM 17.

Các phần cố ý làm sai hợp đồng iterator được giới hạn trong những trường hợp có thứ tự rõ ràng. Chương trình không tạo một cuộc đua đọc/ghi tự do trên `ArrayList` rồi khẳng định stdout của cuộc đua phải cố định.

Phần nhiều luồng dùng `CyclicBarrier` để buộc cả hai luồng kiểm tra xong trước khi thêm. Những lần truy cập danh sách ở đó đi qua `Collections.synchronizedList`. Bởi vậy kết quả trùng có thể giải thích bằng lịch thực thi của các lời gọi hợp lệ riêng lẻ, không cần dựa vào hỏng cấu trúc nội bộ.

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.ConcurrentModificationException;
import java.util.Iterator;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class FailFastBoundaryDemo {
    @FunctionalInterface
    interface Action {
        void run() throws Exception;
    }

    static String outcome(Runnable action) {
        try {
            action.run();
            return "completed";
        } catch (ConcurrentModificationException ex) {
            return ex.getClass().getSimpleName();
        }
    }

    static void runPair(Action action) throws Exception {
        AtomicReference<Throwable> failure = new AtomicReference<>();
        Runnable task = () -> {
            try {
                action.run();
            } catch (Throwable ex) {
                failure.compareAndSet(null, ex);
            }
        };
        Thread first = new Thread(task, "first");
        Thread second = new Thread(task, "second");
        first.setDaemon(true);
        second.setDaemon(true);
        first.start();
        second.start();
        first.join(5000);
        second.join(5000);
        if (first.isAlive() || second.isAlive()) {
            first.interrupt();
            second.interrupt();
            throw new AssertionError("Pair did not finish");
        }
        if (failure.get() != null) {
            throw new AssertionError("Task failed", failure.get());
        }
    }

    public static void main(String[] args) throws Exception {
        List<String> direct = new ArrayList<>(List.of("A", "B"));
        Iterator<String> directIt = direct.iterator();
        direct.add("C");
        System.out.println("direct = " + outcome(() -> directIt.next()));

        List<String> removed = new ArrayList<>(List.of("A", "B", "C"));
        Iterator<String> removeIt = removed.iterator();
        while (removeIt.hasNext()) {
            if (removeIt.next().equals("B")) {
                removeIt.remove();
            }
        }
        System.out.println("iterator-remove = " + removed);

        List<String> guarded =
                Collections.synchronizedList(new ArrayList<>(List.of("P", "Q")));
        synchronized (guarded) {
            Iterator<String> guardedIt = guarded.iterator();
            guarded.add("R");
            System.out.println("guarded-direct = "
                    + outcome(() -> guardedIt.next()));
        }

        List<String> restored = new ArrayList<>(List.of("A", "B"));
        Iterator<String> restoredIt = restored.iterator();
        restored.add("TEMP");
        restored.remove("TEMP");
        System.out.println("restored-content = " + restored);
        System.out.println("restored-iterator = "
                + outcome(() -> restoredIt.next()));

        List<String> replaced = new ArrayList<>(List.of("old", "tail"));
        Iterator<String> replaceIt = replaced.iterator();
        replaced.set(0, "new");
        System.out.println("set-next = " + replaceIt.next());

        StringBuilder box = new StringBuilder("safe");
        List<StringBuilder> boxes = new ArrayList<>(List.of(box));
        Iterator<StringBuilder> boxIt = boxes.iterator();
        box.append("?");
        System.out.println("element-next = " + boxIt.next());

        List<String> shortened = new ArrayList<>(List.of("A", "B"));
        Iterator<String> shortIt = shortened.iterator();
        System.out.println("shortcut-first = " + shortIt.next());
        shortened.remove("B");
        System.out.println("shortcut-hasNext = " + shortIt.hasNext());

        List<String> ordered = new ArrayList<>(List.of("L", "R"));
        Iterator<String> orderedIt = ordered.iterator();
        AtomicReference<Throwable> writerFailure = new AtomicReference<>();
        Thread writer = new Thread(() -> {
            try {
                ordered.add("S");
            } catch (Throwable ex) {
                writerFailure.set(ex);
            }
        }, "ordered-writer");
        writer.setDaemon(true);
        writer.start();
        writer.join(5000);
        if (writer.isAlive()) {
            writer.interrupt();
            throw new AssertionError("Writer did not finish");
        }
        if (writerFailure.get() != null) {
            throw new AssertionError("Writer failed", writerFailure.get());
        }
        System.out.println("after-join = " + outcome(() -> orderedIt.next()));

        List<Integer> duplicate =
                Collections.synchronizedList(new ArrayList<>());
        CyclicBarrier checked = new CyclicBarrier(2);
        runPair(() -> {
            boolean absent = !duplicate.contains(42);
            checked.await(5, TimeUnit.SECONDS);
            if (absent) {
                duplicate.add(42);
            }
        });
        System.out.println("separate-calls = " + duplicate);
        System.out.println("unique-invariant = " + (duplicate.size() == 1));

        List<Integer> unique =
                Collections.synchronizedList(new ArrayList<>());
        CyclicBarrier ready = new CyclicBarrier(2);
        runPair(() -> {
            ready.await(5, TimeUnit.SECONDS);
            synchronized (unique) {
                if (!unique.contains(42)) {
                    unique.add(42);
                }
            }
        });
        System.out.println("whole-operation = " + unique);
        System.out.println("unique-invariant-fixed = " + (unique.size() == 1));

        List<String> jobs = new ArrayList<>(List.of("A", "B", "C"));
        List<String> delivered = new ArrayList<>();
        boolean interrupted = false;
        Iterator<String> jobIt = jobs.iterator();
        try {
            while (jobIt.hasNext()) {
                String job = jobIt.next();
                delivered.add(job);
                if (job.equals("A")) {
                    jobs.add("D");
                }
            }
        } catch (ConcurrentModificationException ex) {
            interrupted = true;
        }
        System.out.println("retry-caught = " + interrupted);
        System.out.println("effects-before-retry = " + delivered);
        for (String job : jobs) {
            delivered.add(job);
        }
        System.out.println("effects-after-retry = " + delivered);

        CopyOnWriteArrayList<String> snapshots =
                new CopyOnWriteArrayList<>(List.of("U", "V"));
        Iterator<String> snapshotIt = snapshots.iterator();
        snapshots.add("W");
        List<String> snapshotRead = new ArrayList<>();
        snapshotIt.forEachRemaining(snapshotRead::add);
        System.out.println("snapshot-iterator = " + snapshotRead);
        System.out.println("snapshot-current = " + snapshots);
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~shell
javac --release 17 -encoding UTF-8 FailFastBoundaryDemo.java
java FailFastBoundaryDemo
~~~

Stdout của lần kiểm chứng:

~~~text
direct = ConcurrentModificationException
iterator-remove = [A, C]
guarded-direct = ConcurrentModificationException
restored-content = [A, B]
restored-iterator = ConcurrentModificationException
set-next = new
element-next = safe?
shortcut-first = A
shortcut-hasNext = false
after-join = ConcurrentModificationException
separate-calls = [42, 42]
unique-invariant = false
whole-operation = [42]
unique-invariant-fixed = true
retry-caught = true
effects-before-retry = [A]
effects-after-retry = [A, A, B, C, D]
snapshot-iterator = [U, V]
snapshot-current = [U, V, W]
~~~

Riêng dòng `shortcut-hasNext = false` là quan sát trên triển khai đã chạy và phù hợp với cách viết `ArrayList.Itr` trong OpenJDK 17 đã đối chiếu. Một triển khai hoặc phiên bản khác có thể kiểm tra ở điểm khác. Không viết ứng dụng dựa vào việc trường hợp vi phạm hợp đồng này sẽ im lặng.

Các thời hạn năm giây giúp chương trình kiểm chứng báo lỗi nếu phối hợp bị kẹt; chúng không dùng để quyết định luồng nào thắng. `Thread.sleep` không tham gia thiết lập lịch thực thi. Kết quả chỉ được in sau khi các luồng tương ứng đã kết thúc; lỗi trong luồng phụ được chuyển về luồng chính thay vì bị bỏ qua.

## 6. Đọc từng nhóm kết quả

### 6.1. Một luồng cũng đủ gây ngoại lệ

`direct` tạo iterator rồi thêm một phần tử bằng chính danh sách. Lời gọi `next` sau đó báo `ConcurrentModificationException`. Không có luồng phụ trong tình huống này.

Ngược lại, `iterator-remove` xóa `B` qua chính iterator đang duyệt và còn `[A, C]`. Đây là đường sửa đổi mà iterator của `ArrayList` hỗ trợ. Với giao diện `Iterator` nói chung, `remove` là thao tác tùy chọn, có điều kiện gọi sau `next` và không được gọi hai lần cho cùng phần tử vừa trả về. Không được giả định mọi iterator đều hỗ trợ xóa. [Java 17: Iterator.remove](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Iterator.html#remove())

Thay `removeIt.remove()` bằng `removed.remove("B")` là thay đổi đường sửa collection. Dù ý định vẫn là xóa `B`, hợp đồng đối với iterator hiện tại đã khác.

Nếu có hai iterator trên cùng `ArrayList`, việc sửa hợp lệ qua iterator thứ nhất cũng không tự cập nhật trạng thái mong đợi của iterator thứ hai. Quyền sửa thuộc lượt duyệt đang thực hiện thao tác, không phải quyền miễn kiểm tra cho mọi lượt duyệt đang tồn tại.

### 6.2. Khóa đúng vẫn không cho phép tùy ý sửa trong lúc duyệt

Trong `guarded-direct`, một luồng giữ monitor của danh sách bọc đồng bộ, tạo iterator và thêm `R`. Thao tác thêm vẫn thực hiện được bởi monitor Java có tính tái nhập: chính luồng đang giữ khóa có thể vào lại đoạn mã dùng cùng khóa.

Khóa giữ các luồng tuân thủ cùng giao thức ở ngoài vùng bảo vệ. Nó không biến `guarded.add("R")` thành `guardedIt.add`, cũng không làm iterator được tạo trước đó quên lịch sử thay đổi.

Đây là tình huống hay xuất hiện qua hàm gọi lại: vòng lặp đang giữ khóa gọi một hàm xử lý phần tử; hàm ấy lại thêm hoặc xóa collection. Khi xem stack trace, cần lần theo cả các hàm được gọi gián tiếp, không chỉ nhìn thân vòng lặp.

Chọn một trong các hướng có ý nghĩa với bài toán:

- Xóa bằng iterator nếu thao tác đó được hỗ trợ và phù hợp.
- Thu thập các thay đổi dự định rồi áp dụng sau khi lượt duyệt kết thúc.
- Duyệt một bản chụp đã lấy an toàn, chấp nhận bản chụp phản ánh thời điểm lấy dữ liệu.
- Chọn cấu trúc có chính sách duyệt cho phép kiểu cập nhật cần dùng.

Mỗi hướng thay đổi cách xử lý dữ liệu, vì vậy cần kiểm tra lại yêu cầu của ứng dụng.

### 6.3. Có thay đổi nhưng không nhất thiết có tín hiệu fail-fast

`set-next = new` xuất hiện vì việc `set` thay tham chiếu trong danh sách này không làm mất hiệu lực iterator theo cơ chế đang xét. Iterator trả về giá trị mới ở vị trí chưa đọc. Điều này không biến việc nhiều luồng đồng thời `set` và `get` trên `ArrayList` thành an toàn.

`element-next = safe?` cho thấy một giới hạn khác: collection chứa tham chiếu đến `StringBuilder`. Sửa nội dung của chính đối tượng ấy không phải thao tác thêm hoặc xóa phần tử trong collection. Iterator không phải bộ theo dõi mọi trường của mọi đối tượng mà nó có thể trả về.

Ví dụ sửa `StringBuilder` chỉ có một luồng. Khi chuyển sang nhiều luồng, tính an toàn của phần tử phải được thiết kế riêng; collection an toàn không tự làm mọi đối tượng nằm trong nó an toàn.

`shortcut-hasNext = false` minh họa điểm kiểm tra có thể không được đi tới. Sau khi lấy `A`, chương trình xóa `B` trực tiếp; vị trí iterator lúc đó trùng kích thước mới. Đường `hasNext` được quan sát trả `false`, nên một vòng lặp kiểu thông thường có thể kết thúc mà không gọi `next` thêm lần nào.

Điều cần học từ quan sát này là **không được dùng sự im lặng làm giấy chứng nhận**, chứ không phải học một thủ thuật sửa danh sách để né ngoại lệ.

### 6.4. Có hai luồng nhưng không cần có truy cập chồng lấn

Trong `after-join`, iterator được tạo trước khi khởi động luồng ghi. Luồng ghi thêm `S` rồi kết thúc; luồng chính đợi bằng `join` và chỉ sau đó gọi `next`.

Không có lượt đọc cấu trúc danh sách của luồng chính diễn ra đồng thời với thao tác thêm trong ví dụ này. Dù vậy, iterator cũ vẫn được sử dụng sau một sửa đổi không đi qua nó và báo lỗi.

Quan hệ sau khi luồng kết thúc qua `join` là cơ sở công bố kết quả của luồng ghi cho luồng chính. Ngoại lệ ở đây không chứng minh `join` thiếu đồng bộ; nó phản ánh tuổi thọ iterator vượt qua sửa đổi không phù hợp. [JLS 17.4.5: Thread.start và Thread.join](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4.5)

Đây cũng là lý do không nên dịch máy móc tên ngoại lệ thành kết luận “đã có hai câu lệnh chạy đúng cùng một thời điểm”.

### 6.5. Không có ngoại lệ nhưng bất biến vẫn sai

`separate-calls` có lịch thực thi bị điều khiển như sau:

~~~text
Luồng thứ nhất: contains(42) -> false
Luồng thứ hai:  contains(42) -> false
Cả hai qua hàng rào
Luồng thứ nhất: add(42)
Luồng thứ hai:  add(42)
Kết quả: [42, 42]
~~~

Thứ tự hai lần thêm có thể đổi, nhưng cả hai đều thêm cùng giá trị, nên kết quả vẫn là hai số `42`. Mỗi lời gọi qua wrapper được bảo vệ riêng. Điều không được bảo vệ là **toàn bộ quyết định kiểm tra rồi thêm**.

Ở đây không tạo iterator, không xảy ra `ConcurrentModificationException` và `unique-invariant = false`. Thất bại được chứng minh bằng điều kiện dữ liệu mong muốn, không bằng việc chờ ngoại lệ.

Phần `whole-operation` đặt cả `contains` và `add` vào một khối `synchronized` chung. Luồng vào sau kiểm tra lại trong vùng bảo vệ và thấy phần tử đã có. Do đó chỉ còn `[42]`. Hàng rào được đặt **trước** khối khóa; nếu đặt chờ cả hai luồng bên trong cùng khóa thì một luồng có thể chờ luồng còn lại trong khi đang ngăn nó vào.

### 6.6. Ngoại lệ không hoàn tác tác dụng đã phát sinh

Trong phần `jobs`, phần tử `A` đã được thêm vào `delivered` trước khi danh sách nguồn được thêm `D` và iterator phát hiện lỗi. Vì vậy sau khi bắt ngoại lệ:

~~~text
effects-before-retry = [A]
~~~

Khi chương trình cố ý duyệt lại từ đầu, `A` được thêm lần nữa:

~~~text
effects-after-retry = [A, A, B, C, D]
~~~

`delivered` là mô hình cho một tác dụng có thể quan sát: gửi thông báo, ghi file, cập nhật hệ thống khác hoặc cộng số liệu. Ngoại lệ của iterator không tự đảo các tác dụng đó. Khối `synchronized` cũng không cung cấp cơ chế hoàn tác.

Không thể biến cách “bắt lỗi rồi chạy lại” thành đúng chỉ bằng giới hạn số lần thử. Phải định nghĩa đầu vào của một lần xử lý, cách nhận diện việc đã làm, tính lặp an toàn của thao tác và cơ chế giao dịch nếu bài toán có yêu cầu ấy.

### 6.7. Iterator không fail-fast có thể là lựa chọn hợp lệ

`CopyOnWriteArrayList` cung cấp iterator theo bản chụp mảng tại lúc tạo. Thay đổi danh sách sau đó không cập nhật mảng mà iterator ấy dùng; các thao tác thay đổi qua iterator không được hỗ trợ. [Java 17: CopyOnWriteArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html)

Vì vậy chương trình in:

~~~text
snapshot-iterator = [U, V]
snapshot-current = [U, V, W]
~~~

Không có ngoại lệ ở đây phù hợp với một chính sách duyệt đã được định nghĩa. Tuy nhiên nếu yêu cầu của ứng dụng là “lượt duyệt phải xử lý cả `W` vừa được thêm” thì bản chụp cũ không đáp ứng yêu cầu ấy. Chọn collection an toàn vẫn phải kiểm tra ngữ nghĩa quan sát dữ liệu.

## 7. Chọn cơ chế đúng theo yêu cầu

### 7.1. Dữ liệu chỉ thuộc một luồng

Cách dễ suy luận nhất trong nhiều tình huống là giới hạn quyền sở hữu: danh sách tạm chỉ do một luồng xây dựng và duyệt. Khi cần chuyển dữ liệu sang luồng khác, bàn giao kết quả bằng cơ chế công bố phù hợp và quy định rõ bên nào còn được sửa.

Giới hạn quyền sở hữu không loại bỏ lỗi tự sửa collection khi đang dùng iterator. Với thao tác xóa chọn lọc trong một luồng, có thể dùng iterator có hỗ trợ `remove` hoặc một API lọc phù hợp.

Đoạn minh họa sau nằm trong phương thức và cần `java.util.ArrayList` cùng `java.util.List`:

~~~java
List<Integer> values = new ArrayList<>(List.of(1, 2, 3, 4));
values.removeIf(value -> value % 2 == 0);
// Sau lời gọi: values chứa [1, 3].
~~~

Đây là lời gọi cập nhật do collection thực hiện theo hợp đồng API, không phải cho phép hàm điều kiện tự thêm hoặc xóa cùng nguồn. Với collection thông thường, cũng không được suy rằng `removeIf` tự tạo cơ chế phối hợp với các luồng khác.

### 7.2. Cần một lượt duyệt ổn định trên collection có thể bị sửa

Nếu dùng wrapper `Collections.synchronizedList`, việc duyệt bằng iterator, spliterator hoặc stream cần nằm trong khóa của chính wrapper theo hợp đồng API. Các bên truy cập phải tuân thủ cùng đường đồng bộ. [Java 17: Collections.synchronizedList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedList(java.util.List))

Ví dụ minh họa trong phương thức, với các kiểu từ `java.util`:

~~~java
List<Integer> shared =
        Collections.synchronizedList(new ArrayList<>(List.of(10, 20, 30)));

int total = 0;
synchronized (shared) {
    for (int value : shared) {
        total += value;
    }
}
// total là 60 đối với dữ liệu khởi tạo trên.
~~~

Khối khóa phải bao trùm việc tạo và sử dụng iterator, không chỉ lời gọi `iterator()`. Một bên khác giữ tham chiếu đến `ArrayList` gốc và sửa trực tiếp sẽ phá giao thức dù vòng lặp đã khóa wrapper.

Với view của map hoặc danh sách con, phải xác định mutex gốc mà API yêu cầu. Khóa một đối tượng bất kỳ có cùng nội dung không tạo phối hợp với bên ghi.

Ngay cả khi giữ khóa đúng, tránh để hàm gọi lại tự sửa cấu trúc qua đường không phù hợp với iterator hiện tại. Đồng thời xem xét chi phí giữ khóa, thứ tự lấy nhiều khóa và công việc có thể chặn trong thân xử lý.

### 7.3. Cần giải phóng khóa trước khi xử lý lâu

Có thể lấy một bản sao dưới khóa, rồi xử lý bản sao bên ngoài:

~~~java
List<Integer> snapshot;
synchronized (shared) {
    snapshot = new ArrayList<>(shared);
}

for (int value : snapshot) {
    // Xử lý dữ liệu của bản sao này.
}
~~~

Đoạn trên tiếp tục dùng `shared` đã khai báo ở ví dụ trước. Bản sao là một danh sách khác; việc thêm hoặc xóa phần tử ở nguồn sau lúc sao chép không đổi thành viên trong bản sao.

Đây là quyết định về thời điểm quan sát. Nó không cam kết rằng dữ liệu vẫn còn hiện hành lúc gửi kết quả ra ngoài. Nếu phần tử là đối tượng có thể sửa, hai danh sách vẫn có thể chứa cùng tham chiếu; sao chép danh sách không tự chụp toàn bộ đồ thị đối tượng.

Quan trọng hơn, thao tác lấy bản sao cũng phải an toàn. Viết `new ArrayList<>(unsafeSource)` trong lúc luồng khác sửa `unsafeSource` mà không phối hợp không phải cách tự sinh ra một bản chụp nhất quán.

### 7.4. Cần duyệt đồng thời với cập nhật

Có thể chọn collection đồng thời có chính sách duyệt thích hợp. Ví dụ iterator của `ConcurrentHashMap` không ném `ConcurrentModificationException` do cập nhật map và có tính nhất quán yếu; nó không hứa một bản chụp nguyên khối của toàn map. Iterator vẫn được thiết kế cho một luồng sử dụng tại một thời điểm. [Java 17: ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)

Điều này có thể phù hợp cho thống kê giám sát chấp nhận dữ liệu biến động. Nó có thể không phù hợp cho việc xuất một báo cáo bắt buộc mọi dòng thuộc cùng một phiên bản dữ liệu. Muốn điều kiện mạnh hơn phải có thiết kế bổ sung hoặc chọn mô hình khác.

`CopyOnWriteArrayList` thích hợp khi việc duyệt nhiều hơn sửa và chi phí sao chép khi cập nhật chấp nhận được. Bản chụp chỉ ổn định đối với thành viên/tham chiếu trong mảng của iterator; tính biến đổi bên trong phần tử vẫn là câu hỏi riêng.

Không đánh giá chất lượng hai loại iterator bằng việc loại nào ném nhiều ngoại lệ hơn. Hãy đối chiếu chính sách duyệt với nhu cầu của người sử dụng dữ liệu.

### 7.5. Cần thao tác nguyên tử theo khóa dữ liệu

Với map đồng thời, sử dụng API có hợp đồng thích hợp cho một khóa như `putIfAbsent`, `replace` có điều kiện hoặc phương thức cập nhật được lớp cụ thể bảo đảm. Việc viết hai lời gọi `get` rồi `put` vẫn có khoảng giữa cho thao tác khác chen vào. [Java 17: ConcurrentMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentMap.html)

Ví dụ minh họa độc lập trong phương thức:

~~~java
java.util.concurrent.ConcurrentMap<String, String> registrations =
        new java.util.concurrent.ConcurrentHashMap<>();

String previous = registrations.putIfAbsent("id-7", "Lan");
boolean created = previous == null;
// Trong ví dụ khởi tạo rỗng này: created là true.
~~~

Nếu quy tắc yêu cầu cập nhật nhiều khóa, hai collection hoặc cả collection và một hệ thống ngoài, một thao tác nguyên tử trên một khóa chưa bảo vệ toàn bộ quy tắc đó.

Tương tự, nếu dữ liệu là tập hợp duy nhất, một `Set` có hợp đồng đồng thời thích hợp có thể diễn đạt yêu cầu trực tiếp hơn danh sách cộng một phép kiểm tra riêng. Việc chọn cấu trúc phải đi cùng yêu cầu và các thao tác được hỗ trợ.

## 8. Những cách “sửa” chỉ che triệu chứng

### 8.1. Bắt rồi bỏ qua ngoại lệ

~~~java
try {
    // Duyệt và xử lý.
} catch (java.util.ConcurrentModificationException ex) {
    // Bỏ qua.
}
~~~

Đây là đoạn minh họa cách xử lý sai, không phải chương trình hoàn chỉnh. Nó chuyển một lỗi có thể quan sát thành một lượt xử lý bị dừng nhưng trông như thành công. Nếu hàm trả kết quả một phần, bên nhận có thể không biết đã bị bỏ sót dữ liệu.

Có thể bắt ngoại lệ tại ranh giới thích hợp để ghi chẩn đoán hoặc đánh dấu lần xử lý thất bại. Điều đó khác với coi lỗi đã được chữa và tiếp tục trả kết quả như bình thường. Tài nguyên vẫn phải được đóng theo cấu trúc quản lý tài nguyên tương ứng.

### 8.2. Đổi sang vòng lặp chỉ số để hết lỗi

~~~java
for (int index = 0; index < list.size(); index++) {
    consume(list.get(index));
}
~~~

Đoạn minh họa trên giả sử `list` và `consume` đã có. Nó không tạo iterator fail-fast, nhưng các lần `size` và `get` vẫn là những bước khác nhau. Nếu phần tử bị xóa, chỉ số có thể bị dịch, dữ liệu có thể bị bỏ qua hoặc đọc không phù hợp; nếu nhiều luồng cùng truy cập thiếu phối hợp thì vấn đề đồng bộ vẫn còn.

Đổi loại vòng lặp chỉ có giá trị khi thuật toán mới thực sự có hợp đồng sửa đổi và bảo vệ phù hợp. Việc ít thấy ngoại lệ hơn tự nó không phải cải thiện tính đúng.

### 8.3. Cho luồng ngủ để “tránh đụng nhau”

Thêm độ trễ chỉ thay đổi lịch thực thi trong vài lần chạy. Nó không chứng minh rằng luồng ghi đã hoàn tất hoặc các ghi đã được công bố bằng quan hệ cần thiết.

Khi cần chờ một sự kiện, dùng công cụ phối hợp có hợp đồng rõ như `join`, latch hoặc future phù hợp với bài toán. Trong kiểm thử, dùng hàng rào/latch để điều khiển điểm giao nhau; không biến thời gian chờ ngẫu nhiên thành lập luận bảo đảm.

### 8.4. Đặt `volatile` lên biến tham chiếu collection

Một tham chiếu `volatile List<?>` có thể tham gia công bố đối tượng hoặc thay một bản dữ liệu theo giao thức phù hợp. Nó không làm cho các thao tác thêm/xóa bên trong cùng một `ArrayList` trở nên nguyên tử, cũng không tự bảo vệ phần tử có thể sửa.

Nếu chọn mô hình thay toàn bộ bản dữ liệu, phải quy định bản đã công bố có tiếp tục bị sửa không và người đọc dùng một bản nào trong suốt thao tác. Không trộn ý tưởng thay bản dữ liệu với việc nhiều luồng sửa tự do cùng một bản.

### 8.5. Đổi tên cơ chế thành “fail-safe”

Tài liệu Java mô tả iterator theo hợp đồng cụ thể như fail-fast, bản chụp hoặc nhất quán yếu. “Fail-safe” thường được dùng không chính thức trong trao đổi, nhưng một nhãn đó không đủ để suy ra chính sách quan sát, quyền xóa hay tính nguyên tử. Tài liệu package mô tả rõ nhóm iterator nhất quán yếu và các đặc điểm của collection đồng thời. [Java 17: java.util.concurrent](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html)

Khi đọc một hướng dẫn dùng từ này, hãy chuyển nó thành câu hỏi cụ thể: iterator lấy dữ liệu lúc nào, cập nhật nào có thể xuất hiện, có hỗ trợ `remove` không, và có thể chia sẻ cùng iterator cho nhiều luồng không?

## 9. Stream và spliterator vẫn cần hợp đồng nguồn dữ liệu

Thay vòng `for-each` bằng `stream().forEach(...)` không tự thêm khóa quanh nguồn. Stream yêu cầu các hàm hành vi không can thiệp không phù hợp vào nguồn trong lúc thực thi; đối với nguồn đồng thời, chính sách nguồn có thể cho phép cập nhật nhưng vẫn phải hiểu kết quả mong đợi. [Java 17: quy tắc non-interference của Stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/package-summary.html#NonInterference)

Vì xử lý stream có thể trì hoãn đến thao tác kết thúc, cần phân biệt thời điểm dựng pipeline và thời điểm nguồn được duyệt. Nếu dùng wrapper đồng bộ và dựa vào khóa ngoài, việc chỉ khóa lúc tạo stream rồi thực thi thao tác kết thúc bên ngoài khóa không bảo vệ lượt duyệt.

Spliterator cũng có chính sách ràng buộc nguồn và phát hiện can thiệp riêng. Với thao tác duyệt hàng loạt, việc phát hiện có thể được dồn đến một điểm kiểm tra sau khi đã gọi hàm xử lý nhiều phần tử. Do đó, ngoại lệ không chứng minh rằng chưa có tác dụng nào phát sinh. [Java 17: Spliterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Spliterator.html)

`parallelStream` thêm khả năng có nhiều tác vụ cùng xử lý. Nó không sửa một nguồn thiếu an toàn và không tự làm một danh sách kết quả bên ngoài trở thành nơi ghi đồng thời hợp lệ. Khi cần kết quả tổng hợp, dùng phép giảm hoặc bộ thu có hợp đồng phù hợp, đồng thời bảo đảm nguồn được dùng đúng.

## 10. Điều tra lỗi và kiểm chứng điều kiện đúng

Khi gặp `ConcurrentModificationException`, đi từ đối tượng đang được duyệt đến mọi đường sửa nó:

1. Xác định lớp triển khai thực, wrapper và view, thay vì chỉ nhìn kiểu khai báo `List` hay `Map`.
2. Xác định iterator được tạo ở đâu, có bị lưu lại qua nhiều lời gọi hay qua một lần cập nhật không.
3. Tìm việc sửa trực tiếp, sửa qua alias, qua collection gốc của view và qua hàm gọi lại.
4. Phân biệt sửa do cùng luồng với sửa do luồng khác; tên ngoại lệ không cho sẵn câu trả lời.
5. Kiểm tra giao thức khóa, công bố dữ liệu và tuổi thọ iterator như các vấn đề riêng.
6. Ghi rõ kết quả nghiệp vụ cần giữ trước khi thay cách duyệt hoặc thay collection.

Thông tin hữu ích cho chẩn đoán gồm dấu thời gian, luồng, danh tính collection, thao tác cập nhật và ranh giới lượt xử lý. Chú ý rằng việc tự ghi log nội dung một collection đang bị sửa thiếu phối hợp cũng có thể trở thành một lượt duyệt không an toàn.

Trong kiểm thử, hãy kiểm tra trực tiếp các điều kiện có ý nghĩa:

- Đủ đúng tập mã công việc thuộc đầu vào đã chọn.
- Không có mã bị xử lý hai lần khi yêu cầu mỗi mã một lần.
- Tổng số liệu hoặc số lượng đăng ký cuối cùng đúng.
- Các cập nhật thất bại được báo rõ và không bị diễn giải thành thành công một phần.
- Kết quả của bản chụp và kết quả theo dữ liệu hiện hành được phân biệt.

Chạy một phép thử nhiều lần có thể tìm thêm lịch gây lỗi nhưng không chứng minh không còn lịch khác. Một phép thử luôn mong đợi `ConcurrentModificationException` từ cuộc đua thiếu đồng bộ có thể tự mang giả định sai. Cần kết hợp hợp đồng API, lập luận về thứ tự truy cập và phép thử có lịch được điều khiển.

## 11. Bài tập tự kiểm tra

### Bài 1 — Ngoại lệ trong một luồng

Một phương thức tạo iterator trên `ArrayList`, gọi một hàm trợ giúp để thêm phần tử vào chính danh sách ấy rồi tiếp tục `next`. Không có luồng phụ. Có thể loại trừ `ConcurrentModificationException` không?

**Đáp án:** Không. Cần xét hàm trợ giúp đã sửa cấu trúc ngoài đường iterator như thế nào. Số luồng không quyết định tính hợp lệ của iterator.

### Bài 2 — Đã khóa nhưng vẫn lỗi

Tất cả mã nằm trong `synchronized (list)` trên wrapper đồng bộ. Trong vòng lặp, hàm xử lý phần tử gọi `list.remove`. Người viết kết luận JVM đã không tôn trọng khóa vì vẫn thấy ngoại lệ. Kết luận này sai ở đâu?

**Đáp án:** Khóa chỉ phối hợp các bên dùng cùng monitor; nó không cấm luồng giữ khóa tái nhập và tự sửa danh sách. Phải chọn đường cập nhật phù hợp với iterator hoặc tách pha cập nhật khỏi pha duyệt.

### Bài 3 — Nội dung được khôi phục

Tạo iterator trên `[1, 2]`, thêm `3` rồi xóa `3`, sau đó tiếp tục iterator cũ. Có thể chứng minh an toàn bằng cách so sánh danh sách cuối với ban đầu không?

**Đáp án:** Không. So sánh hai trạng thái không nói rằng đã không có sửa đổi ở giữa. Với ví dụ `ArrayList` đã kiểm chứng, iterator cũ báo thay đổi dù nội dung cuối giống ban đầu.

### Bài 4 — Không lỗi nhưng có mã trùng

Hai luồng dùng `synchronizedList`, mỗi luồng gọi `contains` rồi `add` nếu chưa có. Hệ thống chạy không có ngoại lệ nhưng xuất hiện mã trùng. Nên thêm khối `catch` hay thay ranh giới thao tác?

**Đáp án:** Thay ranh giới thao tác hoặc cấu trúc dữ liệu. Phải bảo vệ toàn bộ quyết định kiểm tra rồi thêm bằng giao thức chung, hoặc dùng thao tác nguyên tử diễn đạt trực tiếp yêu cầu. Bắt ngoại lệ không ngăn hai lần quyết định cùng dựa trên trạng thái “chưa có”.

### Bài 5 — Bản chụp có đúng yêu cầu không?

Một iterator của `CopyOnWriteArrayList` được tạo trước khi đăng ký người nghe mới. Lượt thông báo hiện tại không gọi người nghe mới và không có ngoại lệ. Đó có phải lỗi collection không?

**Đáp án:** Không thể kết luận như vậy. Đó là hành vi bản chụp của iterator. Cần định nghĩa người nghe thêm trong lúc thông báo sẽ tham gia lượt hiện tại hay lượt tiếp theo; nếu yêu cầu khác thì chọn hoặc thiết kế cơ chế tương ứng.

### Bài 6 — Thử lại sau tác dụng bên ngoài

Một vòng lặp đã gửi hai thông báo trước khi iterator báo lỗi. Người viết bắt ngoại lệ rồi chạy lại toàn bộ vòng lặp. Có bảo đảm mỗi thông báo chỉ gửi một lần không?

**Đáp án:** Không. Ngoại lệ không hoàn tác hai lần gửi trước đó. Phải thiết kế tính lặp an toàn, dấu nhận diện tác vụ hoặc giao dịch phù hợp; chỉ thay iterator hay giới hạn số lần thử chưa đáp ứng yêu cầu.

### Bài 7 — Phần tử thay đổi mà danh sách không đổi

Danh sách chứa các đối tượng số dư. Không thêm hoặc xóa phần tử, nhưng một luồng sửa trường số dư và luồng khác đọc chúng. Không thấy ngoại lệ có chứng minh an toàn không?

**Đáp án:** Không. Cần xét hợp đồng đồng bộ của các đối tượng số dư và các trường được đọc/ghi. Theo dõi cấu trúc collection không phải theo dõi mọi trạng thái nằm bên trong phần tử.

### Bài 8 — Kiểm thử âm tính

Một bài kiểm thử tạo hai luồng đọc/ghi `ArrayList` tự do và chạy một triệu lần không thấy `ConcurrentModificationException`. Có thể dùng kết quả đó để bỏ khóa trong mã sản phẩm không?

**Đáp án:** Không. Phép thử chưa tạo ra bảo đảm đồng bộ hoặc chứng minh mọi lịch thực thi. Hãy xác định các truy cập xung đột, hợp đồng dữ liệu và bất biến cần giữ; sau đó chọn giao thức đúng và kiểm tra kết quả bằng lịch phối hợp có chủ đích.

Khi đánh giá một thay đổi trên collection, câu hỏi quyết định là: **cơ chế nào bảo vệ thao tác và ngữ nghĩa quan sát mà bài toán cần?** Fail-fast hỗ trợ phát hiện sai cách dùng; thiết kế quyền sở hữu, đồng bộ và bất biến mới là cơ sở để lập luận tính đúng.
