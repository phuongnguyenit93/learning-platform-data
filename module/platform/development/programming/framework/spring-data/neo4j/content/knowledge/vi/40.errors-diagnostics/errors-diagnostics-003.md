# Không tìm thấy repository hoặc quét nhầm loại repository

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Phân biệt lỗi repository không được phát hiện với lỗi repository bị gắn nhầm Spring Data module.
- Xác định package scan mặc định của Spring Boot và phạm vi scan của `@EnableNeo4jRepositories`.
- Cấu hình package repository bằng `basePackages` hoặc `basePackageClasses`.
- Phân biệt repository scanning với entity scanning.
- Khai báo repository theo kiểu Neo4j để tránh mơ hồ khi classpath có nhiều Spring Data module.
- Sử dụng `@NoRepositoryBean` đúng cách cho generic base repository.
- Phát hiện package scan chồng lấn, filter loại nhầm repository và cấu hình auto-configuration bị vô hiệu hóa.
- Chẩn đoán lỗi bằng log khởi động, condition evaluation report và kiểm tra ApplicationContext.

## 1. Nhận diện hai nhóm lỗi khác nhau

Khi Spring Data Neo4j (SDN) không tạo được repository bean, lỗi thường thuộc một trong hai nhóm:

**Repository không được phát hiện**

Spring không tạo bean cho interface repository. Khi inject vào service hoặc test, ứng dụng có thể báo:

```text
NoSuchBeanDefinitionException:
No qualifying bean of type 'com.example.graph.PersonRepository' available
```

Nguyên nhân thường nằm ở package scan, cấu hình repository, dependency hoặc filter.

**Repository được phát hiện nhưng gắn nhầm store**

Ứng dụng có nhiều Spring Data module, chẳng hạn JPA và Neo4j. Một repository dùng interface chung như `CrudRepository` có thể không xác định rõ thuộc module nào. Spring Data chuyển sang strict repository configuration mode để phân loại repository. Nếu thông tin về repository và domain class không đủ rõ, repository có thể bị bỏ qua hoặc cấu hình không đúng store.

Hai lỗi này cần cách kiểm tra khác nhau. Nếu bean hoàn toàn không tồn tại, hãy kiểm tra scan trước. Nếu log nói nhiều store module cùng tồn tại hoặc repository không xác định được store, hãy kiểm tra kiểu repository và annotation trên domain class.

## 2. Spring Boot quét repository từ package nào?

Khi dùng Spring Boot, auto-configuration mặc định quét các repository trong auto-configuration packages. Thông thường, package gốc được lấy từ class có `@SpringBootApplication` hoặc `@EnableAutoConfiguration`.

Ví dụ cấu trúc:

```text
com.example.app
├── Application.java
├── domain
│   └── Person.java
└── repository
    └── PersonRepository.java
```

Nếu `Application.java` nằm trong package `com.example.app`, các package con `domain` và `repository` nằm trong phạm vi mặc định.

Ví dụ class khởi động:

```java
package com.example.app;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {

    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

Một lỗi phổ biến là đặt class khởi động quá sâu:

```text
com.example.app.bootstrap
└── Application.java

com.example.app.graph.repository
└── PersonRepository.java
```

Package `com.example.app.bootstrap` không bao phủ package anh em `com.example.app.graph.repository`. Auto-configuration package mặc định không quét ngược lên package cha rồi đi xuống các nhánh khác.

Cách sửa thường dùng là đặt class khởi động tại package gốc chung:

```text
com.example.app
├── Application.java
├── bootstrap
└── graph
    └── repository
```

Nếu không thể thay đổi vị trí class khởi động, khai báo repository package tường minh bằng `@EnableNeo4jRepositories`.

## 3. Phạm vi mặc định của @EnableNeo4jRepositories

`@EnableNeo4jRepositories` kích hoạt repository infrastructure của SDN. Khi không khai báo `value`, `basePackages` hoặc `basePackageClasses`, Spring quét package chứa class cấu hình được gắn annotation.

Ví dụ:

```java
package com.example.app.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.repository.config.EnableNeo4jRepositories;

