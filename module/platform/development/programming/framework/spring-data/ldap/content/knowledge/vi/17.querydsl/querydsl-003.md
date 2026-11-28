# Tổ chức annotation processing trong bản dựng

> **Chương:** Querydsl  
> **Module:** SPRING_DATA_LDAP — truy cập dịch vụ thư mục LDAP bằng Spring Data LDAP, ánh xạ entry phân cấp qua object-directory mapping (ODM), thao tác với `LdapRepository` hoặc `LdapTemplate`.

**Annotation processing** là bước chạy bộ xử lý annotation trong quá trình biên dịch Java để tạo thêm mã nguồn. Khi tích hợp Querydsl với Spring Data LDAP, bước này sinh ra các lớp **Q-type** từ entity được đánh dấu bằng `@Entry`. Nhờ Q-type, ứng dụng có thể viết điều kiện truy vấn có kiểm tra kiểu ngay lúc biên dịch, thay vì chỉ sử dụng các chuỗi tên field.

Ví dụ, với class Java `DirectoryPerson` có field `uid`, annotation processor có thể sinh `QDirectoryPerson`; ứng dụng sau đó sử dụng biểu thức kiểu `QDirectoryPerson.directoryPerson.uid.eq("lan")`. Nếu lập trình viên đổi `uid` thành một field khác mà chưa cập nhật truy vấn, compiler có thể phát hiện sự không nhất quán.

Điểm quan trọng là **Spring Data LDAP có bộ xử lý riêng**: `org.springframework.data.ldap.repository.support.LdapAnnotationProcessor`. Không dùng bộ xử lý JPA `JPAAnnotationProcessor` để mong nó tự nhận diện `@Entry` của LDAP. Bài này giải thích cách tổ chức phụ thuộc và annotation processing cho **Gradle, Maven, IDE, CI/CD và dự án nhiều module**, rồi kiểm tra sản phẩm được sinh ra.

## 1. Annotation processor giải quyết bài toán gì?

Không có Querydsl, một repository LDAP thường tìm kiếm qua tên phương thức hoặc filter:

~~~java
public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {

    List<DirectoryPerson> findByUid(String uid);
}
~~~

Đây là lựa chọn phù hợp cho điều kiện đơn giản, nhưng khi người dùng chọn nhiều điều kiện khác nhau theo một biểu mẫu tìm kiếm, số tổ hợp phương thức có thể tăng. Querydsl cho phép xây dựng `Predicate` từng bước, dựa vào thuộc tính Java đã có trong Q-type.

| Thành phần | Trách nhiệm | Thời điểm hoạt động |
|---|---|---|
| `@Entry`, `@Attribute`, `@Id` | Mô tả cách entity Java ánh xạ vào LDAP entry | Được khai báo ở mã nguồn, sử dụng khi biên dịch và runtime |
| `LdapAnnotationProcessor` | Tìm entity ODM và sinh mã Java `Q...` | **Compile time** |
| `querydsl-apt` | Thư viện hạ tầng APT của Querydsl | **Compile time** |
| `querydsl-core` | Cung cấp các kiểu `Predicate`, `StringPath`, biểu thức Querydsl | Compile time và runtime của truy vấn |
| `QDirectoryPerson` | Mô hình truy vấn Java đã được sinh | Được compiler biên dịch cùng ứng dụng |
| `QuerydslPredicateExecutor` | Tích hợp predicate vào Spring Data repository | **Runtime** |
| Directory server | Thực hiện LDAP search theo schema, base DN và ACL | **Runtime** |

Annotation processing **không kết nối LDAP** và **không cập nhật schema**. Nó phân tích entity Java đã có trong source, sinh mã để compiler dùng. LDAP server chỉ nhận yêu cầu khi ứng dụng thực sự chạy truy vấn.

## 2. Từ @Entry đến Q-type: luồng bản dựng

Một quy trình giản lược:

~~~mermaid
flowchart TD
    A["Entity Java được gắn @Entry"] --> B["Gradle compileJava / Maven compile"]
    B --> C["javac gọi LdapAnnotationProcessor"]
    C --> D["Querydsl APT sinh QDirectoryPerson.java"]
    D --> E["javac biên dịch entity, Q-type và mã sử dụng chúng"]
    E --> F["Ứng dụng có thể tạo Querydsl Predicate"]
    F --> G["LdapRepository / QuerydslPredicateExecutor thực hiện LDAP search"]
~~~

Từng bước cụ thể:

1. Compiler đọc source chứa `@Entry`, `@Id` và `@Attribute`.
2. Bộ xử lý `LdapAnnotationProcessor` nhận diện entity ODM.
3. Hạ tầng Querydsl tạo các thuộc tính truy vấn theo kiểu Java, ví dụ `StringPath` cho field chuỗi.
4. Generated source được đặt trong thư mục do hệ thống build quản lý.
5. Compiler biên dịch Q-class để code ứng dụng có thể tham chiếu `QDirectoryPerson`.
6. Khi chạy ứng dụng, Querydsl predicate được Spring Data LDAP chuyển thành điều kiện truy vấn phù hợp với directory.

