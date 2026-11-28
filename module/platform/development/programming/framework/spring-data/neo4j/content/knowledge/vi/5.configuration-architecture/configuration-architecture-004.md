# Cấu hình thủ công bằng AbstractNeo4jConfig

Spring Data Neo4j (SDN) cần một số thành phần hạ tầng để kết nối Neo4j, ánh xạ node và relationship thành đối tượng Java, thực thi repository và tham gia transaction của Spring. Khi dùng Spring Boot, phần lớn các bean này được tự động cấu hình từ dependency và thuộc tính kết nối. Trong một ứng dụng Spring Framework không dùng Spring Boot, bạn có thể tự khai báo cấu hình Java bằng cách kế thừa **AbstractNeo4jConfig**.

**AbstractNeo4jConfig** là lớp cấu hình nền cho **imperative SDN**. Nó cung cấp các bean hạ tầng mặc định và yêu cầu ứng dụng cung cấp Neo4j Java **Driver**. Cách làm này giữ cho cấu hình tập trung ở một nơi: thông tin kết nối, phạm vi quét entity, phạm vi quét repository và lựa chọn database đều có thể được kiểm soát rõ ràng.

Sau bài học, bạn có thể:

- Giải thích vai trò của **AbstractNeo4jConfig** trong một Spring context không dùng Spring Boot.
- Khai báo **Driver** và các annotation cần thiết để bật repository, transaction.
- Cấu hình package chứa node entity và repository.
- Chọn database mặc định và mở rộng cấu hình khi ứng dụng có yêu cầu riêng.
- Kiểm tra các lỗi thường gặp khi Spring context khởi tạo hoặc khi ứng dụng kết nối Neo4j.

## 1. Khi nào nên dùng AbstractNeo4jConfig?

Bạn có thể dùng SDN mà không cần Spring Boot. Trong Spring context thông thường, ứng dụng cần tự đăng ký các thành phần kết nối và tích hợp SDN với Spring. **AbstractNeo4jConfig** hỗ trợ trường hợp này bằng cách cung cấp một cấu hình nền có sẵn.

Lớp này phù hợp khi:

- Ứng dụng dùng Spring Framework nhưng không dùng Spring Boot.
- Ứng dụng cần tự quyết định cách tạo Neo4j Java Driver.
- Cấu trúc package hoặc lựa chọn database cần được khai báo rõ ràng.
- Nhóm phát triển muốn kiểm soát các bean hạ tầng thay vì dựa vào auto-configuration.

Nếu ứng dụng đã dùng Spring Boot, starter **spring-boot-starter-data-neo4j** thường là lựa chọn đơn giản hơn. Spring Boot có thể tự cấu hình Driver và các thành phần SDN từ cấu hình môi trường. Không nên đồng thời tạo các bean thủ công trùng với bean mà auto-configuration đã cung cấp, vì điều đó có thể gây xung đột hoặc khiến ứng dụng dùng nhầm cấu hình.

**AbstractNeo4jConfig** phục vụ mô hình imperative, trong đó repository và service thường trả về đối tượng hoặc collection thông thường. Nếu ứng dụng dùng reactive repositories và reactive transaction, hãy tìm hiểu **AbstractReactiveNeo4jConfig** cùng **@EnableReactiveNeo4jRepositories**; không trộn hai mô hình truy cập trong cùng một luồng xử lý.

## 2. Các thành phần hạ tầng mà lớp cấu hình cung cấp

SDN xây dựng nhiều mức truy cập trên Neo4j Java Driver:

1. **Driver** quản lý kết nối và connection pool đến máy chủ Neo4j.
2. **Neo4jClient** cung cấp API mức thấp hơn để chạy Cypher và làm việc với kết quả.
3. **Neo4jTemplate** hiểu metadata entity, hỗ trợ thao tác với đối tượng miền.
4. Repository cung cấp API lưu và truy vấn theo từng interface của miền nghiệp vụ.

