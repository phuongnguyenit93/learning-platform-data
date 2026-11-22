# optional trong Maven và compileOnly, api, implementation trong Gradle khi xây custom starter

## 1. Vì sao dependency scope quan trọng với custom starter?

Một Spring Boot starter thường gom auto-configuration và những thư viện cần thiết để người dùng chỉ cần thêm một dependency. Nhưng không phải mọi dependency mà module starter dùng đều phải xuất hiện trong mọi ứng dụng tiêu thụ nó.

Ví dụ, thư viện Acme có một client và một module tích hợp Spring Boot. Phần auto-configuration có thể biên dịch với API của Acme, nhưng chỉ cần kích hoạt khi ứng dụng thực sự đưa Acme Client lên classpath. Nếu starter luôn kéo mọi integration vào ứng dụng, người dùng phải nhận thêm thư viện dù không dùng tính năng đó, classpath lớn hơn và có thể phát sinh xung đột version.

Maven và Gradle giải quyết việc này bằng những cơ chế khác nhau:

- **Maven `optional`**: dependency vẫn được dùng trong chính module hiện tại theo scope đã khai báo, nhưng không tự truyền tiếp sang project phụ thuộc module đó.
- **Gradle `compileOnly`**: dependency chỉ có trên compile classpath của module khai báo; không có trên runtime classpath của module và không được truyền cho consumer.
- **Gradle `api`**: dependency thuộc public API của thư viện, được truyền cho consumer cả compile lẫn runtime.
- **Gradle `implementation`**: dependency được dùng để compile và chạy module hiện tại, được truyền cho consumer ở runtime nhưng không xuất hiện trên compile classpath của consumer.

Đây không phải các tên khác nhau của cùng một khái niệm. `optional` là cờ điều khiển tính transitive của dependency trong Maven; `compileOnly`, `api` và `implementation` là các configuration trong Gradle Java Library Plugin với classpath semantics riêng.

Bài này tập trung vào việc thiết kế một starter có phần auto-configuration và một hoặc nhiều tính năng tích hợp tùy chọn, đồng thời giúp consumer nhận đúng thư viện ở compile time và runtime.

## 2. Hai lớp module thường có trong custom starter

Spring Boot mô tả một cấu trúc phổ biến gồm hai module:

```text
acme-spring-boot-autoconfigure
    - @AutoConfiguration
    - @ConfigurationProperties
    - @ConditionalOnClass / @ConditionalOnMissingBean
    - callback/customizer cho thư viện Acme
    - dependency tích hợp có thể là optional

acme-spring-boot-starter
    - thường là JAR gần như rỗng
    - phụ thuộc vào acme-spring-boot-autoconfigure
    - khai báo những thư viện cần có cho trải nghiệm mặc định
    - cung cấp một dependency duy nhất cho ứng dụng
```

**Module autoconfigure** chứa code biết cách nối Spring Boot với thư viện bên ngoài. Nó có thể được dùng trực tiếp bởi một ứng dụng muốn tự chọn dependency hoặc tự đóng gói starter. Vì thế, dependency của thư viện Acme trong module này thường được đánh dấu optional/compile-only nếu tính năng chỉ nên hoạt động khi Acme có mặt.

**Module starter** là lựa chọn tiện lợi, có chủ ý về các dependency thường cần. Khi ứng dụng thêm starter, module này khai báo trực tiếp những thư viện mà trải nghiệm mặc định yêu cầu. Dependency không optional ở module starter sẽ được truyền tới ứng dụng theo cơ chế quản lý dependency tương ứng.

Không bắt buộc phải tách hai module. Với một integration nhỏ, không có tính năng tùy chọn và dependency luôn cần thiết, có thể gộp autoconfiguration và starter. Khi có nhiều flavor hoặc nhiều integration tùy chọn, tách module giúp thể hiện ranh giới rõ hơn.

### 2.1. Ví dụ về một integration tùy chọn

Giả sử thư viện có các artifact:

| Artifact | Trách nhiệm |
| --- | --- |
| `acme-client` | API và implementation của client |
| `acme-spring-boot-autoconfigure` | Auto-configuration, properties và adapter Spring |
| `acme-spring-boot-starter` | Dependency bundle cho cấu hình phổ biến |
| `acme-client-json` | Adapter JSON tùy chọn, chỉ cần nếu ứng dụng chọn tính năng này |

