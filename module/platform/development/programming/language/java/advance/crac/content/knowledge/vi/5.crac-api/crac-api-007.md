# Thứ tự callback: ngược thứ tự đăng ký trước checkpoint, thuận sau restore

CRaC (Coordinated Restore at Checkpoint) cho phép ứng dụng chuẩn bị tài nguyên trước khi JVM chụp checkpoint và khôi phục tài nguyên sau khi tiến trình được restore. Một ứng dụng thực tế thường có nhiều thành phần phụ thuộc lẫn nhau: HTTP server dùng service, service dùng connection pool, connection pool dùng cấu hình và credential. Nếu đóng các thành phần sai thứ tự, ứng dụng có thể để request tiếp tục chạy trên một connection đã đóng hoặc mở listener trước khi dependency sẵn sàng.

CRaC quy định thứ tự callback theo thứ tự đăng ký resource trong cùng một context:

- **Trước checkpoint (beforeCheckpoint)**: gọi theo thứ tự ngược với thứ tự đăng ký.
- **Sau restore (afterRestore)**: gọi theo đúng thứ tự đăng ký.

Quy tắc này hỗ trợ một vòng đời có tính đối xứng: khởi tạo dependency trước, thành phần phụ thuộc sau; khi checkpoint thì dừng thành phần phụ thuộc trước, dependency sau; khi restore thì khôi phục dependency trước rồi mới khởi động thành phần phụ thuộc.

## 1. Quy tắc thứ tự callback

Giả sử ứng dụng đăng ký ba resource theo trình tự:

    1. DatabasePool
    2. OrderService
    3. HttpServer

Trong đó:

- **OrderService** cần **DatabasePool** để xử lý nghiệp vụ.
- **HttpServer** gọi **OrderService** khi nhận request.

CRaC gọi callback như sau:

    Thứ tự đăng ký
        DatabasePool
            ↓
        OrderService
            ↓
        HttpServer

    Trước checkpoint: beforeCheckpoint (đảo ngược)
        HttpServer
            ↓
        OrderService
            ↓
        DatabasePool

    Sau restore: afterRestore (thuận)
        DatabasePool
            ↓
        OrderService
            ↓
        HttpServer

Có thể nhớ bằng hai quy tắc:

| Giai đoạn | Thứ tự | Mục đích |
|---|---|---|
| Khởi tạo và đăng ký | Dependency trước, thành phần phụ thuộc sau | Thành phần sau có thể sử dụng thành phần trước |
| beforeCheckpoint | Thành phần phụ thuộc trước, dependency sau | Ngừng traffic và công việc trước khi đóng tài nguyên nền |
| afterRestore | Dependency trước, thành phần phụ thuộc sau | Tạo lại nền tảng trước khi mở hoạt động bên ngoài |

Ví dụ, HTTP server nên ngừng nhận request trước khi service dừng. Service nên hoàn tất công việc đang chạy trước khi database pool đóng. Sau restore, database pool cần sẵn sàng trước khi service khởi động; HTTP server chỉ nên nhận request sau khi service đã sẵn sàng.

## 2. Thứ tự được xác định tại thời điểm đăng ký

Resource được đăng ký với một **Context**, thường là global context lấy từ **Core.getGlobalContext()**:

    Core.getGlobalContext().register(databasePool);
    Core.getGlobalContext().register(orderService);
    Core.getGlobalContext().register(httpServer);

Thứ tự callback dựa trên **thứ tự các lần gọi register(...) thực tế**, không dựa vào:

- Tên class hoặc tên biến.
- Thứ tự file trong source code.
- Thứ tự alphabet của package.
- Mức độ quan trọng của resource.
- Suy luận dependency tự động từ object reference.

Nếu một framework tạo bean theo thứ tự khác với dự kiến, thứ tự đăng ký cũng có thể khác. Nếu resource được đăng ký từ các thread khởi tạo song song, trình tự đăng ký có thể không ổn định. Với các resource có quan hệ phụ thuộc, hãy thiết kế một trình tự bootstrap rõ ràng và đăng ký theo trình tự đó.

### 2.1. Đăng ký theo thứ tự khởi tạo thành công

Một resource nên được đăng ký sau khi nó đã khởi tạo thành công và sẵn sàng tham gia vòng đời checkpoint/restore. Ví dụ, nếu database pool mở kết nối thất bại thì không nên để một resource chưa hoạt động được đăng ký như thể nó đã sẵn sàng.

