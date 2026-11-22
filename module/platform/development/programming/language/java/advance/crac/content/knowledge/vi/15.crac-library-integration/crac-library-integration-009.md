# Đối chiếu cách tích hợp của Quarkus và Micronaut với mô hình CRaC chung

Quarkus và Micronaut đều có thể chạy ứng dụng Java từ checkpoint CRaC, nhưng cách đưa CRaC vào vòng đời framework có mức độ tích hợp khác nhau. Quarkus có hỗ trợ CRaC cơ bản trong framework từ phiên bản 2.10.0; ứng dụng có thể đăng ký resource bằng API CRaC và cần kiểm tra khả năng tương thích của các extension cùng thư viện bên dưới. Micronaut cung cấp module riêng io.micronaut.crac:micronaut-crac, tự phát hiện các bean triển khai OrderedResource, điều phối thứ tự callback và tích hợp sẵn một số tài nguyên như Hikari DataSource và Redis.

Điểm chung của cả hai vẫn là mô hình CRaC: trước checkpoint, ứng dụng phải đưa tài nguyên về trạng thái có thể chụp; sau restore, ứng dụng phải tái tạo hoặc xác minh những tài nguyên đã mất hiệu lực. Framework có thể tự điều phối một số thành phần, nhưng không thể tự hiểu mọi quy tắc nghiệp vụ, token, lease, kết nối tùy biến hoặc thư viện bên thứ ba của ứng dụng.

## 1. Mô hình CRaC chung

CRaC (Coordinated Restore at Checkpoint) cho phép lưu trạng thái một tiến trình Java đang chạy rồi khôi phục tiến trình từ ảnh đã lưu. Ảnh có thể giữ lại nhiều trạng thái trong JVM như lớp đã nạp, đối tượng trong heap và kết quả warm-up. Sau restore, tiến trình tiếp tục từ trạng thái checkpoint thay vì khởi động mọi thứ từ đầu.

Một tiến trình server thường giữ các tài nguyên mà ảnh checkpoint không thể đơn giản tiếp tục sử dụng như trước:

- Socket TCP, kết nối HTTP, JDBC và message broker.
- File descriptor, writer, file lock và tệp đang ghi.
- Connection pool, selector, event loop và thread đang chờ I/O.
- Token, session, lease, distributed lock và quyền leader có thời hạn.
- Tài nguyên native hoặc tài nguyên do thư viện bên thứ ba quản lý.

CRaC cung cấp API để ứng dụng nhận thông báo trước checkpoint và sau restore. Với API tương thích org.crac, một resource triển khai hai callback:

~~~java
import org.crac.Context;
import org.crac.Resource;

public final class ClientResource implements Resource {

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        // Dừng nhận công việc, drain và giải phóng tài nguyên.
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {
        // Tạo lại tài nguyên và xác minh dependency.
    }
}
~~~

Ứng dụng đăng ký resource với CRaC context để runtime gọi callback:

~~~java
Core.getGlobalContext().register(clientResource);
~~~

beforeCheckpoint() là nơi dừng nhận công việc mới, hoàn tất hoặc rollback transaction, flush dữ liệu và đóng kết nối. afterRestore() là nơi tạo kết nối mới, làm mới chứng thực, đăng ký lại subscription và kiểm tra readiness. Việc đăng ký resource không tự đóng hoặc mở lại tài nguyên; logic đó vẫn phải do ứng dụng hoặc integration của thư viện triển khai.

### 1.1. Ranh giới giữa CRaC API và framework

Có thể chia tích hợp thành ba lớp:

| Lớp | Trách nhiệm |
|---|---|
| CRaC runtime và API | Tạo checkpoint/restore, gọi callback, quản lý context và báo lỗi với tài nguyên không thể checkpoint |
| Framework integration | Tự đăng ký resource, điều phối lifecycle bean, quản lý các tài nguyên mà framework biết rõ |
| Ứng dụng và thư viện nghiệp vụ | Quản lý tài nguyên tùy biến, transaction, credential, cache nghiệp vụ, lease, idempotency và readiness |

Framework integration giúp giảm lượng mã phải viết, nhưng không có nghĩa mọi thư viện trên classpath đều đã CRaC-aware. Một extension có thể tạo socket hoặc thread nội bộ mà không biết thời điểm checkpoint. Khi đó, checkpoint có thể thất bại hoặc restore xong nhưng thao tác tiếp theo vẫn dùng kết nối đã đóng.

## 2. Quarkus: hỗ trợ CRaC cơ bản trong framework

CRaC ghi nhận Quarkus có hỗ trợ CRaC cơ bản từ Quarkus 2.10.0. Ứng dụng Quarkus có thể chạy trên JDK hỗ trợ CRaC, được warm-up, tạo checkpoint và restore bằng các tùy chọn của runtime. Mô hình tích hợp thường dùng là tạo một CDI bean sở hữu tài nguyên, triển khai org.crac.Resource và đăng ký bean đó với global context.