Ứng dụng có thể chỉ dùng `acme-spring-boot-autoconfigure` và không cài `acme-client-json`; khi đó auto-configuration cho JSON phải không được kích hoạt. Một starter riêng có thể khai báo `acme-client-json` để bật sẵn tính năng đó.

## 3. Maven: hiểu đúng optional

### 3.1. Optional không phải một dependency scope

Trong Maven, dependency có scope như `compile`, `provided`, `runtime`, `test` hoặc `system`. Thuộc tính `<optional>true</optional>` là một cờ bổ sung đặt bên trong một dependency.

Ví dụ trong POM của module autoconfigure:

```xml
<dependencies>
    <dependency>
        <groupId>com.acme</groupId>
        <artifactId>acme-client</artifactId>
        <version>${acme-client.version}</version>
        <optional>true</optional>
    </dependency>
</dependencies>
```

Dependency trên mặc định có scope `compile`. Điều đó có nghĩa:

- Module `acme-spring-boot-autoconfigure` vẫn có `acme-client` trên compile classpath để biên dịch source.
- Dependency cũng có trên runtime classpath của chính module đó.
- Khi một ứng dụng khác chỉ phụ thuộc vào `acme-spring-boot-autoconfigure`, Maven **không tự truyền** `acme-client` sang ứng dụng đó.
- Nếu ứng dụng muốn sử dụng tính năng Acme, nó phải khai báo `acme-client` trực tiếp hoặc dùng starter có khai báo dependency đó.

Vì vậy, optional không có nghĩa "không cần khi chạy module này". Nó có nghĩa "đừng mặc định áp dependency này lên mọi consumer của module".

### 3.2. Bảng phân biệt Maven scope và optional

| Khai báo | Module hiện tại | Consumer phụ thuộc module | Mục đích |
| --- | --- | --- | --- |
| `compile` (mặc định) | Compile + runtime + test | Thường nhận dependency transitive ở compile/runtime | Dependency cần thiết thông thường |
| `runtime` | Runtime + test, không compile source chính | Nhận ở runtime, không compile | Driver hoặc implementation chỉ cần lúc chạy |
| `provided` | Compile + test, không runtime | Không truyền như dependency runtime thông thường | Container/JDK/hạ tầng cung cấp |
| `test` | Compile test + chạy test | Không truyền | JUnit, Mockito, test utilities |
| `compile` + `optional=true` | Compile + runtime + test | Không tự truyền sang consumer | Tính năng tùy chọn của library |
| `runtime` + `optional=true` | Runtime + test | Không tự truyền sang consumer | Implementation runtime tùy chọn |

`optional` không thay thế `provided`. Một dependency optional compile vẫn được đưa vào runtime của module hiện tại. Một dependency provided không được đóng gói vào runtime classpath của module theo cùng cách, vì Maven giả định môi trường triển khai cung cấp nó.

Nếu một dependency là bắt buộc để ứng dụng sử dụng thư viện, không đánh dấu optional chỉ để giảm cây dependency. Nếu nó chỉ phục vụ một integration riêng, hãy cân nhắc tách module hoặc optional dependency cùng condition.

### 3.3. Optional được xử lý theo từng cạnh dependency

Giả sử:

- Project A là `acme-spring-boot-autoconfigure`.
- Project A khai báo `acme-client` là optional.
- Project B là ứng dụng phụ thuộc vào A.

Maven sẽ đưa A vào dependency graph của B, nhưng không tự đưa `acme-client` qua cạnh A → `acme-client`. B có thể tự khai báo `acme-client`, hoặc phụ thuộc vào starter C mà starter C khai báo `acme-client` như dependency thông thường.

Nếu một dependency khác trong graph cũng mang `acme-client` theo cách không optional, nó vẫn có thể xuất hiện trong ứng dụng. `optional=true` không phải lệnh loại trừ toàn cục khỏi mọi đường dependency.

Nếu consumer cần loại một transitive dependency được kéo bởi một artifact khác, dùng `<exclusions>` ở dependency phù hợp; đó là một cơ chế khác với optional.

## 4. Maven: mẫu POM cho autoconfigure module và starter module

### 4.1. Module autoconfigure

```xml
<project>
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>acme-spring-boot-autoconfigure</artifactId>
    <version>1.0.0</version>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>

        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>acme-client</artifactId>
            <version>${acme-client.version}</version>
            <optional>true</optional>
        </dependency>
    </dependencies>
</project>
```

