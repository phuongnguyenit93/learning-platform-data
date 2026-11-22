# Trường `final` và bảo đảm khởi tạo đúng trong Java Memory Model

## 1. Vì sao `final` liên quan đến lập trình đa luồng?

Khi nhiều thread truy cập cùng một đối tượng, câu hỏi đầu tiên là: **thread đọc có thấy trạng thái đối tượng đã được khởi tạo đầy đủ không?** Trình biên dịch, bộ xử lý và bộ nhớ đệm có thể thực hiện tối ưu hóa trong giới hạn Java Memory Model (JMM). Nếu một thread tạo đối tượng rồi chuyển tham chiếu cho thread khác mà không có cơ chế công bố đúng, thread đọc có thể thiếu bảo đảm nhìn thấy một số lần ghi trong constructor.

`final` có hai ý nghĩa cần phân biệt:

1. **Quy tắc của ngôn ngữ:** trường instance `final` chỉ được gán trong quá trình khởi tạo hợp lệ; sau đó mã Java thông thường không thể gán lại trường đó. Với kiểu nguyên thủy, giá trị trường không bị gán lại; với kiểu tham chiếu, chính *tham chiếu* không bị gán lại.
2. **Bảo đảm của Java Memory Model:** khi đối tượng được **khởi tạo đúng cách (properly constructed)**, các giá trị trường `final` đã được thiết lập trong constructor có những bảo đảm đặc biệt về khả năng nhìn thấy đối với thread khác, kể cả trong một số trường hợp không có quan hệ `happens-before` thông thường cho việc công bố tham chiếu.

Điều kiện quan trọng nhất là **không để tham chiếu `this` thoát ra cho thread khác sử dụng trước khi constructor hoàn thành**. Nếu vi phạm điều này, không thể viện dẫn bảo đảm của `final` để khẳng định thread khác luôn thấy trạng thái đã khởi tạo.

Các khái niệm gốc:

- **Initialization (khởi tạo):** constructor và các bước khởi tạo thiết lập trạng thái ban đầu của đối tượng.
- **Publication (công bố):** làm cho tham chiếu tới đối tượng trở nên truy cập được từ thread khác.
- **Visibility (khả năng nhìn thấy):** thread đọc có bảo đảm quan sát các lần ghi tạo trạng thái hay không.
- **Safe publication (công bố an toàn):** sử dụng quan hệ đồng bộ thích hợp khi chuyển đối tượng cho thread khác, ví dụ trường `volatile`, `synchronized`, `AtomicReference`, `BlockingQueue`, hoặc khởi tạo lớp (class initialization) theo hợp đồng của Java.
- **Immutability (bất biến):** trạng thái quan sát được của đối tượng không đổi sau khi khởi tạo; chỉ thêm `final` vào một tham chiếu chưa đủ để làm mọi đối tượng được tham chiếu trở nên bất biến.

Bài này tập trung vào **Java concurrency nói chung** và chính các bảo đảm của JMM; không phụ thuộc framework.

## 2. Một ví dụ dễ hình dung

Xét đối tượng cấu hình:

```java
final class RetrySettings {
    private final String serviceName;
    private final int maxRetries;

    RetrySettings(String serviceName, int maxRetries) {
        if (serviceName == null || serviceName.isBlank()) {
            throw new IllegalArgumentException("serviceName");
        }
        if (maxRetries < 0) {
            throw new IllegalArgumentException("maxRetries");
        }
        this.serviceName = serviceName;
        this.maxRetries = maxRetries;
    }

    String serviceName() {
        return serviceName;
    }

    int maxRetries() {
        return maxRetries;
    }
}
```

Đây là **định nghĩa lớp minh họa** (chưa có `main`). Hai trường được gán khi constructor chạy và không thể gán lại qua mã Java bình thường. `String` cũng bất biến, nên kiểu dữ liệu này có thể được dùng như một value object bất biến đơn giản.

Nếu đối tượng được tạo bằng `new RetrySettings("catalog", 3)`, không làm lộ `this` trong quá trình khởi tạo và thread khác nhận được tham chiếu đó, bảo đảm đặc biệt của `final` giúp thread đọc thấy `serviceName = "catalog"` và `maxRetries = 3` theo ngữ nghĩa trường final. Đây là khác biệt đáng kể với một đối tượng có các trường thường (non-final) được công bố qua data race.

**Không suy rộng:** bảo đảm giá trị trường `final` không tự bảo đảm thread khác sẽ *nhận được tham chiếu* kịp thời, không bảo vệ các trường non-final, và không tạo an toàn cho các thao tác cập nhật trạng thái tiếp theo trên đối tượng khác.

