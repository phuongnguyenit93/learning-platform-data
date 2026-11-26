# Vai trò của RepositoryFactorySupport và factory đặc thù store

## Mục tiêu bài học

Khi một service inject một interface repository, đối tượng được inject thường là proxy do hạ tầng Spring Data tạo ra. Proxy đó có thể chuyển một lời gọi CRUD đến implementation cơ sở, chuyển một query method đến cơ chế truy vấn hoặc gọi một fragment tùy biến đã được ghép vào repository.

Spring Data Commons cung cấp `RepositoryFactorySupport` làm nền tảng chung cho quá trình này. Các factory đặc thù store, chẳng hạn `JpaRepositoryFactory` và `MongoRepositoryFactory`, bổ sung kiến thức về mapping, triển khai repository và thực thi query của từng công nghệ lưu trữ.

Bài học thuộc chương **Proxy và thành phần** của module SPRING_DATA_COMMONS. Sau bài học, bạn có thể:

- Đặt RepositoryFactorySupport đúng vị trí trong vòng đời tạo repository.
- Phân biệt factory tạo repository với FactoryBean và factory tài nguyên lưu trữ.
- Theo dõi các nhóm lời gọi từ interface qua proxy đến thành phần thực thi.
- Giải thích phần dùng chung của Commons và phần đặc thù JPA hoặc MongoDB.
- Chọn mức mở rộng phù hợp thay vì tự viết factory cho mọi nhu cầu tùy biến.

## 1. Từ interface đến một đối tượng có thể gọi được

Giả sử ứng dụng có:

~~~java
public interface BookRepository
        extends CrudRepository<Book, Long> {
}
~~~

Java chỉ biết đây là một interface có các hợp đồng kế thừa. Bản thân khai báo không chứa một implementation của save hay findById.

Trong ứng dụng Spring Data được cấu hình đúng, hạ tầng repository sẽ:

1. Nhận metadata của interface.
2. Kết hợp cấu hình repository với hạ tầng của module lưu trữ.
3. Chuẩn bị implementation cơ sở, query methods và các phần mở rộng cần thiết.
4. Tạo proxy triển khai interface mà bên gọi sử dụng.
5. Cung cấp đối tượng đó qua bean repository trong container.

Không cần sinh một file Java implementation riêng trong mã nguồn ứng dụng để hiện thực từng method CRUD.

Tuy nhiên, “không tự viết implementation” không có nghĩa không có implementation. Phía sau proxy có những đối tượng thực thi do module cung cấp và có thể có thêm phần triển khai do ứng dụng viết.

## 2. RepositoryFactorySupport nằm ở đâu?

Lớp `org.springframework.data.repository.core.support.RepositoryFactorySupport` thuộc Spring Data Commons. Đây là nền tảng trừu tượng cho các factory tạo repository.

Có thể hình dung:

~~~mermaid
flowchart TD
    A["Interface repository và cấu hình"] --> B["Factory đặc thù store"]
    C["RepositoryFactorySupport của Commons"] -.-> B
    B --> D["Metadata và thành phần repository"]
    D --> E["Proxy triển khai interface"]
    E --> F["Triển khai cơ sở"]
    E --> G["RepositoryQuery"]
    E --> H["Fragment tùy biến"]
    E --> I["Default method của interface"]
~~~

Factory đặc thù store sử dụng cơ chế chung của RepositoryFactorySupport và cung cấp những quyết định gắn với công nghệ lưu trữ.

Ví dụ:

| Factory | Module | Hạ tầng thực thi liên quan |
| --- | --- | --- |
| JpaRepositoryFactory | Spring Data JPA | EntityManager và mapping JPA. |
| MongoRepositoryFactory | Spring Data MongoDB | MongoOperations/MongoTemplate và mapping MongoDB. |

RepositoryFactorySupport không phải một datasource, một driver hay một engine tự chuyển mọi query thành SQL. Nó tổ chức việc xây dựng repository và các thành phần xử lý lời gọi.

## 3. Phân biệt các thành phần có tên gần giống nhau

