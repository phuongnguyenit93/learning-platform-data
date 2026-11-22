# Đóng tài nguyên và hủy đăng ký theo quyền sở hữu

Khi một thao tác Java mở file, kết nối, stream, socket, lock hoặc đăng ký listener/callback, hệ thống thường cần thêm một thao tác đối xứng: đóng tài nguyên, trả kết nối, giải phóng khóa, hủy subscription hoặc gỡ listener. Nếu cleanup sai thời điểm hoặc sai người chịu trách nhiệm, chương trình có thể rò rỉ tài nguyên, xử lý sự kiện lặp, giữ đối tượng không còn dùng, hoặc làm hỏng tài nguyên đang được một thành phần khác sử dụng.

**Nguyên tắc trung tâm: thành phần nhận quyền sở hữu (owner) chịu trách nhiệm kết thúc vòng đời tài nguyên hoặc đăng ký do mình sở hữu.** Mã chỉ mượn tài nguyên (borrower) không được tự ý đóng tài nguyên ấy. Cách thiết kế này đặc biệt quan trọng khi có exception: luồng điều khiển có thể rời khỏi phương thức trước khi đi qua đoạn cleanup viết ở cuối thân hàm.

Bài này đặt việc đóng tài nguyên và hủy đăng ký trong mục **Bảo toàn trạng thái** của Java Exception: một thao tác thất bại vẫn phải để hệ thống trong trạng thái vòng đời hợp lệ, tránh tiếp tục giữ tài nguyên, callback hoặc tham chiếu không cần thiết.

## 1. Resource ownership là gì?

*Resource ownership* là quy ước xác định đối tượng hoặc phạm vi nào có quyền và nghĩa vụ kết thúc việc sử dụng một tài nguyên. Đây là **hợp đồng thiết kế**, không phải cơ chế mà Java tự gán bằng từ khóa riêng.

Các vai trò phổ biến:

| Vai trò | Ví dụ | Nghĩa vụ |
| --- | --- | --- |
| Owner tạo và giữ tài nguyên | Service mở một `InputStream` để đọc tệp | Đóng stream khi kết thúc phạm vi sử dụng, kể cả khi có exception. |
| Borrower sử dụng tạm | Hàm nhận `InputStream` từ caller chỉ để phân tích | Không đóng stream trừ khi hợp đồng ghi rõ quyền sở hữu được chuyển. |
| Owner của registration | Component gọi `eventBus.subscribe(listener)` và nhận một handle | Hủy đăng ký khi component dừng, bị thay thế hoặc không cần sự kiện nữa. |
| Owner chuyển giao quyền sở hữu | Factory tạo stream rồi trả ra để caller quản lý | Nêu rõ caller có trách nhiệm đóng; factory không đóng trước khi trả. |
| Owner tổng hợp | Một đối tượng tạo ba tài nguyên con và quản lý chúng | Đóng theo thứ tự phù hợp, xử lý cả trường hợp khởi tạo mới được một phần. |

Một ví dụ **minh họa API**, chưa phải chương trình chạy độc lập:

```java
// Caller sở hữu stream được truyền vào.
int parse(InputStream borrowedStream) throws IOException;

// Factory giao quyền sở hữu stream vừa tạo cho caller.
InputStream openReport() throws IOException;

// Đối tượng đăng ký thuộc caller cho đến khi caller close().
Registration subscribe(Listener listener);
```

Hai phương thức đầu đều có `InputStream` nhưng quy tắc đóng hoàn toàn khác nhau. Điều đó phải được nêu trong tên phương thức, Javadoc, tài liệu hợp đồng và/hoặc kiểu đối tượng trả về.

Không phải cứ giữ một biến tham chiếu là trở thành owner. Nhiều đối tượng có thể cùng tham chiếu một tài nguyên nhưng **chỉ nên có một cơ chế xác định rõ lúc nào tài nguyên được giải phóng**. Nếu thiết kế dùng shared ownership hoặc reference counting thì cần mô tả rõ cách phối hợp, không để mỗi thành phần đóng tự phát.

## 2. Vì sao cleanup ở cuối phương thức không đủ?

Xét một đoạn Java **minh họa vấn đề**:

```java
InputStream input = Files.newInputStream(path);
process(input);   // Nếu process ném exception...
input.close();    // ...dòng này không được chạy.
```

Không có gì bảo đảm rằng `process` sẽ hoàn thành bình thường. IOException, lỗi kiểm tra dữ liệu, exception do callback hay các lỗi khác có thể khiến luồng thực thi rời khỏi đoạn code trước `close()`.

Một biến thể dùng `finally` đúng hơn:

```java
InputStream input = Files.newInputStream(path);
try {
    process(input);
} finally {
    input.close();
}
```

`finally` thông thường được thực hiện khi rời khối `try`, kể cả khi có `return` hoặc exception. Tuy nhiên, ngoại lệ xảy ra ở `close()` có thể che khuất exception gốc nếu viết sơ sài; hệ thống cũng không bảo đảm chạy `finally` trong mọi sự cố ngoài tầm kiểm soát của JVM (ví dụ tiến trình bị cưỡng bức kết thúc).

