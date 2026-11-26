# Khi nào cần tùy chỉnh factory thay vì thêm fragment?

Cần tùy chỉnh repository factory khi yêu cầu tác động tới **cách repository được tạo và lắp ráp**: chọn implementation nền, xử lý metadata, cài đặt cơ chế can thiệp vào proxy hoặc thay đổi chiến lược tạo truy vấn. Nếu yêu cầu chủ yếu là thêm một thao tác nghiệp vụ, repository fragment thường là điểm mở rộng phù hợp hơn.

Giữa hai lựa chọn đó còn có một mức quan trọng: **custom base repository**. Nếu chỉ cần thay implementation chung cho nhiều repository và module đã có cấu hình chọn base class, chưa cần tự viết factory.

Bài học thuộc chương **Factory và metadata** của **SPRING_DATA_COMMONS**. Mục tiêu là chọn đúng tầng mở rộng của abstraction Spring Data, giữ các khả năng CRUD, truy vấn, phân trang và projection hoạt động theo hợp đồng của module lưu trữ.

Sau bài học, bạn có thể:

- Phân biệt fragment, base repository, factory và factory bean.
- Nhận diện yêu cầu thay đổi hành vi nghiệp vụ hay cơ chế tạo repository.
- Giải thích vai trò của repository metadata trong quá trình lắp ráp proxy.
- Tùy chỉnh một hook của factory mà vẫn giữ cấu hình mặc định của store.
- Đánh giá phạm vi ảnh hưởng và cách kiểm chứng một thay đổi hạ tầng repository.

## 1. Nhìn repository như một đối tượng được lắp ráp

Một interface repository không tự có implementation chỉ vì nó khai báo `extends Repository`. Spring Data cần đọc thông tin kiểu, chọn implementation và tạo proxy.

Sơ đồ khái quát:

~~~text
Interface repository
        |
        | scan và đăng ký bean
        v
Factory bean của module
        |
        | khởi tạo/cấu hình
        v
Repository factory
        |
        +--> đọc metadata
        +--> chọn implementation nền
        +--> kết hợp các fragment
        +--> tạo cơ chế thực thi query method
        +--> cấu hình proxy và interceptor
        |
        v
Repository proxy được inject vào ứng dụng
~~~

Khi caller gọi một phương thức, proxy có thể chuyển tới:

- Implementation nền, chẳng hạn các thao tác CRUD.
- Một fragment do ứng dụng cung cấp.
- Implementation của query method.
- Default method trên interface, theo cơ chế hỗ trợ của framework.

Đây là sơ đồ trách nhiệm, không phải thứ tự nội bộ cố định cho mọi phiên bản. Chi tiết lắp ráp và thứ tự interceptor phải được xác nhận trong module đang dùng.

Vì vậy, cần hỏi trước: **yêu cầu nằm ở một phương thức được gọi, hay nằm ở quá trình quyết định phương thức ấy được thực thi thế nào?**

## 2. Bốn thành phần dễ bị nhầm

| Thành phần | Trách nhiệm chính | Ví dụ |
|---|---|---|
| Repository fragment | Đóng gói một nhóm thao tác tùy chỉnh và implementation của chúng | Tạo báo cáo khách hàng |
| Base repository | Implementation dùng chung cho một tập repository | Bổ sung thao tác đặc thù JPA hoặc thay hành vi chung |
| Repository factory | Tạo và cấu hình repository từ metadata, implementation và các thành phần hỗ trợ | Cài hook cho proxy theo loại repository |
| Repository factory bean | Cầu nối với Spring container để tạo/cấu hình factory và cung cấp repository | Factory bean riêng cho một vùng scan |

Ví dụ các kiểu thường gặp trong ứng dụng JPA:

| Phạm vi | Kiểu minh họa |
|---|---|
| Commons | `RepositoryFactorySupport` |
| Commons | `RepositoryFactoryBeanSupport` |
| JPA | `JpaRepositoryFactory` |
| JPA | `JpaRepositoryFactoryBean` |
| JPA | `SimpleJpaRepository` |

Không nên thay factory của store bằng một factory Commons chung mà bỏ qua phần tích hợp store. JPA, MongoDB và các module khác cần những thành phần thực thi và metadata riêng.

### 2.1. “Factory” không phải phương thức tạo entity

