# Vì sao Spring cần xử lý trước khi biên dịch thành native image?

## 1. Vấn đề gốc: Spring linh hoạt ở runtime, native image cần biết trước nhiều thứ

Mục tiêu của **SPRING_BOOT_NATIVE_IMAGE** là biên dịch ứng dụng Spring Boot thành GraalVM Native Image bằng **Spring AOT (Ahead-of-Time)**, sau đó đánh giá tốc độ khởi động, mức dùng bộ nhớ, tính tương thích, quy trình build Maven/Gradle và khả năng đóng gói, vận hành. Để làm được điều đó, cần trả lời một câu hỏi trước tiên: **Tại sao không đưa thẳng JAR Spring Boot vào GraalVM Native Image để biên dịch?**

Trên JVM, Spring có thể khám phá và lắp ghép ứng dụng rất linh hoạt khi khởi động. Ví dụ, Spring Boot thường dựa vào:

- **Classpath scanning** để tìm các lớp đánh dấu `@Component`, `@Service`, `@Repository`, `@Controller`.
- **Bean definition và dependency injection** để xác định bean nào cần được tạo, chọn constructor và kết nối các phụ thuộc.
- **Điều kiện cấu hình** như `@ConditionalOnClass`, `@ConditionalOnProperty`, profile và auto-configuration để quyết định cấu trúc ứng dụng.
- **Reflection** để tìm constructor, field, method, binding thuộc tính hoặc tương tác với framework.
- **Proxy** (JDK dynamic proxy hoặc proxy dựa trên subclass) để triển khai một số cơ chế như transaction, AOP và các chức năng hạ tầng.
- **Resource discovery** để đọc cấu hình, template, schema hay dữ liệu đóng gói trên classpath.

Với ứng dụng chạy trên JVM, nhiều quyết định được thực hiện lúc chương trình bắt đầu chạy. JVM có thể nạp lớp, đọc metadata và gọi method qua reflection khi cần.

**GraalVM Native Image** tiếp cận theo hướng khác: trình biên dịch phân tích ứng dụng theo mô hình **closed world**. Ở thời điểm build, công cụ cần xác định đủ các lớp, đường gọi và hành vi truy cập động sẽ xuất hiện khi chạy. Sau đó nó tạo executable mã máy cho một hệ điều hành và kiến trúc cụ thể. Nó không thể giả định có một classloader JVM đầy đủ để khám phá bất kỳ lớp mới nào trong tương lai.

Vì vậy, một ứng dụng Spring Boot vẫn có thể chạy bình thường trên JVM nhưng gặp lỗi khi build hoặc chạy native: **những thao tác mà JVM khám phá được lúc chạy có thể không được trình phân tích tĩnh nhận diện và đưa vào executable**.

### Ví dụ nhỏ: kiểu truy cập không nhìn rõ qua mã nguồn

~~~java
String className = environment.getProperty("app.report.formatter");
Class<?> formatterClass = Class.forName(className);
Object formatter = formatterClass.getDeclaredConstructor().newInstance();
~~~

Tên lớp được lấy từ cấu hình. Chỉ nhìn vào mã bytecode, Native Image không nhất thiết suy ra được class, constructor hoặc những phần tử cần giữ lại. Với JVM, việc này có thể thành công khi lớp có trên classpath; với native executable, truy cập qua reflection có thể cần **reachability metadata** được đăng ký từ trước.

Không chỉ reflection: nếu chương trình chọn template theo tên trong cấu hình, hoặc tạo proxy cho một tập interface được suy ra động, trình biên dịch cũng có thể cần thêm thông tin.

## 2. Spring AOT giải quyết phần nào của bài toán?

**Spring AOT là quá trình Spring phân tích và chuẩn bị ứng dụng ở thời điểm build**, chuyển các công việc vốn có thể thực hiện ở lúc khởi động sang mã được tạo trước, đồng thời khai báo những kiểu truy cập động cần thiết cho native compilation.

