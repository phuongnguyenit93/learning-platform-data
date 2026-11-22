# Cơ chế quét package và đăng ký projection tường minh trong Spring Data REST

## Mục tiêu

Spring Data REST cho phép định nghĩa projection để thay đổi tập thuộc tính được trả về khi biểu diễn một domain object. Một projection thường là interface có annotation \`@Projection\`, khai báo các getter mà client được nhìn thấy.

Để projection có thể được sử dụng qua REST API, Spring Data REST phải tìm thấy và đăng ký định nghĩa đó. Có hai cách chính:

1. **Quét package tự động:** đặt interface projection có \`@Projection\` trong cùng package với domain type hoặc một package con của package đó.
2. **Đăng ký tường minh:** gọi \`RepositoryRestConfiguration.getProjectionConfiguration().addProjection(...)\` trong cấu hình Spring Data REST, thường thông qua \`RepositoryRestConfigurer\`.

Cả hai cách đều yêu cầu projection interface có annotation \`@Projection\`. Điểm khác nhau là cách Spring Data REST tìm và đưa projection vào registry. Bài này giải thích quy tắc package, cách tổ chức source code, cách đăng ký thủ công, cách kiểm tra projection đã được công bố và các lỗi thường gặp.

## 1. Projection là gì?

Giả sử domain type Person có nhiều thuộc tính:

~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String firstName;
    private String lastName;
    private String email;
    private String phoneNumber;

    @ManyToOne
    private Address address;

    // getters/setters
}
~~~

Repository được Spring Data REST export:

~~~java
public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
~~~

Mặc định, representation của Person có thể chứa các thuộc tính domain và link tới association. Nhưng một client có thể chỉ cần tên của Person, không cần email, phoneNumber hoặc address.

Projection mô tả một view có chọn lọc:

~~~java
@Projection(name = "personSummary", types = Person.class)
public interface PersonSummary {

    String getFirstName();

    String getLastName();
}
~~~

Khi projection được đăng ký, client có thể yêu cầu:

~~~http
GET /api/people/42?projection=personSummary
Accept: application/hal+json
~~~

Response minh họa:

~~~json
{
  "firstName": "Ada",
  "lastName": "Lovelace",
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/people/42{?projection}",
      "templated": true
    }
  }
}
~~~

Tên truyền trong query parameter \`projection\` là giá trị của thuộc tính \`name\` trong \`@Projection\`, ở đây là \`personSummary\`. Nó không tự động là tên interface \`PersonSummary\`.

Projection là một cách thay đổi representation của resource. Nó không tạo repository mới, không tạo endpoint CRUD mới và cũng không thay đổi entity trong database.

## 2. Quy tắc quét package tự động

Spring Data REST tự tìm các projection definition theo package của domain type:

- Interface có annotation \`@Projection\` nằm trong **cùng package với domain type** sẽ được đăng ký.
- Interface nằm trong **một package con** của package domain type cũng được đăng ký.
- Interface nằm ngoài cây package đó cần được đăng ký tường minh nếu muốn Spring Data REST sử dụng.

Ví dụ cấu trúc:

~~~text
com.example.people
├── Person.java
├── PersonRepository.java
└── projection
    ├── PersonSummary.java
    └── PersonWithAddress.java
~~~

Với \`Person\` nằm trong package \`com.example.people\`, các interface trong \`com.example.people\` và \`com.example.people.projection\` thuộc phạm vi package discovery được mô tả ở trên.

Ví dụ projection trong package con:

~~~java
package com.example.people.projection;

import com.example.people.Person;
import org.springframework.data.rest.core.config.Projection;

@Projection(name = "personSummary", types = Person.class)
public interface PersonSummary {

    String getFirstName();

    String getLastName();
}
~~~

Spring Data REST có thể phát hiện interface này theo quy tắc package của domain type Person. Không cần tạo bean riêng cho projection chỉ để đăng ký theo cách quét package.

### Package được tính từ domain type

Điểm neo của quy tắc là package chứa entity/domain type, không phải một package tùy ý của ứng dụng. Ví dụ:

~~~text
com.example.domain.people.Person
com.example.api.projections.PersonSummary
~~~

Trong cấu trúc này, \`com.example.api.projections\` không phải package của Person hoặc package con của \`com.example.domain.people\`. Chỉ đặt interface ở một package được Spring component scan không đảm bảo nó tự được Spring Data REST nhận diện như projection.

Nếu muốn giữ các projection trong một package dùng chung như \`com.example.api.projections\`, hãy đăng ký chúng tường minh bằng projection configuration.

### Quy tắc package không phụ thuộc tên interface

Tên interface có thể là \`PersonSummary\`, \`PersonListView\` hoặc tên khác. Việc phát hiện dựa trên vị trí package và annotation \`@Projection\`, không dựa trên hậu tố \`Projection\` trong tên class.

Tương tự, tên công khai của projection là thuộc tính \`name\`:

~~~java
@Projection(name = "summary", types = Person.class)
public interface PersonSummary {
    String getFirstName();
    String getLastName();
}
~~~

Client gọi \`?projection=summary\`, dù tên interface vẫn là \`PersonSummary\`.

## 3. Annotation @Projection xác định projection áp dụng cho domain type nào

Một projection interface phải có \`@Projection\`:

~~~java
@Projection(
    name = "personSummary",
    types = { Person.class }
)
public interface PersonSummary {

    String getFirstName();

    String getLastName();
}
~~~

Hai thuộc tính quan trọng:

| Thuộc tính | Vai trò |
|---|---|
| \`name\` | Tên projection mà client dùng trong query parameter \`projection\`. |
| \`types\` | Các domain type mà projection được phép áp dụng. |

Projection interface khai báo getter cho các thuộc tính cần xuất hiện trong view. Có thể khai báo getter cho thuộc tính lồng nhau hoặc association, miễn là kiểu trả về và projection semantics phù hợp.

Ví dụ projection cho một Person có address:

~~~java
@Projection(name = "personWithAddress", types = Person.class)
public interface PersonWithAddress {

    String getFirstName();

    String getLastName();

    AddressView getAddress();

    interface AddressView {
        String getCity();
        String getCountry();
    }
}
~~~

Projection có thể lồng nhau để chọn các trường cần thiết của object liên quan. Cách này giúp client nhận một representation phù hợp với use case mà không phải luôn tải toàn bộ domain graph.

Nếu một projection áp dụng cho nhiều domain type, khai báo các source type phù hợp trong \`types\`. Không nên đăng ký một projection cho domain type không tương thích với các getter của nó.

## 4. Khi nào cần đăng ký projection tường minh?

Đăng ký tường minh hữu ích khi:

- Projection nằm trong package dùng chung, ngoài package của domain type và các package con.
- Dự án muốn gom projection vào module API riêng.
- Package layout bị chia theo bounded context hoặc module, không thuận tiện để đặt interface cạnh entity.
- Ứng dụng muốn kiểm soát rõ projection nào được đưa vào Spring Data REST registry.
- Cần đăng ký projection từ một module hoặc thư viện khác mà quy tắc quét package của domain type không bao phủ.

Đăng ký thủ công không bỏ qua yêu cầu annotation. Projection interface vẫn phải có \`@Projection\`; registry cần metadata để xác định tên và source type tương ứng.

## 5. Đăng ký tường minh bằng RepositoryRestConfigurer

Spring Data REST cung cấp \`RepositoryRestConfiguration.getProjectionConfiguration()\`. Gọi \`addProjection(...)\` để đăng ký projection:

~~~java
package com.example.config;

import com.example.api.projections.PersonSummary;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.web.servlet.config.annotation.CorsRegistry;

@Configuration
public class RestProjectionConfiguration
        implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        config.getProjectionConfiguration()
              .addProjection(PersonSummary.class);
    }
}
~~~

Ở đây:

- \`RepositoryRestConfigurer\` là extension point để tùy chỉnh Spring Data REST.
- \`configureRepositoryRestConfiguration\` nhận cấu hình exporter.
- \`getProjectionConfiguration()\` trả registry quản lý projection definition.
- \`addProjection(PersonSummary.class)\` đăng ký interface projection để Spring Data REST tra cứu.

Projection interface vẫn có annotation:

~~~java
package com.example.api.projections;

import com.example.domain.people.Person;
import org.springframework.data.rest.core.config.Projection;

@Projection(name = "personSummary", types = Person.class)
public interface PersonSummary {

    String getFirstName();

    String getLastName();
}
~~~

Ví dụ này đặt projection trong \`com.example.api.projections\`, ngoài package \`com.example.domain.people\`. Đăng ký tường minh giúp Spring Data REST tìm được projection dù package không thuộc phạm vi tự quét.

### Đăng ký với source type tường minh

Projection configuration cũng cung cấp overload nhận source type:

~~~java
config.getProjectionConfiguration()
      .addProjection(PersonSummary.class, Person.class);
~~~

Overload này cho phép chỉ rõ domain type mà projection áp dụng. API còn có overload nhận tên projection và source type:

~~~java
config.getProjectionConfiguration()
      .addProjection(
          PersonSummary.class,
          "personSummary",
          Person.class
      );
~~~

Khi đã khai báo \`name\` và \`types\` trong \`@Projection\`, dạng \`addProjection(PersonSummary.class)\` thường là đủ. Dùng overload có source type hoặc name khi muốn cấu hình mapping rõ ràng theo API của phiên bản Spring Data REST đang dùng. Không đăng ký cùng một projection nhiều lần theo nhiều cách nếu không có lý do cần thiết.

## 6. Kết hợp quét package và đăng ký tường minh

Một ứng dụng có thể dùng cả hai cách, ví dụ:

~~~text
com.example
├── domain
│   └── people
│       ├── Person.java
│       └── projection
│           └── PersonListView.java
├── api
│   └── projections
│       └── PersonSummary.java
└── config
    └── RestProjectionConfiguration.java
~~~

- \`PersonListView\` nằm trong package con của domain type nên có thể được phát hiện tự động.
- \`PersonSummary\` nằm trong package API dùng chung nên được đăng ký tường minh qua \`RepositoryRestConfigurer\`.

Cách tổ chức này phù hợp khi một số projection mang tính cục bộ của domain, trong khi một số projection được quản lý ở tầng API hoặc module riêng.

Tuy nhiên, cần quản lý danh sách projection rõ ràng. Nếu một projection đã được quét tự động và cũng được thêm vào registry thủ công, không nên dựa vào hành vi trùng đăng ký giữa các phiên bản. Hãy chọn một cách đăng ký nhất quán cho mỗi projection và kiểm tra kết quả qua API metadata.

## 7. Dùng projection sau khi đã đăng ký

Giả sử Person repository được export tại \`/api/people\`, projection có tên \`personSummary\`.

Đọc một item:

~~~http
GET /api/people/42?projection=personSummary
Accept: application/hal+json
~~~

Đọc collection:

~~~http
GET /api/people?projection=personSummary
Accept: application/hal+json
~~~

Trong cả hai trường hợp, Spring Data REST dùng projection đã đăng ký để tạo representation phù hợp. Cấu trúc response cụ thể phụ thuộc các getter của projection và resource được yêu cầu.

Nếu gửi tên projection không được đăng ký hoặc không áp dụng cho source type của resource, server không thể áp dụng view đó. Hãy kiểm tra tên trong \`@Projection(name = ...)\`, source type trong \`types\` và việc đăng ký trước khi debug nội dung JSON.

### Tên query parameter

Mặc định, tên query parameter dùng để chọn projection là \`projection\`. Registry projection có cấu hình tên parameter, vì vậy nếu ứng dụng thay đổi cấu hình này, client phải dùng tên thực tế mà API công bố.

Không dùng tên interface làm query parameter trừ khi nó trùng với thuộc tính \`name\` trong annotation.

## 8. Projection và excerpt projection

Projection thông thường được client chọn bằng query parameter. Excerpt projection là một projection được áp dụng mặc định khi Spring Data REST nhúng resource vào collection hoặc resource liên quan.

Có thể chỉ định excerpt projection trên repository:

~~~java
@RepositoryRestResource(
    path = "people",
    excerptProjection = PersonSummary.class
)
public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
~~~

Khi collection \`/api/people\` nhúng các Person, Spring Data REST dùng \`PersonSummary\` làm preview mặc định cho các item được nhúng.

Excerpt projection không tự động áp dụng cho request lấy một item riêng như \`GET /api/people/42\`. Nếu muốn dùng projection cho item resource, client cần yêu cầu rõ bằng query parameter projection.

Nếu excerpt projection nằm ngoài package discovery của Person, hãy đăng ký tường minh để registry biết projection đó. Annotation \`excerptProjection\` trên repository tham chiếu class projection; nó không thay thế annotation \`@Projection\` trên interface.

## 9. Khám phá projection qua profile và ALPS

Spring Data REST công bố metadata giúp client tìm hiểu representation. Root resource thường cung cấp relation \`profile\`. Từ profile của resource, client có thể tìm ALPS metadata và các tùy chọn projection.

Ví dụ một đoạn ALPS minh họa:

~~~json
{
  "descriptors": [
    {
      "name": "projection",
      "type": "SEMANTIC",
      "descriptors": [
        {
          "name": "personSummary",
          "type": "SEMANTIC",
          "descriptors": [
            {
              "name": "firstName",
              "type": "SEMANTIC"
            },
            {
              "name": "lastName",
              "type": "SEMANTIC"
            }
          ]
        }
      ]
    }
  ]
}
~~~

Đoạn trên minh họa projection tên \`personSummary\` và các thuộc tính mà view công bố. ALPS response thực tế có thêm descriptor và metadata khác.

Có thể kiểm tra theo luồng:

1. Gọi API root hoặc collection resource.
2. Đọc relation \`profile\` trong \`_links\`.
3. Theo profile URI của resource.
4. Tìm descriptor \`projection\` trong ALPS.
5. Kiểm tra tên projection và các descriptor thuộc tính.
6. Dùng đúng tên projection trong query parameter.

Đây là cách xác nhận projection đã được công bố ở mức API. Không cần dựa vào tên file Java hoặc suy đoán từ package.

## 10. Phân biệt lỗi package discovery với lỗi projection mapping

Khi projection không xuất hiện hoặc không thể dùng, xác định lỗi thuộc một trong các lớp sau:

| Dấu hiệu | Nguyên nhân có thể | Kiểm tra |
|---|---|---|
| Interface có \`@Projection\` nhưng không thấy trong API | Nằm ngoài package domain và không được đăng ký thủ công. | Package của domain type, package của projection, \`addProjection\`. |
| Projection được phát hiện nhưng không áp dụng cho Person | \`types\` trỏ tới domain type khác. | \`@Projection(types = ...)\` hoặc source type overload. |
| Gửi \`?projection=PersonSummary\` nhưng không nhận đúng view | Dùng tên interface thay vì annotation name. | \`@Projection(name = ...)\`. |
| Projection không được đăng ký dù package đúng | Thiếu \`@Projection\`, sai import hoặc source type không hợp lệ. | Annotation \`org.springframework.data.rest.core.config.Projection\`. |
| Collection có excerpt nhưng item không có | Excerpt chỉ áp dụng tự động cho resource được nhúng. | Gọi item bằng query parameter projection nếu cần. |
| Registry cấu hình nhưng client không thấy lựa chọn | Cấu hình chưa được Spring nhận làm bean hoặc method callback không được gọi. | Bean \`RepositoryRestConfigurer\`, ApplicationContext và log khởi động. |
| Có nhiều projection cùng mục đích | Cấu hình đăng ký phân tán hoặc tên không nhất quán. | Registry, tên projection và package layout. |

Không nhầm package discovery của projection với repository scanning. Repository được phát hiện theo repository detection strategy; projection được tìm theo quy tắc package domain type hoặc được thêm vào projection configuration.

## 11. Những lỗi thường gặp

1. **Đặt projection trong package API rồi chờ tự động phát hiện.** Quy tắc mặc định dựa trên package của domain type và các package con.
2. **Đặt projection trong package con nhưng quên annotation.** Interface phải có \`@Projection\` ngay cả khi package nằm đúng phạm vi quét.
3. **Nhầm package của repository với package của entity.** Dùng package domain type làm mốc khi xác định vị trí projection.
4. **Dùng tên interface trong query parameter.** Giá trị client gửi phải khớp với \`@Projection(name = ...)\`.
5. **Thiếu source type.** Projection cần khai báo domain type mà nó áp dụng.
6. **Đăng ký tường minh nhưng không tạo bean configurer.** Đảm bảo lớp cấu hình được Spring quản lý trong ApplicationContext.
7. **Cho rằng component scan tự thay thế projection registry.** Đặt interface trong package được component scan không tự động chứng minh Spring Data REST đã đăng ký nó.
8. **Cho rằng excerpt projection luôn áp dụng cho item resource.** Excerpt mặc định dành cho resource được nhúng trong collection hoặc resource liên quan.
9. **Đăng ký một projection cho nhầm domain type.** Kiểm tra \`types\` và source type truyền vào \`addProjection\`.
10. **Không kiểm tra metadata API.** Theo profile/ALPS để xác nhận tên projection được công bố.
11. **Dùng projection để bảo vệ dữ liệu nhạy cảm.** Projection là cách chọn representation, không phải authorization boundary.
12. **Không kiểm soát projection có thể đưa dữ liệu ẩn ra ngoài.** Getter trong projection có thể làm lộ thuộc tính mà representation mặc định đang ẩn, kể cả một số thuộc tính được đánh dấu \`@JsonIgnore\`. Không tạo projection cho trường nhạy cảm và vẫn phải kiểm tra security ở server.

## 12. Checklist triển khai

- Projection interface có \`@Projection\`.
- \`name\` được đặt ổn định và là tên client sử dụng.
- \`types\` trỏ tới đúng domain type.
- Nếu dùng quét package, interface nằm cùng package hoặc package con của domain type.
- Nếu nằm ngoài cây package đó, đã gọi \`getProjectionConfiguration().addProjection(...)\`.
- Lớp \`RepositoryRestConfigurer\` được đăng ký trong ApplicationContext.
- Không đăng ký trùng một projection theo nhiều cơ chế nếu không cần thiết.
- Query parameter được gửi theo tên projection đã cấu hình.
- Excerpt projection được khai báo trên đúng repository nếu cần preview mặc định.
- Client không giả định excerpt tự áp dụng cho item resource.
- Profile/ALPS công bố projection như mong đợi.
- Projection không làm lộ dữ liệu nhạy cảm.
- Security vẫn kiểm tra quyền truy cập độc lập với projection.

## Tóm tắt

Spring Data REST tìm projection theo package của domain type: interface có \`@Projection\` trong cùng package hoặc package con sẽ được đăng ký tự động. Nếu projection nằm ngoài cây package đó, ứng dụng có thể đăng ký tường minh bằng \`RepositoryRestConfiguration.getProjectionConfiguration().addProjection(...)\`, thường trong callback của \`RepositoryRestConfigurer\`.

Trong cả hai cách, projection interface phải có \`@Projection\`, khai báo tên và source type. Client chọn projection bằng query parameter mặc định là \`projection\`, với giá trị khớp thuộc tính \`name\`. ALPS/profile giúp khám phá các projection được công bố. Excerpt projection có thể làm view mặc định cho item được nhúng trong collection, nhưng không tự áp dụng cho item resource riêng.

Hãy chọn package layout có chủ đích, đăng ký rõ các projection nằm ngoài phạm vi quét và kiểm tra metadata API. Projection quyết định representation được trả về; nó không thay thế authorization và không nên được dùng để che giấu dữ liệu nhạy cảm.

## Tài liệu tham khảo

- [Spring Data REST — Projections and Excerpts](https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html)
- [Spring Data REST — RepositoryRestConfiguration API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/config/RepositoryRestConfiguration.html)
- [Spring Data REST — ProjectionDefinitionConfiguration API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/config/ProjectionDefinitionConfiguration.html)
- [Spring Data REST — RepositoryRestConfigurer API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/config/RepositoryRestConfigurer.html)
- [Spring Data Commons — Projections](https://docs.spring.io/spring-data/commons/reference/repositories/projections.html)
