# Rủi ro làm lộ this trong quá trình khởi tạo

## Đối tượng đã có tham chiếu nhưng chưa chắc đã sẵn sàng

Khi thân hàm tạo đang chạy, `this` đã trỏ tới một đối tượng. Tuy nhiên, các trường và điều kiện hợp lệ của đối tượng có thể chưa được thiết lập xong.

**Làm lộ `this` (this escape)** xảy ra khi mã bên ngoài có thể tiếp cận đối tượng trong lúc quá trình khởi tạo chưa hoàn tất, chẳng hạn do hàm tạo đăng ký listener, đưa mình vào registry hoặc khởi động một công việc giữ tham chiếu tới mình.

Hậu quả có thể xuất hiện ngay trong một luồng thông qua callback đồng bộ, hoặc giữa nhiều luồng dưới dạng quan sát trạng thái chưa sẵn sàng và thiếu bảo đảm công bố dữ liệu. Bài dùng Java 17+ và một callback gọi ngay để có kết quả tái hiện rõ ràng, không dựa vào may rủi của lịch luồng.

## Vì sao trường có thể vẫn mang giá trị mặc định?

Khi đối tượng được tạo, các trường instance có giá trị mặc định trước những phép gán trong quá trình khởi tạo: số nguyên là `0`, boolean là `false`, tham chiếu là `null`.

Nếu gọi một phương thức đọc trường trước khi phép gán dự định được thực hiện, phương thức có thể đọc giá trị mặc định ấy. Việc có một tham chiếu khác `null` tới đối tượng không chứng minh hàm tạo đã chạy xong. Xem [quá trình tạo instance trong JLS](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.5).

Một điều kiện hợp lệ (invariant) có thể cần nhiều trường cùng được thiết lập, ví dụ tên đã có, cấu hình đã kiểm tra và tài nguyên đã gắn xong. Làm lộ `this` ở giữa các bước có thể cho bên ngoài nhìn một tổ hợp trạng thái mà API không dự định công bố.

## Ví dụ hoàn chỉnh: callback thấy `final` vẫn là `null`

Trong ví dụ, `EventSource.register` lưu listener và gọi callback ngay để lấy trạng thái ban đầu. Đó là hợp đồng có chủ ý của nguồn sự kiện, không có một luồng phụ nào cần thắng cuộc đua để lỗi xuất hiện.

Lưu tệp `ThisEscapeDemo.java`:

```java
import java.util.Objects;

public final class ThisEscapeDemo {
    private ThisEscapeDemo() {
    }

    @FunctionalInterface
    interface Listener {
        String snapshot();
    }

    static final class EventSource {
        private final String label;
        private volatile Listener listener;

        EventSource(String label) {
            this.label = label;
        }

        void register(Listener listener) {
            this.listener = Objects.requireNonNull(listener, "listener");
            System.out.println(label + ".duringRegister: " + listener.snapshot());
        }

        String read() {
            Listener current = listener;
            return current == null ? "<unregistered>" : current.snapshot();
        }
    }

    static final class UnsafeComponent implements Listener {
        private final String name;

        UnsafeComponent(EventSource source) {
            source.register(this);
            name = "ready";
        }

        @Override
        public String snapshot() {
            return name;
        }
    }

    static final class SafeComponent implements Listener {
        private final String name;

        private SafeComponent(String name) {
            this.name = Objects.requireNonNull(name, "name");
        }

        static SafeComponent create(EventSource source, String name) {
            Objects.requireNonNull(source, "source");
            SafeComponent component = new SafeComponent(name);
            source.register(component);
            return component;
        }

        @Override
        public String snapshot() {
            return name;
        }
    }

    public static void main(String[] args) {
        EventSource unsafeSource = new EventSource("unsafe");
        UnsafeComponent unsafe = new UnsafeComponent(unsafeSource);
        System.out.println("unsafe.afterConstructor: " + unsafe.snapshot());

        EventSource safeSource = new EventSource("safe");
        SafeComponent safe = SafeComponent.create(safeSource, "ready");
        System.out.println("safe.afterFactory: " + safe.snapshot());
        System.out.println("safe.sourceRead: " + safeSource.read());
    }
}
```