| Thành phần | Vai trò |
| --- | --- |
| RepositoryFactorySupport | Nền tảng chung để factory xây dựng repository proxy và phối hợp thành phần repository. |
| JpaRepositoryFactory | Factory cụ thể tạo repository theo cơ chế JPA. |
| MongoRepositoryFactory | Factory cụ thể tạo repository theo cơ chế MongoDB. |
| RepositoryFactoryBeanSupport | Hạ tầng tích hợp factory repository với vòng đời bean của Spring. |
| JpaRepositoryFactoryBean hoặc MongoRepositoryFactoryBean | FactoryBean của module, nhận cấu hình và hạ tầng cần thiết để cung cấp repository bean. |
| EntityManagerFactory | Factory tài nguyên JPA, cung cấp EntityManager cho một persistence unit. |
| MongoDatabaseFactory | Hạ tầng cung cấp database và hỗ trợ tài nguyên/session MongoDB. |

Những khác biệt này ảnh hưởng trực tiếp tới cách cấu hình:

- Chọn EntityManagerFactory khác là chọn hạ tầng persistence cho repository JPA.
- Chọn repository factory bean khác là thay cách hạ tầng tạo repository.
- Hai thay đổi không đồng nghĩa và không thay thế nhau.

Trong cấu hình thông thường, JpaRepositoryFactoryBean làm cầu nối để tạo và cấu hình JpaRepositoryFactory. Tương tự, MongoRepositoryFactoryBean tích hợp MongoRepositoryFactory với các dependency của module.

Ứng dụng thường tương tác với repository interface. Factory và FactoryBean là những thành phần hạ tầng, không phải đối tượng mà service nghiệp vụ cần tự tạo mỗi lần truy vấn.

## 4. Những trách nhiệm chung của RepositoryFactorySupport

### 4.1. Đọc metadata của repository

Factory cần biết interface đang quản lý domain nào, kiểu ID nào và có những method nào.

Metadata có thể đến từ hệ kế thừa Repository hoặc từ cách khai báo phù hợp như @RepositoryDefinition.

Hai abstraction thường gặp:

| Metadata | Nội dung khái quát |
| --- | --- |
| RepositoryMetadata | Thông tin repository interface, domain type, ID type và các đặc trưng liên quan. |
| RepositoryInformation | Mở rộng thông tin để phục vụ phân tích method, implementation cơ sở và cách xử lý repository. |

Ví dụ, với BookRepository quản lý Book và Long, metadata giúp hạ tầng đặt các method vào đúng ngữ cảnh domain. Metadata không tự quyết định Book là bảng hay document; module và mapping cung cấp phần đó.

### 4.2. Phối hợp implementation cơ sở và composition

Một repository có thể gồm:

- Implementation cơ sở do module cung cấp.
- Các fragment tùy biến.
- Những query method cần cơ chế thực thi query.
- Default methods đã có thân hàm Java.

RepositoryFactorySupport cung cấp hạ tầng để phối hợp những phần này, thay vì yêu cầu mọi module tự xây lại toàn bộ mô hình composition.

Các abstraction như RepositoryComposition và repository fragments giúp biểu diễn những phần hành vi ghép vào repository. Việc tìm và đăng ký implementation tùy biến trong một ứng dụng còn liên quan đến cấu hình repository và quá trình tạo bean.

Không nên coi factory chung là một bộ quét toàn bộ package để tự đoán mọi lớp implementation.

### 4.3. Tạo proxy và hạ tầng chặn lời gọi

Proxy là đối tượng mà bên gọi nhìn thấy qua repository interface. Nó có thể được bổ sung các interceptor hoặc advice phục vụ những nhóm hành vi liên quan.

Chẳng hạn, hạ tầng có thể có thành phần xử lý query, thực thi method trong composition, gọi default method và các xử lý bổ sung được module hoặc cấu hình đăng ký.

Không cần ghi nhớ một thứ tự interceptor cố định để sử dụng repository. Thứ tự và chi tiết nội bộ có thể thay đổi theo phiên bản, module và những tùy biến đã áp dụng.

Điều quan trọng là proxy phối hợp lời gọi, còn hành vi cuối cùng được cung cấp bởi thành phần phù hợp.

### 4.4. Hỗ trợ những điểm mở rộng

