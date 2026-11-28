# Chọn lớp repository cơ sở khi cần thay đổi hành vi dùng chung

Spring Data Neo4j (SDN) tạo repository proxy từ interface mà ứng dụng khai báo. Phần lớn thao tác CRUD được thực hiện bởi lớp cơ sở mặc định **SimpleNeo4jRepository**. Khi nhiều repository cần cùng một chính sách hoặc cùng một cách triển khai, bạn có thể thay lớp cơ sở này bằng một lớp tùy chỉnh.

Ví dụ, một ứng dụng có nhiều loại node và không muốn mã nghiệp vụ vô tình gọi **findAll()** để đọc toàn bộ node của một loại. Thay vì sửa từng repository, có thể tạo một lớp cơ sở kế thừa **SimpleNeo4jRepository**, ghi đè **findAll()** và đăng ký lớp đó qua **repositoryBaseClass**. Từ đó các repository được cấu hình dùng lớp cơ sở mới.

Điều quan trọng là chọn đúng cơ chế mở rộng:

- **Custom repository fragment** bổ sung chức năng cho một hoặc một nhóm repository được chọn.
- **Custom repository base class** thay đổi cách triển khai mặc định dùng chung cho các repository thuộc cùng cấu hình quét.
- **Base repository interface** chuẩn hóa các phương thức mà repository con công khai; nó không tự cung cấp phần triển khai.

Sau bài học, bạn có thể:

- Giải thích vai trò của **SimpleNeo4jRepository** trong repository proxy.
- Phân biệt repository fragment, base interface và base class.
- Kế thừa **SimpleNeo4jRepository<T, ID>** với constructor đúng của SDN.
- Đăng ký lớp tùy chỉnh bằng **@EnableNeo4jRepositories(repositoryBaseClass = ...)**.
- Ghi đè phương thức mặc định mà vẫn giữ các thao tác repository còn lại.
- Xác định phạm vi áp dụng, transaction và các điểm cần kiểm tra khi khởi tạo ứng dụng.

## 1. Repository proxy sử dụng lớp cơ sở như thế nào?

Khi ứng dụng khai báo:

~~~java
public interface PersonRepository
        extends Neo4jRepository<Person, Long> {
}
~~~

Spring Data không yêu cầu bạn tự viết lớp **PersonRepositoryImpl** cho các thao tác CRUD thông thường. Repository infrastructure tạo proxy kết hợp nhiều thành phần:

1. Lớp triển khai repository cơ sở của store.
2. Các chức năng mở rộng do Spring Data cung cấp, chẳng hạn Query by Example.
3. Các repository fragment do ứng dụng bổ sung.
4. Các phương thức truy vấn được tạo từ tên hoặc khai báo bằng **@Query**.

Trong SDN, lớp triển khai CRUD mặc định là **SimpleNeo4jRepository<T, ID>**. Lớp này cung cấp các thao tác như **save**, **findById**, **findAll**, **delete** và các phương thức phân trang/sắp xếp.

Khi cần thay đổi một hành vi mặc định trên diện rộng, lớp cơ sở tùy chỉnh cho phép kế thừa triển khai hiện có rồi chỉ ghi đè những phương thức cần thay đổi. Các phương thức còn lại tiếp tục dùng hành vi của **SimpleNeo4jRepository**.

## 2. Phân biệt ba cách mở rộng repository

| Cơ chế | Mục đích | Phạm vi |
|---|---|---|
| Repository fragment | Bổ sung một nhóm phương thức nghiệp vụ hoặc truy vấn tùy chỉnh | Repository nào kế thừa fragment |
| Base repository interface | Định nghĩa một API chung hoặc giới hạn các phương thức được công khai | Repository nào kế thừa interface |
| Custom repository base class | Thay đổi cách triển khai mặc định, có thể ghi đè CRUD dùng chung | Các repository thuộc cấu hình có **repositoryBaseClass** |

### Repository fragment khi chỉ một số repository cần chức năng riêng

Ví dụ, chỉ repository người dùng cần tìm kiếm theo một tiêu chí đồ thị đặc thù:

~~~java
package com.acme.graph.repository;

import java.util.List;

import com.acme.graph.domain.Person;

