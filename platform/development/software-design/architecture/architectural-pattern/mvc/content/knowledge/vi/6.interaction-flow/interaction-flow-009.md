# Tránh vòng lặp cập nhật giữa Model và View

Trong mô hình **Model–View–Controller (MVC)**, Model quản lý trạng thái và quy tắc của ứng dụng, View trình bày trạng thái đó, còn Controller tiếp nhận tương tác và điều phối thay đổi. Khi người dùng sửa dữ liệu, View gửi ý định thao tác đến Controller; Controller gọi chức năng phù hợp để cập nhật Model; sau khi trạng thái thay đổi, View nhận dữ liệu mới và hiển thị lại.

Chu trình này là cần thiết. Vấn đề xuất hiện khi một lần cập nhật lại kích hoạt chính đường xử lý đã tạo ra nó. Ví dụ, Model thông báo thay đổi, View cập nhật trường nhập, sự kiện thay đổi của trường lại được xem như thao tác mới của người dùng, Controller ghi ngược giá trị vào Model, rồi Model tiếp tục thông báo. Một thay đổi có thể tạo ra nhiều lần cập nhật lặp, gây tốn tài nguyên, nhấp nháy giao diện, ghi dữ liệu thừa hoặc thậm chí lặp vô hạn.

Bài học này giải thích cách nhận diện vòng lặp cập nhật giữa Model và View, phân biệt sự kiện do người dùng tạo với cập nhật do chương trình thực hiện, và thiết kế luồng một chiều qua Controller để trạng thái luôn nhất quán.

## 1. Chu trình cập nhật bình thường trong MVC

Một tương tác hợp lệ thường có hai chiều truyền thông tin nhưng một chiều quyết định thay đổi:

1. **Model → View:** View nhận trạng thái hiện tại và trình bày nó.
2. **View → Controller:** View phát sự kiện khi người dùng thực hiện thao tác.
3. **Controller → Model:** Controller chuyển thao tác thành lệnh hoặc yêu cầu cập nhật.
4. **Model → View:** Sau khi trạng thái thay đổi, View được thông báo hoặc lấy snapshot mới để hiển thị.

Ví dụ, người dùng sửa tên hồ sơ:

- View hiển thị tên hiện tại là “An”.
- Người dùng nhập “An Nguyễn” và gửi thay đổi.
- Controller tiếp nhận nội dung, kiểm tra dữ liệu đầu vào và gọi use case cập nhật hồ sơ.
- Model lưu tên mới nếu hợp lệ.
- View nhận trạng thái mới và hiển thị “An Nguyễn”.

Luồng này có thể được minh họa như sau:

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant V as View
    participant C as Controller
    participant M as Model

    M-->>V: Trạng thái hiện tại
    V-->>User: Hiển thị dữ liệu
    User->>V: Sửa tên và gửi thao tác
    V->>C: UserEdit(name)
    C->>M: updateName(name)
    M->>M: Kiểm tra và cập nhật trạng thái
    M-->>V: Thông báo trạng thái mới
    V-->>User: Hiển thị tên mới
~~~

Sự kiện từ Model quay lại View là bình thường. Điều cần tránh là View coi thao tác render dữ liệu như một tương tác mới của người dùng rồi phát lại cùng lệnh cập nhật.

## 2. Vòng lặp cập nhật giữa Model và View là gì?

Vòng lặp cập nhật (update loop hoặc feedback loop) xảy ra khi một thay đổi ở thành phần này kích hoạt thay đổi ở thành phần kia, rồi thay đổi đó lại kích hoạt ngược trở lại mà không có điều kiện dừng rõ ràng.

Một chuỗi điển hình:

1. Model thay đổi thuộc tính `name`.
2. Model phát thông báo cho View.
3. View gọi `setText(name)` để cập nhật trường nhập.
4. Listener của trường nhập phát sự kiện thay đổi.
5. View chuyển sự kiện đó cho Controller như thể người dùng vừa nhập.
6. Controller gọi lại `model.setName(name)`.
7. Model phát thông báo lần nữa.
8. Chu trình lặp lại.

~~~mermaid
flowchart TD
    M[Model thay đổi] --> N[Model thông báo]
    N --> V[View render dữ liệu]
    V --> E[Listener của View phát sự kiện]
    E --> C[Controller nhận như thao tác người dùng]
    C --> U[Controller cập nhật Model]
    U --> M
    style E stroke:#c55,stroke-width:2px
~~~

