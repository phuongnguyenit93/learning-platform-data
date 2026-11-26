# Auto-configuration trong Spring Boot

## Mục tiêu bài học

Một ứng dụng Spring Boot có thể sử dụng repository mà không khai báo thủ công một implementation và không thêm annotation kích hoạt repository trong trường hợp thông thường. Điều đó đến từ sự phối hợp giữa auto-configuration của Boot, module Spring Data dành cho kho dữ liệu và hạ tầng dùng chung trong Spring Data Commons.

Auto-configuration không có nghĩa Boot tạo repository cho mọi interface xuất hiện trong dự án. Nó chỉ áp dụng cấu hình khi các điều kiện về classpath, bean, thuộc tính và phạm vi phát hiện repository phù hợp.

Bài học thuộc chương **Kích hoạt repository** của module SPRING_DATA_COMMONS. Sau bài học, bạn có thể:

- Giải thích vai trò riêng của Boot, Commons và module lưu trữ.
- Nhận diện các điều kiện để repository được tự động đăng ký.
- Đặt lớp ứng dụng, repository và domain vào phạm vi quét phù hợp.
- Phân biệt component scanning với repository scanning và entity scanning.
- Sử dụng báo cáo điều kiện để phân tích lỗi khởi tạo repository.
- Nhận biết thời điểm cần chuyển một phần cấu hình sang khai báo tường minh.

Các ví dụ Java và thuộc tính JPA bên dưới minh họa theo bố cục API Spring Boot 3.x với Jakarta Persistence. Khi áp dụng vào một dòng Boot khác, cần dùng dependency, import và thuộc tính phù hợp với dòng đó.

## 1. Ba thành phần phối hợp để tạo repository

| Thành phần | Trách nhiệm chính |
| --- | --- |
| Spring Data Commons | Cung cấp hợp đồng repository, metadata và hạ tầng chung để xây dựng repository. |
| Module Spring Data cụ thể | Tích hợp factory, mapping và thực thi truy cập với JPA, MongoDB hoặc công nghệ tương ứng. |
| Spring Boot | Đánh giá điều kiện và tự cấu hình những thành phần tích hợp phù hợp với ứng dụng. |

Ví dụ với JPA:

~~~text
Dependency JPA có trên classpath
    + cấu hình ứng dụng phù hợp
    + persistence infrastructure đáp ứng điều kiện
    + repository thuộc phạm vi phát hiện
        -> module JPA đăng ký repository
        -> hạ tầng tạo bean/proxy
        -> service có thể inject interface
~~~

Commons không tự chọn một cơ sở dữ liệu cho repository. Boot cũng không bỏ qua module lưu trữ để tự thực hiện CRUD bằng một cơ chế chung cho mọi công nghệ.

Nếu chỉ có dependency `spring-data-commons`, mã có thể import `Repository`, `CrudRepository` hoặc `Pageable`. Điều đó chưa đủ để Boot tạo một repository JPA hay MongoDB có thể truy cập dữ liệu.

## 2. @SpringBootApplication tham gia như thế nào?

Trong trường hợp thông thường, lớp khởi động có:

~~~java
@SpringBootApplication
public class LibraryApplication {
}
~~~

Annotation này kết hợp các vai trò nền tảng, trong đó có:

- Cấu hình ứng dụng Boot.
- Bật cơ chế auto-configuration.
- Component scanning theo phạm vi của lớp ứng dụng, trừ khi được tùy chỉnh.

`@EnableAutoConfiguration` bên trong cơ chế này đưa các auto-configuration phù hợp vào quá trình xử lý cấu hình. Những cấu hình đó tiếp tục có điều kiện để quyết định phần nào được áp dụng.

Có thể hình dung:

