# CopyOnWriteArrayList, CopyOnWriteArraySet và chi phí khi ghi

Một danh sách người nhận sự kiện có thể được duyệt hàng nghìn lần nhưng hiếm khi thêm hoặc gỡ người nhận. Khi đang phát một sự kiện, ứng dụng thường muốn dùng đúng nhóm người nhận của lượt đó, dù bên khác vừa đăng ký hoặc hủy đăng ký.

`CopyOnWriteArrayList` và `CopyOnWriteArraySet` giải quyết kiểu bài toán này bằng chiến lược **sao chép khi ghi (copy-on-write)**: cập nhật tạo ra một phiên bản mảng mới, còn lượt duyệt đã lấy mảng cũ có thể tiếp tục trên phiên bản ấy.

Lợi ích nằm ở lượt đọc ổn định và không cần giữ khóa ngoài trong suốt iterator. Cái giá được chuyển sang bên ghi, việc cấp phát mảng và thời gian các phiên bản cũ còn được giữ.

Để dùng đúng, cần phân biệt:

- **Collection hiện tại:** đối tượng vẫn có thể được thêm, xóa hoặc thay phần tử.
- **Phiên bản mảng:** một trạng thái của dãy tham chiếu phần tử.
- **Iterator theo bản chụp:** lượt duyệt gắn với phiên bản tại lúc tạo iterator.
- **Phần tử có thể sửa:** đối tượng được tham chiếu bên trong mảng; nó không tự trở thành bất biến.
- **Chi phí ghi:** không chỉ phép gán mới, mà có thể gồm tìm kiếm, sao chép, cấp phát, chờ bên ghi khác và thu hồi bộ nhớ.

Bài học bắt đầu từ mô hình mảng, đi qua hợp đồng List/Set và ví dụ chạy được, sau đó phân tích khi nào chi phí này đáng chấp nhận.

## 1. Mảng mới cho bên ghi, mảng cũ cho lượt duyệt

Có thể hình dung một `CopyOnWriteArrayList<String>` như sau:

~~~text
Collection hiện tại -> mảng V1: [A, B, C]
Iterator I1         -> mảng V1: [A, B, C]
~~~

Khi thêm `D`:

~~~text
Collection hiện tại -> mảng V2: [A, B, C, D]
Iterator I1         -> mảng V1: [A, B, C]
~~~

Iterator I1 không chuyển sang V2 giữa chừng. Một iterator được tạo sau khi cập nhật có thể bắt đầu trên V2.

Hợp đồng `CopyOnWriteArrayList` quy định iterator giữ bản chụp tại thời điểm tạo, không phản ánh các lần thêm, xóa hoặc thay phần tử sau đó và không ném `ConcurrentModificationException` do những cập nhật ấy. [Java 17: CopyOnWriteArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html)

“Không thấy cập nhật mới” ở đây là ngữ nghĩa có chủ đích, không phải lỗi hiển thị dữ liệu. Nếu yêu cầu của ứng dụng là lượt duyệt đang chạy phải lập tức phản ánh mọi lần đăng ký mới, chính sách bản chụp này có thể không phù hợp.

### 1.1. Iterator không phải bên sao chép cả mảng

Trong OpenJDK 17, iterator nhận tham chiếu đến mảng hiện tại và giữ nó. Không phải mỗi lần tạo iterator đều sao chép toàn bộ dãy phần tử.

Đây là lý do tên chiến lược là sao chép **khi ghi**, không phải sao chép khi mọi lần đọc. Những API như `toArray` có hợp đồng lấy mảng kết quả riêng và có thể có chi phí khác; không gom mọi API đọc vào cùng một cơ chế.

### 1.2. Việc ghi được phối hợp

Nhiều bên ghi không tự do cùng sửa một mảng đang được iterator dùng. Triển khai OpenJDK 17 phối hợp các cập nhật bằng khóa nội bộ và công bố tham chiếu mảng hiện tại qua trường `volatile`.

Những chi tiết đó giúp giải thích cách phiên bản mới xuất hiện và mảng cũ không bị sửa. Chúng không phải lời hứa rằng mọi phương thức đều không khóa, không chờ hoặc dùng cùng một thuật toán ở mọi JDK. [Mã nguồn OpenJDK 17: CopyOnWriteArrayList](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/concurrent/CopyOnWriteArrayList.java)

Bên đọc dùng iterator không phải giữ khóa ngoài suốt lượt duyệt. Tuy nhiên nếu nhiều luồng cùng cố ghi liên tục, vẫn có chi phí phối hợp giữa các bên ghi.

## 2. Chọn List hay Set theo dữ liệu

| Thuộc tính | CopyOnWriteArrayList | CopyOnWriteArraySet |
|---|---|---|
| Vai trò | Dãy có vị trí, cho phép trùng. | Tập các phần tử không trùng theo phép bằng nhau. |
| Truy cập theo chỉ số | Có `get`, `set` và các API của List. | Không có API truy cập theo chỉ số. |
| Thêm trùng | `add` vẫn thêm một phần tử nữa. | `add` giữ nguyên và trả `false` nếu đã có phần tử bằng nhau. |
| Lượt duyệt | Theo thứ tự danh sách, trên bản chụp. | Theo thứ tự thêm, trên bản chụp. |
| Thay đổi qua iterator | Không hỗ trợ. | Không hỗ trợ `remove`. |
| Hướng dùng điển hình | Danh sách nhỏ, duyệt nhiều, cập nhật ít. | Tập nhỏ, duyệt nhiều, cập nhật ít, cần loại trùng. |