@Configuration
@EnableNeo4jRepositories
public class Neo4jRepositoryConfiguration {
}
```

Trong ví dụ này, package được quét mặc định là `com.example.app.config`, không phải tự động là toàn bộ `com.example.app`.

Nếu repository nằm ở `com.example.app.graph.repository`, cần chỉ rõ package:

```java
@Configuration
@EnableNeo4jRepositories(
    basePackages = "com.example.app.graph.repository"
)
public class Neo4jRepositoryConfiguration {
}
```

Có thể truyền nhiều package:

```java
@Configuration
@EnableNeo4jRepositories(
    basePackages = {
        "com.example.app.graph.person",
        "com.example.app.graph.organization"
    }
)
public class Neo4jRepositoryConfiguration {
}
```

`value` là alias của `basePackages`, vì vậy không khai báo đồng thời cả hai thuộc tính trong cùng annotation.

## 4. Dùng basePackageClasses để tránh sai tên package

Chuỗi package trong `basePackages` dễ sai khi refactor. SDN hỗ trợ `basePackageClasses` như một cách khai báo an toàn theo kiểu Java.

Tạo marker interface trong package repository:

```java
package com.example.app.graph.repository;

public interface Neo4jRepositoryPackage {
}
```

Dùng marker class:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.repository.config.EnableNeo4jRepositories;

@Configuration
@EnableNeo4jRepositories(
    basePackageClasses = Neo4jRepositoryPackage.class
)
public class Neo4jRepositoryConfiguration {
}
```

Spring sẽ quét package chứa `Neo4jRepositoryPackage` và các package con. Marker không cần chứa method hay logic nghiệp vụ.

Có thể dùng chính repository interface làm marker:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.repository.config.EnableNeo4jRepositories;

@EnableNeo4jRepositories(
    basePackageClasses = PersonRepository.class
)
@Configuration
public class Neo4jRepositoryConfiguration {
}
```

Cách này phù hợp nếu package của repository interface chính là package cần quét. Nếu cần quét nhiều package, truyền nhiều marker class.

## 5. Phân biệt repository scanning và entity scanning

Hai cơ chế này có mục đích khác nhau:

| Cơ chế | Thành phần được tìm | Annotation/cấu hình |
| --- | --- | --- |
| Repository scanning | Interface repository cần tạo proxy bean | `@EnableNeo4jRepositories` hoặc Boot auto-configuration |
| Entity scanning | Domain class cần mapping | `@Node`, `@RelationshipProperties` và cấu hình `@EntityScan` khi cần |

`@EntityScan` không thay thế `@EnableNeo4jRepositories`. Nếu `Person` được phát hiện nhưng `PersonRepository` nằm ngoài package scan, repository bean vẫn không được tạo.

Ngược lại, nếu repository đã được tạo nhưng SDN không ánh xạ được domain class hoặc relationship properties, hãy kiểm tra mapping context và entity scanning.

Ví dụ entity:

```java
package com.example.app.graph.domain;

import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    private Long id;

    private String name;

    protected Person() {
    }

    public Person(Long id, String name) {
        this.id = id;
        this.name = name;
    }
}
```

Repository:

```java
package com.example.app.graph.repository;

import org.springframework.data.neo4j.repository.Neo4jRepository;
import com.example.app.graph.domain.Person;

public interface PersonRepository
        extends Neo4jRepository<Person, Long> {
}
```

Nếu domain nằm ngoài auto-configuration packages, có thể cấu hình entity scan riêng bằng `@EntityScan(basePackageClasses = Person.class)` theo phiên bản Spring Boot đang dùng.

## 6. Repository nên mở rộng Neo4jRepository

Khi chỉ dùng một Spring Data module, repository mở rộng `CrudRepository` có thể hoạt động vì chỉ có một repository factory phù hợp trên classpath. Nhưng trong ứng dụng có nhiều module, nên khai báo rõ store mà repository thuộc về.

Repository Neo4j:

```java
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface PersonRepository
        extends Neo4jRepository<Person, Long> {
}
```

Repository JPA:

```java
import org.springframework.data.jpa.repository.JpaRepository;

