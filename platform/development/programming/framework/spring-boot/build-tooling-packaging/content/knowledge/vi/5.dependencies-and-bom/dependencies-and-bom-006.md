# Phân biệt khai báo dependency với dependencyManagement

Khi làm việc với Spring Boot, Maven và Gradle, hai thao tác dễ bị nhầm lẫn là **khai báo một thư viện cần dùng** và **quản lý phiên bản/quy tắc chọn thư viện**. Chúng liên quan chặt chẽ nhưng trả lời hai câu hỏi khác nhau:

- **Dependency declaration:** “Dự án này cần thành phần nào để biên dịch, chạy hoặc kiểm thử?”
- **Dependency management:** “Khi một thành phần xuất hiện trong cây phụ thuộc, nên chọn phiên bản và một số quy tắc liên quan như thế nào?”

Quy tắc cốt lõi: **quản lý phiên bản không tự làm thư viện xuất hiện trong classpath**. Thư viện chỉ tham gia cây phụ thuộc khi được khai báo thực tế hoặc được kéo vào qua quan hệ phụ thuộc bắc cầu (*transitive dependency*). Spring Boot BOM là ví dụ điển hình của cơ chế quản lý phiên bản.

## 1. Hai công việc riêng biệt trong một đồ thị phụ thuộc

Giả sử ứng dụng REST cần `spring-boot-starter-web`. Khi khai báo starter này, build tool sẽ đưa starter vào đồ thị phụ thuộc và truy ra những thành phần nó cần, chẳng hạn Spring Web, Spring MVC và các thư viện khác phù hợp với phiên bản đang dùng.

BOM (*Bill of Materials*) của Spring Boot lại chứa **thông tin quản lý phiên bản** cho nhiều module. BOM giúp các module trong hệ sinh thái được chọn theo một bộ phiên bản đã được kiểm thử cùng nhau. Chỉ import BOM mà không khai báo starter hoặc thư viện khác thì ứng dụng **không tự có Spring MVC, Jackson hay web server**.

~~~text
KHAI BÁO PHỤ THUỘC (chọn "cần gì")
  spring-boot-starter-web
          |
          +--> spring-webmvc
          +--> spring-web
          +--> các dependency bắc cầu khác

QUẢN LÝ PHIÊN BẢN (chọn "phiên bản nào")
  spring-boot-dependencies BOM
          |
          +--> quy tắc phiên bản cho Spring modules
          +--> quy tắc phiên bản cho nhiều thư viện bên thứ ba

Kết quả resolve = Các dependency thực sự có mặt
                + Quan hệ bắc cầu
                + Quy tắc quản lý / giải quyết xung đột.
~~~

Không phải mọi mục được liệt kê trong BOM đều xuất hiện trong classpath; chỉ những mục được cần đến trong đồ thị mới có cơ hội được chọn phiên bản. Ngược lại, khai báo dependency mà không có quy tắc quản lý phiên bản phù hợp có thể buộc bạn phải chỉ định phiên bản trực tiếp hoặc để hệ thống resolve theo cơ chế khác.

## 2. Maven: `<dependencies>` khác `<dependencyManagement>` như thế nào?

Trong Maven, sự phân biệt thể hiện trực tiếp qua hai phần XML.

### 2.1. `<dependencies>`: yêu cầu một dependency thực sự

Ví dụ một đoạn trong `pom.xml`:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
        <version>3.3.5</version>
    </dependency>
</dependencies>
~~~

Maven có một dependency trực tiếp là `spring-boot-starter-web`. Nó sẽ giải quyết thêm các dependency bắc cầu theo metadata của artifact và các quy tắc quản lý đang có. Ví dụ chỉ để minh họa việc **khai báo thực tế**; trong dự án Spring Boot được quản lý bằng BOM hoặc starter parent, thường **không ghi phiên bản starter lặp lại**.

Những thuộc tính quan trọng trong dependency declaration:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `groupId` + `artifactId` | Nhận diện thư viện |
| `version` | Phiên bản yêu cầu, có thể bỏ khi đã được quản lý phù hợp |
| `scope` | Phạm vi như `compile`, `runtime`, `test`, `provided` |
| `optional` | Hạn chế việc dependency truyền sang dự án tiêu thụ như dependency bắc cầu |
| `exclusions` | Loại những dependency bắc cầu cụ thể khỏi nhánh đang khai báo |

