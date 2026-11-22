# Resource: khai báo thành phần cần tham gia checkpoint và restore

Trong CRaC, **Resource** là hợp đồng để một thành phần của ứng dụng thông báo cho runtime biết nó cần chuẩn bị gì trước checkpoint và cần phục hồi gì sau restore. Thành phần triển khai Resource có thể đóng kết nối, hoàn tất công việc đang chạy, làm sạch trạng thái tạm trước khi checkpoint; sau restore, nó có thể tạo lại kết nối, đăng ký lại listener hoặc khởi động lại tác vụ nền.

Điểm quan trọng là **triển khai Resource và đăng ký instance của nó là hai việc riêng biệt**. Một class có implements Resource nhưng chưa được đăng ký với Context thì không tự động nhận callback từ CRaC. Ứng dụng cần đăng ký đúng instance mà nó muốn runtime quản lý.

## 1. Resource là gì?

org.crac.Resource là interface trong CRaC API. Nó định nghĩa hai callback:

- **beforeCheckpoint(...)**: được gọi khi runtime chuẩn bị tạo checkpoint. Resource đưa tài nguyên mà nó sở hữu về trạng thái an toàn.
- **afterRestore(...)**: được gọi khi tiến trình được khôi phục từ checkpoint. Resource xác lập lại những tài nguyên cần thiết để ứng dụng tiếp tục hoạt động.

Hợp đồng API có dạng:

~~~java
public interface Resource {
    void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception;

    void afterRestore(Context<? extends Resource> context)
            throws Exception;
}
~~~

Đây là chữ ký minh họa của API; khi viết ứng dụng, hãy import interface từ CRaC API mà JDK/runtime đang sử dụng thay vì tự khai báo lại interface này.

Một Resource thường đại diện cho một thành phần có vòng đời cần phối hợp với checkpoint/restore, ví dụ:

- Client kết nối tới database, Redis, message broker hoặc dịch vụ HTTP.
- Consumer đang nhận message từ broker.
- Listener, socket hoặc tác vụ nền cần dừng và đăng ký lại.
- Thành phần đang giữ file, buffer hoặc tài nguyên hệ điều hành cần được đóng và mở lại.
- Thành phần quản lý subscription, lease hoặc trạng thái làm việc có thể hết hạn khi tiến trình tạm dừng.

Không cần biến mọi object Java thành Resource. Một object chỉ chứa dữ liệu thuần túy trong heap, không sở hữu tài nguyên cần chuẩn bị hoặc phục hồi, thường không cần callback riêng.

## 2. Hai callback của Resource

### beforeCheckpoint

Runtime gọi beforeCheckpoint trong giai đoạn chuẩn bị checkpoint. Thành phần triển khai callback cần đưa tài nguyên do mình sở hữu về trạng thái có thể checkpoint an toàn.

Các công việc thường gặp:

- Ngừng nhận công việc mới thông qua cơ chế điều phối của ứng dụng.
- Chờ các thao tác đang sử dụng tài nguyên hoàn tất.
- Commit hoặc rollback transaction theo quy tắc nghiệp vụ.
- Flush dữ liệu đang đệm.
- Đóng kết nối hoặc tài nguyên không được bảo đảm có thể sử dụng sau restore.
- Tạm dừng consumer, listener hoặc executor theo hướng dẫn của thư viện.
- Nhả lease hoặc khóa phân tán nếu quyền sở hữu có thể hết hạn trong thời gian tiến trình không hoạt động.

Callback này không nên chứa công việc nghiệp vụ mới hoặc thực hiện những thao tác có thể tạo ra side effect không thể lặp an toàn. Mục tiêu là chuẩn bị tài nguyên và trạng thái thực thi cho checkpoint.

### afterRestore

Runtime gọi afterRestore khi tiến trình được khôi phục. Resource xác lập lại tài nguyên mà ứng dụng cần trong môi trường hiện tại.