Không phải mọi vòng phản hồi đều vô hạn. Một số framework tự phát sự kiện khi code gọi setter; một số cơ chế binding có thể tự nhận diện thay đổi và ngừng khi giá trị không đổi. Tuy vậy, nếu không hiểu rõ hành vi của framework, ứng dụng có thể gặp cập nhật thừa hoặc vòng lặp khó phát hiện.

## 3. Những nguyên nhân thường gặp

### 3.1. Cập nhật giao diện bị xem như thao tác của người dùng

Đây là nguyên nhân phổ biến nhất. Nhiều UI toolkit phát thông báo property changed hoặc document changed ngay cả khi giá trị được thay đổi bằng code.

Ví dụ:

~~~java
// Minh họa cách nối listener dễ tạo vòng lặp.
model.addNameListener(view::setName);
view.addNameListener(model::setName);
~~~

Hai listener nối trực tiếp với nhau. Nếu `view.setName()` phát sự kiện giống thao tác nhập của người dùng, Model lại nhận một lệnh cập nhật mới.

### 3.2. Model phát thông báo dù giá trị không thay đổi

Một setter đơn giản có thể luôn phát sự kiện:

~~~java
public void setName(String name) {
    this.name = name;
    notifyNameChanged(name);
}
~~~

Nếu View render lại đúng giá trị cũ và listener gửi nó về Model, Model tiếp tục phát thông báo. Dù không có thay đổi dữ liệu thực sự, toàn bộ chu trình vẫn chạy nhiều lần.

### 3.3. Có nhiều nơi cùng giữ bản sao trạng thái

Ứng dụng có thể giữ tên hồ sơ trong Model, Controller, View model, component state và một biến JavaScript riêng. Khi mỗi bản sao có quyền ghi, chúng có thể cập nhật qua lại và ghi đè giá trị của nhau.

Ví dụ, Model chuẩn hóa tên thành “An Nguyễn”, View giữ bản nháp “  An Nguyễn  ”, rồi một listener khác lại gửi bản nháp chưa chuẩn hóa về Model. Các bản sao liên tục cố đồng bộ nhưng không thống nhất quy tắc chuyển đổi.

### 3.4. Biến đổi hai chiều không đối xứng

Một giá trị được định dạng khi hiển thị và phân tích ngược khi nhập có thể không còn giống ban đầu. Ví dụ:

- Model lưu số `1234.50`.
- View hiển thị `1.234,50` theo locale Việt Nam.
- Listener phân tích chuỗi theo locale khác, tạo ra `1.2345` hoặc lỗi.
- Model phát thông báo với giá trị đã thay đổi.
- View định dạng lại và tiếp tục phát sự kiện.

Định dạng và phân tích dữ liệu cần có quy tắc rõ, không nên tự động coi mọi thay đổi hiển thị là dữ liệu đầu vào mới.

### 3.5. Listener được đăng ký nhiều lần hoặc không được gỡ bỏ

Khi một màn hình được mở lại, Controller hoặc View có thể đăng ký thêm listener mà không hủy listener cũ. Một thay đổi Model khi đó kích hoạt nhiều callback, mỗi callback lại cập nhật View hoặc Model. Đây có thể không phải vòng lặp vô hạn, nhưng tạo cảm giác cập nhật lặp và làm số lần xử lý tăng dần.

### 3.6. Cập nhật bất đồng bộ đến sai thứ tự

Một request lưu dữ liệu có thể hoàn tất sau một request mới hơn. Nếu phản hồi cũ ghi đè trạng thái mới trên View, người dùng thấy dữ liệu quay ngược. Nếu View tự gửi thay đổi bù lại, ứng dụng có thể tạo thêm các cập nhật không cần thiết.

Với thao tác bất đồng bộ, cần kiểm soát phiên bản, thứ tự hoặc danh tính request để chỉ áp dụng kết quả còn phù hợp.

## 4. Phân biệt sự kiện người dùng và cập nhật do chương trình

Đây là nguyên tắc quan trọng nhất để tránh vòng lặp.

| Loại thay đổi | Ví dụ | Cách xử lý |
|---|---|---|
| Sự kiện do người dùng | Người dùng gõ vào ô tên, chọn ngày, nhấn nút lưu | View phát sự kiện hoặc command đến Controller |
| Cập nhật do render | Controller hoặc Model yêu cầu View hiển thị tên mới | View cập nhật giao diện, không phát lại command người dùng |
| Cập nhật nội bộ của Model | Model chuẩn hóa dữ liệu, tính trạng thái dẫn xuất | Model phát thông báo thay đổi sau khi trạng thái thực sự đổi |
| Phản hồi bất đồng bộ | Server trả về kết quả lưu hồ sơ | Controller kiểm tra phản hồi còn phù hợp rồi cập nhật Model/View |