`<dependencies>` trả lời “dự án đang dùng gì”, nhưng việc một artifact được tải về cũng phụ thuộc vào scope, profiles, lựa chọn phiên bản và các nhánh bắc cầu.

### 2.2. `<dependencyManagement>`: khai báo quy tắc mặc định

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
            <version>3.3.5</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Đoạn này quản lý phiên bản cho `spring-boot-starter-web`, nhưng **không tạo một dependency trực tiếp** trong dự án chỉ nhờ chính đoạn XML trên. Muốn dùng starter, cần khai báo nó:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
~~~

Khi đó Maven có thể lấy phiên bản `3.3.5` từ `dependencyManagement`. Đây là quan hệ **quy tắc + nhu cầu thực tế**.

`dependencyManagement` cũng có thể ảnh hưởng lựa chọn phiên bản của dependency **bắc cầu** khi tọa độ artifact khớp. Vì vậy không nên hiểu “chỉ áp dụng cho dependency khai báo trực tiếp”. Điều chính xác là phần management **không tự thêm một nhánh dependency**, nhưng có thể chi phối phiên bản một dependency nếu nó xuất hiện trong đồ thị do nhánh khác kéo vào.

### 2.3. So sánh nhanh trong Maven

| Chỉ có cấu hình nào? | Có yêu cầu tải `spring-boot-starter-web` như dependency của ứng dụng? | Phiên bản đến từ đâu? |
| --- | --- | --- |
| Chỉ `<dependencyManagement>` quản lý starter | **Không** | Có quy tắc phiên bản nhưng chưa có nhu cầu dùng |
| Chỉ `<dependencies>` có starter với `<version>` | **Có** | Phiên bản ghi trực tiếp |
| `<dependencies>` có starter không version, management quản lý starter | **Có** | Phiên bản do management cung cấp |
| Chỉ import Spring Boot BOM | **Không** | BOM cung cấp nhiều quy tắc, chưa tự thêm starter |
| Import BOM **và** khai báo starter | **Có** | BOM quản lý phiên bản starter và nhiều dependency liên quan |

Trong một `pom.xml` không có version trên dependency và cũng không có version phù hợp từ management/parent, Maven thông thường sẽ báo lỗi thiếu version khi xây mô hình project. Không thể coi “bỏ version” là luôn hợp lệ.

## 3. Spring Boot BOM: import bộ phiên bản được quản lý

BOM của Spring Boot có tọa độ `org.springframework.boot:spring-boot-dependencies`. Nó tập hợp các phiên bản thư viện mà Spring Boot đã kiểm thử cho một release cụ thể.

### Cách A — Dùng `spring-boot-starter-parent` trong Maven

Spring Boot starter parent kế thừa dependency management của Spring Boot, cùng một số cấu hình plugin/build mặc định. Ví dụ `pom.xml` tối giản để minh họa:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>dependency-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

Ở đây có hai nhu cầu thực tế: web starter và test starter. Chúng không ghi version vì parent cung cấp dependency management. `spring-boot-starter-test` có `scope=test`, nên các thư viện chỉ phục vụ kiểm thử không trở thành phụ thuộc runtime chính của ứng dụng.

Bản `3.3.5` chỉ là phiên bản **cố định cho ví dụ**, không hàm ý đây là phiên bản Spring Boot mới nhất hoặc nên dùng cho dự án mới. Để có executable Spring Boot JAR từ Maven, cần thêm/cấu hình `spring-boot-maven-plugin` theo quy trình packaging tương ứng; dependency management tự nó không tạo JAR thực thi.

### Cách B — Import BOM khi dự án không dùng starter parent

Dự án có thể phải kế thừa một Maven parent khác. Khi đó import Spring Boot BOM trực tiếp trong `<dependencyManagement>`:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.3.5</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
~~~