Repository factory tạo đối tượng repository và cơ chế dispatch của nó. Nó không phải constructor của `Customer`, không phải nơi tạo mỗi entity mới và cũng không phải service xử lý nghiệp vụ.

Tương tự, factory bean trong Spring là thành phần cung cấp đối tượng repository cho container. Nó không đồng nghĩa một bean bất kỳ có phương thức tên `createRepository`.

## 3. Khi nào fragment đã đủ?

Dùng fragment khi có một hợp đồng phương thức rõ ràng và có thể triển khai bằng API store hiện có.

Các ví dụ phù hợp:

- Một báo cáo dùng join, aggregate hoặc projection riêng.
- Một thao tác tìm kiếm cần Querydsl, JPQL hoặc API template.
- Một nhóm thao tác của riêng phân hệ khách hàng.
- Một hành vi có thể tái sử dụng có chọn lọc qua interface fragment.

Ví dụ hợp đồng:

~~~java
import java.time.Instant;
import java.util.List;

public interface CustomerReports {

    List<CustomerRevenue> summarizeRevenue(
        Instant fromInclusive,
        Instant toExclusive
    );
}
~~~

Repository ghép fragment:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                CustomerReports {
}
~~~

Implementation có thể là `CustomerReportsImpl`, được phát hiện theo quy ước và cấu hình fragment của ứng dụng. Trong đó, bạn có thể dùng `EntityManager` hoặc query API phù hợp để tạo báo cáo.

Ví dụ này giả định `CustomerRevenue` là kiểu kết quả của báo cáo; không cần thay factory chỉ để thêm nó.

### 3.1. Truy vấn phức tạp chưa phải lý do viết factory

Một query có nhiều join, GROUP BY hoặc một pipeline aggregation phức tạp vẫn có thể nằm trong fragment. Độ phức tạp của câu truy vấn không đồng nghĩa độ phức tạp của cơ chế tạo repository.

Nếu có thể diễn đạt yêu cầu thành:

~~~text
Khi gọi phương thức X, dùng API store Y để trả kết quả Z.
~~~

thì nên xem xét fragment trước.

### 3.2. Fragment có thể can thiệp phương thức đã tồn tại

Fragment không chỉ dành cho tên phương thức mới. Với cấu trúc interface và chữ ký phù hợp, cơ chế composition có thể cho phép fragment cung cấp implementation cho phương thức đã được repository kế thừa.

Vì vậy, không kết luận “muốn thay save thì chắc chắn phải viết factory”.

Tuy nhiên, phải kiểm tra độ ưu tiên dispatch, generic signature và phạm vi các repository ghép fragment đó. Một override cho một nhóm repository khác với chính sách implementation nền cho toàn bộ vùng cấu hình.

### 3.3. Fragment không tự kiểm soát mọi phương thức khác

Nếu fragment triển khai `summarizeRevenue`, nó không tự bao quanh mọi lời gọi `save`, `findById`, query method hoặc fragment khác.

Muốn tác động xuyên suốt proxy cần một cơ chế can thiệp phù hợp. Đừng thêm một fragment rồi kỳ vọng nó nhận được mọi invocation của repository.

## 4. Base repository: mức mở rộng cần cân nhắc trước factory

Giả sử ứng dụng JPA cần một thao tác `refresh` dùng chung cho nhiều repository.

Có thể định nghĩa một interface nền:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.repository.NoRepositoryBean;

@NoRepositoryBean
public interface RefreshableRepository<T, ID>
        extends JpaRepository<T, ID> {

    void refresh(T entity);
}
~~~

`@NoRepositoryBean` cho biết đây là interface nền, không phải repository cụ thể để tạo bean trực tiếp.

Implementation:

~~~java
import jakarta.persistence.EntityManager;

import org.springframework.data.jpa.repository.support.JpaEntityInformation;
import org.springframework.data.jpa.repository.support.SimpleJpaRepository;
import org.springframework.transaction.annotation.Transactional;

public class RefreshableJpaRepository<T, ID>
        extends SimpleJpaRepository<T, ID>
        implements RefreshableRepository<T, ID> {

    private final EntityManager entityManager;

    public RefreshableJpaRepository(
            JpaEntityInformation<T, ?> entityInformation,
            EntityManager entityManager) {
        super(entityInformation, entityManager);
        this.entityManager = entityManager;
    }

    @Override
    @Transactional
    public void refresh(T entity) {
        entityManager.refresh(entity);
    }
}
~~~