Nó không phải trình biên dịch mã máy và cũng không phải công cụ đóng gói container. Spring AOT hiểu *ngữ nghĩa của Spring*; GraalVM Native Image hiểu bytecode và reachability; Native Build Tools tích hợp quá trình build native vào Maven/Gradle.

| Câu hỏi | Spring AOT đóng góp gì? | GraalVM Native Image làm gì tiếp? |
| --- | --- | --- |
| Bean nào có trong ứng dụng? | Xử lý cấu hình/định nghĩa bean và sinh mã bootstrap tương ứng | Phân tích mã của bootstrap và các nhánh có thể được gọi |
| Cần dùng constructor/method bằng reflection? | Spring và thư viện cung cấp runtime hints; ứng dụng có thể bổ sung hints | Giữ khả năng truy cập được khai báo trong image |
| Có cần JDK dynamic proxy/resource/serialization? | Cung cấp metadata cho các trường hợp đã biết | Sử dụng metadata khi biên dịch, đóng gói |
| Làm sao tạo executable native? | Chuẩn bị mã và metadata | Biên dịch mã máy cho môi trường đích |
| Ai đưa các bước vào Maven/Gradle? | Spring Boot build plugin tích hợp các bước AOT | Native Build Tools gọi và cấu hình trình biên dịch |

Về kỹ thuật, quá trình xử lý trước có thể tận dụng các extension point như `BeanFactoryInitializationAotProcessor` và `BeanRegistrationAotProcessor` để đóng góp mã khởi tạo cho phần hạ tầng/bean tương ứng. Ở góc nhìn người viết ứng dụng, không nhất thiết phải tự dùng các API đó: Spring Framework, Spring Boot và nhiều thư viện tích hợp sẵn đã cung cấp cách xử lý cho các trường hợp phổ biến.

### Chuỗi xử lý ở mức khái niệm

~~~mermaid
flowchart TB
    S["Mã ứng dụng + dependency + cấu hình build"] --> A["Spring AOT phân tích định nghĩa bean và cấu hình Spring"]
    A --> G["Mã Java khởi tạo / đăng ký bean được sinh ra"]
    A --> H["Runtime hints và metadata cần thiết"]
    G --> C["Biên dịch bytecode ứng dụng và mã AOT"]
    H --> N["GraalVM Native Image"]
    C --> N
    N --> E["Executable native theo hệ điều hành / kiến trúc đích"]
    B["Maven / Gradle + plugin Spring Boot + Native Build Tools"] -. "điều phối" .-> A
    B -. "điều phối" .-> N
~~~

Sơ đồ thể hiện mối quan hệ logic; thứ tự task và thư mục sinh mã có thể khác giữa hệ build và phiên bản plugin. Đầu ra AOT là **mã nguồn/mã biên dịch và metadata để dùng trong bước tiếp theo**, chưa phải executable native.

## 3. Phần Spring AOT có thể biết trước

### 3.1. Tạo mã cho bean registration và khởi tạo ApplicationContext

Một ứng dụng đơn giản:

~~~java
@Configuration(proxyBeanMethods = false)
class PaymentConfiguration {
    @Bean
    PaymentService paymentService(PaymentGateway gateway) {
        return new PaymentService(gateway);
    }
}
~~~

Khi chạy JVM truyền thống, Spring cần xử lý cấu hình, lập bean definition, tìm dependency và chuẩn bị logic tạo bean. Trong giai đoạn AOT, Spring có thể phân tích thông tin này và **sinh mã Java thực hiện phần bootstrap/đăng ký bean đã xác định trước**.

Mã sinh ra có thể chứa logic tương đương việc đăng ký bean và gọi factory method. Cần tránh suy luận rằng **Spring AOT tạo sẵn tất cả các instance của bean vào lúc build**. Bean vẫn được tạo khi ứng dụng khởi động theo lifecycle thích hợp; điểm khác biệt là một phần công việc khám phá và thiết lập đã được chuẩn bị sớm.

Hệ quả: lúc native executable bắt đầu chạy, Spring thường phải thực hiện ít công việc phân tích cấu hình hơn, góp phần cải thiện thời gian khởi động.

