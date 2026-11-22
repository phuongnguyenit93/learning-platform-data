# Thông báo thay đổi bằng Observer và cơ chế đăng ký

## Mục tiêu

Trong MVC tương tác, Model có thể thay đổi sau một thao tác của người dùng hoặc sau khi ứng dụng nhận dữ liệu mới. View cần biết khi nào trạng thái thay đổi để cập nhật nội dung đang hiển thị. Nếu Model gọi trực tiếp từng View cụ thể, các thành phần sẽ phụ thuộc chặt vào nhau và khó mở rộng.

Mẫu Observer giải quyết vấn đề này bằng cơ chế đăng ký nhận thông báo. Một đối tượng phát thông báo khi có thay đổi; các đối tượng quan tâm đăng ký trước để nhận sự kiện. Model không cần biết cụ thể ai đang lắng nghe, còn View có thể bắt đầu hoặc ngừng nhận thông báo theo vòng đời của nó.

Bài học này trình bày vai trò của Observer trong MVC, cách đăng ký và hủy đăng ký, cách truyền dữ liệu thay đổi, cùng những vấn đề về vòng đời, luồng thực thi, lỗi và kiểm thử. Nội dung cũng phân biệt ứng dụng tương tác lâu dài với ứng dụng web xử lý request–response.

Sau khi học, người học có thể:

- Giải thích vai trò của publisher/subject và observer.
- Mô tả luồng Model phát thông báo và View cập nhật.
- Thiết kế API đăng ký và hủy đăng ký có vòng đời rõ ràng.
- Chọn dữ liệu sự kiện phù hợp và tránh chia sẻ trạng thái có thể bị sửa tùy ý.
- Phân biệt Observer trực tiếp với publish–subscribe qua event bus.
- Nhận diện lỗi đăng ký trùng, rò rỉ listener, cập nhật lặp và vấn đề đồng thời.
- Kiểm thử việc phát, nhận và ngừng nhận thông báo trong ứng dụng MVC.

## 1. Vấn đề: View cần biết Model đã thay đổi

Hãy xét một ứng dụng quản lý công việc. Model giữ danh sách công việc và trạng thái hoàn thành. Người dùng có thể thêm một công việc, đánh dấu hoàn tất hoặc xóa một mục.

Khi trạng thái thay đổi, giao diện cần cập nhật:

- Danh sách hiển thị thêm hoặc bớt một mục.
- Bộ đếm số việc chưa hoàn thành được tính lại.
- Thanh tiến độ phản ánh trạng thái mới.
- Một vùng tóm tắt cập nhật tổng số công việc.

Nếu Controller phải gọi từng phương thức cập nhật của mọi View sau mỗi thao tác, Controller sẽ phải biết cấu trúc giao diện. Khi thêm một View mới, chẳng hạn bảng thống kê hoặc biểu đồ, các endpoint và luồng điều khiển có thể phải sửa theo.

Một cách khác là để Model gọi trực tiếp các đối tượng giao diện cụ thể:

    model.setListView(listView);
    model.setProgressView(progressView);
    model.setSummaryView(summaryView);

Cách này cũng tạo phụ thuộc: Model phải biết từng loại View. Nếu giao diện thay đổi, Model bị ảnh hưởng dù quy tắc nghiệp vụ không đổi.

Observer tạo ra một điểm giao tiếp chung. View đăng ký quan tâm đến thay đổi của Model. Khi Model cập nhật trạng thái, nó phát thông báo đến các listener đã đăng ký. Model chỉ làm việc với một hợp đồng observer, không cần biết lớp giao diện cụ thể.

## 2. Thành phần của mẫu Observer

Mẫu Observer thường có hai vai trò chính:

**Subject / Publisher** là đối tượng sở hữu trạng thái hoặc phát ra thông báo. Nó duy trì danh sách listener, cung cấp thao tác đăng ký và hủy đăng ký, rồi thông báo khi có sự kiện phù hợp.

**Observer / Subscriber** là đối tượng quan tâm đến sự kiện. Nó đăng ký với publisher và cung cấp hàm xử lý khi nhận thông báo.

