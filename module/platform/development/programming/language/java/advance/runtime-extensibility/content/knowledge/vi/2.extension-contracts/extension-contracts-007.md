# Thiết kế callback, sự kiện và quy tắc hủy đăng ký trong Java runtime extensibility

## 1. Bài toán của một hợp đồng mở rộng

Một runtime có thể cho phép plugin đăng ký logic vào các điểm mở rộng: sau khi cấu hình thay đổi, trước khi tác vụ chạy, khi một tài nguyên được cập nhật hoặc khi một thành phần chuyển trạng thái. Runtime giữ vai trò *publisher* (phát thông báo); phần mở rộng giữ vai trò *subscriber/listener* (nhận thông báo). Hợp đồng phải trả lời rõ **ai được đăng ký, lúc nào callback chạy, lỗi được xử lý ra sao và khi nào đăng ký kết thúc**.

- **Callback** là hàm được runtime gọi theo một hợp đồng (ví dụ `onFileChanged(event)`); nó có thể là một phần của lệnh yêu cầu xử lý hoặc của thông báo.
- **Event** là dữ liệu mô tả điều đã xảy ra, thường bất biến, có kiểu và không buộc publisher biết plugin cụ thể.
- **Listener/handler** là callback đăng ký để nhận một loại sự kiện.
- **Subscription/registration** là một lần đăng ký cụ thể, có danh tính và vòng đời riêng. Kết quả đăng ký nên là một đối tượng có thể `close()` để hủy đăng ký.
- **Unsubscribe** là ngừng nhận các lần phát tiếp theo theo ngữ nghĩa đã công bố. Nó không mặc nhiên là hủy tác vụ đang chạy, thu hồi sự kiện đã xử lý, hoặc chờ mọi callback đang chạy kết thúc.

Trong hợp đồng mở rộng, **không nên chỉ có `addListener(listener)` mà thiếu cách tháo đăng ký**. Một registry sống lâu giữ tham chiếu mạnh đến listener, lambda và đối tượng plugin; plugin đã “dừng” vẫn có thể nhận sự kiện và class loader của plugin có thể không được giải phóng.

## 2. Thiết kế API và quyết định ngữ nghĩa trước khi viết code

Ví dụ giao diện API tối thiểu:

```java
@FunctionalInterface
interface Subscription extends AutoCloseable {
    @Override void close(); // không khai báo checked exception
}

Subscription subscribe(Consumer<? super Event> listener);
void publish(Event event);
```

Đây là **phác thảo chữ ký**, không phải một tệp Java độc lập; chương trình chạy được nằm ở mục 4. Một hợp đồng rõ ràng cần nêu:

| Khía cạnh | Quy tắc cho ví dụ trong bài | Vì sao phải công bố |
|---|---|---|
| Đăng ký | `subscribe` từ chối `null`; mỗi lần gọi tạo một token riêng | Cùng một handler có thể có nhiều đăng ký độc lập |
| Phát sự kiện | `publish` từ chối `null`; không lưu lịch sử hay phát lại | Người dùng không hiểu nhầm đây là event log/message broker |
| Thời điểm callback | Gọi **đồng bộ trên luồng gọi `publish`** | Handler chậm sẽ làm publisher chậm |
| Thứ tự | Một lượt phát đi theo thứ tự các đăng ký có mặt trong snapshot của lượt đó | Không hứa thứ tự tuyệt đối khi nhiều thread đăng ký/phát cùng lúc |
| Khi có lỗi | Bắt `RuntimeException` của từng handler, chuyển vào `onError` rồi tiếp tục listener khác | Một plugin lỗi không khiến plugin sau bị bỏ qua |
| Hủy đăng ký | `Subscription.close()` idempotent và loại bỏ đúng một đăng ký | Có thể gọi trong cleanup nhiều lần |
| Hủy trong lúc phát | Vòng lặp duyệt snapshot; trước mỗi callback còn kiểm tra trạng thái active | Hủy đăng ký không nhất thiết ngăn callback đã bắt đầu hoặc vừa vượt qua kiểm tra active |
| Đồng thời | Registry hỗ trợ subscribe/close/publish đồng thời; các lần `publish` khác nhau có thể chạy callback cùng lúc | Listener phải tự bảo đảm an toàn cho trạng thái nội bộ |
| Sở hữu | Bên đăng ký giữ token và đóng khi plugin/đối tượng kết thúc | Tránh callback “mồ côi” và rò rỉ tham chiếu |