## 3. Những quy tắc ngôn ngữ của trường `final`

### 3.1. Gán một lần trong quá trình khởi tạo

Một **blank final instance field** là trường `final` chưa được gán ở chỗ khai báo. Java yêu cầu trường đó được gán đúng cách trên mọi đường hoàn thành constructor bình thường, trong constructor hoặc bộ khởi tạo instance hợp lệ. Trường `final` đã có giá trị từ initializer thì không được gán lại trong constructor.

```java
class Point {
    final int x;
    final int y;

    Point(int x, int y) {
        this.x = x;
        this.y = y;
    }
}
```

Đây là đoạn định nghĩa lớp minh họa. Sau khi tạo `Point p = new Point(2, 5)`, mã `p.x = 7` bị từ chối khi biên dịch. Constructor được quyền chọn giá trị từ tham số, và các đường khởi tạo hợp lệ phải hoàn tất việc gán trường.

Với trường `static final`, việc gán thường nằm ở khai báo hoặc bộ khởi tạo `static`. JMM cung cấp **cơ chế class initialization** riêng để điều phối việc khởi tạo lớp; không nên nhầm cơ chế đó với bảo đảm đặc biệt của **instance final fields** trong constructor.

### 3.2. `final` không đồng nghĩa với “object sâu bên trong bất biến”

```java
class Bag {
    final int[] values = {1, 2};
}
```

Mã `bag.values = new int[] {3, 4}` là không hợp lệ sau khởi tạo. Nhưng `bag.values[0] = 99` vẫn hợp lệ: **mảng** là đối tượng có thể sửa, còn `final` chỉ khóa việc gán lại **tham chiếu tới mảng**.

Tương tự:

```java
private final java.util.List<String> items = new java.util.ArrayList<>();
```

Danh sách vẫn cho phép `items.add(...)`. Truy cập/sửa danh sách từ nhiều thread có thể gây race condition hoặc lỗi cấu trúc. Trường `final` không biến `ArrayList` thành collection an toàn đa luồng.

Muốn thiết kế bất biến hơn, có thể sao chép phòng vệ (`List.copyOf`) và không để lộ các đối tượng phần tử có thể bị sửa. `List.copyOf` tạo danh sách không hỗ trợ thao tác sửa cấu trúc qua tham chiếu nhận được, nhưng **không tự sao chép sâu** mọi phần tử; phần tử mutable vẫn cần xét riêng.

## 4. Bảo đảm đặc biệt của JMM: constructor kết thúc và freeze action

JMM định nghĩa **freeze action** gắn với trường `final` tại thời điểm constructor ghi trường đó kết thúc theo quy tắc của JLS. Hiểu ở mức ứng dụng: khi một đối tượng hoàn tất quá trình khởi tạo một cách hợp lệ, JMM thiết lập quy tắc đặc biệt giúp các thread khác đọc những trường `final` với giá trị đã được thiết lập trong quá trình khởi tạo.

Đây là lý do Java thường khuyến khích tạo **immutable value object** bằng trường `final`. Dù một tham chiếu được công bố bằng cách thiếu đồng bộ, trường `final` của đối tượng **properly constructed** vẫn có bảo đảm riêng về giá trị khởi tạo, với điều kiện thread khác thực sự lấy được tham chiếu đó và thao tác đọc đáp ứng ngữ nghĩa của JMM.

Tuy nhiên, có giới hạn quan trọng:

- Đây **không phải** là bảo đảm rằng mọi trường non-final được ghi trong constructor cũng nhìn thấy đúng qua một lần công bố không an toàn.
- Nó **không tạo ra** một quan hệ `happens-before` tổng quát như khi dùng `synchronized` hay `volatile` để công bố.
- Nó **không làm đối tượng mutable trở thành thread-safe** sau khi constructor xong.
- Nó **không thay thế** giao thức đồng bộ cho nhiều phép đọc/ghi tạo thành một thao tác logic.
- Nó phụ thuộc vào quá trình **khởi tạo đúng**: không để thread khác quan sát `this` trước khi các trường được khởi tạo và constructor cần thiết kết thúc.

Các trường `final` tham chiếu đến object/array còn có một số quy tắc visibility bổ sung đối với trạng thái của những object được tham chiếu khi khởi tạo. Không nên diễn giải những quy tắc đó thành “mọi thay đổi về sau trên object con tự an toàn”; các thay đổi về sau vẫn cần đồng bộ phù hợp.