### 2.1. Đăng ký resource bằng CDI bean

Với Quarkus, có thể dùng @ApplicationScoped để khai báo bean dùng trong toàn ứng dụng, @Startup để buộc bean được khởi tạo trong startup và @PostConstruct để đăng ký resource sau khi dependency injection hoàn tất.

Ví dụ:

~~~java
package example.crac;

import jakarta.annotation.PostConstruct;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;

import io.quarkus.runtime.Startup;
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

@Startup
@ApplicationScoped
public class SearchClientResource implements Resource {

    @Inject
    SearchClient searchClient;

    @PostConstruct
    void registerResource() {
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        searchClient.stopAcceptingRequests();
        searchClient.drainRequests();
        searchClient.closeConnections();
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {
        searchClient.reconnect();
        searchClient.verifyConnection();
    }
}
~~~

SearchClient là kiểu do ứng dụng định nghĩa để minh họa một client có lifecycle. Trong ứng dụng thật, hãy gọi API chính thức của HTTP client, JDBC pool hoặc SDK. Không tự đóng socket nội bộ khi thư viện vẫn còn quản lý socket đó.

Các annotation có vai trò riêng:

- @ApplicationScoped xác định bean CDI có scope toàn ứng dụng.
- @Startup yêu cầu Quarkus khởi tạo bean trong giai đoạn startup, thay vì đợi lần đầu bean được truy cập.
- @PostConstruct chạy sau khi bean và dependency được khởi tạo; đây là vị trí thích hợp để đăng ký resource.
- implements Resource đưa logic chuẩn bị và phục hồi vào hợp đồng CRaC chung.

Nếu bean không được khởi tạo trước checkpoint, resource của nó cũng chưa được đăng ký. Vì vậy, với resource bắt buộc, cần bảo đảm bean được tạo trong startup và kiểm tra thứ tự khởi tạo của dependency.

### 2.2. Dependency và runtime

Ứng dụng cần API CRaC để biên dịch các lớp triển khai Resource. Một dependency Maven điển hình:

~~~xml
<dependency>
    <groupId>org.crac</groupId>
    <artifactId>crac</artifactId>
</dependency>
~~~

Nếu Quarkus BOM hoặc dependency management của dự án không quản lý phiên bản, hãy khai báo phiên bản org.crac:crac tương thích với JDK CRaC và phiên bản framework đang dùng. Không chọn version ngẫu nhiên chỉ để vượt qua bước compile.

Chạy ứng dụng JVM mode bằng một JDK/runtime có CRaC support. Với ứng dụng Quarkus đóng gói theo fast-jar, lệnh có thể có dạng:

~~~bash
java -XX:CRaCCheckpointTo=/var/lib/app/checkpoint \
     -jar target/quarkus-app/quarkus-run.jar
~~~

Sau khi ứng dụng khởi động và warm-up xong, có thể yêu cầu checkpoint bằng công cụ của JDK:

~~~bash
jcmd <PID> JDK.checkpoint
~~~

Khôi phục từ ảnh:

~~~bash
java -XX:CRaCRestoreFrom=/var/lib/app/checkpoint
~~~

Đây là luồng vận hành minh họa. Đường dẫn, quyền hệ điều hành, kernel, container runtime, checkpoint engine và giới hạn tương thích phải theo tài liệu của JDK CRaC được triển khai. Quarkus không thay thế các yêu cầu của runtime.

### 2.3. Kiểm tra tương thích extension và thư viện

Điểm cần chú ý khi dùng Quarkus là một ứng dụng thường có nhiều thành phần được tích hợp qua extension:

- HTTP server và client dựa trên Vert.x.
- Database pool như Agroal hoặc Hikari.
- Hibernate ORM và JDBC driver.
- Kafka client, reactive messaging và các connector.
- Redis client, scheduler, telemetry agent và thư viện native.

Mỗi thành phần có thể sở hữu socket, selector, event loop, thread hoặc file descriptor riêng. Việc Quarkus có hỗ trợ CRaC cơ bản không chứng minh rằng mọi version của các dependency này đều xử lý checkpoint/restore đúng.

Hướng dẫn CRaC cho ứng dụng Quarkus Super Heroes minh họa một trường hợp thực tế: checkpoint ban đầu gặp socket đang mở tới PostgreSQL và Kafka, selector/eventfd của Vert.x cùng các tài nguyên khác. Hướng dẫn dùng dependency đã được điều chỉnh cho CRaC ở một số thành phần Vert.x và Agroal. Các tọa độ thay thế trong ví dụ thuộc bộ version cũ của workshop; không nên sao chép chúng vào một dự án Quarkus hiện tại. Hãy dùng Quarkus platform BOM phù hợp, kiểm tra dependency tree và kiểm thử đúng phiên bản đang triển khai.

Một lỗi khác có thể xuất hiện sau khi checkpoint thành công: ứng dụng đóng pool trong beforeCheckpoint() nhưng pool không tự mở lại sau restore. Khi đó, callback cần gọi lifecycle API phù hợp hoặc tạo lại pool/client theo hướng dẫn của phiên bản thư viện. Đóng tài nguyên là một nửa quy trình; phục hồi tài nguyên là nửa còn lại.

### 2.4. Kiểm thử Quarkus

Với Quarkus, nên kiểm thử ở hai mức:

**Kiểm thử resource và CDI lifecycle**

- Xác nhận bean resource được khởi tạo khi ứng dụng startup.
- Xác nhận Core.getGlobalContext().register() được gọi.
- Kiểm tra beforeCheckpoint() dừng nhận request, drain và đóng tài nguyên.
- Kiểm tra afterRestore() tạo kết nối mới và kiểm tra dependency.
- Kiểm tra lỗi và timeout được truyền lên lifecycle thay vì bị bỏ qua.

**Kiểm thử checkpoint/restore thực tế**

- Chạy bằng CRaC-enabled JDK trên môi trường Linux phù hợp.
- Warm-up endpoint hoặc đường đi nghiệp vụ cần tối ưu.
- Yêu cầu checkpoint bằng jcmd.
- Xác nhận ảnh được tạo và không còn tài nguyên không hợp lệ.
- Restore từ ảnh và gửi request tới các dependency.
- Kiểm tra database, broker, file, scheduler, token và readiness.

Không dùng một unit test callback để kết luận toàn bộ ứng dụng có thể checkpoint. Chỉ chạy trên runtime thật mới kiểm tra được giới hạn của socket, selector, file descriptor, thư viện native và container.

## 3. Micronaut: module CRaC chuyên biệt

Micronaut cung cấp module io.micronaut.crac:micronaut-crac để tích hợp CRaC với BeanContext và lifecycle của framework. Module này phụ thuộc transitively vào org.crac:crac, tự đăng ký các bean triển khai OrderedResource vào CRaC context và cung cấp một số integration cho tài nguyên phổ biến.

Dependency Gradle:

~~~kotlin
dependencies {
    implementation("io.micronaut.crac:micronaut-crac")
}
~~~

Dependency Maven:

~~~xml
<dependency>
    <groupId>io.micronaut.crac</groupId>
    <artifactId>micronaut-crac</artifactId>
</dependency>
~~~

Nếu dự án không dùng BOM hoặc dependency management tương ứng, hãy chọn version của module tương thích với Micronaut Framework và JDK CRaC. Tài liệu module và release notes là nguồn xác nhận API theo version.

### 3.1. OrderedResource và tự động đăng ký bean

Micronaut CRaC định nghĩa OrderedResource, một interface mở rộng org.crac.Resource và io.micronaut.core.order.Ordered:

~~~java
public interface OrderedResource
        extends org.crac.Resource,
                io.micronaut.core.order.Ordered {
}
~~~

Module Micronaut CRaC tự tìm và đăng ký các bean có kiểu OrderedResource với CRaC context. Ứng dụng tập trung viết callback và chỉ định thứ tự khi có quan hệ phụ thuộc.

Ví dụ:

~~~java
package example.micronaut;

import io.micronaut.crac.OrderedResource;
import jakarta.inject.Singleton;
import org.crac.Context;
import org.crac.Resource;

@Singleton
public class SearchClientResource implements OrderedResource {