Ví dụ chọn hệ `jakarta.persistence`. Dự án dùng hệ persistence khác cần bộ dependency và cấu hình tương thích.

Cấu hình JPA:

~~~java
@Configuration
@EnableJpaRepositories(
    basePackages = "com.example.customer",
    repositoryBaseClass = RefreshableJpaRepository.class
)
public class CustomerRepositoryConfiguration {
}
~~~

Repository cụ thể:

~~~java
public interface CustomerRepository
        extends RefreshableRepository<Customer, Long> {
}
~~~

Trong ví dụ, factory mặc định của module vẫn được sử dụng. Cấu hình chỉ thay base class trong phạm vi scan.

`refresh` có ngữ nghĩa JPA: đối tượng phải thỏa điều kiện quản lý của persistence context và lời gọi phải ở phạm vi thực thi phù hợp. Nó có thể nạp lại trạng thái từ store. Không coi đây là một thao tác chung áp dụng nguyên vẹn cho mọi kho dữ liệu.

Điểm thiết kế cần rút ra: nếu hook cấu hình hiện có đã chọn được implementation mong muốn, việc viết thêm factory có thể không cần thiết.

## 5. Những trường hợp thực sự cần tác động tới factory

Factory phù hợp khi yêu cầu nằm ở cơ chế lắp ráp repository và các điểm cấu hình đơn giản chưa đủ.

### 5.1. Chọn implementation theo metadata của từng repository

Một chính sách có thể cần đọc annotation hoặc kiểu repository để quyết định base implementation.

Nếu toàn bộ vùng scan chỉ cần cùng một base class, `repositoryBaseClass` thường đủ. Nếu quyết định thay đổi theo từng repository và không thể phân tách hợp lý bằng cấu hình, hook của factory có thể cần thiết.

Việc chọn class phải đi cùng cách tạo target, constructor và composition tương thích. Chỉ trả về tên một class khác mà không bảo đảm các phần còn lại sẽ không tạo được một repository đúng.

### 5.2. Thêm thành phần vào proxy trong quá trình tạo

Một integration library có thể muốn cài interceptor cho các repository được tạo, đồng thời lấy metadata như interface repository và domain type ngay lúc lắp ráp.

Đây là công việc của proxy/factory hook, không phải một phương thức fragment đơn lẻ.

Tuy nhiên, nếu yêu cầu chỉ là logging hoặc metrics thông thường, cơ chế AOP hay observation hiện có của ứng dụng có thể đã đủ. Factory không phải lựa chọn bắt buộc cho mọi hành vi xuyên suốt.

### 5.3. Thay đổi cách tạo và giải quyết query method

Một extension hạ tầng có thể cần tích hợp một cơ chế query riêng, tham gia query lookup strategy hoặc quá trình tạo repository query.

Trường hợp này liên quan tới cách một phương thức trên interface được chuyển thành đối tượng thực thi. Nó khác với việc viết một truy vấn thủ công trong fragment.

Đây là vùng phụ thuộc sâu vào SPI và module store. Nếu chỉ có vài query đặc biệt, fragment hoặc query được khai báo thường có phạm vi nhỏ hơn.

### 5.4. Tích hợp cơ chế repository của một store hoặc thư viện hạ tầng

Khi phát triển adapter hoặc thư viện repository, có thể cần phối hợp metadata, target, composition và các thành phần thực thi ở cấp hệ thống.

Đối tượng sử dụng điểm mở rộng này thường là code hạ tầng. Logic “tổng doanh thu của khách hàng” vẫn nên nằm ở phương thức nghiệp vụ hoặc fragment, dù hạ tầng phía dưới có factory tùy chỉnh.

## 6. Metadata nào được dùng ở thời điểm tạo?

Hai abstraction cần phân biệt:

| Kiểu | Thông tin điển hình |
|---|---|
| `RepositoryMetadata` | Interface repository, kiểu domain, kiểu định danh và thông tin liên quan đến hợp đồng repository |
| `RepositoryInformation` | Bổ sung thông tin implementation nền, phân loại hoặc ánh xạ phương thức phục vụ thực thi |

Metadata này giúp trả lời:

~~~text
Repository này quản lý kiểu miền nào?
Kiểu ID là gì?
Interface repository cụ thể là interface nào?
Một phương thức được xử lý bởi base implementation hay đường thực thi khác?
~~~

