
# Sử dụng Liquibase qua Maven và Gradle

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, Liquibase quản lý các thay đổi schema và dữ liệu thông qua changelog, changeset, precondition, checksum và lịch sử triển khai. Khi làm việc với dự án Java, Maven và Gradle cung cấp cách khai báo thư viện, JDBC driver, cấu hình kết nối và lệnh chạy migration ngay trong quy trình build.

Mục tiêu của bài học là thiết lập được Liquibase trong một dự án Java, chạy và kiểm tra changelog bằng Maven hoặc Gradle, kết nối đúng database theo từng môi trường, rồi đưa các bước kiểm chứng đó vào CI/CD. Cả hai công cụ đều có thể thực hiện migration; lựa chọn phụ thuộc vào hệ thống build hiện tại và cách nhóm muốn tổ chức phát hành.

## 1. Hai cách tích hợp Liquibase trong dự án Java

Có hai cách dùng phổ biến:

1. **Plugin của công cụ build:** Maven Liquibase Plugin hoặc Liquibase Gradle Plugin cung cấp các goal/task để validate, xem trạng thái, sinh SQL và thực thi migration từ dòng lệnh. Cách này phù hợp với bước migration riêng trong CI/CD hoặc thao tác có chủ đích của developer.
2. **Thư viện chạy cùng ứng dụng:** thêm Liquibase Core vào classpath ứng dụng. Với Spring Boot, auto-configuration có thể chạy Liquibase khi ứng dụng khởi động. Cách này phù hợp khi nhóm muốn schema được cập nhật trong quá trình khởi động một instance được điều phối.

Hai cách có thể cùng tồn tại trong một repository, nhưng cần quy định rõ ai chịu trách nhiệm chạy migration ở mỗi môi trường. Nếu pipeline đã chạy migration như một bước riêng, việc để mọi replica Spring Boot tiếp tục tự chạy migration có thể tạo ra các lần khởi động cạnh tranh và khó quan sát hơn. Hãy chọn một cơ chế điều phối chính cho từng môi trường.

| Nhu cầu | Cách tích hợp thường phù hợp |
|---|---|
| Developer chạy validate, status hoặc updateSQL trên máy cá nhân | Maven plugin hoặc Gradle plugin |
| Pipeline chạy migration trước khi triển khai ứng dụng | Plugin trong một job migration riêng |
| Ứng dụng Spring Boot tự cập nhật schema khi khởi động | Liquibase Core và Spring Boot auto-configuration |
| Muốn dùng chung changelog giữa local, CI và runtime | Đặt changelog trong source/resource của dự án, cấu hình từng cách chạy trỏ về cùng master changelog |

Plugin build và thư viện runtime có classpath khác nhau. Một JDBC driver có trong dependency của ứng dụng chưa chắc đã có trong classpath riêng của Maven plugin hoặc Gradle task. Đây là điểm cần kiểm tra khi cài đặt.

## 2. Chuẩn bị môi trường

Trước khi cấu hình, xác định các thành phần sau:

- JDK tương thích với phiên bản Maven/Gradle, Liquibase và framework của dự án.
- Maven hoặc Gradle Wrapper của repository. Ưu tiên dùng wrapper để mọi developer và CI chạy cùng phiên bản build tool.
- Hệ quản trị cơ sở dữ liệu đích, phiên bản database, JDBC URL và tên driver.
- Tài khoản có quyền phù hợp với migration dự kiến. Tài khoản tạo bảng hoặc index thường cần quyền DDL; tài khoản runtime của ứng dụng có thể chỉ cần quyền đọc/ghi.
- Master changelog và các changelog con, hoặc vị trí dự kiến để tạo chúng.
- Cách cấp thông tin xác thực an toàn, chẳng hạn biến môi trường hoặc secret store của CI.

Ví dụ với PostgreSQL, driver thường dùng là org.postgresql.Driver và URL có dạng:

~~~text
jdbc:postgresql://localhost:5432/appdb
~~~

Với MySQL, driver thường dùng là com.mysql.cj.jdbc.Driver và URL có dạng:

~~~text
jdbc:mysql://localhost:3306/appdb
~~~

Đây chỉ là ví dụ định dạng kết nối. Driver, URL, tham số SSL, schema mặc định và kiểu dữ liệu phải phù hợp với database thực tế. Không đưa mật khẩu production vào POM, build.gradle, file properties được commit hoặc log build.

