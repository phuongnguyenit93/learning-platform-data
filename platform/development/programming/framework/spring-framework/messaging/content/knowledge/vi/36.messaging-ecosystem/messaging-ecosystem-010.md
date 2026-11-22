# Tra cứu Javadoc, tài liệu theo phiên bản và thay đổi API khi nâng cấp Spring

## Mục tiêu

Khi sử dụng Spring, một câu trả lời đúng cho phiên bản mới nhất chưa chắc đúng với ứng dụng đang chạy. Một phương thức có thể chỉ xuất hiện từ một minor release, bị đánh dấu deprecated ở phiên bản khác, đổi chữ ký hoặc bị loại bỏ trong major release. Cấu hình cũng có thể giữ nguyên tên nhưng thay đổi hành vi hoặc giá trị mặc định.

Vì vậy, tra cứu API và nâng cấp Spring cần bắt đầu từ **phiên bản thực sự được resolve trong dự án**, sau đó đối chiếu Javadoc, Reference Documentation, release notes và migration notes của đúng dòng phiên bản. Bài này đưa ra quy trình có thể lặp lại để tìm một class/method, xác định API còn được hỗ trợ hay không, đánh giá tác động nâng cấp và xác nhận thay đổi bằng build/test.

## 1. Phân biệt các nguồn tài liệu

Không có một trang tài liệu nào trả lời đầy đủ mọi câu hỏi. Hãy dùng đúng nguồn cho đúng mục đích:

| Nguồn | Dùng để trả lời | Cần kiểm tra |
| --- | --- | --- |
| Javadoc | Class, interface, constructor, method, tham số, kiểu trả về, exception, annotation và quan hệ kế thừa | Đúng artifact và đúng version |
| Reference Documentation | Cách dùng, cấu hình, lifecycle, semantics và các pattern được Spring hỗ trợ | Chọn đúng phiên bản trong bộ chọn tài liệu |
| Release Notes / What's New | API mới, thay đổi hành vi, deprecation, removal, baseline và thay đổi mặc định | Đọc tất cả release nằm giữa version nguồn và version đích |
| Upgrade / Migration Notes | Việc cần làm khi chuyển từ một generation hoặc minor line sang line khác | Theo đúng điểm xuất phát của dự án |
| JAR và source JAR | Chữ ký thực tế của dependency đã resolve và cách implementation hoạt động | Dùng đúng file artifact/version trong classpath |
| Issue / pull request của dự án | Lý do thiết kế hoặc ngữ cảnh của một thay đổi cụ thể | Dùng để bổ sung, không thay thế tài liệu API công khai |

**Javadoc là hợp đồng API ở cấp Java.** Reference Documentation giải thích cách áp dụng API trong một kịch bản. Release notes giải thích điều đã thay đổi giữa các bản phát hành. Source code giúp làm rõ implementation khi cần, nhưng chi tiết private hoặc package nội bộ không phải cam kết tương thích.

## 2. Xác định phiên bản Spring thực sự đang chạy

Đừng bắt đầu bằng cách tìm trên web một tên class rồi lấy trang đầu tiên. Trước tiên, xác định dependency đang được build và chạy.

Spring Framework được chia thành nhiều artifact, ví dụ:

| Package thường gặp | Artifact Maven |
| --- | --- |
| `org.springframework.core`, `org.springframework.util` | `spring-core` |
| `org.springframework.context`, `org.springframework.beans` | `spring-context`, `spring-beans` |
| `org.springframework.messaging` | `spring-messaging` |
| `org.springframework.jms` | `spring-jms` |
| `org.springframework.web` | `spring-web` |
| `org.springframework.web.servlet` | `spring-webmvc` |
| `org.springframework.web.reactive` | `spring-webflux` |
| `org.springframework.test` | `spring-test` |

Package name gợi ý module nhưng không phải lúc nào cũng đủ để xác định dependency. Hãy kiểm tra class thuộc artifact nào bằng Javadoc, package documentation hoặc dependency tree.

### Maven

Xem các Spring module đang được resolve:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework
~~~

Xem POM sau khi áp dụng parent/BOM và các profile:

