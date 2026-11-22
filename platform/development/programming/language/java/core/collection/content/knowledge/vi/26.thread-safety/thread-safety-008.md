# Tính nhìn thấy dữ liệu và giới hạn của việc công bố collection chỉ đọc

## 1. Chỉ đọc trả lời câu hỏi về quyền sửa, chưa trả lời câu hỏi về nhìn thấy

Giả sử một luồng thực thi tạo danh sách, điền dữ liệu rồi đưa tham chiếu cho luồng khác. Phía nhận chỉ cần đọc danh sách đó. Cụm từ “collection chỉ đọc” nghe có vẻ đủ an toàn, nhưng thực tế có nhiều trách nhiệm khác nhau.

| Trách nhiệm | Câu hỏi cần trả lời |
| --- | --- |
| Quyền sửa qua API | Bên nhận có gọi được `add`, `remove`, `set` hoặc `put` không? |
| Quan hệ với nguồn | Có một cấu trúc độc lập hay chỉ là khung nhìn của nguồn còn sửa được? |
| Công bố dữ liệu | Luồng nhận lấy được tham chiếu và trạng thái khởi tạo bằng cơ chế nào? |
| Thay đổi về sau | Còn ai sửa cấu trúc nền hoặc đối tượng phần tử không? |
| Nhất quán theo phiên bản | Những lần đọc liên quan có cùng thuộc một phiên bản không? |

`Collections.unmodifiableList(source)` chặn những thao tác sửa qua khung nhìn. Nó không tự biến mọi lần gán tham chiếu đến khung nhìn thành một thao tác công bố giữa các luồng.

`List.copyOf(source)` tạo kết quả không chạy theo những thay đổi cấu trúc về sau của nguồn. Nó cũng không tự thiết kế cách thay tham chiếu hiện tại khi nhiều phiên bản cần được chia sẻ.

**Tính nhìn thấy dữ liệu (visibility)** nói về những giá trị mà một luồng được bảo đảm quan sát từ những lần ghi của luồng khác theo mô hình bộ nhớ Java. Nó khác với:

- Quyền sửa một collection.
- Tính nguyên tử của một phép tăng hoặc một chuỗi nhiều bước.
- Việc nhiều lần đọc cùng thuộc một trạng thái nghiệp vụ.

Ví dụ, hai lần lấy tham chiếu nguyên tử đều có thể đúng nhưng nhìn hai phiên bản khác nhau. Một danh sách không cho sửa cũng có thể chứa một đối tượng phần tử đang thay đổi.

Bài này dùng các chương trình Java 17 độc lập để kiểm chứng từng ranh giới. Các kết quả có phối hợp rõ ràng; đoạn mã thiếu phối hợp chỉ được dùng để phân tích giới hạn bảo đảm, không được gán một stdout tưởng tượng.

## 2. Công bố cần dựa vào bảo đảm của mô hình bộ nhớ

Công bố một collection là làm cho tham chiếu và trạng thái cần đọc của nó trở nên sử dụng được bởi một luồng khác.

Để giải thích điều đó, Java định nghĩa quan hệ **xảy ra trước có bảo đảm (happens-before)**. Nếu một lần ghi nằm trước một lần đọc theo quan hệ phù hợp, chương trình có cơ sở về thứ tự và tính nhìn thấy, thay vì dựa vào suy đoán về bộ nhớ đệm hoặc tốc độ CPU.

Một mô hình công bố điển hình là:

```text
Luồng công bố                         Luồng đọc

Tạo cấu trúc
Ghi các phần tử
Hoàn tất trạng thái cần công bố
       ↓
Mốc công bố có phối hợp ─────────────> Mốc nhận có phối hợp
                                              ↓
                                      Đọc trạng thái đã công bố
```

Các quy tắc thường được dùng gồm ghi và đọc một trường `volatile`, nhả và lấy cùng monitor, `Thread.start`, hoàn tất một luồng rồi `join`, hoặc những API đồng thời có hợp đồng bộ nhớ tương ứng. [Java Language Specification về happens-before](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4.5)

Không cần mô tả mọi lần nhìn thấy dữ liệu bằng một câu “đã đẩy xuống RAM”. Bảo đảm nằm ở mô hình bộ nhớ và hợp đồng API; JVM có thể thực thi bằng những cách khác nhau miễn giữ đúng hành vi được phép.

### Tham chiếu không bị xé không đồng nghĩa có đủ bảo đảm công bố

Việc đọc hoặc ghi một tham chiếu đối tượng là nguyên tử theo nghĩa không tạo một nửa tham chiếu từ lần ghi này ghép với nửa tham chiếu từ lần ghi khác. Nhưng riêng tính chất đó không tạo quan hệ công bố cần thiết cho một giao thức chia sẻ dữ liệu.

Đoạn dưới chỉ minh họa một thiết kế thiếu giao thức; không phải chương trình có kết quả được bảo đảm:

```java
// Trường dùng chung thông thường, không volatile.
static List<String> shared;

// Một luồng thực hiện:
shared = Collections.unmodifiableList(new ArrayList<>(List.of("ready")));

// Luồng khác tự đọc shared mà không có mốc phối hợp.
```