public interface PersonGraphSearch {
    List<Person> findPeopleConnectedTo(String personCode);
}
~~~

~~~java
package com.acme.graph.repository;

import java.util.List;
import java.util.Map;

import org.springframework.data.neo4j.core.Neo4jTemplate;

import com.acme.graph.domain.Person;

public class PersonGraphSearchImpl implements PersonGraphSearch {

    private final Neo4jTemplate neo4jTemplate;

    public PersonGraphSearchImpl(Neo4jTemplate neo4jTemplate) {
        this.neo4jTemplate = neo4jTemplate;
    }

    @Override
    public List<Person> findPeopleConnectedTo(String personCode) {
        String cypher = """
            MATCH (source:Person {personCode: $personCode})
                  -[:KNOWS*1..2]-
                  (candidate:Person)
            RETURN DISTINCT candidate
            """;

        return neo4jTemplate.findAll(
            cypher,
            Map.of("personCode", personCode),
            Person.class
        );
    }
}
~~~

~~~java
package com.acme.graph.repository;

import org.springframework.data.neo4j.repository.Neo4jRepository;

import com.acme.graph.domain.Person;

public interface PersonRepository
        extends Neo4jRepository<Person, Long>, PersonGraphSearch {
}
~~~

Repository chỉ nhận chức năng khi kế thừa interface fragment. Tên implementation mặc định ghép tên fragment với hậu tố **Impl**. Có thể cấu hình hậu tố khác qua **repositoryImplementationPostfix**, nhưng cơ chế fragment vẫn là lựa chọn phù hợp khi muốn thêm chức năng có chọn lọc.

### Base repository interface khi muốn chuẩn hóa API

Một interface generic có thể định nghĩa kiểu repository chung:

~~~java
import org.springframework.data.repository.NoRepositoryBean;
import org.springframework.data.neo4j.repository.Neo4jRepository;

@NoRepositoryBean
public interface BaseGraphRepository<T, ID>
        extends Neo4jRepository<T, ID> {
}
~~~

**@NoRepositoryBean** yêu cầu Spring Data không tạo repository proxy trực tiếp cho interface generic này. Nó vẫn được các repository cụ thể kế thừa:

~~~java
public interface PersonRepository
        extends BaseGraphRepository<Person, Long> {
}
~~~

Base interface hữu ích để tập trung các kiểu cha hoặc chữ ký phương thức chung. Tuy nhiên, nếu cần thay đổi cách triển khai **findAll()**, **save()** hoặc một phương thức CRUD mặc định cho nhiều repository, chỉ khai báo interface là chưa đủ. Khi đó cần custom base class.

## 3. Kế thừa SimpleNeo4jRepository

Lớp cơ sở tùy chỉnh của SDN cần kế thừa **SimpleNeo4jRepository<T, ID>**. Constructor của lớp cha nhận hai đối số:

- **Neo4jOperations**: API thao tác với Neo4j; implementation thông thường được cung cấp bởi **Neo4jTemplate**.
- **Neo4jEntityInformation<T, ID>**: metadata về entity và kiểu ID mà repository quản lý.

Đây là constructor cần giữ để repository factory có thể khởi tạo lớp cơ sở tùy chỉnh:

~~~java
package com.acme.graph.repository.support;

import org.springframework.data.neo4j.core.Neo4jOperations;
import org.springframework.data.neo4j.repository.support.Neo4jEntityInformation;
import org.springframework.data.neo4j.repository.support.SimpleNeo4jRepository;

public class GuardedNeo4jRepository<T, ID>
        extends SimpleNeo4jRepository<T, ID> {

    public GuardedNeo4jRepository(
            Neo4jOperations neo4jOperations,
            Neo4jEntityInformation<T, ID> entityInformation) {

        super(neo4jOperations, entityInformation);
    }
}
~~~

Không tự tạo **Neo4jTemplate** hoặc **Neo4jEntityInformation** bên trong constructor. Repository factory sẽ truyền các đối tượng phù hợp cho từng repository. Constructor phải chuyển đúng hai đối số này lên constructor của lớp cha.