Không nên dùng một callback chung cho mọi thay đổi nếu ứng dụng cần phân biệt nguồn gốc sự kiện. Tên và hợp đồng callback nên thể hiện ý nghĩa, ví dụ `onUserEditedName` thay vì `onNameChanged` nếu callback chỉ dành cho thao tác người dùng.

## 5. Thiết kế luồng một chiều qua Controller

Một cách tổ chức dễ hiểu là để Controller kết nối View với Model:

- View gửi sự kiện có ý nghĩa về thao tác người dùng.
- Controller nhận sự kiện và gọi lệnh nghiệp vụ.
- Model thay đổi trạng thái và phát thông báo hoặc trả snapshot mới.
- View chỉ render snapshot.

~~~mermaid
flowchart LR
    U[Người dùng] -->|Thao tác| V[View]
    V -->|User event / command| C[Controller]
    C -->|Gọi use case| M[Model]
    M -->|State change / snapshot| C
    C -->|Render data| V
~~~

Trong một số biến thể MVC, Model phát thông báo trực tiếp cho các View đang quan sát. Cách đó vẫn có thể hợp lệ nếu View chỉ cập nhật cách trình bày và không phát lại sự kiện người dùng. Với ứng dụng cần kiểm soát chặt luồng, Controller có thể làm trung gian nhận thông báo rồi yêu cầu View render.

Điều quan trọng là Model không cần biết View cụ thể, còn View không được tự ý thay đổi Model khi chỉ đang hiển thị dữ liệu.

## 6. Ví dụ Java: ngăn cập nhật do render phát ngược về Model

Giả sử một màn hình chỉnh sửa tên hồ sơ sử dụng một ô nhập. Ví dụ dưới đây là mã minh họa theo phong cách Java UI; API listener cụ thể tùy framework.

### 6.1. Model chỉ thông báo khi trạng thái thực sự đổi

~~~java
public record ProfileSnapshot(String displayName) {}

public class ProfileModel {
    private String displayName;
    private final List<Consumer<ProfileSnapshot>> listeners =
            new ArrayList<>();

    public ProfileModel(String displayName) {
        this.displayName = displayName;
    }

    public ProfileSnapshot snapshot() {
        return new ProfileSnapshot(displayName);
    }

    public void rename(String requestedName) {
        String normalized = requestedName == null
                ? ""
                : requestedName.trim();

        if (Objects.equals(displayName, normalized)) {
            return;
        }

        displayName = normalized;
        ProfileSnapshot current = snapshot();

        for (Consumer<ProfileSnapshot> listener :
                List.copyOf(listeners)) {
            listener.accept(current);
        }
    }

    public Subscription addListener(Consumer<ProfileSnapshot> listener) {
        listeners.add(listener);
        return () -> listeners.remove(listener);
    }
}
~~~

Model chuẩn hóa tên và so sánh với trạng thái hiện tại trước khi phát thông báo. Nếu giá trị không đổi, không có lý do để phát một sự kiện cập nhật mới.

Trong ứng dụng thực tế, cần quản lý việc đăng ký và hủy listener theo vòng đời màn hình. Nếu Model được truy cập từ nhiều thread, danh sách listener và cách phát thông báo cũng cần cơ chế đồng bộ phù hợp.

### 6.2. View tách render khỏi sự kiện nhập của người dùng

~~~java
public class ProfileView {
    private boolean rendering;
    private Consumer<String> userEditHandler = value -> {};

    public void onUserEdit(Consumer<String> handler) {
        this.userEditHandler = handler;
    }

    // Được gọi khi Model/Controller yêu cầu hiển thị snapshot.
    public void render(ProfileSnapshot state) {
        rendering = true;
        try {
            nameField.setText(state.displayName());
        } finally {
            rendering = false;
        }
    }

    // Được nối với listener của trường nhập.
    private void handleTextChanged(String value) {
        if (rendering) {
            return;
        }

        userEditHandler.accept(value);
    }
}
~~~

Khi View cập nhật trường nhập do render, cờ `rendering` ngăn listener phát lại một sự kiện người dùng. Cờ phải được đặt lại trong `finally` để không bị giữ ở trạng thái sai nếu thao tác cập nhật giao diện phát sinh lỗi.

