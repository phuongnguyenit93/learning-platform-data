# Cấu hình enhancement trong quá trình build và kiểm tra mã đã được tăng cường

Hibernate có thể sử dụng **bytecode enhancement** để bổ sung hành vi vào class entity đã biên dịch. Quá trình này biến đổi bytecode để Hibernate có thể theo dõi truy cập thuộc tính, tải lazy attribute theo nhu cầu, phát hiện thay đổi theo cơ chế inline dirty tracking và hỗ trợ đồng bộ hai phía của association.

Với **build-time enhancement**, việc biến đổi diễn ra trong quá trình build sau khi mã Java/Kotlin được biên dịch. File source entity vẫn là mã nguồn thông thường; class được đóng gói vào ứng dụng mới là class đã được tăng cường.

Một cấu hình enhancement chỉ có giá trị khi build thực sự chạy enhancer trên đúng output class và ứng dụng chạy đúng những class đã được biến đổi. Vì vậy, công việc không dừng ở việc thêm plugin vào Gradle hoặc Maven. Cần biết feature nào được bật, thời điểm plugin chạy, vị trí class output, cách kiểm tra bytecode và cách kiểm chứng hành vi ở runtime.

Bài học tập trung vào ba việc:

1. Cấu hình Hibernate enhancement trong build Gradle hoặc Maven.
2. Hiểu các feature lazy initialization, dirty tracking và association management.
3. Xác minh class đã được enhance và ứng dụng thực sự sử dụng bytecode đó.

## 1. Bytecode enhancement là gì?

Java source được biên dịch thành bytecode trong các file `.class`. Hibernate có thể biến đổi bytecode này để thêm các hook mà ORM sử dụng khi entity được đọc hoặc thay đổi.

Quy trình tổng quát:

~~~mermaid
flowchart TD
    A["Entity source: .java / .kt"] --> B["Java/Kotlin compiler"]
    B --> C["Compiled entity .class"]
    C --> D["Hibernate bytecode enhancer"]
    D --> E["Enhanced entity .class"]
    E --> F["Đóng gói vào JAR/WAR"]
    F --> G["Ứng dụng chạy với enhanced classes"]
~~~

Enhancement không phải thao tác sửa source code. Build tool xử lý class đã biên dịch, ghi lại bytecode được tăng cường vào output tương ứng hoặc một output được cấu hình.

Ví dụ entity vẫn có thể viết bình thường:

~~~java
@Entity
public class Document {

    @Id
    private Long id;

    private String title;

    @Basic(fetch = FetchType.LAZY)
    private String content;
}
~~~

Khi class được enhance với lazy initialization, Hibernate có thể can thiệp vào việc truy cập thuộc tính `content` để tải giá trị từ database khi cần, thay vì luôn tải nội dung lớn ngay lúc nạp entity.

### 1.1. Enhancement khác với proxy như thế nào?

**Proxy** thường là một đối tượng đại diện cho entity hoặc association chưa được tải. Khi ứng dụng truy cập dữ liệu cần thiết, proxy có thể kích hoạt truy vấn để lấy entity thật.

**Bytecode enhancement** biến đổi chính class entity để thêm khả năng hỗ trợ ORM. Các feature của enhancement có thể bổ sung hoặc thay đổi cách Hibernate thực hiện lazy loading và dirty tracking.

| Cơ chế | Nơi tác động | Ví dụ |
| --- | --- | --- |
| Entity proxy | Đối tượng đại diện cho entity | Lazy reference tới Customer |
| Bytecode enhancement | Bytecode của class entity | Lazy basic attribute, inline dirty tracking |
| Fetch plan | Cách truy vấn tải association | JOIN FETCH, EntityGraph, batch fetching |

Enhancement không có nghĩa mọi association tự động lazy hoặc mọi truy vấn đều ít hơn. Mapping, fetch plan và code truy cập vẫn quyết định dữ liệu nào cần được tải.

### 1.2. Enhancement thường được thực hiện khi nào?

Hibernate hỗ trợ enhancement theo những cách khác nhau tùy môi trường. Trong ứng dụng build bằng Gradle/Maven, **build-time enhancement** thường dễ kiểm soát vì bytecode được biến đổi trước khi đóng gói và chạy.

Các bước phổ biến:

1. Compile source.
2. Chạy enhancer trên compiled entity classes.
3. Chạy test hoặc đóng gói từ output đã enhance.
4. Đưa artifact đó vào runtime.

Cần bảo đảm enhancer chạy sau compiler. Nếu plugin chỉ được khai báo nhưng không tham gia lifecycle/task thực tế, class có thể vẫn là bytecode nguyên bản.

## 2. Các feature chính của Hibernate enhancement

Hibernate có các tùy chọn enhancement thường gặp:

- `enableLazyInitialization`
- `enableDirtyTracking`
- `enableAssociationManagement`

Các tùy chọn này độc lập về mục đích. Không nhất thiết phải bật tất cả cho mọi ứng dụng.

### 2.1. Lazy initialization

Lazy attribute loading cho phép Hibernate trì hoãn tải một số thuộc tính persistent cho tới khi ứng dụng thực sự truy cập chúng.