~~~bash
./mvnw help:effective-pom
~~~

Nếu cần biết vì sao một phiên bản được chọn, xem cây dependency đầy đủ và kiểm tra dependency management, exclusion, profile và version override. Dependency khai báo trong POM có thể không phải version cuối cùng trên runtime classpath.

### Gradle

Liệt kê dependency của compile classpath:

~~~bash
./gradlew dependencies --configuration compileClasspath
~~~

Xem lý do Gradle chọn một module cụ thể:

~~~bash
./gradlew dependencyInsight --dependency spring-messaging --configuration runtimeClasspath
~~~

Lặp lại với `spring-core`, `spring-context`, `spring-jms` hoặc module liên quan đến API cần tra cứu. Nếu compile classpath và runtime classpath khác nhau, hãy kiểm tra cả hai.

### Kiểm tra version ở runtime

Có thể in version do `spring-core` cung cấp:

~~~java
import org.springframework.core.SpringVersion;

public class SpringVersionProbe {

    public static void main(String[] args) {
        System.out.println(
                "Spring Framework: " + SpringVersion.getVersion());
    }
}
~~~

Kết quả phụ thuộc JAR đang được nạp. Ví dụ, nếu runtime dùng Spring Framework 6.2.19, kết quả sẽ là:

~~~text
Spring Framework: 6.2.19
~~~

Đây là tín hiệu hữu ích để chẩn đoán classpath, nhưng `SpringVersion` lấy version từ Spring Core. Nó không chứng minh tất cả Spring module đều cùng version. Dùng dependency tree để kiểm tra toàn bộ nhóm artifact.

### Nếu dự án dùng Spring Boot hoặc Spring Cloud

Spring Boot quản lý một tập hợp phiên bản Spring Framework và dependency tương thích thông qua dependency management. Spring Cloud cũng có release train và ma trận tương thích riêng.

- Nếu dùng Spring Boot, trước tiên xác định version Boot và các version Spring mà BOM của Boot quản lý.
- Nếu dùng Spring Cloud, kiểm tra release train tương thích với Spring Boot đang chọn.
- Tránh nâng riêng `spring-core`, `spring-messaging` hoặc `spring-context` lên một version khác với phần còn lại của Framework nếu không có lý do và kiểm thử tương thích rõ ràng.
- Nếu dùng Spring Framework thuần, có thể quản lý các module cùng version bằng `spring-framework-bom`.