Ở đây `spring-boot-autoconfigure` là dependency mà code auto-configuration cần để biên dịch và hoạt động. `acme-client` là integration có thể không được mọi consumer sử dụng, nên đánh dấu optional.

Trong dự án thực tế, version có thể được quản lý bằng parent POM hoặc imported BOM; ví dụ trên rút gọn để làm rõ semantics của optional.

### 4.2. Module starter

```xml
<project>
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>acme-spring-boot-starter</artifactId>
    <version>1.0.0</version>

    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>acme-spring-boot-autoconfigure</artifactId>
            <version>${project.version}</version>
        </dependency>

        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>acme-client</artifactId>
            <version>${acme-client.version}</version>
        </dependency>
    </dependencies>
</project>
```

Starter khai báo `acme-client` trực tiếp và không đánh dấu optional. Khi ứng dụng thêm `acme-spring-boot-starter`, Maven nhận cả autoconfigure module và Acme Client.

Nếu muốn starter cho JSON, tạo một artifact starter riêng hoặc thêm dependency JSON vào starter tương ứng. Không nên đưa tất cả database, JSON, messaging và cloud integrations vào một starter duy nhất nếu phần lớn ứng dụng không dùng chúng.

### 4.3. Consumer chọn cách dùng

Chỉ dùng auto-configure module và tự chọn thư viện:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>acme-spring-boot-autoconfigure</artifactId>
    <version>1.0.0</version>
</dependency>
<dependency>
    <groupId>com.acme</groupId>
    <artifactId>acme-client</artifactId>
    <version>4.2.0</version>
</dependency>
```

Hoặc dùng starter đã đóng gói các dependency mặc định:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>acme-spring-boot-starter</artifactId>
    <version>1.0.0</version>
</dependency>
```

Cả hai cách đều có thể kích hoạt auto-configuration nếu class và condition cần thiết hiện diện. Khác biệt là ai chịu trách nhiệm chọn dependency của thư viện Acme.

## 5. Gradle: api và implementation

Để dùng `api` và `implementation` cho một Java library, áp dụng plugin `java-library`:

```kotlin
plugins {
    java-library
}
```

Plugin này phân biệt dependency thuộc public API của module với dependency chỉ là chi tiết triển khai.

### 5.1. api: dependency được export cho consumer

Dùng `api` khi kiểu từ dependency xuất hiện trong API mà consumer cần compile, ví dụ:

- Một public class kế thừa class từ dependency.
- Một public interface mở rộng interface từ dependency.
- Một public method nhận hoặc trả về type của dependency.
- Một public field hoặc annotation contract dùng type từ dependency.

Ví dụ:

```kotlin
dependencies {
    api("com.acme:acme-client:4.2.0")
}
```

Consumer nhận dependency này trên compile classpath và runtime classpath. Vì vậy, code consumer có thể import `AcmeClient` khi gọi API của thư viện.

`api` không có nghĩa dependency được tải "ưu tiên hơn"; nó diễn tả dependency là một phần của compile-time API được export.

### 5.2. implementation: dependency nội bộ nhưng cần khi chạy

Dùng `implementation` khi module cần dependency để compile và chạy, nhưng consumer không cần thấy type của nó trên compile classpath.

```kotlin
dependencies {
    implementation("com.acme:acme-client:4.2.0")
}
```

Kết quả:

- Dependency có trên compile classpath của module hiện tại.
- Dependency có trên runtime classpath của module hiện tại.
- Consumer không nhận dependency trên compile classpath chỉ vì phụ thuộc vào module này.
- Consumer vẫn nhận dependency trên runtime classpath, vì implementation của library cần nó khi chạy.

Đây là lựa chọn mặc định nên ưu tiên khi dependency không thuộc public API. Nó giảm compile classpath của consumer và tránh vô tình để code consumer phụ thuộc vào một thư viện nội bộ.

Nếu consumer cần import type Acme trong source của mình, `implementation` có thể không đủ; khi đó phải xem lại API boundary và cân nhắc `api`.

## 6. Gradle: compileOnly, compileOnlyApi và runtimeOnly

### 6.1. compileOnly

`compileOnly` đưa dependency lên compile classpath của **module hiện tại**, nhưng không đưa nó vào runtime classpath và không export sang consumer.

