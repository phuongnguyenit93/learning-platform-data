# @PreDestroy, DisposableBean và destroyMethod

Một Spring bean thường không chỉ được tạo ra rồi sử dụng mãi mãi. Trong suốt vòng đời ứng dụng, bean có thể mở kết nối, tạo thread pool, giữ file handle, khởi tạo client gọi dịch vụ ngoài hoặc sở hữu một tài nguyên cần đóng khi ứng dụng dừng. Nếu những tài nguyên này không được giải phóng đúng cách, ứng dụng có thể giữ kết nối không cần thiết, không flush dữ liệu, để thread chạy nền tiếp tục hoạt động hoặc làm quá trình shutdown kéo dài.

Spring cung cấp các cơ chế callback để bean thực hiện công việc dọn dẹp khi vòng đời của nó kết thúc. Ba cách thường gặp là:

- **`@PreDestroy`:** đánh dấu phương thức được gọi trước khi bean bị hủy.
- **`DisposableBean`:** implement interface của Spring và cung cấp phương thức `destroy()`.
- **`destroyMethod`:** khai báo tên phương thức hủy tùy chỉnh tại bean definition, thường qua `@Bean`.

Ba cơ chế cùng phục vụ giai đoạn kết thúc vòng đời bean nhưng khác nhau về cách khai báo, mức độ gắn với Spring và nơi phù hợp để sử dụng. Hiểu đúng chúng giúp quản lý tài nguyên có chủ đích và tránh nhầm lẫn giữa việc dừng một bean với việc thực hiện một nghiệp vụ thông thường.

## 1. Vì sao bean cần callback hủy?

Xét một service tạo thread pool để xử lý báo cáo:

~~~java
@Service
public class ReportWorker {
    private final ExecutorService executor =
            Executors.newFixedThreadPool(4);

    public void submit(Runnable task) {
        executor.submit(task);
    }
}
~~~

`ExecutorService` giữ các worker thread. Nếu ứng dụng dừng mà không yêu cầu executor shutdown, các thread hoặc tác vụ đang chạy có thể tiếp tục giữ tài nguyên và ảnh hưởng quá trình kết thúc tiến trình.

Một ví dụ khác là client của dịch vụ bên ngoài:

~~~java
public class VendorClient implements AutoCloseable {
    @Override
    public void close() {
        // Đóng connection pool hoặc tài nguyên nội bộ.
    }
}
~~~

Nếu `VendorClient` mở connection pool khi được tạo, cần đóng pool khi bean không còn được sử dụng. Tương tự, các bean có thể sở hữu:

- Connection pool hoặc client HTTP.
- Thread pool, scheduler và worker nền.
- File, stream, socket hoặc native handle.
- Buffer cần flush hoặc tài nguyên cần hoàn tất.
- Kết nối tới message broker hoặc hệ thống ngoài.

Một callback hủy cho phép bean thực hiện cleanup tại thời điểm container kết thúc quản lý instance. Với singleton, thời điểm này thường là khi ApplicationContext đóng.

### Khởi tạo và hủy là hai nửa của vòng đời

Có thể hình dung vòng đời rút gọn:

~~~text
Bean definition
      |
      v
Tạo instance
      |
      v
Tiêm dependency
      |
      v
Callback khởi tạo
      |
      v
Bean hoạt động
      |
      v
ApplicationContext đóng
      |
      v
Callback hủy
      |
      v
Giải phóng tài nguyên
~~~

`@PostConstruct`, `InitializingBean.afterPropertiesSet()` và `initMethod` thuộc nhóm callback khởi tạo. `@PreDestroy`, `DisposableBean.destroy()` và `destroyMethod` thuộc nhóm callback hủy.

Callback hủy chỉ được Spring quản lý đối với những instance và scope mà container có trách nhiệm quản lý vòng đời. Một object được tạo bằng `new` trong mã nghiệp vụ không tự động nhận callback chỉ vì class có annotation Spring.

## 2. @PreDestroy: đánh dấu phương thức trước khi bean bị hủy

`@PreDestroy` là annotation thuộc Common Annotations, được Spring hỗ trợ để đánh dấu phương thức cleanup. Phương thức được gọi trong giai đoạn hủy bean, trước khi instance được loại khỏi container.

Ví dụ với Spring Boot 3 và Spring Framework 6:

~~~java
package com.example.store.infrastructure;

import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;

@Component
public class CacheConnection {

    public void refresh() {
        // Sử dụng kết nối cache.
    }

    @PreDestroy
    public void close() {
        // Đóng kết nối hoặc giải phóng tài nguyên.
        System.out.println("Closing cache connection");
    }
}
~~~

Khi bean `CacheConnection` được Spring quản lý và vòng đời scope của nó kết thúc, Spring gọi phương thức `close()` đã đánh dấu.

### Quy tắc cơ bản của phương thức @PreDestroy

Phương thức lifecycle được đánh dấu cần có dạng phù hợp:

