# Nhận diện tính năng thử nghiệm và kiểm chứng trước khi đưa vào tài liệu

Spring Data JDBC phát triển theo từng phiên bản của Spring Data và Spring Boot. Một tính năng có thể xuất hiện trong tài liệu mới nhất, trong nhánh mã nguồn đang phát triển hoặc trong một bản milestone, nhưng chưa chắc đã có trong phiên bản mà dự án đang sử dụng. Một API cũng có thể đã tồn tại nhưng vẫn được đánh dấu experimental, incubating, deprecated hoặc internal.

Vì vậy, trước khi đưa một tính năng vào tài liệu kỹ thuật, cần xác minh ba điều riêng biệt:

1. **Tính năng có thực sự có trong phiên bản dự án dùng không?**
2. **API đó có trạng thái hỗ trợ nào và có điều kiện sử dụng gì?**
3. **Hành vi có hoạt động trong cấu hình, database và driver mục tiêu không?**

Không thể trả lời cả ba câu hỏi chỉ bằng một trang tài liệu mới nhất hoặc một ví dụ tìm thấy trên mạng. Bài học này đưa ra quy trình kiểm chứng theo đúng dependency đã resolve, cách đọc Javadoc và release notes, cách nhận diện dấu hiệu API thử nghiệm, cách viết integration test và cách ghi lại kết quả để người đọc biết chính xác tính năng áp dụng cho phiên bản nào.

## 1. Phân biệt phiên bản tài liệu với phiên bản ứng dụng

Spring Data JDBC là một phần của hệ sinh thái Spring Data. Trong một dự án Spring Boot, dependency management thường chọn các phiên bản Spring Framework và Spring Data tương thích với release của Spring Boot.

Điều này có nghĩa:

- Tài liệu Spring Data JDBC mới nhất có thể mô tả API chưa có trong dependency của dự án.
- Ví dụ trên nhánh mã nguồn đang phát triển có thể chứa thay đổi chưa được phát hành.
- Một tính năng được giới thiệu trong milestone hoặc release candidate có thể thay đổi trước khi bản GA ra mắt.
- Phiên bản spring-data-jdbc và spring-data-relational phải tương thích với nhau.
- Database và JDBC driver cũng có thể giới hạn hành vi của tính năng.

Ví dụ, dự án dùng Spring Boot release cũ nhưng người viết mở tài liệu Spring Data Relational của release mới. Tài liệu mới có thể hiển thị method hoặc annotation không tồn tại trong classpath thực tế. Nếu sao chép ví dụ mà không kiểm tra dependency, bài học có thể không biên dịch cho người học.

**Nguyên tắc:** xác định phiên bản dependency mà dự án thực sự resolve trước, sau đó tra tài liệu, Javadoc và mã nguồn đúng phiên bản đó.

## 2. Xác định phiên bản Spring Data JDBC thực tế

Không nên chỉ nhìn phiên bản được khai báo trong file build. Dependency management, BOM, plugin hoặc dependency transitive có thể làm phiên bản được sử dụng khác với điều người viết dự đoán.

### 2.1. Kiểm tra bằng Gradle

Với Gradle, dùng dependencyInsight để xem phiên bản được chọn và lý do lựa chọn:

~~~bash
./gradlew dependencyInsight --dependency spring-data-jdbc --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-data-relational --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-data-commons --configuration runtimeClasspath
~~~

Trên Windows có thể chạy gradlew.bat thay cho ./gradlew.

Lệnh dependencies giúp xem cây dependency runtime:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Hãy kiểm tra:

- Phiên bản spring-data-jdbc cuối cùng được chọn.
- Phiên bản spring-data-relational được resolve.
- Phiên bản spring-data-commons liên quan.
- Dependency nào yêu cầu phiên bản và có quy tắc nào ép phiên bản khác.
- Có dependency snapshot, milestone hoặc release candidate hay không.

dependencyInsight đặc biệt hữu ích khi nhiều dependency cùng yêu cầu một module nhưng Gradle chọn một phiên bản theo quy tắc resolution.

### 2.2. Kiểm tra bằng Maven

Với Maven:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework.data:spring-data-jdbc
./mvnw dependency:tree -Dincludes=org.springframework.data:spring-data-relational
./mvnw dependency:tree -Dincludes=org.springframework.data:spring-data-commons
~~~