Biên dịch và chạy tại thư mục chứa tệp bằng JDK 17 trở lên:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all -Werror ThisEscapeDemo.java
java ThisEscapeDemo
```

Stdout chính xác:

```text
unsafe.duringRegister: null
unsafe.afterConstructor: ready
safe.duringRegister: ready
safe.afterFactory: ready
safe.sourceRead: ready
```

### Điều gì xảy ra trong `UnsafeComponent`?

Hàm tạo gọi `source.register(this)` trước khi gán `name = "ready"`. Khi `register` gọi `listener.snapshot()`, nó đi vào chính đối tượng `UnsafeComponent` còn đang được tạo.

`snapshot()` đọc `name` lúc phép gán cuối chưa diễn ra, nên nhận `null`. Sau khi hàm tạo hoàn tất, lời gọi `unsafe.snapshot()` trong `main` lại nhận `ready`.

Trường `name` là `final`, nhưng điều đó không ngăn một phương thức được gọi sớm đọc giá trị mặc định trong quá trình khởi tạo. Trong ví dụ, phương thức `snapshot` là nơi đọc trường; phép kiểm tra gán chắc chắn của mã nguồn không biến callback này thành một cuộc gọi xảy ra sau hàm tạo.

Đây là quan sát có thứ tự ngay trong cùng luồng, không phải bằng chứng về một data race ngẫu nhiên. Nó cho thấy đối tượng có thể bị sử dụng quá sớm mà không cần thêm `Thread.sleep`, nhiều lõi CPU hay thao tác reflection.

### Factory thay đổi điểm công bố như thế nào?

`SafeComponent` hoàn tất phép kiểm tra và gán trường trong hàm tạo riêng. Sau khi `new SafeComponent(name)` trả về, factory mới gọi `source.register(component)`.

Vì vậy callback gọi ngay vẫn đọc được một đối tượng đã khởi tạo xong. Các lớp của ví dụ là `final`, tránh một lớp con kéo dài quá trình khởi tạo ngoài giả định của factory.

Hàm tạo riêng không tự làm mọi cách khởi tạo trở nên an toàn: nếu tự gọi registry hoặc bắt đầu công việc giữ `this` ngay bên trong hàm tạo riêng thì vấn đề vẫn tồn tại. Điều quan trọng là **thứ tự hoàn tất trạng thái rồi mới công bố**.

## Tách hoàn tất khởi tạo khỏi công bố an toàn giữa các luồng

Để sử dụng một đối tượng từ luồng khác, có hai câu hỏi cần xét riêng:

1. Trạng thái mà bên nhận được phép dùng đã thiết lập xong chưa?
2. Đường truyền tham chiếu có quan hệ bộ nhớ phù hợp để bên nhận quan sát trạng thái đó không?

Hoàn tất hàm tạo rồi đưa tham chiếu qua một biến chia sẻ thường mà không có đồng bộ không phải thiết kế công bố an toàn tổng quát. Ngược lại, đưa một đối tượng vào một cấu trúc đồng bộ khi nó **chưa hoàn tất** cũng không làm các phép gán tương lai tự được truyền theo một cạnh đã xảy ra trước đó.

Trong ví dụ, `EventSource.listener` là `volatile`. Việc lưu tham chiếu vào đó không khiến callback quay ngược thời gian để chờ `name` được gán. Callback trực tiếp vẫn đọc `null` vì phép gán còn ở phía sau.

Nếu một luồng khác đọc tham chiếu qua `volatile`, cạnh ghi–đọc có thể truyền các tác động đã xảy ra **trước** lần ghi tham chiếu; nó không tự bao phủ những cập nhật trong hàm tạo xảy ra **sau** lần ghi ấy.

Với factory, các gán khởi tạo xảy ra trước `register`, rồi tham chiếu được công bố qua trường `volatile`. Bên đọc qua `EventSource.read()` nhận đường công bố phù hợp cho trạng thái đã thiết lập trước đó. Các cơ chế công bố hiện hành còn gồm cùng monitor, khởi tạo tĩnh và các cấu trúc concurrent có hợp đồng bộ nhớ tương ứng. Xem [tính nhất quán bộ nhớ trong `java.util.concurrent`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/package-summary.html#MemoryVisibility).

## `final` hỗ trợ gì và không cứu được gì?

Java có ngữ nghĩa đặc biệt cho trường `final` khi đối tượng được khởi tạo đúng cách. Trong cách thiết kế điển hình, phải tránh để tham chiếu đến đối tượng bị quan sát trước khi quá trình khởi tạo liên quan hoàn tất. Không dựa vào bảo đảm đó để biện minh việc công bố `this` sớm. Xem [ngữ nghĩa trường `final` trong JLS](https://docs.oracle.com/javase/specs/jls/se25/html/jls-17.html#jls-17.5.1).

Đồng thời, không hiểu `final` như một lệnh làm mọi trường khác tự có tính bất biến. Nó cũng không biến các cập nhật trạng thái sau khi tạo thành cập nhật an toàn luồng.

Nếu một đường công bố có quan hệ happens-before riêng, những ghi trước nó có thể được bảo đảm bởi chính quan hệ đó. Vì vậy cần chỉ rõ cơ chế nào cung cấp bảo đảm; tránh cả hai cực đoan “có final là luôn an toàn” và “hễ constructor chưa trả về thì mọi kiểu đồng bộ đều vô tác dụng”.

Lựa chọn dễ kiểm tra là giữ đối tượng chưa hoàn tất ở phạm vi khởi tạo, thiết lập đầy đủ trạng thái, rồi công bố bằng giao thức được chọn.

## Những đường làm lộ `this` thường gặp

| Mẫu trong quá trình khởi tạo | Tham chiếu có thể thoát bằng cách nào? |
| --- | --- |
| `registry.add(this)` hoặc gán `shared = this` | Bên khác nhận tham chiếu và có thể sử dụng ngay |
| Đăng ký listener là chính đối tượng | Nguồn sự kiện có thể gọi callback hoặc chuyển cho luồng khác |
| `source.register(this::handle)` | Method reference giữ đối tượng nhận là `this` |
| Lambda đọc một trường instance | Lambda có thể giữ tham chiếu tới đối tượng bao ngoài |
| Khởi động thread hoặc gửi task truy cập instance | Công việc có thể bắt đầu trước khi constructor xong |
| Tạo inner class không `static` rồi đưa ra ngoài | Inner instance có thể giữ tham chiếu tới outer instance |
| Gọi phương thức có thể bị ghi đè từ constructor cha | Phần cài đặt của lớp con có thể chạy trước khi phần lớp con được khởi tạo |

Không cần xuất hiện chính chữ `this` tại dòng đăng ký mới có rủi ro. Lambda, method reference và các đối tượng giữ tham chiếu gián tiếp vẫn có thể làm lộ cùng đối tượng.

Ngược lại, chỉ truyền `this` cho một helper không tự chứng minh đã có công bố ra bên ngoài. Cần xem helper có lưu tham chiếu, gọi lại, gửi task hoặc trao nó cho mã khác hay không. Ý nghĩa nằm ở hành vi của đường gọi.

## Khởi động công việc trong constructor

Lệnh `Thread.start()` cho phép luồng mới chạy đồng thời với luồng gọi. Những tác động trước `start` có quan hệ thứ tự phù hợp với luồng được khởi động; các phép gán constructor còn nằm sau `start` không nhờ đó mà tự trở thành tác động trước công việc. Xem [`Thread.start()`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html#start()).

Nếu task được gửi tới executor, không giả định nó sẽ chỉ chạy sau khi hàm tạo trở về. Nó có thể chạy rất sớm; một số cách triển khai `Executor` còn có thể thực thi trong chính luồng gọi.

Đặt một thời gian chờ bằng `sleep` trong task không sửa được hợp đồng khởi tạo. Nó chỉ làm thay đổi cơ hội xảy ra lịch thực thi cụ thể.

Thiết kế thường rõ hơn khi constructor chỉ thiết lập trạng thái, còn factory hoặc thành phần quản lý vòng đời gọi `start()` hay đăng ký sau đó. Nếu dùng khởi tạo hai giai đoạn, API phải quy định rõ đối tượng được phép làm gì trước khi bắt đầu và xử lý việc gọi bắt đầu nhiều lần thế nào.

## Gọi phương thức có thể ghi đè từ constructor cha

Constructor của lớp cha có thể gọi một phương thức mà lớp con ghi đè. Java vẫn phân phối lời gọi tới phần thực hiện ở lớp con; nó không tạm vô hiệu hóa đa hình chỉ vì đang khởi tạo.

Nhưng phần khởi tạo instance của lớp con chưa hoàn tất tại lúc constructor cha đang chạy. Phương thức lớp con có thể nhìn các trường con ở giá trị mặc định hoặc dùng một điều kiện hợp lệ chưa được thiết lập.

Cách hạn chế rủi ro là không gọi các điểm mở rộng có thể bị ghi đè từ constructor. Dùng helper `private`, hoặc `final` khi phù hợp, và thiết kế callback mở rộng ở một giai đoạn sau khi đối tượng đã hoàn tất. Giữ lớp `final` cũng không ngăn việc tự đăng ký `this` quá sớm như `UnsafeComponent`.

## Nếu chỉ chuyển phép gán lên trước đăng ký thì sao?

Chuyển `name = "ready"` lên trước `source.register(this)` sẽ làm callback hiện tại đọc đúng giá trị trong ví dụ đơn giản. Nhưng trước khi coi đó là giải pháp tổng quát, phải xét:

- Có trường hoặc bước kiểm tra nào khác còn thực hiện sau đăng ký không?
- Registry có thể gọi những phương thức nào ngay khi nhận đối tượng?
- Có một constructor/lớp con khác còn tiếp tục khởi tạo không?
- Có thể có ngoại lệ khiến quá trình tạo thất bại sau khi đối tượng đã được lưu bên ngoài không?
- Đường công bố giữa các luồng có bảo đảm bộ nhớ nào?

Nếu constructor ném lỗi sau khi đăng ký, registry có thể vẫn giữ một đối tượng mà thao tác tạo chưa hoàn tất thành công. Công bố sau khi tạo xong giúp tránh riêng loại rủi ro đó.

Đăng ký bản thân nó cũng có thể thất bại; thành phần quản lý vòng đời cần xác định quy tắc đăng ký thành công và thu hồi khi cần. Đó là vấn đề vòng đời bổ sung, không được giải quyết chỉ bằng từ khóa `final`.

## Kiểm tra và lựa chọn thiết kế

1. Rà soát constructor và mọi helper nó gọi: đánh dấu nơi tham chiếu có thể được lưu hoặc truyền cho bên khác.
2. Xác định điều kiện hợp lệ của đối tượng và thời điểm nó hoàn tất.
3. Tách callback/task/đăng ký khỏi giai đoạn chưa hoàn tất nếu có thể.
4. Chọn đường công bố rõ ràng cho các luồng khác.
5. Với cấu hình hoặc dữ liệu có thể thay đổi sau khi tạo, thiết kế đồng bộ cập nhật riêng; khởi tạo đúng không tự giải quyết mọi thay đổi tương lai.
6. Kiểm chứng bằng một callback có thể gọi ngay và bằng lập luận happens-before; không chỉ dựa vào nhiều lần chạy không thấy lỗi.

## Thực hành đối chiếu

1. Trong bản sao `UnsafeComponent`, chuyển phép gán `name` lên trước đăng ký. Callback đổi thành `ready`; giải thích vì sao đây chỉ chứng minh thứ tự cho trạng thái của ví dụ.
2. Giữ bản an toàn, đổi tên được truyền vào factory thành `configured`. Cả callback, đối tượng trả về và `safeSource.read()` phải cùng đọc `configured`.
3. Đổi đường đăng ký trực tiếp thành một method reference giữ `this` trong một ví dụ riêng; chỉ ra tham chiếu instance vẫn có thể được giữ gián tiếp.
4. Phân tích một task được gửi từ constructor và đánh dấu các ghi trước/sau điểm gửi, thay vì thêm `sleep` để mong task chạy muộn.
5. Nêu rõ điểm công bố của factory và cơ chế truyền trạng thái cho một luồng đọc khác trong thiết kế đang dùng.

Người học cần phân biệt có tham chiếu tới đối tượng với có một đối tượng đã sẵn sàng, và xét cả thứ tự khởi tạo lẫn đường công bố trước khi cho mã bên ngoài sử dụng instance.