### 3.2. Xác định cấu hình nào hình thành bean graph

Trong Spring Boot, auto-configuration và các annotation điều kiện quyết định bean có xuất hiện hay không. Ví dụ:

~~~java
@Configuration(proxyBeanMethods = false)
class AuditConfiguration {
    @Bean
    @ConditionalOnProperty(
        prefix = "app.audit",
        name = "enabled",
        havingValue = "true"
    )
    AuditService auditService() {
        return new AuditService();
    }
}
~~~

Khi quá trình AOT xử lý điều kiện liên quan đến bean graph, quyết định có thể được **cố định theo môi trường/cấu hình tại lúc build**. Nếu build native trong trạng thái `app.audit.enabled=false`, không nên giả định rằng chỉ cần đổi thành `true` khi chạy executable là Spring sẽ phát hiện lại cấu hình, tạo bean mới và tái dựng toàn bộ bean graph.

Điều này cần được phân biệt với **giá trị thuộc tính thông thường được đọc khi chạy**, ví dụ địa chỉ dịch vụ, timeout hoặc credential. Không phải mọi thuộc tính của ứng dụng đều bị đóng băng; rủi ro đáng chú ý nằm ở **những giá trị quyết định bean nào được đăng ký hoặc cách cấu trúc ứng dụng được sinh ra**.

Vì vậy, khi ứng dụng có nhiều profile hay feature flag làm thay đổi bean graph, phải xem chúng có được quyết định trong quá trình AOT không. Nếu cần phân phối một binary duy nhất cho nhiều môi trường, hãy thiết kế sao cho phần biến đổi khi chạy nằm ở giá trị cấu hình và logic runtime phù hợp, thay vì phụ thuộc vào việc quét và định nghĩa lại bean sau build.

### 3.3. Sinh và tổng hợp thông tin cho truy cập động

GraalVM có thể phân tích tốt các lời gọi tĩnh rõ ràng:

~~~java
ReportService service = new ReportService();
service.generate();
~~~

Nhưng đối với reflection, proxy và tài nguyên tìm theo tên động, cần có metadata. Spring AOT và các tích hợp liên quan có thể đóng góp thông tin về:

| Loại truy cập | Ví dụ thường gặp | Thông tin cần chuẩn bị |
| --- | --- | --- |
| Reflection | Tạo đối tượng qua `Class.forName`, gọi constructor/method động | Class và thành viên được phép truy cập qua reflection |
| JDK proxy | Proxy cho một tập interface xác định | Danh sách interface của proxy |
| Resource | Đọc template, schema hoặc file trên classpath | Resource hoặc pattern cần đưa vào image |
| Serialization | Framework truy cập kiểu dùng trong serialize/deserialize | Metadata phù hợp với cơ chế serialization |
| Proxy/subclass do Spring sử dụng | AOP, một số kiểu bean infrastructure | Mã/metadata sinh trước hoặc cấu hình cần thiết theo cơ chế proxy cụ thể |

Không phải mọi trường hợp truy cập động đều cần tự viết hints. Nhiều thành phần Spring đã hỗ trợ sẵn. Trách nhiệm của ứng dụng là **bổ sung chính xác các trường hợp chưa được framework hoặc dependency mô tả**.

## 4. Khi thiếu xử lý trước, lỗi xuất hiện như thế nào?

Một ứng dụng có thể build native thành công, mở được cổng HTTP và trả về endpoint đơn giản, nhưng vẫn lỗi khi người dùng thực thi một luồng ít chạy. Chẳng hạn tính năng xuất báo cáo:

1. Người dùng gửi yêu cầu xuất dữ liệu ra định dạng được chọn.
2. Chương trình lấy tên implementation từ cấu hình rồi tạo đối tượng qua reflection.
3. Native executable không có đủ metadata cho constructor cần gọi.
4. Luồng xuất báo cáo thất bại dù build thành công và endpoint health vẫn xanh.

Đó là lý do **build thành công chưa chứng minh ứng dụng đã tương thích native**. Các test phải thực thi những hành vi động quan trọng: binding/serialization, kết nối database, proxy transaction, truy cập resource, điều kiện cấu hình và các thư viện tích hợp.