Ví dụ BOM cho ứng dụng dùng Spring Framework trực tiếp:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-framework-bom</artifactId>
            <version>${spring-framework.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Khi dùng Spring Boot parent/BOM, hãy theo dependency management của Boot thay vì thêm một BOM Framework độc lập làm lệch các version mà Boot đã kiểm thử cùng nhau.

## 3. Chọn đúng Reference Documentation theo phiên bản

Trang Reference Documentation hiện hành thường được truy cập qua:

- Current: https://docs.spring.io/spring-framework/reference/
- Dòng 6.2: https://docs.spring.io/spring-framework/reference/6.2/
- Dòng 7.0: https://docs.spring.io/spring-framework/reference/7.0/

Trang chủ có bộ chọn phiên bản và phân biệt Stable, Preview, Snapshot. Khi tra cứu ứng dụng production, chọn đúng stable line tương ứng với dependency đã resolve. Snapshot, milestone và release candidate hữu ích khi đánh giá trước, nhưng không đại diện cho API của bản GA.

Một trang có chữ “current” có thể thay đổi theo thời gian. Nếu dự án đang dùng 6.2.x, một hướng dẫn hiện hành cho 7.0.x có thể mô tả API hoặc baseline mà dự án chưa có. Hãy so sánh cùng một trang ở hai phiên bản khi đánh giá nâng cấp.

Reference Documentation đặc biệt hữu ích để hiểu:

- API được dùng trong lifecycle nào và component nào tạo nó.
- Cấu hình Java, XML hoặc property nào được hỗ trợ.
- Default behavior, transaction boundary, threading và error handling.
- Các điều kiện khi tích hợp với Servlet container, broker, database hoặc reactive runtime.
- Pattern được Spring khuyến nghị thay cho API cũ.

Không suy ra một method tồn tại chỉ từ một đoạn code trong blog. Tìm class và chữ ký trong Javadoc của đúng version trước khi áp dụng.

## 4. Mở Javadoc đúng artifact và đúng version

Javadoc của Spring Framework được xuất bản theo version. Dùng URL có version rõ ràng:

~~~text
https://docs.spring.io/spring-framework/docs/{version}/javadoc-api/
~~~

Thay `{version}` bằng version đã xác định từ dependency tree, ví dụ `6.2.19`. Có thể tra cứu một class cụ thể bằng cách nối package path và tên class:

~~~text
https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/messaging/Message.html
~~~

Đường dẫn Javadoc current có dạng:

~~~text
https://docs.spring.io/spring-framework/docs/current/javadoc-api/
~~~

Dùng `current` để khám phá API hiện hành; dùng URL versioned để quyết định code có biên dịch với dependency của dự án hay không.

Trong Javadoc, có thể đi theo các cấp:

1. **Overview / All Classes:** tìm package hoặc tên class khi chưa biết vị trí.
2. **Package Summary:** hiểu nhóm API, related packages và class trong package.
3. **Class / Interface Page:** xem declaration, superclass, implemented interfaces, constructor và method.
4. **Method Detail:** kiểm tra chính xác overload, kiểu tham số, generic, kiểu trả về, exception và mô tả.
5. **Deprecated List:** rà soát các API đã bị đánh dấu deprecated.
6. **Index / Search:** tìm tên method, constant, annotation hoặc class trên toàn bộ Javadoc.

Ví dụ, với Spring Messaging, tìm `org.springframework.messaging.Message` trong artifact `spring-messaging`; với listener JMS, tra `org.springframework.jms.listener.DefaultMessageListenerContainer` trong artifact `spring-jms`. Không tìm một class chỉ theo tên ngắn như `Message` vì có nhiều package và abstraction trùng tên.

## 5. Đọc một trang Javadoc có hệ thống

Khi mở trang class, đừng chỉ đọc phần mô tả đầu trang. Kiểm tra các phần sau:

- **Declaration:** class/interface/record/enum, generic parameter, modifier và các interface được implement.
- **Since:** version đầu tiên API xuất hiện. Nếu version dự án thấp hơn, API đó có thể chưa tồn tại.
- **Constructor Summary:** cách tạo object, constructor nào public và constructor nào deprecated.
- **Method Summary:** danh sách method, kiểu trả về, tên và tham số.
- **Method Detail:** chữ ký đầy đủ, điều kiện đầu vào, kết quả, side effect, exception và thread/lifecycle contract nếu có.
- **Inherited Methods:** method có thể đến từ superclass hoặc interface; kiểm tra nơi khai báo gốc.
- **Nullability:** annotation nullness, kiểu nullable/non-null và khác biệt giữa Java/Kotlin.
- **See Also:** API liên quan, replacement hoặc abstraction cấp cao hơn.

Với một method overload, phải đối chiếu toàn bộ chữ ký. Hai method cùng tên có thể khác kiểu tham số, generic, overload varargs, return type hoặc semantics. Một ví dụ trên mạng gọi được method không có nghĩa overload đó tồn tại trong version của bạn.

Các tag Javadoc có ý nghĩa:

| Tag / annotation | Cách đọc |
| --- | --- |
| `@since` | API được giới thiệu từ version nào |
| `@deprecated` | Lý do không nên tiếp tục dùng và replacement nếu có |
| `@Deprecated(since = "...")` | Java compiler/IDE có thể cảnh báo; `since` ghi version đánh dấu deprecated |
| `@Deprecated(forRemoval = true)` | API được đánh dấu dự kiến loại bỏ; cần lập kế hoạch thay thế |
| `@throws` | Điều kiện có thể phát sinh exception |
| `@Nullable`, `@NonNull` hoặc JSpecify | Hợp đồng nullness, có thể ảnh hưởng Java và Kotlin |

Không phải API deprecated nào cũng bị loại bỏ ngay ở bản tiếp theo. Ngược lại, major release có thể loại bỏ API đã deprecated từ nhiều năm trước. Hãy đọc release notes để biết trạng thái thực tế.

## 6. Tìm API theo class, package và method

Khi đã có câu hỏi kỹ thuật, hãy biến nó thành truy vấn chính xác:

1. Ghi tên đầy đủ, ví dụ `org.springframework.messaging.rsocket.RSocketRequester`.
2. Xác định artifact chứa class, ví dụ `spring-messaging`.
3. Ghi version hiện tại và version dự kiến nâng cấp.
4. Mở Javadoc cho cả hai version.
5. Tìm đúng method và overload, không chỉ tên class.
6. Đối chiếu với Reference Documentation của cùng dòng version.
7. Tìm release note hoặc migration note đề cập tới API, module hoặc behavior đó.

Khi tìm trên web, dùng tên đầy đủ và giới hạn domain chính thức:

~~~text
site:docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/
"org.springframework.messaging.rsocket.RSocketRequester"
~~~

Hoặc tìm method cụ thể:

~~~text
site:docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/
"setValidator" "RSocketMessageHandler"
~~~

Kết quả tìm kiếm chỉ giúp tìm đúng trang. Sau đó phải mở Javadoc và đọc chữ ký đầy đủ. Snippet của search engine có thể cắt mất overload, version hoặc ngữ cảnh.

Nếu API thuộc Spring Integration, Spring AMQP, Spring Kafka, Spring Security hoặc Spring Cloud, dùng tài liệu và Javadoc của **chính project đó**. Spring Framework Javadoc không mô tả toàn bộ API của các project trong hệ sinh thái.

## 7. Kiểm tra API deprecated, replacement và removal

Khi gặp một cảnh báo deprecated, ghi lại bốn thông tin:

1. API nào bị deprecated: class, constructor, method, field hay package.
2. Version bắt đầu deprecated và có `forRemoval` hay không.
3. Lý do: API cũ, semantics không còn phù hợp, dependency ngừng hỗ trợ hay có abstraction tốt hơn.
4. Replacement được đề xuất và các khác biệt khi chuyển đổi.

Đừng thay một method deprecated bằng method có tên gần giống mà không đọc Javadoc của replacement. Replacement có thể thay đổi lifecycle, threading, transaction, exception hoặc default behavior.

Các dấu hiệu cần rà soát:

- IDE hiển thị gạch ngang hoặc cảnh báo deprecated.
- Compiler báo `[deprecation]`.
- Release notes ghi “removed”, “no longer supported”, “replaced by” hoặc “breaking change”.
- API nằm trong package nội bộ như `*.support`, `*.internal` hoặc implementation class không được tài liệu hóa là extension point.
- Code phụ thuộc vào protected field/method của class mà tài liệu nói đã đổi hoặc loại bỏ.

API public vẫn có thể bị thay đổi qua major release. API internal có rủi ro cao hơn vì không được cam kết ổn định. Ưu tiên interface và extension point công khai được tài liệu hóa.

## 8. Đọc Release Notes và Migration Notes theo đúng đường nâng cấp

Release notes không chỉ là danh sách tính năng mới. Đây là nơi tìm các thay đổi mà Javadoc của một method riêng lẻ có thể không nói rõ, ví dụ:

- Baseline JDK, Jakarta EE, Servlet, JPA, Validation hoặc Kotlin.
- API, class, package hoặc integration bị loại bỏ.
- Cấu hình mặc định và behavior thay đổi.
- Thay đổi autowiring, generic matching, nullability hoặc parameter-name discovery.
- Thay đổi trong test framework, transaction hoặc runtime container.
- Dependency bên thứ ba được nâng version hoặc không còn được hỗ trợ.

Quy tắc quan trọng: nếu nâng từ một major line cũ, hãy đọc **mọi bước trung gian**. Ví dụ nâng từ 5.3 lên 7.0 cần xem thay đổi 6.0, 6.1, 6.2 và 7.0. Chỉ đọc release note 7.0 có thể bỏ sót thay đổi đã xảy ra từ 6.0 hoặc 6.1.

Nguồn chính thức cần mở:

- Spring Framework Versions: https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-Versions
- Upgrading to Spring Framework 6.x: https://github.com/spring-projects/spring-framework/wiki/Upgrading-to-Spring-Framework-6.x
- Spring Framework 7.0 Release Notes: https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-7.0-Release-Notes
- Spring Framework What's New: liên kết từ wiki và Reference Documentation.

Trang Supported Versions cho biết nhánh nào còn được hỗ trợ và baseline của từng generation. Hãy kiểm tra lại trang này tại thời điểm lập kế hoạch vì lịch hỗ trợ có thể thay đổi.

## 9. Ví dụ thay đổi từ Spring Framework 6.2 lên 7.0

Một số ví dụ dưới đây cho thấy vì sao cần đọc cả API reference lẫn migration notes. Đây là các ví dụ tiêu biểu, không phải danh sách đầy đủ.

### Baseline nền tảng

Spring Framework 7.0 giữ JDK 17 baseline nhưng chuyển sang Jakarta EE 11 baseline. Các thay đổi nền tảng bao gồm Servlet 6.1, JPA 3.2, Bean Validation 3.1, Kotlin 2.2, Netty 4.2 và JUnit 6. Trước khi nâng Framework, kiểm tra Servlet container, provider JPA/Validation, test libraries và các thư viện tích hợp có tương thích không.

### Namespace javax và jakarta

Spring Framework 7 không còn hỗ trợ các annotation từ `javax.annotation` và `javax.inject`. Ví dụ `@javax.annotation.Resource`, `@javax.annotation.PostConstruct` và `@javax.inject.Inject` cần chuyển sang package Jakarta tương ứng nếu ứng dụng dùng chúng.

Đây là thay đổi namespace ở dependency và source code. Không giải quyết bằng cách chỉ nâng version Spring mà vẫn giữ API Java EE cũ.

### HttpHeaders và MultiValueMap

Trong Spring Framework 7, `HttpHeaders` không còn implement contract `MultiValueMap`. Code đang gán `HttpHeaders` vào biến `MultiValueMap`, ép kiểu hoặc gọi các method dựa vào contract đó có thể không còn biên dịch. Migration notes mô tả các method fallback đã deprecated; hãy chuyển sang API chuyên biệt của `HttpHeaders` theo Javadoc version đích.

### ListenableFuture

Một số API `ListenableFuture` của Spring đã bị loại bỏ trong Spring Framework 7, với hướng thay thế là `CompletableFuture`. Khi nâng cấp, tìm cả import, kiểu trả về, callback và adapter liên quan. Chuyển kiểu đơn thuần có thể chưa đủ nếu code dựa vào callback registration hoặc cách xử lý cancellation.

### Thay đổi behavior không nhất thiết đổi chữ ký

Từ Spring Framework 7.0.8, SpEL giới hạn số operation trong một lần expression evaluation ở mức mặc định 10.000. Một expression rất phức tạp có thể bắt đầu ném exception dù code vẫn compile. Đây là ví dụ cho thấy nâng cấp cần có kiểm thử behavior và dữ liệu thực tế, không chỉ kiểm tra API signature.

## 10. Phân biệt source, binary và behavioral compatibility

Một nâng cấp có thể thành công ở một tầng nhưng thất bại ở tầng khác:

| Loại tương thích | Câu hỏi | Ví dụ lỗi |
| --- | --- | --- |
| Source compatibility | Source code có biên dịch với API mới không? | Method bị xóa hoặc tham số đổi kiểu |
| Binary compatibility | Bytecode đã biên dịch có chạy với JAR mới không? | `NoSuchMethodError`, `NoSuchFieldError`, `AbstractMethodError` |
| Behavioral compatibility | API còn đó nhưng kết quả/hành vi có đổi không? | Default timeout, ordering, transaction hoặc parser behavior đổi |
| Configuration compatibility | Property/XML/Java config cũ còn được hỗ trợ không? | Property bị xóa hoặc default thay đổi |
| Ecosystem compatibility | Các module và thư viện liên quan có tương thích không? | Spring Boot/Cloud, broker client hoặc Servlet container không tương thích |

Một project có thể compile nhưng lỗi runtime vì classpath có hai version Spring khác nhau. Một project có thể chạy nhưng behavior đổi vì một default hoặc giới hạn mới. Vì vậy cần cả dependency convergence, compilation, unit/integration test và smoke test.

## 11. So sánh API giữa hai version

Khi cần xác định một API thay đổi thế nào, tạo bảng so sánh cụ thể:

| Hạng mục | Version hiện tại | Version đích |
| --- | --- | --- |
| Artifact/version | Ví dụ `spring-messaging:6.2.x` | Ví dụ `spring-messaging:7.0.x` |
| FQCN | Tên đầy đủ class/interface | Tên đầy đủ class/interface |
| Method signature | Kiểu trả về, tên, tham số, generic | Chữ ký mới |
| Status | Public / deprecated / internal | Public / deprecated / removed |
| Since / Deprecated | Tag và version | Tag và version |
| Replacement | API được khuyến nghị | API thay thế |
| Behavior | Nullability, threading, transaction, defaults | Khác biệt cần xử lý |
| Validation | Build/test hiện tại | Test chứng minh tương thích |

Đừng chỉ so sánh tên method. Kiểm tra cả:

- Kiểu tham số và kiểu trả về.
- Generic bound, wildcard, varargs và overload resolution.
- Checked/unchecked exceptions và exception contract.
- Nullability và Kotlin null-safety.
- Interface/superclass, default method và visibility.
- Package, module và artifact chứa class.
- Side effect, lifecycle, threading, transaction và default value.

Với thay đổi lớn hoặc nhiều module, có thể dùng công cụ API/binary compatibility như japicmp hoặc Revapi để phát hiện khác biệt giữa hai JAR. Kết quả của công cụ là đầu vào cho review; vẫn phải đọc release notes và kiểm tra behavior.

## 12. Dùng source JAR và javap khi Javadoc chưa đủ

Nếu Javadoc không giải thích đủ chi tiết, tải source JAR đúng version qua Maven/Gradle hoặc chức năng Download Sources của IDE. Source giúp hiểu implementation, nhưng không nên phụ thuộc vào private field hoặc logic nội bộ khi có API công khai tương đương.

Có thể xem chữ ký bytecode của class từ JAR thực tế bằng `javap`:

~~~bash
javap -classpath path/to/spring-messaging-6.2.x.jar org.springframework.messaging.Message
~~~

`javap` hữu ích khi:

- IDE không tìm được source.
- Cần xác nhận method thực sự có trong JAR runtime.
- Có khác biệt giữa Javadoc hiển thị và dependency đã resolve.
- Điều tra lỗi linkage như `NoSuchMethodError`.

`javap` không thay thế Javadoc: nó không cung cấp đầy đủ semantics, migration notes, nullness contract hay lý do thiết kế. Không dùng source của nhánh main để kết luận API có trong một release đã phát hành.

## 13. Quy trình nâng cấp có kiểm soát

### Bước 1 — Chụp baseline

Ghi lại:

- Spring Boot, Spring Framework và Spring Cloud version.
- Java toolchain/JDK dùng để compile và chạy.
- Spring module đang resolve.
- Jakarta EE/Servlet/JPA/Validation provider.
- Broker, database driver, HTTP client và các integration library.
- Test suite hiện tại và các warning đã tồn tại.

Lưu dependency tree hoặc lockfile làm bằng chứng trước nâng cấp.

### Bước 2 — Chọn version đích

Chọn version dựa trên supported-version policy, yêu cầu bảo mật, JDK và tương thích hệ sinh thái. Nếu dùng Boot/Cloud, chọn release train tương thích trước rồi để BOM quản lý các dependency liên quan. Không nâng riêng một module Spring theo cảm tính.

### Bước 3 — Đọc migration notes

Đọc từ version nguồn tới version đích, bao gồm mọi major/minor release ở giữa. Tìm các từ khóa `removed`, `deprecated`, `breaking`, `baseline`, `behavior`, `default`, `no longer supported`.

Tạo danh sách API và cấu hình cần sửa trước khi thay dependency. Đánh dấu thay đổi nào là compile-time, runtime, configuration hay behavioral.

### Bước 4 — Tìm và thay API deprecated

Bật compiler warnings và xử lý deprecation trong phạm vi nâng cấp:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <showWarnings>true</showWarnings>
        <compilerArgs>
            <arg>-Xlint:deprecation</arg>
        </compilerArgs>
    </configuration>
</plugin>
~~~

Với Gradle Groovy DSL:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add("-Xlint:deprecation")
}
~~~