- Không nhận tham số.
- Trả về `void`.
- Là phương thức instance, không phải phương thức static.
- Được khai báo trên bean mà Spring quản lý.
- Chứa công việc cleanup an toàn và có thời gian thực thi hợp lý.

Phương thức có thể đặt tên tùy ý như `cleanup()`, `close()` hoặc `stopWorker()`; Spring nhận diện bằng annotation chứ không dựa vào tên. Ví dụ:

~~~java
@Component
public class TemporaryFileManager {
    @PreDestroy
    void removeTemporaryFiles() {
        // Dọn file tạm thuộc quyền sở hữu của bean.
    }
}
~~~

Trong dự án Java module hoặc môi trường có giới hạn truy cập reflection, cần đảm bảo framework có thể truy cập phương thức lifecycle. Dùng phương thức dễ đọc và không cần tham số là cách an toàn, dễ bảo trì.

### Package annotation phụ thuộc phiên bản Spring

Một khác biệt quan trọng giữa các thế hệ Spring:

| Nền tảng | Package annotation thường dùng |
|---|---|
| Spring Framework 5 / Spring Boot 2 | `javax.annotation.PreDestroy` |
| Spring Framework 6 / Spring Boot 3 | `jakarta.annotation.PreDestroy` |

Ví dụ ở bài này dùng `jakarta.annotation.PreDestroy` theo thế hệ Spring Boot 3. Nếu dự án cũ vẫn dùng Spring Boot 2, cần dùng namespace `javax.annotation` và dependency annotation tương ứng. Không nên trộn `javax.annotation.PreDestroy` và `jakarta.annotation.PreDestroy` trong cùng một ứng dụng rồi kỳ vọng Spring nhận diện cả hai như nhau.

Annotation API cần có trên classpath. Việc nó được cung cấp sẵn hay cần khai báo thêm phụ thuộc vào phiên bản Spring Boot và dependency của dự án.

### @PreDestroy không phải nơi thực hiện nghiệp vụ kết thúc đơn hàng

Một callback hủy nên phục vụ việc giải phóng tài nguyên thuộc về bean, chẳng hạn đóng pool hoặc dừng executor. Không nên dựa vào callback này để:

- Gửi hóa đơn hoặc thanh toán cho khách hàng.
- Chuyển trạng thái nghiệp vụ quan trọng.
- Gửi thông báo mà hệ thống bắt buộc phải bảo đảm.
- Lưu một giao dịch nghiệp vụ duy nhất trước khi shutdown.
- Thực hiện một quy trình cần retry và xác nhận từ hệ thống ngoài.

Quá trình shutdown có thể bị ngắt đột ngột do mất điện, kill process hoặc lỗi hạ tầng. Nếu một hành động phải được bảo đảm, hãy thực hiện trong use case có transaction, persistence, retry hoặc message delivery phù hợp; cleanup callback chỉ nên là cơ chế kết thúc tài nguyên.

## 3. DisposableBean: implement interface của Spring

Spring cung cấp interface `org.springframework.beans.factory.DisposableBean`. Bean implement interface này phải định nghĩa phương thức:

~~~java
void destroy() throws Exception;
~~~

Ví dụ:

~~~java
package com.example.store.infrastructure;

import org.springframework.beans.factory.DisposableBean;
import org.springframework.stereotype.Component;

@Component
public class MessageBrokerConnection implements DisposableBean {

    public void publish(String message) {
        // Gửi message.
    }

    @Override
    public void destroy() throws Exception {
        // Đóng connection tới broker.
        System.out.println("Closing broker connection");
    }
}
~~~

Khi bean được container quản lý đi tới giai đoạn hủy, Spring gọi `destroy()`.

### Ưu điểm và hạn chế

`DisposableBean` có một ưu điểm rõ ràng: contract của interface thể hiện trực tiếp rằng bean có hành vi cleanup. Tuy nhiên, class phải phụ thuộc vào API của Spring Framework:

~~~java
import org.springframework.beans.factory.DisposableBean;
~~~

Điều này làm class gắn chặt hơn với framework. Nếu muốn tái sử dụng class như một thành phần Java thuần hoặc không muốn lifecycle contract của Spring xuất hiện trong domain/infrastructure API, annotation hoặc phương thức close theo chuẩn Java có thể phù hợp hơn.

`DisposableBean` thường hợp lý trong một số class hạ tầng đã phụ thuộc Spring và muốn dùng trực tiếp lifecycle contract của framework. Với class ứng dụng thông thường, `@PreDestroy` thường ít xâm lấn hơn.

### Không cần vừa implement DisposableBean vừa gọi destroy thủ công

Container đã có trách nhiệm gọi callback cho bean. Không nên viết thêm một nơi khác tùy tiện gọi `destroy()` khi bean vẫn đang được sử dụng, vì có thể đóng tài nguyên quá sớm hoặc hai luồng cleanup cùng thao tác trên một resource.