~~~mermaid
flowchart TD
    A["SpringBootApplication và cấu hình môi trường"] --> B["Đánh giá các auto-configuration"]
    B --> C["Điều kiện classpath, bean và thuộc tính"]
    C --> D["Cấu hình tích hợp cho module lưu trữ"]
    D --> E["Phát hiện interface repository"]
    E --> F["Metadata và factory của module"]
    F --> G["Bean repository và proxy"]
    G --> H["Inject vào service hoặc runner"]
~~~

Đây là sơ đồ trách nhiệm logic. Việc đăng ký bean definition, đánh giá điều kiện và tạo instance không phải lúc nào cũng diễn ra thành từng khối đơn giản theo đúng thứ tự của sơ đồ.

### Starter không phải annotation kích hoạt

Starter giúp đưa một tập dependency liên quan vào dự án. Nó tạo điều kiện về classpath để auto-configuration có thể phù hợp, nhưng không thay thế toàn bộ điều kiện còn lại.

Ví dụ, có JPA starter nhưng thiếu cấu hình datasource cần thiết vẫn có thể làm ứng dụng không khởi tạo được. Có starter và datasource nhưng repository nằm ngoài phạm vi quét thì interface đó vẫn có thể không được đăng ký.

## 3. Những điều kiện Boot thường xem xét

Các auto-configuration có thể kiểm tra những nhóm điều kiện sau:

| Nhóm điều kiện | Câu hỏi điển hình |
| --- | --- |
| Classpath | Module, driver hoặc thư viện tích hợp cần thiết có mặt không? |
| Bean hạ tầng | Có datasource, persistence factory hoặc bean kết nối phù hợp không? |
| Thuộc tính | Tính năng auto-configuration đó có đang được bật không? |
| Cấu hình do ứng dụng cung cấp | Ứng dụng đã tự khai báo thành phần mà Boot định cung cấp chưa? |
| Ngữ cảnh ứng dụng | Loại ứng dụng và các điều kiện khác có phù hợp không? |

Không phải mọi module sử dụng cùng một bộ điều kiện. Cần quan sát cấu hình cụ thể của công nghệ đang chọn.

### Điều kiện về bean không đồng nghĩa đã truy cập dữ liệu thành công

Một bean kết nối có thể được tạo hoặc được khai báo mà chưa chứng minh mọi truy vấn sẽ thành công. Cấu hình có thể hợp lệ về mặt tạo bean nhưng sai thông tin truy cập, mapping hoặc query.

Tương tự, một auto-configuration khớp điều kiện chưa chứng minh tất cả repository và method query đều hợp lệ. Khởi tạo factory hoặc lời gọi đầu tiên vẫn có thể phát hiện vấn đề.

### Boot có thể lùi lại khi ứng dụng tự cấu hình

Nhiều auto-configuration sử dụng các điều kiện kiểu “chưa có bean phù hợp” để cung cấp cấu hình mặc định. Khi ứng dụng tự khai báo thành phần tương ứng, phần mặc định đó có thể không được tạo nữa.

Ví dụ, một DataSource do ứng dụng cung cấp có thể làm phần tạo DataSource mặc định lùi lại, trong khi auto-configuration JPA vẫn tiếp tục sử dụng DataSource đó nếu thỏa điều kiện.

Vì vậy, không dùng quy tắc “thêm một bean cấu hình tay thì toàn bộ auto-configuration ngừng hoạt động”. Cần xem chính điều kiện của từng phần.

## 4. Ví dụ tối thiểu: repository được phát hiện tự động

### 4.1. Dependency thực hành

Giả định dự án Maven đã có parent hoặc BOM phù hợp để quản lý dependency. Phần dependency cho ví dụ gồm:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>

    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Starter JPA đưa module tích hợp JPA vào dự án; Commons xuất hiện qua bộ dependency Spring Data liên quan. Không cần thêm riêng một version Commons để làm repository được nhận diện.

Đoạn XML là phần dependency, không phải toàn bộ cấu hình Maven. Dự án vẫn cần cấu hình build và Java phù hợp với bộ Boot đang sử dụng.

### 4.2. Cấu trúc package