```kotlin
dependencies {
    compileOnly("com.acme:acme-client:4.2.0")
}
```

Nó phù hợp khi:

- Module cần compile code tham chiếu type của dependency.
- Runtime của module/ứng dụng được cung cấp dependency đó từ một nơi khác, hoặc tính năng không được kích hoạt nếu dependency vắng mặt.
- Bạn không muốn dependency này tự động xuất hiện trong runtime của consumer chỉ vì consumer dùng module hiện tại.

Trong custom starter, `compileOnly` thường hợp lý ở module autoconfigure cho một integration tùy chọn được bảo vệ bởi `@ConditionalOnClass`. Starter tương ứng có thể khai báo dependency thật bằng `implementation` để đưa nó vào runtime của ứng dụng.

**Cẩn thận:** nếu dependency thực sự cần để chạy code đang được kích hoạt mà không có thành phần nào khác cung cấp nó, `compileOnly` sẽ dẫn tới lỗi `ClassNotFoundException`/`NoClassDefFoundError` hoặc lỗi linkage. `compileOnly` không tự tải dependency khi condition khớp.

### 6.2. compileOnlyApi

`compileOnlyApi` có trong Java Library Plugin. Nó làm dependency có mặt trên compile classpath của module và compile classpath của consumer, nhưng không cung cấp dependency ở runtime.

```kotlin
dependencies {
    compileOnlyApi("com.acme:acme-contract:4.2.0")
}
```

Dùng khi một type chỉ cần thiết để consumer compile với public API, còn runtime được cung cấp bởi môi trường hoặc một dependency khác. Ví dụ, một thư viện công bố annotation/type contract do container cung cấp.

Nếu ứng dụng cần chính dependency đó khi chạy, hãy đảm bảo runtime dependency được thêm riêng. `compileOnlyApi` không thay thế `api` trong trường hợp runtime cần thư viện.

### 6.3. runtimeOnly

`runtimeOnly` dành cho dependency chỉ cần khi chạy, không cần compile source của module:

```kotlin
dependencies {
    runtimeOnly("com.h2database:h2")
}
```

Ví dụ phổ biến là JDBC driver: source có thể chỉ sử dụng JDBC API từ JDK, nhưng runtime cần driver để mở kết nối. Nếu một integration module cần compile trực tiếp với class của driver, `runtimeOnly` là không đủ cho module đó; lúc ấy cần cấu hình compile phù hợp.

### 6.4. Bảng so sánh Gradle

| Configuration | Compile module | Runtime module | Consumer compile | Consumer runtime |
| --- | --- | --- | --- | --- |
| `api` | Có | Có | Có | Có |
| `implementation` | Có | Có | Không | Có |
| `compileOnly` | Có | Không | Không | Không |
| `compileOnlyApi` | Có | Không | Có | Không |
| `runtimeOnly` | Không | Có | Không | Có |

Bảng giả định sử dụng `java-library` và dependency được publish/consume theo metadata tương ứng. Khi publish cho Maven/Ivy hoặc consume metadata từ một hệ build khác, hãy kiểm tra metadata thực tế vì cách biểu diễn dependency có thể khác.

## 7. Gradle: cấu trúc custom starter hai module

### 7.1. Autoconfigure module

Ví dụ `acme-spring-boot-autoconfigure/build.gradle.kts`:

```kotlin
plugins {
    java-library
}

dependencies {
    implementation("org.springframework.boot:spring-boot-autoconfigure")
    compileOnly("com.acme:acme-client:4.2.0")

    annotationProcessor(
        "org.springframework.boot:spring-boot-configuration-processor"
    )

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("com.acme:acme-client:4.2.0")
}
```

- Code autoconfigure compile với Acme Client nhờ `compileOnly`.
- Ứng dụng chỉ phụ thuộc vào autoconfigure module không tự nhận Acme Client ở runtime.
- Test module cần thư viện thật để kiểm thử nhánh auto-configuration, nên thêm dependency trong `testImplementation`.
- `spring-boot-configuration-processor` được đặt trong `annotationProcessor`, không đặt nhầm thành `implementation`.

Nếu public method/constructor của module export trực tiếp type `AcmeClient` cho consumer, hãy cân nhắc `compileOnlyApi` thay cho `compileOnly` nếu consumer cần type đó khi compile. Hoặc thiết kế API sao cho third-party type chỉ nằm trong nested auto-configuration/internal method và public contract của starter không phơi bày nó.