**Điểm phân biệt:** Q-class được sinh từ **entity Java**, không phải bằng cách đọc trực tiếp schema LDAP hoặc kết nối tới directory. Nếu Java mapping sai so với schema/server, build vẫn có thể thành công nhưng truy vấn hoặc thao tác CRUD vẫn có thể bị server từ chối.

## 3. Entity ODM làm đầu vào cho processor

Ví dụ một entity quản lý nhân viên:

~~~java
package org.example.directory;

import javax.naming.Name;

import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=people",
    objectClasses = {
        "top", "person", "organizationalPerson", "inetOrgPerson"
    }
)
public class DirectoryPerson {

    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "sn")
    private String surname;

    public DirectoryPerson() {
    }

    // Getters/setters tương ứng phục vụ mapping ODM.
}
~~~

Khi processor chạy, trong cùng package thường xuất hiện một lớp có tên:

~~~text
org.example.directory.QDirectoryPerson
~~~

Minh họa cách sử dụng sau khi sinh lớp:

~~~java
QDirectoryPerson person = QDirectoryPerson.directoryPerson;

Predicate criteria = person.uid.eq("lan")
        .and(person.commonName.startsWithIgnoreCase("Tran"));
~~~

Trong code hoàn chỉnh, `Predicate` có thể import từ `com.querydsl.core.types.Predicate`. Cấu trúc field và phương thức cụ thể trong Q-type phụ thuộc vào kiểu thuộc tính và phiên bản Querydsl; ví dụ trên giả định processor nhận diện `uid` và `commonName` là thuộc tính kiểu chuỗi.

Không viết hoặc sửa thủ công `QDirectoryPerson.java` như source nghiệp vụ: mỗi lần ánh xạ Java thay đổi, Q-type cần được tái sinh theo model mới.

## 4. Chọn đúng annotation processor và thư viện

Spring Data LDAP hỗ trợ Querydsl thông qua các thành phần chính:

- `LdapAnnotationProcessor`: sinh Q-type cho entry được gắn ODM annotation.
- `QuerydslPredicateExecutor<T>`: mở rộng khả năng của `LdapRepository<T>` để nhận `Predicate`.
- Hạ tầng query LDAP dựa trên Querydsl: chuyển predicate thành phép tìm kiếm LDAP được hỗ trợ.

**Tên lớp processor cần chỉ định tường minh:**

~~~text
org.springframework.data.ldap.repository.support.LdapAnnotationProcessor
~~~

Tên này khác processor của Querydsl dành cho JPA:

~~~text
com.querydsl.apt.jpa.JPAAnnotationProcessor
~~~

Cả hai đều liên quan đến Querydsl, nhưng chú thích đầu vào khác nhau: LDAP sử dụng `org.springframework.ldap.odm.annotations.Entry`, JPA sử dụng `@Entity` tương ứng. Kích hoạt nhầm processor có thể khiến build chạy bình thường nhưng không sinh Q-class cho LDAP entity.

### Lưu ý về phiên bản và namespace

Một dự án có thể sử dụng Querydsl theo tọa độ `com.querydsl` hoặc bản fork OpenFeign `io.github.openfeign.querydsl`. Spring Data hỗ trợ fork theo khả năng tương thích của phiên bản đang dùng; **không trộn tùy tiện hai nhóm artifact trong cùng một bản dựng**.

Các ví dụ Maven/Gradle dưới đây dùng họ **Querydsl 5.x với `com.querydsl`** và bản Spring Data LDAP có hỗ trợ `LdapAnnotationProcessor`. `5.1.0` là phiên bản ví dụ của Querydsl; phiên bản Spring Data LDAP phải khớp với BOM hoặc dependency management của dự án. Nếu chọn phiên bản khác, cần kiểm tra processor, dependency và tên API trong tài liệu chính thức tương ứng.

Về `javax` và `jakarta`: `javax.naming.Name` của JNDI **vẫn là tên package Java hợp lệ** trong ứng dụng LDAP. Không đổi nó thành `jakarta.naming.Name`. `jakarta` classifier của một số artifact Querydsl thuộc về biến thể đóng gói Querydsl; nó **không** đổi annotation ODM `@Entry` thành JPA `@Entity`.

## 5. Gradle: đặt processor trên annotationProcessor classpath

Với dự án Gradle dùng Java và Spring Boot, nên khai báo phụ thuộc được dùng ở **runtime** và phụ thuộc chỉ dùng trong **annotation processing** bằng những configuration khác nhau.

Ví dụ phần cấu hình thêm vào `build.gradle` của dự án đã có Java plugin và quản lý phiên bản Spring Boot:

~~~groovy
def querydslVersion = '5.1.0'

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-ldap'
    implementation "com.querydsl:querydsl-core:$querydslVersion"

    annotationProcessor 'org.springframework.data:spring-data-ldap'
    annotationProcessor "com.querydsl:querydsl-apt:$querydslVersion:jakarta"
}

tasks.named('compileJava', JavaCompile) {
    options.compilerArgs += [
        '-processor',
        'org.springframework.data.ldap.repository.support.LdapAnnotationProcessor'
    ]
}
~~~

Giải thích từng dòng:

| Cấu hình | Vai trò |
|---|---|
| `implementation spring-boot-starter-data-ldap` | Cung cấp Spring LDAP và Spring Data LDAP cho ứng dụng |
| `implementation querydsl-core` | Các kiểu Querydsl mà Q-class và predicate dùng trong code |
| `annotationProcessor spring-data-ldap` | Đưa `LdapAnnotationProcessor` vào processor path |
| `annotationProcessor querydsl-apt` | Đưa lớp nền của Querydsl APT vào processor path |
| `-processor LdapAnnotationProcessor` | Yêu cầu `javac` chạy **đúng** processor LDAP |

Không đặt `querydsl-apt` ở `runtimeOnly` với kỳ vọng build sẽ sinh Q-type. Ngược lại, đưa toàn bộ annotation processor vào runtime classpath là không cần thiết cho ứng dụng đã biên dịch.

**Lưu ý với các processor khác:** tham số `-processor` chỉ định danh sách processor muốn chạy. Nếu dự án còn dùng Lombok, MapStruct hoặc processor khác, cần phối hợp cấu hình để không vô tình vô hiệu hóa chúng. Không thêm hai cơ chế chạy `LdapAnnotationProcessor` độc lập trong cùng một compile task vì có thể cố sinh trùng Q-file.

### Thư mục generated sources của Gradle

Theo cấu hình Java plugin thông thường, output của main source set sẽ ở gần:

~~~text
build/
└── generated/
    └── sources/
        └── annotationProcessor/
            └── java/
                └── main/
                    └── org/example/directory/
                        └── QDirectoryPerson.java
~~~

Gradle JavaCompile thông thường đưa generated sources vào luồng biên dịch; không cần chép file sinh ra vào `src/main/java`. Đường dẫn có thể khác nếu dự án chủ động thay đổi `options.annotationProcessorGeneratedSourcesDirectory` hoặc sử dụng plugin riêng.

Để thử luồng sinh Q-type từ đầu, ví dụ lệnh ở root dự án Gradle:

~~~bash
./gradlew clean compileJava
~~~

Trên Windows, sử dụng `gradlew.bat clean compileJava`. Đây là lệnh minh họa dành cho người học trên dự án thực tế; **bài viết không thực thi bản dựng tại đây**.

## 6. Maven: cấu hình processor trong maven-compiler-plugin

Maven cũng có thể sinh Q-type trong bước `compile`. Một cấu hình rõ ràng nên chỉ ra cả **processor class** và **processor path**. Dưới đây là ví dụ dùng `maven-compiler-plugin` trong dự án Spring Boot có dependency management:

~~~xml
<properties>
    <querydsl.version>5.1.0</querydsl.version>
    <!-- Phải chọn đúng version được Spring Boot/BOM của dự án quản lý. -->
    <ldap.processor.version>4.1.2</ldap.processor.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-ldap</artifactId>
    </dependency>
    <dependency>
        <groupId>com.querydsl</groupId>
        <artifactId>querydsl-core</artifactId>
        <version>${querydsl.version}</version>
    </dependency>
</dependencies>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <configuration>
                <proc>full</proc>
                <annotationProcessorPaths>
                    <path>
                        <groupId>org.springframework.data</groupId>
                        <artifactId>spring-data-ldap</artifactId>
                        <version>${ldap.processor.version}</version>
                    </path>
                    <path>
                        <groupId>com.querydsl</groupId>
                        <artifactId>querydsl-apt</artifactId>
                        <version>${querydsl.version}</version>
                        <classifier>jakarta</classifier>
                    </path>
                </annotationProcessorPaths>
                <annotationProcessors>
                    <annotationProcessor>
                        org.springframework.data.ldap.repository.support.LdapAnnotationProcessor
                    </annotationProcessor>
                </annotationProcessors>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Trong ví dụ này, `ldap.processor.version=4.1.2` là **giá trị minh họa**, không phải một yêu cầu nâng cấp. Cần đặt nó **bằng đúng phiên bản Spring Data LDAP mà dự án dùng ở compile/runtime**. Nếu BOM Spring Boot hiện tại quản lý phiên bản khác, phải thay `ldap.processor.version` cho đồng bộ hoặc tổ chức phiên bản bằng cách quản lý dependency phù hợp của dự án.