Nó không phải dữ liệu của một bản ghi và không phải schema của toàn bộ database.

Với JPA, `JpaEntityInformation` là một abstraction khác, phục vụ metadata entity cho module, chẳng hạn thông tin định danh và xác định entity mới. Không hoán đổi repository metadata với entity information chỉ vì cả hai đều có chữ “information”.

### 6.1. Metadata cấu trúc không phải ngữ cảnh từng request

Factory thường được cấu hình khi repository được khởi tạo. Nó không chạy lại toàn bộ cho mỗi lời gọi service.

Vì vậy, các quyết định phụ thuộc người dùng, tenant hoặc tham số hiện tại không nên bị chụp cố định vào một repository tại thời điểm khởi tạo.

Ví dụ, nếu interceptor cần một ngữ cảnh thay đổi theo từng lời gọi, nó phải tra cứu ngữ cảnh ở lúc invocation theo thiết kế phù hợp. Đọc một giá trị tại startup rồi giữ mãi không tạo ra hành vi động.

Cũng không nên chia sẻ trong factory những đối tượng tích lũy điều kiện truy vấn có thể bị sửa qua nhiều request.

### 6.2. Metadata không bảo đảm mọi đường thực thi tương đương

Một repository có thể kết hợp CRUD, derived query, query được khai báo, default method và fragment.

Thay base class chưa chắc thay mọi query method. Thêm một interceptor chưa chắc tạo được thứ tự mong muốn với transaction advice. Can thiệp query lookup cũng chưa chắc ảnh hưởng phương thức do fragment triển khai.

Mỗi hook phải được đánh giá theo những loại phương thức mà nó thực sự tác động.

## 7. Ví dụ: cấu hình proxy qua factory đã được module tạo

Ví dụ sau minh họa một thư viện muốn gắn thông tin interface repository vào phép đo thời gian invocation.

Mục tiêu là học cách dùng hook của factory. Trong ứng dụng chỉ cần đo thời gian đơn giản, hãy đánh giá cơ chế quan sát sẵn có trước khi chọn mức tùy chỉnh này.

### 7.1. Factory bean tùy chỉnh

~~~java
import jakarta.persistence.EntityManager;

import org.aopalliance.intercept.MethodInterceptor;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.data.jpa.repository.support.JpaRepositoryFactoryBean;
import org.springframework.data.repository.Repository;
import org.springframework.data.repository.core.support.RepositoryFactorySupport;

public class TimedJpaRepositoryFactoryBean<
        R extends Repository<T, ID>, T, ID>
        extends JpaRepositoryFactoryBean<R, T, ID> {

    private static final Logger log =
        LoggerFactory.getLogger(TimedJpaRepositoryFactoryBean.class);

    public TimedJpaRepositoryFactoryBean(
            Class<? extends R> repositoryInterface) {
        super(repositoryInterface);
    }

    @Override
    protected RepositoryFactorySupport createRepositoryFactory(
            EntityManager entityManager) {

        RepositoryFactorySupport factory =
            super.createRepositoryFactory(entityManager);

        factory.addRepositoryProxyPostProcessor(
            (proxyFactory, repositoryInformation) -> {

                String repositoryName = repositoryInformation
                    .getRepositoryInterface()
                    .getName();

                proxyFactory.addAdvice(
                    (MethodInterceptor) invocation -> {

                        if (invocation.getMethod()
                                .getDeclaringClass() == Object.class) {
                            return invocation.proceed();
                        }

                        long startedAt = System.nanoTime();

                        try {
                            return invocation.proceed();
                        } finally {
                            long elapsedNanos =
                                System.nanoTime() - startedAt;

                            log.debug(
                                "repository={} method={} elapsedNanos={}",
                                repositoryName,
                                invocation.getMethod().getName(),
                                elapsedNanos
                            );
                        }
                    }
                );
            }
        );

        return factory;
    }
}
~~~

Những điểm cần chú ý:

- Factory bean vẫn kế thừa `JpaRepositoryFactoryBean`.
- Gọi `super.createRepositoryFactory(...)` để giữ cách tạo và cấu hình factory của module.
- Hook được thêm trước khi repository proxy được tạo.
- Metadata repository được dùng để tạo thông tin gắn với proxy.
- Interceptor gọi `invocation.proceed()` và trả lại kết quả gốc.
- Khối `finally` ghi thời gian dù lời gọi thành công hay ném ngoại lệ.