public interface PersonJpaRepository
        extends JpaRepository<PersonEntity, Long> {
}
```

Các interface store-specific giúp Spring Data nhận biết repository nào thuộc Neo4j và repository nào thuộc JPA.

Không nên dùng cùng một interface chung để cố gắng đại diện cho hai persistence technology. Mỗi store có repository factory, mapping và transaction semantics riêng.

## 7. Strict repository configuration mode khi có nhiều Spring Data module

Khi classpath chứa nhiều repository factory, Spring Data chuyển sang strict repository configuration mode. Ví dụ phổ biến là ứng dụng có cả:

- Spring Data Neo4j.
- Spring Data JPA.
- Spring Data MongoDB.
- Spring Data Redis.

Strict mode dùng thông tin repository và domain class để xác định store phù hợp.

Có hai tín hiệu chính:

1. Repository mở rộng interface đặc thù của module, ví dụ `Neo4jRepository` hoặc `JpaRepository`.
2. Domain class mang annotation đặc thù của module, ví dụ `@Node` của SDN hoặc `@Entity` của JPA.

Nếu repository chỉ mở rộng `Repository<T, ID>` hoặc `CrudRepository<T, ID>`, đồng thời domain class không có annotation phân biệt store, Spring Data không thể xác định chắc chắn repository thuộc module nào.

Ví dụ dễ gây mơ hồ:

```java
import org.springframework.data.repository.CrudRepository;

public interface PersonRepository
        extends CrudRepository<Person, Long> {
}
```

Nếu classpath chỉ có một Spring Data module, interface trên có thể được bind vào module đó. Khi nhiều module cùng hiện diện, đừng dựa vào hành vi này. Hãy dùng `Neo4jRepository` hoặc bảo đảm domain class có annotation `@Node` phù hợp và không bị gắn annotation store khác gây xung đột.

## 8. Tránh domain class có annotation của nhiều store

Một domain class được gắn cả annotation JPA và SDN có thể làm strict mode mất khả năng phân biệt nếu repository chỉ dùng interface chung.

Ví dụ không nên dùng khi repository cần được phân loại tự động:

```java
import jakarta.persistence.Entity;
import org.springframework.data.neo4j.core.schema.Node;

@Entity
@Node("Person")
public class Person {
    // ...
}
```

Nếu cùng class mang cả `@Entity` và `@Node`, một repository generic có thể là ứng viên của nhiều store. Spring Data không thể suy ra duy nhất module cần sử dụng.

Nên tách domain model theo persistence technology:

```text
com.example.app
├── graph
│   ├── domain
│   │   └── PersonNode.java
│   └── repository
│       └── PersonGraphRepository.java
└── relational
    ├── domain
    │   └── PersonEntity.java
    └── repository
        └── PersonJpaRepository.java
```

Nếu có lý do nghiệp vụ để chia sẻ model, cần cấu hình repository package và store-specific interface rõ ràng, đồng thời hiểu rõ giới hạn mapping của từng module.

## 9. Dùng @NoRepositoryBean cho generic base repository

Ứng dụng thường tạo base repository để chia sẻ method hoặc convention giữa nhiều repository. Spring Data không nên tạo bean cho interface trung gian còn giữ generic type variable.

Dùng `@NoRepositoryBean`:

```java
import org.springframework.data.repository.NoRepositoryBean;
import org.springframework.data.neo4j.repository.Neo4jRepository;

@NoRepositoryBean
public interface BaseGraphRepository<T, ID>
        extends Neo4jRepository<T, ID> {
}
```

Repository cụ thể kế thừa base interface:

```java
public interface PersonRepository
        extends BaseGraphRepository<Person, Long> {
}
```

Ở đây:

- `BaseGraphRepository` là interface trung gian, không được tạo bean trực tiếp.
- `PersonRepository` cung cấp domain type cụ thể `Person` và ID type `Long`.
- Vì base interface mở rộng `Neo4jRepository`, repository cụ thể vẫn có dấu hiệu store-specific của SDN.

Nếu quên `@NoRepositoryBean`, Spring có thể cố tạo repository cho interface generic và không xác định được domain type thực tế. Nếu gắn nhầm annotation này lên repository cụ thể, Spring sẽ bỏ qua repository đó.

## 10. Package repository chồng lấn giữa các store

Trong ứng dụng dùng JPA và Neo4j, không nên cấu hình cả hai module quét cùng một package rộng.

Ví dụ cấu hình dễ gây vấn đề:

```java
@EnableJpaRepositories(
    basePackages = "com.example.app"
)
@EnableNeo4jRepositories(
    basePackages = "com.example.app"
)
@Configuration
public class PersistenceConfiguration {
}
```

Hai registrar có thể cùng nhìn thấy các repository interface trong cùng phạm vi. Nếu interface không có dấu hiệu store rõ ràng, có thể phát sinh cảnh báo strict mode, repository bị bỏ qua hoặc bean registration xung đột.

Tách package theo store:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;
import org.springframework.data.neo4j.repository.config.EnableNeo4jRepositories;

@Configuration
@EnableJpaRepositories(
    basePackages = "com.example.app.relational.repository"
)
@EnableNeo4jRepositories(
    basePackages = "com.example.app.graph.repository"
)
public class PersistenceConfiguration {
}
```