Nếu dự án không có Maven Wrapper, dùng mvn thay cho ./mvnw.

Để xem dependency management sau khi kế thừa parent và import BOM:

~~~bash
./mvnw help:effective-pom
~~~

Tập trung vào dependency thực tế và phần dependencyManagement. Phiên bản ghi trong một property hoặc parent POM chỉ là đầu vào của quá trình quản lý dependency; cây dependency đã resolve mới cho biết artifact nào đi vào classpath.

### 2.3. Kiểm tra Spring Boot và BOM

Nếu dự án dùng Spring Boot, kiểm tra version của Spring Boot parent hoặc plugin và BOM mà dự án import. Spring Boot quản lý một tập phiên bản tương thích cho các thư viện Spring.

Thông thường, nên để Spring Boot dependency management chọn phiên bản Spring Data JDBC. Nếu có lý do phải override, cần xác nhận release train Spring Data đó tương thích với Spring Boot và Spring Framework của dự án.

Không tùy tiện đặt ba version riêng cho:

~~~text
spring-data-jdbc
spring-data-relational
spring-data-commons
~~~

Việc trộn các module thuộc các release train khác nhau có thể gây lỗi binary compatibility, NoSuchMethodError, ClassNotFoundException hoặc hành vi mapping không nhất quán.

## 3. Đọc đúng loại tài liệu và nguồn bằng chứng

Không phải mọi nguồn đều trả lời cùng một câu hỏi. Hãy dùng nguồn phù hợp với loại bằng chứng cần xác nhận.

| Nguồn | Có thể xác nhận điều gì? | Giới hạn |
|---|---|---|
| Reference documentation đúng phiên bản | Cách sử dụng được tài liệu hỗ trợ và cấu hình liên quan | Trang current có thể mô tả release mới hơn |
| Javadoc đúng artifact/version | Chữ ký public API, tham số, kiểu trả về, annotation và ghi chú API | Javadoc có thể thiếu mô tả hành vi nội bộ |
| Release notes/changelog | Phiên bản giới thiệu, thay đổi và migration note | Tóm tắt có thể không mô tả hết điều kiện |
| Migration guide | Thay đổi cần xử lý khi nâng cấp | Không thay thế kiểm thử ứng dụng |
| Source code đúng Git tag | Implementation và annotation của đúng release | Source không tự chứng minh hành vi trong cấu hình ứng dụng |
| Test của dự án tại đúng tag | Cách nhóm phát triển kiểm tra tính năng | Test upstream không thay thế test với database của dự án |
| Artifact đã resolve | Class và method thực sự có trong classpath | Có class không có nghĩa tính năng được hỗ trợ ổn định |
| Integration test của ứng dụng | Hành vi với cấu hình, driver và database mục tiêu | Chỉ xác nhận phạm vi test đã chạy |

### 3.1. Dùng tài liệu có version

Khi tra reference documentation, chọn phiên bản Spring Data tương ứng với dependency đã resolve. Nếu trang có bộ chọn version, không để mặc định ở current khi dự án đang dùng một release cũ hơn.

Hãy xác nhận:

- Tên module là Spring Data JDBC/Relational, không phải Spring Data JPA.
- Trang tài liệu thuộc đúng release train.
- API trong ví dụ tồn tại ở phiên bản dự án.
- Ghi chú tương thích Java, Spring Framework, database hoặc driver có áp dụng không.

Một ví dụ dùng @Query, JdbcAggregateTemplate, custom conversions hoặc callback phải được đối chiếu với API của đúng phiên bản, kể cả khi tên class giống nhau.

### 3.2. Dùng Javadoc để xác nhận hợp đồng API

Javadoc giúp kiểm tra:

- Class và method có phải public API không.
- Kiểu tham số và kiểu trả về chính xác.
- Constructor hoặc overload nào có sẵn.
- Method được đánh dấu @since từ phiên bản nào.
- API có bị deprecated hoặc có cảnh báo về cách dùng không.
- Annotation mô tả trạng thái ổn định của API nếu dự án cung cấp metadata đó.