    private final SearchClient searchClient;

    public SearchClientResource(SearchClient searchClient) {
        this.searchClient = searchClient;
    }

    @Override
    public int getOrder() {
        return 100;
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        searchClient.stopAcceptingRequests();
        searchClient.drainRequests();
        searchClient.closeConnections();
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {
        searchClient.reconnect();
        searchClient.verifyConnection();
    }
}
~~~

SearchClient cũng là kiểu minh họa do ứng dụng định nghĩa. Không cần gọi Core.getGlobalContext().register(this) trong bean này vì Micronaut CRaC tự đăng ký OrderedResource.

Khác biệt quan trọng là cơ chế đăng ký được gắn với BeanContext. Nếu ứng dụng chỉ triển khai org.crac.Resource mà không triển khai OrderedResource, không nên giả định module sẽ tự phát hiện bean đó theo cơ chế mặc định. Với resource tùy biến, hãy triển khai đúng interface mà module yêu cầu.

Để resource được đăng ký, bean phải được tạo trước checkpoint. Nếu ứng dụng thay đổi cấu hình khởi tạo singleton hoặc dùng bean lazy, hãy bảo đảm resource được materialize trong startup. Có thể dùng scope khởi tạo sớm phù hợp với ứng dụng, chẳng hạn @Context, nếu cần ép một bean cụ thể được tạo khi context bắt đầu.

### 3.2. Điều khiển thứ tự resource

Khi có nhiều resource phụ thuộc nhau, Micronaut CRaC cho phép dùng OrderedResource.getOrder() để điều khiển thứ tự đăng ký.

Ví dụ, OrderConsumer sử dụng DatabasePool:

- Trước checkpoint, consumer phải dừng trước khi pool bị đóng.
- Sau restore, pool phải sẵn sàng trước khi consumer khởi động lại.

Hãy sắp xếp order theo quy tắc đăng ký của module và xác nhận callback thực tế trong test. Trong mô hình CRaC Context thông thường, beforeCheckpoint() chạy theo thứ tự ngược đăng ký, còn afterRestore() chạy theo thứ tự đăng ký. Do đó, thứ tự đăng ký cần phản ánh đồ thị phụ thuộc chứ không chỉ là thứ tự alphabet của tên bean.

Không để hai resource cùng sở hữu và đóng một client. Nếu một pool được module quản lý sẵn, không tạo thêm resource riêng đóng chính pool đó trừ khi đã xác định rõ cách phối hợp.

### 3.3. Hỗ trợ Hikari DataSource

Micronaut CRaC có integration cho Hikari DataSource khi pool được cấu hình cho phép suspension:

~~~yaml
datasources:
  default:
    allow-pool-suspension: true
~~~

Khi checkpoint, pool được suspend và các connection được đóng. Sau restore, pool được resume và các connection được thiết lập lại. Cơ chế này giúp ứng dụng không phải tự viết callback quản lý từng JDBC connection.

Điều kiện là DataSource thực sự dùng Hikari và version/configuration tương thích. Nếu ứng dụng dùng pool khác hoặc driver có lifecycle riêng, cần kiểm tra integration tương ứng hoặc viết resource tùy biến.

### 3.4. Hỗ trợ Redis và refresh scope

Module Micronaut CRaC cũng có integration cho một số bean Redis như:

- RedisClient
- RedisCache
- StatefulRedisConnection

Theo tài liệu module, các bean được hỗ trợ sẽ bị hủy khi checkpoint và được tạo lại sau restore. Những bean ứng dụng giữ tham chiếu tới các client/cache này cần nằm trong @Refreshable scope để nhận instance mới sau khi refresh.

Ví dụ:

~~~java
import io.micronaut.runtime.context.scope.Refreshable;

@Refreshable
public class ProductCacheService {