Cũng cần dùng phiên bản `maven-compiler-plugin` hỗ trợ các phần tử cấu hình này; dự án dùng Spring Boot parent thường quản lý phiên bản plugin, còn dự án không dùng parent nên khai báo plugin version phù hợp. `<proc>full</proc>` yêu cầu biên dịch cùng annotation processing và giúp mục đích rõ ràng trên JDK mới, nơi việc tự động phát hiện processor đã thay đổi.

**Ý nghĩa của `annotationProcessorPaths`:** cách ly công cụ sinh mã trên processor classpath, giúp hạn chế việc đưa APT phụ thuộc không cần thiết vào runtime. `annotationProcessors` xác định tên class xử lý LDAP cụ thể. Nếu dự án có các processor khác, phải thêm chúng đúng vào cấu hình và xử lý tương thích từng processor.

### Kiểm tra generated sources của Maven

Biên dịch lại từ trạng thái sạch:

~~~bash
mvn clean compile
~~~

Với cấu hình `maven-compiler-plugin` thông thường, file nguồn được sinh vào:

~~~text
target/
└── generated-sources/
    └── annotations/
        └── org/example/directory/
            └── QDirectoryPerson.java
~~~

Sau đó có thể thấy `QDirectoryPerson.class` trong output class tương ứng. Nếu generated source tồn tại nhưng compile vẫn báo `cannot find symbol QDirectoryPerson`, hãy kiểm tra package, source root của IDE và cấu hình compiler. Maven CLI có thể chạy đúng trong khi IDE chưa đánh dấu generated sources là code được tạo khi build.

## 7. Chỉ biên dịch một lần hay chạy processor thành bước riêng?

Hai cơ chế triển khai phổ biến:

| Phương án | Mô tả | Khi nào phù hợp |
|---|---|---|
| **APT trong compileJava/compile** | `javac` chạy processor trong vòng biên dịch và nhận generated sources | Dự án Java thông thường, ít module |
| **Tác vụ tạo mã riêng** | Một task riêng sinh Q-type, rồi bước compile sử dụng output | Dự án có nhiều bước sinh mã hoặc orchestration đặc biệt |

Với Spring Data LDAP, phương án **APT trong bước compile** thường đơn giản hơn. Task build đã có đầy đủ dependency và compilation input; hệ thống build có thể theo dõi generated sources theo lifecycle của compiler.

Nếu dự án đã dùng plugin hoặc task APT riêng, cần bảo đảm **một Q-type chỉ do một luồng sinh mã chịu trách nhiệm**. Chạy processor một lần trong task tạo mã và lần nữa trong `compileJava` với cùng output có thể gây lỗi `Attempt to recreate a file for type ...` hoặc sinh nhiều bản mã không đồng nhất.

Vì vậy, trước khi thêm plugin APT mới, hãy kiểm tra Gradle/Maven hiện có đã chạy `LdapAnnotationProcessor` qua compiler task hay chưa.

## 8. Dùng Q-type với Spring Data LDAP repository

Khi Q-class đã được sinh và biên dịch, repository có thể nhận Querydsl predicate:

~~~java
package org.example.directory;

import org.springframework.data.ldap.repository.LdapRepository;
import org.springframework.data.querydsl.QuerydslPredicateExecutor;

public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson>,
                QuerydslPredicateExecutor<DirectoryPerson> {
}
~~~

Gọi ở service:

~~~java
package org.example.directory;

import com.querydsl.core.types.Predicate;

public class DirectoryPersonSearch {

    private final DirectoryPersonRepository repository;

    public DirectoryPersonSearch(
            DirectoryPersonRepository repository) {
        this.repository = repository;
    }

    public Iterable<DirectoryPerson> byUid(String uid) {
        QDirectoryPerson person = QDirectoryPerson.directoryPerson;

        Predicate predicate = person.uid.eq(uid);
        return repository.findAll(predicate);
    }
}
~~~

Ví dụ này dùng Q-type tương ứng với entity `DirectoryPerson` và phương thức `findAll(Predicate)` của Querydsl repository. Phần triển khai thực tế cần đúng dependency/phiên bản và LDAP directory đã được cấu hình.

**Querydsl không phải một database mới:** `QDirectoryPerson` chỉ là mô hình tạo biểu thức Java. Khi repository thực thi predicate, Spring Data LDAP vẫn phải xây dựng truy vấn trên directory, áp dụng base DN, objectClass, search scope và những giới hạn mà LDAP server hỗ trợ.

Vì LDAP có đặc tính khác SQL, không mặc nhiên giả định mọi phép toán Querydsl, sắp xếp, phân trang hoặc join của JPA đều có cách thực hiện tương ứng trong LDAP. Một số thao tác repository sorting/paging có thể không được hỗ trợ như trong cơ sở dữ liệu quan hệ; cần tra tài liệu và kiểm thử trên phiên bản Spring LDAP/server thực tế.