Đây là một dạng **tùy chỉnh factory**, dù không tự viết subclass của `JpaRepositoryFactory`. Không phải mọi yêu cầu đều cần thay cả lớp factory.

Nếu viết lại factory từ đầu, người triển khai phải tự bảo đảm những cấu hình module vốn đã thiết lập. Việc giữ factory do superclass tạo giúp giảm phần cơ chế phải tự tái tạo trong ví dụ này.

### 7.2. Đăng ký trong cấu hình repository

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;

@Configuration
@EnableJpaRepositories(
    basePackages = "com.example.customer",
    repositoryFactoryBeanClass = TimedJpaRepositoryFactoryBean.class
)
public class CustomerRepositoryConfiguration {
}
~~~

Thay đổi cấu hình scan hiện có cho phạm vi mong muốn. Không thêm nhiều cấu hình quét trùng một vùng chỉ để bật từng tùy chọn.

Nếu cần cả custom base class ở mục trước, các thuộc tính cấu hình có thể được xem xét cùng nhau trong một cấu hình repository, với điều kiện implementation và constructor tương thích. Các ví dụ trong bài là các lựa chọn minh họa, không phải yêu cầu tạo hai bean cấu hình cùng quét `com.example.customer`.

### 7.3. Phép đo này đo điều gì?

Nó đo khoảng thời gian lời gọi đi qua vị trí interceptor được cài đặt.

Nó không mặc nhiên bằng:

- Thời gian thực thi SQL thuần.
- Thời gian commit của toàn bộ giao dịch service.
- Thời gian caller tiêu thụ xong một `Stream`.
- Thời gian xử lý bất đồng bộ sau khi phương thức đã trả về.

Thứ tự với các advice khác cũng cần được xác nhận. Ví dụ này không đặt tên phép đo là “database time”, vì nó chưa có bằng chứng ở cấp truy vấn store.

Nếu phương thức trả stream, kết quả có thể được tiêu thụ sau khi interceptor đã kết thúc. Logic đóng stream và phạm vi tài nguyên vẫn là trách nhiệm của đường đọc tương ứng.

## 8. Khi nào cần subclass factory thực sự?

Nếu hook công khai trên factory hiện có đã giải quyết được yêu cầu, có thể chưa cần tạo một lớp factory mới.

Subclass factory trở nên cần thiết hơn khi phải thay một quyết định nội bộ được cung cấp qua protected hook, chẳng hạn cách chọn base class hoặc tạo thành phần thực thi query.

Khi đó, thường có ba phần:

~~~text
Factory bean tùy chỉnh
    |
    | tạo
    v
Factory của store được mở rộng
    |
    | dùng các hook phù hợp
    v
Repository được lắp ráp theo chính sách mới
~~~

Không sao chép implementation factory của một phiên bản rồi duy trì như code ứng dụng nếu chỉ cần thay một hook. Hãy giữ phần mặc định và mở rộng ở điểm có hợp đồng rõ.

Các protected method và constructor là SPI phụ thuộc phiên bản/module. Trước khi áp dụng, xác nhận đúng chữ ký và trách nhiệm của hook trong dependency đang dùng.

Nếu phiên bản có một callback hoặc customizer chính thức đáp ứng đầy đủ yêu cầu, nó cũng là lựa chọn cần cân nhắc trước khi tăng mức phụ thuộc bằng subclass.

## 9. Bảng quyết định theo yêu cầu

| Yêu cầu thực tế | Điểm mở rộng nên xem xét trước | Khi nào mới cần factory? |
|---|---|---|
| Thêm báo cáo riêng của Customer | Fragment | Khi còn cần thay cơ chế lắp ráp hoặc thực thi ở cấp hạ tầng |
| Viết query nhiều join, aggregate | Fragment với query API của store | Độ phức tạp query tự nó chưa đủ |
| Thêm một phương thức chung cho nhiều repository | Fragment tái sử dụng hoặc base repository | Khi cách chọn/khởi tạo implementation không diễn đạt được bằng cấu hình sẵn có |
| Thay hành vi CRUD chung trong một phạm vi | Base repository hoặc cơ chế module phù hợp | Khi cần quyết định động theo metadata cấu trúc |
| Ghi nhận invocation trên repository | AOP, observation hoặc proxy hook | Khi integration cần cấu hình ở lúc tạo repository và dùng metadata tương ứng |
| Chọn target khác nhau theo loại repository | Cấu hình scan/base class nếu tách được | Khi chính sách thật sự cần hook của factory |
| Tạo cơ chế query method riêng | SPI của module | Khi phải tham gia quá trình tạo/giải quyết query |
| Bổ sung auditing cho entity | Cơ chế auditing của module | Auditing thông thường không đòi thay repository factory |
| Đổi cách sắp xếp hoặc phân trang một query | Hợp đồng repository, fragment hoặc query API | Khi có yêu cầu hạ tầng bổ sung vượt các API đó |

