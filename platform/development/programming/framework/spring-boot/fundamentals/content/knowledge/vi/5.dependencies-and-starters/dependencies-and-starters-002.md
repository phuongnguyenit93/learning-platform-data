# Dependency trực tiếp, dependency bắc cầu và classpath cuối cùng

Trong một dự án Spring Boot, file build thường chỉ có vài dòng khai báo dependency, nhưng lúc biên dịch hoặc chạy, ứng dụng có thể sử dụng hàng chục hay hàng trăm thư viện. Điều đó xảy ra vì một thư viện có thể cần những thư viện khác, các thư viện đó lại có dependency riêng, và công cụ build phải **giải quyết toàn bộ đồ thị phụ thuộc** trước khi tạo classpath cho từng tác vụ.

Để hiểu đúng một dự án Spring Boot, cần phân biệt ba tầng:

1. **Dependency trực tiếp (direct dependency)**: thư viện mà dự án khai báo là muốn sử dụng.
2. **Dependency bắc cầu (transitive dependency)**: thư viện được đưa vào vì một dependency khác cần đến nó.
3. **Classpath cuối cùng (resolved classpath)**: tập các đường dẫn JAR, thư mục class và tài nguyên mà một tác vụ biên dịch hoặc một môi trường chạy thực sự nhìn thấy sau khi dependency được giải quyết.

Ba tầng này liên quan nhưng **không đồng nhất**. Thấy một dependency trong file build chưa khẳng định nó sẽ xuất hiện trong mọi classpath. Ngược lại, một JAR có thể nằm trong runtime classpath mặc dù bạn chưa từng khai báo trực tiếp tên nó.

## 1. Bắt đầu từ ví dụ Spring Boot

Giả sử dự án dùng Gradle và đã cấu hình các plugin Java, Spring Boot cùng cơ chế quản lý phiên bản dependency phù hợp. Khối khai báo sau minh họa một ứng dụng REST dùng validation, PostgreSQL và bộ công cụ kiểm thử:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Bốn dòng trên khai báo **bốn dependency trực tiếp** ở những configuration khác nhau. Nhưng khi Gradle giải quyết chúng, cây phụ thuộc sẽ mở rộng.

Ví dụ, với một dòng sản phẩm Spring Boot 3.x dùng Spring MVC, starter web thường đưa theo:

- **spring-web** và **spring-webmvc** để cung cấp các thành phần web của Spring Framework.
- Các thành phần Spring Boot nền tảng.
- Bộ thư viện hỗ trợ JSON, thường qua Jackson.
- Một Servlet container nhúng mặc định, thường là Tomcat.
- Các dependency khác của những thư viện trên.

Danh sách chính xác phụ thuộc **phiên bản Spring Boot, starter, metadata và cấu hình build**. Đây là ví dụ nguyên lý, không phải cam kết rằng mọi phiên bản Spring Boot sẽ có cấu trúc JAR giống nhau.

Một hình dung đơn giản:

~~~text
Ứng dụng Spring Boot
├── [TRỰC TIẾP] spring-boot-starter-web
│   ├── [BẮC CẦU] thành phần Spring Web MVC
│   ├── [BẮC CẦU] thành phần JSON
│   ├── [BẮC CẦU] embedded Servlet container
│   └── [BẮC CẦU] các thư viện hỗ trợ khác
├── [TRỰC TIẾP] spring-boot-starter-validation
│   └── [BẮC CẦU] thư viện validation tương thích
├── [TRỰC TIẾP] PostgreSQL JDBC driver (runtimeOnly)
└── [TRỰC TIẾP] spring-boot-starter-test (testImplementation)
    └── [BẮC CẦU] các thư viện phục vụ kiểm thử
~~~

Trong đồ thị thật, các nhánh có thể gặp lại **cùng một module**. Vì vậy đồ thị thường là một DAG sau khi giải quyết, chứ không phải lúc nào cũng là một cây hoàn toàn không có nút chung.

## 2. Dependency trực tiếp là gì?

Dependency trực tiếp là yêu cầu do **chính dự án khai báo** với công cụ build.

Ví dụ:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Ở đây, dự án khai báo starter web làm dependency trực tiếp. Trong hệ sinh thái JVM, một external module thường được nhận diện bằng tọa độ **group:artifact:version**:

~~~text
org.example:example-library:1.4.2
│           │               │
group       artifact        version
~~~

Ngoài external module, Gradle cũng hỗ trợ dependency đến một project khác trong cùng multi-project build:

~~~groovy
dependencies {
    implementation project(':shared-domain')
}
~~~

Khi đó dependency trực tiếp là **project dependency**. Tùy cấu hình, Gradle sử dụng output và các dependency phù hợp của project **shared-domain** để lập classpath cho project tiêu thụ.

### 2.1. Khai báo trực tiếp không có nghĩa tự viết toàn bộ danh sách JAR

Nếu dự án khai báo một thư viện HTTP client, thư viện này có thể cần một thư viện mã hóa, logging API hoặc parser dữ liệu. Khi metadata của dependency mô tả những dependency cần truyền tiếp và các quy tắc resolution cho phép, Gradle sẽ tìm thêm các module đó.

Bạn không cần sao chép thủ công mọi dependency của một starter vào file build. Việc dùng **starter** là một cách chọn một nhóm khả năng đã được thiết kế để làm việc cùng nhau.

### 2.2. Dependency trực tiếp thể hiện ý định sử dụng

Hai khai báo sau thể hiện hai ý định khác nhau:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    runtimeOnly 'org.postgresql:postgresql'
}
~~~

- **implementation**: code ứng dụng được biên dịch dựa trên dependency và các phụ thuộc cần thiết theo cơ chế configuration. Dependency này cũng tham gia runtime classpath thông thường.
- **runtimeOnly**: thư viện cần khi chạy nhưng không cần đưa vào compile classpath của mã chính; thường phù hợp với driver hoặc provider được dùng qua API/đăng ký lúc runtime.