Nếu class cần một API đóng tường minh cho cả container và client Java thuần, có thể thiết kế một phương thức `close()` và để callback gọi nó. Nhưng phải xác định rõ ai sở hữu vòng đời và tránh nhiều bên cùng đóng một tài nguyên không an toàn.

## 4. destroyMethod: cấu hình phương thức hủy trong bean definition

Trong một số trường hợp, class không do dự án sở hữu hoặc không nên sửa để thêm annotation/interface. Spring cho phép khai báo phương thức hủy tại nơi định nghĩa bean.

Cách thường gặp là thuộc tính `destroyMethod` của `@Bean`:

~~~java
@Configuration
public class ClientConfiguration {

    @Bean(destroyMethod = "close")
    public VendorClient vendorClient() {
        return new VendorClient();
    }
}
~~~

Khi ApplicationContext đóng, Spring gọi phương thức `close()` của instance do phương thức factory tạo ra, nếu bean được quản lý và phương thức phù hợp.

Đây là lựa chọn hữu ích khi:

- Đối tượng đến từ thư viện bên thứ ba.
- Không thể hoặc không muốn sửa class để thêm `@PreDestroy`.
- Muốn khai báo lifecycle ngay tại composition root.
- Phương thức cleanup có tên riêng như `shutdown()` hoặc `stop()`.

Ví dụ với tên khác:

~~~java
@Bean(destroyMethod = "shutdown")
public SearchClient searchClient() {
    return new SearchClient();
}
~~~

`SearchClient` ở đây là kiểu giả định có phương thức `shutdown()` không tham số phù hợp để gọi. Tên trong `destroyMethod` phải trùng với phương thức cleanup thực tế.

### Cơ chế suy luận close hoặc shutdown

Trong `@Bean`, giá trị mặc định của `destroyMethod` là cơ chế suy luận. Spring có thể tự nhận diện phương thức public tên `close` hoặc `shutdown` để dùng làm callback hủy nếu có.

Ví dụ:

~~~java
public class ExternalResource implements AutoCloseable {
    @Override
    public void close() {
        // Giải phóng tài nguyên.
    }
}

@Configuration
public class ResourceConfiguration {
    @Bean
    public ExternalResource externalResource() {
        return new ExternalResource();
    }
}
~~~

Với cấu hình mặc định của `@Bean`, Spring có thể suy luận `close` làm destroy method. Điều này đặc biệt thuận tiện với class triển khai `AutoCloseable` hoặc cung cấp phương thức `close()/shutdown()` công khai.

Nếu muốn **tắt cơ chế suy luận** destroy method cho bean đó, có thể khai báo chuỗi rỗng:

~~~java
@Bean(destroyMethod = "")
public ExternalResource externalResource() {
    return new ExternalResource();
}
~~~

Chỉ nên tắt khi có lý do rõ ràng, ví dụ lifecycle của resource do một thành phần khác sở hữu hoặc không muốn Spring tự gọi phương thức đóng. Nếu tắt suy luận nhưng resource thực sự cần cleanup, phải bảo đảm có cơ chế dọn dẹp khác.

### destroyMethod không phải một phương thức Java được gọi ngay khi tạo bean

`destroyMethod` là metadata trong bean definition. Nó chỉ định tên callback cho giai đoạn hủy. Phương thức không được gọi khi Spring tạo bean, không được gọi sau mỗi request, và cũng không phải một lệnh để code nghiệp vụ chủ động yêu cầu đóng bean.

## 5. So sánh ba cơ chế

| Tiêu chí | `@PreDestroy` | `DisposableBean` | `@Bean(destroyMethod = "...")` |
|---|---|---|---|
| Cách khai báo | Annotation trên phương thức | Implement interface | Metadata trên factory method |
| Gắn với Spring | Ít hơn, qua annotation lifecycle | Trực tiếp qua interface Spring | Cấu hình Spring |
| Sửa class bean | Có | Có | Không nhất thiết |
| Hợp với class bên thứ ba | Nếu có thể thêm annotation thì được, nhưng thường không | Không nếu không thể sửa/bao bọc class | Rất phù hợp |
| Tên phương thức | Tùy ý | Bắt buộc `destroy()` | Tên được chỉ định |
| Ví dụ | `@PreDestroy void close()` | `destroy()` | `@Bean(destroyMethod = "close")` |

Có thể chọn theo nguyên tắc:

- Class do ứng dụng sở hữu và cần cleanup: `@PreDestroy` thường là lựa chọn dễ đọc.
- Class hạ tầng đã phụ thuộc Spring và muốn implement lifecycle contract: `DisposableBean` là một lựa chọn.
- Đối tượng do thư viện ngoài cung cấp hoặc muốn giữ lifecycle trong cấu hình: `destroyMethod` phù hợp.

Không cần áp dụng cả ba cho mọi bean. Hãy chọn một cách thể hiện cleanup rõ ràng và tránh lặp cùng một thao tác ở nhiều callback.

