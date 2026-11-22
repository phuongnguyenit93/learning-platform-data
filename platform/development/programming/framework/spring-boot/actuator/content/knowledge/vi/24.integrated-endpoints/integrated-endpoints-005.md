# Kiểm tra thay đổi cơ sở dữ liệu bằng endpoint `liquibase`

## 1. Từ thay đổi lược đồ đến bằng chứng đã triển khai

Giả sử một phiên bản ứng dụng cần bảng `note` và cột `status`. Mã nguồn đã có mô tả tạo bảng, nhưng khi triển khai bạn vẫn cần biết cơ sở dữ liệu mà ứng dụng đang kết nối đã ghi nhận những thay đổi nào. Đây là câu hỏi khác với việc chỉ kiểm tra ứng dụng có trả HTTP 200 hay không.

Endpoint `liquibase` của Actuator cung cấp thông tin về các **change set đã được Liquibase ghi nhận trong cơ sở dữ liệu**. Đường dẫn HTTP mặc định là `GET /actuator/liquibase`. Nó là công cụ quan sát lịch sử thay đổi; thao tác đọc này không phải lệnh chạy migration hay rollback. [API Liquibase của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/liquibase.html)

Các khái niệm cần nắm trước:

- **Migration:** một thay đổi có quản lý đối với cơ sở dữ liệu, chẳng hạn tạo bảng hoặc thêm cột.
- **Changelog:** tệp mô tả tập hợp các thay đổi và thứ tự khai báo.
- **Change set:** đơn vị thay đổi được Liquibase nhận diện và theo dõi.
- **Bảng lịch sử `DATABASECHANGELOG`:** nơi Liquibase lưu thông tin các change set đã ghi nhận.