Ví dụ trong bài dùng repository imperative. Nếu ứng dụng dùng reactive repositories, lớp cơ sở tương ứng là **SimpleReactiveNeo4jRepository<T, ID>**; constructor nhận **ReactiveNeo4jOperations** và **Neo4jEntityInformation<T, ID>**, sau đó được đăng ký bằng **@EnableReactiveNeo4jRepositories(repositoryBaseClass = ...)**. Không dùng lớp imperative cho repository reactive.

## 4. Ví dụ: chặn findAll() không giới hạn

Trong một graph lớn, gọi **findAll()** có thể tải một lượng node vượt quá nhu cầu của màn hình hoặc service. Có thể thiết lập chính sách chung: không cho phép đọc toàn bộ node bằng phương thức không điều kiện, buộc người gọi dùng truy vấn có bộ lọc hoặc phân trang.

Ghi đè phương thức trong lớp cơ sở:

~~~java
package com.acme.graph.repository.support;

import java.util.List;

import org.springframework.data.neo4j.core.Neo4jOperations;
import org.springframework.data.neo4j.repository.support.Neo4jEntityInformation;
import org.springframework.data.neo4j.repository.support.SimpleNeo4jRepository;
import org.springframework.transaction.annotation.Transactional;

public class GuardedNeo4jRepository<T, ID>
        extends SimpleNeo4jRepository<T, ID> {

    public GuardedNeo4jRepository(
            Neo4jOperations neo4jOperations,
            Neo4jEntityInformation<T, ID> entityInformation) {

        super(neo4jOperations, entityInformation);
    }

    @Override
    @Transactional(readOnly = true)
    public List<T> findAll() {
        throw new UnsupportedOperationException(
            "findAll() không giới hạn đã bị tắt. "
            + "Hãy dùng truy vấn có điều kiện hoặc phân trang."
        );
    }
}
~~~

Lớp này chỉ thay đổi hành vi của **findAll() không tham số**. Các phương thức khác như **findById**, **findAll(Pageable)**, **findAll(Sort)**, **save** và **delete** vẫn dùng implementation được kế thừa, trừ khi ứng dụng tiếp tục ghi đè chúng.

Đây là một chính sách bảo vệ ở tầng repository. Nó không thay thế việc thiết kế API tìm kiếm hợp lý: các service vẫn nên dùng derived finder, **@Query** hoặc phương thức có **Pageable** để giới hạn lượng dữ liệu.

## 5. Đăng ký custom base class

Sau khi tạo lớp cơ sở, cấu hình repository scanning để Spring Data sử dụng lớp đó:

~~~java
package com.acme.graph.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.repository.config.EnableNeo4jRepositories;

import com.acme.graph.repository.support.GuardedNeo4jRepository;

@Configuration
@EnableNeo4jRepositories(
    basePackages = "com.acme.graph.repository",
    repositoryBaseClass = GuardedNeo4jRepository.class
)
public class Neo4jRepositoryConfiguration {
}
~~~

Thuộc tính **repositoryBaseClass** xác định lớp cơ sở được dùng để tạo repository proxy trong cấu hình này. Mọi repository được phát hiện trong package **com.acme.graph.repository** sẽ dùng **GuardedNeo4jRepository** làm implementation cơ sở.

Ví dụ repository cụ thể vẫn khai báo như bình thường:

~~~java
package com.acme.graph.repository;

import java.util.List;

import org.springframework.data.neo4j.repository.Neo4jRepository;
import com.acme.graph.domain.Person;

public interface PersonRepository
        extends Neo4jRepository<Person, Long> {

    List<Person> findByCity(String city);
}
~~~

Khi Spring tạo **PersonRepository**, proxy sử dụng **GuardedNeo4jRepository<Person, Long>** làm base implementation. Lời gọi **findAll()** sẽ đi vào phương thức đã ghi đè; lời gọi **findByCity()** vẫn được xử lý bởi cơ chế tạo derived query.

Nếu ứng dụng có nhiều cấu hình **@EnableNeo4jRepositories** với các package khác nhau, hãy đặt **repositoryBaseClass** ở từng cấu hình muốn áp dụng chính sách. Phạm vi của lớp cơ sở gắn với cấu hình repository scanning, không mặc nhiên bao phủ mọi repository trong toàn bộ ứng dụng.