Ví dụ:

~~~java
@Entity
@Table(name = "documents")
public class Document {

    @Id
    @GeneratedValue
    private Long id;

    private String title;

    @Basic(fetch = FetchType.LAZY)
    @LazyGroup("document-content")
    @Column(columnDefinition = "text")
    private String content;

    @Basic(fetch = FetchType.LAZY)
    @LazyGroup("document-content")
    @Column(columnDefinition = "text")
    private String extractedText;
}
~~~

`@LazyGroup` là annotation Hibernate. Hai thuộc tính trong cùng group có thể được tải cùng nhau khi group được khởi tạo. Các thuộc tính không khai báo group có thể thuộc group mặc định theo quy tắc Hibernate.

Khi ứng dụng tải Document chỉ để hiển thị title, Hibernate có thể chưa cần tải content lớn. Khi code gọi `document.getContent()`, interceptor được enhancement hỗ trợ có thể yêu cầu provider tải lazy state.

**Lưu ý:** `FetchType.LAZY` trên basic attribute là yêu cầu lazy mà provider có thể xem là hint theo hợp đồng JPA; khả năng lazy basic property của Hibernate cần bytecode enhancement phù hợp. Nếu không có enhancement, provider có thể tải field sớm hoặc không thực hiện property-level lazy như mong muốn.

### 2.2. Inline dirty tracking

Dirty checking thông thường có thể so sánh trạng thái hiện tại của entity với snapshot mà Hibernate lưu khi entity được nạp hoặc đồng bộ.

Với **inline dirty tracking**, enhancer bổ sung cơ chế đánh dấu thuộc tính thay đổi khi code cập nhật field. Hibernate có thể dùng thông tin đó để xác định field nào dirty, giảm một số chi phí so sánh snapshot.

Ví dụ:

~~~java
Document document = em.find(Document.class, id);

document.rename("Tài liệu mới");
// Enhanced class có thể đánh dấu title là dirty.

em.flush();
~~~

Dirty tracking không làm UPDATE chạy ngay khi setter được gọi. Hibernate vẫn đồng bộ thay đổi theo flush mode và transaction. Enhancement giúp provider nhận biết thay đổi; flush/commit quyết định lúc SQL được thực thi và transaction được xác nhận.

Một lưu ý với các giá trị mutable: nếu một thuộc tính giữ tham chiếu tới object mutable rồi object đó bị sửa bên trong mà không có thao tác ghi field mà enhancer quan sát được, inline tracking có thể không nhận ra theo cách bạn mong đợi. Cần hiểu loại dữ liệu, custom type và chiến lược dirty checking đang dùng; không giả định inline tracking luôn thay thế mọi kiểm tra snapshot.

### 2.3. Bidirectional association management

Với quan hệ hai chiều, code ứng dụng thường phải giữ hai phía của object graph đồng bộ.

Ví dụ:

~~~java
@Entity
public class Department {

    @OneToMany(mappedBy = "department")
    private Set<Employee> employees = new HashSet<>();

    public void addEmployee(Employee employee) {
        employees.add(employee);
        employee.setDepartment(this);
    }
}
~~~

Nếu chỉ thêm Employee vào collection mà không cập nhật phía Employee.department, hai phía trong RAM có thể không nhất quán. Hibernate enhancement với association management có thể hỗ trợ tự đồng bộ hai phía cho các association được mapping phù hợp.

Tuy nhiên, feature này không thay thế việc thiết kế owning side, helper method và quy tắc domain. Hãy kiểm tra rõ cách ứng dụng thay đổi association, tránh để cả enhancer lẫn code nghiệp vụ thực hiện những thao tác phụ không mong muốn.

### 2.4. Bảng so sánh feature

| Feature | Mục đích | Khi cân nhắc bật |
| --- | --- | --- |
| Lazy initialization | Trì hoãn tải lazy attributes | Entity có basic field lớn hoặc association cần lazy state |
| Dirty tracking | Theo dõi field thay đổi theo kiểu inline | Workload nhiều managed entities hoặc muốn giảm chi phí snapshot comparison |
| Association management | Hỗ trợ đồng bộ hai phía association | Mapping hai chiều được thiết kế rõ và muốn provider hỗ trợ giữ object graph nhất quán |

Không bật một feature chỉ vì plugin cung cấp sẵn. Mỗi feature nên có use case, kiểm thử và hiểu biết về ảnh hưởng tới code hiện tại.

## 3. Cấu hình build-time enhancement bằng Gradle

Hibernate cung cấp Gradle plugin có plugin ID `org.hibernate.orm`. Version của plugin nên **khớp với version Hibernate ORM runtime** mà ứng dụng sử dụng, để enhancer và runtime hiểu cùng định dạng/semantics bytecode.

Ví dụ Gradle Groovy DSL:

~~~groovy
plugins {
    id 'java'
    id 'org.hibernate.orm' version 'YOUR_HIBERNATE_VERSION'
}

dependencies {
    implementation 'org.hibernate.orm:hibernate-core:YOUR_HIBERNATE_VERSION'
}

hibernate {
    enhancement {
        enableLazyInitialization = true
        enableDirtyTracking = true
        enableAssociationManagement = true
    }
}
~~~