Khi kế thừa **AbstractNeo4jConfig**, bạn cung cấp **Driver**; lớp cấu hình nền tạo các thành phần SDN cần thiết, trong đó có **Neo4jClient**, **Neo4jTemplate**, **Neo4jMappingContext**, **PlatformTransactionManager** và **Neo4jBookmarkManager**. Nó cũng có các điểm mở rộng như **DatabaseSelectionProvider**, **Neo4jConversions** và cấu hình Cypher-DSL.

| Thành phần | Vai trò |
|---|---|
| **Driver** | Kết nối đến Neo4j, quản lý pool và tạo session |
| **Neo4jClient** | Chạy Cypher trực tiếp, phù hợp với truy vấn tùy chỉnh mức thấp |
| **Neo4jTemplate** | Thao tác với dữ liệu đã được SDN ánh xạ |
| **Neo4jMappingContext** | Lưu metadata về node entity và cách ánh xạ property |
| **PlatformTransactionManager** | Đồng bộ transaction Neo4j với cơ chế transaction của Spring |
| **Neo4jBookmarkManager** | Quản lý bookmark để điều phối tính nhất quán khi làm việc với Neo4j |
| **DatabaseSelectionProvider** | Xác định database mà một thao tác sẽ sử dụng |

Bạn không cần tự khai báo lại toàn bộ các bean trên trong cấu hình thông thường. Hãy để lớp nền tạo các bean mặc định và chỉ override điểm mở rộng khi có yêu cầu cụ thể. Phương thức **driver()** là phần bắt buộc phải triển khai.

## 3. Khai báo cấu hình Java

Giả sử ứng dụng có các package:

~~~text
com.acme.graph
├── config
│   └── Neo4jManualConfiguration.java
├── domain
│   ├── Customer.java
│   └── Product.java
├── repository
│   └── CustomerRepository.java
└── service
    └── CustomerService.java
~~~

Lớp cấu hình có thể được viết như sau:

~~~java
package com.acme.graph.config;

import java.util.Collection;
import java.util.List;

import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.PropertySource;
import org.springframework.core.env.Environment;
import org.springframework.data.neo4j.config.AbstractNeo4jConfig;
import org.springframework.data.neo4j.core.DatabaseSelectionProvider;
import org.springframework.data.neo4j.repository.config.EnableNeo4jRepositories;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@PropertySource("classpath:neo4j.properties")
@EnableNeo4jRepositories(
    basePackages = "com.acme.graph.repository"
)
@EnableTransactionManagement
public class Neo4jManualConfiguration extends AbstractNeo4jConfig {

    private final Environment environment;

    public Neo4jManualConfiguration(Environment environment) {
        this.environment = environment;
    }

    @Bean(destroyMethod = "close")
    @Override
    public Driver driver() {
        String uri = environment.getRequiredProperty("app.neo4j.uri");
        String username = environment.getRequiredProperty("app.neo4j.username");
        String password = environment.getRequiredProperty("app.neo4j.password");

        return GraphDatabase.driver(
            uri,
            AuthTokens.basic(username, password)
        );
    }

    @Override
    protected Collection<String> getMappingBasePackages() {
        return List.of("com.acme.graph.domain");
    }

    @Bean
    @Override
    protected DatabaseSelectionProvider databaseSelectionProvider() {
        String database = environment.getProperty(
            "app.neo4j.database",
            "neo4j"
        );

        return DatabaseSelectionProvider
            .createStaticDatabaseSelectionProvider(database);
    }
}
~~~

Ví dụ này dùng **Environment** để đọc thuộc tính, nhờ đó không phải gắn username hoặc password trực tiếp vào mã nguồn. **@PropertySource** nạp file thuộc tính trên classpath. Nội dung file **neo4j.properties** có thể là:

~~~properties
app.neo4j.uri=bolt://localhost:7687
app.neo4j.username=neo4j
app.neo4j.database=neo4j
~~~

Mật khẩu được đọc từ thuộc tính **app.neo4j.password**. Có thể cung cấp thuộc tính này từ biến môi trường **APP_NEO4J_PASSWORD** hoặc một secret manager được tích hợp vào Spring Environment. Trong môi trường triển khai, không commit mật khẩu vào repository. Giá trị URI local ở ví dụ chỉ dành cho phát triển; nếu Neo4j yêu cầu TLS hoặc dùng cơ chế routing, chọn URI scheme tương ứng với hạ tầng, chẳng hạn scheme bảo mật hoặc scheme routing mà máy chủ hỗ trợ.