Không suy luận chữ ký method từ một bài blog hoặc từ ví dụ của phiên bản khác. Hãy đọc Javadoc của artifact đã resolve.

### 3.3. Dùng release notes và migration notes

Release notes thường cho biết một tính năng được thêm, sửa hoặc thay đổi trong release nào. Migration guide có thể nêu hành vi cũ bị loại bỏ hoặc cách cấu hình mới.

Khi thấy tính năng được giới thiệu:

1. Ghi nhận phiên bản đầu tiên được release notes đề cập.
2. Kiểm tra phiên bản đó là milestone, release candidate hay GA.
3. Xác nhận API có mặt trong artifact GA mà dự án muốn hỗ trợ.
4. Đọc migration note của các phiên bản tiếp theo để biết API có đổi hoặc bị deprecated không.

Không coi một dòng new feature trong changelog là bằng chứng rằng tính năng sẽ có mặt trong mọi phiên bản thấp hơn hoặc giữ nguyên chữ ký ở phiên bản tương lai.

## 4. Nhận diện trạng thái của một API

Một tính năng có thể mới nhưng ổn định, hoặc đã tồn tại một thời gian nhưng vẫn có trạng thái thử nghiệm. Cần phân biệt trạng thái API với tuổi đời của tính năng.

### 4.1. Các trạng thái thường gặp

| Trạng thái | Ý nghĩa thực tế khi viết tài liệu |
|---|---|
| Stable/public API | Có hợp đồng API công khai; vẫn cần ghi rõ phiên bản và giới hạn |
| Experimental | API hoặc tính năng có thể thay đổi; không nên trình bày như hợp đồng ổn định |
| Incubating | Đang được phát triển/hoàn thiện; phải kiểm tra ý nghĩa của nhãn trong dự án cụ thể |
| Preview hoặc milestone | Bản xem trước hoặc bản phát hành trước GA; không đại diện cho release production ổn định |
| Deprecated | Vẫn có thể dùng nhưng đã được khuyến cáo chuyển sang cách khác |
| Internal/unsupported | Không phải hợp đồng public được hỗ trợ; tránh hướng dẫn ứng dụng phụ thuộc trực tiếp |

Tên gọi và chính sách hỗ trợ có thể khác giữa các dự án. Đừng tự gán một trạng thái chỉ dựa vào cách đặt tên class.

### 4.2. Tìm API Guardian metadata

Một số thư viện Java dùng annotation từ API Guardian để mô tả trạng thái API, ví dụ:

~~~java
import org.apiguardian.api.API;

@API(status = API.Status.EXPERIMENTAL)
public class ExampleFeature {
}
~~~

Các trạng thái thường gặp của metadata này gồm STABLE, MAINTAINED, DEPRECATED, EXPERIMENTAL và INTERNAL.

Nếu class hoặc method được đánh dấu EXPERIMENTAL, phải phản ánh điều đó trong tài liệu. Không nên bỏ annotation rồi viết như thể API có hợp đồng ổn định.

Nếu được đánh dấu INTERNAL, không hướng dẫn người dùng ứng dụng phụ thuộc trực tiếp vào nó trừ khi tài liệu chính thức nêu rõ một trường hợp đặc biệt và chấp nhận rủi ro.

Không phải mọi API đều có annotation API Guardian. **Không thấy annotation không có nghĩa API chắc chắn stable.** Khi không có metadata, cần kết hợp Javadoc, reference docs, package, release notes và chính sách của dự án.

### 4.3. Kiểm tra @Deprecated

Ví dụ:

~~~java
@Deprecated(since = "x.y", forRemoval = true)
public void oldOperation() {
}
~~~

since cho biết phiên bản đánh dấu deprecated nếu được cung cấp. forRemoval = true là tín hiệu API dự kiến bị loại bỏ trong tương lai theo hợp đồng của annotation.

Khi viết tài liệu:

- Nêu API bị deprecated từ phiên bản nào nếu đã xác minh.
- Dẫn cách thay thế được tài liệu chính thức đề xuất.
- Ghi chú nếu cách cũ vẫn còn trong một dải phiên bản cần hỗ trợ.
- Không hướng người học bắt đầu dự án mới bằng API đã deprecated nếu có lựa chọn thay thế được hỗ trợ.