### 7.2. Starter module

Ví dụ `acme-spring-boot-starter/build.gradle.kts`:

```kotlin
plugins {
    java-library
}

dependencies {
    api(project(":acme-spring-boot-autoconfigure"))
    implementation("com.acme:acme-client:4.2.0")
}
```

- `api(project(...))` export autoconfigure module tới compile classpath của ứng dụng.
- `implementation("com.acme:acme-client:...")` đưa Acme Client vào runtime classpath của consumer, nhưng không làm lộ type của nó trên compile classpath consumer.
- Nếu ứng dụng được kỳ vọng trực tiếp gọi API `AcmeClient`, hãy đổi dependency của starter thành `api(...)` hoặc cung cấp một API public của starter có chủ đích.

Nếu starter chỉ là artifact dependency bundle và không công bố type để consumer compile, có thể chọn cách đóng gói phù hợp hơn với API mong muốn. Quyết định dựa trên hợp đồng mà starter công bố, không phải vì `api` luôn tốt hơn `implementation`.

### 7.3. Tách starter theo tính năng

Nếu Acme có client core, JSON codec và messaging adapter:

```text
acme-spring-boot-autoconfigure
acme-spring-boot-starter
acme-spring-boot-starter-json
acme-spring-boot-starter-messaging
```

Mỗi starter tính năng thêm dependency tương ứng. Ứng dụng chỉ thêm JSON starter khi thật sự cần JSON integration. Cấu trúc này giảm dependency thừa và cho phép version/capability được quản lý có chủ đích.

## 8. Làm cho auto-configuration an toàn khi dependency vắng mặt

Đánh dấu dependency optional hoặc compile-only chưa đủ. Auto-configuration cần **điều kiện classpath** để không tạo bean khi thư viện không có mặt.

Ví dụ:

```java
@AutoConfiguration
@EnableConfigurationProperties(AcmeProperties.class)
public class AcmeAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(AcmeClient.class)
    static class AcmeClientConfiguration {

        @Bean
        @ConditionalOnMissingBean
        AcmeClient acmeClient(AcmeProperties properties) {
            return new AcmeClient(properties.getEndpoint());
        }
    }
}
```

Nested configuration giúp cô lập reference tới optional class. Khi `AcmeClient` không có trên classpath, Spring Boot có thể bỏ qua cấu hình con dựa trên metadata mà không cần khởi tạo bean có kiểu đó.

Trong module autoconfigure, đăng ký lớp gốc trong:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Ví dụ nội dung:

```text
com.example.acme.autoconfigure.AcmeAutoConfiguration
```

`@ConditionalOnClass` quyết định feature có được xét hay không; `@ConditionalOnMissingBean` cho phép ứng dụng cung cấp bean riêng thay thế mặc định. Hai condition giải quyết hai vấn đề khác nhau:

- Không có thư viện Acme: không kích hoạt integration.
- Có thư viện Acme nhưng ứng dụng đã có `AcmeClient`: auto-configuration nhường chỗ cho bean ứng dụng.

Không dựa vào việc dependency compile-only "tự ẩn" để thay thế class condition. Nếu code hoặc annotation metadata vẫn tham chiếu optional class ở vị trí bị JVM load quá sớm, ứng dụng có thể gặp lỗi linkage. Với optional type trong method signature, hãy cô lập nó trong nested configuration như ví dụ và kiểm thử cả classpath có/không có dependency.

## 9. Chọn configuration theo API thực sự được công bố

Một quy tắc quan trọng của Gradle là **ưu tiên `implementation` trước, chỉ dùng `api` khi public API yêu cầu**.

Ví dụ:

```java
public final class CatalogFacade {
    private final AcmeClient client;

    public CatalogFacade(AcmeClient client) {
        this.client = client;
    }

    public AcmeResponse fetch(String id) {
        return client.fetch(id);
    }
}
```

Trong ví dụ này, constructor public nhận `AcmeClient` và method public trả về `AcmeResponse`. Các type này thuộc public API của module; nếu consumer compile code gọi constructor/method đó, dependency tương ứng phải hiện diện trên compile classpath consumer. `api` là lựa chọn phù hợp nếu runtime cũng cần library.