Trong ứng dụng Spring Boot, hãy tránh tạo hai cấu hình quét chồng lấn cho cùng package. Chọn một điểm cấu hình repository rõ ràng và xác minh repository proxy được tạo đúng một lần.

## 6. Thay đổi phương thức CRUD và transaction

Có thể ghi đè các phương thức CRUD khác nếu thật sự cần thay đổi hành vi chung. Ví dụ, khi ghi đè **save()** để thêm kiểm tra trước khi lưu, hãy giữ đúng chữ ký generic:

~~~java
@Override
@Transactional
public <S extends T> S save(S entity) {
    validateBeforeSave(entity);
    return super.save(entity);
}

protected <S extends T> void validateBeforeSave(S entity) {
    // Áp dụng quy tắc chung nếu có.
}
~~~

Trong ví dụ này, **save()** vẫn trả về instance do lớp cha trả về. Không bỏ qua giá trị trả về của **super.save(entity)**, vì SDN có thể cập nhật ID hoặc version trong quá trình lưu.

Lưu ý về transaction:

- Các phương thức CRUD do **SimpleNeo4jRepository** cung cấp đã có cấu hình transaction tương ứng. Không suy rộng rằng mọi derived query hoặc custom query đều mặc định là read-only.
- Khi ghi đè phương thức, khai báo **@Transactional(readOnly = true)** cho thao tác chỉ đọc và **@Transactional** cho thao tác ghi nếu cần chỉ rõ ranh giới transaction.
- Nếu phương thức mới gọi nhiều thao tác repository hoặc template và cần tính nguyên tử, đặt transaction ở phương thức phù hợp.
- Không tự mở session hoặc transaction Driver bên trong base class nếu đã dùng hạ tầng transaction của SDN.
- Nếu override phương thức có nhiều hành vi bên dưới, hãy gọi **super** khi muốn giữ logic mặc định; chỉ thay hoàn toàn khi hiểu rõ trách nhiệm mà implementation gốc đang đảm nhiệm.

Lớp cơ sở tùy chỉnh trở thành một phần hạ tầng dùng chung. Một thay đổi trong đó có thể ảnh hưởng đến tất cả repository thuộc cấu hình, vì vậy cần cân nhắc tương thích trước khi ghi đè các phương thức CRUD quan trọng.

## 7. Thứ tự ưu tiên giữa base class và fragment

Repository của Spring Data được ghép từ các fragment. Custom fragment có độ ưu tiên cao hơn base implementation và repository aspects. Điều này cho phép một repository cụ thể ghi đè hành vi chung khi có ngoại lệ nghiệp vụ.

Ví dụ:

- **GuardedNeo4jRepository** chặn **findAll()** cho mọi repository trong cấu hình.
- Một fragment riêng có thể cung cấp phương thức tìm kiếm chuyên biệt cho một repository.
- Nếu fragment triển khai cùng chữ ký phương thức với base implementation, fragment có thể được ưu tiên khi proxy phân giải lời gọi.

Hãy dùng base class cho chính sách thực sự phổ quát. Nếu một vài repository cần hành vi khác, hãy cân nhắc fragment thay vì thêm nhiều điều kiện theo tên entity vào base class.

## 8. Khi nào nên chọn base class?

| Nhu cầu | Cách mở rộng phù hợp |
|---|---|
| Chặn một CRUD mặc định trên mọi repository thuộc cấu hình | Custom repository base class |
| Bổ sung một phương thức tìm kiếm cho riêng PersonRepository | Repository fragment |
| Dùng chung một nhóm phương thức tùy chỉnh cho một số repository | Repository fragment tái sử dụng |
| Chuẩn hóa kiểu cha hoặc giới hạn API mà repository công khai | Base repository interface với **@NoRepositoryBean** |
| Thay đổi sâu quá trình tạo proxy, advisor hoặc factory | RepositoryFactoryCustomizer hoặc custom factory bean |

Không nên chọn base class chỉ để thêm một phương thức riêng lẻ cho một repository. Mỗi lần thay đổi base class đều có phạm vi ảnh hưởng rộng hơn, đồng thời làm tăng trách nhiệm của lớp nền.