Mẫu ý tưởng:

    DatabasePool databasePool = DatabasePool.open(configuration);
    Core.getGlobalContext().register(databasePool);

    OrderService orderService = OrderService.start(databasePool);
    Core.getGlobalContext().register(orderService);

    HttpServer httpServer = HttpServer.start(orderService);
    Core.getGlobalContext().register(httpServer);

Đây là mã minh họa cho trình tự. Cách tạo và đóng từng resource phụ thuộc thư viện thực tế. Điểm cần giữ là resource nền được tạo và đăng ký trước resource sử dụng nó.

Nếu resource tự đăng ký trong constructor, hãy bảo đảm việc tạo object và đăng ký không xảy ra trước khi resource thực sự có trạng thái hợp lệ. Một constructor chỉ lưu field nhưng chưa mở kết nối có thể làm cho thứ tự đăng ký không phản ánh đúng thứ tự sẵn sàng của hệ thống.

## 3. Ví dụ nhỏ quan sát thứ tự callback

Có thể quan sát quy tắc bằng một resource chỉ ghi log. Ví dụ không cần database hoặc web framework; mục tiêu là xác nhận trình tự do CRaC thực hiện.

### 3.1. Resource ghi log

Tạo class **TraceResource.java**:

    package com.example.crac;

    import org.crac.Context;
    import org.crac.Core;
    import org.crac.Resource;

    public final class TraceResource implements Resource {

        private final String name;

        public TraceResource(String name) {
            this.name = name;
            Core.getGlobalContext().register(this);
            System.out.println("registered: " + name);
        }

        @Override
        public void beforeCheckpoint(Context<? extends Resource> context) {
            System.out.println("beforeCheckpoint: " + name);
        }

        @Override
        public void afterRestore(Context<? extends Resource> context) {
            System.out.println("afterRestore: " + name);
        }
    }

Mỗi instance giữ một tên để log cho biết callback thuộc resource nào. Constructor đăng ký instance vào global context ngay khi được tạo. Trong ví dụ này, resource chỉ ghi log nên việc đăng ký ngay trong constructor không tạo ra tài nguyên bên ngoài chưa sẵn sàng.

### 3.2. Đăng ký theo thứ tự dependency

Tạo class **CallbackOrderApplication.java**:

    package com.example.crac;

    import java.util.concurrent.CountDownLatch;

    public final class CallbackOrderApplication {

        private CallbackOrderApplication() {
        }

        public static void main(String[] args) throws InterruptedException {
            // Khởi tạo dependency trước, thành phần phụ thuộc sau.
            new TraceResource("DatabasePool");
            new TraceResource("OrderService");
            new TraceResource("HttpServer");

            System.out.println("READY: waiting for checkpoint");

            // Giữ JVM sống để có thể yêu cầu checkpoint bằng jcmd.
            new CountDownLatch(1).await();
        }
    }

Khi ứng dụng khởi động, log đăng ký dự kiến:

    registered: DatabasePool
    registered: OrderService
    registered: HttpServer
    READY: waiting for checkpoint

Sau đó yêu cầu JVM checkpoint bằng CRaC-enabled JDK. Trong giai đoạn chuẩn bị checkpoint, log callback dự kiến:

    beforeCheckpoint: HttpServer
    beforeCheckpoint: OrderService
    beforeCheckpoint: DatabasePool

Khi restore checkpoint, log dự kiến:

    afterRestore: DatabasePool
    afterRestore: OrderService
    afterRestore: HttpServer

Ví dụ xác nhận trực tiếp quan hệ đảo ngược/thuận giữa hai giai đoạn. Việc gọi các callback do CRaC runtime điều phối; không gọi trực tiếp method để giả lập checkpoint hoặc restore.

## 4. Vì sao thứ tự này phù hợp với dependency?

### 4.1. Trước checkpoint: dừng từ ngoài vào trong

Một hệ thống thường nhận công việc từ các thành phần ở biên, sau đó đi vào service và tài nguyên nền. Trình tự dừng cần đi ngược đường đi đó.

Với ví dụ HTTP server, service và database pool:

1. **HTTP server** ngừng nhận request mới. Nếu có request đang xử lý, ứng dụng cần cho chúng hoàn tất hoặc xử lý theo chính sách dừng đã thiết kế.
2. **OrderService** ngừng nhận công việc mới và hoàn tất các thao tác đang dùng database.
3. **DatabasePool** đóng connection sau khi service không còn sử dụng chúng.