Ngược lại:

```java
public final class CatalogFacade {
    public CatalogResult fetch(String id) {
        return internalClient.fetch(id);
    }

    private final AcmeClient internalClient;
}
```

Nếu `AcmeClient` chỉ xuất hiện trong private field và implementation, consumer không cần compile với Acme type chỉ để sử dụng `CatalogFacade`. `implementation` phù hợp hơn nếu dependency cần ở runtime.

Cần xem toàn bộ binary API, không chỉ import statement. Superclass/interface, generic parameter, annotation và public/protected method signature đều có thể làm type dependency trở thành một phần contract. Ngoài ra, compiler có một số trường hợp cần class file của type ngay cả khi nó không hiển thị rõ trong source API, ví dụ type annotation hoặc overload resolution; khi gặp lỗi compile consumer, kiểm tra classpath và cân nhắc `compileOnlyApi` hoặc `api` theo yêu cầu runtime.

## 10. Không nhầm optional dependency với feature flag

Các cơ chế sau có tác dụng khác nhau:

| Cơ chế | Câu hỏi được trả lời |
| --- | --- |
| Maven `<optional>true</optional>` | Dependency có tự truyền tới consumer không? |
| Gradle `compileOnly` | Module cần dependency khi compile nhưng không đưa nó vào runtime/consumer không? |
| Gradle `api` | Consumer có cần type dependency để compile public API không? |
| Gradle `implementation` | Module có cần dependency nội bộ khi compile và chạy không? |
| `@ConditionalOnClass` | Class có hiện diện để kích hoạt integration không? |
| `@ConditionalOnProperty` | Người dùng có bật tính năng qua Environment không? |
| `@ConditionalOnMissingBean` | Ứng dụng đã cung cấp bean thay thế chưa? |

Ví dụ, một integration có thể yêu cầu cả ba điều kiện:

```java
@AutoConfiguration
@ConditionalOnClass(AcmeClient.class)
@ConditionalOnProperty(
    prefix = "acme.client",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
public class AcmeClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    AcmeClient acmeClient() {
        return new AcmeClient();
    }
}
```

Đây là snippet minh họa; với optional type trong method signature, hãy cân nhắc nested configuration để bảo vệ quá trình class loading. Điều kiện classpath không thay thế dependency declaration: module vẫn cần dependency đúng ở nơi compile và ứng dụng cần dependency đúng ở runtime.

## 11. Kiểm tra dependency graph thực tế

Đừng chỉ nhìn build file rồi đoán dependency đã được publish như thế nào. Hãy kiểm tra graph của module producer và consumer.

### 11.1. Maven

Xem dependency tree:

```bash
mvn dependency:tree
```

Lọc riêng Acme Client:

```bash
mvn dependency:tree -Dincludes=com.acme:acme-client
```

Kỳ vọng:

- Trong autoconfigure module, `acme-client` có mặt ở tree của chính module.
- Trong ứng dụng chỉ phụ thuộc autoconfigure module, dependency optional không tự xuất hiện qua cạnh đó.
- Trong ứng dụng phụ thuộc starter, `acme-client` xuất hiện vì starter khai báo trực tiếp dependency không optional.
- Nếu nó vẫn xuất hiện khi consumer chỉ phụ thuộc autoconfigure, hãy tìm một dependency path khác cũng mang Acme Client vào.

Để kiểm tra POM đã publish, xem POM trong repository hoặc dùng `mvn help:effective-pom` cho project hiện tại. POM được publish mới là metadata consumer thực sự đọc.

### 11.2. Gradle

Xem compile classpath của consumer:

```bash
./gradlew :app:dependencies --configuration compileClasspath
```

Xem runtime classpath:

```bash
./gradlew :app:dependencies --configuration runtimeClasspath
```

Hoặc tìm lý do một dependency xuất hiện:

```bash
./gradlew :app:dependencyInsight --dependency acme-client --configuration runtimeClasspath
```

Với `java-library`, kiểm tra:

- `api`: có trên compile và runtime classpath của consumer.
- `implementation`: không trên consumer compile classpath nhưng có trên runtime classpath.
- `compileOnly`: không truyền sang compile/runtime classpath consumer.
- `compileOnlyApi`: có trên consumer compile classpath nhưng không runtime.
- `runtimeOnly`: chỉ có trên runtime classpath consumer.