Nếu ứng dụng thực sự dùng một kiểu class theo tên động, có thể đăng ký runtime hints ở Spring:

~~~java
package com.example.report;

import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(ReportRuntimeHints.class)
class ReportConfiguration {
}

class ReportRuntimeHints implements RuntimeHintsRegistrar {
    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.reflection().registerType(
            CsvReportFormatter.class,
            MemberCategory.INVOKE_DECLARED_CONSTRUCTORS
        );
        hints.resources().registerPattern("report-templates/*.txt");
    }
}

class CsvReportFormatter {
    public CsvReportFormatter() {}
}
~~~

Ví dụ giả định `CsvReportFormatter` là implementation thực tế có trong build, được tạo bằng reflection theo tên lấy từ cấu hình; file như `src/main/resources/report-templates/default.txt` được đọc khi chạy. `@ImportRuntimeHints` giúp Spring đưa thông tin từ registrar vào quá trình AOT. Khi gọi constructor bằng reflection, Native Image cần biết phải giữ khả năng gọi constructor đó; với tài nguyên, cần biết file/pattern nào được đóng gói.

**Không nên dùng hints như cách tự động chữa mọi lỗi.** Chúng không giúp nạp một JAR bất kỳ mới được chép vào thư mục sau khi biên dịch, cũng không tự khai báo mọi method/field của một class. `MemberCategory.INVOKE_DECLARED_CONSTRUCTORS` mô tả nhu cầu constructor; nếu gọi method qua reflection, phải xem xét metadata cho method tương ứng. Thêm quá nhiều hints có thể làm tăng kích thước image và che giấu các phụ thuộc động không cần thiết.

## 5. Những giới hạn AOT buộc ứng dụng phải thiết kế có chủ đích

Spring AOT phù hợp nhất khi cấu trúc ứng dụng có thể xác định tại build time. Cần đặc biệt chú ý những phương thức làm thay đổi cấu trúc Spring sau giai đoạn xử lý trước:

- **Đăng ký bean bằng logic runtime không thể dự đoán**: nếu bean được thêm dựa trên input chỉ có khi chạy, mã AOT có thể không thể chuẩn bị toàn bộ cách tạo bean tương ứng.
- **Tự quét classpath hoặc đọc các plugin JAR thêm vào sau build**: native image không có tính năng khám phá và nạp lớp mới tùy ý như môi trường JVM đầy đủ.
- **Sử dụng reflection/proxy/resource tùy biến**: nếu Spring hoặc thư viện không cung cấp metadata, ứng dụng cần khai báo.
- **Thay đổi profile/điều kiện giữa build và chạy**: có thể làm cấu hình được cố định trong mã AOT khác với kỳ vọng ở runtime.
- **Thư viện có code generation hoặc runtime bytecode manipulation**: cần kiểm tra cơ chế có tương thích với native hay cần phương án build-time thay thế.

Không phải `BeanFactoryPostProcessor`, `BeanPostProcessor` hay proxy nào cũng bị cấm. Vấn đề là **chúng thực thi khi nào, tạo ra điều gì và Spring AOT có thể dự đoán kết quả đó hay không**. Cùng là ứng dụng Spring nhưng một cơ chế do framework hỗ trợ AOT sẵn và một cơ chế tự viết can thiệp classpath tại runtime có rủi ro rất khác nhau.

Ví dụ phân biệt:

| Trường hợp | Thường phù hợp với AOT | Cần rà soát thêm |
| --- | --- | --- |
| Bean khai báo bằng `@Bean`, dependency cố định | Có | Nếu có điều kiện lệ thuộc runtime mà AOT quyết định khi build |
| `@ConfigurationProperties` cho host, port, timeout | Có thể | Nếu giá trị được dùng để đăng ký bean khác nhau lúc build |
| Reflection theo các lớp xác định trước | Có thể | Đảm bảo runtime hints đầy đủ |
| Nạp tên lớp bất kỳ từ thư mục plugin mới lúc chạy | Khó phù hợp với closed world | Cần thiết kế lại khả năng mở rộng |
| Template có trong `src/main/resources` | Có thể | Resource có được đóng gói trong native image không |