## 9. Source sinh ra nằm ở đâu, có nên commit không?

Thông thường `Q...java` là **build output có thể tái tạo**, nên có thể giữ ngoài hệ thống quản lý mã nguồn. Source chính thức vẫn là entity `@Entry`.

Ví dụ tổ chức thư mục:

~~~text
project/
├── src/
│   ├── main/
│   │   └── java/org/example/directory/DirectoryPerson.java
│   └── test/
│       └── java/org/example/directory/DirectoryPersonSearchTest.java
├── build.gradle              # Hoặc pom.xml
└── build/                    # Hoặc target/: output được sinh
    └── generated/...
~~~

Ưu điểm của cách để Q-class trong output:

- Tránh giữ hai bản nguồn gốc dữ liệu: entity Java và Q-source được commit thủ công.
- Khi thay đổi field, generated sources có thể được tái tạo theo source hiện hành.
- CI có thể build từ checkout sạch, chứng minh không phụ thuộc file sinh còn sót trên máy lập trình viên.

Nếu tổ chức **chủ động** commit generated source, phải có quy trình cập nhật và so khớp tự động. Không vừa commit `QDirectoryPerson.java` trong `src/main/java` vừa chạy processor tạo cùng class ở output build, vì compiler có thể gặp duplicate type.

Tệp `.gitignore` thường đã bỏ qua `build/` hoặc `target/`; bài học không yêu cầu thay đổi tệp đó. Dùng đường dẫn generated sources do hệ thống build cung cấp, không cố định một path cho mọi dự án.

## 10. IDE phải hiểu generated sources

Một vấn đề thường gặp: `./gradlew compileJava` hoặc `mvn compile` chạy được, nhưng IDE vẫn tô đỏ `QDirectoryPerson` vì chưa nhận diện thư mục generated source.

Quy trình kiểm tra:

1. Xác nhận build bằng dòng lệnh từ checkout sạch có sinh `QDirectoryPerson.java`.
2. Trong IntelliJ IDEA/Eclipse/IDE khác, bật annotation processing hoặc delegate build cho Gradle/Maven theo cơ chế được IDE hỗ trợ.
3. Làm mới cấu hình dự án từ Gradle/Maven; kiểm tra IDE nhận `build/generated/sources/annotationProcessor/java/main` hoặc `target/generated-sources/annotations` là generated source.
4. Đảm bảo compiler và IDE dùng **JDK tương thích** với phiên bản Spring Data LDAP/Querydsl.
5. Nếu Q-class vẫn lỗi, xem compiler log và processor path trước khi thử xóa cache. Không copy file Q sang `src/main/java` để che một cấu hình APT sai.

**Nguyên tắc kiểm chứng:** kết quả `clean compile` trên CLI/CI là chuẩn để xác định bản dựng có thể tái tạo; IDE chỉ là môi trường hỗ trợ chỉnh sửa. Một lớp Q chỉ có trong cache IDE nhưng không thể sinh trên CI là dấu hiệu cấu hình build chưa hoàn chỉnh.

## 11. Quản lý annotation processing trong dự án nhiều module

Xét một hệ thống:

~~~text
directory-model/      # Entity LDAP được gắn @Entry
directory-service/    # Repository, service tạo Querydsl predicate
directory-web/        # REST controller
~~~

Vị trí hợp lý để sinh `QDirectoryPerson` thường là **module sở hữu entity**, tức `directory-model`. Module này có `@Entry`, hiểu các field và chạy APT; module dịch vụ phụ thuộc vào output của nó.

Một sơ đồ phụ thuộc:

~~~mermaid
flowchart LR
    M["directory-model<br/>@Entry + LdapAnnotationProcessor"]
    Q["QDirectoryPerson.class<br/>được đóng gói cùng model"]
    S["directory-service<br/>Repository + Predicate"]
    W["directory-web<br/>HTTP API"]
    M --> Q
    Q --> S
    S --> W
~~~

Với Gradle `java-library`, nếu Q-class xuất hiện trong chữ ký API hoặc được module khác dùng trực tiếp, cần đảm bảo module tiêu thụ nhận được `querydsl-core` trên compile classpath, chẳng hạn thông qua `api("com.querydsl:querydsl-core:...")` hoặc dependency tường minh. Với Maven, dependency của module cũng phải phản ánh nhu cầu đó.

**Tránh các lỗi sau:**

- Module service phụ thuộc source entity nhưng không phụ thuộc artifact chứa Q-class đã được biên dịch.
- Chỉ cấu hình APT trong module web dù `@Entry` nằm ở module model.
- Chạy hai processor trên cùng entity ở hai module, tạo bản Q-class trùng tên nhưng khác phiên bản.
- Module model có Q-class sinh ra nhưng quá trình đóng gói/publish bỏ sót class được biên dịch.
- Các module chọn khác phiên bản Querydsl khiến lỗi `NoSuchMethodError` hoặc `ClassNotFoundException` khi chạy.