Một thông báo (event) mô tả điều đã xảy ra hoặc dữ liệu cần thiết để subscriber phản ứng. Event có thể chỉ cho biết thuộc tính nào thay đổi, mang giá trị cũ/mới, hoặc mang một snapshot bất biến của trạng thái.

    View A -------- đăng ký --------\
                                     \
    View B -------- đăng ký ---------> Model / Subject
                                     /
    View C -------- đăng ký --------/

    Người dùng
        |
        v
    Controller
        |
        | gọi hành vi
        v
    Model / Subject
        |
        | phát sự kiện
        +----------> View A
        +----------> View B
        +----------> View C

Luồng này tách hai hướng giao tiếp:

- Hướng lệnh: View chuyển thao tác của người dùng đến Controller; Controller gọi hành vi hoặc ca sử dụng.
- Hướng thông báo: Model phát sự kiện khi trạng thái thay đổi; các View đã đăng ký nhận sự kiện và render lại.

Observer không thay thế Controller. Nó giải quyết việc thông báo thay đổi, còn Controller vẫn điều phối tương tác và lệnh từ người dùng.

### Hợp đồng observer

Một hợp đồng tối thiểu có thể là:

    @FunctionalInterface
    public interface Observer<E> {
        void onEvent(E event);
    }

Publisher cung cấp thao tác đăng ký:

    public interface Subscription extends AutoCloseable {
        @Override
        void close();
    }

Subscription đại diện cho một lần đăng ký cụ thể. Khi View không còn cần nhận sự kiện, nó gọi close() để hủy đăng ký. Cách này giúp quyền sở hữu vòng đời đăng ký rõ ràng hơn việc để View tự tìm và xóa listener bằng một lời gọi không gắn với lần đăng ký ban đầu.

## 3. Luồng cập nhật trong MVC tương tác

Một luồng điển hình có thể diễn ra như sau:

1. Khi View được khởi tạo, nó đăng ký một observer với Model.
2. View đọc trạng thái ban đầu để render giao diện lần đầu.
3. Người dùng thao tác trên View, chẳng hạn nhấn nút thêm công việc.
4. View chuyển thao tác đến Controller.
5. Controller gọi hành vi phù hợp trên Model hoặc application service.
6. Model kiểm tra điều kiện, cập nhật trạng thái hợp lệ rồi phát event.
7. View nhận event và render lại phần giao diện liên quan.
8. Khi View bị đóng hoặc rời khỏi màn hình, nó hủy subscription.

Điều quan trọng là Model phát thông báo sau khi thay đổi đã hoàn tất và trạng thái có thể được quan sát một cách nhất quán. Nếu thông báo được phát giữa chừng khi một thao tác còn đang cập nhật nhiều trường, View có thể đọc được một trạng thái chưa hoàn chỉnh.

### Ví dụ: thêm công việc và cập nhật danh sách

Giả sử người dùng nhấn nút “Thêm”. View gửi tiêu đề đến Controller. Controller gọi Model để thêm mục. Model xác thực tiêu đề, cập nhật danh sách và phát sự kiện. Danh sách và bộ đếm có thể cùng nhận sự kiện đó.

    Người dùng nhấn “Thêm”
             |
             v
       TodoView
             |
             v
       TodoController
             |
             v
         TodoModel
          /     \
         /       \
        v         v
    ListView   SummaryView
        |         |
        v         v
     Render     Render

ListView và SummaryView không cần được Controller gọi riêng. Chúng tự nhận thông báo vì đã đăng ký trước đó.

## 4. Ví dụ Java: Model phát sự kiện, View đăng ký

Ví dụ sau minh họa một Model quản lý danh sách công việc. Để dễ theo dõi, mã giả định tất cả thao tác trên Model và callback diễn ra trên cùng một luồng giao diện. Phần xử lý đa luồng sẽ được bàn ở các mục sau.

### Định nghĩa dữ liệu và sự kiện

    public record TodoItem(String title, boolean completed) {
    }

    public record TodoChanged(List<TodoItem> items) {
        public TodoChanged {
            items = List.copyOf(items);
        }
    }

TodoItem là dữ liệu bất biến. TodoChanged mang snapshot danh sách tại thời điểm phát sự kiện. List.copyOf tạo danh sách không thể sửa qua tham chiếu được chia sẻ với subscriber.

### Định nghĩa Observer và Subscription

    @FunctionalInterface
    public interface Observer<E> {
        void onEvent(E event);
    }

    @FunctionalInterface
    public interface Subscription extends AutoCloseable {
        @Override
        void close();
    }