### 3.1. Vì sao cần từng annotation?

- **@Configuration** đăng ký lớp này như một nguồn định nghĩa bean của Spring.
- **@PropertySource** đưa cấu hình kết nối từ file thuộc tính vào **Environment**.
- **@EnableNeo4jRepositories** kích hoạt việc quét và tạo implementation cho repository interface trong package đã chỉ định.
- **@EnableTransactionManagement** bật cơ chế proxy để các lời gọi **@Transactional** được quản lý bởi transaction manager.
- **@Bean** đăng ký Driver vào Spring container. **destroyMethod = "close"** yêu cầu Spring đóng Driver khi context dừng.

**Driver** là đối tượng dùng chung cho ứng dụng và có connection pool nội bộ. Không tạo một Driver mới cho mỗi request hoặc mỗi repository method. Session được tạo cho từng đơn vị thao tác và cần được đóng sau khi dùng; hãy để các API SDN quản lý vòng đời session khi làm việc qua repository, template hoặc client.

## 4. Khai báo phạm vi quét entity và repository

Hai phạm vi quét có mục đích khác nhau:

**Repository scanning** do **@EnableNeo4jRepositories** điều khiển. **basePackages** trỏ đến package chứa các interface như **CustomerRepository**. Nếu repository nằm ngoài package đã khai báo, Spring sẽ không tạo bean cho interface đó và ứng dụng có thể báo lỗi không tìm thấy bean khi inject.

**Entity scanning** do **getMappingBasePackages()** điều khiển. **AbstractNeo4jConfig** dùng các package này để tìm lớp được đánh dấu **@Node** và xây dựng metadata trong **Neo4jMappingContext**. Mặc định, lớp nền dựa vào package của lớp cấu hình cụ thể. Khi entity nằm trong package khác, hãy override phương thức như ví dụ để khai báo đúng vị trí.

Ví dụ, repository có thể được khai báo:

~~~java
package com.acme.graph.repository;

import org.springframework.data.neo4j.repository.Neo4jRepository;

import com.acme.graph.domain.Customer;

public interface CustomerRepository
        extends Neo4jRepository<Customer, Long> {
}
~~~

Nếu entity nằm trong nhiều package, trả về tất cả các package cần quét:

~~~java
@Override
protected Collection<String> getMappingBasePackages() {
    return List.of(
        "com.acme.graph.domain.customer",
        "com.acme.graph.domain.catalog"
    );
}
~~~

Đừng nhầm package quét repository với package quét entity. Repository là các interface truy cập dữ liệu; entity là các lớp mô tả node trong đồ thị. Cả hai phải được Spring Data Neo4j nhận diện đúng thì ứng dụng mới tạo được repository và ánh xạ được dữ liệu trả về.

## 5. Chọn database cho ứng dụng

Neo4j có thể có nhiều database trong cùng một DBMS. Nếu không chỉ định, SDN sử dụng database mặc định theo cấu hình của hệ thống Neo4j. **DatabaseSelectionProvider** cho phép chỉ định database mà các thao tác SDN sẽ sử dụng.

Trong ví dụ cấu hình, provider được tạo bằng:

~~~java
DatabaseSelectionProvider.createStaticDatabaseSelectionProvider("neo4j")
~~~

Đây là lựa chọn tĩnh: mọi thao tác sử dụng provider này sẽ nhắm đến database đã chỉ định. Nếu ứng dụng chỉ dùng database mặc định, có thể giữ provider mặc định mà **AbstractNeo4jConfig** cung cấp và bỏ phương thức override.

Với ứng dụng cần chọn database theo tenant hoặc theo ngữ cảnh request, không nên thay tên database bằng cách ghép chuỗi tùy tiện vào Cypher. Hãy thiết kế một **DatabaseSelectionProvider** phù hợp, xác định rõ nguồn dữ liệu tenant, kiểm tra quyền truy cập và bảo đảm database được chọn nhất quán trong toàn bộ transaction. Cơ chế chọn database động cần được thiết kế riêng; ví dụ provider tĩnh ở trên không thực hiện việc định tuyến theo tenant.