Nếu test source chứa riêng các entity `@Entry` phục vụ kiểm thử, có thể cần processor trên `testAnnotationProcessor` của Gradle hoặc cấu hình test compilation tương ứng ở Maven. Không áp dụng APT cho test source nếu không có trường hợp sử dụng rõ ràng.

## 12. CI/CD: xác minh bản dựng tự tái sinh Q-class

Một pipeline đáng tin cậy không phụ thuộc file Q còn sót từ máy trước đó.

~~~mermaid
flowchart TD
    A["Checkout repository sạch"] --> B["Resolve dependency đã quản lý phiên bản"]
    B --> C["Compile + chạy LdapAnnotationProcessor"]
    C --> D{"Q-type được sinh và compile?"}
    D -->|Không| E["Fail build; kiểm tra processor path và cấu hình"]
    D -->|Có| F["Chạy unit test"]
    F --> G["Integration test với LDAP test độc lập"]
    G --> H["Đóng gói artifact ứng dụng"]
~~~

Có thể dùng các lệnh CLI như sau:

~~~bash
# Gradle
./gradlew clean compileJava test

# Maven
mvn clean verify
~~~

Một bước CI đơn giản kiểm tra rằng class cần dùng đã được compile và mã service tham chiếu được Q-type. Việc chỉ kiểm tra có thư mục generated sources **chưa đủ** để chứng minh mọi predicate runtime thực thi đúng.

Các nguyên tắc chính:

- **Chốt phiên bản dependency**, ưu tiên BOM/dependency lock và không trôi phiên bản Querydsl ngầm ngoài ý muốn.
- **Chạy compile từ checkout sạch** để phát hiện file generated cũ.
- **Không coi APT là bước kiểm thử LDAP:** APT không cần địa chỉ server hoặc password, nên không cấp secret production cho bước tạo Q-class.
- **Integration test phải dùng directory riêng:** kiểm tra schema, base DN, ACL, mapping và kết quả query ở runtime.
- **Theo dõi thay đổi JDK:** JDK 23 trở lên không còn tự động chạy processor chỉ nhờ sự hiện diện trên classpath như một số môi trường trước đây. Việc cấu hình processor tường minh giúp tránh build “thành công” nhưng không sinh Q-class.
- **Xem lại build cache/incremental compilation:** thay đổi entity hoặc annotation phải kích hoạt tái sinh Q-class khi cần. Một `clean compile` định kỳ hoặc trong CI giúp bắt lỗi phụ thuộc vào output cũ.

## 13. Những lỗi thường gặp khi không sinh được Q-class

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `cannot find symbol: QDirectoryPerson` | Processor chưa chạy hoặc output không trên source path | Kiểm tra tên processor, annotationProcessor path và compiler log |
| Không thấy file nào trong generated sources | Dùng nhầm `JPAAnnotationProcessor` hoặc chưa bật APT | Chọn `LdapAnnotationProcessor`, kiểm tra entity `@Entry` |
| `ClassNotFoundException: LdapAnnotationProcessor` | Thiếu `spring-data-ldap` trên processor path | Thêm dependency cho APT và đồng bộ version |
| `NoClassDefFoundError` liên quan Querydsl APT | Thiếu hoặc không tương thích Querydsl APT/core | Đồng bộ Querydsl, xem dependency tree |
| `Attempt to recreate a file for type Q...` | Chạy hai processor/lifecycle sinh cùng Q hoặc có Q thủ công | Chọn một luồng sinh, bỏ bản Q trùng |
| Build CLI thành công nhưng IDE báo đỏ Q-class | IDE không nhận generated source hoặc chưa import lại dự án | Cập nhật project từ Gradle/Maven, bật APT |
| Q-class có field cũ | Incremental build/cache stale hoặc chưa compile lại entity | Tái biên dịch từ sạch, kiểm tra package/entity hiện tại |
| Q-class ở sai package | Đổi package entity nhưng mã gọi vẫn dùng import cũ | Xác nhận package của generated source và import |
| Test compilation không tìm được Q-type | Test entity nằm ở `src/test/java` nhưng test APT chưa cấu hình | Bật test annotation processing đúng source set |
| Runtime báo lỗi API Querydsl | Hỗn hợp artifact hoặc phiên bản `com.querydsl`/fork không khớp | Kiểm tra dependency graph, dùng một hệ tọa độ nhất quán |
| Truy vấn compile được nhưng LDAP trả kết quả sai | Base DN/filter/schema/ACL hoặc chức năng LDAP không hỗ trợ | Kiểm tra integration test với directory thật |

### Phân tích theo ba tầng