Với `AutoCloseable` và `Closeable`, Java cung cấp **try-with-resources**, thường là lựa chọn tốt nhất cho tài nguyên sở hữu trong phạm vi rõ ràng.

## 3. Try-with-resources: tự động đóng khi rời phạm vi

Cú pháp cơ bản:

```java
try (InputStream input = Files.newInputStream(path)) {
    process(input);
}
```

Đoạn này minh họa việc đọc tệp; `path` và `process` giả định đã được khai báo. Sau khi tài nguyên được tạo thành công, khi rời khối `try`, Java sẽ gọi `input.close()`. Điều đó áp dụng cả khi phần thân thành công lẫn khi nó ném exception.

Đặc điểm quan trọng:

- Biến trong phần khai báo tài nguyên phải có kiểu triển khai `AutoCloseable`; `Closeable` cũng mở rộng `AutoCloseable`.
- Java đóng tài nguyên theo **thứ tự ngược lại với thứ tự khai báo**. Điều này hữu ích khi tài nguyên mở sau phụ thuộc vào tài nguyên mở trước.
- Nếu khởi tạo tài nguyên thứ hai thất bại, tài nguyên thứ nhất đã tạo thành công vẫn được đóng.
- Nếu phần thân và `close()` cùng ném exception, Java ưu tiên exception của phần thân; exception từ `close()` được gắn vào `getSuppressed()` của exception chính.
- Nếu phần thân thành công nhưng `close()` ném exception, exception lúc đóng có thể truyền ra ngoài.
- Try-with-resources không tự biết một tài nguyên là “borrowed” hay “owned”. **Đưa borrowed resource vào danh sách tài nguyên sẽ khiến nó bị đóng**, có thể vi phạm hợp đồng.

Ví dụ với hai tài nguyên **minh họa**:

```java
try (Resource first = openFirst();
     Resource second = openSecond(first)) {
    runOperation(first, second);
}
```

Ở đây các khai báo `Resource`, `openFirst`, `openSecond` và `runOperation` là giả định. Nếu tạo đủ hai tài nguyên, Java đóng `second` trước rồi `first`. Nếu tạo `second` thất bại, `first` vẫn được đóng. Thứ tự này tránh đóng nền tảng của một đối tượng bọc trước khi đóng đối tượng bọc, với điều kiện quan hệ phụ thuộc được thiết kế tương ứng.

### Java 9+ và tài nguyên có sẵn

Từ Java 9, một biến resource đã khai báo ở ngoài, nếu là `final` hoặc **effectively final**, có thể được dùng trực tiếp trong phần resource của `try`:

```java
InputStream owned = Files.newInputStream(path);
try (owned) {
    // Đọc stream do chính phạm vi này sở hữu.
}
```

Đây vẫn là **một thao tác đóng** đối với `owned`. Cú pháp không chứng minh quyền sở hữu; trách nhiệm của lập trình viên là chỉ đưa resource vào `try` khi phạm vi đó được phép đóng nó.

## 4. Khi nào người nhận tham số KHÔNG được close?

Giả sử API nhận một stream do caller tạo:

```java
public static int countBytes(InputStream borrowed) throws IOException {
    byte[] buffer = new byte[1024];
    int total = 0;
    int count;
    while ((count = borrowed.read(buffer)) != -1) {
        total += count;
    }
    return total;
}
```

Đây là **phương thức minh họa**, không chứa lớp hoàn chỉnh để chạy riêng. Nó đọc dữ liệu nhưng **không gọi `close()`**, vì caller là owner. Caller có thể tiếp tục thao tác với stream sau khi gọi, nếu đặc tính stream và vị trí đọc cho phép.

Tài liệu API nên giải thích:

> Phương thức chỉ mượn `input` trong thời gian gọi và không đóng stream. Caller giữ trách nhiệm đóng stream.

Nếu API quyết định tiếp nhận quyền sở hữu thì ghi rõ:

> Phương thức nhận quyền sở hữu stream và sẽ đóng stream sau khi hoàn thành hoặc thất bại.

Tuy nhiên, giao quyền sở hữu tại lời gọi có thể tạo câu hỏi: nếu validation thất bại trước khi API tiếp nhận, ai đóng? Hợp đồng phải xác định **thời điểm chuyển giao quyền sở hữu**. Đối với API khó mô tả, thường dễ bảo trì hơn nếu caller vẫn sở hữu tài nguyên và tự bao lời gọi trong `try-with-resources`.

Cũng đừng tự động đóng `System.in`, `System.out`, shared connection, context dùng chung hoặc stream do framework quản lý. Đóng một tài nguyên borrowed có thể làm hỏng các thao tác không liên quan phía sau.

## 5. Hủy đăng ký listener cũng là cleanup tài nguyên