## 9. Những lỗi thường gặp

**Sai constructor của lớp cha.** Constructor của custom base class phải nhận **Neo4jOperations** và **Neo4jEntityInformation<T, ID>**, sau đó truyền chúng cho **super(...)**. Thiếu constructor tương thích có thể khiến repository factory không khởi tạo được proxy.

**Nhầm repositoryBaseClass với repositoryImplementationPostfix.** **repositoryBaseClass** chọn lớp triển khai cơ sở. **repositoryImplementationPostfix** chỉ điều chỉnh hậu tố tên implementation khi Spring Data dò tìm repository fragment.

**Áp dụng nhầm phạm vi.** Base class chỉ áp dụng cho các repository được tạo bởi cấu hình **@EnableNeo4jRepositories** tương ứng. Kiểm tra package scanning nếu một repository không dùng hành vi mới.

**Quên @NoRepositoryBean trên base interface generic.** Spring có thể cố tạo repository trực tiếp từ interface còn tham số kiểu chưa được cụ thể hóa. Dùng **@NoRepositoryBean** cho interface generic trung gian.

**Ghi đè CRUD nhưng không giữ hợp đồng phương thức.** Giữ đúng kiểu generic, kiểu trả về, transaction và ý nghĩa của phương thức. Nếu thay đổi **save()**, hãy chú ý entity bất biến, ID và version.

**Thay toàn bộ hành vi mà không gọi super.** Khi không gọi **super**, logic mặc định của SDN sẽ không chạy. Chỉ làm vậy khi implementation mới thực sự thay thế toàn bộ trách nhiệm đó.

**Đặt nhiều cấu hình repository quét cùng package.** Cấu hình chồng lấn có thể gây đăng ký repository trùng hoặc hành vi khó đoán. Hãy tổ chức phạm vi quét rõ ràng.

**Đưa quy tắc đặc thù vào base class.** Base class không nên chứa điều kiện phụ thuộc vào tên lớp entity hoặc nghiệp vụ của một repository cụ thể. Dùng fragment để cô lập các trường hợp đặc biệt.

## 10. Tự kiểm tra

1. **SimpleNeo4jRepository<T, ID>** đảm nhiệm vai trò gì trong repository proxy?
2. Custom repository base class cần có constructor nhận những kiểu đối số nào?
3. **repositoryBaseClass** khác **repositoryImplementationPostfix** ở điểm nào?
4. Khi nào nên dùng repository fragment thay vì custom base class?
5. Vì sao base repository interface generic cần **@NoRepositoryBean**?
6. Khi ghi đè **save()**, vì sao cần giữ kiểu trả về và kết quả từ **super.save(entity)**?
7. Phạm vi áp dụng của custom base class được xác định bởi yếu tố nào?

**Bài tập thực hành:** Xây dựng **GuardedNeo4jRepository<T, ID>** kế thừa **SimpleNeo4jRepository<T, ID>** và ghi đè **findAll()** để chặn đọc không giới hạn. Đăng ký lớp qua **@EnableNeo4jRepositories(repositoryBaseClass = ...)**. Tạo hai repository **PersonRepository** và **MovieRepository**, xác minh cả hai đều dùng chính sách mới, trong khi **findByCity()**, **findByTitle()**, **findById()** và **findAll(Pageable)** vẫn hoạt động. Sau đó tạo một repository fragment cho riêng PersonRepository và so sánh phạm vi ảnh hưởng của hai cơ chế.

## Tài liệu tham khảo

- [Spring Data Neo4j — Custom Repository Implementations](https://docs.spring.io/spring-data/neo4j/reference/repositories/custom-implementations.html)
- [Spring Data Neo4j — FAQ: Custom base repositories](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
- [Spring Data Neo4j API — SimpleNeo4jRepository](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/repository/support/SimpleNeo4jRepository.html)
- [Spring Data Neo4j API — EnableNeo4jRepositories](https://docs.spring.io/spring-data/neo4j/docs/8.1.x/api/org/springframework/data/neo4j/repository/config/EnableNeo4jRepositories.html)
- [Spring Data Neo4j API — Neo4jEntityInformation](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/repository/support/Neo4jEntityInformation.html)