Một cách tự kiểm tra hữu ích:

> Nếu bỏ yêu cầu nghiệp vụ cụ thể đi, phần tùy chỉnh này có còn là một chính sách về cách tạo repository không?

Nếu câu trả lời là không, nó có thể đang thuộc fragment, service hoặc một cơ chế domain/store khác.

Nếu câu trả lời là có, tiếp tục kiểm tra liệu cấu hình hoặc hook hiện có đã đủ trước khi viết subclass.

## 10. Phạm vi ảnh hưởng khác nhau như thế nào?

### 10.1. Fragment có phạm vi ghép vào repository

Một repository không kế thừa fragment thì không tự có hợp đồng của fragment đó.

Có thể tái sử dụng một fragment ở nhiều repository, nhưng việc ghép phải có chủ đích. Với fragment generic, cần bảo đảm implementation nhận được metadata hoặc thành phần store thích hợp theo cơ chế mà phiên bản hỗ trợ.

Không tự suy generic type bằng vài thao tác reflection đơn giản rồi giả định đúng cho mọi chuỗi kế thừa interface. Spring Data đã có abstraction metadata cho mục đích hạ tầng.

### 10.2. Base class có phạm vi cấu hình

`repositoryBaseClass` có thể tác động tới các repository trong vùng cấu hình đó, rộng hơn một fragment chỉ ghép vào một interface.

Đặt base class không tự thêm phương thức vào mọi interface tại thời điểm biên dịch. Muốn caller gọi `refresh`, repository cụ thể vẫn phải kế thừa một interface khai báo phương thức, như ví dụ `RefreshableRepository`.

Implementation và hợp đồng công khai phải khớp nhau.

### 10.3. Factory customization tác động tới quá trình tạo cả nhóm proxy

Một lỗi trong factory có thể làm nhiều repository không khởi tạo được hoặc thay cách thực thi nhiều nhóm phương thức.

Vì vậy, phạm vi scan và cấu hình factory bean là một phần của thiết kế, không phải chi tiết phụ.

Trong ứng dụng có nhiều module hoặc nhiều persistence unit, cần xác định repository nào dùng factory nào và thành phần store nào được inject. Một cấu hình factory JPA không tự áp dụng cho repository của MongoDB.

### 10.4. Không đặt logic nghiệp vụ cụ thể vào khởi tạo proxy

Giả sử chỉ Customer cần tính doanh thu, không nên làm factory biết chi tiết `CustomerRevenue`, khoảng báo cáo và các trạng thái đơn hàng.

Đặt chúng trong fragment giữ hợp đồng gần với nghiệp vụ và dễ kiểm tra độc lập. Factory chỉ nên biết những chính sách hạ tầng thực sự cần cho việc lắp ráp repository.

## 11. Những lỗi thiết kế thường gặp

### 11.1. Viết factory chỉ để thêm một phương thức

Một thao tác như `summarizeRevenue` không cần thay quá trình tạo mọi repository. Đưa nó vào factory khiến hạ tầng phụ thuộc chi tiết nghiệp vụ và làm phạm vi thay đổi lớn hơn hợp đồng cần thêm.

### 11.2. Viết factory chỉ để thay một base class cố định

Nếu cấu hình module đã cung cấp `repositoryBaseClass`, hãy dùng điểm mở rộng đó khi phù hợp.

Một factory mới chỉ trả về cùng một base class cố định có thể đang lặp lại cơ chế cấu hình đã có.

### 11.3. Thay factory của store bằng code lắp ráp thiếu thành phần

Factory của module phối hợp nhiều phần như metadata, query strategy, composition và các cấu hình tích hợp.

Một implementation tự tạo target rồi dựng proxy sơ sài có thể chạy được vài phương thức nhưng làm mất các khả năng khác của repository.

Ưu tiên giữ lại implementation của store và mở rộng một hook có trách nhiệm rõ.