Không phải hệ thống nào cũng dùng các lựa chọn này. Với *interceptor*, “trước khi xử lý” thường là callback có thứ tự, quyền từ chối và chính sách lỗi khác event thông báo. Với message delivery cần retry, acknowledgement, durable log hoặc backpressure thì API event bus nhỏ như ví dụ này chưa đủ.

### Callback hay event?

Hãy dùng **callback yêu cầu kết quả** khi runtime cần một câu trả lời để tiếp tục (validate, authorize, transform, choose strategy). Quy định rõ thời hạn, lỗi, thứ tự và khả năng từ chối; không xem nó như “thông báo không cần trả lời”.

Hãy dùng **event thông báo** khi runtime báo điều đã xảy ra mà không cần handler trả về kết quả. Đặt tên theo sự kiện quá khứ (`FileChanged`, `PluginStopped`), dùng payload có kiểu và tránh để listener sửa dữ liệu chung. Nếu “event” là một yêu cầu bắt buộc mọi handler phải thành công mới commit, hãy thiết kế lại thành workflow/hợp đồng đồng bộ có kết quả rõ ràng.

## 3. Vòng đời subscription

Một trình tự hợp lý cho extension:

1. Runtime tạo registry và công bố hợp đồng sự kiện.
2. Plugin khởi tạo, gọi `subscribe(handler)`, **lưu token trả về** trong phạm vi sở hữu của plugin.
3. Publisher tạo payload hoàn chỉnh, gọi `publish(event)`; registry chọn listener đang hoạt động và gọi callback theo chính sách đã công bố.
4. Khi plugin shutdown, bị unload, restart hoặc không còn cần dữ liệu, plugin gọi `subscription.close()` **trước khi thả tài nguyên mà callback dùng đến**.
5. Runtime có thể tiếp tục phát cho các plugin khác. Lần `close()` thứ hai không thay đổi trạng thái.

Vòng đời này phải được xử lý cả trong đường thành công lẫn đường lỗi khởi tạo/khởi động. Nếu plugin tạo ba đăng ký nhưng bước thứ tư thất bại, cần đóng lại cả ba token đã tạo. Không dựa vào garbage collector để quyết định lúc nào hủy đăng ký.

```text
Runtime / Publisher       Registry                  Plugin
        |                    |                        |
        |                    |<-- subscribe(handler) --|
        |                    |--- Subscription ------->|
        |--- publish(event) ->|                        |
        |                    |--- handler(event) ----->|
        |                    |<--- return / failure ---|
        |                    |<------ close() ---------|
        |--- publish(next) -->|   không gọi đăng ký đã đóng
```

## 4. Ví dụ Java 17+ chạy độc lập

Lưu mã sau vào tệp **`EventBusDemo.java`**. Ví dụ chọn `CopyOnWriteArrayList` vì giả định số lần phát nhiều hơn rất nhiều so với số lần đăng ký/hủy. Từng lần đăng ký được bọc trong một `Slot` riêng để không nhầm khi đăng ký cùng một handler nhiều lần.

```java
import java.util.Objects;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.function.Consumer;

public final class EventBusDemo {
    record FileChanged(String path, long revision) {
        FileChanged {
            Objects.requireNonNull(path, "path");
        }
    }

    @FunctionalInterface
    interface Subscription extends AutoCloseable {
        @Override
        void close();
    }

    static final class EventBus<E> {
        private static final class Slot<E> {
            final Consumer<? super E> handler;
            final AtomicBoolean active = new AtomicBoolean(true);

            Slot(Consumer<? super E> handler) {
                this.handler = handler;
            }
        }

        private final CopyOnWriteArrayList<Slot<E>> slots =
                new CopyOnWriteArrayList<>();
        private final Consumer<? super RuntimeException> onError;

        EventBus(Consumer<? super RuntimeException> onError) {
            this.onError = Objects.requireNonNull(onError, "onError");
        }

        Subscription subscribe(Consumer<? super E> handler) {
            Objects.requireNonNull(handler, "handler");
            Slot<E> slot = new Slot<>(handler);
            slots.add(slot);

            return () -> {
                if (slot.active.compareAndSet(true, false)) {
                    slots.remove(slot);
                }
            };
        }

        void publish(E event) {
            Objects.requireNonNull(event, "event");
            for (Slot<E> slot : slots) {
                if (!slot.active.get()) {
                    continue;
                }
                try {
                    slot.handler.accept(event);
                } catch (RuntimeException failure) {
                    onError.accept(failure);
                }
            }
        }
    }

    public static void main(String[] args) {
        EventBus<FileChanged> events =
                new EventBus<>(e -> System.out.println("ERROR " + e.getMessage()));

        Subscription audit = events.subscribe(e ->
                System.out.println("AUDIT " + e.path() + "#" + e.revision()));

        Subscription plugin = events.subscribe(e -> {
            if (e.revision() == 2) {
                throw new IllegalStateException("plugin unavailable");
            }
            System.out.println("PLUGIN " + e.revision());
        });

        Subscription metric = events.subscribe(e ->
                System.out.println("METRIC " + e.revision()));

        events.publish(new FileChanged("config.yml", 1));

        audit.close();
        audit.close(); // đóng nhiều lần vẫn an toàn
        events.publish(new FileChanged("config.yml", 2));

        plugin.close();
        metric.close();
        events.publish(new FileChanged("config.yml", 3));
    }
}
```