Đây là kỹ thuật bảo vệ tại View, không phải cách thay thế cho thiết kế luồng một chiều. Một số framework cung cấp API cập nhật giá trị mà không phát sự kiện người dùng, hoặc phân biệt rõ event do code và event do người dùng; nên ưu tiên cơ chế chính thức của framework khi có.

### 6.3. Controller nối các thành phần

~~~java
public class ProfileController {
    private final ProfileModel model;
    private final ProfileView view;
    private Subscription modelSubscription;

    public ProfileController(ProfileModel model, ProfileView view) {
        this.model = model;
        this.view = view;
    }

    public void start() {
        if (modelSubscription != null) {
            return;
        }

        view.onUserEdit(this::handleUserEdit);
        modelSubscription = model.addListener(view::render);
        view.render(model.snapshot());
    }

    private void handleUserEdit(String value) {
        model.rename(value);
    }

    public void stop() {
        if (modelSubscription != null) {
            modelSubscription.close();
            modelSubscription = null;
        }
        view.onUserEdit(value -> {});
    }
}
~~~

Controller là nơi kết nối sự kiện người dùng với lệnh cập nhật Model. Model thông báo snapshot mới; View render snapshot và không gửi ngược một sự kiện nhập giả. Phương thức `stop()` hủy subscription khi màn hình đóng; `start()` tránh đăng ký lặp nếu được gọi nhiều lần.

## 7. Không phát thông báo khi trạng thái không đổi

Kiểm tra thay đổi thực sự là một lớp bảo vệ hữu ích. Nếu Model phát sự kiện sau mọi lần gọi setter, các cập nhật lặp sẽ lan rộng.

Ví dụ:

~~~java
public void setQuantity(int newQuantity) {
    if (this.quantity == newQuantity) {
        return;
    }

    this.quantity = newQuantity;
    notifyQuantityChanged(newQuantity);
}
~~~

Với kiểu dữ liệu phức tạp, so sánh cần dựa trên ý nghĩa nghiệp vụ. Ví dụ, hai giá trị tiền có thể có cùng giá trị số nhưng scale khác nhau; nếu chính sách coi chúng tương đương, nên dùng phép so sánh phù hợp thay vì dựa vào cách biểu diễn thô. Không nên phát thông báo chỉ vì một object mới được tạo nếu nội dung của nó không đổi.

Kiểm tra bằng nhau không giải quyết được mọi vòng lặp. Nếu mỗi lần render tạo ra giá trị khác nhau do thời gian, định dạng, số ngẫu nhiên hoặc chuẩn hóa không ổn định, chu trình vẫn có thể tiếp diễn. Cần bảo đảm hàm chuyển đổi có kết quả ổn định và có chủ sở hữu rõ.

## 8. Cẩn trọng với binding hai chiều

Một số framework cung cấp cơ chế two-way binding để tự đồng bộ thuộc tính Model và View. Cơ chế này tiện lợi cho biểu mẫu đơn giản, nhưng cần hiểu rõ khi nào binding ghi dữ liệu và khi nào nó phát sự kiện.

Ví dụ khái quát:

~~~text
Model.name  <---- two-way binding ---->  TextField.text
~~~

Nếu cả hai phía cùng áp dụng formatter, validator hoặc setter có tác dụng phụ, thay đổi ở một phía có thể kích hoạt thay đổi ngược ở phía kia.

Hãy áp dụng các nguyên tắc sau:

- Chỉ dùng binding hai chiều cho giá trị đơn giản có quy tắc chuyển đổi rõ ràng.
- Tách giá trị đang nhập (draft) khỏi giá trị nghiệp vụ đã được xác nhận nếu dữ liệu cần validation hoặc lưu có điều kiện.
- Dùng converter/parser có xử lý lỗi và locale nhất quán.
- Kiểm tra giá trị trước khi ghi ngược để tránh cập nhật không đổi.
- Tránh đặt tác dụng phụ như lưu cơ sở dữ liệu hoặc phát lệnh nghiệp vụ trong setter được binding gọi tự động.
- Khi framework hỗ trợ, phân biệt cập nhật từ code với thao tác người dùng hoặc dùng cơ chế suspend/unbind trong lúc render.

Với nghiệp vụ phức tạp, luồng một chiều qua Controller thường dễ theo dõi hơn việc để binding tự động quyết định lúc nào Model được thay đổi.

## 9. Phân biệt trạng thái bản nháp và trạng thái đã lưu