Các công việc thường gặp:

- Tạo lại connection hoặc client đã đóng trước checkpoint.
- Khởi động lại consumer hoặc listener.
- Đăng ký lại subscription.
- Đọc lại cấu hình, credential hoặc chứng thư có thể đã thay đổi.
- Xác minh lease, quyền sở hữu và trạng thái tài nguyên từ xa.
- Kiểm tra dependency trước khi ứng dụng nhận traffic.

Restore đưa tiến trình trở lại trạng thái bộ nhớ đã checkpoint, còn các dịch vụ bên ngoài vẫn tiếp tục hoạt động theo thời gian thực của chúng. Vì vậy, afterRestore nên tạo hoặc xác minh tài nguyên dựa trên trạng thái hiện tại của hệ thống bên ngoài.

### Tham số Context

Cả hai callback đều nhận một tham số Context<? extends Resource>. Đây là context mà runtime truyền vào khi gọi callback. Resource có thể không cần sử dụng tham số này nếu nó chỉ quản lý một tài nguyên độc lập.

Tham số context trong callback không phải là một Resource mới và cũng không phải lời gọi checkpoint. Khi đăng ký một Resource ở cấp ứng dụng, mã khởi tạo thường sử dụng global context thông qua Core.getGlobalContext().

### Ngoại lệ trong callback

Hai phương thức khai báo throws Exception để Resource có thể báo lỗi khi không chuẩn bị hoặc phục hồi được tài nguyên. Không nên bắt rồi bỏ qua lỗi đóng kết nối, flush dữ liệu hoặc tạo lại client bắt buộc. Nếu callback không hoàn thành, runtime có thể không thể hoàn tất giai đoạn checkpoint hoặc restore tương ứng.

Ứng dụng cần log lỗi với đủ thông tin để xác định Resource nào thất bại. Với dependency bắt buộc, chỉ đánh dấu ứng dụng sẵn sàng sau khi quá trình phục hồi đã thành công.

## 3. Đăng ký Resource với Context

Sau khi có một instance triển khai Resource, ứng dụng đăng ký instance đó với một Context. Với thành phần thuộc phạm vi toàn ứng dụng, cách dùng phổ biến là đăng ký vào global context:

~~~java
Core.getGlobalContext().register(resource);
~~~

Core và Resource thuộc package org.crac:

~~~java
import org.crac.Core;
import org.crac.Resource;
~~~

Quy trình cơ bản gồm ba bước:

1. Tạo instance của thành phần quản lý tài nguyên.
2. Đăng ký instance đó với context phù hợp.
3. Để CRaC runtime gọi các callback ở những giai đoạn checkpoint và restore.

Ví dụ đăng ký một Resource đã được tạo:

~~~java
RemoteClientResource resource =
        new RemoteClientResource(clientFactory);

Core.getGlobalContext().register(resource);
~~~

Trong ví dụ trên, clientFactory là factory của ứng dụng. Việc đăng ký phải trỏ tới đúng instance đang sở hữu client mà ứng dụng sử dụng. Tạo một instance chỉ để đăng ký, trong khi ứng dụng lại sử dụng một instance khác, sẽ khiến callback quản lý sai đối tượng.

Thông thường, ứng dụng đăng ký Resource trong giai đoạn khởi tạo, sau khi các dependency cần thiết đã sẵn sàng và trước khi có thể thực hiện checkpoint. Hãy bảo đảm mỗi instance chỉ được đăng ký theo chủ đích; đăng ký lặp có thể làm callback chạy nhiều lần trên cùng một tài nguyên.

Việc một class được Spring hoặc framework khác quản lý như bean không đồng nghĩa class đó tự động trở thành Resource của CRaC. Chỉ dựa vào dependency injection hoặc component scanning là chưa đủ, trừ khi framework đang dùng có tích hợp CRaC và tài liệu của framework xác nhận cơ chế đăng ký đó.