Factory chung có các điểm mở rộng để module hoặc cấu hình tham gia quá trình xây dựng repository.

Những khái niệm cần nhận diện gồm:

- Chọn repository base class.
- Tạo hoặc lấy đối tượng implementation cơ sở.
- Cung cấp query lookup strategy.
- Thêm xử lý sau cấu hình proxy hoặc quan sát quá trình tạo query.
- Kết hợp các fragment đã được cung cấp.

Các API protected và hook cụ thể phải được đối chiếu với phiên bản Spring Data đang dùng khi thực sự viết phần mở rộng. Hiểu trách nhiệm của chúng hữu ích hơn việc sao chép nguyên một subclass dựa trên một chữ ký nội bộ của dòng phiên bản khác.

## 5. Factory đặc thù store bổ sung điều gì?

### 5.1. Implementation cơ sở

Với repository JPA thông thường, implementation cơ sở thường là `SimpleJpaRepository`. Với repository MongoDB imperative thông thường, implementation cơ sở thường là `SimpleMongoRepository`.

Chúng không phải cùng một implementation với hai tên khác nhau.

| Khía cạnh | JPA | MongoDB |
| --- | --- | --- |
| Đối tượng domain | Entity theo mapping JPA. | Document theo mapping MongoDB. |
| API thực thi | EntityManager. | MongoOperations/MongoTemplate. |
| Triển khai CRUD cơ sở thường gặp | SimpleJpaRepository. | SimpleMongoRepository. |
| Cách biểu diễn và thực hiện query | Theo cơ chế JPA và provider. | Theo cơ chế query MongoDB và driver. |

Factory của module chọn và xây dựng implementation phù hợp với metadata repository cùng hạ tầng đã được cung cấp.

### 5.2. Thông tin entity và định danh

Một module cần biết cách đọc ID, nhận diện đối tượng mới và sử dụng thông tin mapping.

Chẳng hạn, factory JPA sử dụng thông tin entity phù hợp với JPA. Factory MongoDB sử dụng thông tin domain theo mapping MongoDB.

Commons có các abstraction hỗ trợ việc này, nhưng không tự áp một quy tắc nhận diện entity mới cho mọi module.

Vì thế, hai repository cùng công khai save không bảo đảm bên dưới có cùng cơ chế persist, merge hoặc cập nhật document.

### 5.3. Tạo query phù hợp store

Module cung cấp chiến lược để biến query method thành một đối tượng query có thể thực thi.

Commons có thể phân tích cấu trúc tên method và mô hình hóa tham số, kiểu trả về hoặc metadata chung. Nhưng chuyển điều kiện thành query đúng công nghệ là trách nhiệm của module.

Một tên method có thể phân tích được không tự chứng minh store hỗ trợ mọi toán tử hoặc mọi cách kết hợp điều kiện đó.

### 5.4. Liên kết với đúng hạ tầng

JpaRepositoryFactory cần EntityManager phù hợp. MongoRepositoryFactory cần MongoOperations phù hợp.

Một factory đúng module nhưng nhận hạ tầng sai nguồn vẫn có thể tạo ra repository truy cập dữ liệu ngoài ý định, hoặc thất bại khi mapping và nguồn dữ liệu không khớp.

Factory không tự chọn lại datasource hay database theo tên method mỗi lần gọi.

## 6. Vòng đời trong một ứng dụng Spring được cấu hình thông thường

Có thể phân tích quá trình tạo repository theo các giai đoạn:

~~~text
Cấu hình Boot hoặc annotation Enable của module
    -> phát hiện interface repository candidate
    -> đăng ký bean definition/factory bean phù hợp
    -> cấp hạ tầng và cấu hình cho factory của module
    -> đọc metadata repository
    -> chuẩn bị composition, implementation cơ sở và query
    -> tạo proxy repository
    -> inject bean vào thành phần sử dụng
~~~

Đây là mô hình khái quát, không phải một trace đầy đủ cho mọi phiên bản.

### 6.1. Scanning không phải công việc duy nhất của factory

Repository scanning xác định candidate và cấu hình đăng ký. Factory nhận thông tin để xây dựng repository tương ứng.