Với ví dụ PostgreSQL, code ứng dụng có thể thao tác thông qua **DataSource**, JDBC hoặc abstraction của Spring Data mà không tham chiếu trực tiếp lớp implementation của driver trong source. Nhưng nếu code gọi trực tiếp một lớp thuộc PostgreSQL driver thì **runtimeOnly** có thể không đủ để biên dịch.

## 3. Dependency bắc cầu là gì?

**Dependency bắc cầu** là dependency được kéo vào qua một hoặc nhiều cạnh của đồ thị phụ thuộc.

Giả sử:

~~~text
Ứng dụng A
  └── B
       └── C
            └── D
~~~

Nếu A khai báo B trực tiếp, còn B khai báo C và C khai báo D dưới các quan hệ được phép truyền tiếp, thì:

- B là dependency trực tiếp của A.
- C và D là dependency bắc cầu đối với A.

Với A, C vẫn là dependency bắc cầu dù nó là dependency trực tiếp của B. Hai khái niệm **trực tiếp** và **bắc cầu** luôn được xét **tương đối với một project tiêu thụ**.

### 3.1. Thư viện khai báo dependency của nó ở đâu?

Với external module, thông tin thường đến từ:

- **Maven POM**: mô tả dependency, scope và metadata liên quan.
- **Gradle Module Metadata**: có thể mô tả các biến thể, thuộc tính, capability và dependency chi tiết hơn.
- Metadata khác do repository/artifact hoặc quy tắc build cung cấp.

Gradle đọc metadata từ repository đã cấu hình, dựng đồ thị dependency theo configuration đang giải quyết, chọn module/biến thể thích hợp và tải artifact được chọn nếu cần.

**Không phải mọi dependency được khai báo trong một POM đều sẽ xuất hiện ở mọi classpath của project tiêu thụ.** Scope, optional, exclusion, variant và các quy tắc Gradle có thể thay đổi cạnh nào được truyền tiếp.

### 3.2. Một module có thể được kéo vào qua nhiều nhánh

~~~text
Ứng dụng
├── Library A
│   └── Library C
└── Library B
    └── Library C
~~~

Điều này không có nghĩa nhất thiết có hai bản C độc lập trên cùng resolved classpath. Gradle thường giải quyết các yêu cầu cùng module thành một **lựa chọn phiên bản và variant phù hợp** cho configuration đang xét, dựa trên quy tắc conflict resolution.

Hơn nữa, hai classpath khác nhau của cùng project có thể chọn hai tập artifact khác nhau. Chẳng hạn compile classpath và test runtime classpath có thêm dependency riêng, nên không nên suy từ một đồ thị duy nhất ra toàn bộ môi trường chạy.

### 3.3. Dependency bắc cầu không đồng nghĩa một API bạn được phép dựa vào lâu dài

Giả sử code ứng dụng import trực tiếp một lớp của Library C, nhưng chỉ khai báo Library A, và C tình cờ được kéo vào qua A. Hôm nay code có thể biên dịch; ngày mai A đổi implementation, không còn phụ thuộc C và build của ứng dụng bắt đầu lỗi.

**Nguyên tắc thiết kế:** khi code ứng dụng chủ động sử dụng API của C, hãy cân nhắc khai báo **C là dependency trực tiếp** với version management phù hợp. Điều đó biểu thị hợp đồng sử dụng thật sự và giảm phụ thuộc vào cấu trúc nội bộ của A.

Trong Spring Boot, không nhất thiết phải khai báo mọi JAR của starter; nhưng nếu source cố ý dùng một API không thuộc hợp đồng sử dụng của starter hoặc thư viện mà dự án phụ thuộc trực tiếp, khai báo rõ ý định sẽ giúp việc nâng cấp dễ kiểm soát hơn.

## 4. Từ khai báo đến resolved classpath: Gradle làm gì?

Một cách nhìn theo quá trình:

~~~text
build.gradle
   │
   ├─ Các dependency trực tiếp
   └─ Các configuration và quy tắc build
                   │
                   ▼
       Dependency resolution
       ├─ Đọc metadata của module
       ├─ Mở rộng dependency bắc cầu
       ├─ Xem constraints / BOM / platform
       ├─ Chọn version và variant phù hợp
       ├─ Áp dụng exclusion / substitution / rule
       └─ Chọn artifact cho configuration yêu cầu
                   │
                   ▼
       Resolved dependencies / artifacts
                   │
                   ├─ compileClasspath
                   ├─ runtimeClasspath
                   ├─ testCompileClasspath
                   └─ testRuntimeClasspath
                   │
                   ▼
       Compiler, test runner, Java process,
       Spring Boot packaging / execution
~~~

Trình tự trên là mô hình khái niệm, không phải trình tự nội bộ cố định của mọi API Gradle. Điểm quan trọng là **dependency declaration là đầu vào**, còn **resolved configuration là kết quả** của nhiều quy tắc.

Khi một configuration được resolve, Gradle thường sử dụng:

1. Các dependency được khai báo trực tiếp hoặc kế thừa.
2. Metadata và dependency bắc cầu được cho phép.
3. Các yêu cầu và ràng buộc về phiên bản.
4. Các quy tắc chọn variant/capability/artifact.
5. Repository nơi artifact có thể được tìm thấy.

Nếu có version conflict, Gradle phải chọn ra kết quả theo chính sách resolution đang áp dụng. Nếu module hoặc artifact không có trong repository, quá trình resolve có thể thất bại trước khi ứng dụng chạy.

## 5. Classpath là gì?

**Classpath** trong Java là tập các vị trí mà compiler hoặc runtime sử dụng để tìm lớp và tài nguyên. Các vị trí có thể là:

- Thư mục chứa file **.class**.
- Tệp **.jar** có class và resource.
- Các đường dẫn khác được đưa vào qua cơ chế classpath thích hợp.

Ví dụ khái niệm:

~~~text
Runtime classpath
├── build/classes/java/main/
├── build/resources/main/
├── spring-webmvc-<version>.jar
├── spring-context-<version>.jar
├── jackson-databind-<version>.jar
├── postgresql-<version>.jar
└── ...
~~~

Trong ứng dụng đóng gói bằng Spring Boot, đường dẫn vật lý bên trong executable JAR có thể khác: plugin Spring Boot đóng gói các dependency runtime vào các vùng riêng trong archive và sử dụng launcher/class loader để chạy. Vì vậy danh sách bên trên chỉ minh họa **nội dung logic của runtime classpath**, không phải cấu trúc bắt buộc của một executable JAR.

### 5.1. Compile classpath và runtime classpath khác nhau

**Compile classpath** là nơi compiler tìm các lớp cần thiết để biên dịch source code. **Runtime classpath** là nơi ứng dụng hoặc một tác vụ tìm các lớp khi chạy.

Một dependency hiện diện ở compile classpath không nhất thiết hiện diện ở runtime classpath. Chẳng hạn **compileOnly** cung cấp API lúc biên dịch nhưng không được tự động thêm vào runtime classpath thông thường.

Ngược lại, một dependency ở **runtimeOnly** không cần xuất hiện ở compile classpath nhưng vẫn cần khi chạy.

Ví dụ:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'

    compileOnly 'org.projectlombok:lombok'
    annotationProcessor 'org.projectlombok:lombok'

    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Lombok là ví dụ quen thuộc của thư viện dùng ở giai đoạn biên dịch và annotation processing. Việc khai báo **compileOnly** và **annotationProcessor** là hai vai trò khác nhau. Bản thân annotation processor dùng một đường xử lý riêng; chỉ thêm một processor vào classpath thông thường không bảo đảm nó được Gradle dùng làm annotation processor.

### 5.2. Classpath của test khác classpath của ứng dụng chính

Với plugin Java trong Gradle, các configuration quen thuộc gồm:

| Configuration | Ý nghĩa điển hình |
|---|---|
| **implementation** | Dependency của mã chính, phục vụ compile và runtime theo cấu hình Java plugin. |
| **compileOnly** | Cần cho compile mã chính; không tự đưa vào runtime classpath chính. |
| **runtimeOnly** | Cần khi chạy mã chính; không tự đưa vào compile classpath chính. |
| **annotationProcessor** | Dependency phục vụ annotation processor của mã chính. |
| **testImplementation** | Dependency dùng cho source test. |
| **testCompileOnly** | Dependency chỉ cần cho compile test. |
| **testRuntimeOnly** | Dependency chỉ cần khi chạy test. |

Ví dụ **JUnit** và các tiện ích trong starter test cần cho kiểm thử nhưng không mặc nhiên là dependency runtime của ứng dụng production. Chạy test có thể thành công vì một thư viện hiện diện ở **testRuntimeClasspath**, trong khi chạy ứng dụng thật lại không có thư viện đó.

Đó là lý do khi điều tra lỗi cần hỏi: **classpath của tác vụ nào?** Không thể lấy kết quả test classpath rồi kết luận runtime classpath của application tương đương.

### 5.3. API và implementation trong thư viện dùng lại

Khi dùng plugin **java-library** trong Gradle, một thư viện có thể khai báo:

~~~groovy
plugins {
    id 'java-library'
}

dependencies {
    api 'org.example:public-contract:1.2.0'
    implementation 'org.example:internal-helper:2.0.0'
}
~~~

- **api**: dependency là một phần hợp đồng API được xuất cho project tiêu thụ và thường cần trên compile classpath của consumer.
- **implementation**: dependency dùng nội bộ thư viện; Gradle có thể giữ nó khỏi compile classpath của consumer trong mô hình variant phù hợp, trong khi vẫn cấp nó cho runtime khi cần.

Ví dụ, nếu chữ ký public của thư viện trả về một lớp từ **public-contract**, consumer phải nhìn thấy kiểu đó lúc biên dịch. Nếu **internal-helper** chỉ được dùng trong thân phương thức, không cần đưa nó vào compile classpath của consumer.

Đây là một ví dụ vì sao dependency **bắc cầu** không đơn thuần là “cứ được khai báo ở đâu đó thì mọi nơi đều nhìn thấy”.

### 5.4. Compile classpath không phải mọi thứ có thể được nạp lúc runtime

Trong JVM còn có class loader, module path, classpath theo môi trường, thư viện tự nạp qua reflection, ServiceLoader hoặc cơ chế plugin. Có những lớp không xuất hiện trực tiếp trong import Java nhưng được cần đến khi runtime.

Do đó, compile thành công không chứng minh runtime đủ mọi dependency. Và một artifact nằm trong runtime classpath vẫn có thể gặp vấn đề khi nạp nếu thiếu dependency khác, có bản binary không tương thích hoặc cấu hình class loader không phù hợp.

## 6. Spring Boot starter nằm ở đâu trong bức tranh này?

**Starter** là dependency giúp chọn một nhóm thư viện theo một nhu cầu phổ biến. Ví dụ:

- **spring-boot-starter-web**: dùng để xây dựng ứng dụng web Spring MVC trong các dòng phiên bản Boot có starter này.
- **spring-boot-starter-validation**: hỗ trợ tích hợp validation.
- **spring-boot-starter-data-jpa**: đưa các thành phần thường cần cho JPA/Spring Data JPA.
- **spring-boot-starter-test**: tập hợp công cụ kiểm thử phổ biến.
- **spring-boot-starter-actuator**: thêm khả năng quan sát và endpoint quản lý tùy cấu hình.