Thay `YOUR_HIBERNATE_VERSION` bằng version Hibernate ORM của dự án. Ví dụ cấu hình chỉ ra cấu trúc; không nên dùng một version plugin khác runtime nếu chưa xác nhận compatibility.

### 3.1. Gradle Kotlin DSL

Với file `build.gradle.kts`:

~~~kotlin
plugins {
    java
    id("org.hibernate.orm") version "YOUR_HIBERNATE_VERSION"
}

dependencies {
    implementation("org.hibernate.orm:hibernate-core:YOUR_HIBERNATE_VERSION")
}

hibernate {
    enhancement {
        enableLazyInitialization = true
        enableDirtyTracking = true
        enableAssociationManagement = true
    }
}
~~~

Gradle Kotlin DSL dùng cú pháp Kotlin, còn các thuộc tính enhancement vẫn có cùng ý nghĩa.

### 3.2. Dùng version catalog hoặc dependency management

Trong dự án có version catalog, BOM hoặc convention plugin, hãy tập trung version Hibernate tại một nguồn quản lý chung. Mục tiêu là tránh trường hợp:

- Gradle enhancement plugin ở version A.
- `hibernate-core` ở version B.
- Một dependency transitively kéo Hibernate version C.

Nếu dự án dùng Hibernate BOM hoặc Spring Boot dependency management, hãy kiểm tra version runtime thực tế bằng dependency insight, không chỉ nhìn khai báo trực tiếp.

### 3.3. Enhancement trong multi-module Gradle

Với dự án nhiều module, plugin cần được áp dụng ở module **thực sự biên dịch entity classes**. Nếu entity nằm trong module `domain`, chỉ cấu hình plugin ở module `application` có thể không biến đổi class trong dependency đã được build trước đó.

Hãy xác định:

- Module nào chứa `@Entity`.
- Module nào áp dụng Hibernate Gradle plugin.
- Output class nào được đóng gói.
- Module test/application có sử dụng đúng artifact đã enhance hay không.

Không giả định plugin ở root project tự động enhance mọi subproject nếu chưa cấu hình áp dụng plugin và task cho từng module.

### 3.4. Kiểm tra task và lifecycle của Gradle

Tên task và wiring có thể thay đổi theo plugin/phiên bản. Dùng:

~~~bash
./gradlew tasks --all
~~~

để xem các task liên quan, và:

~~~bash
./gradlew clean classes
~~~

để chạy clean build và compile class. Hibernate Gradle plugin tích hợp enhancement vào lifecycle compile/classes theo cách của plugin; cần xác nhận task graph của dự án thay vì đoán từ tên task.

Nếu dùng Kotlin, Scala hoặc source set tùy chỉnh, xác nhận output compile tương ứng đã nằm trong phạm vi enhancer.

## 4. Cấu hình enhancement bằng Maven

Với Maven, Hibernate cung cấp plugin:

`org.hibernate.orm.tooling:hibernate-enhance-maven-plugin`

Plugin cần chạy sau khi source được compile, thường ở phase `process-classes`.

Ví dụ cấu hình trong `pom.xml`:

~~~xml
<properties>
    <hibernate.version>YOUR_HIBERNATE_VERSION</hibernate.version>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.hibernate.orm.tooling</groupId>
            <artifactId>hibernate-enhance-maven-plugin</artifactId>
            <version>YOUR_HIBERNATE_VERSION</version>
            <executions>
                <execution>
                    <phase>process-classes</phase>
                    <goals>
                        <goal>enhance</goal>
                    </goals>
                </execution>
            </executions>
            <configuration>
                <enableLazyInitialization>true</enableLazyInitialization>
                <enableDirtyTracking>true</enableDirtyTracking>
                <enableAssociationManagement>true</enableAssociationManagement>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Thay cả hai placeholder bằng version Hibernate ORM phù hợp. Trong dự án có property/version management, nên dùng cùng một giá trị quản lý cho dependency và enhancer plugin để tránh lệch version.

### 4.1. Vì sao chọn process-classes?

Maven lifecycle có thứ tự compile rồi mới tới process-classes. Enhancer cần class đã biên dịch để biến đổi bytecode, nên phase này là một điểm thích hợp.

Có thể chạy:

~~~bash
mvn clean process-classes
~~~

hoặc:

~~~bash
mvn clean verify
~~~

`verify` đi qua các phase trước đó, bao gồm process-classes và test/package tùy lifecycle. Kiểm tra log Maven để xác nhận goal `enhance` thực sự được thực thi.

### 4.2. Entity nằm trong test source

Thông thường entity production nằm trong `src/main/java` và được enhance trong process-classes. Nếu dự án có entity test fixture riêng trong `src/test/java`, cần xác định test classes có cần enhancement hay không và cấu hình phase/plugin execution tương ứng. Không giả định cấu hình main classes tự động enhance mọi test fixture.

### 4.3. Multi-module Maven

Nếu entity nằm trong một module con, plugin phải được cấu hình và chạy trong module đó hoặc được kế thừa từ parent theo cấu trúc build. Chỉ khai báo plugin ở parent nhưng không có execution/configuration áp dụng phù hợp có thể không tạo enhancement ở nơi cần thiết.

