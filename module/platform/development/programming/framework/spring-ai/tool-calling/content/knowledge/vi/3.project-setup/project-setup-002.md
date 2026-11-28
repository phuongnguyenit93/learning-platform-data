# Quản lý dependency bằng Spring AI BOM trong Maven và Gradle

Khi tích hợp Spring AI, một ứng dụng thường dùng nhiều artifact cùng lúc: thư viện lõi, starter của nhà cung cấp mô hình, các thành phần hỗ trợ hội thoại và những thư viện Spring liên quan. Nếu tự khai báo phiên bản cho từng artifact, dự án dễ rơi vào tình trạng các module Spring AI không cùng release hoặc một dependency bị kéo về phiên bản không tương thích.

Spring AI BOM (Bill of Materials) cung cấp một tập phiên bản đã được quản lý cho các artifact thuộc cùng một dòng phát hành. Maven nhập BOM vào `dependencyManagement`; Gradle đưa BOM vào dependency graph bằng `platform(...)`. Sau đó, bạn khai báo các thư viện Spring AI cần dùng mà không phải lặp lại phiên bản ở từng dependency.

Bài này hướng dẫn cách chọn phiên bản, nhập Spring AI BOM trong Maven và Gradle, xác minh phiên bản thực tế được phân giải và xử lý các xung đột thường gặp khi thiết lập dự án tool calling.

## BOM quản lý điều gì?

BOM là một POM có danh sách dependency cùng phiên bản được đề xuất hoặc quản lý. Khi nhập BOM, công cụ build có thể lấy phiên bản cho các dependency được BOM quản lý từ một nơi thống nhất.

Trong một ứng dụng Spring Boot dùng Spring AI, thường có hai lớp quản lý phiên bản:

| Bộ quản lý phiên bản | Trách nhiệm chính |
|---|---|
| Spring Boot dependency management | Quản lý phiên bản Spring Boot, Spring Framework và nhiều thư viện nền mà Spring Boot tích hợp. |
| Spring AI BOM | Đồng bộ phiên bản các artifact Spring AI trong cùng một release line. |

Hai BOM có phạm vi khác nhau và thường được dùng cùng nhau. Spring AI BOM không thay thế Spring Boot dependency management; nó cũng không tự thêm thư viện vào ứng dụng. Bạn vẫn phải khai báo từng starter hoặc module thực sự cần dùng.

Ví dụ, nếu ứng dụng dùng starter mô hình OpenAI, dependency có thể được khai báo mà không ghi phiên bản sau khi BOM đã được nhập:

```text
org.springframework.ai:spring-ai-starter-model-openai
```

Tên starter và cấu trúc artifact có thể khác giữa các dòng phiên bản Spring AI. Hãy dùng đúng tên artifact trong tài liệu của release line mà dự án chọn; không trộn tên starter của phiên bản cũ với dependency của phiên bản mới.

## Chọn phiên bản trước khi khai báo dependency

Hãy quyết định phiên bản theo thứ tự sau:

1. Chọn phiên bản Java mà dự án sẽ dùng và xác nhận JDK đó đáp ứng yêu cầu của Spring Boot.
2. Chọn phiên bản Spring Boot phù hợp với hệ sinh thái và các thư viện hiện có.
3. Tra bảng tương thích hoặc hướng dẫn phát hành của Spring AI để chọn release line hỗ trợ phiên bản Spring Boot đã chọn.
4. Kiểm tra model provider dự kiến sử dụng có starter và khả năng tool calling phù hợp trong release line đó.
5. Ghi một phiên bản Spring AI duy nhất vào property hoặc biến dùng chung để Maven hay Gradle nhập BOM.

Không chọn riêng phiên bản mới nhất cho từng module. Một release của `spring-ai-core` và một release khác của starter có thể có API hoặc hợp đồng nội bộ không tương thích. BOM giúp giữ chúng đồng bộ; nó không thể làm cho một tổ hợp Java, Spring Boot và Spring AI vốn không tương thích trở nên tương thích.