## 6. Thứ tự callback hủy khi một bean dùng nhiều cơ chế

Spring hỗ trợ kết hợp các kiểu callback lifecycle. Với một bean có cả phương thức `@PreDestroy`, implement `DisposableBean` và destroy method tùy chỉnh, thứ tự hủy thông thường là:

1. Các phương thức được đánh dấu `@PreDestroy`.
2. `DisposableBean.destroy()`.
3. Phương thức hủy tùy chỉnh được cấu hình trong bean definition, ví dụ `destroyMethod`.

Ví dụ minh họa:

~~~java
@Component
public class LifecycleExample implements DisposableBean {

    @PreDestroy
    public void preDestroy() {
        System.out.println("1. @PreDestroy");
    }

    @Override
    public void destroy() {
        System.out.println("2. DisposableBean.destroy()");
    }

    public void customShutdown() {
        System.out.println("3. custom destroy method");
    }
}
~~~

Nếu dùng `@Bean` để đăng ký bean, có thể khai báo custom method:

~~~java
@Bean(destroyMethod = "customShutdown")
public LifecycleExample lifecycleExample() {
    return new LifecycleExample();
}
~~~

Đoạn minh họa cho thấy các cơ chế có thể cùng tham gia lifecycle. Trong code thực tế, không nên chia cùng một công việc cleanup thành ba callback chỉ để tận dụng thứ tự. Điều đó khiến trạng thái tài nguyên khó theo dõi và có thể gây gọi cleanup trùng lặp nếu nhiều callback cùng thực hiện một thao tác.

Một cách đơn giản hơn là để một callback điều phối phương thức đóng duy nhất, hoặc chỉ dùng một cơ chế phù hợp. Khi cần nhiều giai đoạn cleanup thực sự khác nhau, hãy đặt tên và tài liệu hóa thứ tự phụ thuộc rõ ràng.

### Thứ tự hủy giữa các bean có dependency

Nếu bean A phụ thuộc vào bean B, Spring thường bảo đảm bean phụ thuộc A được hủy trước bean mà nó cần B, để A còn cơ hội sử dụng B trong quá trình cleanup. Đây là một phần của việc quản lý quan hệ phụ thuộc giữa singleton bean.

Ví dụ:

~~~text
OrderService  --->  PaymentClient
      |                   |
      | hủy trước          | hủy sau
      v                   v
cleanup OrderService  cleanup PaymentClient
~~~

Không nên tự đóng `PaymentClient` từ `OrderService` nếu container cũng quản lý nó. Mỗi bean nên cleanup tài nguyên mà nó sở hữu; container điều phối vòng đời theo đồ thị dependency.

## 7. Khi nào callback hủy được gọi?

Với singleton bean được ApplicationContext quản lý, callback hủy thường được gọi khi context đóng một cách bình thường.

Một số cách đóng context:

~~~java
ConfigurableApplicationContext context =
        SpringApplication.run(StoreApplication.class, args);

// Khi ứng dụng cần kết thúc có kiểm soát:
context.close();
~~~

Trong một chương trình Java cần quản lý context thủ công, có thể dùng try-with-resources nếu kiểu context hỗ trợ AutoCloseable:

~~~java
try (ConfigurableApplicationContext context =
             new SpringApplicationBuilder(StoreApplication.class).run(args)) {
    // Dùng ứng dụng hoặc thực hiện công việc.
}
// context được đóng khi thoát khối try.
~~~

Trong ứng dụng Spring Boot chạy bình thường, Spring Boot quản lý ApplicationContext và đăng ký cơ chế shutdown hook theo cấu hình mặc định để đóng context khi JVM kết thúc bình thường. Khi context đóng, các singleton bean được quản lý sẽ nhận giai đoạn destruction.

Cần phân biệt **đóng context có kiểm soát** với **process bị dừng cưỡng bức**. Nếu máy bị mất điện, container runtime kill process không cho shutdown hoàn tất hoặc JVM crash, không thể bảo đảm callback được thực thi. Vì thế, callback hủy không phải nơi duy nhất lưu trạng thái quan trọng.

### Bean lazy chưa từng được tạo thì sao?

Một singleton lazy chưa từng được khởi tạo không có instance để cleanup. Không nên mong callback được gọi cho một bean chưa bao giờ được tạo.

### Prototype bean có callback hủy tự động không?

Đây là điểm đặc biệt quan trọng: Spring tạo và cấu hình prototype bean rồi giao cho client, nhưng **không theo dõi toàn bộ vòng đời của prototype instance sau khi giao**. Vì vậy, Spring không tự động gọi destruction callback cho prototype giống singleton.

Nếu prototype giữ tài nguyên cần đóng, client nhận instance phải chịu trách nhiệm cleanup hoặc cần một cơ chế quản lý vòng đời khác.

~~~java
ReportSession session = provider.getObject();
try {
    session.generate();
} finally {
    session.close();
}
~~~