Kiểm tra artifact của module chứa entity, không chỉ artifact executable cuối cùng.

## 5. Chọn feature nào để bật?

Một cấu hình tối thiểu có thể chỉ bật lazy initialization:

~~~groovy
hibernate {
    enhancement {
        enableLazyInitialization = true
    }
}
~~~

Nếu ứng dụng muốn dùng inline dirty tracking:

~~~groovy
hibernate {
    enhancement {
        enableLazyInitialization = true
        enableDirtyTracking = true
    }
}
~~~

Nếu cần association management:

~~~groovy
hibernate {
    enhancement {
        enableLazyInitialization = true
        enableDirtyTracking = true
        enableAssociationManagement = true
    }
}
~~~

Các cấu hình trên là ví dụ Gradle Groovy DSL. Với Maven/Kotlin DSL, dùng tên thuộc tính tương ứng trong cấu hình plugin.

### 5.1. Lazy initialization cần mapping lazy phù hợp

Bật enhancer không có nghĩa tất cả field tự chuyển thành lazy. Entity vẫn phải có mapping thể hiện thuộc tính cần tải trễ, ví dụ:

~~~java
@Basic(fetch = FetchType.LAZY)
private String largeText;
~~~

Hoặc association:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;
~~~

Lazy loading còn chịu tác động của query fetch join, EntityGraph, fetch profile, batch fetching, trạng thái persistence context và thời điểm ứng dụng truy cập thuộc tính.

### 5.2. Dirty tracking không thay đổi transaction semantics

Ngay cả khi entity enhanced và Hibernate đánh dấu field dirty ngay lúc field thay đổi, SQL vẫn phụ thuộc flush. Đừng hiểu dirty tracking là auto-save:

~~~java
document.setTitle("Bản mới");
// Chưa chắc SQL đã chạy.

em.flush();
// Đồng bộ pending changes.

tx.commit();
// Xác nhận transaction.
~~~

### 5.3. Association management không thay mapping ownership

Nếu association có owning side là Employee.department, enhancer không biến phía inverse thành owning side theo ý muốn. Database vẫn được cập nhật theo quy tắc owning side của JPA. Hãy giữ mapping đúng và test việc thêm/bỏ association từ từng phía.

## 6. Kiểm tra build có thực sự chạy enhancement không

Đây là bước quan trọng. Một file build chứa cấu hình plugin **không đủ chứng minh class đã được enhance**.

Cần kiểm tra ở ít nhất hai mức:

1. **Bytecode/build output:** class đã biên dịch có dấu hiệu được enhancer biến đổi hay không.
2. **Runtime behavior:** ứng dụng đang load chính class enhanced và feature cần dùng hoạt động đúng hay không.

### 6.1. Xác định output directory

Thông thường:

| Build tool | Output class phổ biến |
| --- | --- |
| Gradle Java | `build/classes/java/main` |
| Gradle Kotlin | `build/classes/kotlin/main` |
| Maven | `target/classes` |

Đường dẫn có thể thay đổi nếu dự án dùng custom source set, Kotlin plugin, module layout hoặc output directory riêng.

Sau khi chạy build, xác định đúng class entity trong output. Đừng kiểm tra source folder hoặc một thư mục IDE cũ rồi kết luận enhancement thành công.

### 6.2. Clean build trước khi xác minh

Gradle:

~~~bash
./gradlew clean classes
~~~

Maven:

~~~bash
mvn clean process-classes
~~~

Clean giúp loại class output cũ chưa được enhance. Nếu chỉ build incremental, có thể khó biết class hiện tại là kết quả mới hay bytecode tồn từ lần build trước.

Nếu build task không chạy enhancer, clean build cũng không tự sửa được cấu hình; nó chỉ làm trạng thái output rõ ràng hơn.

## 7. Dùng javap để kiểm tra bytecode

JDK cung cấp công cụ `javap` để xem cấu trúc class và bytecode.

Gradle:

~~~bash
javap -p -classpath build/classes/java/main com.example.domain.Document
~~~

Maven:

~~~bash
javap -p -classpath target/classes com.example.domain.Document
~~~

Tùy version Hibernate và feature được bật, class enhanced có thể triển khai các interface/hook liên quan như:

- `org.hibernate.engine.spi.Managed`
- `org.hibernate.engine.spi.PersistentAttributeInterceptable`
- `org.hibernate.engine.spi.SelfDirtinessTracker`

Có thể thấy các method synthetic do enhancer tạo, thường có tiền tố `$$_hibernate_`, ví dụ hook interceptor, dirty attributes hoặc association management. **Tên interface và method cụ thể là chi tiết implementation, có thể thay đổi theo Hibernate version và feature.**

Đừng viết script kiểm tra cứng một danh sách method nội bộ rồi coi đó là API ổn định qua mọi version. Dùng javap để quan sát class output của đúng phiên bản dự án.

### 7.1. Xem bytecode chi tiết

~~~bash
javap -p -c -classpath build/classes/java/main com.example.domain.Document
~~~

