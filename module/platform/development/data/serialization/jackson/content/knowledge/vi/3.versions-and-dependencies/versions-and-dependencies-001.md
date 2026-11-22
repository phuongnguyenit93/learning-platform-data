# Xác định dòng phiên bản Jackson và phạm vi API được sử dụng

Chọn Jackson cho một ứng dụng Java không chỉ là chọn một con số phiên bản rồi thêm dependency `jackson-databind`. Một dự án có thể nhận Jackson gián tiếp từ framework, thư viện HTTP hoặc starter; các module `core`, `databind`, `annotations`, datatype và dataformat cũng có vòng đời phiên bản cần được giữ tương thích. Vì vậy, cần trả lời hai câu hỏi riêng: **ứng dụng đang chạy trên dòng phiên bản Jackson nào**, và **ứng dụng thực sự cần những API/module nào của Jackson**.

Hai câu hỏi này liên quan nhưng không đồng nhất. Dòng phiên bản xác định nền tảng API, khả năng tương thích và yêu cầu runtime. Phạm vi API xác định phần nào của hệ sinh thái Jackson được đưa vào ứng dụng, được gọi trực tiếp trong mã nguồn hoặc được dùng gián tiếp qua framework. Xác định đúng cả hai giúp tránh xung đột dependency, nâng cấp nhầm major version, kéo theo module không cần thiết và phụ thuộc vào API mà môi trường triển khai không cung cấp.

## 1. Phân biệt dòng phiên bản, phiên bản artifact và phạm vi API

Khi đọc một dependency, cần tách các khái niệm sau:

| Khái niệm | Ý nghĩa | Ví dụ minh họa |
|---|---|---|
| Dòng phiên bản (version line) | Nhóm phát hành có cùng major version và quy tắc tương thích chính. | Jackson 2.x hoặc Jackson 3.x. |
| Major version | Ranh giới có thể chứa thay đổi không tương thích về API, package hoặc yêu cầu runtime. | Chuyển từ 2.x sang 3.x. |
| Minor version | Bản phát hành bổ sung hoặc thay đổi tính năng trong một major line. | Một phiên bản 2.y mới hơn trong dòng 2.x. |
| Patch version | Bản sửa lỗi hoặc cập nhật nhỏ trong một minor release. | Một phiên bản 2.y.z. |
| Artifact | Một thư viện được đóng gói và phát hành riêng. | `jackson-core`, `jackson-databind`. |
| Dependency coordinates | Định danh artifact trong hệ thống build. | `groupId:artifactId:version` trong Maven. |
| API surface | Các package, class, method và module mà ứng dụng sử dụng. | `ObjectMapper`, `JsonParser`, `JsonNode`, Java Time module. |
| Dependency graph | Toàn bộ dependency trực tiếp và gián tiếp sau khi build tool giải quyết phiên bản. | Jackson được kéo vào bởi ứng dụng và các thư viện khác. |

Một ứng dụng có thể khai báo `jackson-databind` trực tiếp nhưng đồng thời nhận `jackson-core` từ một dependency khác. Nếu chỉ nhìn file khai báo ban đầu, ta chưa biết chính xác phiên bản nào cuối cùng có mặt trên classpath. Dependency graph đã được giải quyết mới là căn cứ để xác định phiên bản hiệu lực.

## 2. Hai dòng phiên bản lớn cần phân biệt

Jackson 2.x là dòng được sử dụng rộng rãi trong nhiều ứng dụng Java và hệ sinh thái framework hiện có. Jackson 3.x là major line mới với các thay đổi cần được xem như một đợt migration có chủ đích.

### 2.1. Jackson 2.x

Trong dòng 2.x, các package phổ biến có tiền tố `com.fasterxml.jackson`, ví dụ:

```java
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.annotation.JsonProperty;
```

Các artifact thường gặp có group ID thuộc `com.fasterxml.jackson.*`:

| Chức năng | Artifact thường dùng trong dòng 2.x |
|---|---|
| JSON streaming | `com.fasterxml.jackson.core:jackson-core` |
| Databinding và tree model | `com.fasterxml.jackson.core:jackson-databind` |
| Annotation | `com.fasterxml.jackson.core:jackson-annotations` |
| Java 8 datatype | `com.fasterxml.jackson.datatype:jackson-datatype-jdk8` |
| Java Time | `com.fasterxml.jackson.datatype:jackson-datatype-jsr310` |
| Kotlin | `com.fasterxml.jackson.module:jackson-module-kotlin` |
| YAML | `com.fasterxml.jackson.dataformat:jackson-dataformat-yaml` |