Một đăng ký listener/subscriber thường tạo liên kết từ publisher tới callback. Publisher có thể giữ tham chiếu mạnh tới listener; listener lại có thể giữ component UI, service, cache hoặc đối tượng lớn. Nếu component biến mất nhưng không hủy registration, callback vẫn có thể được gọi và đồ thị đối tượng vẫn có thể được giữ sống.

Một thiết kế rõ quyền sở hữu trả về **handle** khi đăng ký:

```java
Registration registration = eventHub.subscribe(listener);
try {
    doWork();
} finally {
    registration.close();
}
```

Đây là minh họa với `Registration` giả định là `AutoCloseable` có `close()` không khai báo checked exception. Handle đại diện cho **quyền hủy đúng một đăng ký**; code sở hữu handle phải hủy khi hết nhu cầu.

Có hai kiểu API phổ biến:

| API | Cách cleanup | Rủi ro dễ gặp |
| --- | --- | --- |
| `addListener(listener)` / `removeListener(listener)` | Owner phải gọi `removeListener` với đúng listener instance | Dùng lambda mới lúc remove nên không trùng object đã add. |
| `subscribe(listener)` trả `Registration` hoặc `Subscription` | Owner giữ handle và gọi `close` / `unsubscribe` / `cancel` tương ứng | Bỏ quên handle hoặc nhầm quyền sở hữu khi chia sẻ handle. |

Đối với lambda:

```java
// Dễ sai: hai biểu thức lambda không phải một registration handle.
publisher.addListener(event -> handle(event));
publisher.removeListener(event -> handle(event));
```

Trong đoạn **minh họa**, `publisher` và `handle` chưa định nghĩa. Điều cần nhớ là không được dựa vào hai lần viết cùng mã lambda để đảm bảo xóa đúng đăng ký. Hãy lưu instance:

```java
Listener listener = event -> handle(event);
publisher.addListener(listener);
try {
    // Vòng đời của subscriber.
} finally {
    publisher.removeListener(listener);
}
```

Nếu API có handle độc lập, thường nên giữ handle thay vì phụ thuộc vào đối chiếu callback.

## 6. Thiết kế handle có thể dùng try-with-resources

Khi cần một đăng ký chỉ tồn tại trong phạm vi ngắn, có thể cho `Registration` triển khai `AutoCloseable`:

```java
public interface Registration extends AutoCloseable {
    @Override
    void close(); // Thu hẹp chữ ký: không khai báo checked Exception.
}
```

Đây là **định nghĩa interface độc lập**, không phải ví dụ chương trình có `main`. Nếu `subscribe` trả `Registration`, caller viết:

```java
try (Registration owned = eventHub.subscribe(listener)) {
    eventHub.publish("hello");
}
```

Tài nguyên registration được hủy ngay cả khi callback hoặc code bên trong `try` ném exception. Điều này giúp cleanup gắn với phạm vi lexical.

Lưu ý: `AutoCloseable.close()` có thể khai báo `throws Exception`; một override như trên thu hẹp thành **không ném checked exception**, khiến caller không phải xử lý `Exception` chỉ để hủy một đăng ký đơn giản. Đặc tả `AutoCloseable` **không bắt buộc** mọi implementation phải idempotent. Nếu thiết kế registration cho phép `close()` nhiều lần, cần cài đặt và ghi rõ điều đó.

Khi đăng ký sống lâu hơn một lệnh gọi — ví dụ listener của một component tồn tại nhiều phút — owner nên giữ handle trong field và đóng nó ở phương thức `stop()`/`close()` của component, thay vì tạo một try-with-resources ngắn khiến callback vừa đăng ký đã bị hủy quá sớm.

## 7. Ví dụ hoàn chỉnh Java 17: owner, borrowed resource và registration

Ví dụ mô phỏng ba tình huống:

1. Hai tài nguyên được tạo trong một phạm vi; thao tác thất bại và hai tài nguyên vẫn được đóng theo thứ tự ngược.
2. Caller tạo một tài nguyên, truyền cho hàm chỉ mượn; hàm mượn sử dụng nhưng không đóng.
3. Caller đăng ký một listener, sử dụng handle để hủy, gọi `close()` hai lần theo đúng hợp đồng idempotent của **handle trong ví dụ**, rồi xác nhận không còn subscriber.