### 4.4. Đọc @since đúng cách

Javadoc có thể ghi:

~~~java
/**
 * @since 3.x
 */
~~~

Thông tin này hữu ích để xác định thời điểm API được thêm vào. Tuy nhiên:

- @since không tự khẳng định API là stable.
- Thiếu @since không chứng minh API có từ phiên bản đầu tiên.
- @since có thể chỉ ra phiên bản của module, không nhất thiết trùng số phiên bản Spring Boot.
- Cần đối chiếu với release notes và artifact thực tế.

## 5. Dấu hiệu cần thận trọng ngoài annotation

Ngay cả khi không có nhãn experimental rõ ràng, một số dấu hiệu cho thấy cần xác minh thêm trước khi đưa API vào bài học.

### 5.1. Package hoặc tên class mang tính nội bộ

Các package có tên như internal, impl hoặc class không public thường không phải điểm mở rộng được hỗ trợ cho ứng dụng. Đây không phải quy tắc tuyệt đối, nhưng là tín hiệu cần kiểm tra.

Ưu tiên:

- Interface hoặc class public trong package API chính thức.
- Cấu hình được reference documentation hướng dẫn.
- Extension point có hợp đồng và ví dụ công khai.

Tránh hướng dẫn import một implementation class nội bộ chỉ vì nó giải quyết được vấn đề trong một phiên bản.

### 5.2. API chỉ có trên nhánh main hoặc snapshot

Một class có thể xuất hiện trên GitHub nhánh phát triển nhưng chưa có trong artifact GA. Tương tự, dependency có hậu tố snapshot hoặc milestone không phải bằng chứng về API đã phát hành ổn định.

Hãy phân biệt:

- Source của release tag.
- Source của branch phát triển.
- Artifact milestone hoặc release candidate.
- Artifact GA được publish.

Nếu tài liệu cần mô tả tính năng đã phát hành, kiểm tra artifact GA và tag tương ứng.

### 5.3. Tính năng yêu cầu bật riêng

Một số tính năng chỉ hoạt động khi:

- Thêm dependency module khác.
- Bật annotation cấu hình.
- Khai báo bean cụ thể.
- Bật feature flag hoặc property.
- Dùng database dialect hoặc driver có hỗ trợ.
- Dùng một transaction manager nhất định.

Sự hiện diện của class trong classpath không chứng minh feature đã được kích hoạt. Cần kiểm tra điều kiện cấu hình và bean thực tế trong application context.

## 6. Kiểm tra API trong artifact đã resolve

Sau khi biết phiên bản dependency, có thể xác nhận class và method tồn tại trực tiếp trong artifact.

### 6.1. Kiểm tra nội dung JAR

Ví dụ:

~~~bash
jar tf path/to/spring-data-jdbc-version.jar
~~~

Trên Windows có thể lọc tên class bằng findstr; trên macOS/Linux có thể dùng grep.

Lệnh này xác nhận class có trong JAR, nhưng không cho biết API có stable hay hành vi chạy đúng hay không.

### 6.2. Kiểm tra chữ ký bằng javap

Nếu đã biết fully qualified class name:

~~~bash
javap -classpath path/to/spring-data-jdbc-version.jar fully.qualified.ClassName
~~~

Để xem thêm annotation và chữ ký chi tiết:

~~~bash
javap -v -classpath path/to/spring-data-jdbc-version.jar fully.qualified.ClassName
~~~

Nếu class phụ thuộc các artifact khác, thêm chúng vào classpath hoặc dùng IDE để mở external library. javap hữu ích khi Javadoc không sẵn có hoặc cần xác nhận method overload cụ thể.

### 6.3. Kiểm tra annotation bằng reflection

Trong một test nhỏ, có thể kiểm tra annotation runtime nếu annotation có retention phù hợp:

~~~java
API api = ExampleFeature.class.getAnnotation(API.class);

if (api != null) {
    System.out.println(api.status());
}
~~~

Reflection chỉ đọc metadata được đóng gói trong class. Nếu annotation có retention không phù hợp hoặc metadata nằm trong Javadoc/source, reflection không thay thế việc tra tài liệu.

## 7. Biên dịch ví dụ với đúng dependency

