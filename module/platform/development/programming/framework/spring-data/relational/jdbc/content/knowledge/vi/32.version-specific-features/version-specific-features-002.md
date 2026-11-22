# Đối chiếu API đang dùng với tài liệu đúng phiên bản

Một API có thể xuất hiện trong nhiều thế hệ Spring Data JDBC, nhưng chữ ký phương thức, package, kiểu trả về, hành vi mặc định và yêu cầu tương thích có thể thay đổi theo phiên bản. Một ví dụ trên trang tài liệu mới nhất chưa chắc dùng được trong dự án đang chạy phiên bản cũ.

Khi tra cứu một API, cần trả lời hai câu hỏi theo đúng thứ tự:

1. **Dự án thực sự đang nạp phiên bản nào?** Cần kiểm tra dependency đã được resolve, không chỉ nhìn phiên bản được khai báo trực tiếp trong file build.
2. **Tài liệu đang mở có mô tả đúng phiên bản đó không?** Reference documentation giải thích khái niệm và cách dùng; Javadoc xác nhận chữ ký API; release notes và upgrade notes cho biết những thay đổi giữa các phiên bản.

Bài học này hướng dẫn cách xác định phiên bản Spring Data Relational/JDBC và Spring Framework trong dự án, chọn tài liệu đúng nhánh, kiểm tra API cụ thể, đối chiếu khác biệt giữa các phiên bản và xử lý trường hợp code mẫu trên Internet không còn khớp với dependency hiện tại.

> **Mốc tham chiếu của ví dụ trong bài: 13-11-2026.** Tại thời điểm này, Spring Data Relational 4.1.2 là bản stable hiện hành thuộc Spring Data release train 2026.0.2. Hướng dẫn Getting Started của nhánh 4.1.2 yêu cầu Spring Framework 7.0.10 trở lên. Các con số này là mốc minh họa có ngày, không phải giá trị để sao chép mặc định vào mọi dự án.

## 1. Vì sao phải tra tài liệu đúng phiên bản?

Giả sử một dự án đang dùng Spring Data JDBC 3.5.x. Bạn tìm kiếm trên Internet và mở một ví dụ thuộc tài liệu 4.1.x. Trang mới có thể trình bày một API hoặc một cách cấu hình hợp lệ ở phiên bản mới, nhưng dự án cũ có thể:

- Chưa có class hoặc method được minh họa.
- Có method cùng tên nhưng khác overload hoặc kiểu trả về.
- Dùng package khác.
- Có hành vi mặc định khác.
- Cần một phiên bản Spring Framework khác.
- Có bug đã được sửa ở phiên bản mới nhưng vẫn tồn tại trong phiên bản dự án.
- Đã thay đổi cách cấu hình hoặc cách tích hợp với thư viện khác.

Ví dụ, khi đọc về **JdbcClient**, cần nhớ đây là API của Spring Framework trong package org.springframework.jdbc.core.simple, không phải API do Spring Data JDBC định nghĩa. Việc dự án dùng Spring Data JDBC phiên bản nào chưa đủ để kết luận JdbcClient có sẵn; cần kiểm tra phiên bản spring-jdbc thực tế.

Tương tự:

- **@Version** thuộc Spring Data Commons.
- **@Query** và **@Modifying** của repository JDBC thuộc Spring Data Relational/JDBC.
- **@Transactional** thuộc Spring Framework.
- **JdbcClient** thuộc Spring Framework JDBC.

Một dự án Spring Data JDBC thường dùng đồng thời nhiều module. Vì vậy, hãy tra đúng tài liệu của module sở hữu API đang dùng.

### 1.1. Các loại sai lệch thường gặp

| Sai lệch | Ví dụ | Hậu quả |
|---|---|---|
| Sai phiên bản module | Dùng ví dụ 4.1 cho dependency 3.5 | Code không biên dịch hoặc khác hành vi |
| Sai module | Tra API JPA để áp dụng cho JDBC | Dùng nhầm annotation hoặc semantics |
| Sai tầng framework | Nghĩ JdbcClient thuộc Spring Data JDBC | Kiểm tra nhầm artifact |
| Sai trạng thái phát hành | Dùng tài liệu snapshot hoặc milestone | Dựa vào API chưa ổn định |
| Sai dependency thực tế | File build ghi một version nhưng BOM resolve version khác | Tra tài liệu không khớp runtime |
| Sai loại tài liệu | Chỉ đọc guide, không kiểm tra Javadoc | Bỏ sót chữ ký, overload hoặc deprecation |
| Sai thời điểm | Dùng bài blog cũ mà không xem upgrade notes | Bỏ qua thay đổi và bug fix mới |

## 2. Phân biệt các loại phiên bản trong hệ sinh thái Spring

Không nên coi tất cả số phiên bản có chữ Spring là cùng một thứ.