Nếu đóng database pool trước HTTP server, một request mới có thể đến trong lúc service vẫn đang xử lý và gặp lỗi connection. Nếu dừng service trước HTTP server mà server vẫn nhận request, request có thể gọi vào service đã ngừng hoạt động.

### 4.2. Sau restore: khôi phục từ trong ra ngoài

Sau restore, thứ tự cần đảo lại:

1. **DatabasePool** tạo lại connection và xác nhận có thể sử dụng.
2. **OrderService** khôi phục trạng thái hoạt động, cache hoặc dependency cần thiết.
3. **HTTP server** mở listener để nhận request.

Nếu HTTP server mở trước database pool, ứng dụng có thể nhận traffic trong lúc database chưa sẵn sàng. Nếu service khởi động trước dependency, lần gọi đầu tiên có thể thất bại hoặc để lộ trạng thái chưa hoàn chỉnh.

### 4.3. Bảng đối chiếu vòng đời

| Resource | Trước checkpoint | Sau restore |
|---|---|---|
| DatabasePool | Đóng connection sau khi consumer đã dừng | Tạo và kiểm tra connection |
| OrderService | Ngừng nhận việc, chờ xử lý dở dang | Khôi phục service và dependency |
| HttpServer | Ngừng nhận request, đóng listener | Mở listener sau cùng |

Quy tắc callback tạo ra đúng thứ tự này nếu trình tự đăng ký phản ánh đúng trình tự khởi tạo dependency.

## 5. Thiết kế thứ tự trong ứng dụng nhiều resource

Trong ứng dụng thực tế có thể có nhiều loại resource hơn ba thành phần trong ví dụ. Hãy vẽ quan hệ phụ thuộc trước khi quyết định thứ tự đăng ký.

Ví dụ:

    Configuration
        ├── DatabasePool
        │      └── OrderService
        │              └── HttpServer
        │
        ├── MessageConsumer
        │      └── EventHandler
        │
        └── CredentialProvider
               ├── DatabasePool
               └── ExternalApiClient

Sơ đồ này cho thấy một số thành phần có thể độc lập, một số thành phần chia sẻ dependency. Trong cùng một context, chọn trình tự đăng ký sao cho mỗi dependency được đăng ký trước các resource sử dụng nó. Khi checkpoint, thứ tự đảo ngược sẽ dừng các resource phụ thuộc trước; khi restore, thứ tự đăng ký sẽ khôi phục dependency trước.

Một thứ tự có thể là:

    1. Configuration
    2. CredentialProvider
    3. DatabasePool
    4. ExternalApiClient
    5. OrderService
    6. MessageConsumer
    7. EventHandler
    8. HttpServer

Đây chỉ là một thứ tự minh họa cho sơ đồ trên. Nếu dependency graph có nhiều nhánh, có thể có nhiều thứ tự hợp lệ. Điều quan trọng là mọi quan hệ phụ thuộc phải được tôn trọng. Ví dụ, cả **DatabasePool** và **ExternalApiClient** phải sẵn sàng trước **OrderService** nếu service sử dụng cả hai.

### 5.1. Khi có nhiều resource độc lập

Hai resource không phụ thuộc nhau có thể được đăng ký theo một thứ tự xác định bất kỳ, miễn là thứ tự đó được giữ ổn định và không tạo ra quan hệ giả. Dù vậy, vẫn nên chọn thứ tự nhất quán để log dễ đọc và kết quả vận hành có thể dự đoán.

Không nên dựa vào thứ tự ngẫu nhiên của collection, hash map hoặc thread race để quyết định thứ tự đăng ký. Nếu thứ tự có ý nghĩa với checkpoint, hãy dùng một trình tự bootstrap tường minh.

### 5.2. Khi dependency graph thay đổi

Nếu một service bắt đầu sử dụng thêm resource mới, cần xem lại trình tự khởi tạo và đăng ký. Ví dụ, **OrderService** trước đây chỉ dùng database nhưng nay còn gọi **ExternalApiClient**; cả hai dependency phải được khởi tạo trước service.

Thay đổi thứ tự đăng ký có thể thay đổi cả hai giai đoạn callback. Vì vậy, review thay đổi bootstrap nên xem xét ảnh hưởng đến **beforeCheckpoint** và **afterRestore**, không chỉ ảnh hưởng lúc ứng dụng khởi động bình thường.

## 6. Đăng ký resource trong framework và ứng dụng đa luồng

Framework có thể tạo resource thông qua dependency injection, lifecycle hook, auto-configuration hoặc callback khởi động. Thứ tự khởi tạo bean không nên được suy ra từ tên class hoặc thứ tự khai báo trong file cấu hình nếu framework không cam kết điều đó.