Đối với code thực tế, **safe publication của cả đối tượng vẫn là chính sách dễ kiểm chứng hơn**, vì nó bảo vệ cả dữ liệu không phải final và tạo ra quan hệ chia sẻ rõ ràng.

## 5. Properly constructed: không làm lộ `this` trong constructor

**This escape** là tình huống tham chiếu tới đối tượng đang được tạo thoát ra cho code có thể sử dụng nó trước khi constructor hoàn thành. Những cách xảy ra thường gặp:

- Gán `this` vào một biến `static` hoặc một holder dùng chung ngay trong constructor.
- Đăng ký `this` vào listener/callback mà thread khác có thể gọi lập tức.
- Bắt đầu thread ngay trong constructor và truyền lambda có thể truy cập các trường của `this`.
- Gửi `this` cho một dịch vụ hoặc bộ điều phối khác thực thi đồng thời.
- Gọi phương thức có thể bị ghi đè từ constructor của lớp cha; phương thức ghi đè trong lớp con có thể nhìn thấy trạng thái của lớp con **trước khi lớp con khởi tạo xong**, hoặc làm lộ tham chiếu cho thread khác.

Trong các trường hợp đó, thread khác có thể đọc trường khi nó vẫn mang **giá trị mặc định** (`0` đối với `int`, `false` đối với `boolean`, `null` đối với tham chiếu), vì constructor chưa chạy đến phép gán. Không có cơ chế JMM nào cho phép một thread đọc trước phép gán đã xảy ra mà vẫn đòi hỏi giá trị tương lai phải xuất hiện.

### 5.1. Minh chứng có thể chạy: công bố `this` quá sớm

Ví dụ dùng `volatile` và hai `CountDownLatch` để **chủ động bắt gặp trạng thái chưa khởi tạo**. Cách tổ chức này có kết quả xác định và thể hiện rằng ngay cả việc công bố tham chiếu qua `volatile` cũng không thể “sửa” việc công bố **trước khi constructor hoàn thành**.

Tạo tệp `ThisEscapeDemo.java`:

```java
import java.util.concurrent.CountDownLatch;

public class ThisEscapeDemo {
    private static volatile Leaky published;
    private static final CountDownLatch referenceVisible =
            new CountDownLatch(1);
    private static final CountDownLatch finishConstructor =
            new CountDownLatch(1);

    private static final class Leaky {
        final int answer;

        Leaky() {
            published = this; // Công bố khi answer chưa được gán.
            referenceVisible.countDown();

            try {
                finishConstructor.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(e);
            }

            answer = 42;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Thread builder = new Thread(Leaky::new, "builder");
        builder.start();

        referenceVisible.await();
        Leaky leaked = published;
        System.out.println("Khi constructor chưa xong: " + leaked.answer);

        finishConstructor.countDown();
        builder.join();
        System.out.println("Sau khi constructor xong: " + leaked.answer);
    }
}
```

Biên dịch và chạy trên Java 17+:

```bash
javac ThisEscapeDemo.java
java ThisEscapeDemo
```

Kết quả khi không có yêu cầu interrupt bên ngoài:

```text
Khi constructor chưa xong: 0
Sau khi constructor xong: 42
```

**Tại sao không phụ thuộc vào may rủi lập lịch?**

1. Worker gán `published = this` qua trường `volatile` **trước khi** gán `answer = 42`.
2. Worker báo `referenceVisible` rồi đứng chờ `finishConstructor`, nên main biết tham chiếu đã xuất hiện nhưng phép gán `answer` chưa thể chạy.
3. Main đọc `leaked.answer`: vì chưa có phép gán, trường `int` đang mang giá trị mặc định `0`.
4. Main mở latch, cho phép constructor thực hiện `answer = 42` và kết thúc.
5. `builder.join()` hoàn thành tạo quan hệ *happens-before* từ các hành động của builder đến đoạn đọc cuối ở main; giá trị `42` được nhìn thấy sau khi hoàn thành.

Ví dụ chỉ dùng để **giải thích nguy cơ và điều kiện khởi tạo**. Code ứng dụng không nên lưu một đối tượng chưa hoàn tất constructor như thế. Có `volatile` trong ví dụ không khiến trạng thái chưa được gán tự trở nên hợp lệ.

### 5.2. Sửa bằng cách khởi tạo xong rồi mới công bố

Tách hẳn hai hành động:

```java
LeakyReplacement object = new LeakyReplacement(42);
// Constructor đã trả về thành công.
registry.publish(object);
```