Đây là **đoạn cấu hình đặt bên trong `<project>` của `pom.xml`**, không phải một POM độc lập. BOM import cần cả `<type>pom</type>` và `<scope>import</scope>` trong khối management. Sau import, dependency bên dưới có thể bỏ version đã được BOM quản lý.

Phân biệt với một dependency có scope `runtime`: `import` trong `dependencyManagement` **không phải** thêm BOM như JAR vào runtime classpath; nó đưa các quy tắc management của BOM vào mô hình build.

**Lưu ý về parent:** import BOM mang đến dependency management; nó **không tự mang theo toàn bộ cấu hình plugin management/các mặc định build** mà `spring-boot-starter-parent` cung cấp. Khi không dùng starter parent, phải tự xét cấu hình `maven-compiler-plugin`, `spring-boot-maven-plugin` và các plugin cần thiết. Cấu hình `dependencyManagement` không thay cho `pluginManagement`.

## 4. Gradle: các tên gọi khác nhưng vẫn tách nhu cầu và quản lý

Gradle không dùng các thẻ XML `<dependencies>` và `<dependencyManagement>` của Maven như một ngôn ngữ cấu hình gốc. Nó thường khai báo dependency theo **configuration** và quản lý phiên bản qua **platform/BOM, dependency constraints**, hoặc plugin quản lý dependency của Spring.

### 4.1. `dependencies`: thêm thư viện vào cấu hình

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web:3.3.5'
    testImplementation 'org.springframework.boot:spring-boot-starter-test:3.3.5'
}
~~~

Đây là đoạn `build.gradle` minh họa, giả định đã áp dụng Java plugin và có repository thích hợp. `implementation` bổ sung dependency vào quá trình biên dịch/chạy của mã chính; `testImplementation` phục vụ mã test.

Với dự án thực tế dùng Spring Boot BOM, bỏ version ở những dependency đã được BOM quản lý giúp giảm khai báo trùng lặp và tránh các thư viện trong hệ sinh thái lệch phiên bản.

### 4.2. Gradle native BOM qua `platform(...)`

Gradle hỗ trợ nhập BOM bằng dependency platform, không nhất thiết phải dùng plugin quản lý dependency bên ngoài:

~~~groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.5')
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Đây là `build.gradle` hợp lệ để xem/resolution dependency graph khi dùng Gradle phiên bản tương thích. `platform(...)` đưa các **version constraints** từ BOM vào quá trình resolve. Dòng `implementation '...starter-web'` mới yêu cầu starter. Nếu bỏ dòng này, chỉ import BOM không tự làm dự án có thư viện web.

Gradle xử lý xung đột phiên bản bằng cơ chế resolution của nó. Platform thông thường đưa ra ràng buộc/khuyến nghị phiên bản theo metadata; **không nên mặc định một BOM thường sẽ cưỡng chế tuyệt đối mọi phiên bản** khi có các yêu cầu cạnh tranh. `enforcedPlatform(...)` có tính cưỡng chế mạnh hơn và có thể ảnh hưởng đến dự án tiêu thụ thư viện do bạn xuất bản; chỉ dùng khi hiểu hệ quả.

### 4.3. Spring Boot Gradle plugin + `io.spring.dependency-management`

Một lựa chọn phổ biến khác:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Khi **cả** Spring Boot Gradle plugin và `io.spring.dependency-management` plugin được áp dụng, tích hợp Spring Boot có thể tự import BOM `spring-boot-dependencies` phù hợp với phiên bản Boot plugin, nên các starter bên trên không cần ghi version. Đây là cơ chế riêng của cặp plugin này; không được suy luận rằng **chỉ** áp dụng `org.springframework.boot` sẽ luôn tự quản lý phiên bản theo cách của `io.spring.dependency-management`.

Khi dùng riêng plugin `io.spring.dependency-management`, cú pháp import BOM có thể viết rõ:

~~~groovy
dependencyManagement {
    imports {
        mavenBom 'org.springframework.boot:spring-boot-dependencies:3.3.5'
    }
}
~~~

Đoạn này chỉ hợp lệ khi plugin tương ứng đã được áp dụng. Nó import quy tắc quản lý, **không** tự thêm `spring-boot-starter-web`. Có thể chọn một chiến lược nhất quán cho dự án thay vì import nhiều lần BOM với các phiên bản khác nhau.