Biên dịch và chạy (Java 17 hoặc mới hơn):

```bash
javac EventBusDemo.java
java EventBusDemo
```

Stdout chính xác với chương trình trên:

```text
AUDIT config.yml#1
PLUGIN 1
METRIC 1
ERROR plugin unavailable
METRIC 2
```

Giải thích kết quả:

- Ở revision 1, cả ba listener còn hoạt động và chạy theo thứ tự đăng ký.
- `audit.close()` đặt `active=false` và loại slot của `audit` khỏi registry; gọi lặp lại là thao tác rỗng. Vì vậy revision 2 không có dòng `AUDIT`.
- Callback của `plugin` ném `IllegalStateException` ở revision 2. `publish` bắt lỗi này, gọi `onError` in dòng `ERROR` và vẫn tiếp tục `metric`.
- Sau khi đóng hai token còn lại, revision 3 không tạo output. Điều đó chỉ chứng minh hành vi của lượt gọi tuần tự trong `main`, **không chứng minh không có callback đang chạy song song trong ứng dụng đa luồng**.

### Tại sao cách cài đặt này hoạt động?

`CopyOnWriteArrayList` tạo snapshot cho iterator, nên thêm/xóa listener không phá vòng lặp đang duyệt. `AtomicBoolean.compareAndSet(true, false)` giúp nhiều lần đóng token (kể cả từ nhiều thread) chỉ thực hiện logic tháo một lần. Mỗi slot là một đối tượng riêng, nên hai lần `subscribe` cùng lambda vẫn cho hai token có thể đóng riêng. `Objects.requireNonNull` làm lỗi đầu vào lộ rõ tại biên API.

Ví dụ chọn xử lý lỗi ở mức từng listener. Đây là **chính sách thiết kế**, không phải điều Java tự thực hiện. Nếu `onError` ném ngoại lệ thì lượt `publish` cũng bị ngắt; nếu handler ném `Error` thì ví dụ không bắt và lỗi lan ra. Runtime thực tế cần quyết định người chịu trách nhiệm cho lỗi, mức logging, metric, cảnh báo, và có muốn báo trạng thái thất bại cho publisher hay không.

## 5. Quy tắc hủy đăng ký: điều gì được bảo đảm?

### Hủy trước lần phát tiếp theo

Nếu chương trình tuần tự: `close()` hoàn thành, rồi mới `publish(event)`, slot đã đóng sẽ không được gọi. Đây là tình huống dễ hiểu nhất và tương thích với ví dụ.

### Hủy ngay trong callback

Với snapshot của `CopyOnWriteArrayList`, listener A có thể đóng đăng ký của chính nó hoặc của B trong lúc xử lý một sự kiện. Lượt phát không ném `ConcurrentModificationException`. Khi vòng lặp đến B, phép kiểm tra `active` sẽ bỏ qua B nếu việc hủy đã hoàn tất trước phép kiểm tra. Listener đăng ký mới ngay trong callback không xuất hiện trong snapshot đang duyệt.

### Hủy đồng thời với lượt phát