## 4. Ví dụ: Resource quản lý một remote client

Giả sử ứng dụng dùng một client để gửi dữ liệu tới dịch vụ bên ngoài. Client có thể đóng trước checkpoint và tạo lại sau restore.

Ví dụ dưới đây định nghĩa interface client và factory bên trong cùng một class để minh họa một file Java hoàn chỉnh. Trong dự án thật, các interface này có thể được thay bằng API của thư viện đang sử dụng.

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class RemoteClientResource implements Resource {
    public interface RemoteClient extends AutoCloseable {
        void publish(String message) throws Exception;

        @Override
        void close() throws Exception;
    }

    @FunctionalInterface
    public interface RemoteClientFactory {
        RemoteClient connect() throws Exception;
    }

    private final RemoteClientFactory clientFactory;
    private RemoteClient client;

    public RemoteClientResource(RemoteClientFactory clientFactory)
            throws Exception {
        this.clientFactory = clientFactory;
        this.client = clientFactory.connect();

    }

    public synchronized void publish(String message) throws Exception {
        if (client == null) {
            throw new IllegalStateException(
                    "Remote client is not available");
        }
        client.publish(message);
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
        client = clientFactory.connect();
    }
}
~~~

Khi ứng dụng khởi tạo:

~~~java
RemoteClientResource remoteClient =
        new RemoteClientResource(clientFactory);
Core.getGlobalContext().register(remoteClient);
~~~

Vòng đời minh họa:

~~~text
Ứng dụng khởi tạo
       |
       v
Tạo RemoteClient
       |
       v
Đăng ký Resource với global Context
       |
       v
CRaC gọi beforeCheckpoint()
       |
       v
Đóng RemoteClient và đặt client = null
       |
       v
Tạo checkpoint
       |
       v
Khôi phục tiến trình
       |
       v
CRaC gọi afterRestore()
       |
       v
Factory tạo RemoteClient mới
       |
       v
Ứng dụng tiếp tục sử dụng client
~~~

Ví dụ cho thấy các điểm sau:

- implements Resource khai báo class có thể tham gia vòng đời CRaC.
- Core.getGlobalContext().register(remoteClient) đăng ký instance để runtime biết cần gọi callback.
- beforeCheckpoint đóng client đang được quản lý và giải phóng tham chiếu.
- afterRestore dùng factory để tạo một client mới.
- clientFactory cần có khả năng tạo kết nối trong môi trường sau restore, bao gồm việc đọc cấu hình hoặc credential còn hiệu lực khi cần.

Các phương thức synchronized trong ví dụ giúp thao tác publish không chạy đồng thời với việc callback đóng hoặc thay thế trường client. Trong ứng dụng thực tế, đây chưa phải toàn bộ cơ chế dừng hệ thống. Cần phối hợp với tầng nhận request, executor và consumer để ngừng nhận công việc mới, chờ các thao tác đang chạy kết thúc và bảo đảm không có đường truy cập nào bỏ qua Resource để sử dụng client trực tiếp.

## 5. Đặt Resource ở đâu trong kiến trúc ứng dụng?

Resource nên nằm gần thành phần sở hữu vòng đời tài nguyên. Ví dụ:

- Nếu một adapter sở hữu broker client, adapter hoặc một lớp quản lý vòng đời của adapter có thể triển khai Resource.
- Nếu một service quản lý một pool riêng, lớp quản lý pool có thể triển khai Resource.
- Nếu nhiều thành phần cùng phụ thuộc vào một client, nên có một chủ sở hữu rõ ràng quản lý client và đăng ký một Resource cho vòng đời đó.

Không nên để nhiều Resource cùng đóng hoặc tạo lại một tài nguyên. Điều này có thể gây đóng lặp, mở nhiều connection hoặc tạo listener trùng sau restore.