Tùy chọn `-c` hiển thị bytecode của method. Có thể kiểm tra getter/setter hoặc field access đã được biến đổi để gọi hook enhancement hay chưa.

Đây là bằng chứng kỹ thuật mạnh hơn việc chỉ thấy plugin trong `build.gradle`. Tuy vậy, bytecode output cần được kết hợp với runtime test để chắc ứng dụng thực sự load đúng class đó.

### 7.2. Nếu javap không tìm thấy class

Kiểm tra:

- Tên package/class đầy đủ.
- Module đang đứng và output directory.
- Source set là Java hay Kotlin.
- Build đã chạy compile và enhancement chưa.
- Class có được đóng gói từ output khác hay không.

Ví dụ class `com.example.domain.Document` phải được tìm trong classpath có root tương ứng với package path `com/example/domain/Document.class`.

## 8. Kiểm tra bằng reflection và Hibernate SPI

Trong test hoặc diagnostic code, có thể kiểm tra marker interfaces mà Hibernate dùng cho enhanced entity.

Ví dụ:

~~~java
import org.hibernate.engine.spi.PersistentAttributeInterceptable;
import org.hibernate.engine.spi.SelfDirtinessTracker;

Document document = em.find(Document.class, id);

boolean supportsLazyInterception =
    document instanceof PersistentAttributeInterceptable;

boolean supportsInlineDirtyTracking =
    document instanceof SelfDirtinessTracker;

System.out.println(supportsLazyInterception);
System.out.println(supportsInlineDirtyTracking);
~~~

Nếu feature tương ứng được bật và class được enhance, các interface phù hợp có thể xuất hiện. Tuy nhiên, đây là **Hibernate SPI**, không phải domain API mà business code nên phụ thuộc để vận hành.

Dùng kiểm tra này trong diagnostic/integration test gắn với version Hibernate cụ thể. Nếu upgrade ORM, cập nhật cách kiểm tra theo tài liệu và bytecode thực tế.

### 8.1. Reflection kiểm tra class được load từ đâu

Có thể in nguồn class:

~~~java
Class<?> type = Document.class;

System.out.println(
    type.getProtectionDomain()
        .getCodeSource()
        .getLocation()
);
~~~

Điều này giúp phát hiện runtime đang load class từ JAR/module output nào. Nếu build đã enhance `build/classes/...` nhưng test runner hoặc IDE lại load một class khác từ thư mục output cũ, hành vi có thể không như mong đợi.

## 9. Kiểm tra lazy attribute thực sự hoạt động

Một test nên kiểm tra hành vi, không chỉ marker interface.

Entity:

~~~java
@Entity
@Table(name = "documents")
public class Document {

    @Id
    private Long id;

    private String title;

    @Basic(fetch = FetchType.LAZY)
    @LazyGroup("content")
    private String content;

    public String getTitle() {
        return title;
    }

    public String getContent() {
        return content;
    }
}
~~~

Test ý tưởng:

~~~java
Document document = em.find(Document.class, documentId);

boolean loadedBefore =
    em.getEntityManagerFactory()
      .getPersistenceUnitUtil()
      .isLoaded(document, "content");

String content = document.getContent();

boolean loadedAfter =
    em.getEntityManagerFactory()
      .getPersistenceUnitUtil()
      .isLoaded(document, "content");
~~~

Trong một mapping và provider hỗ trợ lazy basic attribute, mục tiêu là `content` chưa loaded sau khi root entity được nạp, rồi được khởi tạo khi truy cập getter trong persistence context hợp lệ.

Có thể dùng SQL logging hoặc `StatementInspector` để xác nhận query phụ thực sự được phát khi đọc content. Kết quả còn phụ thuộc query ban đầu có fetch field này không, second-level cache, lazy group, transaction và provider.

### 9.1. Đừng để query ban đầu vô tình fetch thuộc tính

Nếu query dùng fetch plan lấy toàn bộ field/association hoặc một projection khác, field có thể đã được nạp. Khi đó test không chứng minh lazy loading không hoạt động; test đã yêu cầu dữ liệu ngay từ đầu.

Thiết kế test với query rõ ràng, dữ liệu có kích thước đủ lớn để phân biệt hành vi và kiểm tra SQL.

### 9.2. Persistence context phải còn sử dụng được

Lazy attribute cần persistence context/session hợp lệ để tải state. Nếu entity detached hoặc session đã đóng trước khi getter kích hoạt lazy loading, có thể gặp lỗi lazy initialization ngoài session.

Enhancement không loại bỏ yêu cầu về lifecycle của persistence context.

## 10. Kiểm tra inline dirty tracking

Một test tích hợp có thể:

1. Tải entity managed.
2. Thay đổi một field persistent.
3. Flush.
4. Quan sát SQL UPDATE và parameter.
5. Kiểm tra version nếu entity có `@Version`.
6. Đảm bảo field không đổi không bị ghi ngoài mapping/update strategy dự kiến.

Nếu cần kiểm tra marker, Hibernate có interface `SelfDirtinessTracker` trong SPI; tùy phiên bản, có thể đọc dirty attribute names qua method synthetic/interface tương ứng. Vì method này là chi tiết SPI, không nên dùng trong logic nghiệp vụ.