Không xóa warning bằng cách suppress hàng loạt. Với từng API deprecated, ghi replacement và lý do chưa thể thay nếu cần trì hoãn.

### Bước 5 — Nâng dependency theo BOM

Cập nhật parent/BOM hoặc release train đã chọn. Sau đó kiểm tra dependency tree để phát hiện Spring module bị lệch version, dependency cũ bị kéo bắc cầu hoặc exclusion làm mất module cần thiết.

### Bước 6 — Compile và kiểm thử

Chạy build sạch với JDK mục tiêu:

~~~bash
./mvnw clean verify
~~~

Hoặc:

~~~bash
./gradlew clean test
~~~

Bổ sung test theo rủi ro của ứng dụng: application context startup, messaging broker, listener concurrency, transaction, serialization, WebSocket/RSocket, security, database migration và external client. Nếu thay đổi behavior, tạo test mô tả behavior mong muốn thay vì chỉ sửa code cho compile.

### Bước 7 — Kiểm tra runtime

Sau khi build thành công:

- Kiểm tra dependency tree runtime và classpath thực tế.
- Chạy smoke test trên môi trường gần production.
- Đọc log deprecation/removal và warning lúc startup.
- Kiểm tra actuator/health, broker connection, listener container và transaction.
- Theo dõi error rate, latency, queue backlog và resource usage sau rollout.