Tạo tệp `OwnershipCleanupDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.function.Consumer;

public class OwnershipCleanupDemo {

    private static final List<String> EVENTS = new ArrayList<>();

    private interface Registration extends AutoCloseable {
        @Override
        void close();
    }

    private static final class Resource implements AutoCloseable {
        private final String name;
        private boolean closed;

        Resource(String name) {
            this.name = name;
            EVENTS.add("open " + name);
        }

        void work(boolean fail) {
            if (closed) {
                throw new IllegalStateException("resource closed");
            }
            if (fail) {
                throw new IllegalStateException("work failed");
            }
            EVENTS.add("work " + name);
        }

        @Override
        public void close() {
            if (!closed) {
                closed = true;
                EVENTS.add("close " + name);
            }
        }
    }

    private static final class EventHub {
        private final List<Consumer<String>> listeners = new ArrayList<>();

        Registration subscribe(Consumer<String> listener) {
            Objects.requireNonNull(listener, "listener");
            listeners.add(listener);

            return new Registration() {
                private boolean closed;

                @Override
                public void close() {
                    if (!closed) {
                        closed = true;
                        listeners.remove(listener);
                        EVENTS.add("unsubscribe");
                    }
                }
            };
        }

        void publish(String value) {
            for (Consumer<String> listener : List.copyOf(listeners)) {
                listener.accept(value);
            }
        }

        int subscriberCount() {
            return listeners.size();
        }
    }

    private static void failDuringWork() {
        try (Resource first = new Resource("first");
             Resource second = new Resource("second")) {
            second.work(true);
        }
    }

    // Borrower: tuyệt đối không đóng tài nguyên do caller sở hữu.
    private static void useBorrowed(Resource borrowed) {
        borrowed.work(false);
    }

    public static void main(String[] args) {
        try {
            failDuringWork();
        } catch (IllegalStateException ex) {
            EVENTS.add("caught: " + ex.getMessage());
        }

        // Phạm vi này là owner của Resource.
        try (Resource callerOwned = new Resource("caller-owned")) {
            useBorrowed(callerOwned);
        }

        EventHub hub = new EventHub();
        Registration ownedRegistration =
                hub.subscribe(value -> EVENTS.add("event: " + value));

        hub.publish("one");
        ownedRegistration.close();
        ownedRegistration.close(); // Idempotent theo code của ví dụ.
        hub.publish("two");
        EVENTS.add("subscribers: " + hub.subscriberCount());

        EVENTS.forEach(System.out::println);
    }
}
```

Chạy với Java 17+:

```bash
javac -encoding UTF-8 OwnershipCleanupDemo.java
java OwnershipCleanupDemo
```

Kết quả chuẩn:

```text
open first
open second
close second
close first
caught: work failed
open caller-owned
work caller-owned
close caller-owned
event: one
unsubscribe
subscribers: 0
```

Tại sao kết quả như vậy?

- `first` mở trước `second`. Exception xảy ra trong `second.work(true)`, nhưng try-with-resources vẫn đóng `second` rồi `first`, trước khi exception tới `catch` bên ngoài.
- `useBorrowed` chỉ gọi `work(false)`. `callerOwned` được đóng bởi `try` của **caller**, không bởi hàm mượn.
- `subscribe` thêm đúng một listener. Sau khi nhận sự kiện `one`, owner đóng registration. Sự kiện `two` không còn được chuyển cho listener nên không có dòng `event: two`.
- Lần `close()` thứ hai không thay đổi trạng thái do implementation của ví dụ đã kiểm tra `closed`; chỉ xuất hiện một dòng `unsubscribe`.
- `subscriberCount()` bằng 0 chứng minh ở ví dụ đồng bộ này danh sách listener đã được dọn. Trong hệ thống thật, cần xem xét luồng đồng thời và callback đang chạy.

**Giới hạn của ví dụ:** `EventHub` và `Resource` dùng `ArrayList` và cờ boolean để trình diễn thứ tự một luồng; chúng **không thread-safe**. Không dùng nguyên mẫu này làm event bus đa luồng. Trong thực tế, cần chính sách đồng bộ, vòng đời và điều kiện hủy phù hợp.

## 8. Exception xảy ra trong quá trình close: getSuppressed()

Một vấn đề tinh tế: phần thân thao tác ném lỗi A; trong khi dọn dẹp, `close()` lại ném lỗi B. Exception nào nên được truyền ra?

Với try-with-resources, exception từ phần thân là exception chính; exception xảy ra khi đóng được **suppressed** vào exception chính. Điều này bảo toàn cả hai nguyên nhân mà không để lỗi cleanup che mất lỗi ban đầu.

Tạo file `SuppressedCleanupDemo.java`:

```java
import java.io.IOException;

public class SuppressedCleanupDemo {

    private static final class FailingClose implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    public static void main(String[] args) {
        try (FailingClose resource = new FailingClose()) {
            throw new IOException("work failed");
        } catch (IOException ex) {
            System.out.println(ex.getMessage());
            System.out.println(ex.getSuppressed().length);
            System.out.println(ex.getSuppressed()[0].getMessage());
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 SuppressedCleanupDemo.java
java SuppressedCleanupDemo
```

Kết quả chuẩn:

```text
work failed
1
close failed
```

`ex.getSuppressed()` là mảng các exception bị suppressed. Trong ví dụ, thao tác chính tạo một `IOException` và `close` tạo một `IOException` khác. Nếu chỉ `close()` lỗi trong khi thân `try` thành công, lỗi từ `close()` có thể trở thành exception chính.