### 10.1. Thử cả mutable value

Nếu entity có thuộc tính mutable, ví dụ custom value object hoặc cấu trúc có thể thay đổi bên trong, hãy kiểm tra việc thay đổi nội bộ mà không gọi setter có được nhận biết không. Inline tracking chủ yếu theo dõi thay đổi attribute mà enhancer quan sát; không nên mặc định nó phát hiện mọi thay đổi sâu của mọi object.

Nếu loại dữ liệu cần snapshot comparison hoặc custom mutability plan, cần cấu hình/test phù hợp.

## 11. Kiểm tra association management

Với association hai chiều:

~~~java
Department department = em.find(Department.class, departmentId);
Employee employee = em.find(Employee.class, employeeId);

department.getEmployees().add(employee);
~~~

Nếu bật association management enhancement và mapping phù hợp, Hibernate có thể hỗ trợ cập nhật phía đối ứng khi một bên được thay đổi. Hãy kiểm tra trong test:

- Collection phía Department có chứa Employee.
- `employee.getDepartment()` có trỏ về Department như mong đợi.
- Owning side thực sự được đồng bộ.
- Flush tạo đúng foreign key.
- Reload trong persistence context mới vẫn có quan hệ đúng.

Tuy nhiên, code domain nên có API thay đổi quan hệ rõ ràng, ví dụ `department.addEmployee(employee)`. Đừng phụ thuộc vào việc mọi cách sửa collection trực tiếp đều tự động phù hợp với invariant nghiệp vụ.

## 12. Kiểm tra artifact cuối cùng, không chỉ class output

Build có thể tạo class enhanced nhưng bước đóng gói lại lấy class từ một output khác. Vì vậy, nên xác minh JAR/WAR cuối cùng.

Maven:

~~~bash
jar tf target/application.jar
~~~

Với Spring Boot executable JAR, entity có thể nằm trong dependency JAR ở `BOOT-INF/lib` hoặc class ở `BOOT-INF/classes` tùy module/build. Có thể trích artifact và dùng `javap` với classpath phù hợp để kiểm tra.

Gradle:

~~~bash
jar tf build/libs/application.jar
~~~

Tên file và cấu trúc archive phụ thuộc packaging plugin. Điều cần xác nhận là **class được deploy chính là class đã enhance**, không phải bản compile chưa qua enhancer.

### 12.1. Kiểm tra classpath runtime

Nếu entity nằm trong module domain riêng, application có thể dùng artifact đã publish/cache từ lần build cũ. Hãy xác định JAR mà runtime load qua `CodeSource`, sau đó kiểm tra chính artifact đó.

Một bài test chạy trong Gradle/Maven thường đáng tin hơn việc chỉ chạy main class từ IDE nếu IDE không gọi enhancer.

## 13. Cấu hình trong CI và build reproducible

Để enhancement không phụ thuộc máy developer:

- Khai báo plugin và version trong build script.
- Đưa enhancement vào lifecycle/task chuẩn của build.
- Chạy clean build trong CI.
- Chạy integration tests sau enhancement.
- Đóng gói từ output đã enhanced.
- Không sửa thủ công class trong build output.
- Không copy class chưa enhance đè lên class enhanced ở bước packaging.
- Giữ plugin và Hibernate runtime cùng version tương thích.

Một pipeline minh họa:

~~~text
Checkout source
    ↓
Resolve dependencies
    ↓
Compile entities
    ↓
Hibernate enhancement
    ↓
Unit / integration tests
    ↓
Package JAR/WAR
    ↓
Verify artifact
    ↓
Publish/deploy
~~~

Nếu build incremental trên máy developer thành công nhưng CI clean build thất bại, hãy kiểm tra task dependency và phase execution. Enhancement phải là một phần của build reproducible, không phải thao tác IDE cá nhân.

## 14. Multi-module, test fixtures và IDE

### 14.1. Entity nằm trong module riêng

Nếu module `domain-model` chứa entity còn `web-app` chỉ phụ thuộc module đó, cần enhance class trong `domain-model`. Cấu hình enhancer chỉ ở web-app có thể không biến đổi class dependency đã biên dịch và đóng gói trước.

### 14.2. Test fixture cũng có thể chứa entity

Nếu integration test tạo entity class nằm trong `src/test/java`, enhancer main source không tự động xử lý class test. Chỉ thêm execution cho test output khi thực sự cần; tránh enhance lặp một class đã được xử lý.

### 14.3. IDE có thể chạy class chưa enhance

Một số IDE compile Java trực tiếp ra output riêng mà không chạy Gradle/Maven enhancer. Khi test bằng IDE, class có thể chưa được tăng cường dù command-line build đã cấu hình đúng.

Cách xử lý:

- Dùng Gradle/Maven run configuration để chạy test cần enhancement.
- Hoặc cấu hình IDE build delegate sang build tool.
- Xác minh classpath thực tế trong test.
- Clean output IDE cũ khi cần.

Đừng kết luận plugin lỗi chỉ từ một lần chạy IDE nếu IDE không thực hiện task enhancement.