### 4.4. Dependency constraints và version catalogs không phải dependency thực tế

Gradle còn có `constraints` để định nghĩa điều kiện chọn phiên bản cho module:

~~~groovy
dependencies {
    constraints {
        implementation('org.apache.commons:commons-lang3:3.14.0')
    }
}
~~~

Chỉ có constraint này không khiến `commons-lang3` xuất hiện như một JAR runtime nếu đồ thị phụ thuộc không cần nó. Khi một dependency thực sự cần artifact đó, constraint có thể ảnh hưởng version resolution; cơ chế cụ thể còn phụ thuộc các ràng buộc cạnh tranh.

Tệp `gradle/libs.versions.toml` (*version catalog*) lại là danh sách tên/phiên bản/alias thuận tiện khi **tham chiếu** dependency và plugin. Có alias trong catalog không tự thêm dependency vào project; phải dùng alias trong `dependencies` hoặc cấu hình plugin tương ứng. Version catalog không tự thay thế toàn bộ hành vi của BOM trong việc đồng bộ phiên bản bắc cầu.

### Ánh xạ tư duy Maven và Gradle

| Ý định | Maven | Gradle |
| --- | --- | --- |
| Yêu cầu thư viện cho mã chính | `<dependencies><dependency>...` | `implementation 'group:artifact'` |
| Yêu cầu thư viện cho test | `<scope>test</scope>` | `testImplementation 'group:artifact'` |
| Quản lý phiên bản tập trung | `<dependencyManagement>` | `platform(...)`, constraints hoặc dependency-management plugin |
| Import Spring Boot BOM | `<type>pom</type>` + `<scope>import</scope>` trong management | `platform('...spring-boot-dependencies:...')` hoặc `mavenBom` |
| Kế thừa mặc định build và dependency từ Boot | `spring-boot-starter-parent` | Kết hợp plugin Gradle/cấu hình build thích hợp; không có Maven parent trực tiếp |
| Xem các phiên bản đã chọn | `mvn dependency:tree` | `./gradlew dependencies` / `dependencyInsight` |

Các scope/configuration của hai build tool không tương đương hoàn toàn một-một. Cần xét loại module (ứng dụng hay thư viện) và mục đích cụ thể. Ví dụ Gradle `api` chỉ có khi áp dụng plugin `java-library`; đừng nhầm `api` với `implementation` khi xuất bản thư viện.

## 5. Dependency trực tiếp, bắc cầu và phiên bản hiệu lực

Giả sử có ba nút:

~~~text
Ứng dụng
  |
  +-- trực tiếp: spring-boot-starter-web
                    |
                    +-- bắc cầu: spring-webmvc
                    +-- bắc cầu: các thư viện khác
~~~

- **Dependency trực tiếp** được khai báo bằng `<dependencies>` của Maven hoặc `implementation`/configuration tương ứng của Gradle.
- **Dependency bắc cầu** xuất hiện do dependency trực tiếp (hoặc bắc cầu khác) cần nó.
- **Managed version/constraint** có thể ảnh hưởng cả thành phần trực tiếp và thành phần bắc cầu, nếu module đó nằm trong phạm vi quy tắc.

Ví dụ Spring Boot BOM quản lý nhiều thư viện Jackson. Khi starter web khiến Jackson xuất hiện trong đồ thị, rule quản lý version của Jackson có thể được áp dụng. Điều này **không** có nghĩa chỉ cần import BOM là Jackson xuất hiện. Nó xuất hiện vì một đường dependency có thật.

### Khi khai báo version trực tiếp thì sao?

Với **Maven**, một version được ghi tường minh trong khai báo dependency trực tiếp thường là yêu cầu cụ thể cho dependency đó; quy tắc `dependencyManagement` thường dùng để điền version **khi declaration không ghi version** hoặc điều phối lựa chọn version ở đồ thị bắc cầu. Các phiên bản xung đột còn chịu quy tắc mediation và quản lý của Maven.