## 6. Transaction trong cấu hình thủ công

**AbstractNeo4jConfig** cung cấp **PlatformTransactionManager** dựa trên Driver mà bạn khai báo. Khi bật **@EnableTransactionManagement**, Spring có thể áp dụng transaction cho service method được đánh dấu **@Transactional**.

Ví dụ, một nghiệp vụ tạo liên kết mua hàng có thể đặt thao tác lưu object graph vào ranh giới transaction ở service:

~~~java
package com.acme.graph.service;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.acme.graph.domain.Customer;
import com.acme.graph.domain.Product;
import com.acme.graph.repository.CustomerRepository;

@Service
public class CustomerService {

    private final CustomerRepository customerRepository;

    public CustomerService(CustomerRepository customerRepository) {
        this.customerRepository = customerRepository;
    }

    @Transactional
    public Customer registerPurchase(
            Customer customer,
            Product product) {
        // Giả sử customer.addPurchase cập nhật relationship
        // PURCHASED trong object graph của Customer.
        customer.addPurchase(product, 1);
        return customerRepository.save(customer);
    }
}
~~~

Ví dụ giả định entity **Customer** có phương thức miền **addPurchase** để thêm relationship **PURCHASED** vào object graph trước khi lưu. Repository lưu graph theo mapping đã khai báo. Trong nghiệp vụ có nhiều thao tác lưu hoặc đọc liên quan, hãy đặt ranh giới transaction ở service để các thao tác cùng tham gia một đơn vị công việc. Nếu một thao tác trong transaction thất bại và exception được truyền ra ngoài theo quy tắc rollback của Spring, các thay đổi thuộc transaction đó sẽ được rollback. Điều này giúp tránh trạng thái nghiệp vụ chỉ được ghi một nửa.

Không phải mọi thao tác dùng Driver trực tiếp đều tự động tham gia transaction Spring đang mở. Nếu lấy **Driver** và tự tạo session/transaction, bạn phải hiểu rõ cách quản lý transaction của Neo4j Java Driver và cách đồng bộ với transaction hiện tại. Khi cần tích hợp transaction Spring, ưu tiên repository, **Neo4jTemplate** hoặc **Neo4jClient** được cấu hình bởi SDN.

## 7. Các điểm mở rộng của AbstractNeo4jConfig

Ngoài **driver()** và **getMappingBasePackages()**, lớp cấu hình nền còn cung cấp một số phương thức để điều chỉnh hành vi khi cần:

| Phương thức | Khi nào cần override |
|---|---|
| **databaseSelectionProvider()** | Chọn database khác mặc định hoặc xây dựng chính sách chọn database |
| **neo4jConversions()** | Đăng ký converter cho kiểu dữ liệu miền cần chuyển đổi riêng |
| **cypherDslConfiguration()** | Chọn cấu hình hoặc dialect cho Cypher-DSL khi ứng dụng dùng thư viện này |
| **getMappingBasePackages()** | Entity nằm ngoài package mặc định của lớp cấu hình |

Chỉ override khi có yêu cầu cụ thể. Chẳng hạn, nếu một kiểu thuộc tính miền không được SDN ánh xạ theo cách mong muốn, hãy tìm hiểu custom conversion trước khi tự thay thế toàn bộ **Neo4jMappingContext**. Nếu chỉ cần đổi database, override **DatabaseSelectionProvider**; không cần tự viết lại **Neo4jClient** hay **Neo4jTemplate**.

Khi cần cấu hình driver nâng cao, Neo4j Java Driver cho phép truyền **Config** vào **GraphDatabase.driver(...)** để điều chỉnh connection pool, timeout và các tùy chọn kết nối khác. Hãy chọn giá trị theo tải thực tế và giới hạn tài nguyên của Neo4j server. Không nên tăng connection pool tùy tiện vì số kết nối đồng thời còn phụ thuộc vào năng lực máy chủ và số instance ứng dụng.