Trong ví dụ, `close()` là API do class định nghĩa và nơi sử dụng chủ động gọi. Không nên dựa vào `@PreDestroy` trên prototype để tự động giải phóng mọi tài nguyên sau khi không còn tham chiếu.

### Web scope kết thúc theo phạm vi của nó

Với request, session, application hoặc WebSocket scope được hỗ trợ và đăng ký trong môi trường phù hợp, callback hủy gắn với kết thúc scope tương ứng. Ví dụ, request-scoped bean có thể được cleanup khi HTTP request hoàn tất; session-scoped bean khi session bị hủy hoặc hết hạn theo cơ chế web container.

Tuy nhiên, callback của web scope cũng không biến dữ liệu thành persistence bền vững. Nếu session mất đột ngột hoặc server bị dừng cưỡng bức, không thể xem callback là bảo đảm lưu dữ liệu.

## 8. Ví dụ thực tế: dừng ExecutorService an toàn

Một bean quản lý worker pool cần ngừng nhận task mới và cho task đang chạy cơ hội hoàn tất.

~~~java
package com.example.store.background;

import jakarta.annotation.PreDestroy;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Component;

@Component
public class ReportWorker {

    private final ExecutorService executor =
            Executors.newFixedThreadPool(4);

    public void submit(Runnable task) {
        executor.submit(task);
    }

    @PreDestroy
    public void stop() {
        executor.shutdown();

        try {
            if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        } catch (InterruptedException ex) {
            executor.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }
}
~~~

Trình tự:

1. `shutdown()` ngừng nhận task mới nhưng cho phép task đã submit tiếp tục chạy.
2. `awaitTermination(...)` chờ trong khoảng thời gian giới hạn.
3. Nếu hết thời gian mà pool chưa dừng, `shutdownNow()` yêu cầu dừng các task đang chạy và trả về các task chưa bắt đầu.
4. Nếu thread chờ bị interrupt, gọi `shutdownNow()` và khôi phục interrupt flag.

Không có bảo đảm mọi task dừng ngay sau `shutdownNow()`; task phải hợp tác với cơ chế interrupt. Nếu công việc có thể chạy lâu, cần thiết kế timeout, cancellation và xử lý trạng thái công việc phù hợp.

Ví dụ này cho thấy cleanup callback nên có **giới hạn thời gian**. Nếu shutdown callback chờ vô hạn một server ngoài đang không phản hồi, toàn bộ quá trình đóng context có thể bị kéo dài.

## 9. Ví dụ với tài nguyên bên thứ ba và destroyMethod

Giả sử thư viện ngoài cung cấp `SearchClient` có phương thức `close()` nhưng không có annotation Spring:

~~~java
public class SearchClient {
    public SearchClient(String endpoint) {
        // Mở connection pool.
    }

    public void search(String query) {
        // ...
    }

    public void close() {
        // Đóng connection pool.
    }
}
~~~

Đăng ký bean:

~~~java
@Configuration
public class SearchConfiguration {

    @Bean(destroyMethod = "close")
    public SearchClient searchClient(
            SearchSettings settings
    ) {
        return new SearchClient(settings.endpoint());
    }
}
~~~

Service sử dụng client qua constructor:

~~~java
@Service
public class SearchService {
    private final SearchClient searchClient;

    public SearchService(SearchClient searchClient) {
        this.searchClient = searchClient;
    }
}
~~~

Spring tạo `SearchClient` qua factory method, inject nó vào `SearchService`, và khi context đóng sẽ gọi `close()` theo metadata destroy method.

Service không cần giữ `ApplicationContext` để tự lấy client và cũng không cần tự đóng client. Bean definition sở hữu việc cấu hình lifecycle; consumer chỉ sử dụng dependency.

Nếu `SearchClient` có `close()` public và Spring suy luận được destroy method theo mặc định, có thể không cần ghi rõ `destroyMethod = "close"`. Khai báo tường minh vẫn có giá trị khi muốn làm rõ ý định hoặc khi tên phương thức không nằm trong nhóm suy luận mặc định.

## 10. AutoCloseable và Closeable trong Java

Java cung cấp các interface tiêu chuẩn cho tài nguyên cần đóng:

- `AutoCloseable` định nghĩa `close()` có thể ném `Exception`.
- `Closeable` mở rộng `AutoCloseable` và thường dùng cho I/O resource, với `close()` ném `IOException`.

Một bean triển khai `AutoCloseable` thường phù hợp với cơ chế suy luận `close` của `@Bean`:

~~~java
public class ReportArchive implements AutoCloseable {