Starter chủ yếu xác định **tập dependency**. Nó không trực tiếp định nghĩa nghiệp vụ của bạn. Việc Spring Boot tự thiết lập các bean phù hợp là cơ chế **auto-configuration**, được kích hoạt theo nhiều điều kiện, trong đó có classpath.

Ví dụ:

~~~text
Bạn khai báo starter web
          │
          ▼
Gradle resolve dependency bắc cầu
          │
          ▼
Classpath có Spring MVC và web runtime phù hợp
          │
          ▼
Spring Boot xem xét auto-configuration
          │
          ▼
Nếu điều kiện thỏa mãn, Boot cấu hình
DispatcherServlet và hạ tầng web
          │
          ▼
Controller của bạn có môi trường để xử lý HTTP
~~~

Hai điểm cần tách bạch:

1. **Có JAR trên classpath** là điều kiện về sự hiện diện của thư viện; không bảo đảm mọi feature liên quan đã bật.
2. **Auto-configuration có điều kiện**: tùy classpath, bean đang tồn tại, property và loại ứng dụng, Boot có thể bật, bỏ qua hoặc điều chỉnh một cấu hình.

Ví dụ, thêm JDBC driver không tự cung cấp đúng URL database và credentials. Tương tự, thêm validation starter không tự viết rule nghiệp vụ như số lượng đơn hàng phải lớn hơn 0.

### 6.1. Starter thường không phải mã thực thi chính

Một starter có thể chứa chủ yếu metadata/dependency declarations để kéo một nhóm thư viện tương thích. Phần code thực sự xử lý HTTP nằm ở Spring MVC, Servlet container, Jackson và các thành phần khác. Đọc tên starter mà không xem đồ thị bắc cầu có thể làm bạn hiểu sai thư viện nào đang thực hiện một hành vi.

### 6.2. Dùng nhiều starter có gây trùng thư viện?

Có thể nhiều starter yêu cầu cùng một module Spring core hoặc logging. Gradle sẽ giải quyết các cạnh cùng module cho mỗi configuration; thông thường các yêu cầu đó hội tụ về một module được chọn. Không cần tự loại mọi đường bắc cầu trùng tên.

Tuy vậy, nếu hai starter mang vào **các implementation cạnh tranh** hoặc các module có capability xung đột, bạn vẫn cần hiểu ý định sử dụng và cấu hình build; không nên giả định mọi tổ hợp starter luôn hợp lý.

## 7. Version management: ai quyết định phiên bản cuối cùng?

Tưởng tượng:

~~~text
Ứng dụng
├── Library A → Library C phiên bản 1.2
└── Library B → Library C phiên bản 1.5
~~~

Đồ thị có hai yêu cầu khác nhau dành cho cùng một module C. Công cụ build cần quyết định **version nào được chọn** cho configuration đang resolve.

Với Gradle, chính sách conflict resolution mặc định cho nhiều trường hợp thông thường là **chọn phiên bản cao hơn trong các phiên bản được yêu cầu**, nhưng kết quả còn chịu ảnh hưởng của constraints, rich versions, platform, capability, metadata, forced version, dependency substitution và các quy tắc khác. **Không áp dụng máy móc** giả định “Gradle luôn chọn bản mới nhất trên repository”: Gradle giải quyết theo *những yêu cầu và quy tắc được cung cấp*, không tự nâng lên bản mới nhất bất kỳ.

Maven có cơ chế dependency mediation khác; trong các xung đột thông thường có thể áp dụng nguyên tắc **nearest definition**, cùng các ảnh hưởng từ dependencyManagement. Vì vậy không nên dùng một quy tắc của Maven để giải thích mù quáng kết quả Gradle.

### 7.1. Spring Boot BOM và dependency management

Spring Boot phát hành một **BOM (Bill of Materials)** chứa danh sách phiên bản được quản lý cho nhiều thư viện liên quan. BOM giúp các thành phần Spring và thư viện phổ biến dùng các phiên bản được lựa chọn để hoạt động cùng nhau.

Ví dụ một dự án có plugin Spring Boot và **io.spring.dependency-management** được cấu hình phù hợp có thể khai báo:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    runtimeOnly 'org.postgresql:postgresql'
}
~~~

Các dependency không ghi số phiên bản chỉ có thể resolve thành công khi **build đã cung cấp thông tin quản lý phiên bản phù hợp**. Trong thiết lập kết hợp plugin Boot với dependency-management plugin, BOM tương ứng thường được import tự động. Còn nếu dùng Gradle native platform, phải khai báo platform/BOM đúng cách theo cấu hình của dự án.

**Chỉ áp dụng plugin Spring Boot không phải một lời bảo đảm chung rằng mọi dependency không có version sẽ tự được quản lý trong mọi kiểu build.** Cơ chế dependency management cụ thể của dự án mới quyết định điều đó.

### 7.2. BOM không tự kéo tất cả thư viện vào classpath

Một BOM chủ yếu định nghĩa **version constraints hoặc version recommendations** cho các tọa độ module. Nó không có nghĩa mọi module được liệt kê trong BOM đều được tải về và đóng gói vào ứng dụng.

~~~text
BOM quản lý phiên bản của A, B, C, D
                   │
      Dự án khai báo dependency B
                   │
                   ▼
       Chọn phiên bản của B
       và các dependency được resolve
                   │
                   ▼
       A, C, D chỉ xuất hiện nếu có
       dependency path phù hợp
~~~

Đó là khác biệt giữa **quản lý phiên bản** và **yêu cầu một thư viện xuất hiện**.

### 7.3. Ghi đè phiên bản có thể tạo xung đột

Bạn có thể khai báo hoặc ràng buộc một version khác với version Boot quản lý. Nhưng một thư viện mới hơn hoặc cũ hơn có thể yêu cầu API/binary không tương thích với những thư viện còn lại.

Ví dụ:

~~~text
Spring Boot BOM: chọn thư viện X phiên bản tương thích
Ứng dụng: cố ép X sang phiên bản khác
                           ↓
                 Dependency resolution
                           ↓
          Có thể chọn được phiên bản nhưng
          vẫn gặp lỗi binary khi chạy
~~~

Resolution thành công chỉ chứng minh công cụ build **tìm và chọn được artifact**. Nó không tự chứng minh mọi lớp và API được sử dụng đều tương thích ở runtime.

### 7.4. Version conflict và duplicate class là hai vấn đề khác nhau

- **Version conflict**: nhiều cạnh trong đồ thị yêu cầu **cùng một module** ở các version khác nhau.
- **Duplicate class**: có **hai artifact khác nhau** cùng chứa class có tên package và class giống nhau, hoặc những bản đóng gói/shading gây trùng.

Gradle giải quyết version của cùng một module không tự bảo đảm không còn duplicate class giữa các module khác tên. Duplicate class có thể dẫn đến hành vi phụ thuộc class loading order và các lỗi khó phân tích.

## 8. Configuration quyết định dependency được đưa vào đâu

Một dependency không chỉ có tên và version; nó còn được đặt trong một **configuration** với quy tắc và quan hệ kế thừa riêng.

Ví dụ:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    runtimeOnly 'org.postgresql:postgresql'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Với ứng dụng Java thông thường:

~~~text
compileClasspath
  ├─ output / classpath cần cho compile
  └─ implementation dependencies

runtimeClasspath
  ├─ output chính của ứng dụng
  ├─ implementation dependencies
  └─ runtimeOnly dependencies

testCompileClasspath
  ├─ output + dependency cần cho compile test
  └─ testImplementation và các dependency liên quan

testRuntimeClasspath
  ├─ output ứng dụng + output test
  ├─ runtime dependencies của ứng dụng
  └─ test runtime dependencies
~~~

Đây là sơ đồ trực quan, không thể hiện mọi chi tiết extendsFrom/variant của plugin. Đặc biệt, classpath test còn phụ thuộc plugin và source set đang dùng. Một source set **integrationTest** tự tạo có thể có configuration riêng; không nên mặc định nó giống **test**.

### 8.1. Vì sao test chạy được nhưng bootJar chạy lỗi?

Giả sử code gọi một thư viện ở runtime, nhưng thư viện đó vô tình chỉ được thêm vào **testImplementation**. Test có thể thấy thư viện, còn runtime của ứng dụng chính thì không. Nếu mã chính import lớp đó, compile chính thường sẽ phát hiện thiếu class; nhưng với reflection, ServiceLoader hoặc nạp class theo tên động, sai configuration có thể chỉ bộc lộ khi chạy.

Ngược lại, nếu thư viện được khai báo **compileOnly** mà runtime thực sự cần, code có thể biên dịch nhưng thất bại khi chạy. Lỗi có thể là **NoClassDefFoundError** hoặc lỗi nạp lớp tương tự.

### 8.2. Annotation processor không phải dependency runtime

Annotation processor chạy trong quá trình compile để tạo mã hoặc kiểm tra annotation. Chẳng hạn Lombok được khai báo trong **annotationProcessor** để tham gia biên dịch. Không có nghĩa runtime cần nạp chính Lombok để thực thi bytecode được biên dịch.

Trong các trường hợp khác, processor tạo ra source cần được compile và đóng gói, còn thư viện runtime cung cấp annotation/implementation lại là dependency riêng. Vì vậy cần đọc contract của công cụ thay vì tự động chuyển mọi annotation processor sang **implementation**.

## 9. Classpath cuối cùng thay đổi theo cách chạy ứng dụng

Đừng xem **classpath cuối cùng** là một con số hoặc một danh sách tồn tại duy nhất cho toàn bộ dự án. Có nhiều môi trường:

| Ngữ cảnh | Classpath/artifact cần quan tâm |
|---|---|
| Biên dịch source chính | **compileClasspath** và các cấu hình biên dịch liên quan. |
| Chạy test unit | **testRuntimeClasspath**. |
| Chạy app từ IDE | Classpath IDE dựng từ Gradle model và cấu hình run. |
| Chạy Gradle bootRun | Runtime classpath của tác vụ Boot với các thiết lập liên quan. |
| Đóng gói executable bootJar | Artifact runtime mà Boot plugin lựa chọn để đóng gói, cùng output ứng dụng. |
| Chạy executable JAR | Các lớp/tài nguyên được launcher và class loader thực sự nạp từ archive. |
| Deploy WAR vào container ngoài | Class loading còn phụ thuộc container và dependency được đánh dấu theo cơ chế phù hợp. |

Vì cách chạy có thể khác nhau, đôi khi **chạy trong IDE thành công nhưng chạy JAR thất bại**. Lúc đó không đủ để nhìn dependency declaration; phải đối chiếu artifact đã đóng gói và runtime thực tế.

### 9.1. Executable JAR của Spring Boot

Với một executable JAR Spring Boot điển hình, cấu trúc logic có thể là:

~~~text
application.jar
├── META-INF/
├── BOOT-INF/
│   ├── classes/
│   │   ├── class của ứng dụng
│   │   └── resources của ứng dụng
│   └── lib/
│       ├── thư viện A.jar
│       ├── thư viện B.jar
│       ├── thư viện C.jar
│       └── ...
└── các thành phần launcher
~~~

Boot launcher hỗ trợ nạp class từ các nested JAR trong archive. Tập artifact này phản ánh quy tắc packaging của tác vụ và các runtime dependencies phù hợp, không phải việc copy toàn bộ thư mục cache của Gradle hoặc toàn bộ test dependency vào JAR.

Với phiên bản, layout hoặc kiểu đóng gói khác, chi tiết thực tế có thể thay đổi. Khái niệm vẫn là **đóng gói đủ phần cần thiết cho cách vận hành đã chọn**.

### 9.2. JAR thường và JAR thực thi không giống nhau