### Xây dựng Model

    public final class TodoModel {
        private final List<TodoItem> items = new ArrayList<>();
        private final List<Observer<TodoChanged>> observers = new ArrayList<>();

        public Subscription subscribe(Observer<TodoChanged> observer) {
            Objects.requireNonNull(observer);
            observers.add(observer);

            return new Subscription() {
                private boolean closed;

                @Override
                public void close() {
                    if (!closed) {
                        closed = true;
                        observers.remove(observer);
                    }
                }
            };
        }

        public void add(String rawTitle) {
            String title = Objects.requireNonNull(rawTitle).trim();

            if (title.isEmpty()) {
                throw new IllegalArgumentException("Tiêu đề không được để trống");
            }

            items.add(new TodoItem(title, false));
            publish();
        }

        public void complete(int index) {
            TodoItem current = items.get(index);

            if (!current.completed()) {
                items.set(index, new TodoItem(current.title(), true));
                publish();
            }
        }

        public List<TodoItem> snapshot() {
            return List.copyOf(items);
        }

        private void publish() {
            TodoChanged event = new TodoChanged(snapshot());

            // Duyệt trên bản sao để listener có thể đăng ký/hủy đăng ký
            // trong lúc callback mà không làm thay đổi vòng lặp hiện tại.
            for (Observer<TodoChanged> observer : List.copyOf(observers)) {
                observer.onEvent(event);
            }
        }
    }

Model cung cấp các hành vi có ý nghĩa như add() và complete(). Mỗi hành vi tự kiểm tra điều kiện cần thiết, cập nhật trạng thái rồi mới gọi publish(). Model không cần biết subscriber là một danh sách, bộ đếm hay biểu đồ.

Subscription.close() hủy đúng lần đăng ký mà nó đại diện. Việc gọi close() nhiều lần không gây lỗi vì thao tác được bảo vệ bằng cờ closed. Ví dụ dùng ArrayList và giả định một luồng; không nên dùng nguyên trạng nếu nhiều thread cùng đăng ký, hủy đăng ký hoặc cập nhật Model.

### Controller điều phối lệnh

    public final class TodoController {
        private final TodoModel model;

        public TodoController(TodoModel model) {
            this.model = model;
        }

        public void addItem(String title) {
            model.add(title);
        }

        public void completeItem(int index) {
            model.complete(index);
        }
    }

Controller nhận hành động từ giao diện và gọi API của Model. Trong ứng dụng lớn, Controller thường gọi application service thay vì giữ Model trực tiếp; ví dụ này tập trung vào cách Observer hoạt động trong một MVC tương tác nhỏ.

### View đăng ký và render

    public final class TodoView implements AutoCloseable {
        private final TodoController controller;
        private final Subscription subscription;

        public TodoView(TodoModel model, TodoController controller) {
            this.controller = controller;
            this.subscription = model.subscribe(this::onModelChanged);

            // Hiển thị trạng thái hiện tại ngay khi View được tạo.
            render(model.snapshot());
        }

        public void onAddClicked(String title) {
            controller.addItem(title);
        }

        public void onCompleteClicked(int index) {
            controller.completeItem(index);
        }

        private void onModelChanged(TodoChanged event) {
            render(event.items());
        }

        private void render(List<TodoItem> items) {
            // Cập nhật danh sách, bộ đếm và các thành phần giao diện.
        }

        @Override
        public void close() {
            subscription.close();
        }
    }

View đăng ký callback khi khởi tạo và render snapshot ban đầu. Khi nhận TodoChanged, View cập nhật giao diện. Khi View đóng, close() hủy đăng ký để Model không tiếp tục giữ tham chiếu đến View.

Trong giao diện thật, render() sẽ cập nhật widget hoặc component. View không nên sửa trực tiếp danh sách nội bộ của Model trong callback; nó chỉ phản ánh trạng thái nhận được.

## 5. Đăng ký và hủy đăng ký đúng vòng đời

Đăng ký là một quan hệ có thời hạn. Một View chỉ nên nhận thông báo khi nó còn tồn tại và còn quan tâm đến Model đó.

### Đăng ký khi View sẵn sàng

Có thể đăng ký trong constructor, phương thức initialize hoặc lifecycle hook của framework. Chọn thời điểm mà View đã có đủ thành phần cần render và callback có thể xử lý an toàn.

Nếu View cần dữ liệu ngay lập tức, hãy xác định rõ cơ chế khởi tạo:

- Publisher phát lại snapshot hiện tại ngay sau khi đăng ký (replay).
- View đăng ký xong rồi tự đọc snapshot hiện tại.
- Một phương thức riêng như subscribeAndReplay() kết hợp cả hai.

Không nên để mỗi View tự đoán rằng publisher có phát lại trạng thái hay không. Hợp đồng phải nêu rõ hành vi ban đầu.

Trong môi trường đa luồng, thao tác “đăng ký rồi đọc snapshot” có thể có khoảng thời gian giữa hai bước khiến một thay đổi bị bỏ lỡ hoặc nhận hai lần. Khi cần tính nhất quán chặt chẽ, publisher nên cung cấp thao tác đăng ký kèm snapshot theo một cơ chế đồng bộ rõ ràng, hoặc dùng event stream có offset/version.

### Hủy đăng ký khi View kết thúc

Nếu publisher giữ listener, listener có thể giữ tham chiếu đến View và toàn bộ cây giao diện. Khi View bị đóng nhưng không hủy đăng ký, publisher vẫn giữ View trong bộ nhớ. Đây là một dạng memory leak.

Một số thời điểm nên hủy đăng ký:

- Cửa sổ desktop bị đóng.
- Component frontend bị unmount.
- Màn hình chuyển sang một Model khác.
- Người dùng rời khỏi một phiên tương tác.
- Một subscription chỉ cần tồn tại trong một tác vụ ngắn đã hoàn thành.

Với Java, có thể quản lý Subscription bằng try-with-resources trong trường hợp vòng đời gói gọn trong một khối:

    try (Subscription subscription = model.subscribe(observer)) {
        runInteraction();
    }

Khi thoát khối, close() được gọi tự động. Với View có vòng đời dài hơn một phương thức, hãy lưu Subscription làm thuộc tính và đóng nó trong lifecycle hook tương ứng.

### Tránh đăng ký lặp

Nếu mỗi lần render lại đều gọi subscribe(), một View có thể nhận cùng sự kiện nhiều lần. Hậu quả là render lặp, xử lý lặp hoặc tạo ra nhiều thao tác phụ ngoài ý muốn.

Thông thường, đăng ký một lần trong giai đoạn khởi tạo và hủy một lần khi kết thúc vòng đời. Nếu cần đổi đối tượng được quan sát, hủy subscription cũ trước khi đăng ký subscription mới.

## 6. Chọn nội dung thông báo

Event là hợp đồng giữa publisher và subscriber. Thiết kế event ảnh hưởng đến mức độ phụ thuộc, khả năng mở rộng và tính nhất quán.

### Thông báo trạng thái hay thông báo sự kiện?

Có hai cách truyền thông tin phổ biến:

**Thông báo có thay đổi:** Event cho biết một phần trạng thái đã thay đổi, chẳng hạn TodoItemsChanged. Subscriber đọc snapshot mới hoặc yêu cầu một query để lấy dữ liệu hiện tại.

**Thông báo mang dữ liệu:** Event chứa snapshot hoặc phần dữ liệu mới cần thiết để subscriber cập nhật ngay.

Thông báo chỉ báo “đã thay đổi” có thể giảm kích thước event nhưng khiến subscriber phải đọc lại Model. Snapshot giúp subscriber render nhất quán với thời điểm phát, nhưng có thể truyền nhiều dữ liệu hơn.

Chọn theo kích thước trạng thái và số lượng subscriber. Nếu event chỉ mang một chỉ số như totalCount, cần chắc rằng subscriber không cần các trường khác để cập nhật chính xác.

### Tránh truyền đối tượng có thể bị sửa

Không nên phát một tham chiếu đến List hoặc entity mutable rồi cho mọi subscriber sửa chung. Một subscriber vô tình thay đổi dữ liệu có thể làm subscriber khác nhìn thấy trạng thái sai.

Có thể dùng:

- Record hoặc value object bất biến.
- Danh sách snapshot không thể sửa.
- Event DTO chỉ chứa những trường subscriber được phép đọc.
- Version hoặc sequence number nếu cần phát hiện thông báo cũ.

Không nên gửi toàn bộ entity lưu trữ chỉ vì nó đang có sẵn trong Model. Event công khai nên phản ánh thông tin mà subscriber cần, không phơi bày cấu trúc nội bộ.