    @Override
    public void close() throws IOException {
        // Đóng stream hoặc file resource.
    }
}
~~~

~~~java
@Configuration
public class ArchiveConfiguration {
    @Bean
    public ReportArchive reportArchive() throws IOException {
        return new ReportArchive();
    }
}
~~~

Trong cấu hình `@Bean` mặc định, Spring có thể suy luận phương thức `close()` làm destroy method. Nếu muốn thể hiện rõ:

~~~java
@Bean(destroyMethod = "close")
public ReportArchive reportArchive() {
    return new ReportArchive();
}
~~~

Điểm khác nhau giữa Java resource management và Spring lifecycle:

- `try-with-resources` đóng tài nguyên ở cuối khối sử dụng.
- Spring destroy callback đóng bean khi vòng đời bean/container kết thúc.
- Một object được tạo bằng `new` trong phương thức vẫn có thể dùng try-with-resources, dù không phải bean.
- Một bean được Spring quản lý không nhất thiết nên được đóng thủ công ở từng consumer; việc đó có thể phá vỡ các consumer khác đang dùng cùng singleton.

Chọn cơ chế theo **ai sở hữu vòng đời**. Nếu một bean singleton dùng chung resource, container thường là nơi phù hợp để quản lý việc đóng resource đó.

## 11. Phân biệt destroy callback với SmartLifecycle

`@PreDestroy`, `DisposableBean` và `destroyMethod` phục vụ callback hủy. Nhưng một số thành phần nền cần quy trình start/stop có thứ tự, phối hợp với các component khác hoặc hỗ trợ dừng trước khi container đóng hoàn toàn.

Spring có interface `Lifecycle` và `SmartLifecycle` cho mục đích quản lý vòng đời thành phần có khả năng start/stop. `SmartLifecycle` còn hỗ trợ phase để điều phối thứ tự start/stop và cơ chế auto-start.

Ví dụ khái niệm:

~~~java
@Component
public class EventConsumer implements SmartLifecycle {

    private volatile boolean running;

    @Override
    public void start() {
        // Bắt đầu nhận event.
        running = true;
    }

    @Override
    public void stop() {
        // Ngừng nhận event và dừng xử lý.
        running = false;
    }

    @Override
    public boolean isRunning() {
        return running;
    }
}
~~~

Ví dụ rút gọn chưa triển khai cơ chế dừng an toàn thực tế; một consumer thật cần dừng nhận message, chờ xử lý in-flight, timeout và đóng client. `SmartLifecycle` phù hợp hơn khi cần quản lý trình tự hoạt động; callback hủy vẫn hữu ích để giải phóng tài nguyên cuối cùng.

Có thể kết hợp lifecycle start/stop và destroy callback, nhưng cần tránh gọi cùng thao tác đóng hai lần. Thiết kế nên có trạng thái hoặc thao tác cleanup idempotent để lần gọi lặp không làm hỏng tài nguyên.

## 12. Cleanup nên idempotent và có giới hạn

Trong thực tế, việc dừng ứng dụng có thể diễn ra sau một lỗi hoặc một chuỗi shutdown phức tạp. Một phương thức cleanup tốt nên được thiết kế để gọi lặp an toàn nếu có thể:

~~~java
@Component
public class ManagedConnection {

    private Connection connection;
    private boolean closed;