Cấu trúc package:

```text
com.example.app
├── graph
│   └── repository
│       └── PersonGraphRepository.java
└── relational
    └── repository
        └── PersonJpaRepository.java
```

Nếu cần nhiều cấu hình repository Neo4j, bảo đảm các package được chia có chủ đích và không đăng ký cùng interface qua nhiều registrar.

## 11. Kiểm tra includeFilters, excludeFilters và nested repository

`@EnableNeo4jRepositories` hỗ trợ `includeFilters` và `excludeFilters` để tinh chỉnh tập interface được phát hiện.

Một filter include có thể thu hẹp tập ứng viên hơn nữa. Nếu filter không khớp repository nào, kết quả là không có repository bean được đăng ký.

Ví dụ minh họa loại repository cụ thể:

```java
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.FilterType;

@Configuration
@EnableNeo4jRepositories(
    basePackages = "com.example.app.graph.repository",
    excludeFilters = @ComponentScan.Filter(
        type = FilterType.REGEX,
        pattern = ".*LegacyRepository"
    )
)
public class Neo4jRepositoryConfiguration {
}
```

Nếu không có yêu cầu lọc đặc biệt, hãy bỏ filter và dùng package scan đơn giản. Khi repository biến mất sau một thay đổi cấu hình, kiểm tra lại các filter trước khi sửa domain model.

Các repository interface khai báo lồng bên trong class cũng cần lưu ý. Thuộc tính `considerNestedRepositories` mặc định là `false`; nếu chủ ý đặt repository trong class khác, bật thuộc tính này hoặc chuyển interface thành top-level type:

```java
@EnableNeo4jRepositories(
    basePackages = "com.example.app.graph.repository",
    considerNestedRepositories = true
)
@Configuration
public class Neo4jRepositoryConfiguration {
}
```

Thông thường, top-level repository interface dễ tìm kiếm, kiểm thử và tổ chức package hơn.

## 12. Kiểm tra dependency và auto-configuration

Repository scanning chỉ hoạt động khi repository infrastructure của SDN có mặt trên classpath và cấu hình được kích hoạt.

Với Spring Boot, dependency thường dùng là:

```gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-neo4j")
}
```

Nếu quản lý dependency bằng Spring Boot plugin hoặc BOM, để dependency management chọn phiên bản tương thích. Tránh khai báo thủ công các phiên bản Spring Data Neo4j, Spring Data Commons và Spring Boot không tương thích với nhau.

Kiểm tra các điểm sau:

- Starter hoặc `spring-data-neo4j` có trong runtime classpath.
- Repository interface mở rộng API đúng của phiên bản SDN.
- Không loại repository auto-configuration bằng cấu hình tùy chỉnh.
- Không vô tình exclude `Neo4jRepositoriesAutoConfiguration` khi dùng Boot auto-configuration.
- Không khai báo một cấu hình thủ công khác khiến package scan hoặc repository infrastructure bị thay thế ngoài dự kiến.
- Các profile và conditional configuration chứa `@EnableNeo4jRepositories` có thực sự được kích hoạt.

Nếu ứng dụng tự cấu hình SDN thay vì dùng Boot auto-configuration, cần khai báo repository scanning và hạ tầng tương ứng một cách rõ ràng.

## 13. Phân biệt lỗi repository với lỗi kết nối Neo4j

Không phải mọi lỗi liên quan Neo4j đều là lỗi repository scan.

| Dấu hiệu | Khả năng nguyên nhân |
| --- | --- |
| `NoSuchBeanDefinitionException` cho `PersonRepository` | Repository chưa được phát hiện hoặc bị loại khỏi scan |
| Log strict repository configuration nói không xác định được store | Interface generic hoặc domain annotation mơ hồ |
| `Not a managed type` hoặc lỗi mapping tương đương | Domain class chưa được nhận diện/ánh xạ đúng hoặc dùng sai API theo phiên bản |
| `No qualifying bean` cho `Neo4jClient` hoặc `Neo4jTemplate` | Neo4j data auto-configuration hoặc bean hạ tầng chưa được tạo |
| Lỗi authentication/connection refused khi gọi method repository | Repository bean đã tồn tại nhưng Driver không kết nối được Neo4j |
| Lỗi query/unknown property khi gọi method | Repository đã được tạo; cần kiểm tra derived query, mapping hoặc Cypher |