### 11.4. Chọn phương thức bằng tên quá đơn giản

Một interceptor hoặc cơ chế dispatch không nên chỉ kiểm tra:

~~~text
methodName == "save"
~~~

rồi giả định đã nhận diện đúng mọi chữ ký, generic type, overload hoặc đường gọi.

Metadata và method mapping của framework tồn tại để xử lý những khác biệt này. Nếu viết cơ chế hạ tầng tùy chỉnh, phải xác nhận phương thức thực sự được ánh xạ tới đâu.

### 11.5. Nghĩ rằng custom base class bao phủ mọi query

Các phương thức được suy từ tên hoặc được khai báo query có đường thực thi riêng. Chúng không tự đi qua một phương thức bạn vừa override trong base class.

Tương tự, một fragment có thể ảnh hưởng ưu tiên dispatch. Cần quan sát từng nhóm phương thức khi đánh giá phạm vi thay đổi.

### 11.6. Tự tạo repository mới trong mỗi lời gọi service

Khởi tạo factory và repository thủ công ở tầng service có thể bỏ qua những cấu hình container mà ứng dụng đang dựa vào.

Trong ứng dụng Spring Data thông thường, đăng ký repository theo cơ chế cấu hình của module rồi inject repository đã được tạo. Việc tạo thủ công thuộc những ngữ cảnh hạ tầng riêng và cần hợp đồng đầy đủ về các thành phần hỗ trợ.

### 11.7. Đo được thời gian rồi kết luận về truy vấn

Một interceptor ở proxy đo invocation. Nếu query trả về đối tượng đọc lười hoặc stream, công việc thực tế có thể tiếp tục sau thời điểm đó.

Muốn đo SQL, cursor hoặc thời gian giao dịch phải quan sát đúng lớp tương ứng. Factory hook không tự cung cấp các bằng chứng đó.

## 12. Kiểm chứng thay đổi ở tầng factory

Một thay đổi factory cần kiểm tra nhiều đường thực thi hơn một phương thức fragment.

Ví dụ tập tình huống tích hợp:

| Nhóm | Điều cần xác nhận |
|---|---|
| Khởi tạo | Repository được tạo với đúng factory bean và store component |
| CRUD | Các thao tác kế thừa vẫn đi tới implementation đúng |
| Derived query | Phương thức suy từ tên vẫn được giải quyết đúng |
| Query được khai báo | Cơ chế tạo và thực thi query vẫn hoạt động |
| Fragment | Phương thức custom vẫn được phát hiện và dispatch đúng |
| Default method | Đường gọi được hỗ trợ vẫn hoạt động theo hợp đồng |
| Generic base interface | Domain type và ID type được xác định đúng |
| Giao dịch | Ranh giới, ngoại lệ và advice không bị thay đổi ngoài ý định |
| Kiểu kết quả đặc biệt | Projection, page hoặc stream vẫn giữ hợp đồng tương ứng |
| Phạm vi cấu hình | Repository ngoài vùng áp dụng giữ đúng cấu hình riêng |

Không cần mọi ứng dụng có tất cả các nhóm trên. Chọn những nhóm mà cấu hình thực tế đang sử dụng.

Với ví dụ interceptor thời gian, cần xác nhận thêm:

- Kết quả trả về không bị đổi.
- Ngoại lệ gốc vẫn được truyền ra.
- Không đăng ký trùng interceptor.
- Metadata gắn đúng interface repository.
- Log không làm bạn diễn giải sai phạm vi thời gian được đo.
- Stream vẫn có cơ chế đóng tài nguyên ở đường tiêu thụ.

### 12.1. Khởi tạo thành công chưa chứng minh đủ

Một số lỗi xảy ra khi repository được tạo; một số chỉ xuất hiện khi gọi phương thức cụ thể, tùy chế độ bootstrap và cách tạo query.

Vì vậy, kiểm tra “Spring context đã lên” chưa đủ để kết luận mọi đường dispatch đều đúng. Cần gọi những loại phương thức mà thay đổi có thể ảnh hưởng.

### 12.2. Giữ kiểm tra theo hợp đồng thay vì phụ thuộc cấu trúc nội bộ

Nên xác nhận kết quả, ngoại lệ, dispatch và giao dịch quan sát được.