Nên thống nhất phiên bản Liquibase Core, plugin build, JDBC driver và JDK theo ma trận tương thích của dự án. Ghim phiên bản cụ thể giúp build có thể tái lập; tránh dùng phiên bản động như latest hoặc dải phiên bản không kiểm soát trong pipeline phát hành.

## 3. Chuẩn bị changelog dùng chung

Có thể lưu changelog trong source resources để ứng dụng và plugin cùng tham chiếu:

~~~text
src/
└── main/
    └── resources/
        └── db/
            └── changelog/
                ├── db.changelog-master.yaml
                └── changes/
                    ├── 001-create-customer.yaml
                    └── 002-add-customer-status.yaml
~~~

Master changelog khai báo thứ tự include:

~~~yaml
databaseChangeLog:
  - include:
      file: changes/001-create-customer.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/002-add-customer-status.yaml
      relativeToChangelogFile: true
~~~

Ví dụ một changeset tạo bảng:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-customer
      author: platform-team
      comment: Tạo bảng khách hàng
      changes:
        - createTable:
            tableName: customer
            columns:
              - column:
                  name: id
                  type: bigint
                  autoIncrement: true
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: email
                  type: varchar(320)
                  constraints:
                    nullable: false
                    unique: true
      rollback:
        - dropTable:
            tableName: customer
~~~

Changeset tiếp theo có thể bổ sung một cột:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 002-add-customer-status
      author: platform-team
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: status
                  type: varchar(20)
                  defaultValue: ACTIVE
                  constraints:
                    nullable: true
~~~

Hai ví dụ minh họa cách tổ chức file và khai báo thay đổi. Khi áp dụng vào dự án thật, cần đánh giá kiểu dữ liệu theo DBMS, giá trị mặc định, tính nullable, dữ liệu hiện có, khả năng rollback và tương thích với phiên bản ứng dụng đang chạy.

Không sửa nội dung changeset đã triển khai chỉ để làm cho lệnh build chạy qua. Liquibase lưu định danh và checksum của changeset trong DATABASECHANGELOG. Khi cần thay đổi kết quả đã triển khai, hãy tạo changeset mới. Changelog phải được đóng gói hoặc được cung cấp trên classpath/file path đúng như cấu hình của plugin.

## 4. Cài đặt và cấu hình bằng Maven

### 4.1. Phân biệt dependency ứng dụng và Maven plugin

Nếu ứng dụng hoặc Spring Boot cần chạy Liquibase lúc khởi động, thêm Liquibase Core vào dependency của ứng dụng. Ví dụ:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.liquibase</groupId>
        <artifactId>liquibase-core</artifactId>
        <version>LIQUIBASE_VERSION</version>
    </dependency>

    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <version>POSTGRESQL_DRIVER_VERSION</version>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Nếu dự án dùng Spring Boot dependency management, có thể để BOM quản lý phiên bản tương thích và bỏ phần version ở dependency khi BOM đã quản lý. Không nên thêm một phiên bản Liquibase Core tùy tiện lệch khỏi phiên bản mà Spring Boot release đang hỗ trợ.

Để chạy lệnh Liquibase bằng Maven, khai báo plugin trong build/plugins:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.liquibase</groupId>
            <artifactId>liquibase-maven-plugin</artifactId>
            <version>LIQUIBASE_VERSION</version>
            <configuration>
                <changeLogFile>
                    src/main/resources/db/changelog/db.changelog-master.yaml
                </changeLogFile>
                <url>${env.DB_URL}</url>
                <username>${env.DB_USER}</username>
                <password>${env.DB_PASSWORD}</password>
                <driver>org.postgresql.Driver</driver>
                <logLevel>info</logLevel>
            </configuration>
            <dependencies>
                <dependency>
                    <groupId>org.postgresql</groupId>
                    <artifactId>postgresql</artifactId>
                    <version>POSTGRESQL_DRIVER_VERSION</version>
                </dependency>
            </dependencies>
        </plugin>
    </plugins>
</build>
~~~

Thay các giá trị phiên bản minh họa bằng phiên bản cụ thể đã được nhóm kiểm tra. Plugin có classloader riêng, do đó khai báo PostgreSQL driver trong dependency của ứng dụng chưa chắc đủ cho plugin. Khai báo driver trong phần dependencies của plugin giúp plugin tải được driver khi kết nối database.