    @PreDestroy
    public synchronized void close() {
        if (closed) {
            return;
        }

        closed = true;

        if (connection != null) {
            try {
                connection.close();
            } catch (SQLException ex) {
                // Ghi log phù hợp.
            }
        }
    }
}
~~~

Ví dụ này minh họa ý tưởng idempotent, không phải cách quản lý connection tối ưu cho mọi ứng dụng. Nếu connection được cung cấp bởi pool, bean sử dụng nó thường không nên đóng pool; nó chỉ nên trả connection về pool. Bean sở hữu pool mới là nơi đóng pool khi context dừng.

Một số nguyên tắc cleanup hữu ích:

- Chỉ đóng tài nguyên mà bean thực sự sở hữu.
- Không đóng dependency singleton dùng chung chỉ vì một consumer ngừng hoạt động.
- Dừng nhận công việc mới trước khi chờ công việc đang chạy hoàn tất.
- Dùng timeout cho network call hoặc chờ thread.
- Khôi phục interrupt flag nếu bắt `InterruptedException` mà không truyền tiếp.
- Ghi log lỗi cleanup đủ để vận hành điều tra, nhưng tránh log secret.
- Thiết kế callback an toàn khi trạng thái đã được đóng hoặc khởi tạo chưa hoàn tất.
- Không phụ thuộc callback để bảo đảm lưu dữ liệu nghiệp vụ quan trọng.

### Shutdown hook và thời gian dừng của ứng dụng

Spring Boot có cơ chế đóng ApplicationContext khi JVM shutdown theo quy trình thông thường. Tuy nhiên, nền tảng triển khai có thể gửi tín hiệu dừng và chỉ cho process một khoảng thời gian trước khi kill. Vì vậy, callback cleanup cần hoàn thành trong thời gian hợp lý.

Nếu ứng dụng chạy trong container hoặc orchestrator, hãy phối hợp thời gian graceful shutdown của nền tảng với thời gian cleanup bên trong ứng dụng. Không nên đặt callback chờ một thao tác vô hạn.

## 13. Những điều không nên làm trong destroy callback

### Không gọi API nghiệp vụ quan trọng rồi giả định luôn thành công

Ví dụ không nên dựa vào:

~~~java
@PreDestroy
public void destroy() {
    paymentService.captureAllPendingPayments();
}
~~~

Shutdown không phải một giao dịch nghiệp vụ. Nếu process bị kill, lệnh có thể không chạy; nếu API ngoài lỗi, không có cơ chế retry đáng tin cậy chỉ nhờ callback. Hãy xử lý thanh toán trong luồng nghiệp vụ và lưu trạng thái có thể phục hồi.

### Không block vô thời hạn

~~~java
@PreDestroy
public void close() {
    remoteClient.waitUntilServerRespondsForever();
}
~~~

Một callback vô hạn có thể ngăn context đóng hoàn tất. Hãy sử dụng timeout và phương án fallback.

### Không tự đóng dependency do container sở hữu

Nếu `OrderService` và `InvoiceService` cùng dùng một `DatabaseClient` singleton, việc `OrderService` tự đóng client khi nó bị hủy có thể làm `InvoiceService` mất kết nối trước khi được cleanup.

Mỗi bean nên giải phóng tài nguyên thuộc quyền sở hữu của nó. Container quản lý thứ tự lifecycle giữa các bean theo dependency.

### Không tạo thêm dependency mới trong lúc hủy nếu không cần

Callback hủy nên sử dụng các dependency đã được cung cấp và tài nguyên bean sở hữu. Tránh gọi `ApplicationContext.getBean` để tìm một bean khác vào đúng thời điểm context đang đóng; dependency đó có thể đã bị hủy hoặc không còn sẵn sàng.

### Không giả định callback luôn chạy

Shutdown cưỡng bức, crash, mất điện và một số lỗi runtime có thể bỏ qua cleanup. Dữ liệu cần bền vững phải được ghi trong quá trình hoạt động, không chờ tới lúc hủy bean.

## 14. Kiểm thử destroy callback

Để kiểm tra callback, cần tạo bean trong một context thực và đóng context đó. Ví dụ với context nhỏ:

~~~java
class CleanupProbe {
    private boolean closed;

    @PreDestroy
    public void close() {
        closed = true;
    }