Đây là **mã minh họa** với `LeakyReplacement` và `registry` là API do ứng dụng định nghĩa. Điều quan trọng là constructor không đăng ký `this` ra bên ngoài; bên gọi nhận object hoàn chỉnh rồi mới công bố thông qua cơ chế thread-safe của registry. Không nên tin rằng chỉ đổi tên biến hoặc thêm `final` vào tham số constructor sẽ ngăn được this escape.

## 6. Safe publication: những con đường chuyển object cho thread khác

Đối tượng đã được khởi tạo đúng nên được chuyển qua một cơ chế có quan hệ bộ nhớ rõ ràng. Một số cách phổ biến:

| Cơ chế | Bảo đảm cần nhớ | Phù hợp khi |
| --- | --- | --- |
| Gán vào trường `volatile` sau khi constructor kết thúc | Ghi volatile và đọc volatile tương ứng tạo quan hệ visibility; một tham chiếu được công bố hoàn chỉnh | Một cấu hình hiện hành được thay thế theo phiên bản |
| `AtomicReference.set/get` | Công bố/đọc tham chiếu có ngữ nghĩa bộ nhớ phù hợp; có CAS để cạnh tranh cập nhật | Nhiều reader và trạng thái nguyên khối bất biến |
| Chuyển object qua `BlockingQueue.put/take` | API concurrent collection cung cấp bảo đảm truyền dữ liệu giữa producer và consumer | Bàn giao task hoặc thông điệp |
| Ghi/đọc dưới cùng `synchronized` hoặc lock có hợp đồng bộ nhớ | Hành động nhả khóa xảy ra trước hành động lấy khóa tiếp theo trên cùng cơ chế | Dữ liệu mutable cần bảo vệ nhất quán |
| Đưa tham chiếu vào một trường `static` được khởi tạo an toàn cùng lớp | Class initialization có quy tắc đồng bộ riêng | Singleton/constant khởi tạo khi lớp được sử dụng |
| Công bố trước `Thread.start()` tới thread vừa tạo | Hành động của caller trước `start()` happens-before các hành động của thread được khởi động | Bàn giao dữ liệu lúc tạo worker |

Chỉ đặt một tham chiếu vào một trường thường rồi cho thread khác đọc lại **không mặc nhiên là safe publication**. Bảo đảm đặc biệt của `final` có thể giúp một số dữ liệu khởi tạo, nhưng cách công bố thiếu đồng bộ còn gây nhiều vấn đề khác: reader có thể không thấy tham chiếu mới đúng lúc, đọc các trường non-final không đáng tin, hoặc không có thứ tự rõ với các cập nhật sau đó.

**Không hiểu sai:** `volatile` trên trường tham chiếu không làm **nội dung đối tượng** mutable tự an toàn đa luồng. Mô hình tốt là tạo toàn bộ object bất biến, rồi thay **một tham chiếu** bằng cơ chế công bố phù hợp. Nếu nhiều writer cùng tạo giá trị mới dựa trên giá trị cũ, phải giải quyết cạnh tranh cập nhật bằng CAS hoặc khóa, vì phép `current = next` chỉ đơn lẻ có thể làm mất cập nhật logic.

## 7. Ví dụ hoàn chỉnh: tạo đối tượng bất biến rồi công bố an toàn

Tạo tệp `FinalSettingsDemo.java`:

```java
import java.util.Objects;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicReference;

public class FinalSettingsDemo {
    private static final class Settings {
        private final String service;
        private final int maxAttempts;

        Settings(String service, int maxAttempts) {
            this.service = Objects.requireNonNull(service);
            if (maxAttempts <= 0) {
                throw new IllegalArgumentException("maxAttempts");
            }
            this.maxAttempts = maxAttempts;
        }

        String service() {
            return service;
        }

        int maxAttempts() {
            return maxAttempts;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        AtomicReference<Settings> current = new AtomicReference<>();
        CountDownLatch published = new CountDownLatch(1);

        Thread builder = new Thread(() -> {
            Settings complete = new Settings("catalog", 3);
            current.set(complete); // Công bố sau constructor.
            published.countDown();
        }, "builder");

        builder.start();
        published.await();

        Settings snapshot = current.get();
        System.out.println("service=" + snapshot.service());
        System.out.println("maxAttempts=" + snapshot.maxAttempts());
        builder.join();
    }
}
```

```bash
javac FinalSettingsDemo.java
java FinalSettingsDemo
```

Kết quả:

```text
service=catalog
maxAttempts=3
```

Phân tích:

1. `new Settings(...)` thiết lập các trường `final` và constructor trả về trước khi object được công bố.
2. `AtomicReference.set` chuyển tham chiếu hoàn chỉnh theo hợp đồng bộ nhớ của atomic reference. `CountDownLatch` cũng tạo quan hệ phối hợp để main không đọc `null`.
3. Main lấy một tham chiếu `snapshot` và đọc hai trường từ cùng đối tượng bất biến.
4. Trường `service` là `String` bất biến, trường `maxAttempts` là `int`, nên không có trạng thái con mutable bị chia sẻ qua hai trường này.
5. `builder.join()` kết thúc vòng đời worker. Trong ví dụ, cả `AtomicReference` và latch đã có bảo đảm chuyển giao dữ liệu; vì thế **kết quả này không phải phép thử tách riêng bảo đảm JMM của `final` khi tham chiếu được công bố thiếu đồng bộ**. Nó minh họa mẫu thiết kế an toàn được khuyến khích.

Nếu cần thay đổi cấu hình, tạo **Settings mới** và công bố tham chiếu mới thay vì thử sửa các trường `final`. Reader đang dùng snapshot cũ vẫn thấy snapshot đó không đổi; reader mới có thể nhận snapshot mới tùy thời điểm đọc.

## 8. `final` trên tham chiếu mutable: lỗi vẫn có thể xảy ra

Tạo tệp `FinalReferenceDemo.java`:

```java
public class FinalReferenceDemo {
    private static final class Box {
        final int[] values = {10, 20};
    }

    public static void main(String[] args) {
        Box box = new Box();

        System.out.println("before=" + box.values[0]);
        box.values[0] = 99;
        System.out.println("after=" + box.values[0]);
    }
}
```

```bash
javac FinalReferenceDemo.java
java FinalReferenceDemo
```

Kết quả:

```text
before=10
after=99
```

`box.values` không được phép gán sang mảng mới, nhưng phần tử bên trong mảng vẫn có thể đổi. Nếu nhiều thread cùng đọc/ghi `values[0]` mà không có cơ chế đồng bộ phù hợp, `final` trên `values` không tránh được data race.

Một số cách cải thiện thiết kế:

- Dùng kiểu bất biến thực sự, ví dụ một record chứa các trường nguyên thủy hoặc `String` bất biến.
- Với mảng mutable, sao chép phòng vệ khi đưa vào constructor và sao chép khi trả ra nếu cần tránh caller giữ tham chiếu và sửa sau lưng.
- Với collection, dùng các bản sao không sửa được và kiểm tra xem phần tử bên trong có mutable hay không.
- Nếu object thật sự phải thay đổi trong quá trình chạy, dùng cơ chế đồng bộ thích hợp quanh **mọi đường đọc/ghi** trạng thái đó, thay vì dựa vào `final` để thay cho khóa.

Đây là sự khác biệt giữa **immutable object**, **effectively immutable object** (được tạo xong rồi không sửa thêm trong thực tế), và **final reference to mutable object**. Chỉ trường hợp đầu tiên trực tiếp tạo mô hình bất biến rõ từ hợp đồng của kiểu dữ liệu. “Effectively immutable” có thể rất hữu ích, nhưng cần bảo đảm không còn đường cập nhật nào xảy ra sau công bố.

## 9. Trường `final` khác `volatile` ở đâu?

| Vấn đề | `final` instance field | `volatile` field |
| --- | --- | --- |
| Có được gán lại theo Java thông thường sau khi khởi tạo? | Không | Có |
| Dùng chủ yếu cho | Trạng thái khởi tạo ổn định và thiết kế bất biến | Giá trị được cập nhật/công bố giữa các thread |
| Bảo đảm JMM nổi bật | Quy tắc khởi tạo trường final và freeze khi đối tượng được xây dựng đúng | Visibility và thứ tự bộ nhớ của các thao tác volatile |
| Có khiến nhiều trường thành một transaction? | Không | Không |
| Có làm object được tham chiếu trở nên immutable? | Không | Không |
| Thay thế monitor khi cập nhật nhiều trường liên quan? | Không | Không |

Một trường có thể vừa là `static final` và chứa **tham chiếu tới một đối tượng mutable**, ví dụ `static final AtomicInteger COUNT`. Tham chiếu `COUNT` không đổi, nhưng trạng thái bên trong `AtomicInteger` thay đổi được qua các phương thức thread-safe của nó. Cần phân biệt thuộc tính của **biến chứa tham chiếu** với thuộc tính của **đối tượng được tham chiếu**.