Nếu dùng DBMS khác, thay artifact JDBC driver, tên driver và URL. Với driver nội bộ hoặc changelog phụ thuộc thư viện khác, cũng phải kiểm tra các dependency đó có nằm trong classpath mà plugin sử dụng hay không.

Không phải dự án nào cũng cần cả dependency Liquibase Core trong ứng dụng lẫn Maven plugin. Nếu chỉ chạy migration từ job riêng, plugin có thể đảm nhiệm việc thực thi mà ứng dụng không cần tự khởi chạy Liquibase. Nếu Spring Boot cũng chạy migration, dependency runtime là cần thiết.

### 4.2. Cấp cấu hình theo môi trường

Ví dụ trên dùng biến môi trường DB_URL, DB_USER và DB_PASSWORD. Trên máy local, developer cấp các giá trị kết nối tới database phát triển; CI lấy thông tin tương ứng từ secret store. Không đặt giá trị nhạy cảm trực tiếp trong POM.

Có thể dùng Maven profile cho các khác biệt không nhạy cảm như tên context, label hoặc một số tùy chọn theo môi trường. Tuy nhiên, profile không phải kho bí mật. Thông tin xác thực nên được truyền qua biến môi trường hoặc cơ chế quản lý secret.

Một nguyên tắc hữu ích là giữ đường dẫn changelog giống nhau ở mọi môi trường, còn URL và tài khoản thay đổi theo đích triển khai. Nhờ đó, cùng một revision có thể được chạy trên local, test, staging và production mà không phải sửa nội dung changelog.

### 4.3. Chạy các goal Liquibase bằng Maven

Sử dụng Maven Wrapper của dự án:

~~~bash
./mvnw liquibase:validate
./mvnw liquibase:status
./mvnw liquibase:updateSQL
./mvnw liquibase:update
~~~

Trên Windows có thể dùng mvnw.cmd thay cho ./mvnw. Nếu Maven không nhận diện goal, kiểm tra plugin đã khai báo trong POM, phiên bản plugin và tên goal theo tài liệu đúng phiên bản đang dùng.

Ý nghĩa các lệnh chính:

| Goal | Mục đích | Có thay đổi database không? |
|---|---|---|
| liquibase:validate | Kiểm tra cấu trúc và tham chiếu changelog | Không thực thi changeset |
| liquibase:status | Liệt kê changeset còn chờ trên database đích | Không |
| liquibase:updateSQL | Sinh SQL mà update dự kiến thực thi | Không thực thi SQL |
| liquibase:update | Áp dụng changeset còn thiếu | Có |
| liquibase:rollback | Quay lui theo số lượng, tag hoặc mốc được cấu hình | Có |
| liquibase:rollbackSQL | Sinh SQL rollback để review | Không thực thi SQL rollback |

Tên goal và tham số có thể khác theo phiên bản plugin; hãy kiểm tra tài liệu plugin đang ghim trong dự án. Ví dụ lệnh rollback theo số lượng thường có dạng:

~~~bash
./mvnw liquibase:rollback -Dliquibase.rollbackCount=1
~~~

Chỉ chạy rollback sau khi đã xác định đúng database, mốc rollback, ảnh hưởng dữ liệu và khả năng tương thích của ứng dụng. Với môi trường quan trọng, nên sinh SQL rollback, review và thử trên database tương đương trước khi thực thi.

Một luồng local an toàn là chạy validate, xem status, sinh updateSQL, đọc SQL đầu ra rồi mới chạy update trên database phát triển. UpdateSQL hữu ích cho review nhưng không chứng minh câu lệnh sẽ chạy thành công trên DBMS thật; vẫn cần kiểm thử migration trên đúng loại database.

## 5. Cài đặt và cấu hình bằng Gradle

### 5.1. Thêm plugin và các dependency cần thiết

Với Gradle Groovy DSL, khai báo plugin trong build.gradle:

~~~groovy
plugins {
    id 'java'
    id 'org.liquibase.gradle' version 'LIQUIBASE_GRADLE_PLUGIN_VERSION'
}
~~~

Khai báo dependency riêng cho Liquibase task:

~~~groovy
dependencies {
    liquibaseRuntime 'org.liquibase:liquibase-core:LIQUIBASE_VERSION'
    liquibaseRuntime 'org.postgresql:postgresql:POSTGRESQL_DRIVER_VERSION'
    liquibaseRuntime 'info.picocli:picocli:PICOCLI_VERSION'

    runtimeOnly 'org.postgresql:postgresql:POSTGRESQL_DRIVER_VERSION'
}
~~~