Không coi việc compile thành công là bằng chứng nâng cấp hoàn tất.

## 14. Chẩn đoán lỗi thường gặp khi tra cứu hoặc nâng cấp

| Triệu chứng | Nguyên nhân có thể | Cách điều tra |
| --- | --- | --- |
| IDE không tìm thấy method | Method chưa tồn tại ở version đang dùng hoặc import sai class | Mở Javadoc đúng version và dependency tree |
| `cannot find symbol` | API/package bị xóa, đổi tên hoặc dependency không có | Kiểm tra release notes, FQCN và artifact |
| `NoSuchMethodError` | Runtime nạp version khác với version lúc compile | Kiểm tra runtime dependency tree và duplicate JAR |
| `ClassNotFoundException` / `NoClassDefFoundError` | Thiếu artifact hoặc package đã chuyển | Kiểm tra dependency, namespace và module mới |
| `AbstractMethodError` | Interface/class version không đồng bộ hoặc implementation chưa tương thích | Kiểm tra tất cả module liên quan và dependency convergence |
| Compile được nhưng test behavior sai | Semantics/default/configuration đã thay đổi | Đọc migration notes và viết regression test |
| Javadoc không có class đang dùng | Sai artifact, sai version hoặc class là internal | Tìm package summary và source JAR của đúng artifact |
| Nhiều kết quả search khác nhau | Tài liệu current, snapshot, blog cũ hoặc version khác | Giới hạn domain và version, ưu tiên docs chính thức |