| Loại phiên bản | Ví dụ | Ý nghĩa |
|---|---|---|
| Spring Boot | Version Boot của dự án | Phiên bản nền tảng ứng dụng và dependency management của Boot |
| Spring Data release train | 2026.0.2 | Bộ phiên bản tương thích của nhiều module Spring Data |
| Spring Data Relational | 4.1.2 | Phiên bản module chứa Spring Data JDBC và Spring Data R2DBC |
| Spring Data Commons | 4.1.2 | Hạ tầng chung của nhiều module Spring Data |
| Spring Framework | 7.0.10 | Framework nền mà các module Spring Data phụ thuộc |
| Spring JDBC | Version artifact spring-jdbc được resolve | Chứa JdbcTemplate, NamedParameterJdbcTemplate, JdbcClient |
| JDBC driver | Ví dụ PostgreSQL JDBC driver | Thư viện kết nối database của vendor |

Một release train có thể có version khác với version của module. Ví dụ, release train 2026.0.2 quản lý Spring Data Relational 4.1.2. Không lấy số 2026.0.2 để điền vào dependency spring-data-jdbc.

Cũng không suy ra Spring Framework version chỉ từ Spring Data version. Hãy đọc yêu cầu tương thích của nhánh Spring Data đang dùng và kiểm tra dependency đã resolve.

### 2.1. Mốc phiên bản minh họa tại ngày 13-11-2026

| Spring Data Relational | Spring Framework tối thiểu được tài liệu Getting Started nêu | Tài liệu cần chọn |
|---|---|---|
| 4.1.2 | 7.0.10 | Reference/Javadoc 4.1.x |
| 3.5.13 | 6.2.19 | Reference/Javadoc 3.5.x |

Spring Data 2026.0.2 công bố Spring Data Relational 4.1.2. Tài liệu 3.5.13 vẫn có nhánh riêng và ghi yêu cầu Spring Framework 6.2.19 trở lên.

Đây là ví dụ để thấy hai nhánh có baseline framework khác nhau. Khi làm việc với một dự án, phải kiểm tra chính xác patch version và dependency graph thực tế, không chỉ so sánh số major/minor.

## 3. Xác định phiên bản thực tế của dự án

Đây là bước quan trọng nhất. Phiên bản trong dependency declaration có thể không phải phiên bản cuối cùng được đưa vào classpath.

Một dependency có thể được quản lý bởi:

- Spring Boot dependency management.
- Spring Data release train BOM.
- Maven parent POM.
- Gradle platform hoặc version catalog.
- Dependency constraint.
- Dependency được khai báo bắc cầu bởi một thư viện khác.
- Rule ép version hoặc resolution strategy của build.

Hãy kiểm tra **effective/resolved dependency**.

## 4. Kiểm tra bằng Maven

### 4.1. Xem dependency tree

Dùng Maven Wrapper nếu dự án có file mvnw:

~~~bash
./mvnw dependency:tree \
  -Dincludes=org.springframework.data:spring-data-jdbc,org.springframework.data:spring-data-relational,org.springframework.data:spring-data-commons,org.springframework:spring-jdbc,org.springframework:spring-tx
~~~

Trên Windows có thể chạy:

~~~powershell
.\mvnw.cmd dependency:tree -Dincludes=org.springframework.data:spring-data-jdbc,org.springframework.data:spring-data-relational,org.springframework.data:spring-data-commons,org.springframework:spring-jdbc,org.springframework:spring-tx
~~~

Kết quả cho biết version được resolve và dependency nào đưa artifact vào graph. Nếu dự án là multi-module, chạy tại module thực sự khai báo hoặc sử dụng Spring Data JDBC.

Không chỉ nhìn dòng dependency trực tiếp trong pom.xml. Ví dụ:

~~~xml
<dependency>
    <groupId>org.springframework.data</groupId>
    <artifactId>spring-data-jdbc</artifactId>
</dependency>
~~~

Không có version không có nghĩa là thiếu version. Version có thể được cung cấp bởi parent POM hoặc BOM.

### 4.2. Xem effective POM

~~~bash
./mvnw help:effective-pom
~~~

Effective POM thể hiện cấu hình sau khi Maven hợp nhất parent, properties và dependency management. Dùng nó để tìm:

- BOM nào đang được import.
- Version property nào đang được áp dụng.
- Dependency management có override version hay không.
- Parent POM đang cung cấp cấu hình nào.

Nếu cần tập trung vào một artifact, kết hợp dependency:tree với effective POM thay vì đọc toàn bộ output một cách thủ công.

### 4.3. Kiểm tra dependency bị conflict

Maven thường chọn một version theo mediation rules. Nếu hai dependency yêu cầu các version khác nhau, dependency tree sẽ cho thấy đường đi và version được chọn.

Ví dụ:

~~~text
application
+- spring-data-jdbc:4.1.2
|  \- spring-data-relational:4.1.2
\- another-library
   \- spring-data-relational:4.0.8
~~~

Cần kiểm tra version thực tế và lý do nó được chọn. Không sửa bằng cách thêm version tùy ý vào mọi dependency. Trước tiên xác định BOM hoặc constraint đang quản lý chúng.

## 5. Kiểm tra bằng Gradle

### 5.1. Xem dependencyInsight

Đối với Gradle, dependencyInsight giúp xác định vì sao một version được chọn:

~~~bash
./gradlew dependencyInsight \
  --dependency spring-data-jdbc \
  --configuration runtimeClasspath
~~~

Kiểm tra Spring JDBC riêng:

~~~bash
./gradlew dependencyInsight \
  --dependency spring-jdbc \
  --configuration runtimeClasspath
~~~

Có thể kiểm tra compile classpath nếu cần xác định API mà compiler nhìn thấy:

~~~bash
./gradlew dependencyInsight \
  --dependency spring-data-jdbc \
  --configuration compileClasspath
~~~

### 5.2. Xem toàn bộ dependency graph

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Hãy chú ý các dấu hiệu như:

- by constraint: version được chọn theo dependency constraint.
- by conflict resolution: Gradle chọn version sau khi giải quyết xung đột.
- selected by rule: có resolution rule tác động.
- forced: version bị ép bởi cấu hình.

Những thông tin này giúp giải thích tại sao version trong classpath khác version bạn nhìn thấy ở một dòng khai báo.

### 5.3. Kiểm tra version catalog và platform

Một dự án có thể khai báo dependency qua version catalog:

~~~toml
[versions]
spring-data = "4.1.2"

[libraries]
spring-data-jdbc = {
    module = "org.springframework.data:spring-data-jdbc",
    version.ref = "spring-data"
}
~~~

Hoặc dùng platform/BOM:

~~~kotlin
dependencies {
    implementation(
        platform("org.springframework.data:spring-data-bom:2026.0.2")
    )

    implementation("org.springframework.data:spring-data-jdbc")
}
~~~

Nếu dự án dùng Spring Boot plugin và Boot BOM, hãy kiểm tra dependency management của Boot trước khi thêm một BOM khác. Tránh tạo ra hai nguồn quản lý version cạnh tranh.

## 6. Spring Boot và Spring Data BOM

Spring Boot thường quản lý phiên bản Spring Data và Spring Framework thông qua dependency management của Boot.

Với dự án dùng Spring Boot, dependency thường được khai báo mà không ghi version:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-jdbc</artifactId>
</dependency>
~~~

Hoặc khai báo module trực tiếp khi dự án đã có dependency management phù hợp:

~~~xml
<dependency>
    <groupId>org.springframework.data</groupId>
    <artifactId>spring-data-jdbc</artifactId>
</dependency>
~~~

Spring Data cũng cung cấp release train BOM để quản lý các module có version tương thích.

Ví dụ Maven dùng Spring Data BOM:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.data</groupId>
            <artifactId>spring-data-bom</artifactId>
            <version>2026.0.2</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.data</groupId>
        <artifactId>spring-data-jdbc</artifactId>
    </dependency>
</dependencies>
~~~

Đây là ví dụ dùng BOM trực tiếp cho dự án quản lý Spring Data version theo release train. Nếu Spring Boot đã quản lý version, hãy ưu tiên cơ chế Boot đang dùng và chỉ override khi có lý do tương thích rõ ràng.

Tài liệu Spring Data cho biết khi cần nâng release train được Spring Boot quản lý, có thể cấu hình property spring-data-bom.version theo hướng dẫn của Boot. Không nên tự thêm một BOM khác mà chưa hiểu thứ tự ưu tiên dependency management.

## 7. Chọn đúng bộ tài liệu

Mỗi loại tài liệu trả lời một loại câu hỏi.

| Nguồn | Dùng để trả lời | Không nên dùng thay cho |
|---|---|---|
| Reference documentation | Khái niệm, semantics, cấu hình và ví dụ sử dụng | Chữ ký chi tiết của mọi method |
| Javadoc | Class, method, constructor, annotation, generic và deprecation | Hướng dẫn kiến trúc toàn hệ thống |
| Release notes | Tính năng mới, bug fix, breaking change, dependency update | Hướng dẫn sử dụng đầy đủ |
| Upgrade notes | Các bước và lưu ý khi nâng version | API reference |
| Source code đúng tag | Hành vi triển khai khi tài liệu chưa đủ rõ | Hợp đồng API công khai nếu chỉ dựa vào implementation |
| Dependency metadata/BOM | Quan hệ và version tương thích | Semantics của API |

Một quy trình tra cứu tốt thường dùng nhiều nguồn:

1. Reference guide để hiểu cách dùng.
2. Javadoc để xác nhận API có trong version đang chạy.
3. Release notes/upgrade notes để biết thay đổi giữa các version.
4. Source code đúng release tag khi cần làm rõ một chi tiết chưa được tài liệu mô tả.

Không dùng source code của nhánh main để kết luận hành vi của artifact đang chạy ở một release cũ.

## 8. Mở đúng nhánh reference documentation

Trang tài liệu Spring Data có thể mặc định mở bản stable mới nhất. Cần xem tiêu đề phiên bản trên trang và chọn đúng nhánh.

Các URL hữu ích:

- [Spring Data Relational reference — stable hiện hành](https://docs.spring.io/spring-data/relational/reference/): tại mốc 13-11-2026 là 4.1.2.
- [Spring Data Relational reference — nhánh 3.5](https://docs.spring.io/spring-data/relational/reference/3.5/): dùng khi dự án thuộc dòng 3.5.x.
- [Spring Data JDBC — Getting Started](https://docs.spring.io/spring-data/relational/reference/jdbc/getting-started.html): yêu cầu framework, cấu hình và database dialect của bản hiện hành.
- [Spring Data Relational Javadoc 4.1.2](https://docs.spring.io/spring-data/relational/reference/api/java/): API reference của bản 4.1.2.
- [Spring Data upgrade notes](https://docs.spring.io/spring-data/relational/reference/commons/upgrade.html): hướng tới release notes và hướng dẫn nâng cấp.

Khi trang có bộ chọn version, hãy xác nhận version ở đầu trang sau khi chọn. Đừng chỉ dựa vào đường dẫn tìm kiếm hoặc tiêu đề của tab trình duyệt.

### 8.1. Phân biệt stable, preview và snapshot

Spring Data công bố nhiều trạng thái phát hành:

| Trạng thái | Ví dụ | Ý nghĩa |
|---|---|---|
| Stable | 4.1.2 | Bản phát hành ổn định |
| Milestone | 4.2.0-M1 | Bản thử nghiệm theo mốc |
| Release candidate | 4.2.0-RC1 | Bản ứng viên phát hành |
| Snapshot | 4.2.0-SNAPSHOT | Bản build phát triển liên tục |

Nếu dự án production dùng stable, hãy tra stable docs cùng nhánh. Chỉ dùng tài liệu preview/snapshot khi dự án thực sự phụ thuộc phiên bản đó và chấp nhận API có thể thay đổi.

Không nhầm một bản snapshot mới hơn về số minor với stable hiện tại. “Mới hơn” không đồng nghĩa “đúng version”.

## 9. Xác định module sở hữu API

Một import có thể cho biết API thuộc module nào, từ đó chọn đúng Javadoc.

| API | Package điển hình | Module sở hữu |
|---|---|---|
| @Query cho JDBC repository | org.springframework.data.jdbc.repository.query | Spring Data Relational/JDBC |
| @Modifying cho JDBC repository | org.springframework.data.jdbc.repository.query | Spring Data Relational/JDBC |
| @EnableJdbcAuditing | org.springframework.data.jdbc.repository.config | Spring Data Relational/JDBC |
| @Version | org.springframework.data.annotation | Spring Data Commons |
| @Id | org.springframework.data.annotation | Spring Data Commons |
| JdbcAggregateTemplate | org.springframework.data.jdbc.core | Spring Data Relational/JDBC |
| JdbcClient | org.springframework.jdbc.core.simple | Spring Framework JDBC |
| JdbcTemplate | org.springframework.jdbc.core | Spring Framework JDBC |
| @Transactional | org.springframework.transaction.annotation | Spring Framework transaction |

Ví dụ, khi tra JdbcClient, mở Javadoc/reference của Spring Framework version mà dependency spring-jdbc đang resolve. Tra tài liệu Spring Data JDBC không đủ để xác nhận mọi overload của JdbcClient.

Tương tự, @Version được định nghĩa ở Spring Data Commons. Khi kiểm tra annotation này, hãy xác nhận artifact Spring Data Commons tương ứng với release train của dự án.

## 10. Kiểm tra một API theo từng lớp

Giả sử code đang dùng @Query và @Modifying:

~~~java
import org.springframework.data.jdbc.repository.query.Modifying;
import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.CrudRepository;

public interface OrderRepository
        extends CrudRepository<SalesOrder, Long> {

    @Modifying
    @Query("""
        UPDATE sales_orders
        SET status = :status
        WHERE id = :id
        """)
    int updateStatus(Long id, String status);
}
~~~

Khi đối chiếu với tài liệu, không dừng ở việc thấy annotation có cùng tên. Hãy kiểm tra:

1. Annotation import có thuộc package JDBC không?
2. Annotation đó tồn tại trong version dependency đang resolve không?
3. Method có hỗ trợ câu lệnh UPDATE trong version đó không?
4. Kiểu trả về int có được hỗ trợ và biểu diễn affected rows như mong muốn không?
5. Named parameter có được bind theo tên method parameter trong cấu hình compiler hiện tại không, hay cần @Param?
6. Câu SQL có đúng dialect database không?
7. Transaction boundary của use case có phù hợp không?
8. Direct SQL có bỏ qua aggregate invariant, auditing hoặc optimistic locking không?

Reference documentation giải thích query methods và modifying queries. Javadoc xác nhận annotation và các method. Database vendor docs vẫn cần thiết cho cú pháp SQL cụ thể.

### 10.1. Xác nhận chữ ký bằng Javadoc

Khi mở class hoặc annotation trong Javadoc đúng version, hãy kiểm tra:

- Fully qualified class name.
- Constructor và method công khai.
- Tham số và generic type.
- Return type.
- Checked exception nếu có.
- Annotation target và retention.
- @Deprecated và @since.
- Ghi chú về thread safety hoặc lifecycle nếu có.

Một method có tên giống nhau nhưng nhận kiểu tham số khác có thể làm code không biên dịch hoặc chọn overload không mong muốn.

### 10.2. Kiểm tra @since và @Deprecated

Nếu Javadoc có @since, đó là gợi ý hữu ích về thời điểm API xuất hiện. Nếu có @Deprecated, hãy đọc phần mô tả để biết:

- API bị deprecated từ version nào.
- API thay thế được đề xuất là gì.
- Có kế hoạch xóa trong version nào không.
- Có thay đổi behavior nào cần xử lý trước khi thay thế.

Không xóa API chỉ vì IDE gạch ngang. Đọc deprecation note và upgrade guide trước khi sửa.

## 11. Ví dụ: phân biệt Spring Data JDBC và Spring Framework JdbcClient

Giả sử dự án dùng Spring Data JDBC để lưu aggregate và muốn thêm JdbcClient cho một query báo cáo.

Hai API thuộc hai module khác nhau:

~~~java
import org.springframework.data.jdbc.core.JdbcAggregateTemplate;
import org.springframework.jdbc.core.simple.JdbcClient;
~~~

JdbcAggregateTemplate thuộc Spring Data Relational/JDBC. JdbcClient thuộc Spring Framework JDBC.

Do đó, cần xác định cả hai version:

~~~text
spring-data-jdbc : 4.1.2
spring-jdbc      : 7.0.10
~~~

Đây là cặp version minh họa theo baseline của tài liệu 4.1.2, không phải bảo đảm dependency graph của mọi ứng dụng sẽ giống như vậy. Nếu Spring Boot hoặc BOM quản lý các version khác, hãy dùng kết quả resolve của chính dự án.

Cấu hình bean:

~~~java
@Configuration
class QueryConfiguration {

    @Bean
    JdbcClient jdbcClient(NamedParameterJdbcTemplate template) {
        return JdbcClient.create(template);
    }
}
~~~

Khi code không biên dịch, không nên lập tức đổi Spring Data JDBC version. Hãy xác định class không tìm thấy thuộc artifact nào, kiểm tra spring-jdbc version và mở Javadoc của Spring Framework tương ứng.

Đây là cách tránh nâng một module không liên quan chỉ để sửa lỗi dependency của module khác.

## 12. So sánh tài liệu giữa hai nhánh phiên bản

Khi dự án nâng từ Spring Data Relational 3.5.x lên 4.1.x, hãy dùng tài liệu của cả hai nhánh để so sánh.

Một quy trình:

1. Ghi lại version hiện tại từ dependency tree.
2. Mở reference/Javadoc của nhánh hiện tại.
3. Ghi lại API đang được sử dụng trong source.
4. Mở upgrade notes và release notes của từng release train bị đi qua.
5. Mở tài liệu nhánh đích.
6. So sánh package, method signature, configuration và semantics.
7. Chạy compile/test với dependency đích.
8. Chỉ sửa những phần có thay đổi thực tế hoặc cần tận dụng API mới.

Không chỉ đọc release notes của version đích nếu dự án nhảy qua nhiều release. Upgrade guide của Spring Data lưu ý cần xem cả các release notes trung gian khi bỏ qua nhiều release.

### 12.1. Không suy ra API đã thay đổi chỉ từ khác biệt số version

Hai nhánh có thể giữ nguyên chữ ký API nhưng thay đổi bug fix hoặc semantics ở một trường hợp biên. Ngược lại, một release có thể thêm API mới mà không làm API cũ mất đi.

Hãy phân loại kết quả so sánh:

| Loại khác biệt | Cần làm gì? |
|---|---|
| API mới được thêm | Chỉ dùng nếu version đích có và use case cần |
| API bị deprecated | Lập kế hoạch thay thế, đọc deprecation note |
| API bị xóa hoặc đổi chữ ký | Cập nhật source và test |
| Behavior được sửa | Kiểm tra ảnh hưởng nghiệp vụ |
| Dependency baseline đổi | Kiểm tra JDK, Framework, Boot và thư viện tích hợp |
| Không có thay đổi liên quan | Giữ code hiện tại, không refactor chỉ vì nâng version |

### 12.2. Tách thay đổi API khỏi thay đổi behavior

Ví dụ method vẫn compile sau nâng version, nhưng cách xử lý một tình huống edge case đã thay đổi. Compiler không phát hiện được khác biệt này.

Vì vậy, ngoài compile test, hãy có integration test cho behavior mà ứng dụng phụ thuộc, đặc biệt là:

- Aggregate persistence.
- Optimistic locking.
- Query derivation và modifying query.
- Auditing callback.
- Transaction rollback.
- Database dialect và generated SQL.
- Mapping null, enum, date/time và embedded properties.

## 13. Đọc release notes và upgrade notes theo đúng đường nâng cấp

Release notes thường mô tả:

- New features.
- Bug fixes.
- Deprecations.
- Breaking changes.
- Dependency upgrades.
- Upgrade instructions.

Khi nâng nhiều phiên bản, không nên chỉ đọc release notes mới nhất. Ví dụ, từ 3.5.x lên 4.1.x, hãy xem các thay đổi liên quan ở các release train trung gian và xác định version Framework tối thiểu.

Spring Data có trang upgrade hướng dẫn người đọc tới release notes trên project wiki. Hướng dẫn nâng cấp thường nằm ở phần đầu release notes của từng version.

Nguồn tham khảo chính thức tại mốc của bài:

- Spring Data 2026.0.2 công bố Spring Data Relational 4.1.2.
- Spring Data Relational 4.1.2 Getting Started yêu cầu Spring Framework 7.0.10 trở lên.
- Spring Data Relational 3.5.13 Getting Started yêu cầu Spring Framework 6.2.19 trở lên.

Các nguồn này giúp phân biệt đúng module version và framework baseline. Không dùng một bài blog công bố release để thay thế API reference; dùng nó để xác nhận version, sau đó mở reference/Javadoc tương ứng.

## 14. Đối chiếu ví dụ trên Internet

Một ví dụ từ Stack Overflow, blog hoặc repository GitHub có thể được viết cho version khác. Trước khi sao chép, hãy kiểm tra:

- Ngày đăng và version được ghi trong bài.
- pom.xml, build.gradle hoặc version catalog của ví dụ.
- Package import trong code.
- API được dùng thuộc Spring Data hay Spring Framework.
- Bài viết có dùng snapshot hoặc milestone không.
- Có release note nào thay đổi API đó sau thời điểm bài viết không.
- Ví dụ có dùng database dialect khác với dự án không.

Nếu bài viết không ghi version, xem dependency file trong repository. Nếu vẫn không xác định được, dùng ví dụ như gợi ý về ý tưởng và xác minh API trong tài liệu chính thức của version đang chạy.

Không suy luận rằng một code snippet đúng vì nó có nhiều lượt upvote hoặc vì nó biên dịch trong một project khác.

## 15. Kiểm chứng bằng compiler, test và runtime

Tài liệu cho biết API được hỗ trợ; build và test xác nhận dự án thực tế có thể dùng API đó trong dependency graph hiện tại.

Một quy trình kiểm chứng:

### 15.1. Compile

Maven:

~~~bash
./mvnw -DskipTests compile
~~~

Gradle:

~~~bash
./gradlew compileJava
~~~

Compile xác nhận class, import và method signature trên compile classpath. Nó không chứng minh semantics runtime là đúng.

### 15.2. Unit test

Kiểm tra logic application service, mapping và cách xử lý lỗi bằng test phù hợp. Unit test mock repository không chứng minh SQL thật hoặc transaction behavior của database.

### 15.3. Integration test

Dùng database engine/version gần production để kiểm tra:

- Repository khởi động với dependency hiện tại.
- SQL được tạo và chạy đúng.
- Mapping và conversion hoạt động.
- Transaction và rollback đúng.
- Callback/auditing được gọi đúng đường.
- Locking và concurrency có semantics mong muốn.

### 15.4. Kiểm tra runtime dependency

Nếu compile thành công nhưng runtime gặp NoSuchMethodError, ClassNotFoundException hoặc NoClassDefFoundError, hãy kiểm tra classpath runtime. Có thể compile và runtime đang resolve các version khác nhau hoặc một dependency bị loại trừ/ghi đè.

Không giải quyết lỗi linkage bằng cách chỉ thêm JAR ngẫu nhiên vào classpath. Xác định dependency nào cung cấp class và version nào được runtime nạp.

## 16. Checklist tra cứu một API

Khi cần dùng một API Spring Data JDBC, có thể theo bảng sau:

| Câu hỏi | Nơi kiểm tra |
|---|---|
| Dự án đang dùng version nào? | Maven dependency tree / Gradle dependencyInsight |
| Version do ai quản lý? | Effective POM, BOM, version catalog, constraints |
| API thuộc module nào? | Fully qualified import và dependency artifact |
| Guide đúng version ở đâu? | Reference documentation của nhánh đó |
| Chữ ký method chính xác? | Javadoc đúng version |
| API có deprecated không? | Javadoc và release notes |
| Có behavior change không? | Release notes, upgrade notes, source đúng tag |
| Có yêu cầu framework/JDK mới không? | Getting Started và dependency compatibility |
| Code có compile không? | Compile với resolved dependencies |
| SQL/runtime behavior có đúng không? | Integration test trên database mục tiêu |

### 16.1. Phiếu ghi nhận cho một API quan trọng

Khi một API ảnh hưởng lớn đến persistence hoặc transaction, ghi lại:

~~~text
API:
Fully qualified name:
Artifact:
Resolved version:
Spring Data release train:
Spring Framework version:
Reference documentation:
Javadoc:
Relevant upgrade notes:
Database/dialect:
Compile result:
Integration test:
Known limitations:
~~~

Phiếu này giúp reviewer hiểu API đang dựa trên version nào và nơi kiểm tra khi nâng cấp sau này.

## 17. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Chỉ nhìn version trong file build | Bỏ qua BOM hoặc transitive dependency | Kiểm tra resolved dependency |
| Mở trang tài liệu mới nhất rồi copy code | Dùng API không có trong version hiện tại | Chọn đúng documentation branch |
| Nhầm release train với module version | Khai báo sai version artifact | Ghi riêng train và module version |
| Tra Spring Data docs cho API Spring Framework | Kiểm tra nhầm chữ ký | Xác định package và artifact sở hữu |
| Dùng snapshot docs cho stable dependency | Dựa vào API chưa phát hành | Chọn stable docs |
| Chỉ đọc reference guide | Bỏ sót overload và deprecation | Đối chiếu Javadoc |
| Chỉ đọc Javadoc | Không hiểu aggregate semantics và transaction behavior | Đọc reference guide |
| Bỏ qua release notes trung gian | Bỏ sót migration requirement | Đọc toàn bộ release notes bị đi qua |
| Thấy compile thành công là đủ | Không phát hiện behavior/runtime mismatch | Chạy integration test |
| Thêm dependency version để chữa lỗi tùy tiện | Tạo dependency graph không tương thích | Xác định nguyên nhân resolve version |
| Dùng timestamp của bài blog làm version dự án | Code mẫu có thể đã cũ | Kiểm tra dependency graph và docs version |

## 18. Quy trình làm việc từ lúc gặp API đến khi sử dụng

Khi gặp một API mới hoặc code mẫu không khớp, hãy làm theo thứ tự:

**Bước 1 — Xác định API.** Ghi tên class/method và import đầy đủ.

**Bước 2 — Xác định artifact.** Tìm module cung cấp class đó, phân biệt Spring Data JDBC, Spring Data Commons và Spring Framework.

**Bước 3 — Resolve version.** Dùng dependency tree hoặc dependencyInsight để lấy version thực tế.

**Bước 4 — Xác định release train.** Kiểm tra BOM và dependency management đang điều khiển module.

**Bước 5 — Chọn đúng reference docs.** Mở nhánh tài liệu trùng với module version.

**Bước 6 — Kiểm tra Javadoc.** Xác nhận signature, overload, generic, deprecation và @since.

**Bước 7 — Đọc release notes.** Nếu code được chuyển từ nhánh cũ, xem các release notes trung gian.

**Bước 8 — Kiểm tra baseline.** Xác nhận Spring Framework, Spring Boot, JDK và database driver tương thích.

**Bước 9 — Compile và test.** Dùng dependency graph thật của dự án.

**Bước 10 — Ghi lại nguồn.** Lưu link reference/Javadoc/release notes đúng version trong tài liệu kỹ thuật hoặc code review.

~~~text
Tên API / import
       |
       v
Xác định artifact sở hữu
       |
       v
Resolve dependency version
       |
       v
Xác định BOM / release train
       |
       v
Chọn Reference docs đúng nhánh
       |
       v
Kiểm tra Javadoc / signature
       |
       v
Đọc release notes / upgrade notes
       |
       v
Compile + integration test
       |
       v
Ghi lại version và nguồn tham khảo
~~~

## 19. Bài tập tự suy luận

**Tình huống A — Version không có trong dependency declaration**

pom.xml khai báo spring-data-jdbc nhưng không có version. Có thể kết luận dự án không có version không?

**Gợi ý:** Không. Version có thể được quản lý bởi Spring Boot parent hoặc Spring Data BOM. Dùng dependency:tree và effective POM để tìm version thực tế.

**Tình huống B — API không tìm thấy**

Một ví dụ trên tài liệu mới dùng method mà dự án không biên dịch được. Nên làm gì trước khi nâng dependency?

**Gợi ý:** Xác định artifact sở hữu method, kiểm tra version resolve, mở Javadoc đúng version và đọc release notes. Sau đó mới quyết định dùng API thay thế hay nâng version.

**Tình huống C — JdbcClient**

Dự án dùng Spring Data JDBC 3.5.x nhưng compiler không tìm thấy JdbcClient. Có nên kết luận Spring Data JDBC thiếu API này không?

**Gợi ý:** Không. JdbcClient thuộc Spring Framework JDBC. Kiểm tra version spring-jdbc và framework baseline thực tế.

**Tình huống D — BOM và artifact version**

Release train là 2026.0.2, Spring Data Relational là 4.1.2. Version nào được ghi vào dependency khi dùng BOM?

**Gợi ý:** BOM cung cấp version module tương thích. Khi import BOM, dependency spring-data-jdbc có thể bỏ version; không điền 2026.0.2 như version module.

**Tình huống E — Tài liệu snapshot**

Một trang snapshot mô tả API mới hơn stable docs. Dự án production đang dùng stable. Có nên áp dụng API đó ngay không?

**Gợi ý:** Không. Chỉ sử dụng nếu dự án thực sự nâng lên version preview/snapshot và chấp nhận trạng thái đó. Với stable dependency, tra stable Javadoc/reference.

**Tình huống F — Compile thành công**

Một API compile thành công nhưng query chạy khác với mong đợi trên PostgreSQL. Tài liệu nào cần kiểm tra?

**Gợi ý:** Reference guide và Javadoc cho API Spring, release notes cho behavior changes, database documentation cho SQL dialect, rồi integration test trên PostgreSQL.

## 20. Ghi nhớ

| Thành phần | Vai trò |
|---|---|
| Resolved dependency | Version thực sự được đưa vào classpath |
| Spring Data BOM | Quản lý các module Spring Data tương thích |
| Spring Boot BOM | Quản lý dependency theo phiên bản Boot |
| Release train | Nhóm version tương thích của Spring Data |
| Reference documentation | Giải thích semantics và cách dùng |
| Javadoc | Xác nhận public API và chữ ký |
| Release notes | Ghi nhận tính năng, bug fix và thay đổi |
| Upgrade notes | Hướng dẫn chuyển giữa các phiên bản |
| Source đúng release tag | Làm rõ implementation khi tài liệu chưa đủ |
| Compile test | Xác nhận API tồn tại trên compile classpath |
| Integration test | Xác nhận behavior với dependency và database thực tế |

**Tra đúng API bắt đầu từ version đã resolve trong dự án, không bắt đầu từ trang tìm kiếm đầu tiên.** Xác định artifact sở hữu API, kiểm tra BOM và dependency graph, mở reference/Javadoc đúng nhánh, đọc release notes nếu đang nâng cấp, rồi compile và test trên cấu hình thật. Cách làm này giúp tránh nhầm API giữa Spring Data JDBC, Spring Data Commons và Spring Framework, đồng thời giữ ví dụ kỹ thuật khớp với phiên bản ứng dụng đang chạy.

## Tài liệu tham khảo

- [Spring Data Relational — Reference Documentation](https://docs.spring.io/spring-data/relational/reference/): tài liệu stable hiện hành; tại mốc 13-11-2026 là Spring Data Relational 4.1.2.
- [Spring Data Relational — Javadoc 4.1.2](https://docs.spring.io/spring-data/relational/reference/api/java/): public API của Spring Data Relational 4.1.2.
- [Spring Data Relational 3.5 — Reference Documentation](https://docs.spring.io/spring-data/relational/reference/3.5/): tài liệu đúng nhánh 3.5.x.
- [Spring Data JDBC — Getting Started](https://docs.spring.io/spring-data/relational/reference/jdbc/getting-started.html): dependency, yêu cầu Spring Framework và cấu hình JDBC của nhánh hiện hành.
- [Spring Data 2026.0.2 and 2025.1.8 released](https://spring.io/blog/2026/10/22/spring-data-2026-0-2-and-2025-1-8-released/): xác nhận Spring Data Relational 4.1.2 thuộc release train 2026.0.2.
- [Spring Data — Upgrading](https://docs.spring.io/spring-data/relational/reference/commons/upgrade.html): liên kết tới release notes và hướng dẫn nâng cấp.
- [Spring Framework — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): API JDBC như JdbcTemplate và JdbcClient thuộc Spring Framework.