Định danh một change set dựa trên bộ **`id` + `author` + đường dẫn changelog**, không chỉ riêng `id`. Vì vậy, khi so sánh hai môi trường, phải đối chiếu đủ định danh thay vì thấy cùng một số thứ tự rồi coi là cùng thay đổi. [Bảng DATABASECHANGELOG](https://docs.liquibase.com/concepts/tracking-tables/databasechangelog-table.html)

Bài sử dụng **Java 21, Spring Boot 3.3.13 và Liquibase do BOM của Boot quản lý**. Nhánh Boot này quản lý `liquibase-core` phiên bản `4.27.0`. [Danh mục phiên bản phụ thuộc](https://docs.spring.io/spring-boot/3.3/appendix/dependency-versions/coordinates.html)

## 2. Endpoint nằm ở đâu trong vòng đời migration?

Luồng thường gặp trong ứng dụng Boot:

```text
Changelog được đóng gói cùng ứng dụng
    -> Liquibase kết nối cơ sở dữ liệu khi khởi động
    -> kiểm tra các change set đã ghi nhận
    -> áp dụng những thay đổi đủ điều kiện
    -> ghi thông tin vào bảng lịch sử
    -> Actuator cho phép đọc các thông tin đã ghi nhận
```

Thêm `liquibase-core` vào ứng dụng Boot có cấu hình phù hợp sẽ cho phép migration chạy khi khởi động. Changelog có thể dùng YAML, JSON, XML hoặc SQL; vị trí được điều khiển bởi `spring.liquibase.change-log`. Ví dụ trong bài chọn JSON để biểu diễn rõ cấu trúc dữ liệu. [Khởi tạo cơ sở dữ liệu bằng Liquibase](https://docs.spring.io/spring-boot/3.3/how-to/data-initialization.html)

Cần tách ba câu hỏi:

| Câu hỏi | Bằng chứng cần đối chiếu |
| --- | --- |
| Liquibase đã ghi nhận change set nào? | Endpoint `liquibase` hoặc bảng lịch sử tương ứng |
| Changelog hiện tại còn thay đổi nào chưa triển khai? | Đối chiếu changelog, bộ lọc và công cụ kiểm tra migration |
| Lược đồ đang có đúng bảng/cột mong đợi không? | Metadata hoặc truy vấn trực tiếp vào đúng cơ sở dữ liệu |

Ba câu hỏi liên quan nhưng không thay thế nhau. Một bản ghi lịch sử không tự phát hiện việc ai đó sửa lược đồ thủ công sau migration.

## 3. Dự án thực hành chạy độc lập

### 3.1. Cấu trúc tệp và phụ thuộc

Chuẩn bị JDK 21, Gradle 8.5 và một thư mục thực hành mới:

```text
liquibase-read-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/lab/liquibase/LiquibaseReadApplication.java
    └── resources/
        ├── application.properties
        └── db/changelog/changelog.json
```

`settings.gradle`:

```groovy
rootProject.name = 'liquibase-read-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.liquibase:liquibase-core'
    runtimeOnly 'com.h2database:h2'
}

application {
    mainClass = 'lab.liquibase.LiquibaseReadApplication'
}
```

Ứng dụng dùng H2 dạng tệp để lịch sử còn tồn tại giữa các lần chạy trong cùng thư mục làm việc. Dự án thực hành chỉ dùng Liquibase để quản lý lược đồ; không cần JPA hoặc các tệp `schema.sql`/`data.sql`.

### 3.2. Cấu hình kết nối và HTTP exposure

`src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
server.port=8080

spring.datasource.url=jdbc:h2:file:./data/liquibase-lab;DB_CLOSE_ON_EXIT=FALSE
spring.datasource.username=sa
spring.datasource.password=

spring.liquibase.enabled=true
spring.liquibase.change-log=classpath:/db/changelog/changelog.json

management.endpoints.web.exposure.include=health,liquibase
```

Địa chỉ loopback và tài khoản H2 trên dành cho thí nghiệm cục bộ. Đường dẫn `./data/liquibase-lab` được giải từ thư mục làm việc của tiến trình; cần giữ nguyên thư mục đó khi kiểm tra qua nhiều lần khởi động.

`liquibase` mặc định được bật trong Boot 3.3, nhưng HTTP mặc định chỉ công khai `health`. Nếu ứng dụng đã đặt `management.endpoints.enabled-by-default=false`, bật riêng bằng `management.endpoint.liquibase.enabled=true`. HTTP exposure và quyền truy cập là các lớp cấu hình riêng; `exclude` có ưu tiên hơn `include`. [Cấu hình endpoint Actuator](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)

Ví dụ không thêm Spring Security. Trong ứng dụng có xác thực, người gọi còn phải đáp ứng chính sách truy cập đang áp dụng; việc thêm tên endpoint vào `include` không tự cấp quyền cho người dùng.

### 3.3. Hai change set có quan hệ phụ thuộc

`src/main/resources/db/changelog/changelog.json`:

```json
{
  "databaseChangeLog": [
    {
      "changeSet": {
        "id": "001-create-note",
        "author": "lab",
        "comment": "Create the note table",
        "changes": [
          {
            "createTable": {
              "tableName": "note",
              "columns": [
                {
                  "column": {
                    "name": "id",
                    "type": "BIGINT",
                    "constraints": {
                      "primaryKey": true,
                      "nullable": false
                    }
                  }
                },
                {
                  "column": {
                    "name": "title",
                    "type": "VARCHAR(200)",
                    "constraints": {
                      "nullable": false
                    }
                  }
                }
              ]
            }
          }
        ]
      }
    },
    {
      "changeSet": {
        "id": "002-add-status",
        "author": "lab",
        "comment": "Add note status",
        "changes": [
          {
            "addColumn": {
              "tableName": "note",
              "columns": [
                {
                  "column": {
                    "name": "status",
                    "type": "VARCHAR(20)",
                    "defaultValue": "DRAFT",
                    "constraints": {
                      "nullable": false
                    }
                  }
                }
              ]
            }
          }
        ]
      }
    }
  ]
}
```

Change set đầu tạo bảng với hai cột; change set thứ hai thêm `status` vào bảng đã có. `createTable` và `addColumn` là hai loại thay đổi tương ứng của Liquibase. [createTable](https://docs.liquibase.com/change-types/create-table.html), [addColumn](https://docs.liquibase.com/change-types/add-column.html)

Không dùng thứ tự chữ số trong `id` như cơ chế tự sắp xếp: trong ví dụ, thứ tự đến từ cách khai báo các change set trong changelog.

### 3.4. Mã khởi động và bằng chứng lược đồ

`src/main/java/lab/liquibase/LiquibaseReadApplication.java`:

```java
package lab.liquibase;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class LiquibaseReadApplication {

    public static void main(String[] args) {
        SpringApplication.run(LiquibaseReadApplication.class, args);
    }

    @Bean
    ApplicationRunner showNoteColumns(JdbcTemplate jdbc) {
        return args -> {
            String sql = """
                    SELECT COLUMN_NAME
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA = 'PUBLIC'
                      AND TABLE_NAME = 'NOTE'
                    ORDER BY ORDINAL_POSITION
                    """;
            var columns = jdbc.queryForList(sql, String.class);
            System.out.println("note-columns=" + columns);
        };
    }
}
```

Đoạn kiểm tra đọc metadata của H2 sau khi ứng dụng khởi tạo. H2 lưu thông tin cột và thứ tự cột trong `INFORMATION_SCHEMA.COLUMNS`. [Metadata hệ thống của H2](https://h2database.com/html/systemtables.html)

Tại thư mục thực hành, với Gradle 8.5 và JDK 21 đã sẵn có:

```shell
gradle run
```

Có thể dùng `./gradlew run` hoặc `.\gradlew.bat run` nếu dự án đã có Gradle Wrapper phù hợp. Với cơ sở dữ liệu mới và hai change set trên, dòng do mã ví dụ tự in là:

```text
note-columns=[ID, TITLE, STATUS]
```

Console còn có log của Boot, HikariCP và Liquibase. Dòng trên xác minh các cột đang hiện diện; bước tiếp theo dùng Actuator để xem lịch sử mà Liquibase ghi nhận.

## 4. Gửi yêu cầu và đọc cấu trúc phản hồi

Giữ ứng dụng đang chạy và mở terminal thứ hai:

```shell
curl -i http://127.0.0.1:8080/actuator/liquibase
```

Trên PowerShell, dùng `curl.exe` nếu `curl` đang được ánh xạ sang một lệnh khác. Một yêu cầu thành công trả HTTP 200 cùng JSON. Ví dụ sau chỉ giữ các trường định danh và kiểu thực thi để dễ quan sát:

```json
{
  "contexts": {
    "application": {
      "liquibaseBeans": {
        "liquibase": {
          "changeSets": [
            {
              "id": "001-create-note",
              "author": "lab",
              "execType": "EXECUTED"
            },
            {
              "id": "002-add-status",
              "author": "lab",
              "execType": "EXECUTED"
            }
          ]
        }
      }
    }
  }
}
```

Đây là **bản trích phản hồi**, không phải toàn bộ JSON nguyên trạng. Phản hồi thực tế còn có đường dẫn changelog, checksum, thời điểm, thứ tự thực thi và các metadata khác. `application` là định danh context thường gặp ở ứng dụng đơn giản; `liquibase` là tên bean mặc định trong ví dụ. Cấu trúc được quy định bởi [API Actuator 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/liquibase.html).

Đọc từ ngoài vào trong:

```text
contexts
    -> định danh Spring ApplicationContext
        -> liquibaseBeans
            -> tên bean Liquibase
                -> changeSets
                    -> thông tin từng change set
```

Không giả định mọi ứng dụng đều có đúng một context hoặc một bean. Một hệ thống dùng nhiều nguồn dữ liệu có thể có nhiều cấu hình Liquibase; cần xác định đúng nhánh dữ liệu trước khi so sánh.

## 5. Hiểu các trường mà không nhầm ý nghĩa

### 5.1. Định danh và mô tả

| Trường | Cách sử dụng |
| --- | --- |
| `id`, `author`, `changeLog` | Đối chiếu đủ định danh change set. |
| `description` | Mô tả loại thay đổi, thường được tạo từ các change đã khai báo. |
| `comments` | Chú thích của tác giả. |
| `contexts`, `labels` | Metadata điều kiện/ngữ cảnh của change set. |
| `tag` | Nhãn mốc lịch sử, nếu có. |

Giá trị `changeLog` là đường dẫn được Liquibase ghi nhận. Nó có thể chịu ảnh hưởng của cách đóng gói, đường dẫn khai báo hoặc cấu hình đường dẫn logic; hãy đọc giá trị thực tế thay vì tự tái tạo từ tên tệp ngắn. Bảng lịch sử mặc định lưu các trường tương ứng như `ID`, `AUTHOR`, `FILENAME`, `DESCRIPTION`, `COMMENTS`. [Định danh và các cột lịch sử](https://docs.liquibase.com/concepts/tracking-tables/databasechangelog-table.html)

Có hai nghĩa của `contexts` trong cùng tài liệu:

- `contexts` ở gốc JSON là các **Spring ApplicationContext**.
- `contexts` trong một change set là **metadata context của Liquibase**.

Chúng cũng không tự đồng nghĩa với Spring profile như `dev` hay `prod`. Muốn biết bộ lọc nào thực sự được dùng, phải đọc cấu hình Liquibase của đúng lần triển khai.

### 5.2. Thời điểm, đợt triển khai và thứ tự

`dateExecuted` cho biết thời điểm được ghi nhận; `deploymentId` giúp liên hệ các change set thuộc cùng một thao tác triển khai; `orderExecuted` là thứ tự ghi nhận. Không coi `id` là số thứ tự tự tăng, hoặc `orderExecuted` là một bộ đếm duy nhất dùng chung cho mọi môi trường và mọi lần chạy.

Khi điều tra thứ tự lịch sử, đối chiếu cả thời điểm và thứ tự thay vì chỉ sắp xếp một con số. Liquibase chỉ bảo đảm giá trị `ORDEREXECUTED` tăng trong phạm vi một lần update; các lần update khác không nên được suy diễn thành một dãy toàn cục liên tục. [Ý nghĩa DATEEXECUTED, ORDEREXECUTED và DEPLOYMENT_ID](https://docs.liquibase.com/concepts/tracking-tables/databasechangelog-table.html)

Các timestamp và deployment id phụ thuộc lúc chạy. Vì vậy bài không đưa ra timestamp giả để bạn so khớp như kết quả cố định.

### 5.3. `execType` không chỉ có `EXECUTED`

Hợp đồng REST Boot 3.3 liệt kê các giá trị `EXECUTED`, `FAILED`, `SKIPPED`, `RERAN`, `MARK_RAN`. [Trường execType trong API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/liquibase.html)

Cách tiếp cận khi đọc:

- `EXECUTED`: lịch sử ghi nhận change set đã được thực thi.
- `RERAN`: change set đã được chạy lại; tìm hiểu chính sách như `runOnChange`/`runAlways` và lịch sử triển khai liên quan.
- `MARK_RAN`: được đánh dấu là đã chạy; không được coi đây là bằng chứng rằng các câu lệnh tạo bảng/thêm cột đã thực sự chạy trong thao tác đó.
- `FAILED` hoặc `SKIPPED`, nếu xuất hiện: xem cấu hình, điều kiện và log để giải thích thay vì gộp chúng vào nhóm thành công.

Việc hợp đồng có tên `FAILED` không có nghĩa endpoint lưu đầy đủ mọi lần migration lỗi. Một lỗi khi khởi động có thể làm ứng dụng chưa phục vụ HTTP; lịch sử cũng có thể không có bản ghi mới mà bạn đang tìm.

Liquibase thường cố gắng thực hiện một change set trong giao dịch khi cơ sở dữ liệu hỗ trợ, nhưng khả năng giao dịch của DDL phụ thuộc hệ quản trị và cấu hình. Vì vậy một lần lỗi cần được đối chiếu cả log lẫn trạng thái lược đồ thực tế. [runInTransaction](https://docs.liquibase.com/reference-guide/changelog-attributes/runintransaction)

### 5.4. Checksum nói lên điều gì?

`checksum` là giá trị Liquibase dùng để theo dõi nội dung change set. Nó không phải checksum của toàn bộ tệp changelog và không phải bản băm của toàn bộ lược đồ đang tồn tại. Tiền tố trong chuỗi checksum còn liên quan tới phiên bản thuật toán. [Checksum của change set](https://docs.liquibase.com/concepts/changelogs/changeset-checksums.html)

Vì vậy:

1. Có checksum trong endpoint không chứng minh cơ sở dữ liệu chưa từng bị sửa ngoài Liquibase.
2. Hai kết quả khác checksum cần được đối chiếu theo đúng định danh, phiên bản Liquibase và nội dung triển khai.
3. Đọc endpoint không thay thế bước kiểm tra changelog hiện tại so với lịch sử lưu trong cơ sở dữ liệu.

Với change set thông thường đã triển khai, hãy bổ sung change set mới cho thay đổi tiếp theo. Việc sửa nội dung cũ có thể tạo lỗi kiểm tra checksum. `runOnChange` là một cơ chế có chủ đích cho những trường hợp phù hợp, không phải cách bật đại trà để bỏ qua lỗi. [Quy tắc runOnChange](https://docs.liquibase.com/reference-guide/changelog-attributes/runonchange)

## 6. Lọc thông tin khi phản hồi lớn

Nếu đã cài `jq`, có thể rút ra các dòng cần kiểm tra. Ví dụ sau dành cho Bash và giữ cả định danh context/bean:

```bash
curl -fsS http://127.0.0.1:8080/actuator/liquibase \
  | jq '[
      .contexts | to_entries[] as $ctx
      | $ctx.value.liquibaseBeans | to_entries[] as $bean
      | $bean.value.changeSets[]
      | {
          context: $ctx.key,
          bean: $bean.key,
          changeLog: .changeLog,
          id: .id,
          author: .author,
          execType: .execType
        }
    ]'
```

`to_entries` giữ tên khóa của các object; nhờ đó kết quả không làm mất nguồn gốc context và bean. Các thao tác lọc/chiếu object này được mô tả trong [hướng dẫn jq](https://jqlang.org/manual/). Khi dùng vào kiểm tra triển khai, so khớp tuple `changeLog`, `id`, `author` của đúng nguồn dữ liệu.

Riêng trong dự án một bean của bài, có thể kiểm tra nhanh danh sách id:

```bash
curl -fsS http://127.0.0.1:8080/actuator/liquibase \
  | jq '[.contexts[].liquibaseBeans[].changeSets[].id] | sort'
```

Kết quả mong đợi trên cơ sở dữ liệu thực hành mới:

```json
[
  "001-create-note",
  "002-add-status"
]
```

Lệnh đã sắp xếp theo chuỗi để trình bày ổn định; đó không phải thứ tự thực thi migration. Danh sách id ngắn này chỉ là bước kiểm tra nhanh của bài thực hành, không thay thế định danh đầy đủ trong hệ thống nhiều changelog.

## 7. Quy trình kiểm tra một bản triển khai

### 7.1. Xác định đúng đích trước khi đọc lịch sử

Ghi nhận ứng dụng/bản sao đang truy vấn, môi trường, context, bean Liquibase và cấu hình nguồn dữ liệu liên quan. Cấu hình Liquibase có thể dùng `@LiquibaseDataSource` hoặc các thuộc tính `spring.liquibase.url/user/password` để chọn một nguồn dữ liệu riêng. [Chọn DataSource cho Liquibase](https://docs.spring.io/spring-boot/3.3/how-to/data-initialization.html)

Điều này quan trọng khi endpoint có đủ change set nhưng truy vấn nghiệp vụ lại không thấy bảng: có thể hai thao tác đang nhìn vào hai cơ sở dữ liệu hoặc hai schema khác nhau.

### 7.2. Đối chiếu ba lớp bằng chứng

Với ví dụ của bài:

1. **Nguồn triển khai:** changelog có `001-create-note` rồi `002-add-status`, cùng tác giả `lab`.
2. **Lịch sử ghi nhận:** nhánh Liquibase phù hợp có hai định danh đó với kiểu thực thi mong đợi.
3. **Lược đồ thực tế:** truy vấn metadata trong mã Java trả `ID`, `TITLE`, `STATUS`.

Nếu ba lớp không khớp, xác định lớp nào đang lệch trước khi thay đổi cấu hình. Ví dụ, có `MARK_RAN` nhưng thiếu cột là tình huống khác với việc migration chưa bao giờ được triển khai đến cơ sở dữ liệu đó.

Có thể đối chiếu trực tiếp bảng lịch sử bằng một công cụ SQL được kết nối đúng đích:

```sql
SELECT ID, AUTHOR, FILENAME, EXECTYPE,
       DATEEXECUTED, ORDEREXECUTED, MD5SUM
FROM DATABASECHANGELOG
ORDER BY DATEEXECUTED, ORDEREXECUTED;
```

Tên trên là tên bảng mặc định. Nếu dự án đã đổi tên bảng lịch sử hoặc schema của nó, dùng cấu hình tương ứng. Với H2 dạng tệp đang được ứng dụng mở, một tiến trình SQL khác có thể không mở được cùng tệp; trong thí nghiệm có thể dừng ứng dụng rồi kết nối đúng tệp để đọc.

### 7.3. Những điều endpoint không tự xác nhận

Endpoint này không cung cấp danh sách đầy đủ mọi thay đổi còn chờ trong changelog hiện tại, không kiểm tra mọi sai lệch lược đồ, không thử khả năng rollback và không lưu toàn bộ lịch sử sự kiện ở mức kiểm toán.

Khi cần tìm change set chưa triển khai, dùng quy trình Liquibase phù hợp, chẳng hạn lệnh `status` với đúng changelog, kết nối và bộ lọc. `status` được thiết kế để liệt kê các change set chưa triển khai. [Lệnh status](https://docs.liquibase.com/commands/change-tracking/status.html)

Khi cần kiểm tra cấu trúc changelog, dùng bước xác thực phù hợp với phiên bản đang dùng. Dù bước `validate` đạt, nó cũng không bảo đảm mọi SQL sẽ thực thi thành công trên hệ quản trị đích. [Phạm vi validate](https://docs.liquibase.com/commands/utility/validate.html)

Không dùng `clear-checksums`, đánh dấu lịch sử hoặc rollback chỉ để làm cho một kết quả kiểm tra trông giống mong đợi. Trước tiên cần hiểu nguyên nhân lệch và tác động lên dữ liệu.

## 8. Thực hành thêm một thay đổi và đọc lại

Sau lần chạy đầu, dừng ứng dụng. Thêm **phần tử mới** sau change set thứ hai trong mảng `databaseChangeLog` của cùng tệp JSON; đặt dấu phẩy đúng giữa các phần tử:

```json
{
  "changeSet": {
    "id": "003-add-source",
    "author": "lab",
    "comment": "Add note source",
    "changes": [
      {
        "addColumn": {
          "tableName": "note",
          "columns": [
            {
              "column": {
                "name": "source",
                "type": "VARCHAR(20)",
                "defaultValue": "manual",
                "constraints": {
                  "nullable": false
                }
              }
            }
          ]
        }
      }
    ]
  }
}
```

Đoạn JSON trên là một phần tử để thêm vào changelog, không phải một changelog gốc độc lập. Giữ nguyên hai change set đã áp dụng, rồi chạy lại từ **cùng thư mục làm việc** để kết nối đúng tệp H2 trước đó.

Các kết quả mong đợi:

- Dòng metadata trở thành `note-columns=[ID, TITLE, STATUS, SOURCE]`.
- Endpoint có thêm `003-add-source` với tác giả `lab` và kiểu thực thi phù hợp.
- Hai change set ban đầu vẫn hiện diện theo định danh của chúng; với cấu hình thông thường của ví dụ, chúng không được thực thi lại chỉ vì khởi động lại ứng dụng.

Gọi GET thêm nhiều lần chỉ đọc lịch sử; nó không tự thêm cột mới hoặc tăng số bản ghi lịch sử. Nếu ứng dụng khởi động lỗi vì changelog, bắt đầu từ log khởi động thay vì chờ endpoint trả về một bản ghi thất bại.

## 9. Chẩn đoán theo hiện tượng

| Hiện tượng | Hướng kiểm tra |
| --- | --- |
| 404 ở `/actuator/liquibase` | Kiểm tra URL, cổng/base path, bật endpoint, HTTP exposure và bean Liquibase phù hợp. |
| 401 hoặc 403 | Kiểm tra xác thực và quyền truy cập endpoint. |
| Không kết nối được sau triển khai | Kiểm tra tiến trình và log khởi động, gồm lỗi kết nối hoặc migration. |
| Không thấy change set mong đợi | Đúng database/schema/changelog/profile/bộ lọc và bản triển khai chưa? |
| Lịch sử có bản ghi nhưng thiếu bảng/cột | Kiểm tra `execType`, đúng schema và khả năng lược đồ đã bị sửa ngoài Liquibase. |
| Có lỗi checksum | Đối chiếu định danh, nội dung cũ, phiên bản Liquibase và chính sách chạy lại. |
| Endpoint gặp lỗi khi đọc | Kiểm tra kết nối, quyền đọc bảng lịch sử và log phía ứng dụng. |

HTTP 200 chỉ cho biết yêu cầu đọc đã thành công trong ngữ cảnh đó. Kết luận “bản triển khai cơ sở dữ liệu đúng” cần gắn với các change set dự kiến và bằng chứng lược đồ/dữ liệu liên quan.

Thông tin trả về có thể làm lộ tên bảng, đường dẫn changelog và chú thích nội bộ. Cấp quyền đọc theo nhu cầu vận hành và giữ thông tin kết nối trong cấu hình bí mật phù hợp.

## 10. Tự kiểm tra kiến thức

1. Vì sao không dùng riêng `id` để so sánh change set giữa hai changelog?
2. `contexts` ở gốc JSON khác `contexts` trong change set thế nào?
3. Vì sao `MARK_RAN` không đủ chứng minh SQL đã thực sự chạy?
4. Checksum có phát hiện mọi thay đổi lược đồ thủ công không?
5. Nếu migration khiến ứng dụng không khởi động, vì sao không thể dựa vào endpoint để xem đầy đủ lỗi?
6. Cần thêm bằng chứng gì ngoài HTTP 200 để xác nhận cột mới đã có trong đúng cơ sở dữ liệu?

Một câu trả lời đủ cần liên hệ định danh, nguồn dữ liệu, lịch sử thực thi và cấu trúc thực tế; đó là cách dùng endpoint `liquibase` để kiểm tra một thay đổi có căn cứ.