Tương tự, `final int[] values` không biến phần tử mảng thành `final`; `volatile int[] values` không biến từng phần tử mảng thành volatile. Đây là hai ví dụ tiêu biểu về việc bảo đảm ở cấp **tham chiếu** không tự lan tới mọi trường/phần tử bên trong.

## 10. Khi nào bảo đảm final-field initialization không đủ?

### 10.1. Các trường khác không phải `final`

```java
class MixedState {
    final int id;
    int status;

    MixedState(int id) {
        this.id = id;
        this.status = 1;
    }
}
```

Với một object được khởi tạo đúng nhưng tham chiếu **công bố không an toàn**, quy tắc của `final` bảo vệ trường `id` theo phạm vi đặc biệt của nó; không thể dùng quy tắc đó để khẳng định `status` non-final luôn nhìn thấy giá trị constructor gán. Công bố an toàn sẽ đơn giản hóa hợp đồng cho **cả hai trường**.

### 10.2. Có cập nhật sau constructor

Giả sử `Settings` giữ một `final List<String> endpoints` rồi nhiều thread gọi `endpoints.add(...)`. Bảo đảm trạng thái khởi tạo của final field không cho biết các thread đọc danh sách có nhìn thấy lần thêm mới hay không, cũng không ngăn danh sách bị cập nhật đồng thời gây lỗi.

Nếu muốn trạng thái thay đổi có kiểm soát, hoặc tạo snapshot mới và thay tham chiếu nguyên tử, hoặc bảo vệ đối tượng mutable bằng đồng bộ.

### 10.3. Có this escape

Nếu đăng ký `this` trước khi hoàn thành constructor, thread khác có thể đọc giá trị mặc định khi trường final chưa được gán, như ví dụ `ThisEscapeDemo`. Không thể “cứu” hành vi đó chỉ bằng cách đổi trường thành `volatile` hoặc tạo `Thread.sleep(...)` để mong constructor chạy trước. Cần sửa **thời điểm công bố**.

### 10.4. Cập nhật nhóm nhiều biến liên quan

Hai trường `final` không thể thay đổi sau constructor, phù hợp khi cả hai cùng là một **trạng thái bất biến**. Nhưng nếu dữ liệu nghiệp vụ luôn cần cập nhật cặp giá trị, việc đổi hai trường thành `volatile` rồi cập nhật riêng sẽ không bảo đảm invariant. Chọn một immutable snapshot được công bố nguyên tử hoặc khóa cùng monitor cho cả thao tác cập nhật và đọc.

### 10.5. Reflection, serialization và các cơ chế đặc biệt

Reflection, cơ chế deserialization, native/unsafe hoặc bytecode instrumentation có thể can thiệp vào quá trình khởi tạo theo các đường không giống constructor Java thông thường. Các thay đổi trường final qua cơ chế đặc biệt có quy tắc và giới hạn phức tạp, có thể phụ thuộc JDK và runtime. **Không thiết kế giao thức concurrent dựa trên việc sửa trường final sau constructor.** Với ứng dụng Java bình thường, hãy tạo đối tượng mới rồi công bố tham chiếu mới.

## 11. Thiết kế constructor để object khó bị quan sát nửa chừng

Một số thói quen thiết kế giúp bảo đảm `final` thực sự có giá trị:

1. **Validate đầu vào trước khi công bố:** kiểm tra `null`, phạm vi giá trị, sự phù hợp giữa các tham số ngay trong constructor hoặc factory.
2. **Không đưa `this` cho thread khác trong constructor:** tránh ghi vào registry, gửi event, đăng ký callback có thể chạy ngay, hoặc `new Thread(() -> use(this)).start()`.
3. **Không gọi phương thức có thể override từ constructor** khi phương thức đó có thể dùng trạng thái lớp con hoặc công bố `this`. Dùng phương thức private/final cho logic khởi tạo nội bộ khi phù hợp.
4. **Chú ý các trường mutable được tham chiếu bởi final:** sao chép phòng vệ, tránh trả thẳng mảng hoặc collection mutable ra ngoài, hoặc có hợp đồng đồng bộ minh bạch.
5. **Ưu tiên object nhỏ, hoàn chỉnh, bất biến:** constructor thiết lập toàn bộ các giá trị liên quan; các hoạt động sau đó chỉ đọc.
6. **Công bố sau khi constructor trả về:** sử dụng `volatile`, atomic reference, concurrent collection hoặc monitor. Với một factory, tạo xong rồi mới đưa object vào cache/registry.
7. **Giữ nguyên tính nhất quán khi cập nhật:** thay nguyên snapshot bằng một hành động atomic hoặc dùng lock cho trạng thái mutable; final field không bảo vệ các tài nguyên khác chỉ vì chúng thuộc cùng object.

