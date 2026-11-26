# Chi phí metadata của lời gọi repository và phạm vi bật exposeMetadata

## 1. Metadata đang được nói tới là metadata của một lời gọi

Trong chương **Hiệu năng** của module **SPRING_DATA_COMMONS**, `exposeMetadata` là một lựa chọn dành cho code cần biết repository và method đang được gọi. Đây không phải công tắc bật/tắt toàn bộ metadata của Spring Data.

Ví dụ, một fragment dùng chung cho nhiều repository có thể cần biết:

- Repository interface hiện tại là gì.
- Domain type mà repository quản lý là gì.
- Method nào trên repository interface đang được thực thi.

Thông tin đó hữu ích cho một extension dùng chung, nhưng việc làm nó sẵn có trên đường gọi có chi phí. Cách tiếp cận phù hợp là xác định nơi thực sự cần metadata của lời gọi, giới hạn repository được bật và đo phần chi phí liên quan.

Không có một con số cố định như “bật metadata luôn chậm thêm 5%”. Chênh lệch phụ thuộc phiên bản, cấu trúc proxy, JDK, workload và phần công việc khác trong mỗi lời gọi.

Các ví dụ API trong bài được đối chiếu theo **Spring Data Commons 3.5.0**; tính năng này có từ dòng 3.4. Khi dùng phiên bản khác, cần đối chiếu API và cơ chế factory của phiên bản tương ứng.

## 2. Phân biệt các lớp metadata

| Lớp thông tin | Ví dụ | Có đồng nghĩa với exposeMetadata không? |
| --- | --- | --- |
| Metadata của repository interface | Domain type, ID type, repository interface | Không; đây là thông tin cấu trúc repository |
| Metadata mapping | PersistentEntity, property, converter, quan hệ | Không; cần cho mapping của từng store |
| Metadata query | Query method, tham số, kiểu kết quả | Không; cần cho cơ chế query của module |
| Context của lời gọi hiện tại | Repository nào và method nào đang được gọi | Đây là phạm vi đang xét |
| Metadata nghiệp vụ | Actor auditing, thời điểm tạo/sửa, trạng thái entity | Không tự được tạo hoặc tối ưu bằng cờ này |

`RepositoryMetadata` mô tả repository interface, chẳng hạn domain type và ID type. [RepositoryMetadata API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/core/RepositoryMetadata.html).

`MappingContext` quản lý thông tin PersistentEntity/PersistentProperty phục vụ mapping. Tắt exposure của lời gọi không loại bỏ nhu cầu dùng các cấu trúc mapping đó. [MappingContext API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/mapping/context/MappingContext.html).

Vì vậy, không kỳ vọng `setExposeMetadata(false)` sẽ làm derived query, projection hoặc auditing ngừng sử dụng metadata cần thiết của chúng. Cũng không bật cờ này chỉ vì repository có Pageable, Sort hoặc projection.

## 3. RepositoryMethodContext cung cấp điều gì?

Trong API 3.5.0, code đang ở một lời gọi repository có exposure phù hợp có thể dùng:

~~~java
import org.springframework.data.repository.core.RepositoryMetadata;
import org.springframework.data.repository.core.RepositoryMethodContext;

RepositoryMethodContext context = RepositoryMethodContext.getContext();
RepositoryMetadata repository = context.getMetadata();

Class<?> repositoryType = repository.getRepositoryInterface();
Class<?> domainType = repository.getDomainType();
String methodName = context.getMethod().getName();
~~~

`getMethod()` biểu diễn method trên repository interface được gọi, không nhất thiết là method implementation mà fragment dùng ở bên dưới. `getContext()` cần một context lời gọi hợp lệ; nếu không có, API báo `IllegalStateException` thay vì trả null. [RepositoryMethodContext API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/core/RepositoryMethodContext.html).