Nếu publish Maven POM, kiểm tra cả metadata được sinh ra. Gradle Module Metadata giữ nhiều thông tin variant hơn; consumer dùng Maven POM có thể nhận semantics được biểu diễn bằng Maven scopes. Đừng giả định mọi consumer build tool đều đọc cùng loại metadata.

## 12. Những lỗi thường gặp

1. **Cho rằng optional là scope.** Nó là flag trên dependency, kết hợp với scope hiện tại; không thay thế compile, runtime, provided hoặc test.
2. **Đánh dấu mọi dependency là optional.** Dependency cốt lõi mà starter cần để hoạt động sẽ không tự đến với consumer; ứng dụng có thể thiếu class lúc runtime.
3. **Đánh dấu optional ở autoconfigure rồi quên khai báo lại ở starter.** Consumer thêm starter nhưng không có thư viện cần để tính năng chạy.
4. **Dùng compileOnly cho thư viện cần ở runtime nhưng không có nơi nào cung cấp.** Compile thành công nhưng context hoặc code có thể lỗi khi load class.
5. **Dùng api cho tất cả dependency.** Compile classpath consumer phình to, vô tình công bố implementation detail và tạo coupling.
6. **Dùng implementation cho type trong public API.** Consumer có thể không compile được khi gọi API chứa type đó.
7. **Dùng compileOnlyApi rồi quên runtime dependency.** Consumer compile được nhưng runtime vẫn thiếu class.
8. **Dùng runtimeOnly cho dependency mà source cần import.** Main source không compile vì class không có trên compile classpath.
9. **Dùng compileOnly nhưng quên class condition.** Auto-configuration có thể tham chiếu class vắng mặt và gây lỗi load/linkage.
10. **Đặt optional class trực tiếp trong nhiều method signature của config gốc.** Cân nhắc nested configuration có `@ConditionalOnClass` để cô lập.
11. **Dùng java plugin nhưng mong có api.** `api` và `compileOnlyApi` thuộc Java Library Plugin; áp dụng `java-library`.
12. **Dựa vào dependency transitive tình cờ.** Nếu code trực tiếp dùng type, khai báo dependency trực tiếp và đúng scope.
13. **Chỉ test trong module autoconfigure.** Module producer có dependency compile nên test luôn thấy class; cần thêm test/consumer sample không có optional dependency.
14. **Không kiểm tra artifact đã publish.** Build local có thể thành công nhưng POM/Gradle metadata publish không phản ánh cấu hình mà consumer cần.
15. **Dùng version khác nhau giữa starter và autoconfigure.** Dùng parent/BOM hoặc version catalog để quản lý version nhất quán.

## 13. Ma trận kiểm thử cho một custom starter

Một bộ kiểm thử tối thiểu nên bao gồm:

| Kịch bản | Autoconfigure module | Starter/consumer | Kết quả cần xác nhận |
| --- | --- | --- | --- |
| Chỉ dùng autoconfigure, thiếu Acme Client | Có code integration, dependency optional/compile-only | Không khai báo Acme Client | Context khởi động; integration Acme không được tạo |
| Dùng autoconfigure và khai báo Acme Client trực tiếp | Condition thấy class | Consumer thêm dependency | Bean mặc định có thể được tạo |
| Dùng starter chuẩn | Starter thêm dependency cần thiết | Chỉ thêm starter | Class có mặt và integration được cấu hình |
| User cung cấp bean | Class có mặt | Consumer có custom bean | `@ConditionalOnMissingBean` làm mặc định back off |
| Tắt feature property | Class có mặt | Property `enabled=false` | Auto-configuration không tạo bean feature |
| Dùng thư viện khác version | Version graph thay đổi | Dependency mediation/constraints | Không có lỗi binary incompatibility hoặc class linkage |

Với Spring Boot, có thể dùng `ApplicationContextRunner` để kiểm tra context theo từng classpath/property/user-bean scenario. Tuy nhiên, test trong module autoconfigure vẫn có dependency test nên không đủ chứng minh consumer không có optional library sẽ chạy được. Hãy tạo một sample consumer hoặc integration test tách biệt để xác nhận graph thực tế.

## 14. Checklist chọn dependency declaration

Trước khi publish custom starter, trả lời:

- [ ] Dependency này có bắt buộc cho mọi consumer của module không?
- [ ] Nó chỉ phục vụ một integration tùy chọn có thể tách riêng không?
- [ ] Trong Maven, dependency có nên `optional=true` ở autoconfigure module không?
- [ ] Starter module đã khai báo trực tiếp các dependency cần thiết cho trải nghiệm mặc định chưa?
- [ ] Trong Gradle, đã áp dụng `java-library` nếu cần `api`/`implementation` chưa?
- [ ] Dependency có xuất hiện trong public API? Nếu có, đã chọn `api` hoặc `compileOnlyApi` đúng runtime requirement chưa?
- [ ] Dependency chỉ là implementation detail? Đã ưu tiên `implementation` chưa?
- [ ] Dependency chỉ cần compile và được cung cấp bên ngoài? `compileOnly` có đúng không?
- [ ] Nếu runtime feature cần dependency, starter/consumer có thực sự đưa nó vào runtime classpath không?
- [ ] Optional feature được bảo vệ bằng `@ConditionalOnClass` và property condition phù hợp chưa?
- [ ] Đã test cả consumer có và không có optional dependency chưa?
- [ ] Đã kiểm tra Maven dependency tree hoặc Gradle compile/runtime classpath và metadata publish chưa?

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Maven dependency có `<optional>true</optional>` thì module hiện tại có dùng nó để compile được không?  
**Đáp án:** Có, nếu scope cho phép; optional không xóa dependency khỏi compile/runtime classpath của chính module.

**Câu 2.** Consumer phụ thuộc vào autoconfigure module có tự nhận optional dependency không?  
**Đáp án:** Không. Consumer phải khai báo dependency đó trực tiếp hoặc dùng starter khai báo nó như dependency thông thường.

**Câu 3.** `optional` có tương đương Gradle `compileOnly` không?  
**Đáp án:** Không. Optional điều khiển tính transitive; compileOnly giới hạn dependency ở compile classpath của module và loại khỏi runtime/consumer classpath.

**Câu 4.** Gradle `implementation` có được đưa vào runtime của consumer không?  
**Đáp án:** Có. Nó không xuất hiện trên compile classpath consumer, nhưng vẫn cần ở runtime để implementation của library hoạt động.

**Câu 5.** Khi nào dùng `api` thay `implementation`?  
**Đáp án:** Khi type của dependency được export trong public API và consumer cần type đó để compile.

**Câu 6.** `compileOnlyApi` khác `compileOnly` thế nào?  
**Đáp án:** Cả hai không cung cấp runtime dependency; compileOnlyApi còn đưa type lên compile classpath của consumer.

**Câu 7.** Starter đã đánh dấu thư viện Acme optional ở autoconfigure module. Muốn starter chuẩn luôn bật tính năng Acme thì làm gì?  
**Đáp án:** Starter module khai báo Acme dependency trực tiếp và không optional; runtime classpath consumer sẽ nhận nó.

**Câu 8.** Vì sao cần `@ConditionalOnClass` nếu dependency đã là compileOnly?  
**Đáp án:** CompileOnly chỉ điều khiển build classpath; nó không đảm bảo class tồn tại khi ứng dụng chạy. Condition giúp auto-configuration bỏ qua integration khi class vắng mặt.

## Tài liệu tham khảo chính thức

- Maven — Introduction to Optional and Excludes Dependencies: https://maven.apache.org/guides/introduction/introduction-to-optional-and-excludes-dependencies.html
- Maven — Introduction to the Dependency Mechanism (dependency scopes and transitivity): https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html
- Gradle — The Java Library Plugin (api, implementation, compileOnly, compileOnlyApi, runtime variants): https://docs.gradle.org/current/userguide/java_library_plugin.html
- Gradle — Building Java Projects (compile/runtime dependency configurations): https://docs.gradle.org/current/userguide/building_java_projects.html
- Spring Boot — Creating Your Own Auto-configuration and custom starters: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html

**Ghi nhớ:** Maven optional ngăn dependency tự truyền sang consumer; Gradle compileOnly chỉ cấp class lúc compile cho module; api export type cho consumer compile/runtime; implementation giữ dependency nội bộ ở compile của module nhưng vẫn cấp nó lúc runtime của consumer. Với custom starter, thường đánh dấu integration library optional ở autoconfigure module, sau đó khai báo dependency cần thiết một cách trực tiếp trong starter module.