Với **Gradle**, các yêu cầu version, platform constraints, constraints và quy tắc conflict resolution cùng tham gia lựa chọn phiên bản cuối cùng. Một version ghi trong notation không luôn đồng nghĩa khóa cứng version đó; muốn biết thật sự chọn gì, **phải xem resolved graph**.

Điều quan trọng là phân biệt:

1. **Requested version:** phiên bản mà một khai báo hoặc dependency bắc cầu yêu cầu.
2. **Managed/constrained version:** phiên bản được đề xuất, quản lý hoặc ràng buộc bởi parent/BOM/constraint.
3. **Resolved version:** phiên bản build tool chọn cuối cùng cho cấu hình/phạm vi đang xét.

Không nên dựa chỉ vào `pom.xml` hay `build.gradle` để suy ra chính xác mọi JAR nằm trong runtime.

## 6. Ví dụ trước–sau: từ khai báo version lặp lại sang quản lý tập trung

**Trước — Maven ghi phiên bản riêng từng dependency:**

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
        <version>3.3.5</version>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <version>3.3.5</version>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

**Sau — import một BOM trong management và giữ nguyên nhu cầu dùng thư viện:**

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.3.5</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Hai đoạn này là những **mảnh cấu hình đặt trong `<project>`**, không phải hai ứng dụng chạy độc lập. Sau khi chuyển, danh sách starter **vẫn được khai báo rõ ràng**: management chỉ thay nơi quyết định version. Lợi ích là nâng cấp phiên bản BOM tập trung và giảm khả năng vô tình khai báo các dependency thuộc hệ sinh thái Boot không tương thích với nhau.

**Lưu ý:** BOM có thể quản lý phiên bản của nhiều module bắc cầu ngoài hai starter trên; do đó dù starter trực tiếp vẫn như cũ, cây dependency sau khi migrate có thể khác nếu trước đây bạn đã cố định version thủ công ở những nơi khác. Cần kiểm tra cây phụ thuộc và chạy test khi thay đổi cơ chế quản lý.

## 7. Kiểm tra bằng lệnh thay vì suy đoán

### Maven

Tại thư mục chứa `pom.xml`:

~~~bash
mvn help:effective-pom
mvn dependency:tree
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-web
~~~

- `help:effective-pom` cho biết POM sau kế thừa parent, import BOM và áp dụng cấu hình hiệu lực. Có thể tìm trong đó phần management để xác định phiên bản quản lý.
- `dependency:tree` thể hiện những dependency thực sự được resolve theo scope và quan hệ cây. Một module chỉ có trong `dependencyManagement` nhưng không có đường dependency thực tế sẽ không xuất hiện như một dependency JAR của ứng dụng.
- `-Dincludes=...` giúp lọc tọa độ artifact cần quan sát. Lệnh có thể cần tải Maven plugins/dependencies lần đầu.

Muốn kiểm tra runtime và test, hãy xét đúng scope của dependency thay vì nhìn một danh sách artifact rồi kết luận tất cả đều đóng gói vào sản phẩm. Khi thấy phiên bản lạ, kiểm tra cả parent, management, declaration trực tiếp và đường dependency bắc cầu.

### Gradle

Trên Linux/macOS dùng Gradle Wrapper:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency spring-boot-starter-web --configuration runtimeClasspath
~~~

Trên Windows thay `./gradlew` bằng `gradlew.bat`. `dependencies` in đồ thị theo configuration; `dependencyInsight` cho biết lý do version được chọn, các yêu cầu và đường liên quan. Các kết quả phụ thuộc plugin, repositories, phiên bản Gradle và graph thực tế nên **không gán một stdout cố định** cho các lệnh này.

Khi chỉ import platform/BOM mà chưa khai báo starter, hãy kiểm tra: bạn có thể thấy thông tin platform/constraint nhưng **không có** dependency web như một thư viện runtime chỉ vì BOM có liệt kê nó.

Để làm thí nghiệm có kiểm soát: bắt đầu từ project tối giản, import BOM, quan sát graph; sau đó thêm một dòng `implementation 'org.springframework.boot:spring-boot-starter-web'` hoặc Maven `<dependency>` tương đương, chạy lại graph và so sánh. Đây là cách thấy rõ việc **thêm nhu cầu dependency** khác với **quản lý phiên bản**.