Một ứng dụng có thể đăng ký nhiều Resource. Mỗi Resource nên quản lý một ranh giới tài nguyên có ý nghĩa và có trách nhiệm rõ ràng. Khi các tài nguyên phụ thuộc lẫn nhau, cần xem xét thứ tự khởi tạo, dừng và phục hồi theo tài liệu của phiên bản CRaC API/runtime đang dùng; không để tính đúng đắn phụ thuộc vào thứ tự callback chưa được xác minh.

Đối với framework hoặc thư viện đã có CRaC integration, hãy ưu tiên cơ chế được cung cấp. Ví dụ, một thư viện có thể tự đăng ký Resource để quản lý connection pool của nó. Tạo thêm Resource bên ngoài để đóng cùng pool có thể xung đột với cơ chế tích hợp sẵn.

## 6. Các nguyên tắc khi khai báo và đăng ký Resource

**Đăng ký đúng instance.** Instance đăng ký phải là instance thực sự sở hữu tài nguyên. Không tạo một Resource phụ chỉ để đăng ký trong khi bean hoặc service khác giữ tài nguyên thật.

**Đăng ký sau khi khởi tạo thành công.** Hoàn tất việc thiết lập các trường và dependency cần thiết trước khi đăng ký. Tránh để một instance chưa hoàn chỉnh có thể nhận callback.

**Đăng ký có chủ đích và tránh trùng lặp.** Kiểm soát nơi tạo Resource để không đăng ký nhiều lần cùng một instance hoặc nhiều wrapper cho cùng một tài nguyên.

**Quản lý cả hai chiều vòng đời.** Nếu beforeCheckpoint đóng tài nguyên, afterRestore cần biết cách tạo lại tài nguyên hoặc xác minh rằng một integration khác đã phục hồi nó.

**Giữ callback tập trung vào vòng đời.** Không đưa nghiệp vụ không liên quan vào callback. Tách logic đóng, flush, reconnect và health check thành phương thức có thể quản lý và kiểm thử riêng.

**Phối hợp với luồng đang hoạt động.** Đóng tài nguyên khi request hoặc consumer vẫn đang sử dụng có thể gây lỗi. Ứng dụng cần dừng nhận việc mới và drain công việc đang chạy trước khi đóng.

**Dùng trạng thái hiện tại sau restore.** Factory phục hồi nên đọc cấu hình, credential và địa chỉ dịch vụ còn hiệu lực. Không tái sử dụng session hoặc token cũ chỉ vì object đại diện vẫn có trong heap.

**Không che giấu lỗi.** Nếu tài nguyên bắt buộc không thể đóng an toàn hoặc tạo lại, hãy để lỗi được báo lên và ngăn ứng dụng hoạt động trong trạng thái không sẵn sàng.

**Thiết kế cho nhiều chu kỳ.** Resource cần hoạt động đúng qua nhiều lần beforeCheckpoint và afterRestore. Tránh tạo listener, thread hoặc connection mới mà không giải phóng tài nguyên của chu kỳ trước.

**Xử lý checkpoint thất bại.** Không giả định mọi lần chạy beforeCheckpoint chắc chắn dẫn tới một lần afterRestore. Nếu quá trình checkpoint bị từ chối hoặc thất bại sau khi Resource đã đóng tài nguyên, ứng dụng cần có cách phục hồi phù hợp với runtime và cơ chế điều phối checkpoint đang dùng.

## 7. Những cách hiểu sai thường gặp

**Chỉ cần implements Resource là đủ.**

Chưa đủ. Class cần được đăng ký với Context. Nếu không có đăng ký hoặc tích hợp CRaC tự động tương ứng, runtime không biết instance nào cần nhận callback.

**Đăng ký class thay vì instance.**

Context.register(...) nhận một object triển khai Resource. Ứng dụng phải đăng ký instance đang sở hữu tài nguyên, không truyền tên class hoặc chỉ khai báo một bean mà không có bước đăng ký.