Một ví dụ có thể trông hợp lý nhưng dùng method không tồn tại trong phiên bản dự án. Cách kiểm chứng cơ bản là đưa ví dụ vào một module hoặc sample project dùng đúng dependency management của ứng dụng.

### 7.1. Dùng compile task

Gradle:

~~~bash
./gradlew compileJava
~~~

Maven:

~~~bash
./mvnw -DskipTests compile
~~~

Nếu snippet chỉ là một phần code, hãy đặt nó trong class có import và dependency cần thiết. Một đoạn code thiếu import không chứng minh API sai; cần phân biệt lỗi snippet chưa hoàn chỉnh với lỗi API không tồn tại.

### 7.2. Không kiểm chứng bằng cách nâng dependency tùy tiện

Nếu code chỉ biên dịch sau khi nâng Spring Data JDBC lên phiên bản mới nhất, điều đó không chứng minh ví dụ dùng được với phiên bản dự án hiện tại.

Ghi lại rõ:

- Phiên bản dependency ban đầu.
- Phiên bản mà snippet biên dịch.
- API hoặc method nào được thêm ở phiên bản mới.
- Dự án có kế hoạch nâng cấp hay không.

Không âm thầm đổi version chỉ để làm cho ví dụ chạy được rồi tiếp tục gọi đó là ví dụ của dự án cũ.

## 8. Kiểm thử hành vi bằng integration test

Biên dịch chỉ xác nhận API và kiểu dữ liệu tương thích ở compile time. Với Spring Data JDBC, nhiều hành vi còn phụ thuộc mapping, dialect, JDBC driver và database.

Một tính năng chỉ nên được mô tả là đã kiểm chứng trong môi trường cụ thể khi có test phù hợp.

### 8.1. Kiểm tra với database mục tiêu

Nếu tính năng liên quan đến:

- SQL do Spring Data sinh ra.
- Generated ID.
- Optimistic locking.
- Transaction và savepoint.
- Custom conversion.
- Aggregate collection mapping.
- Pagination hoặc dialect.

hãy chạy integration test với database/driver mà tài liệu tuyên bố hỗ trợ.

H2 có thể hữu ích cho test nhanh, nhưng không thay thế PostgreSQL, MySQL, SQL Server hoặc database production nếu hành vi phụ thuộc dialect. Không kết luận tính năng hoạt động trên mọi database chỉ vì một test H2 thành công.

### 8.2. Dùng @DataJdbcTest hoặc test context phù hợp

Ví dụ khung integration test:

~~~java
@DataJdbcTest
class FeatureIntegrationTest {

    @Autowired
    PurchaseOrderRepository orders;

    @Test
    void featureBehavesAsDocumented() {
        // Arrange: chuẩn bị dữ liệu.
        // Act: gọi repository hoặc JdbcAggregateTemplate.
        // Assert: kiểm tra kết quả và trạng thái database.
    }
}
~~~

Nếu tính năng cần cấu hình riêng, import cấu hình đó vào test hoặc dùng test application context tương đương với ứng dụng. Không chỉ kiểm tra object trả về; khi cần, truy vấn database để xác nhận dữ liệu thực sự được ghi đúng.

### 8.3. Kiểm tra cả trường hợp biên

Một test thành công duy nhất thường không đủ. Tùy tính năng, kiểm tra:

- Giá trị null và dữ liệu rỗng.
- Aggregate có collection con và aggregate không có collection con.
- Insert lần đầu và update lần tiếp theo.
- Lỗi constraint và rollback.
- Hai lần cập nhật cạnh tranh.
- Database/driver version khác nhau trong ma trận hỗ trợ.
- Cấu hình thiếu hoặc feature flag tắt.

Không cần kiểm tra mọi tổ hợp trong một bài học. Chọn các trường hợp chứng minh hợp đồng và giới hạn mà tài liệu đang mô tả.

## 9. Kiểm tra điều kiện kích hoạt và cấu hình Spring

Một tính năng có thể tồn tại trong JAR nhưng không hoạt động vì bean hoặc cấu hình cần thiết chưa được đăng ký.

Hãy kiểm tra:

1. Dependency cần thiết có trong runtime classpath không?
2. Annotation enablement có được đặt trong configuration được scan không?
3. Bean extension point có được đăng ký không?
4. Property/feature flag có đúng giá trị không?
5. Conditional configuration có được kích hoạt không?
6. Repository scan có bao gồm package cần thiết không?
7. Bean có bị một cấu hình khác override hoặc thay thế không?

Với Spring Boot, chế độ debug hoặc condition evaluation report có thể giúp hiểu auto-configuration nào được áp dụng và vì sao một cấu hình bị bỏ qua. Nếu có Actuator conditions endpoint, cần cấu hình quyền truy cập phù hợp trước khi dùng trong môi trường chia sẻ.

Không đưa endpoint chẩn đoán nội bộ ra môi trường production công khai chỉ để kiểm tra một bài học.

## 10. Kiểm chứng một tính năng theo từng lớp

Một quy trình có thể chia thành bốn lớp bằng chứng:

| Lớp | Câu hỏi | Bằng chứng |
|---|---|---|
| Availability | Có trong phiên bản đang dùng không? | Dependency tree, artifact, class/method |
| API status | Có được hỗ trợ ổn định không? | API metadata, Javadoc, reference docs, release notes |
| Activation | Cần cấu hình gì để chạy? | Bean/configuration/property, application context |
| Behavior | Có hoạt động như tài liệu mô tả không? | Integration test với database và driver mục tiêu |

Không nên bỏ qua một lớp. Ví dụ:

- Có class trong JAR nhưng API mang trạng thái experimental.
- API stable nhưng dự án chưa bật bean cần thiết.
- Code biên dịch nhưng dialect database không hỗ trợ cú pháp cần thiết.
- Test H2 thành công nhưng database production có hành vi khác.

## 11. Ví dụ quy trình xác minh một API mới

Giả sử một bản nháp tài liệu muốn giới thiệu một method mới trong JdbcAggregateTemplate.

Không nên lập tức viết rằng method đó có từ mọi phiên bản Spring Data JDBC. Hãy thực hiện:

**Bước 1 — Xác định dependency:** chạy dependencyInsight hoặc dependency:tree và ghi lại phiên bản spring-data-jdbc, spring-data-relational cùng release train.

**Bước 2 — Kiểm tra reference docs:** mở tài liệu của đúng release. Tìm method và xác nhận phần mô tả, điều kiện cấu hình, giới hạn.

**Bước 3 — Kiểm tra Javadoc:** xác nhận chữ ký method, kiểu trả về, annotation API Guardian, @Deprecated và @since nếu có.

**Bước 4 — Kiểm tra release notes:** xác nhận method được giới thiệu ở bản phát hành nào và có thay đổi sau đó không.

**Bước 5 — Kiểm tra artifact:** dùng IDE, jar tf hoặc javap để xác nhận classpath thực sự chứa method.

**Bước 6 — Biên dịch sample:** đặt ví dụ trong project dùng cùng dependency management.

**Bước 7 — Integration test:** gọi method với aggregate thật, kiểm tra kết quả database, transaction và trường hợp lỗi.

**Bước 8 — Viết kết luận có phạm vi:** ghi rõ phiên bản đã xác minh, trạng thái API và database/driver đã thử.

Nếu một bước chưa có bằng chứng, ghi rõ phần chưa xác minh thay vì suy đoán.

## 12. Ghi nhận kết quả theo ma trận phiên bản

Khi một bài học mô tả tính năng có khác biệt theo release, nên tạo bảng tương thích:

| Thành phần | Giá trị cần ghi |
|---|---|
| Spring Boot | Phiên bản dự án hoặc dải phiên bản |
| Spring Data release train | Release train tương ứng |
| Spring Data JDBC | Phiên bản artifact đã resolve |
| Spring Data Relational | Phiên bản artifact đã resolve |
| Spring Framework | Phiên bản được dependency management chọn |
| Java | Phiên bản compile/runtime |
| Database | Hệ quản trị và phiên bản |
| JDBC driver | Tên và phiên bản |
| API status | Stable/experimental/deprecated/internal hoặc chưa có metadata |
| Test result | Compile, integration test và cấu hình đã chạy |

Không ghi “hỗ trợ Spring Data JDBC 3.x” nếu chỉ thử một patch release mà chưa kiểm tra dải version. Khi chỉ xác minh một phiên bản, hãy viết “đã kiểm tra trên phiên bản x.y.z”.