## 15. Các lỗi thường gặp khi cấu hình

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Plugin khai báo nhưng class không có hook enhancement | Task/phase enhancer chưa chạy | Xem Gradle task graph hoặc Maven log |
| Lazy basic attribute vẫn tải sớm | Thiếu enhancement, mapping/query đã fetch field hoặc provider xem LAZY là hint | Kiểm tra bytecode, SQL và fetch plan |
| Dirty tracking marker không xuất hiện | Feature chưa bật hoặc class không được enhance | Kiểm tra plugin config và javap |
| Runtime không có marker dù build output có | Runtime load JAR/class khác | In CodeSource, kiểm tra classpath |
| Local chạy được, CI không | Build phụ thuộc IDE/incremental output | Chạy clean build và test trên CI |
| Một module enhanced, module khác không | Plugin chỉ áp dụng ở module không chứa entity | Kiểm tra module chứa @Entity |
| Test entity không enhanced | Enhancer chỉ xử lý main classes | Kiểm tra test output và execution phase |
| Build lỗi sau nâng Hibernate | Plugin/runtime version không đồng bộ hoặc bytecode compatibility | Đồng bộ version và đọc lỗi enhancer |
| Association hai chiều không nhất quán | Mapping/owning side hoặc feature chưa được bật/không áp dụng | Test thay đổi cả hai phía và reload |
| Build chạy enhancer nhiều lần | Task/plugin execution bị cấu hình lặp | Kiểm tra task graph và Maven executions |

## 16. Khi nào không nên bật tất cả feature ngay lập tức?

Enhancement tác động tới bytecode và cách Hibernate quan sát entity. Với dự án cũ hoặc domain model phức tạp, bật tất cả feature cùng lúc có thể làm khó xác định nguồn gốc thay đổi hành vi.

Một rollout thận trọng:

1. Xác định use case cần enhancement.
2. Bật một feature trước, thường là feature lazy property hoặc dirty tracking mà ứng dụng thực sự cần.
3. Chạy clean build.
4. Kiểm tra class bytecode.
5. Viết integration test chứng minh behavior.
6. Đo SQL, số lần load và hiệu năng.
7. Bật feature tiếp theo nếu có lợi ích rõ.
8. Chạy lại các test association/lifecycle.

Không phải ứng dụng nào cũng cần association management enhancement hoặc lazy basic attributes. Cấu hình tối thiểu dễ giải thích và vận hành hơn.

## 17. Enhancement không thay thế fetch planning

Ngay cả khi lazy initialization được bật, query vẫn có thể tải association bằng:

- `JOIN FETCH`.
- `EntityGraph`.
- Fetch profile.
- Batch fetching.
- Subselect fetching.
- EAGER mapping.

Nếu query đã fetch association, enhancement không thể làm dữ liệu đó “chưa được tải” trở lại. Enhancement bổ sung khả năng cho class; fetch plan quyết định query cụ thể cần lấy dữ liệu nào.

Tương tự, lazy loading không đảm bảo tránh N+1. Nếu code lặp qua 100 entity và truy cập một lazy association chưa được batch fetch, vẫn có thể tạo nhiều truy vấn. Cần kết hợp enhancement với fetch plan và đo SQL.

## 18. Một ví dụ kiểm chứng end-to-end

Giả sử dự án có entity:

~~~java
@Entity
@Table(name = "articles")
public class Article {

    @Id
    @GeneratedValue
    private Long id;

    private String title;

    @Basic(fetch = FetchType.LAZY)
    @LazyGroup("article-body")
    @Column(columnDefinition = "text")
    private String body;

    @Version
    private Long version;

    public String getTitle() {
        return title;
    }

    public String getBody() {
        return body;
    }

    public void rename(String value) {
        title = value;
    }
}
~~~

Cấu hình build bật lazy initialization và dirty tracking. Test có thể thực hiện:

~~~java
@Test
@Transactional
void enhancedArticleSupportsLazyStateAndDirtyTracking() {
    Article article = entityManager.find(Article.class, articleId);

    boolean bodyLoaded = entityManager
        .getEntityManagerFactory()
        .getPersistenceUnitUtil()
        .isLoaded(article, "body");

    String body = article.getBody();

    boolean bodyLoadedAfterAccess = entityManager
        .getEntityManagerFactory()
        .getPersistenceUnitUtil()
        .isLoaded(article, "body");

    article.rename("Tiêu đề mới");
    entityManager.flush();

    assertThat(body).isNotNull();
    assertThat(bodyLoadedAfterAccess).isTrue();
}
~~~

Test minh họa cách quan sát lazy attribute. Assertion rằng `bodyLoaded` phải false chỉ nên thêm khi test query/fetch plan bảo đảm field chưa được nạp và môi trường thực sự hỗ trợ property-level lazy. Không nên ép assertion này trong test mà query đã fetch toàn bộ Article.

Đối với dirty tracking, kiểm tra SQL UPDATE/version hoặc marker SPI theo phiên bản; không suy ra dirty tracking chỉ từ việc flush thành công, vì dirty checking snapshot thông thường cũng có thể tạo cùng UPDATE.

### 18.1. Kiểm chứng bytecode riêng