Các minor release trong cùng major line vẫn có thể bổ sung API hoặc thay đổi hành vi ở một số trường hợp. Do đó, không nên suy luận rằng mọi phiên bản 2.x đều có mọi method xuất hiện trong tài liệu của một bản 2.x mới hơn. Nếu mã nguồn gọi một API mới, phiên bản thực tế trong dependency graph phải cung cấp API đó.

Ứng dụng đang dùng framework thường nên bắt đầu từ dependency management do framework cung cấp. Framework có thể kiểm thử với một tập hợp phiên bản Jackson cụ thể; tự nâng riêng một artifact có thể tạo ra tổ hợp mà framework chưa xác nhận.

### 2.2. Jackson 3.x

Jackson 3.x là thay đổi major. Không nên xem việc đổi số phiên bản từ 2 lên 3 là thao tác nâng cấp patch thông thường. Dòng mới có thay đổi về yêu cầu Java, package và một số API/cấu trúc module. Jackson 3 yêu cầu Java 17 trở lên; ứng dụng có runtime thấp hơn không thể chỉ đổi dependency để sử dụng dòng này.

Các package core và databind của dòng 3 sử dụng namespace `tools.jackson.*`, ví dụ:

```java
import tools.jackson.core.JsonParser;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.JsonNode;
```

Các tọa độ artifact cũng chuyển sang namespace group ID mới của dòng 3. Ví dụ dependency databind có dạng:

```text
tools.jackson.core:jackson-databind:<version-3.x>
```

Không được suy luận rằng chỉ cần thay group ID là toàn bộ mã nguồn tương thích. Hãy kiểm tra migration guide và Javadoc của đúng phiên bản cho từng API, module và annotation đang sử dụng. Một số module mở rộng có thể có lịch phát hành hoặc mức hỗ trợ riêng; phải xác nhận module cụ thể đã có bản tương thích với dòng 3 mà dự án định chọn.

Khi chuyển major, cần kiểm tra đồng thời:

- Phiên bản JDK của môi trường build, test và production.
- Package import trong mã nguồn, annotation và custom serializer/deserializer.
- API đã bị đổi tên, thay đổi chữ ký hoặc loại bỏ.
- Artifact coordinates và BOM tương ứng.
- Module datatype/dataformat và các thư viện tích hợp Jackson.
- Framework hoặc starter có hỗ trợ dòng 3 trong phiên bản đang dùng hay không.
- Các test hợp đồng JSON, đặc biệt với null, enum, ngày giờ, polymorphic type và field lạ.

### 2.3. Không trộn tùy tiện hai major line

Jackson 2.x và 3.x có namespace và hệ dependency khác nhau. Một ứng dụng có thể vô tình kéo cả hai dòng vào classpath thông qua các thư viện khác nhau. Điều đó không có nghĩa chúng tự động thay thế lẫn nhau: một thư viện biên dịch với package/API của 2.x vẫn cần những class tương ứng của 2.x, còn mã nguồn dùng API 3.x cần đúng artifact 3.x.

Nếu dependency graph có cả hai dòng, hãy xác định thư viện nào mang từng dòng vào, API nào thực sự được gọi và liệu framework có chủ đích hỗ trợ song song hay không. Không cố khắc phục bằng cách ép tất cả artifact về cùng một chuỗi version nếu chúng thuộc hai hệ tọa độ và namespace khác nhau.

## 3. Cách đọc một dependency Jackson

Với Maven, một dependency có ba thành phần định danh chính:

```xml
<dependency>
    <groupId>com.fasterxml.jackson.core</groupId>
    <artifactId>jackson-databind</artifactId>
    <version>2.x.y</version>
</dependency>
```

- `groupId` cho biết nhóm phát hành và thường giúp nhận diện dòng artifact.
- `artifactId` cho biết module cụ thể, chẳng hạn databinding hay streaming.
- `version` xác định bản phát hành của artifact đó.

Với Gradle, notation tương đương thường có dạng:

```kotlin
implementation("com.fasterxml.jackson.core:jackson-databind:2.x.y")
```

Không nên chỉ tìm chuỗi `jackson` trong file build rồi kết luận ứng dụng đang dùng phiên bản nào. Cần xem dependency được khai báo trực tiếp, dependency được kế thừa từ parent/BOM, dependency do plugin hoặc framework thêm vào và kết quả giải quyết cuối cùng của build tool.

## 4. Xác định phiên bản thực tế trong Maven

### 4.1. Xem dependency tree

