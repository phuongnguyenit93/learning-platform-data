# Quan sát điểm tiếp tục thực thi và vòng đời phương thức main

Khi một ứng dụng Java được khôi phục từ checkpoint CRaC, JVM tiếp tục từ trạng thái thực thi đã được lưu. Nó không khởi chạy lại chương trình như một lần chạy mới và không tự gọi lại phương thức `main(String[] args)`. Điểm tiếp tục phụ thuộc vào vị trí mà tiến trình đang thực thi tại thời điểm checkpoint: nếu checkpoint được yêu cầu ngay trong một lời gọi Java, luồng đó tiếp tục sau lời gọi khi restore hoàn tất; nếu checkpoint được yêu cầu từ bên ngoài, các luồng tiếp tục từ trạng thái đã được chụp.

Đây là điểm quan trọng để hiểu đúng vòng đời CRaC. Một checkpoint lưu trạng thái của cả tiến trình theo khả năng của runtime và môi trường, trong đó có heap, trạng thái lớp và trạng thái thực thi của các thread. Khi restore, ứng dụng tiếp tục sử dụng trạng thái đó. Các đoạn mã khởi tạo đã chạy trước checkpoint không tự chạy lại; các đoạn mã nằm sau điểm tiếp tục vẫn sẽ chạy khi tiến trình được khôi phục.

## 1. `main()` là điểm vào chương trình, không phải điểm vào của mỗi lần restore

Với một chương trình Java thông thường, Java launcher khởi tạo JVM, nạp lớp chính và gọi phương thức `main(String[] args)`. Các static initializer và quá trình khởi tạo lớp cần thiết diễn ra trước khi mã tương ứng được thực thi. Sau đó `main()` điều khiển luồng khởi động của ứng dụng.

Ví dụ đơn giản:

```java
public class Application {

    static {
        System.out.println("class initialized");
    }

    public static void main(String[] args) {
        System.out.println("main entered");
        initialize();
        serve();
    }

    private static void initialize() {
        System.out.println("application initialized");
    }

    private static void serve() {
        System.out.println("serving requests");
    }
}
```

Trong lần chạy lạnh, luồng chính đi qua các bước theo thứ tự: lớp được khởi tạo, `main()` được gọi, ứng dụng được khởi tạo và cuối cùng bắt đầu phục vụ. Khi tiến trình được checkpoint sau khi đã hoàn thành một phần các bước này, trạng thái đã hoàn thành được giữ lại trong checkpoint.

Restore không tương đương với việc chạy lại lệnh `java -jar application.jar`. Lệnh khởi chạy mới thông thường tạo một JVM mới và gọi `main()` từ đầu. Restore CRaC nạp trạng thái tiến trình đã lưu, vì vậy luồng chính tiếp tục từ stack frame và vị trí thực thi đã được checkpoint. Static initializer, đoạn đầu của `main()` và các bước khởi tạo đã hoàn thành không tự được gọi lại.

Có thể ghi nhớ sự khác biệt như sau:

| Khởi động lạnh | Restore từ CRaC |
|---|---|
| Java launcher tạo tiến trình JVM mới | Runtime khôi phục tiến trình từ checkpoint |
| Lớp được nạp và khởi tạo theo luồng khởi động | Trạng thái lớp đã lưu được khôi phục |
| Launcher gọi `main()` | Không gọi lại `main()` |
| Mã chạy từ đầu theo luồng khởi động | Các thread tiếp tục từ trạng thái đã lưu |
| Ứng dụng tạo lại các object và context | Heap và các trạng thái được checkpoint được phục hồi |

## 2. Quan sát điểm tiếp tục khi gọi `Core.checkpointRestore()`

Một cách dễ quan sát điểm tiếp tục là yêu cầu checkpoint từ chính ứng dụng bằng API CRaC. Trong ví dụ sau, lời gọi `Core.checkpointRestore()` là điểm mà luồng thực thi tạm dừng để tạo checkpoint. Khi một tiến trình được restore từ checkpoint đó, lời gọi hoàn tất và luồng tiếp tục với câu lệnh kế tiếp.