### Ví dụ factory thay vì đăng ký `this` ngay khi tạo

Thay cho một constructor tự đăng ký:

```java
// Ví dụ minh họa cách tổ chức, không phải chương trình độc lập.
final class Listener {
    private final String name;

    private Listener(String name) {
        this.name = name;
    }

    static Listener createAndRegister(String name, Registry registry) {
        Listener complete = new Listener(name);
        registry.register(complete);
        return complete;
    }
}
```

`Registry` là giao diện do ứng dụng định nghĩa; `register` phải có cơ chế thread-safe nếu cho thread khác truy cập. Điều thay đổi về kiến trúc là **constructor chỉ làm nhiệm vụ khởi tạo**, còn factory chỉ đăng ký sau khi object hoàn chỉnh.

Việc tạo constructor `private` không phải điều kiện bắt buộc cho final-field semantics, nhưng có thể giúp API ngăn việc gọi constructor rồi làm lộ `this` theo đường không chủ định.

## 12. Phân biệt bảo đảm và quan sát trong thí nghiệm concurrent

Khi thử một ví dụ JMM, không nên viết một vòng lặp đợi trên một trường non-volatile rồi nhận xét: “chạy một triệu lần vẫn luôn thấy đúng, vậy publication an toàn”. JMM cho phép nhiều hành vi mà một máy và một phiên bản JVM cụ thể có thể **không thể hiện dễ dàng**. Một chương trình có data race có thể trông đúng trong nhiều lần chạy và sai khi đổi tối ưu, CPU hoặc tải.

Một số cách lập luận đúng:

- Nếu thiết kế yêu cầu thread reader luôn nhận object hoàn chỉnh, **chứng minh đường công bố có happens-before**, thay vì chỉ kiểm tra output.
- Nếu thiết kế yêu cầu object không đổi sau khởi tạo, **kiểm tra khả năng rò rỉ mutable state**: có mảng, collection, builder, listener hoặc tham chiếu tới object thay đổi được không?
- Nếu constructor có thể bị truy cập giữa chừng, dùng điều phối bằng latch trong bài học để **chứng minh trạng thái thật sự chưa gán**, như `ThisEscapeDemo`. Điều đó không chứng minh rằng lỗi luôn xuất hiện theo cùng tần suất trong chương trình không điều phối.
- Nếu muốn kiểm tra tính đúng đắn của cập nhật nhiều field, tạo snapshot nhất quán dưới khóa hoặc dùng immutable snapshot, và diễn giải rõ điểm công bố.
- Dùng Java Flight Recorder, thread dump hoặc stress test để tìm vấn đề thực tế khi cần, nhưng không coi một lịch chạy cụ thể là định nghĩa của Java Memory Model.

## 13. Các hiểu nhầm thường gặp

**“Trường final giúp mọi trường của object an toàn đa luồng.”** Sai. Nó có bảo đảm riêng cho dữ liệu khởi tạo final; các trường mutable/non-final vẫn cần cơ chế đồng bộ thích hợp.

**“Chỉ cần khai báo `final List<?>` là có danh sách bất biến.”** Sai. Final giữ tham chiếu, không cấm sửa nội dung collection.

**“Có thể đăng ký `this` trong constructor vì mọi trường đều final.”** Sai. Thread khác có thể đọc object trước khi các phép gán thực sự xảy ra, và final-field guarantees yêu cầu proper construction.

**“Volatile khi công bố tham chiếu sẽ che giấu việc constructor chưa xong.”** Sai. Nếu tham chiếu được công bố quá sớm, thread khác có thể thấy giá trị mặc định. Volatile chỉ áp dụng các bảo đảm bộ nhớ theo thứ tự thực tế của những thao tác đã xảy ra.

**“Một object có trường final thì không cần công bố an toàn.”** Kết luận quá rộng. Final có bảo đảm đặc biệt cho những trường đó nếu đối tượng properly constructed, nhưng không giải quyết toàn bộ đời sống và các dữ liệu liên quan. Safe publication vẫn là chính sách được khuyến khích khi chuyển object giữa thread.

**“Dùng `static final` là giống hệt instance final.”** Không hoàn toàn. `static final` gắn với quá trình khởi tạo lớp; JVM bảo đảm đồng bộ class initialization theo cơ chế riêng. Nếu trường static final giữ mutable object, trạng thái bên trong object đó vẫn cần cơ chế điều phối khi thay đổi.