Chạy từ thư mục dự án có `pom.xml`:

```bash
mvn dependency:tree -Dincludes=com.fasterxml.jackson
```

Với dự án có dependency thuộc namespace mới, mở rộng bộ lọc để xem các artifact liên quan đến `tools.jackson`:

```bash
mvn dependency:tree -Dincludes=tools.jackson
```

Dependency tree cho thấy đường đi của dependency. Ví dụ về mặt cấu trúc:

```text
application
+- framework-starter
|  \- jackson-databind:2.x.y
|     +- jackson-core:2.x.y
|     \- jackson-annotations:2.x.y
\- another-library
   \- jackson-core:2.a.b
```

Đây là ví dụ minh họa tình huống có yêu cầu phiên bản khác nhau. Phiên bản được Maven chọn phụ thuộc quy tắc mediation, vị trí khai báo và `dependencyManagement`. Hãy đọc cả nhánh dependency và phiên bản cuối cùng trong output, không chỉ nhìn dòng khai báo trực tiếp.

### 4.2. Xem POM hiệu lực

Parent POM, profile và BOM có thể làm thay đổi phiên bản so với nội dung nhìn thấy trong `pom.xml`. Có thể xuất POM sau khi Maven áp dụng các cấu hình:

```bash
mvn help:effective-pom
```

Trong POM hiệu lực, tìm `jackson-bom`, `jackson-databind` và các artifact Jackson liên quan. Nếu dự án có nhiều module Maven, chạy lệnh ở đúng module hoặc từ reactor root với lựa chọn phù hợp để không đọc nhầm dependency graph của một module khác.

### 4.3. Hiểu vai trò của `dependencyManagement`

`dependencyManagement` quản lý phiên bản và metadata cho dependency khi dependency được khai báo trong module. Nó không tự động thêm tất cả artifact được quản lý vào classpath.