Nếu interface nằm ngoài vùng quét, không nên chỉ tìm lỗi trong RepositoryFactorySupport. Quá trình có thể chưa đến bước tạo factory cho interface đó.

Tương tự, @NoRepositoryBean được dùng để loại interface nền khỏi việc tạo repository bean theo cơ chế phát hiện thông thường. Nó không lựa chọn implementation store thay cho factory.

### 6.2. Thời điểm tạo có thể bị hoãn

Lazy initialization hoặc bootstrap mode của module có thể làm một số bước tạo hoặc xác minh repository diễn ra muộn hơn.

Do đó:

- Không phải mọi lỗi query đều bắt buộc xuất hiện ở cùng một thời điểm startup.
- Việc inject được một đối tượng proxy chưa chắc đã thực thi mọi đường query.
- Khi repository được sử dụng lần đầu, những kiểm tra bị trì hoãn vẫn có thể phát hiện lỗi.

Việc chuẩn bị một query và việc thực thi query để đọc hoặc ghi dữ liệu cũng là hai giai đoạn khác nhau.

## 7. Ví dụ một repository có bốn nhóm hành vi

Phần này dùng JPA để minh họa đường gọi. Giả định ứng dụng đã có module JPA, datasource, mapping và vùng quét repository phù hợp.

### 7.1. Domain Book

File `domain/Book.java`:

~~~java
package com.example.library.domain;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "library_book")
public class Book {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String title;

    private boolean available;

    protected Book() {
    }

    public Book(String title, boolean available) {
        this.title = title;
        this.available = available;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public boolean isAvailable() {
        return available;
    }
}
~~~

### 7.2. Fragment ứng dụng

File `repository/BookTextOperations.java`:

~~~java
package com.example.library.repository;

public interface BookTextOperations {