Liquibase Gradle Plugin sử dụng cấu hình liquibaseRuntime để tạo classpath khi chạy task. Vì vậy, JDBC driver phải được khai báo trong liquibaseRuntime. Driver ở runtimeOnly phục vụ ứng dụng; nó không tự động thay thế driver trong classpath của task Liquibase.

Một số phiên bản plugin hoặc cách tích hợp có thể quản lý dependency CLI khác nhau. Kiểm tra hướng dẫn của đúng phiên bản plugin trước khi thêm hoặc bỏ dependency như picocli. Không trộn ví dụ cấu hình từ các phiên bản plugin khác nhau.

### 5.2. Khai báo activity

Một cấu hình Groovy DSL tham khảo:

~~~groovy
liquibase {
    activities {
        main {
            changeLogFile 'src/main/resources/db/changelog/db.changelog-master.yaml'
            url System.getenv('DB_URL')
            username System.getenv('DB_USER')
            password System.getenv('DB_PASSWORD')
            driver 'org.postgresql.Driver'
            logLevel 'info'
        }
    }
    runList = 'main'
}
~~~

Activity main xác định cấu hình mà task Liquibase sẽ sử dụng. Nếu dự án cần nhiều database hoặc nhiều bộ cấu hình, có thể khai báo nhiều activity có tên riêng rồi chọn activity phù hợp qua runList. Không nên tạo activity chỉ để nhúng mật khẩu vào source control.

Với Kotlin DSL, cú pháp khai báo plugin, dependency và extension khác Groovy DSL. Hãy dùng đúng cú pháp API mà phiên bản plugin hỗ trợ; không sao chép nguyên khối Groovy DSL vào build.gradle.kts.

Nếu biến môi trường không tồn tại, các giá trị kết nối có thể rỗng và task sẽ thất bại khi chạy. Có thể bổ sung kiểm tra đầu vào trong build script hoặc pipeline để báo lỗi sớm, thay vì để một task kết nối tới đích không xác định.

### 5.3. Chạy task Liquibase bằng Gradle

Dùng Gradle Wrapper:

~~~bash
./gradlew tasks --all
./gradlew validate
./gradlew status
./gradlew updateSQL
./gradlew update
~~~

Lệnh tasks --all giúp kiểm tra các task mà plugin thực sự đăng ký trong dự án. Tên task và cách truyền tham số phụ thuộc phiên bản plugin. Các task rollback như rollbackCount hoặc rollbackToDate chỉ nên chạy sau khi đã xác minh cách truyền tham số của phiên bản đang dùng và kiểm tra database đích.

Một số quy tắc vận hành khi chạy Gradle:

- Chạy task từ đúng module chứa plugin và cấu hình Liquibase.
- Dùng Gradle Wrapper để tránh khác biệt phiên bản Gradle giữa máy local và CI.
- Đảm bảo liquibaseRuntime chứa Liquibase Core, JDBC driver và dependency CLI cần thiết.
- Chọn đúng activity nếu build script khai báo nhiều activity.
- Không gắn task update vào mọi lần build thông thường nếu việc build có thể chạy ở môi trường không có database hoặc không được phép thay đổi schema.
- Tách task sinh SQL và task thực thi để người review có thể kiểm tra thay đổi trước khi cập nhật database.

## 6. Maven và Gradle: chọn cách nào?

Cả hai plugin đều có thể chạy cùng một loại changelog Liquibase. Việc lựa chọn chủ yếu nên dựa trên công cụ build hiện tại và cách nhóm quản lý pipeline.

| Tiêu chí | Maven | Gradle |
|---|---|---|
| Khai báo plugin | POM trong build/plugins | Plugin DSL trong build.gradle hoặc build.gradle.kts |
| Đơn vị chạy | Goal | Task |
| Cấu hình theo môi trường | Properties, profile, biến môi trường | Project properties, activity, biến môi trường |
| Classpath migration | Dependency của Maven plugin | Configuration liquibaseRuntime |
| Wrapper | mvnw / mvnw.cmd | gradlew / gradlew.bat |
| Tích hợp build | Theo lifecycle và plugin execution | Theo task graph và dependency giữa các task |
| Phù hợp | Dự án đang chuẩn hóa theo Maven | Dự án đã dùng Gradle và cần tổ chức task linh hoạt |