Không nên “sửa” bằng cách nuốt tất cả lỗi `close()`. Lỗi đóng có thể làm mất dữ liệu hoặc cho biết thao tác hoàn tất không chắc chắn (ví dụ khi flush buffer). Cần xác định chính sách cụ thể: caller có cần biết lỗi đóng không, trạng thái có thể khôi phục không, log nên ghi ở đâu.

Một `catch` bên ngoài chỉ nhận exception cuối cùng; nếu muốn điều tra đầy đủ, ghi nhận cả cause và suppressed exceptions bằng hệ thống logging thích hợp.

## 9. Cleanup trong finally, trạng thái và thứ tự ưu tiên lỗi

`finally` vẫn cần thiết cho các cơ chế không biểu diễn tự nhiên bằng `AutoCloseable` hoặc khi phải thực hiện hành động điều kiện. Nhưng hãy tránh cấu trúc:

```java
try {
    doWork();
} finally {
    resource.close(); // Có thể ném và che exception từ doWork().
}
```

Đây là mảnh minh họa, với `doWork` và `resource` được định nghĩa ở nơi khác. Nếu `doWork` ném exception A và `close()` ném exception B, câu lệnh `finally` ở đây có thể khiến exception B thay thế A. Nếu resource triển khai `AutoCloseable`, try-with-resources thường giải quyết việc bảo toàn cả hai tốt hơn.

Khi dùng `finally` với callback registration, nếu `unsubscribe()` cũng có thể ném, phải xác định cách giữ lỗi ban đầu và báo lỗi cleanup. Đừng mặc định swallow exception vì “chỉ là giải phóng”; ngược lại, không nên để lỗi cleanup không quan trọng làm hỏng luồng xử lý nghiệp vụ nếu hợp đồng cleanup thực sự bảo đảm an toàn khi bỏ qua. Quyết định phải dựa trên semantics của API.

Nếu nhiều bước cleanup thủ công, nên bảo đảm một bước thất bại không vô tình ngăn bước giải phóng tài nguyên độc lập còn lại. Try-with-resources hỗ trợ tự động đóng nhiều tài nguyên ngay cả khi việc đóng một tài nguyên ném exception.

## 10. Khởi tạo một phần cũng cần cleanup

Giả sử component cần ba registration. Nếu bước thứ ba thất bại, hai bước đầu vẫn đang tồn tại. Nếu chỉ đóng các handle sau khi tất cả đã khởi tạo thành công, chương trình có thể rò rỉ ngay trong constructor/startup.

Các cách thiết kế:

1. **Tạo và đăng ký trong phạm vi có thể rollback.** Khi thao tác tiếp theo thất bại, đóng những tài nguyên/handle đã tạo trước đó.
2. **Chỉ chuyển quyền sở hữu sau khi khởi tạo thành công.** Factory có thể giữ các tài nguyên trong phạm vi tạm; khi xây dựng xong mới giao một đối tượng composite có `close()` quản lý toàn bộ.
3. **Làm rõ mỗi điểm lỗi.** Nếu bước mở kết nối thứ hai ném, kết nối thứ nhất có được đóng không? Nếu callback đã đăng ký mà phần còn lại fail, handle cũ có bị hủy không?

Đoạn dưới minh họa một composite scope khi subscription trả handle `AutoCloseable`. Đây là **mã minh họa theo ý tưởng**, chưa bao gồm `subscribeA`, `subscribeB`, `run` và kiểu handle thực tế:

```java
try (Registration first = subscribeA();
     Registration second = subscribeB()) {
    run();
}
```

Nếu `subscribeB()` ném exception, `first` được đóng. Nhưng nếu `subscribeB()` tạo đăng ký rồi ném **trước khi trả handle**, code tại caller chưa nhận quyền hủy đăng ký đó. Do vậy, chính implementation của `subscribeB()` phải cleanup mọi phần tài nguyên mà nó đã tạo trước khi báo lỗi. Đây là điểm phân biệt giữa **cleanup của caller sau khi nhận handle** và **cleanup nội bộ khi factory thất bại giữa chừng**.

### Giao quyền sở hữu sau khi hoàn tất xây dựng

Một composite có thể sở hữu nhiều resource con và đóng chúng theo thứ tự ngược. Owner composite cần giữ trạng thái `closed` và xác định có thể gọi `close` nhiều lần hay không. Nếu người dùng không thể tạo composite hợp lệ do ném exception giữa chừng, factory/builder có trách nhiệm đóng phần đã tạo; không được đẩy trách nhiệm sang caller khi caller chưa nhận được đối tượng.

## 11. Hủy đăng ký và cạnh tranh đồng thời

Với publisher đa luồng, cần phân biệt hai mệnh đề:

1. **Không nhận callback mới sau khi hủy.**
2. **Không còn callback nào đang chạy khi lời gọi hủy trả về.**

Một API có thể bảo đảm (1) cho các sự kiện bắt đầu sau thời điểm hủy, nhưng **không tự động bảo đảm (2)**. Callback đã được xếp hàng hoặc bắt đầu chạy trước khi gọi `unsubscribe()` có thể tiếp tục sau khi hủy, tùy implementation.