## 6. Lợi ích và chi phí: “làm sớm” để “khởi động nhanh”

Khi một phần xử lý Spring được chuyển từ runtime sang build time, ứng dụng có thể giảm số bước phân tích cấu hình, quét và chuẩn bị metadata lúc khởi động. Kết hợp với executable native, lợi ích thường được quan tâm là:

- **Thời gian khởi động**: hữu ích cho tác vụ ngắn, triển khai cần scale nhanh, workload serverless hoặc môi trường khởi tạo instance thường xuyên.
- **Mức dùng bộ nhớ**: một số workload có thể giảm RSS so với chạy ứng dụng tương đương trên JVM, nhưng mức giảm còn tùy GC, dependency, môi trường và tải.
- **Triển khai**: có thể phân phối executable cho nền tảng đích mà không cần cài JVM tại nơi chạy, với điều kiện đáp ứng các dependency native/hệ điều hành cần thiết.

Đổi lại, **build native** thường mất nhiều thời gian, CPU và RAM hơn build JAR JVM; debugging/build-toolchain phức tạp hơn; thư viện dùng hành vi động có thể cần sửa hoặc thêm metadata. Hiệu năng ứng dụng chạy dài hạn, độ trễ và thông lượng cũng có thể khác JVM với JIT. Không có bảo đảm rằng bản native luôn nhanh hoặc tiết kiệm bộ nhớ trong mọi hoàn cảnh.

Đo lường đáng tin cậy cần:

1. Dùng cùng ứng dụng, dữ liệu và các tính năng bật.
2. So sánh trên môi trường CPU/RAM/container tương đương.
3. Phân biệt **thời gian khởi động**, **thời gian sẵn sàng phục vụ**, **RSS**, **độ trễ**, **thông lượng**, **thời gian build** và **kích thước artifact**.
4. Chạy lặp lại, bỏ qua nhiễu hệ thống, ghi rõ JDK/GraalVM/Spring Boot/version plugin và cấu hình.

Đánh giá hiệu quả AOT không thể chỉ nhìn vào lệnh `native-image` thành công; phải quan sát ứng dụng chạy các luồng nghiệp vụ thật.

## 7. Quan sát Spring AOT trong Maven/Gradle

Để thấy Spring làm gì trước Native Image, có thể chủ động chạy bước AOT riêng rồi kiểm tra mã sinh ra. Ví dụ với dự án Spring Boot đã cấu hình đúng plugin:

**Maven:**

~~~bash
./mvnw spring-boot:process-aot
~~~

**Gradle:**

~~~bash
./gradlew processAot
~~~

Tùy hệ build và phiên bản, các file nguồn và metadata AOT thường xuất hiện dưới những thư mục sinh mã trong `target/` (Maven) hoặc `build/` (Gradle). Chúng là **artifact tạo ra khi build**, không phải mã nguồn cần sửa bằng tay. Khi chạy lại build chúng có thể bị sinh đè.

Sau khi bảo đảm JDK/GraalVM có công cụ `native-image`, native compiler và các plugin tương thích, có thể biên dịch toàn bộ:

~~~bash
# Maven: áp dụng khi dự án đã có cấu hình/profile native phù hợp
./mvnw -Pnative native:compile

# Gradle: áp dụng khi đã tích hợp Spring Boot và Native Build Tools
./gradlew nativeCompile
~~~

Trong những dự án dùng Spring Boot Maven parent, profile `native` thường được chuẩn bị sẵn theo convention; dự án tự quản lý Maven lifecycle cần cấu hình tương đương. Gradle cần plugin Spring Boot và `org.graalvm.buildtools.native` tương thích. Native Build Tools chịu trách nhiệm tích hợp native compiler, còn bước `process-aot`/`processAot` đến từ cơ chế build của Spring Boot.

