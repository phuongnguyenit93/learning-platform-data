# RepositoryFactoryBeanSupport và tích hợp FactoryBean của Spring

## 1. Bài toán: vì sao một interface trở thành bean dùng được?

Trong chương **Factory và metadata** của module **SPRING_DATA_COMMONS**, điểm cần hiểu là cách Spring Data nối định nghĩa repository với vòng đời bean của Spring. Ứng dụng thường chỉ khai báo một interface, rồi inject interface đó vào service. Để lời gọi như `findById(...)` hoặc `findByEmail(...)` hoạt động, hạ tầng phải xác định kiểu domain, chọn implementation nền, ghép các fragment và tạo proxy.

Xét khai báo sau:

~~~java
package example.customer;

import java.util.Optional;
import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository extends CrudRepository<Customer, Long> {
    Optional<Customer> findByEmail(String email);
}
~~~

Giả sử `Customer` là kiểu domain đã được ánh xạ hợp lệ cho kho dữ liệu đang dùng. Interface trên không có constructor để Spring gọi và cũng không chứa implementation Java cho `findByEmail`. Một bean thông thường được tạo bằng cách khởi tạo lớp sẽ chưa giải quyết được bài toán này.

`RepositoryFactoryBeanSupport` là lớp nền giúp hạ tầng repository tham gia cơ chế `FactoryBean` của Spring. Nó tiếp nhận cấu hình, tạo một `RepositoryFactorySupport` phù hợp và cung cấp repository proxy dưới tên bean của repository.

Sau bài học, người đọc cần làm được bốn việc:

- Phân biệt container Spring, factory bean, repository factory và repository proxy.
- Giải thích quá trình khởi tạo, khả năng nhận diện kiểu và ảnh hưởng của lazy initialization.
- Chọn đúng điểm mở rộng khi cần thay đổi cách tạo repository.
- Đọc metadata để chẩn đoán cấu hình mà vẫn tôn trọng giới hạn của từng datastore.

Phần cơ chế chung thuộc Spring Data Commons. Ví dụ tích hợp cụ thể dùng Spring Data JPA để thấy một store triển khai cầu nối này ra sao. Những đoạn dùng `EntityManager` cần module JPA; chỉ thêm `spring-data-commons` chưa đủ để chạy chúng. Các tên API trong ví dụ được đối chiếu với dòng Spring Data 3.4; khi dùng dòng khác, cần đối chiếu chữ ký tương ứng.

## 2. Bốn đối tượng cần phân biệt

| Thành phần | Trách nhiệm | Ví dụ |
|---|---|---|
| `BeanFactory` hoặc `ApplicationContext` | Quản lý định nghĩa bean, dependency và vòng đời | Container của ứng dụng |
| `RepositoryFactoryBeanSupport` và lớp con | Thích nghi việc tạo repository với hợp đồng bean của Spring | `JpaRepositoryFactoryBean` |
| `RepositoryFactorySupport` và lớp con | Xử lý metadata, implementation, fragment và tạo proxy | `JpaRepositoryFactory` |
| Repository proxy | Đối tượng mà service gọi thông qua repository interface | Một đối tượng triển khai `CustomerRepository` |

Tên `FactoryBean` và `BeanFactory` dễ gây nhầm lẫn:

- `BeanFactory` là container có thể lấy và quản lý nhiều bean.
- `FactoryBean<T>` là hợp đồng cho một bean hạ tầng cung cấp sản phẩm kiểu `T`.
- Một phương thức `@Bean` là cách đăng ký bean. Nó không tự biến kiểu trả về thành `FactoryBean`.

Nếu một phương thức `@Bean` trả về đối tượng triển khai `FactoryBean`, container vẫn áp dụng ngữ nghĩa đặc biệt của `FactoryBean` cho bean đó.

Sơ đồ trách nhiệm:

~~~mermaid
flowchart TD
    A["ApplicationContext"] --> B["Factory bean của CustomerRepository"]
    B --> C["Repository factory cho datastore"]
    C --> D["Metadata + implementation nền + fragments"]
    D --> E["Repository proxy: CustomerRepository"]
    A -->|"inject sản phẩm"| F["CustomerService"]
    F -->|"gọi phương thức"| E
~~~

Trong sơ đồ, factory bean không phải đối tượng mà tầng nghiệp vụ cần gọi để thực hiện CRUD. Tầng nghiệp vụ làm việc với sản phẩm của nó.

## 3. Hợp đồng FactoryBean: sản phẩm, kiểu và singleton

`FactoryBean<T>` có ba phương thức cốt lõi:

| Phương thức | Ý nghĩa |
|---|---|
| `getObject()` | Trả về sản phẩm do factory cung cấp |
| `getObjectType()` | Báo kiểu sản phẩm để container nhận diện bean theo kiểu |
| `isSingleton()` | Báo sản phẩm có được chia sẻ dưới một tham chiếu singleton hay không |