**Tự gọi callback để mô phỏng restore.**

Callback thuộc vòng đời do CRaC runtime điều phối. Mã nghiệp vụ không nên tự gọi beforeCheckpoint hoặc afterRestore như một cách thay thế cho checkpoint/restore thật. Có thể kiểm thử logic đóng và tạo lại bằng cách tách nó thành các phương thức riêng, sau đó kiểm thử tích hợp trên runtime CRaC.

**Resource là nơi lưu toàn bộ trạng thái ứng dụng.**

Resource chỉ là hợp đồng tham gia vòng đời. Dữ liệu nghiệp vụ vẫn cần được lưu trong hệ thống lưu trữ phù hợp; callback không biến checkpoint thành database backup hoặc transaction phân tán.

**Một Resource có thể đóng mọi tài nguyên của ứng dụng.**

Một Resource nên quản lý tài nguyên mà nó sở hữu. Đóng tài nguyên của thành phần khác có thể tạo xung đột về quyền sở hữu và thứ tự vòng đời.

**Sau restore chỉ cần tạo lại object wrapper.**

Tạo object wrapper không bảo đảm kết nối phía server, subscription, lease hoặc credential đã hợp lệ. Resource phải phục hồi hoặc xác minh chính tài nguyên mà wrapper đại diện.

## 8. Kiểm thử Resource

Có thể kiểm tra Resource theo hai cấp độ.

Ở cấp độ đơn vị, tách thao tác đóng và tạo lại thành phương thức riêng để kiểm tra:

- Tài nguyên được đóng khi chuẩn bị checkpoint.
- Gọi đóng khi tài nguyên chưa được tạo không làm phát sinh lỗi ngoài dự kiến.
- Factory được gọi để tạo tài nguyên sau restore.
- Lỗi từ factory được truyền ra để ứng dụng nhận biết trạng thái phục hồi thất bại.
- Nhiều chu kỳ đóng và tạo lại không làm tăng số lượng connection hoặc listener ngoài dự kiến.

Ở cấp độ tích hợp, chạy ứng dụng trên JDK/runtime có hỗ trợ CRaC và kiểm tra:

- Resource đã được đăng ký thực sự nhận callback.
- Ứng dụng dừng hoặc drain công việc trước khi tài nguyên bị đóng.
- Checkpoint được tạo thành công khi các Resource đã chuẩn bị xong.
- Sau restore, client kết nối được tới dịch vụ bên ngoài.
- Dependency restart hoặc credential thay đổi trong thời gian checkpoint được xử lý đúng.
- Ứng dụng chỉ nhận traffic sau khi các Resource thiết yếu đã phục hồi.
- Không có consumer, scheduler hoặc listener bị đăng ký trùng qua nhiều chu kỳ.

Một bài kiểm thử chỉ gọi trực tiếp hai phương thức callback có thể kiểm tra logic của class, nhưng chưa chứng minh CRaC runtime đã đăng ký và điều phối Resource đúng cách. Cần có kiểm thử checkpoint/restore thật để xác nhận toàn bộ vòng đời.

## 9. Kết luận

Resource là điểm mở rộng để ứng dụng tham gia có chủ đích vào vòng đời checkpoint và restore. Class triển khai interface này định nghĩa cách chuẩn bị tài nguyên trong beforeCheckpoint và cách phục hồi tài nguyên trong afterRestore. Sau khi tạo instance, ứng dụng đăng ký nó với Context, thường là Core.getGlobalContext() đối với tài nguyên cấp ứng dụng.

Khai báo và đăng ký đúng Resource giúp CRaC runtime gọi đúng thành phần ở đúng giai đoạn. Chất lượng triển khai phụ thuộc vào việc xác định rõ chủ sở hữu tài nguyên, phối hợp với công việc đang chạy, xử lý lỗi và tạo lại kết nối dựa trên trạng thái hiện tại của các hệ thống bên ngoài.