Ví dụ import Jackson BOM trong Maven:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.fasterxml.jackson</groupId>
            <artifactId>jackson-bom</artifactId>
            <version>${jackson.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
    </dependency>
</dependencies>
```

Trong ví dụ này, BOM quản lý phiên bản cho các artifact thuộc bộ Jackson tương ứng; dependency `jackson-databind` vẫn cần được khai báo trong `<dependencies>` để được đưa vào dự án. Dùng BOM giúp các module cùng bộ phát hành được căn chỉnh theo một tập phiên bản đã công bố.

Nếu dự án dùng Jackson 3, hãy dùng BOM và tọa độ artifact thuộc dòng 3 tương ứng. Không dùng BOM 2.x để quản lý artifact 3.x hoặc ngược lại.

## 5. Xác định phiên bản thực tế trong Gradle

### 5.1. Xem dependency graph

Với Gradle, kiểm tra runtime classpath:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Để tập trung vào một dependency:

```bash
./gradlew dependencyInsight \
  --dependency jackson-databind \
  --configuration runtimeClasspath
```

`dependencyInsight` hữu ích vì nó cho biết dependency được yêu cầu từ đâu và lý do phiên bản được chọn. Nếu ứng dụng chạy bằng một configuration khác, ví dụ test runtime hoặc một source set riêng, cần kiểm tra đúng configuration đó.

### 5.2. Dùng platform để căn chỉnh phiên bản

Với Jackson 2.x, Gradle có thể import BOM dưới dạng platform:

```kotlin
dependencies {
    implementation(platform("com.fasterxml.jackson:jackson-bom:$jacksonVersion"))
    implementation("com.fasterxml.jackson.core:jackson-databind")
    implementation("com.fasterxml.jackson.datatype:jackson-datatype-jsr310")
}
```

Với Jackson 3.x, dùng BOM và group ID tương ứng của dòng 3:

```kotlin
dependencies {
    implementation(platform("tools.jackson:jackson-bom:$jacksonVersion"))
    implementation("tools.jackson.core:jackson-databind")
}
```

Các ví dụ dùng biến `jacksonVersion` để thể hiện một nguồn quản lý phiên bản tập trung. Hãy chọn phiên bản BOM đã được xác nhận cho framework và JDK của dự án. Không chép một version minh họa vào mọi dự án mà bỏ qua dependency management sẵn có.

Gradle có thể chọn một phiên bản khác với version được yêu cầu ban đầu do conflict resolution, constraint, platform, resolution rule hoặc dependency substitution. Vì vậy, file build chỉ cho biết yêu cầu; dependency report mới cho biết kết quả.

## 6. BOM và nguyên tắc căn chỉnh các module

Jackson gồm nhiều artifact phát hành riêng. Một dự án có thể cần `jackson-databind`, `jackson-dataformat-yaml` và `jackson-datatype-jsr310`. Các module này có quan hệ tương thích với những thành phần nền tảng của Jackson. Nếu khai báo từng version độc lập, dự án dễ tạo ra tổ hợp lệch nhau.

Ví dụ một cấu hình dễ gây khó kiểm soát:

```xml
<dependencies>
    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
        <version>2.x.a</version>
    </dependency>
    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-core</artifactId>
        <version>2.x.b</version>
    </dependency>
    <dependency>
        <groupId>com.fasterxml.jackson.datatype</groupId>
        <artifactId>jackson-datatype-jsr310</artifactId>
        <version>2.x.c</version>
    </dependency>
</dependencies>
```

Các hậu tố `a`, `b`, `c` chỉ biểu diễn những version khác nhau. Cấu hình này có thể chạy hoặc có thể phát sinh lỗi tùy API và module cụ thể, nhưng nó làm cho tính tương thích khó dự đoán. BOM giảm rủi ro đó bằng cách cung cấp một bộ version được căn chỉnh.

Một số nguyên tắc thực hành:

1. Chọn một BOM tương ứng với đúng major line.
2. Để BOM quản lý version của các artifact Jackson thuộc phạm vi nó quản lý.
3. Chỉ thêm version riêng khi có lý do rõ ràng và đã kiểm tra tác động đến dependency graph.
4. Căn chỉnh cả module datatype và dataformat, không chỉ `core` và `databind`.
5. Kiểm tra kết quả cuối bằng dependency tree hoặc `dependencyInsight`.

BOM không thay thế việc chọn module. Nó chỉ quản lý phiên bản cho các module được khai báo; artifact không được dùng thì không cần thêm chỉ vì BOM có quản lý nó.

## 7. Xác định phạm vi API mà ứng dụng cần

Không phải ứng dụng nào dùng Jackson cũng cần toàn bộ hệ sinh thái. Phạm vi nên được xác định từ mã nguồn, hợp đồng dữ liệu và những tính năng thực sự chạy.

### 7.1. `jackson-core`: đọc và ghi JSON ở mức token

`jackson-core` cung cấp streaming API:

- `JsonFactory` tạo parser và generator.
- `JsonParser` đọc token từ JSON.
- `JsonGenerator` phát token JSON.
- `JsonToken` biểu diễn loại token đang đọc.

Nếu ứng dụng chỉ cần duyệt dữ liệu lớn tuần tự hoặc tự kiểm soát quá trình phát JSON, core API có thể là phần API trực tiếp quan trọng. Core không cung cấp đầy đủ databinding object theo kiểu `ObjectMapper`.

Ví dụ phạm vi core:

```java
try (JsonParser parser = jsonFactory.createParser(inputStream)) {
    while (parser.nextToken() != null) {
        JsonToken token = parser.currentToken();
        // Xử lý token theo cấu trúc dữ liệu của ứng dụng.
    }
}
```

### 7.2. `jackson-databind`: object mapping và tree model

`jackson-databind` cung cấp API cấp cao thường gặp:

- `ObjectMapper`: facade đọc và ghi object.
- `ObjectReader` và `ObjectWriter`: cấu hình đọc/ghi theo tác vụ.
- `JsonNode`, `ObjectNode`, `ArrayNode`: tree model.
- Serializer/deserializer và cơ chế chuyển đổi kiểu.
- `JavaType` và `TypeReference`: biểu diễn kiểu generic.

Nếu ứng dụng chuyển DTO sang JSON hoặc JSON sang DTO, databind thường là dependency chính. Khi dùng databind, các dependency nền tảng cần thiết thường được kéo theo. Tuy nhiên, nếu mã nguồn ứng dụng trực tiếp import class từ một artifact khác, nên cân nhắc khai báo artifact đó trực tiếp để thể hiện dependency mà mã nguồn thực sự sử dụng.

### 7.3. `jackson-annotations`: metadata trên model

Annotation mô tả cách thuộc tính Java tương ứng với JSON, ví dụ:

- `@JsonProperty`: tên thuộc tính.
- `@JsonIgnore`: bỏ qua thuộc tính.
- `@JsonCreator`: cách tạo object.
- `@JsonAlias`: tên thay thế khi đọc.
- `@JsonFormat`: định dạng biểu diễn trong các trường hợp được hỗ trợ.
- `@JsonInclude`: quy tắc đưa giá trị vào JSON.

Nếu model của ứng dụng gắn annotation Jackson trực tiếp, annotation là một phần của API compile-time mà mã nguồn phụ thuộc. Khi nâng major, phải kiểm tra package và artifact cung cấp annotation tương ứng; không thay import hàng loạt chỉ dựa trên tên group ID.

### 7.4. Datatype modules

Datatype module bổ sung cách ánh xạ cho kiểu Java không nằm trong tập kiểu cơ bản hoặc cần quy tắc chuyên biệt.

| Module thường gặp | Phạm vi sử dụng |
|---|---|
| `jackson-datatype-jdk8` | Một số kiểu trong Java 8 như `Optional`. |
| `jackson-datatype-jsr310` | Các kiểu ngày giờ trong `java.time`. |
| `jackson-module-parameter-names` | Sử dụng tên tham số constructor khi metadata tương ứng có sẵn và được cấu hình. |
| `jackson-module-kotlin` | Hỗ trợ mapping cho class, constructor và kiểu dữ liệu Kotlin. |

Chỉ đăng ký module khi ứng dụng có kiểu dữ liệu hoặc quy tắc mapping cần module đó. Với framework, module có thể được tự động phát hiện hoặc đăng ký qua cấu hình tích hợp; cần hiểu rõ cơ chế của framework để tránh đăng ký lặp hoặc bỏ sót.

### 7.5. Dataformat modules

Jackson có các module làm việc với định dạng dữ liệu ngoài JSON, chẳng hạn YAML, XML, CSV hoặc CBOR. Chúng mở rộng cách đọc/ghi định dạng tương ứng và có thể mang theo dependency riêng.

Ví dụ, nếu ứng dụng chỉ nhận và trả JSON, không nên thêm module YAML hoặc XML chỉ vì chúng thuộc cùng hệ sinh thái Jackson. Nếu ứng dụng cần YAML, cần kiểm tra phiên bản `jackson-dataformat-yaml`, dependency parser YAML đi kèm và khả năng tương thích với core/databind của dòng đang dùng.

### 7.6. Module tích hợp hoặc tối ưu

Một số module hỗ trợ framework, ngôn ngữ, hiệu năng hoặc kiểu dữ liệu chuyên biệt. Trước khi thêm, hãy xác định module đó giải quyết yêu cầu nào, có cần ở compile-time hay runtime, tương thích với major line nào và có được framework quản lý sẵn hay không.

## 8. Dependency trực tiếp và dependency bắc cầu

Dependency trực tiếp là dependency được khai báo trong build file của ứng dụng. Dependency bắc cầu được kéo vào bởi một dependency khác.

Ví dụ:

```text
Ứng dụng
  |
  +-- framework-starter
  |      |
  |      +-- jackson-databind
  |      +-- jackson-core
  |      +-- jackson-annotations
  |
  +-- application-module
         |
         +-- jackson-datatype-jsr310
```

Nếu ứng dụng chỉ gọi `ObjectMapper` thông qua starter, framework có thể đã cung cấp databind và cấu hình mapper. Nếu mã nguồn của ứng dụng trực tiếp dùng `JsonParser`, `JsonNode` hoặc annotation, dependency graph cần cung cấp các API đó ở compile classpath.

Một quy tắc hữu ích là khai báo trực tiếp những artifact mà mã nguồn hoặc cấu hình ứng dụng trực tiếp phụ thuộc, đồng thời tránh khai báo lại các dependency chỉ được framework quản lý nếu dự án có quy ước dependency management rõ ràng. Điều quan trọng là dependency declaration phản ánh đúng ranh giới trách nhiệm và phiên bản hiệu lực vẫn được quản lý tập trung.

Không nên xóa dependency chỉ vì nó không xuất hiện trong import Java. Một framework có thể phát hiện module qua service loader, cấu hình runtime hoặc reflection. Trước khi loại bỏ, hãy xác định cả dependency sử dụng gián tiếp.

## 9. Framework và BOM của ứng dụng

Các framework Java thường cung cấp dependency management riêng. Starter có thể đưa Jackson vào mà không cần dự án khai báo version cụ thể. Khi đó, phiên bản Jackson là một phần của tập dependency mà framework đã chọn và kiểm thử.

Khi dùng Spring Boot hoặc framework tương tự:

1. Xác định version framework trước.
2. Xem BOM hoặc dependency management mà framework sử dụng.
3. Kiểm tra phiên bản Jackson thực tế trong runtime classpath.
4. Chỉ override Jackson khi có lý do kỹ thuật rõ ràng, chẳng hạn cần bản sửa lỗi hoặc API mới.
5. Khi override, kiểm tra tương thích giữa các module Jackson và framework, sau đó chạy integration test của serialization/deserialization.

Không nên trộn BOM framework với một BOM Jackson độc lập mà không hiểu quy tắc ưu tiên. Maven có thể áp dụng `dependencyManagement` từ nhiều nguồn theo thứ tự khai báo và cấu trúc kế thừa; Gradle có thể giải quyết platform, constraint và rule. Kết quả cần được xác nhận bằng báo cáo dependency của chính dự án.

## 10. Kiểm tra API đang dùng trong mã nguồn

Để xác định phạm vi API, hãy tìm những package và class Jackson mà mã nguồn import hoặc tham chiếu. Có thể tìm theo các nhóm:

| Nhóm tìm kiếm | Ví dụ class/package |
|---|---|
| Core streaming | `JsonFactory`, `JsonParser`, `JsonGenerator`, `JsonToken` |
| Databinding | `ObjectMapper`, `ObjectReader`, `ObjectWriter`, `JsonSerializer`, `JsonDeserializer` |
| Tree model | `JsonNode`, `ObjectNode`, `ArrayNode` |
| Annotation | `JsonProperty`, `JsonCreator`, `JsonIgnore`, `JsonFormat` |
| Datatype | `JavaTimeModule`, `Jdk8Module`, module Kotlin |
| Dataformat | YAML, XML, CSV, CBOR factory/parser/generator |

Ví dụ dùng `rg` trong repository:

```bash
rg -n "com\.fasterxml\.jackson|tools\.jackson" --glob "*.java" --glob "*.kt"
```

Tìm thêm trong file build và cấu hình:

```bash
rg -n "jackson|Jackson" --glob "pom.xml" --glob "*.gradle" --glob "*.gradle.kts" --glob "*.yml" --glob "*.yaml" --glob "*.properties"
```

Kết quả tìm kiếm import chỉ phản ánh API được gọi trực tiếp trong source được quét. Nó không bao quát cấu hình XML, reflection, service loader, framework auto-configuration hoặc thư viện đã biên dịch. Vì vậy, phải kết hợp source search với dependency graph và test runtime.

## 11. Kiểm tra phiên bản ở runtime

Trong một số môi trường, cần xác nhận artifact thực tế đã được nạp. Có thể xem metadata package của một class:

```java
Package packageInfo = ObjectMapper.class.getPackage();
String implementationVersion = packageInfo == null
    ? null
    : packageInfo.getImplementationVersion();

System.out.println("Jackson databind version: " + implementationVersion);
```

Tên import của `ObjectMapper` phụ thuộc major line. Metadata `Implementation-Version` có thể không tồn tại hoặc trả về `null` nếu cách đóng gói không cung cấp thông tin đó. Vì vậy, đây chỉ là một dấu hiệu runtime, không thay thế dependency report.

Trong container hoặc ứng dụng đóng gói, hãy kiểm tra classpath thực tế và nội dung artifact được đưa vào image/package. Một build thành công ở máy phát triển không chứng minh production đang chạy cùng tập JAR nếu quá trình đóng gói, shading hoặc triển khai thay đổi classpath.

## 12. Chọn dòng phiên bản theo ràng buộc dự án

Quyết định chọn 2.x hay 3.x cần dựa trên các ràng buộc cụ thể:

| Ràng buộc | Câu hỏi cần trả lời |
|---|---|
| JDK | Runtime tối thiểu có đáp ứng yêu cầu của major line không? |
| Framework | Framework/starter hiện tại hỗ trợ và kiểm thử với dòng nào? |
| Thư viện tích hợp | Các thư viện HTTP, messaging, persistence hoặc SDK có tương thích không? |
| Source API | Mã nguồn có dùng package hoặc API đã thay đổi giữa các major không? |
| Module | Các datatype/dataformat cần thiết đã có bản phù hợp chưa? |
| Vận hành | Môi trường build, test, container và production có cùng runtime/classpath không? |
| Bảo trì | Dòng phiên bản được chọn còn nhận cập nhật phù hợp với chính sách dự án không? |

Một dự án đang ổn định trên Jackson 2.x có thể tiếp tục dùng dòng 2.x phù hợp với framework và chính sách bảo trì hiện tại. Một dự án mới hoặc có kế hoạch migration có thể đánh giá Jackson 3.x nếu toàn bộ nền tảng đáp ứng yêu cầu JDK, framework và module. Không có quy tắc rằng cứ major mới hơn thì tự động phù hợp hơn với mọi ứng dụng.

## 13. Quy trình nâng cấp có kiểm soát

Nâng cấp trong cùng major line và chuyển major line có mức độ tác động khác nhau. Dù là loại nào, nên thực hiện theo trình tự có thể kiểm chứng.

### 13.1. Nâng minor hoặc patch trong cùng major

1. Ghi nhận dependency tree hiện tại và version được framework quản lý.
2. Xác định lý do nâng cấp: bản sửa lỗi, bảo mật, tính năng hoặc tương thích JDK.
3. Chọn một BOM/release set phù hợp thay vì sửa version rời rạc cho từng artifact.
4. Xem release notes của phiên bản đích để biết thay đổi hành vi và API.
5. Chạy compile, unit test và integration test của các luồng JSON.
6. Kiểm tra dependency tree sau nâng cấp để phát hiện module lệch version hoặc major ngoài dự kiến.

### 13.2. Chuyển từ Jackson 2.x sang 3.x

Đây là migration lớn hơn và cần một nhánh công việc riêng:

1. Xác nhận JDK tối thiểu của build, CI, test và production.
2. Kiểm tra framework, starter và thư viện tích hợp đã hỗ trợ Jackson 3 hay chưa.
3. Lập danh sách import, annotation, custom serializer/deserializer, module và cấu hình Jackson đang dùng.
4. Thay BOM và dependency coordinates theo dòng 3, đồng thời loại bỏ override thuộc dòng 2 không còn phù hợp.
5. Chuyển mã nguồn theo migration guide, xử lý thay đổi package và API ở từng module.
6. Kiểm tra các module datatype/dataformat và module do framework tự đăng ký.
7. Chạy test round-trip, test hợp đồng API và test với payload thực tế đại diện.
8. Kiểm tra dependency graph và runtime classpath sau khi đóng gói.

Không nên gộp migration major vào một thay đổi dependency nhỏ mà không có test hợp đồng. Các khác biệt có thể không làm compile thất bại nhưng vẫn làm JSON đầu ra hoặc cách xử lý đầu vào thay đổi.

## 14. Kiểm tra hợp đồng JSON khi thay đổi phiên bản

Một test chỉ xác nhận `readValue` không ném exception là chưa đủ. Ứng dụng cần kiểm tra cả dữ liệu sau mapping và JSON được phát ra.

Ví dụ kiểm tra round-trip cơ bản:

```java
String input = """
    {
      "id": 42,
      "display_name": "An",
      "active": true
    }
    """;

User user = mapper.readValue(input, User.class);
assertEquals(42L, user.getId());
assertEquals("An", user.getName());
assertTrue(user.isActive());

String output = mapper.writeValueAsString(user);
JsonNode tree = mapper.readTree(output);
assertEquals(42, tree.path("id").asInt());
assertEquals("An", tree.path("display_name").asText());
assertTrue(tree.path("active").asBoolean());
```

Với ứng dụng thực tế, bổ sung trường hợp:

- Field bị thiếu và field có giá trị `null`.
- Field không biết trước và alias cũ.
- Enum đã biết và enum mới.
- Số nguyên, số thập phân, giá trị biên và overflow.
- Ngày giờ, timezone và định dạng timestamp.
- Collection rỗng, object lồng nhau và generic type.
- Polymorphic type nếu ứng dụng sử dụng.
- Unicode, escaping và ký tự đặc biệt.
- Custom serializer/deserializer và module được framework tự đăng ký.

Khi so sánh JSON, hãy phân biệt khác biệt không gian trắng/thứ tự field với thay đổi ngữ nghĩa. Nếu thứ tự field là một phần của hợp đồng đặc biệt, phải cấu hình và kiểm thử riêng; thông thường client nên dựa vào tên và giá trị field thay vì thứ tự thuộc tính trong object JSON.

## 15. Các sai lầm thường gặp khi xác định phiên bản và phạm vi

### Chỉ nhìn version trong file build

Version khai báo có thể bị BOM, parent POM, platform hoặc conflict resolution thay đổi. Hãy kiểm tra dependency graph ở đúng configuration.

### Chỉ nâng `jackson-databind`

Các module liên quan có thể vẫn ở version cũ hoặc bị framework quản lý theo cách khác. Dùng BOM phù hợp và xác nhận toàn bộ artifact sau khi resolve.

### Cho rằng mọi artifact Jackson đều cần thiết

Ứng dụng dùng JSON cơ bản không tự động cần YAML, XML, Kotlin hoặc Java Time module. Chọn theo kiểu dữ liệu và định dạng thực sự xuất hiện trong hợp đồng.

### Cho rằng cùng tên class nghĩa là cùng API

Một class có tên tương tự giữa hai major line không đảm bảo package, method, hành vi và binary compatibility giống nhau. Kiểm tra import và tài liệu đúng phiên bản.

### Dựa vào dependency bắc cầu mà không biết nguồn

Nếu framework mang Jackson vào, nâng hoặc loại bỏ dependency có thể ảnh hưởng tích hợp của framework. Dùng dependency tree để tìm đường dẫn đưa artifact vào.

### Bỏ module vì không thấy import

Module có thể được đăng ký tự động hoặc được dùng qua reflection. Xác định cả cấu hình runtime và auto-configuration trước khi loại bỏ.

### Ép tất cả dependency về một version bằng exclusion tùy tiện

Exclusion có thể loại bỏ dependency cần thiết hoặc phá vỡ thư viện phụ thuộc. Chỉ dùng khi hiểu rõ đường đi dependency và có kiểm thử chứng minh tổ hợp mới hợp lệ.

## 16. Ví dụ đọc một tình huống dependency

Giả sử dự án có cấu hình như sau:

```text
Java runtime: 17
Framework starter: quản lý Jackson 2.x
Application code: ObjectMapper, JsonNode, JavaTimeModule
Integration library: khai báo jackson-core ở một version khác
```

Có thể xử lý theo các bước:

1. Chạy dependency tree hoặc `dependencyInsight` để xác định version cuối của `jackson-core`, `jackson-databind`, `jackson-annotations` và `jackson-datatype-jsr310`.
2. Xác định framework starter đang quản lý BOM nào và integration library yêu cầu version nào.
3. Kiểm tra source imports để biết ứng dụng đang dùng databind, tree model và Java Time module; không thêm module khác nếu không có nhu cầu.
4. Nếu các artifact lệch nhau, chọn một bộ version được BOM quản lý và xác minh integration library tương thích.
5. Chạy test đọc/ghi ngày giờ, tree model và DTO, sau đó kiểm tra lại runtime dependency graph.

Nếu muốn chuyển sang Jackson 3, việc Java 17 đáp ứng yêu cầu runtime mới chỉ giải quyết một điều kiện. Framework starter, integration library, import và module vẫn phải được xác nhận tương thích trước khi đổi BOM.

## 17. Checklist kỹ thuật trước khi chốt dependency

Trước khi merge thay đổi dependency Jackson, có thể dùng danh sách sau để ghi nhận quyết định:

- [ ] Đã xác định major line dự kiến sử dụng.
- [ ] JDK của build và production đáp ứng yêu cầu của dòng đó.
- [ ] Framework/starter và thư viện tích hợp hỗ trợ dòng đã chọn.
- [ ] Đã xác định BOM hoặc cơ chế quản lý version trung tâm.
- [ ] Core, databind, annotations và module cần thiết được căn chỉnh.
- [ ] Đã phân biệt dependency trực tiếp với dependency bắc cầu.
- [ ] Đã tìm các package/API Jackson được dùng trong source và cấu hình.
- [ ] Đã kiểm tra dependency graph của compile/runtime/test configuration cần thiết.
- [ ] Đã kiểm tra module được đăng ký qua framework hoặc service loader.
- [ ] Đã chạy test cho các hợp đồng JSON quan trọng.
- [ ] Đã kiểm tra classpath của artifact/container được triển khai.

## 18. Kết luận về cách xác định

Để xác định đúng dòng Jackson, hãy bắt đầu từ JDK và framework mà ứng dụng phải tương thích, sau đó kiểm tra BOM và dependency graph để biết version thực tế được resolve. Để xác định đúng phạm vi API, hãy xem mã nguồn và cấu hình đang sử dụng `core`, `databind`, annotation, datatype hay dataformat nào, đồng thời tính đến các module được framework đăng ký gián tiếp.

Jackson 2.x và 3.x cần được quản lý như hai major line có ranh giới tương thích riêng. Trong mỗi dòng, dùng BOM phù hợp để căn chỉnh các artifact, khai báo đúng module cần thiết và kiểm tra dependency graph sau mỗi thay đổi. Khi chuyển major, kết hợp migration guide với test hợp đồng JSON và xác nhận runtime classpath sau đóng gói. Như vậy, quyết định phiên bản phản ánh đúng nền tảng mà ứng dụng chạy trên và API mà ứng dụng thực sự sử dụng.