`CopyOnWriteArraySet` dùng một `CopyOnWriteArrayList` bên trong; tài liệu hướng nó vào các tập thường nhỏ và có thao tác đọc vượt xa thao tác thay đổi. [Java 17: CopyOnWriteArraySet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArraySet.html)

Nó không phải `HashSet` có thêm một khóa. Đặc biệt, việc kiểm tra phần tử đã có thường dựa trên duyệt mảng và so sánh, không có bảng băm giúp suy ra chi phí tra cứu trung bình như hash set.

### 2.1. Thứ tự thêm không phải thứ tự sắp xếp

Nếu thêm `"two"` rồi `"one"`, CopyOnWriteArraySet giữ thứ tự thêm cho iterator, không tự sắp xếp chuỗi.

Hai luồng cùng thêm hai phần tử khác nhau thì thứ tự chấp nhận có thể phụ thuộc lịch thực thi. Một lượt duyệt giữ thứ tự của phiên đã lấy, nhưng không tạo ra một thứ tự nghiệp vụ bên ngoài chưa được định nghĩa.

### 2.2. Phép bằng nhau cần ổn định

Set xét sự bằng nhau của phần tử theo hợp đồng `Set`. Hai đối tượng khác tham chiếu nhưng `equals` bằng nhau không được coi là hai thành viên riêng. [Java 17: Set](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html)

Nếu sửa các trường ảnh hưởng đến `equals` của phần tử sau khi đã thêm, chính ý nghĩa “không trùng” có thể bị phá vỡ. Việc không dùng bảng băm không làm sự thay đổi danh tính theo giá trị trở nên vô hại.

Ưu tiên phần tử bất biến hoặc một khóa nhận diện ổn định nếu tập dùng để quản lý đăng ký.

### 2.3. Null và trùng vẫn là hai quy tắc riêng

`CopyOnWriteArrayList` chấp nhận `null` và cho phép nhiều phần tử bằng nhau. Trong các ví dụ của bài, `CopyOnWriteArraySet` cũng chứa được `null` nhưng chỉ giữ một phần tử null theo quy tắc tập.

Điều này không suy rộng sang các set đồng thời khác. Chẳng hạn set từ `ConcurrentHashMap.newKeySet` không chấp nhận null do hợp đồng map nền. Khi đổi loại collection, kiểm tra lại chính sách phần tử chứ không chỉ kiểm tra tên “đồng thời”.

## 3. Iterator chỉ đọc không làm collection bất biến

Collection vẫn có các phương thức ghi, nhưng iterator bản chụp không là một đường sửa collection:

- `Iterator.remove` không được hỗ trợ.
- `ListIterator.remove`, `set` và `add` không được hỗ trợ.
- Các lời gọi đó ném `UnsupportedOperationException`.

