# Trạng thái trong tiến trình và tài nguyên bên ngoài tiến trình

CRaC (Coordinated Restore at Checkpoint) cho phép lưu trạng thái của một tiến trình Java tại một thời điểm rồi khôi phục tiến trình từ checkpoint đó. Cách làm này có thể rút ngắn thời gian khởi động: ứng dụng được chạy trước, nạp lớp, khởi tạo framework và làm nóng những phần cần thiết; sau đó trạng thái đã chuẩn bị được checkpoint để dùng lại.

Để checkpoint có thể khôi phục an toàn, cần phân biệt hai thứ thường bị nhầm lẫn:

- **Trạng thái trong tiến trình** là dữ liệu và trạng thái thực thi đang được JVM quản lý, chẳng hạn object trên heap, giá trị static và trạng thái của các luồng.
- **Tài nguyên bên ngoài tiến trình** là những tài nguyên do hệ điều hành, hệ thống tệp, mạng hoặc dịch vụ khác quản lý, chẳng hạn phiên kết nối cơ sở dữ liệu, socket, khóa phân tán và dữ liệu đang nằm trong Redis.

Một object Java có thể vẫn còn nguyên sau khi restore nhưng tài nguyên mà object đó đại diện đã hết hiệu lực. Đây là điểm cần xử lý khi thiết kế ứng dụng hỗ trợ CRaC.

## 1. Hai lớp trạng thái cần phân biệt

### Trạng thái nằm trong tiến trình

Đây là phần trạng thái thuộc về tiến trình Java và được lưu trong ảnh checkpoint theo cơ chế của JVM và nền tảng checkpoint. Ví dụ:

- Các object trên heap: cấu hình đã phân tích, cache trong bộ nhớ, cấu trúc dữ liệu, singleton và trạng thái nghiệp vụ tạm thời.
- Các trường static và quan hệ tham chiếu giữa các object.
- Trạng thái thực thi của JVM và luồng: stack, vị trí thực thi và những dữ liệu runtime mà cơ chế checkpoint hỗ trợ.
- Trạng thái đã khởi tạo của framework: metadata, registry, dependency graph và các thành phần đã được tạo trong bộ nhớ.

Khi tiến trình được restore, ứng dụng có thể tiếp tục sử dụng nhiều object đã được tạo trước checkpoint mà không phải thực hiện lại toàn bộ quá trình khởi động.

Tuy nhiên, checkpoint không biến heap thành một kho dữ liệu bền vững. Đây là ảnh chụp trạng thái của một tiến trình tại một thời điểm, không phải cơ chế lưu object theo định dạng nghiệp vụ để có thể đọc độc lập, nâng cấp schema hoặc đồng bộ với một hệ thống khác.

### Tài nguyên nằm ngoài tiến trình

Đây là những tài nguyên có vòng đời hoặc trạng thái được quản lý bên ngoài heap Java. Ví dụ:

- Database quản lý session, transaction, cursor và khóa trên máy chủ cơ sở dữ liệu.
- Redis hoặc message broker quản lý connection, subscription, consumer group và dữ liệu của chúng.
- Hệ điều hành quản lý file descriptor, socket, cổng mạng, file lock và một số loại tài nguyên tiến trình.
- Hệ thống bên ngoài quản lý token, lease, distributed lock, phiên đăng nhập và trạng thái công việc.
- Hệ thống tệp quản lý nội dung file; dịch vụ từ xa quản lý dữ liệu và các side effect đã ghi nhận.

Ứng dụng Java thường chỉ giữ một object đại diện cho tài nguyên bên ngoài. Ví dụ, một object Connection nằm trên heap có thể chứa thông tin để thao tác với một session trên database. Việc object Connection còn tồn tại sau restore không chứng minh session phía database vẫn còn tồn tại hoặc vẫn có thể sử dụng.

### So sánh qua ví dụ

