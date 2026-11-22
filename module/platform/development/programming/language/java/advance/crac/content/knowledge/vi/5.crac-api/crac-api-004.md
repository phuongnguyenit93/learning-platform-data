# Core.getGlobalContext() và Context.register()

Trong Java CRaC, ứng dụng cần thông báo cho runtime về những tài nguyên phải được chuẩn bị trước checkpoint và khôi phục sau restore. Một connection tới database, socket tới message broker, consumer đang nhận thông điệp hoặc client giữ phiên làm việc đều có vòng đời riêng. Chúng có thể không còn hợp lệ sau khi tiến trình được khôi phục, dù các đối tượng Java đại diện cho chúng vẫn còn trong heap.

API `org.crac` cung cấp cơ chế đăng ký các tài nguyên này. `Core.getGlobalContext()` lấy context toàn cục của CRaC trong JVM hiện tại. Phương thức `Context.register()` đưa một đối tượng triển khai `Resource` vào context để runtime gọi các callback vòng đời của đối tượng đó. Hai API thường được dùng cùng nhau:

~~~java
Core.getGlobalContext().register(myResource);
~~~

Dòng lệnh này đăng ký `myResource` với vòng đời checkpoint/restore của JVM. Nó không tự đóng kết nối, không tự mở lại kết nối và cũng không lưu dữ liệu nghiệp vụ. Những hành động đó phải được triển khai trong `Resource.beforeCheckpoint()` và `Resource.afterRestore()`.

## 1. Vai trò của Core.getGlobalContext()

`Core` là điểm truy cập API điều khiển CRaC. Phương thức tĩnh `Core.getGlobalContext()` trả về context toàn cục dùng để đăng ký các resource mà ứng dụng muốn CRaC thông báo khi checkpoint và restore.

Ví dụ:

~~~java
import org.crac.Core;

// Lấy context toàn cục của CRaC trong JVM hiện tại.
var context = Core.getGlobalContext();
~~~

Từ context này, ứng dụng có thể đăng ký các đối tượng triển khai `Resource`:

~~~java
context.register(databaseResource);
context.register(brokerResource);
context.register(fileResource);
~~~

Tên gọi *global context* cần được hiểu trong phạm vi JVM. Nó là context chung của ứng dụng đang chạy trong tiến trình đó, giúp tập trung đăng ký những resource cần tham gia vòng đời CRaC. Nó không phải một registry toàn cụm, không được chia sẻ giữa các JVM và không tự đăng ký tài nguyên với database, service discovery hay message broker.

Nếu ứng dụng chạy nhiều replica, mỗi replica có tiến trình JVM và vòng đời riêng. Mỗi JVM phải quản lý resource của chính nó. Một resource đã đăng ký trong JVM này không đại diện cho kết nối hoặc trạng thái của JVM khác.

`Core.getGlobalContext()` chỉ cung cấp context. Việc gọi phương thức này không làm ứng dụng checkpoint ngay lập tức, không tạo một checkpoint và không tự động kiểm tra mọi tài nguyên đang mở. Runtime chỉ biết những resource được đăng ký hoặc được tích hợp thông qua cơ chế tương ứng.

## 2. Context và phương thức register()

`Context` là nơi tập hợp các đối tượng `Resource` cần được thông báo trong vòng đời checkpoint/restore. Phương thức `register()` nhận một resource và đăng ký resource đó với context:

~~~java
Context<Resource> context = Core.getGlobalContext();
context.register(resource);
~~~

Trong ví dụ này:

- `Core.getGlobalContext()` lấy context toàn cục.
- `Context<Resource>` biểu diễn context có thể đăng ký các đối tượng thuộc kiểu `Resource`.
- `register(resource)` đưa đối tượng vào danh sách resource mà context quản lý.
- Đối tượng được đăng ký phải triển khai `org.crac.Resource` và cung cấp các callback theo hợp đồng của API.

Đăng ký là bước kết nối đối tượng với vòng đời CRaC. Bản thân `register()` không gọi `beforeCheckpoint()` ngay tại thời điểm đăng ký và cũng không gọi `afterRestore()` ngay lập tức. Các callback được runtime gọi khi tiến trình đi qua các giai đoạn tương ứng.

Vì vậy, hãy đăng ký resource trong quá trình khởi tạo ứng dụng, sau khi đối tượng đã được tạo và sẵn sàng quản lý tài nguyên, đồng thời bảo đảm việc đăng ký hoàn tất trước khi checkpoint bắt đầu. Không nên đợi đến lúc checkpoint đang diễn ra mới tìm và đăng ký các resource quan trọng.