Ví dụ trình tự:

```text
Thread A: publisher đã chọn listener để gọi
Thread B: owner gọi unsubscribe()
Thread B: unsubscribe() trả về
Thread A: callback có thể vẫn chạy, nếu API không chờ callback đang chạy
```

Để tránh dùng trạng thái đã đóng:

- Callback có thể kiểm tra trạng thái lifecycle trước khi truy cập dữ liệu nhạy cảm.
- Publisher phải có cơ chế đồng bộ, phiên bản hoặc generation token khi cần loại bỏ sự kiện cũ.
- Nếu API hứa rằng hủy xong thì mọi callback đã dừng, cần cơ chế chờ/drain phù hợp; không thể chỉ xóa một phần tử khỏi list.
- Khi cleanup callback cũng cần dừng thread, executor, timer hoặc network listener, phải phân biệt **cancel request** với **await completion** theo hợp đồng của từng API.
- Không đặt lock giữ lâu rồi gọi callback tùy ý nếu có nguy cơ deadlock/reentrant call; thiết kế cụ thể phụ thuộc concurrency model.

Tài liệu `close()`/`unsubscribe()` nên nói rõ bảo đảm về callback in-flight và thread safety. Ví dụ `EventHub` ở mục trước chỉ chứng minh hành vi trong một luồng, không mang những bảo đảm đồng thời này.

## 12. Cancellation, interruption và quyền sở hữu

Không phải đăng ký nào cũng dùng `close()`. Một số API trả `Future`, `Subscription` hoặc token có phương thức `cancel()`. Owner của tác vụ/subscription cần quyết định khi nào hủy, nhưng semantics không giống hệt đóng stream.

- `Future.cancel(boolean mayInterruptIfRunning)` là yêu cầu hủy. Giá trị trả về cho biết yêu cầu hủy có thành công theo trạng thái của `Future`; nó không chứng minh tác vụ đã dừng ngay lập tức.
- Với API Reactive Streams, `Subscription.cancel()` yêu cầu ngừng truyền tín hiệu tiếp theo theo contract của giao thức; vẫn phải hiểu các race và tín hiệu in-flight.
- Khi một thread bị ngắt qua `InterruptedException`, không vô tình làm mất cờ interrupt nếu bắt exception rồi chuyển nghĩa. Thông thường cần `Thread.currentThread().interrupt()` trước khi truyền lỗi ở dạng khác, trừ khi phương thức đã truyền tiếp chính `InterruptedException` hoặc có chính sách khác rõ ràng.
- Hủy subscription không mặc nhiên đóng producer hoặc tài nguyên chia sẻ với subscriber khác. Owner phải chỉ hủy thứ mình sở hữu.

Ví dụ **mảnh minh họa**, giả định có kiểu `TaskCancelledException` riêng:

```java
try {
    waitForWork();
} catch (InterruptedException cause) {
    Thread.currentThread().interrupt();
    throw new TaskCancelledException("Tác vụ bị ngắt", cause);
} finally {
    registration.close();
}
```

Ở đây `waitForWork`, `TaskCancelledException` và `registration` là các ký hiệu minh họa chưa khai báo đầy đủ. Nếu `registration.close()` có thể ném, cần áp dụng chính sách giữ exception gốc ở mục 8–9. Việc khôi phục interrupt giúp logic phía trên còn nhận biết yêu cầu ngắt khi exception không tiếp tục được ném với kiểu `InterruptedException`.

## 13. Đóng tài nguyên không đồng nghĩa với rollback

Cleanup trả lại tài nguyên và hủy liên kết, nhưng **không tự đảo ngược mọi thay đổi nghiệp vụ**.

Ví dụ:

- Đóng `FileOutputStream` không xóa dữ liệu đã ghi.
- Đóng JDBC connection không phải lúc nào cũng tương đương rollback theo hợp đồng ứng dụng; quản lý transaction phải có quy tắc commit/rollback riêng.
- Hủy listener không rút lại các sự kiện mà callback đã xử lý.
- Cancel một request HTTP không chứng minh server chưa ghi dữ liệu.
- Đóng client mạng có thể hủy các request khác nếu client là tài nguyên chia sẻ.

Vì vậy, cần tách ba nhiệm vụ:

| Nhiệm vụ | Mục tiêu | Ví dụ |
| --- | --- | --- |
| Cleanup vòng đời | Giải phóng tài nguyên/registration thuộc sở hữu | `close()`, `unsubscribe()`, `removeListener()`. |
| Rollback/compensation | Khôi phục hoặc bù các thay đổi nghiệp vụ | Rollback transaction, xóa bản ghi tạm hoặc thực hiện thao tác bù. |
| Bảo toàn lỗi | Giữ thông tin lỗi chính và lỗi cleanup | `getCause()`, `getSuppressed()`, logging có ngữ cảnh. |