    public boolean isClosed() {
        return closed;
    }
}
~~~

~~~java
AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext();

context.registerBean(CleanupProbe.class);
context.refresh();

CleanupProbe probe = context.getBean(CleanupProbe.class);

context.close();

// Sau khi context đóng, probe.isClosed() dự kiến là true.
~~~

Ví dụ này cho thấy callback gắn với việc đóng context. Trong test thật, có thể dùng một probe có cờ hoặc mock để xác nhận phương thức cleanup được gọi.

### Kiểm thử @Bean destroyMethod

Có thể đăng ký bean có phương thức `close()` hoặc `shutdown()`, đóng context rồi xác nhận trạng thái resource đã được giải phóng. Điều này kiểm tra cấu hình destroy method thực sự được Spring áp dụng.

### Kiểm thử prototype

Nếu test lấy prototype bean, không nên mong `context.close()` tự gọi destruction callback cho mọi instance prototype đã giao. Hãy kiểm tra và tự cleanup theo contract của đối tượng.

### Kiểm thử Spring Boot context

Với `@SpringBootTest`, Spring Test thường cache ApplicationContext giữa các test class. Do đó, không phải sau mỗi phương thức test context đều đóng và destroy callback đều chạy. Nếu cần kiểm tra vòng đời đóng context trong test, có thể dùng context riêng hoặc cơ chế `@DirtiesContext` phù hợp để đánh dấu context cần đóng sau test.

Không nên viết test phụ thuộc vào thứ tự cleanup ngẫu nhiên của toàn bộ suite. Tạo context nhỏ, cô lập sẽ giúp kiểm tra lifecycle dễ dự đoán hơn.

## 15. Chọn cơ chế nào trong từng tình huống?

| Tình huống | Cách thường phù hợp | Lý do |
|---|---|---|
| Service do dự án sở hữu cần dừng scheduler | `@PreDestroy` | Khai báo ngay trên bean, không cần implement interface Spring |
| Bean đã phụ thuộc Spring và muốn dùng contract hủy của framework | `DisposableBean` | Phương thức `destroy()` là contract tường minh |
| SDK bên thứ ba có `close()` | `@Bean(destroyMethod = "close")` hoặc suy luận mặc định | Không cần sửa class thư viện |
| Bean có phương thức `shutdown()` riêng | `@Bean(destroyMethod = "shutdown")` | Chỉ định tên callback trong cấu hình |
| Thành phần nền cần start/stop có thứ tự | `SmartLifecycle`, có thể kết hợp cleanup | Có semantics lifecycle phong phú hơn một callback hủy đơn lẻ |
| Object được tạo và dùng trong một khối ngắn | `try-with-resources` | Vòng đời nằm trong phạm vi code sử dụng |
| Prototype giữ resource | API close/factory hoặc cơ chế sở hữu riêng | Container không tự cleanup prototype sau khi giao |

Một lựa chọn tốt thường có các đặc điểm:

- Được khai báo tại nơi dễ xác định quyền sở hữu resource.
- Chỉ có một nơi chịu trách nhiệm đóng resource.
- Không yêu cầu service nghiệp vụ phải tra cứu context để cleanup.
- Có timeout và cách xử lý lỗi phù hợp.
- Dễ kiểm thử bằng cách đóng context hoặc gọi contract đóng một cách có kiểm soát.

## 16. Bài tập thực hành

Giả sử ứng dụng Spring Boot có ba bean:

- `ReportScheduler` tạo scheduled task và cần dừng scheduler.
- `VendorClient` đến từ thư viện bên ngoài, có phương thức `close()`.
- `TemporaryExport` là prototype bean giữ một file tạm cho mỗi lần export.

Hãy chọn cách cleanup:

1. Với `ReportScheduler`, có thể dùng `@PreDestroy` để ngừng nhận task mới, chờ task đang chạy trong thời gian giới hạn rồi dừng executor.
2. Với `VendorClient`, khai báo bằng `@Bean(destroyMethod = "close")` hoặc dựa vào cơ chế suy luận close/shutdown nếu phù hợp.
3. Với `TemporaryExport`, caller nhận instance prototype phải chịu trách nhiệm đóng file sau khi export; không trông chờ Spring tự gọi callback khi context đóng.

Tiếp tục phân tích:

- Nếu `ReportScheduler` dùng `VendorClient`, scheduler phải dừng trước khi client đóng. Quan hệ dependency và thứ tự hủy của container có thể giúp điều phối nếu dependency được khai báo đúng.
- Nếu export bị lỗi giữa chừng, file tạm vẫn cần được đóng hoặc xóa bằng `finally`/try-with-resources.
- Nếu ứng dụng bị kill cưỡng bức, cleanup callback có thể không hoàn tất; dữ liệu quan trọng cần được bảo vệ trong quá trình xử lý, không đợi shutdown.

## 17. Những nguyên tắc cần nhớ

1. **`@PreDestroy` đánh dấu phương thức cleanup trên bean do Spring quản lý.** Phương thức không tham số, trả về void và được gọi ở giai đoạn hủy.
2. **`DisposableBean` là contract của Spring.** Implement `destroy()` nếu class muốn trực tiếp tham gia lifecycle interface.
3. **`destroyMethod` thuộc bean definition.** Hữu ích cho object bên thứ ba hoặc khi muốn khai báo tên cleanup ở cấu hình.
4. **`@Bean` có cơ chế suy luận close/shutdown.** Có thể chỉ định rõ method hoặc dùng `destroyMethod = ""` để tắt suy luận khi có lý do.
5. **Thứ tự callback trong một bean có thể kết hợp:** `@PreDestroy`, `DisposableBean.destroy()`, rồi custom destroy method.
6. **Singleton được cleanup khi context đóng có kiểm soát.** Prototype không được Spring tự quản lý destruction đầy đủ sau khi giao cho caller.
7. **Cleanup không thay thế nghiệp vụ bền vững.** Callback có thể không chạy khi process bị kill; không dùng nó làm nơi duy nhất thực hiện thanh toán hoặc lưu trạng thái quan trọng.
8. **Chỉ đóng tài nguyên thuộc quyền sở hữu của bean.** Không tự đóng dependency dùng chung mà container còn quản lý.
9. **Dùng SmartLifecycle khi cần điều phối start/stop.** Một destroy callback đơn lẻ không thay thế đầy đủ lifecycle của worker nền phức tạp.
10. **Kiểm thử bằng cách đóng context thực.** Đừng giả định context cache trong Spring Test sẽ đóng sau từng test method.

## Kết luận

`@PreDestroy`, `DisposableBean` và `destroyMethod` đều giúp Spring thực hiện cleanup khi bean đi đến cuối vòng đời, nhưng chúng biểu đạt ý định ở những vị trí khác nhau. Annotation phù hợp với class do ứng dụng sở hữu; interface là contract trực tiếp của Spring; destroy method cho phép cấu hình cleanup cho object được tạo qua factory method, đặc biệt hữu ích với thư viện bên ngoài.

Hãy xác định bean sở hữu tài nguyên nào, scope của nó là gì, thời điểm nào container kết thúc scope và ai chịu trách nhiệm đóng tài nguyên. Callback hủy nên ngắn gọn, có giới hạn thời gian, an toàn khi trạng thái chưa hoàn tất và không chứa nghiệp vụ cần bảo đảm. Khi quyền sở hữu vòng đời được thể hiện rõ, quá trình shutdown của Spring Boot sẽ dễ dự đoán và hệ thống ít gặp rò rỉ tài nguyên hơn.