~~~text
com.example.library
    LibraryApplication
    domain
        Book
    repository
        BookRepository
~~~

Lớp ứng dụng đặt ở package cha `com.example.library`. Với cấu hình Boot thông thường, các package con chứa repository và entity nằm trong phạm vi mặc định.

### 4.3. Entity Book

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

    protected Book() {
    }

    public Book(String title) {
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }
}
~~~

Entity được quản lý theo JPA. Nó không cần `@Component` để trở thành một kiểu được JPA mapping.

### 4.4. Interface repository

File `repository/BookRepository.java`:

~~~java
package com.example.library.repository;

import com.example.library.domain.Book;
import org.springframework.data.repository.CrudRepository;

public interface BookRepository
        extends CrudRepository<Book, Long> {
}
~~~

Không có `@Repository` và cũng không có lớp implementation do ứng dụng tự viết.

Interface là một repository candidate thông qua hệ kế thừa của Commons. Module JPA được Boot tích hợp sẽ dùng cơ chế repository tương ứng để đăng ký và tạo bean.

Một interface sử dụng `@RepositoryDefinition` hợp lệ cũng có thể được phát hiện qua cơ chế repository. Điều đó vẫn đòi hỏi module và phạm vi scanning phù hợp.

### 4.5. Cấu hình cơ sở dữ liệu thực hành

File `application.yml`:

~~~yaml
spring:
  main:
    web-application-type: none

  datasource:
    url: jdbc:h2:mem:repository_boot;DB_CLOSE_DELAY=-1
    username: sa
    password: ""

  jpa:
    hibernate:
      ddl-auto: create-drop
~~~

Ví dụ dùng H2 trong bộ nhớ và tạo/dọn schema theo vòng đời ứng dụng. Đây là cấu hình cho môi trường thực hành độc lập; dữ liệu không được thiết kế để tồn tại qua các lần chạy JVM.

`ddl-auto` điều khiển schema theo tích hợp JPA/Hibernate, không phải thuộc tính dùng để bật repository của Commons.

### 4.6. Lớp ứng dụng kiểm chứng bean và lời gọi cơ bản

File `LibraryApplication.java`:

~~~java
package com.example.library;

import com.example.library.repository.BookRepository;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class LibraryApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            LibraryApplication.class,
            args
        ).close();
    }

    @Bean
    ApplicationRunner repositoryProbe(BookRepository repository) {
        return args -> {
            long count = repository.count();

            System.out.println(
                "Repository đã được inject; số sách = " + count
            );
        };
    }
}
~~~

Ứng dụng console này chạy runner rồi đóng context khi `SpringApplication.run(...)` trả về. Việc đóng ngay sau runner là lựa chọn của ví dụ thực hành một lần.

Trong cấu trúc trên không cần thêm `@EnableJpaRepositories` hoặc `@EntityScan`, vì các package đã thuộc phạm vi mặc định và các điều kiện tích hợp phù hợp.

Kết quả dự kiến trên schema mới không có dữ liệu:

~~~text
Repository đã được inject; số sách = 0
~~~

Constructor hoặc tham số bean nhận được repository chứng minh bean đã được đăng ký và có thể inject. Lời gọi `count()` hoàn tất còn kiểm chứng thêm một thao tác truy cập dữ liệu cơ bản. Điều đó chưa kiểm chứng toàn bộ derived queries, projection hay những tính năng khác chưa được sử dụng.

## 5. Ba loại scanning dễ bị nhầm

| Cơ chế | Đối tượng chính được tìm | Ví dụ |
| --- | --- | --- |
| Component scanning | Các component Spring thông thường. | Service, controller, configuration. |
| Repository scanning | Interface repository candidate cho module. | BookRepository. |
| Entity scanning trong JPA | Các kiểu entity và mapping liên quan. | Book mang @Entity. |

Chúng có thể cùng sử dụng package cha của lớp ứng dụng trong cấu hình mặc định, nhưng không vì thế mà trở thành cùng một cơ chế.