**“Record luôn immutable sâu.”** Không đúng. Các component của record được lưu trong trường final, nhưng nếu component là mảng hoặc object mutable thì vẫn có thể thay đổi nội dung. Record là lựa chọn tốt cho value object khi các thành phần của nó cũng được thiết kế bất biến hoặc sao chép phòng vệ phù hợp.

## 14. Tự kiểm tra kiến thức

**Câu 1.** Một lớp có `final int value` được gán trong constructor, đối tượng properly constructed, tham chiếu tới nó cuối cùng được một thread khác đọc qua đường công bố thiếu đồng bộ. Bảo đảm đặc biệt của `final` là gì?

**Trả lời:** Khi thread khác lấy được tham chiếu và đọc trường final theo ngữ nghĩa JMM, các giá trị final đã được gán trong quá trình khởi tạo đúng có bảo đảm visibility đặc biệt. Điều đó không bảo đảm việc thread đọc sẽ nhận được tham chiếu đúng hạn, cũng không mở rộng mọi bảo đảm sang trường non-final.

**Câu 2.** Vì sao `final int[] values` không đảm bảo `values[0]` an toàn khi nhiều thread sửa?

**Trả lời:** `final` chỉ cấm gán lại tham chiếu `values`; nội dung mảng vẫn mutable. Các phép đọc/ghi phần tử đồng thời vẫn có thể data race.

**Câu 3.** Trong constructor, object gán `shared = this` trước khi gán `final int answer = 42` (hoặc trước khi gán blank final trong constructor). Reader có thể thấy `answer = 0` không?

**Trả lời:** Có. Reader có thể chạy khi giá trị final chưa được gán. Việc công bố sớm vi phạm điều kiện proper construction.

**Câu 4.** Có nên dùng `volatile` cho mọi trường vốn chỉ thiết lập một lần và không thay đổi sau constructor?

**Trả lời:** Không cần làm vậy mặc định. Trường final thể hiện hợp đồng bất biến và có bảo đảm khởi tạo riêng. Khi chuyển object giữa các thread, chọn một cơ chế công bố an toàn cho toàn object và dùng volatile/lock nếu trạng thái thực sự cần cập nhật.

**Câu 5.** `AtomicReference<Config>` chứa một immutable `Config`. Nhiều writer cập nhật bản mới dựa trên bản cũ bằng `set` đơn giản. Có thể mất cập nhật không?

**Trả lời:** Có. Từng `set` nguyên tử nhưng hai writer có thể cùng đọc bản cũ và ghi đè lẫn nhau. Nếu mỗi cập nhật phụ thuộc trạng thái cũ, dùng `updateAndGet`/CAS với hàm chuyển đổi không có side effect hoặc dùng khóa phù hợp.

**Câu 6.** Một `record Config(int limit, List<String> hosts)` đã được khởi tạo. Nó có chắc chắn bất biến sâu không?

**Trả lời:** Không. Trường tham chiếu `hosts` là final nhưng bản thân `List` có thể mutable. Constructor nên tạo bản sao không sửa được (`List.copyOf`) khi hợp đồng cần tính bất biến và cân nhắc kiểu phần tử bên trong.

**Câu 7.** Tại sao gọi phương thức có thể bị override từ constructor của lớp cha là nguy hiểm ngay cả khi không tạo thread mới?

**Trả lời:** Phương thức override của lớp con có thể chạy trước khi các trường của lớp con khởi tạo xong, khiến nó quan sát trạng thái mặc định. Nếu phương thức còn công bố `this`, thread khác cũng có thể nhìn thấy object chưa hoàn chỉnh.

## 15. Tổng hợp

**`final` là lời cam kết về việc khởi tạo và không gán lại một trường**, đồng thời cung cấp bảo đảm đặc biệt trong Java Memory Model để giá trị khởi tạo của trường final được quan sát đúng khi object được xây dựng hợp lệ. Điều kiện nền tảng là **constructor hoàn tất mà không làm lộ `this` cho thread khác sử dụng trước đó**.

Một thiết kế dễ giữ đúng là tạo object bất biến với các trường final, kiểm tra đầy đủ invariant trong constructor, chỉ công bố sau khi hoàn thành qua cơ chế thread-safe, rồi đọc object đó như một snapshot. Nếu đối tượng chứa state mutable, final reference không thay thế khóa hoặc các cấu trúc concurrent. Phân biệt **khởi tạo đúng**, **công bố an toàn** và **cập nhật đồng thời an toàn** là chìa khóa để áp dụng JMM chính xác, tránh cả lỗi nhìn thấy dữ liệu khởi tạo lẫn race condition phát sinh về sau.
