# Collection đồng thời, wrapper có khóa và bản sao bất biến

## 1. Ba mô hình khác nhau cho dữ liệu được chia sẻ

Khi nhiều luồng thực thi cùng cần một tập dữ liệu, câu hỏi đầu tiên không chỉ là “lớp nào an toàn đa luồng?”. Cần xác định dữ liệu có còn thay đổi không, ai được thay đổi và người đọc cần thấy một phiên bản nhất quán tới mức nào.

Có ba cách tổ chức thường gặp:

1. **Collection đồng thời:** cấu trúc và các thao tác được thiết kế cho truy cập đồng thời theo hợp đồng riêng, chẳng hạn `ConcurrentHashMap`.
2. **Lớp bao có khóa:** các thao tác phù hợp trên một collection nền được phối hợp qua cơ chế khóa, chẳng hạn `Collections.synchronizedMap`.
3. **Bản sao không cho sửa cấu trúc:** tạo một tập dữ liệu đầu ra không được thêm, xóa hoặc thay phần tử qua API; khi cần cập nhật, tạo và công bố một phiên bản khác.

Ba mô hình không phải ba cấp “tốt, khá, kém”. Chúng xử lý những yêu cầu khác nhau.

| Câu hỏi | Collection đồng thời | Wrapper có khóa | Bản sao không cho sửa |
| --- | --- | --- | --- |
| Dữ liệu có thể cập nhật tại chỗ không? | Có, theo API của lớp | Có nếu cấu trúc nền hỗ trợ | Không qua API của bản sao |
| Ai tổ chức phối hợp truy cập? | Cấu trúc và thao tác concurrent cụ thể | Lớp bao và các vùng khóa do ứng dụng thiết kế | Cơ chế tạo, công bố và thay phiên bản |
| Mọi chuỗi nhiều lời gọi có tự nguyên tử không? | Không | Không; có thể cần giữ cùng khóa | Việc thay tham chiếu hoặc đọc nhiều phiên bản vẫn cần thiết kế |
| Người đọc luôn có ảnh chụp toàn bộ tại một thời điểm không? | Không thể suy chung | Có thể lấy trạng thái dưới khóa đúng phạm vi | Bản sao ổn định chưa chứng minh quá trình lấy nguồn là ảnh chụp nguyên tử |
| Đối tượng phần tử tự bất biến không? | Không | Không | Không, nếu chỉ sao chép cấu trúc |

Trong bài, “bản sao bất biến” được hiểu trước hết ở mức cấu trúc collection: không cho thêm, xóa hoặc thay phần tử. Muốn bất biến sâu còn phải bảo đảm trạng thái của các đối tượng phần tử và những đối tượng mà chúng tham chiếu tới.

Một danh sách chỉ chứa `String` và một danh sách chứa các đối tượng nghiệp vụ có setter không có cùng mức độ ổn định, dù cả hai đều được tạo bằng `List.copyOf`.

## 2. Không cho sửa, có khóa và có bản sao là ba tính chất riêng

Các cách viết sau biểu đạt ba ý khác nhau:

```java
// Đoạn minh họa; source là List<String> hợp lệ.
List<String> locked = Collections.synchronizedList(source);
List<String> readOnlyView = Collections.unmodifiableList(source);
List<String> snapshot = List.copyOf(source);
```

- `locked` là lớp bao đồng bộ nhưng vẫn dùng dữ liệu nền `source`.
- `readOnlyView` chặn sửa qua chính khung nhìn đó, nhưng vẫn nhìn dữ liệu nền.
- `snapshot` có nội dung cấu trúc không tự cập nhật theo những thay đổi về sau ở nguồn.

Nếu nguồn đang được nhiều bên sửa, bản thân bước tạo bản sao cũng phải đọc nguồn theo một chính sách hợp lệ. Cú pháp `copyOf` không tự sửa mọi vấn đề phối hợp ở đầu vào.

### Thí nghiệm wrapper, khung nhìn và bản sao