### 5.1. scanBasePackages không mở rộng mọi loại scanning

Giả sử ứng dụng khởi động ở `com.example.launcher`, còn repository và entity nằm trong `com.acme.catalog`.

Chỉ khai báo:

~~~java
@SpringBootApplication(
    scanBasePackages = {
        "com.example.launcher",
        "com.acme.catalog"
    }
)
~~~

mở rộng component scanning, nhưng không tự mở rộng entity scanning hoặc Spring Data repository scanning theo cùng danh sách đó.

Đây là nguyên nhân phổ biến của tình huống service được tìm thấy nhưng repository mà service cần lại không có bean, hoặc repository có cấu hình quét riêng nhưng entity vẫn không được JPA quản lý.

### 5.2. Dùng cấu hình tường minh khi package không theo bố cục mặc định

Trong kịch bản package bên ngoài đó, có thể chỉ rõ từng phạm vi. Ví dụ dưới đây dùng import của Spring Boot 3.x:

~~~java
package com.example.launcher;

import com.acme.catalog.domain.Book;
import com.acme.catalog.repository.BookRepository;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.domain.EntityScan;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;

@SpringBootApplication(
    scanBasePackages = {
        "com.example.launcher",
        "com.acme.catalog.service"
    }
)
@EntityScan(basePackageClasses = Book.class)
@EnableJpaRepositories(
    basePackageClasses = BookRepository.class
)
public class LauncherApplication {

    public static void main(String[] args) {
        SpringApplication.run(LauncherApplication.class, args);
    }
}
~~~

Đây là một kịch bản thay thế, trong đó Book, BookRepository và service thực sự nằm ở các package `com.acme.catalog` đã nêu. Không đặt ví dụ này cạnh cấu hình mặc định rồi coi cả hai là bắt buộc.

`basePackageClasses` lấy package của lớp hoặc interface được truyền vào làm mốc quét. Nó không có nghĩa chỉ quét đúng một kiểu đó.

Với repository JPA được bật tường minh, Boot có thể lùi lại ở phần auto-configuration repository theo điều kiện của nó, trong khi vẫn cung cấp những phần hạ tầng khác phù hợp. Cần hiểu ranh giới của phần mình đã nhận trách nhiệm cấu hình.

### 5.3. @Repository không chữa được sai phạm vi repository scanning

Đặt stereotype `@Repository` lên một interface tùy ý không làm component scanning tự tạo implementation cho các method abstract.

Repository Spring Data cần được registrar/factory của module nhận diện và tạo. Nếu thiếu module hoặc sai phạm vi, thêm stereotype không thay thế phần cơ chế còn thiếu.

## 6. Những thuộc tính có thể làm thay đổi việc tự cấu hình

### 6.1. Tắt phần tự cấu hình repository JPA

Trong ví dụ Spring Boot 3.x:

~~~yaml
spring:
  data:
    jpa:
      repositories:
        enabled: false
~~~

Thuộc tính này làm phần auto-configuration repository JPA của Boot không được bật theo điều kiện tương ứng.

Nó không có nghĩa mọi truy cập JPA đã bị tắt và cũng không phải một công tắc toàn cục vô hiệu hóa cấu hình `@EnableJpaRepositories` do ứng dụng tự khai báo. Cấu hình tường minh có trách nhiệm và điều kiện riêng.

Khi repository biến mất sau khi đổi profile hoặc môi trường, hãy kiểm tra giá trị thuộc tính có hiệu lực, không chỉ nội dung một file cấu hình mà bạn đang mở.

### 6.2. Thay đổi thời điểm bootstrap repository

Với tích hợp JPA trong dòng Boot đang minh họa:

~~~yaml
spring:
  data:
    jpa:
      repositories:
        bootstrap-mode: default
~~~

Những chế độ thường được sử dụng gồm:

| Chế độ | Ý nghĩa khái quát |
| --- | --- |
| default | Khởi tạo repository theo cơ chế eager thông thường, trừ những điều kiện hoặc cấu hình liên quan khác. |
| lazy | Có thể hoãn việc khởi tạo repository thực sự đến lúc được sử dụng. |
| deferred | Hoãn khởi tạo rồi thực hiện ở giai đoạn làm mới context tương ứng. |

Đổi bootstrap mode có thể làm thời điểm phát hiện lỗi query hoặc mapping thay đổi. Nó không làm một repository không hợp lệ trở nên hợp lệ.

Với lazy initialization, việc ứng dụng khởi động hoặc nhận được một proxy injection chưa chắc đã kiểm chứng mọi phần thực thi. Cần quan sát thời điểm repository thực sự được sử dụng.

### 6.3. Exclusion và profile cũng ảnh hưởng kết quả

Ứng dụng có thể loại một auto-configuration qua annotation hoặc thuộc tính cấu hình. Profile cũng có thể thay đổi datasource, tính năng repository hay các bean được tạo.

Không cần bỏ tất cả exclusion hoặc bật mọi auto-configuration để sửa lỗi. Trước tiên xác định phần nào bị loại và đó có phải chủ đích của ứng dụng hay không.

Tên lớp auto-configuration, vị trí package và thuộc tính hỗ trợ có thể khác giữa các dòng Boot. Đối chiếu đúng dòng dependency của dự án khi đọc báo cáo hoặc khai báo exclusion.

## 7. Đọc Conditions Evaluation Report

Có thể bật chế độ debug của Boot để nhận thêm báo cáo điều kiện, ví dụ trong cấu hình thực hành:

~~~yaml
debug: true
~~~

Đây là thuộc tính cấp gốc của cấu hình. Nó không phải thuộc tính riêng của Commons và không tự bật logging chi tiết cho mọi thư viện.

Báo cáo thường phân biệt những phần như:

- **Positive matches**: các auto-configuration hoặc thành phần điều kiện phù hợp.
- **Negative matches**: những điều kiện không phù hợp, kèm lý do.
- **Exclusions**: các cấu hình bị loại có chủ đích.

### 7.1. Đọc báo cáo theo một câu hỏi cụ thể

Với repository JPA chưa được inject, có thể lần lượt hỏi:

1. Cấu hình datasource có phù hợp không?
2. Cấu hình persistence/JPA có đủ điều kiện không?
3. Cấu hình repository JPA có phù hợp hay đang lùi lại?
4. Nếu lùi lại, ứng dụng đã có cấu hình hoặc bean nào thay thế?
5. Repository cụ thể có nằm trong vùng quét và được tạo thành công không?

Một negative match không tự chứng minh có lỗi. Ví dụ, cấu hình MongoDB không phù hợp là bình thường trong ứng dụng chỉ dùng JPA.

Một negative match ở phần tạo mặc định cũng có thể là đúng, vì ứng dụng đã tự cung cấp thành phần tương ứng.

### 7.2. Positive match chưa phải kết quả cuối cùng

Một cấu hình phù hợp điều kiện nhưng repository có method query sai vẫn có thể làm khởi tạo bean thất bại.

Cần đọc tiếp exception có nguyên nhân gốc, thông tin quét repository và quá trình tạo bean. Báo cáo điều kiện giúp giải thích “vì sao cấu hình có hoặc không được áp dụng”, không thay thế toàn bộ chẩn đoán startup.

### 7.3. Ghi nhận môi trường gây lỗi

Khi so sánh máy phát triển, test và môi trường triển khai, cần xác định:

- Cùng module ứng dụng và dependency thực tế hay không.
- Profile, tham số khởi động và giá trị cấu hình có hiệu lực.
- Những cấu hình tường minh được import vào context.
- Artifact đang được chạy có phải bản dự kiến không.

Không suy luận từ một file YAML duy nhất nếu môi trường còn có biến môi trường, tham số dòng lệnh hoặc các nguồn cấu hình khác.