Không cần chuyển build tool chỉ để sử dụng Liquibase. Nếu dự án đã dùng Maven, khai báo Maven plugin sẽ giúp quy trình migration đồng nhất với POM. Nếu dự án dùng Gradle, plugin Gradle tận dụng cấu hình dependency và task hiện có.

Điểm cần thống nhất giữa hai công cụ là master changelog, quy tắc đặt changeset, phiên bản Liquibase, JDBC driver, cách cấp credentials và quy trình kiểm chứng. Nếu developer chạy Maven còn CI chạy Gradle, cần bảo đảm hai cách chạy dùng cùng phiên bản Liquibase và cùng tham số thực thi.

## 7. Kết hợp với Spring Boot

Spring Boot có thể tự cấu hình Liquibase khi ứng dụng có Liquibase Core trên classpath và có datasource phù hợp. Một cấu hình application.yaml tham khảo:

~~~yaml
spring:
  datasource:
    url: ${DB_URL}
    username: ${DB_USER}
    password: ${DB_PASSWORD}
  liquibase:
    change-log: classpath:db/changelog/db.changelog-master.yaml
    enabled: true
    contexts: ${LIQUIBASE_CONTEXTS:}
    labels: ${LIQUIBASE_LABELS:}
~~~

Spring Boot thường chạy Liquibase trong quá trình khởi động context ứng dụng trước khi các thành phần phụ thuộc vào schema được khởi tạo. Cấu hình thực tế còn phụ thuộc phiên bản Spring Boot, cách khai báo datasource và cách nhóm triển khai ứng dụng.

Nếu Liquibase cần kết nối khác với datasource chính, có thể cấu hình các thuộc tính Liquibase riêng như URL, username, password và driver-class-name theo hỗ trợ của phiên bản Spring Boot. Cách này hữu ích khi tài khoản migration có quyền DDL còn tài khoản ứng dụng có quyền runtime hạn chế hơn.

Có hai mô hình thường gặp:

**Mô hình A — ứng dụng tự chạy migration**

- Đóng gói Liquibase Core và JDBC driver trong ứng dụng.
- Bật spring.liquibase.enabled.
- Đảm bảo chỉ có một tiến trình được điều phối migration tại thời điểm thích hợp, đặc biệt khi triển khai nhiều replica.
- Theo dõi log khởi động, thời gian chờ lock và kết quả migration.

**Mô hình B — pipeline chạy migration riêng**

- Job Maven hoặc Gradle chạy validate, status, updateSQL và update.
- Ứng dụng được triển khai sau khi migration đạt yêu cầu.
- Cấu hình spring.liquibase.enabled=false ở runtime nếu pipeline là chủ thể duy nhất thực thi migration.
- Bảo đảm pipeline và ứng dụng cùng sử dụng revision changelog đã được kiểm tra.

Không bật đồng thời nhiều cơ chế thực thi mà không có chủ đích. DATABASECHANGELOGLOCK giúp điều phối các lần Liquibase cập nhật cùng database, nhưng không thay thế thiết kế thứ tự triển khai ứng dụng và kiểm soát số lượng job.

## 8. Quản lý cấu hình và bí mật theo môi trường

Cùng một changelog có thể chạy trên nhiều môi trường nếu cấu hình kết nối được tách khỏi nội dung migration.

| Tham số | Local | Test/QA | Staging | Production |
|---|---|---|---|---|
| DB_URL | Database local hoặc container | Database kiểm thử | Database gần production | Endpoint production |
| DB_USER | Tài khoản phát triển | Tài khoản test | Tài khoản staging | Tài khoản migration được cấp quyền |
| DB_PASSWORD | Secret local | Secret CI/test | Secret staging | Secret production |
| LIQUIBASE_CONTEXTS | Context cần cho local | Context kiểm thử có chủ đích | Context đã phê duyệt | Chỉ context được phép chạy |
| ChangeLogFile | Master changelog của repository | Cùng master changelog | Cùng revision | Cùng revision đã phát hành |

Các nguyên tắc cần giữ:

1. Không commit mật khẩu, token hoặc URL chứa thông tin xác thực vào repository.
2. Không ghi credentials vào log debug, log pipeline hoặc artifact.
3. Dùng tài khoản migration có quyền vừa đủ cho thay đổi dự kiến.
4. Xác nhận database host, database name và schema trước mọi lệnh update hoặc rollback.
5. Giữ changelog và revision nhất quán khi promote qua môi trường.
6. Truyền context/label rõ ràng. Không giả định changeset có context sẽ tự động bị loại nếu không truyền context filter; kiểm tra hành vi theo phiên bản Liquibase và cách gọi plugin.