## 8. Kiểm tra cấu hình và xử lý lỗi

Sau khi tạo Spring context, hãy kiểm tra theo thứ tự từ hạ tầng đến tầng truy cập dữ liệu:

1. Xác nhận file thuộc tính đã được nạp và URI, username, password có giá trị.
2. Xác nhận Driver tạo được kết nối đến đúng máy chủ Neo4j.
3. Kiểm tra database được chọn có tồn tại và tài khoản có quyền truy cập.
4. Kiểm tra package entity được quét, các lớp **@Node** có metadata hợp lệ.
5. Kiểm tra repository interface nằm trong package đã khai báo ở **@EnableNeo4jRepositories**.
6. Thực hiện một truy vấn đọc đơn giản qua **Neo4jClient** hoặc repository để xác nhận toàn bộ chuỗi cấu hình.

Một truy vấn kiểm tra kết nối ở mức Cypher có thể là:

~~~cypher
RETURN 1 AS connectivityCheck
~~~

Các lỗi thường gặp:

| Triệu chứng | Nguyên nhân cần kiểm tra |
|---|---|
| Lỗi xác thực khi khởi tạo kết nối | Username/password sai, secret chưa được nạp hoặc tài khoản bị giới hạn |
| Không thể kết nối máy chủ | URI, cổng, DNS, firewall, TLS hoặc trạng thái Neo4j server |
| Không tìm thấy repository bean | Sai **basePackages** hoặc chưa bật **@EnableNeo4jRepositories** |
| Entity không được nhận diện | Package trong **getMappingBasePackages()** không chứa lớp **@Node** |
| Không dùng được **@Transactional** | Thiếu **@EnableTransactionManagement**, service không đi qua Spring proxy hoặc transaction manager không được đăng ký |
| Truy vấn chạy trên database khác dự kiến | Kiểm tra database mặc định và **DatabaseSelectionProvider** |

Với ứng dụng chạy lâu dài, nên có kiểm tra sức khỏe kết nối và log lỗi đủ ngữ cảnh nhưng không ghi password, token hoặc dữ liệu nhạy cảm. Khi đóng Spring context, Driver phải được đóng để giải phóng pool và tài nguyên kết nối.

## 9. Tự kiểm tra

1. Vì sao **AbstractNeo4jConfig** yêu cầu ứng dụng triển khai **driver()**?
2. **@EnableNeo4jRepositories** và **getMappingBasePackages()** kiểm soát hai phạm vi quét nào?
3. Lớp cấu hình nền tạo những thành phần nào để SDN làm việc với repository và transaction?
4. Khi ứng dụng dùng database khác database mặc định, vai trò của **DatabaseSelectionProvider** là gì?
5. Vì sao không nên tạo một Neo4j **Driver** mới cho mỗi request?

**Bài tập thực hành:** Tạo một Spring context không dùng Spring Boot cho ứng dụng quản lý thư viện đồ thị. Viết lớp **LibraryNeo4jConfig** kế thừa **AbstractNeo4jConfig**, đọc URI và thông tin xác thực từ file thuộc tính hoặc biến môi trường, bật repository scanning, chỉ định package chứa các lớp **@Node**, và cấu hình database **library**. Tạo một service có phương thức **@Transactional** lưu một thực thể cùng relationship liên quan. Cuối cùng, khởi tạo Spring context, chạy truy vấn **RETURN 1 AS connectivityCheck** và gọi một repository method để xác nhận cấu hình hoạt động.

## Tài liệu tham khảo

- [Spring Data Neo4j Reference Documentation — Using Spring Data Neo4j without Spring Boot](https://docs.spring.io/spring-data/data-graph/docs/7.1.x/reference/html/)
- [Spring Data Neo4j API — AbstractNeo4jConfig](https://docs.spring.io/spring-data/data-neo4j/docs/current/api/org/springframework/data/neo4j/config/AbstractNeo4jConfig.html)
- [Neo4j Java Driver Manual](https://neo4j.com/docs/java-manual/current/)