## 8. Khi nào cần tự cấu hình một phần?

Auto-configuration phù hợp với bố cục và nhu cầu thông thường. Những trường hợp sau thường cần quyết định rõ hơn:

| Trường hợp | Phần cần làm rõ |
| --- | --- |
| Repository nằm ngoài package mặc định. | Phạm vi quét repository. |
| Entity nằm ngoài package mặc định. | Phạm vi phát hiện entity. |
| Nhiều datasource hoặc persistence unit. | Bean hạ tầng và tập repository thuộc từng nguồn. |
| Đồng thời nhiều module Spring Data. | Repository nào được module nào quản lý. |
| Factory hoặc base implementation tùy biến. | Cấu hình factory và cách phần mặc định lùi lại. |
| Ứng dụng chủ động tắt auto-configuration repository. | Cấu hình thay thế và trách nhiệm mà ứng dụng nhận. |

### 8.1. Nhiều datasource không được phân công theo tên package một cách tự động

Có nhiều DataSource không có nghĩa Boot tự biết repository nào thuộc cơ sở dữ liệu nào chỉ từ tên thư mục hoặc tên interface.

Một cấu hình JPA tường minh có thể cần chỉ rõ:

~~~java
@EnableJpaRepositories(
    basePackages = "com.example.catalog.repository",
    entityManagerFactoryRef = "catalogEntityManagerFactory",
    transactionManagerRef = "catalogTransactionManager"
)
~~~

Đoạn trên chỉ minh họa phần liên kết repository. Các bean được tham chiếu phải được cấu hình thực sự và phải quản lý đúng entity, datasource tương ứng.

Một DataSource được chọn làm ứng viên mặc định hoặc primary không tự giải quyết toàn bộ bài toán nhiều persistence unit.

### 8.2. Nhiều module không làm mất ranh giới kho dữ liệu

JPA và MongoDB có thể cùng xuất hiện trong ứng dụng. Auto-configuration phù hợp cho cả hai không bảo đảm mọi repository chung đều được gán đúng theo ý định.

Cần xem interface chuyên biệt, annotation mapping domain và phạm vi cấu hình repository. Khi vùng quét chồng nhau hoặc domain mang dấu hiệu của nhiều công nghệ, hạ tầng có thể không xác định được module phù hợp.

Commons cung cấp nền tảng nhận diện và metadata; cấu hình ứng dụng vẫn phải làm rõ ranh giới.

### 8.3. Repository sẵn sàng không đồng nghĩa mọi tính năng đã bật

Auditing, phần mở rộng tùy biến, mapping đặc biệt hoặc các cơ chế riêng của module có thể cần cấu hình bổ sung.

Chẳng hạn, việc repository JPA được tự động tạo không tự chứng minh auditing JPA đã được kích hoạt đúng. Những annotation metadata như thời điểm tạo hoặc người sửa chỉ có tác dụng theo cơ chế tích hợp và cấu hình tương ứng.

## 9. Phân loại các lỗi thường gặp

| Hiện tượng | Hướng kiểm tra đầu tiên |
| --- | --- |
| Không có bean của interface repository. | Module trên classpath, vùng quét, thuộc tính bật/tắt và cấu hình tường minh. |
| Không cấu hình được datasource. | URL, driver, dependency cơ sở dữ liệu nhúng và giá trị cấu hình có hiệu lực. |
| JPA báo kiểu không được quản lý. | @Entity, namespace JPA, entity scanning và persistence unit liên quan. |
| Lỗi tạo query của repository. | Tên thuộc tính, chữ ký method và khả năng query của module. |
| Bean definition trùng hoặc có nhiều cấu hình repository chồng nhau. | Các vùng quét và cấu hình được import. |
| Có nhiều bean phù hợp để inject. | Kiểu bean thực tế, qualifier và thiết kế repository/datasource. |
| Ứng dụng khởi động nhưng lỗi khi gọi lần đầu. | Lazy bootstrap, mapping hoặc query chỉ được xác minh khi sử dụng. |
| NoSuchMethodError trong quá trình khởi tạo. | Bộ dependency và classpath runtime có tương thích hay không. |