    private final RedisClient redisClient;

    public ProductCacheService(RedisClient redisClient) {
        this.redisClient = redisClient;
    }
}
~~~

Các kiểu Redis ở ví dụ cần được import từ thư viện Redis thực tế của dự án. Điểm chính là service giữ tham chiếu tới bean được tạo lại phải tham gia refresh scope, nếu không nó có thể tiếp tục dùng tham chiếu cũ.

Micronaut CRaC phát RefreshEvent trước checkpoint để invalidate các bean trong @Refreshable scope. Có thể tắt hành vi này bằng:

~~~yaml
crac:
  refresh-beans: false
~~~

Chỉ tắt khi ứng dụng có cơ chế thay thế và đã xác minh không còn bean refreshable nào cần tái tạo. Nếu tắt mặc định refresh mà vẫn giữ tham chiếu tới client cũ, restore có thể thành công nhưng các thao tác Redis sau đó thất bại.

Các integration Redis có thể được bật/tắt theo nhóm hoặc theo loại bean bằng các property module cung cấp, ví dụ crac.redis.enabled, crac.redis.client-enabled, crac.redis.cache-enabled và crac.redis.connection-enabled. Hãy kiểm tra tài liệu đúng version trước khi dùng property này vì module có thể thay đổi tên hoặc phạm vi cấu hình qua các release.

### 3.5. Events và Context Provider

Micronaut CRaC công bố các event:

- BeforeCheckpointEvent
- AfterRestoreEvent

Event chứa thời điểm hoàn tất, thời lượng thực thi tính bằng nanosecond và resource được xử lý. Ứng dụng có thể dùng chúng để ghi log lifecycle, thu thập metric hoặc kích hoạt hành động quan sát phù hợp.

Module cũng cung cấp CracContextProvider; implementation mặc định GlobalCracContextProvider trả về global context. Ứng dụng có thể thay provider nếu cần một CRaC context riêng theo kiến trúc tích hợp.

Không dùng event quan sát để thay callback resource. Event cho biết một thao tác lifecycle đã diễn ra; resource vẫn là nơi thực hiện việc đóng, mở và kiểm tra tài nguyên.

### 3.6. CheckpointSimulator và kiểm thử

Micronaut CRaC cung cấp CheckpointSimulator để mô phỏng việc gọi callback trước checkpoint và sau restore trong test. Ví dụ:

~~~java
@Inject
BeanContext beanContext;

@Test
void resourceIsStoppedAndStartedAgain() {
    ResourceBean resource =
            beanContext.getBean(ResourceBean.class);
    CheckpointSimulator simulator =
            beanContext.getBean(CheckpointSimulator.class);

    assertTrue(resource.isRunning());

    simulator.runBeforeCheckpoint();
    assertFalse(resource.isRunning());

    simulator.runAfterRestore();
    assertTrue(resource.isRunning());
}
~~~

Ví dụ này kiểm tra logic callback và trạng thái bean. CheckpointSimulator không tạo ảnh tiến trình thật, không gọi CRIU và không chứng minh mọi file descriptor hoặc socket trên hệ điều hành có thể checkpoint. Vẫn cần một integration test với CRaC-enabled JDK để kiểm tra runtime.

Micronaut CRaC documentation cũng lưu ý về eager singleton initialization trong ứng dụng và test. Nếu test inject một bean khiến client khởi tạo quá sớm, có thể cần tắt eager initialization trong test hoặc tạo bean client theo cách lazy phù hợp. Đây là khác biệt cần chú ý khi thiết kế test cho resource và HTTP client.

### 3.7. Hỗ trợ tạo Docker image

Micronaut có Gradle và Maven plugin hỗ trợ tạo image có JDK CRaC và ứng dụng đã warm-up/checkpoint. Với Gradle, tài liệu plugin mô tả task dockerBuildCrac, có thể:

1. Tạo image nền chứa JDK hỗ trợ CRaC và ứng dụng.
2. Khởi chạy ứng dụng.
3. Chạy warm-up script.
4. Tạo checkpoint.
5. Đóng gói checkpoint cùng runtime và ứng dụng vào image mới.

Tài liệu plugin hiện hành có cảnh báo trạng thái experimental đối với CRaC plugin. Cần kiểm tra version, hệ điều hành đã được kiểm thử và trạng thái hỗ trợ trước khi dùng trong pipeline production. Plugin chỉ hỗ trợ quy trình đóng gói; nó không thể sửa một callback resource sai hoặc làm dependency không tương thích trở nên an toàn.

## 4. So sánh trực tiếp Quarkus và Micronaut

| Khía cạnh | Quarkus | Micronaut |
|---|---|---|
| Hình thức tích hợp | Hỗ trợ CRaC cơ bản trong framework | Module CRaC chuyên biệt |
| Mốc hỗ trợ được công bố | Basic CRaC support từ Quarkus 2.10.0 | Module io.micronaut.crac:micronaut-crac |
| API nền | org.crac | org.crac thông qua module Micronaut |
| Đăng ký resource tùy biến | Bean/CDI triển khai Resource, thường tự đăng ký qua Core.getGlobalContext() | Bean triển khai OrderedResource; module tự đăng ký |
| Quản lý thứ tự | Theo thứ tự đăng ký của CRaC context; ứng dụng phải tổ chức resource | OrderedResource tích hợp Ordered, có thể điều khiển bằng getOrder() |
| Tích hợp DataSource | Phải xác nhận extension, pool và driver có hỗ trợ; có thể cần resource riêng | Có hỗ trợ Hikari DataSource suspension khi bật allow-pool-suspension |
| Redis | Kiểm tra lifecycle của extension/client và tự phối hợp nếu cần | Có integration cho RedisClient, RedisCache và StatefulRedisConnection |
| Tái tạo bean | Dùng CDI lifecycle và logic ứng dụng; cần xác định cách cập nhật reference | Có @Refreshable scope và RefreshEvent để invalidate bean được quản lý |
| Event quan sát | Dùng CRaC callback và cơ chế event/observer của Quarkus | Có BeforeCheckpointEvent và AfterRestoreEvent của module |
| Test lifecycle | Test resource/CDI và kiểm thử checkpoint thật | Có CheckpointSimulator cùng test CRaC thật |
| Đóng gói image | Dùng build/container pipeline và JDK CRaC phù hợp | Có Gradle/Maven plugin hỗ trợ image checkpoint; trạng thái plugin cần kiểm tra theo version |
| Rủi ro chính | Tính tương thích của các extension và dependency trong stack | Bean reference, refresh scope và phạm vi integration của module |

### 4.1. Khác biệt về cách đăng ký

Quarkus thường để bean tự đăng ký:

~~~java
@Startup
@ApplicationScoped
public class QuarkusResource implements Resource {