**Tầng 1 — Sinh mã:** có `QDirectoryPerson.java` sau lệnh clean compile không? Nếu chưa, xem processor path, tên processor, annotation `@Entry` và compiler log.

**Tầng 2 — Biên dịch:** Q-class đã có nhưng Java báo lỗi? Kiểm tra package, version `querydsl-core`, source root và classpath của module tiêu thụ.

**Tầng 3 — Runtime:** build được nhưng truy vấn LDAP lỗi? Đây thường là vấn đề về query support, connection, base DN, schema, ACL hoặc dữ liệu, không phải lỗi APT thuần túy.

## 14. Annotation processing và bảo mật LDAP

Mặc dù Q-type giúp tạo truy vấn theo thuộc tính Java, cơ chế này không thay thế các lớp bảo vệ khi truy cập LDAP:

- **Q-type không thay thế LDAP schema.** Server vẫn kiểm tra `objectClass`, syntax, MUST/MAY khi CRUD.
- **Q-type không tự kiểm tra ACL.** Repository hoạt động theo credential của `ContextSource`; phải hạn chế quyền tại directory server và phân quyền nghiệp vụ ở ứng dụng.
- **Q-type không tự cố định search base.** Chức năng chỉ được tìm trong OU/tenant đã cấp quyền; kiểm thử search scope, DN và nhánh thực tế.
- **Q-type không đồng nghĩa hỗ trợ mọi biểu thức Querydsl.** Chỉ dùng những predicate mà Spring Data LDAP và server thực hiện đúng.
- **Biểu thức type-safe không thay thế kiểm tra input.** Giá trị người dùng cần được xử lý qua API truy vấn phù hợp; không tự ghép filter LDAP thô hoặc DN từ input.
- **Kết nối phải được bảo vệ:** LDAPS hoặc StartTLS có xác minh chứng chỉ, service account có quyền tối thiểu và thông tin xác thực được cấp từ secret manager.

Build không cần bí mật LDAP để sinh Q-class. Nếu CI đòi credential production mới chạy được annotation processing, hãy xem lại việc trộn nhầm **code generation** với **integration test hoặc thao tác runtime**.

## 15. Kiểm thử có ý nghĩa cho phần build và LDAP runtime

Nên phân biệt hai nhóm kiểm tra:

| Nhóm | Kiểm tra điều gì? | Có cần LDAP server? |
|---|---|---|
| **Build/processor verification** | Q-class được sinh từ `@Entry`, compile được, import đúng | Không |
| **Integration verification** | Predicate lọc đúng entry, không vượt base DN/ACL, xử lý schema và lỗi | Có, dùng directory test độc lập |

### Kịch bản A: thay đổi entity

1. Biên dịch model `DirectoryPerson` và xác nhận có `QDirectoryPerson`.
2. Thêm thuộc tính `@Attribute(name = "mail") private String email;`.
3. Recompile theo cơ chế build và xem Q-class đã có field `email` phù hợp chưa.
4. Viết một predicate sử dụng `person.email.eq("lan@example.org")` và xác nhận compiler kiểm tra được thuộc tính.
5. Đổi tên field Java và biên dịch lại từ sạch; code dùng field cũ phải báo lỗi biên dịch, giúp phát hiện chỗ chưa cập nhật.

### Kịch bản B: chạy truy vấn thật

1. Tạo directory LDAP test với `dc=example,dc=org` và `ou=people`.
2. Nạp các entry `inetOrgPerson` hợp lệ có `uid`, `cn`, `sn`.
3. Gọi repository `findAll(QDirectoryPerson.directoryPerson.uid.eq("lan"))`.
4. Xác nhận chỉ các entry trong base DN và scope mong muốn được trả về.
5. Thử `uid` có ký tự đặc biệt trong dữ liệu test; xác minh framework truyền giá trị query an toàn và kết quả không mở rộng bất ngờ.
6. Dùng tài khoản có ACL hạn chế, xác nhận không thể đọc entry ngoài quyền.
7. Kiểm tra lại sau khi đổi ODM mapping hoặc nâng phiên bản Spring Data LDAP/Querydsl.

Đây là kiểm thử ở môi trường riêng; không nạp dữ liệu test hoặc chạy thao tác thay đổi hàng loạt trên production directory.

## 16. Checklist cho người review build

Trước khi merge thay đổi dùng Querydsl với Spring Data LDAP, hãy xác nhận:

- [ ] Entity nguồn có đúng `@Entry` của Spring LDAP ODM và package của nó được compiler xử lý.
- [ ] Processor được khai báo là `org.springframework.data.ldap.repository.support.LdapAnnotationProcessor`.
- [ ] `querydsl-core` phục vụ compile/runtime; `querydsl-apt` và `spring-data-ldap` có mặt trên processor path.
- [ ] Phiên bản Querydsl, Spring Data LDAP và Spring Boot/BOM tương thích; không trộn hai fork.
- [ ] Chỉ một luồng sinh Q-class, không vừa commit file Q thủ công vừa sinh file cùng tên.
- [ ] `clean compile` từ checkout sạch sinh được Q-type trong đường dẫn output chuẩn.
- [ ] IDE nhận generated source sau khi nhập lại Gradle/Maven project.
- [ ] Module chứa entity chịu trách nhiệm APT; module dùng Q-class nhận được compiled class và dependency.
- [ ] CI chạy build và test phù hợp, không cần LDAP production secret trong bước annotation processing.
- [ ] Kiểm thử tích hợp xác minh predicate, search base, schema, ACL và giới hạn query của directory server.

## 17. Bài tập thực hành

**Bối cảnh:** một dự án Spring Boot sử dụng `SPRING_DATA_LDAP` để tìm người dùng LDAP từ Java entity `DirectoryPerson`. Nhóm phát triển muốn tìm theo `uid`, `cn` và `mail` tùy chọn bằng Querydsl.

Hãy thực hiện:

1. Tạo entity `DirectoryPerson` theo ví dụ, bổ sung `@Attribute(name = "mail")`.
2. Chọn Maven hoặc Gradle và thêm dependency cùng processor LDAP đúng tên.
3. Chạy `clean compile`; ghi nhận thư mục và tên `QDirectoryPerson.java` được sinh.
4. Mở Q-class để xác định các trường Querydsl tương ứng với `uid`, `commonName` và `email`.
5. Tạo repository kế thừa `LdapRepository<DirectoryPerson>` và `QuerydslPredicateExecutor<DirectoryPerson>`.
6. Viết service tìm theo `person.uid.eq(input)` và kết hợp thêm điều kiện khi có `mail`.
7. Đổi tên một field Java, compile lại và quan sát Q-type thay đổi; cập nhật chỗ gọi dựa theo lỗi compiler.
8. Xóa output sinh mã, chạy build bằng dòng lệnh lần nữa để chứng minh không lệ thuộc IDE cache.
9. Chạy integration test với LDAP riêng; xác minh query không tìm ngoài `ou=people` và tuân theo ACL.
10. Thử bỏ cấu hình `-processor` hoặc processor dependency và mô tả lỗi quan sát được, rồi khôi phục cấu hình.

**Tiêu chí hoàn thành:** Q-type được sinh tự động, build tái tạo được trên CLI và CI, service dùng predicate đã được type-check và truy vấn LDAP trả kết quả đúng trên directory test.

## 18. Ghi nhớ và tài liệu tham khảo

**Trong Spring Data LDAP, annotation processing là công đoạn của bản dựng sinh Q-class từ `@Entry`.** Cần đặt `LdapAnnotationProcessor` và Querydsl APT đúng processor path, còn `querydsl-core` cung cấp biểu thức sử dụng khi code được biên dịch và chạy. Hãy để hệ thống build quản lý generated sources, xác minh bằng clean compile và kiểm thử thực tế trên directory độc lập.

Không nhầm công việc sinh Q-type với việc tạo schema, thực thi truy vấn hoặc bảo vệ LDAP. Querydsl cung cấp kiểu truy vấn ở tầng Java; Spring Data LDAP, `LdapRepository`, `LdapTemplate` và directory server vẫn áp dụng base DN, objectClass, filter, ACL và bảo mật kết nối ở runtime.

Nguồn tham khảo chính thức:

- [Spring Data LDAP — Querydsl Support](https://docs.spring.io/spring-data/ldap/reference/ldap/querydsl.html): processor LDAP và khả năng hỗ trợ predicate.
- [Spring Data LDAP — Spring Data Extensions / Setting up Annotation Processing](https://docs.spring.io/spring-data/ldap/reference/repositories/core-extensions.html): ví dụ cấu hình Maven/Gradle.
- [Spring Data LDAP — LdapAnnotationProcessor API](https://docs.spring.io/spring-data/ldap/reference/api/java/org/springframework/data/ldap/repository/support/LdapAnnotationProcessor.html): tên processor và các annotation được hỗ trợ.
- [Spring Data LDAP — Object-Directory Mapping](https://docs.spring.io/spring-data/ldap/reference/ldap/odm.html): `@Entry`, `@Id`, `@Attribute`.
- [Gradle User Manual — Annotation Processors](https://docs.gradle.org/current/userguide/java_plugin.html#sec:java_compile_avoidance): phụ thuộc annotationProcessor và build Java.
- [Maven Compiler Plugin — Annotation Processor Configuration](https://maven.apache.org/plugins/maven-compiler-plugin/compile-mojo.html): `annotationProcessorPaths` và `annotationProcessors`.
- [OpenFeign Querydsl](https://github.com/OpenFeign/querydsl): một nhánh phát triển Querydsl; kiểm tra tính tương thích với phiên bản Spring Data dùng thực tế.