Cách khoanh vùng nên đi từ nguyên nhân cụ thể:

~~~text
Không có bean?
    -> điều kiện và phạm vi đăng ký

Có bean definition nhưng tạo thất bại?
    -> factory, mapping, query hoặc hạ tầng

Tạo được nhưng gọi thất bại?
    -> truy cập dữ liệu, tải trì hoãn hoặc logic thực thi
~~~

Không thêm đồng thời nhiều annotation kích hoạt để thử cho đến khi ứng dụng chạy. Điều đó có thể làm vùng quét chồng nhau và che đi nguyên nhân cấu hình ban đầu.

## 10. Phân biệt môi trường test với ứng dụng đầy đủ

Một test slice cho JPA có tập auto-configuration và cấu hình kiểm thử riêng. Nó có thể dùng datasource, phạm vi context hoặc dữ liệu khác với ứng dụng đầy đủ.

Do đó:

- Test repository chạy được là bằng chứng cho ngữ cảnh test đó.
- Nó không tự chứng minh profile triển khai đang có cùng datasource và bộ dependency.
- Một test không tạo service cũng chưa kiểm chứng cách ứng dụng đầy đủ inject mọi thành phần.
- Việc lỗi chỉ xuất hiện khi chạy ứng dụng cần được điều tra với cấu hình thực sự của ứng dụng đó.

Khi đối chiếu kết quả, hãy ghi rõ đang kiểm tra đăng ký repository, khởi tạo proxy, truy cập cơ sở dữ liệu hay hành vi của một query cụ thể. Những mức kiểm chứng này có liên quan nhưng không đồng nhất.

## 11. Bài tập vận dụng

### Bài tập 1: Thiết kế package để dùng mặc định

Một ứng dụng có lớp khởi động ở `com.example.shop`. Hãy đặt service, repository và entity trong những package con để cơ chế mặc định có thể phát hiện các thành phần phù hợp.

Giải thích vì sao repository không cần một lớp implementation thủ công và vì sao entity không cần @Component.

### Bài tập 2: Tìm nguyên nhân khi service có nhưng repository không có

Lớp ứng dụng nằm ở `com.example.launcher`. Service, repository và entity nằm ở `com.acme.catalog`. Ứng dụng chỉ thêm scanBasePackages để quét `com.acme.catalog`.

Hãy chỉ ra:

1. Phạm vi nào đã được mở rộng.
2. Hai loại scanning nào chưa được cấu hình chỉ bằng thay đổi đó.
3. Có thể sửa bằng bố cục package hoặc cấu hình tường minh ra sao.

### Bài tập 3: Đọc một negative match

Báo cáo cho biết phần repository auto-configuration không áp dụng vì ứng dụng đã có cấu hình repository tương ứng.

Trước khi coi đây là lỗi, hãy tìm cấu hình thay thế và xác định nó có quét đúng repository hay không. Một phần mặc định lùi lại có thể là hành vi đúng của thiết kế.

### Bài tập 4: Phân biệt tự cấu hình và truy cập thành công

Một ứng dụng inject được repository nhưng lần gọi đầu mới phát sinh lỗi truy vấn. Hãy giải thích vì sao điều đó không mâu thuẫn với auto-configuration đã được áp dụng.

Xem xét bootstrap mode, thời điểm xác minh query và nguyên nhân gốc của lỗi.

Auto-configuration giúp nối các điều kiện phù hợp thành một cấu hình hoạt động. Để sử dụng cơ chế này đúng, cần nhìn rõ module nào cung cấp khả năng lưu trữ, repository nào nằm trong phạm vi đăng ký và cấu hình nào thực sự có hiệu lực khi ứng dụng chạy.