## 8. Các trường hợp dễ nhầm với dependencyManagement

### 8.1. “Khai báo BOM rồi mà code vẫn không import được Spring Web?”

Vì BOM chỉ quản lý version. Thêm dependency cần thiết vào `<dependencies>` hoặc `implementation`. Sau đó kiểm tra scope/configuration, repository và công cụ đang dùng để compile. Nếu mã nguồn import Spring Web nhưng dependency chỉ ở `testImplementation`, mã nguồn chính sẽ không thấy thư viện đó.

### 8.2. “Đã khai báo starter nhưng Maven báo thiếu version?”

Kiểm tra POM có thực sự kế thừa parent phù hợp hoặc import BOM đúng cú pháp `type=pom`, `scope=import` trong `dependencyManagement` không. Kiểm tra effective POM và tọa độ `groupId:artifactId`. BOM có thể không quản lý một thư viện tùy ý ngoài tập hỗ trợ của nó; với thư viện đó cần version/management riêng.

### 8.3. “Tại sao có thư viện trong runtime dù không khai báo trực tiếp?”

Nó có thể được kéo vào **bắc cầu**. Dùng `dependency:tree` hoặc `dependencyInsight` để xác định đường nào cần thư viện đó. Quản lý version không giải thích được *vì sao* thư viện được yêu cầu; nó chủ yếu tham gia quyết định *phiên bản nào* được chọn.

### 8.4. “Có BOM rồi sao hai module vẫn dùng version khác với tôi tưởng?”

Có thể do dependency trực tiếp ghi version, BOM khác, parent khác, quy tắc conflict resolution, constraint, dependency lock hoặc plugin cấu hình ở nơi khác. Phiên bản trong BOM chưa chắc luôn là version cuối cùng trong Gradle. Kiểm tra **resolved graph**, không chỉ so sánh tên artifact trong file cấu hình.

### 8.5. “DependencyManagement có thay cho `spring-boot-maven-plugin` không?”

Không. Dependency management quản lý dependencies của project. `spring-boot-maven-plugin` là build plugin cung cấp các goal như `repackage`; còn `spring-boot-gradle-plugin` bổ sung các task như `bootJar`. Sử dụng BOM không tự cấu hình mọi bước packaging, và plugin packaging không tự thay cho việc khai báo starter ứng dụng cần dùng.

### 8.6. “Có thể đặt mọi dependency trong parent POM để con dùng không?”

Maven parent `<dependencies>` có thể được kế thừa thành **dependency thực tế** ở module con. Nếu chỉ muốn tập trung **quy tắc phiên bản** mà không ép mọi module con mang cùng dependency, đặt các phiên bản vào parent `<dependencyManagement>` và để từng module con khai báo dependency nó cần. Đây là một giá trị quan trọng của management trong dự án nhiều module.

### 8.7. “Muốn ghi đè một version mà BOM đang quản lý?”

Có thể có lý do như vá lỗ hổng bảo mật, nhưng phải dựa trên ma trận tương thích, kiểm thử và resolved graph. Cách override phụ thuộc Maven starter parent, Maven BOM import, Gradle platform hay dependency-management plugin. **Không suy luận rằng đổi một property trong POM luôn override được BOM import**: cơ chế properties/precedence khác nhau giữa parent inheritance và imported BOM. Hãy dùng cơ chế override được hỗ trợ của cấu hình thực tế và kiểm tra phiên bản cuối cùng.

### 8.8. “Version catalog Gradle đã định nghĩa starter rồi sao dependency không có?”

Alias trong `libs.versions.toml` chỉ là dữ liệu khai báo để có thể tham chiếu thuận tiện. Nó không tự thêm module nào. Dự án vẫn phải sử dụng alias ở khối `dependencies` phù hợp; và chỉ định alias không mặc nhiên áp dụng một BOM để quản lý tất cả dependency bắc cầu.

## 9. Quy trình chọn cơ chế đúng trong dự án Spring Boot