### Đặt tên event theo điều đã xảy ra

Tên event thường diễn đạt ở thì quá khứ hoặc trạng thái đã hoàn thành, ví dụ:

- TodoItemAdded.
- RegistrationCompleted.
- OrderStatusChanged.
- ProfileUpdated.

Tên như AddTodo hoặc CompleteRegistration dễ bị hiểu là một command yêu cầu thực hiện hành động. Command yêu cầu hệ thống làm điều gì đó; event thông báo điều gì đó đã xảy ra. Phân biệt hai khái niệm giúp tránh việc subscriber vô tình coi thông báo là lệnh.

### Không phát event khi trạng thái không đổi

Nếu người dùng đánh dấu một công việc đã hoàn thành trong khi nó vốn đã hoàn thành, Model có thể không cần phát một event mới. Chỉ phát thông báo khi có thay đổi thực sự giúp giảm render không cần thiết và tránh tạo phản ứng dây chuyền.

Tuy nhiên, quyết định này phải nhất quán với hợp đồng. Một số hệ thống có thể phát event cho mọi yêu cầu, kể cả khi trạng thái không đổi, nếu event đại diện cho lần xử lý lệnh chứ không phải sự thay đổi trạng thái. Khi đó, tên và ngữ nghĩa event cần phản ánh đúng điều này.

## 7. Observer trực tiếp và publish–subscribe

Observer và publish–subscribe có liên hệ nhưng không hoàn toàn giống nhau.

| Khía cạnh | Observer trực tiếp | Publish–subscribe |
|---|---|---|
| Quan hệ | Publisher thường giữ danh sách observer hoặc listener | Publisher gửi vào topic/channel; subscriber đăng ký theo kênh |
| Mức độ trung gian | Thường gọi trực tiếp callback | Thường có event bus, broker hoặc dispatcher |
| Phạm vi thường gặp | Các đối tượng trong cùng ứng dụng hoặc tiến trình | Có thể trải qua nhiều mô-đun, tiến trình hoặc dịch vụ |
| Thời điểm nhận | Thường đồng bộ ngay khi phát | Có thể đồng bộ hoặc bất đồng bộ, tùy cơ chế |
| Vận hành | Đơn giản khi số subscriber và phạm vi nhỏ | Có thể cần quản lý retry, lưu trữ, thứ tự và giám sát |

Ví dụ, một Model gọi trực tiếp listener của các View là Observer. Một dịch vụ đăng ký phát RegistrationCompleted lên event bus, còn dịch vụ thông báo và dịch vụ phân tích cùng subscribe topic là publish–subscribe.

Không phải cứ có phương thức subscribe() là hệ thống đã có message broker. Cần phân biệt rõ listener trong bộ nhớ với cơ chế truyền sự kiện qua mạng.

Trong Java, PropertyChangeSupport có thể hỗ trợ phát thông báo khi thuộc tính thay đổi mà không cần tự viết toàn bộ danh sách listener. Các ứng dụng Spring cũng có cơ chế application event để các thành phần trong cùng application context trao đổi sự kiện. Hãy kiểm tra ngữ nghĩa đồng bộ/bất đồng bộ và vòng đời listener của công cụ đang dùng trước khi áp dụng. Các lớp java.util.Observable và java.util.Observer cũ đã bị đánh dấu deprecated từ Java 9; với mã mới, nên ưu tiên API listener rõ ràng hoặc cơ chế sự kiện phù hợp của framework.

### Event bus trong ứng dụng

Một event bus có thể giúp nhiều mô-đun nhận thông báo mà publisher không cần giữ tham chiếu đến từng subscriber. Tuy vậy, event bus cũng tạo thêm câu hỏi:

- Event được xử lý ngay hay xếp hàng?
- Subscriber lỗi thì có retry không?
- Có bảo đảm thứ tự không?
- Event có được lưu bền vững không?
- Làm thế nào tránh xử lý trùng?
- Làm thế nào theo dõi một event qua nhiều handler?

Với ứng dụng nhỏ, Observer trực tiếp thường dễ hiểu và đủ dùng. Khi cần giao tiếp giữa các mô-đun độc lập hoặc dịch vụ phân tán, có thể cân nhắc event bus hoặc broker phù hợp.

## 8. Đồng bộ và bất đồng bộ

### Thông báo đồng bộ