| Thành phần | Trạng thái trong tiến trình | Trạng thái bên ngoài | Điều cần làm sau restore |
|---|---|---|---|
| JDBC Connection | Object Connection và các object bao quanh nó | Session, transaction và socket tới database | Kiểm tra vòng đời của pool; tạo kết nối hợp lệ mới |
| HTTP client | Object client, cấu hình và bộ quản lý connection | TCP/TLS session, DNS và máy chủ từ xa | Khởi tạo hoặc làm mới client theo hướng dẫn của thư viện |
| File | Đường dẫn, buffer và object đại diện file | Nội dung file, quyền truy cập và trạng thái file trên hệ thống tệp | Flush dữ liệu trước checkpoint; mở lại file nếu handle không còn hợp lệ |
| Cache | Các entry đang nằm trên heap | Nguồn dữ liệu chuẩn như database hoặc Redis | Kiểm tra độ mới và làm mới entry có thể đã lỗi thời |
| Distributed lock | Object quản lý lock và token đang được giữ trong heap | Lease hoặc lock do hệ thống phối hợp phân tán quản lý | Xác minh quyền sở hữu; không tiếp tục dựa vào lease đã hết hạn |
| Scheduler | Object executor và các tác vụ đã đăng ký | Thời gian thực, deadline và trạng thái công việc bên ngoài | Đối chiếu thời gian hiện tại rồi lập lịch lại khi cần |

Một số tài nguyên hệ điều hành có thể được công cụ checkpoint hỗ trợ khôi phục tùy loại tài nguyên, phiên bản và môi trường triển khai. Vì vậy, không nên mặc định mọi file descriptor hoặc socket đều mất, cũng không nên mặc định chúng chắc chắn còn dùng được. Cần kiểm tra khả năng hỗ trợ thực tế và tuân theo hướng dẫn tích hợp của JVM, CRaC và thư viện đang sử dụng.

## 2. Vì sao object còn tồn tại nhưng tài nguyên có thể đã mất?

Hãy xét một ứng dụng có trường instance như sau:

~~~java
public final class OrderRepository {
    private final Connection connection;

    public OrderRepository(Connection connection) {
        this.connection = connection;
    }
}
~~~

Trường connection là một tham chiếu nằm trong object OrderRepository. Khi checkpoint lưu trạng thái tiến trình, tham chiếu này thuộc về trạng thái trong bộ nhớ. Nhưng database là một tiến trình hoặc dịch vụ độc lập. Nó không được quay ngược thời gian cùng với JVM.

Trong khoảng thời gian từ lúc tạo checkpoint đến lúc restore, database có thể đã:

- Đóng session vì timeout hoặc vì server khởi động lại.
- Hủy transaction chưa commit.
- Thu hồi connection do giới hạn tài nguyên.
- Thay đổi dữ liệu mà ứng dụng đã cache trước checkpoint.
- Thay đổi quyền truy cập hoặc thông tin xác thực.

Do đó, sau restore, gọi method trên object Connection cũ có thể thất bại dù trường connection vẫn khác null. Kiểm tra null chỉ cho biết ứng dụng còn giữ một tham chiếu; nó không kiểm tra được tính hợp lệ của session ở phía server.

Nguyên tắc này áp dụng cho mọi object wrapper: object có thể còn sống trong heap trong khi tài nguyên được wrapper đại diện đã đóng, hết hạn hoặc thay đổi ở bên ngoài.

## 3. Checkpoint không đưa hệ thống bên ngoài quay về quá khứ

Checkpoint ghi nhận trạng thái của tiến trình Java. Nó không tạo một snapshot nhất quán cho toàn bộ hệ thống phân tán.

Ví dụ, trước checkpoint ứng dụng gửi yêu cầu trừ tiền và database đã commit giao dịch. Sau đó tiến trình được restore từ checkpoint cũ. Database vẫn giữ giao dịch đã commit; nó không tự hoàn tác chỉ vì JVM quay lại trạng thái bộ nhớ trước đó.

Điều này tạo ra một rủi ro quan trọng: **trạng thái trong heap có thể cũ hơn những side effect đã xảy ra bên ngoài tiến trình**.

Hãy phân biệt ba tình huống:

1. **Dữ liệu chỉ nằm trong heap:** dữ liệu đó có thể trở lại đúng trạng thái tại thời điểm checkpoint.
2. **Dữ liệu đã được ghi vào hệ thống bên ngoài:** dữ liệu bên ngoài tiếp tục tồn tại theo quy tắc của hệ thống đó.
3. **Một thao tác đang thực hiện dở:** kết quả phụ thuộc vào việc hệ thống bên ngoài đã nhận, xử lý hoặc commit thao tác hay chưa.