### 12.1. Mẫu ghi chú kiểm chứng cho một bài học

Có thể dùng cấu trúc sau trong tài liệu:

~~~text
Tính năng:
Phiên bản Spring Data JDBC:
Phiên bản Spring Data Relational:
Phiên bản Spring Boot:
Database và JDBC driver:
Phiên bản giới thiệu:
Trạng thái API:
Tài liệu/Javadoc tham chiếu:
Cấu hình bắt buộc:
Giới hạn đã biết:
Kiểm thử đã chạy:
Phạm vi kết luận:
~~~

Mẫu này giúp người viết khác cập nhật bài học khi dependency thay đổi. Nó cũng tách bằng chứng thực tế khỏi nhận định hoặc dự đoán.

## 13. Cách diễn đạt trong tài liệu theo trạng thái tính năng

Ngôn ngữ trong bài học phải phản ánh đúng mức độ hỗ trợ.

### 13.1. API đã xác nhận là public và stable

Có thể viết:

> API này có trong phiên bản Spring Data JDBC đã nêu và được tài liệu chính thức mô tả là API công khai. Ví dụ dưới đây đã được biên dịch và kiểm tra với database/driver được ghi trong phần môi trường.

Vẫn phải nêu phiên bản và điều kiện cấu hình.

### 13.2. API experimental hoặc incubating

Nên viết:

> Tính năng này được đánh dấu experimental trong phiên bản được kiểm tra. Tên method, chữ ký hoặc hành vi có thể thay đổi ở release sau. Chỉ sử dụng sau khi đánh giá rủi ro nâng cấp và kiểm tra lại với phiên bản triển khai.

Không viết như một API ổn định được khuyến nghị chung cho mọi dự án.

### 13.3. API preview hoặc milestone

Nêu rõ đó là bản phát hành trước GA, version cụ thể và mục đích thử nghiệm. Không dùng bản milestone làm bằng chứng cho hành vi của bản GA nếu chưa kiểm tra lại.

### 13.4. API deprecated

Nêu phiên bản deprecated, API thay thế và lưu ý migration. Không xóa thông tin về API cũ nếu người đọc cần nâng cấp từ một release còn hỗ trợ nó, nhưng không khuyến nghị dùng cho code mới khi có phương án thay thế chính thức.

### 13.5. Chưa xác định được trạng thái

Nếu không tìm thấy metadata hoặc tuyên bố chính thức:

> Chưa tìm thấy tuyên bố ổn định API cho thành phần này trong nguồn đã kiểm tra. Cần xác nhận với Javadoc/release notes của phiên bản mục tiêu trước khi sử dụng làm hợp đồng dài hạn.

Đừng tự đổi trạng thái “chưa xác định” thành stable hoặc experimental.

## 14. Những nhầm lẫn thường gặp

| Nhầm lẫn | Vì sao sai | Cách xử lý |
|---|---|---|
| Tài liệu current áp dụng cho mọi phiên bản | Current có thể thuộc release mới | Chọn tài liệu đúng version |
| Class có trong JAR nghĩa là API stable | Class có thể experimental hoặc internal | Kiểm tra metadata và Javadoc |
| Có @since nghĩa là được hỗ trợ ổn định | @since chỉ chỉ ra thời điểm xuất hiện | Kiểm tra API status và release notes |
| Không có @API nghĩa là stable | Không phải dự án nào cũng gắn metadata cho mọi API | Dùng nhiều nguồn bằng chứng |
| Mã trên GitHub main dùng được trong release hiện tại | Main có thể chứa thay đổi chưa phát hành | Kiểm tra release tag và artifact |
| Milestone/RC tương đương GA | API còn có thể thay đổi trước GA | Ghi đúng loại version |
| Code biên dịch nghĩa là tính năng hoạt động | Runtime cần bean, config, dialect và driver | Chạy integration test |
| H2 test thành công nghĩa là mọi database đều hỗ trợ | Dialect và driver khác nhau | Test database mục tiêu |
| Repository và JdbcTemplate cùng chạy callback | JdbcTemplate mapping trực tiếp không đi qua Spring Data entity lifecycle | Xác định đúng đường persistence |
| Nâng dependency để hết lỗi là đủ | Có thể tạo xung đột release train | Kiểm tra BOM và dependency tree |
| Một lần test thành công chứng minh toàn bộ dải version | Test chỉ xác nhận môi trường cụ thể | Ghi đúng phạm vi kiểm chứng |