Một JAR tạo từ tác vụ **jar** thông thường có thể chỉ chứa code/resource của project, trong khi **bootJar** tạo archive thực thi có cả dependency được bố trí theo cấu trúc Boot.

Do đó, lỗi kiểu “chạy java -jar và không tìm thấy thư viện” còn cần kiểm tra **bạn đang chạy artifact nào**, không chỉ kiểm tra build.gradle.

## 10. Tình huống thực tế: thấy một lớp nhưng không biết nó đến từ đâu

Giả sử bạn không khai báo trực tiếp một thư viện JSON nhưng project vẫn import được lớp từ thư viện đó. Có thể nó được kéo vào từ starter web.

Đừng đoán dựa trên việc “Spring Boot chắc có sẵn”. Hãy tìm **dependency path**:

~~~text
Ứng dụng
  └─ spring-boot-starter-web
       └─ thành phần JSON của starter
            └─ Jackson module
~~~

Đường đi thực tế phải được xác minh từ resolved dependency graph. Nếu thư viện JSON đang được dùng trực tiếp trong public API hoặc source của bạn, nên cân nhắc việc khai báo trực tiếp module phù hợp. Nếu nó chỉ là implementation detail bên trong auto-configuration, bạn thường không cần cố khai báo mọi module của nó.

### 10.1. Các lệnh Gradle hữu ích để quan sát

Trong dự án Gradle, tác vụ **dependencies** cho biết đồ thị theo configuration. Trên máy có shell Unix:

~~~bash
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration testRuntimeClasspath
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat :app:dependencies --configuration runtimeClasspath
~~~

**:app** là ví dụ tên Gradle project. Với dự án single-project, có thể bỏ tiền tố project path:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Lệnh này đọc kết quả resolution của configuration được chọn; nó không có nghĩa tự động chạy ứng dụng Spring Boot.

Khi muốn biết **vì sao một module xuất hiện và phiên bản nào đã được chọn**, dùng **dependencyInsight**:

~~~bash
./gradlew :app:dependencyInsight \
  --configuration runtimeClasspath \
  --dependency jackson-databind
~~~

Trong PowerShell, có thể viết trên một dòng:

~~~powershell
.\gradlew.bat :app:dependencyInsight --configuration runtimeClasspath --dependency jackson-databind
~~~

Output thường cho biết version được lựa chọn và các đường dependency có liên quan; chi tiết thay đổi theo Gradle version, dependency metadata và configuration. Nếu thấy một version được thay bằng version khác, cần kiểm tra nguyên nhân selection/constraint thay vì vội ép version.

**Không chạy các lệnh chẩn đoán một cách mù quáng trong mọi project:** một số build có tác vụ cấu hình/generator với side effect. Khi cần điều tra thực tế, đọc cấu trúc và hướng dẫn dự án trước rồi chọn lệnh phù hợp.

### 10.2. Với Maven

Ý tưởng direct/transitive/runtime tương tự nhưng cấu hình và quy tắc lựa chọn version khác. Lệnh thường dùng:

~~~bash
mvn dependency:tree
~~~

Maven có các scope như **compile**, **runtime**, **test**, **provided** và **system** với ngữ nghĩa khác với Gradle configurations. Không nên dịch máy móc từng scope Maven thành tên configuration Gradle trùng nghĩa hoàn toàn.

### 10.3. Đọc output dependency tree

Một cây minh họa có thể cho thấy:

~~~text
+--- com.example:library-a:1.0
|    \--- com.example:shared-lib:1.2 -> 1.5
\--- com.example:library-b:2.0
     \--- com.example:shared-lib:1.5
~~~

Ý nghĩa của **1.2 -> 1.5** trong kiểu hiển thị này là yêu cầu ban đầu cho module ở một cạnh đã được giải quyết thành **1.5**. Không thể kết luận “có cả hai JAR 1.2 và 1.5” chỉ vì trên output xuất hiện cả hai số.

Các ký hiệu như **(*)** hoặc marker khác trong cây Gradle có thể biểu diễn nhánh lặp và quy ước hiển thị của task; hãy đọc chúng theo phiên bản Gradle đang sử dụng.

## 11. Exclusion: cắt một cạnh bắc cầu có chủ đích

Khi một dependency kéo theo một thư viện không mong muốn, Gradle có cơ chế **exclude**. Ví dụ minh họa:

~~~groovy
dependencies {
    implementation('com.example:legacy-client:1.0') {
        exclude group: 'com.example', module: 'old-logging-bridge'
    }
}
~~~

Điều này yêu cầu loại dependency có group/module chỉ định **trên đường khai báo tương ứng**. Nhưng cần hiểu:

1. Module bị exclude có thể vẫn xuất hiện nếu **đường khác** trong đồ thị tiếp tục yêu cầu nó.
2. Exclude không tự thay thế code đang cần thư viện bị loại.
3. Loại một thư viện chỉ vì tên nó xuất hiện hai lần trong dependency tree có thể phá vỡ runtime.
4. Tùy trường hợp, giải pháp đúng có thể là thay dependency ban đầu, dùng variant khác, điều chỉnh version alignment hoặc sửa code.

Ví dụ, nếu thư viện A thực sự cần lớp từ thư viện C, loại C khỏi graph mà không cung cấp phương án thay thế sẽ dẫn tới lỗi nạp class.

### 11.1. Thay thế starter mặc định

Trong một ứng dụng Spring Boot có thể tồn tại nhu cầu dùng web server khác với server mặc định của starter. Giải pháp thường gồm **loại thành phần server mặc định được kéo vào** và **thêm starter/server thay thế phù hợp**. Tuy nhiên, phải kiểm tra chính xác phiên bản Boot và dependency graph hiện hành trước khi áp dụng; tên module và cấu trúc starter có thể thay đổi giữa các dòng Boot.