Không phải mọi ký tự người dùng gõ đều cần ghi ngay vào Model nghiệp vụ. Một biểu mẫu có thể có trạng thái bản nháp riêng:

- **Draft state:** nội dung người dùng đang chỉnh sửa, có thể chưa hợp lệ hoặc chưa hoàn tất.
- **Committed state:** trạng thái đã được kiểm tra và chấp nhận bởi use case.

Ví dụ, khi người dùng nhập số lượng, View có thể giữ chuỗi `"12x"` trong lúc nhập. Chuỗi đó chưa phải số lượng hợp lệ để ghi vào Model. Khi người dùng gửi biểu mẫu, Controller chuyển chuỗi thành kiểu số, kiểm tra định dạng rồi gọi use case. Model kiểm tra tiếp quy tắc nghiệp vụ như số lượng có sẵn.

Việc tách draft và committed state tránh cho Model liên tục nhận các giá trị tạm thời, không hợp lệ, đồng thời giảm nguy cơ binding hai chiều tạo vòng lặp.

~~~mermaid
flowchart TD
    U[Người dùng nhập] --> D[Draft state trong View]
    D -->|Submit| C[Controller]
    C --> V[Kiểm tra định dạng]
    V -->|Không hợp lệ| E[Trả lỗi cho View]
    V -->|Hợp lệ| M[Model / Use case]
    M --> R[Kiểm tra quy tắc và cập nhật]
    R --> S[Committed state]
    S --> W[View render snapshot]
~~~

## 10. Cập nhật bất đồng bộ và thứ tự phản hồi

Trong ứng dụng web, người dùng có thể sửa dữ liệu nhiều lần trước khi request trước hoàn tất. Ví dụ:

1. Người dùng đổi địa chỉ thành A và gửi request thứ nhất.
2. Người dùng đổi địa chỉ thành B và gửi request thứ hai.
3. Request thứ hai hoàn tất trước và hiển thị B.
4. Request thứ nhất hoàn tất sau và ghi đè A lên giao diện.

Đây là vấn đề thứ tự cập nhật, có thể tạo cảm giác View và Model liên tục đổi qua lại. Cách xử lý gồm:

- Gắn version hoặc request identifier cho mỗi lần gửi.
- Chỉ áp dụng phản hồi nếu nó còn tương ứng với phiên bản mới nhất.
- Dùng optimistic concurrency hoặc version field khi nhiều thao tác có thể ghi cùng một bản ghi.
- Hủy request cũ nếu thao tác và nền tảng cho phép.
- Phân biệt trạng thái đang lưu, đã lưu và lưu thất bại.

Không nên dùng debounce hoặc delay như biện pháp duy nhất để bảo vệ tính đúng đắn. Debounce có thể giảm số request khi người dùng nhập liên tục, nhưng không đảm bảo phản hồi luôn về đúng thứ tự.

## 11. Quản lý vòng đời listener và subscription

Một listener được đăng ký là một liên kết cần được quản lý. Khi View hoặc Controller không còn sử dụng, cần gỡ listener để tránh callback cũ tiếp tục chạy.

Các dấu hiệu cần kiểm tra:

- Mở một màn hình nhiều lần làm số lần callback tăng theo mỗi lần mở.
- Model vẫn giữ tham chiếu đến View đã đóng.
- Một thay đổi duy nhất làm nhiều View cũ cùng render.
- Callback cũ ghi đè dữ liệu của màn hình hiện tại.

Một subscription có thể trả về handle để hủy:

~~~java
public interface Subscription extends AutoCloseable {
    @Override
    void close();
}
~~~

Controller giữ handle và gọi `close()` khi màn hình kết thúc. Cách triển khai cụ thể phụ thuộc framework, nhưng nguyên tắc là mỗi listener phải có vòng đời rõ ràng.

## 12. Kiểm thử để phát hiện vòng lặp cập nhật

Kiểm thử không chỉ xác minh giá trị cuối cùng. Cần kiểm tra số lần cập nhật và số lần thông báo để phát hiện chu trình thừa.

Các tình huống nên kiểm tra:

1. Khi Model thay đổi một lần, View nhận một lần render phù hợp.
2. Khi View render bằng code, Controller không nhận một sự kiện nhập giả.
3. Khi người dùng sửa giá trị, Controller gửi đúng một lệnh cập nhật.
4. Khi Model nhận lại giá trị tương đương, không phát thông báo mới.
5. Khi mở và đóng màn hình nhiều lần, listener cũ không còn hoạt động.
6. Khi hai request hoàn tất sai thứ tự, phản hồi cũ không ghi đè trạng thái mới.
7. Khi validation thất bại, draft state vẫn có thể hiển thị để người dùng sửa mà không ghi dữ liệu sai vào Model.