Đối với dữ liệu mẫu chỉ dành cho kiểm thử, có thể dùng context bắt buộc hoặc label có quy ước rõ ràng, sau đó kiểm tra SQL sinh ra trên cấu hình production. Việc lọc changeset là một phần của cấu hình phát hành và cần được review như code.

## 9. Đưa Maven hoặc Gradle vào CI/CD

Một pipeline migration có thể chia thành các bước độc lập:

~~~text
Pull request
    |
    v
Kiểm tra code và changelog
    |
    v
Resolve dependency bằng Wrapper
    |
    v
Liquibase validate
    |
    v
Kiểm tra status và sinh updateSQL
    |
    v
Review SQL + kiểm thử trên database thử nghiệm
    |
    v
Tạo artifact/revision bất biến
    |
    v
Triển khai migration lên môi trường kế tiếp
    |
    v
Xác minh DATABASECHANGELOG và schema
    |
    v
Triển khai ứng dụng tương thích
~~~

Một job CI nên:

- Dùng đúng JDK và Wrapper đã ghim trong repository.
- Khôi phục dependency từ repository đáng tin cậy và kiểm tra phiên bản plugin.
- Lấy JDBC URL và credentials từ secret store.
- Chạy validate trước khi thực thi migration.
- Sinh SQL dự kiến và lưu kết quả review theo chính sách của dự án, tránh để lộ dữ liệu nhạy cảm.
- Thử migration trên database cùng loại và phiên bản gần với môi trường đích.
- Chỉ chạy update khi đúng môi trường, đúng revision và đúng điều kiện phê duyệt.
- Xác minh changeset đã được ghi nhận và ứng dụng hoạt động với schema mới.

Không nên gắn lệnh update vào lifecycle mặc định của mọi lần package/build nếu build đó được chạy ở pull request, máy developer hoặc môi trường không có quyền thay đổi database. Một bước migration tường minh giúp kiểm soát thời điểm, đích triển khai và quyền thực thi.

Đối với production, pipeline cần có bước xác nhận môi trường đích và quyền chạy. Có thể tách job migration và job deploy ứng dụng thành hai giai đoạn để nhóm quan sát kết quả migration trước khi đưa phiên bản code mới vào hoạt động.

## 10. Kiểm chứng SQL, trạng thái và kết quả migration

Các lệnh validate, status, updateSQL và update phục vụ những mục đích khác nhau:

- Validate xác nhận changelog có thể được phân tích theo cấu hình hiện tại; không đảm bảo mọi câu lệnh DDL sẽ chạy thành công trên database thật.
- Status cho biết changeset còn chờ theo lịch sử và bộ lọc đang dùng; nó không phải phép kiểm tra đầy đủ schema drift.
- UpdateSQL cho phép review câu lệnh dự kiến; nó không thực thi và không chứng minh transaction hoặc lock sẽ diễn ra như mong đợi.
- Update thực thi thay đổi và cập nhật lịch sử Liquibase trong database đích.

Một quy trình kiểm chứng đầy đủ nên thử hai trạng thái database:

**Database mới:** tạo database/schema rỗng rồi chạy toàn bộ master changelog. Kết quả phải tạo ra cấu trúc mà ứng dụng cần.

**Database đã tồn tại:** khôi phục bản database ở phiên bản trước, có dữ liệu đại diện, rồi chạy các changeset mới. Xác nhận dữ liệu được giữ đúng, các constraint/index cần thiết được tạo và ứng dụng truy vấn thành công.

Sau khi update, kiểm tra:

- DATABASECHANGELOG ghi nhận changeset mong đợi.
- Schema thật có bảng, cột, index và constraint đúng.
- Dữ liệu backfill hoặc dữ liệu mặc định có giá trị hợp lệ.
- Ứng dụng khởi động và thực hiện được các luồng đọc/ghi liên quan.
- Log không có lỗi migration, lock hoặc lỗi truy vấn phát sinh.

Nếu migration thất bại giữa chừng, không tự xóa bản ghi lịch sử hoặc sửa bảng DATABASECHANGELOG để ép task chạy lại. Trước tiên xác định changeset nào đã chạy, trạng thái transaction của DBMS, schema thực tế và log. Một số DBMS hỗ trợ rollback DDL trong transaction ở mức khác nhau; không được giả định mọi thay đổi đều tự hoàn tác.