Trong các ví dụ dưới đây, `YOUR_COMPATIBLE_SPRING_AI_VERSION` là chỗ giữ chỗ. Hãy thay bằng phiên bản phát hành cụ thể đã kiểm tra trong tài liệu tương thích trước khi build. Không để nguyên chuỗi chỗ giữ chỗ trong dự án.

## Maven: nhập BOM qua dependencyManagement

Với Maven, khai báo phiên bản Spring AI thành một property, sau đó import BOM trong phần `dependencyManagement` của POM. BOM phải được khai báo với `type` là `pom` và `scope` là `import`.

```xml
<properties>
    <spring-ai.version>YOUR_COMPATIBLE_SPRING_AI_VERSION</spring-ai.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.ai</groupId>
            <artifactId>spring-ai-bom</artifactId>
            <version>${spring-ai.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.ai</groupId>
        <artifactId>spring-ai-starter-model-openai</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Đây là các đoạn cấu hình cần đặt vào POM của dự án; phần `parent`, `groupId`, `artifactId`, plugin và các dependency khác vẫn phụ thuộc cấu trúc ứng dụng. Nếu dự án dùng Spring Boot parent, tiếp tục để parent quản lý các phiên bản thuộc Spring Boot. Nếu dự án không dùng parent đó, cần bảo đảm Spring Boot dependency management đã được cấu hình theo cách phù hợp.

Sau khi import BOM, dependency Spring AI không cần khai báo `<version>` riêng. Maven lấy phiên bản được quản lý từ BOM. Nếu bạn thêm một starter Spring AI khác, hãy khai báo nó trong `<dependencies>` theo cùng cách và chỉ rõ phiên bản khi thật sự có chủ đích ghi đè phiên bản BOM.

**Vị trí cần nhớ:** BOM nằm trong `dependencyManagement`, còn starter mà ứng dụng sử dụng nằm trong `dependencies`. Chỉ import BOM không làm starter xuất hiện trên classpath.

### Khi Maven có nhiều BOM

Một dự án có thể đồng thời nhận dependency management từ Spring Boot parent, Spring AI BOM và BOM của thư viện khác. Hãy giữ các khai báo ở đúng phạm vi và kiểm tra POM hiệu lực khi có dependency được nhiều nguồn quản lý.

Không đưa `spring-ai-bom` như một thư viện runtime thông thường. Nó là metadata phục vụ quản lý phiên bản trong quá trình phân giải dependency, không phải module mà ứng dụng cần đóng gói để chạy.

## Gradle: thêm BOM bằng platform

Gradle sử dụng dependency constraints từ platform. Khai báo Spring AI BOM bằng `platform(...)` trong cấu hình dependency của ứng dụng, rồi thêm các starter cần thiết mà không ghi phiên bản riêng.

### Groovy DSL (`build.gradle`)

```groovy
def springAiVersion = 'YOUR_COMPATIBLE_SPRING_AI_VERSION'