Nếu kiểm tra chỉ dựa trên tên lớp proxy hoặc một thứ tự nội bộ không thuộc hợp đồng, nó có thể dễ vỡ khi nâng phiên bản mà không phản ánh lỗi chức năng thực sự.

Khi một hook yêu cầu thứ tự cụ thể với advice khác, hãy ghi rõ đó là một yêu cầu của integration và xác nhận bằng hành vi tương ứng.

## 13. Chẩn đoán sự cố theo đúng tầng

| Hiện tượng | Nơi cần kiểm tra trước |
|---|---|
| Không gọi được phương thức mới khi biên dịch | Interface công khai đã khai báo/kế thừa phương thức chưa |
| Fragment không được dùng | Interface ghép, tên implementation và package discovery |
| Base class mới không có hiệu lực | Phạm vi cấu hình và thuộc tính `repositoryBaseClass` |
| Không tạo được base implementation | Constructor mà factory store cần có tương thích không |
| Factory bean tùy chỉnh không khởi tạo được | Constructor nhận interface repository và cấu hình đăng ký |
| Một repository bị đăng ký nhiều lần | Vùng scan chồng lấn |
| CRUD chạy nhưng query method lỗi | Query lookup, metadata và phần cấu hình module được giữ lại |
| Metadata domain/ID sai | Generic interface, resolver và cách code tùy chỉnh đọc metadata |
| Advice không bao phủ như mong muốn | Vị trí hook, thứ tự interceptor và đường dispatch |
| Một store khác bị ảnh hưởng ngoài ý định | Phân tách cấu hình module và phạm vi scan |

Bắt đầu ở tầng phù hợp giúp tránh sửa query nghiệp vụ trong khi lỗi thực tế nằm ở cơ chế tạo repository.

## 14. Bài thực hành lựa chọn điểm mở rộng

Với mỗi yêu cầu, chọn phương án nhỏ nhất đáp ứng đầy đủ và giải thích phạm vi ảnh hưởng:

1. Thêm báo cáo doanh thu chỉ cho Customer.
2. Bổ sung `refresh` cho một nhóm repository JPA.
3. Thêm thông tin repository interface vào một interceptor được cài khi tạo proxy.
4. Dùng hai base implementation tùy annotation trên từng repository.
5. Bổ sung một derived query tìm theo email.
6. Thay cơ chế tạo query method để tích hợp một ngôn ngữ truy vấn riêng.
7. Bật auditing theo khả năng chuẩn của module.
8. Đọc tenant hiện tại cho mỗi lời gọi dữ liệu.

Gợi ý phân tích:

- Yêu cầu 1 thường thuộc fragment.
- Yêu cầu 2 có thể dùng base repository hoặc fragment tái sử dụng theo thiết kế.
- Yêu cầu 3 có thể dùng proxy hook nếu đó là hợp đồng integration; logging thông thường có thể có cách cấu hình đơn giản hơn.
- Yêu cầu 4 cần xem cấu hình có tách được không, rồi mới cân nhắc factory theo metadata.
- Yêu cầu 5 thuộc hợp đồng query method.
- Yêu cầu 6 có thể thật sự cần SPI/factory.
- Yêu cầu 7 nên bắt đầu từ cơ chế auditing của store.
- Yêu cầu 8 là ngữ cảnh runtime; không chụp một giá trị tại startup rồi dùng như ngữ cảnh mọi request.

Lập bảng quyết định cho một tình huống của ứng dụng:

| Câu hỏi | Câu trả lời |
|---|---|
| Hợp đồng cần thêm hoặc thay đổi là gì? | Ghi hành vi cụ thể |
| Repository nào bị ảnh hưởng? | Một, một nhóm hay toàn bộ vùng cấu hình |
| Fragment có diễn đạt đủ không? | Có/Không và lý do |
| Base class hoặc cấu hình sẵn có có đủ không? | Có/Không và lý do |
| Metadata/hook nào thật sự cần? | Ghi chính xác trách nhiệm |
| Đường thực thi nào phải kiểm chứng? | CRUD, query, fragment, giao dịch... |
| Phụ thuộc module/phiên bản nào? | Ghi cấu hình thực tế |

Chọn đúng điểm mở rộng giữ logic ở nơi có trách nhiệm rõ: fragment cho thao tác cụ thể, base repository cho implementation dùng chung và factory cho cơ chế tạo repository. Chỉ tăng mức tùy chỉnh khi yêu cầu thực sự vượt khả năng của tầng hiện tại.