Nếu Spring khởi động và inject được repository nhưng method gọi tới Neo4j thất bại vì URI, credential hoặc database, đó là lỗi kết nối/runtime. Sửa package scan sẽ không giải quyết được lỗi này.

## 14. Quy trình chẩn đoán từng bước

Khi gặp lỗi không tìm thấy repository, hãy kiểm tra theo thứ tự:

1. **Xác nhận dependency:** kiểm tra starter SDN hoặc thư viện SDN có trong runtime classpath.
2. **Xác định package gốc:** tìm class `@SpringBootApplication` và package chứa repository.
3. **Kiểm tra package scan mặc định:** repository có nằm trong auto-configuration packages không?
4. **Kiểm tra cấu hình thủ công:** nếu có `@EnableNeo4jRepositories`, package mặc định là package của class cấu hình đó trừ khi đã chỉ định base package.
5. **Dùng marker class:** chuyển sang `basePackageClasses` để tránh chuỗi package sai.
6. **Kiểm tra domain mapping:** entity có được khai báo bằng `@Node` phù hợp và được mapping context nhận biết không?
7. **Kiểm tra strict mode:** repository có mở rộng `Neo4jRepository` hoặc domain type có annotation `@Node` không?
8. **Kiểm tra generic base:** interface trung gian có `@NoRepositoryBean` chưa?
9. **Kiểm tra package chồng lấn:** JPA, MongoDB hoặc store khác có quét cùng package không?
10. **Kiểm tra filter và nested type:** include/exclude filters có loại nhầm interface không; repository lồng có cần `considerNestedRepositories` không?
11. **Kiểm tra profile/condition:** cấu hình repository có bị vô hiệu hóa bởi profile hoặc conditional bean không?
12. **Kiểm tra context:** xác nhận repository bean có trong ApplicationContext trước khi điều tra kết nối database.

Không thay đổi nhiều cấu hình cùng lúc. Mỗi lần chỉ sửa một nguyên nhân nghi ngờ và khởi động lại context để xác nhận.

## 15. Đọc log và condition evaluation report

Khi dùng Spring Boot, chạy ứng dụng với tùy chọn `--debug` để hiển thị condition evaluation report. Report giúp xác định auto-configuration nào được áp dụng, bị bỏ qua hoặc không thỏa điều kiện.

Ví dụ:

```bash
./gradlew bootRun --args='--debug'
```

Với ứng dụng đóng gói:

```bash
java -jar app.jar --debug
```

Tìm các thông tin liên quan:

- Neo4j repository auto-configuration có được áp dụng không.
- Có cấu hình nào đã cung cấp repository infrastructure khiến auto-configuration lùi lại không.
- Driver, client và template có được tạo không.
- Package repository nào đang được scan.
- Log strict repository configuration có xuất hiện không.
- Repository cụ thể được nhận diện là candidate của module nào.

Condition evaluation report giải thích quyết định auto-configuration. Nó không thay thế việc kiểm tra package scan do `@EnableNeo4jRepositories` hoặc custom registrar thực hiện.

Trong ứng dụng có Actuator, endpoint `conditions` có thể hỗ trợ quan sát condition report nếu endpoint được bật và được bảo vệ phù hợp. Không công khai endpoint diagnostics ra mạng không tin cậy.

## 16. Kiểm tra repository bean trong ApplicationContext

Có thể viết một test context nhỏ để xác nhận repository đã được đăng ký:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

@SpringBootTest
class RepositoryRegistrationTest {

    @Autowired
    ApplicationContext context;