## 15. Ghi lại kết quả tra cứu để team dùng lại

Với API quan trọng hoặc một lần nâng cấp lớn, ghi một bản ghi ngắn trong PR hoặc migration document:

| Trường | Nội dung cần ghi |
| --- | --- |
| Câu hỏi | API/hành vi nào cần xác minh |
| Version nguồn/đích | Version đã resolve và version dự kiến |
| Artifact và FQCN | Module Maven và tên class đầy đủ |
| Javadoc | Link versioned của class/method |
| Reference / Release note | Link trang hướng dẫn và mục thay đổi |
| Kết luận | Còn hỗ trợ, deprecated, removed hoặc behavior changed |
| Hành động | Replacement, thay cấu hình hoặc giữ nguyên |
| Bằng chứng | Build, test, runtime check và kết quả |

Ghi version cụ thể thay vì chỉ ghi “theo tài liệu Spring”. Sau này khi dependency được nâng tiếp, người đọc có thể xác định kết luận được đưa ra trên version nào.

## 16. Lỗi tra cứu thường gặp

- **Dùng Javadoc current cho project cũ:** dẫn đến gọi method chưa tồn tại hoặc áp dụng API mới.
- **Chỉ đọc một trang class:** bỏ sót package-level contract, superclass, overload hoặc behavior trong Reference Documentation.
- **Chỉ đọc release notes của version đích:** bỏ qua removal từ các release trung gian.
- **Nhầm Spring Boot version với Spring Framework version:** Boot và Framework có số version khác nhau; cần xem BOM đã resolve.
- **Nâng một Spring module riêng lẻ:** tạo classpath không đồng nhất giữa `spring-core`, `spring-context`, `spring-messaging`, `spring-jms` và các module khác.
- **Tin blog hoặc snippet cũ:** ví dụ có thể đúng cho một version cũ hoặc một provider cụ thể.
- **Dựa vào implementation nội bộ:** code chạy hôm nay nhưng không có cam kết ổn định.
- **Chỉ sửa compile error:** bỏ qua thay đổi transaction, threading, ordering, nullability hoặc configuration.
- **Không lưu bằng chứng:** team sau phải lặp lại quá trình tra cứu và dễ đưa ra kết luận khác.