Với Spring hoặc framework tương tự, nên có một thành phần quản lý vòng đời CRaC rõ ràng:

- Xác định các bean nào cần tham gia checkpoint/restore.
- Chờ bean khởi tạo thành công trước khi đăng ký resource tương ứng.
- Đăng ký theo thứ tự dependency được xác định rõ.
- Ghi log thứ tự đăng ký để chẩn đoán.
- Tránh đăng ký lặp cùng một resource qua nhiều lifecycle hook.

Nếu nhiều thread cùng đăng ký resource, thứ tự thực tế có thể phụ thuộc lịch thực thi của thread. Khi callback cần một thứ tự cụ thể, hãy gom đăng ký vào một giai đoạn tuần tự hoặc một coordinator duy nhất.

Một cách tổ chức dễ kiểm soát là tạo các resource nền trước, sau đó đăng ký từng tầng:

    Bootstrap
      ├── Tạo và đăng ký các dependency nền
      ├── Tạo và đăng ký service sử dụng dependency
      └── Tạo và đăng ký listener/consumer ở biên
              ↓
          Ứng dụng READY

Không nên đánh dấu ứng dụng sẵn sàng nhận traffic trước khi mọi dependency cần thiết đã được tạo và đăng ký thành công.

## 7. Callback cần an toàn khi đóng và khôi phục

Thứ tự đúng là điều kiện quan trọng, nhưng bản thân callback vẫn cần được triển khai an toàn.

### 7.1. beforeCheckpoint

Callback trước checkpoint nên:

- Ngừng nhận công việc mới ở thành phần biên.
- Chờ hoặc xử lý request/message đang chạy theo chính sách của ứng dụng.
- Dừng scheduler hoặc consumer để tránh phát sinh công việc mới.
- Đóng connection, socket và file handle cần tạo lại sau restore.
- Ghi log kết quả đóng resource để có thể xác định bước thất bại.

Không nên đóng một dependency khi vẫn còn resource khác đang sử dụng nó. Nếu không thể dừng công việc trong thời gian cho phép, cần xử lý timeout và báo lỗi phù hợp; không nên giả vờ rằng resource đã sẵn sàng cho checkpoint.

### 7.2. afterRestore

Callback sau restore nên:

- Tạo lại các kết nối và tài nguyên phụ thuộc hệ điều hành.
- Xác thực trạng thái kết nối thay vì chỉ kiểm tra object reference còn tồn tại.
- Làm mới credential hoặc token đã hết hạn nếu cần.
- Khôi phục consumer/scheduler theo chính sách tránh xử lý trùng.
- Chỉ mở listener hoặc nhận công việc khi dependency đã sẵn sàng.

Object Java còn tồn tại sau restore không có nghĩa socket, database session hoặc lease bên ngoài vẫn hợp lệ. Callback cần phục hồi những tài nguyên có vòng đời do hệ điều hành hoặc hệ thống bên ngoài quản lý.

### 7.3. Tính idempotent và xử lý lỗi

Callback có thể gặp lỗi do hệ thống bên ngoài không sẵn sàng, credential hết hạn hoặc tài nguyên không thể mở lại. Hãy thiết kế thao tác đóng/mở để kiểm tra trạng thái hiện tại trước khi thực hiện, tránh đóng hai lần hoặc tạo nhiều listener/pool trùng nhau.

Nếu callback thất bại, thao tác checkpoint/restore có thể không hoàn tất như mong đợi. Hãy để lỗi được báo cáo rõ ràng, ghi log resource và giai đoạn xảy ra lỗi. Không nuốt exception rồi tiếp tục coi ứng dụng đã sẵn sàng. Cũng không nên dựa vào giả định rằng CRaC sẽ tự động rollback mọi callback đã chạy trước callback thất bại; hãy thiết kế trạng thái lỗi và quy trình phục hồi rõ ràng.

## 8. Cách kiểm chứng thứ tự callback

Có thể kiểm chứng bằng log của ví dụ **TraceResource**:

1. Chạy ứng dụng bằng CRaC-enabled JDK.
2. Xác nhận log đăng ký xuất hiện theo thứ tự **DatabasePool**, **OrderService**, **HttpServer**.
3. Dùng **jcmd -l** để tìm PID của ứng dụng.
4. Gửi lệnh **jcmd <PID> JDK.checkpoint**.
5. Đọc log **beforeCheckpoint** và xác nhận thứ tự **HttpServer**, **OrderService**, **DatabasePool**.
6. Restore checkpoint bằng đúng JDK tương thích.
7. Đọc log **afterRestore** và xác nhận thứ tự **DatabasePool**, **OrderService**, **HttpServer**.