### 2.1. Đối tượng nào cần đăng ký?

Hãy đăng ký đối tượng chịu trách nhiệm quản lý vòng đời của một tài nguyên cần chuẩn bị hoặc tái tạo. Ví dụ:

| Resource | Công việc trước checkpoint | Công việc sau restore |
|---|---|---|
| Database connection pool | Ngừng cấp connection mới, chờ thao tác đang chạy và đóng pool | Tạo pool mới và kiểm tra khả năng kết nối |
| Message consumer | Ngừng nhận thông điệp, hoàn tất hoặc trả lại công việc đang giữ, đóng consumer | Tạo consumer mới và đăng ký subscription |
| Socket tới dịch vụ bên ngoài | Dừng trao đổi dữ liệu và đóng socket | Mở kết nối mới, xác thực và khôi phục giao thức |
| Tệp đang được ghi | Hoàn tất thao tác ghi, flush và đóng tệp | Mở lại tệp, kiểm tra trạng thái rồi tiếp tục |
| Client giữ session hoặc token | Dừng sử dụng session cũ và giải phóng tài nguyên liên quan | Xác thực lại hoặc làm mới token, tạo session mới |

Không phải mọi đối tượng Java đều cần đăng ký. Một đối tượng chỉ chứa dữ liệu bất biến hoặc dữ liệu thuần trong heap có thể không cần callback riêng. Hãy tập trung vào tài nguyên có vòng đời bên ngoài JVM, tài nguyên native hoặc trạng thái cần được xác minh sau restore.

Nếu một thư viện đã cung cấp tích hợp CRaC và tự đăng ký tài nguyên của nó, hãy dùng cơ chế được thư viện hỗ trợ. Tránh đăng ký thêm một resource khác để đóng cùng tài nguyên nếu việc đó có thể khiến tài nguyên bị đóng lặp hoặc hai callback quản lý cùng một trạng thái.

## 3. Resource và hai callback vòng đời

Đối tượng đăng ký với context thường triển khai interface `org.crac.Resource`. Interface này định nghĩa hai callback chính:

~~~java
void beforeCheckpoint(Context<? extends Resource> context) throws Exception;
void afterRestore(Context<? extends Resource> context) throws Exception;
~~~

`beforeCheckpoint()` được gọi khi CRaC chuẩn bị checkpoint. Resource dùng callback này để đưa tài nguyên về trạng thái an toàn: dừng nhận công việc mới, hoàn tất hoặc hủy thao tác đang chạy theo chính sách, flush dữ liệu cần thiết và đóng kết nối không thể tiếp tục sử dụng an toàn.

`afterRestore()` được gọi khi tiến trình được restore. Resource dùng callback này để tạo lại kết nối, làm mới thông tin xác thực, khôi phục subscription và kiểm tra các phụ thuộc bên ngoài.

Tham số `Context<? extends Resource>` là context gắn với lần thông báo callback. Trong một triển khai đơn giản, resource có thể không cần sử dụng tham số này, nhưng vẫn phải khai báo đúng chữ ký phương thức theo interface.

Một triển khai tối thiểu:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class ExampleResource implements Resource {

    public ExampleResource() {
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        System.out.println("Prepare resource before checkpoint");
        // Dừng công việc và giải phóng tài nguyên tại đây.
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        System.out.println("Restore resource after checkpoint");
        // Tạo lại tài nguyên và kiểm tra phụ thuộc tại đây.
    }
}
~~~

Constructor đăng ký chính đối tượng vừa được tạo. Sau khi ứng dụng khởi tạo `ExampleResource`, CRaC có thể gọi hai callback khi tiến trình đi qua vòng đời checkpoint/restore.

Ví dụ này chỉ minh họa cách đăng ký và chữ ký callback. Ứng dụng thực tế phải thay các câu lệnh in ra bằng thao tác quản lý tài nguyên cụ thể. Việc ghi log không làm cho socket, connection pool hoặc session trở nên an toàn khi restore.

## 4. Ví dụ: đăng ký resource quản lý socket

Giả sử ứng dụng duy trì một socket kết nối tới dịch vụ bên ngoài. Khi JVM bị dừng để checkpoint, phía máy chủ có thể đóng kết nối do timeout hoặc chính sách mạng. Sau restore, socket cũ không nên được coi là một kết nối còn hoạt động. Resource cần đóng socket trước checkpoint và mở kết nối mới sau restore.