    @PostConstruct
    void register() {
        Core.getGlobalContext().register(this);
    }

    // beforeCheckpoint() và afterRestore()
}
~~~

Micronaut CRaC dùng loại bean có interface riêng:

~~~java
@Singleton
public class MicronautResource implements OrderedResource {

    @Override
    public int getOrder() {
        return 100;
    }

    // beforeCheckpoint() và afterRestore()
}
~~~

Sự khác biệt này ảnh hưởng đến cách tổ chức mã. Với Quarkus, người viết cần chủ động đăng ký resource và bảo đảm bean được tạo. Với Micronaut, module đảm nhận việc tìm và đăng ký bean OrderedResource; người viết tập trung vào callback và thứ tự.

### 4.2. Khác biệt về tài nguyên framework quản lý sẵn

Micronaut CRaC có danh sách integration được module công bố, chẳng hạn Hikari và Redis. Những integration này giảm việc phải viết callback cho các loại bean đã được hỗ trợ.

Quarkus có nhiều extension và dependency nằm dưới cùng một ứng dụng. Tài liệu CRaC mô tả hỗ trợ cơ bản trong framework, nhưng cần kiểm tra từng extension/version để biết tài nguyên nào đã được điều phối. Ví dụ Super Heroes cho thấy Vert.x, Agroal và Kafka có thể tạo socket, selector hoặc connection gây lỗi checkpoint nếu version đang dùng chưa tương thích.

Không nên suy luận rằng Quarkus không thể quản lý pool hoặc Redis. Cách hiểu đúng là phải kiểm tra integration cụ thể của Quarkus platform và version thư viện. Tương tự, không nên giả định mọi Redis client hoặc mọi pool trong Micronaut đều được module tự xử lý chỉ vì một số loại đã có integration.

### 4.3. Khác biệt về kiểm thử

Micronaut có CheckpointSimulator để gọi các callback và kiểm tra thứ tự cùng trạng thái bean trong test. Điều này thuận tiện cho kiểm thử nhanh logic beforeCheckpoint()/afterRestore().

Quarkus có thể kiểm thử resource bằng JUnit và Quarkus test lifecycle, nhưng cần tự tổ chức cách gọi callback hoặc kiểm tra bean. Với cả hai framework, simulator hoặc unit test chỉ xác minh logic ứng dụng. Chỉ một lần checkpoint/restore thật mới phát hiện được lỗi từ CRaC runtime, kernel, socket, selector, file descriptor và thư viện native.

## 5. Mô hình triển khai chung cho cả hai framework

Dù chọn Quarkus hay Micronaut, có thể dùng cùng một quy trình thiết kế.

### 5.1. Trước checkpoint

1. Ngừng nhận request và message mới.
2. Drain các request đang chạy và các queue nội bộ.
3. Commit hoặc rollback transaction theo quy tắc nghiệp vụ.
4. Dừng consumer, scheduler và worker cần được tái tạo.
5. Flush file writer và đóng tài nguyên hệ điều hành không thể tiếp tục sử dụng.
6. Đóng hoặc suspend connection pool/client theo API chính thức.
7. Giải phóng lease/lock nếu giao thức yêu cầu.
8. Báo lỗi nếu resource không thể đạt trạng thái an toàn trong thời hạn cho phép.

### 5.2. Sau restore

1. Đọc lại cấu hình và metadata của môi trường hiện tại.
2. Tạo lại socket, connection pool và client.
3. Nạp lại truststore, chứng chỉ, token hoặc secret nếu chúng có thể thay đổi.
4. Tạo lại worker, scheduler và consumer.
5. Tham gia lại broker group hoặc service registry.
6. Xin lease/lock mới và xác minh quyền sở hữu bằng fencing token khi cần.
7. Làm mới cache có thể đã lỗi thời.
8. Chỉ mở readiness sau khi dependency bắt buộc đã sẵn sàng.

Luồng tổng quát:

~~~mermaid
flowchart TD
    A[Framework khởi động ứng dụng] --> B[Khởi tạo bean và dependency]
    B --> C[Warm-up trạng thái có thể tái sử dụng]
    C --> D[Đăng ký CRaC resources]
    D --> E[Ứng dụng phục vụ]
    E --> F[beforeCheckpoint]
    F --> G[Quiesce, drain và đóng tài nguyên]
    G --> H[CRaC checkpoint]
    H --> I[CRaC restore]
    I --> J[afterRestore]
    J --> K[Tạo lại kết nối và xác minh trạng thái]
    K --> L[Readiness]
    L --> M[Tiếp tục phục vụ]
~~~

Không nhất thiết mọi tài nguyên phải được tạo lại theo cùng một thứ tự. Nếu resource B phụ thuộc resource A, A phải được phục hồi trước B và B phải được dừng trước A. Hãy dùng thứ tự đăng ký phù hợp với CRaC context hoặc OrderedResource của Micronaut.

## 6. Quản lý dữ liệu và trạng thái có thời hạn

Framework lifecycle không thay thế các quy tắc nhất quán của hệ thống phân tán.

### 6.1. Cache

Cache đã được warm-up trước checkpoint có thể giúp giảm thời gian khởi động. Nhưng trong lúc JVM dừng, dữ liệu gốc có thể thay đổi hoặc TTL có thể hết hạn. Hãy phân loại:

- Cache bất biến hoặc có version cố định: có thể giữ lại nếu vẫn phù hợp.
- Cache dữ liệu nghiệp vụ thay đổi: refresh hoặc kiểm tra version sau restore.
- Cache gắn với identity replica: tạo namespace riêng cho replica hiện tại.
- Cache chứa token/session: làm mới theo chính sách chứng thực.

### 6.2. ID và danh tính replica

Nếu cùng một checkpoint được dùng để tạo nhiều replica, các giá trị trong heap có thể được nhân bản. Hãy tạo hoặc truy vấn instance ID sau restore. Không dùng một static UUID được tạo trước checkpoint làm ID riêng cho tất cả replica.

Service identity có thể dùng chung; replica identity và process incarnation ID cần phân biệt. Consumer member ID, socket path, file tạm và lease token cần được cấp lại theo phạm vi sở hữu.

### 6.3. Token và chứng chỉ

Access token, refresh token, chứng chỉ client và private key có thể hết hạn hoặc bị rotate trong thời gian tiến trình dừng. Sau restore, hãy lấy credential từ identity provider hoặc secret manager theo workload hiện tại. Không mặc định một đối tượng credential trong heap vẫn còn hợp lệ.

### 6.4. Lease và quyền leader

Không giữ leader=true hoặc trạng thái lock từ checkpoint làm bằng chứng quyền sở hữu hiện tại. Lease có thể đã hết hạn và được cấp cho replica khác. Sau restore, hãy đăng ký lại với coordinator và dùng fencing token được kiểm tra tại nơi thực hiện ghi.

## 7. Các lỗi thường gặp khi so sánh và triển khai

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Quarkus checkpoint thất bại vì open socket | Extension hoặc dependency giữ socket không được đóng | Xác định chủ sở hữu socket, nâng version tương thích hoặc viết integration |
| Quarkus restore xong nhưng database không truy cập được | Pool đã đóng nhưng không được tái tạo/resume | Dùng API lifecycle của pool hoặc tạo pool mới trong callback |
| Quarkus bean resource không được gọi | Bean chưa được khởi tạo hoặc chưa đăng ký | Dùng startup bean và xác nhận đăng ký hoàn tất |
| Micronaut không gọi resource tùy biến | Bean chỉ triển khai Resource thay vì OrderedResource hoặc bean chưa được tạo | Triển khai OrderedResource và bảo đảm bean được materialize |
| Micronaut Redis service vẫn dùng client cũ | Bean giữ tham chiếu không nằm trong refresh scope | Đặt bean phù hợp vào @Refreshable hoặc quản lý reference mới |
| Hikari pool không resume | Pool không bật suspension hoặc cấu hình/version không được hỗ trợ | Bật allow-pool-suspension và kiểm tra integration |
| Callback chạy sai thứ tự | Resource có quan hệ phụ thuộc nhưng thứ tự đăng ký chưa đúng | Sắp xếp context registration hoặc getOrder |
| Restore thành công nhưng request đầu tiên lỗi | Readiness mở trước khi dependency sẵn sàng | Health check kết nối và chỉ mở readiness sau bootstrap |
| Test simulator pass nhưng CRaC thật thất bại | Simulator không tạo ảnh tiến trình và không kiểm tra file/socket hệ điều hành | Thêm integration test với JDK CRaC trên Linux |
| Nhiều replica dùng cùng consumer/lease identity | ID hoặc quyền sở hữu được snapshot và nhân bản | Tạo identity riêng và acquire lease mới sau restore |
| Checkpoint chờ vô hạn | Callback drain hoặc I/O không có deadline | Đặt timeout và chính sách hủy checkpoint |

## 8. Cách chọn framework theo nhu cầu tích hợp

Quarkus phù hợp khi dự án đã sử dụng hệ sinh thái extension của Quarkus và đội ngũ có thể quản lý rõ dependency tree cùng lifecycle của các client. Cần dành công sức kiểm tra CRaC compatibility cho từng extension và viết resource CDI cho tài nguyên riêng của ứng dụng. Nếu ứng dụng có nhiều Vert.x, Kafka, database hoặc native dependency, hãy kiểm thử checkpoint sớm trong quá trình phát triển.

Micronaut phù hợp khi muốn dùng một module CRaC chuyên biệt gắn với BeanContext, tự đăng ký OrderedResource và các integration đã được module hỗ trợ. Hikari/Redis support, refresh scope, event và simulator có thể giảm lượng lifecycle code cần viết. Tuy nhiên, cần xác nhận đúng version module, loại client được hỗ trợ và scope của bean giữ tham chiếu tới tài nguyên được tái tạo.

Không nên chọn chỉ dựa vào số lượng dòng callback phải viết. Hãy đánh giá:

- Phiên bản framework và runtime CRaC có được hỗ trợ trong môi trường mục tiêu không?
- Database pool, HTTP client, Redis, Kafka và telemetry stack có integration phù hợp không?
- Ứng dụng có nhiều tài nguyên tùy biến hoặc native resource không?
- Có thể kiểm thử callback trong unit test và checkpoint/restore thật trong CI không?
- Pipeline build image và vận hành checkpoint có phù hợp với hạ tầng không?
- Đội ngũ có thể theo dõi version, dependency compatibility và thay đổi lifecycle khi nâng framework không?

## 9. Checklist triển khai dùng chung

### Framework và build

- Xác nhận version Quarkus hoặc Micronaut đang dùng có CRaC support.
- Dùng org.crac API tương thích với JDK/runtime.
- Kiểm tra dependency tree và các extension tạo socket, file, thread hoặc native resource.
- Không sao chép version dependency CRaC-patched từ một ví dụ cũ mà chưa kiểm tra compatibility.

### Resource lifecycle

- Mỗi tài nguyên có một chủ sở hữu lifecycle rõ ràng.
- Resource được đăng ký trước khi checkpoint bắt đầu.
- Callback trước checkpoint có drain, timeout và cleanup rõ ràng.
- Callback sau restore tạo lại kết nối và xác minh dependency.
- Thứ tự callback phản ánh quan hệ phụ thuộc.
- Không để hai resource cùng đóng một tài nguyên.

### Trạng thái ứng dụng

- Cache có chính sách freshness.
- Token và chứng chỉ được làm mới khi cần.
- Replica identity được tạo hoặc truy vấn lại.
- Lease và quyền leader được acquire lại.
- Consumer, scheduler và worker được khởi động đúng một lần.
- Readiness chỉ mở khi ứng dụng thực sự phục vụ được.

### Kiểm thử và vận hành

- Unit test từng resource.
- Với Micronaut, dùng CheckpointSimulator để kiểm tra callback.
- Chạy checkpoint/restore thật bằng JDK CRaC trên môi trường tương thích.
- Kiểm tra lỗi khi database, broker hoặc secret service chưa sẵn sàng.
- Restore nhiều replica từ cùng một ảnh nếu môi trường có scale-out.
- Theo dõi thời gian checkpoint, restore, callback và readiness.
- Bảo vệ checkpoint image vì heap có thể chứa token, password và private key.

## 10. Nguồn tài liệu tham khảo

- [CRaC — Quarkus integration](https://crac.org/frameworks/quarkus/): ghi nhận hỗ trợ CRaC cơ bản trong Quarkus từ phiên bản 2.10.0.
- [CRaC — Micronaut integration](https://micronaut-projects.github.io/micronaut-crac/snapshot/guide/): dependency, OrderedResource, Hikari, Redis, refresh scope, events, context provider và CheckpointSimulator.
- [Micronaut Guide — CRaC](https://guides.micronaut.io/latest/micronaut-crac-helloworld-gradle-java.html): ví dụ ứng dụng Micronaut sử dụng module CRaC.
- [CRaC documentation — Running Quarkus Super Heroes with CRaC](https://github.com/CRaC/docs/blob/master/super-heroes.md): ví dụ thực tế về dependency không tương thích, socket, selector và thay thế dependency trong một ứng dụng Quarkus.
- [CRaC — What is CRaC?](https://crac.org/about/about-crac/): mô hình checkpoint/restore và trách nhiệm phối hợp tài nguyên.
- [Quarkus — AWS Lambda SnapStart guide](https://quarkus.io/version/3.33/guides/aws-lambda-snapstart/): ví dụ Quarkus CDI bean triển khai org.crac.Resource; đây là tích hợp Lambda SnapStart nên cần phân biệt lifecycle của Lambda với quy trình CRaC độc lập.

Tài liệu framework và module thay đổi theo version. Khi áp dụng vào dự án thật, hãy ưu tiên tài liệu đúng version của Quarkus, Micronaut, CRaC runtime và các extension đang dùng.

## 11. Kết luận

Quarkus cung cấp hỗ trợ CRaC cơ bản trong framework và cho phép ứng dụng đăng ký resource qua CDI cùng API org.crac. Phần cần chú ý là tính tương thích của toàn bộ extension/dependency và cách từng client được tạo lại sau restore. Micronaut có module CRaC chuyên biệt, tự đăng ký OrderedResource, quản lý thứ tự và cung cấp integration cho một số tài nguyên phổ biến cùng công cụ mô phỏng callback trong test.

Cả hai cùng tuân theo mô hình CRaC chung: chuẩn bị tài nguyên trước checkpoint, khôi phục tài nguyên sau restore và chỉ phục vụ khi dependency đã sẵn sàng. Khác biệt nằm ở mức framework tự động hóa lifecycle và các integration có sẵn; ứng dụng vẫn phải chịu trách nhiệm cho trạng thái nghiệp vụ, credential, identity, lease và những thư viện chưa được framework quản lý.