Mục đích chạy riêng bước AOT là để thấy **cấu trúc ứng dụng đã được quyết định và mô tả trước như thế nào**, qua đó kiểm tra sai khác giữa cấu hình build và dự kiến runtime. Sau khi sửa code/config, cần build lại để cập nhật mã AOT; không nên thay đổi thủ công mã trong thư mục generated.

## 8. Cách chẩn đoán khi chạy JVM được nhưng native không chạy đúng

| Triệu chứng | Nơi kiểm tra đầu tiên | Cách xử lý phù hợp |
| --- | --- | --- |
| Bean không xuất hiện, `NoSuchBeanDefinitionException` | Profile, điều kiện, cấu hình có ảnh hưởng bean graph tại lúc AOT | Xác nhận môi trường build; thiết kế lại biến đổi runtime nếu cần |
| Lỗi truy cập constructor/method bằng reflection | Runtime hints và cơ chế gọi động | Đăng ký đúng class/thành viên; kiểm tra thư viện đã hỗ trợ hints chưa |
| Lỗi không tìm thấy file template/schema | Resource hints và tài nguyên đóng gói | Đăng ký resource/pattern đúng, xác minh file có trong classpath build |
| Proxy/AOP hoặc thư viện serialize lỗi ở một nhánh | Tích hợp AOT và metadata của thư viện | Kiểm tra hỗ trợ native, cấu hình proxy/serialization phù hợp |
| Native compilation không tìm thấy executable `native-image` | Native Build Tools và toolchain | Cài/cấu hình GraalVM và công cụ hệ thống tương ứng |
| Native build chạy hết RAM | Tài nguyên của giai đoạn Native Image | Điều chỉnh máy build, tham số và phạm vi dependency; không nhầm với RAM lúc runtime |
| Binary không chạy trên server/container đích | OS/CPU architecture, linker, runtime libraries | Build đúng nền tảng hoặc dùng builder/runtime image tương thích |

Một quy trình kiểm tra ngắn:

1. Chạy test JVM để xác nhận chức năng cơ bản.
2. Chạy bước AOT, kiểm tra log và mã sinh ra; xác nhận profile, điều kiện và bean dự kiến.
3. Chạy native build, phân loại lỗi ở AOT, compiler hay linker.
4. Chạy executable native và test những luồng có reflection/resource/proxy/serialization.
5. Sửa nguyên nhân ở đúng lớp: Spring config, runtime hints, dependency hay toolchain. Build lại và kiểm chứng bằng test tương ứng.

**Tránh kết luận “AOT đã xử lý hết mọi thứ” chỉ vì native image khởi động thành công.** AOT giúp Spring chuẩn bị những gì có thể biết trước, nhưng không thể tự biết toàn bộ hành vi động do application code hoặc thư viện tạo ra sau này.

## 9. Ghi nhớ bản chất của Spring AOT

Ba nhận định giúp giải thích được *vì sao* Spring cần xử lý trước:

1. **Spring trên JVM dựa nhiều vào khám phá và cấu hình lúc chạy**, còn GraalVM Native Image cần một bức tranh đủ rõ về mã có thể thực thi và dữ liệu truy cập động từ lúc build.
2. **Spring AOT đưa phần có thể dự đoán của bootstrap Spring sang build time**, sinh mã đăng ký/khởi tạo bean và cung cấp metadata mà Native Image cần; nó không đơn thuần là bật một cờ tối ưu cho JVM.
3. **Việc chuyển công việc sang build time tạo ra ranh giới mới cho cấu hình và tính mở rộng.** Hiểu ranh giới này giúp chọn đúng chỗ bổ sung hints, viết test tương thích, thiết kế cấu hình và đánh giá lợi ích thời gian khởi động/bộ nhớ một cách thực tế.

Khi nhìn log build và hành vi ứng dụng, có thể lần theo mạch **Spring configuration/bean graph → Spring AOT generated code + hints → GraalVM reachability analysis → native executable → kiểm thử runtime**. Đây là mạch nguyên nhân giải thích cả lợi ích lẫn hạn chế của Spring Boot Native Image.