Với thông báo đồng bộ, publisher gọi callback của observer ngay trong luồng phát event. Khi phương thức phát thông báo kết thúc, các callback đã chạy xong (trừ khi callback tự khởi chạy công việc khác).

Ưu điểm:

- Luồng thực thi dễ theo dõi.
- View có thể cập nhật ngay.
- Không cần hàng đợi hoặc cơ chế điều phối riêng.
- Lỗi callback có thể được phát hiện ngay tại nơi phát, nếu hợp đồng cho phép truyền lỗi.

Hạn chế:

- Subscriber chậm làm publisher chậm.
- Callback có thể chặn luồng giao diện.
- Subscriber phát sinh lỗi có thể ảnh hưởng đến các subscriber tiếp theo.
- Callback có thể gọi ngược vào Model và tạo cập nhật lồng nhau.

Thông báo đồng bộ phù hợp với ứng dụng desktop hoặc component nhỏ khi thao tác nhẹ và có quy ước luồng rõ ràng.

### Thông báo bất đồng bộ

Với thông báo bất đồng bộ, publisher gửi event vào hàng đợi hoặc scheduler. Subscriber xử lý sau đó trên một luồng khác hoặc tại thời điểm phù hợp.

Ưu điểm:

- Publisher không cần chờ công việc dài của subscriber.
- Có thể tách tải xử lý giữa các thành phần.
- Hữu ích khi subscriber thực hiện tác vụ nền.

Hạn chế:

- View có thể chưa cập nhật ngay.
- Event có thể đến muộn hoặc sai thứ tự nếu hệ thống không bảo đảm thứ tự.
- Cần xử lý lỗi, retry, hủy tác vụ và trạng thái đang chờ.
- Subscriber có thể nhận một event cũ hơn trạng thái hiện tại.

Với giao diện desktop, cập nhật widget thường phải được chuyển về UI thread. Ví dụ, một tác vụ nền có thể nhận dữ liệu mới rồi lên lịch callback cập nhật giao diện bằng cơ chế của Swing hoặc JavaFX. Không nên cập nhật widget trực tiếp từ worker thread nếu framework yêu cầu thao tác trên UI thread.

### An toàn luồng

Danh sách listener an toàn luồng không đồng nghĩa trạng thái Model cũng an toàn luồng. Ví dụ, CopyOnWriteArrayList có thể giúp đăng ký/hủy đăng ký và duyệt listener an toàn trong một số tình huống, nhưng không tự bảo vệ danh sách công việc hoặc các quy tắc cập nhật của Model.

Hãy chọn và ghi rõ một chính sách:

- Mọi thao tác Model diễn ra trên một UI thread.
- Model dùng khóa hoặc cơ chế đồng bộ để bảo vệ trạng thái.
- Các lệnh được tuần tự hóa qua một executor.
- Event được xử lý trên scheduler riêng, còn UI update được chuyển về UI thread.

Event nên mang dữ liệu bất biến để subscriber không đọc một đối tượng đang bị thay đổi đồng thời.

## 9. Các lỗi thường gặp và cách phòng tránh

### Không hủy đăng ký

Publisher giữ tham chiếu đến listener sau khi View đã đóng. Hãy lưu subscription và hủy nó trong lifecycle hook.

### Đăng ký nhiều lần

Một View đăng ký lại mỗi lần render hoặc mỗi lần vào cùng màn hình. Hãy xác định một điểm đăng ký duy nhất và kiểm thử số lần callback.

### Phát thông báo khi trạng thái chưa nhất quán

Model phát event giữa lúc cập nhật nhiều trường. Subscriber đọc được trạng thái nửa cũ nửa mới. Hãy hoàn thành chuyển đổi trạng thái trước khi phát thông báo, hoặc chỉ phát sau khi transaction đã commit nếu event đại diện cho thay đổi đã lưu bền vững.

### Subscriber sửa dữ liệu dùng chung

Một View thay đổi collection mà Model truyền ra. Hãy gửi snapshot bất biến hoặc DTO chỉ đọc.

### Callback gây cập nhật lồng nhau

Observer nhận event rồi gọi ngược Model để thay đổi trạng thái, khiến event mới được phát ngay trong callback cũ. Điều này có thể tạo vòng lặp hoặc trạng thái khó hiểu. View nên tập trung render; nếu cần phát sinh một command mới, hãy đưa nó qua Controller hoặc cơ chế điều phối có chủ đích.