Trong hai thread, thứ tự có thể là: publisher đọc `active=true`, thread khác gọi `close()`, rồi publisher bắt đầu `handler.accept(event)`. Vì vậy **`close()` không cam kết “sau khi trả về sẽ không có callback nào bắt đầu/chạy”** trong cài đặt này. Nó bảo đảm token bị vô hiệu hóa và loại khỏi registry, không phải *drain* toàn bộ tác vụ đang chạy.

Nếu hợp đồng yêu cầu “không còn callback nào đang chạy khi unload xong”, phải thiết kế thêm cơ chế phối hợp (đếm callback in-flight, chặn callback mới, chờ các callback cũ hoàn tất hoặc khóa thích hợp). Cần xử lý cẩn thận tình huống callback tự gọi `close()` để tránh tự đợi chính mình rồi deadlock. Phương án đơn giản là tách hai thao tác `unsubscribe()` và `awaitQuiescence()`, nêu rõ ai được gọi thao tác chờ.

### Hủy trong hệ thống bất đồng bộ

Với executor/queue, tách rõ:

- **Hủy subscription**: không nhận các lần lập lịch/phát mới theo quy tắc đã chọn.
- **Hủy công việc đang nằm trong queue**: cần cơ chế đánh dấu, loại khỏi queue hoặc kiểm tra token trước thực thi.
- **Hủy công việc đang chạy**: cần cờ phối hợp hoặc interruption; không có bảo đảm callback dừng ngay.
- **Bảo đảm delivery**: at-most-once/at-least-once, retry, thứ tự và xử lý lặp là các hợp đồng độc lập. Một event bus đồng bộ trong bộ nhớ không có retry hay lưu bền.

Tránh viết tài liệu API chung chung rằng “unsubscribe bảo đảm callback không được gọi nữa” nếu implementation chỉ chặn các lượt đăng ký/phát trong tương lai.

## 6. Hợp đồng thread, thứ tự và hiệu năng

**Đồng bộ:** Mọi callback chạy trên thread đã gọi `publish`; không thêm thread ngầm. Đơn giản để debug và giữ thứ tự *trong một lượt phát*, nhưng callback ngủ/chặn I/O sẽ kéo dài thời gian phát. Gắn SLA cho callback hoặc chuyển công việc nặng qua một kênh xử lý khác khi cần.

**Đồng thời:** Hai thread có thể gọi `publish` một lúc và cùng gọi một handler song song. Cấu trúc registry thread-safe không làm logic handler tự động thread-safe. Listener sử dụng biến trạng thái chung phải dùng đồng bộ hóa, kiểu bất biến hoặc dữ liệu concurrent phù hợp. Nếu cần một thứ tự toàn cục, phải có bộ tuần tự hóa riêng và định nghĩa hàng đợi.

**Tái nhập (reentrancy):** Handler có thể gọi lại `publish`, tạo lượt phát lồng nhau trên call stack. Nếu không có giới hạn, chuỗi sự kiện tự kích hoạt có thể lặp vô hạn hoặc tràn stack. Có thể quy định cấm tái nhập, dùng queue có điều tiết hoặc phát hiện chu trình theo nhu cầu.

**Chi phí của `CopyOnWriteArrayList`:** Duyệt không khóa và an toàn với thay đổi đồng thời; nhưng thêm/xóa phải copy mảng, tốn CPU và allocation khi danh sách lớn hoặc plugin churn cao. Chỉ dùng khi mẫu tải thật sự “đọc nhiều, ghi ít”. Với thay đổi liên tục, cân nhắc map concurrent + snapshot có kiểm soát, registry phân vùng theo loại sự kiện, hoặc cấu trúc khác. Không lựa chọn chỉ vì tên có “Concurrent”.

**Backpressure:** Event bus đồng bộ chuyển thời gian chờ sang publisher. Nếu chuyển sang async, producer có thể tạo sự kiện nhanh hơn consumer: cần giới hạn queue, chính sách block/drop/coalesce/reject và ghi metric. `ExecutorService.execute` đơn thuần không tự tạo giới hạn dung lượng hay bảo đảm thứ tự trên pool nhiều thread. Java `Flow.Publisher`/`Subscriber` có mô hình request/demand nếu cần hợp đồng backpressure chính thức, nhưng vẫn phải chọn implementation phù hợp.