## 17. Checklist tra cứu và nâng cấp

- [ ] Đã xác định version Spring Framework thực tế từ dependency resolution.
- [ ] Đã xác định artifact chứa class/API cần dùng.
- [ ] Đã mở Javadoc đúng version, không chỉ trang current hoặc snapshot.
- [ ] Đã đọc class declaration, method overload, generic, nullability và exception contract.
- [ ] Đã kiểm tra `@since`, `@Deprecated`, `forRemoval` và Deprecated List.
- [ ] Đã đọc Reference Documentation đúng dòng version.
- [ ] Đã đọc release notes và migration notes của tất cả version trung gian.
- [ ] Đã kiểm tra Spring Boot/Cloud compatibility và BOM management nếu dự án sử dụng.
- [ ] Đã rà soát baseline JDK, Jakarta EE, container và third-party provider.
- [ ] Đã kiểm tra source/API diff khi thay đổi có rủi ro cao.
- [ ] Đã compile bằng JDK mục tiêu và xử lý deprecation warning.
- [ ] Đã chạy unit, integration và smoke tests theo các behavior bị ảnh hưởng.
- [ ] Đã xác nhận runtime classpath không có Spring module lệch version.
- [ ] Đã lưu link tài liệu và bằng chứng kiểm thử trong PR/migration record.