Khi thao tác cần cam kết **strong exception safety** (thất bại không đổi trạng thái quan sát được), phải thiết kế staging, transaction hoặc rollback thực sự; chỉ thêm `finally { close(); }` chưa đủ.

Với thao tác có **basic exception safety**, trạng thái có thể thay đổi một phần nhưng invariant của đối tượng vẫn đúng và không rò rỉ tài nguyên. Cần xác định mức bảo đảm phù hợp thay vì suy đoán.

## 14. Thiết kế vòng đời và hợp đồng public API

Một API quản lý tài nguyên tốt trả lời rõ:

- **Ai tạo?** Ai có quyền sở hữu handle?
- **Ai đóng?** Caller, callee, container/framework hay lifecycle manager?
- **Đóng lúc nào?** Hết phương thức, kết thúc transaction, dừng component, hết ứng dụng?
- **Close lần hai ra sao?** Idempotent, ném lỗi hay không xác định? Không giả định từ `AutoCloseable`.
- **Close có thể ném gì?** Lỗi cleanup có quan trọng với caller? Có thể còn pending write hay không?
- **Sau close được gọi lại phương thức khác không?** Nếu không, exception nào báo trạng thái không hợp lệ?
- **Có callback in-flight không?** Hủy subscription có đợi callback đang chạy kết thúc không?
- **Tài nguyên có được chia sẻ không?** Nếu có, một borrower có thể vô tình làm hỏng người khác khi đóng không?
- **Khởi tạo lỗi giữa chừng thì sao?** Có dọn đủ resource tạo thành công trước đó không?

Javadoc minh họa hợp đồng cho handle registration (chưa có implementation):

```java
/**
 * Quyền sở hữu một đăng ký listener.
 *
 * <p>Được tạo bởi {@code subscribe}. Caller phải đóng khi không
 * còn cần nhận sự kiện. Đóng nhiều lần không tạo tác dụng bổ sung.
 * Sau khi close trả về, không có callback mới được bắt đầu;
 * callback đã chạy trước đó có thể tiếp tục hoàn thành.
 */
public interface Registration extends AutoCloseable {
    /**
     * Hủy đăng ký do handle này đại diện.
     */
    @Override
    void close();
}
```

Đoạn Javadoc này chỉ phù hợp với **một implementation thực sự bảo đảm đúng các điều đã mô tả**. Không sao chép vào mọi event bus; đặc biệt, lời hứa “không có callback mới” cần đồng bộ thích hợp khi có concurrency.

Nếu phương thức trả handle theo cách chuyển quyền sở hữu, có thể ghi:

```java
/**
 * Đăng ký listener và chuyển quyền sở hữu registration cho caller.
 *
 * @param listener callback nhận sự kiện, không được null
 * @return handle phải được caller đóng khi không còn cần sự kiện
 * @throws NullPointerException nếu {@code listener == null}
 */
Registration subscribe(Listener listener);
```

Đây là đoạn chữ ký minh họa, `Listener` chưa được khai báo. API thực tế có thể dùng callback type khác.

## 15. Các lỗi thiết kế thường gặp

**1. Dùng `try-with-resources` với một tài nguyên được mượn.** Cú pháp đúng nhưng ý nghĩa sai: nó gọi `close()` lên resource của caller. Xác định owner trước khi viết `try`.

**2. Đóng quá sớm.** Subscribe trong một `try` kết thúc ngay sau khi tạo UI; khi UI thật sự hoạt động, listener đã bị hủy. Phạm vi cleanup phải cùng vòng đời với nhu cầu sử dụng, không chỉ phạm vi lexical ngắn nhất.

**3. Không đóng khi constructor hoặc startup thất bại.** Mới tạo được một số tài nguyên nhưng không trả object về caller; phần triển khai phải tự rollback phần acquisition đã thành công.

**4. Không hủy đăng ký callback.** Publisher giữ listener mãi, dẫn đến callback sau khi component dừng, giữ tham chiếu và đôi khi xử lý sự kiện nhiều lần.

**5. Dùng lambda mới để remove listener cũ.** Lưu đúng instance hoặc giữ handle registration do API trả về.

**6. Swallow mọi lỗi close.** Đặc biệt với stream có flush, close thất bại có thể là dấu hiệu dữ liệu chưa được ghi đầy đủ. Phân biệt cleanup không thể thất bại với cleanup có hậu quả.

**7. Giả định mọi close là idempotent.** `AutoCloseable` không bảo đảm điều này cho mọi implementation. Thiết kế tự định nghĩa hoặc tuân theo contract cụ thể của thư viện.

**8. Chỉ cleanup thành công, bỏ nhánh exception.** Sử dụng try-with-resources hoặc finally phù hợp; kiểm tra nhánh thất bại trước/sau acquisition.

**9. Giả định unsubscribe dừng ngay callback đa luồng.** Tùy API, callback đã chạy hoặc được xếp hàng có thể còn tiếp tục. Cần lifecycle synchronization nếu muốn cam kết mạnh hơn.