| Nhu cầu | Hướng thiết kế |
|---|---|
| Callback nhỏ, ít thay đổi registration | Registry + gọi đồng bộ + token `close()` |
| Callback cần trả kết quả điều khiển luồng | Interface callback chuyên biệt, chính sách lỗi và kết quả |
| Handler chạy lâu, có burst | Queue bounded, executor, quan sát độ trễ và drop |
| Cần thứ tự toàn cục hoặc replay | Sequencer/event log/broker có contract delivery rõ |
| Plugin hot reload | Token do plugin sở hữu, unregister có kỷ luật, phối hợp quiescence nếu cần |

## 7. Payload và tính ổn định của hợp đồng mở rộng

Dùng kiểu sự kiện rõ nghĩa, tốt nhất là dữ liệu snapshot bất biến. Ví dụ `record FileChanged(String path, long revision)` ngăn đổi các field của record sau khi tạo; nhưng nếu một field trỏ đến collection mutable, record **không tự deep-copy collection**. Khi công bố API công khai cho plugin:

- Nói rõ ý nghĩa từng trường, `null` có hợp lệ không, có thứ tự phiên bản (revision) hay không, và thời điểm dữ liệu được lấy snapshot.
- Không truyền ra đối tượng nội bộ mutable của runtime rồi để plugin tự sửa. Nếu payload có danh sách/map, tạo bản sao phòng vệ, ví dụ `List.copyOf(items)`/`Map.copyOf(values)` khi phù hợp.
- Giữ tương thích nguồn/binary cho plugin, hoặc version hóa API khi thay đổi kiểu/chữ ký callback. Thêm method abstract vào interface plugin công khai có thể phá implementer cũ; cân nhắc default method, adapter hoặc phiên bản hợp đồng mới theo nhu cầu.
- Không để listener chạy với giả định ngầm rằng thread-local context, transaction hoặc security context sẽ tồn tại khi đổi từ sync sang async. Đây là thay đổi hành vi đáng kể.
- Đặt giới hạn về quyền truy cập tài nguyên, thời gian xử lý và hành vi lỗi nếu plugin do bên thứ ba cung cấp. Catch exception chỉ giúp cô lập lỗi thông thường; không tự tạo isolation về bảo mật, CPU hay memory trong cùng JVM.

## 8. Quản lý ownership: plugin phải dọn đăng ký mình đã tạo

Cách dùng token để gắn vòng đời listener với vòng đời extension (đoạn sau dùng các nested type trong `EventBusDemo` ở mục 4 và có thể đặt thêm trong cùng package):

```java
final class PluginAdapter implements AutoCloseable {
    private final EventBusDemo.Subscription subscription;

    PluginAdapter(EventBusDemo.EventBus<EventBusDemo.FileChanged> bus) {
        this.subscription = bus.subscribe(this::onChanged);
    }

    private void onChanged(EventBusDemo.FileChanged event) {
        System.out.println("PLUGIN ADAPTER " + event.path());
    }

    @Override
    public void close() {
        subscription.close();
    }
}
```

Ý chính nằm ở trường `subscription` và `close()` của plugin. Nếu bỏ `close()`, registry vẫn giữ tham chiếu qua `this::onChanged` đến instance plugin. Với class loader động, các đối tượng còn bị giữ sống có thể kéo theo class loader và mã plugin cũ. Đối với nhiều đăng ký, có thể giữ một danh sách token, đóng theo thứ tự ngược lúc shutdown, và xử lý lỗi cleanup để không bỏ sót những token còn lại.

`try-with-resources` cũng phù hợp cho đăng ký có scope ngắn: tạo `Subscription` trong khối `try (...)`; ra khỏi scope thì gọi `close()` tự động. Với plugin chạy lâu, token thường nằm trong field của đối tượng lifecycle thay vì trong một block ngắn.

Không dùng `finalize()` hoặc chỉ dựa vào `WeakReference` để thay thế cleanup. Weak listener có thể biến mất không xác định thời điểm, làm việc mất subscription khó dự đoán; explicit ownership là hợp đồng dễ kiểm soát và kiểm thử hơn.

## 9. Checklist kiểm thử hợp đồng