### Một subscriber lỗi làm gián đoạn các subscriber khác

Với callback đồng bộ, exception từ một observer có thể ngăn các observer sau nhận thông báo nếu publisher không xác định chính sách xử lý lỗi. Hãy quyết định rõ: dừng và báo lỗi, ghi nhận lỗi rồi tiếp tục, hoặc chuyển xử lý qua dispatcher có cơ chế cô lập. Không âm thầm nuốt mọi lỗi.

### Cập nhật giao diện từ sai luồng

Một event đến trên worker thread nhưng callback sửa widget trực tiếp. Hãy chuyển việc render sang UI thread theo framework.

### Phát quá nhiều event

Một thao tác cập nhật nhiều trường có thể phát nhiều event liên tiếp và làm View render lặp. Có thể gom thay đổi thành một thao tác nguyên tử, phát một event tổng hợp hoặc dùng cơ chế batch/coalescing khi phù hợp.

## 10. Observer trong ứng dụng web request–response

Cần chú ý rằng Observer trong MVC tương tác không tự động có nghĩa trình duyệt sẽ nhận được thông báo từ Model trên server.

Trong ứng dụng server-side rendering truyền thống:

1. Trình duyệt gửi HTTP request.
2. Controller gọi application service.
3. Model hoặc domain được cập nhật.
4. Controller nhận kết quả và trả HTML.
5. Request kết thúc.

View HTML được tạo cho request đó thường không còn là một đối tượng đang sống trong bộ nhớ để subscribe trực tiếp với Model. Request kế tiếp có thể tạo một View mới từ trạng thái hiện tại.

Vì vậy, Observer trực tiếp đặc biệt phù hợp với các ứng dụng có View sống lâu trong cùng tiến trình, chẳng hạn ứng dụng desktop, công cụ tương tác hoặc một số kiến trúc frontend quản lý state.

Nếu cần cập nhật trình duyệt khi dữ liệu phía server thay đổi mà không chờ người dùng gửi request mới, cần một kênh giao tiếp thời gian thực:

- Server-Sent Events (SSE) cho luồng sự kiện một chiều từ server đến browser.
- WebSocket cho giao tiếp hai chiều liên tục.
- Polling hoặc long polling trong những tình huống phù hợp.

Ở đây, Observer hoặc event bus có thể được dùng bên trong server để phát hiện thay đổi; một adapter riêng chuyển event thành SSE/WebSocket message. Trình duyệt nhận message và cập nhật state của frontend. Không truyền trực tiếp tham chiếu đến đối tượng Model phía server cho browser.

### Ví dụ luồng cập nhật qua SSE

    Browser
       |
       | GET /events (mở kết nối)
       v
    SSE Endpoint
       ^
       | chuyển event thành message
       |
    Server Event Adapter
       ^
       | subscribe
       |
    Application Event Publisher
       ^
       |
    Use Case / Domain

Sơ đồ chỉ mô tả một cách tổ chức. Trong hệ thống dùng broker, adapter có thể subscribe từ topic thay vì listener trong bộ nhớ. Cần thiết kế xác thực kết nối, quyền xem event, reconnect, event ID và xử lý dữ liệu bị lặp hoặc bị bỏ lỡ.

## 11. Kiểm thử Observer và luồng MVC tương tác

Kiểm thử nên xác nhận hành vi của hợp đồng thay vì phụ thuộc vào cách lưu danh sách listener nội bộ.

### Các trường hợp cần kiểm tra

| Tình huống | Kết quả mong đợi |
|---|---|
| Đăng ký một observer rồi thêm công việc | Observer nhận một event với snapshot mới |
| Có hai observer cùng đăng ký | Cả hai nhận thông báo theo hợp đồng |
| Hủy đăng ký trước khi thay đổi Model | Observer đã hủy không nhận event tiếp theo |
| Hủy đăng ký hai lần | Không phát sinh lỗi ngoài hợp đồng |
| Gửi tiêu đề rỗng | Model từ chối và không phát event thay đổi |
| Đánh dấu mục đã hoàn tất lần thứ hai | Không phát event nếu trạng thái không đổi theo chính sách ví dụ |
| Observer nhận event | Không thể sửa danh sách snapshot |
| View đóng | Subscription được đóng và View không còn nhận event |