Vì vậy, trước checkpoint nên đưa ứng dụng về một điểm an toàn:

- Ngừng nhận công việc mới trong khoảng thời gian chuẩn bị checkpoint.
- Chờ các request hoặc tác vụ đang chạy hoàn thành, hoặc hủy chúng theo một quy tắc rõ ràng.
- Commit hoặc rollback transaction theo đúng nghiệp vụ.
- Flush buffer ghi file và đóng tài nguyên có vòng đời không thể bảo đảm sau restore.
- Không giữ distributed lock hoặc lease với giả định rằng thời gian bên ngoài sẽ dừng lại cùng tiến trình.

Nếu thao tác có thể được gửi lại sau restore, hãy thiết kế tính idempotent, dùng idempotency key hoặc cơ chế deduplication. Với quy trình ghi dữ liệu và phát sự kiện, có thể dùng transactional outbox để giữ tính nhất quán giữa thay đổi trong database và sự kiện cần phát. Không nên dựa vào checkpoint để hoàn tác side effect đã được hệ thống khác ghi nhận.

## 4. Vòng đời tài nguyên quanh checkpoint và restore

CRaC cung cấp API Resource để ứng dụng tham gia vào vòng đời checkpoint/restore. Hai callback quan trọng là:

- beforeCheckpoint: chuẩn bị tài nguyên trước khi JVM được checkpoint.
- afterRestore: khôi phục hoặc tạo lại tài nguyên sau khi JVM được restore.

Một Resource được đăng ký với context, thường là global context:

~~~java
Core.getGlobalContext().register(resource);
~~~

Các callback cho phép ứng dụng xử lý những tài nguyên mà JVM không thể tự hiểu đầy đủ về ý nghĩa nghiệp vụ. Ví dụ, JVM có thể nhìn thấy một object client, nhưng chỉ ứng dụng mới biết client đó đang giữ subscription nào, có transaction nào cần hoàn tất hay cần đọc lại credential từ đâu.

### Trước checkpoint: đưa ứng dụng về trạng thái an toàn

Trong beforeCheckpoint, ứng dụng có thể:

- Ngừng tiếp nhận công việc mới và chờ công việc đang chạy kết thúc.
- Hoàn tất hoặc rollback transaction.
- Flush dữ liệu đang đệm và đóng file nếu cần.
- Đóng connection hoặc pool không được bảo đảm có thể dùng lại.
- Dừng consumer, listener hoặc tác vụ nền theo cách thư viện hỗ trợ.
- Nhả lock hoặc lease có thể hết hạn trong thời gian tiến trình không hoạt động.

Không phải mọi tài nguyên đều cần tự đóng trong callback. Một số loại tài nguyên được JVM, CRaC hoặc thư viện/framework tích hợp hỗ trợ trực tiếp. Hãy kiểm tra tài liệu của phiên bản đang triển khai trước khi tự quản lý vòng đời của chúng; đóng một listener hoặc connection do framework quản lý sai thời điểm có thể làm hỏng quá trình restore.

### Sau restore: xác lập lại kết nối với thế giới hiện tại

Trong afterRestore, ứng dụng có thể:

- Tạo lại client, connection hoặc pool đã đóng trước checkpoint.
- Khởi động lại consumer và tác vụ nền.
- Đọc lại credential, cấu hình động hoặc chứng thư nếu chúng có thể đã thay đổi.
- Kiểm tra cache và dữ liệu tạm có thể đã lỗi thời.
- Xác minh lease, subscription và quyền sở hữu tài nguyên từ xa.
- Chạy health check trước khi nhận traffic.

Sau restore, ứng dụng đang hoạt động trong thế giới hiện tại. Nó cần dùng thời gian, trạng thái dịch vụ và quyền truy cập hiện tại thay vì giả định mọi thứ vẫn giống lúc checkpoint.

### Ví dụ quản lý một client từ xa

Ví dụ sau minh họa một Resource sở hữu một client có thể đóng và tạo lại. RemoteClient là kiểu do ứng dụng hoặc thư viện tự định nghĩa; phần tạo kết nối thực tế phụ thuộc vào thư viện đang dùng.