```java
import org.crac.Core;

public class CheckpointApplication {

    public static void main(String[] args) throws Exception {
        System.out.println("1. main entered");

        initializeApplication();
        warmUpApplication();

        System.out.println("2. requesting checkpoint");
        Core.checkpointRestore();

        System.out.println("3. execution resumed after restore");
        verifyExternalResources();
        startServing();
    }

    private static void initializeApplication() {
        System.out.println("initialize application");
    }

    private static void warmUpApplication() {
        System.out.println("warm up application");
    }

    private static void verifyExternalResources() {
        System.out.println("verify resources");
    }

    private static void startServing() {
        System.out.println("start serving");
    }
}
```

Ví dụ giả định ứng dụng chạy bằng một JDK có hỗ trợ CRaC và checkpoint được yêu cầu thành công. Dòng `Core.checkpointRestore()` biểu diễn điểm chuyển từ giai đoạn chuẩn bị sang checkpoint/restore. Khi tiến trình được khôi phục, luồng thực thi tiếp tục sau lời gọi này.

Có thể hình dung stack của luồng chính như sau:

```text
main(args)
  |
  +-- initializeApplication()
  |
  +-- warmUpApplication()
  |
  +-- Core.checkpointRestore()
        |
        +-- chuẩn bị và tạo checkpoint
        |
        +-- tiến trình được restore
        |
        +-- lời gọi hoàn tất trong luồng đã khôi phục
  |
  +-- verifyExternalResources()
  |
  +-- startServing()
```

Điểm cần chú ý là sau restore, luồng chính tiếp tục ở câu lệnh `verifyExternalResources()`. Nó không quay về dòng đầu tiên của `main()`. Vì vậy, log `1. main entered`, `initialize application` và `warm up application` không được in lại chỉ vì tiến trình được restore.

Trong cách nhìn này, lời gọi checkpoint có vẻ giống một lời gọi hàm thông thường: chương trình gọi hàm, chờ hàm hoàn tất, rồi chạy câu lệnh kế tiếp. Khác biệt nằm ở chỗ runtime lưu trạng thái tiến trình trong khoảng chuyển tiếp đó. Phần mã sau lời gọi chỉ tiếp tục khi tiến trình được khôi phục và lời gọi có thể trở về luồng thực thi.

## 3. Điểm tiếp tục không nhất thiết nằm trong `main()`

Checkpoint có thể được yêu cầu từ một API trong chương trình hoặc bởi công cụ vận hành bên ngoài. Khi checkpoint được yêu cầu từ bên ngoài, không có một dòng `Core.checkpointRestore()` cụ thể để dùng làm mốc trong mã nguồn. Runtime lưu trạng thái các thread tại thời điểm checkpoint theo cơ chế của môi trường. Sau restore, mỗi thread tiếp tục từ trạng thái đã lưu của chính nó.

Ví dụ, một ứng dụng server có thể có các thread sau:

```text
JVM process
├── main thread
│   └── SpringApplication.run(...) đã trả về
├── HTTP acceptor thread
│   └── đang chờ kết nối mới
├── request worker thread
│   └── đang xử lý hoặc đang chờ công việc
└── scheduler thread
    └── đang chờ lần chạy kế tiếp
```

Nếu checkpoint được yêu cầu khi `main()` đã kết thúc nhưng các thread không daemon của server vẫn giữ JVM hoạt động, stack frame của `main()` không còn hoạt động. Restore không làm cho `main()` chạy lại. Các thread còn tồn tại trong checkpoint tiếp tục theo trạng thái đã lưu và ứng dụng tiếp tục vận hành từ những thread đó.

Ngược lại, nếu checkpoint diễn ra khi `main()` vẫn đang thực thi, stack frame của `main()` cũng thuộc trạng thái tiến trình được lưu. Sau restore, luồng chính tiếp tục tại vị trí thực thi đã lưu. Ví dụ, nếu `main()` đang chờ một tác vụ hoàn tất, nó tiếp tục từ trạng thái chờ được khôi phục theo khả năng của runtime và môi trường.