1. **Xác định các thư viện thật sự cần dùng.** Chọn starter và dependency theo chức năng, phân định rõ main/test/compile-only/runtime-only.
2. **Chọn một cách quản lý phiên bản nhất quán.** Maven có thể dùng Spring Boot starter parent hoặc import Boot BOM. Gradle có thể dùng native platform hoặc tích hợp plugin dependency management, tùy cấu trúc dự án.
3. **Đảm bảo quản lý đúng một bộ Spring Boot tương thích.** Tránh vô tình trộn version của Boot plugin, BOM, starter và các module framework.
4. **Không ghi version lặp lại khi đã có quy tắc phù hợp** trừ khi có lý do rõ ràng và đã hiểu precedence.
5. **Kiểm tra effective configuration và resolved graph** sau khi thay đổi. Ưu tiên xem riêng `compileClasspath`, `runtimeClasspath` và `testRuntimeClasspath` (Gradle) hoặc scopes tương ứng (Maven).
6. **Chạy build và test**, đặc biệt khi đổi BOM/parent/Gradle constraints, vì một thay đổi version quản lý có thể ảnh hưởng nhiều dependency bắc cầu dù mã nguồn không đổi.

Một bảng quyết định ngắn:

| Bạn muốn làm gì? | Nơi cần chỉnh |
| --- | --- |
| Dùng Spring MVC cho ứng dụng | Khai báo `spring-boot-starter-web` trong dependencies |
| Đảm bảo các thư viện Boot chọn phiên bản đồng bộ | Boot BOM / starter parent / Gradle platform hoặc dependency management |
| Thư viện chỉ cần cho kiểm thử | Scope `test` (Maven), `testImplementation` (Gradle) |
| Cập nhật phiên bản của cả bộ phụ thuộc được Spring Boot quản lý | Cập nhật release Boot parent/BOM hoặc version dùng để import |
| Xác minh version thật sự được chọn | Maven dependency tree/effective POM hoặc Gradle dependencies/dependencyInsight |
| Tạo executable Boot archive | Cấu hình và thực thi Spring Boot Maven/Gradle build plugin tương ứng |

## 10. Tự kiểm tra hiểu đúng

**Câu 1.** Một project Maven chỉ import `spring-boot-dependencies` bằng `scope=import`. Project đã có `spring-boot-starter-web` trong dependency tree chưa?

**Đáp án:** Chưa thể kết luận có; BOM tự nó không khai báo nhu cầu sử dụng starter. Cần dependency trực tiếp hoặc một đường bắc cầu thực tế.

**Câu 2.** Maven có management cho `spring-boot-starter-web` version `3.3.5` và khai báo dependency starter không version. Version lấy ở đâu?

**Đáp án:** Từ `dependencyManagement` hiệu lực (giả sử không có cấu hình khác làm thay đổi lựa chọn). Đây là một dependency thực tế được version management hỗ trợ.

**Câu 3.** Gradle có `implementation platform('...spring-boot-dependencies:3.3.5')` nhưng không có `implementation '...spring-boot-starter-web'`. Mã nguồn chính có tự dùng được Spring MVC không?

**Đáp án:** Không chỉ nhờ platform; phải có dependency phù hợp trong compile classpath.

**Câu 4.** Một thư viện không khai báo trực tiếp vẫn có mặt trong `runtimeClasspath`. Có phải BOM “kéo” nó vào?

**Đáp án:** Thông thường phải tìm đường dependency bắc cầu nào đã yêu cầu nó. BOM/platform có thể ảnh hưởng version được chọn nhưng không tự tạo đường phụ thuộc thư viện thông thường.

**Câu 5.** Một thư viện trong BOM được quản lý version A nhưng dependency graph hiển thị version B. Cần kiểm tra gì?

**Đáp án:** Version ghi trực tiếp, parent/BOM khác, constraints, conflict resolution, dependency locks và resolved graph. Version quản lý và version thực tế phải được phân biệt rõ.

**Ghi nhớ:** **Dependency declaration tạo nhu cầu; dependencyManagement/BOM quản lý cách chọn phiên bản; dependency graph sau khi resolve là kết quả thực tế.** Ba lớp thông tin này giúp sửa đúng vấn đề khi thiếu thư viện, xung đột version hoặc nâng cấp Spring Boot.