~~~java
import java.util.concurrent.Callable;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class RemoteClientResource implements Resource {
    private final Callable<RemoteClient> clientFactory;
    private RemoteClient client;

    public RemoteClientResource(Callable<RemoteClient> clientFactory)
            throws Exception {
        this.clientFactory = clientFactory;
        this.client = clientFactory.call();
        Core.getGlobalContext().register(this);
    }

    public synchronized RemoteClient getClient() {
        if (client == null) {
            throw new IllegalStateException("Remote client is not ready");
        }
        return client;
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        if (client != null) {
            client.close();
            client = null;
        }
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {
        client = clientFactory.call();
    }
}
~~~

Điểm quan trọng trong ví dụ:

- Resource giữ factory để có thể tạo client mới sau restore.
- Client hiện tại được đóng trước checkpoint.
- Sau restore, client được tạo lại bằng factory.
- Resource chỉ đăng ký một lần với global context.
- Ứng dụng cần kiểm soát việc truy cập client trong khi đang chuẩn bị checkpoint; callback đóng tài nguyên không thay thế cho bước ngừng và drain request.

Nếu đang dùng connection pool, cần quản lý vòng đời của chính pool theo hướng dẫn của nhà cung cấp. Với một số pool, gọi close trên connection chỉ trả connection về pool chứ không đóng physical connection. Khi đó, chỉ đóng một connection mượn từ pool có thể không đủ để làm mới toàn bộ kết nối cũ.

Callback cũng cần được thiết kế có khả năng chịu lỗi. Nếu việc đóng hoặc tạo lại tài nguyên thất bại, checkpoint hoặc quá trình restore có thể không hoàn tất như mong đợi. Không nên đánh dấu ứng dụng sẵn sàng khi client vẫn chưa được tạo. Đồng thời, không giả định mọi lần gọi beforeCheckpoint đều chắc chắn dẫn đến một lần afterRestore; hãy có cách phục hồi tài nguyên nếu thao tác checkpoint bị từ chối hoặc thất bại.

## 5. Những loại tài nguyên cần chú ý

### Kết nối database và transaction

Connection Java là đại diện cho một kết nối tới database. Phía database có thể quản lý session, transaction, lock và cursor riêng.

Trước checkpoint:

- Không để transaction nghiệp vụ ở trạng thái dở dang.
- Hoàn tất hoặc rollback transaction theo quy tắc nghiệp vụ.
- Dừng việc cấp connection mới trong lúc chuẩn bị.
- Làm theo hướng dẫn CRaC của connection pool và JDBC driver đang sử dụng.

Sau restore:

- Tạo lại hoặc làm mới pool nếu thư viện yêu cầu.
- Kiểm tra kết nối tới database trước khi nhận traffic.
- Không dùng lại transaction, cursor hoặc session cũ chỉ vì object Java vẫn tồn tại.
- Đọc lại dữ liệu chuẩn nếu cache trong heap có thể đã lỗi thời.

### Socket, HTTP client và message broker

Một socket liên quan đến cả trạng thái local do hệ điều hành quản lý và trạng thái của peer ở xa. Peer có thể đã đóng kết nối, timeout hoặc thay đổi trạng thái trong lúc ứng dụng được checkpoint.

Với HTTP client, broker client hoặc consumer, cần kiểm tra tài liệu tích hợp CRaC của thư viện. Có thư viện cung cấp hook hoặc cơ chế tự làm mới connection; có thư viện yêu cầu ứng dụng đóng và tạo lại client. Đặc biệt chú ý subscription, consumer assignment, offset và việc xác nhận message để tránh xử lý lặp hoặc bỏ sót.

### File và buffer ghi dữ liệu

Nội dung file thuộc hệ thống tệp, không nằm trong heap của JVM. Object đại diện file và buffer Java là trạng thái trong tiến trình; file thật và quyền truy cập do hệ thống tệp quản lý.

Trước checkpoint, cần flush dữ liệu đang đệm để tránh mất phần ghi chưa được chuyển xuống hệ thống tệp. Có thể đóng rồi mở lại file sau restore nếu handle không được hỗ trợ hoặc không còn hợp lệ. Nếu ứng dụng cần bảo đảm dữ liệu đã được ghi bền vững, hãy dùng cơ chế đồng bộ phù hợp của hệ thống tệp; việc flush một buffer Java không phải lúc nào cũng tương đương với bảo đảm dữ liệu đã nằm trên thiết bị lưu trữ.

### Lock và lease

Khóa trong JVM như synchronized hoặc ReentrantLock có trạng thái gắn với tiến trình. Trong khi đó, file lock, database lock và distributed lock có thể do thành phần bên ngoài quản lý.

Một distributed lease thường có thời hạn. Thời gian vẫn trôi qua khi ứng dụng được checkpoint. Khi restore, lease có thể đã hết hạn và một tiến trình khác có thể đã nhận quyền sở hữu. Ứng dụng phải xác minh lại quyền sở hữu trước khi tiếp tục thao tác được bảo vệ bởi lease.

Không giữ một distributed lock xuyên qua checkpoint với giả định rằng thời gian lease sẽ tạm dừng. Nếu nghiệp vụ cần tiếp tục công việc sau restore, hãy thiết kế bước giành lại quyền sở hữu và kiểm tra fencing token hoặc phiên bản quyền sở hữu theo cơ chế của hệ thống phối hợp.

### Cache, cấu hình và thông tin xác thực

Cache trong heap có thể được khôi phục nguyên trạng nhưng đã cũ so với nguồn dữ liệu chuẩn. Cấu hình hoặc credential cũng có thể đã được xoay vòng trong khoảng thời gian giữa checkpoint và restore.

Sau restore, hãy xác định dữ liệu nào có thể dùng tiếp và dữ liệu nào phải đọc lại. Ví dụ, cache dữ liệu tham chiếu ít thay đổi có thể được giữ lại nếu có cơ chế kiểm tra phiên bản; access token, secret, chứng thư và cấu hình có thời hạn thường cần được xác minh hoặc làm mới.

### Đồng hồ và tác vụ được lập lịch

Checkpoint không dừng thời gian của hệ thống bên ngoài. Một deadline, token expiration, lease hoặc lịch chạy có thể đã đến hạn trong lúc tiến trình không hoạt động.

Không nên chỉ lưu một khoảng thời gian còn lại trong heap rồi mặc định khoảng thời gian đó vẫn chính xác sau restore. Hãy đối chiếu thời gian hiện tại với nguồn thời gian phù hợp, kiểm tra deadline và tính toán lại lịch chạy. Với các phép đo thời lượng dùng đồng hồ monotonic, cần xem xét hành vi của runtime và nền tảng checkpoint; không tùy tiện giả định giá trị đo trước checkpoint có thể so sánh trực tiếp với giá trị sau restore.

## 6. Thiết kế Resource có thể vận hành ổn định

Một Resource tốt nên có ranh giới sở hữu rõ ràng: biết nó đang quản lý tài nguyên nào, ai được phép sử dụng tài nguyên và cách tạo lại tài nguyên sau restore.

Một số nguyên tắc hữu ích:

1. **Đăng ký đúng chủ sở hữu:** thành phần chịu trách nhiệm vòng đời tài nguyên nên quản lý callback. Tránh nhiều Resource cùng đóng hoặc cùng tạo lại một pool.
2. **Đăng ký một lần:** tránh tạo nhiều đăng ký cho cùng một instance trong quá trình khởi tạo hoặc refresh.
3. **Callback có thể gọi an toàn:** xử lý trường hợp tài nguyên chưa được tạo, đã đóng hoặc đang ở trạng thái dở dang. Không giả định callback chỉ gặp một trạng thái lý tưởng.
4. **Không giữ công việc đang chạy:** phối hợp với request handler, executor và consumer để đưa ứng dụng về điểm an toàn trước khi đóng tài nguyên.
5. **Tạo lại từ nguồn cấu hình hiện tại:** sau restore, factory nên dùng cấu hình và credential còn hiệu lực.
6. **Chỉ báo sẵn sàng sau khi phục hồi xong:** health check cần phản ánh khả năng sử dụng thực tế của các dependency thiết yếu.
7. **Tôn trọng tích hợp của thư viện:** không tự đóng tài nguyên nếu framework hoặc thư viện đã có hỗ trợ CRaC riêng.
8. **Xử lý lỗi rõ ràng:** nếu không thể tạo lại một dependency bắt buộc, ứng dụng cần báo lỗi và không tiếp tục xử lý request như thể dependency đang hoạt động.

Không phải mọi object trong heap đều cần triển khai Resource. Chỉ những thành phần sở hữu tài nguyên có vòng đời cần phối hợp với checkpoint/restore mới cần tham gia. Một object dữ liệu thuần túy, không giữ tài nguyên bên ngoài, thường có thể được khôi phục cùng trạng thái tiến trình mà không cần callback riêng.

## 7. Kiểm thử hành vi sau restore

Một lần khởi động thành công từ checkpoint chưa đủ để chứng minh ứng dụng xử lý đúng mọi tình huống. Nên kiểm thử trong môi trường gần với môi trường triển khai thực tế, bao gồm:

- Restore khi database hoặc broker vẫn hoạt động bình thường.
- Restore sau khi một dependency đã restart hoặc đóng các session cũ.
- Restore sau khoảng thời gian đủ dài để token, lease hoặc cache có thể hết hạn.
- Kiểm tra transaction và request đang chạy tại thời điểm chuẩn bị checkpoint.
- Kiểm tra ứng dụng không tạo trùng consumer, scheduler hoặc background worker.
- Kiểm tra side effect không bị thực hiện lặp khi một thao tác được gửi lại sau restore.
- Kiểm tra callback báo lỗi đúng cách khi không thể đóng hoặc tạo lại tài nguyên.
- Thực hiện nhiều chu kỳ checkpoint/restore để phát hiện đăng ký callback trùng, rò rỉ connection hoặc tác vụ nền bị nhân đôi.

Kết quả kiểm thử phụ thuộc vào phiên bản JDK có CRaC, thư viện, hệ điều hành và công cụ checkpoint được sử dụng. Vì vậy, cần xác minh trên đúng tổ hợp runtime sẽ chạy trong môi trường thật.

## 8. Những hiểu nhầm thường gặp

**“Object vẫn còn nên connection vẫn dùng được.”**  
Không đúng. Object và session ở phía database có vòng đời khác nhau. Hãy kiểm tra hoặc tạo lại kết nối theo hướng dẫn của driver và pool.

**“Restore sẽ hoàn tác những thao tác đã thực hiện sau checkpoint.”**  
Không đúng. Database, message broker và dịch vụ bên ngoài không tự quay lại trạng thái cũ. Các side effect đã commit vẫn có thể tồn tại.

**“Mọi tài nguyên ngoài heap đều tự động mất.”**  
Không chính xác. Khả năng khôi phục phụ thuộc loại tài nguyên, CRaC implementation, công cụ hệ điều hành và tích hợp của thư viện. Cần xác minh từng loại tài nguyên.

**“Chỉ cần đóng mọi thứ trong beforeCheckpoint.”**  
Đóng tài nguyên không đúng thứ tự có thể làm hỏng request đang chạy hoặc xung đột với framework. Trước hết cần ngừng nhận công việc mới, drain công việc đang chạy và tuân theo vòng đời do thư viện cung cấp.

**“Cache trong heap luôn còn đúng sau restore.”**  
Không đúng. Cache có thể vẫn tồn tại nhưng dữ liệu nguồn đã thay đổi. Cần kiểm tra tính hợp lệ theo chính sách cache.

**“Checkpoint là một cách thay thế database backup.”**  
Không đúng. Checkpoint phục vụ khôi phục trạng thái tiến trình. Nó không thay thế backup, transaction log, cơ chế replication hoặc quy trình khôi phục dữ liệu của hệ thống lưu trữ.

## 9. Kết luận

Khi thiết kế ứng dụng Java với CRaC, hãy xem checkpoint là ranh giới giữa trạng thái bộ nhớ của một tiến trình và thế giới bên ngoài vẫn tiếp tục vận hành. Dữ liệu trong heap có thể được khôi phục, nhưng session, connection, lock, credential, deadline và side effect bên ngoài cần được đánh giá theo vòng đời riêng.

Ứng dụng hỗ trợ CRaC tốt khi có thể đưa mình về trạng thái an toàn trước checkpoint, tạo lại hoặc xác minh tài nguyên sau restore, và tiếp tục xử lý mà không giả định các hệ thống bên ngoài đã quay về quá khứ.