Hợp đồng này giúp Spring đăng ký một thành phần tạo đối tượng phức tạp nhưng vẫn cho phép consumer nhận đối tượng được tạo qua dependency injection. Xem [cơ chế FactoryBean trong Spring Framework](https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html).

### 3.1. Cùng tên bean, hai cách truy cập

Giả sử tên bean được đăng ký là `customerRepository`:

~~~java
CustomerRepository repository =
        context.getBean("customerRepository", CustomerRepository.class);

Object factoryBean =
        context.getBean("&customerRepository");
~~~

Lệnh đầu lấy sản phẩm repository. Lệnh thứ hai lấy chính factory bean. Ký tự `&` là tiền tố yêu cầu container trả về factory thay vì sản phẩm; nó không phải ký tự cần thêm vào tên bean khi đăng ký.

Có thể kiểm tra vai trò bằng đoạn chẩn đoán sau trong một context đã khởi tạo:

~~~java
import org.springframework.beans.factory.FactoryBean;

Object product = context.getBean("customerRepository");
Object creator = context.getBean("&customerRepository");

System.out.println(product instanceof CustomerRepository); // true
System.out.println(creator instanceof FactoryBean<?>);     // true
System.out.println(product == creator);                    // false
~~~

Tên mặc định có thể thay đổi khi cấu hình naming strategy. Khi sử dụng ví dụ, cần thay bằng tên thực tế trong ứng dụng.

### 3.2. getObjectType không phải getClass của proxy

Đối với `RepositoryFactoryBeanSupport`, kiểu sản phẩm được nhận diện bằng repository interface truyền vào constructor. Ví dụ, kiểu được công bố là `CustomerRepository.class`, còn lớp runtime của sản phẩm có thể là một lớp proxy.

Vì vậy:

~~~java
Class<?> advertisedType = context.getType("customerRepository");

System.out.println(
        advertisedType != null
                && CustomerRepository.class.isAssignableFrom(advertisedType)
);
~~~

Việc nhận diện bean theo kiểu không nên yêu cầu chạy query hay gọi một phương thức nghiệp vụ. Khi viết factory hạ tầng, tránh tạo sản phẩm trong `getObjectType()` chỉ để lấy `getClass()`. Spring có thể hỏi kiểu từ sớm, trước khi factory hoàn tất các callback khởi tạo. Hợp đồng kiểu và khả năng gọi sớm được mô tả trong [Javadoc FactoryBean](https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/beans/factory/FactoryBean.html).

### 3.3. Singleton proxy không có nghĩa là singleton dữ liệu

`RepositoryFactoryBeanSupport` công bố sản phẩm singleton. Hai lần lấy cùng repository trong cùng context thông thường nhận cùng tham chiếu:

~~~java
CustomerRepository first =
        context.getBean("customerRepository", CustomerRepository.class);
CustomerRepository second =
        context.getBean("customerRepository", CustomerRepository.class);

System.out.println(first == second); // true
~~~

Điều đó không có nghĩa là entity được tải chỉ tồn tại một bản trong toàn ứng dụng, các kết quả query luôn được cache, hay mọi request dùng cùng một transaction.

Phạm vi bean của factory và tính singleton của sản phẩm là hai khái niệm riêng. Ngoài ra, custom fragment có trạng thái thay đổi dùng chung vẫn phải được thiết kế phù hợp khi nhiều luồng cùng gọi repository.

## 4. Hình dạng của RepositoryFactoryBeanSupport

Lớp nền có ba tham số generic:

~~~java
RepositoryFactoryBeanSupport<T extends Repository<S, ID>, S, ID>
~~~

| Tham số | Đại diện cho | Với ví dụ Customer |
|---|---|---|
| `T` | Kiểu repository interface | `CustomerRepository` |
| `S` | Kiểu entity/domain | `Customer` |
| `ID` | Kiểu định danh | `Long` |

Các điểm móc quan trọng gồm:

- Constructor nhận `Class<? extends T>` của repository.
- `createRepositoryFactory()` được lớp con triển khai để cung cấp factory cho store.
- `afterPropertiesSet()` chuẩn bị hạ tầng sau khi Spring đã cấp cấu hình.
- Các setter tiếp nhận lựa chọn về base class, fragments, query lookup và lazy initialization.
- Nhóm phương thức metadata cung cấp thông tin repository và domain.