## 15. Checklist trước khi đưa một tính năng vào tài liệu

Trước khi viết một tính năng theo cách khẳng định, hãy có câu trả lời cho các mục sau:

1. Đã xác định version thực tế của spring-data-jdbc chưa?
2. Đã xác nhận spring-data-relational và spring-data-commons tương thích chưa?
3. Đã đọc reference docs của đúng release chưa?
4. Đã xem Javadoc và trạng thái API nếu có chưa?
5. Đã xem release notes và migration guide chưa?
6. Tính năng có cần annotation, bean, property hoặc dependency bổ sung không?
7. Có giới hạn database dialect hoặc JDBC driver không?
8. Ví dụ có biên dịch trên dependency mục tiêu không?
9. Hành vi quan trọng có integration test không?
10. Tài liệu đã ghi rõ version và giới hạn kiểm chứng chưa?

Checklist này là quy trình thu thập bằng chứng cho người viết. Nó không thay thế review nội dung của dự án hoặc kiểm thử chính thức trước khi phát hành.

## 16. Bài tập thực hành

### Bài 1 — Kiểm tra dependency thực tế

1. Mở một dự án Spring Boot dùng Spring Data JDBC.
2. Chạy dependencyInsight hoặc dependency:tree.
3. Ghi phiên bản JDBC, Relational và Commons.
4. Xác định BOM hoặc dependency management đã chọn phiên bản đó.
5. So sánh với phiên bản trên trang tài liệu đang mở.

### Bài 2 — Phân loại API

1. Chọn một public class hoặc method trong Spring Data JDBC.
2. Mở Javadoc đúng version.
3. Tìm @API, @Deprecated và @since nếu có.
4. Đối chiếu release notes và source tag.
5. Ghi trạng thái API cùng bằng chứng; nếu không có tuyên bố thì ghi chưa xác định.

### Bài 3 — Kiểm tra một ví dụ code

1. Tạo sample class dùng API cần tìm hiểu.
2. Biên dịch bằng đúng dependency của dự án.
3. Nếu compile lỗi, phân biệt lỗi import, API không có và version conflict.
4. Chạy integration test với database mục tiêu.
5. Ghi rõ điều kiện test và kết quả.

### Bài 4 — Viết ghi chú tương thích

1. Chọn một tính năng mới được release notes đề cập.
2. Tìm phiên bản đầu tiên có tính năng.
3. Xác định bản phát hành là milestone, RC hay GA.
4. Kiểm tra trạng thái API ở bản GA.
5. Viết một ghi chú tương thích ngắn, không khái quát quá phạm vi đã xác minh.

## 17. Kết luận

Để nhận diện tính năng thử nghiệm và kiểm chứng trước khi đưa vào tài liệu, hãy bắt đầu từ **dependency đã resolve của dự án**, sau đó đối chiếu reference documentation, Javadoc, release notes và source tag đúng phiên bản. Kiểm tra metadata như @API, @Deprecated và @since, nhưng đừng xem việc thiếu annotation là bằng chứng API stable.

Tiếp theo, xác nhận tính năng có trong artifact thực tế, biên dịch ví dụ bằng dependency mục tiêu và chạy integration test với database cùng JDBC driver cần hỗ trợ. Một class có mặt trong JAR chỉ chứng minh nó tồn tại; một ví dụ biên dịch chỉ chứng minh chữ ký tương thích. Hành vi, cấu hình kích hoạt và giới hạn database cần được kiểm tra riêng.

Khi viết, hãy ghi rõ phiên bản đã xác minh, trạng thái API, cấu hình bắt buộc và phạm vi test. Nếu trạng thái hoặc khả năng tương thích chưa có bằng chứng, nói rõ điều đó. Cách làm này giúp tài liệu Spring Data JDBC theo sát phiên bản thực tế và tránh biến tính năng preview hoặc experimental thành lời khuyên ổn định cho người đọc.