    @Test
    void registersPersonRepository() {
        assertThat(context.getBeansOfType(PersonRepository.class))
            .hasSize(1);
    }
}
```

Nếu muốn kiểm tra đúng bean name:

```java
assertThat(context.containsBean("personRepository")).isTrue();
```

Tên bean mặc định thường được suy ra từ tên interface theo quy tắc bean naming của Spring Data, nhưng khi chẩn đoán nên kiểm tra theo type trước để tránh phụ thuộc vào tên.

Test context không nhất thiết phải gọi database nếu mục tiêu chỉ là xác nhận repository proxy được đăng ký. Nếu test dùng `@DataNeo4jTest`, cần cấu hình Neo4j test database theo đúng yêu cầu của test slice.

## 17. Bảng tổng hợp nguyên nhân và cách sửa

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Repository nằm ngoài package của Application | Auto-configuration package quá hẹp | Đặt main class ở package gốc hoặc dùng `@EnableNeo4jRepositories` |
| Repository nằm ngoài package của config class | `@EnableNeo4jRepositories` không có base package | Chỉ rõ `basePackages` hoặc `basePackageClasses` |
| Entity scan đúng nhưng repository không có | Nhầm entity scan với repository scan | Cấu hình `@EnableNeo4jRepositories` |
| Repository generic bị bỏ qua | Strict mode không xác định được store | Mở rộng `Neo4jRepository` |
| Domain class không phân biệt store | Thiếu `@Node` hoặc có annotation store mơ hồ | Dùng annotation SDN và model riêng |
| Generic base repository bị tạo bean | Thiếu `@NoRepositoryBean` | Đánh dấu interface trung gian |
| Repository lồng không được tìm thấy | `considerNestedRepositories` mặc định false | Bật thuộc tính hoặc chuyển thành top-level interface |
| Repository biến mất sau khi thêm filter | `includeFilters` hoặc `excludeFilters` không đúng | Bỏ filter hoặc sửa pattern |
| JPA và Neo4j cùng scan một package | Package scan chồng lấn | Tách package theo store |
| Không có Neo4j repository infrastructure | Thiếu dependency hoặc auto-configuration bị exclude | Kiểm tra starter và condition report |
| Repository bean tồn tại nhưng query không chạy | Lỗi kết nối, mapping hoặc query | Chẩn đoán Driver, entity mapping và Cypher |

## 18. Câu hỏi tự kiểm tra

1. Spring Boot mặc định quét Neo4j repositories từ package nào?
2. Khi không khai báo base package, `@EnableNeo4jRepositories` quét package nào?
3. `basePackages` khác `basePackageClasses` như thế nào?
4. Vì sao `@EntityScan` không sửa được lỗi repository bean bị thiếu?
5. Strict repository configuration mode xuất hiện khi nào?
6. Vì sao repository nên mở rộng `Neo4jRepository` trong ứng dụng có cả JPA và SDN?
7. Annotation `@Node` giúp Spring Data phân biệt repository ra sao?
8. Vì sao một domain class có cả `@Entity` và `@Node` có thể gây mơ hồ cho repository generic?
9. `@NoRepositoryBean` có vai trò gì với generic base repository?
10. `considerNestedRepositories` có giá trị mặc định là gì?
11. Package scan chồng lấn giữa JPA và Neo4j có thể gây ra vấn đề nào?
12. Làm thế nào xác định auto-configuration Neo4j bị bỏ qua?
13. Phân biệt lỗi `NoSuchBeanDefinitionException` với lỗi authentication khi gọi repository như thế nào?
14. Có thể dùng ApplicationContext để xác nhận repository proxy đã được đăng ký ra sao?

## Tài liệu tham khảo

- [Spring Boot – Working with NoSQL Technologies: Neo4j repositories](https://docs.spring.io/spring-boot/reference/data/nosql.html)
- [Spring Data Neo4j – Defining Repository Interfaces](https://docs.spring.io/spring-data/neo4j/reference/repositories/definition.html)
- [Spring Data Neo4j – Creating Repository Instances](https://docs.spring.io/spring-data/neo4j/reference/repositories/create-instances.html)
- [Spring Data Neo4j – EnableNeo4jRepositories API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/repository/config/EnableNeo4jRepositories.html)
- [Spring Boot – Auto-configuration diagnostics](https://docs.spring.io/spring-boot/reference/using/auto-configuration.html)

## Kết luận

Lỗi không tìm thấy repository thường bắt đầu từ phạm vi package scan hoặc repository infrastructure chưa được kích hoạt. Hãy kiểm tra package của class `@SpringBootApplication`, phạm vi mặc định của `@EnableNeo4jRepositories`, dependency SDN và các filter trước khi sửa mapping.

Khi ứng dụng có nhiều Spring Data module, hãy khai báo repository theo store cụ thể bằng `Neo4jRepository`, dùng `@Node` cho domain graph và `@NoRepositoryBean` cho interface generic trung gian. Tách package repository giữa Neo4j và JPA để tránh scan chồng lấn. Cuối cùng, xác nhận repository proxy có trong ApplicationContext và dùng condition report để phân biệt lỗi auto-configuration với lỗi kết nối hoặc truy vấn ở runtime.