Điểm cốt lõi: **exclude phải phục vụ một lựa chọn kiến trúc cụ thể**, không phải một thói quen “dọn cho cây dependency ngắn hơn”.

## 12. Tại sao vẫn có thể lỗi dù dependency đã resolve?

Resolve thành công nghĩa là Gradle tìm được kết quả phù hợp với **quy tắc dependency resolution**. Nó không chứng minh code sử dụng chúng đúng cách hoặc chúng tương thích ở mọi đường chạy.

Các lỗi điển hình:

### 12.1. ClassNotFoundException

~~~text
java.lang.ClassNotFoundException: com.example.SomeClass
~~~

Thường xuất hiện khi một cơ chế nạp class theo tên không tìm thấy lớp bằng class loader được sử dụng. Cần kiểm tra runtime classpath, artifact đã đóng gói và class loader phù hợp.

### 12.2. NoClassDefFoundError

~~~text
java.lang.NoClassDefFoundError: com/example/SomeClass
~~~

Đây là một **Error** có thể xảy ra khi JVM không thể định nghĩa hoặc sử dụng một lớp được kỳ vọng có mặt lúc chạy, ví dụ lớp có lúc biên dịch nhưng runtime thiếu dependency. Nó cũng có thể liên quan thất bại khởi tạo lớp trước đó; không nên kết luận mọi NoClassDefFoundError đều chỉ là “quên thêm JAR”.

Một dấu hiệu đáng kiểm tra: module đó bị khai báo **compileOnly** hoặc chỉ có trong **testImplementation**, trong khi runtime cần nó.

### 12.3. NoSuchMethodError và NoSuchFieldError

~~~text
java.lang.NoSuchMethodError: ...
~~~

Loại lỗi này thường gợi ý một class ở runtime **không cung cấp thành viên** mà bytecode đã được biên dịch kỳ vọng. Một nguyên nhân phổ biến là **binary incompatibility** giữa các phiên bản thư viện. Hãy tìm version thật sự được resolve và artifact thật sự được nạp, thay vì chỉ xem version ghi trong một dòng khai báo.

### 12.4. Service/provider không hoạt động

Ứng dụng có thể biên dịch và chạy nhưng một chức năng không hoạt động do thiếu provider, implementation, metadata hoặc điều kiện auto-configuration. Ví dụ:

- Thiếu JDBC driver thích hợp ở runtime.
- Thiếu provider cần thiết cho một API tích hợp.
- Có dependency nhưng property cấu hình chưa được cung cấp.
- Bean được khai báo ngoài phạm vi component scan.

Lúc này việc thêm dependency không tự giải quyết mọi nguyên nhân. Cần xác định **classpath**, **cấu hình** và **thành phần Spring đang được khởi tạo**.

### 12.5. Trùng API hoặc implementation trên classpath

Hai thư viện có thể chứa class/package trùng nhau do repackaging hoặc vì một thư viện cũ đi kèm bản copy của API. Khi đó, dù mỗi module chỉ có một version được chọn, class loader có thể gặp tình huống khó dự đoán hoặc lỗi binary.

Cần xem artifact vật lý nào chứa lớp đó, nguồn dependency path nào đưa chúng vào, và liệu có yêu cầu sử dụng một giải pháp alignment/relocation thay vì exclude tùy tiện.

## 13. Auto-configuration phụ thuộc classpath nhưng không chỉ phụ thuộc classpath

Spring Boot dùng nhiều conditional configuration, ví dụ kiểm tra class có mặt bằng **@ConditionalOnClass**, bean hiện có qua **@ConditionalOnMissingBean**, property thông qua **@ConditionalOnProperty** và loại web application.

Một mô hình đơn giản:

~~~text
Đã resolve dependency phù hợp?
              │
              ▼
Classpath có các class cần thiết?
              │
              ▼
Điều kiện auto-configuration khác thỏa?
              │
       ┌──────┴───────┐
       │              │
      Có            Không
       │              │
       ▼              ▼
 Cấu hình có thể   Không áp dụng
 được áp dụng      cấu hình đó
~~~

Vì vậy:

- Có **spring-webmvc** trong classpath chưa chắc mọi controller đã được đăng ký.
- Có JDBC driver chưa chắc Boot cấu hình đúng DataSource.
- Có Actuator chưa chắc mọi management endpoint đều được expose.
- Có hai starter khác nhau có thể thay đổi cách Boot xác định loại ứng dụng hoặc cách auto-configuration được lựa chọn.

Khi một bean không xuất hiện như mong đợi, cần kiểm tra cả **resolved classpath** và **điều kiện thực tế**, không chỉ tên starter trong file build.

## 14. Ví dụ điều tra: một lỗi chỉ xảy ra sau khi đóng gói

Giả sử service dùng một provider lúc chạy qua reflection. Khi chạy test trong IDE thì chức năng hoạt động, nhưng executable JAR báo:

~~~text
java.lang.ClassNotFoundException: com.example.provider.JsonProvider
~~~

Hướng phân tích có thể là:

1. **Xác định ngữ cảnh lỗi**: Java process đang chạy artifact nào? Đó là JAR do **bootJar** hay một JAR thường?
2. **Kiểm tra cấu hình dependency**: thư viện provider được khai báo ở **testImplementation**, **compileOnly**, **runtimeOnly** hay **implementation**?
3. **Xem runtimeClasspath thực tế**: provider có được resolve cho source set chính không?
4. **Xem artifact đã đóng gói**: JAR provider có nằm trong vùng dependency runtime của executable JAR không?
5. **Kiểm tra lớp bên trong artifact**: tên class/package có đúng version, đã bị đổi tên/relocate hay chưa?
6. **Kiểm tra class loading**: ứng dụng dùng class loader nào, có cần metadata/service registration riêng không?