~~~java
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.Socket;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class ServiceSocketResource implements Resource {
    private final String host;
    private final int port;
    private Socket socket;

    public ServiceSocketResource(String host, int port)
            throws IOException {
        this.host = host;
        this.port = port;

        // Tạo tài nguyên ban đầu.
        connect();

        // Đăng ký vòng đời của tài nguyên với CRaC.
        Core.getGlobalContext().register(this);
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws IOException {
        closeSocket();
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws IOException {
        connect();
    }

    private void connect() throws IOException {
        Socket candidate = new Socket();
        try {
            candidate.connect(
                    new InetSocketAddress(host, port),
                    5_000
            );
            socket = candidate;
        } catch (IOException error) {
            try {
                candidate.close();
            } catch (IOException closeError) {
                error.addSuppressed(closeError);
            }
            throw error;
        }
    }

    private void closeSocket() throws IOException {
        Socket current = socket;
        socket = null;

        if (current != null) {
            current.close();
        }
    }
}
~~~

Trong ví dụ:

1. Constructor nhận địa chỉ dịch vụ và tạo kết nối ban đầu.
2. Sau khi kết nối được tạo, `Core.getGlobalContext().register(this)` đăng ký resource với context toàn cục.
3. Khi chuẩn bị checkpoint, `beforeCheckpoint()` đóng socket hiện tại và bỏ tham chiếu tới socket đó.
4. Khi restore, `afterRestore()` gọi `connect()` để tạo socket mới.

Đoạn mã thể hiện vòng đời cơ bản của một socket. Giao thức thực tế có thể cần thêm bước xác thực, handshake, đăng ký client, khôi phục subscription hoặc đồng bộ trạng thái ứng dụng sau khi kết nối được mở. Những bước đó cần nằm trong quy trình phục hồi tương ứng.

Ngoài ra, đóng socket không tự bảo đảm rằng không còn thread khác đang sử dụng socket. Trước khi callback đóng tài nguyên, ứng dụng cần ngừng nhận công việc mới và chờ các thao tác đang chạy kết thúc theo thời hạn phù hợp. Việc đồng bộ ở cấp phương thức chỉ bảo vệ các phương thức trong ví dụ; nó không thay thế cơ chế drain request của toàn ứng dụng.

## 5. Thứ tự đăng ký và thứ tự callback

Thứ tự đăng ký có ý nghĩa khi nhiều resource phụ thuộc vào nhau. Theo quy tắc của CRaC Context, các resource trong cùng context được thông báo theo thứ tự:

- `beforeCheckpoint()`: theo thứ tự ngược với thứ tự đăng ký.
- `afterRestore()`: theo thứ tự đăng ký.

Quy tắc này tạo ra vòng đời giống như sử dụng ngăn xếp: resource được tạo trước có thể được phục hồi trước, còn resource phụ thuộc được đóng trước khi tài nguyên nền tảng mà nó cần bị đóng.

Giả sử ứng dụng có hai resource:

- `databasePool` quản lý kết nối database.
- `orderService` sử dụng `databasePool` để xử lý nghiệp vụ.

`orderService` phụ thuộc vào `databasePool`, vì vậy pool cần sẵn sàng trước khi service bắt đầu phục vụ. Khi đăng ký, hãy đăng ký pool trước rồi đăng ký service:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class ApplicationResources {
    public void register(
            Resource databasePool,
            Resource orderService) {

        Context<Resource> context = Core.getGlobalContext();

        // Đăng ký tài nguyên nền tảng trước.
        context.register(databasePool);

        // Đăng ký thành phần phụ thuộc sau.
        context.register(orderService);
    }
}
~~~

Thứ tự callback sẽ là:

| Giai đoạn | Thứ tự | Lý do |
|---|---|---|
| Trước checkpoint | `orderService` rồi `databasePool` | Dừng thành phần sử dụng pool trước, sau đó mới đóng pool |
| Sau restore | `databasePool` rồi `orderService` | Tạo pool trước, sau đó mới khởi động lại service |

Nếu đăng ký theo thứ tự ngược lại, callback có thể chạy sai thứ tự so với quan hệ phụ thuộc. Khi đó service có thể vẫn đang dừng hoặc khởi động trong lúc pool đã bị đóng hoặc chưa sẵn sàng.

Với nhiều resource, hãy vẽ quan hệ phụ thuộc trước khi quyết định thứ tự đăng ký. Nếu A cần B để hoạt động, thông thường đăng ký B trước A để A được dừng trước B và được phục hồi sau B. Cần kiểm tra toàn bộ đồ thị phụ thuộc để tránh vòng phụ thuộc hoặc việc hai callback cùng quản lý một tài nguyên.

## 6. Đăng ký resource ở đâu trong ứng dụng?

Vị trí đăng ký tốt thường là giai đoạn bootstrap, khi ứng dụng tạo các thành phần hạ tầng. Ví dụ, một ứng dụng web có thể tạo connection pool, client tới broker và service nghiệp vụ trong lúc khởi động. Sau khi các đối tượng resource được tạo và có thể quản lý vòng đời, ứng dụng đăng ký chúng với global context.

Một cách tổ chức rõ ràng là gom việc đăng ký vào lớp cấu hình hoặc lớp khởi tạo tài nguyên:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class CracResourceRegistrar {

    public void registerAll(
            Resource databasePool,
            Resource messageConsumer,
            Resource externalClient) {

        Context<Resource> context = Core.getGlobalContext();

        context.register(databasePool);
        context.register(messageConsumer);
        context.register(externalClient);
    }
}
~~~

Ví dụ này đăng ký ba resource theo một vị trí tập trung. Thứ tự cần được điều chỉnh theo quan hệ phụ thuộc thực tế giữa chúng. Nếu message consumer cần database để xử lý thông điệp, database pool phải được phục hồi trước consumer và consumer phải dừng trước pool.

Một số nguyên tắc tổ chức:

- Đăng ký resource sau khi đã xác định được đối tượng thực sự sở hữu vòng đời của tài nguyên.
- Đảm bảo mỗi tài nguyên có một chủ sở hữu vòng đời rõ ràng.
- Thực hiện đăng ký ở giai đoạn khởi tạo có kiểm soát, tránh đăng ký rải rác ở nhiều nhánh xử lý request.
- Giữ thứ tự đăng ký dễ đọc và phản ánh quan hệ phụ thuộc.
- Tránh đăng ký cùng một resource nhiều lần do constructor hoặc hàm khởi tạo bị gọi lặp.
- Nếu thư viện đã tự tích hợp CRaC, kiểm tra cách thư viện quản lý resource trước khi thêm callback riêng.

Đăng ký tập trung giúp người bảo trì biết ứng dụng đang quản lý những tài nguyên nào qua CRaC và thứ tự callback được hình thành ra sao. Với ứng dụng lớn, có thể chia thành các nhóm resource theo thành phần, nhưng vẫn cần kiểm soát thứ tự giữa các nhóm có phụ thuộc.

## 7. Những việc register() không làm

Một hiểu nhầm phổ biến là cho rằng chỉ cần gọi `register()` thì CRaC sẽ tự động làm cho tài nguyên an toàn. Thực tế, `register()` chỉ đăng ký đối tượng để runtime gọi callback. Nội dung quản lý tài nguyên vẫn thuộc trách nhiệm của ứng dụng hoặc thư viện tích hợp.

| Hiểu nhầm | Hành vi thực tế |
|---|---|
| Gọi `register()` sẽ đóng kết nối ngay | Đăng ký resource; việc đóng kết nối cần được viết trong `beforeCheckpoint()` |
| CRaC tự mở lại mọi kết nối sau restore | Ứng dụng hoặc thư viện phải tạo lại kết nối trong `afterRestore()` |
| Global context đồng bộ trạng thái với database | Context chỉ quản lý callback trong JVM; database có vòng đời và trạng thái riêng |
| Đăng ký một đối tượng đồng nghĩa dữ liệu của nó đã bền vững | Checkpoint có thể giữ trạng thái heap, nhưng không thay thế hệ thống lưu trữ |
| Mọi đối tượng trong ứng dụng tự động được đăng ký | Chỉ resource đã đăng ký hoặc được tích hợp theo cơ chế tương ứng mới tham gia callback |
| Global context dùng chung giữa mọi replica | Mỗi JVM có vòng đời CRaC riêng |
| Callback có thể bỏ qua quan hệ phụ thuộc | Thứ tự đăng ký ảnh hưởng thứ tự callback trong cùng context |

Vì vậy, hãy xem `Core.getGlobalContext()` và `Context.register()` là cơ chế nối resource của ứng dụng vào vòng đời CRaC. Chúng không thay thế thiết kế xử lý transaction, idempotency, đồng bộ dữ liệu hoặc giao thức kết nối với hệ thống bên ngoài.

## 8. Xử lý lỗi trong callback

Các phương thức callback của `Resource` cho phép khai báo `throws Exception` vì thao tác chuẩn bị hoặc phục hồi tài nguyên có thể thất bại. Ví dụ:

- Database không thể đóng pool vì một thao tác vẫn đang sử dụng connection.
- Socket không đóng được do lỗi I/O.
- Database hoặc broker chưa sẵn sàng khi `afterRestore()` cố kết nối lại.
- Token đã hết hạn và dịch vụ cấp token tạm thời không truy cập được.
- Một tệp hoặc volume cần thiết chưa được mount lại.

Không nên bắt mọi exception rồi bỏ qua. Nếu `beforeCheckpoint()` không thể đưa tài nguyên về trạng thái an toàn, việc tiếp tục checkpoint có thể khiến ảnh chứa trạng thái không phù hợp. Nếu `afterRestore()` không thể khôi phục phụ thuộc bắt buộc, ứng dụng không nên nhận lưu lượng nghiệp vụ như thể đã sẵn sàng.

Một số nguyên tắc xử lý lỗi:

1. Chỉ báo callback hoàn tất khi các thao tác cần thiết đã đạt kết quả được xác định.
2. Ghi log đủ thông tin để nhận biết resource và giai đoạn thất bại, nhưng không ghi token, mật khẩu hoặc dữ liệu nhạy cảm.
3. Dùng timeout cho kết nối và thao tác chờ để callback không bị treo vô hạn.
4. Dùng retry có giới hạn, backoff và jitter khi phụ thuộc bên ngoài có thể tạm thời chưa sẵn sàng.
5. Giữ readiness ở trạng thái chưa sẵn sàng cho đến khi các phụ thuộc bắt buộc đã được khôi phục.
6. Làm cho thao tác đóng và phục hồi có thể xử lý trạng thái đã đóng hoặc đã khởi tạo một phần.

Lỗi callback có thể khiến quy trình checkpoint hoặc restore không hoàn tất theo cách ứng dụng mong đợi. Cách runtime báo lỗi và cách môi trường triển khai phản ứng còn phụ thuộc phiên bản CRaC và nền tảng. Cần kiểm tra log của runtime và kiểm thử cả đường đi thành công lẫn đường đi thất bại.

## 9. Thiết kế callback có thể chạy an toàn

Một callback tốt cần có kết quả rõ ràng và có thể lặp lại trong phạm vi hợp lý. Ví dụ, gọi `close()` hai lần không nên làm ứng dụng rơi vào trạng thái không thể phục hồi; gọi `connect()` khi đã có kết nối cũng cần có quy tắc rõ ràng.

Hãy cân nhắc các khía cạnh sau:

### Dừng công việc trước khi đóng tài nguyên

Nếu một consumer đang xử lý thông điệp hoặc một request đang dùng connection pool, đóng tài nguyên ngay có thể làm thao tác dở dang. Ứng dụng cần chuyển sang trạng thái ngừng nhận việc, drain các thao tác đang chạy, xử lý transaction theo chính sách và sau đó mới đóng tài nguyên.

### Phục hồi theo thứ tự phụ thuộc

Tạo lại thành phần nền tảng trước khi khởi động thành phần sử dụng nó. Ví dụ: khôi phục network client trước consumer; khôi phục connection pool trước service xử lý nghiệp vụ.

### Kiểm tra trạng thái bên ngoài

Không chỉ kiểm tra biến Java có khác `null` hay không. Hãy xác minh kết nối, session, quyền sở hữu lease, token và phiên bản dữ liệu với hệ thống có thẩm quyền.

### Giữ callback có giới hạn thời gian

Callback có thể cần thực hiện I/O, nhưng phải có timeout và chính sách lỗi. Không để callback chờ vô hạn một dịch vụ bên ngoài đang ngừng hoạt động.

### Không đưa công việc nghiệp vụ tùy ý vào callback

Callback nên tập trung vào chuẩn bị và phục hồi tài nguyên. Tránh tạo giao dịch nghiệp vụ mới, gửi thanh toán hoặc phát thông điệp nghiệp vụ chỉ vì callback được gọi. Nếu phải thực hiện thao tác bên ngoài, cần thiết kế idempotency và lưu kết quả bền vững.

## 10. Quy trình sử dụng hai API trong ứng dụng

Có thể triển khai theo trình tự sau:

1. Xác định tài nguyên nào cần đóng, làm mới hoặc xác minh qua checkpoint/restore.
2. Tạo một lớp triển khai `Resource` cho mỗi chủ sở hữu vòng đời hoặc nhóm tài nguyên có cùng quy tắc.
3. Viết `beforeCheckpoint()` để dừng hoạt động, hoàn tất công việc cần thiết và giải phóng tài nguyên.
4. Viết `afterRestore()` để tạo lại tài nguyên, xác thực và kiểm tra các phụ thuộc.
5. Lấy context bằng `Core.getGlobalContext()` trong giai đoạn bootstrap.
6. Đăng ký resource bằng `Context.register()` theo thứ tự phụ thuộc.
7. Kiểm thử checkpoint khi ứng dụng đang có lưu lượng, rồi restore và xác minh các phụ thuộc bên ngoài.
8. Kiểm thử lỗi kết nối, timeout và trường hợp nhiều instance được tạo từ cùng checkpoint.

Luồng tổng quát:

~~~mermaid
flowchart TD
    A[Khởi tạo ứng dụng] --> B[Tạo Resource]
    B --> C[Core.getGlobalContext]
    C --> D[Context.register Resource]
    D --> E[Ứng dụng hoạt động]
    E --> F[beforeCheckpoint]
    F --> G[Đóng hoặc chuẩn bị tài nguyên]
    G --> H[CRaC checkpoint]
    H --> I[CRaC restore]
    I --> J[afterRestore]
    J --> K[Tạo lại và xác minh tài nguyên]
    K --> L[Ứng dụng sẵn sàng]
~~~

`Core.getGlobalContext()` và `Context.register()` là hai bước kết nối đối tượng `Resource` với vòng đời CRaC. Thiết kế đúng cần xác định rõ ai sở hữu tài nguyên, callback phải làm gì, resource nào phụ thuộc resource nào và khi nào ứng dụng được phép nhận công việc trở lại.

## 11. Kiểm thử việc đăng ký resource

Kiểm thử không nên chỉ xác nhận rằng chương trình gọi được `register()`. Cần chứng minh runtime thực sự gọi callback và tài nguyên có thể được phục hồi trong môi trường triển khai.

Một số tình huống nên kiểm tra:

- Resource đã được đăng ký có chạy `beforeCheckpoint()` khi checkpoint diễn ra không?
- Resource có được gọi `afterRestore()` sau khi tiến trình restore không?
- Nhiều resource có chạy callback theo thứ tự đăng ký đã dự kiến không?
- Nếu resource phụ thuộc database pool, pool có sẵn sàng trước khi resource đó phục hồi không?
- Nếu callback đóng tài nguyên gặp lỗi, quy trình checkpoint có báo lỗi rõ ràng không?
- Nếu database hoặc broker chưa sẵn sàng sau restore, ứng dụng có giữ readiness ở trạng thái phù hợp không?
- Nếu cùng một checkpoint tạo nhiều replica, mỗi replica có tạo kết nối và identity riêng không?
- Nếu resource được khởi tạo nhiều lần trong quá trình bootstrap, ứng dụng có tránh đăng ký trùng không?

Hãy chạy thử trên đúng JDK có hỗ trợ CRaC, hệ điều hành, container runtime và cấu hình checkpoint/restore dự kiến. API có thể có khác biệt theo bản phân phối JDK hoặc phiên bản CRaC; hãy xác nhận dependency và tài liệu tương ứng với môi trường đang dùng.

## 12. Tóm tắt cách phối hợp hai API

| API | Trách nhiệm | Cách dùng điển hình |
|---|---|---|
| `Core.getGlobalContext()` | Lấy context vòng đời toàn cục của CRaC trong JVM | Gọi trong giai đoạn khởi tạo để lấy context đăng ký |
| `Context.register(Resource)` | Đăng ký một resource để nhận callback checkpoint/restore | Gọi cho từng đối tượng triển khai `Resource` |
| `Resource.beforeCheckpoint(Context)` | Chuẩn bị và giải phóng tài nguyên trước checkpoint | Drain công việc, flush dữ liệu, đóng kết nối |
| `Resource.afterRestore(Context)` | Khôi phục tài nguyên sau restore | Kết nối lại, xác thực, đăng ký subscription và kiểm tra readiness |

Khi được dùng đúng cách, hai API này tạo ra một điểm đăng ký tập trung để ứng dụng phối hợp vòng đời của tài nguyên. `Core.getGlobalContext()` cung cấp context, `Context.register()` đăng ký đối tượng, còn logic thực tế nằm trong các callback của `Resource`. Nhờ đó, ứng dụng có thể chuẩn bị tài nguyên trước checkpoint và chủ động phục hồi chúng sau restore.