Lưu vào `LockedViewAndCopyDemo.java`.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class LockedViewAndCopyDemo {
    public static void main(String[] args) {
        List<String> locked = Collections.synchronizedList(
                new ArrayList<>(List.of("A", "B")));
        List<String> readOnlyView = Collections.unmodifiableList(locked);
        List<String> snapshot;
        synchronized (locked) {
            snapshot = List.copyOf(locked);
        }

        locked.add("C");
        synchronized (locked) {
            System.out.println("locked=" + locked);
            System.out.println("readOnlyView=" + readOnlyView);
        }
        System.out.println("snapshot=" + snapshot);

        try {
            readOnlyView.add("D");
        } catch (UnsupportedOperationException e) {
            System.out.println("viewAdd=UnsupportedOperationException");
        }
        try {
            snapshot.add("D");
        } catch (UnsupportedOperationException e) {
            System.out.println("copyAdd=UnsupportedOperationException");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 LockedViewAndCopyDemo.java
java LockedViewAndCopyDemo
```

Stdout:

```text
locked=[A, B, C]
readOnlyView=[A, B, C]
snapshot=[A, B]
viewAdd=UnsupportedOperationException
copyAdd=UnsupportedOperationException
```

Sau khi tạo ba đối tượng liên quan, chương trình thêm `C` thông qua `locked`:

- `locked` có `[A, B, C]`.
- `readOnlyView` cũng có `[A, B, C]` vì nó đọc dữ liệu nền qua lớp bao.
- `snapshot` vẫn là `[A, B]`.

Cả `readOnlyView.add` và `snapshot.add` đều bị chặn, nhưng nguyên nhân “không cho sửa qua API” không làm hai đối tượng có cùng quan hệ với nguồn.

`Collections.unmodifiableList` tạo khung nhìn, còn `List.copyOf` có cam kết rằng các thay đổi cấu trúc về sau ở nguồn không được phản ánh vào kết quả. [Javadoc Collections.unmodifiableList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)), [Javadoc List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection))

Trong ví dụ, việc tạo bản sao và phần đọc khung nhìn được đặt dưới đúng khóa của `locked`. Không thêm một lớp `unmodifiable` rồi giả định đã có một monitor mới thay thế monitor gốc.

### Không cần phụ thuộc danh tính của bản sao

Một factory có thể tái sử dụng một đối tượng đầu vào phù hợp thay vì luôn cấp một đối tượng mới. Điều cần dựa vào là hợp đồng nội dung và quyền sửa, không phải kết luận rằng hai tham chiếu chắc chắn khác nhau.

Nếu cần công bố hoặc cập nhật dữ liệu giữa các luồng, dùng một cơ chế phối hợp rõ ràng. Không chọn chính đối tượng collection dựa trên giá trị làm khóa chỉ vì nghĩ nó luôn là một đối tượng mới riêng biệt.

## 3. Wrapper có khóa phù hợp với một chính sách sở hữu chung

Với `Collections.synchronizedList`, `synchronizedSet` hoặc `synchronizedMap`, mọi đường truy cập tới cấu trúc nền phải tuân thủ chính sách của lớp bao. Giữ lại tham chiếu thô rồi sửa nó ở nơi khác làm mất sự thống nhất đó.

Các thao tác trực tiếp như `add`, `get` hoặc `put` được phối hợp, nhưng một quyết định gồm nhiều lời gọi cần có phạm vi bảo vệ riêng.

Đoạn minh họa kiểm tra rồi thêm dưới cùng monitor:

```java
// names là một synchronized List<String> được chia sẻ.
synchronized (names) {
    if (!names.contains("new")) {
        names.add("new");
    }
}
```

Nếu bỏ khối ngoài, hai luồng vẫn có thể cùng thấy chưa có phần tử trước khi lần lượt thêm. Từng phương thức được đồng bộ không có nghĩa toàn bộ thuật toán tự là một thao tác nguyên tử.

### Duyệt là một phạm vi cần được bảo vệ

Với iterator, spliterator hoặc stream trên lớp bao, phải tuân thủ quy tắc khóa thủ công cho thời gian duyệt. Với các khung nhìn của synchronized Map, khóa là Map lớp bao gốc, không phải đối tượng `keySet` hay `entrySet`. [Javadoc synchronizedMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedMap(java.util.Map))

Điều đó cho phép ứng dụng lấy một trạng thái có kiểm soát trong lúc mọi bên liên quan cùng dùng đúng chính sách khóa. Đổi lại, những bên cần cùng khóa có thể phải chờ trong thời gian vùng bảo vệ đang chạy.

Một wrapper không tự tạo giao dịch cho nhiều collection khác nhau. Nếu một bất biến liên quan một List và một Map, hai monitor độc lập không đủ để đảm bảo người đọc luôn thấy một trạng thái chung của cả hai.

### Đừng chuyển quy tắc monitor sang mọi collection concurrent

Một khối `synchronized (someMap)` chỉ hữu ích khi những bên cần phối hợp thực sự tuân thủ monitor đó. Các thao tác thông thường của `ConcurrentHashMap` không tự dùng monitor của đối tượng theo hợp đồng của `synchronizedMap`.

Vì thế, đổi loại Map mà giữ nguyên giả định “khóa bên ngoài sẽ chặn mọi thao tác” có thể làm sai thiết kế. Chọn loại cấu trúc và cách bảo vệ một bất biến là một quyết định kết hợp.

## 4. Collection đồng thời cung cấp những thao tác có hợp đồng riêng

`ConcurrentHashMap` cho phép truy cập và cập nhật đồng thời theo hợp đồng của nó. Các phép đọc thường có thể chồng lấp với cập nhật; không nên hình dung toàn bộ Map bị giữ bởi một monitor chung giống lớp bao đồng bộ.

Tuy nhiên, “collection đồng thời” không có nghĩa mọi thao tác đều không chờ, mọi chuỗi lời gọi đều nguyên tử hoặc mọi lần duyệt đều là ảnh chụp toàn bộ.

Đoạn minh họa sau vẫn chưa gộp một phép tăng:

```java
// counts là ConcurrentHashMap<String, Integer>.
int previous = counts.getOrDefault("count", 0);
counts.put("count", previous + 1);
```

Hai bên có thể đọc cùng giá trị cũ rồi ghi cùng giá trị mới. Cấu trúc bên trong Map vẫn hợp lệ nhưng mục tiêu đếm đủ số lần cập nhật có thể không đạt.

Với yêu cầu cập nhật theo một khóa, chọn thao tác nguyên tử phù hợp, chẳng hạn `merge`, `compute` hoặc `putIfAbsent` theo đúng ngữ nghĩa cần có.

### Thí nghiệm cập nhật nguyên tử theo khóa

Lưu vào `ConcurrentMapOperationsDemo.java`.

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;

public class ConcurrentMapOperationsDemo {
    private static void await(CountDownLatch latch) {
        try {
            latch.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(e);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        ConcurrentHashMap<String, Integer> counts = new ConcurrentHashMap<>();
        CountDownLatch start = new CountDownLatch(1);
        Thread[] threads = new Thread[4];
        for (int i = 0; i < threads.length; i++) {
            threads[i] = new Thread(() -> {
                await(start);
                for (int n = 0; n < 500; n++) {
                    counts.merge("requests", 1, Integer::sum);
                }
            });
            threads[i].start();
        }
        start.countDown();
        for (Thread thread : threads) {
            thread.join();
        }

        Integer first = counts.putIfAbsent("limit", 42);
        Integer second = counts.putIfAbsent("limit", 99);
        System.out.println("requests=" + counts.get("requests"));
        System.out.println("firstPrevious=" + first);
        System.out.println("secondPrevious=" + second);
        System.out.println("limit=" + counts.get("limit"));

        try {
            counts.put("invalid", null);
        } catch (NullPointerException e) {
            System.out.println("nullValue=NullPointerException");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 ConcurrentMapOperationsDemo.java
java ConcurrentMapOperationsDemo
```

Stdout:

```text
requests=2000
firstPrevious=null
secondPrevious=42
limit=42
nullValue=NullPointerException
```

Bốn luồng thực thi đều chờ tín hiệu bắt đầu rồi mỗi luồng tăng `requests` 500 lần. `merge("requests", 1, Integer::sum)` diễn đạt việc thêm giá trị ban đầu nếu chưa có, hoặc cộng vào giá trị hiện tại như một thao tác nguyên tử theo hợp đồng phương thức. Sau khi `join` các luồng, tổng là 2000. [Javadoc ConcurrentHashMap.merge](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html#merge(K,V,java.util.function.BiFunction))

Hàm kết hợp `Integer::sum` chỉ tính giá trị mới, không có I/O hay cập nhật một ánh xạ khác. Hàm tính lại trong các thao tác này cần ngắn và tuân thủ giới hạn của phương thức; không coi nó là nơi tùy ý thực hiện một quy trình nghiệp vụ dài.

Hai lần `putIfAbsent` cho khóa `limit` cho thấy:

- Lần đầu chưa có khóa, nên thêm 42 và trả `null` để báo chưa có giá trị trước.
- Lần sau thấy 42 đã có, nên không thay thành 99 và trả 42.
- Giá trị cuối của `limit` vẫn là 42.

`ConcurrentHashMap` không chấp nhận khóa hoặc giá trị `null`. Vì thế `firstPrevious=null` là giá trị báo chưa có ánh xạ trước đó, không phải bằng chứng Map đang lưu một giá trị `null`.

### Nguyên tử theo khóa không phải giao dịch nhiều khóa

Một phép `merge` hoặc `putIfAbsent` đúng không tự tạo giao dịch bao trùm hai khóa, hai Map hoặc một Map cùng một hệ thống bên ngoài.

Ví dụ, nếu cần cập nhật hai số liệu mà tổng của chúng phải giữ nguyên, hai lời gọi cập nhật riêng vẫn có thể để người đọc thấy trạng thái xen giữa. Khi đó phải thiết kế bất biến và cách công bố dữ liệu phù hợp, thay vì chỉ đổi loại Map.

Tương tự, lấy một đối tượng giá trị ra từ Map rồi sửa trường của nó không tự trở thành thao tác nguyên tử của Map. Tính an toàn của cấu trúc chứa và tính an toàn của trạng thái phần tử vẫn là hai tầng riêng.

## 5. Cách duyệt cho thấy sự khác nhau rõ nhất giữa các mô hình

Có ít nhất ba kiểu hành vi cần phân biệt:

| Kiểu duyệt | Cách tổ chức | Người đọc cần hiểu |
| --- | --- | --- |
| Duyệt dưới khóa của wrapper | Giữ đúng monitor suốt lần duyệt | Những bên cập nhật theo cùng khóa phải chờ |
| Duyệt ảnh chụp của CopyOnWriteArrayList | Iterator giữ mảng đã có khi nó được tạo | Không tự nhìn những lần thêm hoặc xóa sau đó |
| Duyệt nhất quán yếu của ConcurrentHashMap | Duyệt theo chính sách concurrent của lớp | Không có cam kết ảnh chụp nguyên tử toàn bộ Map |

Không gom hai loại sau thành một khái niệm “cứ concurrent là duyệt snapshot”. Chính sách của từng lớp có ý nghĩa khác nhau.

### Thí nghiệm wrapper khóa người ghi và iterator ảnh chụp

Lưu vào `TraversalModelsDemo.java`.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.Iterator;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;

public class TraversalModelsDemo {
    public static void main(String[] args) throws InterruptedException {
        List<Integer> locked = Collections.synchronizedList(
                new ArrayList<>(List.of(1, 2, 3)));
        CountDownLatch approachingAdd = new CountDownLatch(1);
        CountDownLatch addFinished = new CountDownLatch(1);
        List<Integer> lockedRead = new ArrayList<>();
        Thread writer;
        boolean finishedInsideLock;

        synchronized (locked) {
            writer = new Thread(() -> {
                approachingAdd.countDown();
                locked.add(4);
                addFinished.countDown();
            });
            writer.start();
            approachingAdd.await();
            Iterator<Integer> iterator = locked.iterator();
            while (iterator.hasNext()) {
                lockedRead.add(iterator.next());
            }
            finishedInsideLock = addFinished.getCount() == 0;
        }
        writer.join();
        System.out.println("lockedRead=" + lockedRead);
        System.out.println("addFinishedInsideLock=" + finishedInsideLock);
        System.out.println("lockedAfterWriter=" + locked);

        CopyOnWriteArrayList<Integer> copyOnWrite =
                new CopyOnWriteArrayList<>(List.of(1, 2, 3));
        Iterator<Integer> oldIterator = copyOnWrite.iterator();
        Thread anotherWriter = new Thread(() -> copyOnWrite.add(4));
        anotherWriter.start();
        anotherWriter.join();
        List<Integer> oldRead = new ArrayList<>();
        oldIterator.forEachRemaining(oldRead::add);
        System.out.println("snapshotIteratorRead=" + oldRead);
        System.out.println("copyOnWriteAfterWriter=" + copyOnWrite);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 TraversalModelsDemo.java
java TraversalModelsDemo
```

Stdout:

```text
lockedRead=[1, 2, 3]
addFinishedInsideLock=false
lockedAfterWriter=[1, 2, 3, 4]
snapshotIteratorRead=[1, 2, 3]
copyOnWriteAfterWriter=[1, 2, 3, 4]
```

Ở phần synchronized List, luồng chính giữ monitor của `locked`. Bên ghi báo tín hiệu trước khi gọi `locked.add(4)`. Khi luồng chính còn giữ khóa, phép thêm đó chưa thể hoàn tất, nên `addFinishedInsideLock=false`.

Tín hiệu ở đây được phát trước khi bên ghi cần khóa. Vì vậy luồng chính có thể chờ mốc tín hiệu trong vùng khóa mà không yêu cầu bên ghi phải vào vùng đang bị khóa mới phát được tín hiệu.

Dữ liệu duyệt dưới khóa là `[1, 2, 3]`. Sau khi nhả khóa và chờ bên ghi kết thúc, nguồn có `[1, 2, 3, 4]`. Thí nghiệm không đoán trạng thái lập lịch hoặc dùng thời gian ngủ để suy ra rằng bên ghi đã chạy xong.

Ở phần `CopyOnWriteArrayList`, iterator được tạo trước khi thêm 4. Bên ghi hoàn tất trước khi iterator cũ được duyệt, nhưng iterator vẫn trả `[1, 2, 3]`. Trạng thái hiện tại của collection đã là `[1, 2, 3, 4]`.

Đó là chính sách ảnh chụp của iterator: đọc mảng đã chọn từ lúc tạo iterator, không cập nhật theo mảng mới của collection. Các lần ghi có chi phí tạo bản sao mảng; chính sách này cần được cân nhắc theo tần suất đọc và ghi. [Javadoc CopyOnWriteArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html)

### ConcurrentHashMap không cung cấp cùng ảnh chụp đó

Iterator và spliterator của `ConcurrentHashMap` có chính sách nhất quán yếu. Chúng hỗ trợ việc duyệt khi có cập nhật, nhưng không cam kết toàn bộ kết quả tương ứng với một trạng thái duy nhất tại một thời điểm. Những phép tổng hợp như `size` trong lúc cập nhật cũng không phải hàng rào để quyết định một bất biến chung. [Javadoc ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)

Không ném `ConcurrentModificationException` chỉ là một phần của hợp đồng đó, không đồng nghĩa:

- Nhìn thấy mọi cập nhật vừa xảy ra.
- Giữ nguyên mọi giá trị lúc iterator được tạo.
- Có cùng kết quả với một lần đọc toàn bộ dưới khóa.
- Có thể thực hiện một giao dịch nhiều khóa dựa trên kết quả duyệt.

Nếu nghiệp vụ chỉ cần duyệt dữ liệu đang thay đổi để giám sát hoặc xử lý theo chính sách cho phép, kiểu nhất quán này có thể phù hợp. Nếu cần một phiên bản thống nhất, phải thiết kế cách lấy hoặc công bố phiên bản đó.

## 6. Bản sao ổn định chưa chắc được tạo từ một thời điểm nguyên tử

`List.copyOf`, `Set.copyOf` và `Map.copyOf` tạo kết quả không cho sửa cấu trúc theo hợp đồng tương ứng. Khi nguồn được sửa về sau, cấu trúc kết quả không tự chạy theo nguồn.

Nhưng có hai giai đoạn độc lập:

```text
Đọc trạng thái từ nguồn  →  Tạo cấu trúc kết quả không cho sửa
        ↑                                ↑
  Có nhất quán không?             Có ổn định về sau không?
```

Đầu ra ổn định chỉ trả lời vế sau. Nếu đầu vào đang được đọc theo chính sách nhất quán yếu, không có một phép khóa toàn cục tự xuất hiện chỉ vì kết quả cuối được tạo bằng `copyOf`.

Ví dụ minh họa một lần đọc có thể bị xen cập nhật:

```text
Trạng thái đầu: A=1, B=1

Lần đọc bản sao: đọc A=1
Bên ghi:        đổi A thành 2
Bên ghi:        đổi B thành 2
Lần đọc bản sao: đọc B=2

Giá trị đã đọc: A=1, B=2
```

Trong lịch này, các trạng thái nguồn đi qua là `(1,1)`, `(2,1)`, `(2,2)`. Bộ giá trị đã đọc `(1,2)` không phải một trong những trạng thái toàn bộ đó.

Đây là minh họa vấn đề đọc nhiều giá trị khi chúng thay đổi, không phải stdout cố định của một chương trình được giả định luôn có đúng lịch xen kẽ này. Một cấu trúc duyệt nhất quán yếu không tạo cam kết ngăn mọi trường hợp như vậy.

### Khi cần ảnh chụp đúng phạm vi, phải bảo vệ bước lấy dữ liệu

Với wrapper có khóa, có thể giữ đúng monitor trong khi sao chép, miễn mọi bên ghi dữ liệu liên quan đều tuân thủ cùng chính sách.

Với một hệ thống công bố các phiên bản không cho sửa, người đọc có thể lấy một tham chiếu phiên bản rồi đọc toàn bộ dữ liệu từ đúng phiên bản đó.

Với một collection concurrent đang được cập nhật độc lập theo nhiều khóa, nếu yêu cầu đòi trạng thái toàn cục, cần một thiết kế riêng. `Map.copyOf(concurrentMap)` không phải thao tác giao dịch chụp toàn bộ Map tại một thời điểm.

Ngay cả khi tạo bản sao từ `ArrayList` thông thường, vẫn phải bảo đảm giai đoạn đọc nguồn không bị cập nhật trái với hợp đồng. Kết quả không cho sửa không sửa được một bước lấy dữ liệu không hợp lệ.

## 7. Công bố các phiên bản không cho sửa bằng một tham chiếu được phối hợp

Khi dữ liệu chủ yếu được đọc, một mô hình khác là không cập nhật tại chỗ phiên bản đã đưa cho người đọc. Bên ghi tạo phiên bản tiếp theo, rồi thay tham chiếu dùng để công bố phiên bản hiện tại.

Người đọc lấy tham chiếu một lần và tiếp tục dùng chính phiên bản đó:

```text
Tham chiếu hiện tại ──> phiên bản mới
Người đọc cũ       ──> phiên bản cũ vẫn giữ nguyên
```

Việc không cho sửa cấu trúc giúp đọc một phiên bản ổn định. Cơ chế công bố tham chiếu giúp các luồng phối hợp về việc nhìn thấy và thay phiên bản. Hai trách nhiệm này không thay thế cho nhau.

Có thể tổ chức công bố bằng một khóa, trường `volatile` trong thiết kế thích hợp hoặc `AtomicReference`. Nếu nhiều bên ghi cần tính phiên bản mới từ phiên bản hiện tại, chỉ gọi `get` rồi `set` riêng không tự gộp toàn bộ cập nhật.

### Thí nghiệm thay phiên bản nguyên tử

Lưu vào `PublishedImmutableVersionsDemo.java`.

```java
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;

public class PublishedImmutableVersionsDemo {
    public static void main(String[] args) throws InterruptedException {
        AtomicReference<Map<String, Integer>> current =
                new AtomicReference<>(Map.of("count", 0));
        Map<String, Integer> oldVersion = current.get();

        Runnable update = () -> {
            for (int i = 0; i < 200; i++) {
                current.updateAndGet(previous -> {
                    Map<String, Integer> next = new HashMap<>(previous);
                    next.put("count", previous.get("count") + 1);
                    return Map.copyOf(next);
                });
            }
        };
        Thread first = new Thread(update);
        Thread second = new Thread(update);
        first.start();
        second.start();
        first.join();
        second.join();

        Map<String, Integer> latest = current.get();
        System.out.println("oldVersionCount=" + oldVersion.get("count"));
        System.out.println("latestVersionCount=" + latest.get("count"));
        try {
            latest.put("count", -1);
        } catch (UnsupportedOperationException e) {
            System.out.println("latestPut=UnsupportedOperationException");
        }
        System.out.println("oldVersionStill=" + oldVersion.get("count"));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 PublishedImmutableVersionsDemo.java
java PublishedImmutableVersionsDemo
```

Stdout:

```text
oldVersionCount=0
latestVersionCount=400
latestPut=UnsupportedOperationException
oldVersionStill=0
```

Mỗi luồng tạo 200 lần cập nhật. `updateAndGet` gộp việc lấy phiên bản hiện tại, tính ứng viên và cập nhật tham chiếu theo hợp đồng nguyên tử của phương thức, nên sau hai luồng giá trị là 400. [Javadoc AtomicReference.updateAndGet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html#updateAndGet(java.util.function.UnaryOperator))

Mỗi ứng viên được tạo bằng một `HashMap` cục bộ, sửa bản cục bộ đó rồi chuyển thành `Map.copyOf`. Không có thao tác sửa tại chỗ một Map đã được công bố.

`oldVersion` vẫn giữ `count=0`, trong khi `latest` có `count=400`. Gọi `put` lên `latest` bị chặn. Khóa và giá trị trong ví dụ đều là `String` hoặc `Integer` bất biến, nên không có một giá trị đối tượng thay đổi được ẩn bên trong phiên bản.

### Hàm tính phiên bản có thể được gọi lại

Khi các cập nhật cạnh tranh, `updateAndGet` có thể áp dụng lại hàm tính. Vì vậy, hàm đó cần không có tác động phụ bên ngoài.

Ví dụ tạo một Map cục bộ là phù hợp: nếu ứng viên không được dùng, không có dữ liệu ngoài nào đã bị cập nhật. Không đặt hành động gửi yêu cầu bên ngoài, ghi nhận một sự kiện bắt buộc chỉ một lần hoặc tăng một biến chung trong hàm rồi giả định hàm luôn được gọi đúng một lần cho mỗi cập nhật thành công.

Điều này khác với một lời gọi phương thức nghiệp vụ thông thường mà người đọc mã có thể tưởng chỉ chạy một lượt.

### Lấy cùng một phiên bản cho các lần đọc liên quan

Nếu một thao tác cần đọc hai trường thuộc cùng trạng thái cấu hình, nên lấy tham chiếu hiện tại một lần rồi đọc cả hai từ phiên bản đã lấy.

Gọi `current.get()` riêng trước mỗi trường có thể nhận các phiên bản khác nhau nếu bên ghi vừa công bố một phiên bản mới. Mỗi lần lấy tham chiếu đúng riêng lẻ không có nghĩa nhiều lần lấy liên tiếp tự thuộc một giao dịch đọc chung.

Ví dụ có chủ đích giữ `oldVersion` và `latest` thành hai tham chiếu riêng để làm rõ ranh giới phiên bản. Không dùng `Thread.sleep` để suy luận bên ghi đã xong; các lần `join` bảo vệ thời điểm đánh giá kết quả cuối.

### Chi phí không biến mất, nó chuyển sang lúc cập nhật

Tạo bản sao toàn bộ mỗi lần cập nhật tốn công sao chép và tạo đối tượng mới. Mô hình này có thể phù hợp khi người đọc cần phiên bản ổn định và số lần cập nhật tương đối ít, nhưng không phải cách mặc định tối ưu cho một Map lớn được sửa liên tục.

Ví dụ có một ánh xạ để kiểm chứng tính đúng đắn, không phải phép đo hiệu năng. Khi dữ liệu lớn, cần cân nhắc kích thước phiên bản, tần suất cập nhật, khả năng giữ phiên bản cũ và cách thu hồi những phiên bản không còn được dùng.

## 8. Bản sao không cho sửa vẫn có giới hạn ở phần tử

Một bản sao `List.copyOf` không tự tạo đối tượng mới cho từng phần tử. `Map.copyOf` cũng không tự sao chép sâu mọi khóa và giá trị.

Lưu vào `ShallowImmutableCopyDemo.java`.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class ShallowImmutableCopyDemo {
    static final class MutableTag {
        private String text;

        MutableTag(String text) {
            this.text = text;
        }
    }

    public static void main(String[] args) {
        MutableTag tag = new MutableTag("before");
        List<MutableTag> source = new ArrayList<>(List.of(tag));
        List<MutableTag> copiedList = List.copyOf(source);
        Map<String, MutableTag> copiedMap = Map.copyOf(Map.of("tag", tag));

        source.add(new MutableTag("later"));
        tag.text = "after";
        System.out.println("sourceSize=" + source.size());
        System.out.println("copiedListSize=" + copiedList.size());
        System.out.println("copiedListText=" + copiedList.get(0).text);
        System.out.println("copiedMapText=" + copiedMap.get("tag").text);

        try {
            copiedList.add(new MutableTag("extra"));
        } catch (UnsupportedOperationException e) {
            System.out.println("copiedListAdd=UnsupportedOperationException");
        }
        try {
            List.copyOf(Arrays.asList("A", null));
        } catch (NullPointerException e) {
            System.out.println("nullListElement=NullPointerException");
        }

        Map<String, String> withNull = new HashMap<>();
        withNull.put("key", null);
        try {
            Map.copyOf(withNull);
        } catch (NullPointerException e) {
            System.out.println("nullMapValue=NullPointerException");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 ShallowImmutableCopyDemo.java
java ShallowImmutableCopyDemo
```

Stdout:

```text
sourceSize=2
copiedListSize=1
copiedListText=after
copiedMapText=after
copiedListAdd=UnsupportedOperationException
nullListElement=NullPointerException
nullMapValue=NullPointerException
```

Sau khi thêm một phần tử vào nguồn:

- Nguồn có hai phần tử.
- `copiedList` vẫn có một phần tử.

Đây là sự độc lập về cấu trúc.

Nhưng sửa `tag.text` thành `after` làm cả `copiedListText` lẫn `copiedMapText` đều là `after`. Chúng vẫn tham chiếu cùng một `MutableTag`. Thí nghiệm chạy những thay đổi này trên một luồng để quan sát quan hệ tham chiếu; nó không biến một thao tác sửa trường dùng chung thành an toàn đa luồng.

Do đó, muốn nhiều người đọc một phiên bản dữ liệu bất biến sâu, phải xem cả mô hình phần tử:

- Dùng các giá trị bất biến phù hợp.
- Tạo dữ liệu đầu ra riêng nếu cần cắt quan hệ với đối tượng nguồn.
- Sao chép hoặc bảo vệ những cấu trúc lồng nhau có thể thay đổi.
- Không để một setter hoặc một tham chiếu có thể sửa xuyên qua ranh giới dữ liệu đã công bố.

Không có một lớp bao collection nào tự suy ra cách sao chép sâu đúng cho mọi đối tượng nghiệp vụ.

### Chính sách null và thứ tự cũng cần được kiểm tra

Các factory `List.copyOf`, `Set.copyOf` và `Map.copyOf` từ chối phần tử hoặc khóa, giá trị `null` theo hợp đồng tương ứng. Chương trình kiểm chứng trường hợp phần tử null của List và giá trị null của Map. [Javadoc List](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html), [Javadoc Set](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html), [Javadoc Map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html)

Đổi mô hình dữ liệu có thể làm đổi những chính sách khác:

| Lựa chọn | Null | Thứ tự cần chú ý |
| --- | --- | --- |
| Wrapper trên một collection nền | Theo khả năng của nền | Theo hợp đồng của nền |
| `ConcurrentHashMap` | Không nhận khóa hoặc giá trị null | Không cam kết thứ tự duyệt theo chèn |
| `CopyOnWriteArrayList` | Cho phép phần tử null | Có thứ tự danh sách; iterator đọc ảnh chụp |
| `List.copyOf` | Từ chối phần tử null | Giữ thứ tự duyệt của nguồn |
| `Set.copyOf` | Từ chối phần tử null | Không cam kết giữ thứ tự duyệt của nguồn |
| `Map.copyOf` | Từ chối khóa hoặc giá trị null | Không cam kết giữ thứ tự duyệt của nguồn |

Ví dụ, đổi một Map nền cho phép null thành `ConcurrentHashMap` hoặc một bản `Map.copyOf` không chỉ đổi cách phối hợp truy cập. Cần kiểm tra dữ liệu hợp lệ và hợp đồng API.

Tương tự, khi cần một ảnh chụp Map duyệt theo thứ tự chèn, không mặc định `Map.copyOf` giữ thứ tự đó. Có thể tạo một cấu trúc nền riêng có thứ tự rồi bao không cho sửa, đồng thời không để lộ đường sửa nền và vẫn bảo vệ bước lấy dữ liệu.

## 9. Chọn mô hình theo bất biến và cách cập nhật

| Tình huống | Mô hình có thể phù hợp | Điều phải xác định |
| --- | --- | --- |
| Nhiều cập nhật độc lập theo khóa | Collection concurrent và thao tác nguyên tử phù hợp | Phạm vi nguyên tử theo khóa; trạng thái giá trị |
| Một nhóm thao tác cần cùng một trạng thái dùng chung | Wrapper có khóa hoặc lớp sở hữu với chính sách khóa rõ | Monitor và toàn bộ đường đọc, ghi cần phối hợp |
| Dữ liệu cấu hình đọc nhiều, thay theo phiên bản | Phiên bản không cho sửa được công bố đúng cách | Bất biến phần tử, cách thay tham chiếu và cách đọc một phiên bản |
| Danh sách cần duyệt thường xuyên, ít cập nhật | Collection có chính sách ảnh chụp như copy-on-write nếu chi phí phù hợp | Chi phí ghi và việc người đọc không thấy cập nhật mới |
| Tác vụ tính toán dài chấp nhận dữ liệu tại một mốc | Chụp dữ liệu hợp lệ rồi xử lý bản chụp | Tính nhất quán khi chụp và mức độ sao chép |
| Chuyển dữ liệu đầu ra cho bên chỉ được đọc | Bản sao hoặc mô hình dữ liệu đầu ra không cho sửa | Có dùng chung đối tượng phần tử hay không |

Những lựa chọn này cần được kiểm tra trên yêu cầu thật. Không phải mọi Map đều có một bất biến toàn cục, và không phải mọi lần đọc đều cần thấy dữ liệu mới nhất. Yêu cầu càng rõ, phạm vi phối hợp càng dễ thiết kế.

### Các kết luận dễ gây lỗi

| Kết luận sai | Điều cần phân biệt |
| --- | --- |
| Có từ concurrent là mọi thuật toán nhiều bước đều đúng | Thao tác nguyên tử cụ thể khác chuỗi lời gọi bất kỳ |
| Có wrapper là chỉ cần không sửa trực tiếp dữ liệu thô | Còn phải bảo vệ thao tác ghép và quá trình duyệt |
| Bọc unmodifiable là đã có snapshot | Khung nhìn vẫn có thể chạy theo cấu trúc nền |
| copyOf tự khóa toàn bộ nguồn khi đọc | Bước lấy dữ liệu cần chính sách nhất quán riêng |
| Kết quả copyOf ổn định nên chắc là một trạng thái nguồn tại một thời điểm | Ổn định về sau khác tính nguyên tử khi lấy nguồn |
| CopyOnWriteArrayList và ConcurrentHashMap có cùng chính sách duyệt | Một loại iterator ảnh chụp khác với duyệt nhất quán yếu |
| Thread-safe của Map bảo vệ mọi setter của giá trị | Giá trị có trạng thái dùng chung cần chính sách riêng |
| Danh sách không cho sửa nghĩa là mọi phần tử bất biến sâu | Bản sao cấu trúc có thể giữ cùng tham chiếu phần tử |
| Gọi AtomicReference.get rồi set riêng là một phép cập nhật ghép nguyên tử | Cần thao tác nguyên tử thích hợp hoặc một chính sách bên ngoài |
| Hàm updateAndGet luôn được gọi đúng một lần | Có thể được áp dụng lại khi cạnh tranh |
| Đọc current.get nhiều lần tự cho cùng phiên bản | Nếu cần nhất quán theo phiên bản, lấy tham chiếu một lần |
| synchronized trên ConcurrentHashMap chặn mọi thao tác của nó | Không cùng hợp đồng monitor với synchronizedMap |
| Đổi mô hình chỉ ảnh hưởng tốc độ | Null, thứ tự, chính sách duyệt và quyền sửa cũng có thể khác |

Một thiết kế có thể kết hợp nhiều mô hình ở các ranh giới khác nhau. Chẳng hạn, bộ phận ghi dùng Map đồng thời cho những cập nhật độc lập; một quy trình khác tạo dữ liệu tổng hợp theo chính sách đã xác định rồi công bố kết quả không cho sửa. Tuy nhiên, phần kết hợp phải có hợp đồng rõ, không tự xuất hiện chỉ vì từng thành phần riêng được gọi là an toàn đa luồng.

## 10. Thực hành xác định đúng bảo đảm cần có

### Bài 1: khung nhìn hay bản sao?

Từ một synchronized List có `[A, B]`, tạo một `Collections.unmodifiableList` và một `List.copyOf` theo đúng chính sách khóa. Sau đó thêm `C` vào nguồn qua lớp bao. Hai kết quả đọc có giống nhau không?

**Đối chiếu:**

Không. Khung nhìn đọc `[A, B, C]`, bản sao giữ `[A, B]`. Cả hai chặn thao tác thêm qua API của kết quả, nhưng có quan hệ khác nhau với nguồn.

### Bài 2: cộng bằng hai lời gọi trên ConcurrentHashMap

Một đoạn mã dùng `get` rồi `put` để tăng bộ đếm. Có thể bỏ qua việc phối hợp thao tác ghép chỉ vì Map là concurrent không?

**Đối chiếu:**

Không. Hai bên có thể tính từ cùng giá trị cũ. Với yêu cầu đếm theo một khóa, có thể dùng `merge` như chương trình, hoặc chọn một thao tác khác có hợp đồng phù hợp.

Điều này chưa giải quyết mọi bất biến liên quan nhiều khóa hoặc hệ thống bên ngoài.

### Bài 3: cần thấy phiên bản cũ hay bản cập nhật?

Iterator của `CopyOnWriteArrayList` được tạo khi có `[1, 2, 3]`. Một bên đã thêm 4 và hoàn tất trước khi iterator cũ được duyệt. Iterator cũ có bắt buộc thấy 4 không?

**Đối chiếu:**

Không. Nó đọc ảnh chụp lúc được tạo, nên trong tình huống đã kiểm chứng vẫn thấy `[1, 2, 3]`. Muốn đọc trạng thái mới, lấy một lần duyệt mới theo hợp đồng lớp.

### Bài 4: tạo Map.copyOf từ Map đang cập nhật

Một Map concurrent chứa nhiều giá trị liên hệ với nhau. Sau `Map.copyOf`, kết quả không cho sửa. Có thể kết luận ngay rằng mọi giá trị trong đó cùng thuộc một thời điểm toàn cục không?

**Đối chiếu:**

Không. Cần xem cách đọc nguồn. Một đầu ra ổn định có thể được tạo từ những giá trị quan sát ở các thời điểm khác nhau nếu nguồn không cung cấp ảnh chụp nguyên tử.

Nếu cần một phiên bản thống nhất, bảo vệ quá trình lấy dữ liệu hoặc dùng cơ chế công bố phiên bản đáp ứng yêu cầu.

### Bài 5: một Map không cho sửa nhưng có MutableTag

Map được tạo bằng `Map.copyOf`, nhưng giá trị là một `MutableTag` đã được dùng ở nơi khác. Khi nơi khác sửa trường của tag, giá trị đọc qua Map có bắt buộc giữ trạng thái cũ không?

**Đối chiếu:**

Không. Map chặn thay ánh xạ qua API, không sao chép sâu đối tượng tag. Cần dữ liệu phần tử bất biến, bản sao phù hợp hoặc một chính sách phối hợp riêng.

### Bài 6: công bố phiên bản bằng AtomicReference

Một yêu cầu cần đọc hai thông số thuộc cùng phiên bản. Cách nào rõ hơn: gọi `current.get()` trước mỗi thông số, hay lấy một biến phiên bản rồi đọc cả hai từ biến đó?

**Đối chiếu:**

Lấy một tham chiếu phiên bản rồi đọc cả hai. Nếu có bên ghi thay tham chiếu giữa hai lần `get`, hai lần đọc riêng có thể thuộc hai phiên bản khác nhau.

AtomicReference giúp phối hợp tham chiếu, nhưng ứng dụng vẫn phải xác định phạm vi của một lần đọc nhất quán.

### Bài 7: tác động phụ trong updateAndGet

Hàm tính phiên bản mới vừa tạo Map vừa ghi nhận một sự kiện bên ngoài. Có được giả định sự kiện đó xảy ra đúng một lần cho mỗi lần cập nhật thành công không?

**Đối chiếu:**

Không. Hàm tính có thể được gọi lại khi cạnh tranh. Giữ hàm tính không có tác động phụ bên ngoài và thiết kế việc ghi nhận sự kiện theo một cơ chế phù hợp riêng.

### Bài 8: nêu đủ điều kiện cho một lựa chọn

Chọn một trong ba yêu cầu:

1. Bộ đếm nhiều khóa được cập nhật độc lập.
2. Một cặp dữ liệu phải được đọc và thay đổi như cùng một trạng thái.
3. Bộ cấu hình được thay theo phiên bản, người đọc cần giữ một phiên bản trong suốt tác vụ.

Với mỗi lựa chọn, hãy nêu cấu trúc hoặc mô hình phối hợp, phạm vi nguyên tử, chính sách duyệt và mức bảo vệ phần tử.

Một lời giải đạt yêu cầu không chỉ nêu tên lớp. Nó cần giải thích người đọc được thấy trạng thái nào, bên ghi được sửa ở đâu và vì sao những cập nhật liên quan không phá bất biến đã chọn.