## 11. Rollback và sửa lỗi khi chạy qua build tool

Maven và Gradle chỉ là lớp gọi lệnh Liquibase. Quy tắc rollback vẫn do Liquibase, changeset và DBMS quyết định.

Trước khi rollback:

1. Xác nhận đúng database và đúng revision đã triển khai.
2. Kiểm tra tag, số changeset hoặc mốc thời gian sẽ quay lui.
3. Sinh SQL rollback nếu plugin và goal tương ứng hỗ trợ.
4. Kiểm tra rollback có làm mất dữ liệu phát sinh sau migration không.
5. Thử trên database đại diện và xác nhận ứng dụng cũ có tương thích với schema sau rollback.
6. Có backup hoặc phương án phục hồi dữ liệu khi thao tác không thể đảo ngược.

Nếu một changeset tạo bảng có rollback dropTable, rollback có thể xóa cả dữ liệu đã được ứng dụng ghi vào bảng đó sau khi migration chạy. Với thay đổi dữ liệu hoặc migration phá hủy, forward fix đôi khi an toàn hơn rollback.

Khi có lỗi checksum, hãy so sánh changeset hiện tại với phiên bản đã triển khai. Không sửa changeset cũ hoặc chạy clearCheckSums chỉ để bỏ qua lỗi. Nếu cần điều chỉnh, tạo changeset mới và xử lý checksum theo quy trình được review.

## 12. Lỗi thường gặp khi cài đặt và chạy plugin

| Biểu hiện | Nguyên nhân thường gặp | Cách kiểm tra và xử lý |
|---|---|---|
| Maven không tìm thấy liquibase goal | Plugin chưa khai báo hoặc cấu hình sai module | Kiểm tra POM của module, groupId/artifactId/version và gọi đúng goal |
| Gradle không có task update | Plugin chưa được áp dụng hoặc task chưa được đăng ký ở module hiện tại | Kiểm tra plugins block, Gradle Wrapper và danh sách tasks |
| Không tìm thấy JDBC driver | Driver không có trong classpath riêng của plugin/task | Maven: kiểm tra dependencies của plugin; Gradle: kiểm tra liquibaseRuntime |
| Changelog không tìm thấy | Sai đường dẫn tương đối hoặc file không được đóng gói/copy | Xác minh changeLogFile, working directory và resource path |
| Không kết nối được database | URL, host, port, credentials, SSL hoặc network sai | Kiểm tra biến môi trường và quyền truy cập từ đúng runner |
| Validate thành công nhưng update thất bại | SQL không tương thích DBMS, quyền DDL thiếu, precondition không đạt hoặc lock | Đọc lỗi DBMS, SQL sinh ra, precondition và trạng thái lock |
| Local chạy được nhưng CI thất bại | Khác JDK, plugin, driver, biến môi trường hoặc working directory | Dùng Wrapper, ghim dependency và kiểm tra cấu hình job |
| Chạy nhầm database | Biến môi trường hoặc profile trỏ sai đích | In thông tin định danh không nhạy cảm của DB trước khi update và thêm guard theo môi trường |
| Build treo khi migration | Kết nối chờ, lock đang được giữ hoặc prompt tương tác | Kiểm tra log, timeout, tiến trình Liquibase và cấu hình non-interactive |
| Ứng dụng chạy migration lần nữa | Pipeline và Spring Boot cùng bật cơ chế update | Xác định một chủ thể migration chính và cấu hình bật/tắt rõ ràng |

Khi debug, ghi lại phiên bản JDK, Maven/Gradle Wrapper, Liquibase, plugin và JDBC driver. Thông tin này thường giúp phân biệt lỗi cấu hình với lỗi tương thích. Không bật log chứa credentials; nếu cần debug sâu, che các giá trị nhạy cảm trước khi chia sẻ log.

## 13. Nâng cấp phiên bản và giữ build có thể tái lập

Liquibase Core, Maven plugin, Gradle plugin, JDBC driver và Spring Boot có vòng đời phát hành riêng. Nâng cấp một thành phần có thể ảnh hưởng cách parse changelog, sinh SQL, hỗ trợ DBMS, checksum hoặc task/goal.

Khi nâng cấp:

- Chọn phiên bản theo yêu cầu JDK, DBMS và Spring Boot đang dùng.
- Đọc release notes và ghi nhận thay đổi tương thích.
- Nâng cấp plugin và Liquibase Core có chủ đích, tránh để mỗi môi trường tự resolve phiên bản khác nhau.
- Chạy validate, status và updateSQL trên changelog hiện tại.
- Kiểm thử cả database mới lẫn database nâng cấp từ phiên bản cũ.
- Thử rollback và các thay đổi SQL đặc thù DBMS nếu chúng thuộc quy trình khôi phục.
- Cập nhật Wrapper và dependency lock/verification nếu dự án sử dụng.

Không dùng một lệnh upgrade dependency hàng loạt trong lúc đang xử lý sự cố production mà chưa kiểm thử. Giữ một bộ phiên bản đã được xác nhận trong build để developer và CI tạo kết quả nhất quán.

## 14. Bài thực hành: chạy cùng một changelog bằng Maven và Gradle

Giả sử dự án có master changelog tạo bảng customer và bổ sung cột status. Có thể thực hành theo trình tự:

1. Tạo database phát triển riêng và cấp DB_URL, DB_USER, DB_PASSWORD trong môi trường local.
2. Đặt master changelog và changeset vào src/main/resources/db/changelog.
3. Cấu hình Maven plugin hoặc Gradle plugin theo build tool của dự án, bảo đảm JDBC driver nằm trong plugin classpath.
4. Chạy validate và status. Nếu changelog mới, status phải hiển thị các changeset còn chờ.
5. Chạy updateSQL và đọc câu lệnh sinh ra; kiểm tra schema, kiểu dữ liệu, constraint, thứ tự thay đổi và rollback.
6. Chạy update trên database thử nghiệm.
7. Truy vấn schema và DATABASECHANGELOG để xác nhận changeset đã được ghi nhận.
8. Chạy status lần nữa để xác nhận không còn changeset chờ trong cùng bộ lọc.
9. Khởi động ứng dụng Spring Boot hoặc chạy kiểm thử tích hợp để xác nhận code làm việc với schema mới.
10. Nếu dự án hỗ trợ cả Maven và Gradle ở các module khác nhau, xác nhận cả hai cấu hình trỏ tới cùng changelog và cùng bộ phiên bản Liquibase.

Không cần chạy cả Maven và Gradle trên cùng database trong mọi lần phát hành. Mục tiêu thực hành là hiểu classpath và cấu hình của từng plugin, đồng thời bảo đảm chúng thực thi cùng một lịch sử migration nếu tổ chức dự án cần hỗ trợ cả hai.

## 15. Checklist trước khi đưa vào sử dụng

- [ ] Đã xác định dùng plugin build, runtime Spring Boot hay migration job riêng.
- [ ] Đã ghim phiên bản JDK, Maven/Gradle Wrapper, Liquibase và plugin.
- [ ] Liquibase Core được thêm vào ứng dụng nếu runtime cần tự chạy migration.
- [ ] JDBC driver có trong classpath của Maven plugin hoặc Gradle liquibaseRuntime.
- [ ] Master changelog và các file con tồn tại ở đường dẫn được cấu hình.
- [ ] URL, username và password được cấp theo môi trường từ nguồn an toàn.
- [ ] Tài khoản migration có quyền cần thiết và không dùng quyền quá rộng.
- [ ] Validate, status và updateSQL đã được chạy trước update.
- [ ] Migration đã được kiểm tra trên database mới và database có dữ liệu.
- [ ] Context/label và precondition đã được review cho từng môi trường.
- [ ] Pipeline sử dụng đúng Wrapper, revision và artifact đã kiểm tra.
- [ ] Có kế hoạch rollback/forward fix, backup và theo dõi sau triển khai.
- [ ] Chỉ có một cơ chế điều phối migration chính cho mỗi môi trường.
- [ ] DATABASECHANGELOG và schema thực tế đã được xác minh sau update.

Maven và Gradle giúp đưa Liquibase vào quy trình phát triển Java một cách có thể lặp lại. Khi plugin, JDBC driver, changelog và cấu hình môi trường được khai báo rõ ràng, developer có thể kiểm tra SQL trước khi chạy, CI có thể thực hiện migration theo revision đã review, và nhóm vận hành có thể truy vết trạng thái của từng database. Chất lượng của quy trình phụ thuộc vào việc kiểm chứng trên database thật phù hợp, quản lý changeset bất biến và kiểm soát rõ ràng thời điểm migration được thực thi.