### Ví dụ unit test

    @Test
    void notifiesObserverAfterAddingAnItem() {
        TodoModel model = new TodoModel();
        List<TodoChanged> received = new ArrayList<>();

        try (Subscription subscription = model.subscribe(received::add)) {
            model.add("Đọc tài liệu MVC");

            assertEquals(1, received.size());
            assertEquals(
                    List.of(new TodoItem("Đọc tài liệu MVC", false)),
                    received.get(0).items());
        }
    }

    @Test
    void doesNotNotifyAfterUnsubscribe() {
        TodoModel model = new TodoModel();
        List<TodoChanged> received = new ArrayList<>();

        Subscription subscription = model.subscribe(received::add);
        subscription.close();

        model.add("Kiểm thử observer");

        assertTrue(received.isEmpty());
    }

    @Test
    void rejectsBlankTitleWithoutPublishingChange() {
        TodoModel model = new TodoModel();
        List<TodoChanged> received = new ArrayList<>();

        try (Subscription subscription = model.subscribe(received::add)) {
            assertThrows(
                    IllegalArgumentException.class,
                    () -> model.add("   "));

            assertTrue(received.isEmpty());
            assertTrue(model.snapshot().isEmpty());
        }
    }

Ví dụ minh họa cách kiểm thử publisher. Trong bộ test thực tế, cần đóng mọi subscription sau khi test kết thúc để tránh listener còn tồn tại nếu Model được chia sẻ. Với test có thời gian hoặc bất đồng bộ, hãy dùng cơ chế chờ đồng bộ hóa có timeout thay vì sleep tùy ý.

### Kiểm thử tích hợp với View và Controller

Ngoài unit test cho Model, có thể kiểm thử:

- Khi người dùng thao tác trên View, Controller gọi đúng hành vi.
- Khi Model phát event, View render dữ liệu mới.
- Khi View bị đóng hoặc unmount, listener không còn được gọi.
- Event đến từ worker thread được chuyển về UI thread.
- Một event không tạo ra vòng lặp cập nhật ngoài dự kiến.

Không cần kiểm thử lại toàn bộ quy tắc nghiệp vụ trong test Observer. Quy tắc đó thuộc unit test của Model hoặc application service; test giao diện tập trung vào việc nhận thông báo và phản ánh trạng thái.

## 12. Quy trình thiết kế cơ chế đăng ký

Khi thêm Observer vào một ứng dụng MVC, hãy thực hiện theo trình tự:

1. Xác định trạng thái nào thay đổi và những thành phần nào thực sự cần biết.
2. Xác định publisher sở hữu thay đổi; không biến mọi lớp thành event source.
3. Định nghĩa event nhỏ, có ý nghĩa và chỉ mang dữ liệu cần thiết.
4. Thiết kế subscribe() trả về một Subscription có thể đóng.
5. Quy định rõ có phát lại trạng thái ban đầu hay không.
6. Chọn đồng bộ hay bất đồng bộ và ghi rõ chính sách luồng.
7. Đăng ký ở giai đoạn View sẵn sàng; hủy khi View kết thúc vòng đời.
8. Quy định cách xử lý exception từ observer và cập nhật lồng nhau.
9. Kiểm thử phát event, nhận event, hủy đăng ký và trường hợp biên.
10. Nếu cần giao tiếp qua mạng hoặc nhiều tiến trình, đánh giá event bus, SSE hoặc WebSocket thay vì mở rộng listener trong bộ nhớ một cách tùy tiện.

## Kết luận

Observer cung cấp cơ chế để Model thông báo thay đổi cho những thành phần đã đăng ký quan tâm. Trong MVC tương tác, View có thể subscribe khi được khởi tạo, render trạng thái ban đầu, nhận event để cập nhật giao diện và unsubscribe khi kết thúc vòng đời. Controller tiếp tục xử lý lệnh từ người dùng và điều phối hành vi của ứng dụng.

Thiết kế tốt cần làm rõ hợp đồng event, dữ liệu bất biến, vòng đời subscription, chính sách đồng bộ/bất đồng bộ và xử lý lỗi. Với ứng dụng web request–response, View HTML thường chỉ tồn tại trong một request; cập nhật trình duyệt theo thời gian thực cần một kênh như SSE hoặc WebSocket. Chọn cơ chế theo vòng đời và ranh giới thực tế của các thành phần giúp ứng dụng giảm phụ thuộc và dễ kiểm thử hơn.