Ví dụ lệnh ở Linux, với thư mục checkpoint mới:

    java -XX:CRaCCheckpointTo="$PWD/checkpoint-order" \
         -cp target/classes:target/dependency/* \
         com.example.crac.CallbackOrderApplication

Từ terminal khác:

    jcmd -l
    jcmd <PID> JDK.checkpoint

Sau khi checkpoint hoàn tất:

    java -XX:CRaCRestoreFrom="$PWD/checkpoint-order"

Đường dẫn classpath trong ví dụ giả định class và dependency đã được chuẩn bị ở các thư mục tương ứng; hãy điều chỉnh theo cấu trúc build của dự án. Quan trọng là cả checkpoint và restore đều dùng CRaC-enabled JDK phù hợp với môi trường đã tạo checkpoint.

### 8.1. Bằng chứng cần lưu

Khi kiểm tra thứ tự callback trong dự án thật, lưu lại:

- Thứ tự resource được đăng ký.
- Log từng callback, bao gồm tên resource và giai đoạn.
- Kết quả checkpoint và restore.
- Kết quả health check sau restore.
- Phiên bản JDK/CRaC và môi trường thực thi.

Nếu log cho thấy thứ tự khác dự kiến, hãy kiểm tra nơi gọi **register**, lifecycle hook nào gọi trước, có đăng ký từ thread khác hay không và có đăng ký trùng hay không. Đừng suy luận thứ tự từ sơ đồ dependency nếu chưa xác nhận trình tự đăng ký thực tế.

## 9. Những hiểu lầm thường gặp

### Nghĩ rằng beforeCheckpoint chạy theo thứ tự đăng ký

Nếu đăng ký database, service, server thì **beforeCheckpoint** chạy server, service, database. Dùng thứ tự thuận ở giai đoạn này có thể đóng dependency khi consumer vẫn còn hoạt động.

### Nghĩ rằng afterRestore chạy ngược thứ tự đăng ký

**afterRestore** chạy database, service, server theo thứ tự đăng ký ban đầu. Đây là trình tự cần thiết để thành phần phụ thuộc chỉ khởi động sau khi dependency đã sẵn sàng.

### Nghĩ rằng CRaC tự phân tích dependency graph

CRaC thực hiện theo thứ tự đăng ký trong context. Runtime không tự đọc object reference để biết service nào phụ thuộc database hoặc server nào phụ thuộc service. Ứng dụng chịu trách nhiệm đăng ký đúng thứ tự.

### Nghĩ rằng thứ tự khởi tạo bean luôn là thứ tự đăng ký

Framework có thể khởi tạo bean theo dependency injection, lazy initialization, parallel initialization hoặc lifecycle hook. Chỉ thứ tự gọi **Context.register(...)** mới quyết định thứ tự callback trong context tương ứng.

### Nghĩ rằng callback có thể thay thế mọi thao tác shutdown

Callback không tự động hiểu cách dừng request, hoàn tất transaction, xác nhận message hoặc đóng pool của từng thư viện. Ứng dụng phải triển khai logic phù hợp với từng resource.

## 10. Nguyên tắc thiết kế cần ghi nhớ

Khi tích hợp CRaC, hãy xác định dependency graph và thứ tự khởi tạo thành công trước. Đăng ký resource theo thứ tự đó trong context. CRaC sẽ gọi **beforeCheckpoint** theo thứ tự ngược để dừng thành phần phụ thuộc trước, rồi gọi **afterRestore** theo thứ tự thuận để khôi phục dependency trước.

Với ví dụ **DatabasePool → OrderService → HttpServer**, trình tự đầy đủ là:

    Khởi tạo/đăng ký:
    DatabasePool → OrderService → HttpServer

    beforeCheckpoint:
    HttpServer → OrderService → DatabasePool

    afterRestore:
    DatabasePool → OrderService → HttpServer

Hãy giữ thứ tự đăng ký ổn định, ghi log để kiểm chứng và xử lý lỗi callback rõ ràng. Như vậy, ứng dụng có thể dừng theo chiều từ biên vào dependency và khôi phục theo chiều từ dependency ra biên, giảm nguy cơ thành phần hoạt động khi tài nguyên mà nó cần chưa sẵn sàng.