Hợp đồng iterator/list iterator ghi rõ không cần đồng bộ trong lúc duyệt bản chụp, đồng thời không hỗ trợ các phương thức sửa nói trên. [Java 17: iterator của CopyOnWriteArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html#listIterator())

Không được chuyển máy móc mẫu “duyệt rồi `iterator.remove`” từ `ArrayList` sang CopyOnWriteArrayList.

Có thể cập nhật qua chính collection nếu phù hợp với ngữ nghĩa yêu cầu. Iterator đã có vẫn tiếp tục dùng bản cũ; nó không tự bỏ phần tử vừa bị xóa khỏi collection hiện tại.

Ví dụ một iterator đã chứa người nhận L. Bên khác gỡ L thành công khỏi set hiện tại. Iterator cũ vẫn có thể gọi L sau đó. Nếu hệ thống yêu cầu “sau khi hủy đăng ký trả về thì tuyệt đối không còn lời gọi nào đang hoặc sắp chạy”, cần giao thức hủy/chờ riêng. Chỉ xóa khỏi collection không cung cấp bảo đảm mạnh đó.

## 4. Bản chụp là bản chụp tham chiếu

Mảng lưu các tham chiếu đến phần tử. Sao chép mảng không tự sao chép sâu từng đối tượng.

~~~text
Mảng cũ:  [tham chiếu P]
Mảng mới: [tham chiếu P, tham chiếu Q]

Cả hai vẫn có thể trỏ đến cùng đối tượng P.
~~~

Nếu P có trường thay đổi, iterator cũ có thể trả về P với nội dung mới. “Mảng cũ không đổi” nghĩa là các vị trí và tham chiếu trong mảng đó ổn định, không phải toàn bộ đồ thị đối tượng mà các tham chiếu dẫn tới bị đóng băng.

Ví dụ `String` là phần tử thuận lợi để giải thích bản chụp vì đối tượng chuỗi không bị sửa tại chỗ. Ví dụ `StringBuilder` sẽ cho thấy giới hạn rõ hơn trong chương trình bên dưới.

Về công bố dữ liệu, lớp có bảo đảm nhất quán bộ nhớ đối với các hành động trước khi đưa đối tượng vào collection và các truy cập tương ứng từ luồng khác. Điều này không tự đồng bộ mọi sửa đổi mới bên trong phần tử về sau.

Do đó cần hai quyết định độc lập:

1. Collection bảo vệ việc quản lý thành viên và lượt duyệt ra sao?
2. Chính đối tượng thành viên có được đọc/ghi an toàn giữa các luồng không?

## 5. Thêm khi chưa có và thêm theo lô

### 5.1. contains rồi add vẫn là hai lời gọi

Với một CopyOnWriteArrayList:

~~~java
if (!members.contains(name)) {
    members.add(name);
}
~~~

Đoạn minh họa giả sử các biến đã có. Hai luồng có thể cùng thấy chưa có rồi cùng thêm. Từng phương thức an toàn không gộp cả quyết định thành một hành động.

Dùng `addIfAbsent` nếu cần thao tác thêm khi chưa có trên List. Với Set, `add` đã biểu đạt quy tắc không thêm phần tử bằng nhau.

### 5.2. addIfAbsent không biến List thành Set

Một danh sách đang có `[A, A]` vẫn có hai phần tử `A` sau `addIfAbsent("A")`. Phương thức chỉ quyết định lần thêm mới, không dọn các phần tử trùng đã tồn tại.

Nếu yêu cầu dữ liệu luôn là một tập, dùng cấu trúc Set để biểu đạt yêu cầu trực tiếp, thay vì trộn `add` thông thường và `addIfAbsent` rồi mong List luôn duy nhất.

### 5.3. addAllAbsent trả số phần tử mới

`CopyOnWriteArrayList.addAllAbsent` thêm các phần tử chưa có theo thứ tự nguồn và trả về số phần tử đã thêm. Nó cũng tránh thêm lặp lại các ứng viên bằng nhau trong cùng đợt.

Ví dụ danh sách `[A, A]` nhận `[B, A, B, C]` sẽ thêm `B` và `C`, trả `2`, thành `[A, A, B, C]`. Các `A` cũ không bị loại.

### 5.4. Ghi theo lô giảm các lần tạo phiên, nhưng không miễn mọi chi phí

Khi cần thêm nhiều phần tử đã sẵn, một lần `addAll` thường tránh việc tạo một phiên mảng đích cho từng phần tử riêng. Khi cần loại trùng, `addAllAbsent` hoặc API của Set còn có chi phí kiểm tra bằng nhau.

Mã nguồn CopyOnWriteArraySet của OpenJDK 17 chuyển `add` thành `addIfAbsent` và `addAll` thành `addAllAbsent` trên danh sách nền. [OpenJDK 17: CopyOnWriteArraySet](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/concurrent/CopyOnWriteArraySet.java)

Nguồn của một phép thêm theo lô cũng phải được đọc hợp lệ. Đích là collection đồng thời không tự làm một collection nguồn đang bị sửa thiếu phối hợp trở nên an toàn.

## 6. Chương trình kiểm chứng đầy đủ

Lưu tệp `CopyOnWriteCostDemo.java`. Chương trình dùng Java 17, đã được biên dịch với `javac --release 17` và chạy trên OpenJDK Zulu 24.0.2; đây không phải tuyên bố đã chạy trên JVM 17.

Phần sửa từ luồng phụ được chờ hoàn tất trước khi tiếp tục đọc iterator cũ để stdout xác định. Phần tranh chấp thêm Set dùng hàng rào trước thao tác thêm. Không dùng thời gian ngủ để đoán thứ tự luồng.

Hai dòng cuối chỉ tính **mô hình số tham chiếu cũ được sao chép**, không đo thời gian, số byte cấp phát hay số lần thu gom rác.

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Iterator;
import java.util.List;
import java.util.ListIterator;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CopyOnWriteArraySet;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class CopyOnWriteCostDemo {
    static <T> List<T> drain(Iterator<T> iterator) {
        List<T> result = new ArrayList<>();
        iterator.forEachRemaining(result::add);
        return result;
    }

    static String unsupported(Runnable action) {
        try {
            action.run();
            return "completed";
        } catch (UnsupportedOperationException ex) {
            return ex.getClass().getSimpleName();
        }
    }

    static void complete(Thread thread, AtomicReference<Throwable> error)
            throws InterruptedException {
        thread.join(5000);
        if (thread.isAlive()) {
            thread.interrupt();
            throw new AssertionError("Thread did not finish");
        }
        if (error.get() != null) {
            throw new AssertionError("Thread failed", error.get());
        }
    }

    public static void main(String[] args) throws Exception {
        CopyOnWriteArrayList<String> names =
                new CopyOnWriteArrayList<>(List.of("A", "B", "C"));
        Iterator<String> oldNames = names.iterator();
        List<String> firstPass = new ArrayList<>();
        firstPass.add(oldNames.next());

        AtomicReference<Throwable> editError = new AtomicReference<>();
        Thread editor = new Thread(() -> {
            try {
                names.set(0, "X");
                names.remove("B");
                names.add("D");
            } catch (Throwable ex) {
                editError.set(ex);
            }
        }, "editor");
        editor.setDaemon(true);
        editor.start();
        complete(editor, editError);
        oldNames.forEachRemaining(firstPass::add);
        System.out.println("old-list-iterator = " + firstPass);
        System.out.println("current-list = " + names);
        System.out.println("new-list-iterator = " + drain(names.iterator()));

        Iterator<String> noRemove = names.iterator();
        noRemove.next();
        System.out.println("iterator-remove = " + unsupported(noRemove::remove));
        ListIterator<String> noEdit = names.listIterator();
        noEdit.next();
        System.out.println("listIterator-set = "
                + unsupported(() -> noEdit.set("Z")));
        System.out.println("listIterator-add = "
                + unsupported(() -> noEdit.add("Z")));

        CopyOnWriteArrayList<String> duplicates =
                new CopyOnWriteArrayList<>(List.of("A", "A"));
        System.out.println("addIfAbsent-existing = " + duplicates.addIfAbsent("A"));
        System.out.println("addAllAbsent-count = "
                + duplicates.addAllAbsent(List.of("B", "A", "B", "C")));
        System.out.println("list-keeps-old-duplicates = " + duplicates);

        CopyOnWriteArraySet<String> receivers =
                new CopyOnWriteArraySet<>(List.of("one", "two"));
        Iterator<String> beforeChange = receivers.iterator();
        System.out.println("set-duplicate-add = " + receivers.add(new String("one")));
        receivers.remove("one");
        receivers.add("three");
        System.out.println("old-set-iterator = " + drain(beforeChange));
        System.out.println("current-set = " + receivers);
        Iterator<String> setCursor = receivers.iterator();
        setCursor.next();
        System.out.println("set-iterator-remove = " + unsupported(setCursor::remove));

        StringBuilder payload = new StringBuilder("draft");
        CopyOnWriteArrayList<StringBuilder> payloads =
                new CopyOnWriteArrayList<>(List.of(payload));
        Iterator<StringBuilder> payloadCursor = payloads.iterator();
        payload.append("-edited");
        StringBuilder observed = payloadCursor.next();
        System.out.println("snapshot-element = " + observed);
        System.out.println("snapshot-same-object = " + (observed == payload));

        CopyOnWriteArrayList<String> nullable =
                new CopyOnWriteArrayList<>(Arrays.asList("N", null, "N"));
        CopyOnWriteArraySet<String> nullableSet = new CopyOnWriteArraySet<>(nullable);
        System.out.println("nullable-list = " + nullable);
        System.out.println("nullable-set = " + nullableSet);

        CopyOnWriteArrayList<Integer> versions = new CopyOnWriteArrayList<>(List.of(1));
        Iterator<Integer> versionOne = versions.iterator();
        versions.add(2);
        Iterator<Integer> versionTwo = versions.iterator();
        versions.clear();
        System.out.println("saved-version-one = " + drain(versionOne));
        System.out.println("saved-version-two = " + drain(versionTwo));
        System.out.println("versions-current = " + versions);

        CopyOnWriteArraySet<String> sharedSet = new CopyOnWriteArraySet<>();
        AtomicInteger accepted = new AtomicInteger();
        AtomicReference<Throwable> addError = new AtomicReference<>();
        CyclicBarrier ready = new CyclicBarrier(2);
        Runnable register = () -> {
            try {
                ready.await(5, TimeUnit.SECONDS);
                if (sharedSet.add("member")) {
                    accepted.incrementAndGet();
                }
            } catch (Throwable ex) {
                addError.compareAndSet(null, ex);
            }
        };
        Thread left = new Thread(register, "left");
        Thread right = new Thread(register, "right");
        left.setDaemon(true);
        right.setDaemon(true);
        left.start();
        right.start();
        complete(left, addError);
        complete(right, addError);
        System.out.println("concurrent-set-accepted = " + accepted.get());
        System.out.println("concurrent-set = " + sharedSet);

        CopyOnWriteArrayList<Integer> individually =
                new CopyOnWriteArrayList<>(List.of(0, 1));
        for (int value : List.of(2, 3, 4)) {
            individually.add(value);
        }
        CopyOnWriteArrayList<Integer> batched =
                new CopyOnWriteArrayList<>(List.of(0, 1));
        batched.addAll(List.of(2, 3, 4));
        System.out.println("individual-content = " + individually);
        System.out.println("batch-content = " + batched);

        long initial = 10_000;
        long additions = 1_000;
        long individualExistingCopies =
                additions * initial + additions * (additions - 1) / 2;
        System.out.println("model-individual-existing-references = "
                + individualExistingCopies);
        System.out.println("model-batch-existing-references = " + initial);
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~shell
javac --release 17 -encoding UTF-8 CopyOnWriteCostDemo.java
java CopyOnWriteCostDemo
~~~

Stdout đã kiểm chứng:

~~~text
old-list-iterator = [A, B, C]
current-list = [X, C, D]
new-list-iterator = [X, C, D]
iterator-remove = UnsupportedOperationException
listIterator-set = UnsupportedOperationException
listIterator-add = UnsupportedOperationException
addIfAbsent-existing = false
addAllAbsent-count = 2
list-keeps-old-duplicates = [A, A, B, C]
set-duplicate-add = false
old-set-iterator = [one, two]
current-set = [two, three]
set-iterator-remove = UnsupportedOperationException
snapshot-element = draft-edited
snapshot-same-object = true
nullable-list = [N, null, N]
nullable-set = [N, null]
saved-version-one = [1]
saved-version-two = [1, 2]
versions-current = []
concurrent-set-accepted = 1
concurrent-set = [member]
individual-content = [0, 1, 2, 3, 4]
batch-content = [0, 1, 2, 3, 4]
model-individual-existing-references = 10499500
model-batch-existing-references = 10000
~~~

Chương trình chuyển lỗi trong luồng phụ về luồng chính và kiểm tra thời hạn hoàn tất. Không bỏ qua lỗi rồi vẫn báo các kết quả tranh chấp như thể thành công.

## 7. Diễn giải kết quả

### 7.1. Iterator cũ và mới thuộc hai phiên

~~~text
old-list-iterator = [A, B, C]
current-list = [X, C, D]
new-list-iterator = [X, C, D]
~~~

Iterator cũ đã lấy `A` trước khi luồng ghi thay vị trí đầu, xóa `B` và thêm `D`. Phần còn lại vẫn trả `B, C` của cùng phiên cũ.

Iterator mới thấy phiên hiện tại `[X, C, D]`. Không có lý do để mong iterator cũ tự chuyển sang phiên đó.

### 7.2. Từ chối sửa qua iterator

Ba kết quả `UnsupportedOperationException` của List và kết quả tương ứng của Set xác nhận đường sửa iterator không được hỗ trợ.

Đây không phải dấu hiệu collection không thể sửa. Chương trình vẫn dùng `set`, `remove` và `add` trên collection thành công. Cần phân biệt năng lực của collection với năng lực của lượt duyệt.

### 7.3. List giữ các phần tử trùng đã có

~~~text
addIfAbsent-existing = false
addAllAbsent-count = 2
list-keeps-old-duplicates = [A, A, B, C]
~~~

Không có một đợt “dọn trùng toàn bộ”. Các phương thức điều kiện chỉ quyết định những phần tử của lần thêm mới.

### 7.4. Xóa khỏi Set không xóa khỏi iterator đã lấy

~~~text
set-duplicate-add = false
old-set-iterator = [one, two]
current-set = [two, three]
~~~

`new String("one")` khác đối tượng với chuỗi sẵn có nhưng bằng nhau về nội dung, nên không được thêm thành một thành viên thứ hai.

Sau khi gỡ `one` và thêm `three`, iterator cũ vẫn chứa `one, two`. Một registry thông báo cần chấp nhận hoặc xử lý rõ việc một lượt đã bắt đầu còn dùng nhóm người nhận cũ.

### 7.5. Sửa phần tử không phải sửa mảng

~~~text
snapshot-element = draft-edited
snapshot-same-object = true
~~~

Iterator giữ tham chiếu đến cùng `StringBuilder`. Việc thêm `-edited` diễn ra trong một luồng duy nhất ở ví dụ này, nên nó chỉ chứng minh bản chụp không sâu; không dùng nó để suy rằng `StringBuilder` an toàn khi nhiều luồng cùng sửa.

### 7.6. Các phiên đã lấy sống độc lập với collection hiện tại

~~~text
saved-version-one = [1]
saved-version-two = [1, 2]
versions-current = []
~~~

Sau `clear`, hai iterator vẫn giữ dữ liệu của các phiên trước. Nội dung đã không còn là thành viên của phiên hiện tại vẫn được cần đến để thực hiện hợp đồng iterator.

Đây vừa là lợi ích về ngữ nghĩa, vừa dẫn tới chi phí giữ bộ nhớ nếu các iterator được lưu quá lâu.

### 7.7. Set chỉ chấp nhận một lần thêm cùng phần tử

~~~text
concurrent-set-accepted = 1
concurrent-set = [member]
~~~

Hai luồng cùng thử `add("member")`, không có xóa trong giai đoạn thử. Một bên nhận `true` và bên còn lại nhận `false`. Tính duy nhất do thao tác Set thực hiện, không dựa vào một phép `contains` tách riêng.

Nếu phần tử bị xóa rồi thêm lại ở một thời điểm khác, một lần thêm sau có thể thành công trong vòng đời mới. Kết quả “một lần” ở đây gắn với giai đoạn không có xóa của phép thử.

### 7.8. Cùng kết quả cuối không có nghĩa cùng chi phí hoặc cùng các trạng thái giữa chừng

~~~text
individual-content = [0, 1, 2, 3, 4]
batch-content = [0, 1, 2, 3, 4]
~~~

Ba lần `add` và một lần `addAll` cho cùng kết quả khi chạy tuần tự. Nhưng cách thứ nhất tạo nhiều bước công bố hơn; các iterator được tạo giữa các lần thêm có thể lấy những phiên trung gian khác nhau.

Chọn thêm theo lô còn là quyết định về nhịp công bố dữ liệu. Không đổi sang cách lô chỉ để tối ưu rồi quên xem người đọc có cần thấy từng bước hay không.

## 8. Chi phí khi ghi nằm ở đâu?

### 8.1. Sao chép dãy tham chiếu

Giả sử mảng hiện tại có `n` phần tử. Một lần thêm thực sự thường phải tạo mảng đích có đủ chỗ và chuyển các tham chiếu cũ sang.

Với một lần thêm cuối trên mô hình này, lượng tham chiếu cũ cần sao chép tỷ lệ với `n`. Không giống `ArrayList` thông thường còn dung lượng dự trữ để nhiều lần append chỉ ghi vào ô trống, một đợt ghi COW phải giữ nguyên phiên mảng đang có thể được người đọc dùng.

Các đối tượng phần tử không nhất thiết được nhân bản. Sao chép `n` tham chiếu khác với sao chép sâu `n` đối tượng lớn.

### 8.2. Nhiều lần thêm riêng tạo tổng chi phí tăng nhanh

Bắt đầu có `n` phần tử, thêm riêng `m` phần tử. Trong mô hình sao chép mảng cho từng lần thêm, số tham chiếu cũ được chuyển là:

~~~text
n + (n + 1) + ... + (n + m - 1)
= m*n + m*(m - 1)/2
~~~

Với `n = 10.000` và `m = 1.000`:

~~~text
10.499.500 tham chiếu cũ được sao chép theo mô hình.
~~~

Nếu đã có sẵn cả lô `1.000` phần tử và thêm vào một lần trên mảng đích không rỗng, phần tham chiếu cũ cần chuyển cho lần mở rộng ấy là `10.000`. Ngoài ra còn các thao tác với dữ liệu đầu vào và phần tử mới.

Hai số này là mô hình phân tích cho các điều kiện đã nêu, không phải kết quả đo cấp phát thực tế của mọi JVM, không bao gồm byte header mảng, kích thước tham chiếu, các bản dữ liệu trung gian của nguồn hay chi phí khóa.

Chương trình chỉ in công thức này. Không dùng một vòng chạy vài mili giây để khẳng định collection nhanh hơn chính xác một hệ số nào.

### 8.3. Cấp phát và thu gom rác

Mảng mới cần bộ nhớ. Khi các phiên cũ không còn được tham chiếu, chúng có thể được bộ thu gom rác thu hồi. Tốc độ tạo mảng cao làm tăng lượng cấp phát và công việc thu hồi, ngay cả khi lượng dữ liệu cuối cùng không lớn.

Chi phí hệ thống có thể thể hiện ở độ trễ ghi, thông lượng cập nhật, áp lực bộ nhớ hoặc các đợt thu gom. Chỉ đếm số phần tử cuối cùng không mô tả đủ lượng công việc đã diễn ra.

Không tự gán một số byte cụ thể cho mỗi phần tử mà chưa xét cấu hình JVM, kích thước tham chiếu và layout thực tế.

### 8.4. Các bên ghi phải phối hợp

Nếu nhiều luồng cùng cập nhật, ngoài sao chép còn có thời gian đợi lượt ghi được phối hợp. Tăng số luồng ghi không làm các lần sao chép trên cùng collection tự chạy độc lập rồi tự gộp.

Đây là lý do tỉ lệ đọc/ghi chưa đủ để lựa chọn. Cần biết số lượng ghi tuyệt đối và mức tranh chấp. Một triệu lượt đọc mỗi giây không làm hàng chục nghìn lần sao chép một mảng rất lớn mỗi giây trở nên miễn phí.

### 8.5. Không phải mọi lời gọi có ý định ghi đều sao chép cùng lượng

Các trường hợp không làm đổi nội dung có thể không tạo mảng mới. Ví dụ thêm một phần tử đã có bằng `addIfAbsent` có thể kết thúc sau việc kiểm tra; OpenJDK 17 còn có nhánh tối ưu `set` khi cùng tham chiếu.

`clear` có thể công bố mảng rỗng thay vì sao chép mọi phần tử sang một mảng đầy đủ khác. Nhưng các phiên cũ vẫn có thể còn được giữ bởi iterator.

Vì vậy nói “mọi lời gọi ghi đều sao chép đúng n phần tử” là quá mạnh. Cách suy luận đúng là nhận diện thao tác, việc có thay đổi thực sự không, kích thước phiên và triển khai đang xét. Mô hình chi phí phổ biến không thay thế hợp đồng hay phép đo.

## 9. Chi phí giữ các phiên bản cũ

Trong OpenJDK 17, iterator giữ trường tham chiếu đến mảng bản chụp. Khi iterator còn được giữ, mảng đó và các phần tử mà nó tham chiếu có thể vẫn còn reachable đối với bộ thu gom rác.

Hệ quả thực tế:

- Xóa phần tử khỏi collection hiện tại không chắc giải phóng được đối tượng ấy ngay.
- Giữ nhiều iterator từ nhiều đợt ghi có thể giữ nhiều mảng khác nhau.
- Duyệt xong nhưng vẫn lưu đối tượng iterator lâu có thể tiếp tục giữ mảng cũ theo cách triển khai này.
- Một phần tử nặng hoặc giữ tài nguyên gián tiếp có thể còn được tham chiếu dù không còn trong phiên hiện tại.

Không nhầm việc này với một rò bộ nhớ chắc chắn của thư viện. Nó là hệ quả của việc người đọc còn giữ một phiên mà hợp đồng vẫn cho phép đọc. Cần quản lý thời gian sống của các iterator, stream, spliterator hoặc tác vụ giữ bản chụp phù hợp.

Bộ thu gom rác không cung cấp lời hứa “mảng cũ bị xóa ngay khi remove trả về”. Chương trình ví dụ không đo và không tuyên bố thời điểm thu hồi bộ nhớ.

## 10. Đọc nhiều cũng có các loại chi phí khác nhau

| Thao tác thường gặp | Cách suy nghĩ về chi phí |
|---|---|
| `get(index)` trên List | Truy cập theo chỉ số trên mảng của lần đọc; thường hằng số theo số phần tử. |
| Duyệt toàn bộ iterator | Tỷ lệ với số phần tử của bản chụp, không sao chép cả mảng cho từng bước iterator. |
| `contains`, tìm theo giá trị | Có thể phải quét mảng và gọi `equals` nhiều lần. |
| Thêm mới hoặc xóa thành công | Thường có tìm kiếm/kiểm tra và tạo phiên mảng mới. |
| Thêm theo lô | Có thể giảm số lần tạo phiên đích nhưng vẫn cần đọc nguồn và xử lý từng ứng viên. |
| So sánh hai set hoặc loại trùng cả lô | Có thể có nhiều lượt so sánh; không tự mang hiệu năng của bảng băm. |

Đặc biệt với CopyOnWriteArraySet, “đọc rất nhiều” cần hỏi đọc kiểu gì. Duyệt một tập nhỏ nhiều lần rất khác việc tìm thành viên theo khóa trên một tập hàng triệu phần tử.

Hàm `equals` đắt tiền hoặc phụ thuộc vào trạng thái đang bị sửa cũng ảnh hưởng thời gian và tính đúng của việc kiểm tra thành viên.

## 11. Những giới hạn không nên bỏ qua

### 11.1. size rồi get vẫn có thể thuộc hai phiên

~~~java
if (!items.isEmpty()) {
    use(items.get(0));
}
~~~

Đây là đoạn minh họa, giả sử `items` là CopyOnWriteArrayList và `use` đã có. Giữa hai lời gọi, một bên khác có thể `clear`. Việc List an toàn không bảo đảm chuỗi lời gọi này cùng dùng một phiên; `get(0)` có thể không còn chỉ số hợp lệ.

Nếu cần duyệt một nhóm phần tử ổn định, dùng iterator theo bản chụp thay vì ghép nhiều lần `size/get` và giả định chúng thuộc một mảng.

Tương tự, vòng lặp chỉ số đọc lại `size` và `get` qua nhiều lời gọi không tự mang ngữ nghĩa bản chụp của iterator.

### 11.2. subList là view, không phải bản chụp độc lập

`CopyOnWriteArrayList.subList` trả view được hậu thuẫn bởi danh sách gốc. Tài liệu quy định ngữ nghĩa của view không còn được xác định nếu danh sách gốc bị sửa qua đường khác ngoài view đó. [Java 17: CopyOnWriteArrayList.subList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html#subList(int,int))

Không giữ một subList rồi cho rằng nó có cùng bảo đảm sống độc lập với các cập nhật của iterator bản chụp. Nếu cần một phần dữ liệu ổn định, chọn cách lấy dữ liệu có hợp đồng tương ứng thay vì coi mọi view là snapshot.

### 11.3. Không phải mọi phương thức đều có quy tắc iterator

Bảo đảm iterator không bị cập nhật cấu trúc làm hỏng lượt duyệt không có nghĩa mọi callback truyền cho mọi phương thức đều được phép sửa lồng collection tùy ý.

Các phép như `removeIf`, `replaceAll` hoặc `sort` có cơ chế và hợp đồng riêng; trong triển khai, một số công việc chạy trong vùng phối hợp ghi. Giữ các hàm điều kiện/biến đổi ngắn và tránh cập nhật lồng hoặc chờ một bên đang cần ghi cùng collection.

Một iterator bản chụp đang duyệt và một thuật toán đang tạo phiên cập nhật là hai bối cảnh khác nhau.

### 11.4. Không cung cấp giao dịch giữa nhiều collection

Cập nhật danh sách người nhận và một map thông tin bổ sung là hai tác động. Một iterator COW chỉ chốt dãy tham chiếu của chính collection đó, không chốt đồng thời map khác hay trường trạng thái của từng người nhận.

Nếu một sự kiện phải dùng dữ liệu đồng bộ giữa nhiều cấu trúc, cần mô hình phiên chung hoặc giao thức rộng hơn.

## 12. Khi nào nên cân nhắc sử dụng?

Copy-on-write thường đáng cân nhắc khi:

- Collection thường nhỏ hoặc vừa với chi phí sao chép cho phép.
- Lượt duyệt nhiều hơn cập nhật rất rõ và số cập nhật tuyệt đối thấp.
- Cần lượt duyệt ổn định mà không giữ khóa ngoài qua các hàm xử lý người nhận.
- Chấp nhận rằng một lượt đã bắt đầu có thể dùng thành viên cũ.
- Phần tử có trạng thái phù hợp để đọc an toàn hoặc đã được quản lý riêng.

Các ví dụ phù hợp có thể là danh sách bộ xử lý được đăng ký hiếm khi, nhóm luật cấu hình đọc nhiều hoặc tập người nhận sự kiện nhỏ. Vẫn phải đối chiếu kích thước và tải thật.

Nên xem lại lựa chọn khi:

- Dữ liệu lớn và ghi nhiều hoặc ghi theo từng phần tử liên tục.
- Dùng nó như bộ đệm log, hàng đợi công việc hoặc nơi gom từng kết quả của một quá trình song song.
- Cần tra cứu thành viên lớn theo khóa với tần suất cao.
- Cần người đọc lập tức phản ánh mọi lần gỡ/thêm.
- Có các tác vụ giữ bản chụp cũ rất lâu.

Không có một ngưỡng phần trăm đọc/ghi cố định đúng cho mọi chương trình. Kích thước, loại thao tác đọc, số lần ghi mỗi giây và thời gian sống bản chụp đều quan trọng.

## 13. Các lựa chọn gần nhau khác ở đâu?

| Nhu cầu nổi bật | Lựa chọn cần xem xét |
|---|---|
| Danh sách thường bị sửa và chỉ thuộc một luồng | `ArrayList` thông thường. |
| Muốn bảo vệ cả một đoạn duyệt/cập nhật bằng khóa chung | Wrapper đồng bộ hoặc khóa ngoài có giao thức rõ. |
| Tập lớn, thêm/xóa/tra cứu thường xuyên, chấp nhận duyệt nhất quán yếu | Set từ `ConcurrentHashMap.newKeySet`. |
| Tập có thứ tự khóa/phần tử, cập nhật thường xuyên | Cấu trúc skip list đồng thời phù hợp. |
| Cập nhật cả cấu hình theo từng phiên không sửa được | Xây bản cấu hình mới rồi công bố tham chiếu phiên. |
| Nhận và xử lý công việc theo cơ chế hàng đợi | Queue phù hợp với yêu cầu sản xuất/tiêu thụ, chờ và sức chứa. |

Với wrapper `Collections.synchronizedList`, duyệt cần đồng bộ trên wrapper theo hợp đồng. Đó là đánh đổi khác với giữ bản chụp: có thể chặn bên ghi trong lượt duyệt, nhưng không cần tạo một phiên mảng cho mỗi cập nhật theo chiến lược COW. [Java 17: Collections.synchronizedList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedList(java.util.List))

Set từ `ConcurrentHashMap` có cập nhật/tra cứu theo map nền và iterator có chính sách khác. Không đổi collection chỉ vì cùng an toàn giữa nhiều luồng rồi bỏ qua việc iterator là bản chụp hay nhất quán yếu. [Java 17: ConcurrentHashMap.newKeySet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html#newKeySet())

Việc chọn cấu trúc xuất phát từ hợp đồng dữ liệu và ngữ nghĩa quan sát trước, rồi mới đo chi phí.

## 14. Cách kiểm chứng hiệu năng có ý nghĩa

Trước khi đo, mô tả tải:

- Kích thước collection thường gặp và cực đại.
- Số lượt duyệt, tra cứu thành viên và cập nhật mỗi giây.
- Tỉ lệ cập nhật thực sự làm đổi nội dung so với cập nhật không có tác dụng.
- Số luồng ghi và mức tranh chấp.
- Độ lớn lô ghi nếu có thể gom lô.
- Thời gian sống của iterator và đối tượng phần tử.
- Độ trễ ghi, lượng cấp phát và giới hạn bộ nhớ chấp nhận được.

Sau đó đo các mô hình có cùng yêu cầu ngữ nghĩa. So một iterator bản chụp với một lượt duyệt không đồng bộ sai hợp đồng không phải so sánh hữu ích. Cũng không chỉ đo vòng lặp đọc mà bỏ chi phí của bên ghi và giữ phiên.

Chương trình trong bài là minh chứng hành vi và phép tính mô hình; nó không phải benchmark. Mô hình giúp thấy lý do chi phí tăng, còn việc lựa chọn trong một hệ thống cần dữ liệu tải tương ứng.

## 15. Bài tập thực hành

### Bài 1 — Ai sao chép mảng?

Một hệ thống tạo rất nhiều iterator nhưng hiếm khi ghi. Có đúng rằng mỗi iterator của CopyOnWriteArrayList phải tự sao chép toàn bộ mảng không?

**Đáp án:** Không theo mô hình và triển khai đã xét. Iterator giữ tham chiếu đến phiên mảng; việc cập nhật mới thường tạo mảng mới. Các API đọc khác như `toArray` có thể có chi phí riêng.

### Bài 2 — Gỡ người nhận

Một iterator đã được tạo, sau đó bên khác gỡ người nhận L khỏi Set. L có thể vẫn xuất hiện trong lượt duyệt cũ không?

**Đáp án:** Có. Iterator giữ phiên đã lấy. Nếu cần hủy có hiệu lực đối với mọi lời gọi đang hoặc sắp chạy, phải có giao thức bổ sung.

### Bài 3 — Iterator chỉ đọc

Vì sao `list.set(0, x)` có thể hợp lệ nhưng `list.listIterator().set(x)` không được dùng để sửa?

**Đáp án:** Collection hỗ trợ cập nhật, còn list iterator là đường đọc trên bản chụp và không hỗ trợ các phương thức sửa. Ngoài ra, các điều kiện gọi ListIterator thông thường cũng cần được hiểu, nhưng ở đây khả năng sửa đã không được hỗ trợ.

### Bài 4 — Tính duy nhất của List

Danh sách đã có `[A, A]`. `addIfAbsent(A)` và `addAllAbsent([B,A,B])` có dọn bớt một A cũ không?

**Đáp án:** Không. Chúng chỉ tránh các lần thêm mới không cần thiết. Kết quả sau hai lời gọi là `[A, A, B]`.

### Bài 5 — Bản chụp sâu hay nông?

Iterator lấy trước khi một đối tượng phần tử bị sửa trường dữ liệu. Nó có bảo đảm trả nội dung cũ của đối tượng không?

**Đáp án:** Không. Nó giữ tham chiếu phần tử; đối tượng ấy có thể là cùng đối tượng đã bị sửa. Cần thiết kế trạng thái phần tử riêng.

### Bài 6 — Ghi một nghìn phần tử

Tại sao thêm từng phần tử vào một danh sách COW lớn có thể tốn hơn thêm cả lô dù nội dung cuối giống nhau?

**Đáp án:** Các lần thêm riêng tạo nhiều phiên mảng và lặp lại việc sao chép phần đã có. Thêm lô có thể giảm số lần mở rộng đích, nhưng vẫn cần xử lý nguồn và không tự miễn chi phí loại trùng.

### Bài 7 — Xóa hết mà bộ nhớ chưa giảm ngay

Collection đã `clear` nhưng một tác vụ vẫn giữ iterator cũ. Vì sao các phần tử cũ có thể còn được giữ?

**Đáp án:** Iterator cần mảng bản chụp để giữ hợp đồng duyệt. Mảng đó còn tham chiếu tới phần tử. Thời điểm giải phóng còn phụ thuộc việc hết tham chiếu và bộ thu gom rác.

### Bài 8 — Tỉ lệ đọc rất cao

Một collection có một triệu phần tử, cập nhật nhiều nghìn lần mỗi giây nhưng số đọc còn cao hơn nữa. Chỉ từ “đọc nhiều hơn ghi” có đủ chọn copy-on-write không?

**Đáp án:** Không. Phải xét lượng sao chép và cấp phát tuyệt đối, thời gian giữ phiên, tranh chấp ghi và ngữ nghĩa người đọc. Tỉ lệ cao không làm một mảng lớn rẻ đi khi ghi liên tục.

Copy-on-write phù hợp khi việc giữ một lượt duyệt ổn định có giá trị lớn và có thể chấp nhận trả chi phí ở các lần cập nhật hiếm. Hãy đánh giá cả kích thước, cách đọc, nhịp ghi và vòng đời bản chụp để lựa chọn đúng cho dữ liệu của chương trình.