Sau build, chạy `javap` trên Article trong output directory và xác nhận class có hook/interceptor phù hợp. Tiếp theo, in `CodeSource` trong test để chắc Article runtime là class từ output đã enhance.

Kết hợp build evidence, bytecode evidence và runtime behavior giúp phân biệt ba lỗi khác nhau: plugin không chạy, enhancer chạy sai class, hoặc runtime load nhầm artifact.

## 19. Checklist triển khai

### Cấu hình build

- [ ] Chọn Gradle hoặc Maven plugin đúng với Hibernate ORM.
- [ ] Đồng bộ version enhancer và runtime.
- [ ] Bật feature có use case cụ thể.
- [ ] Đặt enhancer sau bước compile.
- [ ] Cấu hình đúng module/source set chứa entity.
- [ ] Tránh enhancement bị bỏ qua hoặc chạy lặp không chủ đích.

### Xác minh class

- [ ] Chạy clean build.
- [ ] Xác định đúng output directory.
- [ ] Dùng `javap -p` xem class/interface.
- [ ] Dùng `javap -p -c` khi cần xem bytecode.
- [ ] Kiểm tra marker interfaces/hook phù hợp version.
- [ ] Xác minh classpath runtime và artifact cuối.

### Xác minh behavior

- [ ] Test lazy attribute với fetch plan không tải sẵn field.
- [ ] Kiểm tra SQL khi lazy attribute được truy cập.
- [ ] Test dirty tracking qua thay đổi field và flush.
- [ ] Test association management nếu feature được bật.
- [ ] Test lifecycle khi entity detached/session đóng.
- [ ] Chạy test qua Gradle/Maven và CI clean build.

## 20. Bài tập thực hành

### Bài 1 — Xác định build stage

Vì sao Hibernate enhancer cần xử lý class sau khi Java/Kotlin compiler tạo file `.class`? Nếu enhancer chạy trước compiler, nó có thể biến đổi entity nào?

### Bài 2 — Gradle

Viết cấu hình Gradle sử dụng plugin `org.hibernate.orm`, bật lazy initialization và dirty tracking. Vì sao version plugin nên khớp với `hibernate-core`?

### Bài 3 — Maven

Thêm `hibernate-enhance-maven-plugin` vào phase `process-classes`. Giải thích vì sao cấu hình plugin nhưng không có execution/goal phù hợp có thể khiến class không được enhance.

### Bài 4 — Bytecode

Sau build, dùng `javap -p` và `javap -p -c` để kiểm tra một entity. Những interface hoặc method hook nào có thể xuất hiện? Vì sao không nên coi tên synthetic method là API ổn định?

### Bài 5 — Lazy attribute

Một field `@Basic(fetch = LAZY)` vẫn được tải ngay. Nêu ít nhất ba nguyên nhân có thể: thiếu enhancement, query đã fetch field, hoặc fetch configuration khác. Cách dùng SQL log và PersistenceUnitUtil để phân biệt?

### Bài 6 — Dirty tracking

Một entity có inline dirty tracking nhưng UPDATE vẫn chỉ chạy khi flush. Giải thích vì sao enhancement không biến setter thành auto-commit.

### Bài 7 — IDE và CI

Build Gradle clean có enhancement, nhưng chạy test bằng IDE lại không thấy marker interface. Những classpath/build output nào cần kiểm tra?

### Bài 8 — Multi-module

Entity nằm trong module `domain`, enhancer chỉ được cấu hình trong module `application`. Vì sao artifact domain có thể vẫn chứa class chưa enhanced? Cần đặt plugin ở đâu?

### Gợi ý trả lời

- **Bài 1:** Enhancer biến đổi bytecode đã biên dịch; trước compile chưa có class entity để xử lý.
- **Bài 2:** Dùng plugin và runtime cùng version tương thích để tránh enhancer tạo bytecode không phù hợp provider.
- **Bài 3:** Plugin cần goal được gắn vào lifecycle phase sau compile.
- **Bài 4:** Có thể thấy interface/hook Hibernate như PersistentAttributeInterceptable, SelfDirtinessTracker và method `$$_hibernate_...`; đây là chi tiết implementation theo version.
- **Bài 5:** Kiểm tra enhancer, query fetch plan, trạng thái loaded và SQL thực tế.
- **Bài 6:** Dirty tracking đánh dấu thay đổi; flush mới đồng bộ SQL và commit mới xác nhận transaction.
- **Bài 7:** IDE có thể compile vào output khác và bỏ qua enhancer; kiểm tra CodeSource, classpath và build delegation.
- **Bài 8:** Cần enhance trong module thực sự compile entity classes, sau đó đóng gói và sử dụng artifact đã enhance.

---

**Ghi nhớ:** Build-time enhancement biến đổi bytecode entity sau khi compile. Gradle/Maven phải chạy đúng plugin, đúng version và đúng module chứa entity. Hãy xác minh class output bằng `javap`, kiểm tra class runtime thực sự được load và viết integration test cho lazy loading, dirty tracking hoặc association management mà ứng dụng sử dụng. **Cấu hình plugin chỉ là khai báo; bytecode và hành vi runtime mới chứng minh enhancement đã có hiệu lực.**