Ví dụ kiểm tra số lần thông báo:

~~~java
AtomicInteger notifications = new AtomicInteger();
model.addListener(snapshot -> notifications.incrementAndGet());

model.rename("An Nguyễn");
assertEquals(1, notifications.get());

// Gán lại cùng giá trị không tạo thông báo mới.
model.rename("An Nguyễn");
assertEquals(1, notifications.get());
~~~

Trong test giao diện, có thể đếm số lần handler do người dùng gọi được kích hoạt trong lúc render. Kết quả mong đợi là render chương trình không phát lệnh cập nhật ngược.

## 13. Những cách xử lý dễ gây vấn đề

### Chỉ thêm một cờ boolean ở Controller

Cờ `updating` có thể ngăn callback lặp trong một số trường hợp, nhưng nếu có nhiều luồng hoặc nhiều thuộc tính cùng cập nhật, cờ dùng chung có thể chặn nhầm sự kiện hợp lệ. Nếu dùng cờ, cần giới hạn phạm vi, bảo đảm reset bằng `finally` và hiểu rõ thread thực thi.

### Dùng delay để chờ vòng lặp tự dừng

Thêm `sleep`, timer hoặc debounce không sửa được nguyên nhân về nguồn sự kiện và quyền sở hữu trạng thái. Nó có thể chỉ làm vòng lặp chậm hơn hoặc che giấu race condition.

### Ghi Model trong mọi callback thay đổi giao diện

Không phải mọi thay đổi của thuộc tính UI đều là ý định nghiệp vụ. Cập nhật do render, thay đổi focus, định dạng hoặc khôi phục giá trị có thể phát callback. Hãy phát command rõ ràng từ thao tác người dùng.

### Để View và Model gọi setter của nhau trực tiếp

Hai chiều liên kết trực tiếp làm luồng khó quan sát và khó kiểm soát. Hãy để Controller hoặc cơ chế binding có quy tắc rõ làm trung gian.

### Phát thông báo trong lúc Model còn ở trạng thái chưa hoàn chỉnh

Nếu một use case cập nhật nhiều thuộc tính, phát thông báo sau từng setter có thể khiến View render các trạng thái trung gian. Có thể gom thay đổi thành một thao tác hoặc phát snapshot sau khi cập nhật hoàn tất.

## 14. Checklist review luồng cập nhật Model–View

- [ ] Model là nguồn sự thật cho trạng thái nghiệp vụ đã được xác nhận.
- [ ] View phân biệt sự kiện người dùng với cập nhật do render.
- [ ] Controller tiếp nhận command và điều phối thay đổi Model.
- [ ] View không ghi Model chỉ vì đang hiển thị snapshot mới.
- [ ] Model chỉ phát thông báo khi trạng thái thực sự thay đổi.
- [ ] Các phép chuyển đổi hai chiều có quy tắc parse/format ổn định.
- [ ] Draft state được tách khỏi committed state khi biểu mẫu cần validation.
- [ ] Listener được đăng ký một lần và gỡ bỏ đúng vòng đời.
- [ ] Phản hồi bất đồng bộ cũ không ghi đè trạng thái mới.
- [ ] Các cập nhật liên quan có thể được gom thành một lần thông báo nhất quán.
- [ ] Kiểm thử xác minh cả giá trị cuối và số lần callback/render.

## Kết luận

Vòng lặp cập nhật giữa Model và View xuất hiện khi một thay đổi được phản hồi bằng một cập nhật ngược không cần thiết, thường do sự kiện render bị hiểu nhầm là thao tác người dùng, setter luôn phát thông báo hoặc nhiều nơi cùng giữ quyền ghi trạng thái. Hãy giữ Model làm nguồn sự thật, để View phát sự kiện người dùng đến Controller, chỉ render dữ liệu từ Model và thông báo khi trạng thái thực sự thay đổi. Khi cần binding hai chiều, hãy kiểm soát nguồn sự kiện, tách dữ liệu bản nháp khỏi dữ liệu đã xác nhận và quản lý vòng đời listener. Những ranh giới rõ ràng giúp giao diện cập nhật ổn định, tránh ghi thừa và giữ luồng tương tác MVC dễ kiểm thử.