Điều này giúp phân biệt ba trường hợp:

1. **Checkpoint tại lời gọi API trong `main()`:** sau restore, lời gọi hoàn tất và `main()` chạy câu lệnh kế tiếp.
2. **Checkpoint bên ngoài khi `main()` còn hoạt động:** `main()` tiếp tục từ trạng thái stack đã lưu, không bắt đầu lại từ đầu.
3. **Checkpoint sau khi `main()` đã trả về:** `main()` vẫn đã kết thúc; các thread khác còn sống tiếp tục công việc của chúng sau restore.

Nếu tất cả thread không daemon đã kết thúc và JVM đã thoát, sẽ không còn tiến trình đang chạy để chụp checkpoint theo cách thông thường. Vì vậy, một ứng dụng server thường còn các thread phục vụ hoặc thread nền giữ tiến trình hoạt động sau khi `main()` trả về.

## 4. Ví dụ với vòng đời `main()` của Spring Boot

Ứng dụng Spring Boot thường có phương thức `main()` rất ngắn:

```java
@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

`SpringApplication.run(...)` tạo và khởi động Spring `ApplicationContext`, khởi tạo bean, chạy các bước khởi động của Spring Boot và khởi động web server nếu ứng dụng có cấu hình web. Khi lời gọi trả về, câu lệnh trong `main()` kết thúc và phương thức `main()` có thể trả về. Các thread của web server tiếp tục giữ JVM hoạt động và xử lý request.

Nếu ứng dụng được checkpoint sau khi Spring context đã khởi động, checkpoint có thể chứa trạng thái context, bean, cache và các thread đang tồn tại theo khả năng hỗ trợ của CRaC. Khi restore, Spring context được khôi phục cùng trạng thái tiến trình. `SpringApplication.run(...)` không được gọi lại chỉ vì restore diễn ra; các bean không được tạo lại từ đầu theo quy trình khởi động lạnh.

Điều này cũng có nghĩa những callback hoặc sự kiện chỉ chạy trong quá trình khởi động ban đầu không tự được phát lại. Chẳng hạn, không nên giả định `@PostConstruct`, `ApplicationRunner`, `CommandLineRunner` hoặc các sự kiện startup sẽ tự chạy lần nữa sau restore. Nếu một thành phần cần mở lại kết nối hoặc làm mới dữ liệu sau restore, hãy tích hợp trách nhiệm đó với vòng đời CRaC của tài nguyên.

Một số công việc thường cần được phân chia như sau:

| Công việc | Thời điểm phù hợp |
|---|---|
| Tạo Spring bean và cấu trúc nội bộ | Khởi động ban đầu, trước checkpoint |
| Nạp cache ổn định và làm nóng đường chạy | Trước checkpoint |
| Ngừng nhận request, drain request đang chạy | Chuẩn bị checkpoint |
| Đóng hoặc đưa connection pool/client về trạng thái an toàn | `beforeCheckpoint` theo hướng dẫn của thư viện |
| Tạo lại kết nối, xác thực lại hoặc làm mới lease | `afterRestore` |
| Cho phép load balancer gửi traffic | Sau khi restore và kiểm tra readiness hoàn tất |

Ví dụ trên chỉ mô tả vòng đời khái niệm. Tích hợp thực tế cần tuân theo hỗ trợ CRaC của phiên bản Spring Boot, JDK, connection pool, JDBC driver, HTTP client và các thư viện ứng dụng đang sử dụng.

## 5. Callback CRaC nằm ở đâu so với điểm tiếp tục của `main()`?

CRaC cung cấp giao diện `Resource` để thành phần sở hữu tài nguyên tham gia vào hai giai đoạn của vòng đời:

- `beforeCheckpoint(...)` chạy trong quá trình chuẩn bị checkpoint. Resource có thể ngừng hoạt động liên quan, flush dữ liệu hoặc đóng tài nguyên cần tạo lại.
- `afterRestore(...)` chạy trong quá trình phục hồi. Resource có thể mở lại kết nối, làm mới thông tin hết hạn hoặc khởi động lại thành phần đã tạm dừng.

Ví dụ rút gọn:

```java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class ConnectionResource implements Resource {

    private RemoteConnection connection;

    public ConnectionResource() {
        connection = RemoteConnection.open();
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        if (connection != null) {
            connection.close();
            connection = null;
        }
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        connection = RemoteConnection.open();
    }

    public static void register() {
        Core.getGlobalContext().register(new ConnectionResource());
    }
}
```

`RemoteConnection` là lớp minh họa. Trong ứng dụng thực tế, cần dùng API của client/driver tương ứng và phối hợp với các thread đang sử dụng kết nối trước khi đóng nó.

Khi checkpoint được yêu cầu từ `Core.checkpointRestore()`, các resource đã đăng ký tham gia vào quy trình checkpoint/restore. Sau khi tiến trình được khôi phục và các bước phục hồi liên quan hoàn tất, luồng gọi tiếp tục sau điểm gọi API. Vì thế, mã sau `Core.checkpointRestore()` có thể kiểm tra trạng thái tài nguyên và tiếp tục quá trình đưa ứng dụng vào phục vụ.

Không nên đặt logic mở kết nối sau restore ở đầu `main()` với giả định rằng `main()` sẽ chạy lại. Đầu `main()` chỉ chạy trong lần khởi động ban đầu. Callback `afterRestore` hoặc cơ chế lifecycle tương ứng mới là nơi phù hợp cho việc phục hồi tài nguyên.

## 6. Checkpoint không làm stack Java thoát ra như shutdown bình thường

Checkpoint là thao tác lưu trạng thái tiến trình, không phải một lần kết thúc ứng dụng theo luồng shutdown thông thường. Khi tiến trình được checkpoint, các stack frame và trạng thái thực thi được lưu để có thể tiếp tục khi restore. Chương trình không tự đi qua các câu lệnh còn lại trong `try`, không tự unwind stack và không chạy `finally` chỉ vì checkpoint xảy ra.

Ví dụ:

```java
try {
    performWork();
    Core.checkpointRestore();
    continueWorkAfterRestore();
} finally {
    releaseResource();
}
```

`finally` không phải callback checkpoint. Nó chạy khi luồng điều khiển rời khỏi khối `try` theo các quy tắc Java thông thường, chẳng hạn khi khối hoàn tất hoặc có exception. Việc tiến trình bị checkpoint không tương đương với việc thoát khỏi khối `try`. Nếu `releaseResource()` cần chạy trước checkpoint, hãy xử lý qua `beforeCheckpoint` hoặc cơ chế quản lý resource phù hợp. Nếu tài nguyên cần được tạo lại, hãy xử lý sau restore.

Tương tự, không nên dựa vào shutdown hook, `@PreDestroy` hoặc callback đóng ứng dụng để chuẩn bị checkpoint. Các cơ chế đó phục vụ vòng đời kết thúc ứng dụng. CRaC resource callback phục vụ chuyển trạng thái checkpoint/restore và cần được thiết kế riêng.

## 7. Cách quan sát điểm tiếp tục trong thực tế

Để quan sát đúng vòng đời, hãy đặt log ở các mốc khác nhau thay vì chỉ ghi một thông báo chung như “application started”. Một ví dụ có thể dùng các nhãn sau:

```java
public static void main(String[] args) throws Exception {
    log("MAIN_ENTERED");

    initialize();
    log("INITIALIZATION_COMPLETED");

    warmUp();
    log("WARMUP_COMPLETED");

    Core.checkpointRestore();
    log("MAIN_CONTINUED_AFTER_RESTORE");

    verifyConnections();
    log("DEPENDENCIES_READY");

    serve();
}
```

Khi xem log, hãy diễn giải theo điểm thực thi:

| Log marker | Ý nghĩa |
|---|---|
| `MAIN_ENTERED` | `main()` đã được gọi trong quá trình khởi động ban đầu |
| `INITIALIZATION_COMPLETED` | Các bước khởi tạo trước checkpoint đã hoàn thành |
| `WARMUP_COMPLETED` | Warm-up đã hoàn thành |
| `MAIN_CONTINUED_AFTER_RESTORE` | Luồng đã tiếp tục sau điểm checkpoint/restore trong ví dụ |
| `DEPENDENCIES_READY` | Các dependency cần thiết đã được kiểm tra sau restore |

Khi restore từ checkpoint tạo tại lời gọi API trong ví dụ, marker `MAIN_ENTERED`, `INITIALIZATION_COMPLETED` và `WARMUP_COMPLETED` không được in lại bởi lần restore đó. Marker `MAIN_CONTINUED_AFTER_RESTORE` xuất hiện khi luồng đã khôi phục tiếp tục qua lời gọi checkpoint. Nếu checkpoint được yêu cầu từ bên ngoài, hãy đặt log trong các `Resource` callback và ở các điểm xử lý nghiệp vụ quan trọng để quan sát quá trình phục hồi của từng thread.

Log cần phân biệt được các mốc khởi động ban đầu, chuẩn bị checkpoint, phục hồi resource và readiness. Có thể bổ sung định danh instance được cấp mới sau restore để phân biệt các bản restore. Tránh dùng một giá trị định danh đã tạo trước checkpoint làm định danh duy nhất cho mọi bản sao được restore.

## 8. Một checkpoint có thể tạo ra nhiều điểm tiếp tục độc lập

Trong môi trường triển khai, một checkpoint có thể được dùng làm nguồn để khởi chạy nhiều tiến trình đã restore. Mỗi tiến trình bắt đầu từ trạng thái được lưu và tiếp tục tại cùng điểm thực thi trong snapshot, nhưng sau đó hoạt động như một process độc lập.

Điều này có hệ quả quan trọng: trạng thái trong checkpoint có thể được nhân bản. Nếu snapshot chứa một instance ID, một lease, một bộ đếm cục bộ hoặc trạng thái scheduler, nhiều bản restore có thể bắt đầu với cùng giá trị đó. Nếu mỗi bản restore tiếp tục thực hiện một side effect như gửi message, chạy tác vụ định kỳ hoặc ghi dữ liệu, side effect có thể xảy ra ở nhiều instance.

Vì vậy, phần mã sau restore và callback `afterRestore` cần xem xét các thao tác phụ thuộc danh tính hoặc quyền sở hữu instance:

- Tạo hoặc đăng ký định danh instance mới theo môi trường triển khai.
- Lấy lại lease hoặc quyền leader bằng cơ chế phối hợp bên ngoài.
- Tham gia lại consumer group và để broker phân phối partition theo trạng thái hiện tại.
- Khởi động scheduler theo chính sách chạy trên một hoặc nhiều instance.
- Đảm bảo thao tác có thể được retry hoặc có idempotency key phù hợp khi có khả năng thực thi lặp.

Không nên giả định rằng một đoạn mã sau checkpoint chỉ chạy một lần trên toàn hệ thống. Nó có thể chạy một lần trong từng tiến trình được restore từ cùng snapshot. Tính duy nhất phải được bảo đảm bởi hệ thống phân tán hoặc cơ chế cấp phát bên ngoài, không thể chỉ dựa vào biến trong heap đã checkpoint.

## 9. Các nhầm lẫn thường gặp

### Nghĩ rằng restore gọi lại `main()`

Đây là nhầm lẫn phổ biến nhất. Restore phục hồi tiến trình đã lưu và tiếp tục các thread. Nó không khởi chạy lại ứng dụng từ đầu. Hãy đặt công việc sau restore ở resource callback hoặc tại điểm tiếp tục phù hợp.

### Nghĩ rằng static initializer sẽ chạy lại

Static initializer đã chạy trước checkpoint và trạng thái lớp được lưu trong checkpoint. Restore phục hồi trạng thái đó. Nếu một giá trị static phụ thuộc môi trường đã thay đổi, hãy làm mới nó một cách tường minh sau restore.

### Nghĩ rằng `@PostConstruct` và startup runner sẽ chạy lại

Các callback này thuộc quá trình tạo bean và khởi động context. Nếu context được phục hồi từ checkpoint, chúng không tự được thực hiện lại như trong lần khởi động lạnh. Thành phần cần phục hồi kết nối hoặc tài nguyên nên tham gia vòng đời CRaC.

### Nghĩ rằng `finally` hoặc shutdown hook sẽ dọn tài nguyên

Checkpoint không phải thao tác unwind stack hoặc shutdown thông thường. Dùng `beforeCheckpoint` để chuẩn bị tài nguyên và `afterRestore` để phục hồi tài nguyên.

### Nghĩ rằng một log ở đầu `main()` chứng minh restore đã khởi động lại ứng dụng

Log đó có thể chỉ xuất hiện ở lần khởi động ban đầu. Hãy thêm marker tại điểm tiếp tục sau checkpoint, trong callback phục hồi và tại readiness để quan sát đúng trình tự.

### Nghĩ rằng một side effect sau checkpoint chỉ xảy ra một lần

Nếu nhiều tiến trình được restore từ cùng snapshot, mỗi tiến trình có thể chạy tiếp cùng đoạn mã. Hãy thiết kế thao tác phân tán theo hướng idempotent hoặc sử dụng cơ chế phân quyền phù hợp.

## 10. Cách suy luận khi debug một ứng dụng CRaC

Khi một log xuất hiện nhiều lần hoặc một đoạn mã dường như không chạy sau restore, hãy xác định bốn thông tin:

1. Checkpoint được yêu cầu từ API trong ứng dụng hay từ công cụ bên ngoài?
2. Thread nào đang thực thi tại thời điểm checkpoint và stack của thread đó ở đâu?
3. `main()` còn đang hoạt động hay đã trả về trước checkpoint?
4. Sau restore, resource callback nào đã chạy và điều kiện readiness đã được thỏa mãn chưa?

Sau đó đối chiếu log với điểm tiếp tục thực tế. Với checkpoint được gọi trong mã nguồn, kiểm tra câu lệnh ngay sau lời gọi. Với checkpoint từ bên ngoài, kiểm tra stack của các thread và vị trí chúng tiếp tục. Nếu `main()` đã kết thúc, hãy theo dõi thread server, worker hoặc scheduler còn sống thay vì chờ `main()` xuất hiện lần nữa.

Để kiểm chứng hành vi, nên quan sát ít nhất hai kịch bản: checkpoint được gọi trực tiếp bằng `Core.checkpointRestore()` và checkpoint được yêu cầu từ bên ngoài khi ứng dụng đang hoạt động. Ghi log trước/sau điểm gọi, trong `beforeCheckpoint`, trong `afterRestore` và tại readiness. Đồng thời kiểm tra các dependency bên ngoài sau restore để chắc chắn trạng thái bộ nhớ được phục hồi không bị nhầm với trạng thái kết nối còn hợp lệ.

## 11. Kết luận

Điểm tiếp tục thực thi là chìa khóa để hiểu vòng đời `main()` trong CRaC. Khởi động lạnh gọi `main()` để bắt đầu một chương trình mới; restore phục hồi tiến trình đã lưu và tiếp tục các thread từ trạng thái checkpoint. Nếu checkpoint xảy ra tại `Core.checkpointRestore()`, luồng gọi tiếp tục sau lời gọi đó khi restore hoàn tất. Nếu checkpoint được yêu cầu từ bên ngoài, thread tiếp tục từ trạng thái thực thi đã lưu. Nếu `main()` đã trả về, nó vẫn ở trạng thái kết thúc và các thread còn sống khác tiếp tục công việc.

Khi thiết kế và debug, hãy phân biệt rõ mã khởi động ban đầu, callback chuẩn bị checkpoint, callback phục hồi và mã sau điểm tiếp tục. Những thành phần cần kết nối lại, làm mới lease hoặc tạo định danh mới phải xử lý theo vòng đời CRaC. Cách quan sát này giúp tránh chạy lặp logic khởi tạo, bỏ sót phục hồi tài nguyên và tạo side effect trùng lặp khi nhiều tiến trình được restore từ cùng checkpoint.