Đây là lớp abstract, nên ứng dụng không thể đăng ký nó như một factory hoàn chỉnh rồi mong tự có khả năng truy cập một cơ sở dữ liệu. Với lớp con generic, cần giữ thứ tự repository, domain, identifier như hợp đồng lớp nền; đảo thứ tự có thể làm suy luận kiểu sai. Xem [Javadoc RepositoryFactoryBeanSupport](https://docs.spring.io/spring-data/commons/docs/3.4.x/api/org/springframework/data/repository/core/support/RepositoryFactoryBeanSupport.html).

Một hình dung hữu ích là: `Class<CustomerRepository>` trả lời “cần tạo sản phẩm theo hợp đồng nào”, còn `RepositoryFactorySupport` trả lời “dùng cơ chế nào để tạo sản phẩm đó cho store này”.

## 5. Vòng đời từ đăng ký đến inject

### 5.1. Đăng ký định nghĩa

Cơ chế bật repository của một store tìm các interface phù hợp trong phạm vi cấu hình, rồi đăng ký định nghĩa cho factory bean tương ứng. Với JPA, `@EnableJpaRepositories` là một điểm cấu hình phổ biến.

Đây là quá trình quét repository của Spring Data. Việc thêm `@Repository` vào một interface rồi chỉ chạy component scan thông thường chưa thay thế được cấu hình hạ tầng repository cho store.

### 5.2. Spring khởi tạo factory bean

Container tạo factory bean với repository interface, cung cấp dependency và gọi các callback liên quan. Lớp nền tham gia các hợp đồng như `BeanFactoryAware`, `BeanClassLoaderAware`, `EnvironmentAware`, `ApplicationEventPublisherAware` và `InitializingBean`.

Ý nghĩa thực tế:

- Factory có thể truy cập các thành phần hạ tầng của container.
- Proxy cần được tạo với class loader phù hợp.
- Cấu hình môi trường và việc phát sự kiện có thể được chuyển cho cơ chế repository.
- Việc chuẩn bị repository được đặt vào vòng đời khởi tạo thay vì constructor.

Constructor nên xác lập thông tin tối thiểu. Tạo repository hoặc thực thi query ngay trong constructor dễ gặp dependency chưa sẵn sàng.

### 5.3. Chuẩn bị repository factory và sản phẩm

Trong dòng triển khai được tham chiếu, `afterPropertiesSet()` thực hiện các nhóm việc sau:

1. Tạo repository factory cho store.
2. Chuyển cấu hình, ngữ cảnh Spring và các lựa chọn repository cho factory.
3. Áp dụng các customizer trước khi tạo repository.
4. Chuẩn bị metadata và tổ hợp fragment.
5. Chuẩn bị bộ giữ sản phẩm có khả năng tạo trì hoãn.
6. Khởi tạo proxy ngay nếu không bật lazy cho repository.

Khi có mapping context, kiểu domain còn được đưa vào quá trình nhận diện mapping. Đây là phần chuẩn bị metadata; cơ chế auditing đầy đủ vẫn cần cấu hình tương ứng của store.

Sơ đồ vòng đời rút gọn:

~~~mermaid
sequenceDiagram
    participant C as Spring container
    participant B as Repository factory bean
    participant F as Repository factory
    participant S as Service
    C->>B: Constructor(repositoryInterface)
    C->>B: Cấp cấu hình và callback Aware
    C->>B: afterPropertiesSet()
    B->>F: Tạo và cấu hình factory
    B->>F: Chuẩn bị metadata và fragments
    opt Khởi tạo proxy ngay
        B->>F: getRepository(...)
        F-->>B: Repository proxy
    end
    C->>B: getObject()
    opt Proxy còn chưa được tạo
        B->>F: getRepository(...)
        F-->>B: Repository proxy
    end
    B-->>C: Sản phẩm repository
    C-->>S: Inject repository
~~~

Sơ đồ bỏ qua nhiều chi tiết hậu xử lý bean để tập trung vào trách nhiệm của cầu nối. Cơ chế bộ giữ lazy, customizer và việc chuẩn bị mapping được thể hiện trong [mã nguồn RepositoryFactoryBeanSupport dòng 3.4](https://raw.githubusercontent.com/spring-projects/spring-data-commons/3.4.x/src/main/java/org/springframework/data/repository/core/support/RepositoryFactoryBeanSupport.java).

### 5.4. Tạo bằng new không thực hiện toàn bộ vòng đời

Đoạn sau không tương đương lấy repository từ Spring:

~~~java
var factoryBean =
        new JpaRepositoryFactoryBean<CustomerRepository, Customer, Long>(
                CustomerRepository.class
        );

// Chưa cung cấp hạ tầng và chưa chạy đầy đủ vòng đời.
// Không gọi factoryBean.getObject() ở đây.
~~~

Nếu factory được Spring quản lý, không gọi thủ công `afterPropertiesSet()` thêm lần nữa. Nếu tự quản lý factory ở mức hạ tầng, người viết phải tự chịu trách nhiệm cung cấp dependency và thứ tự khởi tạo; việc đó nằm ngoài cách dùng thông thường của tầng nghiệp vụ.


## 6. Lazy initialization: cần hỏi đang trì hoãn tầng nào

Lazy initialization có thể xuất hiện ở nhiều tầng:

| Tầng | Đối tượng hoặc công việc được trì hoãn |
|---|---|
| Định nghĩa bean của Spring | Việc khởi tạo bean theo chính sách container |
| Dependency được inject qua lazy proxy | Việc giải quyết dependency đích đến khi cần sử dụng |
| `setLazyInit(true)` của repository factory bean | Việc tạo repository proxy bên trong factory bean |
| Bootstrap mode của store | Cách hạ tầng store phối hợp khởi tạo repository trong quá trình bootstrap |

`setLazyInit(true)` không có nghĩa là factory bean không chạy `afterPropertiesSet()`. Nó cũng không có nghĩa là metadata và dependency của store đều được bỏ qua lúc khởi động.

Một tình huống dễ hiểu sai:

1. Factory bean được cấu hình tạo repository proxy theo kiểu lazy.
2. Một service singleton vẫn được tạo ngay.
3. Container cần sản phẩm repository để inject vào constructor service.
4. Container gọi `getObject()`, khiến proxy được tạo ngay tại bước đó.

Do đó, muốn giải thích thời điểm khởi tạo, phải xem cả cấu hình repository và cách dependency được yêu cầu. Không suy ra từ riêng một setter rằng proxy chỉ được tạo vào lần chạy query đầu tiên.

Với JPA, `bootstrapMode` còn là lựa chọn trên `@EnableJpaRepositories`. Nó cần được xem trong cấu hình khởi động của store; không nên đánh đồng với việc tự gọi một setter lazy. Các tùy chọn đăng ký này được liệt kê trong [Javadoc EnableJpaRepositories](https://docs.spring.io/spring-data/jpa/docs/3.4.x/api/org/springframework/data/jpa/repository/config/EnableJpaRepositories.html).

### 6.1. Lazy thay đổi thời điểm thấy lỗi

Giả sử có phương thức:

~~~java
Optional<Customer> findByEmali(String email);
~~~

Nếu `Customer` chỉ có thuộc tính `email`, phần `Emali` không mô tả được thuộc tính mong muốn. Khi store phân tích query được suy ra từ tên, lỗi có thể xuất hiện lúc tạo repository, hoặc muộn hơn nếu phần tạo repository/query bị trì hoãn theo cấu hình cụ thể.

Không phải mọi lỗi truy vấn đều được phát hiện ở bước tạo proxy. Ví dụ, quyền truy cập bảng hoặc lỗi kết nối có thể chỉ xuất hiện khi thao tác thật với database.

Một ứng dụng có repository lazy có thể hoàn tất bootstrap mà chưa chứng minh được mọi query đều hợp lệ và mọi nguồn dữ liệu đều truy cập được. Khi quyết định chính sách khởi tạo, cần cân nhắc giữa thời gian bootstrap, thời điểm phát hiện lỗi và độ trễ của lần sử dụng đầu.

## 7. Các nhóm cấu hình đi qua factory bean

Bảng sau giúp xác định cấu hình nào thuộc quá trình tạo repository:

| Điểm cấu hình | Mục đích | Câu hỏi cần trả lời trước khi dùng |
|---|---|---|
| `setRepositoryBaseClass(...)` | Chọn implementation nền cho repository | Store có thể khởi tạo lớp này bằng constructor nào? |
| `setRepositoryFragments(...)` | Cung cấp tổ hợp implementation bổ sung | Những phương thức nào do fragment chịu trách nhiệm? |
| `setQueryLookupStrategyKey(...)` | Chọn chính sách tìm hoặc tạo query | Store hỗ trợ chính sách đó đến đâu? |
| `setNamedQueries(...)` | Cung cấp nguồn query có tên | Tên và cú pháp có đúng quy ước store không? |
| `addRepositoryFactoryCustomizer(...)` | Cấu hình repository factory trước lúc tạo sản phẩm | Có thể giải quyết yêu cầu bằng customizer thay vì viết lại factory không? |
| `setLazyInit(...)` | Chọn việc tạo proxy ngay hoặc trì hoãn bên trong factory bean | Consumer có yêu cầu sản phẩm ngay khi bootstrap không? |

Đây là các điểm tiếp nhận của hạ tầng. Trong ứng dụng thông thường, người dùng thường cấu hình qua annotation hoặc cơ chế của store thay vì lấy factory bean ra rồi gọi setter sau khi context đã chạy.

### 7.1. Cấu hình phải đến trước khi sản phẩm được tạo

Ví dụ sau minh họa một cách tiếp cận không phù hợp:

~~~java
var creator = context.getBean(
        "&customerRepository",
        RepositoryFactoryBeanSupport.class
);

// Sản phẩm có thể đã được tạo và cache trước thời điểm này.
creator.setRepositoryBaseClass(MyCustomerRepositoryBase.class);
~~~

Dòng setter không phải cơ chế dựng lại proxy hiện có. Thay đổi trường cấu hình sau khi quá trình tạo sản phẩm đã hoàn tất không bảo đảm consumer nhận hành vi mới.

Khi cần cấu hình dùng chung, nên đưa nó vào giai đoạn đăng ký hoặc khởi tạo factory bean. Với cấu hình JPA, chọn `repositoryBaseClass` hoặc `repositoryFactoryBeanClass` ngay trên `@EnableJpaRepositories` thường làm ý định rõ hơn.

### 7.2. Chọn tầng mở rộng theo yêu cầu

| Yêu cầu | Điểm mở rộng nên xem xét trước |
|---|---|
| Thêm thao tác tìm kiếm đặc thù cho một nhóm repository | Repository fragment |
| Thay hành vi implementation CRUD nền dùng chung | Repository base class tương thích store |
| Thêm advice cho các proxy được tạo | Repository factory customizer và proxy post-processor |
| Cần cách tạo factory hoặc cấp dependency riêng cho hạ tầng repository | Factory bean của store |
| Triển khai hỗ trợ cho một loại kho dữ liệu mới | Repository factory và hệ thống mapping/query của store mới |

Không nên viết lại toàn bộ factory bean chỉ để thêm một phương thức nghiệp vụ. Ngược lại, nếu cần thay cách dựng factory và cung cấp thành phần hạ tầng, fragment đơn lẻ không giải quyết được toàn bộ yêu cầu.

## 8. Metadata: lấy từ factory thay vì đoán qua tên lớp proxy

`RepositoryFactoryBeanSupport` còn đóng vai trò `RepositoryFactoryInformation<S, ID>`. Điều này cho phép thành phần hạ tầng truy cập thông tin về repository và entity. Những nhóm chính gồm:

| API | Loại thông tin |
|---|---|
| `getRepositoryInformation()` | Repository interface, domain, ID và thông tin liên quan implementation |
| `getEntityInformation()` | Cách hạ tầng nhận diện entity và định danh |
| `getPersistentEntity()` | Metadata mapping của domain thông qua mapping context |
| `getQueryMethods()` | Những query method mà repository factory ghi nhận |

Các nhóm này được định nghĩa trong [hợp đồng RepositoryFactoryInformation](https://docs.spring.io/spring-data/commons/docs/3.4.x/api/org/springframework/data/repository/core/support/RepositoryFactoryInformation.html).

### 8.1. Đọc metadata sau khi context đã sẵn sàng

Đoạn chẩn đoán dưới đây chạy trong ứng dụng đã bật repository và biết đúng tên bean:

~~~java
import org.springframework.context.ApplicationContext;
import org.springframework.data.repository.core.RepositoryInformation;
import org.springframework.data.repository.core.support.RepositoryFactoryInformation;

public final class RepositoryDiagnostics {

    private RepositoryDiagnostics() {
    }

    public static void describe(
            ApplicationContext context,
            String repositoryBeanName
    ) {
        Object creator = context.getBean("&" + repositoryBeanName);

        if (!(creator instanceof RepositoryFactoryInformation<?, ?> info)) {
            throw new IllegalArgumentException(
                    "Bean không cung cấp metadata repository: "
                            + repositoryBeanName
            );
        }

        RepositoryInformation repository = info.getRepositoryInformation();

        System.out.println(
                "Repository: " + repository.getRepositoryInterface().getName()
        );
        System.out.println(
                "Domain: " + repository.getDomainType().getName()
        );
        System.out.println(
                "ID: " + repository.getIdType().getName()
        );
    }
}
~~~

Ví dụ gọi:

~~~java
RepositoryDiagnostics.describe(context, "customerRepository");
~~~

Kết quả dự kiến với ví dụ đã nêu:

~~~text
Repository: example.customer.CustomerRepository
Domain: example.customer.Customer
ID: java.lang.Long
~~~

Đoạn mã dùng pattern matching cho `instanceof`, phù hợp với Java 17 trở lên. Việc kiểm tra qua interface metadata giúp công cụ chẩn đoán bớt phụ thuộc vào một factory bean cụ thể.

### 8.2. Những giới hạn cần hiểu

**Mapping metadata có điều kiện.** Không giả định mọi cấu hình đều có `MappingContext`. Với lớp nền được tham chiếu, gọi `getPersistentEntity()` khi không có context có thể thất bại. Một công cụ hỗ trợ nhiều store cần biết khả năng của từng cấu hình trước khi dùng API này.

**Query metadata phụ thuộc giai đoạn khởi tạo.** Nếu proxy/query chưa được dựng do lazy initialization, danh sách do factory ghi nhận có thể chưa phản ánh trạng thái sau khởi tạo đầy đủ. Không dùng một lần đọc danh sách rỗng ở giai đoạn sớm để kết luận repository không có query method.

**Metadata cấu trúc khác metadata của lời gọi hiện tại.** Thông tin như domain type có thể đọc phục vụ chẩn đoán. Còn việc expose ngữ cảnh của phương thức repository đang chạy là một cơ chế riêng, có thể cần cấu hình và có chi phí interception. Không bật nó cho toàn bộ ứng dụng chỉ để in kiểu domain khi khởi động.

**Metadata không cấp thêm khả năng cho store.** Biết kiểu domain, query method hoặc tham số trả về không đồng nghĩa mọi store đều hỗ trợ cùng projection, query-by-example, phân trang hay kiểu truy vấn.

Cũng không nên dùng tên lớp runtime như `$Proxy...` làm khóa định danh nghiệp vụ hoặc cơ chế xác định domain. Tên ấy phản ánh cách proxy được tạo và có thể thay đổi theo môi trường.

## 9. Tích hợp cụ thể với JPA

### 9.1. Chuỗi kế thừa bổ sung khả năng của store

Trong ví dụ JPA, chuỗi lớp liên quan là:

~~~text
RepositoryFactoryBeanSupport
        ↓
TransactionalRepositoryFactoryBeanSupport
        ↓
JpaRepositoryFactoryBean
~~~

`TransactionalRepositoryFactoryBeanSupport` bổ sung bước cấu hình transaction cho proxy. Trong lớp này, `createRepositoryFactory()` là phương thức `final`, điều phối lời gọi `doCreateRepositoryFactory()` và áp dụng phần hạ tầng transaction.

Điều đó ảnh hưởng trực tiếp đến cách mở rộng: không cố override `createRepositoryFactory()` không tham số khi đang kế thừa chuỗi này. Hãy chọn hook phù hợp của lớp store. Xem [Javadoc TransactionalRepositoryFactoryBeanSupport](https://docs.spring.io/spring-data/commons/docs/3.4.x/api/org/springframework/data/repository/core/support/TransactionalRepositoryFactoryBeanSupport.html).

Với `JpaRepositoryFactoryBean`, `EntityManager` là dependency của store. Lớp cung cấp hook `createRepositoryFactory(EntityManager)` để tạo repository factory JPA. Phương thức này khác với `createRepositoryFactory()` không tham số của lớp nền. Xem [Javadoc JpaRepositoryFactoryBean](https://docs.spring.io/spring-data/jpa/docs/3.4.x/api/org/springframework/data/jpa/repository/support/JpaRepositoryFactoryBean.html).

Việc kế thừa `RepositoryFactoryBeanSupport` trực tiếp rồi trả về một factory tùy ý chưa tự mang theo toàn bộ cách tích hợp transaction, mapping và truy vấn của JPA.

### 9.2. Ví dụ: thêm ghi nhận thời gian qua custom factory bean

Giả sử cần quan sát thời gian xử lý các lời gọi repository JPA trong một phạm vi quét xác định. Có thể kế thừa factory bean JPA, rồi đăng ký customizer để thêm advice cho proxy.

Mã này là ví dụ mở rộng hạ tầng, không phải phép đo riêng thời gian thực thi SQL. Khoảng thời gian đo bao quanh lời gọi mà advice quan sát được.

~~~java
package example.infrastructure;

import java.util.logging.Level;
import java.util.logging.Logger;

import org.aopalliance.intercept.MethodInterceptor;
import org.springframework.data.jpa.repository.support.JpaRepositoryFactoryBean;
import org.springframework.data.repository.Repository;

public class ObservedJpaRepositoryFactoryBean<
        T extends Repository<S, ID>, S, ID>
        extends JpaRepositoryFactoryBean<T, S, ID> {

    private static final Logger LOGGER =
            Logger.getLogger(ObservedJpaRepositoryFactoryBean.class.getName());

    public ObservedJpaRepositoryFactoryBean(
            Class<? extends T> repositoryInterface
    ) {
        super(repositoryInterface);

        addRepositoryFactoryCustomizer(factory ->
                factory.addRepositoryProxyPostProcessor(
                        (proxyFactory, repositoryInformation) ->
                                proxyFactory.addAdvice(
                                        (MethodInterceptor) invocation -> {
                                            long started = System.nanoTime();

                                            try {
                                                return invocation.proceed();
                                            } finally {
                                                long elapsed =
                                                        System.nanoTime() - started;

                                                LOGGER.log(
                                                        Level.FINE,
                                                        "repository={0}, method={1}, elapsedNs={2}",
                                                        new Object[] {
                                                            repositoryInformation
                                                                    .getRepositoryInterface()
                                                                    .getSimpleName(),
                                                            invocation.getMethod()
                                                                    .getName(),
                                                            elapsed
                                                        }
                                                );
                                            }
                                        }
                                )
                )
        );
    }
}
~~~

Điểm đáng chú ý trong ví dụ:

- Constructor giữ nguyên hợp đồng nhận repository interface.
- Thứ tự generic vẫn là repository, domain, ID.
- Customizer được đăng ký trước vòng đời tạo sản phẩm.
- Advice luôn gọi `invocation.proceed()` và giữ nguyên kết quả hoặc ngoại lệ.
- Biến thời gian nằm trong từng lời gọi; không dùng một trường thay đổi chung giữa các luồng.
- Ví dụ ghi tên repository, phương thức và thời lượng; không cần ghi đối số nghiệp vụ.

Để nhìn thấy bản ghi mức `FINE`, ứng dụng phải cấu hình logger và handler tương ứng. Khi repository có phương thức reactive, đo quanh `proceed()` thường chỉ đo thời gian tạo publisher; muốn đo thời gian thực hiện và hoàn tất cần công cụ quan sát ở vòng đời subscription. Vì vậy không chuyển nguyên ví dụ này thành phép đo thời gian truy vấn reactive.


### 9.3. Đăng ký factory bean cho đúng phạm vi repository

Trong một ứng dụng JPA đã có `EntityManagerFactory` và transaction manager hợp lệ:

~~~java
package example.configuration;

import example.customer.CustomerRepository;
import example.infrastructure.ObservedJpaRepositoryFactoryBean;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;

@Configuration
@EnableJpaRepositories(
        basePackageClasses = CustomerRepository.class,
        repositoryFactoryBeanClass = ObservedJpaRepositoryFactoryBean.class
)
public class CustomerRepositoryConfiguration {
}
~~~

`basePackageClasses` dùng package chứa kiểu được chỉ định làm phạm vi quét. Cấu hình này áp dụng factory bean đã chọn cho các repository thuộc phạm vi đó, không chỉ cho riêng interface được dùng làm mốc.

Các điều kiện của ví dụ:

- Có dependency Spring Data JPA và JPA provider tương thích.
- `Customer` được đăng ký trong persistence unit tương ứng.
- Có datasource, entity manager factory và transaction manager được cấu hình.
- Cấu hình trên được đưa vào application context.
- Không có một cấu hình quét khác đồng thời đăng ký lại cùng repository.

Một entity tối thiểu để ghép với interface ở đầu bài:

~~~java
package example.customer;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;

@Entity
public class Customer {

    @Id
    @GeneratedValue
    private Long id;

    private String email;

    protected Customer() {
    }

    public Customer(String email) {
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }
}
~~~

Việc tạo schema và dữ liệu mẫu phụ thuộc cấu hình database của ứng dụng thực hành. `findByEmail` trả về `Optional<Customer>` giả định truy vấn có nhiều nhất một kết quả; nếu nghiệp vụ yêu cầu email duy nhất, cần bảo đảm ràng buộc dữ liệu tương ứng.

Service vẫn inject interface bình thường:

~~~java
package example.customer;

import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class CustomerService {

    private final CustomerRepository customers;

    public CustomerService(CustomerRepository customers) {
        this.customers = customers;
    }

    public Optional<Customer> findByEmail(String email) {
        return customers.findByEmail(email);
    }
}
~~~

Service không cần biết repository được tạo bởi factory bean tùy biến nào. Nhờ vậy, thay đổi cơ chế tạo proxy không buộc mã nghiệp vụ phụ thuộc lớp hạ tầng.

### 9.4. Vì sao ví dụ không override getObject?

Nhu cầu là thêm advice trong quá trình dựng proxy. Đăng ký customizer giải quyết trực tiếp nhu cầu đó và vẫn giữ các bước chuẩn bị sản phẩm của lớp nền.

Nếu tự override `getObject()` để tạo một repository mới mỗi lần gọi, rất dễ phá vỡ kỳ vọng singleton, bỏ qua phần ghép fragment hoặc làm sản phẩm không đồng nhất với metadata đã chuẩn bị. Khi thực sự cần thay repository factory JPA, hãy dùng hook của store và giữ các dependency cùng cấu hình mà store yêu cầu.

## 10. Ranh giới giữa Commons và từng datastore

`RepositoryFactoryBeanSupport` cung cấp một khung tích hợp chung. Khung đó không triển khai sẵn mọi thao tác lưu trữ hoặc mọi ngôn ngữ query.

| Nhu cầu trong module Commons | Vai trò của khung chung | Phần cần store thực hiện |
|---|---|---|
| CRUD | Mô hình repository và quy trình tạo proxy | Cách đọc, lưu, xóa và nhận diện entity mới |
| Derived query | Đầu mối cấu hình query lookup | Diễn giải thuộc tính và tạo truy vấn theo store |
| Phân trang, sắp xếp | Các abstraction đầu vào và đầu ra chung | Cách thực hiện truy vấn, giới hạn và count |
| Projection | Hạ tầng mô tả và tạo kết quả theo hợp đồng | Khả năng chọn dữ liệu và ánh xạ kết quả của store |
| Query by example | Hợp đồng và dữ liệu mô tả ví dụ | Những phép so khớp mà store hỗ trợ |
| Auditing | Các abstraction và mapping metadata liên quan | Cấu hình kích hoạt, callback và tích hợp lưu trữ |

Bảng mô tả ranh giới trách nhiệm, không khẳng định mọi store đều hỗ trợ đủ các hàng. Ví dụ, thay factory bean không biến một store thiếu query-by-example thành store có implementation đầy đủ cho nó. Tương tự, đưa domain vào mapping context chưa tự tạo ra các trường thời gian kiểm toán.

Trong một ứng dụng dùng nhiều store, cần đặt ranh giới quét rõ ràng, chọn interface và metadata phù hợp, rồi cấp đúng factory bean cho từng nhóm. Cùng một lớp domain hoặc cùng một tên repository không phải bằng chứng rằng hai hạ tầng có thể thay thế trực tiếp cho nhau.

Transaction cũng cần xem theo store. Sự hiện diện của cầu nối `FactoryBean` không tự bảo đảm một lệnh gọi qua nhiều nguồn dữ liệu sẽ dùng chung một transaction.

## 11. Chẩn đoán lỗi theo tầng

| Biểu hiện | Tầng cần kiểm tra trước | Hướng xử lý |
|---|---|---|
| Không inject được `CustomerRepository` | Đăng ký repository | Kiểm tra cấu hình store, package quét và repository interface |
| Lấy `&customerRepository` rồi ép thành `CustomerRepository` bị lỗi | Truy cập bean | Lấy tên không có `&` nếu cần sản phẩm |
| Factory thiếu `EntityManager` | Dependency của JPA | Kiểm tra persistence unit và cấu hình hạ tầng của store |
| Custom factory bean không được dùng | Cấu hình phạm vi quét | Kiểm tra `repositoryFactoryBeanClass` trên đúng cấu hình đăng ký |
| Override `createRepositoryFactory()` bị báo không hợp lệ | Chuỗi kế thừa | Xem phương thức `final` và hook dành cho lớp store |
| Đọc `PersistentEntity` thất bại | Mapping metadata | Xác nhận có mapping context hỗ trợ domain đang dùng |
| Sửa setter sau bootstrap nhưng hành vi không đổi | Thời điểm cấu hình | Đưa cấu hình về trước khi tạo repository proxy |
| Lỗi tên thuộc tính khi tạo query | Query và domain metadata | Đối chiếu tên phương thức với thuộc tính được ánh xạ |
| Hai bean cùng loại gây mơ hồ | Định danh và dependency injection | Kiểm tra quét trùng, tên bean và qualifier theo store |

Nên phân biệt lỗi tạo bean với lỗi thực thi query. Một thông báo bao ngoài như `BeanCreationException` chỉ cho biết khởi tạo bean thất bại; nguyên nhân sâu hơn mới cho biết đó là thiếu dependency, metadata sai hay query không tạo được.

Quy trình chẩn đoán gọn:

1. Xác nhận tên bean và xác định đang lấy sản phẩm hay factory.
2. Xác nhận factory bean thuộc đúng store và đúng phạm vi quét.
3. Đọc thông tin repository, domain và ID sau thời điểm khởi tạo phù hợp.
4. Đối chiếu lỗi gốc với dependency, mapping hoặc query.
5. Xem chính sách lazy để giải thích vì sao lỗi xuất hiện lúc bootstrap hay lúc sử dụng.

Không nên “sửa” lỗi bằng cách thêm mọi annotation hoặc đổi factory ngẫu nhiên. Ví dụ, một lỗi tên thuộc tính query cần sửa mô hình hoặc phương thức truy vấn, chứ không cần thay đổi semantics của `getObject()`.

## 12. Quan sát hành vi trong ứng dụng thực hành

Sau khi đưa ví dụ vào một ứng dụng JPA đã cấu hình, có thể quan sát trực tiếp các điểm sau:

- Lấy `customerRepository` nhận được đối tượng gán được cho `CustomerRepository`.
- Lấy `&customerRepository` nhận được `ObservedJpaRepositoryFactoryBean`.
- Hai lần lấy sản phẩm của cùng bean trong cùng context trả về cùng tham chiếu.
- `getObjectType()` của factory báo repository interface.
- Metadata mô tả đúng domain `Customer` và kiểu ID `Long`.
- Khi mức log phù hợp được bật, lời gọi repository đi qua advice đã đăng ký.

Đây là các quan sát của cơ chế tích hợp. Chúng chưa chứng minh toàn bộ truy vấn đúng, transaction đúng hay mọi đường dữ liệu được xử lý đầy đủ.

Khi cần mở rộng tiếp, hãy bắt đầu từ yêu cầu cụ thể: thêm thao tác nghiệp vụ thì xem fragment; thay implementation nền thì xem base class; điều chỉnh cách tạo proxy thì xem factory customizer; thay cách tạo repository factory thì xem hook của factory bean thuộc store. Cách chọn này giữ cấu hình gần với trách nhiệm cần thay đổi và giúp đánh giá phạm vi ảnh hưởng trước khi áp dụng cho nhiều repository.