Chỉ thấy tên `unmodifiableList` chưa đủ để giải thích luồng kia khi nào quan sát được tham chiếu mới. Nếu có bảo đảm khởi tạo đặc biệt từ trường `final` hoặc đối tượng bất biến được xây dựng đúng, phải phân tích đúng phạm vi của nó; phần 6 sẽ làm rõ điều này.

Điều không được làm là viết một vòng kiểm tra trên trường thông thường, chạy thấy kết thúc trên một máy rồi suy ra giao thức đó luôn hợp lệ.

### Đúng chiều và đúng thời điểm mới có ích

Một ghi `volatile` chỉ giúp công bố những hành động nằm trước nó theo quan hệ tương ứng. Nó không tự đưa mọi lần sửa phát sinh về sau vào cùng một lần công bố.

Tương tự, nhả khóa A không tự phối hợp với người đọc lấy khóa B. Có từ khóa `synchronized` ở cả hai nơi chưa đủ nếu hai bên không dùng cùng chính sách.

## 3. Thí nghiệm công bố danh sách qua volatile

Lưu vào `VolatileReadOnlyPublicationDemo.java`.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class VolatileReadOnlyPublicationDemo {
    private static volatile List<Integer> published;

    public static void main(String[] args) throws InterruptedException {
        int[] observed = new int[2];
        Thread reader = new Thread(() -> {
            List<Integer> local;
            while ((local = published) == null) {
                Thread.onSpinWait();
            }
            observed[0] = local.size();
            observed[1] = local.stream().mapToInt(Integer::intValue).sum();
        });
        Thread publisher = new Thread(() -> {
            List<Integer> building = new ArrayList<>();
            building.add(10);
            building.add(20);
            building.add(30);
            published = Collections.unmodifiableList(building);
        });

        reader.start();
        publisher.start();
        publisher.join();
        reader.join();
        System.out.println("seenSize=" + observed[0]);
        System.out.println("seenSum=" + observed[1]);
        try {
            published.add(40);
        } catch (UnsupportedOperationException e) {
            System.out.println("publishedAdd=UnsupportedOperationException");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 VolatileReadOnlyPublicationDemo.java
java VolatileReadOnlyPublicationDemo
```

Stdout:

```text
seenSize=3
seenSum=60
publishedAdd=UnsupportedOperationException
```

Luồng công bố tạo `building`, thêm đủ 10, 20, 30 rồi mới gán khung nhìn vào trường `published` có `volatile`.

Luồng đọc chờ đến khi đọc được tham chiếu khác `null`, giữ nó trong biến cục bộ `local`, rồi đọc kích thước và tính tổng. Những ghi khởi tạo dữ liệu xảy ra trước ghi `volatile`; việc đọc trường `volatile` tạo mốc phối hợp cho người đọc.

Bảo đảm về nhìn thấy dữ liệu đến từ việc công bố đúng thời điểm qua trường đó. Bảo đảm chặn `add` đến từ lớp bao `unmodifiableList`. Đó là hai phần hợp đồng khác nhau.

Trong chương trình, danh sách nền không được sửa sau công bố và không có đường sửa được đưa cho người đọc. Các phần tử `Integer` cũng bất biến. Vì thế người đọc có thể xử lý dữ liệu sau khi lấy tham chiếu mà không có một bên tiếp tục thay cấu trúc nền.

### volatile trên tham chiếu không làm từng phần tử thành volatile

Khai báo `volatile List<T>` áp dụng cho trường chứa tham chiếu. Nó không tự gắn chính sách `volatile` cho các ô của danh sách, bộ đếm kích thước hay mọi trường bên trong từng `T`.

Nếu một bên vẫn tiếp tục gọi `building.add` hoặc sửa đối tượng phần tử sau câu gán `published`, cần một chính sách khác cho những thay đổi đó. Một lần công bố đúng không biến mọi cập nhật tương lai thành an toàn.

### onSpinWait không phải thành phần tạo bảo đảm nhìn thấy

`Thread.onSpinWait()` chỉ báo cho runtime rằng đoạn mã đang chờ bằng vòng lặp; nó có thể giúp cách thực thi vòng chờ. Chương trình vẫn đúng về cơ chế công bố nếu bỏ lời gọi đó, vì biến được kiểm tra là `volatile`. [Javadoc Thread.onSpinWait](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html#onSpinWait())

Không thêm `onSpinWait` vào vòng đọc một trường thông thường rồi coi như đã sửa xong giao thức. Trong mã ứng dụng, có thể dùng latch, future hoặc hàng đợi khi chúng diễn đạt việc chờ và chuyển dữ liệu rõ hơn một vòng chờ chủ động.

### join bảo vệ phần đánh giá kết quả cuối

Mảng `observed` chỉ được luồng đọc ghi, và luồng chính chỉ đọc nó sau khi `reader.join()` hoàn tất. Các lời gọi `join` làm thời điểm in kết quả có ý nghĩa.

Điều đó không thay thế quan hệ giữa luồng công bố và luồng đọc trong lúc pipeline dữ liệu đang được sử dụng: ở ví dụ này, quan hệ công bố chính vẫn là trường `published` có `volatile`.

## 4. Những thay đổi sau công bố cần một quan hệ phối hợp mới

Giả sử đã gán một khung nhìn chỉ đọc vào trường `volatile`, rồi sau đó tiếp tục sửa danh sách nền. Người đọc không được dựa vào lần công bố cũ để suy ra mọi sửa đổi mới đều đã được phối hợp.

Có hai vấn đề riêng:

1. Khung nhìn vẫn dùng chung dữ liệu nền.
2. Những ghi về sau cần có quy tắc nhìn thấy và tính nhất quán riêng.

### Thí nghiệm cho thay đổi về sau một mốc phối hợp rõ ràng

Lưu vào `ChangesAfterPublicationDemo.java`.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.CountDownLatch;

public class ChangesAfterPublicationDemo {
    private static volatile List<String> published;

    public static void main(String[] args) throws InterruptedException {
        List<String> backing = new ArrayList<>(List.of("before"));
        published = Collections.unmodifiableList(backing);
        List<String> copied = List.copyOf(backing);
        CountDownLatch referenceCaptured = new CountDownLatch(1);
        CountDownLatch changeFinished = new CountDownLatch(1);
        String[] observed = new String[4];

        Thread reader = new Thread(() -> {
            List<String> view = published;
            referenceCaptured.countDown();
            try {
                changeFinished.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(e);
            }
            observed[0] = Integer.toString(view.size());
            observed[1] = view.get(0);
            observed[2] = Integer.toString(copied.size());
            observed[3] = copied.get(0);
        });
        reader.start();

        referenceCaptured.await();
        backing.set(0, "after");
        backing.add("later");
        changeFinished.countDown();
        reader.join();

        System.out.println("viewSize=" + observed[0]);
        System.out.println("viewFirst=" + observed[1]);
        System.out.println("copySize=" + observed[2]);
        System.out.println("copyFirst=" + observed[3]);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 ChangesAfterPublicationDemo.java
java ChangesAfterPublicationDemo
```

Stdout:

```text
viewSize=2
viewFirst=after
copySize=1
copyFirst=before
```

Luồng đọc lấy tham chiếu `view` rồi báo mốc `referenceCaptured`. Luồng chính chờ mốc đó, sửa danh sách nền, sau đó mới phát tín hiệu `changeFinished`. Luồng đọc chỉ tiếp tục đọc cấu trúc sau khi `await` thành công.

Vì vậy, kết quả `viewSize=2` và `viewFirst=after` có nguyên nhân rõ ràng:

- Khung nhìn không phải bản sao nên vẫn đọc nguồn nền.
- Latch cung cấp quan hệ phối hợp cho những ghi xảy ra sau lần gán `published`.

Các hành động trước `countDown` có quan hệ happens-before với các hành động sau một lần `await` tương ứng thành công, theo hợp đồng của latch. [Javadoc CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html)

Chương trình không chứng minh rằng một khung nhìn chỉ đọc tự bảo đảm nhìn thấy cập nhật tương lai. Ngược lại, nó cố ý đưa vào một cơ chế phối hợp riêng để phép đọc có hợp đồng đúng.

`copied` được tạo bằng `List.copyOf` khi nguồn còn có `before`. Nó giữ cấu trúc `[before]` dù nguồn đã có `[after, later]`. Ở ví dụ này phần tử là `String` bất biến, nên không có thay đổi trạng thái phần tử dùng chung.

### Latch trong ví dụ không chỉ là dụng cụ trì hoãn

Khi thiết kế một thí nghiệm đa luồng, một latch có thể vừa điều phối thứ tự vừa tạo quan hệ bộ nhớ. Không thêm latch rồi dùng kết quả để kết luận rằng phiên bản không có latch cũng có cùng bảo đảm.

Tương tự, nếu dùng `join` để chờ bên ghi xong trước khi đọc, chính `join` đã cung cấp một quan hệ hoàn tất. Một kết quả đúng sau `join` không chứng minh một phép đọc cạnh tranh, không có phối hợp, cũng luôn đúng.

Trong ví dụ này, dữ liệu ban đầu còn được tạo trước `reader.start()`; điều đó cũng có ý nghĩa về công bố ban đầu. Phần cần kiểm chứng là những ghi được thực hiện sau khi người đọc đã lấy khung nhìn, và chúng được phối hợp bằng `changeFinished`.

### volatile không phải khóa cho nguồn nền

Đọc một trường `volatile` rồi duyệt một `ArrayList` đang bị bên khác sửa vẫn có thể vi phạm hợp đồng duyệt của nguồn. Tham chiếu được công bố đúng và nguồn được bảo vệ trong quá trình sử dụng là hai điều kiện riêng.

Nếu muốn tiếp tục sửa cùng cấu trúc, có thể dùng chính sách khóa hoặc cấu trúc concurrent thích hợp. Nếu muốn một phiên bản ổn định để đọc, tạo bản sao đúng cách và không sửa phiên bản đã công bố.

## 5. Nhìn thấy đúng từng lần vẫn có thể trộn hai phiên bản

Một trường `volatile` hoặc một `AtomicReference` giúp phối hợp việc truy cập tham chiếu. Nó không tự gộp nhiều lần lấy tham chiếu thành một lần đọc giao dịch.

Giả sử phiên bản 1 có nhãn `old`, phiên bản 2 có nhãn `new`. Nếu người đọc lấy số phiên bản từ lần đọc thứ nhất và nhãn từ lần đọc tham chiếu thứ hai, có thể ghép “phiên bản 1, nhãn new”.

Đây không nhất thiết là lỗi nhìn thấy bộ nhớ. Mỗi lần đọc có thể quan sát đúng một phiên bản đã được công bố, nhưng thuật toán đọc đã chọn hai mốc khác nhau.

Lưu vào `CapturedVersionReadDemo.java`.

```java
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicReference;

public class CapturedVersionReadDemo {
    record Settings(int version, List<String> labels) {
        Settings {
            labels = List.copyOf(labels);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        AtomicReference<Settings> current =
                new AtomicReference<>(new Settings(1, List.of("old")));
        CountDownLatch firstRead = new CountDownLatch(1);
        CountDownLatch replacementReady = new CountDownLatch(1);
        String[] observed = new String[4];

        Thread reader = new Thread(() -> {
            Settings captured = current.get();
            observed[0] = Integer.toString(captured.version());
            firstRead.countDown();
            try {
                replacementReady.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(e);
            }
            observed[1] = current.get().labels().get(0);
            observed[2] = Integer.toString(captured.version());
            observed[3] = captured.labels().get(0);
        });
        reader.start();

        firstRead.await();
        current.set(new Settings(2, List.of("new")));
        replacementReady.countDown();
        reader.join();

        System.out.println("separateReadVersion=" + observed[0]);
        System.out.println("separateReadLabel=" + observed[1]);
        System.out.println("capturedVersion=" + observed[2]);
        System.out.println("capturedLabel=" + observed[3]);
        System.out.println("latestVersion=" + current.get().version());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 CapturedVersionReadDemo.java
java CapturedVersionReadDemo
```

Stdout:

```text
separateReadVersion=1
separateReadLabel=new
capturedVersion=1
capturedLabel=old
latestVersion=2
```

Latch buộc bên đọc lấy `captured` trước khi luồng chính thay tham chiếu. Sau khi thay xong, người đọc được cho đi tiếp.

Hai dòng đầu ghép giá trị từ hai mốc:

```text
separateReadVersion=1
separateReadLabel=new
```

Hai dòng sau đọc từ cùng `captured`:

```text
capturedVersion=1
capturedLabel=old
```

Phiên bản hiện tại đã là 2, nhưng biến cục bộ vẫn giữ tham chiếu phiên bản 1. `Settings` có trường record cố định và constructor sao chép danh sách bằng `List.copyOf`; các nhãn là `String`. Không có thao tác sửa tại chỗ phiên bản cũ.

`AtomicReference` cung cấp cách truy cập và cập nhật một biến tham chiếu theo các thao tác atomic. Trong ví dụ, nó là nơi công bố phiên bản hiện tại; latch còn được dùng để tạo lịch quan sát xác định cho thí nghiệm. [Javadoc java.util.concurrent.atomic](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/package-summary.html)

### Quy tắc lấy một phiên bản cho một tác vụ

Nếu yêu cầu cần nhiều lần đọc nhất quán theo phiên bản:

1. Lấy tham chiếu phiên bản hiện tại một lần.
2. Giữ trong một biến cục bộ.
3. Đọc những dữ liệu liên quan từ đúng đối tượng phiên bản đó.
4. Không tự trộn thêm dữ liệu từ một lần lấy phiên bản mới nếu hợp đồng không cho phép.

Điều này yêu cầu bản thân phiên bản có mức ổn định phù hợp. Nếu nó chứa phần tử đang thay đổi được, chỉ giữ cùng một tham chiếu chưa đủ để có ảnh chụp sâu.

Nhiều bên ghi cũng là một yêu cầu khác. `get` rồi `set` riêng để tính phiên bản mới không tự tạo một phép cập nhật ghép nguyên tử. Cần một thao tác cập nhật phù hợp hoặc một chính sách bảo vệ cho toàn bộ bước tính và công bố.

## 6. final có bảo đảm khởi tạo riêng, nhưng không đóng băng mọi dữ liệu

Không nên rút vấn đề công bố thành câu “bất cứ thứ gì không dùng volatile đều sai”. Java còn có bảo đảm về trường `final`, khởi tạo lớp và các cơ chế phối hợp khác.

### Biến cục bộ final và trường final khác vai trò

Một biến cục bộ `final List<T>` không được gán lại sau khi khởi tạo. Tính chất đó không tự tạo một kênh công bố tới luồng khác và không làm danh sách trở thành bất biến sâu.

Trường instance `final` có thêm ngữ nghĩa khởi tạo của mô hình bộ nhớ Java. Khi đối tượng được xây dựng đúng, không để tham chiếu `this` thoát ra cho luồng khác trước khi constructor hoàn tất, các giá trị trường `final` có bảo đảm khởi tạo đặc biệt. Bảo đảm còn liên quan tới trạng thái khởi tạo của những đối tượng được tham chiếu qua các trường đó. Đây là một bảo đảm đặc biệt cho trạng thái khởi tạo khi luồng khác đã quan sát được đối tượng được xây dựng hoàn tất, kể cả trong trường hợp việc truyền tham chiếu không dùng đồng bộ thông thường; nó không tạo cơ chế buộc một vòng chờ quan sát mọi lần thay tham chiếu. [Java Language Specification về final fields](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.5)

Đoạn minh họa thiết kế lớp, không phải chương trình độc lập:

```java
final class Catalog {
    private final List<String> names;

    Catalog(List<String> source) {
        this.names = List.copyOf(source);
    }

    List<String> names() {
        return names;
    }
}
```

Ở đây cần giả định bước đọc `source` khi sao chép là hợp lệ. Đối tượng không để lộ chính nó trong constructor, danh sách không cho sửa cấu trúc và phần tử là `String` bất biến.

Không được vì có bảo đảm `final` mà kết luận một trường tham chiếu thông thường dùng để thay `Catalog` hiện tại sẽ tự có giao thức cập nhật và thông báo. Bảo đảm khởi tạo không buộc một vòng chờ trên trường thông thường quan sát được mọi lần thay tham chiếu.

Nó cũng không bảo vệ các sửa đổi xảy ra về sau trên một collection nền còn thay đổi được hoặc trên những trường không được bảo vệ của phần tử.

### static final qua khởi tạo lớp là một cách chia sẻ hợp lệ

Ví dụ khai báo trường trong một lớp:

```java
private static final List<String> DEFAULT_NAMES = List.of("A", "B");
```

Khởi tạo lớp có cơ chế phối hợp của JVM. Khi dùng đúng cách, kiểu dữ liệu tĩnh không thay đổi này không cần một trường `volatile` riêng chỉ để người dùng lớp đọc danh sách mặc định đã khởi tạo. [Java Language Specification về khởi tạo lớp](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.2)

Tuy nhiên, nếu thay phần tử bằng một đối tượng có setter, `static final` vẫn không tự biến mọi lời gọi setter thành an toàn đa luồng. Nó cố định tham chiếu trường và tham gia hợp đồng khởi tạo, không áp một khóa lên toàn bộ đồ thị đối tượng.

### Tạo trước Thread.start cũng có ý nghĩa

Những hành động trước khi gọi `start` có quan hệ happens-before với hành động trong luồng được bắt đầu. Vì vậy, một snapshot được chuẩn bị xong, đưa vào tác vụ rồi bắt đầu luồng đọc có thể có một đường công bố hợp lệ mà không dùng thêm trường `volatile`.

Điều kiện còn lại vẫn là kiểm soát thay đổi sau đó. Nếu một bên tiếp tục sửa đối tượng được dùng chung, bảo đảm của thời điểm bắt đầu luồng không tự bao phủ những sửa đổi tương lai.

## 7. Collection chỉ đọc vẫn có thể chứa phần tử thay đổi được

Một collection không cho thêm hoặc xóa phần tử chưa phải một đồ thị dữ liệu bất biến sâu. Những tham chiếu đang có bên trong vẫn có thể dẫn tới trạng thái thay đổi được.

Lưu vào `ReadOnlyListMutableCounterDemo.java`.

```java
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

public class ReadOnlyListMutableCounterDemo {
    public static void main(String[] args) throws InterruptedException {
        List<AtomicInteger> counters = List.of(new AtomicInteger());
        Runnable increment = () -> {
            for (int i = 0; i < 1000; i++) {
                counters.get(0).incrementAndGet();
            }
        };
        Thread first = new Thread(increment);
        Thread second = new Thread(increment);
        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("listSize=" + counters.size());
        System.out.println("counterValue=" + counters.get(0).get());
        try {
            counters.add(new AtomicInteger());
        } catch (UnsupportedOperationException e) {
            System.out.println("listAdd=UnsupportedOperationException");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 ReadOnlyListMutableCounterDemo.java
java ReadOnlyListMutableCounterDemo
```

Stdout:

```text
listSize=1
counterValue=2000
listAdd=UnsupportedOperationException
```

Danh sách có đúng một phần tử và không cho gọi `add`. Nhưng phần tử đó là một `AtomicInteger`, được thiết kế để cập nhật.

Hai luồng mỗi bên tăng 1000 lần, nên giá trị cuối là 2000. Tính đúng của phép tăng và các quy tắc truy cập giá trị đến từ `AtomicInteger`, không đến từ việc danh sách bên ngoài không cho sửa. [Javadoc AtomicInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html)

Dữ liệu được chuẩn bị trước khi bắt đầu hai luồng, và luồng chính đợi cả hai hoàn tất bằng `join` trước khi in kết quả. Không có phép đọc mảng hoặc phần tử đang thiếu mốc phối hợp trong phần đánh giá cuối.

Nếu thay `AtomicInteger` bằng một đối tượng có trường `int` thông thường rồi tùy ý thực hiện `value++` từ hai luồng, danh sách chỉ đọc không tự bảo vệ phép đọc, cộng và ghi đó. Tình huống còn có vấn đề tính nguyên tử, không chỉ nhìn thấy dữ liệu.

### Khóa hoặc giá trị trong Map cũng có giới hạn tương tự

Một Map không cho thay ánh xạ có thể vẫn chứa giá trị có setter. Một Set không cho thêm phần tử có thể vẫn chứa đối tượng có trạng thái thay đổi được.

Nếu sửa trạng thái ảnh hưởng tới `equals`, `hashCode` hoặc thứ tự so sánh của khóa hay phần tử tập, còn có thể vi phạm giả định của cấu trúc dữ liệu. Vì vậy, thiết kế phần tử ổn định có giá trị cả về tính đúng của collection lẫn việc chia sẻ giữa các luồng.

Khi hợp đồng API nói “chỉ đọc”, cần nêu rõ nó cấm sửa cấu trúc hay cung cấp một giá trị bất biến sâu. Hai lời hứa không tương đương.

## 8. Bàn giao qua hàng đợi có thể cung cấp đường công bố rõ ràng

Không phải mọi giao thức cần một trường `volatile` và vòng chờ tự viết. Một `BlockingQueue` có hợp đồng về bộ nhớ khi một luồng đặt phần tử vào và luồng khác lấy phần tử đó.

Những hành động trước khi đặt đối tượng vào hàng đợi có quan hệ happens-before với các hành động sau khi luồng khác truy cập hoặc lấy đúng phần tử đó. [Javadoc BlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html)

Lưu vào `ReadOnlyQueueHandoffDemo.java`.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

public class ReadOnlyQueueHandoffDemo {
    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<List<String>> channel = new ArrayBlockingQueue<>(1);
        String[] received = new String[1];
        int[] sizes = new int[2];

        Thread consumer = new Thread(() -> {
            try {
                List<String> message = channel.take();
                received[0] = message.toString();
                sizes[0] = message.size();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(e);
            }
        });
        Thread producer = new Thread(() -> {
            try {
                List<String> building =
                        new ArrayList<>(List.of("alpha", "beta"));
                List<String> message = List.copyOf(building);
                channel.put(message);
                building.add("later");
                sizes[1] = building.size();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(e);
            }
        });

        consumer.start();
        producer.start();
        producer.join();
        consumer.join();
        System.out.println("received=" + received[0]);
        System.out.println("receivedSize=" + sizes[0]);
        System.out.println("builderSizeAfterSend=" + sizes[1]);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 ReadOnlyQueueHandoffDemo.java
java ReadOnlyQueueHandoffDemo
```

Stdout:

```text
received=[alpha, beta]
receivedSize=2
builderSizeAfterSend=3
```

Bên tạo dữ liệu có một `building` chỉ do chính nó sở hữu:

1. Tạo đủ `alpha` và `beta`.
2. Tạo `message = List.copyOf(building)`.
3. Đặt `message` vào hàng đợi.
4. Tiếp tục sửa `building` bằng cách thêm `later`.

Bên nhận lấy `message` qua `take`. Nó đọc đúng danh sách `[alpha, beta]` với kích thước 2. Phần xây dựng riêng của bên gửi đã có kích thước 3 nhưng không làm cấu trúc `message` chạy theo.

Có hai bảo đảm kết hợp:

- Hàng đợi cung cấp quan hệ công bố dữ liệu trước bước gửi.
- Bản sao không cho sửa và các phần tử `String` bất biến giữ dữ liệu thông điệp ổn định sau đó.

Các mảng dùng để ghi nhận kết quả được các luồng con cập nhật, rồi chỉ được luồng chính đọc sau `join`. Chúng là nơi ghi nhận kết quả của ví dụ, không phải một kênh đọc cạnh tranh chưa được bảo vệ.

### Gửi khung nhìn còn thay đổi được là một hợp đồng khác

Nếu thay `List.copyOf(building)` bằng một khung nhìn `Collections.unmodifiableList(building)`, rồi bên gửi tiếp tục sửa `building` sau khi gửi, khung nhìn vẫn dùng cùng cấu trúc nền.

Hợp đồng hàng đợi chỉ công bố những hành động ở trước bước đưa phần tử vào theo quan hệ tương ứng. Nó không tự cấm bên gửi sửa nền về sau và không khóa thay cho bên nhận trong suốt thời gian đọc.

Một lựa chọn khác là chuyển quyền sở hữu cấu trúc cho bên nhận và cam kết bên gửi không đụng vào nó nữa. Lựa chọn đó cần được thiết kế và tuân thủ rõ ràng; chỉ bọc một lớp chỉ đọc chưa tạo ra việc chuyển quyền sở hữu.

## 9. Thiết kế đường đi của dữ liệu thay vì chỉ chọn nhãn chỉ đọc

Có thể đọc một thiết kế chia sẻ collection theo chuỗi sau:

```text
Xây dựng dữ liệu hợp lệ
        ↓
Chọn mức bảo vệ cấu trúc và phần tử
        ↓
Hoàn tất phiên bản cần đưa cho người đọc
        ↓
Công bố bằng một cơ chế có hợp đồng bộ nhớ
        ↓
Người đọc lấy đúng phạm vi phiên bản
        ↓
Mọi thay đổi về sau có chính sách riêng
```

Các câu hỏi cần giải thích được:

| Giai đoạn | Điều phải rõ |
| --- | --- |
| Xây dựng | Có bên nào đọc hoặc sửa cùng nguồn trong lúc tạo bản sao không? |
| Giới hạn quyền sửa | Kết quả là khung nhìn, bản sao cấu trúc hay dữ liệu bất biến sâu? |
| Công bố | Quan hệ nào cho phép luồng nhận đọc trạng thái đã chuẩn bị? |
| Đọc | Một tác vụ lấy một phiên bản hay có thể ghép nhiều phiên bản? |
| Cập nhật về sau | Sửa tại chỗ dưới khóa, dùng phần tử atomic, hay tạo phiên bản mới? |
| Kết thúc tác vụ | Có dùng tín hiệu hoàn tất đúng nghĩa khi cần quan sát kết quả không? |

Nếu chọn khóa, cả bên ghi lẫn bên đọc trạng thái liên quan phải dùng cùng monitor hoặc cùng giao thức khóa. Khóa trên một lớp bao chỉ đọc mới tạo không tự phối hợp với bên đang khóa trên một đối tượng nền khác.

Nếu chọn `volatile` hoặc một tham chiếu atomic, xác định những ghi nào nằm trước bước công bố và còn thao tác sửa nào xảy ra sau đó.

Nếu chọn phiên bản không cho sửa, xác định cả cấu trúc lồng nhau và trạng thái phần tử; một lần sao chép danh sách không tự tạo bản sao sâu cho mọi đối tượng.

### Không dùng thời gian trôi qua để thay cho nhìn thấy dữ liệu

`Thread.sleep` và `Thread.yield` không có ngữ nghĩa đồng bộ hóa để buộc các lần ghi được công bố hay các lần đọc phải nạp lại một trường thông thường. [Java Language Specification về sleep và yield](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.3)

Thêm log có thể làm thay đổi lịch chạy hoặc tương tác khóa trong chương trình. Việc lỗi biến mất khi thêm `println` không tạo thành bằng chứng rằng giao thức dữ liệu đã đúng.

Với đoạn mã có tranh chấp dữ liệu, không hứa một kết quả sai cố định như “luôn đọc 0”, “luôn treo” hoặc “chạy lại là chắc thấy lỗi”. Giới hạn là không có bảo đảm cần thiết; một lần quan sát thuận lợi không mở rộng hợp đồng Java.

### Những kết luận thường bị nhầm

| Kết luận | Điều cần sửa |
| --- | --- |
| Không gọi được add thì dữ liệu đã được công bố an toàn | Quyền sửa qua API khác cơ chế công bố giữa các luồng |
| Tham chiếu được gán nguyên tử thì mọi trạng thái đã nhìn thấy đúng | Tính nguyên tử của tham chiếu khác các quan hệ khởi tạo và công bố |
| volatile List làm mọi phần tử tự volatile | Chỉ trường tham chiếu có chính sách đó |
| Ghi volatile một lần bảo vệ mọi sửa đổi tương lai của nền | Những ghi sau đó cần một quan hệ phối hợp riêng |
| unmodifiableList cắt quan hệ với nguồn | Nó là khung nhìn, không phải bản sao độc lập |
| copyOf làm bất biến sâu mọi phần tử | Nó không tự sao chép sâu đồ thị đối tượng |
| Có final là không cần phân tích constructor hoặc cách chia sẻ | Bảo đảm final có điều kiện xây dựng và phạm vi riêng |
| Mọi dữ liệu chỉ đọc đều bắt buộc có trường volatile | Khởi tạo lớp, ngữ nghĩa khởi tạo final trong phạm vi của nó, start, khóa hoặc API bàn giao cũng có những bảo đảm phù hợp |
| AtomicReference.get nhiều lần tự cho một phiên bản | Mỗi lần lấy có thể quan sát một phiên bản hợp lệ khác |
| Dùng latch trong kiểm thử chỉ làm chậm các bước | Latch còn tạo quan hệ bộ nhớ có thể thay đổi điều được kiểm chứng |
| Đã đọc đúng sau join thì mọi đọc cạnh tranh trước đó cũng đúng | join cung cấp một mốc hoàn tất; không thể bỏ nó khỏi lập luận |
| Queue bảo vệ mọi sửa đổi sau khi gửi đối tượng | Hợp đồng bàn giao không tự bảo vệ cập nhật tương lai của đối tượng dùng chung |
| Vòng chờ có sleep hoặc onSpinWait tự an toàn | Phải có biến hoặc giao thức có ngữ nghĩa phối hợp đúng |
| Chạy nhiều lần không lỗi thì không có tranh chấp dữ liệu | Cần kiểm tra quan hệ bộ nhớ, không chỉ đếm lần chạy thành công |

Một hợp đồng trả collection chỉ đọc nên nói rõ dữ liệu có thể thay đổi từ phía khác không, phần tử có thể thay đổi không và người dùng nhận một ảnh chụp hay khung nhìn. Với dữ liệu dùng giữa các luồng, còn cần mô tả đường công bố hoặc giao thức sử dụng phù hợp.

## 10. Thực hành tìm đúng quan hệ bảo đảm

### Bài 1: chỉ bọc unmodifiable rồi gán vào trường thông thường

Một luồng tạo danh sách, bọc `unmodifiableList` rồi gán vào trường dùng chung không có `volatile`. Luồng kia lặp đọc trường đó mà không có mốc phối hợp. Có thể giải thích vòng chờ luôn quan sát được tham chiếu mới chỉ bằng việc danh sách không cho sửa không?

**Đối chiếu:**

Không. Lớp bao chỉ đọc không phải một giao thức thông báo tham chiếu mới. Cần xác định bảo đảm công bố và tiến trình quan sát phù hợp, chẳng hạn trường `volatile`, một khóa dùng chung hoặc API bàn giao dữ liệu.

Nếu có bảo đảm khởi tạo đặc biệt của đối tượng bất biến được xây dựng đúng, phải phân biệt nó với việc một vòng chờ trên trường thông thường chắc chắn nhìn thấy cập nhật.

### Bài 2: sửa nền sau lần ghi volatile

Danh sách nền được điền xong, công bố qua một trường `volatile`, rồi tiếp tục bị sửa bằng `set`. Người đọc chỉ đọc trường tham chiếu đó một lần. Lần ghi `volatile` trước có tự bảo vệ lần `set` sau không?

**Đối chiếu:**

Không. Nó không tự đưa những ghi về sau vào cùng lần công bố. Cần một chính sách mới cho các cập nhật đó, hoặc không sửa phiên bản đã công bố.

`ChangesAfterPublicationDemo` có kết quả xác định vì dùng thêm latch cho các ghi sau công bố.

### Bài 3: hai lần đọc đều an toàn nhưng khác phiên bản

Phiên bản 1 có nhãn `old`, phiên bản 2 có nhãn `new`. Người đọc lấy số phiên bản rồi lấy nhãn qua hai lần đọc tham chiếu hiện tại riêng biệt. Vì sao có thể ghép “1, new” mà không cần giả định bộ nhớ đọc sai?

**Đối chiếu:**

Một lần đọc có thể lấy phiên bản 1, lần sau lấy phiên bản 2. Đó là hai quan sát hợp lệ ở hai mốc. Nếu cần một trạng thái nhất quán, lấy tham chiếu một lần và đọc các giá trị liên quan từ cùng phiên bản ổn định.

### Bài 4: final tham chiếu tới một List

Một lớp có trường `final List<MutableItem>` được gán trong constructor. Sau khi constructor hoàn tất, bên khác sửa một trường của `MutableItem`. Chỉ từ từ khóa `final` có thể kết luận thao tác đó được bảo vệ không?

**Đối chiếu:**

Không. Trường `final` có bảo đảm khởi tạo riêng khi xây dựng đúng, nhưng không khóa mọi thay đổi về sau của đối tượng được tham chiếu. Trạng thái `MutableItem` cần mức bất biến hoặc phối hợp riêng.

### Bài 5: danh sách mặc định static final

Một lớp khai báo `private static final List<String> DEFAULTS = List.of("A", "B");` và không có phần tử thay đổi được. Có cần thêm `volatile` chỉ vì dữ liệu được đọc từ nhiều luồng không?

**Đối chiếu:**

Không cần thêm như vậy chỉ để đọc dữ liệu mặc định đã được khởi tạo lớp đúng cách. Khởi tạo lớp đã có hợp đồng phối hợp, và cấu trúc cùng các giá trị `String` không thay đổi trong thiết kế này.

Không suy rộng đáp án sang một biến tham chiếu khác thường xuyên bị gán lại hoặc sang những phần tử có trạng thái thay đổi được.

### Bài 6: chỉ đọc bên ngoài, AtomicInteger bên trong

Một `List.of(new AtomicInteger())` chặn thêm phần tử. Hai luồng vẫn tăng được bộ đếm bên trong. Vì sao điều đó không mâu thuẫn?

**Đối chiếu:**

Danh sách không bị thay cấu trúc; trạng thái đối tượng phần tử được cập nhật. `AtomicInteger` cung cấp hợp đồng cho phép tăng và đọc giá trị; tính chất chỉ đọc của danh sách không làm việc đó và cũng không cấm nó.

### Bài 7: hàng đợi và dữ liệu nền còn bị sửa

Bên gửi đặt `Collections.unmodifiableList(building)` vào một `BlockingQueue`, rồi tiếp tục sửa `building`. Bên nhận có được coi thông điệp là một snapshot không đổi chỉ vì đi qua hàng đợi không?

**Đối chiếu:**

Không. Hàng đợi có bảo đảm công bố cho các hành động trước khi gửi, nhưng khung nhìn vẫn có nền dùng chung. Cần bản sao phù hợp, chuyển quyền sở hữu hoặc một chính sách cho những sửa đổi tiếp theo.

### Bài 8: xác định điều mà một kiểm chứng thật sự chứng minh

Một ví dụ chỉ đọc trường thông thường sau khi đã `join` bên ghi, và kết quả luôn đúng. Có được bỏ `join` rồi dùng chính quan sát đó để nói bản không có phối hợp cũng an toàn không?

**Đối chiếu:**

Không. `join` là một phần của lập luận về hoàn tất và nhìn thấy dữ liệu. Thay đổi mốc phối hợp làm thay đổi những bảo đảm đang dùng.

Một lời giải tốt cần chỉ ra từng mốc: dữ liệu được tạo ở đâu, tham chiếu được chuyển bằng cách nào, những ghi nào nằm trước mốc công bố, người đọc giữ phiên bản nào và những thay đổi về sau được bảo vệ ra sao.