| Ca kiểm thử | Điều cần khẳng định |
|---|---|
| Đăng ký 2–3 handler | Mỗi lần phát gọi đúng handler đang active; kiểm tra thứ tự trong một lượt tuần tự |
| Gọi `close()` hai lần | Không lỗi, không nhận sự kiện sau khi đóng trong trường hợp tuần tự |
| Đăng ký cùng handler hai lần | Hai lượt subscription độc lập; đóng một token không đóng token kia |
| Handler A hủy B trong callback | Không làm hỏng vòng lặp; kiểm tra B theo quy tắc active và snapshot |
| Handler đăng ký C trong callback | C chỉ có thể nhận từ lượt phát sau khi snapshot hiện tại kết thúc |
| Handler ném `RuntimeException` | Error handler được gọi, handler sau vẫn chạy; kiểm thử cả trường hợp error handler bị lỗi |
| Nhiều publisher/closer đồng thời | Không hỏng registry; xác nhận kỳ vọng chính xác về race, không hứa cứng “zero in-flight” |
| Plugin unload/reload | Mọi token của phiên cũ được đóng; không còn listener cũ trong registry |
| Handler chậm/tự phát sự kiện | Quan sát latency, recursion và chính sách queue/time budget |
| Payload có object mutable | Không có chia sẻ dữ liệu có thể bị sửa ngoài hợp đồng |

Với test đa luồng, dùng `CountDownLatch`/`Phaser` để sắp xếp điểm cạnh tranh thay vì `Thread.sleep` đoán thời gian. Test phải kiểm tra cam kết thực tế của API; không assert một thứ tự ngẫu nhiên do scheduler quyết định. Với yêu cầu quiescence chặt, xây test chứng minh `close-and-drain` chờ callback đã bắt đầu hoàn tất.

## 10. Lỗi thiết kế phổ biến và cách tránh

1. **Chỉ có `void addListener(...)`:** Không trả token, không biết chính xác ai chịu trách nhiệm cleanup. Trả `Subscription`/`AutoCloseable` để thể hiện ownership.
2. **Hủy bằng `listeners.remove(handler)` khi đăng ký trùng:** Có thể xóa sai lần hoặc phụ thuộc `equals`. Tạo slot/token riêng cho mỗi registration.
3. **Duyệt `ArrayList` rồi sửa danh sách trong callback:** Có nguy cơ `ConcurrentModificationException` hoặc hành vi khó đoán. Chọn snapshot, đồng bộ hóa hoặc cấu trúc concurrent theo contract.
4. **Catch exception rồi bỏ qua:** Sự kiện có vẻ thành công trong khi plugin hỏng. Xác định error channel, log có ngữ cảnh, metric và chính sách propagate hay isolate.
5. **Tuyên bố “close ngăn mọi callback” nhưng không chờ in-flight:** Tạo race khi unload tài nguyên. Ghi rõ close chỉ unregister, thêm quiescence khi thật sự cần.
6. **Gọi code plugin dưới lock của registry:** Callback có thể đăng ký/hủy/tái nhập hoặc đợi lock khác và gây deadlock. Tránh giữ khóa cấu trúc trong thời gian gọi code bên ngoài; nếu cần lock, thiết kế thứ tự khóa rõ ràng.
7. **Đẩy mọi sự kiện lên thread pool vô hạn:** Mất kiểm soát queue, thứ tự, shutdown và memory. Chọn giới hạn và chính sách backpressure từ đầu.
8. **Để plugin dùng đối tượng mutable hoặc API nội bộ:** Dễ phá encapsulation và gây tương thích kém. Cấp payload bất biến, interface công khai ổn định.
9. **Quên hủy đăng ký lúc reload:** Registry giữ lambda và class loader cũ, có thể xử lý trùng. Ràng buộc unregister vào plugin lifecycle và kiểm thử unload.
10. **Đồng nhất event với lệnh bắt buộc thành công:** Event thông báo thường không trả lời; hành vi cần kết quả/rollback nên được diễn đạt bằng hợp đồng điều khiển luồng riêng.

## 11. Các tiêu chí chốt cho một extension point

Một hợp đồng tốt có thể trả lời cụ thể: sự kiện được phát từ đâu; callback chạy trên thread nào; ai sở hữu token; trình tự và ngoại lệ được xử lý ra sao; `close()` có chờ in-flight không; có replay/retry/backpressure không; dữ liệu có bất biến và versioned không; khi plugin unload thì dọn những gì. Đưa các điều khoản này vào JavaDoc của API và bài test contract. Chọn implementation sao cho **từng cam kết đều có thể kiểm chứng**, nhất là khi có thay đổi động của plugin và nhiều thread trong cùng runtime.