dependencies {
    implementation platform("org.springframework.ai:spring-ai-bom:${springAiVersion}")

    implementation 'org.springframework.ai:spring-ai-starter-model-openai'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

### Kotlin DSL (`build.gradle.kts`)

```kotlin
val springAiVersion = "YOUR_COMPATIBLE_SPRING_AI_VERSION"

dependencies {
    implementation(platform("org.springframework.ai:spring-ai-bom:$springAiVersion"))

    implementation("org.springframework.ai:spring-ai-starter-model-openai")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
```

Hai ví dụ trên thể hiện cùng một cấu hình. Chọn DSL mà dự án đang sử dụng và thay chuỗi chỗ giữ chỗ bằng release đã xác minh. Nếu dự án có nhiều module Gradle cùng dùng Spring AI, hãy đặt phiên bản ở một nơi dùng chung và áp dụng cùng platform cho những module cần Spring AI.

`platform(...)` đưa các ràng buộc phiên bản từ BOM vào quá trình phân giải. Gradle vẫn có thể phải giải quyết xung đột với dependency constraints hoặc phiên bản được khai báo ở nơi khác; vì vậy, hãy kiểm tra dependency graph sau khi thêm BOM.

### Có nên dùng enforcedPlatform không?

`enforcedPlatform(...)` áp đặt các phiên bản từ platform mạnh hơn `platform(...)` và có thể ghi đè lựa chọn phiên bản từ các dependency khác trong graph. Chỉ dùng khi bạn chủ động muốn ép toàn bộ graph tuân theo một tập phiên bản và hiểu ảnh hưởng của nó đến các thư viện tích hợp. Với cấu hình thông thường, bắt đầu bằng `platform(...)` để tôn trọng cơ chế giải quyết dependency của Gradle.

## Chọn starter cho ứng dụng tool calling

BOM chỉ quản lý phiên bản. Bạn vẫn phải chọn starter theo model provider mà ứng dụng kết nối. Ví dụ, dự án dùng OpenAI có thể thêm `spring-ai-starter-model-openai`; nếu dùng provider khác, chọn starter tương ứng trong tài liệu Spring AI của release line đã chọn.

Không cần thêm một dependency riêng chỉ vì ứng dụng sử dụng tool calling nếu starter/model integration đang dùng đã cung cấp các API Spring AI cần thiết. Các API như `@Tool`, `ToolCallback` và `ToolContext` thuộc hệ sinh thái Spring AI; cách đóng gói artifact cụ thể phụ thuộc phiên bản. Chỉ thêm module khác khi mã nguồn thực sự sử dụng API mà module đó cung cấp.

Hãy phân biệt ba việc độc lập:

| Việc cần làm | Được giải quyết bởi |
|---|---|
| Chọn các phiên bản thư viện Spring AI đồng bộ | Spring AI BOM |
| Đưa integration của model provider vào classpath | Starter hoặc module của provider |
| Cung cấp API key, endpoint, model name và cấu hình runtime | Cấu hình ứng dụng và môi trường triển khai |

Ví dụ, API key nên được lấy từ biến môi trường hoặc hệ thống quản lý secret. Không ghi key vào `pom.xml`, `build.gradle`, file version catalog hoặc mã nguồn. Import BOM không cấu hình thông tin xác thực, không chọn model và không tự bật quyền gọi công cụ ở phía provider.

## Xác minh dependency đã được phân giải

Sau khi cấu hình, hãy kiểm tra phiên bản thực tế thay vì chỉ nhìn vào nội dung POM hoặc build script.

### Với Maven

Tạo POM hiệu lực để xem dependency management sau khi kết hợp parent và các BOM:

```bash
./mvnw help:effective-pom
```

Xem cây dependency của các artifact Spring AI:

```bash
./mvnw dependency:tree -Dincludes=org.springframework.ai
```

Trên Windows, dùng wrapper `mvnw.cmd` thay cho `./mvnw`:

```powershell
.\mvnw.cmd dependency:tree -Dincludes=org.springframework.ai
```

Kết quả cần cho thấy các artifact Spring AI đang dùng được phân giải về phiên bản nhất quán theo BOM đã chọn. Nếu một artifact có phiên bản khác, hãy tìm dependency management hoặc khai báo version riêng đang tác động đến nó.

### Với Gradle

Liệt kê dependency của runtime classpath:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Tra nguồn quyết định phiên bản của một artifact cụ thể:

```bash
./gradlew dependencyInsight --dependency spring-ai-core --configuration runtimeClasspath
```

Trên Windows, dùng `gradlew.bat`:

```powershell
.\gradlew.bat dependencyInsight --dependency spring-ai-core --configuration runtimeClasspath
```

`dependencyInsight` hữu ích khi Gradle chọn phiên bản khác với điều bạn dự kiến. Đọc phần lý do lựa chọn để biết phiên bản đến từ platform, constraint, dependency bắc cầu hay khai báo trực tiếp.

Sau khi xác minh graph, chạy build và test của dự án. Dependency tree xác nhận quá trình phân giải phiên bản; nó chưa chứng minh API key, kết nối model provider hoặc tool calling hoạt động đúng lúc chạy.

## Xử lý các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra và xử lý |
|---|---|---|
| Không tìm thấy `spring-ai-bom` | Sai group/artifact, phiên bản không tồn tại hoặc repository chưa truy cập được | Kiểm tra tọa độ `org.springframework.ai:spring-ai-bom`, phiên bản đã chọn và log tải artifact. |
| Starter không tìm thấy | Dùng tên artifact của release line khác hoặc chọn nhầm provider starter | Đối chiếu tên starter trong tài liệu đúng phiên bản Spring AI. |
| Các module Spring AI có phiên bản khác nhau | Có version khai báo trực tiếp, BOM khác hoặc constraint khác can thiệp | Dùng `effective-pom`, `dependency:tree` hoặc `dependencyInsight` để tìm nguồn quản lý phiên bản. |
| Build báo thiếu class hoặc `NoSuchMethodError` | Các thư viện trên classpath không tương thích hoặc có module bị ghi đè phiên bản | Kiểm tra toàn bộ dependency graph, loại bỏ override không cần thiết và đồng bộ lại release line. |
| IDE không nhận API sau khi thêm BOM | BOM đã được import nhưng starter/module cần thiết chưa được khai báo, hoặc IDE chưa đồng bộ build | Kiểm tra phần `dependencies`, sau đó reload Maven/Gradle project. |
| Build thành công nhưng không gọi được model | Cấu hình runtime, thông tin xác thực, model hoặc khả năng tool calling của provider chưa phù hợp | Kiểm tra cấu hình môi trường và log runtime; BOM không giải quyết các vấn đề này. |

Khi cần ghi đè phiên bản một dependency cụ thể, hãy xác định lý do trước, kiểm tra tương thích với các module Spring AI còn lại và ghi lại quyết định đó. Một override có thể giải quyết một cảnh báo nhưng cũng có thể tạo ra lỗi runtime khó phát hiện.

## Quy tắc giữ cấu hình ổn định

- Khai báo một phiên bản Spring AI ở một nơi dùng chung; tránh lặp các số phiên bản trên từng starter.
- Chọn Spring AI release line theo bảng tương thích với Java và Spring Boot của dự án.
- Dùng cùng BOM cho các module ứng dụng có tích hợp Spring AI, trừ khi có lý do kỹ thuật rõ ràng để tách phiên bản.
- Tránh phiên bản động như `+` hoặc version range vì kết quả build có thể thay đổi theo thời điểm phân giải.
- Không trộn starter cũ và mới trong cùng một classpath chỉ vì tên artifact gần giống nhau.
- Kiểm tra dependency graph khi thêm provider, nâng cấp BOM hoặc thay đổi cấu hình dependency management.
- Lưu wrapper và cấu hình build trong repository để thành viên khác có thể tái lập quá trình build.
- Quản lý API key và endpoint bằng cấu hình môi trường; không đưa secret vào repository.

## Bài tập thực hành

Tạo một ứng dụng Spring Boot nhỏ để thử nghiệm cấu hình dependency:

1. Chọn phiên bản Java và Spring Boot, sau đó tra release line Spring AI tương thích.
2. Nhập `spring-ai-bom` bằng Maven hoặc Gradle theo build tool của dự án.
3. Thêm một starter model provider phù hợp mà không ghi phiên bản riêng cho starter.
4. Chạy lệnh xem dependency tree và ghi lại phiên bản của BOM, starter và `spring-ai-core`.
5. Tạm thêm một khai báo version riêng cho một artifact Spring AI trong môi trường thử nghiệm, chạy lại lệnh kiểm tra để nhận diện nguồn xung đột, rồi bỏ override đó.
6. Build và chạy một kiểm thử khởi tạo context để xác nhận starter có mặt trên classpath.

Bạn hoàn thành bài tập khi có thể giải thích BOM đang quản lý những dependency nào, starter nào được đưa vào ứng dụng và công cụ build đã chọn phiên bản cuối cùng từ nguồn nào. Đây là nền tảng để các bài tiếp theo tập trung vào cấu hình provider và xây dựng công cụ bằng Spring AI.