    String normalizeTitle(String value);
}
~~~

File `repository/BookTextOperationsImpl.java`:

~~~java
package com.example.library.repository;

public class BookTextOperationsImpl
        implements BookTextOperations {

    @Override
    public String normalizeTitle(String value) {
        if (value == null) {
            throw new IllegalArgumentException(
                "Tiêu đề không được null"
            );
        }

        return value.trim();
    }
}
~~~

Implementation cung cấp một hành vi Java cụ thể. Factory không tự suy ra thuật toán chuẩn hóa tiêu đề từ tên method.

Tên lớp theo hậu tố Impl là quy ước mặc định thường dùng để phát hiện implementation của fragment. Cần đặt implementation trong phạm vi phát hiện phù hợp và dùng đúng quy ước mà cấu hình dự án lựa chọn.

### 7.3. Interface repository

File `repository/BookRepository.java`:

~~~java
package com.example.library.repository;

import com.example.library.domain.Book;
import java.util.List;
import java.util.Optional;
import org.springframework.data.repository.CrudRepository;

public interface BookRepository
        extends CrudRepository<Book, Long>,
                BookTextOperations {

    List<Book> findByAvailableTrueOrderByTitleAsc();

    default Optional<Book> findAvailableById(Long id) {
        return findById(id).filter(Book::isAvailable);
    }
}
~~~

Bốn nhóm lời gọi có thể đọc như sau:

| Method | Nguồn hành vi |
| --- | --- |
| save, findById và các CRUD kế thừa | Implementation cơ sở của JPA trong cấu hình thông thường. |
| findByAvailableTrueOrderByTitleAsc | Query method được cơ chế JPA tạo và thực thi. |
| normalizeTitle | Implementation fragment BookTextOperationsImpl. |
| findAvailableById | Default method có thân hàm Java trên interface. |

Bảng là cách phân loại trách nhiệm, không phải một chuỗi if/else cố định bên trong proxy.

Default method tự viết logic Java và tiếp tục gọi findById. Hạ tầng không cần suy diễn một query từ tên default method đã có implementation đó.

Fragment tùy biến được ghép đúng cũng có thể cung cấp hành vi cho những method trùng hợp đồng cơ sở theo cơ chế composition. Nếu có ý định ghi đè hành vi, phải giữ đúng chữ ký và hiểu ảnh hưởng lên hợp đồng repository, không chỉ thêm một method cùng tên gần giống.

### 7.4. Quan sát ở phía bên gọi

~~~java
Book saved = repository.save(
    new Book("Spring Data Commons", true)
);

List<Book> availableBooks =
    repository.findByAvailableTrueOrderByTitleAsc();

String normalized =
    repository.normalizeTitle("   Spring Data Commons   ");

Optional<Book> availableBook =
    repository.findAvailableById(saved.getId());
~~~

Bên gọi dùng một interface, nhưng bốn lời gọi không nhất thiết đi vào cùng một đối tượng implementation cuối cùng.

Đây là lý do repository nên được hiểu như một proxy phối hợp nhiều thành phần, thay vì một lớp CRUD đơn lẻ đã tự chứa mọi query và mọi hành vi ứng dụng.

## 8. QueryLookupStrategy và RepositoryQuery

### 8.1. Từ method đến một query có thể thực thi

Một query method cần được liên kết với một cơ chế thực thi cụ thể. Factory của module cung cấp query lookup strategy phù hợp để phân giải method đó.

Kết quả là một dạng `RepositoryQuery` hoặc thành phần query tương ứng theo hạ tầng module.

Có thể hình dung:

~~~text
Method repository và metadata
    -> chiến lược tìm hoặc tạo query
    -> đối tượng query của module
    -> nhận tham số khi method được gọi
    -> thực thi qua API truy cập dữ liệu của store
~~~

Trong JPA, việc thực thi còn đi qua EntityManager và provider. Trong MongoDB, nó đi qua cơ chế MongoOperations và driver tương ứng.

### 8.2. Những ý định chiến lược thường gặp

| Chiến lược | Ý định |
| --- | --- |
| CREATE | Tạo query từ thông tin method theo khả năng module. |
| USE_DECLARED_QUERY | Sử dụng query đã khai báo; thiếu query phù hợp có thể làm phân giải thất bại. |
| CREATE_IF_NOT_FOUND | Tìm query khai báo trước, nếu không có thì thử tạo từ method. |

Những key này thuộc mô hình chung, còn mức hỗ trợ và cấu hình mặc định phải được xem theo module. Không giả định mọi module đều hiện thực mọi lựa chọn giống nhau.

Đổi strategy không làm một thuộc tính domain không tồn tại trở thành hợp lệ và không biến một toán tử chưa được store hỗ trợ thành query thực thi được.

### 8.3. Method tùy biến không có implementation có thể bị hiểu nhầm là query

Nếu BookTextOperationsImpl không được tìm thấy hoặc chưa được cung cấp vào composition, method normalizeTitle không tự có hành vi.

Hạ tầng có thể cố phân giải một method chưa được triển khai theo đường query và phát sinh lỗi tên thuộc tính hoặc lỗi tạo query.

Trong trường hợp đó, nguyên nhân có thể nằm ở đăng ký fragment thay vì chính khả năng parse của query.

Cần lần theo câu hỏi: method này được thiết kế là query, default method, base method hay custom implementation? Sau đó kiểm tra thành phần cung cấp hành vi đã có trong cấu hình chưa.

## 9. Proxy repository không đồng nhất với base implementation

Một bean BookRepository không được bảo đảm là một instance có thể ép kiểu trực tiếp thành SimpleJpaRepository.

Proxy thường được nhìn thấy qua interface repository. Bên trong có target hoặc composition và những thành phần xử lý khác.

Vì vậy:

- Inject và sử dụng BookRepository trong service.
- Không phụ thuộc vào tên lớp proxy được sinh ở runtime.
- Không suy từ class name của proxy để kết luận query đang dùng store nào.
- Không ép kiểu về base implementation để gọi một method chưa công khai trong API.

Nếu ứng dụng cần thêm hành vi, hãy đưa hành vi đó vào hợp đồng và cơ chế mở rộng phù hợp.

Proxy cũng không tự làm mọi method có cùng transaction, cùng mức tải dữ liệu hay cùng bảo đảm hiệu năng. Những đặc tính đó còn phụ thuộc cấu hình, module và thành phần thực thi.

## 10. Tạo factory trực tiếp khác với dùng repository bean được quản lý

Để thấy API tạo repository, xét một interface đọc tối thiểu:

~~~java
import com.example.library.domain.Book;
import java.util.Optional;
import org.springframework.data.repository.Repository;

public interface BookReadRepository
        extends Repository<Book, Long> {

    Optional<Book> findById(Long id);
}
~~~

Giả sử đã có một EntityManager được cấu hình và quản lý vòng đời phù hợp, một đoạn API minh họa là:

~~~java
JpaRepositoryFactory factory =
    new JpaRepositoryFactory(entityManager);

BookReadRepository repository =
    factory.getRepository(BookReadRepository.class);
~~~

JpaRepositoryFactory được import từ `org.springframework.data.jpa.repository.support`. Ví dụ chỉ minh họa việc factory có thể tạo proxy từ interface; nó không phải toàn bộ cấu hình một ứng dụng.

Những khác biệt cần hiểu khi tạo trực tiếp:

- Không tự có toàn bộ scanning và đăng ký bean như khi dùng cấu hình module.
- Cần cung cấp hạ tầng và quản lý vòng đời đúng.
- Nếu interface có fragment, cần cung cấp composition phù hợp; tên một lớp Impl trên classpath chưa tự bảo đảm factory trực tiếp sẽ đăng ký nó.
- Các proxy post-processor, transaction advice hoặc exception translation được thiết lập qua FactoryBean và cấu hình tiêu chuẩn không được mặc định là đã giống hệt.
- Cần hiểu rõ những cấu hình mà mình đã bỏ qua hoặc tự nhận trách nhiệm cung cấp.

Đặc biệt, một proxy được tạo ra không tự chứng minh lời gọi ghi đã có transaction cần thiết. Trong cấu hình Spring Data JPA thông thường, hạ tầng FactoryBean và transaction liên quan tham gia tạo hành vi đó.

Ứng dụng nghiệp vụ thường nên nhận repository bean được cấu hình thay vì tạo factory mới trong mỗi method service. Tạo trực tiếp phù hợp hơn với các tình huống hạ tầng hoặc tích hợp mà người viết chủ động kiểm soát đầy đủ ngữ cảnh.

## 11. Chọn điểm mở rộng theo yêu cầu

| Yêu cầu | Điểm mở rộng nên đánh giá |
| --- | --- |
| Ghép vài thao tác đọc đã có bằng logic Java đơn giản. | Default method hoặc service. |
| Thêm một nhóm hành vi tùy biến cho một repository. | Repository fragment. |
| Thay hành vi cơ sở cho một nhóm repository của cùng module. | Base implementation phù hợp với module. |
| Thay cách tạo, cấu hình hoặc phối hợp proxy/query ở mức hạ tầng. | Factory/factory bean tùy biến tương thích. |

Một custom factory không phải bước bắt buộc để viết một query đặc biệt. Fragment có thể dùng EntityManager, template hoặc API phù hợp mà không thay toàn bộ cơ chế tạo repository.

Ngược lại, nếu thật sự thay factory, cần giữ các hợp đồng:

- Metadata domain và ID đúng.
- Base implementation tương thích.
- Query lookup strategy phù hợp với module.
- Composition và custom implementation được cung cấp đúng.
- Hạ tầng transaction và các xử lý proxy cần thiết vẫn được tích hợp.
- Bộ dependency và API mở rộng tương thích với phiên bản dự án.

Commons cho phép tái sử dụng cấu trúc xây dựng repository, nhưng factory JPA không trở thành factory MongoDB chỉ vì cả hai cùng mở rộng nền tảng chung.

## 12. Những điều RepositoryFactorySupport không tự bảo đảm

### 12.1. Không tự cấu hình mọi kết nối

Factory cần hạ tầng store phù hợp được cung cấp. Nó không tự đoán URL, credentials hoặc database từ tên repository.

### 12.2. Không tự tạo schema và index cho mọi store

Tạo proxy không đồng nghĩa đã tạo bảng, collection hoặc index phục vụ query. Những việc đó có cơ chế mapping, migration và cấu hình riêng.

### 12.3. Không làm mọi query portable

Một method có thể diễn đạt bằng mô hình chung nhưng vẫn dùng toán tử, kiểu trả về hoặc đặc tính mà module khác không hỗ trợ.

### 12.4. Không thay thế transaction manager

Transaction manager quản lý tài nguyên và ranh giới transaction. Repository factory xây dựng repository và phối hợp hành vi. Hai vai trò có liên quan nhưng không phải một.

### 12.5. Không tự kích hoạt toàn bộ auditing hoặc projection

Factory sử dụng các cơ chế được cấu hình để xử lý repository. Tính năng cụ thể vẫn cần mức hỗ trợ và tích hợp của module, mapping và cấu hình ứng dụng.

Một repository CRUD hoạt động chưa tự chứng minh mọi dạng projection hoặc auditing đã được thiết lập đúng.

## 13. Phân tích lỗi theo đúng giai đoạn

| Hiện tượng | Giai đoạn hoặc thành phần cần kiểm tra |
| --- | --- |
| Không có bean repository để inject. | Scanning, cấu hình đăng ký, điều kiện module trước bước tạo repository. |
| Không xác định được domain hoặc ID. | Metadata interface và cách khai báo repository. |
| Domain không phải kiểu được store quản lý. | Mapping, phạm vi entity và hạ tầng cấp cho factory. |
| Query tham chiếu thuộc tính không tồn tại. | Method query, query lookup strategy và metadata domain. |
| Method custom bị báo như một query sai. | Fragment implementation và composition có được đăng ký không. |
| Ép kiểu proxy sang implementation bị lỗi. | Mã ứng dụng phụ thuộc nhầm vào lớp target thay vì interface. |
| Proxy tạo được nhưng thao tác ghi thiếu transaction. | Cách tạo repository, post-processor và transaction configuration. |
| Tùy biến factory gây lỗi liên kết API. | Phiên bản dependency, chữ ký hook và hợp đồng của module. |

Không nên bắt đầu bằng cách thay RepositoryFactorySupport hoặc viết một factory mới cho mọi lỗi.

Hãy xác định lời gọi đã đi tới bước nào: đăng ký, metadata, tạo proxy, phân giải method hay thực thi truy cập dữ liệu. Mỗi bước cung cấp bằng chứng cho một nhóm nguyên nhân khác nhau.

## 14. Bài tập vận dụng

### Bài tập 1: Phân loại lời gọi

Với BookRepository trong bài, phân loại:

1. findById.
2. findByAvailableTrueOrderByTitleAsc.
3. normalizeTitle.
4. findAvailableById.

Chỉ ra phần dùng chung của factory và phần cung cấp hành vi cuối cùng cho mỗi method.

### Bài tập 2: Phân biệt factory và tài nguyên

Giải thích vì sao ba đối tượng sau không thay thế nhau:

- JpaRepositoryFactoryBean.
- JpaRepositoryFactory.
- EntityManagerFactory.

Xác định đối tượng nào tích hợp với vòng đời bean, đối tượng nào tạo repository và đối tượng nào cung cấp tài nguyên persistence.

### Bài tập 3: Điều tra fragment bị thiếu

Repository có method normalizeTitle nhưng startup báo lỗi phân giải một query có tên liên quan.

Hãy kiểm tra quy ước implementation, package phát hiện và composition trước khi sửa tên query hoặc thay factory. Giải thích vì sao có interface fragment chưa đủ để tự tạo hành vi.

### Bài tập 4: Đánh giá cách tạo trực tiếp

Một service tự tạo JpaRepositoryFactory rồi gọi getRepository cho mỗi yêu cầu.

Hãy xác định những trách nhiệm mà service đang nhận về: EntityManager, vòng đời, fragment và các xử lý proxy. Đề xuất cách nhận một repository bean được quản lý nếu service không có nhu cầu hạ tầng đặc biệt.

RepositoryFactorySupport giúp các module Spring Data chia sẻ cách xây dựng một repository có metadata, composition và proxy. Factory đặc thù store hoàn thiện mô hình đó bằng mapping, implementation cơ sở và query của công nghệ cụ thể. Hiểu cả hai phần giúp giải thích vì sao một interface có thể hoạt động mà vẫn giữ được ranh giới rõ giữa hợp đồng chung và khả năng của từng kho dữ liệu.