**10. Nhầm cleanup với rollback.** Đóng resource không phục hồi dữ liệu đã thay đổi. Nếu API hứa trạng thái không đổi khi thất bại, cần transaction/compensation riêng.

## 16. Kiểm thử exception safety của cleanup

Nên thử các tình huống gần ranh giới vòng đời:

| Tình huống | Điều cần khẳng định |
| --- | --- |
| Thao tác thành công | Resource owner đóng đúng một lần theo contract, hoặc đúng số lần logic yêu cầu. |
| Thân `try` ném exception | Resource vẫn được đóng; exception chính không mất. |
| Lỗi khi tạo resource thứ hai | Resource thứ nhất đã mở được đóng, không còn dangling registration. |
| Cả xử lý và `close()` đều ném | Primary exception còn nguyên; lỗi close nằm trong `getSuppressed()`. |
| Hàm chỉ mượn resource | Resource của caller vẫn mở sau lời gọi, caller là bên đóng. |
| Subscribe rồi cleanup | Listener không nhận sự kiện mới theo bảo đảm của API; handle không bị bỏ quên. |
| Close handle hai lần | Kết quả đúng chính sách idempotency đã tài liệu hóa. |
| Unsubscribe đồng thời với publish | Không có data race/deadlock; kết quả theo contract về callback in-flight. |
| Thao tác ghi thất bại giữa chừng | Xác nhận side effect/rollback theo bảo đảm API, tách khỏi việc giải phóng tài nguyên. |

Với ví dụ `OwnershipCleanupDemo`, kiểm tra danh sách `EVENTS` cho biết thứ tự đóng, và `subscribers: 0` cho thấy registration được gỡ. Với ứng dụng thực, cần test ở cấp adapter hoặc integration để bắt rò rỉ file handle, connection, listener và task còn chạy.

Hãy ưu tiên **kiểm tra hành vi** hơn là assert chi tiết implementation. Ví dụ, nếu hợp đồng chỉ hứa tài nguyên cuối cùng được đóng, không cần buộc implementation phải có đúng một lần gọi nội bộ `close` nếu cơ chế idempotent được cho phép.

## 17. Bài tập và câu hỏi tự kiểm tra

**Tình huống A:** Hàm `parse(InputStream input)` nhận stream từ caller. Nó có nên viết `try (input)` không?

**Đáp án:** Chỉ khi hợp đồng trao quyền sở hữu cho `parse`. Nếu API chỉ mượn stream, hàm không được tự đóng. Caller nên bao việc tạo và gọi trong `try-with-resources`.

**Tình huống B:** Component đăng ký ba listener, nhưng đăng ký thứ ba ném exception. Ai hủy hai listener đầu?

**Đáp án:** Thành phần đang sở hữu hai registration đầu trong giai đoạn khởi tạo phải hủy chúng trước khi báo thất bại. Nếu factory chưa trả component về caller, caller không thể thực hiện cleanup nội bộ này.

**Tình huống C:** Trong try-with-resources, phần xử lý ném `IOException("write")` và `close()` ném `IOException("close")`. Caller thường nhận gì?

**Đáp án:** Nhận exception chính `"write"`; exception `"close"` nằm trong `getSuppressed()`. Với một `finally` tự viết gọi `close()` trực tiếp, lỗi close có thể che mất lỗi xử lý.

**Tình huống D:** `unsubscribe()` trả về nhưng callback đã bắt đầu ở thread khác vẫn đang chạy. Có chắc API sai không?

**Đáp án:** Chưa chắc. Phải xem contract có bảo đảm chờ callback in-flight hay chỉ ngăn đăng ký nhận sự kiện mới. Nếu cần chặn cả callback đang chạy, phải thiết kế cơ chế đồng bộ hoặc đợi hoàn thành tương ứng.

**Tình huống E:** Một đối tượng shared HTTP client được dùng bởi mười request. Mỗi request có nên gọi `client.close()` không?

**Đáp án:** Không, nếu client thuộc sở hữu của application/lifecycle manager và request chỉ mượn. Mỗi request chỉ cleanup tài nguyên mình sở hữu (ví dụ body/response riêng theo contract thư viện). Owner của shared client đóng nó ở cuối vòng đời ứng dụng.

## 18. Nguyên tắc áp dụng

Quy tắc dễ kiểm tra nhất là vẽ một cặp **acquire → release** cho mỗi tài nguyên, subscription hoặc tác vụ: ai nhận trách nhiệm, thời điểm giải phóng, đường lỗi nào đi qua cleanup, và chuyện gì xảy ra nếu cleanup cũng thất bại. Đưa tài nguyên sở hữu trong phạm vi ngắn vào try-with-resources; dùng handle/lifecycle rõ ràng cho đăng ký sống lâu; giữ borrowed resource nguyên vẹn; xét cả khởi tạo một phần và cạnh tranh đồng thời. Khi làm được vậy, exception có thể làm thao tác thất bại mà vẫn không biến failure thành rò rỉ tài nguyên hoặc trạng thái vòng đời sai.