Nếu provider chỉ nằm trong **testImplementation**, test thấy nó là điều dễ hiểu; runtime application không có nó. Khi ứng dụng thực sự cần provider lúc chạy, cần khai báo vào configuration thích hợp, chẳng hạn **runtimeOnly** nếu source không tham chiếu trực tiếp API của provider.

Nếu class vẫn tồn tại trong runtime artifact mà lỗi chưa hết, tiếp tục điều tra class loader, binary compatibility và cơ chế nạp class. Đừng mặc định “thêm JAR” là giải pháp cho mọi ClassNotFoundException.

## 15. Ví dụ điều tra: hai thư viện yêu cầu version khác nhau

Một app dùng hai client:

~~~text
Ứng dụng
├── report-client:2.0
│   └── common-utils:1.6
└── billing-client:3.0
    └── common-utils:2.1
~~~

Bạn đọc file build và chỉ thấy **report-client** và **billing-client**. Khi chạy, một phương thức trong report-client báo **NoSuchMethodError**.

Đường điều tra hợp lý:

1. In **runtimeClasspath dependency tree**.
2. Dùng **dependencyInsight** đối với **common-utils**.
3. Xác nhận version cuối cùng của common-utils và vì sao nó được chọn.
4. Đối chiếu API mà report-client đã biên dịch kỳ vọng với API của common-utils thực sự được nạp.
5. Xem release note, compatibility matrix hoặc BOM/constraints của hai client.
6. Chọn bộ phiên bản tương thích, cập nhật một client, hoặc điều chỉnh dependency alignment có chủ đích.

Việc ép common-utils về **1.6** chỉ vì report-client yêu cầu nó có thể làm billing-client hỏng. Ngược lại, chọn **2.1** theo chính sách Gradle không tự bảo đảm report-client tương thích. **Dependency resolution** giải bài toán chọn artifact theo quy tắc; **tương thích API/binary** vẫn cần được xác nhận bằng hành vi thực tế.

## 16. Một số nhầm lẫn thường gặp

**“Khai báo bốn dependency thì chỉ có bốn JAR.”**  
Không. Các dependency trực tiếp có thể kéo theo nhiều module bắc cầu. JAR cuối cùng phụ thuộc configuration và resolution.

**“Starter đã khai báo thì mọi thư viện trong BOM cũng được tải.”**  
Không. Starter yêu cầu một tập dependency; BOM cung cấp thông tin version cho các module được dùng. Chúng làm hai việc khác nhau.

**“Hai đường phụ thuộc đến cùng module có nghĩa classpath chứa hai version.”**  
Không nhất thiết. Gradle thường giải quyết một module thành một version được chọn cho configuration, nhưng duplicate classes giữa những module khác tên vẫn là vấn đề riêng.

**“Có module trong dependency tree thì code ở mọi source set đều import được.”**  
Không. Phải xem **configuration** và classpath đang xét. **testImplementation**, **runtimeOnly** và **compileOnly** có mục đích khác nhau.

**“Build thành công nghĩa là chạy được.”**  
Không. Compile có thể thành công nhưng runtime thiếu class/provider, gặp binary incompatibility hoặc cấu hình ứng dụng sai.

**“Spring Boot đã quản lý version thì ghi đè bất kỳ version cũng an toàn.”**  
Không. Bộ phiên bản được quản lý hướng tới tương thích; ghi đè cần hiểu tác động lên cả đồ thị.

**“Exclude được JAR không mong muốn thì chắc chắn hết xung đột.”**  
Không. Một cạnh khác vẫn có thể kéo JAR vào, hoặc loại JAR làm hỏng thư viện đang cần nó.

**“Có JAR trên classpath thì Spring Boot tự tạo mọi bean liên quan.”**  
Không. Auto-configuration còn phụ thuộc các điều kiện như bean hiện tại, property, environment và loại ứng dụng.

**“Classpath trên máy lập trình luôn giống trong executable JAR.”**  
Không. IDE, test runner, bootRun và artifact được đóng gói có thể sử dụng classpath hoặc cơ chế class loading khác nhau.

## 17. Cách suy nghĩ khi thêm hoặc sửa một dependency

Trước khi sửa khối dependencies, hãy trả lời bốn câu hỏi:

1. **Mình sử dụng API nào?** Nếu code source trực tiếp dùng một API của thư viện, đó thường là ý định dependency rõ ràng cần thể hiện.
2. **Thư viện cần ở giai đoạn nào?** Compile, runtime, test hay annotation processing?
3. **Ai quản lý version?** Spring Boot BOM/platform, dependency constraint riêng của dự án hay một version được chỉ định tường minh?
4. **Artifact thực tế đến từ đâu?** Một khai báo trực tiếp, một starter, project dependency hay đường bắc cầu nào?

Từ bốn câu hỏi này, xác định configuration đúng, kiểm tra resolved graph và chỉ thêm exclude/version override khi có lý do cụ thể. Khi gặp lỗi ở runtime, tiếp tục hỏi **artifact được đóng gói và class loader thực sự có gì**.

## Ghi nhớ cốt lõi

**Dependency trực tiếp** thể hiện điều dự án khai báo muốn dùng. **Dependency bắc cầu** mở rộng yêu cầu đó theo metadata và quan hệ giữa các thư viện. **Classpath cuối cùng** là kết quả resolution cho **một configuration và một ngữ cảnh thực thi cụ thể**.

Trong Spring Boot, **starter** giúp khai báo nhóm dependency, **BOM/dependency management** giúp lựa chọn phiên bản phù hợp, còn **auto-configuration** sử dụng những điều kiện như classpath và cấu hình hiện tại để thiết lập thành phần ứng dụng. Nắm được ranh giới này sẽ giúp bạn hiểu vì sao một lớp xuất hiện dù không được khai báo trực tiếp, vì sao một thư viện thiếu khi chạy dù test thành công, và phải nhìn vào đâu khi xảy ra lỗi phụ thuộc phiên bản.