## Tài liệu tham khảo chính thức

- [Spring Framework Reference Documentation](https://docs.spring.io/spring-framework/reference/): tài liệu hiện hành và bộ chọn version.
- [Spring Framework Reference 6.2](https://docs.spring.io/spring-framework/reference/6.2/): ví dụ tài liệu theo một dòng version cụ thể.
- [Spring Framework Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/): API reference hiện hành; thay `current` bằng version cụ thể khi kiểm tra dự án cũ.
- [Spring Framework Versions](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-Versions): supported versions, JDK range và Jakarta EE baseline.
- [Upgrading to Spring Framework 6.x](https://github.com/spring-projects/spring-framework/wiki/Upgrading-to-Spring-Framework-6.x): các thay đổi khi nâng từ generation 5.x.
- [Spring Framework 7.0 Release Notes](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-7.0-Release-Notes): nâng từ 6.2, baseline, removed APIs và breaking changes.
- [Spring Framework Documentation Update](https://spring.io/blog/2023/05/11/spring-framework-reference-documentation-update/): cách chọn phiên bản Reference Documentation và cấu trúc tài liệu.
- [Spring Boot Reference Documentation](https://docs.spring.io/spring-boot/reference/): dependency management và cấu hình theo version Boot.
- [Spring Cloud Documentation](https://docs.spring.io/spring-cloud/reference/): tài liệu và compatibility guidance của Spring Cloud release trains.