Tên accessor trong code ở đây là `getMetadata()`, theo [mã API Spring Data Commons 3.5.0](https://github.com/spring-projects/spring-data-commons/blob/3.5.0/src/main/java/org/springframework/data/repository/core/RepositoryMethodContext.java). Không suy tên method từ một snippet thuộc phiên bản khác.

### 3.1. Context không phải một registry dùng ở mọi nơi

Không gọi `RepositoryMethodContext.getContext()` trong constructor của một bean rồi kỳ vọng biết repository sẽ sử dụng bean đó sau này. Tại thời điểm constructor chạy, chưa có lời gọi repository tương ứng.

Tương tự, một service gọi xong repository không thể tiếp tục dùng context đó như một trạng thái request tồn tại lâu dài.

Context phù hợp cho một thao tác nằm trong phạm vi lời gọi được quản lý. Nếu dữ liệu đã được biết ở lúc khởi tạo, một dependency hoặc cấu hình tường minh thường dễ hiểu hơn việc tìm lại nó từ ambient context.

## 4. Chi phí được thêm vào ở đâu?

`setExposeMetadata` có mặc định false để tránh interception bổ sung không cần thiết. Nó yêu cầu repository factory làm metadata lời gọi sẵn có thông qua cơ chế ThreadLocal phục vụ RepositoryMethodContext. [RepositoryFactoryBeanSupport API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/core/support/RepositoryFactoryBeanSupport.html).

Với cơ chế của dòng 3.5.0, có thể hình dung đường gọi:

~~~text
Caller
    -> repository proxy
    -> advice phục vụ exposure
       - chuẩn bị context cho method hiện tại
       - gắn context vào phạm vi luồng
    -> các advice/query/fragment cần thực thi
    -> khôi phục context trước đó khi rời lời gọi
    -> trả kết quả hoặc truyền lỗi
~~~

Mã factory 3.5.0 bổ sung advice cho metadata và invocation exposure; interceptor tạo context rồi khôi phục context cũ trong finally. Đây là chi tiết triển khai của phiên bản được khảo sát, không phải hợp đồng cố định về số allocation hay thời gian nanosecond. [RepositoryFactorySupport 3.5.0](https://github.com/spring-projects/spring-data-commons/blob/3.5.0/src/main/java/org/springframework/data/repository/core/support/RepositoryFactorySupport.java).

Các nhóm chi phí cần xem xét:

| Nhóm | Nội dung cần đo |
| --- | --- |
| Dispatch/interception | Thêm công việc trong chuỗi advice |
| Context binding | Đọc, đặt và khôi phục trạng thái lời gọi |
| Allocation thực tế | Các object tồn tại sau tối ưu JIT và lượng bộ nhớ cấp phát |
| Logic dùng metadata | Lookup registry, đọc annotation, chọn converter hoặc tạo descriptor |
| Quan sát bổ sung | Log, metric hoặc tracing do extension tự thêm |

Chi phí exposure và chi phí ứng dụng xử lý metadata là hai phần khác nhau. Nếu fragment vừa đọc context vừa log nhiều thông tin, chênh lệch đo được không thể được gán toàn bộ cho cờ exposure.

### 4.1. Không nhầm với việc phân tích lại toàn bộ repository mỗi lần

Exposure không có nghĩa mỗi lời gọi phải scan lại mọi entity, phân tích lại toàn bộ generic type và tạo lại mọi query method từ đầu.

Ngược lại, việc Spring Data đã có thông tin cấu trúc repository không làm chi phí gắn context theo từng lời gọi tự biến mất. Đây là hai giai đoạn khác nhau cần phân biệt khi đo startup và steady state.

### 4.2. Quy mô lời gọi quyết định mức ảnh hưởng

Có thể dùng mô hình ước lượng:

~~~text
CPU time tăng mỗi giây
    ≈ tổng theo repository i:
      số lời gọi/giây của i × thời gian CPU tăng thêm/lời gọi

Allocation tăng mỗi giây
    ≈ tổng theo repository i:
      số lời gọi/giây của i × số byte cấp phát tăng thêm/lời gọi
~~~

Đây là mô hình phân tích, chưa phải số đo. Nó giúp nhận ra một repository có tần suất rất cao đáng được xem riêng, ngay cả khi phần tăng thêm của một lần gọi nhỏ.

Latency toàn request còn chứa database, network, transaction, mapping và code nghiệp vụ. Một phần tăng CPU nhỏ trên đường proxy không tự chuyển thành cùng một tỷ lệ tăng p99 latency.

## 5. Bật bằng marker của fragment khi fragment thật sự cần context

Một cách khai báo nhu cầu là cho **implementation của fragment** implement `RepositoryMetadataAccess`.

~~~java
public record InvocationSummary(
    Class<?> repositoryType,
    Class<?> domainType,
    String methodName
) {
}
~~~

~~~java
public interface InvocationInspection {
    InvocationSummary describeInvocation();
}
~~~

~~~java
import org.springframework.data.repository.core.RepositoryMethodContext;
import org.springframework.data.repository.core.support.RepositoryMetadataAccess;

public class InvocationInspectionImpl
        implements InvocationInspection, RepositoryMetadataAccess {

    @Override
    public InvocationSummary describeInvocation() {
        RepositoryMethodContext context =
            RepositoryMethodContext.getContext();

        return new InvocationSummary(
            context.getMetadata().getRepositoryInterface(),
            context.getMetadata().getDomainType(),
            context.getMethod().getName()
        );
    }
}
~~~

Một repository của ứng dụng có thể sử dụng fragment này:

~~~java
import org.springframework.data.repository.CrudRepository;

public interface CatalogRepository
        extends CrudRepository<CatalogItem, Long>,
                InvocationInspection {
}
~~~

Ở đây, `CatalogItem` là domain type của ứng dụng, cần mapping phù hợp với module store thực tế. Các đoạn code minh họa được đặt trong những file Java riêng khi triển khai; fragment cần nằm trong phạm vi discovery/wiring đúng của repository.

Marker thể hiện nhu cầu metadata tại implementation. Nó không cần một method cấu hình trên interface nghiệp vụ. Theo thiết kế, marker áp dụng cho repository composition chứa fragment đó; nên đặt ở implementation thay vì interface fragment. [RepositoryMetadataAccess API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/core/support/RepositoryMetadataAccess.html).

### 5.1. Phạm vi thực tế là proxy repository

Giả sử:

~~~text
CatalogRepository -> InvocationInspectionImpl có marker
StockRepository   -> không có fragment cần metadata
OrderRepository   -> không có fragment cần metadata
~~~

Với cấu hình khác không mở rộng exposure:

- CatalogRepository được bật exposure vì composition của nó có fragment yêu cầu.
- StockRepository và OrderRepository không tự được bật chỉ vì có cùng application context.
- Các method thông thường đi qua chuỗi advice của CatalogRepository cũng chịu phần công việc exposure tương ứng.

Không diễn giải marker thành “chỉ method describeInvocation trả chi phí metadata”. Nó khiến proxy repository được cấu hình exposure; phạm vi hẹp ở cấp repository, không phải một bộ lọc method riêng.

Nếu fragment được gắn vào một base interface mà hàng trăm repository cùng kế thừa, phạm vi có thể lớn hơn ý định ban đầu. Cần nhìn vào composition của các repository thực tế.

## 6. Bật có chọn lọc bằng BeanPostProcessor

Khi chính sách ứng dụng muốn chọn một nhóm repository cụ thể, có thể đặt `exposeMetadata` trên factory bean trước khởi tạo.

Đây là **phương án thay thế** cho việc để marker của fragment quyết định phạm vi; không cần chồng cả hai nếu chúng chỉ phục vụ cùng một nhu cầu.

Ví dụ dùng một marker riêng của ứng dụng:

~~~java
public interface NeedsInvocationMetadata {
}
~~~

Marker này là một nhãn chọn nhóm repository, không phải `RepositoryMetadataAccess` của Spring Data. Interface repository thuộc nhóm cần bật có thể khai báo:

~~~java
import org.springframework.data.repository.CrudRepository;

public interface CatalogRepository
        extends CrudRepository<CatalogItem, Long>,
                InvocationInspection,
                NeedsInvocationMetadata {
}
~~~

Trong phương án này, implementation fragment có thể chỉ implement `InvocationInspection`; việc bật được thực hiện bởi cấu hình sau:

~~~java
import org.springframework.beans.factory.config.BeanPostProcessor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.repository.core.support.RepositoryFactoryBeanSupport;

@Configuration(proxyBeanMethods = false)
public class InvocationMetadataConfiguration {

    @Bean
    static BeanPostProcessor selectedRepositoryMetadataExposure() {
        return new BeanPostProcessor() {

            @Override
            public Object postProcessBeforeInitialization(
                    Object bean, String beanName) {

                if (bean instanceof RepositoryFactoryBeanSupport<?, ?, ?>
                        factoryBean) {

                    Class<?> repositoryType = factoryBean.getObjectType();

                    if (repositoryType != null
                            && NeedsInvocationMetadata.class
                                .isAssignableFrom(repositoryType)) {
                        factoryBean.setExposeMetadata(true);
                    }
                }

                return bean;
            }
        };
    }
}
~~~

Điều kiện chọn dựa trên repository interface, không dựa vào việc object proxy tình cờ có tên class nào. `getObjectType()` trên factory bean 3.5.0 trả interface repository; việc thiết lập cờ cần diễn ra trước quá trình factory dựng proxy. [RepositoryFactoryBeanSupport 3.5.0](https://github.com/spring-projects/spring-data-commons/blob/3.5.0/src/main/java/org/springframework/data/repository/core/support/RepositoryFactoryBeanSupport.java).

Cấu hình trả lại nguyên bean và chỉ bật nhóm đã chọn. Nó không đặt false trên mọi factory khác, vì có thể các factory đó đã có nhu cầu exposure từ một extension khác.

### 6.1. Vì sao không copy một post-processor bật cho mọi repository?

Một điều kiện chỉ kiểm tra:

~~~java
if (bean instanceof RepositoryFactoryBeanSupport<?, ?, ?> factoryBean) {
    factoryBean.setExposeMetadata(true);
}
~~~

sẽ bật cho tất cả factory bean tương ứng đi qua post-processor. Trong ứng dụng có nhiều Spring Data module, điều đó có thể bao gồm nhiều nhóm repository.

Tài liệu Spring Data cũng lưu ý cần giới hạn theo use case thay vì copy cấu hình bật toàn bộ. [Hướng dẫn expose repository metadata](https://docs.spring.io/spring-data/commons/reference/repositories/custom-implementations.html).

Nếu chỉ một nhóm repository cần extension dựa trên method context, nhóm còn lại không có lợi ích trực tiếp từ exposure này. Một thư viện dùng chung càng cần tránh mở rộng phạm vi một cách âm thầm.

### 6.2. Đây là cấu hình lúc tạo proxy

Không coi `setExposeMetadata` là công tắc hot toggle cho từng request. Khi proxy đã được tạo, việc đổi cờ trên một object factory không có nghĩa chuỗi advice của proxy hiện hữu tự được dựng lại.

Cần chọn chính sách trong quá trình khởi tạo và kiểm thử cấu hình kết quả. Muốn thay đổi phạm vi giữa các phiên bản triển khai, cập nhật composition hoặc cấu hình tạo repository tương ứng.

## 7. Cờ false không ghi đè nhu cầu do marker tạo ra

Đây là một điểm quan trọng khi giới hạn phạm vi.

Trong cơ chế factory được xét, exposure có thể đến từ hai nguồn:

~~~text
cờ exposeMetadata được bật
    HOẶC
composition có implementation fragment cần metadata
~~~

Vì vậy:

| Cờ explicit | Có fragment implement RepositoryMetadataAccess | Kết quả exposure |
| --- | --- | --- |
| false | Không | Không được bật bởi hai cơ chế này |
| true | Không | Bật |
| false | Có | Bật |
| true | Có | Bật |

Factory API mô tả cả cơ chế cờ và cơ chế marker trong composition. Không coi false là một lệnh phủ định tuyệt đối đối với nhu cầu fragment. [RepositoryFactorySupport API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/core/support/RepositoryFactorySupport.html).

Nếu muốn một repository không cần exposure nữa, phải xác định nguồn yêu cầu:

- Post-processor nào đã bật cờ?
- Repository có kế thừa fragment nào cần marker không?
- Một thư viện dùng chung có góp fragment vào composition không?
- Một cấu hình factory khác có thay đổi chính sách không?

Chỉ thêm `setExposeMetadata(false)` ở một nơi khác có thể không đạt mục tiêu, đồng thời làm cấu hình khó hiểu hơn.

### 7.1. Marker không nên lan qua mọi base repository một cách vô thức

Giả sử chỉ một module tìm kiếm cần context, nhưng nhóm phát triển thêm fragment cần metadata vào base interface dùng chung:

~~~text
BaseBusinessRepository
    -> SearchDiagnostics cần metadata
        -> ProductRepository
        -> OrderRepository
        -> StockRepository
        -> ...
~~~

Lúc này mọi repository trong cây đều có thể thuộc phạm vi exposure, dù phần lớn không dùng diagnostics.

Có thể cân nhắc tách base interface hoặc gắn fragment vào nhóm thực sự cần. Việc tách phải giữ đúng API nghiệp vụ và được kiểm tra theo composition, không chỉ theo tên package.

Nếu workload của một repository vừa có CRUD tần suất cao vừa có extension hiếm dùng, có thể đánh giá một cấu trúc collaborator riêng cho extension. Không tự tách repository chỉ để né một chi phí chưa đo; cần cân nhắc wiring, transaction và khả năng đọc hiểu của thiết kế.

## 8. Giữ phạm vi context đúng khi có lời gọi lồng nhau

Context gắn với luồng thực thi hiện tại trong cơ chế được xét. Khi đi vào lời gọi lồng nhau rồi quay lại, việc khôi phục context trước đó là cần thiết. [RepositoryMethodContextHolder API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/core/RepositoryMethodContextHolder.html).

Ví dụ:

~~~text
Repository A đang có context A
    -> gọi Repository B có exposure
       -> trong B thấy context B
    -> quay lại A
       -> tiếp tục thấy context A
    -> rời lời gọi ngoài cùng
       -> không giữ context A cho công việc kế tiếp
~~~

Đừng tự đặt hoặc xóa holder của framework trong code nghiệp vụ để “giảm chi phí”. Xóa không đúng chỗ có thể phá context của lời gọi bao ngoài.

### 8.1. Một lần đọc không ném lỗi chưa chứng minh đang thấy đúng repository

Có một tình huống dễ bỏ sót: A có exposure gọi B không có exposure trên cùng luồng. Nếu B đọc ambient context mà không được bảo đảm phạm vi riêng, nó có thể gặp context còn tồn tại từ A.

Vì vậy, không dùng quy tắc “getContext không lỗi thì chắc chắn là metadata của repository hiện tại”. Khi xây extension, cần kiểm tra identity repository/method được kỳ vọng trong các trường hợp lồng nhau.

Đối với cấu hình không bật exposure, API không đưa ra bảo đảm truy cập context nhất quán. Không dựa vào một lần thử tình cờ thành công để bỏ khai báo nhu cầu.

### 8.2. Không giữ context lời gọi trong field của singleton

Tránh kiểu thiết kế:

~~~java
// Trạng thái theo lời gọi không nên trở thành field dùng chung của bean.
private RepositoryMethodContext lastInvocation;
~~~

Hai lời gọi đồng thời có thể thuộc hai repository khác nhau. Một field dùng chung vừa làm sai identity vừa kéo dài thời gian sống của dữ liệu không cần thiết.

Nếu cần truyền dữ liệu đi tiếp, hãy tạo một snapshot bất biến gồm đúng các giá trị cần dùng, như repository interface, domain type và Method hoặc tên method. Snapshot đó phải đi theo công việc tương ứng.

## 9. Reactive, coroutine và ranh giới bất đồng bộ

Exposure dựa vào ThreadLocal không phải một cam kết truyền context qua mọi scheduler, executor hoặc lần suspend/resume. Lỗi thường gặp là đọc context quá muộn:

~~~java
import org.springframework.data.repository.core.RepositoryMethodContext;
import reactor.core.publisher.Mono;

// Không suy rằng supplier chạy trong cùng phạm vi lời gọi repository.
Mono<RepositoryMethodContext> delayed =
    Mono.fromSupplier(RepositoryMethodContext::getContext);
~~~

Publisher có thể được subscribe sau khi method repository đã trả về hoặc trên một luồng khác. Việc có reactive transaction context không đồng nghĩa RepositoryMethodContext cũng tự được truyền như vậy.

Một hướng rõ ràng hơn là lấy các giá trị cần thiết **khi đang ở phạm vi hợp lệ**, rồi truyền snapshot:

~~~java
import org.springframework.data.repository.core.RepositoryMethodContext;
import reactor.core.publisher.Mono;

public Mono<InvocationSummary> describeReactiveInvocation() {
    RepositoryMethodContext current =
        RepositoryMethodContext.getContext();

    InvocationSummary snapshot = new InvocationSummary(
        current.getMetadata().getRepositoryInterface(),
        current.getMetadata().getDomainType(),
        current.getMethod().getName()
    );

    return Mono.just(snapshot);
}
~~~

Method này minh họa một phần implementation cần được gọi trong context repository hợp lệ. Nó không tự bật exposure và không phải cấu hình repository reactive hoàn chỉnh.

Nếu công việc thật cần chạy bất đồng bộ, truyền snapshot như tham số hoặc một cơ chế context ứng dụng được thiết kế tường minh. Không giữ toàn bộ holder như một biến toàn cục, và không gọi lại API ambient context từ callback chỉ vì callback từng được tạo trong fragment.

Với coroutine, cũng cần kiểm tra thời điểm lấy context khi có suspension hoặc đổi dispatcher. Từ khóa `suspend` không tạo ra một bảo đảm ThreadLocal mới cho extension này.

## 10. Đo riêng phần exposure bằng một benchmark hẹp

Có hai câu hỏi đo lường khác nhau:

1. Cấu hình exposure làm đường gọi proxy thay đổi bao nhiêu khi không có store I/O?
2. Thay đổi phạm vi exposure ảnh hưởng workload thật ra sao?

Câu thứ nhất phù hợp với một microbenchmark có kiểm soát. Câu thứ hai cần bài đo ứng dụng trên store và tải tương ứng.

JMH là công cụ dành cho benchmark trên JVM. Nó không tự làm một workload sai mục tiêu trở thành đại diện cho ứng dụng, nhưng hỗ trợ thiết lập phép đo tốt hơn một vòng lặp bấm giờ đơn giản. [Dự án OpenJDK JMH](https://github.com/openjdk/jmh).

### 10.1. Một benchmark core không truy cập database

Ví dụ sau dùng API Spring Data Commons 3.5.0 và JMH. Nó tạo repository proxy với target đơn giản để quan sát phần tăng thêm của việc bật exposure.

Target không đọc context, không implement RepositoryMetadataAccess và không truy cập store. Như vậy, hai trường hợp chỉ khác cấu hình cờ trên factory.

~~~java
import java.util.concurrent.TimeUnit;

import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Level;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Param;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.Setup;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Warmup;

import org.springframework.data.repository.Repository;
import org.springframework.data.repository.core.EntityInformation;
import org.springframework.data.repository.core.RepositoryInformation;
import org.springframework.data.repository.core.RepositoryMetadata;
import org.springframework.data.repository.core.support.RepositoryFactorySupport;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 5)
@Measurement(iterations = 5)
@Fork(3)
public class MetadataExposureBenchmark {

    @Param({"false", "true"})
    public boolean exposeMetadata;

    private BenchRepository repository;
    private int input;

    @Setup(Level.Trial)
    public void setup() {
        BenchFactory factory = new BenchFactory();
        factory.setBeanClassLoader(
            MetadataExposureBenchmark.class.getClassLoader()
        );
        factory.setExposeMetadata(exposeMetadata);

        repository = factory.getRepository(BenchRepository.class);
    }

    @Benchmark
    public int repositoryCall() {
        return repository.touch(++input);
    }

    public record BenchEntity(Long id) {
    }

    public interface BenchRepository
            extends Repository<BenchEntity, Long> {
        int touch(int value);
    }

    public static class BenchTarget {
        public int touch(int value) {
            return value + 1;
        }
    }

    private static class BenchFactory
            extends RepositoryFactorySupport {

        @Override
        public <T, ID> EntityInformation<T, ID> getEntityInformation(
                Class<T> domainClass) {
            throw new UnsupportedOperationException(
                "Benchmark này không dùng persistence"
            );
        }

        @Override
        protected Object getTargetRepository(
                RepositoryInformation information) {
            return new BenchTarget();
        }

        @Override
        protected Class<?> getRepositoryBaseClass(
                RepositoryMetadata metadata) {
            return BenchTarget.class;
        }
    }
}
~~~

Đây là một fixture benchmark, không phải factory dùng cho repository production. Nó cố ý chỉ có một method target đơn giản và không cung cấp persistence functionality.

Cần cấu hình dependency và annotation processing của JMH trước khi thực thi. Bài viết không chứa kết quả đã chạy benchmark.

### 10.2. Benchmark này đo và chưa đo điều gì?

| Đo được theo thiết kế | Không tự đo được |
| --- | --- |
| Chênh lệch đường proxy khi cờ false/true trên fixture | Latency database, network và driver |
| Chi phí runtime đã qua warmup của target đơn giản | Startup toàn application context |
| Allocation thực tế nếu thu thập profiler phù hợp | Kích thước object cố định cho mọi JDK |
| Tác động tổng hợp của chuỗi advice thay đổi | Riêng một thao tác ThreadLocal trong môi trường khác |
| Một baseline cho so sánh phiên bản/cấu hình | P99 hoặc throughput toàn ứng dụng production |

Không thêm fragment có marker vào cả hai trường hợp rồi cho rằng `@Param false` là baseline tắt exposure. Theo bảng ở phần 7, cả hai có thể vẫn bật.

Tương tự, không để target của trường hợp false đọc context rồi ném lỗi trong khi true chạy bình thường. Khi đó hai workload không còn tương đương.

### 10.3. Tránh các lỗi đo cơ bản

- Tạo factory và proxy trong setup thay vì mỗi operation nếu đang đo steady state.
- Giữ cùng target, input và đường gọi cho hai cấu hình.
- Trả về hoặc tiêu thụ kết quả để hạn chế phép tính bị tối ưu bỏ.
- Warmup trước giai đoạn thu thập kết quả.
- Dùng nhiều fork và xem mức dao động.
- Tách phép đo có profiler khỏi baseline khi profiler gây nhiễu đáng kể.
- Không bật log per-call ở một cấu hình rồi tắt ở cấu hình còn lại.

Việc tiêu thụ kết quả và ảnh hưởng của tối ưu JVM được minh họa trong [JMH sample về dead-code elimination](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_08_DeadCode.java); cách dùng fork giúp hạn chế ảnh hưởng profile JVM lẫn nhau được giải thích trong [JMH sample về forking](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_12_Forking.java).

Một chênh lệch nhỏ hơn mức nhiễu chưa đủ để tuyên bố có lợi ích. Cũng không suy rằng microbenchmark không thấy khác biệt rõ nghĩa là mọi workload tần suất cao đều không chịu tác động.

## 11. Đo ảnh hưởng trong workload thật

Sau benchmark hẹp, hãy kiểm tra cùng workload trên cấu hình ứng dụng cần dùng.

Một so sánh hữu ích là:

| Cấu hình | Repository có extension cần context | Repository còn lại |
| --- | --- | --- |
| Bật có chọn lọc | Bật | Giữ mặc định nếu không có nhu cầu khác |
| Bật toàn bộ | Bật | Bật |

Hai cấu hình này giữ chức năng của extension nhưng khác phạm vi exposure. Đây là so sánh có ý nghĩa hơn việc tắt mọi thứ rồi để extension cần context bị lỗi.

Nếu muốn có trường hợp “không exposure ở đâu cả”, phải dùng một workload không cần context hoặc đã chuyển sang thiết kế truyền thông tin tường minh với chức năng tương đương. Một lần chạy nhanh vì bỏ qua công việc không phải tối ưu tương đương.

### 11.1. Các chỉ số nên ghi nhận

| Chỉ số | Câu hỏi được hỗ trợ |
| --- | --- |
| Số lời gọi theo repository | Phạm vi nào chịu ảnh hưởng nhiều nhất? |
| CPU và allocation theo operation | Có chi phí tăng ở phía JVM không? |
| Throughput tại cùng điều kiện tải | Hệ thống xử lý được bao nhiêu công việc? |
| P50/P95/P99 latency | Độ trễ của request thay đổi thế nào? |
| Query count và thời gian store | Hai trường hợp có thực hiện cùng công việc persistence không? |
| Error/timeout rate | Có đánh đổi hiệu năng bằng lỗi hoặc thiếu kết quả không? |
| GC và bộ nhớ | Allocation tăng có kéo theo áp lực thu gom không? |

Số lần gọi repository không đồng nhất với số query xuống store. Một method trả Page có thể cần thêm công việc đếm; một lời gọi fragment có thể thực hiện nhiều thao tác. Cần ghi nhận hai đại lượng riêng thay vì dùng chúng thay thế cho nhau.

Đối với tác vụ reactive/coroutine, đo đến đúng mốc hoàn tất công việc. Chỉ đo thời gian tạo Mono/Flux/Flow sẽ bỏ qua phần thực thi store và mapping diễn ra sau đó.

### 11.2. Giữ điều kiện so sánh ổn định

Cần kiểm soát các yếu tố có thể lấn át phần đang đo:

- Cùng dataset, phân bố tham số và tỷ lệ các loại repository call.
- Cùng schema/index và kế hoạch query trong phạm vi hợp lý.
- Cùng trạng thái cache hoặc một chính sách warmup rõ ràng.
- Cùng connection pool, concurrency và mức tải.
- Cùng mức logging/tracing và các interceptor ngoài exposure.
- Cùng kiểu trả về, số phần tử được tiêu thụ và logic nghiệp vụ.

Nếu cấu hình “selective” đồng thời giảm page size hoặc bỏ một query count, chênh lệch không còn là tác động riêng của metadata exposure.

Với workload bị chi phối bởi I/O, phần chênh lệch proxy có thể khó quan sát ở latency. Khi đó vẫn có thể xem CPU/allocation ở mức tải đủ lớn, nhưng không gán mọi thay đổi nhỏ cho exposure khi dữ liệu đo chưa hỗ trợ.

### 11.3. Phân tích kết quả theo ý nghĩa thực tế

Một báo cáo đo nên nêu:

~~~text
Phiên bản Spring Data/JDK:
Phạm vi repository được bật:
Nguồn bật: marker hay cấu hình factory:
Workload và dữ liệu:
Mức concurrency:
Warmup và khoảng đo:
Latency/throughput/error:
CPU và allocation:
Mức dao động giữa các lần chạy:
Kết luận trong phạm vi đã đo:
~~~

Đây là các thông tin cần cho việc diễn giải, không phải một yêu cầu tạo thêm file cấu hình trong ứng dụng.

Không chuyển thẳng số nanosecond của microbenchmark thành một tỷ lệ cải thiện request. Cũng không lấy kết quả trên target không có I/O làm bằng chứng cho thời gian query hoặc khả năng chịu tải của database.

## 12. Giảm nhu cầu metadata thay vì chỉ tìm cách tắt cờ

Đôi khi giải pháp tốt là làm extension ít phụ thuộc ambient context hơn.

### 12.1. Truyền thông tin cố định qua dependency

Nếu một collaborator chỉ làm việc với CatalogItem, domain type đã được biết trong thiết kế. Không nhất thiết phải truy vấn context mỗi lần để tìm lại lớp đó.

Có thể truyền domain type hoặc cấu hình target qua constructor, hoặc dùng một collaborator gắn với repository cụ thể. Nếu làm như vậy, cần wiring instance đúng phạm vi; không giả định Spring tự tạo một bean riêng cho mỗi giá trị generic chỉ vì constructor nhận Class<T>.

Đây là đánh đổi giữa tính tổng quát và sự tường minh. Một extension thực sự dùng lại cho nhiều repository vẫn có thể cần context; không loại bỏ khả năng tái sử dụng chỉ để tránh một chi phí chưa đáng kể.

### 12.2. Tách thông tin cấu trúc và dữ liệu thay đổi theo lời gọi

| Loại dữ liệu | Khả năng xử lý |
| --- | --- |
| Repository interface, domain type, Method | Có thể làm khóa cho phân tích cấu trúc |
| Kết quả phân tích annotation cố định | Có thể cache nếu semantics không đổi |
| Tenant, actor, locale, tham số query | Cần đi theo lời gọi hiện tại |
| Target index/collection thay đổi theo runtime | Không cache chỉ theo domain class nếu chưa đủ khóa |
| Kiểu projection động truyền qua tham số | Không suy từ Method một mình nếu còn phụ thuộc đối số |

Một cache chỉ theo domain type có thể sai nếu hai repository cùng domain nhưng khác store, target hoặc chính sách dispatch. Chọn khóa theo toàn bộ những yếu tố ảnh hưởng tới kết quả.

Không giữ một RepositoryMethodContext được đọc lần đầu rồi tái sử dụng cho mọi lời gọi. Chỉ cache kết quả phân tích cấu trúc đã xác định rõ phạm vi.

### 12.3. Cache lookup không xóa chi phí exposure

Nếu extension cache kết quả phân tích annotation, phần xử lý ứng dụng có thể giảm. Nhưng proxy vẫn có phần công việc exposure nếu cấu hình còn bật.

Do đó, cần đo riêng:

~~~text
Chi phí bật context ở proxy
    +
Chi phí lấy thông tin từ context
    +
Chi phí ứng dụng xử lý/cache thông tin
~~~

Không gọi tổng chi phí của cả ba phần là “chi phí ThreadLocal” rồi tối ưu sai vị trí.

### 12.4. Domain class không tự cho tên tài nguyên chính xác

Một fragment có thể dùng domain type làm khóa chọn search index, collection hoặc table. Tuy nhiên, tên class không tự bằng tên vật lý của tài nguyên trong mọi module.

Nếu extension cần tên target, hãy dùng registry hoặc mapping configuration phù hợp store. Tránh lấy tên đơn giản của class rồi chuyển chữ thường như một quy tắc toàn cục mà không kiểm chứng.

exposeMetadata chỉ giúp extension biết thông tin lời gọi được cung cấp. Nó không tự bảo đảm routing đúng, không tạo index và không thay các quy tắc mapping của từng kho dữ liệu.

## 13. Kiểm tra cấu hình đúng trước khi diễn giải hiệu năng

Không cần benchmark để phát hiện một cấu hình bật sai phạm vi. Trước phép đo, nên có các kiểm chứng chức năng phù hợp:

| Tình huống | Điều cần quan sát |
| --- | --- |
| Fragment có marker | Context bên trong fragment mô tả đúng repository và method |
| Repository chọn qua marker ứng dụng/BPP | Chỉ nhóm được chọn nhận chính sách explicit tương ứng |
| Repository không cần context | Chức năng CRUD/query vẫn đúng |
| Hai repository dùng chung fragment | Mỗi lời gọi nhận đúng repository/domain của nó |
| Lời gọi lồng nhau | Context của lời gọi ngoài được khôi phục sau lời gọi trong |
| Fragment ném exception | Context không bị giữ sai cho công việc kế tiếp |
| Code chạy sau khi rời proxy | Không dựa vào context của lời gọi đã kết thúc |
| Callback reactive/executor | Không giả định ambient context tự truyền qua ranh giới |
| Cùng domain ở hai nhóm store | Registry/cache không trộn cấu hình target |

Khi xác nhận method, dùng đúng identity/signature cần thiết thay vì chỉ so tên. Repository có method overload có thể dùng cùng tên nhưng khác tham số.

Một kiểm chứng chỉ gọi trực tiếp `new InvocationInspectionImpl().describeInvocation()` sẽ không đi qua repository proxy. Việc nó không có context không chứng minh marker của repository bị cấu hình sai; bài test đã bỏ qua chính hạ tầng cần kiểm tra.

Tương tự, test trực tiếp helper nhận một InvocationSummary dựng sẵn có thể xác nhận logic của helper, nhưng chưa xác nhận exposure trên repository proxy.

### 13.1. Không để một cấu hình test toàn cục che lỗi

Nếu test dùng post-processor bật exposure cho tất cả repository, extension có thể chạy được dù production quên khai báo marker hoặc điều kiện chọn.

Vì vậy, test kiểm tra phạm vi cần dùng chính sách tương ứng với môi trường triển khai, không âm thầm thêm một cấu hình rộng hơn để hết lỗi.

Nếu một baseline performance khai báo cờ false nhưng composition có marker, phải sửa fixture trước khi đọc kết quả đo. Không sửa số liệu hoặc đặt tên baseline thành “off” khi đường gọi thực tế vẫn được bật.

## 14. Các lỗi thường gặp khi tối ưu exposeMetadata

| Biểu hiện hoặc quyết định | Vấn đề cần xem xét | Hướng xử lý |
| --- | --- | --- |
| Bật cho mọi factory trong thư viện dùng chung | Phạm vi vượt use case của extension | Chọn composition hoặc nhóm repository có nhu cầu |
| Tắt cờ nhưng proxy vẫn có exposure | Marker hoặc cấu hình khác vẫn yêu cầu | Xác định tất cả nguồn bật |
| Cho rằng chỉ method fragment chịu chi phí | Exposure được cài ở proxy | Đánh giá toàn bộ workload đi qua proxy đó |
| getContext lỗi trong constructor | Chưa có lời gọi repository | Dùng dependency tường minh khi khởi tạo |
| getContext lúc có lúc không trong callback | Đọc ngoài phạm vi hoặc đổi luồng | Lấy snapshot hợp lệ và truyền theo công việc |
| Context của B lại mô tả A | Ambient context của lời gọi bao ngoài | Kiểm tra phạm vi B và identity context |
| Bật metadata để sửa query chậm | Cờ không thay kế hoạch query | Đo query, index, mapping và round-trip riêng |
| Benchmark false/true giống nhau | Cả hai có thể được marker bật | Kiểm tra composition của fixture |
| Benchmark true chậm do logging | Đã thay nhiều yếu tố cùng lúc | Giữ workload tương đương, tách phần logic extension |
| Lưu context trong field singleton | State theo lời gọi bị dùng chung | Dùng biến cục bộ/snapshot theo công việc |

Không dùng tối ưu metadata làm lý do bỏ các abstraction cần thiết như projection, phân trang hoặc auditing. Phải xác định chi phí nào thực sự thuộc exposure và chi phí nào thuộc công việc ứng dụng cần thực hiện.

Nếu bottleneck chính là một query count đắt hoặc tải quá nhiều entity, thay đổi phạm vi exposure không thay thế việc giải quyết bottleneck đó. Tuy nhiên, việc query chậm cũng không biện minh cho bật một interceptor không cần thiết lên mọi repository.

## 15. Tự kiểm tra kiến thức

1. exposeMetadata khác metadata mapping và metadata query ở điểm nào?
2. Tại sao mặc định false không có nghĩa Spring Data không cần metadata để chạy repository?
3. RepositoryMetadataAccess nên được đặt ở đâu, và phạm vi bật thực tế là gì?
4. Vì sao một CRUD method không đọc context vẫn có thể chịu phần chi phí exposure trên proxy đã bật?
5. setExposeMetadata(false) có tắt nhu cầu do fragment marker tạo ra không?
6. Vì sao post-processor cần điều kiện chọn repository thay vì chỉ kiểm tra kiểu factory bean?
7. Một lần getContext không ném lỗi trong lời gọi lồng nhau chưa chứng minh điều gì?
8. Khi trả Mono/Flux hoặc đổi dispatcher, tại sao cần xem lại thời điểm đọc context?
9. Benchmark nào giúp tách chi phí đường proxy khỏi I/O store, và nó chưa chứng minh điều gì?
10. Một baseline không dùng exposure phải kiểm tra những nguồn bật nào?
11. Khi nào cache theo domain class là chưa đủ cho extension?
12. Cần giữ những yếu tố nào tương đương khi so phạm vi bật chọn lọc với bật toàn bộ?

Quyết định bật exposeMetadata cần xuất phát từ nhu cầu của extension, được giới hạn theo repository composition hoặc chính sách chọn factory rõ ràng. Đo đường proxy và workload thực tế riêng, đồng thời giữ đúng vòng đời context, giúp đánh giá chi phí mà không làm sai chức năng của repository.
